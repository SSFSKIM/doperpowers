#!/usr/bin/env python3
"""A closed session stays: stopped, held, and its sender told (T1's M3:
docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md, the milestone's
"What it proves"; Interfaces §5, §6 rows 7, 8 and 16, §8).

- Its process gone, a thread its human opened stays a member, `stopped`,
  under its alias and in-charge line, and comes back as itself; a lane B
  session still leaves with its process; an older copy's `ended` for a
  stopped thread changes nothing, and older and newer ticks in turn settle.
- The hold: an addressed message is recorded, stays owed with no attempt
  counted, and its sender is told why; what settles without a push still
  settles; a tick passes a held backlog by on the memory of a full pass;
  `daemon owed` counts it as waiting for a closed session.
- X3's first value on a stopped thread's `state`, and what a sender on
  another machine is told from it.
- The thread sweep's stop mark.
- A `/clear`: the note of the engine's `SessionEnd`, the witness, and the
  alias moving to the new session.

The cut-over machine's half of the hold (the words and reach gates) is in
test_words.py. Hermetic: HOME and SMINOS_HOME are temporary, fresh for each
test (test_threads.Machine); sessions are `sleep` processes with engine
records the test writes.
Run: python3 -B sminos/tests/test_threads_stopped.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
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

from test_threads import BASE, SCRIPTS, Killed, Machine, records, sminos, threads  # noqa: E402

HOOK = os.path.join(os.path.dirname(HERE), "hooks", "smns-cleared.sh")
INBOX = os.path.join(HERE, "inbox_standin.py")


def wait_for(pred, timeout=10, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


class Rig(Machine):
    """test_threads.Machine, with a transcript for each session (a session
    with none reads `gone`, not `stopped`), inboxes, and the daemon."""

    def setUp(self):
        super().setUp()
        self.daemon = sminos.daemon_module()
        self.inboxes = {}
        self.daemon._HELD_PASSES.clear()

    def fresh(self):
        """setUp again inside one test (a subtest's own machine), its processes stopped first."""
        self.stop_all()
        self.setUp()

    def transcript(self, sid, mode="plan"):
        """Its last turn in `plan` mode by default (T2's M3): a stopped thread here is held for `mode`, never
        woken, so these suites, which have no engine, pin the hold as T1 built it; the wake is
        test_wake_delivery.py's. A seat's resume, where a test patches the launch, runs in `auto`, under a
        machine ceiling that lets a first wake keep it (a first wake's capped mode decides `mode`)."""
        if mode != "plan":
            path = sminos.sibling_module("sminos_policy").policy_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump({"ceiling": "bypassPermissions"}, f)
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-work")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "a") as f:
            f.write(json.dumps({"type": "user", "sessionId": sid, "cwd": self.root, "permissionMode": mode,
                                "message": {"role": "user", "content": "work"}}) + "\n")
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()

    def opened(self, name="alpha", charge="owns alpha", sid=None, inbox=False, **more):
        """A session its human opened, joined, with a transcript, a user-given name and an in-charge line."""
        sid, proc = self.live(sid=sid, name=name, inbox=inbox, **more)
        self.transcript(sid)
        self.reconcile()
        if charge:
            sminos.lifecycle(self.p, sid, "in-charge", text=charge, source="set")
        sminos.forget_caches()
        return sid, proc

    def live(self, sid=None, name="alpha", inbox=False, kind="interactive", started=None):
        sid, proc = self.session(sid=sid, name=name, kind=kind, started=started)
        fields = {"nameSource": "user"}
        if inbox:
            sock = os.path.join(self.home, "in-%s.sock" % sid[:8])
            self.inboxes[sid] = sock + ".received"
            open(self.inboxes[sid], "a").close()
            server = subprocess.Popen([sys.executable, "-B", INBOX, sock, self.inboxes[sid]])
            self.addCleanup(lambda: (server.kill(), server.wait()))
            wait_for(lambda: sminos.socket_ok(sock))   # listening, not just bound: a connect is answered
            fields["messagingSocketPath"] = sock
        self.peer_set(proc, **fields)
        return sid, proc

    def inbox(self, sid):
        try:
            with open(self.inboxes[sid]) as f:
                return [json.loads(line)["message"]["content"] for line in f if line.strip()]
        except (KeyError, OSError):
            return []

    def member(self, sid, p=None):
        sminos.forget_caches()
        return next((m for m in sminos.view_of(p or self.p).members if m.session == sid), None)

    def say(self, text, sender=None):
        env = {"CLAUDE_CODE_SESSION_ID": sender} if sender else {}
        with mock.patch.dict(os.environ, env):
            if not sender:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            return self.cli("say", text)

    def tick(self):
        sminos.forget_caches()
        return self.daemon.tick(self.p)

    def owed_to(self, sid):
        m = self.member(sid)
        return [(e["writer"], e["seq"]) for e in sminos.owed(self.p, m)] if m else []

    def attempts(self, sid):
        return {w: d.get("attempts", 0) for w, d in sminos.delivered_load(self.p, sid).items()}


# ------------------------------------------------------------ stopped, not ended


class Stopped(Rig):
    def test_closed_it_is_listed_stopped_folded_in_list_and_nothing_retires_it(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        self.tick()
        self.assertEqual([e for e in self.own(sid) if e["kind"] == "retired"], [])
        code, out = self.cli("list", "--stopped")
        self.assertEqual(code, 0, out)
        self.assertIn("alpha [%s]" % sid[:8], out)
        self.assertIn("stopped", out)
        self.assertIn("in charge: owns alpha", out)
        code, out = self.cli("list")
        self.assertNotIn("alpha [", out, "folded")
        self.assertIn("+1 hidden (stopped", out)

    def test_reopened_it_is_live_under_its_alias_and_line_and_what_was_held_is_pushed_in_order(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        for n in (1, 2):
            code, out = self.say("@alpha number %d" % n)
            self.assertEqual(code, 0, out)
        self.tick()
        self.assertEqual(len(self.owed_to(sid)), 2, "held")
        self.live(sid=sid, name="alpha", inbox=True)
        self.tick()
        m = self.member(sid)
        self.assertEqual((m.alias, m.charge, m.thread), ("alpha", "owns alpha", tid))
        self.assertEqual(m.state, "idle")
        got = self.inbox(sid)
        self.assertEqual(len(got), 2)
        self.assertIn("number 1", got[0])
        self.assertIn("number 2", got[1])
        self.assertEqual(self.owed_to(sid), [])
        self.assertEqual([e["kind"] for e in self.own(sid) if e["kind"] in ("joined", "retired")], ["joined"])

    def test_a_new_session_with_its_name_is_told_apart_from_it(self):
        old, proc = self.opened()
        self.end(proc)
        self.reconcile()
        new, _ = self.opened(charge="")
        m = self.member(new)
        self.assertEqual(m.alias, new[:8], "the name is the stopped session's: the new one goes by its short id")
        code, out = self.say("@alpha hi")
        self.assertIn("alpha: recorded and held", out, "a bare @alpha still names the stopped one")

    def test_a_lane_b_session_that_never_was_a_thread_leaves_unstamped(self):
        sid, proc = self.session()
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        self.reconcile()
        self.end(proc)
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e["reason"]), ("retired", "ended"))
        self.assertNotIn("thread", e)

    def test_an_older_copys_ended_for_a_stopped_thread_changes_nothing(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        self.write_own(sid, [{"kind": "retired", "by": "", "reason": "ended"}])
        before = len(self.own(sid))
        self.reconcile()
        self.tick()
        self.assertEqual(len([e for e in self.own(sid) if e["kind"] in ("joined", "retired")]), 2)
        self.assertTrue(self.is_member(sid))
        code, out = self.cli("list", "--stopped")
        self.assertIn("alpha [%s]" % sid[:8], out)
        self.assertEqual(len(self.own(sid)), before, "nothing written")

    def test_an_older_copys_joined_then_ended_is_joined_again_stamped_once(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        self.end(proc)
        self.reconcile()
        self.write_own(sid, [self.old_joined(sid, alias="alpha"), {"kind": "retired", "by": "", "reason": "ended"}])
        self.reconcile()
        self.reconcile()
        e = threads.in_effect(self.own(sid))
        self.assertEqual((e["kind"], e["thread"]), ("joined", tid))
        self.assertEqual(len(self.joins(sid)), 3, "the first, the older copy's, and one stamped again")
        self.assertFalse(threads.record_ended(threads.get(tid)))

    def older_tick(self, sid, running):
        """What sminos 1.27.10's reconciliation writes for a seat-less
        session of this machine: from the raw last membership event alone,
        an `ended` when no process runs it, a `joined` when one does."""
        own = [e for e in self.own(sid) if e["kind"] in ("joined", "retired")]
        last = own[-1]["kind"] if own else None
        if running and last != "joined":
            self.write_own(sid, [self.old_joined(sid, alias="alpha")])
        elif not running and last == "joined":
            self.write_own(sid, [{"kind": "retired", "by": "", "reason": "ended"}])

    def test_older_and_newer_ticks_in_turn_stop_growing_after_one_round(self):
        for reopened in (False, True):
            with self.subTest(reopened=reopened):
                sid, proc = self.opened(name="alpha%d" % reopened)
                self.end(proc)
                self.reconcile()
                if reopened:
                    self.live(sid=sid, name="alpha%d" % reopened)
                counts = []
                for _ in range(3):
                    self.older_tick(sid, reopened)
                    self.reconcile()
                    self.older_tick(sid, reopened)
                    self.reconcile()
                    counts.append(len(self.own(sid)))
                self.assertEqual(counts[1], counts[2], counts)
                self.assertEqual(counts[0], counts[1], counts)
                self.assertTrue(self.is_member(sid))
                self.assertTrue(threads.stamped(threads.in_effect(self.own(sid))))

    def test_without_a_transcript_it_is_stopped_by_its_record(self):
        sid, proc = self.live()   # no transcript on this machine
        self.reconcile()
        self.end(proc)
        self.reconcile()
        self.assertEqual(self.member(sid).state, "stopped", "the thread and its process say so, not a transcript")

    def test_a_spawned_thread_turned_lane_b_ends_with_its_process_and_its_seat_reads_retired(self):
        sid, proc = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.assertIn("opened", sminos.load_seat(sminos.meta_path(seat_id)), "a spawned thread's record")
        records.set_controller(sid, "B")
        self.end(proc)
        self.reconcile()
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual((seat["status"], seat["ended"]["reason"], seat.get("pending")), ("retired", "ended", None))
        last = threads.in_effect(self.own(sid))
        self.assertEqual((last["kind"], last["reason"], last["thread"]), ("retired", "ended", seat_id), "stamped")
        self.assertEqual(self.member(sid), None)
        self.reconcile()
        self.assertEqual(len([e for e in self.own(sid) if e["kind"] == "retired"]), 1, "once")

    def test_a_human_opened_session_an_older_cli_seated_ends_by_its_own_record(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})   # the older CLI's seat, no thread keys
        self.reconcile()
        records.set_controller(sid, "B")
        self.end(proc)
        self.reconcile()
        self.assertTrue(threads.record_ended(threads.get(tid)), "its record, in the thread store, ended")
        self.assertEqual(threads.get(tid)["ended"]["reason"], "ended")
        last = threads.in_effect(self.own(sid))
        self.assertEqual((last["kind"], last["reason"], last["thread"]), ("retired", "ended", tid))
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertEqual(seat["status"], "retired", "the seat row is not its record: it follows the record's end")
        self.reconcile()
        self.assertEqual(len([e for e in self.own(sid) if e["kind"] == "retired"]), 1, "once")

    def test_an_ordinary_lane_a_seat_whose_process_ended_is_left_as_it_is(self):
        sid, proc = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.end(proc)
        self.reconcile()
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        self.assertNotEqual(seat["status"], "retired")
        self.assertNotIn("ended", seat)
        self.assertEqual(threads.in_effect(self.own(sid))["kind"], "joined")


# ------------------------------------------------------------ the hold


class Hold(Rig):
    def stopped(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        return sid

    def test_an_addressed_say_is_recorded_held_owed_and_counts_no_attempt(self):
        sid = self.stopped()
        other, _ = self.opened(name="beta", charge="")
        for sender in (other, None):
            code, out = self.say("@alpha are you there", sender=sender)
            self.assertEqual(code, 0, out)
            self.assertIn("alpha: recorded and held: the session is stopped and is not woken: a wake would run it in a "
                          "mode that asks for approval; it is pushed when a process of it runs again before it ends", out)
        for _ in range(sminos.DELIVERY_ATTEMPTS + 2):
            self.tick()
        self.assertEqual(len(self.owed_to(sid)), 2)
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
        self.assertEqual(threads.hold_of(sid), "mode")
        self.assertEqual(self.member(sid).state, "stopped")

    def test_push_member_holds_an_addressed_frame_and_records_one_for_the_live_alone(self):
        sid = self.stopped()
        m = self.member(sid)
        self.assertEqual(sminos.push_member(m, "x", True), "held:mode")
        self.assertEqual(sminos.push_member(m, "x", False), "recorded")

    def test_what_settles_without_a_push_still_settles(self):
        sid = self.stopped()
        w = "testhost/human"
        bcast = sminos.log_append(self.p, w, "say", **{"from": "human", "to": [{"session": sid, "alias": "alpha"}],
                                                       "text": "@all hi", "wake": True})
        admitted = sminos.log_append(self.p, "testhost/other", "say", **{
            "from": "x", "to": [{"session": sid, "alias": "alpha"}], "text": "taken before it exited"})
        real = sminos.holder_owed

        def owed(project, member, session, e, events, cursor):
            return "sent" if e["seq"] == admitted["seq"] and e["writer"] == admitted["writer"] else \
                real(project, member, session, e, events, cursor)
        with mock.patch.object(sminos, "holder_owed", side_effect=owed):
            got = sminos.deliver_next(self.p, self.member(sid))
        outcomes = {(e["writer"], e["seq"]): o for e, o in got["outcomes"]}
        self.assertEqual(outcomes[(w, bcast["seq"])], "recorded", "a broadcast reaches the live alone")
        self.assertEqual(outcomes[(admitted["writer"], admitted["seq"])], "sent", "an admitted receipt settles")
        self.assertEqual(self.owed_to(sid), [])

    def test_on_a_read_only_machine_an_outside_event_settles_as_today(self):
        sid = self.stopped()
        e = sminos.log_append(self.p, "othermachine/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "from elsewhere"})
        policy = sminos.sibling_module("sminos_policy")
        with mock.patch.object(policy, "read_only", return_value=True):
            got = sminos.deliver_next(self.p, self.member(sid))
        self.assertEqual([o for x, o in got["outcomes"] if x["seq"] == e["seq"]], ["refused-read-only"])
        self.assertEqual(self.owed_to(sid), [])

    def test_a_seated_send_after_a_clear_pushes_nothing_through_the_socket_the_pid_kept(self):
        """An older copy's seat holding a session its human opened, live; a
        `/clear` moves its process to another id, its socket kept, while
        this process's copy of the engine's records still names it."""
        sid, proc = self.opened(inbox=True)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        sminos.forget_caches()
        sminos.peer_records()
        path = self.peer_path(proc.pid)
        with open(path) as f:
            rec = json.load(f)
        with open(path, "w") as f:
            json.dump(dict(rec, sessionId=str(uuidlib.uuid4())), f)   # the /clear, this process not told
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sminos.send_to_seat(seat, "to the old session", "m1", False,
                                record=lambda s: sminos.record_send(s, "human", "human", "to the old session", "m1"))
        self.assertIn("recorded and held", out.getvalue())
        self.assertEqual(self.inbox(sid), [], "nothing through the socket the pid kept")
        self.assertEqual([e["text"] for e in sminos.owed(self.p, self.member(sid))], ["to the old session"])

    def successor_during_the_append(self, sid, proc):
        """The reviewer's interleaving, run while the send's append is
        written: the process looked at moves to a successor session (a
        `/clear`, its socket kept) and the old id reopens in another process
        with its own inbox. Returns the inbox file of the process looked at."""
        looked_at = self.inboxes[sid]

        def swap():
            self.peer_set(proc, sessionId=str(uuidlib.uuid4()))
            self.live(sid=sid, inbox=True)
        return looked_at, swap

    def test_a_seated_send_pushes_nothing_when_its_session_moved_process_during_the_append(self):
        sid, proc = self.opened(inbox=True)
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        seat = sminos.load_seat(sminos.meta_path(seat_id))
        looked_at, swap = self.successor_during_the_append(sid, proc)

        def record(s):
            d = sminos.record_send(s, "human", "human", "to the old session", "m1")
            swap()
            return d
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sminos.send_to_seat(seat, "to the old session", "m1", False, record=record)
        with open(looked_at) as f:
            self.assertEqual(f.read(), "", "nothing through the socket the successor holds")
        self.assertEqual(self.inbox(sid), [], "nor to a process the sender never looked at")
        self.assertIn("not pushed now", out.getvalue())
        self.assertEqual([e["text"] for e in sminos.owed(self.p, self.member(sid))], ["to the old session"])

    def test_a_seatless_send_pushes_nothing_when_its_session_moved_process_during_the_append(self):
        sid, proc = self.opened(inbox=True)
        looked_at, swap = self.successor_during_the_append(sid, proc)
        real = sminos.record_message

        def record_message(*a, **k):
            d = real(*a, **k)
            swap()
            return d
        with mock.patch.object(sminos, "record_message", side_effect=record_message):
            code, out = self.cli("send", "alpha", "to the old session")
        self.assertEqual(code, 0, out)
        with open(looked_at) as f:
            self.assertEqual(f.read(), "", "nothing through the socket the successor holds")
        self.assertEqual(self.inbox(sid), [], "nor to a process the sender never looked at")
        self.assertIn("not pushed now", out)
        self.assertEqual([e["text"] for e in sminos.owed(self.p, self.member(sid))], ["to the old session"])

    def test_the_fresh_hold_after_an_archive_change_in_a_fresh_process_reads_no_record_set_aside(self):
        """What every push and ask asks last (hold_now) reads the live stores
        alone: in a fresh process, just after the archive changed, neither an
        ordinary seat's session, a live session its human opened nor a
        stopped one opens an ended record."""
        for _ in range(5):   # an archive of unrelated ended threads
            s, proc = self.session()
            self.reconcile()
            self.ended_by_its_process(s, proc)
        seated, _ = self.session(name="seated")
        self.transcript(seated)
        code, out = self.cli("seat", "add", "g", "w", "--session", seated)
        self.assertEqual(code, 0, out)
        live, _ = self.opened(inbox=True)
        stopped = self.stopped()
        s, proc = self.session()
        self.reconcile()
        self.ended_by_its_process(s, proc)   # the archive changed just now
        self.assertEqual(len(self.human_files(aside=True)), 6)
        probe = (
            "import json, os, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import sminos, sminos_threads as threads\n"
            "read = []\n"
            "real_at, real_list = threads._human_at, os.listdir\n"
            "aside = os.path.realpath(threads.aside_dir())\n"
            "def at(path):\n"
            "    if os.path.realpath(os.path.dirname(path)) == aside: read.append(path)\n"
            "    return real_at(path)\n"
            "def listdir(path='.'):\n"
            "    if os.path.realpath(str(path)) == aside: read.append(str(path))\n"
            "    return real_list(path)\n"
            "threads._human_at, os.listdir = at, listdir\n"
            "holds = [sminos.hold_now(sid) for sid in sys.argv[2:]]\n"
            "print(json.dumps({'holds': holds, 'read': read}))\n")
        r = subprocess.run([sys.executable, "-B", "-c", probe, SCRIPTS, seated, live, stopped], capture_output=True,
                           text=True, cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(got["holds"], ["", "", "mode"])
        self.assertEqual(got["read"], [], "the hold reads only the live stores")

    def test_the_hold_reads_the_record_thread_of_reads(self):
        """hold_of's index answers what thread_of does from the live stores,
        for every session a live record names current: a seat whose open
        entry makes the session current outranks its human's record; a
        human record under a reservation is the session's, and holds
        nothing; a record set aside holds nothing."""
        sid = self.stopped()
        tid = threads.stamp(sid)

        def agree(why, hold):
            sminos.forget_caches()
            threads._forget_live()
            want = threads.thread_of(sid, ended=False)
            got = threads._live_index().get(sid)
            self.assertEqual((got or {}).get("thread"), (want or {}).get("thread") if want and
                             want["current"] == sid else None, why)
            self.assertEqual(threads.hold_of(sid), hold, why)
        agree("its human's record", "mode")
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle", "opened": "spawned", "sessions": [sid],
                                  "pending": {"op": "advance", "events": []}})
        agree("a seat's open entry making it current", "mode")   # T2: the hold is any thread's, its reason a fact
        os.unlink(sminos.meta_path(seat_id))
        path = threads._human_path(tid)
        with open(path) as f:
            rec = json.load(f)
        sminos.write_json(path, dict(rec, pending={"op": threads.RESERVED}))
        agree("a reservation", "")
        sminos.write_json(path, rec)
        agree("its record again", "mode")

    def hub_stopped(self):
        """A hub project with a stopped thread its human opened, a member there."""
        hub = sminos.make_project(str(uuidlib.uuid4()), "hubbed", "", "", {"url": "http://127.0.0.1:9",
                                                                           "org": "org-1"})
        sminos.project_path(hub, "log")
        sid = str(uuidlib.uuid4())
        threads.ensure(sid)
        sminos.lifecycle(hub, sid, "joined", alias="alpha", name_source="user", machine=sminos.host_name(),
                         cwd=self.root, worktree="", role="", seat="", by="", session_kind="interactive")
        sminos.forget_caches()
        return hub, sid

    def outbox(self, project):
        path = os.path.join(project.home, sminos.sibling_module("sminos_outcomes").OUTBOX)
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_a_read_only_machine_settles_what_settles_without_a_push_before_any_refusal(self):
        hub, sid = self.hub_stopped()
        admitted = sminos.log_append(hub, "othermachine/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "taken before it exited"})
        refused = sminos.log_append(hub, "othermachine/other", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "after"})
        real = sminos.holder_owed

        def owed(project, member, session, e, events, cursor):
            return "sent" if (e["writer"], e["seq"]) == (admitted["writer"], admitted["seq"]) else \
                real(project, member, session, e, events, cursor)
        policy = sminos.sibling_module("sminos_policy")
        with mock.patch.object(policy, "read_only", return_value=True), \
                mock.patch.object(sminos, "holder_owed", side_effect=owed):
            sminos.forget_caches()
            self.daemon.deliver_owed(hub, sminos.view_of(hub, titles=False))
        rows = {(r["event"]["writer"], r["event"]["seq"]): r["outcome"] for r in self.outbox(hub)}
        self.assertEqual(rows[(admitted["writer"], admitted["seq"])], "delivered", "the admitted receipt, not a refusal")
        self.assertEqual(rows[(refused["writer"], refused["seq"])], "refused-read-only")

    def test_an_outside_broadcast_to_it_is_recorded_once(self):
        hub, sid = self.hub_stopped()
        bcast = sminos.log_append(hub, "othermachine/human", "say", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "@all hi", "wake": True})
        for _ in range(3):
            sminos.forget_caches()
            self.daemon.deliver_owed(hub, sminos.view_of(hub, titles=False))
        mine = [r["outcome"] for r in self.outbox(hub) if r["event"] == {"writer": bcast["writer"],
                                                                        "seq": bcast["seq"]}]
        self.assertEqual(mine, ["recorded"])

    def test_a_tick_passes_a_held_backlog_by_on_the_memory_of_a_full_pass(self):
        sid = self.stopped()
        for n in range(20):
            sminos.log_append(self.p, "testhost/human", "human", **{
                "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "held %d" % n})
        self.tick()   # the full pass that leaves the memory
        with mock.patch.object(sminos, "deliver_next", wraps=sminos.deliver_next) as passes, \
                mock.patch.object(sminos, "flocked", wraps=sminos.flocked) as locks, \
                mock.patch.object(sminos, "_owed", wraps=sminos._owed) as enumerated, \
                mock.patch.object(sminos, "delivered_load", wraps=sminos.delivered_load) as loads:
            self.tick()
            self.tick()
            self.assertEqual(passes.call_count, 0, "no delivery pass")
            self.assertFalse([c for c in locks.call_args_list if "delivered" in str(c)], "no delivery lock")
            self.assertFalse([c for c in enumerated.call_args_list if c.args[1] == sid], "its backlog not enumerated")
            self.assertFalse([c for c in loads.call_args_list if c.args[1] == sid], "nor its delivery record read")
            sminos.log_append(self.p, "testhost/human", "human", **{
                "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "one more"})
            self.tick()
            self.assertEqual(passes.call_count, 1, "a new event for it ends the skip for one pass")
            self.tick()
            self.assertEqual(passes.call_count, 1)
            os.makedirs(sminos.holder_module().home(), exist_ok=True)
            with open(os.path.join(sminos.holder_module().home(), "x.json"), "w") as f:
                f.write("{}")   # a receipt written, or admitted
            self.tick()
            self.assertEqual(passes.call_count, 2, "a receipt's change ends it too")
        self.assertEqual(len(self.owed_to(sid)), 21)

    def test_a_held_backlog_reads_the_log_no_more_than_a_tick_over_none(self):
        sid = self.stopped()
        sminos.log_append(self.p, "testhost/human", "human", **{"from": "human", "text": "to no one"})
        self.tick()

        def reads():
            sminos.forget_caches()
            with mock.patch.object(sminos, "_log_file_held", wraps=sminos._log_file_held) as held, \
                    mock.patch.object(sminos, "log_read", wraps=sminos.log_read) as logged:
                self.tick()
            return held.call_count + logged.call_count
        none = reads()
        for n in range(30):
            sminos.log_append(self.p, "testhost/human", "human", **{
                "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "held %d" % n})
        self.tick()   # the full pass
        self.assertLessEqual(reads(), none)

    def test_the_memory_of_a_session_that_left_the_view_goes(self):
        sid = self.stopped()
        self.say("@alpha later")
        self.tick()
        self.assertIn((self.p.id, sid), self.daemon._HELD_PASSES)
        view = sminos.view_of(self.p, titles=False)
        self.daemon.deliver_owed(self.p, view._replace(members=[m for m in view.members if m.session != sid]))
        self.assertNotIn((self.p.id, sid), self.daemon._HELD_PASSES)

    def test_what_moves_during_a_pass_is_the_next_passs(self):
        sid = self.stopped()
        self.say("@alpha later")
        real = sminos.deliver_next

        def admitted_meanwhile(project, member):
            got = real(project, member)
            os.makedirs(sminos.holder_module().home(), exist_ok=True)
            with open(os.path.join(sminos.holder_module().home(), "mid.json"), "w") as f:
                f.write("{}")   # a receipt written while the pass ran
            return got
        with mock.patch.object(sminos, "deliver_next", side_effect=admitted_meanwhile):
            self.tick()
        with mock.patch.object(sminos, "deliver_next", wraps=sminos.deliver_next) as passes:
            self.tick()
            self.assertEqual(passes.call_count, 1, "not skipped on a snapshot taken after the change")
            self.tick()
            self.assertEqual(passes.call_count, 1, "then skipped")

    def test_a_report_that_could_not_be_written_is_not_remembered_as_done(self):
        hub, sid = self.hub_stopped()
        sminos.log_append(hub, "othermachine/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "from elsewhere"})
        outcomes = sminos.sibling_module("sminos_outcomes")
        with mock.patch.object(outcomes.Outbox, "record", side_effect=OSError("disk full")):
            sminos.forget_caches()
            self.daemon.deliver_owed(hub, sminos.view_of(hub, titles=False))
        self.assertNotIn((hub.id, sid), self.daemon._HELD_PASSES, "a report still owed")
        sminos.forget_caches()
        self.daemon.deliver_owed(hub, sminos.view_of(hub, titles=False))
        self.assertEqual([r["outcome"] for r in self.outbox(hub)], ["recorded"], "written by the next pass")
        self.assertIn((hub.id, sid), self.daemon._HELD_PASSES)

    def test_daemon_owed_counts_what_is_held_as_waiting_for_a_closed_session(self):
        sid = self.stopped()
        self.say("@alpha later")
        code, out = self.cli("daemon", "owed")
        self.assertEqual(code, 0, out)
        self.assertIn("closed sessions 1", out)
        self.assertIn("nothing owed", out)
        outcomes = sminos.sibling_module("sminos_outcomes")
        self.assertIn(sid, outcomes.closed_sessions(sminos.view_of(self.p)))

    def test_an_outside_event_is_reported_recorded_once_and_stays_owed(self):
        hub = sminos.make_project(str(uuidlib.uuid4()), "hubbed", "", "", {"url": "http://127.0.0.1:9",
                                                                           "org": "org-1"})
        sminos.project_path(hub, "log")
        sid = str(uuidlib.uuid4())
        threads.ensure(sid)   # a thread its human opened, its process gone
        sminos.lifecycle(hub, sid, "joined", alias="alpha", name_source="user", machine=sminos.host_name(),
                         cwd=self.root, worktree="", role="", seat="", by="", session_kind="interactive")
        sminos.log_append(hub, "othermachine/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "from elsewhere"})
        outcomes = sminos.sibling_module("sminos_outcomes")
        for _ in range(3):
            sminos.forget_caches()
            self.daemon.tick(hub)
        with open(os.path.join(hub.home, outcomes.OUTBOX)) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        self.assertEqual([(r["session"], r["outcome"]) for r in rows], [(sid, "recorded")], "once")
        self.assertEqual(len(sminos.owed(hub, self.member(sid, hub))), 1, "and still owed")


# ------------------------------------------------------------ X3: whether its machine wakes it


class Wake(Rig):
    def test_a_stopped_threads_state_carries_its_value_whichever_writer_writes_it(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        sminos.lifecycle(self.p, sid, "state", state="stopped", machine="testhost")
        self.assertEqual(self.own(sid)[-1].get("wake"), "held")
        sminos.lifecycle(self.p, sid, "state", state="idle", machine="testhost")
        self.assertNotIn("wake", self.own(sid)[-1], "only on a stopped one")
        # A newly admitted audience's snapshot restates the state through the same writer.
        visibility = sminos.sibling_module("sminos_visibility")
        self.write_own(sid, [{"kind": "retired", "by": "", "reason": "moved", "project": "elsewhere"}])
        self.write_own(sid, [self.old_joined(sid, alias="alpha")])   # a joined to restate
        with mock.patch.object(sminos, "view_of", return_value=type("V", (), {
                "members": [self.member(sid)._replace(state="stopped")], "info": {}})()):
            visibility.snapshot(sid, self.p)
        states = [e for e in self.own(sid) if e["kind"] == "state"]
        self.assertEqual(states[-1].get("wake"), "held")

    def test_a_stopped_seats_state_says_it_is_woken(self):
        sid, _ = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        sminos.lifecycle(self.p, sid, "state", state="stopped", machine="testhost")
        self.assertEqual(self.own(sid)[-1].get("wake"), "woken")

    def test_publish_state_writes_it_again_when_only_the_value_changes(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        record = {}
        view = sminos.view_of(self.p, titles=False)
        self.daemon.publish_state(self.p, view, record)
        self.assertEqual(self.own(sid)[-1].get("wake"), "held")
        with mock.patch.object(sminos, "wake_published", return_value=("woken", "")):
            sminos.forget_caches()
            n = self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record)
        self.assertEqual((n, self.own(sid)[-1].get("state"), self.own(sid)[-1].get("wake")), (1, "stopped", "woken"))
        sminos.forget_caches()
        with mock.patch.object(sminos, "wake_published", return_value=("woken", "")):
            self.assertEqual(self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record), 0)

    def test_an_adopted_seat_stopped_before_its_adoption_gets_its_value_once(self):
        sid, proc = self.session()
        self.transcript(sid, mode="auto")
        self.cli("seat", "add", "g", "w", "--session", sid)
        self.reconcile()
        self.end(proc)
        self.write_own(sid, [{"kind": "state", "state": "stopped", "machine": "testhost"}])   # an older copy's
        self.assertNotIn("thread", self.own(sid)[-1])
        record = {}
        sminos.forget_caches()
        self.assertEqual(self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record), 1)
        last = self.own(sid)[-1]
        self.assertEqual((last["state"], last.get("wake"), bool(last.get("thread"))), ("stopped", "woken", True))
        sminos.forget_caches()
        self.assertEqual(self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record), 0,
                         "and not again")

    def remote(self, wake):
        sid = str(uuidlib.uuid4())
        w = "elsewhere/%s" % sid
        sminos.log_append(self.p, w, "joined", session=sid, alias="far", name_source="user", machine="elsewhere",
                          cwd="/w", worktree="", role="", seat="", by="", session_kind="interactive",
                          thread=str(uuidlib.uuid4()))
        sminos.log_append(self.p, w, "state", session=sid, state="stopped", machine="elsewhere",
                          **({"wake": wake} if wake else {}))
        sminos.forget_caches()
        return sid

    def test_a_sender_is_told_what_the_far_machine_published(self):
        for wake, line in (("held", "far: recorded and held on elsewhere: the session is stopped, and a session "
                                    "its human opened is not woken"),
                           ("woken", "far: recorded (on elsewhere): the session is stopped, and its machine wakes "
                                     "it with this"),
                           (None, "far: recorded (on elsewhere)\n")):
            with self.subTest(wake=wake):
                sid = self.remote(wake)
                self.assertEqual(sminos.wake_of(self.member(sid)), wake)
                code, out = self.say("@far#%s hi" % sid[:8])
                self.assertEqual(code, 0, out)
                self.assertIn(line, out)

    def test_send_tells_what_the_far_machine_published_and_a_held_wait_records_and_exits_4(self):
        for wake, line in (("held", "for far: recorded and held on elsewhere: the session is stopped"),
                           ("woken", "for far: recorded (on elsewhere): the session is stopped, and its machine "
                                     "wakes it"),
                           (None, "for far on elsewhere — its machine delivers it")):
            with self.subTest(wake=wake):
                sid = self.remote(wake)
                code, out = self.cli("send", "far#%s" % sid[:8], "a note")
                self.assertEqual(code, 0, out)
                self.assertIn(line, out)
                owed = len(self.owed_to(sid))
                code, out = self.cli("send", "far#%s" % sid[:8], "and wait", "--wait")
                self.assertEqual(code, 4 if wake == "held" else 2, out)
                self.assertEqual(len(self.owed_to(sid)), owed + (1 if wake == "held" else 0),
                                 "a known hold appends, and waits for nothing")
                if wake == "held":
                    self.assertIn("recorded and held on elsewhere", out)
                    self.assertIn("nothing was started", out)


# ------------------------------------------------------------ the sweep's stop mark


class Sweep(Rig):
    def test_the_stop_is_marked_after_two_passes_and_lifted_when_a_process_holds_it_again(self):
        sid, proc = self.opened()
        tid = threads.stamp(sid)
        self.end(proc)
        self.daemon.sweep_threads()
        self.assertNotIn("stopped", threads.get(tid), "one pass is not a stop")
        sminos.forget_caches()
        self.daemon.sweep_threads()
        stopped = threads.get(tid)["stopped"]
        sminos.forget_caches()
        self.daemon.sweep_threads()
        self.assertEqual(threads.get(tid)["stopped"], stopped, "kept as it was")
        self.live(sid=sid)
        self.daemon.sweep_threads()
        self.assertNotIn("stopped", threads.get(tid))

    def test_a_pass_between_two_never_marks_while_the_resume_lock_is_held(self):
        sid, _ = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.stop_all()   # its process stops, as a resume's first step does
        import fcntl
        with open(os.path.join(sminos.root(), seat_id + ".resume.lock"), "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            for _ in range(3):
                sminos.forget_caches()
                self.daemon.sweep_threads()
            fcntl.flock(lf, fcntl.LOCK_UN)
        self.assertNotIn("stopped", threads.get(seat_id))
        for _ in range(2):
            sminos.forget_caches()
            self.daemon.sweep_threads()
        self.assertIn("stopped", threads.get(seat_id), "two passes after the resume let go")


# ------------------------------------------------------------ a /clear


class Clear(Rig):
    NEW = "11111111-2222-4333-8444-555555555555"

    def setUp(self):
        super().setUp()
        self.old, self.proc = self.opened(started=int((time.time() - 30) * 1000))
        self.tid = threads.stamp(self.old)

    def note(self, reason="clear", session=None, pid=None, env=None):
        """The engine's SessionEnd through the hook, as the engine runs it in the process."""
        return subprocess.run([HOOK], input=json.dumps({"session_id": session or self.old, "reason": reason,
                                                        "hook_event_name": "SessionEnd"}),
                              text=True, capture_output=True,
                              env={**os.environ, "CLAUDE_PID": str(pid or self.proc.pid), **(env or {})})

    def start(self, source="clear", record=True, guide=False, names=None):
        """The new session's SessionStart in the same process: the engine's
        record names it (or, `names`, still another), and its hooks run."""
        self.peer_set(self.proc, sessionId=names or self.NEW)
        env = {"CLAUDE_PID": str(self.proc.pid), "CLAUDE_CODE_SESSION_ID": self.NEW}
        out = ""
        if guide:
            with mock.patch.dict(os.environ, env), mock.patch.object(sminos, "enrollment",
                                                                     return_value={"machine": "testhost", "org": "org-1", "url": ""}):
                sminos.forget_caches()
                out = sminos.guide_text(self.NEW, self.root, source)
        if record:
            self.hook(self.NEW, source=source, env=env)
        return out

    def test_the_note_is_kept_for_a_clear_alone(self):
        d = os.path.join(sminos.root(), sminos.CLEARED)
        self.assertEqual(self.note(reason="logout").returncode, 0)
        self.assertFalse(os.path.exists(d))
        self.assertEqual(self.note(env={"SMNS_INTERNAL": "1"}).returncode, 0)
        self.assertFalse(os.path.exists(d))
        got = self.note()
        self.assertEqual((got.returncode, got.stdout), (0, ""))
        self.assertEqual(os.listdir(d), ["%d.json" % self.proc.pid])
        with open(sminos.cleared_note_path(self.proc.pid)) as f:
            self.assertEqual(json.load(f)["session_id"], self.old)

    def assert_transferred(self):
        new = self.member(self.NEW)
        self.assertEqual(new.alias, "alpha", "the new session holds the alias")
        old = self.member(self.old)
        self.assertEqual((old.alias, old.charge), (self.old[:8], "owns alpha"), "the session left: its short id")
        self.assertNotEqual(new.thread, old.thread, "another thread")
        self.assertEqual(threads.thread_of(self.old)["thread"], self.tid)
        self.assertFalse([e for e in self.own(self.old) if e.get("reason") == "continued"], "no continuation")
        self.assertNotIn(self.old, (records.read(self.NEW) or {}).get("former") or [])
        sminos.forget_caches()
        self.assertEqual(sminos._resolve_tag(self.p, {"raw": "@alpha", "project": "", "name": "alpha",
                                                      "short": ""})[1].session, self.NEW, "a bare @alias")
        for name, short in (("alpha", self.old[:8]), (self.old[:8], "")):
            with self.subTest(name=name, short=short):
                sminos.forget_caches()
                tag = {"raw": "@%s" % name, "project": "", "name": name, "short": short}
                self.assertEqual(sminos._resolve_tag(self.p, tag)[1].session, self.old)

    def test_the_new_session_takes_the_alias_and_the_one_left_is_stopped_under_its_short_id(self):
        self.note()
        self.start()
        e = [x for x in self.own(self.old) if x["kind"] == "renamed"][-1]
        self.assertEqual((e["alias"], e["name_source"], e["thread"], bool(e.get("op"))),
                         (self.old[:8], "derived", self.tid, True))
        self.assertEqual(threads.get(self.tid)["released"]["alias"], "alpha")
        self.assert_transferred()

    def test_the_guide_names_the_new_session_by_the_alias_whichever_hook_runs_first(self):
        for guide_first in (True, False):
            with self.subTest(guide_first=guide_first):
                if not guide_first:
                    self.fresh()
                self.note()
                if guide_first:
                    out = self.start(guide=True, record=False)
                    self.start()
                else:
                    self.start()
                    out = self.start(guide=True, record=False)
                self.assertIn("you are alpha [%s]" % self.NEW[:8], out)
                self.assert_transferred()

    def test_a_rename_pass_between_the_release_and_the_join_does_not_put_the_name_back(self):
        self.note()
        real = sminos.join_on_sight

        def between(*a, **k):
            # The engine's record still names the session left, under the name.
            self.peer_set(self.proc, sessionId=self.old)
            sminos.forget_caches()
            self.daemon.publish_renames(self.p, sminos.view_of(self.p, titles=False))
            self.peer_set(self.proc, sessionId=self.NEW)
            sminos.forget_caches()
            return real(*a, **k)
        with mock.patch.object(sminos, "join_on_sight", side_effect=between):
            self.start()
        renames = [x["alias"] for x in self.own(self.old) if x["kind"] == "renamed"]
        self.assertEqual(renames, [self.old[:8]], "the name did not go back")
        self.assert_transferred()

    def test_a_rename_chosen_from_a_view_before_the_release_does_not_undo_it(self):
        """publish_renames run between the release and the new session's
        join, from a view it took before the release."""
        self.peer_set(self.proc, name="alpha-two")   # its human renames it: a rename is due in this view
        sminos.forget_caches()
        before = sminos.view_of(self.p, titles=False)
        self.assertEqual(next(m for m in before.members if m.session == self.old).alias, "alpha-two")
        self.peer_set(self.proc, name="alpha")
        self.note()
        self.start()
        self.assertEqual(self.daemon.publish_renames(self.p, before), 0, "the stale choice is not appended")
        renames = [x["alias"] for x in self.own(self.old) if x["kind"] == "renamed"]
        self.assertEqual(renames[-1], self.old[:8], "the release stands")

    def test_a_release_cut_after_the_records_write_is_finished_from_the_journal(self):
        self.note()
        real = threads.begin

        def begin(*a, **k):
            if real(*a, **k) is not None:
                raise Killed()
            return None
        with mock.patch.object(threads, "begin", side_effect=begin), self.assertRaises(Killed):
            self.start()
        self.assertEqual(threads.get(self.tid)["pending"]["op"], "release")
        self.reconcile()
        self.assertIsNone(threads.get(self.tid).get("pending"))
        self.assertEqual([x["alias"] for x in self.own(self.old) if x["kind"] == "renamed"], [self.old[:8]])
        self.reconcile()
        self.assertEqual([x["alias"] for x in self.own(self.old) if x["kind"] == "renamed"], [self.old[:8]], "once")

    def assert_no_transfer(self):
        self.assertNotIn("released", threads.get(self.tid))
        self.assertEqual([x for x in self.own(self.old) if x["kind"] == "renamed"], [])
        self.assertEqual(self.member(self.NEW).alias, self.NEW[:8], "the new session goes by its short id")
        self.assertEqual(self.member(self.old).alias, "alpha")

    def test_no_transfer_without_a_believable_witness(self):
        cases = {
            "no note": lambda: None,
            "an old note": lambda: (self.note(), os.utime(sminos.cleared_note_path(self.proc.pid),
                                                          (time.time() - 61, time.time() - 61))),
            "another process's": lambda: self.note(pid=self.proc.pid + 1),
            "the starting session's": lambda: self.note(session=self.NEW),
            "a note written before the process started": lambda: (self.note(), self.peer_set(
                self.proc, startedAt=int((time.time() + 5) * 1000))),
        }
        for why, make in cases.items():
            with self.subTest(why=why):
                self.fresh()
                make()
                self.start()
                self.assert_no_transfer()
        with self.subTest(why="a start whose source is not clear"):
            self.fresh()
            self.note()
            self.start(source="resume")
            self.assert_no_transfer()

    def test_the_release_goes_to_the_project_the_session_left_is_a_member_of(self):
        other = self.project_of(self.repo("other"))
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": self.old}):
            code, out = self.cli("join", other.name)
        self.assertEqual(code, 0, out)
        self.note()
        self.start()
        self.assertEqual(threads.get(self.tid)["released"]["alias"], "alpha")
        renamed = [x for x in self.own(self.old, other) if x["kind"] == "renamed"]
        self.assertEqual([(x["alias"], x["thread"]) for x in renamed], [(self.old[:8], self.tid)],
                         "journaled where its membership is in effect")
        self.assertEqual(self.member(self.NEW).alias, "alpha", "the new session in its launch's project")
        self.assertIsNone(self.member(self.NEW, other), "the join is not the new session's")

    def test_the_session_left_run_again_keeps_its_short_id_and_its_release_is_let_go_of(self):
        self.note()
        self.start()
        self.live(sid=self.old, name="alpha", started=int((time.time() + 1) * 1000))
        self.reconcile()
        self.assertEqual(self.member(self.old).alias, self.old[:8], "the new session holds the name")
        self.daemon.sweep_threads()
        self.assertNotIn("released", threads.get(self.tid), "a process started after the release holds it")
        self.assertEqual(self.member(self.old).alias, self.old[:8], "and the name stays the new session's")


# ------------------------------------------------------------ the verbs that start a process


class Verbs(Rig):
    """A session its human opened that is held (here for `mode`, the rig's
    last turn being `plan`): `send` is held as a tagged say is; `resume`,
    `fill --resume` and `send --wait` record their message, start nothing,
    say why and exit 4 (T2's §6; the verbs that wake one are
    test_wake_verbs.py's); a fresh `fill` and a `spawn` onto its alias are
    refused and record nothing."""

    def setUp(self):
        super().setUp()
        self.sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        self.launched = []
        for name in ("run_claude_bg", "claude_stop"):
            patcher = mock.patch.object(sminos, name, side_effect=lambda *a, **k: self.launched.append(a) or ("", ""))
            patcher.start()
            self.addCleanup(patcher.stop)

    def owed_texts(self, sid=None):
        m = self.member(sid or self.sid)
        return [e["text"] for e in sminos.owed(self.p, m)]

    def test_send_is_recorded_and_held(self):
        code, out = self.cli("send", "alpha", "while you are away")
        self.assertEqual(code, 0, out)
        self.assertIn("for alpha: recorded and held", out)
        self.assertEqual(self.owed_texts(), ["while you are away"])
        self.assertEqual(self.launched, [])

    def test_resume_fill_resume_and_send_wait_record_their_message_start_nothing_and_exit_4(self):
        for argv, text in ((("resume", "alpha", "pick it up"), "pick it up"),
                           (("fill", "alpha", "carry on", "--resume"), "carry on"),
                           (("send", "alpha", "and answer", "--wait"), "and answer")):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("recorded and held", out.splitlines()[0])
                self.assertIn("nothing was started: a wake would run it in a mode that asks for approval", out)
                self.assertEqual(self.owed_texts()[-1], text)
        self.assertEqual(len(self.owed_texts()), 3)
        self.assertEqual(self.launched, [], "no claude call")

    def test_a_fresh_fill_and_a_spawn_onto_its_alias_are_refused_and_record_nothing(self):
        for argv in (("fill", "alpha", "a new task"), ("spawn", "alpha", "a new task")):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("its human", out)
        self.assertEqual(self.owed_texts(), [])
        self.assertEqual(list(sminos.record_files()), [], "no seat made")
        self.assertEqual(self.launched, [])

    def seated(self):
        """The stopped human-opened session given a seat by an older CLI (D7)."""
        seat_id = str(uuidlib.uuid4())
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": self.sid, "alias": "w", "group": "g", "cwd": self.root,
                                  "status": "idle", "short": "ab12cd34"})
        sminos.forget_caches()
        return seat_id

    def test_a_human_opened_session_with_a_seat_is_held_and_neither_filled_nor_spawned_onto(self):
        self.seated()
        for argv, code_wanted in ((("resume", "g/w", "go on"), 4), (("fill", "g/w", "go on", "--resume"), 4),
                                  (("fill", "g/w", "fresh"), 4), (("send", "g/w", "a note"), 0),
                                  (("send", "g/w", "a note", "--wait"), 4)):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, code_wanted, out)
                self.assertNotIn("Traceback", out)
        with mock.patch.dict(os.environ, {"PWD": self.root}):
            code, out = self.cli("spawn", "w", "fresh")
        self.assertEqual(code, 4, out)
        self.assertEqual(self.launched, [], "no claude call")
        self.assertEqual(set(self.attempts(self.sid).values()) - {0}, set(), "no attempt counted")
        m = self.member(self.sid)
        self.assertEqual(sminos.push_member(m, "x", True), "held:mode")
        self.tick()
        self.assertEqual(self.launched, [])
        self.assertTrue(self.owed_texts(), "what was recorded stays owed")


    def test_a_name_send_refuses_as_ambiguous_resume_and_fill_refuse_too(self):
        other, _ = self.session(name="alpha")
        self.cli("seat", "add", "g", "alpha", "--session", other)   # a seat of the same alias beside it
        self.reconcile()
        for argv in (("send", "alpha", "x"), ("resume", "alpha", "x"), ("fill", "alpha", "x", "--resume")):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("ambiguous", out)
        self.assertEqual(self.launched, [])

    def test_a_refill_between_the_lookup_and_the_lock_does_not_take_the_bound_sessions_place(self):
        first, proc = self.session()
        self.cli("seat", "add", "g", "w", "--session", first)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.end(proc)
        real = sminos.find_target

        def refilled(q):
            got = real(q)
            sminos.meta_set(seat_id, {"current": str(uuidlib.uuid4())})
            return got
        for argv in (("resume", "w#%s" % first[:8], "x"), ("fill", "w#%s" % first[:8], "x", "--resume")):
            with self.subTest(argv=argv), mock.patch.object(sminos, "find_target", side_effect=refilled):
                sminos.meta_set(seat_id, {"current": first})
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("session %s left seat g/w" % first[:8], out)
        self.assertEqual(self.launched, [])

    def test_a_hold_found_under_the_lock_records_against_the_session_checked(self):
        first, proc = self.session()
        self.cli("seat", "add", "g", "w", "--session", first)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.end(proc)
        real = sminos.find_target

        def given_the_held_session(q):
            got = real(q)
            sminos.meta_set(seat_id, {"current": self.sid})   # an older copy seats the stopped human-opened one
            return got
        with mock.patch.object(sminos, "find_target", side_effect=given_the_held_session):
            code, out = self.cli("resume", "g/w", "for whoever holds it")
        self.assertEqual(code, 4, out)
        self.assertIn("nothing was started", out)
        self.assertEqual(self.owed_texts(), ["for whoever holds it"], "to the session the check found")
        self.assertEqual(self.launched, [])

# ------------------------------------------------------------ questions closed while stopped


class Questions(Rig):
    def asked(self, sid, src="toolu_q1"):
        sminos.append_host(self.p, sid, [{"kind": "question", "from": "alpha", "to": "host", "text": ["which way?"],
                                          "choices": [], "src": src}])

    def answers(self, sid):
        return [e for e in self.own(sid) if e["kind"] == "answered"]

    def sweep(self, n=1):
        for _ in range(n):
            sminos.forget_caches()
            self.daemon.sweep_threads()

    def test_an_open_question_is_closed_after_two_passes_once(self):
        sid, proc = self.opened()
        self.asked(sid)
        self.asked(sid, "toolu_q2")
        sminos.append_host(self.p, sid, [{"kind": "answered", "from": "alpha", "src": "toolu_q2", "text": "left"}])
        self.end(proc)
        self.sweep()
        self.assertEqual(len(self.answers(sid)), 1, "one pass is not a stop")
        self.sweep()
        closed = [e for e in self.answers(sid) if e.get("closed")]
        self.assertEqual([(e["src"], e["text"], e["closed"], e["from"]) for e in closed],
                         [("toolu_q1", sminos.QUESTION_CLOSED, "stopped", "alpha")])
        t = threads.thread_of(sid)
        self.assertEqual(t["swept"], t["stopped"])
        self.sweep(2)
        self.assertEqual(len(self.answers(sid)), 2, "once")
        self.live(sid=sid)
        sminos.append_host(self.p, sid, [{"kind": "answered", "from": "alpha", "src": "toolu_q1", "text": "late"}])
        self.assertEqual(len(self.answers(sid)), 2, "a later answer appends nothing")

    def test_a_pass_killed_after_the_stop_was_marked_leaves_it_to_the_next(self):
        sid, proc = self.opened()
        self.asked(sid)
        self.end(proc)
        self.sweep()
        with mock.patch.object(sminos, "close_questions", side_effect=OSError("disk full")):
            self.sweep()
        t = threads.thread_of(sid)
        self.assertIn("stopped", t)
        self.assertNotIn("swept", t)
        self.assertEqual(self.answers(sid), [])
        self.sweep()
        self.assertEqual(len(self.answers(sid)), 1)

    def test_not_during_a_resumes_stop_and_relaunch(self):
        sid, _ = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.asked(sid)
        self.stop_all()
        import fcntl
        with open(os.path.join(sminos.root(), seat_id + ".resume.lock"), "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            self.sweep(3)
            fcntl.flock(lf, fcntl.LOCK_UN)
        self.assertEqual(self.answers(sid), [])


    def test_a_retry_of_a_marked_stop_is_kept_out_by_the_resume_lock_and_checked_again(self):
        sid, proc = self.session()
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.asked(sid)
        self.end(proc)
        self.sweep()
        with mock.patch.object(sminos, "close_questions", side_effect=OSError("disk full")):
            self.sweep()   # the stop marked, its closing cut
        self.assertIn("stopped", threads.get(seat_id))
        self.assertNotIn("swept", threads.get(seat_id))
        import fcntl
        with open(os.path.join(sminos.root(), seat_id + ".resume.lock"), "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            self.sweep(2)
            fcntl.flock(lf, fcntl.LOCK_UN)
        self.assertEqual(self.answers(sid), [], "not while a resume holds its lock")
        # Its process back between the pass's read and its decision: checked again, afresh, under the lock.
        real = sminos.running_now
        with mock.patch.object(sminos, "running_now", side_effect=lambda s: {"pid": 1} if s == sid else real(s)):
            self.sweep()
        self.assertEqual(self.answers(sid), [], "nor once a process holds it again")
        self.sweep()
        self.assertEqual(len(self.answers(sid)), 1, "then closed, once")


    def test_a_spawned_resume_during_the_sweeps_hold_waits_it_out_with_no_attempt_counted(self):
        import threading
        sid, proc = self.session()
        self.transcript(sid, mode="auto")
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.end(proc)
        launched = []

        def start(args, cwd, settings):   # the resume's engine: the session's process again
            launched.append(args)
            self.session(sid=sid, kind="bg")
            return sid[:8], "backgrounded · %s" % sid[:8]
        with mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                mock.patch.object(sminos, "poll_uuid", return_value=(sid, "working", self.root)), \
                mock.patch.object(sminos, "claude_stop", return_value=None):
            for hold_for_s, wait_s in ((0.4, 5.0), (1.0, 0.2)):
                with self.subTest(hold=hold_for_s, wait=wait_s), mock.patch.object(sminos, "SWEEP_WAIT", wait_s):
                    held, release = threading.Event(), threading.Event()

                    def sweep_hold():
                        with self.daemon.resume_lock_out(seat_id) as out:
                            self.assertTrue(out)
                            held.set()
                            release.wait(hold_for_s)
                    t = threading.Thread(target=sweep_hold)
                    t.start()
                    held.wait(5)
                    code, out = self.cli("send", "g/w", "while the sweep decides")
                    release.set()
                    t.join(5)
                    self.assertNotIn("in flight", out)
                    self.assertNotIn("Traceback", out)
                    self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
                    if wait_s > hold_for_s:
                        self.assertEqual(code, 0, out)
                        self.assertNotIn("waits for the thread sweep", out, "waited out")
                        self.assertEqual(len(launched), 1, "and resumed")
                        self.stop_all()
                        for p_ in list(self.procs):
                            self.procs.remove(p_)
                        for f in os.listdir(os.path.join(os.environ["HOME"], ".claude", "sessions")):
                            os.unlink(os.path.join(os.environ["HOME"], ".claude", "sessions", f))
                        sminos.forget_caches()
                    else:
                        self.assertEqual(code, 0, out)
                        self.assertIn("its process is starting, and the daemon delivers it", out, "tried again later")
                        self.assertTrue(self.owed_to(sid), "owed for the next pass")

    def test_a_resume_that_meets_the_sweep_releasing_its_lock_takes_it_with_no_twin_and_no_attempt(self):
        """The sweep's last moment under the resume lock: its name emptied
        from the file, the lock not yet released. A resume that meets it
        then retries the lock rather than refusing a twin; one whose holder
        never names itself is left owed, no attempt counted."""
        import fcntl
        import threading
        sid, proc = self.session()
        self.transcript(sid, mode="auto")
        self.cli("seat", "add", "g", "w", "--session", sid)
        seat_id = sminos.load_seat(next(sminos.record_files()))["seat_id"]
        self.reconcile()
        self.end(proc)
        launched = []

        def start(args, cwd, settings):
            launched.append(args)
            self.session(sid=sid, kind="bg")
            return sid[:8], "backgrounded · %s" % sid[:8]
        path = os.path.join(sminos.root(), seat_id + ".resume.lock")
        real_flock = fcntl.flock
        # The one that never names itself first: the resume that takes the lock keeps it (an in-process cli).
        for releases, wait_s in ((False, 0.3), (True, 5.0)):
            with self.subTest(releases=releases):
                sweep = open(path, "a+")
                real_flock(sweep, fcntl.LOCK_EX)
                sweep.seek(0)
                sweep.truncate()   # its name emptied, its lock still held (resume_lock_out's finally)
                sweep.flush()
                met = threading.Semaphore(0)

                def flock(f, op):
                    try:
                        return real_flock(f, op)
                    except OSError:
                        if f is not sweep:
                            met.release()   # the resume met the held lock
                        raise

                def release():
                    for _ in range(3):   # past the resume's first look at it, and two more
                        if not met.acquire(timeout=2):
                            break
                    real_flock(sweep, fcntl.LOCK_UN)
                t = threading.Thread(target=release) if releases else None
                if t:
                    t.start()
                with mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                        mock.patch.object(sminos, "poll_uuid", return_value=(sid, "working", self.root)), \
                        mock.patch.object(sminos, "claude_stop", return_value=None), \
                        mock.patch.object(sminos.fcntl, "flock", side_effect=flock), \
                        mock.patch.object(sminos, "SWEEP_WAIT", wait_s):
                    code, out = self.cli("send", "g/w", "while the sweep lets go")
                if t:
                    t.join(5)
                else:
                    real_flock(sweep, fcntl.LOCK_UN)
                sweep.close()
                self.assertNotIn("in flight", out)
                self.assertNotIn("Traceback", out)
                self.assertEqual(code, 0, out)
                self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
                if releases:
                    self.assertEqual(len(launched), 1, "it took the lock and resumed")
                else:
                    self.assertIn("its process is starting, and the daemon delivers it", out,
                                  "a holder that names none is the sweep's moment: a hold that passes (T2's §5)")
                    self.assertEqual(launched, [])
                    self.assertTrue(self.owed_to(sid), "owed for the next pass")


class Derive(Rig):
    def test_derive_all_forks_no_stopped_human_opened_session(self):
        sid, proc = self.opened()
        self.end(proc)
        self.reconcile()
        m = self.member(sid)
        self.assertIn("its human opened it", sminos.derive_refusal(self.p, m))
        fork = sminos.sibling_module("sminos_fork")
        with mock.patch.object(fork, "headless_fork") as forked:
            self.cli("derive", "--all")
        forked.assert_not_called()


    def test_derive_forks_nothing_once_a_clear_moved_its_session_away_after_the_refusal_read_it(self):
        """A live session its human opened, whose process `/clear`s after
        derive_refusal read this process's copy of the engine's records:
        neither the fork straight after it nor the one after a failed side
        question starts, and nothing is stamped failed."""
        sid, proc = self.opened()
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-work")
        with open(os.path.join(d, sid + ".jsonl"), "a") as f:
            for i in range(sminos.DERIVE_MIN_TOOL_CALLS):
                f.write(json.dumps({"type": "assistant", "sessionId": sid, "message": {
                    "role": "assistant", "content": [{"type": "tool_use", "id": "t%d" % i, "name": "Bash",
                                                      "input": {}}]}}) + "\n")
        m = self.member(sid)
        fork = sminos.sibling_module("sminos_fork")
        refusal = sminos.derive_refusal

        def clear():
            self.peer_set(proc, sessionId=str(uuidlib.uuid4()))

        def refused_then_cleared(*a, **k):
            why = refusal(*a, **k)
            self.assertEqual(why, "", "this process's copy: it runs")
            clear()
            return why

        def btw_cleared(*_a, **_k):
            clear()
            raise fork.ForkFailed("aborted")
        for name, offers, btw, refused in (("no side question", False, None, refused_then_cleared),
                                          ("after the side question failed", True, btw_cleared, refusal)):
            with self.subTest(name):
                self.peer_set(proc, sessionId=sid)
                sminos.forget_caches()
                sminos.peer_records()
                with mock.patch.object(sminos, "derive_refusal", side_effect=refused), \
                        mock.patch.object(fork, "bridge_offers", return_value=offers), \
                        mock.patch.object(fork, "ask_btw", side_effect=btw), \
                        mock.patch.object(fork, "headless_fork", return_value=mock.Mock(
                            text="in charge of nothing", via="a headless fork",
                            usage={"cacheRead": 0, "input": 0})) as forked, \
                        contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(sminos.derive_member(self.p, m, held_off=True), "refused")
                forked.assert_not_called()
                self.assertIn("its human opened it", out.getvalue())
                self.assertIsNone(sminos.derive_failed_age(sid), "nothing stamped failed")


if __name__ == "__main__":
    unittest.main()
