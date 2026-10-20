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

The reference consumer (dx4_consumer.Consumer) applies DX4 as the web does
and records every gap in `n`, duplicated row, chunk at or below its
watermark, block whose streamed text differs from its row, and block that
vanished before its row landed; StreamFixture holds it to dx4-stream.json.
Hermetic: HOME and SMINOS_HOME are temporary; nothing reaches beyond
127.0.0.1 and this directory.
"""

import base64
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
import types
import unittest
import urllib.parse
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts")
T = tempfile.mkdtemp(prefix="smp.", dir="/tmp")
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"), DAEMON_HOST="testhost",
                  CLAUDE_CODE_TMPDIR=os.path.join(T, "tmp"))   # the engine's temp root: `output` reads under it
for k in ("CLAUDE_CODE_SESSION_ID", "SMNS_INTERNAL", "DAEMON_HOME", "AGORA_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
os.makedirs(os.environ["SMINOS_HOME"])
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import bench_open  # noqa: E402
import dx4_consumer  # noqa: E402
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


def read(path):
    with open(path) as f:
        return f.read()


def new_session():
    return str(uuidlib.uuid4())


FIXTURE = json.load(open(os.path.join(HERE, "dx4-jobs.json"), encoding="utf-8"))


class Rows:
    """Transcript rows shaped as the engine writes them (2.1.300), cut down;
    each gets a uuid and the next second as its timestamp."""

    def __init__(self):
        self.i = 0

    def row(self, **fields):
        self.i += 1
        return {"uuid": str(uuidlib.uuid4()), "timestamp": "2026-10-17T10:%02d:%02d.000Z" % divmod(self.i, 60),
                **fields}

    def at(self):
        return "2026-10-17T10:%02d:%02d.000Z" % divmod(self.i, 60)

    def call(self, name, tid, **inp):
        return self.row(type="assistant", message={"role": "assistant", "content": [
            {"type": "tool_use", "id": tid, "name": name, "input": inp}]})

    def result(self, tid, tur=None, text="", is_error=False):
        block = {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}
        if is_error:
            block["is_error"] = True
        return self.row(type="user", message={"role": "user", "content": [block]}, toolUseResult=tur or {})

    def notification(self, task=None, tool=None, status=None, summary=None, output=None):
        parts = [("task-id", task), ("tool-use-id", tool), ("output-file", output), ("status", status),
                 ("summary", summary)]
        prompt = "<task-notification>\n%s\n</task-notification>" % "\n".join(
            "<%s>%s</%s>" % (k, v, k) for k, v in parts if v is not None)
        return self.row(type="attachment", attachment={"type": "queued_command", "prompt": prompt,
                                                       "commandMode": "task-notification"})

    def plugin_note(self, text):
        """A user row a plugin appended: kept isMeta with origin {kind: plugin}."""
        return self.row(type="user", isMeta=True, origin={"kind": "plugin", "name": "doperpowers"},
                        message={"role": "user", "content": [{"type": "text", "text": text}]})

    def task_status(self, task, status, path=None, kind="local_bash"):
        return self.row(type="attachment", attachment={"type": "task_status", "taskId": task, "taskType": kind,
                                                       "description": "", "status": status, "deltaSummary": None,
                                                       "outputFilePath": path})

    def mcp(self, added=(), removed=()):
        return self.row(type="attachment", attachment={"type": "mcp_instructions_delta", "addedNames": list(added),
                                                       "removedNames": list(removed)})


class Thread(Rows):
    """Rows chained as the engine writes them (2.1.300): each names the last
    one written as its parent, a tool result its issuing assistant (the
    engine's sourceToolAssistantUUID), unless the test names another — an
    Esc's or a /rewind's branch point."""

    def __init__(self, sidechain=False):
        super().__init__()
        self.leaf = None
        self.sidechain = sidechain

    def chained(self, row, parent=Ellipsis):
        row.update(parentUuid=self.leaf if parent is Ellipsis else parent, isSidechain=self.sidechain)
        self.leaf = row["uuid"]
        return row

    def prompt(self, text, parent=Ellipsis):
        return self.chained(self.row(type="user", message={"role": "user", "content": text}), parent)

    def attachment(self, kind="output_style", parent=Ellipsis):
        return self.chained(self.row(type="attachment", attachment={"type": kind}), parent)

    def answer(self, text, mid, parent=Ellipsis):
        return self.chained(self.row(type="assistant", message={"id": mid, "role": "assistant", "content": [
            {"type": "text", "text": text}]}), parent)

    def tool_call(self, tid, mid, parent=Ellipsis):
        return self.chained(self.row(type="assistant", message={"id": mid, "role": "assistant", "content": [
            {"type": "tool_use", "id": tid, "name": "Bash", "input": {}}]}), parent)

    def tool_result(self, tid, call):
        return self.chained(self.row(type="user", sourceToolAssistantUUID=call["uuid"], message={
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "ok"}]}), call["uuid"])

    def steer(self, text, parent=Ellipsis):
        """A row the bridge appended mid-turn (`$.session.append`): kept isMeta with the plugin's origin."""
        return self.chained(self.plugin_note(text), parent)

    def turn_end(self, parent=Ellipsis):
        return self.chained(self.row(type="system", subtype="turn_duration", durationMs=1000), parent)


def by_agent(body):
    """agentId → (status, evidence) of a widened `subagents` body."""
    return {e["agentId"]: (e["status"], e["evidence"]) for e in body["subagents"]}


def by_task(body):
    return {j["taskId"]: j for j in body["jobs"]}


class Session(unittest.TestCase):
    """What a Subscription test stands on: the scripted endpoint, a transcript
    the test writes, and a clock the test moves."""

    def setUp(self):
        self.sid = new_session()
        self.fake = fake_session.FakeSession(os.environ["HOME"], os.environ["SMINOS_HOME"], self.sid)
        self.clock = Clock()
        self.alive = True
        self.subs = []
        self.transcripts = plane.Transcripts()  # this test's own: what it builds is counted here
        self.disk = plane.Disk()                # and what its disk facts open

    def tearDown(self):
        for s in self.subs:
            s.close()
        self.fake.stop_bridge()

    def subscribe(self, agent=None, bridge=True, fake=None, clock=None, received=None):
        """A subscription on the test's clock, which stands for the wall
        clock too: the subscribe's arrival (`received`, by default now) and
        the reader's stamps read it."""
        fake = fake or self.fake
        clock = clock or self.clock
        reader = plane.BridgeReader(os.path.join(os.environ["SMINOS_HOME"], "bridge", fake.session + ".sock"),
                                    lambda: None, stamp=clock) if bridge else None
        if reader is not None:
            reader.start()
        sub = plane.Subscription(project=PROJECT, machine="testhost", session=fake.session, agent=agent,
                                 sub="sub-%d" % len(self.subs), locate=lambda: fake.path(None), reader=reader,
                                 presence=lambda: {"record": {"status": "busy"}, "bridge": bridge},
                                 alive=lambda: self.alive, clock=clock, transcripts=self.transcripts,
                                 disk=self.disk, received=received, wall=clock)
        self.subs.append(sub)
        return sub, dx4_consumer.Consumer(agent)

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
        mine = {k: v for k, v in b.texts().items() if k[1] == agent}
        self.assertEqual(mine, {}, "no partial text left beside its row")


class Engine(Session):
    """The Subscription, with the scripted endpoint and a clock the test moves."""

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
        self.assertEqual(s["subagents"], [{"agentId": "a1", "meta": {"agentType": "x"}, "status": "unknown",
                                           "evidence": "none"}],
                         "a meta with no toolUseId and no spawn record: unknown, one of §9.3's named cases")
        self.assertEqual((s["jobs"], s["mcp"]), ([], []))
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
        self.assertEqual(self.page(sub, b, ids[0], 50), {"rows": [], "before": ids[0], "more": False, "offChain": []},
                         "nothing before the first row")
        self.assertEqual(self.page(sub, b, "no-such-row", 50), {"rows": [], "before": "no-such-row", "more": False,
                                                                "offChain": []})
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
        self.assertEqual(b.uuids(), ids, "the pages held before the snapshot's rows")
        self.assertEqual([r["uuid"] for r in reversed(older)], ids[:len(older)])
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
        self.assertEqual(b.texts(), {("turn-1", None, 0, 0): "Hel"}, "the partial text from the snapshot")
        m.text(0, "lo, ")
        m.text(0, "world")
        m.row(0)
        m.text(1, "more")
        m.row(1)
        self.fake.user_row("tool result")
        self.fake.usage(1234)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == 4 and b.usage))
        self.assertClean(b)
        inventory = dx4_consumer.Inventory.from_sources(self.fake.path(None), self.fake.emitted)
        self.assertEqual(set(inventory.blocks), {(m.turn, None, 0, 0), (m.turn, None, 0, 1)}, "both blocks streamed")
        self.assertEqual(inventory.check(b), {"holes": [], "partial": [], "vanished": [], "dups": [], "undrawn": [],
                                              "residual": []})
        self.assertLess(b.kinds.index("block-row"), b.kinds.index("row"), "a block-row before its row")
        # Each live chunk carries the bridge's stamp through, for the web's chunk-to-drawn latency.
        self.assertEqual(b.stamps, [1760000000000 + i for i in (1, 2, 3)], "the bridge's stamps, passed through")
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
                self.assertTrue(self.pump(sub, b, lambda: b.texts().get((m.turn, agent, 0, 1)) == "second block"))
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
                self.assertEqual({k: v for k, v in b.texts().items() if k[1] == agent},
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
        self.assertEqual(b.texts(), {("turn-1", None, 0, 0): "Hel", ("turn-1", None, 0, 1): "draft"})
        self.fake.gap()
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(b.end["reason"], "discontinuity")
        u = m.row(1, lost=True)  # its row flushed; the gap took its block-row
        m.text(0, "lo")
        self.fake.resync()
        again, b2 = self.subscribe()
        self.assertTrue(self.pump(again, b2, lambda: b2.snapshot is not None))
        self.assertEqual(b2.texts(), {("turn-1", None, 0, 0): "Hello"}, "the mod's copy: block 1 settled")
        self.assertIn(u, b2.uuids(), "its row in history, to the mod's cut")
        m.text(0, ", world")
        m.row(0)
        self.assertTrue(self.pump(again, b2, lambda: len(b2.rows) == len(self.fake.rows())))
        self.assertClean(b2)

    def opens_said(self, sub):
        """daemon.log's lines for this subscription's open."""
        try:
            with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
                return [line for line in f if "plane: open %s of %s:" % (sub.sub, sub.session[:8]) in line]
        except OSError:
            return []

    def test_each_open_is_said_once_with_the_wait_that_ended_it(self):
        """One daemon.log line an open: subscribe to snapshot (or to its end
        before one), and which wait ended it, so a slow Resume's open can be
        read off the machine."""
        self.fake.user_row("hello", post=False)
        plain, b = self.subscribe(bridge=False)
        self.clock.advance(0.25)
        self.assertTrue(self.pump(plain, b, lambda: b.snapshot is not None))
        self.settle(plain, b)
        said = self.opens_said(plain)
        self.assertEqual(len(said), 1, said)
        self.assertIn("transcript-only (no bridge socket) after 0.25 s from the subscribe's arrival "
                      "(no bridge; build: cold %d ms 1 rows, cut null; waits 0)" % plain.cpu_ms, said[0])
        self.fake.start_bridge()
        bridged, b2 = self.subscribe()
        self.assertTrue(self.pump(bridged, b2, lambda: b2.snapshot is not None))
        self.settle(bridged, b2)
        said = self.opens_said(bridged)
        self.assertEqual(len(said), 1, said)
        self.assertIn(": bridge snapshot after", said[0])
        self.assertRegex(said[0], r"\(bridge: snapshot arrived \d+\.\d\d s, taken \d+\.\d\d s; "
                                  r"build: warm \d+ ms 1 rows, cut on disk; waits 0\)$")
        # The cut's row not on disk yet: each build that answered "waiting" is counted.
        m = self.fake.message()
        m.text(0, "late")
        u = m.row(0, disk=False)
        late, b4 = self.subscribe()
        self.assertTrue(self.pump(late, b4, lambda: late.waits >= 1))
        m.write(0, u)
        self.assertTrue(self.pump(late, b4, lambda: b4.snapshot is not None))
        said = self.opens_said(late)
        self.assertEqual(len(said), 1, said)
        self.assertRegex(said[0], r"; build: warm \d+ ms 2 rows, cut on disk; waits [1-9]\d*\)$")
        m.end()
        self.fake.stop_bridge()
        self.fake.start_bridge(ready=False)
        waiting, b3 = self.subscribe()
        self.settle(waiting, b3)
        self.clock.advance(plane.OPEN_WAIT + 1)
        self.assertTrue(self.pump(waiting, b3, lambda: b3.end is not None))
        self.assertEqual(b3.end["reason"], "discontinuity")
        said = self.opens_said(waiting)
        self.assertEqual(len(said), 1, said)
        self.assertIn("timeout: the bridge sent no snapshot in %g s after %.2f s from the subscribe's arrival "
                      "(bridge: no snapshot; build: none, cut null; waits 0)" % (plane.OPEN_WAIT, plane.OPEN_WAIT + 1),
                      said[0])

    def test_an_open_that_ends_waiting_for_its_cut_says_its_builds(self):
        """The line of an open that ended before its snapshot, its cut's row
        never on disk: the builds that answered "waiting" are said whole —
        how the first came, their CPU together, the rows the last indexed."""
        self.fake.user_row("before", post=False)
        self.fake.start_bridge()
        m = self.fake.message()
        m.text(0, "never flushed")
        u = m.row(0, disk=False)
        sub, b = self.subscribe(received=self.clock() - 0.5)
        self.assertTrue(self.pump(sub, b, lambda: sub.waits >= 2), "builds asked, and asked again")
        self.clock.advance(plane.NOTICE_WAIT + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: b.end is not None))
        self.assertEqual(sub.build_how, "cold")
        said = [line.split(" ", 1)[1] for line in self.opens_said(sub)]
        self.assertEqual(said, ["plane: open %s of %s: discontinuity before its snapshot: the snapshot's cut, row %s, "
                                "never reached the transcript after %.2f s from the subscribe's arrival (bridge: "
                                "snapshot arrived 0.50 s, taken 0.50 s; build: cold %d ms 1 rows, cut not on disk; "
                                "waits %d)\n" % (sub.sub, sub.session[:8], u, 0.5 + plane.NOTICE_WAIT + 0.1, sub.cpu_ms,
                                                   sub.waits)])
        m.end()

    def test_the_open_line_says_where_the_time_went(self):
        """§5's line, pinned whole: N from the subscribe frame's arrival at
        the reader (`received`), the bridge's snapshot's arrival (A) and when
        the open took it (M), how the build came, its CPU and rows, whether
        the cut's row was on disk, the waits."""
        for i in range(3):
            self.fake.user_row("before %d" % i, post=False)
        self.fake.start_bridge()
        sub, b = self.subscribe(received=self.clock() - 0.5)
        deadline = time.time() + 5
        while sub.reader.items.empty() and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(sub.reader.items.empty(), "the bridge's snapshot is in the reader's queue")
        self.clock.advance(0.25)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        said = [line.split(" ", 1)[1] for line in self.opens_said(sub)]   # past daemon.log's stamp
        self.assertEqual(said, ["plane: open %s of %s: bridge snapshot after 0.75 s from the subscribe's arrival "
                                "(bridge: snapshot arrived 0.50 s, taken 0.75 s; build: cold %d ms 3 rows, cut on disk; "
                                "waits 0)\n" % (sub.sub, sub.session[:8], sub.cpu_ms)])

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
        self.assertEqual(b.uuids(), early + [last], "the pages held before the snapshot's rows")
        self.assertEqual([r["uuid"] for r in reversed(older)], early[:len(older)])
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
        self.assertEqual((b.snapshot["rows"], b.texts()), ([], {(m.turn, None, 0, 0): "raced"}))
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
        [entry] = b.snapshot["subagents"]
        self.assertEqual({k: entry[k] for k in ("agentId", "meta", "status", "evidence")},
                         {"agentId": "a1", "meta": {"agentType": "worker"}, "status": "unknown", "evidence": "none"},
                         "that agent's own entry alone")
        self.assertEqual(entry["file"]["size"], os.path.getsize(self.fake.path("a1")))
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
        self.assertNotIn(("turn-1", None, 0, 0), b.texts())

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
        self.assertEqual(b.texts(), {})
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


