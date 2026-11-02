#!/usr/bin/env python3
"""The bridge child's gate client (O12 M4a, the child's side): a MAWS lane B
session's observer on the engine host's holder socket (OX10), and its
private relay to the bridge mod (sminos_holder.py's docstring is the
contract).

Each case runs a real `sminos bridge` child against a fake engine host on a
real Unix socket and plays the mod itself: it reads the child's stdout and
posts to its POST /holder route. Timings are scaled (heartbeat 0.2 s,
backoff 0.3 s); production's are 5 s each. The replay plays the child's side
of O16's gate fixture (p5-o16-gate.jsonl, MAWS's copied byte for byte, its
source in p5-o16-gate.source.json): what the child alone can be judged on —
its hello, welcome, heartbeats, reconnects, the relay of every host frame,
and an `armed` only for an arm the mod acknowledged, in arm order. What only
the fix-wave host can show is printed as PENDING (decisions P3), never
skipped silently. The mod's fence is bridge.test.ts's.

Hermetic: every case has its own HOME, SMINOS_HOME and CLAUDE_CONFIG_DIR
under one temporary directory; nothing listens beyond Unix sockets there.
Run: python3 -B sminos/tests/test_holder.py
"""

import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
SMINOS = str(SCRIPTS / "sminos")
FIXTURE = HERE / "p5-o16-gate.jsonl"
BASE = tempfile.mkdtemp(prefix="smh.", dir="/tmp")   # short: a Unix socket's path is bounded
for var in ("CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "MAWS_LANE", "SMNS_MEMBER", "MAWS_HOLDER_SOCKET",
            "MAWS_LAUNCHED_BY", "SMINOS_LAUNCH", "RUNNER_TRACKING_ID"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"),
                  CLAUDE_CONFIG_DIR=os.path.join(BASE, "cc"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))

import sminos  # noqa: E402
import sminos_bridge  # noqa: E402
import sminos_holder  # noqa: E402

SESSION = "5f0c2a1e-6b7d-4c3e-9a8f-0123456789ab"   # the fixture's
HEARTBEAT, BACKOFF = 0.2, 0.3
LIVENESS = 15            # s: how long a wait for something that must happen may take on a loaded machine
QUIET = 0.6              # s: how long nothing must happen, for "nothing happens"
PENDING = []


