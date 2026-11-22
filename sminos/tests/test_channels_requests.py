#!/usr/bin/env python3
"""Requests on one machine (CH1's M4: docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md,
the milestone's "Proves"; Interfaces §2, §3's rows C3 and C4, §6).

- §6's table, row by row, through `judge` and through `carry_out` and
  `carry_due`: each row's outcome, what is written for it (a statement
  that answers, applied or refused, or nothing), for both kinds of thread,
  live and stopped; the limit.
- Under the lock: each fact the second evaluation reads (the owners, the
  policy, the revocation set, the capability, the machine's identity, the
  session's membership) changed by another process after this one's caches
  were warmed, with no forget_caches between, the fresh value deciding;
  the read under the lock locking and writing nothing, on a stream whose
  writer file this process never read.
- Words: `deliver` and `refuse` handed in for a session, and for a session
  or a reach the thread no longer has, neither recorded; a second writer's
  request under an id the first writer's request used, arriving while the
  first one's question is outstanding, not carried out and not given that
  word.
- Order and identity: an earlier-sorting request imported while a carrier
  is paused after its read, the later one not carried out ahead of it, and
  (as a statement of the accepted rule) one imported between the last read
  and the record's write carried out as a later arrival; two terminals'
  requests queued for their writer's head, the first command cut after its
  append, the second waiting behind it; an operator's queued request
  carried out by the command and not again when it reaches the log; an add
  then a remove, and the reverse, carried by the command or the tick, the
  words in either order; two requests in two channels answered once each;
  a request read twice, and again after the thread changed session,
  project and reach, and after its record was absorbed; behind an open
  entry, and behind a wake in flight (another process's, and this one's);
  five requests from two requesters; two adds for the 128th place.
- The verbs at the CLI: `create` cut after its registration and run again,
  and `create` of a name whose channel was emptied, each bringing the
  channel back under its id; a session's `create` whose first membership
  could not be recorded exiting 1; the limit at `create` (before
  registration), at `add` for oneself and at `add` for another.

The verbs through the launcher are test-channels.sh's.
Hermetic: test_threads.Machine (HOME and SMINOS_HOME temporary, sessions
`sleep`s with engine records the test writes), the machine cut over to an
endpoint that is never run (daemon/identity.json) and whose kept welcome
lists `channels`.
Run: python3 -B sminos/tests/test_channels_requests.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import fcntl
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_channels_store import DESK, HUB, LOBBY, SCRIPTS, Store, channel_ids, sminos, threads  # noqa: E402
from test_channels_life import Life  # noqa: E402
import test_threads as T1  # noqa: E402
import sminos_audience as audience  # noqa: E402
import sminos_channels as channels  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402

O = channels.Outcome
OTHER = "6b000009-0000-4000-8000-0000000000b9"     # a session of another machine: the remote requester
SIGNER = {"kind": "machine", "keyId": "key-other"}
SAME_ID = "5a" * 16                               # one request id two writers use (§2: 32 lower-case hex digits)


def forbidden(*a, **k):
    raise AssertionError("a read under the record's lock wrote or locked something")


def merged(*a, **k):
    raise AssertionError("the channel's input was read and merged under the record's lock")


class Requests(Store):
    """Store, on a machine cut over to its endpoint, whose kept welcome lists `channels`."""

    def setUp(self):
        super().setUp()
        self.identity(sminos.host_name())
        self.p = self.project_of(self.root)
        audience.keep_capabilities(["channels"])
        sminos.forget_caches()

    def identity(self, name, former=None):
        os.makedirs(os.path.dirname(rl10.identity_path()), mode=0o700, exist_ok=True)
        sminos.write_json(rl10.identity_path(), {
            "org": HUB["org"], "hub": HUB["url"], "name": name, "former": former or {}, "ref": "machine-ref-1",
            "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)

    # -- writing requests as their writers would

    def request(self, cid, op, sid, tid, writer=None, rid=None, ts=None, **more):
        """A request in the channel's log, under `writer` (the machine's human writer by default)."""
        fields = {"op": op, "session": sid, "thread": tid, "id": rid or os.urandom(16).hex(), **more}
        if ts is not None:
            fields["ts"] = ts
        e = sminos.log_append(self.chan(cid), writer or sminos.writer_id(), "channel-request", **fields)
        time.sleep(0.002)   # one request a millisecond: the merged log's order is the order they were written
        return e

    def remote(self, cid, op, sid, tid, signer=SIGNER, **more):
        """A request another machine's session wrote, as an import stores it (with its `verified`)."""
        if signer is not None:
            more["verified"] = {"signer": signer}
        return self.request(cid, op, sid, tid, writer="other/" + OTHER, **more)

    def asked(self, sid):
        return {"session": sid, "reach": channels.reach_token(sid)}

    def words(self, cid, e, word, sid):
        return {channels.event_key(self.chan(cid), e): (word, self.asked(sid))}

    # -- reading what came of them

    def carry(self, cid, **kw):
        sminos.forget_caches()
        return {r["id"]: o for r, o in channels.carry_due(self.chan(cid), **kw)}

    def judge(self, cid, e, tid, **kw):
        sminos.forget_caches()
        c = self.chan(cid)
        _, reqs = channels.requests_of(c)
        return channels.judge(c, e, threads.get(tid), channels._earlier(reqs, e), **kw)

    def answers(self, sid, p=None):
        return [(s["answers"]["channel"], s["answers"]["id"], s["result"], s.get("reason"), tuple(s["channels"]))
                for s in self.statements(sid, p) if "answers" in s]

    def held(self, tid):
        return threads.get(tid).get("channels")

    def answered(self, tid):
        return [(a[0], a[1]) for a in threads.get(tid).get("answered") or []]

    def owners(self, sid, owners):
        self.record(sid, owners=owners)

    def record(self, sid, **fields):
        """The session's record rewritten whole with `fields`, as another process writes it."""
        path = records.record_path(sid)
        with open(path) as f:
            rec = json.load(f)
        rec.update(fields)
        sminos.write_json(path, rec)

    def bump(self, sid):
        """The session's reach changed: its policyRev moved."""
        rec = records.read(sid)
        self.record(sid, policyRev=int(rec.get("policyRev") or 0) + 1)

    def seat(self, alias):
        """A live session given a seat of its own alias: (thread id, session, process)."""
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", alias, "--session", sid)
        self.assertEqual(code, 0, out)
        return threads.thread_of(sid)["thread"], sid, proc

    def two(self):
        """A live human-opened thread and a second live session of this machine (a requester)."""
        tid, sid, proc = self.human()
        _, other, _ = self.human()
        return tid, sid, proc, other


# ------------------------------------------------------------ §6's table, row by row


