"""`ls`, `ssh`, `lease` and `down` (M3's decisions in the driver spec)."""

import json
import shlex

from . import caps, hostctl, reaper
from .errors import CAP, FAILED, GUARD, USAGE, DriverError
from .profile import duration, format_duration
from .up import iso, price_text


def _relative(expires, now):
    if expires is None:
        return "-"
    delta = int(expires - now)
    return f"in {format_duration(delta // 60 * 60 or 60)}" if delta > 0 else \
        f"ended {format_duration(-delta // 60 * 60 or 60)} ago"


def _expires(vm):
    try:
        return int(vm["labels"]["devcloud-expires"])
    except (KeyError, ValueError):
        return None


def ls(ctx, as_json=False):
    """Every usable account's VMs and the tailnet's devcloud nodes that no VM
    accounts for, the throwaway count against the cap at the head."""
    try:
        reaper.run(ctx, bounded=True)
    except DriverError as error:
        ctx.warn(f"devcloud vm ls: the reaper's run: {error}")
    entries = ctx.fleet()
    now = ctx.clock()
    prices = {}
    rows = []
    for e in entries:
        key = (e.account.name, e.vm["location"])
        if key not in prices:
            try:
                prices[key] = {t["type"]: t for t in e.client.types(e.vm["location"])}
            except DriverError:
                prices[key] = {}
        type_ = prices[key].get(e.vm["type"])
        labels = e.vm["labels"]
        state = "held" if labels.get("devcloud-held") == "1" else e.vm["state"]
        rows.append({"name": e.vm["name"], "account": e.account.name, "provider": e.account.provider,
                     "lifetime": labels.get("devcloud-lifetime", "?"), "expires": _expires(e.vm), "state": state,
                     "price": price_text(type_) if type_ else "-", "creator": labels.get("devcloud-creator", "-"),
                     "confirmed": labels.get("devcloud-confirmed") == "1", "id": e.vm["id"]})
    known = {row["name"] for row in rows}
    for node in ctx.tailnet():
        if "tag:devcloud" in node.get("tags", []) and node["name"] not in known:
            rows.append({"name": node["name"], "account": None, "provider": None, "lifetime": None, "expires": None,
                         "state": "online" if node.get("online") else "offline", "price": "-", "creator": "-",
                         "confirmed": False, "id": None, "tailnet_only": True})
    alive = len(caps.throwaway([e.vm for e in entries]))
    cap = ctx.profile.caps.throwaway
    if as_json:
        ctx.say(json.dumps({"throwaway": {"alive": alive, "cap": cap}, "vms": rows}, indent=1))
        return 0
    ctx.say(f"throwaway {alive}/{cap}")
    table = [("NAME", "ACCOUNT", "LIFETIME", "LEASE", "STATE", "PRICE", "CREATOR")]
    for row in rows:
        if row.get("tailnet_only"):
            table.append((row["name"], "tailnet only", "-", "-", row["state"], "-", "-"))
        else:
            table.append((row["name"], f"{row['provider']}/{row['account']}", row["lifetime"],
                          _relative(row["expires"], now), row["state"], row["price"], row["creator"]))
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    for r in table:
        ctx.say("  ".join(cell.ljust(width) for cell, width in zip(r, widths)).rstrip())
    return 0


def ssh(ctx, name, root, command):
    """The user over the tailnet (`--root` for root). One argument is a shell
    line passed as given; several are an argv, each quoted. A host whose
    departure has started is refused, except to root, for inspection."""
    entry = ctx.find(name)
    host = entry.host
    if not root:
        state = hostctl.lifecycle(ctx, host)
        if state in hostctl.DEPARTURE_STARTED:
            raise DriverError(FAILED, f"{name}'s departure has started ({state}): its sessions are over; "
                                      "pass --root to inspect it")
    line = None if not command else command[0] if len(command) == 1 else shlex.join(command)
    return ctx.remote.interactive(host.name, host.alias, line, user="root" if root else ctx.user())


def lease(ctx, name, text, confirmed):
    """The lease end set to now + duration: the host first (under its lock),
    then the label with the lease the host printed back (§4.1)."""
    try:
        seconds = duration(text)
    except ValueError as error:
        raise DriverError(USAGE, str(error)) from None
    entry = ctx.find(name)
    vm = entry.vm
    now = int(ctx.clock())
    wanted = now + seconds
    current = _expires(vm)
    longer = current is None or wanted > current
    lease_max = ctx.profile.caps.lease_max
    if longer and not confirmed and wanted - vm["created"] > lease_max:
        raise DriverError(CAP, f"{name} would live {format_duration(wanted - vm['created'])} from its creation, over "
                               f"the lifetime cap ({format_duration(lease_max)}): ask the person, then pass --confirmed")
    printed = hostctl.lease_set(ctx, entry.host, wanted)
    labels = {**vm["labels"], "devcloud-expires": str(printed), "devcloud-lifetime": "ttl"}
    entry.client.set_labels(vm["id"], labels)
    ctx.say(f"{name} lease ends {iso(printed)} ({_relative(printed, now)})")
    return 0


def down(ctx, name, force):
    """The down guard, the departure, then the delete after the label
    recheck. Unreachable: --force deletes without departing."""
    entry = ctx.find(name)
    host = entry.host
    if not hostctl.reachable(ctx, host):
        if not force:
            raise DriverError(FAILED, f"{name} does not answer over the tailnet: pass --force to delete it "
                                      "without its departure (its sessions' last lines are lost)")
        return _delete(ctx, entry, "deleted without its departure (unreachable)")
    if not force:
        dirty = hostctl.unpushed(ctx, host)
        if dirty:
            repos = ", ".join(repo for repo, _ in dirty)
            raise DriverError(GUARD, f"{name} has unpushed work in {repos}: push it, or pass --force")
    outcome = hostctl.depart(ctx, host, force=True, no_hold=force)
    if outcome in (hostctl.DONE, hostctl.AFTER_READY):
        return _delete(ctx, entry, "departed and deleted")
    if outcome == hostctl.HELD:
        raise DriverError(FAILED, f"{name}'s departure is held (its ship failed, or sessions keep starting); it is "
                                  "kept so its transcripts can still ship: fix it, or pass --force to delete anyway")
    if outcome == hostctl.UNKNOWN:
        raise DriverError(FAILED, f"the connection to {name} dropped before its departure was ready to log out: "
                                  "the outcome is unknown, and the VM is kept")
    if outcome == hostctl.UNREACHABLE and force:
        return _delete(ctx, entry, "deleted without its departure (unreachable)")
    if force:
        return _delete(ctx, entry, f"deleted after a departure that ended {outcome}")
    raise DriverError(FAILED, f"{name}'s departure ended {outcome}; the VM is kept: pass --force to delete it anyway")


def _delete(ctx, entry, what):
    if not ctx.delete(entry):
        raise DriverError(FAILED, f"{entry.vm['name']} was not deleted: its labels changed since it was read")
    ctx.say(f"{entry.vm['name']}: {what}")
    return 0
