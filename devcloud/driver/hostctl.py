"""What the driver does on a host, over SSH: the slow path's install, the
seed and the boot's start (§3 steps 4 and 7), the wait (step 8), and the
host commands of M2 the driver consumes — `ledger add` before each credential
write, `lease set`, `unpushed`, `depart` and its ready line.

A host is reached at its public address until the tailnet attach step has
succeeded (the boot closes the public port right after it), then over the
tailnet by its name (§5)."""

import dataclasses
import json
import math
import pathlib
import re
import shlex

from .compose import SEED_PATH, SRC, STAGE, recipe_tar
from .errors import FAILED, DriverError

READY = "devcloud-depart: ready-to-logout"
BOOT_ENV = "/etc/devcloud/boot.env"
CODE_PATH = "/etc/devcloud/enroll-code"
STATUS = "/var/lib/devcloud/status.json"
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

def public_address(ctx, entry):
    """The server's public IPv4, which a provider may report only some
    seconds after the create."""
    for _ in range(30):
        vm = entry.client.get(entry.vm["id"])
        if vm and vm.get("public_ipv4"):
            return vm["public_ipv4"]
        ctx.sleep(5)
    raise DriverError(FAILED, f"{entry.vm['name']} has no public IPv4 for the first contact")


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


def install_recipe(ctx, address, key_alias, build, adopting=False):
    """The slow path: the plugin's recipe streamed and `setup.sh` run, its
    exit checked (adopt's install path, §6.5, `adopting`: setup.sh then
    refuses rather than delete an account in its way)."""
    for key in ("DEVCLOUD_USER", "DEVCLOUD_UID", "DEVCLOUD_HOME"):
        if not build.get(key):
            raise DriverError(FAILED, f"the profile's build.env lacks {key}, which setup.sh needs")
    unpack = f"rm -rf {SRC} && mkdir -p {SRC} && tar -x -C {SRC}"
    result = ctx.remote.run(address, key_alias, unpack, input=recipe_tar(ctx.plugin), timeout=300)
    if result.code != 0:
        raise DriverError(FAILED, f"streaming the recipe failed (exit {result.code})")
    inputs = " ".join(f"{k}={shlex.quote(build[k])}" for k in ("DEVCLOUD_USER", "DEVCLOUD_UID", "DEVCLOUD_HOME"))
    if adopting:
        inputs += " DEVCLOUD_ADOPTING=1"
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
    # The staging file too: a delivery stopped before its rename leaves the key there.
    ledger(ctx, address, key_alias, SEED_PATH, f"{SEED_PATH}.tmp", BOOT_ENV)
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


def stage(ctx, address, key_alias, desc):
    """The descriptor staged over SSH, where no user-data staged it."""
    stage_dir = STAGE.rsplit("/", 1)[0]
    result = ctx.remote.run(address, key_alias, f"umask 077 && install -d -m 0700 {stage_dir} && cat > {STAGE}",
                            input=desc.encode(), timeout=60)
    if result.code != 0:
        raise DriverError(FAILED, f"staging the descriptor failed (exit {result.code})")


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
    ledger(ctx, target, key_alias, CODE_PATH, f"{CODE_PATH}.tmp")
    result = ctx.remote.run(target, key_alias, f"umask 077 && cat > {CODE_PATH}.tmp && mv {CODE_PATH}.tmp {CODE_PATH}",
                            input=code, timeout=60)
    if result.code != 0:
        raise DriverError(FAILED, f"delivering the enrollment code failed (exit {result.code})")
    return ctx.remote.run(target, key_alias, "devcloud reconcile", timeout=900)


# --- over the tailnet -----------------------------------------------------------

def idle(ctx, host, timeout=10):
    """The host's idle record, or None when absent, invalid or unreachable.
    This is a noninteractive SSH probe: it must not reset the host's clock.
    """
    result = ctx.remote.run(host.name, host.alias, "cat /var/lib/devcloud/idle.json 2>/dev/null",
                            timeout=timeout, connect_timeout=max(1, math.ceil(timeout)))
    if result.code != 0:
        return None
    try:
        data = json.loads(result.out)
    except ValueError:
        return None
    value = data.get("active_at") if isinstance(data, dict) else None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    return data


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


