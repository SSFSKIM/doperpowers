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
import subprocess
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


def reopened_now():
    """A reopening process's start (the engine record's startedAt), after what was held for it."""
    time.sleep(0.01)
    return int(time.time() * 1000)


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
        _, quiet = self.session(sid=sid, started=reopened_now())
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


class Wave2Push(Rig):
    """The invariant (review 2, items 2 and 8): for a thread its human
    opened, an addressed message that was held stays owed until it is pushed
    to that thread's process or the thread ends."""

    def held_then_reopened(self, socket_path):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        code, out = self.say("@alpha while you were away")
        self.assertEqual(code, 0, out)
        _, quiet = self.session(sid=sid, started=reopened_now())
        fields = {"nameSource": "user"}
        if socket_path:
            fields["messagingSocketPath"] = socket_path
        self.peer_set(quiet, **fields)
        return sid, quiet

    def assert_owed_then_pushed(self, sid, quiet):
        for _ in range(sminos.DELIVERY_ATTEMPTS + 1):
            self.tick()
        self.assertEqual(len(self.owed_to(sid)), 1, "not pushed yet: still owed")
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
        self.end(quiet)
        self.live(sid=sid, inbox=True)
        self.tick()
        self.assertEqual(self.owed_to(sid), [])
        self.assertTrue(any("while you were away" in x for x in self.inbox(sid)), self.inbox(sid))

    def test_a_reopened_process_whose_record_names_no_socket_yet(self):
        self.assert_owed_then_pushed(*self.held_then_reopened(None))

    def test_a_reopened_process_whose_inbox_does_not_answer_yet(self):
        self.assert_owed_then_pushed(*self.held_then_reopened(os.path.join(self.home, "none.sock")))

    def test_through_a_seat_an_older_copy_made_over_the_session(self):
        sid, proc = self.opened()
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "alpha", "group": "g",
                                  "cwd": self.root, "status": "idle"})
        sminos.forget_caches()
        self.end(proc)
        self.reconcile()
        sminos.lifecycle(self.p, str(uuidlib.uuid4()), "say", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "while you were away"})
        sminos.forget_caches()
        self.assertEqual(len(self.owed_to(sid)), 1)
        self.assertIsNotNone(self.member(sid).seat, "the seat branch delivers it")
        _, quiet = self.session(sid=sid, started=reopened_now())
        self.peer_set(quiet, nameSource="user", messagingSocketPath=os.path.join(self.home, "none.sock"))
        with mock.patch.object(sminos, "run_claude_bg") as launched:
            self.assert_owed_then_pushed(sid, quiet)
        launched.assert_not_called()

    def test_the_supervisor_is_not_handed_a_job_a_clear_moved(self):
        sid, proc = self.opened(inbox=True)
        self.peer_set(proc, kind="bg", jobId="ab12cd34")
        e = sminos.log_append(self.p, "testhost/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "for alpha"})
        control = sminos.control_module()
        peer = sminos.peer_for_session(sid)

        def declined_meanwhile_cleared(*_a):
            self.peer_set(proc, sessionId=str(uuidlib.uuid4()))   # the /clear: the same pid, job and socket
            return None
        with mock.patch.object(control, "deliver", side_effect=declined_meanwhile_cleared), \
                mock.patch.object(control, "supervisor_reply", return_value=True) as supervisor:
            with self.assertRaises(sminos.SendFailed):
                control.push_live(peer, sid, "for alpha", e, self.p.id, words=True)
        supervisor.assert_not_called()
        self.assertEqual(self.inbox(sid), [])


class Wave2Join(Rig):
    def test_a_reopened_lane_b_predecessors_joined_carries_no_successors_stamp(self):
        old, proc = self.opened()
        tid = threads.thread_of(old)["thread"]
        new = str(uuidlib.uuid4())
        self.write_own(old, [{"kind": "retired", "by": "", "reason": "continued", "to": new, "thread": tid}])
        path = os.path.join(threads.store_dir(), tid + ".json")
        with open(path) as f:
            raw = json.load(f)
        sminos.write_json(path, dict(raw, current=new, sessions=[old, new]))   # handed off to `new`
        self.end(proc)
        records.set_controller(old, "B")
        time.sleep(1.1)
        self.session(sid=old, started=int(time.time() * 1000))   # reopened, lane B
        self.reconcile()
        joins = self.joins(old)
        self.assertGreater(len(joins), 1, "it joined again")
        self.assertNotIn("thread", joins[-1], "unstamped: the thread that only had it is not its stamp")


class Wave2Questions(Rig):
    def test_a_former_sessions_unmarked_question_elsewhere_stays_open(self):
        there = self.project_of(self.repo("there"))
        old, new, tid = (str(uuidlib.uuid4()) for _ in range(3))
        self.write_own(old, [self.old_joined(old, alias="alpha", thread=tid),
                             {"kind": "retired", "by": "", "reason": "continued", "to": new, "thread": tid}])
        self.write_own(old, [self.old_joined(old, alias="alpha"), question("q-there")], p=there)   # an older hook
        self.write_own(new, [self.old_joined(new, alias="alpha", thread=tid), question("q-mine")])
        got = sminos.close_questions({"thread": tid, "sessions": [old, new], "current": new})
        self.assertEqual([e["src"] for e in got], ["q-mine"])
        self.assertEqual([e for e in self.own(old, there) if e["kind"] == "answered"], [])


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

    def test_a_waiting_send_whose_seat_ended_says_it_waits(self):
        sid, _ = self.opened(inbox=True)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        sminos.forget_caches()
        with self.ended_after_the_append({"at": sminos.now(), "reason": "retire", "by": "", "pid": None}), \
                mock.patch.object(sminos, "waits_for_head", return_value=True):
            code, out = self.cli("send", "g/w", "after its end")
        self.assertEqual(code, 4, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("it waits in", out)
        self.assertEqual(self.inbox(sid), [])

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



# ------------------------------------------------------------ the third wave: the findings first set aside as debt


class Debt(Rig):
    def test_a_seatless_session_retired_after_lookup_is_pushed_nothing(self):
        """[scalpel-5#5]"""
        sid, _ = self.opened(inbox=True)
        real = sminos.record_message

        def retired_first(*a, **k):
            with mock.patch.object(sminos, "claude_stop", return_value=True):
                code, out = self.cli("retire", "alpha")
            self.assertEqual(code, 0, out)
            return real(*a, **k)
        with mock.patch.object(sminos, "record_message", side_effect=retired_first):
            code, out = self.cli("send", "alpha", "after its retire")
        self.assertEqual(code, 4, out)
        self.assertIn("has ended", out)
        self.assertEqual(self.inbox(sid), [], "nothing pushed")

    def test_the_records_export_waits_out_a_join_that_holds_the_move_lock(self):
        """[scalpel-1#13] The bridge's export, in another process, while a
        `join` holds the move lock, its override written: the join's own
        `joined` says `join`."""
        there = self.project_of(self.repo("there"))
        sid, _ = self.session()
        real = sminos.write_override
        script = ("import sys; sys.path.insert(0, %r); import sminos; sminos.export_live(%r, %r, [])"
                  % (sminos.os.path.dirname(sminos.__file__), self.root, sid))

        def exported_meanwhile(session, pid):
            real(session, pid)
            subprocess.run([sys.executable, "-B", "-c", script], check=True, timeout=60)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}), \
                mock.patch.object(sminos, "write_override", side_effect=exported_meanwhile):
            code, out = self.cli("join", there.name)
        self.assertEqual(code, 0, out)
        self.assertEqual([e.get("by") for e in self.joins(sid, there)], ["join"])

    def test_two_alias_copies_in_the_other_order_leave_the_later(self):
        """[scalpel-2#8]"""
        sid, _ = self.opened(charge="")
        tid = threads.thread_of(sid)["thread"]
        copies, real = [], threads.note_alias
        with mock.patch.object(threads, "note_alias", side_effect=lambda *a, **k: copies.append((a, k))):
            for alias in ("first", "second"):
                sminos.lifecycle(self.p, sid, "renamed", alias=alias, name_source="user")
        self.assertEqual(len(copies), 2)
        for a, k in reversed(copies):
            real(*a, **k)
        sminos.forget_caches()
        self.assertEqual(threads.get(tid)["alias"], "second")

    def test_a_remote_legacy_seats_id_reaches_its_session(self):
        """[scalpel-3#9]"""
        sid, seat = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        sminos.log_append(self.p, "elsewhere/%s" % sid, "joined", session=sid, alias="far", name_source="seat",
                          machine="elsewhere", cwd="/w", worktree="", role="", seat=seat, by="",
                          session_kind="bg")
        sminos.forget_caches()
        code, out = self.cli("send", seat, "by its seat id")
        self.assertEqual(code, 0, out)
        self.assertIn("far", out)
        self.assertEqual([e["text"] for e in self.own_to(sid)], ["by its seat id"])

    def own_to(self, sid):
        sminos.forget_caches()
        return [e for e in sminos.log_read(self.p, to_session=sid) if e["kind"] in ("human", "say")]

    def test_a_clear_after_an_outlived_release_releases_its_new_alias(self):
        """[scalpel-4#12]"""
        old, proc = self.opened()
        tid = threads.thread_of(old)["thread"]
        self.assertTrue(sminos.release_alias(self.p, old, "alpha"))
        self.end(proc)
        time.sleep(1.1)
        self.live(sid=old, name="gamma", started=int(time.time() * 1000))   # reopened after the release
        got = sminos.release_alias(self.p, old, "gamma")
        self.assertTrue(got, "the second clear's release")
        self.assertEqual(threads.get(tid)["released"]["alias"], "gamma")

    def test_a_resume_of_an_ended_session_an_older_copy_seated_records_nothing(self):
        """[scalpel-5#6]"""
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 0, out)
        self.assertTrue(threads.record_ended(threads.thread_of(sid)))
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        sminos.forget_caches()
        with mock.patch.object(sminos, "run_claude_bg") as launched:
            code, out = self.cli("resume", "g/w", "after its end")
        self.assertEqual(code, 4, out)
        launched.assert_not_called()
        self.assertNotIn("reads the message", out)
        self.assertEqual([e for e in self.own_to(sid) if e.get("text") == "after its end"], [], "nothing recorded")

    def test_an_unreadable_record_adopts_nothing(self):
        """[scalpel-5#8]"""
        sid, _ = self.session()
        path = records.record_path(sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("{not json")
        self.reconcile()
        self.assertEqual(self.human_files(), [], "no thread minted while its lane cannot be read")
        self.assertEqual([e.get("thread") for e in self.joins(sid)], [], "and nothing joined")

    def test_a_refused_send_leaves_no_seat_lock_held(self):
        """The older residue: a `send` refusal path left its name lock open."""
        code, out = self.cli("seat", "add", "g", "w", "--session", str(uuidlib.uuid4()))
        self.assertEqual(code, 0, out)
        held = []
        real = sminos.lock_names
        with mock.patch.object(sminos, "lock_names", side_effect=lambda *a, **k: held.append(real(*a, **k)) or held[-1]):
            sminos.forget_caches()
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    sminos.cmd_send(sminos.build_parser().parse_args(["send", "g/w", "x"]))
            except SystemExit as e:
                self.assertEqual(e.code, 4)
        self.assertTrue(held)
        self.assertTrue(all(lf.closed for locks in held for lf in locks), "every seat lock closed")


class EndedReceipt(Rig):
    """[scalpel-5#7] The end's settlement of an event a gate process admitted."""

    def test_an_admitted_receipt_settles_delivered_at_the_end(self):
        hd = sminos.holder_module()
        outcomes = sminos.sibling_module("sminos_outcomes")
        hub = self.repo("hp")
        subprocess.run([sys.executable, "-B", os.path.join(os.path.dirname(sminos.__file__), "sminos.py"), "project",
                        "init", "--name", "hp"], cwd=hub, check=True, capture_output=True)
        smns = os.path.join(hub, ".smns")
        with open(smns) as f:
            d = json.load(f)
        d["hub"] = {"url": "http://127.0.0.1:9", "org": "org-1"}
        with open(smns, "w") as f:
            json.dump(d, f)
        hp = self.project_of(hub)
        self.root = hub
        sid, proc = self.live(inbox=True)
        self.assertEqual(hd.activate(proc.pid, "launch-1", sid)["mode"], "gate")
        e = {"ts": "2026-11-02T01:00:01.000Z", "writer": "othermachine/%s" % uuidlib.uuid4(), "seq": 1,
             "kind": "say", "from": "alice", "to": [{"session": sid, "alias": "m"}], "text": "admitted before the end"}
        self.assertEqual(sminos.sibling_module("sminos_hublog").append_verbatim(hp, e), "appended")
        m = sminos.Member(session=sid, short=sid[:8], alias="m", name_source="derived", machine="testhost",
                          local=True, state="idle", state_age=None, charge="", charge_source="", status="", by="",
                          worktree="", seat=None)
        sminos.deliver_next(hp, m)
        path = hd._receipt_path(hd.key_hash(hp.id, sid, e["writer"], e["seq"]))
        with open(path) as f:
            rid = json.load(f)["id"]
        self.assertTrue(hd.admit([rid], proc.pid, sid)["ok"])
        self.assertTrue(outcomes.settle_ended(hp, sid))
        got = [r["outcome"] for r in outcomes.Outbox(hp).read() if r["event"]["writer"] == e["writer"]]
        self.assertEqual(got, ["delivered"])

if __name__ == "__main__":
    unittest.main()
