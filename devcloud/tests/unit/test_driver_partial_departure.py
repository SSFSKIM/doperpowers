"""A partial host can log out before SSH delivers its ready line.

Run the real departure, then cut its output at that boundary: an ordinary
`down` must not guess that the logout happened, and an explicit force must
still be able to delete the VM. External commands use the departure fixture.
"""
import shutil

import _path  # noqa: F401
from devcloudlib import departure, status
from driver import ops
from driver.errors import DriverError
from driver.ssh import Result
from driver_fixtures import DriverBase, vm_labels
from test_departure import DepartureBase


class PartialDepartureTest(DriverBase):
    def setUp(self):
        super().setUp()
        self.add_server("dc-partial-0001", vm_labels(), sid="501")
        self.partial = DepartureBase()
        self.partial.setUp()
        self.addCleanup(shutil.rmtree, self.partial.tmp)
        self.addCleanup(self.partial.doCleanups)
        # apply failed before services or enrollment; configuration already
        # supplied the shipper, which still has to ship any transcripts.
        shutil.rmtree(self.partial.units)
        self.partial.units.mkdir()
        (self.partial.home / ".claude/sminos/daemon/hub.json").unlink()
        (self.partial.home / ".config/systemd/user/sminos-daemon.service").unlink()
        status.record("apply", "failed", "deliberate failure", path=self.partial.tmp / "status.json")
        self.remote.on("devcloud depart", fn=self.depart_and_lose_confirmation)

    def depart_and_lose_confirmation(self, target, command):
        code = departure.depart(self.partial.host(), force=True, no_poweroff=True)
        self.assertEqual(code, departure.DONE)
        output = "\n".join(e[1] for e in self.partial.world.events if e[0] == "say") + "\n"
        self.assertIn(departure.READY, output)
        self.assertIn(["tailscale", "logout"], self.partial.world.runs())
        self.assertEqual(self.partial.lifecycle()["state"], "departed")
        # The host flushed READY, but the transport lost it at logout.
        return Result(255, output.split(departure.READY, 1)[0], "", False)

    def test_missing_units_are_skipped_but_shipping_and_leave_still_run(self):
        self.depart_and_lose_confirmation(None, None)
        self.assertNotIn(["systemctl", "stop", departure.SHIPPER_UNIT], self.partial.world.runs())
        self.assertTrue(any(argv[-2:] == ["ship", "--once"] for argv in self.partial.world.runs()))
        leave = next(step for step in self.partial.lifecycle()["steps"] if step["name"] == "leave")
        self.assertEqual((leave["state"], leave["detail"]), ("ok", "not enrolled"))

    def test_lost_confirmation_keeps_vm_and_explains_the_recovery(self):
        with self.assertRaises(DriverError) as caught:
            ops.down(self.ctx, "dc-partial-0001", force=False)
        message = str(caught.exception)
        self.assertEqual(caught.exception.code, 1)
        for text in ("logout confirmation", "leave (ok)", "unknown", "--force", "unshipped", "desk",
                     "sminos machines", "devcloud vm ls"):
            self.assertIn(text, message)
        self.assertNotIn("\n", message)
        self.assertIn("dc-partial-0001", self.servers())

    def test_force_deletes_even_when_the_confirmation_was_lost(self):
        self.assertEqual(ops.down(self.ctx, "dc-partial-0001", force=True), 0)
        self.assertNotIn("dc-partial-0001", self.servers())
        self.assertIn("without departure confirmation", self.out.getvalue())
        self.assertNotIn("departed and deleted", self.out.getvalue())

    def test_followup_unreachable_names_what_force_skips_and_cleanup_checks(self):
        self.remote.on("true", code=255)
        with self.assertRaises(DriverError) as caught:
            ops.down(self.ctx, "dc-partial-0001", force=False)
        message = str(caught.exception)
        for text in ("unreachable", "--force", "unshipped", "desk", "sminos machines", "devcloud vm ls"):
            self.assertIn(text, message)
        self.assertNotIn("\n", message)
        self.assertIn("dc-partial-0001", self.servers())
        self.assertEqual(ops.down(self.ctx, "dc-partial-0001", force=True), 0)
        self.assertNotIn("dc-partial-0001", self.servers())
