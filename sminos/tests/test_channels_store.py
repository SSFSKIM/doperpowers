#!/usr/bin/env python3
"""A thread's declared set: one durable operation, its statement and the
statement's reader (CH1's M2: docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md,
the milestone's "Proves"; Interfaces §2 to §5).

- The reader (C2): the statement in effect folded from hand-written logs —
  one before its writer's `joined`, one under another writer than the
  `joined`'s, one after a `retired`, two, one with an empty list, ids that
  are no channel's, a 129th id, a `joined` after a statement — through the
  projection and every row's `Member.channels`.
- Rows C1 and C2 through `sminos_channels.change`, for both kinds of thread,
  live and stopped: the record's set, where each membership began, the one
  statement in the thread's own project and what every reader takes from
  it; a decide given a record changed between its caller's read and the
  lock; the set already reading so; the limit; each `failed` and why; what
  `set_channels` refuses as the caller's error.
- Where a membership began: an empty log, one with other writers' events,
  one already holding events addressed to the thread, a removal, and, as a
  statement of the accepted rule and no guarantee of an order, an event
  imported between the positions' read and the record's write ending past
  them.
- The journal: a cut after the record's write, and one after the
  statement's append before the entry is cleared, each finished by this
  code's next reconciliation with one statement; an answer's `answered`
  kept and pruned; a cut followed by a `join` to another project, the
  statement landing in the project left; a finish that cannot be had after
  the commit, the change still applied.
- What the operation reads under the lock creates nothing and takes no lock
  (a cold audience stream); a move landing while the positions are read is
  never committed past (the membership read last); a channel log there
  that cannot be read writes nothing.
- The wake: a thread's own change that times out on the wake lock fails and
  a quiet tick after it changes nothing; a launch paused before it records
  its job and a `resume` paused between its check and its stop, each with
  the operation attempted meanwhile from another process and from the
  caller that holds the wake lock, which writes nothing and leaves the wake
  as it would have been (the engine's processes and launches, the job and
  its grace, the caller's hold).
- `update` refuses the three keys; `list --json` holds neither `began` nor
  `answered`.

The older copies' finishers of the same cut are test-older-cli.sh's.
Hermetic: test_threads.Machine (HOME and SMINOS_HOME temporary, sessions
`sleep`s with engine records the test writes); the wake cases on
test_wake_delivery.Deliveries, the test engine first on PATH.
Run: python3 -B sminos/tests/test_channels_store.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import fcntl
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

from test_threads import Killed, Machine, sminos, threads  # noqa: E402
from test_wake import wait_for  # noqa: E402
from test_wake_delivery import Deliveries  # noqa: E402
import sminos_channels as channels  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
HUB = {"url": "http://127.0.0.1:9", "org": "org-1"}
DESK = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"     # channels (version 8)
LOBBY = "0123abcd-4567-8abc-a123-456789abcdef"
ROOM = "0123abce-4567-8abc-a123-456789abcdef"
REMOTE = "6b000001-0000-4000-8000-0000000000b1"   # another machine's session


def channel_ids(n):
    """n distinct channel ids."""
    return ["%08x-0000-8000-8000-000000000000" % i for i in range(1, n + 1)]


class Store(Machine):
    """A local project and channels registered here as the org's directory registers a log."""

    def setUp(self):
        super().setUp()
        for cid, name in ((DESK, "desk"), (LOBBY, "lobby"), (ROOM, "room")):
            sminos.register_if_absent(sminos.make_project(cid, name, "", "", HUB))
        sminos.forget_caches()

    def chan(self, cid):
        return sminos.known_project(cid)

    def human(self, root=None):
        """A live session its human opened, joined on sight: (thread id, session, process)."""
        sid, proc = self.session(root=root)
        self.reconcile(self.project_of(root) if root else None)
        t = threads.thread_of(sid)
        self.assertEqual(t["opened"], "human")
        return t["thread"], sid, proc

    def spawned(self):
        """A live session given a seat (`seat add --session`): (thread id, session, process)."""
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        t = threads.thread_of(sid)
        self.assertEqual(t["opened"], "spawned")
        return t["thread"], sid, proc

    def statements(self, sid, p=None):
        return [e for e in self.own(sid, p) if e["kind"] == "channels"]

    def member(self, sid, p=None):
        sminos.forget_caches()
        return next((m for m in sminos.view_of(p or self.p).members if m.session == sid), None)

    def raw(self, tid, mutate):
        """The record's stored object changed in place, under its store lock (another writer, or a hand edit)."""
        def change(view, raw):
            mutate(raw)
            return True
        self.assertTrue(threads._change(tid, change))
        sminos.forget_caches()

    def append(self, cid, writer, kind="channel-env", **fields):
        e = sminos.log_append(self.chan(cid), writer, kind, **fields)
        sminos.forget_caches()
        return e


# ------------------------------------------------------------ the reader (C2, §5)


