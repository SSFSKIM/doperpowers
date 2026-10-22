"""The departure and the release (the driver's Design §4.2, §6.5), played on a
stand-in host: its `claude` processes, its commands, its clock. Every command
goes through one recorder, which also takes the lines the departure prints, so
the order of everything a run did is one list."""

import json
import os
import pathlib
import pwd
import signal
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from devcloudlib import departure, ledger, nodekind, proc, redact, status, tsapi
from devcloudlib.proc import StepError, User

NOW = 1_792_000_000
CLIENT = "tskey-client-kmadeup1CNTRL-made-up-secret"
EXPIRED, LATER = NOW - 60, NOW + 3600
PERIODIC = ("pull-config", "refresh-secrets", "refresh-mirrors", "enroll")


class World:
    """The host as the departure sees it."""

    def __init__(self):
        self.events = []            # ("run", argv, who) | ("call", argv, who) | ("say", line) | ("kill", pid, sig)
        self.procs = set()          # live `claude` pids
        self.stubborn = set()       # pids that ignore SIGTERM
        self.ships = []             # each ship's outcome, in order: True, False, or "spawn" (ok, then a session)
        self.calls = {}             # an argv's last word -> (exit, stderr) for `call`
        self.failing = {}           # an argv's first words -> message: `run` raises StepError
        self.clock = 0.0
        self.next_pid = 4000
        self.node = None            # the node tailscaled holds, {"ID": …}, for a stateful `tailscale status`

    def spawn(self, stubborn=False):
        self.next_pid += 1
        self.procs.add(self.next_pid)
        if stubborn:
            self.stubborn.add(self.next_pid)
        return self.next_pid

    def run(self, argv, *, user=None, log=None, timeout=None, **_):
        argv = list(argv)
        self.events.append(("run", argv, user.name if user else "root"))
        for prefix, message in self.failing.items():
            if tuple(argv[:len(prefix)]) == prefix:
                raise StepError(message)
        if argv == ["tailscale", "logout"] and self.node is not None:
            self.node = {}
        if argv[-2:] == ["ship", "--once"]:
            outcome = self.ships.pop(0) if self.ships else True
            if outcome == "spawn":
                self.spawn()
            elif outcome is False:
                raise StepError("session-mirror ship exited 1 (log /var/log/devcloud/lifecycle.log)")

    def call(self, argv, *, user=None, log=None, timeout=None, **_):
        self.events.append(("call", list(argv), user.name if user else "root"))
        if list(argv) == ["tailscale", "status", "--json"] and self.node is not None:
            return 0, json.dumps({"BackendState": "Running" if self.node else "NeedsLogin", "Self": self.node}), ""
        return self.calls.get(argv[-1], (0, "", ""))

    def runs(self):
        return [e[1] for e in self.events if e[0] in ("run", "call")]

    def index(self, predicate):
        for i, event in enumerate(self.events):
            if predicate(event):
                return i
        raise AssertionError("no such event")


class StandIn(departure.Host):
    world: World = None

    def claude_pids(self):
        return sorted(self.world.procs)

    def alive(self, pid):
        return pid in self.world.procs

    def kill(self, pid, sig):
        self.world.events.append(("kill", pid, sig))
        if sig == signal.SIGKILL or pid not in self.world.stubborn:
            self.world.procs.discard(pid)

    def say(self, line):
        self.world.events.append(("say", line))

    def user_env(self):
        return self.user.env()

    def preempted(self):
        return self.world.preempted

    def ts_client(self, d):
        self.world.events.append(("ts-client", d.ts_secret))
        if self.world.client_fails:
            raise StepError(f"{d.ts_secret}: HTTP 403")
        return CLIENT


class FakeApi:
    """The Tailscale API as tsapi's callers see it; its calls go into the
    world's events, in order with everything else."""

    def __init__(self, world, scopes=("auth_keys", "devices:core")):
        self.world = world
        self.scopes = list(scopes)
        self.delete_fails = 0

    def token(self, secret):
        self.world.events.append(("api", "token", secret == CLIENT))
        return tsapi.Token("made-up-access-token", self.scopes)

    def delete_node(self, tok, node_id):
        self.world.events.append(("api", "delete", node_id))
        if self.delete_fails:
            self.delete_fails -= 1
            raise StepError("HTTP 500")
        return "removed"


