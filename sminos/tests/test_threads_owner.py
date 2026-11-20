#!/usr/bin/env python3
"""A thread that owns a VM is neither retired nor ended (T1's M5:
docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md, the milestone's
"What it proves"; Interfaces §7, §8; contract X9).

- Owned: `retire` refused naming each host, an adopted machine as one, the
  thread still a member; the ending pass leaves it stopped and says so once.
- Each way of getting no answer that reads unknown: refused naming it, and
  the ending pass leaves the thread stopped.
- None and exit 6: the retire and the end go through.
- The lookup's order, against a made-up plugin layout; a manifest older
  than 0.17.2 read as unknown, named; the real launcher, once, under a HOME
  with no seed key: exit 6, read as none.
- The names asked: the short ids of every session the thread has had.
- `--owner-unknown`: a person at a terminal, after a typed yes, and only on
  unknown.
- The census: off the tick, one in flight, one question for every thread
  due, its answer taken up only for the stop it was asked about; a driver
  that never answers is stopped with what it started.

Hermetic: test_threads.Machine's temporary HOME and SMINOS_HOME, and the
suite's stand-in for devcloud (devcloud_standin.py, which SMINOS_DEVCLOUD
names); the one test of the real launcher runs it under an empty HOME with
none of devcloud's variables. Run: python3 -B sminos/tests/test_threads_owner.py
"""
import devcloud_isolation  # noqa: F401 — first: no test reaches a real devcloud (T1's M5)
import contextlib
import fcntl
import glob
import io
import json
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import BASE, sminos, threads  # noqa: E402
from test_threads_ended import PERIOD, Ending, ago  # noqa: E402
from test_threads_stopped import wait_for  # noqa: E402

STANDIN = os.path.join(HERE, "devcloud_standin.py")
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(REPO, "sminos", "skills", "sminos", "scripts")


def host(name, short, account="main", provider="hetzner"):
    return {"name": name, "account": account, "provider": provider, "creator": "@" + short}


def adopted(name, short):
    return {"name": name, "account": "adopted", "provider": None, "creator": "@" + short, "adopted": True}


SPARE = {"account": "spare", "provider": "gce", "failed": "account",
         "reason": "provider gce of account spare has no passing copy yet"}


def launcher(path, script, version=None):
    """A copy of devcloud's CLI at `path` (its bin/devcloud) running `script`
    (sh), with the plugin manifest beside it at `version` (none if None)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + script + "\n")
    os.chmod(path, 0o755)
    if version is not None:
        manifest = os.path.join(os.path.dirname(os.path.dirname(path)), ".claude-plugin", "plugin.json")
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, "w") as f:
            json.dump({"name": "devcloud", "version": version}, f)


class Owner(Ending):
    def setUp(self):
        super().setUp()
        self.assertIs(sminos.threads_module(), threads)
        os.environ.pop("SMINOS_DEVCLOUD_TIMEOUT", None)
        self.addCleanup(self.standins_gone)

    def standins_gone(self):
        """Whatever a stand-in this test ran left running (a failed test's), stopped."""
        for call in self.calls():
            for pid in (call["pid"], call["child"]):
                with contextlib.suppress(OSError, TypeError):
                    os.kill(pid, signal.SIGKILL)

    def standin(self, **cfg):
        with open(os.path.join(os.environ["HOME"], "devcloud-standin.json"), "w") as f:
            json.dump(cfg, f)

    def calls(self):
        try:
            with open(os.path.join(os.environ["HOME"], "devcloud-standin.calls")) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def asked(self):
        return [c["argv"][2:] for c in self.calls()]

    def logged(self, needle):
        try:
            with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
                return [line for line in f if needle in line]
        except OSError:
            return []

    def due(self, name="alpha"):
        """A session its human opened, closed, and stopped past the period:
        its stop marked by passes that find nothing due (another thread due
        already would be asked about)."""
        sid = self.closed(name=name)
        with mock.patch.dict(os.environ, {"SMINOS_THREAD_END_AFTER": str(100 * PERIOD)}):
            self.pass_()
            self.pass_()
        tid = threads.stamp(sid)
        self.assertTrue(threads.get(tid).get("stopped"), "the stop is marked")
        at = ago(2 * PERIOD)
        self.assertTrue(threads.update(tid, {"stopped": at, "swept": at}))
        return sid, tid, at

    def ended(self, tid):
        return threads.record_ended(threads.get(tid))

    def pass_(self, spaced=True):
        """One pass of the sweep, as the daemon's tick makes it, on the
        ending pass's spacing unless `spaced` is false."""
        if spaced:
            self.spacing_due()
        sminos.forget_caches()
        self.daemon.sweep_threads()
        sminos.forget_caches()

    def take_up(self):
        """A pass on its spacing that takes up the census's answer as it
        stands, its own census held back: the mock of start_census."""
        with mock.patch.object(self.daemon, "start_census") as start:
            self.pass_()
        return start

    def run_path(self):
        return os.path.join(os.environ["SMINOS_HOME"], "daemon", "census-run.json")

    def owe(self, to, sender, text):
        """A message addressed to `to`, written as an older sender writes one
        (its own writer file, no push): owed until a tick delivers it."""
        sminos.log_append(self.p, sminos.writer_id(sender), "message", session=sender, text="@x %s" % text,
                          to=[{"session": to, "alias": "x"}])
        sminos.forget_caches()

    def full_tick(self):
        """The daemon's whole tick (every project, then the thread sweep):
        how long it took."""
        began = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            self.daemon.tick_all(quiet=True)
        sminos.forget_caches()
        return time.monotonic() - began

    def census_here(self, *tids):
        """The census's question, asked in this process (so a test's patches
        of the lookup apply), its answer written as the child writes it."""
        self.daemon.census(list(tids))
        sminos.forget_caches()

    def census_done(self):
        proc = self.daemon._CENSUS
        self.assertIsNotNone(proc, "a census was started")
        proc.wait(30)

    def subprocess_env(self, **more):
        """The CLI in a process of its own: this test's machine, and a
        `claude` that lists no background session."""
        bindir = os.path.join(self.home, "bin")
        if not os.path.exists(os.path.join(bindir, "claude")):
            os.makedirs(bindir, exist_ok=True)
            with open(os.path.join(bindir, "claude"), "w") as f:
                f.write("#!/bin/sh\necho '[]'\n")
            os.chmod(os.path.join(bindir, "claude"), 0o755)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
        env.update(more)
        return env

    def cli_alone(self, *argv):
        """The CLI with no controlling terminal (a new session)."""
        p = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), *argv], cwd=self.root,
                           env=self.subprocess_env(), capture_output=True, text=True, timeout=60,
                           start_new_session=True)
        return p.returncode, p.stdout + p.stderr

    def cli_tty(self, answer, *argv):
        """The CLI on a controlling pty of its own, a person typing `answer`
        at its prompt: (exit code, what it printed)."""
        env = self.subprocess_env()
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(self.root)
                os.execve(sys.executable, [sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), *argv], env)
            finally:
                os._exit(127)
        out, sent, end = b"", False, time.monotonic() + 60
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], 1)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if not sent and b"[y/N]" in out:
                os.write(fd, answer.encode() + b"\n")
                sent = True
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        return os.waitstatus_to_exitcode(status), out.decode("utf-8", "replace")


