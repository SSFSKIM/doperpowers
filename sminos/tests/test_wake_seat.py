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
import subprocess
import sys
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_wake import Engine, sminos, threads, wake, wait_for  # noqa: E402
import sminos_records as records  # noqa: E402
import wake_engine  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts", "sminos.py")


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
            "starting": lambda tid, sid: self.switch("agents-fail"),
            "transcript": lambda tid, sid: os.unlink(sminos.transcript_now(sid)),
            "failed": lambda tid, sid: self.edit(tid, waking={"session": sid, "failed": 1, "at": sminos.now()}),
            "unknown": lambda tid, sid: self.unreadable_record(sid),
        }
        for why, make in cases.items():
            with self.subTest(why=why):
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

    def test_an_ended_thread_is_woken_for_a_return_alone(self):
        tid, sid = self.human_thread()
        self.edit(tid, ended={"at": sminos.now(), "pid": None})
        self.assertEqual(self.wake(sid).why, "ended")
        self.assertTrue(self.wake(sid, returns=True).live, "returns: the one caller that wakes an ended record")

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

    def test_a_launch_that_timed_out_with_its_process_running_is_live(self):
        tid, sid = self.human_thread()
        self.switch("no-banner", 30)
        with mock.patch.dict(os.environ, {"SMINOS_LAUNCH_TIMEOUT": "1.5"}):
            got = self.wake(sid)
        self.assertTrue(got.live, got)
        self.assertIsNotNone(self.record(sid))

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

    def test_a_send_wakes_it_and_its_message_arrives_once_opened_by_the_line(self):
        s = self.seat()
        sid = s["current"]
        before = len(self.frames(sid))
        code, out = self.cli("send", "w", "hello there")
        self.assertEqual(code, 0, out)
        self.assertIn("sent to %s/w (woken)" % s["group"], out)
        self.assertEqual(self.resumes(sid), [[]], "a row is there: no flag, and no message after the id")
        frames = self.frames(sid)[before:]
        self.assertEqual(len(frames), 1, "pushed once")
        self.assertIn(wake.LINE_HEAD, frames[0].split("\n\n")[0], "the line opens it")
        self.assertIn("You run under your saved options.", frames[0].split("\n\n")[0])
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
        self.assertIn("w: woken", out)
        self.assertEqual(sum("over to you" in f for f in self.frames(sid)), 1)

    def test_a_failed_wake_is_said_and_counted(self):
        s = self.seat()
        self.switch("fail-job")
        code, out = self.cli("say", "@w nobody home")
        self.assertIn("w: failed:waking it failed", out)
        self.assertEqual(self.waking(s["seat_id"], s["current"])["failed"], 1)

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


if __name__ == "__main__":
    unittest.main()