class DepartureBase(unittest.TestCase):
    adopted = False

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-depart-"))
        me = pwd.getpwuid(os.getuid())
        self.home = self.tmp / "home"
        self.user = User(name=me.pw_name, uid=me.pw_uid, gid=me.pw_gid, home=self.home)
        self.world = World()
        self.world.preempted = False
        self.world.client_fails = False
        self.api = FakeApi(self.world)
        for patch in (mock.patch.object(tsapi, "token", self.api.token),
                      mock.patch.object(tsapi, "delete_node", self.api.delete_node)):
            patch.start()
            self.addCleanup(patch.stop)
        self.units = self.tmp / "units"
        self.units.mkdir()
        for name in ("pull-config", "refresh-secrets", "refresh-mirrors", "enroll", "lease"):
            (self.units / f"devcloud-{name}.service").write_text("")
            (self.units / f"devcloud-{name}.timer").write_text("")
        for name in ("devcloud-session-mirror.service", "devcloud-boot.service", "devcloud-spot.service"):
            (self.units / name).write_text("")
        (self.units / "devcloud-boot.service.d").mkdir()
        (self.units / "devcloud-boot.service.d/stand-ins.conf").write_text("")
        (self.units / "sshd.service").write_text("")
        # Enrolled, with the sminos CLI in the marketplace clone and its daemon's user unit.
        clone = self.home / ".claude/plugins/marketplaces/doperpowers"
        cli = clone / "sminos/skills/sminos/scripts/sminos.py"
        cli.parent.mkdir(parents=True)
        cli.write_text("")
        (self.home / ".claude/plugins/known_marketplaces.json").write_text(
            json.dumps({"doperpowers": {"installLocation": str(clone)}}))
        (self.home / ".claude/sminos/daemon").mkdir(parents=True)
        (self.home / ".claude/sminos/daemon/hub.json").write_text("{}\n")
        unit = self.home / ".config/systemd/user/sminos-daemon.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("")
        tools = self.home / ".claude/tools"
        tools.mkdir()
        (tools / "session-mirror").write_text("#!/bin/sh\n")
        (tools / "session-mirror").chmod(0o755)
        self.cli = cli
        self.write_descriptor(EXPIRED)

    def write_descriptor(self, expires):
        lines = ["DEVCLOUD_NAME=dc-build-7f3a", "DEVCLOUD_KIND=vm", "DEVCLOUD_ROLE=persistent",
                 "DEVCLOUD_TAILSCALE=join", "DEVCLOUD_TS_SECRET=tailscale-client",
                 "DEVCLOUD_SEED=file:/etc/devcloud/seed/key.json", "DEVCLOUD_SM_PROJECT=example-project",
                 "DEVCLOUD_CONFIG_REPO=https://github.com/example/config.git",
                 "DEVCLOUD_CONFIG_TOKEN_SECRET=config-token"]
        if expires is not None:
            lines.append(f"DEVCLOUD_EXPIRES={expires}")
        if self.adopted:
            lines.append("DEVCLOUD_ADOPTED=1")
        (self.tmp / "boot.env").write_text("\n".join(lines) + "\n")

    def host(self, **over):
        world = self.world
        paths = dict(status_path=self.tmp / "status.json", ledger_path=self.tmp / "credentials.ledger",
                     desc_path=self.tmp / "boot.env", lock_path=self.tmp / "lifecycle.lock",
                     adopt_dir=self.tmp / "adopt", unit_dir=self.units, inbound_nft=self.tmp / "inbound.nft",
                     shipper_seen=self.tmp / "shipper-configured", state_dir=self.tmp / "state")
        paths.update(over)
        host = StandIn(user=self.user, run=world.run, call=world.call, now=lambda: NOW,
                       monotonic=lambda: world.clock, sleep=lambda s: setattr(world, "clock", world.clock + s),
                       **paths)
        host.world = world
        return host

    def lifecycle(self):
        return status.lifecycle(self.tmp / "status.json")

    def leave_event(self):
        return lambda e: e[0] == "call" and e[1][-2:] == ["hub", "leave"]

    def assert_held(self, code, reason):
        self.assertEqual(code, departure.HELD)
        record = self.lifecycle()
        self.assertEqual((record["state"], record["detail"]), ("held", f"held ({reason})"))
        runs = self.world.runs()
        self.assertNotIn(["tailscale", "logout"], runs)
        self.assertFalse(any(r[-2:] == ["hub", "leave"] for r in runs), "left the desk after a hold")
        self.assertNotIn(["systemctl", "poweroff"], runs)
        self.assertNotIn(("say", departure.READY), self.world.events)


