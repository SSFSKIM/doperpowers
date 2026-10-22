"""`devcloud vm adopt <user@address>` (§6.5): an Ubuntu 24.04 machine the
driver did not make becomes a host, and `down` (or its own lease end) gives
it back, running, with the access it had.

The target comes only from the command line, and only with --confirmed. The
driver keeps one record per adopted machine,
`~/.local/state/devcloud/adopted/<name>.json` — the one piece of lifecycle
state it keeps locally, since an adopted machine has no provider label. Its
phase is written before the step it names (`preparing`: the keys saved, the
driver's key authorized for root, setup.sh, the descriptor staged; `seeded`:
the seed; `booted`: the descriptor installed and the boot started;
`released`: the release), and `adopt` run again for the same target resumes
from it. `ready` records when the boot finished.

The first contact is the person's own key as the login user (sudo for one
that is not root); from the authorization on, the driver's key as root, at
the public address until the boot closes it, then over the tailnet. Every
connection is keyed by the machine's name (§8.3)."""

import base64
import dataclasses
import json
import pathlib
import re
import shlex

from . import compose, hostctl, names, reaper, tailnet
from .errors import CAP, FAILED, USAGE, DriverError
from .hostctl import Host
from .profile import duration, format_duration

PHASES = ("preparing", "seeded", "booted", "released")
BUILD_KEYS = ("DEVCLOUD_USER", "DEVCLOUD_UID", "DEVCLOUD_HOME")
CONTACT_TIMEOUT = 45
SSH_WAIT = 3 * 60
BOOT_WAIT = 15 * 60
VERIFY_WAIT = 3 * 60
_USER = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
_ADDRESS = re.compile(r"[A-Za-z0-9.:\[\]-]{1,253}\Z")
# The release left nothing of devcloud: no descriptor, no ledger, no seed (staged or not), no unit
# (the transient release unit included, so it has finished), no firewall table. Run as root at the public address. A unit whose
# file is gone but whose failure systemd still remembers until the next boot (`not-found failed`,
# the boot unit of an adoption whose boot failed) is no unit.
RELEASED = (f"test ! -e /etc/devcloud/boot.env && test ! -e /var/lib/devcloud/credentials.ledger && "
            f"test ! -e {compose.SEED_PATH} && test ! -e {compose.SEED_PATH}.tmp && "
            "! systemctl list-units --all --no-legend --plain 'devcloud-*' | grep -v ' not-found ' | grep -q . && "
            "! systemctl list-unit-files --no-legend 'devcloud-*' | grep -q . && "
            "! nft list table inet devcloud >/dev/null 2>&1")


@dataclasses.dataclass
class Record:
    name: str
    address: str
    user: str
    lifetime: str               # ttl | keep
    expires: int | None
    projects: list
    phase: str
    created: int
    ready: int | None = None
    creator: str | None = None  # the creating session's short id
    enroll: str | None = None   # "key" when its boot enrolls at the desk with the provisioning key

    @property
    def host(self):
        return Host(name=self.name, alias=self.name, public=self.address)


def _dir(ctx):
    return ctx.paths.adopted


def path(ctx, name):
    return _dir(ctx) / f"{name}.json"


def save(ctx, record):
    directory = _dir(ctx)
    directory.mkdir(parents=True, exist_ok=True)
    staged = directory / f".{record.name}.json.tmp"
    staged.write_text(json.dumps(dataclasses.asdict(record), indent=1) + "\n")
    staged.replace(path(ctx, record.name))


def load(ctx, name):
    """The adoption record named `name`, or None."""
    try:
        return Record(**json.loads(path(ctx, name).read_text()))
    except FileNotFoundError:
        return None
    except (ValueError, TypeError) as error:
        raise DriverError(FAILED, f"the adoption record {path(ctx, name)} does not read ({error})") from None


def records(ctx):
    directory = _dir(ctx)
    if not directory.is_dir():
        return []
    return [r for r in (load(ctx, p.stem) for p in sorted(directory.glob("*.json"))) if r is not None]


