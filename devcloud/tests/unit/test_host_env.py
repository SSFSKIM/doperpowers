"""/etc/devcloud/env's merge (boot step 10): the host's identity, then the
profile's profile.env and secrets.toml's env targets. The profile is shared
by every host, so it never sets a per-host identity: a name or boot id it
carries would make hosts share one."""

import unittest

import _path  # noqa: F401
from devcloudlib import steps


class HostEnvTest(unittest.TestCase):
    def test_identity_then_profile_then_secrets(self):
        pairs, ignored = steps.host_env({"SESSION_MIRROR_HOST": "sbx-a1"}, {"TZ": "UTC", "LANG": "C.UTF-8"},
                                        {"API_KEY": "made-up"})
        self.assertEqual(list(pairs.items()), [("SESSION_MIRROR_HOST", "sbx-a1"), ("TZ", "UTC"),
                                               ("LANG", "C.UTF-8"), ("API_KEY", "made-up")])
        self.assertEqual(ignored, [])

    def test_the_profile_never_sets_a_per_host_identity(self):
        identity = {"SESSION_MIRROR_HOST": "sbx-a1", "DAEMON_BOOT_ID": "0b6c-host-own"}
        profile = {"SESSION_MIRROR_HOST": "laptop", "DAEMON_HOST": "laptop", "TZ": "UTC"}
        secret_env = {"DAEMON_BOOT_ID": "shared"}
        pairs, ignored = steps.host_env(identity, profile, secret_env)
        self.assertEqual(pairs, {"SESSION_MIRROR_HOST": "sbx-a1", "DAEMON_BOOT_ID": "0b6c-host-own", "TZ": "UTC"})
        self.assertEqual(ignored, ["DAEMON_BOOT_ID", "DAEMON_HOST", "SESSION_MIRROR_HOST"])

    def test_a_vm_keeps_its_kernel_boot_id(self):
        # A VM's identity has no DAEMON_BOOT_ID (sminos reads the kernel's); the profile cannot add one.
        pairs, ignored = steps.host_env({"SESSION_MIRROR_HOST": "devbox-a"}, {"DAEMON_BOOT_ID": "shared"}, {})
        self.assertNotIn("DAEMON_BOOT_ID", pairs)
        self.assertEqual(ignored, ["DAEMON_BOOT_ID"])


if __name__ == "__main__":
    unittest.main()
