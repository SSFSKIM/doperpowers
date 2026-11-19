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
from test_threads_stopped import Rig, wait_for  # noqa: E402

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
        self.launched = []

    def engine(self, sid, short=None):
        """The harness's two steps a fill takes, stood in for: the engine's
        start (a process for `sid`) and the launcher's wait for its id; with
        `short` "", a start that launched nothing."""
        def start(args, cwd, settings):
            self.launched.append(args)
            if short == "":
                return "", "no background id"
            self.session(sid=sid, kind="bg", started=ms_ago(0))
            return sid[:8], "banner"

        return mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
            mock.patch.object(sminos, "poll_uuid", return_value=(sid, "idle", self.root))

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
        sminos.agents_json.return_value = [{"id": "job00001", "sessionId": sid, "state": "working",
                                            "status": "busy"}]   # the harness's turn of it, which the end sees
        with mock.patch.object(sminos, "claude_stop", side_effect=Killed), \
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

    def seat(self):
        return sminos.load_seat(sminos.meta_path(self.seat_id))

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


# ------------------------------------------------------------ an end stands until a return (review 1)


class EndStands(Ending):
    """What may return an ended thread, and only it: a fill that launched,
    or a process its end did not see, chosen for that very end; each read
    again where it acts."""

    def seat(self, seat_id):
        return sminos.load_seat(sminos.meta_path(seat_id))

    def retired_seat(self, alias="w"):
        sid, proc, seat_id = self.seated(alias=alias)
        self.end(proc)
        self.reconcile()
        code, out = self.cli("retire", "g/" + alias)
        self.assertEqual(code, 0, out)
        return sid, seat_id

    def test_a_resume_whose_seat_ended_while_it_waited_for_the_resume_lock_is_refused(self):
        sid, proc, seat_id = self.seated(alias="v")
        self.end(proc)
        self.reconcile()
        real = sminos.resume_lock_taken

        def ended_meanwhile(lf, label):
            real(lf, label)   # the sweep's end, written while it held this lock out, is in the record now
            at = sminos.now()
            sminos.meta_set(seat_id, {"status": "retired", "updated": at,
                                      "ended": {"at": at, "reason": "ended", "by": "", "pid": None}})
        before = self.own(sid)
        start, poll = self.engine(sid)
        with start, poll, mock.patch.object(sminos, "resume_lock_taken", side_effect=ended_meanwhile):
            code, out = self.cli("resume", "g/v", "go on")
        self.assertEqual(code, 4, out)
        self.assertIn("a fill returns it", out)
        self.assertEqual(self.launched, [], "nothing launched")
        self.assertEqual((self.seat(seat_id)["status"], self.seat(seat_id)["ended"]["reason"]), ("retired", "ended"))
        self.assertEqual(self.own(sid), before, "nothing joined it again")

    def test_a_fill_resume_that_launched_nothing_leaves_the_seat_retired(self):
        sid, seat_id = self.retired_seat()
        start, poll = self.engine(sid, short="")
        with start, poll:
            code, out = self.cli("fill", "g/w", "carry on", "--resume")
        self.assertEqual(code, 1, out)
        seat = self.seat(seat_id)
        self.assertEqual((seat["status"], seat["ended"]["reason"]), ("retired", "retire"))
        self.assertFalse(self.is_member(sid))

    def test_seat_add_of_an_ended_seats_own_occupant_does_not_return_it(self):
        sid, seat_id = self.retired_seat()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.assertIn("stays retired", out)
        seat = self.seat(seat_id)
        self.assertEqual((seat["status"], seat["ended"]["reason"]), ("retired", "retire"))
        self.assertFalse(self.is_member(sid))
        self.reconcile()
        self.assertFalse(self.is_member(sid), "nor does the next reconciliation")

    def test_a_return_chosen_for_an_older_end_does_not_undo_a_newer_self_retire(self):
        sid, tid = self.ended_by_rule()
        older = threads.get(tid)
        _, proc = self.live(sid=sid, name="alpha")
        self.reconcile()
        self.assertTrue(self.is_member(sid), "returned")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("retire", sid)
        self.assertEqual(code, 0, out)
        newer = threads.get(tid)["ended"]
        self.assertEqual((newer["reason"], newer["pid"]), ("retire", proc.pid))
        real = threads.choose
        # A reconciliation that read the record before the self-retire: its choice is for the older end.
        with mock.patch.object(threads, "choose", side_effect=lambda *a, **k: (older, "return")
                               if a[0] == sid else real(*a, **k)):
            self.reconcile()
            self.hook(sid, env={"CLAUDE_CODE_SESSION_ID": sid, "CLAUDE_PID": str(proc.pid)})
        self.assertEqual(threads.get(tid)["ended"], newer, "the newer end stands")
        self.assertFalse(self.is_member(sid))

    def test_after_its_end_is_at_the_ends_own_precision(self):
        at = sminos.now()
        epoch = sminos._ts_epoch(at)
        record = {"thread": "t", "opened": "human", "ended": {"at": at, "reason": "retire", "by": "", "pid": 4242}}
        self.assertFalse(threads.returns(record, {"pid": 4242, "startedAt": (epoch + 0.5) * 1000}),
                         "within the second the end names: not after it")
        self.assertTrue(threads.returns(record, {"pid": 4242, "startedAt": (epoch + 1.5) * 1000}))

    def test_a_reopening_the_sweep_never_saw_starts_the_clock_again(self):
        sid = self.closed()
        tid, _ = self.stopped_since(sid, 2 * PERIOD)
        _, proc = self.live(sid=sid)
        self.hook(sid, env={"CLAUDE_CODE_SESSION_ID": sid, "CLAUDE_PID": str(proc.pid)})
        self.assertIsNone(threads.get(tid).get("stopped"), "its hook lifted the mark")
        self.end(proc)   # closed again before any sweep saw it open
        self.sweep()
        self.assertFalse(threads.record_ended(threads.get(tid)), "not ended on the mark from before")
        self.assertTrue(self.is_member(sid))

    def test_a_fresh_fill_drops_the_stop_mark_of_the_session_it_replaces(self):
        _, seat_id = self.retired_seat()
        self.assertTrue(threads.update(seat_id, {"stopped": ago(2 * PERIOD), "swept": ago(2 * PERIOD)}))
        new = str(uuidlib.uuid4())
        start, poll = self.engine(new)
        with start, poll:
            code, out = self.cli("fill", "g/w", "a fresh task")
        self.assertEqual(code, 0, out)
        seat = self.seat(seat_id)
        self.assertEqual((seat["current"], seat.get("ended"), seat.get("stopped"), seat.get("swept")),
                         (new, None, None, None))

    def older_copys_retired_seat(self):
        """A seat an older CLI retired: its `status` and `updated`, and its unstamped `retired`."""
        sid, proc, seat_id = self.seated(alias="v")
        self.end(proc)
        self.reconcile()
        sminos.meta_set(seat_id, {"status": "retired", "updated": ago(600)})
        self.write_own(sid, [{"kind": "retired", "by": "old", "reason": "retire"}])
        return sid, seat_id

    def test_a_seat_an_older_copy_retired_returns_to_a_process_started_after_its_retire(self):
        sid, seat_id = self.older_copys_retired_seat()
        self.live(sid=sid, name="v", started=ms_ago(0))
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e.get("thread")), ("joined", seat_id))
        self.assertNotEqual(self.seat(seat_id)["status"], "retired")

    def test_a_retire_of_a_seat_an_older_copy_retired_writes_its_end(self):
        sid, seat_id = self.older_copys_retired_seat()
        code, out = self.cli("retire", "g/v")
        self.assertEqual(code, 0, out)
        seat = self.seat(seat_id)
        self.assertEqual((seat["status"], seat["ended"]["reason"], seat.get("pending")), ("retired", "retire", None))

    def test_a_seat_an_older_copy_retired_does_not_return_to_a_process_started_before_its_retire(self):
        sid, seat_id = self.older_copys_retired_seat()
        self.live(sid=sid, name="v", started=ms_ago(1200))
        self.reconcile()
        self.assertFalse(self.is_member(sid))
        self.assertEqual(self.seat(seat_id)["status"], "retired")