def ev(writer, seq, kind, session, ms, **fields):
    if kind == "channels":   # a statement's other required fields (§2), unless a case says otherwise
        fields = {"thread": "t-remote", "op": "e%d" % seq, **fields}
    return {"ts": "2026-11-21T10:00:%02d.%03dZ" % (ms // 1000, ms % 1000), "writer": writer, "seq": seq,
            "kind": kind, "session": session, **fields}


def joined(writer, seq, session, ms):
    return ev(writer, seq, "joined", session, ms, alias="faraway", name_source="user", machine="other", cwd="/d",
              worktree="", role="", seat="", by="")


class Reader(unittest.TestCase):
    W = "other/" + REMOTE
    STREAM = "other/%s~0123456789abcdef" % REMOTE

    def stated(self, events):
        return threads.stated_set(sminos._projection(events)[REMOTE]["stated"])

    def test_the_statement_in_effect_follows_its_writers_joined_in_effect(self):
        W, S = self.W, self.STREAM
        cases = {
            "a statement after its writer's joined": ([joined(W, 1, REMOTE, 1), ev(W, 2, "channels", REMOTE, 2,
                                                                                  channels=[DESK])], (DESK,)),
            "a statement before its writer's joined": ([ev(W, 1, "channels", REMOTE, 1, channels=[DESK]),
                                                        joined(W, 2, REMOTE, 2)], ()),
            "under another writer than the joined's": ([joined(W, 1, REMOTE, 1), ev(S, 1, "channels", REMOTE, 2,
                                                                                     channels=[DESK])], ()),
            "after a retired": ([joined(W, 1, REMOTE, 1), ev(W, 2, "retired", REMOTE, 2, reason="retire", by=""),
                                 ev(W, 3, "channels", REMOTE, 3, channels=[DESK])], ()),
            "a retired after it": ([joined(W, 1, REMOTE, 1), ev(W, 2, "channels", REMOTE, 2, channels=[DESK]),
                                    ev(W, 3, "retired", REMOTE, 3, reason="moved", project="")], ()),
            "two statements, the later": ([joined(W, 1, REMOTE, 1), ev(W, 2, "channels", REMOTE, 2, channels=[DESK]),
                                           ev(W, 3, "channels", REMOTE, 3, channels=[LOBBY, DESK])], (LOBBY, DESK)),
            "one with an empty list": ([joined(W, 1, REMOTE, 1), ev(W, 2, "channels", REMOTE, 2, channels=[DESK]),
                                        ev(W, 3, "channels", REMOTE, 3, channels=[])], ()),
            "a joined after it (a writer reused)": ([joined(W, 1, REMOTE, 1),
                                                     ev(W, 2, "channels", REMOTE, 2, channels=[DESK]),
                                                     joined(W, 3, REMOTE, 3)], ()),
            "ids that are no channel's, and one twice": ([joined(W, 1, REMOTE, 1), ev(
                W, 2, "channels", REMOTE, 2, channels=["7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d", DESK, 8, None, "desk",
                                                       DESK, LOBBY])], (DESK, LOBBY)),
            "a statement whose channels is no list": ([joined(W, 1, REMOTE, 1), ev(W, 2, "channels", REMOTE, 2,
                                                                                    channels=DESK)], ()),
            "another session's statement": ([joined(W, 1, REMOTE, 1), ev(
                "other/6b000002-0000-4000-8000-0000000000b2", 1, "channels", REMOTE, 2, channels=[DESK])], ()),
        }
        for why, (events, want) in cases.items():
            with self.subTest(why):
                self.assertEqual(self.stated(events), want)

    def test_an_event_missing_a_statements_fields_is_none_and_leaves_the_one_in_effect(self):
        W = self.W
        valid = [joined(W, 1, REMOTE, 1), ev(W, 2, "channels", REMOTE, 2, channels=[DESK])]
        malformed = {"no channels": {"channels": None}, "channels no list": {"channels": DESK},
                     "no thread": {"thread": None}, "an empty thread": {"thread": ""}, "no op": {"op": None},
                     "an op of another type": {"op": 7}}
        for why, wrong in malformed.items():
            with self.subTest(why):
                bad = ev(W, 3, "channels", REMOTE, 3, channels=[LOBBY])
                for k, v in wrong.items():
                    if v is None:
                        bad.pop(k)
                    else:
                        bad[k] = v
                self.assertEqual(self.stated(valid + [bad]), (DESK,), "no statement: the valid one stays")
        self.assertEqual(self.stated(valid + [ev(W, 3, "channels", REMOTE, 3, channels=[])]), (),
                         "a valid empty list is a statement of no channel")

    def test_a_129th_id_is_not_read(self):
        ids = channel_ids(129)
        events = [joined(self.W, 1, REMOTE, 1), ev(self.W, 2, "channels", REMOTE, 2, channels=ids)]
        self.assertEqual(self.stated(events), tuple(ids[:128]))
        self.assertEqual(threads.stated_set(None), ())


class Rows(Store):
    def test_every_row_takes_its_membership_from_the_log(self):
        w = "other/" + REMOTE
        sminos.log_append(self.p, w, "joined", session=REMOTE, alias="faraway", name_source="user", machine="other",
                          cwd="/d", worktree="", role="", seat="", by="")
        self.assertEqual(self.member(REMOTE).channels, (), "a writer that has stated nothing states no channel")
        sminos.log_append(self.p, w, "channels", session=REMOTE, thread="t-remote", op="e1", channels=[DESK, LOBBY])
        m = self.member(REMOTE)
        self.assertEqual(m.channels, (DESK, LOBBY))
        self.assertEqual(m.status, "", "a statement is no status line")
        sminos.log_append(self.p, w, "channels", session=REMOTE, thread="t-remote", op="e2", channels=[])
        self.assertEqual(self.member(REMOTE).channels, ())


# ------------------------------------------------------------ rows C1 and C2 (§3)


class OwnChange(Store):
    def assert_states(self, tid, sid, want, n):
        t = threads.get(tid)
        self.assertEqual((t["channels"], t.get("pending")), (want, None))
        said = self.statements(sid)
        self.assertEqual(len(said), n, "one statement for each change")
        last = said[-1]
        self.assertEqual((last["channels"], last["thread"], last["writer"], set(last) - {"ts", "writer", "seq"}),
                         (want, tid, sminos.writer_id(sid), {"kind", "session", "thread", "op", "channels"}),
                         "the whole set, under its writer, stamped, naming its op and nothing else")
        self.assertEqual(self.member(sid).channels, tuple(want), "what every reader takes")
        self.assertEqual(channels.channels_of(sid), tuple(want))

    def test_a_thread_adds_and_removes_itself(self):
        for kind in ("human", "spawned", "stopped"):
            with self.subTest(kind):
                if kind == "spawned":
                    tid, sid, _ = self.spawned()
                    with open(sminos.meta_path(tid)) as f:
                        gen = json.load(f).get("gen")
                else:
                    tid, sid, proc = self.human()
                    if kind == "stopped":
                        self.end(proc)   # its terminal closed: stopped, and still its thread's
                self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("applied", ""))
                self.assert_states(tid, sid, [DESK], 1)
                self.assertEqual(channels.change(tid, self.chan(LOBBY), "add", sid).state, "applied", "by its Project")
                self.assert_states(tid, sid, [DESK, LOBBY], 2)
                self.assertEqual(channels.change(tid, DESK, "remove", sid), channels.Outcome("applied", ""))
                self.assert_states(tid, sid, [LOBBY], 3)
                self.assertEqual(channels.change(tid, LOBBY, "remove", sid), channels.Outcome("applied", ""))
                self.assert_states(tid, sid, [], 4)
                self.assertNotIn("began", threads.get(tid), "an empty set has no positions")
                self.assertEqual(self.statements(sid)[-1]["channels"], [], "the empty set is stated")
                if kind == "spawned":
                    with open(sminos.meta_path(tid)) as f:
                        self.assertEqual(json.load(f).get("gen"), gen, "no lifecycle generation moved: a turn's "
                                         "watcher keeps its reply")

    def test_a_set_that_already_reads_so_writes_nothing_and_says_so(self):
        tid, sid, _ = self.human()
        channels.change(tid, DESK, "add", sid)
        before = (threads.get(tid), self.statements(sid))
        self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("applied", "unchanged"))
        self.assertEqual(channels.change(tid, LOBBY, "remove", sid), channels.Outcome("applied", "unchanged"))
        self.assertEqual((threads.get(tid), self.statements(sid)), before)

    def test_decide_reads_the_record_as_it_is_under_the_lock_not_as_its_caller_read_it(self):
        tid, sid, _ = self.human()
        self.assertEqual(threads.get(tid)["channels"], [], "the caller reads an empty set")
        real = sminos.wake_lock
        meanwhile = []

        def lock(thread_id, *a, **k):
            if thread_id == tid and not meanwhile:   # between the caller's read and the record's lock
                meanwhile.append(True)
                self.raw(tid, lambda r: r.update(channels=[LOBBY], began={LOBBY: {"w": 1}}))
            return real(thread_id, *a, **k)
        with mock.patch.object(sminos, "wake_lock", lock):
            self.assertEqual(channels.change(tid, DESK, "add", sid).state, "applied")
        t = threads.get(tid)
        self.assertEqual(t["channels"], [LOBBY, DESK], "added to the set as it was under the lock")
        self.assertEqual(t["began"][LOBBY], {"w": 1}, "a channel that stays keeps its positions")
        self.assertEqual(self.statements(sid)[-1]["channels"], [LOBBY, DESK])
        # A removal the record no longer needs by the lock: nothing is written.
        meanwhile.clear()
        real_lock = sminos.wake_lock

        def drop(thread_id, *a, **k):
            if thread_id == tid and not meanwhile:
                meanwhile.append(True)
                self.raw(tid, lambda r: r.update(channels=[DESK]))
            return real_lock(thread_id, *a, **k)
        n = len(self.statements(sid))
        with mock.patch.object(sminos, "wake_lock", drop):
            self.assertEqual(channels.change(tid, LOBBY, "remove", sid), channels.Outcome("applied", "unchanged"))
        self.assertEqual((threads.get(tid)["channels"], len(self.statements(sid))), ([DESK], n))

    def test_the_limit(self):
        tid, sid, _ = self.human()
        full = channel_ids(128)
        self.raw(tid, lambda r: r.update(channels=full))
        self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("refused", "limit"))
        self.assertEqual((threads.get(tid)["channels"], self.statements(sid)), (full, []))
        self.assertEqual(channels.change(tid, full[0], "remove", sid).state, "applied", "a removal still is")
        self.assertEqual(threads.get(tid)["channels"], full[1:])

    def test_what_cannot_be_recorded_fails_and_says_why(self):
        tid, sid, _ = self.human()
        before = threads.get(tid)
        # An open entry that cannot be finished.
        with mock.patch.object(sminos, "finish_thread", lambda *a, **k: False):
            self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("failed", "entry"))
        # One opened between the caller's finish and the lock.
        real = sminos.wake_lock

        def opened(thread_id, *a, **k):
            if thread_id == tid:
                self.raw(tid, lambda r: r.update(pending={"id": "e9", "op": "advance", "project": self.p.id,
                                                          "events": []}))
            return real(thread_id, *a, **k)
        with mock.patch.object(sminos, "wake_lock", opened):
            self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("failed", "entry"))
        self.raw(tid, lambda r: r.pop("pending"))
        # A session that is no longer the thread's, and none.
        self.assertEqual(channels.change(tid, DESK, "add", str(uuidlib.uuid4())), channels.Outcome("failed", "moved"))
        self.assertEqual(channels.change(tid, DESK, "add", ""), channels.Outcome("failed", "vacant"))
        code, out = self.cli("seat", "add", "g", "vacant")
        self.assertEqual(code, 0, out)
        vacant = next(s for s in sminos.seats() if s["alias"] == "vacant")["seat_id"]
        self.assertEqual(channels.change(vacant, DESK, "add", ""), channels.Outcome("failed", "vacant"))
        # Between two projects: a move whose destination's joined is not written yet.
        self.write_own(sid, [{"kind": "retired", "reason": "moved", "project": "", "thread": tid}])
        self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("failed", "between"))
        t = threads.get(tid)
        self.assertEqual((t["channels"], t.get("pending"), t.get("began")), (before["channels"], None, None))
        self.assertEqual(self.statements(sid), [], "nothing was recorded")

    def test_a_change_found_elsewhere_by_the_lock_is_written_where_the_session_is(self):
        other = self.project_of(self.repo("other"))
        tid, sid, _ = self.human()
        real = sminos.last_project
        stale = [True]

        def last(session):
            if stale and session == sid:   # read before the lock: the session's project as it was
                stale.clear()
                return other
            return real(session)
        with mock.patch.object(sminos, "last_project", last):
            self.assertEqual(channels.change(tid, DESK, "add", sid).state, "applied")
        self.assertEqual((len(self.statements(sid)), self.statements(sid, other)), (1, []))

    def test_a_change_set_channels_refuses_is_the_callers_error(self):
        tid, sid, _ = self.human()
        bad = {"a session that is not the record's": {"session": str(uuidlib.uuid4())},
               "129 ids": {"channels": channel_ids(129)},
               "an id twice": {"channels": [DESK, DESK]},
               "an element no id at all, and unhashable": {"channels": [DESK, [LOBBY]]},
               "an id that is no channel's": {"channels": ["7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"]},
               "a channel as the project": {"project": self.chan(DESK)},
               "an answer refused for no reason": {"answer": {"channel": DESK, "id": "r1", "ts": sminos.now(ms=True),
                                                              "result": "refused", "reason": None}}}
        for why, wrong in bad.items():
            with self.subTest(why):
                change = {"project": self.p, "session": sid, "channels": [DESK], "answer": None, **wrong}
                with self.assertRaises(ValueError):
                    threads.set_channels(tid, lambda rec: change)
                self.assertEqual((threads.get(tid)["channels"], threads.get(tid).get("pending")), ([], None))
        self.assertIsNone(threads.set_channels(tid, lambda rec: None), "decide's None writes nothing")


