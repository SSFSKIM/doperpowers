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
    def test_the_services_of_i7(self):
        listed = services.service_list(USER)
        self.assertEqual([s.name for s in listed],
                         ["pull-config", "refresh-secrets", "refresh-mirrors", "session-mirror"])
        pull, refresh, mirrors, ship = listed
        self.assertEqual((pull.every, pull.as_user), (1800, False))
        self.assertEqual((refresh.every, refresh.as_user), (1800, False))
        self.assertEqual((mirrors.every, mirrors.as_user, mirrors.argv),
                         (1800, False, ("/usr/local/bin/devcloud", "refresh-mirrors")))
        self.assertEqual((ship.every, ship.as_user), (None, True))
        self.assertEqual(ship.argv, ("/Users/dev/.claude/tools/session-mirror", "ship"))

    def test_systemd_units_are_named_devcloud_service(self):
        units = services.units(services.service_list(USER), USER)
        self.assertEqual(sorted(units), [
            "devcloud-pull-config.service", "devcloud-pull-config.timer",
            "devcloud-refresh-mirrors.service", "devcloud-refresh-mirrors.timer",
            "devcloud-refresh-secrets.service", "devcloud-refresh-secrets.timer",
            "devcloud-session-mirror.service",
        ])
        ship = units["devcloud-session-mirror.service"]
        for line in ("User=dev", "EnvironmentFile=/etc/devcloud/env", "Restart=always",
                     "ExecStart=/usr/local/bin/devcloud run-scrubbed -- /Users/dev/.claude/tools/session-mirror ship", "WantedBy=multi-user.target"):
            self.assertIn(line + "\n", ship)
        self.assertIn("OnUnitActiveSec=1800s\n", units["devcloud-pull-config.timer"])
        self.assertIn("Type=oneshot\n", units["devcloud-pull-config.service"])
        self.assertNotIn("User=", units["devcloud-pull-config.service"])


SECRET = "made-up-service-secret-81Qz"


