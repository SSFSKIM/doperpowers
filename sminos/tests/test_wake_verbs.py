#!/usr/bin/env python3
"""The verbs, what a sender is told on any machine, and the direct send
(T2's M4: docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md, the
milestone's "Proves"; Interfaces §5's wire half and §6), against the test
engine:

- every cell of §6's table for a thread its human opened and for a seat:
  `resume`, `fill --resume` and `send --wait` wake a stopped thread and push
  their message (with `--wait`, the reply to it); aimed at one that is not
  woken, or whose wake failed, they record it, start nothing, say why and
  exit 4; held for a moment, they record it and exit 4 waiting for nothing;
  a live one in a terminal is pushed to and stopped never; a live background
  job's turn is stopped and the session woken again; a fresh `fill`, and a
  `fill --resume` of a live one, refused; a spawned thread in a protected
  folder resumed;
- `--wait` printing the reply to its own message when a second sender's is
  answered after it, and saying there is none when the session answered
  nothing; `sminos reply` for a session with no seat;
- `wake` and `why` on a stopped thread's `state` (X3): each reason, `failed`
  due or not, `read-only` beside another reason, written again when `why`
  changes and not when only the schedule turns, `mode` for a last prompt
  beyond the tail's bound;
- the line a sender on another machine reads for each published value, and
  over a git mirror from a second registry;
- a direct send after a hand-off leaving the stale event out and settling
  it in its writer's order.

Hermetic: test_wake.Engine (HOME, SMINOS_HOME and the engine's state
temporary, the engine first on PATH and checked to be, every teardown failing
on a resume that carried a message).
Run: python3 -B sminos/tests/test_wake_verbs.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_wake import answer, line_of, prompt, rows, wait_for  # noqa: E402
from test_wake_delivery import FLAGS, STARTING, TAIL, WORDS, Deliveries, line  # noqa: E402
from test_wake_seat import SCRIPT, sminos, threads, wake  # noqa: E402

VERBS = (("resume",), ("fill", "--resume"), ("send", "--wait"))
# §5's line for the sweep's moment: nothing launched, the daemon delivers it.
SWEPT = "recorded: its wake waits for the thread sweep or a transition of it, which holds its lock, and the daemon " \
        "delivers it"


def argv_of(verb, target, text):
    """A verb of §6 with its target and its message."""
    return [verb[0], target, text] + list(verb[1:])


def first_line(out):
    return out.splitlines()[0] if out else ""


class Verbs(Deliveries):
    def logged(self, text):
        return [e for e in self.log() if e.get("text") == text]

    def run_cli(self, *argv):
        """The CLI in a process of its own (a verb that waits blocks)."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        return subprocess.Popen([sys.executable, "-B", SCRIPT] + list(argv), cwd=self.root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def foreign(self, sid):
        other = os.path.join(self.home, "other-config")
        p = mock.patch.object(sminos, "foreign_config", lambda s: other if s == sid else "")
        p.start()
        self.addCleanup(p.stop)

    def cut_over(self):
        """This machine cut over to its endpoint, whose welcome kept no capabilities."""
        rl10 = sminos.sibling_module("sminos_rl10")
        sminos.write_json(rl10.identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "r",
            "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"})
        sminos.audience_module().keep_capabilities([])
        sminos.forget_caches()

    @contextlib.contextmanager
    def swept(self, tid):
        """The thread's wake lock held as the sweep holds it (its own descriptor: flock is per open file)."""
        f = open(sminos.wake_lock_path(tid), "a+")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.seek(0)
        f.truncate()
        f.write(sminos.SWEEP_HOLD)
        f.flush()
        try:
            yield
        finally:
            f.close()

    def one_hold(self, tid):
        """Every fresh taking of the thread's wake lock (none held by this thread yet) and, at each stop and launch,
        whether it was held: patches in place, read back from the lists returned."""
        takes, at = [], []
        real_lock, real_stop, real_run = sminos.wake_lock, sminos.claude_stop, sminos.run_claude_bg

        def lock(thread_id, *a, **k):
            if thread_id == tid and sminos.wake_held(tid) is None:
                takes.append(thread_id)
            return real_lock(thread_id, *a, **k)

        def stop(short):
            at.append(("stop", sminos.wake_held(tid) is not None))
            return real_stop(short)

        def run(args, cwd, settings):
            at.append(("launch", sminos.wake_held(tid) is not None))
            return real_run(args, cwd, settings)
        for name, f in (("wake_lock", lock), ("claude_stop", stop), ("run_claude_bg", run)):
            p = mock.patch.object(sminos, name, f)
            p.start()
            self.addCleanup(p.stop)
        return takes, at

    def owed_mark(self, out, sid):
        return ("owed: %s" % sid) in out.splitlines()

    def held_verb(self, argv, sid, why, text):
        """A verb aimed at a thread that is not woken: recorded and held, said why, nothing started, exit 4."""
        launched = self.launches()
        code, out = self.cli(*argv)
        self.assertEqual(code, 4, out)
        self.assertIn("recorded and held", first_line(out), "the phrase the board reads, in the first line")
        self.assertIn(line(why), out, "§5's line")
        self.assertIn("nothing was started: %s" % WORDS[why], out)
        self.assertEqual(self.launches(), launched, "nothing launched")
        self.assertTrue(self.owes(sid, text), "owed")
        self.assertIn(threads.stamp(sid), set(self.marked(sid).values()), "marked for its thread")
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")


# ------------------------------------------------------------ a thread its human opened


