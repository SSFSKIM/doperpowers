#!/usr/bin/env python3
"""`sminos spawn --on <vm>|new`, the Mac side, and the outcome line both
sides share (EN.G1's plan, M3:
docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, Interfaces
§7 and §8).

- Each refusal sminos decides alone, by its exit and its words, with
  devcloud's stand-in not called where devcloud is not run: usage, a host,
  a Mac not enrolled, this machine named, a session with no address, a
  project this enrollment does not carry (each reason by itself, and
  `not_carried` agreeing with the uplink's `hub_projects`), the reach rule
  (read-only: the record store unchanged), no devcloud or an old one.
- `--on new`: what `vm up` is called with; the projects read in the
  caller's own worktree and asked of origin by the exact ref (two linked
  worktrees, a worktree's own origin, a branch origin lacks while it holds
  `x/<branch>`, a commit ahead, no branch, no GitHub, no answer); devcloud
  reading another creator; the checkout at another commit; the reach
  narrowed while the VM is made and between two tries of the wait.
- The outcome line: one whole line, last, held to the call; every other
  shape is an outcome that is not known, never tried again (a `channels`
  key a Mac that asked none ignores, whatever it holds: EN.G2's §1); and
  the VM side's own line, for each way it ends, read by the same check.
- --channel's VM side (EN.G2's §1), among the rest: a channel the org's
  directory retired is refused before the launch though no registration
  of it is here.

Hermetic: test_threads.Machine's temporary HOME and SMINOS_HOME, cut over
as an endpoint's welcome leaves a machine (daemon/identity.json); origins
read as GitHub's and resolve through git's insteadOf to local bare
repositories; devcloud is its stand-in (devcloud_isolation.py), whose
`vm ssh` here answers what a test sets, under a fixed nonce.
Run: python3 -B sminos/tests/test_on.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import types
import unittest
import uuid as uuidlib
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from test_threads import Machine, records, sminos  # noqa: E402
import sminos_on as on  # noqa: E402
import sminos_uplink  # noqa: E402

NONCE = "0123456789abcdef"
ORIGIN = "https://github.com/example/repo"
KEY = "github.com/example/repo"
SEAT = "6f0e9d8c-7b6a-4594-8382-716253443526"
JOB = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
DROP = object()   # a key taken out of a request
DEVCLOUD = os.path.join(os.path.dirname(os.path.dirname(HERE)), "devcloud")
# spawn --on --channel (EN.G2's M1): channels' ids (version 8), registered as the org's directory registers one
DESK = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"
LOBBY = "0123abcd-4567-8abc-a123-456789abcdef"
HUB = {"url": "http://127.0.0.1:9", "org": "org-1"}


def register(cid, name, hub=None):
    sminos.register_if_absent(sminos.make_project(cid, name, "", "", hub or HUB))
    sminos.forget_caches()


def ids(n):
    return ["%08x-0000-8000-8000-000000000000" % i for i in range(1, n + 1)]


def devcloud_python():
    """A Python devcloud runs under (3.11 or later, found as devcloud/bin/devcloud finds one), or None."""
    if sys.version_info >= (3, 11):
        return sys.executable
    for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3"):
        found = shutil.which(name)
        if found and subprocess.run([found, "-c", "import sys; sys.exit(sys.version_info < (3, 11))"],
                                    capture_output=True).returncode == 0:
            return found
    return None


PARSER_PROBE = """import json, sys
sys.path[:0] = sys.argv[1:3]
from driver import cli
print(json.dumps(vars(cli.parser().parse_args(json.loads(sys.argv[3]))), default=repr))"""


def devcloud_reads(argv):
    """What devcloud's own `vm` parser, from this tree (devcloud/driver/cli.py), reads `argv` as: imported, never
    run (no devcloud process, profile or provider), under a Python devcloud accepts, since its modules need 3.11
    (tomllib) and sminos runs on 3.10. Skipped where there is none, as devcloud itself could not run there."""
    py = devcloud_python()
    if py is None:
        raise unittest.SkipTest("devcloud's parser needs Python 3.11 or later, and none is on PATH")
    done = subprocess.run([py, "-B", "-I", "-c", PARSER_PROBE, DEVCLOUD, os.path.join(DEVCLOUD, "boot"),
                           json.dumps(argv)], capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError("devcloud's parser did not read %r: %s" % (argv, done.stderr))
    return types.SimpleNamespace(**json.loads(done.stdout))


REMOTE_HEAD = ["env", "-u", "CLAUDE_CODE_SESSION_ID", "sminos"]   # the session variable cleared there (H3)


def vm_side(argv):
    """The VM side's words of a `vm ssh` call (everything after its `--` but its head, `sminos` started with the
    session variable cleared), read by sminos's own parser as the VM's sminos reads them."""
    words = argv[argv.index("--") + 1:]
    assert words[:len(REMOTE_HEAD)] == REMOTE_HEAD, words
    return sminos.build_parser().parse_args(words[len(REMOTE_HEAD):])


def gitq(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main",
                           *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@contextlib.contextmanager
def piped(data):
    """Standard input holding `data` (bytes), as a pipe gives it; as it was where `data` is None."""
    if data is None:
        yield
        return
    with mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(data))):
        yield


def stop_soon(when):
    """SIGTERM to this process, from a thread, once `when()` holds (within 20 s)."""
    def go():
        end = time.monotonic() + 20
        while not when() and time.monotonic() < end:
            time.sleep(0.02)
        time.sleep(0.1)
        os.kill(os.getpid(), signal.SIGTERM)
    t = threading.Thread(target=go)
    t.start()
    return t


class On(Machine):
    def setUp(self):
        super().setUp()
        h = os.environ["HOME"]
        # git here reaches local repositories only: an origin no insteadOf rewrites fails, never reaches a network.
        allow = mock.patch.dict(os.environ, {"GIT_ALLOW_PROTOCOL": "file"})
        allow.start()
        self.addCleanup(allow.stop)
        self.bare = os.path.join(self.home, "origin.git")
        gitq("init", "-q", "--bare", self.bare)
        with open(os.path.join(h, ".gitconfig"), "w") as f:
            f.write('[url "%s"]\n\tinsteadOf = %s\n' % (self.bare, ORIGIN))
        self.work = os.path.join(self.home, "repo")
        gitq("init", "-q", self.work)
        gitq("remote", "add", "origin", ORIGIN, cwd=self.work)
        gitq("checkout", "-q", "-b", "topic", cwd=self.work)
        gitq("commit", "-q", "--allow-empty", "-m", "one", cwd=self.work)
        gitq("push", "-q", "origin", "topic", cwd=self.work)
        self.commit = gitq("rev-parse", "HEAD", cwd=self.work)
        self.enroll()
        self.cfg = {"ssh_hosts": {}}
        self.save()
        self.sid, self.proc = self.session(root=self.work)
        self.recorded(self.sid)

    # --- the machine and the session

    def enroll(self, org="org-1"):
        d = os.path.join(os.environ["SMINOS_HOME"], "daemon")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "identity.json"), "w") as f:
            json.dump({"org": org, "hub": "http://127.0.0.1:9", "name": "testhost", "former": {}, "ref": "ref-1",
                       "enrolled": "2026-11-05T00:00:00.000Z", "cutover": "2026-11-05T00:00:01.000Z",
                       "build": "b"}, f)
        os.chmod(os.path.join(d, "identity.json"), 0o600)
        sminos.forget_caches()

    def unenroll(self):
        os.unlink(os.path.join(os.environ["SMINOS_HOME"], "daemon", "identity.json"))
        sminos.forget_caches()

    def recorded(self, sid, **policy):
        """The session's record as its own hook writes one (final, resting on the hook), with `policy`; then a
        member of its project, a thread, as a reading verb leaves it."""
        records.establish(sid, {**records.default_provenance("hook"), **policy})
        sminos.forget_caches()
        root = (sminos.session_running(sid) or {}).get("cwd")
        if not policy and root and sminos.resolve_project(root) is not None:
            self.reconcile(sminos.resolve_project(root))

    def store(self):
        d = records.records_dir()
        out = {}
        for root, _, files in os.walk(d):
            for n in files:
                with open(os.path.join(root, n), "rb") as f:
                    out[os.path.relpath(os.path.join(root, n), d)] = f.read()
        return out

    # --- devcloud's stand-in

    def save(self):
        with open(os.path.join(os.environ["HOME"], "devcloud-standin.json"), "w") as f:
            json.dump(self.cfg, f)

    def calls(self):
        try:
            with open(os.path.join(os.environ["HOME"], "devcloud-standin.calls")) as f:
                return [json.loads(line)["argv"] for line in f]
        except OSError:
            return []

    def forget_calls(self):
        with contextlib.suppress(FileNotFoundError):
            os.unlink(os.path.join(os.environ["HOME"], "devcloud-standin.calls"))

    def verbs(self):
        return [c[1] for c in self.calls()]

    def answers(self, vm, *lines, code=0):
        """`vm ssh <vm>` printing `lines` and exiting `code`, nothing run."""
        self.cfg["ssh_hosts"][vm] = {"stdout": "".join(line + "\n" for line in lines), "exit": code}
        self.save()

    def spawned(self, **over):
        d = {"ok": True, "refilled": False, "group": "repo", "alias": "w", "short": "a1b2c3d4", "seat": SEAT,
             "session": JOB, "status": "working", "project": {"id": "p-id", "name": "repo"}, "machine": "vm1",
             "cwd": "/home/u/Developer/GitHub/repo", "head": self.commit}
        d.update(over)
        return on.outcome_line(NONCE, d)

    # --- the verb

    def spawn(self, *argv, session=True, cwd=None, alias="w", task="a task", stdin=None):
        """(exit, stdout, stderr) of `sminos spawn <alias> <task> <argv>` (sminos_argv)."""
        return self.sminos_argv("spawn", alias, task, *argv, session=session, cwd=cwd, stdin=stdin)

    def sminos_argv(self, *argv, session=True, cwd=None, stdin=None):
        """(exit, stdout, stderr) of `sminos <argv>` run here, `argv` whole, from the session (or a terminal), under
        a fixed nonce; `stdin`, bytes, piped to it."""
        out, err = io.StringIO(), io.StringIO()
        env = {"CLAUDE_CODE_SESSION_ID": self.sid} if session else {}
        here = os.getcwd()
        os.chdir(cwd or self.work)
        try:
            with mock.patch.dict(os.environ, env), mock.patch.object(on.secrets, "token_hex", return_value=NONCE), \
                    piped(stdin), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                if not session:
                    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                try:
                    sminos.main(list(argv))
                    code = 0
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 1
        finally:
            os.chdir(here)
            sminos.forget_caches()
        return code, out.getvalue(), err.getvalue()

    def refused(self, want_code, words, *argv, called=(), **kw):
        code, out, err = self.spawn(*argv, **kw)
        self.assertEqual(code, want_code, out + err)
        self.assertIn(words, err)
        self.assertNotIn("seat spawned on", out)
        self.assertEqual(self.verbs(), list(called), "devcloud called as the table says")
        return out, err


class Usage(On):
    def test_each_usage_refusal_is_2_and_calls_nothing(self):
        for argv, words in (
                (["--on", "vm1", "--vm-project", "a/b"], "--vm-project and --vm-confirmed are for the VM that "
                                                         "--on new makes: drop them, or pass --on new"),
                (["--on", "vm1", "--vm-confirmed"], "--vm-project and --vm-confirmed are for the VM"),
                (["--on", "vm1", "--wait"], "spawn --on: --wait watches a seat of this machine"),
                (["--on", "new", "--settings", "{}"], "spawn --on: --settings names a file of this machine"),
                (["--on", "vm1", "--cwd", "work/x"], "spawn --on: --cwd is a path on the other machine"),
                (["--on", "testhost"], "spawn --on: testhost is this machine: drop --on"),
                (["--on", "TestHost"], "spawn --on: TestHost is this machine: drop --on")):
            with self.subTest(argv=argv):
                self.refused(2, words, *argv)

    def test_on_a_devcloud_host_it_is_refused(self):
        marker = os.path.join(self.home, "boot.env")
        open(marker, "w").close()
        with mock.patch.object(on, "HOST_MARKER", marker):
            self.refused(1, "spawn --on: this machine is a devcloud host", "--on", "vm1")

    def test_a_mac_not_enrolled_is_refused_before_devcloud(self):
        self.unenroll()
        for vm in ("vm1", "new"):
            with self.subTest(vm=vm):
                self.refused(1, "spawn --on: this machine is not enrolled in the org", "--on", vm)

    def test_no_devcloud_and_an_old_one(self):
        with mock.patch.object(sminos.threads_module(), "find_devcloud", return_value=(None, "PATH (none)")):
            self.refused(1, "spawn --on: no devcloud CLI was found here (looked at: PATH (none))", "--on", "vm1")
        plugin = os.path.join(self.home, "devcloud")
        os.makedirs(os.path.join(plugin, "bin"))
        os.makedirs(os.path.join(plugin, ".claude-plugin"))
        cli = os.path.join(plugin, "bin", "devcloud")
        open(cli, "w").close()
        with open(os.path.join(plugin, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"version": "0.17.3"}, f)
        with mock.patch.object(sminos.threads_module(), "find_devcloud", return_value=("PATH", cli)):
            self.refused(1, "spawn --on: the devcloud at %s is 0.17.3, and spawn --on needs 0.18.0 or later" % cli,
                         "--on", "vm1")


    def test_vm_flags_without_on_are_row_1_and_nothing_is_launched(self):
        with mock.patch.object(sminos, "run_claude_bg") as launch:
            for argv in (["--vm-project", "a/b"], ["--vm-confirmed"]):
                with self.subTest(argv=argv):
                    self.refused(2, "--vm-project and --vm-confirmed are for the VM that --on new makes: drop them, "
                                    "or pass --on new", *argv)
        launch.assert_not_called()

    def test_an_empty_task_is_refused_before_devcloud_runs(self):
        for where in ("vm1", "new"):
            with self.subTest(where=where):
                self.answers("vm1", self.spawned())
                self.refused(2, "spawn --on: the task is empty", "--on", where, task="")
                self.assertEqual(self.calls(), [], "devcloud never called")

    def test_a_malformed_stamp_is_refused_before_devcloud_runs(self):
        for where, stamp, words in (("vm1", "nofield", "--stamp takes field=value: nofield"),
                                    ("new", "=x", "--stamp takes field=value: =x"),
                                    ("new", "a_token=1", "'a_token' is a credential field")):
            with self.subTest(where=where, stamp=stamp):
                self.answers("vm1", self.spawned())
                self.refused(2, words, "--on", where, "--stamp", stamp)

    def test_the_fixtures_git_reaches_local_repositories_only(self):
        done = subprocess.run(["git", "ls-remote", "https://127.0.0.1:9/example/repo"], capture_output=True,
                              text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("transport 'https' not allowed", done.stderr)


class RouteBack(On):
    def test_a_session_with_no_address_is_refused(self):
        self.sid = str(uuidlib.uuid4())   # no process, no membership
        self.refused(1, "spawn --on: this session is no member of a project yet", "--on", "vm1")

    def test_a_project_this_enrollment_does_not_carry_each_reason_by_itself(self):
        def smns(d, **hub):
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, ".smns"), "w") as f:
                json.dump({"project": str(uuidlib.uuid4()), "name": os.path.basename(d), "remote": "",
                           **({"hub": hub} if hub else {})}, f)
            return d

        local = smns(os.path.join(self.home, "local"))
        other = smns(os.path.join(self.home, "other"), org="org-2")
        retired = smns(os.path.join(self.home, "retired"), org="org-1")
        left = smns(os.path.join(self.home, "left"), org="org-1")
        shared = smns(os.path.join(self.home, "shared"), org="org-1")
        ids = {d: self.project_of(d).id for d in (local, other, retired, left, shared)}
        daemon = os.path.join(os.environ["SMINOS_HOME"], "daemon")
        with open(os.path.join(daemon, "org.json"), "w") as f:
            json.dump({"projects": [{"id": ids[retired], "retired": True}], "machines": [], "at": ""}, f)
        with open(os.path.join(daemon, "leaving.json"), "w") as f:
            json.dump({"counted": {}, "left": [ids[left]]}, f)
        sminos.forget_caches()
        cases = ((local, "it syncs through no hub"), (other, "its .smns names another org"),
                 (retired, "the org's directory has retired it"), (left, "it has left this machine"))
        for d, why in cases:
            with self.subTest(why=why):
                self.sid, _ = self.session(root=d)
                self.recorded(self.sid)
                self.refused(1, "spawn --on: this session's project, %s, is not one this machine's enrollment carries "
                                "(%s)" % (os.path.basename(d), why), "--on", "vm1", cwd=d)
        sminos.forget_caches()
        opened = sminos_uplink.hub_projects({"org": "org-1"})
        for d in (local, other, retired, left, shared):
            p = sminos.resolve_project(d)
            with self.subTest(project=os.path.basename(d)):
                self.assertEqual(p.id in opened, not sminos.not_carried(p, "org-1"))
        self.assertIn(ids[shared], opened)


    def test_the_spawner_is_named_from_its_record_whatever_its_projects_name(self):
        """The request's `by` is the spawner's alias, short id and project as sminos holds them, never read back
        out of its address line: a project named with spaces and parentheses keeps the alias (G7)."""
        d = os.path.join(self.home, "spaced")
        os.makedirs(d)
        pid = str(uuidlib.uuid4())
        with open(os.path.join(d, ".smns"), "w") as f:
            json.dump({"project": pid, "name": "Build Tools (Core)", "remote": "", "hub": {"org": "org-1"}}, f)
        self.sid, _ = self.session(root=d)
        self.recorded(self.sid)
        address = sminos.session_address(self.sid, d)
        self.assertTrue(address.endswith(" (Build Tools (Core) on testhost)"), address)
        alias = address[len("Sminos-Session: "):].split("#", 1)[0]
        self.assertNotEqual(alias, self.sid[:8], "a session with an alias")
        sent = {}

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            sent["args"] = args
            return 0, [self.spawned()], "", False, True
        with mock.patch.object(on, "run_devcloud", side_effect=run):
            code, out, err = self.spawn("--on", "vm1", "--cwd", "/srv/x", cwd=d)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(vm_side(sent["args"]).asked_from)["by"],
                         {"alias": alias, "short": self.sid[:8], "project": pid, "project_name": "Build Tools (Core)",
                          "machine": "testhost", "session": self.sid})
        # An alias the address line does not show (parentheses): the line names the short alone, as it did, and
        # the request still names the alias sminos holds.
        self.sid, proc = self.session(root=d, name="Build (Core)")
        self.peer_set(proc, nameSource="user")
        self.recorded(self.sid)
        self.assertEqual(sminos.session_address(self.sid, d),
                         "Sminos-Session: %s (Build Tools (Core) on testhost)" % self.sid[:8])
        self.assertEqual(sminos.address_of(self.sid, d)[0], "Build (Core)")
        with mock.patch.object(on, "run_devcloud", side_effect=run):
            code, out, err = self.spawn("--on", "vm1", "--cwd", "/srv/x", cwd=d)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(vm_side(sent["args"]).asked_from)["by"]["alias"], "Build (Core)")


class Reach(On):
    def test_reach_that_could_not_be_read_refuses_and_nothing_is_written(self):
        job, jproc = self.session(root=self.work, kind="bg")
        self.recorded(job)
        cases = []
        nobody, _ = self.session(root=self.work)
        cases.append((nobody, "it has no record yet: its own hook writes one when a turn ends, and sminos list does"))
        broken, _ = self.session(root=self.work)
        os.makedirs(records.records_dir(), exist_ok=True)
        with open(records.record_path(broken), "w") as f:
            f.write("{not a record")
        cases.append((broken, "its record cannot be read"))
        cases.append((job, "its record is not settled: it is a background job's, which may still take the reach of a "
                           "session it continues; sminos list records a hand-off, and a job that continues none "
                           "spawns from another session"))
        defaults, _ = self.session(root=self.work)
        records.establish(defaults, records.default_provenance())
        cases.append((defaults, "its record is not settled: it rests on this machine's defaults alone until its own "
                                "hook, at the end of a turn, or sminos list gives it more"))
        for sid, why in cases:
            with self.subTest(why=why[:40]):
                self.sid = sid
                before = self.store()
                self.refused(1, "spawn --on: this session's reach could not be read (%s), and a session is opened on "
                                "another machine only from one whose reach is known to be this machine's default: "
                                "nothing was spawned" % why, "--on", "vm1")
                self.assertEqual(self.store(), before, "the reach rule reads and writes nothing")

    def test_reach_not_the_default_refuses_naming_which(self):
        private, _ = self.session(root=self.work)
        self.recorded(private, access="private", shares=[])
        shared, _ = self.session(root=self.work)
        self.recorded(shared, shares=[{"member": "0" * 32, "grade": "view"}])
        for sid, why in ((private, "its access is private"), (shared, "it has shares")):
            with self.subTest(why=why):
                self.sid = sid
                self.refused(1, "spawn --on: this session's reach is not this machine's default (%s)" % why,
                             "--on", "vm1")

    def test_a_settled_default_record_passes_an_owner_added_too(self):
        self.answers("vm1", self.spawned())
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        with_owner, _ = self.session(root=self.work)
        self.recorded(with_owner, owners=["@machine", "1" * 32])
        self.sid = with_owner
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)


    def test_a_process_gone_while_the_vm_is_made_is_not_settled_and_the_vm_is_kept(self):
        for basis in ("hook", "launch"):
            with self.subTest(basis=basis):
                self.forget_calls()
                self.sid, proc = self.session(root=self.work)
                records.establish(self.sid, records.default_provenance(basis))
                sminos.forget_caches()
                self.reconcile(sminos.resolve_project(self.work))
                gate = os.path.join(self.home, "gate-" + basis)
                self.cfg["up"] = {"gate": gate}
                self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))

                def gone():
                    end = time.monotonic() + 20
                    while "up" not in self.verbs() and time.monotonic() < end:
                        time.sleep(0.02)
                    proc.kill()
                    proc.wait()
                    os.unlink(self.peer_path(proc.pid))   # sminos's own copy of the engine's records is not told
                    open(gate, "w").close()
                t = threading.Thread(target=gone)
                t.start()
                out, err = self.refused(1, "spawn --on: this session's reach could not be read (its record is not "
                                           "settled: no running process of it is found on this machine)",
                                        "--on", "new", called=["up"])
                t.join()
                self.assertIn(". The VM dc-x-0001 is kept and", err)


class New(On):
    def up_args(self):
        [up] = [c for c in self.calls() if c[1] == "up"]
        return up[2:]

    def test_what_vm_up_is_called_with(self):
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.up_args(), ["--enroll", "--keep", "--expect-creator=%s" % self.sid[:8], "--label=w",
                                          "--project=example/repo@topic"])
        self.assertIn("sminos: note: making a VM (a few minutes; devcloud's own lines follow): devcloud vm up "
                      "--enroll --keep --expect-creator=%s --label=w --project=example/repo@topic" % self.sid[:8], err)
        lines = out.splitlines()
        self.assertTrue(lines.index("dc-x-0001  ready in 0m01s") < len(lines) - 1, "devcloud's lines come first")
        self.assertEqual(lines[-1], 'seat spawned on dc-x-0001: repo/w  [a1b2c3d4 / %s]  status=working  (message '
                                    'it: sminos say "@%s …"; it is listed here once dc-x-0001\'s events arrive)'
                         % (SEAT, JOB[:8]))
        self.assertIn("sminos: note: dc-x-0001 is kept and this session's thread owns it: devcloud vm down "
                      "dc-x-0001 ends it, and it sends a notice after three idle days", err)
        self.assertNotIn("the VM's checkout is at", err)
        ssh = [c for c in self.calls() if c[1] == "ssh"][0]
        self.assertEqual(ssh[2:4], ["dc-x-0001", "--"])
        # The VM's sminos started with the session variable cleared, for that call alone: a client that sends it
        # and a host that accepts it would otherwise have the transport's call refused as a session's (H3). `vm up`
        # runs here, under this session, as above.
        self.assertEqual(ssh[4:9], ["env", "-u", "CLAUDE_CODE_SESSION_ID", "sminos", "spawn"])
        there = vm_side(ssh)
        request = json.loads(there.asked_from)
        self.assertEqual(request, {"v": 1, "nonce": NONCE, "org": "org-1", "origin": KEY,
                                   "by": {"alias": request["by"]["alias"], "short": self.sid[:8],
                                          "project": sminos.resolve_project(self.work).id,
                                          "project_name": sminos.resolve_project(self.work).name,
                                          "machine": "testhost", "session": self.sid}})
        self.assertEqual(there.cwd, "~/Developer/GitHub/repo")
        self.assertTrue(all(w.startswith(("--asked-from=", "--cwd=", "--permission-mode=")) for w in ssh[9:12]),
                        "each value one word, the request's too: %r" % ssh[9:12])

    def test_devcloud_reads_each_value_of_vm_up_as_it_was_sent(self):
        """Each value `vm up` is given is one `--flag=value` word, read here by devcloud's own parser: a label
        that opens with `-` (an alias after `--`) and a project that does are values, not flags (G3)."""
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", alias="-review"))
        code, out, err = self.sminos_argv("spawn", "--on", "new", "--vm-project=-odd/repo@-ref", "--vm-confirmed",
                                          "--", "-review", "a task")
        self.assertEqual(code, 0, err)
        [up] = [c for c in self.calls() if c[1] == "up"]
        args = devcloud_reads(up[1:])
        self.assertEqual((args.command, args.label, args.project, args.expect_creator, args.enroll, args.keep,
                          args.confirmed), ("up", "-review", ["-odd/repo@-ref"], self.sid[:8], True, True, True))

    def test_label_confirmed_and_named_projects(self):
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", alias="Big_W"))
        gitq("remote", "set-url", "origin", "https://github.com/example/nowhere", cwd=self.work)  # origin unasked
        code, _, err = self.spawn("--on", "new", "--vm-project", "example/repo@main", "--vm-project", "maws",
                                  "--vm-confirmed", alias="Big_W")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.up_args(), ["--enroll", "--keep", "--expect-creator=%s" % self.sid[:8],
                                          "--project=example/repo@main", "--project=maws", "--confirmed"])

    def test_devcloud_reading_another_creator_makes_nothing_and_spawns_nothing(self):
        self.cfg["up"] = {"creator": "ffffffff"}
        self.save()
        out, err = self.refused(1, "spawn --on new: devcloud vm up exited 1; its own lines above say why, and what "
                                   "became of any VM it made. Nothing was spawned", "--on", "new", called=["up"])
        self.assertIn("devcloud vm: --expect-creator: the caller expects @%s as this host's creator, and devcloud "
                      "read @ffffffff: nothing was made" % self.sid[:8], err)

    def test_a_cap_passes_through_with_its_exit_and_the_way_on(self):
        self.cfg["up"] = {"lines": ["caps      over the count cap"], "exit": 4,
                          "stderr": "devcloud vm: over the count cap: ask the person, then pass --confirmed\n"}
        self.save()
        out, err = self.refused(4, ". The cap is the person's: after their yes to this exact request, pass "
                                   "--vm-confirmed", "--on", "new", called=["up"])
        self.assertIn("caps      over the count cap", out)

    ACCOUNT = "account   main (fake)  location fsn1  type medium (4 vCPU, 8 GB, 160 GB disk)  lifetime keep"
    CAPS = "caps      unconfirmed 0/3 ok, size 4/8 vCPU ok, disk 160/200 GB ok"
    CREATED = "created   dc-x-0001 (id 1) from base, slow path"
    MAYBE = ("sminos: spawn --on new: a VM may have been made all the same, since a provider can make one and lose "
             "the answer that names it: before running this again, devcloud vm ls shows it, kept and owned by this "
             "session's thread, and devcloud vm down <name> removes it\n")

    def failed_up(self, lines, code, stderr):
        self.forget_calls()
        self.cfg["up"] = {"lines": lines, "exit": code, "stderr": stderr}
        self.save()
        return self.refused(code, "spawn --on new: devcloud vm up exited %d; its own lines above say why, and what "
                                  "became of any VM it made. Nothing was spawned" % code, "--on", "new",
                            called=["up"])

    def test_an_up_that_failed_after_it_named_its_vm_says_it_is_kept_whose_it_is_and_what_ends_it(self):
        """--keep: no lease bounds the VM, so sminos names it, its owner and its down, as after `ready`."""
        _, err = self.failed_up([self.ACCOUNT, self.CAPS, self.CREATED], 1,
                                "devcloud vm: the boot failed at step secrets (it broke); the VM dc-x-0001 is kept "
                                "for inspection, with no lease: devcloud vm down dc-x-0001 removes it\n")
        self.assertTrue(err.endswith("Nothing was spawned. The VM dc-x-0001 is kept and this session's thread owns it: "
                                     "devcloud vm down dc-x-0001 ends it\n"), err)
        self.assertNotIn("lease bounds", err)
        self.assertNotIn("may have been made", err)
        _, err = self.failed_up([self.ACCOUNT, self.CAPS, self.CREATED], 1,
                                "devcloud vm: the recount after the create failed: list failed; dc-x-0001 could not "
                                "be deleted: down it, or the reaper will\n")
        self.assertIn(". The VM dc-x-0001 is kept and this session's thread owns it", err)

    def test_an_up_whose_own_recount_deleted_the_vm_says_nothing_is_kept(self):
        for code, words in ((4, "over the count cap (4 unconfirmed alive after the create, cap 3: another driver "
                                "created one meanwhile); deleted dc-x-0001: ask the person, then pass --confirmed"),
                            (1, "the recount after the create failed: list failed; deleted dc-x-0001")):
            with self.subTest(code=code):
                _, err = self.failed_up([self.ACCOUNT, self.CAPS, self.CREATED], code, "devcloud vm: %s\n" % words)
                self.assertNotIn("is kept", err)
                self.assertNotIn("may have been made", err)

    def test_an_up_that_failed_past_its_caps_naming_no_vm_ends_saying_one_may_exist(self):
        _, err = self.failed_up([self.ACCOUNT, self.CAPS], 1, "devcloud vm: fake: describe of server 7 failed\n")
        self.assertTrue(err.endswith(self.MAYBE), err)
        self.assertNotIn(". The VM ", err)

    def test_an_up_refused_before_any_create_says_no_vm_may_exist(self):
        for lines, code, words in (([self.ACCOUNT, self.CAPS], 4, "over the count cap: ask the person"),
                                   ([self.ACCOUNT, self.CAPS], 3, "fake refused the create (limit)"),
                                   ([], 1, "--enroll: nothing was made"), ([], 3, "--enroll: nothing was made")):
            with self.subTest(code=code, words=words):
                _, err = self.failed_up(lines, code, "devcloud vm: %s\n" % words)
                self.assertNotIn("may have been made", err)
                self.assertNotIn("is kept", err)

    def test_an_up_that_succeeded_without_a_usable_ready_line_keeps_the_vm_it_created(self):
        self.forget_calls()
        self.cfg["up"] = {"lines": [self.ACCOUNT, self.CAPS, self.CREATED]}
        self.save()
        _, err = self.refused(1, "spawn --on new: devcloud vm up succeeded and did not name one host where sminos "
                                 "reads it", "--on", "new", called=["up"])
        self.assertTrue(err.endswith(". The VM dc-x-0001 is kept and this session's thread owns it: devcloud vm down "
                                     "dc-x-0001 ends it\n"), err)
        self.cfg["up"] = {"lines": [self.ACCOUNT, self.CAPS]}
        self.save()
        self.forget_calls()
        _, err = self.refused(1, "did not name one host where sminos reads it", "--on", "new", called=["up"])
        self.assertTrue(err.endswith(self.MAYBE), err)

    def test_only_the_recounts_own_line_says_a_vm_was_deleted(self):
        """Another line that holds `deleted <name>` is not the recount's: the VM is kept."""
        _, err = self.failed_up([self.ACCOUNT, self.CAPS, self.CREATED], 1,
                                "devcloud vm: the boot failed at step secrets (it was deleted dc-x-0001's key, then "
                                "retried); the VM dc-x-0001 is kept for inspection, with no lease: devcloud vm down "
                                "dc-x-0001 removes it\n")
        self.assertIn(". The VM dc-x-0001 is kept and this session's thread owns it", err)

    def test_an_up_that_names_no_host_or_two(self):
        for lines in (["created   dc-x-0001"], ["a  ready in 0m01s", "b  ready in 0m02s"]):
            with self.subTest(lines=lines):
                self.forget_calls()
                self.cfg["up"] = {"lines": lines}
                self.save()
                self.refused(1, "spawn --on new: devcloud vm up succeeded and did not name one host where sminos "
                                "reads it", "--on", "new", called=["up"])

    def test_the_checkout_at_another_commit_is_said(self):
        other = "f" * 40
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", head=other))
        code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertIn("sminos: note: the VM's checkout is at %s, not at %s, the commit origin's topic was at when it "
                      "was checked" % (other, self.commit), err)
        self.assertNotIn("moved", err, "the HEAD is read after the job started: it shows a difference, not its cause")
        self.answers("vm1", self.spawned(head=other))
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("the VM's checkout is at", err)
        self.assertNotIn("is kept and", err)
        # An explicit --cwd: the session's directory need not be the checkout of the branch derived, so its commit
        # says nothing of that branch.
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", head=other, cwd="/home/u/elsewhere"))
        code, out, err = self.spawn("--on", "new", "--cwd", "~/elsewhere")
        self.assertEqual(code, 0, err)
        self.assertNotIn("the VM's checkout is at", err)
        # The derived checkout named with --cwd is compared; another checkout the engine ran in (--worktree) is not.
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", head=other))
        code, out, err = self.spawn("--on", "new", "--cwd", "~/Developer/GitHub/repo")
        self.assertIn("the VM's checkout is at", err)
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", head=other,
                                               cwd="/home/u/Developer/GitHub/repo/.claude/worktrees/wt"))
        code, out, err = self.spawn("--on", "new", "--worktree", "wt")
        self.assertEqual(code, 0, err)
        self.assertNotIn("the VM's checkout is at", err)

    def test_from_a_terminal_new_is_refused(self):
        self.refused(1, "spawn --on new: no session runs this, so the VM would have no owner", "--on", "new",
                     session=False)

    def test_a_worktree_origin_does_not_hold_at_its_commit_each_with_the_ways_out(self):
        gitq("commit", "-q", "--allow-empty", "-m", "two", cwd=self.work)
        ahead = gitq("rev-parse", "HEAD", cwd=self.work)
        self.refused(1, "spawn --on new: origin's topic is at %s and this checkout is at %s, so the VM would clone "
                        "without what differs: push it, or name the ref with --vm-project example/repo@<ref>"
                        % (self.commit, ahead), "--on", "new")
        gitq("checkout", "-q", "-b", "lone", cwd=self.work)
        gitq("push", "-q", "origin", "HEAD:refs/heads/x/lone", cwd=self.work)
        self.refused(1, "spawn --on new: origin has no branch lone, and the VM clones from GitHub, so it would not "
                        "get this work: push it (git push -u origin lone), or name what the VM checks out with "
                        "--vm-project example/repo@<ref>", "--on", "new")
        gitq("checkout", "-q", "--detach", cwd=self.work)
        self.refused(1, "spawn --on new: this checkout is on no branch, and the VM clones a branch or a ref from "
                        "GitHub: check a pushed branch out, or name the ref with --vm-project example/repo@<ref>",
                     "--on", "new")
        gitq("checkout", "-q", "topic", cwd=self.work)
        gitq("remote", "set-url", "origin", "https://gitlab.example/example/repo", cwd=self.work)
        self.refused(1, "spawn --on new: %s is in no repository whose origin is on GitHub, so there is nothing to "
                        "tell the VM to check out: name it with --vm-project owner/repo[@ref]" % self.work,
                     "--on", "new")
        gitq("remote", "set-url", "origin", "https://github.com/example/silent", cwd=self.work)
        with open(os.path.join(os.environ["HOME"], ".gitconfig"), "a") as f:
            f.write('[url "%s"]\n\tinsteadOf = https://github.com/example/silent\n'
                    % os.path.join(self.home, "nothing-here"))
        self.refused(1, "spawn --on new: origin did not say where topic is (", "--on", "new")

    def test_two_linked_worktrees_each_read_in_their_own(self):
        gitq("checkout", "-q", "-b", "main", cwd=self.work)
        gitq("push", "-q", "origin", "main", cwd=self.work)
        linked = os.path.join(self.home, "linked")
        gitq("worktree", "add", "-q", "-b", "feature", linked, cwd=self.work)
        gitq("commit", "-q", "--allow-empty", "-m", "unpushed", cwd=linked)
        mine = gitq("rev-parse", "HEAD", cwd=linked)
        gitq("push", "-q", "origin", "%s:refs/heads/feature" % self.commit, cwd=linked)
        self.sid, _ = self.session(root=linked)
        self.recorded(self.sid)
        self.refused(1, "spawn --on new: origin's feature is at %s and this checkout is at %s" % (self.commit, mine),
                     "--on", "new", cwd=linked)
        self.sid, _ = self.session(root=self.work)
        self.recorded(self.sid)
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        code, _, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertIn("--project=example/repo@main", [c for c in self.calls() if c[1] == "up"][0])

    def test_a_linked_worktrees_own_origin_is_the_one_read(self):
        linked = os.path.join(self.home, "linked")
        gitq("worktree", "add", "-q", "-b", "feature", linked, cwd=self.work)
        gitq("config", "extensions.worktreeConfig", "true", cwd=self.work)
        gitq("config", "--worktree", "remote.origin.url", "https://github.com/example/fork", cwd=linked)
        fork = os.path.join(self.home, "fork.git")
        gitq("clone", "-q", "--bare", self.bare, fork)
        gitq("push", "-q", fork, "feature", cwd=linked)
        with open(os.path.join(os.environ["HOME"], ".gitconfig"), "a") as f:
            f.write('[url "%s"]\n\tinsteadOf = https://github.com/example/fork\n' % fork)
        self.sid, _ = self.session(root=linked)
        self.recorded(self.sid)
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        code, _, err = self.spawn("--on", "new", cwd=linked)
        self.assertEqual(code, 0, err)
        self.assertIn("--project=example/fork@feature", [c for c in self.calls() if c[1] == "up"][0])

    def test_reach_narrowed_while_the_vm_is_made_refuses_saying_it_is_kept(self):
        gate = os.path.join(self.home, "gate")
        self.cfg["up"] = {"gate": gate}
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))

        def narrow():
            end = time.monotonic() + 20
            while "up" not in self.verbs() and time.monotonic() < end:
                time.sleep(0.02)
            records.set_policy(self.sid, lambda access, shares: ("private", shares))
            open(gate, "w").close()
        t = threading.Thread(target=narrow)
        t.start()
        out, err = self.refused(1, "spawn --on: this session's reach is not this machine's default (its access is "
                                   "private)", "--on", "new", called=["up"])
        t.join()
        self.assertIn(". The VM dc-x-0001 is kept and this session's thread owns it: devcloud vm down dc-x-0001 "
                      "ends it", err)

    def test_reach_narrowed_between_two_tries_of_the_wait(self):
        self.answers("dc-x-0001", on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"}), code=1)

        def narrow():
            end = time.monotonic() + 20
            while "ssh" not in self.verbs() and time.monotonic() < end:
                time.sleep(0.02)
            records.set_policy(self.sid, lambda access, shares: ("private", shares))
        t = threading.Thread(target=narrow)
        t.start()
        with mock.patch.dict(os.environ, {"SMINOS_ON_ENROLL_POLL": "0.5"}):
            out, err = self.refused(1, "(its access is private)", "--on", "new", called=["up", "ssh"])
        t.join()
        self.assertIn("is up and not enrolled in the org yet: waiting up to 11 minutes", err)
        self.assertIn("is kept and this session's thread owns it", err)


    def test_each_try_of_the_wait_names_the_spawner_where_it_is_then(self):
        """The spawner's project changed on disk while the VM enrolled (its checkout's `.smns`, written by another
        process): the try that spawns reads it again and sends the address as it is then, never the one read before
        the VM was made; the nonce stays the request's."""
        moved = str(uuidlib.uuid4())
        sent = []

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")
                return 0, ["dc-x-0001  ready in 0m01s"], "", False, True
            sent.append(json.loads(vm_side(args).asked_from))
            if len(sent) == 1:
                with open(os.path.join(self.work, ".smns"), "w") as f:
                    json.dump({"project": moved, "name": "moved", "remote": "", "hub": {"org": "org-1"}}, f)
                return 1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], "", False, True
            return 0, [self.spawned(machine="dc-x-0001")], "", False, True
        before = sminos.resolve_project(self.work)
        with mock.patch.object(on, "run_devcloud", side_effect=run), \
                mock.patch.dict(os.environ, {"SMINOS_ON_ENROLL_POLL": "0.01"}):
            code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertEqual([(r["by"]["project"], r["by"]["project_name"]) for r in sent],
                         [(before.id, before.name), (moved, "moved")])
        self.assertEqual({r["nonce"] for r in sent}, {NONCE})

    def test_a_tag_named_as_the_branch_reads_the_branch(self):
        gitq("tag", "topic", cwd=self.work)
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        code, _, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.up_args()[-1:], ["--project=example/repo@topic"])

    def test_devcloud_reading_no_creating_session_makes_nothing_and_spawns_nothing(self):
        self.cfg["up"] = {"creator": None}
        self.save()
        out, err = self.refused(1, "spawn --on new: devcloud vm up exited 1; its own lines above say why, and what "
                                   "became of any VM it made. Nothing was spawned", "--on", "new", called=["up"])
        self.assertIn("devcloud vm: --expect-creator: the caller expects @%s as this host's creator, and devcloud "
                      "read no creating session here" % self.sid[:8], err)

    def test_a_line_of_up_that_opens_the_mark_is_passed_through(self):
        said = "sminos-spawn %s {}" % NONCE
        self.cfg["up"] = {"lines": [said, "dc-x-0001  ready in 0m01s"]}
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertIn(said, out.splitlines())

    def waited(self, *answers, wait="60", poll="30", bound="480", reach_takes=0, on_="new", spawned=False, argv=()):
        """`--on new` under a clock that only sleeping and each read of the reach rule (`reach_takes` seconds)
        move, devcloud answering `up` with a host and each `vm ssh` with the next of `answers` ((exit, lines,
        timed out)): (exit, stderr, each try's (start, bound))."""
        clock, tries, left = [1000.0], [], list(answers)
        self.ssh_args = []
        reach = on.reach

        def slow_reach(c):
            clock[0] += reach_takes
            reach(c)

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")   # as run_devcloud's reading of the ready line records it
                return 0, ["dc-x-0001  ready in 0m01s"], "", False, True
            tries.append((clock[0], timeout))
            self.ssh_args.append(args)
            code, lines, timed_out = left.pop(0)
            return code, lines, "", timed_out, True
        fake = mock.Mock(monotonic=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))
        env = {"SMINOS_ON_ENROLL_WAIT": wait, "SMINOS_ON_ENROLL_POLL": poll, "SMINOS_ON_TIMEOUT": bound}
        with mock.patch.object(on, "run_devcloud", side_effect=run), mock.patch.object(on, "time", fake), \
                mock.patch.object(on, "reach", slow_reach), mock.patch.dict(os.environ, env):
            code, out, err = self.spawn("--on", on_, *argv)
        self.assertEqual("seat spawned on" in out, spawned, out + err)
        return code, err, tries

    def test_the_wait_starts_no_try_at_its_deadline_and_bounds_each_by_what_is_left(self):
        no = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], False)
        code, err, tries = self.waited(no, no, (0, [self.spawned(machine="dc-x-0001")], False))
        self.assertEqual(tries, [(1000.0, 480.0), (1030.0, 30.0)])
        self.assertEqual(code, 1, err)
        self.assertIn("spawn --on new: dc-x-0001 did not enroll within 1 minutes: nothing was spawned", err)
        self.assertIn(". The VM dc-x-0001 is kept and", err)

    def test_no_try_starts_past_the_deadline_however_long_the_reach_read_takes(self):
        no = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], False)
        code, err, tries = self.waited(no, (0, [self.spawned(machine="dc-x-0001")], False), reach_takes=40)
        self.assertEqual(tries, [(1080.0, 480.0)], "the reach read before the second try ends past the deadline")
        self.assertEqual(code, 1, err)
        self.assertIn("spawn --on new: dc-x-0001 did not enroll within 1 minutes: nothing was spawned", err)

    def test_a_try_cut_short_by_the_deadline_may_have_spawned(self):
        no = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], False)
        code, err, tries = self.waited(no, (-15, [], True))
        self.assertEqual(tries, [(1000.0, 480.0), (1030.0, 30.0)])
        self.assertEqual(code, 1, err)
        self.assertIn("spawn --on: dc-x-0001 gave no outcome within 1 minutes, and the call was stopped: a session may "
                      "or may not have started there, and devcloud vm ssh dc-x-0001 -- sminos list shows", err)
        self.assertNotIn("nothing was spawned", err)
        self.assertIn(". The VM dc-x-0001 is kept and", err)

    NOT_ENROLLED = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], False)
    NOT_READ = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "spawner-unknown"})], False)

    def test_a_vm_that_has_not_read_the_spawner_is_tried_again_within_the_enrollment_s_bound(self):
        """One bound, from the first refusal of either kind: enrolled late, then still downloading the project's log,
        then spawned."""
        code, err, tries = self.waited(self.NOT_ENROLLED, self.NOT_READ,
                                       (0, [self.spawned(machine="dc-x-0001")], False), wait="90", spawned=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(tries, [(1000.0, 480.0), (1030.0, 60.0), (1060.0, 30.0)])
        self.assertIn("dc-x-0001 is up and not enrolled in the org yet: waiting up to 2 minutes", err)
        self.assertIn("dc-x-0001 has not read this session from the project's log yet (a machine enrolled moments "
                      "ago downloads it first): waiting for it, within the same 2 minutes, then spawning", err)

    def test_at_the_bound_nothing_is_opened_and_the_vm_is_kept(self):
        code, err, tries = self.waited(self.NOT_READ, self.NOT_READ, self.NOT_READ)
        self.assertEqual(tries, [(1000.0, 480.0), (1030.0, 30.0)])
        self.assertEqual(code, on.EXIT_LATER, err)
        self.assertIn("spawn --on: dc-x-0001 had not read this session from the project's log within 1 minutes (it "
                      "is still downloading the log): no thread was opened there. Once it has, sminos spawn --on "
                      "dc-x-0001 opens it", err)
        self.assertIn(". The VM dc-x-0001 is kept and this session's thread owns it: devcloud vm down dc-x-0001 ends "
                      "it", err)
        self.assertNotIn("did not enroll", err)

    def test_a_named_vm_that_has_not_read_the_spawner_is_waited_for_too(self):
        """A VM that exists can be behind on the project's log as well; it is never one the Mac made, so nothing is
        said kept."""
        code, err, tries = self.waited(self.NOT_READ, (0, [self.spawned()], False), on_="vm1", spawned=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(tries), 2)
        code, err, tries = self.waited(self.NOT_READ, self.NOT_READ, self.NOT_READ, on_="vm1")
        self.assertEqual(code, on.EXIT_LATER, err)
        self.assertNotIn("is kept", err)

    def test_a_spawner_named_as_someone_else_is_never_waited_on(self):
        shadowed = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "spawner-shadowed"})], False)
        for on_ in ("new", "vm1"):
            with self.subTest(on=on_):
                code, err, tries = self.waited(shadowed, (0, [self.spawned()], False), on_=on_)
                self.assertEqual((code, len(tries)), (1, 1), err)
                self.assertIn("sminos answered exit 1; its line above says why", err)
                self.assertNotIn("waiting", err)

    def test_an_enrollment_gone_or_changed_between_tries_refuses_and_keeps_the_vm(self):
        """The request's org is the enrollment's as it is at each try: never another org's, and none sent once
        this machine is no longer enrolled."""
        identity = os.path.join(os.environ["SMINOS_HOME"], "daemon", "identity.json")
        for change, words in ((lambda: os.unlink(identity), "spawn --on: this machine is no longer enrolled in the org"),
                              (lambda: self.enroll(org="org-2"), "spawn --on: this machine is now enrolled in "
                                                                  "another org than when the VM was asked for")):
            with self.subTest(words=words[:40]):
                self.enroll()
                sent = []

                def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
                    if args[:2] == ["vm", "up"]:
                        c.ready.append("dc-x-0001")
                        return 0, ["dc-x-0001  ready in 0m01s"], "", False, True
                    sent.append(json.loads(vm_side(args).asked_from))
                    change()
                    return 1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], "", False, \
                        True
                with mock.patch.object(on, "run_devcloud", side_effect=run), \
                        mock.patch.dict(os.environ, {"SMINOS_ON_ENROLL_POLL": "0.01"}):
                    code, out, err = self.spawn("--on", "new")
                self.assertEqual(code, 1, err)
                self.assertIn(words, err)
                self.assertIn(". The VM dc-x-0001 is kept and", err)
                self.assertEqual([r["org"] for r in sent], ["org-1"], "no second try")

    def test_each_try_is_given_what_the_one_read_of_the_clock_left(self):
        """A clock that moves at every read: the wait's end and the try's budget are one read, so no try is started
        with nothing left (the transport would take that as a call cut short, which may have spawned), and the wait
        ends at row 27a."""
        clock, given = [1000.0], []

        def monotonic():
            clock[0] += 0.4
            return clock[0]

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")
                return 0, ["dc-x-0001  ready in 0m01s"], "", False, True
            given.append(timeout)
            return 1, self.NOT_READ[1], "", False, True
        # A sleep may end a little early: the clock never lands on the wait's end exactly.
        fake = mock.Mock(monotonic=monotonic, sleep=lambda s: clock.__setitem__(0, clock[0] + 0.9 * s))
        env = {"SMINOS_ON_ENROLL_WAIT": "60", "SMINOS_ON_ENROLL_POLL": "1"}
        with mock.patch.object(on, "run_devcloud", side_effect=run), mock.patch.object(on, "time", fake), \
                mock.patch.dict(os.environ, env):
            code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, on.EXIT_LATER, err)
        self.assertGreater(len(given), 20)
        self.assertTrue(all(t > 0 for t in given), "a try given %r" % min(given))

    def test_the_wait_s_end_is_read_before_the_route_back(self):
        """A route back read after the wait has ended would refuse in its own words; the wait's end is what is
        true."""
        clock, left = [1000.0], [self.NOT_READ, self.NOT_READ, (0, [self.spawned(machine="dc-x-0001")], False)]
        reach = on.reach

        def late_reach(c):
            if clock[0] >= 1060:
                c.refuse("the route back, read past the wait")
            reach(c)

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")
                return 0, ["dc-x-0001  ready in 0m01s"], "", False, True
            code, lines, timed_out = left.pop(0)
            return code, lines, "", timed_out, True
        fake = mock.Mock(monotonic=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))
        env = {"SMINOS_ON_ENROLL_WAIT": "60", "SMINOS_ON_ENROLL_POLL": "30"}
        with mock.patch.object(on, "run_devcloud", side_effect=run), mock.patch.object(on, "time", fake), \
                mock.patch.object(on, "reach", late_reach), mock.patch.dict(os.environ, env):
            code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, on.EXIT_LATER, err)
        self.assertIn("had not read this session from the project's log within 1 minutes", err)
        self.assertNotIn("the route back, read past the wait", err)

    def test_stopped_between_two_tries_of_the_wait_keeps_the_vm(self):
        def guard(*_):
            raise AssertionError("the SIGTERM reached this test's own handler, not sminos's")
        self.addCleanup(signal.signal, signal.SIGTERM, signal.signal(signal.SIGTERM, guard))
        no = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], "", False, True)
        real = time.sleep

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")   # as run_devcloud's reading of the ready line records it
                return 0, ["dc-x-0001  ready in 0m01s"], "", False, True
            return no

        def term(seconds):
            os.kill(os.getpid(), signal.SIGTERM)
            real(1)   # the signal lands here

        def interrupt(seconds):
            raise KeyboardInterrupt
        for how, sleep in (("SIGTERM", term), ("an interrupt", interrupt)):
            with self.subTest(how=how):
                with mock.patch.object(on, "run_devcloud", side_effect=run), \
                        mock.patch.object(on, "time", mock.Mock(monotonic=time.monotonic, sleep=sleep)):
                    code, out, err = self.spawn("--on", "new")
                self.assertEqual(code, 1, err)
                self.assertIn("spawn --on: stopped: nothing was spawned. The VM dc-x-0001 is kept and", err)

    def stopped(self, *argv):
        """`spawn --on …` given a SIGTERM once devcloud's stand-in has reached its gate."""
        self.addCleanup(signal.signal, signal.SIGTERM, signal.signal(signal.SIGTERM, lambda *_: None))
        marker = os.path.join(self.home, "said")
        with contextlib.suppress(FileNotFoundError):
            os.unlink(marker)   # a call before this one's
        for held in [self.cfg.get("up") or {}] + list(self.cfg["ssh_hosts"].values()):
            if "hold" in held:
                held["said"] = marker
        self.save()
        t = stop_soon(lambda: os.path.exists(marker))
        code, out, err = self.spawn(*argv)
        t.join()
        self.assertEqual(code, 1, err)
        self.assertNotIn("seat spawned on", out)
        return err

    def test_stopped_while_up_runs_after_it_made_its_vm_and_before_ready_keeps_it(self):
        """One disposition for a failure, a stop and an unusable `ready` output: the VM a `created` line named, said
        kept with its owner and its down; and no `vm ssh`, which only a `ready` line starts."""
        self.cfg["up"] = {"lines": [New.ACCOUNT, New.CAPS, New.CREATED], "hold": os.path.join(self.home, "never")}
        err = self.stopped("--on", "new")
        self.assertIn("spawn --on: stopped while devcloud ran", err)
        self.assertTrue(err.endswith(". The VM dc-x-0001 is kept and this session's thread owns it: devcloud vm down "
                                     "dc-x-0001 ends it\n"), err)
        self.assertEqual(self.verbs(), ["up"])

    def test_stopped_while_up_runs_past_its_caps_naming_nothing_says_one_may_exist(self):
        self.cfg["up"] = {"lines": [New.ACCOUNT, New.CAPS], "hold": os.path.join(self.home, "never")}
        err = self.stopped("--on", "new")
        self.assertIn("spawn --on: stopped while devcloud ran", err)
        self.assertTrue(err.endswith(New.MAYBE), err)
        self.assertEqual(self.verbs(), ["up"])

    def test_stopped_while_up_runs_after_it_named_its_host_keeps_the_vm(self):
        self.cfg["up"] = {"hold": os.path.join(self.home, "never")}
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        err = self.stopped("--on", "new")
        self.assertIn("spawn --on: stopped while devcloud ran", err)
        self.assertIn(". The VM dc-x-0001 is kept and", err)
        self.assertEqual(self.verbs(), ["up"])

    def test_stopped_after_up_exited_before_its_result_returned_keeps_the_vm(self):
        closed, calls = on.closed, []

        def stopped_once(files):
            calls.append(files)
            if len(calls) == 1:   # up's own: its child has exited, and its result is not yet returned
                raise KeyboardInterrupt
            closed(files)
        with mock.patch.object(on, "closed", stopped_once):
            code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, 1, err)
        self.assertIn("dc-x-0001  ready in 0m01s", out.splitlines())
        self.assertIn("spawn --on: stopped while devcloud ran", err)
        self.assertIn(". The VM dc-x-0001 is kept and", err)
        self.assertEqual(self.verbs(), ["up"])
        for files in calls:
            closed(files)

    def test_stopped_while_the_vm_side_runs_says_where_to_look(self):
        for argv, vm in ((["--on", "vm1"], "vm1"), (["--on", "new"], "dc-x-0001")):
            with self.subTest(vm=vm):
                self.forget_calls()
                self.cfg = {"ssh_hosts": {vm: {"stdout": "", "exit": 0, "hold": os.path.join(self.home, "never")}}}
                err = self.stopped(*argv)
                self.assertIn("a session may or may not have started there, and devcloud vm ssh %s -- sminos list "
                              "shows" % vm, err)
                self.assertNotIn("nothing was spawned", err)
                if vm == "dc-x-0001":
                    self.assertIn(". The VM dc-x-0001 is kept and", err)

    # EN.G2's §1: a VM that has kept no welcome yet, asked for channels.
    WELCOME = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "welcome-unknown"})], False)

    def test_a_vm_that_has_kept_no_welcome_is_waited_on_named_or_new_and_each_try_sends_the_same_channels(self):
        register(DESK, "desk")
        for on_ in ("vm1", "new"):
            with self.subTest(on=on_):
                line = self.spawned(machine=on_ if on_ != "new" else "dc-x-0001",
                                    channels=[{"id": DESK, "state": "applied", "why": ""}])
                code, err, tries = self.waited(self.WELCOME, self.NOT_READ, (0, [line], False), wait="90",
                                               on_=on_, spawned=True, argv=("--channel", "desk"))
                self.assertEqual((code, len(tries)), (0, 3), err)
                self.assertIn("has kept no welcome of its endpoint yet (a machine enrolled moments ago keeps it once "
                              "its uplink connects): waiting up to 2 minutes for it, then spawning", err)
                sent = {json.dumps(json.loads(vm_side(a).asked_from)["channels"]) for a in self.ssh_args}
                self.assertEqual(sent, {json.dumps([{"id": DESK, "name": "desk"}])})

    def test_at_the_wait_s_end_nothing_was_opened_exit_75_and_the_way_on(self):
        register(DESK, "desk")
        code, err, tries = self.waited(self.WELCOME, self.WELCOME, self.WELCOME, on_="vm1", argv=("--channel", "desk"))
        self.assertEqual(code, on.EXIT_LATER, err)
        self.assertIn("spawn --on: vm1's sminos had kept no welcome of its endpoint within 1 minutes, so whether it "
                      "serves channels is not known: no thread was opened there. devcloud vm ssh vm1 -- sminos daemon "
                      "status shows its uplink; once it is connected, the same command with --on vm1 opens it", err)


