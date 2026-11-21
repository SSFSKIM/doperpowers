#!/usr/bin/env python3
"""Several senders against the wake (T2's M5: docs/doperpowers/plans/
2026-11-20-sminos-threads-t2.md, the milestone's decision on the
several-senders suite; Interfaces §3, §4 and §7), against the test engine.
What the delivery and transition suites hold fixed is varied here: one, two
and five senders, one and three messages from one sender, and the three ways
a message is sent (`say` with a tag, `send`, and a message from another
project: a second project's sender on this machine, and a second registry's
writer over a git mirror, whose log reaches this machine by the sync alone),
each against:

- a thread that is woken, its human's or a seat: one launch, every message in
  the inbox once and in its sender's order, the line once after the last
  frame of the first text;
- a thread held for each reason, `failed` too: every message held with its
  mark for its thread and no attempt counted, its sender told why; pushed
  once when a process of the thread takes it;
- a wake that fails once and then succeeds, by a sender's own call and by
  the daemon's retry on §4's schedule;
- a hand-off, a `/clear`, a retire and a refill between the send and the
  wake: settled with the thread's end or change and pushed to no process, or
  woken and pushed to the session the messages were for, never the one the
  `/clear` started;
- the accepted job's grace: a launch whose process is not up by W7's bound
  holds every sender `starting` and launches nothing twice, and is pushed
  once when its process comes up; one that never comes up is counted failed
  after its grace and woken again, its first worker stopped;
- the line's binding to its launch with senders racing one wake: once, on
  the first text pushed to the process the launch started; never to a
  terminal's process or another job's, nor after an earlier wake's;
- what is not promised, as it is: a deliverer killed between an inbox's
  admission of a frame and its settlement leaves the event owed and the next
  pass pushes it again; one killed after the wake and before the push leaves
  no second copy (the wake adds no window).

Every teardown fails on a launch that carried a message (test_wake.Engine).
Hermetic: test_wake.Engine (HOME, SMINOS_HOME and the engine's state
temporary, the engine first on PATH and checked to be).
Run: python3 -B sminos/tests/test_wake_senders.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import collections
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import Killed  # noqa: E402
from test_wake import line_of, wait_for  # noqa: E402
from test_wake_delivery import STARTING, Deliveries, line  # noqa: E402
from test_wake_seat import INBOX, SCRIPT, sminos, threads, wake  # noqa: E402
import wake_engine  # noqa: E402

PATHS = ("say", "send", "project")
COMBOS = ((1, 1), (1, 3), (2, 1), (2, 3), (5, 1), (5, 3))   # (senders, messages from each)
WOKEN_FAR = "recorded (on testhost): the session is stopped, and its machine wakes it with this"

Msg = collections.namedtuple("Msg", "token path sender told")
Target = collections.namedtuple("Target", "kind tid sid alias")


def told(out):
    """What a sender's call printed for its one recipient: `sent`, `sent (woken)`, or the line after the
    recipient's name (a hold's, §5's)."""
    said = [ln for ln in out.splitlines() if ln and not ln.startswith(("copy ", "sminos:"))
            and not (ln.startswith("recorded ") and " in " in ln and ": " not in ln)]
    last = said[-1] if said else ""
    if last.startswith("sent to "):
        return "sent (woken)" if last.endswith("(woken)") else "sent"
    return last.split(": ", 1)[1] if ": " in last else last


