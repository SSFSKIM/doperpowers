#!/usr/bin/env python3
"""bench_open — how long a session view takes to open, end to end through the
real uplink and the real hub code, and phase by phase in-process (the desk
open-fast spec, docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md,
M2). An open runs from a browser client's `subscribe` to its receipt of the
`snapshot`: E. The machine's share, N, from the subscribe frame's arrival at
the uplink's reader to the snapshot's emission, is the plane's open line in
daemon.log, reported beside E as a diagnostic.

    bench_open.py --uplink --hub local --maws <MAWS worktree> [--live [--thinking] [--model M] | --synthetic-rows N]
                  --scenario S --opens N [--pause-stream 4 --backlog 4m] [--keep]
    bench_open.py --uplink --hub standin [...]
    bench_open.py --micro --session <id> --sminos-home <dir> [--home <dir>] [--opens N]

The full path (`--uplink`): this checkout's `sminos daemon uplink` under a
temporary HOME and SMINOS_HOME, enrolled at a hub this instrument starts —
`--hub local`, the hub's own Worker on a local runtime (`pnpm --filter
desk-hub local --state <tmp> --port <free>` in the `--maws` worktree), a
browser client on the project's socket (ws_client); or `--hub standin`,
hub_standin.py, its `/control/send` the client's subscribe and its stamped
`sessions` what the client receives. The session is fake_session.py's
scripted one by default; `--live` an isolated headless session as
mods/live-bridge-check.py isolates one (it spends haiku calls: run by hand,
with the gateway's keys in the environment; `--thinking` turns extended
thinking on); `--synthetic-rows N` a transcript of N rows shaped like a real
one, with no bridge. Every DX4 message the client received for an open goes
through the reference consumer (dx4_consumer.Consumer), and the inventory
says what is missing against the transcript on disk and the DX5 events the
session emitted (the fake session's posts, or a live session's probe
subscription), with the bridge's snapshot line placed among them for each
subscription the plane served (the uplink here runs under a bootstrap that
tees each subscription's first bridge lines, its sub beside them: nothing of
the uplink's behavior changes).

Scenarios: `idle` (opens between turns, after one uncounted open that builds
the index), `after-prompt` (each open made on the prompt row's notice),
`mid-message` (`--thinking` live, or the fake session's scripted message: the
open made on the first text chunk after the thinking block's `block-row`; it
counts only when the probe shows it inside that window, which each line
reports; a first live message with no thinking stops the run), `long-answer`
(the same window, opened at +1 s and re-subscribed at +7 s: an `end` before
the step's is said), `kill` (live: the child SIGKILLed mid-stream by the pid
its /status answers, the client subscribing again on each `end`, measured
from the kill to the successor's bridged snapshot), `restart` (the same open
on a fresh uplink, then after each restart), `held` (local hub: the pause
proxy between the uplink and the hub; a subscription streaming, a second
machine's upload of `--backlog` bytes fanned out down the uplink's stream,
the proxy pausing it on its first `events` frame for `--pause-stream`
seconds; the chunks' lag and the hub's answers in that window, and an open
1 s after it resumes).

Each open prints one JSON line — {"mode", "scenario", "load1", "E", "N",
"arrived", "taken", "build", "cpu_ms", "rows", "cut", "waits", "holes",
"dups", "gaps", "vanished", ...} — and each scenario a summary line: min /
p50 / max of E and N over the opens that count, and the load's range
(`load1` is the 1-minute load average, uptime's first figure).

The micro-benchmark (`--micro`): one Subscription made as Plane.subscribe
makes it and pumped as the uplink pumps it, in this process, against a
session's bridge and transcript under the named SMINOS_HOME (and HOME), the
open's phases stamped — the bench's plane_open.py, ported. It leaves out the
reader queue, the record scan, the ticks, the refreshes, the warmer and the
uplink's thread: its figure is N_micro, not N and not E. It writes nothing
under the directories it reads (the plane's log lines are kept here).
"""

import argparse
import base64
import bisect
import collections
import glob
import http.client
import importlib.util
import json
import os
import random
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid as uuidlib

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts")
SMINOS = os.path.join(SCRIPTS, "sminos")
sys.path.insert(0, HERE)

import dx4_consumer  # noqa: E402

KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"   # the stand-in's org key: bytes(range(32)), base64url
BASE_KEYS = ("PATH", "TERM", "LANG", "USER", "LOGNAME", "SHELL", "TMPDIR")
SCENARIOS = ("idle", "after-prompt", "mid-message", "long-answer", "kill", "restart", "held")
TEE_LINES = 3          # bridge lines teed per subscription: its snapshot, and what follows to place it
LEAVES_OUT = "the reader queue, the record scan, the ticks, the refreshes, the warmer and the uplink's thread"

PROMPTS = {
    "settle": "Reply with the single word: ready. Use no tools.",
    "after-prompt": "Say hello in five words. Use no tools.",
    "mid-message": ("Think the plot through step by step before you answer. Then write a 400-word story about a "
                    "lighthouse keeper who finds a message in a bottle. Plain prose, no headings. Use no tools."),
    "long-answer": ("Think the plot through step by step before you answer. Then write a 900-word story about a "
                    "lighthouse keeper who finds a message in a bottle. Plain prose, no headings. Use no tools."),
    "kill": "Write a 450-word story about a lighthouse keeper. Plain prose, no headings. Use no tools.",
}


# ------------------------------------------------------------- what is read


OPEN_LINE = re.compile(
    r"plane: open (?P<sub>\S+) of (?P<sid>[0-9a-f]{8})(?:/(?P<agent>\S+))?: (?P<outcome>.*?) after "
    r"(?P<N>-?\d+\.\d+) s from the subscribe's arrival \((?P<bridge>.*?); build: (?P<build>.*?), "
    r"cut (?P<cut>on disk|not on disk|null); waits (?P<waits>\d+)\)$")
BRIDGE_CLAUSE = re.compile(r"bridge: snapshot arrived (-?\d+\.\d+) s, taken (-?\d+\.\d+) s")
BUILD_CLAUSE = re.compile(r"(\w+) (\d+) ms (\d+) rows")


def parse_open_line(line):
    """The plane's open line (the spec's section 5) as figures, or None."""
    m = OPEN_LINE.search(line.rstrip("\n"))
    if not m:
        return None
    out = {"sub": m["sub"], "outcome": m["outcome"], "N": float(m["N"]), "arrived": None, "taken": None,
           "bridge": m["bridge"], "build": None, "cpu_ms": None, "rows": None, "cut": m["cut"],
           "waits": int(m["waits"])}
    b = BRIDGE_CLAUSE.fullmatch(m["bridge"])
    if b:
        out["arrived"], out["taken"] = float(b[1]), float(b[2])
    k = BUILD_CLAUSE.fullmatch(m["build"])
    if k:
        out["build"], out["cpu_ms"], out["rows"] = k[1], int(k[2]), int(k[3])
    else:
        out["build"] = m["build"]
    return out


def open_lines(path):
    """Every open line in a daemon.log, by sub (the last, should one repeat)."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                if "plane: open " in line:
                    rec = parse_open_line(line)
                    if rec:
                        out[rec["sub"]] = rec
    except FileNotFoundError:
        pass
    return out


def stats(xs):
    """min / p50 / max of the figures that are there."""
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {"n": 0, "min": None, "p50": None, "max": None}
    return {"n": len(xs), "min": round(xs[0], 3), "p50": round(statistics.median(xs), 3), "max": round(xs[-1], 3)}


def size_arg(text):
    """`4m`, `512k`, `1000000`: bytes."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", text.strip())
    if not m:
        raise argparse.ArgumentTypeError("a size is a number with an optional k or m: %r" % text)
    return int(float(m[1]) * {"": 1, "k": 1 << 10, "m": 1 << 20}[m[2].lower()])


