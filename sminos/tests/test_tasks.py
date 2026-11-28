#!/usr/bin/env python3
"""The Task Board's store, its commands, the door and the start line (the execution document
docs/doperpowers/plans/2026-11-27-task-board-b1.md, M1's Proves; §1 to §3 and §5).

- The store: two processes' assigns, a kill before the replace, a line applied once whatever the target became,
  a writer of a newer version, the door refusing a session, the 501st open task, the history's order, the
  readers writing nothing and only the human's text `show` sending a `seen`, `waiting` unbounded by state or age,
  the human's verbs and their keys.
- The start line: nothing, open tasks, outcomes, more than twenty, a fork; 25 waiting with another deliverer
  marking first; a key whose target moved.
- The target and the asker's rights: a thread running, stopped, held, ended, purged; a /clear's successor in each
  of its states, handed off, cleared twice and forty times, a loop, the left session opened again; a session with
  no thread; MAWS's lane; records that cannot be read.
- A real /clear: the pair written before the alias is released, once whichever hook runs first, and by `remind`
  alone when the record hook was cut short.

Hermetic: HOME and SMINOS_HOME are temporary, fresh for each test (test_threads.Machine); sessions are `sleep`
processes with engine records the test writes, thread records written as sminos_threads keeps them.
Run: python3 -B sminos/tests/test_tasks.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import SCRIPTS, Killed, ms_ago, sminos, threads  # noqa: E402
from test_threads_stopped import Rig  # noqa: E402

tasks = sminos.sibling_module("sminos_tasks")
CLI = os.path.join(SCRIPTS, "sminos")
TITLE, BODY = "Log in to the console", "The body, which no start line carries."
DAY = 86400


def sid():
    return str(uuidlib.uuid4())


class Stdin:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)

    def isatty(self):
        return False


class Board(Rig):
    """A machine with the Task Board's verbs run in this process, and a world written by hand: thread records,
    the engine's records (live `sleep`s), session records, and a /clear's pairs in the store."""

    def t(self, *argv, session=None, stdin=None, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}), mock.patch.object(sys, "stdin", Stdin((stdin or "").encode())), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if "CLAUDE_CODE_SESSION_ID" not in (env or {}):
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

    def assign(self, session, cls="blocking", title=TITLE, **kw):
        return self.ok("assign", "--class", cls, "--title", title, session=session, **kw).split()[0]

    def done(self, tid, *more):
        return json.loads(self.ok("done", tid, *more).strip())

    def path(self):
        return tasks.state_path()

    def state(self):
        with open(self.path()) as f:
            return json.load(f)

    def raw(self):
        with open(self.path(), "rb") as f:
            return f.read()

    def write_state(self, s):
        os.makedirs(tasks.tasks_dir(), exist_ok=True)
        tasks._replace(s)

    def thread(self, current, sessions=None, ended=False, stopped=False, tid=None):
        tid = tid or str(uuidlib.uuid4())
        rec = {"thread": tid, "opened": "human", "current": current, "sessions": sessions or [current], "alias": "",
               "launch": {"cwd": self.root}, "channels": [], "created": sminos.now(), "updated": sminos.now()}
        if stopped:
            rec["stopped"] = sminos.now()
        if ended:
            rec["ended"] = {"at": sminos.now(), "reason": "retire", "by": "", "pid": None}
        os.makedirs(threads.store_dir(), exist_ok=True)
        sminos.write_json(os.path.join(threads.store_dir(), tid + ".json"), rec)
        sminos.forget_caches()
        return tid

    def unthread(self, tid):
        os.unlink(os.path.join(threads.store_dir(), tid + ".json"))
        sminos.forget_caches()

    def lane_b(self, session):
        d = os.path.join(sminos.root(), "session-records")
        os.makedirs(d, exist_ok=True)
        sminos.write_json(os.path.join(d, session + ".json"),
                          {"owners": ["@machine"], "origin": {"kind": "maws"}, "source": "hook", "basis": "hook"})

    def pair(self, left, begun, thread=None, at=None):
        s = self.state()
        s["successors"][left] = {"session": begun, "thread": thread, "at": at or tasks.stamp(time.time() - 5)}
        self.write_state(s)

    def target(self, tid="t1"):
        sminos.forget_caches()
        tasks._fresh_engine()
        s = self.state()
        return tasks.target_of(s, s["tasks"][tid])

    def asker(self, session, tid="t1"):
        sminos.forget_caches()
        tasks._fresh_engine()
        s = self.state()
        return tasks.is_asker(s, s["tasks"][tid], session)

    def line(self, **f):
        return json.dumps({"v": 1, "key": str(uuidlib.uuid4()), **f})


# ------------------------------------------------------------ the store


class Store(Board):
    def test_two_assigns_at_once_from_two_processes_get_two_ids_and_neither_is_lost(self):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=sid())
        loop = 'for i in $(seq 15); do "$0" task assign --class optional --title "t $i" >/dev/null || exit 1; done'
        procs = [subprocess.Popen(["bash", "-c", loop, CLI], env=env) for _ in range(2)]
        self.assertEqual([p.wait(120) for p in procs], [0, 0])
        s = self.state()
        self.assertEqual(sorted(s["tasks"], key=tasks.task_number), ["t%d" % n for n in range(1, 31)])
        self.assertEqual((s["nextId"], s["seq"]), (31, 30))

    def test_a_kill_between_the_temporary_file_and_the_replace_leaves_the_store_as_it_was(self):
        s1 = sid()
        self.assign(s1)
        before = self.raw()
        with mock.patch.object(tasks.os, "replace", side_effect=Killed):
            with self.assertRaises(Killed):
                self.t("assign", "--class", "needed", "--title", "second", session=s1)
        self.assertEqual(self.raw(), before)
        self.assertTrue([n for n in os.listdir(tasks.tasks_dir()) if n.startswith(".tmp-")], "the dead step's file")
        self.assertEqual(self.assign(s1), "t2")
        self.assertFalse([n for n in os.listdir(tasks.tasks_dir()) if n.startswith(".tmp-")], "removed by the next")

    def test_the_same_line_twice_answers_the_first_verdict_whatever_the_target_became(self):
        s1 = sid()
        self.assign(s1)
        line = self.line(act="done", task="t1", revision=1, text="", wake=None)
        ended = {"session": s1, "thread": None, "project": None, "state": "ended", "runner": "terminal",
                 "wake": None, "why": "", "via": "self"}
        with mock.patch.object(tasks, "_target", return_value=ended):
            first = self.ok("act", stdin=line + "\n")
        self.assertEqual(json.loads(first)["told"], "ended")
        seq = self.state()["seq"]
        with mock.patch.object(tasks, "_target", return_value=dict(ended, state="running")):
            again = self.ok("act", stdin=line + "\n")
        self.assertEqual(again, first)
        self.assertEqual(self.state()["seq"], seq, "nothing changed")

    def test_a_command_waiting_behind_a_newer_writer_refuses_and_the_readers_still_read(self):
        s1 = sid()
        self.assign(s1)
        newer = self.state()
        newer["version"] = 2
        newer["tasks"]["t1"]["laterField"] = {"x": 1}
        with open(tasks.lock_path(), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            proc = subprocess.Popen([CLI, "task", "assign", "--class", "needed", "--title", "x"],
                                    env=dict(os.environ, CLAUDE_CODE_SESSION_ID=s1), stderr=subprocess.PIPE, text=True)
            time.sleep(0.8)
            self.assertIsNone(proc.poll(), "it waits for the lock")
            tasks._replace(newer)
            fcntl.flock(lock, fcntl.LOCK_UN)
        _, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 1, err)
        self.assertIn("newer than this sminos writes", err)
        self.assertEqual(self.state()["version"], 2, "nothing written over it")
        for argv in (("show", "t1"), ("show", "t1", "--json"), ("list",), ("list", "--json"), ("waiting", "--json")):
            with self.subTest(argv=argv):
                self.assertEqual(self.t(*argv, session=s1)[0], 0)
        self.assertEqual(self.t("act", stdin=self.line(act="seen", task="t1", seq=1))[0], 1)

    def test_a_session_at_the_door_exits_3_and_changes_nothing(self):
        s1 = sid()
        self.assign(s1)
        before = self.raw()
        for argv, stdin in ((("act",), self.line(act="done", task="t1", revision=1, text="", wake=None)),
                            (("done", "t1"), None), (("decline", "t1", "--reason", "no"), None)):
            with self.subTest(argv=argv):
                code, out, err = self.t(*argv, session=s1, stdin=stdin)
                self.assertEqual((code, out), (3, ""))
                self.assertIn("does not complete the human's task", err)
        self.assertEqual(self.raw(), before)

    def test_a_call_with_one_bad_line_applies_nothing(self):
        s1 = sid()
        self.assign(s1)
        before = self.raw()
        good = self.line(act="done", task="t1", revision=1, text="", wake=None)
        for bad in ('{"v":1}', self.line(act="done", task="t1", revision=1, text="", wake=None, extra=1),
                    self.line(act="decline", task="t1", revision=1, text="", wake=None), "not json",
                    self.line(act="done", task="t1", revision=1, text="", wake=None).replace("null", "NaN"),
                    # Each field of its type exactly, checked before anything else looks at it.
                    self.line(act=["done"], task="t1", revision=1, text="", wake=None),
                    self.line(act={"done": 1}, task="t1"),
                    self.line(act="done", task="t1", revision=1, text="", wake=1),
                    self.line(act="done", task="t1", revision=1, text="", wake=0),
                    self.line(act="done", task="t1", revision=True, text="", wake=None),
                    self.line(act="done", task="t1", revision=1.0, text="", wake=None),
                    self.line(act="done", task="t1", revision=1, text=7, wake=None),
                    self.line(act="done", task=1, revision=1, text="", wake=None),
                    self.line(act="done", key=7, task="t1", revision=1, text="", wake=None),
                    self.line(act="done", task="t1", revision=1, text="", wake=None).replace('"v": 1', '"v": true'),
                    self.line(act="seen", task="t1", seq=True),
                    self.line(act="comment", task="t1", text=["x"], wake=None),
                    self.line(act="shown", task="t1", session=7, keys=["t1.1"]),
                    self.line(act="shown", task="t1", session=sid(), keys="t1.1"),
                    self.line(act="shown", task="t1", session=sid(), keys=[1])):
            with self.subTest(bad=bad):
                self.assertEqual(self.t("act", stdin=good + "\n" + bad + "\n")[0], 2)
                self.assertEqual(self.raw(), before)
        self.assertEqual(self.t("act", stdin="\n".join([good] * 51))[0], 2, "at most fifty lines a call")

    def test_the_501st_open_task_is_refused_by_assign_and_by_reopen(self):
        s1 = sid()
        self.assign(s1)
        s = self.state()
        for n in range(2, 501):
            s["tasks"]["t%d" % n] = dict(s["tasks"]["t1"], id="t%d" % n)
        s["nextId"] = 501
        self.write_state(s)
        code, _, err = self.t("assign", "--class", "needed", "--title", "one more", session=s1)
        self.assertEqual(code, 3)
        self.assertIn("500 open", err)
        self.done("t500")
        self.assertEqual(self.assign(s1, title="the 500th open"), "t501")
        code, _, err = self.t("reopen", "t500", "--comment", "it failed", session=s1)
        self.assertEqual(code, 3)
        self.assertIn("500 open", err)
        self.assertEqual(self.state()["tasks"]["t500"]["state"], "done")

    def test_a_done_a_reopen_and_a_second_done_within_one_millisecond_print_in_that_order(self):
        s1 = sid()
        self.assign(s1)
        with mock.patch.object(tasks, "clock", return_value=time.time()):
            self.done("t1", "--note", "first")
            self.ok("reopen", "t1", "--comment", "still asks", session=s1)
            self.done("t1@2", "--note", "second")
        hist = [ln.strip() for ln in self.ok("show", "t1", session=s1).splitlines()
                if ln.strip().startswith(("done", "comment"))]
        self.assertEqual([h.split()[0] for h in hist], ["done", "comment", "done"])
        self.assertIn('"first"', hist[0])
        self.assertIn('"still asks"', hist[1])
        self.assertIn('"second"', hist[2])

    def test_a_reopened_task_is_open_and_not_listed_as_closed(self):
        s1 = sid()
        self.assign(s1)
        self.done("t1")
        self.ok("reopen", "t1", "--comment", "no", session=s1)
        t = self.state()["tasks"]["t1"]
        self.assertEqual((t["state"], t["closed"], t["revision"]), ("open", None, 2))
        self.assertFalse(tasks.closed_lately(t, time.time()))
        self.assertEqual(json.loads(self.ok("list", "--closed", "--json"))["tasks"], [])
        self.assertEqual([x["id"] for x in json.loads(self.ok("list", "--json"))["tasks"]], ["t1"])

    def test_a_refused_line_again_answers_its_refusal_whatever_the_store_became(self):
        """§3's retry promise, the first verdict whatever it was: a refusal is kept by its key like an
        application, so the same line again answers it and changes nothing."""
        s1 = sid()
        self.assign(s1)
        self.done("t1")
        late = self.line(act="done", task="t1", revision=1, text="late", wake=None)
        closed = json.loads(self.ok("act", stdin=late + "\n"))
        self.assertEqual((closed["verdict"], closed["state"]), ("closed", "done"))
        self.ok("reopen", "t1", "--comment", "still asks", session=s1)
        before = self.raw()
        self.assertEqual(json.loads(self.ok("act", stdin=late + "\n")), closed)
        self.assertEqual(self.raw(), before, "nothing applied, nothing changed")

    def test_the_humans_keyed_comment_refused_closed_stays_refused_after_a_reopen(self):
        s1 = sid()
        self.assign(s1)
        self.done("t1")
        key = str(uuidlib.uuid4())
        code, out, _ = self.t("comment", "t1", "which account?", "--key", key)
        self.assertEqual((code, json.loads(out)["verdict"]), (3, "closed"))
        self.ok("reopen", "t1", "--comment", "still asks", session=s1)
        before = self.raw()
        self.assertEqual(self.t("comment", "t1", "which account?", "--key", key)[:2], (code, out))
        self.assertEqual(self.raw(), before)
        self.assertEqual([c["by"] for c in self.state()["tasks"]["t1"]["comments"]].count("human"), 0)
        code, out, _ = self.t("comment", "t1", "which account?")          # a new key: a new act
        self.assertEqual((code, json.loads(out)["verdict"]), (0, "applied"))

    def test_a_done_on_an_id_not_yet_made_stays_unknown_once_it_is(self):
        s1 = sid()
        self.assign(s1)
        line = self.line(act="done", task="t2", revision=1, text="", wake=None)
        unknown = json.loads(self.ok("act", stdin=line + "\n"))
        self.assertEqual(unknown["verdict"], "unknown")
        self.assertEqual(self.state()["applied"][json.loads(line)["key"]]["task"], "t2", "kept under the id named")
        self.assign(s1, title="second")
        self.assertIn("t2", self.state()["tasks"])
        before = self.raw()
        self.assertEqual(json.loads(self.ok("act", stdin=line + "\n")), unknown)
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.state()["tasks"]["t2"]["state"], "open")

    def test_a_door_line_where_there_is_no_store_makes_it_to_keep_its_verdict(self):
        line = self.line(act="done", task="t1", revision=1, text="", wake=None)
        unknown = json.loads(self.ok("act", stdin=line + "\n"))
        self.assertEqual(unknown["verdict"], "unknown")
        self.assign(sid())
        self.assertEqual(json.loads(self.ok("act", stdin=line + "\n")), unknown)
        self.assertEqual(self.state()["tasks"]["t1"]["state"], "open")

    def test_an_id_has_no_cap(self):
        s1 = sid()
        self.assign(s1)
        far = "t12345678901"
        v = json.loads(self.ok("act", stdin=self.line(act="done", task=far, revision=12345678901, text="",
                                                      wake=None) + "\n"))
        self.assertEqual((v["verdict"], v["task"]), ("unknown", far))
        code, _, err = self.t("show", far)
        self.assertNotEqual(code, 2, err)
        self.assertEqual(self.t("show", "t01")[0], 2)
        code, out, err = self.t("done", far + "@12345678901")
        self.assertEqual(json.loads(out)["verdict"], "unknown", err)

    def test_a_stamp_is_the_millisecond_its_second_is(self):
        t = 1764263999.9997
        self.assertEqual(tasks.stamp(t), time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(1764263999)) + ".999Z")
        self.assertEqual(tasks.stamp(1764264000.0), time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(1764264000)) +
                         ".000Z")

    def test_the_humans_comment_and_reason_are_held_to_the_doors_rule(self):
        s1 = sid()
        self.assign(s1)
        self.assign(s1, cls="optional", title="second")
        for argv in (("comment", "t1", "   "), ("decline", "t2", "--reason", " \t ")):
            with self.subTest(argv=argv):
                code, out, err = self.t(*argv)
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out)["verdict"], "applied")
        for argv in (("comment", "t1", ""), ("decline", "t1", "--reason", "")):
            with self.subTest(argv=argv):
                self.assertEqual(self.t(*argv)[0], 2, "the empty string is no text, at the CLI as at the door")
        self.assertEqual(self.t("comment", "t1", " ", session=s1)[0], 0, "an agent's comment by the same rule")

    def test_show_prints_a_dones_note_and_a_declines_reason(self):
        s1 = sid()
        self.assign(s1)
        self.assign(s1, cls="optional", title="second")
        self.done("t1", "--note", "logged in with account B")
        self.assertEqual(json.loads(self.ok("decline", "t2", "--reason", "not mine"))["state"], "declined")
        self.assertIn('"logged in with account B"', self.ok("show", "t1", session=s1))
        self.assertIn('declined', self.ok("show", "t2", session=s1))
        self.assertIn('"not mine"', self.ok("show", "t2", session=s1))

    def test_the_readers_write_nothing_and_only_the_humans_text_show_sends_a_seen(self):
        s1 = sid()
        self.assign(s1)
        self.ok("revise", "t1", "--title", "changed", session=s1)
        before = self.raw()
        for _ in range(2):
            for argv in (("list", "--json"), ("show", "t1", "--json"), ("waiting", "--json"), ("list",), ("waiting",)):
                self.ok(*argv)
            self.ok("show", "t1", session=s1)
        self.assertEqual(self.raw(), before, "bytes and seq as they were")
        self.assertTrue(json.loads(self.ok("show", "t1", "--json"))["task"]["updated"])
        self.ok("show", "t1")
        s = self.state()
        self.assertEqual((s["seq"], s["tasks"]["t1"]["seenSeq"]), (3, 2), "a seen for the snapshot's seq")
        self.assertFalse(json.loads(self.ok("show", "t1", "--json"))["task"]["updated"])

    def test_a_reader_leaves_the_whole_home_as_it_was(self):
        """The readers run ahead of main's migration (which would make the root 0700, files 0600, former paths'
        links): every file and directory of HOME and SMINOS_HOME, its bytes and its mode, as it was. The human's
        text show changes the store alone (its `seen`)."""
        s1, _ = self.opened()
        self.assign(s1)
        self.done("t1")
        os.chmod(sminos.root(), 0o755)     # what a migration would put right, so a reader that ran one shows it

        def snapshot(skip=()):
            got = {}
            for top in (os.environ["HOME"], sminos.root()):
                for d, dirs, files in os.walk(top):
                    for n in dirs + files:
                        p = os.path.join(d, n)
                        if p in skip:
                            continue
                        st = os.lstat(p)
                        body = b""
                        if os.path.isfile(p) and not os.path.islink(p):
                            with open(p, "rb") as f:
                                body = f.read()
                        got[p] = (st.st_mode, hashlib.sha256(body).hexdigest(), os.path.islink(p) and os.readlink(p))
                got[top] = (os.lstat(top).st_mode,)
            return got
        before = snapshot()
        for argv in (("list",), ("list", "--json"), ("list", "--all"), ("show", "t1", "--json"), ("waiting",),
                     ("waiting", "--json"), ("waiting", "--mine")):
            with self.subTest(argv=argv):
                self.t(*argv, session=s1 if "--mine" in argv else None)
                self.assertEqual(snapshot(), before)
        self.ok("show", "t1")
        self.assertEqual(snapshot(skip={self.path()}), {p: v for p, v in before.items() if p != self.path()})

    def test_waiting_lists_an_outcome_of_a_task_closed_forty_days_ago(self):
        s1 = sid()
        self.assign(s1)
        with mock.patch.object(tasks, "clock", return_value=time.time() - 40 * DAY):
            self.done("t1")
        self.assertEqual([w["key"] for w in json.loads(self.ok("waiting", "--json"))["waiting"]], ["t1.1"])
        self.assertEqual(json.loads(self.ok("list", "--closed", "--json"))["tasks"], [], "past its 30 days")
        self.assertIn("t1.1  marked t1 done", self.ok("waiting"))

    def test_waiting_mine_lists_the_twenty_first_outcome_the_start_line_counts(self):
        s1, s2 = sid(), sid()
        for n in range(21):
            self.assign(s1, cls="optional", title="t%d" % n)
            self.done("t%d" % (n + 1))
        self.assign(s2)
        self.done("t22")
        out = self.ok("remind", "--session", s1)
        self.assertEqual(out.splitlines()[0].split(), ["t%d.1" % n for n in range(1, 21)])
        self.assertIn("(and 1 more: sminos task waiting --mine)", out)
        mine = json.loads(self.ok("waiting", "--mine", "--json", session=s1))["waiting"]
        self.assertEqual([w["key"] for w in mine], ["t%d.1" % n for n in range(1, 22)])
        self.assertEqual(self.t("waiting", "--mine")[0], 3, "--mine needs a session")

    def test_done_exits_3_on_a_stale_revision_and_prints_the_verdict(self):
        s1 = sid()
        self.assign(s1)
        self.ok("revise", "t1", "--class", "needed", session=s1)
        code, out, err = self.t("done", "t1")
        self.assertEqual(code, 3)
        v = json.loads(out)
        self.assertEqual((v["verdict"], v["revision"], v["state"]), ("stale", 2, "open"))
        self.assertTrue(err.startswith("key "))

    def test_done_with_a_key_twice_applies_once_and_a_comment_without_one_twice_makes_two(self):
        s1 = sid()
        self.assign(s1)
        key = str(uuidlib.uuid4())
        first = self.t("done", "t1", "--key", key)
        self.assertEqual(self.t("done", "t1", "--key", key), first)
        self.assertEqual(first[2], "key %s\n" % key)
        self.assertEqual(len(self.state()["tasks"]["t1"]["outcomes"]), 1)
        self.assign(s1, title="second")
        self.ok("comment", "t2", "the same words")
        self.ok("comment", "t2", "the same words")
        self.assertEqual([c["text"] for c in self.state()["tasks"]["t2"]["comments"]], ["the same words"] * 2)
        code, out, _ = self.t("done", "t1", "--key", key, "--note", "other")
        self.assertEqual((code, json.loads(out)["reason"]), (3, "key-reused"))

    def test_the_key_is_printed_before_anything_is_applied(self):
        s1 = sid()
        self.assign(s1)
        seen = []
        real = tasks.apply_line

        def check(line):
            seen.append(sys.stderr.getvalue())
            return real(line)
        with mock.patch.object(tasks, "apply_line", side_effect=check):
            self.t("done", "t1")
        self.assertTrue(seen and seen[0].startswith("key "), seen)

    def test_an_agents_verbs_need_a_session_and_the_humans_refuse_one(self):
        self.assertEqual(self.t("assign", "--class", "needed", "--title", "x")[0], 3)
        s1 = sid()
        self.assign(s1)
        for argv in (("revise", "t1", "--title", "y"), ("withdraw", "t1"), ("reopen", "t1", "--comment", "c")):
            self.assertEqual(self.t(*argv)[0], 3, argv)
        for bad in (("--title", ""), ("--title", "a\nb"), ("--title", "x" * 201), ("--tag", "Bad Tag"),
                    ("--due", "2027-02-30"), ("--asker-agent", "a b")):
            with self.subTest(bad=bad):
                self.assertEqual(self.t("assign", "--class", "needed", *(bad if bad[0] == "--title" else
                                                                         ("--title", "ok") + bad), session=s1)[0], 2)
        self.assertEqual(self.t("revise", "t1", session=s1)[0], 2, "nothing given")

    def test_assign_records_the_subagent_and_reduces_its_name(self):
        s1 = sid()
        self.ok("assign", "--class", "blocking", "--title", "x", "--asker-agent", "a1b2c3d4e5f60718",
                "--asker-name", 'code "review" agent', session=s1)
        self.assertEqual(self.state()["tasks"]["t1"]["askers"][0]["agent"],
                         {"id": "a1b2c3d4e5f60718", "name": "code-review-agent"})


# ------------------------------------------------------------ the start line


class StartLine(Board):
    def test_remind_for_nothing_open_tasks_and_waiting_outcomes(self):
        s1 = sid()
        self.assign(s1)
        self.assertEqual(self.ok("remind", "--session", sid()), "\n", "nothing: an empty first line")
        self.assertEqual(self.ok("remind", "--session", s1), "\nTasks you assigned to the human: 1 open (1 blocking).\n")
        self.done("t1")
        self.assertEqual(self.ok("remind", "--session", s1), "t1.1\nThe human acted on tasks you assigned: marked t1 "
                                                             "done. Read one: sminos task show t1\n")
        self.assertFalse(os.path.exists(os.path.join(sminos.root(), "daemon", "identity.json")), "no enrollment")

    def test_more_than_twenty_are_counted_and_the_rest_named_at_the_next_start(self):
        s1 = sid()
        for n in range(1, 24):
            self.assign(s1, cls="optional", title="t%d" % n)
            self.done("t%d" % n)
        out = self.ok("remind", "--session", s1).splitlines()
        self.assertEqual(len(out[0].split()), 20)
        self.assertIn("(and 3 more: sminos task waiting --mine)", out[1])
        self.ok("shown", "--session", s1, "--keys", ",".join(out[0].split()))
        out = self.ok("remind", "--session", s1).splitlines()
        self.assertEqual(out[0].split(), ["t21.1", "t22.1", "t23.1"])
        self.assertNotIn("more", out[1])

    def test_a_fork_is_told_and_its_line_holds_no_title_or_body(self):
        s1 = sid()
        self.ok("assign", "--class", "blocking", "--title", TITLE, "--body-file", "-", session=s1, stdin=BODY)
        out = self.ok("remind", "--session", sid(), "--source", "fork")
        self.assertEqual(out, "\n" + tasks.FORK + "\n")
        self.done("t1", "--note", "the human's note")
        for session, source in ((s1, "startup"), (s1, "compact"), (sid(), "fork")):
            out = self.ok("remind", "--session", session, "--source", source)
            for words in (TITLE, BODY, "the human's note"):
                self.assertNotIn(words, out)

    def test_with_25_waiting_another_deliverer_marks_first_and_this_start_marks_nothing_more(self):
        for mark in ("another start", "the door"):
            with self.subTest(mark=mark):
                self.fresh()
                s1 = sid()
                for n in range(1, 26):
                    self.assign(s1, cls="optional", title="t%d" % n)
                    self.done("t%d" % n)
                named = self.ok("remind", "--session", s1).splitlines()[0].split()
                self.assertEqual(named, ["t%d.1" % n for n in range(1, 21)])
                if mark == "another start":
                    self.ok("shown", "--session", s1, "--keys", ",".join(named))
                else:
                    for n in range(1, 21):
                        self.ok("act", stdin=self.line(act="shown", task="t%d" % n, session=s1, keys=["t%d.1" % n]))
                self.assertEqual(self.ok("shown", "--session", s1, "--keys", ",".join(named)), "\n")
                left = [w["key"] for w in json.loads(self.ok("waiting", "--json"))["waiting"]]
                self.assertEqual(left, ["t%d.1" % n for n in range(21, 26)])

    def test_shown_for_a_session_no_longer_a_keys_target_marks_nothing(self):
        s1, s2 = sid(), sid()
        tid = self.thread(s1)
        self.assign(s1)
        self.done("t1")
        self.pair(s1, s2, thread=self.thread(s2, stopped=True))
        self.assertEqual(self.target()["session"], s2)
        self.assertEqual(self.ok("shown", "--session", s1, "--keys", "t1.1"), "\n")
        v = json.loads(self.ok("act", stdin=self.line(act="shown", task="t1", session=s1, keys=["t1.1"])))
        self.assertEqual(v["keys"], [])
        self.assertIsNone(self.state()["tasks"]["t1"]["outcomes"][0]["shown"])
        self.assertTrue(tid)


# ------------------------------------------------------------ the target and the asker's rights


class Targets(Board):
    def asked(self, live=True, **thread):
        """A session with a thread record (and a process when `live`) that assigned t1."""
        s1 = sid()
        if live:
            self.session(sid=s1)
        tid = self.thread(s1, **thread)
        self.assign(s1)
        self.assertEqual(self.state()["tasks"]["t1"]["askers"][0]["thread"], tid)
        return s1, tid

    def assertTarget(self, session, state, via="self", runner="terminal"):
        got = self.target()
        self.assertEqual((got["session"], got["state"], got["via"], got["runner"]), (session, state, via, runner))
        return got

    def test_a_running_thread(self):
        s1, tid = self.asked()
        got = self.assertTarget(s1, "running")
        self.assertEqual(got["thread"], tid)

    def test_a_stopped_thread_with_and_without_its_stop_mark_to_be_woken_and_held(self):
        for mark in (False, True):
            with self.subTest(mark=mark):
                self.fresh()
                s1, _ = self.asked(live=False, stopped=mark)
                with mock.patch.object(sminos, "wake_here", return_value=("woken", "")):
                    self.assertEqual(self.assertTarget(s1, "stopped")["wake"], "woken")
                    self.assertIn("(stopped, to be woken)", self.ok("list"))
                with mock.patch.object(sminos, "wake_here", return_value=("held", "mode")):
                    got = self.assertTarget(s1, "stopped")
                    self.assertEqual((got["wake"], got["why"]), ("held", "mode"))
                    self.assertIn("(stopped, held: mode)", self.ok("list"))

    def test_an_ended_thread_even_while_its_process_runs(self):
        s1, tid = self.asked(live=False)
        self.thread(s1, ended=True, tid=tid)
        self.assertTarget(s1, "ended")
        self.session(sid=s1)
        self.assertTarget(s1, "ended")
        self.assertEqual(json.loads(self.ok("done", "t1").strip())["told"], "ended")

    def test_a_retired_and_purged_thread_is_gone(self):
        s1, tid = self.asked(live=False)
        self.unthread(tid)
        self.assertTarget(s1, "gone")

    def test_a_cleared_thread_with_a_running_a_stopped_and_an_unrecorded_successor(self):
        for case in ("running", "stopped", "unrecorded"):
            with self.subTest(case=case):
                self.fresh()
                s1, _ = self.asked(live=False)
                s2 = sid()
                if case != "stopped":
                    self.session(sid=s2)
                t2 = self.thread(s2) if case != "unrecorded" else None
                self.pair(s1, s2, thread=t2)
                self.assertTarget(s2, "running" if case != "stopped" else "stopped", via="cleared")
                self.assertTrue(self.asker(s2), "the successor may revise")
                self.assertTrue(self.asker(s1), "and the thread's current session still")

    def test_a_dead_successor_leaves_the_task_with_the_conversation_before_it(self):
        for case in ("ended", "purged, bound", "retired, unbound", "gone, unbound"):
            with self.subTest(case=case):
                self.fresh()
                s1, _ = self.asked(live=False)
                s2 = sid()
                t2 = None
                if case == "ended":
                    t2 = self.thread(s2, ended=True)
                elif case == "purged, bound":
                    t2 = self.thread(s2)
                    self.unthread(t2)
                elif case == "retired, unbound":
                    self.session(sid=s2)
                self.pair(s1, s2, thread=t2)
                with mock.patch.object(sminos, "last_project", return_value=self.p), \
                        mock.patch.object(sminos, "retired_in_log", return_value=True):
                    self.assertTarget(s1, "stopped")
                    self.assertFalse(self.asker(s2))

    def test_a_successor_that_handed_off_is_followed_to_its_thread_and_not_its_old_id(self):
        s1, _ = self.asked(live=False)
        s2, s3 = sid(), sid()
        t2 = self.thread(s3, sessions=[s2, s3])
        self.pair(s1, s2, thread=t2)
        self.session(sid=s3)
        self.assertTarget(s3, "running", via="cleared")
        self.thread(s2)              # the successor's old id opened again: a thread of its own
        self.session(sid=s2)
        self.assertTarget(s3, "running", via="cleared")
        self.assertEqual(self.t("revise", "t1", "--class", "needed", session=s2)[0], 3)
        self.assertEqual(self.t("revise", "t1", "--class", "needed", session=s3)[0], 0)

    def test_cleared_twice_and_forty_times_in_a_row(self):
        s1, _ = self.asked(live=False)
        chain = [s1] + [sid() for _ in range(40)]
        tids = {}
        for left, begun in zip(chain, chain[1:]):
            tids[begun] = self.thread(begun, ended=chain.index(begun) > 35)
            self.pair(left, begun, thread=tids[begun])
        self.assertTarget(chain[35], "stopped", via="cleared")
        self.fresh()
        s1, _ = self.asked(live=False)
        s2, s3 = sid(), sid()
        self.pair(s1, s2, thread=self.thread(s2))
        self.pair(s2, s3, thread=self.thread(s3))
        self.assertTarget(s3, "stopped", via="cleared")

    def test_a_pair_that_loops_ends_the_chain(self):
        s1, t1 = self.asked(live=False)
        s2 = sid()
        self.pair(s1, s2, thread=self.thread(s2))
        self.pair(s2, s1, thread=t1)
        self.assertTarget(s2, "stopped", via="cleared")

    def test_the_left_session_opened_again_after_the_clear_and_still_held_by_the_clearing_process(self):
        s1, _ = self.asked(live=False)
        s2 = sid()
        self.pair(s1, s2, thread=self.thread(s2), at=tasks.stamp(time.time() - 60))
        _, proc = self.session(sid=s1, started=ms_ago(120))     # the clearing process, still on record for it
        self.assertTarget(s2, "stopped", via="cleared")
        self.end(proc)
        self.session(sid=s1, started=ms_ago(1))                 # its human opened it again
        self.assertTarget(s1, "running")
        self.assertTrue(self.asker(s1))

    def test_a_session_opened_again_and_cleared_again_goes_to_its_new_successor(self):
        s1, _ = self.asked(live=False)
        s2, s3 = sid(), sid()
        clearing = self.session(sid=s1, started=ms_ago(60))[1]
        self.session(sid=s2)
        tasks.cleared(s1, s2)                                    # the first clear
        self.assertTarget(s2, "running", via="cleared")
        self.end(clearing)
        time.sleep(0.01)
        self.session(sid=s1, started=ms_ago(0))                  # its human opened it again: rule 2
        self.assertTarget(s1, "running")
        self.session(sid=s3)
        tasks.cleared(s1, s3)                                    # and cleared it again: a new witnessed clear
        tasks.cleared(s1, s3)                                    # whose second writer changes nothing
        pair = self.state()["successors"][s1]
        self.assertEqual((pair["session"], pair["thread"]), (s3, None))
        self.assertTarget(s3, "running", via="cleared")
        self.assertTrue(self.asker(s3))
        self.ok("revise", "t1", "--class", "needed", session=s3)

    def test_a_pair_written_between_two_lines_of_a_call_is_read_by_the_second(self):
        s1, _ = self.asked()
        self.assign(s1, title="second")
        self.done("t1")
        self.done("t2")
        s2 = sid()
        self.session(sid=s2)
        time.sleep(0.01)
        lines = [self.line(act="shown", task=t, session=s1, keys=[t + ".1"]) for t in ("t1", "t2")]
        real = tasks.apply_line

        def between(line, memo=None):
            got = real(line, memo)
            if line["task"] == "t1":
                tasks.cleared(s1, s2)                            # a /clear lands between the two steps
            return got
        with mock.patch.object(tasks, "apply_line", side_effect=between):
            out = [json.loads(x) for x in self.ok("act", stdin="\n".join(lines) + "\n").splitlines()]
        self.assertEqual([v["keys"] for v in out], [["t1.1"], []], "the second marks against the new target")
        self.assertIsNone(self.state()["tasks"]["t2"]["outcomes"][0]["shown"])

    def test_a_session_that_took_the_left_ones_alias_is_no_successor(self):
        s1, _ = self.asked(live=False)
        s2, s9 = sid(), sid()
        self.pair(s1, s2, thread=self.thread(s2))
        self.thread(s9)
        self.session(sid=s9, name="alpha")
        self.assertTarget(s2, "stopped", via="cleared")
        self.assertFalse(self.asker(s9))

    def test_a_session_with_no_thread_is_its_own_asker_whatever_it_becomes(self):
        s1 = sid()
        self.assign(s1)
        self.assertIsNone(self.state()["tasks"]["t1"]["askers"][0]["thread"])
        self.assertTarget(s1, "gone")
        self.session(sid=s1)
        self.assertTarget(s1, "running")
        s2 = sid()
        self.thread(s1)                                         # later a member, then cleared
        self.pair(s1, s2, thread=self.thread(s2))
        self.session(sid=s2)
        self.assertTarget(s1, "running")
        self.assertFalse(self.asker(s2))
        self.assertFalse(self.asker(sid()), "a second session with no thread")

    def test_the_seat_before_and_a_fork_are_no_askers(self):
        s0, s1 = sid(), sid()
        self.thread(s1, sessions=[s0, s1])
        self.session(sid=s1)
        self.assign(s1)
        fork = sid()
        self.thread(fork)
        self.session(sid=fork)
        self.assertTrue(self.asker(s1))
        self.assertFalse(self.asker(s0), "a session that filled the seat before")
        self.assertFalse(self.asker(fork), "a fork is a thread of its own")

    def test_a_lane_b_session_whose_process_is_gone_and_records_that_cannot_be_read(self):
        s1, tid = self.asked(live=False)
        self.lane_b(s1)
        self.assertTarget(s1, "gone", runner="maws")
        self.assertIn("(run by MAWS)", self.ok("list"))
        v = json.loads(self.ok("done", "t1", "--wake").strip())
        self.assertEqual(v["told"], "maws")
        with open(os.path.join(sminos.root(), "session-records", s1 + ".json"), "w") as f:
            f.write("{not a record")
        self.assertEqual(self.target()["state"], "unknown")
        os.unlink(os.path.join(sminos.root(), "session-records", s1 + ".json"))
        with open(os.path.join(threads.store_dir(), tid + ".json"), "w") as f:
            f.write("{not a record")
        sminos.forget_caches()
        self.assertEqual(self.target()["state"], "unknown")

    def test_the_target_is_resolved_once_for_each_distinct_asker_of_a_call(self):
        s1, _ = self.asked()
        for n in range(4):
            self.assign(s1, title="more %d" % n)
        with mock.patch.object(tasks, "_describe", wraps=tasks._describe) as describe:
            self.ok("list", "--json")
        self.assertEqual(describe.call_count, 1)
        lines = "".join(self.line(act="done", task="t%d" % n, revision=1, text="", wake=None) + "\n"
                        for n in range(1, 6))
        with mock.patch.object(tasks, "_describe", wraps=tasks._describe) as describe:
            self.ok("act", stdin=lines)
        self.assertEqual(describe.call_count, 1, "one target memo for the call's lines")


# ------------------------------------------------------------ a real /clear


class ClearedPair(Board):
    NEW = "11111111-2222-4333-8444-555555555555"

    def setUp(self):
        super().setUp()
        self.old, self.proc = self.opened(started=int((time.time() - 30) * 1000))
        self.assign(self.old)
        self.env = {"CLAUDE_PID": str(self.proc.pid), "CLAUDE_CODE_SESSION_ID": self.NEW}

    def note(self):
        hook = os.path.join(os.path.dirname(HERE), "hooks", "smns-cleared.sh")
        subprocess.run([hook], input=json.dumps({"session_id": self.old, "reason": "clear",
                                                 "hook_event_name": "SessionEnd"}),
                       text=True, capture_output=True, env={**os.environ, "CLAUDE_PID": str(self.proc.pid)})
        self.peer_set(self.proc, sessionId=self.NEW)

    def record(self):
        self.hook(self.NEW, source="clear", env=self.env)

    def remind(self):
        return self.ok("remind", "--session", self.NEW, "--source", "clear", env=self.env)

    def test_the_record_hook_writes_the_pair_before_it_releases_the_alias(self):
        self.note()
        at_release = []
        real = sminos.release_alias

        def release(*a, **k):
            at_release.append(self.old in self.state()["successors"])
            return real(*a, **k)
        with mock.patch.object(sminos, "release_alias", side_effect=release):
            self.record()
        self.assertEqual(at_release, [True])
        pair = self.state()["successors"][self.old]
        self.assertEqual(pair["session"], self.NEW)
        self.assertEqual(threads.get(threads.thread_of(self.old)["thread"])["released"]["alias"], "alpha")
        self.assertEqual(self.target()["session"], self.NEW)

    def test_the_pair_is_written_once_whichever_hook_runs_first(self):
        for remind_first in (True, False):
            with self.subTest(remind_first=remind_first):
                if not remind_first:
                    self.fresh()     # setUp again: a session opened, its task assigned
                self.note()
                if remind_first:
                    self.remind()
                    first = self.state()["successors"][self.old]
                    self.record()
                else:
                    self.record()
                    first = self.state()["successors"][self.old]
                    self.remind()
                now = self.state()["successors"]
                self.assertEqual(list(now), [self.old])
                self.assertEqual((now[self.old]["session"], now[self.old]["at"]), (self.NEW, first["at"]),
                                 "the pair the first wrote, not replaced")
                self.ok("shown", "--session", self.NEW, "--keys", "", env=self.env)   # the start hook's second call
                self.assertEqual(self.state()["successors"][self.old]["thread"],
                                 threads.current_record(self.NEW, fresh=True)["thread"],
                                 "bound to the new session's thread by its own step")
                self.assertEqual(self.target()["session"], self.NEW)

    def test_remind_alone_writes_the_pair_when_the_record_hook_was_cut_short(self):
        self.note()
        out = self.remind()
        self.assertEqual(self.state()["successors"][self.old]["session"], self.NEW)
        self.assertIn("Tasks you assigned to the human: 1 open (1 blocking).", out)

    def held(self, seconds):
        """The store's lock held by another holder (its own open file) for `seconds`, from a thread."""
        lock = open(tasks.lock_path(), "a")
        fcntl.flock(lock, fcntl.LOCK_EX)

        def let_go():
            time.sleep(seconds)
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        th = threading.Thread(target=let_go)
        th.start()
        self.addCleanup(th.join)
        return th

    def test_remind_at_a_clear_waits_past_the_hooks_short_wait_to_write_the_pair(self):
        self.note()
        self.held(tasks.HOOK_LOCK_WAIT + 1)
        began = time.time()
        self.remind()
        self.assertGreater(time.time() - began, tasks.HOOK_LOCK_WAIT, "it waited")
        self.assertEqual(self.state()["successors"][self.old]["session"], self.NEW)

    def test_the_record_hook_writes_the_pair_past_its_own_deadline_and_still_releases_the_alias(self):
        """The record's timer (run_record's, here 1.5 s) is paused while the pair waits for the lock (2.5 s), so
        neither the pair nor the release after it is cut short."""
        import signal
        self.note()
        self.held(2.5)
        previous = signal.signal(signal.SIGALRM, sminos._record_expired)
        signal.setitimer(signal.ITIMER_REAL, 1.5)
        try:
            self.record()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        self.assertEqual(self.state()["successors"][self.old]["session"], self.NEW)
        self.assertEqual(threads.get(threads.thread_of(self.old)["thread"])["released"]["alias"], "alpha")

    def test_the_record_hook_keeps_the_releases_budget_after_waiting_for_the_board(self):
        """Through the hook's own entry (smns-record.sh, `sminos record`, run_record's deadline at 2 s): the board's
        lock held 3.5 s, and as it is let go the thread store's lock (which the release's journaled change on a
        record its human opened takes, until the record's deadline) held 1 s more. The pair waits out the first; the release still has the budget
        it had before the pair, so it waits out the second and the alias is released."""
        self.note()
        left_thread = threads.thread_of(self.old)["thread"]
        board = open(tasks.lock_path(), "a")
        fcntl.flock(board, fcntl.LOCK_EX)
        store = open(os.path.join(threads.store_dir(), ".lock"), "a")

        def let_go():
            time.sleep(3.5)
            fcntl.flock(store, fcntl.LOCK_EX)      # the hook is waiting for the board by now, past its own locks
            fcntl.flock(board, fcntl.LOCK_UN)
            time.sleep(1)
            fcntl.flock(store, fcntl.LOCK_UN)
        th = threading.Thread(target=let_go)
        th.start()
        self.addCleanup(board.close)
        self.addCleanup(store.close)
        payload = {"session_id": self.NEW, "transcript_path": os.path.join(self.home, "t-%s.jsonl" % self.NEW),
                   "cwd": self.root, "hook_event_name": "SessionStart", "source": "clear"}
        hook = os.path.join(os.path.dirname(HERE), "hooks", "smns-record.sh")
        subprocess.run([hook], input=json.dumps(payload), text=True, capture_output=True, timeout=60,
                       env={**os.environ, **self.env, "SMNS_RECORD_TIMEOUT": "2"})
        th.join()
        sminos.forget_caches()
        log = os.path.join(sminos.root(), "daemon.log")
        with open(log) if os.path.exists(log) else contextlib.nullcontext(io.StringIO()) as f:
            said = f.read()
        self.assertEqual(self.state()["successors"][self.old]["session"], self.NEW, said)
        self.assertEqual((threads.get(left_thread).get("released") or {}).get("alias"), "alpha", said)
        self.assertIsNotNone(threads.current_record(self.NEW, fresh=True), "the join after it, made: " + said)
        self.assertEqual(said, "", "nothing skipped")

    def run_hook(self, name, env=None):
        """One of the plugin's SessionStart hooks run as the engine runs it, on the new session's /clear payload."""
        payload = {"session_id": self.NEW, "transcript_path": os.path.join(self.home, "t-%s.jsonl" % self.NEW),
                   "cwd": self.root, "hook_event_name": "SessionStart", "source": "clear"}
        hook = os.path.join(os.path.dirname(HERE), "hooks", name)
        done = subprocess.run([hook], input=json.dumps(payload), text=True, capture_output=True, timeout=60,
                              env={**os.environ, **self.env, **(env or {})})
        sminos.forget_caches()
        return done

    def test_the_task_hook_before_the_join_and_the_record_hook_binds_the_pair_after_it(self):
        """The task hook's remind and shown both run before the record hook has joined the new session (no
        thread to bind to yet); the record hook's join makes the thread, and the pair is bound to it there: the
        successor that stops before its next task verb is still the target."""
        self.note()
        self.run_hook("smns-tasks.sh")
        pair = self.state()["successors"][self.old]
        self.assertEqual((pair["session"], pair["thread"]), (self.NEW, None), "no thread to bind to yet")
        self.run_hook("smns-record.sh")
        made = threads.current_record(self.NEW, fresh=True)
        self.assertIsNotNone(made, "the join made the new session's thread")
        self.assertEqual(self.state()["successors"][self.old]["thread"], made["thread"])
        self.assertEqual(self.target()["session"], self.NEW)

    def test_a_diagnostic_that_cannot_be_written_skips_neither_the_release_nor_the_join(self):
        self.note()
        with mock.patch.object(tasks, "cleared", side_effect=RuntimeError("the store")), \
                mock.patch.object(sminos, "daemon_log", side_effect=OSError("the log")):
            self.record()
        self.assertEqual(threads.get(threads.thread_of(self.old)["thread"])["released"]["alias"], "alpha")
        self.assertIsNotNone(threads.current_record(self.NEW, fresh=True), "the join after it")

    def test_shown_with_nothing_to_mark_or_bind_takes_no_lock(self):
        self.held(4)
        began = time.time()
        self.assertEqual(self.ok("shown", "--session", self.old, "--keys", ""), "\n")
        self.assertLess(time.time() - began, 2, "it read the store and stopped, the lock held elsewhere")

    def test_no_store_no_pair(self):
        os.unlink(self.path())
        self.note()
        self.record()
        self.remind()
        self.assertFalse(os.path.exists(self.path()), "nothing is made")


if __name__ == "__main__":
    unittest.main(verbosity=1)
