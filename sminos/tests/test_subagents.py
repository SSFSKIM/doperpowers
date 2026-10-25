#!/usr/bin/env python3
"""`sminos list --subagents`: each subagent's lifecycle from the engine's word (the bridge's agents) or the disk
the engine writes (metas, transcripts), the tree, --done, and the CLI's text and JSON, in a temp home. The rows
are shaped as the engine writes them (2.1.310: a background Bash launch, its notification after the preamble, a
handback's turn-ending result, request records between rows)."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/sminos/scripts"
sys.path.insert(0, str(SCRIPTS))
import sminos_subagents as V  # noqa: E402

CLI = SCRIPTS / "sminos.py"
NOW = 1_800_000_000.0
STARTED = NOW - 3600   # the session's running process started an hour ago
SID = "5a000001-0000-4000-8000-0000000000a1"
OTHER = "5a000002-0000-4000-8000-0000000000a2"


def ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class Rows:
    """Transcript rows as the engine writes them."""
    n = 0

    @classmethod
    def _uuid(cls):
        cls.n += 1
        return "u-%d" % cls.n

    @classmethod
    def prompt(cls, t, text="do the work", **extra):
        return {"type": "user", "uuid": cls._uuid(), "timestamp": ts(t),
                "message": {"role": "user", "content": text}, **extra}

    @classmethod
    def call(cls, t, tid, name, inp=None, msg="m1"):
        return {"type": "assistant", "uuid": cls._uuid(), "timestamp": ts(t),
                "message": {"id": msg, "role": "assistant", "stop_reason": "tool_use",
                            "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp or {}}]}}

    @classmethod
    def result(cls, t, tid, text="ok", tur=None, ends=None):
        row = {"type": "user", "uuid": cls._uuid(), "timestamp": ts(t),
               "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}}
        if tur is not None:
            row["toolUseResult"] = tur
        if ends:
            row["toolEndsTurn"] = True
        return row

    @classmethod
    def reply(cls, t, text="done", stop="end_turn", msg="m9"):
        return {"type": "assistant", "uuid": cls._uuid(), "timestamp": ts(t),
                "message": {"id": msg, "role": "assistant", "stop_reason": stop,
                            "content": [{"type": "text", "text": text}]}}

    @classmethod
    def api_error(cls, t):
        return {"type": "assistant", "uuid": cls._uuid(), "timestamp": ts(t), "isApiErrorMessage": True,
                "error": "model_not_found",
                "message": {"id": "e1", "role": "assistant", "stop_reason": "stop_sequence",
                            "content": [{"type": "text", "text": "There's an issue with the selected model."}]}}

    @classmethod
    def notification(cls, t, task, status="completed"):
        text = ("[SYSTEM NOTIFICATION - NOT USER INPUT]\nThis is an automated background-task event.\n\n"
                "<task-notification>\n<task-id>%s</task-id>\n<status>%s</status>\n"
                "<summary>Background command finished</summary>\n</task-notification>" % (task, status))
        return {"type": "user", "uuid": cls._uuid(), "timestamp": ts(t), "isMeta": True,
                "origin": {"kind": "task-notification"}, "message": {"role": "user", "content": text}}

    @classmethod
    def bg_bash(cls, t, tid, task, desc="run the tests"):
        """A background Bash launch: its call, then its result naming the task."""
        return [cls.call(t, tid, "Bash", {"command": "make test", "description": desc, "run_in_background": True},
                         msg="m-" + tid),
                cls.result(t + 1, tid, "Command running in background with ID: %s." % task,
                           tur={"stdout": "", "backgroundTaskId": task})]

    @classmethod
    def handback(cls, t, tid="toolu_hb"):
        return [cls.call(t, tid, "SubagentHandback", {"message": "report"}, msg="m-hb"),
                cls.result(t + 1, tid, "Report delivered to your caller.", tur={"success": True}, ends=True)]


REQUEST = '{"type":"api-request","sessionId":"x","params":{"messages":"%s"}}' % ("x" * 2000)


class Session:
    """A session's transcripts under a temp home: the main loop's, and each agent's meta and transcript, each
    file's mtime set."""

    def __init__(self, home, session=SID):
        self.dir = Path(home) / ".claude/projects/proj"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.main = self.dir / (session + ".jsonl")
        self.sub = self.dir / session / "subagents"
        self.sub.mkdir(parents=True, exist_ok=True)
        self.write(self.main, [Rows.prompt(STARTED)], STARTED)
        self.order = 0

    @staticmethod
    def write(path, rows, mtime):
        with open(path, "w") as f:
            for r in rows:
                f.write((r if isinstance(r, str) else json.dumps(r, separators=(",", ":"))) + "\n")
        os.utime(path, (mtime, mtime))

    def agent(self, agent_id, rows, at, meta=None, parent=None, d=None, meta_text=None):
        d = Path(d) if d else self.sub
        m = {"agentType": "general-purpose", "description": "task " + agent_id, "toolUseId": "tu-" + agent_id,
             "spawnDepth": 1, "requestShape": "background"}
        if parent:
            m["parentAgentId"] = parent
        m.update(meta or {})
        meta_path = d / ("agent-%s.meta.json" % agent_id)
        meta_path.write_text(meta_text if meta_text is not None else json.dumps({k: v for k, v in m.items()
                                                                                 if v is not None}))
        self.order += 1
        os.utime(meta_path, (at, at))
        if rows is not None:
            self.write(d / ("agent-%s.jsonl" % agent_id), rows, at)

    def append_main(self, rows):
        with open(self.main, "a") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        os.utime(self.main, (NOW, NOW))

    def view(self, live=True, bridge=None, started=STARTED, stall=V.STALL_SECONDS):
        return V.Subagents(str(self.main), live=live, started=started, bridge=bridge, stall=stall, now=NOW)


