#!/usr/bin/env python3
"""Delivery wakes every stopped thread, and holds what it cannot push (T2's
M3: docs/doperpowers/plans/2026-11-20-sminos-threads-t2.md, the milestone's
"Proves"; Interfaces §4 and the local half of §5), against the test engine:

- `say` with a tag, a plain `send` and a message from another project wake a
  closed thread its human opened under its own id, with a first wake's flags,
  and push the message once, opened by the line; a later message goes to the
  process still up, or wakes it again with no flag; an event for the live
  alone wakes nothing;
- one, two and five senders, one and three messages each: one launch, every
  message in the inbox exactly once and in its sender's order;
- two deliverers together, from one project and from two, one launch; the line on the first frame when
  another deliverer pushes before the wake has returned;
- each reason a thread is not woken held with its mark, for each kind of
  thread it applies to, its sender told why in §5's words; pushed once a
  process of the thread takes it; `read-only` for an outside event; a process
  with no inbox yet; a live inbox pushed to while a reason still reads true;
- a failed wake held and tried again on §4's schedule, a sender's own call
  trying at once, and the line in daemon.log at the fifth failure;
- a session turned lane B, a record that cannot be read; a marked event of a
  spawned thread settled at its end; a refill settling what was held;
- one reach permit serving a wake and the push after it;
- no fork by derive, no young-background wait, and a tick that launches
  nothing and lists no job for a thread nothing is owed to.

The wake itself is test_wake_seat.py's; the transitions against it are
test_wake_transitions.py's. Hermetic: test_wake.Engine (HOME, SMINOS_HOME
and the engine's state temporary, the engine first on PATH and checked to
be, every teardown failing on a resume that carried a message).
Run: python3 -B sminos/tests/test_wake_delivery.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_wake import rows, wait_for  # noqa: E402
from test_wake_seat import INBOX, SCRIPT, Wakers, records, sminos, threads, wake  # noqa: E402

TAIL = "; it is pushed when a process of it runs again before it ends (three days stopped, or a retire), else it " \
       "stays in the log"
HEAD = "recorded and held: the session is stopped and is not woken: "
STARTING = "recorded: its process is starting, and the daemon delivers it"
WORDS = {
    "config": "it runs under another config dir",
    "transcript": "no conversation of it is on that machine",
    "cwd": "its directory is gone",
    "protected": "its directory is in a folder macOS protects, where a background launch would stop at a prompt "
                 "for its human",
    "mode": "a wake would run it in a mode that asks for approval",
    "failed": "waking it failed, and its machine tries again",
}
FLAGS = ["--permission-mode", "auto", "--model", "claude-term"]


def line(why):
    return HEAD + WORDS[why] + TAIL


class Deliveries(Wakers):
    def setUp(self):
        super().setUp()
        self.daemon = sminos.daemon_module()
        self.daemon._HELD_PASSES.clear()

    def frames(self, sid):
        return [i["message"]["content"] for i in self.inputs(sid)]

    def say(self, text, sender=None, cwd=None):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sender} if sender else {}):
            if not sender:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            return self.cli("say", text, cwd=cwd)

    def send(self, target, text, sender=None):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sender} if sender else {}):
            if not sender:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            return self.cli("send", target, text)

    def member(self, sid, p=None):
        sminos.forget_caches()
        return next((m for m in sminos.view_of(p or self.p).members if m.session == sid), None)

    def owed(self, sid, p=None):
        m = self.member(sid, p)
        return [re.sub(r"^@\S+ ", "", e["text"]) for e in sminos.owed(p or self.p, m)] if m else []   # its tag off

    def marked(self, sid, p=None):
        """{(writer, seq): the thread its hold names} of the session's delivery record."""
        out = {}
        for w, d in sminos.delivered_load(p or self.p, sid).items():
            for seq, t in (d.get("held") or {}).items():
                out[(w, int(seq))] = t
        return out

    def attempts(self, sid, p=None):
        return {w: d.get("attempts", 0) for w, d in sminos.delivered_load(p or self.p, sid).items()}

    def tick(self, p=None):
        sminos.forget_caches()
        return self.daemon.deliver_owed(p or self.p, sminos.view_of(p or self.p))

    def live_sender(self, name, root=None, p=None):
        sid, _ = self.session(root=root, name=name)
        self.reconcile(p)
        return sid

    def shown(self, out, sid):
        """deliver_say's line for its one recipient (named as the say found it: a woken session may be renamed by
        its process's own record after)."""
        return [ln.split(": ", 1)[1] for ln in out.splitlines()
                if ": " in ln and not ln.startswith(("recorded ", "copy ", "sminos:"))]

    def seat_in(self, alias, where):
        """A seat spawned from `where` (a directory of the project), its first turn run and its process stopped."""
        os.makedirs(where, exist_ok=True)
        code, out = self.cli("spawn", alias, "the task", cwd=where)
        self.assertEqual(code, 0, out)
        s = next(x for x in sminos.seats() if x["alias"] == alias)
        self.assertTrue(wait_for(lambda: self.record(s["current"]) is not None))
        self.stop(s["current"])
        return sminos.reload_seat(s["seat_id"])

    def vault(self):
        """A directory of the project that this machine reads as in a protected folder, and nothing else."""
        where = os.path.realpath(os.path.join(self.root, "vault"))
        os.makedirs(where, exist_ok=True)
        for name, value in (("TCC", True),
                            ("protected_folder", lambda path: where if os.path.realpath(path).startswith(where)
                             else "")):
            p = mock.patch.object(sminos, name, value)
            p.start()
            self.addCleanup(p.stop)
        return where

    def owes(self, sid, text, p=None):
        return [t for t in self.owed(sid, p) if t.endswith(text)]


