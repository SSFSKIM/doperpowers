#!/usr/bin/env python3
"""A seat's lifecycle verbs against the writers that race them (T1:
docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md, Interfaces §6 and
§7): retire, remove and purge, `seat add` and its plain repoint, a refill's
launch, and a first spawn's claim of its child, each driven through the
interleaving that once broke it.

- An end decides on what it rechecks under the lock it writes under: a
  seat adopted as a thread after its no-thread end was decided is not
  retired or deleted outside its journal; a repeated retire stops only the
  process the end that stands saw; a vacant seat's refill left open is
  finished before its removal.
- A purge deletes only the occupant it was begun for, and `remove` names
  a thread's current session before a seat it left; an ended thread its
  human opened is still reached by a full id.
- A seat that takes another session takes none of its predecessor's marks
  or, for a lane B session, its thread; `seat add` writes nothing a refused
  claim would leave; a plain repoint never writes through an open entry.
- A first spawn's seat and its child's own record never both claim the
  child; a refill whose launch could not be journaled writes nothing over
  the session the seat holds.

Hermetic, as test_threads.py. Run: python3 -B sminos/tests/test_threads_branch_a.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
import os
import sys
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import Killed, Sessions, SpawnsChild, ms_ago, records, sminos, threads  # noqa: E402
from test_threads_ended import Ending  # noqa: E402


def seat_raw(seat_id):
    try:
        return sminos.load_seat(sminos.meta_path(seat_id))
    except FileNotFoundError:
        return None


class Base(Ending):
    def lane_b_seat(self, alias="w"):
        """A seat `seat add` made for a lane B session: no thread."""
        sid, proc = self.session(name=alias)
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        code, out = self.cli("seat", "add", "g", alias, "--session", sid)
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats() if s["alias"] == alias)
        self.assertIsNone(threads.get(seat_id))
        return sid, proc, seat_id

    def retirements(self, sid):
        return [e for e in self.own(sid) if e["kind"] == "retired"]


class NoThreadEnd(Base):
    """[scalpel-1#1] The end of a seat no record tracked, decided and written
    under both stores' locks."""

    def adopted_meanwhile(self, sid, seat_id):
        real = threads.ensure

        def ensure(session, seat=None, *a, **k):
            got = real(session, seat, *a, **k)
            if got is None and seat is not None and session == sid:
                # A reconciliation, after the end found no thread: the session is lane A now, and its seat adopted.
                records.set_controller(sid, "A")
                self.assertIsNotNone(real(sid, seat=sminos.reload_seat(seat_id), project=self.p))
            return got
        return mock.patch.object(threads, "ensure", side_effect=ensure)

    def test_a_seat_adopted_after_its_no_thread_retire_was_decided_is_not_retired(self):
        sid, _, seat_id = self.lane_b_seat()
        with self.adopted_meanwhile(sid, seat_id):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 4, out)
        self.assertIn("changed while its end was decided", out)
        self.assertNotEqual(seat_raw(seat_id)["status"], "retired")
        self.assertEqual(self.retirements(sid), [])

    def test_nor_removed(self):
        sid, _, seat_id = self.lane_b_seat()
        with self.adopted_meanwhile(sid, seat_id):
            code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 4, out)
        self.assertIsNotNone(seat_raw(seat_id), "the seat, a thread now, is not deleted")
        self.assertEqual(self.retirements(sid), [])

    def test_a_lane_b_seat_retires_and_is_removed_as_before(self):
        sid, _, seat_id = self.lane_b_seat()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertEqual(seat_raw(seat_id)["status"], "retired")
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIsNone(seat_raw(seat_id))


