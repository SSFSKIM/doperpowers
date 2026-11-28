#!/usr/bin/env python3
"""Telling the asker now (the execution document docs/doperpowers/plans/2026-11-27-task-board-b1.md, M2's Proves;
§3's table and §5's sending), against the test engine:

- the door's decision for each row of §3's table, each kind and class, and each of `wake` true, false and null;
- each notice's form, and that none holds the title, the body, an agent's comment, the human's note, an alias or
  a subagent's name;
- a running session's notice in its inbox; a notice that may wake waking a stopped thread once; a held thread's
  answer kept as given; one for the live alone whose recipient stopped before the push, at the door and with the
  push delayed to the daemon, starting nothing; a session in no project `none`, `not-addressable`, the verdict
  still `now`;
- the tell: queued by the stand-in bridge with no notice; refused, with no socket, and unanswered, each going on
  to the subagent's-thread form; never tried for a MAWS-run session, an outcome not sent, a successor or a session
  a hand-off went on in;
- a door killed after its replace: the sending due, resolved once the minute has passed by the same line again,
  by another task's act, by the hourly duty; a refusal not tried again;
- the ended line: in the project the thread ended in, naming no session, once; `endedLine` null when nothing could
  be appended;
- the hourly duty: the prune of closed tasks and of keys, the pairs bound and pruned, the daemon's call.

Hermetic: test_wake.Engine (HOME, SMINOS_HOME and the engine's state temporary, the engine first on PATH and
checked to be); bridges are bridge_standin.py's.
Run: python3 -B sminos/tests/test_tasks_telling.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import SCRIPTS, Killed  # noqa: E402
from test_wake import wait_for  # noqa: E402
from test_wake_delivery import FLAGS, Deliveries  # noqa: E402
from test_wake_seat import INBOX, sminos, threads  # noqa: E402
import bridge_standin  # noqa: E402

tasks = sminos.sibling_module("sminos_tasks")
CLI = os.path.join(SCRIPTS, "sminos")
TITLE, BODY = "Log in to the console", "Open the console and sign in."
NOTE, COMMENT, NAME = "logged in with account B", "an agent's own words", "the-reviewer"
AGENT = "a1b2c3d4e5f60718"
DAY = 86400


class Stdin:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)

    def isatty(self):
        return False


class Board(Deliveries):
    """The test engine's machine with the Task Board's verbs run in this process."""

    def t(self, *argv, session=None, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}), mock.patch.object(sys, "stdin", Stdin(stdin.encode())), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            if session:
                os.environ["CLAUDE_CODE_SESSION_ID"] = session
            sminos.forget_caches()
            try:
                sminos.main(["task"] + list(argv))
                code = 0
            except SystemExit as e:
                code = e.code or 0
            finally:
                sminos.forget_caches()
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv, **kw):
        code, out, err = self.t(*argv, **kw)
        self.assertEqual(code, 0, err)
        return out

    def assign(self, session, cls="blocking", agent=False):
        more = ["--asker-agent", AGENT, "--asker-name", NAME] if agent else []
        out = self.ok("assign", "--class", cls, "--title", TITLE, "--body-file", "-", *more, session=session,
                      stdin=BODY + "\n")
        return out.split()[0]

    def act(self, verb, tid, *more, expect=0):
        code, out, err = self.t(verb, tid, *more)
        self.assertEqual(code, expect, err)
        self.assertEqual([x for x in err.splitlines() if not x.startswith("key ")], [], "nothing else said")
        return json.loads(out)

    def store(self):
        with open(tasks.state_path()) as f:
            return json.load(f)

    def outcome(self, tid="t1", n=0):
        return self.store()["tasks"][tid]["outcomes"][n]

    def notices(self):
        return [e for e in self.log() if e.get("notice") == "tasks"]

    def live(self, name="term-a", sid=None):
        """A terminal's process holding a session with an inbox, joined: (session, process, the inbox's file)."""
        sid = sid or str(uuidlib.uuid4())
        sid, proc = self.session(sid=sid, kind="interactive", name=name)
        sock = os.path.join(self.home, "t-%s.sock" % sid[:8])
        received = sock + ".received"
        open(received, "a").close()
        server = subprocess.Popen([sys.executable, "-B", INBOX, sock, received])
        self.addCleanup(lambda: (server.kill(), server.wait()))
        wait_for(lambda: sminos.socket_ok(sock))
        self.peer_set(proc, messagingSocketPath=sock, nameSource="user")
        self.reconcile()
        return sid, proc, received

    def asked(self, cls="blocking", agent=False):
        """A running session's task, t1: (session, process, inbox)."""
        sid, proc, received = self.live()
        self.assertEqual(self.assign(sid, cls, agent), "t1")
        return sid, proc, received

    def bridge(self, sid, **kw):
        """The session's bridge: the real child, the stand-in its mod. A Unix socket's path is bounded (104 bytes on
        macOS), so the home is named through a short link from here on, as test_sheet_contract.py names it."""
        if not os.environ["SMINOS_HOME"].startswith("/tmp/"):
            link = os.path.join(tempfile.mkdtemp(prefix="smt.", dir="/tmp"), "s")
            os.symlink(os.environ["SMINOS_HOME"], link)
            self.addCleanup(shutil.rmtree, os.path.dirname(link))
            p = mock.patch.dict(os.environ, {"SMINOS_HOME": link})
            p.start()
            self.addCleanup(p.stop)
            sminos.forget_caches()
        standin = bridge_standin.StandIn(CLI, sid, ops=["tell"], env=dict(os.environ), **kw)
        self.addCleanup(standin.stop)
        self.assertTrue(wait_for(lambda: os.path.exists(os.path.join(sminos.root(), "bridge", sid + ".sock"))))
        return standin

    def told(self, standin):
        return [c for c in standin.commands if c.get("op") == "tell"]

    def later(self, seconds):
        """tasks.clock moved on by `seconds` for the rest of the test."""
        real = time.time
        p = mock.patch.object(tasks, "clock", side_effect=lambda: real() + seconds)
        p.start()
        self.addCleanup(p.stop)

    def form(self, letter, word, tid="t1"):
        return {"A": "[tasks v1] The human %s, a task you assigned. Read it: sminos task show %s",
                "B": "[tasks v1] The human %s, a task assigned by the conversation this one replaced at a /clear. "
                     "Read it: sminos task show %s",
                "C": "[tasks v1] The human %%s, a task your subagent %s assigned. Read it: sminos task show %%s"
                     % AGENT}[letter] % (word, tid)

    def assertClean(self, text, *also):
        for words in (TITLE, BODY, NOTE, COMMENT, NAME, "term-a", "alpha", *also):
            self.assertNotIn(words, text)


