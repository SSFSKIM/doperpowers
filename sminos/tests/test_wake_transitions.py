#!/usr/bin/env python3
"""The wake against what else changes a thread (T2's M2:
docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md, the milestone's
"Proves" and its decision "Transitions take the wake lock"), against the
test engine:

- the two orders of a wake against the thread sweep's stop mark, and a wake
  that meets the sweep holding the lock;
- a retire while a wake holds the lock (refused, nothing changed; a
  reconciliation after it leaves the thread as the wake left it), and a
  wake inside a retire's open entry (nothing launched, a retire that
  reported success staying one); a wake's answer to an open entry is
  test_wake_seat.py's (row 5);
- a hand-off, which waits for a wake in flight and is made after it, and
  an absorption's reservation, which waits for a wake of the record it
  absorbs;
- a retired seat returned by `fill --resume`, what was owed before settled
  and its new task pushed, and left retired by a launch that failed;
- a `/clear`'s release while a launcher holds the lock.

Hermetic: test_wake_seat.Wakers (test_wake.Engine's engine first on PATH).
Run: python3 -B sminos/tests/test_wake_transitions.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
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

from test_wake_seat import Wakers, sminos, threads, wait_for  # noqa: E402


class Transitions(Wakers):
    def setUp(self):
        super().setUp()
        self.daemon = sminos.daemon_module()

    def sweep(self, n=1):
        for _ in range(n):
            sminos.forget_caches()
            self.daemon.sweep_threads()
        sminos.forget_caches()

    def in_background(self, fn):
        """fn run on a thread of its own; its result in the list returned once it ends."""
        out = []
        t = threading.Thread(target=lambda: out.append(fn()))
        t.start()
        self.addCleanup(t.join, 60)
        return t, out

    def barrier(self):
        self.switch("barrier")
        return lambda: os.unlink(os.path.join(self.state, "barrier"))


# ------------------------------------------------------------ the sweep's stop mark


class Sweep(Transitions):
    def test_a_wake_after_the_mark_lifts_it(self):
        tid, sid = self.human_thread()
        self.sweep(2)
        self.assertIn("stopped", threads.get(tid))
        self.assertTrue(self.wake(sid).live)
        self.assertNotIn("stopped", threads.get(tid), "the wake's W8 lifts the mark")
        self.sweep(2)
        self.assertNotIn("stopped", threads.get(tid), "and a process holds it")

    def test_a_wake_between_the_sweeps_two_passes_is_never_marked(self):
        tid, sid = self.human_thread()
        self.sweep()
        self.assertTrue(self.wake(sid).live)
        self.sweep(3)
        self.assertNotIn("stopped", threads.get(tid))

    def test_a_thread_whose_wake_accepted_a_job_still_starting_is_neither_marked_nor_ended(self):
        # frontier review, scalpel-1#3: W7's bound passed with the banner's job accepted and no process yet.
        tid, sid = self.human_thread()
        self.switch("late-process", 30)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "2"}):
            self.assertEqual(self.wake(sid).why, "starting")
        self.sweep(3)
        self.assertNotIn("stopped", threads.get(tid), "not marked stopped while it starts")
        old = "2026-01-01T00:00:00.000Z"
        self.assertTrue(threads.update(tid, {"stopped": old, "swept": old}))
        t = threads.get(tid)
        asked = threads.shorts_of(threads.owner_sessions(t))
        self.assertEqual(self.daemon.end_stopped(threads, tid, sid, old, asked), [], "not ended by the rule")
        self.assertIsNone(threads.get(tid).get("ended"))
        with mock.patch.dict(os.environ, {"SMINOS_WAKE_GRACE": "0"}):
            self.assertTrue(self.daemon.end_stopped(threads, tid, sid, old, asked), "ended once its grace passed")

    def test_an_accepted_launch_that_never_runs_is_a_failed_wake_backed_off_and_the_thread_still_stops_and_ends(self):
        # frontier review round 2, scalpel-2#1: each launch's banner accepted, its worker gone before it published.
        # A wake that finds that job dead counts the failure, so the daemon's next wake waits on §4's schedule; the
        # sweep counts one whose grace passed with no wake to look, and marks and ends the thread as any other.
        tid, sid = self.human_thread()
        self.switch("late-process", 60)
        env = {"SMINOS_UUID_POLL": "2", "SMINOS_WAKE_RETRY": "1", "SMINOS_WAKE_RETRY_MAX": "60",
               "SMINOS_WAKE_GRACE": "1.5"}
        launched, deadline = [], time.monotonic() + 40
        with mock.patch.dict(os.environ, env):
            while len(launched) < 3 and time.monotonic() < deadline:
                n = self.launches()
                got = sminos.wake(threads.get(tid), sid)   # the daemon's: on the schedule
                if self.launches() > n:
                    launched.append(time.monotonic())
                    self.assertEqual((got.live, got.why), (False, "starting"))
                    self.claude("stop", sid[:8])   # its worker gone before it published
                else:
                    self.assertEqual((got.live, got.why), (False, "failed"), "held on the schedule")
                time.sleep(0.05)
            self.assertEqual(len(launched), 3, "three launches")
            first, second = launched[1] - launched[0], launched[2] - launched[1]
            self.assertGreater(first, 1, "the first retry waits")
            self.assertGreater(second, first + 0.5, "and the next twice as long")
            self.assertEqual(self.waking(tid, sid)["failed"], 2)
            time.sleep(1.6)   # the third's grace passes with no wake to look
            self.sweep()
            waking = self.waking(tid, sid)
            self.assertEqual(waking["failed"], 3, "the sweep counts it")
            self.assertNotIn("job", waking)
            self.assertNotIn("line", waking, "its line removed with it")
            self.assertIn("its job %s was accepted and never ran" % sid[:8], self.daemon_log())
            self.sweep(2)
        self.assertIn("stopped", threads.get(tid), "marked stopped")
        old = "2026-01-01T00:00:00.000Z"
        self.assertTrue(threads.update(tid, {"stopped": old, "swept": old}))
        asked = threads.shorts_of(threads.owner_sessions(threads.get(tid)))
        self.assertTrue(self.daemon.end_stopped(threads, tid, sid, old, asked), "and ended by the rule")
        self.assertEqual(self.launches(), 3)

    def test_a_dead_accepted_launchs_line_goes_to_no_process_resumed_after_it(self):
        # frontier review round 2, scalpel-2#4: the accepted worker gone before it published; a background resume
        # of the same id by hand afterwards is no process of that launch, and is pushed no line of it.
        tid, sid = self.human_thread()
        self.switch("late-process", 60)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "2", "SMINOS_WAKE_GRACE": "1"}):
            self.assertEqual(self.wake(sid).why, "starting")
            self.assertEqual(self.waking(tid, sid)["line"]["short"], sid[:8])
            self.claude("stop", sid[:8])
            time.sleep(1.1)
            self.sweep()
        os.unlink(os.path.join(self.state, "late-process"))
        code, out, err = self.claude("--bg", "--resume", sid)
        self.assertEqual(code, 0, err)
        self.assertTrue(wait_for(lambda: self.record(sid) is not None))
        code, out = self.cli("say", "@%s after it" % sid[:8])
        self.assertEqual(code, 0, out)
        [frame] = [i["message"]["content"] for i in self.inputs(sid)]
        self.assertIn("after it", frame)
        self.assertNotIn(sminos.wake_module().LINE_HEAD, frame)

    def test_the_sweep_clears_a_wakes_state_only_for_a_process_it_reads_again_under_the_wake_lock(self):
        # frontier review round 2, scalpel-2#2: the pass's reading saw a process; it exited and a replacement wake
        # accepted its job before the sweep acted on that reading.
        tid, sid = self.human_thread()
        _, proc = self.session(sid=sid, kind="bg")
        real = threads.all_threads

        def after_its_reading():
            # The pass has read the engine's records (a process holds it); then that process exits and another
            # wake's banner is accepted.
            self.end(proc)
            self.assertTrue(threads.wake_job(tid, sid, sid[:8]))
            return real()
        with mock.patch.object(threads, "all_threads", after_its_reading):
            self.sweep()
        self.assertEqual(self.waking(tid, sid)["job"]["short"], sid[:8], "the replacement's job kept")
        # A process that holds it, while the lock is busy: the next tick's.
        self.edit(tid, waking={"session": sid, "failed": 2, "at": sminos.now()})
        _, proc = self.session(sid=sid, kind="bg")
        held, release = threading.Event(), threading.Event()

        def launcher():
            hold, _ = sminos.launch_hold(tid)
            held.set()
            release.wait(10)
            hold.release()
        t, _ = self.in_background(launcher)
        self.assertTrue(held.wait(5))
        self.sweep()
        self.assertEqual(self.waking(tid, sid)["failed"], 2, "left while a launch holds the lock")
        release.set()
        t.join(10)
        self.sweep()
        self.assertEqual(self.waking(tid, sid), {}, "cleared once read again under it")
        self.end(proc)

    def test_a_process_seen_by_the_sweep_clears_a_wakes_failures(self):
        # frontier review, scalpel-2#3: a terminal reopened after failed wakes, seen live by the sweep.
        tid, sid = self.human_thread()
        self.edit(tid, waking={"session": sid, "failed": 4, "at": sminos.now()})
        _, proc = self.session(sid=sid, kind="interactive", name="term-a")
        self.sweep()
        self.assertEqual(self.waking(tid, sid), {}, "the failures and the retry time cleared")
        self.end(proc)

    def test_a_wake_that_meets_the_sweeps_hold_waits_it_out_or_launches_nothing(self):
        tid, sid = self.human_thread()
        held, release = threading.Event(), threading.Event()

        def sweep_hold():
            with self.daemon.resume_lock_out(tid) as out:
                held.set()
                release.wait(10)
                return out
        t, out = self.in_background(sweep_hold)
        self.assertTrue(held.wait(5))
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            got = self.wake(sid)
        self.assertEqual((got.live, got.why), (False, "sweep"))
        self.assertEqual(self.launches(), 0, "nothing launched under the sweep's hold")
        release.set()
        t.join(10)
        self.assertEqual(out, [True])
        self.assertTrue(self.wake(sid).live, "once it let go")


# ------------------------------------------------------------ a retire, an end


class Retire(Transitions):
    def test_a_retire_while_a_wake_holds_the_lock_changes_nothing_and_the_wake_stands(self):
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        lift = self.barrier()
        t, got = self.in_background(lambda: sminos.wake(threads.get(seat_id), sid, due=True))
        self.assertTrue(wait_for(lambda: self.launches() >= 1 and self.resumes(sid)))
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            code, out = self.cli("retire", "w")
        self.assertEqual(code, 1, out)
        self.assertIn("is in flight: nothing was changed; run it again", out)
        lift()
        t.join(30)
        self.assertTrue(got[0].live)
        self.reconcile()
        fresh = sminos.reload_seat(seat_id)
        self.assertNotEqual(fresh["status"], "retired")
        self.assertNotIn("ended", threads.get(seat_id))
        self.assertIsNotNone(self.record(sid), "the woken process runs on")
        code, out = self.cli("retire", "w")
        self.assertEqual(code, 0, out)
        self.assertTrue(wait_for(lambda: self.record(sid) is None), "the retire stops what it saw")
        self.reconcile()
        self.assertEqual(sminos.reload_seat(seat_id)["status"], "retired", "a retire that reported success stays one")

    def test_a_wake_inside_a_retires_open_entry_launches_nothing(self):
        # The end's write sets `ended` with its entry: W2 reads ended before an open entry (§3's order).
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        seen = []
        real = threads.finish

        def finish(*a, **kw):
            if not seen and (threads.get(seat_id) or {}).get("pending"):   # the retire's entry, begun
                seen.append(sminos.wake(threads.get(seat_id), sid, due=True))
            return real(*a, **kw)
        with mock.patch.object(threads, "finish", side_effect=finish):
            code, out = self.cli("retire", "w")
        self.assertEqual(code, 0, out)
        self.assertEqual([(w.live, w.why) for w in seen], [(False, "ended")])
        self.assertEqual(self.resumes(sid), [], "nothing launched")
        self.assertEqual(self.wake(sid).why, "ended")
        self.reconcile()
        self.assertEqual(sminos.reload_seat(seat_id)["status"], "retired")


# ------------------------------------------------------------ a hand-off


class HandOff(Transitions):
    def test_a_hand_off_waits_for_a_wake_in_flight_and_is_made_after_it(self):
        tid, sid = self.human_thread()
        job = "22222222-3333-4444-8555-666666666666"
        taken, release = threading.Event(), threading.Event()

        def launcher():
            hold, _ = sminos.wake_lock(tid, holder=sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()))
            taken.set()
            release.wait(10)
            hold.release()
        t, _ = self.in_background(launcher)
        self.assertTrue(taken.wait(5))
        began = time.monotonic()
        with mock.patch.object(sminos, "_RECORD_DEADLINE", time.time() + 0.3):
            self.assertEqual(sminos.hand_off(self.p, sid, job), [], "the hook's hand-off left for later")
        self.assertLess(time.monotonic() - began, 3, "bounded by the hook's deadline")
        self.assertEqual((threads.get(tid)["current"], threads.get(tid).get("pending")), (sid, None), "unchanged")
        release.set()
        t.join(10)
        events = sminos.hand_off(self.p, sid, job)
        self.assertEqual([e["kind"] for e in events], ["retired", "joined"])
        self.assertEqual(threads.get(tid)["current"], job)


class HandOffRaces(Transitions):
    def continued(self, old, new):
        """The engine's hand-off of `old` to a background job `new`, as test_threads.Sessions writes it: the old
        transcript's `continued-in`, and the job's process."""
        with open(sminos.transcript_now(old), "a") as f:
            f.write(json.dumps({"type": "continued-in", "sessionId": old, "continuedInSessionId": new}) + "\n")
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        _, proc = self.session(kind="bg", sid=new, name="handyjob")
        self.peer_set(proc, nameSource="auto")
        return proc

    def test_a_hand_off_found_while_a_wake_is_past_w2_waits_and_the_wake_stands(self):
        tid, sid = self.human_thread()
        job = str(uuidlib.uuid4())
        lift = self.barrier()
        t, got = self.in_background(lambda: sminos.wake(threads.get(tid), sid, due=True))
        self.assertTrue(wait_for(lambda: self.launches() >= 1))
        self.continued(sid, job)
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            self.reconcile()
        self.assertEqual((threads.get(tid)["current"], threads.get(tid).get("pending")), (sid, None),
                         "the hand-off waits for the wake in flight: nothing written")
        lift()
        t.join(30)
        self.assertTrue(got[0].live)
        self.reconcile()
        # The session the wake started runs again: no hand-off is read from a session a process holds, and each
        # session is one record's (the job a thread of its own).
        rec = threads.get(tid)
        self.assertEqual((rec["current"], rec.get("pending")), (sid, None), "the wake stands")
        self.assertIsNotNone(self.record(sid))
        owner = threads.thread_of(job)
        self.assertTrue(owner is None or owner["thread"] != tid, "the job is not this thread's")

    def test_a_wake_after_a_hand_offs_begin_launches_nothing(self):
        tid, sid = self.human_thread()
        job = str(uuidlib.uuid4())
        self.continued(sid, job)
        seen = []
        real = threads.finish

        def finish(*a, **kw):
            if not seen and (threads.get(tid) or {}).get("pending"):   # the hand-off's entry, begun
                seen.append(sminos.wake(threads.get(tid), sid, due=True))
            return real(*a, **kw)
        with mock.patch.object(threads, "finish", side_effect=finish):
            self.reconcile()
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].live)
        self.assertIn(seen[0].why, ("gone", "pending"))
        self.assertEqual(self.resumes(sid), [], "nothing launched")
        self.reconcile()
        self.assertEqual(threads.get(tid)["current"], job)

    def test_an_absorption_waits_for_a_wake_of_the_record_it_absorbs(self):
        tid, sid = self.human_thread()                      # the thread that goes on in the job
        jtid, job = self.human_thread()                     # the job's own record, made before its hand-off
        lift = self.barrier()
        t, got = self.in_background(lambda: sminos.wake(threads.get(jtid), job, due=True))
        self.assertTrue(wait_for(lambda: self.launches() >= 1))
        with open(sminos.transcript_now(sid), "a") as f:
            f.write(json.dumps({"type": "continued-in", "sessionId": sid, "continuedInSessionId": job}) + "\n")
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.3), mock.patch.object(sminos, "_RECORD_DEADLINE",
                                                                             time.time() + 0.3):
            self.assertEqual(sminos.hand_off(self.p, sid, job), [], "the absorption waits")
        self.assertEqual(threads.get(tid)["current"], sid, "its owner unchanged")
        self.assertIsNone(threads.reservation(threads.get(jtid)), "the absorbed record untouched")
        lift()
        t.join(30)
        self.assertTrue(got[0].live, "the wake of the record stands")
        events = sminos.hand_off(self.p, sid, job)
        self.assertEqual([e["kind"] for e in events], ["retired", "joined"], "made after it")
        self.assertEqual(threads.get(tid)["current"], job)
        self.assertIsNone(threads.get(jtid), "the job's record absorbed")


# ------------------------------------------------------------ an absorption


class Absorption(Transitions):
    def test_its_reservation_waits_for_a_wake_of_the_record_it_absorbs(self):
        tid, sid = self.human_thread()
        taken, release = threading.Event(), threading.Event()

        def launcher():
            hold, _ = sminos.wake_lock(tid, holder=sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()))
            taken.set()
            release.wait(10)
            hold.release()
        t, _ = self.in_background(launcher)
        self.assertTrue(taken.wait(5))
        entry = {"id": "e-absorb", "op": "absorb", "other": tid}
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            got = threads._hold("absorber", entry, sid, time.time() + 0.3)
        self.assertEqual(got, "busy", "tried again by the next finish")
        self.assertIsNone(threads.reservation(threads.get(tid)), "nothing written")
        release.set()
        t.join(10)


    def free_elsewhere(self, tid):
        """Whether another process can take the record's wake lock now: no hold of this process is left on it."""
        code = ("import fcntl, sys\nf = open(sys.argv[1], 'a')\n"
                "try:\n    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\nexcept OSError:\n    sys.exit(1)\n")
        return subprocess.run([sys.executable, "-c", code, sminos.wake_lock_path(tid)]).returncode == 0

    def test_a_queued_absorption_leaves_no_hold_behind(self):
        s = self.seat()
        seat_id, old = s["seat_id"], s["current"]
        jtid, job = self.human_thread()                     # a record of its own the seat's next session made
        with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")):
            entry = threads.begin(seat_id, "advance", self.p,
                                  [{"kind": "retired", "session": old, "by": "", "reason": "replaced"}],
                                  fields={"current": ""}, guard=lambda t: t["current"] == old)
        self.assertIsNotNone(entry)
        joined = sminos.joined_fields("w", "seat", self.root, "", "", seat_id, "", "seat", session=job)
        self.assertTrue(threads.follow(seat_id, entry["id"], "advance", self.p,
                                       [{"kind": "joined", "session": job, **joined}],
                                       fields={"current": job}, absorbs=True))
        self.assertEqual(dict(sminos._WAKE_HOLDS), {})
        sminos.finish_thread(seat_id, project=self.p)
        sminos.finish_thread(seat_id, project=self.p)
        self.assertEqual(threads.get(seat_id)["current"], job, "the queued advance absorbed the job's record")
        self.assertIsNone(threads.get(jtid))
        self.assertEqual(dict(sminos._WAKE_HOLDS), {}, "no hold is left registered")
        self.assertTrue(self.free_elsewhere(jtid) and self.free_elsewhere(seat_id), "nor any flock")

    def test_a_queued_absorption_waits_for_a_wake_of_the_record_it_absorbs(self):
        s = self.seat()
        seat_id, old = s["seat_id"], s["current"]
        jtid, job = self.human_thread()
        with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")):
            entry = threads.begin(seat_id, "advance", self.p,
                                  [{"kind": "retired", "session": old, "by": "", "reason": "replaced"}],
                                  fields={"current": ""}, guard=lambda t: t["current"] == old)
        joined = sminos.joined_fields("w", "seat", self.root, "", "", seat_id, "", "seat", session=job)
        threads.follow(seat_id, entry["id"], "advance", self.p, [{"kind": "joined", "session": job, **joined}],
                       fields={"current": job}, absorbs=True)
        taken, release = threading.Event(), threading.Event()

        def launcher():
            hold, _ = sminos.wake_lock(jtid, holder=sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()))
            taken.set()
            release.wait(10)
            hold.release()
        t, _ = self.in_background(launcher)
        self.assertTrue(taken.wait(5))
        with mock.patch.object(sminos, "SWEEP_WAIT", 0.3):
            sminos.finish_thread(seat_id, project=self.p, lock_until=time.time() + 0.3)
        self.assertNotEqual(threads.get(seat_id)["current"], job, "not absorbed while a wake of it holds it")
        self.assertIsNotNone(threads.get(jtid))
        release.set()
        t.join(10)
        sminos.finish_thread(seat_id, project=self.p)
        sminos.finish_thread(seat_id, project=self.p)
        self.assertEqual(threads.get(seat_id)["current"], job, "absorbed once the wake let go")
        self.assertEqual(dict(sminos._WAKE_HOLDS), {})