class RepeatedRetire(Base):
    """[scalpel-1#5] A retire of a seat whose end stands stops only the
    process that end saw."""

    def test_a_process_the_standing_end_did_not_see_is_not_stopped(self):
        sid, proc, seat_id = self.seated()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertEqual(seat_raw(seat_id)["ended"]["pid"], proc.pid)
        real = sminos.locked_fresh

        def locked(*a, **k):
            got = real(*a, **k)
            # Past the lookup's reconciliation: a new job of the session, which the end that stands never saw.
            self.end(proc)
            self.session(sid=sid, kind="bg", started=ms_ago(0))
            sminos.agents_json.return_value = [{"id": "newjob01", "sessionId": sid, "state": "working",
                                                "status": "busy"}]
            return got
        sminos.claude_stop.reset_mock()
        with mock.patch.object(sminos, "locked_fresh", side_effect=locked):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertNotIn(mock.call("newjob01"), sminos.claude_stop.call_args_list)
        self.assertEqual(seat_raw(seat_id)["ended"]["pid"], proc.pid, "the end that stands is the first")

    def test_the_process_the_standing_end_saw_is_still_stopped(self):
        sid, proc, seat_id = self.seated()
        sminos.agents_json.return_value = [{"id": "job00001", "sessionId": sid, "state": "working",
                                            "status": "busy"}]
        with mock.patch.object(sminos, "claude_stop", return_value=False):   # the first stop did not take
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        sminos.claude_stop.reset_mock()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIn(mock.call("job00001"), sminos.claude_stop.call_args_list)


class VacantRefillRemoved(Base):
    """[scalpel-2#1] A vacant seat whose refill was cut with its new session
    queued behind the launch's entry: the entry is finished before the seat
    is removed."""

    def test_the_queued_refill_is_finished_and_the_remove_refused_until_asked_again(self):
        old, proc, seat_id = self.seated()
        self.end(proc)
        new, _ = self.session(kind="bg", started=ms_ago(0))
        with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")):
            entry = threads.begin(seat_id, "advance", self.p,
                                  [{"kind": "retired", "session": old, "by": "", "reason": "replaced"}],
                                  fields={"current": ""}, guard=lambda t: t["current"] == old)
        self.assertIsNotNone(entry)
        joined = sminos.joined_fields("w", "seat", self.root, "", "", seat_id, "", "seat", session=new)
        self.assertTrue(threads.follow(seat_id, entry["id"], "advance", self.p,
                                       [{"kind": "joined", "session": new, **joined}],
                                       fields={"current": new}, absorbs=True))
        s0 = sminos.reload_seat(seat_id)
        self.assertEqual(s0["current"], "")
        how = sminos.OwnerAsk("g/w", "remove")
        asked = sminos.seat_owner_guard(s0, True, how)
        locks, s = sminos.locked_fresh(s0, "remove")
        try:
            with self.assertRaises(SystemExit) as cm:
                sminos.end_and_stop(s, True, asked)
        finally:
            sminos.unlock(locks)
        self.assertEqual(cm.exception.code, 4)
        sminos.forget_caches()
        seat = seat_raw(seat_id)
        self.assertIsNotNone(seat, "not deleted over the replacement")
        self.assertEqual((seat["current"], seat.get("pending")), (new, None))
        self.assertEqual([e["reason"] for e in self.retirements(old)], ["replaced"], "the displacement is settled")
        self.assertTrue(self.is_member(new))
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIsNone(seat_raw(seat_id))
        self.assertEqual([e["reason"] for e in self.retirements(new)], ["retire"])