# ------------------------------------------------------------ the decision (§3's table)


def target(state, runner="terminal", project="1c0de000-0000-5000-8000-0000000000aa"):
    return {"session": "s", "thread": "t", "project": project, "state": state, "runner": runner, "wake": None,
            "why": "", "via": "self"}


class Decision(unittest.TestCase):
    def test_each_row_for_each_kind_and_class_and_each_wake(self):
        for act in ("done", "decline", "comment"):
            for cls in ("blocking", "needed", "optional"):
                for asked in (True, False, None):
                    wake = asked if asked is not None else cls == "blocking"
                    urgent = act != "decline" or cls == "blocking" or asked is True
                    rows = {
                        ("running", "terminal", True): "now" if urgent else "next-start",
                        ("running", "maws", True): "now" if urgent else "next-start",
                        ("running", "terminal", False): "now" if urgent else "next-start",
                        ("stopped", "terminal", True): "wake" if wake else "next-start",
                        ("stopped", "terminal", False): "next-start",
                        ("gone", "maws", True): "maws" if wake else "next-start",
                        ("gone", "terminal", True): "next-start",
                        ("ended", "terminal", True): "ended",
                        ("unknown", "terminal", True): "next-start",
                    }
                    for (state, runner, addressable), told in rows.items():
                        with self.subTest(act=act, cls=cls, wake=asked, state=state, runner=runner,
                                          addressable=addressable):
                            got = tasks.told_of(target(state, runner, "p" if addressable else None),
                                                {"class": cls}, {"act": act, "wake": asked}, {"wake": wake})
                            self.assertEqual(got, told)


