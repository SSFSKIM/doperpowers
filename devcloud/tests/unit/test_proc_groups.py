"""A command run as the host's user carries the user's supplementary groups
from the group database, as a login does: a project's `devenv up` at boot
reaches Docker's socket through the `docker` group the GPU step added
(the VM driver's §6.7), in the same boot."""
import subprocess
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import proc
from devcloudlib.proc import User

USER = User(name="dev", uid=1001, gid=1001, home="/home/dev")


class UserGroupsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_run(argv, **kwargs):
            self.calls.append(kwargs)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        for patch in (mock.patch.object(proc.os, "geteuid", lambda: 0),
                      mock.patch.object(proc.os, "getgrouplist",
                                        lambda name, gid: [gid, 999] if name == "dev" else [gid]),
                      mock.patch.object(proc.subprocess, "run", fake_run)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_run_as_the_user_carries_its_groups(self):
        proc.run(["devenv", "up", "app"], user=USER)
        self.assertEqual(self.calls[-1]["extra_groups"], [1001, 999])
        self.assertEqual((self.calls[-1]["user"], self.calls[-1]["group"]), (1001, 1001))

    def test_call_as_the_user_carries_its_groups(self):
        proc.call(["sminos", "hub", "check"], user=USER)
        self.assertEqual(self.calls[-1]["extra_groups"], [1001, 999])

    def test_root_runs_as_itself(self):
        proc.run(["true"])
        self.assertNotIn("extra_groups", self.calls[-1])

    def test_a_user_the_database_does_not_know_gets_its_primary_group_alone(self):
        with mock.patch.object(proc.os, "getgrouplist", mock.Mock(side_effect=KeyError("dev"))):
            proc.run(["true"], user=USER)
        self.assertEqual(self.calls[-1]["extra_groups"], [1001])


if __name__ == "__main__":
    unittest.main()