class PlainRepoint(Base):
    """[scalpel-2#3], [scalpel-4#7], [scalpel-3#8] `seat add --session` with no
    journal (a lane B session)."""

    def lane_b(self):
        sid, proc = self.session()
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        return sid, proc

    def test_an_end_begun_after_the_verbs_preflight_refuses_the_repoint(self):
        old, proc, seat_id = self.seated()
        self.end(proc)
        new, _ = self.lane_b()
        real = threads.repoint_seat

        def repoint(tid, fields, *a, **k):
            with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")):
                at = sminos.now()
                self.assertIsNotNone(threads.begin(
                    tid, "end", self.p, [{"kind": "retired", "session": old, "by": "", "reason": "ended"}],
                    fields={"status": "retired", "updated": at,
                            "ended": {"at": at, "reason": "ended", "by": "", "pid": None}}, settle=old))
            return real(tid, fields, *a, **k)
        with mock.patch.object(threads, "repoint_seat", side_effect=repoint):
            code, out = self.cli("seat", "add", "g", "w", "--session", new)
        self.assertEqual(code, 1, out)
        self.assertIn("begun meanwhile", out)
        seat = seat_raw(seat_id)
        self.assertEqual((seat["current"], seat["pending"]["op"]), (old, "end"))

    def test_a_retired_seat_given_a_lane_b_session_keeps_neither_its_end_nor_its_thread(self):
        old, proc, seat_id = self.seated()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.end(proc)
        new, _ = self.lane_b()
        code, out = self.cli("seat", "add", "g", "w", "--session", new)
        self.assertEqual(code, 0, out)
        seat = seat_raw(seat_id)
        self.assertEqual(seat["current"], new)
        for k in threads.SEAT_KEYS:
            self.assertNotIn(k, seat)
        self.assertIsNone(threads.get(seat_id))
        self.assertEqual(threads.stamp(new), "")
        self.assertTrue(self.joins(new))
        self.assertTrue(all("thread" not in j for j in self.joins(new)), "an unstamped join, as lane B's")
        self.assertTrue(self.is_member(new))

    def test_a_lane_a_plain_repoint_drops_its_predecessors_marks(self):
        old, proc, seat_id = self.seated()
        self.end(proc)
        sminos.meta_set(seat_id, {"stopped": sminos.now(), "swept": sminos.now(),
                                  "ended": {"at": sminos.now(), "reason": "ended", "by": "", "pid": None}})
        new, _ = self.session()
        self.assertTrue(threads.repoint_seat(seat_id, {"current": new, "status": "idle"}))
        seat = seat_raw(seat_id)
        for k in ("ended", "stopped", "swept"):
            self.assertNotIn(k, seat)
        self.assertEqual(seat["opened"], "spawned", "a lane A session's seat stays its thread")


class OlderRefill(Base):
    """[scalpel-3#6] An older copy that refilled a seat (its `current`
    changed, `sessions` and the marks left as they were)."""

    def test_its_predecessors_end_and_stop_marks_are_not_the_new_occupants(self):
        old, proc, seat_id = self.seated()
        self.end(proc)
        at = sminos.now()
        sminos.meta_set(seat_id, {"stopped": at, "swept": at,
                                  "ended": {"at": at, "reason": "ended", "by": "", "pid": None}})
        new, _ = self.session(kind="bg", started=ms_ago(0))
        sminos.meta_set(seat_id, {"current": new, "status": "working"})   # 1.27.10's refill merges `current`
        t = threads.get(seat_id)
        self.assertEqual(t["current"], new)
        for k in ("ended", "stopped", "swept"):
            self.assertNotIn(k, t)
        self.reconcile()
        seat = seat_raw(seat_id)
        self.assertIn(new, seat["sessions"])
        for k in ("ended", "stopped", "swept"):
            self.assertNotIn(k, seat, "dropped where the sessions are repaired")
        self.assertTrue(self.is_member(new))


class PurgeAfterOlderRefill(Base):
    """[scalpel-3#3] A purge left open, then an older copy's refill of the
    seat: the replay deletes nothing that holds another session."""

    def test_the_replay_keeps_the_seat_that_holds_another_session(self):
        old, proc, seat_id = self.seated()
        real = threads._change

        def change(tid, mutate, *a, **k):
            if mutate.__name__ == "clear":
                raise Killed()
            return real(tid, mutate, *a, **k)
        with mock.patch.object(threads, "_change", side_effect=change), self.assertRaises(Killed):
            self.cli("remove", "g/w")
        self.assertEqual(seat_raw(seat_id)["pending"]["last"], "purge")
        self.end(proc)
        new, _ = self.session(kind="bg", started=ms_ago(0))
        sminos.meta_set(seat_id, {"current": new, "status": "working"})   # 1.27.10 keeps the unknown `pending`
        self.reconcile()
        seat = seat_raw(seat_id)
        self.assertIsNotNone(seat, "the replacement's seat is not deleted")
        self.assertEqual((seat["current"], seat.get("pending")), (new, None))
        self.assertEqual([e["reason"] for e in self.retirements(old)], ["retire"])


