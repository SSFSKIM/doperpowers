"""sminos on a host (Design §8; boot step 11's sminos part).

A persistent host's enrollment is its MAWS endpoint's: step 13 provisions
the endpoint, and its first complete welcome cuts sminos over, writing
`$SMINOS_HOME/daemon/identity.json`. Step 11 enrolls nothing itself, and a
phase-1 `hub.json` left on a host makes nothing enrolled: the desk refuses
DX2.

A sminos machine — cut over (identity.json), or about to be cut over by step
13's provisioning, which needs the daemon up for the endpoint's welcome —
gets the daemon: step 11 runs `sminos daemon install` as the user (it only
writes the systemd user unit), turns lingering on so the user manager runs
with nobody logged in and from boot, reloads the user manager, and enables
and starts the unit — restarting it when its unit or the host environment
changed. Otherwise the host's projects run local-only and nothing is
installed.

A sandbox is never a sminos machine: one carrying a machine identity (a
cutover, a phase-1 enrollment, or an instance claim a daemon wrote) shares
it with the machine it came from, whose streams and writers then collide.
Step 11 refuses it rather than delete it, since the directory may be a mount
of the original's."""

import json
import os
import pathlib
import re

from . import proc
from .proc import StepError, as_user, write_file
from .services import DEVCLOUD

UNIT = "sminos-daemon.service"
# What names a machine under $SMINOS_HOME/daemon/: a phase-1 enrollment, the
# instance claim and the cutover's identity (a sandbox carrying any of them
# shares its original's). Locks and the tick's state name nothing.
IDENTITY = ("hub.json", "machine.json", "identity.json")
# The interpreter the unit pins (`daemon install` records its own).
PYTHON = "/usr/bin/python3"
ENV_PATH = "/etc/devcloud/env"
# Set when the unit, its drop-in or the host environment changed and cleared
# only once the daemon is restarted: a failed attempt leaves it for the next.
PENDING = pathlib.Path("/var/lib/devcloud/sminos-restart-pending")
DROPIN = ("# Written by devcloud (boot step 11): the host environment and output scrubber,\n"
          "# as every devcloud service has them (Design §6).\n"
          "[Service]\n"
          f"EnvironmentFile={ENV_PATH}\n")


def scrubbed_dropin(unit):
    """Wrap the single-line ExecStart that `sminos daemon install` writes.

    Keep its systemd quoting/specifiers, not shell-parse and re-quote it. Only
    the executable moves from program position (no variable expansion) to
    argument position, where a literal dollar must be doubled. The original
    unit owns output destinations, restart policy and signal handling.
    """
    section, commands = "", []
    for line in unit.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[Service]" and line.startswith("ExecStart="):
            commands.append(line.removeprefix("ExecStart="))
    if len(commands) != 1 or not commands[0]:
        raise StepError("sminos daemon unit must have one nonempty ExecStart to scrub")
    # sminos quotes its interpreter with unit_word; older installers wrote a
    # bare absolute path. Refuse other command forms rather than run raw.
    match = re.fullmatch(r'("/(?:[^"\\]|\\.)*"|/[^\s"\\]+)(\s+.+)', commands[0])
    if not match:
        raise StepError("sminos daemon unit has an unsupported ExecStart to scrub")
    command = match[1].replace("$", "$$") + match[2]
    return DROPIN + f"ExecStart=\nExecStart={DEVCLOUD} run-scrubbed -- {command}\n"


def sminos_home(user, env):
    """$SMINOS_HOME as the user's sessions resolve it."""
    for key in ("SMINOS_HOME", "DAEMON_HOME"):
        if env.get(key):
            return pathlib.Path(env[key])
    return user.home / ".claude/sminos"


def _identity(user, env):
    daemon = sminos_home(user, env) / "daemon"
    return [name for name in IDENTITY if (daemon / name).is_file()]


def cut_over(user, env):
    """Whether sminos reaches the org here: cut over to the endpoint."""
    return "identity.json" in _identity(user, env)


def check_role(user, role, env):
    """Refuses a sandbox that carries a sminos machine identity."""
    found = _identity(user, env)
    if role == "sandbox" and found:
        raise StepError(f"a sandbox is never a sminos machine, and this one carries an identity "
                        f"({', '.join(found)} in {sminos_home(user, env) / 'daemon'}), copied from an image, "
                        f"a mount or a run of `sminos daemon` here: remove it")