# ------------------------------------------------------------ the notice


class Notice(Board):
    def test_a_done_reaches_a_running_session_now_in_form_a_with_nothing_an_agent_wrote(self):
        sid, _, received = self.asked()
        self.ok("comment", "t1", COMMENT, session=sid)
        v = self.act("done", "t1@1", "--note", NOTE)
        self.assertEqual(v["told"], "now")
        [frame] = self.received(received)
        self.assertIn(" from tasks@testhost → @you", frame.split("\n", 2)[1])
        self.assertIn(self.form("A", "marked t1 done"), frame)
        self.assertClean(frame)
        [e] = self.notices()
        self.assertEqual((e["kind"], e["text"], e["to"], e.get("wake")),
                         ("human", self.form("A", "marked t1 done"), [{"session": sid, "alias": e["to"][0]["alias"]}],
                          None), "addressed, able to wake: the task is blocking")
        send = self.outcome()["send"]
        self.assertEqual({k: send[k] for k in ("state", "how", "session", "agent", "liveOnly", "answer")},
                         {"state": "sent", "how": "notice", "session": sid, "agent": None, "liveOnly": False,
                          "answer": "sent"})
        self.assertEqual(send["project"], self.p.id)
        shown = self.ok("show", "t1").splitlines()
        at = next(i for i, x in enumerate(shown) if x.strip().startswith("done ") and NOTE in x)
        self.assertEqual(shown[at + 1].strip(), "a notice to [%s] that may wake: sent" % sid[:8],
                         "what was sent and what sminos answered, beneath the act")

    def test_each_kind_has_its_word_and_an_act_that_does_not_ask_is_for_the_live_alone(self):
        sid, _, received = self.live()
        for cls in ("needed", "optional", "needed"):
            self.assign(sid, cls)
        self.assertEqual(self.act("done", "t1")["told"], "now")
        self.assertEqual(self.act("comment", "t2", NOTE)["told"], "now")
        self.assertEqual(self.act("decline", "t3", "--reason", NOTE)["told"], "next-start")
        self.assertEqual(self.act("decline", "t2", "--reason", NOTE, "--wake")["told"], "now")
        self.assertEqual([e["text"] for e in self.notices()],
                         [self.form("A", "marked t1 done"), self.form("A", "commented on t2", "t2"),
                          self.form("A", "declined t2", "t2")])
        self.assertEqual([e.get("wake") for e in self.notices()], [True, True, None],
                         "for the live alone unless the act asked for a wake")
        self.assertEqual([self.outcome("t2", n)["send"]["liveOnly"] for n in (0, 1)], [True, False])
        self.assertIsNone(self.outcome("t3")["send"], "nothing sent for a needed task's decline")
        self.assertEqual(len(self.received(received)), 3)

    def test_a_notice_that_may_wake_wakes_a_stopped_thread_once(self):
        _, sid = self.human_thread()
        self.assign(sid)
        self.assign(sid, "needed")
        v = self.act("done", "t1")
        self.assertEqual(v["told"], "wake")
        self.assertEqual(self.resumes(sid), [FLAGS], "one wake")
        [frame] = self.frames(sid)
        self.assertIn(self.form("A", "marked t1 done"), frame)
        self.assertIn(self.outcome()["send"]["answer"], ("woken", "woken?"))
        self.stop(sid)
        self.assertEqual(self.act("done", "t2")["told"], "next-start", "a needed task's act asks no wake")
        self.assertEqual(self.resumes(sid), [FLAGS], "nothing started again")

    def test_a_held_threads_answer_is_kept_as_given(self):
        _, sid = self.human_thread(mode="plan")
        self.assign(sid)
        self.assertIn("stopped, held: mode", self.ok("list"))
        self.assertEqual(self.act("done", "t1")["told"], "wake")
        self.assertEqual(self.outcome()["send"]["answer"], "held:mode")
        self.assertEqual(self.resumes(sid), [])

    def test_a_notice_for_the_live_alone_whose_recipient_stopped_before_the_push_starts_nothing(self):
        _, sid = self.human_thread()
        sid, proc, _ = self.live(sid=sid)
        self.assign(sid, "needed")
        real = tasks.send

        def stopped_first(tid, key, memo=None):
            self.end(proc)
            return real(tid, key, memo)
        with mock.patch.object(tasks, "send", side_effect=stopped_first):
            self.assertEqual(self.act("done", "t1")["told"], "now")
        send = self.outcome()["send"]
        self.assertEqual((send["liveOnly"], send["answer"]), (True, "recorded"))
        self.assertEqual(self.resumes(sid), [], "nothing started")
        self.assertEqual(self.owed(sid), [])

    def test_with_its_push_delayed_to_the_daemon_too(self):
        _, sid = self.human_thread()
        sid, proc, _ = self.live(sid=sid)
        self.assign(sid, "needed")
        with mock.patch.object(sminos, "deliver_next", return_value={"delivered": 0, "pending": 1, "outcomes": []}):
            self.assertEqual(self.act("done", "t1")["told"], "now")
        self.assertEqual(self.outcome()["send"]["answer"], "owed")
        self.end(proc)
        self.assertEqual(len(self.owed(sid)), 1, "owed to it when it stopped")
        self.tick()
        self.assertEqual(self.resumes(sid), [], "the daemon's push started nothing")
        self.assertEqual(self.owed(sid), [], "settled, recorded")

    def test_a_session_in_no_project_is_not_addressable_and_the_verdict_still_says_now(self):
        sid, _ = self.session()
        self.assign(sid)
        self.assertEqual(self.act("done", "t1")["told"], "now")
        send = self.outcome()["send"]
        self.assertEqual((send["state"], send["why"]), ("none", "not-addressable"))
        self.assertEqual(self.notices(), [])
        self.assertIn("  not sent: not-addressable", self.ok("show", "t1"))

    def test_a_machine_whose_name_no_notice_is_read_under_is_no_writer(self):
        sid, _, received = self.asked()
        with mock.patch.object(sminos, "writer_id", side_effect=lambda s=None: "_mac/%s" % (s or "human")):
            self.assertEqual(self.act("done", "t1")["told"], "now")
        self.assertEqual(self.outcome()["send"]["why"], "no-writer")
        self.assertEqual((self.notices(), self.received(received)), ([], []))