# ------------------------------------------------------------ what the operation reads, and when it stops


def forbidden(*a, **k):
    raise AssertionError("a read under the record's lock wrote or locked something")


class Reads(Store):
    def test_the_read_under_the_lock_of_a_cold_audience_stream_creates_nothing_and_takes_no_lock(self):
        tid, sid, _ = self.human()
        audience = ["member-1", "member-2"]
        stream = sminos.stream_writer(sminos.writer_id(sid), audience)
        sminos.keep_stream(self.p, stream, audience)
        with open(os.path.join(self.p.home, "log", stream.replace("/", ".") + ".jsonl"), "w") as f:
            f.write(json.dumps({"ts": sminos.now(ms=True), "writer": stream, "seq": 1, "kind": "titled",
                                "session": sid, "title": "under its stream"}) + "\n")
        sminos.forget_caches()   # cold: no home of this process's, no view, no stream read yet
        real, read = sminos._own_events, []

        def own(project, session, *a, **k):
            with mock.patch.object(sminos, "project_path", forbidden), mock.patch.object(os, "makedirs", forbidden), \
                    mock.patch.object(os, "mkdir", forbidden), mock.patch.object(fcntl, "flock", forbidden), \
                    mock.patch.object(sminos, "write_json", forbidden):
                got = real(project, session, *a, **k)
            read.append({e["writer"] for e in got})
            return got
        with mock.patch.object(sminos, "_own_events", own):
            self.assertEqual(channels.change(tid, DESK, "add", sid).state, "applied")
        self.assertIn(stream, set().union(*read), "the stream's file was read, as it is")

    def test_a_move_that_lands_while_the_positions_are_read_is_never_committed_past(self):
        other = self.project_of(self.repo("other"))
        for landed in ("between", "moved"):
            with self.subTest(landed):
                tid, sid, _ = self.human()
                real, moved = sminos.channel_positions, []

                def positions(cid):
                    got = real(cid)
                    if not moved:   # the move's `retired`, appended by another process during this read
                        moved.append(True)
                        dest = other.id if landed == "moved" else ""
                        self.write_own(sid, [{"kind": "retired", "reason": "moved", "project": dest, "thread": tid}])
                        if landed == "moved":
                            self.write_own(sid, [self.old_joined(sid, alias="mover", thread=tid)], p=other)
                    return got
                with mock.patch.object(sminos, "channel_positions", positions):
                    got = channels.change(tid, DESK, "add", sid)
                if landed == "between":
                    self.assertEqual(got, channels.Outcome("failed", "between"))
                    t = threads.get(tid)
                    self.assertEqual((t["channels"], t.get("pending"), t.get("began")), ([], None, None),
                                     "nothing written")
                    self.assertEqual(self.statements(sid), [])
                else:
                    self.assertEqual(got, channels.Outcome("applied", ""), "looked for again, and found there")
                    self.assertEqual((self.statements(sid), len(self.statements(sid, other))), ([], 1),
                                     "stated in the project it moved to, never in the one it left")

    def test_a_channel_log_that_cannot_be_read_writes_nothing(self):
        tid, sid, _ = self.human()
        self.append(DESK, "beta/human", op="add", machine="beta", thread="x")
        self.assertEqual(sminos.channel_positions("%08x-0000-8000-8000-000000000000" % 9), {}, "not registered: {}")
        self.assertEqual(sminos.channel_positions(LOBBY), {}, "a log that holds nothing yet: {}")

        def unreadable(f):
            raise OSError(5, "Input/output error")
        said = []
        with mock.patch.object(sminos, "_last_seq", unreadable), mock.patch.object(sminos, "warn", said.append):
            self.assertEqual(channels.change(tid, DESK, "add", sid), channels.Outcome("failed", "unreadable"))
        log = os.path.join(self.chan(ROOM).home, "log")
        if os.path.isdir(log):
            os.rmdir(log)
        with open(log, "w") as f:
            f.write("not a directory")
        with mock.patch.object(sminos, "warn", said.append):
            self.assertEqual(channels.change(tid, ROOM, "add", sid), channels.Outcome("failed", "unreadable"))
        self.assertEqual(len(said), 2, "each said once")
        t = threads.get(tid)
        self.assertEqual((t["channels"], t.get("pending"), t.get("began")), ([], None, None), "no partial boundary")
        self.assertEqual(self.statements(sid), [])
        self.assertEqual(channels.change(tid, DESK, "add", sid).state, "applied", "once it reads, it is made")
        self.assertEqual(channels.began_of(tid, DESK), {"beta/human": 1})

    def test_a_finish_that_cannot_be_had_after_the_commit_keeps_it_applied(self):
        tid, sid, _ = self.human()
        real, nudged = sminos.finish_thread, []

        def finish(thread_id, *a, **k):
            if (threads.get(thread_id) or {}).get("pending"):
                raise sminos.LockBusy("the finisher lock is busy")
            return real(thread_id, *a, **k)
        said = []
        with mock.patch.object(sminos, "finish_thread", finish), mock.patch.object(sminos, "warn", said.append), \
                mock.patch.object(sminos, "nudge_daemon", lambda: nudged.append(True)):
            got = channels.change(tid, DESK, "add", sid)
        self.assertIn("left to the next reconciliation", said[0])
        self.assertEqual((got, nudged), (channels.Outcome("applied", ""), [True]), "committed, said so, nudged")
        self.assertEqual((threads.get(tid)["channels"], threads.get(tid)["pending"]["op"], self.statements(sid)),
                         ([DESK], "channels", []), "the entry left for the replay")
        self.reconcile()
        self.assertEqual((len(self.statements(sid)), threads.get(tid).get("pending")), (1, None))


