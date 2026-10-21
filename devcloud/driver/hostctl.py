"""What the driver does on a host, over SSH: the slow path's install, the
seed and the boot's start (§3 steps 4 and 7), the wait (step 8), and the
host commands of M2 the driver consumes — `ledger add` before each credential
write, `lease set`, `unpushed`, `depart` and its ready line.

A host is reached at its public address until the tailnet attach step has
succeeded (the boot closes the public port right after it), then over the
tailnet by its name (§5)."""

import dataclasses
import io
import json
import pathlib
import shlex
import tarfile

from .compose import SEED_PATH, STAGE
from .errors import CAP, FAILED, DriverError

READY = "devcloud-depart: ready-to-logout"
BOOT_ENV = "/etc/devcloud/boot.env"
CODE_PATH = "/etc/devcloud/enroll-code"
STATUS = "/var/lib/devcloud/status.json"
SRC = "/opt/devcloud-src"
SETUP_LOG = "/var/log/devcloud-setup.log"
DEPARTURE_STARTED = ("departing", "held", "departed")


@dataclasses.dataclass(frozen=True)
class Host:
    name: str            # its tailnet name too
    alias: str           # the known_hosts key: the server, never its address
    public: str | None   # the public IPv4, for first contact


def alias(account, server_id):
    return f"devcloud-{account}-{server_id}"


# --- first contact (the public address) ---------------------------------------

def wait_ssh(ctx, address, key_alias, deadline):
    while True:
        if ctx.remote.run(address, key_alias, "true", timeout=30).code == 0:
            return
        if ctx.clock() >= deadline:
            raise DriverError(FAILED, f"SSH at {address} did not answer in time")
        ctx.sleep(5)


def wait_cloud_init(ctx, address, key_alias):
    result = ctx.remote.run(address, key_alias, "cloud-init status --wait >/dev/null 2>&1; cloud-init status",
                            timeout=900)
    if result.code not in (0, 2) or "status: done" not in result.out:
        # 2: done with recoverable errors, which cloud-init reports for a deprecated key.
        raise DriverError(FAILED, f"cloud-init did not finish cleanly ({result.out.strip() or result.code})")


def recipe_tar(plugin_dir):
    """The plugin's `image/` and `boot/` as a tar stream, without bytecode."""
    buffer = io.BytesIO()
    root = pathlib.Path(plugin_dir)
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for part in ("image", "boot"):
            tar.add(root / part, arcname=f"devcloud/{part}",
                    filter=lambda info: None if "__pycache__" in info.name or info.name.endswith(".pyc") else info)
    return buffer.getvalue()


def install_recipe(ctx, address, key_alias, build):
    """The slow path: the plugin's recipe streamed and `setup.sh` run, its
    exit checked (adopt's install path, §6.5)."""
    for key in ("DEVCLOUD_USER", "DEVCLOUD_UID", "DEVCLOUD_HOME"):
        if not build.get(key):
            raise DriverError(FAILED, f"the profile's build.env lacks {key}, which setup.sh needs")
    unpack = f"rm -rf {SRC} && mkdir -p {SRC} && tar -x -C {SRC}"
    result = ctx.remote.run(address, key_alias, unpack, input=recipe_tar(ctx.plugin), timeout=300)
    if result.code != 0:
        raise DriverError(FAILED, f"streaming the recipe failed (exit {result.code})")
    inputs = " ".join(f"{k}={shlex.quote(build[k])}" for k in ("DEVCLOUD_USER", "DEVCLOUD_UID", "DEVCLOUD_HOME"))
    setup = (f"{inputs} bash {SRC}/devcloud/image/setup.sh >{SETUP_LOG} 2>&1 "
             f"|| {{ code=$?; tail -n 30 {SETUP_LOG}; exit $code; }}")
    result = ctx.remote.run(address, key_alias, setup, timeout=3600)
    if result.code != 0:
        tail = result.out.strip().splitlines()[-1:] or [f"exit {result.code}"]
        raise DriverError(FAILED, f"setup.sh failed (exit {result.code}; {SETUP_LOG} on the host): {tail[0]}")


def deliver_seed(ctx, address, key_alias):
    """The seed key file into a root-only path, its path in the credential
    ledger first (§3 step 7, §6.5); read from its file into ssh's stdin,
    never argv, never printed."""
    ledger(ctx, address, key_alias, SEED_PATH, BOOT_ENV)
    seed_dir = str(pathlib.PurePosixPath(SEED_PATH).parent)
    command = (f"umask 077 && install -d -m 0700 {seed_dir} && cat > {SEED_PATH}.tmp && "
               f"mv {SEED_PATH}.tmp {SEED_PATH} && test -s {SEED_PATH}")
    result = ctx.remote.run(address, key_alias, command, input=ctx.paths.seed.read_bytes(), timeout=120)
    if result.code != 0:
        raise DriverError(FAILED, f"delivering the seed failed (exit {result.code})")


def ledger(ctx, target, key_alias, *paths):
    result = ctx.remote.run(target, key_alias, "devcloud ledger add " + " ".join(paths), timeout=60)
    if result.code != 0:
        raise DriverError(FAILED, f"`devcloud ledger add` failed on the host (exit {result.code})")