# ------------------------------------------------------------ the tell


class Tell(Board):
    def test_a_tell_the_bridge_queues_writes_no_notice(self):
        sid, _, received = self.asked(agent=True)
        standin = self.bridge(sid, results={"tell": {"sent": True}})
        self.assertEqual(self.act("done", "t1")["told"], "now")
        [c] = self.told(standin)
        self.assertEqual((c["agentId"], c["resolvedAgentId"], c["text"]), (AGENT, AGENT, self.form("A", "marked t1 done")))
        send = self.outcome()["send"]
        self.assertEqual({k: send[k] for k in ("state", "how", "session", "agent", "liveOnly", "answer")},
                         {"state": "sent", "how": "tell", "session": sid, "agent": AGENT, "liveOnly": True,
                          "answer": "queued"})
        self.assertEqual((self.notices(), self.received(received)), ([], []))
        self.assertIn("  told its subagent %s: queued" % AGENT, self.ok("show", "t1"))

    def not_taken(self, answers=None):
        """A tell that did not take (`answers`: the stand-in's for `tell`; None: no bridge, no socket): the notice
        in the subagent's-thread form, by the table as the target then stands."""
        sid, _, received = self.asked(agent=True)
        standin = self.bridge(sid, answers={"tell": answers}) if answers is not None else None
        with mock.patch.object(tasks, "TELL_WAIT_MS", 300):
            self.assertEqual(self.act("done", "t1")["told"], "now")
        if standin is not None:
            self.assertEqual(len(self.told(standin)), 1)
        [frame] = self.received(received)
        self.assertIn(self.form("C", "marked t1 done"), frame)
        self.assertClean(frame)
        self.assertEqual(self.outcome()["send"]["how"], "notice")

    def test_a_refused_tell_goes_on_to_the_threads_form(self):
        self.not_taken({"refuse": ["unknown-agent", "agent %s is not running" % AGENT]})

    def test_an_unanswered_tell_goes_on_to_the_threads_form(self):
        self.not_taken({"unanswered": True})

    def test_a_tell_with_no_socket_goes_on_to_the_threads_form(self):
        self.not_taken()

    def test_no_tell_for_a_maws_session_or_an_outcome_not_sent(self):
        sid, _, received = self.asked(agent=True)
        self.assign(sid, "needed", agent=True)
        standin = self.bridge(sid, results={"tell": {"sent": True}})
        self.assertEqual(self.act("decline", "t2", "--reason", NOTE)["told"], "next-start")
        d = os.path.join(sminos.root(), "session-records")
        os.makedirs(d, exist_ok=True)
        sminos.write_json(os.path.join(d, sid + ".json"),
                          {"owners": ["@machine"], "origin": {"kind": "maws"}, "source": "hook", "basis": "hook"})
        self.assertEqual(self.act("done", "t1")["told"], "now")
        self.assertEqual(self.told(standin), [])
        self.assertIn(self.form("C", "marked t1 done"), self.received(received)[0])

    def test_a_successor_gets_form_b_and_a_hand_off_form_c_and_no_subagent_there_is_told(self):
        s1, proc, _ = self.asked(agent=True)
        self.assign(s1, agent=True)
        tid = threads.current_record(s1)["thread"]
        self.end(proc)
        s2, _, got2 = self.live(name="term-b")
        st = self.store()
        st["successors"][s1] = {"session": s2, "thread": threads.current_record(s2)["thread"],
                                "at": tasks.stamp(time.time() - 5)}
        tasks._replace(st)
        there = self.bridge(s2, results={"tell": {"sent": True}})
        self.assertEqual(self.act("done", "t1")["told"], "now")
        [frame] = self.received(got2)
        self.assertIn(self.form("B", "marked t1 done"), frame)
        st = self.store()
        del st["successors"][s1]
        tasks._replace(st)
        s3, _, got3 = self.live(name="term-c")
        self.edit(tid, current=s3, sessions=[s1, s3])
        here = self.bridge(s3, results={"tell": {"sent": True}})
        self.assertEqual(self.act("done", "t2")["told"], "now")
        [frame] = self.received(got3)
        self.assertIn(self.form("C", "marked t2 done", "t2"), frame)
        self.assertEqual((self.told(there), self.told(here)), ([], []), "a subagent's id is its own session's")