class Table(Requests):
    def test_row_1_an_expired_request_is_ignored_and_never_carried(self):
        tid, sid, _ = self.human()
        old = self.request(DESK, "add", sid, tid, ts="2026-11-01T00:00:00.000Z")
        self.assertEqual(self.judge(DESK, old, tid), O("ignored", "expired"))
        self.assertEqual(self.carry(DESK), {})
        self.assertEqual(self.held(tid), [])
        self.assertEqual(self.statements(sid), [])

    def test_row_2_a_second_writers_request_under_a_used_id_is_not_carried_out_nor_given_the_word(self):
        """The first writer's question is outstanding (pending `endpoint`) when the second writer's request under
        its id arrives; the word for the first answers the first alone."""
        tid, sid, _, other = self.two()
        self.owners(other, ["member-other"])   # so the second writer's own request would need a word too
        first = self.remote(DESK, "add", sid, tid, rid=SAME_ID)
        self.assertEqual(self.carry(DESK), {SAME_ID: O("pending", "endpoint")})
        second = self.request(DESK, "remove", sid, tid, writer=sminos.writer_id(other), rid=SAME_ID)
        self.assertEqual(self.judge(DESK, second, tid), O("ignored", "duplicate"))
        words = {**self.words(DESK, first, "deliver", sid), **self.words(DESK, second, "deliver", sid)}
        got = [(r["writer"], o) for r, o in channels.carry_due(self.chan(DESK), words=words)]
        self.assertEqual(got, [(first["writer"], O("applied"))], "the second passed by: its id is answered")
        self.assertEqual(self.judge(DESK, second, tid), O("ignored", "duplicate"))
        self.assertEqual(self.held(tid), [DESK], "the first one's add, and not the second one's remove")
        self.assertEqual(self.answers(sid), [(DESK, SAME_ID, "applied", None, (DESK,))])
        self.assertEqual(self.carry(DESK, words=words), {}, "once")

    def test_row_3_a_request_that_names_no_thread_here_changes_neither_and_writes_nothing(self):
        tid, sid, proc = self.human()
        tid2, sid2, _ = self.human()
        cases = {
            "a thread unknown here": lambda: (sid, "f" * 32),
            "a session the thread never had": lambda: (sid2, tid),
        }
        for why, make in cases.items():
            with self.subTest(why):
                s, t = make()
                e = self.request(DESK, "add", s, t)
                self.assertEqual(self.judge(DESK, e, t) if threads.get(t) else O("ignored", "not-here"),
                                 O("ignored", "not-here"))
                self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "not-here"))
        # A session the thread had that is now another thread's current one: it would lend that thread's reach.
        self.raw(tid, lambda r: r.update(sessions=[sid2] + [x for x in r.get("sessions", []) if x != sid2]))
        lent = self.request(DESK, "add", sid2, tid)
        self.assertEqual(self.carry(DESK, also=[lent])[lent["id"]], O("ignored", "not-here"))
        # Lane B, and an ended thread. (Each pass judges a request anew: a thread back in lane A is named again.)
        records.set_controller(sid, "B")
        lane = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK, also=[lane])[lane["id"]], O("ignored", "not-here"))
        self.raw(tid2, lambda r: r.update(ended={"at": sminos.now(), "reason": "retire", "by": "", "pid": None}))
        gone = self.request(DESK, "add", sid2, tid2)
        self.assertEqual(self.carry(DESK, also=[gone])[gone["id"]], O("ignored", "not-here"))
        for t, s in ((tid, sid), (tid2, sid2)):
            self.assertEqual(threads.get(t).get("channels"), [])
            self.assertNotIn("answered", threads.get(t))
            self.assertEqual(self.statements(s), [])

    def test_row_4_a_request_read_twice_and_after_the_thread_moved_on_is_carried_out_once(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")})
        self.assertEqual(self.judge(DESK, e, tid), O("ignored", "answered"))
        self.assertEqual(self.carry(DESK, also=[e]), {e["id"]: O("ignored", "answered")})
        # The thread's reach changed, it went on in another session, in another project.
        self.bump(sid)
        _, later, _ = self.human()
        other = self.project_of(self.repo("elsewhere"))
        self.raw(tid, lambda r: r.update(current=later, sessions=[sid, later]))
        self.write_own(later, [self.old_joined(later, alias="later", thread=tid)], p=other)
        self.assertEqual(self.carry(DESK), {})
        self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "answered"))
        self.assertEqual(len(self.answers(sid)), 1)
        self.assertEqual(self.answers(later, other), [])
        # Its record absorbed (gone, its answers the continuing record's): the request names no thread here.
        os.unlink(threads._human_path(tid))
        sminos.forget_caches()
        self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "not-here"))

    def test_row_5_a_request_waits_behind_an_earlier_one_for_the_same_thread_and_channel(self):
        tid, sid, _ = self.human()
        first = self.remote(DESK, "add", sid, tid)   # waits for the endpoint's word
        mine = self.request(DESK, "remove", sid, tid)
        elsewhere = self.request(LOBBY, "add", sid, tid)
        self.assertEqual(self.judge(DESK, mine, tid), O("pending", "earlier"))
        self.assertEqual(self.carry(DESK), {first["id"]: O("pending", "endpoint"), mine["id"]: O("pending", "earlier")})
        self.assertEqual(self.carry(LOBBY), {elsewhere["id"]: O("applied")}, "another channel's are not ordered")
        self.assertEqual(self.held(tid), [LOBBY])
        # An earlier one that expired, or that names no thread here, holds nothing back.
        tid2, sid2, _ = self.human()
        self.request(DESK, "add", sid2, tid2, ts="2026-11-01T00:00:00.000Z")
        self.request(DESK, "add", sid, tid2)   # a session tid2 never had
        last = self.request(DESK, "add", sid2, tid2)
        self.assertEqual(self.carry(DESK)[last["id"]], O("applied"))

    def test_row_6_behind_an_open_entry_and_carried_out_after_it(self):
        tid, sid, _ = self.human()
        self.assertEqual(channels.change(tid, LOBBY, "add", sid).state, "applied")
        # An entry left open (a cut after a record's write), its finisher lock held meanwhile by another process.
        entry = {"id": "cut-entry", "op": "channels", "at": sminos.now(), "project": self.p.id,
                 "events": [{"kind": "channels", "session": sid, "thread": tid, "channels": [LOBBY]}]}
        self.raw(tid, lambda r: r.update(pending=entry))
        e = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.judge(DESK, e, tid), O("pending", "entry"))
        path = os.path.join(threads.store_dir(), ".finish", tid + ".lock")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            got = self.carry(DESK, lock_until=time.time() + 0.3)
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertEqual(got, {e["id"]: O("pending", "entry")})
        self.assertEqual(self.held(tid), [LOBBY])
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")}, "the entry finished first, then the request")
        self.assertEqual(self.held(tid), [LOBBY, DESK])
        self.assertNotIn("pending", threads.get(tid))

    def test_row_7_a_vacant_thread_and_one_between_two_projects_wait(self):
        tid, sid, _ = self.human()
        self.write_own(sid, [{"kind": "retired", "reason": "moved", "project": "", "thread": tid}])
        e = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "between")})
        self.write_own(sid, [self.old_joined(sid, alias="back", thread=tid)])
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")})
        self.raw(tid, lambda r: r.update(current=""))
        e2 = self.request(DESK, "remove", sid, tid)
        self.assertEqual(self.carry(DESK), {e2["id"]: O("pending", "vacant")})

    def test_rows_8_and_9_a_request_from_elsewhere_needs_the_capability_and_a_machine_that_admits_it(self):
        tid, sid, _ = self.human()
        e = self.remote(DESK, "add", sid, tid)
        audience.keep_capabilities([])
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "no-channels")})
        audience.keep_capabilities(["channels"])
        sminos.write_json(sminos.sibling_module("sminos_policy").policy_path(), {"read_only": True})
        self.assertEqual(self.carry(DESK), {e["id"]: O("refused", "read-only")})
        self.assertEqual(self.held(tid), [])
        self.assertEqual(self.answers(sid), [(DESK, e["id"], "refused", "read-only", ())])
        self.assertEqual(self.answered(tid), [(DESK, e["id"])])

    def test_row_10_this_machines_own_writer_of_the_same_owners_is_honoured_without_a_word(self):
        tid, sid, _, other = self.two()
        by_person = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {by_person["id"]: O("applied")})
        by_session = self.request(DESK, "remove", sid, tid, writer=sminos.writer_id(other))
        self.assertEqual(self.carry(DESK), {by_session["id"]: O("applied")})
        # Another person's session of this machine: its sender is verified, and the endpoint's word is needed.
        self.owners(other, ["member-other"])
        asked = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(other))
        self.assertEqual(self.carry(DESK), {asked["id"]: O("pending", "endpoint")})
        self.assertEqual(self.carry(DESK, words=self.words(DESK, asked, "deliver", sid)), {asked["id"]: O("applied")})
        self.assertEqual(self.held(tid), [DESK])

    def test_row_11_an_unverified_sender_is_refused_and_an_unreadable_revocation_set_waits(self):
        tid, sid, _ = self.human()
        cases = {"no verified key": None, "a legacy signer": {"kind": "legacy"}}
        for why, signer in cases.items():
            with self.subTest(why):
                e = self.remote(DESK, "add", sid, tid, signer=signer)
                got = self.carry(DESK, words=self.words(DESK, e, "deliver", sid))
                self.assertEqual(got, {e["id"]: O("refused", "not-reachable")}, "though the endpoint would deliver")
        with open(rl10.revoked_path(), "w") as f:
            f.write("not a set")
        e = self.remote(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK, words=self.words(DESK, e, "deliver", sid)), {e["id"]: O("pending",
                                                                                                    "unverifiable")})
        sminos.write_json(rl10.revoked_path(), {"version": 1, "devices": [], "members": [], "keys": ["key-other"]})
        self.assertEqual(self.carry(DESK, words=self.words(DESK, e, "deliver", sid)), {e["id"]: O("refused",
                                                                                                    "not-reachable")})
        self.assertEqual(self.held(tid), [])
        self.assertEqual([a[2:4] for a in self.answers(sid)], [("refused", "not-reachable")] * 3)

    def test_rows_12_14_and_15_the_endpoints_word(self):
        tid, sid, _ = self.human()
        e = self.remote(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "endpoint")}, "no word yet")
        self.assertEqual(self.carry(DESK, words=self.words(DESK, e, "refuse", sid)), {e["id"]: O("refused",
                                                                                                   "not-reachable")})
        e2 = self.remote(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK, words=self.words(DESK, e2, "deliver", sid)), {e2["id"]: O("applied")})
        self.assertEqual(self.answers(sid), [(DESK, e["id"], "refused", "not-reachable", ()),
                                             (DESK, e2["id"], "applied", None, (DESK,))])

    def test_row_13_a_word_for_a_session_or_a_reach_the_thread_no_longer_has_is_dropped(self):
        tid, sid, _ = self.human()
        _, later, _ = self.human()
        for word in ("deliver", "refuse"):
            with self.subTest(word):
                said = len(self.statements(sid))
                e = self.remote(DESK, "add", sid, tid)
                stale_session = {channels.event_key(self.chan(DESK), e): (word, self.asked(later))}
                self.assertEqual(self.carry(DESK, words=stale_session), {e["id"]: O("pending", "moved")})
                kept = self.asked(sid)
                self.bump(sid)
                stale_reach = {channels.event_key(self.chan(DESK), e): (word, kept)}
                self.assertEqual(self.carry(DESK, words=stale_reach), {e["id"]: O("pending", "moved")})
                self.assertEqual(len(self.statements(sid)), said, "neither recorded")
                self.assertEqual(self.carry(DESK, words=self.words(DESK, e, word, sid))[e["id"]].state,
                                 "applied" if word == "deliver" else "refused", "asked again, and answered")
                self.assertEqual(self.carry(DESK), {})
                if word == "deliver":
                    self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")

    def test_the_limit_binds_an_honoured_request_with_a_refusing_statement(self):
        tid, sid, _ = self.human()
        full = channel_ids(128)
        self.raw(tid, lambda r: r.update(channels=full))
        add = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {add["id"]: O("refused", "limit")})
        self.assertEqual(self.held(tid), full)
        self.assertEqual(self.answers(sid)[-1][2:4], ("refused", "limit"))
        drop = self.request(DESK, "remove", sid, tid)
        self.assertEqual(self.carry(DESK), {drop["id"]: O("applied", "unchanged")}, "a remove of what is not there")
        self.assertEqual(self.answers(sid)[-1][2], "applied")

    def test_two_adds_for_the_128th_place_the_first_carried_takes_it(self):
        tid, sid, _ = self.human()
        self.raw(tid, lambda r: r.update(channels=channel_ids(127)))
        a, b = self.request(DESK, "add", sid, tid), self.request(LOBBY, "add", sid, tid)
        self.assertEqual(self.carry(LOBBY), {b["id"]: O("applied")})
        self.assertEqual(self.carry(DESK), {a["id"]: O("refused", "limit")})
        self.assertEqual(len(self.held(tid)), 128)
        self.assertIn(LOBBY, self.held(tid))

    def test_both_kinds_of_thread_live_and_stopped(self):
        for kind in ("human", "spawned"):
            for state in ("live", "stopped"):
                with self.subTest(kind=kind, state=state):
                    tid, sid, proc = self.human() if kind == "human" else self.seat("w-" + state)
                    if state == "stopped":
                        self.end(proc)
                    e = self.request(DESK, "add", sid, tid)
                    self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("applied"))
                    self.assertEqual(threads.get(tid)["channels"], [DESK])
                    self.assertEqual(self.member(sid).channels, (DESK,), "every reader takes the set")
                    self.assertIn(DESK, threads.get(tid)["began"])
                    r = self.request(DESK, "remove", sid, tid)
                    self.assertEqual(self.carry(DESK, also=[r])[r["id"]], O("applied"))
                    self.assertEqual(self.member(sid).channels, ())
                    self.assertNotIn("began", threads.get(tid), "a removal drops where the membership began")