class Human(Verbs):
    def test_resume_and_fill_resume_wake_it_and_push_their_message_once(self):
        for verb in (("resume",), ("fill", "--resume")):
            with self.subTest(verb=verb):
                tid, sid = self.human_thread()
                code, out = self.cli(*argv_of(verb, sid[:8], "carry on, %s" % verb[0]))
                self.assertEqual(code, 0, out)
                self.assertIn("(woken)", out)
                self.assertEqual(self.resumes(sid), [FLAGS], "a first wake's flags, no message after them")
                self.assertTrue(wait_for(lambda: self.frames(sid)), "its inbox wrote the frame down")
                [frame] = self.frames(sid)
                self.assertTrue(line_of(frame)[1].startswith(wake.LINE_HEAD), "closed by the line")
                self.assertEqual(frame.count("carry on, %s" % verb[0]), 1)
                [event] = self.logged("carry on, %s" % verb[0])
                self.assertIn("id=%s" % event["msg_id"], frame, "recorded first, its id in the frame")
                self.assertEqual(self.owed(sid), [])

    def test_a_fresh_fill_is_still_refused_and_records_nothing(self):
        tid, sid = self.human_thread()
        code, out = self.cli("fill", sid[:8], "a new task")
        self.assertEqual(code, 4, out)
        self.assertIn("its human", out)
        self.assertEqual(self.logged("a new task"), [])
        self.assertEqual(self.resumes(sid), [])

    def test_each_reason_records_holds_says_why_starts_nothing_and_exits_4(self):
        def protected(tid, sid):
            self.edit(tid, launch={"cwd": self.vault(), "at": sminos.now()})
        cases = {
            "mode": (lambda tid, sid: None, "plan"),
            "cwd": (lambda tid, sid: self.edit(tid, launch={"cwd": os.path.join(self.home, "gone"),
                                                             "at": sminos.now()}), "auto"),
            "transcript": (lambda tid, sid: os.unlink(sminos.transcript_now(sid)), "auto"),
            "config": (lambda tid, sid: self.foreign(sid), "auto"),
            "protected": (protected, "auto"),
        }
        for why, (make, mode) in cases.items():
            tid, sid = self.human_thread(mode)
            make(tid, sid)
            sminos.forget_caches()
            for verb in VERBS:
                with self.subTest(why=why, verb=verb):
                    text = "for %s by %s" % (why, verb[0])
                    self.held_verb(argv_of(verb, sid[:8], text), sid, why, text)

    def test_a_failed_wake_is_recorded_held_and_said_and_tried_again_by_the_next_verb(self):
        tid, sid = self.human_thread()
        self.switch("fail-job")
        for n, verb in enumerate(VERBS, 1):
            with self.subTest(verb=verb):
                text = "failing %s" % verb[0]
                code, out = self.cli(*argv_of(verb, sid[:8], text))
                self.assertEqual(code, 4, out)
                self.assertIn("recorded and held", first_line(out))
                self.assertIn("nothing was started: %s" % WORDS["failed"], out)
                self.assertEqual(len(self.resumes(sid)), n, "a verb's own call tries at once, whatever the schedule")
                self.assertTrue(self.owes(sid, text))
        os.unlink(os.path.join(self.state, "fail-job"))
        code, out = self.cli("resume", sid[:8], "and now")
        self.assertEqual(code, 0, out)
        # The engine's inbox appends a frame once it has read it: the last one pushed is waited for.
        self.assertTrue(wait_for(lambda: any("and now" in f for f in self.frames(sid))))
        frames = self.frames(sid)
        for text in ("failing resume", "failing fill", "failing send", "and now"):
            self.assertEqual(sum(f.count(text) for f in frames), 1, text)

    def test_a_hold_that_passes_on_its_own_records_waits_for_nothing_and_exits_4(self):
        tid, sid = self.human_thread()
        self.switch("late-inbox", 5)
        code, out = self.cli("send", sid[:8], "soon", "--wait")
        self.assertEqual(code, 4, out)
        self.assertIn(STARTING, first_line(out))
        self.assertIn("no reply is waited for", out)
        self.assertTrue(self.owes(sid, "soon"), "owed, the daemon's to deliver")

    def test_a_hold_with_no_launch_under_way_is_not_said_as_a_process_starting(self):
        # frontier review, scalpel-4#7: a job list that does not read, and a record that does not, launch nothing.
        unread = ("recorded: its machine could not read the session's state just now, and the daemon delivers it "
                  "when it can")
        for case in ("jobs", "record"):
            with self.subTest(case=case):
                tid, sid = self.human_thread()
                path = sminos.records_module().record_path(sid)
                with open(path) as f:
                    kept = f.read()
                if case == "jobs":
                    self.switch("agents-fail")
                else:
                    with open(path, "w") as f:
                        f.write("{")   # the session's record there and unreadable: row 3
                try:
                    code, out = self.cli("send", sid[:8], "unread %s" % case)
                    self.assertEqual(code, 0, out)
                    self.assertIn(unread, out)
                    self.assertNotIn("its process is starting", out)
                    code, out = self.cli("send", sid[:8], "unread %s, waited" % case, "--wait")
                    self.assertEqual(code, 4, out)
                    self.assertIn(unread, first_line(out))
                    self.assertEqual(self.launches(), 0, "nothing launched")
                finally:
                    if case == "jobs":
                        os.unlink(os.path.join(self.state, "agents-fail"))
                    else:
                        with open(path, "w") as f:
                            f.write(kept)

    def test_an_ended_one_is_refused_with_exit_4_and_nothing_recorded(self):
        tid, sid = self.human_thread()
        code, out = self.cli("retire", sid[:8])
        self.assertEqual(code, 0, out)
        for verb in VERBS:
            with self.subTest(verb=verb):
                code, out = self.cli(*argv_of(verb, sid[:8], "after its end"))
                self.assertEqual(code, 4, out)
        code, out = self.cli("fill", sid[:8], "after its end", "--resume")
        self.assertIn("returns when its human reopens it", out)
        self.assertEqual(self.resumes(sid), [])
        self.assertEqual(self.logged("after its end"), [], "nothing recorded")

    def test_resume_of_a_session_a_terminal_holds_pushes_to_it_says_so_and_stops_nothing(self):
        tid, sid = self.human_thread()
        received = self.terminal(sid)
        before = len(self.calls())
        code, out = self.cli("resume", sid[:8], "at your terminal")
        self.assertEqual(code, 0, out)
        self.assertIn("a terminal holds it", out)
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "nothing stopped")
        self.assertEqual(self.resumes(sid), [])
        [frame] = self.received(received)
        self.assertIn("at your terminal", frame)

    def test_resume_of_its_background_process_stops_the_turn_and_wakes_it_again(self):
        tid, sid = self.human_thread()
        code, out = self.say("@%s first" % sid[:8])
        self.assertEqual(self.shown(out, sid), ["sent (woken)"])
        before = len(self.calls())
        code, out = self.cli("resume", sid[:8], "start over")
        self.assertEqual(code, 0, out)
        self.assertIn("(woken)", out)
        self.assertTrue([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "its turn stopped")
        self.assertEqual(self.resumes(sid), [FLAGS, []], "woken again, under its row")
        self.assertEqual(sum(f.count("start over") for f in self.frames(sid)), 1)

    def test_resume_stops_its_turn_and_wakes_it_under_one_hold_of_the_wake_lock(self):
        tid, sid = self.human_thread()
        self.say("@%s first" % sid[:8])
        takes, at = self.one_hold(tid)
        code, out = self.cli("resume", sid[:8], "start over")
        self.assertEqual(code, 0, out)
        self.assertIn("(woken)", out)
        self.assertEqual(at, [("stop", True), ("launch", True)], "the stop and the launch under the lock")
        self.assertEqual(takes, [tid], "one hold, taken before the stop, for both")

    def test_resume_that_cannot_have_the_wake_lock_stops_nothing_and_answers_the_hold(self):
        tid, sid = self.human_thread()
        self.say("@%s first" % sid[:8])
        before, resumes = len(self.calls()), len(self.resumes(sid))
        with self.swept(tid), mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            code, out = self.cli("resume", sid[:8], "start over")
        self.assertEqual(code, 4, out)
        self.assertIn(SWEPT, first_line(out))
        self.assertTrue(self.owed_mark(out, sid))
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "its turn left running")
        self.assertEqual(len(self.resumes(sid)), resumes, "nothing launched")
        self.assertIsNotNone(self.record(sid), "its process still runs")
        self.assertTrue(self.owes(sid, "start over"), "owed")
        self.tick()
        self.assertTrue(wait_for(lambda: sum(f.count("start over") for f in self.frames(sid)) == 1),
                        "the daemon pushes it to the process that runs")

    def test_fill_resume_of_a_live_one_is_refused_as_a_filled_seat_is_and_records_nothing(self):
        tid, sid = self.human_thread()
        self.say("@%s up now" % sid[:8])
        code, out = self.cli("fill", sid[:8], "not for a live one", "--resume")
        self.assertEqual(code, 4, out)
        self.assertIn("is filled", out)
        self.assertIn("use sminos send", out)
        self.assertEqual(self.logged("not for a live one"), [])

    def test_wait_prints_the_reply_to_its_own_message_when_a_second_senders_is_answered_after_it(self):
        for verb in (("send", "--wait"), ("resume", "--wait")):
            with self.subTest(verb=verb):
                tid, sid = self.human_thread()
                self.switch("reply-delay", 1)
                text = "mine, by %s" % verb[0]
                p = self.run_cli(*argv_of(verb, sid[:8], text))
                self.addCleanup(lambda p=p: p.poll() is None and p.kill())
                self.assertTrue(wait_for(lambda: self.inputs(sid), timeout=30), "its frame arrived")
                self.push(sid, sminos.compose_frame("bee", "other001", "theirs"))
                out, err = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 0, out + err)
                [event] = self.logged(text)
                self.assertIn("reply to %s" % event["msg_id"], out)
                self.assertNotIn("other001", out, "another sender's reply is not this one's")
                self.assertTrue(self.replied(sid, "other001"), "the other was answered, after")
                os.unlink(os.path.join(self.state, "reply-delay"))

    def test_wait_says_there_is_no_reply_when_the_session_answered_nothing(self):
        tid, sid = self.human_thread()
        self.switch("no-reply")
        p = self.run_cli("send", sid[:8], "say nothing", "--wait")
        self.addCleanup(lambda: p.poll() is None and p.kill())
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertIn("(no reply yet)", out)


