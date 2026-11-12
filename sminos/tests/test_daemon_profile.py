#!/usr/bin/env python3
"""`sminos daemon profile`: the running `daemon run`, or its uplink, profiles
itself for a few seconds when asked, and the verb prints where its time
went. Asked through a request file and the nudge both loops already watch,
so a loop with no request makes no new read, and a process on older code
ticks once and is otherwise untouched; the verb says when it did not take
the request. A profile holds function names and counts, never arguments.
Hermetic: every test has its own HOME and SMINOS_HOME under /tmp.
Run: python3 -B sminos/tests/test_daemon_profile.py
"""

import builtins
import contextlib
import fcntl
import io
import json
import marshal
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "sminos" / "scripts"
CLI = str(SCRIPTS / "sminos.py")
BASE = os.path.realpath(tempfile.mkdtemp(prefix="smp.", dir="/tmp"))
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import sminos  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_profile as profile  # noqa: E402
import sminos_uplink as uplink  # noqa: E402
import endpoint_standin  # noqa: E402
from rl10_identity import write_identity  # noqa: E402


def wait_for(test, timeout=10.0, every=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = test()
        if got:
            return got
        time.sleep(every)
    return None


class Paths:
    """Every path the file calls were made on while installed (open, os.open,
    stat, lstat, listdir, scandir, utime)."""

    def __init__(self):
        self.seen = []

    @contextlib.contextmanager
    def counting(self):
        real = {"open": builtins.open, "os.open": os.open, "stat": os.stat, "lstat": os.lstat,
                "listdir": os.listdir, "scandir": os.scandir, "utime": os.utime}

        def wrap(fn):
            def call(*args, **kwargs):
                if args and isinstance(args[0], (str, bytes, os.PathLike)):
                    self.seen.append(os.fsdecode(args[0]))
                return fn(*args, **kwargs)
            return call
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("builtins.open", wrap(real["open"])))
            for name in ("open", "stat", "lstat", "listdir", "scandir", "utime"):
                stack.enter_context(mock.patch("os." + name, wrap(real["os." + name if name == "open" else name])))
            yield self

    def about_profiles(self):
        return [p for p in self.seen if "profile" in os.path.basename(p)]


class Lane:
    def __init__(self):
        self.sent = []

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            then()

    def posting(self):
        return False

    def queued(self):
        return 0

    def close(self):
        pass


class Home(unittest.TestCase):
    """A fresh SMINOS_HOME per test, `testhost` cut over into org-1."""

    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"))
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        write_identity(os.environ["SMINOS_HOME"])
        sminos.forget_caches()
        profile._reset()

    def tearDown(self):
        profile._reset()

    def request(self, of="uplink", seconds=0.5, **fields):
        req = profile.new_request(of, seconds)
        req.update(fields)
        sminos.write_json(profile.request_path(of), req)
        return req

    def result(self, of, req, timeout=10):
        path = profile.result_path(of, req["id"], ".json")
        self.assertTrue(wait_for(lambda: os.path.exists(path), timeout), "a result came back")
        with open(path) as f:
            return path, json.load(f)


# ------------------------------------------------------------- the loops' idle cost


