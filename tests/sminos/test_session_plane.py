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

import base64
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
import urllib.parse
import uuid as uuidlib
from unittest import mock

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
import ws_client  # noqa: E402

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
        self.step_ends = []   # (turnId, agentId, step), in order
        self.dropped = {}     # a block a step-end dropped (no block-row came): its partial text
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
        elif kind == "step-end":
            key = (body["turnId"], body["agentId"], body["step"])
            self.step_ends.append(key)
            # A block its block-row named waits for its row; one with none was cut off.
            for bk in [bk for bk in self.blocks if bk[:3] == key and bk not in self.named.values()]:
                self.dropped[bk] = self.blocks.pop(bk)  # no block-row came: an aborted block's text goes
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
        self.settle(sub, b)
        self.clock.advance(plane.NOTICE_WAIT - 0.5)
        self.settle(sub, b)
        self.assertIsNone(b.end, "a notice may come before its flush")
        self.clock.advance(0.6)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")

    def test_an_unnamed_row_is_released_by_a_later_rows_notice(self):
        """Disk order: a row no notice names (a compaction's) goes out as soon
        as a later row of its loop is noticed, ahead of it — not 2 s later,
        after it."""
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        quiet = self.fake.user_row("a compaction's row: no hook names it", post=False)
        self.settle(sub, b)
        self.assertEqual(b.rows, [], "held: a notice may still come")
        said = self.fake.user_row("the next prompt")
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2), "released by the later row's notice")
        self.assertEqual(b.uuids(), [quiet, said], "in disk order")
        quiet2 = self.fake.user_row("another quiet row", post=False)
        m = self.fake.message()
        m.text(0, "noticed before its flush")
        u = str(uuidlib.uuid4())
        m.notice(0, u)  # a row not on disk yet is later than every row that is
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 3))
        self.assertEqual(b.uuids()[-1], quiet2)
        m.write(0, u)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 4))
        self.assertClean(b)
        self.assertIsNone(b.end, "the clock never moved: nothing waited 2 s")

    def test_rows_wait_behind_an_earlier_one(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        first = self.fake.user_row("first, its notice late", post=False)
        self.settle(sub, b)
        self.clock.advance(1.5)
        second = self.fake.user_row("second, never noticed", post=False)
        self.settle(sub, b)
        self.clock.advance(0.6)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 1))
        self.assertEqual(b.uuids(), [first], "the first goes after 2 s; the second, younger, waits")
        self.clock.advance(1.5)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2))
        self.assertEqual(b.uuids(), [first, second])
        self.fake.seen(first)
        self.settle(sub, b)
        self.assertIsNone(b.end, "a row-seen for a row released unnamed is passed over")

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

    def test_bridge_not_ready_past_the_window_is_a_discontinuity(self):
        self.fake.start_bridge(ready=False)
        sub, b = self.subscribe()
        t0 = time.time()
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None, wait=12))
        self.assertEqual((b.end["reason"], b.n), ("discontinuity", 0))
        self.assertGreaterEqual(time.time() - t0, plane.NOT_READY_WINDOW, "the 503 was asked again for the window")

    def test_bridge_ready_within_the_window_is_served(self):
        self.fake.start_bridge(ready=False)
        sub, b = self.subscribe()
        self.settle(sub, b, 1.5)  # past the first 503 (the hold is 0.5 s here)
        self.assertIsNone(b.end)
        self.fake.resync()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None, wait=6), "a 503 is retried, as watch does")
        self.assertIsNone(b.end)

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

    def test_a_null_cut_has_empty_history(self):
        self.fake.start_bridge()  # no rows on disk: the seed names no loop
        u = self.fake.user_row("flushed before its notice", post=False)
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.snapshot["rows"], [], "the loop had no rows at load: its history is empty")
        self.settle(sub, b)
        self.assertEqual(b.rows, [], "the row is live, held for its notice")
        self.fake.seen(u)
        self.fake.user_row("after")
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 2))
        self.assertClean(b)

    def test_a_null_cut_row_flushed_beside_its_streaming_block(self):
        """The overlap the seeded cut closes: a row on disk whose block still
        streams in the snapshot is live, not history, and comes on its
        block-row."""
        self.fake.start_bridge()
        m = self.fake.message()
        m.text(0, "raced")
        u = str(uuidlib.uuid4())
        m.write(0, u)
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual((b.snapshot["rows"], b.blocks), ([], {(m.turn, None, 0, 0): "raced"}))
        m.notice(0, u)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 1))
        self.assertIsNone(b.end)
        self.assertClean(b)

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

    def test_step_end_follows_the_steps_block_rows(self):
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        m = self.fake.message()
        m.text(0, "a whole ")
        m.text(0, "answer")
        m.row(0)
        m.end()
        self.assertTrue(self.pump(sub, b, lambda: b.step_ends and b.rows))
        self.assertEqual(b.step_ends, [(m.turn, None, 0)])
        self.assertLess(b.kinds.index("block-row"), b.kinds.index("step-end"), "after every block-row of the step")
        self.assertEqual(b.dropped, {})
        self.assertClean(b)
        m.turn_complete("answer")
        self.settle(sub, b)
        self.assertEqual(b.step_ends, [(m.turn, None, 0)], "its turn's end says nothing more")

    def test_an_aborted_step_is_cut_off_by_its_turns_end(self):
        self.fake.start_bridge()
        m = self.fake.message()
        m.text(0, "begun before the subscription, ")
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        m.text(0, "then Esc")
        m.turn_complete("aborted")  # no step end: the turn's end cuts the step off
        self.assertTrue(self.pump(sub, b, lambda: b.step_ends))
        self.assertEqual(b.step_ends, [(m.turn, None, 0)])
        self.assertEqual(b.dropped, {(m.turn, None, 0, 0): "begun before the subscription, then Esc"},
                         "the partial text of a block no row will settle goes")
        self.assertEqual(b.blocks, {})
        self.assertEqual(b.errors, [])

    def test_step_end_by_scope(self):
        self.fake.start_bridge()
        main_sub, main_b = self.subscribe()
        agent_sub, agent_b = self.subscribe(agent="a1")
        for sub, b in ((main_sub, main_b), (agent_sub, agent_b)):
            self.assertTrue(self.pump(sub, b, lambda b=b: b.snapshot is not None))
        main = self.fake.message()
        sa = self.fake.message(agent="a1", turn="t-a1")
        main.text(0, "m")
        sa.text(0, "s")
        main.end()
        sa.end()
        self.assertTrue(self.pump(main_sub, main_b, lambda: len(main_b.step_ends) == 2))
        self.assertEqual(sorted(main_b.step_ends, key=str), sorted([(main.turn, None, 0), ("t-a1", "a1", 0)], key=str),
                         "a main sub carries every agent's")
        self.settle(agent_sub, agent_b)
        self.assertEqual(agent_b.step_ends, [("t-a1", "a1", 0)], "an agent sub its own")

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