def load1():
    return round(os.getloadavg()[0], 2)


def uptime():
    return subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()


def event_key(e):
    """A DX5 event as the child fans it out, less the subscriber's own `n`."""
    return json.dumps({k: v for k, v in e.items() if k != "n"}, sort_keys=True)


def place_snapshots(backbone, tees):
    """One ordered DX5 stream with the bridge's snapshot line for each
    subscription the plane served placed in it, as the inventory reads it:
    `backbone` the session's events in the child's order, [(at, event)];
    `tees` [{"sub", "lines": [(at, line), ...]}], each subscription's first
    bridge lines, its snapshot first. The child takes a snapshot and adds its
    subscriber under the lock that applies events, so a snapshot stands just
    before the first event its subscriber was sent: placed there when that
    event is in the backbone (the nearest copy in time), else by its arrival
    stamp. Returns (events, {sub: "event" | "time"})."""
    positions = {}
    for i, (_, e) in enumerate(backbone):
        positions.setdefault(event_key(e), []).append(i)
    stamps = [at for at, _ in backbone]
    inserts, how = [], {}
    for t in tees:
        lines = t.get("lines") or []
        if not lines or not isinstance(lines[0][1], dict) or lines[0][1].get("type") != "snapshot":
            continue
        snap_at, snap = lines[0]
        pos = None
        for at, e in lines[1:]:
            found = positions.get(event_key(e)) if isinstance(e, dict) else None
            if found:
                pos = min(found, key=lambda i: abs(backbone[i][0] - at))
                how[t["sub"]] = "event"
                break
        if pos is None:
            pos = bisect.bisect_right(stamps, snap_at)
            how[t["sub"]] = "time"
        inserts.append((pos, snap_at, {**snap, "sub": t["sub"]}))
    inserts.sort(key=lambda x: (x[0], x[1]))
    out, k = [], 0
    for i, (_, e) in enumerate(backbone):
        while k < len(inserts) and inserts[k][0] <= i:
            out.append(inserts[k][2])
            k += 1
        out.append(e)
    out += [x[2] for x in inserts[k:]]
    return out, how


def read_tees(path):
    """The uplink's teed bridge lines, per sub: [{"sub", "lines"}]."""
    by = collections.OrderedDict()
    try:
        with open(path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                by.setdefault(rec["sub"], []).append((rec["k"], rec["at"], rec["line"]))
    except FileNotFoundError:
        pass
    return [{"sub": s, "lines": [(at, obj) for _, at, obj in sorted(v, key=lambda x: x[0])]} for s, v in by.items()]


def steps_seen(events, since=0.0, agent=None):
    """What a probe saw of each model request of a loop since `since`:
    (turnId, agentId, step) → {"kinds": {index: kind}, "named": {index: at
    of its block-row}, "thinking_named" (the first thinking block's
    block-row), "text_after" (the first text chunk after it), "end" (its
    step end, or its turn's completion cutting it off), "chunks"}."""
    out = {}
    turns_done = {}
    for at, e in events:
        if at < since or not isinstance(e, dict) or (e.get("agentId") or None) != agent:
            continue
        kind = e.get("type")
        if kind == "turn" and e.get("phase") == "complete":
            turns_done.setdefault(e.get("turnId"), at)
            continue
        key = (e.get("turnId"), e.get("agentId"), e.get("step"))
        if kind not in ("chunk", "block-row", "step"):
            continue
        s = out.setdefault(key, {"kinds": {}, "named": {}, "thinking_named": None, "text_after": None, "end": None,
                                 "chunks": 0, "start": None})
        if kind == "chunk":
            c = e.get("chunk") or {}
            s["chunks"] += 1
            s["kinds"].setdefault(c.get("index"), c.get("kind"))
            if c.get("kind") == "text" and s["thinking_named"] is not None and s["text_after"] is None:
                s["text_after"] = at
        elif kind == "block-row":
            s["named"].setdefault(e.get("index"), at)
            if s["kinds"].get(e.get("index")) == "thinking" and s["thinking_named"] is None:
                s["thinking_named"] = at
        elif kind == "step":
            if e.get("phase") == "start":
                s["start"] = s["start"] or at
            elif e.get("phase") == "end" and s["end"] is None:
                s["end"] = at
    for key, s in out.items():
        if s["end"] is None and key[0] in turns_done:
            s["end"] = turns_done[key[0]]
    return out


def in_window(named, end, at):
    """Whether an open made at `at` fell after the thinking block's
    block-row and before its step's end."""
    return named is not None and end is not None and named < at < end


# ------------------------------------------------------------- the uplink's bootstrap


def install_tee(P, path):
    """Each subscription's first TEE_LINES bridge lines, with its sub and
    their arrival, appended to `path` from the reader's thread: a snapshot
    line's place among the session's events is found from the event that
    follows it (place_snapshots). The plane's code is wrapped, not changed."""
    lock = threading.Lock()
    f = open(path, "a", buffering=1)
    reader_init, reader_put, sub_init = P.BridgeReader.__init__, P.BridgeReader.put, P.Subscription.__init__

    def flush(r):
        b = r._bench
        if b["sub"] is None:
            return
        while b["written"] < len(b["lines"]):
            at, obj = b["lines"][b["written"]]
            f.write(json.dumps({"sub": b["sub"], "k": b["written"], "at": at, "line": obj}) + "\n")
            b["written"] += 1

    def init(self, *args, **kwargs):
        reader_init(self, *args, **kwargs)
        self._bench = {"sub": None, "lines": [], "written": 0}

    def put(self, item):
        b = getattr(self, "_bench", None)
        if b is not None and item[0] == "line" and len(b["lines"]) < TEE_LINES:
            with lock:
                b["lines"].append((time.time(), item[1]))
                flush(self)
        reader_put(self, item)

    def subscription(self, *args, **kwargs):
        sub_init(self, *args, **kwargs)
        r = self.reader
        if r is not None and getattr(r, "_bench", None) is not None:
            with lock:
                r._bench["sub"] = self.sub
                flush(r)

    P.BridgeReader.__init__, P.BridgeReader.put, P.Subscription.__init__ = init, put, subscription


def uplink_main(scripts, tee):
    sys.path.insert(0, os.path.abspath(scripts))
    import sminos_plane
    install_tee(sminos_plane, tee)
    import sminos
    sminos.main(["daemon", "uplink"])


# ------------------------------------------------------------- http


def call(url, method, path, body=None, headers=None, timeout=30):
    u = urllib.parse.urlsplit(url)
    c = http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    c.request(method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        r = c.getresponse()
        raw = r.read()
        try:
            return r.status, json.loads(raw or b"{}")
        except ValueError:
            return r.status, {"raw": raw.decode("utf-8", "replace")[:300]}
    finally:
        c.close()


def wait_for(what, seconds, fn, every=0.05):
    deadline = time.time() + seconds
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))


def free_pair():
    """A port n with n and n + 1 free on 127.0.0.1 (the local hub takes both)."""
    for _ in range(200):
        n = random.randint(20000, 60000)
        socks = []
        try:
            for p in (n, n + 1):
                s = socket.socket()
                s.bind(("127.0.0.1", p))
                socks.append(s)
            return n
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    raise RuntimeError("no free port pair")


