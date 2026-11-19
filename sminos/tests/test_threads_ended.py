#!/usr/bin/env python3
"""A thread ends, and returns (T1's M4:
docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md, the milestone's
"What it proves"; Interfaces §5, §6 rows 9 to 12, §8).

- The three-day rule, with the period set short: the sweep's end, written
  only for the stop it was decided for; nothing else ends a thread by it.
- At an end, what was held is settled `recorded`, and nothing is pushed
  when the thread returns; what reaches the log after the end is settled too.
- A retire, by another session or by the session itself: recorded before
  anything is stopped, and holding against the process it saw.
- The return: reopened by its human, an ended thread is a member again
  under its thread id, alias, in-charge line and channels; a spawned one
  returns by a fill, fresh or `--resume`, or by its human reopening its
  session, and by nothing else.
- The journal of each end and of a return, the process killed after the
  record's write, after the event and after the settlement.
- An older copy's unstamped `retire`, read from the log alone.

The retired machine's half is in test_org_retired.py. Hermetic: HOME and
SMINOS_HOME are temporary, fresh for each test (test_threads.Machine);
sessions are `sleep` processes with engine records the test writes; the
harness's `claude agents` and `claude stop` are stood in for.
Run: python3 -B sminos/tests/test_threads_ended.py
"""
import contextlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import BASE, Killed, ms_ago, sminos, threads  # noqa: E402
from test_threads_stopped import Rig  # noqa: E402

PERIOD = 3600
ENV = {"SMINOS_THREAD_END_AFTER": str(PERIOD), "SMINOS_THREAD_END_EVERY": "0"}


