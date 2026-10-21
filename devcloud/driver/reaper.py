"""The reaper (§4.3), `devcloud vm reap`: deletes what outlived its lease, its
purpose or its retention, and unconfirmed throwaway VMs above the cap.

Its decisions are pure functions of (the servers with their labels and
states, the hosts' answers, now) → actions; `run` is a thin layer of side
effects over the protocol client and SSH. It never touches a resource without
the devcloud label, rechecks the label (and the lease it decided on) with a
`get` immediately before every delete, never runs an unusable account's
provider, and never sees an adopted machine, which carries no provider label.

A scheduled (unbounded) run also builds an image for each account that lacks
a current one (§7), at most once a day per account and never while a builder
of the account is alive.

Run at the start of `up` and `ls` it is bounded: it departs no host (that
takes minutes), so it deletes only what needs no departure, all of it within
an overall 60 s (`BOUND`, §4.3), and its lines go to stderr, the command's
own output being what stdout is for."""

import dataclasses
import datetime
import os
import pathlib
import plistlib
import subprocess
import sys

from . import caps, compose, hostctl, images as images_mod
from .errors import FAILED, DriverError, NotOwned, Spent

GRACE = 15 * 60                 # past the label's lease before anything is done
UNREACHABLE_RUNNING = 6 * 3600  # a running host that does not answer is given this long
HELD_MAX = 24 * 3600            # a held departure is retried this long past the lease end
LEFTOVER = 2 * 3600             # builders and provider-test servers
KEEP_IMAGES = 2
DEPART_TIMEOUT = 6 * 60
LABEL = "com.doperpowers.devcloud-reap"
INTERVAL = 600
BOUND = 60                      # the bounded run's whole budget, in seconds


@dataclasses.dataclass(frozen=True)
class Action:
    kind: str                     # keep | contact | delete | label
    reason: str
    labels: dict = dataclasses.field(default_factory=dict)   # for label: the changes
    loss: bool = False            # a delete that loses unshipped sessions


def _expires(vm):
    try:
        return int(vm["labels"]["devcloud-expires"])
    except (KeyError, ValueError):
        return None


def decide(vm, now, answer=None, host_expires=None):
    """What to do with one VM (§4.3's table). `answer` is None before the
    host was contacted, else hostctl's outcome of its departure."""
    labels = vm["labels"]
    expires = _expires(vm)
    if labels.get("devcloud") != "vm" or labels.get("devcloud-lifetime") != "ttl" or expires is None:
        return Action("keep", "not a leased VM")
    past = now - expires
    if past <= GRACE:
        return Action("keep", "lease not over, or within the 15 min grace")
    held = labels.get("devcloud-held") == "1"
    if held and past > HELD_MAX:
        return Action("delete", "held 24 h past its lease end: its unshipped session lines are lost", loss=True)
    if answer is None:
        if vm["state"] != "running":
            if held:
                return Action("keep", "held, not running: waits 24 h past its lease end")
            return Action("delete", f"lease ended, not running ({vm['state']})")
        return Action("contact", "lease ended")
    if answer in (hostctl.DONE, hostctl.AFTER_READY):
        return Action("delete", "departed")
    if answer == hostctl.NOT_OVER:
        if host_expires is None:
            return Action("keep", "the host says its lease is not over, and gave no lease to repair the label with")
        return Action("label", "the host's lease is later: label repaired", {"devcloud-expires": str(host_expires)})
    if answer == hostctl.HELD:
        if held:
            return Action("keep", "departure still held (a failed ship, or sessions that keep starting)")
        return Action("label", "departure held: kept until 24 h past its lease end", {"devcloud-held": "1"})
    if answer == hostctl.UNREACHABLE:
        if held:
            return Action("keep", "held and unreachable: waits 24 h past its lease end")
        if past > UNREACHABLE_RUNNING:
            return Action("delete", "unreachable and running 6 h past its lease end")
        return Action("keep", "unreachable but running: waits until 6 h past its lease end")
    return Action("keep", f"departure outcome {answer}: tried again next run")


