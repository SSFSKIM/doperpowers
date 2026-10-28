"""Step 11's enrollment at the desk without a person (the driver's Design §10,
I15): `sminos hub check` decides, the provisioning key (or a one-time code
file) reaches `sminos hub enroll` on stdin only, and an undecided desk defers
the step to the devcloud-enroll service. The sminos stand-in
(fixtures/sminos.py) runs as a real subprocess; every value is made up."""

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
from devcloudlib import descriptor, lease, proc, sminos_host, status, steps
from devcloudlib.proc import StepError, User

FAKE = pathlib.Path(__file__).resolve().parents[1] / "fixtures/sminos.py"
KEY = "smns-provision-v1.made-up-key-Qx7Lp2Nd9Rv4"
CODE = "smns-enroll-v1.made-up-code-Hj3Kt8Wm1Zs6"
BASE = ("DEVCLOUD_NAME=dc-build-7f3a\nDEVCLOUD_KIND=vm\nDEVCLOUD_ROLE=persistent\nDEVCLOUD_TAILSCALE=none\n"
        "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=example-project\n"
        "DEVCLOUD_CONFIG_REPO=https://github.com/example/config.git\nDEVCLOUD_CONFIG_TOKEN_SECRET=config-token\n")


class EnrollBase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-enroll-"))
        me = pwd.getpwuid(os.getuid())
        self.home = self.tmp / "home"
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.home)
        clone = self.home / ".claude/plugins/marketplaces/doperpowers"
        cli = clone / "sminos/skills/sminos/scripts/sminos.py"
        cli.parent.mkdir(parents=True)
        shutil.copy(FAKE, cli)
        (self.home / ".claude/plugins/known_marketplaces.json").write_text(
            json.dumps({"doperpowers": {"installLocation": str(clone)}}))
        self.state = self.home / ".local/state/devcloud-test"
        self.state.mkdir(parents=True)
        self.code_file = self.tmp / "enroll-code"
        self.hub = self.home / ".claude/sminos/daemon/hub.json"
        self.ledgered = []
        self.sleeps = []
        self.fetched = []
        patch = mock.patch.object(proc, "LOG_DIR", self.tmp / "log")
        patch.start()
        self.addCleanup(patch.stop)

    def desc(self, secret=True):
        return descriptor.parse(BASE + ("DEVCLOUD_SMINOS_SECRET=desk-provisioning-key\n" if secret else ""))

    def exits(self, check=None, enroll=None):
        if check is not None:
            (self.state / "check.exit").write_text("".join(f"{c}\n" for c in check))
        if enroll is not None:
            (self.state / "enroll.exit").write_text("".join(f"{c}\n" for c in enroll))

    def fetch(self, name):
        self.fetched.append(name)
        return KEY

    def enroll(self, secret=True):
        return sminos_host.enroll(self.user, self.desc(secret), {}, self.fetch, code_file=self.code_file,
                                  ledger_add=self.ledgered.append, sleep=self.sleeps.append)

    def calls(self):
        path = self.state / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def verbs(self):
        return [" ".join(c["argv"][:2]) + (" --replace" if "--replace" in c["argv"] else "") for c in self.calls()]


