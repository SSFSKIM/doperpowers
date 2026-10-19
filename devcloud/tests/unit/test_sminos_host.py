"""sminos on a host (Design §8, boot step 11): an enrolled persistent host
installs the sminos daemon as a systemd user unit, lingers, reloads the
user manager and enables and starts the unit; an unenrolled one stays
local-only; a sandbox is never a sminos machine. Commands go to a recording
stand-in for proc.run; `sminos daemon install` is played by writing a unit."""

import json
import os
import pathlib
import pwd
import tempfile
import unittest

import _path  # noqa: F401
from devcloudlib import sminos_host
from devcloudlib.proc import StepError, User

UNIT_TEXT = "[Service]\nExecStart=/usr/bin/python3 sminos.py daemon run\n"


class Recorder:
    """Stands in for proc.run: records each call; `daemon install` writes the unit."""

    def __init__(self, unit_path, unit_text=UNIT_TEXT, fail=None):
        self.calls = []
        self.unit_path = unit_path
        self.unit_text = unit_text
        self.fail = fail          # the first word of a command that fails, once

    def __call__(self, argv, *, user=None, env=None, log=None, timeout=None, **_):
        env = dict(env or {})
        self.calls.append({"argv": list(argv), "as": user.name if user else "root", "env": env})
        if argv[0] == self.fail:
            self.fail = None
            raise StepError(f"{argv[0]} exited 1")
        if argv[-2:] == ["daemon", "install"]:
            # As sminos does: the unit goes under $XDG_CONFIG_HOME when it is set.
            config = env.get("XDG_CONFIG_HOME")
            path = pathlib.Path(config) / "systemd/user/sminos-daemon.service" if config else self.unit_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.unit_text)

    def commands(self):
        return [(c["as"], c["argv"]) for c in self.calls]


