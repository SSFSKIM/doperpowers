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
import json
import os
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_channels_store import DESK, HUB, LOBBY, Store, channel_ids, sminos, threads  # noqa: E402
import sminos_audience as audience  # noqa: E402
import sminos_channels as channels  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402

O = channels.Outcome
OTHER = "6b000009-0000-4000-8000-0000000000b9"     # a session of another machine: the remote requester
SIGNER = {"kind": "machine", "keyId": "key-other"}


def forbidden(*a, **k):
    raise AssertionError("a read under the record's lock wrote or locked something")


class Requests(Store):
    """Store, on a machine cut over to its endpoint, whose kept welcome lists `channels`."""

    def setUp(self):
        super().setUp()
        self.identity(sminos.host_name())
        self.p = self.project_of(self.root)
        audience.keep_capabilities(["channels"])
        sminos.forget_caches()

    def identity(self, name):
        os.makedirs(os.path.dirname(rl10.identity_path()), mode=0o700, exist_ok=True)
        sminos.write_json(rl10.identity_path(), {
            "org": HUB["org"], "hub": HUB["url"], "name": name, "former": {}, "ref": "machine-ref-1",
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
        first = self.remote(DESK, "add", sid, tid, rid="same-id")
        self.assertEqual(self.carry(DESK), {"same-id": O("pending", "endpoint")})
        second = self.request(DESK, "remove", sid, tid, writer=sminos.writer_id(other), rid="same-id")
        self.assertEqual(self.judge(DESK, second, tid), O("ignored", "duplicate"))
        words = {**self.words(DESK, first, "deliver", sid), **self.words(DESK, second, "deliver", sid)}
        got = [(r["writer"], o) for r, o in channels.carry_due(self.chan(DESK), words=words)]
        self.assertEqual(got, [(first["writer"], O("applied"))], "the second passed by: its id is answered")
        self.assertEqual(self.judge(DESK, second, tid), O("ignored", "duplicate"))
        self.assertEqual(self.held(tid), [DESK], "the first one's add, and not the second one's remove")
        self.assertEqual(self.answers(sid), [(DESK, "same-id", "applied", None, (DESK,))])
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
            "the machine's identity": ("person", lambda sid: self.identity("renamed"),
                                       O("refused", "not-reachable")),
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
                        mock.patch.object(fcntl, "flock", forbidden), mock.patch.object(sminos, "write_json", forbidden):
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

    def queue(self, cid, op, sid, tid):
        """A terminal's request that waits for its writer's head, as the command queued it."""
        return sminos._queue(self.chan(cid), sminos.writer_id(), [
            {"kind": "channel-request", "op": op, "session": sid, "thread": tid, "id": os.urandom(16).hex()}])[0]

    def test_two_terminals_queued_requests_the_first_cut_the_second_waiting_behind_it(self):
        tid, sid, _ = self.human()
        first = self.queue(DESK, "add", sid, tid)        # its command cut after the append
        time.sleep(0.002)
        second = self.queue(DESK, "remove", sid, tid)
        got = [(r["id"], o) for r, o in channels.carry_due(self.chan(DESK), also=[second])]
        self.assertEqual(got, [(first["id"], O("applied")), (second["id"], O("applied"))], "the first one first")
        self.assertEqual(self.held(tid), [])
        self.assertEqual([a[1] for a in self.answers(sid)], [first["id"], second["id"]])

    def test_an_operators_queued_request_is_carried_out_by_the_command_and_not_again_in_the_log(self):
        tid, sid, _ = self.human()
        e = self.queue(DESK, "add", sid, tid)
        self.assertIsNone(e["seq"])
        self.assertEqual(self.carry(DESK, also=[e]), {e["id"]: O("applied")})
        # It reaches the log once the head is known: the queue drained into the log, its ts kept.
        c = self.chan(DESK)
        sminos._append(c, e["writer"], [{k: v for k, v in e.items() if k not in ("writer", "seq")}], released=True)
        os.unlink(sminos.queued_path(c, e["writer"]))
        self.assertEqual(self.carry(DESK), {})
        self.assertEqual(len(self.answers(sid)), 1)
        self.assertEqual(self.held(tid), [DESK])

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


if __name__ == "__main__":
    unittest.main()
