"""`ls`, `ssh`, `lease` and `down` (M3's decisions in the driver spec), for VMs
and, through `adopt`, for adopted machines."""

import json
import shlex

from . import adopt, caps, hostctl, reaper, tailnet
from .errors import FAILED, GUARD, USAGE, DriverError
from .profile import duration, format_duration
from .up import iso, price_text


def _relative(expires, now):
    if expires is None:
        return "-"
    delta = int(expires - now)
    return f"in {format_duration(delta // 60 * 60 or 60)}" if delta > 0 else \
        f"ended {format_duration(-delta // 60 * 60 or 60)} ago"


def _age(created, now):
    """`3d4h`, `5h10m` or `12m`: how long a VM has run, to the minute."""
    minutes = max(0, int(now - created)) // 60
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    return f"{days}d{hours}h" if days else f"{hours}h{minutes}m" if hours else f"{minutes}m"


def _spent(type_, created, now):
    """The type's list price times the VM's age, or None without a price."""
    price = (type_ or {}).get("hourly_price")
    if price is None:
        return None
    return price * max(0, now - created) / 3600


def _expires(vm):
    try:
        return int(vm["labels"]["devcloud-expires"])
    except (KeyError, ValueError):
        return None


def ls(ctx, as_json=False):
    """Every usable account's VMs, each with its age and what it has cost at
    its type's list price, and the tailnet's devcloud nodes that no VM
    accounts for; the unconfirmed count against the cap at the head."""
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
                     "price": price_text(type_) if type_ else "-", "created": e.vm["created"],
                     "spent": _spent(type_, e.vm["created"], now), "currency": (type_ or {}).get("currency"),
                     "creator": labels.get("devcloud-creator", "-"),
                     "confirmed": labels.get("devcloud-confirmed") == "1", "id": e.vm["id"]})
    nodes = ctx.tailnet()
    online = {node["name"]: node.get("online") for node in nodes}
    for record in adopt.records(ctx):
        if record.phase == "booted" and record.ready:
            state = {True: "online", False: "offline"}.get(online.get(record.name), "not on the tailnet")
        else:
            state = f"adopting ({record.phase})" if record.phase != "released" else "releasing"
        rows.append({"name": record.name, "account": "adopted", "provider": None, "lifetime": record.lifetime,
                     "expires": record.expires, "state": state, "price": "-", "creator": record.creator or "-",
                     "confirmed": True, "id": None, "adopted": True, "phase": record.phase,
                     "target": f"{record.user}@{record.address}"})
    known = {row["name"] for row in rows}
    for node in nodes:
        if "tag:devcloud" in node.get("tags", []) and node["name"] not in known:
            rows.append({"name": node["name"], "account": None, "provider": None, "lifetime": None, "expires": None,
                         "state": "online" if node.get("online") else "offline", "price": "-", "creator": "-",
                         "confirmed": False, "id": None, "tailnet_only": True})
    alive = len(caps.unconfirmed([e.vm for e in entries]))
    cap = ctx.profile.caps.unconfirmed
    if as_json:
        ctx.say(json.dumps({"unconfirmed": {"alive": alive, "cap": cap}, "vms": rows}, indent=1))
        return 0
    ctx.say(f"unconfirmed {alive}/{cap}")
    table = [("NAME", "ACCOUNT", "LIFETIME", "LEASE", "STATE", "AGE", "PRICE", "SPENT", "CREATOR")]
    for row in rows:
        if row.get("tailnet_only"):
            table.append((row["name"], "tailnet only", "-", "-", row["state"], "-", "-", "-", "-"))
        elif row.get("adopted"):
            table.append((row["name"], "adopted", row["lifetime"], _relative(row["expires"], now), row["state"], "-",
                          "-", "-", row["creator"]))
        else:
            spent = "-" if row["spent"] is None else f"{row['spent']:.2f}" + (
                f" {row['currency']}" if row["currency"] else "")
            table.append((row["name"], f"{row['provider']}/{row['account']}", row["lifetime"],
                          _relative(row["expires"], now), row["state"], _age(row["created"], now), row["price"],
                          spent, row["creator"]))
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    for r in table:
        ctx.say("  ".join(cell.ljust(width) for cell, width in zip(r, widths)).rstrip())
    return 0


def ssh(ctx, name, root, command):
    """The user over the tailnet (`--root` for root). One argument is a shell
    line passed as given; several are an argv, each quoted. A host whose
    departure has started is refused, except to root, for inspection."""
    record = adopt.load(ctx, name)
    host = record.host if record else ctx.find(name).host
    if not root:
        state = hostctl.lifecycle(ctx, host)
        if state in hostctl.DEPARTURE_STARTED:
            raise DriverError(FAILED, f"{name}'s departure has started ({state}): its sessions are over; "
                                      "pass --root to inspect it")
    line = None if not command else command[0] if len(command) == 1 else shlex.join(command)
    return ctx.remote.interactive(host.name, host.alias, line, user="root" if root else ctx.user())


