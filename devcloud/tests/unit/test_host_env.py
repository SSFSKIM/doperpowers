"""/etc/devcloud/env's merge (boot step 10): the image's defaults, the host's
identity, then the profile's profile.env and secrets.toml's env targets. The
profile is shared by every host, so it never sets a per-host identity: a name
or boot id it carries would make hosts share one."""

import unittest

import _path  # noqa: F401
from devcloudlib import descriptor, steps

RENDERER = ("WEB_CHROME", "/usr/local/bin/chrome-headless-shell")


class HostEnvTest(unittest.TestCase):
    def test_image_then_identity_then_profile_then_secrets(self):
        pairs, ignored = steps.host_env({"SESSION_MIRROR_HOST": "sbx-a1"}, {"TZ": "UTC", "LANG": "C.UTF-8"},
                                        {"API_KEY": "made-up"})
        self.assertEqual(list(pairs.items()), [RENDERER, ("SESSION_MIRROR_HOST", "sbx-a1"), ("TZ", "UTC"),
                                               ("LANG", "C.UTF-8"), ("API_KEY", "made-up")])
        self.assertEqual(ignored, [])

    def test_the_profile_overrides_an_image_default(self):
        # WEB_CHROME=none in profile.env turns the web plugin's rendering off on every host.
        pairs, ignored = steps.host_env({"SESSION_MIRROR_HOST": "sbx-a1"}, {"WEB_CHROME": "none"}, {})
        self.assertEqual(pairs["WEB_CHROME"], "none")
        self.assertEqual(ignored, [])

    def test_the_profile_never_sets_a_per_host_identity(self):
        identity = {"SESSION_MIRROR_HOST": "sbx-a1", "DAEMON_BOOT_ID": "0b6c-host-own"}
        profile = {"SESSION_MIRROR_HOST": "laptop", "DAEMON_HOST": "laptop", "TZ": "UTC"}
        secret_env = {"DAEMON_BOOT_ID": "shared"}
        pairs, ignored = steps.host_env(identity, profile, secret_env)
        self.assertEqual(pairs, {RENDERER[0]: RENDERER[1], "SESSION_MIRROR_HOST": "sbx-a1",
                                 "DAEMON_BOOT_ID": "0b6c-host-own", "TZ": "UTC"})
        self.assertEqual(ignored, ["DAEMON_BOOT_ID", "DAEMON_HOST", "SESSION_MIRROR_HOST"])

    def test_the_delegation_id_is_the_descriptors_not_the_profiles(self):
        # Step 12's `devenv up maws` mints the machine's ref under it, before mawsd's first start.
        identity = {"SESSION_MIRROR_HOST": "dc-a-0001", "MAWS_DELEGATION_ID": "0123456789abcdef" * 2}
        pairs, ignored = steps.host_env(identity, {"MAWS_DELEGATION_ID": "f" * 32}, {})
        self.assertEqual(pairs["MAWS_DELEGATION_ID"], "0123456789abcdef" * 2)
        self.assertEqual(ignored, ["MAWS_DELEGATION_ID"])

    def test_the_identity_carries_the_delegation_id_when_the_descriptor_names_one(self):
        base = ("DEVCLOUD_NAME=dc-a-0001\nDEVCLOUD_KIND=vm\nDEVCLOUD_ROLE=persistent\nDEVCLOUD_TAILSCALE=none\n"
                "DEVCLOUD_SEED=gce-metadata\nDEVCLOUD_SM_PROJECT=example-project\n"
                "DEVCLOUD_CONFIG_REPO=https://github.com/example/config.git\nDEVCLOUD_CONFIG_TOKEN_SECRET=config-token\n")
        self.assertEqual(steps.identity_pairs(descriptor.parse(base)), {"SESSION_MIRROR_HOST": "dc-a-0001"})
        maws = base + f"DEVCLOUD_MAWS_SECRET=desk-provisioning-v2\nDEVCLOUD_MAWS_DELEGATION_ID={'ab' * 16}\n"
        self.assertEqual(steps.identity_pairs(descriptor.parse(maws)),
                         {"SESSION_MIRROR_HOST": "dc-a-0001", "MAWS_DELEGATION_ID": "ab" * 16})

    def test_a_vm_keeps_its_kernel_boot_id(self):
        # A VM's identity has no DAEMON_BOOT_ID (sminos reads the kernel's); the profile cannot add one.
        pairs, ignored = steps.host_env({"SESSION_MIRROR_HOST": "devbox-a"}, {"DAEMON_BOOT_ID": "shared"}, {})
        self.assertNotIn("DAEMON_BOOT_ID", pairs)
        self.assertEqual(ignored, ["DAEMON_BOOT_ID"])


if __name__ == "__main__":
    unittest.main()
