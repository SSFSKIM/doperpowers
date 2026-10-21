"""`devcloud vm up` (§3): resolve the request, check the caps, name the VM,
compose its descriptor and user-data, create it with its labels, recount,
deliver the seed, wait for the boot, print what was made.

A failure before the server exists leaves nothing; after it, the VM stays
with its lease and labels for `down` or the reaper. A VM starts from its
account's newest image whose recipe hash is current (§7), else from the
provider's Ubuntu by the slow path."""

import dataclasses
import datetime
import json

from . import caps, compose, hostctl, hostfile, images, names, reaper
from .errors import CAP, FAILED, REFUSED, USAGE, DriverError
from .profile import duration, format_duration

BOOT_WAIT = 15 * 60
SSH_WAIT = 5 * 60
POLL = 10


@dataclasses.dataclass
class Resolved:
    account: object
    client: object
    location: str
    type: dict
    lifetime: str
    lease: int | None
    disk_gb: int | None
    spot: bool
    confirmed: bool

    @property
    def price(self):
        return price_text(self.type)


def price_text(type_):
    price = type_.get("hourly_price")
    if price is None:
        return "price unknown"
    return f"{price:g} {type_['currency']}/h" if type_.get("currency") else f"{price:g}/h"


def require_key_pushed(ctx, verb):
    """The boot's home step makes root's keys the configuration repository's
    driver keys (§8.3): one only on this Mac would lock the driver out of the
    host it makes or adopts, once its public port closed."""
    if not ctx.key_pushed():
        raise DriverError(FAILED, f"this driver's key (driver-keys/{ctx.machine}.pub in the profile) is not in the "
                                  "configuration repository yet, and a host's boot would replace root's keys "
                                  f"without it: run the configuration sync (~/.claude/sync/sync.sh), then {verb} again")