class Senders(Deliveries):
    def setUp(self):
        super().setUp()
        self.other = self.repo("other")
        self.q = self.project_of(self.other)
        self.pools = {"here": [], "there": []}
        self.waves = 0

    # -- who sends, and how

    def sender(self, path, j):
        where = "there" if path == "project" else "here"
        pool = self.pools[where]
        while len(pool) <= j:
            if where == "here":
                pool.append(self.live_sender("sender-%d" % len(pool)))
            else:
                pool.append(self.live_sender("far-%d" % len(pool), root=self.other, p=self.q))
        return pool[j]

    def post(self, target, path, text, sender):
        short = target.sid[:8]
        if path == "say":
            return self.say("@%s %s" % (target.alias if target.kind == "seat" else short, text), sender=sender)
        if path == "send":
            return self.send(target.alias if target.kind == "seat" else short, text, sender=sender)
        return self.say("@%s %s" % (short, text), sender=sender, cwd=self.other)

    def wave(self, target, paths, n, k, first=0):
        """k messages from each of n senders, sender j by paths[j % len(paths)], in rounds; each Msg with what its
        sender was told. Senders first..first+n-1 of each path's pool."""
        self.waves += 1
        out = []
        for i in range(k):
            for j in range(first, first + n):
                path = paths[j % len(paths)]
                s = self.sender(path, j)
                token = "m-%d-%d-%d." % (self.waves, j, i)
                code, said = self.post(target, path, token, s)
                self.assertEqual(code, 0, said)
                out.append(Msg(token, path, s, told(said)))
        return out

    # -- what the thread is

    def human(self, mode="auto"):
        tid, sid = self.human_thread(mode)
        return Target("human", tid, sid, threads.get(tid)["alias"])

    def seated(self, alias):
        s = self.seat(alias)
        return Target("seat", s["seat_id"], s["current"], alias)

    def holder(self, sid, kind, name, root=None, **fields):
        """A process holding the session that no wake of sminos started (a terminal's, or a background job of
        another's), with an inbox of its own: (its process, the file its inbox appends every frame to)."""
        _, proc = self.session(sid=sid, kind=kind, name=name, root=root)
        sock = os.path.join(self.home, "%x.sock" % proc.pid)   # an AF_UNIX path is short
        received = sock + ".received"
        open(received, "a").close()
        server = subprocess.Popen([sys.executable, "-B", INBOX, sock, received])
        self.addCleanup(lambda: (server.kill(), server.wait()))
        self.assertTrue(wait_for(lambda: sminos.socket_ok(sock)))
        self.peer_set(proc, messagingSocketPath=sock, nameSource="user", **fields)
        return proc, received

    # -- what each message became

    def event_of(self, token, p=None):
        sminos.forget_caches()
        d = sminos.project_path(p or self.p, "log")
        for name in sorted(os.listdir(d)):
            if name.endswith(".jsonl"):
                with open(os.path.join(d, name)) as f:
                    for ln in f:
                        e = json.loads(ln) if ln.strip() else {}
                        if str(e.get("text") or "").endswith(token):
                            return e["writer"], e["seq"]
        self.fail("no event for %s" % token)

    def assert_once(self, frames, msgs):
        for m in msgs:
            self.assertEqual(sum(f.count(m.token) for f in frames), 1, m)

    def assert_in_order(self, frames, msgs):
        by = collections.defaultdict(list)
        for m in msgs:
            by[m.sender].append(next(x for x, f in enumerate(frames) if m.token in f))
        for sender, at in by.items():
            self.assertEqual(at, sorted(at), "a sender's messages in its order")

    def assert_line_once_first(self, frames):
        """The line in exactly one of `frames`, the first, as its last paragraph (after its last frame)."""
        self.assertEqual(sum(f.count(wake.LINE_HEAD) for f in frames), 1, frames)
        placed = line_of(frames[0])
        self.assertIsNotNone(placed, "the line the last paragraph of the first text")
        self.assertTrue(placed[1].startswith(wake.LINE_HEAD))

    def assert_held(self, sid, tid, msgs, why=None, p=None):
        marks, owed = self.marked(sid, p), self.owed(sid, p)
        for m in msgs:
            if why is not None:
                self.assertEqual(m.told, line(why), m)
            self.assertEqual(marks.get(self.event_of(m.token, p)), tid, "held with its mark for its thread: %s"
                             % (m,))
            self.assertEqual(sum(t.endswith(m.token) for t in owed), 1, "owed: %s" % (m,))
        self.assertEqual(set(self.attempts(sid, p).values()) - {0}, set(), "no attempt counted")

    def helpers_alive(self, sid):
        """The engine's worker processes for the session that still run."""
        alive = []
        d = os.path.join(self.state, "helpers")
        for name in os.listdir(d) if os.path.isdir(d) else []:
            with open(os.path.join(d, name)) as f:
                spec = wake_engine.read_json(f.read().strip()) or {}
            if spec.get("sid") == sid and wake_engine.pid_alive(int(name)):
                alive.append(int(name))
        return alive

    def retry_soon(self, retry="0.2", cap="0.5"):
        p = mock.patch.dict(os.environ, {"SMINOS_WAKE_RETRY": retry, "SMINOS_WAKE_RETRY_MAX": cap})
        p.start()
        self.addCleanup(p.stop)

    def held_by_failure(self, target, paths=PATHS, n=5, k=1):
        """Messages held by wakes that fail (each sender's own call tries once), then the engine mended: the
        messages, every one held `failed` with its mark."""
        self.switch("fail-job")
        msgs = self.wave(target, paths, n, k)
        msgs += self.wave(target, paths[:1], 1, 2)   # one sender's three
        os.unlink(os.path.join(self.state, "fail-job"))
        self.assert_held(target.sid, target.tid, msgs, "failed")
        return msgs


