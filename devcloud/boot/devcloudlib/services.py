"""The host's services (Interfaces I7) — one list, two runners. Under systemd
as PID 1 the boot program writes units `devcloud-<service>`; otherwise
`devcloud-services`, the container entrypoint's foreground, supervises the
same list: it restarts a crashed service with backoff, restarts a continuous
service when `/etc/devcloud/env` changes, reaps every orphan (it is PID 1
there), and forwards SIGTERM to every child before it exits. Either way a
service's output is scrubbed of every value the host holds before it is passed
on: the supervisor scrubs what it forwards, and every unit runs its command
through `devcloud run-scrubbed`, so journald gets the same."""

import dataclasses
import hashlib
import json
import os
import pathlib
import selectors
import signal
import subprocess
import sys
import time

from . import envfile, redact
from .proc import SYSTEM_PATH, run

ENV_PATH = "/etc/devcloud/env"
UNIT_DIR = pathlib.Path("/etc/systemd/system")
PIDFILE = pathlib.Path("/run/devcloud/services.pid")
DEVCLOUD = "/usr/local/bin/devcloud"
INTERVAL = 1800
# The lease and enroll services' interval (Design §4.1, §10): fixed, whatever
# the jobs' interval.
LIFECYCLE_INTERVAL = 300
# Shipped disabled by the image; the boot enables it only on a spot VM (§4.2).
SPOT_UNIT = "devcloud-spot.service"
# Written by a boot that made the host (exit 0, or 3 when only projects
# failed), removed when a boot starts: a continuous unit runs only on a host
# a boot made. Under /run, so a reboot starts without it.
BOOTED = pathlib.Path("/run/devcloud/booted")
# One flag per owed systemctl action (a unit to restart, a reload), written
# before the run that owes it tries and removed once it succeeded, so a failed
# run leaves it for the next.
PENDING_DIR = pathlib.Path("/var/lib/devcloud/pending")
# Written the first time the services step finds a shipper, never removed by
# a later one: the departure's evidence that this host's configuration ships
# its sessions, kept after the shipper went and the step removed its unit.
SHIPPER_SEEN = pathlib.Path("/var/lib/devcloud/shipper-configured")


@dataclasses.dataclass(frozen=True)
class Service:
    name: str
    argv: tuple
    as_user: bool
    every: int | None    # seconds between runs; None runs continuously
    description: str


def service_list(user, interval=INTERVAL, persistent=False):
    """The host's services; a persistent host (systemd, its own machine
    identity) also runs the lease service and the deferred enrollment's."""
    lifecycle = [
        Service("lease", (DEVCLOUD, "lease", "tick"), False, LIFECYCLE_INTERVAL,
                "devcloud: the lease: warn its creator, depart at its end"),
        Service("enroll", (DEVCLOUD, "enroll"), False, LIFECYCLE_INTERVAL,
                "devcloud: finish an enrollment the desk left undecided"),
    ] if persistent else []
    return [
        Service("pull-config", (DEVCLOUD, "pull-config"), False, interval,
                "devcloud: receive the configuration repository; reconcile on a new commit"),
        Service("refresh-secrets", (DEVCLOUD, "refresh-secrets"), False, interval,
                "devcloud: materialize the profile's secrets again"),
        Service("refresh-mirrors", (DEVCLOUD, "refresh-mirrors"), False, interval,
                "devcloud: fetch the repository mirrors sandboxes clone from (persistent hosts)"),
        Service("session-mirror", (f"{user.home}/.claude/tools/session-mirror", "ship"), True, None,
                "devcloud: ship this host's sessions to the session store"),
    ] + lifecycle


def available(service):
    return os.access(service.argv[0], os.X_OK)


def systemd_is_init():
    return os.path.isdir("/run/systemd/system")


# --- systemd ---------------------------------------------------------------

