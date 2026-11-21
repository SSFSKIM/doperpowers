#!/usr/bin/env python3
"""The set across a thread's life (CH1's M3:
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, the milestone's
"Proves"; Interfaces §3's rows C5 to C9).

- The log kept equal to the record (C5): after a continuation (a hand-off,
  of a thread its human opened and of a seat), a refill, a `join`, a `join`
  back to a project left with another set, a change of reach and back, a
  `joined` an older copy wrote, a return and a `/clear`, the reconciliation
  states the record's set, and every reader takes it (this machine's row,
  `channels_of`, and another machine's copy of the log), the empty set
  included. A reconciliation overtaken between its read and its call, by a
  removal or by a move, states nothing; a wake in flight, this process's
  or another's, leaves the difference to the next pass. On a machine with
  no channel, and over a log that states the record's set already, a
  reconciliation calls the operation not at all.
- Where a membership began (§4): unchanged by an end, a hand-off and a
  refill; written anew by a return with the log's positions then, over
  events addressed to the thread while it was ended; a former session that
  runs again as a thread of its own holds an empty set and no positions.
- An absorption (C9): a set on both sides, the continuing record's first;
  the limit, an addition past it dropped and said in daemon.log; the
  positions of the channels brought; the answered requests united; and its
  replay from a cut at each step.

Hermetic: test_threads' fixtures (HOME and SMINOS_HOME temporary; sessions
`sleep`s with engine records the test writes), T1's transitions driven
through their own (Sessions, LateHandOff, Hub, Ending, Clear).
Run: python3 -B sminos/tests/test_channels_life.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import os
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import test_threads as T1  # noqa: E402 — its fixtures by module: their own tests are not run again here
import test_threads_ended as T1_ended  # noqa: E402
import test_threads_stopped as T1_stopped  # noqa: E402
from test_threads import Killed, ms_ago, records, sminos, threads  # noqa: E402
import sminos_channels as channels  # noqa: E402

HUB = {"url": "http://127.0.0.1:9", "org": "org-1"}
DESK = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"     # channels (version 8)
LOBBY = "0123abcd-4567-8abc-a123-456789abcdef"
ROOM = "0123abce-4567-8abc-a123-456789abcdef"


def channel_ids(n, start=1):
    return ["%08x-0000-8000-8000-000000000000" % i for i in range(start, start + n)]


class Life:
    """Channels registered here as the org's directory registers a log, and what a test reads of a set. A
    fixture class's own tests are not inherited: each runs in its own file."""

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        for name in dir(cls):
            if name.startswith("test_") and name not in cls.__dict__:
                setattr(cls, name, None)

    REGISTER = True

    def setUp(self):
        super().setUp()
        if self.REGISTER:
            self.register()

    def register(self):
        for cid, name in ((DESK, "desk"), (LOBBY, "lobby"), (ROOM, "room")):
            sminos.register_if_absent(sminos.make_project(cid, name, "", "", HUB))
        sminos.forget_caches()

    def chan(self, cid):
        return sminos.known_project(cid)

    def add(self, tid, sid, *cids):
        for cid in cids:
            self.assertEqual(channels.change(tid, cid, "add", sid).state, "applied")
        sminos.forget_caches()

    def statements(self, sid, p=None):
        return [e for e in sminos._own_events(p or self.p, sid) if e["kind"] == "channels"]

    def row_of(self, sid, p=None):
        sminos.forget_caches()
        return next((m for m in sminos.view_of(p or self.p).members if m.session == sid), None)

    def raw(self, tid, mutate):
        """The record's stored object changed in place, under its store lock (a hand edit, another writer)."""
        def change(view, raw):
            mutate(raw)
            return True
        self.assertTrue(threads._change(tid, change))
        sminos.forget_caches()

    def touch(self, cid, writer="beta/human", **fields):
        """An event in a channel's log, as an import leaves one."""
        e = sminos.log_append(self.chan(cid), writer, "channel-env", op="add", machine="beta", thread="x", **fields)
        sminos.forget_caches()
        return e

    def assert_read(self, tid, sid, want, p=None, elsewhere=True):
        """Every reader takes the record's set: the record, channels_of, this machine's row and, from the log
        alone, another machine's."""
        want = list(want)
        self.assertEqual(threads.get(tid)["channels"], want)
        self.assertEqual(channels.channels_of(sid), tuple(want))
        row = self.row_of(sid, p)
        self.assertIsNotNone(row, "a member here")
        self.assertEqual(row.channels, tuple(want), "this machine's row")
        if elsewhere and hasattr(self, "elsewhere") and (p is None or p.id == self.p.id):
            with self.elsewhere() as there:
                m = next((m for m in sminos.view_of(there).members if m.session == sid), None)
                self.assertIsNotNone(m)
                self.assertEqual(m.channels, tuple(want), "another machine's, from the log alone")

    def assert_steady(self, tid, sid, p=None):
        """A reconciliation over a log that states the record's set calls the operation not at all."""
        before = list(self.statements(sid, p))
        with mock.patch.object(threads, "set_channels", side_effect=AssertionError("set_channels called")):
            self.reconcile(p)
            self.reconcile(p)
        self.assertEqual(self.statements(sid, p), before)


