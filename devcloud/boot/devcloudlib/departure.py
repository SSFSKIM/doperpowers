"""The departure and the release (Design §4.2, §6.5): what a host does at its
lease end, or when `devcloud vm down` asks.

`devcloud depart`, in order, each step bounded so a broken one cannot keep the
host alive: 0 close admission (every periodic timer but the lease's, and the
sminos daemon, stopped and disabled); 1 end the user's `claude` processes;
2 stop the continuous shipper and ship once, then end and ship again while
sessions keep appearing, three rounds at most; 3 `sminos hub leave`; 4 the
flushed line `devcloud-depart: ready-to-logout`, then `tailscale logout`, and
the node's removal through the Tailscale API when the logout leaves it listed
(a node not known to be ephemeral: its id is read before the logout, board
#118); 5 stop devcloud's services (not the transient unit this runs in);
6 power off.
A failed ship, or sessions still there after the third round, holds the
departure before step 3 — no leave, no logout, no power-off — and exits 4; the
lease service's next run starts again, step 0 re-applied first.

`devcloud release`, on an adopted machine: steps 0-2 as the departure's, then
the leave, the firewall table and its unit removed, the saved
`authorized_keys` restored, the logout and the node's removal, devcloud's
units stopped and removed,
and every credential the ledger lists removed, the descriptor and then the
ledger last. The machine keeps running. A failed firewall removal, key
restore, logout (unless `tailscale status` shows the node logged out), unit
removal or credential removal stops the release there (exit 1,
state `departing`) before anything that would cut the person off or leave
them nothing to resume from; run again, it resumes after the last step that
succeeded.

Both run under the lifecycle lock, re-read the lease under it, and refuse
with exit 3 ("lease not over") unless it has ended, they were given --force,
or they resume one under way. Each step's outcome is a status entry
(status.json's `lifecycle`). Each is a process of its own: it learns the
host's secrets before its first step, so no child's output reaches its log
unscrubbed."""

import dataclasses
import json
import os
import pathlib
import pwd
import signal
import sys
import time
import urllib.request

from . import descriptor, envfile, ledger, lease, nodekind, proc, secretmanager, services, sminos_host, status, \
    steps, tsapi
from .proc import StepError

DONE, FAILED, USAGE, NOT_OVER, HELD = 0, 1, 2, 3, 4
READY = "devcloud-depart: ready-to-logout"
ROUNDS = 3
SESSION_GRACE = 30
SHIP_TIMEOUT = 300
LEAVE_TIMEOUT = 180     # I15: one `hub` call can take about 150 s
ADOPT_DIR = pathlib.Path("/var/lib/devcloud-adopt")
INBOUND_UNIT = "devcloud-inbound.service"
SHIPPER_UNIT = "devcloud-session-mirror.service"
INBOUND_NFT = pathlib.Path("/etc/devcloud/inbound.nft")
UNIT_DIR = pathlib.Path("/etc/systemd/system")
# The spot reclaim's window: steps 0-4 within 25 of the provider's ~30 seconds.
PREEMPT_BUDGET = 25


@dataclasses.dataclass
class Host:
    """Everything a departure touches, one seam each, so tests can stand in."""
    user: proc.User
    run: object = proc.run      # raises StepError on a nonzero exit
    call: object = None         # returns (exit, stdout, stderr's last line); proc.call by default
    status_path: pathlib.Path = status.PATH
    ledger_path: pathlib.Path = ledger.PATH
    desc_path: pathlib.Path = pathlib.Path(descriptor.PATH)
    lock_path: pathlib.Path = None
    adopt_dir: pathlib.Path = ADOPT_DIR
    unit_dir: pathlib.Path = UNIT_DIR
    inbound_nft: pathlib.Path = INBOUND_NFT
    shipper_seen: pathlib.Path = None    # services.SHIPPER_SEEN by default
    state_dir: pathlib.Path = status.PATH.parent     # /var/lib/devcloud
    out: object = None
    as_user: object = proc.as_user
    now: object = time.time
    monotonic: object = time.monotonic
    sleep: object = time.sleep
    allow_http: bool = False

    def __post_init__(self):
        if self.call is None:
            self.call = proc.call
        if self.shipper_seen is None:
            self.shipper_seen = services.SHIPPER_SEEN

    def installed(self, unit):
        return (self.unit_dir / unit).exists()

    def say(self, line):
        (self.out or sys.stdout).write(line + "\n")
        (self.out or sys.stdout).flush()

    def claude_pids(self):
        return claude_pids(self.user.uid)

    def alive(self, pid):
        return _alive(pid)

    def kill(self, pid, sig):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass

    def user_env(self):
        try:
            env = envfile.parse(pathlib.Path(services.ENV_PATH).read_text())
        except (FileNotFoundError, ValueError):
            env = {}
        return self.user.env(env)

    def preempted(self):
        return _preempted()

    def know_secrets(self, d):
        proc.know_host(self.user, d.seed_path if d.seed_kind == "file" else None, env_path=services.ENV_PATH)

    def ts_client(self, d):
        """The OAuth client the host joined with, from Secret Manager through
        the seed, as the boot fetches it."""
        return steps.fetch_text(secretmanager.Tokens(d), d.ts_secret)

    @property
    def node_path(self):
        """The record of the host's tailnet node (nodekind's)."""
        return self.state_dir / nodekind.PATH.name


