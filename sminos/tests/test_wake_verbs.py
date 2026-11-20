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

from test_wake import answer, prompt, rows, wait_for  # noqa: E402
from test_wake_delivery import FLAGS, STARTING, TAIL, WORDS, Deliveries, line  # noqa: E402
from test_wake_seat import SCRIPT, sminos, threads, wake  # noqa: E402

VERBS = (("resume",), ("fill", "--resume"), ("send", "--wait"))


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
                [frame] = self.frames(sid)
                self.assertIn(wake.LINE_HEAD, frame.partition("\n\n")[0], "opened by the line")
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


if __name__ == "__main__":
    unittest.main()
