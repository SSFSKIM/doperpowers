"""The `devcloud vm` command line (I16): parsing and exit codes, the refusals
that make a machine not a driver, and the entry chain bin/devcloud →
boot/devcloud → the driver."""
import io
import os
import pathlib
import subprocess
import tempfile
import unittest

import _path  # noqa: F401
from driver import cli

from driver_fixtures import DriverBase, vm_labels, NOW


class CliTest(DriverBase):
    def main(self, *argv, stdin=b"", host_marker=None):
        return cli.main(list(argv), ctx=self.ctx, host_marker=host_marker or self.tmp / "no-boot.env",
                        stdin=io.BytesIO(stdin))

    def test_on_a_host_vm_refuses_with_6_and_calls_no_provider(self):
        marker = self.tmp / "boot.env"
        marker.write_text("DEVCLOUD_NAME=x\n")
        for argv in (["ls"], ["up", "--dry-run"], ["reap"]):
            self.assertEqual(self.main(*argv, host_marker=marker), 6)
        self.assertIn("devcloud vm: this machine is a devcloud host; drive from a Mac", self.err.getvalue())
        self.assertEqual(self.state()["calls"], [])

    def test_no_seed_is_6_for_every_command(self):
        self.seed.unlink()
        for argv in (["ls"], ["up", "--dry-run"], ["provider", "test", "main"], ["down", "x"]):
            self.assertEqual(self.main(*argv), 6, argv)
        self.assertIn("no seed key", self.err.getvalue())

    def test_usage_is_2(self):
        for argv in ([], ["fly"], ["up", "--keep", "--ttl", "3h"], ["up", "--disk", "lots"], ["lease", "x"],
                     ["up", "--enroll-code", "abc"], ["provider", "register"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.main(*argv), 2)

    def test_errors_print_one_line_and_their_code(self):
        self.assertEqual(self.main("up", "--type", "big", "--dry-run"), 4)
        self.assertIn("devcloud vm: big has 16 vCPU, over the size cap (8 vCPU): ask the person, then pass "
                      "--confirmed", self.err.getvalue())

    def test_ssh_takes_everything_after_the_double_dash(self):
        self.add_server("dc-a-0001", vm_labels(expires=NOW + 3600))
        self.assertEqual(self.main("ssh", "dc-a-0001", "--", "sminos", "spawn", "acc", "reply ok", "--cwd", "~/x"), 0)
        self.assertEqual(self.remote.calls[-1]["command"], "sminos spawn acc 'reply ok' --cwd '~/x'")
        self.main("ssh", "dc-a-0001", "--root")
        self.assertEqual(self.remote.calls[-1]["user"], "root")
        self.assertEqual(self.remote.calls[-1]["command"], "")

    def test_enroll_code_reads_stdin(self):
        self.assertEqual(self.main("up", "--enroll-code", "-", "--dry-run", stdin=b"smns-enroll-v1.x\n"), 0)
        self.assertEqual(self.main("up", "--enroll-code", "-", "--dry-run", stdin=b""), 2)


class EntryTest(unittest.TestCase):
    """bin/devcloud runs boot/devcloud with a Python 3.11+, which hands `vm`
    to the driver with the caller's PATH; without a seed that is exit 6."""

    def test_the_chain(self):
        home = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-entry-"))
        env = {"PATH": os.environ["PATH"], "HOME": str(home)}
        done = subprocess.run([str(_path.DEVCLOUD / "bin" / "devcloud"), "vm", "ls"], env=env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(done.returncode, 6, done.stderr)
        self.assertIn("no seed key", done.stderr)
        done = subprocess.run([str(_path.DEVCLOUD / "bin" / "devcloud"), "vm", "fly"], env=env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(done.returncode, 2)

    def test_no_python_311_is_a_clear_failure(self):
        empty = pathlib.Path(tempfile.mkdtemp())
        (empty / "python3").symlink_to("/usr/bin/false")
        done = subprocess.run(["/bin/bash", str(_path.DEVCLOUD / "bin" / "devcloud"), "vm", "ls"],
                              env={"PATH": f"{empty}:/usr/bin:/bin" if not pathlib.Path("/usr/bin/python3").exists()
                                   else str(empty), "HOME": str(empty)}, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertIn("Python 3.11", done.stderr)


if __name__ == "__main__":
    unittest.main()
