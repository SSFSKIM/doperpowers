#!/usr/bin/env python3
"""The question sheet's project log and end of life (plan docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md,
M6's Proves; I12; the composite's §11 and §3's lifetime).

- The projection (`sminos sheet log`): what the record owes the log, written under the session's writer, a question
  to the project the session is in, every later event of it to that project; run twice, or cut after its append,
  nothing twice; a question owed while the session is no member waits.
- Stop, resume, answer: one `question` and one `answered` with the real answer; the stop cleanup passes a sheet's
  question; a subagent's question and an answer accepted at a start are in the log.
- Removal closes what was open, also after projections that failed; the Stop hook projects.
- The daemon's sweep: a record whose session runs nowhere here, whose transcript is gone and which has not been
  touched for an hour, and one a /clear's note names, at once; nothing else.

Hermetic: HOME and SMINOS_HOME are temporary, fresh for each test (test_threads.Machine); sessions are `sleep`
processes with engine records the test writes.
Run: python3 -B sminos/tests/test_sheet_log.py   (ends `test_sheet_log: N passed`)
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import errno
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import sminos  # noqa: E402
from test_threads_stopped import HOOK, Rig  # noqa: E402

sheet = sminos.sibling_module("sminos_sheet")


def entry(question, labels=("Yes", "No")):
    return {"question": question, "options": [{"label": x} for x in labels]}


class Log(Rig):
    """A machine with sessions whose sheets are driven through the real step, as the mod orders it."""

    def setUp(self):
        super().setUp()
        self.daemon = sminos.daemon_module()
        self.keys = 0

    def step(self, sid, event):
        out = sheet.run_step(sid, json.dumps(dict(event, runner="terminal")).encode())
        self.assertTrue(out["ok"], out)
        return out

    def start(self, sid, source="startup"):
        return self.step(sid, {"event": "start", "start": {"source": source}})

    def ask(self, sid, call_id, entries=(), withdraw=(), asker="main"):
        call = {"callId": call_id, "asker": asker, "entries": list(entries)}
        if withdraw:
            call["withdraw"] = list(withdraw)
        return self.step(sid, {"event": "call", "call": call})

    def put(self, sid, *lines):
        out = []
        for x in lines:
            self.keys += 1
            out.append(dict({"v": 1, "key": "k-%08d" % self.keys, "by": "cli"}, **x))
        sheet.put(sid, "".join(json.dumps(x) + "\n" for x in out).encode(), wait=False)
        return [x["key"] for x in out]

    def answer(self, sid, id_, picks=(), text="", revision=1):
        line = {"kind": "answer", "id": id_, "revision": revision, "picks": list(picks)}
        if text:
            line["text"] = text
        return self.put(sid, line)

    def stop_hook(self, sid, cwd=None):
        """The Stop hook's `sminos record`, in this process."""
        sminos.forget_caches()
        sminos.cmd_record(None, {"session_id": sid, "cwd": cwd or self.root, "hook_event_name": "Stop",
                                 "transcript_path": sminos.transcript_path(sid), "last_assistant_message": ""})
        sminos.forget_caches()

    def project(self, sid, **k):
        sminos.forget_caches()
        try:
            return sheet.project_log(sid, **k)
        finally:
            sminos.forget_caches()

    def logged(self, sid, kind, p=None):
        return [e for e in self.own(sid, p) if e["kind"] == kind and str(e.get("src", "")).startswith("sheet:")]

    def questions(self, sid, p=None):
        return [(e["src"], e["text"], e["choices"], e["from"], e["to"]) for e in self.logged(sid, "question", p)]

    def answers(self, sid, p=None):
        return [(e["src"], e["text"], e.get("closed")) for e in self.logged(sid, "answered", p)]

    def state(self, sid):
        with open(os.path.join(sheet.record_dir(sid), "state.json")) as f:
            return json.load(f)

    def src(self, sid, id_):
        return "sheet:%s:%s" % (sid, id_)

    @contextlib.contextmanager
    def dies_after_its_append(self):
        """The projection killed after the log took its events and before its last replace: the replace that takes
        them off `log.owed` raises (the one recording destinations, before the append, goes through)."""
        real, seen = sheet._write_file, []

        def dies(rec, rel, data):
            if rel == "state.json":
                with open(os.path.join(rec, rel), "rb") as f:
                    if json.loads(data)["log"]["owed"] != json.load(f)["log"]["owed"]:
                        raise OSError("killed before its replace")
            return real(rec, rel, data)
        with mock.patch.object(sheet, "_write_file", side_effect=dies):
            yield seen

    def move(self, sid, project):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("join", project.name)
        self.assertEqual(code, 0, out)
        self.assertEqual(sminos.session_project(sid, sminos.launch_cwd(sid)).id, project.id, "moved")

    def moved_transcript(self, sid, root):
        """The session's transcript naming another launch directory: a session of that project."""
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-" + os.path.basename(root))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, sid + ".jsonl"), "a") as f:
            f.write(json.dumps({"type": "user", "sessionId": sid, "cwd": root, "permissionMode": "plan",
                                "message": {"role": "user", "content": "work"}}) + "\n")
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()