# ------------------------------------------------------------ the log kept equal to the record (C5)


class Kept(Life, T1.Sessions):
    def test_a_hand_off_of_a_thread_its_human_opened_is_restated_under_the_job_and_keeps_its_positions(self):
        old, oproc, tid = self.member()
        self.touch(DESK)
        self.add(tid, old, DESK, LOBBY)
        began = threads.get(tid)["began"]
        self.assertEqual(began[DESK], {"beta/human": 1})
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assertEqual(threads.get(tid)["current"], job)
        [s] = self.statements(job)
        self.assertEqual((s["channels"], s["thread"], s["writer"]), ([DESK, LOBBY], tid, sminos.writer_id(job)))
        self.assert_read(tid, job, [DESK, LOBBY])
        self.assertEqual(threads.get(tid)["began"], began, "a continuation carries the positions untouched")
        self.assert_steady(tid, job)

    def test_a_hand_off_of_a_seat_is_restated_under_the_job(self):
        old, seat_id = self.seated(alias="keeper")
        _, oproc = self.session(sid=old)
        self.reconcile()
        self.add(seat_id, old, DESK)
        began = threads.get(seat_id)["began"]
        job, _ = self.job(old)
        self.end(oproc)
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["current"], job)
        self.assert_read(seat_id, job, [DESK])
        self.assertEqual(threads.get(seat_id)["began"], began)
        self.assert_steady(seat_id, job)

    def test_a_refill_is_restated_under_the_new_session_and_keeps_its_positions(self):
        old, seat_id = self.seated()
        self.touch(LOBBY)
        self.add(seat_id, old, LOBBY)
        began = threads.get(seat_id)["began"]
        new, _, out = self.refill(seat_id)
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["current"], new, out)
        self.assert_read(seat_id, new, [LOBBY])
        self.assertEqual(threads.get(seat_id)["began"], began, "a refill carries the positions untouched")
        self.assertEqual([s["channels"] for s in self.statements(new)], [[LOBBY]])

    def live_thread(self, kind):
        """(session, thread id) of a live thread of either kind."""
        if kind == "human":
            sid, _, tid = self.member()
            return sid, tid
        sid, _ = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        return sid, threads.thread_of(sid)["thread"]

    def test_a_join_is_restated_in_the_project_moved_to_and_a_join_back_with_another_set(self):
        for kind in ("human",):   # a seat's project is where it was spawned: `join` refuses one, writing nothing
            with self.subTest(kind):
                self.fresh()
                self.register()
                other = self.project_of(self.repo("other"))
                sid, tid = self.live_thread(kind)
                self.add(tid, sid, DESK)
                with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
                    code, out = self.cli("join", other.name)
                self.assertEqual(code, 0, out)
                self.reconcile(other)
                self.assertEqual([s["channels"] for s in self.statements(sid, other)], [[DESK]])
                self.assert_read(tid, sid, [DESK], p=other)
                # In the project moved to, another set; then back to the first, whose last statement says [DESK].
                self.add(tid, sid, LOBBY)
                self.assertEqual(self.statements(sid, other)[-1]["channels"], [DESK, LOBBY])
                with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
                    code, out = self.cli("join", self.p.name)
                self.assertEqual(code, 0, out)
                self.reconcile()
                self.assertEqual(self.statements(sid)[-1]["channels"], [DESK, LOBBY], "never the old statement")
                self.assert_read(tid, sid, [DESK, LOBBY])
                self.assert_steady(tid, sid)

    def test_a_joined_an_older_copy_wrote_is_followed_by_a_statement_in_the_same_pass(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.write_own(sid, [self.old_joined(sid, alias="handy")])   # unstamped: an older copy's
        self.assertEqual(self.row_of(sid).channels, (DESK,), "restated by the pass that reads it")
        self.assertEqual(threads.in_effect(self.own(sid))["kind"], "joined")
        self.assert_read(tid, sid, [DESK])
        self.assert_steady(tid, sid)

    def test_the_empty_set_is_stated_over_a_log_that_states_another(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[]), r.pop("began", None)))
        self.reconcile()
        self.assertEqual(self.statements(sid)[-1]["channels"], [])
        self.assert_read(tid, sid, [])
        self.assert_steady(tid, sid)

    def test_a_thread_in_no_channel_with_nothing_stated_needs_no_statement(self):
        sid, _, tid = self.member()
        self.assert_steady(tid, sid)
        self.assertEqual(self.statements(sid), [])
        self.assert_read(tid, sid, [], elsewhere=False)

    def test_with_channels_registered_and_no_set_nothing_is_compared(self):
        """No thread here is in a channel and no log states one: the reconciliation's last step makes no
        comparison and calls nothing."""
        self.member()
        self.seated()
        with mock.patch.object(threads, "set_channels", side_effect=AssertionError("set_channels")), \
                mock.patch.object(channels, "restate", side_effect=AssertionError("restate")), \
                mock.patch.object(sminos, "_keep_sets", side_effect=AssertionError("the comparison was made")):
            self.reconcile()
            sminos.forget_caches()
            sminos.view_of(self.p)

    def test_another_machines_statement_is_not_restated_here(self):
        sid, _, tid = self.member()
        remote = "6b000001-0000-4000-8000-0000000000b1"
        w = "other/" + remote
        sminos.log_append(self.p, w, "joined", session=remote, alias="faraway", name_source="user", machine="other",
                          cwd="/d", worktree="", role="", seat="", by="")
        sminos.log_append(self.p, w, "channels", session=remote, thread="t-remote", op="e1", channels=[DESK])
        sminos.forget_caches()
        with mock.patch.object(threads, "set_channels", side_effect=AssertionError("set_channels")):
            self.reconcile()
        self.assertEqual(self.row_of(remote).channels, (DESK,))

    # ---------------------------------------------------- overtaken, and a wake in flight

    def overtaken(self, meanwhile):
        """A reconciliation that read a difference ([DESK, LOBBY] in the record, [DESK] in the log), with
        `meanwhile()` run between its read and its call."""
        real, ran = channels.restate, []

        def restate(*a, **k):
            if not ran:
                ran.append(True)
                meanwhile()
            return real(*a, **k)
        with mock.patch.object(channels, "restate", side_effect=restate):
            self.reconcile()
        self.assertTrue(ran, "the reconciliation noticed the difference")

    def test_a_reconciliation_overtaken_by_a_removal_states_nothing(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))
        self.overtaken(lambda: self.assertEqual(channels.change(tid, LOBBY, "remove", sid).state, "applied"))
        said = [s["channels"] for s in self.statements(sid)]
        self.assertEqual(said, [[DESK], [DESK]], "the removal's statement, and no older set's")
        self.assert_read(tid, sid, [DESK])

    def test_a_reconciliation_overtaken_by_a_move_states_nothing_in_the_project_left(self):
        other = self.project_of(self.repo("other"))
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))

        def move():
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
                code, out = self.cli("join", other.name)
            self.assertEqual(code, 0, out)
        self.overtaken(move)
        self.assertEqual([s["channels"] for s in self.statements(sid)], [[DESK]], "nothing in the project left")
        self.reconcile(other)
        self.assertEqual([s["channels"] for s in self.statements(sid, other)], [[DESK, LOBBY]])
        self.assert_read(tid, sid, [DESK, LOBBY], p=other)

    def test_a_reconciliation_overtaken_by_the_destinations_join_before_the_retirement_states_nothing(self):
        """The window _reconcile allows (a dual membership of one tick): the project moved to joins the session
        before the project left retires it. The pass of the project left, which read its difference before,
        writes nothing there: the session's newest joined is the other project's."""
        other = self.project_of(self.repo("other"))
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))

        def destination_first():
            sminos.write_override(sid, other.id)
            self.reconcile(other)   # joins it there; the project left's retirement is its own pass's, paused
            self.assertTrue(self.is_member(sid, other) and self.is_member(sid), "a member of both, for now")
        self.overtaken(destination_first)
        self.assertEqual([s["channels"] for s in self.statements(sid)], [[DESK]], "nothing in the project left")
        self.assertEqual([s["channels"] for s in self.statements(sid, other)], [[DESK, LOBBY]],
                         "stated where it is now, by that project's own pass")
        self.reconcile()
        self.assertFalse(self.is_member(sid), "retired from the project left")
        self.assertEqual([s["channels"] for s in self.statements(sid)], [[DESK]])
        self.assert_read(tid, sid, [DESK, LOBBY], p=other)

    def test_a_join_back_inside_that_window_is_restated_where_the_session_is(self):
        """The project moved to joins it before the project left retires it, and the session joins back to the
        first inside that window: `join` retires it from the other and writes no new joined here, where its
        membership is still in effect. A joined the other's retirement ended competes with nothing: the next
        pass here states the record's set, and the one after that is steady."""
        other = self.project_of(self.repo("other"))
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))
        sminos.write_override(sid, other.id)
        sminos.forget_caches()
        with mock.patch.object(channels, "restate", return_value=False):
            self.reconcile(other)   # the destination first; its own statement aside
        self.assertTrue(self.is_member(sid, other) and self.is_member(sid), "a member of both, for now")
        joins = len(self.joins(sid))
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("join", self.p.name)
        self.assertEqual(code, 0, out)
        self.assertFalse(self.is_member(sid, other), "retired from the other")
        self.assertEqual(threads.in_effect(self.own(sid, other))["project"], self.p.id, "moved back here")
        self.assertEqual(len(self.joins(sid)), joins, "no new joined here: its membership stayed in effect")
        self.assertEqual(sminos.last_project(sid).id, self.p.id)
        self.reconcile()
        self.assertEqual(self.statements(sid)[-1]["channels"], [DESK, LOBBY], "stated where it is")
        self.assert_read(tid, sid, [DESK, LOBBY])
        self.assert_steady(tid, sid)

    def test_a_reconciliation_overtaken_by_a_rename_of_the_machine_states_nothing(self):
        """The writer's identity is read as it is at the write, not from the invocation's cache: a machine
        renamed between the read and the write writes under no writer the thread no longer has."""
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))
        renamed = mock.patch.dict(os.environ, {"DAEMON_HOST": "renamedhost"})
        self.overtaken(renamed.start)   # this process's identity stays cached as it was read
        renamed.stop()
        self.assertEqual([s["channels"] for s in self.statements(sid)], [[DESK]], "nothing written")
        self.reconcile()
        self.assertEqual(self.statements(sid)[-1]["channels"], [DESK, LOBBY], "the next pass states it")

    def test_a_wake_in_flight_leaves_the_difference_to_the_next_pass(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))
        n = len(self.statements(sid))
        # This process's own wake of the thread: the hold is never the operation's.
        hold, _ = sminos.wake_lock(tid, holder="a wake")
        try:
            self.reconcile()
            self.assertEqual(len(self.statements(sid)), n)
            self.assertIsNotNone(sminos.wake_held(tid), "the wake's own hold is still live")
        finally:
            hold.release()
        # Another's (a thread of this process stands in for another process: its own descriptor, its own flock).
        taken, let_go = threading.Event(), threading.Event()

        def wake():
            h, _ = sminos.wake_lock(tid, holder="pid 1 since then")
            taken.set()
            let_go.wait(30)
            h.release()
        t = threading.Thread(target=wake)
        t.start()
        try:
            self.assertTrue(taken.wait(10))
            began = time.time()
            self.reconcile()
            self.assertLess(time.time() - began, sminos.SWEEP_WAIT, "the lock is tried, not waited for")
            self.assertEqual(len(self.statements(sid)), n)
        finally:
            let_go.set()
            t.join()
        self.reconcile()
        self.assertEqual(self.statements(sid)[-1]["channels"], [DESK, LOBBY], "the next pass states it")
        self.assert_read(tid, sid, [DESK, LOBBY])

    # ---------------------------------------------------- a session that comes to be another thread's

    def test_a_former_session_that_runs_again_holds_an_empty_set_and_no_positions(self):
        old, oproc, tid = self.member()
        self.add(tid, old, DESK)
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.session(sid=old, started=ms_ago(-1))
        self.reconcile()
        mine = threads.thread_of(old)
        self.assertNotEqual(mine["thread"], tid)
        self.assertEqual((mine["channels"], mine.get("began"), mine.get("answered")), ([], None, None))
        self.assertEqual(channels.channels_of(old), ())
        self.assertEqual(self.row_of(old).channels, (), "the log states nothing for it")
        self.assert_read(tid, job, [DESK], elsewhere=False)


