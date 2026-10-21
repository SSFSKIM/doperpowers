"""`ls`, `ssh`, `lease` and `down` (M3's decisions) against the stand-in
provider and stand-in hosts."""
import json

import _path  # noqa: F401
from driver import ops
from driver.errors import DriverError
from driver.ssh import Result

from driver_fixtures import NOW, READY, DriverBase, status_json, vm_labels

HOUR = 3600


class OpsBase(DriverBase):
    def fails(self, fn):
        with self.assertRaises(DriverError) as caught:
            fn()
        return caught.exception.code, str(caught.exception)


class LsTest(OpsBase):
    def test_rows_and_the_throwaway_count(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW + 2 * HOUR, **{"devcloud-creator": "abcd1234"}))
        self.add_server("dc-b-0002", vm_labels(expires=NOW - 600, **{"devcloud-held": "1"}))
        self.add_server("dc-k-0003", vm_labels(lifetime="keep", confirmed=True))
        self.add_server("dc-bake-0004", {"devcloud": "builder"}, created=NOW - 60)
        self.tailnet_nodes += [{"name": "dc-a-0001", "online": True, "tags": ["tag:devcloud"]},
                               {"name": "dc-gone-0009", "online": False, "tags": ["tag:devcloud"]},
                               {"name": "macbook", "online": True, "tags": []}]
        self.assertEqual(ops.ls(self.ctx), 0)
        out = self.out.getvalue()
        self.assertTrue(out.startswith("throwaway 2/3"), out)
        self.assertRegex(out, r"dc-a-0001\s+fake/main\s+ttl\s+in 2h\s+running\s+0.1178 EUR/h\s+abcd1234")
        self.assertRegex(out, r"dc-b-0002 .*ended 10m ago\s+held")
        self.assertRegex(out, r"dc-k-0003\s+fake/main\s+keep\s+-")
        self.assertRegex(out, r"dc-gone-0009\s+tailnet only")
        self.assertNotIn("macbook", out)
        self.assertNotIn("dc-bake-0004", out)

    def test_json(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW + HOUR))
        self.assertEqual(ops.ls(self.ctx, as_json=True), 0)
        data = json.loads(self.out.getvalue())
        self.assertEqual(data["throwaway"], {"alive": 1, "cap": 3})
        self.assertEqual(data["vms"][0]["name"], "dc-a-0001")
        self.assertEqual(data["vms"][0]["expires"], NOW + HOUR)

    def test_json_stays_json_when_the_reaper_deleted_something(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW + HOUR))
        self.add_server("dc-off-0002", vm_labels(expires=NOW - HOUR), state="off")
        self.assertEqual(ops.ls(self.ctx, as_json=True), 0)
        data = json.loads(self.out.getvalue())
        self.assertEqual([vm["name"] for vm in data["vms"]], ["dc-a-0001"])
        self.assertIn("reap: deleted dc-off-0002", self.err.getvalue())

    def test_a_failing_list_is_named_and_the_rest_shown(self):
        self.behave(fail={"list": 1})
        self.assertEqual(ops.ls(self.ctx), 0)
        self.assertIn("account main", self.err.getvalue())

    def test_a_failing_edit_of_the_working_file_leaves_ls_working(self):
        (self.profile_dir / "providers" / "fake").write_text("#!/bin/sh\nexit 1\n")
        self.add_server("dc-a-0001", vm_labels(expires=NOW + HOUR))
        ops.ls(self.ctx)
        self.assertIn("dc-a-0001", self.out.getvalue())


class SshTest(OpsBase):
    def setUp(self):
        super().setUp()
        self.add_server("dc-a-0001", vm_labels(expires=NOW + HOUR), sid="501")

    def test_the_user_over_the_tailnet_and_the_command_as_given(self):
        ops.ssh(self.ctx, "dc-a-0001", root=False, command=["cd ~/x && devenv validate"])
        call = self.remote.calls[-1]
        self.assertEqual((call["kind"], call["target"], call["alias"], call["user"]),
                         ("interactive", "dc-a-0001", "devcloud-main-501", "dev"))
        self.assertEqual(call["command"], "cd ~/x && devenv validate")
        ops.ssh(self.ctx, "dc-a-0001", root=False, command=["sminos", "spawn", "acc", "reply ok and stop"])
        self.assertEqual(self.remote.calls[-1]["command"], "sminos spawn acc 'reply ok and stop'")

    def test_refuses_a_departing_or_held_host_unless_root(self):
        for state in ("departing", "held", "departed"):
            with self.subTest(state=state):
                self.remote.rules = []
                self.remote.on("status.json", out=status_json(lifecycle=state))
                code, message = self.fails(lambda: ops.ssh(self.ctx, "dc-a-0001", root=False, command=["true"]))
                self.assertEqual(code, 1)
                self.assertIn(state, message)
                self.assertIn("--root", message)
                self.assertEqual(ops.ssh(self.ctx, "dc-a-0001", root=True, command=["true"]), 0)
                self.assertEqual(self.remote.calls[-1]["user"], "root")

    def test_an_unknown_name(self):
        self.assertEqual(self.fails(lambda: ops.ssh(self.ctx, "dc-nope-0000", root=False, command=[]))[0], 1)


