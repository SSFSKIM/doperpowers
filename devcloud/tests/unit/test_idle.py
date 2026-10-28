"""Idle stretches, real transcript mtimes, and notice routing at the CLI boundary."""
import dataclasses
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import descriptor, lease, proc
from test_lease import BASE, NOW

DAY = 86400


class IdleBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="devcloud-idle-")
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.user = proc.User("worker", os.getuid(), os.getgid(), self.root / "home")
        self.state = self.root / "idle.json"
        self.d = descriptor.parse(BASE)
        self.sent = []

    def tick(self, now, active=False, d=None):
        from devcloudlib import idle
        d = d or self.d
        observed = idle.observe(self.user, d, path=self.state, now=lambda: now,
                                activity=lambda user, since: active)
        pending = idle.reserve(d, observed, path=self.state, now=lambda: now)
        if pending is not None:
            idle.send(self.user, d, pending, notify=self.sent.append,
                      scan=lambda: [("app", "2 unpushed commits")])

    def read(self):
        return json.loads(self.state.read_text())


class IdleTest(IdleBase):
    def test_first_run_starts_clock_and_notices_repeat_every_three_idle_days(self):
        self.tick(NOW)
        self.assertEqual(self.read()["active_at"], NOW)
        self.tick(NOW + 3 * DAY - 1)
        self.assertEqual(self.sent, [])
        self.tick(NOW + 3 * DAY)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.read()["noticed_at"], NOW + 3 * DAY)
        self.tick(NOW + 6 * DAY - 1)
        self.assertEqual(len(self.sent), 1)
        self.tick(NOW + 6 * DAY)
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self.sent[-1].startswith(f"devcloud on {self.d.name}:"))
        self.assertIn("6d", self.sent[-1])
        self.assertIn(lease.iso(NOW), self.sent[-1])
        self.assertIn("runs until down", self.sent[-1])
        self.assertIn("app (2 unpushed commits)", self.sent[-1])
        self.assertIn(f"devcloud vm down {self.d.name}", self.sent[-1])
        self.assertNotIn("cost", self.sent[-1])

    def test_activity_rearms_the_notice_for_a_new_stretch(self):
        self.tick(NOW)
        self.tick(NOW + 3 * DAY)
        self.tick(NOW + 4 * DAY, active=True)
        self.assertEqual(self.read()["active_at"], NOW + 4 * DAY)
        self.assertIsNone(self.read()["noticed_at"])
        self.tick(NOW + 7 * DAY)
        self.assertEqual(len(self.sent), 2)

    def test_leased_vm_names_lease_and_cost_including_zero_price(self):
        for price, cost in (("0.25", "18.00 USD"), ("0", "0.00 USD")):
            d = descriptor.parse(BASE + f"DEVCLOUD_CREATED={NOW}\nDEVCLOUD_HOURLY_PRICE={price}\n"
                                 f"DEVCLOUD_CURRENCY=USD\nDEVCLOUD_EXPIRES={NOW + 4 * DAY}\n")
            self.state.unlink(missing_ok=True)
            self.tick(NOW, d=d)
            self.tick(NOW + 3 * DAY, d=d)
            self.assertIn(cost, self.sent[-1])
            self.assertIn(lease.iso(d.expires), self.sent[-1])

    def test_adopted_and_non_vm_hosts_never_record_or_send(self):
        for d in (dataclasses.replace(self.d, adopted=True), dataclasses.replace(self.d, kind="container")):
            self.tick(NOW, d=d)
            self.tick(NOW + 3 * DAY, d=d)
            self.assertFalse(self.state.exists())
        self.assertEqual(self.sent, [])

    def test_probe_failure_does_not_prevent_lease_warning_or_departure(self):
        from devcloudlib import idle
        desc = self.root / "boot.env"
        desc.write_text(BASE + f"DEVCLOUD_EXPIRES={NOW + 600}\n")
        warned, started = [], []
        with mock.patch.object(idle, "observe", side_effect=OSError("probe failed")):
            for now in (NOW, NOW + 600):
                self.assertEqual(lease.tick(self.user, desc_path=desc, lock_path=self.root / "lock",
                                 state_path=self.root / "lease.json", status_path=self.root / "status.json",
                                 now=lambda: now, active=lambda unit: False, warn=lambda d: warned.append(d),
                                 start=lambda *a: started.append(a), say=lambda text: None), 0)
        self.assertEqual(len(warned), 1)
        self.assertEqual(len(started), 1)

    def test_lease_service_updates_idle_for_kept_and_leased_but_not_departing(self):
        from devcloudlib import idle, status
        desc = self.root / "boot.env"
        paths = dict(desc_path=desc, lock_path=self.root / "lock", status_path=self.root / "status.json",
                     state_path=self.root / "lease.json")
        with mock.patch.object(idle, "observe", return_value=None) as check:
            for tail in ("", f"DEVCLOUD_EXPIRES={NOW + 7200}\n"):
                desc.write_text(BASE + tail)
                lease.tick(self.user, now=lambda: NOW, active=lambda unit: False, **paths)
            self.assertEqual(check.call_count, 2)
            status.set_lifecycle("depart", "held", "held", path=paths["status_path"])
            lease.tick(self.user, now=lambda: NOW, active=lambda unit: False, **paths)
            self.assertEqual(check.call_count, 2)