class Idle(Life, T1.Sessions):
    """The idle cost (the holder's ruling): on a machine where no channel is registered, the reconciliation
    looks up no thread's set at all, not only compares none."""
    REGISTER = False

    def test_a_machine_with_no_channel_looks_up_no_holder(self):
        self.member()
        self.seated()
        with mock.patch.object(threads, "set_holders", side_effect=AssertionError("the holders were looked up")), \
                mock.patch.object(sminos, "_keep_sets", side_effect=AssertionError("the comparison was made")):
            for _ in range(2):
                self.reconcile()
                sminos.forget_caches()
                sminos.view_of(self.p)
        self.register()   # a channel registered: the lookup is made again
        self.assertEqual(sminos.channels_here(), True)

    def test_a_listing_that_fails_for_a_moment_is_not_kept(self):
        """The registrations' directory stats but cannot be listed for a moment: the gate does not keep a "no
        channel" it never read, and once the directory lists again it answers what is there."""
        self.register()
        root, real = sminos.projects_root(), os.listdir

        def listdir(path="."):
            if path == root:
                raise OSError(5, "Input/output error")
            return real(path)
        with mock.patch.object(os, "listdir", listdir):
            self.assertTrue(sminos.channels_here(), "unknown is no answer of none: the holders are looked up")
        self.assertTrue(sminos.channels_here(), "the same generation, the directory listing again")
        sminos.forget_caches()
        self.assertTrue(sminos.channels_here(), "and the next")