# ------------------------------------------------------------ owned


class Owned(Owner):
    def test_retire_is_refused_naming_each_host_and_an_adopted_machine_as_one_and_it_stays_a_member(self):
        sid, _ = self.opened()
        self.standin(hosts=[host("dc-a-0001", sid[:8]), adopted("lab-box", sid[:8]), host("dc-z-0009", "ffff0000")])
        code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 1, out)
        self.assertIn("alpha (session %s) is not retired" % sid[:8], out)
        self.assertIn("dc-a-0001 (hetzner, account main)", out)
        self.assertIn("lab-box (an adopted machine)", out)
        self.assertIn("devcloud vm down dc-a-0001", out)
        self.assertNotIn("dc-z-0009", out, "another thread's host")
        self.assertTrue(self.is_member(sid))
        self.assertFalse(self.ended(threads.stamp(sid)))
        self.assertEqual(self.asked(), [[sid[:8]]])

    def test_purge_and_remove_are_refused_too_for_a_seat_and_for_a_session_its_human_opened(self):
        sid, _ = self.opened()
        wsid, _, seat_id = self.seated()
        self.standin(hosts=[host("dc-a-0001", sid[:8]), host("dc-b-0002", wsid[:8])])
        for argv in (("retire", "alpha", "--purge"), ("remove", "alpha"), ("retire", "g/w"),
                     ("retire", "g/w", "--purge"), ("remove", "g/w")):
            code, out = self.cli(*argv)
            self.assertEqual(code, 1, (argv, out))
            self.assertIn("devcloud vm down", out, argv)
        self.assertTrue(self.is_member(sid) and self.is_member(wsid))
        self.assertIsNotNone(sminos.reload_seat(seat_id))
        self.assertEqual(self.human_files(), [threads.stamp(sid) + ".json"])

    def test_the_ending_pass_leaves_it_stopped_and_says_so_once(self):
        sid, tid, at = self.due()
        self.standin(hosts=[host("dc-a-0001", sid[:8])])
        for _ in range(3):
            self.sweep()
        self.assertFalse(self.ended(tid))
        self.assertEqual(threads.get(tid)["stopped"], at)
        self.assertTrue(self.is_member(sid))
        said = self.logged("stopped and not ended")
        self.assertEqual(len(said), 1, said)
        self.assertIn("dc-a-0001 (hetzner, account main)", said[0])
        self.assertGreaterEqual(len(self.calls()), 2, "asked again by the next census")

    def test_the_names_asked_are_the_short_ids_of_every_session_the_thread_has_had(self):
        old = "0a1b2c3d-0000-4000-8000-000000000001"
        sid, _ = self.session(name="alpha")
        self.transcript(sid)
        self.write_own(old, [self.old_joined(old), {"kind": "retired", "by": "", "reason": "continued", "to": sid}])
        self.write_own(sid, [self.old_joined(sid, alias="alpha")])
        self.reconcile()
        self.assertEqual(threads.thread_of(sid)["sessions"], [old, sid])
        self.standin(hosts=[host("dc-a-0001", old[:8])])
        code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 1, out)
        self.assertIn("dc-a-0001", out, "a host the session it continues made")
        self.assertEqual(self.asked(), [[old[:8], sid[:8]]], "bare short ids, each session's")

    def test_a_seat_adopted_after_it_was_refilled_whose_host_names_only_its_first_occupant_is_refused(self):
        first, current = "1a1b2c3d-0000-4000-8000-000000000001", None
        current, _ = self.session(name="worker")
        seat_id = "5ea70000-0000-4000-8000-000000000001"
        sminos.meta_set(seat_id, {"uuid": seat_id, "current": current, "alias": "worker", "group": "g",
                                  "cwd": self.root, "status": "idle",
                                  "history": [{"current": first, "short": first[:8], "status": "idle"}]})
        self.write_own(current, [self.old_joined(current, alias="worker", seat=seat_id, name_source="seat")])
        self.standin(hosts=[host("dc-a-0001", first[:8])])
        code, out = self.cli("retire", "g/worker")
        self.assertEqual(code, 1, out)
        self.assertIn("dc-a-0001", out, "before its adoption, from its history")
        self.reconcile()
        self.assertEqual(threads.get(seat_id)["sessions"], [first, current], "adopted")
        code, out = self.cli("retire", "g/worker")
        self.assertEqual(code, 1, out)
        self.assertIn("dc-a-0001", out)
        self.assertNotEqual(sminos.reload_seat(seat_id)["status"], "retired")

    def test_a_vacant_seat_is_retired_with_no_question_asked(self):
        code, out = self.cli("seat", "add", "g", "v")
        self.assertEqual(code, 0, out)
        self.standin(exit=1, stderr="never asked")
        code, out = self.cli("retire", "g/v")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls(), [])
        seat = next(s for s in sminos.seats() if s["alias"] == "v")
        self.assertEqual(seat["status"], "retired")


    def test_a_seat_filled_while_devcloud_was_asked_is_not_retired(self):
        code, out = self.cli("seat", "add", "g", "v")
        self.assertEqual(code, 0, out)
        seat_id = next(s["seat_id"] for s in sminos.seats() if s["alias"] == "v")
        sid, _ = self.session(name="v")
        real = sminos.owner_guard

        def meanwhile(*a):
            got = real(*a)
            sminos.meta_set(seat_id, {"current": sid})   # a fill, between the question and the seat's locks
            return got
        with mock.patch.object(sminos, "owner_guard", side_effect=meanwhile):
            code, out = self.cli("retire", "g/v")
        self.assertEqual(code, 4, out)
        self.assertIn("changed while its end was decided", out)
        self.assertNotEqual(sminos.reload_seat(seat_id)["status"], "retired")


    def test_a_seat_ended_already_and_filled_before_its_retire_takes_its_locks_is_not_retired(self):
        """A retire of an ended seat asks nothing, since it ends nothing;
        a fill that returns the seat before the retire takes its locks
        leaves it nothing to stand on."""
        sid, proc, seat_id = self.seated()
        code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.ended(seat_id))
        new, _ = self.session(name="w")
        self.standin(hosts=[host("dc-a-0001", new[:8])])
        real = sminos.seat_owner_guard

        def filled(*a):
            got = real(*a)
            self.assertEqual(got, threads.Exempt("ended"))
            with open(sminos.meta_path(seat_id)) as f:   # a fill's return, between the question and the locks
                raw = json.load(f)
            raw.update(current=new, status="idle", sessions=raw["sessions"] + [new])
            raw.pop("ended", None)
            sminos.write_json(sminos.meta_path(seat_id), raw)
            sminos.forget_caches()
            return got
        with mock.patch.object(sminos, "seat_owner_guard", side_effect=filled):
            code, out = self.cli("retire", "g/w")
        self.assertEqual(code, 4, out)
        self.assertIn("changed while its end was decided", out)
        self.assertFalse(self.ended(seat_id), "its new occupant, never asked about, keeps it")
        self.assertFalse(threads.asked_all(threads.get(seat_id), None), "nothing asked clears nothing")


