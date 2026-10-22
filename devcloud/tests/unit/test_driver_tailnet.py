"""The tailnet nodes of a host the driver is done with (board #118): removed
through the Tailscale API by node id once the VM's delete has succeeded,
matched exactly by tag:devcloud and the hostname the host joined with. A
removal that fails is named on the deletion's line and the deletion stands."""
import unittest

import _path  # noqa: F401
from driver import images, ops, reaper, tailnet

from driver_fixtures import NOW, READY, TS_CLIENT, DriverBase, ts_device, vm_labels

MIN, HOUR = 60, 3600


class MatchTest(unittest.TestCase):
    def test_only_tagged_nodes_reported_under_exactly_the_hosts_name(self):
        devices = [ts_device("dc-k-0001", "nOwn1CNTRL"),
                   # The host's own older node, named <name>-1 by the tailnet: its hostname is still the host's.
                   ts_device("dc-k-0001-1", "nOwn2CNTRL", hostname="dc-k-0001"),
                   ts_device("dc-k-0001", "nPerson1CNTRL", tags=()),
                   ts_device("dc-k-00012", "nPrefix1CNTRL"),
                   ts_device("dc-k-000", "nShort1CNTRL"),
                   ts_device("DC-K-0001", "nCase1CNTRL"),
                   {"hostname": "dc-k-0001", "tags": ["tag:devcloud"]}]
        self.assertEqual([d["nodeId"] for d in tailnet.nodes_of(devices, "dc-k-0001")], ["nOwn1CNTRL", "nOwn2CNTRL"])


class DownRemovesTheNodeTest(DriverBase):
    def setUp(self):
        super().setUp()
        self.add_server("dc-k-0001", vm_labels(lifetime="keep", confirmed=True), sid="501")
        self.tailnet_api.devices_listed = [ts_device("dc-k-0001", "nKept1CNTRL"),
                                           ts_device("dc-k-0001", "nPerson1CNTRL", tags=()),
                                           ts_device("dc-other-0002", "nOther1CNTRL")]
        self.present_at_removal = []
        delete = self.tailnet_api.delete_node

        def checked(tok, node_id, timeout):
            self.present_at_removal.append("dc-k-0001" in self.servers())
            return delete(tok, node_id, timeout)
        self.tailnet_api.delete_node = checked

    def test_down_force_on_an_unreachable_kept_vm_removes_its_node_after_the_delete(self):
        self.remote.on("true", code=255)
        self.assertEqual(ops.down(self.ctx, "dc-k-0001", force=True), 0)
        self.assertNotIn("dc-k-0001", self.servers())
        self.assertEqual(self.tailnet_api.deleted(), ["nKept1CNTRL"])
        self.assertEqual(self.present_at_removal, [False], "the node went before the VM")
        self.assertEqual(self.tailnet_api.calls[0], ("token", TS_CLIENT), "the hosts' client, newline dropped")
        self.assertIn("ts-oauth", self.secrets.reads)
        self.assertIn("dc-k-0001: deleted without its departure (unreachable); its tailnet node nKept1CNTRL removed "
                      "through the Tailscale API", self.out.getvalue())

    def test_a_node_the_departure_already_removed_leaves_the_line_as_it_was(self):
        self.tailnet_api.devices_listed = [d for d in self.tailnet_api.devices_listed if d["nodeId"] != "nKept1CNTRL"]
        self.remote.on("devcloud depart", code=255, out=READY + "\n", marker=True)
        self.assertEqual(ops.down(self.ctx, "dc-k-0001", force=False), 0)
        self.assertEqual(self.tailnet_api.deleted(), [])
        self.assertIn("dc-k-0001: departed and deleted\n", self.out.getvalue())

    def test_a_node_the_departure_left_is_removed(self):
        self.remote.on("devcloud depart", code=255, out=READY + "\n", marker=True)
        self.assertEqual(ops.down(self.ctx, "dc-k-0001", force=False), 0)
        self.assertEqual(self.tailnet_api.deleted(), ["nKept1CNTRL"])

    def test_a_removal_that_fails_is_named_and_the_deletion_stands(self):
        self.remote.on("true", code=255)
        for fail, needle in (({"devices": "the Tailscale API did not list the devices (HTTP 500)"}, "HTTP 500"),
                             ({"nKept1CNTRL": "the Tailscale API did not remove node nKept1CNTRL (HTTP 403)"},
                              "nKept1CNTRL (the Tailscale API did not remove node nKept1CNTRL (HTTP 403)) not removed")):
            with self.subTest(fail=fail):
                self.tailnet_api.fail = fail
                if "dc-k-0001" not in self.servers():
                    self.add_server("dc-k-0001", vm_labels(lifetime="keep", confirmed=True), sid="502")
                self.assertEqual(ops.down(self.ctx, "dc-k-0001", force=True), 0)
                self.assertNotIn("dc-k-0001", self.servers())
                line = self.out.getvalue().splitlines()[-1]
                self.assertIn(needle, line)
                self.assertIn("remove it in the Tailscale admin console if it is listed", line)

    def test_an_unreadable_client_or_one_without_the_devices_scope_removes_nothing(self):
        self.remote.on("true", code=255)
        del self.secrets.values["ts-oauth"]
        self.assertEqual(ops.down(self.ctx, "dc-k-0001", force=True), 0)
        self.assertIn("its tailnet node was not removed (Secret Manager has no secret ts-oauth)", self.out.getvalue())
        self.add_server("dc-k-0001", vm_labels(lifetime="keep", confirmed=True), sid="502")
        self.secrets.values["ts-oauth"] = TS_CLIENT
        self.tailnet_api.scopes = ["auth_keys"]
        self.assertEqual(ops.down(self.ctx, "dc-k-0001", force=True), 0)
        self.assertIn("devices:core", self.out.getvalue().splitlines()[-1])
        self.assertEqual(self.tailnet_api.deleted(), [])

    def test_a_delete_the_label_fence_refused_removes_no_node(self):
        self.remote.on("true", code=255)
        self.behave(drop_on_get="devcloud")
        with self.assertRaises(Exception):
            ops.down(self.ctx, "dc-k-0001", force=True)
        self.assertEqual(self.tailnet_api.calls, [])