class KeptOnAStream(Life, T1.Hub):
    """A change of reach: the session's own events move to its audience stream and back, each `joined` there
    beginning a membership that has stated nothing."""

    def test_a_change_of_reach_and_back_is_restated_under_each_writer(self):
        vis = sminos.sibling_module("sminos_visibility")
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        plain = sminos.writer_id(sid)
        self.assertEqual(self.statements(sid)[-1]["writer"], plain)
        self.private(sid)
        with self.quiet():
            vis.snapshot(sid, self.p)
            self.reconcile()
        [(stream, evs)] = self.streams(sid).items()
        said = [e for e in evs if e["kind"] == "channels"]
        self.assertEqual([(s["channels"], s["writer"]) for s in said], [([DESK], stream)])
        self.assertEqual(self.row_of(sid).channels, (DESK,))
        records.set_policy(sid, lambda a, shares: ("org-view", shares))
        with self.quiet():
            vis.snapshot(sid, self.p)
            self.reconcile()
        last = [e for e in self.plain(sid) if e["kind"] in ("joined", "channels")][-2:]
        self.assertEqual([(e["kind"], e.get("channels")) for e in last], [("joined", None), ("channels", [DESK])],
                         "back on the plain writer, stated after its new joined")
        self.assert_read(tid, sid, [DESK], elsewhere=False)


    def test_a_writer_whose_joined_is_not_written_yet_is_left_to_a_later_pass(self):
        """Its own events go under its stream now, and its `joined` there is not written yet: a statement
        there would state nothing, and one under the old writer would be under a writer it no longer writes
        under; nothing is written, pass after pass, until the snapshot lands."""
        vis = sminos.sibling_module("sminos_visibility")
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.raw(tid, lambda r: (r.update(channels=[DESK, LOBBY]), r["began"].update({LOBBY: {}})))
        self.private(sid)
        n = len(self.plain(sid))
        with self.quiet():
            for _ in range(3):
                self.reconcile()
        self.assertEqual((len(self.plain(sid)), self.streams(sid)), (n, {}), "nothing written")
        with self.quiet():
            vis.snapshot(sid, self.p)
            self.reconcile()
        [(stream, evs)] = self.streams(sid).items()
        self.assertEqual([e["channels"] for e in evs if e["kind"] == "channels"], [[DESK, LOBBY]])