# ------------------------------------------------------------ a seat


class StopDecided(Verbs):
    """`resume` decides under the wake lock whatever would refuse the wake before it stops a live turn (frontier
    review round 2, scalpel-1#1): a turn stopped and not started again is the failure."""

    @contextlib.contextmanager
    def entry_open(self, tid, opened):
        """The record's entry open and kept open for the block (a hand-off's, say, whose carry cannot finish yet):
        every finisher leaves it as it is."""
        path = self.record_file(tid) if opened == "human" else sminos.meta_path(tid)
        with open(path) as f:
            rec = json.load(f)
        rec["pending"] = {"id": "e1", "op": "advance", "events": []}
        with open(path, "w") as f:
            json.dump(rec, f)
        sminos.forget_caches()
        with mock.patch.object(threads, "finish", lambda *a, **k: []), \
                mock.patch.object(sminos, "finish_thread", lambda *a, **k: []):
            yield

    def test_an_entry_open_under_the_lock_stops_no_turn_and_holds_the_message(self):
        for opened in ("human", "spawned"):
            with self.subTest(opened=opened):
                if opened == "human":
                    tid, sid = self.human_thread()
                    target = sid[:8]
                    self.say("@%s up" % target)
                else:
                    s = self.seat("w")
                    tid, sid, target = s["seat_id"], s["current"], "w"
                    self.cli("send", "w", "up")
                self.assertTrue(wait_for(lambda: self.record(sid) is not None))
                before, launched = len(self.calls()), self.launches()
                with self.entry_open(tid, opened):
                    code, out = self.cli("resume", target, "start over")
                self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "no turn stopped")
                self.assertIn("was not stopped: it holds a transition not finished yet", out)
                self.assertIsNotNone(self.record(sid), "its process still runs")
                self.assertEqual(self.launches(), launched, "nothing launched")
                if opened == "human":
                    # A thread with no seat: its delivery pass pushes to the live process, as to any live session.
                    self.assertEqual(code, 0, out)
                    self.assertTrue(wait_for(lambda: sum(f.count("start over") for f in self.frames(sid)) == 1))
                else:
                    # A seat's wake answers the open entry (row 5): held, the daemon's to push once it is finished.
                    self.assertEqual(code, 4, out)
                    self.assertTrue(self.owes(sid, "start over"), "owed")


class Seat(Verbs):
    def test_each_reason_records_holds_says_why_starts_nothing_and_exits_4(self):
        def gone(s):
            shutil.rmtree(seat_dirs[s["alias"]])
        seat_dirs = {}
        cases = {"cwd": gone, "transcript": lambda s: os.unlink(sminos.transcript_now(s["current"])),
                 "config": lambda s: self.foreign(s["current"])}
        for why, make in cases.items():
            alias = "w-" + why
            seat_dirs[alias] = os.path.join(self.root, "sub-" + why)
            s = self.seat_in(alias, seat_dirs[alias])
            make(s)
            sminos.forget_caches()
            for verb in VERBS:
                with self.subTest(why=why, verb=verb):
                    text = "for %s by %s" % (why, verb[0])
                    self.held_verb(argv_of(verb, alias, text), s["current"], why, text)

    def test_resume_stops_its_turn_and_wakes_it_under_one_hold_of_the_wake_lock(self):
        s = self.seat()
        sid = s["current"]
        self.cli("send", "w", "up")
        takes, at = self.one_hold(s["seat_id"])
        code, out = self.cli("resume", "w", "start over")
        self.assertEqual(code, 0, out)
        self.assertEqual(at, [("stop", True), ("launch", True)], "the stop and the launch under the lock")
        self.assertEqual(takes, [s["seat_id"]], "one hold, taken before the stop, for both")
        self.assertEqual(sum(f.count("start over") for f in self.frames(sid)), 1)

    def test_resume_stops_no_job_an_earlier_wake_accepted_that_is_still_starting(self):
        s = self.seat()
        sid = s["current"]
        self.switch("late-process", 30)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "2"}):
            code, out = self.cli("send", "w", "up")
            self.assertIn(sminos.PASSING_LINE, out)
            launched, before = self.launches(), len(self.calls())
            code, out = self.cli("resume", "w", "start over")
        self.assertEqual(code, 4, out)
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] in (["stop"], ["rm"])], "nothing stopped")
        self.assertEqual(self.launches(), launched, "nothing launched beside it")
        self.assertTrue(self.owes(sid, "start over"), "owed")

    def test_resume_that_cannot_have_the_wake_lock_stops_nothing_and_answers_the_hold(self):
        s = self.seat()
        sid = s["current"]
        self.cli("send", "w", "up")
        before, resumes = len(self.calls()), len(self.resumes(sid))
        with self.swept(s["seat_id"]), mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            code, out = self.cli("resume", "w", "start over")
        self.assertEqual(code, 4, out)
        self.assertIn(SWEPT, out)
        self.assertTrue(self.owed_mark(out, sid))
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "its turn left running")
        self.assertEqual(len(self.resumes(sid)), resumes, "nothing launched")
        self.assertIsNotNone(self.record(sid), "its process still runs")
        self.assertTrue(self.owes(sid, "start over"), "owed")

    def test_a_spawned_thread_in_a_protected_folder_is_resumed(self):
        s = self.seat_in("w", self.vault())
        code, out = self.cli("resume", "w", "in the vault")
        self.assertEqual(code, 0, out)
        self.assertIn("resumed", out)
        self.assertEqual(sum(f.count("in the vault") for f in self.frames(s["current"])), 1)

    def test_a_failed_wake_is_recorded_held_and_exits_4(self):
        s = self.seat()
        self.switch("fail-job")
        for verb in VERBS:
            with self.subTest(verb=verb):
                text = "failing %s" % verb[0]
                code, out = self.cli(*argv_of(verb, "w", text))
                self.assertEqual(code, 4, out)
                self.assertIn("recorded and held", first_line(out))
                self.assertIn("nothing was started: %s" % WORDS["failed"], out)
                self.assertTrue(self.owes(s["current"], text))
                self.assertEqual(set(self.attempts(s["current"]).values()) - {0}, set(), "no attempt counted")

    def test_a_hold_that_passes_on_its_own_exits_4_waiting_for_nothing(self):
        s = self.seat()
        self.switch("late-inbox", 5)
        code, out = self.cli("resume", "w", "soon")
        self.assertEqual(code, 4, out)
        self.assertIn(STARTING, first_line(out))
        self.assertIn("no reply is waited for", out)
        self.assertTrue(self.owes(s["current"], "soon"))


# ------------------------------------------------------------ reply


class Reply(Verbs):
    def test_reply_reads_a_session_with_no_seat(self):
        tid, sid = self.human_thread()
        self.say("@%s what now" % sid[:8])
        [event] = [e for e in self.log() if "what now" in str(e.get("text"))]
        frame = self.frames(sid)[0]
        mid = frame.split("id=", 1)[1].split("]", 1)[0] if "id=" in frame else event.get("msg_id", "")
        self.assertTrue(self.replied(sid, mid), "it answered")
        code, out = self.cli("reply", sid[:8])
        self.assertEqual(code, 0, out)
        self.assertIn("reply to %s" % mid, out)