# ------------------------------------------------------------ the second evaluation, under the lock


class UnderTheLock(Requests):
    def meanwhile(self, change):
        """threads.set_channels with `change` made just before it, as another process would make it: after the
        first evaluation, with this process's caches warm and no forget_caches."""
        real = threads.set_channels

        def paused(*a, **k):
            change()
            return real(*a, **k)
        return mock.patch.object(threads, "set_channels", paused)

    def carry_warm(self, cid, **kw):
        sminos.forget_caches()
        sminos.host_name(), sminos.enrollment()   # the invocation's cached identity, warm
        return {r["id"]: o for r, o in channels.carry_due(self.chan(cid), **kw)}

    def test_each_fact_changed_by_another_process_is_read_fresh(self):
        policy = sminos.sibling_module("sminos_policy")
        cases = {
            "the owners": ("person", lambda sid: self.owners(sid, ["member-new"]), O("pending", "endpoint")),
            "the policy": ("remote", lambda sid: sminos.write_json(policy.policy_path(), {"read_only": True}),
                           O("refused", "read-only")),
            "the revocation set": ("remote", lambda sid: sminos.write_json(rl10.revoked_path(), {
                "version": 2, "devices": [], "members": [], "keys": ["key-other"]}), O("refused", "not-reachable")),
            "the capability": ("remote", lambda sid: audience.keep_capabilities([]), O("pending", "no-channels")),
            # Renamed: a session's writer under the old name is no longer one same_owner_local vouches for, so
            # its request, this machine's own by its receipt, takes the endpoint's word.
            "the machine's identity": ("session", lambda sid: self.identity("renamed", {"testhost": [sid]}),
                                       O("pending", "endpoint")),
            "the session's membership": ("person", lambda sid: self.write_own(sid, [
                {"kind": "retired", "reason": "moved", "project": ""}]), O("pending", "between")),
        }
        for why, (by, change, want) in cases.items():
            with self.subTest(why):
                try:
                    self.fresh_case(by, change, want)
                finally:   # undone for the next case, whatever came of this one
                    self.identity("testhost")
                    for path in (policy.policy_path(), rl10.revoked_path()):
                        with contextlib.suppress(FileNotFoundError):
                            os.unlink(path)
                    audience.keep_capabilities(["channels"])
                    sminos.forget_caches()

    def fresh_case(self, by, change, want):
        tid, sid, _ = self.human()
        if by == "session":
            _, other, _ = self.human()
            e = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(other))
        else:
            e = self.remote(DESK, "add", sid, tid) if by == "remote" else self.request(DESK, "add", sid, tid)
        words = self.words(DESK, e, "deliver", sid) if by == "remote" else None
        first = self.judge(DESK, e, tid, word="deliver" if words else None, asked=self.asked(sid))
        self.assertEqual(first, O("applied"), "the first evaluation would carry it out")
        with self.meanwhile(lambda: change(sid)):
            got = self.carry_warm(DESK, words=words, wake_until=time.time())
        self.assertEqual(got.get(e["id"]), want)
        self.assertEqual(self.held(tid), [])
        self.assertEqual([a[2:4] for a in self.answers(sid)],
                         [tuple(want)] if want.state == "refused" else [], "the fresh value decided")

    def test_the_read_under_the_lock_locks_and_writes_nothing_on_a_cold_stream(self):
        """Nor does it read or merge the channel's input there: its files' signature alone is compared."""
        tid, sid, _ = self.human()
        aud = ["member-1", "member-2"]
        stream = sminos.stream_writer(sminos.writer_id(sid), aud)
        sminos.keep_stream(self.p, stream, aud)
        with open(os.path.join(self.p.home, "log", stream.replace("/", ".") + ".jsonl"), "w") as f:
            f.write(json.dumps({"ts": sminos.now(ms=True), "writer": stream, "seq": 1, "kind": "titled",
                                "session": sid, "title": "under its stream"}) + "\n")
        e = self.remote(DESK, "add", sid, tid)
        words = self.words(DESK, e, "deliver", sid)
        sminos.forget_caches()   # cold: no stream of the thread's read by this process yet
        real, decided = threads.set_channels, []

        def guarded(thread_id, decide, **k):
            def inner(rec):
                with mock.patch.object(sminos, "project_path", forbidden), \
                        mock.patch.object(os, "makedirs", forbidden), mock.patch.object(os, "mkdir", forbidden), \
                        mock.patch.object(fcntl, "flock", forbidden), mock.patch.object(sminos, "write_json", forbidden), \
                        mock.patch.object(channels, "requests_of", merged), mock.patch.object(sminos, "_store_whole", merged), \
                        mock.patch.object(sminos, "queued_operators", merged):
                    got = decide(rec)
                decided.append(got)
                return got
            return real(thread_id, inner, **k)
        with mock.patch.object(threads, "set_channels", guarded):
            got = {r["id"]: o for r, o in channels.carry_due(self.chan(DESK), words=words)}
        self.assertEqual(got, {e["id"]: O("applied")})
        self.assertTrue(decided and decided[-1] is not None)


# ------------------------------------------------------------ order and identity