class Bound(On):
    """One deadline for the run and the reading of its output: a descendant of devcloud that keeps the output open
    (the ssh under `devcloud vm ssh`) holds neither past it. A watchdog ends the descendant after 8 s, so that a call
    that waits on it fails here rather than hangs."""

    def child(self):
        with contextlib.suppress(OSError, ValueError, IndexError, KeyError):
            with open(os.path.join(os.environ["HOME"], "devcloud-standin.calls")) as f:
                return json.loads(f.readlines()[-1])["child"]

    @contextlib.contextmanager
    def watched(self):
        returned = threading.Event()

        def watchdog():
            if not returned.wait(8) and self.child():
                with contextlib.suppress(ProcessLookupError):
                    os.kill(self.child(), signal.SIGKILL)
        threading.Thread(target=watchdog, daemon=True).start()
        began = time.monotonic()
        took = []
        try:
            yield took
        finally:
            took.append(time.monotonic() - began)
            returned.set()
            pid = self.child()
            if pid:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)

    def bounded(self, **cfg):
        self.cfg.update(child=True, **cfg)
        self.save()
        c = on.Call(mock.Mock(on="vm1", alias="w"))
        c.devcloud = os.environ["SMINOS_DEVCLOUD"]
        with self.watched() as took, contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            got = on.run_devcloud(c, ["vm", "owned-by", "abcd1234"], timeout=0.3, keep_err=True)
        return got, took[0]

    def test_a_stand_in_whose_hold_is_never_released_ends_by_itself(self):
        """A test killed while the stand-in waits on its hold leaves no stand-in behind (the orphans of EN.G1's M3)."""
        self.cfg["ssh_hosts"]["vm1"] = {"stdout": "", "exit": 0, "hold": os.path.join(self.home, "never")}
        self.save()
        began = time.monotonic()
        done = subprocess.run([sys.executable, "-B", os.environ["SMINOS_DEVCLOUD"], "vm", "ssh", "vm1", "--", "true"],
                              capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
                              env={**os.environ, "DEVCLOUD_STANDIN_WAIT_BOUND": "0.5"})
        self.assertEqual(done.returncode, 75, done.stderr)
        self.assertIn("did not come within", done.stderr)
        self.assertLess(time.monotonic() - began, 20)

    def test_the_bound_holds_while_a_descendant_keeps_devcloud_s_output_open(self):
        got, took = self.bounded(hang=True)
        self.assertTrue(got[3], "the bound passed")
        self.assertFalse(got[4], "its output did not end")
        self.assertLess(took, 3, "returned at its deadline, not when the descendant let go")

    def test_a_child_that_exits_at_once_holds_the_call_no_longer_than_the_deadline(self):
        got, took = self.bounded()
        self.assertEqual((got[0], got[3], got[4]), (0, False, False), "exit 0, within the bound, output not ended")
        self.assertLess(took, 3, "returned at its deadline (took %.1f s)" % took)

    def test_an_outcome_line_from_output_that_never_ended_is_not_known(self):
        self.answers("vm1", self.spawned())
        self.cfg["child"] = True
        self.save()
        with self.watched() as took, mock.patch.dict(os.environ, {"SMINOS_ON_TIMEOUT": "0.5"}):
            code, out, err = self.spawn("--on", "vm1")
        self.assertLess(took[0], 4)
        self.assertEqual(code, 1, err)
        self.assertNotIn("seat spawned on", out)
        self.assertIn("spawn --on: the outcome on vm1 is not known (its output did not end: something it started "
                      "still holds it open): a session may or may not have started there, and devcloud vm ssh vm1 -- "
                      "sminos list shows", err)


