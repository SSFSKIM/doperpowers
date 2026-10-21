"""sminos on a host (Design §8; boot step 11's sminos part).

A persistent host is a sminos machine once it is enrolled (`sminos hub
enroll`), which leaves its identity in `$SMINOS_HOME/daemon/hub.json`. A
host enrolls itself, without a person, when its descriptor names the desk's
provisioning key (`DEVCLOUD_SMINOS_SECRET`) or a driver left a one-time code
in `/etc/devcloud/enroll-code` (`enroll`, the driver's §10 and I15): step 11
asks the desk first (`sminos hub check`) and enrolls only on its 1 (not
enrolled here) or 3 (rejected: `--replace`); on 4, undecided, it keeps the
credential it has and defers, for the `devcloud-enroll` service to finish.
The key is held in memory and handed to the enroll on stdin, never written
to disk or an argument list. Enrolled, step 11
runs `sminos daemon install` as the user (it only writes the systemd user
unit), turns lingering on so the user manager runs with nobody logged in
and from boot, reloads the user manager, and enables and starts the unit —
restarting it when its unit or the host environment changed. Unenrolled,
the host's projects run local-only and nothing is installed.

A sandbox is never a sminos machine: one carrying a machine identity (an
enrollment, or an instance claim a daemon wrote) shares it with the machine
it came from, whose streams and writers then collide. Step 11 refuses it
rather than delete it, since the directory may be a mount of the original's."""

import dataclasses
import json
import os
import pathlib
import time

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


# A one-time enrollment code a driver writes (root, 0600) when the desk has no
# provisioning key for it (§10); deleted once the desk has decided.
CODE_FILE = pathlib.Path("/etc/devcloud/enroll-code")
# I15: one `hub check` can take about 150 s.
HUB_TIMEOUT = 180
ENROLL_ATTEMPTS = 3
ENROLL_RETRY_DELAY = 10
# `hub enroll`'s exit-1 reasons that need the person, not another try.
FATAL_REASONS = ("key-revoked", "key-expired", "key-exhausted")


@dataclasses.dataclass(frozen=True)
class Enrollment:
    state: str        # none | accepted | enrolled | deferred
    detail: str


def hub_json(user, env):
    return sminos_home(user, env) / "daemon/hub.json"


def enroll(user, desc, env, fetch_key, call=proc.call, code_file=CODE_FILE, ledger_add=lambda path: None,
           sleep=time.sleep):
    """Step 11's enrollment (§10's `hub check` table, I15's `hub enroll`
    exits). `fetch_key(secret_id)` returns the provisioning key as text;
    `ledger_add(path)` lists hub.json before an enroll writes it. Raises
    StepError where the table fails the step."""
    code_file = pathlib.Path(code_file)
    has_code = code_file.exists()
    if desc.role == "sandbox" or not (desc.sminos_secret or has_code):
        return Enrollment("none", "")
    program = cli(user)
    if program is None:
        raise StepError("this host enrolls at the desk, but the doperpowers marketplace clone that holds sminos is "
                        "absent (~/.claude/plugins/known_marketplaces.json)")
    hub_env = {k: v for k, v in user.env(env).items() if k != "XDG_CONFIG_HOME"}
    check, _, err = call([PYTHON, str(program), "hub", "check"], user=user, env=hub_env, log="services",
                         timeout=HUB_TIMEOUT, cwd=str(user.home))
    if check == 124:
        check = 4        # no answer within the bound: as undecided
    if check == 0:
        code_file.unlink(missing_ok=True)
        return Enrollment("accepted", "the desk accepts this machine's credential")
    if check == 4:
        return Enrollment("deferred", "the desk is undecided (sminos hub check 4); devcloud-enroll asks again")
    if check not in (1, 3):
        raise StepError(f"sminos hub check exited {check}" + (f": {err}" if err else "")
                        + (" (a sminos older than the desk's provisioning keys)" if check == 2 else ""))
    replace = check == 3
    if has_code:
        secret, how = code_file.read_text().strip(), "the one-time code"
        code_file.unlink()          # the desk has decided: the code is spent whatever the enroll does
    else:
        secret, how = fetch_key(desc.sminos_secret), f"the provisioning key {desc.sminos_secret}"
    if not secret:
        raise StepError(f"{how} is empty")
    proc.KNOWN.add(secret)
    ledger_add(hub_json(user, env))
    argv = [PYTHON, str(program), "hub", "enroll", "--name", desc.name] + (["--replace"] if replace else [])
    reason = ""
    for attempt in range(1, ENROLL_ATTEMPTS + 1):
        code, _, err = call(argv, user=user, env=hub_env, log="services", input=secret + "\n",
                            timeout=HUB_TIMEOUT, cwd=str(user.home))
        if code == 0:
            return Enrollment("enrolled", f"enrolled as {desc.name} with {how}"
                              + (" (--replace: the desk had rejected the old credential)" if replace else ""))
        reason = err or f"exit {code}"
        if code == 3:
            raise StepError(f"the desk refused the name {desc.name}: taken ({reason})")
        if code == 2:
            raise StepError(f"sminos hub enroll exited 2 ({reason})")
        if code == 1 and any(fatal in reason for fatal in FATAL_REASONS):
            raise StepError(f"the desk refused {how} ({reason}): the person issues another")
        if attempt < ENROLL_ATTEMPTS:
            sleep(ENROLL_RETRY_DELAY)
    raise StepError(f"sminos hub enroll failed {ENROLL_ATTEMPTS} times ({reason})")


def owe_restart(pending=None):
    """A new enrollment owes the running daemon a restart, to load its credential."""
    write_file(pending or PENDING, "", mode=0o644, dir_mode=0o755)


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
    pending = pathlib.Path(pending)
    if env_changed:
        # Recorded before anything here can fail: the next run sees the
        # environment unchanged and would owe nothing.
        write_file(pending, "", mode=0o644, dir_mode=0o755)
    before = (_read(unit), _read(dropin))
    run([PYTHON, str(program), "daemon", "install"], user=user, env=install_env, log="services", timeout=120)
    as_user(user, lambda: write_file(dropin, DROPIN, mode=0o644, dir_mode=0o755))
    if _read(unit) is None:
        raise StepError(f"sminos daemon install wrote no {unit}")
    if (_read(unit), _read(dropin)) != before:
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
