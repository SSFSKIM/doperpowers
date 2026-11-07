"""The driver's descriptor keys (Interfaces I12): the lease, its creator, the
inbound policy, adoption, a spot VM and MAWS's provisioning code. Unknown
keys stay refused, but the retired DX2 provisioning key is ignored; a lease
end in the past is accepted (a host rebooted after its lease must still
boot, then depart); a sandbox carries none of the keys that would make it
depart or enroll."""

import dataclasses
import unittest

import _path  # noqa: F401
from devcloudlib import descriptor

VM = {
    "DEVCLOUD_NAME": "dc-build-7f3a",
    "DEVCLOUD_KIND": "vm",
    "DEVCLOUD_ROLE": "persistent",
    "DEVCLOUD_TAILSCALE": "join",
    "DEVCLOUD_TS_SECRET": "tailscale-client",
    "DEVCLOUD_SEED": "file:/etc/devcloud/seed/key.json",
    "DEVCLOUD_SM_PROJECT": "example-project",
    "DEVCLOUD_CONFIG_REPO": "https://github.com/example/config.git",
    "DEVCLOUD_CONFIG_TOKEN_SECRET": "config-token",
}
SANDBOX = dict(VM, DEVCLOUD_KIND="container", DEVCLOUD_ROLE="sandbox", DEVCLOUD_TAILSCALE="host",
               DEVCLOUD_TS_SECRET=None)


def text(base=VM, **overrides):
    values = dict(base, **overrides)
    return "".join(f"{k}={v}\n" for k, v in values.items() if v is not None)


