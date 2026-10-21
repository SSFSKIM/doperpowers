"""What `up` composes before anything is created (§3 steps 3–5): the
descriptor (I5 + I12), the user-data, the labels (I14) and the recipe hash."""
import base64
import pathlib
import re
import shutil
import tempfile
import unittest

import _path  # noqa: F401
from devcloudlib import descriptor, redact
from driver import compose, profile

from driver_fixtures import DRIVER_TOML, KEY, NOW, TOKEN

SEED_PRIVATE = "-----BEGIN PRIVATE KEY-----\nmadeUpSeedKeyBodyForTheScanOnly0123456789\n-----END PRIVATE KEY-----\n"


def a_profile(desk=False):
    d = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-compose-"))
    text = DRIVER_TOML.replace("{state}", "/tmp/x").replace("{registered}", "ab" * 32)
    if desk:
        text += '\n[desk]\nprovisioning_secret = "desk-key"\n'
    (d / "driver.toml").write_text(text)
    return profile.load(d)


class DescriptorTest(unittest.TestCase):
    def compose(self, **kw):
        args = dict(name="dc-build-7f3a", profile=a_profile(), projects=["example/repo", "other/thing@dev"],
                    expires=NOW + 3600, creator="@abcd1234", spot=False, seed="file")
        args.update(kw)
        return compose.descriptor(**args)

    def test_the_host_reads_it(self):
        d = descriptor.parse(self.compose())
        self.assertEqual((d.name, d.kind, d.role, d.tailscale), ("dc-build-7f3a", "vm", "persistent", "join"))
        self.assertEqual(d.ts_secret, "ts-oauth")
        self.assertEqual((d.seed_kind, d.seed_path), ("file", "/etc/devcloud/seed/seed.json"))
        self.assertEqual(d.projects, ("example/repo", "other/thing@dev"))
        self.assertEqual((d.expires, d.creator, d.inbound), (NOW + 3600, "@abcd1234", "tailnet"))
        self.assertEqual((d.sm_project, d.config_token_secret), ("example-project", "config-token"))
        self.assertFalse(d.spot or d.adopted)
        self.assertIsNone(d.sminos_secret)

    def test_keep_spot_metadata_seed_and_the_desk_key(self):
        d = descriptor.parse(self.compose(expires=None, creator=None, spot=True, seed="gce-metadata",
                                          profile=a_profile(desk=True)))
        self.assertIsNone(d.expires)
        self.assertIsNone(d.creator)
        self.assertTrue(d.spot)
        self.assertEqual(d.seed_kind, "gce-metadata")
        self.assertEqual(d.sminos_secret, "desk-key")

    def test_ids_never_values(self):
        text = self.compose(profile=a_profile(desk=True))
        self.assertNotIn(TOKEN, text)
        for line in text.splitlines():
            key, _, value = line.partition("=")
            self.assertTrue(key.startswith("DEVCLOUD_"), line)


class UserDataTest(unittest.TestCase):
    def test_keys_and_the_staged_descriptor_with_no_secret_value(self):
        desc = compose.descriptor(name="dc-a-0001", profile=a_profile(desk=True), projects=[], expires=NOW,
                                  creator=None, spot=False, seed="file")
        data = compose.user_data(desc, [KEY])
        self.assertTrue(data.startswith("#cloud-config\n"))
        # The staged descriptor, never /etc/devcloud/boot.env (setup.sh refuses one).
        self.assertIn(compose.STAGE, data)
        self.assertNotIn("/etc/devcloud/boot.env", data)
        blobs = re.findall(r"content: (\S+)", data)
        decoded = [base64.b64decode(b).decode() for b in blobs]
        self.assertIn(desc, decoded)
        self.assertIn(KEY + "\n", decoded)
        # The known-value scan: no value of the seed or Secret Manager in any spelling.
        known = redact.Known([TOKEN, SEED_PRIVATE, "madeUpSeedKeyBodyForTheScanOnly0123456789"])
        self.assertEqual(known.scrub(data), data)
        self.assertLess(len(data.encode()), 32 * 1024, "over Hetzner's user-data limit")


class LabelsTest(unittest.TestCase):
    def test_up_labels(self):
        got = compose.labels(kind="vm", lifetime="ttl", expires=NOW + 60, by="testmac", creator="abcd1234",
                             recipe="0123456789ab", confirmed=True, enroll="key", test_run="m3-1")
        self.assertEqual(got, {"devcloud": "vm", "devcloud-lifetime": "ttl", "devcloud-expires": str(NOW + 60),
                               "devcloud-by": "testmac", "devcloud-creator": "abcd1234",
                               "devcloud-recipe": "0123456789ab", "devcloud-confirmed": "1",
                               "devcloud-enroll": "key", "devcloud-test": "m3-1"})
        bare = compose.labels(kind="vm", lifetime="keep", expires=None, by="testmac", creator=None,
                              recipe="0123456789ab", confirmed=False, enroll=None, test_run=None)
        self.assertEqual(set(bare), {"devcloud", "devcloud-lifetime", "devcloud-by", "devcloud-recipe"})


class RecipeTest(unittest.TestCase):
    def test_twelve_hex_over_image_and_boot_and_nothing_else(self):
        root = pathlib.Path(tempfile.mkdtemp())
        for rel in ("image/setup.sh", "boot/devcloud", "boot/devcloudlib/x.py", "README.md"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(rel)
        first = compose.recipe_hash(root)
        self.assertRegex(first, r"\A[0-9a-f]{12}\Z")
        (root / "README.md").write_text("changed")
        (root / "boot/devcloudlib/__pycache__").mkdir()
        (root / "boot/devcloudlib/__pycache__/x.cpython-312.pyc").write_bytes(b"\0")
        self.assertEqual(compose.recipe_hash(root), first)
        (root / "boot/devcloudlib/x.py").write_text("changed")
        self.assertNotEqual(compose.recipe_hash(root), first)
        shutil.rmtree(root)

    def test_the_plugins_own(self):
        self.assertRegex(compose.recipe_hash(_path.DEVCLOUD), r"\A[0-9a-f]{12}\Z")


if __name__ == "__main__":
    unittest.main()