def ago(seconds):
    """A record's timestamp (sminos.now()'s form) `seconds` ago."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))


class Ending(Rig):
    def setUp(self):
        super().setUp()
        for patcher in (mock.patch.dict(os.environ, ENV), mock.patch.object(sminos, "agents_json", return_value=[]),
                        mock.patch.object(sminos, "claude_stop", return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.daemon._ENDING[0] = 0.0

    def sweep(self):
        sminos.forget_caches()
        self.daemon.sweep_threads()
        sminos.forget_caches()

    def stopped_since(self, sid, seconds):
        """The thread's stop marked by the sweep (two passes), then dated
        `seconds` ago: (thread id, the mark)."""
        self.sweep()
        self.sweep()
        t = threads.thread_of(sid)
        self.assertTrue(t.get("stopped"), "the stop is marked")
        at = ago(seconds)
        self.assertTrue(threads.update(t["thread"], {"stopped": at, "swept": at}))
        return t["thread"], at

    def closed(self, **more):
        """A session its human opened, then closed: a stopped thread."""
        sid, proc = self.opened(**more)
        self.end(proc)
        self.reconcile()
        return sid

    def ended_by_rule(self, **more):
        sid = self.closed(**more)
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        self.sweep()
        return sid, tid

    def owed_any(self, sid):
        """What is owed to a session, member or not."""
        sminos.forget_caches()
        return [(e["writer"], e["seq"]) for e in sminos._owed(sminos.log_read(self.p, to_session=sid), sid,
                                                              sminos.delivered_load(self.p, sid))]

    def ended_with(self, sid):
        e = threads.in_effect(self.own(sid))
        return (e["kind"], e.get("reason"), e.get("by"), e.get("thread"))

    def seated(self, alias="w"):
        """A spawned thread: a seat whose session runs, with a transcript."""
        sid, proc = self.session(name=alias)
        code, out = self.cli("seat", "add", "g", alias, "--session", sid)
        self.assertEqual(code, 0, out)
        self.transcript(sid)
        seat_id = next(s["seat_id"] for s in sminos.seats() if s["alias"] == alias)
        return sid, proc, seat_id


# ------------------------------------------------------------ the rule


class Rule(Ending):
    def test_stopped_past_the_period_the_sweep_ends_it_out_of_list_and_stopped_and_in_all(self):
        sid, tid = self.ended_by_rule()
        self.assertEqual(self.ended_with(sid), ("retired", "ended", "", tid))
        t = threads.get(tid)
        self.assertEqual((t["ended"]["reason"], t["ended"]["by"], t["ended"]["pid"], t.get("pending")),
                         ("ended", "", None, None))
        self.assertEqual((self.human_files(), self.human_files(aside=True)), ([], [tid + ".json"]))
        for argv in (("list",), ("list", "--stopped")):
            code, out = self.cli(*argv)
            self.assertEqual(code, 0, out)
            self.assertNotIn("alpha [", out, argv)
            self.assertNotIn("hidden", out, "an ended thread is not counted among the hidden")
        code, out = self.cli("list", "--all")
        self.assertIn("alpha [%s]" % sid[:8], out)
        row = next(line for line in out.splitlines() if "alpha [" in line)
        self.assertIn("retired", row)
        self.assertIn("ended after it stopped", row)
        self.assertIn("in charge: owns alpha", row)
        code, out = self.say("@alpha are you there")
        self.assertEqual(code, 4, out)
        self.assertIn("alpha has ended", out)
        self.assertIn("returns when its human reopens its session", out)
        self.assertEqual(self.owed_any(sid), [], "nothing was recorded for it")

    def test_a_moment_before_the_period_it_is_not_ended(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, PERIOD - 60)
        self.sweep()
        self.assertTrue(self.is_member(sid))
        self.assertFalse(threads.record_ended(threads.get(tid)))

    def test_its_clock_starts_again_after_a_process_held_its_session_in_between(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        _, proc = self.live(sid=sid)
        self.sweep()
        self.assertIsNone(threads.get(tid).get("stopped"), "the mark goes while a process holds it")
        self.end(proc)
        self.sweep()
        self.sweep()
        self.assertTrue(threads.get(tid).get("stopped"), "stopped again, from now")
        self.sweep()
        self.assertTrue(self.is_member(sid))
        self.assertFalse(threads.record_ended(threads.get(tid)))

    def test_no_reading_verb_hook_or_project_tick_ends_it(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        other, _ = self.session()
        self.reconcile()
        self.cli("list", "--all")
        self.hook(other)
        self.tick()
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertEqual([e for e in self.own(sid) if e["kind"] == "retired"], [])
        self.sweep()
        self.assertTrue(threads.record_ended(threads.get(tid)), "the sweep does")

    def test_the_spacing_of_the_ending_pass(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        with mock.patch.dict(os.environ, {"SMINOS_THREAD_END_EVERY": "3600"}):
            self.daemon._ENDING[0] = time.time() - 60
            self.sweep()
            self.assertFalse(threads.record_ended(threads.get(tid)), "within the spacing: no ending pass")
            self.daemon._ENDING[0] = time.time() - 3601
            self.sweep()
            self.assertTrue(threads.record_ended(threads.get(tid)))

    def test_a_process_that_takes_the_session_after_the_pass_decided_is_not_ended(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        real = self.daemon.resume_lock_out

        @contextlib.contextmanager
        def racing(thread_id):
            self.live(sid=sid)   # reopened between the decision and the end's write
            with real(thread_id) as out:
                yield out
        with mock.patch.object(self.daemon, "resume_lock_out", side_effect=racing):
            self.sweep()
        self.assertTrue(self.is_member(sid))
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertEqual([e for e in self.own(sid) if e["kind"] == "retired"], [])

    def test_a_process_the_passs_cached_records_miss_but_fresh_ones_show_is_not_ended(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        self.live(sid=sid)
        real, calls = sminos.peer_records, []

        def stale():
            calls.append(1)
            return [] if len(calls) == 1 else real()   # the pass's own read misses it; a fresh read does not
        with mock.patch.object(sminos, "peer_records", side_effect=stale):
            self.sweep()
        self.assertGreater(len(calls), 1, "the end asked afresh")
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertEqual([e for e in self.own(sid) if e["kind"] == "retired"], [])

    def test_a_spawned_thread_stopped_past_the_period_ends_and_its_seat_reads_retired_to_every_reader(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        self.stopped_since(sid, 2 * PERIOD)
        self.sweep()
        self.assertEqual(self.ended_with(sid), ("retired", "ended", "", seat_id))
        with open(sminos.meta_path(seat_id)) as f:
            raw = json.load(f)
        self.assertEqual((raw["status"], raw["ended"]["reason"], raw.get("pending")), ("retired", "ended", None),
                         "the form a sminos from before threads reads as a retired seat (D7)")
        self.assertEqual(sminos.state(sminos.load_seat(sminos.meta_path(seat_id))), "retired")


# ------------------------------------------------------------ what was held


class Settled(Ending):
    def test_what_was_held_is_settled_at_its_end_and_not_pushed_when_it_returns(self):
        sid = self.closed()
        tid = threads.stamp(sid)
        threads.set_channels(tid, ["c-one"])
        for n in (1, 2):
            code, out = self.say("@alpha number %d" % n)
            self.assertEqual(code, 0, out)
        self.assertEqual(len(self.owed_any(sid)), 2, "held")
        self.stopped_since(sid, 2 * PERIOD)
        self.sweep()
        self.assertEqual(self.owed_any(sid), [], "settled at its end")
        code, out = self.cli("daemon", "owed")
        self.assertEqual(code, 0, out)
        self.assertNotIn("alpha", out)
        self.live(sid=sid, name="alpha", inbox=True)
        self.reconcile()
        self.tick()
        self.assertEqual(self.inbox(sid), [], "nothing is delivered again on a return")
        m = self.member(sid)
        self.assertEqual((m.alias, m.charge, m.thread), ("alpha", "owns alpha", tid))
        t = threads.get(tid)
        self.assertEqual(self.human_files(), [tid + ".json"], "back in the thread store")
        self.assertEqual((t["channels"], t.get("ended"), t.get("stopped"), t.get("swept")), (["c-one"], None, None,
                                                                                             None))
        self.assertEqual([e["kind"] for e in self.own(sid) if e["kind"] in ("joined", "retired")],
                         ["joined", "retired", "joined"])

    def test_what_reaches_the_log_for_it_after_its_end_is_settled_too(self):
        sid, _ = self.ended_by_rule()
        other, _ = self.session(name="older")
        self.reconcile()
        # An older sender's tag, written as it writes one: an addressed message in its own file.
        sminos.log_append(self.p, sminos.writer_id(other), "message", session=other, text="@alpha late",
                          to=[{"session": sid, "alias": "alpha"}])
        sminos.forget_caches()
        self.assertEqual(len(self.owed_any(sid)), 1)
        self.tick()
        self.assertEqual(self.owed_any(sid), [])


# ------------------------------------------------------------ a retire, and the return


class Retire(Ending):
    def test_a_self_retire_holds_against_its_own_process_and_a_new_one_returns_it(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("retire", sid)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))
        self.assertEqual(threads.get(tid)["ended"]["pid"], proc.pid)
        self.hook(sid, env={"CLAUDE_CODE_SESSION_ID": sid, "CLAUDE_PID": str(proc.pid)})
        self.reconcile()
        self.assertFalse(self.is_member(sid), "its own process's hooks and the reconciliation do not join it")
        self.end(proc)
        self.live(sid=sid, name="alpha")
        self.reconcile()
        self.assertTrue(self.is_member(sid), "a new process returns it")
        self.assertEqual(threads.in_effect(self.own(sid))["thread"], tid)
        self.assertEqual(self.member(sid).alias, "alpha")

    def test_a_spawned_self_retire_is_recorded_even_when_the_stop_ends_its_caller(self):
        sid, proc, seat_id = self.seated()
        with mock.patch.object(sminos, "stop_session", side_effect=Killed), \
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}), self.assertRaises(Killed):
            self.cli("retire", "g/w")
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["status"], seat["ended"]["reason"], seat["ended"]["pid"], seat.get("pending")),
                         ("retired", "retire", proc.pid, None))
        self.assertEqual(self.ended_with(sid)[:2] + (self.ended_with(sid)[3],), ("retired", "retire", seat_id))

    def test_a_retire_of_a_stopped_thread_saw_no_process_and_one_started_before_it_returns_it(self):
        sid = self.closed()
        tid = threads.stamp(sid)
        code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 0, out)
        self.assertIsNone(threads.get(tid)["ended"]["pid"])
        self.session(sid=sid, started=ms_ago(3600))
        self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.assertEqual(threads.in_effect(self.own(sid))["thread"], tid)

    def test_the_rule_returns_to_a_process_that_started_a_moment_before_its_end(self):
        sid, tid = self.ended_by_rule()
        self.session(sid=sid, started=ms_ago(30))
        self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.assertEqual(threads.in_effect(self.own(sid))["thread"], tid)

    def test_retire_purge_ends_a_thread_its_human_opened_and_deletes_its_record(self):
        sid, _ = self.opened()
        tid = threads.stamp(sid)
        code, out = self.cli("retire", "alpha", "--purge")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ended_with(sid), ("retired", "retire", "", tid))
        self.assertEqual((self.human_files(), self.human_files(aside=True)), ([], []))
        self.assertIsNone(threads.get(tid))

    def test_remove_ends_a_thread_its_human_opened_and_deletes_its_record(self):
        sid = self.closed()
        tid = threads.stamp(sid)
        code, out = self.cli("remove", "alpha")
        self.assertEqual(code, 0, out)
        self.assertIn("removed alpha", out)
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))
        self.assertIsNone(threads.get(tid))


class Spawned(Ending):
    """An ended seat returns by a fill, fresh or `--resume`, and by its human
    reopening its session; `send`, `resume` and a tagged `say` are refused,
    naming the fill."""

    def setUp(self):
        super().setUp()
        self.sid, proc, self.seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.launched = []

    def seat(self):
        return sminos.load_seat(sminos.meta_path(self.seat_id))

    def engine(self, sid):
        """The harness's two steps a fill takes, stood in for: the engine's
        start (a process for `sid`) and the launcher's wait for its id."""
        def start(args, cwd, settings):
            self.launched.append(args)
            self.session(sid=sid, kind="bg", started=ms_ago(0))
            return sid[:8], "banner"

        return mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
            mock.patch.object(sminos, "poll_uuid", return_value=(sid, "idle", self.root))

    def test_send_resume_and_a_tagged_say_do_not_return_it(self):
        start, poll = self.engine(self.sid)
        with start, poll:
            for argv, said in ((("send", "g/w", "hello"), "fill"), (("resume", "g/w", "go on"), "a fill returns it")):
                with self.subTest(argv=argv):
                    code, out = self.cli(*argv)
                    self.assertEqual(code, 4, out)
                    self.assertIn(said, out)
            code, out = self.say("@w are you there")
        self.assertEqual(code, 4, out)
        self.assertIn("a fill returns it", out)
        self.assertEqual(self.launched, [], "no claude call")
        self.assertEqual(self.seat()["status"], "retired")
        self.assertFalse(self.is_member(self.sid))

    def test_fill_resume_returns_it(self):
        start, poll = self.engine(self.sid)
        with start, poll:
            code, out = self.cli("fill", "g/w", "carry on", "--resume")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.launched), 1)
        e = threads.in_effect(self.own(self.sid))
        self.assertEqual((e["kind"], e["thread"]), ("joined", self.seat_id))
        self.assertNotEqual(self.seat()["status"], "retired")
        self.assertIsNone(self.seat().get("ended"))

    def test_a_fresh_fill_returns_it(self):
        new = str(uuidlib.uuid4())
        start, poll = self.engine(new)
        with start, poll:
            code, out = self.cli("fill", "g/w", "a fresh task")
        self.assertEqual(code, 0, out)
        seat = self.seat()
        self.assertEqual((seat["current"], seat.get("ended")), (new, None))
        self.assertNotEqual(seat["status"], "retired")
        self.assertEqual(threads.in_effect(self.own(new))["thread"], self.seat_id)

    def test_its_human_reopening_its_session_returns_it(self):
        self.live(sid=self.sid, name="w")
        self.reconcile()
        e = threads.in_effect(self.own(self.sid))
        self.assertEqual((e["kind"], e["thread"]), ("joined", self.seat_id))
        seat = self.seat()
        self.assertEqual((seat.get("ended"), seat.get("pending")), (None, None))
        self.assertNotEqual(seat["status"], "retired")

    def test_the_process_its_retire_saw_does_not_return_it(self):
        sid, proc, seat_id = self.seated(alias="v")
        code, out = self.cli("retire", "g/v")
        self.assertEqual(code, 0, out)
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["ended"]["pid"], proc.pid)
        self.reconcile()
        self.assertFalse(self.is_member(sid), "its process runs on (the stop did not take): it stays ended")
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["status"], "retired")