class Projection(Log):
    def test_stop_resume_answer_leaves_one_question_and_its_real_answer(self):
        sid, proc = self.opened()
        self.start(sid)
        added = self.ask(sid, "toolu_1", [entry("Ship today?")])
        self.assertEqual(added["effects"]["owed"], 1, "the step says the log is owed")
        self.stop_hook(sid)
        self.assertEqual(self.questions(sid), [(self.src(sid, "q1"), ["Ship today?"], ["Yes", "No"], "alpha", "host")])
        self.assertEqual(self.state(sid)["log"]["owed"], [])
        self.assertEqual(self.state(sid)["log"]["projects"], {"q1": self.p.id})
        self.end(proc)
        for _ in range(3):   # the thread sweep's stop pass, which closes today's open questions
            sminos.forget_caches()
            self.daemon.sweep_threads()
        self.assertIn("swept", sminos.threads_module().thread_of(sid))
        self.assertEqual(self.answers(sid), [], "the stop cleanup leaves a sheet question open")
        self.answer(sid, "q1", ["Yes"], "after the review")
        _, proc = self.live(sid=sid)
        started = self.start(sid, "resume")
        self.assertEqual(started["effects"]["owed"], 1)
        self.project(sid)
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), '"Ship today?" → Yes. Their text: "after the review"',
                                              None)])
        self.assertEqual(len(self.questions(sid)), 1)
        self.assertEqual(self.state(sid)["log"]["owed"], [])

    def test_a_projection_run_twice_or_cut_after_its_append_appends_nothing_again(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("One?"), entry("Two?")])
        with self.dies_after_its_append():
            with self.assertRaises(OSError):
                self.project(sid)
        self.assertEqual(len(self.questions(sid)), 2, "appended")
        self.assertEqual(len(self.state(sid)["log"]["owed"]), 2, "and still owed")
        self.assertEqual(self.project(sid), {"written": 2, "owed": 0})
        self.assertEqual(self.project(sid), {"written": 0, "owed": 0})
        self.assertEqual(len(self.questions(sid)), 2, "nothing twice")
        self.assertEqual(self.state(sid)["log"]["owed"], [])

    def test_the_projection_moves_the_records_seq_at_each_replace_and_changes_nothing_else(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("One?")])
        before = self.state(sid)
        self.project(sid)
        after = self.state(sid)
        self.assertEqual(after["seq"], before["seq"] + 2, "the destination recorded, then the events taken off")
        self.assertEqual(dict(after, seq=0, log=None), dict(before, seq=0, log=None))
        self.assertEqual(after["log"], {"next": before["log"]["next"], "owed": [], "projects": {"q1": self.p.id}})

    def test_a_question_owed_while_its_session_is_no_member_waits(self):
        sid, _ = self.session()   # a process the log holds no membership of
        self.transcript(sid)
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Wait?")])
        self.assertEqual(self.project(sid), {"written": 0, "owed": 1})
        self.assertEqual(self.questions(sid), [])
        self.reconcile()   # now a member
        self.assertEqual(self.project(sid), {"written": 1, "owed": 0})
        self.assertEqual([q[0] for q in self.questions(sid)], [self.src(sid, "q1")])

    def test_an_answer_goes_where_its_question_went_under_the_askers_writer(self):
        a, _ = self.opened()
        self.start(a)
        self.ask(a, "toolu_a", [entry("Where?")])
        self.project(a)
        other_root = self.repo("other")
        other = self.project_of(other_root)
        b, _ = self.session(root=other_root, name="beta")
        self.moved_transcript(b, other_root)
        self.reconcile(other)
        self.start(b)
        self.ask(b, "toolu_b", [entry("Theirs?")])
        self.project(b)
        self.assertEqual([q[0] for q in self.questions(b, other)], [self.src(b, "q1")])
        self.move(a, other)
        self.answer(a, "q1", ["Yes"])
        self.step(a, {"event": "drain"})
        self.ask(a, "toolu_a2", [entry("Here now?")])
        self.project(a)
        self.assertEqual(self.answers(a), [(self.src(a, "q1"), '"Where?" → Yes.', None)], "in the first project")
        self.assertEqual(self.answers(a, other), [], "none in the second")
        self.assertEqual([q[0] for q in self.questions(a, other)], [self.src(a, "q2")], "a new question goes there")
        self.assertEqual(self.answers(b, other), [], "the other session's q1 is untouched")
        self.assertEqual(self.state(a)["log"]["projects"], {"q1": self.p.id, "q2": other.id})

    def test_a_projection_cut_after_its_append_then_a_move_sends_nothing_of_the_question_elsewhere(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Where?")])
        with self.dies_after_its_append():
            with self.assertRaises(OSError):
                self.project(sid)
        self.assertEqual(self.state(sid)["log"]["projects"], {"q1": self.p.id}, "its destination recorded first")
        other = self.project_of(self.repo("other"))
        self.move(sid, other)
        self.answer(sid, "q1", ["Yes"])
        self.step(sid, {"event": "drain"})
        self.project(sid)
        self.assertEqual([q[0] for q in self.questions(sid)], [self.src(sid, "q1")])
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), '"Where?" → Yes.', None)])
        self.assertEqual(self.logged(sid, "question", other) + self.logged(sid, "answered", other), [],
                         "nothing of it in the second project")

    def test_two_projections_overlapping_a_move_send_a_question_to_one_project(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Where?")])
        other = self.project_of(self.repo("other"))
        real, inner = sminos.append_host, []

        def append(project, session, events):
            if not inner:
                inner.append(project.id)   # the session moves, and another projection runs, before this one appends
                self.move(sid, other)
                self.project(sid)
            return real(project, session, events)
        with mock.patch.object(sminos, "append_host", side_effect=append):
            self.project(sid)
        self.assertEqual([q[0] for q in self.questions(sid)], [self.src(sid, "q1")])
        self.assertEqual(self.logged(sid, "question", other), [], "never in the second project")
        self.assertEqual(self.state(sid)["log"], {"next": 2, "owed": [], "projects": {"q1": self.p.id}})

    def test_a_projection_that_outlives_its_record_changes_nothing_in_the_one_made_after_it(self, sid=None):
        sid = sid or self.opened()[0]
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Old one?"), entry("Old two?")])
        real, again = sminos.append_host, []

        def append(project, session, events):
            if not again:
                # Paused at its append: meanwhile the record is removed (its own closings written) and the session's
                # sheet made again, owing two questions of its own.
                again.append(1)
                sheet.remove_record(sid, cleared=True)
                self.start(sid)
                self.ask(sid, "toolu_2", [entry("New one?"), entry("New two?")])
                again.append(self.state(sid))
            return real(project, session, events)
        with mock.patch.object(sminos, "append_host", side_effect=append):
            self.project(sid)
        made = again[1]
        self.assertEqual(self.state(sid)["log"], made["log"], "the new record still owes its own")
        self.assertEqual(self.state(sid)["seq"], made["seq"])
        self.assertEqual([e["text"] for e in made["log"]["owed"]], [["New one?"], ["New two?"]])

    def test_a_record_made_again_on_the_inode_of_the_one_removed_is_another_to_a_projection(self):
        """A filesystem that gives the new directory the inode of the one removed (as ext4 does at once): the nonce
        tells them apart."""
        sid = self.opened()[0]
        rec = sheet.record_dir(sid)
        real = os.lstat

        def same_inode(path, *a, **k):
            st = real(path, *a, **k)
            return os.stat_result((st.st_mode, 4242) + tuple(st)[2:]) if path == rec else st
        with mock.patch.object(os, "lstat", side_effect=same_inode):
            self.start(sid)
            before = sheet.record_identity(rec, mint=True)
            sheet.remove_record(sid, cleared=True)
            self.start(sid)
            after = sheet.record_identity(rec)
            self.assertEqual(before[:2], after[:2], "the same device and inode")
            self.assertNotEqual(before, after)
            self.test_a_projection_that_outlives_its_record_changes_nothing_in_the_one_made_after_it(sid)

    def test_two_sessions_of_one_project_each_keep_their_own_q1(self):
        a, _ = self.opened()
        b, _ = self.opened(name="beta", charge="")
        for sid, pick in ((a, "Yes"), (b, "No")):
            self.start(sid)
            self.ask(sid, "toolu_%s" % sid[:4], [entry("Which?")])
            self.project(sid)
        for sid, pick in ((a, "Yes"), (b, "No")):
            self.answer(sid, "q1", [pick])
            self.step(sid, {"event": "drain"})
            self.project(sid)
        self.assertEqual(self.answers(a), [(self.src(a, "q1"), '"Which?" → Yes.', None)])
        self.assertEqual(self.answers(b), [(self.src(b, "q1"), '"Which?" → No.', None)])

    def test_a_subagents_question_and_an_answer_accepted_at_a_start_are_in_the_log(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Theirs?")], asker={"agentId": "a1", "name": "helper"})
        self.project(sid)
        self.assertEqual([q[0] for q in self.questions(sid)], [self.src(sid, "q1")])
        self.end(proc)
        self.answer(sid, "q1", ["No"])
        self.live(sid=sid)
        self.start(sid, "resume")
        self.project(sid)
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), '"Theirs?" → No.', None)])

    def test_dismissed_and_withdrawn_close_with_their_word(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("One?"), entry("Two?")])
        self.put(sid, {"kind": "dismiss", "id": "q1"})
        self.step(sid, {"event": "drain"})
        self.ask(sid, "toolu_2", withdraw=["q2"])
        self.project(sid)
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), "dismissed", "dismissed"),
                                             (self.src(sid, "q2"), "withdrawn", "withdrawn")])

    def test_the_command_projects_and_says_what_it_wrote(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("One?")])
        code, out = self.cli("sheet", "log", "--session", sid)
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out), {"session": sid, "written": 1, "owed": 0})
        self.assertEqual(len(self.questions(sid)), 1)
        code, out = self.cli("sheet", "log", "--session", "5eed0000-0000-4000-8000-0000000000ff")
        self.assertEqual(code, 3, out)