class Outcome(On):
    """The outcome line, through `vm ssh`'s answer (§8)."""

    def unknown(self, reason, *lines, code=0, want=None, vm="vm1", argv=()):
        self.answers(vm, *lines, code=code)
        code_, out, err = self.spawn("--on", vm, *argv)
        self.assertEqual(code_, want if want is not None else (code or 1), err)
        self.assertIn("spawn --on: the outcome on %s is not known (%s): a session may or may not have started there, "
                      "and devcloud vm ssh %s -- sminos list shows" % (vm, reason, vm), err)
        self.assertNotIn("seat spawned on", out)
        return out, err

    def test_one_whole_line_last_is_the_outcome(self):
        self.answers("vm1", "some noise", self.spawned())
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), ["some noise", 'seat spawned on vm1: repo/w  [a1b2c3d4 / %s]  '
                                            'status=working  (message it: sminos say "@%s …"; it is listed here '
                                            'once vm1\'s events arrive)' % (SEAT, JOB[:8])])
        self.answers("vm1", self.spawned(refilled=True, extra="a key beyond the shape"))
        code, out, _ = self.spawn("--on", "vm1")
        self.assertEqual((code, out.split(":")[0]), (0, "seat re-filled on vm1"))
        # `channels` on a success to a Mac that asked for none is a key beyond the shape too (EN.G2's §1).
        for placed in ({}, [], "x", [{"id": "not-a-channel"}]):
            with self.subTest(channels=placed):
                self.answers("vm1", self.spawned(channels=placed))
                code, out, err = self.spawn("--on", "vm1")
                self.assertEqual((code, out.split(":")[0]), (0, "seat spawned on vm1"), err)

    def test_every_other_shape_is_not_known_and_spawns_nothing(self):
        line = self.spawned()
        other = line.replace(NONCE, "f" * 16)
        cases = [
            ("no outcome line came back", [other]),
            ("more than one outcome line came back", [line, line]),
            ("the outcome line is not the last line it printed", [line, "after"]),
            ("the outcome line does not read as one", ["sminos-spawn %s {not json" % NONCE]),
            ("the outcome line names another alias than the one asked", [self.spawned(alias="x")]),
            ("the outcome line does not read as one", [self.spawned(session="not-an-id")]),
            ("the outcome line does not read as one", [self.spawned(refilled="no")]),
            ("the outcome line does not read as one",
             [on.outcome_line(NONCE, {k: v for k, v in json.loads(line.split(" ", 2)[2]).items() if k != "refilled"})]),
            ("the outcome line does not read as one", [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "x"})]),
            ("the outcome line does not read as one",
             [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": {"not": "a word"}})]),
            ("the outcome line does not read as one", [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": []})]),
            ("the outcome line does not read as one", [on.outcome_line(NONCE, {"ok": False, "exit": 1})]),
            ("the outcome line does not read as one",
             [on.outcome_line(NONCE, {k: v for k, v in json.loads(line.split(" ", 2)[2]).items() if k != "head"})]),
            ("the outcome line does not read as one", [self.spawned(project=None)]),
            ("the outcome line does not read as one", [self.spawned(head="")]),
            ("the outcome line does not read as one", [self.spawned(not_carried=7)]),
            ("the outcome line does not read as one", [self.spawned(not_carried=None)]),
            ("the outcome line does not read as one", [self.spawned(not_carried=["it syncs through no hub"])]),
        ]
        for reason, lines in cases:
            with self.subTest(reason=reason, lines=lines[0][:60]):
                self.unknown(reason, *lines)
        with self.subTest("a refusal whose not_carried is no string"):
            self.unknown("the outcome line does not read as one",
                         on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "other", "not_carried": None}), code=1)
        with self.subTest("ok beside a non-zero exit"):
            self.unknown("the outcome line and the exit status disagree", line, code=3, want=3)
        with self.subTest("a refusal beside exit 0"):
            self.unknown("the outcome line and the exit status disagree",
                         on.outcome_line(NONCE, {"ok": False, "exit": 4, "why": "other"}), code=0, want=1)

    def test_a_task_holding_a_line_with_another_nonce_changes_nothing(self):
        other = 'sminos-spawn %s {"ok": true}' % ("e" * 16)
        self.answers("vm1", other, self.spawned())
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertIn(other, out.splitlines(), "a line of another call is passed through")
        self.assertNotIn(self.spawned(), out)

    def test_no_line_and_a_usage_exit_is_a_copy_that_may_predate_the_call(self):
        _, err = self.unknown("no outcome line came back", code=2, want=2)
        self.assertIn(". What devcloud or the host printed above may say why. It ended with a usage error, so its "
                      "sminos may predate this call", err)
        self.assertNotIn("nothing was spawned", err)

    def test_a_seat_filed_in_a_project_its_machine_does_not_carry_is_said_without_the_promise(self):
        self.answers("vm1", self.spawned(not_carried="it syncs through no hub",
                                         project={"id": "p-u", "name": "unshared"}))
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[-1], "seat spawned on vm1: repo/w  [a1b2c3d4 / %s]  status=working" % SEAT)
        self.assertNotIn("message it", out)
        self.assertIn("sminos: note: vm1 filed this seat in its project unshared, which its enrollment does not carry "
                      "(it syncs through no hub): it will not be listed here, and nothing said from here reaches it",
                      err)
        self.answers("vm1", self.spawned(not_carried="a word a newer VM knows", project={"id": "p-u",
                                                                                         "name": "unshared"}))
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("message it", out, "a word this Mac does not know: not carried")
        self.assertIn("sminos: note: vm1 filed this seat in its project unshared, which its enrollment does not carry: "
                      "it will not be listed here", err)
        self.assertNotIn("a word a newer VM knows", err, "with no reason shown")
        self.answers("vm1", self.spawned(not_carried="", project={"id": "p-u", "name": "unshared"}))
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("message it", out, "the key present, a string: not carried, whatever it says")
        self.assertIn("which its enrollment does not carry: it will not be listed here", err, "and no reason shown")
        self.answers("vm1", self.spawned(project={"id": "p-u", "name": "unshared"}))
        code, out, err = self.spawn("--on", "vm1")
        self.assertIn("(message it: sminos say", out, "no key: carried, the promise as before")

    def test_a_refusal_passes_its_exit_and_not_enrolled_is_refused_at_once_for_a_vm(self):
        self.answers("vm1", on.outcome_line(NONCE, {"ok": False, "exit": 4, "why": "other"}), code=4)
        code, _, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 4)
        self.assertIn("spawn --on: vm1's sminos answered exit 4; its line above says why", err)
        self.answers("vm1", on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"}), code=1)
        code, _, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 1)
        self.assertIn("spawn --on: vm1 is not enrolled in the org", err)
        self.assertEqual([c[1] for c in self.calls()].count("ssh"), 2, "no second call for a VM named")

    def test_under_new_a_line_outside_the_table_is_never_tried_again(self):
        for line, code in ((on.outcome_line(NONCE, {"ok": False, "exit": 2, "why": "not-enrolled"}), 2),
                           (on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "elsewhere"}), 1),
                           (on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled",
                                                    "not_carried": 7}), 1)):
            with self.subTest(line=line):
                self.forget_calls()
                self.answers("dc-x-0001", line, code=code)
                c, out, err = self.spawn("--on", "new")
                self.assertEqual(c, code, err)
                self.assertIn("is not known (the outcome line does not read as one)", err)
                self.assertIn("is kept and this session's thread owns it", err)
                self.assertEqual(self.verbs(), ["up", "ssh"])

    def test_a_name_devcloud_has_no_vm_for(self):
        code, out, err = self.spawn("--on", "mini")
        self.assertEqual(code, 1, err)
        self.assertIn("devcloud vm: no VM named mini in any usable account", err)
        self.assertIn("the outcome on mini is not known (no outcome line came back)", err)
        self.assertNotIn("If it is a Mac", err)
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon", "org.json"), "w") as f:
            json.dump({"projects": [], "machines": [{"name": "Mini"}], "at": ""}, f)
        code, out, err = self.spawn("--on", "mini")
        self.assertEqual(code, 1, err)
        self.assertTrue(err.rstrip().endswith("mini is a machine of this org that devcloud has no host for. If it is a "
                                              "Mac: a session is not opened on a Mac from another machine in this "
                                              "version, since a Mac's login keychain is closed to an ssh session and "
                                              "claude needs it; open it on that Mac"), err)


    def test_the_standin_runs_nothing_under_a_host_env_that_lacks_a_variable(self):
        ran = os.path.join(self.home, "ran")
        script = os.path.join(self.home, "sminos-here")
        with open(script, "w") as f:
            f.write("#!/bin/sh\ntouch %s\n" % ran)
        os.chmod(script, 0o755)
        full = {"HOME": self.home, "SMINOS_HOME": self.home, "DAEMON_HOST": "vm1", "PATH": "/usr/bin:/bin"}
        for lacking in ("HOME", "SMINOS_HOME", "DAEMON_HOST", "PATH"):
            with self.subTest(lacking=lacking):
                self.cfg = {"sminos": script,
                            "ssh_hosts": {"vm1": {"env": {k: v for k, v in full.items() if k != lacking}}}}
                self.save()
                code, out, err = self.spawn("--on", "vm1")
                self.assertIn("devcloud stand-in: ssh_hosts.vm1.env lacks %s" % lacking, err)
                self.assertFalse(os.path.exists(ran), "nothing was launched")