class OffChain(Session):
    """The live chain on a subscription: the snapshot and its pages mark the
    rows off it, and a row that starts a branch takes off, live, the rows the
    desk already drew — a prompt sent again after an Esc, a steer under an
    undone turn — while the rows of a parallel call stay on."""

    def write(self, rows, agent=None, seen=False):
        for r in rows:
            self.fake.write_row(agent, r)
            if seen:
                self.fake.seen(r["uuid"], agent)
        return rows

    def undone_turn(self, t):
        """A turn the session ran — a parallel call, a steer appended while
        it ran — and its end; the branch point an Esc goes back to first."""
        rows = [t.prompt("hello"), t.answer("hi", "m0"), t.turn_end()]
        end = rows[-1]
        prompt = t.prompt("check both files")
        a, b = t.tool_call("toolu_a", "m1"), t.tool_call("toolu_b", "m1")
        steer = t.steer("and the third one")
        ra, rb = t.tool_result("toolu_a", a), t.tool_result("toolu_b", b)
        turn = [prompt, a, b, steer, ra, rb, t.answer("both fine", "m2")]
        return rows, end, turn, steer

    def test_a_snapshot_and_its_pages_mark_the_rows_off_the_chain(self):
        t = Thread()
        before, end, turn, steer = self.undone_turn(t)
        pad = "x" * 200000
        again = t.prompt("check both files " + pad, parent=end["uuid"])   # sent again: a branch
        later = [t.answer("checking", "m3")] + [t.prompt("next %d %s" % (i, pad)) for i in range(3)]
        self.write(before + turn + [again] + later)
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertTrue(b.snapshot["more"], "older rows left to page: the undone turn is among them")
        self.assertEqual(b.snapshot["offChain"], [], "the newest rows are all on the chain")
        older = self.page_to_first(sub, b)
        off = [u for p in b.pages for u in p["offChain"]]
        self.assertEqual(sorted(off), sorted(r["uuid"] for r in turn), "the undone turn, steer and all, marked off")
        self.assertTrue(steer["uuid"] in b.off)
        self.assertTrue(older)
        self.assertEqual(b.uuids(), [r["uuid"] for r in before + turn + [again] + later], "every row still sent")
        self.assertEqual(b.errors, [])

    def test_a_snapshot_marks_a_rewound_prompt_and_keeps_parallel_results_on(self):
        t = Thread()
        before, end, turn, steer = self.undone_turn(t)
        live = [t.turn_end()]
        first = t.prompt("fix it")
        hook = t.attachment()
        again = t.prompt("fix it", parent=live[-1]["uuid"])   # Esc before the answer; sent again
        self.write(before + turn + live + [first, hook, again, t.answer("fixed", "m4")])
        sub, b = self.subscribe(bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertFalse(b.snapshot["more"])
        self.assertEqual(sorted(b.snapshot["offChain"]), sorted([first["uuid"], hook["uuid"]]),
                         "the first copy and what it held; the parallel results and the steer stay on")
        self.assertEqual(b.drawn(), [r["uuid"] for r in before + turn + live + [again]] + [b.uuids()[-1]])
        self.assertEqual(b.errors, [])

    def test_a_live_rewind_takes_off_what_the_desk_drew(self):
        """Through the bridge's release order, each row released by its own
        notice: the turn goes out row by row with nothing off, the parallel
        results included; the prompt sent again carries the retraction."""
        t = Thread()
        before, end, turn, steer = self.undone_turn(t)
        self.write(before)
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.write(turn, seen=True)
        self.assertTrue(self.pump(sub, b, lambda: len(b.rows) == len(before + turn)))
        self.assertEqual((b.off, b.marked), (set(), {}), "a live turn, its parallel results and its steer: nothing off")
        self.assertEqual(b.drawn(), [r["uuid"] for r in before + turn])
        again = t.prompt("check both files", parent=end["uuid"])
        self.write([again], seen=True)
        self.assertTrue(self.pump(sub, b, lambda: again["uuid"] in b.uuids()))
        self.assertEqual(b.marked, {again["uuid"]: ([r["uuid"] for r in turn], [])},
                         "the row that starts the branch carries what it took off, oldest first")
        self.assertIn(steer["uuid"], b.off, "the steer under the undone turn among it")
        self.assertEqual(b.drawn(), [r["uuid"] for r in before] + [again["uuid"]])
        self.settle(sub, b)
        self.assertClean(b)
        self.assertIsNone(b.end)

    def test_rows_past_the_cut_carry_their_own_marks(self):
        """The build reads past the cut: a row it found off the chain goes out
        marked off, the branch that took it off with nothing to say again."""
        t = Thread()
        before, end, turn, steer = self.undone_turn(t)
        self.write(before)
        self.fake.start_bridge()                 # its seed, the cut: the last row of `before`
        again = t.prompt("check both files", parent=end["uuid"])
        self.write(turn + [again])               # on disk past the cut, noticed after the snapshot
        sub, b = self.subscribe()
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        for r in turn + [again]:
            self.fake.seen(r["uuid"])
        self.assertTrue(self.pump(sub, b, lambda: again["uuid"] in b.uuids()))
        self.assertEqual(b.marked, {r["uuid"]: ([r["uuid"]], []) for r in turn}, "each marks itself off")
        self.assertEqual(b.drawn(), [r["uuid"] for r in before] + [again["uuid"]])
        self.assertEqual(b.errors, [])

    def test_an_agents_transcript_has_its_own_chain(self):
        t = Thread(sidechain=True)
        rows = [t.prompt("the brief"), t.tool_call("toolu_1", "m1")]
        result = t.tool_result("toolu_1", rows[-1])
        dropped = t.answer("handing back", "m2")
        note = t.chained(t.row(type="user", isMeta=True, isSidechain=True,
                               message={"role": "user", "content": "a message reached the turn"}), result["uuid"])
        self.write(rows + [result, dropped, note], agent="a1")
        self.fake.meta("a1", {"agentType": "worker"})
        sub, b = self.subscribe(agent="a1", bridge=False)
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None))
        self.assertEqual(b.snapshot["offChain"], [dropped["uuid"]], "the response the engine dropped")
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
                self.assertTrue(self.pump(again, b2, lambda: b2.texts().get((new.turn, agent, 0, 0)) == "fresh"))
                new.row(0)
                self.assertTrue(self.pump(again, b2, lambda: len(b2.rows) == len(self.fake.rows(agent))))
                self.assertIn(u, b2.uuids())
                self.assertClean(b2, agent)
                self.fake.stop_bridge()
                sub.close()
                again.close()