class StopHook(Log):
    HOOK = os.path.join(os.path.dirname(HERE), "hooks", "smns-record.sh")

    def test_the_record_hooks_stop_writes_what_a_session_in_no_project_owes_where_its_question_went(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Ship?")])
        self.project(sid)
        self.answer(sid, "q1", ["No"])
        self.step(sid, {"event": "drain"})
        # Its directory is no project any more: the hook's preflight finds no .smns and no repository above it.
        os.rename(os.path.join(self.root, ".git"), os.path.join(self.root, ".git-gone"))
        sminos.forget_caches()
        payload = {"session_id": sid, "cwd": self.root, "hook_event_name": "Stop", "last_assistant_message": "",
                   "transcript_path": sminos.transcript_path(sid)}
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "SMNS_INTERNAL",
                                                               "CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE_SESSION_ID")}
        p = subprocess.run(["bash", self.HOOK], input=json.dumps(payload), capture_output=True, text=True, env=env,
                           timeout=60)
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
        sminos.forget_caches()
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), '"Ship?" → No.', None)])
        self.assertEqual(self.state(sid)["log"]["owed"], [])


class StopCleanup(Log):
    def test_close_questions_closes_todays_and_passes_a_sheets(self):
        sid, proc = self.opened()
        sminos.append_host(self.p, sid, [{"kind": "question", "from": "alpha", "to": "host", "text": ["today's?"],
                                          "choices": [], "src": "toolu_q1"}])
        self.start(sid)
        self.ask(sid, "toolu_2", [entry("The sheet's?")])
        self.project(sid)
        self.end(proc)
        for _ in range(3):
            sminos.forget_caches()
            self.daemon.sweep_threads()
        closed = [(e["src"], e["closed"]) for e in self.own(sid) if e["kind"] == "answered"]
        self.assertEqual(closed, [("toolu_q1", "stopped")])