class RealChild(Engine):
    """Every engine case again, the bridge being the real child (`sminos
    bridge --session`, DC2's M4) with this process as its mod: the seeded
    cut from its hello, its readiness, its notices and its stream. Its wait
    for the first resync is the script's, 0.5 s."""

    def setUp(self):
        super().setUp()
        self.fake.real = True
        self.fake.child_env = {"SMINOS_BRIDGE_READY_WAIT": str(fake_session.READY_HOLD)}

    def test_a_module_reload_with_the_seeded_cut(self):
        """The module reloads mid-session (a new child, its hello's seed the
        transcript's tail): the old stream ends, the new snapshot's history
        is the seed, a request begun under the old module never streams and
        its row comes by row-seen, and a new request streams."""
        for agent in (None, "a1"):
            with self.subTest(agent=agent):
                self.fake.start_bridge()
                self.fake.user_row("before the reload", agent=agent)
                old = self.fake.message(agent=agent, turn="t-old-%s" % agent)
                old.text(0, "half ")
                sub, b = self.subscribe(agent=agent)
                self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
                self.fake.stop_bridge(unlink=False)
                self.fake.start_bridge()
                self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
                self.assertEqual(b.end["reason"], "discontinuity")
                self.assertEqual(self.fake.child.seed.get(agent or "main"), self.fake.rows(agent)[-1]["uuid"],
                                 "the hello's seed is the loop's tail")
                again, b2 = self.subscribe(agent=agent)
                self.assertTrue(self.pump(again, b2, lambda: b2.snapshot is not None))
                self.assertEqual(b2.snapshot["streaming"], [], "a request begun before the reload never streams")
                self.assertEqual(b2.uuids(), [r["uuid"] for r in self.fake.rows(agent)], "history to the seed")
                old.text(0, "done")
                u = old.row(0)  # named by row-seen: nothing of it streamed here
                new = self.fake.message(agent=agent, turn="t-new-%s" % agent)
                new.text(0, "fresh")
                self.assertTrue(self.pump(again, b2, lambda: b2.blocks.get((new.turn, agent, 0, 0)) == "fresh"))
                new.row(0)
                self.assertTrue(self.pump(again, b2, lambda: len(b2.rows) == len(self.fake.rows(agent))))
                self.assertIn(u, b2.uuids())
                self.assertClean(b2, agent)
                self.fake.stop_bridge()
                sub.close()
                again.close()