class LeaseTest(OpsBase):
    def setUp(self):
        super().setUp()
        self.add_server("dc-a-0001", vm_labels(expires=NOW + HOUR), created=NOW - 10 * HOUR)

    def test_writes_the_host_then_the_label_with_the_value_the_host_printed(self):
        printed = NOW + 2 * HOUR + 7
        self.remote.on("devcloud lease set", out=f"{printed}\n")
        self.assertEqual(ops.lease(self.ctx, "dc-a-0001", "2h", confirmed=False), 0)
        self.assertIn(f"devcloud lease set {NOW + 2 * HOUR}", self.remote.commands()[-1])
        self.assertEqual(self.servers()["dc-a-0001"]["labels"]["devcloud-expires"], str(printed))
        self.assertEqual(self.servers()["dc-a-0001"]["labels"]["devcloud-by"], "testmac", "the full set kept")

    def test_a_host_that_refuses_or_does_not_answer_leaves_the_label(self):
        for code in (3, 255):
            with self.subTest(code=code):
                self.remote.rules = []
                self.remote.on("devcloud lease set", code=code)
                self.assertEqual(self.fails(lambda: ops.lease(self.ctx, "dc-a-0001", "2h", confirmed=False))[0], 1)
                self.assertEqual(self.servers()["dc-a-0001"]["labels"]["devcloud-expires"], str(NOW + HOUR))
        self.assertNotIn("set-labels", self.ops())

    def test_longer_is_capped_from_the_creation_time_shorter_never(self):
        # Created 10 h ago: 63 h more reaches 73 h of life, over 72 h.
        code, message = self.fails(lambda: ops.lease(self.ctx, "dc-a-0001", "63h", confirmed=False))
        self.assertEqual(code, 4)
        self.assertIn("--confirmed", message)
        self.remote.on("devcloud lease set", out=f"{NOW + 63 * HOUR}\n")
        self.assertEqual(ops.lease(self.ctx, "dc-a-0001", "63h", confirmed=True), 0)
        self.remote.rules = []
        self.remote.on("devcloud lease set", out=f"{NOW + 1800}\n")
        state = self.state()
        state["servers"][0]["labels"]["devcloud-expires"] = str(NOW + 100 * HOUR)
        self.state_file.write_text(json.dumps(state))
        self.assertEqual(ops.lease(self.ctx, "dc-a-0001", "30m", confirmed=False), 0)

    def host_lease(self, unix):
        """The host's own lease: `lease set` writes it, DEVCLOUD_EXPIRES reads it."""
        held = {"lease": unix}

        def lease_set(target, command):
            held["lease"] = int(command.split()[-1])
            return Result(0, f"{held['lease']}\n", "", False)

        self.remote.on("devcloud lease set", fn=lease_set)
        self.remote.on("DEVCLOUD_EXPIRES", fn=lambda target, command: Result(0, f"{held['lease']}\n", "", False))
        return held

    def test_past_the_cap_unconfirmed_is_measured_against_the_hosts_lease_not_the_label(self):
        # Confirmed earlier to 100 h of life; then `lease 1h` set the host but its label write failed, so the
        # label still says 100 h while the host says 1 h.
        state = self.state()
        state["servers"][0]["labels"]["devcloud-expires"] = str(NOW - 10 * HOUR + 100 * HOUR)
        self.state_file.write_text(json.dumps(state))
        held = self.host_lease(NOW - 10 * HOUR + 100 * HOUR)
        self.behave(fail={"set-labels": 1})
        self.assertEqual(self.fails(lambda: ops.lease(self.ctx, "dc-a-0001", "1h", confirmed=False))[0], 1)
        self.assertEqual(held["lease"], NOW + HOUR)
        self.assertEqual(self.servers()["dc-a-0001"]["labels"]["devcloud-expires"], str(NOW + 90 * HOUR))
        self.behave(fail={})
        # 70 h more is 80 h of life: within the stale label, past the host's lease, so it needs --confirmed.
        code, message = self.fails(lambda: ops.lease(self.ctx, "dc-a-0001", "70h", confirmed=False))
        self.assertEqual(code, 4)
        self.assertEqual(held["lease"], NOW + HOUR, "the host untouched")
        # Shortening the host's own lease past the cap needs no confirmation.
        held["lease"] = NOW + 85 * HOUR
        self.assertEqual(ops.lease(self.ctx, "dc-a-0001", "70h", confirmed=False), 0)
        self.assertEqual(held["lease"], NOW + 70 * HOUR)

    def test_the_label_write_goes_through_the_gate(self):
        self.remote.on("devcloud lease set", out=f"{NOW + 2 * HOUR}\n")
        self.behave(drop_on_get="devcloud")
        self.assertEqual(self.fails(lambda: ops.lease(self.ctx, "dc-a-0001", "2h", confirmed=False))[0], 1)
        self.assertNotIn("set-labels", self.ops())

    def test_a_bad_duration_is_usage(self):
        self.assertEqual(self.fails(lambda: ops.lease(self.ctx, "dc-a-0001", "soon", confirmed=False))[0], 2)


