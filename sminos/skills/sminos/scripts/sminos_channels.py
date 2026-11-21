#!/usr/bin/env python3
"""sminos_channels — what reads and decides for declared channels (CH1 of
docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md; its plan,
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, Interfaces §1 and
§5).

A channel is a log whose id passes sminos.is_channel_id. It is no project:
its view has no members (sminos.view_of), nothing of this machine is
published under its id, and a fact about a thread goes to the thread's own
project. What is here:

- Finding a channel by its id, `name#short` or name (find_channel), with the
  one refusal for a name several logs answer to (sminos.ambiguous_name).
- Registering one as the org's directory registers a log (register).
- Whether this machine opens a channel's log without `follow`
  (opens_unfollowed): read from this machine's thread records and nothing
  else (held_channels), which MAWS counts, with a member frame naming the
  channel, as this machine holding it.
- A thread's own add or remove (change, §3's rows C1 and C2), through the
  one operation that writes a set (sminos_threads.set_channels); what the
  record holds of it (channels_of, began_of), and what a change came to
  (Outcome, §6).
- The log kept equal to the record (restate, §3's row C5): what the
  reconciliation (sminos._keep_sets) calls when a log states otherwise than
  a thread's record, with what it read there.
"""
import os
import sys
import time
from typing import NamedTuple

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos  # noqa: E402


def find_channel(q, required=True):
    """The channel `q` names: by its id, `name#short` or name. Exit 4 with
    the one refusal when several logs answer, with "no channel '<q>' is
    known on this machine" for none (None instead with required=False), and
    with "'<q>' is a project, not a channel" for a project."""
    out, clash = sminos._name_tiers(q)
    if clash:
        sminos.die(sminos.ambiguous_name(q, clash), sminos.EXIT_UNKNOWN)
    if not out:
        if not required:
            return None
        sminos.die("no channel '%s' is known on this machine" % q, sminos.EXIT_UNKNOWN)
    if not sminos.is_channel_id(out[0].id):
        sminos.die("'%s' is a project, not a channel" % q, sminos.EXIT_UNKNOWN)
    return out[0]


def register(channel_id, name):
    """The channel registered here as the org's directory registers a log
    (sminos.register_if_absent: no root, the enrollment's hub), a
    registration already there kept. ValueError for an id that is no
    channel's, or on a machine not enrolled at a hub."""
    if not sminos.is_channel_id(channel_id):
        raise ValueError("%r is no channel's id" % (channel_id,))
    e = sminos.enrollment()
    if e is None:
        raise ValueError("this machine is not enrolled at a desk hub: a channel's log syncs through one")
    sminos.register_if_absent(sminos.make_project(channel_id, name, "", "", {"url": e["url"], "org": e["org"]}))
    sminos.forget_caches()
    return sminos.known_project(channel_id)


_HELD = {}   # "generation": the cache generation it was last asked in, "key": the stores' stat key, "value"


def _stores_key():
    """Both thread stores as a stat reads them: every seat record file and
    every live record of a thread its human opened (each written by atomic
    replace)."""
    out = []
    for path in sminos.record_files():
        try:
            st = os.stat(path)
        except OSError:
            continue
        out.append((os.path.basename(path), st.st_ino, st.st_size, st.st_mtime_ns))
    return tuple(out), sminos.threads_module().store_key()


def held_channels():
    """Every channel id in the set of a thread of this machine that has not
    ended (sminos_threads.all_threads; a set aside record is ended), as a
    frozenset. Read again only in a new cache generation whose stores' stat
    key moved: the uplink asks at every scan for each channel it opened."""
    generation = sminos._GENERATION[0]
    if _HELD.get("generation") == generation:
        return _HELD["value"]
    key = _stores_key()   # before the read: a write during it moves the key the next generation compares
    if _HELD.get("key") != key or "value" not in _HELD:
        threads = sminos.threads_module()
        _HELD["value"] = frozenset(c for t in threads.all_threads() if not threads.record_ended(t)
                                   for c in _channels_of(t) if sminos.is_channel_id(c))
        _HELD["key"] = key
    _HELD["generation"] = generation
    return _HELD["value"]


def _channels_of(record):
    """A thread record's `channels`, read where it is read: a value that is no
    list (a hand edit, another version's) is none."""
    chs = record.get("channels")
    return chs if isinstance(chs, list) else ()


