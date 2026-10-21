"""`provider test` and `provider register` (§6.2).

Registration records the person's approval of a profile provider's
executable (its sha256, on the account in driver.toml) before anything runs
it with a credential. The test runs the working file — from a private copy of
the exact bytes it hashed — through the conformance sequence; a pass copies
those bytes to `providers/.pass/<account>` and records their sha256 beside
it, and every later call of the account runs that copy. The test deletes its
own server and image in a finally block: the reaper never runs a provider
with no passing copy, so a leftover is the test's to report."""

import datetime
import hashlib
import json
import pathlib
import re
import shutil
import tempfile

from . import provider as provider_mod
from .errors import CAP, FAILED, USAGE, DriverError

TEST_LABELS = ("devcloud", "devcloud-test")


class Failed(Exception):
    def __init__(self, step, why):
        super().__init__(f"{step}: {why}")
        self.step = step


def _smallest(types):
    offered = [t for t in types if t.get("available")]
    if not offered:
        raise Failed("types", "no type is available in the account's location")
    return min(offered, key=lambda t: (t.get("vcpus", 0), t.get("memory_gb", 0), t.get("disk_gb", 0),
                                       t.get("hourly_price") if t.get("hourly_price") is not None else float("inf")))


def _wait(ctx, window, poll, check):
    end = ctx.clock() + window
    while True:
        if check():
            return True
        if ctx.clock() >= end:
            return False
        ctx.sleep(poll)


def test(ctx, account_name, gone_window=600, running_window=300, poll=5):
    account = ctx.profile.account(account_name)
    if not account.shipped and not account.registered:
        raise provider_mod.not_registered(account)
    working = provider_mod.working_file(ctx.paths.profile, account)
    data = working.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(prefix="devcloud-provider-test-") as tmp:
        exe = pathlib.Path(tmp) / account.provider
        exe.write_bytes(data)
        exe.chmod(0o755)
        client = ctx.client(account, executable=exe)
        _sequence(ctx, client, account, gone_window, running_window, poll)
    if account.shipped:
        ctx.say("pass (a shipped provider: it runs from the plugin, no passing copy is kept)")
        return 0
    copy, record = provider_mod.pass_paths(ctx.paths.profile, account.name)
    copy.parent.mkdir(parents=True, exist_ok=True)
    staged = copy.with_name(f".{copy.name}.new")
    staged.write_bytes(data)
    staged.chmod(0o755)
    staged.replace(copy)
    record.write_text(json.dumps({"sha256": sha, "tested": _utc(ctx.clock()), "account": account.name,
                                  "provider": account.provider}, indent=1) + "\n")
    ctx.say(f"pass recorded (sha256 {sha[:12]}…): {copy}")
    return 0


def _utc(now):
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sequence(ctx, client, account, gone_window, running_window, poll):
    run_id = f"pt-{datetime.datetime.fromtimestamp(ctx.clock(), datetime.timezone.utc):%Y%m%d%H%M}-{ctx.token_hex()}"
    labels = {"devcloud": "test", "devcloud-test": run_id}
    made = {"server": None, "image": None}     # what exists until the test sees it gone
    try:
        _steps(ctx, client, account, labels, made, gone_window, running_window, poll)
        problem = None
    except Failed as failure:
        problem = f"provider test of {account.name} failed at {failure}"
    except DriverError as error:
        problem = f"provider test of {account.name} failed at the provider: {error}"
    leftovers = _clean(ctx, client, made["server"], made["image"])
    if leftovers:
        problem = (f"{problem}; " if problem else "provider test: ") + f"it could not clean up: {', '.join(leftovers)}"
    if problem:
        raise DriverError(FAILED, problem)