# ------------------------------------------------------------ unknown


class Unknown(Owner):
    def rows(self):
        """Each way of getting no answer that reads unknown: (what it is, a
        context that makes it, what the refusal names)."""
        layout = os.path.join(self.home, "layout")
        bare = os.path.join(self.home, "bare")
        os.makedirs(bare, exist_ok=True)

        @contextlib.contextmanager
        def standin(**cfg):
            self.standin(**cfg)
            yield

        @contextlib.contextmanager
        def lookup(version):
            beside = os.path.join(layout, "devcloud", "bin", "devcloud")
            if version is not None:
                launcher(beside, "exit 6", version)
            env = {k: v for k, v in os.environ.items() if k != "SMINOS_DEVCLOUD"}
            env["PATH"] = bare
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(threads, "plugin_root", return_value=os.path.join(layout, "sminos")):
                yield

        @contextlib.contextmanager
        def unrunnable():
            path = os.path.join(self.home, "not-executable")
            with open(path, "w") as f:
                f.write("#!/bin/sh\nexit 6\n")
            os.chmod(path, 0o644)
            with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD": path}):
                yield

        @contextlib.contextmanager
        def bounded():
            self.standin(hang=True)
            with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD_TIMEOUT": "0.5"}):
                yield

        return [
            ("an answer of unknown", standin(unknown=[SPARE]),
             "account spare (gce): provider gce of account spare has no passing copy yet"),
            ("an owned answer for another thread, and something it could not ask",
             standin(hosts=[host("dc-z-0009", "ffff0000")], unknown=[SPARE]), "account spare (gce)"),
            ("another exit", standin(exit=1, stderr="devcloud: needs Python 3.11 or later on PATH\n"),
             "exited 1: devcloud: needs Python 3.11 or later on PATH"),
            ("exit 0 without the answer", standin(stdout="Traceback (most recent call last):\n"),
             "exited 0 without a well-formed answer (a malformed answer): Traceback (most recent call last):"),
            ("a timeout", bounded(), "gave no answer within 0.5s, and was stopped"),
            ("owned with no host", standin(stdout='{"answer": "owned"}\n'), "a malformed answer"),
            ("a host with no creator", standin(stdout=json.dumps({
                "answer": "owned", "vms": [{"name": "dc-a-0001", "account": "main", "provider": "hetzner"}],
                "unknown": [], "listed": ["main"]}) + "\n"), "a malformed answer"),
            ("none with something it could not ask", standin(stdout=json.dumps({
                "answer": "none", "vms": [], "unknown": [SPARE], "listed": []}) + "\n"), "a malformed answer"),
            ("a host with no provider that is no adopted machine", standin(stdout=json.dumps({
                "answer": "owned", "vms": [{"name": "dc-a-0001", "account": "main", "provider": None,
                                            "creator": "@abcd1234"}], "unknown": [], "listed": []}) + "\n"),
             "a malformed answer"),
            ("a launcher that cannot be run", unrunnable(), "could not be run"),
            ("a copy older than 0.17.2", lookup("0.17.1"), "is 0.17.1, older than 0.17.2"),
            ("no copy found", lookup(None), "no devcloud CLI was found here"),
        ]

    def test_each_way_of_no_answer_refuses_naming_it_and_the_pass_leaves_the_thread_stopped(self):
        for i, (what, _, _) in enumerate(self.rows()):
            with self.subTest(what):
                if i:
                    self.fresh()
                what, ctx, named = self.rows()[i]
                sid, tid, at = self.due()
                with ctx:
                    code, out = self.cli("retire", "alpha")
                    self.assertEqual(code, 1, out)
                    self.assertIn("is not retired", out)
                    self.assertIn(named, out)
                    self.assertIn("sminos retire alpha --owner-unknown", out)
                    self.assertTrue(self.is_member(sid))
                    self.census_here(tid)
                self.take_up()
                self.assertFalse(self.ended(tid))
                self.assertEqual(threads.get(tid)["stopped"], at)
                said = self.logged("stopped and not ended")
                self.assertEqual(len(said), 1, said)
                self.assertIn(named, said[0])

    def test_a_copy_older_than_0_17_2_is_not_run_and_its_version_and_place_are_named(self):
        layout = os.path.join(self.home, "layout")
        beside = os.path.join(layout, "devcloud", "bin", "devcloud")
        ran = os.path.join(self.home, "ran")
        launcher(beside, "touch %s; exit 6" % ran, "0.17.1")
        env = {k: v for k, v in os.environ.items() if k != "SMINOS_DEVCLOUD"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(threads, "plugin_root", return_value=os.path.join(layout, "sminos")):
            got = threads.owned_by(["abcd1234"])
        self.assertEqual(got.answer, "unknown")
        self.assertIn(beside, got.unknown[0]["reason"])
        self.assertIn("0.17.1", got.unknown[0]["reason"])
        self.assertEqual((got.unknown[0]["failed"], got.unknown[0]["account"], got.unknown[0]["provider"]),
                         ("query", None, None))
        self.assertFalse(os.path.exists(ran), "an older copy's exit 6 may mean a broken driver: not asked")

    def test_a_copy_with_no_manifest_beside_it_is_of_no_readable_version(self):
        layout = os.path.join(self.home, "layout")
        launcher(os.path.join(layout, "devcloud", "bin", "devcloud"), "exit 6")
        env = {k: v for k, v in os.environ.items() if k != "SMINOS_DEVCLOUD"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(threads, "plugin_root", return_value=os.path.join(layout, "sminos")):
            got = threads.owned_by(["abcd1234"])
        self.assertEqual(got.answer, "unknown")
        self.assertIn("of no readable version", got.unknown[0]["reason"])


# ------------------------------------------------------------ none


class NoneAnswer(Owner):
    def test_none_the_retire_and_the_end_go_through(self):
        sid, _ = self.opened()
        code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))
        self.assertEqual(self.asked(), [[sid[:8]]])
        other, tid, _ = self.due(name="beta")
        self.sweep()
        self.assertTrue(self.ended(tid))
        self.assertEqual(self.asked()[-1], [other[:8]])

    def test_exit_6_from_a_devcloud_of_0_17_2_reads_none_and_the_retire_and_the_end_go_through(self):
        layout = os.path.join(self.home, "layout")
        launcher(os.path.join(layout, "devcloud", "bin", "devcloud"),
                 "echo 'devcloud vm: no seed key: this machine is not a driver' >&2; exit 6", "0.17.2")
        env = {k: v for k, v in os.environ.items() if k != "SMINOS_DEVCLOUD"}
        sid, _ = self.opened()
        other, tid, _ = self.due(name="beta")
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(threads, "plugin_root", return_value=os.path.join(layout, "sminos")):
            code, out = self.cli("retire", "alpha")
            self.assertEqual(code, 0, out)
            self.assertNotIn("seed", out, "exit 6 refuses nothing, and is given as no reason")
            self.census_here(tid)
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))
        self.take_up()
        self.assertTrue(self.ended(tid))

    def test_exit_6_from_the_copy_sminos_devcloud_names_is_taken_at_its_word(self):
        path = os.path.join(self.home, "override", "devcloud")
        launcher(path, "exit 6")
        sid, _ = self.opened()
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD": path}):
            code, out = self.cli("retire", "alpha")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))


