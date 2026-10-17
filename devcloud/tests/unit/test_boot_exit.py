"""devcloud-boot's exit status: 0 when every step is ok, 1 when a step of 1-11
failed (step 12 then never runs), 3 when only step 12 (projects) failed — the
code the container entrypoint and the boot unit read as "start the services"."""
import contextlib
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import status, steps

HOST_STEPS = ("identity", "seed", "bootstrap_secrets", "tailnet_attach", "configuration", "tailnet_check",
              "secrets_step", "home", "apply", "settings_and_env", "services_step")


class BootExitTest(unittest.TestCase):
    def boot(self, failing=None, projects_state="ok"):
        recorded = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(steps, "_locked", contextlib.nullcontext))
            stack.enter_context(mock.patch.object(steps, "_mark_applied", lambda r: None))
            stack.enter_context(mock.patch.object(status, "reset", lambda: None))
            stack.enter_context(mock.patch.object(steps.services, "mark_booted", lambda ok: None))
            stack.enter_context(mock.patch.object(
                status, "record", lambda name, state, detail: recorded.append((name, state))))
            for name in HOST_STEPS:
                result = ("failed", "made up") if name == failing else "fine"
                stack.enter_context(mock.patch.object(steps, name, lambda r, result=result: result))
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


if __name__ == "__main__":
    unittest.main()