# ------------------------------------------------------------ what a thread's machine publishes (X3)


class Published(Verbs):
    def setUp(self):
        super().setUp()
        self.record = {}

    def stopped_state(self, sid):
        sminos.lifecycle(self.p, sid, "state", state="stopped", machine="testhost")
        e = self.own(sid)[-1]
        return e.get("wake"), e.get("why")

    def publish(self):
        sminos.forget_caches()
        return self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), self.record)

    def test_each_reason_is_published_as_why(self):
        cases = {
            "mode": (lambda tid, sid: None, "plan"),
            "cwd": (lambda tid, sid: self.edit(tid, launch={"cwd": os.path.join(self.home, "gone"),
                                                             "at": sminos.now()}), "auto"),
            "transcript": (lambda tid, sid: os.unlink(sminos.transcript_now(sid)), "auto"),
            "config": (lambda tid, sid: self.foreign(sid), "auto"),
            "protected": (lambda tid, sid: self.edit(tid, launch={"cwd": self.vault(), "at": sminos.now()}), "auto"),
        }
        for why, (make, mode) in cases.items():
            with self.subTest(why=why):
                tid, sid = self.human_thread(mode)
                make(tid, sid)
                sminos.forget_caches()
                self.assertEqual(self.stopped_state(sid), ("held", why))
        tid, sid = self.human_thread()
        self.assertEqual(self.stopped_state(sid), ("woken", None), "one its machine wakes")

    def test_a_failed_wake_is_published_failed_whether_or_not_it_is_due(self):
        tid, sid = self.human_thread()
        threads.wake_failed(tid, sid, "x")
        self.assertEqual(self.stopped_state(sid), ("held", "failed"))
        with mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": "0"}):
            self.assertTrue(wake.wake_due(threads.get(tid), sid), "due now")
            self.assertEqual(self.stopped_state(sid), ("held", "failed"), "the value does not turn with the schedule")

    def test_read_only_is_published_beside_another_reason(self):
        tid, sid = self.human_thread("plan")
        policy = sminos.sibling_module("sminos_policy")
        with mock.patch.object(policy, "read_only", return_value=True):
            self.assertEqual(self.stopped_state(sid), ("held", "read-only"))
        tid2, sid2 = self.human_thread()
        with mock.patch.object(policy, "read_only", return_value=True):
            self.assertEqual(self.stopped_state(sid2), ("held", "read-only"), "for a thread it would wake too")

    def test_the_state_is_written_again_when_why_changes_and_not_when_only_the_schedule_turns(self):
        tid, sid = self.human_thread("plan")
        self.publish()
        last = self.own(sid)[-1]
        self.assertEqual((last["state"], last.get("wake"), last.get("why")), ("stopped", "held", "mode"))
        self.assertEqual(self.publish(), 0, "nothing changed")
        with open(sminos.transcript_now(sid), "a") as f:
            f.write(rows(prompt("auto", "on again"), answer("claude-term", "req_9")))
        threads.wake_failed(tid, sid, "x")
        self.assertEqual(self.publish(), 1, "`why` changed: written again")
        last = self.own(sid)[-1]
        self.assertEqual((last.get("wake"), last.get("why")), ("held", "failed"))
        with mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": "0"}):
            self.assertEqual(self.publish(), 0, "a wake falling due changes nothing published")
        threads.wake_done(tid, sid)
        self.assertEqual(self.publish(), 1)
        last = self.own(sid)[-1]
        self.assertEqual((last.get("wake"), last.get("why")), ("woken", None))

    def test_mode_is_published_for_a_thread_whose_last_prompt_lies_beyond_the_tails_bound(self):
        tid, sid = self.human_thread("plan")
        filler = {"type": "progress", "data": "x" * 900}
        with open(sminos.transcript_now(sid), "a") as f:
            for _ in range(64):
                f.write(json.dumps(filler) + "\n")
        with mock.patch.object(wake, "TAIL_BOUND", 8 << 10):
            sminos.forget_caches()
            wake._KEPT.clear()
            wake._TURNS.clear()
            self.assertIsNone(wake.last_turn(sid)["mode"], "beyond the bound")
            self.publish()
        last = self.own(sid)[-1]
        self.assertEqual((last.get("wake"), last.get("why")), ("held", "mode"))


# ------------------------------------------------------------ a sender on another machine


class Remote(Verbs):
    def remote(self, wake_value, why=None):
        """A stopped thread of another machine, as its machine published it into this project's log."""
        sid = str(uuidlib.uuid4())
        w = "elsewhere/%s" % sid
        sminos.log_append(self.p, w, "joined", session=sid, alias="far", name_source="user", machine="elsewhere",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.p, w, "state", session=sid, state="stopped", machine="elsewhere",
                          **({"wake": wake_value} if wake_value else {}), **({"why": why} if why else {}))
        sminos.forget_caches()
        return sid

    def test_the_line_a_remote_sender_reads_for_each_published_value(self):
        tail = TAIL
        cases = [(("held", why), "recorded and held on elsewhere: the session is stopped and is not woken: %s%s"
                  % (WORDS[why], tail)) for why in WORDS]
        cases += [(("held", "read-only"), "recorded: elsewhere admits nothing from another machine, and refuses it "
                                          "there"),
                  (("held", None), "recorded and held on elsewhere: the session is stopped, and a session its human "
                                   "opened is not woken"),
                  (("woken", None), "recorded (on elsewhere): the session is stopped, and its machine wakes it "
                                    "with this")]
        for (value, why), said in cases:
            with self.subTest(wake=value, why=why):
                sid = self.remote(value, why)
                m = self.member(sid)
                self.assertEqual((sminos.wake_of(m), sminos.why_of(m)), (value, why or ""))
                code, out = self.say("@far#%s hi" % sid[:8])
                self.assertEqual(code, 0, out)
                self.assertIn("far: " + said, out)
                code, out = self.send("far#%s" % sid[:8], "a note")
                self.assertEqual(code, 0, out)
                self.assertIn("for far: " + said, out)

    def hint(self, sid):
        """`who`'s lines for the session, from the line its commits carry."""
        m = self.member(sid)
        return "\n".join(sminos.who_lines({"line": "Sminos-Session: %s#%s (work on %s)" % (m.alias, sid[:8], m.machine),
                                           "short": sid[:8], "alias": m.alias, "project": "work",
                                           "machine": m.machine}))

    def test_who_says_what_a_message_from_here_meets(self):
        """`who`'s hint is §5's: a hold waits for a process of the thread, but a read-only machine refuses what
        comes from another machine, and a thread whose hold its machine publishes on `gone` is held too."""
        out = self.hint(self.remote("held", "read-only"))
        self.assertIn("no message from here reaches it: elsewhere admits nothing from another machine, and refuses "
                      "it there", out)
        self.assertNotIn("leave it a message", out)
        out = self.hint(self.remote("held", "transcript"))
        self.assertIn("or leave it a message, held until a process of it runs (%s)" % WORDS["transcript"], out)
        sid = self.remote("held", "transcript")
        sminos.log_append(self.p, "elsewhere/%s" % sid, "state", session=sid, state="gone", machine="elsewhere",
                          wake="held", why="transcript")
        self.assertIn("or leave it a message, held until a process of it runs (%s)" % WORDS["transcript"],
                      self.hint(sid), "published on `gone`")
        self.assertIn("or message it, which wakes it", self.hint(self.remote("woken")))
        tid, sid = self.human_thread()
        policy = sminos.sibling_module("sminos_policy")
        with mock.patch.object(policy, "read_only", return_value=True):
            out = self.hint(sid)
        self.assertIn("or message it, which wakes it", out, "this machine refuses only what comes from another")
        self.assertNotIn("admits nothing", out)

    def test_over_a_git_mirror_a_second_registry_reads_what_this_machine_published(self):
        bare = os.path.join(self.home, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        repo = self.repo("mirrored")
        code, out = self.cli("project", "init", "--name", "demo", "--remote", bare, cwd=repo)
        self.assertEqual(code, 0, out)
        subprocess.run(["git", "-C", repo, "add", ".smns"], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "smns"],
                       check=True)
        self.p = self.project_of(repo)
        sid = self.opened("plan")
        _, proc = self.session(sid=sid, root=repo)
        self.reconcile()
        self.end(proc)
        self.edit(threads.stamp(sid), launch={"cwd": repo, "at": sminos.now()})
        sminos.forget_caches()
        code, out = self.cli("daemon", "tick", cwd=repo)
        self.assertEqual(code, 0, out)
        there = tempfile.mkdtemp(dir=self.home)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        env.update(HOME=os.path.join(there, "h"), SMINOS_HOME=os.path.join(there, "s"), DAEMON_HOST="farhost")
        os.makedirs(os.path.join(env["HOME"], ".claude", "sessions"))
        os.makedirs(env["SMINOS_HOME"], mode=0o700)

        def far(*argv):
            p = subprocess.run([sys.executable, "-B", SCRIPT] + list(argv), cwd=repo, env=env, capture_output=True,
                               text=True, timeout=120)
            return p.returncode, p.stdout + p.stderr
        code, out = far("project", "attach")
        self.assertEqual(code, 0, out)
        code, out = far("say", "@%s from afar" % sid[:8])
        self.assertEqual(code, 0, out)
        self.assertIn("recorded and held on testhost: the session is stopped and is not woken: %s" % WORDS["mode"],
                      out)
        # A spawned thread with no conversation here: `gone`, its hold published on that state and mirrored.
        g = self.seat_in("g", repo)["current"]
        os.unlink(sminos.transcript_now(g))
        self.assertTrue(wait_for(lambda: (self.member(g, self.p) or self.member(g)).state == "gone"))
        for _ in range(2):
            code, out = self.cli("daemon", "tick", cwd=repo)
            self.assertEqual(code, 0, out)
        far("daemon", "tick")
        code, out = far("say", "@%s from afar" % g[:8])
        self.assertEqual(code, 0, out)
        self.assertIn("recorded and held on testhost: the session is stopped and is not woken: %s"
                      % WORDS["transcript"], out)
        policy = sminos.sibling_module("sminos_policy")
        with mock.patch.object(policy, "read_only", return_value=True):
            code, out = self.cli("daemon", "tick", cwd=repo)
            self.assertEqual(code, 0, out)
        code, out = far("daemon", "tick")
        code, out = far("say", "@%s again" % sid[:8])
        self.assertIn("recorded: testhost admits nothing from another machine, and refuses it there", out)