def sub_id():
    return base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()   # DX3: 128 bits, base64url


# ------------------------------------------------------------- the hubs and their browsers


class StandinBrowser:
    """A browser of the project as the stand-in plays it: a subscribe is a
    frame written down the uplink's stream (its `at`, when flushed, the
    open's start), and what the uplink posted is the stand-in's stamped
    `sessions`."""

    def __init__(self, url, project, machine):
        self.url, self.project, self.machine = url, project, machine
        self.seen, self.msgs = 0, []

    def send(self, frame_):
        status, body = call(self.url, "POST", "/control/send", {"frames": [frame_]})
        if status != 200:
            raise RuntimeError("the stand-in did not write the frame: %s %s" % (status, body))
        return body.get("at") or time.time()

    def poll(self):
        status, body = call(self.url, "GET", "/control/since?sessions=%d" % self.seen)
        got = body.get("sessions") or []
        self.seen += len(got)
        self.msgs += [(e.get("at") or e.get("received"), e["message"]) for e in got]

    def subscribe(self, session, agent=None):
        sub = sub_id()
        return sub, self.send({"t": "subscribe", "project": self.project, "session": session, "agentId": agent,
                               "sub": sub})

    def unsubscribe(self, sub):
        self.send({"t": "unsubscribe", "project": self.project, "sub": sub})

    def close(self):
        pass


class LocalBrowser:
    """A browser of the project on the local hub: DX3 over its socket, each
    frame stamped on arrival (ws_client)."""

    def __init__(self, url, project, machine):
        import ws_client
        self.project, self.machine = project, machine
        ws_url = "ws" + url[len("http"):] + "/api/projects/%s/socket" % project
        self.ws = wait_for("the project's socket at the local hub", 30, lambda: self.connect(ws_client, ws_url), 0.2)
        self.seen, self.msgs = 0, []

    @staticmethod
    def connect(ws_client, url):
        try:
            return ws_client.WebSocket(url)
        except OSError:
            return None

    def send(self, frame_):
        at = time.time()
        self.ws.send(frame_)
        return at

    def poll(self):
        got = self.ws.stamped(self.seen)
        self.seen += len(got)
        self.msgs += [(at, f["message"]) for at, f in got if f.get("t") == "session"]

    def subscribe(self, session, agent=None):
        sub = sub_id()
        return sub, self.send({"t": "subscribe", "session": session, "agentId": agent, "sub": sub,
                               "machine": self.machine})

    def unsubscribe(self, sub):
        self.send({"t": "unsubscribe", "sub": sub})

    def close(self):
        self.ws.close()


class Standin:
    """hub_standin.py: one machine, `testhost`, enrolled already."""

    name, org, machine = "standin", "org-1", "testhost"

    def __init__(self, rig):
        port_file = os.path.join(rig.root, "hub.port")
        self.proc = rig.spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1",
                               "2000"], log="standin.out")
        self.url = "http://127.0.0.1:%s" % wait_for("the stand-in's port", 10, lambda: _read(port_file))
        self.key = KEY

    def enroll(self, rig):
        rig.write_credential({"hub": self.url, "org": self.org, "machine": self.machine, "client_id": "cid-1",
                              "client_secret": "secret-1", "key": KEY})

    def browser(self, rig):
        return StandinBrowser(self.url, rig.project, self.machine)

    def requests(self, since, until):
        status, st = call(self.url, "GET", "/control/state")
        return [{"status": p.get("status"), "conn": p.get("conn")} for p in st.get("posted") or []]

    def close(self):
        pass


class Local:
    """The hub's own Worker on a local runtime behind its stand-in for Access
    (`pnpm --filter desk-hub local`), from the MAWS worktree named, with a
    state directory of its own and a free port; its stdout, read here line by
    line and stamped, is its request log."""

    name, org = "local", "local"

    def __init__(self, rig, maws):
        if not maws or not os.path.isdir(os.path.join(maws, "apps", "desk-hub")):
            sys.exit("bench_open: --hub local needs --maws <a MAWS worktree with apps/desk-hub>")
        port = free_pair()
        self.url = "http://127.0.0.1:%d" % port
        self.machine = "bench-" + uuidlib.uuid4().hex[:6]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))}
        self.proc = subprocess.Popen(["pnpm", "--filter", "desk-hub", "local", "--state",
                                      os.path.join(rig.root, "hubstate"), "--port", str(port)],
                                     cwd=maws, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self.log, self.lock = [], threading.Lock()
        self.ready = threading.Event()
        threading.Thread(target=self.read, daemon=True).start()
        if not self.ready.wait(180):
            tail = "\n".join(l for _, l in self.log[-15:])
            self.close()
            sys.exit("bench_open: the local hub did not come up in 180 s:\n" + tail)
        self.key = None

    def read(self):
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\n")
            with self.lock:
                self.log.append((time.time(), line))
            if "Ready on http" in line:
                self.ready.set()

    def code(self, machine, key=None):
        status, body = call(self.url, "POST", "/standin/enrollment-code",
                            {"machine": machine, **({"key": key} if key else {})})
        if status != 200:
            raise RuntimeError("no enrollment code: %s %s" % (status, body))
        return body

    def enroll(self, rig):
        body = self.code(self.machine)
        self.key = body["key"]
        r = subprocess.run([SMINOS, "hub", "enroll", "--name", self.machine], input=body["code"].encode(),
                           env=rig.env, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("sminos hub enroll failed: %s" % (r.stdout + r.stderr).decode()[-500:])

    def mint(self, machine):
        """Another machine of the org, its credential redeemed here."""
        body = self.code(machine, self.key)
        status, cred = call(self.url, "POST", "/machine/enroll", {"token": body["token"], "machine": machine})
        if status != 200:
            raise RuntimeError("the redemption failed: %s %s" % (status, cred))
        return cred

    def browser(self, rig):
        return LocalBrowser(self.url, rig.project, self.machine)

    def requests(self, since, until):
        """The request log's machine POSTs between the stamps: {status, ms}."""
        pat = re.compile(r"POST /machine/frames (\d+) .*\((\d+)ms\)")
        with self.lock:
            lines = [(at, l) for at, l in self.log if since <= at <= until]
        out = []
        for at, l in lines:
            m = pat.search(l)
            if m:
                out.append({"at": at, "status": int(m[1]), "ms": int(m[2])})
        return out

    def close(self):
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(20)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


# ------------------------------------------------------------- the transcript shapes


def synthetic_transcript(path, rows, cwd, sid, seed=7):
    """A transcript of `rows` rows shaped like a working session's: turns of
    a prompt, a tool call, its result (most of the bytes, its output twice
    as the engine keeps it), and an answer, each row with the engine's
    metadata and a line of its bookkeeping beside it (no uuid: the plane
    passes such lines over unparsed), on one parent chain: about 11 KB a row,
    as the build measurement of the spec's Surprises & Discoveries shaped one
    (15,000 rows, 163 MB). The uuids repeat from `seed`."""
    rnd = random.Random(seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    filler = "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz      \n") for _ in range(26000))
    parent = None
    with open(path, "w") as f:
        for i in range(rows):
            uid = str(uuidlib.UUID(int=rnd.getrandbits(128), version=4))
            stamp = "2026-10-20T%02d:%02d:%02d.000Z" % (i // 3600 % 24, i // 60 % 60, i % 60)
            base = {"parentUuid": parent, "isSidechain": False, "userType": "external", "cwd": cwd,
                    "sessionId": sid, "version": "2.1.304", "gitBranch": "main", "slug": "bench-session",
                    "uuid": uid, "timestamp": stamp}
            usage = {"input_tokens": 3 + i % 7, "cache_creation_input_tokens": 120 + i % 50,
                     "cache_read_input_tokens": 40000 + i, "output_tokens": 30 + i % 90, "service_tier": "standard",
                     "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 120 + i % 50}}
            phase = i % 4
            if phase == 0:
                row = {**base, "type": "user", "message": {"role": "user", "content": "step %d: carry on" % i}}
            elif phase == 1:
                row = {**base, "type": "assistant", "requestId": "req_%024d" % i, "message": {
                    "id": "msg_%024d" % i, "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                    "content": [{"type": "tool_use", "id": "toolu_%020d" % i, "name": "Bash",
                                 "input": {"command": "grep -rn pattern%d src/" % i, "description": "Search"}}],
                    "stop_reason": "tool_use", "stop_sequence": None, "usage": usage}}
            elif phase == 2:
                out = filler[i % 500:][:12000]
                row = {**base, "type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_%020d" % (i - 1), "content": out,
                     "is_error": False}]},
                    "toolUseResult": {"stdout": out, "stderr": "", "interrupted": False, "isImage": False}}
            else:
                row = {**base, "type": "assistant", "requestId": "req_%024d" % i, "message": {
                    "id": "msg_%024d" % i, "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                    "content": [{"type": "text", "text": filler[:2000]}], "stop_reason": "end_turn",
                    "stop_sequence": None, "usage": usage}}
            f.write(json.dumps(row) + "\n")
            f.write(json.dumps({"type": "api-request", "sessionId": sid, "timestamp": stamp,
                                "detail": filler[:4000]}) + "\n")
            parent = uid