def iso(unix):
    return datetime.datetime.fromtimestamp(unix, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def resolve(ctx, opts, wanted=None):
    """Flags, then the first project's host.toml (`wanted`), then the
    profile's defaults (§3 step 1, §9). The file's type, location and spot
    were chosen for its account (its own, else the default one), so a flag
    naming another account drops them; its disk stays."""
    profile = ctx.profile
    wanted = wanted or hostfile.HostFile(project="", source="")
    account = profile.account(opts.account or wanted.account or profile.default_account)
    bound = account.name == (wanted.account or profile.default_account)
    if not bound and any(v is not None for v in (wanted.type, wanted.location, wanted.spot)):
        ctx.say(f"host.toml of {wanted.project}: its type, location and spot are ignored: they are for account "
                f"{wanted.account or profile.default_account}, and --account names {account.name}")
    if not bound:
        wanted = dataclasses.replace(wanted, type=None, location=None, spot=None)
    client = ctx.client(account)
    spot = bool(opts.spot or wanted.spot)
    if spot and not client.has("spot"):
        why = "" if opts.spot else f" (devenv/host.toml of {wanted.project} asks for spot)"
        raise DriverError(REFUSED, f"provider {account.provider} has no spot capability{why}")
    if opts.keep and opts.ttl:
        raise DriverError(USAGE, "--ttl and --keep exclude each other")
    lifetime = "keep" if opts.keep else "ttl"
    lease = None
    if lifetime == "ttl":
        try:
            lease = duration(opts.ttl) if opts.ttl else profile.caps.lease_default
        except ValueError as error:
            raise DriverError(USAGE, f"--ttl: {error}") from None
    if opts.disk is not None and opts.disk <= 0:
        raise DriverError(USAGE, "--disk must be a positive number of GB")
    disk = opts.disk if opts.disk is not None else wanted.disk_gb
    location = opts.location or wanted.location or account.location
    type_name = opts.type or wanted.type or account.type
    offered = {t["type"]: t for t in client.types(location)}
    type_ = offered.get(type_name)
    if type_ is None:
        raise DriverError(REFUSED, f"{account.provider} offers no type {type_name} in {location}")
    if not type_.get("available"):
        raise DriverError(REFUSED, f"{type_name} is not available in {location} now")
    return Resolved(account=account, client=client, location=location, type=type_, lifetime=lifetime, lease=lease,
                    disk_gb=disk, spot=spot, confirmed=bool(opts.confirmed))


def verdict(ctx, r, servers):
    request = caps.Request(type=r.type["type"], vcpus=r.type["vcpus"], type_disk_gb=r.type["disk_gb"],
                           disk_gb=r.disk_gb, lifetime=r.lifetime, lease=r.lease, confirmed=r.confirmed)
    return caps.check(request, ctx.profile.caps, alive=len(caps.throwaway(servers)))


def describe(r):
    t = r.type
    lifetime = f"ttl {format_duration(r.lease)}" if r.lifetime == "ttl" else "keep"
    disk = f", {r.disk_gb} GB requested" if r.disk_gb else ""
    return (f"account   {r.account.name} ({r.account.provider})  location {r.location}  type {t['type']} "
            f"({t['vcpus']} vCPU, {t.get('memory_gb', '?')} GB, {t['disk_gb']} GB disk{disk})  lifetime {lifetime}"
            f"{'  spot' if r.spot else ''}  price {r.price}")


def run(ctx, opts):
    begun = ctx.clock()
    label = names.check_label(opts.label or "vm")
    code = opts.enroll_code
    # A project's file is checked before anything runs: a bad one is exit 2 with nothing done.
    wanted = hostfile.governing(ctx, list(opts.project or []))
    if wanted is not None:
        ctx.say(f"host.toml of {wanted.project}, read from {wanted.source}")
    if not opts.dry_run:
        try:
            reaper.run(ctx, bounded=True)
        except DriverError as error:
            ctx.warn(f"devcloud vm up: the reaper's run before up: {error}")
    r = resolve(ctx, opts, wanted)
    # Every usable account's list must answer: one that failed is not zero VMs.
    servers = [e.vm for e in ctx.fleet(quiet=True, kinds=None, strict=True)]
    v = verdict(ctx, r, servers)
    ctx.say(describe(r))
    ctx.say(f"caps      {v.line}")
    if v.refusal:
        raise DriverError(CAP, v.refusal)
    if opts.dry_run:
        return 0

    started = ctx.clock()
    keys = ctx.driver_keys()
    require_key_pushed(ctx, "up")
    name = names.draw(label, ctx.taken_names(servers), ctx.token_hex)
    tag, short = ctx.creator()
    expires = int(started) + r.lease if r.lifetime == "ttl" else None
    metadata_seed = r.client.has("metadata_seed")
    if metadata_seed and not r.client.has("user_data"):
        raise DriverError(REFUSED, f"provider {r.client.name} has metadata_seed without user_data: nothing could "
                                   "start its first boot")
    desc = compose.descriptor(name=name, profile=ctx.profile, projects=list(opts.project or []), expires=expires,
                              creator=tag, spot=r.spot, seed="gce-metadata" if metadata_seed else "file")
    enroll = "code" if code else ("key" if ctx.profile.desk_secret else None)
    recipe = compose.recipe_hash(ctx.plugin)
    labels = compose.labels(kind="vm", lifetime=r.lifetime, expires=expires, by=ctx.machine, creator=short,
                            recipe=recipe, confirmed=r.confirmed, enroll=enroll,
                            test_run=ctx.env.get("DEVCLOUD_TEST_RUN"))
    image = images.current(r.client.images(), recipe) if r.client.has("images") else None
    if metadata_seed:
        # No seed to deliver and no SSH before the tailnet: cloud-init does the
        # first boot, carrying the recipe on the slow path (§3 step 4).
        user_data = compose.boot_user_data(desc, keys, None if image else compose.recipe_archive(ctx.plugin),
                                           ctx.profile.build)
    else:
        user_data = compose.user_data(desc, keys) if r.client.has("user_data") else None
    vm = r.client.create({"name": name, "type": r.type["type"], "location": r.location,
                          "image": image["id"] if image else None, "labels": labels, "ssh_public_keys": keys,
                          "user_data": user_data, "disk_gb": r.disk_gb, "spot": r.spot})
    made_from = f"{image['name']} (id {image['id']})" if image else "built from base, slow path"
    ctx.say(f"created   {name} (id {vm['id']}) from " + (f"image {made_from}" if image else "base, slow path"))
    from .context import Entry
    entry = Entry(r.account, r.client, vm)
    recount(ctx, entry, r)

    host = entry.host
    if not metadata_seed:
        address = host.public or hostctl.public_address(ctx, entry)
        hostctl.wait_ssh(ctx, address, host.alias, ctx.clock() + SSH_WAIT)
        if user_data is None:
            hostctl.stage(ctx, address, host.alias, desc)
        hostctl.wait_cloud_init(ctx, address, host.alias)
        if image is None:
            ctx.say(f"setup     {name}: setup.sh from the plugin's recipe")
            hostctl.install_recipe(ctx, address, host.alias, ctx.profile.build)
        hostctl.deliver_seed(ctx, address, host.alias)
        hostctl.start_boot(ctx, address, host.alias)
    else:
        address = None
    wait_boot(ctx, host, address, started + BOOT_WAIT)
    if code:
        enroll_with_code(ctx, host, code)
    elapsed = int(ctx.clock() - begun)
    ctx.say(f"{name}  ready in {elapsed // 60}m{elapsed % 60:02d}s")
    ctx.say(f"  provider  {r.client.name}  location {r.location}  type {r.type['type']}")
    ctx.say(f"  tailnet   {name}")
    ctx.say(f"  lease     " + (f"ends {iso(expires)} (in {format_duration(r.lease)})" if expires else "none (keep)"))
    ctx.say(f"  price     {r.price}")
    ctx.say(f"  image     {made_from}")
    return 0


def recount(ctx, entry, r):
    """§2: two drivers racing past the count would make one too many; the
    newest unconfirmed throwaway VM above the cap, when it is this one, goes."""
    if r.lifetime != "ttl" or r.confirmed:
        return
    try:
        counted = caps.throwaway([e.vm for e in ctx.fleet(quiet=True, strict=True)])
    except DriverError as error:
        # A recount that cannot be made cannot show this VM is within the cap.
        gone = ctx.delete(entry)
        raise DriverError(FAILED, f"the recount after the create failed: {error}; "
                                  + (f"deleted {entry.vm['name']}" if gone else
                                     f"{entry.vm['name']} could not be deleted: down it, or the reaper will")) from None
    cap = ctx.profile.caps.throwaway
    if len(counted) <= cap:
        return
    newest = max(counted, key=lambda vm: (vm["created"], vm["id"]))
    if newest["id"] != entry.vm["id"] or newest["name"] != entry.vm["name"]:
        return
    ctx.delete(entry)
    raise DriverError(CAP, f"over the throwaway cap ({len(counted)} alive after the create, cap {cap}: another "
                           f"driver created one meanwhile); deleted {entry.vm['name']}: ask the person, then pass "
                           "--confirmed")


def wait_boot(ctx, host, address, deadline):
    """§3 step 8: over the public address until the tailnet attach step is
    ok, then over the tailnet; a failed step prints the status and exits 1."""
    attached = address is None
    while True:
        answer = None
        for target in ([host.name] if attached else [address, host.name]):
            answer = hostctl.progress(ctx, target, host.alias)
            if answer is not None:
                break
        if answer is not None:
            data, unit = answer
            steps = data.get("steps", [])
            states = {s["name"]: s["state"] for s in steps}
            if states.get("tailnet-attach") == "ok":
                attached = True
            failed = [s for s in steps if s["state"] == "failed"]
            if unit != "activating" and (failed or len(states) == 12):
                if failed:
                    from devcloudlib import status
                    ctx.warn(status.render(data).rstrip())
                    raise DriverError(FAILED, f"the boot failed at step {failed[0]['name']} ({failed[0]['detail']}); "
                                              f"the VM {host.name} is kept for inspection, its lease bounds it")
                return data
            if unit == "failed":
                raise DriverError(FAILED, f"devcloud-boot.service failed on {host.name} with no step recorded as "
                                          "failed (journalctl -u devcloud-boot there); the VM is kept for inspection")
        if ctx.clock() >= deadline:
            where = ("" if answer is not None or address is not None else
                     f"; it never answered over the tailnet, so its first boot may have failed before the boot "
                     f"started: see {compose.FIRST_BOOT_LOG} on it, through the provider's serial console")
            raise DriverError(FAILED, f"the boot of {host.name} did not finish within 15 minutes{where}; the VM is "
                                      "kept for inspection, its lease bounds it")
        ctx.sleep(POLL)


def enroll_with_code(ctx, host, code):
    """§10's stand-in for the desk's key: the code delivered after the boot,
    then a reconcile whose step 11 enrolls with it. Enrolled only when that
    reconcile exited 0 and wrote a services entry of its own: the boot's
    entry from before it proves nothing about the code."""
    before = _services(hostctl.progress(ctx, host.name, host.alias))
    result = hostctl.deliver_code(ctx, host.name, host.alias, code)
    if result.code != 0:
        why = ("the connection dropped" if result.code is None or result.code < 0 or result.code == 255
               else f"devcloud reconcile exited {result.code}")
        raise DriverError(FAILED, f"the enrollment with the code failed on {host.name} ({why})")
    answer = hostctl.progress(ctx, host.name, host.alias)
    services = _services(answer)
    if services is None or (before is not None and services.get("at", "") <= before.get("at", "")):
        raise DriverError(FAILED, f"the enrollment with the code is unconfirmed on {host.name}: the reconcile wrote "
                                  "no services entry of its own")
    if services["state"] == "failed":
        raise DriverError(FAILED, f"the enrollment with the code failed on {host.name} ({services['detail']})")
    if answer[0].get("enroll"):
        ctx.say("enroll    deferred: the desk was undecided; devcloud-enroll finishes it")
    ctx.say(f"enroll    {host.name}: {services['detail'] or services['state']}")


def _services(answer):
    return next((s for s in (answer[0] if answer else {}).get("steps", []) if s["name"] == "services"), None)
