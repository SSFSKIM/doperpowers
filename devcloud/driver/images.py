"""Images (§7): `devcloud vm image build` bakes the plugin's recipe on a
builder and records it through the provider as an image labeled with the
recipe hash; `up` uses the newest current one (§3 step 5); `image ls`; and the
decision behind the reaper's daily build.

A builder gets the driver keys and nothing else: never a seed, a descriptor
or a secret, which is why its structural check (`bake_check`) suffices where
the container image needs the parent's known-value scan. A bake that fails
labels its builder `devcloud-bake=failed-<step>` and deletes it; the reaper
deletes any builder older than 2 hours regardless."""

import datetime
import json
import pathlib

from . import bake_check, compose, hostctl, names
from .context import Entry
from .errors import FAILED, REFUSED, DriverError

BUILD_EVERY = 24 * 3600     # the reaper's build, per account, at most this often
SSH_WAIT = 5 * 60
OFF_WAIT = 5 * 60
POLL = 5
# What makes one machine's disk every VM's first boot: cloud-init runs again
# (its per-instance state gone, new SSH host keys), a new machine id, a new
# tailnet machine key, no driver key in root's authorized_keys (each VM's
# create authorizes the keys of its day), no recipe source. Then power off,
# queued so the command returns before the connection goes.
CLEAN = ("cloud-init clean --logs --machine-id --seed && "
         "{ systemctl stop tailscaled || true; } && rm -f /var/lib/tailscale/tailscaled.state && "
         "rm -f /etc/ssh/ssh_host_* && rm -rf /opt/devcloud-src /root/.ssh/authorized_keys && sync && "
         "systemctl --no-block poweroff")


def current(images, recipe):
    """The newest image (`devcloud=image`) whose recipe hash is `recipe`, or None."""
    ours = [i for i in images if i["labels"].get("devcloud") == "image" and i["labels"].get("devcloud-recipe") == recipe]
    return max(ours, key=lambda i: (i["created"], i["id"]), default=None)


def builder_type(types):
    """The smallest available type whose disk is the least the provider
    offers, so the image fits every type (§7)."""
    offered = [t for t in types if t.get("available")]
    if not offered:
        raise DriverError(REFUSED, "the provider offers no available type for a builder here")
    least = min(t["disk_gb"] for t in offered)
    return min((t for t in offered if t["disk_gb"] == least),
               key=lambda t: (t["vcpus"], t.get("memory_gb") or 0, t.get("hourly_price") or 0, t["type"]))


def needs_build(images, builders, recipe, last, now):
    """The reaper's daily build (§7, M4): an account lacking a current image,
    with no builder of its own alive, last tried more than a day ago."""
    if current(images, recipe) is not None or builders:
        return False
    return last is None or now - last >= BUILD_EVERY


# --- image build ---------------------------------------------------------------------------

def _accounts(ctx, account_name):
    """The (account, client) pairs to build for: the one named, which must
    have images, else every usable account whose provider has them."""
    if account_name:
        account = ctx.profile.account(account_name)
        client = ctx.client(account)
        if not client.has("images"):
            raise DriverError(REFUSED, f"provider {account.provider} of account {account.name} has no images "
                                       "capability: its VMs always take the slow path")
        return [(account, client)]
    pairs = [(a, c) for a, c in ctx.usable() if c.has("images")]
    if not pairs:
        raise DriverError(REFUSED, "no usable account's provider has the images capability")
    return pairs


def build_command(ctx, account_name=None):
    """`image build [--account A]`: one image for the account named, else for
    each usable account whose provider has images."""
    pairs = _accounts(ctx, account_name)
    if len(pairs) == 1:
        build(ctx, *pairs[0])
        return 0
    failed = False
    for account, client in pairs:
        try:
            build(ctx, account, client)
        except DriverError as error:
            ctx.warn(f"devcloud vm image build: account {account.name}: {error}")
            failed = True
    return 1 if failed else 0


def _stamp(now):
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y%m%d%H%M")


