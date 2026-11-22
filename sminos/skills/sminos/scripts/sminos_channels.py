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
- Requests (§2, §6): the ordered input of a channel's log (requests_of),
  the one function that decides one (judge, §6's table, no effect), the one
  that carries it out (carry_out: judge again under the record's lock, on
  reads fresh in fact), and the pass that calls it in the log's order
  (carry_due: the command, the daemon's channel pass, and from M7 the
  uplink at an answer); who sent one (sender_verified) and what a word was
  asked for (reach_token, event_key).
- The verbs `channel create`, `add` and `remove` (cmd_channel, place).
- The roster (§5): the rows, each its thread's own row in its own
  project's view, whose log states the channel (rosters, roster), read by
  `list`, `channel show`, `channel env` and the pool and by nothing that
  delivers, addresses or publishes (C1); what became of a request (answers,
  answer_of: an index of the statements that answer one, never the fold);
  the pool (pool: the roster's rows by machine, and the machines a member
  added by hand, `channel-env`); `channel show` and `channel env` (show,
  env).
"""
import json
import os
import re
import sys
import time
import uuid
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


def frame_channels(session, holders=None):
    """channels_of(session) as a member frame carries it (§7, X5): its
    entries that are channels' ids, in order, the first 128; () for a
    thread in none, ended, or no thread. Read from the threads that hold a
    set (sminos_threads.set_holders: the records channels_of reads, by the
    same rule, kept while the stores' index is the same), so a thread in
    none is one lookup; `holders`, that map as a caller read it once for
    many."""
    threads = sminos.threads_module()
    t = (threads.set_holders() if holders is None else holders).get(session) if session else None
    if t is None:
        return ()
    return tuple(c for c in threads.held_set(t) if sminos.is_channel_id(c))[:threads.CHANNEL_LIMIT]


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
    member there, read from its writer files as they are, chosen by this
    machine's names as its identity file holds them now (no lock taken,
    nothing written): what decide() may read (§3)."""
    return project is not None and sminos.threads_module().member(sminos.own_events_now(project, session))


def change(thread_id, channel, op, session, lock_until=None):
    """A thread's own add (`op` "add") or remove ("remove") of a channel (an
    id, or its Project), §3's rows C1 and C2: an Outcome, `applied`
    ("unchanged" when the set already read so: nothing is written), refused
    `limit` for a 129th channel, or `failed` with why it could not be
    recorded: `wake` (a wake of the thread holds its wake lock, or this
    process does), `entry` (its record holds an operation not finished
    yet), `vacant` (it holds no session), `between` (its session is a member
    of no project now), `moved` (`session` is not the thread's current one
    any more, or the thread ended), `unreadable` (the channel's log is
    there and could not be read, so where the membership begins is not
    known), `lane-b` or `record-unreadable` (set_channels' last reads: the
    session is lane B now, or its record is there and cannot be read).
    Never `pending`: no request exists for a later pass to carry out, so
    the caller says nothing was recorded and to run it again.

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
            made.append({"project": project, "session": session, "channels": after, "answer": None})
            return made[-1]
        made = []
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
        unwritten = made[-1].get("unwritten") if made else None
        if unwritten in ("moved", "lane-b", "record-unreadable"):
            return Outcome("failed", unwritten)   # set_channels' last reads: not this thread's now, or not readable
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


# ------------------------------------------------------------ requests and their carrying out (§2, §6)

# What a command and `channel show` print for an outcome's word (§6's words): a refusal's reason, a pending or
# ignored word. `moved` is a request's word; a thread's own change that could not be recorded says OWN_FAILED's.
WORDS = {
    "not-reachable": "its machine does not let you message it",
    "read-only": "its machine admits nothing from outside",
    "limit": "it is in %d channels, the limit" % 128,
    "duplicate": "not carried out: another request in this channel used its id first",
    "earlier": "behind an earlier request for it in this channel",
    "entry": "its record holds an unfinished operation",
    "wake": "it is being woken; its machine's next pass carries this out",
    "busy": "its record is being written by another process; its machine's next pass carries this out",
    "vacant": "the thread holds no session now",
    "between": "its session is between two projects",
    "no-channels": "its machine's endpoint does not serve channels",
    "unverifiable": "its machine cannot read its revocation set",
    "endpoint": "its machine's endpoint has not said whether you may message it",
    "moved": "its session, its reach or the channel's log changed while its machine decided: tried again",
    "unreadable": "the channel's log is there and could not be read; its machine's next pass carries this out",
    "record-unreadable": "its session's record is there and could not be read; its machine's next pass carries this "
                         "out",
    "queued": "it waits in its machine's queue under a name the machine wrote as before; it is carried out once the "
              "queue is released",
    "expired": "not carried out: the request is more than seven days old",
    "not-here": "not carried out: it names a session that is no longer that thread's, or a thread that has ended",
    "audience": "not sent (its endpoint refused the audience it went under: its target's reach changed before it "
                "was signed)",
}
# Why a thread's own add or remove was not recorded (change's `failed`), in `nothing was recorded (<why>)`.
OWN_FAILED = {
    "wake": "it is being woken",
    "entry": "its record holds an unfinished operation",
    "vacant": "the thread holds no session now",
    "between": "its session is between two projects",
    "moved": "this session is no longer its thread's current one, or the thread has ended",
    "unreadable": "the channel's log is there and could not be read",
    "lane-b": "this session is lane B now, and no thread",
    "record-unreadable": "this session's record is there and could not be read",
}
CAPABILITY_REFUSAL = ("this machine's endpoint does not serve channels (its welcome listed no channels): nothing "
                      "was written")
LIMIT_REFUSAL = "%s is in 128 channels, the limit: nothing was written"
CARRIED = ("applied", "refused")   # the outcomes a write records; every other is said and writes nothing


REQUEST_ID_RE = re.compile(r"[0-9a-f]{32}")   # a request's `id` as §2 writes it (uuid4().hex)


def is_request(e):
    """Whether an event is a `channel-request` of §2's shape: `op` add or
    remove, a `session`, a `thread` and a writer, each a string that is not
    empty, and an `id` of 32 lower-case hex digits, as the verbs write it.
    A reader takes any other as no request: an answer copies the id into
    its target's own project, whose readers may be more than the request's,
    so nothing but a random id is ever carried there."""
    return isinstance(e, dict) and e.get("kind") == "channel-request" and e.get("op") in ("add", "remove") \
        and all(isinstance(e.get(k), str) and e[k] for k in ("session", "thread", "writer")) \
        and isinstance(e.get("id"), str) and REQUEST_ID_RE.fullmatch(e["id"]) is not None


def _logged_requests(events):
    return [e for e in events if is_request(e)]


def input_signature(channel):
    """The signature of the files the ordered input of a carrying out is
    read from (requests_of): the channel log's writer files and its queued
    appends as _input_files lists them, each as a stat gives it, read by
    stats alone (no file parsed, no lock, nothing written): what decide()
    compares under the record's lock, so the input is read and merged only
    outside it."""
    return _signature(*_input_files(channel))


def _signature(logs, queues, unlisted):
    def keys(paths):
        out = []
        for path in paths:
            try:
                st = os.stat(path)
                out.append((path, st.st_ino, st.st_size, st.st_mtime_ns))
            except OSError:
                out.append((path, None))
        return tuple(out)
    return keys(logs), keys(queues), tuple(unlisted)


def _input_files(channel):
    """([the log's writer files], [its queues], [the directories of them
    that are there and cannot be listed]): the ordered input's files, each
    directory listed once (os.listdir), strictly: a listing that fails is
    no empty directory (glob, which the store's readers list through, takes
    it for one), and only one that does not exist holds nothing, as where a
    membership begins reads it (sminos.channel_positions). requests_of
    reads the files this lists, never a listing of its own beside it."""
    out, unlisted = [], []
    for where in (os.path.join(channel.home, "log"), os.path.join(channel.home, sminos.QUEUED)):
        try:
            names = os.listdir(where)
        except FileNotFoundError:
            names = []
        except OSError:
            names = []
            unlisted.append(where)
        out.append(sorted(os.path.join(where, n) for n in names if n.endswith(".jsonl") and not n.startswith(".")))
    return out[0], out[1], unlisted


def requests_of(channel, whole=True):
    """(signature, requests): the ordered input of a carrying out (§6). The
    channel log's requests in the merged read's order, then those among this
    machine's queued appends for that log (an append that waits for its
    writer's head), in the queue's order, each with `seq` None, read without
    changing the queue; one whose writer and id the log holds already (a
    release cut short) once. The signature (input_signature) is taken
    before the read, so a file that moves during it moves it too; both are
    of the files one strict listing gave (_input_files).

    A directory of the input (its log, its queues) that is there and cannot
    be listed, a writer file of the log, or a queue, that is there and
    cannot be read raises sminos.PositionsUnread, as an unreadable channel
    log does where a membership begins (Y3): an input missing a file has no
    order, and a request after one it cannot see must not be carried past
    it. `whole` False reads what it can instead (`channel show`, which only
    reads)."""
    logs, queue_files, unlisted = _input_files(channel)
    sig = _signature(logs, queue_files, unlisted)
    unread = list(unlisted) if whole else []
    files, events = sminos._store_whole(channel, "log", shared=True, paths=logs)
    unread += [path for path, key in files if key is None and not _gone(path)]
    try:
        queues = sminos.queued_operators(channel, paths=queue_files)
        queued = sminos.said_order(queues) if queues else []
    except OSError as e:
        unread.append(getattr(e, "filename", None) or "its queue")
        queues, queued = {}, []
    if unread and whole:
        raise sminos.PositionsUnread("channel %s: %s cannot be read, so no request of it is carried out"
                                     % (channel.name, ", ".join(sorted(os.path.basename(str(p)) for p in unread))))
    logged = sminos.log_memo(events, "channel-requests", _logged_requests)
    held = {(e["writer"], e["id"]) for e in logged}
    queued = [{**e, "seq": None} for e in queued if is_request(e) and (e["writer"], e["id"]) not in held]
    return sig, [dict(e) for e in logged] + queued


def _gone(path):
    """Whether a listed file is no longer there: FileNotFoundError alone. A
    stat refused any other way (a permission) says nothing of whether it
    is there, so the file is unread, never absent (os.path.lexists is False
    for both)."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _queued_under_former_name(request):
    """Whether a request is one of this machine's queued appends made under
    a name it no longer writes as (seq None, its writer's machine not its
    name now): its release rewrites it under the name now, with the same id
    (sminos.release_queued), and until then nothing here can tell who wrote
    it. Never a logged event: a former name extends no trust to what a log
    holds."""
    return request.get("seq") is None \
        and sminos.writer_base(str(request.get("writer") or "")).rpartition("/")[0] != sminos.machine_name_now()


def event_key(channel, request):
    """What a word of the endpoint's is asked and kept under (§6): the
    channel's id, the request's writer, its seq and its event hash, as a
    reach permit is keyed. A word answers the event it was asked about and
    no other request, whatever id that other carries."""
    return (getattr(channel, "id", channel), request.get("writer"), request.get("seq"), sminos.event_hash(request))


class _Facts:
    """What judge() reads beside the record, each from its file as it is
    when asked: the machine's identity and enrollment (the shared helpers'
    `fresh` reading, never the invocation's cache), the policy, the kept
    capabilities, the revocation set, the session records and the thread
    stores, taking no lock and writing nothing (§3). One evaluation's: a
    record asked for twice in it reads once."""

    def __init__(self):
        self._current, self._ended = {}, {}

    def current_record(self, session):
        """The record whose current session `session` is, from the stores as they are."""
        if session not in self._current:
            self._current[session] = sminos.threads_module().current_record(session, fresh=True)
        return self._current[session]

    def ended_owner(self, session):
        """The record, ended or set aside, whose current session `session` still
        is (thread_of's order; a reservation is none), from the stores as they
        are: for §6's row 3 when no live record holds it (C6)."""
        if session not in self._ended:
            threads = sminos.threads_module()
            t = threads.thread_of(session)
            self._ended[session] = t if t is not None and t["current"] == session and not threads.reservation(t) \
                else None
        return self._ended[session]

    def outside_origin(self, channel, e):
        """Rows 8 and 9: a request this machine did not append itself
        (appended_here) is from outside, whatever its writer's name."""
        return not appended_here(channel, e)

    def read_only(self):
        """The policy's `read_only`, read now; a file that is no policy reads
        as read-only (policy.load's rule, without its note in daemon.log)."""
        d = sminos.sibling_module("sminos_policy").stored()
        return True if d is None else bool(d.get("read_only", False))

    def serves_channels(self):
        return sminos.audience_module().advertised("channels")

    def lane_b(self, session):
        records = sminos.records_module()
        return bool(session) and records.lane_of(records.read(session)) == "B"

    def shares_owners(self, channel, e, session):
        """Row 10: a request this machine appended itself (appended_here, the
        one test of "this machine's own" for every row) whose writer shares
        the thread's owners: a session's writer by sminos.same_owner_local,
        the human writer, which that rule does not answer for, by the
        target's record read now naming the machine's owners (machine_owns);
        by the identity read now. Every other request takes the endpoint's
        word."""
        if not appended_here(channel, e):
            return False
        writer = str(e.get("writer") or "")
        if sminos.writer_base(writer).rpartition("/")[2] != "human":
            return sminos.same_owner_local(e, session, channel, fresh=True)
        return machine_owns(session)


def appended_here(channel, request):
    """Whether this machine appended the request itself, the one test of a
    request being this machine's own (§6's rows 8 to 11; the holder's ruling
    of 2026-11-22), never its writer's name: one of its own queued appends
    (no position yet: the queue is this machine's alone, a former name's
    included), or a logged one its append receipt names (sminos.receipted:
    the receipt is written under the writer file's lock before the event,
    outside log/, so nothing imported has one, and it stays under the name
    the append used)."""
    return request.get("seq") is None or sminos.receipted(channel, request)


def machine_owns(session):
    """Whether the machine's owners (the person at its terminal) own the
    session, read from the session's record as it is now: it names the
    machine's token, or a member the endpoint resolved as the machine's
    owner. Never the endpoint's last resolved owners of the session itself,
    which a record replaced since (stronger provenance) can outlive."""
    records = sminos.records_module()
    rec = records.read(session) if session else None
    owners = rec.get("owners") if rec and isinstance(rec.get("owners"), list) else []
    if records.MACHINE in owners:
        return True
    resolved = sminos.audience_module().machine_owners()
    return bool(resolved) and bool(set(resolved) & set(owners))


def sender_verified(channel, request):
    """Whether the request's sender is held as verified (C3): True for a
    request this machine appended itself (appended_here). Else from the key
    an import stores on the event, `verified`, whatever its writer's name:
    False when it is no object or its signer is none or of kind `legacy`;
    None while the revocation set cannot be read; False when the set names
    the signer; else True."""
    if appended_here(channel, request):
        return True
    verified = request.get("verified")
    signer = verified.get("signer") if isinstance(verified, dict) else None
    if not isinstance(signer, dict) or signer.get("kind") == "legacy":
        return False
    rl10 = sminos.sibling_module("sminos_rl10")
    try:
        revoked = rl10.revoked()
    except rl10.RevokedUnreadable:
        return None
    return not rl10.signer_revoked(signer, revoked)


def reach_token(session):
    """What "its reach has not changed" compares (§6): the session's
    record's owners with its access, shares and policyRev
    (sminos_audience.policy_of), as one value; None while the record cannot
    be read. Read from the record's file as it is."""
    rec = sminos.records_module().read(session) if session else None
    if rec is None:
        return None
    access, shares, rev = sminos.audience_module().policy_of(rec)
    owners = rec.get("owners") if isinstance(rec.get("owners"), list) else []
    return (tuple(sorted(str(o) for o in owners)), access,
            tuple(sorted((s["member"], s["grade"]) for s in shares)), rev)


def _names_here(record, request, facts):
    """§6's row 3, the other way round: the request names `record`'s thread
    as this machine holds it. The record is there and has not ended, has had
    the request's session, that session is no other record's current one
    now (read from the stores as they are; for a session the record only
    had, an ended or set-aside record's included: the newer record it went
    on as still holds it once that ends, the frontier's second review, C6),
    and the thread's session is not lane B."""
    threads = sminos.threads_module()
    if record is None or record["thread"] != request["thread"] or threads.record_ended(record):
        return False
    session = request["session"]
    if session != record["current"] and session not in record["sessions"]:
        return False
    other = facts.current_record(session)
    if other is None and session != record["current"]:
        other = facts.ended_owner(session)
    if other is not None and other["thread"] != record["thread"]:
        return False
    return not facts.lane_b(record["current"])


def _answered(record):
    held = (record or {}).get("answered")
    return {(a[0], a[1]) for a in held if isinstance(a, list) and len(a) == 3} if isinstance(held, list) else set()


def _duplicate(request, earlier):
    return any(r["id"] == request["id"] and r["writer"] != request["writer"] for r in earlier)


_LOOK = object()   # judge's `project` not given: where the thread's session is, looked up (last_project)


def judge(channel, request, record, earlier, word=None, asked=None, project=_LOOK, now=None, facts=None):
    """§6's table and nothing else: an Outcome by the first row that holds,
    read with no write and no lock. `record` is the target's, as its caller
    read it; `earlier` the requests of the ordered input before this one;
    `word` the endpoint's ("deliver" | "refuse" | None), the one kept under
    this request's event_key and no other; `asked` {"session", "reach"} the
    word was asked for. `project`, the thread's own project as its caller
    found it (None for none); not given, it is looked up, which a caller
    under the record's lock never lets it do. "applied" and "refused" are
    what a write would record; nothing has been written."""
    threads = sminos.threads_module()
    facts = facts or _Facts()
    cid = getattr(channel, "id", channel)
    if expired(request, now):
        return Outcome("ignored", "expired")
    if _duplicate(request, earlier):
        return Outcome("ignored", "duplicate")
    if not _names_here(record, request, facts):
        return Outcome("ignored", "not-here")
    answered = _answered(record)
    if (cid, request["id"]) in answered:
        return Outcome("ignored", "answered")
    if _queued_under_former_name(request):
        # After whom it names and the ledger, before who may ask: a request that names no thread here, or is
        # answered, holds nothing back; one that does waits, its thread's later ones behind it.
        return Outcome("pending", "queued")
    for i, r in enumerate(earlier):
        if r["thread"] == record["thread"] and (cid, r["id"]) not in answered and not expired(r, now) \
                and not _duplicate(r, earlier[:i]) and _names_here(record, r, facts):
            return Outcome("pending", "earlier")
    if record.get("pending"):
        return Outcome("pending", "entry")
    current = record["current"]
    if not current:
        return Outcome("pending", "vacant")
    where = sminos.last_project(current) if project is _LOOK else project
    if not _member_of(where, current):
        return Outcome("pending", "between")
    outside = facts.outside_origin(channel, request)
    if outside and not facts.serves_channels():
        return Outcome("pending", "no-channels")
    if outside and facts.read_only():
        return Outcome("refused", "read-only")
    if not facts.shares_owners(channel, request, current):
        verified = sender_verified(channel, request)
        if verified is False:
            return Outcome("refused", "not-reachable")
        if verified is None:
            return Outcome("pending", "unverifiable")
        if word not in ("deliver", "refuse"):
            return Outcome("pending", "endpoint")
        reach = reach_token(current)
        if not isinstance(asked, dict) or asked.get("session") != current or reach is None \
                or asked.get("reach") != reach:
            return Outcome("pending", "moved")
        if word == "refuse":
            return Outcome("refused", "not-reachable")
    chans = threads.held_set(record)
    if request["op"] == "add":
        if cid in chans:
            return Outcome("applied", "unchanged")
        return Outcome("refused", "limit") if len(chans) >= threads.CHANNEL_LIMIT else Outcome("applied")
    return Outcome("applied", "" if cid in chans else "unchanged")


def _earlier(requests, request):
    """The requests of the ordered input before `request`: before the first
    of its writer and id, or all of them for one the input does not hold (a
    command's own, in hand)."""
    for i, r in enumerate(requests):
        if r["writer"] == request.get("writer") and r["id"] == request.get("id"):
            return requests[:i]
    return list(requests)


def carry_out(channel, request, word=None, asked=None, lock_until=None, wake_until=None, finishes=True):
    """One request (§6): judge() on what it reads, then, when that says a
    statement is owed, sminos_threads.set_channels with a decide that runs
    judge() again on the record it is given and on fresh reads, and writes
    that second answer or nothing; the Outcome is the second one's. An
    input whose signature moved since `earlier` was read is read again,
    three times in the call, then pending `moved`. The thread's open entry
    is finished first if it can be (with no wake lock held), so row 6 is
    what is left. A wake lock that cannot be had is pending `wake`;
    `wake_until`, when given, bounds its poll alone (a pass only tries it),
    `lock_until` the store lock's (and the wake lock's when no `wake_until`
    is given: a command waits as a transition does). `finishes` False (the
    uplink's pass, on its consumer's thread): an entry the record holds
    already is not finished here (another operation's replay takes locks no
    deadline bounds, a hand-off's carry among them), so the request is
    pending `entry` (row 6) until a reconciliation finishes it."""
    threads = sminos.threads_module()
    cid, tid = channel.id, request["thread"]
    why = "moved"
    for _ in range(3):
        try:
            sig, requests = requests_of(channel)
        except sminos.PositionsUnread:
            return Outcome("pending", "unreadable")
        earlier = _earlier(requests, request)
        record = threads.get(tid)
        if finishes and record is not None and record.get("pending") and not threads.reservation(record) \
                and sminos.wake_held(tid) is None:
            try:
                sminos.finish_thread(tid, lock_until=lock_until)
            except (sminos.LockBusy, sminos.LogWriteFailed, OSError):
                pass   # its entry is row 6's: pending
            record = threads.get(tid)
        project = sminos.last_project(record["current"]) if record is not None and record["current"] else None
        first = judge(channel, request, record, earlier, word, asked, project)
        if first.state not in CARRIED:
            return first
        if sminos.wake_held(tid) is not None:
            return Outcome("pending", "wake")   # a wake of the thread under way in this process: never across it
        said = []

        def decide(rec, project=project, sig=sig, earlier=earlier):
            if input_signature(channel) != sig:
                said.append("input")
                return None
            out = judge(channel, request, rec, earlier, word, asked, project)
            said.append(out)
            if out.state not in CARRIED:
                return None
            chans = list(threads.stated_set({"channels": threads.held_set(rec)}))
            if out.state == "applied" and out.why != "unchanged":
                chans = chans + [cid] if request["op"] == "add" else [c for c in chans if c != cid]
            made.append({"project": project, "session": rec["current"], "channels": chans,
                         "answer": {"channel": cid, "id": request["id"], "ts": request["ts"], "result": out.state,
                                    "reason": out.why if out.state == "refused" else ""}})
            if word is not None and isinstance(asked, dict):
                made[-1]["reach"] = asked.get("reach")   # checked again last, after the positions (_last_reads)
            return made[-1]
        made = []
        try:
            entry = threads.set_channels(tid, decide, lock_until=lock_until, wake_until=wake_until)
        except sminos.WakeBusy:
            return Outcome("pending", "wake")
        except sminos.PositionsUnread as e:
            sminos.daemon_log("channel %s: a request for %s waits: %s" % (channel.name, tid[:8], e))
            return Outcome("pending", "unreadable")
        except sminos.LockBusy:
            return Outcome("pending", "busy")
        if entry is not None:
            try:
                # The entry this call committed, and no other: one committed since in its place (another process
                # finished this statement, then began a hand-off) is its own replay's, whose carry no deadline bounds.
                sminos.finish_thread(tid, project=project, lock_until=lock_until, only=entry["id"])
            except (sminos.LockBusy, sminos.LogWriteFailed, OSError) as e:
                sminos.warn("the statement of %s's channels is left to the next reconciliation: %s"
                            % (tid[:8], e or "its lock is busy"))
            sminos.nudge_daemon()
            return said[-1]
        if not said:   # decide was not asked: an entry opened since, or the record ended
            why = "entry"
            continue
        if said[-1] == "input":
            why = "moved"
            continue
        if said[-1].state not in CARRIED:
            return said[-1]
        # The Change was refused by set_channels' last reads: what judge() would have said of it a moment earlier.
        unwritten = made[-1].get("unwritten") if made else None
        if unwritten in ("moved", "lane-b"):
            return Outcome("ignored", "not-here")   # row 3: the session is no thread's of this machine's now
        if unwritten == "reach":
            return Outcome("pending", "moved")      # row 13: the word was for a reach the thread no longer has
        if unwritten == "record-unreadable":
            return Outcome("pending", unwritten)    # its lane not known: carried out once the record reads again
        # `between`: the session is no member of `project` now.
        sminos.forget_caches()
        again = sminos.last_project(record["current"])
        if getattr(again, "id", None) == getattr(project, "id", None):
            return Outcome("pending", "between")
        why = "between"
    return Outcome("pending", why)


def ask_of(channel, request):
    """What the endpoint is asked about a request a pass left pending
    `endpoint` (§6, M7), read now: {"key": its event_key, "thread",
    "session": the thread's current session, "project": the thread's own
    project, "reach": reach_token(session)}, the session and reach being
    what the word is bound to (judge's row 13). None when §6's row 3 or 7
    holds (it names no thread here; the thread holds no session, or its
    session is a member of no project), when the session's record cannot be
    read (no reach to bind a word to), and for a request that has no
    position in the log yet (one of this machine's queued appends: it is
    asked about once it is there, behind its upload)."""
    if request.get("seq") is None:
        return None
    facts = _Facts()
    record = sminos.threads_module().get(request["thread"])
    if not _names_here(record, request, facts) or not record["current"]:
        return None
    session = record["current"]
    project = sminos.last_project(session)
    if not _member_of(project, session):
        return None
    reach = reach_token(session)
    if reach is None:
        return None
    return {"key": event_key(channel, request), "thread": record["thread"], "session": session,
            "project": project, "reach": reach}


_UNREAD_SAID = {}   # channel id → the last unreadable input said in daemon.log, said once while it stays


def carry_due(channel, words=None, also=(), lock_until=None, wake_until=None, finishes=True):
    """The pass (§6): every request of the ordered input that is not expired
    and names a thread of this machine that has not ended, in order, then
    the requests of `also` it does not hold (a command's own, in hand), each
    through carry_out; a request its thread's record has answered already
    is passed by (judge's row 4, read from the record without a lock: it
    writes nothing either way), and a request pending leaves the later ones
    for its thread pending `earlier`. `words`: {event_key: (word, asked)};
    `finishes`, carry_out's.
    [(request, Outcome)] of the requests carried."""
    threads = sminos.threads_module()
    words = words or {}
    try:
        _, requests = requests_of(channel)
    except sminos.PositionsUnread as e:
        # Nothing of the channel is carried while a file of its input cannot be read; a command's own is told why.
        if _UNREAD_SAID.get(channel.id) != str(e):
            sminos.daemon_log(str(e))
        _UNREAD_SAID[channel.id] = str(e)
        return [(r, Outcome("pending", "unreadable")) for r in also]
    _UNREAD_SAID.pop(channel.id, None)
    have = {(r["writer"], r["id"]) for r in requests}
    own = {(r.get("writer"), r.get("id")) for r in also}
    todo = requests + [r for r in also if (r.get("writer"), r.get("id")) not in have]
    records, waiting, out = {}, set(), []
    for r in todo:
        if r["thread"] not in records:
            records[r["thread"]] = threads.get(r["thread"])
        record = records[r["thread"]]
        mine = (r["writer"], r["id"]) in own
        if not mine and (record is None or threads.record_ended(record) or expired(r)
                         or (channel.id, r["id"]) in _answered(record)):
            continue
        if r["thread"] in waiting:
            out.append((r, Outcome("pending", "earlier")))
            continue
        word, asked = words.get(event_key(channel, r), (None, None))
        got = carry_out(channel, r, word, asked, lock_until=lock_until, wake_until=wake_until, finishes=finishes)
        if got.state in CARRIED:
            records[r["thread"]] = threads.get(r["thread"])
        elif got.state == "pending":
            waiting.add(r["thread"])
        out.append((r, got))
    return out


# ------------------------------------------------------------ the verbs: create, add, remove (§8)


class Target(NamedTuple):
    """A thread a verb names, as this machine reads it."""
    label: str           # <alias>#<short>
    thread: str          # its thread id ("" for none)
    session: str         # its current session as this machine reads it
    alias: str
    local: bool          # a thread of this machine
    machine: str         # the machine it runs on
    channels: tuple      # its set where this machine can see it: its record's, or its row's
    refusal: str         # why it is refused before anything is written; "" for none


def _label(alias, session):
    return "%s#%s" % (alias, session[:8]) if alias and session else alias or session[:8] or "?"


def _alias_of(session):
    """The session's alias as its project's view lists it, else its short."""
    project = sminos.last_project(session)
    if project is not None:
        for m in sminos.view_of(project).members:
            if m.session == session:
                return m.alias
    return session[:8]


def _local(record, session, alias):
    """A thread of this machine, from its record: refused when there is none
    (no thread, or its session is lane B), when it has ended, or when it
    holds no session."""
    threads, records = sminos.threads_module(), sminos.records_module()
    if record is None:
        return Target(_label(alias, session), "", session, alias, True, sminos.host_name(), (), "it is no thread")
    current = record["current"]
    label = _label(alias or record.get("alias") or "", current or session)
    if threads.record_ended(record):
        return Target(label, record["thread"], current, alias, True, sminos.host_name(), (), "it has ended")
    if not current:
        return Target(label, record["thread"], "", alias, True, sminos.host_name(), (), "it holds no session")
    if records.lane_of(records.read(current)) == "B":
        return Target(label, record["thread"], current, alias, True, sminos.host_name(), (),
                      "it is no thread (its session is lane B)")
    return Target(label, record["thread"], current, alias or record.get("alias") or _alias_of(current), True,
                  sminos.host_name(), tuple(threads.held_set(record)), "")


def _target(q):
    """The thread `q` names (sminos.find_target: exit 4 for a name that is
    unknown or ambiguous)."""
    threads = sminos.threads_module()
    found = sminos.find_target(q)
    if found[0] == "none":
        sminos.die("no seat or member matching '%s'" % q, sminos.EXIT_UNKNOWN)
    if found[0] == "seat":
        # A full id resolves as a seat even where it is an older copy's seat over a session its human opened: the
        # thread named is the session's canonical record (current_record), the seat's own only where none is.
        s = found[1]
        session = found[2] or s["current"]
        record = threads.current_record(session, fresh=True) if session else None
        return _local(record if record is not None else threads.get(s["seat_id"]), session, s["alias"])
    m = found[2]
    if m.local:
        record = threads.current_record(m.session, fresh=True)
        if record is None:
            t = threads.thread_of(m.session)
            record = t if t is not None and t["current"] == m.session and threads.record_ended(t) else None
        return _local(record, m.session, m.alias)
    label = _label(m.alias, m.session)
    refusal = "it is no thread" if not m.thread else "it has ended" if m.end else ""
    return Target(label, m.thread, m.session, m.alias, False, m.machine, tuple(m.channels), refusal)


def _caller(session):
    """The calling session's own thread, or exit 1 when it is none here."""
    record = sminos.threads_module().current_record(session, fresh=True)
    t = _local(record, session, "")
    if t.refusal:
        sminos.die("this session (%s) cannot be placed in a channel: %s" % (session[:8], t.refusal), 1)
    return t


def _placed(op, channel, outcome):
    """What a target's line says of an applied or a pending change."""
    if outcome.state == "applied":
        if outcome.why == "unchanged":
            return ("already in %s" if op == "add" else "was not in %s") % channel.name
        return ("in %s" if op == "add" else "out of %s") % channel.name
    if outcome.state == "refused":
        return "refused: %s" % WORDS[outcome.why]
    return "pending: %s" % WORDS.get(outcome.why, outcome.why)


def _answer_of_record(thread_id, channel_id, request_id):
    """The statement that answers a request for this machine's thread: in
    its record's open entry, else among its sessions' own events in the
    projects known here. None when neither can be read."""
    threads = sminos.threads_module()
    record = threads.get(thread_id)
    if record is None:
        return None

    def answers(e):
        a = e.get("answers") if isinstance(e, dict) else None
        return e.get("kind") == "channels" and isinstance(a, dict) and a.get("channel") == channel_id \
            and a.get("id") == request_id and e.get("result") in CARRIED
    for e in ((record.get("pending") or {}).get("events") or []):
        if answers(e):
            return e
    sessions = [x for x in dict.fromkeys(record["sessions"] + [record["current"]]) if x]
    for project in sminos.known_projects():
        for session in sessions:
            for e in sminos._own_events(project, session):
                if answers(e) and e.get("thread") == thread_id:
                    return e
    return None


def _answered_line(op, channel, target, request):
    """A request this command wrote that its thread's machine answered first
    (the daemon's pass, between the append and the command's own): what
    the statement answering it says, read from the thread's open entry or
    its sessions' own events; when neither can be read, that it was
    answered, and the thread's membership now as such, not as the verdict.
    (line, the outcome recorded: applied or refused with its reason from
    the statement, `ignored answered` when none could be read)."""
    answer = _answer_of_record(target.thread, channel.id, request["id"])
    if answer is not None:
        if answer["result"] == "refused":
            reason = answer.get("reason")
            return "refused: %s" % WORDS.get(reason, reason), Outcome("refused", reason)
        return ("in %s" if op == "add" else "out of %s") % channel.name, Outcome("applied")
    threads = sminos.threads_module()
    held = channel.id in threads.held_set(threads.get(target.thread))
    return ("answered already by its machine; it is %s %s now" % ("in" if held else "not in", channel.name),
            Outcome("ignored", "answered"))


def _choice(channel, session, target):
    """The stream a request of `session`'s for `target` goes under in the
    channel's log (sminos.stream_choice for that one recipient): (choice,
    None), or (None, why it is refused). Local: it writes nothing, so it
    can be asked of a channel not registered yet."""
    choice, refusal = sminos.stream_choice(channel, session, [{"session": target.session, "alias": target.alias}],
                                           "the request for %s" % target.label)
    return (None, refusal[0]) if refusal else (choice, None)


def place(channel, op, targets, session, choices=None):
    """Each target added to or removed from the channel (§8): the caller's
    own thread by a statement alone (change), any other by a request
    written into the channel's log under the caller's writer there (the
    stream sminos.stream_choice gives for that one recipient; the
    machine's human writer from a terminal) and, for a thread of this
    machine, carried out at once from the request in hand (carry_due, which
    carries the channel's other due requests too). [(target, outcome or
    None, line)] in the targets' order, a target named twice once, and
    whether any was refused or could not be recorded. `choices`: {thread:
    (stream choice, None)} made for a target before (create's, against the
    channel before it was registered): the choice is made again at the
    append, and one that refuses or differs writes nothing for it."""
    threads = sminos.threads_module()
    me = threads.current_record(session, fresh=True) if session else None
    rows, seen, written, bad, wrote = [], set(), [], False, False
    for t in targets:
        if t.thread and t.thread in seen:
            continue
        seen.add(t.thread)
        if t.refusal:
            rows.append([t, None, "refused: %s: nothing was written" % t.refusal])
            bad = True
            continue
        if op == "add" and channel.id not in t.channels and len(t.channels) >= threads.CHANNEL_LIMIT:
            rows.append([t, None, LIMIT_REFUSAL % t.label])
            bad = True
            continue
        if me is not None and t.thread == me["thread"]:
            got = change(t.thread, channel, op, session)
            if got.state == "failed":
                rows.append([t, got, "nothing was recorded (%s): run the command again" % OWN_FAILED[got.why]])
                bad = True
            elif got.state == "refused":
                rows.append([t, got, LIMIT_REFUSAL % t.label])
                bad = True
            else:
                rows.append([t, got, _placed(op, channel, got)])
            continue
        choice, refusal = _choice(channel, session, t)   # at the append, for this one recipient, always
        before = (choices or {}).get(t.thread)
        if before is not None and (refusal or choice[0][:2] != before[0][0][:2]):   # (writer, audience)
            # create's first member, whose reach changed while the channel was registered: nothing is written for
            # it under the stream chosen before (its ids would leave under an audience it no longer has), nor under
            # another one the preflight did not see. The channel stays registered with no member (§8).
            rows.append([t, None, "nothing was recorded (its reach changed as the channel was made): %s stays "
                                  "registered with no member, and the same command run again brings it back"
                                  % channel.name])
            bad = True
            continue
        if refusal:
            rows.append([t, None, "refused: not reachable: %s" % refusal])
            bad = True
            continue
        writer, audience, _, _ = choice[0]
        try:
            sminos.keep_stream(channel, writer, audience)
            e = sminos.log_append(channel, writer, "channel-request", op=op, session=t.session, thread=t.thread,
                                  id=uuid.uuid4().hex)
        except (OSError, sminos.audience_module().StreamUnknown) as err:
            # This target's outcome alone: the requests already written are still reported and carried out.
            rows.append([t, None, "the request could not be written in %s's log: %s" % (channel.name, err)])
            bad = True
            continue
        wrote = True
        if t.local:
            written.append(e)
            rows.append([t, e, ""])
        else:
            rows.append([t, None, "asked; pending on %s: its machine carries it out when its daemon reads the "
                                  "request" % t.machine])
    if wrote:
        sminos.nudge_daemon()   # the uplink sends what was written within a scan
    if written:
        got = {(r["writer"], r["id"]): o for r, o in carry_due(channel, also=written)}
        for row in rows:
            if isinstance(row[1], dict):
                e = row[1]
                o = got.get((e["writer"], e["id"]), Outcome("pending", "earlier"))
                row[1] = o
                if o.state == "ignored" and o.why == "answered":
                    row[2], row[1] = _answered_line(op, channel, row[0], e)
                    bad = bad or row[1].state == "refused"
                elif o.state == "ignored":
                    row[2] = WORDS[o.why]
                    bad = True
                else:
                    row[2] = _placed(op, channel, o)
                    bad = bad or o.state == "refused"
    return [tuple(r) for r in rows], bad


def mint_channel_id():
    """A new channel's id: a UUID of version 8 (MAWS's isChannelId), minted
    again while this machine knows one of it."""
    while True:
        u = uuid.uuid4().int
        cid = str(uuid.UUID(int=(u & ~(0xF << 76)) | (0x8 << 76)))
        if sminos.is_channel_id(cid) and not os.path.exists(os.path.join(sminos.projects_root(), cid)):
            return cid


def _memberless(channel):
    """Whether a channel registered here has no member as this machine can
    tell: no record of this machine that has not ended names it, and the
    org's directory it keeps does not list it (MAWS lists a channel while
    some machine holds a member of it)."""
    listed = {p.get("id") for p in ((sminos.org_directory() or {}).get("projects") or [])}
    return channel.id not in held_channels() and channel.id not in listed


def _refuse_uncarried(channel, doing):
    """A channel write refused, before anything is written, where this
    machine's enrollment does not carry the channel's log (sminos.not_carried,
    the test the uplink makes of every log it opens: a registration of no
    hub or of another enrollment's, one the org's directory retired, or no
    enrollment at all): the write would say success for facts that never
    leave this machine (the frontier's second review, C3). A channel that
    left this machine (has_left: memberless, and unlisted for the counted
    period) is not refused: a member placed in it is what brings it back
    (Leaving). Nor is a thread's remove of itself: leaving is always
    possible."""
    enrolled = sminos.enrollment()
    why = sminos.not_carried(channel, enrolled["org"]) if enrolled is not None else sminos.NOT_ENROLLED
    if why and why != sminos.LEFT_HERE:
        sminos.die("cannot %s %s: this machine's enrollment does not carry its log (%s): nothing was written"
                   % (doing, channel.name, why), 1)


def _print_rows(rows):
    for t, _, line in rows:
        print("%s: %s" % (t.label, line))


def cmd_channel(a):
    """`sminos channel create|add|remove|show|env` (§8): every verb that
    writes refused before anything is written where the kept welcome lists
    no `channels`; `show` is a read, and needs none."""
    if a.channel_op == "show":
        show(find_channel(a.channel), a.json)
        return
    if not sminos.audience_module().advertised("channels"):
        sminos.die(CAPABILITY_REFUSAL, 1)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if a.channel_op == "create":
        sys.exit(_create(a.name, a.thread, session))
    if a.channel_op == "env":
        channel = find_channel(a.channel)
        _refuse_uncarried(channel, "change the pool of")
        sys.exit(env(channel, a.env_op, a.machine, session))
    channel = find_channel(a.channel)
    if a.channel_op == "add":
        _refuse_uncarried(channel, "add to")
    if not a.threads and not session:
        sminos.die("from a terminal, sminos channel %s names the threads it places: sminos channel %s %s "
                   "<thread>..." % (a.channel_op, a.channel_op, a.channel), 1)
    targets = [_target(q) for q in a.threads] if a.threads else [_caller(session)]
    rows, bad = place(channel, a.channel_op, targets, session)
    _print_rows(rows)
    sys.exit(1 if bad else 0)


def _create(name, thread, session):
    """`channel create <name> [<thread>]`: the capability (checked by the
    caller), the name, the first member and the limit checked before
    anything is registered; a name a log known here answers to refused, but
    a channel of that name registered here with no member, which is brought
    back under its id; else a new id registered, and the first member
    placed as `add` places one. The exit code."""
    if not sminos.valid_name(name) or sminos.UUID_RE.fullmatch(name):
        sminos.die("'%s' is no channel name: up to 64 letters, digits, '.', '_' or '-', and not an id: nothing was "
                   "written" % name, 1)
    if session and thread:
        sminos.die("from a session, channel create makes the session its first member: create it, then sminos "
                   "channel add %s %s: nothing was written" % (name, thread), 1)
    if not session and not thread:
        sminos.die("from a terminal, channel create names the thread of this machine that is its first member: "
                   "sminos channel create %s <thread>: nothing was written" % name, 1)
    first = _target(thread) if thread else _caller(session)
    if first.refusal:
        sminos.die("%s: refused: %s: nothing was written" % (first.label, first.refusal), 1)
    if not first.local:
        sminos.die("cannot create %s with %s: it runs on %s, and a channel's first member is a thread of this "
                   "machine: nothing was written" % (name, first.label, first.machine), 1)
    if len(first.channels) >= sminos.threads_module().CHANNEL_LIMIT:
        sminos.die(LIMIT_REFUSAL % first.label, 1)
    named = [p for p in sminos.known_logs() if p.name == name]
    back, cid = None, None
    if named:
        if len(named) == 1 and sminos.is_channel_id(named[0].id) and _memberless(named[0]):
            back = named[0]
        else:
            sminos.die("cannot create channel %s: %s already answers to that name — name it otherwise: nothing was "
                       "written" % (name, ", ".join(sorted(map(sminos.log_label, named)))), 1)
    if back is None:
        enrolled = sminos.enrollment()
        if enrolled is None:
            sminos.die("cannot create channel %s: this machine is not enrolled at a desk hub: a channel's log syncs "
                       "through one" % name, 1)
        cid = mint_channel_id()
        candidate = sminos.make_project(cid, name, "", "", {"url": enrolled["url"], "org": enrolled["org"]})
    else:
        _refuse_uncarried(back, "bring back")
        candidate = back
    me = sminos.threads_module().current_record(session, fresh=True) if session else None
    choices = None
    if me is None or me["thread"] != first.thread:
        # The first member is placed by a request: its stream is chosen against the channel about to be made, the
        # last thing before the registration, so a target already unreachable (a private thread whose audience is
        # not known yet) leaves nothing registered or written. place chooses again at the append, and writes
        # nothing if that choice refuses or differs (its reach changed while the channel was registered).
        choice, refusal = _choice(candidate, session, first)
        if refusal:
            sminos.die("%s: refused: not reachable: %s: nothing was written" % (first.label, refusal), 1)
        choices = {first.thread: (choice, None)}
    if back is None:
        try:
            channel = register(cid, name)
        except ValueError as e:
            sminos.die("cannot create channel %s: %s" % (name, e), 1)
    else:
        channel = back
    rows, bad = place(channel, "add", [first], session, choices)
    t, outcome, line = rows[0]
    done = isinstance(outcome, Outcome) and outcome.state == "applied"
    if back is None:
        print("created channel %s (%s)%s" % (channel.name, channel.id, " with %s" % t.label if done else ""))
    else:
        print("%s exists and has no member%s" % (channel.name, ": %s is in it again" % t.label if done else ""))
    if not done:
        print("%s: %s" % (t.label, line))
    return 1 if bad else 0


# ------------------------------------------------------------ the roster, what became of a request, the pool (§5, §8)

_SWEPT = {}   # "views": the views the last sweep read, with the projects; "value": what it made of them


def _sweep():
    """One sweep over view_of(p) for p in sminos.known_projects(): the
    roster of every channel, every thread's sessions as its rows list them,
    and each session's row. A session whose rows stand in two projects' views
    (a move seen across two logs, one imported ahead of the other) is the
    row of the project its newest membership in effect names (_where_now,
    last_project's rule), so one thread is one row of a roster and counts
    once in a pool. Kept while every view it read is the one view_of answers
    (a view is dropped by forget_caches, a lifecycle append and an import,
    and the sweep with it), so a second read in one invocation reads no log
    again. Never called from view_of, _reconcile, the plane or the uplink
    (C1)."""
    projects = sminos.known_projects()
    views = [(p, sminos.view_of(p)) for p in projects]
    held = _SWEPT.get("views")
    if held is not None and len(held) == len(views) and all(
            p.id == q.id and v is w for (p, v), (q, w) in zip(held, views)):
        return _SWEPT["value"]
    seen = {}
    for p, v in views:
        for m in v.members:
            if m.session:
                seen.setdefault(m.session, []).append(p.id)
    where = {sid: _where_now(sid, views) for sid, pids in seen.items() if len(set(pids)) > 1}
    kept, had = [], {}
    for p, v in views:
        for m in v.members:
            if m.thread:
                had.setdefault(m.thread, set()).update((m.session,) + tuple(m.former) + tuple(m.thread_sessions))
            if m.session in where and where[m.session] != p.id:
                continue
            kept.append((p, v, m))
    # One row a stamped thread across the views: a refill displaces a session in one project and joins its
    # replacement in another, and the two halves can be imported in either order.
    by_thread = {}
    for p, v, m in kept:
        if m.thread:
            by_thread.setdefault(m.thread, []).append((p, v, m))
    current = {tid: _newest_row(found) for tid, found in by_thread.items() if len(found) > 1}
    rosters_, rows = {}, {}
    for p, v, m in kept:
        if m.thread in current and current[m.thread] != (p.id, m.session):
            continue
        if m.session:
            rows.setdefault(m.session, (p, m))
        if sminos.has_ended(m):
            continue
        for c in m.channels:
            rosters_.setdefault(c, []).append((p, m))
    value = {"rosters": rosters_, "had": had, "rows": rows, "views": views, "ended": None}
    _SWEPT["views"], _SWEPT["value"] = views, value
    return value


def _where_now(session, views):
    """The project id a session is in now, by its membership in effect in
    each view's log (last_project's rule): the newest decides, a `retired`
    `moved` naming its destination; the newest of one moment naming two
    projects decide none (None)."""
    at, newest = "", set()
    for p, v in views:
        last = (v.info.get(session) or {}).get("latest")
        if not last:
            continue
        ts = str(last.get("ts") or "")
        if ts < at:
            continue
        if ts > at:
            at, newest = ts, set()
        newest.add(str(last.get("project") or "") if last["kind"] == "retired" and last.get("reason") == "moved"
                   else p.id)
    return next(iter(newest)) if len(newest) == 1 else None


def _in_effect_at(v, session):
    """The timestamp of the session's membership event in effect in a view's log ("" for none)."""
    return str(((v.info.get(session) or {}).get("latest") or {}).get("ts") or "")


def _newest_row(found):
    """(project id, session) of the row, among one thread's rows in several views, whose membership in
    effect is the newest; None when the newest of one moment are two (neither is kept, as _where_now)."""
    at = max(_in_effect_at(v, m.session) for _, v, m in found)
    newest = [(p.id, m.session) for p, v, m in found if _in_effect_at(v, m.session) == at]
    return newest[0] if len(newest) == 1 else None


def _ended_row(thread_id, session):
    """(Project, Member) of a thread's ended row in a view here (View.ended:
    a row the log shows unlisted to this reader is none of them), by its
    thread, else by the session, the one whose end is the latest; None for
    none. Read only where no member row is there, and never put back in a
    roster."""
    swept = _sweep()
    if swept["ended"] is None:
        swept["ended"] = [(p, m, _in_effect_at(v, m.session)) for p, v in swept["views"] for m in v.ended]
    found = [x for x in swept["ended"] if thread_id and x[1].thread == thread_id] \
        or [x for x in swept["ended"] if x[1].session == session]
    if not found:
        return None
    p, m, _ = max(found, key=lambda x: x[2])   # the latest visible end, across every project's view
    return p, m


def rosters():
    """{channel id: [(Project, Member), ...]} (§5): every member row of every
    project known here whose `channels` (what its log states) holds the id
    and that has not ended, with the project whose view it is in. A row is
    the member's row in its own project's view, with every rule that builds
    it: a thread this reader may not read is absent, a stopped one there."""
    return _sweep()["rosters"]


def roster(channel):
    """rosters()'s rows for the channel (an id, or its Project), by alias,
    then short id."""
    cid = getattr(channel, "id", channel)
    return sorted(rosters().get(cid, []), key=lambda pm: (pm[1].alias, pm[1].short))


def _sessions_had(thread_id):
    """The sessions the thread has had as this reader can tell from its rows:
    each row's current session, those it continues, its thread's others."""
    return _sweep()["had"].get(thread_id, set())


def _answers_a_request(e):
    """A statement (sminos_threads.is_statement) that carries a well-formed
    answer (§2): `answers` {channel: a channel's id, id: a string}, `result`
    applied, or refused with a `reason` of REASONS. A refusal with no
    reason, or one of another value or type, answers nothing."""
    a = e.get("answers")
    return e.get("kind") == "channels" and sminos.threads_module().is_statement(e) and isinstance(a, dict) \
        and sminos.is_channel_id(a.get("channel")) and isinstance(a.get("id"), str) and a["id"] \
        and (e.get("result") == "applied" or (e.get("result") == "refused" and isinstance(e.get("reason"), str)
                                              and e["reason"] in REASONS))


def _answering(events):
    """One log's ([answering statements], {session: the thread stamps of its own joined events}), in the
    merged read's order: what answer_of reads of a log, kept beside it (sminos.log_memo)."""
    said, stamps = [], {}
    for e in events:
        kind = e.get("kind")
        if kind == "channels" and _answers_a_request(e):
            said.append(e)
        elif kind == "joined":
            sid, stamp = e.get("session"), e.get("thread")
            if isinstance(sid, str) and isinstance(stamp, str) and stamp \
                    and sminos.writer_session(e["writer"]) == sid:
                stamps.setdefault(sid, set()).add(stamp)
    return said, stamps


def _answer_index():
    """{(channel id, request id): [(statement, its log's joined stamps), ...]} over every project's log
    known here, each log in its merged order."""
    out = {}
    for p in sminos.known_projects():
        _, events = sminos._store_whole(p, "log", shared=True)
        said, stamps = sminos.log_memo(events, "channel-answers", _answering)
        for e in said:
            out.setdefault((e["answers"]["channel"], e["answers"]["id"]), []).append((e, stamps))
    return out


def answers():
    """{(channel id, request id): [statement, ...]} (§5): every `channels`
    event that carries a well-formed `answers`, in every project's log this
    machine reads (sminos.known_projects), in the merged read's order,
    whatever statement is in effect there now. Read from an index of its
    own, never from the fold that reads membership."""
    return {k: [e for e, _ in v] for k, v in _answer_index().items()}


def answer_of(channel, request):
    """The answer to a request of the channel's log (§5): the first statement
    of answers() for its channel and id whose `thread` stamp is the
    request's `thread` and whose writer's session is one that thread has
    had, as this reader can tell: a session its rows list (its current one,
    those it continues, its thread's others), or one whose own `joined` in
    the log the statement lies in is stamped with that thread, a project the
    thread has since left included. None for none: the stamp alone is a
    field any writer can set."""
    return _answer_in(_answer_index(), channel, request)


def _answer_in(index, channel, request):
    cid, tid = getattr(channel, "id", channel), request.get("thread")
    had = None
    for e, stamps in index.get((cid, request.get("id")), []):
        if e.get("thread") != tid:
            continue
        session = sminos.writer_session(e["writer"])
        if tid in stamps.get(session, ()):
            return e
        had = _sessions_had(tid) if had is None else had
        if session in had:
            return e
    return None


def _row_of(thread_id, session):
    """(Project, Member) of a thread's row in any project's view here, by its
    thread, else by the session; None for none."""
    swept = _sweep()
    for p, m in swept["rows"].values():
        if thread_id and m.thread == thread_id:
            return p, m
    return swept["rows"].get(session)


def _stamp(ts):
    """A request's time as shown: its stamp to the second."""
    return str(ts or "?")[:19]


def _requester(writer):
    """Who wrote a request, as `channel show` names it: a session's row's
    `alias#short`, else its short and machine; the human writer as the person
    at that machine."""
    base = sminos.writer_base(str(writer or ""))
    machine, _, tail = base.rpartition("/")
    if tail == "human":
        return "the person at %s" % (machine or "?")
    row = _row_of("", tail)
    return _label(row[1].alias, row[1].session) if row else "%s@%s" % (tail[:8], machine or "?")


def requests_shown(channel, now=None):
    """The channel's requests as `channel show` prints them (§8): those of
    the ordered input (requests_of) that have not expired, oldest first,
    each with what became of it: `duplicate` (an earlier request of another
    writer used its id: §6's row 2), else `applied` or `refused` with its
    reason from the statement that answers it (answer_of), else `withheld`
    (`not-reachable`) for one of this machine's writers at a position the
    hub withheld (sminos_hublog.withheld_of: its uplink's own record, read
    with no lock; M7), else `pending` with the machine its target's row
    was last seen on."""
    _, reqs = requests_of(channel, whole=False)
    index, out = _answer_index(), []
    settled = _settled_own(channel)
    for i, r in enumerate(reqs):
        if expired(r, now):
            continue
        # A target that has ended keeps the machine its last visible row was seen on (an ended row, which no
        # roster holds; one the log shows unlisted to this reader is none).
        row = _row_of(r["thread"], r["session"]) or _ended_row(r["thread"], r["session"])
        state, reason, machine = "pending", None, None
        if _duplicate(r, reqs[:i]):
            state = "duplicate"
        else:
            answer = _answer_in(index, channel, r)
            if answer is not None:
                state = answer["result"]
                reason = answer.get("reason") if state == "refused" else None
            elif r.get("seq") in settled.get(r["writer"], {}):
                # The hub withheld it, or the endpoint refused its stream's audience: its target never read it.
                state, reason = "withheld", settled[r["writer"]][r["seq"]]
            else:
                local = sminos.threads_module().get(r["thread"])
                machine = row[1].machine if row else sminos.host_name() if local is not None else None
        target = _label(row[1].alias, r["session"]) if row else r["session"][:8]
        out.append({"id": r["id"], "op": r["op"], "thread": r["thread"], "session": r["session"], "target": target,
                    "by": _requester(r["writer"]), "ts": r.get("ts"), "state": state, "reason": reason,
                    "machine": machine})
    return out


def outstanding(channel, heard=None, now=None):
    """Whether the channel holds a request this machine appended itself
    (appended_here: its receipt or its own queue, a former name's
    included, never the name it went under) that is still outstanding:
    its lifetime not out, its id no other writer's first (§6's row 2), not
    withheld or refused by the upstream (_settled_own), and not answered.
    The answer is looked up where it is held, never by reading every log:
    for a thread of this machine its record (`answered`, or the record
    ended); for one of another machine `heard`, {(channel id, request id):
    thread} of the answering statements this machine's uplink imported
    (sminos_uplink.Link.hear_answers), so until one is heard such a
    request is outstanding until its lifetime is out. What keeps the
    channel's log open here while no thread of this machine is in it
    (sminos_uplink's leaving rule), so the ask pass can carry it; a file
    of it that cannot be read or listed keeps it too."""
    try:
        _, reqs = requests_of(channel)
    except sminos.PositionsUnread:
        return True
    threads, heard, settled = sminos.threads_module(), heard or {}, None
    for i, r in enumerate(reqs):
        if expired(r, now) or _duplicate(r, reqs[:i]) or not appended_here(channel, r):
            continue
        settled = _settled_own(channel) if settled is None else settled
        if r.get("seq") in settled.get(r["writer"], {}):
            continue
        record = threads.get(r["thread"])
        if record is not None:
            if threads.record_ended(record) or (channel.id, r["id"]) in _answered(record):
                continue
            return True
        if heard.get((channel.id, r["id"])) != r["thread"]:
            return True
    return False


def answers_in(project, events):
    """{(channel id, request id): thread} of the statements among `events`,
    stored in `project`'s log just now, that answer a request
    (_answers_a_request) by answer_of's rule of their writer: its session's
    own `joined` in that log is stamped with the statement's thread (the
    log's merged read, kept beside it: _answering). What the uplink keeps
    of what it imports, for outstanding; the rows' sessions are not read
    (the roster is every project's)."""
    said = [e for e in events if _answers_a_request(e) and isinstance(e.get("thread"), str)]
    if not said:
        return {}
    _, merged = sminos._store_whole(project, "log", shared=True)
    stamps = sminos.log_memo(merged, "channel-answers", _answering)[1]
    return {(e["answers"]["channel"], e["answers"]["id"]): e["thread"] for e in said
            if e["thread"] in stamps.get(sminos.writer_session(e["writer"]), ())}


def _settled_own(channel):
    """{writer: {seq: reason}} of this machine's writers' positions in the
    channel's log that the upstream did not carry and never will, as its
    uplink keeps them (uplink.json, read with no lock): `not-reachable` where
    the hub withheld one (sminos_hublog.withheld_of), `audience` where the
    endpoint refused its stream's audience (sminos_hublog.refused_audience_of:
    the stream chosen for the target was stale when it was signed)."""
    hublog = sminos.sibling_module("sminos_hublog")
    out = {}
    for reason, held in (("audience", hublog.refused_audience_of(channel)), ("not-reachable",
                                                                          hublog.withheld_of(channel))):
        for w, seqs in held.items():
            out.setdefault(w, {}).update(dict.fromkeys(seqs, reason))
    return out


def _request_line(r):
    if r["state"] == "applied":
        what = "applied"
    elif r["state"] == "refused":
        what = "refused: %s" % WORDS.get(r["reason"], r["reason"] or "?")
    elif r["state"] == "withheld":
        what = "refused: " + WORDS["audience"] if r["reason"] == "audience" else \
            "refused: not reachable (the hub withheld it)"
    elif r["state"] == "duplicate":
        what = WORDS["duplicate"]
    elif r["machine"]:
        what = "pending on %s since %s" % (r["machine"], _stamp(r["ts"]))
    else:
        what = "pending since %s (the machine of its thread is not known here)" % _stamp(r["ts"])
    return [_stamp(r["ts"]), r["op"], r["target"], "by " + r["by"], what]


def is_env(e):
    """Whether an event is a `channel-env` of §2's shape: `op` add or remove,
    a `machine` and a `thread`, each a string that is not empty."""
    return isinstance(e, dict) and e.get("kind") == "channel-env" and e.get("op") in ("add", "remove") \
        and all(isinstance(e.get(k), str) and e[k] for k in ("machine", "thread", "writer"))


def _by_hand(channel, rows):
    """{machine, lower-cased: (its name, held)}: the last honoured `channel-env`
    of each machine, by merge order. An event is honoured when the roster as
    read holds a row of its `thread` that lists the writer's session among
    the sessions it has had; an association this reader cannot make is not
    honoured. (The queue of appends waiting for their writer's head holds
    the operator's alone, and `env` writes under a session's own stream.)"""
    _, events = sminos._store_whole(channel, "log", shared=True)
    held = {}
    for e in events:
        if not is_env(e):
            continue
        session = sminos.writer_session(e["writer"])
        if not any(m.thread == e["thread"] and session in (m.session,) + tuple(m.former) + tuple(m.thread_sessions)
                   for _, m in rows):
            continue
        held[e["machine"].lower()] = (e["machine"], e["op"] == "add")
    return held


def pool(channel, rows=None):
    """The channel's pool (§8): one entry a machine, by name: `live` its
    roster rows there in a state of FILLED, `stopped` those stopped or gone,
    and `by_hand` whether a `channel-env` holds it in. A machine is in the
    pool when a row of the roster is there or a member added it by hand."""
    rows = roster(channel) if rows is None else rows
    counts = {}
    for _, m in rows:
        c = counts.setdefault(m.machine.lower(), [m.machine, 0, 0])
        if m.state in sminos.FILLED:
            c[1] += 1
        elif m.state in ("stopped", "gone"):
            c[2] += 1
    hand = _by_hand(channel, rows)
    for key, (name, on) in hand.items():
        if on:
            counts.setdefault(key, [name, 0, 0])
    return [{"machine": name, "live": live, "stopped": stopped, "by_hand": hand.get(key, ("", False))[1]}
            for key, (name, live, stopped) in sorted(counts.items())]


def _pool_line(e):
    return ["%s  %d live, %d stopped%s" % (e["machine"], e["live"], e["stopped"],
                                            ", added by hand" if e["by_hand"] else "")]


def section(rows):
    """A channel's rows as `list` and `channel show` print them: one row each
    with its project's column (sminos.row_cells), none folded; `(none)` for
    none."""
    if rows:
        sminos.print_rows([sminos.row_cells(m, p) for p, m in rows])
    else:
        print("  (none)")


def show(channel, as_json=False):
    """`channel show <channel> [--json]` (§8): its heading, its members (the
    roster, each row with its project), its requests of the last seven days
    with what became of each, and its pool."""
    rows = roster(channel)
    shown = requests_shown(channel)
    held = pool(channel, rows)
    if as_json:
        print(json.dumps({"id": channel.id, "name": channel.name,
                          "members": [sminos.member_json(m, p) for p, m in rows],
                          "requests": shown, "pool": held}, indent=2))
        return
    print("# %s  %s" % (channel.name, channel.id))
    print("members")
    section(rows)
    for title, lines in (("requests", [_request_line(r) for r in shown]), ("pool", [_pool_line(e) for e in held])):
        print(title)
        if lines:
            sminos.print_table_rows(lines)
        else:
            print("  (none)")


def _states(channel, record, session):
    """Whether the session is its thread's current one (a thread of this
    machine that has not ended, lane A) and its own events in the project it
    is in state the channel under a `joined` in effect stamped with that
    thread: what a reader of the roster honours an env
    event by. Read from files as they are, reconciling nothing and writing
    nothing (no view is read), so a refusal leaves every log as it was."""
    threads, records = sminos.threads_module(), sminos.records_module()
    if record is None or threads.record_ended(record) or record["current"] != session \
            or records.lane_of(records.read(session)) == "B":
        return False
    project = sminos.last_project(session)
    if project is None:
        return False
    row = sminos._projection(sminos.own_events_now(project, session)).get(session) or {}
    # The `joined` in effect is the record's thread's: the env event is stamped with that thread, and a reader
    # honours it only through that thread's row.
    if (row.get("joined") or {}).get("thread") != record["thread"]:
        return False
    return channel.id in threads.stated_set(row.get("stated"))


def env(channel, op, machine, session):
    """`channel env add|remove <channel> <machine>` (§8): a `channel-env`
    under the calling thread's own stream in the channel's log (§2), refused
    before anything is written, and before any read that reconciles: from a
    terminal, for a machine the org's directory does not list, and from a
    thread whose own events do not state the channel under this session (no
    reader would honour its event; _states). The capability is the
    caller's check (cmd_channel). The exit code."""
    if not session:
        sminos.die("channel env is a member's: run it from a session of a thread in %s: nothing was written"
                   % channel.name, 1)
    listed = {str(m.get("name") or "").lower(): m["name"] for m in ((sminos.org_directory() or {}).get("machines")
                                                                     or [])}
    name = listed.get(machine.lower())
    if not name:
        sminos.die("no machine %s is listed in the org's directory: nothing was written" % machine, 1)
    record = sminos.threads_module().current_record(session, fresh=True)
    if not _states(channel, record, session):
        sminos.die("%s is not in %s: only a member changes its pool: nothing was written"
                   % (_label((record or {}).get("alias") or "", session), channel.name), 1)
    try:
        writer, audience = sminos.own_stream(channel, session)
        sminos.keep_stream(channel, writer, audience)
        sminos.log_append(channel, writer, "channel-env", op=op, machine=name, thread=record["thread"])
    except (OSError, sminos.audience_module().StreamUnknown) as err:
        sminos.die("the pool of %s was not changed: %s: nothing was written" % (channel.name, err), 1)
    sminos.nudge_daemon()
    print(("%s is in the pool of %s, added by hand" if op == "add" else
           "%s is no longer in the pool of %s by hand") % (name, channel.name))
    return 0
