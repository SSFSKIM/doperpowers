"""One command's world: where the profile, the seed and the driver's own
state live (§8), Secret Manager, the providers of every account, SSH to the
hosts, the tailnet and the desk. Commands take a Context; tests build one
from stand-ins."""

import contextlib
import dataclasses
import json
import os
import pathlib
import re
import secrets as secrets_mod
import socket
import subprocess
import sys
import time

from . import hostfile
from . import labels as label_rules
from . import tailnet as tailnet_mod
from . import profile as profile_mod
from . import provider
from .errors import FAILED, UNUSABLE, DriverError, NotOwned
from .gsm import SecretManager
from .hostctl import Host, alias
from .ssh import Ssh

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
sha256_file = provider.sha256_file


@dataclasses.dataclass(frozen=True)
class Paths:
    profile: pathlib.Path    # the profile's devcloud/ directory
    state: pathlib.Path      # ~/.local/state/devcloud
    seed: pathlib.Path

    @classmethod
    def from_env(cls, env):
        home = pathlib.Path(env.get("HOME") or pathlib.Path.home())
        return cls(profile=pathlib.Path(env.get("DEVCLOUD_PROFILE") or home / ".claude" / "devcloud"),
                   state=home / ".local" / "state" / "devcloud",
                   seed=pathlib.Path(env.get("DEVCLOUD_SEED_FILE") or home / ".config" / "devcloud" / "seed.json"))

    @property
    def key(self):
        return self.state / "ssh" / "id_ed25519"

    @property
    def known_hosts(self):
        return self.state / "ssh" / "known_hosts"

    @property
    def reap_log(self):
        return self.state / "reap.log"

    @property
    def adopted(self):
        return self.state / "adopted"


@dataclasses.dataclass
class Entry:
    """One labeled server of one account."""
    account: profile_mod.Account
    client: provider.Client
    vm: dict

    @property
    def host(self):
        return Host(name=self.vm["name"], alias=alias(self.account.name, self.vm["id"]),
                    public=self.vm.get("public_ipv4"))


