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
        pending = idle.check(d, observed, path=self.state, now=lambda: now)
        if pending is not None:
            idle.send(self.user, d, pending, notify=self.sent.append,
                      scan=lambda: [("app", "2 unpushed commits")])
            idle.delivered(pending, path=self.state, now=lambda: now)

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
        identity = self.user.home / ".claude/sminos/daemon/identity.json"
        identity.parent.mkdir(parents=True, exist_ok=True)
        identity.write_text("{}")
        d = dataclasses.replace(self.d, creator=creator, creator_project=project)
        def call(argv, **kw):
            calls.append((argv, kw))
            return results.pop(0), "", "refused"
        with mock.patch.object(notices.sminos_host, "cli", return_value=pathlib.Path("/opt/sminos.py")):
            notices.deliver(self.user, d, "idle notice", call=call, say=said.append)
        return calls, said

    def test_live_creator_only(self):
        calls, said = self.deliver([0])
        self.assertEqual(calls[0][0][-5:], ["say", "--notice", "devcloud", "--exit-held", "@abcd1234 idle notice"])
        self.assertEqual(calls[0][1]["user"], self.user)
        self.assertEqual(len(calls), 1, "exit 0 ends the delivery")
        self.assertEqual(said, ["devcloud notice: sent: idle notice"])

    def test_ended_creator_falls_back_to_project_and_empty_project_to_durable_note(self):
        calls, _ = self.deliver([4, 4, 0])
        self.assertEqual(calls[1][0][-6:], ["say", "--notice", "devcloud", "--project", "example", "idle notice"])
        self.assertEqual(calls[2][0][-6:], ["say", "--notice", "devcloud", "--in", "example", "idle notice"])
        self.assertEqual(len(calls), 3)

    def test_a_held_owner_goes_on_as_any_other_failure_of_the_first_step(self):
        calls, said = self.deliver([3, 4, 0])
        self.assertEqual([c[0][5:-1] for c in calls], [["--exit-held"], ["--project", "example"],
                                                       ["--in", "example"]])
        self.assertEqual(said[0], "devcloud notice: recorded for the thread that owns this host, which is not woken "
                                  "with it now; going on to its project")
        calls, _ = self.deliver([3, 0])
        self.assertEqual(len(calls), 2, "a live member heard it: no note")

    def test_a_step_its_sminos_refuses_as_usage_runs_again_without_the_flags(self):
        calls, said = self.deliver([2, 0])
        self.assertEqual(calls[1][0][-2:], ["say", "@abcd1234 idle notice"], "today's call")
        self.assertEqual(len(calls), 2, "the second exit decides")
        self.assertIn("devcloud notice: this host's sminos does not know the notice flags; sent without them", said)
        calls, _ = self.deliver([2, 4, 2, 4, 2, 0])
        self.assertEqual([c[0][3:] for c in calls], [
            ["--notice", "devcloud", "--exit-held", "@abcd1234 idle notice"], ["@abcd1234 idle notice"],
            ["--notice", "devcloud", "--project", "example", "idle notice"], ["--project", "example", "idle notice"],
            ["--notice", "devcloud", "--in", "example", "idle notice"], ["--in", "example", "idle notice"]])
        calls, said = self.deliver([2, 2, 2, 1, 0])
        self.assertEqual(calls[-1][0], ["wall", "devcloud: idle notice"], "a second refusal is a failure")

    def test_a_general_failure_is_a_step_that_failed_and_never_a_reason_to_send_unmarked(self):
        """sminos refuses `say --notice` with exit 1 under a writer its notice grammar does not mark (a host
        whose own name is outside it): read here as a step that failed, so the delivery goes on marked and
        ends in the journal and wall, and nothing is sent without the flags, which would be a person's words."""
        calls, said = self.deliver([1, 1, 0])
        self.assertEqual([c[0][3:5] for c in calls[:2]], [["--notice", "devcloud"], ["--notice", "devcloud"]])
        self.assertEqual(calls[2][0], ["wall", "devcloud: idle notice"])
        self.assertEqual(len(calls), 3, "no step run again without the flags")
        self.assertNotIn("devcloud notice: this host's sminos does not know the notice flags; sent without them",
                         said)
        self.assertEqual(said[:2], ["devcloud notice: delivery failed (exit 1): refused"] * 2)

    def test_no_creator_starts_at_project(self):
        calls, _ = self.deliver([0], creator=None)
        self.assertEqual(calls[0][0][-6:], ["say", "--notice", "devcloud", "--project", "example", "idle notice"])

    def test_no_project_ends_in_journal_and_wall_after_the_first_step(self):
        calls, said = self.deliver([3, 0], project=None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0], ["wall", "devcloud: idle notice"])
        self.assertEqual(said[-1], "devcloud notice: idle notice")

    def test_a_host_that_is_not_enrolled_runs_no_say(self):
        from devcloudlib import notices
        calls = []
        d = dataclasses.replace(self.d, creator="@abcd1234", creator_project="example")
        with mock.patch.object(notices.sminos_host, "cli", return_value=pathlib.Path("/opt/sminos.py")):
            notices.deliver(self.user, d, "idle notice", call=lambda argv, **kw: calls.append(argv) or (0, "", ""),
                            say=lambda text: None)
        self.assertEqual(calls, [["wall", "devcloud: idle notice"]])

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