class DepartTest(DepartureBase):
    def test_refuses_while_the_lease_is_not_over_and_runs_nothing(self):
        for expires in (LATER, None):
            with self.subTest(expires=expires):
                self.write_descriptor(expires)
                self.assertEqual(departure.depart(self.host()), departure.NOT_OVER)
                self.assertEqual(self.world.runs(), [])
                self.assertIsNone(self.lifecycle())

    def test_force_departs_whatever_the_lease(self):
        self.write_descriptor(LATER)
        self.assertEqual(departure.depart(self.host(), force=True, no_poweroff=True), departure.DONE)
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_the_order_closes_admission_ends_sessions_ships_leaves_and_logs_out(self):
        first, second = self.world.spawn(), self.world.spawn()
        self.assertEqual(departure.depart(self.host()), departure.DONE)
        runs = self.world.runs()
        timers = [r for r in runs if r[:3] == ["systemctl", "disable", "--now"]]
        self.assertEqual(sorted(t[3] for t in timers), sorted(f"devcloud-{n}.timer" for n in PERIODIC),
                         "every periodic timer but the lease's, and only those")
        daemon = ("run", ["systemctl", "--user", "disable", "--now", "sminos-daemon.service"], self.user.name)
        self.assertIn(daemon, self.world.events, "the daemon disabled as the user")
        w = self.world
        disabled = w.index(lambda e: e == daemon)
        killed = w.index(lambda e: e[0] == "kill")
        stop_ship = w.index(lambda e: e[0] == "run" and e[1] == ["systemctl", "stop", "devcloud-session-mirror.service"])
        ship = w.index(lambda e: e[0] == "run" and e[1][-2:] == ["ship", "--once"])
        leave = w.index(self.leave_event())
        ready = w.index(lambda e: e == ("say", departure.READY))
        logout = w.index(lambda e: e[0] == "run" and e[1] == ["tailscale", "logout"])
        stop = w.index(lambda e: e[0] == "run" and e[1][:2] == ["systemctl", "stop"] and "devcloud-lease.timer" in e[1])
        poweroff = w.index(lambda e: e[0] == "run" and e[1] == ["systemctl", "poweroff"])
        last_timer = max(w.index(lambda e, t=t: e[0] == "run" and e[1] == t) for t in timers)
        order = [last_timer, disabled, killed, stop_ship, ship, leave, ready, logout, stop, poweroff]
        self.assertEqual(order, sorted(order))
        self.assertEqual(ready + 1, logout, "the ready line comes just before the logout")
        self.assertEqual(w.events[ship][2], self.user.name, "the ship runs as the user")
        self.assertEqual(w.events[leave][2], self.user.name)
        self.assertEqual(self.world.procs, set())
        self.assertEqual({e[1] for e in w.events if e[0] == "kill"}, {first, second})
        stopped = w.events[stop][1]
        self.assertIn("devcloud-lease.service", stopped)
        self.assertNotIn("devcloud-depart.service", stopped, "the transient unit stops itself")
        record = self.lifecycle()
        self.assertEqual(record["state"], "departed")
        self.assertEqual([s["name"] for s in record["steps"]],
                         ["close-admission", "end-sessions", "stop-shipper", "ship", "leave", "logout",
                          "remove-node", "stop-services", "poweroff"])

    def test_a_session_that_ignores_sigterm_is_killed_after_30_seconds(self):
        pid = self.world.spawn(stubborn=True)
        departure.depart(self.host(), no_poweroff=True)
        kills = [e for e in self.world.events if e[0] == "kill"]
        self.assertEqual(kills, [("kill", pid, signal.SIGTERM), ("kill", pid, signal.SIGKILL)])
        self.assertGreaterEqual(self.world.clock, 30)

    def test_a_hung_or_failing_step_does_not_stop_the_next(self):
        self.world.calls["leave"] = (124, "", "timed out after 180s")
        self.world.failing[("systemctl", "disable", "--now", "devcloud-pull-config.timer")] = "systemctl exited 1"
        self.assertEqual(departure.depart(self.host(), no_poweroff=True), departure.DONE)
        steps = {s["name"]: s["state"] for s in self.lifecycle()["steps"]}
        self.assertEqual((steps["close-admission"], steps["leave"], steps["logout"]), ("failed", "failed", "ok"))
        self.assertIn(["tailscale", "logout"], self.world.runs())
        self.assertIn(["systemctl", "disable", "--now", "devcloud-refresh-secrets.timer"], self.world.runs(),
                      "one timer's failure stopped the others")

    def test_a_failed_logout_still_departs_the_vm(self):
        """The VM is deleted next, and its node is ephemeral: the coordination
        server removes it once it is offline (§4.1)."""
        self.world.failing[("tailscale", "logout")] = "tailscale exited 1"
        self.assertEqual(departure.depart(self.host(), no_poweroff=True), departure.DONE)
        steps = {s["name"]: s["state"] for s in self.lifecycle()["steps"]}
        self.assertEqual((steps["logout"], steps["stop-services"]), ("failed", "ok"))
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_the_desk_not_answering_the_leave_goes_on(self):
        self.world.calls["leave"] = (1, "", "sminos: the desk did not answer")
        departure.depart(self.host(), no_poweroff=True)
        steps = {s["name"]: s for s in self.lifecycle()["steps"]}
        self.assertEqual(steps["leave"]["state"], "ok")
        self.assertIn("stays in the desk's Machines until someone removes it", steps["leave"]["detail"],
                      "the desk revokes nothing for being offline (H4)")

    def test_a_session_started_during_the_departure_is_ended_and_its_lines_shipped(self):
        self.world.ships = ["spawn", True]
        self.assertEqual(departure.depart(self.host(), no_poweroff=True), departure.DONE)
        ships = [r for r in self.world.runs() if r[-2:] == ["ship", "--once"]]
        self.assertEqual(len(ships), 2)
        kills = [e for e in self.world.events if e[0] == "kill"]
        self.assertEqual(len(kills), 1, "the spawned session was ended")
        last_kill = self.world.index(lambda e: e[0] == "kill")
        second_ship = max(i for i, e in enumerate(self.world.events) if e[0] == "run" and e[1][-2:] == ["ship", "--once"])
        self.assertLess(last_kill, second_ship, "shipped again after ending it")
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_sessions_that_keep_starting_hold_after_three_rounds(self):
        self.world.ships = ["spawn", "spawn", "spawn"]
        code = departure.depart(self.host())
        self.assert_held(code, "sessions keep starting")
        self.assertEqual(len([r for r in self.world.runs() if r[-2:] == ["ship", "--once"]]), 3)

    def test_a_failed_ship_holds_and_a_later_run_starts_again_with_admission_closed_again(self):
        self.world.ships = [False]
        self.assert_held(departure.depart(self.host()), "ship failed")
        first = list(self.world.events)
        self.world.events.clear()
        self.world.spawn()           # a session started while the departure was held
        self.assertEqual(departure.depart(self.host(), no_poweroff=True), departure.DONE)
        runs = self.world.runs()
        self.assertEqual(runs[0][:3], ["systemctl", "disable", "--now"], "step 0 re-applied first")
        self.assertIn(["systemctl", "--user", "disable", "--now", "sminos-daemon.service"], runs)
        self.assertLess(self.world.index(lambda e: e[0] == "kill"),
                        self.world.index(lambda e: e[0] == "run" and e[1][-2:] == ["ship", "--once"]))
        self.assertEqual(self.lifecycle()["state"], "departed")
        self.assertTrue(any(e[0] == "run" and e[1][-2:] == ["ship", "--once"] for e in first))

    def test_no_hold_goes_past_a_failed_ship(self):
        self.world.ships = [False]
        self.assertEqual(departure.depart(self.host(), force=True, no_hold=True, no_poweroff=True), departure.DONE)
        self.assertIn(["tailscale", "logout"], self.world.runs())

    def test_the_hold_and_every_refusal_are_decided_before_the_ready_line(self):
        self.world.ships = [False]
        departure.depart(self.host())
        self.assertNotIn(("say", departure.READY), self.world.events)

    def test_no_poweroff_leaves_the_host_running(self):
        departure.depart(self.host(), no_poweroff=True)
        self.assertNotIn(["systemctl", "poweroff"], self.world.runs())

    def test_a_completed_departure_run_again_does_nothing(self):
        departure.depart(self.host(), no_poweroff=True)
        self.world.events.clear()
        self.assertEqual(departure.depart(self.host(), force=True), departure.DONE)
        self.assertEqual(self.world.runs(), [])

    def test_an_unenrolled_host_leaves_nothing_and_a_host_without_a_shipper_ships_nothing(self):
        (self.home / ".claude/sminos/daemon/hub.json").unlink()
        (self.home / ".claude/tools/session-mirror").unlink()
        (self.units / "devcloud-session-mirror.service").unlink()     # the configuration has none
        self.assertEqual(departure.depart(self.host(), no_poweroff=True), departure.DONE)
        steps = {s["name"]: s for s in self.lifecycle()["steps"]}
        self.assertEqual(steps["leave"]["detail"], "not enrolled")
        self.assertIn("no shipper", steps["ship"]["detail"])

    def test_a_configured_shipper_that_is_missing_or_not_executable_holds(self):
        shipper = self.home / ".claude/tools/session-mirror"
        for broken in ("not executable", "missing"):
            with self.subTest(broken=broken):
                self.world.events.clear()
                if broken == "missing":
                    shipper.unlink()
                else:
                    shipper.chmod(0o644)
                self.assert_held(departure.depart(self.host()), "ship failed")
                ship = [s for s in self.lifecycle()["steps"] if s["name"] == "ship"][-1]
                self.assertIn(broken, ship["detail"])
        self.assertEqual(departure.depart(self.host(), no_hold=True, no_poweroff=True), departure.DONE,
                         "--no-hold goes past it")

    def test_a_shipper_the_services_step_converged_away_still_holds(self):
        # The boot once found a shipper; it went, and a reconcile then removed
        # its unit. The flag the boot left is the evidence that remains.
        (self.home / ".claude/tools/session-mirror").unlink()
        (self.units / "devcloud-session-mirror.service").unlink()
        (self.tmp / "shipper-configured").write_text("")
        self.world.spawn()
        self.assert_held(departure.depart(self.host()), "ship failed")
        ship = [s for s in self.lifecycle()["steps"] if s["name"] == "ship"][-1]
        self.assertIn("missing", ship["detail"])

    def test_an_adopted_machine_is_released_not_departed(self):
        self.adopted = True
        self.write_descriptor(EXPIRED)
        self.assertEqual(departure.depart(self.host()), departure.FAILED)
        self.assertEqual(self.world.runs(), [])

    def test_the_spot_reclaim_departs_fast_only_when_reclaimed(self):
        self.write_descriptor(LATER)
        self.assertEqual(departure.depart_preempted(self.host()), departure.DONE)
        self.assertEqual(self.world.runs(), [], "an ordinary shutdown departed")
        self.world.preempted = True
        self.world.spawn(stubborn=True)
        self.world.ships = [False]
        self.assertEqual(departure.depart_preempted(self.host()), departure.DONE)
        runs = self.world.runs()
        self.assertIn(["tailscale", "logout"], runs, "a failed ship held a reclaimed VM")
        self.assertNotIn(["systemctl", "poweroff"], runs)
        self.assertLessEqual(self.world.clock, departure.PREEMPT_BUDGET, "the session wait outlasted the window")
        self.assertEqual(self.lifecycle()["state"], "departed")