class RetireWrites(Ending):
    """A retire ends the canonical record, through its journal only, and
    stops nothing until its retirement is in the log."""

    def rival(self, sid):
        """Another retire that wins the claim: it ends the record first, just before this one's begins."""
        real, raced = threads.begin, []

        def begin(tid, op, project, events, **k):
            if op == "end" and not raced:
                raced.append(tid)
                real(tid, "end", project, [{"kind": "retired", "session": sid, "by": "rival", "reason": "retire"}],
                     fields={"ended": {"at": sminos.now(), "reason": "retire", "by": "rival", "pid": None}},
                     settle=sid, last="aside")
                sminos.finish_thread(tid, project=project)
            return real(tid, op, project, events, **k)
        return mock.patch.object(threads, "begin", side_effect=begin)

    def retirements(self, sid):
        return [(e.get("by"), bool(e.get("op"))) for e in self.own(sid) if e["kind"] == "retired"]

    def test_a_purge_that_lost_the_claim_purges_that_end_and_appends_no_second_retirement(self):
        sid, _ = self.opened()
        tid = threads.stamp(sid)
        with self.rival(sid):
            code, out = self.cli("retire", "alpha", "--purge")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.retirements(sid), [("rival", True)])
        self.assertIsNone(threads.get(tid), "the record it reported deleted is")
        self.assertEqual((self.human_files(), self.human_files(aside=True)), ([], []))

    def test_a_retire_that_lost_the_claim_says_so_and_appends_nothing(self):
        sid, _ = self.opened()
        tid = threads.stamp(sid)
        with self.rival(sid):
            code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 4, out)
        self.assertIn("retired already", out)
        self.assertEqual(self.retirements(sid), [("rival", True)])
        self.assertEqual(threads.get(tid)["ended"]["by"], "rival")

    def test_a_seat_an_older_copy_gave_a_human_opened_thread_ends_by_that_threads_record(self):
        sid, _ = self.opened()
        tid = threads.stamp(sid)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})   # the older CLI's seat, no thread keys
        self.reconcile()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        t = threads.get(tid)
        self.assertEqual((t["opened"], t["ended"]["reason"]), ("human", "retire"))
        self.assertEqual(self.human_files(aside=True), [tid + ".json"])
        self.assertEqual([(e.get("thread"), bool(e.get("op"))) for e in self.own(sid) if e["kind"] == "retired"],
                         [(tid, True)])
        with open(sminos.meta_path(seat_id)) as f:
            raw = json.load(f)
        self.assertEqual((raw["status"], raw.get("ended"), raw.get("pending")), ("retired", None, None))

    def failing_retirement(self):
        real = sminos.lifecycle

        def append(project, session, kind, *a, **k):
            if kind == "retired":
                if k.get("required", True):
                    raise sminos.LogWriteFailed("the log refused it")
                return []
            return real(project, session, kind, *a, **k)
        return mock.patch.object(sminos, "lifecycle", side_effect=append)

    def test_a_self_retire_whose_event_was_not_appended_stops_nothing(self):
        sid, _, seat_id = self.seated()
        with self.failing_retirement(), mock.patch.object(sminos, "stop_session") as stop, \
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 1, out)
        stop.assert_not_called()
        self.assertTrue(self.is_member(sid))
        self.reconcile()   # the next reading verb finishes the entry
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))