# ------------------------------------------------------------ woken by a message


class Woken(Deliveries):
    def test_a_tag_wakes_a_closed_session_its_human_opened_and_its_message_arrives_once_opened_by_the_line(self):
        tid, sid = self.human_thread()
        code, out = self.say("@%s look at this" % sid[:8])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.shown(out, sid), ["sent (woken)"])
        self.assertEqual(self.resumes(sid), [FLAGS], "under its own id, a first wake's flags, no message after them")
        [frame] = self.frames(sid)
        head, _, rest = frame.partition("\n\n")
        self.assertIn(wake.LINE_HEAD, head, "the line opens it")
        self.assertIn("You run in auto mode on claude-term.", head)
        self.assertIn("first run outside the terminal", head)
        self.assertEqual(frame.count("look at this"), 1)
        self.assertEqual(self.record(sid)["name"], "term-a", "the name its human gave it kept")
        self.assertEqual(self.owed(sid), [], "settled once pushed")
        self.assertNotIn("line", self.waking(tid, sid), "the line went with the frame")

    def test_a_plain_send_wakes_it_and_pushes_once(self):
        tid, sid = self.human_thread()
        code, out = self.send(sid[:8], "by send")
        self.assertEqual(code, 0, out)
        self.assertIn("(woken)", out)
        self.assertEqual(self.resumes(sid), [FLAGS])
        [frame] = self.frames(sid)
        self.assertIn(wake.LINE_HEAD, frame.partition("\n\n")[0])
        self.assertEqual(frame.count("by send"), 1)
        self.assertEqual(self.owed(sid), [])

    def test_a_later_message_goes_to_the_process_still_up_and_once_it_ended_wakes_it_with_no_flag(self):
        tid, sid = self.human_thread()
        self.say("@%s one" % sid[:8])
        code, out = self.say("@%s two" % sid[:8])
        self.assertEqual(self.shown(out, sid), ["sent"])
        self.assertEqual(self.resumes(sid), [FLAGS], "no second launch")
        self.assertNotIn(wake.LINE_HEAD, self.frames(sid)[1], "a live push carries no line")
        self.stop(sid)
        code, out = self.say("@%s three" % sid[:8])
        self.assertEqual(self.shown(out, sid), ["sent (woken)"])
        self.assertEqual(self.resumes(sid), [FLAGS, []], "a later wake passes no flag")
        third = self.frames(sid)[2]
        self.assertIn(wake.LINE_HEAD, third.partition("\n\n")[0])
        self.assertNotIn("first run outside the terminal", third)
        self.assertEqual([f.count(t) for f, t in zip(self.frames(sid), ("one", "two", "three"))], [1, 1, 1])

    def test_an_event_for_the_live_alone_wakes_nothing(self):
        tid, sid = self.human_thread()
        code, out = self.say("@all for whoever runs")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.resumes(sid), [], "nothing launched")
        self.assertEqual(self.owed(sid), [], "settled recorded, as for any stopped member")

    def test_the_three_ways_a_message_is_sent_reach_one_process_once_each(self):
        tid, sid = self.human_thread()
        a = self.live_sender("sender-a")
        other = self.repo("other")
        q = self.project_of(other)
        b = self.live_sender("sender-b", root=other, p=q)
        self.say("@%s by say" % sid[:8], sender=a)
        self.stop(sid)
        self.send(sid[:8], "by send")
        self.stop(sid)
        code, out = self.say("@%s from another project" % sid[:8], sender=b, cwd=other)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.resumes(sid)), 3, "each wakes it once, its process stopped between")
        frames = self.frames(sid)
        for text in ("by say", "by send", "from another project"):
            self.assertEqual(sum(f.count(text) for f in frames), 1, text)
        self.assertEqual(self.owed(sid), [])


# ------------------------------------------------------------ several senders, several messages


class Senders(Deliveries):
    def test_one_two_and_five_senders_with_one_and_three_messages_each_wake_once_and_arrive_once_in_order(self):
        senders = [self.live_sender("sender-%d" % i) for i in range(5)]
        for n in (1, 2, 5):
            for k in (1, 3):
                with self.subTest(senders=n, messages=k):
                    tid, sid = self.human_thread()
                    for i in range(k):
                        for j, s in enumerate(senders[:n]):
                            code, out = self.say("@%s m-%d-%d" % (sid[:8], j, i), sender=s)
                            self.assertEqual(code, 0, out)
                    self.assertEqual(len(self.resumes(sid)), 1, "one launch")
                    frames = self.frames(sid)
                    self.assertEqual(len(frames), n * k, "one frame a message")
                    for j in range(n):
                        texts = ["m-%d-%d" % (j, i) for i in range(k)]
                        at = [next(x for x, f in enumerate(frames) if t in f) for t in texts]
                        self.assertEqual(at, sorted(at), "a sender's messages in its order")
                        for t in texts:
                            self.assertEqual(sum(f.count(t) for f in frames), 1, t)
                    self.assertEqual(sum(wake.LINE_HEAD in f for f in frames), 1, "the line on the first frame alone")
                    self.assertIn(wake.LINE_HEAD, frames[0])
                    self.assertEqual(self.owed(sid), [])

    def test_several_senders_to_a_held_thread_are_all_held_marked_and_pushed_once_when_it_runs(self):
        senders = [self.live_sender("sender-%d" % i) for i in range(5)]
        tid, sid = self.human_thread("plan")
        for i in range(3):
            for j, s in enumerate(senders):
                code, out = self.say("@%s h-%d-%d" % (sid[:8], j, i), sender=s)
                self.assertEqual(self.shown(out, sid), [line("mode")])
        self.assertEqual(self.resumes(sid), [])
        self.assertEqual(len(self.owed(sid)), 15)
        self.assertEqual(len(self.marked(sid)), 15, "each one marked")
        self.assertEqual(set(self.marked(sid).values()), {tid}, "for its thread")
        received = self.terminal(sid)
        self.tick()
        got = self.received(received)
        self.assertEqual(len(got), 15)
        for j in range(5):
            for i in range(3):
                self.assertEqual(sum(f.count("h-%d-%d" % (j, i)) for f in got), 1)
        self.assertFalse([f for f in got if wake.LINE_HEAD in f], "no line to a terminal's process")
        self.assertEqual(self.owed(sid), [])


