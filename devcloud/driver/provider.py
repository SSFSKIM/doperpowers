"""The provider protocol's client (I13, §6.1, §6.2): the one place the core
runs a provider. It decides which executable an account's calls run (a
shipped provider from the plugin; a profile provider only through its passing
copy, checked against its pass record), gives it the account's credentials in
its environment only, bounds each operation, maps its exits, and shows its
stderr with the credential values scrubbed."""

import hashlib
import json
import os
import pathlib
import signal
import subprocess

from devcloudlib import redact

from . import labels as label_rules
from .errors import FAILED, REFUSED, UNUSABLE, USAGE, DriverError, NotOwned, Spent
from .profile import SHIPPED

SHIPPED_DIR = pathlib.Path(__file__).resolve().parent / "providers"
LONG = 15 * 60
SHORT = 2 * 60
LONG_OPS = ("create", "image-create", "images", "image-delete")
KINDS = ("limit", "quota", "unavailable", "other")
# What a provider inherits of the driver's environment; the rest is the account's.
INHERITED = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SSL_CERT_FILE",
             "SSL_CERT_DIR", "SYSTEMROOT")


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def pass_paths(profile_dir, account):
    providers = pathlib.Path(profile_dir) / "providers"
    return providers / ".pass" / account, providers / f"{account}.pass.json"


def not_registered(account):
    return DriverError(UNUSABLE, f"provider {account.provider} of account {account.name} is not registered (the "
                                 f"person runs devcloud vm provider register {account.name} --confirmed, then "
                                 f"devcloud vm provider test {account.name})")


def working_file(profile_dir, account):
    """The executable an account names: the plugin's for a shipped provider
    (refused when the profile shadows it), else the profile's file."""
    own = pathlib.Path(profile_dir) / "providers" / account.provider
    if account.provider in SHIPPED:
        if own.exists():
            raise DriverError(USAGE, f"the profile's providers/{account.provider} shadows the shipped provider "
                                     f"of that name; rename it")
        shipped = SHIPPED_DIR / account.provider
        if not shipped.exists():
            raise DriverError(UNUSABLE, f"the shipped provider {account.provider} is not in this plugin version")
        return shipped
    if not own.is_file():
        raise DriverError(USAGE, f"account {account.name} names provider {account.provider}, which is neither "
                                 f"shipped nor in the profile's providers/")
    return own


def usable_executable(profile_dir, account):
    """What every call of the account runs (§6.2), and the sha256 each call
    checks it against: the shipped script (no hash: it is the plugin's), or
    the profile provider's passing copy once it is registered and its copy's
    sha256 matches its pass record. The working file is not read here: a
    missing or edited one leaves the copy serving. Exit 7 otherwise."""
    if account.shipped:
        return working_file(profile_dir, account), None
    if not account.registered:
        raise not_registered(account)
    copy, record = pass_paths(profile_dir, account.name)
    try:
        recorded = json.loads(record.read_text())["sha256"]
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        recorded = None
    if not copy.is_file() or recorded is None:
        raise DriverError(UNUSABLE, f"provider {account.provider} of account {account.name} has no passing copy "
                                    f"yet (run devcloud vm provider test {account.name})")
    if sha256_file(copy) != recorded:
        raise DriverError(UNUSABLE, _changed(account))
    return copy, recorded


def _changed(account):
    return (f"account {account.name}'s passing copy no longer matches its pass record "
            f"(run devcloud vm provider test {account.name})")


