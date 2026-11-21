"""`devcloud vm owner <name> <thread>` (EN.G1's plan, Interfaces §5): a host
handed to another thread of this machine, which then owns it — receives its
notices, and is refused a retire while it lasts.

The thread is sminos's to name (`sminos who --thread`); what is refused is
decided here, before anything is asked of a host or a provider. Then the
host is written first, by a program the driver sends (owner_host.py), then
the provider's label or this Mac's adoption record, then both are read
back, and a handover is reported only when both hold what this run wrote.
A reply that is lost, the host's or the provider's, is never read as a
write that failed, nor a command that timed out as one that did nothing:
the read-back says what holds, and "not known" of what it could not read.
Run again, every step finds its part done, or does it."""

from . import adopt, hostctl
from .errors import FAILED, DriverError

UNREAD = "what could not be read"


def _refusal(given, t):
    """§5's refusal for a thread a VM is not handed to, or None."""
    alias, short, machine = t.get("alias"), t.get("short"), t.get("machine")
    if not t["thread"]:
        return (f"owner: {given} is a session, not a thread (one the MAWS app launched keeps MAWS's rules), and a VM "
                "is owned by a thread: nothing was changed")
    if not t["session"]:
        return f"owner: {alias} holds no session (a vacant seat); fill it first: nothing was changed"
    if not t["local"]:
        return (f"owner: {alias}#{short} is a thread of {machine}, and a VM is handed to a thread of the machine this "
                "runs on, the only place sminos asks devcloud what a thread owns: run it on "
                f"{machine}; nothing was changed")
    if t["ended"]:
        return (f"owner: {alias} has ended (retired, or stopped for three days), and a VM is handed to a thread that "
                "has not: nothing was changed")
    if t.get("project") is None:
        return (f"owner: sminos could not read {alias}'s project from here (its directory is in a folder macOS "
                "protects): run it from inside that folder; nothing was changed")
    return None


def host_words(held):
    """What a host was read to hold."""
    if held is None:
        return UNREAD
    if not held.tag:
        return "no owner"
    return f"{held.tag} with project {held.project}" if held.project else f"{held.tag} with no project"


def run(ctx, name, given):
    t = ctx.thread(given)
    refused = _refusal(given, t)
    if refused:
        raise DriverError(FAILED, refused)
    short, project = t["short"], t["project"]
    tag = "@" + short
    record = adopt.load(ctx, name)
    entry = None if record is not None else ctx.find(name)
    host = record.host if record is not None else entry.host
    old = record.creator if record is not None else entry.vm["labels"].get("devcloud-creator")

    def holds(held):
        return held is not None and held.tag == tag and (held.project == project["id"] or not held.takes_project)

    # The host first: it sends the notices, and a host that refuses changes nothing. An acknowledgement that does
    # not confirm what was asked is no answer either: the recovery read says what the host holds.
    seen = []
    held = hostctl.owner_set(ctx, host, tag, project["id"], seen=seen)
    if held is not None and not holds(held):
        seen.append(f"exit 0: it answered {host_words(held)}")
        held = None
    if held is None:
        now = hostctl.host_owner(ctx, host)
        if now is None:
            raise DriverError(FAILED, f"{name} gave no answer about its owner ({seen[0]}): what it holds is not "
                                      f"known, and nothing else was changed; run devcloud vm owner {name} {given} "
                                      "again")
        if not holds(now):
            raise DriverError(FAILED, f"{name} gave no whole answer to the new owner ({seen[0]}) and holds "
                                      f"{host_words(now)} now; the command may still be running there. Nothing else "
                                      f"was changed: run devcloud vm owner {name} {given} again to settle it")
    # Then the label or the record. A failure or a lost reply here does not end the verb: the read-back says.
    if old != short:
        if record is not None:
            try:
                written = adopt.update(ctx, name, creator=short)
            except (OSError, DriverError) as error:
                written = True       # not known to be gone: the read-back says what the record holds
                ctx.warn(f"devcloud vm: {name}'s adoption record: {getattr(error, 'strerror', None) or error}")
            if written is None:
                raise adopt.gone(name)
        else:
            try:
                ctx.merge_labels(entry, {"devcloud-creator": short})
            except DriverError as error:
                ctx.warn(f"devcloud vm: {name}'s label: {error}")
    # Both sides read back, the host by its own parser.
    held = hostctl.host_owner(ctx, host)
    if record is not None:
        where = "this Mac's adoption record"
        try:
            now = adopt.load(ctx, name)
        except DriverError:
            label = UNREAD
        else:
            if now is None:
                raise adopt.gone(name)
            label = now.creator
    else:
        where = "its provider's label"
        try:
            vm = entry.client.get(entry.vm["id"])
            label = vm["labels"].get("devcloud-creator") if vm is not None else UNREAD
        except DriverError:
            label = UNREAD
    if not (holds(held) and label == short):
        named = UNREAD if label == UNREAD else f"@{label}" if label else "no owner"
        raise DriverError(FAILED, f"{name}'s owner is not settled: the host, which sends its notices, holds "
                                  f"{host_words(held)}, and {where}, which decides whom sminos refuses to retire, "
                                  f"names {named}; this run wrote {tag} with project {project['id']}. Another devcloud "
                                  f"vm owner ran at the same time, or a write did not land: run devcloud vm owner "
                                  f"{name} {given} again to settle it")
    who = f"{t['alias']}#{short} ({project['name']} on {t['machine']})"
    if old == short:
        ctx.say(f"{name} is owned by {who} already")
    elif old:
        ctx.say(f"{name} was owned by @{old}; {who} owns it now")
    else:
        ctx.say(f"{name} had no owner; {who} owns it now")
    if not held.takes_project:
        ctx.say(f"{name} was built before a host kept its owner's project: a notice no session of {t['alias']} "
                "takes ends in its journal")
    return 0
