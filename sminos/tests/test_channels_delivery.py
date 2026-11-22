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
from test_channels_life import DESK, LOBBY, Life  # noqa: E402
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
        sminos.deliver_next(self.chan(DESK), row, owing=o)
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

        def read_only():
            path = sminos_policy.policy_path()
            with open(path) as f:
                pol = json.load(f)
            pol["read_only"] = True
            with open(path, "w") as f:
                json.dump(pol, f)
        self.stalled(tid, sid, read_only)
        self.assertEqual(self.woken_got(sid, "read-only meanwhile"), [], "no text")
        self.assertEqual(self.settled(tid, W1), e["seq"], "refused as the check before a push refuses it")
        self.assertEqual(self.owed_to(tid), [])

    def test_a_signer_revoked_across_the_launch_hands_nothing_over_and_its_event_is_marked(self):
        tid, sid = self.stopped()
        sminos.write_json(sminos.sibling_module("sminos_rl10").identity_path(), {
            "org": "org-1", "hub": "http://127.0.0.1:9", "name": sminos.host_name(), "former": {},
            "ref": "machine-ref-1", "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z",
            "build": "b"}, mode=0o600)
        sminos.audience_module().keep_capabilities([])
        sminos.forget_caches()
        e = self.message((sid, tid), text="revoked meanwhile")
        rl10 = sminos.sibling_module("sminos_rl10")
        self.stalled(tid, sid, lambda: rl10.keep_revoked({"version": 2, "devices": [], "members": [],
                                                          "keys": [SIGNER["keyId"]]}, True))
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