def wait_for(pred, timeout=LIVENESS, step=0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("holder", timeout=10)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def _quiet(fn, *args):
    try:
        return fn(*args)
    except OSError:
        return None


def _kill(pid):
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass


def post(path, url, body, headers=None):
    c = _UnixHTTP(path)
    try:
        c.request("POST", url, body=json.dumps(body).encode(), headers={"content-type": "application/json",
                                                                         **(headers or {})})
        r = c.getresponse()
        text = r.read().decode()
        return r.status, json.loads(text) if text else None
    finally:
        c.close()


# ------------------------------------------------------------------ the fake engine host


class HostConn:
    """One observer connection as the host sees it: every frame it read, with
    when it read it."""

    def __init__(self, sock):
        self.sock = sock
        self.frames = []          # [(monotonic, frame)]
        self.cond = threading.Condition()
        self.closed = False
        self.closed_at = None
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b""
        while True:
            try:
                chunk = self.sock.recv(65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                with self.cond:
                    self.frames.append((time.monotonic(), json.loads(line)))
                    self.cond.notify_all()
        with self.cond:
            self.closed = True
            self.cond.notify_all()

    def send(self, frame):
        self.sock.sendall((json.dumps(frame) + "\n").encode())

    def close(self):
        self.closed_at = time.monotonic()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def seen(self, t=None, skip_hb=False):
        with self.cond:
            return [f for _, f in self.frames if (t is None or f.get("t") == t) and not (skip_hb and f.get("t") == "hb")]

    def times(self, t):
        with self.cond:
            return [at for at, f in self.frames if f.get("t") == t]

    def wait_frames(self, n, skip_hb=True):
        """The connection's first n frames (heartbeats left out), once it has them."""
        got = wait_for(lambda: len(self.seen(skip_hb=skip_hb)) >= n)
        assert got, "the host saw %r, waiting for %d frames" % (self.seen(), n)
        return self.seen(skip_hb=skip_hb)[:n]


class FakeHost:
    """The engine host's gate socket: every observer connection kept, in order."""

    def __init__(self, path):
        self.path = path
        self.conns = []
        self.cond = threading.Condition()
        self._listen()

    def _listen(self):
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.path)
        self.listener.listen(16)
        threading.Thread(target=self._accept, args=(self.listener,), daemon=True).start()

    def _accept(self, listener):
        while True:
            try:
                s, _ = listener.accept()
            except OSError:
                return
            with self.cond:
                self.conns.append(HostConn(s))
                self.cond.notify_all()

    def conn(self, i):
        got = wait_for(lambda: len(self.conns) > i)
        assert got, "no connection %d reached the host (it has %d)" % (i, len(self.conns))
        return self.conns[i]

    def replace(self):
        """The engine host is replaced: its gate closes, and a new one listens
        at the same path. When the old one closed."""
        self.listener.close()
        for c in list(self.conns):
            c.close()
        closed = time.monotonic()
        self._listen()
        return closed

    def stop(self):
        self.listener.close()
        for c in list(self.conns):
            c.close()


# ------------------------------------------------------------------ the child, and the mod the test plays


class Child:
    """A `sminos bridge` child, its stdout read as the mod reads it."""

    def __init__(self, home, gate, args=("--lane", "match"), marked=True, env=None, read_stdout=True):
        e = dict(os.environ)
        e.update(HOME=os.path.join(home, "home"), SMINOS_HOME=os.path.join(home, "s"),
                 CLAUDE_CONFIG_DIR=os.path.join(home, "cc"), SMINOS_HOLDER_HEARTBEAT=str(HEARTBEAT),
                 SMINOS_HOLDER_BACKOFF=str(BACKOFF), SMINOS_HOLDER_WELCOME_WAIT="1.5")
        if marked:
            e["MAWS_LANE"] = "B"
        if gate is not None:
            e["MAWS_HOLDER_SOCKET"] = gate
        e.update(env or {})
        self.home = home
        self.stderr = open(os.path.join(home, "child.err"), "w")
        self.proc = subprocess.Popen([SMINOS, "bridge", "--session", SESSION, *args], stdout=subprocess.PIPE,
                                     stderr=self.stderr, env=e)
        self.lines = []
        self.cond = threading.Condition()
        self.boot = None
        if read_stdout:
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for raw in self.proc.stdout:
            with self.cond:
                self.lines.append(json.loads(raw))
                self.cond.notify_all()

    def first_line(self):
        """The first stdout line, read directly (a child whose stdout the test does not drain)."""
        return json.loads(self.proc.stdout.readline())

    def wait_line(self, pred, timeout=LIVENESS):
        got = wait_for(lambda: next((ln for ln in list(self.lines) if pred(ln)), None), timeout)
        return got

    def holder_lines(self):
        return [ln for ln in list(self.lines) if ln.get("op") == "holder" and "bootstrap" not in ln]

    def bootstrap(self):
        if self.boot is None:
            line = self.wait_line(lambda ln: ln.get("op") == "holder" and "bootstrap" in ln)
            assert line is not None, "no bootstrap line; stdout: %r" % self.lines
            self.boot = line["bootstrap"]
        return self.boot

    def relay(self, epoch, frame, after=0):
        """The relay line of a host frame on `epoch` (the n-th such past `after` lines)."""
        return self.wait_line(lambda ln: ln.get("op") == "holder" and ln.get("epoch") == epoch
                              and ln.get("frame") == frame and self.lines.index(ln) >= after)

    def welcomes(self):
        return [ln for ln in self.holder_lines() if (ln.get("frame") or {}).get("t") == "welcome"]

    def welcome_epoch(self, n=1):
        """The epoch the n-th relayed welcome names."""
        assert wait_for(lambda: len(self.welcomes()) >= n), "no welcome %d relayed; stdout: %r" % (n, self.lines)
        return self.welcomes()[n - 1]["epoch"]

    def next_relay(self, before):
        """The first relay line past the `before` already seen."""
        assert wait_for(lambda: len(self.holder_lines()) > before), "nothing relayed; stdout: %r" % self.lines
        return self.holder_lines()[before]

    def post(self, body, nonce=None):
        boot = self.bootstrap()
        return post(boot["socket"], "/holder", body, {sminos_holder.NONCE_HEADER: boot["nonce"] if nonce is None else nonce})

    def ready(self):
        return self.post({"kind": "ready", "generation": self.bootstrap()["generation"]})

    def ack(self, epoch, arm, fence):
        return self.post({"kind": "armed", "generation": self.bootstrap()["generation"], "epoch": epoch, "arm": arm,
                          "fence": fence})

    def turn(self, epoch, fence, origin, delivery=None):
        body = {"kind": "turn", "generation": self.bootstrap()["generation"], "epoch": epoch, "fence": fence,
                "origin": origin}
        if delivery is not None:
            body["delivery"] = delivery
        return self.post(body)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc.stdout.close()
        self.stderr.close()


class Case(unittest.TestCase):
    """A fresh home, a fake host at its gate path, and the children it starts."""

    def setUp(self):
        self.home = tempfile.mkdtemp(dir=BASE)
        self.gate = os.path.join(self.home, "gate.sock")
        self.host = FakeHost(self.gate)
        self.children = []

    def tearDown(self):
        for c in self.children:
            c.stop()
        self.host.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def child(self, **kw):
        c = Child(self.home, kw.pop("gate", self.gate), **kw)
        self.children.append(c)
        return c

    def welcomed(self, child, i=0):
        """The child's i-th connection, said hello on and welcomed: (host side, epoch)."""
        conn = self.host.conn(i)
        self.assertEqual(conn.wait_frames(1)[0]["t"], "hello")
        n = len(child.welcomes())
        conn.send({"t": "welcome", "protocol": 1})
        return conn, child.welcome_epoch(n + 1)

    def assertQuiet(self, conn, t, seconds=QUIET):
        time.sleep(seconds)
        self.assertEqual(conn.seen(t), [], "the host saw %r" % conn.seen())


# ------------------------------------------------------------------ the connection


class Connection(Case):
    def test_hello_names_claude_and_the_child_then_welcome_then_heartbeats(self):
        child = self.child()
        boot = child.bootstrap()
        self.assertEqual(child.lines[0].get("op"), "holder", "the bootstrap is the child's first line")
        self.assertEqual(boot["pid"], os.getpid(), "pid is claude's: the child's parent")
        self.assertEqual(boot["childPid"], child.proc.pid)
        self.assertTrue(os.path.exists(boot["socket"]) and boot["nonce"] and boot["generation"])
        time.sleep(QUIET)
        self.assertEqual(self.host.conns, [], "no connection before the mod says it is ready")
        status, answer = child.ready()
        self.assertEqual((status, answer["ok"], answer["lane"]), (200, True, "match"))
        conn = self.host.conn(0)
        hello = conn.wait_frames(1)[0]
        self.assertEqual(hello, {"t": "hello", "protocol": 1, "session": SESSION, "pid": os.getpid(),
                                 "childPid": child.proc.pid})
        time.sleep(QUIET)
        self.assertEqual(conn.seen(), [hello], "nothing before the welcome, a heartbeat included")
        welcomed_at = time.monotonic()
        conn.send({"t": "welcome", "protocol": 1})
        epoch = child.welcome_epoch()
        self.assertTrue(epoch.startswith(boot["generation"] + "."), epoch)
        self.assertTrue(wait_for(lambda: len(conn.times("hb")) >= 5))
        beats = conn.times("hb")
        self.assertLess(beats[0] - welcomed_at, 1.0, "a heartbeat at once after the welcome")
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        self.assertTrue(all(HEARTBEAT * 0.5 < g < HEARTBEAT * 5 for g in gaps), gaps)
        self.assertEqual(conn.seen("hello"), [hello], "hello is once per connection: none periodic")
        _, st = sminos_bridge.request(os.path.join(self.home, "s", "bridge", SESSION + ".sock"), "GET", "/status")
        self.assertEqual(st["holder"], {"ready": True, "epoch": epoch, "attempts": 1})

    def test_a_close_without_welcome_backs_off_then_says_hello_afresh(self):
        child = self.child()
        child.ready()
        first = self.host.conn(0)
        first.wait_frames(1)
        first.close()   # the no-row case: the gate closes, writing nothing
        second = self.host.conn(1)
        self.assertEqual(second.wait_frames(1)[0]["t"], "hello")
        self.assertEqual(first.seen(), [first.seen()[0]], "hello alone on a connection never welcomed")
        self.assertGreaterEqual(second.frames[0][0] - first.closed_at, BACKOFF * 0.9, "the backoff")
        self.assertEqual(second.seen()[0]["childPid"], child.proc.pid)

    def test_no_welcome_in_time_ends_the_attempt(self):
        child = self.child()
        child.ready()
        first = self.host.conn(0)
        first.wait_frames(1)   # and the host says nothing
        self.assertTrue(wait_for(lambda: first.closed))
        self.assertGreaterEqual(time.monotonic() - first.frames[0][0], 1.4, "the welcome's wait (1.5 s here)")
        self.assertEqual(self.host.conn(1).wait_frames(1)[0]["t"], "hello")

    def test_a_host_line_past_the_bound_ends_the_connection(self):
        # Its newline arrives in the chunk that crosses LINE_MAX: the
        # completed line is measured too, never relayed.
        child = self.child()
        child.ready()
        conn, epoch = self.welcomed(child)
        line = json.dumps({"t": "disarm", "fence": 1, "pad": "x" * 66560}).encode() + b"\n"
        self.assertGreater(len(line), sminos_holder.LINE_MAX + 1000)
        conn.sock.sendall(line)
        self.assertTrue(wait_for(lambda: conn.closed), "the connection ends")
        self.assertEqual(self.host.conn(1).wait_frames(1)[0]["t"], "hello")
        self.assertEqual([ln for ln in child.holder_lines() if (ln.get("frame") or {}).get("t") == "disarm"], [])

    def test_an_invalid_welcome_is_no_welcome(self):
        child = self.child()
        child.ready()
        first = self.host.conn(0)
        first.wait_frames(1)
        first.send({"t": "welcome", "protocol": 2})
        self.assertEqual(self.host.conn(1).wait_frames(1)[0]["t"], "hello")
        self.assertEqual([f["t"] for f in first.seen()], ["hello"], "no heartbeat on a connection not welcomed")
        self.assertEqual(child.holder_lines(), [], "nothing relayed of it")

    def test_a_replaced_socket_gets_a_fresh_hello_after_the_backoff(self):
        child = self.child()
        child.ready()
        old, epoch1 = self.welcomed(child)
        self.assertTrue(wait_for(lambda: old.times("hb")))
        closed = self.host.replace()
        new = self.host.conn(1)
        hello = new.wait_frames(1)[0]
        self.assertEqual(hello, {"t": "hello", "protocol": 1, "session": SESSION, "pid": os.getpid(),
                                 "childPid": child.proc.pid})
        self.assertGreaterEqual(new.frames[0][0] - closed, BACKOFF * 0.9)
        new.send({"t": "welcome", "protocol": 1})
        epoch2 = child.welcome_epoch(2)
        self.assertNotEqual(epoch1, epoch2)
        self.assertTrue(wait_for(lambda: len(new.times("hb")) >= 2))
        self.assertEqual(len(old.seen("hello")), 1)

    def test_a_silent_host_gets_heartbeats_and_no_second_hello(self):
        # R5: on the fixed gate a later hb heals a silent row on the same
        # connection; the observer never says hello on a gap.
        child = self.child()
        child.ready()
        conn, _ = self.welcomed(child)
        time.sleep(HEARTBEAT * 8)
        self.assertEqual(len(conn.seen("hello")), 1)
        self.assertGreaterEqual(len(conn.seen("hb")), 4)
        self.assertEqual(len(self.host.conns), 1)


# ------------------------------------------------------------------ the verdict


class Verdict(Case):
    def ordinary_hello(self, child):
        line = child.wait_line(lambda ln: ln.get("op") == "hello")
        self.assertIsNotNone(line, "the ordinary hello; stdout: %r" % child.lines)
        return line

    def test_a_module_holding_mismatch_starts_no_gate(self):
        child = self.child(args=("--lane", "mismatch"))
        self.assertEqual(self.ordinary_hello(child)["lane"], "mismatch")
        time.sleep(QUIET)
        self.assertFalse([ln for ln in child.lines if ln.get("op") == "holder"])
        self.assertEqual(self.host.conns, [])

    def test_a_mismatch_verdict_never_connects(self):
        child = self.child(args=())     # marked, but no SMNS_MEMBER: positive evidence of another spawner
        self.assertEqual(self.ordinary_hello(child)["lane"], "mismatch")
        status, answer = child.ready()
        self.assertEqual((status, answer["lane"]), (200, "mismatch"))
        time.sleep(QUIET * 2)
        self.assertEqual(self.host.conns, [])

    def test_an_unresolved_verdict_does_not_connect(self):
        # The session's registry record is not there: M3's retries go on, and the gate waits.
        child = self.child(args=(), env={"SMNS_MEMBER": "999999"})
        self.assertEqual(self.ordinary_hello(child)["lane"], "unresolved")
        status, answer = child.ready()
        self.assertEqual((status, answer["lane"]), (200, "unresolved"))
        time.sleep(QUIET * 2)
        self.assertEqual(self.host.conns, [])

    def test_an_unmarked_session_has_no_holder(self):
        child = self.child(args=(), marked=False)
        self.assertNotIn("lane", self.ordinary_hello(child))
        time.sleep(QUIET)
        self.assertFalse([ln for ln in child.lines if ln.get("op") == "holder"])
        self.assertEqual(self.host.conns, [])

    def test_no_socket_variable_no_holder(self):
        child = self.child(gate=None)
        self.ordinary_hello(child)
        self.assertFalse([ln for ln in child.lines if ln.get("op") == "holder"])


# ------------------------------------------------------------------ acknowledgements


class Acks(Case):
    def test_acks_leave_in_arm_order_one_per_arm(self):
        # R1: two renewals of one fence, the earlier one's install acknowledged late.
        child = self.child()
        child.ready()
        conn, epoch = self.welcomed(child)
        arm = {"t": "arm", "fence": 1, "leaseMs": 400}
        conn.send(arm)
        conn.send(arm)
        first = child.wait_line(lambda ln: ln.get("epoch") == epoch and ln.get("arm") == 1)
        second = child.wait_line(lambda ln: ln.get("epoch") == epoch and ln.get("arm") == 2)
        self.assertEqual((first["frame"], second["frame"]), (arm, arm))
        self.assertQuiet(conn, "armed")   # received is not installed: nothing before the mod's ack
        status, answer = child.ack(epoch, 2, 1)
        self.assertEqual((status, answer), (200, {"ok": True, "sent": 0, "waiting": 1}))
        self.assertQuiet(conn, "armed")   # the later one waits for the earlier
        status, answer = child.ack(epoch, 1, 1)
        self.assertEqual((status, answer), (200, {"ok": True, "sent": 2, "waiting": 0}))
        self.assertTrue(wait_for(lambda: len(conn.seen("armed")) == 2))
        self.assertEqual(child.ack(epoch, 1, 1), (200, {"ok": True, "duplicate": True}))
        self.assertEqual(child.ack(epoch, 2, 1), (200, {"ok": True, "duplicate": True}))
        self.assertEqual(child.ack(epoch, 3, 1)[0], 404)
        time.sleep(QUIET)
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 1}] * 2, "exactly one per arm")

    def test_a_turn_and_its_late_armed_in_either_order(self):
        # R4: an arm meeting a turn in progress gets its armed once installed,
        # before or after the turn, before or after the host's answer.
        child = self.child()
        child.ready()
        conn, epoch = self.welcomed(child)
        conn.send({"t": "arm", "fence": 3, "leaseMs": 400})
        child.wait_line(lambda ln: ln.get("arm") == 1)
        self.assertEqual(child.turn(epoch, 3, "query"), (200, {"ok": True}))
        self.assertEqual(conn.wait_frames(2)[1], {"t": "turn", "fence": 3, "origin": "query"})
        for frame in ({"t": "proceed", "fence": 3}, {"t": "disarm", "fence": 3}):
            conn.send(frame)
            self.assertIsNotNone(child.relay(epoch, frame))
        self.assertEqual(child.ack(epoch, 1, 3)[1]["sent"], 1)
        self.assertEqual(conn.wait_frames(3)[2], {"t": "armed", "fence": 3})
        conn.send({"t": "arm", "fence": 4, "leaseMs": 400})
        child.wait_line(lambda ln: ln.get("arm") == 2)
        self.assertEqual(child.ack(epoch, 2, 4)[1]["sent"], 1)
        self.assertEqual(child.turn(epoch, 4, "peer", "dlv-9"), (200, {"ok": True}))
        self.assertEqual(conn.wait_frames(5)[3:], [{"t": "armed", "fence": 4},
                                                   {"t": "turn", "fence": 4, "origin": "peer", "delivery": "dlv-9"}])

    def test_no_ack_and_no_turn_cross_epochs(self):
        child = self.child()
        child.ready()
        old, epoch1 = self.welcomed(child)
        old.send({"t": "arm", "fence": 1, "leaseMs": 400})
        child.wait_line(lambda ln: ln.get("epoch") == epoch1 and ln.get("arm") == 1)
        self.host.replace()
        new = self.host.conn(1)
        new.wait_frames(1)
        new.send({"t": "welcome", "protocol": 1})
        epoch2 = child.welcome_epoch(2)
        self.assertEqual(child.ack(epoch1, 1, 1), (409, {"ok": False, "code": "epoch",
                                                          "error": "epoch %s is not the gate's connection" % epoch1}))
        self.assertEqual(child.turn(epoch1, 1, "cron")[0], 409)
        self.assertEqual(child.ack(epoch2, 1, 1)[0], 404, "epoch 2 carried no arm 1")
        time.sleep(QUIET)
        self.assertEqual(new.seen(skip_hb=True), [new.seen()[0]], "nothing of epoch 1 on epoch 2")
        self.assertEqual(old.seen("armed") + old.seen("turn"), [])


