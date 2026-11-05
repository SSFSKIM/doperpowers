"""devcloud-boot's exit status: 0 when every step is ok, 1 when a step of 1-11
failed (the GPU step and steps 12 and 13 then never run), 3 when only the GPU
step, step 12 (projects) or 13 (maws) failed — the code the container
entrypoint and the boot unit read as "start the services". A GPU step that
installed a newer kernel for the driver's modules reboots the machine at once,
with nothing after it run or started."""
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

    def boot(self, failing=None, projects_state="ok", during=None, maws_state="skipped", gpu_state="skipped",
             reboot=False, reboot_fails=False, during_gpu=None):
        """`during`: a step's label and what happens on the host while it runs.
        `reboot`: the GPU step asks for the reboot; `during_gpu`, what happens
        on the host as the GPU step ends, once its step guard is let go."""
        recorded = []
        self.ran, self.booted = [], []

        def gpu_step(r):
            r.reboot = reboot
            if during_gpu:
                during_gpu()
            return (gpu_state, "made up")

        self.held, self.held_at_run = [], []

        def run(argv, **kwargs):
            self.ran.append(argv)
            self.held_at_run.append(list(self.held))
            if reboot_fails:
                raise steps.StepError("systemctl reboot exited 1")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(steps, "_locked", contextlib.nullcontext))
            stack.enter_context(mock.patch.object(status, "PATH", self.status_path))
            stack.enter_context(mock.patch.object(steps.lease, "LOCK", self.lock_path))
            stack.enter_context(mock.patch.object(steps, "_mark_applied", lambda r: None))
            stack.enter_context(mock.patch.object(status, "reset", lambda: None))
            stack.enter_context(mock.patch.object(steps.services, "mark_booted", self.booted.append))
            stack.enter_context(mock.patch.object(steps, "run", run))
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
            stack.enter_context(mock.patch.object(steps, "gpu_step", gpu_step))
            stack.enter_context(mock.patch.object(steps, "projects", lambda r: (projects_state, "made up")))
            stack.enter_context(mock.patch.object(steps, "maws", lambda r: (maws_state, "made up")))
            with contextlib.redirect_stdout(None):
                code = steps.boot()
        return code, recorded

    def test_every_step_ok_exits_0(self):
        code, recorded = self.boot(maws_state="ok")
        self.assertEqual(code, 0)
        self.assertEqual(recorded[-2:], [("projects", "ok"), ("maws", "ok")])

    def test_only_projects_failed_exits_3_and_maws_still_runs(self):
        # The project that installs mawsd may have come through where another failed.
        code, recorded = self.boot(projects_state="failed")
        self.assertEqual(code, steps.PROJECTS_FAILED)
        self.assertEqual(code, 3)
        self.assertEqual(recorded[-2:], [("projects", "failed"), ("maws", "skipped")])

    def test_maws_failing_exits_3(self):
        # The host is made: the services start all the same.
        code, recorded = self.boot(maws_state="failed")
        self.assertEqual(code, steps.PROJECTS_FAILED)
        self.assertEqual(recorded[-1], ("maws", "failed"))

    def test_a_deferred_maws_exits_0(self):
        self.assertEqual(self.boot(maws_state="deferred")[0], 0)

    def test_skipped_projects_exit_0(self):
        self.assertEqual(self.boot(projects_state="skipped")[0], 0)

    def test_a_host_step_failing_exits_1_and_never_runs_projects(self):
        code, recorded = self.boot(failing="apply")
        self.assertEqual(code, 1)
        for name in ("gpu", "projects", "maws"):
            self.assertNotIn(name, [name for name, _ in recorded])

    def test_the_gpu_step_runs_after_the_services_and_before_the_projects(self):
        code, recorded = self.boot(gpu_state="ok", maws_state="ok")
        self.assertEqual(code, 0)
        self.assertEqual(recorded[-4:], [("services", "ok"), ("gpu", "ok"), ("projects", "ok"), ("maws", "ok")])
        self.assertEqual(self.booted, [False, True])

    def test_the_gpu_step_failing_exits_3_and_the_projects_still_run(self):
        # The host works without its GPU: the services start, and the driver sees the failed step.
        code, recorded = self.boot(gpu_state="failed")
        self.assertEqual(code, steps.PROJECTS_FAILED)
        self.assertEqual(recorded[-3:], [("gpu", "failed"), ("projects", "ok"), ("maws", "skipped")])
        self.assertEqual(self.booted, [False, True])

    def test_the_gpu_steps_reboot_stops_the_boot_there(self):
        code, recorded = self.boot(gpu_state="deferred", reboot=True)
        self.assertEqual(code, 0, "the unit is not failed: the driver's wait sees it reboot and goes on")
        self.assertEqual(recorded[-1], ("gpu", "deferred"))
        self.assertNotIn("projects", [name for name, _ in recorded])
        self.assertEqual(self.ran, [["systemctl", "reboot"]])
        self.assertNotIn(True, self.booted, "the services are not started: the next boot starts them")

    def test_a_reboot_that_cannot_be_asked_for_fails_the_gpu_step_and_the_boot_goes_on(self):
        code, recorded = self.boot(gpu_state="deferred", reboot=True, reboot_fails=True)
        self.assertEqual(code, steps.PROJECTS_FAILED)
        self.assertEqual(recorded[-3:], [("gpu", "failed"), ("projects", "ok"), ("maws", "skipped")])
        self.assertEqual(self.booted, [False, True])


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

    def test_only_an_adopted_machines_steps_wait_on_the_lifecycle_lock(self):
        """A VM's departure must not wait for a long step (apply runs up to 30
        minutes; the reaper's and down's departure are bounded below that)."""
        for adopted, locks in ((False, 0), (True, len(steps.BOOT) + 3)):  # + gpu, projects and maws
            with self.subTest(adopted=adopted):
                taken = []
                host = mock.Mock(desc=mock.Mock(adopted=adopted), reboot=False)
                with mock.patch.object(steps.lease, "locked",
                                       lambda **kw: taken.append(kw) or contextlib.nullcontext()), \
                        mock.patch.object(steps, "Run", lambda kind: host):
                    self.assertEqual(self.boot()[0], 0)
                self.assertEqual(len(taken), locks)
                self.assertTrue(all(kw == {"shared": True} for kw in taken))

    def test_a_release_starting_as_the_gpu_step_ends_is_not_rebooted_under(self):
        """The step asks for its reboot outside its own step guard; a release
        that took the lifecycle lock in that gap must not have the person's
        server rebooted mid-release."""
        host = mock.Mock(desc=mock.Mock(adopted=True), reboot=False)
        with mock.patch.object(steps, "Run", lambda kind: host):
            code, recorded = self.boot(gpu_state="deferred", reboot=True,
                                       during_gpu=lambda: self.released_up_to("restore-keys"))
        self.assertEqual(code, 0)
        self.assertEqual(self.ran, [], "no systemctl reboot once the release has started")
        self.assertNotIn("projects", [name for name, _ in recorded])
        self.assertNotIn(True, self.booted)

    def test_a_vm_whose_departure_started_as_the_gpu_step_ends_is_not_rebooted_either(self):
        # A reboot would cut the departure's ship short; the departure owns the machine now.
        code, recorded = self.boot(gpu_state="deferred", reboot=True, during_gpu=lambda: status.set_lifecycle(
            "depart", "departing", "started", steps=[], path=self.status_path))
        self.assertEqual(code, 0)
        self.assertEqual(self.ran, [])
        self.assertNotIn("projects", [name for name, _ in recorded])

    def test_the_reboot_is_asked_for_under_the_lifecycle_lock(self):
        # A VM's steps take no lock (its departure must not wait on them): only the reboot's request does.
        real = steps.lease.locked

        @contextlib.contextmanager
        def locked(**kw):
            with real(**kw):
                self.held.append(kw)
                yield
                self.held.pop()
        host = mock.Mock(desc=mock.Mock(adopted=False), reboot=False)
        with mock.patch.object(steps.lease, "locked", locked), mock.patch.object(steps, "Run", lambda kind: host):
            self.boot(gpu_state="deferred", reboot=True)
            self.assertEqual(self.ran, [["systemctl", "reboot"]])
        self.assertEqual(self.held_at_run, [[{"shared": True}]])

    def test_a_departing_vm_still_boots_its_services_gated(self):
        """A VM's departure starts again from step 0 after a reboot (§4.2):
        its boot runs, and the services step keeps admission closed."""
        status.set_lifecycle("depart", "departing", "started", steps=[], path=self.status_path)
        code, recorded = self.boot()
        self.assertEqual(code, 0)
        self.assertEqual(recorded[-1], ("maws", "skipped"))


if __name__ == "__main__":
    unittest.main()