def units(listed, user):
    out = {}
    for s in listed:
        unit = f"devcloud-{s.name}"
        lines = ["[Unit]", f"Description={s.description}", "Wants=network-online.target",
                 "After=network-online.target devcloud-boot.service"]
        if s.every is None:
            # Ordered after the boot and run only when it made the host: a
            # condition, not Requires=, so starting the unit from the boot's own
            # step 11 queues behind the boot rather than deadlocking on it.
            lines.append(f"ConditionPathExists={BOOTED}")
        lines += ["", "[Service]"]
        if s.as_user:
            lines += [f"User={user.name}", f"Group={user.gid}",
                      f"Environment=HOME={user.home} USER={user.name} LOGNAME={user.name} "
                      f"SHELL=/usr/bin/zsh PATH={user.home}/.local/bin:{SYSTEM_PATH}",
                      f"EnvironmentFile={ENV_PATH}", f"WorkingDirectory={user.home}"]
        lines.append(f"ExecStart={DEVCLOUD} run-scrubbed -- " + " ".join(s.argv))
        # SIGTERM to the wrapper alone, which passes it on once: the command's
        # final pass then runs under it, its output still scrubbed.
        lines.append("KillMode=mixed")
        if s.every is None:
            lines += ["Restart=always", "RestartSec=2", "RestartSteps=6", "RestartMaxDelaySec=120",
                      "TimeoutStopSec=30", "", "[Install]", "WantedBy=multi-user.target"]
        else:
            lines += ["Type=oneshot", "TimeoutStartSec=30min"]
        out[f"{unit}.service"] = "\n".join(lines) + "\n"
        if s.every is not None:
            out[f"{unit}.timer"] = "\n".join([
                "[Unit]", f"Description={s.description} (every {s.every // 60} min)", "", "[Timer]",
                f"OnBootSec={s.every}s", f"OnUnitActiveSec={s.every}s", "RandomizedDelaySec=60", "",
                "[Install]", "WantedBy=timers.target"]) + "\n"
    return out


def admission(lifecycle):
    """What the services step may start, from the persisted lifecycle (§4.2's
    second guard): `open`; `closed` while a departure is under way or held
    (the lease service alone of the periodic ones, whose next run retries
    it); `over` once it is done (nothing)."""
    state = (lifecycle or {}).get("state")
    return "over" if state == "departed" else "closed" if state in ("departing", "held") else "open"