def claude_pids(uid):
    """The user's `claude` processes (by name or by argv[0]), zombies left out."""
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        base = f"/proc/{entry}"
        try:
            with open(f"{base}/status") as f:
                fields = dict(line.split(":", 1) for line in f if ":" in line)
            if int(fields["Uid"].split()[0]) != uid or fields.get("State", "").strip().startswith("Z"):
                continue
            with open(f"{base}/comm") as f:
                comm = f.read().strip()
            with open(f"{base}/cmdline", "rb") as f:
                argv0 = f.read().split(b"\0")[0].decode(errors="replace")
        except (OSError, ValueError, KeyError):
            continue
        if comm == "claude" or os.path.basename(argv0) == "claude":
            found.append(int(entry))
    return found


def _alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def _preempted():
    """GCE's word that this spot VM is being reclaimed."""
    root = os.environ.get("GCE_METADATA_HOST", "metadata.google.internal")
    request = urllib.request.Request(f"http://{root}/computeMetadata/v1/instance/preempted",
                                     headers={"Metadata-Flavor": "Google"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.read().decode().strip().upper() == "TRUE"
    except (OSError, ValueError):
        return False


class _Held(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Run:
    """One departure or release: its steps recorded as they finish."""

    def __init__(self, host, op, deadline=None):
        self.host = host
        self.op = op
        self.steps = []
        self.deadline = deadline

    def bound(self, seconds):
        """`seconds`, cut to what the deadline leaves (at least 1)."""
        if self.deadline is None:
            return seconds
        return max(1, min(seconds, int(self.deadline - self.host.monotonic())))

    def record(self, name, state, detail):
        detail = proc.KNOWN.scrub(detail)
        self.steps.append({"name": name, "state": state, "at": status.now(), "detail": detail})
        status.set_lifecycle(self.op, "departing", f"step {name}: {state}", steps=self.steps,
                             path=self.host.status_path)
        self.host.say(f"devcloud {self.op}: {name}: {state}" + (f" — {detail}" if detail else ""))

    def step(self, name, fn):
        """Runs one step; a failure is recorded and the run goes on, except a hold."""
        try:
            detail = fn()
            self.record(name, "ok", detail or "")
            return True
        except _Held:
            raise
        except Exception as error:  # noqa: BLE001 — a broken step never keeps the host alive
            self.record(name, "failed", f"{type(error).__name__}: {error}" if not isinstance(error, StepError)
                        else str(error))
            return False


# --- the steps both share ----------------------------------------------------------

def _periodic_units(host, keep_lease=True):
    listed = services.service_list(host.user, persistent=True)
    return [unit for unit in (f"devcloud-{s.name}.timer" for s in listed
                              if s.every is not None and not (keep_lease and s.name == "lease"))
            if host.installed(unit)]


def close_admission(run):
    """Step 0: every periodic timer but the lease's, and the sminos daemon,
    stopped and disabled, so nothing starts a session or the daemon again —
    not a job, not the user manager at the next boot."""
    host = run.host
    done, failed = [], []
    for unit in _periodic_units(host):
        try:
            host.run(["systemctl", "disable", "--now", unit], log="lifecycle", timeout=run.bound(60))
            done.append(unit)
        except StepError as error:
            failed.append(f"{unit} ({error})")
    unit_file = host.user.home / ".config/systemd/user" / sminos_host.UNIT
    if unit_file.exists():
        env = dict(host.user_env(), XDG_RUNTIME_DIR=f"/run/user/{host.user.uid}")
        try:
            host.run(["systemctl", "--user", "disable", "--now", sminos_host.UNIT], user=host.user, env=env,
                     log="lifecycle", timeout=run.bound(60))
            done.append(f"{sminos_host.UNIT} (user)")
        except StepError as error:
            failed.append(f"{sminos_host.UNIT} ({error})")
    detail = f"stopped and disabled: {', '.join(done) or 'nothing'}"
    if failed:
        raise StepError(detail + "; failed: " + "; ".join(failed))
    return detail


def end_sessions(run, grace=SESSION_GRACE):
    """Step 1: SIGTERM to the user's `claude` processes, SIGKILL to what remains
    after `grace` seconds."""
    host = run.host
    pids = host.claude_pids()
    if not pids:
        return "no session running"
    for pid in pids:
        host.kill(pid, signal.SIGTERM)
    end = host.monotonic() + run.bound(grace)
    while host.monotonic() < end and any(host.alive(pid) for pid in pids):
        host.sleep(0.5)
    killed = [pid for pid in pids if host.alive(pid)]
    for pid in killed:
        host.kill(pid, signal.SIGKILL)
    return f"{len(pids)} ended" + (f", {len(killed)} of them killed after {grace}s" if killed else "")


def _shipper(host):
    return host.user.home / ".claude/tools/session-mirror"


def ship_once(run, timeout=SHIP_TIMEOUT):
    """`session-mirror ship --once` as the user; False when it failed. A host
    that never had a shipper (no program, no unit, and the services step never
    found one) has nothing to ship; one configured but now missing or not
    executable is a failed ship."""
    host = run.host
    program = _shipper(host)
    if not os.access(program, os.X_OK):
        if not (os.path.lexists(program) or host.installed(SHIPPER_UNIT) or host.shipper_seen.exists()):
            return True, "no shipper configured (nothing to ship)"
        return False, f"the shipper {program} is {'not executable' if os.path.lexists(program) else 'missing'}"
    try:
        host.run([str(program), "ship", "--once"], user=host.user, env=host.user_env(), log="lifecycle",
                 timeout=run.bound(timeout), cwd=str(host.user.home))
    except StepError as error:
        return False, str(error)
    return True, "shipped"


def sessions_and_ship(run, no_hold, grace=SESSION_GRACE, rounds=ROUNDS, ship_timeout=SHIP_TIMEOUT):
    """Steps 1 and 2 with the final check: end the sessions, stop the shipper
    and ship once; while a `claude` process is found after the ship (`sminos
    spawn` starts one without the daemon), end and ship again — `rounds` at
    most, then hold. A failed ship holds at once. With `no_hold` both go on."""
    host = run.host
    for number in range(1, rounds + 1):
        run.step("end-sessions", lambda: end_sessions(run, grace))
        if number == 1:
            run.step("stop-shipper", lambda: host.run(
                ["systemctl", "stop", SHIPPER_UNIT], log="lifecycle",
                timeout=run.bound(60)) or f"{SHIPPER_UNIT} stopped")
        ok, detail = ship_once(run, ship_timeout)
        run.record("ship", "ok" if ok else "failed", detail)
        if not ok:
            if no_hold:
                return
            raise _Held("ship failed")
        if not host.claude_pids():
            return
        if number == rounds:
            if no_hold:
                return
            raise _Held("sessions keep starting")
        run.record("final-check", "ok", f"a session appeared after the ship; round {number + 1} of {rounds}")


def leave(run, timeout=LEAVE_TIMEOUT):
    """Step 3: `sminos hub leave` as the user; 0 and 1 both go on. The desk
    revokes nothing for being offline, so on 1 the machine stays in its
    Machines until someone removes it, which the driver tells the person."""
    host = run.host
    env = host.user_env()
    if not (sminos_host.sminos_home(host.user, env) / "daemon/hub.json").is_file():
        return "not enrolled"
    program = sminos_host.cli(host.user)
    if program is None:
        raise StepError("enrolled, but the sminos CLI is absent")
    code, _, err = host.call([sminos_host.PYTHON, str(program), "hub", "leave"], user=host.user, env=env,
                             log="lifecycle", timeout=run.bound(timeout))
    if code == 0:
        return "left the desk"
    if code == 1:
        return f"the desk did not answer the leave ({err or 'exit 1'}); it stays in the desk's Machines until someone removes it"
    raise StepError(f"sminos hub leave exited {code}" + (f": {err}" if err else ""))


def logout(run, d, confirm=False):
    """Step 4: the node's id recorded for its removal (`mark_node`), the line
    the driver reads as success once the logout cuts its connection, flushed,
    then `tailscale logout`. With `confirm` (the release's), a failed logout
    still counts when `tailscale status` shows the node logged out
    (`NeedsLogin`): a command that timed out may have done its work."""
    note = mark_node(run, d) if d.tailscale == "join" else None
    run.host.say(READY)
    if d.tailscale != "join":
        return "not a tailnet node of its own"
    note = f"; {note}" if note else ""
    try:
        run.host.run(["tailscale", "logout"], log="lifecycle", timeout=run.bound(60))
    except StepError as error:
        if not confirm:
            raise StepError(f"{error}{note}") from None
        state = _backend_state(run)
        if state != "NeedsLogin":
            raise StepError(f"{error}; tailscale status shows {state or 'nothing readable'}, not NeedsLogin{note}") \
                from None
        return f"tailscale logout failed ({error}), but tailscale status shows the node logged out (NeedsLogin){note}"
    return f"logged out of the tailnet{note}"


def _status(run):
    """`tailscale status --json` as a dict, or None when it cannot be read."""
    code, out, _ = run.host.call(["tailscale", "status", "--json"], log="lifecycle", timeout=run.bound(30))
    try:
        data = json.loads(out) if code == 0 else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _backend_state(run):
    return (_status(run) or {}).get("BackendState")


def _held(run):
    """The id of the node tailscaled holds: "" for none (a logged-out daemon
    names no Self.ID), None when the status cannot be read."""
    data = _status(run)
    return None if data is None else (data.get("Self") or {}).get("ID") or ""


def mark_node(run, d):
    """Before the logout: the id of the node the logout would leave listed
    recorded as pending removal (nodekind's record), where `remove_node`
    finds it, and a resumed release too. A logout removes an ephemeral node
    at once and leaves a non-ephemeral one listed, offline and expired
    (measured 2026-10-22); a kind not recorded counts as non-ephemeral. A
    node joined with the fallback auth key has no client to remove it with.
    Returns a note when the id could not be read."""
    path = run.host.node_path
    if not nodekind.applies(d) or nodekind.recorded(path).get("ephemeral") is True:
        return None
    held = _held(run)
    if held:
        nodekind.pend(held, path)
        return None
    if held is None:
        return "its node's id could not be read before the logout, so the node stays listed until the driver removes it"
    return None


def remove_node(run, d):
    """Step 4's second half, right after the logout (board #118): every node
    id the record holds as pending removal — this host's own, read before the
    logout, and an old node a rejoin left — removed through the Tailscale API
    with the OAuth client, as the rejoin removes them (`steps.remove_pending`,
    never the node held). A removal that fails is recorded and the run goes
    on; the driver removes what a deleted host leaves listed."""
    host = run.host
    if d.tailscale != "join":
        return "not a tailnet node of its own"
    if not nodekind.pending(host.node_path):
        if not nodekind.applies(d):
            return "joined with an auth key file, not the OAuth client: nothing here can remove its node"
        if nodekind.recorded(host.node_path).get("ephemeral") is True:
            return "an ephemeral node, which left at its logout"
        return "no node id to remove"
    held = _held(run)
    detail = steps.remove_pending(lambda: tsapi.token(host.ts_client(d)), held, path=host.node_path,
                                  sleep=host.sleep)
    if nodekind.pending(host.node_path):
        raise StepError(detail)
    if held:
        raise StepError(f"{detail}; tailscale still holds that node after the logout, so it stays listed")
    return detail


def stop_services(run):
    """Step 5: every devcloud unit stopped — the lease service among them —
    but not the transient unit the departure runs in."""
    host = run.host
    units = []
    for s in services.service_list(host.user, persistent=True):
        units.append(f"devcloud-{s.name}.service")
        if s.every is not None:
            units.append(f"devcloud-{s.name}.timer")
    units = [unit for unit in units if host.installed(unit)]
    if units:
        host.run(["systemctl", "stop", *units], log="lifecycle", timeout=run.bound(120))
    return f"stopped {', '.join(units) or 'no unit'}"


# --- the departure ------------------------------------------------------------------

def _lease_over(d, host):
    return d.expires is not None and host.now() >= d.expires


def _begin(host, op, force):
    """The checks under the lock, before any step: the operation already
    done (read first: a completed release has removed the descriptor), the
    descriptor, and the lease, unless forced or resuming a run of the same
    operation under way. Returns (descriptor, the record resumed or None,
    exit)."""
    record = status.lifecycle(host.status_path)
    if record and record.get("op") == op and record.get("state") == "departed":
        host.say(f"devcloud {op}: already done ({record['at']})")
        return None, None, DONE
    if op == "release" and not host.state_dir.exists() and not host.desc_path.exists():
        host.say("devcloud release: already done (nothing of devcloud is left here)")
        return None, None, DONE
    try:
        d = descriptor.load(host.desc_path, allow_http=host.allow_http)
    except descriptor.DescriptorError as error:
        host.say(f"devcloud {op}: {error}")
        return None, None, FAILED
    if d.role != "persistent":
        host.say(f"devcloud {op}: a sandbox never departs; its host removes it")
        return None, None, FAILED
    if (op == "release") != d.adopted:
        host.say(f"devcloud {op}: " + ("only an adopted machine (DEVCLOUD_ADOPTED=1) is released"
                                        if op == "release" else "an adopted machine is released, not departed"))
        return None, None, FAILED
    # A run that passed these checks once and stopped part way: its lease
    # cannot have moved since (`lease set` refuses once a departure started).
    resumed = record if record and record.get("op") == op and record.get("state") == "departing" else None
    if not force and resumed is None and not _lease_over(d, host):
        when = f"ends {lease.iso(d.expires)}" if d.expires is not None else "has no end (keep)"
        host.say(f"devcloud {op}: lease not over (it {when}); --force departs anyway")
        return None, None, NOT_OVER
    host.know_secrets(d)
    return d, resumed, None


def depart(host, force=False, no_hold=False, no_poweroff=False):
    """`devcloud depart`; returns its exit status (I16)."""
    with lease.locked(path=host.lock_path):
        d, _, code = _begin(host, "depart", force)
        if d is None:
            return code
        run = Run(host, "depart")
        status.set_lifecycle("depart", "departing", "started", steps=[], path=host.status_path)
        try:
            run.step("close-admission", lambda: close_admission(run))
            sessions_and_ship(run, no_hold)
        except _Held as held:
            status.set_lifecycle("depart", "held", f"held ({held.reason})", steps=run.steps,
                                 path=host.status_path)
            host.say(f"devcloud depart: held ({held.reason}); the lease service tries again at its next run")
            return HELD
        run.step("leave", lambda: leave(run))
        run.step("logout", lambda: logout(run, d))
        run.step("remove-node", lambda: remove_node(run, d))
        run.step("stop-services", lambda: stop_services(run))
        if not no_poweroff:
            run.steps.append({"name": "poweroff", "state": "ok", "at": status.now(), "detail": "requested"})
        status.set_lifecycle("depart", "departed", "departed", steps=run.steps, path=host.status_path)
        if not no_poweroff:
            try:
                host.run(["systemctl", "poweroff"], log="lifecycle", timeout=60)
            except StepError as error:
                host.say(f"devcloud depart: the power-off failed ({error})")
        return DONE


def depart_preempted(host):
    """The spot reclaim's departure: only when the metadata server says this
    VM is being reclaimed, and then steps 0-4 within 25 seconds, one round,
    no hold, no lease check; the provider deletes the VM."""
    if not host.preempted():
        host.say("devcloud depart: not preempted; an ordinary shutdown departs nothing")
        return DONE
    deadline = host.monotonic() + PREEMPT_BUDGET
    try:
        lock = lease.locked(path=host.lock_path, timeout=2)
        lock.__enter__()
    except TimeoutError:
        host.say("devcloud depart: a departure already holds the lifecycle lock")
        return DONE
    try:
        try:
            d = descriptor.load(host.desc_path, allow_http=host.allow_http)
        except descriptor.DescriptorError as error:
            host.say(f"devcloud depart: {error}")
            return FAILED
        host.know_secrets(d)
        run = Run(host, "depart", deadline=deadline)
        status.set_lifecycle("depart", "departing", "reclaimed by the provider", steps=[], path=host.status_path)
        run.step("close-admission", lambda: close_admission(run))
        sessions_and_ship(run, no_hold=True, grace=5, rounds=1, ship_timeout=max(1, PREEMPT_BUDGET - 15))
        run.step("leave", lambda: leave(run, timeout=5))
        run.step("logout", lambda: logout(run, d))
        run.step("remove-node", lambda: remove_node(run, d))
        status.set_lifecycle("depart", "departed", "departed (reclaimed)", steps=run.steps, path=host.status_path)
        return DONE
    finally:
        lock.__exit__(None, None, None)


# --- the release --------------------------------------------------------------------

def remove_firewall(run):
    """Release step 3: devcloud's `inet devcloud` table and its unit; every
    other rule stays."""
    host = run.host
    unit = host.unit_dir / INBOUND_UNIT
    parts = []
    if unit.exists():
        try:
            host.run(["systemctl", "disable", "--now", INBOUND_UNIT], log="lifecycle", timeout=60)
        except StepError:
            pass    # its stop deletes the table; the delete below covers a failed stop
        unit.unlink()
        host.run(["systemctl", "daemon-reload"], log="lifecycle", timeout=60)
        parts.append(f"{INBOUND_UNIT} removed")
    code, _, _ = host.call(["nft", "list", "table", "inet", "devcloud"], log="lifecycle", timeout=30)
    if code == 0:
        host.run(["nft", "delete", "table", "inet", "devcloud"], log="lifecycle", timeout=30)
        parts.append("table inet devcloud deleted")
    host.inbound_nft.unlink(missing_ok=True)
    return "; ".join(parts) or "no devcloud firewall"


def restore_keys(run):
    """Release step 4: each saved `authorized_keys` back where adopt found it
    (a file that did not exist then is removed), then the saved copies. The
    manifest, `keys.json` in the adopt directory: {"keys": [{"path", "owner",
    "saved"}]}, `saved` the copy's file name there, or null."""
    host = run.host
    manifest = host.adopt_dir / "keys.json"
    if not manifest.exists():
        if host.adopt_dir.exists():
            raise StepError(f"{host.adopt_dir} holds no keys.json: nothing to restore from")
        return "nothing saved"
    entries = json.loads(manifest.read_text())["keys"]
    restored = []
    for entry in entries:
        target = pathlib.Path(entry["path"])
        owner = pwd.getpwnam(entry["owner"])
        data = (host.adopt_dir / entry["saved"]).read_bytes() if entry.get("saved") else None
        who = proc.User(name=owner.pw_name, uid=owner.pw_uid, gid=owner.pw_gid, home=pathlib.Path(owner.pw_dir))

        def put(target=target, data=data):
            if data is None:
                target.unlink(missing_ok=True)
            else:
                proc.write_file(target, data, mode=0o600, dir_mode=0o700)
        host.as_user(who, put)
        restored.append(f"{target} ({'restored' if data is not None else 'removed: there was none'})")
    ledger.remove_one(str(host.adopt_dir))
    return "; ".join(restored) + f"; {host.adopt_dir} removed"


def remove_units(run):
    """Release step 6: every devcloud unit stopped, disabled and removed (with
    its drop-ins), the user unit's devcloud drop-in too; not the transient
    release unit, which lives under /run and runs on to record the end."""
    host = run.host
    names = sorted({p.name for p in host.unit_dir.glob("devcloud-*") if p.suffix in (".service", ".timer")})
    if names:
        host.run(["systemctl", "disable", "--now", *names], log="lifecycle", timeout=run.bound(180))
    for name in names:
        ledger.remove_one(str(host.unit_dir / name))
        ledger.remove_one(str(host.unit_dir / f"{name}.d"))
    dropin = host.user.home / ".config/systemd/user" / f"{sminos_host.UNIT}.d" / "devcloud.conf"
    host.as_user(host.user, lambda: ledger.remove_one(str(dropin)))
    host.run(["systemctl", "daemon-reload"], log="lifecycle", timeout=60)
    return f"removed {', '.join(names) or 'no unit'}"


def remove_credentials(run):
    """Release step 7: every path the ledger lists, the descriptor last of
    them (a retry loads it to resume), then the ledger."""
    host = run.host
    removed, failures = ledger.remove_all(host.user, host.as_user, path=host.ledger_path, last=[host.desc_path])
    if failures:
        raise StepError(f"removed {len(removed)}; left: {', '.join(failures)}; the ledger and the descriptor stay")
    return f"removed {len(removed)} credential paths, then the ledger"


def release(host, force=False, no_hold=False):
    """`devcloud release`; returns its exit status (I16). Run again after one
    that stopped part way, it skips each step after the ship that already
    succeeded; steps 0-2 and the final check run again until a logout has
    succeeded, since a host still on the tailnet can have started a session
    since (only cleanup is left once it is off)."""
    with lease.locked(path=host.lock_path):
        d, resumed, code = _begin(host, "release", force)
        if d is None:
            return code
        run = Run(host, "release")
        done = set()
        if resumed:
            run.steps = list(resumed.get("steps") or [])
            done = {s["name"] for s in run.steps if s["state"] == "ok"}
        status.set_lifecycle("release", "departing", "resumed" if resumed else "started", steps=run.steps,
                             path=host.status_path)
        if "logout" not in done:
            try:
                run.step("close-admission", lambda: close_admission(run))
                sessions_and_ship(run, no_hold)
            except _Held as held:
                status.set_lifecycle("release", "held", f"held ({held.reason})", steps=run.steps,
                                     path=host.status_path)
                host.say(f"devcloud release: held ({held.reason}); the lease service tries again at its next run")
                return HELD
        # (step, whether its failure stops the release): the firewall and the
        # keys are the person's way in once the tailnet is gone; the machine
        # keeps running and its node is not ephemeral, so a logout that did
        # not happen would leave it on the tailnet with nothing of devcloud
        # left to retry from; units left would rewrite the credentials;
        # credentials left need the descriptor. The node's removal needs the
        # OAuth client, which the seed among the credentials reads, so it
        # comes before them; it fails alone (the driver's `down` removes the
        # node too).
        for name, fn, stops in (("leave", lambda: leave(run), False),
                                ("firewall", lambda: remove_firewall(run), True),
                                ("restore-keys", lambda: restore_keys(run), True),
                                ("logout", lambda: logout(run, d, confirm=True), True),
                                ("remove-node", lambda: remove_node(run, d), False),
                                ("remove-units", lambda: remove_units(run), True),
                                ("remove-credentials", lambda: remove_credentials(run), True)):
            if name in done:
                # Its line again, marked: the driver reads the leave's outcome
                # from the output (whether the desk confirmed it).
                earlier = next(s for s in reversed(run.steps) if s["name"] == name and s["state"] == "ok")
                host.say(f"devcloud release: {name}: ok" + (f" — {earlier['detail']}" if earlier["detail"] else "")
                         + " (an earlier run)")
                continue
            if not run.step(name, fn) and stops:
                status.set_lifecycle("release", "departing", f"{name} failed: run it again to resume",
                                     steps=run.steps, path=host.status_path)
                host.say(f"devcloud release: {name} failed; nothing after it ran. "
                         "`devcloud release` again resumes from there")
                return FAILED
        status.set_lifecycle("release", "departed", "released", steps=run.steps, path=host.status_path)
        forget(run)
        return DONE


def forget(run):
    """The end of a completed release: devcloud's state directory goes (its
    record of this release with it), leaving no devcloud state outside the
    home; and systemd forgets the failures of the units removed, which it
    would list until the next boot."""
    host = run.host
    try:
        ledger.remove_one(str(host.state_dir))
    except OSError as error:
        host.say(f"devcloud release: {host.state_dir} stays ({error})")
    host.call(["systemctl", "reset-failed", "devcloud-*"], log="lifecycle", timeout=30)
    host.say("devcloud release: released")