# ------------------------------------------------------------ two at once


class Together(Deliveries):
    def test_two_deliverers_waking_one_thread_together_start_one_process_and_both_messages_arrive_once(self):
        other = self.repo("other")
        self.project_of(other)
        for where in ("one project", "two"):
            with self.subTest(where):
                tid, sid = self.human_thread()
                launched = self.launches()
                self.switch("barrier")
                env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
                runs = [(["say", "@%s from say" % sid[:8]], self.root),
                        (["send", sid[:8], "from send"], self.root) if where == "one project"
                        else (["say", "@%s from send" % sid[:8]], other)]
                procs = [subprocess.Popen([sys.executable, "-B", SCRIPT] + argv, cwd=cwd, env=env,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                         for argv, cwd in runs]
                for p in procs:
                    self.addCleanup(lambda p=p: p.poll() is None and p.kill())
                self.assertTrue(wait_for(lambda: self.launches() > launched, timeout=30), "a launch entered")
                time.sleep(0.5)   # the other deliverer, at the delivery lock or the wake's
                os.unlink(os.path.join(self.state, "barrier"))
                for p in procs:
                    out, err = p.communicate(timeout=90)
                    self.assertEqual(p.returncode, 0, out + err)
                self.tick()   # what a deliverer left owed for a moment, the daemon's
                self.tick(self.project_of(other))
                self.assertEqual(self.launches() - launched, 1, "the engine's launch counter: one")
                frames = self.frames(sid)
                for text in ("from say", "from send"):
                    self.assertEqual(sum(f.count(text) for f in frames), 1, text)
                self.assertEqual(sum(wake.LINE_HEAD in f for f in frames), 1)
                self.assertEqual(self.owed(sid), [])

    def test_the_line_opens_the_first_frame_when_another_deliverer_pushes_before_the_wake_returns(self):
        tid, sid = self.human_thread()
        self.switch("no-banner", 3)   # its process starts, and the launch returns 3 s later with nothing printed
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "say", "@%s the waker's" % sid[:8]], cwd=self.root,
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        rec = wait_for(lambda: self.record(sid), timeout=30)
        self.assertIsNotNone(rec, "the woken process is up while its launch has not returned")
        self.assertTrue(wait_for(lambda: sminos.socket_ok(sminos.socket_path_of(rec))))
        # Another project's deliverer, under its own delivery lock: the push a live session gets.
        sminos.forget_caches()
        sminos.control_module().push_live(sminos.peer_for_session(sid), sid,
                                          sminos.compose_frame("elsewhere", "aaaa1111", "the other's"))
        out, err = p.communicate(timeout=90)
        self.assertEqual(p.returncode, 0, out + err)
        frames = self.frames(sid)
        self.assertEqual(len(frames), 2, frames)
        self.assertIn("the other's", frames[0])
        self.assertIn(wake.LINE_HEAD, frames[0].partition("\n\n")[0], "the first frame after the wake has it")
        self.assertIn("the waker's", frames[1])
        self.assertNotIn(wake.LINE_HEAD, frames[1], "and no other")

    def test_a_line_met_for_a_terminals_process_is_not_sent(self):
        tid, sid = self.human_thread()
        threads.wake_line(tid, sid, wake.line_note(True, FLAGS, {"mode": "auto", "model": "claude-term"}, []))
        received = self.terminal(sid)
        code, out = self.say("@%s at the terminal" % sid[:8])
        self.assertEqual(self.shown(out, sid), ["sent"])
        [frame] = self.received(received)
        self.assertNotIn(wake.LINE_HEAD, frame)
        self.assertNotIn("line", self.waking(tid, sid))
        self.assertEqual(self.resumes(sid), [])


# ------------------------------------------------------------ held, for each reason