class IdleCost(Home):
    def link(self):
        cred = {"org": "org-1", "hub": "http://127.0.0.1:9", "machine": "testhost", "key": None}
        link = uplink.Link(cred, {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.members_before = lambda project, sessions: True
        return link

    def test_an_uplink_tick_with_no_nudge_reads_no_request(self):
        link = self.link()
        link.tick()
        paths = Paths()
        with paths.counting():
            for _ in range(5):
                link.tick()
        self.assertEqual(paths.about_profiles(), [], "an un-nudged tick never looks for a profile request")

    def test_a_nudged_uplink_tick_looks_once_and_takes_its_own_request(self):
        link = self.link()
        link.tick()
        self.request("run")
        sminos.nudge_daemon()
        paths = Paths()
        with paths.counting():
            link.tick()
        self.assertEqual(paths.about_profiles(), [profile.request_path("uplink")], "one look, at its own request")
        self.assertTrue(os.path.exists(profile.request_path("run")), "the other process's request is left")
        os.unlink(profile.request_path("run"))
        req = self.request("uplink")
        sminos.nudge_daemon()
        link.tick()
        self.assertFalse(os.path.exists(profile.request_path("uplink")), "taken")
        _, got = self.result("uplink", req)
        self.assertEqual(got["of"], "uplink")
        self.assertEqual(got["pid"], os.getpid())

    def test_the_run_loops_watch_looks_only_at_a_new_nudge(self):
        watch = profile.Watch("run")
        paths = Paths()
        with paths.counting():
            watch.look(5)
            watch.look(5)
            watch.look(5)
        self.assertEqual(paths.about_profiles(), [profile.request_path("run")], "the first look, then none")
        paths = Paths()
        with paths.counting():
            watch.look(6)
            watch.look(6)
            watch.after_pass()
        self.assertEqual(paths.about_profiles(), [profile.request_path("run")], "one look for the new nudge")


# ------------------------------------------------------------- the request and the window


class Window(Home):
    def test_a_window_profiles_every_thread_into_private_files_of_names_and_counts(self):
        req = self.request("run", seconds=0.6)
        watch = profile.Watch("run")
        watch.look(1)
        self.assertFalse(os.path.exists(profile.request_path("run")), "taken")
        watch.after_pass()

        def secret_worker_fn(word):
            for _ in range(20):
                os.stat(os.environ["SMINOS_HOME"])
            return word.upper()
        t = threading.Thread(target=secret_worker_fn, args=("SECRET-ARGUMENT-%s" % os.getpid(),))
        t.start()
        t.join()
        path, got = self.result("run", req)
        prof = profile.result_path("run", req["id"], ".prof")
        for p in (path, prof):
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600, p)
        self.assertEqual(got["id"], req["id"])
        self.assertGreater(got["to"] - got["from"], 0.5)
        self.assertIsInstance(got["cpu"], float)
        with open(prof, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"SECRET-ARGUMENT", raw, "no argument is kept")
        stats = marshal.loads(raw)
        names = {k[2] for k in stats}
        self.assertIn("secret_worker_fn", names, "a thread other than the one that began it is seen")
        self.assertIn("<built-in method posix.stat>", names)
        for (fn, line, name), (cc, nc, tt, ct, callers) in stats.items():
            self.assertIsInstance(fn, str)
            self.assertIsInstance(line, int)
            self.assertIsInstance(name, str)
            for n in (cc, nc):
                self.assertIsInstance(n, int)
            for t_ in (tt, ct):
                self.assertIsInstance(t_, float)
            for k, v in callers.items():
                self.assertEqual(len(k), 3)
                self.assertTrue(all(isinstance(x, (int, float)) for x in v))

    def test_a_request_while_one_runs_is_refused_with_why(self):
        first = self.request("run", seconds=1.5)
        watch = profile.Watch("run")
        watch.look(1)
        watch.after_pass()
        second = self.request("run", seconds=1)
        watch.look(2)
        watch.after_pass()
        _, got = self.result("run", second, timeout=3)
        self.assertIn("already", got["refused"])
        _, done = self.result("run", first)
        self.assertNotIn("refused", done)

    def test_a_stale_or_malformed_request_is_removed_and_not_taken(self):
        self.request("run", at=time.time() - 3600)
        self.assertIsNone(profile.take("run"))
        self.assertFalse(os.path.exists(profile.request_path("run")))
        for bad in ({"id": "../../x", "seconds": 1}, {"seconds": -1}, {"seconds": 10 ** 6}):
            self.request("run", **bad)
            self.assertIsNone(profile.take("run"), bad)
            self.assertFalse(os.path.exists(profile.request_path("run")))
        with open(profile.request_path("run"), "w") as f:
            f.write("not json")
        self.assertIsNone(profile.take("run"))
        self.assertFalse(os.path.exists(profile.request_path("run")))

    def test_a_refusal_that_cannot_be_written_never_reaches_the_loop(self):
        self.request("run")
        watch = profile.Watch("run")
        watch.look(1)
        logged = []
        full = OSError(28, "No space left on device")
        with mock.patch.object(profile.sys, "version_info", (3, 11, 9)), \
                mock.patch.object(profile, "_private", side_effect=full), \
                mock.patch.object(profile.sminos, "daemon_log", side_effect=logged.append):
            watch.after_pass()
        self.assertEqual(len(logged), 1, logged)
        self.assertIn("not written", logged[0])
        with mock.patch.object(profile, "_private", side_effect=full), \
                mock.patch.object(profile, "_begin", side_effect=RuntimeError("boom")), \
                mock.patch.object(profile.sminos, "daemon_log", side_effect=OSError(28, "full")):
            self.request("run")
            watch.look(2)
            watch.after_pass()   # nor when daemon.log cannot be written either

    def test_an_unexpected_error_in_noticing_never_reaches_the_loop(self):
        logged = []
        with mock.patch.object(profile, "take", side_effect=RuntimeError("boom")), \
                mock.patch.object(profile.sminos, "daemon_log", side_effect=logged.append):
            profile.noticed("uplink")
            profile.Watch("run").look(1)
        self.assertEqual(len(logged), 2, logged)
        self.assertIsNone(profile._STATE["pending"])

    def test_a_start_that_fails_after_enable_leaves_no_profiler_running(self):
        req = self.request("run", seconds=0.5)
        watch = profile.Watch("run")
        watch.look(1)
        with mock.patch.object(threading.Timer, "start", side_effect=RuntimeError("can't start new thread")):
            watch.after_pass()
        _, got = self.result("run", req, timeout=3)
        self.assertIn("could not begin", got["refused"])
        self.assertIsNone(profile._STATE["running"], "no window is left counted as running")
        self.assertIsNone(sys.monitoring.get_tool(sys.monitoring.PROFILER_ID), "the profiler is disabled")
        again = self.request("run", seconds=0.2)
        watch.look(2)
        watch.after_pass()
        _, done = self.result("run", again)
        self.assertNotIn("refused", done, "the next request profiles")

    def test_only_the_newest_profiles_are_kept(self):
        for _ in range(profile.KEEP + 2):
            req = self.request("run", seconds=0.05)
            watch = profile.Watch("run")
            watch.look(1)
            watch.after_pass()
            self.result("run", req)
            time.sleep(0.01)
        kept = [n for n in os.listdir(os.path.join(os.environ["SMINOS_HOME"], "daemon"))
                if n.startswith("profile-run-") and n.endswith(".prof")]
        self.assertEqual(len(kept), profile.KEEP)


# ------------------------------------------------------------- the verb's refusals


class Refusals(Home):
    def verb(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                sminos.main(["daemon", "profile"] + list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_no_daemon_here(self):
        code, _, err = self.verb()
        self.assertEqual(code, 1)
        self.assertIn("no daemon runs here", err)
        self.assertFalse(os.path.exists(profile.request_path("uplink")))

    def test_bad_arguments(self):
        for argv in (["--seconds", "0"], ["--seconds", "100000"], ["--of", "both"]):
            code, _, err = self.verb(*argv)
            self.assertNotEqual(code, 0, argv)

    def hold(self, name):
        """A process holding daemon/<name> as a daemon on older code holds
        it: it watches no request and only ticks at a nudge."""
        path = daemon.daemon_path(name)
        p = subprocess.Popen([sys.executable, "-c", (
            "import fcntl, sys, time\n"
            "f = open(sys.argv[1], 'a+'); fcntl.flock(f, fcntl.LOCK_EX); f.seek(0); f.truncate()\n"
            "f.write('pid %d since then' % __import__('os').getpid()); f.flush()\n"
            "print('held', flush=True)\n"
            "time.sleep(120)\n"), path], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close()))
        self.assertEqual(p.stdout.readline().strip(), "held")
        return p

    def test_a_daemon_on_older_code_is_untouched_and_said_so(self):
        old = self.hold("run.lock")
        with mock.patch.object(profile, "TAKE_WITHIN", 1.0):
            code, _, err = self.verb("--of", "run", "--seconds", "1")
        self.assertEqual(code, 1)
        self.assertIn("did not take", err)
        self.assertIn("pid %d" % old.pid, err)
        self.assertIsNone(old.poll(), "the process runs on")
        self.assertFalse(os.path.exists(profile.request_path("run")), "the request is withdrawn")

    def test_a_request_already_waiting_for_the_process_is_left_and_the_verb_refuses(self):
        self.hold("run.lock")
        waiting = self.request("run", seconds=5)
        code, _, err = self.verb("--of", "run", "--seconds", "1")
        self.assertEqual(code, 1)
        self.assertIn("already waiting", err)
        with open(profile.request_path("run")) as f:
            self.assertEqual(json.load(f)["id"], waiting["id"], "the waiting request is untouched")

    def test_a_stale_waiting_request_is_replaced(self):
        self.hold("run.lock")
        self.request("run", at=time.time() - profile.STALE - 5)
        seen = []

        def watch():
            def own():
                try:
                    with open(profile.request_path("run")) as f:
                        got = json.load(f)
                except (OSError, ValueError):
                    return None
                return got if abs(time.time() - got["at"]) < 60 else None
            seen.append(wait_for(own, timeout=5))
        t = threading.Thread(target=watch)
        t.start()
        with mock.patch.object(profile, "TAKE_WITHIN", 1.0):
            code, _, err = self.verb("--of", "run", "--seconds", "1")
        t.join()
        self.assertEqual(code, 1)
        self.assertIn("did not take", err)
        self.assertTrue(seen[0], "the verb's own request replaced the stale one")
        self.assertFalse(os.path.exists(profile.request_path("run")), "and is withdrawn")

    def test_a_request_replaced_by_another_counts_as_taken_and_the_other_is_kept(self):
        self.hold("run.lock")
        other = profile.new_request("run", 3)

        def replace():
            def mine():
                try:
                    with open(profile.request_path("run")) as f:
                        return json.load(f)["id"] != other["id"]
                except (OSError, ValueError):
                    return False
            wait_for(mine, timeout=5)
            sminos.write_json(profile.request_path("run"), other)
        t = threading.Thread(target=replace)
        t.start()
        with mock.patch.object(profile, "RESULT_GRACE", 0.3):
            code, out, err = self.verb("--of", "run", "--seconds", "0.2")
        t.join()
        self.assertIn("took the request", out)
        self.assertEqual(code, 1)
        self.assertIn("no profile came back", err)
        with open(profile.request_path("run")) as f:
            self.assertEqual(json.load(f)["id"], other["id"], "the other request is never withdrawn")

    def test_a_withdrawal_removes_only_its_own_request(self):
        mine, other = profile.new_request("run", 1), profile.new_request("run", 1)
        path = profile.request_path("run")
        sminos.write_json(path, other)
        self.assertFalse(profile._withdraw(path, mine["id"]), "another's request is not withdrawn")
        with open(path) as f:
            self.assertEqual(json.load(f)["id"], other["id"])
        os.unlink(path)
        self.assertFalse(profile._withdraw(path, mine["id"]), "nothing there: taken")
        sminos.write_json(path, mine)
        self.assertTrue(profile._withdraw(path, mine["id"]))
        self.assertFalse(os.path.exists(path))
        self.assertEqual([n for n in os.listdir(os.path.dirname(path)) if "request" in n], [], "nothing left aside")

    def test_no_uplink_here(self):
        self.hold("run.lock")
        code, _, err = self.verb("--of", "uplink")
        self.assertEqual(code, 1)
        self.assertIn("no uplink runs here", err)


# ------------------------------------------------------------- a live daemon


class LiveDaemon(unittest.TestCase):
    """The real `daemon run --interval 1` and its uplink on a machine cut
    over to the endpoint stand-in."""

    @classmethod
    def setUpClass(cls):
        cls.saved = dict(os.environ)
        cls.base = tempfile.mkdtemp(prefix="smq.", dir="/tmp")
        os.environ.update(HOME=os.path.join(cls.base, "h"), SMINOS_HOME=os.path.join(cls.base, "s"),
                          MAWS_USER_DATA=os.path.join(cls.base, "m"))
        os.makedirs(os.path.join(os.environ["HOME"], ".claude", "sessions"))
        bindir = os.path.join(cls.base, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "claude"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
        os.chmod(os.path.join(bindir, "claude"), 0o755)
        os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        write_identity(os.environ["SMINOS_HOME"])
        sminos.forget_caches()
        sminos.audience_module().keep_capabilities([])
        cls.ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"))
        cls.ep.start()
        cls.loop = subprocess.Popen([sys.executable, "-B", CLI, "daemon", "run", "--interval", "1"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        up = wait_for(lambda: daemon.held_by(daemon.daemon_path("uplink.lock")) and cls.ep.frames(), timeout=30)
        if not up:
            cls.tearDownClass()
            raise AssertionError("the uplink connected to the endpoint")

    @classmethod
    def tearDownClass(cls):
        cls.loop.send_signal(signal.SIGTERM)
        try:
            cls.loop.wait(20)
        except subprocess.TimeoutExpired:
            cls.loop.kill()
            cls.loop.wait()
        cls.ep.stop()
        os.environ.clear()
        os.environ.update(cls.saved)
        sminos.forget_caches()
        shutil.rmtree(cls.base, ignore_errors=True)

    def verb(self, *argv):
        return subprocess.run([sys.executable, "-B", CLI, "daemon", "profile"] + list(argv),
                              capture_output=True, text=True, timeout=120)

    def profiled(self, out):
        line = [x for x in out.splitlines() if x.startswith("written to ")]
        self.assertTrue(line, out)
        path = line[0][len("written to "):].split(" (")[0]
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path, "rb") as f:
            return marshal.load(f)

    def test_the_uplink_profiles_itself(self):
        r = self.verb("--seconds", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sys.stderr.write("\n--- daemon profile (the uplink, 2 s) ---\n%s---\n" % r.stdout)
        up = daemon.held_by(daemon.daemon_path("uplink.lock"))
        self.assertIn("profile of the uplink (pid %s" % up.split()[1], r.stdout)
        for word in ("CPU", "calls a second", "file calls:", "posix.stat", "open", "listdir", "scandir", "lstat",
                     "most time of their own"):
            self.assertIn(word, r.stdout)
        files = {k[0] for k in self.profiled(r.stdout)}
        self.assertTrue(any(f.endswith("sminos_uplink.py") for f in files), "the uplink's own code")
        self.assertIsNone(self.loop.poll(), "the daemon runs on")

    def test_daemon_run_profiles_itself(self):
        r = self.verb("--of", "run", "--seconds", "1.5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("profile of daemon run (pid %d" % self.loop.pid, r.stdout)
        files = {k[0] for k in self.profiled(r.stdout)}
        self.assertTrue(any(f.endswith("sminos_daemon.py") for f in files), "the loop's own code")
        self.assertIsNone(self.loop.poll())


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(BASE, ignore_errors=True)