def lease(ctx, name, text):
    """The lease end set to now + duration, or removed (`keep`): the host
    first (under its lock), then the label with the lease the host printed
    back (§4.1). When that changed the kind of the host's tailnet node, the
    host rejoins as the other kind under the same name, and the driver waits
    for it to come back. No cap applies: a lease changes when a VM ends,
    never how many are alive (§2)."""
    keep = text == "keep"
    try:
        seconds = None if keep else duration(text)
    except ValueError as error:
        raise DriverError(USAGE, str(error)) from None
    now = int(ctx.clock())
    wanted = None if keep else now + seconds
    record = adopt.load(ctx, name)
    if record is not None:
        done = adopt.lease(ctx, record, wanted)
        ctx.say(f"{name} is kept, without a lease" if done.expires is None else
                f"{name} lease ends {iso(done.expires)} ({_relative(done.expires, now)}); then it releases itself")
        _follow(ctx, record.host, done)
        return 0
    entry = ctx.find(name)
    vm = entry.vm
    done = hostctl.lease_set(ctx, entry.host, wanted)
    if done.expires is None:
        # Kept; devcloud-confirmed stays as `up` set it, so the count cap still sees the VM.
        entry.client.set_labels(vm["id"], {"devcloud-lifetime": "keep"}, merge=True, drop=("devcloud-expires",))
        ctx.say(f"{name} is kept, without a lease")
    else:
        entry.client.set_labels(vm["id"], {"devcloud-expires": str(done.expires), "devcloud-lifetime": "ttl"},
                                merge=True)
        ctx.say(f"{name} lease ends {iso(done.expires)} ({_relative(done.expires, now)})")
    _follow(ctx, entry.host, done)
    return 0


def _follow(ctx, host, done):
    """The wait for a rejoin the lease write started (§4.1)."""
    if done.rejoin is None:
        return
    ctx.say(f"{host.name} is rejoining the tailnet as {hostctl.a_node(done.rejoin)}; waiting for it")
    hostctl.wait_rejoin(ctx, host, done.rejoin)
    ctx.say(f"{host.name} is back on the tailnet as {hostctl.a_node(done.rejoin)}, under the same name")


FORCE_WITHOUT_DEPARTURE = (
    "--force deletes without a confirmed departure (unshipped transcripts may be lost and desk enrollment may "
    "remain); afterwards check `sminos machines` and `devcloud vm ls` for desk and tailnet residue")


def down(ctx, name, force):
    """The down guard, the departure, then the delete after the label
    recheck. Unreachable: --force deletes without departing. An adopted
    machine is released instead, and keeps running (§6.5)."""
    record = adopt.load(ctx, name)
    if record is not None:
        return adopt.down(ctx, record, force)
    entry = ctx.find(name)
    host = entry.host
    if not hostctl.reachable(ctx, host):
        if not force:
            raise DriverError(FAILED, f"{name}'s departure is unconfirmed (unreachable over the tailnet); "
                                      f"the VM is kept; {FORCE_WITHOUT_DEPARTURE}")
        return _delete(ctx, entry, "deleted without its departure (unreachable)")
    if not force:
        dirty = hostctl.unpushed(ctx, host)
        if dirty:
            repos = ", ".join(repo for repo, _ in dirty)
            raise DriverError(GUARD, f"{name} has unpushed work in {repos}: push it, or pass --force")
    outcome = hostctl.depart(ctx, host, force=True, no_hold=force)
    if outcome in (hostctl.DONE, hostctl.AFTER_READY):
        return _delete(ctx, entry, "departed and deleted", left_desk=outcome.left_desk)
    if outcome == hostctl.HELD:
        raise DriverError(FAILED, f"{name}'s departure is held (its ship failed, or sessions keep starting); it is "
                                  "kept so its transcripts can still ship: fix it, or pass --force to delete anyway")
    if outcome == hostctl.UNKNOWN:
        if force:
            return _delete(ctx, entry, "deleted without departure confirmation (connection lost)",
                           left_desk=outcome.left_desk)
        last = f"last received step: {outcome.last_step}" if outcome.last_step else "no departure step received"
        raise DriverError(FAILED, f"{name}'s logout confirmation was not received ({last}); "
                                  f"the outcome is unknown and the VM is kept; {FORCE_WITHOUT_DEPARTURE}")
    if outcome == hostctl.UNREACHABLE and force:
        return _delete(ctx, entry, "deleted without its departure (unreachable)")
    if force:
        return _delete(ctx, entry, f"deleted after a departure that ended {outcome}",
                       left_desk=getattr(outcome, "left_desk", False))
    raise DriverError(FAILED, f"{name}'s departure ended {outcome}; the VM is kept: pass --force to delete it anyway")


def _delete(ctx, entry, what, left_desk=False):
    """The delete, then whatever the tailnet still lists of the host (a kept
    VM's node, which a departure cut short or none ran for, board #118)."""
    if not ctx.delete(entry):
        raise DriverError(FAILED, f"{entry.vm['name']} was not deleted: its labels changed since it was read")
    name = entry.vm["name"]
    ctx.say(f"{name}: {what}{reaper.desk_note(ctx, entry.vm, left_desk)}{tailnet.remove(ctx, name)}")
    return 0