def _steps(ctx, client, account, labels, made, gone_window, running_window, poll):
    capabilities = client.info()
    ctx.say(f"info ok ({', '.join(sorted(capabilities)) or 'no capabilities'})")
    type_ = _smallest(client.types(account.location))
    ctx.say(f"types ok ({type_['type']} in {account.location})")
    name = f"dc-ptest-{ctx.token_hex()}"
    request = {"name": name, "type": type_["type"], "location": account.location, "image": None, "labels": labels,
               "ssh_public_keys": ctx.driver_keys(), "disk_gb": None, "spot": False,
               "user_data": "#cloud-config\n{}\n" if "user_data" in capabilities else None}
    made["server"] = server = client.create(request)
    ctx.say(f"create ok ({name}, id {server['id']})")
    listed = client.list()
    if not any(vm["id"] == server["id"] for vm in listed):
        raise Failed("list", "the new server is not listed")
    if any("devcloud" not in vm["labels"] for vm in listed):
        raise Failed("list", "it lists a server without the devcloud label")
    ctx.say("list ok")
    got = client.get(server["id"])
    if got is None or got["labels"] != labels:
        raise Failed("get", f"labels {got and got['labels']} are not the ones created, verbatim")
    if not _wait(ctx, running_window, poll, lambda: (client.get(server["id"]) or {}).get("state") == "running"):
        raise Failed("running", "the server never reported state running")
    ctx.say("get ok (labels verbatim, running)")
    changed = {**labels, "devcloud-held": "1"}
    for want in (changed, labels):
        answer = client.set_labels(server["id"], want)
        now = client.get(server["id"])
        if answer["labels"] != want or now is None or now["labels"] != want:
            raise Failed("set-labels", "the full label set did not round-trip")
    ctx.say("set-labels ok")
    if "images" in capabilities:
        made["image"] = image = client.image_create(server["id"], f"dc-ptest-img-{ctx.token_hex()}", labels)
        found = [i for i in client.images() if i["id"] == image["id"]]
        if not found or found[0]["labels"] != labels:
            raise Failed("images", "the new image is not listed with its labels verbatim")
        client.image_delete(image["id"])
        if not _wait(ctx, gone_window, poll, lambda: all(i["id"] != image["id"] for i in client.images())):
            raise Failed("images", "the deleted image is still listed")
        made["image"] = None
        ctx.say("images ok")
    client.delete(server["id"])
    ctx.say("delete ok")
    if not _wait(ctx, gone_window, poll, lambda: client.get(server["id"]) is None
                 and all(vm["id"] != server["id"] for vm in client.list())):
        raise Failed("gone", "the deleted server is still there (get or list)")
    made["server"] = None
    ctx.say("gone ok")


def _clean(ctx, client, server, image):
    """Deletes what the test made and still exists; returns the leftovers,
    each named on stderr. The recheck is the core's: the devcloud label."""
    leftovers = []
    if image is not None:
        try:
            client.image_delete(image["id"])
        except DriverError:
            leftovers.append(f"leftover image {image['id']}")
    if server is not None:
        try:
            current = client.get(server["id"])
            if current is not None and "devcloud" in current["labels"]:
                client.delete(server["id"])
            elif current is not None:
                leftovers.append(f"leftover server {server['id']} (it lost its devcloud label; not deleted)")
        except DriverError:
            leftovers.append(f"leftover server {server['id']}")
    for line in leftovers:
        ctx.warn(f"devcloud vm provider test: {line}: delete it by hand")
    return leftovers


def register(ctx, account_name, confirmed):
    """Records the sha256 of the account's working file as `registered` on
    the account in driver.toml: the person's one confirmation (§6.2)."""
    account = ctx.profile.account(account_name)
    if account.shipped:
        raise DriverError(USAGE, f"{account.provider} is a shipped provider: it needs no registration")
    if not confirmed:
        raise DriverError(CAP, f"registering provider {account.provider} lets it run with account "
                               f"{account.name}'s credential and spend the person's money: ask the person, then "
                               "pass --confirmed")
    working = provider_mod.working_file(ctx.paths.profile, account)
    sha = provider_mod.sha256_file(working)
    path = ctx.profile.toml
    path.write_text(set_registered(path.read_text(), account.name, sha))
    ctx.reload_profile()
    if ctx.profile.account(account.name).registered != sha:
        raise DriverError(FAILED, "a bug: driver.toml did not take the registration")
    ctx.say(f"registered {account.provider} for account {account.name} (sha256 {sha[:12]}…); next: "
            f"devcloud vm provider test {account.name}")
    return 0


def set_registered(text, account_name, sha):
    """driver.toml's text with `registered` set in the named account's
    [[account]] block, every other line as it was."""
    lines = text.splitlines(keepends=True)
    blocks, start = [], None
    for i, line in enumerate(lines):
        if re.match(r"\s*\[", line):
            if start is not None:
                blocks.append((start, i))
            start = i if re.match(r"\s*\[\[\s*account\s*\]\]", line) else None
    if start is not None:
        blocks.append((start, len(lines)))
    name_line = re.compile(r'\s*name\s*=\s*"' + re.escape(account_name) + r'"\s*(#.*)?$')
    for begin, end in blocks:
        names = [i for i in range(begin, end) if name_line.match(lines[i].rstrip("\n"))]
        if not names:
            continue
        new = f'registered = "{sha}"\n'
        existing = [i for i in range(begin, end) if re.match(r"\s*registered\s*=", lines[i])]
        if existing:
            lines[existing[0]] = new
        else:
            at = names[0] + 1
            if not lines[names[0]].endswith("\n"):
                lines[names[0]] += "\n"
            lines.insert(at, new)
        return "".join(lines)
    raise DriverError(USAGE, f"driver.toml has no [[account]] named {account_name}")
