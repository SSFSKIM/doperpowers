#!/usr/bin/env python3
"""The session plane on the machine side (DC7 M1 of the desk): presence from
the engine's session records, and DX4 subscriptions served from the
transcript on disk joined with the bridge's DX5 stream in one order.

Two halves. The engine (`Subscription`) is driven directly against a scripted
DX5 endpoint (fake_session.py) and a transcript the test writes, on a clock
the test moves, so each order the agreed rules name is produced on purpose: a
row on disk ahead of its notice, a notice ahead of its row, a chunk while the
snapshot waits for its cut, a notice past the 2 s bound, a row that never
comes, a module reload, a gap. Then the uplink (`sminos daemon uplink`)
against the hub stand-in (hub_standin.py, unchanged: it keeps every `session`
message and sends whatever frame the test asks): presence within a second,
subscriptions through DX2, and a reconnect in the middle of a response while
rows keep flushing, in the main transcript and in a subagent's.

A reference consumer (Browser) applies DX4 as the web does and records every
gap in `n`, duplicated row, chunk at or below its watermark, and block whose
streamed text differs from its row. Hermetic: HOME and SMINOS_HOME are
temporary; nothing reaches beyond 127.0.0.1 and this directory.
"""

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid as uuidlib

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", "sminos", "scripts")
T = tempfile.mkdtemp(prefix="smp.", dir="/tmp")
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"), DAEMON_HOST="testhost")
for k in ("CLAUDE_CODE_SESSION_ID", "SMNS_INTERNAL", "DAEMON_HOME", "AGORA_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
os.makedirs(os.environ["SMINOS_HOME"])
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import fake_session  # noqa: E402
import sminos_plane as plane  # noqa: E402

fake_session.READY_HOLD = 0.5
PROJECT = "0d9e8f7a-6b5c-4d3e-a2f1-0e9d8c7b6a59"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, s):
        self.now += s


class Browser:
    """DX4 as the web applies it, recording what would be wrong on screen."""

    def __init__(self):
        self.n = -1
        self.rows = []
        self.errors = []
        self.blocks = {}      # (turnId, agentId, step, index) → partial text
        self.upto = {}        # (turnId, agentId, step) → the last chunk applied
        self.named = {}       # uuid → the block its block-row settles
        self.settled = set()
        self.other = {}       # another loop's block settled on its block-row (main scope): uuid → text
        self.end = None
        self.snapshot = None
        self.subagents = None
        self.usage = []
        self.pages = []
        self.diff = None
        self.kinds = []

    def take(self, env):
        n, kind, body = env["n"], env["kind"], env["body"]
        self.kinds.append(kind)
        if self.end is not None:
            self.errors.append("a %s after end" % kind)
        if n != self.n + 1 and not (kind == "end" and n == 0 and self.n == -1):
            self.errors.append("n went %d → %d (%s)" % (self.n, n, kind))
        self.n = n
        if kind == "snapshot":
            self.snapshot = body
            for row in reversed(body["rows"]):
                self.add_row(row)
            for e in body["streaming"]:
                key = (e["turnId"], e["agentId"], e["step"])
                self.upto[key] = e["upTo"]
                for b in e["blocks"]:
                    self.blocks[key + (b["index"],)] = b["text"]
            self.subagents = body["subagents"]
        elif kind == "chunk":
            key = (body["turnId"], body["agentId"], body["step"])
            if body["chunkIndex"] <= self.upto.get(key, -1):
                self.errors.append("chunk %s %d at or below its watermark" % (key, body["chunkIndex"]))
            self.upto[key] = body["chunkIndex"]
            bk = key + (body["chunk"]["index"],)
            if bk not in self.settled:
                self.blocks[bk] = self.blocks.get(bk, "") + body["chunk"].get("text", "")
        elif kind == "block-row":
            bk = (body["turnId"], body["agentId"], body["step"], body["index"])
            self.named[body["uuid"]] = bk
            if self.snapshot is not None and body["agentId"] != self.scope_agent():
                self.settled.add(bk)
                self.other[body["uuid"]] = self.blocks.pop(bk, None)
        elif kind == "row":
            self.add_row(body["row"])
        elif kind == "end":
            self.end = body
        elif kind == "subagents":
            self.subagents = body["subagents"]
        elif kind == "usage":
            self.usage.append(body)
        elif kind == "rows":
            self.pages.append(body)
        elif kind == "diff":
            self.diff = body

    def scope_agent(self):
        return self.agent

    def add_row(self, row):
        u = row["uuid"]
        if u in [r["uuid"] for r in self.rows]:
            self.errors.append("row %s twice" % u)
        self.rows.append(row)
        bk = self.named.pop(u, None)
        if bk is not None:
            self.settled.add(bk)
            text = self.blocks.pop(bk, None)
            shown = row["message"]["content"][0]["text"] if isinstance(row["message"]["content"], list) else None
            if text is not None and text != shown:
                self.errors.append("block %s streamed %r, its row says %r" % (bk, text, shown))

    def uuids(self):
        return [r["uuid"] for r in self.rows]