def remove(ctx, record):
    path(ctx, record.name).unlink(missing_ok=True)
    ctx.remote.forget(record.name)


def parse_target(text):
    user, at, address = (text or "").rpartition("@")
    if not at or not _USER.match(user) or not _ADDRESS.match(address):
        raise DriverError(USAGE, f"adopt takes <user>@<address> (the login user and the machine's address), not "
                                 f"{text!r}")
    return user, address.strip("[]")


def _script(ctx, chan, args, what):
    source = pathlib.Path(__file__).with_name("adopt_host.py").read_bytes()
    result = chan(f"python3 - {args}", input=source, timeout=120)
    if result.code != 0:
        raise DriverError(FAILED, f"{what} failed on the machine (exit {result.code}): "
                                  f"{(result.err or result.out).strip()[-200:]}")
    return result.out


def _channel(ctx, record):
    """A way to run root commands at the machine's public address: the
    driver's key as root, else the person's key as the login user (sudo for
    one that is not root). None when neither answers."""
    host = record.host

    def as_root(command, **kw):
        return ctx.remote.run(record.address, host.alias, command, **kw)

    def as_login(command, **kw):
        return _as_login(ctx, record, command, **kw)
    for chan in (as_root, as_login):
        if chan("true", timeout=CONTACT_TIMEOUT, connect_timeout=15).code == 0:
            return chan
    return None


def _as_login(ctx, record, command, **kw):
    """`command` as root through the original login user with the person's
    own key, at the public address."""
    return ctx.remote.run(record.address, record.name, hostctl.as_root(record.user, command), user=record.user,
                          person=True, **kw)


def run(ctx, opts):
    """`devcloud vm adopt`."""
    user, address = parse_target(opts.target)
    if not opts.confirmed:
        raise DriverError(CAP, f"adopting {user}@{address} sends the seed key to a machine the driver did not make "
                               "and takes over its SSH and firewall until it is released: ask the person, then pass "
                               "--confirmed")
    lease = None
    if opts.ttl:
        try:
            lease = duration(opts.ttl)
        except ValueError as error:
            raise DriverError(USAGE, f"--ttl: {error}") from None
    label = names.check_label(opts.label or "vm")
    record = next((r for r in records(ctx) if r.address == address and r.user == user), None)
    life = f"ttl {format_duration(lease)}" if lease else "keep"
    if opts.dry_run:
        what = f"resumes {record.name} from phase {record.phase}" if record else f"as a new dc-{label}-…"
        ctx.say(f"adopt     {user}@{address} {what}  lifetime {life}  projects {' '.join(opts.project) or '-'}")
        ctx.say("caps      adopt always needs the person's yes: confirmed")
        return 0
    from .up import pushed_driver_keys
    keys = pushed_driver_keys(ctx, "adopt")
    fresh = record is None
    if fresh:
        servers = [e.vm for e in ctx.fleet(quiet=True)]
        _, short = ctx.creator()
        now = int(ctx.clock())
        record = Record(name=names.draw(label, ctx.taken_names(servers), ctx.token_hex), address=address, user=user,
                        lifetime="ttl" if lease else "keep", expires=now + lease if lease else None,
                        projects=list(opts.project or []), phase="preparing", created=now, creator=short,
                        enroll="key" if ctx.profile.desk_secret else None)
    elif record.phase == "released":
        raise DriverError(FAILED, f"{record.name} ({user}@{address}) is being released: devcloud vm down "
                                  f"{record.name} finishes that, and a later adopt starts afresh")
    else:
        ctx.say(f"adopt     resuming {record.name} ({user}@{address}) from phase {record.phase}; this run's "
                "--label, --ttl and --project are ignored")
    chan = _channel(ctx, record)
    try:
        if chan is None and record.phase != "booted":
            raise DriverError(FAILED, f"cannot reach {user}@{address} over SSH with your own key (for a user other "
                                      "than root, sudo must work without a password)")
        if chan is not None:
            _check(ctx, chan, None if fresh else record)
        if record.phase == "preparing":
            _preflight(ctx, chan, record)
    except DriverError:
        if fresh:
            ctx.remote.forget(record.name)
        raise
    begun = ctx.clock()
    if record.phase == "preparing":
        _prepare(ctx, record, chan, keys)
    if record.phase in ("preparing", "seeded"):
        record.phase = "seeded"
        save(ctx, record)
        hostctl.deliver_seed(ctx, address, record.name)
    if record.phase in ("seeded", "booted"):
        _boot(ctx, record)
    elapsed = int(ctx.clock() - begun)
    ctx.say(f"{record.name}  adopted in {elapsed // 60}m{elapsed % 60:02d}s ({user}@{address}; it keeps running "
            "when released)")
    ctx.say(f"  tailnet   {record.name}")
    from .up import iso
    ctx.say("  lease     " + (f"ends {iso(record.expires)}, then it releases itself" if record.expires else
                              "none (keep): devcloud vm down releases it"))
    return 0


