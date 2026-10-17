import pathlib
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

import _path  # noqa: F401
from devcloudlib import services
from devcloudlib.proc import User

BOOT = pathlib.Path(__file__).resolve().parents[2] / "boot"
USER = User(name="dev", uid=1001, gid=1001, home=pathlib.Path("/Users/dev"))


class ListTest(unittest.TestCase):
    def test_the_three_services_of_i7(self):
        listed = services.service_list(USER)
        self.assertEqual([s.name for s in listed], ["pull-config", "refresh-secrets", "session-mirror"])
        pull, refresh, ship = listed
        self.assertEqual((pull.every, pull.as_user), (1800, False))
        self.assertEqual((refresh.every, refresh.as_user), (1800, False))
        self.assertEqual((ship.every, ship.as_user), (None, True))
        self.assertEqual(ship.argv, ("/Users/dev/.claude/tools/session-mirror", "ship"))

    def test_systemd_units_are_named_devcloud_service(self):
        units = services.units(services.service_list(USER), USER)
        self.assertEqual(sorted(units), [
            "devcloud-pull-config.service", "devcloud-pull-config.timer",
            "devcloud-refresh-secrets.service", "devcloud-refresh-secrets.timer",
            "devcloud-session-mirror.service",
        ])
        ship = units["devcloud-session-mirror.service"]
        for line in ("User=dev", "EnvironmentFile=/etc/devcloud/env", "Restart=always",
                     "ExecStart=/Users/dev/.claude/tools/session-mirror ship", "WantedBy=multi-user.target"):
            self.assertIn(line + "\n", ship)
        self.assertIn("OnUnitActiveSec=1800s\n", units["devcloud-pull-config.timer"])
        self.assertIn("Type=oneshot\n", units["devcloud-pull-config.service"])
        self.assertNotIn("User=", units["devcloud-pull-config.service"])


def supervise(tmp, specs, env_text=""):
    """Starts the supervisor in a child process over `specs`: (name, script, every)."""
    env_file = tmp / "env"
    env_file.write_text(env_text)
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(BOOT)!r})
        from devcloudlib import services
        listed = [services.Service(name=n, argv=("sh", "-c", "exec 2>/dev/null; " + s), as_user=True, every=e,
                                   description=n)
                  for n, s, e in {specs!r}]
        supervisor = services.Supervisor(listed, env_path={str(env_file)!r}, user=None, poll=0.1, grace=3,
                                         log=lambda message: None)
        sys.exit(supervisor.run())
    """)
    return subprocess.Popen([sys.executable, "-c", code], cwd=tmp)


def wait_for(predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.proc = None

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()

    def lines(self, name):
        path = self.tmp / name
        return path.read_text().splitlines() if path.exists() else []

    def test_forwards_sigterm_to_every_child_and_waits_for_it(self):
        script = 'trap "echo term >> $PWD/$0.log; exit 0" TERM; echo up >> $PWD/$0.log; while :; do sleep 0.05; done'
        self.proc = supervise(self.tmp, [("a", script.replace("$0", "a"), None), ("b", script.replace("$0", "b"), None)])
        self.assertTrue(wait_for(lambda: self.lines("a.log") == ["up"] and self.lines("b.log") == ["up"]))
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0)
        self.assertEqual(self.lines("a.log"), ["up", "term"])
        self.assertEqual(self.lines("b.log"), ["up", "term"])

    def test_restarts_a_crashed_service_with_growing_delays(self):
        self.proc = supervise(self.tmp, [("crash", "python3 -c 'import time; print(time.time())' >> $PWD/crash.log; exit 3", None)])
        self.assertTrue(wait_for(lambda: len(self.lines("crash.log")) >= 3, timeout=8))
        times = [float(t) for t in self.lines("crash.log")[:3]]
        first, second = times[1] - times[0], times[2] - times[1]
        self.assertGreater(first, 0.8)
        self.assertGreater(second, first * 1.5)

    def test_restarts_a_continuous_service_when_the_environment_changes(self):
        script = 'echo "$GREETING" >> $PWD/env.log; exec sleep 60'
        self.proc = supervise(self.tmp, [("ship", script, None)], env_text='GREETING="hello"\n')
        self.assertTrue(wait_for(lambda: self.lines("env.log") == ["hello"]))
        (self.tmp / "env").write_text('GREETING="changed"\n')
        self.assertTrue(wait_for(lambda: self.lines("env.log") == ["hello", "changed"], timeout=5))

    def test_runs_a_periodic_job_each_interval_never_at_start(self):
        self.proc = supervise(self.tmp, [("job", "echo run >> $PWD/job.log; sleep 0.3", 1)])
        time.sleep(0.6)
        self.assertEqual(self.lines("job.log"), [])
        self.assertTrue(wait_for(lambda: len(self.lines("job.log")) >= 2, timeout=5))


if __name__ == "__main__":
    unittest.main()