# ------------------------------------------------------------ where a membership began (§4)


class Began(Store):
    def test_where_each_membership_began(self):
        tid, sid, _ = self.human()
        channels.change(tid, DESK, "add", sid)
        self.assertEqual(channels.began_of(tid, DESK), {}, "an empty log: nothing was held then")
        self.assertEqual(sminos.channel_positions(DESK), {})
        self.append(LOBBY, "beta/human", op="add", machine="beta", thread="x")
        self.append(LOBBY, "beta/human", op="add", machine="gamma", thread="x")
        self.append(LOBBY, "gamma/" + REMOTE, op="add", machine="beta", thread="y")
        channels.change(tid, LOBBY, "add", sid)
        self.assertEqual(channels.began_of(tid, LOBBY), {"beta/human": 2, "gamma/" + REMOTE: 1})
        self.assertEqual(channels.began_of(tid, DESK), {}, "a channel that stays keeps its own")
        # A log that already holds events addressed to the thread: those are before where it began.
        self.append(ROOM, "beta/human", "human", to=[{"session": sid, "alias": "x"}], text="early")
        self.append(ROOM, "beta/human", "human", to=[{"session": sid, "alias": "x"}], text="earlier")
        channels.change(tid, ROOM, "add", sid)
        self.assertEqual(channels.began_of(tid, ROOM), {"beta/human": 2})
        channels.change(tid, LOBBY, "remove", sid)
        self.assertIsNone(channels.began_of(tid, LOBBY), "a removal drops them")
        self.assertEqual(sorted(threads.get(tid)["began"]), sorted([DESK, ROOM]))
        self.append(LOBBY, "beta/human", op="remove", machine="beta", thread="x")
        channels.change(tid, LOBBY, "add", sid)
        self.assertEqual(channels.began_of(tid, LOBBY), {"beta/human": 3, "gamma/" + REMOTE: 1},
                         "an add after a removal begins where the log is then")
        self.assertIsNone(channels.began_of(tid, "%08x-0000-8000-8000-000000000000" % 7))
        for e in self.statements(sid):
            self.assertNotIn("began", json.dumps(e), "no position is written into a log")

    def test_an_event_imported_between_the_positions_read_and_the_write_counts_as_after_it(self):
        """The accepted rule (the constraints' list), stated and promising no order: no lock holds the channel's
        log still."""
        tid, sid, _ = self.human()
        self.append(DESK, "beta/human", op="add", machine="beta", thread="x")
        real, late = sminos.channel_positions, []

        def positions(cid):
            got = real(cid)
            if cid == DESK and not late:
                late.append(self.append(DESK, "beta/human", op="add", machine="gamma", thread="x"))
                late.append(self.append(DESK, "gamma/" + REMOTE, op="add", machine="beta", thread="y"))
            return got
        with mock.patch.object(sminos, "channel_positions", positions):
            self.assertEqual(channels.change(tid, DESK, "add", sid).state, "applied")
        began = channels.began_of(tid, DESK)
        self.assertEqual(began, {"beta/human": 1})
        self.assertGreater(late[0]["seq"], began["beta/human"])
        self.assertNotIn(late[1]["writer"], began, "a writer first seen after the read")


