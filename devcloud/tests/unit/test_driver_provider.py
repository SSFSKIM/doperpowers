"""The provider protocol's client (I13, §6.1, §6.2), against the stand-in
provider executable: exits, timeouts, the environment, the scrub, and which
executable an account's calls run."""
import json
import shutil

import _path  # noqa: F401
from driver import provider
from driver.errors import DriverError

from driver_fixtures import TOKEN, DriverBase, vm_labels


class ProtocolTest(DriverBase):
    def client(self):
        return self.ctx.client(self.ctx.profile.account("main"))

    def code_of(self, fn):
        with self.assertRaises(DriverError) as caught:
            fn()
        return caught.exception.code, str(caught.exception)

    def test_a_refusal_of_each_kind_is_exit_3_with_its_kind(self):
        for kind in ("limit", "quota", "unavailable", "other"):
            with self.subTest(kind=kind):
                self.behave(refuse={"create": kind})
                code, message = self.code_of(lambda: self.client().call("create", {"labels": {"devcloud": "vm"}}))
                self.assertEqual(code, 3)
                self.assertIn(f"({kind})", message)

    def test_any_other_exit_or_unparsable_stdout_is_exit_1(self):
        self.behave(fail={"list": 1})
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)
        self.behave(fail={"list": 7})
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)
        self.behave(fail={}, garbage=["list"])
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)
        # A refusal whose stdout is not a refusal is a failure, not a refusal.
        self.behave(garbage=[], refuse={}, fail={"get": 3})
        self.assertEqual(self.code_of(lambda: self.client().get("1"))[0], 1)

    def test_each_timeout(self):
        ctx = self.make_ctx(timeouts={"list": 1, "create": 1})
        client = ctx.client(ctx.profile.account("main"))
        self.behave(hang=["list", "create"])
        for fn in (client.list, lambda: client.call("create", {"labels": {"devcloud": "vm"}})):
            code, message = self.code_of(fn)
            self.assertEqual(code, 1)
            self.assertIn("timed out", message)
        self.assertEqual(provider.LONG, 900)
        self.assertEqual(provider.SHORT, 120)
        self.assertEqual(set(provider.LONG_OPS), {"create", "image-create", "images", "image-delete"})

    def test_credentials_reach_the_childs_environment_only(self):
        ctx = self.make_ctx(env={"PATH": self.ctx.env["PATH"], "HOME": str(self.tmp), "DRIVER_ONLY": "x"})
        self.behave(record_env=["FAKE_TOKEN", "FAKE_PROVIDER_STATE", "DRIVER_ONLY", "HOME"])
        ctx.client(ctx.profile.account("main")).list()
        call = self.state()["calls"][-1]
        self.assertEqual(call["argv"], ["list"])
        self.assertEqual(call["env"]["FAKE_TOKEN"], TOKEN)
        self.assertEqual(call["env"]["FAKE_PROVIDER_STATE"], str(self.state_file))
        self.assertIsNone(call["env"]["DRIVER_ONLY"], "the driver's own environment leaked into the provider's")
        self.assertEqual(call["env"]["HOME"], str(self.tmp))
        self.assertEqual(self.secrets.reads, ["fake-token-secret"], "read from Secret Manager per call")
        ctx.client(ctx.profile.account("main")).list()
        self.assertEqual(self.secrets.reads, ["fake-token-secret"] * 2)

    def test_stderr_is_shown_scrubbed_of_the_credential(self):
        self.behave(stderr="auth with {env:FAKE_TOKEN} failed", fail={"list": 1})
        self.code_of(lambda: self.client().list())
        shown = self.err.getvalue()
        self.assertIn("auth with [secret] failed", shown)
        self.assertNotIn(TOKEN, shown)
        self.behave(fail={}, refuse={"create": "limit"})
        self.code_of(lambda: self.client().call("create", {"labels": {"devcloud": "vm"}}))
        self.assertNotIn(TOKEN, self.err.getvalue())

    def test_a_label_outside_i14_is_refused_before_the_provider_runs(self):
        before = len(self.state()["calls"])
        for labels in ({"devcloud": "vm", "owner": "me"}, {"devcloud": "nope"}, {"name": "x"}):
            code, _ = self.code_of(lambda: self.client().call("create", {"labels": labels}))
            self.assertEqual(code, 1)
        self.assertEqual(len(self.state()["calls"]), before)

    def test_answers_that_are_not_the_shapes_are_failures(self):
        state = self.state()
        state["servers"].append({"id": 1, "name": "x", "labels": {"devcloud": "vm"}})
        self.state_file.write_text(json.dumps(state))
        self.assertEqual(self.code_of(lambda: self.client().list())[0], 1)


class UsabilityTest(DriverBase):
    def account(self):
        return self.ctx.profile.account("main")

    def code_of(self, fn):
        with self.assertRaises(DriverError) as caught:
            fn()
        return caught.exception.code, str(caught.exception)

    def test_an_unregistered_account_is_exit_7_naming_registration(self):
        toml = self.profile_dir / "driver.toml"
        toml.write_text("\n".join(l for l in toml.read_text().splitlines() if not l.startswith("registered")))
        self.ctx.reload_profile()
        code, message = self.code_of(lambda: self.ctx.client(self.account()))
        self.assertEqual(code, 7)
        self.assertIn("not registered (the person runs devcloud vm provider register main --confirmed, then "
                      "devcloud vm provider test main)", message)

    def test_no_passing_copy_is_exit_7(self):
        (self.profile_dir / "providers" / ".pass" / "main").unlink()
        code, message = self.code_of(lambda: self.ctx.client(self.account()))
        self.assertEqual(code, 7)
        self.assertIn("no passing copy", message)

    def test_a_copy_that_does_not_match_its_record_is_exit_7(self):
        copy = self.profile_dir / "providers" / ".pass" / "main"
        copy.write_text(copy.read_text() + "\n# changed\n")
        self.assertEqual(self.code_of(lambda: self.ctx.client(self.account()))[0], 7)

    def test_every_call_runs_the_passing_copy_not_the_working_file(self):
        working = self.profile_dir / "providers" / "fake"
        working.write_text("#!/bin/sh\necho broken >&2\nexit 1\n")
        self.add_server("dc-a-0001", vm_labels(expires=1))
        names = [vm["name"] for vm in self.ctx.client(self.account()).list()]
        self.assertEqual(names, ["dc-a-0001"])

    def test_a_profile_provider_under_a_shipped_name_is_refused(self):
        shutil.copy(self.profile_dir / "providers" / "fake", self.profile_dir / "providers" / "hetzner")
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text().replace('provider = "fake"', 'provider = "hetzner"'))
        self.ctx.reload_profile()
        code, message = self.code_of(lambda: self.ctx.client(self.account()))
        self.assertEqual(code, 2)
        self.assertIn("shadows", message)

    def test_a_shipped_provider_needs_neither(self):
        toml = self.profile_dir / "driver.toml"
        toml.write_text(toml.read_text().replace('provider = "fake"', 'provider = "hetzner"'))
        self.ctx.reload_profile()
        client = self.ctx.client(self.account())
        self.assertEqual(client.executable, provider.SHIPPED_DIR / "hetzner")

    def test_usable_skips_and_names_an_unusable_account(self):
        (self.profile_dir / "providers" / ".pass" / "main").unlink()
        self.assertEqual(self.ctx.usable(), [])
        self.assertIn("skipping account main", self.err.getvalue())
