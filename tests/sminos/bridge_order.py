"""Row order and the snapshot cut (DC2 M4, DX5), against the real child.

The mod names every row the session keeps once, in write order, before the
row is written (`block-row` for a response row, `row-seen` for any other);
the child applies each notice under the lock that guards `streaming` and
keeps each loop's last as the snapshot's `cut`. A reader that joins the
transcript on disk with the stream — DC7's daemon — needs no row twice, none
lost, and none both in history and still streaming. `Consumer` below is the
reference for that reader (DX5's consumer rule, which DC7 ports); the
scenarios drive the real child as the mod would, write the "transcript" as
the engine would, and check what the consumer emits.

    python3 bridge_order.py <sminos> <work-dir>      # prints ok/FAIL lines

The caller isolates HOME and SMINOS_HOME (short, for the socket's path).
"""

import http.client
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

SMINOS, WORK = sys.argv[1], sys.argv[2]
FLUSH_WAIT = 5.0     # a named row not on disk this long after its notice ends the subscription
UNNAMED_AFTER = 2.0  # a disk row past the cut that no notice named this long is emitted unnamed
FAILURES = []


def check(name, ok, detail=""):
    print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else " — %s" % detail), flush=True)
    if not ok:
        FAILURES.append(name)


class Conn(http.client.HTTPConnection):
    def __init__(self, path, timeout=10):
        super().__init__("bridge", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class Child:
    """The child, spawned as the mod spawns it; this process is its mod."""

    n = 0

    def __init__(self, env=None):
        Child.n += 1
        self.session = "5b000001-0000-4000-8000-%012d" % (0xf00 + Child.n)
        self.proc = subprocess.Popen([SMINOS, "bridge", "--session", self.session], stdout=subprocess.PIPE,
                                     text=True, env={**os.environ, **(env or {})})
        self.sock = json.loads(self.proc.stdout.readline())["socket"]

    def post(self, *events):
        c = Conn(self.sock)
        c.request("POST", "/events", json.dumps([{"t": int(time.time() * 1000), **e} for e in events]))
        assert c.getresponse().status == 204

    def status(self):
        c = Conn(self.sock)
        c.request("GET", "/status")
        return json.loads(c.getresponse().read())

    def resync(self, **fields):
        self.post({"type": "resync", "turns": [], "streaming": [], "agents": [], **fields})

    def stop(self):
        self.proc.kill()
        self.proc.wait()


class Disk:
    """The transcripts as the engine writes them: one file per loop."""

    def __init__(self, name):
        self.dir = os.path.join(WORK, name)
        os.makedirs(self.dir)

    def path(self, loop):
        return os.path.join(self.dir, loop + ".jsonl")

    def write(self, loop, uuid, kind="user"):
        with open(self.path(loop), "a") as f:
            f.write(json.dumps({"uuid": uuid, "type": kind}) + "\n")

    def rows(self, loop):
        try:
            with open(self.path(loop)) as f:
                return [json.loads(line)["uuid"] for line in f if line.strip()]
        except OSError:
            return []


class Sub:
    """A bare subscription: its snapshot, then its lines, and whether it ended."""

    def __init__(self, child):
        c = Conn(child.sock, timeout=None)
        c.request("GET", "/events")
        self.r = c.getresponse()
        self.snapshot = json.loads(self.r.readline())
        self.lines, self.ended = [], False
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.r:
            self.lines.append(json.loads(line))
        self.ended = True


def until(seconds, fn):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.02)
    return False


def seen(uuid, loop="main"):
    return {"type": "row-seen", "uuid": uuid, "agentId": None if loop == "main" else loop, "door": "tool-result"}