def excess(vms, cap):
    """The newest unconfirmed throwaway VMs above the cap, newest first."""
    counted = sorted(caps.throwaway(vms), key=lambda vm: (vm["created"], vm["id"]), reverse=True)
    return counted[:max(0, len(counted) - cap)]


def leftovers(vms, now):
    return [vm for vm in vms if vm["labels"].get("devcloud") in ("builder", "test") and now - vm["created"] > LEFTOVER]


def surplus_images(images, now, recipe=None):
    """Failed images; ready images beyond the newest two, those of the current
    `recipe` kept first; and provider-test images past 2 h. A pending image
    is a build's, still being made; one without a state (a provider that
    gives none) is not known to have failed."""
    ours = [i for i in images if i["labels"].get("devcloud") == "image"]
    failed = [i for i in ours if i.get("state") and i["state"] not in ("ready", "pending")]
    kept = sorted((i for i in ours if i.get("state") == "ready"),
                  key=lambda i: (i["labels"].get("devcloud-recipe") == recipe, i["created"], i["id"]), reverse=True)
    tests = [i for i in images if i["labels"].get("devcloud") == "test" and now - i["created"] > LEFTOVER]
    return failed + kept[KEEP_IMAGES:] + tests


# --- the run ---------------------------------------------------------------------------

def _utc(now):
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tell(ctx, bounded, line):
    """A reaper line: the output of `vm reap`, incidental (stderr) inside
    another command."""
    (ctx.warn if bounded else ctx.say)(f"reap: {line}")


def log(ctx, line, bounded=False):
    ctx.paths.reap_log.parent.mkdir(parents=True, exist_ok=True)
    with open(ctx.paths.reap_log, "a") as f:
        f.write(f"{_utc(ctx.clock())} {line}\n")
    tell(ctx, bounded, line)


def desk_note(ctx, vm, left_desk):
    """What a deletion leaves at the desk. The desk revokes nothing for being
    offline (H4), so an enrolled VM whose departure did not confirm its leave
    is named for removal by hand, unless the desk shows it gone. A VM that
    departed on its own at its lease end is deleted without contact, so the
    desk is asked; its absence counts only from the org's directory, read
    through this driver's enrollment, and only when that directory is newer
    than the lease end: an older one, or a table of this machine alone, may
    simply predate the VM."""
    how = vm["labels"].get("devcloud-enroll")
    if not how or left_desk:
        return ""
    by = "a provisioning key" if how == "key" else "a one-time code"
    ended = _expires(vm)
    since = ctx.clock() - ended if ended is not None and ended <= ctx.clock() else None
    listing = ctx.desk_listing()
    if listing is not None and listing.org:
        if vm["name"] in listing.names:
            return (f"; it was enrolled at the desk by {by}, its leave was not confirmed and the desk still "
                    "lists it, so it stays in the desk's Machines until someone removes it")
        if since is not None and listing.age < since:
            return ""
    return (f"; it was enrolled at the desk by {by} and neither its departure nor the desk confirmed its leave, "
            "so it may still be in the desk's Machines: remove it by hand if so")


def _delete(ctx, entry, reason, left_desk, decided=True, bounded=False):
    vm = entry.vm
    if not ctx.delete(entry, decided_expires=vm["labels"].get("devcloud-expires") if decided else None,
                      decided_state=vm["state"] if decided else None):
        return False
    log(ctx, f"deleted {vm['name']} ({entry.account.name}, id {vm['id']}): {reason}" + desk_note(ctx, vm, left_desk),
        bounded)
    return True