class RedactionTest(DepartureBase):
    """A lifecycle command is a process of its own: it learns the host's
    secrets before any child runs, as the boot and the jobs do."""

    def test_a_childs_output_reaches_the_log_scrubbed(self):
        canary = "made-up-store-value-Zq81Lr5Tx0Kp"
        store = self.home / ".config/claude-secrets"
        store.mkdir(parents=True)
        (store / "API_KEY").write_text(canary)
        shipper = self.home / ".claude/tools/session-mirror"
        shipper.write_text(f"#!/bin/sh\necho shipping with {canary}\n")
        logs = self.tmp / "log"
        for patch in (mock.patch.object(proc, "LOG_DIR", logs), mock.patch.object(proc, "KNOWN", redact.Known())):
            patch.start()
            self.addCleanup(patch.stop)
        world_run = self.world.run

        def run(argv, **kw):
            world_run(argv, **kw)
            if argv[-2:] == ["ship", "--once"]:
                return proc.run(argv, **kw)     # the real child, its output logged
        host = self.host()
        host.run = run
        self.assertEqual(departure.depart(host, no_poweroff=True), departure.DONE)
        text = (logs / "lifecycle.log").read_text()
        self.assertIn("shipping with", text)
        self.assertNotIn(canary, text)


class ReleaseTest(DepartureBase):
    adopted = True

    def setUp(self):
        super().setUp()
        (self.units / "devcloud-inbound.service").write_text("")
        self.write_descriptor(EXPIRED)
        # Adopt saved root's keys and the login user's (who had none).
        adopt = self.tmp / "adopt"
        adopt.mkdir()
        self.saved_keys = self.home / ".ssh/authorized_keys"
        (adopt / "user.authorized_keys").write_text("ssh-ed25519 AAAAoriginal person@laptop\n")
        self.gone_keys = self.tmp / "other/.ssh/authorized_keys"
        self.gone_keys.parent.mkdir(parents=True)
        self.gone_keys.write_text("ssh-ed25519 AAAAdriver devcloud\n")
        (adopt / "keys.json").write_text(json.dumps({"keys": [
            {"path": str(self.saved_keys), "owner": self.user.name, "saved": "user.authorized_keys"},
            {"path": str(self.gone_keys), "owner": self.user.name, "saved": None}]}))
        self.saved_keys.parent.mkdir(parents=True)
        self.saved_keys.write_text("ssh-ed25519 AAAAdriver devcloud\n")
        # What devcloud wrote, listed in the ledger as each was written.
        self.led = self.tmp / "credentials.ledger"
        self.written = [self.home / ".config/claude-secrets/OLD_NAME", self.home / ".pgpass",
                        self.tmp / "root-gcloud", self.tmp / "etc-devcloud-env"]
        for path in self.written:
            if path.name == "root-gcloud":
                (path / "credentials.db").parent.mkdir(parents=True)
                (path / "credentials.db").write_text("made-up")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("made-up")
            ledger.add(path, path=self.led)
        self.kept = self.home / "notes.txt"
        self.kept.write_text("the person's own file")
        self.world.calls["devcloud"] = (0, "table inet devcloud {}", "")

    def test_refuses_while_the_lease_is_not_over_and_runs_nothing(self):
        self.write_descriptor(LATER)
        self.assertEqual(departure.release(self.host()), departure.NOT_OVER)
        self.assertEqual(self.world.runs(), [])

    def test_only_an_adopted_machine_is_released(self):
        self.adopted = False
        self.write_descriptor(EXPIRED)
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        self.assertEqual(self.world.runs(), [])

    def test_the_order_and_what_it_removes(self):
        self.world.spawn()
        self.assertEqual(departure.release(self.host()), departure.DONE)
        w = self.world
        ship = w.index(lambda e: e[0] == "run" and e[1][-2:] == ["ship", "--once"])
        leave = w.index(self.leave_event())
        table = w.index(lambda e: e[0] == "run" and e[1][:2] == ["nft", "delete"])
        ready = w.index(lambda e: e == ("say", departure.READY))
        logout = w.index(lambda e: e[0] == "run" and e[1] == ["tailscale", "logout"])
        units = w.index(lambda e: e[0] == "run" and e[1][:3] == ["systemctl", "disable", "--now"]
                        and "devcloud-boot.service" in e[1])
        self.assertEqual(sorted([ship, leave, table, ready, logout, units]), [ship, leave, table, ready, logout, units])
        self.assertEqual(w.events[table][1], ["nft", "delete", "table", "inet", "devcloud"], "only devcloud's table")
        self.assertFalse(any(r[:2] == ["nft", "flush"] for r in w.runs()))
        # Access back before the logout: the saved keys restored, a file adopt did not find removed.
        self.assertEqual(self.saved_keys.read_text(), "ssh-ed25519 AAAAoriginal person@laptop\n")
        self.assertFalse(self.gone_keys.exists())
        self.assertFalse((self.tmp / "adopt").exists())
        # devcloud's units gone, its drop-ins too; nothing else's.
        self.assertEqual(sorted(p.name for p in self.units.iterdir()), ["sshd.service"])
        self.assertNotIn("devcloud-release.service", w.events[units][1])
        # The credentials, then the ledger; the person's files and the home stay.
        for path in self.written:
            self.assertFalse(path.exists(), f"{path} survived the release")
        self.assertFalse(self.led.exists())
        self.assertEqual(self.kept.read_text(), "the person's own file")
        self.assertTrue(self.home.is_dir())
        self.assertEqual(self.lifecycle()["state"], "departed")
        self.assertEqual(self.lifecycle()["op"], "release")
        self.assertNotIn(["systemctl", "poweroff"], w.runs(), "an adopted machine keeps running")

    def test_runs_through_credential_removal_after_the_lease_services_unit_was_stopped(self):
        departure.release(self.host())
        names = [s["name"] for s in self.lifecycle()["steps"]]
        self.assertLess(names.index("remove-units"), names.index("remove-credentials"))
        self.assertEqual(self.lifecycle()["state"], "departed")
        stopped = [e[1] for e in self.world.events if e[0] == "run" and e[1][:3] == ["systemctl", "disable", "--now"]
                   and "devcloud-lease.service" in e[1]]
        self.assertTrue(stopped, "the lease service's unit was not stopped")

    @unittest.skipIf(os.geteuid() == 0, "root removes what a mode forbids")
    def test_the_ledger_stays_until_every_removal_succeeded(self):
        stuck = self.home / ".config/claude-secrets"
        stuck.chmod(0o500)          # its file cannot be removed
        self.addCleanup(stuck.chmod, 0o700)
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        self.assertTrue(self.led.exists())
        self.assertIn(str(stuck / "OLD_NAME"), ledger.entries(self.led))
        self.assertFalse((self.home / ".pgpass").exists(), "one failure stopped the other removals")
        self.assertEqual(self.lifecycle()["state"], "departing")

    def assert_access_kept(self, step):
        """A release stopped before it could cut the person off: no logout, no
        ready line, every credential and the ledger there, resumable."""
        runs = self.world.runs()
        self.assertNotIn(["tailscale", "logout"], runs)
        self.assertNotIn(("say", departure.READY), self.world.events)
        for path in self.written:
            self.assertTrue(path.exists(), f"{path} removed by a release that failed")
        self.assertTrue(self.led.exists())
        record = self.lifecycle()
        self.assertEqual((record["op"], record["state"]), ("release", "departing"))
        self.assertEqual((record["steps"][-1]["name"], record["steps"][-1]["state"]), (step, "failed"))

    def test_a_failed_key_restore_stops_before_the_logout(self):
        (self.tmp / "adopt/keys.json").write_text("not json")
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        self.assert_access_kept("restore-keys")
        self.assertFalse(any(r[:4] == ["systemctl", "disable", "--now", "devcloud-boot.service"]
                             for r in self.world.runs()), "units removed after a failed restore")

    def test_a_failed_firewall_removal_stops_before_the_logout(self):
        self.world.failing[("nft", "delete")] = "nft exited 1"
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        self.assert_access_kept("firewall")
        self.assertEqual(self.saved_keys.read_text(), "ssh-ed25519 AAAAdriver devcloud\n",
                         "went on to the keys behind a firewall still up")

    def test_a_failed_unit_removal_is_not_a_completed_release(self):
        self.world.failing[("systemctl", "disable", "--now", "devcloud-boot.service")] = "systemctl exited 1"
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        record = self.lifecycle()
        self.assertEqual(record["state"], "departing")
        self.assertEqual((record["steps"][-1]["name"], record["steps"][-1]["state"]), ("remove-units", "failed"))
        for path in self.written:
            self.assertTrue(path.exists(), "credentials removed though the units that rewrite them remain")

    def test_a_retry_before_the_logout_closes_admission_and_ships_again(self):
        manifest = self.tmp / "adopt/keys.json"
        good = manifest.read_text()
        manifest.write_text("not json")
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        # Still on the tailnet: a person logs in and starts a session meanwhile.
        manifest.write_text(good)
        session = self.world.spawn()
        self.world.events.clear()
        self.assertEqual(departure.release(self.host()), departure.DONE)
        runs = self.world.runs()
        self.assertIn(["systemctl", "--user", "disable", "--now", "sminos-daemon.service"], runs,
                      "admission not closed again")
        self.assertIn(("kill", session, signal.SIGTERM), self.world.events, "the new session was left running")
        self.assertNotIn(session, self.world.procs)
        ship = self.world.index(lambda e: e[0] == "run" and e[1][-2:] == ["ship", "--once"])
        self.assertLess(self.world.index(lambda e: e[0] == "kill"), ship)
        self.assertLess(ship, self.world.index(lambda e: e[0] == "run" and e[1] == ["tailscale", "logout"]))
        self.assertFalse(any(r[:2] == ["nft", "delete"] for r in runs), "the firewall step, done, ran again")
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_retry_before_the_logout_holds_when_its_ship_fails(self):
        manifest = self.tmp / "adopt/keys.json"
        good = manifest.read_text()
        manifest.write_text("not json")
        departure.release(self.host())
        manifest.write_text(good)
        self.world.ships = [False]
        self.world.events.clear()
        self.assert_held(departure.release(self.host()), "ship failed")
        for path in self.written:
            self.assertTrue(path.exists())

    def test_a_second_release_after_a_completed_one_does_nothing(self):
        ledger.add(self.tmp / "boot.env", path=self.led)     # the boot lists the descriptor
        self.assertEqual(departure.release(self.host()), departure.DONE)
        self.assertFalse((self.tmp / "boot.env").exists())
        self.world.events.clear()
        self.assertEqual(departure.release(self.host()), departure.DONE)
        self.assertEqual(self.world.runs(), [])

    def state(self):
        """The real layout: the status, the ledger and the shipper flag in
        devcloud's state directory, with what else the boot kept there."""
        state = self.tmp / "state"
        (state / "marketplaces/doperpowers").mkdir(parents=True)
        (state / "identity.env").write_text("DEVCLOUD_NAME=dc-build-7f3a\n")
        (state / "shipper-configured").write_text("")
        (state / "lease.json").write_text("{}\n")
        led = state / "credentials.ledger"
        for path in ledger.entries(self.led) + [str(self.tmp / "boot.env")]:
            ledger.add(path, path=led)
        self.led.unlink()
        self.led = led
        return state, self.host(status_path=state / "status.json", ledger_path=led,
                                shipper_seen=state / "shipper-configured")

    def test_a_completed_release_removes_the_state_directory(self):
        state, host = self.state()
        self.assertEqual(departure.release(host), departure.DONE)
        self.assertFalse(state.exists(), "devcloud's state directory survived the release")
        self.assertFalse((self.tmp / "boot.env").exists())
        self.assertEqual(self.kept.read_text(), "the person's own file")
        self.assertTrue(self.home.is_dir())
        self.world.events.clear()
        self.assertEqual(departure.release(host), departure.DONE, "a second release has nothing left to do")
        self.assertEqual(self.world.runs(), [])

    @unittest.skipIf(os.geteuid() == 0, "root removes what a mode forbids")
    def test_a_release_that_left_a_credential_keeps_the_state_directory(self):
        state, host = self.state()
        stuck = self.home / ".config/claude-secrets"
        stuck.chmod(0o500)
        self.addCleanup(stuck.chmod, 0o700)
        self.assertEqual(departure.release(host), departure.FAILED)
        self.assertTrue((state / "credentials.ledger").exists())
        self.assertTrue((state / "identity.env").exists())
        self.assertNotIn(["systemctl", "reset-failed", "devcloud-*"], self.world.runs())

    def test_systemd_forgets_the_removed_units_failures_at_the_end(self):
        self.assertEqual(departure.release(self.host()), departure.DONE)
        w = self.world
        units = w.index(lambda e: e[0] == "run" and e[1][:3] == ["systemctl", "disable", "--now"]
                        and "devcloud-boot.service" in e[1])
        reset = w.index(lambda e: e[0] == "call" and e[1] == ["systemctl", "reset-failed", "devcloud-*"])
        self.assertLess(units, reset)

    @unittest.skipIf(os.geteuid() == 0, "root removes what a mode forbids")
    def test_a_release_that_left_a_credential_resumes_where_it_stopped(self):
        ledger.add(self.tmp / "boot.env", path=self.led)
        stuck = self.home / ".config/claude-secrets"
        stuck.chmod(0o500)
        self.addCleanup(stuck.chmod, 0o700)
        self.write_descriptor(LATER)
        self.assertEqual(departure.release(self.host(), force=True), departure.FAILED)
        self.assertTrue((self.tmp / "boot.env").exists(), "the descriptor went before the other credentials")
        stuck.chmod(0o700)
        self.world.events.clear()
        # Run again without --force: the release under way is resumed, not refused.
        self.assertEqual(departure.release(self.host()), departure.DONE)
        runs = self.world.runs()
        self.assertFalse(any(r[-2:] == ["ship", "--once"] for r in runs), "shipped again")
        self.assertNotIn(["tailscale", "logout"], runs, "logged out again")
        self.assertFalse(any(r[:2] == ["nft", "delete"] for r in runs))
        for path in self.written + [self.tmp / "boot.env", self.led]:
            self.assertFalse(path.exists(), f"{path} survived the resumed release")
        record = self.lifecycle()
        self.assertEqual(record["state"], "departed")
        self.assertEqual([s["name"] for s in record["steps"] if s["state"] == "ok"][-1], "remove-credentials")

    def test_a_failed_logout_keeps_the_release_resumable(self):
        """An adopted machine keeps running and its node is not ephemeral: a
        release that removed everything after a failed logout would leave it
        on the tailnet with nothing of devcloud left to retry from."""
        self.world.failing[("tailscale", "logout")] = "tailscale exited 1"
        self.world.calls["--json"] = (0, json.dumps({"BackendState": "Running"}), "")
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        record = self.lifecycle()
        self.assertEqual(record["state"], "departing")
        self.assertEqual((record["steps"][-1]["name"], record["steps"][-1]["state"]), ("logout", "failed"))
        self.assertTrue((self.units / "devcloud-lease.timer").exists(), "units removed after a failed logout")
        for path in self.written:
            self.assertTrue(path.exists(), f"{path} removed after a failed logout")
        # Run again once tailscale can log out: it resumes, the logout first.
        del self.world.failing[("tailscale", "logout")]
        self.world.events.clear()
        self.assertEqual(departure.release(self.host()), departure.DONE)
        self.assertIn(["tailscale", "logout"], self.world.runs())
        for path in self.written:
            self.assertFalse(path.exists())
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_failed_logout_that_tailscale_shows_logged_out_goes_on(self):
        self.world.failing[("tailscale", "logout")] = "tailscale exited 1 (timed out)"
        self.world.calls["--json"] = (0, json.dumps({"BackendState": "NeedsLogin"}), "")
        self.assertEqual(departure.release(self.host()), departure.DONE)
        logout = next(s for s in self.lifecycle()["steps"] if s["name"] == "logout")
        self.assertEqual(logout["state"], "ok")
        self.assertIn("NeedsLogin", logout["detail"])

    def test_a_resumed_release_repeats_what_its_earlier_run_did(self):
        """The driver reads the leave's outcome from the release's output (§4.4's
        desk note): a resumed release, which skips the leave it made, repeats
        its line."""
        self.world.failing[("systemctl", "disable", "--now", "devcloud-boot.service")] = "systemctl exited 1"
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        del self.world.failing[("systemctl", "disable", "--now", "devcloud-boot.service")]
        self.world.events.clear()
        self.assertEqual(departure.release(self.host()), departure.DONE)
        said = [e[1] for e in self.world.events if e[0] == "say"]
        self.assertIn("devcloud release: leave: ok — left the desk (an earlier run)", said)
        self.assertFalse(any(r[-2:] == ["hub", "leave"] for r in self.world.runs()), "left the desk twice")

    def test_a_held_release_removes_nothing(self):
        self.world.ships = [False]
        self.assert_held(departure.release(self.host()), "ship failed")
        for path in self.written:
            self.assertTrue(path.exists())
        self.assertTrue(self.led.exists())
        self.assertFalse(any(r[:2] == ["nft", "delete"] for r in self.world.runs()))


