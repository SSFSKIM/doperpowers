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


def gitq(*args, cwd=None):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main",
                           *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class On(Machine):
    def setUp(self):
        super().setUp()
        h = os.environ["HOME"]
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

    def spawn(self, *argv, session=True, cwd=None, alias="w"):
        """(exit, stdout, stderr) of `sminos spawn <alias> <task> <argv>` run here, from the session (or a
        terminal), under a fixed nonce."""
        out, err = io.StringIO(), io.StringIO()
        env = {"CLAUDE_CODE_SESSION_ID": self.sid} if session else {}
        here = os.getcwd()
        os.chdir(cwd or self.work)
        try:
            with mock.patch.dict(os.environ, env), mock.patch.object(on.secrets, "token_hex", return_value=NONCE), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                if not session:
                    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                try:
                    sminos.main(["spawn", alias, "a task", *argv])
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
        self.answers("vm1", 'sminos-spawn %s {"ok": true}' % ("e" * 16), self.spawned())
        code, _, err = self.spawn("--on", "vm1")
        self.assertEqual(code, 0, err)

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


class VmSide(On):
    """The VM side's own line, for each way it ends, read by the Mac's check."""

    def asked(self, req=None, cwd=None, **over):
        req = req or {"v": 1, "nonce": NONCE, "org": "org-1", "origin": None,
                      "by": {"alias": "boss", "short": "abcd1234", "project": "p", "project_name": "repo",
                             "machine": "mac"}}
        req.update(over)
        out, err = io.StringIO(), io.StringIO()
        argv = ["spawn", "w", "a task", "--asked-from", json.dumps(req), "--cwd", cwd or self.work]
        launched = {}

        def start(args, cwd_, settings):
            launched["task"] = args[-1]
            sid, launched["proc"] = self.session(root=cwd_, kind="bg", sid=JOB)
            return "a1b2c3d4", "banner"
        with mock.patch.object(sminos, "run_claude_bg", side_effect=start), \
                mock.patch.object(sminos, "poll_uuid", return_value=(JOB, "working", cwd or self.work)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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
        for bad in ({"v": 2}, {"nonce": "short"}, {"org": ""}, {"by": {"alias": "a"}},
                    {"by": {"alias": "a", "short": "XYZ", "project": "p", "project_name": "n", "machine": "m"}}):
            with self.subTest(bad=bad):
                code, lines, err, _ = self.asked(**bad)
                self.assertEqual((code, lines), (2, []))
                self.assertIn("spawn: --asked-from is not a request this version reads", err)

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