class VmSide(On):
    """The VM side's own line, for each way it ends, read by the Mac's check."""

    def asked(self, req=None, cwd=None, raw=None, task="a task", stdin=None, runcwd=None, session=None,
              launch=None, launcher=None, alias="w", **over):
        """The VM side run here with `req` (each key of `over` set, DROP's taken out), or `raw` as the value:
        (exit, stdout's lines, stderr, what was launched); `runcwd`, the directory the engine says the job runs
        in (a --worktree's), else the directory asked for; `session`, the session it runs in (none, as over
        `devcloud vm ssh`); `launch`, what the launcher answers, (short, banner), in place of a job;
        `launcher`, a shell script run as `claude` by the real run_claude_bg instead."""
        req = req or {"v": 1, "nonce": NONCE, "org": "org-1", "origin": None,
                      "by": {"alias": "boss", "short": "abcd1234", "project": "p", "project_name": "repo",
                             "machine": "mac"}}
        req.update(over)
        req = {k: v for k, v in req.items() if v is not DROP}
        out, err = io.StringIO(), io.StringIO()
        argv = ["spawn", alias, task, "--asked-from", raw or json.dumps(req), "--cwd", cwd or self.work]
        launched = {}

        def start(args, cwd_, settings):
            launched["task"] = args[-1]
            if launch is not None:
                return launch
            sid, launched["proc"] = self.session(root=cwd_, kind="bg", sid=JOB)
            return "a1b2c3d4", "banner"
        bindir = os.path.join(self.home, "launcher-bin")
        if launcher is not None:
            os.makedirs(bindir, exist_ok=True)
            with open(os.path.join(bindir, "claude"), "w") as f:
                f.write("#!/bin/sh\n" + launcher + "\n")
            os.chmod(os.path.join(bindir, "claude"), 0o755)
        with mock.patch.object(sminos, "run_claude_bg", side_effect=start) if launcher is None else \
                mock.patch.dict(os.environ, {"PATH": bindir + os.pathsep + os.environ["PATH"]}), \
                mock.patch.object(sminos, "poll_uuid", return_value=(JOB, "working", runcwd or cwd or self.work)), \
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session} if session else {}), \
                piped(stdin), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if not session:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            try:
                sminos.main(argv)
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
            finally:
                sminos.forget_caches()
        return code, out.getvalue().splitlines(), err.getvalue(), launched

    def test_a_spawn_ends_with_a_whole_line_and_names_its_spawner(self):
        code, lines, err, launched = self.asked()
        verdict, d = on.judge(lines, NONCE, "w", code)
        self.assertEqual((code, verdict), (0, "ok"), err)
        self.assertEqual((d["session"], d["alias"], d["machine"], d["cwd"], d["head"]),
                         (JOB, "w", "testhost", self.work, self.commit))
        self.assertNotIn("seat spawned:", "\n".join(lines))
        self.assertNotIn("not_carried", d, "a project this enrollment carries: no key")
        self.assertIn('boss (@abcd1234, in repo on mac; sminos say "@abcd1234 …" reaches it)', launched["task"])

    SPAWNER = "abcd1234-5678-4abc-8def-0123456789ab"

    def by(self, **over):
        """The spawner's `by` as a Mac of this version sends it: its project the one the directory is in."""
        p = sminos.resolve_project(self.work)
        return {"alias": "boss", "short": self.SPAWNER[:8], "project": p.id, "project_name": p.name, "machine": "mac",
                "session": self.SPAWNER, **over}

    def remote_joined(self, session, alias="boss", project=None):
        """A `joined` of a session of mac in the directory's project (or `project`), as the download brings it."""
        p = project or sminos.resolve_project(self.work)
        path = sminos.writer_path(p, "mac/" + session)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps({"ts": "2026-11-22T00:00:01.000Z", "writer": "mac/" + session, "seq": 1,
                                "kind": "joined", "session": session, "alias": alias, "name_source": "user",
                                "machine": "mac", "cwd": "/Users/x/repo", "worktree": "", "role": ""}) + "\n")
        sminos.forget_caches()

    def test_a_spawner_this_machine_has_not_read_yet_is_refused_and_nothing_is_launched(self):
        """A fresh VM holds no row of the spawner until its first download of the project's log reaches the
        spawner's writer: the child's first `@<short>` would reach no one, so nothing is opened yet."""
        code, lines, err, launched = self.asked(by=self.by())
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1,
                                                                         "why": "spawner-unknown"}), err)
        self.assertIn("spawn: this machine has not read the spawner, boss (@abcd1234), from the project's log yet", err)
        self.assertEqual(launched, {}, "no launcher was started")
        self.assertEqual(sminos.seats(), [], "no seat record was written")

    def test_a_spawner_whose_row_answers_its_short_is_spawned_for(self):
        self.remote_joined(self.SPAWNER)
        code, lines, err, launched = self.asked(by=self.by())
        self.assertEqual((code, on.judge(lines, NONCE, "w", code)[0]), (0, "ok"), err)
        self.assertIn('boss (@abcd1234, in ', launched["task"])

    def shadowed(self, code, lines, err, launched, alias="w"):
        """The VM side refused at once, the short naming someone else: no launch, no seat."""
        self.assertEqual(on.judge(lines, NONCE, alias, code), ("refused", {"ok": False, "exit": 1,
                                                                           "why": "spawner-shadowed"}), err)
        self.assertEqual(launched, {}, "no launcher was started")
        self.assertEqual(sminos.seats(), [], "no seat record was written")

    def test_a_short_that_answers_another_member_is_refused_at_once(self):
        """The child's tag reads the short as its project's aliases first: a member named so takes it, and the
        spawner's message would go to that member. Nothing the download brings changes that: no wait."""
        self.remote_joined(self.SPAWNER)
        self.remote_joined("eeee0000-5678-4abc-8def-0123456789ab", alias=self.SPAWNER[:8])
        code, lines, err, launched = self.asked(by=self.by())
        self.shadowed(code, lines, err, launched)
        self.assertIn("spawn: the spawner's short, @abcd1234, names abcd1234 (@eeee0000, in repo) on this machine", err)

    def test_a_child_whose_alias_is_the_spawner_s_short_is_refused_at_once(self):
        """Its own alias would take its first `@<short>`: the message would reach the child itself."""
        self.remote_joined(self.SPAWNER)
        code, lines, err, launched = self.asked(by=self.by(), alias=self.SPAWNER[:8])
        self.shadowed(code, lines, err, launched, alias=self.SPAWNER[:8])
        self.assertIn("names the session asked for itself (its alias abcd1234)", err)
        self.assertIn("spawn it under another alias", err)

    def test_a_spawner_whose_project_this_machine_registers_for_another_org_is_refused_at_once(self):
        """The tag reaches the spawner's session in the project the request names, but this machine's registration
        of that project names another org's hub: the reply would be written to a log the uplink never sends."""
        stale = os.path.join(self.home, "stale")
        os.makedirs(stale)
        pid = str(uuidlib.uuid4())
        with open(os.path.join(stale, ".smns"), "w") as f:
            json.dump({"project": pid, "name": "stale", "remote": "", "hub": {"org": "org-2"}}, f)
        q = self.project_of(stale)
        self.remote_joined(self.SPAWNER, project=q)
        code, lines, err, launched = self.asked(by=self.by(project=pid, project_name="stale"))
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1, "why": "other"}), err)
        self.assertIn("spawn: the spawner's short, @abcd1234, reaches boss in project stale, whose registration on "
                      "this machine its enrollment does not carry (its .smns names another org)", err)
        self.assertEqual(launched, {})
        self.assertEqual(sminos.seats(), [])

    def test_a_warning_before_an_ambiguous_answer_is_still_someone_else(self):
        """The resolver's own last word decides, not whatever a read printed before it."""
        self.remote_joined(self.SPAWNER)
        for sid in ("eeee0000-5678-4abc-8def-0123456789ab", "eeee1111-5678-4abc-8def-0123456789ab"):
            self.remote_joined(sid, alias=self.SPAWNER[:8])
        real = sminos.match_members

        def noisy(*a, **kw):
            sminos.warn("a reconcile's aside")
            return real(*a, **kw)
        with mock.patch.object(sminos, "match_members", side_effect=noisy):
            code, lines, err, launched = self.asked(by=self.by())
        self.assertIn("a reconcile's aside", err)
        self.shadowed(code, lines, err, launched)
        self.assertIn("names more than one member (ambiguous @abcd1234 matches:", err)

    def test_the_spawner_s_row_in_another_project_is_not_its_row_in_the_one_asked(self):
        """The request names the spawner's project now; this machine holds only its row of the project it was in
        before, which the child's tag would reach, writing to that project's log."""
        before = os.path.join(self.home, "before")
        os.makedirs(before)
        with open(os.path.join(before, ".smns"), "w") as f:
            json.dump({"project": str(uuidlib.uuid4()), "name": "before", "remote": "", "hub": {"org": "org-1"}}, f)
        old = self.project_of(before)
        self.remote_joined(self.SPAWNER, project=old)
        code, lines, err, launched = self.asked(by=self.by())
        self.shadowed(code, lines, err, launched)
        self.assertIn("names boss (@abcd1234, in before) on this machine", err)

    def test_a_request_from_an_older_mac_is_spawned_for_at_once(self):
        """No `by.session`: nothing is asked of the log, as before this version."""
        code, lines, err, _ = self.asked()
        self.assertEqual((code, on.judge(lines, NONCE, "w", code)[0]), (0, "ok"), err)

    def test_a_session_its_short_does_not_begin_is_read_as_absent(self):
        code, lines, err, _ = self.asked(by=self.by(session="ffff1234-5678-4abc-8def-0123456789ab"))
        self.assertEqual((code, on.judge(lines, NONCE, "w", code)[0]), (0, "ok"), err)

    def test_each_refusal_ends_with_a_whole_line_of_its_why(self):
        self.unenroll()
        code, lines, err, _ = self.asked()
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1, "why": "not-enrolled"}))
        self.assertIn("spawn: this machine is not enrolled in the org", err)
        self.enroll(org="org-2")
        code, lines, err, _ = self.asked()
        self.assertEqual(on.judge(lines, NONCE, "w", code)[1]["why"], "other-org")
        self.enroll()
        elsewhere = os.path.join(self.home, "elsewhere")
        gitq("init", "-q", elsewhere)
        gitq("remote", "add", "origin", "https://github.com/someone/else", cwd=elsewhere)
        for d, what in ((elsewhere, "a checkout of github.com/someone/else"), (self.home, "no checkout")):
            with self.subTest(what=what):
                code, lines, err, _ = self.asked(cwd=d, origin=KEY)
                self.assertEqual(on.judge(lines, NONCE, "w", code)[1]["why"], "other-repository")
                self.assertIn("spawn: %s is %s, and the machine that asked took it for its checkout of %s: nothing was "
                              "spawned. Name the directory with --cwd" % (d, what, KEY), err)
        code, lines, err, _ = self.asked(cwd=os.path.join(self.home, "missing"))
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 2, "why": "other"}))
        code, lines, err, _ = self.asked(origin=KEY)
        self.assertEqual(on.judge(lines, NONCE, "w", code)[0], "ok", err)

    def test_a_directory_in_a_project_this_enrollment_does_not_carry_is_refused_before_the_launch(self):
        """The session would be in the project spawn_fresh selects, which the uplink leaves out (a `.smns` that
        names no hub): refused, an explicit --cwd included, as the Mac refuses its own spawner's (not_carried)."""
        bare = os.path.join(self.home, "nowhere")
        os.makedirs(bare)
        with open(os.path.join(bare, ".smns"), "w") as f:
            json.dump({"project": str(uuidlib.uuid4()), "name": "nowhere", "remote": ""}, f)
        for origin in (None, KEY):
            with self.subTest(origin=origin):
                with mock.patch.object(on, "hold_to_origin"):   # the inferred directory's own check, aside here
                    code, lines, err, launched = self.asked(cwd=bare, origin=origin)
                self.assertEqual(on.judge(lines, NONCE, "w", code),
                                 ("refused", {"ok": False, "exit": 1, "why": "other"}))
                self.assertIn("spawn: %s is in project nowhere, which this machine's enrollment does not carry (it "
                              "syncs through no hub), so the session there and the machine that asked could not reach "
                              "each other: nothing was spawned. Name a directory of a project the org shares with --cwd"
                              % bare, err)
                self.assertEqual(launched, {}, "nothing launched")

    def test_a_worktree_the_engine_runs_in_whose_project_is_not_carried_is_said_in_the_outcome(self):
        """The reviewer's probe: `--worktree` puts the job in a linked worktree whose `.smns` names no hub, which
        admission (the directory asked for) cannot see before the launch. The launch is no refusal (F6): the
        outcome says it, with the fixed word for why the project is not carried."""
        wt = os.path.join(self.work, ".claude", "worktrees", "wt")
        gitq("worktree", "add", "-q", "-b", "worktree-wt", wt, cwd=self.work)
        with open(os.path.join(wt, ".smns"), "w") as f:
            json.dump({"project": str(uuidlib.uuid4()), "name": "unshared", "remote": ""}, f)
        code, lines, err, _ = self.asked(runcwd=wt)
        verdict, d = on.judge(lines, NONCE, "w", code)
        self.assertEqual((code, verdict), (0, "ok"), err)
        self.assertEqual((d["cwd"], d["project"]["name"], d.get("not_carried")),
                         (wt, "unshared", "it syncs through no hub"))
        self.assertIn(d["not_carried"], sminos.NOT_CARRIED_WORDS)

    def test_a_request_this_version_does_not_read_prints_no_line(self):
        for bad in ({"v": 2}, {"v": True}, {"nonce": "short"}, {"org": ""}, {"by": {"alias": "a"}},
                    {"by": {"alias": "a", "short": "XYZ", "project": "p", "project_name": "n", "machine": "m"}},
                    {"origin": 7}, {"origin": DROP}, {"by": DROP}, {"v": DROP}):
            with self.subTest(bad=bad):
                code, lines, err, _ = self.asked(**bad)
                self.assertEqual((code, lines), (2, []), err)
                self.assertIn("spawn: --asked-from is not a request this version reads", err)
        for bad in ("[]", "null", "7", "{"):
            with self.subTest(bad=bad):
                code, lines, err, _ = self.asked(raw=bad)
                self.assertEqual((code, lines), (2, []), err)

    def test_inside_a_session_the_flag_is_refused_before_anything_is_made(self):
        """`--asked-from` is the transport's (§8): a session that passes it would give its child the terminal's
        reach, not its own, so it is refused there as `say --notice` is, exit 2, before the request is read, with
        no outcome line, nothing launched and no seat. Over `devcloud vm ssh` there is no session: the same call
        spawns (G1)."""
        code, lines, err, launched = self.asked(session=self.sid)
        self.assertEqual((code, lines), (2, []), err)
        self.assertIn("sminos: spawn: --asked-from is the form another machine's sminos calls over devcloud vm ssh, "
                      "and a session is not one: drop it (sminos spawn --on <vm> opens a session on another machine)",
                      err)
        self.assertEqual(launched, {}, "nothing launched")
        self.assertEqual([x["alias"] for x in sminos.seats()], [], "no seat")
        code, lines, err, launched = self.asked(raw="not even a request", session=self.sid)
        self.assertEqual((code, lines), (2, []), "refused before the request is read")
        self.assertIn("a session is not one: drop it", err)
        code, lines, err, launched = self.asked()
        self.assertEqual(on.judge(lines, NONCE, "w", code)[0], "ok", err)

    def test_inside_a_session_it_is_refused_at_once_with_standard_input_left_open(self):
        """The real CLI, its standard input a pipe nobody closes: the refusal comes before the task is read,
        so it never waits on it (G1)."""
        request = json.dumps({"v": 1, "nonce": NONCE, "org": "org-1", "origin": None, "by": None})
        script = os.path.join(HERE, "..", "skills", "sminos", "scripts", "sminos.py")
        with open(os.path.join(self.home, "open-pipe.out"), "w+") as out, \
                open(os.path.join(self.home, "open-pipe.err"), "w+") as err:
            proc = subprocess.Popen([sys.executable, "-B", script, "spawn", "w", "-", "--asked-from=" + request,
                                     "--cwd", self.work], stdin=subprocess.PIPE, stdout=out, stderr=err,
                                    env={**os.environ, "CLAUDE_CODE_SESSION_ID": self.sid})
            try:
                code = proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                self.fail("it waited on standard input before refusing")
            finally:
                proc.stdin.close()
            out.seek(0)
            err.seek(0)
            self.assertEqual((code, out.read()), (2, ""))
            self.assertIn("a session is not one: drop it", err.read())

    def test_a_launcher_that_gave_no_answer_is_no_refusal_and_the_mac_says_not_known(self):
        """A launcher started and stopped at its bound may have started the job: no outcome line, so the Mac
        says the outcome is not known and where to look before a retry (row 29), never a refusal (G2). One that
        answered, with a failure, is still a refusal."""
        code, lines, err, _ = self.asked(launch=("", sminos.LaunchOutput("timed out", timeout=300.0)))
        self.assertEqual(code, 1, err)
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("unknown", "no outcome line came back"), lines)
        self.assertIn("sminos: spawn: the launcher (claude --bg) was started here and named no job (it gave no "
                      "answer within 300 s, and was stopped): a session may have started all the same; no outcome is "
                      "reported for it, so the machine that asked says it is not known: sminos list here shows "
                      "whether one runs", err)
        self.answers("vm1", *lines, code=code)
        mac, out, said = self.spawn("--on", "vm1")
        self.assertEqual(mac, 1, said)
        self.assertIn("spawn --on: the outcome on vm1 is not known (no outcome line came back): a session may or may "
                      "not have started there, and devcloud vm ssh vm1 -- sminos list shows", said)
        self.assertNotIn("answered exit", said)
        self.assertNotIn("seat spawned on", out)
        code, lines, err, _ = self.asked(launch=("", sminos.LaunchOutput("claude: refused", status=1)))
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1, "why": "other"}))

    def test_every_launcher_started_that_named_no_job_is_no_refusal(self):
        """Started, and no usable acknowledgement: an exit 0 with no job's banner, or a kill before one, through
        the real run_claude_bg; each prints no outcome line and says why. A launcher that refused in its own
        words (a non-zero exit), or could not be started, is still a refusal (G2)."""
        for script, why in (("echo starting; exit 0", "it exited 0 without naming a job"),
                            ("kill -9 $$", "it was ended by signal 9")):
            with self.subTest(why=why):
                code, lines, err, _ = self.asked(launcher=script)
                self.assertEqual(on.judge(lines, NONCE, "w", code), ("unknown", "no outcome line came back"), err)
                self.assertIn("sminos: spawn: the launcher (claude --bg) was started here and named no job (%s): a "
                              "session may have started all the same; no outcome is reported for it, so the machine "
                              "that asked says it is not known: sminos list here shows whether one runs" % why, err)
        code, lines, err, _ = self.asked(launcher="echo 'claude: not logged in' >&2; exit 1")
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1, "why": "other"}),
                         err)
        code, lines, err, _ = self.asked(launch=("", sminos.LaunchOutput("No such file or directory: 'claude'")))
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1, "why": "other"}))

    def test_a_launcher_whose_output_is_not_utf8_keeps_its_status(self):
        """A launcher that exits 0 after a byte that is not UTF-8, through the real run_claude_bg: its output is
        read with that byte replaced, so its status is kept and it is a launcher started that named no job, not
        a refusal (H1)."""
        code, lines, err, _ = self.asked(launcher=r"printf 'starting \377\n'; exit 0")
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("unknown", "no outcome line came back"), err)
        self.assertIn("was started here and named no job (it exited 0 without naming a job)", err)

    def test_a_request_carrying_the_markers_is_refused_with_its_line(self):
        """`unanswered` and `launched` are this side's own state: a request that carries them (extra keys pass
        the shape) is refused before any launcher ran with its outcome line, as any other (H2)."""
        self.unenroll()
        for markers in ({"unanswered": True}, {"launched": "a1b2c3d4"}, {"unanswered": True, "launched": "a1b2c3d4"}):
            with self.subTest(markers=markers):
                code, lines, err, launched = self.asked(**markers)
                self.assertEqual(on.judge(lines, NONCE, "w", code),
                                 ("refused", {"ok": False, "exit": 1, "why": "not-enrolled"}), err)
                self.assertNotIn("was launched here", err)
                self.assertEqual(launched, {}, "nothing launched")

    def test_a_success_it_cannot_say_whole_prints_no_line_and_names_the_job(self):
        """After a launch nothing is a refusal (§8 steps 6 and 8): no outcome line, so the Mac takes row 29; the
        VM's own diagnostic kept, and the job named."""
        with mock.patch.object(on, "head_of", return_value="not a commit"):
            code, lines, err, launched = self.asked()
        self.assertEqual(code, 1)
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("unknown", "no outcome line came back"), lines)
        self.assertIn("spawn: seat repo/w was spawned here (session %s), and its result could not be reported in "
                      "the outcome line's shape (" % JOB, err)
        self.assertIn("sminos: spawn: session a1b2c3d4 was launched here, and then this failed: it ended with exit 1, "
                      "its own line above saying why; no outcome is reported for it, so the machine that asked says it "
                      "is not known: sminos list here shows whether it runs, and claude stop a1b2c3d4 stops it", err)

    def test_a_launch_with_no_usable_session_id_prints_no_line_and_names_the_job(self):
        with mock.patch.object(sminos, "poll_uuid", return_value=None):
            out, err = io.StringIO(), io.StringIO()
            request = json.dumps({"v": 1, "nonce": NONCE, "org": "org-1", "origin": None, "by": None})
            with mock.patch.object(sminos, "run_claude_bg", return_value=("a1b2c3d4", "banner")), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                try:
                    sminos.main(["spawn", "w", "a task", "--asked-from", request, "--cwd", self.work])
                    code = 0
                except SystemExit as e:
                    code = e.code
                finally:
                    sminos.forget_caches()
        self.assertEqual(code, 1)
        self.assertEqual(on.judge(out.getvalue().splitlines(), NONCE, "w", code),
                         ("unknown", "no outcome line came back"))
        self.assertIn("produced no usable session uuid", err.getvalue())
        self.assertIn("sminos: spawn: session a1b2c3d4 was launched here, and then this failed: it ended with exit 1",
                      err.getvalue())

    def test_an_empty_task_on_standard_input_is_refused_with_a_line(self):
        code, lines, err, launched = self.asked(task="-", stdin=b"")
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 2, "why": "other"}))
        self.assertIn("spawn -: no text on standard input", err)
        self.assertEqual(launched, {}, "nothing launched")

    def task_given(self, *argv, stdin=None):
        """The task `sminos spawn <argv>` run here hands the launch (spawn_fresh), launching nothing."""
        given = []

        def fresh(*args, **kw):
            given.append(args[5])
            for held in args[12]:   # the seat's lock, which spawn_fresh's own path releases
                held.close()
            raise SystemExit(0)
        err = io.StringIO()
        with mock.patch.object(sminos, "spawn_fresh", side_effect=fresh), piped(stdin), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            with contextlib.suppress(SystemExit):
                sminos.main(["spawn", "w", *argv, "--cwd", self.work])
        sminos.forget_caches()
        self.assertEqual(len(given), 1, err.getvalue())
        return given[0]

    def test_the_session_on_the_vm_gets_the_task_a_spawn_here_would_give_it(self):
        request = json.dumps({"v": 1, "nonce": NONCE, "org": "org-1", "origin": None, "by": None})
        undecodable = b"x\xff".decode("utf-8", "surrogateescape")   # as Python reads such an argument
        for how, body in (("positional", "x\n"), ("positional", "x\r\n"), ("piped", b"x\n"), ("piped", b"x\r\n"),
                          ("piped", b"x\n\n"), ("positional", undecodable)):
            with self.subTest(how=how, body=body):
                task, stdin = (body, None) if how == "positional" else ("-", body)
                here = self.task_given(task, stdin=stdin)
                sent = {}

                def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
                    sent["task"] = stdin
                    return 0, [self.spawned()], "", False, True
                with mock.patch.object(on, "run_devcloud", side_effect=run):
                    code, _, err = self.spawn("--on", "vm1", task=task, stdin=stdin)
                self.assertEqual(code, 0, err)
                there = self.task_given("-", "--asked-from", request,
                                        stdin=sent["task"].encode("utf-8", "surrogateescape"))   # as run_devcloud feeds it
                self.assertEqual(there, here)

    def test_option_like_values_reach_the_vm_as_the_mac_read_them(self):
        """`--brief=--review` and an alias after `--`, through the real parser on both sides: the forwarded words
        parse on the VM to what they parsed to on the Mac."""
        for argv in (["spawn", "w", "a task", "--on", "vm1", "--brief=--review", "--role=-r", "--stamp=k=-v"],
                     ["spawn", "--on", "vm1", "--", "-alias", "-dash task"]):
            with self.subTest(argv=argv):
                sent = {}

                def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
                    sent["args"] = args
                    return 0, [self.spawned(alias=c.a.alias)], "", False, True
                mac = sminos.build_parser().parse_args(argv)
                with mock.patch.object(on, "run_devcloud", side_effect=run):
                    code, out, err = self.sminos_argv(*argv)
                self.assertEqual(code, 0, err)
                words = sent["args"][sent["args"].index("--") + 1:]
                self.assertEqual(words[:len(REMOTE_HEAD)], REMOTE_HEAD)
                words = words[len(REMOTE_HEAD):]
                said = io.StringIO()
                with contextlib.redirect_stderr(said):
                    try:
                        there = sminos.build_parser().parse_args(words)
                    except SystemExit:
                        self.fail("the VM's parser refused %r: %s" % (words, said.getvalue()))
                self.assertEqual((there.alias, there.task, there.brief, there.role, there.stamp),
                                 (mac.alias, "-", mac.brief, mac.role, mac.stamp))
                self.assertIsNotNone(there.asked_from)

    def test_without_the_flag_spawn_is_as_before(self):
        out = io.StringIO()
        with mock.patch.object(sminos, "run_claude_bg", return_value=("a1b2c3d4", "banner")), \
                mock.patch.object(sminos, "poll_uuid", return_value=(JOB, "working", self.work)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            sminos.main(["spawn", "w", "a task", "--cwd", self.work])
        sminos.forget_caches()
        self.assertTrue(out.getvalue().startswith("seat spawned: repo/w  [a1b2c3d4 / %s]" % JOB), out.getvalue())

    # --channel's VM side (EN.G2's §1): the request's shape, its checks before the launch, the qualified address,
    # the outcome's `channels`. The kept welcome lists channels unless a case says otherwise.

    CHANNELS = [{"id": DESK, "name": "desk"}]

    def welcomed(self):
        sminos.audience_module().keep_capabilities(["channels"])

    def test_a_request_whose_channels_are_not_whole_prints_no_line(self):
        self.welcomed()
        bad = [[], [{"id": DESK}], [{"id": "x", "name": "desk"}], [{"id": DESK, "name": "has space"}],
               [{"id": DESK, "name": "desk"}, {"id": DESK, "name": "again"}], {"id": DESK, "name": "desk"},
               [{"id": cid, "name": "c"} for cid in ids(129)], [{"id": DESK, "name": 5}]]
        for chans in bad:
            with self.subTest(chans=str(chans)[:60]):
                code, lines, err, launched = self.asked(channels=chans)
                self.assertEqual(code, 2, err)
                self.assertNotIn("sminos-spawn", "\n".join(lines))
                self.assertEqual(launched, {})
        code, lines, err, _ = self.asked(channels=[{"id": cid, "name": "c"} for cid in ids(128)])
        self.assertEqual(code, 0, err + " — 128 is whole")

    def test_no_welcome_kept_a_welcome_without_channels_and_an_uncarried_channel_launch_nothing(self):
        self.welcomed()
        os.unlink(sminos.audience_module().audiences_path())
        code, lines, err, launched = self.asked(channels=self.CHANNELS)
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1,
                                                                         "why": "welcome-unknown"}), err)
        self.assertIn("this machine has kept no welcome of its endpoint yet", err)
        self.assertEqual((launched, sminos.seats()), ({}, []))
        sminos.audience_module().keep_capabilities(["access"])
        code, lines, err, launched = self.asked(channels=self.CHANNELS)
        self.assertEqual(on.judge(lines, NONCE, "w", code)[1]["why"], "other", err)
        self.assertIn("this machine's endpoint serves no channels", err)
        sminos.audience_module().keep_capabilities(["channels"])
        register(DESK, "here-desk", hub={"url": HUB["url"], "org": "org-2"})
        code, lines, err, launched = self.asked(channels=self.CHANNELS)
        self.assertEqual(on.judge(lines, NONCE, "w", code)[1]["why"], "other", err)
        self.assertIn("does not carry the log of channel here-desk (%s)" % DESK, err)
        self.assertEqual((launched, sminos.seats()), ({}, []))
        self.assertEqual(sminos.registration(LOBBY), {}, "nothing registered before a launch")

    def test_a_channel_the_directory_retired_is_refused_though_no_registration_is_here(self):
        self.welcomed()
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "org.json"), {
            "projects": [{"id": LOBBY, "name": "lobby", "retired": True}], "machines": [], "at": sminos.now(ms=True)})
        sminos.forget_caches()
        self.assertEqual(sminos.registration(LOBBY), {}, "the uplink registers no retired entry")
        code, lines, err, launched = self.asked(channels=[{"id": DESK, "name": "desk"}, {"id": LOBBY, "name": "lobby"}])
        self.assertEqual(on.judge(lines, NONCE, "w", code)[1]["why"], "other", err)
        self.assertIn("the org's directory has retired channel lobby (%s)" % LOBBY, err)
        self.assertEqual((launched, sminos.seats()), ({}, []))
        self.assertEqual((sminos.registration(DESK), sminos.registration(LOBBY)), ({}, {}), "nothing registered")

    def test_without_channels_nothing_of_it_is_read_and_the_outcome_has_no_key(self):
        self.welcomed()
        os.unlink(sminos.audience_module().audiences_path())
        code, lines, err, launched = self.asked()
        verdict, d = on.judge(lines, NONCE, "w", code)
        self.assertEqual(verdict, "ok", err)
        self.assertNotIn("channels", d)
        self.assertNotIn("You are being placed", launched["task"])

    def test_a_placed_spawn_reports_its_channels_registers_one_it_did_not_know_and_says_the_qualified_address(self):
        self.welcomed()
        self.remote_joined(self.SPAWNER)
        p = sminos.resolve_project(self.work)
        register(LOBBY, "its-lobby")
        code, lines, err, launched = self.asked(by=self.by(), channels=[{"id": DESK, "name": "desk"},
                                                                        {"id": LOBBY, "name": "lobby"}])
        verdict, d = on.judge(lines, NONCE, "w", code, [DESK, LOBBY])
        self.assertEqual(verdict, "ok", err)
        self.assertEqual(d["channels"], [{"id": DESK, "state": "applied", "why": ""},
                                         {"id": LOBBY, "state": "applied", "why": ""}])
        self.assertEqual(sminos.registration(DESK)["name"], "desk", "registered under the name sent")
        self.assertEqual(sminos.registration(LOBBY)["name"], "its-lobby", "its own registration kept")
        tag = "@%s/%s" % (p.id, self.SPAWNER[:8])
        self.assertIn('boss (%s, in %s on mac; sminos say "%s …" reaches it as it is now; once it has sent you a '
                      "message, answer by the reply line of its latest message)"
                      % (tag, p.name, tag), launched["task"])
        self.assertIn('You are being placed in the channel "desk", as your spawner asked: once that is recorded on '
                      'your machine, `sminos list %s`' % DESK,
                      launched["task"])
        self.assertIn('You are being placed in the channel "its-lobby"', launched["task"], "as this machine knows it")
        self.assertNotIn("seat spawned", "\n".join(lines), "no placement line on the VM side")

    def test_the_qualified_tag_passes_beside_another_project_s_alias_and_is_shadowed_in_the_spawner_s_own(self):
        self.welcomed()
        self.remote_joined(self.SPAWNER)
        other = os.path.join(self.home, "other")
        os.makedirs(other)
        with open(os.path.join(other, ".smns"), "w") as f:
            json.dump({"project": str(uuidlib.uuid4()), "name": "other", "remote": "", "hub": {"org": "org-1"}}, f)
        self.remote_joined("eeee0000-5678-4abc-8def-0123456789ab", alias=self.SPAWNER[:8],
                           project=self.project_of(other))
        code, lines, err, launched = self.asked(by=self.by(), channels=self.CHANNELS)
        self.assertEqual(on.judge(lines, NONCE, "w", code)[0], "ok", err)

    def test_the_qualified_tag_is_shadowed_by_an_alias_in_the_spawner_s_own_project(self):
        self.welcomed()
        self.remote_joined(self.SPAWNER)
        self.remote_joined("eeee1111-5678-4abc-8def-0123456789ab", alias=self.SPAWNER[:8])
        code, lines, err, launched = self.asked(by=self.by(), channels=self.CHANNELS)
        self.shadowed(code, lines, err, launched)
        p = sminos.resolve_project(self.work)
        self.assertIn("spawn: the spawner's address, @%s/%s, names" % (p.id, self.SPAWNER[:8]), err)