# ------------------------------------------------------------ the lookup


class Lookup(Owner):
    def test_each_place_is_found_when_the_ones_before_it_are_absent(self):
        layout = os.path.join(self.home, "layout")
        clone = os.path.join(self.home, "clone")
        pathplugin = os.path.join(self.home, "pathplugin")
        places = {"$SMINOS_DEVCLOUD": os.path.join(self.home, "override", "devcloud"),
                  "beside sminos": os.path.join(layout, "devcloud", "bin", "devcloud"),
                  "the marketplace clone": os.path.join(clone, "devcloud", "bin", "devcloud"),
                  "PATH": os.path.join(pathplugin, "bin", "devcloud")}
        for path in places.values():
            launcher(path, "exit 6", "0.17.2")
        known = os.path.join(os.environ["HOME"], ".claude", "plugins", "known_marketplaces.json")
        os.makedirs(os.path.dirname(known), exist_ok=True)
        with open(known, "w") as f:
            json.dump({"doperpowers": {"installLocation": clone}}, f)
        env = {"SMINOS_DEVCLOUD": places["$SMINOS_DEVCLOUD"], "PATH": os.path.dirname(places["PATH"])}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(threads, "plugin_root", return_value=os.path.join(layout, "sminos")):
            for where in ("$SMINOS_DEVCLOUD", "beside sminos", "the marketplace clone", "PATH"):
                self.assertEqual(threads.find_devcloud(), (where, places[where]))
                self.assertEqual(threads.owned_by(["abcd1234"]).answer, "none", where)
                if where == "$SMINOS_DEVCLOUD":
                    del os.environ["SMINOS_DEVCLOUD"]
                else:
                    os.unlink(places[where])
            where, looked = threads.find_devcloud()
            self.assertIsNone(where)
            for name in places:
                self.assertIn(name, looked)
            got = threads.owned_by(["abcd1234"])
            self.assertEqual(got.answer, "unknown")
            self.assertIn("the marketplace clone (%s)" % places["the marketplace clone"], got.unknown[0]["reason"])

    def test_the_call_puts_sminos_interpreter_first_on_the_path_it_gives(self):
        threads.owned_by(["abcd1234"])
        path = self.calls()[0]["path"].split(os.pathsep)
        self.assertEqual(path[0], os.path.dirname(sys.executable))
        self.assertEqual(path[1:], os.environ["PATH"].split(os.pathsep), "nothing else of it changed")

    def test_the_real_launcher_under_a_home_with_no_seed_key_answers_6_read_as_none(self):
        """The one test that runs devcloud's own CLI: beside this sminos, in
        this checkout, under an empty HOME and none of devcloud's variables,
        so nothing it could read names a seed key or a cloud account."""
        empty = tempfile.mkdtemp(dir=BASE)
        env = {k: v for k, v in os.environ.items() if k != "SMINOS_DEVCLOUD" and not k.startswith("DEVCLOUD_")}
        env["HOME"] = empty
        with mock.patch.dict(os.environ, env, clear=True):
            where, path = threads.find_devcloud()
            self.assertEqual((where, path), ("beside sminos", os.path.join(REPO, "devcloud", "bin", "devcloud")))
            self.assertGreaterEqual(threads.devcloud_version(path), threads.DEVCLOUD_MIN)
            self.assertFalse(os.path.exists(os.path.join(empty, ".config", "devcloud")))
            self.assertEqual(threads.owned_by(["abcd1234"]), threads.Owned("none", [], [], ["abcd1234"]))
        shutil.rmtree(empty, ignore_errors=True)