# ------------------------------------------------------------ the journal: a cut after the record's write


class Cut(Store):
    def cut(self, tid, sid, chans, answer=None, project=None):
        """set_channels' record write, and nothing after it: a process stopped before the statement."""
        entry = threads.set_channels(tid, lambda rec: {"project": project or self.p, "session": sid,
                                                       "channels": chans, "answer": answer})
        self.assertIsNotNone(entry)
        sminos.forget_caches()
        return entry

    def test_a_cut_after_the_records_write_is_finished_by_the_next_reconciliation_once(self):
        tid, sid, _ = self.human()
        self.append(DESK, "beta/human", op="add", machine="beta", thread="x")
        entry = self.cut(tid, sid, [DESK])
        t = threads.get(tid)
        self.assertEqual((t["channels"], t["began"], t["pending"]["op"], t["pending"]["project"]),
                         ([DESK], {DESK: {"beta/human": 1}}, "channels", self.p.id), "the record holds the change")
        self.assertEqual(list(t["pending"]["events"][0]), ["kind", "session", "thread", "channels"],
                         "its entry owes the statement and nothing else")
        self.assertEqual(self.statements(sid), [], "not yet stated")
        self.reconcile()
        [s] = self.statements(sid)
        self.assertEqual((s["op"], s["channels"], s["thread"]), (entry["id"], [DESK], tid))
        self.assertIsNone(threads.get(tid).get("pending"))
        self.reconcile()
        self.assertEqual(len(self.statements(sid)), 1, "and not twice")
        self.assertEqual(self.member(sid).channels, (DESK,))

    def test_a_cut_after_the_statements_append_is_finished_by_clearing_the_entry_with_no_second(self):
        tid, sid, _ = self.human()
        real = threads._change

        def change(thread_id, mutate, *a, **k):
            if thread_id == tid and mutate.__name__ == "clear":
                raise Killed()   # the process stops after the append, before the write that clears the entry
            return real(thread_id, mutate, *a, **k)
        with mock.patch.object(threads, "_change", change), self.assertRaises(Killed):
            channels.change(tid, DESK, "add", sid)
        sminos.forget_caches()
        entry = threads.get(tid)["pending"]
        self.assertEqual([s["op"] for s in self.statements(sid)], [entry["id"]], "appended, its entry still open")
        self.reconcile()
        self.assertIsNone(threads.get(tid).get("pending"), "the replay clears it")
        self.assertEqual([s["op"] for s in self.statements(sid)], [entry["id"]], "and appends nothing again")
        self.assertEqual(self.member(sid).channels, (DESK,))

    def test_an_answer_is_kept_once_and_pruned_once_its_request_could_no_longer_be_pending(self):
        tid, sid, _ = self.spawned()
        old = "2026-11-01T00:00:00.000Z"
        self.raw(tid, lambda r: r.update(answered=[[LOBBY, "r0", old], [LOBBY, "r1", sminos.now(ms=True)]]))
        at = sminos.now(ms=True)
        answer = {"channel": DESK, "id": "r2", "ts": at, "result": "applied", "reason": None}
        self.cut(tid, sid, [DESK], answer=answer)
        self.reconcile()
        t = threads.get(tid)
        self.assertEqual([a[1] for a in t["answered"]], ["r1", "r2"], "the expired entry dropped, the answer added")
        self.assertEqual(t["answered"][-1], [DESK, "r2", at])
        [s] = self.statements(sid)
        self.assertEqual((s["answers"], s["result"], "reason" in s), ({"channel": DESK, "id": "r2"}, "applied",
                                                                     False))
        refusal = {"channel": LOBBY, "id": "r3", "ts": at, "result": "refused", "reason": "limit"}
        self.cut(tid, sid, [DESK], answer=refusal)
        self.cut_finished()
        s = self.statements(sid)[-1]
        self.assertEqual((s["channels"], s["result"], s["reason"]), ([DESK], "refused", "limit"),
                         "a refusal carries the set unchanged")
        self.cut(tid, sid, [DESK], answer=dict(answer, ts=sminos.now(ms=True)))
        self.cut_finished()
        self.assertEqual([a[1] for a in threads.get(tid)["answered"]], ["r1", "r2", "r3"], "one entry per request")

    def cut_finished(self):
        self.reconcile()

    def test_a_cut_followed_by_a_join_states_in_the_project_left(self):
        other = self.project_of(self.repo("other"))
        tid, sid, _ = self.human()
        entry = self.cut(tid, sid, [DESK])
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("join", other.name)
        self.assertEqual(code, 0, out)
        self.reconcile()
        self.reconcile(other)
        [s] = self.statements(sid)
        self.assertEqual(s["op"], entry["id"], "in the project the entry names")
        self.assertEqual(self.statements(sid, other), [], "none in the project it moved to")
        self.assertEqual(threads.get(tid)["channels"], [DESK], "the record's set as written")
        self.assertEqual(self.member(sid, other).channels, (), "the project it moved to states nothing yet (M3)")