# ------------------------------------------------------------ the direct send


class Direct(Verbs):
    def stale(self, sid, text, writer="testhost/human"):
        """An event of `writer` to the session, marked held for a thread it no longer fills."""
        e = sminos.log_append(self.p, writer, "human", **{"from": "human", "to": [{"session": sid, "alias": "x"}],
                                                          "text": text})
        sminos.delivered_held(self.p, sid, writer, e["seq"], str(uuidlib.uuid4()))
        return e

    def test_a_direct_send_leaves_the_stale_event_out_and_settles_it_in_order(self):
        tid, sid = self.human_thread()
        received = self.terminal(sid)
        e = self.stale(sid, "told it went to no one")
        code, out = self.send(sid[:8], "the new one")
        self.assertEqual(code, 0, out)
        got = self.received(received)
        self.assertEqual(sum(f.count("the new one") for f in got), 1)
        self.assertFalse([f for f in got if "told it went to no one" in f], "the stale text is pushed to no one")
        self.assertEqual(self.owed(sid), [], "both settled")
        self.assertGreaterEqual(sminos._delivery(sminos.delivered_load(self.p, sid), e["writer"])["settled"],
                                e["seq"])

    def test_a_stale_event_behind_an_owed_one_is_never_settled_ahead_of_it(self):
        tid, sid = self.human_thread()
        self.terminal(sid)
        w = "testhost/human"
        first = sminos.log_append(self.p, w, "human", **{"from": "human", "to": [{"session": sid, "alias": "x"}],
                                                         "text": "owed first"})
        stale = self.stale(sid, "stale between")
        mine = sminos.log_append(self.p, w, "human", **{"from": "human", "to": [{"session": sid, "alias": "x"}],
                                                        "text": "this send"})
        d = sminos.SendDelivery(self.p, sid, w, mine)
        self.assertEqual([x["seq"] for x in d.queue], [first["seq"], stale["seq"], mine["seq"]])
        self.assertNotIn("stale between", d.payload(True))
        self.assertEqual([x["seq"] for x in d.carried(True)], [first["seq"], mine["seq"]])
        d.fail()
        entry = sminos._delivery(sminos.delivered_load(self.p, sid), w)
        self.assertEqual((entry["settled"] < first["seq"], entry["pending"]), (True, first["seq"]),
                         "the owed one failed and pending; nothing behind it settled")
        d = sminos.SendDelivery(self.p, sid, w, mine)
        d.settle()
        self.assertGreaterEqual(sminos._delivery(sminos.delivered_load(self.p, sid), w)["settled"], mine["seq"])


# ------------------------------------------------------------ review round 1: holds on every path, the marker


