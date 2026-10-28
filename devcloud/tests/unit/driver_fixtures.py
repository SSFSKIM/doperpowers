"""Shared stand-ins for the driver's tests: a profile on disk, Secret Manager,
SSH to the hosts, the tailnet and the desk, a clock. The provider is the real
protocol client running the stand-in executable `fixtures/provider`."""
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest

import _path  # noqa: F401
from driver import context, hostctl
from driver.ssh import Result

FIXTURES = _path.DEVCLOUD / "tests" / "fixtures"
FAKE_PROVIDER = FIXTURES / "provider"
NOW = 1_792_000_000
TOKEN = "made-up-provider-token-Zq81Lr5Tx0Kp"
TS_CLIENT = "tskey-client-kmadeup-" + "made-up" * 3
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMadeUpDriverKeyForTestsOnly000000000000 devcloud-testmac"

DRIVER_TOML = """\
[caps]
throwaway = 3
lease_default = "12h"
lease_max = "72h"
vcpu_max = 8
max_disk_gb = 200

[defaults]
account = "main"

[host]
sm_project = "example-project"
config_repo = "https://github.com/example/config.git"
config_branch = "main"
config_token_secret = "config-token"
tailscale_secret = "ts-oauth"

[[account]]
name = "main"
provider = "fake"
location = "here"
type = "medium"
env = { FAKE_TOKEN = "fake-token-secret" }
vars = { FAKE_PROVIDER_STATE = "{state}" }
registered = "{registered}"
"""


class FakeSecrets:
    def __init__(self, values=None):
        self.values = values if values is not None else {"fake-token-secret": TOKEN}
        self.reads = []
        self.timeouts = []

    def access(self, secret_id, timeout=None):
        self.reads.append(secret_id)
        self.timeouts.append(timeout)
        if secret_id not in self.values:
            from driver.errors import DriverError
            raise DriverError(1, f"Secret Manager has no secret {secret_id}")
        return self.values[secret_id]


class FakeTailnetApi:
    """The Tailscale API as the driver's tailnet.remove sees it: the devices
    it lists, and each call in order."""

    def __init__(self, devices=None, scopes=("auth_keys", "devices:core")):
        self.devices_listed = list(devices or [])
        self.scopes = list(scopes)
        self.calls = []
        self.fail = {}              # "token" | "devices" | a node id -> the StepError message

    def _maybe_fail(self, what):
        if what in self.fail:
            from devcloudlib.proc import StepError
            raise StepError(self.fail[what])

    def token(self, secret, timeout):
        self.calls.append(("token", secret))
        self._maybe_fail("token")
        from devcloudlib import tsapi
        return tsapi.Token("made-up-access-token", self.scopes)

    def devices(self, tok, timeout):
        self.calls.append(("devices",))
        self._maybe_fail("devices")
        return [dict(d) for d in self.devices_listed]

    def delete_node(self, tok, node_id, timeout):
        self.calls.append(("delete", node_id))
        self._maybe_fail(node_id)
        before = len(self.devices_listed)
        self.devices_listed = [d for d in self.devices_listed if d.get("nodeId") != node_id]
        return "removed" if len(self.devices_listed) < before else "already gone"

    def deleted(self):
        return [c[1] for c in self.calls if c[0] == "delete"]


def ts_device(name, node_id, tags=("tag:devcloud",), hostname=None):
    """A device as the API lists it."""
    return {"nodeId": node_id, "hostname": hostname or name, "name": f"{name}.example-tailnet.ts.net",
            "tags": list(tags)}