class ReaperRemovesTheNodeTest(DriverBase):
    def setUp(self):
        super().setUp()
        images.record_build(self.ctx, "main", NOW)

    def test_a_deleted_vms_node_is_removed_and_its_id_logged(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW - 20 * MIN), state="stopped", sid="501")
        self.tailnet_api.devices_listed = [ts_device("dc-a-0001", "nLeft1CNTRL")]
        reaper.run(self.ctx)
        self.assertNotIn("dc-a-0001", self.servers())
        self.assertEqual(self.tailnet_api.deleted(), ["nLeft1CNTRL"])
        self.assertRegex(self.paths.reap_log.read_text(),
                         r"deleted dc-a-0001 \(main, id 501\): .*its tailnet node nLeft1CNTRL removed")

    def test_a_builder_leftover_asks_the_tailnet_nothing(self):
        self.add_server("dc-bake-0001", {"devcloud": "builder"}, created=NOW - 3 * HOUR)
        reaper.run(self.ctx)
        self.assertNotIn("dc-bake-0001", self.servers())
        self.assertEqual(self.tailnet_api.calls, [])

    def test_a_bounded_run_with_its_time_spent_asks_the_api_nothing(self):
        vm = {"name": "dc-a-0001"}
        with self.ctx.bounded(1):
            note = tailnet.remove(self.ctx, vm["name"])
        self.assertIn("not looked for", note)
        self.assertEqual(self.tailnet_api.calls, [])
        self.assertEqual(self.secrets.reads, [])


if __name__ == "__main__":
    unittest.main()
