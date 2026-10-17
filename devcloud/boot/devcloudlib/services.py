"""The host's services (Interfaces I7) — one list, two runners. Under systemd
as PID 1 the boot program writes units `devcloud-<service>`; otherwise
`devcloud-services`, the container entrypoint's foreground, supervises the
same list: it restarts a crashed service with backoff, restarts a continuous
service when `/etc/devcloud/env` changes, reaps every orphan (it is PID 1
there), and forwards SIGTERM to every child before it exits."""

import dataclasses
import hashlib
import os
import pathlib
import signal
import subprocess
import sys
import time

from . import envfile
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
    for s in gone:
        run(["systemctl", "disable", "--now", f"devcloud-{s.name}.service"], log="services", timeout=60)
        (UNIT_DIR / f"devcloud-{s.name}.service").unlink(missing_ok=True)
    if changed or gone:
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
            run(["systemctl", verb, f"{unit}.service"], log="services", timeout=60)
        started.append(s.name)
    detail = "systemd: " + ", ".join(started)
    if gone:
        detail += "; not installed: " + ", ".join(f"{s.name} ({s.argv[0]} absent)" for s in gone)
    return detail


# --- the supervisor --------------------------------------------------------

def _digest(path):
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


class _Slot:
    def __init__(self, service, now):
        self.service = service
        self.proc = None
        self.started = 0.0
        self.failures = 0
        self.restart_now = False
        self.due = now + service.every if service.every is not None else now


class Supervisor:
    """Runs `listed` until SIGTERM or SIGINT. A user service runs as `user`
    (when the supervisor is root) with the user's clean environment plus the
    env file; a root service inherits the supervisor's environment."""

    def __init__(self, listed, env_path=ENV_PATH, user=None, poll=0.5, grace=8.0, log=None):
        self.listed = listed
        self.env_path = env_path
        self.user = user
        self.poll = poll
        self.grace = grace
        self.stopping = False
        self.log = log or (lambda message: print(f"devcloud-services: {message}", flush=True))

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
        try:
            slot.proc = subprocess.Popen(list(s.argv), env=self._env(s), start_new_session=True,
                                         stdin=subprocess.DEVNULL, **kwargs)
            slot.started = now
        except OSError as error:
            self.log(f"{s.name}: cannot start ({type(error).__name__}: {error.strerror})")
            slot.started = now
            self._schedule_after_exit(slot, now)

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
            if not self.stopping:
                if slot.service.every is None and not slot.restart_now:
                    self.log(f"{slot.service.name} exited {code}; restarting")
                elif code != 0:
                    self.log(f"{slot.service.name} exited {code}")
                self._schedule_after_exit(slot, now)
            else:
                slot.proc = None

    def _stop(self, *_):
        self.stopping = True

    def run(self):
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        now = time.monotonic()
        slots = [_Slot(s, now) for s in self.listed]
        env_digest = _digest(self.env_path)
        while not self.stopping:
            now = time.monotonic()
            self._reap(slots, now)
            digest = _digest(self.env_path)
            if digest != env_digest:
                env_digest = digest
                for slot in slots:
                    if slot.service.every is None and slot.proc:
                        self.log(f"{self.env_path} changed; restarting {slot.service.name}")
                        slot.restart_now = True
                        self._signal(slot, signal.SIGTERM)
            for slot in slots:
                if slot.proc is None and now >= slot.due and not self.stopping:
                    self._start(slot, now)
            time.sleep(self.poll)
        running = [slot for slot in slots if slot.proc]
        for slot in running:
            self._signal(slot, signal.SIGTERM)
        deadline = time.monotonic() + self.grace
        while any(slot.proc for slot in slots) and time.monotonic() < deadline:
            self._reap(slots, time.monotonic())
            time.sleep(0.05)
        for slot in slots:
            if slot.proc:
                self.log(f"{slot.service.name} ignored SIGTERM for {self.grace:.0f}s; killing it")
                self._signal(slot, signal.SIGKILL)
        self._reap(slots, time.monotonic())
        return 0


def main(user):
    interval = int(os.environ.get("DEVCLOUD_JOB_INTERVAL", INTERVAL))
    listed = [s for s in service_list(user, interval) if s.every is not None or available(s)]
    for s in service_list(user, interval):
        if s not in listed:
            print(f"devcloud-services: {s.name} not started: {s.argv[0]} absent", file=sys.stderr, flush=True)
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(f"{os.getpid()}\n")
    try:
        return Supervisor(listed, user=user).run()
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