def read(path):
    with open(path) as f:
        return f.read()


def new_session():
    return str(uuidlib.uuid4())


class Engine(unittest.TestCase):
    """The Subscription, with the scripted endpoint and a clock the test moves."""

    def setUp(self):
        self.sid = new_session()
        self.fake = fake_session.FakeSession(os.environ["HOME"], os.environ["SMINOS_HOME"], self.sid)
        self.clock = Clock()
        self.alive = True
        self.subs = []

    def tearDown(self):
        for s in self.subs:
            s.close()
        self.fake.stop_bridge()

    def subscribe(self, agent=None, bridge=True):
        reader = plane.BridgeReader(os.path.join(os.environ["SMINOS_HOME"], "bridge", self.sid + ".sock"),
                                    lambda: None) if bridge else None
        if reader is not None:
            reader.start()
        sub = plane.Subscription(project=PROJECT, machine="testhost", session=self.sid, agent=agent,
                                 sub="sub-%d" % len(self.subs), locate=lambda: self.fake.path(None), reader=reader,
                                 presence=lambda: {"record": {"status": "busy"}, "bridge": bridge},
                                 alive=lambda: self.alive, clock=self.clock)
        self.subs.append(sub)
        b = Browser()
        b.agent = agent
        return sub, b

    def pump(self, sub, b, until=lambda: False, wait=3.0):
        """Pumps until `until()` holds or nothing changes for a while."""
        deadline = time.time() + wait
        while time.time() < deadline:
            for env in sub.pump():
                self.assertEqual(env["project"], PROJECT)
                self.assertEqual(env["session"], self.sid)
                b.take(env)
            if until():
                return True
            time.sleep(0.01)
        return False

    def settle(self, sub, b, seconds=0.3):
        self.pump(sub, b, wait=seconds)

    def assertClean(self, b, agent=None):
        self.assertEqual(b.errors, [])
        self.assertEqual(b.uuids(), [r["uuid"] for r in self.fake.rows(agent)], "every row once, in order")
        mine = {k: v for k, v in b.blocks.items() if k[1] == agent}
        self.assertEqual(mine, {}, "no partial text left beside its row")

    # ---------------------------------------------------- without a bridge

    def test_bridgeless_rows_from_the_transcript_alone(self):
        for i in range(3):
            self.fake.user_row("before %d" % i, post=False)
        self.fake.write_row(None, {"type": "cost-state", "usd": 1})  # no uuid: not a row
        self.fake.write_partial(None, '{"type": "user", "uuid": "half')
        self.fake.meta("a1", {"agentType": "x"})
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        s = b.snapshot
        self.assertEqual([r["message"]["content"] for r in s["rows"]], ["before 2", "before 1", "before 0"],
                         "the rows newest first, the half-written one and the uuid-less one left out")
        self.assertFalse(s["more"])
        self.assertEqual(s["streaming"], [])
        self.assertIsNone(s["usage"], "no bridge: usage null")
        self.assertEqual(s["presence"], {"record": {"status": "busy"}, "bridge": False})
        self.assertEqual(s["subagents"], [{"agentId": "a1", "meta": {"agentType": "x"}}])
        self.fake.write_partial(None, '-row", "message": {"role": "user", "content": "finished"}}\n')
        self.fake.user_row("after", post=False)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 5), "new rows follow at once")
        self.assertEqual([r["message"]["content"] for r in b.rows[3:]], ["finished", "after"])
        self.assertEqual(b.errors, [])

    def test_snapshot_fits_its_budget_and_older_rows_page(self):
        pad = "x" * 100000
        ids = [self.fake.user_row("%d %s" % (i, pad), post=False) for i in range(12)]
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        got = [r["uuid"] for r in b.snapshot["rows"]]
        self.assertTrue(0 < len(got) < 12, "as many as fit the budget (%d)" % len(got))
        self.assertEqual(got, list(reversed(ids))[:len(got)], "the newest")
        self.assertTrue(b.snapshot["more"])
        oldest = got[-1]
        b.take(sub.page(oldest, 2)[0])
        page = b.pages[-1]
        self.assertEqual(page["before"], oldest)
        self.assertEqual([r["uuid"] for r in page["rows"]], [ids[ids.index(oldest) - 1], ids[ids.index(oldest) - 2]])
        self.assertTrue(page["more"])
        b.take(sub.page(ids[1], 50)[0])
        self.assertEqual([r["uuid"] for r in b.pages[-1]["rows"]], [ids[0]])
        self.assertFalse(b.pages[-1]["more"])
        self.assertEqual(b.errors, [])

    def test_bridgeless_session_that_ended(self):
        self.fake.user_row("the last word", post=False)
        self.alive = False
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(len(b.rows), 1)
        self.clock.advance(plane.END_GRACE + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "session-ended")
        self.assertEqual(b.errors, [])

    # ---------------------------------------------------- with the bridge

    def test_response_streams_and_settles_by_row(self):
        self.fake.start_bridge()
        self.fake.user_row("question")
        m = self.fake.message()
        m.text(0, "Hel")
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.blocks, {("turn-1", None, 0, 0): "Hel"}, "the partial text from the snapshot")
        m.text(0, "lo, ")
        m.text(0, "world")
        m.row(0)
        m.text(1, "more")
        m.row(1)
        self.fake.user_row("tool result")
        self.fake.usage(1234)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 4 and b.usage))
        self.assertClean(b)
        self.assertLess(b.kinds.index("block-row"), b.kinds.index("row"), "a block-row before its row")
        self.assertEqual(b.usage, [{"context": {"tokens": 1234, "window": 200000, "percent": 0.617},
                                    "cost": {"usd": 0.01}}])

    def test_cut_row_not_yet_on_disk_while_chunks_arrive(self):
        self.fake.start_bridge()
        for agent in (None, "a1"):
            with self.subTest(agent=agent):
                m = self.fake.message(agent=agent)
                m.text(0, "first block")
                u = m.row(0, disk=False)  # announced: in the cut, not yet flushed
                sub, b = self.subscribe(agent=agent)
                self.settle(sub, b)
                self.assertIsNone(b.snapshot, "the snapshot waits for its cut row on disk")
                m.text(1, "second ")  # while the snapshot is built
                m.text(1, "block")
                self.settle(sub, b)
                m.write(0, u)
                self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
                self.assertEqual([r["uuid"] for r in b.snapshot["rows"]], [u], "history up to the cut")
                self.assertTrue(self.pump(sub, b, lambda: b.blocks.get((m.turn, agent, 0, 1)) == "second block"))
                m.row(1)
                self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2))
                self.assertClean(b, agent)

    def test_cut_row_that_never_reaches_disk(self):
        self.fake.start_bridge()
        m = self.fake.message()
        m.text(0, "lost")
        m.row(0, disk=False)
        sub, b = self.subscribe()
        self.settle(sub, b)
        self.clock.advance(plane.NOTICE_WAIT + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual((b.end["reason"], b.n), ("discontinuity", 0))

    def test_row_on_disk_ahead_of_its_notice_across_establishment(self):
        self.fake.start_bridge()
        for agent in (None, "a1"):
            with self.subTest(agent=agent):
                self.fake.user_row("before", agent=agent)
                m = self.fake.message(agent=agent)
                m.text(0, "flushed ")
                m.text(0, "early")
                u = str(uuidlib.uuid4())
                m.write(0, u)  # the engine flushed; the mod's post is late
                sub, b = self.subscribe(agent=agent)
                self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
                self.assertEqual(len(b.snapshot["rows"]), 1, "the row past the cut is not history")
                self.assertEqual({k: v for k, v in b.blocks.items() if k[1] == agent},
                                 {(m.turn, agent, 0, 0): "flushed early"}, "its block still streams")
                self.settle(sub, b)
                self.assertEqual(len(b.rows), 1, "held: a notice may still name it")
                m.notice(0, u)
                self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2))
                self.assertClean(b, agent)
                self.assertEqual(b.kinds[-2:], ["block-row", "row"])

    def test_row_no_notice_named_within_2s_is_drawn_and_a_late_block_row_ends(self):
        self.fake.start_bridge()
        m = self.fake.message()
        m.text(0, "slow post")
        u = str(uuidlib.uuid4())
        m.write(0, u)
        other = self.fake.user_row("no notice ever", post=False)
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.clock.advance(plane.UNNAMED_WAIT + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2))
        self.assertEqual(b.uuids(), [u, other], "in disk order")
        m.notice(0, u)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity", "the block would stay beside its row")

    def test_notice_whose_row_never_flushes(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        m = self.fake.message()
        m.text(0, "x")
        m.row(0, disk=False)
        later = self.fake.user_row("after it")
        self.settle(sub, b)
        self.assertEqual(b.rows, [], "rows follow their notices in order: the later one waits")
        self.clock.advance(plane.NOTICE_WAIT + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")
        self.assertNotIn(later, b.uuids())

    def test_gap_ends_as_a_discontinuity(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.fake.gap()
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")

    def test_module_reload_ends_the_subscription(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.fake.resync()  # a later resync: the child ends every subscription
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")
        again, b2 = self.subscribe()
        self.assertTrue(self.pump(again, b2, lambda: b2.snapshot is not None), "a fresh one is served")

    def test_bridge_not_ready_is_a_discontinuity(self):
        self.fake.start_bridge(ready=False)
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual((b.end["reason"], b.n), ("discontinuity", 0))

    def test_session_ending_ends_the_subscription(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.fake.user_row("last", post=False)
        self.alive = False
        self.fake.stop_bridge()
        self.settle(sub, b)
        self.clock.advance(plane.END_GRACE + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "session-ended")
        self.assertEqual(len(b.rows), 1, "what flushed before the end is drawn")

    def test_null_cut_takes_history_to_eof(self):
        self.fake.start_bridge()
        u = self.fake.user_row("before any notice", post=False)
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.uuids(), [u])
        self.fake.post([{"type": "row-seen", "uuid": u, "agentId": None, "door": "append", "t": 0}])
        self.fake.user_row("after")
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2))
        self.settle(sub, b)
        self.assertIsNone(b.end, "a late notice for history is dropped")
        self.assertClean(b)

    def test_block_row_for_history_whose_block_the_subscriber_holds(self):
        self.fake.start_bridge()
        m = self.fake.message()
        m.text(0, "raced")
        u = str(uuidlib.uuid4())
        m.write(0, u)  # on disk, cut still null: history to EOF holds it
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.uuids(), [u])
        m.notice(0, u)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity", "else its streamed text stays beside its row")

    # ---------------------------------------------------- scopes

    def test_agent_scope_carries_that_agent_alone(self):
        self.fake.start_bridge()
        self.fake.meta("a1", {"agentType": "worker"})
        self.fake.meta("a2", {"agentType": "other"})
        self.fake.user_row("the brief", agent="a1")
        sub, b = self.subscribe(agent="a1")
        main = self.fake.message()
        main.text(0, "main text")
        sa = self.fake.message(agent="a1", turn="t-a1")
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertNotIn("usage", b.snapshot)
        self.assertEqual(b.snapshot["subagents"], [{"agentId": "a1", "meta": {"agentType": "worker"}}])
        sa.text(0, "sub ")
        sa.text(0, "text")
        sa.row(0)
        main.row(0)
        self.fake.user_row("result", agent="a1")
        self.fake.usage(5)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 3))
        self.settle(sub, b)
        self.assertClean(b, agent="a1")
        self.assertTrue(all(r.get("agentId") == "a1" for r in b.rows))
        self.assertEqual(b.usage, [])
        self.assertNotIn(("turn-1", None, 0, 0), b.blocks)

    def test_main_scope_carries_every_chunk_and_the_tree(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.snapshot["subagents"], [])
        sa = self.fake.message(agent="a1", turn="t-a1")
        sa.text(0, "sub ")
        self.fake.meta("a1", {"agentType": "worker"})
        self.clock.advance(1)
        self.assertTrue(self.pump(sub, b, lambda: b.subagents))
        sa.text(0, "streams")
        u = sa.row(0)
        self.assertTrue(self.pump(sub, b, lambda: u in b.other))
        self.assertEqual(b.other[u], "sub streams", "a subagent's text streams in the main view")
        self.settle(sub, b)
        self.assertEqual(b.rows, [], "its rows stay in its own transcript")
        self.assertEqual(b.errors, [])