class Round(Verbs):
    """What the first review found: a hold published on a `gone` state, the thread's hold before the endpoint's
    gate, the turn a verb stops, the line a script reads, a verb with nothing recorded, a returned seat's
    refusal, a terminal's seat, an ended name's tiers, a stale event's reach."""

    # I1
    def test_a_spawned_thread_with_no_conversation_here_publishes_its_hold_on_its_gone_state(self):
        s = self.seat()
        sid = s["current"]
        os.unlink(sminos.transcript_now(sid))
        self.assertTrue(wait_for(lambda: self.member(sid).state == "gone"), "its seat reads gone")
        record = {}
        for _ in range(2):
            sminos.forget_caches()
            self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record)
        last = [e for e in self.own(sid) if e["kind"] == "state"][-1]
        self.assertEqual((last["state"], last.get("wake"), last.get("why")), ("gone", "held", "transcript"))
        sminos.forget_caches()
        self.assertEqual(self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record), 0)

    def remote_in(self, state, wake_value=None, why=None):
        sid = str(uuidlib.uuid4())
        w = "elsewhere/%s" % sid
        sminos.log_append(self.p, w, "joined", session=sid, alias="far", name_source="user", machine="elsewhere",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.p, w, "state", session=sid, state=state, machine="elsewhere",
                          **({"wake": wake_value} if wake_value else {}), **({"why": why} if why else {}))
        sminos.forget_caches()
        return sid

    def test_a_remote_gone_state_is_read_by_its_why_and_a_bare_one_as_before(self):
        sid = self.remote_in("gone", "held", "transcript")
        code, out = self.send("far#%s" % sid[:8], "a note")
        self.assertIn("for far: " + line("transcript").replace("recorded and held:", "recorded and held on "
                                                                   "elsewhere:"), out)
        sid = self.remote_in("gone")
        code, out = self.send("far#%s" % sid[:8], "a note")
        self.assertNotIn("recorded and held", out, "a gone with nothing published reads as today")

    def test_send_wait_to_a_remote_held_thread_records_it_whether_stopped_or_gone(self):
        """A `gone` its machine publishes `held` (a spawned thread whose conversation is not there) is a stopped
        one's to `send --wait` too (§6): recorded, the hold's words, nothing started, exit 4."""
        for state in ("stopped", "gone"):
            with self.subTest(state=state):
                sid = self.remote_in(state, "held", "transcript")
                text = "waited on while %s" % state
                code, out = self.cli("send", "--wait", "far#%s" % sid[:8], text)
                self.assertEqual(code, 4, out)
                self.assertEqual(len(self.logged(text)), 1, out)
                self.assertIn("for far: " + line("transcript").replace("recorded and held:", "recorded and held on "
                                                                           "elsewhere:"), out)
                self.assertIn("nothing was started: far runs on elsewhere, which holds it; no reply is waited for",
                              out)

    def test_a_retired_machines_gone_is_never_read_as_a_hold(self):
        sid = self.remote_in("gone", "held", "transcript")
        with mock.patch.object(sminos, "machine_retired", lambda name: str(name).lower() == "elsewhere"):
            sminos.forget_caches()
            m = self.member(sid) or next((x for x in sminos.view_of(self.p).ended if x.session == sid), None)
            self.assertIsNotNone(m)
            self.assertEqual(sminos.why_of(m), "")
            self.assertIsNone(sminos.remote_line(m))

    # I2
    def test_a_seat_verb_held_for_its_thread_on_a_cut_over_machine_exits_4_and_waits_for_nothing(self):
        for verb in (("send", "--wait"), ("resume", "--wait"), ("resume",)):
            with self.subTest(verb=verb):
                alias = "c-" + verb[0] + str(len(verb))
                s = self.seat(alias)
                os.unlink(sminos.transcript_now(s["current"]))
                self.cut_over()
                text = "held for %s" % "-".join(verb)
                with mock.patch.dict(os.environ, {"SMINOS_ACK_TIMEOUT": "3"}):
                    code, out = self.cli(*argv_of(verb, alias, text))
                self.assertEqual(code, 4, out)
                self.assertIn("recorded and held", first_line(out))
                self.assertIn("nothing was started: %s" % WORDS["transcript"], out)
                self.assertNotIn("no evidence", out, "no watcher started")
                self.assertTrue(self.owed_mark(out, s["current"]))

    def test_a_hand_off_awaiting_admission_is_a_push_and_is_waited_for(self):
        tid, sid = self.human_thread()
        self.say("@%s up" % sid[:8])
        real = sminos.deliver_next

        def handed(project, member, due=False, **kw):
            # As holder_carry hands a frame to a receipt's process: pushed, then awaiting its admission.
            got = real(project, member, due=due, **kw)
            return {**got, "outcomes": [(e, sminos.HandedOff()) for e, _ in got["outcomes"]]}
        with mock.patch.object(sminos, "deliver_next", handed):
            p = mock.patch.dict(os.environ, {"SMINOS_ACK_TIMEOUT": "20"})
            with p:
                code, out = self.cli("send", sid[:8], "handed over", "--wait")
        self.assertEqual(code, 0, out)
        [event] = self.logged("handed over")
        self.assertIn("reply to %s" % event["msg_id"], out, "waited for its reply")
        lines = out.splitlines()
        self.assertLess(lines.index("owed: %s" % sid), lines.index("--- reply ---"),
                        "owed until its admission: the line before the waiter")

    def test_a_hold_with_no_push_is_said_held_and_waits_for_nothing(self):
        tid, sid = self.human_thread()
        self.say("@%s up" % sid[:8])

        def unread(project, member, due=False, **kw):
            evs = [e for e in sminos.owed(project, member)]
            return {"outcomes": [(e, "held:its process's mode cannot be read") for e in evs]}
        with mock.patch.object(sminos, "deliver_next", unread):
            code, out = self.cli("send", sid[:8], "not handed", "--wait")
        self.assertEqual(code, 4, out)
        self.assertIn("no reply is waited for", out)
        self.assertTrue(self.owed_mark(out, sid))

    # I3
    def test_a_resume_whose_message_another_deliverer_pushed_stops_no_turn(self):
        tid, sid = self.human_thread()
        self.say("@%s first" % sid[:8])
        real = sminos.SendDelivery.__init__

        def raced(d, project, session, writer, event):
            sminos.deliver_next(project, self.member(session), due=True)
            real(d, project, session, writer, event)
        before = len(self.calls())
        with mock.patch.object(sminos.SendDelivery, "__init__", raced):
            code, out = self.cli("resume", sid[:8], "taken meanwhile")
        self.assertEqual(code, 0, out)
        self.assertIn("delivered by a concurrent delivery", out)
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "its turn ran on")
        self.assertEqual(sum(f.count("taken meanwhile") for f in self.frames(sid)), 1)

    def test_a_message_settled_by_another_without_a_push_is_not_said_delivered(self):
        tid, sid = self.human_thread()
        self.say("@%s first" % sid[:8])
        real = sminos.SendDelivery.__init__

        def settled(d, project, session, writer, event):
            sminos.delivered_settle(project, session, writer, event["seq"])
            real(d, project, session, writer, event)
        before = len(self.calls())
        with mock.patch.object(sminos.SendDelivery, "__init__", settled), \
                mock.patch.dict(os.environ, {"SMINOS_ACK_TIMEOUT": "1"}):
            code, out = self.cli("resume", sid[:8], "settled unpushed", "--wait")
        self.assertNotEqual(code, 0, out)
        self.assertNotIn("delivered by a concurrent delivery", out)
        self.assertNotIn("--- reply ---", out)
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]])

    # I4
    def test_a_verb_queued_behind_an_earlier_message_prints_the_owed_line(self):
        tid, sid = self.human_thread()

        def behind(project, member, due=False, **kw):
            [e] = [x for x in sminos.owed(project, member)][:1] or [None]
            return {"outcomes": [({**e, "seq": e["seq"] - 1}, "failed:busy")]} if e else {"outcomes": []}
        with mock.patch.object(sminos, "deliver_next", behind):
            code, out = self.cli("resume", sid[:8], "queued")
        self.assertEqual(code, 4, out)
        self.assertTrue(self.owed_mark(out, sid), out)

    def test_an_endpoint_gated_seat_resume_whose_wait_expires_prints_the_owed_line(self):
        s = self.seat()
        self.cli("send", "w", "up")
        self.cut_over()
        with mock.patch.dict(os.environ, {"SMINOS_ACK_TIMEOUT": "0.5"}):
            code, out = self.cli("resume", "w", "gated", "--wait")
        self.assertEqual(code, 1, out)
        self.assertTrue(self.owed_mark(out, s["current"]), out)

    def test_a_held_verb_prints_the_owed_line_and_a_pushed_one_none(self):
        tid, sid = self.human_thread("plan")
        code, out = self.cli("resume", sid[:8], "held one")
        self.assertEqual(code, 4, out)
        self.assertTrue(self.owed_mark(out, sid))
        tid, sid = self.human_thread()
        code, out = self.cli("resume", sid[:8], "pushed one")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.owed_mark(out, sid))

    # I5
    def test_a_verb_whose_message_cannot_be_recorded_starts_nothing(self):
        self.seat()
        real = sminos.seat_project
        with mock.patch.object(sminos, "seat_project",
                               lambda seat, fresh=False: None if seat and seat.get("alias") == "w" else real(seat, fresh)):
            launched, before = self.launches(), len(self.calls())
            for verb in (("resume",), ("fill", "--resume")):
                with self.subTest(verb=verb):
                    code, out = self.cli(*argv_of(verb, "w", "no log for it"))
                    self.assertEqual(code, 4, out)
                    self.assertIn("nothing was started", out)
            self.assertEqual(self.launches(), launched, "nothing launched")
            self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]])

    # I6
    def test_a_returned_seats_task_the_endpoint_refuses_says_both(self):
        s = self.seat()
        code, out = self.cli("retire", "w")
        self.assertEqual(code, 0, out)
        self.cut_over()
        env = {"SMINOS_VERDICT_WAIT": "60"}
        with mock.patch.dict(os.environ, env):
            p = self.run_cli("fill", "w", "refuse this", "--resume")
        self.addCleanup(lambda: p.poll() is None and p.kill())
        def recorded():
            sminos.forget_caches()
            return [x for x in sminos.log_read(project) if x.get("text") == "refuse this"]
        project = sminos.seat_project(sminos.reload_seat(s["seat_id"]))   # cut over: the machine's project
        self.assertTrue(wait_for(recorded, timeout=60), "recorded")
        [e] = recorded()
        seat = sminos.reload_seat(s["seat_id"])
        self.assertTrue(wait_for(lambda: self.member(seat["current"], project) is not None, timeout=30))
        sminos.deliver_verdict(project, self.member(seat["current"], project), e, "refuse")
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 4, out + err)
        said = out + err
        self.assertIn("returned", said)
        self.assertIn("refused", said)
        self.assertNotIn("is retired", said)
        self.assertNotIn("if the endpoint refuses", said, "the fact, not a hypothetical")

    # I7
    def test_a_seat_a_terminal_holds_is_said_so_by_resume(self):
        s = self.seat()
        self.terminal(s["current"])
        code, out = self.cli("resume", "w", "at the terminal")
        self.assertEqual(code, 0, out)
        self.assertIn("a terminal holds it", out)
        self.assertNotIn("via --bg --resume", out)

    def test_an_ended_session_named_by_its_project_or_its_short_is_said_ended_by_every_verb(self):
        tid, sid = self.human_thread()
        alias = self.member(sid).alias
        code, out = self.cli("retire", sid[:8])
        self.assertEqual(code, 0, out)
        for name in ("%s/%s" % (self.p.name, alias), "%s#%s" % (alias, sid[:8])):
            for verb in VERBS:
                with self.subTest(name=name, verb=verb):
                    code, out = self.cli(*argv_of(verb, name, "after its end"))
                    self.assertEqual(code, 4, out)
                    self.assertIn("returns when its human reopens it", out)
        self.assertEqual(self.logged("after its end"), [])

    # Minor
    def test_a_stale_event_asks_no_reach_for_a_direct_send(self):
        tid, sid = self.human_thread()
        received = self.terminal(sid)
        stale = Direct.stale(self, sid, "to no one")
        real = sminos.ReachGate.needs
        with mock.patch.object(sminos.ReachGate, "needs",
                               lambda g, e, session: e["seq"] == stale["seq"] and e["writer"] == stale["writer"]
                               or real(g, e, session)):
            code, out = self.send(sid[:8], "goes now")
        self.assertEqual(code, 0, out)
        self.assertNotIn("the endpoint decides", out)
        self.assertEqual(sum(f.count("goes now") for f in self.received(received)), 1)


