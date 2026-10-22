"""What the boot and the jobs do around a departure (the driver's Design
§4.1-§4.2, §5, §6.5): the lease and enroll services on a persistent host;
the services step's second guard, which starts no daemon and no periodic
service but the lease's once a departure has started, and nothing once it is
over; the jobs exiting at once; the spot unit; the inbound policy; the
status records a reboot keeps; the credential ledger."""

import contextlib
import json
import os
import pathlib
import pwd
import stat
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import inbound, lease, ledger, services, sminos_host, status, steps
from devcloudlib.proc import User

USER = User(name="dev", uid=1001, gid=1001, home=pathlib.Path("/Users/dev"))


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **_):
        self.calls.append(list(argv))


class ServiceListTest(unittest.TestCase):
    def test_a_persistent_host_adds_the_lease_and_enroll_services_every_five_minutes(self):
        self.assertEqual([s.name for s in services.service_list(USER)],
                         ["pull-config", "refresh-secrets", "refresh-mirrors", "session-mirror"])
        listed = {s.name: s for s in services.service_list(USER, interval=40, persistent=True)}
        self.assertEqual(list(listed)[-2:], ["lease", "enroll"])
        self.assertEqual((listed["lease"].argv, listed["lease"].every, listed["lease"].as_user),
                         (("/usr/local/bin/devcloud", "lease", "tick"), 300, False))
        self.assertEqual((listed["enroll"].argv, listed["enroll"].every), (("/usr/local/bin/devcloud", "enroll"), 300))
        units = services.units(services.service_list(USER, persistent=True), USER)
        self.assertIn("OnUnitActiveSec=300s\n", units["devcloud-lease.timer"])
        self.assertIn("ExecStart=/usr/local/bin/devcloud run-scrubbed -- /usr/local/bin/devcloud lease tick\n",
                      units["devcloud-lease.service"])