class RemoveByFirstOccupant(Base):
    """[scalpel-3#2] `remove` of a seat's first occupant, reopened as a
    thread of its own, by its id, which is also the seat's."""

    def test_it_removes_that_session_and_not_the_seat_it_left(self):
        first, proc = self.live(name="alpha")
        self.transcript(first)
        code, out = self.cli("seat", "add", "g", "w", "--session", first)
        self.assertEqual(code, 0, out)
        self.assertIsNotNone(seat_raw(first), "the seat's id is its first session's")
        self.end(proc)
        second, _ = self.session(name="w")
        code, out = self.cli("seat", "add", "g", "w", "--session", second)
        self.assertEqual(code, 0, out)
        self.assertEqual(seat_raw(first)["current"], second)
        self.live(sid=first, name="alpha", started=ms_ago(0))   # its human reopens it: a thread of its own
        self.reconcile()
        mine = threads.thread_of(first)
        self.assertEqual((mine["opened"], mine["current"]), ("human", first))
        code, out = self.cli("remove", first)
        self.assertEqual(code, 0, out)
        self.assertIsNotNone(seat_raw(first), "the seat it left is not removed")
        self.assertEqual(seat_raw(first)["current"], second, "the seat it left keeps its session")
        self.assertIsNone(threads.get(mine["thread"]), "its own record is purged")


class ArchivedHuman(Base):
    """[scalpel-4#9] An ended thread its human opened, its record set aside,
    reached by a full id for its purge."""

    def retired_aside(self):
        sid = self.closed()
        tid = threads.stamp(sid)
        code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.human_files(aside=True)), 1)
        return sid, tid

    def test_remove_by_its_session_id(self):
        sid, tid = self.retired_aside()
        code, out = self.cli("remove", sid)
        self.assertEqual(code, 0, out)
        self.assertIsNone(threads.get(tid))
        self.assertEqual(self.human_files(aside=True), [])

    def test_retire_purge_by_its_thread_id(self):
        sid, tid = self.retired_aside()
        code, out = self.cli("retire", tid, "--purge")
        self.assertEqual(code, 0, out)
        self.assertIsNone(threads.get(tid))

    def test_a_plain_retire_of_it_says_it_was_retired_already(self):
        sid, tid = self.retired_aside()
        code, out = self.cli("retire", sid)
        self.assertEqual(code, 4, out)
        self.assertIn("retired already", out)
        self.assertIsNotNone(threads.get(tid))


class ArchivedPurgeBound(Base):
    """Review 2, item 3: an ended row is the log's and outlives its record;
    a purge by a thread's id acts on that thread's record alone."""

    def test_remove_by_a_purged_threads_id_deletes_no_later_thread_of_its_session(self):
        sid = self.closed()
        a = threads.stamp(sid)
        code, out = self.cli("retire", "alpha", "--purge")
        self.assertEqual(code, 0, out)
        self.assertIsNone(threads.get(a))
        other = self.repo("other")
        p2 = self.project_of(other)
        _, proc = self.session(root=other, sid=sid, started=ms_ago(0), name="alpha")
        self.peer_set(proc, nameSource="user")
        self.transcript(sid)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("join", p2.id, cwd=other)
        self.assertEqual(code, 0, out)
        self.reconcile(p2)
        b = threads.stamp(sid)
        self.assertTrue(b and b != a, "its session, run again, is a thread of its own")
        self.end(proc)
        code, out = self.cli("retire", sid, cwd=other)
        self.assertEqual(code, 0, out)
        self.assertTrue(threads.record_ended(threads.get(b)))
        code, out = self.cli("remove", a)
        self.assertEqual(code, 4, out)
        self.assertIsNotNone(threads.get(b), "the later thread's record is not purged")
        code, out = self.cli("retire", a, "--purge")
        self.assertEqual(code, 4, out)
        self.assertIsNotNone(threads.get(b))