class SettledByItsEnd(Ending):
    """What reaches the log for an ended thread is settled while that end
    stands, and only then."""

    def older_sender(self, sid, text):
        if not hasattr(self, "sender"):
            self.sender, _ = self.session(name="older")
            self.reconcile()
        sminos.log_append(self.p, sminos.writer_id(self.sender), "message", session=self.sender, text=text,
                          to=[{"session": sid, "alias": "alpha"}])
        sminos.forget_caches()

    def test_what_reached_it_while_it_was_ended_is_settled_by_its_return_and_what_follows_is_delivered(self):
        sid, _ = self.ended_by_rule()
        self.older_sender(sid, "@alpha meanwhile")
        self.assertEqual(len(self.owed_any(sid)), 1)
        self.live(sid=sid, name="alpha", inbox=True)
        self.reconcile()
        self.assertTrue(self.is_member(sid), "returned")
        self.assertEqual(self.owed_any(sid), [], "settled by the return, before its joined")
        self.tick()
        self.assertEqual(self.inbox(sid), [], "nothing of its ended interval is pushed")
        code, out = self.say("@alpha after")
        self.assertEqual(code, 0, out)
        self.tick()
        self.assertTrue(wait_for(lambda: any("after" in x for x in self.inbox(sid))), self.inbox(sid))

    def test_a_late_pass_read_before_the_return_settles_nothing_after_it(self):
        sid, _ = self.ended_by_rule()
        self.older_sender(sid, "@alpha meanwhile")
        stale = sminos.view_of(self.p)
        end = stale.info[sid]["latest"]
        self.live(sid=sid, name="alpha")
        self.reconcile()
        self.older_sender(sid, "@alpha after")
        outcomes = sminos.sibling_module("sminos_outcomes")
        outcomes.settle_ended_owed(self.p, stale)
        self.assertEqual(len(self.owed_any(sid)), 1, "what came after the return is the returned session's")
        self.assertFalse(outcomes.settle_ended(self.p, sid, end=end), "that end no longer stands")
        self.assertEqual(len(self.owed_any(sid)), 1)

    def test_what_reaches_it_after_an_older_copys_retire_is_settled(self):
        sid, proc = self.opened()
        self.end(proc)
        self.write_own(sid, [{"kind": "retired", "by": "old", "reason": "retire"}])
        self.reconcile()
        self.older_sender(sid, "@alpha late")
        self.assertEqual(len(self.owed_any(sid)), 1)
        self.tick()
        self.assertEqual(self.owed_any(sid), [])


