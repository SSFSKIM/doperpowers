#!/usr/bin/env python3
"""The wake (T2's M2: docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md,
the milestone's "Proves"; Interfaces §3), against the test engine:

- every row of §3's table, for a thread its human opened by a direct call
  of `sminos.wake` (no delivery path wakes one yet) and, where the row is a
  seat's too, for a seat through the verbs and delivery;
- a seat's message pushed once, through its inbox, opened by the wake's
  line, after a wake that carried no message; the name kept; the seat's
  `turns` and `status` written at the push, no `pending_short`;
- `resume` recording its message as `send` records one; `--wait` printing
  the reply to its own message when another sender's is answered after it;
- a copy removed (and one that cannot be, stopped and said); a failed first
  wake leaving no row and the next passing flags; a row there before never
  removed; a launch that timed out with its process read as live; a second
  wake while the first holds the lock; the one function that launches.

The transitions against a wake are test_wake_transitions.py's.

Hermetic: test_wake.Engine (HOME, SMINOS_HOME and the engine's state
temporary, the engine first on PATH, every teardown failing on a resume
that carried a message).
Run: python3 -B sminos/tests/test_wake_seat.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_wake import Engine, line_of, sminos, threads, wake, wait_for  # noqa: E402
import sminos_records as records  # noqa: E402
import wake_engine  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts", "sminos.py")
INBOX = os.path.join(HERE, "inbox_standin.py")


def interleave_hook(case, sid):
    """The record hook of a process that comes up holding the session, made to land inside the next count of a
    failed wake: just before that count's write, between the record's read and its compare-and-set. The list it
    returns holds that process once it came up."""
    real, came_up = threads.update, []

    def update(thread_id, fields, *a, **k):
        if not came_up and "failed" in (fields.get("waking") or {}):
            came_up.append(case.session(sid=sid, kind="bg")[1])
            case.assertTrue(threads.stop_seen(sid), "the hook cleared the accepted job")
        return real(thread_id, fields, *a, **k)
    p = mock.patch.object(threads, "update", update)
    p.start()
    case.addCleanup(p.stop)
    case.addCleanup(lambda: [case.end(proc) for proc in came_up])
    return came_up


class Wakers(Engine):
    """The engine first on PATH, polls short."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"SMINOS_POLL_INTERVAL": "0.05", "SMINOS_UUID_POLL": "60"})
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- a thread its human opened

    def human_thread(self, mode="auto"):
        """A thread its human opened in a terminal that has exited: its record, its transcript, no row."""
        sid = self.opened(mode)
        _, proc = self.session(sid=sid)
        self.reconcile()
        self.end(proc)
        t = threads.thread_of(sid)
        self.assertEqual(t["opened"], "human")
        return t["thread"], sid

    def wake(self, sid, **kw):
        sminos.forget_caches()
        t = threads.thread_of(sid) or {"thread": "none"}
        return sminos.wake(t, sid, **{"due": True, **kw})

    def record_file(self, tid):
        return os.path.join(threads.store_dir(), tid + ".json")

    def edit(self, tid, **fields):
        path = self.record_file(tid)
        with open(path) as f:
            rec = json.load(f)
        rec.update(fields)
        with open(path, "w") as f:
            json.dump(rec, f)
        sminos.forget_caches()

    # -- the engine's view

    def calls(self):
        try:
            with open(os.path.join(self.state, "calls.log")) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def resumes(self, sid=None):
        """Every wake's argv tail after the id (the flags), in order."""
        return [c["argv"][3:] for c in self.calls()
                if c["argv"][:2] == ["--bg", "--resume"] and (sid is None or c["argv"][2] == sid)]

    def removals(self):
        return [c["argv"][1] for c in self.calls() if c["argv"][:1] == ["rm"]]

    def launches(self):
        return wake_engine.launches(self.state)

    def stop(self, sid):
        self.claude("stop", sid[:8])
        self.assertTrue(wait_for(lambda: self.record(sid) is None), "its process ended")
        sminos.forget_caches()

    def waking(self, tid, sid):
        sminos.forget_caches()
        return threads.waking(threads.get(tid), sid)

    def log(self):
        """Every event of the project's log."""
        d = sminos.project_path(self.p, "log")
        out = []
        for name in sorted(os.listdir(d)):
            if name.endswith(".jsonl"):
                with open(os.path.join(d, name)) as f:
                    out += [json.loads(line) for line in f if line.strip()]
        return out

    def daemon_log(self):
        try:
            with open(os.path.join(sminos.root(), "daemon.log")) as f:
                return f.read()
        except OSError:
            return ""

    def terminal(self, sid, name="term-a"):
        """A terminal's process holding the session (its engine record, kind `interactive`) with an inbox of
        its own; the path of the file its inbox appends every frame to."""
        _, proc = self.session(sid=sid, kind="interactive", name=name)
        sock = os.path.join(self.home, "t-%s.sock" % sid[:8])
        received = sock + ".received"
        open(received, "a").close()
        server = subprocess.Popen([sys.executable, "-B", INBOX, sock, received])
        self.addCleanup(lambda: (server.kill(), server.wait()))
        wait_for(lambda: sminos.socket_ok(sock))
        self.peer_set(proc, messagingSocketPath=sock, nameSource="user")
        return received

    def received(self, path):
        with open(path) as f:
            return [json.loads(line)["message"]["content"] for line in f if line.strip()]

    # -- a seat

    def seat(self, alias="w"):
        """A seat spawned through the engine, its first turn run and its process stopped."""
        code, out = self.cli("spawn", alias, "the task")
        self.assertEqual(code, 0, out)
        s = next(x for x in sminos.seats() if x["alias"] == alias)
        sid = s["current"]
        self.assertTrue(wait_for(lambda: self.record(sid) is not None))
        self.stop(sid)
        return sminos.reload_seat(s["seat_id"])