class Jobs(Session):
    """What the session runs (DC8 M4; DX4 "Jobs and agent status" and
    `output`): the widened `subagents` body derived from the rows the
    subscription parses, the bridge's agent state and the disk facts, sent
    in the snapshot and whenever it changes; `output` answered off the
    uplink's thread."""

    def write(self, *rows, agent=None, fake=None):
        for row in rows:
            (fake or self.fake).write_row(agent, row)
        return rows[-1]["uuid"]

    def meta_path(self, agent, fake=None):
        fake = fake or self.fake
        return os.path.join(fake.dir, fake.session, "subagents", "agent-%s.meta.json" % agent)

    def look(self, sub, b, until, wait=3.0):
        """Pumps with the clock moved past METAS_EVERY each time, so the disk
        facts are looked at again, until `until()` holds."""
        deadline = time.time() + wait
        while time.time() < deadline:
            self.clock.advance(plane.METAS_EVERY)
            for env in sub.pump():
                b.take(env)
            if until():
                return True
            time.sleep(0.01)
        return False

    def quiet(self, sub, b):
        """Pumps, the clock still, until no look at the disk is in flight."""
        self.assertTrue(self.pump(sub, b, lambda: not sub.looking))

    def opened(self, sub, b):
        self.assertTrue(self.pump(sub, b, lambda: b.snapshot is not None or b.end is not None))
        self.assertIsNone(b.end)
        return b.snapshot

    def entry(self, body, agent):
        return next(e for e in body["subagents"] if e["agentId"] == agent)

    # ---------------------------------------------------- the shared fixture

    def test_the_shared_fixtures_bodies_through_the_plane(self):
        """Every body case of dx4-jobs.json, its files written where the
        engine writes them and its bridge state served by the endpoint, comes
        out of the plane's own snapshot as the fixture says."""
        for i, case in enumerate(FIXTURE["cases"]):
            with self.subTest(case=case["name"]):
                inp, want = case["input"], json.loads(json.dumps(case["expect"]))
                fake = fake_session.FakeSession(os.environ["HOME"], os.environ["SMINOS_HOME"], inp["session"]["id"],
                                                project_dir="fixture-%d" % i)
                fake.real, fake.child_env = self.fake.real, self.fake.child_env
                self.write(*inp["main"], fake=fake)
                for k, m in enumerate(inp["metas"]):
                    fake.meta(m["agentId"], m["meta"])
                    ns = (1700000000 + k) * 10 ** 9   # the metas' order is their files' mtime order
                    os.utime(self.meta_path(m["agentId"], fake), ns=(ns, ns))
                for agent, f in inp["agentFiles"].items():
                    if f is None:
                        continue
                    self.write(*f["rows"], agent=agent, fake=fake)
                    path = fake.path(agent)
                    pad = f["size"] - os.path.getsize(path) - len('{"pad": ""}\n')
                    if pad >= 0:   # a record that is no row, to the fixture's size
                        with open(path, "a") as out:
                            out.write('{"pad": "%s"}\n' % ("x" * pad))
                    else:
                        for e in want["subagents"]:
                            if e["agentId"] == agent and "file" in e:
                                e["file"]["size"] = os.path.getsize(path)
                    ns = int(f["mtimeMs"] * 10 ** 6)
                    os.utime(path, ns=(ns, ns))
                bridged = inp["bridge"] is not None
                if bridged:
                    fake.agents = inp["bridge"]["agents"]
                    fake.start_bridge()
                self.alive = inp["session"]["running"]
                try:
                    sub, b = self.subscribe(bridge=bridged, fake=fake)
                    snap = self.opened(sub, b)
                    for part in ("subagents", "jobs", "mcp"):
                        self.assertEqual(snap[part], want[part], part)
                finally:
                    fake.stop_bridge()

    # ---------------------------------------------------- agents

    def test_agents_that_ran_before_the_bridge_loaded(self):
        """The module reloaded mid-session: no `agent` event for what ran
        before, the snapshot's agents seeded from $.agent.list(); then a spawn
        and a stop the module sees."""
        r = Rows()
        self.write(r.call("Agent", "toolu_done", description="done before", run_in_background=True),
                   r.result("toolu_done", {"status": "async_launched", "agentId": "adone"}),
                   r.notification(task="adone", tool="toolu_done", status="completed", summary="finished"),
                   r.call("Agent", "toolu_fg", description="still running"),
                   r.call("Agent", "toolu_gone", description="stopped without a word"))
        for agent, tid in (("adone", "toolu_done"), ("afg", "toolu_fg"), ("agone", "toolu_gone")):
            self.fake.meta(agent, {"agentType": "general-purpose", "toolUseId": tid})

        def seed(agent, running):
            return {"agentId": agent, "parentAgentId": None, "subagentType": "general-purpose",
                    "description": agent, "running": running}

        self.fake.agents = [seed("adone", False), seed("afg", True), seed("agone", False)]
        self.fake.start_bridge()
        sub, b = self.subscribe()
        snap = self.opened(sub, b)
        self.assertEqual(by_agent(snap), {"adone": ("completed", "rows"), "afg": ("running", "bridge"),
                                          "agone": ("exited", "bridge")})
        afg = self.entry(snap, "afg")
        self.assertEqual((afg["running"], afg["spawn"]), (True, {"parentAgentId": None,
                                                                 "subagentType": "general-purpose",
                                                                 "description": "afg"}),
                         "a seeded spawn carries what the list gives")
        self.assertEqual(self.entry(snap, "adone")["outcome"]["summary"], "finished")

        self.fake.meta("anew", {"agentType": "x", "toolUseId": "toolu_new"})
        self.fake.agent("spawn", "anew", parentAgentId=None, subagentType="x", description="new", name="n",
                        background=False, model="m", toolUseId="toolu_new")
        self.assertTrue(self.look(sub, b, lambda: by_agent(b.body).get("anew") == ("running", "bridge")))
        self.assertEqual(self.entry(b.body, "anew")["spawn"],
                         {"parentAgentId": None, "subagentType": "x", "description": "new", "name": "n",
                          "background": False, "model": "m", "toolUseId": "toolu_new"})
        count = len(b.changes)
        self.fake.agent("stop", "afg", agentType="general-purpose")
        self.assertTrue(self.pump(sub, b, lambda: by_agent(b.body)["afg"] == ("exited", "bridge")))
        self.assertEqual(len(b.changes), count + 1, "one `subagents` message for the change")
        self.settle(sub, b)
        self.assertEqual(len(b.changes), count + 1, "nothing more while nothing changes")
        self.assertEqual(b.errors, [])

    def test_nested_agents_from_their_parents_transcript(self):
        """A nested agent's outcome is in its parent's file, read as a disk
        fact; its parent ending ends it."""
        r = Rows()
        self.write(r.call("Agent", "toolu_P", description="parent"))
        self.write(r.row(type="user", message={"role": "user", "content": "the brief"}),
                   r.call("Agent", "toolu_N1", description="one"), r.call("Agent", "toolu_N2", description="two"),
                   agent="aP")
        self.fake.meta("aP", {"toolUseId": "toolu_P"})
        self.fake.meta("aN1", {"toolUseId": "toolu_N1", "parentAgentId": "aP"})
        self.fake.meta("aN2", {"toolUseId": "toolu_N2", "parentAgentId": "aP"})
        self.fake.agents = [{"agentId": a, "parentAgentId": p, "subagentType": "x", "description": a, "running": True}
                            for a, p in (("aP", None), ("aN1", "aP"), ("aN2", "aP"))]
        self.fake.start_bridge()
        sub, b = self.subscribe()
        snap = self.opened(sub, b)
        self.assertEqual(by_agent(snap), {a: ("running", "bridge") for a in ("aP", "aN1", "aN2")})
        self.assertEqual(self.entry(snap, "aP")["file"]["firstAt"], "2026-10-17T10:00:02.000Z")

        self.write(r.result("toolu_N1", {"status": "completed"}, "done"), agent="aP")
        self.assertTrue(self.look(sub, b, lambda: by_agent(b.body)["aN1"] == ("completed", "rows")),
                        "the nested agent's result, from its parent's transcript")
        self.assertEqual(self.entry(b.body, "aN1")["outcome"], {"status": "completed", "raw": "completed",
                                                               "at": r.at()})
        self.assertEqual(self.entry(b.body, "aP")["file"]["lastAt"], r.at())

        self.write(r.result("toolu_P", {"status": "completed"}, "parent done"))
        self.assertTrue(self.pump(sub, b, lambda: by_agent(b.body)["aP"] == ("completed", "rows")))
        self.assertEqual(by_agent(b.body)["aN2"], ("exited", "parent"),
                         "a nested agent with no word of its own ends with its parent, over the bridge's running")
        self.assertEqual(b.errors, [])

    # ---------------------------------------------------- jobs and MCP

    def test_background_jobs_started_before_the_subscription(self):
        r = Rows()
        tasks = os.path.join(T, "tmp", "claude-0", "x", self.fake.session, "tasks")
        calls = {}

        def started(name, tid, tur, text="", **inp):
            call = r.call(name, tid, **inp)
            calls[tid] = call["timestamp"]
            return [call, r.result(tid, tur, text)]

        self.write(*started("Bash", "toolu_b1", {"backgroundTaskId": "b1"},
                            "Command running in background with ID: b1. Output is being written to: %s/b1.output"
                            % tasks, command="make watch", description="Watch the build", run_in_background=True),
                   *started("Monitor", "toolu_m1", {"taskId": "m1", "timeoutMs": 1800000, "persistent": False},
                            "Monitor started", description="Watch the log", command="tail -f log"),
                   *started("Bash", "toolu_b2", {"backgroundTaskId": "b2"},
                            "Output is being written to: %s/b2.output" % tasks, command="sleep 600",
                            run_in_background=True),
                   *started("Bash", "toolu_b3", {"backgroundTaskId": "b3"},
                            "Output is being written to: %s/b3.output" % tasks, command="sleep 900",
                            run_in_background=True),
                   r.mcp(added=["github", "linear"]))
        sub, b = self.subscribe(bridge=False)
        snap = self.opened(sub, b)
        self.assertEqual(by_task(snap)["b1"], {"taskId": "b1", "kind": "shell", "toolUseId": "toolu_b1",
                                               "startedAt": calls["toolu_b1"], "description": "Watch the build",
                                               "command": "make watch", "outputFile": tasks + "/b1.output",
                                               "status": "running"})
        self.assertEqual(by_task(snap)["m1"], {"taskId": "m1", "kind": "monitor", "toolUseId": "toolu_m1",
                                               "startedAt": calls["toolu_m1"], "description": "Watch the log",
                                               "command": "tail -f log", "outputFile": None, "status": "running"},
                         "a monitor names no file at its start")
        self.assertEqual(snap["mcp"], [{"name": "github"}, {"name": "linear"}])

        def after(*rows, until):
            count = len(b.changes)
            self.write(*rows)
            self.assertTrue(self.pump(sub, b, lambda: until(by_task(b.body))))
            self.assertEqual(len(b.changes), count + 1)

        after(r.notification(task="b1", tool="toolu_b1", status="completed", summary="exit 0",
                             output=tasks + "/b1.output"),
              until=lambda j: j["b1"]["status"] == "completed")
        self.assertEqual((by_task(b.body)["b1"]["endedAt"], by_task(b.body)["b1"]["summary"]), (r.at(), "exit 0"))
        after(r.task_status("m1", "running", tasks + "/m1.output", kind="monitor"),
              until=lambda j: j["m1"]["outputFile"] == tasks + "/m1.output")
        self.assertEqual(by_task(b.body)["m1"]["status"], "running")
        after(r.call("TaskStop", "toolu_stop", task_id="m1"),
              r.result("toolu_stop", {"message": "Successfully stopped task: m1"}, "stopped"),
              until=lambda j: j["m1"]["status"] == "stopped")
        self.assertEqual(by_task(b.body)["m1"]["summary"], "Successfully stopped task: m1")
        after(r.task_status("b2", "failed"), until=lambda j: j["b2"]["status"] == "failed")
        count = len(b.changes)
        self.write(r.mcp(removed=["github"]))
        self.assertTrue(self.pump(sub, b, lambda: b.body["mcp"] == [{"name": "linear"}]))
        self.assertEqual(by_task(b.body)["b3"]["status"], "running")
        self.alive = False
        self.assertTrue(self.pump(sub, b, lambda: by_task(b.body)["b3"]["status"] == "exited"),
                        "a job still running when the process goes has exited")
        self.assertEqual(len(b.changes), count + 2)
        self.assertEqual(b.errors, [])

    # ---------------------------------------------------- timing and liveness

    def test_a_status_reaches_subagents_within_a_second_of_its_evidence(self):
        """DC8.G3's bound, on the clock: evidence on the bridge's stream, in
        the main transcript, in a parent's transcript (a disk fact), and the
        process gone."""
        r = Rows()
        self.write(r.call("Agent", "toolu_A", description="a"),
                   r.call("Agent", "toolu_B", description="b", run_in_background=True),
                   r.result("toolu_B", {"status": "async_launched"}),
                   r.call("Agent", "toolu_P", description="p"), r.call("Agent", "toolu_C", description="c"))
        self.write(r.call("Agent", "toolu_N", description="n"), agent="aP")
        metas = (("aA", "toolu_A", None), ("aB", "toolu_B", None), ("aP", "toolu_P", None), ("aN", "toolu_N", "aP"),
                 ("aC", "toolu_C", None))
        for agent, tid, parent in metas:
            self.fake.meta(agent, {"toolUseId": tid, **({"parentAgentId": parent} if parent else {})})
        self.fake.agents = [{"agentId": a, "parentAgentId": p, "running": True} for a, _, p in metas]
        self.fake.start_bridge()
        sub, b = self.subscribe(clock=time.monotonic)
        self.assertEqual(set(by_agent(self.opened(sub, b)).values()), {("running", "bridge")})

        def timed(evidence, agent, want):
            t0 = time.monotonic()
            evidence()
            self.assertTrue(self.pump(sub, b, lambda: by_agent(b.body)[agent] == want, wait=3.0), agent)
            self.assertLess(time.monotonic() - t0, 1.0, "%s reached `subagents` within a second" % agent)

        timed(lambda: self.fake.agent("stop", "aA"), "aA", ("exited", "bridge"))
        timed(lambda: self.write(r.notification(task="aB", tool="toolu_B", status="completed")), "aB",
              ("completed", "rows"))
        timed(lambda: self.write(r.result("toolu_N", {"status": "completed"}), agent="aP"), "aN", ("completed", "rows"))
        timed(lambda: setattr(self, "alive", False), "aC", ("exited", "session"))
        self.assertEqual(b.errors, [])

    def test_a_cold_open_and_a_live_one_reach_the_same_statuses(self):
        """Cold (a subscribe to the ended session) and live (open while it
        ended) agree: every entry is derived again when the process goes."""
        r = Rows()
        self.write(r.call("Agent", "toolu_A", description="a"),
                   r.call("Agent", "toolu_B", description="b", run_in_background=True),
                   r.result("toolu_B", {"status": "async_launched"}),
                   r.call("Agent", "toolu_C", description="c", run_in_background=True),
                   r.result("toolu_C", {"status": "async_launched"}),
                   r.notification(task="aC", tool="toolu_C", status="completed"),
                   r.call("Agent", "toolu_P", description="p"), r.call("Agent", "toolu_D", description="d"))
        self.write(r.call("Agent", "toolu_N", description="n"), agent="aP")
        metas = (("aA", "toolu_A", None), ("aB", "toolu_B", None), ("aC", "toolu_C", None), ("aP", "toolu_P", None),
                 ("aN", "toolu_N", "aP"), ("aD", "toolu_D", None))
        for agent, tid, parent in metas:
            self.fake.meta(agent, {"toolUseId": tid, **({"parentAgentId": parent} if parent else {})})
        self.fake.agents = [{"agentId": a, "parentAgentId": p, "running": a != "aD"} for a, _, p in metas]
        self.fake.start_bridge()
        sub, b = self.subscribe()
        self.opened(sub, b)
        self.assertEqual(by_agent(b.body)["aA"], ("running", "bridge"))
        self.alive = False
        self.fake.stop_bridge()
        self.assertTrue(self.pump(sub, b, lambda: "running" not in {s for s, _ in by_agent(b.body).values()}))
        self.clock.advance(plane.END_GRACE + 0.1)
        self.settle(sub, b)
        live = by_agent(b.body)
        self.assertEqual(live, {"aA": ("exited", "session"), "aB": ("exited", "session"),
                                "aC": ("completed", "rows"), "aP": ("exited", "session"),
                                "aN": ("exited", "session"), "aD": ("exited", "session")})
        self.assertNotIn("running", self.entry(b.body, "aA"), "the bridge's running stops counting")
        cold, cb = self.subscribe(bridge=False)
        self.assertEqual(by_agent(self.opened(cold, cb)), live)
        self.assertEqual(b.errors + cb.errors, [])

    # ---------------------------------------------------- an agent's subscription

    def test_a_job_the_bridge_stopped_reads_stopped_from_its_note_the_main_loops_and_a_subagents(self):
        """DC10: a plugin's TaskStop writes no row, so the bridge's note in the
        main loop's rows is the word: it ends a main-loop job on the main
        subscription, and a subagent's job on that agent's subscription, whose
        own rows hear of it only at the agent's next tool batch."""
        r = Rows()
        self.write(r.call("Agent", "toolu_A", description="a", run_in_background=True),
                   r.result("toolu_A", {"status": "async_launched"}),
                   r.call("Bash", "toolu_bm", command="main's", run_in_background=True),
                   r.result("toolu_bm", {"backgroundTaskId": "bm"}))
        self.write(r.row(type="user", message={"role": "user", "content": "the brief"}),
                   r.call("Monitor", "toolu_ma", command="agent's"),
                   r.result("toolu_ma", {"taskId": "ma", "timeoutMs": 1, "persistent": False}), agent="aA")
        self.fake.meta("aA", {"toolUseId": "toolu_A", "requestShape": "background"})
        main, mb = self.subscribe(bridge=False)
        self.assertEqual(by_task(self.opened(main, mb))["bm"]["status"], "running")
        sa, ab = self.subscribe(agent="aA", bridge=False)
        self.assertEqual(by_task(self.opened(sa, ab))["ma"]["status"], "running")
        self.write(r.plugin_note("Task bm, a background task, was stopped from the desk: it is not running."),
                   r.plugin_note("Task ma, a background task, was stopped from the desk: it is not running."))
        self.assertTrue(self.look(main, mb, lambda: by_task(mb.body)["bm"]["status"] == "stopped"))
        self.assertTrue(self.look(sa, ab, lambda: by_task(ab.body)["ma"]["status"] == "stopped"),
                        "the agent's job, from the main loop's note")
        self.assertNotIn("ma", by_task(mb.body), "a subagent's job is not the main loop's")

    def test_an_agents_subscription_carries_its_own_entry_and_jobs(self):
        """Two derivations: its entry from its parent loop's rows, its jobs and
        MCP names from its own."""
        r = Rows()
        self.write(r.call("Agent", "toolu_A", description="a", run_in_background=True),
                   r.result("toolu_A", {"status": "async_launched"}),
                   r.call("Bash", "toolu_bm", command="main's", run_in_background=True),
                   r.result("toolu_bm", {"backgroundTaskId": "bm"}))
        self.write(r.row(type="user", message={"role": "user", "content": "the brief"}),
                   r.call("Bash", "toolu_ba", command="agent's", run_in_background=True),
                   r.result("toolu_ba", {"backgroundTaskId": "ba"}), r.mcp(added=["sentry"]),
                   r.call("Agent", "toolu_N", description="n"), r.call("Agent", "toolu_N2", description="n2"),
                   agent="aA")
        self.write(r.row(type="user", message={"role": "user", "content": "n's brief"}), agent="aN")
        self.write(r.row(type="user", message={"role": "user", "content": "n2's brief"}), agent="aN2")
        self.fake.meta("aA", {"toolUseId": "toolu_A", "requestShape": "background"})
        self.fake.meta("aN", {"toolUseId": "toolu_N", "parentAgentId": "aA"})
        self.fake.meta("aN2", {"toolUseId": "toolu_N2", "parentAgentId": "aA"})
        main, mb = self.subscribe(bridge=False)
        self.assertEqual([j["taskId"] for j in self.opened(main, mb)["jobs"]], ["bm"], "the main loop's jobs alone")
        self.assertEqual(mb.snapshot["mcp"], [])

        sa, ab = self.subscribe(agent="aA", bridge=False)
        snap = self.opened(sa, ab)
        [entry] = snap["subagents"]
        self.assertEqual({k: entry[k] for k in ("agentId", "status", "evidence", "outcome")},
                         {"agentId": "aA", "status": "running", "evidence": "rows",
                          "outcome": {"status": "running", "raw": "async_launched", "at": "2026-10-17T10:00:02.000Z"}},
                         "its entry from the main loop's rows")
        self.assertEqual(entry["file"]["size"], os.path.getsize(self.fake.path("aA")))
        self.assertEqual([j["taskId"] for j in snap["jobs"]], ["ba"], "its own loop's jobs")
        self.assertEqual(snap["mcp"], [{"name": "sentry"}])

        sn, nb = self.subscribe(agent="aN", bridge=False)
        sn2, n2b = self.subscribe(agent="aN2", bridge=False)
        self.assertEqual(by_agent(self.opened(sn, nb)), {"aN": ("unknown", "none")},
                         "no bridge and no outcome yet in its parent's rows")
        self.assertEqual(by_agent(self.opened(sn2, n2b)), {"aN2": ("unknown", "none")})
        self.write(r.result("toolu_N", {"status": "completed"}, "n done"), agent="aA")
        self.assertTrue(self.look(sn, nb, lambda: by_agent(nb.body) == {"aN": ("completed", "rows")}),
                        "a nested agent's entry from its parent's transcript")
        self.write(r.notification(task="aA", tool="toolu_A", status="completed"))
        self.assertTrue(self.look(sa, ab, lambda: by_agent(ab.body) == {"aA": ("completed", "rows")}))
        self.assertTrue(self.look(sn2, n2b, lambda: by_agent(n2b.body) == {"aN2": ("exited", "parent")}),
                        "its parent ended: the chain is derived")
        self.assertEqual(ab.errors + nb.errors + n2b.errors, [])

    # ---------------------------------------------------- the disk, looked at

    def test_an_unchanged_check_stats_the_agent_files_and_reads_none(self):
        r = Rows()
        self.write(r.row(type="user", message={"role": "user", "content": "go"}))
        agents = ["a%03d" % k for k in range(150)]
        for agent in agents:
            self.write(r.row(type="user", message={"role": "user", "content": "brief"}),
                       r.row(type="assistant", message={"role": "assistant", "content": [{"type": "text",
                                                                                          "text": "x" * 2000}]}),
                       agent=agent)
            self.fake.meta(agent, {"agentType": "worker", "toolUseId": "toolu_" + agent})
        sub, b = self.subscribe(bridge=False)
        snap = self.opened(sub, b)
        self.assertEqual(len(snap["subagents"]), 150)
        self.assertTrue(all("file" in e for e in snap["subagents"]))
        self.quiet(sub, b)
        opened, looks = self.disk.opened, sub.looks
        self.assertEqual(opened, 300, "the open read each meta and each agent file once")
        self.assertTrue(self.look(sub, b, lambda: sub.looks >= looks + 3))
        self.quiet(sub, b)
        self.assertEqual(self.disk.opened, opened, "an unchanged check opens nothing: each file is stat'ed")

        self.write(r.row(type="user", message={"role": "user", "content": "more"}), agent="a007")
        self.fake.meta("a042", {"agentType": "reviewer", "toolUseId": "toolu_a042"})
        looks = sub.looks
        self.assertTrue(self.look(sub, b, lambda: sub.looks >= looks + 3))
        self.quiet(sub, b)
        self.assertEqual(self.disk.opened, opened + 2, "a changed file is read again, nothing else")
        self.assertEqual(self.entry(b.body, "a007")["file"]["lastAt"], r.at())
        self.assertEqual(self.entry(b.body, "a042")["meta"]["agentType"], "reviewer")

    # ---------------------------------------------------- output

    def test_output_on_a_live_and_an_ended_subscription(self):
        r = Rows()
        sid = self.fake.session
        root = os.path.join(os.path.realpath(os.environ["CLAUDE_CODE_TMPDIR"]), "claude-%d" % os.getuid(), "proj", sid,
                            "tasks")
        elsewhere = os.path.join(T, "elsewhere", sid, "tasks")
        for d, name, text in ((root, "b1.output", "line one\nline two\n"), (elsewhere, "b3.output", "not this\n")):
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        for task, d in (("b1", root), ("b2", root), ("b3", elsewhere)):
            self.write(r.call("Bash", "toolu_" + task, command="run " + task, run_in_background=True),
                       r.result("toolu_" + task, {"backgroundTaskId": task},
                                "Output is being written to: %s/%s.output" % (d, task)))
        self.write(r.call("Monitor", "toolu_m1", description="watch"), r.result("toolu_m1", {"taskId": "m1"}))
        sub, b = self.subscribe(bridge=False)
        self.opened(sub, b)

        def ask(task, tail=65536):
            count = len(b.outputs)
            self.assertEqual(sub.output(task, tail, []), [], "nothing at once: read on the transcript's worker")
            self.assertTrue(self.pump(sub, b, lambda: len(b.outputs) > count))
            return b.outputs[-1]

        self.assertEqual(ask("b1"), {"taskId": "b1", "result": "ok", "path": root + "/b1.output", "size": 18,
                                     "from": 0, "text": "line one\nline two\n", "truncated": False},
                         "under the root of the transcript's project directory")
        self.assertEqual(ask("b1", tail=10), {"taskId": "b1", "result": "ok", "path": root + "/b1.output",
                                              "size": 18, "from": 9, "text": "line two\n", "truncated": True})
        self.assertEqual(ask("m1"), {"taskId": "m1", "result": "missing", "path": None})
        self.assertEqual(ask("b2"), {"taskId": "b2", "result": "missing", "path": root + "/b2.output"})
        refused = ask("b3")
        self.assertEqual((refused["result"], refused["path"]), ("refused", elsewhere + "/b3.output"))
        self.assertTrue(refused["reason"].strip())
        self.assertEqual(ask("nope"), {"taskId": "nope", "result": "unknown-task"})

        self.alive = False
        self.settle(sub, b)
        self.clock.advance(plane.END_GRACE + 0.1)
        self.assertTrue(self.pump(sub, b, lambda: sub.over))
        with open(os.path.join(root, "m1.output"), "w") as f:
            f.write("event\n")
        self.write(r.task_status("m1", "running", root + "/m1.output", kind="monitor"))
        self.assertTrue(self.pump(sub, b, lambda: by_task(b.body)["m1"]["outputFile"] == root + "/m1.output"))
        self.assertEqual(ask("m1"), {"taskId": "m1", "result": "ok", "path": root + "/m1.output", "size": 6,
                                     "from": 0, "text": "event\n", "truncated": False},
                         "an idle subscription answers too, once a row names the file")
        self.assertIsNone(b.end)
        self.assertEqual(b.errors, [])

    def test_an_output_frame_out_of_form_is_passed_by(self):
        r = Rows()
        self.write(r.call("Monitor", "toolu_m1", description="watch"), r.result("toolu_m1", {"taskId": "m1"}))
        sub, b = self.subscribe(bridge=False)
        self.opened(sub, b)
        p = plane.Plane("testhost", lambda: None, transcripts=self.transcripts, disk=self.disk)
        p.subs[sub.sub] = sub
        for task, tail in (("m 1", 10), ("x" * 65, 10), (7, 10), ("m1", 0), ("m1", 524289), ("m1", True),
                           ("m1", "10")):
            self.assertEqual(p.output({"sub": sub.sub, "taskId": task, "tail": tail}), [])
        self.assertEqual(p.output({"sub": "another", "taskId": "m1", "tail": 10}), [])
        self.settle(sub, b)
        self.assertEqual(b.outputs, [], "nothing answered a frame out of form")
        self.assertEqual(p.output({"sub": sub.sub, "taskId": "m1", "tail": 524288}), [])
        self.assertTrue(self.pump(sub, b, lambda: b.outputs))
        self.assertEqual(b.outputs, [{"taskId": "m1", "result": "missing", "path": None}])
        p.subs.clear()