class Round2(Verbs):
    """What the second review found: a refused stop's owed line, no wake for an unrecorded message, a receipt
    pending is no hand-off, both endpoint refusals of a returned seat's task, a live job's turn left running
    under a reason, an ended `alias#short` from another project."""

    # I1
    def test_a_refused_stop_leaves_the_task_owed_and_says_so(self):
        s = self.seat()
        self.cli("send", "w", "up")
        with mock.patch.object(sminos, "claude_stop", lambda short: False), \
                mock.patch.dict(os.environ, {"SMINOS_ACK_TIMEOUT": "1"}):
            code, out = self.cli("resume", "w", "over a running turn", "--wait")
        self.assertNotEqual(code, 0, out)
        self.assertIn("claude stop", out)
        self.assertTrue(self.owed_mark(out, s["current"]), out)
        self.assertTrue(self.owes(s["current"], "over a running turn"), "owed")

    # I2
    def projectless(self, alias="w"):
        real = sminos.seat_project
        p = mock.patch.object(sminos, "seat_project",
                              lambda seat, fresh=False: None if seat and seat.get("alias") == alias
                              else real(seat, fresh))
        p.start()
        self.addCleanup(p.stop)

    def test_a_stopped_projectless_seat_is_woken_for_no_unrecorded_message(self):
        s = self.seat()
        self.projectless()
        launched = self.launches()
        for argv in (("send", "w", "unrecorded wait", "--wait"), ("send", "w", "unrecorded")):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("nothing was started", out)
        self.assertEqual(self.launches(), launched, "no wake")
        self.assertFalse([i for i in self.inputs(s["current"]) if "unrecorded" in i["message"]["content"]])

    def test_a_live_projectless_seat_still_takes_the_owner_checked_push(self):
        s = self.seat()
        self.cli("send", "w", "up")
        self.projectless()
        code, out = self.cli("send", "w", "straight to it")
        self.assertEqual(code, 0, out)
        self.assertTrue(wait_for(lambda: [i for i in self.inputs(s["current"])
                                          if "straight to it" in i["message"]["content"]]))

    # I3
    def test_a_receipt_awaiting_with_no_hand_off_is_owed_and_waits_for_nothing(self):
        tid, sid = self.human_thread()
        self.say("@%s up" % sid[:8])

        def pending(project, member, due=False, **kw):
            return {"outcomes": [(e, sminos.HOLDER_AWAITING) for e in sminos.owed(project, member)]}
        with mock.patch.object(sminos, "deliver_next", pending):
            code, out = self.cli("send", sid[:8], "not handed yet", "--wait")
        self.assertEqual(code, 4, out)
        self.assertTrue(self.owed_mark(out, sid), out)
        self.assertNotIn("--- reply ---", out)
        self.assertNotIn("no evidence", out, "no watcher")

    # I4
    def returned_refusal(self, refuse, **env):
        s = self.seat()
        code, out = self.cli("retire", "w")
        self.assertEqual(code, 0, out)
        self.cut_over()
        with mock.patch.dict(os.environ, env):
            p = self.run_cli("fill", "w", "refuse this", "--resume")
        self.addCleanup(lambda: p.poll() is None and p.kill())
        project = sminos.seat_project(sminos.reload_seat(s["seat_id"]))

        def recorded():
            sminos.forget_caches()
            return [x for x in sminos.log_read(project) if x.get("text") == "refuse this"]
        self.assertTrue(wait_for(recorded, timeout=60), "recorded")
        [e] = recorded()
        seat = sminos.reload_seat(s["seat_id"])
        self.assertTrue(wait_for(lambda: self.member(seat["current"], project) is not None, timeout=30))
        refuse(project, self.member(seat["current"], project), e)
        out, err = p.communicate(timeout=90)
        return p.returncode, out + err

    def test_a_returned_seats_task_refused_by_reach_says_both(self):
        code, said = self.returned_refusal(lambda project, m, e: sminos.deliver_reach(project, m, e, "refuse",
                                                                                     "not shared"),
                                           SMINOS_VERDICT_WAIT="60")
        self.assertEqual(code, 4, said)
        self.assertIn("returned", said)
        self.assertIn("refused", said)
        self.assertNotIn("are confirmed yet", said)

    def test_a_returned_seats_task_queued_for_its_writers_head_is_said_queued(self):
        # frontier review, scalpel-3#7: the task's append waits (WaitingSend, no seq) once the seat runs again.
        seats = {wait: self.seat("q%d" % wait) for wait in (False, True)}
        for s in seats.values():
            self.cli("retire", s["alias"])
        self.cut_over()
        with open(os.path.join(sminos.root(), "daemon.log"), "a"):
            pass   # a daemon.log there: the refusal lookup is reached
        for wait, s in seats.items():
            with self.subTest(wait=wait):
                with mock.patch.object(sminos, "waits_for_head", return_value=True), \
                        mock.patch.dict(os.environ, {"SMINOS_VERDICT_WAIT": "1"}):
                    code, out = self.cli("fill", s["alias"], "queued task", "--resume",
                                         *(["--wait"] if wait else []))
                self.assertEqual(code, 4 if wait else 0, out)
                self.assertNotIn("Traceback", out)
                self.assertIn("returned and its session runs; its task waits", out)
                self.assertIn("queued", out)
                self.assertTrue(self.owed_mark(out, sminos.reload_seat(s["seat_id"])["current"]), out)

    def test_a_returned_seats_task_still_pending_starts_no_watcher(self):
        s = self.seat()
        self.cli("retire", "w")
        self.cut_over()
        with mock.patch.dict(os.environ, {"SMINOS_VERDICT_WAIT": "1", "SMINOS_ACK_TIMEOUT": "1"}):
            code, out = self.cli("fill", "w", "waits for its verdict", "--resume", "--wait")
        self.assertEqual(code, 4, out)
        self.assertIn("no push of its task and no refusal of it are confirmed yet", out)
        self.assertTrue(self.owed_mark(out, sminos.reload_seat(s["seat_id"])["current"]), out)
        self.assertNotIn("no evidence", out, "no watcher")
        self.assertNotIn("--- reply ---", out)

    # I5
    def test_resume_of_a_live_job_under_a_reason_pushes_to_it_and_leaves_its_turn(self):
        s = self.seat()
        sid = s["current"]
        self.cli("send", "w", "up")
        self.foreign(sid)
        resumes, before = len(self.resumes(sid)), len(self.calls())
        code, out = self.cli("resume", "w", "to the running one")
        self.assertEqual(code, 0, out)
        self.assertIn("its turn was not stopped", out)
        self.assertIn(WORDS["config"], out)
        self.assertNotIn("via --bg --resume", out)
        self.assertNotIn("a terminal holds it", out)
        self.assertFalse([c for c in self.calls()[before:] if c["argv"][:1] == ["stop"]], "no stop")
        self.assertEqual(len(self.resumes(sid)), resumes, "no wake")
        self.assertEqual(sum(f.count("to the running one") for f in self.frames(sid)), 1)

    # I6
    def test_an_ended_alias_and_short_from_another_project_is_said_ended(self):
        tid, sid = self.human_thread()
        alias = self.member(sid).alias
        code, out = self.cli("retire", sid[:8])
        self.assertEqual(code, 0, out)
        other = self.repo("other")
        code, out = self.cli("project", "init", "--name", "other", cwd=other)
        self.assertEqual(code, 0, out)
        for verb in VERBS:
            with self.subTest(verb=verb):
                code, out = self.cli(*argv_of(verb, "%s#%s" % (alias, sid[:8]), "from elsewhere"), cwd=other)
                self.assertEqual(code, 4, out)
                self.assertIn("returns when its human reopens it", out)


