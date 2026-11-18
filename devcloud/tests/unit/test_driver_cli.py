"""The `devcloud vm` command line (I16): parsing and exit codes, the refusals
that make a machine not a driver, and the entry chain bin/devcloud →
boot/devcloud → the driver."""
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from driver import cli, images

from driver_fixtures import DriverBase, vm_labels, NOW


class CliTest(DriverBase):
    def main(self, *argv, host_marker=None):
        return cli.main(list(argv), ctx=self.ctx, host_marker=host_marker or self.tmp / "no-boot.env")

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

    def test_a_seed_that_cannot_be_looked_up_is_1_not_6(self):
        refused = PermissionError(13, "Permission denied")
        with mock.patch.object(pathlib.Path, "stat", side_effect=refused):
            self.assertEqual(self.main("owned-by", "@abcd1234"), 1)
        self.assertIn("cannot look up the seed key", self.err.getvalue())
        self.assertNotIn("no seed key", self.err.getvalue())

    def test_a_sigterm_ends_the_command_as_an_interrupt_does(self):
        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)

        def terminated(argv):
            os.kill(os.getpid(), signal.SIGTERM)
            return 0

        with mock.patch.object(cli, "main", terminated):
            with self.assertRaises(cli.Terminated):
                cli.command_line(["ls"])
        with mock.patch("driver.ops.ls", side_effect=cli.Terminated):
            self.assertEqual(self.main("ls"), 143)
        self.assertIn("devcloud vm: terminated", self.err.getvalue())

    def test_usage_is_2(self):
        for argv in ([], ["fly"], ["up", "--keep", "--ttl", "3h"], ["up", "--disk", "lots"], ["lease", "x"],
                     ["up", "--enroll-code", "-"], ["provider", "register"], ["image"], ["image", "bake"]):
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

    def test_image_ls_and_build_reach_the_images(self):
        self.assertEqual(self.main("image", "ls"), 0)
        self.assertIn("ACCOUNT", self.out.getvalue())
        self.behave(capabilities=["user_data"])
        self.ctx = self.make_ctx()
        self.assertEqual(self.main("image", "build", "--account", "main"), 3)
        self.assertIn("no images capability", self.err.getvalue())
        self.assertEqual(self.main("image", "build", "--account", "main", "--arch", "sparc"), 2)

    def test_image_build_takes_an_architecture(self):
        with mock.patch.object(images, "build_command", return_value=0) as build:
            self.assertEqual(self.main("image", "build", "--account", "main", "--arch", "arm"), 0)
        build.assert_called_once_with(self.ctx, "main", arch="arm")

    def test_adopt_needs_confirmed_and_dry_runs_with_it(self):
        self.assertEqual(self.main("adopt", "root@203.0.113.50", "--dry-run"), 4)
        self.assertIn("--confirmed", self.err.getvalue())
        self.assertEqual(self.main("adopt", "root@203.0.113.50", "--label", "adp", "--ttl", "2h", "--confirmed",
                                   "--dry-run"), 0)
        self.assertIn("root@203.0.113.50 as a new dc-adp-", self.out.getvalue())
        self.assertEqual(self.main("adopt"), 2)


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