class RepeatedPurgeStop(Base):
    """Review 2, item 5: a purge of a seat whose end stands, the seat file
    deleted by the time its stop is decided, stops only the process that end
    recorded."""

    def test_remove_does_not_stop_a_job_that_reopened_the_session_after_the_lookup(self):
        sid, proc, seat_id = self.seated()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        end = seat_raw(seat_id)["ended"]
        self.assertEqual(end["pid"], proc.pid)
        real = sminos.locked_fresh

        def locked(*a, **k):
            got = real(*a, **k)
            # Past the lookup: another job of the session, started within the second of the end.
            self.end(proc)
            self.session(sid=sid, kind="bg", started=int(sminos._ts_epoch(end["at"]) * 1000))
            sminos.agents_json.return_value = [{"id": "newjob01", "sessionId": sid, "state": "working",
                                                "status": "busy"}]
            return got
        sminos.claude_stop.reset_mock()
        with mock.patch.object(sminos, "locked_fresh", side_effect=locked):
            code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIsNone(seat_raw(seat_id), "removed")
        self.assertNotIn(mock.call("newjob01"), sminos.claude_stop.call_args_list)

    def test_remove_still_stops_the_job_the_standing_end_saw(self):
        sid, proc, seat_id = self.seated()
        sminos.agents_json.return_value = [{"id": "job00001", "sessionId": sid, "state": "working",
                                            "status": "busy"}]
        with mock.patch.object(sminos, "claude_stop", return_value=False):   # the retire's stop did not take
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        sminos.claude_stop.reset_mock()
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIsNone(seat_raw(seat_id))
        self.assertIn(mock.call("job00001"), sminos.claude_stop.call_args_list)


class SeatAddRefused(Base):
    """[scalpel-2#2] `seat add --session` whose claim is refused changes
    nothing of the seat."""

    def test_its_fields_are_not_written_when_another_seat_holds_the_session(self):
        a, proc, seat_id = self.seated(alias="w1")
        self.end(proc)
        x, _, _ = self.seated(alias="w2")
        before = seat_raw(seat_id)
        code, out = self.cli("seat", "add", "g", "w1", "--session", x, "--role", "new role")
        self.assertEqual(code, 4, out)
        after = seat_raw(seat_id)
        self.assertEqual({k: after[k] for k in ("current", "role", "status", "short", "updated")},
                         {k: before[k] for k in ("current", "role", "status", "short", "updated")})

    def test_a_claim_that_succeeds_writes_them_with_the_session(self):
        a, proc, seat_id = self.seated(alias="w1")
        self.end(proc)
        x, _ = self.session()
        code, out = self.cli("seat", "add", "g", "w1", "--session", x, "--role", "new role")
        self.assertEqual(code, 0, out)
        seat = seat_raw(seat_id)
        self.assertEqual((seat["current"], seat["role"], seat["status"]), (x, "new role", "idle"))
        self.assertEqual(self.joins(x)[-1]["role"], "new role", "its joined carries the role written with it")


class RefillLaunchFailed(Base):
    """[scalpel-2#5] A refill whose launch write could not be journaled."""

    def test_nothing_is_written_over_the_seats_session_and_the_launched_one_is_stopped(self):
        old, proc, seat_id = self.seated()
        self.end(proc)
        new = str(uuidlib.uuid4())
        real = threads.begin

        def begin(tid, op, *a, **k):
            if op == "advance" and (k.get("fields") or {}).get("current") == "":
                raise OSError("disk full")
            return real(tid, op, *a, **k)
        start, _ = self.engine(new)
        with start, mock.patch.object(sminos, "poll_uuid", return_value=None), \
                mock.patch.object(threads, "begin", side_effect=begin):
            code, out = self.cli("fill", "g/w", "a task")
        self.assertEqual(code, 1, out)
        seat = seat_raw(seat_id)
        self.assertEqual((seat["current"], seat.get("pending")), (old, None))
        self.assertIn(mock.call(new[:8]), sminos.claude_stop.call_args_list)
        self.assertEqual(self.retirements(old), [], "nothing displaced it")