# ------------------------------------------------------------ woken


class Woken(Senders):
    def test_each_way_of_sending_and_several_senders_wake_it_once_and_arrive_once_in_order_the_line_once(self):
        # A tagged say from this project, 1/2/5 x 1/3, is test_wake_delivery.Senders's; the rest of the matrix here.
        rows_ = [("human", ("send",)), ("human", ("project",)), ("human", PATHS),
                 ("seat", ("say",)), ("seat", ("send",)), ("seat", PATHS)]
        for kind, paths in rows_:
            for n, k in COMBOS:
                with self.subTest(kind=kind, paths=paths, senders=n, messages=k):
                    target = self.human() if kind == "human" else self.seated("w%d" % self.waves)
                    before, launched = len(self.frames(target.sid)), self.launches()
                    msgs = self.wave(target, paths, n, k)
                    self.assertEqual(self.launches() - launched, 1, "one launch")
                    self.assertEqual(len(self.resumes(target.sid)), 1, "one wake")
                    self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) - before == n * k))
                    frames = self.frames(target.sid)[before:]
                    self.assertEqual(len(frames), n * k, "one frame a message")
                    self.assert_once(frames, msgs)
                    self.assert_in_order(frames, msgs)
                    self.assert_line_once_first(frames)
                    self.assertEqual([m.told for m in msgs], ["sent (woken)"] + ["sent"] * (n * k - 1))
                    self.assertEqual(self.owed(target.sid), [])


# ------------------------------------------------------------ held


class Held(Senders):
    def reasons(self):
        def config(target):
            other = os.path.join(self.home, "other-config")
            p = mock.patch.object(sminos, "foreign_config", lambda s: other if s == target.sid else "")
            p.start()
            self.addCleanup(p.stop)
        return {
            "mode": ("plan", lambda t: None),
            "cwd": ("auto", lambda t: self.edit(t.tid, launch={"cwd": os.path.join(self.home, "gone"),
                                                               "at": sminos.now()})),
            "transcript": ("auto", lambda t: os.unlink(sminos.transcript_now(t.sid))),
            "config": ("auto", config),
            "protected": ("auto", lambda t: self.edit(t.tid, launch={"cwd": self.vault(), "at": sminos.now()})),
            "failed": ("auto", lambda t: self.switch("fail-job")),
        }

    def test_each_reason_holds_every_senders_messages_by_each_way_marked_and_pushes_them_once_to_its_process(self):
        for r, (why, (mode, make)) in enumerate(self.reasons().items()):
            for x, path in enumerate(PATHS):
                n, k = COMBOS[(r + 2 * x) % len(COMBOS)]
                with self.subTest(why=why, path=path, senders=n, messages=k):
                    target = self.human(mode)
                    make(target)
                    sminos.forget_caches()
                    launched = self.launches()
                    msgs = self.wave(target, (path,), n, k)
                    self.assert_held(target.sid, target.tid, msgs, why)
                    self.assertEqual(self.launches() - launched, n * k if why == "failed" else 0,
                                     "a failed wake tried at each sender's own call, nothing launched otherwise")
                    if why == "failed":
                        os.unlink(os.path.join(self.state, "fail-job"))
                        self.assertEqual(self.waking(target.tid, target.sid)["failed"], n * k)
                        self.assertNotIn("line", self.waking(target.tid, target.sid), "each failed line removed")
                    _, received = self.holder(target.sid, "interactive", target.alias)
                    self.tick()
                    got = self.received(received)
                    self.assertEqual(len(got), n * k)
                    self.assert_once(got, msgs)
                    self.assert_in_order(got, msgs)
                    self.assertFalse([f for f in got if wake.LINE_HEAD in f], "no line to a terminal's process")
                    self.assertEqual(self.owed(target.sid), [])
                    self.assertEqual(self.inputs(target.sid), [], "nothing to any process a wake started")

    def test_a_seat_held_for_its_reasons_holds_every_way_of_sending_and_its_process_takes_them_once(self):
        for why in ("transcript", "config", "failed"):
            with self.subTest(why=why):
                target = self.seated("h-" + why)
                if why == "transcript":
                    os.unlink(sminos.transcript_now(target.sid))
                elif why == "config":
                    other = os.path.join(self.home, "other-config")
                    p = mock.patch.object(sminos, "foreign_config", lambda s, sid=target.sid: other if s == sid
                                          else "")
                    p.start()
                    self.addCleanup(p.stop)
                else:
                    self.switch("fail-job")
                sminos.forget_caches()
                launched = self.launches()
                msgs = self.wave(target, PATHS, 5, 1) + self.wave(target, ("say",), 1, 2)
                self.assert_held(target.sid, target.tid, msgs, why)
                self.assertEqual(self.launches() - launched, len(msgs) if why == "failed" else 0)
                if why == "failed":
                    os.unlink(os.path.join(self.state, "fail-job"))
                _, received = self.holder(target.sid, "bg", target.alias)
                self.tick()
                got = self.received(received)
                self.assert_once(got, msgs)
                self.assert_in_order(got, msgs)
                self.assertEqual(self.owed(target.sid), [])