# ------------------------------------------------------------- the sessions


class FakeKind:
    """fake_session.py's scripted session in the project (`bridged`), or a
    synthetic transcript with no bridge: a `sleep` stands for its process,
    under an engine record in the project's checkout."""

    def __init__(self, rig, synthetic_rows=None):
        import fake_session
        self.rig = rig
        self.sid = str(uuidlib.uuid4())
        self.fake = fake_session.FakeSession(rig.home, rig.smh, self.sid)
        self.stamps = []
        lose = self.fake.lose

        def stamped(events):
            self.stamps += [time.time()] * len(events)
            lose(events)

        self.fake.lose = stamped
        self.holder = rig.spawn(["sleep", "86399"])
        self.record({"status": "idle"})
        self.name = "synthetic" if synthetic_rows else "fake"
        if synthetic_rows:
            synthetic_transcript(self.fake.path(None), synthetic_rows, rig.work, self.sid)
            self.bridged = False
        else:
            self.fake.user_row("hello")
            m = self.fake.message()
            m.text(0, "Hello there.")
            m.row(0)
            m.end()
            self.bridged = True

    def record(self, fields):
        path = os.path.join(self.rig.home, ".claude", "sessions", "%d.json" % self.holder.pid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rec = {"pid": self.holder.pid, "sessionId": self.sid, "cwd": self.rig.work, "kind": "interactive",
               "name": "bench", "nameSource": "derived", **fields}
        with open(path + ".tmp", "w") as f:
            json.dump(rec, f)
        os.replace(path + ".tmp", path)

    def start(self):
        if self.bridged:
            self.fake.start_bridge()

    def transcript(self):
        return self.fake.path(None)

    def dx5(self):
        return list(zip(self.stamps, self.fake.emitted))

    def close(self):
        self.fake.stop_bridge()


class LiveKind:
    """An isolated headless session (mods/live-bridge-check.py's Live,
    started headless), a probe subscription on its bridge from the start:
    the probe's events are the DX5 source the inventory reads."""

    name = "live"
    bridged = True

    def __init__(self, rig, a):
        self.rig, self.live = rig, rig.live
        self.thinking, self.model = a.thinking, a.model

    def start(self):
        live = self.live
        live.start_session(headless=True, thinking=self.thinking, model=self.model)
        sock_dir = os.path.join(live.smh, "bridge")
        found = wait_for("the session's bridge socket", 120, lambda: [
            n[:-5] for n in os.listdir(sock_dir) if n.endswith(".sock") and not n.startswith(".")]
            if os.path.isdir(sock_dir) else None, 0.1)
        self.sid = live.session = found[0]
        wait_for("the bridge to answer", 30, live.status, 0.1)
        threading.Thread(target=live.subscribe_forever, daemon=True).start()
        wait_for("the probe's subscription", 15, lambda: live.subscriptions > 0)

    def prompt(self, text):
        t0 = time.time()
        self.live.send(text)
        return t0

    def turn_done(self, since):
        return bool(self.live.turns_done(since))

    def events(self, since=0.0):
        with self.live.lock:
            return [(t, e) for t, e in self.live.events if t >= since]

    def transcript(self):
        found = glob.glob(os.path.join(self.live.cfg, "projects", "*", self.sid + ".jsonl"))
        return found[0] if found else os.path.join(self.live.cfg, "projects", "none", self.sid + ".jsonl")

    def dx5(self):
        return self.events()

    def close(self):
        pass


# ------------------------------------------------------------- the rig


class Rig:
    """One run's machine: a temporary HOME and SMINOS_HOME (a live
    session's own, under --live), the hub, the project, the uplink."""

    def __init__(self, a):
        self.a, self.procs, self.live = a, [], None
        if a.live:
            lbc = _load_live_check()
            missing = [k for k in lbc.GATEWAY_KEYS if k not in os.environ]
            if missing:
                sys.exit("bench_open --live: the gateway keys are not in the environment: %s" % ", ".join(missing))
            self.live = lbc.Live(a.keep)
            self.live.setup()
            self.root, self.home, self.smh, self.work = self.live.root, self.live.home, self.live.smh, self.live.work
        else:
            self.root = tempfile.mkdtemp(prefix="bo.", dir="/tmp")
            self.home, self.smh = os.path.join(self.root, "home"), os.path.join(self.root, "s")
            self.work = os.path.join(self.root, "work")
            os.makedirs(os.path.join(self.home, ".claude", "sessions"))
            os.makedirs(self.smh, mode=0o700)
        stub = os.path.join(self.root, "bin")
        os.makedirs(stub, exist_ok=True)
        with open(os.path.join(stub, "claude"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
        os.chmod(os.path.join(stub, "claude"), 0o755)
        self.env = {k: os.environ[k] for k in BASE_KEYS if k in os.environ}
        self.env.update(HOME=self.home, SMINOS_HOME=self.smh, CLAUDE_CONFIG_DIR=os.path.join(self.home, ".claude"),
                        PATH=stub + os.pathsep + os.environ.get("PATH", ""), SMINOS_DERIVE_EVERY="0",
                        PYTHONDONTWRITEBYTECODE="1")
        self.tee = os.path.join(self.root, "tee.jsonl")
        self.uplink = None
        self.hub = Local(self, a.maws) if a.hub == "local" else Standin(self)
        self.hub.enroll(self)
        if not a.live:
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
            subprocess.run(git + ["init", "-q", self.work], check=True)
            self.sminos("project", "init", "--name", "benchproj")
        smns = os.path.join(self.work, ".smns")
        with open(smns) as f:
            d = json.load(f)
        d["hub"] = {"url": self.hub.url, "org": self.hub.org}
        with open(smns, "w") as f:
            json.dump(d, f, indent=2)
        self.project = d["project"]
        self.browser = None

    def spawn(self, argv, log=None, env=None):
        out = open(os.path.join(self.root, log), "ab") if log else subprocess.DEVNULL
        p = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT if log else subprocess.DEVNULL,
                             env=env if env is not None else None)
        self.procs.append(p)
        return p

    def sminos(self, *args):
        return subprocess.run([SMINOS, *args], cwd=self.work, env=self.env, capture_output=True, check=True)

    def write_credential(self, cred):
        path = os.path.join(self.smh, "daemon", "hub.json")
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cred, f)
        os.replace(path + ".tmp", path)

    def point_uplink_at(self, url):
        """The credential's hub (the pause proxy's URL, for `held`)."""
        path = os.path.join(self.smh, "daemon", "hub.json")
        with open(path) as f:
            cred = json.load(f)
        cred["hub"] = url
        self.write_credential(cred)

    def daemon_log(self):
        return os.path.join(self.smh, "daemon.log")

    def start_uplink(self):
        self.uplink = self.spawn([sys.executable, os.path.realpath(__file__), "_uplink", SCRIPTS, self.tee],
                                 log="uplink.out", env=self.env)
        return time.time()

    def stop_uplink(self):
        if self.uplink is None:
            return
        self.uplink.send_signal(signal.SIGTERM)
        try:
            self.uplink.wait(30)
        except subprocess.TimeoutExpired:
            self.uplink.kill()
            self.uplink.wait()
        self.uplink = None

    def open_line(self, sub, seconds=10):
        try:
            return wait_for("the open line of %s" % sub, seconds, lambda: open_lines(self.daemon_log()).get(sub), 0.05)
        except TimeoutError:
            return None

    def close(self):
        if self.browser is not None:
            self.browser.close()
        self.stop_uplink()
        for p in reversed(self.procs):
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        self.hub.close()
        if self.live is not None:
            self.live.cleanup()
        elif not self.a.keep:
            shutil.rmtree(self.root, ignore_errors=True)
        else:
            print("kept: %s" % self.root, file=sys.stderr)


def _load_live_check():
    spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "mods",
                                                                                  "live-bridge-check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------- an open


class Open:
    def __init__(self, sub, sent, consumer):
        self.sub, self.sent, self.consumer = sub, sent, consumer
        self.snap_at = None
        self.end_at = None
        self.taken = 0
        self.chunks = []      # (arrival, the bridge's stamp `t`, ms) of each chunk message


class Bench:
    """The opens of one run, and what each prints."""

    def __init__(self, rig, kind, a):
        self.rig, self.kind, self.a = rig, kind, a
        self.records = []
        self.mode = "uplink"

    # ---- the uplink, connected

    def connected(self, since):
        """Once the hub relayed a presence of the session said after `since`."""
        b = self.rig.browser

        def said():
            b.poll()
            return any(at >= since and m.get("kind") == "presence" and m.get("session") == self.kind.sid
                       for at, m in b.msgs)
        wait_for("the session's presence through the hub", 60, said, 0.1)

    def start(self):
        rig = self.rig
        rig.sminos("daemon", "tick")   # the project's .smns read, a scripted session's record joined
        t = rig.start_uplink()
        rig.browser = rig.hub.browser(rig)
        self.kind.start()
        self.connected(t - 1)

    def restart(self):
        self.rig.stop_uplink()
        t = self.rig.start_uplink()
        self.connected(t)
        return t

    # ---- one open

    def open(self, previous=None, agent=None):
        sub, sent = self.rig.browser.subscribe(self.kind.sid, agent)
        return Open(sub, sent, dx4_consumer.Consumer(agent, previous))

    def feed(self, o):
        b = self.rig.browser
        b.poll()
        mine = [(at, m) for at, m in b.msgs if m.get("sub") == o.sub]
        for at, m in mine[o.taken:]:
            o.consumer.take(m)
            if m.get("kind") == "snapshot" and o.snap_at is None:
                o.snap_at = at
            elif m.get("kind") == "end" and o.end_at is None:
                o.end_at = at
            elif m.get("kind") == "chunk":
                t = (m.get("body") or {}).get("t")
                o.chunks.append((at, t))
        o.taken = len(mine)

    def until(self, o, pred, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.feed(o)
            if pred():
                return True
            time.sleep(0.02)
        self.feed(o)
        return pred()

    def opened(self, o, seconds=30):
        self.until(o, lambda: o.snap_at is not None or o.end_at is not None, seconds)
        return o

    def close(self, o):
        if o.end_at is None:
            self.rig.browser.unsubscribe(o.sub)

    def record(self, scenario, o, counted=True, **extra):
        """The open's line: E, the open line's figures, the consumer's and the inventory's findings."""
        line = self.rig.open_line(o.sub) or {}
        backbone = self.kind.dx5()
        tees = [t for t in read_tees(self.rig.tee)]
        events, how = place_snapshots(backbone, tees)
        check = dx4_consumer.Inventory.from_sources(self.kind.transcript(), events).check(o.consumer)
        kinds = o.consumer.error_kinds()
        rec = {"mode": self.mode, "hub": self.rig.hub.name, "session": self.kind.name, "scenario": scenario,
               "load1": load1(), "E": None if o.snap_at is None else round(o.snap_at - o.sent, 3),
               "N": line.get("N"), "arrived": line.get("arrived"), "taken": line.get("taken"),
               "build": line.get("build"), "cpu_ms": line.get("cpu_ms"), "rows": line.get("rows"),
               "cut": line.get("cut"), "waits": line.get("waits"),
               "holes": len(check["holes"]), "dups": len(check["dups"]), "gaps": kinds.count("gap"),
               "vanished": len(check["vanished"]), "undrawn": len(check["undrawn"]),
               "residual": len(check["residual"]), "partial": len(check["partial"]),
               "errors": sorted(set(kinds)), "outcome": line.get("outcome"),
               "ended": None if o.end_at is None else (o.consumer.end or {}).get("reason"),
               "placed": how.get(o.sub), "counted": counted, **extra}
        self.records.append(rec)
        print(json.dumps(rec), flush=True)
        return rec

    def summary(self, scenario):
        mine = [r for r in self.records if r["scenario"] == scenario and r.get("counted")]
        loads = [r["load1"] for r in mine]
        out = {"summary": scenario, "mode": self.mode, "hub": self.rig.hub.name, "session": self.kind.name,
               "opens": len(mine), "E": stats(r["E"] for r in mine), "N": stats(r["N"] for r in mine),
               "load1": {"min": min(loads, default=None), "max": max(loads, default=None)},
               "uptime": uptime()}
        extra = [r for r in self.records if r["scenario"] == scenario and not r.get("counted")]
        if extra:
            out["not_counted"] = len(extra)
        print(json.dumps(out), flush=True)
        return out


# ------------------------------------------------------------- the scenarios


def settle(bench):
    """A live session with one turn behind it, so it has rows and is idle."""
    k = bench.kind
    if k.name == "live":
        t0 = k.prompt(PROMPTS["settle"])
        wait_for("the settling turn", 180, lambda: k.turn_done(t0), 0.2)
        time.sleep(1.0)


def sc_idle(bench, a):
    settle(bench)
    o = bench.opened(bench.open())
    bench.until(o, lambda: False, 0.5)
    bench.record("idle", o, counted=False, note="the warm-up open: builds the index")
    bench.close(o)
    for _ in range(a.opens):
        time.sleep(0.5)
        o = bench.opened(bench.open())
        bench.until(o, lambda: False, 0.5)
        bench.record("idle", o)
        bench.close(o)


def last_row_held(bench, o):
    """Whether the consumer holds the transcript's last row on disk."""
    inv = dx4_consumer.Inventory.from_sources(bench.kind.transcript(), [])
    return bool(inv.rows) and inv.rows[-1]["uuid"] in o.consumer.held


def sc_after_prompt(bench, a):
    settle(bench)
    k = bench.kind
    for _ in range(a.opens):
        time.sleep(0.5)
        if k.name == "live":
            t0 = k.prompt(PROMPTS["after-prompt"])
            wait_for("the prompt row's notice", 60, lambda: any(
                e.get("type") == "row-seen" and not e.get("agentId") for _, e in k.events(t0)), 0.005)
            o = bench.opened(bench.open())
            bench.until(o, lambda: k.turn_done(t0), 120)
            bench.until(o, lambda: last_row_held(bench, o), 5)
        else:
            u = str(uuidlib.uuid4())
            k.fake.user_row("hi", disk=False, uuid=u)
            threading.Timer(0.1, lambda: k.fake.write_row(None, {
                "type": "user", "uuid": u, "agentId": None, "message": {"role": "user", "content": "hi"}})).start()
            o = bench.opened(bench.open())
            m = k.fake.message()
            m.text(0, "Hello again.")
            m.row(0)
            m.end()
            bench.until(o, lambda: last_row_held(bench, o), 5)
        bench.record("after-prompt", o)
        bench.close(o)


def fake_thinking_message(fake, think_s, answer_s, on_text, every=0.1):
    """A scripted model request with thinking: its thinking block streams
    and is named by its block-row (the row not on disk: the engine flushes
    a message's rows when it ends), then its text streams for `answer_s`
    (`on_text()` at the first text chunk), then the text's block-row, both
    rows on disk, the step's end. The chunks carry the wall clock's `t`."""
    m = fake.message()
    chunk = [0]

    def post(kind, index, text):
        m.post([{"type": "chunk", **m.ids(), "chunkIndex": chunk[0], "chunk": {"kind": kind, "index": index,
                                                                                "text": text},
                 "t": int(time.time() * 1000)}])
        m.up_to[index] = chunk[0]
        chunk[0] += 1
        m.next_chunk = chunk[0]

    thought = ""
    for i in range(max(1, int(think_s / every))):
        piece = "considering %d. " % i
        thought += piece
        post("thinking", 0, piece)
        time.sleep(every)
    a_uuid, b_uuid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
    m.settled.add(0)
    m.post([{"type": "block-row", "uuid": a_uuid, **m.ids(), "index": 0, "t": int(time.time() * 1000)}])
    said = ""
    n = max(1, int(answer_s / every))
    for i in range(n):
        piece = "word%d " % i
        said += piece
        post("text", 1, piece)
        if i == 0:
            on_text()
        time.sleep(every)
    m.settled.add(1)
    m.post([{"type": "block-row", "uuid": b_uuid, **m.ids(), "index": 1, "t": int(time.time() * 1000)}])
    for uid, content in ((a_uuid, {"type": "thinking", "thinking": thought}), (b_uuid, {"type": "text", "text": said})):
        fake.write_row(None, {"type": "assistant", "uuid": uid, "agentId": None,
                              "message": {"role": "assistant", "content": [content]}})
    m.end()
    return m


def thinking_trial(bench, scenario, opens_at, answer_s):
    """One message with thinking and the opens of a window scenario: the
    first at the first text chunk after the thinking block's block-row
    (`opens_at` None) or at those offsets from it, each later one a
    re-subscribe that resumes the one before. Returns (opens, the probe's
    view of the step, the step key) or None when the message had no
    thinking."""
    k = bench.kind
    trigger = threading.Event()
    t0 = time.time()
    if k.name == "live":
        k.prompt(PROMPTS[scenario])

        def text_after():
            for key, s in steps_seen(k.events(t0), t0).items():
                if s["text_after"] is not None:
                    return key, s
            return None

        def ended_without():
            return k.turn_done(t0) and text_after() is None

        wait_for("a text chunk after a thinking block's block-row, or the turn's end", 240,
                 lambda: text_after() or ended_without(), 0.005)
        found = text_after()
        if found is None:
            return None
        key, s = found
        named = s["thinking_named"]
    else:
        th = threading.Thread(target=fake_thinking_message, args=(k.fake, 0.5, answer_s, trigger.set), daemon=True)
        th.start()
        trigger.wait(30)
        found = [(key, s) for key, s in steps_seen(k.dx5(), t0).items() if s["thinking_named"] is not None]
        key, s = found[-1]
        named = s["thinking_named"]
    opens = []
    previous = None
    for offset in (opens_at or (None,)):
        if offset is not None:
            delay = named + offset - time.time()
            if delay > 0:
                time.sleep(delay)
        if opens:
            bench.close(opens[-1])
            previous = opens[-1].consumer
        o = bench.opened(bench.open(previous=previous))
        o.offset = offset
        opens.append(o)
    return opens, key


def step_view(bench, key, since):
    events = bench.kind.dx5()
    return steps_seen(events, since).get(key) or {}


def sc_window(bench, a, scenario):
    """mid-message and long-answer: opens counted only inside the thinking-to-end window."""
    settle(bench)
    k = bench.kind
    long_ = scenario == "long-answer"
    counted, trials = 0, 0
    while counted < a.opens and trials < max(a.opens * 3, a.opens + 2):
        trials += 1
        t0 = time.time()
        got = thinking_trial(bench, scenario, (1.0, 7.0) if long_ else None, 12.5 if long_ else 2.3)
        if got is None:
            if trials == 1:
                print(json.dumps({"stopped": scenario, "why": "the first message streamed no thinking block before "
                                  "its text: the model or the budget gave no thinking (try --model sonnet)"}),
                      flush=True)
                return
            continue
        opens, key = got
        last = opens[-1]

        def done():
            s = step_view(bench, key, t0)
            return s.get("end") is not None and (k.name != "live" or k.turn_done(t0))
        bench.until(last, done, 240)
        bench.until(last, lambda: last_row_held(bench, last), 6)
        for o in opens[:-1]:
            bench.feed(o)
        s = step_view(bench, key, t0)
        named, end = s.get("thinking_named"), s.get("end")
        window = None if named is None or end is None else round(end - named, 3)
        inside = all(in_window(named, end, o.sent) for o in opens)
        if long_:
            inside = inside and window is not None and window >= 7.0
        for o in opens:
            early = o.end_at is not None and end is not None and o.end_at < end
            bench.record(scenario, o, counted=inside, window=window, trial=trials,
                         at=None if named is None else round(o.sent - named, 3),
                         **({"offset": o.offset, "end_before_step_end": early,
                             "window_12s": window is not None and window >= 12.0} if long_ else {}))
        bench.close(last)
        if inside:
            counted += 1
        if k.name == "live":
            wait_for("the trial's turn end", 240, lambda: k.turn_done(t0), 0.2)
        time.sleep(1.0)
    print(json.dumps({"windows": scenario, "trials": trials, "counted": counted, "missed": trials - counted}),
          flush=True)


def sc_kill(bench, a):
    k = bench.kind
    if k.name != "live":
        sys.exit("bench_open: --scenario kill needs --live (the mod respawns the child)")
    settle(bench)
    for _ in range(a.opens):
        o = bench.opened(bench.open())
        t0 = k.prompt(PROMPTS["kill"])
        wait_for("the answer streaming", 120, lambda: sum(
            1 for _, e in k.events(t0) if e.get("type") == "chunk" and (e.get("chunk") or {}).get("kind") == "text")
            >= 20, 0.005)
        pid = k.live.status()["pid"]
        killed = time.time()
        os.kill(pid, signal.SIGKILL)
        successor, tries = None, 0
        current = o
        deadline = time.time() + 30
        while time.time() < deadline and successor is None:
            bench.until(current, lambda: current.end_at is not None, max(0.1, deadline - time.time()))
            if current.end_at is None:
                break
            tries += 1
            nxt = bench.opened(bench.open(previous=current.consumer))
            line = bench.rig.open_line(nxt.sub, 5) or {}
            if nxt.snap_at is not None and line.get("outcome") == "bridge snapshot":
                successor = nxt
            current = nxt
        if successor is None:
            print(json.dumps({"kill": "no bridged snapshot within 30 s of the kill", "tries": tries}), flush=True)
        else:
            bench.until(successor, lambda: k.turn_done(t0), 180)
            bench.record("kill", successor, E_kill=round(successor.snap_at - killed, 3), resubscribes=tries)
            bench.close(successor)
        wait_for("the turn's end", 180, lambda: k.turn_done(t0), 0.2)
        time.sleep(1.0)


def sc_restart(bench, a):
    for i in range(max(1, a.opens)):
        if i:
            bench.restart()
        time.sleep(0.5)
        o = bench.opened(bench.open(), 120)
        bench.until(o, lambda: False, 0.3)
        bench.record("restart", o, moment="first start" if i == 0 else "after restart %d" % i)
        bench.close(o)


class Uploader:
    """A second machine of the org at the local hub: its own stream (read
    and dropped), a hello for the project, then `events` uploads of its own
    writer, sealed with the org key, which the hub fans out down every other
    machine's stream that opened the project."""

    def __init__(self, hub, project):
        sys.path.insert(0, SCRIPTS)
        import sminos_codes
        self.codes = sminos_codes
        self.hub, self.project = hub, project
        self.machine = "bench-up-" + uuidlib.uuid4().hex[:6]
        self.cred = hub.mint(self.machine)
        self.headers = {"CF-Access-Client-Id": self.cred["client_id"],
                        "CF-Access-Client-Secret": self.cred["client_secret"]}
        u = urllib.parse.urlsplit(hub.url)
        self.stream = http.client.HTTPConnection(u.hostname, u.port, timeout=30)
        self.stream.request("GET", "/machine/stream", headers={**self.headers, "Accept": "text/event-stream"})
        r = self.stream.getresponse()
        if r.status != 200:
            raise RuntimeError("the uploader's stream was refused: %s" % r.status)
        self.generation = None
        while self.generation is None:
            line = r.fp.readline()
            if line.startswith(b"data: "):
                f = json.loads(line[6:])
                if f.get("t") == "welcome":
                    self.generation = f["generation"]
        self.r = r
        threading.Thread(target=self.drain, daemon=True).start()

    def drain(self):
        try:
            while self.r.fp.readline():
                pass
        except (OSError, ValueError, AttributeError):   # AttributeError: closed under it (fp gone)
            pass

    def post(self, frames):
        body = "".join(json.dumps(f) + "\n" for f in frames).encode()
        return call(self.hub.url, "POST", "/machine/frames", body,
                    {**self.headers, "X-Desk-Generation": str(self.generation), "Content-Type": "application/x-ndjson"},
                    timeout=60)

    def upload(self, size, per_event=64 << 10, per_post=8):
        """`size` bytes of events in POSTs of `per_post` events; each POST's (status, answer)."""
        status, body = self.post([{"t": "hello", "project": self.project, "name": "benchproj", "have": {}}])
        if status != 200:
            raise RuntimeError("the uploader's hello: %s %s" % (status, body))
        key = base64.urlsafe_b64decode(self.hub.key + "=" * (-len(self.hub.key) % 4))
        sid = str(uuidlib.uuid4())
        writer = "%s/%s" % (self.machine, sid)
        n = max(1, size // per_event)
        answers, seq = [], 0
        while seq < n:
            batch = []
            for _ in range(min(per_post, n - seq)):
                seq += 1
                draft = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), "writer": writer, "seq": seq,
                         "kind": "say", "session": sid, "to": [], "text": ("backlog %d " % seq).ljust(per_event, "x")}
                batch.append(self.codes.seal(key, "log", self.project, draft, self.codes.b64url(os.urandom(16))))
            answers.append(self.post([{"t": "events", "project": self.project, "events": batch}]))
        return answers

    def close(self):
        try:
            self.stream.close()
        except OSError:
            pass


def sc_held(bench, a):
    rig, k = bench.rig, bench.kind
    if rig.hub.name != "local" or k.name != "fake":
        sys.exit("bench_open: --scenario held runs on --hub local with the fake session")
    proxy = rig.proxy
    control = proxy["control"]
    o = bench.opened(bench.open())
    stop = threading.Event()
    m = k.fake.message()

    def stream():
        i = 0
        while not stop.is_set():
            m.post([{"type": "chunk", **m.ids(), "chunkIndex": i,
                     "chunk": {"kind": "text", "index": 0, "text": "c%d " % i}, "t": int(time.time() * 1000)}])
            m.texts[0] = m.texts.get(0, "") + "c%d " % i
            m.up_to[0] = i
            i += 1
            m.next_chunk = i
            time.sleep(0.1)

    th = threading.Thread(target=stream, daemon=True)
    th.start()
    bench.until(o, lambda: bool(o.chunks), 10)
    streams_before = call(control, "GET", "/control/state")[1]["streams"]
    status, armed = call(control, "POST", "/control/arm", {"on": "next-events", "seconds": a.pause_stream})
    if status != 200 or armed.get("state") != "armed":
        sys.exit("bench_open: the proxy did not arm: %s %s" % (status, armed))
    up = Uploader(rig.hub, rig.project)
    t_up = time.time()
    answers = up.upload(a.backlog)
    t_answered = time.time()
    try:
        st = wait_for("the proxy's pause", 30, lambda: (lambda s: s if s["state"] in ("paused", "resumed") else None)(
            call(control, "GET", "/control/state")[1]), 0.02)
    except TimeoutError:
        sys.exit("bench_open: the proxy never paused: the upload's answers %s, the proxy %s" % (
            [(s_, str(b_)[:200]) for s_, b_ in answers], call(control, "GET", "/control/state")[1]))
    paused_at = st["paused_at"]
    st = wait_for("the proxy's resume", a.pause_stream + 30, lambda: (lambda s: s if s["state"] == "resumed" else None)(
        call(control, "GET", "/control/state")[1]), 0.05)
    resumed_at = st["resumed_at"]
    bench.until(o, lambda: False, max(0.0, resumed_at + 1.0 - time.time()))
    o2 = bench.opened(bench.open())
    bench.until(o2, lambda: False, 1.0)
    stop.set()
    th.join(5)
    u = m.row(0)
    m.end()
    bench.until(o, lambda: u in o.consumer.held, 10)
    bench.feed(o2)
    lags = [round(at - t / 1000.0, 3) for at, t in o.chunks if isinstance(t, (int, float))
            and paused_at <= t / 1000.0 <= resumed_at]
    posts = rig.hub.requests(paused_at, resumed_at + 0.5)
    final = call(control, "GET", "/control/state")[1]
    bench.record("held", o, counted=False, role="the subscription streaming through the pause",
                 window=round(resumed_at - paused_at, 3), held_bytes=final.get("held"), backlog=a.backlog,
                 upload_answers=[s for s, _ in answers], upload_s=round(t_answered - t_up, 3),
                 chunk_lag_max=max(lags, default=None), chunks_in_window=len(lags),
                 posts_in_window=len(posts), posts_not_200=[p for p in posts if p["status"] != 200],
                 post_ms_max=max((p["ms"] for p in posts), default=None),
                 stream_survived=final.get("streams") == streams_before and o.end_at is None)
    bench.record("held", o2, role="the open 1 s after the resume", at=round(o2.sent - resumed_at, 3))
    bench.close(o)
    bench.close(o2)
    up.close()


# ------------------------------------------------------------- the micro-benchmark


def micro(a):
    """N_micro: one Subscription made as Plane.subscribe makes it, pumped as
    the uplink pumps it (a wake, else every POLL), its phases stamped."""
    os.environ["SMINOS_HOME"] = os.path.abspath(a.sminos_home)
    if a.home:
        os.environ["HOME"] = os.path.abspath(a.home)
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(os.environ["HOME"], ".claude")
    sys.path.insert(0, SCRIPTS)
    import sminos as S
    import sminos_bridge as B
    import sminos_plane as P
    marks = []
    T0 = [time.monotonic()]

    def mark(what, detail=None):
        marks.append((round(time.monotonic() - T0[0], 4), what, detail))

    def wrap(obj, name, label, detail=None):
        orig = getattr(obj, name)

        def f(*args, **kwargs):
            mark(label + ":start")
            r = orig(*args, **kwargs)
            mark(label + ":end", detail(r) if detail else None)
            return r
        setattr(obj, name, f)

    put = P.BridgeReader.put

    def put_(self, item):
        if item[0] != "line" or (isinstance(item[1], dict) and item[1].get("type") == "snapshot"):
            mark("reader:" + item[0], item[1].get("type") if isinstance(item[1], dict) else str(item[1])[:80])
        put(self, item)

    P.BridgeReader.put = put_
    wrap(P, "build", "build", lambda r: r[0])
    wrap(P, "look", "look")
    wrap(S, "transcript_now", "locate", lambda r: bool(r))
    said = []
    P.log = lambda line: (said.append(line), mark("log", line))
    transcripts, disk = P.Transcripts(), P.Disk()
    records = []
    for i in range(a.opens):
        marks.clear()
        said.clear()
        woken = threading.Event()
        T0[0] = time.monotonic()
        received = time.time()
        reader = None
        if os.path.exists(B.endpoint(a.session)):
            reader = P.BridgeReader(B.endpoint(a.session), woken.set)
            reader.start()
        sub = P.Subscription("micro", "micro", a.session, None, "micro-%d" % i, reader=reader,
                             locate=lambda: S.transcript_now(a.session),
                             presence=lambda: {"record": None, "bridge": reader is not None}, alive=lambda: True,
                             transcripts=transcripts, wake=woken.set, disk=disk, received=received)
        mark("subscription")
        snap = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and snap is None and not sub.ended:
            woken.wait(0.25)
            woken.clear()
            for msg in sub.pump():
                if msg["kind"] in ("snapshot", "end"):
                    snap = (round(time.monotonic() - T0[0], 4), msg["kind"])
                    mark(msg["kind"])
        sub.close()
        line = parse_open_line("plane: " + said[0]) if said else {}
        rec = {"mode": "micro", "scenario": "micro", "load1": load1(), "N_micro": snap[0] if snap else None,
               "outcome": snap[1] if snap else None, "build": (line or {}).get("build"),
               "cpu_ms": (line or {}).get("cpu_ms"), "rows": (line or {}).get("rows"),
               "cut": (line or {}).get("cut"), "waits": (line or {}).get("waits"),
               "phases": marks[:], "line": said[0] if said else None, "leaves_out": LEAVES_OUT}
        records.append(rec)
        print(json.dumps(rec), flush=True)
        time.sleep(0.2)
    loads = [r["load1"] for r in records]
    print(json.dumps({"summary": "micro", "mode": "micro", "opens": len(records),
                      "N_micro": stats(r["N_micro"] for r in records),
                      "load1": {"min": min(loads, default=None), "max": max(loads, default=None)},
                      "uptime": uptime(), "leaves_out": LEAVES_OUT}), flush=True)


# ------------------------------------------------------------- main


def run(a):
    print(json.dumps({"start": a.scenario, "hub": a.hub, "session": "live" if a.live else
                      ("synthetic" if a.synthetic_rows else "fake"), "uptime": uptime()}), flush=True)
    rig = Rig(a)
    kind = None
    try:
        kind = LiveKind(rig, a) if a.live else FakeKind(rig, a.synthetic_rows)
        if a.scenario == "held":
            ports_file = os.path.join(rig.root, "proxy.json")
            rig.spawn([sys.executable, os.path.join(HERE, "pause_proxy.py"), rig.hub.url, ports_file],
                      log="proxy.out")
            ports = json.loads(wait_for("the pause proxy", 10, lambda: _read(ports_file)))
            rig.proxy = {"proxy": "http://127.0.0.1:%d" % ports["proxy"],
                         "control": "http://127.0.0.1:%d" % ports["control"]}
            rig.point_uplink_at(rig.proxy["proxy"])
        bench = Bench(rig, kind, a)
        bench.start()
        {"idle": sc_idle, "after-prompt": sc_after_prompt, "kill": sc_kill, "restart": sc_restart, "held": sc_held,
         "mid-message": lambda b, x: sc_window(b, x, "mid-message"),
         "long-answer": lambda b, x: sc_window(b, x, "long-answer")}[a.scenario](bench, a)
        bench.summary(a.scenario)
    finally:
        if kind is not None:
            kind.close()
        rig.close()


def main():
    if sys.argv[1:2] == ["_uplink"]:
        return uplink_main(sys.argv[2], sys.argv[3])
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--uplink", action="store_true", help="the full path: the real uplink and a hub")
    mode.add_argument("--micro", action="store_true", help="one Subscription in-process: N_micro")
    p.add_argument("--hub", choices=("local", "standin"), default="standin")
    p.add_argument("--maws", help="the MAWS worktree whose apps/desk-hub runs as the local hub")
    p.add_argument("--live", action="store_true", help="an isolated headless session (spends haiku calls)")
    p.add_argument("--thinking", action="store_true", help="with --live: extended thinking on")
    p.add_argument("--model", default="haiku", help="with --live: the session's model")
    p.add_argument("--synthetic-rows", type=int, metavar="N", help="a synthetic transcript of N rows, no bridge")
    p.add_argument("--scenario", choices=SCENARIOS, default="idle")
    p.add_argument("--opens", type=int, default=5)
    p.add_argument("--pause-stream", type=float, default=4.0, metavar="S")
    p.add_argument("--backlog", type=size_arg, default=4 << 20, metavar="B")
    p.add_argument("--keep", action="store_true", help="leave the run's temporary directory")
    p.add_argument("--session", help="--micro: the session id")
    p.add_argument("--sminos-home", help="--micro: the SMINOS_HOME its bridge and the plane read")
    p.add_argument("--home", help="--micro: the HOME whose .claude holds its transcript")
    a = p.parse_args()
    if a.micro:
        if not (a.session and a.sminos_home):
            p.error("--micro needs --session and --sminos-home")
        return micro(a)
    if a.live and a.synthetic_rows:
        p.error("--live and --synthetic-rows are two different sessions")
    if a.thinking and not a.live:
        p.error("--thinking is a live session's")
    run(a)


if __name__ == "__main__":
    main()
