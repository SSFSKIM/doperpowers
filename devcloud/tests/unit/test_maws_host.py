"""Boot step 13, `maws` (the O14 spec's M3 and Interfaces §F): a host whose
descriptor names the MAWS provisioning code pipes it to `mawsd endpoint
provision` as the user, and an endpoint not yet listed is left to the
devcloud-enroll timer, which runs the same command again. The mawsd stand-in
(fixtures/mawsd.py) runs as a real subprocess; every value is made up."""

import contextlib
import hashlib
import json
import os
import pathlib
import pwd
import shutil
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import descriptor, lease, maws_host, proc, status, steps
from devcloudlib.proc import StepError, User

FAKE = pathlib.Path(__file__).resolve().parents[1] / "fixtures/mawsd.py"
CODE = "smns-provision-v2.made-up-code-Wq4Zr8Tn2Lp6"
DELEGATION = "0123456789abcdef0123456789abcdef"
BASE = ("DEVCLOUD_NAME=dc-build-7f3a\nDEVCLOUD_KIND=vm\nDEVCLOUD_ROLE=persistent\nDEVCLOUD_TAILSCALE=none\n"
        "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=example-project\n"
        "DEVCLOUD_CONFIG_REPO=https://github.com/example/config.git\nDEVCLOUD_CONFIG_TOKEN_SECRET=config-token\n")
PROVISION = ["endpoint", "provision", "--name", "dc-build-7f3a", "--wait", "120"]


class MawsBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-maws-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        me = pwd.getpwuid(os.getuid())
        self.home = self.tmp / "home"
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.home)
        self.wrapper = self.home / ".config/MAWS/mawsd/bin/mawsd"
        self.install_mawsd()
        self.state = self.home / ".local/state/devcloud-test"
        self.state.mkdir(parents=True)
        self.fetched = []
        patch = mock.patch.object(proc, "LOG_DIR", self.tmp / "log")
        patch.start()
        self.addCleanup(patch.stop)

    def install_mawsd(self):
        self.wrapper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FAKE, self.wrapper)
        self.wrapper.chmod(0o755)

    def desc(self, secret=True):
        return descriptor.parse(BASE + (f"DEVCLOUD_MAWS_SECRET=desk-provisioning-v2\n"
                                        f"DEVCLOUD_MAWS_DELEGATION_ID={DELEGATION}\n" if secret else ""))

    def exits(self, *lines):
        (self.state / "provision.exit").write_text("".join(f"{line}\n" for line in lines))

    def fetch(self, name):
        self.fetched.append(name)
        return CODE

    def provision(self, secret=True, env=None):
        return maws_host.provision(self.user, self.desc(secret), self.user.env(env or {}), self.fetch)

    def calls(self):
        path = self.state / "mawsd-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class ProvisionTest(MawsBase):
    def test_0_is_done_with_the_code_on_stdin_alone(self):
        result = self.provision()
        self.assertEqual(result.state, "ok")
        [call] = self.calls()
        self.assertEqual(call["argv"], PROVISION)
        self.assertEqual(call["stdin_sha256"], hashlib.sha256(CODE.encode()).hexdigest())
        self.assertEqual(self.fetched, ["desk-provisioning-v2"])
        self.assertIn("org-listed", result.detail)

    def test_4_defers_to_the_timer(self):
        self.exits("4")
        result = self.provision()
        self.assertEqual(result.state, "deferred")
        self.assertIn("devcloud-enroll", result.detail)

    def test_an_endpoint_that_does_not_answer_yet_defers_too(self):
        # A unit `devenv up` has just started may not answer its socket yet.
        self.exits("3 mawsd is not running (no socket)")
        self.assertEqual(self.provision().state, "deferred")

    def test_1_is_a_refusal_with_its_reason(self):
        self.exits("1 name-prefix: dc-build-7f3a is outside the delegation's prefix dc2-")
        with self.assertRaisesRegex(StepError, "refused.*name-prefix"):
            self.provision()

    def test_2_is_a_mawsd_without_the_endpoint(self):
        self.exits("2 no endpoint module")
        with self.assertRaisesRegex(StepError, "exited 2"):
            self.provision()

    def test_no_wrapper_skips_and_fetches_nothing(self):
        self.wrapper.unlink()
        result = self.provision()
        self.assertEqual(result.state, "skipped")
        self.assertIn("no mawsd here", result.detail)
        self.assertEqual(self.fetched, [], "the code was fetched for a host with no mawsd")

    def test_no_code_named_skips(self):
        result = self.provision(secret=False)
        self.assertEqual(result.state, "skipped")
        self.assertEqual((self.fetched, self.calls()), ([], []))

    def test_the_wrapper_is_the_default_profiles_under_xdg_config_home(self):
        config = self.tmp / "config"
        self.wrapper = config / "MAWS/mawsd/bin/mawsd"
        self.install_mawsd()
        self.assertEqual(maws_host.wrapper(self.user, {"XDG_CONFIG_HOME": str(config)}), self.wrapper)
        self.assertEqual(maws_host.wrapper(self.user, {}), self.home / ".config/MAWS/mawsd/bin/mawsd")

    def test_the_code_never_reaches_a_file_or_an_argument_list(self):
        self.provision()
        self.assertFalse(any(CODE in arg for call in self.calls() for arg in call["argv"]))
        for path in self.tmp.rglob("*"):
            if path.is_file():
                self.assertNotIn(CODE.encode(), path.read_bytes(), f"the code is in {path}")