class SminosHostTest(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-sminos-"))
        me = pwd.getpwuid(os.getuid())
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.home)
        self.unit = self.home / ".config/systemd/user/sminos-daemon.service"
        self.dropin = self.home / ".config/systemd/user/sminos-daemon.service.d/devcloud.conf"
        self.env = {"SESSION_MIRROR_HOST": "devbox-a", "PATH": f"{self.home}/bin:/usr/bin:/bin"}
        self.pending = self.home / "state/sminos-restart-pending"

    def enroll(self, home=None):
        daemon = (home or self.home / ".claude/sminos") / "daemon"
        daemon.mkdir(parents=True, exist_ok=True)
        (daemon / "hub.json").write_text('{"machine": "devbox-a"}\n')

    def marketplace(self, layout="sminos/skills/sminos/scripts/sminos.py"):
        """The doperpowers marketplace clone with the sminos CLI where `layout`
        puts it: the sminos plugin's folder (from the move of sminos into a
        plugin of its own), or, before it, doperpowers' own skill."""
        clone = self.home / ".claude/plugins/marketplaces/doperpowers"
        cli = clone / layout
        cli.parent.mkdir(parents=True)
        cli.write_text("# sminos\n")
        (self.home / ".claude/plugins/known_marketplaces.json").write_text(json.dumps(
            {"doperpowers": {"source": {"source": "github", "repo": "example/doperpowers"},
                             "installLocation": str(clone)}}))
        return cli

    def converge(self, role="persistent", env_changed=False, recorder=None):
        recorder = recorder or Recorder(self.unit)
        detail = sminos_host.converge(self.user, role, self.env, env_changed, run=recorder, pending=self.pending)
        return detail, recorder

    # --- a sandbox -----------------------------------------------------------------

    def test_a_sandbox_is_not_a_sminos_machine(self):
        sminos_host.check_role(self.user, "sandbox", self.env)
        detail, recorder = self.converge(role="sandbox")
        self.assertEqual(recorder.calls, [])
        self.assertIn("sandbox", detail)

    def test_a_sandbox_carrying_a_machine_identity_is_refused(self):
        for name in ("hub.json", "machine.json"):
            with self.subTest(name=name):
                daemon = self.home / ".claude/sminos/daemon"
                daemon.mkdir(parents=True, exist_ok=True)
                (daemon / name).write_text("{}\n")
                with self.assertRaisesRegex(StepError, f"sandbox.*{name}"):
                    sminos_host.check_role(self.user, "sandbox", self.env)
                (daemon / name).unlink()

    def test_a_sandbox_may_hold_a_daemon_directory_without_an_identity(self):
        # `sminos daemon status` makes the directory and a lock; neither names a machine.
        daemon = self.home / ".claude/sminos/daemon"
        daemon.mkdir(parents=True)
        (daemon / "run.lock").write_text("")
        sminos_host.check_role(self.user, "sandbox", self.env)

    def test_the_identity_is_looked_for_under_the_hosts_sminos_home(self):
        custom = self.home / "elsewhere/sminos"
        self.env["SMINOS_HOME"] = str(custom)
        self.enroll(home=self.home / ".claude/sminos")      # the default home, not the one in use
        sminos_host.check_role(self.user, "sandbox", self.env)
        self.enroll(home=custom)
        with self.assertRaisesRegex(StepError, "sandbox"):
            sminos_host.check_role(self.user, "sandbox", self.env)

    def test_a_persistent_host_may_carry_its_identity(self):
        self.enroll()
        sminos_host.check_role(self.user, "persistent", self.env)

    # --- a persistent host -----------------------------------------------------------

    def test_unenrolled_it_stays_local_only(self):
        self.marketplace()
        detail, recorder = self.converge()
        self.assertEqual(recorder.calls, [])
        self.assertIn("not enrolled", detail)

    def test_enrolled_without_the_sminos_cli_fails(self):
        self.enroll()
        with self.assertRaisesRegex(StepError, "enrolled.*sminos"):
            self.converge()

    def test_enrolled_it_installs_lingers_reloads_enables_and_starts_the_daemon(self):
        self.enroll()
        cli = self.marketplace()
        detail, recorder = self.converge()
        uid = str(self.user.uid)
        self.assertEqual(recorder.commands(), [
            (self.user.name, ["/usr/bin/python3", str(cli), "daemon", "install"]),
            ("root", ["loginctl", "enable-linger", self.user.name]),
            ("root", ["systemctl", "start", f"user@{uid}.service"]),
            (self.user.name, ["systemctl", "--user", "daemon-reload"]),
            (self.user.name, ["systemctl", "--user", "enable", "sminos-daemon.service"]),
            (self.user.name, ["systemctl", "--user", "restart", "sminos-daemon.service"]),
        ])
        install = recorder.calls[0]["env"]
        self.assertEqual((install["HOME"], install["PATH"], install["SESSION_MIRROR_HOST"]),
                         (str(self.home), self.env["PATH"], "devbox-a"))
        for call in recorder.calls[3:]:
            self.assertEqual(call["env"]["XDG_RUNTIME_DIR"], f"/run/user/{uid}")
        self.assertIn("EnvironmentFile=/etc/devcloud/env\n", self.dropin.read_text())
        self.assertIn("sminos daemon", detail)

    def test_the_cli_is_the_sminos_plugins_in_the_clone_then_the_retired_path(self):
        # From the move of sminos into a plugin of its own, the clone holds the
        # CLI in its sminos/ folder; a clone not yet moved holds it at the old
        # path (doperpowers' shim there forwards, through the roll), found second.
        self.assertIsNone(sminos_host.cli(self.user))
        old = self.marketplace(layout="skills/sminos/scripts/sminos.py")
        self.assertEqual(sminos_host.cli(self.user), old)
        new = self.marketplace(layout="sminos/skills/sminos/scripts/sminos.py")
        self.assertEqual(sminos_host.cli(self.user), new)

    def test_an_unchanged_unit_is_started_and_a_changed_one_or_environment_restarted(self):
        self.enroll()
        self.marketplace()
        self.converge()
        _, recorder = self.converge()
        self.assertEqual(recorder.calls[-1]["argv"], ["systemctl", "--user", "start", "sminos-daemon.service"])
        _, recorder = self.converge(env_changed=True)
        self.assertEqual(recorder.calls[-1]["argv"], ["systemctl", "--user", "restart", "sminos-daemon.service"])
        _, recorder = self.converge(recorder=Recorder(self.unit, UNIT_TEXT + "Environment=\"PATH=/new\"\n"))
        self.assertEqual(recorder.calls[-1]["argv"], ["systemctl", "--user", "restart", "sminos-daemon.service"])


    def test_a_restart_owed_by_a_failed_attempt_is_made_by_the_next(self):
        # The first attempt rewrites the unit, then lingering fails; the retry
        # finds the unit unchanged, and still owes the running daemon a restart.
        self.enroll()
        self.marketplace()
        with self.assertRaises(StepError):
            self.converge(recorder=Recorder(self.unit, fail="loginctl"))
        _, recorder = self.converge()
        self.assertEqual(recorder.calls[-1]["argv"], ["systemctl", "--user", "restart", "sminos-daemon.service"])
        _, recorder = self.converge()
        self.assertEqual(recorder.calls[-1]["argv"], ["systemctl", "--user", "start", "sminos-daemon.service"])

    def test_an_environment_change_survives_a_failed_attempt(self):
        self.enroll()
        self.marketplace()
        self.converge()
        with self.assertRaises(StepError):
            self.converge(env_changed=True, recorder=Recorder(self.unit, fail="systemctl"))
        _, recorder = self.converge(env_changed=False)
        self.assertEqual(recorder.calls[-1]["argv"], ["systemctl", "--user", "restart", "sminos-daemon.service"])

    def test_the_unit_goes_where_a_cold_started_user_manager_looks(self):
        # The user manager does not read /etc/devcloud/env, so a profile's
        # XDG_CONFIG_HOME would hide the unit from it on a cold boot.
        self.enroll()
        self.marketplace()
        self.env["XDG_CONFIG_HOME"] = str(self.home / "elsewhere")
        _, recorder = self.converge()
        self.assertNotIn("XDG_CONFIG_HOME", recorder.calls[0]["env"])
        self.assertTrue(self.unit.is_file() and self.dropin.is_file())
        self.assertFalse((self.home / "elsewhere/systemd").exists())
        for call in recorder.calls:
            self.assertNotIn("XDG_CONFIG_HOME", call["env"])


if __name__ == "__main__":
    unittest.main()