# ------------------------------------------------------------ --owner-unknown


class Terminal(Owner):
    def test_owner_unknown_is_refused_from_a_session_and_nothing_is_asked(self):
        sid, _ = self.opened()
        self.standin(unknown=[SPARE])
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            code, out = self.cli("retire", "alpha", "--owner-unknown")
        self.assertEqual(code, 1, out)
        self.assertIn("--owner-unknown is for a person at a terminal", out)
        self.assertEqual(self.calls(), [])
        self.assertTrue(self.is_member(sid))

    def test_owner_unknown_is_refused_with_no_terminal(self):
        sid, _ = self.opened()
        self.standin(unknown=[SPARE])
        code, out = self.cli_alone("retire", "alpha", "--owner-unknown")
        self.assertEqual(code, 1, out)
        self.assertIn("needs a person at a terminal to confirm it", out)
        self.assertTrue(self.is_member(sid))

    def test_owner_unknown_retires_on_unknown_at_a_terminal_after_a_typed_yes_and_only_then(self):
        sid, _ = self.opened()
        self.standin(unknown=[SPARE])
        code, out = self.cli_tty("n", "retire", "alpha", "--owner-unknown")
        self.assertEqual(code, 1, out)
        self.assertIn("alpha (session %s)" % sid[:8], out, "the prompt names the thread")
        self.assertIn("account spare (gce)", out, "and what could not be asked")
        self.assertIn("not confirmed; nothing was retired", out)
        self.assertTrue(self.is_member(sid))
        code, out = self.cli_tty("y", "retire", "alpha", "--owner-unknown")
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        self.assertEqual(self.ended_with(sid)[:2], ("retired", "retire"))

    def test_owner_unknown_is_refused_on_owned(self):
        sid, _ = self.opened()
        self.standin(hosts=[host("dc-a-0001", sid[:8])], unknown=[SPARE])
        code, out = self.cli_alone("retire", "alpha", "--owner-unknown")
        self.assertEqual(code, 1, out)
        self.assertIn("dc-a-0001 (hetzner, account main)", out)
        self.assertNotIn("[y/N]", out)
        self.assertTrue(self.is_member(sid))