class FakeRemote:
    """SSH to the hosts. Rules match a command by substring (and, when
    given, the target); the first rule that matches answers, and a rule with
    `times` answers that many calls. Unmatched commands answer 0, empty."""

    def __init__(self):
        self.calls = []
        self.rules = []
        self.forgotten = []

    def on(self, needle, code=0, out="", err="", marker=False, target=None, times=None, fn=None):
        self.rules.append({"needle": needle, "code": code, "out": out, "err": err, "marker": marker,
                           "target": target, "times": times, "fn": fn})

    def _answer(self, kind, target, alias, command, user, input, person=False):
        self.calls.append({"kind": kind, "target": target, "alias": alias, "command": command, "user": user,
                           "input": input, "person": person})
        for rule in self.rules:
            if rule["needle"] not in command or (rule["target"] and rule["target"] != target):
                continue
            if rule["times"] is not None:
                if rule["times"] == 0:
                    continue
                rule["times"] -= 1
            if rule["fn"]:
                return rule["fn"](target, command)
            return Result(rule["code"], rule["out"], rule["err"], rule["marker"])
        return Result(0, "", "", False)

    def ensure_key(self):
        return KEY

    def run(self, target, alias, command, *, user="root", input=None, timeout=60, connect_timeout=10, person=False):
        return self._answer("run", target, alias, command, user, input, person)

    def stream(self, target, alias, command, *, user="root", timeout=60, marker=None):
        return self._answer("stream", target, alias, command, user, None)

    def interactive(self, target, alias, command, *, user="root"):
        return self._answer("interactive", target, alias, command or "", user, None).code

    def forget(self, alias):
        self.forgotten.append(alias)

    def commands(self, needle=None):
        return [c["command"] for c in self.calls if needle is None or needle in c["command"]]


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class DriverBase(unittest.TestCase):
    """A profile with one account on the stand-in provider, registered and
    with a passing copy, so it is usable."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="devcloud-driver-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.profile_dir = self.tmp / "profile"
        (self.profile_dir / "providers" / ".pass").mkdir(parents=True)
        (self.profile_dir / "driver-keys").mkdir()
        (self.profile_dir / "build.env").write_text("DEVCLOUD_USER=dev\nDEVCLOUD_UID=1001\nDEVCLOUD_HOME=/Users/dev\n")
        self.state_file = self.tmp / "provider-state.json"
        self.state_file.write_text(json.dumps({"servers": [], "images": [], "deleted": [], "calls": [], "behavior": {}}))
        working = self.profile_dir / "providers" / "fake"
        shutil.copy(FAKE_PROVIDER, working)
        working.chmod(0o755)
        self.sha = context.sha256_file(working)
        (self.profile_dir / "driver.toml").write_text(
            DRIVER_TOML.replace("{state}", str(self.state_file)).replace("{registered}", self.sha))
        self.pass_copy()
        self.seed = self.tmp / "seed.json"
        self.seed.write_text('{"type": "service_account"}')
        self.state_dir = self.tmp / "state"
        self.paths = context.Paths(profile=self.profile_dir, state=self.state_dir, seed=self.seed)
        self.secrets = FakeSecrets(dict(FakeSecrets().values, **{"ts-oauth": TS_CLIENT + "\n"}))
        self.tailnet_api = FakeTailnetApi()
        self.remote = FakeRemote()
        self.clock = Clock()
        self.tailnet_nodes = []
        self.desk_machines = []         # the names an enrolled driver's current listing shows
        self.desk_output = None         # else `sminos machines`' whole stdout; None for neither: no sminos
        self.desk_timeouts = []
        self.out, self.err = io.StringIO(), io.StringIO()
        self.ctx = self.make_ctx()

    def sminos_machines(self, timeout):
        """`sminos machines` as the CLI prints it (see test_driver_desk)."""
        self.desk_timeouts.append(timeout)
        if self.desk_output is not None:
            return self.desk_output
        if not self.desk_machines:
            return None
        return "MACHINE  STATE  LIVE  PROJECTS\n" + "".join(f"{n}  online  0  -\n" for n in self.desk_machines)

    def pass_copy(self):
        working = self.profile_dir / "providers" / "fake"
        copy = self.profile_dir / "providers" / ".pass" / "main"
        shutil.copy(working, copy)
        copy.chmod(0o755)
        (self.profile_dir / "providers" / "main.pass.json").write_text(
            json.dumps({"sha256": context.sha256_file(copy)}))

    def make_ctx(self, **kw):
        defaults = dict(paths=self.paths, secrets=self.secrets, remote=self.remote, clock=self.clock,
                        sleep=self.clock.sleep, out=self.out, err=self.err, machine="testmac",
                        tailnet=lambda: list(self.tailnet_nodes), sminos_machines=self.sminos_machines,
                        creator=lambda: ("@abcd1234", "abcd1234"), env={"PATH": os.environ["PATH"]},
                        key_pushed=lambda: True, host_file=lambda project: (None, "no devenv/host.toml here"),
                        tailnet_api=self.tailnet_api)
        defaults.update(kw)
        return context.Context(**defaults)

    # the stand-in provider's state
    def state(self):
        return json.loads(self.state_file.read_text())

    def behave(self, **behavior):
        state = self.state()
        state["behavior"].update(behavior)
        self.state_file.write_text(json.dumps(state))

    def add_server(self, name, labels, state="running", created=NOW - 3600, ipv4="203.0.113.9", sid=None):
        data = self.state()
        sid = sid or str(500 + len(data["servers"]) + len(data.get("deleted", [])))
        data["servers"].append({"id": sid, "name": name, "location": "here", "type": "medium", "labels": labels,
                                "public_ipv4": ipv4, "state": state, "created": created})
        self.state_file.write_text(json.dumps(data))
        return sid

    def servers(self):
        return {s["name"]: s for s in self.state()["servers"]}

    def ops(self):
        return [c["op"] for c in self.state()["calls"]]


def vm_labels(expires=None, lifetime="ttl", confirmed=False, **extra):
    labels = {"devcloud": "vm", "devcloud-lifetime": lifetime, "devcloud-by": "testmac"}
    if expires is not None:
        labels["devcloud-expires"] = str(expires)
    if confirmed:
        labels["devcloud-confirmed"] = "1"
    labels.update(extra)
    return labels


def status_json(steps_ok=None, failed=None, lifecycle=None):
    """A host's status.json: its first `steps_ok` steps ok (every step when None)."""
    from devcloudlib import status
    steps = [{"name": n, "state": "ok", "at": "t", "detail": ""} for n in status.STEPS[:steps_ok]]
    if failed:
        steps.append({"name": failed, "state": "failed", "at": "t", "detail": "it broke"})
    data = {"steps": steps}
    if lifecycle:
        data["lifecycle"] = {"op": "depart", "state": lifecycle, "at": "t", "detail": "", "steps": []}
    return json.dumps(data)


READY = hostctl.READY