class SecondGuardTest(unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.home = tmp / "home"
        (self.home / ".claude/tools").mkdir(parents=True)
        shipper = self.home / ".claude/tools/session-mirror"
        shipper.write_text("#!/bin/sh\n")
        shipper.chmod(0o755)
        self.user = User(name="dev", uid=1001, gid=1001, home=self.home)
        self.units = tmp / "units"
        self.units.mkdir()
        (self.units / services.SPOT_UNIT).write_text("")
        self.pending = tmp / "pending"
        booted = tmp / "booted"
        booted.write_text("")
        self.seen = tmp / "shipper-configured"
        for patch in (mock.patch.object(services, "BOOTED", booted),
                      mock.patch.object(services, "SHIPPER_SEEN", self.seen)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_a_shipper_found_once_is_remembered_after_convergence_removes_its_unit(self):
        self.apply()
        self.assertTrue(self.seen.exists(), "the boot found a shipper and left no evidence of it")
        (self.home / ".claude/tools/session-mirror").unlink()
        calls, _ = self.apply()
        self.assertIn(["systemctl", "disable", "--now", "devcloud-session-mirror.service"], calls)
        self.assertFalse((self.units / "devcloud-session-mirror.service").exists())
        self.assertTrue(self.seen.exists(), "convergence erased the evidence")

    def test_a_host_that_never_had_a_shipper_has_no_flag(self):
        (self.home / ".claude/tools/session-mirror").unlink()
        self.apply()
        self.assertFalse(self.seen.exists())

    def apply(self, lifecycle=None, spot=False):
        recorder = Recorder()
        detail = services.apply_systemd(self.user, False, run=recorder, unit_dir=self.units,
                                        pending_dir=self.pending, persistent=True, lifecycle=lifecycle, spot=spot)
        return recorder.calls, detail

    @staticmethod
    def enabled(calls):
        return {c[-1] for c in calls if c[:2] == ["systemctl", "enable"]}

    @staticmethod
    def started(calls):
        return {c[-1] for c in calls if c[:2] == ["systemctl", "--no-block"]}

    def test_open_admission_runs_everything(self):
        calls, _ = self.apply()
        self.assertEqual(self.enabled(calls), {
            "devcloud-pull-config.timer", "devcloud-refresh-secrets.timer", "devcloud-refresh-mirrors.timer",
            "devcloud-lease.timer", "devcloud-enroll.timer", "devcloud-session-mirror.service"})
        self.assertEqual(self.started(calls), {"devcloud-session-mirror.service"})

    def test_a_departure_under_way_or_held_starts_no_periodic_service_but_the_lease(self):
        for state in ("departing", "held"):
            with self.subTest(state=state):
                calls, detail = self.apply({"op": "depart", "state": state})
                timers = {u for u in self.enabled(calls) if u.endswith(".timer")}
                self.assertEqual(timers, {"devcloud-lease.timer"})
                self.assertIn("departure has started", detail)

    def test_a_departure_over_starts_nothing(self):
        calls, detail = self.apply({"op": "depart", "state": "departed"})
        self.assertEqual(self.enabled(calls), set())
        self.assertEqual(self.started(calls), set())
        self.assertIn("departure has ended", detail)

    def test_the_spot_unit_is_enabled_on_a_spot_vm_only(self):
        calls, _ = self.apply(spot=True)
        # Queued, not awaited: the unit is ordered after the boot unit this runs in.
        self.assertIn(["systemctl", "enable", "--now", "--no-block", services.SPOT_UNIT], calls)
        calls, _ = self.apply(spot=False)
        self.assertIn(["systemctl", "disable", services.SPOT_UNIT], calls)
        self.assertFalse(any(c[:2] == ["systemctl", "enable"] and services.SPOT_UNIT in c for c in calls))


class ServicesStepTest(unittest.TestCase):
    """The step under the lifecycle lock: with a departure started, the
    daemon is neither enrolled nor started."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.status = self.tmp / "status.json"
        self.converged, self.enrolled = [], []
        for patch in (mock.patch.object(status, "PATH", self.status),
                      mock.patch.object(lease, "LOCK", self.tmp / "lifecycle.lock"),
                      mock.patch.object(steps, "_read_env", lambda path: {}),
                      mock.patch.object(steps, "_devcloud_services", lambda r, record: f"systemd ({record})"),
                      mock.patch.object(steps, "_enroll", lambda r, env: self.enrolled.append(1) or
                                        sminos_host.Enrollment("none", "")),
                      mock.patch.object(sminos_host, "converge", lambda *a: self.converged.append(1) or "daemon")):
            patch.start()
            self.addCleanup(patch.stop)
        self.r = mock.Mock(user=USER, env_changed=False)
        self.r.desc.role = "persistent"

    def test_with_a_departure_started_the_daemon_stays_stopped(self):
        for state in ("departing", "held", "departed"):
            with self.subTest(state=state):
                status.set_lifecycle("depart", state, state)
                result = steps.services_step(self.r)
                self.assertEqual((self.converged, self.enrolled), ([], []))
                self.assertIn("the daemon stays stopped", result[1])

    def test_with_no_departure_it_enrolls_and_starts_the_daemon(self):
        self.assertEqual(steps.services_step(self.r)[0], "ok")
        self.assertEqual((self.converged, self.enrolled), ([1], [1]))


class JobsDuringAHoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        for patch in (mock.patch.object(status, "PATH", self.tmp / "status.json"),
                      mock.patch.object(lease, "LOCK", self.tmp / "lifecycle.lock"),
                      mock.patch.object(steps, "_locked", contextlib.nullcontext),
                      mock.patch.object(steps, "_say", lambda message: None),
                      mock.patch.object(steps, "_run", mock.Mock(side_effect=AssertionError("a job ran a step"))),
                      mock.patch.object(sminos_host, "converge", mock.Mock(side_effect=AssertionError("restarted")))):
            patch.start()
            self.addCleanup(patch.stop)

    def test_every_job_exits_at_once_without_restarting_the_daemon(self):
        status.set_lifecycle("depart", "held", "held (ship failed)")
        status.set_enroll_deferred(True)
        for job in (steps.refresh_secrets, steps.reconcile, steps.pull_config, steps.refresh_mirrors, steps.enroll):
            with self.subTest(job=job.__name__):
                self.assertEqual(job(), 0)


class StatusRecordsTest(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "status.json"

    def test_a_boots_reset_keeps_the_lifecycle_and_a_deferred_enrollment(self):
        status.record("seed", "ok", "", path=self.path)
        status.set_lifecycle("depart", "held", "held (ship failed)", steps=[{"name": "ship"}], path=self.path)
        status.set_enroll_deferred(True, path=self.path)
        status.reset(path=self.path)
        data = status.load(self.path)
        self.assertEqual(data["steps"], [])
        self.assertEqual(data["lifecycle"]["state"], "held")
        self.assertEqual(data["enroll"]["state"], "deferred")
        self.assertTrue(status.departure_started(self.path))

    def test_render_shows_the_deferral_and_the_departure(self):
        status.record("services", "deferred", "sminos: undecided", path=self.path)
        status.set_enroll_deferred(True, path=self.path)
        status.set_lifecycle("depart", "held", "held (sessions keep starting)", path=self.path)
        lines = status.render(status.load(self.path)).splitlines()
        self.assertRegex(lines[0], r"^services\s+deferred\s")
        self.assertRegex(lines[1], r"^enroll deferred since \d{4}-")
        self.assertRegex(lines[2], r"^depart\s+held\s+\S+\s+held \(sessions keep starting\)$")

    def test_deferred_counts_as_done(self):
        for name in status.STEPS:
            status.record(name, "deferred" if name == "services" else "ok", "", path=self.path)
        self.assertTrue(status.healthy(status.load(self.path)))

    def test_no_departure_before_one_starts(self):
        self.assertFalse(status.departure_started(self.path))
        with self.assertRaises(ValueError):
            status.set_lifecycle("depart", "gone", "", path=self.path)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.path = self.tmp / "credentials.ledger"
        me = pwd.getpwuid(os.getuid())
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.tmp / "home")

    def test_lists_each_path_once_root_only(self):
        ledger.add(self.tmp / "a", path=self.path)
        ledger.add(str(self.tmp / "a"), path=self.path)
        ledger.add(self.tmp / "b/../c", path=self.path)
        self.assertEqual(ledger.entries(self.path), [str(self.tmp / "a"), str(self.tmp / "c")])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_removes_files_directories_and_links_never_what_a_link_points_to(self):
        outside = self.tmp / "outside"
        outside.write_text("not devcloud's")
        home = self.user.home
        (home / ".config/gcloud").mkdir(parents=True)
        (home / ".config/gcloud/credentials.db").write_text("made-up")
        (home / ".pgpass").symlink_to(outside)
        for target in (home / ".config/gcloud", home / ".pgpass", home / "never-written"):
            ledger.add(target, path=self.path)
        as_user_calls = []
        removed, failures = ledger.remove_all(self.user, lambda user, fn: as_user_calls.append(user) or fn(),
                                              path=self.path)
        self.assertEqual(failures, [])
        self.assertEqual(len(as_user_calls), 3, "a path in the home was removed as root")
        self.assertFalse((home / ".config/gcloud").exists() or (home / ".pgpass").is_symlink())
        self.assertEqual(outside.read_text(), "not devcloud's")
        self.assertFalse(self.path.exists())

    def test_the_last_paths_go_after_every_other_and_stay_while_one_failed(self):
        desc, other = self.tmp / "boot.env", self.user.home / ".pgpass"
        other.parent.mkdir(parents=True)
        for path in (desc, other):
            path.write_text("made-up")
            ledger.add(path, path=self.path)       # the descriptor listed first, as the boot lists it

        def refuse(user, fn):
            raise PermissionError("made-up refusal")
        removed, failures = ledger.remove_all(self.user, refuse, path=self.path, last=[desc])
        self.assertEqual((removed, len(failures)), ([], 1))
        self.assertTrue(desc.exists(), "the descriptor went while another credential was left")
        self.assertTrue(self.path.exists())
        removed, failures = ledger.remove_all(self.user, lambda user, fn: fn(), path=self.path, last=[desc])
        self.assertEqual((removed, failures), ([str(other), str(desc)], []))
        self.assertFalse(desc.exists() or self.path.exists())


class InboundTest(unittest.TestCase):
    def test_the_ruleset_is_one_table_devcloud_owns_and_reloads_idempotently(self):
        text = inbound.ruleset()
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual(lines[:3], ["table inet devcloud", "delete table inet devcloud", "table inet devcloud {"])
        for rule in ('type filter hook input priority filter; policy drop;', 'iif "lo" accept',
                     'iifname "tailscale0" accept', "ct state established,related accept", "ct state invalid drop",
                     "meta l4proto icmp accept", "meta l4proto ipv6-icmp accept", "udp dport 41641 accept",
                     "udp sport 67 udp dport 68 accept", "udp sport 547 udp dport 546 accept"):
            self.assertIn(rule, lines)
        self.assertNotIn("output", text, "outbound is untouched")
        self.assertEqual(sum(1 for line in lines if line.startswith("table")), 2)

    def test_the_unit_loads_it_before_the_network_at_every_boot(self):
        unit = inbound.unit()
        for line in ("DefaultDependencies=no", "Before=network-pre.target", "Wants=network-pre.target",
                     "ExecStart=/usr/sbin/nft -f /etc/devcloud/inbound.nft",
                     "ExecStop=/usr/sbin/nft delete table inet devcloud", "WantedBy=sysinit.target"):
            self.assertIn(line + "\n", unit)

    def test_apply_writes_enables_and_loads_restarting_only_on_a_change(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        first = Recorder()
        inbound.apply(run=first, nft_path=tmp / "inbound.nft", unit_dir=tmp)
        self.assertEqual(first.calls, [["systemctl", "daemon-reload"], ["systemctl", "enable", inbound.UNIT],
                                       ["systemctl", "restart", inbound.UNIT]])
        again = Recorder()
        inbound.apply(run=again, nft_path=tmp / "inbound.nft", unit_dir=tmp)
        self.assertEqual(again.calls, [["systemctl", "enable", inbound.UNIT], ["systemctl", "start", inbound.UNIT]])
        self.assertEqual((tmp / "inbound.nft").read_text(), inbound.ruleset())


class LedgeredWritesTest(unittest.TestCase):
    def test_secrets_list_every_target_before_writing_it_and_keep_a_renamed_one(self):
        from devcloudlib import secrets
        home = pathlib.Path(tempfile.mkdtemp())
        seen = []

        def before(path):
            seen.append((str(path), path.exists()))
        entries = secrets.parse('[[secret]]\nname = "a"\nstore = "OLD"\nfile = "~/.pgpass"\n')
        secrets.materialize(entries, lambda name: b"made-up", home, before_write=before)
        self.assertEqual(seen, [(str(home / ".config/claude-secrets/OLD"), False), (str(home / ".pgpass"), False)])


if __name__ == "__main__":
    unittest.main()