# ------------------------------------------------------------ a sending left due


class Due(Board):
    def killed(self, cls="blocking"):
        """t1 of a running session, its done's door killed after its replace: (session, inbox, the line)."""
        sid, _, received = self.asked(cls)
        line = json.dumps({"v": 1, "key": str(uuidlib.uuid4()), "act": "done", "task": "t1", "revision": 1,
                           "text": "", "wake": None}) + "\n"
        with mock.patch.object(tasks, "send", side_effect=Killed):
            with self.assertRaises(Killed):
                self.t("act", stdin=line)
        self.assertEqual(self.outcome()["send"]["state"], "due")
        return sid, received, line

    def test_the_same_line_again_answers_the_verdict_and_resolves_the_sending_once_the_minute_has_passed(self):
        sid, received, line = self.killed()
        first = self.ok("act", stdin=line)
        self.assertEqual(json.loads(first)["told"], "now")
        self.assertEqual(self.outcome()["send"]["state"], "due", "not before the minute")
        self.assertEqual(self.received(received), [])
        self.later(61)
        self.assertEqual(self.ok("act", stdin=line), first, "the stored verdict")
        self.assertEqual(self.outcome()["send"]["state"], "sent")
        self.assertEqual(len(self.received(received)), 1)
        self.ok("act", stdin=line)
        self.assertEqual(len(self.received(received)), 1, "resolved once")

    def test_another_tasks_act_resolves_it(self):
        sid, received, _ = self.killed()
        self.assign(sid, "needed")
        self.later(61)
        self.act("decline", "t2", "--reason", NOTE)
        self.assertEqual(self.outcome()["send"]["state"], "sent")
        self.assertIn(self.form("A", "marked t1 done"), self.received(received)[0])

    def test_the_hourly_duty_resolves_it_with_no_act(self):
        sid, received, _ = self.killed()
        self.assertEqual(tasks.hourly(), [])
        self.assertEqual(self.outcome()["send"]["state"], "due", "not before the minute")
        self.later(61)
        self.assertEqual(tasks.hourly(), [])
        self.assertEqual(self.outcome()["send"]["state"], "sent")
        self.assertEqual(len(self.received(received)), 1)

    def test_a_refusal_resolves_to_none_and_is_not_tried_again(self):
        sid, _ = self.session()
        self.assign(sid)
        self.act("done", "t1")
        refused = self.outcome()["send"]
        self.assertEqual(refused["state"], "none")
        self.reconcile()
        self.later(3600)
        self.assertEqual(tasks.hourly(), [])
        self.assertEqual(self.outcome()["send"], refused)
        self.assertEqual(self.notices(), [])


    def test_a_late_resolution_to_a_thread_ended_since_sends_no_notice_and_writes_its_ended_line(self):
        sid, received, line = self.killed()
        first = self.ok("act", stdin=line)
        self.edit(threads.current_record(sid)["thread"],
                  ended={"at": sminos.now(), "reason": "ended", "by": "", "pid": None})   # its process still there
        self.later(61)
        self.assertEqual(tasks.hourly(), [])
        send = self.outcome()["send"]
        self.assertEqual((send["state"], send["why"]), ("none", "not-addressable"))
        self.assertEqual(self.received(received), [], "nothing in the ended session's inbox")
        [e] = self.notices()
        self.assertEqual((e["to"], e["text"].split(";")[0]), ("*", "tasks: t1 was completed"))
        self.assertIsNotNone(self.outcome()["endedLine"])
        self.assertEqual(self.ok("act", stdin=line), first, "the verdict untouched")
        self.assertEqual(len(self.notices()), 1)

    def test_a_late_resolution_to_a_stopped_thread_whose_act_asked_no_wake_sends_nothing(self):
        _, sid = self.human_thread()
        sid, proc, _ = self.live(sid=sid)
        self.assign(sid, "needed")
        with mock.patch.object(tasks, "send", side_effect=Killed):
            with self.assertRaises(Killed):
                self.t("done", "t1")
        self.end(proc)
        self.later(61)
        self.assertEqual(tasks.hourly(), [])
        self.assertEqual(self.outcome()["send"]["why"], "not-addressable")
        self.assertEqual((self.notices(), self.resumes(sid)), ([], []))

    def test_the_acts_own_sending_reads_a_clear_written_since_its_step(self):
        s1, _, got1 = self.asked()
        s2, _, got2 = self.live(name="term-b")
        real = tasks.send

        def cleared_first(tid, key, memo=None):
            st = self.store()
            st["successors"][s1] = {"session": s2, "thread": threads.current_record(s2)["thread"],
                                    "at": tasks.stamp(time.time())}
            tasks._replace(st)
            return real(tid, key, memo)
        with mock.patch.object(tasks, "send", side_effect=cleared_first):
            self.assertEqual(self.act("done", "t1")["told"], "now")
        self.assertEqual(self.received(got1), [], "not the session left behind")
        [frame] = self.received(got2)
        self.assertIn(self.form("B", "marked t1 done"), frame)

    def test_a_store_of_a_newer_version_is_sent_nothing_however_often_it_is_tried(self):
        sid, received, line = self.killed()
        st = self.store()
        st["version"] = tasks.VERSION + 1
        tasks._replace(st)
        self.later(61)
        for _ in range(2):
            [why] = tasks.hourly()
            self.assertIn("newer than this sminos writes", why)
            code, _, err = self.t("act", stdin=line)
            self.assertEqual(code, 1)
            self.assertIn("nothing is sent", err)
        self.assertEqual((self.notices(), self.received(received)), ([], []))
        self.assertEqual(self.outcome()["send"]["state"], "due")

    def test_a_delivery_that_fails_once_the_notice_is_appended_is_owed_never_appended_again(self):
        sid, received = self.asked()[0], None
        with mock.patch.object(sminos, "deliver_next", side_effect=OSError("the delivery record")):
            self.assertEqual(self.act("done", "t1")["told"], "now")
        send = self.outcome()["send"]
        self.assertEqual((send["state"], send["answer"]), ("sent", "owed"))
        self.later(61)
        self.assertEqual(tasks.hourly(), [])
        self.assertEqual(len(self.notices()), 1, "sminos retries what it holds")


