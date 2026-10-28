"""A VM's idle clock and three-day notice (§4.5).

Observe activity outside the lifecycle lock; reserve the notice under it;
scan checkouts and deliver only after releasing it.

Only activity resets the clock; a resident session waiting for a message
and the driver's noninteractive SSH probes do not. Nothing is stopped.
"""
import json
import math
import pathlib
import time

from . import notices, proc

STATE = pathlib.Path("/var/lib/devcloud/idle.json")
INTERVAL = 3 * 86400


def active(user, since, load_path="/proc/loadavg", call=proc.call):
    """Transcript writes, terminal logins, or >= 0.5 fifteen-minute load.
    An unreadable signal raises: the caller skips this check, never turns
    an unavailable activity probe into evidence that a host is idle.
    """
    for path in (user.home / ".claude/projects").rglob("*.jsonl"):
        try:
            if path.stat().st_mtime > since:
                return True
        except FileNotFoundError:  # a transcript removed during the scan
            continue
    load = float(pathlib.Path(load_path).read_text().split()[2])
    if not math.isfinite(load):
        raise ValueError("invalid load average")
    if load >= 0.5:
        return True
    code, sessions, _ = call(["loginctl", "list-sessions", "--no-legend", "--no-pager"], timeout=30)
    if code:
        raise proc.StepError("loginctl could not list sessions")
    for row in sessions.splitlines():
        if not row.strip():
            continue
        code, output, _ = call(["loginctl", "show-session", row.split()[0],
                                "--property=TTY", "--property=State"], timeout=30)
        if code:
            raise proc.StepError("loginctl could not read a session")
        properties = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        # systemd keeps a logged-out session closing while its processes
        # (for example tmux with KillUserProcesses=no) remain, TTY included.
        if properties.get("TTY") and properties.get("State") in ("active", "online"):
            return True
    return False


def read(path):
    try:
        state = json.loads(pathlib.Path(path).read_text())
        if not isinstance(state, dict):
            return None
        for key in ("active_at", "checked_at"):
            value = state.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                return None
        noticed = state.get("noticed_at")
        if noticed is not None and (type(noticed) not in (int, float) or not math.isfinite(noticed) or noticed < 0):
            return None
        return state
    except (FileNotFoundError, ValueError):
        return None


def text(d, state, current, found):
    from .lease import iso
    seconds = max(0, current - state["active_at"])
    duration = f"{int(seconds // 86400)}d {int(seconds % 86400 // 3600)}h"
    lifetime = f"lease ends at {iso(d.expires)}" if d.leased else "runs until down"
    cost = ""
    if d.created is not None and d.hourly_price is not None:
        spent = d.hourly_price * max(0, current - d.created) / 3600
        cost = f"; estimated cost so far {spent:.2f}" + (f" {d.currency}" if d.currency else "")
    unpushed = ", ".join(f"{repo} ({what})" for repo, what in found) if found else "none"
    return (f"devcloud on {d.name}: idle {duration}; last active {iso(state['active_at'])}; {lifetime}{cost}; "
            f"unpushed: {unpushed}; end it with devcloud vm down {d.name}")


def observe(user, d, path=None, now=time.time, activity=None):
    """Read the idle state and activity without holding the lifecycle lock.
    Keep the observation's start time so writes during a slow probe are
    still visible at the next check.
    """
    if d.adopted or d.kind != "vm" or d.role != "persistent":
        return None
    checked_at = now()
    state = read(path or STATE)
    is_active = state is None or (activity or active)(user, state["checked_at"])
    return state, is_active, checked_at


def reserve(d, observation, path=None, now=time.time):
    """Under the lifecycle lock, record the check and reserve any notice.
    Another tick may have updated the clock during our observation; leave
    that newer state alone. The returned snapshot is delivered unlocked.
    """
    if observation is None or d.adopted or d.kind != "vm" or d.role != "persistent":
        return None
    path = path or STATE
    before, is_active, checked_at = observation
    if read(path) != before:
        return None
    current = now()
    state = dict(before) if before is not None else {}
    owed = False
    if is_active:
        state = {"active_at": current, "noticed_at": None}
    elif current - state["active_at"] >= INTERVAL and (
            state.get("noticed_at") is None or current - state["noticed_at"] >= INTERVAL):
        state["noticed_at"] = current
        owed = True
    state["checked_at"] = checked_at
    proc.write_file(path, json.dumps(state) + "\n", mode=0o644, dir_mode=0o755)
    return (state, current) if owed else None


def send(user, d, pending, notify=None, scan=None, say=print):
    """Scan and deliver a reserved notice, without the lifecycle lock."""
    from .lease import unpushed
    state, current = pending
    found = (scan or (lambda: unpushed(user)))()
    message = text(d, state, current, found)
    (notify or (lambda message: notices.deliver(user, d, message, say=say)))(message)