class Derivation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sminos-subagents-")
        self.addCleanup(self.tmp.cleanup)
        self.s = Session(self.tmp.name)

    def state(self, agent_id, **kw):
        return self.s.view(**kw).state(agent_id)

    # -- the four live states
    def test_a_tool_in_flight_runs_however_long_it_has_run(self):
        self.s.agent("a1", [Rows.prompt(NOW - 1800), Rows.call(NOW - 1500, "t1", "Bash", {"command": "sleep 2000"})],
                     NOW - 1500)
        st = self.state("a1")
        self.assertEqual((st["state"], st["source"], st["tool"]["name"]), ("running", "disk", "Bash"))
        e = self.s.view().entry("a1")
        self.assertEqual(e["seconds"], 1800, "running since its turn began")
        self.assertIn("running 30m (disk) · in Bash 25m", V.state_text(e))

    def test_the_model_at_work_runs_and_a_quiet_open_turn_with_nothing_in_flight_stalls(self):
        rows = [Rows.prompt(NOW - 900), Rows.call(NOW - 890, "t1", "Read"), Rows.result(NOW - 880, "t1")]
        self.s.agent("a1", rows, NOW - 30)
        self.assertEqual(self.state("a1")["state"], "running")
        self.s.agent("a2", rows, NOW - 700)
        st = self.state("a2")
        self.assertEqual((st["state"], st["source"]), ("stalled", "disk"))
        self.assertEqual(self.state("a2", stall=900)["state"], "running", "the threshold is the caller's")

    def test_the_engine_saying_running_is_never_stalled_however_long_since_a_write(self):
        rows = [Rows.prompt(NOW - 2000), Rows.call(NOW - 1990, "t1", "Read"), Rows.result(NOW - 1980, "t1")]
        self.s.agent("a1", rows, NOW - 1980)
        bridge = [{"agentId": "a1", "running": True, "status": "running", "subagentType": "general-purpose"}]
        v = self.s.view(bridge=bridge)
        e = v.entry("a1")
        self.assertEqual((e["state"], e["source"], e["engineStatus"]), ("running", "engine", "running"))
        self.assertEqual(e["quietSeconds"], 1980)
        self.assertIn("· no write 33m", V.state_text(e))

    def test_a_closed_turn_waits_on_a_background_shell_with_no_notification_yet(self):
        rows = [Rows.prompt(NOW - 600), *Rows.bg_bash(NOW - 590, "t1", "bs5pfwoe5"), REQUEST,
                Rows.reply(NOW - 580, "launched")]
        self.s.agent("a1", rows, NOW - 580, meta={"finished": True})
        st = self.state("a1")
        self.assertEqual(st["state"], "waiting", "finished by its meta, its turn closed, its shell still runs")
        self.assertEqual([b["taskId"] for b in st["background"]], ["bs5pfwoe5"])
        self.assertEqual(V.state_text(self.s.view().entry("a1")), "waiting on background 9m (disk)",
                         "the row names the wait, not the jobs: those stay in --json")

    def test_the_notification_ends_the_wait(self):
        rows = [Rows.prompt(NOW - 600), *Rows.bg_bash(NOW - 590, "t1", "bs1"), Rows.reply(NOW - 580, "launched"),
                Rows.notification(NOW - 400, "bs1"), *Rows.handback(NOW - 390)]
        self.s.agent("a1", rows, NOW - 389, meta={"finished": True})
        self.assertEqual(self.state("a1")["state"], "completed")

    def test_a_shell_stopped_with_no_notification_does_not_keep_it_waiting(self):
        rows = [Rows.prompt(NOW - 600), *Rows.bg_bash(NOW - 590, "t1", "bs1"),
                Rows.call(NOW - 585, "t2", "TaskStop", {"task_id": "bs1"}, msg="m-stop"),
                Rows.result(NOW - 584, "t2", "stopped", tur={"message": "Successfully stopped task: bs1",
                                                             "task_id": "bs1", "task_type": "local_bash"}),
                Rows.reply(NOW - 580)]
        self.s.agent("a1", rows, NOW - 580, meta={"finished": True})
        self.assertEqual(self.state("a1")["state"], "completed", "its TaskStop ends the shell")

    def test_a_shell_the_bridge_stopped_is_ended_by_its_note_in_the_main_loop(self):
        rows = [Rows.prompt(NOW - 600), *Rows.bg_bash(NOW - 590, "t1", "bs7"), Rows.reply(NOW - 580)]
        self.s.agent("a1", rows, NOW - 580)
        self.assertEqual(self.state("a1")["state"], "waiting")
        self.s.append_main([{"type": "user", "uuid": "note-1", "timestamp": ts(NOW - 100), "isMeta": True,
                             "origin": {"kind": "plugin", "name": "sminos"},
                             "message": {"role": "user", "content": "Task bs7, a background task, was stopped from "
                                                                     "the desk: it is not running."}}])
        self.assertEqual(self.state("a1")["state"], "completed")

    def test_a_closed_turn_waits_on_a_running_background_child_agent(self):
        self.s.agent("p1", [Rows.prompt(NOW - 600), Rows.reply(NOW - 500)], NOW - 500, meta={"finished": True})
        self.s.agent("c1", [Rows.prompt(NOW - 550), Rows.call(NOW - 540, "t1", "Bash")], NOW - 540, parent="p1")
        st = self.state("p1")
        self.assertEqual((st["state"], st["waitingOn"]), ("waiting", ["c1"]))

    def test_an_open_turn_from_before_the_process_started_is_orphaned_and_so_is_one_of_a_session_not_running(self):
        self.s.agent("a1", [Rows.prompt(STARTED - 900), Rows.call(STARTED - 800, "t1", "Bash")], STARTED - 800)
        self.assertEqual(self.state("a1")["state"], "orphaned")
        self.s.agent("a2", [Rows.prompt(NOW - 60), Rows.call(NOW - 50, "t1", "Bash")], NOW - 50)
        self.assertEqual(self.state("a2", live=False)["state"], "orphaned")

    # -- how it ended
    def test_an_agent_its_parent_stopped_with_TaskStop_is_stopped_not_orphaned(self):
        self.s.agent("a1", [Rows.prompt(STARTED - 900), Rows.call(STARTED - 800, "t1", "Bash")], STARTED - 800)
        self.s.append_main([Rows.call(STARTED - 700, "ts1", "TaskStop", {"task_id": "a1"}, msg="m-ts"),
                            Rows.result(STARTED - 699, "ts1", "stopped",
                                        tur={"message": "Successfully stopped task: a1", "task_id": "a1",
                                             "task_type": "local_agent"})])
        st = self.state("a1")
        self.assertEqual((st["state"], st["stoppedBy"]), ("stopped", "TaskStop"))

    def test_stopped_by_the_user_failed_and_killed(self):
        self.s.agent("u1", [Rows.prompt(NOW - 900), Rows.call(NOW - 800, "t1", "Bash")], NOW - 800,
                     meta={"stoppedByUser": True, "finished": True})
        self.s.agent("f1", [Rows.prompt(NOW - 900), Rows.api_error(NOW - 850)], NOW - 850, meta={"finished": True})
        self.s.agent("k1", [Rows.prompt(NOW - 900), Rows.call(NOW - 800, "t1", "Bash")], NOW - 800)
        self.s.agent("k2", [Rows.prompt(NOW - 900), Rows.call(NOW - 800, "t1", "Bash")], NOW - 800)
        bridge = [{"agentId": "k1", "running": False, "status": "killed"}, {"agentId": "k2", "running": False}]
        v = self.s.view(bridge=bridge)
        self.assertEqual((v.state("u1")["state"], v.state("u1")["stoppedBy"]), ("stopped", "user"))
        self.assertEqual(v.state("f1")["state"], "failed")
        self.assertEqual((v.state("k1")["state"], v.state("k1")["source"], v.state("k1")["stoppedBy"]),
                         ("stopped", "engine", "killed"))
        self.assertEqual((v.state("k2")["state"], v.state("k2")["stoppedBy"]), ("stopped", "killed"),
                         "ended with no word while its own rows leave the turn open")

    def test_a_finished_agent_revived_by_SendMessage_runs_again(self):
        revived = NOW - 120
        rows = [Rows.prompt(NOW - 3000), *Rows.handback(NOW - 2900),
                Rows.prompt(revived, "where are you?", isMeta=True, origin={"kind": "human"}),
                Rows.call(NOW - 100, "t9", "Grep", msg="m-r")]
        self.s.agent("a1", rows, NOW - 100, meta={"finished": True, "revivedAt": int(revived * 1000)})
        st = self.state("a1")
        self.assertEqual((st["state"], st["tool"]["name"]), ("running", "Grep"))
        self.assertEqual(self.s.view().entry("a1")["seconds"], 120, "running since the revival opened its turn")

    def test_a_revival_after_the_engine_said_it_ended_is_read_from_its_rows(self):
        """The bridge learns an end but no revival, and a resync's records carry no time: a revival
        (`revivedAt`, written since) whose turn its rows hold open is read from the rows, however soon after the
        end it came."""
        revived = NOW - 2898
        rows = [Rows.prompt(NOW - 3000), *Rows.handback(NOW - 2900),
                Rows.prompt(revived, "go on", isMeta=True, origin={"kind": "human"}),
                Rows.call(NOW - 2897, "t9", "Grep", msg="m-r")]
        self.s.agent("a1", rows, NOW - 2897, meta={"finished": True, "revivedAt": int(revived * 1000)})
        for said in ({"agentId": "a1", "running": False, "status": "completed"},
                     {"agentId": "a1", "running": False, "status": "completed", "t": int((NOW - 2899) * 1000)}):
            st = self.state("a1", bridge=[said])
            self.assertEqual((st["state"], st["source"], st["tool"]["name"]), ("running", "disk", "Grep"), said)
        closed = rows[:3] + [Rows.reply(NOW - 2890)]
        self.s.agent("a2", closed, NOW - 2890, meta={"finished": True, "revivedAt": int(revived * 1000)})
        st = self.state("a2", bridge=[{"agentId": "a2", "running": False, "status": "completed"}])
        self.assertEqual((st["state"], st["source"]), ("completed", "engine"), "a revival whose turn closed again")

    def test_finished_revived_then_stopped_by_its_parent_is_stopped(self):
        """TaskStop after a revival: the meta still says finished, the turn is open, the parent's rows end it.
        A TaskStop from before the revival does not."""
        revived = NOW - 300
        rows = [Rows.prompt(NOW - 3000), *Rows.handback(NOW - 2900),
                Rows.prompt(revived, "go on", isMeta=True, origin={"kind": "human"}),
                Rows.call(NOW - 290, "t9", "Bash", msg="m-r")]
        self.s.agent("a1", rows, NOW - 290, meta={"finished": True, "revivedAt": int(revived * 1000)})
        self.s.append_main([Rows.call(NOW - 2950, "ts0", "TaskStop", {"task_id": "a1"}, msg="m-ts0"),
                            Rows.result(NOW - 2949, "ts0", "stopped", tur={"task_id": "a1"})])
        self.assertEqual(self.state("a1")["state"], "running", "a stop before the revival says nothing of this turn")
        self.s.append_main([Rows.call(NOW - 200, "ts1", "TaskStop", {"task_id": "a1"}, msg="m-ts1"),
                            Rows.result(NOW - 199, "ts1", "stopped", tur={"task_id": "a1"})])
        for bridge in (None, [{"agentId": "a1", "running": False, "status": "completed"}]):
            st = self.state("a1", bridge=bridge)
            self.assertEqual((st["state"], st["stoppedBy"]), ("stopped", "TaskStop"), bridge)
        self.s.append_main([Rows.call(NOW - 100, "ts2", "TaskStop", {"task_id": "a9"}, msg="m-ts2"),
                            Rows.result(NOW - 99, "ts2", "Error: no such task", tur={})])

    def test_revived_stopped_and_revived_again_runs(self):
        """A TaskStop leaves no row that closes a turn: after finished → revived → TaskStopped → revived again,
        the open turn's first row is the first revival's, and only the latest revival (`revivedAt`) bounds what
        a stop can say of the turn running now."""
        first, second = NOW - 900, NOW - 300
        rows = [Rows.prompt(NOW - 3000), *Rows.handback(NOW - 2900),
                Rows.prompt(first, "go on", isMeta=True, origin={"kind": "human"}),
                Rows.call(first + 5, "t8", "Bash", msg="m-1"),
                Rows.prompt(second, "go on again", isMeta=True, origin={"kind": "human"}),
                Rows.call(second + 5, "t9", "Grep", msg="m-2")]
        self.s.agent("a1", rows, second + 5, meta={"finished": True, "revivedAt": int(second * 1000)})
        self.s.append_main([Rows.call(first + 60, "ts1", "TaskStop", {"task_id": "a1"}, msg="m-ts1"),
                            Rows.result(first + 61, "ts1", "stopped", tur={"task_id": "a1"})])
        st = self.state("a1")
        self.assertEqual((st["state"], st["tool"]["name"]), ("running", "Grep"))
        self.assertEqual([e["agentId"] for e in self.s.view().tree()], ["a1"], "and it stays in the live tree")

    def test_bisection_reads_each_rows_own_time_not_one_nested_in_its_message(self):
        """A row's `message` comes before its own `timestamp`, and may hold an older one (a tool's input, a
        quoted record): the bisection over the main loop must read the row's own, or it skips the stop."""
        def row(t, i):
            return {"type": "assistant", "uuid": "h-%d" % i,
                    "message": {"id": "mh-%d" % i, "role": "assistant", "stop_reason": "tool_use",
                                "content": [{"type": "tool_use", "id": "x%d" % i, "name": "mcp__log__write",
                                             "input": {"timestamp": "2020-01-01T00:00:00.000Z", "text": "y" * 700}}]},
                    "timestamp": ts(t)}
        before = [row(NOW - 2000 + i * 0.25, i) for i in range(3000)]       # ~2.3 MB before the stop
        after = [row(NOW - 1000 + i * 0.25, 10000 + i) for i in range(3000)]   # and as much after it
        stop = [Rows.call(NOW - 1100, "ts1", "TaskStop", {"task_id": "a1"}, msg="m-ts1"),
                Rows.result(NOW - 1099, "ts1", "stopped", tur={"task_id": "a1"})]
        self.s.write(self.s.main, [Rows.prompt(STARTED)] + before + stop + after, NOW - 200)
        self.s.agent("a1", [Rows.prompt(NOW - 1200), Rows.call(NOW - 1190, "t1", "Bash")], NOW - 1190)
        mm_size = os.path.getsize(self.s.main)
        self.assertGreater(mm_size, 4 << 20, "large enough for the bisection to run")
        st = self.state("a1")
        self.assertEqual((st["state"], st["stoppedBy"]), ("stopped", "TaskStop"))

    def test_a_stops_result_beyond_a_large_record_still_counts(self):
        """A multi-megabyte record between a TaskStop and its result (a request record, an image result) does
        not hide the result."""
        big = '{"type":"api-request","sessionId":"x","params":{"messages":"%s"}}' % ("z" * (6 << 20))
        self.s.append_main([Rows.call(NOW - 500, "ts1", "TaskStop", {"task_id": "a1"}, msg="m-ts1")])
        with open(self.s.main, "a") as f:
            f.write(big + "\n")
        self.s.append_main([Rows.result(NOW - 499, "ts1", "stopped", tur={"task_id": "a1"})])
        self.s.agent("a1", [Rows.prompt(NOW - 900), Rows.call(NOW - 800, "t1", "Bash")], NOW - 800)
        st = self.state("a1")
        self.assertEqual((st["state"], st["stoppedBy"]), ("stopped", "TaskStop"))

    def test_a_failed_agent_stays_failed_once_its_process_ends(self):
        self.s.agent("f1", [Rows.prompt(NOW - 900), Rows.api_error(NOW - 850)], NOW - 850, meta={"finished": True})
        for live in (True, False):
            self.assertEqual(self.state("f1", live=live)["state"], "failed", live)
        self.s.agent("f2", [Rows.prompt(STARTED - 900), Rows.api_error(STARTED - 850)], STARTED - 850,
                     meta={"finished": True})
        self.assertEqual(self.state("f2")["state"], "failed", "of an earlier process")
        self.assertEqual([e["agentId"] for e in self.s.view(live=False).done(5)], ["f1", "f2"])
        self.assertTrue(all(e["state"] == "failed" for e in self.s.view(live=False).done(5)))

    def test_a_transcript_with_no_readable_row_falls_back_to_its_meta(self):
        self.s.agent("a1", ["not json at all"], STARTED - 5000, meta={"finished": True})
        self.assertEqual(self.state("a1")["state"], "completed")

    def test_the_main_loop_is_read_once_and_only_as_far_back_as_asked(self):
        """Many agents waiting on shells cost one read of the main loop's rows since the process started (its
        TaskStops and the bridge's stop notes), not a read per task; rows from before are not read."""
        old = [Rows.prompt(STARTED - 86400 * 3 + i) for i in range(4000)]   # days of history, megabytes of it
        for r in old:
            r["message"]["content"] = "x" * 600
        early = {"type": "user", "uuid": "note-0", "timestamp": ts(STARTED - 86400 * 4), "isMeta": True,
                 "origin": {"kind": "plugin", "name": "sminos"},
                 "message": {"role": "user", "content": "Task bs3, a background task, was stopped from the desk: it "
                                                         "is not running."}}
        self.s.write(self.s.main, [early] + old, STARTED - 100)
        self.s.append_main([{"type": "user", "uuid": "note-1", "timestamp": ts(NOW - 60), "isMeta": True,
                             "origin": {"kind": "plugin", "name": "sminos"},
                             "message": {"role": "user", "content": "Task bs1, a background task, was stopped from "
                                                                     "the desk: it is not running."}}])
        for i in range(6):
            rows = [Rows.prompt(NOW - 600), *Rows.bg_bash(NOW - 590, "t1", "bs%d" % i), Rows.reply(NOW - 580)]
            self.s.agent("w%d" % i, rows, NOW - 580, meta={"finished": True})
        calls = []
        real = V.offset_since

        def counted(mm, t):
            calls.append(t)
            return real(mm, t)

        V.offset_since = counted
        self.addCleanup(setattr, V, "offset_since", real)
        v = self.s.view()
        states = {i: v.state("w%d" % i)["state"] for i in range(6)}
        self.assertEqual(states, {0: "waiting", 1: "completed", 2: "waiting", 3: "waiting", 4: "waiting",
                                  5: "waiting"}, "a stop note from before the process started is not read")
        self.assertEqual(calls, [STARTED - V.EVIDENCE_MARGIN], "the main loop read once, back to the process start")

    def test_plain_list_counts_cheaply(self):
        """`sminos list`'s line: the engine's running agents, else the open turns of the running process from the
        tails alone; never the main loop's rows or the background reads."""
        self.s.agent("r1", [Rows.prompt(NOW - 60), Rows.call(NOW - 50, "t1", "Bash")], NOW - 50)
        self.s.agent("c1", [Rows.prompt(NOW - 600), *Rows.bg_bash(NOW - 590, "t1", "bs1"), Rows.reply(NOW - 580)],
                     NOW - 580, meta={"finished": True})
        self.s.agent("o1", [Rows.prompt(STARTED - 900), Rows.call(STARTED - 800, "t1", "Bash")], STARTED - 800)

        def refuse(*_a, **_k):
            raise AssertionError("the deep reads ran")

        for name in ("live_background", "offset_since"):
            real = getattr(V, name)
            setattr(V, name, refuse)
            self.addCleanup(setattr, V, name, real)
        self.assertEqual(self.s.view().live_summary(), {"source": "disk", "open": 1})
        bridge = [{"agentId": "r1", "running": True, "subagentType": "x"}, {"agentId": "c1", "running": False}]
        self.assertEqual(self.s.view(bridge=bridge).live_summary(), {"source": "engine", "running": 1})

    # -- what the disk holds
    def test_missing_meta_keys_unreadable_and_malformed_metas(self):
        self.s.agent("m0", [Rows.prompt(NOW - 60), Rows.reply(NOW - 50)], NOW - 50, meta_text="{}")
        self.s.agent("m1", [Rows.prompt(NOW - 60), Rows.reply(NOW - 50)], NOW - 50, meta_text="{not json")
        self.s.agent("m2", [Rows.prompt(NOW - 60), Rows.reply(NOW - 50)], NOW - 50, meta_text="[1, 2]")
        v = self.s.view()
        e = v.entry("m0")
        self.assertEqual((e["type"], e["description"], e["parentAgentId"], e["model"], e["worktree"]),
                         ("?", "", None, None, None))
        self.assertEqual(e["state"], "completed")
        self.assertTrue(v.entry("m1")["metaUnread"] and v.entry("m2")["metaUnread"])
        self.assertEqual(len(v.notes), 1)
        self.assertIn("2 agent meta files could not be read (m1, m2)", v.notes[0])

    def test_request_records_are_passed_over(self):
        rows = [Rows.prompt(NOW - 60), Rows.call(NOW - 50, "t1", "Bash"), REQUEST, REQUEST]
        self.s.agent("a1", rows, NOW - 40)
        self.assertEqual(self.state("a1")["tool"]["name"], "Bash")

    def test_workflow_agents_and_agents_the_bridge_alone_knows(self):
        wf = self.s.sub / "workflows" / "wf_1"
        wf.mkdir(parents=True)
        self.s.agent("w1", [Rows.prompt(NOW - 60), Rows.reply(NOW - 50)], NOW - 50, d=wf,
                     meta={"agentType": "workflow-subagent"})
        bridge = [{"agentId": "b1", "running": True, "subagentType": "Explore", "description": "look"},
                  {"agentId": "x1", "agentType": "", "running": False}]
        v = self.s.view(bridge=bridge)
        self.assertEqual(v.entry("w1")["workflow"], "wf_1")
        self.assertEqual((v.state("b1")["state"], v.entry("b1")["type"]), ("running", "Explore"))
        self.assertNotIn("x1", v.agents, "an agent known only by a SubagentStop, never spawned, is the engine's own")

    # -- views
    def test_the_tree_by_parent_in_spawn_order_and_its_depth_limit(self):
        # Spawn order is each transcript's first row, the prompt (never a file's birth time, which only some
        # filesystems keep): r1, c1, g1, g2, r2, whatever order or times the files were written in.
        spawned = {"r1": NOW - 2400, "c1": NOW - 2399, "g1": NOW - 2398, "g2": NOW - 2397, "r2": NOW - 2396}
        for agent, parent in (("r2", None), ("g2", "c1"), ("g1", "c1"), ("c1", "r1"), ("r1", None)):
            if agent == "g2":   # stalled: its last write long ago
                rows = [Rows.prompt(spawned[agent]), Rows.result(NOW - 1900, "t0")]
                at = NOW - 1900
            else:
                rows = [Rows.prompt(spawned[agent]), Rows.call(NOW - 50, "t1", "Bash")]
                at = NOW - 50
            self.s.agent(agent, rows, at, parent=parent)
        v = self.s.view()
        self.assertEqual([(e["agentId"], e["depth"]) for e in v.tree()],
                         [("r1", 0), ("c1", 1), ("g1", 2), ("g2", 2), ("r2", 0)])
        top = v.tree(depth=1)
        self.assertEqual([e["agentId"] for e in top], ["r1", "r2"])
        self.assertEqual(top[0]["folded"], {"count": 3, "states": {"running": 2, "stalled": 1}})
        self.assertIn("· +3 below (1 stalled)", V.state_text(top[0]))
        self.assertEqual(v.counts()["running"] + v.counts()["stalled"], 5, "the counts cover every depth")

    def test_ended_agents_fold_and_a_live_child_stands_under_its_nearest_live_ancestor(self):
        self.s.agent("r1", [Rows.prompt(NOW - 600), *Rows.handback(NOW - 500)], NOW - 499, meta={"finished": True})
        self.s.agent("c1", [Rows.prompt(NOW - 60), Rows.call(NOW - 50, "t1", "Bash")], NOW - 50, parent="r1")
        v = self.s.view()
        self.assertEqual([(e["agentId"], e["depth"]) for e in v.tree()], [("r1", 0), ("c1", 1)],
                         "a parent waiting on its background child is live itself")
        self.assertEqual(v.state("r1")["state"], "waiting")
        self.assertEqual([e["agentId"] for e in v.tree(every=True)], ["r1", "c1"])

    def test_done_is_the_ended_newest_first_with_its_outcome(self):
        self.s.agent("d1", [Rows.prompt(NOW - 900), Rows.reply(NOW - 800)], NOW - 800, meta={"finished": True})
        self.s.agent("d2", [Rows.prompt(NOW - 900), Rows.reply(NOW - 700)], NOW - 700, meta={"finished": True})
        self.s.agent("d3", [Rows.prompt(NOW - 900), Rows.call(NOW - 650, "t1", "Bash")], NOW - 600,
                     meta={"finished": True, "stoppedByUser": True})
        self.s.agent("l1", [Rows.prompt(NOW - 60), Rows.call(NOW - 50, "t1", "Bash")], NOW - 10)
        v = self.s.view()
        self.assertEqual([e["agentId"] for e in v.done(2)], ["d3", "d2"])
        self.assertEqual([e["agentId"] for e in v.done(10)], ["d3", "d2", "d1"])
        lines = V.done_lines(v.done(2))
        self.assertTrue(lines[0].endswith("stopped by user") and lines[1].endswith("completed"), lines)