class RealChildJobs(Jobs):
    """Every jobs case again, the bridge being the real child: its snapshot's
    `agents` as the mod's resync gave them, its `agent` events folded as it
    folds them (DC8 M3)."""

    def setUp(self):
        super().setUp()
        self.fake.real = True
        self.fake.child_env = {"SMINOS_BRIDGE_READY_WAIT": str(fake_session.READY_HOLD)}


class Roots(unittest.TestCase):
    """`output`'s canonical roots, derived from the machine's own state (DC8's
    Decision Log): one per slug, under the engine's per-uid temp root."""

    def test_the_engines_slug(self):
        self.assertEqual(plane.engine_slug("/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/sminos-family"),
                         "-Users-new-Developer-GitHub-doperpowers--claude-worktrees-sminos-family")
        # Past 200 characters (UTF-16 units), cut and the original's base-36 hash added (node, the engine's j0):
        self.assertEqual(plane.engine_slug("/Users/new/" + "x" * 210 + "/é😀"),
                         "-Users-new-" + "x" * 189 + "-xnssi")

    def test_one_root_per_slug(self):
        sid = new_session()
        base = os.path.join(os.path.realpath(os.environ["CLAUDE_CODE_TMPDIR"]), "claude-%d" % os.getuid())
        main = "/h/.claude/projects/-w-repo--claude-worktrees-x/%s.jsonl" % sid
        self.assertEqual(plane.output_roots(sid, main, ["/w/repo", "/w/repo/.claude/worktrees/x", "", None]),
                         [os.path.join(base, slug, sid, "tasks")
                          for slug in ("-w-repo--claude-worktrees-x", "-w-repo")],
                         "the transcript's project directory, then each working directory's slug, once each")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_TMPDIR": ""}):
            self.assertEqual(plane.output_roots(sid, main, []),
                             [os.path.join(os.path.realpath("/tmp"), "claude-%d" % os.getuid(),
                                           "-w-repo--claude-worktrees-x", sid, "tasks")])