# ------------------------------------------------------------ a thread its human opened, by direct call


class Human(Wakers):
    def test_a_first_wake_runs_with_its_last_turns_flags_where_its_human_opened_it_and_keeps_its_name(self):
        tid, sid = self.human_thread()
        elsewhere = os.path.join(self.home, "elsewhere")
        os.makedirs(elsewhere)
        here = os.getcwd()
        os.chdir(elsewhere)
        self.addCleanup(os.chdir, here)
        got = self.wake(sid)
        self.assertEqual((got.live, got.why, got.short), (True, "", sid[:8]))
        [call] = [c for c in self.calls() if c["argv"][:1] == ["--bg"]]
        self.assertEqual(call["argv"], ["--bg", "--resume", sid, "--permission-mode", "auto", "--model",
                                        "claude-term"], "a first wake's flags, no message after them")
        self.assertEqual(call["cwd"], self.root, "issued in the directory its human opened it in, not the caller's")
        rec = self.record(sid)
        self.assertEqual((rec["kind"], rec["name"], rec["cwd"]), ("bg", "term-a", self.root), "its name kept")
        line = self.waking(tid, sid)["line"]
        self.assertEqual((line["first"], line["mode"], line["model"]), (True, "auto", "claude-term"))
        self.assertEqual(self.turns(sid)[-1]["type"], "assistant", "no turn ran: the wake hands it nothing")
        self.assertNotIn("pending_short", json.dumps(threads.get(tid)))

    def test_a_later_wake_passes_no_flag_and_runs_under_its_row(self):
        tid, sid = self.human_thread()
        self.assertTrue(self.wake(sid).live)
        self.stop(sid)
        got = self.wake(sid)
        self.assertTrue(got.live)
        self.assertEqual(self.resumes(sid), [["--permission-mode", "auto", "--model", "claude-term"], []])
        line = self.waking(tid, sid)["line"]
        self.assertEqual((line["first"], line["mode"]), (False, "auto"), "the row's options in the line")

    def test_rows_that_launch_nothing(self):
        cases = {
            "live": lambda tid, sid: self.session(sid=sid, kind="interactive"),
            "gone": lambda tid, sid: self.edit(tid, current="11111111-2222-4333-8444-555555555555"),
            "ended": lambda tid, sid: self.edit(tid, ended={"at": sminos.now(), "pid": None}),
            "pending": lambda tid, sid: self.edit(tid, pending={"id": "x1", "op": "end", "events": []}),
            "lane": lambda tid, sid: records.set_controller(sid, "B"),
            "unknown jobs": lambda tid, sid: self.switch("agents-fail"),   # row 8: a signal it cannot read
            "transcript": lambda tid, sid: os.unlink(sminos.transcript_now(sid)),
            "failed": lambda tid, sid: self.edit(tid, waking={"session": sid, "failed": 1, "at": sminos.now()}),
            "unknown": lambda tid, sid: self.unreadable_record(sid),
        }
        for case, make in cases.items():
            why = case.split()[0]
            with self.subTest(why=case):
                tid, sid = self.human_thread()
                make(tid, sid)
                got = self.wake(sid, due=why != "failed")
                self.assertEqual((got.live, got.why), (why == "live", "" if why == "live" else why))
                self.assertEqual(self.resumes(sid), [], "nothing launched")
                for name in ("agents-fail",):
                    try:
                        os.unlink(os.path.join(self.state, name))
                    except OSError:
                        pass

    def unreadable_record(self, sid):
        path = records.record_path(sid)
        with open(path, "w") as f:
            f.write("{")

    def test_an_ended_thread_its_human_opened_is_never_returned_by_a_wake(self):
        tid, sid = self.human_thread()
        self.edit(tid, ended={"at": sminos.now(), "pid": None})
        self.assertEqual(self.wake(sid).why, "ended")
        self.assertEqual(self.wake(sid, returns=True).why, "ended", "a return is a spawned thread's seat's alone (§3)")
        self.assertEqual(self.resumes(sid), [])

    def test_a_thread_record_there_and_unreadable_is_unknown_not_gone(self):
        tid, sid = self.human_thread()
        t = threads.thread_of(sid)
        with open(self.record_file(tid), "w") as f:
            f.write("{")
        sminos.forget_caches()
        got = sminos.wake(t, sid, due=True)
        self.assertEqual((got.live, got.why), (False, "unknown"), "row 3: present but unreadable")
        self.assertEqual(self.resumes(sid), [])

    def test_a_reopening_by_hand_answers_a_copy_which_is_removed_and_nothing_is_remembered(self):
        tid, sid = self.human_thread()
        for held in ("open", "running"):
            with self.subTest(held=held):
                self.switch("held", held)
                got = self.wake(sid)
                self.assertEqual((got.live, got.why), (False, "starting"), "no process of its own holds it yet")
                [copy] = self.removals()[-1:]
                self.assertNotEqual(copy, sid[:8])
                self.assertIsNone(self.job(copy), "the copy is gone from the job list")
                waking = self.waking(tid, sid)
                self.assertNotIn("line", waking, "its line removed")
                self.assertNotIn("failed", waking, "nothing counted")
        os.unlink(os.path.join(self.state, "held"))
        _, proc = self.session(sid=sid, kind="interactive")   # the terminal's process
        launched = self.launches()
        self.assertTrue(self.wake(sid).live, "the terminal's process holds it: live, nothing launched")
        self.assertEqual(self.launches(), launched)

    def test_a_copy_that_cannot_be_removed_is_stopped_and_said(self):
        tid, sid = self.human_thread()
        self.switch("held", "open")
        self.switch("rm-refuses")
        self.wake(sid)
        [copy] = self.removals()
        self.assertEqual(self.job(copy)["state"], "stopped")
        self.assertIn("a wake's copy %s (the session was held) could not be removed; it was stopped" % copy,
                      self.daemon_log())

    def test_a_copy_that_can_be_neither_removed_nor_stopped_is_said_as_one_that_may_still_run(self):
        tid, sid = self.human_thread()
        self.switch("held", "open")
        self.switch("rm-refuses")
        with mock.patch.object(sminos, "claude_stop", lambda short: False):
            self.wake(sid)
        [copy] = self.removals()
        log = self.daemon_log()
        self.assertIn("a wake's copy %s (the session was held) could not be removed, and claude stop failed: it may "
                      "still run" % copy, log)
        self.assertNotIn("it was stopped", log)

    def test_a_failed_launch_is_said_with_its_option_names_and_no_value_or_argument_vector(self):
        tid, sid = self.human_thread()
        settings = os.path.join(self.home, "kept-settings.json")
        with open(settings, "w") as f:
            json.dump({}, f)
        self.edit(tid, launch=dict(threads.get(tid).get("launch") or {}, options=["--settings", settings]))
        self.switch("barrier")   # the launch blocks: it times out with no process of the session
        try:
            with mock.patch.dict(os.environ, {"SMINOS_LAUNCH_TIMEOUT": "1"}):
                got = self.wake(sid)
        finally:
            os.unlink(os.path.join(self.state, "barrier"))
        self.assertEqual((got.live, got.why), (False, "failed"))
        log = self.daemon_log()
        self.assertIn("the wake of %s failed: the launch failed (options --permission-mode, --model, --settings; "
                      "timed out after 1s)" % sid[:8], log)
        for leaked in (settings, self.home, "--resume", sid, "Command"):
            self.assertNotIn(leaked, log)

    def test_the_engine_s_message_is_said_with_its_paths_removed(self):
        self.assertEqual(sminos.engine_said("Error: cannot read /a/b/settings.json (see ~/.claude/x.log): "
                                            "path='/c d' and/or x"),
                         "Error: cannot read <path> (see <path>): path='<path> d' and/or x")
        out = sminos.LaunchOutput("No conversation found in /a/b", status=1)
        self.assertEqual(sminos.launch_failed(["--model", "m"], out),
                         "the launch failed (options --model; exit 1): No conversation found in <path>")

    def test_an_unexpected_copy_is_removed_and_counted(self):
        tid, sid = self.human_thread()
        self.switch("silent-copy")
        got = self.wake(sid)
        self.assertEqual((got.live, got.why), (False, "failed"))
        [copy] = self.removals()
        self.assertIsNone(self.job(copy))
        waking = self.waking(tid, sid)
        self.assertEqual((waking["failed"], "line" in waking), (1, False))

    def test_an_unreadable_row_answered_with_a_copy_is_woken_again_with_no_flag_and_the_next_passes_none(self):
        tid, sid = self.human_thread()
        self.switch("row-elsewhere")   # the engine's rows where sminos does not look: no `jobs` directory here
        self.assertTrue(self.wake(sid).live)
        self.stop(sid)
        got = self.wake(sid)
        self.assertTrue(got.live, got)
        flagged = ["--permission-mode", "auto", "--model", "claude-term"]
        self.assertEqual(self.resumes(sid), [flagged, flagged, []], "the copy's answer, then the same with none")
        [copy] = self.removals()
        self.assertIsNone(self.job(copy))
        self.assertTrue(self.waking(tid, sid)["saved"])
        self.stop(sid)
        self.assertTrue(self.wake(sid).live)
        self.assertEqual(self.resumes(sid)[-1], [], "the next wake passes none")

    def test_a_failed_first_wake_leaves_no_row_and_the_next_passes_flags(self):
        for with_flags in (True, False):
            with self.subTest(flags=with_flags):
                tid, sid = self.human_thread("auto" if with_flags else "default")
                if not with_flags:
                    # Nothing to pass: no mode, no model the launch or a turn names.
                    self.edit(tid, launch={"cwd": self.root, "at": sminos.now(), "options": []})
                    with open(sminos.transcript_now(sid), "w") as f:
                        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
                    sminos.forget_caches()
                os.makedirs(os.path.join(self.config(), "jobs"), exist_ok=True)   # W4 reads "no row", not unreadable
                self.switch("fail-before-start")
                got = self.wake(sid)
                self.assertEqual((got.live, got.why), (False, "failed"))
                self.assertIn(sid[:8], self.removals(), "its own failed row removed")
                self.assertIsNone(wake.row_of(sid))
                self.assertEqual(self.waking(tid, sid)["failed"], 1, "counted, as a failed wake is")
                os.unlink(os.path.join(self.state, "fail-before-start"))
                self.assertTrue(self.wake(sid).live)
                flags = self.resumes(sid)
                self.assertEqual(flags[0], flags[1], "the next wake passes the first's flags again")

    def test_a_row_there_before_the_launch_is_never_removed(self):
        for switch in ("fail-before-start", "fail-job", "silent-copy"):
            with self.subTest(switch=switch):
                tid, sid = self.human_thread()
                self.assertTrue(self.wake(sid).live)
                self.stop(sid)
                self.switch(switch)
                got = self.wake(sid)
                self.assertEqual((got.live, got.why), (False, "failed"))
                self.assertNotIn(sid[:8], self.removals())
                self.assertIsInstance(wake.row_of(sid), dict, "the row is still there")
                os.unlink(os.path.join(self.state, switch))

    def test_a_failed_first_wake_whose_row_cannot_be_removed_is_said_and_the_next_passes_no_flag(self):
        tid, sid = self.human_thread()
        os.makedirs(os.path.join(self.config(), "jobs"), exist_ok=True)
        self.switch("fail-before-start")
        self.switch("rm-refuses", sid[:8])
        self.assertEqual(self.wake(sid).why, "failed")
        self.assertIn("the failed first wake of %s left its row: claude rm %s" % (sid[:8], sid[:8]),
                      self.daemon_log())
        for name in ("fail-before-start", "rm-refuses"):
            os.unlink(os.path.join(self.state, name))
        self.assertTrue(self.wake(sid).live)
        self.assertEqual(self.resumes(sid)[-1], [], "a row there: no flag")

    def test_a_line_that_cannot_be_written_launches_nothing(self):
        # W4's write refused: an entry opened after W2 (an older copy's retire takes no wake lock) is the table's
        # `pending`; a write refused otherwise is `unknown`. Either way nothing is launched on what was read.
        tid, sid = self.human_thread()
        real = threads.wake_line

        def opened(t, s, line, lock_until=None):
            self.edit(tid, pending={"id": "e1", "op": "retire", "events": []})
            return real(t, s, line, lock_until)
        with mock.patch.object(threads, "wake_line", opened):
            got = self.wake(sid)
        self.assertEqual((got.live, got.why), (False, "pending"))
        self.assertEqual(self.launches(), 0, "nothing launched")
        self.assertNotIn("line", threads.waking(threads.get(tid), sid))
        self.edit(tid, pending=None)
        with mock.patch.object(threads, "wake_line", lambda *a, **k: False):
            got = self.wake(sid)
        self.assertEqual((got.live, got.why), (False, "unknown"))
        self.assertEqual(self.launches(), 0, "nothing launched")

    def test_a_ceiling_lowered_after_w2_holds_the_launch_for_mode(self):
        # Eligibility read the ceiling at W2; the flags read it again: a launch whose own mode flag asks for
        # approval is not made (held, `mode`), whatever W2 read.
        tid, sid = self.human_thread()
        self.ceiling("auto")
        real = sminos.stop_lingering

        def lowered(session, row):
            self.ceiling("default")
            return real(session, row)
        with mock.patch.object(sminos, "stop_lingering", lowered):
            got = self.wake(sid)
        self.assertEqual((got.live, got.why), (False, "mode"))
        self.assertEqual(self.launches(), 0, "nothing launched")
        self.assertNotIn("failed", self.waking(tid, sid), "nothing counted")

    def test_a_process_late_to_publish_is_starting_then_live(self):
        tid, sid = self.human_thread()
        self.switch("late-process", 1.5)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "4"}):
            got = self.wake(sid)
        self.assertEqual((got.live, got.why, got.short), (False, "starting", sid[:8]))
        self.assertNotIn("failed", self.waking(tid, sid), "nothing counted")
        self.assertTrue(wait_for(lambda: self.record(sid) is not None))
        launched = self.launches()
        self.assertTrue(self.wake(sid).live)
        self.assertEqual(self.launches(), launched, "once it publishes, live with no second launch")

    def test_a_job_accepted_and_still_starting_is_neither_stopped_nor_launched_beside(self):
        # A banner named this session's job and its process is not there at W7's bound (frontier review,
        # scalpel-3#6): the job is remembered, and the next wake, within its grace, stops nothing and launches
        # nothing; once the process is up it is live with no second launch, and the job is forgotten.
        tid, sid = self.human_thread()
        self.switch("late-process", 2.5)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "4"}):
            got = self.wake(sid)
            self.assertEqual((got.live, got.why), (False, "starting"))
            self.assertEqual(self.waking(tid, sid)["job"]["short"], sid[:8], "the accepted job noted")
            before = len(self.calls())
            for _ in range(2):
                again = self.wake(sid)
                self.assertEqual((again.live, again.why), (False, "starting"))
        self.assertEqual(self.launches(), 1, "no second launch")
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] in (["stop"], ["rm"])], "nothing stopped")
        self.assertTrue(wait_for(lambda: self.record(sid) is not None))
        self.assertTrue(self.wake(sid).live)
        self.assertEqual(self.launches(), 1)
        sminos.daemon_module().sweep_threads()
        self.assertNotIn("job", self.waking(tid, sid), "forgotten once a process is seen holding the session")

    def test_a_job_accepted_whose_grace_passed_lingers_as_any_other(self):
        # Past its grace with no process seen, that launch failed (round 2, scalpel-2#1): counted, so a wake on the
        # schedule waits; a sender's own call stops the job as lingering and launches again.
        tid, sid = self.human_thread()
        self.switch("late-process", 30)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "2", "SMINOS_WAKE_GRACE": "0.3"}):
            self.assertEqual(self.wake(sid).why, "starting")
            time.sleep(0.4)
            os.unlink(os.path.join(self.state, "late-process"))
            self.assertEqual(self.wake(sid, due=False).why, "failed", "counted: the schedule holds the next")
            self.assertEqual(self.waking(tid, sid)["failed"], 1)
            got = self.wake(sid)
        self.assertTrue(got.live, got)
        self.assertTrue([c for c in self.calls() if c["argv"][:1] == ["stop"]], "stopped as lingering")
        self.assertEqual(self.launches(), 2, "launched again")

    def test_a_job_accepted_and_read_failed_is_a_failed_wake_and_a_due_one_goes_on(self):
        tid, sid = self.human_thread()
        self.switch("late-process", 30)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "2"}):
            self.assertEqual(self.wake(sid).why, "starting")
        self.claude("stop", sid[:8])   # its worker gone before it published,
        path = os.path.join(self.state, "jobs", sid[:8] + ".json")
        with open(path) as f:
            entry = json.load(f)
        with open(path, "w") as f:
            json.dump(dict(entry, state="failed"), f)   # and its job read as failed
        os.unlink(os.path.join(self.state, "late-process"))
        got = self.wake(sid)
        self.assertTrue(got.live, got)
        self.assertEqual(self.launches(), 2, "a sender's own call launches again")
        self.assertIn("the wake of %s failed: its job %s was accepted and never ran" % (sid[:8], sid[:8]),
                      self.daemon_log(), "the one that never ran counted")

    def test_a_hook_that_clears_the_accepted_job_before_its_count_wins(self):
        # Round 3: the wake reads its accepted job dead, and a process of the session comes up before the count
        # lands; its record hook (stop_seen, under the record's lock alone) clears the job first. The count is made
        # only while the record holds that very job, in the field's own compare-and-set: nothing is counted, and
        # the line stays for the process that runs.
        tid, sid = self.human_thread()
        self.switch("late-process", 30)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "2"}):
            self.assertEqual(self.wake(sid).why, "starting")
        line = self.waking(tid, sid)["line"]
        self.claude("stop", sid[:8])   # its job read dead by the next wake
        came_up = interleave_hook(self, sid)
        got = self.wake(sid)
        self.assertTrue(came_up, "the hook landed between the observation and the count")
        self.assertTrue(got.live, got)
        waking = self.waking(tid, sid)
        self.assertNotIn("failed", waking, "nothing counted")
        self.assertEqual(waking.get("line"), line, "the line kept for the process that runs")
        self.assertNotIn("accepted and never ran", self.daemon_log())
        self.assertEqual(self.launches(), 1, "nothing launched beside it")

    def test_a_launch_that_timed_out_with_its_process_running_is_live_through_w8(self):
        tid, sid = self.human_thread()
        threads.update(tid, {"stopped": sminos.now(), "swept": sminos.now()})
        self.edit(tid, waking={"session": sid, "failed": 2, "at": sminos.now()})
        self.switch("no-banner", 30)
        seen = []
        with mock.patch.dict(os.environ, {"SMINOS_LAUNCH_TIMEOUT": "1.5"}):
            got = sminos.wake(threads.get(tid), sid, due=True, on_live=seen.append)
        self.assertTrue(got.live, got)
        self.assertIsNotNone(self.record(sid))
        self.assertEqual(seen, [sid[:8]], "the caller's W8, with the short the process's record names")
        rec = threads.get(tid)
        self.assertNotIn("stopped", rec, "the stop mark lifted")
        self.assertNotIn("failed", threads.waking(rec, sid), "the failures cleared")
        self.assertEqual(threads.waking(rec, sid)["line"]["short"], sid[:8], "its line bound to that process's job")

    def lingering(self, between):
        """A thread woken once and stopped, its job's entry then reading working with no process (W3's job), and
        `between` run once W2 has read the thread and before W3: the wake's result, the thread's id and session,
        the job's short and how many stops it saw before the wake."""
        tid, sid = self.human_thread()
        self.assertTrue(self.wake(sid).live)
        self.stop(sid)
        short = sid[:8]
        path = os.path.join(self.state, "jobs", short + ".json")
        with open(path) as f:
            entry = json.load(f)
        with open(path, "w") as f:
            json.dump(dict(entry, state="working"), f)
        stops = len([c for c in self.calls() if c["argv"][:1] == ["stop"]])
        wm = sminos.wake_module()
        real = wm.row_of
        seen = []

        def w2_read(session):
            row = real(session)
            between(sid)
            return row
        with mock.patch.object(wm, "row_of", side_effect=w2_read):
            got = self.wake(sid, on_live=seen.append)
        self.assertEqual(seen, [], "no W8: this wake launched nothing")
        self.assertEqual(self.resumes(sid), [["--permission-mode", "auto", "--model", "claude-term"]], "no launch")
        self.assertNotIn("failed", self.waking(tid, sid), "nothing counted")
        self.assertEqual(len([c for c in self.calls() if c["argv"][:1] == ["stop"]]), stops, "nothing stopped")
        return got

    def test_a_job_list_that_stops_reading_before_w3_is_unknown_and_launches_nothing(self):
        got = self.lingering(lambda sid: self.switch("agents-fail"))
        self.assertEqual((got.live, got.why), (False, "unknown"))

    def test_a_process_back_before_w3_is_live_and_nothing_is_stopped_under_it(self):
        got = self.lingering(lambda sid: self.session(sid=sid, kind="bg"))
        self.assertEqual((got.live, got.why, got.short), (True, "", ""))

    def test_a_stop_whose_confirmation_cannot_be_read_is_unknown_and_launches_nothing(self):
        """W3's stop confirmed only by a job list that reads: one that stops reading right after `claude stop`
        is row 8 (unknown), no launch and no attempt spent."""
        tid, sid = self.human_thread()
        self.assertTrue(self.wake(sid).live)
        self.stop(sid)
        path = os.path.join(self.state, "jobs", sid[:8] + ".json")
        with open(path) as f:
            entry = json.load(f)
        with open(path, "w") as f:
            json.dump(dict(entry, state="working"), f)   # a lingering job: working, no process
        real, seen = sminos.claude_stop, []

        def stop_then_unlisted(short):
            ok = real(short)
            self.switch("agents-fail")
            return ok
        with mock.patch.object(sminos, "claude_stop", side_effect=stop_then_unlisted), \
                mock.patch.dict(os.environ, {"SMINOS_STOP_TIMEOUT": "1", "SMINOS_POLL_INTERVAL": "0.2"}):
            got = self.wake(sid, on_live=seen.append)
        self.assertEqual((got.live, got.why), (False, "unknown"))
        self.assertEqual(self.resumes(sid), [["--permission-mode", "auto", "--model", "claude-term"]], "no launch")
        self.assertEqual(seen, [])
        self.assertNotIn("failed", self.waking(tid, sid), "nothing counted")

    def test_a_second_wake_while_the_first_holds_the_lock_launches_nothing(self):
        tid, sid = self.human_thread()
        self.switch("barrier")
        results = []
        first = threading.Thread(target=lambda: results.append(sminos.wake(threads.thread_of(sid), sid, due=True)))
        first.start()
        self.assertTrue(wait_for(lambda: self.launches() == 1))
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.5):
            second = sminos.wake(threads.thread_of(sid), sid, due=True)
        self.assertEqual((second.live, second.why), (False, "in flight"))
        os.unlink(os.path.join(self.state, "barrier"))
        first.join(30)
        self.assertTrue(results[0].live)
        self.assertEqual(self.launches(), 1, "the engine's launch counter: one")


