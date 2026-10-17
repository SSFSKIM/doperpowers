import unittest

import _path  # noqa: F401
from devcloudlib import descriptor

BASE = {
    "DEVCLOUD_NAME": "sbx-a1b2",
    "DEVCLOUD_KIND": "container",
    "DEVCLOUD_ROLE": "sandbox",
    "DEVCLOUD_TAILSCALE": "host",
    "DEVCLOUD_SEED": "file:/run/devcloud/seed.json",
    "DEVCLOUD_SM_PROJECT": "example-project",
    "DEVCLOUD_CONFIG_REPO": "https://github.com/example/config.git",
    "DEVCLOUD_CONFIG_TOKEN_SECRET": "config-token",
}


def text(**overrides):
    values = dict(BASE, **overrides)
    return "".join(f"{k}={v}\n" for k, v in values.items() if v is not None)


class DescriptorTest(unittest.TestCase):
    def test_reads_the_required_keys_with_defaults(self):
        d = descriptor.parse(text())
        self.assertEqual((d.name, d.kind, d.role, d.tailscale), ("sbx-a1b2", "container", "sandbox", "host"))
        self.assertEqual((d.seed_kind, d.seed_path), ("file", "/run/devcloud/seed.json"))
        self.assertEqual(d.config_branch, "main")
        self.assertEqual(d.projects, ())
        self.assertIsNone(d.mirror_dir)

    def test_gce_metadata_seed_and_projects(self):
        d = descriptor.parse(text(DEVCLOUD_SEED="gce-metadata", DEVCLOUD_CONFIG_BRANCH="hosts",
                                  DEVCLOUD_PROJECTS='"doperpowers example/repo@v2 other@main"'))
        self.assertEqual((d.seed_kind, d.seed_path), ("gce-metadata", None))
        self.assertEqual(d.config_branch, "hosts")
        self.assertEqual(d.projects, ("doperpowers", "example/repo@v2", "other@main"))

    def test_join_needs_an_auth_key_file_and_a_persistent_host(self):
        d = descriptor.parse(text(DEVCLOUD_KIND="vm", DEVCLOUD_ROLE="persistent", DEVCLOUD_TAILSCALE="join",
                                  DEVCLOUD_TS_AUTHKEY_FILE="/run/devcloud/ts.key"))
        self.assertEqual(d.ts_authkey_file, "/run/devcloud/ts.key")
        with self.assertRaisesRegex(descriptor.DescriptorError, "DEVCLOUD_TS_AUTHKEY_FILE"):
            descriptor.parse(text(DEVCLOUD_KIND="vm", DEVCLOUD_ROLE="persistent", DEVCLOUD_TAILSCALE="join"))
        with self.assertRaisesRegex(descriptor.DescriptorError, "sandbox"):
            descriptor.parse(text(DEVCLOUD_TAILSCALE="join", DEVCLOUD_TS_AUTHKEY_FILE="/k"))

    def test_refuses_missing_unknown_and_malformed_keys(self):
        cases = {
            "DEVCLOUD_SM_PROJECT": text(DEVCLOUD_SM_PROJECT=None),
            "DEVCLOUD_KIND": text(DEVCLOUD_KIND="laptop"),
            "DEVCLOUD_ROLE": text(DEVCLOUD_ROLE="pet"),
            "DEVCLOUD_TAILSCALE": text(DEVCLOUD_TAILSCALE="maybe"),
            "DEVCLOUD_SEED": text(DEVCLOUD_SEED="password:x"),
            "DEVCLOUD_NAME": text(DEVCLOUD_NAME="bad_name!"),
            "DEVCLOUD_PROJECTS": text(DEVCLOUD_PROJECTS='"a/b/c"'),
            "DEVCLOUD_TYPO": text() + "DEVCLOUD_TYPO=1\n",
            "DEVCLOUD_MIRROR_DIR": text(DEVCLOUD_MIRROR_DIR="relative/mirrors"),
        }
        for key, body in cases.items():
            with self.subTest(key=key), self.assertRaisesRegex(descriptor.DescriptorError, key):
                descriptor.parse(body)

    def test_config_repo_is_https_unless_plain_http_is_allowed(self):
        plain = text(DEVCLOUD_CONFIG_REPO="http://fixtures:8083/config.git")
        with self.assertRaisesRegex(descriptor.DescriptorError, "https"):
            descriptor.parse(plain)
        self.assertEqual(descriptor.parse(plain, allow_http=True).config_repo, "http://fixtures:8083/config.git")


if __name__ == "__main__":
    unittest.main()
