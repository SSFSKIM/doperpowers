"""The reaper (§4.3): its decision table as a pure function, then its runs
against the stand-in provider and stand-in hosts — lease fencing, excess,
leftovers, images, the bounded run of `up` and `ls`, the log, `--install`."""
import json
import plistlib
import time
import unittest
from unittest import mock

import _path  # noqa: F401
from driver import hostctl, images, reaper

from driver_fixtures import NOW, READY, DriverBase, vm_labels

MIN, HOUR = 60, 3600


def vm(expires, state="running", lifetime="ttl", **extra):
    return {"id": "1", "name": "dc-a-0001", "labels": vm_labels(expires=expires, lifetime=lifetime, **extra),
            "state": state, "created": NOW - 10 * HOUR}


class DecisionTest(unittest.TestCase):
    """Each row of §4.3's table: (the VM, the host's answer, now) → the action."""

    def decide(self, v, answer=None, host_expires=None):
        return reaper.decide(v, NOW, answer, host_expires)

    def test_not_expired_or_within_the_grace_is_left(self):
        self.assertEqual(self.decide(vm(NOW + HOUR)).kind, "keep")
        self.assertEqual(self.decide(vm(NOW - 14 * MIN)).kind, "keep")
        self.assertEqual(self.decide(vm(None, lifetime="keep")).kind, "keep")
        self.assertEqual(self.decide(vm(None)).kind, "keep", "a ttl VM with no lease label is not guessed at")

    def test_expired_past_the_grace_is_contacted_when_running(self):
        self.assertEqual(self.decide(vm(NOW - 16 * MIN)).kind, "contact")

    def test_departed_or_dropped_after_the_ready_line_is_deleted(self):
        for answer in (hostctl.DONE, hostctl.AFTER_READY):
            action = self.decide(vm(NOW - 16 * MIN), answer)
            self.assertEqual(action.kind, "delete", answer)
            self.assertFalse(action.loss)

    def test_dropped_before_the_ready_line_is_skipped_and_kept(self):
        self.assertEqual(self.decide(vm(NOW - 16 * MIN), hostctl.UNKNOWN).kind, "keep")
        self.assertEqual(self.decide(vm(NOW - 16 * MIN), hostctl.FAILED_RUN).kind, "keep")

    def test_lease_not_over_repairs_the_label_from_the_host(self):
        action = self.decide(vm(NOW - 16 * MIN), hostctl.NOT_OVER, host_expires=NOW + 5 * HOUR)
        self.assertEqual(action.kind, "label")
        self.assertEqual(action.labels["devcloud-expires"], str(NOW + 5 * HOUR))

    def test_held_is_labeled_and_kept_until_24h_then_deleted_naming_the_loss(self):
        action = self.decide(vm(NOW - HOUR), hostctl.HELD)
        self.assertEqual((action.kind, action.labels.get("devcloud-held")), ("label", "1"))
        held = vm(NOW - 23 * HOUR, **{"devcloud-held": "1"})
        self.assertEqual(self.decide(held).kind, "contact", "a held departure is retried at each run")
        self.assertEqual(self.decide(held, hostctl.HELD).kind, "keep")
        late = vm(NOW - 24 * HOUR - MIN, **{"devcloud-held": "1"})
        action = self.decide(late)
        self.assertEqual(action.kind, "delete")
        self.assertTrue(action.loss)
        self.assertIn("unshipped", action.reason)

    def test_unreachable(self):
        # Not running: deleted once 15 min past, without trying SSH.
        self.assertEqual(self.decide(vm(NOW - 16 * MIN, state="off")).kind, "delete")
        # Running: kept from 15 min to 6 h past the label, deleted beyond.
        self.assertEqual(self.decide(vm(NOW - 16 * MIN), hostctl.UNREACHABLE).kind, "keep")
        self.assertEqual(self.decide(vm(NOW - 5 * HOUR), hostctl.UNREACHABLE).kind, "keep")
        self.assertEqual(self.decide(vm(NOW - 6 * HOUR - MIN), hostctl.UNREACHABLE).kind, "delete")
        # Held waits 24 h either way.
        self.assertEqual(self.decide(vm(NOW - 7 * HOUR, state="off", **{"devcloud-held": "1"})).kind, "keep")
        self.assertEqual(self.decide(vm(NOW - 7 * HOUR, **{"devcloud-held": "1"}), hostctl.UNREACHABLE).kind,
                         "keep")

    def test_excess_newest_first_down_to_the_cap(self):
        fleet = [{"id": str(i), "name": f"v{i}", "labels": vm_labels(expires=NOW + HOUR), "created": NOW - 100 + i}
                 for i in range(5)]
        fleet.append({"id": "9", "name": "conf", "labels": vm_labels(expires=NOW + HOUR, confirmed=True),
                      "created": NOW})
        self.assertEqual([v["name"] for v in reaper.excess(fleet, 3)], ["v4", "v3"])
        self.assertEqual(reaper.excess(fleet[:3], 3), [])

    def test_leftovers_and_images(self):
        servers = [{"id": "1", "name": "b-old", "labels": {"devcloud": "builder"}, "created": NOW - 3 * HOUR},
                   {"id": "2", "name": "b-new", "labels": {"devcloud": "builder"}, "created": NOW - HOUR},
                   {"id": "3", "name": "t-old", "labels": {"devcloud": "test"}, "created": NOW - 3 * HOUR},
                   {"id": "4", "name": "vm", "labels": vm_labels(expires=NOW), "created": NOW - 9 * HOUR}]
        self.assertEqual([v["name"] for v in reaper.leftovers(servers, NOW)], ["b-old", "t-old"])
        images = [{"id": f"i{i}", "name": f"img{i}", "labels": {"devcloud": "image"}, "created": NOW - i * HOUR}
                  for i in range(4)]
        images.append({"id": "t", "name": "test-img", "labels": {"devcloud": "test"}, "created": NOW - 9 * HOUR})
        self.assertEqual([i["id"] for i in reaper.surplus_images(images, NOW)], ["i2", "i3", "t"])


