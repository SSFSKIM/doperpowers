"""A VM's idle clock and three-day notice (§4.5), run under the lease lock.

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
        code, tty, _ = call(["loginctl", "show-session", row.split()[0], "--property=TTY", "--value"], timeout=30)
        if code:
            raise proc.StepError("loginctl could not read a session")
        if tty.strip():
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
    return (f"{d.name} has been idle {duration}; last active {iso(state['active_at'])}; {lifetime}{cost}; "
            f"unpushed: {unpushed}; end it with devcloud vm down {d.name}")


def tick(user, d, path=None, now=time.time, activity=active, notify=None, scan=None, say=print):
    if d.adopted or d.kind != "vm" or d.role != "persistent":
        return
    from .lease import unpushed
    path = path or STATE
    current = now()
    state = read(path)
    if state is None or activity(user, state["checked_at"]):
        state = {"active_at": current, "noticed_at": None}
    elif current - state["active_at"] >= INTERVAL and (
            state.get("noticed_at") is None or current - state["noticed_at"] >= INTERVAL):
        found = (scan or (lambda: unpushed(user)))()
        message = text(d, state, current, found)
        (notify or (lambda message: notices.deliver(user, d, message, say=say)))(message)
        state["noticed_at"] = current
    state["checked_at"] = current
    proc.write_file(path, json.dumps(state) + "\n", mode=0o644, dir_mode=0o755)
