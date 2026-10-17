"""The host's services (Interfaces I7) — one list, two runners. Under systemd
as PID 1 the boot program writes units `devcloud-<service>`; otherwise
`devcloud-services`, the container entrypoint's foreground, supervises the
same list: it restarts a crashed service with backoff, restarts a continuous
service when `/etc/devcloud/env` changes, reaps every orphan (it is PID 1
there), and forwards SIGTERM to every child before it exits."""

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


@dataclasses.dataclass(frozen=True)
class Service:
    name: str
    argv: tuple
    as_user: bool
    every: int | None    # seconds between runs; None runs continuously
    description: str


def service_list(user, interval=INTERVAL):
    return [
        Service("pull-config", (DEVCLOUD, "pull-config"), False, interval,
                "devcloud: receive the configuration repository; reconcile on a new commit"),
        Service("refresh-secrets", (DEVCLOUD, "refresh-secrets"), False, interval,
                "devcloud: materialize the profile's secrets again"),
        Service("session-mirror", (f"{user.home}/.claude/tools/session-mirror", "ship"), True, None,
                "devcloud: ship this host's sessions to the session store"),
    ]


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
                 "After=network-online.target devcloud-boot.service", "", "[Service]"]
        if s.as_user:
            lines += [f"User={user.name}", f"Group={user.gid}",
                      f"Environment=HOME={user.home} USER={user.name} LOGNAME={user.name} "
                      f"SHELL=/usr/bin/zsh PATH={user.home}/.local/bin:{SYSTEM_PATH}",
                      f"EnvironmentFile={ENV_PATH}", f"WorkingDirectory={user.home}"]
        lines.append("ExecStart=" + " ".join(s.argv))
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


def apply_systemd(user, env_changed):
    """Writes the units, reloads systemd when one changed, enables and starts
    them, and restarts a continuous service whose unit or environment changed.
    Returns a status detail."""
    listed = [s for s in service_list(user) if s.every is not None or available(s)]
    wanted = units(listed, user)
    changed = set()
    for name, text in wanted.items():
        path = UNIT_DIR / name
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            changed.add(name)
    gone = [s for s in service_list(user) if s not in listed]
    removed = False
    for s in gone:
        unit = UNIT_DIR / f"devcloud-{s.name}.service"
        if unit.exists():
            run(["systemctl", "disable", "--now", unit.name], log="services", timeout=60)
            unit.unlink()
            removed = True
    if changed or removed:
        run(["systemctl", "daemon-reload"], log="services", timeout=60)
    started = []
    for s in listed:
        unit = f"devcloud-{s.name}"
        if s.every is not None:
            run(["systemctl", "enable", "--now", f"{unit}.timer"], log="services", timeout=60)
            if f"{unit}.timer" in changed:
                run(["systemctl", "restart", f"{unit}.timer"], log="services", timeout=60)
        else:
            verb = "restart" if env_changed or f"{unit}.service" in changed else "start"
            run(["systemctl", "enable", f"{unit}.service"], log="services", timeout=60)
            # Queued, not awaited: the unit is ordered after devcloud-boot.service
            # (so a reboot starts it after the boot), and the boot is the caller.
            run(["systemctl", "--no-block", verb, f"{unit}.service"], log="services", timeout=60)
        started.append(s.name)
    detail = "systemd: " + ", ".join(started)
    if gone:
        detail += "; not installed: " + ", ".join(f"{s.name} ({s.argv[0]} absent)" for s in gone)
    return detail


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
        self.pending = b""
        self.started = 0.0
        self.failures = 0
        self.restart_now = False
        self.removed = False
        self.due = now + service.every if service.every is not None else now


class Supervisor:
    """Runs the services of `listed` that the desired-state file names (all of
    them without one) until SIGTERM or SIGINT. A user service runs as `user`
    (when the supervisor is root) with the user's clean environment plus the
    env file; a root service inherits the supervisor's environment. Every
    line a service prints is forwarded as `<service>: <line>`, each value
    `known()` returns scrubbed out first."""

    REFRESH = 30.0
    LINE_MAX = 4096

    def __init__(self, listed, env_path=ENV_PATH, user=None, poll=0.5, grace=8.0, log=None, known=None,
                 desired_path=None, out=None, known_signature=None):
        self.listed = {s.name: s for s in listed}
        self.env_path = env_path
        self.user = user
        self.poll = poll
        self.grace = grace
        self.known_source = known or (lambda: ())
        self.known_signature = known_signature
        self.signature = None
        self.known = redact.Known()
        self.desired_path = desired_path
        self.out = out or sys.stdout.buffer
        self.stopping = False
        self.selector = selectors.DefaultSelector()
        self.log = log or (lambda message: self._emit(b"devcloud-services: " + message.encode() + b"\n"))

    def _emit(self, data):
        self.out.write(self.known.scrub(data))
        self.out.flush()

    def _refresh_known(self):
        """Adds the host's current values to every value known before: a
        credential rotated away is still what an old process may print."""
        try:
            self.known.update(self.known_source())
        except Exception as error:  # noqa: BLE001 — keep the set rather than stop supervising
            self.log(f"cannot read the host's values ({type(error).__name__}); keeping the set known so far")

    def _follow_sources(self):
        """Refreshes the known values when their sources changed on disk, so a
        just-rotated credential is known before the next line is forwarded."""
        if self.known_signature is None:
            return
        try:
            signature = self.known_signature()
        except Exception:  # noqa: BLE001 — refresh rather than trust a signature we cannot read
            signature = object()
        if signature != self.signature:
            self.signature = signature
            self._refresh_known()

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
        the bytes are read and before any is emitted, so a credential rotated
        while they waited in the pipe is already known."""
        eof = False
        while True:
            try:
                chunk = os.read(slot.pipe, 65536)
            except BlockingIOError:
                break
            if not chunk:
                eof = True
                break
            slot.pending += chunk
        *lines, slot.pending = slot.pending.split(b"\n")
        if len(slot.pending) > self.LINE_MAX:
            lines.append(slot.pending)
            slot.pending = b""
        if (eof or final) and slot.pending:
            lines.append(slot.pending)
            slot.pending = b""
        if lines:
            self._follow_sources()
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
                    self._signal(slot, signal.SIGTERM)
        have = {slot.service.name for slot in slots if not slot.removed}
        for name in self.listed:
            if name in wanted and name not in have:
                if any(slot.service.name == name and slot.proc for slot in slots):
                    continue   # still stopping; started again once it is gone
                slots.append(_Slot(self.listed[name], now))
        slots[:] = [slot for slot in slots if not (slot.removed and slot.proc is None and slot.pipe is None)]

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
                        self._signal(slot, signal.SIGTERM)
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