# ------------------------------------------------------------ a wake that fails once


class Retry(Senders):
    def test_a_wake_that_fails_once_is_woken_by_the_next_senders_own_call_which_carries_every_message_once(self):
        for n, k in ((1, 3), (2, 1), (5, 3)):
            with self.subTest(senders=n, messages=k):
                target = self.human()
                self.switch("fail-job")
                [first] = self.wave(target, ("say",), 1, 1)
                self.assertEqual(first.told, line("failed"))
                self.assert_held(target.sid, target.tid, [first], "failed")
                os.unlink(os.path.join(self.state, "fail-job"))
                rest = self.wave(target, PATHS, n, k, first=1)
                # A sender's own call tries at once, whatever the schedule. Its wake is made for the held message
                # it meets first, so its own is said `sent`, with no ` (woken)` (§5 asks for it): as it is.
                self.assertEqual({m.told for m in rest}, {"sent"})
                self.assertEqual(len(self.resumes(target.sid)), 2, "the failed launch and the one that woke it")
                frames = self.frames(target.sid)
                self.assert_once(frames, [first] + rest)
                self.assertIn(first.token, frames[0], "the held message first")
                self.assert_line_once_first(frames)
                self.assertEqual(self.owed(target.sid), [])
                self.assertNotIn("failed", self.waking(target.tid, target.sid), "cleared by the wake that made it live")


# ------------------------------------------------------------ a transition between the send and the wake