KIND = "/var/lib/devcloud/tailnet.json"     # the node's kind as the host joined it (§4.1)


@dataclasses.dataclass(frozen=True)
class LeaseSet:
    expires: int | None     # the lease in force; None: kept
    rejoin: str | None      # the kind the node is rejoining as, when the lease changed it


def lease_set(ctx, host, unix):
    """`devcloud lease set` under the host's lock (`keep` for `unix` None);
    the lease it printed, which is the one in force (§4.1), and the kind its
    tailnet node is rejoining as when the write changed it."""
    command = f"devcloud lease set {'keep' if unix is None else int(unix)}"
    result = ctx.remote.run(host.name, host.alias, command, timeout=60)
    if result.code == 3:
        raise DriverError(FAILED, f"{host.name}'s departure has started; its lease stays as it is")
    lines = (result.out or "").strip().splitlines()
    rejoin = next((line.split(" ", 1)[1] for line in lines[:-1] if line.startswith("rejoin ")), None)
    try:
        done = LeaseSet(None if lines[-1] == "keep" else int(lines[-1]), rejoin)
    except (ValueError, IndexError):
        done = None
    # The rejoin it started can log the node out before SSH delivers the exit
    # status: a complete answer, its rejoin line and then the lease, stands.
    lost = result.code is None or result.code == 255 or result.code < 0
    if result.code != 0 and not (lost and done is not None and rejoin is not None):
        raise DriverError(FAILED, f"{host.name} did not set the lease (exit {result.code}); its label is untouched")
    if done is None:
        raise DriverError(FAILED, f"{host.name}'s `lease set` printed no lease")
    return done


REJOIN_WAIT = 10 * 60


def a_node(kind):
    """`an ephemeral node`, `a non-ephemeral node`."""
    return f"{'an' if kind[:1] in 'aeiou' else 'a'} {kind} node"


def wait_rejoin(ctx, host, kind, timeout=REJOIN_WAIT):
    """The host back on the tailnet under its own name as a `kind` node,
    after the rejoin its lease write started (§4.1): read over SSH by name
    from the host's record of its join, so an answer is itself the proof that
    the name reaches it. The rejoin cuts the connections it finds, so this
    only reads."""
    ephemeral = kind == "ephemeral"
    deadline = ctx.clock() + timeout
    while True:
        result = ctx.remote.run(host.name, host.alias, f"cat {KIND} 2>/dev/null || echo '{{}}'", timeout=30)
        try:
            record = json.loads(result.out) if result.code == 0 else {}
        except ValueError:
            record = {}
        if record.get("wanted") is ephemeral and record.get("state") == "failed":
            raise DriverError(FAILED, f"{host.name} did not rejoin the tailnet as {a_node(kind)}: "
                                      f"{record.get('detail') or 'no detail'}; its lease service tries again every "
                                      "5 minutes")
        if record.get("state") == "joined" and record.get("ephemeral") is ephemeral:
            if record.get("name") not in (None, host.name):
                raise DriverError(FAILED, f"{host.name} rejoined the tailnet as {a_node(kind)}, but under the name "
                                          f"{record['name']}: {record.get('detail')}")
            return record
        if ctx.clock() >= deadline:
            raise DriverError(FAILED, f"{host.name} did not come back on the tailnet as {a_node(kind)} within "
                                      f"{timeout // 60} minutes; `devcloud status` and the devcloud-rejoin unit's "
                                      "journal on it say why")
        ctx.sleep(5)


KEPT = "keep"     # host_expires of a host whose descriptor has no lease


def host_expires(ctx, host):
    """The lease in the host's descriptor; KEPT when it has none (`up --keep`
    or `lease keep`, both confirmed); None when it could not be read."""
    result = ctx.remote.run(host.name, host.alias, f"sed -n 's/^DEVCLOUD_EXPIRES=//p' {BOOT_ENV}", timeout=30)
    if result.code != 0:
        return None
    value = result.out.strip().strip('"')
    if not value:
        return KEPT
    try:
        return int(value)
    except ValueError:
        return None