# ------------------------------------------------------------ a retired seat's return


class Return(Transitions):
    def test_fill_resume_returns_a_retired_seat_settles_what_was_owed_before_and_pushes_its_task(self):
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        code, out = self.cli("retire", "w")
        self.assertEqual(code, 0, out)
        # An event addressed to it while it was retired, owed until the return settles it.
        project = sminos.seat_project(sminos.reload_seat(seat_id))
        older = sminos.record_message(project, sid, "w", "human", "human", "said while it was retired", "old00001",
                                      deliver=False)
        turns = int(sminos.reload_seat(seat_id)["turns"] or 0)
        before = len(self.inputs(sid))
        code, out = self.cli("fill", "w", "the new task", "--resume")
        self.assertEqual(code, 0, out)
        self.assertIn("filled %s/w" % s["group"], out)
        self.assertNotEqual(sminos.reload_seat(seat_id)["status"], "retired")
        self.assertNotIn("ended", threads.get(seat_id))
        frames = [i["message"]["content"] for i in self.inputs(sid)][before:]
        self.assertEqual(len(frames), 1, frames)
        self.assertIn("the new task", frames[0])
        self.assertNotIn("said while it was retired", frames[0], "settled by the return, not pushed")
        settled = sminos.delivered_load(project, sid).get(older["writer"], {}).get("settled") or 0
        self.assertGreaterEqual(settled, older["seq"], "the older event is settled")
        self.assertEqual(int(sminos.reload_seat(seat_id)["turns"]), turns + 1, "the woken push counted")
        self.assertEqual(self.resumes(sid), [[]])

    def test_a_return_whose_launch_lost_its_banner_with_its_process_up_returns_and_delivers(self):
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        self.cli("retire", "w")
        self.switch("no-banner", 30)
        with mock.patch.dict(os.environ, {"SMINOS_LAUNCH_TIMEOUT": "1.5"}):
            code, out = self.cli("fill", "w", "after a lost banner", "--resume")
        self.assertEqual(code, 0, out)
        self.assertNotEqual(sminos.reload_seat(seat_id)["status"], "retired", "returned through W8")
        self.assertNotIn("ended", threads.get(seat_id))
        self.assertIn("after a lost banner", self.inputs(sid)[-1]["message"]["content"], "and its task delivered")

    def test_a_task_its_stream_refuses_starts_nothing(self):
        """What refuses the task here, with nothing appended and no endpoint asked (the audience choice, D4), is
        checked before the return starts anything."""
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        self.cli("retire", "w")
        au = sminos.audience_module()
        with mock.patch.object(sminos, "streams_for", side_effect=au.Unreachable("w is outside its audience")):
            code, out = self.cli("fill", "w", "never sent", "--resume")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("w is outside its audience", out)
        self.assertEqual(self.resumes(sid), [], "nothing launched")
        self.assertEqual(sminos.reload_seat(seat_id)["status"], "retired")
        self.assertIn("ended", threads.get(seat_id))
        self.assertFalse([e for e in self.log() if e.get("text") == "never sent"])

    def test_a_seat_whose_project_cannot_be_read_is_refused_its_return_and_nothing_starts(self):
        """Its return is journaled in its project's log (join_seat at W8): with none read, no process starts."""
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        self.cli("retire", "w")
        launched = self.launches()
        with mock.patch.object(sminos, "seat_project", return_value=None):
            code, out = self.cli("fill", seat_id, "never sent", "--resume")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertIn("cannot return from here: its project cannot be read", out)
        self.assertEqual((self.resumes(sid), self.launches()), ([], launched), "nothing launched")
        self.assertEqual(sminos.reload_seat(seat_id)["status"], "retired")
        self.assertIn("ended", threads.get(seat_id))
        self.assertFalse([e for e in self.log() if e.get("text") == "never sent"])

    def test_a_stopped_seat_whose_project_cannot_be_read_is_refused_its_task_before_anything_starts(self):
        """No log to record its task in: a verb's message is a logged event, so nothing is woken and nothing
        pushed (T2's M4, the rule behind M2's last fix: what a verb must write is writable before the launch)."""
        s = self.seat()
        sid, seat_id = s["current"], s["seat_id"]
        launched = self.launches()
        with mock.patch.object(sminos, "seat_project", return_value=None):
            code, out = self.cli("fill", seat_id, "no log to hold it", "--resume")
        self.assertEqual(code, sminos.EXIT_UNKNOWN, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("nothing was started", out)
        self.assertEqual((self.resumes(sid), self.launches()), ([], launched), "nothing launched")
        self.assertFalse([i for i in self.inputs(sid) if "no log to hold it" in i["message"]["content"]])
        self.assertFalse([e for e in self.log() if e.get("text") == "no log to hold it"], "nothing recorded")

    def test_a_failed_launch_leaves_it_retired_and_records_nothing(self):
        s = self.seat()
        seat_id = s["seat_id"]
        self.cli("retire", "w")
        self.switch("fail-job")
        code, out = self.cli("fill", "w", "never sent", "--resume")
        self.assertNotEqual(code, 0, out)
        self.assertIn("was not woken: waking it failed; nothing was recorded", out)
        self.assertEqual(sminos.reload_seat(seat_id)["status"], "retired")
        self.assertIn("ended", threads.get(seat_id))
        self.assertFalse([e for e in self.log() if e.get("text") == "never sent"])


# ------------------------------------------------------------ a /clear


class Clear(Transitions):
    def test_its_release_takes_no_wake_lock(self):
        tid, sid = self.human_thread()
        alias = threads.get(tid)["alias"]
        taken, release = threading.Event(), threading.Event()

        def launcher():
            hold, _ = sminos.wake_lock(tid, holder=sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()))
            taken.set()
            release.wait(10)
            hold.release()
        t, _ = self.in_background(launcher)
        self.assertTrue(taken.wait(5))
        started = time.monotonic()
        events = sminos.release_alias(self.p, sid, alias)
        self.assertLess(time.monotonic() - started, sminos.SWEEP_WAIT, "not waited behind the launcher")
        self.assertEqual([e["kind"] for e in events], ["renamed"])
        self.assertEqual(threads.get(tid)["released"]["alias"], alias)
        release.set()
        t.join(10)


if __name__ == "__main__":
    unittest.main()