def _check(ctx, chan, record):
    """The machine is Ubuntu 24.04, and holds no descriptor unless it is the
    one this record's adoption installed."""
    found = json.loads(_script(ctx, chan, "inspect", "inspecting the machine").strip().splitlines()[-1])
    if (found.get("id"), found.get("version")) != ("ubuntu", "24.04"):
        raise DriverError(FAILED, f"adopt takes Ubuntu 24.04; this machine is {found.get('id')} "
                                  f"{found.get('version')}")
    existing = found.get("descriptor")
    if existing is not None and not (record is not None and existing.get("name") == record.name
                                     and existing.get("adopted")):
        raise DriverError(FAILED, f"this machine is already a devcloud host ({existing.get('name')}) with no "
                                  "matching adoption record here: see devcloud vm ls")


def _preflight(ctx, chan, record):
    """Before anything is changed: no existing account or home that setup.sh
    would remove or take over to make the profile's user (it deletes an
    `ubuntu` account holding the uid, and adds to a home it finds). Adopt
    never deletes or replaces an account; the machine keeps the verdict, so
    a resume after setup.sh made the user is not refused for it."""
    build = ctx.profile.build
    for key in BUILD_KEYS:
        if not build.get(key):
            raise DriverError(FAILED, f"the profile's build.env lacks {key}, which setup.sh needs")
    args = " ".join(shlex.quote(build[key]) for key in BUILD_KEYS)
    found = json.loads(_script(ctx, chan, f"preflight {args}", "checking the machine's accounts")
                       .strip().splitlines()[-1])
    if found["problems"]:
        raise DriverError(FAILED, f"{record.user}@{record.address} already has what setup.sh would remove or take "
                                  f"over to make the hosts' user {build['DEVCLOUD_USER']} (uid {build['DEVCLOUD_UID']}, "
                                  f"home {build['DEVCLOUD_HOME']}, the profile's build.env): "
                                  f"{'; '.join(found['problems'])}. Adopt never deletes or replaces an existing "
                                  "account; nothing was changed")


def _prepare(ctx, record, chan, keys):
    """`preparing`: the keys the machine had saved (once), the driver's key
    authorized for root, the recipe and setup.sh, the descriptor staged."""
    save(ctx, record)
    _script(ctx, chan, f"save-keys {record.user}", "saving the machine's authorized_keys")
    encoded = base64.b64encode("\n".join(keys).encode()).decode()
    _script(ctx, chan, f"authorize {encoded}", "authorizing the driver's key for root")
    try:
        hostctl.wait_ssh(ctx, record.address, record.name, ctx.clock() + SSH_WAIT)
    except DriverError:
        raise DriverError(FAILED, f"{record.address} refuses root over SSH with the driver's key (sshd's "
                                  "PermitRootLogin): adopt needs it, as every devcloud host does") from None
    ctx.say(f"setup     {record.name}: setup.sh from the plugin's recipe")
    hostctl.install_recipe(ctx, record.address, record.name, ctx.profile.build, adopting=True)
    desc = compose.descriptor(name=record.name, profile=ctx.profile, projects=record.projects,
                              expires=record.expires, creator=f"@{record.creator}" if record.creator else None,
                              spot=False, seed="file", adopted=True)
    hostctl.stage(ctx, record.address, record.name, desc)