class Lifecycle(unittest.TestCase):
    """The engine's records as presence reads them, and the machine's policy."""

    def setUp(self):
        self.sid = new_session()
        self.path = os.path.join(os.environ["HOME"], ".claude", "sessions", "lifecycle.json")
        with open(self.path, "w") as f:
            json.dump({"pid": 999999, "sessionId": self.sid, "procStart": "Thu Oct 15 09:52:25 2026",
                       "status": "idle"}, f)

    def tearDown(self):
        os.unlink(self.path)

    def test_a_record_left_behind_whose_pid_is_reused(self):
        records = plane.Records()
        alive, start = [True], ["Thu Oct 15 09:52:25 2026"]
        with mock.patch.object(plane.sminos, "pid_alive", lambda _pid: alive[0]), \
                mock.patch.object(plane.sminos, "proc_start", lambda _pid: start[0]):
            self.assertIn(self.sid, records.scan(), "its process runs")
            alive[0] = False
            self.assertNotIn(self.sid, records.scan(), "the session crashed: its record is left behind")
            alive[0], start[0] = True, "Fri Oct 16 11:00:00 2026"
            self.assertNotIn(self.sid, records.scan(), "its pid now holds another process")

    def test_a_pid_reused_between_two_polls(self):
        """The process exits and its pid is reused between two scans: alive at
        both, only its start time changed. The identity is read again within
        IDENTITY_EVERY, so the stale session leaves within that bound."""
        clock = Clock()
        records = plane.Records(clock=clock)
        start, reads = ["Thu Oct 15 09:52:25 2026"], []

        def proc_start(pid):
            reads.append(pid)
            return start[0]

        with mock.patch.object(plane.sminos, "pid_alive", lambda _pid: True), \
                mock.patch.object(plane.sminos, "proc_start", proc_start):
            self.assertIn(self.sid, records.scan())
            start[0] = "Fri Oct 16 11:00:00 2026"  # reused between polls, never seen dead
            clock.advance(plane.PRESENCE_EVERY)
            self.assertIn(self.sid, records.scan(), "within the bound the identity is not read again")
            self.assertEqual(len(reads), 1, "ps is not asked at every poll")
            clock.advance(plane.IDENTITY_EVERY)
            self.assertNotIn(self.sid, records.scan(), "past the bound the pid's start time is read again")
            self.assertEqual(len(reads), 2)

    def test_the_ceiling_is_the_settings_default_mode(self):
        settings = os.path.join(os.environ["HOME"], ".claude", "settings.json")
        import sminos_hublog as hublog
        try:
            self.assertEqual(hublog.machine_policy(), {"read_only": False, "ceiling": "default"},
                             "no settings: the engine's own default")
            with open(settings, "w") as f:
                json.dump({"permissions": {"defaultMode": "acceptEdits"}}, f)
            before = os.stat(settings).st_mtime_ns
            self.assertEqual(hublog.machine_policy()["ceiling"], "acceptEdits", "the settings' defaultMode")
            self.assertEqual(os.stat(settings).st_mtime_ns, before, "read, never written")
            with open(settings, "w") as f:
                json.dump({"permissions": {"allow": ["Bash"]}}, f)
            self.assertEqual(hublog.machine_policy()["ceiling"], "default", "settings that name no mode")
        finally:
            if os.path.exists(settings):
                os.unlink(settings)