class Bound(Deliveries):
    """The push after a wake goes to the session the thread holds at the moment of the handoff: the wake's hold is
    kept through it, and an entry open by then holds the event (the frontier review's scalpel-3#2)."""

    def test_the_push_after_a_wake_is_made_under_the_wake_lock_and_a_transition_waits_for_it(self):
        for kind in ("human", "seat"):
            with self.subTest(kind=kind):
                if kind == "human":
                    tid, sid = self.human_thread()
                    target = "@%s" % sid[:8]
                else:
                    s = self.seat("w%d" % len(sminos.seats()))
                    tid, sid, target = s["seat_id"], s["current"], "@" + s["alias"]
                control, seen = sminos.control_module(), []
                real = control.push_live

                def probed(peer, session, *a, **kw):
                    got = []
                    t = threading.Thread(target=lambda: got.append(sminos.wake_lock(tid, until=time.time() + 0.3)))
                    t.start()
                    t.join(5)
                    seen.append((sminos.wake_held(tid) is not None, got[0][0] is None))
                    return real(peer, session, *a, **kw)
                with mock.patch.object(control, "push_live", probed):
                    code, out = self.say("%s under the lock" % target)
                self.assertEqual(self.shown(out, sid), ["sent (woken)"])
                self.assertEqual(seen, [(True, True)], "held by the push, so no transition opens meanwhile")
                self.assertFalse(sminos.wake_held(tid), "let go after the push")
                self.assertTrue(sminos.wake_lock(tid, until=time.time() + 1)[0].release() is None)

    def test_an_entry_open_by_the_time_of_the_push_holds_the_event(self):
        for how in ("say", "send"):
            with self.subTest(how=how):
                tid, sid = self.human_thread()
                real = sminos.wake

                def then_opened(record, session, *a, **kw):
                    got = real(record, session, *a, **kw)
                    # An entry an older copy opened (it takes no wake lock) after the wake made the session live.
                    self.edit(tid, pending={"id": "e1", "op": "retire", "events": []})
                    return got
                with mock.patch.object(sminos, "wake", then_opened):
                    if how == "say":
                        code, out = self.say("@%s too soon" % sid[:8])
                    else:
                        code, out = self.send(sid[:8], "too soon")
                self.assertEqual(code, 0, out)
                self.assertEqual(sum(f.count("too soon") for f in self.frames(sid)), 0, "nothing pushed")
                self.assertTrue(self.owes(sid, "too soon"), "owed")
                self.edit(tid, pending=None)
                self.tick()
                self.assertTrue(wait_for(lambda: sum(f.count("too soon") for f in self.frames(sid)) == 1),
                                "pushed once the entry is gone")


class Unpushed(Deliveries):
    def test_a_woken_process_whose_inbox_went_before_the_push_keeps_the_event_owed(self):
        # The first addressed event, not marked yet: its inbox gone between the wake's look and the push's
        # (frontier review, scalpel-3#1). Owed and held `starting`, never settled `recorded`; the next pass
        # wakes it again and pushes it once.
        for how in ("say", "send"):
            with self.subTest(how=how):
                tid, sid = self.human_thread()
                real = sminos.wake_member

                def then_gone(project, member, session, e, *a, **kw):
                    got = real(project, member, session, e, *a, **kw)
                    if got[0] == "woken":
                        self.claude("stop", session[:8])
                        self.assertTrue(wait_for(lambda: self.record(session) is None))
                        sminos.forget_caches()
                    return got
                with mock.patch.object(sminos, "wake_member", then_gone):
                    code, out = self.say("@%s first one" % sid[:8]) if how == "say" else \
                        self.send(sid[:8], "first one")
                self.assertEqual(code, 0, out)
                self.assertEqual(sum(f.count("first one") for f in self.frames(sid)), 0, "nothing pushed")
                self.assertTrue(self.owes(sid, "first one"), "owed")
                self.assertIn(tid, set(self.marked(sid).values()), "held for its thread")
                self.tick()
                self.assertTrue(wait_for(lambda: sum(f.count("first one") for f in self.frames(sid)) == 1))
                self.assertFalse(self.owes(sid, "first one"))