class Removal(Log):
    def test_a_removal_closes_what_was_open(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Open?"), entry("Answered?")])
        self.answer(sid, "q2", ["Yes"])
        self.step(sid, {"event": "drain"})
        self.project(sid)
        self.end(proc)
        sminos.forget_caches()
        sheet.remove(sid)
        self.assertEqual(self.answers(sid), [(self.src(sid, "q2"), '"Answered?" → Yes.', None),
                                             (self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])
        self.assertFalse(os.path.exists(sheet.record_dir(sid)))
        self.assertTrue(os.path.isfile(sheet.lock_path(sid)), "the lock file stays")

    def test_projections_that_failed_still_leave_the_question_and_its_closing_at_the_removal(self):
        sid, proc = self.opened()
        self.start(sid)
        with mock.patch.object(sminos, "append_host", side_effect=sminos.LogWriteFailed("the log refused")):
            self.ask(sid, "toolu_1", [entry("Kept?", ("A", "B"))])
            with self.assertRaises(sheet.LogFailed):
                self.project(sid)
            self.ask(sid, "toolu_2", withdraw=["q1"])
            with self.assertRaises(sheet.LogFailed):
                self.project(sid)
        self.assertEqual(self.questions(sid), [])
        self.end(proc)
        sminos.forget_caches()
        sheet.remove(sid)
        self.assertEqual(self.questions(sid), [(self.src(sid, "q1"), ["Kept?"], ["A", "B"], "alpha", "host")])
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), "withdrawn", "withdrawn")])

    def aside(self):
        root = sheet.sheet_root()
        return [n for n in os.listdir(root) if n.startswith(".removed-")
                and os.path.isfile(os.path.join(root, n, "state.json"))]

    def test_a_removal_whose_closings_the_log_refused_keeps_the_record_aside_until_they_are_written(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Open?")])
        self.end(proc)
        sminos.forget_caches()
        with mock.patch.object(sminos, "append_host", side_effect=sminos.LogWriteFailed("the log refused")):
            with self.assertRaises(sheet.Refused) as e:
                sheet.remove_record(sid)
        self.assertEqual(e.exception.code, 1)
        self.assertIn("the log refused", str(e.exception))
        self.assertFalse(sheet.has_record(sid), "removed")
        self.assertEqual(len(self.aside()), 1, "but kept aside, its log owed")
        self.assertEqual(sheet.finish_removed(), [], "not within its first minute: a removal elsewhere may hold it")
        self.assertEqual(len(self.aside()), 1)
        sminos.forget_caches()
        self.assertEqual(sheet.finish_removed(time.time() + 120), [])
        self.assertEqual(self.aside(), [], "written, then deleted")
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_detached_record_whose_state_cannot_be_read_is_kept_and_said(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Open?")])
        self.end(proc)
        sminos.forget_caches()
        real = sheet._read_json

        def eio(path):
            if os.path.basename(os.path.dirname(path)).startswith(sheet.REMOVED):
                raise OSError(errno.EIO, "input/output error")
            return real(path)
        with mock.patch.object(sheet, "_read_json", side_effect=eio):
            with self.assertRaises(sheet.Refused) as e:
                sheet.remove_record(sid)
            self.assertEqual(e.exception.code, 1)
            self.assertIn("input/output error", str(e.exception))
            self.assertEqual(len(self.aside()), 1, "kept aside, not deleted")
            why = sheet.finish_removed(time.time() + 120)
            self.assertEqual(len(why), 1, why)
            self.assertIn("input/output error", why[0])
            self.assertEqual(len(self.aside()), 1, "still kept")
        sminos.forget_caches()
        self.assertEqual(sheet.finish_removed(time.time() + 120), [])
        self.assertEqual(self.aside(), [])
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_leftover_that_fails_keeps_its_failure_to_itself(self):
        sids = []
        for name in ("alpha", "beta"):
            sid, proc = self.opened(name=name)
            self.start(sid)
            self.ask(sid, "toolu_1", [entry("Open?")])
            self.end(proc)
            sids.append(sid)
        sminos.forget_caches()
        with mock.patch.object(sminos, "append_host", side_effect=sminos.LogWriteFailed("the log refused")):
            for sid in sids:
                with self.assertRaises(sheet.Refused):
                    sheet.remove_record(sid)
        self.assertEqual(len(self.aside()), 2)
        real = sheet.project_log

        def first_fails(session, **k):
            if session == sids[0]:
                raise RuntimeError("something unforeseen")
            return real(session, **k)
        sminos.forget_caches()
        with mock.patch.object(sheet, "project_log", side_effect=first_fails):
            why = sheet.finish_removed(time.time() + 120)
        self.assertEqual(len(why), 1, why)
        self.assertIn("something unforeseen", why[0])
        self.assertEqual(len(self.aside()), 1, "the other written and deleted")
        self.assertEqual(self.answers(sids[1]), [(self.src(sids[1], "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_removal_refused_under_the_lock_publishes_no_closing(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Still mine?")])
        self.project(sid)
        self.end(proc)
        sminos.forget_caches()
        # Resumed between the removal's first look and its look under the lock.
        with mock.patch.object(sminos, "running_now", return_value={"sessionId": sid, "pid": 1}):
            with self.assertRaises(sheet.Refused) as e:
                sheet.remove_record(sid)
        self.assertEqual(e.exception.code, 2)
        self.assertEqual(self.answers(sid), [], "the question is open in the log")
        self.assertEqual([q["id"] for q in self.state(sid)["questions"]], ["q1"], "and in the record")

    def test_a_closing_whose_recorded_project_is_not_known_here_is_a_debt_kept(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Kept?")])
        self.project(sid)
        self.end(proc)
        sminos.forget_caches()
        real = sminos.known_project
        with mock.patch.object(sminos, "known_project", side_effect=lambda pid: None if pid == self.p.id else real(pid)):
            with self.assertRaises(sheet.Refused) as e:
                sheet.remove_record(sid)
            self.assertIn("is not known here", str(e.exception))
            self.assertEqual(len(self.aside()), 1, "kept aside")
            self.assertEqual(len(sheet.finish_removed(time.time() + 120)), 1, "still owed while its project is unknown")
        sminos.forget_caches()
        self.assertEqual(sheet.finish_removed(time.time() + 120), [])
        self.assertEqual(self.aside(), [])
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_removal_of_a_session_that_was_never_a_member_drops_what_it_owed(self):
        sid, _ = self.session()
        self.transcript(sid)
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Nobody's?")])
        self.stop_all()
        sheet.remove(sid)
        self.assertFalse(os.path.exists(sheet.record_dir(sid)))
        self.assertEqual(self.logged(sid, "question"), [])


class ClearsRemoval(Log):
    """R1: the record a /clear left is removed by the mod (`sheet remove --cleared`, at the session's end, again at
    the next start), on the identity it witnessed at the clear (`sheet witness`), so a retry delayed behind a start
    in flight never removes a record a resume of the left session made since."""

    def asked_and_stopped(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Still open?")])
        self.end(proc)
        return sid

    def witness(self, sid):
        code, out = self.cli("sheet", "witness", "--session", sid)
        return code, out.strip()

    def test_the_witness_is_the_records_identity_minted_if_none_is(self):
        sid = self.asked_and_stopped()
        rec = sheet.record_dir(sid)
        self.assertEqual(sheet.record_identity(rec)[2], "", "no reader has bound to it yet")
        code, out = self.witness(sid)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, "%d:%d:%s" % sheet.record_identity(rec))
        self.assertRegex(out, r"^[0-9]+:[0-9]+:[0-9a-f]{32}$")
        self.assertEqual(self.witness(sid), (0, out), "minted once")
        sheet.remove_record(sid, cleared=True)
        self.assertEqual(self.witness(sid)[0], sheet.EXIT_NO_SHEET)

    def test_a_clears_removal_without_a_witness_removes_nothing(self):
        sid = self.asked_and_stopped()
        code, out = self.cli("sheet", "remove", "--session", sid, "--cleared")
        self.assertEqual(code, 2, out)
        self.assertIn("--witness", out)
        self.assertTrue(os.path.isfile(os.path.join(sheet.record_dir(sid), "state.json")))

    def test_a_clears_removal_removes_the_record_it_witnessed_and_no_later_one(self):
        sid = self.asked_and_stopped()
        _, witnessed = self.witness(sid)
        # The removal waits behind a start in flight; meanwhile the left session's sheet goes (the daemon's sweep of
        # the clear's note) and a resume of it elsewhere makes another, which asks.
        sheet.remove_record(sid, cleared=True)
        self.start(sid, source="resume")
        self.ask(sid, "toolu_2", [entry("Asked after the clear?")])
        code, out = self.remove_cleared(sid, witnessed, os.getpid())
        self.assertEqual(code, 2, out)
        self.assertIn("not the record the removal was decided on", out)
        self.assertEqual([q["question"] for q in self.state(sid)["questions"]], ["Asked after the clear?"])
        # The record it witnessed is removed.
        _, again = self.witness(sid)
        code, out = self.remove_cleared(sid, again, os.getpid())
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(sheet.record_dir(sid)))

    def remove_cleared(self, sid, witnessed, clearing):
        return self.cli("sheet", "remove", "--session", sid, "--cleared", "--witness", witnessed,
                        "--clearing", str(clearing))

    def test_a_clears_retry_keeps_a_record_a_resume_in_another_process_holds(self):
        """The record a /clear left, witnessed; the clearing process still on record as running the session left,
        and a resume of it in another process holding the same record: the delayed retry keeps it. The clearing
        process alone does not keep it."""
        sid, clearing = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Still open?")])
        _, witnessed = self.witness(sid)
        _, resumed = self.session(sid=sid)
        code, out = self.remove_cleared(sid, witnessed, clearing.pid)
        self.assertEqual(code, 2, out)
        self.assertIn("runs in another process", out)
        self.assertEqual([q["question"] for q in self.state(sid)["questions"]], ["Still open?"])
        self.end(resumed)
        code, out = self.remove_cleared(sid, witnessed, clearing.pid)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(sheet.record_dir(sid)))

    def test_a_clears_removal_whose_liveness_cannot_be_told_keeps_the_record(self):
        sid, clearing = self.opened()
        self.start(sid)
        _, witnessed = self.witness(sid)
        code, out = self.cli("sheet", "remove", "--session", sid, "--cleared", "--witness", witnessed)
        self.assertEqual(code, 2, out)
        self.assertIn("--clearing", out)
        # An engine session record that cannot be read may be a resume's.
        _, other = self.session()
        with open(self.peer_path(other.pid), "w") as f:
            f.write("{not json")
        code, out = self.remove_cleared(sid, witnessed, clearing.pid)
        self.assertEqual(code, 2, out)
        self.assertIn("could not be told", out)
        self.assertTrue(os.path.isfile(os.path.join(sheet.record_dir(sid), "state.json")))

    def test_a_witness_that_is_no_identity_removes_nothing(self):
        sid = self.asked_and_stopped()
        for bad in ("", "1:2", "1:2:" + "0" * 31, "x:2:" + "0" * 32):
            with self.subTest(bad=bad):
                code, out = self.remove_cleared(sid, bad, os.getpid())
                self.assertEqual(code, 2, out)
                self.assertTrue(os.path.isfile(os.path.join(sheet.record_dir(sid), "state.json")))


class Sweep(Log):
    def aged(self, sid, seconds):
        t = time.time() - seconds
        os.utime(os.path.join(sheet.record_dir(sid), "state.json"), (t, t))

    def transcript_gone(self, sid):
        os.unlink(sminos.transcript_path(sid))
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()

    def sweep(self):
        sminos.forget_caches()
        self.daemon.sweep_sheets()
        sminos.forget_caches()

    def asked_and_stopped(self):
        sid, proc = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Still open?")])
        self.end(proc)
        return sid

    def exists(self, sid):
        return os.path.isfile(os.path.join(sheet.record_dir(sid), "state.json"))

    def test_a_stopped_sessions_record_goes_once_its_transcript_is_gone_and_an_hour_passed(self):
        sid = self.asked_and_stopped()
        self.aged(sid, 2 * 3600)
        self.sweep()
        self.assertTrue(self.exists(sid), "its transcript is still there")
        self.transcript_gone(sid)
        self.aged(sid, 3000)
        self.sweep()
        self.assertTrue(self.exists(sid), "touched within the hour")
        self.aged(sid, 3700)
        self.sweep()
        self.assertFalse(self.exists(sid))
        self.assertTrue(os.path.isfile(sheet.lock_path(sid)), "no lock file is removed")
        self.assertEqual([q[0] for q in self.questions(sid)], [self.src(sid, "q1")])
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_an_old_sheet_survives_a_listing_of_transcripts_that_failed_for_a_moment(self):
        sid = self.asked_and_stopped()
        self.aged(sid, 3700)
        real_scandir, real_listdir = os.scandir, os.listdir
        projects = os.path.join(os.environ["HOME"], ".claude", "projects")

        def failing(fn):
            def call(path=".", *a, **k):
                if os.path.realpath(str(path)) == os.path.realpath(projects):
                    raise OSError(5, "input/output error")
                return fn(path, *a, **k)
            return call
        with mock.patch.object(os, "scandir", side_effect=failing(real_scandir)):
            self.sweep()
        self.assertTrue(self.exists(sid), "the index's listing failed: its transcript is still on disk")
        with mock.patch.object(os, "scandir", side_effect=failing(real_scandir)), \
                mock.patch.object(os, "listdir", side_effect=failing(real_listdir)):
            self.sweep()
        self.assertTrue(self.exists(sid), "no listing at all: absence unknown, nothing removed")
        self.assertEqual(self.answers(sid), [])

    def note(self, sid, age=0):
        """The engine's SessionEnd of a /clear that left `sid`, through the hook, `age` seconds ago."""
        _, proc = self.session(name="beta")
        got = subprocess.run([HOOK], input=json.dumps({"session_id": sid, "reason": "clear",
                                                       "hook_event_name": "SessionEnd"}),
                             text=True, capture_output=True, env={**os.environ, "CLAUDE_PID": str(proc.pid)})
        self.assertEqual((got.returncode, got.stdout, got.stderr), (0, "", ""))
        note = sminos.cleared_note_path(proc.pid)
        t = time.time() - age
        os.utime(note, (t, t))
        return note, proc

    def witnessed(self, note):
        with open(os.path.splitext(note)[0] + ".sheet") as f:
            return f.read()

    def test_a_clears_note_stays_until_the_sheet_it_names_is_removed(self):
        sid = self.asked_and_stopped()
        self.aged(sid, 30)
        note, proc = self.note(sid)
        self.end(proc)   # the process that cleared is gone: its note is the sweep's only record of the /clear
        import fcntl
        with open(sheet.lock_path(sid), "a") as lf, mock.patch.object(sheet, "LOCK_WAIT_S", 0.2):
            fcntl.flock(lf, fcntl.LOCK_EX)
            self.sweep()
            self.daemon.sweep_cleared()
            fcntl.flock(lf, fcntl.LOCK_UN)
        self.assertTrue(self.exists(sid), "busy: not removed")
        self.assertTrue(os.path.exists(note), "and its note kept")
        self.sweep()
        self.assertFalse(self.exists(sid))
        self.daemon.sweep_cleared()
        self.assertFalse(os.path.exists(note), "then the note goes")

    def test_a_daemons_removal_looks_again_under_the_lock(self):
        sid = self.asked_and_stopped()
        self.aged(sid, 30)
        self.note(sid)
        with mock.patch.object(sminos, "running_now", return_value={"sessionId": sid, "pid": 1}):
            self.sweep()
        self.assertTrue(self.exists(sid), "resumed while the sweep decided: it stays")
        self.assertEqual(self.answers(sid), [])

    def test_a_running_sessions_record_stays_whatever_else_holds(self):
        sid, _ = self.opened()
        self.start(sid)
        self.transcript_gone(sid)
        self.aged(sid, 2 * 3600)
        self.sweep()
        self.assertTrue(self.exists(sid))

    def test_a_record_a_clears_note_names_goes_at_once(self):
        sid = self.asked_and_stopped()
        note, _ = self.note(sid)
        self.assertEqual(self.witnessed(note), "%d:%d:%s\n" % sheet.record_identity(sheet.record_dir(sid)),
                         "the record the note witnessed")
        self.sweep()
        self.assertFalse(self.exists(sid), "transcript there, touched now: a /clear's note is enough")
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_note_binds_the_record_it_witnessed_and_no_other(self):
        sid = self.asked_and_stopped()
        note, proc = self.note(sid, age=2)
        # Removed, and the session's sheet made again (a resume that stopped): within the note's allowance, and
        # untouched since, but not the record the note saw.
        sheet.remove_record(sid, cleared=True)
        self.start(sid)
        self.ask(sid, "toolu_2", [entry("Made after the note?")])
        self.sweep()
        self.assertTrue(self.exists(sid), "a replacement record is not the note's")
        self.end(proc)
        self.daemon.sweep_cleared()
        self.assertEqual(os.listdir(os.path.dirname(note)), [])
        self.assertFalse(os.path.exists(note), "the note names no record it witnessed: it goes once its process is")

    def test_a_note_that_witnessed_no_record_authorizes_nothing(self):
        sid, proc = self.opened()
        note, _ = self.note(sid)     # the /clear before the session asked anything: no record then
        self.assertFalse(os.path.exists(os.path.splitext(note)[0] + ".sheet"))
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("Asked after?")])
        self.end(proc)
        self.sweep()
        self.assertTrue(self.exists(sid))

    def test_notes_that_disagree_on_the_record_authorize_nothing(self):
        sid = self.asked_and_stopped()
        self.note(sid)
        other, _ = self.note(sid)
        with open(os.path.splitext(other)[0] + ".sheet", "w") as f:
            f.write("1:2:%s\n" % ("0" * 32))
        self.sweep()
        self.assertTrue(self.exists(sid))

    def test_a_sweep_without_the_transcripts_own_path_keeps_the_record(self):
        sid = self.asked_and_stopped()
        self.transcript_gone(sid)
        self.aged(sid, 3700)
        os.unlink(sminos.launch_cache_path(sid))
        self.sweep()
        self.assertTrue(self.exists(sid), "where its transcript was is not known: absence is not established")

    def test_a_sheet_made_again_between_the_sweeps_decision_and_its_lock_stays(self):
        sid = self.asked_and_stopped()
        self.transcript_gone(sid)
        self.aged(sid, 3700)
        real = sminos.transcript_confirmed_gone

        def replaced_meanwhile(session):
            gone = real(session)
            # Decided gone; before the removal takes the lock, the session's sheet is removed and made again.
            sheet.remove_record(sid, cleared=True)
            self.start(sid)
            self.ask(sid, "toolu_2", [entry("Asked again?")])
            return gone
        with mock.patch.object(sminos, "transcript_confirmed_gone", side_effect=replaced_meanwhile):
            self.sweep()
        self.assertTrue(self.exists(sid), "the record made again is not the one the sweep decided on")
        self.assertEqual([q["question"] for q in self.state(sid)["questions"]], ["Asked again?"])

    def test_a_sheet_touched_between_the_sweeps_decision_and_its_lock_stays(self):
        sid = self.asked_and_stopped()
        self.transcript_gone(sid)
        self.aged(sid, 3700)
        real = sminos.transcript_confirmed_gone

        def touched_meanwhile(session):
            gone = real(session)
            self.ask(sid, "toolu_2", [entry("One more?")])
            return gone
        with mock.patch.object(sminos, "transcript_confirmed_gone", side_effect=touched_meanwhile):
            self.sweep()
        self.assertTrue(self.exists(sid), "touched since the decision: no longer an hour quiet")
        self.assertEqual(len(self.state(sid)["questions"]), 2)

    def test_a_transcript_restored_between_the_sweeps_decision_and_its_lock_keeps_the_sheet(self):
        sid = self.asked_and_stopped()
        path = sminos.transcript_path(sid)
        with open(path) as f:
            kept = f.read()
        self.transcript_gone(sid)
        self.aged(sid, 3700)
        real, calls = sminos.transcript_confirmed_gone, []

        def restored_meanwhile(session):
            gone = real(session)
            if not calls:
                # Decided gone; before the removal takes the lock, the transcript is back (a resume that wrote no
                # state, so the record's mtime is the one the sweep read).
                with open(path, "w") as f:
                    f.write(kept)
            calls.append(gone)
            return gone
        with mock.patch.object(sminos, "transcript_confirmed_gone", side_effect=restored_meanwhile):
            self.sweep()
        self.assertEqual(calls, [True, False], "looked at again under the lock")
        self.assertTrue(self.exists(sid), "its transcript is back: the sheet stays")
        self.assertEqual(self.answers(sid), [])

    def test_a_clears_note_whose_record_cannot_be_compared_is_kept_with_its_witness(self):
        sid = self.asked_and_stopped()
        note, proc = self.note(sid)
        self.end(proc)
        witness = os.path.splitext(note)[0] + ".sheet"
        nonce = os.path.join(sheet.record_dir(sid), sheet.INCARNATION)
        real = open

        def eio(path, *a, **k):
            if str(path) == nonce:
                raise OSError(errno.EIO, "input/output error")
            return real(path, *a, **k)
        with mock.patch("builtins.open", side_effect=eio):
            self.sweep()
            self.daemon.sweep_cleared()
        self.assertTrue(self.exists(sid), "its identity not read: no removal")
        self.assertTrue(os.path.exists(note) and os.path.exists(witness), "not known to differ: both kept")
        self.sweep()
        self.assertFalse(self.exists(sid), "read on the next pass: the /clear is finished")
        self.daemon.sweep_cleared()
        self.assertFalse(os.path.exists(note) or os.path.exists(witness))

    def test_a_clears_witness_that_cannot_be_read_keeps_the_note_for_a_later_pass(self):
        sid = self.asked_and_stopped()
        note, proc = self.note(sid)
        self.end(proc)
        witness = os.path.splitext(note)[0] + ".sheet"
        real = open

        def eio(path, *a, **k):
            if str(path) == witness:
                raise OSError(errno.EIO, "input/output error")
            return real(path, *a, **k)
        with mock.patch("builtins.open", side_effect=eio):
            self.sweep()
            self.daemon.sweep_cleared()
        self.assertTrue(self.exists(sid), "no witness read: no removal")
        self.assertTrue(os.path.exists(note) and os.path.exists(witness), "unknown is not absent: both kept")
        self.sweep()
        self.assertFalse(self.exists(sid), "read on the next pass: the /clear is finished")
        self.daemon.sweep_cleared()
        self.assertFalse(os.path.exists(note) or os.path.exists(witness))

    def nonce_holds(self, sid, data):
        """The record's `.incarnation` as an unclean stop can leave it (a link made, its bytes not written)."""
        with open(os.path.join(sheet.record_dir(sid), sheet.INCARNATION), "wb") as f:
            f.write(data)

    def test_a_record_whose_nonce_is_not_one_is_never_removed_on_its_inode_alone(self):
        """R5: an identity is the directory with the minted 32 hex digits; an empty, cut, overlong or undecodable
        `.incarnation` is no identity, and the sweep keeps the record (and does not fail on it)."""
        for data in (b"", b"0123456789abcdef", b"0" * 32 + b"\n" + b"x" * 64, b"\xff" * 32):
            with self.subTest(data=data[:20]):
                sid = self.asked_and_stopped()
                self.transcript_gone(sid)
                self.aged(sid, 3700)
                sheet.record_identity(sheet.record_dir(sid), mint=True)
                self.nonce_holds(sid, data)
                self.assertIsNone(sheet.record_identity(sheet.record_dir(sid))[2])
                self.sweep()
                self.assertTrue(self.exists(sid), "no identity: kept")
                self.assertEqual(self.answers(sid), [])

    def test_an_identity_is_compared_three_ways(self):
        n, m = "a" * 32, "b" * 32
        same = sheet.same_record
        self.assertIs(same((1, 2, n), (1, 2, n)), True)
        self.assertIs(same((1, 2, m), (1, 2, n)), False, "another nonce")
        self.assertIs(same((1, 3, n), (1, 2, n)), False, "another directory")
        self.assertIs(same(None, (1, 2, n)), False, "no record there")
        self.assertIs(same((1, 2, ""), (1, 2, n)), False, "a nonce is never taken away: a record without is another")
        self.assertIsNone(same((1, 2, None), (1, 2, n)), "its nonce not read")
        self.assertIsNone(same((1, 2, n), (1, 2, None)), "the witness holds none")
        self.assertIsNone(same((1, 2, ""), (1, 2, "")), "neither minted: the inode alone tells nothing")

    def test_a_removal_witnessed_on_a_record_whose_nonce_cannot_be_read_now_keeps_it(self):
        sid = self.asked_and_stopped()
        rec = sheet.record_dir(sid)
        identity = sheet.record_identity(rec, mint=True)
        self.nonce_holds(sid, b"")
        with self.assertRaises(sheet.Refused) as e:
            sheet.remove_record(sid, witnessed=identity)
        self.assertEqual(e.exception.code, 2)
        self.assertIn("could not be told", str(e.exception))
        self.assertTrue(self.exists(sid))

    def in_config_dir(self, sid):
        """The session's transcript under a config dir of its own, recorded for it (config-dirs/), as its
        launch record names it."""
        cfg = os.path.join(self.home, "cfg-other")
        d = os.path.join(cfg, "projects", "p-work")
        os.makedirs(d)
        to = os.path.join(d, sid + ".jsonl")
        os.rename(sminos.transcript_path(sid), to)
        for path, value in ((sminos.config_dir_path(sid), {"configDir": cfg}),
                            (sminos.launch_cache_path(sid), {"transcript": to, "size": os.path.getsize(to),
                                                             "launch": self.root})):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(value, f)
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()
        self.assertEqual(sminos.transcript_path(sid, fresh=True), to)
        return cfg, to

    def moved_to_a_registered_dir(self, sid):
        """The engine moved the session's transcript under a config dir known only by its registration
        (config-dirs/), while its launch cache still names where it was."""
        cfg = os.path.join(self.home, "cfg-moved")
        d = os.path.join(cfg, "projects", "p-elsewhere")
        os.makedirs(d)
        to = os.path.join(d, sid + ".jsonl")
        os.rename(sminos.transcript_path(sid), to)
        path = sminos.config_dir_path(sid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"configDir": cfg}, f)
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()
        return path, to

    def test_a_registry_that_could_not_be_read_whole_establishes_no_absence(self):
        """R3: the config dirs a removal looks in are the registry read whole; a listing of it that fails, or a
        registration that cannot be read, is no answer, and the sheet stays."""
        sid = self.asked_and_stopped()
        registration, to = self.moved_to_a_registered_dir(sid)
        self.aged(sid, 3700)
        registry = os.path.dirname(registration)
        real_listdir, real_open = os.listdir, open

        def listing_fails(path=".", *a, **k):
            if os.path.realpath(str(path)) == os.path.realpath(registry):
                raise OSError(errno.EIO, "input/output error")
            return real_listdir(path, *a, **k)

        def reading_fails(path, *a, **k):
            if str(path) == registration:
                raise OSError(errno.EIO, "input/output error")
            return real_open(path, *a, **k)
        for patch in (mock.patch.object(os, "listdir", side_effect=listing_fails),
                      mock.patch("builtins.open", side_effect=reading_fails)):
            with self.subTest(patch=patch.attribute), patch:
                sminos.forget_caches()
                self.assertFalse(sminos.transcript_confirmed_gone(sid))
                self.sweep()
                self.assertTrue(self.exists(sid), "its transcript is on disk, in the dir the registry names")
        sminos.forget_caches()
        self.assertFalse(sminos.transcript_confirmed_gone(sid), "read whole, the registry finds it")
        os.unlink(to)
        sminos.forget_caches()
        self.assertTrue(sminos.transcript_confirmed_gone(sid), "and then gone")

    def test_the_duty_keeps_a_sheet_whose_transcript_one_listing_missed_in_its_own_config_dir(self):
        sid = self.asked_and_stopped()
        cfg, to = self.in_config_dir(sid)
        self.aged(sid, 3700)
        real = os.scandir
        projects = os.path.realpath(os.path.join(cfg, "projects"))

        def failing(path=".", *a, **k):
            if os.path.realpath(str(path)) == projects:
                raise OSError(5, "input/output error")
            return real(path, *a, **k)
        for _ in range(2):   # the hour of the miss, and the one after
            sminos._TINDEX.at = None
            sminos._TINDEXES.clear()
            sminos.forget_caches()
            with mock.patch.object(os, "scandir", side_effect=failing), \
                    mock.patch.object(self.daemon, "_OVERRIDES_SWEPT", 0.0):
                self.daemon.override_duty()
            self.assertTrue(self.exists(sid), "its transcript is on disk")
            self.assertTrue(os.path.isfile(sminos.launch_cache_path(sid)), "where it is stays known while the sheet does")
            self.assertTrue(os.path.isfile(sminos.config_dir_path(sid)))
        with open(to) as f:
            self.assertIn(sid, f.read())
        self.assertEqual(self.answers(sid), [])

    def test_a_record_touched_after_its_clears_note_is_the_sessions_again(self):
        sid = self.asked_and_stopped()
        self.note(sid, age=600)   # the /clear ten minutes ago; the left session resumed elsewhere since
        self.sweep()
        self.assertTrue(self.exists(sid), "resumed and touched since: its transcript's rule holds")

    def cleared_quietly(self, sid, note_age=600):
        """A /clear `note_age` seconds ago, of a sheet and a transcript last written before it."""
        note, proc = self.note(sid, age=note_age)
        self.aged(sid, note_age + 300)
        t = time.time() - note_age - 300
        os.utime(sminos.transcript_path(sid), (t, t))
        return note, proc

    def test_a_clears_note_is_not_believed_over_a_listing_of_transcripts_that_failed(self):
        """R2: whether the transcript was written since the note is read past the index, whose listing that fails
        reads as no transcript: a resume of the session left, which wrote it, keeps the sheet."""
        sid = self.asked_and_stopped()
        path = sminos.transcript_path(sid)
        self.cleared_quietly(sid)
        os.utime(path)   # written since the note: the session left was resumed, and stopped
        real = os.scandir
        projects = os.path.realpath(os.path.join(os.environ["HOME"], ".claude", "projects"))

        def failing(p=".", *a, **k):
            if os.path.realpath(str(p)) == projects:
                raise OSError(errno.EIO, "input/output error")
            return real(p, *a, **k)
        with mock.patch.object(os, "scandir", side_effect=failing):
            self.sweep()
        self.assertTrue(self.exists(sid), "its transcript was written after the note")
        self.assertEqual(self.answers(sid), [])

    def test_a_clears_note_is_looked_at_again_under_the_lock(self):
        """R2: a transcript written between the sweep's decision on a note and its removal's lock keeps the sheet."""
        sid = self.asked_and_stopped()
        path = sminos.transcript_path(sid)
        self.cleared_quietly(sid)
        real, calls = self.daemon._cleared_sheet, []

        def resumed_meanwhile(*a):
            got = real(*a)
            if not calls:
                os.utime(path)   # decided; before the removal takes the lock, a resume writes the transcript
            calls.append(got)
            return got
        with mock.patch.object(self.daemon, "_cleared_sheet", side_effect=resumed_meanwhile):
            self.sweep()
        self.assertEqual(calls, [True, False], "looked at again under the lock")
        self.assertTrue(self.exists(sid))
        self.sweep()
        self.assertTrue(self.exists(sid), "and the note describes it no more")

    def test_a_clears_note_still_removes_the_quiet_sheet_it_names(self):
        sid = self.asked_and_stopped()
        self.cleared_quietly(sid)
        self.sweep()
        self.assertFalse(self.exists(sid))
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_sheet_a_quick_resume_made_again_within_a_minute_of_the_note_is_not_the_notes(self):
        sid = self.asked_and_stopped()
        self.note(sid, age=30)   # the record was made again 30 s after the /clear, by a resume of the session left
        self.sweep()
        self.assertTrue(self.exists(sid))

    def test_the_daemons_duty_sweeps_them_on_its_spacing(self):
        sid = self.asked_and_stopped()
        self.transcript_gone(sid)
        self.aged(sid, 2 * 3600)
        with mock.patch.object(self.daemon, "_OVERRIDES_SWEPT", time.time()):
            self.daemon.override_duty()
            self.assertTrue(self.exists(sid), "not before its spacing")
        with mock.patch.object(self.daemon, "_OVERRIDES_SWEPT", 0.0):
            self.daemon.override_duty()
        self.assertFalse(self.exists(sid))


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=1).result
    ok = r.wasSuccessful()
    print("test_sheet_log: %d %s" % (r.testsRun, "passed" if ok else "run, %d failed" % (len(r.failures) + len(r.errors))))
    sys.exit(0 if ok else 1)