# ------------------------------------------------------------ an end and a return (C6, C7)


class Returns(Life, T1_ended.Ending):
    def test_a_seat_ended_and_returned_by_its_human_writes_its_positions_anew(self):
        sid, proc, seat_id = self.seated()
        self.end(proc)
        self.reconcile()
        self.touch(DESK)
        self.add(seat_id, sid, DESK)
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        t = threads.get(seat_id)
        self.assertTrue(threads.record_ended(t))
        self.assertEqual((t["channels"], t["began"]), ([DESK], {DESK: {"beta/human": 1}}))
        self.touch(DESK, to=[{"session": sid, "alias": "w"}])
        self.live(sid=sid, name="w")
        self.reconcile()
        t = threads.get(seat_id)
        self.assertIsNone(t.get("ended"))
        self.assertEqual(t["began"], {DESK: {"beta/human": 2}})
        self.assertEqual(self.statements(sid)[-1]["channels"], [DESK])
        self.assert_read(seat_id, sid, [DESK], elsewhere=False)

    def test_an_end_keeps_the_set_and_its_positions_and_a_return_writes_them_anew(self):
        sid = self.closed()
        tid = threads.stamp(sid)
        self.touch(DESK)
        self.add(tid, sid, DESK, LOBBY)
        before = threads.get(tid)["began"]
        self.assertEqual(before, {DESK: {"beta/human": 1}, LOBBY: {}})
        self.stopped_since(sid, 2 * T1_ended.PERIOD)
        self.sweep()
        t = threads.get(tid)
        self.assertTrue(threads.record_ended(t))
        self.assertEqual((t["channels"], t["began"]), ([DESK, LOBBY], before), "an end touches neither")
        # While it is ended, its channels' logs gain: events addressed to it among them.
        self.touch(DESK, text="while ended", to=[{"session": sid, "alias": "alpha"}])
        self.touch(LOBBY, writer="gamma/human", to=[{"session": sid, "alias": "alpha"}])
        self.touch(LOBBY, writer="gamma/human")
        self.live(sid=sid, name="alpha")
        self.reconcile()
        t = threads.get(tid)
        self.assertIsNone(t.get("ended"), "returned")
        self.assertEqual(t["began"], {DESK: {"beta/human": 2}, LOBBY: {"gamma/human": 2}},
                         "the log's positions at the return, past what reached it while it was ended")
        joins = [e for e in self.own(sid) if e["kind"] in ("joined", "retired", "channels")]
        self.assertEqual([e["kind"] for e in joins][-2:], ["joined", "channels"], "restated after its new joined")
        self.assertEqual(joins[-1]["channels"], [DESK, LOBBY])
        self.assert_read(tid, sid, [DESK, LOBBY], elsewhere=False)

    def test_a_channels_log_that_cannot_be_read_at_a_return_keeps_its_old_position(self):
        """The holder's ruling ("A return over an unreadable channel log"): the return is committed, the
        channel whose log raises keeps its earlier position, the others are written anew, and it is said once,
        in daemon.log."""
        sid = self.closed()
        tid = threads.stamp(sid)
        self.touch(DESK)
        self.touch(LOBBY, writer="gamma/human")
        self.add(tid, sid, DESK, LOBBY)
        self.stopped_since(sid, 2 * T1_ended.PERIOD)
        self.sweep()
        self.touch(DESK)
        self.touch(LOBBY, writer="gamma/human")
        real, asked = sminos.channel_positions, []

        def positions(cid):
            asked.append(cid)
            if cid == DESK:
                raise sminos.PositionsUnread("the log of channel %s could not be listed: EIO" % cid[:8])
            return real(cid)
        self.live(sid=sid, name="alpha")
        err = io.StringIO()
        with mock.patch.object(sminos, "channel_positions", positions), contextlib.redirect_stderr(err):
            self.reconcile()
            self.reconcile()
        t = threads.get(tid)
        self.assertIsNone(t.get("ended"), "the return is committed")
        self.assertEqual(t["began"], {DESK: {"beta/human": 1}, LOBBY: {"gamma/human": 2}},
                         "the unreadable channel's position from before its end, the other's anew")
        self.assertIn(DESK, asked)
        with open(os.path.join(sminos.root(), "daemon.log")) as f:
            said = [line for line in f if "keeps where its membership" in line]
        self.assertEqual(len(said), 1, "said once")
        self.assertIn(DESK[:8], said[0])
        self.assertNotIn(LOBBY[:8], said[0])
        self.assertNotIn("keeps where its membership", err.getvalue(), "and only there")