def _boot(ctx, record):
    """`booted`: the descriptor installed (unless an earlier run did) and the
    boot started, then waited on; a finished boot is not started again."""
    from .up import wait_boot
    host = record.host
    if record.phase != "booted":
        record.phase = "booted"
        save(ctx, record)
    finished = _finished(ctx, host)
    if not finished:
        target = record.address if _answers(ctx, record.address, host) else record.name
        command = (f"test -e {hostctl.BOOT_ENV} || install -m 0600 -o root -g root {compose.STAGE} "
                   f"{hostctl.BOOT_ENV}; systemctl start --no-block devcloud-boot.service")
        result = ctx.remote.run(target, host.alias, command, timeout=120)
        if result.code != 0:
            raise DriverError(FAILED, f"starting the boot on {record.name} failed (exit {result.code})")
        wait_boot(ctx, host, record.address, ctx.clock() + BOOT_WAIT)
    record.ready = int(ctx.clock())
    save(ctx, record)


def _answers(ctx, target, host):
    return ctx.remote.run(target, host.alias, "true", timeout=CONTACT_TIMEOUT, connect_timeout=15).code == 0


def _finished(ctx, host):
    """Whether a boot already finished every step, asked over the tailnet."""
    answer = hostctl.progress(ctx, host.name, host.alias)
    if answer is None:
        return False
    data, unit = answer
    steps = data.get("steps", [])
    return unit != "activating" and len(steps) == 12 and all(s["state"] != "failed" for s in steps)


# --- the adopted machine's later life (ops dispatches here) ---------------------------------

def lease(ctx, record, wanted, confirmed):
    """The lease on the host alone, under its lock, then the record: there
    are no labels (§6.5). Past the lifetime cap from the adoption, only with
    the person's yes, as for a VM; `wanted` None keeps it (the caller holds
    that yes). Returns the host's LeaseSet."""
    cap = None if confirmed or wanted is None else record.created + ctx.profile.caps.lease_max
    done = hostctl.lease_set(ctx, record.host, wanted, cap=cap)
    record.expires, record.lifetime = done.expires, "keep" if done.expires is None else "ttl"
    save(ctx, record)
    return done