# ------------------------------------------------------------ the journal


class Journal(Ending):
    """Each end of M4 and a return, the process killed after the record's
    write, after its event, and after its settlement: each finished by the
    next reconciliation and by none after it, no event twice, a record
    neither set aside nor deleted while its entry is open, and the same
    membership read from a second registry that holds only the log."""

    POINTS = ("record", "event", "settled")

    def kill_at(self, point):
        if point == "record":
            real = threads.begin

            def begin(*a, **k):
                if real(*a, **k) is not None:
                    raise Killed()
                return None
            return mock.patch.object(threads, "begin", side_effect=begin)
        if point == "event":
            return mock.patch.object(sminos, "settle_ended", side_effect=Killed)
        real_change = threads._change

        def change(tid, mutate, *a, **k):
            if mutate.__name__ == "clear":
                raise Killed()
            return real_change(tid, mutate, *a, **k)
        return mock.patch.object(threads, "_change", side_effect=change)

    def held_for(self, sid):
        code, out = self.say("@alpha before its end")
        self.assertEqual(code, 0, out)

    def setups(self):
        """op → (prepare() → (sid, thread id), act(), what is in effect after, the record's fate)."""
        def rule():
            sid = self.closed()
            self.held_for(sid)
            tid, _ = self.stopped_since(sid, 2 * PERIOD)
            return sid, tid, self.sweep

        def retire(purge):
            def prepare():
                sid = self.closed()
                self.held_for(sid)
                return sid, threads.stamp(sid), lambda: self.cli("retire", "alpha", *(["--purge"] if purge else []))
            return prepare

        def remove():
            sid, proc, seat_id = self.seated()
            self.end(proc)
            self.reconcile()
            return sid, seat_id, lambda: self.cli("remove", "g/w")

        return {"rule": (rule, ("retired", "ended"), "aside"), "retire": (retire(False), ("retired", "retire"), "aside"),
                "purge": (retire(True), ("retired", "retire"), "gone"), "remove": (remove, ("retired", "retire"), "gone")}

    def assert_once_and_settled(self, sid, effect):
        ops = [(e["kind"], e["op"]) for e in self.own(sid) if e.get("op")]
        self.assertEqual(len(ops), len(set(ops)), "no event appended twice")
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"],) + ((e["reason"],) if effect[0] == "retired" else ()), effect)
        before = list(self.own(sid))
        self.reconcile()
        self.assertEqual(self.own(sid), before, "a second reconciliation does nothing")
        self.assert_second_registry_agrees(sid)

    def assert_second_registry_agrees(self, sid):
        first = threads.member(self.own(sid))
        copy_home = tempfile.mkdtemp(dir=BASE)
        shutil.copytree(os.path.join(self.p.home, "log"), os.path.join(copy_home, "log"))
        events = []
        for name in os.listdir(os.path.join(copy_home, "log")):
            with open(os.path.join(copy_home, "log", name)) as f:
                events += [json.loads(line) for line in f if line.strip()]
        own = sorted((e for e in events if e.get("session") == sid), key=lambda e: (e["ts"], e["seq"]))
        self.assertEqual(threads.member(own), first)

    def record_present(self, tid):
        return os.path.exists(sminos.meta_path(tid)) or os.path.exists(os.path.join(threads.store_dir(),
                                                                                      tid + ".json"))

    def test_each_end_cut_at_each_step_is_finished_by_the_next_reconciliation(self):
        for op, (prepare, effect, fate) in self.setups().items():
            for point in self.POINTS:
                with self.subTest(op=op, point=point):
                    self.fresh()
                    sid, tid, act = prepare()
                    with mock.patch.object(sminos, "stop_session"), self.kill_at(point), self.assertRaises(Killed):
                        act()
                    t = threads.get(tid)
                    self.assertEqual(((t or {}).get("pending") or {}).get("op"), "end", "its entry is open")
                    self.assertTrue(self.record_present(tid), "neither set aside nor deleted while it is open")
                    if point != "settled" and op != "remove":
                        self.assertTrue(self.owed_any(sid), "what was held is settled after the event")
                    self.reconcile()
                    self.assertEqual(self.owed_any(sid), [])
                    if fate == "aside":
                        self.assertEqual(self.human_files(aside=True), [tid + ".json"])
                        self.assertIsNone(threads.get(tid).get("pending"))
                    else:
                        self.assertFalse(self.record_present(tid), "purged once its end is in the log and settled")
                        self.assertIsNone(threads.get(tid))
                    self.assert_once_and_settled(sid, effect)

    def test_a_return_cut_at_each_step_is_finished_by_the_next_reconciliation(self):
        for point in ("record", "settled"):
            with self.subTest(point=point):
                self.fresh()
                sid, tid = self.ended_by_rule()
                self.live(sid=sid, name="alpha")
                with self.kill_at(point), self.assertRaises(Killed):
                    self.reconcile()
                self.assertEqual(threads.get(tid)["pending"]["op"], "return")
                self.reconcile()
                self.assertIsNone(threads.get(tid).get("pending"))
                self.assertEqual(self.human_files(), [tid + ".json"])
                self.assert_once_and_settled(sid, ("joined",))


# ------------------------------------------------------------ an older copy's retire


class OlderCopy(Ending):
    def test_an_older_copys_unstamped_retire_has_ended_from_the_log_alone_and_a_tag_naming_it_is_refused(self):
        sid, proc = self.opened()
        self.write_own(sid, [{"kind": "retired", "by": "old", "reason": "retire", "pid": proc.pid}])
        info = sminos._projection(sminos.log_read(self.p))
        m = sminos._member(sid, info[sid], None, None, False, info=info)
        self.assertTrue(sminos.has_ended(m), "read from the log, with no record")
        self.assertEqual((m.end, m.end_by, sminos.wake_of(m)), ("retire", "old", "ended"))
        code, out = self.cli("list", "--all")
        row = next((line for line in out.splitlines() if "alpha [" in line), "")
        self.assertIn("retired", row, out)
        self.assertIn("retired by old", row)
        code, out = self.say("@alpha still there?")
        self.assertEqual(code, 4, out)
        self.assertIn("alpha was retired by old", out)


if __name__ == "__main__":
    unittest.main()