# ------------------------------------------------------------------ the route


class Route(Case):
    def test_the_route_checks_nonce_generation_and_shape(self):
        child = self.child()
        boot = child.bootstrap()
        g = boot["generation"]
        self.assertEqual(child.post({"kind": "ready", "generation": g}, nonce="x")[1]["code"], "nonce")
        self.assertEqual(child.post({"kind": "ready", "generation": g}, nonce="")[1]["code"], "nonce")
        self.assertEqual(child.post({"kind": "ready"})[1]["code"], "generation")
        self.assertEqual(child.post({"kind": "ready", "generation": g + "0"})[1]["code"], "generation")
        self.assertEqual(child.post([g])[0], 409)
        self.assertEqual(child.post({"kind": "nope", "generation": g})[0], 400)
        time.sleep(QUIET)
        self.assertEqual(self.host.conns, [], "no refused post made the mod ready")
        child.ready()
        conn, epoch = self.welcomed(child)
        conn.send({"t": "arm", "fence": 2, "leaseMs": 400})
        child.wait_line(lambda ln: ln.get("arm") == 1)
        for bad in ({"epoch": epoch, "arm": 0, "fence": 2}, {"epoch": epoch, "arm": "1", "fence": 2},
                    {"epoch": 1, "arm": 1, "fence": 2}, {"epoch": epoch, "arm": 1, "fence": 3},
                    {"epoch": epoch, "arm": 1, "fence": True}):
            self.assertEqual(child.post({"kind": "armed", "generation": g, **bad})[0], 400, bad)
        for bad in ({"fence": 2, "origin": "human"}, {"fence": -1, "origin": "query"},
                    {"fence": 2, "origin": "query", "delivery": ""}, {"fence": 2, "origin": "query", "delivery": 7},
                    {"fence": 2, "origin": "query", "delivery": "d" * 257}):
            self.assertEqual(child.post({"kind": "turn", "generation": g, "epoch": epoch, **bad})[0], 400, bad)
        self.assertEqual(child.ack("another", 1, 2)[0], 409)
        time.sleep(QUIET)
        self.assertEqual(conn.seen(skip_hb=True), [conn.seen()[0]], "no refused post reached the host")
        self.assertEqual(post(boot["socket"], "/command", {"op": "ping"})[0], 404)

    def test_the_bridge_refuses_holder_as_a_command(self):
        child = self.child()
        child.wait_line(lambda ln: ln.get("op") == "hello")
        path = os.path.join(self.home, "s", "bridge", SESSION + ".sock")
        status, answer = sminos_bridge.request(path, "POST", "/command", {"op": "holder", "bootstrap": {}})
        self.assertEqual(status, 400)
        self.assertIn("holder", answer["error"])
        time.sleep(QUIET)
        self.assertEqual(len([ln for ln in child.lines if ln.get("op") == "holder"]), 1, "the bootstrap alone")