# ------------------------------------------------------------ a seat, through the verbs and delivery


class Seat(Wakers):
    def frames(self, sid):
        return [i["message"]["content"] for i in self.inputs(sid)]

    def test_a_send_wakes_it_and_its_message_arrives_once_closed_by_the_line(self):
        s = self.seat()
        sid = s["current"]
        before = len(self.frames(sid))
        code, out = self.cli("send", "w", "hello there")
        self.assertEqual(code, 0, out)
        self.assertIn("sent to %s/w (woken)" % s["group"], out)
        self.assertEqual(self.resumes(sid), [[]], "a row is there: no flag, and no message after the id")
        frames = self.frames(sid)[before:]
        self.assertEqual(len(frames), 1, "pushed once")
        pushed, said = line_of(frames[0])
        self.assertTrue(pushed.startswith("[sminos message from "), "the frame's header first")
        self.assertTrue(said.startswith(wake.LINE_HEAD), "the line after it")
        self.assertIn("You run under your saved options.", said)
        self.assertEqual(frames[0].count("hello there"), 1)
        self.assertEqual(self.record(sid)["name"], "w", "the name kept")
        fresh = sminos.reload_seat(s["seat_id"])
        self.assertEqual((fresh["status"], int(fresh["turns"])), ("working", int(s["turns"] or 0) + 1))
        self.assertNotIn("pending_short", json.dumps(threads.get(s["seat_id"])))
        self.assertNotIn("line", self.waking(s["seat_id"], sid), "the line went with the frame")
        code, out = self.cli("send", "w", "live now")
        self.assertIn("sent to %s/w" % s["group"], out)
        self.assertNotIn("(woken)", out)
        self.assertNotIn(wake.LINE_HEAD, self.frames(sid)[-1], "a live push carries no line")

    def test_a_first_wake_of_a_seat_whose_row_is_gone_says_nothing_of_a_terminal(self):
        s = self.seat()
        sid = s["current"]
        os.unlink(wake_engine.row_path(sid))   # its `jobs` directory kept: no row, a first wake
        before = len(self.frames(sid))
        code, out = self.cli("send", "w", "row gone")
        self.assertEqual(code, 0, out)
        self.assertIn("(woken)", out)
        self.assertTrue(self.resumes(sid)[-1], "a first wake's flags")
        [frame] = self.frames(sid)[before:]
        said = line_of(frame)[1]
        self.assertTrue(said.startswith(wake.LINE_HEAD))
        self.assertNotIn("terminal", said, "a spawned seat never ran in one")

    def test_resume_records_its_message_as_send_does_and_delivers_it(self):
        s = self.seat()
        sid = s["current"]
        code, out = self.cli("resume", "w", "carry on")
        self.assertEqual(code, 0, out)
        self.assertIn("resumed %s/w" % s["group"], out)
        [event] = [e for e in self.log() if e.get("text") == "carry on"]
        self.assertEqual(event["to"][0]["session"], sid, "recorded, addressed to its session")
        frame = self.frames(sid)[-1]
        self.assertEqual(frame.count("carry on"), 1)
        self.assertIn("id=%s" % event["msg_id"], frame, "the id a waiter looks for")
        self.assertEqual(self.resumes(sid), [[]])

    def test_a_tag_wakes_it_through_delivery(self):
        s = self.seat()
        sid = s["current"]
        code, out = self.cli("say", "@w over to you")
        self.assertEqual(code, 0, out)
        self.assertIn("w: sent (woken)", out, "a live push's words, woken (T2's §5)")
        self.assertEqual(sum("over to you" in f for f in self.frames(sid)), 1)

    def test_a_failed_wake_is_held_said_and_counted_in_waking_not_as_an_attempt(self):
        """M3: a failed wake holds the message for the thread (§4), its sender told why; the failure counts in
        `waking`, never as a delivery attempt."""
        s = self.seat()
        self.switch("fail-job")
        code, out = self.cli("say", "@w nobody home")
        self.assertIn("w: recorded and held: the session is stopped and is not woken: waking it failed, and its "
                      "machine tries again", out)
        self.assertEqual(self.waking(s["seat_id"], s["current"])["failed"], 1)
        record = sminos.delivered_load(self.p, s["current"])
        self.assertEqual({w: d.get("attempts", 0) for w, d in record.items()}, {"testhost/human": 0})
        self.assertTrue(record["testhost/human"].get("held"), "marked held")

    def test_wait_prints_the_reply_to_its_own_message_when_another_senders_is_answered_after_it(self):
        s = self.seat()
        sid = s["current"]
        self.switch("reply-delay", 1)
        before = len(self.inputs(sid))
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "send", "w", "mine", "--wait"], cwd=self.root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.assertTrue(wait_for(lambda: len(self.inputs(sid)) > before, timeout=30), "its frame arrived")
        self.push(sid, sminos.compose_frame("bee", "other001", "theirs"))
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, err)
        self.assertIn("reply to ", out)
        self.assertNotIn("other001", out, "another sender's reply is not this one's")
        self.assertTrue(self.replied(sid, "other001"), "the other was answered, after")

    def test_wait_ended_by_the_next_prompt_leaves_the_seat_to_the_turn_that_runs(self):
        """The next prompt delimits this message's reply; the later prompt's turn, still running, is not this
        waiter's to publish as idle."""
        s = self.seat()
        sid = s["current"]
        self.switch("reply-delay", 5)   # each turn: the waiter polls every 2s, so it returns inside the later one
        before = len(self.inputs(sid))
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "send", "w", "mine", "--wait"], cwd=self.root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.assertTrue(wait_for(lambda: len(self.inputs(sid)) > before, timeout=30), "its frame arrived")
        self.push(sid, sminos.compose_frame("bee", "other001", "theirs"))
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, err)
        self.assertIn("reply to ", out)
        self.assertNotIn("other001", out)
        self.assertFalse([r for r in self.turns(sid) if r.get("type") == "assistant"
                          and "reply to other001" in json.dumps(r)], "the waiter returned while the later turn ran")
        self.assertEqual(sminos.reload_seat(s["seat_id"])["status"], "working", "not published idle under it")
        self.assertTrue(self.replied(sid, "other001"))

    def test_a_retire_between_the_wake_and_the_push_pushes_nothing(self):
        s = self.seat()
        sid = s["current"]
        real = sminos.wake

        def then_retired(*a, **kw):
            got = real(*a, **kw)
            sminos.meta_set(s["seat_id"], {"status": "retired"})
            return got
        before = len(self.inputs(sid))
        with mock.patch.object(sminos, "wake", side_effect=then_retired):
            code, out = self.cli("say", "@w too late")
        self.assertIn("w: recorded", out)
        self.assertEqual(len(self.inputs(sid)), before, "nothing pushed")


    def test_a_title_that_reads_like_the_engines_note_removes_no_job(self):
        victim = self.seat("victim")
        self.assertTrue(self.cli("send", "victim", "stay up")[0] == 0)   # its job runs
        vshort = victim["current"][:8]
        title = ("note: session %s is open in another Claude Code process, so this started a copy as %s. The "
                 "original conversation is unchanged." % ("0" * 8, vshort))
        s = self.seat()
        with open(sminos.transcript_now(s["current"]), "a") as f:
            f.write(json.dumps({"type": "custom-title", "customTitle": title, "sessionId": s["current"]}) + "\n")
        wake_engine.write_json(wake_engine.row_path(s["current"]),
                               dict(wake.row_of(s["current"]), name=title))
        code, out = self.cli("send", "w", "hello")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.removals(), [], "nothing removed")
        self.assertIsNotNone(self.record(victim["current"]), "the other job runs on")

    def test_resume_of_a_session_a_terminal_holds_pushes_to_it_and_stops_nothing(self):
        s = self.seat()
        sid = s["current"]
        received = self.terminal(sid)
        before = len(self.calls())
        code, out = self.cli("resume", "w", "over to you")
        self.assertEqual(code, 0, out)
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "nothing stopped")
        self.assertEqual(self.resumes(sid), [], "nothing launched")
        frames = self.received(received)
        self.assertEqual(len(frames), 1)
        self.assertIn("over to you", frames[0])
        self.assertNotIn(wake.LINE_HEAD, frames[0])

    def test_a_reopening_by_hand_during_the_wake_gets_the_message_once_and_no_line(self):
        s = self.seat()
        sid = s["current"]
        base = self.launches()
        self.switch("barrier")
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "send", "w", "for the terminal"], cwd=self.root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.assertTrue(wait_for(lambda: self.launches() > base, timeout=30), "the launch is in flight, past W2")
        received = self.terminal(sid)   # its human reopens it now: the engine answers with a copy
        os.unlink(os.path.join(self.state, "barrier"))
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, out + err)
        [copy] = self.removals()
        self.assertNotEqual(copy, sid[:8])
        self.assertIsNone(self.job(copy), "the copy is gone")
        frames = self.received(received)
        self.assertEqual(len(frames), 1, frames)
        self.assertIn("for the terminal", frames[0])
        self.assertNotIn(wake.LINE_HEAD, frames[0], "a terminal's process gets no wake line")
        self.assertNotIn("line", self.waking(s["seat_id"], sid))

    def test_fill_resume_of_a_stopped_seat_records_its_task_before_anything_is_launched(self):
        s = self.seat()
        sid = s["current"]
        self.switch("fail-job")
        code, out = self.cli("fill", "w", "recorded first", "--resume")
        self.assertNotEqual(code, 0, out)
        [event] = [e for e in self.log() if e.get("text") == "recorded first"]
        self.assertEqual(event["to"][0]["session"], sid, "the task is in the log though the wake failed")
        os.unlink(os.path.join(self.state, "fail-job"))
        before = int(sminos.reload_seat(s["seat_id"])["turns"] or 0)
        code, out = self.cli("fill", "w", "then delivered", "--resume")
        self.assertEqual(code, 0, out)
        frames = [i["message"]["content"] for i in self.inputs(sid)]
        self.assertIn("then delivered", frames[-1])
        self.assertEqual(int(sminos.reload_seat(s["seat_id"])["turns"]), before + 1)


