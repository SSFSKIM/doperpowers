"""Row order and the snapshot cut (DC2 M4, DX5), against the real child.

The mod names every row the session keeps once, as its append resolves, so
in write order (`block-row` for a response row, `row-seen` for any other);
the child applies each notice under the lock that guards `streaming` and
keeps each loop's last as the snapshot's `cut`, which the module's first
resync seeds with each loop's last row at load (the child's hello `seed`).
A reader that joins the transcript on disk with the stream — DC7's
daemon — needs no row twice, none
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
FLUSH_WAIT = 5.0     # a cut's row, or a named row, not on disk this long is a discontinuity
UNNAMED_AFTER = 2.0  # from first seen on disk: a row past the cut released with no notice for it or any row after it
FAILURES = []


def check(name, ok, detail=""):
    print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else " — %s" % (detail,)), flush=True)
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

    def __init__(self, env=None, session=None):
        Child.n += 1
        self.session = session or "5b000001-0000-4000-8000-%012d" % (0xf00 + Child.n)
        self.proc = subprocess.Popen([SMINOS, "bridge", "--session", self.session], stdout=subprocess.PIPE,
                                     text=True, env={**os.environ, **(env or {})})
        hello = json.loads(self.proc.stdout.readline())
        self.sock, self.nonce, self.seed = hello["socket"], hello.get("nonce"), hello.get("seed")

    def post(self, *events, nonce=None, expect=204):
        """Posts as the mod does, with this child's nonce (or `nonce`); the status."""
        c = Conn(self.sock)
        headers = {"X-Bridge-Nonce": nonce if nonce is not None else self.nonce} if (nonce or self.nonce) else {}
        if nonce == "":
            headers = {}
        c.request("POST", "/events", json.dumps([{"t": int(time.time() * 1000), **e} for e in events]), headers)
        status = c.getresponse().status
        assert expect is None or status == expect, "post answered %d" % status
        return status

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
    """The reference reader of one subscription (DX5's consumer rule, which
    DC7 ports), as the plan's Decision Log states it:

    History waits until each loop's cut row is on disk (5 s, else a
    discontinuity) and reads up to and including it; live, disk rows are
    emitted strictly in disk order, a row past the cut released on whichever
    comes first — its own notice, a notice for any later row of the same loop
    (a row passed over is unnamed), or 2 s after it was first seen on disk with
    neither — and every later row waits behind it. A notice whose row is not on disk within 5 s, and a
    `block-row` for a uuid already released unnamed, end the subscription; a
    `row-seen` for an already released uuid is ignored.

    A loop whose cut is null, or that the cut does not name, had no rows: its
    history is empty. The stream ending is the other discontinuity: the
    consumer ends with it, and a new subscription starts over from a fresh
    snapshot.
    """

    def __init__(self, child, disk, loops=("main",)):
        self.child, self.disk, self.loops = child, disk, loops
        self.out = []            # (uuid, how): how is history, notice or unnamed
        self.how = {}
        self.at = {}             # uuid → when it was emitted
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
        self.at[uuid] = time.time()

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
        released = {}            # loop → how many of its disk rows are emitted
        for loop in self.loops:
            at = cut.get(loop)
            rows = []
            if at is not None:
                deadline = time.time() + FLUSH_WAIT
                while at not in self.disk.rows(loop):
                    if time.time() > deadline:
                        return self.end("the cut's row %s is not on disk" % at)
                    time.sleep(0.02)
                rows = self.disk.rows(loop)
                rows = rows[:rows.index(at) + 1]
            for uuid in rows:
                self.emit(uuid, "history")
            released[loop] = len(rows)
        named = {}               # uuid → when its notice came, for a row not yet emitted
        first_seen = {}          # a disk row past the cut → when it was first seen on disk
        stream_over = False
        while not self.stop.is_set():
            while True:
                try:
                    e = events.get_nowait()
                except queue.Empty:
                    break
                if e is None:
                    stream_over = True
                elif e.get("type") in ("block-row", "row-seen") and (e.get("agentId") or "main") in self.loops:
                    uuid = e["uuid"]
                    if uuid in self.how:
                        if e["type"] == "block-row" and self.how[uuid] == "unnamed":
                            return self.end("a block-row for %s, emitted unnamed" % uuid)
                        continue
                    named[uuid] = time.time()
            now = time.time()
            for loop in self.loops:
                rows = self.disk.rows(loop)
                for uuid in rows[released[loop]:]:
                    first_seen.setdefault(uuid, now)
                while released[loop] < len(rows):
                    head = rows[released[loop]]
                    if head in named:
                        self.emit(head, "notice")
                        del named[head]
                    elif any(u in named for u in rows[released[loop] + 1:]):
                        self.emit(head, "unnamed")
                    elif now - first_seen[head] >= UNNAMED_AFTER:
                        self.emit(head, "unnamed")
                    else:
                        break
                    released[loop] += 1
            late = [u for u, t in named.items() if now - t > FLUSH_WAIT]
            if late:
                return self.end("%s is not on disk %ss after its notice" % (late[0], FLUSH_WAIT))
            if stream_over and not named:
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
    child.resync(cut={"main": "seed-row", "a7": "s-seed"})
    th.join(5)
    check("before the mod's first resync the child is not ready, and says so", before is False, before)
    check("a subscription is held until the first resync, then opens with the snapshot, its cut the resync's (the seed)",
          held and got.get("status") == 200 and got.get("at", 0) >= 0.6 and got["snap"]["sessionInfo"]["cwd"] == "/w"
          and got["snap"]["cut"] == {"main": "seed-row", "a7": "s-seed"},
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


def step_end_drops():
    """A step's end takes all its blocks out of `streaming`, whether or not a
    block-row came for each: a block aborted mid-response is in no later
    snapshot."""
    child = Child()
    child.resync()
    child.post({"type": "turn", "phase": "start", "turnId": "t1", "agentId": None},
               {"type": "step", "phase": "start", "turnId": "t1", "agentId": None, "step": 0, "model": "m"},
               {"type": "chunk", "turnId": "t1", "agentId": None, "step": 0, "chunkIndex": 0,
                "chunk": {"kind": "text", "index": 0, "text": "cut "}},
               {"type": "chunk", "turnId": "t1", "agentId": None, "step": 0, "chunkIndex": 1,
                "chunk": {"kind": "tool", "index": 1, "id": "toolu_1", "name": "Bash"}})
    during = Sub(child).snapshot["streaming"]
    child.post({"type": "step", "phase": "end", "turnId": "t1", "agentId": None, "step": 0, "stopReason": None, "usage": None})
    after = Sub(child).snapshot
    check("a step that ends with no block-row for its blocks leaves streaming whole: a fresh snapshot has no entry for it",
          len(during) == 1 and len(during[0]["blocks"]) == 2 and after["streaming"] == [] and after["turns"],
          "during %s; after %s" % (during, after["streaming"]))
    child.stop()


def seed():
    """The child reads each loop's transcript tail before its hello: the seed
    the mod's first resync carries as the cut."""
    cfg = os.path.join(WORK, "cfg")
    sid = "5b000001-0000-4000-8000-%012d" % 0xfee
    proj = os.path.join(cfg, "projects", "-w")
    os.makedirs(os.path.join(proj, sid, "subagents"))
    with open(os.path.join(proj, sid + ".jsonl"), "w") as f:
        f.write(json.dumps({"uuid": "m1", "type": "user"}) + "\n")
        f.write(json.dumps({"uuid": "m2", "type": "assistant", "message": {"content": "x" * 200000}}) + "\n")
        f.write(json.dumps({"type": "summary", "leafUuid": "m2"}) + "\n")
        f.write('{"uuid": "m3", "type": "us')   # a row still being flushed
    with open(os.path.join(proj, sid, "subagents", "agent-a7.jsonl"), "w") as f:
        f.write(json.dumps({"uuid": "s1", "type": "user"}) + "\n")
    open(os.path.join(proj, sid, "subagents", "agent-a8.jsonl"), "w").close()
    child = Child(env={"CLAUDE_CONFIG_DIR": cfg}, session=sid)
    check("the hello's seed: each loop's last whole row, read from the end (a line with no uuid, and a row half-flushed, passed over); a loop with none is not named",
          child.seed == {"main": "m2", "a7": "s1"}, child.seed)
    child.stop()
    fresh = Child(env={"CLAUDE_CONFIG_DIR": cfg})
    check("a session with no transcript yet: an empty seed", fresh.seed == {}, fresh.seed)
    fresh.stop()


def passed_over():
    """Rows no notice names (the bridge's own compaction rows, the engine's
    reload line) are released by the next notice of their loop, in disk order;
    the 2 s wait is only for such a row last on disk."""
    child, disk = Child(), Disk("passed")
    child.resync()
    c = Consumer(child, disk)
    c.wait("the snapshot", 3, lambda: c.snapshot)
    t0 = time.time()
    disk.write("main", "c1", "system")
    disk.write("main", "c2", "system")
    disk.write("main", "p1")
    child.post(seen("p1"))
    c.wait("p1", 3, lambda: len(c.out) >= 3)
    took = c.at.get("p1", t0 + 99) - t0
    check("unnamed compaction rows followed promptly by a prompt come out in disk order, at once",
          c.out == [("c1", "unnamed"), ("c2", "unnamed"), ("p1", "notice")] and took < 1, "%s after %.2f s" % (c.out, took))
    t1 = time.time()
    disk.write("main", "x1", "system")
    c.wait("x1", 4, lambda: len(c.out) >= 4)
    waited = c.at.get("x1", t1) - t1
    check("an unnamed row last on disk waits the 2 s", c.out[3:] == [("x1", "unnamed")] and 1.9 <= waited < 3,
          "%s after %.2f s" % (c.out[3:], waited))
    t2 = time.time()
    for u in ("k1", "k2", "k3"):     # an idle compaction's rows, written together, none named
        disk.write("main", u, "system")
    c.wait("k3", 5, lambda: len(c.out) >= 7)
    took = [round(c.at.get(u, t2 + 99) - t2, 2) for u in ("k1", "k2", "k3")]
    check("unnamed rows written together, with no notice after them, all come out about 2 s after they were first on disk, in disk order",
          c.out[4:7] == [("k1", "unnamed"), ("k2", "unnamed"), ("k3", "unnamed")] and all(1.9 <= x < 2.8 for x in took),
          "%s after %s s" % (c.out[4:7], took))
    disk.write("main", "a")
    disk.write("main", "b")
    child.post(seen("b"))
    c.wait("b", 3, lambda: len(c.out) >= 9)
    child.post(seen("a"))
    time.sleep(0.3)
    check("a notice for a later row releases the rows before it, unnamed; a row-seen for one released is ignored",
          c.out[7:] == [("a", "unnamed"), ("b", "notice")] and c.ended is None, "%s, ended %s" % (c.out[7:], c.ended))
    child.stop()


def cut_wait():
    """History waits for the cut's row (a seed or a notice ahead of its flush)."""
    child, disk = Child(), Disk("cutwait")
    disk.write("main", "h1")
    child.resync(cut={"main": "h2"})
    c = Consumer(child, disk)
    time.sleep(0.8)
    early = list(c.out)
    disk.write("main", "h2")
    disk.write("main", "h3")
    c.wait("h3", 4, lambda: len(c.out) >= 3)
    check("history waits for the cut's row to be on disk, then reads up to it; the row past it is live",
          early == [] and c.out == [("h1", "history"), ("h2", "history"), ("h3", "unnamed")], "%s then %s" % (early, c.out))
    child.resync(cut={"main": "never"})
    d = Consumer(child, disk)
    d.wait("the end", FLUSH_WAIT + 2, lambda: d.ended)
    check("a cut whose row is not on disk within 5 s is a discontinuity", d.ended == "the cut's row never is not on disk" and not d.out,
          "%s; %s" % (d.ended, d.out))
    child.stop()


def seeded():
    """A loop the cut names is history to it; one it does not name had no rows
    at the snapshot, and every row of it is live."""
    child, disk = Child(), Disk("seeded")
    for u in ("o1", "o2"):
        disk.write("main", u)
    child.resync(cut={"main": "o2"})
    c = Consumer(child, disk, loops=("main", "a7"))
    c.wait("history", 3, lambda: len(c.out) >= 2)
    disk.write("a7", "s1")
    child.post(seen("s1", "a7"))
    disk.write("main", "n1")
    child.post(seen("n1"))
    c.wait("live", 3, lambda: len(c.out) >= 4)
    check("the seed's rows are history; a loop begun after it, and the rows past the seed, come on their notices",
          c.out[:2] == [("o1", "history"), ("o2", "history")] and sorted(c.out[2:]) == [("n1", "notice"), ("s1", "notice")],
          c.out)
    child.stop()


def fence():
    """After a module reload the old instance's in-flight dispatches still
    post to the session's path, which the new module's child now serves: the
    child turns away every post without its own nonce, and changes nothing."""
    old = Child()
    stale = old.nonce
    old.stop()
    new = Child(session=old.session)
    new.resync(cut={"main": "new-row"}, override={"model": "sonnet", "effort": None}, delivered={"m/human": 8})
    sub = Sub(new)
    before = dict(sub.snapshot)
    kept_path = os.path.join(os.environ["SMINOS_HOME"], "bridge", new.session + ".json")
    until(3, lambda: os.path.exists(kept_path))
    with open(kept_path) as f:
        kept_before = f.read()
    stale_resync = {"type": "resync", "turns": [], "streaming": [], "agents": [], "cut": {"main": "old-row"},
                    "override": {"model": "haiku", "effort": None}, "delivered": {"m/human": 3}}
    first = new.post(stale_resync, nonce=stale, expect=None)
    second = new.post(seen("old-row2"), {"type": "gap", "dropped": 1}, nonce=stale, expect=None)
    bare = new.post(stale_resync, nonce="", expect=None)
    time.sleep(0.3)
    after = Sub(new)
    with open(kept_path) as f:
        kept_after = f.read()
    check("the hello carries a nonce, each child its own", bool(stale) and bool(new.nonce) and stale != new.nonce)
    check("an old module instance's posts (its child's nonce, or none) are refused (409)",
          (first, second, bare) == (409, 409, 409), (first, second, bare))
    check("and change nothing: the cut, the model, the delivered keys, the open subscription",
          after.snapshot["cut"] == before["cut"] == {"main": "new-row"} and after.snapshot["override"] == before["override"]
          and kept_after == kept_before and not sub.ended and not sub.lines,
          "cut %s, override %s, kept %s → %s, subscription ended %s, lines %s" % (
              after.snapshot["cut"], after.snapshot["override"], kept_before, kept_after, sub.ended, sub.lines))
    new.post(seen("next-row"))
    until(2, lambda: sub.lines)
    check("the new module's own posts go on", [e.get("uuid") for e in sub.lines] == ["next-row"], sub.lines)
    new.stop()


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


for case in (readiness, cut, step_end_drops, seed, flush_ahead, between_chunk_and_row, notice_past_bound, passed_over, cut_wait, seeded,
             fence, subagent_loop):
    try:
        case()
    except Exception as e:  # noqa: BLE001 — a case that cannot go on is a failed case
        check("%s ran to its end" % case.__name__, False, "%s: %s" % (type(e).__name__, e))
sys.exit(1 if FAILURES else 0)