class FirstSpawnClaim(SpawnsChild):
    """[scalpel-2#4] A first spawn whose launcher, slower than the
    spawner's bound, dies once its seat is named."""

    def test_its_seat_and_its_childs_own_record_never_both_claim_the_child(self):
        hooked = []

        def meanwhile(child, launch):
            self.peer_set(child["proc"], startedAt=ms_ago(threads.spawner_bound() + 5))
            self.child_hook(child, launch)
            self.assertEqual(threads.thread_of(child["sid"])["opened"], "human")
            hooked.append(1)

        real = sminos.ensure_record

        def ensure_record(*a, **k):
            if hooked:
                raise Killed()   # the launcher, once its seat is named
            return real(*a, **k)
        with mock.patch.object(sminos, "ensure_record", side_effect=ensure_record), self.assertRaises(Killed):
            self.spawn(meanwhile)
        sminos.forget_caches()
        [path] = list(sminos.record_files())
        [human] = threads.human_threads()
        child = human["current"]
        self.assertNotEqual(sminos.load_seat(path)["current"], child, "the seat claims it only by its absorption")
        self.assertEqual(threads.thread_of(child)["thread"], human["thread"])


# ------------------------------------------------------------ the debt, fixed (group-DEBT, review 2 items 4, 6, 9, 11)


def queued_refill(case, seat_id, old, new):
    """A refill of `seat_id` cut with its launch's entry open (owing `old`'s
    `replaced`) and its poll's advance to `new` queued behind it."""
    with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")):
        entry = threads.begin(seat_id, "advance", case.p,
                              [{"kind": "retired", "session": old, "by": "", "reason": "replaced"}],
                              fields={"current": ""}, guard=lambda t: t["current"] == old)
    joined = sminos.joined_fields("w", "seat", case.root, "", "", seat_id, "", "seat", session=new)
    case.assertTrue(threads.follow(seat_id, entry["id"], "advance", case.p,
                                   [{"kind": "joined", "session": new, **joined}],
                                   fields={"current": new}, absorbs=True))


def cut_at_clear():
    real = threads._change

    def change(tid, mutate, *a, **k):
        if mutate.__name__ == "clear":
            raise Killed()
        return real(tid, mutate, *a, **k)
    return mock.patch.object(threads, "_change", side_effect=change)


class FormerShortBinds(Base):
    """[scalpel-4#8] A thread's former session named by its short binds the
    session the seat holds: a refill before the verb's lock is refused."""

    def test_a_retire_by_a_former_short_is_refused_after_a_refill_in_between(self):
        code, out = self.cli("seat", "add", "g", "w")
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats())
        first, p1 = self.session(name="w")
        code, out = self.cli("seat", "add", "g", "w", "--session", first)
        self.assertEqual(code, 0, out)
        self.end(p1)
        second, p2 = self.session(name="w")
        code, out = self.cli("seat", "add", "g", "w", "--session", second)
        self.assertEqual(code, 0, out)
        self.end(p2)
        real = sminos.locked_fresh

        def locked(*a, **k):
            third, _ = self.session(name="w")
            code, out = self.cli("seat", "add", "g", "w", "--session", third)   # a refill, after the lookup
            self.assertEqual(code, 0, out)
            return real(*a, **k)
        with mock.patch.object(sminos, "locked_fresh", side_effect=locked):
            code, out = self.cli("retire", first[:8])
        self.assertEqual(code, 4, out)
        self.assertIn("left seat", out)
        self.assertNotIn("ended", seat_raw(seat_id), "the session the refill put there is not retired")


class HumanOccupantKept(Base):
    """[scalpel-4#5] `seat add` does not displace a stopped session its human
    opened that an older copy seated."""

    def test_seat_add_over_it_is_refused(self):
        sid = self.closed()
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})   # the older CLI's seat
        other, _ = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", other)
        self.assertEqual(code, 4, out)
        self.assertIn("its human opened", out)
        self.assertEqual(seat_raw(seat_id)["current"], sid)
        self.assertEqual(self.retirements(sid), [])