class OwnedByEntryTest(unittest.TestCase):
    """`vm owned-by` through the real launcher, in an isolated HOME and PATH.
    With a Python 3.11+ the driver decides; without one the launcher answers 6
    only where the driver would (a host, a copy without driver/, a seed key
    confirmed absent where Paths.from_env puts it), and 1 otherwise."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-owned-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.no_python = self.tmp / "no-python"     # a PATH with nothing on it
        self.no_python.mkdir()
        self.python = self.tmp / "python"           # a PATH with a Python 3.11+ alone
        self.python.mkdir()
        (self.python / "python3").symlink_to(sys.executable)
        self.seed = self.home / ".config" / "devcloud" / "seed.json"

    def run_launcher(self, path, root=_path.DEVCLOUD, home=True, **env):
        env = {"PATH": str(path), **({"HOME": str(self.home)} if home else {}), **env}
        return subprocess.run(["/bin/bash", str(root / "bin" / "devcloud"), "vm", "owned-by", "@abcd1234"],
                              env=env, capture_output=True, text=True, timeout=60)

    def give_seed(self):
        self.seed.parent.mkdir(parents=True)
        self.seed.write_text("{}")

    def copy(self, driver=True, rebind=None):
        """The plugin's launcher and boot program, with or without the driver,
        and the launcher's fixed paths rebound as `rebind` maps them."""
        root = self.tmp / "devcloud"
        skip = shutil.ignore_patterns("__pycache__")
        for part in ("bin", "boot") + (("driver",) if driver else ()):
            shutil.copytree(_path.DEVCLOUD / part, root / part, ignore=skip, symlinks=True)
        launcher = root / "bin" / "devcloud"
        text = launcher.read_text()
        for fixed, there in (rebind or {}).items():
            self.assertIn(fixed, text)
            text = text.replace(fixed, there)
        launcher.write_text(text)
        return root

    def test_a_host_without_python_is_6(self):
        marker = self.tmp / "boot.env"
        marker.write_text("DEVCLOUD_NAME=x\n")
        self.give_seed()
        done = self.run_launcher(self.no_python, root=self.copy(rebind={"/etc/devcloud/boot.env": str(marker)}))
        self.assertEqual(done.returncode, 6, done.stderr)
        self.assertIn("devcloud vm: this machine is a devcloud host; drive from a Mac", done.stderr)

    def test_no_seed_key_is_6_with_or_without_python(self):
        for path in (self.no_python, self.python):
            done = self.run_launcher(path)
            self.assertEqual(done.returncode, 6, (path, done.stderr))
            self.assertIn(f"no seed key at {self.seed}", done.stderr)
            self.assertIn("this machine is not a driver", done.stderr)
        elsewhere = self.tmp / "elsewhere.json"
        self.give_seed()                            # the default exists, the one named does not
        done = self.run_launcher(self.no_python, DEVCLOUD_SEED_FILE=str(elsewhere))
        self.assertEqual(done.returncode, 6, done.stderr)
        self.assertIn(f"no seed key at {elsewhere}", done.stderr)

    def test_a_seed_key_without_python_is_1(self):
        self.give_seed()
        done = self.run_launcher(self.no_python)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("Python 3.11", done.stderr)

    def test_a_seed_named_with_a_trailing_slash_or_dot_is_the_same_file(self):
        self.give_seed()
        for spelled in (f"{self.seed}/", f"{self.seed}/.", f"{self.seed}//./"):
            done = self.run_launcher(self.no_python, DEVCLOUD_SEED_FILE=spelled)
            self.assertEqual(done.returncode, 1, (spelled, done.stderr))
            self.assertIn("Python 3.11", done.stderr)

    @unittest.skipIf(os.geteuid() == 0, "root searches every directory")
    def test_a_seed_that_cannot_be_looked_up_is_not_missing(self):
        sealed = self.seed.parent
        sealed.mkdir(parents=True)
        sealed.chmod(0)
        self.addCleanup(sealed.chmod, 0o755)
        done = self.run_launcher(self.no_python)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("Python 3.11", done.stderr)

    @unittest.skipIf(os.geteuid() == 0, "root searches every directory")
    def test_a_seed_that_is_a_symlink_is_never_absent(self):
        sealed = self.tmp / "sealed"
        sealed.mkdir()
        (sealed / "seed.json").write_text("{}")
        sealed.chmod(0)
        self.addCleanup(sealed.chmod, 0o755)
        self.seed.parent.mkdir(parents=True)
        for target in (sealed / "seed.json", self.tmp / "nowhere.json"):     # unreadable, dangling
            self.seed.unlink(missing_ok=True)
            self.seed.symlink_to(target)
            done = self.run_launcher(self.no_python)
            self.assertEqual(done.returncode, 1, (target, done.stderr))
            self.assertIn("Python 3.11", done.stderr)

    def test_without_home_the_seed_is_under_the_accounts_home(self):
        from driver.context import Paths
        account_seed = Paths.from_env({}).seed      # the driver's own reading
        done = self.run_launcher(self.no_python, home=False)
        if account_seed.exists():
            self.assertEqual(done.returncode, 1, done.stderr)
        else:
            self.assertEqual(done.returncode, 6, done.stderr)
            self.assertIn(f"no seed key at {account_seed}", done.stderr)

    def test_6_for_a_missing_driver_with_or_without_python(self):
        self.give_seed()
        root = self.copy(driver=False)
        for path in (self.no_python, self.python):
            done = self.run_launcher(path, root=root)
            self.assertEqual(done.returncode, 6, (path, done.stderr))
            self.assertIn("has no driver", done.stderr)

    def test_a_symlinked_boot_program_is_not_refused_for_a_driver_beside_it(self):
        self.give_seed()
        root = self.copy(driver=False)
        entry = root / "boot" / "devcloud"
        entry.unlink()
        entry.symlink_to(_path.DEVCLOUD / "boot" / "devcloud")    # its realpath has a driver beside it
        done = self.run_launcher(self.no_python, root=root)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("Python 3.11", done.stderr)

    def test_a_driver_that_does_not_import_is_not_6(self):
        self.give_seed()
        root = self.copy()
        cli_py = root / "driver" / "cli.py"
        cli_py.write_text("import devcloud_missing_dependency\n" + cli_py.read_text())
        done = self.run_launcher(self.python, root=root)
        self.assertNotIn(done.returncode, (0, 6), done.stderr)
        self.assertIn("devcloud_missing_dependency", done.stderr)
        self.assertNotIn("has no driver", done.stderr)

if __name__ == "__main__":
    unittest.main()