# ------------------------------------------------------------ the keys no other writer writes


class Keys(Store):
    def test_update_refuses_each_of_the_three_keys(self):
        tid, sid, _ = self.human()
        for key, value in (("channels", [DESK]), ("began", {}), ("answered", [])):
            with self.subTest(key):
                with self.assertRaises(ValueError):
                    threads.update(tid, {key: value})
                with self.assertRaises(ValueError):
                    threads.update(tid, {}, remove=(key,))
        self.assertEqual(threads.get(tid)["channels"], [])

    def test_list_json_holds_neither_began_nor_answered(self):
        for kind in ("human", "spawned"):
            with self.subTest(kind):
                tid, sid, _ = self.human() if kind == "human" else self.spawned()
                at = sminos.now(ms=True)
                threads.set_channels(tid, lambda rec: {"project": self.p, "session": sid, "channels": [DESK],
                                                       "answer": {"channel": DESK, "id": "r-" + kind, "ts": at,
                                                                  "result": "applied", "reason": None}})
                self.reconcile()
                self.assertIn("began", threads.get(tid))
                code, out = self.cli("list", "--json")
                self.assertEqual(code, 0, out)
                self.assertNotIn('"began"', out)
                self.assertNotIn('"answered"', out)
                self.assertNotIn("r-" + kind, out)