def call(url, method, path, body=None, headers=None):
    u = urllib.parse.urlsplit(url)
    c = http.client.HTTPConnection(u.hostname, u.port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body),
              headers={"Content-Type": "application/json", **(headers or {})})
    try:
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")
    finally:
        c.close()


class Hub:
    """The hub the uplink talks to, as the tests use it: what it relays (the
    DX4 messages a browser of the project would see, in order), the frames
    a browser's subscription makes it send the machine, and a dropped stream.
    The base reads its messages from `messages()`."""

    machine = "testhost"

    def wait(self, test, timeout=10.0):
        """The messages once `test(messages)` holds, else None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ms = self.messages()
            if test(ms):
                return ms
            time.sleep(0.03)
        return None


class StandinHub(Hub):
    """hub_standin.py (DX2's machine side): every `session` message a POST
    carried, and any frame sent down as the test asks."""

    org = "org-1"

    def __init__(self, spawn):
        port_file = os.path.join(T, "hub.port")
        spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1", "2000"])
        deadline = time.time() + 10
        while not (os.path.exists(port_file) and read(port_file)) and time.time() < deadline:
            time.sleep(0.05)
        self.url = "http://127.0.0.1:%s" % read(port_file)

    def enroll(self, _sminos_cli):
        cred = os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")
        os.makedirs(os.path.dirname(cred), exist_ok=True)
        with open(cred, "w") as f:
            json.dump({"hub": self.url, "org": self.org, "machine": self.machine, "client_id": "cid-1",
                       "client_secret": "secret-1", "key": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"}, f)
        os.chmod(cred, 0o600)

    def follow(self, _project):
        pass

    def state(self):
        return call(self.url, "GET", "/control/state")[1]

    def send(self, frame_):
        status, body = call(self.url, "POST", "/control/send", {"frames": [frame_]})
        assert status == 200, body

    def messages(self):
        return [s["message"] for s in self.state()["sessions"]]

    def drop(self):
        """Ends the uplink's stream; a predicate: whether a newer one opened."""
        before = self.state()["generation"]
        call(self.url, "POST", "/control/drop", {})
        return lambda: self.state()["generation"] > before


class LocalHub(Hub):
    """DC3's local hub behind its stand-in for Access (DESK_HUB, its URL): the
    machine enrolls with a code the stand-in mints, and the test is a
    browser of the project (DX3), subscribing over its socket."""

    org = "local"

    def __init__(self, url):
        self.url = url.rstrip("/")
        self.socket = None
        # The hub keeps its machines across runs: a name of this run's own.
        self.machine = "testhost-" + uuidlib.uuid4().hex[:6]

    def enroll(self, sminos_cli):
        status, body = call(self.url, "POST", "/standin/enrollment-code", {"machine": self.machine})
        assert status == 200, body
        r = subprocess.run([sminos_cli, "hub", "enroll", "--name", self.machine], input=body["code"].encode(),
                           capture_output=True)
        assert r.returncode == 0, (r.stdout + r.stderr).decode()

    def follow(self, project):
        """Opens the browser's socket once the uplink registered the project."""
        ws_url = "ws" + self.url[len("http"):] + "/api/projects/%s/socket" % project
        deadline = time.time() + 20
        while True:
            try:
                self.socket = ws_client.WebSocket(ws_url)
                return
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.2)

    def close(self):
        if self.socket is not None:
            self.socket.close()

    def send(self, frame_):
        """A down frame the test wants the machine to receive, as the browser
        frame that makes the hub send it (DX3)."""
        t = frame_["t"]
        keep = {"subscribe": ("session", "agentId", "sub"), "unsubscribe": ("sub",), "rows": ("sub", "before", "limit"),
                "diff": ("sub",)}[t]
        out = {"t": t, **{k: frame_[k] for k in keep}}
        if t == "subscribe":
            out["machine"] = self.machine
        self.socket.send(out)

    def messages(self):
        out = []
        for f in self.socket.received():
            if f.get("t") == "session":
                out.append(f["message"])
            elif f.get("t") == "machines":
                out += [{"kind": "machine", "session": None, "sub": None, "machine": m["machine"],
                         "body": {k: v for k, v in m.items() if k != "machine"}}
                        for m in f["machines"] if m.get("machine") == self.machine]
        return out

    def drop(self):
        """A second stream under the machine's credential ends the uplink's
        (DX2: a new stream ends the previous one); the uplink reconnects and
        ends it in turn. A predicate: whether the uplink's newer stream is
        open, which the caller reads from its presence said again."""
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")) as f:
            cred = json.load(f)
        u = urllib.parse.urlsplit(self.url)
        c = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
        c.request("GET", "/machine/stream", headers={"CF-Access-Client-Id": cred["client_id"],
                                                     "CF-Access-Client-Secret": cred["client_secret"],
                                                     "Accept": "text/event-stream"})
        r = c.getresponse()
        assert r.status == 200, r.status
        r.fp.readline()  # its welcome: the uplink's stream is over
        c.close()
        return lambda: True