class Order(Requests):
    def test_an_earlier_sorting_request_imported_while_the_carrier_is_paused_is_not_overtaken(self):
        tid, sid, _ = self.human()
        mine = self.request(DESK, "add", sid, tid)
        earlier_ts = "%s.000Z" % time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 60))
        real = threads.set_channels
        imported = []

        def paused(*a, **k):
            if not imported:   # another process imports a request stamped before this one
                imported.append(self.remote(DESK, "remove", sid, tid, ts=earlier_ts))
            return real(*a, **k)
        with mock.patch.object(threads, "set_channels", paused):
            got = channels.carry_out(self.chan(DESK), mine)
        self.assertEqual(got, O("pending", "earlier"))
        self.assertEqual(self.held(tid), [])
        self.assertEqual(self.statements(sid), [])

    def test_one_imported_between_the_last_read_and_the_write_is_carried_out_as_a_later_arrival(self):
        """The accepted rule, stated: no lock holds the channel's log still."""
        tid, sid, _ = self.human()
        mine = self.request(DESK, "add", sid, tid)
        earlier_ts = "%s.000Z" % time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 60))
        real, imported = sminos.channel_positions, []

        def during(cid):
            got = real(cid)
            if not imported:
                imported.append(self.remote(DESK, "remove", sid, tid, ts=earlier_ts))
            return got
        with mock.patch.object(sminos, "channel_positions", during):
            self.assertEqual(channels.carry_out(self.chan(DESK), mine), O("applied"))
        self.assertTrue(imported)
        self.assertEqual(self.held(tid), [DESK])
        self.assertEqual(self.carry(DESK, words=self.words(DESK, imported[0], "deliver", sid)),
                         {imported[0]["id"]: O("applied")}, "then the one stamped before it, carried after it")
        self.assertEqual(self.held(tid), [])

    def test_an_add_then_a_remove_and_the_reverse_whichever_path_and_whatever_order_the_words_came(self):
        for first, then, want in (("add", "remove", []), ("remove", "add", [DESK])):
            for order in ("in order", "reversed"):
                with self.subTest(first=first, words=order):
                    tid, sid, _ = self.human()
                    if first == "remove":
                        self.assertEqual(channels.change(tid, DESK, "add", sid).state, "applied")
                    a, b = self.remote(DESK, first, sid, tid), self.remote(DESK, then, sid, tid)
                    wa, wb = self.words(DESK, a, "deliver", sid), self.words(DESK, b, "deliver", sid)
                    if order == "in order":
                        self.assertEqual(self.carry(DESK, words=wa), {a["id"]: O("applied"), b["id"]: O("pending",
                                                                                                           "endpoint")})
                        self.assertEqual(self.carry(DESK, words=wb), {b["id"]: O("applied")})
                    else:
                        self.assertEqual(self.carry(DESK, words=wb), {a["id"]: O("pending", "endpoint"),
                                                                       b["id"]: O("pending", "earlier")})
                        self.assertEqual(self.carry(DESK, words={**wa, **wb}), {a["id"]: O("applied"),
                                                                                b["id"]: O("applied")})
                    self.assertEqual(self.held(tid), want)
        # One carried by the daemon's tick, the other by a command.
        tid, sid, _ = self.human()
        a = self.request(DESK, "add", sid, tid)
        sminos.forget_caches()
        daemon.channel_pass([self.chan(DESK)], sminos.seats())
        self.assertEqual(self.held(tid), [DESK], "the tick carried the add")
        b = self.request(DESK, "remove", sid, tid)
        self.assertEqual(self.carry(DESK, also=[b]), {b["id"]: O("applied")})
        self.assertEqual(self.held(tid), [])
        self.assertEqual([x[1] for x in self.answers(sid)], [a["id"], b["id"]])

    def test_two_requests_in_two_channels_are_each_answered_once_by_its_statement(self):
        tid, sid, _ = self.human()
        a, b = self.request(DESK, "add", sid, tid), self.request(LOBBY, "add", sid, tid)
        self.assertEqual(self.carry(LOBBY), {b["id"]: O("applied")})
        self.assertEqual(self.carry(DESK), {a["id"]: O("applied")})
        self.assertEqual(self.carry(DESK), {})
        self.assertEqual(self.carry(LOBBY), {})
        self.assertEqual(self.answers(sid), [(LOBBY, b["id"], "applied", None, (LOBBY,)),
                                             (DESK, a["id"], "applied", None, (LOBBY, DESK))])
        self.assertEqual(sorted(self.answered(tid)), sorted([(DESK, a["id"]), (LOBBY, b["id"])]))

    def test_five_requests_for_one_thread_from_two_requesters(self):
        tid, sid, _, other = self.two()
        made = []
        for i, op in enumerate(("add", "remove", "add", "remove", "add")):
            made.append(self.request(DESK, op, sid, tid, writer=sminos.writer_id(other) if i % 2 else None))
        got = [(r["id"], o) for r, o in channels.carry_due(self.chan(DESK))]
        self.assertEqual(got, [(e["id"], O("applied")) for e in made])
        self.assertEqual(self.held(tid), [DESK])
        self.assertEqual([x[1] for x in self.answers(sid)], [e["id"] for e in made])
        self.assertEqual(self.carry(DESK), {})

    def test_behind_a_wake_in_flight_another_processes_and_this_ones(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, tid)
        taken, done = threading.Event(), threading.Event()

        def wake():   # another process's wake (a thread of its own here: its own hold of the lock's file)
            hold, _ = sminos.wake_lock(tid, holder=sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()))
            taken.set()
            done.wait(10)
            hold.release()
        t = threading.Thread(target=wake)
        t.start()
        try:
            self.assertTrue(taken.wait(5))
            self.assertEqual(self.carry(DESK, wake_until=time.time()), {e["id"]: O("pending", "wake")})
            self.assertEqual(self.carry(DESK, also=[e], wake_until=time.time() + 0.2)[e["id"]], O("pending", "wake"))
        finally:
            done.set()
            t.join()
        hold, _ = sminos.wake_lock(tid)   # a wake of the thread under way in this process
        try:
            self.assertEqual(channels.carry_out(self.chan(DESK), e), O("pending", "wake"))
        finally:
            hold.release()
        self.assertEqual(self.statements(sid), [])
        self.assertEqual(self.carry(DESK, wake_until=time.time()), {e["id"]: O("applied")})


CHILD = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
import sminos, sminos_rl10 as rl10
project, sid, old = sminos.known_project(sys.argv[2]), sys.argv[3], sys.argv[4]
path = rl10.identity_path()
with open(path) as f:
    ident = json.load(f)
ident.update(name="renamed", former={old: [sid]})
sminos.write_json(path, ident, mode=0o600)
sminos.forget_caches()
writer = "renamed/" + sid
sminos.log_append(project, writer, "joined", session=sid, alias="moved-on", name_source="user", machine="renamed",
                  cwd="/d", worktree="", role="", seat="", by="", session_kind="interactive")
sminos._append(project, writer, [{"kind": "retired", "session": sid, "reason": "moved", "project": ""}])
"""


class Renamed(Requests):
    """Another process renames the machine and, under the new name, moves the session out of its project while
    a carrier that read the old name is paused: the locked membership checks choose the writer files by the
    identity as its file says now, so the old name's standing `joined` never lets the write through."""

    def rename_and_move(self, sid):
        subprocess.run([sys.executable, "-B", "-c", CHILD, SCRIPTS, self.p.id, sid, sminos.host_name()],
                       check=True, env=dict(os.environ), timeout=60)

    def staged(self):
        tid, sid, _ = self.human()
        e = self.remote(DESK, "add", sid, tid)
        words = self.words(DESK, e, "deliver", sid)
        sminos.forget_caches()
        self.assertEqual(sminos.host_name(), "testhost", "the carrier's cached identity, warm")
        return tid, sid, e, words

    def test_paused_before_the_lock(self):
        tid, sid, e, words = self.staged()
        real = threads.set_channels

        def paused(*a, **k):
            if not os.path.exists(os.path.join(self.p.home, "log", "renamed.%s.jsonl" % sid)):
                self.rename_and_move(sid)
            return real(*a, **k)
        with mock.patch.object(threads, "set_channels", paused):
            got = {r["id"]: o for r, o in channels.carry_due(self.chan(DESK), words=words)}
        self.assertEqual(got, {e["id"]: O("pending", "between")})
        self.assertEqual(threads.get(tid)["channels"], [])
        self.assertEqual(self.statements(sid), [])

    def test_paused_inside_the_write_before_its_last_guard(self):
        """The journal's own last guard (set_channels), after decide has passed."""
        tid, sid, e, words = self.staged()
        real, done = sminos.channel_positions, []

        def during(cid):
            got = real(cid)
            if not done:
                done.append(True)
                self.rename_and_move(sid)
            return got
        with mock.patch.object(sminos, "channel_positions", during):
            got = channels.carry_out(self.chan(DESK), e, *words[channels.event_key(self.chan(DESK), e)])
        self.assertTrue(done)
        self.assertEqual(got, O("pending", "between"))
        self.assertEqual(threads.get(tid)["channels"], [])
        self.assertNotIn("pending", threads.get(tid))
        self.assertEqual(self.statements(sid), [])


class Absorbed(Life, T1.LateHandOff):
    """A request a provisional record answered, replayed after a real absorption (M3's fixture, T1's late
    hand-off): the continuing thread holds the answer, and the request, naming the record absorbed, names no
    thread here and is carried out for neither."""

    def test_an_answered_request_replayed_after_the_absorption(self):
        audience.keep_capabilities(["channels"])
        old, job, tid, theirs = self.late()
        c = self.chan(DESK)
        e = sminos.log_append(c, "other/" + OTHER, "channel-request", op="add", session=job, thread=theirs,
                              id="be" * 16, verified={"signer": SIGNER})
        words = {channels.event_key(c, e): ("deliver", {"session": job, "reach": channels.reach_token(job)})}
        sminos.forget_caches()
        self.assertEqual({r["id"]: o for r, o in channels.carry_due(c, words=words)},
                         {e["id"]: O("applied")})
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        t = threads.get(tid)
        self.assertIn(DESK, t["channels"])
        self.assertIn([DESK, e["id"]], [a[:2] for a in t["answered"]])
        said = len(self.statements(job))
        sminos.forget_caches()
        self.assertEqual(channels.carry_due(c, words=words), [], "passed by: the record it names is gone")
        self.assertEqual(channels.carry_out(c, e, *words[channels.event_key(c, e)]), O("ignored", "not-here"))
        self.assertEqual(len(self.statements(job)), said, "nothing written for either thread")
        self.assertEqual(threads.get(tid)["channels"].count(DESK), 1)


# ------------------------------------------------------------ the verbs at the CLI