class ClearKept(Life, T1_stopped.Clear):
    def test_the_thread_left_keeps_its_set_and_the_new_one_states_none(self):
        self.add(self.tid, self.old, DESK)
        self.note()
        self.start()
        self.reconcile()
        left = threads.get(self.tid)
        self.assertEqual((left["current"], left["channels"]), (self.old, [DESK]))
        self.assertEqual(self.row_of(self.old).channels, (DESK,), "stopped, and still in its channels")
        new = threads.thread_of(self.NEW)
        self.assertNotEqual(new["thread"], self.tid)
        self.assertEqual((new["channels"], new.get("began")), ([], None))
        self.assertEqual(self.row_of(self.NEW).channels, ())
        self.assertEqual(self.statements(self.NEW), [], "the new thread needs no statement")
        self.assertEqual(channels.channels_of(self.NEW), ())


# ------------------------------------------------------------ an absorption (C9)


class Absorbed(Life, T1.LateHandOff):
    def staged(self, own=(DESK,), theirs=(LOBBY,), seat=False):
        old, job, tid, theirs_id = self.late(seat=seat)
        if own:
            self.add(tid, old, *own)
        if theirs:
            self.add(theirs_id, job, *theirs)
        return old, job, tid, theirs_id

    def said(self):
        try:
            with open(os.path.join(sminos.root(), "daemon.log")) as f:
                return [line for line in f if "past the limit" in line]
        except FileNotFoundError:
            return []

    def test_the_continuing_thread_takes_the_absorbed_records_channels_after_its_own(self):
        for seat in (False, True):
            with self.subTest(seat=seat):
                self.fresh()
                self.register()
                self.touch(DESK)
                self.touch(LOBBY, writer="gamma/human")
                self.touch(LOBBY, writer="gamma/human")
                old, job, tid, theirs = self.late(seat=seat)
                self.add(tid, old, DESK, ROOM)
                self.touch(LOBBY, writer="gamma/human")
                self.add(theirs, job, LOBBY, DESK)
                mine, brought = threads.get(tid)["began"], threads.get(theirs)["began"]
                self.reconcile()
                self.assert_absorbed(old, job, tid, theirs)
                t = threads.get(tid)
                self.assertEqual(t["channels"], [DESK, ROOM, LOBBY], "its own, then those it lacks")
                self.assertEqual(t["began"], {DESK: mine[DESK], ROOM: mine[ROOM], LOBBY: brought[LOBBY]},
                                 "its own positions kept, the absorbed record's for each channel brought")
                self.assertEqual(brought[LOBBY], {"gamma/human": 3})
                self.assertEqual(self.statements(job)[-1]["channels"], [DESK, ROOM, LOBBY], "the reconciliation states it")
                self.assert_read(tid, job, [DESK, ROOM, LOBBY], elsewhere=False)
                self.assertEqual(self.said(), [])

    def test_the_answered_requests_are_united(self):
        old, job, tid, theirs = self.late()
        at = sminos.now(ms=True)

        def answer(thread, sid, rid, chans):
            entry = threads.set_channels(thread, lambda rec: {
                "project": self.p, "session": sid, "channels": chans,
                "answer": {"channel": DESK, "id": rid, "ts": at, "result": "applied", "reason": None}})
            self.assertIsNotNone(entry)
            sminos.finish_thread(thread)
        answer(tid, old, "r1", [DESK])
        answer(theirs, job, "r2", [DESK])
        answer(theirs, job, "r1", [DESK])
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        self.assertEqual([a[:2] for a in threads.get(tid)["answered"]], [[DESK, "r1"], [DESK, "r2"]],
                         "both, one entry per request")

    def test_the_answered_requests_united_are_oldest_first(self):
        old, job, tid, theirs = self.late()

        def answer(thread, sid, rid, at):
            self.assertIsNotNone(threads.set_channels(thread, lambda rec: {
                "project": self.p, "session": sid, "channels": [DESK],
                "answer": {"channel": DESK, "id": rid, "ts": at, "result": "applied", "reason": None}}))
            sminos.finish_thread(thread)
        answer(tid, old, "r1", T1_ended.ago(40))
        answer(theirs, job, "r2", T1_ended.ago(30))
        answer(tid, old, "r3", T1_ended.ago(20))
        answer(theirs, job, "r4", T1_ended.ago(10))
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        self.assertEqual([a[1] for a in threads.get(tid)["answered"]], ["r1", "r2", "r3", "r4"],
                         "oldest first, the two ledgers' interleaved")

    def full(self):
        """A continuing record at 126 channels, the job's record bringing two it may take and one it may not."""
        old, job, tid, theirs = self.late()
        own = channel_ids(126)
        self.raw(tid, lambda r: r.update(channels=own, began={c: {} for c in own}))
        self.add(theirs, job, DESK, own[0], LOBBY, ROOM)
        return old, job, tid, theirs, own

    def test_the_notice_of_an_addition_past_the_limit_survives_a_cut(self):
        """The notice is written with the merge, before its write lands: a cut after the write leaves it said
        once, and a cut before the write lands says it again at the replay, which merges once."""
        for cut, said in (("after", 1), ("before", 2)):
            with self.subTest(cut=cut):
                self.fresh()
                self.register()
                old, job, tid, theirs, own = self.full()
                killer = self.kill_after_merge() if cut == "after" else self.kill_at_merge_write()
                with killer, self.assertRaises(Killed):
                    self.reconcile()
                self.reconcile()
                self.assert_absorbed(old, job, tid, theirs)
                self.assertEqual(threads.get(tid)["channels"], own + [DESK, LOBBY])
                lines = self.said()
                self.assertEqual(len(lines), said)
                self.assertTrue(all(ROOM[:8] in line for line in lines))

    def kill_at_merge_write(self):
        """The process dies inside the merge's write, its change made and not yet written."""
        real = threads._change

        def change(tid, mutate, *a, **k):
            if mutate.__name__ == "merge":
                def dies(view, raw):
                    mutate(view, raw)
                    raise Killed()
                return real(tid, dies, *a, **k)
            return real(tid, mutate, *a, **k)
        return mock.patch.object(threads, "_change", side_effect=change)

    def test_an_addition_past_the_limit_is_dropped_and_said(self):
        old, job, tid, theirs = self.late()
        own = channel_ids(126)
        self.raw(tid, lambda r: r.update(channels=own, began={c: {} for c in own}))
        self.add(theirs, job, DESK, own[0], LOBBY, ROOM)
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        t = threads.get(tid)
        self.assertEqual(t["channels"], own + [DESK, LOBBY], "up to 128")
        self.assertNotIn(ROOM, t["began"])
        [line] = self.said()
        self.assertIn(ROOM[:8], line)

    def test_an_absorption_cut_at_each_step_merges_once(self):
        for cut in ("begin", "merge", "retirement", "delete", "clear"):
            with self.subTest(cut=cut):
                self.fresh()
                self.register()
                old, job, tid, theirs = self.late()
                self.add(tid, old, DESK)
                self.add(theirs, job, LOBBY)
                if cut == "begin":
                    killer = self.kill_after_begin()
                elif cut == "merge":
                    killer = self.kill_after_merge()
                elif cut == "retirement":
                    killer = self.kill_before_event("joined", job)
                else:
                    killer = self.kill_at_change(cut)
                with killer, self.assertRaises(Killed):
                    self.reconcile()
                self.reconcile()
                self.assert_absorbed(old, job, tid, theirs)
                self.assert_finished(tid, (old, job))
                t = threads.get(tid)
                self.assertEqual((t["channels"], sorted(t["began"])), ([DESK, LOBBY], sorted([DESK, LOBBY])))
                self.assertEqual(self.statements(job)[-1]["channels"], [DESK, LOBBY])

    def kill_after_merge(self):
        """The process dies right after the absorption's merge is written."""
        real = threads._change

        def change(tid, mutate, *a, **k):
            got = real(tid, mutate, *a, **k)
            if mutate.__name__ == "merge":
                raise Killed()
            return got
        return mock.patch.object(threads, "_change", side_effect=change)

    def test_a_job_in_no_channel_brings_none(self):
        old, job, tid, theirs = self.staged(theirs=())
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        self.assertEqual(threads.get(tid)["channels"], [DESK])
        self.assert_read(tid, job, [DESK], elsewhere=False)


if __name__ == "__main__":
    unittest.main()