# ------------------------------------------------------------ the census


class Census(Owner):
    def test_no_child_when_none_is_due(self):
        sid = self.closed()
        self.stopped_since(sid, PERIOD - 60)
        self.pass_()
        self.assertIsNone(self.daemon._CENSUS)
        self.assertFalse(os.path.exists(self.run_path()))
        self.assertEqual(self.calls(), [])

    def test_the_pass_returns_before_the_answer_delivery_goes_on_and_a_later_pass_takes_it_up(self):
        gate = os.path.join(self.home, "gate")
        self.standin(gate=gate)
        beta, _ = self.opened(name="beta", inbox=True)
        other, _ = self.session(name="older")
        self.reconcile()
        sid, tid, _ = self.due()
        began = time.monotonic()
        self.pass_()
        self.assertLess(time.monotonic() - began, 5, "the pass does not wait for devcloud")
        self.assertTrue(wait_for(lambda: self.calls()), "the census asks")
        for n in (1, 2):
            self.owe(beta, other, "number %d" % n)
            self.assertLess(self.full_tick(), 5)
            self.assertTrue(any("number %d" % n in m for m in self.inbox(beta)), self.inbox(beta))
        self.assertFalse(self.ended(tid))
        self.assertEqual(len(self.calls()), 1, "one census in flight")
        open(gate, "w").close()
        self.census_done()
        self.pass_(spaced=False)
        self.assertTrue(self.ended(tid), "the pass its landing starts takes the answer up")

    def test_one_call_for_every_thread_due_and_each_threads_answer_its_own(self):
        a, ta, at = self.due(name="alpha")
        b, tb, _ = self.due(name="beta")
        self.standin(hosts=[host("dc-a-0001", a[:8])])
        self.pass_()
        self.census_done()
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(sorted(self.asked()[0]), sorted([a[:8], b[:8]]))
        self.pass_(spaced=False)
        self.assertFalse(self.ended(ta))
        self.assertEqual(threads.get(ta)["stopped"], at)
        self.assertTrue(self.ended(tb))
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon", "census.json")) as f:
            census = json.load(f)
        self.assertEqual(sorted(x["thread"] for x in census["threads"]), sorted([ta, tb]))

    def test_an_answer_older_than_one_spacing_is_not_taken_up(self):
        """One spacing, whatever the bound on a question (a minute here, below
        what a census may take)."""
        sid, tid, at = self.due()
        for age, taken in ((90, False), (30, True)):
            sminos.write_json(self.daemon.daemon_path("census.json"), {
                "at": ago(age), "threads": [{"thread": tid, "current": sid, "stopped": at, "shorts": [sid[:8]]}],
                "answer": "none", "vms": [], "unknown": []})
            with mock.patch.dict(os.environ, {"SMINOS_THREAD_END_EVERY": "60"}):
                start = self.take_up()
            self.assertEqual(self.ended(tid), taken, age)
            self.assertEqual(start.called, not taken, "a thread with no answer it may take is asked about")

    def test_a_malformed_census_answer_holds_the_thread_named(self):
        sid, tid, at = self.due()
        sminos.write_json(self.daemon.daemon_path("census.json"), {
            "at": ago(1), "threads": [{"thread": tid, "current": sid, "stopped": at, "shorts": [sid[:8]]}],
            "answer": "owned", "vms": [{"name": "dc-a-0001", "account": "main", "provider": "hetzner"}],
            "unknown": []})
        self.take_up()
        self.assertFalse(self.ended(tid))
        said = self.logged("stopped and not ended")
        self.assertEqual(len(said), 1, said)
        self.assertIn("malformed", said[0])

    def test_a_driver_that_never_answers_is_stopped_past_the_bound_with_the_child_it_started(self):
        self.standin(hang=True, ignore_term=True, child=True)
        sid, tid, at = self.due()
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD_TIMEOUT": "1"}):
            self.pass_()
            with open(self.run_path()) as f:
                first = json.load(f)["pid"]
            self.assertTrue(wait_for(lambda: self.calls()), "the census asks")
            self.pass_()
            with open(self.run_path()) as f:
                self.assertEqual(json.load(f)["pid"], first, "no second census beside the first")
            self.census_done()
            call = self.calls()
            self.assertEqual(len(call), 1)
            for pid in (call[0]["pid"], call[0]["child"]):
                self.assertTrue(wait_for(lambda pid=pid: not alive(pid)), "past the bound, %d is gone" % pid)
            self.pass_(spaced=False)
        self.assertFalse(self.ended(tid))
        self.assertEqual(threads.get(tid)["stopped"], at)
        said = self.logged("devcloud")
        self.assertEqual(len(said), 1, said)
        self.assertIn("gave no answer within 1s, and was stopped", said[0])

    def stuck_run(self, started_ago=10, ignore_term=True):
        """A census that will not stop: a process recorded as the run,
        started `started_ago` s ago, that ignores SIGTERM (unless told
        not to) and has a child of its own in a session of its own."""
        stuck = subprocess.Popen([sys.executable, "-c", "import signal, subprocess, sys, time\n"
                                  "if sys.argv[1] == '1': signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                                  "print(subprocess.Popen(['sleep', '600'], start_new_session=True).pid, flush=True)\n"
                                  "time.sleep(600)", "1" if ignore_term else "0"], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (stuck.kill(), stuck.wait(), stuck.stdout.close()))
        child = int(stuck.stdout.readline())
        self.addCleanup(killed, child)
        sminos.write_json(self.daemon.daemon_path("census-run.json"),
                          {"pid": stuck.pid, "start": sminos.read_proc_start(stuck.pid),
                           "started": time.time() - started_ago})
        return stuck, child

    def test_a_census_past_twice_its_bound_is_stopped_off_the_tick_while_the_full_tick_delivers(self):
        beta, _ = self.opened(name="beta", inbox=True)
        other, _ = self.session(name="older")
        self.reconcile()
        stuck, child = self.stuck_run()
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD_TIMEOUT": "1"}):
            with open(self.daemon.daemon_path("census.lock"), "a") as held:
                fcntl.flock(held, fcntl.LOCK_EX)   # the census lock, held by another process at it
                self.owe(beta, other, "first")
                self.assertLess(self.full_tick(), 3, "a busy census lock is left to the next tick")
                fcntl.flock(held, fcntl.LOCK_UN)
            self.assertIsNone(self.daemon._REAPER)
            self.owe(beta, other, "second")
            self.assertLess(self.full_tick(), 3, "the escalation is a reaper's, never the tick's")
            reaper = self.daemon._REAPER
            self.assertIsNotNone(reaper, "a reaper started")
            self.owe(beta, other, "third")
            self.assertLess(self.full_tick(), 3)
            self.assertIs(self.daemon._REAPER, reaper, "one reaper")
            for text in ("first", "second", "third"):
                self.assertTrue(any(text in m for m in self.inbox(beta)), (text, self.inbox(beta)))
            self.assertTrue(wait_for(lambda: stuck.poll() is not None, timeout=30), "killed after the grace")
            self.assertTrue(wait_for(lambda: not alive(child)), "with the child it started")
            self.assertTrue(self.daemon.census_tick(), "its end is a landing, taken once")
            self.assertFalse(os.path.exists(self.run_path()))
            self.assertFalse(self.daemon.census_tick())
        said = self.logged("ran past twice its bound of 1s")
        self.assertEqual(len(said), 1, said)

    def test_a_recorded_run_is_supervised_at_the_next_tick_after_a_restart_whatever_is_due(self):
        self.daemon._CENSUS = self.daemon._REAPER = None   # a daemon restarted in place: no memory of the run
        done = subprocess.Popen(["true"])
        done.wait()
        sminos.write_json(self.daemon.daemon_path("census-run.json"), {"pid": done.pid, "start": "gone",
                                                                       "started": time.time() - 1})
        self.assertTrue(self.daemon.census_tick(), "an ended run is reaped and lands")
        self.assertFalse(os.path.exists(self.run_path()))
        stuck, child = self.stuck_run(ignore_term=False)
        with mock.patch.dict(os.environ, {"SMINOS_DEVCLOUD_TIMEOUT": "1"}):
            self.pass_(spaced=False)
            self.assertIsNotNone(self.daemon._REAPER, "supervised though nothing is due")
            self.assertTrue(wait_for(lambda: stuck.poll() is not None, timeout=15))

    def test_signals_go_only_to_the_process_the_run_names(self):
        sleeper = subprocess.Popen(["sleep", "600"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait()))
        sminos.write_json(self.daemon.daemon_path("census-run.json"),
                          {"pid": sleeper.pid, "start": "another start", "started": time.time() - 999})
        self.daemon.census_reap()
        self.assertIsNone(sleeper.poll(), "a pid whose start is not the run's is not signalled")
        self.daemon._CENSUS = sleeper
        sminos.write_json(self.daemon.daemon_path("census-run.json"), {"pid": 1, "start": "x", "started": 0})
        self.assertFalse(self.daemon.census_running({"pid": 1, "start": "x"}), "a handle of another pid is no say")
        self.daemon._CENSUS = None

    def test_a_census_asks_nothing_until_its_run_names_it(self):
        me = {"pid": os.getpid(), "start": sminos.read_proc_start(os.getpid()), "started": time.time()}
        with mock.patch.object(self.daemon, "CENSUS_WAIT", 0.2):
            sminos.write_json(self.daemon.daemon_path("census-run.json"), dict(me, pid=1))
            self.assertFalse(self.daemon.census_published())
            sminos.write_json(self.daemon.daemon_path("census-run.json"), me)
            self.assertTrue(self.daemon.census_published())

    def test_a_thread_that_reopened_during_the_question_or_reopened_and_stopped_again_is_not_ended_by_it(self):
        gate = os.path.join(self.home, "gate")
        self.standin(gate=gate)
        a, ta, _ = self.due(name="alpha")
        b, tb, _ = self.due(name="beta")
        self.pass_()
        self.assertTrue(wait_for(lambda: self.calls()), "the census asks about both")
        _, proc_a = self.live(sid=a, name="alpha")
        _, proc_b = self.live(sid=b, name="beta")
        self.pass_(spaced=False)
        self.assertIsNone(threads.get(tb).get("stopped"), "reopened: its stop mark goes")
        self.end(proc_b)
        self.pass_(spaced=False)
        self.pass_(spaced=False)
        self.assertTrue(threads.update(tb, {"stopped": ago(3 * PERIOD), "swept": ago(3 * PERIOD)}))
        open(gate, "w").close()
        self.census_done()
        self.pass_(spaced=False)
        self.assertFalse(self.ended(ta), "reopened during the question")
        self.assertFalse(self.ended(tb), "reopened and stopped again: another stop than the one asked about")
        self.assertTrue(self.is_member(a) and self.is_member(b))