def start_boot(ctx, address, key_alias):
    """The staged descriptor installed as /etc/devcloud/boot.env, and the boot
    started without waiting on it."""
    command = (f"install -m 0600 -o root -g root {STAGE} {BOOT_ENV} && "
               "systemctl start --no-block devcloud-boot.service")
    result = ctx.remote.run(address, key_alias, command, timeout=120)
    if result.code != 0:
        raise DriverError(FAILED, f"starting the boot failed (exit {result.code})")


def progress(ctx, target, key_alias):
    """The boot's status file and its unit's state, or None when the host
    did not answer."""
    result = ctx.remote.run(target, key_alias, f"cat {STATUS} 2>/dev/null || echo '{{}}'; "
                            "echo; systemctl is-active devcloud-boot.service || true", timeout=60)
    if result.code != 0:
        return None
    text, _, unit = result.out.strip().rpartition("\n")
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        data = {}
    return data, unit.strip()


def deliver_code(ctx, target, key_alias, code):
    """The one-time enrollment code (`--enroll-code -`, §10) into a root-only
    file, ledgered first, then a reconcile whose step 11 enrolls with it."""
    ledger(ctx, target, key_alias, CODE_PATH)
    result = ctx.remote.run(target, key_alias, f"umask 077 && cat > {CODE_PATH}.tmp && mv {CODE_PATH}.tmp {CODE_PATH}",
                            input=code, timeout=60)
    if result.code != 0:
        raise DriverError(FAILED, f"delivering the enrollment code failed (exit {result.code})")
    return ctx.remote.run(target, key_alias, "devcloud reconcile", timeout=900)


# --- over the tailnet -----------------------------------------------------------

def reachable(ctx, host, timeout=10):
    return ctx.remote.run(host.name, host.alias, "true", timeout=timeout + 5, connect_timeout=timeout).code == 0


def lifecycle(ctx, host, user="root"):
    """The host's lifecycle state (departing, held, departed), None before a
    departure; raises when the host does not answer."""
    result = ctx.remote.run(host.name, host.alias, f"cat {STATUS} 2>/dev/null || echo '{{}}'", user=user, timeout=30)
    if result.code != 0:
        raise DriverError(FAILED, f"{host.name} did not answer over the tailnet")
    try:
        record = json.loads(result.out or "{}").get("lifecycle") or {}
    except ValueError:
        return None
    return record.get("state")


OVER_CAP = 4    # `lease set --cap`'s refusal (M2's host command, I16)


def lease_set(ctx, host, unix, cap=None):
    """`devcloud lease set` under the host's lock; the lease it printed, which
    is the one in force (§4.1). With `cap` the host itself refuses, under the
    same lock as the write, a lease past the cap that is later than the one
    in force: the check cannot be overtaken by another Mac's write."""
    command = f"devcloud lease set {int(unix)}" + (f" --cap {int(cap)}" if cap is not None else "")
    result = ctx.remote.run(host.name, host.alias, command, timeout=60)
    if result.code == 3:
        raise DriverError(FAILED, f"{host.name}'s departure has started; its lease stays as it is")
    if result.code == OVER_CAP and cap is not None:
        raise DriverError(CAP, f"{host.name}'s lease would end past the lifetime cap, later than the lease in force")
    if result.code != 0:
        raise DriverError(FAILED, f"{host.name} did not set the lease (exit {result.code}); its label is untouched")
    try:
        return int(result.out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise DriverError(FAILED, f"{host.name}'s `lease set` printed no lease") from None


def host_expires(ctx, host):
    result = ctx.remote.run(host.name, host.alias, f"sed -n 's/^DEVCLOUD_EXPIRES=//p' {BOOT_ENV}", timeout=30)
    try:
        return int(result.out.strip().strip('"')) if result.code == 0 else None
    except ValueError:
        return None


def unpushed(ctx, host):
    """The checkouts with unpushed or uncommitted work (`devcloud unpushed`,
    exit 5 when there is any), as (repository, what) pairs."""
    result = ctx.remote.run(host.name, host.alias, "devcloud unpushed", timeout=120)
    if result.code == 0:
        return []
    if result.code != 5:
        raise DriverError(FAILED, f"`devcloud unpushed` failed on {host.name} (exit {result.code})")
    return [tuple(line.split("\t", 1)) if "\t" in line else (line, "") for line in result.out.splitlines() if line]


# --- the departure ----------------------------------------------------------------

DONE, AFTER_READY, UNKNOWN, NOT_OVER, HELD, FAILED_RUN, UNREACHABLE = (
    "departed", "dropped after ready", "dropped before ready", "lease not over", "held", "failed", "unreachable")


def depart(ctx, host, force=False, no_hold=False, timeout=8 * 60):
    """`devcloud depart --no-poweroff` over the tailnet, and what came of it
    (§4.2): its exit codes reach the driver up to the ready line; once that
    line is read, the connection dropping is the logout, so success."""
    if not reachable(ctx, host):
        return UNREACHABLE
    flags = ["--no-poweroff"] + (["--force"] if force else []) + (["--no-hold"] if no_hold else [])
    result = ctx.remote.stream(host.name, host.alias, "devcloud depart " + " ".join(flags), timeout=timeout,
                               marker=READY)
    if result.code == 0:
        return DONE
    if result.code == 3:
        return NOT_OVER
    if result.code == 4:
        return HELD
    if result.code == 255 or result.code is None or result.code < 0:
        return AFTER_READY if result.marker else UNKNOWN
    return FAILED_RUN