class DownTest(OpsBase):
    def setUp(self):
        super().setUp()
        self.add_server("dc-a-0001", vm_labels(expires=NOW + HOUR), sid="501")

    def test_unpushed_work_is_exit_5_naming_the_repository(self):
        self.remote.on("devcloud unpushed", code=5, out="repo\t1 unpushed commit\n")
        code, message = self.fails(lambda: ops.down(self.ctx, "dc-a-0001", force=False))
        self.assertEqual(code, 5)
        self.assertEqual(message, "dc-a-0001 has unpushed work in repo: push it, or pass --force")
        self.assertIn("dc-a-0001", self.servers())
        self.assertEqual(self.remote.commands("devcloud depart"), [])

    def test_force_skips_the_guard_and_the_hold(self):
        self.remote.on("devcloud unpushed", code=5, out="repo\tdirty\n")
        self.remote.on("devcloud depart", code=0)
        self.assertEqual(ops.down(self.ctx, "dc-a-0001", force=True), 0)
        self.assertEqual(self.remote.commands("devcloud unpushed"), [])
        self.assertIn("--force --no-hold", self.remote.commands("devcloud depart")[0])
        self.assertNotIn("dc-a-0001", self.servers())

    def test_a_drop_after_the_ready_line_deletes(self):
        self.remote.on("devcloud depart", code=255, out=READY + "\n", marker=True)
        self.assertEqual(ops.down(self.ctx, "dc-a-0001", force=False), 0)
        depart = self.remote.commands("devcloud depart")[0]
        self.assertIn("--no-poweroff", depart)
        self.assertIn("--force", depart)
        self.assertNotIn("--no-hold", depart)
        self.assertNotIn("dc-a-0001", self.servers())
        self.assertEqual(self.remote.forgotten, ["devcloud-main-501"])

    def test_a_drop_before_it_keeps_the_vm_and_exits_1(self):
        self.remote.on("devcloud depart", code=255, marker=False)
        code, message = self.fails(lambda: ops.down(self.ctx, "dc-a-0001", force=False))
        self.assertEqual(code, 1)
        self.assertIn("unknown", message)
        self.assertIn("dc-a-0001", self.servers())

    def test_a_held_departure_exits_1_naming_the_hold_and_force(self):
        self.remote.on("devcloud depart", code=4)
        code, message = self.fails(lambda: ops.down(self.ctx, "dc-a-0001", force=False))
        self.assertEqual(code, 1)
        self.assertIn("held", message)
        self.assertIn("--force", message)
        self.assertIn("dc-a-0001", self.servers())

    def test_unreachable_asks_for_force_which_deletes_straight_away(self):
        self.remote.on("true", code=255)
        code, message = self.fails(lambda: ops.down(self.ctx, "dc-a-0001", force=False))
        self.assertEqual(code, 1)
        self.assertIn("--force", message)
        self.assertIn("dc-a-0001", self.servers())
        self.assertEqual(ops.down(self.ctx, "dc-a-0001", force=True), 0)
        self.assertNotIn("dc-a-0001", self.servers())
        self.assertEqual(self.remote.commands("devcloud depart"), [])

    def test_the_delete_rechecks_the_label(self):
        self.remote.on("devcloud depart", code=0)
        self.behave(drop_on_get="devcloud")
        code, _ = self.fails(lambda: ops.down(self.ctx, "dc-a-0001", force=False))
        self.assertEqual(code, 1)
        self.assertIn("dc-a-0001", self.servers())