# ------------------------------------------------------------ every runnable fixture


class Isolation(unittest.TestCase):
    """Every runnable test of this suite keeps devcloud out by itself, run
    alone as in the suite: its first import, or its first command, is the
    shared isolation (devcloud_isolation.py, devcloud-isolation.sh)."""

    def test_every_python_test_imports_the_isolation_first(self):
        for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))) + [os.path.join(HERE, "bench_scale.py")]:
            with open(path) as f:
                first = next(line for line in f if line.startswith(("import ", "from ")))
            self.assertTrue(first.startswith("import devcloud_isolation"), os.path.basename(path))

    def test_every_shell_test_sources_the_isolation_first(self):
        for path in sorted(glob.glob(os.path.join(HERE, "test-*.sh"))):
            with open(path) as f:
                lines = [line for line in f.read().splitlines()[1:] if line.strip() and not line.startswith("#")]
            self.assertIn("devcloud-isolation.sh", lines[0], os.path.basename(path))

    def test_the_isolation_points_at_the_stand_in_and_drops_devclouds_variables(self):
        env = dict(os.environ, DEVCLOUD_SEED_FILE="/nonexistent/seed.json", DEVCLOUD_PROFILE="/nonexistent/p")
        env.pop("SMINOS_DEVCLOUD", None)
        out = subprocess.run(["bash", "-c", '. "$1"; env', "-", os.path.join(HERE, "devcloud-isolation.sh")],
                             env=env, capture_output=True, text=True, timeout=30).stdout
        self.assertIn("SMINOS_DEVCLOUD=%s" % STANDIN, out)
        self.assertNotIn("DEVCLOUD_", out.replace("SMINOS_DEVCLOUD", ""))
        code = "import os, devcloud_isolation; print(sorted(k for k in os.environ if 'DEVCLOUD' in k), " \
               "os.environ['SMINOS_DEVCLOUD'])"
        out = subprocess.run([sys.executable, "-c", code], env=env, cwd=HERE, capture_output=True, text=True,
                             timeout=30).stdout
        self.assertEqual(out.strip(), "['SMINOS_DEVCLOUD'] %s" % STANDIN)


def killed(pid):
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGKILL)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)   # a child of this process (none here) would be a zombie
        return waited == 0
    except ChildProcessError:
        return not zombie(pid)


def zombie(pid):
    try:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip().startswith("Z") or not out.strip()


if __name__ == "__main__":
    unittest.main()
