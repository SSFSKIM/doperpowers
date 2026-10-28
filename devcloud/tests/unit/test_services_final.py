"""The final review's service findings: output scrubbed as a stream (before
lines are split or cut) and under systemd too; owed restarts kept until they
happen; continuous units need a boot that made the host; a service stopped by
a reconcile is killed when it ignores SIGTERM."""

import contextlib
import io
import os
import pathlib
import selectors
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import services, steps
from devcloudlib.proc import StepError, User

BOOT = pathlib.Path(__file__).resolve().parents[2] / "boot"
MULTILINE = "made-up-first-line-Qz81\nmade-up-second-line-Lp42"
CROSSING = "Q7zKp-made-up-crossing-value-71"
SPLIT = "made-up-split-across-reads-Wx63"


def drain_through(chunks, values):
    """Feeds `chunks` through a supervisor slot's pipe, draining after each,
    and returns what the supervisor forwarded."""
    out = io.BytesIO()
    supervisor = services.Supervisor([], env_path="/nonexistent", log=lambda message: None, out=out,
                                     known=lambda: set(values))
    supervisor._refresh_known()
    slot = services._Slot(services.Service("ship", ("true",), True, None, "ship"), time.monotonic())
    read, write = os.pipe()
    os.set_blocking(read, False)
    slot.pipe = read
    supervisor.selector.register(read, selectors.EVENT_READ, slot)
    for i, chunk in enumerate(chunks):
        os.write(write, chunk)
        if i == len(chunks) - 1:
            os.close(write)
        supervisor._drain(slot)
    return out.getvalue()


class StreamScrubTest(unittest.TestCase):
    def test_a_multiline_value_is_scrubbed_whole(self):
        text = drain_through([f"key follows\n{MULTILINE}\ndone\n".encode()], [MULTILINE])
        self.assertNotIn(b"made-up-first-line", text)
        self.assertNotIn(b"made-up-second-line", text)
        self.assertIn(b"ship: [secret]\n", text)

    def test_a_value_crossing_the_line_limit_leaves_no_prefix(self):
        line = b"x" * (services.Supervisor.LINE_MAX - 5) + CROSSING.encode() + b"\n"
        text = drain_through([line], [CROSSING])
        self.assertNotIn(b"Q7zKp", text)
        self.assertTrue(text.startswith(b"ship: xxx"))

    def test_a_value_split_across_two_reads_is_scrubbed(self):
        value = SPLIT.encode()
        text = drain_through([b"start " + value[:9], value[9:] + b" end\n"], [SPLIT])
        self.assertEqual(text, b"ship: start [secret] end\n")

    def test_a_multiline_value_split_across_reads_at_its_newline(self):
        value = MULTILINE.encode()
        cut = value.index(b"\n") + 1
        text = drain_through([b"a\n" + value[:cut], value[cut:] + b"\n"], [MULTILINE])
        self.assertNotIn(b"made-up-first-line", text)
        self.assertEqual(text, b"ship: a\nship: [secret]\n")