class Between(Senders):
    def setUp(self):
        super().setUp()
        self.retry_soon()

    def due(self):
        time.sleep(0.6)   # past the schedule's cap: the daemon's next pass may wake it

    def continued(self, old, new):
        """The engine's hand-off of `old` to a background job `new`: the old transcript's `continued-in`, and the
        job's process, with an inbox."""
        with open(sminos.transcript_now(old), "a") as f:
            f.write(json.dumps({"type": "continued-in", "sessionId": old, "continuedInSessionId": new}) + "\n")
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        proc, received = self.holder(new, "bg", "handyjob")
        self.peer_set(proc, nameSource="auto")
        return received

    def test_a_hand_off_settles_what_was_held_and_pushes_it_to_neither_session(self):
        target = self.human()
        msgs = self.held_by_failure(target)
        launched = self.launches()
        job = str(uuidlib.uuid4())
        received = self.continued(target.sid, job)
        self.reconcile()
        self.assertEqual(threads.get(target.tid)["current"], job, "handed off")
        self.due()
        self.tick()
        self.tick()
        self.assertEqual(self.owed(target.sid), [], "settled: the thread went on in the job")
        self.assertFalse([f for f in self.received(received) if any(m.token in f for m in msgs)],
                         "nothing of the session left pushed into the job")
        self.assertEqual(self.inputs(target.sid), [])
        self.assertEqual(self.launches(), launched, "nothing woken")

    def test_a_clear_leaves_the_messages_to_the_session_they_were_for_woken_and_never_to_the_new_one(self):
        target = self.human()
        msgs = self.held_by_failure(target)
        launched = self.launches()
        proc, received = self.holder(target.sid, "interactive", target.alias,   # its human reopens it
                                     startedAt=int((time.time() - 30) * 1000))
        new = str(uuidlib.uuid4())
        os.makedirs(os.path.dirname(sminos.cleared_note_path(proc.pid)), exist_ok=True)
        with open(sminos.cleared_note_path(proc.pid), "w") as f:
            json.dump({"session_id": target.sid, "reason": "clear", "hook_event_name": "SessionEnd"}, f)
        self.peer_set(proc, sessionId=new)   # the /clear: the same process, another session
        self.hook(new, source="clear", env={"CLAUDE_PID": str(proc.pid), "CLAUDE_CODE_SESSION_ID": new})
        self.assertEqual(threads.get(target.tid)["released"]["alias"], target.alias, "the /clear released it")
        self.assertEqual(threads.thread_of(target.sid)["thread"], target.tid, "the session left keeps its thread")
        self.due()
        self.tick()
        self.assertEqual(self.launches() - launched, 1, "the session left, woken once")
        self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == len(msgs)))
        frames = self.frames(target.sid)
        self.assert_once(frames, msgs)
        self.assert_in_order(frames, msgs)
        self.assert_line_once_first(frames)
        self.assertEqual(self.received(received), [], "nothing to the session the /clear started")
        self.assertEqual(self.owed(target.sid), [])

    def test_a_retire_settles_what_was_held_and_pushes_it_nowhere(self):
        target = self.human()
        msgs = self.held_by_failure(target)
        launched = self.launches()
        code, out = self.cli("retire", target.sid[:8])
        self.assertEqual(code, 0, out)
        self.due()
        self.tick()
        self.assertEqual(self.owed(target.sid), [], "settled with its end")
        self.assertEqual(self.inputs(target.sid), [])
        self.assertEqual(self.launches(), launched, "nothing woken")
        self.assertTrue(msgs)

    def test_a_refill_settles_what_was_held_for_the_session_it_displaces_and_pushes_it_to_neither(self):
        target = self.seated("w")
        s = sminos.reload_seat(target.tid)
        msgs = self.held_by_failure(target)
        launched = self.launches()
        new, proc = self.session(name="w-new")
        code, out = self.cli("seat", "add", s["group"], "w", "--session", new)
        self.assertEqual(code, 0, out)
        self.end(proc)
        self.assertEqual(self.owed(target.sid), [], "settled in the refill's entry")
        self.due()
        self.tick()
        self.assertEqual(self.launches(), launched, "nothing woken for the session displaced")
        for sid in (target.sid, new):
            self.assertFalse([f for f in self.frames(sid) if any(m.token in f for m in msgs)], sid)


# ------------------------------------------------------------ the accepted job's grace


class Grace(Senders):
    def test_a_job_not_up_by_the_bound_holds_every_sender_starting_launches_nothing_twice_and_is_pushed_once(self):
        target = self.human()
        self.switch("late-process", 8)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "1", "SMINOS_WAKE_GRACE": "60"}):
            msgs = self.wave(target, PATHS, 5, 1) + self.wave(target, ("say",), 1, 2)
            self.assertEqual(self.launches(), 1, "one launch, the others held behind its accepted job")
            self.assertEqual([m.told for m in msgs], [STARTING] * len(msgs))
            self.assertEqual(self.waking(target.tid, target.sid)["job"]["short"], target.sid[:8])
            self.assert_held(target.sid, target.tid, msgs)
            self.assertIsNotNone(wait_for(lambda: self.record(target.sid), timeout=15), "its process comes up")
            self.tick()
        self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == len(msgs)))
        frames = self.frames(target.sid)
        self.assert_once(frames, msgs)
        self.assert_in_order(frames, msgs)
        self.assert_line_once_first(frames)
        self.assertEqual(self.launches(), 1, "nothing launched twice")
        self.assertEqual(self.owed(target.sid), [])
        self.assertEqual(len(self.helpers_alive(target.sid)), 1)

    def test_one_that_never_comes_up_is_counted_failed_after_its_grace_and_woken_again_its_worker_stopped(self):
        target = self.human()
        self.switch("late-process", 120)
        with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "1", "SMINOS_WAKE_GRACE": "2"}):
            msgs = self.wave(target, PATHS, 2, 1)
            self.assertEqual([m.told for m in msgs], [STARTING] * 2)
            self.assertEqual(self.launches(), 1)
            [stuck] = self.helpers_alive(target.sid)
            time.sleep(2.2)   # the grace passes with no process holding the session
            os.unlink(os.path.join(self.state, "late-process"))
            rest = self.wave(target, PATHS, 5, 1, first=2)
        self.assertEqual({m.told for m in rest}, {"sent"}, "pushed by a sender's own call, due once the grace passed")
        self.assertEqual(self.launches(), 2)
        self.assertIn("its job %s was accepted and never ran" % target.sid[:8], self.daemon_log())
        self.assertFalse(wake_engine.pid_alive(stuck), "the accepted worker stopped before the next launch")
        self.assertEqual(len(self.helpers_alive(target.sid)), 1, "one copy of it runs")
        self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == len(msgs + rest)))
        frames = self.frames(target.sid)
        self.assert_once(frames, msgs + rest)
        self.assert_line_once_first(frames)
        waking = self.waking(target.tid, target.sid)
        self.assertNotIn("job", waking)
        self.assertNotIn("failed", waking, "forgotten once a process holds it")
        self.assertEqual(self.owed(target.sid), [])


