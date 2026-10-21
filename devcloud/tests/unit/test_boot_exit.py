"""devcloud-boot's exit status: 0 when every step is ok, 1 when a step of 1-11
failed (step 12 then never runs), 3 when only step 12 (projects) failed — the
code the container entrypoint and the boot unit read as "start the services"."""
import contextlib
import pathlib
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import status, steps

HOST_STEPS = ("identity", "seed", "bootstrap_secrets", "tailnet_attach", "configuration", "tailnet_check",
              "secrets_step", "home", "apply", "settings_and_env", "services_step")


class BootExitTest(unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.status_path = tmp / "status.json"
        self.lock_path = tmp / "lifecycle.lock"

    def boot(self, failing=None, projects_state="ok", during=None):
        """`during`: a step's label and what happens on the host while it runs."""
        recorded = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(steps, "_locked", contextlib.nullcontext))
            stack.enter_context(mock.patch.object(status, "PATH", self.status_path))
            stack.enter_context(mock.patch.object(steps.lease, "LOCK", self.lock_path))
            stack.enter_context(mock.patch.object(steps, "_mark_applied", lambda r: None))
            stack.enter_context(mock.patch.object(status, "reset", lambda: None))
            stack.enter_context(mock.patch.object(steps.services, "mark_booted", lambda ok: None))
            # The host running the tests may itself run systemd (GitHub's runners do).
            stack.enter_context(mock.patch.object(steps.services, "systemd_is_init", lambda: False))
            stack.enter_context(mock.patch.object(
                status, "record", lambda name, state, detail: recorded.append((name, state))))
            for (label, _), name in zip(steps.BOOT, HOST_STEPS):
                result = ("failed", "made up") if name == failing else "fine"
                side = during[1] if during and during[0] == label else (lambda: None)
                stack.enter_context(mock.patch.object(
                    steps, name, lambda r, result=result, side=side: side() or result))
            # BOOT holds the step functions themselves, bound at import.
            stack.enter_context(mock.patch.object(steps, "BOOT", tuple(
                (label, getattr(steps, fn)) for (label, _), fn in zip(steps.BOOT, HOST_STEPS))))
            stack.enter_context(mock.patch.object(steps, "projects", lambda r: (projects_state, "made up")))
            with contextlib.redirect_stdout(None):
                code = steps.boot()
        return code, recorded

    def test_every_step_ok_exits_0(self):
        code, recorded = self.boot()
        self.assertEqual(code, 0)
        self.assertEqual(recorded[-1], ("projects", "ok"))

    def test_only_projects_failed_exits_3(self):
        code, recorded = self.boot(projects_state="failed")
        self.assertEqual(code, steps.PROJECTS_FAILED)
        self.assertEqual(code, 3)
        self.assertEqual(recorded[-1], ("projects", "failed"))

    def test_skipped_projects_exit_0(self):
        self.assertEqual(self.boot(projects_state="skipped")[0], 0)

    def test_a_host_step_failing_exits_1_and_never_runs_projects(self):
        code, recorded = self.boot(failing="apply")
        self.assertEqual(code, 1)
        self.assertNotIn("projects", [name for name, _ in recorded])


class ReleaseStartedTest(BootExitTest):
    """A boot after a release started on an adopted machine (§6.5) configures
    nothing: its steps would undo what the release did — the driver keys back
    over the restored authorized_keys (home), the firewall and the tailnet
    back (tailnet-attach) — and the release, resumed, skips what it recorded
    as done."""

    def released_up_to(self, last):
        done = ["close-admission", "end-sessions", "stop-shipper", "ship", "leave", "firewall", "restore-keys"]
        steps_ = [{"name": n, "state": "ok", "at": "t", "detail": ""} for n in done[:done.index(last) + 1]]
        status.set_lifecycle("release", "departing", "remove-units failed: run it again to resume", steps=steps_,
                             path=self.status_path)

    def test_a_reboot_after_restore_keys_replays_no_step(self):
        self.released_up_to("restore-keys")
        before = status.load(self.status_path)
        code, recorded = self.boot()
        self.assertEqual(code, 0)
        self.assertEqual(recorded, [], "no step ran: not home's keys, not tailnet-attach's firewall or join")
        self.assertEqual(status.load(self.status_path), before, "the release's record and the last boot's stay")

    def test_a_held_release_too(self):
        self.released_up_to("firewall")
        status.set_lifecycle("release", "held", "held (ship failed)", path=self.status_path)
        self.assertEqual(self.boot()[1], [])

    def test_a_release_starting_during_the_boot_stops_it_at_the_next_step(self):
        code, recorded = self.boot(during=("apply", lambda: self.released_up_to("restore-keys")))
        self.assertEqual(code, 0)
        self.assertEqual([name for name, _ in recorded][-1], "apply")
        self.assertNotIn("settings-and-env", [name for name, _ in recorded])
        self.assertNotIn("projects", [name for name, _ in recorded])

    def test_a_departing_vm_still_boots_its_services_gated(self):
        """A VM's departure starts again from step 0 after a reboot (§4.2):
        its boot runs, and the services step keeps admission closed."""
        status.set_lifecycle("depart", "departing", "started", steps=[], path=self.status_path)
        code, recorded = self.boot()
        self.assertEqual(code, 0)
        self.assertEqual(recorded[-1], ("projects", "ok"))


if __name__ == "__main__":
    unittest.main()
