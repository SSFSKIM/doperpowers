"""The lease on a host (the driver's Design §4.1): the lifecycle lock, `lease
set`, the lease service's run, the creator's warning and the unpushed scan it
names. Real locks, real git repositories, a stand-in for systemd."""

import contextlib
import io
import json
import os
import pathlib
import pwd
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import departure, descriptor, lease, nodekind, proc, redact, status
from devcloudlib.proc import User

from test_departure import DepartureBase

NOW = 1_792_000_000
BASE = ("DEVCLOUD_NAME=dc-build-7f3a\nDEVCLOUD_KIND=vm\nDEVCLOUD_ROLE=persistent\nDEVCLOUD_TAILSCALE=none\n"
        "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=example-project\n"
        "DEVCLOUD_CONFIG_REPO=https://github.com/example/config.git\nDEVCLOUD_CONFIG_TOKEN_SECRET=config-token\n")


class LeaseBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-lease-"))
        self.desc = self.tmp / "boot.env"
        self.paths = dict(desc_path=self.desc, lock_path=self.tmp / "lifecycle.lock",
                          status_path=self.tmp / "status.json")
        me = pwd.getpwuid(os.getuid())
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.tmp / "home")
        self.write(NOW + 7200)

    def write(self, expires, adopted=False):
        text = BASE + (f"DEVCLOUD_EXPIRES={expires}\n" if expires is not None else "")
        self.desc.write_text(text + ("DEVCLOUD_ADOPTED=1\n" if adopted else ""))
        self.desc.chmod(0o600)

    def set_lease(self, value, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = lease.set_lease(value, out=lambda m: None, **self.paths, **kw)
        return code, out.getvalue()


class LeaseSetTest(LeaseBase):
    def test_writes_the_lease_and_prints_the_one_in_force(self):
        code, printed = self.set_lease(NOW + 9000)
        self.assertEqual((code, printed), (0, f"{NOW + 9000}\n"))
        self.assertEqual(descriptor.load(self.desc).expires, NOW + 9000)
        self.assertEqual(self.desc.stat().st_mode & 0o777, 0o600, "the descriptor's mode changed")

    def test_a_lease_end_in_the_past_is_the_hosts_to_accept(self):
        self.assertEqual(self.set_lease(1)[0], 0)

    def test_gives_a_keep_host_a_lease(self):
        self.write(None)
        self.assertEqual(self.set_lease(NOW)[0], 0)
        self.assertEqual(descriptor.load(self.desc).expires, NOW)

    def test_refused_once_the_departure_has_started(self):
        for state in status.DEPARTURE_STARTED:
            with self.subTest(state=state):
                status.set_lifecycle("depart", state, state, path=self.paths["status_path"])
                self.assertEqual(self.set_lease(NOW + 9000), (3, ""))
                self.assertEqual(descriptor.load(self.desc).expires, NOW + 7200)


class LeaseSetCapTest(LeaseBase):
    """`lease set <unix> --cap <unix>`: the driver's unconfirmed request,
    decided under the lock against the lease in force (§4.1)."""

    CAP = NOW + 3 * 3600

    def test_within_the_cap_is_written(self):
        self.assertEqual(self.set_lease(NOW + 3600, cap=self.CAP), (0, f"{NOW + 3600}\n"))

    def test_past_the_cap_and_later_than_the_lease_in_force_is_refused_with_4(self):
        code, printed = self.set_lease(NOW + 5 * 3600, cap=self.CAP)
        self.assertEqual((code, printed), (lease.OVER_CAP, ""))
        self.assertEqual(lease.OVER_CAP, 4)
        self.assertEqual(descriptor.load(self.desc).expires, NOW + 7200, "the lease untouched")

    def test_past_the_cap_but_shortening_the_lease_in_force_is_written(self):
        self.write(NOW + 9 * 3600)
        self.assertEqual(self.set_lease(NOW + 5 * 3600, cap=self.CAP), (0, f"{NOW + 5 * 3600}\n"))

    def test_a_keep_host_has_no_lease_to_shorten(self):
        self.write(None)
        self.assertEqual(self.set_lease(NOW + 5 * 3600, cap=self.CAP)[0], lease.OVER_CAP)
        self.assertIsNone(descriptor.load(self.desc).expires)

    def test_without_cap_nothing_is_checked(self):
        self.assertEqual(self.set_lease(NOW + 500 * 3600)[0], 0)

    def test_the_departure_still_comes_first(self):
        status.set_lifecycle("depart", "held", "held", path=self.paths["status_path"])
        self.assertEqual(self.set_lease(NOW + 5 * 3600, cap=self.CAP)[0], 3)

    def test_the_command_line(self):
        self.assertEqual(lease.parse_set(["123"]), (123, None))
        self.assertEqual(lease.parse_set(["123", "--cap", "456"]), (123, 456))
        for bad in ([], ["x"], ["123", "--cap"], ["123", "--cap", "y"], ["123", "--cap", "4", "5"],
                    ["123", "--confirmed"]):
            with self.subTest(args=bad):
                self.assertIsNone(lease.parse_set(bad))


class LeaseSetKeepTest(LeaseBase):
    def test_keep_removes_the_lease_and_prints_keep(self):
        code, printed = self.set_lease(None)
        self.assertEqual((code, printed), (0, "keep\n"))
        self.assertFalse(descriptor.load(self.desc).leased)

    def test_the_command_line_takes_keep_alone(self):
        self.assertEqual(lease.parse_set(["keep"]), (None, None))
        for bad in (["keep", "--cap", "4"], ["keep", "keep"], ["Keep"]):
            with self.subTest(args=bad):
                self.assertIsNone(lease.parse_set(bad))

    def test_keep_is_refused_once_the_departure_has_started(self):
        status.set_lifecycle("depart", "held", "held", path=self.paths["status_path"])
        self.assertEqual(self.set_lease(None), (3, ""))
        self.assertTrue(descriptor.load(self.desc).leased)


JOINED = BASE.replace("DEVCLOUD_TAILSCALE=none\n", "DEVCLOUD_TAILSCALE=join\nDEVCLOUD_TS_SECRET=tailscale-client\n")


class NodeKindFollowsTheLeaseTest(LeaseBase):
    """A lease write that changes the kind the tailnet node should be starts
    the rejoin as a transient unit and says so before the lease (§4.1); the
    lease service starts it again while the node stays behind."""

    def setUp(self):
        super().setUp()
        self.kind = self.tmp / "tailnet.json"
        self.started = []
        self.write(None)

    def write(self, expires, adopted=False):
        text = JOINED + (f"DEVCLOUD_EXPIRES={expires}\n" if expires is not None else "")
        self.desc.write_text(text + ("DEVCLOUD_ADOPTED=1\n" if adopted else ""))
        self.desc.chmod(0o600)

    def joined_as(self, ephemeral):
        nodekind.record(ephemeral, ephemeral, nodekind.JOINED, path=self.kind)

    def set_lease(self, value, **kw):
        start = lambda unit, argv, what="": self.started.append((unit, argv))  # noqa: E731
        return super().set_lease(value, kind_path=self.kind, start=start, **kw)

    def test_a_kept_node_given_a_lease_rejoins_as_ephemeral(self):
        self.joined_as(False)
        code, printed = self.set_lease(NOW + 7200)
        self.assertEqual((code, printed), (0, f"rejoin ephemeral\n{NOW + 7200}\n"))
        self.assertEqual(self.started, [("devcloud-rejoin", ["/usr/local/bin/devcloud", "rejoin"])])
        kind = nodekind.recorded(self.kind)
        self.assertEqual((kind["ephemeral"], kind["wanted"], kind["state"]), (False, True, nodekind.REJOINING),
                         "a reader could take the earlier join for this rejoin's end")

    def test_a_leased_node_kept_rejoins_as_non_ephemeral(self):
        self.write(NOW + 7200)
        self.joined_as(True)
        self.assertEqual(self.set_lease(None), (0, "rejoin non-ephemeral\nkeep\n"))
        self.assertEqual(len(self.started), 1)

    def test_a_lease_that_keeps_the_kind_starts_nothing(self):
        self.write(NOW + 7200)
        self.joined_as(True)
        self.assertEqual(self.set_lease(NOW + 9000), (0, f"{NOW + 9000}\n"))
        self.write(None)
        self.joined_as(False)
        self.assertEqual(self.set_lease(None), (0, "keep\n"))
        self.assertEqual(self.started, [])

    def test_an_unrecorded_kind_or_a_failed_rejoin_counts_as_behind(self):
        self.assertEqual(self.set_lease(NOW + 7200)[1], f"rejoin ephemeral\n{NOW + 7200}\n")
        nodekind.record(None, True, nodekind.FAILED, "up failed", path=self.kind)
        self.assertEqual(self.set_lease(NOW + 9000)[1], f"rejoin ephemeral\n{NOW + 9000}\n")

    def test_a_unit_that_did_not_start_still_names_the_rejoin_for_the_lease_service(self):
        self.joined_as(False)

        def fail(unit, argv, what=""):
            raise lease.StepError("systemd-run failed")
        code, printed = super().set_lease(NOW + 7200, kind_path=self.kind, start=fail)
        self.assertEqual((code, printed), (0, f"rejoin ephemeral\n{NOW + 7200}\n"))
        self.assertTrue(descriptor.load(self.desc).leased)

    def test_a_refused_write_starts_nothing(self):
        self.joined_as(False)
        self.assertEqual(self.set_lease(NOW + 5 * 3600, cap=NOW + 3600)[0], lease.OVER_CAP)
        status.set_lifecycle("depart", "held", "held", path=self.paths["status_path"])
        self.assertEqual(self.set_lease(NOW + 600)[0], 3)
        self.assertEqual(self.started, [])

    def test_a_fallback_key_node_has_no_kind_to_follow(self):
        self.desc.write_text(BASE.replace("DEVCLOUD_TAILSCALE=none\n",
                                          "DEVCLOUD_TAILSCALE=join\nDEVCLOUD_TS_AUTHKEY_FILE=/etc/devcloud/ts.key\n"))
        self.assertEqual(self.set_lease(NOW + 7200), (0, f"{NOW + 7200}\n"))

    def tick(self, now, active=False):
        said = []
        code = lease.tick(self.user, state_path=self.tmp / "lease.json", now=lambda: now,
                          active=lambda unit: active,
                          start=lambda unit, argv, what="": self.started.append((unit, argv)),
                          warn=lambda d: None, say=said.append, kind_path=self.kind, **self.paths)
        self.assertEqual(code, 0)
        return said

    def test_the_lease_service_restarts_a_rejoin_while_the_node_is_behind_on_a_kept_host_too(self):
        self.joined_as(True)                   # kept, but the node is still ephemeral
        self.tick(NOW)
        self.assertEqual(self.started, [("devcloud-rejoin", ["/usr/local/bin/devcloud", "rejoin"])])
        self.joined_as(False)
        self.tick(NOW)
        self.assertEqual(len(self.started), 1, "a node that follows its lease was rejoined")

    def test_nor_while_one_is_under_way_or_the_departure_has_started(self):
        self.joined_as(True)
        self.tick(NOW, active=True)
        status.set_lifecycle("depart", "held", "held", path=self.paths["status_path"])
        self.tick(NOW)
        self.assertEqual(self.started, [])

    def test_a_rejoin_that_does_not_start_never_holds_back_the_departure(self):
        self.write(NOW)
        self.joined_as(False)
        started = []

        def start(unit, argv, what=""):
            if unit == "devcloud-rejoin":
                raise lease.StepError("systemd-run failed")
            started.append(unit)
        lease.tick(self.user, state_path=self.tmp / "lease.json", now=lambda: NOW, active=lambda unit: False,
                   start=start, warn=lambda d: None, say=lambda m: None, kind_path=self.kind, **self.paths)
        self.assertEqual(started, ["devcloud-depart"])

    def test_a_leased_host_behind_rejoins_before_its_lease_end_departs(self):
        self.write(NOW)
        self.joined_as(False)
        self.tick(NOW)
        self.assertEqual([unit for unit, _ in self.started], ["devcloud-rejoin", "devcloud-depart"])


class TickTest(LeaseBase):
    def tick(self, now, active=False):
        started, warned = [], []
        code = lease.tick(self.user, state_path=self.tmp / "lease.json", now=lambda: now,
                          active=lambda unit: active, start=lambda unit, argv: started.append((unit, argv)),
                          warn=lambda d: warned.append(d.expires), say=lambda m: None, **self.paths)
        self.assertEqual(code, 0)
        return started, warned

    def test_starts_the_departure_as_a_transient_unit_at_the_lease_end(self):
        self.write(NOW)
        self.assertEqual(self.tick(NOW)[0], [("devcloud-depart", ["/usr/local/bin/devcloud", "depart"])])

    def test_on_an_adopted_machine_it_starts_the_release(self):
        self.write(NOW, adopted=True)
        self.assertEqual(self.tick(NOW + 1)[0], [("devcloud-release", ["/usr/local/bin/devcloud", "release"])])

    def test_a_reboot_past_the_lease_departs(self):
        self.write(NOW - 86400)
        self.assertEqual(len(self.tick(NOW)[0]), 1)

    def test_nothing_while_a_departure_is_under_way_or_done_and_none_without_a_lease(self):
        self.write(NOW)
        self.assertEqual(self.tick(NOW, active=True), ([], []))
        status.set_lifecycle("depart", "departed", "departed", path=self.paths["status_path"])
        self.assertEqual(self.tick(NOW), ([], []))
        status.set_lifecycle("depart", "held", "held (ship failed)", path=self.paths["status_path"])
        self.assertEqual(len(self.tick(NOW)[0]), 1, "a held departure is retried")
        self.write(None)
        self.assertEqual(self.tick(NOW), ([], []))

    def test_warns_once_per_lease_value_from_30_minutes_before_the_end(self):
        end = NOW + 7200
        self.assertEqual(self.tick(end - 1801)[1], [])
        self.assertEqual(self.tick(end - 1800)[1], [end])
        self.assertEqual(self.tick(end - 600)[1], [], "warned twice for one lease")
        self.assertEqual(self.set_lease(end + 3600)[0], 0)
        self.assertEqual(self.tick(end - 300)[1], [], "an extension past the window warns at its own window")
        self.assertEqual(self.tick(end + 1800)[1], [end + 3600], "an extension re-arms the warning")
        self.assertEqual(self.set_lease(NOW + 600)[0], 0)
        self.assertEqual(self.tick(NOW + 1)[1], [NOW + 600], "a lease set inside the window warns at once")

    def test_learns_the_hosts_secrets_before_any_child_runs(self):
        canary = "made-up-store-value-Wn4Ty7Ub2Xc9"
        store = self.user.home / ".config/claude-secrets"
        store.mkdir(parents=True)
        (store / "API_KEY").write_text(canary)
        self.write(NOW)
        seen = []
        with mock.patch.object(proc, "KNOWN", redact.Known()):
            lease.tick(self.user, state_path=self.tmp / "lease.json", now=lambda: NOW, active=lambda unit: False,
                       start=lambda unit, argv: seen.append(proc.KNOWN.scrub(canary)), say=lambda m: None,
                       **self.paths)
        self.assertEqual(len(seen), 1)
        self.assertNotIn(canary, seen[0], "the transient unit's start ran before the host's secrets were known")

    def test_a_lease_write_racing_the_lease_service_is_serialized(self):
        # The lease ends now; an extension holds the lock. The lease service
        # waits for it, then reads the extended lease and departs nothing.
        self.write(NOW)
        result = {}
        with lease.locked(path=self.paths["lock_path"]):
            worker = threading.Thread(target=lambda: result.setdefault("started", self.tick(NOW)[0]))
            worker.start()
            time.sleep(0.3)
            self.assertTrue(worker.is_alive(), "the lease service did not wait for the lock")
            self.desc.write_text(descriptor.set_expires(self.desc.read_text(), NOW + 3600))
        worker.join(5)
        self.assertEqual(result["started"], [])

    def test_admission_is_refused_to_jobs_once_the_departure_started(self):
        with lease.admitted("refresh-secrets", say=lambda m: None, lock_path=self.paths["lock_path"],
                            status_path=self.paths["status_path"]) as ok:
            self.assertTrue(ok)
        status.set_lifecycle("depart", "held", "held (ship failed)", path=self.paths["status_path"])
        said = []
        with lease.admitted("refresh-secrets", say=said.append, lock_path=self.paths["lock_path"],
                            status_path=self.paths["status_path"]) as ok:
            self.assertFalse(ok)
        self.assertIn("departure has started", said[0])

    def test_a_job_holds_the_lock_shared_so_a_departure_waits_for_it(self):
        entered = threading.Event()
        with lease.admitted("pull-config", say=lambda m: None, lock_path=self.paths["lock_path"],
                            status_path=self.paths["status_path"]):
            with lease.admitted("refresh-secrets", say=lambda m: None, lock_path=self.paths["lock_path"],
                                status_path=self.paths["status_path"]):
                pass        # two jobs at once: both shared
            worker = threading.Thread(target=lambda: lease.locked(path=self.paths["lock_path"]).__enter__()
                                      or entered.set())
            worker.daemon = True
            worker.start()
            self.assertFalse(entered.wait(0.3), "an exclusive lock was had while a job ran")
        self.assertTrue(entered.wait(5))


class PausedReleaseTest(DepartureBase):
    """The transient unit was dispatched but has not run when the lease is
    renewed: the release re-reads the lease under the lock and does nothing."""
    adopted = True

    def test_a_lease_renewed_before_the_unit_runs_stops_the_release(self):
        self.write_descriptor(departure_now := 1_792_000_000)
        paths = dict(desc_path=self.tmp / "boot.env", lock_path=self.tmp / "lifecycle.lock",
                     status_path=self.tmp / "status.json", kind_path=self.tmp / "tailnet.json")
        nodekind.record(True, True, nodekind.JOINED, path=paths["kind_path"])     # leased, and ephemeral
        started = []
        lease.tick(self.user, state_path=self.tmp / "lease.json", now=lambda: departure_now + 5,
                   active=lambda unit: False, start=lambda unit, argv: started.append(unit), say=lambda m: None,
                   **paths)
        self.assertEqual(started, ["devcloud-release"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lease.set_lease(departure_now + 7200, out=lambda m: None, **paths), 0)
        self.assertEqual(departure.release(self.host()), departure.NOT_OVER)
        self.assertEqual(self.world.runs(), [], "a step ran")
        self.assertIsNone(status.lifecycle(self.tmp / "status.json"))


class WarningTest(LeaseBase):
    def setUp(self):
        super().setUp()
        clone = self.user.home / ".claude/plugins/marketplaces/doperpowers"
        self.cli = clone / "sminos/skills/sminos/scripts/sminos.py"
        self.cli.parent.mkdir(parents=True)
        self.cli.write_text("")
        (self.user.home / ".claude/plugins/known_marketplaces.json").write_text(
            json.dumps({"doperpowers": {"installLocation": str(clone)}}))
        self.calls = []

    def run_(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs.get("user")))

    def warn(self, creator="@build#4f2a", enrolled=True):
        hub = self.user.home / ".claude/sminos/daemon/hub.json"
        hub.parent.mkdir(parents=True, exist_ok=True)
        hub.write_text("{}\n") if enrolled else hub.unlink(missing_ok=True)
        d = descriptor.parse(BASE + f"DEVCLOUD_EXPIRES={NOW}\n" + (f"DEVCLOUD_CREATOR={creator}\n" if creator else ""))
        said = []
        with mock.patch.object(lease, "ENV_PATH", str(self.tmp / "env")):
            lease.warn_creator(self.user, d, run=self.run_, say=said.append,
                               scan=lambda: [("app", "2 unpushed commits"), ("lib", "uncommitted changes")])
        return said

    def test_says_to_the_creator_as_the_user_naming_the_end_and_the_unpushed_work(self):
        self.warn()
        (argv, user), = self.calls
        text = f"dc-build-7f3a's lease ends at {lease.iso(NOW)}; unpushed: app (2 unpushed commits), lib " \
               "(uncommitted changes)"
        self.assertEqual(lease.iso(NOW), "2026-10-14T17:46Z")
        self.assertEqual(lease.warning_text("dc-build-7f3a", NOW, [("app", "2 unpushed commits"),
                                                                  ("lib", "uncommitted changes")]), text)
        self.assertEqual(argv, ["/usr/bin/python3", str(self.cli), "say", f"@build#4f2a {text}"])
        self.assertEqual(user, self.user)

    def test_without_a_creator_or_unenrolled_the_journal_and_wall(self):
        for kwargs in ({"creator": None}, {"enrolled": False}):
            with self.subTest(**kwargs):
                self.calls.clear()
                said = self.warn(**kwargs)
                self.assertEqual([argv[0] for argv, _ in self.calls], ["wall"])
                self.assertIn("unpushed: app", said[-1])


class UnpushedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-unpushed-"))
        self.root = self.tmp / "Developer/GitHub"
        self.root.mkdir(parents=True)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_GLOBAL="/dev/null")

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True)

    def clone(self, name):
        remote = self.tmp / f"{name}.git"
        self.git("init", "-q", "--bare", "-b", "main", str(remote))
        work = self.root / name
        self.git("clone", "-q", str(remote), str(work))
        (work / "README").write_text("one\n")
        self.git("add", "README", cwd=work)
        self.git("commit", "-qm", "one", cwd=work)
        self.git("push", "-q", "origin", "HEAD:main", cwd=work)
        return work

    def test_names_unpushed_commits_uncommitted_changes_and_worktrees(self):
        clean = self.clone("clean")
        ahead = self.clone("ahead")
        for n in ("two", "three"):
            (ahead / n).write_text(n)
            self.git("add", n, cwd=ahead)
            self.git("commit", "-qm", n, cwd=ahead)
        dirty = self.clone("dirty")
        (dirty / "README").write_text("edited\n")
        tree = clean / ".claude/worktrees/feature"
        self.git("worktree", "add", "-q", "-b", "feature", str(tree), cwd=clean)
        (tree / "new").write_text("x")
        self.git("add", "new", cwd=tree)
        self.git("commit", "-qm", "feature work", cwd=tree)
        (self.root / "not-a-repo").mkdir()
        found = lease.unpushed(None, root=self.root)
        self.assertEqual(found, [("ahead", "2 unpushed commits"), ("clean/.claude/worktrees/feature", "1 unpushed commit"),
                                 ("dirty", "uncommitted changes")])

    def test_nothing_without_the_directory(self):
        self.assertEqual(lease.unpushed(None, root=self.tmp / "absent"), [])


if __name__ == "__main__":
    unittest.main()