class ParentLoop(unittest.TestCase):
    """A parent loop's ledger read off disk (Loop) parses only what an agent's
    outcome reads, and gives every agent the outcome the whole ledger gives."""

    def test_its_views_agree_with_the_whole_ledger(self):
        r, path = Rows(), os.path.join(tempfile.mkdtemp(dir=T), "agent-p.jsonl")
        rows = [r.call("Bash", "toolu_sh", command="make", run_in_background=True),
                r.result("toolu_sh", {"backgroundTaskId": "b1"}, "Output is being written to: /x/b1.output"),
                r.call("Read", "toolu_read", file_path="/x"), r.result("toolu_read", {}, "x" * 5000),
                r.call("Agent", "toolu_a", description="done"), r.result("toolu_a", {"status": "completed"}, "ok"),
                r.call("Agent", "toolu_b", description="bg", run_in_background=True),
                r.result("toolu_b", {"status": "async_launched"}),
                r.call("TaskStop", "toolu_stop", task_id="ab"),
                r.result("toolu_stop", {"message": "Successfully stopped task: ab"}, "stopped"),
                r.call("Agent", "toolu_c", description="c", run_in_background=True),
                r.result("toolu_c", {"status": "async_launched"}),
                r.task_status("ac", "failed", kind="local_agent"),
                r.call("Agent", "toolu_d", description="d", run_in_background=True),
                r.result("toolu_d", {"status": "async_launched"}),
                r.row(type="user", origin={"kind": "task-notification"}, message={"role": "user", "content":
                      "<task-notification>\n<task-id>ad</task-id>\n<status>killed</status>\n</task-notification>"}),
                r.call("Agent", "toolu_e", description="e")]
        with open(path, "w") as f:
            f.writelines(json.dumps(row) + "\n" for row in rows)
        whole = plane.jobs.Ledger()
        whole.feed(rows)
        cases = list(zip(["aa", "ab", "ac", "ad", "ae"], ["toolu_a", "toolu_b", "toolu_c", "toolu_d", "toolu_e"],
                         (False, True, True, True, False)))
        disk = plane.Disk()
        view = disk.view(path, [c[0] for c in cases], [c[1] for c in cases])
        for agent, tool, background in cases:
            self.assertEqual(view.agent_outcome(agent, tool, background),
                             whole.agent_outcome(agent, tool, background), agent)
        self.assertEqual([(view.agent_outcome(*c) or {}).get("status") for c in cases],
                         ["completed", "stopped", "failed", "stopped", None])
        loop = disk.get(("loop", path))
        self.assertNotIn("toolu_read", loop.ledger.calls, "a call no agent's outcome reads is not parsed")
        self.assertEqual(loop.ledger.jobs, {}, "nor are the loop's jobs kept")


def wait_file(path, timeout=10):
    deadline = time.time() + timeout
    while not (os.path.exists(path) and read(path)) and time.time() < deadline:
        time.sleep(0.05)
    return read(path)


def dechunked(raw):
    """An HTTP/1.1 response's chunked body as far as it came, its framing taken off."""
    body = raw.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in raw else b""
    out = b""
    while b"\r\n" in body:
        size, rest = body.split(b"\r\n", 1)
        n = int(size, 16)
        out += rest[:n]
        if n == 0 or len(rest) < n + 2:
            break
        body = rest[n + 2:]
    return out


