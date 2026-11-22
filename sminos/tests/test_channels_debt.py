#!/usr/bin/env python3
"""What a channel owes a thread (CH2's M2:
docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md, the milestone's
"Proves"; Interfaces §3's first half and its rows D1 to D15).

- The selection (sminos_channels.owed over debt()): the events of a
  channel's log whose `to` names the thread by its id, past where its
  membership began, not settled in its delivery record. Staged through each
  transition itself: an add (its own, and a request carried out), a
  removal, a removal and an add, a reopening while a member, a hand-off,
  an absorption, a refill (and a repoint to a lane B session), an end and
  each kind of return, a session that runs again as another thread, a
  person's message released from this machine's queue after an add, a seat
  made again over a purged seat's session.
- Who an entry names: the thread, never a session; an entry with no
  `thread` names no one; the thread's own message is not owed to it.
- What reads it and what it reads: owing() with a session's record there,
  absent (lane A) and unreadable, lane B and an open entry; a delivery
  record absent (empty) and unreadable (nothing claimed); a thread whose own
  record cannot be read (no debt attributed); the last check (still_owed).
- `sminos daemon owed`: a channel's debt under the thread's alias, a held
  thread's as waiting, an unreadable delivery record among what it could
  not inspect, and a cold run over a store with an entry open that lists
  the debt and changes no file.

Nothing is pushed here: the messages are put into the channel's log by the
suite (log_append under a writer, an imported one carrying `verified`), and
settled by the delivery record's own writers under the thread's id.
Hermetic: test_channels_life's Life over T1's fixtures (HOME and SMINOS_HOME
temporary; sessions `sleep`s with engine records the test writes).
Run: python3 -B sminos/tests/test_channels_debt.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import os
import subprocess
import sys
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import test_threads as T1  # noqa: E402 — its fixtures by module: their own tests are not run again here
import test_threads_ended as T1_ended  # noqa: E402
from test_threads import SCRIPTS, Killed, records, sminos, threads  # noqa: E402
from test_channels_life import DESK, LOBBY, Life  # noqa: E402
import test_channels_requests as CH1_requests  # noqa: E402 — by module: its own tests are not run again here
import sminos_channels as channels  # noqa: E402

FAR = "beta"                                         # another machine's name
SENDER = "5e000001-0000-4000-8000-0000000000e1"      # a session of that machine, and its thread
SENDER_THREAD = "5e0000a1-0000-4000-8000-0000000000a1"
SIGNER = {"kind": "machine", "keyId": "key-beta"}
W1 = "%s/%s" % (FAR, SENDER)
W2 = "%s/5e000002-0000-4000-8000-0000000000e2" % FAR


def ref(w, seq):
    return sminos.event_ref({"writer": w, "seq": seq})


class Debts(Life):
    """Messages put into a channel's log, and what is read of the debt."""

    def message(self, cid, *to, writer=W1, kind="say", sender=SENDER_THREAD, **fields):
        """A message in the channel's log naming each (session, thread) of `to` (a thread None: an entry with
        none), as an import leaves one: under another machine's writer, carrying `verified`. (writer, seq)."""
        entries = [dict({"session": sid, "alias": "a"}, **({"thread": tid} if tid is not None else {}))
                   for sid, tid in to]
        body = {"from": "human"} if kind == "human" else {"from": "s", "thread": sender}
        body.update(to=entries, text="hi", verified={"signer": SIGNER})
        body.update(fields)
        time.sleep(0.002)   # the merged log's order is by time
        e = sminos.log_append(self.chan(cid), writer, kind, **body)
        sminos.forget_caches()
        return e["writer"], e["seq"]

    def debt_of(self, tid, cid=DESK):
        sminos.forget_caches()
        t = threads.get(tid)
        return channels.debt(self.chan(cid), t) if t is not None else None

    def owed_to(self, tid, cid=DESK):
        """What the channel owes the thread, as (writer, seq): None for no debt, or one that cannot be told."""
        d = self.debt_of(tid, cid)
        if d is None:
            return None
        got = channels.owed(d, sminos.log_read(self.chan(cid)))
        return None if got is None else [(e["writer"], e["seq"]) for e in got]

    def settle(self, tid, w, seq, cid=DESK):
        """Settled by the record's own writer, under the thread's id."""
        sminos.delivered_settle(self.chan(cid), tid, w, seq)

    def record_path(self, tid, cid=DESK):
        return os.path.join(self.chan(cid).home, "delivered", tid + ".json")

    def bytes_of(self, path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def owed_cli(self):
        """`daemon owed`, in this process: (exit code, its lines)."""
        code, out = self.cli("daemon", "owed")
        return code, out.splitlines()

    def desk_lines(self, lines):
        return [line for line in lines if line.startswith("desk: ")]


# ------------------------------------------------------------ the selection, and who an entry names


class Selection(Debts, T1.Sessions):
    def test_d1_what_the_machine_held_at_the_add_is_never_owed_and_what_follows_is_in_order(self):
        sid, _, tid = self.member()
        before = [self.message(DESK, (sid, tid)) for _ in range(2)]
        self.assertIsNone(self.owed_to(tid), "not in the channel: no debt")
        self.add(tid, sid, DESK)
        d = self.debt_of(tid)
        self.assertEqual((d.thread, d.session, d.boundary), (tid, sid, {W1: 2}))
        after = [self.message(DESK, (sid, tid)), self.message(DESK, (sid, tid), writer=W2),
                 self.message(DESK, (sid, tid))]
        self.assertEqual(self.owed_to(tid), after, "the one at the boundary (seq 2) is not owed; the next is")
        self.assertNotIn(before[-1], self.owed_to(tid))
        self.assertEqual([(e["writer"], e["seq"]) for e in
                          [channels.first_owed(d, W1, sminos.log_read(self.chan(DESK)))]], [after[0]])
        self.assertEqual(channels.first_owed(d, W2, sminos.log_read(self.chan(DESK)))["seq"], 1)

    def test_d2_what_the_record_settles_is_owed_no_more(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        a, b = self.message(DESK, (sid, tid)), self.message(DESK, (sid, tid))
        self.settle(tid, *a)
        self.assertEqual(self.owed_to(tid), [b])
        self.assertEqual(sminos.delivered_fail(self.chan(DESK), tid, *b), 1)
        self.assertEqual(self.owed_to(tid), [b], "a failed attempt leaves it owed")
        self.assertFalse(os.path.exists(os.path.join(self.chan(DESK).home, "delivered", sid + ".json")),
                         "the record is the thread's, never its session's")

    def test_an_entry_names_a_thread_by_its_id_and_never_by_a_session(self):
        sid, _, tid = self.member()
        other_tid = str(uuidlib.uuid4())
        self.add(tid, sid, DESK)
        self.message(DESK, (sid, other_tid))                        # its session, another thread's id
        never = self.message(DESK, (str(uuidlib.uuid4()), tid))     # its id, a session it never held
        self.message(DESK, (sid, None))                             # its session, no thread: names no one
        self.message(DESK, (sid, 7))                                # a thread of the wrong type: none
        self.message(DESK, (sid, tid), sender=tid)                  # its own message
        self.message(DESK, (sid, tid), copy={"project": "x"})       # a copy is owed to no one
        self.message(DESK, to="*")                                  # an untagged post
        twice = self.message(DESK, (sid, tid), (str(uuidlib.uuid4()), tid))
        person = self.message(DESK, (sid, tid), writer="%s/human" % FAR, kind="human")
        self.assertEqual(self.owed_to(tid), [never, twice, person], "each once, in the log's order")

    def test_d4_a_thread_removed_is_owed_nothing_and_its_record_stays_as_it_is(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        a = self.message(DESK, (sid, tid))
        self.message(DESK, (sid, tid))
        self.settle(tid, *a)
        held = self.bytes_of(self.record_path(tid))
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.message(DESK, (sid, tid))
        self.assertIsNone(self.debt_of(tid))
        self.assertEqual(self.bytes_of(self.record_path(tid)), held, "nothing written at a removal")
        code, lines = self.owed_cli()
        self.assertEqual(self.desk_lines(lines), [], lines)

    def test_d5_removed_and_added_again_owes_only_what_the_machine_imports_after_the_second_add(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.message(DESK, (sid, tid))                              # owed while a member, never delivered
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.message(DESK, (sid, tid))                              # while it was out
        self.message(DESK, (sid, tid), writer=W2)
        self.add(tid, sid, DESK)
        self.assertEqual(self.debt_of(tid).boundary, {W1: 2, W2: 1})
        self.assertEqual(self.owed_to(tid), [], "what the machine held at the second add, held mail included")
        late = self.message(DESK, (sid, tid), writer="%s/5e000003-0000-4000-8000-0000000000e3" % FAR,
                            ts="2026-01-01T00:00:00.000Z")         # written long before, imported now
        after = self.message(DESK, (sid, tid))
        self.assertEqual(self.owed_to(tid), [late, after], "whenever it was written")

    def test_a_thread_in_no_channel_is_owed_nothing_whatever_names_it(self):
        sid, _, tid = self.member()
        self.add(tid, sid, LOBBY)
        self.message(DESK, (sid, tid))
        self.assertIsNone(self.debt_of(tid))
        self.assertEqual([d.thread for d, _ in channels.owed_here(self.chan(DESK))], [])
        code, lines = self.owed_cli()
        self.assertEqual(self.desk_lines(lines), [], lines)


class Requested(Debts, CH1_requests.Verbs):
    """On a machine cut over to its endpoint: an add by a request carried out, and a person's message that
    waited in this machine's queue."""

    def test_d1_an_add_by_a_request_carried_out_begins_where_the_log_stood_then(self):
        tid, sid, _ = self.human()
        before = self.message(DESK, (sid, tid))
        e = self.request(DESK, "add", sid, tid)
        between = self.message(DESK, (sid, tid))           # after the request, before it is carried out
        self.assertIsNone(self.owed_to(tid), "not in the channel until it is carried out")
        self.assertEqual(self.carry(DESK), {e["id"]: channels.Outcome("applied")})
        d = self.debt_of(tid)
        self.assertEqual((d.boundary[W1], d.boundary[e["writer"]]), (2, e["seq"]), "the log's positions then")
        after = self.message(DESK, (sid, tid))
        self.assertEqual(self.owed_to(tid), [after])
        self.assertNotIn(before, self.owed_to(tid))
        self.assertNotIn(between, self.owed_to(tid))

    def test_d14_a_persons_message_queued_across_a_removal_and_an_add_is_owed_once_released(self):
        tid, sid, _ = self.human()
        self.add(tid, sid, DESK)
        self.head_wait()
        e = sminos.log_append(self.chan(DESK), sminos.writer_id(), "human", **{
            "from": "human", "text": "queued", "to": [{"session": sid, "alias": "a", "thread": tid}]})
        self.assertIsNone(e["seq"], "it waits in the queue for its writer's head: no position")
        sminos.forget_caches()
        self.assertEqual(self.owed_to(tid), [], "nothing in the log names it yet")
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.add(tid, sid, DESK)
        self.release()
        [released] = [x for x in sminos.log_read(self.chan(DESK)) if x["kind"] == "human"]
        self.assertEqual(released["ts"], e["ts"], "appended with the time it was said")
        self.assertGreater(released["seq"], self.debt_of(tid).boundary.get(released["writer"], 0))
        self.assertEqual(self.owed_to(tid), [(released["writer"], released["seq"])],
                         "its position is past the new boundary")


class HandOff(Debts, T1.Sessions):
    def test_d6_a_hand_off_carries_nothing_and_the_same_record_is_owed_to_the_session_that_goes_on(self):
        old, oproc, tid = self.member()
        self.add(tid, old, DESK)
        a = self.message(DESK, (old, tid))
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assertEqual(threads.get(tid)["current"], job)
        d = self.debt_of(tid)
        self.assertEqual((d.thread, d.session), (tid, job))
        b = self.message(DESK, (job, tid))
        self.assertEqual(self.owed_to(tid), [a, b], "whatever session an entry names")
        self.settle(tid, *a)
        self.assertEqual(self.owed_to(tid), [b], "one record, the thread's")
        for s in (old, job):
            self.assertFalse(os.path.exists(os.path.join(self.chan(DESK).home, "delivered", s + ".json")))

    def test_d6_d12_while_a_hand_offs_entry_is_open_the_debt_is_listed_and_owing_is_none(self):
        old, oproc, tid = self.member()
        self.add(tid, old, DESK)
        a = self.message(DESK, (old, tid))
        row = (self.p, self.row(old))   # read now: a view reconciles, and would finish the entry cut below
        job, _ = self.job(old)
        self.end(oproc)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        t = threads.get(tid)
        entry = t.get("pending")
        self.assertIsNotNone(entry, "the entry is open")
        self.assertEqual(self.owed_to(tid), [a], "an open entry hides no debt")
        self.assertIsNone(channels.owing(self.chan(DESK), t, row))
        code, lines = self.owed_cli()
        [line] = self.desk_lines(lines)
        self.assertIn("deliveries 1", line)
        self.assertEqual(threads.get(tid).get("pending"), entry, "the diagnostic left the entry as the cut did")


class Absorption(Debts, T1.LateHandOff):
    def test_d7_what_names_the_absorbed_thread_is_owed_to_no_one(self):
        for both in (True, False):
            with self.subTest(both=both):
                self.fresh()
                self.register()
                old, job, tid, theirs = self.late()
                if both:
                    self.add(tid, old, DESK)
                self.add(theirs, job, DESK)
                mine = self.message(DESK, (old, tid))
                lost = self.message(DESK, (job, theirs))
                self.assertEqual(self.owed_to(theirs), [lost])
                self.reconcile()
                self.assert_absorbed(old, job, tid, theirs)
                self.assertEqual(self.owed_to(tid), [mine],
                                 "its own, past its boundary as the merge left it (the absorbed record's where only "
                                 "it was in the channel); never the absorbed one's")
                after = self.message(DESK, (job, tid))
                self.message(DESK, (job, theirs))
                self.assertEqual(self.owed_to(tid), [mine, after])
                self.assertNotIn(theirs, [d.thread for d, _ in channels.owed_here(self.chan(DESK))])

    def test_d7_an_absorbed_threads_record_under_the_channel_stays_and_nothing_reads_it(self):
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        self.add(theirs, job, DESK)
        lost = self.message(DESK, (job, theirs))
        self.message(DESK, (job, theirs))
        self.settle(theirs, *lost)
        held = self.bytes_of(self.record_path(theirs))
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        self.assertEqual(self.bytes_of(self.record_path(theirs)), held)
        self.assertEqual(self.owed_to(tid), [])

    def test_d7_d12_while_the_absorptions_entry_is_open_nothing_is_owing_and_the_debt_is_listed(self):
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        mine = self.message(DESK, (job, tid))
        # The thread's row, read from another machine's copy of the log: a view here reconciles, and would
        # carry out the absorption the cut below is to leave open.
        with self.elsewhere() as there:
            row = (self.p, next(m for m in sminos.view_of(there).members if m.session == old))
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        t = threads.get(tid)
        entry = t["pending"]
        self.assertEqual(entry["op"], "absorb")
        self.assertEqual(self.owed_to(tid), [mine])
        self.assertIsNone(channels.owing(self.chan(DESK), t, row))
        code, lines = self.owed_cli()
        [line] = self.desk_lines(lines)
        self.assertIn("deliveries 1", line)
        self.assertEqual(threads.get(tid)["pending"], entry, "the diagnostic left the entry as the cut did")


class Refill(Debts, T1.Sessions):
    def test_d8_a_refills_new_occupant_is_owed_what_names_the_thread(self):
        old, seat_id = self.seated()
        self.add(seat_id, old, DESK)
        a = self.message(DESK, (old, seat_id))
        new, _, out = self.refill(seat_id)
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["current"], new, out)
        d = self.debt_of(seat_id)
        self.assertEqual((d.thread, d.session), (seat_id, new))
        b = self.message(DESK, (new, seat_id))
        self.assertEqual(self.owed_to(seat_id), [a, b])


    def test_d8_a_seat_repointed_to_a_lane_b_session_holds_no_membership_and_is_owed_nothing(self):
        old, seat_id = self.seated()
        self.add(seat_id, old, DESK)
        a = self.message(DESK, (old, seat_id))
        self.message(DESK, (old, seat_id))
        self.settle(seat_id, *a)
        held = self.bytes_of(self.record_path(seat_id))
        self.assertEqual(len(channels.owed_here(self.chan(DESK))), 1)
        new, _ = self.session(kind="bg")
        records.establish(new, T1.OWNED)
        records.set_controller(new, "B")
        code, out = self.cli("seat", "add", "g", "worker", "--session", new)
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        self.assertEqual(sminos.load_seat(sminos.meta_path(seat_id))["current"], new, "repointed by the verb")
        self.assertNotIn("channels", sminos.load_seat(sminos.meta_path(seat_id)), "the seat's keys dropped (CH1)")
        self.assertIsNone(self.debt_of(seat_id), "row D4: no membership, no debt")
        self.message(DESK, (new, seat_id))
        self.assertEqual(channels.owed_here(self.chan(DESK)), [])
        code, lines = self.owed_cli()
        self.assertEqual(self.desk_lines(lines), [], lines)
        self.assertEqual(self.bytes_of(self.record_path(seat_id)), held, "its record under the channel as it was")


class AgainAsAnother(Debts, T1.Sessions):
    def test_d11_d13_a_session_run_again_as_another_thread_brings_no_debt_and_a_late_import_is_its_threads(self):
        old, oproc, tid = self.member()
        self.add(tid, old, DESK)
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.session(sid=old, started=T1.ms_ago(-1))
        self.reconcile()
        again = threads.thread_of(old)["thread"]
        self.assertNotEqual(again, tid)
        early = self.message(DESK, (old, again))
        self.assertIsNone(self.owed_to(again), "in no channel: no debt, by session or otherwise")
        self.add(again, old, DESK)
        self.assertNotIn(early, self.owed_to(again), "held by the machine at its add")
        mine = self.message(DESK, (old, again))
        late = self.message(DESK, (old, tid))       # D13: names the thread whose old session `again` now holds
        self.assertEqual(self.owed_to(again), [mine])
        self.assertEqual(self.owed_to(tid), [late], "owed to the thread named, never to the session's holder")


class Reads(Debts, T1.Sessions):
    def row_and_record(self, sid, tid):
        return threads.get(tid), (self.p, self.row(sid))

    def test_d12_owing_reads_the_sessions_record_one_way(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.message(DESK, (sid, tid))
        t, row = self.row_and_record(sid, tid)
        o = channels.owing(self.chan(DESK), t, row)
        self.assertEqual((o.thread, o.session, o.project.id, o.member.session), (tid, sid, self.p.id, sid))
        self.assertEqual(o.reach, channels.reach_token(sid))
        self.assertIsNotNone(o.reach)
        self.assertIsNone(channels.owing(self.chan(DESK), t, None), "no row given: none, and none looked up")
        path = records.record_path(sid)
        with open(path, "rb") as f:
            kept = f.read()
        with open(path, "w") as f:
            f.write("{not json")
        self.assertIsNone(channels.owing(self.chan(DESK), t, row), "there and unreadable: it defers")
        self.assertEqual(self.debt_of(tid).thread, tid, "the debt is still listed")
        os.unlink(path)
        o = channels.owing(self.chan(DESK), t, row)
        self.assertIsNotNone(o, "not there at all: lane A, delivered to")
        self.assertIsNone(o.reach, "with the token an absent record gives")
        with open(path, "wb") as f:
            f.write(kept)
        records.set_controller(sid, "B")
        self.assertIsNone(channels.owing(self.chan(DESK), t, row), "lane B defers")
        code, lines = self.owed_cli()
        [line] = self.desk_lines(lines)
        self.assertIn("deliveries 1", line)

    def test_d12_a_thread_whose_own_record_cannot_be_read_is_attributed_no_debt_and_nothing_is_settled(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        a = self.message(DESK, (sid, tid))
        self.message(DESK, (sid, tid))
        self.settle(tid, *a)
        held = self.bytes_of(self.record_path(tid))
        with open(threads._human_path(tid), "w") as f:
            f.write("{torn")
        sminos.forget_caches()
        self.assertTrue(threads.unreadable(tid))
        self.assertEqual(channels.owed_here(self.chan(DESK)), [])
        code, lines = self.owed_cli()
        self.assertEqual(self.desk_lines(lines), [], lines)
        self.assertEqual(self.bytes_of(self.record_path(tid)), held)

    def test_a_delivery_record_that_cannot_be_read_claims_nothing_and_one_absent_is_empty(self):
        sid, _, tid = self.member()
        sid2, _, tid2 = self.member(name="other", charge="")
        self.add(tid, sid, DESK)
        self.add(tid2, sid2, DESK)
        a = self.message(DESK, (sid, tid), (sid2, tid2))
        self.assertEqual(channels.delivered(self.chan(DESK), tid), {}, "absent: an empty record")
        self.assertEqual(self.owed_to(tid2), [a], "owed from the boundary")
        whole = '"settled": 0, "pending": null, "attempts": 0'
        for bad in (b"{torn", b"[]", b'{"w": 3}', b'{"w": {"settled": "x"}}', b'{"w": {"attempts": []}}',
                    # an entry whose settled prefix cannot be known: no prefix, or one that is no count
                    b'{"w": {}}', b'{"w": {"settled": null, "pending": null, "attempts": 0}}',
                    b'{"w": {"pending": null, "attempts": 0}}', b'{"w": {"settled": true, "pending": null, "attempts": 0}}',
                    b'{"w": {"settled": -1, "pending": null, "attempts": 0}}',
                    # what every writer writes beside it, missing or mistyped
                    b'{"w": {"settled": 0, "attempts": 0}}', b'{"w": {"settled": 0, "pending": null}}',
                    b'{"w": {"settled": 0, "pending": "2", "attempts": 0}}',
                    # a mark out of shape, which the projects' loader would pass by and so drop
                    ('{"w": {%s, "revoked": "3"}}' % whole).encode(),
                    ('{"w": {%s, "revoked": [3, "4"]}}' % whole).encode(),
                    ('{"w": {%s, "held": [[3]]}}' % whole).encode(),
                    ('{"w": {%s, "held": [[3, 7]]}}' % whole).encode(),
                    ('{"w": {%s, "held": {"3": "t"}}}' % whole).encode(),
                    ('{"w": {"settled": 0, "pending": 3, "attempts": 1, "pushed": [3]}}').encode(),
                    ('{"w": {"settled": 0, "pending": 3, "attempts": 1, "pushed": [3, "nowhere"]}}').encode()):
            with self.subTest(bad=bad):
                os.makedirs(os.path.dirname(self.record_path(tid)), exist_ok=True)
                with open(self.record_path(tid), "wb") as f:
                    f.write(bad)
                self.assertIsNone(channels.delivered(self.chan(DESK), tid))
                self.assertIsNone(self.owed_to(tid), "nothing owed is claimed")
        code, lines = self.owed_cli()
        self.assertEqual(code, 1)
        self.assertIn("%s: cannot be inspected" % self.record_path(tid), "\n".join(lines))
        [line] = self.desk_lines(lines)
        self.assertIn("deliveries 1", line, "the other thread's debt is still counted")
        self.assertEqual(self.bytes_of(self.record_path(tid)), bad, "nothing written")
        with open(self.record_path(tid), "w") as f:
            f.write("{}")
        self.assertEqual(channels.delivered(self.chan(DESK), tid), {}, "an empty object is an empty record")
        self.assertEqual(self.owed_to(tid), [a])

    def test_a_record_that_is_a_link_to_nothing_is_there_and_cannot_be_read(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        self.message(DESK, (sid, tid))
        os.makedirs(os.path.dirname(self.record_path(tid)), exist_ok=True)
        os.symlink(os.path.join(self.home, "nowhere.json"), self.record_path(tid))
        self.assertIsNone(channels.delivered(self.chan(DESK), tid), "not absent: a file is there")
        self.assertIsNone(self.owed_to(tid))
        code, lines = self.owed_cli()
        self.assertEqual(code, 1)
        self.assertIn("%s: cannot be inspected" % self.record_path(tid), "\n".join(lines))
        self.assertEqual(self.desk_lines(lines), [], lines)

    def test_a_whole_record_reads_as_the_projects_loader_reads_it(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        a = self.message(DESK, (sid, tid))
        self.settle(tid, *a)
        b = self.message(DESK, (sid, tid))
        sminos.delivered_fail(self.chan(DESK), tid, *b)
        c = self.message(DESK, (sid, tid))
        sminos.delivered_held(self.chan(DESK), tid, *c, thread=tid)
        sminos.delivered_pushed(self.chan(DESK), tid, *b, sminos.PUSHED[0])
        got = channels.delivered(self.chan(DESK), tid)
        self.assertEqual(got, sminos.delivered_load(self.chan(DESK), tid))
        self.assertEqual((got[W1]["pending"], got[W1]["held"], got[W1]["pushed"]),
                         (b[1], {c[1]: tid}, [b[1], sminos.PUSHED[0]]), "every mark its writers write reads")

    def test_the_index_by_thread_is_built_once_for_a_log_however_many_threads_hold_the_channel(self):
        members = [self.member(name="m%d" % i, charge="") for i in range(4)]
        for sid, _, tid in members:
            self.add(tid, sid, DESK)
        self.message(DESK, *[(sid, tid) for sid, _, tid in members])
        sminos.forget_caches()
        with mock.patch.object(channels, "_addressed", side_effect=channels._addressed) as built:
            got = channels.owed_here(self.chan(DESK))
            self.assertEqual(len(got), 4)
            self.assertTrue(all(len(evs) == 1 for _, evs in got))
            self.assertEqual(built.call_count, 1, "one build for the log, not one a thread")
            sminos.forget_caches()
            channels.owed_here(self.chan(DESK))
            self.assertEqual(built.call_count, 1, "kept beside the log while no file of it moved")


class OwedLines(Debts, T1.Sessions):
    def test_daemon_owed_lists_a_channels_debt_under_the_threads_alias(self):
        sid, proc, tid = self.member(name="handy")
        self.add(tid, sid, DESK)
        self.message(DESK, (sid, tid))
        self.message(DESK, (sid, tid))
        code, lines = self.owed_cli()
        self.assertEqual(code, 1)
        [line] = self.desk_lines(lines)
        self.assertIn("deliveries 2 [%s → handy, %s → handy]" % (ref(W1, 1), ref(W1, 2)), line)

    def test_a_stopped_thread_that_is_held_waits_and_owes_nothing(self):
        sid, proc, tid = self.member(name="handy")
        self.add(tid, sid, DESK)
        self.message(DESK, (sid, tid))
        self.end(proc)
        sminos.forget_caches()
        self.assertTrue(sminos.hold_for(sid), "stopped, and not woken (its conversation is not here)")
        code, lines = self.owed_cli()
        [line] = self.desk_lines(lines)
        self.assertIn("waiting 1", line)
        self.assertIn("closed sessions 1 [%s → handy]" % ref(W1, 1), line)


class Cold(Debts, T1.LateHandOff):
    def snapshot(self):
        out = {}
        for top in (os.environ["SMINOS_HOME"], os.environ["HOME"]):
            for d, dirs, files in os.walk(top):
                out[d] = None
                for n in files:
                    p = os.path.join(d, n)
                    st = os.lstat(p)
                    out[p] = (st.st_mtime_ns, self.bytes_of(p) if os.path.isfile(p) else None)
        return out

    def test_daemon_owed_cold_over_an_open_entry_lists_the_debt_and_changes_no_file(self):
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        self.message(DESK, (job, tid))
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        self.assertEqual(threads.get(tid)["pending"]["op"], "absorb")
        before = self.snapshot()
        got = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), "daemon", "owed"],
                             capture_output=True, text=True, cwd=self.root, timeout=120)
        self.assertEqual(got.returncode, 1, got.stdout + got.stderr)
        [line] = self.desk_lines(got.stdout.splitlines())
        self.assertIn("deliveries 1 [%s → tardy]" % ref(W1, 1), line)
        self.assertEqual(self.snapshot(), before, "it only reads")


# ------------------------------------------------------------ an end and a return (D9, D10), a purge (D15)


class Returns(Debts, T1_ended.Ending):
    def ended_with_mail(self):
        """A stopped thread in the channel, a message held for it, then ended, and one gained while ended:
        (session, thread, the two messages)."""
        sid = self.closed()
        tid = threads.stamp(sid)
        self.add(tid, sid, DESK)
        held = self.message(DESK, (sid, tid))
        self.stopped_since(sid, 2 * T1_ended.PERIOD)
        self.sweep()
        self.assertTrue(threads.record_ended(threads.get(tid)))
        self.assertIsNone(self.debt_of(tid), "D9: no debt while it is ended")
        gained = self.message(DESK, (sid, tid))
        return sid, tid, [held, gained]

    def test_d3_a_thread_reopened_while_still_a_member_is_owed_what_was_held_and_its_boundary_stays(self):
        sid = self.closed()
        tid = threads.stamp(sid)
        self.add(tid, sid, DESK)
        began = threads.get(tid)["began"]
        held = self.message(DESK, (sid, tid))
        sminos.forget_caches()
        self.assertTrue(sminos.hold_for(sid), "stopped, and held")
        code, lines = self.owed_cli()
        [line] = self.desk_lines(lines)
        self.assertIn("waiting 1", line, "while held it waits")
        self.live(sid=sid, name="alpha")
        self.reconcile()
        sminos.forget_caches()
        self.assertFalse(sminos.hold_for(sid), "reopened")
        self.assertEqual(threads.get(tid)["began"], began, "a reopening is no return: where it began stays")
        self.assertEqual(self.owed_to(tid), [held])
        code, lines = self.owed_cli()
        [line] = self.desk_lines(lines)
        self.assertIn("deliveries 1", line, "now owed")
        self.settle(tid, *held)
        self.assertEqual(self.owed_to(tid), [], "and settled once by the record's writer")

    def test_d10_a_return_of_this_code_owes_neither_what_was_held_nor_what_came_while_ended(self):
        sid, tid, _ = self.ended_with_mail()
        self.live(sid=sid, name="alpha")
        self.reconcile()
        self.assertIsNone(threads.get(tid).get("ended"))
        self.assertEqual(self.owed_to(tid), [])
        after = self.message(DESK, (sid, tid))
        self.assertEqual(self.owed_to(tid), [after])

    def test_d10_a_return_that_keeps_the_earlier_boundary_owes_both(self):
        for how in ("unreadable", "older"):
            with self.subTest(how=how):
                self.fresh()
                self.register()
                sid, tid, both = self.ended_with_mail()
                if how == "unreadable":
                    def positions(cid):
                        raise sminos.PositionsUnread("the log of channel %s could not be listed: EIO" % cid[:8])
                    keeping = mock.patch.object(sminos, "channel_positions", positions)
                else:   # an older copy's return writes no positions
                    keeping = mock.patch.object(threads, "_began_anew", lambda view, raw: [])
                self.live(sid=sid, name="alpha")
                with keeping, contextlib.redirect_stderr(io.StringIO()):
                    self.reconcile()
                self.assertIsNone(threads.get(tid).get("ended"))
                self.assertEqual(self.owed_to(tid), both)


class Purged(Debts, T1.Sessions):
    def test_d15_a_seat_made_again_over_a_purged_seats_session_is_that_thread_with_its_record(self):
        sid, proc = self.session()
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.assertIsNotNone(threads.get(sid), "the seat's id is its session's")
        self.add(sid, sid, DESK)
        a = self.message(DESK, (sid, sid))
        self.settle(sid, *a)
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        self.assertIsNone(threads.get(sid), "purged")
        before = self.message(DESK, (sid, sid))       # reaches the machine before the seat is made again
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.add(sid, sid, DESK)
        self.assertEqual(threads.get(sid)["thread"], sid)
        late = self.message(DESK, (sid, sid), writer=W2, ts="2026-01-01T00:00:00.000Z")
        self.assertEqual(self.owed_to(sid), [late], "past the new boundary, whenever written; the earlier not")
        self.assertNotIn(before, self.owed_to(sid))
        self.assertEqual(channels.delivered(self.chan(DESK), sid)[W1]["settled"], a[1], "the first seat's record")


# ------------------------------------------------------------ the last check


class LastCheck(Debts, T1.Sessions):
    def owing_now(self, sid, tid):
        sminos.forget_caches()
        return channels.owing(self.chan(DESK), threads.get(tid), (self.p, self.row(sid)))

    def event(self, ws):
        w, seq = ws
        return next(e for e in sminos.log_read(self.chan(DESK)) if (e["writer"], e["seq"]) == (w, seq))

    def test_it_holds_on_files_as_they_are_and_fails_on_each_change(self):
        sid, _, tid = self.member()
        self.add(tid, sid, DESK)
        a = self.message(DESK, (sid, tid))
        o = self.owing_now(sid, tid)
        self.assertTrue(channels.still_owed(o))
        self.assertTrue(channels.still_owed(o, self.event(a), reach=True))
        # Removed: fails. Added again: holds, but the event is at or below the new boundary.
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.assertFalse(channels.still_owed(o))
        self.add(tid, sid, DESK)
        self.assertTrue(channels.still_owed(o))
        self.assertFalse(channels.still_owed(o, self.event(a)))
        b = self.message(DESK, (sid, tid))
        self.assertTrue(channels.still_owed(o, self.event(b)))
        # The session's record: unreadable defers; absent is lane A, but a change of reach with `reach`.
        path = records.record_path(sid)
        with open(path, "rb") as f:
            kept = f.read()
        with open(path, "w") as f:
            f.write("{torn")
        self.assertFalse(channels.still_owed(o))
        os.unlink(path)
        self.assertTrue(channels.still_owed(o), "absent: lane A")
        self.assertFalse(channels.still_owed(o, reach=True), "the token o was read with is the record's")
        absent = self.owing_now(sid, tid)
        self.assertTrue(channels.still_owed(absent, reach=True))
        with open(path, "wb") as f:
            f.write(kept)
        self.assertFalse(channels.still_owed(absent, reach=True), "a record written since is a change of reach")
        records.set_controller(sid, "B")
        self.assertFalse(channels.still_owed(o), "lane B")
        records.set_controller(sid, "A")
        self.assertTrue(channels.still_owed(o))
        # The thread's own file unreadable, then an open entry on it.
        with open(threads._human_path(tid), "rb") as f:
            rec = f.read()
        with open(threads._human_path(tid), "w") as f:
            f.write("{torn")
        sminos.forget_caches()
        self.assertFalse(channels.still_owed(o))
        with open(threads._human_path(tid), "wb") as f:
            f.write(rec)
        sminos.forget_caches()
        self.assertTrue(channels.still_owed(o))
        self.raw(tid, lambda r: r.update(pending={"op": "release", "session": sid}))
        self.assertFalse(channels.still_owed(o), "an open entry")

    def test_a_pass_that_lost_its_session_or_its_project_does_nothing(self):
        old, oproc, tid = self.member()
        self.add(tid, old, DESK)
        o = self.owing_now(old, tid)
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assertFalse(channels.still_owed(o), "handed off: the session is not the thread's current one")
        self.assertTrue(channels.still_owed(self.owing_now(job, tid)))
        # A join elsewhere: the captured project is no longer where the session is.
        n = self.owing_now(job, tid)
        other = self.project_of(self.repo("other"))
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": job}):
            code, out = self.cli("join", other.name)
        self.assertEqual(code, 0, out)
        self.assertFalse(channels.still_owed(n), "moved to another project")


if __name__ == "__main__":
    unittest.main()