def opens_unfollowed(channel_id):
    """Whether this machine opens the channel's log without `follow`: a
    thread of this machine that has not ended is in it, by its record alone
    (C1). sminos does not keep this equal to MAWS's `known`, which also needs
    that thread's member frame to name the channel."""
    return channel_id in held_channels()


# ------------------------------------------------------------ the record's set (§3, §5) and a thread's own change

REQUEST_TTL = 7 * 86400   # seconds a request can be pending, by its own ts (C3); SMINOS_CHANNEL_REQUEST_TTL
REASONS = ("not-reachable", "read-only", "limit")   # why a request is refused (C2)


class Outcome(NamedTuple):
    """What became of a change of a thread's set (§6). `state`: applied,
    refused, pending, ignored or failed; `why`: for refused one of REASONS,
    for pending, ignored and failed a word of §6's tables, for applied
    "unchanged" when the set already read so (nothing was written), else
    ""."""
    state: str
    why: str = ""


def request_ttl():
    try:
        return float(os.environ.get("SMINOS_CHANNEL_REQUEST_TTL") or REQUEST_TTL)
    except ValueError:
        return float(REQUEST_TTL)


def expired(request, now=None):
    """Whether a request can no longer be pending: its `ts` unreadable, or
    older than the request lifetime (C3: seven days by its own timestamp)."""
    at = sminos._ts_epoch((request or {}).get("ts"))
    return at is None or (time.time() if now is None else now) - at > request_ttl()


def channels_of(session):
    """The set of the thread whose current session `session` is, when it is a
    thread of this machine that has not ended; () otherwise (§5): what the
    record holds, which the member frame carries and a bare `list` reads for
    its caller."""
    threads = sminos.threads_module()
    t = threads.current_record(session)
    return tuple(threads.held_set(t)) if t is not None else ()


def began_of(thread_id, channel_id):
    """Where the thread's membership of the channel began (§4): its record's
    positions for it, {writer: seq}; None when the thread is not in it. A
    channel of the set the record keeps no positions for reads as {}:
    nothing was held then."""
    threads = sminos.threads_module()
    t = threads.get(thread_id)
    if t is None or channel_id not in threads.held_set(t):
        return None
    began = t.get("began") if isinstance(t.get("began"), dict) else {}
    held = began.get(channel_id)
    return dict(held) if isinstance(held, dict) else {}


def _member_of(project, session):
    """Whether the session's own events in the project's log leave it a
    member there, read from its writer files as they are (no lock taken,
    nothing written): what decide() may read (§3)."""
    return project is not None and sminos.threads_module().member(sminos._own_events(project, session))