class StepTest(MawsBase):
    """The step in the runs: its status entry, its deferral kept in the status
    and finished by `devcloud enroll`, and its rerun by `devcloud reconcile`."""

    def setUp(self):
        super().setUp()
        self.status = self.tmp / "status.json"
        for patch in (mock.patch.object(status, "PATH", self.status),
                      mock.patch.object(lease, "LOCK", self.tmp / "lifecycle.lock"),
                      mock.patch.object(steps, "_locked", contextlib.nullcontext),
                      mock.patch.object(steps, "_read_env", lambda path: {}),
                      mock.patch.object(steps, "_fetch_text", lambda r, name: self.fetch(name)),
                      mock.patch.object(steps.Run, "load", lambda r: setattr(r, "desc", self.desc()) or setattr(
                          r, "user", self.user)),
                      mock.patch.object(steps, "_say", lambda message: None)):
            patch.start()
            self.addCleanup(patch.stop)

    def step(self):
        """Step 13 as a run records it: its state and detail."""
        r = steps.Run("boot")
        steps._run((("maws", steps.maws),), r)
        return {s["name"]: s for s in status.load(self.status)["steps"]}["maws"]

    def test_a_deferral_is_finished_by_the_timer_with_the_same_command(self):
        self.exits("4", "0")
        self.assertEqual(self.step()["state"], "deferred")
        self.assertIsNotNone(status.maws_deferred(self.status))
        self.assertIn("maws provisioning deferred since", status.render(status.load(self.status)))
        self.assertEqual(steps.enroll(), 0)
        first, second = self.calls()
        self.assertEqual((first["argv"], first["stdin_sha256"]), (second["argv"], second["stdin_sha256"]),
                         "the timer ran another command than the boot's")
        self.assertIsNone(status.maws_deferred(self.status))
        self.assertEqual({s["name"]: s for s in status.load(self.status)["steps"]}["maws"]["state"], "ok")
        self.assertEqual(steps.enroll(), 0)
        self.assertEqual(len(self.calls()), 2, "the timer ran provision again once it was done")

    def test_the_timer_stays_deferred_on_another_4_keeping_the_first_time(self):
        self.exits("4", "4")
        self.step()
        since = status.maws_deferred(self.status)
        self.assertEqual(steps.enroll(), 0)
        self.assertEqual(status.maws_deferred(self.status), since, "the first deferral's time was lost")

    def test_a_refusal_fails_the_step_and_ends_the_deferral(self):
        self.exits("4", "1 other-delegation")
        self.step()
        self.assertEqual(steps.enroll(), 1)
        self.assertIsNone(status.maws_deferred(self.status), "a refusal left the timer retrying")
        entry = {s["name"]: s for s in status.load(self.status)["steps"]}["maws"]
        self.assertEqual(entry["state"], "failed")
        self.assertIn("other-delegation", entry["detail"])

    def test_a_rerun_of_a_provisioned_host_runs_the_same_command_again(self):
        # M1's `provision` is the idempotent one: on an org-listed endpoint it posts nothing and exits 0.
        self.assertEqual(self.step()["state"], "ok")
        self.assertEqual(self.step()["state"], "ok")
        first, second = self.calls()
        self.assertEqual(first["argv"], second["argv"])

    def test_nothing_is_provisioned_once_the_departure_has_started(self):
        status.set_lifecycle("depart", "departing", "started", path=self.status)
        entry = self.step()
        self.assertEqual(entry["state"], "skipped")
        self.assertIn("departure", entry["detail"])
        self.assertEqual(self.calls(), [])

    def test_devcloud_reconcile_runs_the_step_once_the_host_steps_are_done(self):
        for host_steps, ran in ((0, ["configuration", "maws"]), (1, ["configuration"])):
            with self.subTest(host_steps=host_steps):
                runs = []

                def run_(steps_, r, done=None, guard=None, code=host_steps):
                    runs.append(steps_[0][0])
                    return code if steps_[0][0] == "configuration" else 0
                with mock.patch.object(steps, "_run", run_):
                    self.assertEqual(steps.reconcile(), host_steps)
                self.assertEqual(runs, ran)
        self.assertNotIn("maws", [name for name, _ in steps.RECONCILE],
                         "the periodic jobs would provision a host again behind a brief's back")


if __name__ == "__main__":
    unittest.main()