class Verbs(Requests):
    def verb(self, *argv, session=""):
        env = {"CLAUDE_CODE_SESSION_ID": session} if session else {}
        with mock.patch.dict(os.environ, env):
            if not session:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            return self.cli(*argv)

    def channel_named(self, name):
        return [c for c in sminos.known_channels() if c.name == name]

    def head_wait(self):
        """The machine's enrolment marked, so an append of its operator writer in a channel's log waits for the
        upstream's head (sminos.waits_for_head)."""
        ident = rl10.cutover()
        sminos.mark_enrolled(ident["name"], ident["enrolled"])
        sminos.forget_caches()
        self.assertTrue(sminos.waits_for_head(self.chan(DESK), sminos.writer_id()))

    def release(self):
        sminos.release_queued(self.chan(DESK), sminos.writer_id())
        sminos.forget_caches()

    def test_two_terminals_queued_requests_the_first_cut_the_second_waiting_behind_it(self):
        tid, sid, _ = self.human()
        self.head_wait()

        def cut(*a, **k):
            raise KeyboardInterrupt   # the first command stopped once its request is appended
        with mock.patch.object(channels, "carry_due", cut), self.assertRaises(KeyboardInterrupt):
            self.verb("channel", "add", "desk", sid)
        queued = channels.requests_of(self.chan(DESK))[1]
        self.assertEqual([(r["op"], r["seq"]) for r in queued], [("add", None)], "queued for its writer's head")
        code, out = self.verb("channel", "remove", "desk", sid)
        self.assertEqual(code, 0, out)
        self.assertIn(": out of desk", out, "behind the first, which its pass carried out first")
        self.assertEqual([x[1:3] for x in self.answers(sid)], [(queued[0]["id"], "applied"),
                                                              (channels.requests_of(self.chan(DESK))[1][1]["id"],
                                                               "applied")])
        self.release()
        logged = channels.requests_of(self.chan(DESK))[1]
        self.assertEqual([(r["op"], type(r["seq"])) for r in logged], [("add", int), ("remove", int)],
                         "the queue drained into the log, in its order")
        self.assertEqual(self.carry(DESK), {})
        self.assertEqual(self.held(tid), [])
        self.assertEqual(len(self.answers(sid)), 2)

    def test_an_operators_queued_request_is_carried_out_by_the_command_and_not_again_in_the_log(self):
        tid, sid, _ = self.human()
        self.head_wait()
        code, out = self.verb("channel", "add", "desk", sid)
        self.assertEqual(code, 0, out)
        self.assertIn(": in desk", out)
        self.assertEqual([r["seq"] for r in channels.requests_of(self.chan(DESK))[1]], [None])
        self.release()
        self.assertEqual([type(r["seq"]) for r in channels.requests_of(self.chan(DESK))[1]], [int])
        self.assertEqual(self.carry(DESK), {})
        self.assertEqual(len(self.answers(sid)), 1)
        self.assertEqual(self.held(tid), [DESK])

    def test_a_request_queued_under_a_former_name_waits_for_its_release(self):
        """Nothing here can tell who wrote it until the release rewrites it under the name now: it is neither
        refused nor carried out before, and once released it is carried out as this machine's own."""
        tid, sid, _ = self.human()
        self.identity("testhost", {"oldname": []})
        sminos.forget_caches()
        c = self.chan(DESK)
        old = sminos._queue(c, "oldname/human", [{"kind": "channel-request", "op": "add", "session": sid,
                                                  "thread": tid, "id": "0d" * 16}])[0]
        self.assertEqual(self.carry(DESK), {old["id"]: O("pending", "queued")})
        sminos.forget_caches()
        daemon.channel_pass([c], sminos.seats())
        self.assertEqual(self.statements(sid), [], "the daemon refused nothing")
        sminos.release_queued(c, sminos.writer_id())
        sminos.forget_caches()
        self.assertEqual(self.carry(DESK), {old["id"]: O("applied")}, "as this machine's own")
        self.assertEqual([x[1:3] for x in self.answers(sid)], [(old["id"], "applied")])
        self.assertEqual(self.held(tid), [DESK])

    def test_a_former_names_request_that_names_no_thread_here_holds_nothing_back(self):
        """Deferred only once whom it names and the ledger are read: an old queued request naming a session the
        thread never had is not-here, and a valid request queued behind it is carried out."""
        tid, sid, _, other = self.two()
        self.identity("testhost", {"oldname": []})
        self.head_wait()
        sminos._queue(self.chan(DESK), "oldname/human", [{"kind": "channel-request", "op": "add", "session": other,
                                                          "thread": tid, "id": "0e" * 16}])
        time.sleep(0.002)
        code, out = self.verb("channel", "add", "desk", sid)
        self.assertEqual(code, 0, out)
        self.assertIn(": in desk", out)
        self.assertEqual([r["seq"] for r in channels.requests_of(self.chan(DESK))[1]], [None, None], "both queued")
        self.assertEqual(self.held(tid), [DESK])
        c = self.chan(DESK)
        _, reqs = channels.requests_of(c)
        self.assertEqual(channels.judge(c, reqs[0], threads.get(tid), []), O("ignored", "not-here"))

    def test_create_chooses_before_registering_and_again_at_the_append(self):
        tid, sid, _ = self.human()
        audience.keep_capabilities(["access", "channels"])
        real_choice, chosen = channels._choice, []

        def counted(*a, **k):
            chosen.append(a[0].id)
            return real_choice(*a, **k)
        # The target goes private just before the choice: refused, nothing registered.
        real_mint = channels.mint_channel_id

        def private_first():
            self.record(sid, access="private")
            return real_mint()
        self.verb("list")
        before, logs = [c.id for c in sminos.known_channels()], self.logs()
        with mock.patch.object(channels, "_choice", counted), mock.patch.object(channels, "mint_channel_id",
                                                                                private_first):
            code, out = self.verb("channel", "create", "desk-new", sid)
        self.assertEqual(code, 1, out)
        self.assertIn("refused: not reachable", out)
        self.assertEqual([c.id for c in sminos.known_channels()], before)
        self.assertEqual(self.logs(), logs)
        self.assertEqual(len(chosen), 1)
        # It goes private as the channel is registered, after the preflight: the choice made again at the append
        # differs, so nothing is written for it under the stream the preflight chose (its ids would leave under an
        # audience it no longer has), and the channel stays registered with no member.
        self.record(sid, access="listed")
        chosen.clear()
        real_register = channels.register

        def narrowed(*a, **k):
            self.record(sid, access="private")
            return real_register(*a, **k)
        self.narrowed_known(sid, real_register, counted, chosen)
        chosen.clear()
        logs = self.logs()
        with mock.patch.object(channels, "_choice", counted), mock.patch.object(channels, "register", narrowed):
            code, out = self.verb("channel", "create", "desk-new", sid)
        made = self.channel_named("desk-new")
        self.assertEqual(code, 1, out)
        self.assertEqual(len(made), 1, "registered")
        self.assertEqual(chosen, [made[0].id, made[0].id], "chosen before the registration, and again at the append")
        self.assertIn("created channel desk-new (%s)\n" % made[0].id, out)
        self.assertIn("nothing was recorded (its reach changed as the channel was made): desk-new stays registered "
                      "with no member, and the same command run again brings it back", out)
        self.assertEqual(channels.requests_of(made[0])[1], [], "no request appended")
        self.assertEqual(self.logs(), logs, "nothing written under any stream, in any log")
        self.assertEqual(self.held(tid), [])
        # Its audience known again, the same command brings the channel back.
        self.record(sid, access="listed")
        code, out = self.verb("channel", "create", "desk-new", sid)
        self.assertEqual(code, 0, out)
        self.assertIn("desk-new exists and has no member: ", out)
        self.assertEqual([c.id for c in self.channel_named("desk-new")], [made[0].id])
        self.assertEqual(self.held(tid), [made[0].id])

    def narrowed_known(self, sid, real_register, counted, chosen):
        """Private with its audience known: the choice at the append gives another stream, not a refusal; nothing is
        written under either, and the channel stays registered with no member."""
        def narrowed(*a, **k):
            self.record(sid, access="private")
            d = audience._held_for_write()
            d["sessions"][sid] = {"owners": ["member-1"], "members": ["member-1", "member-2"],
                                  "policyRev": int(records.read(sid).get("policyRev") or 0)}
            audience._write_audiences(d)
            return real_register(*a, **k)
        logs = self.logs()
        with mock.patch.object(channels, "_choice", counted), mock.patch.object(channels, "register", narrowed):
            code, out = self.verb("channel", "create", "desk-known", sid)
        made = self.channel_named("desk-known")
        self.assertEqual((code, len(made), len(chosen)), (1, 1, 2), out)
        self.assertIn("nothing was recorded (its reach changed as the channel was made)", out)
        self.assertEqual(channels.requests_of(made[0])[1], [])
        self.assertEqual(self.logs(), logs)
        self.assertFalse(glob.glob(os.path.join(made[0].home, "log", "*")), "no stream file either")
        self.record(sid, access="listed")

    def test_a_terminals_create_the_daemon_carried_first_is_reported_from_its_answer(self):
        tid, sid, _ = self.human()
        raced = []
        with self.raced(lambda: raced.append(self.answers(sid))):
            code, out = self.verb("channel", "create", "desk-new", sid)
        cid = self.channel_named("desk-new")[0].id
        self.assertEqual([a[0] for a in raced[0]], [cid], "the daemon's pass answered it first")
        self.assertEqual(code, 0, out)
        self.assertIn("created channel desk-new (%s) with " % cid, out)
        self.assertEqual(channels.change(tid, cid, "remove", sid).state, "applied")
        with self.raced(lambda: None):
            code, out = self.verb("channel", "create", "desk-new", sid)
        self.assertEqual(code, 0, out)
        self.assertIn("desk-new exists and has no member: ", out)
        self.assertIn(" is in it again", out)
        self.assertEqual(out.count("\n"), 1, "the one line, no target line after it")
        self.assertEqual(self.held(tid), [cid])

    def test_a_private_targets_refused_stream_at_a_terminals_create_registers_and_writes_nothing(self):
        tid, sid, _ = self.human()
        audience.keep_capabilities(["access", "channels"])
        self.record(sid, access="private")   # its audience at this policyRev not known yet
        self.verb("list")
        before = [c.id for c in sminos.known_channels()]
        logs = self.logs()
        code, out = self.verb("channel", "create", "desk-new", sid)
        self.assertEqual(code, 1, out)
        self.assertIn("refused: not reachable: ", out)
        self.assertIn("nothing was written", out)
        self.assertEqual([c.id for c in sminos.known_channels()], before, "nothing registered")
        self.assertEqual(self.logs(), logs, "no log changed")
        self.assertEqual(self.held(tid), [])

    def logs(self):
        out = {}
        for path in glob.glob(os.path.join(sminos.projects_root(), "*", "log", "*.jsonl")):
            with open(path, "rb") as f:
                out[path] = f.read()
        return out

    def raced(self, then):
        """The command's request answered by another process (the daemon's pass) between its append and the
        command's own pass, and `then` done after."""
        real, once = sminos.nudge_daemon, []

        def nudge():
            if not once:
                once.append(True)
                sminos.forget_caches()
                for c in sminos.known_channels():   # the daemon's channel pass, every channel here
                    channels.carry_due(c, wake_until=time.time())
                then()
            return real()
        return mock.patch.object(sminos, "nudge_daemon", nudge)

    def test_a_request_answered_first_elsewhere_is_reported_from_its_answer(self):
        tid, sid, _, other = self.two()
        with self.raced(lambda: channels.change(tid, DESK, "remove", sid)):
            code, out = self.verb("channel", "add", "desk", sid, session=other)
        self.assertEqual(code, 0, out)
        self.assertIn(": in desk", out, "the add was applied, whatever was done after it")
        self.assertEqual(self.held(tid), [])
        with self.raced(lambda: None), mock.patch.object(channels, "_answer_of_record", lambda *a: None):
            code, out = self.verb("channel", "add", "desk", sid, session=other)
        self.assertEqual(code, 0, out)
        self.assertIn(": answered already by its machine; it is in desk now", out)

    def test_a_write_that_fails_for_one_target_leaves_the_others_reported_and_carried(self):
        tid, sid, _, other = self.two()
        tid3, sid3, _ = self.human()
        real, calls = sminos.log_append, []

        def flaky(*a, **k):
            calls.append(True)
            if len(calls) == 2:
                raise OSError("no space left on the device")
            return real(*a, **k)
        with mock.patch.object(sminos, "log_append", flaky), mock.patch.object(sminos, "nudge_daemon") as nudged:
            code, out = self.verb("channel", "add", "desk", sid, sid3, session=other)
        self.assertEqual(code, 1, out)
        self.assertIn(": in desk", out)
        self.assertIn(": the request could not be written in desk's log: no space left on the device", out)
        self.assertTrue(nudged.called)
        self.assertEqual(self.held(tid), [DESK])
        self.assertEqual(self.held(tid3), [])

    def test_create_cut_after_its_registration_and_run_again_brings_the_channel_back(self):
        tid, sid, _ = self.human()
        real = channels.place

        def cut(*a, **k):
            raise KeyboardInterrupt   # the command stopped once the channel is registered
        with mock.patch.object(channels, "place", cut), self.assertRaises(KeyboardInterrupt):
            self.verb("channel", "create", "desk-new", session=sid)
        made = self.channel_named("desk-new")
        self.assertEqual(len(made), 1)
        self.assertEqual(self.held(tid), [])
        self.assertIs(channels.place, real)
        code, out = self.verb("channel", "create", "desk-new", session=sid)
        self.assertEqual(code, 0, out)
        self.assertIn("desk-new exists and has no member: ", out)
        self.assertIn("is in it again", out)
        self.assertEqual(self.held(tid), [made[0].id])
        code, out = self.verb("channel", "create", "desk-new", session=sid)
        self.assertEqual(code, 1)
        self.assertIn("cannot create channel desk-new: desk-new#%s (channel) already answers to that name"
                      % made[0].id[:8], out)

    def test_create_of_a_name_whose_channel_was_emptied_brings_it_back_under_its_id(self):
        tid, sid, _ = self.human()
        code, out = self.verb("channel", "create", "desk-new", session=sid)
        self.assertEqual(code, 0, out)
        cid = self.channel_named("desk-new")[0].id
        self.assertIn("created channel desk-new (%s) with " % cid, out)
        self.assertTrue(sminos.is_channel_id(cid))
        code, out = self.verb("channel", "remove", "desk-new", session=sid)
        self.assertEqual(code, 0, out)
        self.assertIn(": out of desk-new", out)
        code, out = self.verb("channel", "create", "desk-new", session=sid)
        self.assertEqual(code, 0, out)
        self.assertIn("is in it again", out)
        self.assertEqual([c.id for c in self.channel_named("desk-new")], [cid])
        self.assertEqual(self.held(tid), [cid])

    def test_a_sessions_create_whose_first_membership_cannot_be_recorded_exits_1(self):
        tid, sid, _ = self.human()
        taken, done = threading.Event(), threading.Event()

        def wake():
            hold, _ = sminos.wake_lock(tid, holder=sminos.LAUNCH_HOLD % (os.getpid(), sminos.now()))
            taken.set()
            done.wait(20)
            hold.release()
        t = threading.Thread(target=wake)
        t.start()
        try:
            self.assertTrue(taken.wait(5))
            with mock.patch.object(sminos, "SWEEP_WAIT", 0.2):
                code, out = self.verb("channel", "create", "desk-new", session=sid)
        finally:
            done.set()
            t.join()
        self.assertEqual(code, 1, out)
        self.assertIn("nothing was recorded (it is being woken): run the command again", out)
        self.assertEqual(len(self.channel_named("desk-new")), 1, "the channel stays registered")
        self.assertEqual(self.held(tid), [])
        code, out = self.verb("channel", "create", "desk-new", session=sid)
        self.assertEqual(code, 0, out)
        self.assertIn("is in it again", out)

    def test_the_limit_at_create_before_registration_and_at_add_for_oneself_and_another(self):
        tid, sid, _, other = self.two()
        full = channel_ids(128)
        self.raw(tid, lambda r: r.update(channels=full))
        before = [c.id for c in sminos.known_channels()]
        code, out = self.verb("channel", "create", "desk-new", session=sid)
        self.assertEqual(code, 1)
        self.assertIn("is in 128 channels, the limit: nothing was written", out)
        self.assertEqual([c.id for c in sminos.known_channels()], before, "nothing registered")
        code, out = self.verb("channel", "add", "desk", session=sid)
        self.assertEqual(code, 1)
        self.assertIn("is in 128 channels, the limit: nothing was written", out)
        code, out = self.verb("channel", "add", "desk", sid, session=other)
        self.assertEqual(code, 1)
        self.assertIn("is in 128 channels, the limit: nothing was written", out)
        self.assertEqual(channels.requests_of(self.chan(DESK))[1], [], "no request written")
        self.assertEqual(self.held(tid), full)

    def test_add_and_remove_of_another_thread_by_a_request_carried_out_at_once(self):
        tid, sid, _, other = self.two()
        code, out = self.verb("channel", "add", "desk", sid, session=other)
        self.assertEqual(code, 0, out)
        self.assertIn(": in desk", out)
        self.assertEqual(self.held(tid), [DESK])
        reqs = channels.requests_of(self.chan(DESK))[1]
        self.assertEqual([(r["op"], r["writer"], r["thread"], r["session"]) for r in reqs],
                         [("add", sminos.writer_id(other), tid, sid)])
        self.assertNotIn("to", reqs[0])
        code, out = self.verb("channel", "add", "desk", sid)
        self.assertEqual((code, out.count(": already in desk")), (0, 1), out)
        code, out = self.verb("channel", "remove", "desk", sid)
        self.assertEqual(code, 0, out)
        self.assertIn(": out of desk", out)
        code, out = self.verb("channel", "remove", "desk", sid)
        self.assertIn(": was not in desk", out)
        self.assertEqual(self.held(tid), [])
        self.assertEqual(len(self.answers(sid)), 4)