def down(ctx, record, force):
    """The release over the tailnet, else as root over the recorded public
    address, else as the original login user there (a release that stopped
    after it gave the keys back: the driver's key is gone, the descriptor
    stays for the retry); the record removed once the release is verified
    there, as the original login user with the person's own key. A machine
    with no descriptor installed never booted (or its release removed it,
    last of everything): there is nothing for `devcloud release` to load, so
    the driver rolls back what the adoption delivered itself."""
    host = record.host
    login = None
    if hostctl.reachable(ctx, host):
        target = record.name
    elif _answers(ctx, record.address, host):
        target = record.address
    elif _released(ctx, record, wait=0):
        note = _desk_note(ctx, record, left_desk=False) + tailnet.remove(ctx, record.name)
        remove(ctx, record)
        ctx.say(f"{record.name}: already released (it keeps running at {record.address}); its record is "
                f"removed{note}")
        return 0
    elif _as_login(ctx, record, "true", timeout=CONTACT_TIMEOUT, connect_timeout=15).code == 0:
        target, login = record.address, record.user
    else:
        raise DriverError(FAILED, f"{record.name} answers neither over the tailnet nor at {record.address} (as root, "
                                  f"or as {record.user} with your own key): the adoption record stays")
    chan = _at(ctx, record, target, login)
    found = json.loads(_script(ctx, chan, "inspect", "inspecting the machine").strip().splitlines()[-1])
    if found.get("descriptor") is None:
        return _roll_back(ctx, record, chan)
    if not force:
        dirty = hostctl.unpushed(ctx, host, target=target, login=login)
        if dirty:
            raise DriverError(5, f"{record.name} has unpushed work in {', '.join(r for r, _ in dirty)}: push it, or "
                                 "pass --force")
    record.phase = "released"
    save(ctx, record)
    outcome = hostctl.release(ctx, host, target, no_hold=force, login=login)
    if outcome == hostctl.HELD:
        raise DriverError(FAILED, f"{record.name}'s release is held (its ship failed, or sessions keep starting): fix "
                                  "it, or pass --force; the adoption record stays")
    if outcome == hostctl.UNKNOWN:
        raise DriverError(FAILED, f"the connection to {record.name} dropped before its release was ready to log "
                                  "out: the outcome is unknown, and the adoption record stays")
    if outcome not in (hostctl.DONE, hostctl.AFTER_READY):
        raise DriverError(FAILED, f"{record.name}'s release ended {outcome}; run devcloud vm down {record.name} again "
                                  "to resume it (the adoption record stays)")
    if not _released(ctx, record, wait=VERIFY_WAIT):
        raise DriverError(FAILED, f"{record.name} was released, but a check as {record.user}@{record.address} did "
                                  "not confirm it: the adoption record stays; down again once it answers")
    # Released and verified: what the tailnet still lists of it goes (its own
    # removal, after the logout, may have failed; board #118).
    note = _desk_note(ctx, record, outcome.left_desk) + tailnet.remove(ctx, record.name)
    remove(ctx, record)
    ctx.say(f"{record.name}: released; the machine keeps running at {record.address} ({record.user} reaches it "
            f"as before){note}")
    return 0


def _at(ctx, record, target, login):
    """Root commands at `target` (the tailnet name or the public address), as
    root with the driver's key, or through `login` with the person's own."""
    def chan(command, **kw):
        return ctx.remote.run(target, record.name, hostctl.as_root(login or "root", command),
                              **({"user": login, "person": True} if login else {}), **kw)
    return chan


def _roll_back(ctx, record, chan):
    """An adoption with no descriptor installed, given back: the ledgered
    paths (the seed), the staged descriptor, the units setup.sh installed,
    the saved keys restored (adopt_host's `rollback`); then verified as a
    release is before the record goes. Its phase is left as it was until
    then: a rollback that stopped part way is down's to run again."""
    ctx.say(f"{record.name}: its adoption never booted (phase {record.phase}); rolling back what it delivered")
    _script(ctx, chan, "rollback", "rolling back the adoption")
    if not _released(ctx, record, wait=VERIFY_WAIT):
        raise DriverError(FAILED, f"{record.name} was rolled back, but a check as {record.user}@{record.address} did "
                                  "not confirm it: the adoption record stays; down again once it answers")
    remove(ctx, record)
    ctx.say(f"{record.name}: rolled back; the machine keeps running at {record.address} ({record.user} reaches it "
            "as before)")
    return 0


def _desk_note(ctx, record, left_desk):
    """What the release leaves at the desk, as for a deleted VM (the reaper's
    note): an adoption enrolled with the provisioning key whose leave was
    not confirmed may stay in the desk's Machines until removed by hand."""
    labels = {"devcloud-enroll": record.enroll} if record.enroll else {}
    if record.expires is not None:
        labels["devcloud-expires"] = str(record.expires)
    return reaper.desk_note(ctx, {"name": record.name, "labels": labels}, left_desk)


def _released(ctx, record, wait):
    """A new connection as the original login user, with the person's own
    key, to the public address finds nothing of devcloud left."""
    deadline = ctx.clock() + wait
    while True:
        result = _as_login(ctx, record, RELEASED, timeout=CONTACT_TIMEOUT, connect_timeout=15)
        if result.code == 0:
            return True
        if ctx.clock() >= deadline:
            return False
        ctx.sleep(10)