class Refusals(Ending):
    def test_a_bare_id_naming_an_ended_thread_of_another_project_is_refused_saying_so(self):
        there = self.repo("elsewhere")
        q = self.project_of(there)
        sid, proc = self.session(root=there, name="beta")
        self.peer_set(proc, nameSource="user")
        self.reconcile(q)
        self.assertTrue(self.is_member(sid, q))
        code, out = self.cli("retire", sid, cwd=there)
        self.assertEqual(code, 0, out)
        for argv in (("say", "@%s are you there" % sid[:8]), ("send", sid[:8], "are you there")):
            with self.subTest(argv=argv):
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("beta was retired", out)


# ------------------------------------------------------------ an end's boundaries (review 2)


class Boundaries(Ending):
    """The settlement's boundary with a return, the record its human opened
    as the one authority over a seat an older copy gave it, the stop of the
    process the end saw alone, and a seat's edit that keeps its end."""

    def older_sender(self, sid, text):
        if not hasattr(self, "sender"):
            self.sender, _ = self.session(name="older")
            self.reconcile()
        sminos.log_append(self.p, sminos.writer_id(self.sender), "message", session=self.sender, text=text,
                          to=[{"session": sid, "alias": "alpha"}])
        sminos.forget_caches()

    def older_seat(self, sid, alias="w"):
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": alias, "group": "g", "cwd": self.root,
                                  "status": "idle"})   # the older CLI's seat, no thread keys
        self.reconcile()
        return seat_id

    def test_an_event_past_the_returns_until_does_not_strand_it(self):
        sid, tid = self.ended_by_rule()
        self.sender, _ = self.session(name="older")
        self.reconcile()
        self.live(sid=sid, name="alpha")
        real = threads.begin

        def begin(*a, **k):
            entry = real(*a, **k)
            if entry is not None and entry["op"] == "return":
                time.sleep(0.005)
                self.older_sender(sid, "@alpha just after")   # past `until`, before the settlement runs
            return entry
        with mock.patch.object(threads, "begin", side_effect=begin):
            self.reconcile()
        self.assertIsNone(threads.get(tid).get("pending"), "the return finished")
        self.assertTrue(self.is_member(sid))
        self.assertEqual(len(self.owed_any(sid)), 1, "what came past `until` is the returned session's")

    def test_a_return_begun_just_after_the_late_passs_check_keeps_what_follows_it(self):
        sid, tid = self.ended_by_rule()
        self.older_sender(sid, "@alpha meanwhile")
        view = sminos.view_of(self.p)
        self.live(sid=sid, name="alpha")
        real, calls = sminos.delivered_load, []

        def load(project, session):
            calls.append(session)
            if session == sid and len(calls) == 2:   # inside the late pass's settlement, under its lock
                t = threads.get(tid)
                self.assertIsNotNone(threads.begin(tid, "return", self.p, [{**self.old_joined(sid, alias="alpha"),
                                                                            "session": sid}],
                                                   **sminos.return_change(t)))
                time.sleep(0.005)
                self.older_sender(sid, "@alpha after its return began")
            return real(project, session)
        with mock.patch.object(sminos, "delivered_load", side_effect=load):
            sminos.sibling_module("sminos_outcomes").settle_ended_owed(self.p, view)
        self.assertEqual(len(calls), 2, "the late pass reached its settlement")
        self.reconcile()   # the return finished: its settlement takes what reached the log before its `until`
        self.assertIsNone(threads.get(tid).get("pending"))
        self.assertTrue(self.is_member(sid))
        self.assertEqual(len(self.owed_any(sid)), 1, "what came after the return began is the returned session's")

    def test_a_retired_human_opened_thread_reopened_is_reached_through_the_seat_an_older_copy_gave_it(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        seat_id = self.older_seat(sid)
        with mock.patch.object(sminos, "stop_session"):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["status"], "retired", "it followed the record")
        self.end(proc)
        self.live(sid=sid, name="alpha")
        self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.assertFalse(threads.record_ended(threads.get(tid)))
        self.assertNotEqual(sminos.load_seat(sminos.meta_path(seat_id))["status"], "retired",
                            "the return brought the seat back with it")
        code, out = self.say("@w are you there")
        self.assertEqual(code, 0, out)

    def test_a_purge_cut_before_its_last_step_never_rejoins_through_the_older_copys_seat(self):
        sid, _ = self.opened()
        tid = threads.stamp(sid)
        seat_id = self.older_seat(sid)
        real_change = threads._change

        def change(t, mutate, *a, **k):
            if mutate.__name__ == "clear":
                raise Killed()
            return real_change(t, mutate, *a, **k)
        with mock.patch.object(sminos, "stop_session"), mock.patch.object(threads, "_change", side_effect=change), \
                self.assertRaises(Killed):
            self.cli("retire", "g/w", "--purge")
        self.reconcile()   # its process runs on: the replay finishes the purge, and nothing joins it
        self.reconcile()
        self.assertIsNone(threads.get(tid))
        self.assertFalse(os.path.exists(sminos.meta_path(seat_id)), "the seat went in the record's own entry")
        self.assertFalse(self.is_member(sid))

    def test_a_retire_stops_no_process_its_end_did_not_see(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        real = sminos.settle_ended

        def settle(*a, **k):
            self.session(sid=sid, kind="bg", started=ms_ago(0))   # a process started while the end finished
            return real(*a, **k)
        with mock.patch.object(sminos, "settle_ended", side_effect=settle), \
                mock.patch.object(sminos, "stop_session") as stop:
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIsNone(sminos.load_seat(sminos.meta_path(seat_id))["ended"]["pid"])
        stop.assert_not_called()

    def test_a_fill_resume_whose_return_is_not_finished_writes_nothing_through_it_and_says_so(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        real = sminos.settle_ended
        start, poll = self.engine(sid)
        with start, poll, mock.patch.object(sminos, "settle_ended", side_effect=lambda p, s, lock_until=None,
                                            until=None: False if until is not None else real(p, s, lock_until, until)):
            code, out = self.cli("fill", "g/w", "carry on", "--resume")
        self.assertEqual(code, 1, out)
        self.assertIn("its joined waits for the next reconciliation", out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual(seat["pending"]["op"], "return")
        self.assertNotEqual(seat["status"], "working", "nothing written through its open entry")
        self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.assertIsNone(sminos.load_seat(sminos.meta_path(seat_id)).get("pending"))

    def test_an_edit_of_a_seat_its_end_reached_meanwhile_keeps_it_retired(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        real = sminos.seat_project

        def ended_meanwhile(s):
            if s and s.get("seat_id") == seat_id and "ended" not in (sminos.reload_seat(seat_id) or {}):
                at = sminos.now()   # the sweep's end, between the edit's read and its write
                sminos.meta_set(seat_id, {"status": "retired", "updated": at,
                                          "ended": {"at": at, "reason": "ended", "by": "", "pid": None}})
            return real(s)
        with mock.patch.object(sminos, "seat_project", side_effect=ended_meanwhile):
            code, out = self.cli("seat", "add", "g", "w", "--session", sid, "--role", "reviewer")
        self.assertEqual(code, 0, out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["status"], seat["ended"]["reason"], seat["role"]), ("retired", "ended", "reviewer"))

    def test_an_edit_of_a_seat_an_older_copy_retired_keeps_the_time_of_its_end(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        at = ago(600)
        sminos.meta_set(seat_id, {"status": "retired", "updated": at})
        code, out = self.cli("seat", "add", "g", "w", "--session", sid, "--role", "reviewer")
        self.assertEqual(code, 0, out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["status"], seat["updated"], seat["role"]), ("retired", at, "reviewer"))

    def test_a_retired_seat_named_by_its_short_and_an_ended_thread_by_its_full_id_are_refused_saying_so(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        other = self.closed(name="beta")
        code, out = self.cli("retire", "beta")
        self.assertEqual(code, 0, out)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        for argv, said in ((("say", "@%s are you there" % sid[:8]), "is retired — a fill returns it"),
                           (("send", sid[:8], "are you there"), "g/w is retired"),
                           (("send", other, "are you there"), "beta was retired")):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn(said, out)


# ------------------------------------------------------------ the canonical end, final (review 3)


class Canonical(Ending):
    """The end in effect governs a seat an older copy gave a thread its
    human opened, a seat that cannot be read keeps the entry open, the
    return's boundary is the log's positions, and nothing is stopped,
    returned or edited past what was seen."""

    older_seat = Boundaries.older_seat

    def remote_message(self, sid, offset):
        """An addressed message from another machine's writer, its clock `offset` seconds off this one's."""
        writer = "farhost/%s" % uuidlib.uuid4()
        t = time.time() + offset
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%03dZ" % int((t % 1) * 1000)
        with open(sminos.writer_path(self.p, writer), "a") as f:
            f.write(json.dumps({"ts": ts, "writer": writer, "seq": 1, "kind": "message", "session": str(uuidlib.uuid4()),
                                "text": "@alpha from afar", "to": [{"session": sid, "alias": "alpha"}]}) + "\n")
        sminos.forget_caches()

    def legacy_retired(self, project_seat=True):
        """A thread its human opened, an older copy's seat over it, and that copy's retire of it, reconciled."""
        sid, proc = self.opened(inbox=True)
        tid = threads.stamp(sid)
        seat_id = self.older_seat(sid)
        self.write_own(sid, [{"kind": "retired", "by": "legacy", "reason": "retire", "pid": proc.pid}])
        if project_seat:
            self.reconcile()
        else:
            with mock.patch.object(sminos, "seat_over", return_value=None):
                self.reconcile()
        self.assertTrue(threads.record_ended(threads.get(tid)))
        return sid, tid, seat_id

    def assert_ended_governs(self, sid):
        code, out = self.cli("list", "--all")
        row = next((" ".join(line.split()) for line in out.splitlines() if line.lstrip().startswith("w [")), "")
        self.assertIn("retired", row, out)
        self.assertNotIn("idle", row)
        code, out = self.cli("send", "g/w", "are you there")
        self.assertEqual(code, 4, out)
        self.assertIn("has ended", out)
        self.assertEqual(self.inbox(sid), [], "nothing reached it")

    def test_an_older_copys_retire_of_a_seated_human_thread_governs_its_row_and_send(self):
        sid, _, seat_id = self.legacy_retired()
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["status"], "retired", "its seat followed")
        self.assert_ended_governs(sid)

    def test_the_end_governs_even_where_the_seat_never_followed_and_a_retire_then_aligns_it(self):
        sid, _, seat_id = self.legacy_retired(project_seat=False)
        self.assertNotEqual(sminos.load_seat(sminos.meta_path(seat_id))["status"], "retired")
        self.assert_ended_governs(sid)
        with mock.patch.object(sminos, "stop_session"):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["status"], "retired", out)

    def test_a_purge_whose_seat_cannot_be_read_stays_open_until_it_can(self):
        sid, _ = self.opened()
        tid = threads.stamp(sid)
        seat_id = self.older_seat(sid)
        path, real = sminos.meta_path(seat_id), sminos.settle_ended
        self.addCleanup(lambda: os.path.exists(path) and os.chmod(path, 0o600))

        def unreadable(*a, **k):
            os.chmod(path, 0)   # an OSError on the seat's read, just before the entry brings it in line
            return real(*a, **k)
        with mock.patch.object(sminos, "settle_ended", side_effect=unreadable), \
                mock.patch.object(sminos, "stop_session"):
            code, out = self.cli("retire", "g/w", "--purge")
        self.assertEqual(code, 1, out)
        self.assertEqual(threads.get(tid)["pending"]["last"], "purge", "not purged while its seat stands")
        os.chmod(path, 0o600)
        self.reconcile()
        self.assertIsNone(threads.get(tid))
        self.assertFalse(os.path.exists(path))
        self.assertFalse(self.is_member(sid))

    def test_a_remote_event_from_a_clock_ahead_that_reached_the_log_before_the_return_is_settled_by_it(self):
        sid, tid = self.ended_by_rule()
        self.remote_message(sid, 3600)
        self.assertEqual(len(self.owed_any(sid)), 1)
        self.live(sid=sid, name="alpha")
        self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.assertEqual(self.owed_any(sid), [], "it reached the log while the end stood")

    def test_a_remote_event_from_a_clock_behind_that_reached_the_log_after_the_return_began_is_its_own(self):
        sid, tid = self.ended_by_rule()
        self.live(sid=sid, name="alpha")
        real = threads.begin

        def begin(*a, **k):
            entry = real(*a, **k)
            if entry is not None and entry["op"] == "return":
                self.remote_message(sid, -3600)
            return entry
        with mock.patch.object(threads, "begin", side_effect=begin):
            self.reconcile()
        self.assertTrue(self.is_member(sid))
        self.assertEqual(len(self.owed_any(sid)), 1, "it reached the log after the return began")

    def test_a_retire_with_no_turn_seen_never_stops_a_turn_found_after_its_end(self):
        sid, proc, seat_id = self.seated()
        real, swapped = sminos.agents_refresh, []

        def refresh():
            if not swapped and isinstance((sminos.reload_seat(seat_id) or {}).get("ended"), dict):
                swapped.append(1)   # after the end: the process it saw is gone, and another holds the session
                self.end(proc)
                self.session(sid=sid, kind="bg", started=ms_ago(0))
                sminos.agents_json.return_value = [{"id": "newjob01", "sessionId": sid, "state": "working",
                                                    "status": "busy"}]
            return real()
        with mock.patch.object(sminos, "agents_refresh", side_effect=refresh):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertTrue(swapped)
        self.assertNotIn(mock.call("newjob01"), sminos.claude_stop.call_args_list)

    def test_an_unconfirmed_fill_resume_does_not_return_the_seat(self):
        sid, seat_id = EndStands.retired_seat(self)
        start, _ = self.engine(sid)
        with start, mock.patch.object(sminos, "poll_uuid", return_value=None):
            code, out = self.cli("fill", "g/w", "carry on", "--resume")
        self.assertEqual(code, 1, out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["status"], (seat.get("ended") or {}).get("reason")), ("retired", "retire"))
        self.assertFalse(self.is_member(sid))
        self.assertIn("stays retired", out)

    def open_end(self, seat_id, sid):
        at = sminos.now()
        return threads.begin(seat_id, "end", self.p, [{"kind": "retired", "session": sid, "by": "", "reason": "retire"}],
                             fields={"status": "retired", "updated": at,
                                     "ended": {"at": at, "reason": "retire", "by": "", "pid": None}}, settle=sid)

    def test_seat_add_is_refused_while_an_end_it_cannot_finish_is_open(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        self.assertIsNotNone(self.open_end(seat_id, sid))
        with mock.patch.object(sminos, "settle_ended", return_value=False):
            code, out = self.cli("seat", "add", "g", "w", "--session", sid, "--role", "reviewer")
        self.assertEqual(code, 1, out)
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["role"], seat["pending"]["op"]), ("", "end"))

    def test_seat_add_writes_nothing_through_an_end_begun_meanwhile(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        real = sminos.seat_project

        def begun_meanwhile(s):
            if s and s.get("seat_id") == seat_id and not (sminos.reload_seat(seat_id) or {}).get("pending"):
                self.assertIsNotNone(self.open_end(seat_id, sid))
            return real(s)
        with mock.patch.object(sminos, "seat_project", side_effect=begun_meanwhile):
            code, out = self.cli("seat", "add", "g", "w", "--session", sid, "--role", "reviewer")
        self.assertEqual(code, 1, out)
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["role"], "")

    def test_a_qualified_tag_naming_a_retired_seat_by_its_short_is_refused_saying_so(self):
        sid, _ = EndStands.retired_seat(self)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        code, out = self.say("@%s/%s are you there" % (self.p.name, sid[:8]))
        self.assertEqual(code, 4, out)
        self.assertIn("is retired — a fill returns it", out)


if __name__ == "__main__":
    unittest.main()