class Hub:
    """The test's hands on the hub stand-in."""

    def __init__(self, port):
        self.port = port

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request(method, path, body=None if body is None else json.dumps(body),
                  headers={"Content-Type": "application/json"})
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def state(self):
        return self.call("GET", "/control/state")[1]

    def send(self, frame_):
        status, body = self.call("POST", "/control/send", {"frames": [frame_]})
        assert status == 200, body
        return body

    def messages(self):
        return [s["message"] for s in self.state()["sessions"]]

    def wait(self, test, timeout=10.0):
        """The messages once `test(messages)` holds, else None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ms = self.messages()
            if test(ms):
                return ms
            time.sleep(0.03)
        return None


class Uplink(unittest.TestCase):
    """The plane on the uplink's stream, against the hub stand-in."""

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        home, sh = os.environ["HOME"], os.environ["SMINOS_HOME"]
        cls.bin = os.path.join(T, "bin")
        os.makedirs(cls.bin)
        with open(os.path.join(cls.bin, "claude"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
        os.chmod(os.path.join(cls.bin, "claude"), 0o755)
        os.environ["PATH"] = cls.bin + os.pathsep + os.environ["PATH"]
        os.environ["SMINOS_DERIVE_EVERY"] = "0"
        port_file = os.path.join(T, "hub.port")
        cls.spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1", "2000"])
        deadline = time.time() + 10
        while not (os.path.exists(port_file) and read(port_file)) and time.time() < deadline:
            time.sleep(0.05)
        cls.hub = Hub(int(read(port_file)))
        url = "http://127.0.0.1:%d" % cls.hub.port

        cls.root = os.path.join(T, "hp")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
        subprocess.run(git + ["init", "-q", cls.root], check=True)
        sminos_cli = os.path.join(SCRIPTS, "sminos")
        subprocess.run([sminos_cli, "project", "init", "--name", "hubproj"], cwd=cls.root, check=True,
                       capture_output=True)
        smns = os.path.join(cls.root, ".smns")
        d = json.loads(read(smns))
        d["hub"] = {"url": url, "org": "org-1"}
        with open(smns, "w") as f:
            json.dump(d, f, indent=2)
        cls.project = d["project"]
        with open(os.path.join(cls.root, "tracked.txt"), "w") as f:
            f.write("one\n")
        subprocess.run(git + ["-C", cls.root, "add", "-A"], check=True)
        subprocess.run(git + ["-C", cls.root, "commit", "-qm", "base"], check=True)

        # A live session in the project: its record names a process that runs.
        cls.sid = new_session()
        cls.holder = cls.spawn(["sleep", "3600"])
        cls.record_path = os.path.join(home, ".claude", "sessions", "%d.json" % cls.holder.pid)
        cls.write_record({"status": "idle"})
        cls.fake = fake_session.FakeSession(home, sh, cls.sid)
        cls.fake.user_row("hello")
        subprocess.run([sminos_cli, "daemon", "tick"], check=True, capture_output=True)

        key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
        os.makedirs(os.path.join(sh, "daemon"), exist_ok=True)
        cred = os.path.join(sh, "daemon", "hub.json")
        with open(cred, "w") as f:
            json.dump({"hub": url, "org": "org-1", "machine": "testhost", "client_id": "cid-1",
                       "client_secret": "secret-1", "key": key}, f)
        os.chmod(cred, 0o600)
        cls.uplink = cls.spawn([sminos_cli, "daemon", "uplink"])
        ok = cls.hub.wait(lambda ms: any(m["kind"] == "presence" and m["session"] == cls.sid for m in ms))
        assert ok is not None, "the uplink connected and said its sessions' presence"

    @classmethod
    def spawn(cls, argv):
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.procs.append(p)
        return p

    @classmethod
    def write_record(cls, fields):
        rec = {"pid": cls.holder.pid, "sessionId": cls.sid, "cwd": cls.root, "kind": "interactive",
               "name": "m", "nameSource": "derived", **fields}
        tmp = cls.record_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(rec, f)
        os.replace(tmp, cls.record_path)

    @classmethod
    def tearDownClass(cls):
        cls.fake.stop_bridge()
        for p in reversed(cls.procs):
            p.terminate()
        for p in cls.procs:
            p.wait(10)

    def tearDown(self):
        self.fake.stop_bridge()

    # ---------------------------------------------------- helpers

    def presences(self, ms):
        return [m["body"] for m in ms if m["kind"] == "presence" and m["session"] == self.sid]

    def generation(self):
        return self.hub.state()["generation"]

    def reconnect(self):
        """Drops the stream; returns once the uplink is back with presence said again."""
        before = self.generation()
        count = len(self.hub.state()["sessions"])
        self.hub.call("POST", "/control/drop", {})
        ok = self.hub.wait(lambda ms: len(ms) > count and self.generation() > before and any(
            m["kind"] == "presence" and m["session"] == self.sid for m in ms[count:]), timeout=15)
        self.assertIsNotNone(ok, "the uplink reconnected and said presence again")

    def subscribe(self, agent=None):
        sub = "sub-" + uuidlib.uuid4().hex[:12]
        self.hub.send({"t": "subscribe", "project": self.project, "session": self.sid, "agentId": agent, "sub": sub})
        b = Browser()
        b.agent = agent
        b.sub = sub
        b.seen = 0
        return b

    def feed(self, b, until, timeout=10.0):
        """Feeds the sub's messages to `b` until `until()` holds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            mine = [m for m in self.hub.messages() if m.get("sub") == b.sub]
            for m in mine[b.seen:]:
                self.assertEqual((m["project"], m["machine"], m["session"]), (self.project, "testhost", self.sid))
                b.take(m)
            b.seen = len(mine)
            if until():
                return True
            time.sleep(0.03)
        return False

    def assertClean(self, b, agent=None):
        self.assertEqual(b.errors, [])
        self.assertEqual(b.uuids(), [r["uuid"] for r in self.fake.rows(agent)], "every row once, in order")
        self.assertEqual({k: v for k, v in b.blocks.items() if k[1] == agent}, {}, "no text left beside its row")

    # ---------------------------------------------------- the cases

    def test_a_presence_within_a_second(self):
        ms = self.hub.messages()
        machine = [m for m in ms if m["kind"] == "machine"]
        self.assertTrue(machine, "machine presence on connect")
        self.assertEqual(machine[-1]["body"]["policy"], {"read_only": False, "ceiling": "default"})
        self.assertEqual(self.presences(ms)[0], {"record": {"status": "idle"}, "bridge": False})
        count = len(ms)
        t0 = time.time()
        self.write_record({"status": "waiting", "waitingFor": "input needed", "needs": None})
        got = self.hub.wait(lambda ms: {"record": {"status": "waiting", "waitingFor": "input needed", "needs": None},
                                        "bridge": False} in self.presences(ms[count:]), timeout=3)
        took = time.time() - t0
        self.assertIsNotNone(got, "the record's change reaches the hub")
        self.assertLess(took, 1.0, "within a second (%.2fs)" % took)
        t0 = time.time()
        self.fake.start_bridge()
        got = self.hub.wait(lambda ms: any(p["bridge"] for p in self.presences(ms[count:])), timeout=3)
        self.assertIsNotNone(got, "a bridge that answers is said")
        self.assertLess(time.time() - t0, 1.0)
        self.write_record({"status": "busy"})
        self.reconnect()
        ms = self.hub.messages()
        self.assertEqual(self.presences(ms)[-1], {"record": {"status": "busy"}, "bridge": True},
                         "republished after the reconnect")
        self.write_record({"status": "idle"})

    def test_a2_a_session_that_starts_and_ends(self):
        holder = self.spawn(["sleep", "3600"])
        sid = new_session()
        path = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % holder.pid)
        with open(path, "w") as f:
            json.dump({"pid": holder.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive",
                       "status": "busy"}, f)

        def said(ms):
            return [m["body"] for m in ms if m["kind"] == "presence" and m["session"] == sid]

        t0 = time.time()
        ms = self.hub.wait(lambda ms: said(ms), timeout=5)
        self.assertIsNotNone(ms, "a session that starts in the project is said")
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual(said(ms), [{"record": {"status": "busy"}, "bridge": False}])
        holder.terminate()
        holder.wait(5)
        ms = self.hub.wait(lambda ms: {"record": None, "bridge": False} in said(ms), timeout=5)
        self.assertIsNotNone(ms, "and once its process is gone, said as not running")

    def test_b_subscription_rows_diff_and_end(self):
        b = self.subscribe()
        self.assertTrue(self.feed(b, lambda: b.snapshot is not None))
        self.assertEqual(b.snapshot["streaming"], [])
        self.assertIsNone(b.snapshot["usage"])
        self.assertTrue(b.snapshot["rows"])
        self.fake.start_bridge()
        self.assertTrue(self.feed(b, lambda: b.end is not None), "a bridge appearing ends a bridgeless one")
        self.assertEqual(b.end["reason"], "discontinuity")
        b = self.subscribe()
        self.assertTrue(self.feed(b, lambda: b.snapshot is not None))
        m = self.fake.message()
        m.text(0, "streamed ")
        m.text(0, "through the hub")
        m.row(0)
        self.fake.usage(42)
        self.assertTrue(self.feed(b, lambda: b.usage and len(b.rows) == len(self.fake.rows())))
        self.assertClean(b)
        oldest = b.rows[1]["uuid"]
        self.hub.send({"t": "rows", "project": self.project, "session": self.sid, "agentId": None, "sub": b.sub,
                       "before": oldest, "limit": 5})
        self.assertTrue(self.feed(b, lambda: b.pages))
        self.assertEqual([r["uuid"] for r in b.pages[0]["rows"]], [b.rows[0]["uuid"]])
        with open(os.path.join(self.root, "tracked.txt"), "a") as f:
            f.write("two\n")
        with open(os.path.join(self.root, "new.txt"), "w") as f:
            f.write("fresh\n")
        self.hub.send({"t": "diff", "project": self.project, "session": self.sid, "sub": b.sub})
        self.assertTrue(self.feed(b, lambda: b.diff is not None))
        self.assertEqual(b.diff["base"], "main")
        self.assertIn("+two", b.diff["text"])
        self.assertIn("+fresh", b.diff["text"])
        self.hub.send({"t": "unsubscribe", "project": self.project, "sub": b.sub})
        self.assertTrue(self.feed(b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "unsubscribed")
        self.assertEqual(b.errors, [])

    def test_c_unknown_session(self):
        sub = "sub-" + uuidlib.uuid4().hex[:12]
        other = new_session()
        self.hub.send({"t": "subscribe", "project": self.project, "session": other, "agentId": None, "sub": sub})
        ms = self.hub.wait(lambda ms: any(m.get("sub") == sub for m in ms))
        end = [m for m in ms if m.get("sub") == sub]
        self.assertEqual([(m["kind"], m["n"], m["body"]["reason"]) for m in end], [("end", 0, "error")])

    def test_d_module_reload(self):
        self.fake.start_bridge()
        b = self.subscribe()
        self.assertTrue(self.feed(b, lambda: b.snapshot is not None))
        self.fake.resync()
        self.assertTrue(self.feed(b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")
        b = self.subscribe()
        m = self.fake.message()
        m.text(0, "after the reload")
        m.row(0)
        self.assertTrue(self.feed(b, lambda: len(b.rows) == len(self.fake.rows())))
        self.assertClean(b)

    def test_e_reconnect_mid_response_while_rows_flush(self):
        """A response streams in the main loop and in a subagent while rows
        keep flushing; the stream drops in the middle (a Worker restart); a
        row reaches disk ahead of its notice across the reconnect. Both
        scopes, subscribed before and again after, draw every row once and
        every block's text whole."""
        self.fake.start_bridge()
        self.fake.meta("a7", {"agentType": "worker"})
        self.fake.user_row("brief", agent="a7")
        before = [self.subscribe(), self.subscribe("a7")]
        for b in before:
            self.assertTrue(self.feed(b, lambda b=b: b.snapshot is not None))
        main = self.fake.message()
        sa = self.fake.message(agent="a7", turn="t-a7")
        for i in range(3):
            main.text(i, "main %d, " % i)
            sa.text(i, "sub %d, " % i)
            main.text(i, "more")
            sa.text(i, "more")
            main.row(i)
            sa.row(i)
            self.fake.user_row("result %d" % i)
            time.sleep(0.05)
        main.text(3, "cut ")
        sa.text(3, "cut ")
        for b in before:
            self.assertTrue(self.feed(b, lambda b=b: len(b.rows) == len(self.fake.rows(b.agent))))
            self.assertEqual(b.errors, [])
        main.text(3, "short")
        early = str(uuidlib.uuid4())
        main.write(3, early)  # flushed; the mod's post is late
        flushing = self.fake.user_row("flushing as it drops", post=False)  # its post is late too
        stop = threading.Event()

        def keep_flushing():  # the subagent's rows go on flushing, each noticed, through the drop
            i = 0
            while not stop.is_set():
                self.fake.user_row("flush %d" % i, agent="a7")
                i += 1
                time.sleep(0.02)

        writer = threading.Thread(target=keep_flushing)
        writer.start()
        try:
            self.reconnect()
        finally:
            stop.set()
            writer.join()
        for b in before:
            self.feed(b, lambda: False, timeout=0.5)
            self.assertEqual(b.errors, [], "nothing wrong up to the drop")
        after = [self.subscribe(), self.subscribe("a7")]
        for b in after:
            self.assertTrue(self.feed(b, lambda b=b: b.snapshot is not None))
        self.assertIn((main.turn, None, 0, 3), after[0].blocks, "the late-noticed block still streams")
        sa.text(3, "tail")
        main.notice(3, early)
        self.fake.post([{"type": "row-seen", "uuid": flushing, "agentId": None, "door": "append", "t": 0}])
        sa.row(3)
        self.fake.user_row("after", post=True)
        for b in after:
            self.assertTrue(self.feed(b, lambda b=b: len(b.rows) == len(self.fake.rows(b.agent))), b.agent)
            self.feed(b, lambda: False, timeout=0.3)
            self.assertClean(b, b.agent)
        self.assertEqual(after[0].other.get(self.fake.rows("a7")[-1]["uuid"]), "cut tail",
                         "the subagent's text streamed whole in the main view")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
