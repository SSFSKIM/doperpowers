"""One command's world: where the profile, the seed and the driver's own
state live (§8), Secret Manager, the providers of every account, SSH to the
hosts, the tailnet and the desk. Commands take a Context; tests build one
from stand-ins."""

import dataclasses
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time

from . import labels as label_rules
from . import profile as profile_mod
from . import provider
from .errors import FAILED, UNUSABLE, DriverError
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
                 out=sys.stdout, err=sys.stderr, machine=None, tailnet=None, desk=None, creator=None,
                 timeouts=None, plugin=PLUGIN_DIR, key_pushed=None):
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
        self.desk = desk or desk_machines
        self.creator = creator or (lambda: session_creator(self.env))
        self.key_pushed = key_pushed or (lambda: key_in_remote(self))

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

    def say(self, line=""):
        print(line, file=self.out, flush=True)

    def warn(self, line):
        print(line, file=self.err, flush=True)

    # --- providers --------------------------------------------------------------------

    def client(self, account, executable=None):
        """The account's provider; exit 7 when it is not usable."""
        if executable is None and account.name in self._clients:
            return self._clients[account.name]
        exe = executable or provider.usable_executable(self.paths.profile, account)
        client = provider.Client(account, exe, self.secrets, env=self.env, seed_path=self.paths.seed,
                                 timeouts=self.timeouts, warn=self.warn)
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

    def fleet(self, quiet=False, kinds=("vm",)):
        """Every labeled server of every usable account whose devcloud label
        is one of `kinds`; a provider that fails is named and skipped."""
        entries = []
        for account, client in self.usable(quiet=quiet):
            try:
                vms = client.list()
            except DriverError as error:
                self.warn(f"devcloud vm: account {account.name}: {error}")
                continue
            entries += [Entry(account, client, vm) for vm in vms
                        if kinds is None or vm["labels"].get("devcloud") in kinds]
        return entries

    def find(self, name):
        for entry in self.fleet(quiet=True):
            if entry.vm["name"] == name:
                return entry
        raise DriverError(FAILED, f"no VM named {name} in any usable account")

    def user(self):
        user = self.profile.build.get("DEVCLOUD_USER")
        if not user:
            raise DriverError(FAILED, "the profile's build.env lacks DEVCLOUD_USER (the hosts' user)")
        return user

    def delete(self, entry, decided_expires=None, decided_state=None):
        """The label recheck, then the delete (§4.3, §6.1): `get` immediately
        before; refused unless the devcloud label is still there and, when
        given, the lease label and the state are still what was decided on.
        Returns whether it deleted."""
        current = entry.client.get(entry.vm["id"])
        if current is None:
            self.remote.forget(entry.host.alias)
            return True
        labels = current["labels"]
        if "devcloud" not in labels:
            self.warn(f"devcloud vm: {current['name']} lost its devcloud label; not deleting it")
            return False
        if decided_expires is not None and labels.get("devcloud-expires") != decided_expires:
            self.warn(f"devcloud vm: {current['name']}'s lease changed since it was decided on; not deleting it")
            return False
        if decided_state is not None and (current["state"] == "running") != (decided_state == "running"):
            self.warn(f"devcloud vm: {current['name']}'s state changed since it was decided on; not deleting it")
            return False
        entry.client.delete(entry.vm["id"])
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


def desk_machines(env=None):
    """The desk's machine names, when this machine is enrolled; [] otherwise."""
    env = env or os.environ
    cli = _sminos(env)
    if not cli:
        return []
    try:
        done = subprocess.run([cli, "machines"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if done.returncode != 0:
        return []
    return [line.split()[0] for line in done.stdout.splitlines()[1:] if line.strip() and not line.startswith("(")]


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
    out of the host it is making. True when the profile is not a checkout
    (a temporary profile, whose hosts the person points elsewhere)."""
    profile_dir = ctx.paths.profile
    def git(*args, timeout=60):
        return subprocess.run(["git", "-C", str(profile_dir), *args], capture_output=True, text=True,
                              timeout=timeout)
    try:
        top = git("rev-parse", "--show-toplevel")
        if top.returncode != 0:
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