def _expired(ctx, entry, bounded):
    """One leased VM through the table; True when it was deleted."""
    vm, now = entry.vm, ctx.clock()
    action, answer = decide(vm, now), None
    if action.kind == "contact":
        if bounded:
            return False
        answer = hostctl.depart(ctx, entry.host, timeout=DEPART_TIMEOUT)
        host_expires = hostctl.host_expires(ctx, entry.host) if answer == hostctl.NOT_OVER else None
        action = decide(vm, now, answer, host_expires)
        tell(ctx, bounded, f"{vm['name']}: {answer}")
    if action.kind == "delete":
        left = action.reason == "departed" and getattr(answer, "left_desk", False)
        return _delete(ctx, entry, action.reason, left, bounded=bounded)
    if action.kind == "label":
        entry.client.set_labels(vm["id"], action.labels, merge=True)
        tell(ctx, bounded, f"{vm['name']}: {action.reason}")
    return False


def run(ctx, bounded=False):
    """One reaper run over every usable account. Returns the exit code: 0,
    or 1 when an account's provider failed (the others still ran) or a
    bounded run ran out of time."""
    if not bounded:
        return _run(ctx, bounded)
    with ctx.bounded(BOUND):
        try:
            return _run(ctx, bounded)
        except Spent:
            ctx.warn(f"devcloud vm: the reaper's run stopped at its {BOUND} s bound; the scheduled reaper "
                     "finishes it")
            return 1


def _run(ctx, bounded):
    failed = False
    survivors = []
    bakeable = []       # (account, client, its images, its live builders), for the daily build
    accounts = []
    for account, client in ctx.usable(quiet=bounded):
        accounts.append(account)
        try:
            entries = ctx.fleet_of(account, client, kinds=None)
        except Spent:
            raise
        except DriverError as error:
            ctx.warn(f"devcloud vm reap: account {account.name}: {error}")
            failed = True
            continue
        now = ctx.clock()
        builders = []
        for entry in entries:
            kind = entry.vm["labels"].get("devcloud")
            if kind == "builder":
                # A builder holds off the daily build until its delete is known to have happened.
                builders.append(entry.vm)
            try:
                if kind == "vm":
                    if not _expired(ctx, entry, bounded):
                        survivors.append(entry)
                elif leftovers([entry.vm], now):
                    if _delete(ctx, entry, f"a {kind} server older than 2 h", left_desk=False, decided=False,
                               bounded=bounded) and kind == "builder":
                        builders.remove(entry.vm)
            except Spent:
                raise
            except DriverError as error:
                ctx.warn(f"devcloud vm reap: {entry.vm['name']}: {error}")
                failed = True
        try:
            if client.has("images"):
                listed = client.images()
                for image in surplus_images(listed, now, compose.recipe_hash(ctx.plugin)):
                    try:
                        _image_delete(ctx, client, account, image, bounded)
                    except Spent:
                        raise
                    except DriverError as error:
                        ctx.warn(f"devcloud vm reap: image {image['name']} ({account.name}): {error}")
                        failed = True
                bakeable.append((account, client, listed, builders))
        except Spent:
            raise
        except DriverError as error:
            ctx.warn(f"devcloud vm reap: account {account.name} images: {error}")
            failed = True
    if not bounded:
        for vm in excess([dict(e.vm, _entry=e) for e in survivors], ctx.profile.caps.throwaway):
            entry = vm["_entry"]
            try:
                answer = hostctl.depart(ctx, entry.host, force=True, timeout=DEPART_TIMEOUT)
                _delete(ctx, entry, f"over the throwaway cap (newest first; its departure: {answer})",
                        left_desk=getattr(answer, "left_desk", False), decided=False)
            except DriverError as error:
                ctx.warn(f"devcloud vm reap: {entry.vm['name']}: {error}")
                failed = True
        for account, client, listed, builders in bakeable:
            failed |= not _daily_build(ctx, account, client, listed, builders)
        # One dated line per scheduled run, so the agent's output shows it running when nothing is due.
        tell(ctx, bounded, f"run {_utc(ctx.clock())} {'failed' if failed else 'done'}: accounts "
                           f"{', '.join(a.name for a in accounts) or 'none usable'}")
    return 1 if failed else 0