def apply_systemd(user, env_changed, run=run, unit_dir=UNIT_DIR, pending_dir=PENDING_DIR, persistent=False,
                  lifecycle=None, spot=False):
    """Writes the units, reloads systemd when one changed, enables and starts
    them, and restarts a continuous service whose unit or environment changed.
    What a changed file owes — the reload, a restart — is recorded before the
    first systemctl call and cleared only once done, so a run that fails
    leaves it for the next one, which would otherwise see nothing changed.
    Once a departure has started (`lifecycle`), it enables and starts no
    periodic service but the lease's, and once it is over none at all; what
    the departure disabled stays disabled. The spot unit is enabled on a spot
    VM only. Returns a status detail."""
    unit_dir, pending_dir = pathlib.Path(unit_dir), pathlib.Path(pending_dir)
    gate = admission(lifecycle)
    every = service_list(user, persistent=persistent)
    listed = [s for s in every if s.every is not None or available(s)]
    if any(s.name == "session-mirror" for s in listed):
        SHIPPER_SEEN.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        SHIPPER_SEEN.touch()
    wanted = units(listed, user)
    owed = set()
    for name, text in wanted.items():
        path = unit_dir / name
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            owed |= {"daemon-reload", name}
    gone = [s for s in every if s not in listed]
    for s in gone:
        if (unit_dir / f"devcloud-{s.name}.service").exists():
            owed.add("daemon-reload")
    if env_changed:
        owed |= {f"devcloud-{s.name}.service" for s in listed if s.every is None}
    pending_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    for name in owed:
        (pending_dir / name).touch()

    def due(name):
        return (pending_dir / name).exists()

    def done(name):
        (pending_dir / name).unlink(missing_ok=True)

    for s in gone:
        unit = unit_dir / f"devcloud-{s.name}.service"
        if unit.exists():
            run(["systemctl", "disable", "--now", unit.name], log="services", timeout=60)
            unit.unlink()
        done(unit.name)
    if due("daemon-reload"):
        run(["systemctl", "daemon-reload"], log="services", timeout=60)
        done("daemon-reload")
    started, held_back = [], []
    for s in listed:
        unit = f"devcloud-{s.name}"
        if gate == "over" or (gate == "closed" and s.every is not None and s.name != "lease"):
            held_back.append(s.name)
            continue
        if s.every is not None:
            run(["systemctl", "enable", "--now", f"{unit}.timer"], log="services", timeout=60)
            if due(f"{unit}.timer"):
                run(["systemctl", "restart", f"{unit}.timer"], log="services", timeout=60)
            done(f"{unit}.timer")
            done(f"{unit}.service")    # a oneshot job's next run reads its new unit
        else:
            run(["systemctl", "enable", f"{unit}.service"], log="services", timeout=60)
        started.append(s.name)
    if persistent and (unit_dir / SPOT_UNIT).exists():
        # Its start queued, not awaited: the unit is ordered after the boot
        # unit this runs in, so a start waited for here would never end.
        run(["systemctl", "enable", "--now", "--no-block", SPOT_UNIT] if spot
            else ["systemctl", "disable", SPOT_UNIT], log="services", timeout=60)
    if BOOTED.exists():
        start_gated(user, run=run, pending_dir=pending_dir, lifecycle=lifecycle)
    detail = "systemd: " + (", ".join(started) or "nothing")
    if held_back:
        detail += (f"; the departure has {'ended' if gate == 'over' else 'started'}: "
                   f"{', '.join(held_back)} not started")
    if persistent and spot:
        detail += f"; {SPOT_UNIT} enabled"
    if not BOOTED.exists():
        detail += f" ({', '.join(s.name for s in listed if s.every is None)} once the boot has made the host)"
    if gone:
        detail += "; not installed: " + ", ".join(f"{s.name} ({s.argv[0]} absent)" for s in gone)
    return detail


def start_gated(user, run=run, pending_dir=PENDING_DIR, lifecycle=None):
    """Queues the start of each continuous unit — a restart where one is owed,
    whose flag is cleared once it is queued. Only once the boot's marker
    exists: the units are conditioned on it, and a start queued before it is
    written is skipped by systemd (a boot run by hand has no unit job for the
    start to wait behind). Queued, not awaited: from inside the boot unit the
    start waits for the boot to end. Nothing once the departure is over."""
    if admission(lifecycle) == "over":
        return
    pending_dir = pathlib.Path(pending_dir)
    for s in service_list(user):
        if s.every is not None or not available(s):
            continue
        unit = f"devcloud-{s.name}.service"
        verb = "restart" if (pending_dir / unit).exists() else "start"
        run(["systemctl", "--no-block", verb, unit], log="services", timeout=60)
        (pending_dir / unit).unlink(missing_ok=True)


def mark_booted(ok):
    """The boot's word to the continuous units: set when it made the host."""
    if ok:
        BOOTED.parent.mkdir(mode=0o711, parents=True, exist_ok=True)
        BOOTED.write_text("")
    else:
        BOOTED.unlink(missing_ok=True)


# --- run-scrubbed ------------------------------------------------------------

def run_scrubbed(argv, known, signature=None, out=None, env=None):
    """Runs `argv`, passing its output (stdout and stderr, joined) on to `out`
    scrubbed as a stream of every value `known()` returns, the set refreshed
    whenever `signature()` changes and before any byte read is passed on.
    SIGTERM, SIGINT and SIGHUP go to the command. Returns its exit status
    (128 + the signal when a signal ended it). A systemd unit's ExecStart."""
    out = out or sys.stdout.buffer
    following = redact.Following(known, signature)
    following.refresh()
    try:
        child = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=env)
    except OSError as error:
        out.write(f"devcloud run-scrubbed: cannot start {argv[0]} ({error.strerror})\n".encode())
        out.flush()
        return 127

    def forward(sig, _frame):
        try:
            child.send_signal(sig)
        except ProcessLookupError:
            pass
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, forward)
    raw = b""
    fd = child.stdout.fileno()
    while True:
        chunk = os.read(fd, 65536)
        raw += chunk
        if raw:
            following.follow()
            passed, raw = following.known.scrub_stream(raw, final=not chunk)
            if passed:
                out.write(passed)
                out.flush()
        if not chunk:
            break
    code = child.wait()
    return code if code >= 0 else 128 - code