# ------------------------------------------------------------------ independence of the bridge's work


class Independence(Case):
    def beats_hold(self, conn, seconds=1.5):
        """Heartbeats keep their cadence for `seconds` from now."""
        start = time.monotonic()
        time.sleep(seconds)
        beats = [t for t in conn.times("hb") if t >= start - HEARTBEAT * 2]
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        self.assertGreaterEqual(len(beats), int(seconds / HEARTBEAT) - 2, "beats %r" % beats)
        self.assertLess(max(gaps), 1.0, "the longest gap between heartbeats")

    def test_a_blocked_stdout_withholds_armed_never_hb(self):
        child = self.child(read_stdout=False)
        child.boot = child.first_line()["bootstrap"]
        child.ready()
        conn = self.host.conn(0)
        conn.wait_frames(1)
        conn.send({"t": "welcome", "protocol": 1})
        self.assertTrue(wait_for(lambda: conn.times("hb")))
        bridge = os.path.join(self.home, "s", "bridge", SESSION + ".sock")
        self.assertTrue(wait_for(lambda: os.path.exists(bridge)))
        # Commands the mod never reads fill the pipe: every later stdout line blocks.
        blocked = threading.Event()

        def flood():
            for _ in range(8):
                try:
                    post(bridge, "/command", {"op": "ping", "pad": "x" * 65536})
                except OSError:
                    pass
            blocked.set()
        for _ in range(4):
            threading.Thread(target=flood, daemon=True).start()
        time.sleep(1.0)
        self.assertFalse(blocked.is_set(), "the floods are held at a full stdout")
        conn.send({"t": "arm", "fence": 1, "leaseMs": 400})
        self.beats_hold(conn)
        self.assertEqual(conn.seen("armed"), [], "an arm the mod cannot read is never acknowledged")

    def test_a_relay_the_mod_never_reads_ends_the_connection_rather_than_lose_a_frame(self):
        # Dropping a relayed arm would pair a later ack with it (R1): past
        # RELAY_QUEUED unread lines the connection ends, and a fresh hello follows.
        child = self.child(read_stdout=False)
        child.boot = child.first_line()["bootstrap"]
        child.ready()
        conn = self.host.conn(0)
        conn.wait_frames(1)
        conn.send({"t": "welcome", "protocol": 1})
        self.assertTrue(wait_for(lambda: conn.times("hb")))
        bridge = os.path.join(self.home, "s", "bridge", SESSION + ".sock")
        self.assertTrue(wait_for(lambda: os.path.exists(bridge)))
        for _ in range(4):
            threading.Thread(target=lambda: [_quiet(post, bridge, "/command", {"op": "ping", "pad": "x" * 65536})
                                             for _ in range(8)], daemon=True).start()
        time.sleep(1.0)
        for fence in range(sminos_holder.RELAY_QUEUED + 8):
            conn.send({"t": "disarm", "fence": fence})
        self.assertTrue(wait_for(lambda: conn.closed), "the connection ends")
        self.assertEqual(self.host.conn(1).wait_frames(1)[0]["t"], "hello")
        with open(os.path.join(self.home, "child.err")) as f:
            self.assertIn("the mod is not reading the relay", f.read())

    def test_heartbeats_while_the_startup_seed_read_is_held(self):
        # The transcript is a FIFO nobody writes: read_seed blocks at its
        # open, before the ordinary hello.
        projects = os.path.join(self.home, "cc", "projects", "p")
        os.makedirs(projects)
        fifo = os.path.join(projects, SESSION + ".jsonl")
        os.mkfifo(fifo)
        child = self.child()
        child.bootstrap()
        child.ready()
        conn, epoch = self.welcomed(child)
        conn.send({"t": "arm", "fence": 1, "leaseMs": 400})
        child.wait_line(lambda ln: ln.get("arm") == 1)
        self.assertEqual(child.ack(epoch, 1, 1)[1]["sent"], 1)
        self.beats_hold(conn)
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 1}])
        self.assertFalse([ln for ln in child.lines if ln.get("op") == "hello"], "the ordinary hello is still held")
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        self.assertIsNotNone(child.wait_line(lambda ln: ln.get("op") == "hello"))

    def hold_seed(self):
        """The session's transcript a FIFO nobody writes: read_seed blocks at
        its open, before the ordinary hello (and the watchdog it starts)."""
        projects = os.path.join(self.home, "cc", "projects", "p")
        os.makedirs(projects)
        fifo = os.path.join(projects, SESSION + ".jsonl")
        os.mkfifo(fifo)
        return fifo

    def orphan(self, args=("--lane", "match"), env=None):
        """A child under a stand-in claude, its ordinary startup held:
        (the stand-in, its bootstrap, the file whose creation ends it)."""
        self.hold_seed()
        go = os.path.join(self.home, "go")
        err = open(os.path.join(self.home, "child.err"), "w")
        parent = subprocess.Popen(
            [sys.executable, "-c", "import os, subprocess, sys, time\n"
             "subprocess.Popen(sys.argv[2:])\n"
             "while not os.path.exists(sys.argv[1]): time.sleep(0.02)\n",
             go, SMINOS, "bridge", "--session", SESSION, *args],
            stdout=subprocess.PIPE, stderr=err,
            env={**os.environ, "HOME": os.path.join(self.home, "home"), "SMINOS_HOME": os.path.join(self.home, "s"),
                 "CLAUDE_CONFIG_DIR": os.path.join(self.home, "cc"), "MAWS_LANE": "B", "MAWS_HOLDER_SOCKET": self.gate,
                 "SMINOS_HOLDER_HEARTBEAT": str(HEARTBEAT), "SMINOS_HOLDER_BACKOFF": str(BACKOFF), **(env or {})})
        err.close()
        boot = json.loads(parent.stdout.readline())["bootstrap"]
        self.assertEqual(boot["pid"], parent.pid)
        self.addCleanup(parent.stdout.close)
        self.addCleanup(lambda: _kill(boot["childPid"]))
        return parent, boot, go

    def test_a_sticky_match_connects_while_the_kept_state_read_is_held(self):
        # The kept state is a FIFO nobody writes: Bridge() blocks reading it.
        # The module's verdict (`--lane match`) reaches the gate at once.
        d = os.path.join(self.home, "s", "bridge")
        os.makedirs(d, mode=0o700)
        os.mkfifo(os.path.join(d, SESSION + ".json"))
        child = self.child()
        child.ready()
        conn, epoch = self.welcomed(child)
        self.assertEqual(conn.seen()[0]["childPid"], child.proc.pid)
        self.beats_hold(conn, 1.0)
        self.assertFalse([ln for ln in child.lines if ln.get("op") == "hello"], "the ordinary hello is still held")

    def test_an_unresolved_verdict_connects_once_resolved_while_the_seed_read_is_held(self):
        # No `--lane`: the session's registry record is missing at first, so
        # the verdict is unresolved; it arrives while read_seed is blocked,
        # and the retries (on their own thread) resolve `match` and connect.
        parent, boot, _go = self.orphan(args=(), env={"SMNS_MEMBER": str(os.getpid())})
        h = {sminos_holder.NONCE_HEADER: boot["nonce"]}
        status, answer = post(boot["socket"], "/holder", {"kind": "ready", "generation": boot["generation"]}, h)
        self.assertEqual((status, answer["lane"]), (200, "unresolved"))
        time.sleep(QUIET)
        self.assertEqual(self.host.conns, [])
        sessions = os.path.join(self.home, "cc", "sessions")
        os.makedirs(sessions)
        with open(os.path.join(sessions, "%d.json" % parent.pid), "w") as f:
            json.dump({"sessionId": SESSION, "pid": parent.pid}, f)
        conn = self.host.conn(0)
        self.assertEqual(conn.wait_frames(1)[0], {"t": "hello", "protocol": 1, "session": SESSION, "pid": parent.pid,
                                                  "childPid": boot["childPid"]})
        conn.send({"t": "welcome", "protocol": 1})
        self.assertTrue(wait_for(lambda: len(conn.times("hb")) >= 2))

    def test_an_orphaned_child_leaves_the_gate_even_while_its_startup_is_held(self):
        # claude dies while the child's ordinary startup is held: the gate
        # client notices for itself, closes, and says hello to no one again.
        parent, boot, go = self.orphan()
        h = {sminos_holder.NONCE_HEADER: boot["nonce"]}
        post(boot["socket"], "/holder", {"kind": "ready", "generation": boot["generation"]}, h)
        conn = self.host.conn(0)
        self.assertEqual(conn.wait_frames(1)[0]["pid"], parent.pid)
        conn.send({"t": "welcome", "protocol": 1})
        self.assertTrue(wait_for(lambda: conn.times("hb")))
        Path(go).touch()
        parent.wait(10)
        self.assertTrue(wait_for(lambda: conn.closed), "the gate connection closes once claude is gone")
        time.sleep(BACKOFF * 3)
        self.assertEqual(len(self.host.conns), 1, "and no hello follows")

    def test_an_orphaned_child_never_connects_and_its_route_still_answers(self):
        # claude dies before the mod said it is ready: the waiting gate sees
        # it, and the route (and /status with it) keeps answering.
        parent, boot, go = self.orphan()
        Path(go).touch()
        parent.wait(10)
        time.sleep(1.5)   # past the gate's own look at its parent
        h = {sminos_holder.NONCE_HEADER: boot["nonce"]}
        status, _ = post(boot["socket"], "/holder", {"kind": "ready", "generation": boot["generation"]}, h)
        self.assertEqual(status, 200)
        time.sleep(BACKOFF * 3)
        self.assertEqual(self.host.conns, [])

    def test_heartbeats_while_stream_posts_saturate_and_a_delivery_lock_is_held(self):
        child = self.child()
        child.ready()
        conn, epoch = self.welcomed(child)
        hello = child.wait_line(lambda ln: ln.get("op") == "hello")
        bridge, nonce = hello["socket"], hello["nonce"]
        chunk = {"type": "chunk", "turnId": "t", "agentId": None, "step": 0, "chunkIndex": 0,
                 "chunk": {"kind": "text", "index": 0, "text": "y" * 200}}
        batch = [chunk] * 4000
        stop = threading.Event()

        def flood():
            while not stop.is_set():
                try:
                    post(bridge, "/events", batch, {sminos_bridge.NONCE_HEADER: nonce})
                except OSError:
                    pass
        threads = [threading.Thread(target=flood, daemon=True) for _ in range(8)]
        lock = os.path.join(self.home, "s", "projects", "p", "delivered", sminos.reader_key(SESSION) + ".lock")
        os.makedirs(os.path.dirname(lock))
        with sminos.flocked(lock):
            for t in threads:
                t.start()
            try:
                conn.send({"t": "arm", "fence": 5, "leaseMs": 400})
                child.wait_line(lambda ln: ln.get("arm") == 1)
                self.assertEqual(child.ack(epoch, 1, 5)[1]["sent"], 1)
                self.beats_hold(conn)
            finally:
                stop.set()
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 5}])

    def test_the_bridge_lock_held_in_process(self):
        # The gate and its route take nothing of the Bridge's: with its lock
        # held, hello, heartbeats, an arm's ack and a turn all go.
        lines, said = [], threading.Event()

        def emit(obj):
            lines.append(obj)
            said.set()
        route = os.path.join(self.home, "h.sock")
        holder = sminos_holder.Holder(SESSION, self.gate, route, emit, log=lambda _t: None)
        bridge = sminos_bridge.Bridge(SESSION, os.path.join(self.home, "b.sock"))
        bridge.holder = holder
        old = sminos_holder.HEARTBEAT_S
        sminos_holder.HEARTBEAT_S = HEARTBEAT
        try:
            with bridge.lock:
                holder.start()
                holder.set_lane("match")
                boot = lines[0]["bootstrap"]
                g = {"generation": boot["generation"]}
                h = {sminos_holder.NONCE_HEADER: boot["nonce"]}
                self.assertEqual(post(route, "/holder", {"kind": "ready", **g}, h)[0], 200)
                conn = self.host.conn(0)
                conn.wait_frames(1)
                conn.send({"t": "welcome", "protocol": 1})
                conn.send({"t": "arm", "fence": 1, "leaseMs": 400})
                arm = wait_for(lambda: next((ln for ln in lines if ln.get("arm") == 1), None))
                ack = {"kind": "armed", "epoch": arm["epoch"], "arm": 1, "fence": 1, **g}
                self.assertEqual(post(route, "/holder", ack, h)[1]["sent"], 1)
                turn = {"kind": "turn", "epoch": arm["epoch"], "fence": 1, "origin": "task", **g}
                self.assertEqual(post(route, "/holder", turn, h)[0], 200)
                self.beats_hold(conn, 1.0)
        finally:
            sminos_holder.HEARTBEAT_S = old
            holder.close()
        self.assertEqual(conn.seen(skip_hb=True)[1:], [{"t": "armed", "fence": 1},
                                                       {"t": "turn", "fence": 1, "origin": "task"}])


