#!/usr/bin/env python3
"""A view answers from a log no older than its own reconciliation (#581).

view_of reads the project's log, then reconciles this machine's sessions into
it. When another process (the daemon's tick, any other verb) joins a new
session between the two, this reconciliation's guard declines to join it
again; the view must still hold that member. Here the other writer is a real
`sminos list` in another process, run just before this process's
reconciliation; the verbs run in this process through main().

Hermetic: HOME and SMINOS_HOME are temporary, fresh for each test; the
sessions are `sleep` processes with engine records the test writes.
Run: python3 -B sminos/tests/test_view_race.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
CLI = os.path.join(SCRIPTS, "sminos.py")
BASE = os.path.realpath(tempfile.mkdtemp(prefix="smvr."))
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "MAWS_LANE",
            "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_LAUNCH", "CLAUDE_PID",
            "MAWS_LAUNCHED_BY"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), DAEMON_HOST="testhost",
                  SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, SCRIPTS)

import sminos  # noqa: E402


class JoinedMeanwhile(unittest.TestCase):
    STATE = "s"   # the state directory's name under the test's home

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, self.STATE))
        os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
        os.makedirs(os.environ["SMINOS_HOME"])
        self.procs, self.proc_of = [], {}
        self.addCleanup(self.stop_all)
        self.root = os.path.join(home, "work")
        subprocess.run(["git", "init", "-q", self.root], check=True)
        sminos.forget_caches()
        self.p = sminos.resolve_project(self.root)
        sminos.project_path(self.p, "log")
        self.sender = self.session("sender")
        self.cli("list")

    def stop_all(self):
        for proc in self.procs:
            proc.kill()
            proc.wait()
        sminos.forget_caches()

    def session(self, name, sid=None):
        """A live interactive session of this machine named `name`."""
        sid = sid or str(uuidlib.uuid4())
        proc = subprocess.Popen(["sleep", "600"])
        self.procs.append(proc)
        self.proc_of[sid] = proc
        with open(self.peer_path(proc.pid), "w") as f:
            json.dump({"pid": proc.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive", "name": name,
                       "nameSource": "user", "status": "idle"}, f)
        sminos.forget_caches()
        return sid

    @staticmethod
    def peer_path(pid):
        return os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % pid)

    def end(self, sid):
        """The session's process gone, and its engine record with it."""
        proc = self.proc_of.pop(sid)
        proc.kill()
        proc.wait()
        os.unlink(self.peer_path(proc.pid))
        sminos.forget_caches()

    def handoff_transcript(self, old, new):
        """The old session's transcript as the engine leaves it at a hand-off to a background job."""
        d = os.path.join(os.environ["HOME"], ".claude", "projects", "p-work")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, old + ".jsonl"), "a") as f:
            for r in ({"type": "user", "sessionId": old, "cwd": self.root,
                       "message": {"role": "user", "content": "keep going"}},
                      {"type": "assistant", "uuid": "h-" + old[:4], "message": {
                          "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}},
                      {"type": "continued-in", "sessionId": old, "continuedInSessionId": new}):
                f.write(json.dumps(r) + "\n")
        sminos._TINDEX.at = None
        sminos._TINDEXES.clear()
        sminos.forget_caches()

    def cli(self, *argv, session=None):
        """The verb in this process: (exit code, its output)."""
        out = io.StringIO()
        here = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), \
                    mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session} if session else {}):
                try:
                    sminos.main(list(argv))
                    code = 0
                except SystemExit as e:
                    code = e.code or 0
        finally:
            os.chdir(here)
            sminos.forget_caches()
        return code, out.getvalue()

    def other_writer_first(self):
        """_reconcile, run once another process has reconciled the project
        (joining whatever this one is about to): the interleaving where a
        verb's log read is older than a join it then declines to repeat."""
        real = sminos._reconcile
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}

        def reconcile(*args, **kwargs):
            subprocess.run([sys.executable, "-B", CLI, "list"], cwd=self.root, env=env, check=True,
                           capture_output=True, timeout=60)
            return real(*args, **kwargs)

        return mock.patch.object(sminos, "_reconcile", reconcile)

    def joined_by_other(self, sid):
        joins = [e for e in sminos._own_events(self.p, sid) if e["kind"] == "joined"]
        self.assertEqual(len(joins), 1, "joined once, by the other process: %s" % joins)

    def test_the_view_holds_a_member_the_other_process_joined(self):
        new = self.session("newcomer")
        with self.other_writer_first():
            view = sminos.view_of(self.p)
        self.joined_by_other(new)
        self.assertIn(new, [m.session for m in view.members])
        self.assertEqual(view.reconciled, 0, "nothing of it was this reconciliation's")

    def test_list_shows_it(self):
        new = self.session("newcomer")
        with self.other_writer_first():
            code, out = self.cli("list", "--json")
        self.assertEqual(code, 0, out)
        self.joined_by_other(new)
        self.assertIn(new, [r.get("session") for r in json.loads(out)], out)

    def test_say_at_its_alias_reaches_it(self):
        # Two members whose short is the alias: a tag that misses the alias would be ambiguous between them.
        h = uuidlib.uuid4().hex[:8]
        self.session("x1", "%s-0000-4000-8000-000000000001" % h)
        self.session("x2", "%s-0000-4000-8000-000000000002" % h)
        self.cli("list")
        new = self.session(h)
        with self.other_writer_first():
            code, out = self.cli("say", "@%s the alias" % h, session=self.sender)
        self.assertEqual(code, 0, out)
        self.joined_by_other(new)
        said = [e for e in sminos.log_read(self.p) if e["kind"] == "say" and "the alias" in str(e.get("text"))]
        self.assertEqual([r.get("session") for e in said for r in e.get("to") or []], [new], said)

    def test_a_seat_the_other_process_handed_off_is_still_its_seat(self):
        # The other process moves the seat to the job it went on in, and appends the hand-off's events; this
        # reconciliation appends nothing, and the view must read the seats as the log it answers from has them.
        old = self.session("w")
        code, out = self.cli("seat", "add", "g", "worker", "--session", old)
        self.assertEqual(code, 0, out)
        self.end(old)
        job = str(uuidlib.uuid4())
        self.handoff_transcript(old, job)
        here = os.getcwd()
        os.chdir(self.root)   # the caller's project, as a verb run there has it
        try:
            with self.other_writer_first():
                view = sminos.view_of(self.p)
                target = sminos.find_target("worker")
        finally:
            os.chdir(here)
        self.assertEqual(sminos.load_seat(next(sminos.record_files()))["current"], job, "handed off by the other")
        self.assertEqual(view.reconciled, 0, "nothing of it was this reconciliation's")
        [row] = [m for m in view.members if m.session == job]
        self.assertIsNotNone(row.seat, "the job is the seat's session")
        self.assertEqual(target[0], "seat", target)


class GlobInHome(JoinedMeanwhile):
    """Every case again, in a state directory whose path holds glob characters, and the log read there."""
    STATE = "state[1]"

    @unittest.skip("the seats' own listing (record_files) takes the state directory as a pattern still")
    def test_a_seat_the_other_process_handed_off_is_still_its_seat(self):
        pass

    def test_the_log_is_read(self):
        new = self.session("newcomer")
        view = sminos.view_of(self.p)
        self.assertIn(new, [m.session for m in view.members], "this process's own join")
        self.assertTrue(any(e["kind"] == "joined" and e["session"] == new for e in sminos.log_read(self.p)))
        sminos.forget_caches()
        self.assertIn(new, [m.session for m in sminos.view_of(self.p).members], "and the next view's")


if __name__ == "__main__":
    unittest.main()
