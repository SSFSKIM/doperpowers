"""The driver key's check before `up` (§8.3): a host's boot makes root's keys
equal to the configuration repository's driver-keys/, so `up` refuses while
this driver's key is not there yet — checked in the profile's checkout when it
is a checkout of that repository, and unchecked otherwise (a temporary
profile, wherever it lives)."""
import argparse
import os
import pathlib
import subprocess

import _path  # noqa: F401
from driver import adopt, context
from driver.errors import DriverError

from driver_fixtures import KEY, DriverBase

CONFIG = "https://github.com/example/config.git"


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"})


class Checkout(DriverBase):
    def setUp(self):
        super().setUp()
        (self.profile_dir / "driver-keys" / "testmac.pub").write_text(KEY + "\n")
        self.bare = self.tmp / "config.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.bare))

    def checkout(self, origin, pushed):
        git(self.profile_dir, "init", "-q", "-b", "main")
        git(self.profile_dir, "remote", "add", "origin", origin)
        for url in (CONFIG, "https://github.com/example/other.git"):
            git(self.profile_dir, "config", "--add", f"url.{self.bare.as_uri()}.insteadOf", url)
        if pushed:
            git(self.profile_dir, "add", "driver-keys/testmac.pub")
        else:
            (self.profile_dir / "README").write_text("x")
            git(self.profile_dir, "add", "README")
        git(self.profile_dir, "commit", "-q", "-m", "c")
        git(self.profile_dir, "push", "-q", "origin", "main")


class KeyInRemoteTest(Checkout):

    def test_a_checkout_of_the_config_repository_without_the_key_refuses(self):
        self.checkout(CONFIG, pushed=False)
        self.assertFalse(context.key_in_remote(self.ctx))

    def test_a_checkout_of_the_config_repository_with_the_key_passes(self):
        self.checkout(CONFIG, pushed=True)
        self.assertTrue(context.key_in_remote(self.ctx))

    def test_a_profile_inside_another_repository_is_unchecked(self):
        self.checkout("https://github.com/example/other.git", pushed=False)
        self.assertTrue(context.key_in_remote(self.ctx))
        self.assertIn("not a checkout of the configuration repository", self.err.getvalue())

    def test_a_profile_outside_any_checkout_is_unchecked(self):
        self.assertTrue(context.key_in_remote(self.ctx))


NEW_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINewKeyAfterTheOldOneWasLost devcloud-testmac"


class AdoptPreflightTest(Checkout):
    """adopt's preflight checks the key this Mac will use, so the key is
    made (and its public half written to the profile, as ssh.ensure_key
    does) before the check reads it."""

    def setUp(self):
        super().setUp()
        self.ctx = self.make_ctx(key_pushed=None)
        def ensure_key():
            mine = self.profile_dir / "driver-keys" / "testmac.pub"
            mine.write_text(NEW_KEY + "\n")
            return NEW_KEY
        self.remote.ensure_key = ensure_key

    def refused(self):
        opts = argparse.Namespace(target="root@203.0.113.50", label="adp", project=[], ttl=None, confirmed=True,
                                  dry_run=False)
        with self.assertRaises(DriverError) as caught:
            adopt.run(self.ctx, opts)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("configuration repository", str(caught.exception))
        self.assertEqual(self.remote.calls, [], "the machine was contacted")

    def test_first_use_makes_the_key_then_refuses_it_unpublished(self):
        self.checkout(CONFIG, pushed=False)
        (self.profile_dir / "driver-keys" / "testmac.pub").unlink()
        self.refused()

    def test_a_regenerated_key_is_checked_not_the_old_published_one(self):
        self.checkout(CONFIG, pushed=True)      # the old key is in the repository; this Mac lost it
        self.refused()