def supervise(tmp, specs, env_text="", desired=None, stdout=None, known=None, signature="None"):
    """Starts the supervisor in a child process over `specs`: (name, script,
    every). With `desired`, the desired-state file names the services to run;
    `known` and `signature` are Python expressions for its value source and
    the source's change signature."""
    env_file = tmp / "env"
    env_file.write_text(env_text)
    desired_file = tmp / "desired.json"
    if desired is not None:
        services.write_desired(desired, desired_file)
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(BOOT)!r})
        import os
        from devcloudlib import envfile, services
        listed = [services.Service(name=n, argv=("sh", "-c", s), as_user=True, every=e, description=n)
                  for n, s, e in {specs!r}]
        supervisor = services.Supervisor(listed, env_path={str(env_file)!r}, user=None, poll=0.1, grace=3,
                                         log=lambda message: None, known={known or "lambda: {" + repr(SECRET) + "}"},
                                         known_signature={signature},
                                         desired_path={str(desired_file) if desired is not None else None!r})
        sys.exit(supervisor.run())
    """)
    return subprocess.Popen([sys.executable, "-c", code], cwd=tmp, stdout=stdout or subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
        # SIGTERM, so the supervisor stops its services: each runs in a session
        # of its own, which a SIGKILL of the supervisor leaves running forever.
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
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

    def test_forwards_service_output_with_known_values_scrubbed(self):
        script = f'echo "out {SECRET}"; echo "err {SECRET}" >&2; exec sleep 60'
        self.proc = supervise(self.tmp, [("talk", script, None)], stdout=subprocess.PIPE)
        time.sleep(1.0)
        self.proc.send_signal(signal.SIGTERM)
        out, _ = self.proc.communicate(timeout=5)
        text = out.decode()
        self.assertNotIn(SECRET, text)
        self.assertIn("talk: out [secret]", text)
        self.assertIn("talk: err [secret]", text)

    def test_a_rotated_env_credential_printed_on_sigterm_stays_scrubbed(self):
        old, new = "made-up-old-credential-41", "made-up-new-credential-42"
        script = 'trap "echo \\"bye $GREETING\\"; exit 0" TERM; echo "hello $GREETING"; while :; do sleep 0.05; done'
        known = f"lambda: {{envfile.parse(open({str(self.tmp / 'env')!r}).read()).get('GREETING', '')}}"
        self.proc = supervise(self.tmp, [("ship", script, None)], env_text=f'GREETING="{old}"\n',
                              stdout=subprocess.PIPE, known=known)
        time.sleep(1.0)
        (self.tmp / "env").write_text(f'GREETING="{new}"\n')
        time.sleep(1.5)
        self.proc.send_signal(signal.SIGTERM)
        out, _ = self.proc.communicate(timeout=5)
        text = out.decode()
        self.assertIn("ship: bye [secret]", text)
        self.assertNotIn(old, text)
        self.assertNotIn(new, text)

    def test_a_just_rotated_file_credential_is_scrubbed_from_the_first_line_that_prints_it(self):
        cred = self.tmp / "cred"
        cred.write_text("made-up-first-credential-51")
        script = f'while :; do echo "using $(cat {cred})"; sleep 0.05; done'
        known = f"lambda: {{open({str(cred)!r}).read().strip()}}"
        signature = f"lambda: os.stat({str(cred)!r}).st_mtime_ns"
        self.proc = supervise(self.tmp, [("ship", script, None)], stdout=subprocess.PIPE, known=known,
                              signature=signature)
        time.sleep(1.0)
        cred.write_text("made-up-second-credential-52")
        time.sleep(1.0)
        self.proc.send_signal(signal.SIGTERM)
        out, _ = self.proc.communicate(timeout=5)
        text = out.decode()
        self.assertIn("ship: using [secret]", text)
        self.assertNotIn("made-up-first-credential-51", text)
        self.assertNotIn("made-up-second-credential-52", text)

    def test_adds_and_removes_services_as_the_desired_list_changes(self):
        script = 'trap "echo term >> $PWD/$0.log; exit 0" TERM; echo start >> $PWD/$0.log; while :; do sleep 0.05; done'
        specs = [("a", script.replace("$0", "a"), None), ("b", script.replace("$0", "b"), None)]
        self.proc = supervise(self.tmp, specs, desired=["a"])
        self.assertTrue(wait_for(lambda: self.lines("a.log") == ["start"]))
        time.sleep(0.5)
        self.assertEqual(self.lines("b.log"), [])
        services.write_desired(["a", "b"], self.tmp / "desired.json")
        self.assertTrue(wait_for(lambda: self.lines("b.log") == ["start"]))
        services.write_desired(["b"], self.tmp / "desired.json")
        self.assertTrue(wait_for(lambda: self.lines("a.log") == ["start", "term"]))
        time.sleep(2.5)
        self.assertEqual(self.lines("a.log"), ["start", "term"], "a removed service is not restarted")
        self.assertEqual(self.lines("b.log"), ["start"])

    def test_runs_a_periodic_job_each_interval_never_at_start(self):
        self.proc = supervise(self.tmp, [("job", "echo run >> $PWD/job.log; sleep 0.3", 1)])
        time.sleep(0.6)
        self.assertEqual(self.lines("job.log"), [])
        self.assertTrue(wait_for(lambda: len(self.lines("job.log")) >= 2, timeout=5))



class DrainFreshnessTest(unittest.TestCase):
    """A credential rotated between the supervisor's freshness check and its
    read of a pipe must still be scrubbed: the drain checks again after it
    has the bytes and before it emits them."""

    def test_a_value_rotated_between_check_and_read_is_scrubbed(self):
        import io
        import os
        import selectors
        tmp = pathlib.Path(tempfile.mkdtemp())
        cred = tmp / "cred"
        cred.write_text("made-up-before-rotation-61")
        out = io.BytesIO()
        supervisor = services.Supervisor(
            [], env_path=str(tmp / "env"), log=lambda message: None, out=out,
            known=lambda: {cred.read_text()},
            known_signature=lambda: (cred.stat().st_ino, cred.stat().st_mtime_ns, cred.stat().st_size))
        slot = services._Slot(services.Service("ship", ("true",), True, None, "ship"), time.monotonic())
        read, write = os.pipe()
        os.set_blocking(read, False)
        slot.pipe = read
        supervisor.selector.register(read, selectors.EVENT_READ, slot)
        os.write(write, b"using made-up-before-rotation-61\n")         # output queued
        supervisor._follow_sources()                                    # the freshness check
        rotated = tmp / ".cred.new"                                     # the rotation
        rotated.write_text("made-up-after-rotation-62")
        rotated.replace(cred)
        os.write(write, b"using made-up-after-rotation-62\n")          # the new value appended
        os.close(write)
        supervisor._drain(slot)                                         # the read and the emit
        text = out.getvalue().decode()
        self.assertEqual(text, "ship: using [secret]\nship: using [secret]\n")


if __name__ == "__main__":
    unittest.main()