class Consumer:
    """The reference reader of one subscription (DX5's consumer rule):

    1. History: each loop's disk rows up to and including its cut (waiting,
       at most FLUSH_WAIT, for the cut's row to be flushed); a loop whose cut
       is null (or absent) is read to the end of its file at snapshot time.
    2. Live, in notice order: a notice emits the row it names from disk once
       flushed; one not on disk within FLUSH_WAIT ends the subscription. A
       `row-seen` for a row already emitted is dropped; a `block-row` for a
       row already emitted unnamed ends the subscription (that block would
       stay beside its row; a fresh snapshot heals it).
    3. A disk row past the history that no notice named within UNNAMED_AFTER
       is emitted, unnamed, in disk order.
    4. The stream ending is the one discontinuity: the consumer ends with
       it, and a new subscription starts over from a fresh snapshot.
    """

    def __init__(self, child, disk, loops=("main",)):
        self.child, self.disk, self.loops = child, disk, loops
        self.out = []            # (uuid, how): how is history, notice or unnamed
        self.how = {}
        self.ended = None
        self.snapshot = None
        self.status = None
        self.lines = []          # every stream line after the snapshot
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def emit(self, uuid, how):
        self.out.append((uuid, how))
        self.how[uuid] = how

    def end(self, why):
        self.ended = why
        self.stop.set()

    def run(self):
        c = Conn(self.child.sock, timeout=None)
        c.request("GET", "/events")
        r = c.getresponse()
        self.status = r.status
        if r.status != 200:
            return self.end("refused %d" % r.status)
        self.snapshot = json.loads(r.readline())
        events = queue.Queue()

        def read():
            for line in r:
                e = json.loads(line)
                self.lines.append(e)
                events.put(e)
            events.put(None)
        threading.Thread(target=read, daemon=True).start()
        cut = self.snapshot.get("cut") or {}
        for loop in self.loops:
            at = cut.get(loop)
            if at is None:
                rows = self.disk.rows(loop)
            else:
                deadline = time.time() + FLUSH_WAIT
                while at not in self.disk.rows(loop):
                    if time.time() > deadline:
                        return self.end("the cut's row %s is not on disk" % at)
                    time.sleep(0.02)
                rows = self.disk.rows(loop)
                rows = rows[:rows.index(at) + 1]
            for uuid in rows:
                self.emit(uuid, "history")
        notices, named, first_seen = [], set(), {}
        stream_over = False
        while not self.stop.is_set():
            while True:
                try:
                    e = events.get_nowait()
                except queue.Empty:
                    break
                if e is None:
                    stream_over = True
                elif e.get("type") in ("block-row", "row-seen"):
                    notices.append((e, time.time()))
                    named.add(e["uuid"])
            while notices:
                e, at = notices[0]
                uuid, loop = e["uuid"], e.get("agentId") or "main"
                if uuid in self.how:
                    if e["type"] == "block-row" and self.how[uuid] == "unnamed":
                        return self.end("a block-row for %s, emitted unnamed" % uuid)
                    notices.pop(0)
                    continue
                if uuid in self.disk.rows(loop):
                    self.emit(uuid, "notice")
                    notices.pop(0)
                    continue
                if time.time() - at > FLUSH_WAIT:
                    return self.end("%s is not on disk %ss after its notice" % (uuid, FLUSH_WAIT))
                break
            now = time.time()
            for loop in self.loops:
                for uuid in self.disk.rows(loop):
                    if uuid in self.how or uuid in named:
                        continue
                    first_seen.setdefault(uuid, now)
                    if now - first_seen[uuid] >= UNNAMED_AFTER:
                        self.emit(uuid, "unnamed")
            if stream_over and not notices:
                return self.end("the stream ended")
            time.sleep(0.02)

    def wait(self, what, seconds, fn):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if fn():
                return True
            time.sleep(0.02)
        return False

    def uuids(self):
        return [u for u, _ in self.out]


def gap_free(out, expect):
    return [u for u, _ in out] == expect


# -- readiness


def readiness():
    child = Child()
    before = child.status().get("ready")
    t0 = time.time()
    got = {}

    def sub():
        c = Conn(child.sock, timeout=None)
        c.request("GET", "/events")
        r = c.getresponse()
        got["status"], got["at"] = r.status, time.time() - t0
        got["snap"] = json.loads(r.readline()) if r.status == 200 else None
    th = threading.Thread(target=sub)
    th.start()
    time.sleep(0.5)
    child.post({"type": "session", "phase": "start", "session": child.session, "cwd": "/w"})
    time.sleep(0.2)
    held = "status" not in got
    child.resync()
    th.join(5)
    check("before the mod's first resync the child is not ready, and says so", before is False, before)
    check("a subscription is held until the first resync, then opens with the snapshot",
          held and got.get("status") == 200 and got.get("at", 0) >= 0.6 and got["snap"]["sessionInfo"]["cwd"] == "/w",
          got)
    check("then the child is ready", child.status().get("ready") is True)
    child.stop()
    late = Child(env={"SMINOS_BRIDGE_READY_WAIT": "1"})
    c = Conn(late.sock, timeout=10)
    t0 = time.time()
    c.request("GET", "/events")
    r = c.getresponse()
    took = time.time() - t0
    check("a subscription no first resync answers within the wait is refused (503)",
          r.status == 503 and 0.9 <= took < 3, "%s after %.2f s" % (r.status, took))
    late.stop()