# ------------------------------------------------------------ the line, senders racing one wake


class Race(Senders):
    def racing(self, target, n, during=None):
        """n senders' calls in processes of their own, by each way in turn, against one wake held at the engine's
        barrier until all have started; `during` run while it is held. The messages."""
        self.waves += 1
        self.switch("barrier")
        entered = self.launches()
        procs, msgs = [], []
        for j in range(n):
            path = PATHS[j % len(PATHS)]
            s = self.sender(path, j)
            token = "r-%d-%d." % (self.waves, j)
            env = dict({k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"},
                       CLAUDE_CODE_SESSION_ID=s)
            argv = ["send", target.sid[:8], token] if path == "send" else ["say", "@%s %s" % (target.sid[:8], token)]
            procs.append(subprocess.Popen([sys.executable, "-B", SCRIPT] + argv, env=env, text=True,
                                          cwd=self.other if path == "project" else self.root,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            self.addCleanup(lambda p=procs[-1]: p.poll() is None and p.kill())
            msgs.append(Msg(token, path, s, None))
        self.assertTrue(wait_for(lambda: self.launches() > entered, timeout=30), "a launch entered")
        time.sleep(0.5)   # the others, at the delivery lock or the wake's
        if during:
            during()
        os.unlink(os.path.join(self.state, "barrier"))
        for p in procs:
            out, err = p.communicate(timeout=90)
            self.assertEqual(p.returncode, 0, out + err)
        self.tick()   # what a deliverer left owed for a moment, the daemon's
        self.tick(self.q)
        return msgs

    def test_senders_racing_one_wake_start_one_process_and_the_line_goes_once_then_once_for_the_next_wake(self):
        target = self.human()
        msgs = self.racing(target, 5)
        self.assertEqual(self.launches(), 1, "one launch for five senders")
        self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == 5))
        frames = self.frames(target.sid)
        self.assert_once(frames, msgs)
        self.assert_line_once_first(frames)
        self.assertIn("terminal", line_of(frames[0])[1], "a first wake's line")
        self.stop(target.sid)
        later = self.racing(target, 5)
        self.assertEqual(self.launches(), 2)
        self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == 10))
        frames2 = self.frames(target.sid)[5:]
        self.assert_once(frames2, later)
        self.assert_line_once_first(frames2)
        self.assertNotIn("terminal", line_of(frames2[0])[1], "the later wake's own line, not the first's again")
        self.assertNotIn("line", self.waking(target.tid, target.sid))

    def test_senders_racing_a_wake_whose_session_another_process_took_meanwhile_push_there_with_no_line(self):
        for kind, fields in (("interactive", {}),
                             ("bg", {"jobId": "0badf00d", "startedAt": int(time.time() * 1000) + 60000})):
            with self.subTest(kind=kind):
                target = self.human()
                launched, removed = self.launches(), len(self.removals())
                took = []
                msgs = self.racing(target, 5, during=lambda: took.append(
                    self.holder(target.sid, kind, target.alias, **fields)))
                [(proc, received)] = took
                self.assertEqual(self.launches() - launched, 1, "one launch, its copy")
                self.assertEqual(len(self.removals()) - removed, 1, "the copy removed")
                got = self.received(received)
                self.assert_once(got, msgs)
                self.assertFalse([f for f in got if wake.LINE_HEAD in f],
                                 "no line to a process its launch did not make")
                self.assertNotIn("line", self.waking(target.tid, target.sid), "the copy's line removed")
                self.assertEqual(self.inputs(target.sid), [])
                self.assertEqual([j for j in self.jobs() if j.get("sessionId") != target.sid
                                  and j.get("state") not in ("stopped", "failed")], [], "no copy left running")
                self.end(proc)