class SeatAddAfterReplay(Base):
    """Review 2, item 6: `seat add` acts on the seat its preflight's replay
    left, not on the occupant it read before."""

    def test_a_live_replacement_a_queued_refill_installs_is_not_displaced(self):
        old, proc, seat_id = self.seated()
        self.end(proc)
        new, _ = self.live(kind="bg", inbox=True, started=ms_ago(0), name="w")
        queued_refill(self, seat_id, old, new)
        lane_b, _ = self.session()
        records.establish(lane_b, records.default_provenance())
        records.set_controller(lane_b, "B")
        code, out = self.cli("seat", "add", "g", "w", "--session", lane_b)
        self.assertEqual(code, 4, out)
        self.assertIn("still holds a live session", out)
        self.assertEqual(seat_raw(seat_id)["current"], new)
        self.assertEqual(self.retirements(new), [])

    def test_a_seat_whose_purge_the_replay_finished_is_not_refilled(self):
        old, proc, seat_id = self.seated()
        with cut_at_clear(), self.assertRaises(Killed):
            self.cli("remove", "g/w")
        self.end(proc)
        new, _ = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", new)
        self.assertEqual(code, 4, out)
        self.assertIn("was removed", out)
        self.assertIsNone(seat_raw(seat_id))


class SupersededPurge(Base):
    """Review 2, item 9: a purge whose seat an older copy refilled before
    its last step says the seat was not removed."""

    def test_remove_says_the_seat_was_not_removed(self):
        old, proc, seat_id = self.seated()
        new, _ = self.session(kind="bg", started=ms_ago(0))
        real = threads._change

        def change(tid, mutate, *a, **k):
            if mutate.__name__ == "clear" and tid == seat_id and seat_raw(seat_id)["current"] == old:
                sminos.meta_set(seat_id, {"current": new, "status": "working"})   # 1.27.10's refill, just before
            return real(tid, mutate, *a, **k)
        with mock.patch.object(threads, "_change", side_effect=change):
            code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 4, out)
        self.assertIn("was not removed", out)
        seat = seat_raw(seat_id)
        self.assertEqual((seat["current"], seat.get("pending")), (new, None))
        self.assertEqual([e["reason"] for e in self.retirements(old)], ["retire"])


class ReplayedPurgeStops(Base):
    """Review 2, item 4: a remove retried after its purge was cut before its
    stop stops what that end saw."""

    def test_the_retry_stops_the_job_the_cut_purge_saw(self):
        sid, proc, seat_id = self.seated()
        sminos.agents_json.return_value = [{"id": "job00001", "sessionId": sid, "state": "working",
                                            "status": "busy"}]
        with cut_at_clear(), mock.patch.object(sminos, "stop_seen_turn", side_effect=Killed), \
                self.assertRaises(Killed):
            self.cli("remove", "g/w")   # the process dies before its stop
        self.assertEqual(seat_raw(seat_id)["pending"]["last"], "purge")
        sminos.claude_stop.reset_mock()
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIn("removed g/w", out)
        self.assertIsNone(seat_raw(seat_id))
        self.assertIn(mock.call("job00001"), sminos.claude_stop.call_args_list)

    def test_nor_a_job_that_reopened_it_since(self):
        sid, proc, seat_id = self.seated()
        with cut_at_clear(), mock.patch.object(sminos, "stop_seen_turn", side_effect=Killed), \
                self.assertRaises(Killed):
            self.cli("remove", "g/w")
        self.end(proc)
        self.session(sid=sid, kind="bg", started=ms_ago(0))
        sminos.agents_json.return_value = [{"id": "newjob01", "sessionId": sid, "state": "working",
                                            "status": "busy"}]
        sminos.claude_stop.reset_mock()
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertNotIn(mock.call("newjob01"), sminos.claude_stop.call_args_list)


class OlderRefillBack(Base):
    """Review 2, item 11: an older copy's refill back to an earlier
    occupant."""

    def test_the_earlier_occupant_is_current_last_and_not_ended_by_its_successors_end(self):
        a, pa, seat_id = self.seated()
        self.end(pa)
        b, pb = self.session(name="w")
        code, out = self.cli("seat", "add", "g", "w", "--session", b)
        self.assertEqual(code, 0, out)
        self.end(pb)
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertEqual(seat_raw(seat_id)["sessions"], [a, b])
        sminos.meta_set(seat_id, {"current": a, "status": "idle"})   # 1.27.10's `seat add --session` back to a
        t = threads.get(seat_id)
        self.assertEqual((t["current"], t["sessions"][-1]), (a, a))
        self.assertNotIn("ended", t, "b's end is not a's")
        self.session(sid=a, kind="bg", started=ms_ago(0), name="w")   # the older copy started it
        self.reconcile()
        seat = seat_raw(seat_id)
        self.assertEqual(seat["sessions"][-1], a)
        self.assertNotIn("ended", seat)