# ------------------------------------------------------------ spawn --on --channel (EN.G2's M1, Interfaces §1)

class OnChannels(On):
    """The Mac's side of --channel: decided before devcloud, the request, the outcome's `channels` and its lines."""

    def setUp(self):
        super().setUp()
        register(DESK, "desk")
        register(LOBBY, "lobby")

    def request_sent(self, n=-1):
        return json.loads(vm_side([c for c in self.calls() if c[1] == "ssh"][n]).asked_from)

    def placed(self, *entries, **over):
        return self.spawned(channels=[{"id": cid, "state": state, "why": why} for cid, state, why in entries], **over)

    def test_a_name_refused_on_the_mac_calls_no_devcloud(self):
        self.refused(4, "no channel 'nowhere' is known on this machine", "--on", "vm1", "--channel", "nowhere")
        self.refused(4, "no channel 'nowhere' is known on this machine", "--on", "new", "--channel", "nowhere")
        register(ids(1)[0], "desk")
        self.refused(4, "ambiguous name 'desk'", "--on", "vm1", "--channel", "desk")
        self.refused(4, "is a project, not a channel", "--on", "vm1", "--channel", sminos.resolve_project(self.work).id)

    def test_129_channels_are_refused_on_the_mac_and_more_values_folding_to_128_are_sent_folded(self):
        many = ids(129)
        for cid in many:
            register(cid, "c" + cid[:8])
        argv = [w for cid in many for w in ("--channel", cid)]
        self.refused(1, "--channel names 129 channels, and a thread is in at most 128: nothing was spawned",
                     "--on", "new", *argv)
        folded = many[:128]
        self.answers("vm1", self.placed(*[(cid, "applied", "") for cid in folded]))
        code, out, err = self.spawn("--on", "vm1", *[w for cid in folded + folded[:5] for w in ("--channel", cid)])
        self.assertEqual(code, 0, err)
        self.assertEqual([c["id"] for c in self.request_sent()["channels"]], folded)

    def test_a_channel_this_enrollment_does_not_carry_is_refused_before_devcloud(self):
        register(ids(1)[0], "far", hub={"url": HUB["url"], "org": "org-2"})
        self.refused(1, "cannot spawn a thread into far: this machine's enrollment does not carry its log (its "
                        "registration on this machine names another org): nothing was spawned",
                     "--on", "new", "--channel", "far")

    def test_a_spawner_whose_project_id_fits_no_qualifier_is_refused_before_devcloud(self):
        real = on.route_back

        def odd(c, enrolled):
            return {**real(c, enrolled), "project": "an id with spaces"}
        with mock.patch.object(on, "route_back", side_effect=odd):
            self.refused(1, "this session's project id is not one a tag's qualifier takes", "--on", "new",
                         "--channel", "desk")
            self.answers("vm1", self.spawned())
            code, out, err = self.spawn("--on", "vm1")
            self.assertEqual(code, 0, err + " — without --channel it is G1's spawn")

    def test_the_request_carries_the_channels_by_id_and_name_and_none_without_the_flag(self):
        self.answers("vm1", self.spawned())
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("channels", self.request_sent(), "byte for byte G1's request")
        self.forget_calls()
        self.answers("vm1", self.placed((LOBBY, "applied", ""), (DESK, "applied", "unchanged")))
        code, out, err = self.spawn("--on", "vm1", "--channel", "lobby", "--channel", DESK)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.request_sent()["channels"], [{"id": LOBBY, "name": "lobby"}, {"id": DESK, "name": "desk"}])
        label = "w#%s" % JOB[:8]   # the session's first eight, never the outcome's short (a1b2c3d4)
        self.assertEqual(out.splitlines()[1:], ["%s: in lobby" % label, "%s: already in desk" % label])

    def test_each_failed_word_on_the_vm_is_a_warning_naming_the_channel_by_id_and_the_thread_by_its_session(self):
        words = sorted(sminos.channels_module().OWN_FAILED) + ["unregistered", "not-carried", "time", "error",
                                                              "a-word-of-a-later-copy"]
        for word in words:
            with self.subTest(word=word):
                self.answers("vm1", self.placed((DESK, "failed", word), (LOBBY, "refused", "limit")))
                code, out, err = self.spawn("--on", "vm1", "--channel", "desk", "--channel", "lobby")
                self.assertEqual(code, 0, err)
                said = sminos.channels_module().placement_words("failed", word)
                self.assertIn("sminos: warning: spawn completed, but w#%s was not placed in desk on vm1 (%s): sminos "
                              "channel add %s %s asks its machine, once sminos list --machine vm1 shows it here"
                              % (JOB[:8], said, DESK, JOB), err)
                self.assertIn("was not placed in lobby on vm1 (it is in 128 channels, the limit)", err)
        self.assertEqual(sminos.channels_module().placement_words("failed", "a-word-of-a-later-copy"),
                         "a-word-of-a-later-copy")

    def test_a_carriage_the_vm_could_not_read_makes_no_promise(self):
        self.answers("vm1", self.placed((DESK, "failed", "time"),
                                        not_carried=sminos.channels_module().CARRIAGE_UNREAD))
        code, out, err = self.spawn("--on", "vm1", "--channel", "desk")
        self.assertEqual(code, 0, err)
        self.assertIn("whether its enrollment carries that project could not be read once it was placed: it may not "
                      "be listed here, and what is said from here may not reach it", err)
        self.assertNotIn("it is listed here once", out + err)
        self.assertNotIn("which its enrollment does not carry", err)

    def test_identity_and_a_project_not_carried_are_one_warning_that_names_no_membership(self):
        self.answers("vm1", self.placed((DESK, "failed", "identity"), (LOBBY, "failed", "identity")))
        code, out, err = self.spawn("--on", "vm1", "--channel", "desk", "--channel", "lobby")
        self.assertEqual(code, 0, err)
        self.assertIn("spawn completed, but none of the placements asked for was made: vm1 is no longer enrolled in "
                      "this org", err)
        self.assertNotIn("channel add", err)
        self.answers("vm1", self.placed((DESK, "failed", "project-not-carried"), (LOBBY, "failed", "project-not-carried"),
                                        not_carried="it syncs through no hub", project={"id": "p-u", "name": "u"}))
        code, out, err = self.spawn("--on", "vm1", "--channel", "desk", "--channel", "lobby")
        self.assertEqual(code, 0, err)
        self.assertIn("filed this seat in its project u, which its enrollment does not carry", err)
        self.assertIn("none of the placements asked for (desk, lobby) was made: its project on vm1 is not carried, "
                      "and this project's memberships will not be seen from here", err)
        for absent in ("channel add", "once it is listed here", ": in desk", "not placed in"):
            self.assertNotIn(absent, out + err)

    def test_an_older_vm_that_reports_no_channels_is_said_so_naming_no_membership(self):
        self.answers("vm1", self.spawned())
        code, out, err = self.spawn("--on", "vm1", "--channel", "desk")
        self.assertEqual(code, 0, err)
        self.assertIn("spawn completed, but vm1's sminos did not carry out the placements asked for (it predates "
                      "spawn --channel). Which channels w#%s is in is not known here: sminos list %s shows, once its "
                      "events arrive, and sminos channel add %s %s asks its machine. It was told to reach you as @%s, "
                      "which a member of a channel it is already in can answer to if that is its alias"
                      % (JOB[:8], DESK, DESK, JOB, self.sid[:8]), err)
        self.assertNotIn(": in desk", out)

    def test_an_outcome_whose_channels_are_not_the_ones_asked_or_not_whole_is_not_known(self):
        cases = [
            ("the outcome line's channels are not the ones asked", self.placed((LOBBY, "applied", ""))),
            ("the outcome line's channels are not the ones asked", self.placed((DESK, "applied", ""), (LOBBY, "applied", ""))),
            ("the outcome line does not read as one", self.placed((DESK, "applied", "limit"))),
            ("the outcome line does not read as one", self.placed((DESK, "refused", "time"))),
            ("the outcome line does not read as one", self.placed((DESK, "failed", ""))),
            ("the outcome line does not read as one", self.placed((DESK, "pending", "x"))),
            ("the outcome line does not read as one", self.placed(("not-an-id", "applied", ""))),
            ("the outcome line does not read as one", self.spawned(channels={"id": DESK})),
        ]
        for reason, line in cases:
            with self.subTest(line=line[-120:]):
                self.answers("vm1", line)
                code, out, err = self.spawn("--on", "vm1", "--channel", "desk")
                self.assertEqual(code, 1, err)
                self.assertIn("the outcome on vm1 is not known (%s)" % reason, err)
        self.answers("vm1", self.placed((DESK, "failed", "x")))
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err + " — a Mac that sent no channel ignores a whole list")

    def test_a_lost_call_names_every_seat_the_engines_jobs_and_each_channel_and_g1_s_line_without_channels(self):
        self.answers("vm1", "nothing whole", code=0)
        code, out, err = self.spawn("--on", "vm1", "--channel", "desk", "--channel", "lobby")
        self.assertEqual(code, 1, err)
        self.assertIn("the outcome on vm1 is not known (no outcome line came back): a session may or may not have "
                      "started there. Do not spawn it again before looking: devcloud vm ssh vm1 -- sminos list --here "
                      "--all lists every seat on vm1, in any project, and devcloud vm ssh vm1 -- claude agents the "
                      "engine's jobs there, if a session started and no seat was recorded. devcloud vm ssh vm1 -- "
                      "sminos list %s shows who is in desk there, once vm1 has registered it. devcloud vm ssh vm1 -- "
                      "sminos list %s shows who is in lobby there, once vm1 has registered it; a channel that does not "
                      "list it shows nothing about whether it was launched"
                      % (DESK, LOBBY), err)
        code, out, err = self.spawn("--on", "vm1")
        self.assertIn("a session may or may not have started there, and devcloud vm ssh vm1 -- sminos list shows",
                      err)
        self.assertNotIn("--here --all", err)

if __name__ == "__main__":
    unittest.main()