def build(ctx, account, client):
    """Bakes one image for `account` and returns it (an I13 Image)."""
    recipe = compose.recipe_hash(ctx.plugin)
    type_ = builder_type(client.types(account.location))
    keys = ctx.driver_keys()
    taken = {vm["name"] for vm in client.list()}
    name = names.draw("bake", taken, ctx.token_hex)
    test_run = ctx.env.get("DEVCLOUD_TEST_RUN")
    labels = {"devcloud": "builder", "devcloud-by": ctx.machine, "devcloud-recipe": recipe}
    if test_run:
        labels["devcloud-test"] = test_run
    user_data = compose.user_data(None, keys) if client.has("user_data") else None
    vm = client.create({"name": name, "type": type_["type"], "location": account.location, "image": None,
                        "labels": labels, "ssh_public_keys": keys, "user_data": user_data, "disk_gb": None,
                        "spot": False})
    entry = Entry(account, client, vm)
    host = entry.host
    ctx.say(f"builder   {name} (id {vm['id']}, {type_['type']} in {account.location}) for account {account.name}")
    step = "ssh"
    try:
        address = host.public or hostctl.public_address(ctx, entry)
        hostctl.wait_ssh(ctx, address, host.alias, ctx.clock() + SSH_WAIT)
        step = "cloud-init"
        hostctl.wait_cloud_init(ctx, address, host.alias)
        step = "setup"
        hostctl.install_recipe(ctx, address, host.alias, ctx.profile.build)
        step = "check"
        check(ctx, address, host.alias)
        step = "clean"
        clean(ctx, address, host.alias)
        step = "poweroff"
        wait_off(ctx, entry)
        step = "image"
        image_labels = {"devcloud": "image", "devcloud-recipe": recipe, "devcloud-by": ctx.machine}
        if test_run:
            image_labels["devcloud-test"] = test_run
        made = client.image_create(vm["id"], f"dc-img-{recipe}-{_stamp(ctx.clock())}", image_labels)
    except BaseException as error:
        gone = _discard(ctx, entry, step)
        if isinstance(error, DriverError):
            left = ("the builder is deleted" if gone else
                    f"the builder (id {vm['id']}) is left; the reaper deletes builders older than 2 hours")
            raise DriverError(error.code, f"the bake of {name} failed at {step}: {error}; {left}") from None
        raise
    gone = _delete(ctx, entry)
    ctx.say(f"image     {made['name']} (id {made['id']}, recipe {recipe}) for account {account.name}")
    if not gone:
        raise DriverError(FAILED, f"image {made['name']} is recorded, but its builder {name} (id {vm['id']}) "
                                  "was not deleted; the reaper deletes builders older than 2 hours")
    return made


def check(ctx, address, key_alias):
    """The structural check, run on the builder (§7)."""
    source = pathlib.Path(bake_check.__file__).read_bytes()
    result = ctx.remote.run(address, key_alias, "python3 - /", input=source, timeout=120)
    if result.code == 1:
        found = [line.split(" ", 1)[1] for line in result.out.splitlines() if line.startswith("forbidden ")]
        raise DriverError(FAILED, "the builder holds what an image must not: " + (", ".join(found) or "(unnamed)"))
    if result.code != 0:
        raise DriverError(FAILED, f"the structural check did not run (exit {result.code})")


def clean(ctx, address, key_alias):
    result = ctx.remote.run(address, key_alias, CLEAN, timeout=300)
    # 255: the connection went with the poweroff, which is what was asked for.
    if result.code not in (0, 255):
        raise DriverError(FAILED, f"cleaning the builder failed (exit {result.code})")


def wait_off(ctx, entry):
    deadline = ctx.clock() + OFF_WAIT
    while True:
        vm = entry.client.get(entry.vm["id"])
        if vm is None:
            raise DriverError(FAILED, f"the builder {entry.vm['name']} is gone")
        if vm["state"] != "running":
            return
        if ctx.clock() >= deadline:
            raise DriverError(FAILED, f"the builder {entry.vm['name']} did not power off within "
                                      f"{OFF_WAIT // 60} minutes")
        ctx.sleep(POLL)


def _discard(ctx, entry, step):
    """A failed bake: the builder labeled with the step, then deleted.
    Whether it is gone."""
    try:
        entry.client.set_labels(entry.vm["id"], {"devcloud-bake": f"failed-{step}"}, merge=True)
    except DriverError as error:
        ctx.warn(f"devcloud vm image build: labeling {entry.vm['name']} failed-{step}: {error}")
    if not _delete(ctx, entry):
        ctx.warn(f"devcloud vm image build: the builder {entry.vm['name']} (id {entry.vm['id']}) is left; the "
                 "reaper deletes builders older than 2 hours")
        return False
    return True


def _delete(ctx, entry):
    try:
        return ctx.delete(entry)
    except DriverError as error:
        ctx.warn(f"devcloud vm image build: deleting {entry.vm['name']}: {error}")
        return False


# --- image ls ------------------------------------------------------------------------------

def ls(ctx):
    recipe = compose.recipe_hash(ctx.plugin)
    rows = [("ACCOUNT", "NAME", "ID", "RECIPE", "CREATED", "")]
    for account, client in ctx.usable():
        if not client.has("images"):
            continue
        listed = [i for i in client.images() if i["labels"].get("devcloud") == "image"]
        newest = current(listed, recipe)
        for i in sorted(listed, key=lambda i: (i["created"], i["id"]), reverse=True):
            created = datetime.datetime.fromtimestamp(i["created"], datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            rows.append((account.name, i["name"] or "-", i["id"], i["labels"].get("devcloud-recipe", "-"), created,
                         "current" if newest is not None and i["id"] == newest["id"] else ""))
    widths = [max(len(r[c]) for r in rows) for c in range(len(rows[0]))]
    for r in rows:
        ctx.say("  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip())
    ctx.say(f"(the plugin's recipe is {recipe})")
    return 0


# --- the reaper's daily build: when each account was last tried ---------------------------

def _builds_file(ctx):
    return ctx.paths.state / "image-builds.json"


def last_build(ctx, account_name):
    try:
        return json.loads(_builds_file(ctx).read_text()).get(account_name)
    except (FileNotFoundError, ValueError, AttributeError):
        return None


def record_build(ctx, account_name, when):
    path = _builds_file(ctx)
    try:
        record = json.loads(path.read_text())
        if not isinstance(record, dict):
            record = {}
    except (FileNotFoundError, ValueError):
        record = {}
    record[account_name] = int(when)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")