class Held(Deliveries):
    def held_says(self, sid, why, tid=None, text="while away"):
        code, out = self.say("@%s %s" % (sid[:8], text))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.shown(out, sid), [line(why)])
        self.assertEqual(self.resumes(sid), [], "nothing launched")
        self.assertTrue(self.owes(sid, text), "owed")
        marks = self.marked(sid)
        self.assertTrue(marks, "its hold marked")
        if tid:
            self.assertEqual(set(marks.values()), {tid})
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
        self.assertEqual(threads.hold_of(sid), why)
        return out

    def test_each_reason_holds_a_thread_its_human_opened_with_its_mark(self):
        def config(tid, sid):
            other = os.path.join(self.home, "other-config")
            p = mock.patch.object(sminos, "foreign_config", lambda s: other if s == sid else "")
            p.start()
            self.addCleanup(p.stop)

        def protected(tid, sid):
            self.edit(tid, launch={"cwd": self.vault(), "at": sminos.now()})
        cases = {
            "mode": (lambda tid, sid: None, "plan"),
            "cwd": (lambda tid, sid: self.edit(tid, launch={"cwd": os.path.join(self.home, "gone"),
                                                             "at": sminos.now()}), "auto"),
            "transcript": (lambda tid, sid: os.unlink(sminos.transcript_now(sid)), "auto"),
            "config": (config, "auto"),
            "protected": (protected, "auto"),
        }
        for why, (make, mode) in cases.items():
            with self.subTest(why=why):
                tid, sid = self.human_thread(mode)
                make(tid, sid)
                sminos.forget_caches()
                self.held_says(sid, why, tid)

    def test_a_spawned_thread_is_held_for_its_reasons_where_it_was_recorded(self):
        def gone(s):
            shutil.rmtree(os.path.join(self.root, "sub-cwd"))
        for why, make in (("cwd", gone), ("transcript", lambda s: os.unlink(sminos.transcript_now(s["current"])))):
            with self.subTest(why=why):
                s = self.seat_in("w-" + why, os.path.join(self.root, "sub-" + why))
                make(s)
                sminos.forget_caches()
                launched = self.launches()
                code, out = self.say("@w-%s while away" % why)
                self.assertIn("w-%s: %s" % (why, line(why)), out)
                self.assertEqual(self.launches(), launched)
                self.assertEqual(self.owed(s["current"]), ["while away"])
                self.assertEqual(set(self.marked(s["current"]).values()), {s["seat_id"]})
        s = self.seat("w-config")
        other = os.path.join(self.home, "other-config")
        with mock.patch.object(sminos, "foreign_config", lambda x: other if x == s["current"] else ""):
            code, out = self.say("@w-config while away")
        self.assertIn("w-config: %s" % line("config"), out)
        self.assertEqual(self.owed(s["current"]), ["while away"])

    def test_a_spawned_thread_in_a_protected_folder_is_woken_and_one_its_human_opened_there_is_held(self):
        where = self.vault()
        s = self.seat_in("w", where)
        tid, sid = self.human_thread()
        self.edit(tid, launch={"cwd": where, "at": sminos.now()})
        self.held_says(sid, "protected", tid)
        code, out = self.say("@w for the seat")
        self.assertIn("w: sent (woken)", out)
        self.assertEqual(sum("for the seat" in f for f in self.frames(s["current"])), 1)

    def test_what_was_held_is_pushed_once_when_a_process_of_the_thread_takes_it(self):
        tid, sid = self.human_thread("plan")
        self.held_says(sid, "mode", tid, "first")
        self.held_says(sid, "mode", tid, "second")
        self.tick()
        self.tick()
        received = self.terminal(sid)
        self.tick()
        got = self.received(received)
        self.assertEqual([f.count(t) for f, t in zip(got, ("first", "second"))], [1, 1])
        self.assertEqual(len(got), 2)
        self.assertEqual(self.owed(sid), [])
        self.assertEqual(self.resumes(sid), [])

    def test_a_ceiling_that_lowers_a_first_wakes_mode_holds_it_until_it_is_raised(self):
        self.ceiling("default")
        tid, sid = self.human_thread("auto")
        code, out = self.say("@%s under the ceiling" % sid[:8])
        [said] = self.shown(out, sid)
        self.assertTrue(said.startswith(HEAD), said)
        self.assertIn("this machine's ceiling (default) would start it in a mode that asks for approval; the ceiling "
                      "is its owner's setting (sminos daemon policy shows it)", said, "the ceiling named as the cause")
        self.assertEqual(threads.hold_of(sid), "mode")
        self.tick()
        self.assertEqual(self.resumes(sid), [])
        self.ceiling("auto")
        self.tick()
        self.assertEqual(self.resumes(sid), [FLAGS], "the next pass wakes it, nothing new sent")
        self.assertEqual(sum("under the ceiling" in f for f in self.frames(sid)), 1)

    def test_read_only_refuses_an_outside_event_and_a_local_one_wakes(self):
        tid, sid = self.human_thread()
        policy = sminos.sibling_module("sminos_policy")
        with mock.patch.object(policy, "read_only", return_value=True):
            e = sminos.log_append(self.p, "othermachine/human", "human", **{
                "from": "human", "to": [{"session": sid, "alias": "x"}], "text": "from elsewhere"})
            got = sminos.deliver_next(self.p, self.member(sid))
            self.assertEqual([o for x, o in got["outcomes"] if x["seq"] == e["seq"]], ["refused-read-only"])
            self.assertEqual(self.resumes(sid), [], "refused, not held, and nothing woken for it")
            code, out = self.say("@%s from here" % sid[:8])
        self.assertEqual(self.shown(out, sid), ["sent (woken)"])
        self.assertEqual(self.owed(sid), [])

    def test_a_process_with_no_inbox_yet_holds_and_is_pushed_with_no_file_written_between(self):
        tid, sid = self.human_thread()
        _, proc = self.session(sid=sid, kind="bg", name="term-a")
        sock = os.path.join(self.home, "late.sock")
        self.peer_set(proc, messagingSocketPath=sock)   # named, not served yet
        code, out = self.say("@%s for when it answers" % sid[:8])
        self.assertEqual(self.shown(out, sid), [STARTING])
        self.assertTrue(self.marked(sid), "held with its mark")
        self.tick()
        self.assertEqual(self.owed(sid), ["for when it answers"])
        received = sock + ".received"
        open(received, "a").close()
        server = subprocess.Popen([sys.executable, "-B", INBOX, sock, received])
        self.addCleanup(lambda: (server.kill(), server.wait()))
        self.assertTrue(wait_for(lambda: sminos.socket_ok(sock)))
        self.tick()
        self.assertEqual([f.count("for when it answers") for f in self.received(received)], [1])
        self.assertEqual(self.owed(sid), [])
        self.assertEqual(self.resumes(sid), [], "a process held it: nothing launched")

    def test_a_live_inbox_is_pushed_to_while_a_reason_reads_true_and_while_a_failed_wake_waits(self):
        tid, sid = self.human_thread("plan")
        received = self.terminal(sid)
        code, out = self.say("@%s despite the mode" % sid[:8])
        self.assertEqual(self.shown(out, sid), ["sent"])
        tid2, sid2 = self.human_thread()
        self.edit(tid2, waking={"session": sid2, "failed": 3, "at": sminos.now()})
        received2 = self.terminal(sid2, name="term-b")
        code, out = self.say("@%s despite the failure" % sid2[:8])
        self.assertEqual(self.shown(out, sid2), ["sent"])
        self.assertEqual([len(self.received(received)), len(self.received(received2))], [1, 1])
        self.assertEqual(self.resumes(), [])


# ------------------------------------------------------------ a wake that failed, and its schedule