def change(thread_id, channel, op, session, lock_until=None):
    """A thread's own add (`op` "add") or remove ("remove") of a channel (an
    id, or its Project), §3's rows C1 and C2: an Outcome, `applied`
    ("unchanged" when the set already read so: nothing is written), refused
    `limit` for a 129th channel, or `failed` with why it could not be
    recorded: `wake` (a wake of the thread holds its wake lock, or this
    process does), `entry` (its record holds an operation not finished
    yet), `vacant` (it holds no session), `between` (its session is a member
    of no project now), `moved` (`session` is not the thread's current one
    any more, or the thread ended) or `unreadable` (the channel's log is
    there and could not be read, so where the membership begins is not
    known). Never `pending`: no request exists for a
    later pass to carry out, so the caller says nothing was recorded and to
    run it again.

    The statement goes to the project in whose log the session is a member
    at the write, read under the record's lock from the session's own
    events there; the project read before the lock only chooses where to
    look, and a session found elsewhere by then is looked for again. An
    entry the record holds is finished first, with no wake lock held; the
    one this change opens is finished after its write, and a finish cut
    short is the next reconciliation's. The daemon is nudged after a write."""
    cid = getattr(channel, "id", channel)
    if op not in ("add", "remove") or not sminos.is_channel_id(cid):
        raise ValueError("change(%r, %r): an add or a remove of a channel id" % (op, cid))
    threads = sminos.threads_module()
    if sminos.wake_held(thread_id) is not None:
        return Outcome("failed", "wake")   # a wake of the thread under way in this process: never across it
    if not sminos.finish_thread(thread_id, lock_until=lock_until):
        return Outcome("failed", "entry")
    project = sminos.last_project(session) if session else None
    for _ in range(3):
        t = threads.get(thread_id)
        if t is None or threads.record_ended(t) or (session and t["current"] and t["current"] != session):
            return Outcome("failed", "moved")
        if not session or not t["current"]:
            return Outcome("failed", "vacant")
        said = []

        def decide(rec, project=project):
            if rec["current"] != session:
                said.append("vacant" if not rec["current"] else "moved")
                return None
            if not _member_of(project, session):
                said.append("between")
                return None
            said.append("between")   # set_channels' own last read, after the positions, may find it moved since
            chans = threads.held_set(rec)
            if (cid in chans) == (op == "add"):
                said[-1] = "unchanged"
                return None
            if op == "add" and len(chans) >= threads.CHANNEL_LIMIT:
                said[-1] = "limit"
                return None
            after = chans + [cid] if op == "add" else [c for c in chans if c != cid]
            return {"project": project, "session": session, "channels": after, "answer": None}
        try:
            entry = threads.set_channels(thread_id, decide, lock_until=lock_until)
        except sminos.WakeBusy:
            return Outcome("failed", "wake")
        except sminos.PositionsUnread as e:
            sminos.warn(str(e))
            return Outcome("failed", "unreadable")
        if entry is not None:
            # Committed: the record holds the change whatever comes of its statement now. A finish that cannot be
            # had (its finisher lock busy past the deadline, a write that fails) leaves the entry to the replay.
            try:
                sminos.finish_thread(thread_id, project=project, lock_until=lock_until)
            except (sminos.LockBusy, sminos.LogWriteFailed, OSError) as e:
                sminos.warn("the statement of %s's channels is left to the next reconciliation: %s"
                            % (thread_id[:8], e or "its lock is busy"))
            sminos.nudge_daemon()
            return Outcome("applied")
        if not said:   # decide was not asked: an entry opened since, or the record ended
            return Outcome("failed", "entry" if (threads.get(thread_id) or {}).get("pending") else "moved")
        if said[0] == "unchanged":
            return Outcome("applied", "unchanged")
        if said[0] == "limit":
            return Outcome("refused", "limit")
        if said[0] != "between":
            return Outcome("failed", said[0])
        sminos.forget_caches()   # the project read before the lock: is the session a member elsewhere now?
        again = sminos.last_project(session)
        if getattr(again, "id", None) == getattr(project, "id", None):
            return Outcome("failed", "between")
        project = again
    return Outcome("failed", "between")


def restate(project, thread_id, session, writer, seen, appended=None):
    """§3's row C5: the record's set stated in `project`'s log, as the
    reconciliation read it there: `session` the thread's current session,
    a member of the project, its own events going under `writer` (the
    writer of its `joined` in effect), and `seen` the record's set. Each is
    read again under the record's lock (set_channels; in its last guard the
    writer, by this machine's name read afresh, and the project, as the one
    the session's newest `joined` here names: sminos.restated_holds), and
    if any of them moved, or the record has an open entry or has ended, nothing is written
    and the next reconciliation notices afresh: a reconciliation overtaken
    by a removal or a move never states the set it read. It only tries the
    wake lock: a wake in flight, another process's or one under way in this
    one, writes nothing. The store's lock is waited for as any
    reconciliation's write waits.

    True when the statement was owed and its entry begun; the entry is
    finished here (the statement appended through `lifecycle`, gaining
    `appended`), and a finish cut short is the next reconciliation's. The
    daemon is nudged after the write."""
    threads = sminos.threads_module()
    seen = list(seen)

    def decide(rec):
        if rec["current"] != session or threads.held_set(rec) != seen:
            return None
        try:
            if sminos.own_stream(project, session)[0] != writer:
                return None
        except sminos.audience_module().StreamUnknown:
            return None
        return {"project": project, "session": session, "channels": list(threads.stated_set({"channels": seen})),
                "answer": None, "writer": writer}
    try:
        entry = threads.set_channels(thread_id, decide, wake_until=time.time())
    except (sminos.LockBusy, sminos.PositionsUnread):   # WakeBusy is a LockBusy
        return False
    if entry is None:
        return False
    try:
        sminos.finish_thread(thread_id, appended, project=project)
    except (sminos.LockBusy, sminos.LogWriteFailed, OSError) as e:
        sminos.warn("the statement of %s's channels is left to the next reconciliation: %s"
                    % (thread_id[:8], e or "its lock is busy"))
    sminos.nudge_daemon()
    return True