# ------------------------------------------------------------ the wake lock


class Wake(Store):
    def test_an_own_change_that_times_out_on_the_wake_lock_fails_and_a_quiet_tick_changes_nothing(self):
        for holder in (sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()), sminos.SWEEP_HOLD):
            with self.subTest(holder):
                tid, sid, _ = self.human()
                taken, release = threading.Event(), threading.Event()

                def hold():
                    h, _ = sminos.wake_lock(tid, holder=holder)
                    taken.set()
                    release.wait(10)
                    h.release()
                t = threading.Thread(target=hold)
                t.start()
                self.assertTrue(taken.wait(5))
                before = (threads.get(tid), self.own(sid))
                began = time.monotonic()
                got = channels.change(tid, DESK, "add", sid, lock_until=time.time() + 0.3)
                self.assertLess(time.monotonic() - began, 3)
                release.set()
                t.join(10)
                self.assertEqual(got, channels.Outcome("failed", "wake"))
                self.assertEqual((threads.get(tid), self.own(sid)), before, "nothing was recorded")
                code, out = self.cli("daemon", "tick")
                self.assertEqual(code, 0, out)
                self.assertEqual((threads.get(tid)["channels"], self.statements(sid)), ([], []),
                                 "no pass carries out a change no request records")


def change_elsewhere(tid, cid, sid):
    """The operation from another process, waiting half a second for the wake lock: its Outcome's fields."""
    code = ("import sys, time; sys.path.insert(0, sys.argv[1]); import sminos_channels as c; "
            "print(' '.join(c.change(sys.argv[2], sys.argv[3], 'add', sys.argv[4], lock_until=time.time() + 0.5)))")
    p = subprocess.run([sys.executable, "-B", "-c", code, SCRIPTS, tid, cid, sid], capture_output=True, text=True,
                       timeout=60)
    return p.stdout.strip() or p.stderr.strip()