# --- the supervisor --------------------------------------------------------

DESIRED = pathlib.Path("/run/devcloud/services.json")


def desired_names(user):
    """The services this host should run now: the jobs, and each continuous
    service whose program the configuration holds."""
    return [s.name for s in service_list(user) if s.every is not None or available(s)]


def write_desired(names, path=DESIRED):
    """Step 11's word to a running supervisor: the services to run. The
    supervisor rereads the file when it changes, starting what it lacks and
    stopping what is no longer named."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps({"services": list(names)}) + "\n")
    os.replace(tmp, path)


def _read_desired(path):
    try:
        names = json.loads(pathlib.Path(path).read_text())["services"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return [n for n in names if isinstance(n, str)]


def _digest(path):
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


class _Slot:
    def __init__(self, service, now):
        self.service = service
        self.proc = None
        self.pipe = None
        self.raw = b""        # read, not yet scrubbed (may begin a value)
        self.pending = b""    # scrubbed, not yet a whole line
        self.kill_at = None   # when a stop a reconcile asked for turns to SIGKILL
        self.started = 0.0
        self.failures = 0
        self.restart_now = False
        self.removed = False
        self.due = now + service.every if service.every is not None else now


class Supervisor:
    """Runs the services of `listed` that the desired-state file names (all of
    them without one) until SIGTERM or SIGINT. A user service runs as `user`
    (when the supervisor is root) with the user's clean environment plus the
    env file; a root service inherits the supervisor's environment. What a
    service prints is scrubbed as a stream of each value `known()` returns,
    then forwarded line by line as `<service>: <line>`. A service a reconcile
    stops (removed, or restarted for a new environment) gets SIGTERM, then
    SIGKILL after `grace` seconds."""

    REFRESH = 30.0
    LINE_MAX = 4096

    def __init__(self, listed, env_path=ENV_PATH, user=None, poll=0.5, grace=8.0, log=None, known=None,
                 desired_path=None, out=None, known_signature=None):
        self.listed = {s.name: s for s in listed}
        self.env_path = env_path
        self.user = user
        self.poll = poll
        self.grace = grace
        self.desired_path = desired_path
        self.out = out or sys.stdout.buffer
        self.stopping = False
        self.selector = selectors.DefaultSelector()
        self.log = log or (lambda message: self._emit(b"devcloud-services: " + message.encode() + b"\n"))
        self.following = redact.Following(known or (lambda: ()), known_signature, log=lambda m: self.log(m))

    @property
    def known(self):
        return self.following.known

    def _emit(self, data):
        self.out.write(self.known.scrub(data))
        self.out.flush()

    def _refresh_known(self):
        self.following.refresh()

    def _follow_sources(self):
        self.following.follow()

    def _env(self, service):
        if not service.as_user:
            return dict(os.environ)
        base = self.user.env() if self.user else {
            k: v for k, v in os.environ.items() if k in ("HOME", "USER", "LOGNAME", "SHELL", "PATH", "LANG")}
        try:
            with open(self.env_path) as f:
                base.update(envfile.parse(f.read()))
        except FileNotFoundError:
            pass
        except ValueError as error:
            self.log(f"{self.env_path} unreadable ({error}); starting {service.name} without it")
        return base

    def _start(self, slot, now):
        s = slot.service
        kwargs = {}
        if s.as_user and self.user and os.geteuid() == 0:
            kwargs = dict(user=self.user.uid, group=self.user.gid, extra_groups=[], cwd=str(self.user.home))
        read, write = os.pipe()
        try:
            slot.proc = subprocess.Popen(list(s.argv), env=self._env(s), start_new_session=True,
                                         stdin=subprocess.DEVNULL, stdout=write, stderr=write, **kwargs)
            slot.started = now
            slot.kill_at = None
        except OSError as error:
            os.close(read)
            self.log(f"{s.name}: cannot start ({type(error).__name__}: {error.strerror})")
            slot.started = now
            self._schedule_after_exit(slot, now)
            return
        finally:
            os.close(write)
        os.set_blocking(read, False)
        slot.pipe = read
        self.selector.register(read, selectors.EVENT_READ, slot)

    def _drain(self, slot, final=False):
        """Forwards what the slot's pipe holds, line by line; at EOF (or
        `final`) the rest, and the pipe is closed. The one path every
        forwarded byte takes: the known values are brought up to date after
        the bytes are read, and the bytes are scrubbed as a stream — before
        they are split into lines, prefixed or cut — so a value spanning
        lines, reads or the line limit is caught whole."""
        eof = False
        while True:
            try:
                chunk = os.read(slot.pipe, 65536)
            except BlockingIOError:
                break
            if not chunk:
                eof = True
                break
            slot.raw += chunk
        if slot.raw:
            self._follow_sources()
            scrubbed, slot.raw = self.known.scrub_stream(slot.raw, final=eof or final)
            slot.pending += scrubbed
        *lines, slot.pending = slot.pending.split(b"\n")
        if len(slot.pending) > self.LINE_MAX:
            lines.append(slot.pending)
            slot.pending = b""
        if (eof or final) and slot.pending:
            lines.append(slot.pending)
            slot.pending = b""
        prefix = slot.service.name.encode() + b": "
        for line in lines:
            self._emit(prefix + line[:self.LINE_MAX] + b"\n")
        if eof or final:
            self.selector.unregister(slot.pipe)
            os.close(slot.pipe)
            slot.pipe = None

    def _schedule_after_exit(self, slot, now):
        """When a service runs next: a job after its interval; a continuous
        service at once after a deliberate restart, else after 1, 2, 4 ... 60 s,
        the count starting over once a run lasted a minute."""
        s = slot.service
        slot.proc = None
        if s.every is not None:
            slot.due = now + s.every
        elif slot.restart_now:
            slot.restart_now = False
            slot.failures = 0
            slot.due = now
        else:
            if now - slot.started > 60:
                slot.failures = 0
            slot.failures += 1
            slot.due = now + min(60.0, 2.0 ** (slot.failures - 1))

    def _signal(self, slot, sig):
        try:
            os.killpg(slot.proc.pid, sig)
        except ProcessLookupError:
            pass

    def _reap(self, slots, now):
        by_pid = {slot.proc.pid: slot for slot in slots if slot.proc}
        while True:
            try:
                pid, wait_status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            slot = by_pid.get(pid)
            if slot is None:
                continue   # an orphan this process adopted as PID 1
            code = os.waitstatus_to_exitcode(wait_status)
            slot.proc.returncode = code
            if slot.pipe is not None:
                self._drain(slot, final=True)
            if self.stopping or slot.removed:
                slot.proc = None
                continue
            if slot.service.every is None and not slot.restart_now:
                self.log(f"{slot.service.name} exited {code}; restarting")
            elif code != 0:
                self.log(f"{slot.service.name} exited {code}")
            self._schedule_after_exit(slot, now)

    def _reconcile(self, slots, now):
        """Brings the slots in line with the desired-state file."""
        names = _read_desired(self.desired_path) if self.desired_path else None
        wanted = set(self.listed) if names is None else {n for n in names if n in self.listed}
        for slot in slots:
            if slot.service.name not in wanted and not slot.removed:
                slot.removed = True
                if slot.proc:
                    self.log(f"{slot.service.name} is no longer wanted; stopping it")
                    self._terminate(slot, now)
        have = {slot.service.name for slot in slots if not slot.removed}
        for name in self.listed:
            if name in wanted and name not in have:
                if any(slot.service.name == name and slot.proc for slot in slots):
                    continue   # still stopping; started again once it is gone
                slots.append(_Slot(self.listed[name], now))
        slots[:] = [slot for slot in slots if not (slot.removed and slot.proc is None and slot.pipe is None)]

    def _terminate(self, slot, now):
        """SIGTERM now, SIGKILL once the grace has passed (see _enforce)."""
        self._signal(slot, signal.SIGTERM)
        if slot.kill_at is None:
            slot.kill_at = now + self.grace

    def _enforce(self, slots, now):
        for slot in slots:
            if slot.proc and slot.kill_at is not None and now >= slot.kill_at:
                self.log(f"{slot.service.name} ignored SIGTERM for {self.grace:.0f}s; killing it")
                self._signal(slot, signal.SIGKILL)
                slot.kill_at = None

    def _stop(self, *_):
        self.stopping = True

    def run(self):
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        now = time.monotonic()
        slots = []
        self._refresh_known()
        refreshed = now
        env_digest = _digest(self.env_path)
        desired_digest = object()
        while not self.stopping:
            now = time.monotonic()
            self._reap(slots, now)
            digest = _digest(self.desired_path) if self.desired_path else None
            if digest != desired_digest:
                desired_digest = digest
                self._refresh_known()
                refreshed = now
            self._reconcile(slots, now)
            digest = _digest(self.env_path)
            if digest != env_digest:
                env_digest = digest
                self._refresh_known()
                refreshed = now
                for slot in slots:
                    if slot.service.every is None and slot.proc and not slot.removed:
                        self.log(f"{self.env_path} changed; restarting {slot.service.name}")
                        slot.restart_now = True
                        self._terminate(slot, now)
            self._enforce(slots, now)
            if now - refreshed > self.REFRESH:
                self._refresh_known()
                refreshed = now
            for slot in slots:
                if slot.proc is None and not slot.removed and now >= slot.due and not self.stopping:
                    self._start(slot, now)
            ready = self.selector.select(timeout=self.poll) if self.selector.get_map() else ()
            for key, _ in ready:
                if key.data.pipe is not None:
                    self._drain(key.data)
            if not self.selector.get_map():
                time.sleep(self.poll)
        for slot in slots:
            if slot.proc:
                self._signal(slot, signal.SIGTERM)
        deadline = time.monotonic() + self.grace
        while any(slot.proc for slot in slots) and time.monotonic() < deadline:
            self._reap(slots, time.monotonic())
            ready = self.selector.select(timeout=0.05) if self.selector.get_map() else ()
            for key, _ in ready:
                if key.data.pipe is not None:
                    self._drain(key.data)
            if not self.selector.get_map():
                time.sleep(0.05)
        for slot in slots:
            if slot.proc:
                self.log(f"{slot.service.name} ignored SIGTERM for {self.grace:.0f}s; killing it")
                self._signal(slot, signal.SIGKILL)
        self._reap(slots, time.monotonic())
        for slot in slots:
            if slot.pipe is not None:
                self._drain(slot, final=True)
        return 0


def main(user):
    interval = int(os.environ.get("DEVCLOUD_JOB_INTERVAL", INTERVAL))
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    if not DESIRED.exists():
        write_desired(desired_names(user))
    PIDFILE.write_text(f"{os.getpid()}\n")
    try:
        return Supervisor(service_list(user, interval), user=user, desired_path=DESIRED,
                          known=lambda: redact.host_values(user, env_path=ENV_PATH),
                          known_signature=lambda: redact.host_signature(user, env_path=ENV_PATH)).run()
    finally:
        PIDFILE.unlink(missing_ok=True)


def supervisor_running():
    """The supervisor's pid when one runs (its pidfile can outlive it across a
    container restart, where another program may hold the same pid)."""
    try:
        pid = int(PIDFILE.read_text())
        cmdline = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return None
    return pid if b"devcloud-services" in cmdline else None