class ChannelsTest(IdleBase):
    """EN.G2's M3 (docs/doperpowers/plans/2026-11-23-sminos-environments-en-g2.md, Interfaces §5): after the
    chain, whichever way it ended, one call records the notice in every channel whose pool holds this host."""

    POOLS = ["say", "--notice", "devcloud", "--pools", "short notice"]

    def deliver(self, results, creator="@abcd1234", project="example", short="short notice", cli=True,
                cut_over=True):
        """(calls, said) of one delivery; `results` (exit, stdout, stderr) a call, in order."""
        from devcloudlib import notices
        calls, said = [], []
        identity = self.user.home / ".claude/sminos/daemon/identity.json"
        identity.parent.mkdir(parents=True, exist_ok=True)
        identity.write_text("{}") if cut_over else identity.unlink(missing_ok=True)
        d = dataclasses.replace(self.d, creator=creator, creator_project=project)

        def call(argv, **kw):
            calls.append((argv, kw))
            got = results.pop(0)
            if isinstance(got, Exception):
                raise got
            return got
        with mock.patch.object(notices.sminos_host, "cli", return_value=pathlib.Path("/opt/sminos.py") if cli
                               else None):
            notices.deliver(self.user, d, "idle notice", call=call, say=said.append, short=short)
        return calls, said

    def test_the_fourth_call_carries_the_short_text_as_the_chains_steps_are_called(self):
        calls, said = self.deliver([(0, "", ""), (0, "recorded beta:1 in desk\nrecorded beta:2 in ops\n", "")])
        (first, first_kw), (channels, kw) = calls
        self.assertEqual(first[-1], "@abcd1234 idle notice", "the chain's step keeps the full text")
        self.assertEqual(channels, ["/usr/bin/python3", "/opt/sminos.py", *self.POOLS])
        self.assertEqual({k: kw[k] for k in ("user", "env", "log", "cwd", "timeout")},
                         {k: first_kw[k] for k in ("user", "env", "log", "cwd", "timeout")}, "as the chain calls")
        self.assertEqual(said, ["devcloud notice: sent: idle notice", "devcloud notice: channels: recorded beta:1 in desk",
                                "devcloud notice: channels: recorded beta:2 in ops"])

    def test_it_follows_each_way_the_chain_ends(self):
        ok = (0, "recorded beta:1 in desk\n", "")
        for why, results, chain in (
                ("sent at the first step", [(0, "", "")], ["--exit-held"]),
                ("gone on", [(3, "", ""), (0, "", "")], ["--exit-held", "--project"]),
                ("fallen to the journal", [(4, "", ""), (4, "", ""), (1, "", "x"), (0, "", "")],
                 ["--exit-held", "--project", "--in", "wall"])):
            with self.subTest(why):
                calls, said = self.deliver(results + [ok])
                self.assertEqual([argv[0] if argv[0] == "wall" else argv[5] for argv, _ in calls[:-1]], chain)
                self.assertEqual(calls[-1][0][2:], self.POOLS, "last, after the chain")
                self.assertEqual(said[-1], "devcloud notice: channels: recorded beta:1 in desk")

    def test_no_creator_and_no_project_still_records_in_the_channels(self):
        calls, _ = self.deliver([(0, "", ""), (0, "", "")], creator=None, project=None)
        self.assertEqual([argv[0] if argv[0] == "wall" else argv[2:] for argv, _ in calls], ["wall", self.POOLS])

    def test_exit_2_says_its_line_and_calls_nothing_again(self):
        calls, said = self.deliver([(0, "", ""), (2, "", "unrecognized arguments: --pools")])
        self.assertEqual(len(calls), 2)
        self.assertEqual(said[-1], "devcloud notice: this host's sminos does not know --pools; no channel's timeline "
                                   "was written")

    def test_exit_0_with_a_waiting_line_calls_nothing_again(self):
        line = ("it waits in desk for the upstream's head of beta (this machine's enrolment is new): it is recorded, "
                "and delivered, once the uplink has seen it")
        calls, said = self.deliver([(0, "", ""), (0, line + "\n", "")])
        self.assertEqual(len(calls), 2)
        self.assertEqual(said[-1], "devcloud notice: channels: " + line)

    def test_another_exit_or_a_call_that_raises_is_said_and_changes_nothing_else(self):
        calls, said = self.deliver([(0, "", ""), (1, "recorded beta:1 in desk\n", "cannot say into ops")])
        self.assertEqual(len(calls), 2)
        self.assertEqual(said[-1], "devcloud notice: the channels' record failed (exit 1): cannot say into ops")
        calls, said = self.deliver([(0, "", ""), OSError("no log")])
        self.assertEqual(said[-1], "devcloud notice: the channels' record failed: no log")

    def test_no_sminos_or_not_cut_over_makes_no_call(self):
        for kwargs in ({"cli": False}, {"cut_over": False}):
            with self.subTest(**kwargs):
                calls, _ = self.deliver([(0, "", "")], **kwargs)
                self.assertEqual([argv for argv, _ in calls], [["wall", "devcloud: idle notice"]])

    def test_the_short_text_never_falls_back_to_the_full_one(self):
        calls, _ = self.deliver([(0, "", "")], short=None)
        self.assertEqual(len(calls), 1, "no short text given: no call")

    def test_set_to_the_full_text_the_fourth_call_carries_it(self):
        from devcloudlib import notices
        self.assertEqual(notices.CHANNEL_TEXT, "short", "O6's default, while the owner has not answered")
        with mock.patch.object(notices, "CHANNEL_TEXT", "full"):
            calls, _ = self.deliver([(0, "", ""), (0, "", "")])
            self.assertEqual(calls[-1][0][2:], [*self.POOLS[:-1], "idle notice"])
            calls, _ = self.deliver([(0, "", ""), (0, "", "")], short=None)
            self.assertEqual(calls[-1][0][2:], [*self.POOLS[:-1], "idle notice"])

    def test_the_short_idle_text_names_the_machine_its_idleness_and_lifetime_and_no_repository(self):
        d = descriptor.parse(BASE + f"DEVCLOUD_CREATED={NOW}\nDEVCLOUD_HOURLY_PRICE=0.25\nDEVCLOUD_CURRENCY=USD\n"
                             f"DEVCLOUD_EXPIRES={NOW + 5 * DAY}\n")
        from devcloudlib import idle
        state, current, found = {"active_at": NOW}, NOW + 3 * DAY + 4 * 3600, [("app", "2 unpushed commits")]
        full = idle.text(d, state, current, found)
        short = idle.text(d, state, current, found, short=True)
        self.assertEqual(short, f"devcloud on {d.name}: idle 3d 4h; last active {lease.iso(NOW)}; lease ends at "
                                f"{lease.iso(NOW + 5 * DAY)}; estimated cost so far 19.00 USD")
        self.assertEqual(full, short + f"; unpushed: app (2 unpushed commits); end it with devcloud vm down {d.name}")
        self.assertNotIn("app", short)

    def test_each_notice_hands_delivery_its_short_text(self):
        from devcloudlib import idle, notices
        with mock.patch.object(notices, "deliver") as send:
            idle.send(self.user, self.d, ({"active_at": NOW}, NOW + 3 * DAY), scan=lambda: [("app", "x")])
            lease.warn_creator(self.user, dataclasses.replace(self.d, expires=NOW), scan=lambda: [("app", "x")])
        (idle_call, warning_call) = send.call_args_list
        self.assertEqual(idle_call.kwargs["short"],
                         idle.text(self.d, {"active_at": NOW}, NOW + 3 * DAY, [], short=True))
        self.assertEqual(warning_call.kwargs["short"], lease.warning_text(self.d.name, NOW, [], short=True))


if __name__ == "__main__":
    unittest.main()
