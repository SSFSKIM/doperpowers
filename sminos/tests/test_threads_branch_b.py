#!/usr/bin/env python3
"""T1's branch review, group B: each interleaving a reviewer found, driven
(docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md, Interfaces §1, §4,
§6).

- A push's inbox frame after a declined bridge is bound to its recipient
  again; what is addressed to a reopened session whose inbox does not answer
  yet stays owed.
- A stopped thread's questions are closed within its own episodes, in the
  project each was asked in.
- A send's end found after its append is decided under its locks, and says
  what was recorded; a running session its human opened is not told it is
  stopped.
- The sweep ends only the canonical record; a lane B join is not stamped
  with a thread that only had the session; launch options end at `--`.
- `join` reads the membership it leaves under its lock, and that lock stays
  one file.
- Derive is shown the line the member's row shows.

Hermetic, as test_threads.Machine.
Run: python3 -B sminos/tests/test_threads_branch_b.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import fcntl
import io
import json
import os
import sys
import threading
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import records, sminos, threads  # noqa: E402
from test_threads_stopped import Rig  # noqa: E402


def ago(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))


def question(src):
    return {"kind": "question", "from": "alpha", "to": "host", "text": ["which way?"], "choices": [], "src": src}


class Push(Rig):
    def test_the_inbox_frame_after_a_declined_bridge_goes_to_no_session_a_clear_put_there(self):
        sid, proc = self.opened(inbox=True)
        e = sminos.log_append(self.p, "testhost/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "for alpha"})
        control = sminos.control_module()
        peer = sminos.peer_for_session(sid)

        def declined_meanwhile_cleared(*_a):
            self.peer_set(proc, sessionId=str(uuidlib.uuid4()))   # the /clear: the same pid and socket
            return False
        with mock.patch.object(control, "deliver", side_effect=declined_meanwhile_cleared), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(sminos.SendFailed) as caught:
                control.push_live(peer, sid, "for alpha", e, self.p.id, words=True)
        self.assertEqual(caught.exception.phase, "before")
        self.assertEqual(self.inbox(sid), [], "nothing through the socket the new session holds")

    def test_a_held_message_stays_owed_until_the_reopened_inbox_answers(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        code, out = self.say("@alpha while you were away")
        self.assertEqual(code, 0, out)
        _, quiet = self.session(sid=sid)
        self.peer_set(quiet, nameSource="user", messagingSocketPath=os.path.join(self.home, "none.sock"))
        self.assertEqual(threads.hold_now(sid), "", "the hold is lifted by the process's record")
        for _ in range(sminos.DELIVERY_ATTEMPTS + 1):
            self.tick()
        self.assertEqual(len(self.owed_to(sid)), 1, "still owed while its inbox does not answer")
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
        self.end(quiet)
        self.live(sid=sid, inbox=True)
        self.tick()
        self.assertEqual(self.owed_to(sid), [])
        self.assertTrue(any("while you were away" in x for x in self.inbox(sid)), self.inbox(sid))


class Questions(Rig):
    def closed_srcs(self, sid, p=None):
        return sorted(e["src"] for e in self.own(sid, p) if e["kind"] == "answered" and e.get("closed"))

    def test_a_former_session_running_as_another_thread_keeps_its_question_open(self):
        old, new, tid, other = (str(uuidlib.uuid4()) for _ in range(4))
        self.write_own(old, [self.old_joined(old, alias="alpha", thread=tid), question("q-in-thread"),
                             {"kind": "retired", "by": "", "reason": "continued", "to": new, "thread": tid},
                             self.old_joined(old, alias="alpha", thread=other), question("q-its-own")])
        sminos.close_questions({"thread": tid, "sessions": [old, new], "current": new})
        self.assertEqual(self.closed_srcs(old), ["q-in-thread"])

    def test_a_question_is_closed_in_the_project_it_was_asked_in(self):
        there = self.project_of(self.repo("there"))
        sid, tid = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        self.write_own(sid, [self.old_joined(sid, alias="alpha", thread=tid), question("q-here"),
                             {"kind": "retired", "by": "", "reason": "moved", "project": there.id, "thread": tid}])
        self.write_own(sid, [self.old_joined(sid, alias="alpha", thread=tid, by="join")], p=there)
        self.assertEqual(sminos.last_project(sid).id, there.id)
        sminos.close_questions({"thread": tid, "sessions": [sid], "current": sid})
        self.assertEqual(self.closed_srcs(sid), ["q-here"])


class Send(Rig):
    def ended_after_the_append(self, then):
        """canonical_end: none at the check before the append, an end at the
        check after it, then `then` (None: a return in between)."""
        calls = []

        def end(*_a):
            calls.append(1)
            if len(calls) == 1:
                return None
            if len(calls) == 2:
                return {"at": sminos.now(), "reason": "retire", "by": "", "pid": None}
            return then
        return mock.patch.object(sminos, "canonical_end", side_effect=end)

    def test_an_end_found_after_the_append_is_final_whatever_follows_the_locks(self):
        sid, _ = self.live(inbox=True)
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        with self.ended_after_the_append(None):
            code, out = self.cli("send", "g/w", "after its end")
        self.assertEqual(code, 4, out)
        self.assertEqual(self.inbox(sid), [], "nothing pushed")

    def test_a_human_opened_seats_end_after_the_append_says_the_message_was_recorded(self):
        sid, _ = self.opened(inbox=True)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        sminos.forget_caches()
        with self.ended_after_the_append({"at": sminos.now(), "reason": "retire", "by": "", "pid": None}):
            code, out = self.cli("send", "g/w", "after its end")
        self.assertEqual(code, 4, out)
        self.assertNotIn("nothing was recorded", out)
        self.assertIn("was recorded and is settled with its end", out)

    def test_a_running_session_its_human_opened_is_not_told_it_is_stopped(self):
        sid, _ = self.opened(inbox=True)
        for argv in (("resume", "alpha", "x"), ("fill", "alpha", "x", "--resume")):
            with self.subTest(argv=argv), mock.patch.object(sminos, "run_claude_bg") as launched:
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                launched.assert_not_called()
                self.assertIn("nothing was started", out)
                self.assertNotIn("stopped", out)
                self.assertNotIn("reopens", out)
                self.assertIn("its session runs", out)


class Canonical(Rig):
    def test_the_sweep_ends_no_seat_an_older_copy_made_over_a_human_opened_thread(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        human = threads.thread_of(sid)["thread"]
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        sminos.forget_caches()
        at = ago(7200)
        self.assertTrue(threads.update(seat_id, {"stopped": at}))
        seat = threads.get(seat_id)
        asked = threads.shorts_of(threads.owner_sessions(seat))
        self.assertEqual(self.daemon.end_stopped(threads, seat_id, sid, at, asked), [])
        self.assertEqual(sminos.end_by_rule(seat, at, asked), [], "nor through the end's own guard")
        sminos.forget_caches()
        self.assertFalse(threads.record_ended(threads.get(seat_id)))
        self.assertFalse(threads.record_ended(threads.get(human)))
        self.assertEqual(threads.in_effect(self.own(sid))["kind"], "joined")

    def test_a_lane_b_join_is_not_stamped_with_a_thread_that_only_had_the_session(self):
        old, _ = self.opened()
        tid = threads.thread_of(old)["thread"]
        new = str(uuidlib.uuid4())
        path = os.path.join(threads.store_dir(), tid + ".json")
        with open(path) as f:
            raw = json.load(f)
        sminos.write_json(path, dict(raw, current=new, sessions=[old, new]))   # handed off to `new`
        sminos.forget_caches()
        records.set_controller(old, "B")
        t, action = threads.choose(old)
        self.assertEqual((t, action), (None, "join"))

    def test_launch_options_end_at_the_end_of_options(self):
        self.assertEqual(threads.launch_options(["claude", "--model", "opus", "--", "--dangerously-skip-permissions",
                                                 "--model", "x"]), ["--model", "opus"])


class Join(Rig):
    def test_two_joins_that_both_read_the_same_membership_leave_one(self):
        b, c = self.project_of(self.repo("b")), self.project_of(self.repo("c"))
        sid, _ = self.session()
        self.reconcile()
        real, nested = sminos.moving, []

        @contextlib.contextmanager
        def another_join_first(session):
            if not nested:
                nested.append(1)
                code, out = self.cli("join", b.name)   # read the same membership, took the lock first
                self.assertEqual(code, 0, out)
            with real(session):
                yield
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}), \
                mock.patch.object(sminos, "moving", side_effect=another_join_first):
            code, out = self.cli("join", c.name)
        self.assertEqual(code, 0, out)
        self.assertEqual([self.is_member(sid, p) for p in (self.p, b, c)], [False, False, True])

    def test_the_move_lock_stays_one_file_for_a_join_that_waited(self):
        sid = str(uuidlib.uuid4())
        path = sminos.override_path(sid) + ".lock"
        first_in, first_go, second_in = threading.Event(), threading.Event(), threading.Event()

        def first():
            with sminos.moving(sid):
                first_in.set()
                first_go.wait(10)

        def second():
            first_in.wait(10)
            with sminos.moving(sid):
                second_in.set()
                time.sleep(0.5)
        threads_ = [threading.Thread(target=first), threading.Thread(target=second)]
        for t in threads_:
            t.start()
        first_in.wait(10)
        time.sleep(0.2)   # the second join waits on the lock
        first_go.set()
        self.assertTrue(second_in.wait(10))
        try:
            with open(path) as f:   # a third join, as moving_elsewhere looks
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        finally:
            for t in threads_:
                t.join(10)


class Derive(Rig):
    def test_derive_is_shown_the_line_its_row_shows(self):
        old, new, seat, other = (str(uuidlib.uuid4()) for _ in range(4))
        self.write_own(old, [self.old_joined(old, alias="w", thread=seat, seat=seat),
                             {"kind": "in-charge", "text": "the seat's work", "source": "set"},
                             {"kind": "retired", "by": "", "reason": "replaced", "thread": seat}])
        self.write_own(new, [self.old_joined(new, alias="w", thread=seat, seat=seat)])
        self.write_own(old, [self.old_joined(old, alias="old", thread=other),
                             {"kind": "in-charge", "text": "something unrelated", "source": "set"}])
        m = self.member(new)
        self.assertEqual(m.charge, "the seat's work")
        self.assertEqual(sminos.current_line(self.p, m), "the seat's work")


if __name__ == "__main__":
    unittest.main()