# ------------------------------------------------------------ the ended line


class Ended(Board):
    def ended(self):
        sid, proc, received = self.asked("needed")
        tid = threads.current_record(sid)["thread"]
        self.end(proc)
        self.edit(tid, ended={"at": sminos.now(), "reason": "ended", "by": "", "pid": None})
        return sid, received

    def test_the_ended_line_goes_to_the_project_it_ended_in_naming_no_session_once(self):
        sid, received = self.ended()
        v = self.act("done", "t1", "--note", NOTE)
        self.assertEqual(v["told"], "ended")
        [e] = self.notices()
        self.assertEqual((e["text"], e["to"]), (
            "tasks: t1 was completed; the conversation that assigned it has ended. It is on the board: sminos task "
            "show t1", "*"))
        self.assertNotIn(sid[:8], json.dumps(e))
        self.assertIsNotNone(self.outcome()["endedLine"])
        self.assertIsNone(self.outcome()["send"])
        self.later(61)
        self.assertEqual(tasks.hourly(), [])
        self.assertEqual(len(self.notices()), 1, "once")
        self.assertEqual(self.resumes(sid), [])

    def test_ended_line_stays_null_when_nothing_could_be_appended(self):
        self.ended()
        with mock.patch.object(sminos, "writer_id", side_effect=lambda s=None: "_mac/%s" % (s or "human")):
            self.assertEqual(self.act("done", "t1")["told"], "ended")
        self.assertIsNone(self.outcome()["endedLine"])
        self.assertEqual(self.notices(), [])


