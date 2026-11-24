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
import json
import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import sminos  # noqa: E402
from test_threads_stopped import Rig  # noqa: E402

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
        real = sheet._write_file

        def dies(rec, rel, data):
            if rel == "state.json":
                raise OSError("killed before its replace")
            return real(rec, rel, data)
        with mock.patch.object(sheet, "_write_file", side_effect=dies):
            with self.assertRaises(OSError):
                self.project(sid)
        self.assertEqual(len(self.questions(sid)), 2, "appended")
        self.assertEqual(len(self.state(sid)["log"]["owed"]), 2, "and still owed")
        self.assertEqual(self.project(sid), {"written": 2, "owed": 0})
        self.assertEqual(self.project(sid), {"written": 0, "owed": 0})
        self.assertEqual(len(self.questions(sid)), 2, "nothing twice")
        self.assertEqual(self.state(sid)["log"]["owed"], [])

    def test_the_projection_moves_the_records_seq_and_changes_nothing_else(self):
        sid, _ = self.opened()
        self.start(sid)
        self.ask(sid, "toolu_1", [entry("One?")])
        before = self.state(sid)
        self.project(sid)
        after = self.state(sid)
        self.assertEqual(after["seq"], before["seq"] + 1)
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
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": a}):
            code, out = self.cli("join", other.name)
        self.assertEqual(code, 0, out)
        self.assertEqual(sminos.session_project(a, sminos.launch_cwd(a)).id, other.id, "moved")
        self.answer(a, "q1", ["Yes"])
        self.step(a, {"event": "drain"})
        self.ask(a, "toolu_a2", [entry("Here now?")])
        self.project(a)
        self.assertEqual(self.answers(a), [(self.src(a, "q1"), '"Where?" → Yes.', None)], "in the first project")
        self.assertEqual(self.answers(a, other), [], "none in the second")
        self.assertEqual([q[0] for q in self.questions(a, other)], [self.src(a, "q2")], "a new question goes there")
        self.assertEqual(self.answers(b, other), [], "the other session's q1 is untouched")
        self.assertEqual(self.state(a)["log"]["projects"], {"q1": self.p.id, "q2": other.id})

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

    def test_a_removal_whose_projection_fails_leaves_the_record(self):
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
        self.assertTrue(os.path.isfile(os.path.join(sheet.record_dir(sid), "state.json")), "the sheet stays")
        sheet.remove_record(sid)
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

    def test_a_running_sessions_record_stays_whatever_else_holds(self):
        sid, _ = self.opened()
        self.start(sid)
        self.transcript_gone(sid)
        self.aged(sid, 2 * 3600)
        self.sweep()
        self.assertTrue(self.exists(sid))

    def test_a_record_a_clears_note_names_goes_at_once(self):
        sid = self.asked_and_stopped()
        _, proc = self.session(name="beta")
        note = os.path.join(sminos.root(), sminos.CLEARED, "%d.json" % proc.pid)
        os.makedirs(os.path.dirname(note), exist_ok=True)
        with open(note, "w") as f:
            json.dump({"session_id": sid, "reason": "clear", "hook_event_name": "SessionEnd"}, f)
        self.sweep()
        self.assertFalse(self.exists(sid), "transcript there, touched now: a /clear's note is enough")
        self.assertEqual(self.answers(sid), [(self.src(sid, "q1"), sheet.LOG_REMOVED, "removed")])

    def test_a_record_touched_after_its_clears_note_is_the_sessions_again(self):
        sid = self.asked_and_stopped()
        _, proc = self.session(name="beta")
        note = os.path.join(sminos.root(), sminos.CLEARED, "%d.json" % proc.pid)
        os.makedirs(os.path.dirname(note), exist_ok=True)
        with open(note, "w") as f:
            json.dump({"session_id": sid, "reason": "clear", "hook_event_name": "SessionEnd"}, f)
        t = time.time() - 600
        os.utime(note, (t, t))   # the /clear ten minutes ago; the left session resumed elsewhere since
        self.sweep()
        self.assertTrue(self.exists(sid), "resumed and touched since: its transcript's rule holds")

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