# ------------------------------------------------------------ the frontier review, round 1 (the holder's fix wave)


class Frontier(Requests):
    """The fixes of the frontier review's first round that §6's carrying out owns (A2 to A5, A8, A9)."""

    def imported_own(self, cid, op, sid, tid, writer=None, **more):
        """A request under this machine's own name that this machine did not append: in its log, with no append
        receipt (as one the hub brought back under a reused name would be), with the import's `verified`."""
        more.setdefault("verified", {"signer": SIGNER})
        e = self.request(cid, op, sid, tid, writer=writer, **more)
        path = sminos.receipt_path(self.chan(cid), e["writer"])
        with open(path) as f:
            kept = [line for line in f if line.strip() and json.loads(line)["seq"] != e["seq"]]
        with open(path, "w") as f:
            f.writelines(kept)
        self.assertFalse(channels.appended_here(self.chan(cid), e))
        return e

    def test_a2_the_shortcut_holds_only_for_a_requester_this_machine_has_a_record_of(self):
        """An event under this machine's name that this machine did not write (one the hub brought back under a
        reused name, a home rebuilt) is not its own: it takes the endpoint's word, whatever its owners."""
        tid, sid, _ = self.human()
        # The person at this machine: a request with no append receipt here.
        e = self.imported_own(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "endpoint")}, "not appended here: asked")
        self.assertEqual(self.carry(DESK, words=self.words(DESK, e, "deliver", sid)), {e["id"]: O("applied")})
        # A session of this machine's name whose owners are the thread's, with no thread or seat record here.
        ghost = str(uuidlib.uuid4())
        shutil.copy(records.record_path(sid), records.record_path(ghost))
        self.assertTrue(sminos.same_owner_local({"writer": sminos.writer_id(ghost)}, sid, self.chan(DESK)),
                        "by the owners alone, the same owner")
        r = self.imported_own(DESK, "remove", sid, tid, writer=sminos.writer_id(ghost))
        self.assertEqual(self.carry(DESK), {r["id"]: O("pending", "endpoint")}, "not appended here: asked")
        self.assertEqual(self.held(tid), [DESK])
        # Written here, under either writer: no word.
        tid2, sid2, _, other = self.two()
        mine = self.request(DESK, "add", sid2, tid2)
        self.assertEqual(self.carry(DESK, also=[mine])[mine["id"]], O("applied"))
        theirs = self.request(DESK, "remove", sid2, tid2, writer=sminos.writer_id(other))
        self.assertEqual(self.carry(DESK, also=[theirs])[theirs["id"]], O("applied"))

    def test_a2_a_request_this_machine_queued_is_its_own(self):
        """A request in this machine's own queue for its writer's head has no position or receipt yet; the queue
        is this machine's, so it is honoured with no word."""
        tid, sid, _ = self.human()
        ident = rl10.cutover()
        sminos.mark_enrolled(ident["name"], ident["enrolled"])
        sminos.forget_caches()
        e = self.request(DESK, "add", sid, tid)
        self.assertIsNone(e["seq"], "queued")
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")})

    def test_a3_the_terminals_shortcut_reads_the_targets_owners_from_its_record(self):
        """The endpoint's last resolved owners of the target (its audience entry) do not make the person at this
        machine its owner once the record names another owner."""
        tid, sid, _, other = self.two()
        for s in (sid, other):
            audience.keep_audience({"session": s, "owners": ["member-me"], "members": None, "policyRev": 0})
        self.assertEqual(audience.machine_owners(), ["member-me"])
        self.owners(sid, ["member-someone"])   # stronger provenance replaced the machine's provisional owners
        self.assertTrue(sminos.owners_meet("", sid), "the stale audience entry would meet")
        e = self.request(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "endpoint")})
        self.owners(sid, ["member-me"])
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")}, "the machine's owner, by the record")

    def during_positions(self, change):
        """sminos.channel_positions with `change` made as it is read: after the judgment under the lock, before
        the record's write."""
        real = sminos.channel_positions

        def reading(*a, **k):
            change()
            return real(*a, **k)
        return mock.patch.object(sminos, "channel_positions", reading)

    def assert_unwritten(self, tid, sid):
        t = threads.get(tid)
        self.assertEqual((t["channels"], t.get("pending"), t.get("answered")), ([], None, None), "nothing written")
        self.assertEqual(self.statements(sid), [])

    def test_a4_a_reach_changed_while_the_positions_are_read_commits_nothing(self):
        tid, sid, _ = self.human()
        e = self.remote(DESK, "add", sid, tid)
        words = self.words(DESK, e, "deliver", sid)
        with self.during_positions(lambda: self.bump(sid)):
            self.assertEqual(self.carry(DESK, words=words), {e["id"]: O("pending", "moved")})
        self.assert_unwritten(tid, sid)
        self.assertEqual(self.carry(DESK, words=self.words(DESK, e, "deliver", sid)), {e["id"]: O("applied")})

    def test_a4_a_session_turned_lane_b_while_the_positions_are_read_gets_no_statement(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, tid)
        with self.during_positions(lambda: records.set_controller(sid, "B")):
            self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "not-here"))
        self.assert_unwritten(tid, sid)
        records.set_controller(sid, "A")
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")}, "judged anew once it is lane A again")

    def test_a4_a_threads_own_change_rechecks_its_lane_last(self):
        tid, sid, _ = self.human()
        with self.during_positions(lambda: records.set_controller(sid, "B")):
            self.assertEqual(channels.change(tid, DESK, "add", sid), O("failed", "lane-b"))
        self.assert_unwritten(tid, sid)
        self.assertIn("lane-b", channels.OWN_FAILED)
        records.set_controller(sid, "A")
        self.assertEqual(channels.change(tid, DESK, "add", sid), O("applied"))

    def test_a4_a_move_while_the_positions_are_read_is_still_between(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, tid)
        with self.during_positions(lambda: self.write_own(sid, [{"kind": "retired", "reason": "moved", "project": "",
                                                                 "thread": tid}])):
            self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("pending", "between"))
        self.assert_unwritten(tid, sid)

    def test_a5_a_session_named_by_its_full_id_is_stamped_with_its_canonical_thread(self):
        """An older copy's seat over a session its human opened: the full id resolves as that seat, and the
        request names the thread whose record is the session's canonical one."""
        tid, sid, _ = self.human()
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})   # the older CLI's seat, no thread keys
        self.reconcile()
        self.assertEqual(sminos.find_target(sid)[0], "seat")
        self.assertEqual(threads.current_record(sid, fresh=True)["thread"], tid)
        self.assertEqual(channels._target(sid).thread, tid)
        code, out = self.cli("channel", "add", "desk", sid)
        self.assertEqual(code, 0, out)
        self.assertIn(": in desk", out)
        self.assertEqual(self.held(tid), [DESK])

    def unreadable(self, path):
        """`path` there and not to be opened (its stat still reads), forgotten by the read caches."""
        real = open

        def opening(p, *a, **k):
            if os.path.abspath(str(p)) == os.path.abspath(path):
                raise PermissionError(13, "Permission denied", p)
            return real(p, *a, **k)
        sminos._LOG_FILES.pop(path, None)
        sminos._MERGED.clear()
        return mock.patch("builtins.open", opening)

    def test_a8_nothing_is_carried_past_a_writer_file_that_cannot_be_read(self):
        tid, sid, _, other = self.two()
        first = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(other))
        later = self.request(DESK, "remove", sid, tid)
        path = sminos.writer_path(self.chan(DESK), first["writer"])
        with self.unreadable(path):
            self.assertEqual(self.carry(DESK, also=[later]), {later["id"]: O("pending", "unreadable")})
            self.assertEqual(self.carry(DESK), {}, "nothing of the channel carried")
            with self.assertRaises(sminos.PositionsUnread):
                channels.requests_of(self.chan(DESK))
        self.assertEqual(self.held(tid), [])
        sminos._MERGED.clear()
        self.assertEqual(self.carry(DESK), {first["id"]: O("applied"), later["id"]: O("applied")}, "in order")
        self.assertEqual([a[1] for a in self.answered(tid)], [first["id"], later["id"]])

    def test_a8_nor_past_an_operator_queue_that_cannot_be_read(self):
        tid, sid, _ = self.human()
        ident = rl10.cutover()
        sminos.mark_enrolled(ident["name"], ident["enrolled"])
        sminos.forget_caches()
        e = self.request(DESK, "add", sid, tid)
        self.assertIsNone(e["seq"])
        [queue] = glob.glob(os.path.join(self.chan(DESK).home, sminos.QUEUED, "*.jsonl"))
        with self.unreadable(queue):
            self.assertEqual(self.carry(DESK, also=[e]), {e["id"]: O("pending", "unreadable")})
        self.assertEqual(self.held(tid), [])
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")})

    def test_a9_a_request_id_is_32_lower_case_hex_digits(self):
        tid, sid, _ = self.human()
        for bad in ("same-id", "A" * 32, "a" * 31, "a" * 33, "a" * 32 + "\n", "{\"private\": 1}"):
            with self.subTest(bad):
                e = self.request(DESK, "add", sid, tid, rid=bad)
                self.assertFalse(channels.is_request(e))
                self.assertEqual(self.carry(DESK), {}, "no request")
        good = self.request(DESK, "add", sid, tid, rid="0123456789abcdef" * 2)
        self.assertTrue(channels.is_request(good))
        self.assertEqual(self.carry(DESK), {good["id"]: O("applied")})

    # -- the fix wave's review, round 1

    def test_rows_8_and_9_an_imported_request_under_this_machines_name_is_from_outside(self):
        """The ruling of 2026-11-22: one predicate (appended_here) decides "this machine's own" for every row."""
        tid, sid, _ = self.human()
        e = self.imported_own(DESK, "add", sid, tid)
        self.assertTrue(channels._Facts().outside_origin(self.chan(DESK), e), "row 8: from outside")
        audience.keep_capabilities([])
        self.assertEqual(self.carry(DESK), {e["id"]: O("pending", "no-channels")})
        audience.keep_capabilities(["channels"])
        sminos.write_json(sminos.sibling_module("sminos_policy").policy_path(), {"read_only": True})
        self.assertEqual(self.carry(DESK), {e["id"]: O("refused", "read-only")}, "row 9: read-only refuses it")
        mine = self.request(LOBBY, "add", sid, tid)   # appended here: no request from outside, read-only or not
        self.assertFalse(channels._Facts().outside_origin(self.chan(LOBBY), mine))
        self.assertEqual(self.carry(LOBBY), {mine["id"]: O("applied")})

    def test_row_11_an_imported_request_under_this_machines_name_has_its_signer_read(self):
        tid, sid, _ = self.human()
        unsigned = self.imported_own(DESK, "add", sid, tid, verified=None)
        self.assertFalse(channels.sender_verified(self.chan(DESK), unsigned), "no verified key: refused")
        self.assertEqual(self.carry(DESK, words=self.words(DESK, unsigned, "deliver", sid)),
                         {unsigned["id"]: O("refused", "not-reachable")})
        sminos.write_json(rl10.revoked_path(), {"version": 1, "devices": [], "members": [], "keys": ["key-other"]})
        revoked = self.imported_own(DESK, "add", sid, tid)
        self.assertEqual(self.carry(DESK, words=self.words(DESK, revoked, "deliver", sid)),
                         {revoked["id"]: O("refused", "not-reachable")}, "a revoked signer is caught")
        own = self.request(DESK, "remove", sid, tid)
        self.assertTrue(channels.sender_verified(self.chan(DESK), own), "appended here: verified as this machine's")
        self.assertEqual(self.held(tid), [])

    def listing_denied(self, where):
        """`where` (a directory) there and not to be listed."""
        real_listdir, real_scandir = os.listdir, os.scandir

        def denied(real):
            def call(p=".", *a, **k):
                if os.path.abspath(os.fspath(p)) == os.path.abspath(where):
                    raise PermissionError(13, "Permission denied", p)
                return real(p, *a, **k)
            return call
        sminos._MERGED.clear()
        return mock.patch("os.listdir", denied(real_listdir)), mock.patch("os.scandir", denied(real_scandir))

    def test_a8_nothing_is_carried_past_a_log_or_a_queue_that_cannot_be_listed(self):
        tid, sid, _, other = self.two()
        first = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(other))
        ident = rl10.cutover()
        sminos.mark_enrolled(ident["name"], ident["enrolled"])
        sminos.forget_caches()
        later = self.request(DESK, "remove", sid, tid)   # queued for its writer's head
        self.assertIsNone(later["seq"])
        for where in (os.path.join(self.chan(DESK).home, "log"), os.path.join(self.chan(DESK).home, sminos.QUEUED)):
            with self.subTest(os.path.basename(where)):
                listdir, scandir = self.listing_denied(where)
                with listdir, scandir:
                    self.assertEqual(self.carry(DESK, also=[later]), {later["id"]: O("pending", "unreadable")})
                    with self.assertRaises(sminos.PositionsUnread):
                        channels.requests_of(self.chan(DESK))
                self.assertEqual(self.held(tid), [])
                self.assertEqual(self.answered(tid), [])
        sminos._MERGED.clear()
        self.assertEqual(self.carry(DESK), {first["id"]: O("applied"), later["id"]: O("applied")}, "in order")

    def test_a8_the_input_read_is_the_one_the_strict_listing_listed(self):
        """The strict listing is the read's own input, never a check beside it: a listing the readers would take
        between them that fails as glob fails (as nothing at all) cannot make a log or a queue read as empty."""
        tid, sid, _, other = self.two()
        first = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(other))
        ident = rl10.cutover()
        sminos.mark_enrolled(ident["name"], ident["enrolled"])
        sminos.forget_caches()
        later = self.request(DESK, "remove", sid, tid)   # queued for its writer's head
        self.assertIsNone(later["seq"])
        home, real = self.chan(DESK).home, glob.glob

        def failing(pattern, *a, **k):
            if os.fspath(pattern).startswith(glob.escape(home)):
                return []   # glob's answer to a directory it could not list
            return real(pattern, *a, **k)
        sminos._MERGED.clear()
        with mock.patch("glob.glob", failing):
            _, reqs = channels.requests_of(self.chan(DESK))
        self.assertEqual([r["id"] for r in reqs], [first["id"], later["id"]])

    def test_a8_nor_past_a_listed_writer_file_whose_metadata_cannot_be_read(self):
        """A writer file the listing named whose stat and lstat are refused (a permission, not an absence) is
        unread: only FileNotFoundError says a listed file is gone."""
        tid, sid, _, other = self.two()
        first = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(other))
        later = self.request(DESK, "remove", sid, tid)
        path = sminos.writer_path(self.chan(DESK), first["writer"])

        def denied(real):
            def call(p, *a, **k):
                if not isinstance(p, int) and os.path.abspath(os.fspath(p)) == os.path.abspath(path):
                    raise PermissionError(13, "Permission denied", p)
                return real(p, *a, **k)
            return call
        sminos._LOG_FILES.pop(path, None)
        sminos._MERGED.clear()
        with mock.patch("os.stat", denied(os.stat)), mock.patch("os.lstat", denied(os.lstat)):
            self.assertEqual(self.carry(DESK, also=[later]), {later["id"]: O("pending", "unreadable")})
            with self.assertRaises(sminos.PositionsUnread):
                channels.requests_of(self.chan(DESK))
        self.assertEqual(self.held(tid), [])
        self.assertEqual(self.answered(tid), [])
        sminos._MERGED.clear()
        self.assertEqual(self.carry(DESK), {first["id"]: O("applied"), later["id"]: O("applied")}, "in order")



