"""sminos on a host (Design §8; boot step 11's sminos part).

A persistent host is a sminos machine once the person enrolls it (`sminos
hub enroll`, a human step: the code carries the organization's key), which
leaves its identity in `$SMINOS_HOME/daemon/hub.json`. Enrolled, step 11
runs `sminos daemon install` as the user (it only writes the systemd user
unit), turns lingering on so the user manager runs with nobody logged in
and from boot, reloads the user manager, and enables and starts the unit —
restarting it when its unit or the host environment changed. Unenrolled,
the host's projects run local-only and nothing is installed.

A sandbox is never a sminos machine: one carrying a machine identity (an
enrollment, or an instance claim a daemon wrote) shares it with the machine
it came from, whose streams and writers then collide. Step 11 refuses it
rather than delete it, since the directory may be a mount of the original's."""

import json
import pathlib

from . import proc
from .proc import StepError, as_user, write_file

UNIT = "sminos-daemon.service"
# What names a machine under $SMINOS_HOME/daemon/: the enrollment and the
# instance claim. Locks and the tick's state name nothing.
IDENTITY = ("hub.json", "machine.json")
# The interpreter the unit pins (`daemon install` records its own).
PYTHON = "/usr/bin/python3"
ENV_PATH = "/etc/devcloud/env"
# Set when the unit, its drop-in or the host environment changed and cleared
# only once the daemon is restarted: a failed attempt leaves it for the next.
PENDING = pathlib.Path("/var/lib/devcloud/sminos-restart-pending")
DROPIN = ("# Written by devcloud (boot step 11): the host environment, as every devcloud\n"
          "# service has it (Design §6).\n"
          "[Service]\n"
          f"EnvironmentFile={ENV_PATH}\n")


def sminos_home(user, env):
    """$SMINOS_HOME as the user's sessions resolve it."""
    for key in ("SMINOS_HOME", "DAEMON_HOME"):
        if env.get(key):
            return pathlib.Path(env[key])
    return user.home / ".claude/sminos"


def _identity(user, env):
    daemon = sminos_home(user, env) / "daemon"
    return [name for name in IDENTITY if (daemon / name).is_file()]


def check_role(user, role, env):
    """Refuses a sandbox that carries a sminos machine identity."""
    found = _identity(user, env)
    if role == "sandbox" and found:
        raise StepError(f"a sandbox is never a sminos machine, and this one carries an identity "
                        f"({', '.join(found)} in {sminos_home(user, env) / 'daemon'}), copied from an image, "
                        f"a mount or a run of `sminos daemon` here: remove it")


def cli(user):
    """The doperpowers marketplace clone's sminos.py (the path `daemon
    install` keeps across plugin updates), or None."""
    known = user.home / ".claude/plugins/known_marketplaces.json"
    try:
        location = json.loads(known.read_text())["doperpowers"]["installLocation"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(location, str) or not location:
        return None
    path = pathlib.Path(location) / "skills/sminos/scripts/sminos.py"
    return path if path.is_file() else None


def _read(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def converge(user, role, env, env_changed, run=proc.run, pending=PENDING):
    """Step 11's sminos part; returns its status detail. `env` is the host
    environment (/etc/devcloud/env); `env_changed`, whether this run changed it;
    `pending`, the root-owned flag that carries an owed restart across runs."""
    if role == "sandbox":
        return "sminos: a sandbox, not a sminos machine"
    if "hub.json" not in _identity(user, env):
        return "sminos: not enrolled, local-only"
    program = cli(user)
    if program is None:
        raise StepError("this host is enrolled at a sminos hub, but the doperpowers marketplace clone that holds "
                        "sminos is absent (~/.claude/plugins/known_marketplaces.json)")
    # The default user unit directory: the user manager does not read
    # /etc/devcloud/env, so a profile's XDG_CONFIG_HOME would hide the unit from it.
    install_env = {k: v for k, v in user.env(env).items() if k != "XDG_CONFIG_HOME"}
    units = user.home / ".config/systemd/user"
    unit, dropin = units / UNIT, units / f"{UNIT}.d" / "devcloud.conf"
    before = (_read(unit), _read(dropin))
    run([PYTHON, str(program), "daemon", "install"], user=user, env=install_env, log="services", timeout=120)
    as_user(user, lambda: write_file(dropin, DROPIN, mode=0o644, dir_mode=0o755))
    if _read(unit) is None:
        raise StepError(f"sminos daemon install wrote no {unit}")
    pending = pathlib.Path(pending)
    if (_read(unit), _read(dropin)) != before or env_changed:
        write_file(pending, "", mode=0o644, dir_mode=0o755)

    run(["loginctl", "enable-linger", user.name], log="services", timeout=60)
    # Started (and waited for) here: lingering starts the user manager, but
    # not necessarily before the next call needs it.
    run(["systemctl", "start", f"user@{user.uid}.service"], log="services", timeout=120)
    user_env = dict(install_env, XDG_RUNTIME_DIR=f"/run/user/{user.uid}")

    def systemctl(*args):
        run(["systemctl", "--user", *args], user=user, env=user_env, log="services", timeout=60)
    systemctl("daemon-reload")
    systemctl("enable", UNIT)
    verb = "restart" if pending.exists() else "start"
    systemctl(verb, UNIT)
    pending.unlink(missing_ok=True)
    return f"sminos daemon: {UNIT} enabled and {'restarted' if verb == 'restart' else 'running'}, lingering"