def as_root(user, command):
    """`command` run as root by the login `user`: sudo, without a password,
    for a user other than root."""
    return command if user == "root" else f"sudo -n sh -c {shlex.quote(command)}"


def _through(login):
    """The connection's keyword arguments: the driver's key as root, or with
    `login` the person's own key as that user (an adopted machine whose
    release gave its keys back, §6.5)."""
    return {} if login is None else {"user": login, "person": True}


def unpushed(ctx, host, target=None, login=None):
    """The checkouts with unpushed or uncommitted work (`devcloud unpushed`,
    exit 5 when there is any), as (repository, what) pairs; over the tailnet
    unless `target` names another way to the host, as root unless `login`
    names the person's own login there."""
    result = ctx.remote.run(target or host.name, host.alias, as_root(login or "root", "devcloud unpushed"),
                            timeout=120, **_through(login))
    if result.code == 0:
        return []
    if result.code != 5:
        raise DriverError(FAILED, f"`devcloud unpushed` failed on {host.name} (exit {result.code})")
    return [tuple(line.split("\t", 1)) if "\t" in line else (line, "") for line in result.out.splitlines() if line]


# --- the departure ----------------------------------------------------------------

DONE, AFTER_READY, UNKNOWN, NOT_OVER, HELD, FAILED_RUN, UNREACHABLE = (
    "departed", "dropped after ready", "dropped before ready", "lease not over", "held", "failed", "unreachable")
# The departure's leave step as it prints it when the desk no longer holds the machine.
# A resumed release repeats the line of a leave an earlier run made.
LEFT_DESK = re.compile(r"^devcloud (depart|release): leave: ok — (left the desk|not enrolled)( \(an earlier run\))?$",
                       re.M)


class Outcome(str):
    """A departure's outcome (one of the names above), and whether its
    output showed the desk confirming the leave: the desk revokes nothing
    for being offline, so a machine it was not confirmed to leave stays in
    the desk's Machines until someone removes it."""

    def __new__(cls, value, left_desk=False, last_step=None):
        made = super().__new__(cls, value)
        made.left_desk = left_desk
        made.last_step = last_step
        return made


def depart(ctx, host, force=False, no_hold=False, timeout=8 * 60):
    """`devcloud depart --no-poweroff` over the tailnet, and what came of it
    (§4.2): its exit codes reach the driver up to the ready line; once that
    line is read, the connection dropping is the logout, so success."""
    if not reachable(ctx, host):
        return UNREACHABLE
    flags = ["--no-poweroff"] + (["--force"] if force else []) + (["--no-hold"] if no_hold else [])
    return _outcome(ctx.remote.stream(host.name, host.alias, "devcloud depart " + " ".join(flags), timeout=timeout,
                                      marker=READY))


def release(ctx, host, target, no_hold=False, timeout=8 * 60, login=None):
    """`devcloud release --force` on an adopted machine (§6.5) at `target`
    (its tailnet name, or its public address when the tailnet is down), as
    root unless `login` names the person's own login there; read as a
    departure is: it prints the same ready line before its logout."""
    command = as_root(login or "root", "devcloud release --force" + (" --no-hold" if no_hold else ""))
    return _outcome(ctx.remote.stream(target, host.alias, command, timeout=timeout, marker=READY,
                                      **_through(login)))


def _outcome(result):
    left = bool(LEFT_DESK.search(result.out or ""))
    if result.code == 0:
        return Outcome(DONE, left)
    if result.code == 3:
        return Outcome(NOT_OVER, left)
    if result.code == 4:
        return Outcome(HELD, left)
    if result.code == 255 or result.code is None or result.code < 0:
        # A flushed line can still be lost when logout cuts SSH. Retain only
        # the last delivered step's name/state, not arbitrary child output.
        steps = re.findall(r"^devcloud (?:depart|release): ([a-z-]+): (ok|failed)(?: —[^\n]*)?$",
                           result.out or "", re.M)
        last = f"{steps[-1][0]} ({steps[-1][1]})" if steps else None
        return Outcome(AFTER_READY if result.marker else UNKNOWN, left, last)
    return Outcome(FAILED_RUN, left)