def make_hub(spawn):
    url = os.environ.get("DESK_HUB")
    return LocalHub(url) if url else StandinHub(spawn)


class Uplink(unittest.TestCase):
    """The plane on the uplink's stream, against the hub stand-in, or against
    DC3's local hub when DESK_HUB names its stand-in for Access."""

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
        cls.hub = make_hub(cls.spawn)
        sminos_cli = os.path.join(SCRIPTS, "sminos")
        cls.hub.enroll(sminos_cli)

        cls.root = os.path.join(T, "hp")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
        subprocess.run(git + ["init", "-q", cls.root], check=True)
        subprocess.run([sminos_cli, "project", "init", "--name", "hubproj"], cwd=cls.root, check=True,
                       capture_output=True)
        smns = os.path.join(cls.root, ".smns")
        d = json.loads(read(smns))
        d["hub"] = {"url": cls.hub.url, "org": cls.hub.org}
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
        cls.uplink = cls.spawn([sminos_cli, "daemon", "uplink"])
        cls.hub.follow(cls.project)
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
        if isinstance(cls.hub, LocalHub):
            cls.hub.close()
        for p in reversed(cls.procs):
            p.terminate()
        for p in cls.procs:
            p.wait(10)

    def tearDown(self):
        self.fake.stop_bridge()

    # ---------------------------------------------------- helpers

    def presences(self, ms):
        return [m["body"] for m in ms if m["kind"] == "presence" and m["session"] == self.sid]

    def reconnect(self):
        """Drops the stream; returns once the uplink is back with presence said again."""
        count = len(self.hub.messages())
        newer = self.hub.drop()
        ok = self.hub.wait(lambda ms: len(ms) > count and newer() and any(
            m["kind"] == "presence" and m["session"] == self.sid for m in ms[count:]), timeout=15)
        self.assertIsNotNone(ok, "the uplink reconnected and said presence again")

    def subscribe(self, agent=None):
        sub = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()  # DX3: 128 bits, base64url
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
                self.assertEqual((m["project"], m["machine"], m["session"]), (self.project, self.hub.machine, self.sid))
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
        self.assertIsNotNone(self.hub.wait(lambda ms: (self.presences(ms) or [{}])[-1].get("record") == {"status": "busy"},
                                           timeout=3), "said before the drop, so what follows it is the republish")
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

    def test_a3_stalled_bridges_do_not_hold_presence(self):
        """Three sessions whose bridges listen and never answer: another
        session's record changes still reach the hub within a second, each
        time, while their probes time out."""
        stalled = []
        os.makedirs(os.path.join(os.environ["SMINOS_HOME"], "bridge"), mode=0o700, exist_ok=True)
        try:
            for _ in range(3):
                holder = self.spawn(["sleep", "3600"])
                sid = new_session()
                with open(os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % holder.pid), "w") as f:
                    json.dump({"pid": holder.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive",
                               "status": "busy"}, f)
                sock = fake_session.stalled_socket(os.path.join(os.environ["SMINOS_HOME"], "bridge", sid + ".sock"))
                stalled.append((holder, sid, sock))
            ok = self.hub.wait(lambda ms: all(any(m["kind"] == "presence" and m["session"] == sid for m in ms)
                                              for _, sid, _ in stalled), timeout=5)
            self.assertIsNotNone(ok, "the stalled sessions are members")
            took = []
            for status in ("busy", "idle", "busy", "idle", "busy", "idle"):
                count = len(self.hub.messages())
                t0 = time.time()
                self.write_record({"status": status})
                got = self.hub.wait(lambda ms: {"status": status} in [
                    p["record"] for p in self.presences(ms[count:])], timeout=5)
                took.append(round(time.time() - t0, 2))
                self.assertIsNotNone(got)
                time.sleep(0.4)
            self.assertLess(max(took), 1.0, "every change within a second: %s" % took)
        finally:
            for holder, sid, sock in stalled:
                sock.close()
                os.unlink(os.path.join(os.environ["SMINOS_HOME"], "bridge", sid + ".sock"))
                holder.terminate()
                holder.wait(5)

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
        m.end()
        self.fake.usage(42)
        self.assertTrue(self.feed(b, lambda: b.usage and b.step_ends and len(b.rows) == len(self.fake.rows())))
        self.assertClean(b)
        self.assertEqual(b.step_ends, [(m.turn, None, 0)], "the step's end, relayed through the hub")
        self.assertLess(b.kinds.index("block-row"), b.kinds.index("step-end"))
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
        if isinstance(self.hub, StandinHub):
            # The stand-in shows what the machine posted: its end.
            self.assertTrue(self.feed(b, lambda: b.end is not None))
            self.assertEqual(b.end["reason"], "unsubscribed")
        else:
            # The hub drops the browser's route first, so the machine's end
            # reaches nobody (relay: a message for a sub nobody holds); the
            # sub falls silent while the session goes on.
            seen = b.seen
            self.fake.user_row("after the unsubscribe")
            self.feed(b, lambda: False, timeout=1.0)
            self.assertEqual(b.seen, seen, "nothing more for the sub")
        self.assertEqual(b.errors, [])

    def test_c_unknown_session(self):
        sub = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
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
        # The snapshot first: on a fresh endpoint the cut is null, and a row
        # flushed before the snapshot while its block still streams is the
        # null-cut case the composite's writer holds (it ends the sub).
        self.assertTrue(self.feed(b, lambda: b.snapshot is not None))
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
        main.end()
        sa.end()
        self.assertTrue(self.feed(after[0], lambda: len(after[0].step_ends) == 2))
        self.assertEqual(sorted(after[0].step_ends, key=str), sorted([(main.turn, None, 0), (sa.turn, "a7", 0)], key=str),
                         "a main sub carries every loop's step-end")
        self.feed(after[1], lambda: False, timeout=0.5)
        self.assertEqual(after[1].step_ends, [(sa.turn, "a7", 0)], "an agent sub its own")
        for b in after:
            self.assertEqual(b.errors, [])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