class Instruments(unittest.TestCase):
    """The fixtures the open's instruments stand on: the hub stand-in on
    HTTP/1.1, each POST recorded with its connection and each session
    message with its arrival; and the pause proxy, which stops the hub's
    stream to the uplink on its first `events` frame while every other
    connection passes."""

    CRED = {"CF-Access-Client-Id": "cid-1", "CF-Access-Client-Secret": "secret-1"}

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        port_file = os.path.join(T, "instruments-hub.port")
        cls.procs.append(subprocess.Popen([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1",
                                           "secret-1", "2000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        cls.hub = "http://127.0.0.1:%s" % wait_file(port_file)
        proxy_file = os.path.join(T, "instruments-proxy.json")
        cls.procs.append(subprocess.Popen([sys.executable, os.path.join(HERE, "pause_proxy.py"), cls.hub, proxy_file],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        ports = json.loads(wait_file(proxy_file))
        cls.proxy = "http://127.0.0.1:%d" % ports["proxy"]
        cls.control = "http://127.0.0.1:%d" % ports["control"]

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.terminate()
            p.wait(10)

    def open_stream(self, base):
        """GET /machine/stream at `base` on a socket of its own; (socket, the
        bytes read up to the welcome, its generation)."""
        u = urllib.parse.urlsplit(base)
        sock = socket.create_connection((u.hostname, u.port), timeout=5)
        sock.sendall(("GET /machine/stream HTTP/1.1\r\nHost: %s\r\nCF-Access-Client-Id: cid-1\r\n"
                      "CF-Access-Client-Secret: secret-1\r\nAccept: text/event-stream\r\n\r\n" % u.netloc).encode())
        got = b""
        while True:
            got += sock.recv(65536)
            for line in got.split(b"\n"):
                if line.startswith(b"data: ") and b'"t": "welcome"' in line:
                    return sock, got, json.loads(line[len(b"data: "):])["generation"]

    def test_a_keep_alive_connection_keeps_its_id(self):
        """Two POSTs on one http.client connection carry one `conn`; a third
        on a fresh connection another."""
        state = lambda: call(self.hub, "GET", "/control/state")[1]  # noqa: E731
        count = len(state()["posted"])
        u = urllib.parse.urlsplit(self.hub)
        c = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
        for _ in range(2):
            c.request("POST", "/machine/frames", body=b'{"t":"hb-ack"}\n',
                      headers={**self.CRED, "X-Desk-Generation": "999"})
            r = c.getresponse()
            r.read()
            self.assertEqual(r.status, 409, "no stream of that generation")
            self.assertFalse(r.will_close, "HTTP/1.1: the connection stays open")
        c.close()
        call(self.hub, "POST", "/machine/frames", None, {**self.CRED, "X-Desk-Generation": "999"})
        posted = state()["posted"][count:]
        self.assertEqual(len(posted), 3)
        self.assertEqual(posted[0]["conn"], posted[1]["conn"], "one keep-alive connection, one id")
        self.assertNotEqual(posted[1]["conn"], posted[2]["conn"], "a new connection, a new id")

    def test_a_session_message_carries_its_arrival(self):
        sock, _, generation = self.open_stream(self.hub)
        try:
            t0 = time.time()
            message = {"project": PROJECT, "machine": "testhost", "session": new_session(), "kind": "presence",
                       "sub": None, "n": None, "body": {"record": None, "bridge": False}}
            u = urllib.parse.urlsplit(self.hub)
            c = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
            c.request("POST", "/machine/frames", body=json.dumps({"t": "session", "message": message}).encode(),
                      headers={**self.CRED, "X-Desk-Generation": str(generation)})
            r = c.getresponse()
            r.read()
            c.close()
            self.assertEqual(r.status, 200)
            got = [m for m in call(self.hub, "GET", "/control/state")[1]["sessions"] if m["message"] == message]
            self.assertEqual(len(got), 1)
            self.assertLessEqual(t0, got[0]["at"])
            self.assertLessEqual(got[0]["at"], time.time())
        finally:
            sock.close()

    def test_the_proxy_pauses_the_stream_on_its_first_events_frame(self):
        """Armed, the proxy forwards the stream's first `events` frame, then
        reads nothing more of that connection for the seconds asked and says
        `paused` with what it held back; another connection passes meanwhile;
        then `resumed`, and what was held arrives."""
        sock, _, _ = self.open_stream(self.proxy)
        try:
            status, armed = call(self.control, "POST", "/control/arm", {"on": "next-events", "seconds": 1.5})
            self.assertEqual((status, armed["state"]), (200, "armed"))
            frames = [{"t": "events", "project": PROJECT, "writer": "w", "events": [], "mark": "first"},
                      {"t": "events", "project": PROJECT, "writer": "w", "events": [], "mark": "held " + "x" * 2000}]
            status, sent = call(self.hub, "POST", "/control/send", {"frames": frames})
            self.assertEqual(status, 200, sent)
            got = b""
            sock.settimeout(5)
            while b'"mark": "first"' not in got:
                got += sock.recv(65536)
            sock.settimeout(0.5)
            try:
                more = sock.recv(65536)
            except OSError:   # socket.timeout
                more = b""
            self.assertNotIn(b'"mark": "held', got + more, "nothing past the first events frame while paused")
            status, st = call(self.control, "GET", "/control/state")
            self.assertEqual(st["state"], "paused", st)
            self.assertGreater(st["held"], 2000, "what the proxy holds back of the hub's writes")
            status, _ = call(self.proxy, "GET", "/control/state")
            self.assertEqual(status, 200, "another connection passes while the stream is paused")
            sock.settimeout(5)
            rest = got + more
            while b'"mark": "held' not in rest:
                rest += sock.recv(65536)
            status, st = call(self.control, "GET", "/control/state")
            self.assertEqual(st["state"], "resumed", st)
            self.assertGreaterEqual(st["resumed_at"] - st["paused_at"], 1.4, "paused for the seconds asked")
        finally:
            sock.close()

    def test_the_proxy_pauses_now_and_resumes_on_ask(self):
        sock, _, _ = self.open_stream(self.proxy)
        try:
            status, armed = call(self.control, "POST", "/control/arm", {"on": "now", "seconds": 30})
            self.assertEqual(status, 200)
            deadline = time.time() + 5
            while call(self.control, "GET", "/control/state")[1]["state"] != "paused" and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(call(self.control, "GET", "/control/state")[1]["state"], "paused")
            call(self.hub, "POST", "/control/send", {"frames": [{"t": "ping", "mark": "after now"}]})
            status, _ = call(self.control, "POST", "/control/resume", {})
            self.assertEqual(status, 200)
            got = b""
            sock.settimeout(5)
            while b'"mark": "after now"' not in got:
                got += sock.recv(65536)
            self.assertEqual(call(self.control, "GET", "/control/state")[1]["state"], "resumed")
        finally:
            sock.close()

    def test_the_proxy_finds_an_events_frame_in_a_chunked_stream(self):
        """The local hub's stream is chunked, and its runtime splits a
        frame's JSON across chunks (`{"t":` in one, `"events",…` in the
        next): the proxy reads the body through the chunked framing, so it
        still pauses right after the first events frame, which it forwards
        whole."""
        frames = [b'event: hb\ndata: {"t":"hb"}\n\n',
                  b'event: events\ndata: {"t":"events","project":"p","events":[],"mark":"first"}\n\n',
                  b'event: events\ndata: {"t":"events","project":"p","events":[],"mark":"held"}\n\n']
        pieces = []
        for f in frames:
            k = f.index(b'"t":') + 4      # where the runtime cut it
            pieces += [f[:k], f[k:-1], f[-1:]]
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        go = threading.Event()

        def hub():
            conn, _ = listener.accept()
            conn.recv(65536)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n")
            conn.sendall(b"%x\r\n%s\r\n" % (len(pieces[0]), pieces[0]))
            go.wait(10)
            for p in pieces[1:]:
                conn.sendall(b"%x\r\n%s\r\n" % (len(p), p))
                time.sleep(0.02)
            time.sleep(5)
            conn.close()

        threading.Thread(target=hub, daemon=True).start()
        proxy_file = os.path.join(T, "instruments-chunked-proxy.json")
        proxy = subprocess.Popen([sys.executable, os.path.join(HERE, "pause_proxy.py"),
                                  "http://127.0.0.1:%d" % listener.getsockname()[1], proxy_file],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            ports = json.loads(wait_file(proxy_file))
            control = "http://127.0.0.1:%d" % ports["control"]
            sock = socket.create_connection(("127.0.0.1", ports["proxy"]), timeout=5)
            sock.sendall(b"GET /machine/stream HTTP/1.1\r\nHost: x\r\n\r\n")
            got = b""
            while pieces[0] not in dechunked(got):
                got += sock.recv(65536)
            status, armed = call(control, "POST", "/control/arm", {"on": "next-events", "seconds": 1.0})
            self.assertEqual((status, armed["state"]), (200, "armed"))
            go.set()
            deadline = time.time() + 5
            while call(control, "GET", "/control/state")[1]["state"] != "paused" and time.time() < deadline:
                time.sleep(0.02)
            st = call(control, "GET", "/control/state")[1]
            self.assertEqual(st["state"], "paused", st)
            sock.settimeout(0.3)
            try:
                while True:
                    more = sock.recv(65536)
                    if not more:
                        break
                    got += more
            except OSError:   # socket.timeout: nothing more while paused
                pass
            self.assertTrue(dechunked(got).endswith(frames[0] + frames[1]), "the first events frame forwarded whole, "
                            "and nothing of the next one while paused: %r" % dechunked(got)[-120:])
            sock.settimeout(5)
            while b'"mark":"held"' not in dechunked(got):
                got += sock.recv(65536)
            self.assertEqual(call(control, "GET", "/control/state")[1]["state"], "resumed")
            sock.close()
        finally:
            proxy.terminate()
            proxy.wait(10)
            listener.close()


class BenchOpen(unittest.TestCase):
    """What bench_open.py reads and decides: the open line's figures, where
    a subscription's snapshot stands among the session's events, which opens
    fell inside a thinking-to-end window; and one run of it end to end."""

    def test_the_open_line_read_as_figures(self):
        read = bench_open.parse_open_line
        self.assertEqual(read("2026-10-20T10:00:00.000Z plane: open s-1 of 0123abcd: bridge snapshot after 0.75 s from "
                              "the subscribe's arrival (bridge: snapshot arrived 0.50 s, taken 0.75 s; build: cold 12 ms "
                              "3 rows, cut on disk; waits 2)\n"),
                         {"sub": "s-1", "outcome": "bridge snapshot", "N": 0.75, "arrived": 0.5, "taken": 0.75,
                          "bridge": "bridge: snapshot arrived 0.50 s, taken 0.75 s", "build": "cold", "cpu_ms": 12,
                          "rows": 3, "cut": "on disk", "waits": 2})
        line = read("plane: open Ab_-9 of 0123abcd/a1b2: transcript-only (no bridge socket) after 0.02 s from the "
                    "subscribe's arrival (no bridge; build: warm 0 ms 15000 rows, cut null; waits 0)")
        self.assertEqual((line["sub"], line["outcome"], line["arrived"], line["build"], line["rows"], line["cut"]),
                         ("Ab_-9", "transcript-only (no bridge socket)", None, "warm", 15000, "null"))
        line = read("plane: open s-2 of 0123abcd: discontinuity before its snapshot: the snapshot's cut, row r, never "
                    "reached the transcript after 5.15 s from the subscribe's arrival (bridge: no snapshot; build: "
                    "none, cut not on disk; waits 25)")
        self.assertEqual((line["outcome"][:13], line["N"], line["build"], line["cpu_ms"], line["cut"], line["waits"]),
                         ("discontinuity", 5.15, "none", None, "not on disk", 25))
        self.assertIsNone(read("plane: something else"))

    def test_a_snapshot_stands_before_the_first_event_its_subscriber_was_sent(self):
        e = [{"type": "chunk", "chunkIndex": i, "t": 100 + i} for i in range(4)]
        backbone = [(10.0 + i, x) for i, x in enumerate(e)]
        snap = {"type": "snapshot", "cut": {}}
        tees = [{"sub": "a", "lines": [(11.5, snap), (12.2, {"n": 1, **e[2]})]},     # placed by its next event
                {"sub": "b", "lines": [(10.5, snap)]},                              # nothing after it: by its stamp
                {"sub": "c", "lines": [(11.9, snap), (12.0, {"n": 1, "type": "gone"}), (13.1, {"n": 2, **e[3]})]}]
        events, how = bench_open.place_snapshots(backbone, tees)
        self.assertEqual([x.get("sub") or x["chunkIndex"] for x in events], [0, "b", 1, "a", 2, "c", 3])
        self.assertEqual(how, {"a": "event", "b": "time", "c": "event"})
        self.assertEqual(events[3], {"type": "snapshot", "cut": {}, "sub": "a"})
        # The inventory reads the placed snapshot: a request whose step ended before it is the accepted hole.
        order = dx4_consumer.order_of([{"type": "step", "phase": "end", "turnId": "t", "agentId": None, "step": 0}]
                                      + events)
        self.assertEqual(order[0], {"b": 2, "a": 4, "c": 6})

    def test_an_open_counts_inside_the_thinking_to_end_window(self):
        key = ("turn-1", None, 0)
        ev = [(1.0, {"type": "step", "phase": "start", "turnId": "turn-1", "agentId": None, "step": 0}),
              (1.1, {"type": "chunk", "turnId": "turn-1", "agentId": None, "step": 0,
                     "chunk": {"kind": "thinking", "index": 0, "text": "hm"}}),
              (1.5, {"type": "block-row", "turnId": "turn-1", "agentId": None, "step": 0, "index": 0, "uuid": "u"}),
              (1.6, {"type": "chunk", "turnId": "turn-1", "agentId": "a1", "step": 0,
                     "chunk": {"kind": "text", "index": 0, "text": "another loop's"}}),
              (1.7, {"type": "chunk", "turnId": "turn-1", "agentId": None, "step": 0,
                     "chunk": {"kind": "text", "index": 1, "text": "Once"}}),
              (4.0, {"type": "step", "phase": "end", "turnId": "turn-1", "agentId": None, "step": 0})]
        s = bench_open.steps_seen(ev)[key]
        self.assertEqual((s["thinking_named"], s["text_after"], s["end"]), (1.5, 1.7, 4.0))
        self.assertTrue(bench_open.in_window(s["thinking_named"], s["end"], 1.71))
        self.assertFalse(bench_open.in_window(s["thinking_named"], s["end"], 1.4), "before the block-row")
        self.assertFalse(bench_open.in_window(s["thinking_named"], s["end"], 4.2), "after the step's end")
        cut_off = ev[:5] + [(3.0, {"type": "turn", "phase": "complete", "turnId": "turn-1", "agentId": None})]
        self.assertEqual(bench_open.steps_seen(cut_off)[key]["end"], 3.0, "a turn's completion cuts its step off")
        plain = [x for x in ev if x[1].get("type") != "block-row"]
        self.assertIsNone(bench_open.steps_seen(plain)[key]["text_after"], "no thinking named: no window")

    def test_figures_and_sizes(self):
        self.assertEqual(bench_open.stats([0.3, None, 0.1, 0.2]), {"n": 3, "min": 0.1, "p50": 0.2, "max": 0.3})
        self.assertEqual(bench_open.stats([]), {"n": 0, "min": None, "p50": None, "max": None})
        self.assertEqual([bench_open.size_arg(x) for x in ("4m", "512k", "100")], [4 << 20, 512 << 10, 100])

    def test_a_run_against_the_stand_in(self):
        """bench_open.py itself, end to end: the real uplink against the
        stand-in, the fake session, two idle opens after the warm-up."""
        r = subprocess.run([sys.executable, os.path.join(HERE, "bench_open.py"), "--uplink", "--hub", "standin",
                            "--scenario", "idle", "--opens", "2"], capture_output=True, text=True, timeout=120,
                           env={k: v for k, v in os.environ.items() if k not in ("HOME", "SMINOS_HOME")}
                           | {"HOME": os.path.join(T, "bench-home")})
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = [json.loads(line) for line in r.stdout.splitlines()]
        opens = [o for o in out if o.get("mode") == "uplink" and "summary" not in o]
        self.assertEqual([o["counted"] for o in opens], [False, True, True])
        for o in opens:
            self.assertEqual((o["outcome"], o["holes"], o["dups"], o["gaps"], o["vanished"], o["errors"]),
                             ("bridge snapshot", 0, 0, 0, 0, []))
            self.assertGreater(o["E"], 0)
            self.assertIsNotNone(o["N"])
        self.assertEqual(opens[1]["build"], "warm")
        summary = out[-1]
        self.assertEqual((summary["summary"], summary["opens"], summary["E"]["n"]), ("idle", 2, 2))


class BenchOpenMicro(Session):
    """bench_open.py --micro against a scripted session's bridge and
    transcript: one line per open with N_micro and its phases, labelled."""

    def test_two_opens_in_process(self):
        for i in range(3):
            self.fake.user_row("row %d" % i, post=False)
        self.fake.start_bridge()
        r = subprocess.run([sys.executable, os.path.join(HERE, "bench_open.py"), "--micro", "--session", self.sid,
                            "--sminos-home", os.environ["SMINOS_HOME"], "--home", os.environ["HOME"], "--opens", "2"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = [json.loads(line) for line in r.stdout.splitlines()]
        opens = [o for o in out if o.get("mode") == "micro" and "summary" not in o]
        self.assertEqual(len(opens), 2)
        for o in opens:
            self.assertEqual((o["outcome"], o["rows"], o["cut"]), ("snapshot", 3, "on disk"))
            self.assertLess(o["N_micro"], 5)
            self.assertIn("build:end", [p[1] for p in o["phases"]])
            self.assertIn("the warmer", o["leaves_out"])
        self.assertEqual([o["build"] for o in opens], ["cold", "warm"])
        self.assertEqual(out[-1]["summary"], "micro")


class FixtureOutput(unittest.TestCase):
    """Every `output` case of dx4-jobs.json through the plane's own path. The
    case's roots are never handed to anything: the plane derives them from
    this machine's state, set up so they come out as the case's. The session's
    transcript sits in the worktree's project directory, it joined from the
    launch directory (`here`), its engine record's cwd is the worktree, and
    CLAUDE_CODE_TMPDIR is `<ROOT>/tmp`. The frame goes through Plane.output,
    the read runs on the transcript's worker, and the DX4 `output` message is
    what is checked."""

    SID = "d0c8a000-0000-4000-8000-00000000c0de"   # the fixture's session
    LAUNCH = "/Users/me/work/proj"                     # engine slug -Users-me-work-proj
    WORKTREE = "/Users/me/work/proj/.claude/worktrees/dc8"   # engine slug -Users-me-work-proj--claude-worktrees-dc8

    @classmethod
    def setUpClass(cls):
        home = os.environ["HOME"]
        cls.holder = subprocess.Popen(["sleep", "3600"])
        cls.record = os.path.join(home, ".claude", "sessions", "%d.json" % cls.holder.pid)
        with open(cls.record, "w") as f:
            json.dump({"pid": cls.holder.pid, "sessionId": cls.SID, "cwd": cls.WORKTREE, "kind": "interactive",
                       "status": "busy"}, f)
        cls.transcript = os.path.join(home, ".claude", "projects", plane.engine_slug(cls.WORKTREE), cls.SID + ".jsonl")
        os.makedirs(os.path.dirname(cls.transcript), exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.holder.terminate()
        cls.holder.wait(5)
        for path in (cls.record, cls.transcript):
            os.unlink(path)

    def pump(self, p, until):
        out, deadline = [], time.time() + 5
        while time.time() < deadline:
            out += p.pump_one("fx")
            if until(out):
                return out
            time.sleep(0.01)
        self.fail("nothing came: %r" % [m["kind"] for m in out])

    def test_every_output_case_through_the_plane(self):
        for case in FIXTURE["outputCases"]:
            with self.subTest(case=case["name"]):
                root = os.path.realpath(tempfile.mkdtemp(dir=T))
                # The fixture spells the engine's per-uid directory for uid 501, this machine's; the plane
                # derives it from its own uid.
                c = json.loads(json.dumps(case).replace("<ROOT>", root).replace("/claude-501/",
                                                                               "/claude-%d/" % os.getuid()))
                inp, want = c["input"], c["expect"]
                self.assertEqual(inp["session"], self.SID)
                for item in inp["layout"]:
                    path = item["path"]
                    os.makedirs(path if item.get("dir") else os.path.dirname(path), exist_ok=True)
                    if "file" in item:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(item["file"])
                    elif "symlink" in item:
                        os.symlink(item["symlink"], path)
                with open(self.transcript + ".tmp", "w") as f:
                    f.writelines(json.dumps(row) + "\n" for row in inp["main"])
                os.replace(self.transcript + ".tmp", self.transcript)
                with mock.patch.dict(os.environ, {"CLAUDE_CODE_TMPDIR": os.path.join(root, "tmp")}):
                    p = plane.Plane("testhost", lambda: None, transcripts=plane.Transcripts(), disk=plane.Disk())
                    try:
                        p.here = {PROJECT: {self.SID: self.LAUNCH}}
                        out = p.subscribe(types.SimpleNamespace(id=PROJECT, name="fixture"),
                                          {"session": self.SID, "agentId": None, "sub": "fx"})
                        self.pump(p, lambda ms: any(m["kind"] == "snapshot" for m in out + ms))
                        self.assertEqual(p.live[self.SID]["cwd"], self.WORKTREE, "the engine record is read")
                        self.assertEqual(p.output({"sub": "fx", **inp["request"]}), [], "read on the worker")
                        got = [m for m in self.pump(p, lambda ms: any(m["kind"] == "output" for m in ms))
                               if m["kind"] == "output"][0]["body"]
                    finally:
                        p.close()
                if want["result"] == "refused":
                    self.assertTrue(str(got.pop("reason", "")).strip(), "a refusal gives its reason")
                self.assertEqual(got, want)


STREAM = json.load(open(os.path.join(HERE, "dx4-stream.json"), encoding="utf-8"))


class StreamFixture(unittest.TestCase):
    """dx4-stream.json (written by dx4-stream.gen.py, shared with the web's
    layer test): the reference consumer draws, after every message, what the
    fixture says by hand; the store-side keys a replay of the web's layer
    alone reads (`settle`, `landing`, `lands`) are what the consumer derived;
    and every planted error is found, the consumer's own and the
    inventory's."""

    def test_every_sequence_draws_as_the_fixture_says(self):
        self.assertTrue(STREAM)
        for seq in STREAM:
            with self.subTest(seq=seq["name"]):
                c = dx4_consumer.Consumer(seq["agent"])
                for i, step in enumerate(seq["steps"]):
                    where = "%s, step %d (%s)" % (seq["name"], i, step.get("note") or (
                        step["message"] if isinstance(step["message"], str) else step["message"]["kind"]))
                    if step["message"] == "resubscribe":
                        c = dx4_consumer.Consumer(seq["agent"], previous=c)
                    else:
                        c.take(step["message"])
                        self.assertEqual(c.last_settle, step.get("settle", []), where)
                        if "landing" in step:
                            self.assertEqual((c.last_landing, c.last_lands), (step["landing"], step["lands"]), where)
                    self.assertEqual(c.drawn_by_agent(), step["drawn"], where)
                self.assertEqual(c.error_kinds(), seq["errors"], c.errors)
                if "inventory" in seq:
                    path = os.path.join(T, "stream-%s.jsonl" % seq["name"])
                    with open(path, "w") as f:
                        f.writelines(json.dumps(r) + "\n" for r in seq["inventory"]["transcript"])
                    inventory = dx4_consumer.Inventory.from_sources(path, seq["inventory"]["dx5"])
                    self.assertEqual(inventory.check(c), seq["inventory"]["check"])

    def env(self, kind, n, body):
        return {"project": PROJECT, "machine": "testhost", "session": "s", "kind": kind, "sub": "x", "n": n,
                "body": body}

    def test_a_page_holding_a_row_twice_is_held_once_and_said(self):
        c = dx4_consumer.Consumer(None)
        newest = {"type": "user", "uuid": "b", "message": {"role": "user", "content": "b"}}
        older = {"type": "user", "uuid": "a", "message": {"role": "user", "content": "a"}}
        c.take(self.env("snapshot", 0, {"rows": [newest], "more": True, "subagents": [], "presence": {},
                                        "streaming": [], "offChain": []}))
        c.take(self.env("rows", 1, {"rows": [older, older], "before": "b", "more": False, "offChain": []}))
        self.assertEqual(c.uuids(), ["a", "b"], "held once")
        self.assertEqual(c.error_kinds(), ["dup"])
        c.take(self.env("rows", 2, {"rows": [older], "before": "b", "more": False, "offChain": []}))
        self.assertEqual((c.uuids(), c.error_kinds()), (["a", "b"], ["dup"]), "a held row paged again is no dup")

    def test_the_inventory_reads_a_missing_transcript_as_empty_and_fails_on_any_other_error(self):
        missing = dx4_consumer.Inventory.from_sources(os.path.join(T, "no-such-transcript.jsonl"), [])
        self.assertEqual(missing.rows, [], "a transcript not written yet holds no rows")
        unreadable = os.path.join(T, "unreadable-transcript")
        os.makedirs(unreadable, exist_ok=True)
        with self.assertRaises(OSError):
            dx4_consumer.Inventory.from_sources(unreadable, [])

    def test_every_sequence_section_9_names_is_there(self):
        """The fixture covers what §9 lists, and names and describes each sequence."""
        kinds = {s["message"]["kind"] for q in STREAM for s in q["steps"] if isinstance(s["message"], dict)}
        self.assertLessEqual({"snapshot", "chunk", "block-row", "step-end", "row", "end"}, kinds)
        first = [next(s["message"]["body"] for s in q["steps"]
                      if isinstance(s["message"], dict) and s["message"]["kind"] == "snapshot") for q in STREAM]
        carried = {b["kind"] for body in first for e in body["streaming"] for b in e["blocks"]}
        self.assertEqual(carried, {"thinking", "text", "tool"}, "first snapshots carry every kind")
        names = [q["name"] for q in STREAM]
        self.assertEqual(len(names), len(set(names)))
        for q in STREAM:
            self.assertTrue(q["about"].strip(), q["name"])
            self.assertTrue(all("drawn" in s for s in q["steps"]), q["name"])
        for name in ("reconnect-empty-history-carries-the-named-block", "reconnect-snapshot-no-longer-carries-the-block",
                     "reconnect-older-snapshot-changes-nothing"):
            self.assertIn(name, names)
        planted = {k for q in STREAM for k in q["errors"]} | {
            k for q in STREAM for k, v in q.get("inventory", {}).get("check", {}).items() if v}
        self.assertLessEqual({"gap", "dup", "watermark", "after-end", "vanished", "holes", "partial", "dups", "undrawn",
                              "residual"}, planted)
        truncated = {b["kind"] for q in STREAM for s in q["steps"] if isinstance(s["message"], dict)
                     and s["message"]["kind"] == "snapshot" for e in s["message"]["body"]["streaming"]
                     for b in e["blocks"] if b.get("truncated")}
        self.assertEqual(truncated, {"text", "tool"}, "truncated blocks of text and of a tool call settle")


class ChainRules(unittest.TestCase):
    """The live chain (Chain) row by row, on the shapes the engine writes:
    what each row takes off the chain and puts back on."""

    def feed(self, chain, rows):
        """(off, on) per row, by uuid."""
        return {r["uuid"]: chain.add(r) for r in rows}

    def first_turn(self, t, mid="m0"):
        """A prompt answered, its turn ended: the branch point an Esc goes back to."""
        return [t.prompt("hello"), t.attachment(), t.answer("hi", mid), t.turn_end()]

    def test_a_prompt_sent_again_after_an_esc_leaves_the_first_copy_off(self):
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        end = before[-1]["uuid"]
        sent = [t.prompt("fix the bug"), t.attachment()]
        again = t.prompt("fix the bug", parent=end)   # the Esc handed it back; sent again from the turn's end
        after = [t.attachment(), t.answer("on it", "m1")]
        got = self.feed(c, before + sent + [again] + after)
        self.assertEqual(got[again["uuid"]], ([r["uuid"] for r in sent], []),
                         "the copy sent again takes the first one off, and the rows it held")
        self.assertTrue(all(got[r["uuid"]] == ([], []) for r in before + sent + after), "nothing else moves")
        self.assertEqual({u for u in c.offs}, {r["uuid"] for r in sent})
        self.assertFalse(any(c.off(r["uuid"]) for r in before + [again] + after))

    def test_a_steer_stays_on_through_its_turn_and_goes_off_with_it(self):
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        end = before[-1]["uuid"]
        prompt = t.prompt("run the suite")
        call = t.tool_call("toolu_1", "m1")
        steer = t.steer("also run the linter")   # appended while the call runs
        result = t.tool_result("toolu_1", call)  # names its call, not the steer: the leaf's ancestry skips it
        more = [t.answer("running the linter too", "m2")]
        got = self.feed(c, before + [prompt, call, steer, result] + more)
        self.assertTrue(all(off == [] for off, _ in got.values()), "a live turn takes nothing off")
        self.assertFalse(c.off(steer["uuid"]), "the steer the turn read is on the chain")
        undone = [prompt, call, steer, result] + more
        again = t.prompt("run the suite", parent=end)   # a /rewind undid the turn
        off, on = c.add(again)
        self.assertEqual((off, on), ([r["uuid"] for r in undone], []))
        self.assertTrue(c.off(steer["uuid"]), "the steer went off with the turn it was read in")

    def test_parallel_tool_results_stay_on(self):
        """One response, two calls: split into two assistant rows, each result
        hanging off its own call; what the leaf's ancestry skips stays on."""
        t, c = Thread(), plane.Chain()
        self.feed(c, self.first_turn(t))
        end = t.leaf
        rows = [t.prompt("check both")]
        a = t.tool_call("toolu_a", "m1")
        b = t.tool_call("toolu_b", "m1")
        ra = t.tool_result("toolu_a", a)
        hook = t.attachment("hook_success")      # on the first result: the second's ancestry skips it
        rb = t.tool_result("toolu_b", b)
        rows += [a, b, ra, hook, rb, t.attachment(), t.answer("both pass", "m2"), t.turn_end()]
        got = self.feed(c, rows)
        self.assertTrue(all(v == ([], []) for v in got.values()), "no row takes another off")
        self.assertEqual(c.offs, set())
        self.assertLessEqual({r["uuid"] for r in rows}, set(c.pos), "every row on the chain")
        again = t.prompt("check both", parent=end)   # undo the whole turn
        off, _ = c.add(again)
        self.assertEqual(off, [r["uuid"] for r in rows], "and a rewind past the turn takes all of it off")

    def test_a_response_the_engine_dropped_goes_off(self):
        """A message reaching the turn while a response streams: the engine
        drops the response and asks again, the message parented on the row
        before it."""
        t, c = Thread(), plane.Chain()
        rows = [t.prompt("go")]
        call = t.tool_call("toolu_1", "m1")
        result = t.tool_result("toolu_1", call)
        dropped = [t.answer("thinking it over", "m2"), t.answer("done, I think", "m2")]
        note = t.chained(t.row(type="user", isMeta=True, message={"role": "user", "content": "a message"}),
                         result["uuid"])
        got = self.feed(c, rows + [call, result] + dropped + [note])
        self.assertEqual(got[note["uuid"]], ([r["uuid"] for r in dropped], []))

    def test_rows_written_ahead_of_their_parent_wait_for_it(self):
        """Around a session's start the engine writes a child a few ms ahead
        of its parent: it waits, unplaced and unmarked, and joins with it."""
        t, c = Thread(), plane.Chain()
        hook = t.attachment("hook_success", parent=None)
        prompt = t.prompt("start")
        env = t.attachment("environment")
        model = t.attachment("model")
        order = [env, hook, prompt, model]       # env on disk before its parent
        got = self.feed(c, order)
        self.assertTrue(all(v == ([], []) for v in got.values()), "nothing taken off")
        self.assertEqual(c.line, [hook["uuid"], prompt["uuid"], env["uuid"], model["uuid"]],
                         "the chain in the order of its parents, not of the file")
        orphan = t.prompt("a fork's first row", parent=str(uuidlib.uuid4()))
        self.assertEqual(c.add(orphan), ([], []))
        self.assertFalse(c.off(orphan["uuid"]), "a row whose parent never comes stays unmarked")

    def test_a_compaction_keeps_the_history_and_a_null_parent_continues(self):
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        boundary = t.chained(t.row(type="system", subtype="compact_boundary", logicalParentUuid=t.leaf), None)
        after = [t.prompt("This session is being continued", parent=boundary["uuid"]), t.answer("ok", "m9")]
        got = self.feed(c, before + [boundary] + after)
        self.assertTrue(all(v == ([], []) for v in got.values()))
        self.assertEqual(c.offs, set(), "the history before a compaction stays on")

    def test_a_result_of_a_call_off_the_chain_is_off_and_moves_nothing(self):
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        end = before[-1]["uuid"]
        prompt = t.prompt("slow one")
        call = t.tool_call("toolu_1", "m1")
        again = t.prompt("never mind", parent=end)
        reply = t.answer("ok", "m2")
        late = t.tool_result("toolu_1", call)    # the undone call's result, written late
        got = self.feed(c, before + [prompt, call, again, reply, late])
        self.assertEqual(got[late["uuid"]], ([late["uuid"]], []))
        self.assertEqual(c.line[-2:], [again["uuid"], reply["uuid"]], "the chain did not move")

    def test_a_branch_back_onto_rows_taken_off_puts_them_back(self):
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        end = before[-1]["uuid"]
        first = [t.prompt("one"), t.answer("1", "m1")]
        other = t.prompt("two", parent=end)
        back = t.prompt("continue one", parent=first[-1]["uuid"])
        got = self.feed(c, before + first + [other, back])
        self.assertEqual(got[other["uuid"]], ([r["uuid"] for r in first], []))
        self.assertEqual(got[back["uuid"]], ([other["uuid"]], [r["uuid"] for r in first]))
        self.assertEqual(c.offs, {other["uuid"]})

    def test_a_branch_back_into_a_parallel_response_brings_all_of_it_back(self):
        """The loader recovers a response's other calls and their results with
        any one of them: so does a branch that runs back through one."""
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        prompt = t.prompt("check both")
        a, b = t.tool_call("toolu_a", "m1"), t.tool_call("toolu_b", "m1")
        ra, rb = t.tool_result("toolu_a", a), t.tool_result("toolu_b", b)
        other = t.prompt("never mind", parent=prompt["uuid"])
        back = t.answer("a passed", "m2", parent=ra["uuid"])
        got = self.feed(c, before + [prompt, a, b, ra, rb, other, back])
        self.assertEqual(got[other["uuid"]], ([a["uuid"], b["uuid"], ra["uuid"], rb["uuid"]], []))
        off, on = got[back["uuid"]]
        self.assertEqual(off, [other["uuid"]])
        self.assertEqual(sorted(on), sorted(r["uuid"] for r in (a, b, ra, rb)), "the whole response, both results")
        self.assertEqual(c.offs, {other["uuid"]})

    def test_rows_brought_back_stand_in_the_order_they_were_written(self):
        """A later branch cuts by where rows stand on the chain, so a result
        brought back with its response stands before the turn that followed."""
        t, c = Thread(), plane.Chain()
        before = self.first_turn(t)
        prompt = t.prompt("check both")
        a, b = t.tool_call("toolu_a", "m1"), t.tool_call("toolu_b", "m1")
        ra, rb = t.tool_result("toolu_a", a), t.tool_result("toolu_b", b)
        answer = t.answer("both pass", "m2")     # after rb: the branch back runs through rb, not ra
        other = t.prompt("never mind", parent=prompt["uuid"])
        back = t.prompt("go on", parent=answer["uuid"])
        fork = t.prompt("redo a", parent=ra["uuid"])
        got = self.feed(c, before + [prompt, a, b, ra, rb, answer, other, back, fork])
        self.assertEqual(got[fork["uuid"]], ([answer["uuid"], back["uuid"]], []),
                         "the turn after the response goes; the response's rows stay")
        self.assertEqual(c.offs, {other["uuid"], answer["uuid"], back["uuid"]})

    def test_a_cascade_reports_each_rows_net_move(self):
        """Waiting rows placed in one cascade can move a row more than once;
        what the row reports is where each ended up."""
        c = plane.Chain()
        x, cc, d, e, f = (str(uuidlib.uuid4()) for _ in range(5))
        rows = [{"uuid": e, "parentUuid": cc}, {"uuid": f, "parentUuid": d}, {"uuid": cc, "parentUuid": x},
                {"uuid": d, "parentUuid": x}, {"uuid": x, "parentUuid": None}]
        got = self.feed(c, [dict(r, type="user") for r in rows])
        off, on = got[x]
        self.assertEqual(set(off), c.offs, "every row reported off is off, and every off row reported")
        self.assertEqual(len(off), len(set(off)), "once each")
        self.assertEqual(on, [], "nothing was off before the row came")

    def test_progress_and_sidechain_rows_are_never_marked(self):
        t, c = Thread(), plane.Chain()
        prompt = t.prompt("x")
        progress = t.chained(t.row(type="progress", data={}))
        reply = t.answer("y", "m1")              # parented on the progress row: passed through to the prompt
        side = t.chained(t.row(type="user", message={"role": "user", "content": "old subagent row"}), prompt["uuid"])
        side["isSidechain"] = True
        got = self.feed(c, [prompt, progress, reply, side])
        self.assertTrue(all(v == ([], []) for v in got.values()))
        self.assertEqual(c.line, [prompt["uuid"], reply["uuid"]])
        agent = plane.Chain(main=False)          # an agent's transcript: every row is a sidechain row
        t2 = Thread(sidechain=True)
        rows = [t2.prompt("task"), t2.answer("a", "m1")]
        again = t2.prompt("task", parent=None)
        self.feed(agent, rows)
        self.assertEqual(agent.add(again), ([], []), "a null parent continues")

    def test_copy_is_independent(self):
        t, c = Thread(), plane.Chain()
        first = self.first_turn(t)
        second = self.first_turn(t, mid="m1")   # another response: a response's rows share its message id
        self.feed(c, first + second)
        d = c.copy()
        again = t.prompt("hello", parent=first[-1]["uuid"])
        self.assertEqual(d.add(again)[0], [r["uuid"] for r in second])
        self.assertEqual(c.offs, set(), "the original did not see it")
        self.assertEqual(c.add(again)[0], [r["uuid"] for r in second])


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
                mock.patch.object(plane.sminos, "read_proc_start", lambda _pid: start[0]):
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

        def read_proc_start(pid):
            reads.append(pid)
            return start[0]

        with mock.patch.object(plane.sminos, "pid_alive", lambda _pid: True), \
                mock.patch.object(plane.sminos, "read_proc_start", read_proc_start):
            self.assertIn(self.sid, records.scan())
            start[0] = "Fri Oct 16 11:00:00 2026"  # reused between polls, never seen dead
            clock.advance(plane.PRESENCE_EVERY)
            self.assertIn(self.sid, records.scan(), "within the bound the identity is not read again")
            self.assertEqual(len(reads), 1, "the start time is not read at every poll")
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
                return {"t": "session", "message": {"kind": "machine", "body": {"checkouts": []}}}

            def hello(self, follow=False):
                return {"t": "hello", "project": project.id, **({"follow": True} if follow else {})}

            def reported(self, _):
                pass

        posted = []

        def refused(frames):
            posted.append(frames)
            raise uplink.NotDelivered("the hub answered 503")

        def link_of(post):
            link = uplink.Link({"machine": "testhost", "org": "org-1", "key": b"k" * 32, "hub": "http://127.0.0.1:9"}, {})
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


class TickCost(unittest.TestCase):
    """What the uplink's tick reads again and again — every live session's
    start time — read without running a process."""

    @unittest.skipUnless(sys.platform == "darwin", "read off the kernel on macOS; ps elsewhere")
    def test_a_start_time_is_what_ps_prints_read_without_running_it(self):
        import sminos
        holder = subprocess.Popen(["sleep", "60"])
        try:
            ps = " ".join(subprocess.run(["ps", "-o", "lstart=", "-p", str(holder.pid)], capture_output=True,
                                         text=True, env={**os.environ, "LC_ALL": "C", "LANG": "C"}).stdout.split())
            with mock.patch.object(sminos.subprocess, "run", side_effect=AssertionError("a process was run")):
                self.assertEqual(sminos.read_proc_start(holder.pid), ps)
                self.assertTrue(sminos.same_process({"pid": holder.pid, "procStart": ps}, fresh=True))
                self.assertFalse(sminos.same_process({"pid": holder.pid, "procStart": "Mon Jan 1 00:00:00 2001"},
                                                     fresh=True), "another process's start time")
        finally:
            holder.kill()
            holder.wait()
        with mock.patch.object(sminos.subprocess, "run", side_effect=AssertionError("a process was run")):
            self.assertEqual(sminos.read_proc_start(holder.pid), "", "no process holds the pid now")


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
        b = dx4_consumer.Consumer(agent)
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
        self.assertEqual({k: v for k, v in b.texts().items() if k[1] == agent}, {}, "no text left beside its row")

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
        said = [line for line in read(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")).splitlines()
                if "plane: open %s of %s:" % (b.sub, self.sid[:8]) in line]
        self.assertEqual(len(said), 1, said)
        self.assertRegex(said[0], r": bridge snapshot after \d+\.\d\d s from the subscribe's arrival \(bridge: "
                                  r"snapshot arrived \d+\.\d\d s, taken \d+\.\d\d s; build: (cold|warm) \d+ ms \d+ rows, "
                                  r"cut (on disk|null); waits \d+\)$", "the uplink's open line, timed from the frame's arrival")
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
        self.assertEqual(b.uuids(), ids + [last], "back to the first line, the pages held before")
        self.assertEqual([r["uuid"] for r in reversed(older)], ids[:len(older)])
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
        self.assertIn((main.turn, None, 0, 3), after[0].texts(), "the late-noticed block still streams")
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

    def test_g_output_through_the_hub(self):
        """DX2's `output` frame down, DX4 `output` up, its four variants: a
        session whose transcript lives under one slug ("proj") and whose
        outputs are under its working directory's; then the session ends and
        the idle subscription answers still."""
        home, sh = os.environ["HOME"], os.environ["SMINOS_HOME"]
        sid = new_session()
        fake = fake_session.FakeSession(home, sh, sid)
        base = os.path.join(os.path.realpath(os.environ["CLAUDE_CODE_TMPDIR"]), "claude-%d" % os.getuid())
        root = os.path.join(base, plane.engine_slug(self.root), sid, "tasks")
        elsewhere = os.path.join(T, "elsewhere", sid, "tasks")
        for d, name in ((root, "bo1.output"), (elsewhere, "bo3.output")):
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "w") as f:
                f.write("built\nok\n")
        r = Rows()
        for task, d in (("bo1", root), ("bo2", root), ("bo3", elsewhere)):
            for row in (r.call("Bash", "toolu_" + task, command="make " + task, run_in_background=True),
                        r.result("toolu_" + task, {"backgroundTaskId": task},
                                 "Output is being written to: %s/%s.output" % (d, task))):
                fake.write_row(None, row)
        for row in (r.call("Monitor", "toolu_mo1", description="watch"), r.result("toolu_mo1", {"taskId": "mo1"})):
            fake.write_row(None, row)
        holder = self.spawn(["sleep", "3600"])
        with open(os.path.join(home, ".claude", "sessions", "%d.json" % holder.pid), "w") as f:
            json.dump({"pid": holder.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive",
                       "status": "busy"}, f)
        self.assertIsNotNone(self.hub.wait(lambda ms: any(m["kind"] == "presence" and m["session"] == sid
                                                          for m in ms), timeout=5), "the session is a member")
        b = self.subscribe(session=sid)
        self.assertTrue(self.feed(b, lambda: b.snapshot is not None))
        self.assertEqual(sorted(by_task(b.snapshot)), ["bo1", "bo2", "bo3", "mo1"])

        def ask(*tasks):
            count = len(b.outputs)
            for task in tasks:
                self.hub.send({"t": "output", "project": self.project, "session": sid, "agentId": None, "sub": b.sub,
                               "taskId": task, "tail": 4096})
            self.assertTrue(self.feed(b, lambda: len(b.outputs) == count + len(tasks)))
            return {o["taskId"]: o for o in b.outputs[count:]}

        got = ask("bo1", "mo1", "bo2", "bo3", "nope")
        self.assertEqual(got["bo1"], {"taskId": "bo1", "result": "ok", "path": root + "/bo1.output", "size": 9,
                                      "from": 0, "text": "built\nok\n", "truncated": False})
        self.assertEqual(got["mo1"], {"taskId": "mo1", "result": "missing", "path": None})
        self.assertEqual(got["bo2"], {"taskId": "bo2", "result": "missing", "path": root + "/bo2.output"})
        self.assertEqual((got["bo3"]["result"], got["bo3"]["path"]), ("refused", elsewhere + "/bo3.output"))
        self.assertTrue(got["bo3"]["reason"].strip())
        self.assertEqual(got["nope"], {"taskId": "nope", "result": "unknown-task"})

        holder.terminate()
        holder.wait(5)
        self.feed(b, lambda: by_task(b.body)["mo1"]["status"] == "exited", timeout=plane.END_GRACE + 2.0)
        self.assertEqual({j["status"] for j in b.body["jobs"]}, {"exited"}, "the jobs ended with the process")
        self.feed(b, lambda: False, timeout=plane.END_GRACE + 0.5)
        self.assertEqual(ask("bo1")["bo1"]["result"], "ok", "the idle subscription answers `output` too")
        self.assertIsNone(b.end)
        self.assertEqual(b.errors, [])
        self.hub.send({"t": "unsubscribe", "project": self.project, "sub": b.sub})


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