class NodeRemovalBase(DepartureBase):
    """A host that leaves for good removes its own tailnet node when the
    logout leaves it listed (board #118): a node not known to be ephemeral,
    its id read before the logout, removed through the API right after it.
    A removal that fails is recorded and the departure completes."""

    NODE = "nHost7CNTRL"

    def setUp(self):
        super().setUp()
        self.world.node = {"ID": self.NODE}
        self.kind_path = self.tmp / "state" / "tailnet.json"

    def joined(self, ephemeral, remove=()):
        nodekind.record(ephemeral, ephemeral, nodekind.JOINED, "joined", name="dc-build-7f3a", path=self.kind_path,
                        remove=list(remove))

    def step(self, name):
        return next(s for s in self.lifecycle()["steps"] if s["name"] == name)

    def api_calls(self):
        return [e[1:] for e in self.world.events if e[0] == "api"]


class DepartNodeRemovalTest(NodeRemovalBase):
    def depart(self):
        self.write_descriptor(None)
        return departure.depart(self.host(), force=True, no_poweroff=True)

    def test_a_kept_hosts_node_is_removed_right_after_its_logout(self):
        self.joined(False)
        self.assertEqual(self.depart(), departure.DONE)
        w = self.world
        status_read = w.index(lambda e: e[0] == "call" and e[1] == ["tailscale", "status", "--json"])
        ready = w.index(lambda e: e == ("say", departure.READY))
        logout = w.index(lambda e: e[0] == "run" and e[1] == ["tailscale", "logout"])
        delete = w.index(lambda e: e == ("api", "delete", self.NODE))
        stop = w.index(lambda e: e[0] == "run" and e[1][:2] == ["systemctl", "stop"] and "devcloud-lease.timer" in e[1])
        self.assertLess(status_read, ready, "the id is read before the ready line")
        self.assertEqual(ready + 1, logout, "the ready line still comes just before the logout")
        self.assertLess(logout, delete)
        self.assertLess(delete, stop)
        self.assertEqual(self.api_calls(), [("token", True), ("delete", self.NODE)])
        self.assertEqual(self.step("remove-node")["state"], "ok")
        self.assertIn(f"{self.NODE} removed through the API", self.step("remove-node")["detail"])
        self.assertEqual(nodekind.pending(self.kind_path), [])
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_node_of_no_recorded_kind_is_removed_too(self):
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [("token", True), ("delete", self.NODE)])

    def test_an_ephemeral_node_leaves_at_its_logout_without_the_api(self):
        self.joined(True)
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [])
        self.assertNotIn(("ts-client", "tailscale-client"), self.world.events, "fetched the client for nothing")
        self.assertEqual(self.step("remove-node")["state"], "ok")
        self.assertIn("ephemeral", self.step("remove-node")["detail"])

    def test_an_old_node_a_rejoin_left_pending_is_removed_with_the_hosts_own(self):
        self.joined(True, remove=["nOld3CNTRL"])
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [("token", True), ("delete", "nOld3CNTRL")])

    def test_a_removal_that_keeps_failing_is_recorded_and_the_departure_completes(self):
        self.joined(False)
        self.api_fails(3)
        self.write_descriptor(None)
        self.assertEqual(departure.depart(self.host(), force=True), departure.DONE)
        self.assertEqual([e for e in self.api_calls() if e[0] == "delete"], [("delete", self.NODE)] * 3)
        removal = self.step("remove-node")
        self.assertEqual(removal["state"], "failed")
        self.assertIn(f"the old node {self.NODE} was not removed (HTTP 500)", removal["detail"])
        self.assertEqual(self.step("stop-services")["state"], "ok")
        self.assertIn(["systemctl", "poweroff"], self.world.runs(), "a failed removal kept the VM up")
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_client_that_cannot_be_fetched_is_recorded_and_the_departure_completes(self):
        self.joined(False)
        self.world.client_fails = True
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [])
        removal = self.step("remove-node")
        self.assertEqual(removal["state"], "failed")
        self.assertIn("HTTP 403", removal["detail"])
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_client_without_the_devices_scope_removes_nothing_and_the_departure_completes(self):
        self.joined(False)
        self.api.scopes = ["auth_keys"]
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [("token", True)])
        self.assertIn("devices:core", self.step("remove-node")["detail"])
        self.assertEqual(self.step("remove-node")["state"], "failed")

    def test_a_logout_that_failed_leaves_the_node_held_untouched(self):
        """The node is still the daemon's: never removed from under it. The
        driver removes it once the VM is deleted."""
        self.joined(False)
        self.world.failing[("tailscale", "logout")] = "tailscale exited 1"
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [])
        removal = self.step("remove-node")
        self.assertEqual(removal["state"], "failed")
        self.assertIn("still holds that node", removal["detail"])
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_status_that_cannot_be_read_before_the_logout_is_named_and_nothing_is_removed(self):
        self.joined(False)
        self.world.node = None
        self.world.calls["--json"] = (1, "", "tailscaled not running")
        self.assertEqual(self.depart(), departure.DONE)
        self.assertEqual(self.api_calls(), [])
        self.assertIn("could not be read before the logout", self.step("logout")["detail"])
        self.assertEqual(self.step("remove-node")["detail"], "no node id to remove")

    def test_the_spot_reclaim_removes_a_kept_nodes_after_its_logout(self):
        self.joined(False)
        self.world.preempted = True
        self.assertEqual(departure.depart_preempted(self.host()), departure.DONE)
        self.assertEqual(self.api_calls(), [("token", True), ("delete", self.NODE)])
        names = [s["name"] for s in self.lifecycle()["steps"]]
        self.assertEqual(names[names.index("logout") + 1], "remove-node")

    def api_fails(self, count):
        self.api.delete_fails = count