class Schedule(Deliveries):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": "0.5", "SMINOS_WAKE_RETRY_MAX": "4"})
        p.start()
        self.addCleanup(p.stop)

    def test_a_failed_wake_is_held_and_tried_again_on_the_schedule(self):
        tid, sid = self.human_thread()
        self.switch("fail-job")
        code, out = self.say("@%s first" % sid[:8])
        self.assertEqual(self.shown(out, sid), [line("failed")])
        self.assertEqual(self.launches(), 1)
        self.assertEqual(threads.hold_of(sid), "failed")
        self.tick()
        self.assertEqual(self.launches(), 1, "the daemon waits for the schedule")
        for text in ("second", "third"):
            code, out = self.say("@%s %s" % (sid[:8], text))
            self.assertEqual(self.shown(out, sid), [line("failed")], "a sender's own call tries at once")
        self.assertEqual(self.launches(), 3)
        self.assertEqual(self.waking(tid, sid)["failed"], 3)
        self.tick()
        self.assertEqual(self.launches(), 3, "its replay of the same events waits")
        self.assertEqual(self.owed(sid), ["first", "second", "third"])
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")
        os.unlink(os.path.join(self.state, "fail-job"))
        self.assertTrue(wait_for(lambda: not threads.hold_of(sid) and not sminos.forget_caches(), timeout=10))
        self.tick()
        self.assertEqual(self.launches(), 4, "due: the daemon wakes it")
        frames = self.frames(sid)
        self.assertEqual([sum(f.count(t) for f in frames) for t in ("first", "second", "third")], [1, 1, 1])
        self.assertEqual(self.owed(sid), [])
        self.assertNotIn("failed", self.waking(tid, sid), "cleared by the wake that made it live")

    def test_the_schedule_from_the_first_failure_to_the_hours_cap(self):
        tid, sid = self.human_thread()
        with mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": "60", "SMINOS_WAKE_RETRY_MAX": "3600"}):
            for failed, waits in ((1, 60), (2, 120), (3, 240), (6, 1920), (7, 3600), (30, 3600)):
                with self.subTest(failed=failed):
                    at = time.time() - waits

                    def stamp(t):
                        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
                    self.edit(tid, waking={"session": sid, "failed": failed, "at": stamp(at + 5)})
                    self.assertEqual(threads.hold_of(sid), "failed", "not due yet")
                    self.edit(tid, waking={"session": sid, "failed": failed, "at": stamp(at - 5)})
                    self.assertEqual(threads.hold_of(sid), "", "due")

    def test_the_fifth_failure_in_a_row_is_said_once_in_daemon_log(self):
        tid, sid = self.human_thread()
        self.switch("fail-job")
        for i in range(6):
            self.say("@%s try %d" % (sid[:8], i))
        said = [ln for ln in self.daemon_log().splitlines() if "failed 5 times in a row" in ln]
        self.assertEqual(len(said), 1, self.daemon_log())
        self.assertIn(tid, said[0])
        self.assertIn(sid[:8], said[0])


# ------------------------------------------------------------ lane, unknown, ends and refills


class Settles(Deliveries):
    def test_a_session_turned_lane_b_is_not_woken_and_one_whose_record_cannot_be_read_is_held(self):
        tid, sid = self.human_thread()
        m = self.member(sid)
        records.set_controller(sid, "B")
        sminos.forget_caches()
        e = sminos.log_append(self.p, "testhost/human", "human", **{
            "from": "human", "to": [{"session": sid, "alias": "x"}], "text": "to lane b"})
        got = sminos.deliver_next(self.p, m, due=True)
        self.assertEqual([o for x, o in got["outcomes"] if x["seq"] == e["seq"]], ["recorded"])
        self.assertEqual(self.resumes(sid), [])
        tid2, sid2 = self.human_thread()
        with open(records.record_path(sid2), "w") as f:
            f.write("{")
        sminos.forget_caches()
        e2 = sminos.log_append(self.p, "testhost/human", "human", **{
            "from": "human", "to": [{"session": sid2, "alias": "y"}], "text": "to unknown"})
        got = sminos.deliver_next(self.p, self.member(sid2), due=True)
        self.assertEqual([o for x, o in got["outcomes"] if x["seq"] == e2["seq"]], ["held:unknown"])
        self.assertEqual(self.owed(sid2), ["to unknown"], "held, not settled")
        self.assertEqual(self.resumes(sid2), [])

    def test_a_marked_event_of_a_spawned_thread_is_settled_when_it_ends(self):
        s = self.seat_in("w", os.path.join(self.root, "sub"))
        shutil.rmtree(os.path.join(self.root, "sub"))
        sminos.forget_caches()
        self.say("@w held for the seat")
        self.assertEqual(self.owed(s["current"]), ["held for the seat"])
        code, out = self.cli("retire", "w")
        self.assertEqual(code, 0, out)
        self.tick()
        self.assertEqual(self.owed(s["current"]), [], "settled with its end, pushed nowhere")
        self.assertFalse([f for f in self.frames(s["current"]) if "held for the seat" in f])

    def test_a_refill_settles_what_was_held_for_the_session_it_displaces(self):
        s = self.seat()
        old = s["current"]
        os.unlink(sminos.transcript_now(old))
        sminos.forget_caches()
        self.say("@w old news")
        self.assertEqual(self.owed(old), ["old news"])
        self.assertTrue(self.marked(old))
        new, proc = self.session(name="w-new")
        code, out = self.cli("seat", "add", s["group"], "w", "--session", new)
        self.assertEqual(code, 0, out)
        self.end(proc)
        self.assertEqual(self.owed(old), [], "settled in the refill's entry")
        received = self.terminal(old, name="w-old")
        code, out = self.cli("seat", "add", s["group"], "w", "--session", old)
        self.assertEqual(code, 0, out)
        self.tick()
        self.assertFalse([f for f in self.received(received) if "old news" in f], "nothing old pushed")


# ------------------------------------------------------------ what else reads the hold