class Client:
    """One account's provider. `sha256`, when given, is checked against the
    executable before every call; `budget`, when given, answers the seconds a
    bounded run has left (None outside one), which caps each call's
    credential reads and timeout, and no call starts once it is spent."""

    def __init__(self, account, executable, secrets, env=None, seed_path=None, timeouts=None, warn=None,
                 sha256=None, budget=None):
        self.account = account
        self.executable = pathlib.Path(executable)
        self.secrets = secrets
        self.base_env = env if env is not None else os.environ
        self.seed_path = seed_path
        self.timeouts = timeouts or {}
        self.warn = warn or (lambda line: None)
        self.sha256 = sha256
        self.budget = budget or (lambda: None)
        self._capabilities = None

    @property
    def name(self):
        return f"{self.account.provider}/{self.account.name}"

    def _left(self, op):
        """The bounded run's seconds left; Spent once there are none."""
        left = self.budget()
        if left is not None and left <= 0:
            raise Spent(f"provider {self.name}: {op} not started: the bounded run's time is spent")
        return left

    def environment(self, op="call"):
        env = {k: self.base_env[k] for k in INHERITED if k in self.base_env}
        env.update(self.account.vars)
        secret_values = []
        for var, secret_id in self.account.env.items():
            value = self.secrets.access(secret_id, timeout=self._left(op))
            value = value[:-1] if value.endswith("\n") else value
            env[var] = value
            secret_values.append(value)
        if self.account.provider == "gce" and self.seed_path:
            env["DEVCLOUD_SEED_FILE"] = str(self.seed_path)
        return env, secret_values

    def call(self, op, payload=None):
        payload = {} if payload is None else payload
        if op in ("create", "set-labels", "image-create"):
            label_rules.check(payload["labels"])
        self._left(op)
        env, secret_values = self.environment(op)
        timeout = self.timeouts.get(op, LONG if op in LONG_OPS else SHORT)
        left = self._left(op)
        if left is not None:
            timeout = min(timeout, left)
        if self.sha256 is not None and sha256_file(self.executable) != self.sha256:
            raise DriverError(UNUSABLE, _changed(self.account))
        proc = subprocess.Popen([str(self.executable), op], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, start_new_session=True)
        try:
            out, err = proc.communicate(json.dumps(payload).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop(proc)
            raise DriverError(FAILED, f"provider {self.name}: {op} timed out after {timeout:g} s") from None
        except BaseException:
            # An interrupt or a SIGTERM: the provider's whole group goes with the driver.
            _stop(proc)
            raise
        known = redact.Known(secret_values)
        shown = known.scrub(err.decode(errors="replace")).strip()
        if proc.returncode == 0:
            try:
                return json.loads(out)
            except ValueError:
                self._show(shown)
                raise DriverError(FAILED, f"provider {self.name}: {op} printed something that is not JSON") from None
        if proc.returncode == 3:
            try:
                refusal = json.loads(out)
                kind, error = refusal["kind"], refusal["error"]
                if kind not in KINDS or not isinstance(error, str):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                self._show(shown)
                raise DriverError(FAILED, f"provider {self.name}: {op} refused without a valid refusal") from None
            self._show(shown)
            line = known.scrub(error.splitlines()[0] if error else "")
            raise DriverError(REFUSED, f"provider {self.name} refused {op} ({kind}): {line}")
        self._show(shown)
        raise DriverError(FAILED, f"provider {self.name}: {op} failed (exit {proc.returncode})")

    def _show(self, stderr):
        for line in stderr.splitlines()[-20:]:
            self.warn(f"  {self.account.provider}: {line}")

    # --- the operations, their shapes checked ------------------------------------

    def info(self):
        if self._capabilities is None:
            answer = self.call("info")
            if not isinstance(answer, dict) or answer.get("protocol") != 1 or not isinstance(
                    answer.get("capabilities"), list):
                raise DriverError(FAILED, f"provider {self.name}: info is not protocol 1")
            self._capabilities = set(answer["capabilities"])
        return self._capabilities

    def has(self, capability):
        return capability in self.info()

    def types(self, location):
        answer = self.call("types", {"location": location})
        if not isinstance(answer, list) or not all(isinstance(t, dict) and "type" in t for t in answer):
            raise DriverError(FAILED, f"provider {self.name}: types is not a list of types")
        return answer

    def create(self, request):
        return _vm(self, self.call("create", request), "create")

    def list(self):
        answer = self.call("list")
        if not isinstance(answer, list):
            raise DriverError(FAILED, f"provider {self.name}: list is not a list")
        return [_vm(self, vm, "list") for vm in answer]

    def get(self, server_id):
        answer = self.call("get", {"id": str(server_id)})
        return None if answer is None else _vm(self, answer, "get")

    # --- the ownership gate: every delete and relabel reads its target again first ---

    def _owned(self, server_id, what):
        current = self.get(server_id)
        if current is None:
            raise NotOwned(f"provider {self.name}: server {server_id} is gone; nothing to {what}")
        if "devcloud" not in current["labels"]:
            raise NotOwned(f"{current['name']} lost its devcloud label; not going to {what} it")
        return current

    def set_labels(self, server_id, labels, merge=False):
        """`set-labels` after a `get` that still finds the devcloud label;
        `merge` lays `labels` over the labels read then, else they are the
        whole set."""
        current = self._owned(server_id, "relabel")
        full = {**current["labels"], **labels} if merge else labels
        return _vm(self, self.call("set-labels", {"id": str(server_id), "labels": full}), "set-labels")

    def delete(self, server_id, fence=None):
        """`delete` after a `get`: False when the server is already gone;
        NotOwned unless it still carries the devcloud label and `fence`
        (current Vm → why not, or None) passes."""
        current = self.get(server_id)
        if current is None:
            return False
        if "devcloud" not in current["labels"]:
            raise NotOwned(f"{current['name']} lost its devcloud label; not deleting it")
        why = fence(current) if fence else None
        if why:
            raise NotOwned(f"{current['name']}: {why}; not deleting it")
        self.call("delete", {"id": str(server_id)})
        return True

    def image_create(self, server_id, name, labels):
        return _image(self, self.call("image-create", {"id": str(server_id), "name": name, "labels": labels}))

    def images(self):
        answer = self.call("images")
        if not isinstance(answer, list):
            raise DriverError(FAILED, f"provider {self.name}: images is not a list")
        return [_image(self, image) for image in answer]

    def image_delete(self, image_id, labels):
        """The image fence (I13 has no image `get`): `images` again, and the
        delete only while the id is still listed with the labels the decision
        used. False when it is already gone."""
        current = next((i for i in self.images() if i["id"] == str(image_id)), None)
        if current is None:
            return False
        if current["labels"] != labels:
            raise NotOwned(f"image {current['name']}'s labels changed since it was decided on; not deleting it")
        self.call("image-delete", {"id": str(image_id)})
        return True


def _stop(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.communicate()


VM_KEYS = ("id", "name", "location", "type", "labels", "public_ipv4", "state", "created")


def _vm(client, vm, op):
    if not isinstance(vm, dict) or not all(k in vm for k in VM_KEYS) or not isinstance(vm["labels"], dict):
        raise DriverError(FAILED, f"provider {client.name}: {op} answered something that is not a Vm")
    try:
        return dict(vm, id=str(vm["id"]), created=int(vm["created"]))
    except (TypeError, ValueError):
        raise DriverError(FAILED, f"provider {client.name}: {op} gave a Vm without a Unix created time") from None


def _image(client, image):
    if not isinstance(image, dict) or not all(k in image for k in ("id", "name", "labels", "created")):
        raise DriverError(FAILED, f"provider {client.name}: an image is not an Image")
    return dict(image, id=str(image["id"]), created=int(image["created"]))