class RunTest(DriverBase):
    def setUp(self):
        super().setUp()
        # Its daily image build is tried and tested in test_driver_images; here it has just been tried.
        images.record_build(self.ctx, "main", NOW)

    def run_reaper(self, **kw):
        return reaper.run(self.ctx, **kw)

    def depart_answers(self, code=0, marker=False, target=None):
        self.remote.on("devcloud depart", code=code, marker=marker, target=target)

    def test_a_departed_host_is_deleted_and_logged(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN), sid="501")
        self.depart_answers(code=255, marker=True)
        self.run_reaper()
        self.assertNotIn("dc-a-0001", self.servers())
        depart = [c for c in self.remote.calls if "devcloud depart" in c["command"]][0]
        self.assertEqual((depart["target"], depart["alias"]), ("dc-a-0001", "devcloud-main-501"))
        self.assertNotIn("--force", depart["command"], "the reaper's departure keeps the host's lease check")
        self.assertIn("--no-poweroff", depart["command"])
        log = self.paths.reap_log.read_text()
        self.assertRegex(log, r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ deleted dc-a-0001 \(main, id 501\)")
        self.assertEqual(self.remote.forgotten, ["devcloud-main-501"])

    def test_a_drop_before_the_ready_line_keeps_the_vm(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN))
        self.depart_answers(code=255, marker=False)
        self.run_reaper()
        self.assertIn("dc-a-0001", self.servers())

    def test_fencing_a_crash_between_the_host_write_and_the_label_write(self):
        # The host's lease was extended; the label still holds the old value.
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN))
        self.depart_answers(code=3)
        self.remote.on("DEVCLOUD_EXPIRES", out=f"{NOW + 5 * HOUR}\n")
        self.run_reaper()
        server = self.servers()["dc-a-0001"]
        self.assertEqual(server["labels"]["devcloud-expires"], str(NOW + 5 * HOUR), "label repaired")
        self.assertNotIn("delete", self.ops())

    def test_fencing_an_extension_between_the_list_and_the_delete(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN))

        def extended_meanwhile(target, command):
            # A `vm lease` on another Mac lands while this reaper departs the host.
            state = self.state()
            state["servers"][0]["labels"]["devcloud-expires"] = str(NOW + 9 * HOUR)
            self.state_file.write_text(json.dumps(state))
            from driver.ssh import Result
            return Result(0, READY + "\n", "", True)

        self.remote.on("devcloud depart", fn=extended_meanwhile)
        self.run_reaper()
        self.assertIn("dc-a-0001", self.servers())
        self.assertNotIn("delete", self.ops())

    def test_fencing_reverse_order_renewals_and_an_outage(self):
        # Two renewals landed in reverse order: the label trails the host. Unreachable and running within 6 h of
        # the stale label: kept; then reachable: the label is repaired, not the VM deleted.
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 2 * HOUR))
        self.remote.on("true", code=255, times=1)
        self.run_reaper()
        self.assertIn("dc-a-0001", self.servers())
        self.depart_answers(code=3)
        self.remote.on("DEVCLOUD_EXPIRES", out=f"{NOW + 3 * HOUR}\n")
        self.run_reaper()
        self.assertEqual(self.servers()["dc-a-0001"]["labels"]["devcloud-expires"], str(NOW + 3 * HOUR))
        self.assertNotIn("delete", self.ops())

    def test_unreachable_and_not_running_is_deleted_without_ssh(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.run_reaper()
        self.assertNotIn("dc-a-0001", self.servers())
        self.assertEqual(self.remote.calls, [])

    def test_held_is_labeled_then_deleted_after_24h_naming_the_loss(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN, **{"devcloud-enroll": "code"}))
        self.depart_answers(code=4)
        self.run_reaper()
        self.assertEqual(self.servers()["dc-a-0001"]["labels"].get("devcloud-held"), "1")
        self.clock.now += 24 * HOUR
        self.run_reaper()
        self.assertNotIn("dc-a-0001", self.servers())
        log = self.paths.reap_log.read_text()
        self.assertIn("unshipped", log)
        self.assertIn("one-time code", log, "a VM enrolled by a code that did not depart stays at the desk")

    def test_a_driver_killed_after_create_leaves_4_and_the_next_run_brings_3(self):
        for i in range(4):
            self.add_server(f"dc-x-000{i}", vm_labels(expires=NOW + HOUR), created=NOW - 100 + i)
        self.add_server("dc-conf-0001", vm_labels(expires=NOW + HOUR, confirmed=True), created=NOW)
        self.add_server("dc-keep-0001", vm_labels(lifetime="keep", confirmed=True), created=NOW)
        self.run_reaper()
        self.assertEqual(sorted(self.servers()), ["dc-conf-0001", "dc-keep-0001", "dc-x-0000", "dc-x-0001",
                                                  "dc-x-0002"])
        depart = [c["command"] for c in self.remote.calls if "devcloud depart" in c["command"]]
        self.assertEqual(len(depart), 1)
        self.assertIn("--force", depart[0])

    def test_leftovers_images_and_unlabeled_servers(self):
        self.add_server("dc-bake-0001", {"devcloud": "builder"}, created=NOW - 3 * HOUR)
        self.add_server("dc-ptest-0001", {"devcloud": "test", "devcloud-test": "r1"}, created=NOW - 3 * HOUR)
        self.add_server("dc-bake-0002", {"devcloud": "builder"}, created=NOW - HOUR)
        state = self.state()
        state["images"] = [{"id": f"i{i}", "name": f"img{i}", "labels": {"devcloud": "image"},
                            "created": NOW - i * HOUR} for i in range(3)]
        state["behavior"]["list_unlabeled"] = True
        self.state_file.write_text(json.dumps(state))
        self.run_reaper()
        self.assertEqual(sorted(self.servers()), ["dc-bake-0002"])
        self.assertEqual(sorted(i["id"] for i in self.state()["images"]), ["i0", "i1"])
        deleted_ids = [c["input"]["id"] for c in self.state()["calls"] if c["op"] == "delete"]
        self.assertNotIn("9999", deleted_ids, "a server without the devcloud label is never touched")

    def test_the_label_recheck_refuses_a_server_that_lost_its_label(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.behave(drop_on_get="devcloud")
        self.run_reaper()
        self.assertIn("dc-a-0001", self.servers())

    def test_the_bounded_run_of_up_and_ls_never_departs(self):
        self.add_server("dc-run-0001", vm_labels(expires=NOW - 20 * MIN))
        self.add_server("dc-off-0001", vm_labels(expires=NOW - 20 * MIN), state="off")
        for i in range(4):
            self.add_server(f"dc-x-000{i}", vm_labels(expires=NOW + HOUR), created=NOW - 100 + i)
        self.run_reaper(bounded=True)
        self.assertEqual(self.remote.calls, [])
        self.assertNotIn("dc-off-0001", self.servers())
        self.assertIn("dc-run-0001", self.servers())
        self.assertEqual(sum(n.startswith("dc-x-") for n in self.servers()), 4)

    def test_the_bounded_run_stops_at_its_deadline_with_a_hanging_provider(self):
        self.add_server("dc-off-0001", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.add_server("dc-off-0002", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.behave(hang=["get"])
        started = time.monotonic()
        with mock.patch.object(reaper, "BOUND", 1):
            self.assertEqual(self.run_reaper(bounded=True), 1)
        self.assertLess(time.monotonic() - started, 10, "the bound did not cut the hanging call")
        self.assertEqual(self.ops(), ["list", "get"], "no call started once the budget was spent")
        self.assertIn("1 s bound", self.err.getvalue())
        self.assertTrue(all(t is not None and t <= 1 for t in self.secrets.timeouts), self.secrets.timeouts)
        self.assertEqual(sorted(self.servers()), ["dc-off-0001", "dc-off-0002"])

    def test_the_bounded_runs_lines_go_to_stderr_and_the_scheduled_runs_to_stdout(self):
        self.add_server("dc-off-0001", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.run_reaper(bounded=True)
        self.assertEqual(self.out.getvalue(), "")
        self.assertIn("reap: deleted dc-off-0001", self.err.getvalue())
        self.add_server("dc-off-0002", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.run_reaper()
        self.assertIn("reap: deleted dc-off-0002", self.out.getvalue())

    def test_each_scheduled_run_ends_with_one_dated_line_and_a_bounded_run_with_none(self):
        # The agent's output is how anyone sees it run every 10 minutes, deletions or not.
        self.run_reaper(bounded=True)
        self.assertNotIn("reap: run", self.err.getvalue() + self.out.getvalue())
        self.assertEqual(self.run_reaper(), 0)
        self.assertRegex(self.out.getvalue().splitlines()[-1],
                         r"^reap: run \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ done: accounts main$")

    def test_an_image_relabeled_after_the_list_is_not_deleted(self):
        state = self.state()
        state["images"] = [{"id": f"i{i}", "name": f"img{i}", "labels": {"devcloud": "image"},
                            "created": NOW - i * HOUR} for i in range(3)]
        self.state_file.write_text(json.dumps(state))
        client = self.ctx.client(self.ctx.profile.account("main"))
        listed = client.images

        def stale_list():
            # The reaper's list is taken; then the image is relabeled before its delete.
            answer = listed()
            client.images = listed
            state = self.state()
            state["images"][2]["labels"]["devcloud-recipe"] = "cccccccccccc"
            self.state_file.write_text(json.dumps(state))
            return answer

        client.images = stale_list
        self.run_reaper()
        self.assertEqual(sorted(i["id"] for i in self.state()["images"]), ["i0", "i1", "i2"])
        self.assertNotIn("image-delete", self.ops())
        self.assertIn("labels changed", self.err.getvalue())

    def test_a_label_repair_reads_the_target_first(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN))
        self.depart_answers(code=3)
        self.remote.on("DEVCLOUD_EXPIRES", out=f"{NOW + 5 * HOUR}\n")
        self.behave(drop_on_get="devcloud")
        self.run_reaper()
        self.assertNotIn("set-labels", self.ops())
        self.assertEqual(self.servers()["dc-a-0001"]["labels"]["devcloud-expires"], str(NOW - 20 * MIN))

    def test_an_unusable_account_is_never_run(self):
        (self.profile_dir / "providers" / ".pass" / "main").unlink()
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN), state="off")
        self.run_reaper()
        self.assertIn("dc-a-0001", self.servers())
        self.assertEqual(self.state()["calls"], [])


class InstallTest(DriverBase):
    def test_writes_a_launchd_agent_every_10_minutes(self):
        ran = []
        agents = self.tmp / "LaunchAgents"
        reaper.install(self.ctx, agents_dir=agents, bin_path="/opt/devcloud/bin/devcloud",
                       launchctl=lambda argv: ran.append(argv) or 0, uid=501)
        plist = plistlib.loads((agents / f"{reaper.LABEL}.plist").read_bytes())
        self.assertIn("devcloud-reap", reaper.LABEL)
        self.assertEqual(plist["Label"], reaper.LABEL)
        self.assertEqual(plist["ProgramArguments"], ["/opt/devcloud/bin/devcloud", "vm", "reap"])
        self.assertEqual(plist["StartInterval"], 600)
        self.assertIn("PATH", plist["EnvironmentVariables"])
        self.assertEqual(ran[-1][:2], ["launchctl", "bootstrap"])


if __name__ == "__main__":
    unittest.main()