class Elsewhere(Deliveries):
    def test_derive_forks_no_stopped_session_its_human_opened_even_one_it_would_wake(self):
        tid, sid = self.human_thread()
        self.assertEqual(threads.hold_of(sid), "", "it would be woken")
        self.assertEqual(sminos.derive_refusal(self.p, self.member(sid)), sminos.DERIVE_HELD)

    def test_a_woken_thread_is_not_withheld_as_a_young_background_spawn(self):
        tid, sid = self.human_thread()
        self.say("@%s hello" % sid[:8])
        rec = self.record(sid)
        self.assertEqual(rec["kind"], "bg")
        self.assertFalse(threads.awaits_seat(sid, rec, False), "the current session of a thread")

    def test_one_reach_permit_serves_the_wake_and_the_push_after_it(self):
        tid, sid = self.human_thread()
        au = sminos.audience_module()
        with mock.patch.object(au, "reach_capable", return_value=True):
            e = sminos.log_append(self.p, "othermachine/aaaa1111-0000-4000-8000-000000000001", "say", **{
                "from": "elsewhere", "to": [{"session": sid, "alias": "x"}], "text": "admitted once"})
            got = sminos.deliver_next(self.p, self.member(sid), due=True)
            self.assertTrue(all(o.startswith("held:reach") for x, o in got["outcomes"] if x["seq"] == e["seq"]),
                            got["outcomes"])
            self.assertEqual(self.resumes(sid), [], "no permit: nothing launched")
            self.assertEqual(sminos.deliver_reach(self.p, self.member(sid), e, "deliver"), "woken",
                             "the wake's check kept the permit for the push")
        self.assertEqual(self.resumes(sid), [FLAGS])
        self.assertEqual([f.count("admitted once") for f in self.frames(sid)], [1])
        self.assertEqual(sminos._REACH_PERMITS, set(), "spent")
        self.assertEqual(self.owed(sid), [])

    def test_a_tick_launches_nothing_and_lists_no_job_for_a_thread_nothing_is_owed_to(self):
        tid, sid = self.human_thread()
        before = len(self.calls())
        sminos.forget_caches()
        self.daemon.tick(self.p)
        self.assertEqual(self.calls()[before:], [], "no claude call of any kind")



# ------------------------------------------------------------ a plain send, as a tagged say (review round 1)


class PlainSend(Deliveries):
    """A plain `send` to a spawned thread no process answers for is recorded, then woken or held as a tagged
    `say` is; the verbs and `--wait` are M4's."""

    def test_a_plain_send_to_a_seat_held_for_each_reason_is_recorded_held_and_marked(self):
        other = os.path.join(self.home, "other-config")
        for why in ("transcript", "cwd", "config"):
            with self.subTest(why=why):
                where = os.path.join(self.root, "sub-p-" + why)
                s = self.seat_in("p-" + why, where)
                sid = s["current"]
                if why == "transcript":
                    os.unlink(sminos.transcript_now(sid))
                elif why == "cwd":
                    shutil.rmtree(where)
                sminos.forget_caches()
                launched = self.launches()
                with mock.patch.object(sminos, "foreign_config", lambda x: other if why == "config" and x == sid
                                       else ""):
                    code, out = self.send("p-" + why, "while away")
                self.assertEqual(code, 0, out)
                self.assertIn(line(why), out)
                self.assertEqual(self.launches(), launched, "nothing launched")
                self.assertEqual(self.owed(sid), ["while away"])
                self.assertEqual(set(self.marked(sid).values()), {s["seat_id"]})
                self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")

    def test_a_plain_send_to_a_seat_whose_process_has_no_inbox_yet_is_held_while_it_starts(self):
        s = self.seat()
        sid = s["current"]
        _, proc = self.session(sid=sid, kind="bg", name="w")
        self.peer_set(proc, messagingSocketPath=os.path.join(self.home, "late-w.sock"))   # named, not served
        code, out = self.send("w", "for when it answers")
        self.assertEqual(code, 0, out)
        self.assertIn(STARTING, out)
        self.assertEqual(self.owed(sid), ["for when it answers"])
        self.assertTrue(self.marked(sid), "held with its mark")
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set(), "no attempt counted")


# ------------------------------------------------------------ what decides a hold, and for which thread (review round 1)