# -- the cut


def cut():
    child = Child()
    child.resync(cut={"main": "m0", "a7": "s0"})
    snap = Sub(child)
    check("a resync's cut is the snapshot's", snap.snapshot["cut"] == {"main": "m0", "a7": "s0"}, snap.snapshot["cut"])
    child.post({"type": "turn", "phase": "start", "turnId": "t1", "agentId": None},
               {"type": "step", "phase": "start", "turnId": "t1", "agentId": None, "step": 0, "model": "m"},
               {"type": "chunk", "turnId": "t1", "agentId": None, "step": 0, "chunkIndex": 0,
                "chunk": {"kind": "text", "index": 0, "text": "Hi"}},
               seen("m1"), seen("s1", "a7"),
               {"type": "block-row", "uuid": "m2", "turnId": "t1", "agentId": None, "step": 0, "index": 0})
    after = Sub(child)
    s = after.snapshot
    check("each loop's cut is its last notice applied, a block-row's included",
          s["cut"] == {"main": "m2", "a7": "s1"}, s["cut"])
    check("and the block its row settled has left streaming with it",
          [m for m in s["streaming"] if m["turnId"] == "t1"][0]["blocks"] == [], s["streaming"])
    child.resync(cut={"main": "m2"})
    ok = until(3, lambda: snap.ended and after.ended)
    check("a later resync ends every open subscription; none sees a resync line",
          ok and not [e for c in (snap, after) for e in c.lines if e.get("type") == "resync"],
          "%s / %s" % (snap.ended, after.ended))
    again = Sub(child)
    check("and the next snapshot's cut is the resync's, the loops it does not name gone",
          again.snapshot["cut"] == {"main": "m2"}, again.snapshot["cut"])
    child.stop()


# -- the consumer, through the cases the order exists for


def flush_ahead():
    """A row flushed to disk before its notice reached the child: across a
    subscription's start, and across a reconnect."""
    child, disk = Child(), Disk("ahead")
    child.resync()
    for u in ("r1", "r2"):
        child.post(seen(u))
        disk.write("main", u)
    disk.write("main", "r3")         # on disk; its notice still on its way
    c = Consumer(child, disk)
    c.wait("history", 3, lambda: len(c.out) >= 2)
    time.sleep(0.6)
    child.post(seen("r3"))
    disk.write("main", "r4")
    time.sleep(0.2)
    child.post(seen("r4"))
    c.wait("r4", 3, lambda: len(c.out) >= 4)
    check("a row on disk ahead of its notice at the subscription's start: history to the cut, then the row on its notice",
          c.out == [("r1", "history"), ("r2", "history"), ("r3", "notice"), ("r4", "notice")] and c.ended is None,
          c.out)
    # Its notice later than the bound: emitted unnamed, the notice then dropped.
    disk.write("main", "r5")
    c.wait("r5 unnamed", 4, lambda: len(c.out) >= 5)
    child.post(seen("r5"))
    time.sleep(0.3)
    check("a row whose notice comes past the 2 s bound is emitted unnamed, once; its late row-seen is dropped",
          c.out[4:] == [("r5", "unnamed")] and c.ended is None, c.out)
    # Across a reconnect: the mod's resync (its cut short of a row already
    # flushed) ends the subscription; the next one reads to the cut and
    # takes the row on its notice.
    disk.write("main", "r6")
    child.resync(cut={"main": "r5"})
    c.wait("the end", 3, lambda: c.ended)
    d = Consumer(child, disk)
    d.wait("history", 3, lambda: len(d.out) >= 5)
    time.sleep(0.4)
    child.post(seen("r6"))
    d.wait("r6", 3, lambda: len(d.out) >= 6)
    check("across a reconnect: the stream ends, and the next subscription has every row once, in order",
          c.ended == "the stream ended" and gap_free(d.out, ["r1", "r2", "r3", "r4", "r5", "r6"])
          and d.how["r6"] == "notice", "%s; %s" % (c.ended, d.out))
    child.stop()


