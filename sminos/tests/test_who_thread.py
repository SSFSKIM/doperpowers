#!/usr/bin/env python3
"""`sminos who --thread <name>`: the thread a name is, as one line of JSON a
program reads (EN.G1's plan, M2:
docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, Interfaces
§4). devcloud's `vm owner` is its reader.

- One thread by every name `find_target` takes for it (its alias,
  `alias#short`, `@short`, a bare short, its thread id, a former session's
  id and short after a hand-off and after a refill): the same answer, its
  `session` the current one.
- The fields: another machine's member, a retired seat, an ended thread
  its human opened by its full id, a stopped one, a session that is no
  thread, a vacant seat, the project by id and name.
- A name two threads share and a name nothing answers: exit 4, sminos's own
  line on standard error, nothing on standard output.
- `who` alone and `who --session` print as before, before any migration;
  `who --thread` migrates as every reading verb does.

Hermetic: test_threads.Machine's temporary HOME and SMINOS_HOME, sessions
that are `sleep` processes, the engine's `claude agents` and `claude stop`
stood in for, devcloud's stand-in (devcloud_isolation.py).
Run: python3 -B sminos/tests/test_who_thread.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import json
import os
import sys
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import Sessions, records, sminos, threads  # noqa: E402
from test_threads_ended import Ending  # noqa: E402

KEYS = ["thread", "session", "short", "alias", "opened", "state", "ended", "local", "machine", "project"]


class Who(Ending):
    # A hand-off and a refill as test_threads.Sessions makes them.
    handoff_transcript = Sessions.handoff_transcript
    job = Sessions.job
    refill = Sessions.refill
    elsewhere = Sessions.elsewhere

    def who(self, *argv, cwd=None):
        """(exit, stdout, stderr) of `sminos <argv>` run in this process."""
        out, err = io.StringIO(), io.StringIO()
        here = os.getcwd()
        os.chdir(cwd or self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    sminos.main(list(argv))
                    code = 0
                except SystemExit as e:
                    code = e.code or 0
        finally:
            os.chdir(here)
            sminos.forget_caches()
        return code, out.getvalue(), err.getvalue()

    def answer(self, name, cwd=None):
        code, out, err = self.who("who", "--thread", name, cwd=cwd)
        self.assertEqual(code, 0, (name, out, err))
        self.assertEqual(len(out.splitlines()), 1, "one line and nothing else: %r" % out)
        got = json.loads(out)
        self.assertEqual(list(got), KEYS)
        return got

    def project(self, p=None):
        p = p or self.p
        return {"id": p.id, "name": p.name}


class Names(Who):
    def test_a_thread_its_human_opened_handed_to_a_job_is_the_same_answer_by_every_name(self):
        old, oproc = self.opened(name="handy")
        tid = threads.stamp(old)
        job, _ = self.job(old)
        self.reconcile()
        self.end(oproc)
        self.reconcile()
        self.assertEqual(threads.get(tid)["current"], job)
        want = {"thread": tid, "session": job, "short": job[:8], "alias": "handy", "opened": "human",
                "state": self.member(job).state, "ended": False, "local": True, "machine": sminos.host_name(),
                "project": self.project()}
        for name in ("handy", "handy#" + job[:8], "@" + job[:8], job[:8], job, tid, old, old[:8], "@" + old[:8]):
            with self.subTest(name=name):
                self.assertEqual(self.answer(name), want)

    def test_a_spawned_thread_refilled_is_the_same_answer_by_every_name(self):
        old, proc, seat_id = self.seated(alias="worker")
        self.end(proc)
        self.reconcile()
        new, _, out = self.refill(seat_id, alias="worker")
        self.reconcile()
        self.assertEqual(sminos.reload_seat(seat_id)["current"], new, out)
        want = {"thread": seat_id, "session": new, "short": new[:8], "alias": "worker", "opened": "spawned",
                "state": self.answer("g/worker")["state"], "ended": False, "local": True,
                "machine": sminos.host_name(), "project": self.project()}
        for name in ("worker", "g/worker", "worker#" + new[:8], "@" + new[:8], new[:8], new, seat_id, old, old[:8]):
            with self.subTest(name=name):
                self.assertEqual(self.answer(name), want)


class Fields(Who):
    def test_a_member_of_another_machine_is_not_local(self):
        sid, _ = self.opened(name="faraway")
        tid = threads.stamp(sid)
        with self.elsewhere() as p:
            got = self.answer("faraway")
            self.assertEqual((got["thread"], got["session"], got["alias"], got["local"], got["machine"]),
                             (tid, sid, "faraway", False, "testhost"))
            self.assertEqual(got["project"], self.project(p))
            self.assertFalse(got["ended"])

    def test_a_retired_seat_has_ended(self):
        sid, proc, seat_id = self.seated(alias="w")
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        got = self.answer("g/w")
        self.assertEqual((got["thread"], got["alias"], got["opened"], got["state"], got["ended"]),
                         (seat_id, "w", "spawned", "retired", True))

    def test_an_ended_thread_its_human_opened_answers_to_its_full_ids_alone(self):
        sid, _ = self.opened(name="gone")
        tid = threads.stamp(sid)
        code, out = self.cli("retire", "gone")
        self.assertEqual(code, 0, out)
        for name in (sid, tid):
            with self.subTest(name=name):
                got = self.answer(name)
                self.assertEqual((got["thread"], got["session"], got["alias"], got["opened"], got["ended"]),
                                 (tid, sid, "gone", "human", True))
        for name in ("gone", sid[:8]):
            with self.subTest(name=name):
                code, out, err = self.who("who", "--thread", name)
                self.assertEqual((code, out), (4, ""), err)

    def test_a_stopped_thread_has_not_ended(self):
        sid = self.closed(name="resting")
        got = self.answer("resting")
        self.assertEqual((got["session"], got["state"], got["ended"]), (sid, "stopped", False))

    def test_a_session_that_is_no_thread_has_an_empty_thread(self):
        sid, _ = self.session(name="maws-launched")
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        self.reconcile()
        got = self.answer(sid[:8])
        self.assertEqual((got["thread"], got["opened"], got["session"]), ("", "", sid))

    def test_a_seat_a_session_of_no_thread_holds_is_no_thread(self):
        """A seat `seat add` made for a lane B session (one the MAWS app
        launched): no record represents a thread, as its retire's guard
        reads it, so nothing is made up for it."""
        sid, _ = self.session(name="maws-seated")
        records.establish(sid, records.default_provenance())
        records.set_controller(sid, "B")
        code, out = self.cli("seat", "add", "g", "laneb", "--session", sid)
        self.assertEqual(code, 0, out)
        self.assertIsNone(threads.get(next(s["seat_id"] for s in sminos.seats() if s["alias"] == "laneb")))
        got = self.answer("g/laneb")
        self.assertEqual((got["thread"], got["opened"], got["session"]), ("", "", sid))

    def test_a_seat_an_older_copy_put_on_a_thread_its_human_opened_answers_with_that_thread(self):
        sid, _ = self.opened(name="older")
        tid = threads.stamp(sid)
        seat_id = "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d"
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": sid, "alias": "older", "group": "g", "cwd": self.root,
                                  "status": "idle"})
        sminos.forget_caches()
        got = self.answer("g/older")
        self.assertEqual((got["thread"], got["opened"], got["session"]), (tid, "human", sid), "not the wrapper seat")

    def test_a_vacant_seat_has_an_empty_session(self):
        code, out = self.cli("seat", "add", "g", "empty")
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats() if s["alias"] == "empty")
        got = self.answer("g/empty")
        self.assertEqual((got["thread"], got["session"], got["short"], got["state"], got["ended"]),
                         (seat_id, "", "", "vacant", False))
        self.assertEqual(got["project"], self.project())


class Refusals(Who):
    def test_a_name_two_threads_share_and_one_nothing_answers_exit_4_with_nothing_on_standard_output(self):
        for group in ("g", "h"):
            code, out = self.cli("seat", "add", group, "twin")
            self.assertEqual(code, 0, out)
        code, out, err = self.who("who", "--thread", "twin")
        self.assertEqual((code, out), (4, ""))
        self.assertIn("sminos: ambiguous seat 'twin' matches: g/twin, h/twin", err)
        code, out, err = self.who("who", "--thread", "nobody")
        self.assertEqual((code, out, err), (4, "", "sminos: no seat or member matching 'nobody'\n"))

    def test_thread_beside_a_target_or_a_session_and_an_empty_name_are_usage_errors(self):
        for argv in (("who", "--thread", "x", "HEAD"), ("who", "--thread", "x", "--session", "y"), ("who", "--thread"),
                     ("who", "--thread", "")):
            with self.subTest(argv=argv):
                with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": str(uuidlib.uuid4())}):
                    code, out, _ = self.who(*argv)
                self.assertEqual((code, out), (2, ""), "never the session's trailer")


class EarlyPath(Who):
    def test_who_alone_and_who_session_print_as_before_and_never_migrate_while_who_thread_does(self):
        sid, _ = self.opened(name="addressed")
        line = sminos.session_address(sid, self.root)
        self.assertTrue(line)
        with mock.patch.object(sminos, "migrate", side_effect=AssertionError("migrated")):
            code, out, err = self.who("who", "--session", sid)
            self.assertEqual((code, out), (0, line + "\n"), err)
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
                code, out, err = self.who("who")
            self.assertEqual((code, out), (0, line + "\n"), err)
        with mock.patch.object(sminos, "migrate", wraps=sminos.migrate) as migrate:
            self.answer("addressed")
        self.assertEqual(migrate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