class Context:
    def __init__(self, paths, env=None, secrets=None, remote=None, clock=time.time, sleep=time.sleep,
                 out=sys.stdout, err=sys.stderr, machine=None, tailnet=None, sminos_machines=None, creator=None,
                 timeouts=None, plugin=PLUGIN_DIR, key_pushed=None, token_hex=None, monotonic=time.monotonic,
                 host_file=None, tailnet_api=None):
        self.paths = paths
        self.env = dict(os.environ if env is None else env)
        self.clock = clock
        self.sleep = sleep
        self.out = out
        self.err = err
        self.machine = machine or label_rules.machine(socket.gethostname())
        self.plugin = pathlib.Path(plugin)
        self.timeouts = timeouts
        self._secrets = secrets
        self._remote = remote
        self._profile = None
        self._clients = {}
        self.tailnet = tailnet or tailnet_nodes
        # The Tailscale API, for the nodes of a host the driver is done with (tailnet.remove).
        self.tailnet_api = tailnet_api or tailnet_mod.Api()
        # `sminos machines`' stdout, or None when there is no answer; the argument is its timeout.
        self.sminos_machines = sminos_machines or (lambda timeout: run_sminos_machines(self.env, timeout))
        self.creator = creator or (lambda: session_creator(self.env))
        self.key_pushed = key_pushed or (lambda: key_in_remote(self))
        self.token_hex = token_hex or (lambda: secrets_mod.token_hex(2))
        self.monotonic = monotonic
        # A project's devenv/host.toml: (text or None, where it was read).
        self.host_file = host_file or (lambda project: hostfile.read(project, os.getcwd(), self.env))
        self._deadline = None

    # --- lazily loaded --------------------------------------------------------------

    @property
    def profile(self):
        if self._profile is None:
            self._profile = profile_mod.load(self.paths.profile)
        return self._profile

    def reload_profile(self):
        self._profile = None
        self._clients = {}

    @property
    def secrets(self):
        if self._secrets is None:
            self._secrets = SecretManager(self.paths.seed, self.profile.host.sm_project, clock=self.clock)
        return self._secrets

    @property
    def remote(self):
        if self._remote is None:
            self._remote = Ssh(self.paths, self.machine)
        return self._remote

    @contextlib.contextmanager
    def bounded(self, seconds):
        """A run with an overall deadline: every provider call inside it
        takes its credential reads and its timeout from what is left, and
        none starts once nothing is."""
        previous = self._deadline
        self._deadline = self.monotonic() + seconds
        try:
            yield
        finally:
            self._deadline = previous

    def remaining(self):
        return None if self._deadline is None else self._deadline - self.monotonic()

    def say(self, line=""):
        print(line, file=self.out, flush=True)

    def warn(self, line):
        print(line, file=self.err, flush=True)

    # --- providers --------------------------------------------------------------------

    def client(self, account, executable=None):
        """The account's provider; exit 7 when it is not usable."""
        if executable is None and account.name in self._clients:
            return self._clients[account.name]
        exe, sha = (executable, None) if executable else provider.usable_executable(self.paths.profile, account)
        client = provider.Client(account, exe, self.secrets, env=self.env, seed_path=self.paths.seed,
                                 timeouts=self.timeouts, warn=self.warn, sha256=sha, budget=self.remaining)
        if executable is None:
            self._clients[account.name] = client
        return client

    def usable(self, quiet=False):
        """Every usable account's client; an unusable one is named on stderr
        and left out (`ls` and the reaper serve the rest)."""
        out = []
        for account in self.profile.accounts.values():
            try:
                out.append((account, self.client(account)))
            except DriverError as error:
                if error.code != UNUSABLE:
                    raise
                if not quiet:
                    self.warn(f"devcloud vm: skipping account {account.name}: {error}")
        return out

    def fleet_of(self, account, client, kinds=("vm",)):
        """The account's labeled servers whose devcloud label is one of
        `kinds` (None: every kind)."""
        return [Entry(account, client, vm) for vm in client.list()
                if kinds is None or vm["labels"].get("devcloud") in kinds]

    def fleet(self, quiet=False, kinds=("vm",), strict=False):
        """`fleet_of` every usable account. A provider whose list fails is
        named and skipped, for what only shows the fleet (`ls`, `find`);
        `strict`, for what counts it against a cap, fails instead: a list
        that failed must not count as no VMs."""
        entries = []
        for account, client in self.usable(quiet=quiet):
            try:
                entries += self.fleet_of(account, client, kinds)
            except DriverError as error:
                if strict:
                    raise DriverError(FAILED, f"account {account.name}'s VMs could not be listed, so the count "
                                              f"cap cannot be counted ({error})") from None
                self.warn(f"devcloud vm: account {account.name}: {error}")
        return entries

    def find(self, name):
        for entry in self.fleet(quiet=True):
            if entry.vm["name"] == name:
                return entry
        raise DriverError(FAILED, f"no VM named {name} in any usable account")

    def driver_keys(self):
        """Every driver Mac's public key (the profile's driver-keys/), this
        one's made first when missing."""
        own = self.remote.ensure_key()
        keys = {own.strip()}
        directory = self.paths.profile / "driver-keys"
        if directory.is_dir():
            keys |= {p.read_text().strip() for p in sorted(directory.glob("*.pub")) if p.read_text().strip()}
        return sorted(keys)

    def desk_listing(self):
        """The desk's machines as this driver's enrollment reads them, within
        what a bounded run has left; None when nothing could be read."""
        left = self.remaining()
        if left is not None and left < DESK_MIN:
            return None
        return parse_machines(self.sminos_machines(DESK_TIMEOUT if left is None else min(DESK_TIMEOUT, left)))

    def taken_names(self, servers):
        """Names a new VM must not take: live servers of every account, adoption
        records, tailnet nodes, desk machines."""
        taken = {vm["name"] for vm in servers}
        if self.paths.adopted.is_dir():
            taken |= {p.stem for p in self.paths.adopted.glob("*.json")}
        taken |= {node["name"] for node in self.tailnet()}
        listing = parse_machines(self.sminos_machines(DESK_TIMEOUT))
        taken |= set(listing.names if listing else [])
        return taken

    def user(self):
        user = self.profile.build.get("DEVCLOUD_USER")
        if not user:
            raise DriverError(FAILED, "the profile's build.env lacks DEVCLOUD_USER (the hosts' user)")
        return user

    def delete(self, entry, decided_expires=None, decided_state=None):
        """A server's delete through the provider client's ownership gate
        (§4.3, §6.1): `get` immediately before; refused unless the devcloud
        label is still there and, when given, the lease label and the state
        are still what was decided on. Returns whether the server is gone."""
        def fence(current):
            labels = current["labels"]
            if decided_expires is not None and labels.get("devcloud-expires") != decided_expires:
                return "its lease changed since it was decided on"
            if decided_state is not None and (current["state"] == "running") != (decided_state == "running"):
                return "its state changed since it was decided on"
            return None
        try:
            entry.client.delete(entry.vm["id"], fence=fence)
        except NotOwned as refusal:
            self.warn(f"devcloud vm: {refusal}")
            return False
        self.remote.forget(entry.host.alias)
        return True


# --- the world around the driver ---------------------------------------------------------