class Frontier2(Requests):
    """The fixes of the frontier review's second round that §6's carrying out and the verbs own (C3 to C6)."""

    during_positions = Frontier.during_positions
    assert_unwritten = Frontier.assert_unwritten

    def verb(self, *argv, session=""):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session} if session else {}):
            if not session:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            return self.cli(*argv)

    def test_c3_a_channel_write_is_refused_where_this_machines_enrollment_does_not_carry_its_log(self):
        """A channel registered under another enrollment (another org's hub): its log is one the uplink leaves out,
        so create's revival, add and env each refuse before anything is written, rather than say success for
        facts that never sync. Leaving one stays possible."""
        tid, sid, _ = self.human()
        cid = channels.mint_channel_id()
        sminos.register_if_absent(sminos.make_project(cid, "old", "", "", {"url": HUB["url"], "org": "org-0"}))
        sminos.forget_caches()
        home = os.path.join(sminos.projects_root(), cid)

        def files():
            return sorted((os.path.relpath(os.path.join(d, f), home), os.path.getsize(os.path.join(d, f)))
                          for d, _, fs in os.walk(home) for f in fs)
        before = files()
        for argv, session in ((("channel", "create", "old"), sid), (("channel", "add", "old", sid), ""),
                              (("channel", "add", "old"), sid), (("channel", "env", "add", "old", "beta"), sid)):
            with self.subTest(argv):
                code, out = self.verb(*argv, session=session)
                self.assertEqual(code, 1, out)
                self.assertIn("this machine's enrollment does not carry its log (%s)" % sminos.OTHER_ORG, out)
                self.assertIn("nothing was written", out)
        self.assertEqual(files(), before, "nothing written in its log")
        self.assertEqual(self.held(tid), [])
        self.assertEqual(self.statements(sid), [])
        # One of this enrollment that left this machine (memberless, unlisted): a member placed is what brings it back.
        kept = channels.mint_channel_id()
        sminos.register_if_absent(sminos.make_project(kept, "kept", "", "", HUB))
        sminos.write_json(sminos.leaving_path(), {"counted": {}, "left": [kept]})
        sminos.forget_caches()
        self.assertEqual(sminos.not_carried(self.chan(kept), HUB["org"]), sminos.LEFT_HERE)
        code, out = self.verb("channel", "create", "kept", session=sid)
        self.assertEqual(code, 0, out)
        self.assertIn("is in it again", out)
        self.assertEqual(self.held(tid), [kept])

    def test_c4_an_exact_seat_group_still_resolves_beside_a_channel_of_its_name(self):
        """`g/worker`, where `g` is a seat group and no project: a channel named `g` arriving does not make the
        seat unreachable by that exact name; what is only the channel's is still refused."""
        tid, sid, _ = self.seat("worker")
        sminos.register_if_absent(sminos.make_project(channels.mint_channel_id(), "g", "", "", HUB))
        sminos.forget_caches()
        self.assertIsNotNone(sminos.names_channel("g"))
        kind, res, _ = sminos.find_target("g/worker")
        self.assertEqual((kind, res["seat_id"]), ("seat", tid))
        self.assertEqual(channels._target("g/worker").thread, tid)
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as out:
            sminos.find_target("g/nobody")
        self.assertEqual(out.exception.code, sminos.EXIT_UNKNOWN)
        self.assertIn("names a thread through a channel", err.getvalue())

    def test_c5_a_record_that_cannot_be_read_at_the_last_read_defers_the_write(self):
        """The last lane read: a session record that is missing is absence (lane A, as ever); one that is there and
        cannot be read writes nothing, a request pending for it and a thread's own change failed, as an unreadable
        writer file does (A8)."""
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, tid)
        path = records.record_path(sid)
        with open(path) as f:
            kept = f.read()

        def spoil():
            with open(path, "w") as f:
                f.write("{")

        def mend():
            with open(path, "w") as f:
                f.write(kept)
            sminos.forget_caches()
        with self.during_positions(spoil):
            self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("pending", "record-unreadable"))
        self.assert_unwritten(tid, sid)
        mend()
        with self.during_positions(spoil):
            self.assertEqual(channels.change(tid, LOBBY, "add", sid), O("failed", "record-unreadable"))
        self.assert_unwritten(tid, sid)
        self.assertIn("record-unreadable", channels.WORDS)
        self.assertIn("record-unreadable", channels.OWN_FAILED)
        mend()
        self.assertEqual(self.carry(DESK), {e["id"]: O("applied")}, "carried out once it reads again")

    def test_c6_a_session_still_current_on_a_newer_ended_record_names_no_older_thread(self):
        """§6's row 3 reads whose current session it is over ended records too: the addressed session is the current
        one of another, newer record that has ended (in place, then set aside), so an older thread that once had it
        is not placed by a request naming it."""
        tid, sid, _ = self.human()
        tid2, sid2, _ = self.human()
        self.raw(tid, lambda r: r.update(sessions=[sid2] + [x for x in r.get("sessions", []) if x != sid2]))
        e = self.request(DESK, "add", sid2, tid)
        self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "not-here"), "its live current one")
        self.raw(tid2, lambda r: r.update(ended={"at": sminos.now(), "reason": "retire", "by": "", "pid": None}))
        self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "not-here"), "ended, in place")
        self.assertTrue(threads._change(tid2, lambda view, raw: "aside"))
        sminos.forget_caches()
        self.assertTrue(os.path.exists(threads._human_path(tid2, aside=True)))
        self.assertIsNone(threads.current_record(sid2, fresh=True), "no live record's current one")
        self.assertEqual(self.carry(DESK, also=[e])[e["id"]], O("ignored", "not-here"), "set aside")
        self.assertEqual((self.held(tid), self.answered(tid)), ([], []))
        self.assertEqual(self.statements(sid), [])


if __name__ == "__main__":
    unittest.main()