def between_chunk_and_row():
    """A subscription opened after a response's last chunk and before its
    block-row: the block is in the snapshot's streaming, not in history; its
    row comes once, on the block-row."""
    child, disk = Child(), Disk("between")
    child.resync()
    child.post(seen("p1"))
    disk.write("main", "p1")
    child.post({"type": "turn", "phase": "start", "turnId": "t1", "agentId": None},
               {"type": "step", "phase": "start", "turnId": "t1", "agentId": None, "step": 0, "model": "m"},
               {"type": "chunk", "turnId": "t1", "agentId": None, "step": 0, "chunkIndex": 0,
                "chunk": {"kind": "text", "index": 0, "text": "Hello"}})
    c = Consumer(child, disk)
    c.wait("the snapshot", 3, lambda: c.snapshot and c.out)
    blocks = [b for m in c.snapshot["streaming"] for b in m["blocks"]]
    child.post({"type": "block-row", "uuid": "a1", "turnId": "t1", "agentId": None, "step": 0, "index": 0})
    time.sleep(0.3)
    disk.write("main", "a1", "assistant")
    c.wait("a1", 3, lambda: len(c.out) >= 2)
    check("a subscription between a response's last chunk and its block-row: the block streams, its row comes once on the block-row",
          [b["text"] for b in blocks] == ["Hello"] and c.out == [("p1", "history"), ("a1", "notice")] and c.ended is None,
          "%s; %s" % (blocks, c.out))
    late = Consumer(child, disk)
    late.wait("history", 3, lambda: len(late.out) >= 2)
    check("one opened after the block-row: no block streaming, the row in history",
          not [b for m in late.snapshot["streaming"] for b in m["blocks"]] and late.out == [("p1", "history"), ("a1", "history")],
          "%s; %s" % (late.snapshot["streaming"], late.out))
    child.stop()


def notice_past_bound():
    """A response row on disk whose block-row comes past the 2 s bound: it
    was emitted unnamed beside its streaming block, so the block-row ends the
    subscription; the fresh one is whole."""
    child, disk = Child(), Disk("pastbound")
    child.resync()
    child.post({"type": "turn", "phase": "start", "turnId": "t1", "agentId": None},
               {"type": "step", "phase": "start", "turnId": "t1", "agentId": None, "step": 0, "model": "m"},
               {"type": "chunk", "turnId": "t1", "agentId": None, "step": 0, "chunkIndex": 0,
                "chunk": {"kind": "text", "index": 0, "text": "Hi"}})
    c = Consumer(child, disk)
    c.wait("the snapshot", 3, lambda: c.snapshot)
    disk.write("main", "a1", "assistant")
    c.wait("a1 unnamed", 4, lambda: c.out)
    child.post({"type": "block-row", "uuid": "a1", "turnId": "t1", "agentId": None, "step": 0, "index": 0})
    c.wait("the end", 3, lambda: c.ended)
    d = Consumer(child, disk)
    d.wait("history", 3, lambda: d.out)
    check("a response row's notice past the 2 s bound ends the subscription; the next has the row once, its block gone",
          c.out == [("a1", "unnamed")] and c.ended == "a block-row for a1, emitted unnamed"
          and d.out == [("a1", "history")] and not [b for m in d.snapshot["streaming"] for b in m["blocks"]],
          "%s, %s; then %s" % (c.out, c.ended, d.out))
    child.stop()


def subagent_loop():
    """Each loop is cut on its own: a subagent's rows in its own file."""
    child, disk = Child(), Disk("loops")
    child.resync()
    child.post(seen("m1"), seen("s1", "a7"))
    disk.write("main", "m1")
    disk.write("a7", "s1")
    disk.write("a7", "s2")
    c = Consumer(child, disk, loops=("main", "a7"))
    c.wait("history", 3, lambda: len(c.out) >= 2)
    time.sleep(0.3)
    child.post(seen("s2", "a7"))
    c.wait("s2", 3, lambda: len(c.out) >= 3)
    check("a subagent's loop has a cut of its own; its rows past it come on their notices",
          c.snapshot["cut"] == {"main": "m1", "a7": "s1"} and c.out == [("m1", "history"), ("s1", "history"), ("s2", "notice")],
          "%s; %s" % (c.snapshot["cut"], c.out))
    child.stop()


for case in (readiness, cut, flush_ahead, between_chunk_and_row, notice_past_bound, subagent_loop):
    try:
        case()
    except Exception as e:  # noqa: BLE001 — a case that cannot go on is a failed case
        check("%s ran to its end" % case.__name__, False, "%s: %s" % (type(e).__name__, e))
sys.exit(1 if FAILURES else 0)
