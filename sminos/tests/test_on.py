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
  shape is an outcome that is not known, never tried again; and the VM
  side's own line, for each way it ends, read by the same check.

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
import signal
import subprocess
import sys
import threading
import time
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
        """(exit, stdout, stderr) of `sminos spawn <alias> <task> <argv>` run here, from the session (or a
        terminal), under a fixed nonce; `stdin`, bytes, piped to it."""
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
                    sminos.main(["spawn", alias, task, *argv])
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
        self.assertEqual(self.up_args(), ["--enroll", "--keep", "--expect-creator", self.sid[:8], "--label", "w",
                                          "--project", "example/repo@topic"])
        self.assertIn("sminos: note: making a VM (a few minutes; devcloud's own lines follow): devcloud vm up "
                      "--enroll --keep --expect-creator %s --label w --project example/repo@topic" % self.sid[:8], err)
        lines = out.splitlines()
        self.assertTrue(lines.index("dc-x-0001  ready in 0m01s") < len(lines) - 1, "devcloud's lines come first")
        self.assertEqual(lines[-1], 'seat spawned on dc-x-0001: repo/w  [a1b2c3d4 / %s]  status=working  (message '
                                    'it: sminos say "@%s …"; it is listed here once dc-x-0001\'s events arrive)'
                         % (SEAT, JOB[:8]))
        self.assertIn("sminos: note: dc-x-0001 is kept and this session's thread owns it: devcloud vm down "
                      "dc-x-0001 ends it, and it sends a notice after three idle days", err)
        self.assertNotIn("moved while the VM was made", err)
        ssh = [c for c in self.calls() if c[1] == "ssh"][0]
        self.assertEqual(ssh[2:4], ["dc-x-0001", "--"])
        request = json.loads(ssh[ssh.index("--asked-from") + 1])
        self.assertEqual(request, {"v": 1, "nonce": NONCE, "org": "org-1", "origin": KEY,
                                   "by": {"alias": request["by"]["alias"], "short": self.sid[:8],
                                          "project": sminos.resolve_project(self.work).id,
                                          "project_name": sminos.resolve_project(self.work).name,
                                          "machine": "testhost"}})
        self.assertEqual(ssh[ssh.index("--cwd") + 1], "~/Developer/GitHub/repo")

    def test_label_confirmed_and_named_projects(self):
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001", alias="Big_W"))
        gitq("remote", "set-url", "origin", "https://github.com/example/nowhere", cwd=self.work)  # origin unasked
        code, _, err = self.spawn("--on", "new", "--vm-project", "example/repo@main", "--vm-project", "maws",
                                  "--vm-confirmed", alias="Big_W")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.up_args(), ["--enroll", "--keep", "--expect-creator", self.sid[:8],
                                          "--project", "example/repo@main", "--project", "maws", "--confirmed"])

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
        self.assertIn("sminos: note: origin's topic moved while the VM was made: the VM's checkout is at %s" % other,
                      err)
        self.answers("vm1", self.spawned(head=other))
        code, out, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("moved while", err)
        self.assertNotIn("is kept and", err)

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
        self.assertIn("example/repo@main", [c for c in self.calls() if c[1] == "up"][0])

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
        self.assertIn("example/fork@feature", [c for c in self.calls() if c[1] == "up"][0])

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


    def test_a_tag_named_as_the_branch_reads_the_branch(self):
        gitq("tag", "topic", cwd=self.work)
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        code, _, err = self.spawn("--on", "new")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.up_args()[-2:], ["--project", "example/repo@topic"])

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

    def waited(self, *answers, wait="60", poll="30", bound="480", reach_takes=0):
        """`--on new` under a clock that only sleeping and each read of the reach rule (`reach_takes` seconds)
        move, devcloud answering `up` with a host and each `vm ssh` with the next of `answers` ((exit, lines,
        timed out)): (exit, stderr, each try's (start, bound))."""
        clock, tries, left = [1000.0], [], list(answers)
        reach = on.reach

        def slow_reach(c):
            clock[0] += reach_takes
            reach(c)

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")   # as run_devcloud's reading of the ready line records it
                return 0, ["dc-x-0001  ready in 0m01s"], "", False
            tries.append((clock[0], timeout))
            code, lines, timed_out = left.pop(0)
            return code, lines, "", timed_out
        fake = mock.Mock(monotonic=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))
        env = {"SMINOS_ON_ENROLL_WAIT": wait, "SMINOS_ON_ENROLL_POLL": poll, "SMINOS_ON_TIMEOUT": bound}
        with mock.patch.object(on, "run_devcloud", side_effect=run), mock.patch.object(on, "time", fake), \
                mock.patch.object(on, "reach", slow_reach), mock.patch.dict(os.environ, env):
            code, out, err = self.spawn("--on", "new")
        self.assertNotIn("seat spawned on", out)
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

    def test_stopped_between_two_tries_of_the_wait_keeps_the_vm(self):
        def guard(*_):
            raise AssertionError("the SIGTERM reached this test's own handler, not sminos's")
        self.addCleanup(signal.signal, signal.SIGTERM, signal.signal(signal.SIGTERM, guard))
        no = (1, [on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "not-enrolled"})], "", False)
        real = time.sleep

        def run(c, args, stdin=None, timeout=None, keep_err=False, **kw):
            if args[:2] == ["vm", "up"]:
                c.ready.append("dc-x-0001")   # as run_devcloud's reading of the ready line records it
                return 0, ["dc-x-0001  ready in 0m01s"], "", False
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

    def test_stopped_while_up_runs_after_it_named_its_host_keeps_the_vm(self):
        self.cfg["up"] = {"hold": os.path.join(self.home, "never")}
        self.answers("dc-x-0001", self.spawned(machine="dc-x-0001"))
        err = self.stopped("--on", "new")
        self.assertIn("spawn --on: stopped while devcloud ran", err)
        self.assertIn(". The VM dc-x-0001 is kept and", err)
        self.assertEqual(self.verbs(), ["up"])

    def test_stopped_after_up_exited_before_its_result_returned_keeps_the_vm(self):
        closed, calls = on.closed, []

        def stopped_once(proc):
            calls.append(proc)
            if len(calls) == 1:   # up's own: its child has exited, and its result is not yet returned
                raise KeyboardInterrupt
            closed(proc)
        with mock.patch.object(on, "closed", stopped_once):
            code, out, err = self.spawn("--on", "new")
        self.assertEqual(code, 1, err)
        self.assertIn("dc-x-0001  ready in 0m01s", out.splitlines())
        self.assertIn("spawn --on: stopped while devcloud ran", err)
        self.assertIn(". The VM dc-x-0001 is kept and", err)
        self.assertEqual(self.verbs(), ["up"])
        for proc in calls:
            closed(proc)

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
        ]
        for reason, lines in cases:
            with self.subTest(reason=reason, lines=lines[0][:60]):
                self.unknown(reason, *lines)
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
                           (on.outcome_line(NONCE, {"ok": False, "exit": 1, "why": "elsewhere"}), 1)):
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

    def asked(self, req=None, cwd=None, raw=None, task="a task", stdin=None, **over):
        """The VM side run here with `req` (each key of `over` set, DROP's taken out), or `raw` as the value:
        (exit, stdout's lines, stderr, what was launched)."""
        req = req or {"v": 1, "nonce": NONCE, "org": "org-1", "origin": None,
                      "by": {"alias": "boss", "short": "abcd1234", "project": "p", "project_name": "repo",
                             "machine": "mac"}}
        req.update(over)
        req = {k: v for k, v in req.items() if v is not DROP}
        out, err = io.StringIO(), io.StringIO()
        argv = ["spawn", "w", task, "--asked-from", raw or json.dumps(req), "--cwd", cwd or self.work]
        launched = {}

        def start(args, cwd_, settings):
            launched["task"] = args[-1]
            sid, launched["proc"] = self.session(root=cwd_, kind="bg", sid=JOB)
            return "a1b2c3d4", "banner"
        with mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                mock.patch.object(sminos, "poll_uuid", return_value=(JOB, "working", cwd or self.work)), \
                piped(stdin), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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
        self.assertIn('boss (@abcd1234, in repo on mac; sminos say "@abcd1234 …" reaches it)', launched["task"])

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

    def test_a_success_it_cannot_say_whole_ends_with_a_refusal_and_says_why(self):
        with mock.patch.object(on, "head_of", return_value="not a commit"):
            code, lines, err, launched = self.asked()
        self.assertEqual(on.judge(lines, NONCE, "w", code), ("refused", {"ok": False, "exit": 1, "why": "other"}))
        self.assertIn("spawn: seat repo/w was spawned here (session %s), and its result could not be reported in "
                      "the outcome line's shape (" % JOB, err)
        self.assertIn("sminos list here shows it", err)
        self.assertNotIn("was not", err)

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
                    return 0, [self.spawned()], "", False
                with mock.patch.object(on, "run_devcloud", side_effect=run):
                    code, _, err = self.spawn("--on", "vm1", task=task, stdin=stdin)
                self.assertEqual(code, 0, err)
                there = self.task_given("-", "--asked-from", request,
                                        stdin=sent["task"].encode("utf-8", "surrogateescape"))   # as run_devcloud feeds it
                self.assertEqual(there, here)

    def test_without_the_flag_spawn_is_as_before(self):
        out = io.StringIO()
        with mock.patch.object(sminos, "run_claude_bg", return_value=("a1b2c3d4", "banner")), \
                mock.patch.object(sminos, "poll_uuid", return_value=(JOB, "working", self.work)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            sminos.main(["spawn", "w", "a task", "--cwd", self.work])
        sminos.forget_caches()
        self.assertTrue(out.getvalue().startswith("seat spawned: repo/w  [a1b2c3d4 / %s]" % JOB), out.getvalue())


if __name__ == "__main__":
    unittest.main()