class OneLauncher(unittest.TestCase):
    def test_only_the_wake_and_a_fresh_spawn_call_the_launch(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        callers = set()
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "run_claude_bg":
                        callers.add(fn.name)
        self.assertEqual(callers, {"_wake_held", "spawn_fresh"})
        with open(SCRIPT) as f:
            text = f.read()
        src = ast.get_source_segment(text, next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "spawn_fresh"))
        self.assertNotIn('"--resume"', src, "a fresh spawn resumes nothing")



class Tail(unittest.TestCase):
    def test_a_transcript_replaced_at_the_same_path_is_read_whole_again(self):
        """--wait's incremental read (TranscriptTail): another file at the same path, as long or longer, is
        another transcript, not more of the one read."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "t.jsonl")

        def write(target, *texts):
            with open(target, "w") as f:
                f.writelines(json.dumps({"type": "user", "n": x}) + "\n" for x in texts)
        write(path, "old-1", "old-2")
        tail = sminos.TranscriptTail("s")
        with mock.patch.object(sminos, "transcript_now", return_value=path):
            self.assertEqual([r["n"] for r in tail.read()], ["old-1", "old-2"])
            for texts in (("new-1", "new-2"), ("next-1", "next-2", "next-3")):   # as long, then longer
                write(path + ".new", *texts)
                os.replace(path + ".new", path)
                self.assertEqual([r["n"] for r in tail.read()], list(texts))
            with open(path, "a") as f:
                f.write(json.dumps({"type": "user", "n": "appended"}) + "\n")
            self.assertEqual([r["n"] for r in tail.read()][-2:], ["next-3", "appended"], "an append read on")


if __name__ == "__main__":
    unittest.main()