def _daily_build(ctx, account, client, listed, builders):
    """§7: an image for an account that lacks a current one, at most once a
    day; the attempt is recorded before it starts. False when it failed."""
    now = ctx.clock()
    recipe = compose.recipe_hash(ctx.plugin)
    if not images_mod.needs_build(listed, builders, recipe, images_mod.last_build(ctx, account.name), now):
        return True
    images_mod.record_build(ctx, account.name, now)
    tell(ctx, False, f"account {account.name} has no image of recipe {recipe}: building one")
    try:
        made = images_mod.build(ctx, account, client)
    except DriverError as error:
        log(ctx, f"image build for account {account.name} failed: {error}")
        return False
    log(ctx, f"built image {made['name']} ({account.name}, id {made['id']}, recipe {recipe})")
    return True


def _image_delete(ctx, client, account, image, bounded):
    """One surplus image through the image fence; whether it was deleted."""
    try:
        if not client.image_delete(image["id"], image["labels"]):
            return False
    except NotOwned as refusal:
        ctx.warn(f"devcloud vm reap: {refusal}")
        return False
    if image["labels"]["devcloud"] != "image":
        why = "a test image"
    elif image.get("state") not in ("ready", "pending"):
        why = f"its state is {image['state']}"
    else:
        why = f"beyond the newest {KEEP_IMAGES}"
    log(ctx, f"deleted image {image['name']} ({account.name}, id {image['id']}): {why}", bounded)
    return True


# --- the scheduled job (launchd, on the always-on Mac) ---------------------------------------

def bin_path(env):
    """The command the agent runs: the marketplace clone's, which follows
    updates, else the one running now."""
    clone = pathlib.Path(env.get("HOME", "~")).expanduser() / ".claude/plugins/marketplaces/doperpowers/devcloud/bin/devcloud"
    if clone.exists():
        return str(clone)
    own = env.get("DEVCLOUD_BIN")
    if not own:
        raise DriverError(FAILED, "cannot tell where bin/devcloud is (run it through the plugin's bin/devcloud)")
    return own


def install(ctx, agents_dir=None, bin_path=None, launchctl=None, uid=None):
    """`reap --install`: a launchd agent that runs the reaper every 10
    minutes, its output beside the reap log."""
    if launchctl is None and sys.platform != "darwin":
        raise DriverError(FAILED, "reap --install writes a launchd agent: it is for the Macs")
    agents_dir = pathlib.Path(agents_dir or pathlib.Path(ctx.env.get("HOME", "~")).expanduser() / "Library/LaunchAgents")
    program = bin_path or globals()["bin_path"](ctx.env)
    uid = os.getuid() if uid is None else uid
    launchctl = launchctl or (lambda argv: subprocess.run(argv, capture_output=True).returncode)
    ctx.paths.state.mkdir(parents=True, exist_ok=True)
    plist = {"Label": LABEL, "ProgramArguments": [program, "vm", "reap"], "StartInterval": INTERVAL,
             "RunAtLoad": True,
             "EnvironmentVariables": {k: ctx.env[k] for k in ("PATH", "HOME", "DEVCLOUD_PROFILE", "DEVCLOUD_SEED_FILE")
                                      if ctx.env.get(k)},
             "StandardOutPath": str(ctx.paths.state / "reap.out"),
             "StandardErrorPath": str(ctx.paths.state / "reap.out")}
    agents_dir.mkdir(parents=True, exist_ok=True)
    path = agents_dir / f"{LABEL}.plist"
    path.write_bytes(plistlib.dumps(plist))
    launchctl(["launchctl", "bootout", f"gui/{uid}/{LABEL}"])
    if launchctl(["launchctl", "bootstrap", f"gui/{uid}", str(path)]) != 0:
        raise DriverError(FAILED, f"launchctl did not load {path}")
    ctx.say(f"installed {path}: devcloud vm reap every {INTERVAL // 60} minutes, output in {ctx.paths.state / 'reap.out'}")
    return 0