class CheckTableTest(EnrollBase):
    def test_0_accepted_enrolls_nothing(self):
        self.exits(check=[0])
        self.assertEqual(self.enroll().state, "accepted")
        self.assertEqual(self.verbs(), ["hub check"])
        self.assertEqual(self.fetched, [], "the key was fetched for a credential the desk accepts")

    def test_1_enrolls_with_the_key_on_stdin(self):
        self.exits(check=[1])
        result = self.enroll()
        self.assertEqual(result.state, "enrolled")
        check, enroll = self.calls()
        self.assertEqual(enroll["argv"], ["hub", "enroll", "--name", "dc-build-7f3a"])
        self.assertEqual(enroll["stdin_sha256"], hashlib.sha256(KEY.encode()).hexdigest())
        self.assertEqual(self.fetched, ["desk-provisioning-key"])
        self.assertEqual(self.ledgered, [self.hub], "hub.json listed in the ledger before the enroll")
        self.assertTrue(self.hub.is_file())

    def test_3_enrolls_again_with_replace(self):
        self.hub.parent.mkdir(parents=True)
        self.hub.write_text("{}\n")
        self.exits(check=[3])
        self.assertEqual(self.enroll().state, "enrolled")
        self.assertEqual(self.verbs(), ["hub check", "hub enroll --replace"])

    def test_4_defers_keeping_the_credential_and_the_code(self):
        self.code_file.write_text(CODE + "\n")
        self.exits(check=[4])
        self.assertEqual(self.enroll().state, "deferred")
        self.assertEqual(self.verbs(), ["hub check"])
        self.assertTrue(self.code_file.exists(), "the code was spent on an undecided desk")

    def test_2_fails_the_step(self):
        self.exits(check=[2])
        with self.assertRaisesRegex(StepError, "hub check exited 2"):
            self.enroll()

    def test_a_cut_over_machine_enrolls_nothing(self):
        # O12's switch refuses `hub check` and `hub enroll` there, whose 1 would read as "not enrolled".
        (self.hub.parent).mkdir(parents=True)
        (self.hub.parent / "identity.json").write_text("{}\n")
        self.code_file.write_text(CODE + "\n")
        result = self.enroll()
        self.assertEqual(result.state, "cutover")
        self.assertEqual((self.calls(), self.fetched), ([], []))
        self.assertTrue(self.code_file.exists(), "a code was spent on a machine that enrolls nothing")

    def test_no_secret_and_no_code_enrolls_nothing(self):
        self.assertEqual(self.enroll(secret=False).state, "none")
        self.assertEqual(self.calls(), [])


class EnrollExitTest(EnrollBase):
    def test_retryable_refusals_are_tried_three_times_ten_seconds_apart(self):
        self.exits(check=[1], enroll=["1 sminos: mint-failed", "1 sminos: busy", "0"])
        self.assertEqual(self.enroll().state, "enrolled")
        self.assertEqual(self.verbs(), ["hub check"] + ["hub enroll"] * 3)
        self.assertEqual(self.sleeps, [10, 10])

    def test_three_retryable_refusals_fail_the_step(self):
        self.exits(check=[1], enroll=["1 sminos: no answer from the desk"] * 3)
        with self.assertRaisesRegex(StepError, "failed 3 times"):
            self.enroll()

    def test_a_refusal_that_needs_the_person_fails_at_once(self):
        for reason in sminos_host.FATAL_REASONS:
            with self.subTest(reason=reason):
                (self.state / "calls.jsonl").unlink(missing_ok=True)
                self.exits(check=[1], enroll=[f"1 sminos: {reason}"])
                with self.assertRaisesRegex(StepError, reason):
                    self.enroll()
                self.assertEqual(self.verbs(), ["hub check", "hub enroll"])

    def test_a_name_taken_and_a_usage_error_fail_the_step(self):
        for line, message in (("3 sminos: name taken", "taken"), ("2 sminos: name outside the key's prefix", "exited 2")):
            with self.subTest(line=line):
                self.exits(check=[1], enroll=[line])
                with self.assertRaisesRegex(StepError, message):
                    self.enroll()

    def test_a_code_file_stands_in_for_the_key_and_is_spent_whatever_the_outcome(self):
        self.code_file.write_text(CODE + "\n")
        self.exits(check=[1], enroll=["1 sminos: key-expired"])
        with self.assertRaises(StepError):
            self.enroll(secret=False)
        self.assertFalse(self.code_file.exists())
        self.assertEqual(self.calls()[-1]["stdin_sha256"], hashlib.sha256(CODE.encode()).hexdigest())
        self.assertEqual(self.fetched, [], "the key was fetched though a code was given")
        self.code_file.write_text(CODE + "\n")
        self.exits(check=[0])
        self.enroll(secret=False)
        self.assertFalse(self.code_file.exists(), "a decided 0 kept the code")

    def test_the_key_never_reaches_a_file_or_an_argument_list(self):
        self.exits(check=[1])
        self.enroll()
        self.assertFalse(any(KEY in arg for call in self.calls() for arg in call["argv"]))
        for path in self.tmp.rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes(), f"the key is in {path}")