class RunScrubbedTest(unittest.TestCase):
    """`devcloud run-scrubbed -- <command>`, the wrapper a systemd unit runs:
    the command's output reaches journald only scrubbed."""

    def test_forwards_output_scrubbed_and_the_exit_status(self):
        out = io.BytesIO()
        script = f"print('a {SPLIT}'); print('{MULTILINE.splitlines()[0]}'); raise SystemExit(4)"
        code = services.run_scrubbed([sys.executable, "-c", script], known=lambda: {SPLIT}, out=out)
        self.assertEqual(code, 4)
        self.assertEqual(out.getvalue(), f"a [secret]\n{MULTILINE.splitlines()[0]}\n".encode())

    def test_forwards_sigterm_to_the_command(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        child = (f"import signal, sys, time\n"
                 f"signal.signal(signal.SIGTERM, lambda *a: (print('final {SPLIT}', flush=True), sys.exit(0)))\n"
                 f"print('up', flush=True)\n"
                 f"while True: time.sleep(0.05)\n")
        (tmp / "child.py").write_text(child)
        code = textwrap.dedent(f"""
            import sys; sys.path.insert(0, {str(BOOT)!r})
            from devcloudlib import services
            sys.exit(services.run_scrubbed([sys.executable, {str(tmp / 'child.py')!r}], known=lambda: {{{SPLIT!r}}}))
        """)
        wrapper = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
        self.assertEqual(wrapper.stdout.readline(), b"up\n")
        wrapper.send_signal(signal.SIGTERM)
        rest, _ = wrapper.communicate(timeout=10)
        self.assertEqual(wrapper.returncode, 0)
        self.assertEqual(rest, b"final [secret]\n")

    def test_every_unit_runs_its_command_through_the_wrapper(self):
        user = User(name="dev", uid=1001, gid=1001, home=pathlib.Path("/Users/dev"))
        units = services.units(services.service_list(user), user)
        for name, text in units.items():
            if name.endswith(".service"):
                exec_start = [line for line in text.splitlines() if line.startswith("ExecStart=")]
                self.assertEqual(len(exec_start), 1, name)
                self.assertTrue(exec_start[0].startswith("ExecStart=/usr/local/bin/devcloud run-scrubbed -- "), name)


class NeedsABootTest(unittest.TestCase):
    def test_a_continuous_unit_starts_only_after_a_boot_that_made_the_host(self):
        user = User(name="dev", uid=1001, gid=1001, home=pathlib.Path("/Users/dev"))
        ship = services.units(services.service_list(user), user)["devcloud-session-mirror.service"]
        self.assertIn(f"ConditionPathExists={services.BOOTED}\n", ship)
        self.assertIn("After=network-online.target devcloud-boot.service\n", ship)

    def boot(self, outcome):
        marker = pathlib.Path(tempfile.mkdtemp()) / "booted"
        marker.write_text("")   # a previous boot's

        def run_steps(steps_, r, done=None, guard=None):
            self.assertFalse(marker.exists(), "the marker outlived the start of a boot")
            if steps_ is steps.BOOT:
                return 1 if outcome == "host failed" else 0
            return 1 if outcome == "projects failed" else 0
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(steps, "_locked", contextlib.nullcontext))
            stack.enter_context(mock.patch.object(steps.status, "reset", lambda: None))
            stack.enter_context(mock.patch.object(steps, "_run", run_steps))
            stack.enter_context(mock.patch.object(services, "BOOTED", marker))
            stack.enter_context(mock.patch.object(services, "systemd_is_init", lambda: False))
            code = steps.boot()
        return code, marker.exists()

    def test_the_boot_marks_success_on_0_or_3_and_clears_it_otherwise(self):
        self.assertEqual(self.boot("ok"), (0, True))
        self.assertEqual(self.boot("projects failed"), (3, True))
        self.assertEqual(self.boot("host failed"), (1, False))


class Recorder:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, argv, **_):
        self.calls.append(list(argv))
        if self.fail and self.fail(argv):
            self.fail = None
            raise StepError(f"{argv[0]} exited 1")


class OwedRestartTest(unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.home = tmp / "home"
        (self.home / ".claude/tools").mkdir(parents=True)
        shipper = self.home / ".claude/tools/session-mirror"
        shipper.write_text("#!/bin/sh\n")
        shipper.chmod(0o755)
        self.user = User(name="dev", uid=1001, gid=1001, home=self.home)
        self.units = tmp / "units"
        self.units.mkdir()
        self.pending = tmp / "pending"
        self.booted = tmp / "booted"
        self.booted.write_text("")             # a boot made this host
        for patcher in (mock.patch.object(services, "BOOTED", self.booted),
                        mock.patch.object(services, "SHIPPER_SEEN", tmp / "shipper-configured")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def apply(self, env_changed, run):
        return services.apply_systemd(self.user, env_changed, run=run, unit_dir=self.units, pending_dir=self.pending)

    def test_during_a_boot_the_gated_start_waits_for_the_marker_and_keeps_what_it_owes(self):
        self.apply(False, Recorder())
        ship = "devcloud-session-mirror.service"
        self.booted.unlink()                   # a boot is under way: run directly, no unit job to order after
        during = Recorder()
        self.apply(True, during)               # the environment changed: a restart is owed
        self.assertEqual(self.verbs(during, ship), [], "queued while the unit's condition would skip it")
        self.assertTrue((self.pending / ship).exists(), "the owed restart was cleared before it was queued")
        self.booted.write_text("")             # the boot made the host
        after = Recorder()
        services.start_gated(self.user, run=after, pending_dir=self.pending)
        self.assertEqual(self.verbs(after, ship), ["restart"])
        self.assertFalse((self.pending / ship).exists())

    def test_the_boot_starts_the_gated_services_once_its_marker_is_written(self):
        calls = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(steps, "_locked", contextlib.nullcontext))
            stack.enter_context(mock.patch.object(steps.status, "reset", lambda: None))
            stack.enter_context(mock.patch.object(steps, "_run", lambda steps_, r, done=None, guard=None: 0))
            stack.enter_context(mock.patch.object(steps, "Run", lambda kind: mock.Mock(user=self.user)))
            stack.enter_context(mock.patch.object(services, "systemd_is_init", lambda: True))
            stack.enter_context(mock.patch.object(services, "start_gated", lambda user, **_: calls.append(
                ("start_gated", self.booted.exists()))))
            self.booted.unlink()
            self.assertEqual(steps.boot(), 0)
        self.assertEqual(calls, [("start_gated", True)])

    def verbs(self, recorder, unit):
        return [c[2] for c in recorder.calls if c[:2] == ["systemctl", "--no-block"] and c[-1] == unit]

    def test_a_restart_a_failed_run_owed_is_made_by_the_next(self):
        self.apply(False, Recorder())                      # installed, nothing owed
        ship = "devcloud-session-mirror.service"
        failing = Recorder(fail=lambda argv: argv[:2] == ["systemctl", "enable"] and argv[-1] == ship)
        with self.assertRaises(StepError):
            self.apply(True, failing)                      # the environment changed; the run fails first
        retry = Recorder()
        self.apply(False, retry)                           # nothing changed now, but the restart is owed
        self.assertEqual(self.verbs(retry, ship), ["restart"])
        settled = Recorder()
        self.apply(False, settled)
        self.assertEqual(self.verbs(settled, ship), ["start"])

    def test_a_reload_a_failed_run_owed_is_made_by_the_next(self):
        failing = Recorder(fail=lambda argv: argv[1:] == ["daemon-reload"])
        with self.assertRaises(StepError):
            self.apply(False, failing)                     # units written, reload failed
        retry = Recorder()
        self.apply(False, retry)
        self.assertIn(["systemctl", "daemon-reload"], retry.calls)
        settled = Recorder()
        self.apply(False, settled)
        self.assertNotIn(["systemctl", "daemon-reload"], settled.calls)

    def test_sminos_still_records_its_restart_when_the_devcloud_units_fail(self):
        r = mock.Mock()
        r.env_changed = True
        r.desc.role = "persistent"
        r.user = self.user
        seen = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(steps.lease, "LOCK", pathlib.Path(tempfile.mkdtemp()) / "lock"))
            stack.enter_context(mock.patch.object(steps.status, "lifecycle", lambda: None))
            stack.enter_context(mock.patch.object(steps, "_enroll", lambda r, env: steps.sminos_host.Enrollment(
                "none", "")))
            stack.enter_context(mock.patch.object(steps, "_read_env", lambda path: {}))
            stack.enter_context(mock.patch.object(steps.sminos_host, "check_role", lambda *a: None))
            stack.enter_context(mock.patch.object(steps, "_devcloud_services", mock.Mock(
                side_effect=StepError("systemctl exited 1"))))
            stack.enter_context(mock.patch.object(
                steps.sminos_host, "converge",
                lambda user, role, env, changed, provisions=False: seen.append(changed) or "sminos: fine"))
            with self.assertRaises(StepError) as caught:
                steps.services_step(r)
        self.assertEqual(seen, [True])
        self.assertIn("systemctl exited 1", str(caught.exception))