# ------------------------------------------------------------ what is not promised


class NotPromised(Senders):
    def setUp(self):
        super().setUp()
        self.retry_soon()

    def killed_once(self, name, module=None):
        """`name` of `module` (sminos) raising Killed at its first call: the deliverer dies there."""
        module = module or sminos
        real, calls = getattr(module, name), []

        def once(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise Killed(name)
            return real(*a, **k)
        return mock.patch.object(module, name, once)

    def test_a_deliverer_killed_between_the_inboxs_admission_and_the_settlement_leaves_it_owed_and_pushed_again(self):
        for how in ("a sender's own call", "the daemon's pass"):
            with self.subTest(how=how):
                target = self.human()
                self.switch("fail-job")
                held = self.wave(target, PATHS[:2], 2, 1)
                os.unlink(os.path.join(self.state, "fail-job"))
                time.sleep(0.6)
                patch = self.killed_once("delivered_settle")
                with patch, self.assertRaises(Killed):
                    if how == "the daemon's pass":
                        self.tick()
                    else:
                        self.post(target, "project", "the third", self.sender("project", 2))
                self.assertIsNone(sminos.wake_held(target.tid), "no wake hold kept past the death")
                self.assertTrue(wait_for(lambda: self.frames(target.sid)), "the first frame admitted")
                first = held[0]
                self.assertEqual(sum(f.count(first.token) for f in self.frames(target.sid)), 1)
                self.assertTrue(self.owes(target.sid, first.token), "owed: its settlement died")
                self.tick()
                frames = self.frames(target.sid)
                self.assertEqual(sum(f.count(first.token) for f in frames), 2, "pushed again: T1's limit")
                self.assert_once(frames, held[1:])
                if how == "a sender's own call":
                    self.assertEqual(sum(f.count("the third") for f in frames), 1, "the dying sender's own, once")
                self.assertEqual(sum(f.count(wake.LINE_HEAD) for f in frames), 1, "the line once, with the first")
                self.assertEqual(len(self.resumes(target.sid)), 3, "two failed, one woke it: no wake for the copy")
                self.assertEqual(self.owed(target.sid), [])

    def test_a_deliverer_killed_after_the_wake_and_before_the_push_leaves_no_second_copy(self):
        target = self.human()
        self.switch("fail-job")
        held = self.wave(target, PATHS, 3, 1)
        os.unlink(os.path.join(self.state, "fail-job"))
        time.sleep(0.6)
        control = sminos.control_module()
        patch = self.killed_once("push_live", control)
        with patch, self.assertRaises(Killed):
            self.tick()
        self.assertIsNotNone(self.record(target.sid), "woken")
        self.assertEqual(self.frames(target.sid), [], "nothing pushed")
        self.assertIsNone(sminos.wake_held(target.tid))
        self.tick()
        frames = self.frames(target.sid)
        self.assert_once(frames, held)
        self.assert_line_once_first(frames)
        self.assertEqual(len(self.resumes(target.sid)), 4, "three failed, one woke it, none again")
        self.assertEqual(self.owed(target.sid), [])


# ------------------------------------------------------------ a second registry over a git mirror


class Remote(Senders):
    """Another machine's writers in the same project, their log reaching this machine by the git mirror alone:
    delivered by this machine's daemon, never by a sender's own call."""

    def setUp(self):
        super().setUp()
        bare = os.path.join(self.home, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        self.repo_dir = self.repo("mirrored")
        code, out = self.cli("project", "init", "--name", "demo", "--remote", bare, cwd=self.repo_dir)
        self.assertEqual(code, 0, out)
        subprocess.run(["git", "-C", self.repo_dir, "add", ".smns"], check=True)
        subprocess.run(["git", "-C", self.repo_dir, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
                        "smns"], check=True)
        self.p = self.project_of(self.repo_dir)
        there = tempfile.mkdtemp(dir=self.home)
        self.far_env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        self.far_env.update(HOME=os.path.join(there, "h"), SMINOS_HOME=os.path.join(there, "s"),
                            DAEMON_HOST="farhost")
        os.makedirs(os.path.join(self.far_env["HOME"], ".claude", "sessions"))
        os.makedirs(self.far_env["SMINOS_HOME"], mode=0o700)
        code, out = self.far("project", "attach")
        self.assertEqual(code, 0, out)

    def far(self, *argv, sender=None):
        env = dict(self.far_env, **({"CLAUDE_CODE_SESSION_ID": sender} if sender else {}))
        p = subprocess.run([sys.executable, "-B", SCRIPT] + list(argv), cwd=self.repo_dir, env=env,
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def mirrored(self, mode="auto"):
        """A stopped thread its human opened in the mirrored project."""
        sid = self.opened(mode)
        _, proc = self.session(sid=sid, root=self.repo_dir)
        self.reconcile()
        self.end(proc)
        tid = threads.stamp(sid)
        self.edit(tid, launch={"cwd": self.repo_dir, "at": sminos.now()})
        return Target("human", tid, sid, threads.get(tid)["alias"])

    def here_tick(self):
        code, out = self.cli("daemon", "tick", cwd=self.repo_dir)
        self.assertEqual(code, 0, out)

    def publish(self):
        """This machine's state to the other's, by the mirror."""
        self.here_tick()
        self.far("daemon", "tick")

    def far_wave(self, target, n, k):
        self.waves += 1
        senders = [str(uuidlib.uuid4()) for _ in range(n)]
        out = []
        for i in range(k):
            for j, s in enumerate(senders):
                token = "f-%d-%d-%d." % (self.waves, j, i)
                code, said = self.far("say", "@%s %s" % (target.sid[:8], token), sender=s)
                self.assertEqual(code, 0, said)
                out.append(Msg(token, "far", s, told(said)))
        code, said = self.far("daemon", "tick")   # its log to the mirror
        self.assertEqual(code, 0, said)
        return out

    def test_several_far_writers_wake_it_once_by_the_daemon_and_arrive_once_in_order(self):
        targets = {combo: self.mirrored() for combo in ((1, 1), (2, 3), (5, 1))}
        self.publish()
        for (n, k), target in targets.items():
            with self.subTest(senders=n, messages=k):
                msgs = self.far_wave(target, n, k)
                self.assertEqual({m.told for m in msgs}, {WOKEN_FAR})
                self.assertEqual(self.resumes(target.sid), [], "nothing here before the mirror brings it")
                self.here_tick()
                self.assertEqual(len(self.resumes(target.sid)), 1, "one wake")
                self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == n * k))
                frames = self.frames(target.sid)
                self.assert_once(frames, msgs)
                self.assert_in_order(frames, msgs)
                self.assert_line_once_first(frames)
                self.assertEqual(self.owed(target.sid), [])

    def test_far_writers_to_a_held_thread_are_told_why_held_marked_and_pushed_once_to_its_process(self):
        target = self.mirrored("plan")
        self.publish()
        self.publish()   # its hold published, then mirrored
        msgs = self.far_wave(target, 2, 3)
        self.assertEqual({m.told for m in msgs},
                         {line("mode").replace("recorded and held:", "recorded and held on testhost:")})
        self.here_tick()
        self.assert_held(target.sid, target.tid, msgs)
        self.assertEqual(self.resumes(target.sid), [])
        _, received = self.holder(target.sid, "interactive", target.alias, root=self.repo_dir)
        self.tick()
        got = self.received(received)
        self.assert_once(got, msgs)
        self.assert_in_order(got, msgs)
        self.assertEqual(self.owed(target.sid), [])

    def test_far_writers_after_one_failed_wake_wait_for_the_schedule_and_are_pushed_once(self):
        self.retry_soon(retry="1", cap="1")
        target = self.mirrored()
        self.publish()
        msgs = self.far_wave(target, 5, 1)
        self.switch("fail-job")
        self.here_tick()
        self.assertEqual(len(self.resumes(target.sid)), 1, "the daemon's wake, failed")
        self.assert_held(target.sid, target.tid, msgs)
        os.unlink(os.path.join(self.state, "fail-job"))
        self.tick()
        self.assertEqual(len(self.resumes(target.sid)), 1, "not due: the daemon waits")
        time.sleep(1.1)
        self.tick()
        self.assertEqual(len(self.resumes(target.sid)), 2, "due: woken")
        self.assertTrue(wait_for(lambda: len(self.frames(target.sid)) == len(msgs)))
        frames = self.frames(target.sid)
        self.assert_once(frames, msgs)
        self.assert_line_once_first(frames)
        self.assertEqual(self.owed(target.sid), [])


if __name__ == "__main__":
    unittest.main()