class LeaseKeysTest(unittest.TestCase):
    def test_absent_keys_mean_no_lease_open_inbound_and_nothing_else(self):
        d = descriptor.parse(text())
        self.assertEqual((d.expires, d.leased, d.creator, d.inbound, d.adopted, d.spot),
                         (None, False, None, "open", False, False))

    def test_reads_every_key(self):
        d = descriptor.parse(text(DEVCLOUD_EXPIRES="1792000000", DEVCLOUD_CREATOR="@build#4f2a",
                                  DEVCLOUD_INBOUND="tailnet", DEVCLOUD_ADOPTED="1", DEVCLOUD_SPOT="1"))
        self.assertEqual((d.expires, d.leased, d.creator, d.inbound, d.adopted, d.spot),
                         (1792000000, True, "@build#4f2a", "tailnet", True, True))

    def test_a_lease_end_in_the_past_is_accepted(self):
        self.assertEqual(descriptor.parse(text(DEVCLOUD_EXPIRES="1")).expires, 1)

    def test_refuses_malformed_values(self):
        cases = {
            "DEVCLOUD_EXPIRES": ["soon", "-5", "1.5", "17920000000000"],
            "DEVCLOUD_CREATOR": ["build", "@", "@a b"],
            "DEVCLOUD_INBOUND": ["closed", "TAILNET"],
            "DEVCLOUD_ADOPTED": ["yes", "0", "true"],
            "DEVCLOUD_SPOT": ["yes", "2"],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaisesRegex(descriptor.DescriptorError, key):
                    descriptor.parse(text(**{key: f"'{value}'"}))

    def test_a_tailnet_only_inbound_needs_a_tailnet_join(self):
        with self.assertRaisesRegex(descriptor.DescriptorError, "DEVCLOUD_TAILSCALE=join"):
            descriptor.parse(text(DEVCLOUD_TAILSCALE="none", DEVCLOUD_TS_SECRET=None, DEVCLOUD_INBOUND="tailnet"))

    def test_a_sandbox_never_carries_a_lease_adoption_enrollment_or_spot(self):
        self.assertEqual(descriptor.parse(text(SANDBOX, DEVCLOUD_INBOUND="open")).inbound, "open")
        for key, value in (("DEVCLOUD_EXPIRES", "1792000000"), ("DEVCLOUD_ADOPTED", "1"),
                           ("DEVCLOUD_SPOT", "1")):
            with self.subTest(key=key), self.assertRaisesRegex(descriptor.DescriptorError, f"{key}.*sandbox"):
                descriptor.parse(text(SANDBOX, **{key: value}))
        with self.assertRaisesRegex(descriptor.DescriptorError, "DEVCLOUD_MAWS_SECRET.*sandbox"):
            descriptor.parse(text(SANDBOX, DEVCLOUD_MAWS_SECRET="desk-provisioning-v2",
                                  DEVCLOUD_MAWS_DELEGATION_ID="0123456789abcdef" * 2))

    def test_the_maws_provisioning_code_and_its_delegation_are_optional_and_go_together(self):
        d = descriptor.parse(text())
        self.assertEqual((d.maws_secret, d.maws_delegation_id), (None, None))
        maws = dict(DEVCLOUD_MAWS_SECRET="desk-provisioning-v2", DEVCLOUD_MAWS_DELEGATION_ID="0123456789abcdef" * 2)
        d = descriptor.parse(text(**maws))
        self.assertEqual((d.maws_secret, d.maws_delegation_id), ("desk-provisioning-v2", "0123456789abcdef" * 2))
        for key in maws:
            with self.subTest(alone=key), self.assertRaisesRegex(descriptor.DescriptorError, "together"):
                descriptor.parse(text(**{key: maws[key]}))
        for key, value in (("DEVCLOUD_MAWS_SECRET", "projects/x/secrets/y"),
                           ("DEVCLOUD_MAWS_DELEGATION_ID", "0123456789ABCDEF" * 2),
                           ("DEVCLOUD_MAWS_DELEGATION_ID", "0123")):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(descriptor.DescriptorError, key):
                descriptor.parse(text(**dict(maws, **{key: value})))

    def test_the_retired_dx2_provisioning_key_is_ignored_not_refused(self):
        # A live VM an older driver made still names the v1 key: it boots as before, the key ignored.
        for base in (VM, SANDBOX):
            with self.subTest(role=base["DEVCLOUD_ROLE"]):
                d = descriptor.parse(text(base, DEVCLOUD_SMINOS_SECRET="desk-key"))
                self.assertEqual(d.ignored, ("DEVCLOUD_SMINOS_SECRET",))
                self.assertEqual(dataclasses.replace(d, ignored=()), descriptor.parse(text(base)))
        self.assertEqual(descriptor.parse(text()).ignored, ())

    def test_unknown_keys_stay_refused(self):
        with self.assertRaisesRegex(descriptor.DescriptorError, "DEVCLOUD_LEASE"):
            descriptor.parse(text(DEVCLOUD_LEASE="12h"))


class SetExpiresTest(unittest.TestCase):
    def test_rewrites_the_lease_and_keeps_every_other_line(self):
        before = "# made by the driver\n" + text(DEVCLOUD_EXPIRES="1792000000") + "DEVCLOUD_SPOT=1\n"
        after = descriptor.set_expires(before, 1792003600)
        self.assertEqual(after, before.replace("DEVCLOUD_EXPIRES=1792000000", "DEVCLOUD_EXPIRES=1792003600"))
        self.assertEqual(descriptor.parse(after).expires, 1792003600)

    def test_adds_a_lease_to_a_descriptor_without_one(self):
        after = descriptor.set_expires(text().rstrip("\n"), 1792000000)
        self.assertEqual(descriptor.parse(after).expires, 1792000000)
        self.assertTrue(after.endswith("\nDEVCLOUD_EXPIRES=1792000000\n"))

    def test_a_repeated_key_leaves_one_line(self):
        after = descriptor.set_expires(text() + "DEVCLOUD_EXPIRES=1\nexport DEVCLOUD_EXPIRES=2\n", 3)
        self.assertEqual(after.count("DEVCLOUD_EXPIRES"), 1)
        self.assertEqual(descriptor.parse(after).expires, 3)

    def test_none_removes_the_lease_and_keeps_every_other_line(self):
        before = "# made by the driver\n" + text(DEVCLOUD_EXPIRES="1792000000") + "export DEVCLOUD_EXPIRES=2\n"
        after = descriptor.set_expires(before, None)
        self.assertNotIn("DEVCLOUD_EXPIRES", after)
        self.assertEqual(after, "# made by the driver\n" + text())
        self.assertFalse(descriptor.parse(after).leased)
        self.assertEqual(descriptor.set_expires(text(), None), text())


if __name__ == "__main__":
    unittest.main()