# ------------------------------------------------------------ the hourly duty


class Hourly(Board):
    def test_a_closed_task_past_30_days_goes_with_its_keys_unless_an_outcome_waits(self):
        sid, _ = self.session()
        self.assign(sid)
        self.assign(sid)
        self.act("done", "t1")
        self.act("done", "t2")
        shown = json.dumps({"v": 1, "key": str(uuidlib.uuid4()), "act": "shown", "task": "t1", "session": sid,
                            "keys": ["t1.1"]})
        self.assertEqual(json.loads(self.ok("act", stdin=shown + "\n"))["keys"], ["t1.1"])
        self.assertEqual(len(self.store()["applied"]), 3)
        self.later(29 * DAY)
        tasks.hourly()
        self.assertEqual(sorted(self.store()["tasks"]), ["t1", "t2"], "not yet 30 days")
        self.later(31 * DAY)
        tasks.hourly()
        s = self.store()
        self.assertEqual(sorted(s["tasks"]), ["t2"], "t2's outcome still waits")
        self.assertEqual([v["task"] for v in s["applied"].values()], ["t2"], "t1's keys, the shown's among them")

    def closed_and_shown(self):
        sid, _ = self.session()
        self.assign(sid)
        self.act("done", "t1")
        shown = json.dumps({"v": 1, "key": str(uuidlib.uuid4()), "act": "shown", "task": "t1", "session": sid,
                            "keys": ["t1.1"]})
        self.ok("act", stdin=shown + "\n")
        return sid

    def test_a_closed_task_whose_outcomes_do_not_read_stays_and_keeps_its_exemption(self):
        self.closed_and_shown()
        st = self.store()
        st["tasks"]["t1"]["outcomes"].append("not a record")
        tasks._replace(st)
        self.assertIn("could not be read", tasks.keeps("any", 3 * DAY))
        self.later(31 * DAY)
        tasks.hourly()
        self.assertIn("t1", self.store()["tasks"])
        self.assertIn("could not be read", tasks.keeps("any", 3 * DAY), "the exemption still holds")

    def test_a_closed_task_with_a_sending_still_due_stays(self):
        self.closed_and_shown()
        st = self.store()
        st["tasks"]["t1"]["outcomes"][0]["send"] = {"state": "due", "since": tasks.stamp(time.time())}
        tasks._replace(st)
        self.later(31 * DAY)
        with mock.patch.object(tasks, "send", side_effect=OSError("the log")):
            [why] = tasks.hourly()
        self.assertIn("left due", why)
        self.assertIn("t1", self.store()["tasks"])

    def test_an_unknown_ids_key_goes_after_30_days(self):
        sid, _ = self.session()
        self.assign(sid)
        self.act("done", "t9", expect=3)
        self.later(31 * DAY)
        self.act("done", "t8", expect=3)
        tasks.hourly()
        self.assertEqual(sorted(v["task"] for v in self.store()["applied"].values()), ["t8"])

    def test_pairs_are_bound_and_those_in_no_chain_go(self):
        s1, proc, _ = self.asked()
        self.end(proc)
        s2, _, _ = self.live(name="term-b")
        s8, s9 = str(uuidlib.uuid4()), str(uuidlib.uuid4())
        st = self.store()
        at = tasks.stamp(time.time() - 5)
        st["successors"][s1] = {"session": s2, "thread": None, "at": at}
        st["successors"][s8] = {"session": s9, "thread": None, "at": at}
        tasks._replace(st)
        self.assertEqual(tasks.hourly(), [])
        s = self.store()["successors"]
        self.assertEqual(sorted(s), [s1], "a pair no task's chain passes through goes")
        self.assertEqual(s[s1]["thread"], threads.current_record(s2)["thread"], "bound")
        self.assertEqual(self.ok("show", "t1", "--json").count('"via":"cleared"'), 1)

    def test_the_daemon_calls_it_hourly_and_says_a_failure_in_its_log(self):
        with mock.patch.object(tasks, "hourly", side_effect=OSError("the disk")), \
                mock.patch.object(self.daemon, "_OVERRIDES_SWEPT", 0):
            self.daemon.override_duty()
        self.assertIn("tasks: OSError: the disk", self.daemon_log())


if __name__ == "__main__":
    unittest.main(verbosity=1)