class OlderSeatAddsAsked(Base):
    """[scalpel-3#4] Occupants an older copy's `seat add` displaced without
    writing `history` are asked about too."""

    def test_an_intermediate_occupants_host_keeps_the_seat_from_its_end(self):
        a, pa, seat_id = self.seated()
        self.end(pa)
        b, c = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        for x in (b, c):   # two older `seat add --session`s between reads: `current`, a `joined`, no history
            sminos.meta_set(seat_id, {"current": x, "status": "idle"})
            self.write_own(x, [self.old_joined(x, alias="w", seat=seat_id, session_kind="seat")])
        with open(os.path.join(os.environ["HOME"], "devcloud-standin.json"), "w") as f:
            json.dump({"hosts": [{"name": "dc-b-0001", "account": "main", "provider": "hetzner",
                                  "creator": "@" + b[:8]}]}, f)
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 1, out)
        self.assertIn("dc-b-0001", out)
        self.assertNotIn("ended", seat_raw(seat_id))
        self.assertIn(b, seat_raw(seat_id)["sessions"], "and its repair keeps it")


class OlderSeatRepair(Base):
    """[scalpel-1#10] The repair of an older copy's seat of a thread its
    human opened, made by a retire that met the end in place, does not undo
    a return finished meanwhile."""

    def test_a_return_finished_before_the_repair_keeps_the_seat_idle(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        self.reconcile()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.end(proc)
        self.assertEqual(seat_raw(seat_id)["status"], "retired")
        real = threads.project_seat

        def project_seat(*a, **k):
            self.live(sid=sid, name="alpha", started=ms_ago(0))   # its human reopens it: returned meanwhile
            self.reconcile()
            self.assertFalse(threads.record_ended(threads.get(tid)))
            self.assertEqual(seat_raw(seat_id)["status"], "idle")
            return real(*a, **k)
        with mock.patch.object(threads, "project_seat", side_effect=project_seat):
            self.cli("retire", "g/w")
        self.assertEqual(seat_raw(seat_id)["status"], "idle", "the stale repair writes nothing over the return")


class CarriedOnce(Sessions):
    """[scalpel-2#6] A hand-off's carry, once done, is not done again by a
    replay over a deliberate change since."""

    def test_an_override_removed_after_the_copy_is_not_restored(self):
        old, oproc, tid = self.member()
        sminos.write_override(old, self.p.id)
        job, _ = self.job(old)
        self.end(oproc)
        with mock.patch.object(sminos, "_append", side_effect=OSError("disk full")), \
                mock.patch.object(sys, "stderr"):
            self.reconcile()
        self.assertEqual(threads.get(tid)["pending"]["carry"], [old, job], "open, an event owed")
        self.assertTrue(sminos.override_of(job), "the override copied")
        os.unlink(sminos.override_path(job))   # `join --cwd` removed it, deliberately
        sminos.forget_caches()
        self.reconcile()
        self.assertIsNone(threads.get(tid).get("pending"))
        self.assertFalse(sminos.override_of(job), "not copied again")


class RefusedOnce(Base):
    """The plan's residue: a refused absorption is said once on the machine,
    not once per process."""

    def test_a_second_process_says_nothing(self):
        old, new = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        other = {"ended": {"at": sminos.now(), "reason": "ended", "by": "", "pid": None}}
        for _ in range(2):
            sminos._HANDOFF_REFUSED.clear()   # another process
            sminos.refuse_hand_off(old, new, other)
        self.assertEqual(len(self.logged("cannot be absorbed")), 1)

    def logged(self, needle):
        try:
            with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
                return [line for line in f if needle in line]
        except OSError:
            return []


if __name__ == "__main__":
    unittest.main()