class Round3(Verbs):
    """What the third review found: a hand-off not admitted by the deadline is owed, hand-off evidence is the call's
    own outcome, a refusal is matched by the event's identity."""

    def test_a_hand_off_not_admitted_by_the_deadline_is_said_owed(self):
        tid, sid = self.human_thread()
        self.say("@%s up" % sid[:8])

        def handed_unadmitted(project, member, due=False, **kw):
            # Handed to a receipt's process, its admission (and so its row in the conversation) yet to come.
            return {"outcomes": [(e, sminos.HandedOff()) for e in sminos.owed(project, member)]}
        with mock.patch.object(sminos, "deliver_next", handed_unadmitted), \
                mock.patch.dict(os.environ, {"SMINOS_ACK_TIMEOUT": "1"}):
            code, out = self.cli("send", sid[:8], "queued in the engine", "--wait")
        self.assertEqual(code, 1, out)
        self.assertTrue(self.owed_mark(out, sid), out)
        self.assertIn("no evidence", out)

    def test_hand_off_evidence_is_the_outcome_not_a_record_of_this_process(self):
        self.assertFalse(hasattr(sminos, "HANDED_OFF"), "no process-wide history")
        self.assertEqual(sminos.HandedOff(), sminos.HOLDER_AWAITING)
        self.assertTrue(sminos.holder_waiting(sminos.HandedOff()), "owed until admitted, wherever it is compared")
        self.assertTrue(json.loads(json.dumps(sminos.HandedOff())) == sminos.HOLDER_AWAITING)

    def test_a_refusal_is_matched_by_the_events_identity_alone(self):
        sid = str(uuidlib.uuid4())
        other_sid = sid[:8] + str(uuidlib.uuid4())[8:]   # the same short
        twin = self.p._replace(id=str(uuidlib.uuid4()))   # another project under the same name
        e = {"writer": "testhost/human", "seq": 3}
        for said in (sminos.WORDS_REFUSED_SAID % ("testhost/human:3", self.p.name, sid,
                                                  sminos.refused_key(self.p, sid, e)),
                     sminos.REACH_REFUSED_SAID % ("testhost/human:3", self.p.name, sid[:8], "no reason given",
                                                  sminos.refused_key(self.p, sid, e))):
            with self.subTest(said=said[:40]):
                open(os.path.join(sminos.root(), "daemon.log"), "w").close()
                sminos.daemon_log(said)
                self.assertTrue(sminos.refusal_logged(self.p, sid, e))
                self.assertFalse(sminos.refusal_logged(twin, sid, e), "another project of the same name")
                self.assertFalse(sminos.refusal_logged(self.p, other_sid, e), "another session of the same short")
                self.assertFalse(sminos.refusal_logged(self.p, sid, {**e, "seq": 4}), "another event")



class Round4(Verbs):
    """What the second frontier review found in what a waiter reads and what a sender is told."""

    def test_a_row_put_into_the_running_turn_does_not_end_the_wait(self):
        """A text-bearing user row inside the turn that holds the message (the bridge's second delivery, which a
        plugin appends; the engine's own meta row) is no prompt of another turn: the waiter waits for the reply."""
        put = {"a plugin's": {"origin": {"kind": "plugin", "name": "sminos"}}, "the engine's": {}}
        for who, origin in put.items():
            with self.subTest(row=who):
                tid, sid = self.human_thread()
                self.switch("reply-delay", 4)
                text = "mine, then %s row" % who
                p = self.run_cli("send", sid[:8], text, "--wait")
                self.addCleanup(lambda p=p: p.poll() is None and p.kill())
                [event] = wait_for(lambda: self.logged(text), timeout=30)
                self.assertTrue(wait_for(lambda: sminos.transcript_contains(sid, "id=%s]" % event["msg_id"]),
                                         timeout=30), "its prompt is in")
                row = {"type": "user", "isMeta": True, "sessionId": sid, "uuid": str(uuidlib.uuid4()),
                       "message": {"role": "user", "content": [
                           {"type": "text", "text": sminos.compose_frame("bee", "other001", "theirs")}]}, **origin}
                with open(sminos.transcript_now(sid), "a") as f:
                    f.write(json.dumps(row) + "\n")
                out, err = p.communicate(timeout=60)
                self.assertEqual(p.returncode, 0, out + err)
                self.assertIn("reply to %s" % event["msg_id"], out, "the reply, not an empty one")
                os.unlink(os.path.join(self.state, "reply-delay"))

if __name__ == "__main__":
    unittest.main()
