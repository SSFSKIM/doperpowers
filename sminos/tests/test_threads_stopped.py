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

from test_threads import BASE, Killed, Machine, records, sminos, threads  # noqa: E402

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

    def transcript(self, sid):
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-work")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "a") as f:
            f.write(json.dumps({"type": "user", "sessionId": sid, "cwd": self.root,
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
            wait_for(lambda: os.path.exists(sock))
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
            self.assertIn("alpha: recorded and held: the session is stopped, and a session its human opened is not "
                          "woken; it reads this when its human reopens it", out)
        for _ in range(sminos.DELIVERY_ATTEMPTS + 2):
            self.tick()
        self.assertEqual(len(self.owed_to(sid)), 2)
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
        self.assertEqual(threads.hold_of(sid), "human")
        self.assertEqual(self.member(sid).state, "stopped")

    def test_push_member_holds_an_addressed_frame_and_records_one_for_the_live_alone(self):
        sid = self.stopped()
        m = self.member(sid)
        self.assertEqual(sminos.push_member(m, "x", True), sminos.HELD_HUMAN)
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

    def test_a_tick_passes_a_held_backlog_by_on_the_memory_of_a_full_pass(self):
        sid = self.stopped()
        for n in range(20):
            sminos.log_append(self.p, "testhost/human", "human", **{
                "from": "human", "to": [{"session": sid, "alias": "alpha"}], "text": "held %d" % n})
        self.tick()   # the full pass that leaves the memory
        with mock.patch.object(sminos, "deliver_next", wraps=sminos.deliver_next) as passes, \
                mock.patch.object(sminos, "flocked", wraps=sminos.flocked) as locks:
            self.tick()
            self.tick()
            self.assertEqual(passes.call_count, 0, "no delivery pass")
            self.assertFalse([c for c in locks.call_args_list if "delivered" in str(c)], "no delivery lock")
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
        with mock.patch.object(sminos, "hold_for", return_value=""):
            sminos.forget_caches()
            n = self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record)
        self.assertEqual((n, self.own(sid)[-1].get("state"), self.own(sid)[-1].get("wake")), (1, "stopped", "woken"))
        sminos.forget_caches()
        with mock.patch.object(sminos, "hold_for", return_value=""):
            self.assertEqual(self.daemon.publish_state(self.p, sminos.view_of(self.p, titles=False), record), 0)

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
                           ("woken", "far: recorded (on elsewhere)"),
                           (None, "far: recorded (on elsewhere)")):
            with self.subTest(wake=wake):
                sid = self.remote(wake)
                self.assertEqual(sminos.wake_of(self.member(sid)), wake)
                code, out = self.say("@far#%s hi" % sid[:8])
                self.assertEqual(code, 0, out)
                self.assertIn(line, out)


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

    def test_the_session_left_run_again_keeps_its_short_id_and_its_release_is_let_go_of(self):
        self.note()
        self.start()
        self.live(sid=self.old, name="alpha", started=int((time.time() + 1) * 1000))
        self.reconcile()
        self.assertEqual(self.member(self.old).alias, self.old[:8], "the new session holds the name")
        self.daemon.sweep_threads()
        self.assertNotIn("released", threads.get(self.tid), "a process started after the release holds it")
        self.assertEqual(self.member(self.old).alias, self.old[:8], "and the name stays the new session's")


if __name__ == "__main__":
    unittest.main()
