#!/usr/bin/env python3
"""Pushing and waking from a channel's log (CH2's M3:
docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md, the milestone's
"Seams" and "Proves"; Interfaces §3's second half), against the test engine:

- A message that lies in a channel's log and names a thread of this machine
  that is in the channel is pushed to the thread's current session once by
  the channel's delivery pass (sminos_channels.deliver, the daemon's channel
  pass, last), wakes a stopped thread that may be woken, and is held, owed,
  for one that may not; it is settled in the thread's delivery record under
  the channel and in no session's, and no file appears under any project.
- Its frame names the channel; its reply line names the channel's id and
  the first eight of the sender's thread, or, for a message that carries
  `from_project`, the frame says its sender is not in the channel and the
  line names the sender in its own project.
- The last check, under the thread's delivery lock and again before a push,
  around a wake's launch: a pass that lost its session (a hand-off, its two
  interleavings), that meets an open entry (from both sides), a move to
  another project (and CH1's tie), a change of lane, a record that cannot
  be read, a removal, an end, pushes and settles nothing; a session with no
  record at all and a home whose path holds a bracket are pushed to.
- A record that remembers an attempt the boundary has passed (normalize),
  and one whose writer's file could not be read.
- Membership read in the thread's own project, never the channel's log.
- A launch crossed by a change of reach, of the machine's policy and of the
  signer; a removal attempted meanwhile.
- A receipt found by its thread beside its session; swept on its thread's
  record.

The messages are put into the channel's log by the suite (the doors are
still shut): under another machine's writer, carrying `verified`, as an
import leaves one, or under this machine's own name with or without its
append receipt. Hermetic: test_wake's Engine (HOME, SMINOS_HOME and the
engine's state temporary; the engine first on PATH), test_channels_life's
channels, and T1's sessions.
Run: python3 -B sminos/tests/test_channels_delivery.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
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
from test_wake import wait_for  # noqa: E402
from test_wake_delivery import Deliveries  # noqa: E402
from test_channels_life import DESK, Life  # noqa: E402
import sminos_channels as channels  # noqa: E402
import sminos_policy  # noqa: E402

FAR = "beta"                                         # another machine's name
SENDER = "5e000001-0000-4000-8000-0000000000e1"      # a session of that machine
SENDER_THREAD = "5e0000a1-0000-4000-8000-0000000000a1"
ELSEWHERE = "0abc0001-0000-4000-8000-00000000c0de"   # a project of the sender's, for a sender that is no member
SIGNER = {"kind": "machine", "keyId": "key-beta"}
W1 = "%s/%s" % (FAR, SENDER)
W2 = "%s/5e000002-0000-4000-8000-0000000000e2" % FAR


class Channel(Life, Deliveries, T1.Sessions):
    """A channel registered here, threads of this machine in it, messages put into its log, and what its delivery
    pass does with them."""

    member = T1.Sessions.member   # T1's (a human-opened member), which its fixtures call; not Deliveries'

    def message(self, *to, writer=W1, kind="say", sender=SENDER_THREAD, text="hi", cid=DESK, **fields):
        """A message in the channel's log naming each (session, thread) of `to`, as an import leaves one: under
        another machine's writer, carrying `verified`. The event."""
        entries = [{"session": sid, "alias": "a", "thread": tid} for sid, tid in to]
        body = {"from": "human"} if kind == "human" else {"from": "sender", "thread": sender}
        body.update(to=entries, text=text, verified={"signer": SIGNER})
        body.update(fields)
        time.sleep(0.002)   # the merged log's order is by time
        e = sminos.log_append(self.chan(cid), writer, kind, **body)
        sminos.forget_caches()
        return e

    def deliver(self, cid=DESK):
        """The channel's delivery pass, in this process."""
        sminos.forget_caches()
        return channels.deliver(self.chan(cid))

    def apart(self, cid=DESK):
        """The channel's delivery pass in a process of its own (the daemon's): its Popen."""
        code = ("import json, sys; sys.path.insert(0, %r); import sminos, sminos_channels; "
                "print(json.dumps(sminos_channels.deliver(sminos.known_project(%r))))" % (SCRIPTS, cid))
        return subprocess.Popen([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

    def live(self, name="term-a", cid=DESK):
        """A live thread its human opened, with an inbox, in the channel: (thread, session, its inbox's file)."""
        sid = str(uuidlib.uuid4())
        received = self.terminal(sid, name)
        self.reconcile()
        tid = threads.stamp(sid)
        self.add(tid, sid, cid)
        return tid, sid, received

    def stopped(self, mode="auto", cid=DESK):
        """A closed thread its human opened, in the channel: (thread, session)."""
        tid, sid = self.human_thread(mode)
        self.add(tid, sid, cid)
        return tid, sid

    def got(self, received, text):
        """The frames of an inbox that carry `text`."""
        return [f for f in self.received(received) if text in f]

    def woken_got(self, sid, text):
        return [f for f in self.frames(sid) if text in f]

    def record_of(self, tid, cid=DESK):
        sminos.forget_caches()
        return channels.delivered(self.chan(cid), tid)

    def settled(self, tid, w, cid=DESK):
        return sminos._delivery(self.record_of(tid, cid) or {}, w)["settled"]

    def owed_to(self, tid, cid=DESK):
        """What the channel owes the thread now, as seqs of W1 and W2's events: [(writer, seq)]."""
        sminos.forget_caches()
        t = threads.get(tid)
        d = channels.debt(self.chan(cid), t) if t is not None else None
        got = channels.owed(d, sminos.log_read(self.chan(cid))) if d is not None else None
        return None if got is None else [(e["writer"], e["seq"]) for e in got]

    def inbox(self, sid, proc, name="i"):
        """An inbox for the process `proc` holding the session: the path of the file it appends every frame to."""
        sock = os.path.join(self.home, "%s-%s.sock" % (name, sid[:8]))
        received = sock + ".received"
        open(received, "a").close()
        server = subprocess.Popen([sys.executable, "-B", os.path.join(HERE, "inbox_standin.py"), sock, received])
        self.addCleanup(lambda: (server.kill(), server.wait()))
        wait_for(lambda: sminos.socket_ok(sock))
        self.peer_set(proc, messagingSocketPath=sock, nameSource="user")
        sminos.forget_caches()
        return received

    def live_member(self, name="handy"):
        """A live member its human opened (T1's), with an inbox, in the channel: (thread, session, process,
        its inbox's file)."""
        sid, proc, tid = self.member(name=name)
        received = self.inbox(sid, proc)
        self.add(tid, sid, DESK)
        return tid, sid, proc, received

    def before_last_check(self, meanwhile):
        """meanwhile() runs once, as a pass that chose an event waits before its last check for it (the check
        holder_push makes, given the event): what another process does at that moment."""
        real, done = channels.still_owed, []

        def still_owed(o, e=None, reach=False):
            if e is not None and not done:
                done.append(e)
                meanwhile()
            return real(o, e, reach)
        return mock.patch.object(channels, "still_owed", still_owed)

    def project_files(self):
        """Every file under every project's home here but the channels': what delivery must leave alone."""
        out = {}
        for p in sminos.known_projects():
            for root, _, names in os.walk(p.home):
                for n in names:
                    path = os.path.join(root, n)
                    try:
                        st = os.stat(path)
                    except FileNotFoundError:
                        continue
                    out[path] = (st.st_size, st.st_mtime_ns)
        return out


def failing(text, why="failed:refused"):
    """Every push of a frame that carries `text` fails before it reached the session (`why`); the rest go."""
    real = sminos.push_member
    return mock.patch.object(sminos, "push_member",
                             lambda m, frame, *a, **k: why if text in frame else real(m, frame, *a, **k))


def turn_read_only():
    """The machine's policy turned read-only, as its owner turns it."""
    path = sminos_policy.policy_path()
    with open(path) as f:
        pol = json.load(f)
    pol["read_only"] = True
    with open(path, "w") as f:
        json.dump(pol, f)


def cut_over_to_an_endpoint():
    """This machine cut over to an endpoint that decides no reach: a signer's revocation binds its deliveries."""
    sminos.write_json(sminos.sibling_module("sminos_rl10").identity_path(), {
        "org": "org-1", "hub": "http://127.0.0.1:9", "name": sminos.host_name(), "former": {},
        "ref": "machine-ref-1", "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z",
        "build": "b"}, mode=0o600)
    sminos.audience_module().keep_capabilities([])
    sminos.forget_caches()


def revoke_the_signer():
    sminos.sibling_module("sminos_rl10").keep_revoked({"version": 2, "devices": [], "members": [],
                                                       "keys": [SIGNER["keyId"]]}, True)


def reply_of(frame):
    """The reply line a frame closes with: the tag it names, or None."""
    import re
    m = re.search(r'say "@([^ "]+) <your reply>"\]', frame)
    return m.group(1) if m else None


# ------------------------------------------------------------ pushed, woken, held


class Pushed(Channel):
    def test_a_message_to_a_live_member_is_pushed_once_by_the_daemons_tick_and_settled_in_the_threads_record(self):
        tid, sid, received = self.live()
        self.reconcile()
        before = self.project_files()
        e = self.message((sid, tid), text="the schema changed")
        code, out = self.cli("daemon", "tick")
        self.assertEqual(code, 0, out)
        [frame] = self.got(received, "the schema changed")
        self.assertIn("[sminos chat desk %s from sender → @you]" % sminos.event_ref(e), frame)
        self.assertEqual(reply_of(frame), "%s/%s" % (DESK, SENDER_THREAD[:8]),
                         "the channel's id and the first eight of the sender's thread")
        self.assertEqual(self.settled(tid, W1), e["seq"])
        self.assertFalse(os.path.exists(os.path.join(self.chan(DESK).home, "delivered", sid + ".json")),
                         "settled in the thread's record, in no session's")
        self.deliver()
        self.cli("daemon", "tick")
        self.assertEqual(len(self.got(received, "the schema changed")), 1, "once")
        changed = {p for p, st in self.project_files().items() if before.get(p) != st}
        self.assertEqual({p for p in changed if "/delivered/" in p or "/outbox" in p or "/cursors/" in p}, set(),
                         "no file under any project for a channel's delivery")

    def test_a_stopped_member_is_woken_and_pushed_once_opened_by_the_line(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="wake for this")
        total, reached = self.deliver()
        self.assertEqual(total, 1)
        self.assertEqual(len(self.resumes(sid)), 1, "one launch, under its own id")
        [frame] = self.woken_got(sid, "wake for this")
        self.assertIn("[sminos chat desk %s from sender → @you]" % sminos.event_ref(e), frame)
        self.assertIn("[sminos] ", frame, "the line after a wake")
        self.assertEqual(self.settled(tid, W1), e["seq"])
        self.deliver()
        self.assertEqual(len(self.resumes(sid)), 1, "nothing launched again")

    def test_a_thread_that_may_not_be_woken_is_held_owed_and_marked_and_pushed_once_when_reopened(self):
        tid, sid = self.stopped(mode="plan")
        e = self.message((sid, tid), text="held for now")
        self.deliver()
        self.assertEqual(self.resumes(sid), [], "not woken: it is held for mode")
        self.assertEqual(self.owed_to(tid), [(W1, e["seq"])], "owed")
        self.assertEqual(self.record_of(tid)[W1]["held"], {e["seq"]: tid}, "marked for the thread, in its record")
        self.assertEqual(self.record_of(tid)[W1]["attempts"], 0, "no attempt counted")
        received = self.terminal(sid)
        self.deliver()
        self.assertEqual(len(self.got(received, "held for now")), 1)
        self.assertEqual(self.owed_to(tid), [])
        self.deliver()
        self.assertEqual(len(self.got(received, "held for now")), 1, "once")

    def test_a_held_message_is_pushed_once_when_the_thread_is_woken(self):
        tid, sid = self.stopped(mode="plan")
        self.message((sid, tid), text="held then woken")
        self.deliver()
        self.assertEqual(self.resumes(sid), [])
        self.ceiling("bypassPermissions")
        self.edit(tid)   # the record touched: the hold read again
        transcript = sminos.transcript_now(sid)
        with open(transcript, "a") as f:   # its last turn in a mode that does not ask
            f.write(json.dumps({"type": "user", "permissionMode": "auto",
                                "message": {"role": "user", "content": "go"}}) + "\n")
        sminos.forget_caches()
        self.deliver()
        self.assertEqual(len(self.resumes(sid)), 1)
        self.assertEqual(len(self.woken_got(sid, "held then woken")), 1)
        self.deliver()
        self.assertEqual(len(self.woken_got(sid, "held then woken")), 1, "once")

    def test_an_event_for_the_live_alone_settles_recorded_for_a_stopped_member_and_wakes_nothing(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="whoever runs", wake=True)
        self.deliver()
        self.assertEqual(self.resumes(sid), [])
        self.assertEqual(self.owed_to(tid), [])
        self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_two_messages_of_one_writer_are_pushed_in_order_and_a_failure_stops_that_writer(self):
        tid, sid, received = self.live()
        a = self.message((sid, tid), text="first")
        b = self.message((sid, tid), text="second")
        c = self.message((sid, tid), writer=W2, text="other writer")
        with failing("first"):
            self.deliver()
        self.assertEqual(self.got(received, "second"), [], "stopped behind the failure")
        self.assertEqual(len(self.got(received, "other writer")), 1, "another writer goes on")
        self.assertEqual(self.record_of(tid)[W1]["pending"], a["seq"])
        self.assertEqual(self.record_of(tid)[W1]["attempts"], 1)
        self.deliver()
        frames = self.received(received)
        order = [i for i, f in enumerate(frames) for t in ("first", "second") if t in f]
        self.assertEqual(len(order), 2)
        self.assertLess(next(i for i, f in enumerate(frames) if "first" in f),
                        next(i for i, f in enumerate(frames) if "second" in f), "in order")
        self.assertEqual(self.settled(tid, W1), b["seq"])
        self.assertEqual(self.settled(tid, W2), c["seq"])



# ------------------------------------------------------------ the frame, and a writer that is no member


class Framed(Channel):
    def test_a_message_from_outside_the_channel_says_so_and_its_reply_line_names_the_sender_in_its_project(self):
        tid, sid, received = self.live()
        inside = self.message((sid, tid), text="from a member")
        outside = self.message((sid, tid), text="from outside", from_project=ELSEWHERE)
        self.deliver()
        [a] = self.got(received, "from a member")
        [b] = self.got(received, "from outside")
        self.assertIn("[sminos chat desk %s from sender → @you" % sminos.event_ref(inside), a)
        self.assertNotIn("(not in desk)", a)
        self.assertEqual(reply_of(a), "%s/%s" % (DESK, SENDER_THREAD[:8]))
        self.assertIn("[sminos chat desk %s from sender (not in desk) → @you" % sminos.event_ref(outside), b,
                      "the clause first after the alias")
        self.assertEqual(reply_of(b), "%s/%s" % (ELSEWHERE, SENDER[:8]), "the sender in its own project")
        self.assertEqual(self.settled(tid, W1), outside["seq"], "both pushed, both settled")

    def test_a_persons_message_has_no_reply_line(self):
        tid, sid, received = self.live()
        self.message((sid, tid), writer="%s/human" % FAR, kind="human", text="from a person")
        self.deliver()
        [f] = self.got(received, "from a person")
        self.assertIsNone(reply_of(f))

    def test_no_host_kind_is_written_by_a_push_or_a_wake_from_a_channel(self):
        tid, sid, received = self.live()
        stid, ssid = self.stopped()
        self.message((sid, tid), (ssid, stid), text="to both")
        self.deliver()
        self.assertEqual(len(self.got(received, "to both")), 1)
        self.assertEqual(len(self.woken_got(ssid, "to both")), 1)
        for p in sminos.known_projects() + [self.chan(DESK)]:
            kinds = {e["kind"] for e in sminos.log_read(p)}
            self.assertFalse(kinds & {"message", "question", "answered"}, (p.name, kinds))
        self.assertFalse(os.path.exists(os.path.join(self.chan(DESK).home, "host")), "nothing in its host store")


# ------------------------------------------------------------ the thread for the debt, the session for the process


    def test_a_channels_unread_count_leaves_out_the_threads_own_messages_and_no_others(self):
        tid, sid, received = self.live()
        chan = self.chan(DESK)
        other = str(uuidlib.uuid4())
        before = [
            {"writer": sminos.writer_id(sid), "seq": 1, "kind": "say", "thread": other, "text": "as another thread"},
            {"writer": "%s/%s" % (FAR, str(uuidlib.uuid4())), "seq": 1, "kind": "say", "thread": tid,
             "text": "the thread's own, from its earlier session"},
        ]
        e = {"writer": W1, "seq": 9, "kind": "say", "from": "sender", "thread": SENDER_THREAD, "text": "now",
             "to": [{"session": sid, "alias": "a", "thread": tid}]}
        frame = sminos.frame_of(chan, e, before + [e], sid, {}, thread=tid)
        self.assertIn("| unread 1]", frame, "what this session said as another thread is unread to this one")
        p_frame = sminos.frame_of(self.p, e, before + [e], sid, {})
        self.assertIn("| unread 1]", p_frame, "a project's count by the session, as before")

    def test_a_projects_frames_count_by_the_sessions_own_cursor_and_a_channels_by_the_threads_key(self):
        tid, sid, _ = self.live()
        sminos.cursor_save(self.p, sid, {"w": 3})
        self.assertEqual(sminos.delivery_cursor(self.p, sid), {"w": 3}, "a project's: the session's, as before")
        chan = self.chan(DESK)
        sminos.cursor_save(chan, tid, {"w": 5})   # an older copy's key, the bare id
        sminos.cursor_save(chan, channels.THREAD_CURSOR % tid, {"w": 2})
        o = channels.owing(chan, threads.get(tid), channels.own_row(threads.get(tid)))
        self.assertEqual(sminos.delivery_cursor(chan, o.thread, o), {"w": 2}, "a channel's: the thread's own key")


class HandOff(Channel):
    def handed(self, old, oproc):
        """The thread handed off to a job with an inbox: (the job, its inbox's file)."""
        job, jproc = T1.Sessions.job(self, old)
        jreceived = self.inbox(job, jproc, "j")
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        return job, jreceived

    def test_d6_a_message_pushed_to_a_live_member_is_settled_in_the_threads_record_and_in_no_sessions(self):
        tid, old, oproc, received = self.live_member()
        a = self.message((old, tid), text="before")
        self.deliver()
        self.assertEqual(len(self.got(received, "before")), 1)
        job, jreceived = self.handed(old, oproc)
        self.assertEqual(threads.get(tid)["current"], job)
        b = self.message((old, tid), text="named by the old session")
        self.deliver()
        self.assertEqual(len(self.got(jreceived, "named by the old session")), 1,
                         "pushed to the session that continues the thread, whatever session the entry names")
        self.assertEqual(self.settled(tid, W1), b["seq"])
        for s in (old, job):
            self.assertFalse(os.path.exists(os.path.join(self.chan(DESK).home, "delivered", s + ".json")))
        self.assertGreater(b["seq"], a["seq"])

    def test_a_pass_that_lost_its_session_to_a_hand_off_before_its_last_check_pushes_and_settles_nothing(self):
        tid, old, oproc, received = self.live_member()
        e = self.message((old, tid), text="mid hand-off")
        got = {}
        with self.before_last_check(lambda: got.update(zip(("job", "jreceived"), self.handed(old, oproc)))):
            self.deliver()
        self.assertEqual(self.got(received, "mid hand-off"), [], "the old session receives nothing")
        self.assertEqual(self.got(got["jreceived"], "mid hand-off"), [], "nor the new one, by that pass")
        self.assertEqual(self.settled(tid, W1), 0, "nothing settled")
        self.assertEqual(self.record_of(tid).get(W1, {}).get("attempts", 0), 0, "no attempt counted")
        self.deliver()
        self.assertEqual(len(self.got(got["jreceived"], "mid hand-off")), 1, "the next pass: one frame")
        self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_a_push_made_whose_settlement_waits_across_a_hand_off_is_pushed_once(self):
        tid, old, oproc, received = self.live_member()
        e = self.message((old, tid), text="settling")
        real, seen = sminos.delivered_settle, {}

        def settle(project, key, writer, seq):
            if project.id == DESK and not seen:
                seen["job"], seen["jreceived"] = self.handed(old, oproc)
                other = self.apart()
                time.sleep(1.0)
                seen["waited"] = other.poll() is None
                real(project, key, writer, seq)
                seen["other"] = other
                return
            real(project, key, writer, seq)
        with mock.patch.object(sminos, "delivered_settle", settle):
            self.deliver()
        out, err = seen["other"].communicate(timeout=60)
        self.assertEqual(seen["other"].returncode, 0, err)
        self.assertTrue(seen["waited"], "the pass for the new session waits on the thread's lock")
        self.assertEqual(len(self.got(received, "settling")), 1)
        self.assertEqual(self.got(seen["jreceived"], "settling"), [], "and pushes nothing more")
        self.assertEqual(self.settled(tid, W1), e["seq"])


    def test_a_hand_off_that_lands_after_the_last_check_and_before_the_push_settles_nothing(self):
        tid, old, oproc, received = self.live_member()
        e = self.message((old, tid), text="handed meanwhile")
        real, got = sminos.push_member, {}

        def push_member(m, frame, *a, **k):
            # The push's own read of the peer comes after every check: the hand-off lands just before it.
            if "handed meanwhile" in frame and not got:
                got["job"], got["jreceived"] = self.handed(old, oproc)
            return real(m, frame, *a, **k)
        with mock.patch.object(sminos, "push_member", push_member):
            self.deliver()
        self.assertEqual(self.got(received, "handed meanwhile"), [], "the old inbox gets nothing")
        self.assertEqual(self.settled(tid, W1), 0, "never `recorded`: the session that continues it is owed it")
        self.assertEqual(self.record_of(tid).get(W1, {}).get("attempts", 0), 0, "no attempt counted")
        self.deliver()
        self.assertEqual(len(self.got(got["jreceived"], "handed meanwhile")), 1, "the next pass: one frame")
        self.assertEqual(self.settled(tid, W1), e["seq"])


    def test_a_push_that_fails_across_a_hand_off_counts_no_attempt_and_its_successor_is_pushed_it(self):
        tid, old, oproc, received = self.live_member()
        e = self.message((old, tid), text="failed across")
        for _ in range(sminos.DELIVERY_ATTEMPTS - 1):
            sminos.delivered_fail(self.chan(DESK), tid, W1, e["seq"])
        control, got = sminos.control_module(), {}
        real = control.push_live

        def push_live(peer, session, text, *a, **k):
            # The hand-off lands after push_member found the peer and before the push binds it: nothing goes.
            if "failed across" in text and not got:
                got["job"], got["jreceived"] = self.handed(old, oproc)
                raise sminos.SendFailed("before", "the inbox went")
            return real(peer, session, text, *a, **k)
        with mock.patch.object(control, "push_live", push_live):
            self.deliver()
        self.assertEqual(self.got(received, "failed across"), [])
        self.assertEqual(self.got(got["jreceived"], "failed across"), [])
        w = self.record_of(tid)[W1]
        self.assertEqual((w["settled"], w["attempts"]), (0, sminos.DELIVERY_ATTEMPTS - 1),
                         "not given up: the failure was no attempt of the thread's")
        self.deliver()
        self.assertEqual(len(self.got(got["jreceived"], "failed across")), 1, "pushed to the session that continues it")
        self.assertEqual(self.settled(tid, W1), e["seq"])


    def test_a_pass_stopped_at_a_failure_across_a_hand_off_reports_no_outcome_for_the_event(self):
        tid, old, oproc, received = self.live_member()
        e = self.message((old, tid), text="no outcome")
        sminos.forget_caches()
        t = threads.get(tid)
        o = channels.owing(self.chan(DESK), t, channels.own_row(t))
        control, got = sminos.control_module(), {}
        real = control.push_live

        def push_live(peer, session, text, *a, **k):
            if "no outcome" in text and not got:
                got["job"], got["jreceived"] = self.handed(old, oproc)
                raise sminos.SendFailed("before", "the inbox went")
            return real(peer, session, text, *a, **k)
        with mock.patch.object(control, "push_live", push_live):
            result = sminos.deliver_next(self.chan(DESK), o.member, owing=o)
        self.assertEqual([x for x, _ in result["outcomes"] if x["seq"] == e["seq"] and x["writer"] == W1], [],
                         "a stopped pass publishes nothing for the event it stopped at")
        self.assertGreaterEqual(result["pending"], 1, "still pending")


class Boundary(Channel):
    def test_an_attempt_the_boundary_has_passed_is_cleared_and_the_writers_next_message_goes(self):
        tid, sid, received = self.live()
        first = self.message((sid, tid), text="first")
        with failing("first"):
            self.deliver()
        self.assertEqual(self.record_of(tid)[W1]["pending"], first["seq"])
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.add(tid, sid, DESK)
        second = self.message((sid, tid), text="second")
        self.deliver()
        self.deliver()
        self.assertEqual(len(self.got(received, "second")), 1, "pushed once")
        self.assertEqual(self.got(received, "first"), [], "and the first never")
        w = self.record_of(tid)[W1]
        self.assertEqual((w["settled"], w["pending"], w["attempts"]), (second["seq"], None, 0))

    def test_a_writer_whose_file_cannot_be_read_keeps_its_mark_and_is_attempted_again(self):
        tid, sid, received = self.live()
        first = self.message((sid, tid), text="first")
        with failing("first"):
            self.deliver()
        kept = self.record_of(tid)[W1]
        path = os.path.join(self.chan(DESK).home, "log", W1.replace("/", ".") + ".jsonl")
        self.assertTrue(os.path.exists(path), path)
        # Its writer's file out of the selection's reach (a read that fails leaves it out as an absent one does).
        os.rename(path, path + ".aside")
        other = self.message((sid, tid), writer=W2, text="other writer")
        self.deliver()
        self.assertEqual(len(self.got(received, "other writer")), 1)
        self.assertEqual(self.record_of(tid)[W1], kept, "its mark and its count as they were")
        os.rename(path + ".aside", path)
        self.deliver()
        self.assertEqual(len(self.got(received, "first")), 1, "attempted again")
        self.assertEqual(self.settled(tid, W1), first["seq"])
        self.assertEqual(self.settled(tid, W2), other["seq"])

    def test_an_event_held_and_since_passed_by_a_new_boundary_is_never_pushed_and_its_mark_goes(self):
        tid, sid = self.stopped(mode="plan")
        held = self.message((sid, tid), text="held then passed")
        self.deliver()
        self.assertIn(held["seq"], self.record_of(tid)[W1]["held"])
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.add(tid, sid, DESK)
        received = self.terminal(sid)
        nxt = self.message((sid, tid), text="after the add")
        self.deliver()
        self.assertEqual(self.got(received, "held then passed"), [], "never pushed")
        self.assertEqual(len(self.got(received, "after the add")), 1)
        self.assertNotIn("held", self.record_of(tid)[W1], "its mark gone once the writer's next event settled")
        self.assertEqual(self.settled(tid, W1), nxt["seq"])


    def test_a_pass_whose_owing_predates_a_removal_and_an_add_settles_nothing_the_new_boundary_passed(self):
        for case in ("held, for the live alone", "read-only"):
            with self.subTest(case=case):
                if case == "read-only":
                    tid, sid, received = self.live(name="ro")
                    self.message((sid, tid), text="case " + case)
                else:
                    tid, sid = self.stopped(mode="plan")
                    self.message((sid, tid), text="case " + case, wake=True)
                sminos.forget_caches()
                t = threads.get(tid)
                o = channels.owing(self.chan(DESK), t, channels.own_row(t))
                self.assertIsNotNone(o)
                self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
                self.add(tid, sid, DESK)
                self.assertEqual(self.owed_to(tid), [], "at or below the new boundary: owed nothing")
                with mock.patch.object(sminos_policy, "read_only", return_value=case == "read-only"):
                    sminos.deliver_next(self.chan(DESK), o.member, owing=o)
                self.assertEqual(self.settled(tid, W1), 0, "nothing settled on the old choice")



# ------------------------------------------------------------ the thread's own project, and its lane, at the last check


class LastCheck(Channel):
    def moved(self, sid, tie=False):
        """The session joins another project (with `tie`, its `joined` there at the very millisecond of the
        source's, CH1's tie, the retirement here not written yet): that project."""
        other = self.project_of(self.repo("other"))
        if not tie:
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
                code, out = self.cli("join", other.name)
            self.assertEqual(code, 0, out)
            return other
        source = threads.in_effect(self.own(sid))
        sminos.write_override(sid, other.id)
        sminos.forget_caches()
        with mock.patch.object(channels, "restate", return_value=False):
            self.reconcile(other)
        path = os.path.join(other.home, "log", sminos.writer_id(sid).replace("/", ".") + ".jsonl")
        with open(path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        for e in events:
            if e["kind"] == "joined":
                e["ts"] = source["ts"]
        with open(path, "w") as f:
            f.write("".join(json.dumps(e) + "\n" for e in events))
        sminos.forget_caches()
        self.assertEqual(threads.in_effect(self.own(sid, other))["ts"], source["ts"], "the same moment")
        return other

    def test_a_move_a_tie_a_change_of_lane_and_an_unreadable_record_before_the_last_check_push_nothing(self):
        for case in ("join", "tie", "lane B", "unreadable"):
            with self.subTest(case=case):
                tid, sid, proc, received = self.live_member(name="m-" + case.replace(" ", ""))
                e = self.message((sid, tid), text="case " + case)
                kept = {}

                def meanwhile():
                    if case in ("join", "tie"):
                        kept["other"] = self.moved(sid, tie=case == "tie")
                    elif case == "lane B":
                        records.set_controller(sid, "B")
                    else:
                        path = records.record_path(sid)
                        with open(path, "rb") as f:
                            kept["record"] = f.read()
                        with open(path, "w") as f:
                            f.write("{torn")
                    sminos.forget_caches()
                with self.before_last_check(meanwhile):
                    self.deliver()
                self.assertEqual(self.got(received, "case " + case), [], "nothing pushed")
                self.assertEqual(self.settled(tid, W1), 0, "nothing settled, never `recorded`")
                self.assertEqual(self.record_of(tid).get(W1, {}).get("attempts", 0), 0)
                if case in ("join", "tie"):
                    if case == "tie":
                        self.reconcile()   # the move's retirement lands here, and the tie ends
                    self.reconcile(kept["other"])
                    self.deliver()
                    self.assertEqual(len(self.got(received, "case " + case)), 1,
                                     "the next pass captures the new project and pushes one frame")
                    self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_a_session_with_no_record_at_all_is_lane_a_and_is_pushed_to(self):
        tid, sid, proc, received = self.live_member()
        os.unlink(records.record_path(sid))
        sminos.forget_caches()
        e = self.message((sid, tid), text="no record")
        self.deliver()
        self.assertEqual(len(self.got(received, "no record")), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_a_membership_changed_after_the_choice_pushes_and_settles_nothing(self):
        for case in ("removed", "removed and added", "ended"):
            with self.subTest(case=case):
                tid, sid, proc, received = self.live_member(name="c-" + case.replace(" ", ""))
                self.message((sid, tid), text="case " + case)

                def meanwhile():
                    if case.startswith("removed"):
                        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
                    if case == "removed and added":
                        self.add(tid, sid, DESK)
                    if case == "ended":
                        self.raw(tid, lambda r: r.update(ended={"at": sminos.now(), "reason": "retire"}))
                    sminos.forget_caches()
                with self.before_last_check(meanwhile):
                    self.deliver()
                self.assertEqual(self.got(received, "case " + case), [], "nothing pushed")
                self.assertEqual(self.settled(tid, W1), 0, "nothing settled")


class Bracket(Channel):
    """A home whose path holds a bracket, which the base's membership scan reads as a pattern
    (_membership_in_effect's glob, behind last_project and member_project_now; a TECH-DEBT row). That scan
    keeps a thread from being placed in a channel there at all (CH1's change answers `between`), so the record is
    staged by hand and the Owing given: what is proved is that delivery's own last check reads by literal
    paths."""

    def setUp(self):
        real = T1.tempfile.mkdtemp
        with mock.patch.object(T1.tempfile, "mkdtemp", lambda dir=None, **kw: real(prefix="b[1]", dir=dir)):
            super().setUp()

    def test_the_last_check_holds_and_a_member_is_pushed_to_under_a_home_whose_path_holds_a_bracket(self):
        self.assertIn("[", os.environ["SMINOS_HOME"])
        sid = str(uuidlib.uuid4())
        received = self.terminal(sid)
        self.reconcile()
        tid = threads.stamp(sid)
        self.raw(tid, lambda r: r.update(channels=[DESK], began={DESK: {}}))
        e = self.message((sid, tid), text="bracketed")
        sminos.forget_caches()
        row = next(m for m in sminos.view_of(self.p).members if m.session == sid)
        o = channels.owing(self.chan(DESK), threads.get(tid), (self.p, row))
        self.assertIsNotNone(o)
        self.assertTrue(channels.still_owed(o, e))
        self.assertEqual(self.deliver(), (1, [row.alias]), "the channel's own pass finds its row, as anywhere")
        self.assertEqual(len(self.got(received, "bracketed")), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])


# ------------------------------------------------------------ membership read in the thread's own project


class OwnProject(Channel):
    def test_a_held_member_whose_inbox_fails_once_stays_held_owed_with_no_attempt_and_is_pushed_after(self):
        tid, sid = self.stopped(mode="plan")
        e = self.message((sid, tid), text="held inbox")
        self.deliver()
        self.assertIn(e["seq"], self.record_of(tid)[W1]["held"])
        received = self.terminal(sid)
        with failing("held inbox", "failed:the inbox refused"):
            self.deliver()
        w = self.record_of(tid)[W1]
        self.assertEqual((w["settled"], w["attempts"]), (0, 0), "held, owed, no attempt counted")
        self.assertIn(e["seq"], w["held"])
        self.deliver()
        self.assertEqual(len(self.got(received, "held inbox")), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_a_member_whose_own_writer_in_the_channels_log_holds_an_old_retirement_is_pushed_and_woken(self):
        tid, sid, received = self.live()
        stid, ssid = self.stopped()
        for s in (sid, ssid):
            # An older copy's `joined` in the channel's log, which CH1's reconciliation undoes (`retired` moved).
            sminos.log_append(self.chan(DESK), sminos.writer_id(s), "joined", session=s, alias="old",
                              name_source="derived", machine=sminos.host_name())
        sminos.forget_caches()
        sminos.view_of(self.chan(DESK))
        self.assertEqual(sminos.latest_membership(sminos._own_events(self.chan(DESK), sid)), "retired",
                         "a live session's undone in the channel's log (CH1's `retired` `moved`)")
        self.assertEqual(sminos.latest_membership(sminos._own_events(self.chan(DESK), ssid)), "joined",
                         "a closed session's left as it is")
        self.message((sid, tid), (ssid, stid), text="despite the old line")
        self.deliver()
        self.assertEqual(len(self.got(received, "despite the old line")), 1)
        self.assertEqual(len(self.woken_got(ssid, "despite the old line")), 1, "woken as any member")

    def test_a_thread_in_the_channel_with_a_private_record_is_pushed_to(self):
        tid, sid, received = self.live()
        records.set_policy(sid, lambda access, shares: ("private", []))
        sminos.forget_caches()
        e = self.message((sid, tid), text="private")
        self.deliver()
        self.assertEqual(len(self.got(received, "private")), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])


    def test_a_synced_moves_destination_is_checked_as_a_name_before_any_lookup(self):
        tid, sid, received = self.live()
        # As a synced or hand-edited line could say it: written as retire_moved writes one, its destination no name.
        sminos.lifecycle(self.p, sid, "retired", required=False, by="", reason="moved", project="../escape")
        sminos.forget_caches()
        real, asked = sminos.registration, []
        with mock.patch.object(sminos, "registration", lambda pid: (asked.append(pid), real(pid))[1]):
            self.assertIsNone(channels._project_now(sid))
        self.assertNotIn("../escape", asked, "never read as a path")



# ------------------------------------------------------------ an open entry, from both sides


class OpenEntry(Channel, T1.LateHandOff):
    def proc_of(self, sid):
        rec = self.record(sid)
        return type("P", (), {"pid": rec["pid"]})()

    def test_nothing_is_delivered_over_an_absorptions_open_entry_and_the_pass_leaves_it_as_it_was(self):
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        e = self.message((job, tid), text="over an open entry")
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        entry = threads.get(tid)["pending"]
        self.assertEqual((entry["op"], threads.get(tid)["current"]), ("absorb", job))
        self.deliver()   # the channel's delivery by itself: a tick's reconciliation would finish the entry first
        self.assertEqual(self.got(jreceived, "over an open entry"), [], "nothing pushed to the provisional process")
        self.assertEqual(self.settled(tid, W1), 0, "nothing settled")
        self.assertEqual(threads.get(tid)["pending"], entry, "the entry as the cut left it")
        self.reconcile()   # the daemon's own reconciliation finishes it
        self.assertIsNone(threads.get(tid).get("pending"))
        self.deliver()
        self.assertEqual(len(self.got(jreceived, "over an open entry")), 1, "then delivered, once")
        self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_a_pass_for_another_member_of_the_project_leaves_an_absorptions_open_entry_as_it_was(self):
        stid, ssid, sproc, sreceived = self.live_member(name="second")
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        self.message((job, tid), text="over the open entry")
        e = self.message((ssid, stid), text="to the other member")
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        entry = threads.get(tid)["pending"]
        self.deliver()
        self.assertEqual(threads.get(tid).get("pending"), entry,
                         "the other member's row read without a reconciliation: the entry as the cut left it")
        self.assertEqual(len(self.got(sreceived, "to the other member")), 1)
        self.assertEqual(self.settled(stid, W1), e["seq"])
        self.assertEqual(self.got(jreceived, "over the open entry"), [])

    # -- the notice of a say the hub withheld (the frontier review's F10, and its wave review)

    NOTICE = "your message to ghost was not delivered"

    def withheld_say(self, sid, thread=None):
        """A say of `sid` into the channel, stamped with `thread` (none: unstamped), that the hub withheld: the
        channel's HubLog that settled it."""
        import sminos_hublog as hublog
        w = sminos.writer_id(sid)
        e = sminos.log_append(self.chan(DESK), w, "say", **{
            "from": "s", "to": [{"session": str(uuidlib.uuid4()), "alias": "ghost", "thread": str(uuidlib.uuid4())}],
            "text": "the secret words", **({"thread": thread} if thread else {})})
        sminos.forget_caches()
        hl = hublog.HubLog(self.chan(DESK), {"key": None, "machine": sminos.host_name()})
        self.assertTrue(hl.withhold_own(w, e["seq"]))
        return hl

    def queued_notices(self, hl):
        return hl.state().get("notices") or []

    def shown(self, received):
        time.sleep(0.3)   # the inbox appends what it took on its own thread
        return [f for f in self.received(received) if self.NOTICE in f]

    def test_a_notice_waits_out_an_unsettled_hand_off_and_goes_to_the_session_that_goes_on(self):
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        hl = self.withheld_say(old, tid)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        sminos.forget_caches()
        self.assertEqual(threads.get(tid)["pending"]["op"], "absorb")
        hl.show_notices()
        self.assertEqual(self.shown(jreceived), [], "not while the entry is open")
        self.assertEqual(len(self.queued_notices(hl)), 1, "kept for a later pass")
        self.reconcile()
        sminos.forget_caches()
        hl.show_notices()
        self.assertEqual(len(wait_for(lambda: self.shown(jreceived), timeout=10)), 1, "the session that goes on with the thread")
        self.assertEqual(self.queued_notices(hl), [])

    def test_a_notice_of_the_absorbed_thread_never_goes_to_the_absorbers_session(self):
        old, job, tid, theirs = self.late()
        self.add(theirs, job, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        hl = self.withheld_say(job, theirs)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        sminos.forget_caches()
        self.assertEqual((threads.get(theirs)["current"], threads.get(theirs).get("pending")), (job, None),
                         "its own file still names the session")
        self.assertEqual(threads.current_record(job, fresh=True)["thread"], tid, "the session is the absorber's now")
        hl.show_notices()
        self.assertEqual(self.shown(jreceived), [], "not the absorber's session")
        self.reconcile()
        sminos.forget_caches()
        hl.show_notices()
        self.assertEqual(self.shown(jreceived), [], "nor once the absorption is done")
        self.assertEqual(self.queued_notices(hl), [], "dropped with the thread it was for")

    def test_a_notice_waits_out_an_entry_opened_on_the_fresh_record(self):
        """The second reading (G9): an entry opened on the thread's record after the notice's first read of it,
        as the fresh record (current_record) shows it, defers the notice too."""
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        hl = self.withheld_say(old, tid)
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        sminos.forget_caches()
        opened = threads.get(tid)
        self.assertEqual((opened["pending"]["op"], opened["current"]), ("absorb", job))
        real = threads.get
        before = {k: v for k, v in opened.items() if k != "pending"}   # the record as read before the entry opened
        with mock.patch.object(threads, "get", lambda t: before if t == tid else real(t)):
            hl.show_notices()
        self.assertEqual(self.shown(jreceived), [], "not while the fresh record holds the entry")
        self.assertEqual(len(self.queued_notices(hl)), 1, "kept for a later pass")

    def test_a_notice_is_kept_while_its_seat_is_vacant_between_occupants(self):
        """The second reading (G9): a seat being refilled holds no session (`current` empty) and has not ended:
        its notice waits for the next occupant, never dropped."""
        sid, proc, tid = self.member(name="seated")
        self.add(tid, sid, DESK)
        received = self.inbox(sid, proc)
        hl = self.withheld_say(sid, tid)
        real = threads.get
        with mock.patch.object(threads, "get", lambda t: dict(real(t), current="") if t == tid else real(t)):
            hl.show_notices()
        self.assertEqual(len(self.queued_notices(hl)), 1, "kept while the seat is vacant")
        hl.show_notices()
        self.assertEqual(len(wait_for(lambda: self.shown(received), timeout=10)), 1, "shown to its occupant")

    def test_an_unstamped_say_into_a_channel_tells_no_session(self):
        sid, proc, _ = self.member(name="loose")
        received = self.inbox(sid, proc)
        hl = self.withheld_say(sid)
        self.assertEqual(self.queued_notices(hl), [], "no thread to tell: nothing queued")
        d = hl.state()
        hl.save({**d, "notices": [{"writer": sminos.writer_id(sid), "seq": 1, "session": sid, "to": "ghost",
                                   "ts": sminos.now(ms=True)}]})   # one queued by an earlier copy
        hl.notices_owed = None
        hl.show_notices()
        self.assertEqual(self.shown(received), [], "never by a session id alone")
        self.assertEqual(self.queued_notices(hl), [])

    def test_d7_after_an_absorption_what_names_the_thread_is_pushed_and_what_named_the_absorbed_one_is_not(self):
        old, job, tid, theirs = self.late()
        self.add(tid, old, DESK)
        self.add(theirs, job, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        self.message((job, theirs), text="to the absorbed")
        self.reconcile()
        self.assert_absorbed(old, job, tid, theirs)
        mine = self.message((job, tid), text="to the thread that goes on")
        self.message((job, theirs), text="to the absorbed, after")
        self.deliver()
        self.assertEqual(len(self.got(jreceived, "to the thread that goes on")), 1)
        self.assertEqual(self.got(jreceived, "to the absorbed"), [], "owed to no one")
        self.assertEqual(self.settled(tid, W1), mine["seq"])

    def test_no_owing_for_a_thread_whose_session_is_another_threads_now(self):
        old, job, tid, theirs = self.late()
        self.add(theirs, job, DESK)
        self.message((job, theirs), text="to the absorbed")
        with self.elsewhere() as there:
            row = (self.p, next(m for m in sminos.view_of(there).members if m.session == job))
        with self.kill_after_begin(), self.assertRaises(Killed):
            self.reconcile()
        sminos.forget_caches()
        t = threads.get(theirs)
        self.assertEqual((t["current"], t.get("pending")), (job, None), "its own file names the session, no entry")
        self.assertEqual(threads.current_record(job, fresh=True)["thread"], tid, "the session is the absorber's now")
        self.assertIsNone(channels.owing(self.chan(DESK), t, row))

    def test_a_pass_chosen_for_the_provisional_thread_and_let_go_after_the_begin_pushes_nothing(self):
        old, job, tid, theirs = self.late()
        self.add(theirs, job, DESK)
        jreceived = self.inbox(job, self.proc_of(job), "j")
        self.message((job, theirs), text="for the provisional thread")
        # The provisional thread's row, read from another machine's copy of the log: a view here reconciles, and
        # would carry the absorption out before the pass chose.
        with self.elsewhere() as there:
            row = (self.p, next(m for m in sminos.view_of(there).members if m.session == job))
        begun = []

        def begin():
            with self.kill_after_begin():
                try:
                    self.reconcile()
                except Killed:
                    begun.append(True)
            self.assertEqual(threads.get(tid)["pending"]["op"], "absorb")
            self.assertIsNone(threads.get(theirs).get("pending"), "its own file names the session, no entry")
        with self.before_last_check(begin), mock.patch.object(channels, "own_row", lambda record: row):
            self.deliver()
        self.assertEqual(begun, [True], "the absorption began while the pass waited before its last check")
        self.assertEqual(self.got(jreceived, "for the provisional thread"), [], "nothing pushed")
        self.assertEqual(self.settled(theirs, W1), 0, "nothing settled")


# ------------------------------------------------------------ a wake's launch and the last check


class Launch(Channel):
    def stalled(self, tid, sid, meanwhile):
        """The channel's pass in a process of its own, the engine's launch stalled at its barrier while
        meanwhile() runs; then the barrier lifted. The pass's output."""
        self.switch("barrier")
        p = self.apart()
        self.assertTrue(wait_for(lambda: self.launches() >= 1, timeout=30), "the launch entered")
        try:
            meanwhile()
        finally:
            os.unlink(os.path.join(self.state, "barrier"))
        out, err = p.communicate(timeout=120)
        self.assertEqual(p.returncode, 0, err)
        sminos.forget_caches()
        return out

    def test_a_change_of_reach_across_the_launch_hands_nothing_over_and_launches_nothing_twice(self):
        tid, sid = self.stopped()
        self.assertIsNotNone(records.read(sid), "the session has a record")
        e = self.message((sid, tid), text="across a change of reach")
        self.stalled(tid, sid, lambda: records.set_policy(sid, lambda access, shares: ("private", [])))
        self.assertEqual(self.launches(), 1)
        self.assertEqual(self.woken_got(sid, "across a change of reach"), [], "no text handed to it")
        self.assertEqual(self.owed_to(tid), [(W1, e["seq"])], "still owed")
        self.assertEqual(self.record_of(tid).get(W1, {}).get("attempts", 0), 0)
        self.deliver()
        self.assertEqual(len(self.woken_got(sid, "across a change of reach")), 1, "pushed to the process that runs")
        self.assertEqual(self.launches(), 1, "no second launch")

    def test_the_machine_turned_read_only_across_the_launch_refuses_an_outside_event(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="read-only meanwhile")
        self.stalled(tid, sid, turn_read_only)
        self.assertEqual(self.woken_got(sid, "read-only meanwhile"), [], "no text")
        self.assertEqual(self.settled(tid, W1), e["seq"], "refused as the check before a push refuses it")
        self.assertEqual(self.owed_to(tid), [])

    def test_a_signer_revoked_across_the_launch_hands_nothing_over_and_its_event_is_marked(self):
        tid, sid = self.stopped()
        cut_over_to_an_endpoint()
        e = self.message((sid, tid), text="revoked meanwhile")
        self.stalled(tid, sid, revoke_the_signer)
        self.assertEqual(self.woken_got(sid, "revoked meanwhile"), [], "no text")
        self.assertEqual(self.record_of(tid)[W1].get("revoked"), None, "passed by the prefix in order")
        self.assertEqual(self.settled(tid, W1), e["seq"], "marked, never delivered")
        self.assertEqual(self.owed_to(tid), [])

    def test_a_removal_attempted_during_the_launch_is_busy_and_lands_after_the_push(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="under the wake's hold")
        tried = {}

        def remove():
            tried["outcome"] = channels.change(tid, DESK, "remove", sid, lock_until=time.time() + 0.5)
        self.stalled(tid, sid, remove)
        self.assertEqual(tried["outcome"].state, "failed")
        self.assertEqual(tried["outcome"].why, "wake", "busy under the wake's hold")
        self.assertEqual(len(self.woken_got(sid, "under the wake's hold")), 1, "handed over: a member under the hold")
        self.assertEqual(self.settled(tid, W1), e["seq"])
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied", "it lands after")

    def test_a_removal_made_before_the_wakes_hold_starts_no_process_and_the_event_is_not_owed(self):
        tid, sid = self.stopped()
        self.message((sid, tid), text="removed first")
        with self.before_last_check(lambda: self.assertEqual(
                channels.change(tid, DESK, "remove", sid).state, "applied")):
            self.deliver()
        self.assertEqual(self.launches(), 0, "no process started")
        self.assertIsNone(self.owed_to(tid), "not owed: no longer in the channel")


    def test_a_wake_whose_hold_is_busy_while_the_session_reads_live_launches_nothing(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="no hold, no launch")
        real_hold, real_live, busy, live = sminos.launch_hold, sminos.live_now, [True], [True]

        def launch_hold(thread_id):
            # The wake's hold busy once (another's transition), the session reading live at that moment.
            return (None, "sweep") if busy and busy.pop() else real_hold(thread_id)

        def live_now(session):
            return live.pop() if live else real_live(session)
        with mock.patch.object(sminos, "launch_hold", launch_hold), mock.patch.object(sminos, "live_now", live_now):
            self.deliver()
        self.assertEqual(self.resumes(sid), [], "nothing launched without the wake's own hold")
        self.assertEqual(self.settled(tid, W1), 0, "nothing settled")
        self.assertEqual(self.owed_to(tid), [(W1, e["seq"])], "still owed")
        self.deliver()
        self.assertEqual(len(self.resumes(sid)), 1)
        self.assertEqual(len(self.woken_got(sid, "no hold, no launch")), 1, "the next pass wakes it")


    def test_a_change_of_reach_while_the_wake_waits_for_its_lock_launches_nothing(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="reach changed at the lock")
        real, once = sminos.launch_hold, []

        def launch_hold(thread_id):
            # The wake waits for its lock; meanwhile the session's access changes (its lane and thread as they were).
            if not once:
                once.append(True)
                records.set_policy(sid, lambda access, shares: ("private", []))
            return real(thread_id)
        with mock.patch.object(sminos, "launch_hold", launch_hold):
            self.deliver()
        self.assertEqual(once, [True])
        self.assertEqual(self.launches(), 0, "nothing launched on the answer the access change made stale")
        self.assertEqual(self.owed_to(tid), [(W1, e["seq"])], "still owed")
        self.assertEqual(self.record_of(tid).get(W1, {}).get("attempts", 0), 0)
        self.deliver()
        self.assertEqual(self.launches(), 1)
        self.assertEqual(len(self.woken_got(sid, "reach changed at the lock")), 1, "the next pass wakes it, once")

    def test_a_change_of_reach_while_the_wake_writes_its_line_launches_nothing(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="reach changed at the line")
        real, once = threads.wake_line, []

        def wake_line(*a, **k):
            # The wake waits on the record's lock to write its line; meanwhile the session's access changes.
            if not once:
                once.append(True)
                records.set_policy(sid, lambda access, shares: ("private", []))
            return real(*a, **k)
        with mock.patch.object(threads, "wake_line", wake_line):
            self.deliver()
        self.assertEqual(once, [True])
        self.assertEqual(self.launches(), 0, "the channel's whole check, the reach in it, at the launch boundary")
        self.assertEqual(self.owed_to(tid), [(W1, e["seq"])], "still owed")
        self.assertIsNone((self.waking(tid, sid) or {}).get("line"), "its line taken back")
        self.deliver()
        self.assertEqual(self.launches(), 1)
        self.assertEqual(len(self.woken_got(sid, "reach changed at the line")), 1, "the next pass wakes it, once")

    def at_the_line(self, meanwhile):
        real, once = threads.wake_line, []

        def wake_line(*a, **k):
            # The wake waits on the record's lock to write its line; meanwhile() runs then.
            if not once:
                once.append(True)
                meanwhile()
            return real(*a, **k)
        return mock.patch.object(threads, "wake_line", wake_line), once

    def test_the_machine_turned_read_only_while_the_wake_writes_its_line_launches_nothing(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="read-only at the line")
        patch, once = self.at_the_line(turn_read_only)
        with patch:
            self.deliver()
        self.assertEqual(once, [True])
        self.assertEqual(self.launches(), 0, "the read-only policy read at the launch boundary")
        self.assertIsNone((self.waking(tid, sid) or {}).get("line"), "its line taken back")
        self.deliver()
        self.assertEqual(self.settled(tid, W1), e["seq"], "refused by the next pass, as before a push")
        self.assertEqual(self.launches(), 0)

    def test_a_signer_revoked_while_the_wake_writes_its_line_launches_nothing(self):
        tid, sid = self.stopped()
        cut_over_to_an_endpoint()
        e = self.message((sid, tid), text="revoked at the line")
        patch, once = self.at_the_line(revoke_the_signer)
        with patch:
            self.deliver()
        self.assertEqual(once, [True])
        self.assertEqual(self.launches(), 0, "the revocation read at the launch boundary")
        self.deliver()
        self.assertEqual(self.settled(tid, W1), e["seq"], "marked by the next pass, never delivered")
        self.assertEqual(self.launches(), 0)

    def test_a_session_turned_lane_b_while_the_wake_writes_its_line_launches_nothing(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="lane b at the line")
        real, once = threads.wake_line, []

        def wake_line(*a, **k):
            # The wake waits on the record's lock to write its line; meanwhile the session turns lane B.
            if not once:
                once.append(True)
                records.set_controller(sid, "B")
            return real(*a, **k)
        with mock.patch.object(threads, "wake_line", wake_line):
            self.deliver()
        self.assertEqual(once, [True])
        self.assertEqual(self.launches(), 0, "the lane read at the launch boundary")
        self.assertEqual(self.settled(tid, W1), 0, "nothing settled")
        self.assertEqual((self.record_of(tid).get(W1) or {}).get("attempts", 0), 0, "no attempt counted")
        self.assertIsNone((self.waking(tid, sid) or {}).get("line"), "its line taken back")
        self.assertGreater(e["seq"], 0)

    def test_a_removal_and_a_reopening_while_the_wakes_lock_is_busy_push_nothing(self):
        tid, sid = self.stopped()
        self.message((sid, tid), text="removed while busy")
        real_hold, busy, got = sminos.launch_hold, [True], {}

        def launch_hold(thread_id):
            if busy and busy.pop():
                # Busy (another's transition); meanwhile the thread is removed and its session reopened.
                self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
                got["received"] = self.terminal(sid)
                return None, "sweep"
            return real_hold(thread_id)
        with mock.patch.object(sminos, "launch_hold", launch_hold):
            self.deliver()
        self.assertEqual(self.got(got["received"], "removed while busy"), [], "the reopened session gets nothing")
        self.assertEqual(self.settled(tid, W1), 0)
        self.assertEqual(self.resumes(sid), [])

    def test_a_woken_process_that_stops_before_the_push_leaves_the_event_held_starting_and_marked(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="woken then gone")
        real, once = sminos.push_member, []

        def push_member(m, frame, *a, **k):
            # No process answered by the push (the woken one stopped first): what push_member answers then.
            if "woken then gone" in frame and not once:
                once.append(True)
                return "recorded"
            return real(m, frame, *a, **k)
        with mock.patch.object(sminos, "push_member", push_member):
            self.deliver()
        self.assertEqual(len(self.resumes(sid)), 1)
        w = self.record_of(tid).get(W1, {})
        self.assertEqual(w.get("held"), {e["seq"]: tid}, "held for its thread: `starting`")
        self.assertEqual((w.get("settled", 0), w.get("attempts", 0)), (0, 0), "owed, no attempt counted")
        self.deliver()
        self.assertEqual(len(self.woken_got(sid, "woken then gone")), 1, "then pushed, once")
        self.assertEqual(len(self.resumes(sid)), 1, "no second launch")
        self.assertEqual(self.settled(tid, W1), e["seq"])


    def test_a_thread_ended_and_its_session_reopened_at_the_wakes_look_is_pushed_nothing(self):
        tid, sid = self.stopped()
        self.message((sid, tid), text="ended at the look")
        real, got = sminos.wake_member, {}

        def wake_member(*a, **k):
            # Past holder_push's check, before the wake looks: the thread ends, and its session runs again.
            if not got:
                self.raw(tid, lambda r: r.update(ended={"at": sminos.now(), "reason": "retire"}))
                got["received"] = self.terminal(sid)
                sminos.forget_caches()
                self.assertIsNone(threads.current_record(sid, fresh=True), "no current thread")
            return real(*a, **k)
        with mock.patch.object(sminos, "wake_member", wake_member):
            self.deliver()
        self.assertEqual(self.got(got["received"], "ended at the look"), [], "nothing pushed to its session")
        self.assertEqual(self.settled(tid, W1), 0, "nothing settled for the ended thread")
        self.assertEqual(self.resumes(sid), [])


# ------------------------------------------------------------ the last check after receipt planning


class Planned(Channel):
    """holder_push's last check made by the receipts' planner, after every wait the planning holds: it reads what
    the check after a launch reads, and the push goes to the process it was made for."""

    def at_the_planners_check(self, meanwhile):
        """meanwhile() runs once, as the planner, past its waits, makes the last check with the session's reach."""
        real, done = channels.still_owed, []

        def still_owed(o, e=None, reach=False):
            if reach and e is not None and not done:
                done.append(e)
                meanwhile()
            return real(o, e, reach)
        return mock.patch.object(channels, "still_owed", still_owed), done

    def test_the_machine_turned_read_only_during_receipt_planning_refuses_an_outside_event(self):
        tid, sid, received = self.live()
        e = self.message((sid, tid), text="read-only while planned")
        patch, done = self.at_the_planners_check(turn_read_only)
        with patch:
            self.deliver()
        self.assertEqual(len(done), 1, "the planner made its check")
        self.assertEqual(self.got(received, "read-only while planned"), [], "nothing handed over")
        self.assertEqual(self.settled(tid, W1), e["seq"], "refused as the check after a launch refuses it")
        self.assertEqual(self.owed_to(tid), [])

    def test_a_signer_revoked_during_receipt_planning_hands_nothing_over_and_its_event_is_marked(self):
        tid, sid, received = self.live()
        cut_over_to_an_endpoint()
        e = self.message((sid, tid), text="revoked while planned")
        patch, done = self.at_the_planners_check(revoke_the_signer)
        with patch:
            self.deliver()
        self.assertEqual(len(done), 1, "the planner made its check")
        self.assertEqual(self.got(received, "revoked while planned"), [], "nothing handed over")
        self.assertEqual(self.settled(tid, W1), e["seq"], "marked, never delivered")
        self.assertEqual(self.owed_to(tid), [])

    def test_a_legacy_push_goes_to_the_process_the_planner_checked_and_never_to_its_replacement(self):
        tid, sid, proc, received = self.live_member()
        e = self.message((sid, tid), text="to the process checked")
        got = {}

        def restarted():
            # Past the mode's choice for the process looked at: it ends, and another process holds the session.
            self.end(proc)
            _, again = self.session(sid=sid)
            got["received"] = self.inbox(sid, again, "again")
        patch, done = self.at_the_planners_check(restarted)
        with patch:
            self.deliver()
        self.assertEqual(len(done), 1, "the planner made its check")
        self.assertEqual(self.got(got["received"], "to the process checked"), [],
                         "nothing to a process no check was made for")
        self.assertEqual(self.owed_to(tid), [(W1, e["seq"])], "still owed")
        self.assertEqual((self.record_of(tid).get(W1) or {}).get("attempts", 0), 0, "no attempt counted")
        self.deliver()
        self.assertEqual(len(self.got(got["received"], "to the process checked")), 1, "the next pass, once")
        self.assertEqual(self.settled(tid, W1), e["seq"])


# ------------------------------------------------------------ a project's delivery as it was (B11)


class ProjectsAsBefore(Channel):
    """What the channels' fixes to the push and the wake changed in a channel and nowhere else: a project's log is
    delivered as it was."""

    def to_member(self, sid, text, wake=False):
        """An event of the project's log addressed to the session (an @all's `wake` with `wake`)."""
        writer = "testhost/%s" % uuidlib.uuid4()
        fields = {"from": "k", "to": [{"session": sid, "alias": "x"}], "text": text}
        if wake:
            fields["wake"] = True
        e = sminos.log_append(self.p, writer, "say", **fields)
        sminos.forget_caches()
        return e

    def project_member(self, sid):
        sminos.forget_caches()
        return next(m for m in sminos.view_of(self.p).members if m.session == sid)

    def test_a_projects_legacy_push_goes_to_the_process_that_holds_the_session_at_the_push(self):
        tid, sid, proc, received = self.live_member()
        self.to_member(sid, "to whoever holds it")
        hd, got = sminos.holder_module(), {}
        real = hd.plan

        def plan(*a, **k):
            out = real(*a, **k)
            if out is not None and out.kind == "legacy" and "received" not in got:
                # Past the mode's choice for the process looked at: it ends, and another holds the session.
                self.end(proc)
                _, again = self.session(sid=sid)
                got["received"] = self.inbox(sid, again, "again")
            return out
        with mock.patch.object(hd, "plan", plan):
            sminos.deliver_next(self.p, self.project_member(sid))
        self.assertIn("received", got)
        self.assertEqual(len(self.got(got["received"], "to whoever holds it")), 1, "pushed on this pass, as before")

    def test_a_projects_event_for_the_live_alone_whose_receipt_was_never_admitted_stays_owed(self):
        tid, sid = self.stopped()
        e = self.to_member(sid, "to whoever runs", wake=True)
        hd = sminos.holder_module()
        keyhash = hd.key_hash(self.p.id, sid, e["writer"], e["seq"])
        with open(hd._receipt_path(keyhash), "w") as f:   # handed to a process that is gone, never admitted
            json.dump({"v": 1, "id": "%s.%s" % (keyhash, "0" * 16),
                       "key": {"project": self.p.id, "session": sid, "writer": e["writer"], "seq": e["seq"]},
                       "hash": sminos.event_hash(e), "words": None, "created": sminos.now(ms=True),
                       "attempt": {"n": 1, "pid": 1, "start": 1, "launch": "l", "body": "full", "state": "pushed",
                                   "at": sminos.now(ms=True)},
                       "released": None, "admitted": None, "handed": True}, f)
        sminos.deliver_next(self.p, self.project_member(sid))
        self.assertTrue(hd.exists(self.p.id, sid, e), "its receipt kept, as before")
        self.assertIn(e["seq"], [x["seq"] for x in sminos.owed(self.p, self.project_member(sid))], "still owed")
        self.assertEqual(self.resumes(sid), [])

    def test_a_projects_wake_reads_nothing_again_at_the_launch_boundary(self):
        tid, sid = self.stopped()
        real, once = threads.wake_line, []

        def wake_line(*a, **k):
            if not once:
                once.append(True)
                records.set_controller(sid, "B")
            return real(*a, **k)
        with mock.patch.object(threads, "wake_line", wake_line):
            sminos.wake(threads.get(tid), sid, due=True)
        self.assertEqual(once, [True])
        self.assertEqual(self.launches(), 1, "launched as before: no channel's check to make")


# ------------------------------------------------------------ a receipt and the thread it was for


class Receipts(Channel):
    def receipt(self, cid, session, e, thread, admitted=False):
        """A receipt written by hand (test_wake_delivery's Awaiting): handed to a process that is gone, keyed by
        the session and the thread."""
        hd = sminos.holder_module()
        keyhash = hd.key_hash(cid, session, e["writer"], e["seq"], thread)
        with open(hd._receipt_path(keyhash), "w") as f:
            json.dump({"v": 1, "id": "%s.%s" % (keyhash, "0" * 16),
                       "key": {"project": cid, "session": session, "writer": e["writer"], "seq": e["seq"],
                               "thread": thread},
                       "hash": sminos.event_hash(e), "words": None, "created": sminos.now(ms=True),
                       "attempt": {"n": 1, "pid": 1, "start": 1, "launch": "l", "body": "full", "state": "pushed",
                                   "at": sminos.now(ms=True)},
                       "released": None, "admitted": sminos.now(ms=True) if admitted else None, "handed": True}, f)
        self.assertTrue(hd.exists(cid, session, e, thread))
        self.assertFalse(hd.exists(cid, session, e), "a receipt by session alone is another")
        return keyhash

    def test_two_threads_one_event_names_over_one_sessions_receipt_each_get_their_own_frame(self):
        for admitted in (False, True):
            with self.subTest(admitted=admitted):
                old, oproc, tid = self.member(name="first" + str(int(admitted)))
                self.add(tid, old, DESK)
                job, jproc = T1.Sessions.job(self, old)
                jreceived = self.inbox(job, jproc, "j")
                self.reconcile()
                self.end(oproc)
                self.reconcile()
                _, again_proc = self.session(sid=old, started=T1.ms_ago(-1))
                self.reconcile()
                again = threads.thread_of(old)["thread"]
                self.assertNotEqual(again, tid, "the old session runs again as another thread")
                received = self.inbox(old, again_proc, "a")
                self.add(again, old, DESK)
                e = self.message((old, tid), (old, again), text="to both, admitted %s" % admitted)
                self.receipt(DESK, old, e, tid, admitted=admitted)
                self.deliver()
                self.assertEqual(len(self.got(received, "to both")), 1, "the second thread's own frame, once")
                self.assertEqual(len(self.got(jreceived, "to both")), 1, "the first thread's, in its session now")
                self.assertEqual(self.settled(again, W1), e["seq"], "settled on its own push")
                self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_an_event_for_the_live_alone_whose_receipt_was_never_admitted_settles_for_a_stopped_thread(self):
        tid, sid = self.stopped()
        everyone = self.message((sid, tid), text="to whoever runs", wake=True)
        named = self.message((sid, tid), text="named after it")
        self.receipt(DESK, sid, everyone, tid)   # handed to a process that is gone, never admitted
        self.deliver()
        self.assertEqual(self.woken_got(sid, "to whoever runs"), [], "nothing for the live alone to a stopped thread")
        self.assertEqual(len(self.resumes(sid)), 1, "the named message that follows wakes it")
        self.assertEqual(len(self.woken_got(sid, "named after it")), 1)
        self.assertEqual(self.settled(tid, W1), named["seq"], "neither stays first owed")
        self.assertFalse(sminos.holder_module().exists(DESK, sid, everyone, tid), "its receipt settled with it")

    def test_an_event_for_the_live_alone_is_not_settled_on_a_process_that_went_live_while_its_receipt_was_read(self):
        tid, sid = self.stopped()
        everyone = self.message((sid, tid), text="to whoever runs now", wake=True)
        self.receipt(DESK, sid, everyone, tid)   # handed to a process that is gone, never admitted
        hd, got = sminos.holder_module(), {}
        real = hd.plan

        def plan(*a, **k):
            # The receipt read for the pass (no process seen before it); meanwhile a process of the session starts.
            out = real(*a, **k)
            if k.get("existing_only") and "received" not in got:
                got["received"] = self.terminal(sid)
            return out
        with mock.patch.object(hd, "plan", plan):
            self.deliver()
        self.assertIn("received", got)
        self.assertEqual(self.owed_to(tid), [(W1, everyone["seq"])], "still owed: the thread is not stopped")
        self.assertTrue(hd.exists(DESK, sid, everyone, tid), "its receipt kept")
        self.deliver()
        self.assertEqual(len(self.got(got["received"], "to whoever runs now")), 1, "pushed to the live process, once")
        self.assertEqual(self.settled(tid, W1), everyone["seq"])

    def test_a_channels_receipt_is_swept_on_the_record_of_its_thread_never_on_a_seats_by_its_session(self):
        seat = str(uuidlib.uuid4())              # a seat's thread id: its first session's
        other = str(uuidlib.uuid4())             # the thread the receipt was for, that session's now
        e = self.message((seat, other), text="swept")
        hd = sminos.holder_module()
        keyhash = self.receipt(DESK, seat, e, other)
        sminos._delivered_write(self.chan(DESK), seat, {W1: sminos._entry(e["seq"])})   # the seat's, settled past
        hd.sweep(sminos.known_project)
        self.assertTrue(os.path.exists(hd._receipt_path(keyhash)), "the seat's record never sweeps it")
        sminos._delivered_write(self.chan(DESK), other, {W1: sminos._entry(e["seq"])})
        hd.sweep(sminos.known_project)
        self.assertFalse(os.path.exists(hd._receipt_path(keyhash)), "its thread's does")

    def test_a_receipts_key_is_todays_without_a_thread(self):
        hd = sminos.holder_module()
        self.assertEqual(hd.key_hash("p", "s", "w", 1),
                         __import__("hashlib").sha256(json.dumps(["p", "s", "w", 1]).encode()).hexdigest()[:24])
        self.assertNotEqual(hd.key_hash("p", "s", "w", 1, "t"), hd.key_hash("p", "s", "w", 1))


    def test_a_projects_receipt_lookups_call_key_hash_as_they_always_did(self):
        hd = sminos.holder_module()
        real, calls = hd.key_hash, []

        def key_hash(*a, **k):
            calls.append((a, k))
            return real(*a, **k)
        e = {"writer": W1, "seq": 1}
        with mock.patch.object(hd, "key_hash", key_hash):
            hd.exists("p", "s", e)
            hd.admitted("p", "s", e)
            hd.words_of("p", "s", e)
            hd.handed("p", "s", e)
            hd.settled("p", "s", e)
            hd.plan("p", "s", e, "h", None, existing_only=True, prepare=False)
        self.assertEqual(calls, [(("p", "s", W1, 1), {})] * 6, "no thread argument at all for a project")


    def test_an_admitted_receipt_of_an_earlier_membership_settles_nothing_on_an_owing_taken_before(self):
        for entry in ("deliver_next", "deliver_reach"):
            with self.subTest(entry=entry):
                tid, sid, received = self.live(name="r-" + entry[-4:])
                e = self.message((sid, tid), text="admitted before, " + entry)
                self.receipt(DESK, sid, e, tid, admitted=True)
                sminos.forget_caches()
                t = threads.get(tid)
                o = channels.owing(self.chan(DESK), t, channels.own_row(t))
                self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
                self.add(tid, sid, DESK)
                if entry == "deliver_next":
                    sminos.deliver_next(self.chan(DESK), o.member, owing=o)
                else:
                    self.assertIsNone(sminos.deliver_reach(self.chan(DESK), o.member, e, "deliver", owing=o))
                self.assertEqual(self.settled(tid, W1), 0, "nothing settled below the new boundary")


    def test_an_admitted_receipt_for_a_second_writer_settles_nothing_once_the_thread_ended_between_writers(self):
        tid, sid, received = self.live()
        first = self.message((sid, tid), text="first writer")
        second = self.message((sid, tid), writer=W2, text="second writer")
        self.receipt(DESK, sid, second, tid, admitted=True)
        real, ended = sminos.push_member, []

        def push_member(m, frame, *a, **k):
            out = real(m, frame, *a, **k)
            if "first writer" in frame and not ended:
                ended.append(True)   # the thread ends once the first writer's frame is handed over
                self.raw(tid, lambda r: r.update(ended={"at": sminos.now(), "reason": "retire"}))
                sminos.forget_caches()
            return out
        with mock.patch.object(sminos, "push_member", push_member):
            self.deliver()
        self.assertEqual(len(self.got(received, "first writer")), 1)
        self.assertEqual(self.settled(tid, W1), first["seq"], "its own hand-over settles, with no check between")
        self.assertEqual(self.settled(tid, W2), 0, "the earlier pass's receipt is no debt of an ended thread")
        self.assertGreater(second["seq"], 0)


# ------------------------------------------------------------ what this machine appended


class Appended(Channel):
    def test_a_message_under_this_machines_own_name_with_no_receipt_is_an_outside_event(self):
        tid, sid, received = self.live()
        own = "%s/%s" % (sminos.host_name(), str(uuidlib.uuid4()))
        e = self.message((sid, tid), writer=own, text="no receipt")
        path = sminos.receipt_path(self.chan(DESK), own)
        if os.path.exists(path):
            os.unlink(path)   # an import under this machine's name: nothing this machine appended
        self.assertFalse(channels.appended_here(self.chan(DESK), e))
        with mock.patch.object(sminos_policy, "read_only", return_value=True):
            self.deliver()
        self.assertEqual(self.got(received, "no receipt"), [])
        self.assertEqual(self.settled(tid, W1 if False else own), e["seq"], "refused-read-only")
        gate = sminos.ReachGate(self.chan(DESK))
        gate.capable = True
        with mock.patch.object(sminos, "same_owner_local", return_value=True):
            self.assertTrue(gate.needs(e, sid), "never the same-owner shortcut")

    def test_a_say_this_machine_appends_to_a_channel_has_its_receipt_and_the_shortcut_holds_for_it(self):
        tid, sid, received = self.live()
        own = "%s/%s" % (sminos.host_name(), str(uuidlib.uuid4()))
        e = sminos.log_append(self.chan(DESK), own, "say", **{"from": "me", "thread": str(uuidlib.uuid4()),
                                                              "to": [{"session": sid, "alias": "a", "thread": tid}],
                                                              "text": "appended here"})
        self.assertTrue(channels.appended_here(self.chan(DESK), e), "a `say` appended to a channel is receipted")
        gate = sminos.ReachGate(self.chan(DESK))
        gate.capable = True
        with mock.patch.object(sminos, "same_owner_local", return_value=True):
            self.assertFalse(gate.needs(e, sid))
        p_e = sminos.log_append(self.p, own, "say", **{"from": "me", "to": [{"session": sid, "alias": "a"}],
                                                       "text": "in a project"})
        self.assertIsNone(sminos.receipt_of(self.p, own, p_e["seq"]), "a project's say keeps none, as before")


    def receipts(self, log, own, lines, tail=""):
        path = sminos.receipt_path(log, own)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in lines) + tail)
        return path

    def parsed(self):
        """What a channel's receipt index parses, as the length of each text it is given."""
        real, seen = sminos._receipt_lines, []
        patcher = mock.patch.object(sminos, "_receipt_lines", lambda text: (seen.append(len(text)), real(text))[1])
        return patcher, seen

    def test_a_channels_receipt_file_is_parsed_once_extended_by_an_append_and_keeps_its_last_valid_line(self):
        own = "%s/%s" % (sminos.host_name(), str(uuidlib.uuid4()))
        chan = self.chan(DESK)
        lines = [{"seq": i, "hash": "h%d" % i} for i in range(1, 2001)]
        lines += [{"seq": 5, "hash": "again"}, {"seq": 6, "hash": 7}]
        path = self.receipts(chan, own, lines, "{torn\n")
        patcher, seen = self.parsed()
        with patcher:
            got = [sminos.receipt_of(chan, own, seq) for seq in range(1, 2001)]
        self.assertEqual(len([n for n in seen if n]), 1, "its lines parsed once while the file is unchanged")
        self.assertEqual(got[4], "again", "a seq written twice is its last line's")
        self.assertEqual(got[5], "h6", "a line with no hash names none")
        self.assertEqual(got[1999], "h2000")
        line = json.dumps({"seq": 2001, "hash": "late"}) + "\n"
        with open(path, "a") as f:
            f.write(line)
        patcher, seen = self.parsed()
        with patcher:
            self.assertEqual(sminos.receipt_of(chan, own, 2001), "late", "what the append added")
        self.assertLessEqual(sum(seen), len(line), "and only that, parsed")
        with open(path, "a") as f:
            f.write(json.dumps({"seq": 2002, "hash": "unended"}))
        self.assertEqual(sminos.receipt_of(chan, own, 2002), "unended", "a line its newline has not ended yet")
        self.assertIsNone(sminos.receipt_of(chan, own, 2003))

    def test_a_channels_receipt_file_rewritten_in_place_at_the_same_length_is_read_again(self):
        own = "%s/%s" % (sminos.host_name(), str(uuidlib.uuid4()))
        chan = self.chan(DESK)
        path = self.receipts(chan, own, [{"seq": 1, "hash": "aaaa"}])
        self.assertEqual(sminos.receipt_of(chan, own, 1), "aaaa")
        before = os.stat(path)
        with open(path, "r+") as f:   # the same inode and length, other contents
            f.write(json.dumps({"seq": 1, "hash": "bbbb"}) + "\n")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        self.assertEqual(os.stat(path).st_size, before.st_size)
        self.assertEqual(sminos.receipt_of(chan, own, 1), "bbbb", "as a cold read says")


    def test_a_receipt_that_cannot_be_read_now_names_nothing_in_a_project_and_in_a_channel(self):
        for log in (self.p, self.chan(DESK)):
            with self.subTest(log=log.name):
                own = "%s/%s" % (sminos.host_name(), str(uuidlib.uuid4()))
                path = self.receipts(log, own, [{"seq": 1, "hash": "h1"}])
                self.assertEqual(sminos.receipt_of(log, own, 1), "h1")
                os.chmod(path, 0)
                self.addCleanup(os.chmod, path, 0o600)
                self.assertIsNone(sminos.receipt_of(log, own, 1), "fail closed, as before")
                os.chmod(path, 0o600)
                self.assertEqual(sminos.receipt_of(log, own, 1), "h1")

    def test_a_projects_receipt_lookup_is_todays_and_keeps_no_index(self):
        own = "%s/%s" % (sminos.host_name(), str(uuidlib.uuid4()))
        path = self.receipts(self.p, own, [{"seq": i, "hash": "h%d" % i} for i in range(1, 50)])
        patcher, seen = self.parsed()
        with patcher:
            self.assertEqual(sminos.receipt_of(self.p, own, 49), "h49")
        self.assertEqual(seen, [], "no channel's index for a project")
        self.assertNotIn(path, sminos._RECEIPT_INDEX)


# ------------------------------------------------------------ the transitions, as pushes


class Seats(Channel):
    def test_d8_a_lane_a_refills_new_occupant_is_pushed_what_names_the_thread(self):
        old, seat_id = self.seated()
        self.add(seat_id, old, DESK)
        e = self.message((old, seat_id), text="for the seat")
        new, nproc, out = self.refill(seat_id)
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["current"], new, out)
        received = self.inbox(new, nproc, "n")
        self.deliver()
        self.assertEqual(len(self.got(received, "for the seat")), 1)
        self.assertEqual(self.settled(seat_id, W1), e["seq"])

    def test_d15_a_seat_made_again_over_a_purged_seats_session_is_pushed_what_lies_past_its_new_boundary(self):
        sid, proc = self.session()
        received = self.inbox(sid, proc)
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.add(sid, sid, DESK)
        code, out = self.cli("remove", "g/w")
        self.assertEqual(code, 0, out)
        before = self.message((sid, sid), text="before the seat was made again")
        code, out = self.cli("seat", "add", "g", "w", "--session", sid)
        self.assertEqual(code, 0, out)
        self.add(sid, sid, DESK)
        late = self.message((sid, sid), writer=W2, text="imported late", ts="2026-01-01T00:00:00.000Z")
        self.deliver()
        self.assertEqual(len(self.got(received, "imported late")), 1, "the same thread, past its new boundary")
        self.assertEqual(self.got(received, "before the seat was made again"), [])
        self.assertEqual(self.settled(sid, W2), late["seq"])
        self.assertEqual(self.settled(sid, W1), 0, before["seq"])



class Several(Channel):
    def test_five_messages_of_two_writers_to_a_stopped_thread_wake_it_once_and_arrive_once_in_order(self):
        tid, sid = self.stopped()
        sent = [self.message((sid, tid), writer=(W1, W2)[i % 2], text="number %d" % i) for i in range(5)]
        self.deliver()
        self.assertEqual(len(self.resumes(sid)), 1, "woken once")
        self.assertTrue(wait_for(lambda: all(self.woken_got(sid, "number %d" % i) for i in range(5))))
        frames = self.frames(sid)
        for i in range(5):
            self.assertEqual(sum(f.count("number %d" % i) for f in frames), 1)
        for w in (W1, W2):
            seen = [i for f in frames for i in range(5) if "number %d" % i in f and sent[i]["writer"] == w]
            self.assertEqual(seen, sorted(seen), "each writer's in its order")
            self.assertEqual(self.settled(tid, w), max(e["seq"] for e in sent if e["writer"] == w))

    def test_two_threads_of_one_message_each_get_it_once_one_live_and_one_woken(self):
        tid, sid, received = self.live()
        stid, ssid = self.stopped()
        e = self.message((sid, tid), (ssid, stid), text="to the two")
        total, reached = self.deliver()
        self.assertEqual(total, 2)
        self.assertEqual(len(self.got(received, "to the two")), 1)
        self.assertEqual(len(self.woken_got(ssid, "to the two")), 1)
        self.assertEqual((self.settled(tid, W1), self.settled(stid, W1)), (e["seq"], e["seq"]))


    def test_a_channel_no_thread_here_holds_forgets_its_remembered_passes_without_reading_its_log(self):
        daemon = sminos.daemon_module()
        chan = self.chan(DESK)
        for key in ((DESK, "t"), ("other", "t")):
            daemon._HELD_PASSES[key] = ("kept",)
            self.addCleanup(daemon._HELD_PASSES.pop, key, None)
        sminos.forget_caches()
        with mock.patch.object(sminos, "_store_whole", side_effect=AssertionError("the log read")):
            self.assertEqual(channels.deliver(chan), (0, []))
        self.assertNotIn((DESK, "t"), daemon._HELD_PASSES, "the channel's memories forgotten")
        self.assertIn(("other", "t"), daemon._HELD_PASSES, "another log's kept")


# ------------------------------------------------------------ the operation's entry points and the endpoint's word


class Words(Channel):
    """On a machine cut over to its endpoint (cut_over and reach_capable answered, in this process: a real cut-over
    would make a directory no `.smns` claims the machine's own project, and move the sessions there)."""

    def cut_over(self, reach=False):
        for target, name, value in ((sminos.sibling_module("sminos_rl10"), "cut_over", True),
                                    (sminos.audience_module(), "reach_capable", reach)):
            patcher = mock.patch.object(target, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        sminos.forget_caches()

    def owing_of(self, tid):
        sminos.forget_caches()
        t = threads.get(tid)
        return channels.owing(self.chan(DESK), t, channels.own_row(t))

    def test_a_channels_log_given_without_its_owing_is_refused(self):
        tid, sid, received = self.live()
        member = channels.own_row(threads.get(tid))[1]
        for push in (lambda: sminos.deliver_next(self.chan(DESK), member),
                     lambda: sminos.deliver_verdict(self.chan(DESK), member, {"writer": W1, "seq": 1}, "peer"),
                     lambda: sminos.deliver_reach(self.chan(DESK), member, {"writer": W1, "seq": 1}, "deliver")):
            with self.assertRaises(AssertionError):
                push()

    def test_a_persons_words_are_left_owed_and_listed_gated_and_words_due_chooses_by_the_thread(self):
        tid, sid, received = self.live()
        other = str(uuidlib.uuid4())
        e = self.message((other, tid), writer="%s/human" % FAR, kind="human", text="a person's words")
        o = self.owing_of(tid)
        self.cut_over()
        got = sminos.deliver_next(self.chan(DESK), o.member, owing=o)
        self.assertEqual([(x["writer"], x["seq"]) for x in got["gated"]], [(e["writer"], e["seq"])])
        self.assertEqual(self.got(received, "a person's words"), [], "the endpoint decides it: left owed")
        self.assertEqual(self.owed_to(tid), [(e["writer"], e["seq"])])
        due = sminos.words_due(self.chan(DESK), [], owing={sid: o})
        self.assertEqual([(x["writer"], x["seq"]) for x in due[sid]], [(e["writer"], e["seq"])],
                         "chosen by the thread, whatever session its entry names")
        self.assertEqual(sminos.deliver_verdict(self.chan(DESK), o.member, e, "peer", owing=o), "sent")
        self.assertEqual(len(self.got(received, "a person's words")), 1)
        self.assertEqual(self.settled(tid, e["writer"]), e["seq"])
        self.assertEqual(sminos.words_due(self.chan(DESK), [], owing={sid: o}), {})

    def test_reach_due_chooses_by_the_thread_and_a_refusal_settles_here_with_no_push(self):
        tid, sid, received = self.live()
        a = self.message((sid, tid), text="refused")
        b = self.message((sid, tid), writer=W2, text="admitted")
        o = self.owing_of(tid)
        self.cut_over(reach=True)
        got = sminos.deliver_next(self.chan(DESK), o.member, owing=o)
        self.assertEqual(len(got["gated"]), 2)
        self.assertEqual(self.received(received), [], "a peer's push waits for the endpoint's word")
        due = sminos.reach_due(self.chan(DESK), [], owing={sid: o})
        self.assertEqual(sorted((x["writer"], x["seq"]) for x in due[sid]),
                         sorted([(W1, a["seq"]), (W2, b["seq"])]))
        self.assertEqual(sminos.deliver_reach(self.chan(DESK), o.member, a, "refuse", "not in the org", owing=o),
                         "refused-reach")
        self.assertEqual(sminos.deliver_reach(self.chan(DESK), o.member, b, "deliver", owing=o), "sent")
        self.assertEqual(self.got(received, "refused"), [])
        self.assertEqual(len(self.got(received, "admitted")), 1)
        self.assertEqual((self.settled(tid, W1), self.settled(tid, W2)), (a["seq"], b["seq"]))
        outbox = os.path.join(self.chan(DESK).home, sminos.sibling_module("sminos_outcomes").OUTBOX)
        self.assertFalse(os.path.exists(outbox), "no outcome kept for the uplink under a channel's id")

    def test_a_word_on_an_event_no_longer_its_writers_first_owed_does_nothing(self):
        tid, sid, received = self.live()
        a = self.message((sid, tid), text="first")
        b = self.message((sid, tid), text="second")
        o = self.owing_of(tid)
        self.cut_over(reach=True)
        self.assertIsNone(sminos.deliver_reach(self.chan(DESK), o.member, b, "deliver", owing=o))
        self.assertEqual(self.received(received), [])
        self.assertEqual(sminos.deliver_reach(self.chan(DESK), o.member, a, "deliver", owing=o), "sent")
        self.assertEqual(self.settled(tid, W1), a["seq"])


    def test_a_refusal_on_an_owing_that_predates_a_removal_and_an_add_settles_nothing(self):
        tid, sid, received = self.live()
        a = self.message((sid, tid), text="refused late")
        o = self.owing_of(tid)
        self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
        self.add(tid, sid, DESK)
        self.cut_over(reach=True)
        self.assertIsNone(sminos.deliver_reach(self.chan(DESK), o.member, a, "refuse", "late", owing=o))
        self.assertEqual(self.settled(tid, W1), 0, "the refusal decided nothing on an event the thread is not owed")

    def test_a_persons_words_reach_the_bridge_scoped_by_the_thread_they_are_owed_to(self):
        tid, sid, received = self.live()
        e = self.message((sid, tid), writer="%s/human" % FAR, kind="human", text="words for the thread")
        o = self.owing_of(tid)
        self.cut_over()
        control = sminos.control_module()
        keys = []

        def post_command(path, body, *a):
            keys.append(body["key"])
            return 200, {"ok": True, "result": {"submitted": True}}
        with mock.patch.object(control, "post_command", post_command):
            self.assertEqual(sminos.deliver_verdict(self.chan(DESK), o.member, e, "words", owing=o), "sent")
            control.deliver(sid, "p", {"writer": "m/human", "seq": 3}, "text")
        self.assertEqual(keys, [{"project": "%s#%s" % (DESK, tid), "writer": e["writer"], "seq": e["seq"]},
                                {"project": "p", "writer": "m/human", "seq": 3}],
                         "the thread in the scope a bridge keys on; a project's key as it was")
        # Every bridge a session has loaded keys its mark on `project` (sminos_bridge._mark is the mod's rule).
        bridge = sminos.sibling_module("sminos_bridge")
        marks = {bridge._mark(k) for k in (keys[0], dict(keys[0], project="%s#%s" % (DESK, SENDER_THREAD)),
                                           dict(keys[0], project=DESK))}
        self.assertEqual(len(marks), 3, "one thread's mark is neither another's nor the channel's")


# ------------------------------------------------------------ a return that writes the boundary anew


class Returned(Life, T1_ended.Ending):
    message = Channel.message
    deliver = Channel.deliver
    record_of = Channel.record_of
    settled = Channel.settled

    def test_an_attempt_a_return_put_below_the_boundary_is_cleared_and_the_writers_next_message_goes(self):
        sid, proc = self.opened(inbox=True)
        tid = threads.stamp(sid)
        self.add(tid, sid, DESK)
        first = self.message((sid, tid), text="first")
        with failing("first"):
            self.deliver()
        self.assertEqual(self.record_of(tid)[W1]["pending"], first["seq"])
        self.end(proc)
        self.reconcile()
        self.stopped_since(sid, 2 * T1_ended.PERIOD)
        self.sweep()
        self.assertTrue(threads.record_ended(threads.get(tid)))
        self.message((sid, tid), text="while ended")
        kept = self.record_of(tid)
        self.deliver()
        self.assertEqual(self.record_of(tid), kept, "D9: nothing delivered, nothing settled while it is ended")
        self.live(sid=sid, name="alpha", inbox=True)
        self.reconcile()
        self.assertIsNone(threads.get(tid).get("ended"), "returned")
        second = self.message((sid, tid), text="second")
        self.deliver()
        self.deliver()
        frames = self.inbox(sid)
        self.assertEqual(sum("second" in f for f in frames), 1, "pushed once")
        self.assertEqual(sum("first" in f for f in frames), 0, "and the first never")
        self.assertEqual(sum("while ended" in f for f in frames), 0, "nor what came while ended (this code's return)")
        w = self.record_of(tid)[W1]
        self.assertEqual((w["settled"], w["pending"], w["attempts"]), (second["seq"], None, 0))


if __name__ == "__main__":
    unittest.main()