class DeferredTest(EnrollBase):
    """The step's deferral, kept in the status, finished by `devcloud enroll`."""

    def setUp(self):
        super().setUp()
        self.status = self.tmp / "status.json"
        self.converged = []
        for patch in (mock.patch.object(status, "PATH", self.status),
                      mock.patch.object(lease, "LOCK", self.tmp / "lifecycle.lock"),
                      mock.patch.object(steps, "_locked", contextlib.nullcontext),
                      mock.patch.object(steps, "_read_env", lambda path: {}),
                      mock.patch.object(steps.ledger, "add", self.ledgered.append),
                      mock.patch.object(sminos_host, "CODE_FILE", self.code_file),
                      mock.patch.object(sminos_host, "PENDING", self.tmp / "restart-pending"),
                      mock.patch.object(sminos_host, "converge", lambda user, role, env, changed, provisions=False:
                                        self.converged.append(changed) or "sminos daemon: running"),
                      mock.patch.object(steps, "_fetch_text", lambda r, name: self.fetch(name)),
                      mock.patch.object(steps, "_say", lambda message: None)):   # the job's status lines
            patch.start()
            self.addCleanup(patch.stop)

    def run_(self):
        r = steps.Run("boot")
        r.desc, r.user, r.env_changed = self.desc(), self.user, False
        return r

    def test_the_step_defers_and_the_daemon_still_starts(self):
        self.exits(check=[4])
        with mock.patch.object(steps, "_devcloud_services", lambda r, record: "systemd: fine"):
            state, detail = steps.services_step(self.run_())
        self.assertEqual(state, "deferred")
        self.assertEqual(self.converged, [False], "the daemon was not started on a deferral")
        self.assertIsNotNone(status.enroll_deferred(self.status))
        self.assertIn("enroll deferred since", status.render(status.load(self.status)))

    def test_devcloud_enroll_finishes_on_a_later_1_and_then_does_nothing(self):
        status.set_enroll_deferred(True, self.status)
        self.exits(check=[1])
        with mock.patch.object(steps.Run, "load", lambda r: setattr(r, "desc", self.desc()) or setattr(
                r, "user", self.user)):
            self.assertEqual(steps.enroll(), 0)
            self.assertEqual(self.verbs(), ["hub check", "hub enroll"])
            self.assertIsNone(status.enroll_deferred(self.status))
            self.assertTrue((self.tmp / "restart-pending").exists(), "a new credential owes the daemon a restart")
            services = {s["name"]: s for s in status.load(self.status)["steps"]}["services"]
            self.assertEqual(services["state"], "ok")
            self.assertEqual(steps.enroll(), 0)
            self.assertEqual(len(self.calls()), 2, "the job asked again once the desk had decided")

    def test_devcloud_enroll_after_a_0_enrolls_nothing(self):
        status.set_enroll_deferred(True, self.status)
        self.exits(check=[0])
        with mock.patch.object(steps.Run, "load", lambda r: setattr(r, "desc", self.desc()) or setattr(
                r, "user", self.user)):
            self.assertEqual(steps.enroll(), 0)
        self.assertEqual(self.verbs(), ["hub check"])
        self.assertIsNone(status.enroll_deferred(self.status))

    def test_a_machine_cut_over_meanwhile_ends_the_deferral(self):
        status.set_enroll_deferred(True, self.status)
        (self.hub.parent).mkdir(parents=True)
        (self.hub.parent / "identity.json").write_text("{}\n")
        with mock.patch.object(steps.Run, "load", lambda r: setattr(r, "desc", self.desc()) or setattr(
                r, "user", self.user)):
            self.assertEqual(steps.enroll(), 0)
        self.assertEqual(self.calls(), [])
        self.assertIsNone(status.enroll_deferred(self.status), "the timer would ask a cut-over machine forever")

    def test_devcloud_enroll_stays_deferred_on_another_4(self):
        status.set_enroll_deferred(True, self.status)
        since = status.enroll_deferred(self.status)
        self.exits(check=[4])
        with mock.patch.object(steps.Run, "load", lambda r: setattr(r, "desc", self.desc()) or setattr(
                r, "user", self.user)):
            self.assertEqual(steps.enroll(), 0)
        self.assertEqual(status.enroll_deferred(self.status), since, "the first deferral's time was lost")


if __name__ == "__main__":
    unittest.main()