class ReleaseNodeRemovalTest(NodeRemovalBase):
    adopted = True

    def setUp(self):
        super().setUp()
        self.write_descriptor(EXPIRED)
        self.joined(False)

    def test_the_node_is_removed_after_the_logout_and_before_the_units_and_credentials(self):
        seed = self.tmp / "seed.json"
        seed.write_text("made-up")
        ledger.add(seed, path=self.tmp / "credentials.ledger")
        self.assertEqual(departure.release(self.host()), departure.DONE)
        w = self.world
        logout = w.index(lambda e: e[0] == "run" and e[1] == ["tailscale", "logout"])
        client = w.index(lambda e: e[0] == "ts-client")
        delete = w.index(lambda e: e == ("api", "delete", self.NODE))
        units = w.index(lambda e: e[0] == "run" and e[1][:3] == ["systemctl", "disable", "--now"]
                        and "devcloud-boot.service" in e[1])
        self.assertLess(logout, client)
        self.assertLess(client, delete)
        self.assertLess(delete, units, "the credentials' removal comes after the node's")
        self.assertFalse(seed.exists())
        names = [s["name"] for s in self.lifecycle()["steps"]]
        self.assertEqual(names[names.index("logout"):], ["logout", "remove-node", "remove-units",
                                                          "remove-credentials"])

    def test_a_failed_removal_does_not_stop_the_release(self):
        self.api.delete_fails = 3
        self.assertEqual(departure.release(self.host()), departure.DONE)
        self.assertEqual(self.step("remove-node")["state"], "failed")
        self.assertEqual(self.lifecycle()["state"], "departed")

    def test_a_resumed_release_retries_a_removal_that_failed(self):
        self.api.delete_fails = 3
        self.world.failing[("systemctl", "disable", "--now", "devcloud-boot.service")] = "systemctl exited 1"
        self.assertEqual(departure.release(self.host()), departure.FAILED)
        self.assertEqual(nodekind.pending(self.kind_path), [self.NODE], "the id was lost")
        del self.world.failing[("systemctl", "disable", "--now", "devcloud-boot.service")]
        self.world.events.clear()
        self.assertEqual(departure.release(self.host()), departure.DONE)
        self.assertNotIn(["tailscale", "logout"], self.world.runs(), "logged out again")
        self.assertEqual(self.api_calls(), [("token", True), ("delete", self.NODE)])


if __name__ == "__main__":
    unittest.main()