class Cli(unittest.TestCase):
    """Through the real CLI, in a temp home: the session's record names this test's own process as its own."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="sminos-subagents-cli-")
        cls.addClassCleanup(cls.tmp.cleanup)
        home = Path(cls.tmp.name)
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith(("SMINOS_", "SMNS_", "CLAUDE_CODE_"))}
        cls.env.update(HOME=str(home), SMINOS_HOME=str(home / "registry"), DAEMON_HOST="testhost")
        (home / ".claude/sessions").mkdir(parents=True)
        cls.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock_path = tempfile.mktemp(prefix="sa", dir="/tmp")
        cls.sock.bind(sock_path)
        cls.sock.listen(8)
        cls.addClassCleanup(cls.sock.close)
        cls.addClassCleanup(os.unlink, sock_path)
        now = time.time()
        for name, sid, extra in (
                ("lead", SID, {}), ("peer", OTHER, {}),
                # No member: another tool's SDK run, its inbox listening; a spare parked until a host claims it;
                # one whose inbox does not listen.
                ("sdkrun", "5a000003-0000-4000-8000-0000000000a3", {"entrypoint": "sdk-ts", "status": "shell"}),
                ("spare", "5a000004-0000-4000-8000-0000000000a4", {"entrypoint": "sdk-ts", "status": "parked"}),
                ("deaf", "5a000005-0000-4000-8000-0000000000a5", {"entrypoint": "sdk-ts",
                                                                  "messagingSocketPath": sock_path + "-none"}),
                ("desk", "5a000006-0000-4000-8000-0000000000a6", {
                    "entrypoint": "claude-desktop", "hostSessionId": "local_1",
                    "formerNames": [{"name": "old-name", "until": int(now * 1000), "sessionId": "x"}]})):
            (home / (".claude/sessions/%s.json" % name)).write_text(json.dumps({
                "pid": os.getpid(), "sessionId": sid, "name": name, "nameSource": "user", "kind": "interactive",
                "entrypoint": "cli", "status": "busy", "cwd": str(home), "startedAt": int((now - 3600) * 1000),
                "updatedAt": int(now * 1000), "messagingSocketPath": sock_path, **extra}))
        s = Session(home)
        cls.session = s
        s.agent("aa00000000000001", [Rows.prompt(now - 900), Rows.call(now - 600, "t1", "Bash")], now - 600,
                meta={"agentType": "doperpowers:task-executor", "model": "opus", "description": "Build the thing",
                      "worktreePath": str(home / "wt/agent-1")})
        s.agent("aa00000000000002", [Rows.prompt(now - 500), Rows.call(now - 400, "t1", "Read")], now - 400,
                parent="aa00000000000001", meta={"agentType": "Explore", "description": "Look around"})
        s.agent("aa00000000000003", [Rows.prompt(now - 5000), *Rows.handback(now - 4900)], now - 4899,
                meta={"finished": True, "description": "Old review"})
        s.agent("aa00000000000004", [Rows.prompt(now - 5000), Rows.call(now - 4800, "t1", "Bash")], now - 4700,
                meta={"finished": True, "stoppedByUser": True, "description": "Stopped scan"})

    def cli(self, *args, session=SID, rc=0):
        env = dict(self.env, **({"CLAUDE_CODE_SESSION_ID": session} if session else {}))
        r = subprocess.run([sys.executable, str(CLI), *args], cwd=self.tmp.name, env=env, text=True,
                           capture_output=True)
        self.assertEqual(r.returncode, rc, "%s: %s\n%s" % (args, r.stdout, r.stderr))
        return r.stdout + r.stderr

    def test_text_says_who_you_are_the_counts_the_tree_and_what_ended(self):
        out = self.cli("list", "--subagents").splitlines()
        self.assertEqual(out[0], "you: lead [5a000001]")
        self.assertEqual(out[1], "subagents [2 running · 0 waiting on background · 0 stalled · 0 orphaned]")
        self.assertRegex(out[2], r"^  aa00000000000001  +doperpowers:task-executor \(opus\)  +Build the thing  +"
                                 r"running 15m \(disk\) · in Bash 10m  +wt ~/wt/agent-1$")
        self.assertRegex(out[3], r"^    aa00000000000002  +Explore  +Look around  +running 8m \(disk\) · in Read 6m$")
        self.assertEqual(out[4], "  +2 ended (1 completed · 1 stopped) — sminos list --subagents --done 10")
        self.assertEqual(out[5], "note: no bridge runs in this session: lifecycle is inferred from its transcripts")

    def test_depth_folds_the_levels_below(self):
        out = self.cli("list", "--subagents", "--depth", "1")
        self.assertRegex(out, r"aa00000000000001 .* · in Bash 10m · \+1 below  wt ")
        self.assertNotIn("aa00000000000002", out)

    def test_json_is_an_envelope_with_every_agent(self):
        d = json.loads(self.cli("list", "--subagents", "--json").split("\nnote:")[0])
        self.assertEqual(sorted(d), ["agents", "counts", "notes", "scope", "self"])
        self.assertEqual(d["self"], {"session": SID, "short": SID[:8], "alias": "lead"})
        self.assertEqual((d["scope"]["session"], d["scope"]["inspectionOnly"], d["scope"]["bridge"]),
                         (SID, False, "none"))
        self.assertEqual(len(d["agents"]), 4, "--json keeps every agent, the ended too")
        self.assertEqual(d["counts"]["completed"], 1)
        self.assertTrue(d["notes"])

    def test_done_lists_the_ended_with_their_outcome(self):
        out = self.cli("list", "--subagents", "--done", "5").splitlines()
        self.assertEqual(out[1], "ended subagents, the 5 ended last, newest first:")
        self.assertRegex(out[2], r"aa00000000000004 .*Stopped scan +stopped by user$")
        self.assertRegex(out[3], r"aa00000000000003 .*Old review +completed$")
        self.assertEqual(out[4], "SendMessage to an agentId resumes that agent, when its work should go on")
        d = json.loads(self.cli("list", "--subagents", "--done", "1", "--json"))
        self.assertEqual([e["agentId"] for e in d["agents"]], ["aa00000000000004"])

    def test_another_members_tree_is_inspection_only(self):
        out = self.cli("list", "--subagents", SID, session=OTHER).splitlines()
        self.assertEqual(out[0], "you: peer [5a000002]")
        self.assertTrue(out[1].startswith("subagents of %s [5a000001] — inspection only: SendMessage reaches only "
                                          "your own session's subagents" % SID), out[1])
        d = json.loads(self.cli("list", "--subagents", "lead", "--json", session=OTHER))
        self.assertTrue(d["scope"]["inspectionOnly"])
        self.assertTrue(all(e["inspectionOnly"] for e in d["agents"]))

    def test_outside_a_session_a_member_must_be_named(self):
        out = self.cli("list", "--subagents", session=None, rc=2)
        self.assertIn("name whose subagents", out)
        self.assertIn("inspection only", self.cli("list", "--subagents", SID, session=None))

    def test_here_ends_with_the_live_sessions_that_are_no_member(self):
        out = self.cli("list", "--here", session=OTHER)
        tail = out.split("other live sessions (not members)\n", 1)[1].splitlines()
        self.assertRegex(tail[0], r"^  sdkrun \[5a000003\]  interactive  shell  sdk-ts  started 1h$")
        self.assertTrue(tail[1].startswith("you: "), "the spare, the deaf one and the caller are left out: %s" % tail)
        self.assertRegex(out, r"desk \[5a000006\]  interactive desktop ", "a Claude Desktop session is marked")
        rows = json.loads(self.cli("list", "--here", "--json", session=None))
        others = [r for r in rows if r.get("member") is False]
        self.assertEqual([r["alias"] for r in others], ["sdkrun"])
        self.assertEqual(others[0]["engine"]["status"], "shell")
        desk = next(r for r in rows if r["alias"] == "desk")
        self.assertEqual((desk["engine"]["desktop"], desk["engine"]["formerName"], desk["engine"]["status"]),
                         (True, "old-name", "busy"))
        self.assertAlmostEqual(desk["engine"]["startedAge"], 3600, delta=120)

    def test_a_session_with_no_subagents_says_where_it_looked(self):
        out = self.cli("list", "--subagents", OTHER, session=None)
        self.assertIn("(no subagents in session 5a000002", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