def tailnet_nodes():
    """The tailnet's peers as {name, online, tags}; [] when tailscale is not
    there to ask."""
    try:
        done = subprocess.run(["tailscale", "status", "--json"], capture_output=True, timeout=20)
        peers = json.loads(done.stdout).get("Peer") or {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []
    return [{"name": (p.get("DNSName") or p.get("HostName") or "").split(".")[0] or p.get("HostName", ""),
             "online": bool(p.get("Online")), "tags": p.get("Tags") or []} for p in peers.values()]


def _sminos(env):
    from shutil import which
    found = which("sminos", path=env.get("PATH"))
    if found:
        return found
    clone = pathlib.Path(env.get("HOME", "~")).expanduser() / (
        ".claude/plugins/marketplaces/doperpowers/sminos/skills/sminos/scripts/sminos")
    return str(clone) if clone.exists() else None


DESK_TIMEOUT = 30
DESK_MIN = 2            # a bounded run with less left asks the desk nothing


@dataclasses.dataclass(frozen=True)
class Machines:
    """`sminos machines` read: the names in its table; whether they are the
    org's directory (an enrolled machine's, rather than its table of itself
    alone); and that directory's age at most, in seconds."""
    names: list
    org: bool
    age: int


_AGE = re.compile(r"^\(the org's directory is (\d+)([smhd]) old")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_machines(stdout):
    """The shapes sminos prints (sminos.py, `cmd_machines`, `org_age_line`):
    a line saying the machine is not enrolled or has no org directory yet,
    then a table of itself; or the org's table, then, when the directory is
    older than a minute, its age, rounded down to a unit. None when there is
    no table."""
    lines = (stdout or "").splitlines()
    try:
        header = next(i for i, line in enumerate(lines) if line.split()[:2] == ["MACHINE", "STATE"])
    except StopIteration:
        return None
    names, age = [], 60
    for line in lines[header + 1:]:
        found = _AGE.match(line)
        if found:
            age = (int(found.group(1)) + 1) * _UNIT[found.group(2)]
        elif line.strip() and not line.startswith("("):
            names.append(line.split()[0])
    return Machines(names=names, org=header == 0, age=age)


def run_sminos_machines(env, timeout):
    """`sminos machines`' stdout, or None: no CLI, a failure or the timeout."""
    cli = _sminos(env)
    if not cli:
        return None
    try:
        done = subprocess.run([cli, "machines"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def session_creator(env):
    """(sminos tag, session short id) of the session the driver runs in, or
    (None, None) outside one."""
    session = env.get("CLAUDE_CODE_SESSION_ID")
    cli = _sminos(env)
    if not session or not cli:
        return None, None
    try:
        done = subprocess.run([cli, "who", "--session", session], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    match = re.search(r"#([0-9a-f]{4,})\b", done.stdout)
    if done.returncode != 0 or not match:
        return None, None
    return f"@{match.group(1)}", match.group(1)


def key_in_remote(ctx):
    """Whether this driver's public key is in the configuration repository's
    branch the hosts pull (§8.3): the boot's home step makes root's keys
    equal to that directory, so a key only on this Mac would lock the driver
    out of the host it is making. True, unchecked, when the profile is not a
    checkout of the configuration repository [host] names (a temporary
    profile, wherever it lives)."""
    profile_dir = ctx.paths.profile
    def git(*args, timeout=60):
        return subprocess.run(["git", "-C", str(profile_dir), *args], capture_output=True, text=True,
                              timeout=timeout)
    try:
        top = git("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return True
        origin = git("config", "--get", "remote.origin.url").stdout.strip()
        if _repo(origin) != _repo(ctx.profile.host.config_repo):
            ctx.warn("devcloud vm: the profile is not a checkout of the configuration repository; its driver keys "
                     "are unchecked")
            return True
        rel = (profile_dir / "driver-keys" / f"{ctx.machine}.pub").resolve().relative_to(
            pathlib.Path(top.stdout.strip()).resolve())
        branch = ctx.profile.host.config_branch
        if git("fetch", "-q", "origin", branch).returncode != 0:
            ctx.warn("devcloud vm: could not fetch the configuration repository; its driver keys are unchecked")
            return True
        remote = git("show", f"FETCH_HEAD:{rel.as_posix()}")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return True
    mine = (profile_dir / "driver-keys" / f"{ctx.machine}.pub").read_text().strip()
    return remote.returncode == 0 and remote.stdout.strip() == mine


def _repo(url):
    """A git URL as host/owner/name, so the https and scp forms compare equal."""
    url = url.strip().removesuffix("/").removesuffix(".git")
    url = re.sub(r"^[a-z+]+://(?:[^@/]+@)?", "", url)
    url = re.sub(r"^[^@/]+@([^:/]+):", r"\1/", url)
    return url.lower()