class Decided(Deliveries):
    def addressed(self, sid, text, writer="testhost/human"):
        return sminos.log_append(self.p, writer, "human", **{
            "from": "human", "to": [{"session": sid, "alias": "x"}], "text": text})

    def test_a_thread_whose_own_record_cannot_be_read_holds_its_message_marked_for_it(self):
        tid, sid = self.human_thread()
        member = self.member(sid)
        with open(self.record_file(tid), "w") as f:
            f.write("{")
        sminos.forget_caches()
        e = self.addressed(sid, "to an unreadable thread")
        for _ in range(2):
            got = sminos.deliver_next(self.p, member, due=True)
            self.assertEqual([o for x, o in got["outcomes"] if x["seq"] == e["seq"]], ["held:unknown"])
        self.assertEqual(self.owed(sid), ["to an unreadable thread"], "held, never settled")
        self.assertEqual(set(self.marked(sid).values()), {tid}, "marked for the thread its member is stamped with")
        self.assertEqual(self.resumes(sid), [])

    def test_the_mark_names_the_thread_the_hold_was_decided_for_whatever_the_stamp_reads_after(self):
        def held_with(make, due):
            tid, sid = self.human_thread(make)
            member = self.member(sid)
            first, second = self.addressed(sid, "one"), self.addressed(sid, "two")
            real = threads.stamp
            with mock.patch.object(threads, "stamp", lambda x: "another-thread" if x == sid else real(x)):
                got = sminos.deliver_next(self.p, member, due=due)
            self.assertTrue(all(o.startswith("held:") for _, o in got["outcomes"]), got["outcomes"])
            self.assertEqual(self.marked(sid), {("testhost/human", first["seq"]): tid,
                                                ("testhost/human", second["seq"]): tid})
        with self.subTest("held before a wake"):
            held_with("plan", False)
        with self.subTest("held by a wake"):
            self.switch("fail-job")
            held_with("auto", True)

    def test_a_late_verdict_for_an_event_for_the_live_alone_settles_it_recorded_and_marks_nothing(self):
        tid, sid = self.human_thread("plan")
        writer = "othermachine/aaaa1111-0000-4000-8000-000000000002"
        for name, call in (("reach", lambda e: sminos.deliver_reach(self.p, self.member(sid), e, "deliver")),
                           ("words", lambda e: sminos.deliver_verdict(self.p, self.member(sid), e, "peer"))):
            with self.subTest(name):
                e = sminos.log_append(self.p, writer, "say", **{
                    "from": "elsewhere", "to": [{"session": sid, "alias": "x"}], "wake": True, "scope": "all",
                    "text": "standup " + name})
                self.assertEqual(call(e), "recorded")
                self.assertEqual(self.marked(sid), {}, "no debt for the live alone")
                self.assertEqual(self.owed(sid), [])


    def test_a_hold_for_an_unreadable_record_survives_a_words_timeout_and_is_not_asked_about(self):
        tid, sid = self.human_thread()
        member = self.member(sid)
        with open(self.record_file(tid), "w") as f:
            f.write("{")
        sminos.forget_caches()
        e = self.addressed(sid, "while unreadable")
        got = sminos.deliver_next(self.p, member, due=True)
        self.assertEqual([o for x, o in got["outcomes"] if x["seq"] == e["seq"]], ["held:unknown"])
        for _ in range(sminos.DELIVERY_ATTEMPTS + 1):
            self.assertEqual(sminos.words_unanswered(self.p, member, e, "no verdict"), 0, "no attempt counted")
        self.assertEqual(self.owed(sid), ["while unreadable"], "still owed")
        self.assertEqual(set(self.attempts(sid).values()) - {0}, set())
        with mock.patch.object(sminos, "words_route", lambda project, x: "ask"):
            self.assertEqual(sminos.words_due(self.p, [member]), {}, "the words pass asks nothing while it holds")
        with mock.patch.object(sminos.audience_module(), "reach_capable", return_value=True):
            self.assertEqual(sminos.reach_due(self.p, [member]), {}, "nor the reach pass")

    def test_a_mark_for_an_unreadable_record_is_never_pushed_and_settles_once_another_thread_holds_the_session(self):
        tid, sid = self.human_thread("plan")
        code, out = self.say("@%s old debt" % sid[:8])
        self.assertEqual(self.marked(sid), {(w, q): tid for (w, q) in self.marked(sid)}, "held for its thread")
        with open(self.record_file(tid), "w") as f:
            f.write("{")
        received = self.terminal(sid)   # a process holds the session again: a live inbox
        self.tick()
        self.assertEqual(self.received(received), [], "an unknown binding pushes nothing")
        self.assertEqual(self.owed(sid), ["old debt"], "and stays owed")
        new = threads.ensure(sid)   # the same session under a new record: another thread positively holds it
        sminos.forget_caches()
        self.assertNotEqual(threads.stamp(sid), tid)
        self.tick()
        self.assertEqual(self.received(received), [], "the old thread's debt goes to no process of another")
        self.assertEqual(self.owed(sid), [], "settled as stale")
        self.assertIsNotNone(new)

# ------------------------------------------------------------ what the hold reads (review round 1)


class Reads(Deliveries):
    def test_a_mode_beyond_the_ticks_bound_found_by_a_wake_holds_the_next_passes_with_no_job_list(self):
        tid, sid = self.human_thread("plan")
        self.transcript(sid, rows(*[{"type": "system", "content": "x" * 1000}] * (wake.TAIL_BOUND // 1000 + 64)))
        self.assertEqual(threads.hold_of(sid), "", "the tick's bounded reading finds no mode")
        code, out = self.say("@%s far back" % sid[:8])
        self.assertEqual(self.shown(out, sid), [line("mode")], "the wake's whole reading finds it")
        sminos.forget_caches()
        self.assertEqual(threads.hold_of(sid), "mode", "and the hold reads it from then on")
        before = len(self.calls())
        self.tick()
        self.tick()
        self.assertEqual([c["argv"] for c in self.calls()[before:]], [], "no job list, no launch")
        self.assertEqual(self.owed(sid), ["far back"])

    def test_the_hold_looks_into_no_protected_folder_the_wake_does_not(self):
        where = self.vault()
        tid, sid = self.human_thread()
        self.edit(tid, launch={"cwd": where, "at": sminos.now()})
        s = self.seat_in("v", os.path.join(where, "seat"))
        looked = []
        real = wake._stat
        with mock.patch.object(wake, "_stat", lambda path: looked.append(path) or real(path)):
            self.assertEqual(threads.hold_of(sid), "protected")
            self.assertEqual(threads.hold_of(sid), "protected", "kept")
            self.assertEqual(threads.hold_of(s["current"]), "")
            wake.hold_key(threads.get(tid), sid)
            wake.hold_key(threads.get(s["seat_id"]), s["current"])
        self.assertEqual([p for p in looked if p and os.path.realpath(p).startswith(where)], [])

    def test_the_schedule_has_one_deadline(self):
        tid, sid = self.human_thread()
        with mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": "60", "SMINOS_WAKE_RETRY_MAX": "3600"}):
            at = time.time() - 100
            self.edit(tid, waking={"session": sid, "failed": 2, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                                     time.gmtime(at))})
            t = threads.get(tid)
            due = wake.due_at(t, sid)
            self.assertAlmostEqual(due, int(at) + 120, delta=1)
            self.assertFalse(wake.wake_due(t, sid, now=due - 1))
            self.assertTrue(wake.wake_due(t, sid, now=due))
            self.assertEqual(wake.deadline(t, sid), due)

if __name__ == "__main__":
    unittest.main()