class ActivityTest(IdleBase):
    def setUp(self):
        super().setUp()
        self.load = self.root / "loadavg"
        self.load.write_text("10.00 5.00 0.49 1/200 999\n")
        self.projects = self.user.home / ".claude/projects"
        self.projects.mkdir(parents=True)

    def active(self, since=NOW, terminals=(), states=()):
        from devcloudlib import idle
        def call(argv, **kw):
            if "list-sessions" in argv:
                return 0, "\n".join(f"{i} 1000 worker seat0" for i in range(len(terminals))), ""
            index = int(argv[2])
            tty = terminals[index]
            state = states[index] if states else "active"
            properties = {"TTY": tty, "State": state}
            selected = [arg.removeprefix("--property=") for arg in argv if arg.startswith("--property=")]
            output = "\n".join(properties[key] if "--value" in argv else f"{key}={properties[key]}"
                               for key in selected)
            return 0, output + "\n", ""
        return idle.active(self.user, since, load_path=self.load, call=call)

    def test_only_transcript_writes_since_previous_check_count(self):
        transcript = self.projects / "repo/subagents/agent.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("{}\n")
        os.utime(transcript, (NOW - 1, NOW - 1))
        self.assertFalse(self.active())
        os.utime(transcript, (NOW + 1, NOW + 1))
        self.assertTrue(self.active())
        self.assertFalse(self.active(since=NOW + 2))
        (self.projects / "sessions-index.json").write_text("{}")
        self.assertFalse(self.active(since=NOW + 2))

    def test_interactive_terminal_but_not_noninteractive_ssh_counts(self):
        self.assertFalse(self.active(terminals=("", "")))
        self.assertTrue(self.active(terminals=("", "pts/0")))

    def test_a_logged_out_session_with_remaining_processes_is_not_activity(self):
        self.assertFalse(self.active(terminals=("pts/0",), states=("closing",)))
        self.assertTrue(self.active(terminals=("pts/0", "pts/1"), states=("closing", "online")))

    def test_load_uses_fifteen_minutes_and_includes_half(self):
        self.assertFalse(self.active())
        self.load.write_text("0.00 0.00 0.50 1/200 999\n")
        self.assertTrue(self.active())


class DeliveryTest(IdleBase):
    def deliver(self, results, creator="@abcd1234", project="example"):
        from devcloudlib import notices
        calls, said = [], []
        hub = self.user.home / ".claude/sminos/daemon/hub.json"
        hub.parent.mkdir(parents=True, exist_ok=True)
        hub.write_text("{}")
        d = dataclasses.replace(self.d, creator=creator, creator_project=project)
        def call(argv, **kw):
            calls.append((argv, kw))
            return results.pop(0), "", "refused"
        with mock.patch.object(notices.sminos_host, "cli", return_value=pathlib.Path("/opt/sminos.py")):
            notices.deliver(self.user, d, "idle notice", call=call, say=said.append)
        return calls, said

    def test_live_creator_only(self):
        calls, _ = self.deliver([0])
        self.assertEqual(calls[0][0][-2:], ["say", "@abcd1234 idle notice"])
        self.assertEqual(calls[0][1]["user"], self.user)
        self.assertEqual(len(calls), 1)

    def test_ended_creator_falls_back_to_project_and_empty_project_to_durable_note(self):
        calls, _ = self.deliver([4, 4, 0])
        self.assertEqual(calls[1][0][-4:], ["say", "--project", "example", "idle notice"])
        self.assertEqual(calls[2][0][-4:], ["say", "--in", "example", "idle notice"])

    def test_no_creator_starts_at_project(self):
        calls, _ = self.deliver([0], creator=None)
        self.assertEqual(calls[0][0][-4:], ["say", "--project", "example", "idle notice"])

    def test_failed_delivery_ends_in_journal_and_wall(self):
        calls, said = self.deliver([4, 1, 0])
        self.assertEqual(calls[-1][0], ["wall", "devcloud: idle notice"])
        self.assertIn("idle notice", said[-1])

    def test_lease_warning_uses_the_same_fallback(self):
        from devcloudlib import notices
        d = dataclasses.replace(self.d, expires=NOW)
        with mock.patch.object(notices, "deliver") as send:
            lease.warn_creator(self.user, d, scan=lambda: [("app", "uncommitted changes")])
        self.assertTrue(send.call_args.args[2].startswith(f"devcloud on {d.name}:"))
        self.assertIn("lease ends", send.call_args.args[2])
        self.assertIn("app", send.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