# ------------------------------------------------------------------ launch_env


class LaunchEnv(unittest.TestCase):
    def test_launch_env_drops_the_holder_socket(self):
        os.environ["MAWS_HOLDER_SOCKET"] = "/tmp/gate.sock"
        try:
            self.assertNotIn("MAWS_HOLDER_SOCKET", sminos.launch_env("x"))
            self.assertNotIn("MAWS_HOLDER_SOCKET", sminos.launch_env(""))
        finally:
            del os.environ["MAWS_HOLDER_SOCKET"]


# ------------------------------------------------------------------ the fixture's replay


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class Replay(Case):
    """Each case of O16's gate fixture played at the child: the fake host
    sends the fixture's host frames; the test, as the mod, acknowledges an
    arm where the fixture's observer says `armed` and asks a turn where it
    says `turn`. The child's frames, heartbeats aside, must be the fixture's
    observer frames in order, with one `armed` more for each arm the
    fixture's observer left unacknowledged, which the mod acknowledges at the
    case's end (P4, R4: every arm gets its one `armed` once installed, and a
    late one is valid). Every host frame must reach the mod as its relay
    line, an arm numbered."""

    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        source = json.loads((HERE / "p5-o16-gate.source.json").read_text())
        assert git_blob(raw) == source["blob"], "the fixture is not MAWS %s's %s" % (source["commit"][:9], source["path"])
        lines = [json.loads(x) for x in raw.decode().splitlines() if x.strip()]
        cls.header, cls.rows = lines[0], lines[1:]

    def rows_of(self, case):
        return [r for r in self.rows if r["case"] == case]

    def play(self, case):
        child = self.child()
        child.ready()
        conns = -1
        conn = epoch = None
        consumed = 0                 # the connection's non-heartbeat frames already matched
        arms = []                    # (epoch, number, fence) relayed and not yet acknowledged, oldest first
        late = []                    # the `armed` frames the case's end must still see
        closed_at = None
        for row in self.rows_of(case):
            event = row.get("event")
            if event == "silence":
                return child, conn, epoch, arms
            if event == "server_restart":
                closed_at = self.host.replace()
            elif event in ("exit", "closed"):
                conn.close()
                if event == "closed":
                    self.assertEqual([f["t"] for f in conn.seen()], ["hello"], "a hello, then nothing, unwelcomed")
            if event is not None:
                continue
            frame, t = row["frame"], row["frame"]["t"]
            if row["from"] == "observer":
                if t == "hello":
                    conns += 1
                    conn, consumed = self.host.conn(conns), 0
                    if closed_at is not None:
                        conn.wait_frames(1)
                        self.assertGreaterEqual(conn.frames[0][0] - closed_at, BACKOFF * 0.9, "%s: the backoff" % case)
                    expected = {**frame, "session": SESSION, "pid": os.getpid(), "childPid": child.proc.pid}
                elif t == "hb":
                    self.assertTrue(wait_for(lambda: conn.times("hb")), "%s: a heartbeat" % case)
                    continue
                elif t == "armed":
                    e, n, fence = arms.pop(0)
                    self.assertEqual(fence, frame["fence"])
                    self.assertEqual(child.ack(e, n, fence)[0], 200)
                    expected = frame
                else:   # turn: the mod asks it, its origin and opaque delivery as the fixture has them
                    self.assertEqual(child.turn(epoch, frame["fence"], frame["origin"], frame.get("delivery")),
                                     (200, {"ok": True}))
                    expected = frame
                got = conn.wait_frames(consumed + 1)[consumed]
                self.assertEqual(got, expected, "%s: the observer's frame %d" % (case, consumed + 1))
                consumed += 1
                continue
            before = len(child.holder_lines())
            conn.send(frame)
            line = child.next_relay(before)
            self.assertEqual(line["frame"], frame, "%s: %r relayed to the mod" % (case, frame))
            if t == "welcome":
                epoch = line["epoch"]
                continue
            self.assertEqual(line["epoch"], epoch, "%s: relayed under its connection's epoch" % case)
            if t == "arm":
                arms.append((epoch, line["arm"], frame["fence"]))
        # Every arm the fixture's observer left unacknowledged gets its one
        # `armed` now, on a connection still open.
        for e, n, fence in arms:
            if e == epoch and not conn.closed:
                self.assertEqual(child.ack(e, n, fence)[0], 200)
                late.append({"t": "armed", "fence": fence})
        if late:
            self.assertEqual(conn.wait_frames(consumed + len(late))[consumed:], late, "%s: the late acks" % case)
        time.sleep(QUIET)
        self.assertEqual(len(conn.seen(skip_hb=True)), consumed + len(late), "%s: nothing more: %r" % (case, conn.seen()))
        return child, conn, epoch, []

    def test_proceed(self):
        _, conn, _, _ = self.play("proceed")
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 1}], "the arm met a turn: still one armed")

    def test_stop(self):
        child, conn, epoch, _ = self.play("stop")
        stop = next(ln for ln in child.holder_lines() if (ln.get("frame") or {}).get("t") == "stop")
        self.assertEqual(stop["frame"]["reason"], "The holder ended this session; reopening it continues the conversation.")
        self.assertEqual(conn.seen("turn"), [{"t": "turn", "fence": 1, "origin": "peer", "delivery": "dlv-1"}])

    def test_armed_renewing_turn_proceed(self):
        _, conn, _, _ = self.play("armed-renewing-turn-proceed")
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 1}] * 2, "the renewal acknowledged too")

    def test_armed_veto_turn_proceed(self):
        _, conn, _, _ = self.play("armed-veto-turn-proceed")
        self.assertEqual([f["t"] for f in conn.seen(skip_hb=True)], ["hello", "armed", "turn"])

    def test_no_answer(self):
        _, conn, _, _ = self.play("no-answer")
        # The fixture's observer never acknowledged: nothing went before the
        # mod's ack; acknowledged late (after the disarm), it goes once.
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 1}])

    def test_renew(self):
        _, conn, _, _ = self.play("renew")
        self.assertEqual(conn.seen("armed"), [{"t": "armed", "fence": 1}] * 3)
        PENDING.append("P3b: the host awaiting `armed` for a renewal while signalled is the fix-wave host's; "
                       "the child acknowledges every renewal once installed (`renew`, played)")

    def test_heartbeat_loss_up_to_its_silence(self):
        child, conn, epoch, arms = self.play("heartbeat-loss")
        # Past the silence the baseline heals by a second hello on the same
        # connection; on the fixed gate an hb does (R5), which is all this
        # child ever sends there.
        self.assertEqual(len(arms), 1)
        conn.send({"t": "disarm", "fence": 1})
        self.assertIsNotNone(child.relay(epoch, {"t": "disarm", "fence": 1}))
        time.sleep(HEARTBEAT * 6)
        self.assertEqual(len(conn.seen("hello")), 1, "no gap hello")
        conn.send({"t": "arm", "fence": 2, "leaseMs": 400})
        line = child.wait_line(lambda ln: ln.get("epoch") == epoch and ln.get("arm") == 2)
        self.assertEqual(child.ack(epoch, 1, 1)[1]["sent"], 1)
        self.assertEqual(child.ack(epoch, line["arm"], 2)[1]["sent"], 1)
        self.assertEqual(conn.wait_frames(3)[1:], [{"t": "armed", "fence": 1}, {"t": "armed", "fence": 2}])
        PENDING.append("P3c: `heartbeat-loss` healed by `hb` on the same connection: played up to its silence; "
                       "the baseline's gap hello is not this child's (R5), the rest awaits the fix-wave fixture")

    def test_server_restart(self):
        child, conn, epoch, _ = self.play("server-restart")
        self.assertEqual(len(self.host.conns), 2)
        self.assertNotEqual(child.welcome_epoch(1), epoch)

    def test_no_row(self):
        # The fixture's hello names a session no row holds (and no pids); this
        # child says its own, and on the close without a welcome it backs off
        # and says hello afresh.
        self.play("no-row")
        self.assertEqual(self.host.conn(1).wait_frames(1)[0]["t"], "hello")
        PENDING.append("P3a: the final SIGTERM's confirmed-lease check is the fix-wave host's (the joint proof)")


def tearDownModule():
    for line in sorted(set(PENDING)):
        sys.stderr.write("PENDING %s\n" % line)
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