class WakeInFlight(Deliveries):
    """The operation attempted while a wake holds the thread's wake lock, from the caller that holds it and from
    another process: it writes nothing, and the wake goes on as it would have (§3; the constraint "Lock order")."""

    def setUp(self):
        super().setUp()
        sminos.register_if_absent(sminos.make_project(DESK, "desk", "", "", HUB))
        sminos.forget_caches()

    def processes(self, sid):
        sminos.forget_caches()
        return len([r for r in sminos.peer_records() if r.get("sessionId") == sid and sminos.pid_alive(r.get("pid"))])

    def attempt(self, tid, sid):
        """Both attempts, made where the wake holds the lock: what each answered, and whether the hold is live after."""
        asked = []
        with self.assertRaises(sminos.WakeBusy, msg="the store's operation refuses its caller's hold itself"):
            threads.set_channels(tid, lambda rec: asked.append(rec))
        self.assertEqual(asked, [], "nothing decided under it")
        here = channels.change(tid, DESK, "add", sid)
        live = sminos.wake_held(tid) is not None
        there = change_elsewhere(tid, DESK, sid)
        return here, live, there

    def assert_nothing_written(self, tid, sid, seen):
        here, live, there = seen
        self.assertEqual(here, channels.Outcome("failed", "wake"), "the caller's own hold is never the operation's")
        self.assertTrue(live, "and the caller's hold is still live after it")
        self.assertEqual(there, "failed wake", "another process waits for it, and fails")
        t = threads.get(tid)
        self.assertEqual((t["channels"], t.get("pending"), t.get("began")), ([], None, None))
        self.assertEqual([e for e in sminos._own_events(self.p, sid) if e["kind"] == "channels"], [])

    def test_a_launch_paused_before_it_records_its_job(self):
        tid, sid = self.human_thread()
        real, seen, job = threads.wake_job, [], []

        def wake_job(thread_id, session, short, *a, **k):
            if thread_id == tid and not seen:
                seen.append(self.attempt(tid, sid))
                ok = real(thread_id, session, short, *a, **k)
                job.append((ok, short, threads.waking(threads.get(tid), sid).get("job")))
                return ok
            return real(thread_id, session, short, *a, **k)
        with mock.patch.object(threads, "wake_job", wake_job):
            got = self.wake(sid)
        self.assertTrue(got.live, got)
        self.assert_nothing_written(tid, sid, seen[0])
        [(ok, short, held)] = job
        self.assertTrue(ok, "the launch recorded its job")
        self.assertEqual((held["short"], bool(held["at"])), (short, True), "its job and the grace it starts")
        self.assertEqual(self.launches(), 1, "the engine's launch count: one")
        self.assertEqual(self.processes(sid), 1, "one process holds the session")

    def test_a_resume_paused_between_its_check_and_its_stop(self):
        tid, sid = self.human_thread()
        code, out = self.say("@%s first" % sid[:8])
        self.assertEqual(code, 0, out)
        self.assertTrue(wait_for(lambda: self.processes(sid) == 1))
        launched = self.launches()
        real_stop, real_job, seen, job = sminos.claude_stop, threads.wake_job, [], []

        def stop(short):
            if not seen:
                seen.append(self.attempt(tid, sid))
            return real_stop(short)

        def wake_job(thread_id, session, short, *a, **k):
            ok = real_job(thread_id, session, short, *a, **k)
            job.append((ok, short, threads.waking(threads.get(tid), sid).get("job")))
            return ok
        with mock.patch.object(sminos, "claude_stop", stop), mock.patch.object(threads, "wake_job", wake_job):
            code, out = self.cli("resume", sid[:8], "start over")
        self.assertEqual(code, 0, out)
        self.assertIn("(woken)", out)
        self.assert_nothing_written(tid, sid, seen[0])
        [(ok, short, held)] = job
        self.assertTrue(ok, "the wake after the stop recorded its job")
        self.assertEqual(held["short"], short)
        self.assertEqual(self.launches() - launched, 1, "the turn stopped is started again, once")
        self.assertTrue(wait_for(lambda: self.processes(sid) == 1), "one process holds the session")
        self.assertTrue(wait_for(lambda: sum(f.count("start over") for f in self.frames(sid)) == 1))


if __name__ == "__main__":
    unittest.main()