class ReconcileStopTest(unittest.TestCase):
    """A service a reconcile stops (removed, or restarted for a new
    environment) and that ignores SIGTERM is killed after the grace."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.proc = None

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        # Killing the supervisor leaves the service it was running (it ignores
        # SIGTERM by design) orphaned and looping forever; end it by its pid.
        for pid in self.pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def start(self, desired):
        stubborn = ('trap "" TERM; echo $$ >> $PWD/pids; '
                    'while :; do sleep 0.05 & wait $!; done')
        env_file = self.tmp / "env"
        env_file.write_text('A="1"\n')
        services.write_desired(desired, self.tmp / "desired.json")
        code = textwrap.dedent(f"""
            import sys; sys.path.insert(0, {str(BOOT)!r})
            from devcloudlib import services
            listed = [services.Service("stubborn", ("sh", "-c", {stubborn!r}), True, None, "stubborn")]
            sys.exit(services.Supervisor(listed, env_path={str(env_file)!r}, poll=0.1, grace=2,
                                         log=lambda message: None,
                                         desired_path={str(self.tmp / 'desired.json')!r}).run())
        """)
        self.proc = subprocess.Popen([sys.executable, "-c", code], cwd=self.tmp, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

    def pids(self):
        path = self.tmp / "pids"
        return [int(p) for p in path.read_text().split()] if path.exists() else []

    def wait_for(self, predicate, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    @staticmethod
    def alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        stat = pathlib.Path(f"/proc/{pid}/stat")
        return not (stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] == "Z")

    def test_a_removed_service_that_ignores_sigterm_is_killed(self):
        self.start(["stubborn"])
        self.assertTrue(self.wait_for(lambda: len(self.pids()) == 1, 5))
        services.write_desired([], self.tmp / "desired.json")
        self.assertTrue(self.wait_for(lambda: not self.alive(self.pids()[0]), 8), "still running after the grace")

    def test_a_restart_for_a_new_environment_kills_a_service_that_ignores_sigterm(self):
        self.start(["stubborn"])
        self.assertTrue(self.wait_for(lambda: len(self.pids()) == 1, 5))
        (self.tmp / "env").write_text('A="2"\n')
        self.assertTrue(self.wait_for(lambda: len(self.pids()) == 2, 8), "never restarted")
        self.assertFalse(self.alive(self.pids()[0]))


if __name__ == "__main__":
    unittest.main()
