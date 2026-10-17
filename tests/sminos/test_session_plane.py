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
        self.transcripts = plane.Transcripts()  # this test's own: what it builds is counted here

    def tearDown(self):
        for s in self.subs:
            s.close()
        self.fake.stop_bridge()

    def subscribe(self, agent=None, bridge=True, fake=None):
        fake = fake or self.fake
        reader = plane.BridgeReader(os.path.join(os.environ["SMINOS_HOME"], "bridge", fake.session + ".sock"),
                                    lambda: None) if bridge else None
        if reader is not None:
            reader.start()
        sub = plane.Subscription(project=PROJECT, machine="testhost", session=fake.session, agent=agent,
                                 sub="sub-%d" % len(self.subs), locate=lambda: fake.path(None), reader=reader,
                                 presence=lambda: {"record": {"status": "busy"}, "bridge": bridge},
                                 alive=lambda: self.alive, clock=self.clock, transcripts=self.transcripts)
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
                self.assertEqual(env["session"], sub.session)
                b.take(env)
            if until():
                return True
            time.sleep(0.01)
        return False

    def settle(self, sub, b, seconds=0.3):
        self.pump(sub, b, wait=seconds)

    def page(self, sub, b, before, limit):
        """A `rows` request: answered off the thread, on a later pump."""
        count = len(b.pages)
        self.assertEqual(sub.page(before, limit), [], "nothing at once: the page is read on the transcript's worker")
        self.assertTrue(self.pump(sub, b, lambda: len(b.pages) > count or b.end is not None), "the page came")
        self.assertIsNone(b.end)
        return b.pages[-1]

    def page_to_first(self, sub, b, limit=1000):
        """Pages from the snapshot's oldest row back to the first line: every
        row the snapshot did not hold, newest first."""
        older, before = [], b.snapshot["rows"][-1]["uuid"]
        while True:
            page = self.page(sub, b, before, limit)
            older += page["rows"]
            if not page["more"]:
                return older
            self.assertTrue(page["rows"], "a page that says more holds rows")
            before = page["rows"][-1]["uuid"]

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
        page = self.page(sub, b, oldest, 2)
        self.assertEqual(page["before"], oldest)
        self.assertEqual([r["uuid"] for r in page["rows"]], [ids[ids.index(oldest) - 1], ids[ids.index(oldest) - 2]])
        self.assertTrue(page["more"])
        page = self.page(sub, b, ids[1], 50)
        self.assertEqual([r["uuid"] for r in page["rows"]], [ids[0]])
        self.assertFalse(page["more"])
        self.assertEqual(self.page(sub, b, ids[0], 50), {"rows": [], "before": ids[0], "more": False},
                         "nothing before the first row")
        self.assertEqual(self.page(sub, b, "no-such-row", 50), {"rows": [], "before": "no-such-row", "more": False})
        self.assertEqual(b.errors, [])

    def test_pages_reach_the_first_row_on_a_live_session(self):
        """Paging from the newest row to the first line while the session
        runs, rows flushed after the open included: each page reads its own
        rows' bytes off the index."""
        pad = "x" * 100000
        ids = [self.fake.user_row("%d %s" % (i, pad), post=False) for i in range(15)]
        self.fake.write_row(None, {"type": "api-request", "body": {"messages": [{"uuid": "nested, no row"}]}})
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        held = [r["uuid"] for r in b.snapshot["rows"]]
        later = [self.fake.user_row("later %d" % i, post=False) for i in range(3)]
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == len(held) + 3), "flushed after the open: live rows")
        page = self.page(sub, b, later[2], 2)
        self.assertEqual([r["uuid"] for r in page["rows"]], [later[1], later[0]],
                         "a row flushed after the open is pageable")
        self.assertTrue(page["more"])
        page = self.page(sub, b, later[0], 1)
        self.assertEqual([r["uuid"] for r in page["rows"]], [ids[-1]], "and pages go on into what the open read")
        older = self.page_to_first(sub, b)
        self.assertEqual(list(reversed(held + [r["uuid"] for r in older])), ids, "every row, back to the first line")
        self.assertIsNone(b.end)
        self.assertEqual(b.errors, [])

    def test_a_second_subscription_builds_nothing(self):
        """One index per transcript file, shared: a second subscription on
        it, and one after both went (kept a while), parse nothing the first
        did not."""
        for i in range(40):
            self.fake.user_row("row %d" % i, post=False)
        first, b1 = self.subscribe(bridge=False)
        self.assertTrue(self.pump(first, b1, lambda: b1.snapshot is not None))
        index = self.transcripts.held[self.fake.path(None)].index
        parsed = index.parsed
        self.assertGreater(parsed, 0)
        second, b2 = self.subscribe(bridge=False)
        self.assertTrue(self.pump(second, b2, lambda: b2.snapshot is not None))
        self.assertEqual(b2.snapshot["rows"], b1.snapshot["rows"])
        self.assertEqual(index.parsed, parsed, "the second subscription built nothing")
        first.close()
        second.close()
        again, b3 = self.subscribe(bridge=False)
        self.assertTrue(self.pump(again, b3, lambda: b3.snapshot is not None))
        self.assertIs(self.transcripts.held[self.fake.path(None)].index, index, "kept after the last one went")
        self.assertEqual(index.parsed, parsed)
        self.fake.user_row("one more", post=False)
        self.assertTrue(self.pump(again, b3, lambda: len(b3.rows) == 41))
        self.page(again, b3, b3.rows[-1]["uuid"], 1)
        self.assertGreater(index.parsed, parsed, "extended by what was flushed since, only")
        self.assertLess(index.parsed, parsed + 1000)

    def test_a_replaced_or_shrunk_transcript_ends_its_subscriptions(self):
        for how in ("replaced", "shrunk"):
            with self.subTest(how=how):
                fake = fake_session.FakeSession(os.environ["HOME"], os.environ["SMINOS_HOME"], new_session())
                for i in range(4):
                    fake.user_row("%s %d" % (how, i), post=False)
                tailing, b1 = self.subscribe(bridge=False, fake=fake)
                paging, b2 = self.subscribe(bridge=False, fake=fake)
                for sub, b in ((tailing, b1), (paging, b2)):
                    self.assertTrue(self.pump(sub, b, lambda b=b: b.snapshot is not None))
                path = fake.path(None)
                if how == "replaced":
                    with open(path + ".new", "w") as f:
                        f.write(json.dumps({"type": "user", "uuid": "fresh", "message": {"content": "fresh"}}) + "\n")
                    os.replace(path + ".new", path)
                else:
                    with open(path, "r+") as f:
                        f.truncate(os.path.getsize(path) // 2)
                self.assertEqual(paging.page(b2.snapshot["rows"][0]["uuid"], 5), [])
                for sub, b in ((paging, b2), (tailing, b1)):
                    self.assertTrue(self.pump(sub, b, lambda b=b: b.end is not None))
                    self.assertEqual(b.end["reason"], "discontinuity")
                fresh, b3 = self.subscribe(bridge=False, fake=fake)
                self.assertTrue(self.pump(fresh, b3, lambda: b3.snapshot is not None))
                self.assertEqual([r["uuid"] for r in b3.snapshot["rows"]],
                                 [r["uuid"] for r in reversed(fake.rows())], "the file as it is now")

    def test_a_session_with_no_process_is_served_from_disk_and_pages(self):
        pad = "x" * 100000
        ids = [self.fake.user_row("%d %s" % (i, pad), post=False) for i in range(12)]
        self.alive = False
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.clock.advance(plane.END_GRACE + 0.1)
        self.settle(sub, b)
        self.assertIsNone(b.end, "no end: the subscription stays, idle")
        older = self.page_to_first(sub, b)
        self.assertEqual([r["uuid"] for r in reversed(older)] + b.uuids(), ids)
        b.take(sub.end("unsubscribed")[0])
        self.assertEqual(b.end["reason"], "unsubscribed")
        self.assertEqual(b.errors, [])

    def test_session_ended_only_for_a_transcript_not_held_here(self):
        self.alive = False
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual((b.end["reason"], b.n, b.snapshot), ("session-ended", 0, None),
                         "no process and no transcript: session-ended at n 0")
        self.fake.user_row("the main loop's", post=False)
        agent, b = self.subscribe(agent="a-none", bridge=False)
        self.assertTrue(self.pump(agent, b, lambda: b.end is not None))
        self.assertEqual((b.end["reason"], b.n), ("session-ended", 0), "the same for a subagent's transcript")
        self.alive = True
        sub, b = self.subscribe(agent="a-new", bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.snapshot["rows"], [], "a running session's transcript not written yet: an empty snapshot")
        self.fake.user_row("first", agent="a-new", post=False)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 1), "and its rows as they come")
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

    def test_a_resync_replaces_what_streams(self):
        """A gap drops a block's notice; the mod's resync carries its own
        copy of what streams (the live block's text so far, the settled one
        gone), and the next snapshot is that copy, not the child's stale
        partial text beside a row history already holds."""
        self.fake.start_bridge()
        self.fake.user_row("question")
        m = self.fake.message()
        m.text(0, "Hel")
        m.text(1, "draft")
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.blocks, {("turn-1", None, 0, 0): "Hel", ("turn-1", None, 0, 1): "draft"})
        self.fake.gap()
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")
        u = m.row(1, lost=True)  # its row flushed; the gap took its block-row
        m.text(0, "lo")
        self.fake.resync()
        again, b2 = self.subscribe()
        self.assertTrue(self.pump(again, b2, lambda: b2.snapshot is not None))
        self.assertEqual(b2.blocks, {("turn-1", None, 0, 0): "Hello"}, "the mod's copy: block 1 settled")
        self.assertIn(u, b2.uuids(), "its row in history, to the mod's cut")
        m.text(0, ", world")
        m.row(0)
        self.assertTrue(self.pump(again, b2, lambda: len(b2.rows) == len(self.fake.rows())))
        self.assertClean(b2)

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

    def test_a_session_that_ends_while_subscribed_stays_pageable(self):
        early = [self.fake.user_row("early %d %s" % (i, "x" * 100000), post=False) for i in range(8)]
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        last = self.fake.user_row("last", post=False)
        self.alive = False
        self.fake.stop_bridge()
        self.settle(sub, b)
        self.clock.advance(plane.END_GRACE + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: last in b.uuids()), "what flushed before the end is drawn")
        self.settle(sub, b)
        self.assertIsNone(b.end, "no end: the subscription stays, idle")
        self.assertFalse(sub.bridged, "transcript-only once the session is over")
        older = self.page_to_first(sub, b)
        self.assertEqual([r["uuid"] for r in reversed(older)] + b.uuids(), early + [last])
        self.assertEqual(b.errors, [])

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

    # ---------------------------------------------------- the worker, held

    def test_rows_flushed_during_the_build_and_after_its_offset(self):
        """The build held on its worker before it reads, while a response
        streams and its first block's row flushes (past the cut: read by the
        build, released live by its notice); then held after it read, while
        the next block's row and a user row flush past the offset it reached
        (read by the Tail). Every row once, in disk order, every block
        settled by its own row."""
        self.fake.start_bridge()
        self.fake.user_row("before")
        held = Held()
        with mock.patch.object(plane, "build", held):
            sub, b = self.subscribe()
            self.assertTrue(self.pump(sub, b, held.entered.is_set), "the build is asked once the bridge snapped")
            m = self.fake.message()
            m.text(0, "during ")
            m.text(0, "the build")
            during = m.row(0)
            m.text(1, "after ")
            held.go.set()
            self.assertTrue(held.built.wait(10))
            m.text(1, "the offset")
            after = m.row(1)
            tail = self.fake.user_row("past the offset")
            self.settle(sub, b)
            self.assertIsNone(b.snapshot, "nothing until the build's answer")
            held.deliver.set()
            self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == len(self.fake.rows())))
        self.assertIn(during, held.read, "the build read the row flushed while it waited")
        self.assertNotIn(after, held.read)
        self.assertEqual(b.uuids()[-3:], [during, after, tail])
        self.assertEqual(b.settled, {(m.turn, None, 0, 0), (m.turn, None, 0, 1)}, "both blocks settled by their rows")
        self.assertClean(b)

    def test_a_reset_between_the_build_and_its_answer(self):
        for how in ("replaced", "shrunk"):
            with self.subTest(how=how):
                fake = fake_session.FakeSession(os.environ["HOME"], os.environ["SMINOS_HOME"], new_session())
                old = [fake.user_row("%s %d" % (how, i), post=False) for i in range(5)]
                held = Held(go=True)
                with mock.patch.object(plane, "build", held):
                    sub, b = self.subscribe(bridge=False, fake=fake)
                    self.pump(sub, b, held.built.is_set)
                    self.assertTrue(held.built.is_set())
                    path = fake.path(None)
                    if how == "replaced":
                        with open(path + ".new", "w") as f:
                            for i in range(9):
                                f.write(json.dumps({"type": "user", "uuid": "new-%d" % i,
                                                    "message": {"content": "x" * 50}}) + "\n")
                        os.replace(path + ".new", path)
                    else:
                        with open(path, "r+") as f:
                            f.truncate(os.path.getsize(path) // 3)
                    held.deliver.set()
                    self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
                self.assertEqual(b.end["reason"], "discontinuity")
                self.assertEqual(b.uuids(), old, "the snapshot is the file the build read, and nothing of the new")
                self.assertEqual(b.errors, [])
                fresh, b2 = self.subscribe(bridge=False, fake=fake)
                self.assertTrue(self.pump(fresh, b2, lambda: b2.snapshot is not None))
                self.assertEqual(b2.uuids(), [r["uuid"] for r in fake.rows()], "a fresh one reads the file as it is")

    def test_a_second_subscription_extends_the_index_before_the_first_answer_is_taken(self):
        """The first subscription's build answered and not taken yet; a
        second one, on the same index, extends it past rows flushed since; the
        first then starts from its own build's offset: its Tail reads what
        the second's build already indexed, once."""
        first_rows = [self.fake.user_row("first %d" % i, post=False) for i in range(5)]
        first, b1 = self.subscribe(bridge=False)
        self.assertEqual(first.pump(), [], "asked, not answered")
        deadline = time.time() + 10
        while first.answers.empty() and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(first.answers.empty(), "the first build answered, untaken")
        between = [self.fake.user_row("between %d" % i, post=False) for i in range(4)]
        index = self.transcripts.held[self.fake.path(None)].index
        second, b2 = self.subscribe(bridge=False)
        self.assertTrue(self.pump(second, b2, lambda: b2.snapshot is not None))
        self.assertEqual(index.uuids, first_rows + between, "the second extended the shared index")
        later = self.fake.user_row("later", post=False)
        tailed = []
        real = plane.parse_rows
        with mock.patch.object(plane, "parse_rows", lambda lines: tailed.extend(lines) or real(lines)):
            self.assertTrue(self.pump(first, b1, lambda: len(b1.rows) == 10))
        self.assertEqual(len(tailed), 5, "the uplink's thread parsed only what flushed after its build's offset")
        self.assertEqual([r["uuid"] for r in reversed(b1.snapshot["rows"])], first_rows, "its own build's history")
        self.assertEqual(b1.uuids(), first_rows + between + [later], "then the rest, live, once each")
        self.assertTrue(self.pump(second, b2, lambda: len(b2.rows) == 10))
        self.assertEqual(b2.uuids(), first_rows + between + [later])
        for b in (b1, b2):
            self.assertEqual(b.errors, [])


class Held:
    """`plane.build` on the worker, held where a test opens it: before it
    reads (`entered`, released by `go`) and after (`built`, then `read`: the
    uuids it read; released by `deliver`)."""

    real = staticmethod(plane.build)

    def __init__(self, go=False):
        self.entered, self.go, self.built, self.deliver = (threading.Event() for _ in range(4))
        if go:
            self.go.set()
        self.read = []

    def __call__(self, t, cut, bridged):
        self.entered.set()
        assert self.go.wait(10), "never let go"
        answer = self.real(t, cut, bridged)
        self.read = list(t.index.uuids)
        self.built.set()
        assert self.deliver.wait(10), "never delivered"
        return answer


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


class TranscriptIndex(unittest.TestCase):
    """The offset index (DC8 M2): each row's uuid, byte offset and length in
    file order, extended from where it stopped; the transcripts kept a while
    after their last subscription."""

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(dir=T), "t.jsonl")

    def append(self, text):
        with open(self.path, "ab") as f:
            f.write(text.encode())

    def test_rows_in_file_order_with_their_spans(self):
        lines = [
            json.dumps({"type": "user", "uuid": "u1", "message": {"content": "é one"}}),
            json.dumps({"type": "api-request", "body": {"messages": [{"uuid": "nested, no row"}]}}),
            json.dumps({"toolUseResult": {"uuid": "nested-first"}, "type": "user", "uuid": "u2"}),
            json.dumps({"type": "cost-state", "uuid": 5}),
            "not json at all \"uuid\"",
            json.dumps({"type": "assistant", "uuid": "u3"}, ensure_ascii=False),
        ]
        self.append("\n".join(lines) + "\n" + '{"type": "user", "uuid": "u4", ')
        index = plane.Index(self.path)
        index.extend()
        self.assertEqual(index.uuids, ["u1", "u2", "u3"], "rows only, by their top-level uuid")
        with open(self.path, "rb") as f:
            data = f.read()
        self.assertEqual(index.end, data.rfind(b"\n") + 1, "through the last whole line")
        for i, u in enumerate(index.uuids):
            line = data[index.offsets[i]:index.offsets[i] + index.lengths[i]]
            self.assertEqual(json.loads(line)["uuid"], u, "the span is the row's line")
        self.assertEqual([r["uuid"] for r in index.rows(0, 3)], ["u1", "u2", "u3"])
        self.assertEqual([r["uuid"] for r in index.rows(1, 2)], ["u2"])
        parsed = index.parsed
        self.append('"message": {}}\n' + json.dumps({"type": "user", "uuid": "u5"}) + "\n")
        index.extend()
        self.assertEqual(index.uuids, ["u1", "u2", "u3", "u4", "u5"], "extended from where it stopped")
        self.assertEqual(index.at["u4"], 3)
        self.assertLess(index.parsed - parsed, 200, "only the new lines were parsed")

    def test_a_page_fits_the_budget_and_the_limit(self):
        pad = "x" * (plane.ROWS_BUDGET // 3)
        self.append("".join(json.dumps({"uuid": "r%d" % i, "pad": pad}) + "\n" for i in range(6)))
        index = plane.Index(self.path)
        index.extend()
        self.assertEqual(index.older(6, None), 4, "as many as fit the budget: two")
        self.assertEqual(index.older(6, 1), 5, "at most the limit")
        self.assertEqual(index.older(1, None), 0)
        self.append(json.dumps({"uuid": "huge", "pad": "y" * plane.ROWS_BUDGET}) + "\n")
        index.extend()
        self.assertEqual(index.older(7, None), 6, "at least one, however large")

    def test_replaced_shrunk_or_gone_resets(self):
        for how in ("replaced", "shrunk", "gone"):
            with self.subTest(how=how):
                self.append(json.dumps({"uuid": "a"}) + "\n" + json.dumps({"uuid": "b"}) + "\n")
                index = plane.Index(self.path)
                index.extend()
                if how == "replaced":
                    with open(self.path + ".new", "w") as f:
                        f.write(json.dumps({"uuid": "c"}) + "\n" * 40)
                    os.replace(self.path + ".new", self.path)
                elif how == "shrunk":
                    with open(self.path, "r+") as f:
                        f.truncate(3)
                else:
                    os.unlink(self.path)
                with self.assertRaises(plane.Reset):
                    index.extend()
                if os.path.exists(self.path):
                    os.unlink(self.path)
        index = plane.Index(self.path)
        index.extend()
        self.assertEqual((index.uuids, index.end), ([], 0), "a file not written yet is no reset")

    def test_kept_a_while_after_the_last_subscription(self):
        transcripts = plane.Transcripts(keep=2)
        held = [transcripts.acquire("/t/%d" % i) for i in range(4)]
        self.assertIs(transcripts.acquire("/t/0"), held[0], "shared while held")
        transcripts.release(held[0])
        for t in held:
            transcripts.release(t)
        self.assertEqual(list(transcripts.held), ["/t/2", "/t/3"], "the two released last are kept")
        self.assertIs(transcripts.acquire("/t/3"), held[3])
        self.assertIsNot(transcripts.acquire("/t/0"), held[0], "one evicted builds again")


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

    def ended_presence_project(self, name):
        """A project with one running member and one session that joined
        from here and ended: (project, running sid, ended sid)."""
        import sminos
        root = os.path.join(T, name)
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", root], check=True)
        subprocess.run([os.path.join(SCRIPTS, "sminos"), "project", "init", "--name", name], cwd=root,
                       check=True, capture_output=True)
        holders = {}
        for k in ("runs", "ended"):
            p, sid = subprocess.Popen(["sleep", "3600"]), new_session()
            rec = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % p.pid)
            holders[k] = (p, sid, rec)
            with open(rec, "w") as f:
                json.dump({"pid": p.pid, "sessionId": sid, "cwd": root, "kind": "interactive", "status": "idle"}, f)

        def cleanup():
            for p, _, rec in holders.values():
                if p.poll() is None:
                    p.terminate()
                    p.wait(5)
                if os.path.exists(rec):
                    os.unlink(rec)
        self.addCleanup(cleanup)
        sminos.forget_caches()
        project = sminos.resolve_project(root)
        sminos.view_of(project, titles=False)            # both join
        p, ended, rec = holders["ended"]
        p.terminate()
        p.wait(5)
        os.unlink(rec)
        sminos.forget_caches()
        sminos.view_of(project, titles=False)            # it retires, ended, while no stream is open
        return project, holders["runs"][1], ended

    @staticmethod
    def connect(project, wall=None):
        """A new stream's plane and the presence its connect says: (plane, {session: body})."""
        pl = plane.Plane("testhost", lambda: None)
        if wall is not None:
            pl.wall = wall
        pl.refresh(project)
        return pl, {m["session"]: m["body"] for m in pl.presence(project.id, force=True)}

    @staticmethod
    def marks():
        try:
            with open(plane.tombstone_path()) as f:
                return json.load(f)
        except OSError:
            return {}

    def test_a_first_connect_with_no_mark_says_every_session_that_ended_here(self):
        """The hub keeps each session's presence across connections with no
        expiry, and a new stream's plane has sent nothing: with no mark kept
        (a first run, an upgrade), every session that joined from here and
        is no member now is said as not running, however long ago it left;
        the mark is kept once the hub takes it, and the next connect says
        none that left before it."""
        project, runs, ended = self.ended_presence_project("ended-first")
        self.assertNotIn(project.id, self.marks())
        pl, got = self.connect(project, wall=lambda: time.time() + 30 * 86400)
        self.assertEqual(got.get(ended), {"record": None, "bridge": False}, "said as not running: %s" % got)
        self.assertEqual(got.get(runs), {"record": {"status": "idle"}, "bridge": False})
        self.assertNotIn(project.id, self.marks(), "no mark until the hub takes it")
        pl.accepted(project.id)
        self.assertIn(project.id, self.marks(), "kept once taken")
        _, got = self.connect(project, wall=lambda: time.time() + 31 * 86400)
        self.assertNotIn(ended, got, "a leaver the hub took is not said again")

    def test_an_outage_longer_than_a_week_still_says_who_ended_in_it(self):
        """The mark is the last connect the hub took, not a window: a session
        that ended after it is said on a connect eight days later."""
        project, _, ended = self.ended_presence_project("ended-outage")
        pl, _ = self.connect(project, wall=lambda: time.time() - 3600)
        pl.accepted(project.id)     # the last connect the hub took, an hour before the session ended
        _, got = self.connect(project, wall=lambda: time.time() + 8 * 86400)
        self.assertEqual(got.get(ended), {"record": None, "bridge": False}, "said, eight days on: %s" % got)

    def test_a_connect_the_hub_never_took_keeps_the_old_mark(self):
        """A reconnect whose POST fails before the hub takes its presence
        (Link.open, the hub answering 503) leaves the mark where it was, so
        the leavers it carried are said on the next connect."""
        import sminos_uplink as uplink
        project, _, ended = self.ended_presence_project("ended-unaccepted")
        old, _ = self.connect(project, wall=lambda: time.time() - 3600)
        old.accepted(project.id)
        mark = self.marks()[project.id]

        class Log:
            def __init__(self):
                self.project = project

            def rejoin_former(self):
                pass

            def unreported(self):
                return []

            def presence(self):
                return {"t": "session", "message": {"kind": "machine", "body": {}}}

            def hello(self):
                return {"t": "hello", "project": project.id}

            def reported(self, _):
                pass

        posted = []

        def refused(frames):
            posted.append(frames)
            raise uplink.NotDelivered("the hub answered 503")

        def link_of(post):
            link = uplink.Link({"machine": "testhost", "key": b"k" * 32, "hub": "http://127.0.0.1:9"}, {})
            link.plane.wall = lambda: time.time() + 3600
            link.post = post
            return link

        with self.assertRaises(uplink.NotDelivered):
            link_of(refused).open(Log())
        self.assertTrue(any(f.get("t") == "session" and f["message"].get("session") == ended
                            and f["message"]["body"] == {"record": None, "bridge": False}
                            for f in posted[0]), "the leaver was in the POST that failed")
        self.assertEqual(self.marks()[project.id], mark, "the mark stays where it was")
        _, got = self.connect(project, wall=lambda: time.time() + 7200)
        self.assertEqual(got.get(ended), {"record": None, "bridge": False}, "and the next connect says it again")
        link_of(posted.append).open(Log())
        self.assertGreater(self.marks()[project.id], mark, "taken: the mark moves")

    def test_the_daemon_sweeps_what_the_bridge_left_for_ended_sessions(self):
        """A session no process runs leaves its kept file once it has been
        quiet a day (neither its transcript nor the file touched), so a Resume soon after
        keeps its model choice; a socket nobody listens on goes with its
        session's end; a running session's files stay, however old."""
        import sminos
        import sminos_daemon as daemon
        d = os.path.join(os.environ["SMINOS_HOME"], "bridge")
        os.makedirs(d, exist_ok=True)
        old = time.time() - 2 * 86400
        holder = subprocess.Popen(["sleep", "60"])
        rec = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % holder.pid)
        try:
            ids = {k: new_session() for k in ("quiet", "recent", "kept-recently", "no-transcript", "running",
                                              "dead-socket")}
            with open(rec, "w") as f:
                json.dump({"pid": holder.pid, "sessionId": ids["running"], "status": "idle"}, f)
            transcripts = os.path.join(os.environ["HOME"], ".claude", "projects", "-sweep")
            os.makedirs(transcripts, exist_ok=True)
            for k in ("quiet", "recent", "kept-recently", "running"):
                t = os.path.join(transcripts, ids[k] + ".jsonl")
                with open(t, "w") as f:
                    f.write("{}\n")
                if k != "recent":
                    os.utime(t, (old, old))
            kept = {k: os.path.join(d, sid + ".json") for k, sid in ids.items() if k != "dead-socket"}
            for k, p in kept.items():
                with open(p, "w") as f:
                    json.dump({"override": {"model": "opus", "effort": None}, "delivered": {}}, f)
                if k != "kept-recently":
                    os.utime(p, (old, old))
            dead = os.path.join(d, ids["dead-socket"] + ".sock")
            fake_session.stalled_socket(dead).close()  # bound, then nobody listens
            self.assertTrue(os.path.exists(dead))
            sminos.forget_caches()
            daemon.sweep_bridges()
            self.assertEqual({k: os.path.exists(p) for k, p in kept.items()},
                             {"quiet": False, "recent": True, "kept-recently": True, "no-transcript": False,
                              "running": True})
            self.assertFalse(os.path.exists(dead), "a socket nobody listens on, of a session that ended")
        finally:
            holder.kill()
            holder.wait()
            os.unlink(rec)


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

    def subscribe(self, agent=None, session=None):
        sub = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()  # DX3: 128 bits, base64url
        session = session or self.sid
        self.hub.send({"t": "subscribe", "project": self.project, "session": session, "agentId": agent, "sub": sub})
        b = Browser()
        b.agent = agent
        b.sub = sub
        b.session = session
        b.seen = 0
        return b

    def feed(self, b, until, timeout=10.0):
        """Feeds the sub's messages to `b` until `until()` holds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            mine = [m for m in self.hub.messages() if m.get("sub") == b.sub]
            for m in mine[b.seen:]:
                self.assertEqual((m["project"], m["machine"], m["session"]),
                                 (self.project, self.hub.machine, b.session))
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

    def test_f_an_ended_session_stays_pageable_until_resume(self):
        """G2 through the hub: a session that ends while subscribed sends no
        `end`, is said not running within a second, pages back to its first
        line; Resume brings its bridge back, which ends the transcript-only
        subscription `discontinuity`, and a fresh one streams."""
        home, sh = os.environ["HOME"], os.environ["SMINOS_HOME"]
        sid = new_session()
        fake = fake_session.FakeSession(home, sh, sid)
        ids = [fake.user_row("%d %s" % (i, "x" * 100000), post=False) for i in range(12)]

        def run(status):
            holder = self.spawn(["sleep", "3600"])
            with open(os.path.join(home, ".claude", "sessions", "%d.json" % holder.pid), "w") as f:
                json.dump({"pid": holder.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive",
                           "status": status}, f)
            return holder

        def said(ms):
            return [m["body"] for m in ms if m["kind"] == "presence" and m["session"] == sid]

        holder = run("busy")
        self.assertIsNotNone(self.hub.wait(lambda ms: said(ms), timeout=5), "the session is a member")
        b = self.subscribe(session=sid)
        self.assertTrue(self.feed(b, lambda: b.snapshot is not None))
        last = fake.user_row("the last word", post=False)
        self.assertTrue(self.feed(b, lambda: last in b.uuids()))
        count = len(self.hub.messages())
        t0 = time.time()
        holder.terminate()
        holder.wait(5)
        self.assertIsNotNone(self.hub.wait(lambda ms: {"record": None, "bridge": False} in said(ms[count:]), timeout=5))
        self.assertLess(time.time() - t0, 1.0, "said not running within a second")
        self.feed(b, lambda: False, timeout=plane.END_GRACE + 1.0)
        self.assertIsNone(b.end, "no end once the session is over")
        older, before = [], b.snapshot["rows"][-1]["uuid"]
        while True:
            self.hub.send({"t": "rows", "project": self.project, "session": sid, "agentId": None, "sub": b.sub,
                           "before": before, "limit": 1000})
            count = len(b.pages)
            self.assertTrue(self.feed(b, lambda: len(b.pages) > count))
            older += b.pages[-1]["rows"]
            if not b.pages[-1]["more"]:
                break
            before = older[-1]["uuid"]
        self.assertEqual([r["uuid"] for r in reversed(older)] + b.uuids(), ids + [last], "back to the first line")
        resumed = run("idle")
        try:
            fake.start_bridge()
            self.assertTrue(self.feed(b, lambda: b.end is not None))
            self.assertEqual(b.end["reason"], "discontinuity", "Resume ends the transcript-only subscription")
            b2 = self.subscribe(session=sid)
            self.assertTrue(self.feed(b2, lambda: b2.snapshot is not None))
            m = fake.message()
            m.text(0, "after the resume")
            u = m.row(0)
            self.assertTrue(self.feed(b2, lambda: u in b2.uuids()), "the fresh one streams")
            self.assertEqual(b2.errors, [])
        finally:
            fake.stop_bridge()
            resumed.terminate()
            resumed.wait(5)
        self.assertEqual(b.errors, [])

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