#: Where the doperpowers marketplace clone holds the sminos CLI, in the order
#: looked for: the sminos plugin's folder (sminos@doperpowers), then the path
#: from before sminos was a plugin of its own, which a clone not yet moved
#: still has (doperpowers keeps a shim there that forwards, through the roll).
CLI_PATHS = ("sminos/skills/sminos/scripts/sminos.py", "skills/sminos/scripts/sminos.py")


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
    for relative in CLI_PATHS:
        path = pathlib.Path(location) / relative
        if path.is_file():
            return path
    return None


#: `sminos` on every shell's PATH: the profile defines it as an alias in an
#: interactive zsh only, so a command run over SSH (`devcloud vm ssh <n> --
#: sminos …`), a login shell's included, would not find it otherwise.
LINK = pathlib.Path("/usr/local/bin/sminos")


def link_cli(user, link=LINK):
    """Points `link` at the clone's sminos launcher (beside sminos.py, which
    follows its own symlinks) and returns the launcher; when none resolves,
    links nothing and returns None. Idempotent; a moved clone moves it."""
    program = cli(user)
    launcher = program.parent / "sminos" if program is not None else None
    if launcher is None or not launcher.is_file():
        return None
    link = pathlib.Path(link)
    if link.is_symlink() and os.readlink(link) == str(launcher):
        return launcher
    temporary = link.with_name(f".{link.name}.devcloud")
    temporary.unlink(missing_ok=True)
    os.symlink(launcher, temporary)
    os.replace(temporary, link)
    return launcher


def _read(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def converge(user, role, env, env_changed, run=proc.run, pending=PENDING, provisions=False):
    """Step 11's sminos part; returns its status detail. `env` is the host
    environment (/etc/devcloud/env); `env_changed`, whether this run changed it;
    `pending`, the root-owned flag that carries an owed restart across runs;
    `provisions`, whether step 13 provisions this host's endpoint."""
    if role == "sandbox":
        return "sminos: a sandbox, not a sminos machine"
    if not (cut_over(user, env) or provisions):
        return "sminos: not enrolled, local-only"
    program = cli(user)
    if program is None:
        raise StepError("this host is a sminos machine (cut over or provisioning its endpoint), but the "
                        "doperpowers marketplace clone that holds sminos is absent "
                        "(~/.claude/plugins/known_marketplaces.json)")
    # The default user unit directory: the user manager does not read
    # /etc/devcloud/env, so a profile's XDG_CONFIG_HOME would hide the unit from it.
    install_env = {k: v for k, v in user.env(env).items() if k != "XDG_CONFIG_HOME"}
    units = user.home / ".config/systemd/user"
    unit, dropin = units / UNIT, units / f"{UNIT}.d" / "devcloud.conf"
    pending = pathlib.Path(pending)
    if env_changed:
        # Recorded before anything here can fail: the next run sees the
        # environment unchanged and would owe nothing.
        write_file(pending, "", mode=0o644, dir_mode=0o755)
    before = (_read(unit), _read(dropin))
    run([PYTHON, str(program), "daemon", "install"], user=user, env=install_env, log="services", timeout=120)
    if _read(unit) is None:
        raise StepError(f"sminos daemon install wrote no {unit}")
    wrapped = scrubbed_dropin(unit.read_text())
    as_user(user, lambda: write_file(dropin, wrapped, mode=0o644, dir_mode=0o755))
    if (_read(unit), _read(dropin)) != before:
        write_file(pending, "", mode=0o644, dir_mode=0o755)

    user_env = proc.start_user_manager(user, install_env, log="services", run=run)

    def systemctl(*args):
        run(["systemctl", "--user", *args], user=user, env=user_env, log="services", timeout=60)
    systemctl("daemon-reload")
    systemctl("enable", UNIT)
    verb = "restart" if pending.exists() else "start"
    systemctl(verb, UNIT)
    pending.unlink(missing_ok=True)
    return f"sminos daemon: {UNIT} enabled and {'restarted' if verb == 'restart' else 'running'}, lingering"
