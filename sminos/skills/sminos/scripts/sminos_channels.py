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
  `list`, `channel show`, `channel env`, the pool and the commands that
  address through a channel (below), and by nothing that delivers or
  publishes (C1); what became of a request (answers,
  answer_of: an index of the statements that answer one, never the fold);
  the pool (pool: the roster's rows by machine, and the machines a member
  added by hand, `channel-env`); `channel show` and `channel env` (show,
  env).
- Names through a channel (CH2's M1, its plan
  docs/doperpowers/plans/2026-11-22-sminos-channels-ch2.md, Interfaces §1):
  the thread a name reaches in a channel's roster (reach_in, which a verb's
  target `<channel>/<name>` is, sminos.find_target), whom a row is
  addressed as (thread_of_row), the threads a session has been
  (claimants), those ever in a channel (once_in), and the rows a bare
  `@alias` is also looked up in (shared_rows, sminos._resolve_tag).
- What a channel owes a thread (CH2's M2, Interfaces §3's first half): the
  one selection (owed, over a Debt read from the thread's record alone:
  debt), by the thread's id and past where its membership began; what a
  push needs beside it (owing, an Owing); the thread's delivery record read
  strictly (delivered); the last check (still_owed); and what `daemon owed`
  counts for a channel (owed_here).
- Pushing from a channel's log (CH2's M3, §3's second half): the channel's
  delivery pass (deliver), a thread's row in its own project (own_row), and
  a record made consistent with its boundary (normalize).
- Saying into a channel (CH2's M4, §2 and §6): the door (speak), which
  hands its appends to sminos.say_into with what a channel adds (Said); a
  recipient of this machine's Owing for the sender's own delivery
  (owing_for); and `chat <channel>` (chat).
- Across machines (CH2's M6, §4): what the uplink asks about a channel's
  messages (asks_due, by the one selection, one ask per thread and
  writer), the endpoint's answer kept in a file for the daemon
  (word_key, keep_word, under `words/`, good for WORD_KEPT seconds and
  one launch) and carried out by the daemon's channel pass (carry_words,
  each kept word handed to the delivery operation, which takes it under
  the thread's lock: take_word); and what holds a channel's log open on a
  machine that only wrote into it (unsent).
- The lead (CH2's M8, §5): which `channel-lead` a reader honours (is_lead),
  the lead in effect for this reader (lead_of, read where a person's
  untagged post is written: speak), and the verb (`channel lead`, lead).
"""
import glob
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
    return _boundary(t, channel_id)


def _boundary(record, channel_id):
    """The record's positions for the channel, {writer: seq}, {} for none."""
    began = record.get("began") if isinstance(record.get("began"), dict) else {}
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
        self._owner = {}

    def owner(self, session):
        """The record whose current session `session` is, by thread_of's
        order over every record, those set aside included (an archived
        human-opened record before an older copy's seat for the same
        session: T1; a newer record that ended still holds it: C6), from the
        stores as they are; None for none, or a reservation's."""
        if session not in self._owner:
            threads = sminos.threads_module()
            t = threads.thread_of(session)
            self._owner[session] = t if t is not None and t["current"] == session and not threads.reservation(t) \
                else None
        return self._owner[session]

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
    return _token(sminos.records_module().read(session) if session else None)


def _token(rec):
    """reach_token of a session's record as read (None for none)."""
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
    now by thread_of's order, ended and set-aside records included (read
    from the stores as they are: an archived human-opened record owns its
    current session before an older copy's seat, and a newer record that
    ended still holds the session it had; the frontier's second review,
    C6), and the thread's session is not lane B."""
    threads = sminos.threads_module()
    if record is None or record["thread"] != request["thread"] or threads.record_ended(record):
        return False
    session = request["session"]
    if session != record["current"] and session not in record["sessions"]:
        return False
    other = facts.owner(session)
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
        # not_carried's reason, told of a channel: it has a registration on this machine, never a .smns.
        said = {sminos.NO_HUB: "its registration on this machine names no hub",
                sminos.OTHER_ORG: "its registration on this machine names another org"}.get(why, why)
        sminos.die("cannot %s %s: this machine's enrollment does not carry its log (%s): nothing was written"
                   % (doing, channel.name, said), 1)


def _print_rows(rows):
    for t, _, line in rows:
        print("%s: %s" % (t.label, line))


def cmd_channel(a):
    """`sminos channel create|add|remove|show|env|lead` (§8; `lead` CH2's
    M8): every verb that writes refused before anything is written where the
    kept welcome lists no `channels`; `show` is a read, and needs none."""
    if a.channel_op == "show":
        show(find_channel(a.channel), a.json)
        return
    if a.channel_op == "lead":
        sys.exit(lead(a.channel, a.thread))   # its refusal inside a session comes before anything is read
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
    named = [p for p in sminos.known_logs() if p.name == name]
    if len(named) == 1 and sminos.is_channel_id(named[0].id) and _memberless(named[0]):
        _refuse_uncarried(named[0], "bring back")   # before the first member is looked up, which reconciles
    first = _target(thread) if thread else _caller(session)
    if first.refusal:
        sminos.die("%s: refused: %s: nothing was written" % (first.label, first.refusal), 1)
    if not first.local:
        sminos.die("cannot create %s with %s: it runs on %s, and a channel's first member is a thread of this "
                   "machine: nothing was written" % (name, first.label, first.machine), 1)
    if len(first.channels) >= sminos.threads_module().CHANNEL_LIMIT:
        sminos.die(LIMIT_REFUSAL % first.label, 1)
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


class _SweptRow(sminos.Member):
    """A row as the sweep that produced it gives it: the view's Member, with
    what that sweep read of the row's view kept on the row itself
    (`swept`: its `joined`'s stamp, its statement's thread), so whom a row
    is addressed as (thread_of_row) is answered from the reading that found
    it, however many sweeps came after."""


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
            kept.append((p, v, m, _row_read(v.info.get(m.session))))
    # One row a thread across the views: a refill displaces a session in one project and joins its replacement in
    # another, and the two halves can be imported in either order. A row's thread is its stamp, else an older
    # copy's unstamped row's statement in effect (_thread_read), the rule thread_of_row addresses it by (CH2's M1).
    by_thread = {}
    for p, v, m, got in kept:
        if _thread_read(got):
            by_thread.setdefault(_thread_read(got), []).append((p, v, m))
    current = {tid: _newest_row(found) for tid, found in by_thread.items() if len(found) > 1}
    rosters_, rows, read = {}, {}, {}
    for p, v, m, got in kept:
        if _thread_read(got) in current and current[_thread_read(got)] != (p.id, m.session):
            continue
        if m.session:
            m = _SweptRow(*m)
            m.swept = got
            rows.setdefault(m.session, (p, m))
            read[(p.id, m.session)] = (m,) + got
        if sminos.has_ended(m):
            continue
        for c in m.channels:
            rosters_.setdefault(c, []).append((p, m))
    value = {"rosters": rosters_, "had": had, "rows": rows, "read": read, "views": views, "ended": None}
    _SWEPT["views"], _SWEPT["value"] = views, value
    return value


def _thread_read(read):
    """The thread a row is, from what _sweep read of it (_row_read): its stamp, else its statement's thread;
    "" for none."""
    return read[0] or read[1]


def _row_read(r):
    """(the thread its `joined` in effect is stamped with, the `thread` of its statement in effect) from a
    _projection row, each "" for none: what _sweep keeps of a row's view beside the row (thread_of_row)."""
    joined, stated = (r or {}).get("joined") or {}, (r or {}).get("stated") or {}
    stamp, said = joined.get("thread"), stated.get("thread")
    return (stamp if isinstance(stamp, str) else "", said if isinstance(said, str) else "")


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


# ------------------------------------------------------------ names through a channel (CH2's M1, its §1)

_ID_FORM = re.compile(r"[0-9a-f]{8}[0-9a-f-]{0,28}")


def id_form(name):
    """Whether a name reads as an id through a channel (§1): a whole id, or its first eight or more."""
    return _ID_FORM.fullmatch(name) is not None


def _kept_read(member):
    """What the sweep that produced a row read of it, (stamp, statement's thread), kept on the row (_SweptRow);
    None for a row no sweep produced (never a read made after the row was found)."""
    return getattr(member, "swept", None)


def row_thread(project, member):
    """The thread a row is, by the one rule a channel's rows are told
    apart by (CH2's M1): its `joined`'s stamp, else an older copy's
    unstamped row's statement in effect; "" for none. A roster's row is
    read from what its sweep kept; any other (a project's member list) from
    its project's view. For telling two rows of one thread apart, never for
    addressing one (thread_of_row)."""
    got = _kept_read(member)
    return _thread_read(got if got is not None else _row_read(sminos.view_of(project).info.get(member.session)))


def shared_rows(session):
    """The rows of the rosters of the channels the thread whose current
    session `session` is holds (channels_of), each thread once though it is
    in several (row_thread): what a bare `@alias` is also looked up in
    (§1). [] with no roster read when the record holds none, or there is no
    session (a person at a terminal), so such a sender pays one read of its
    own record."""
    held = [c for c in channels_of(session) if sminos.is_channel_id(c)] if session else []
    if not held:
        return []
    every, seen, out = rosters(), set(), []
    for c in held:
        for p, m in every.get(c, []):
            key = row_thread(p, m) or m.session
            if key not in seen:
                seen.add(key)
                out.append((p, m))
    return out


def thread_of_row(project, member):
    """(thread id, session) a roster's row is addressed as (§1), both from
    the one reading of that row the roster's own sweep made (_sweep keeps
    it beside its rows): the thread its `joined` in effect is stamped with,
    else, where an older copy left it unstamped, the `thread` of its
    statement in effect. None where both are there and disagree, where
    neither is, and for a row no sweep produced: nothing is read again
    here."""
    got = _kept_read(member)
    if got is None:
        return None
    stamp, said = got
    if stamp and said and stamp != said:
        return None
    thread = stamp or said
    return (thread, member.session) if thread and member.session else None


def _stated(events):
    """One log's statements that took effect and its sessions' episodes,
    folded in the merged read's order by the reducer's own rules
    (sminos_threads.Fold; the projection's episode step,
    sminos.episode_step): {"said": [(session, thread, channels, the stamp of
    the session's `joined` in effect then)], "episodes": {session:
    [(mark, {the threads of the statements that took effect in it}),
    ...]}}. A statement takes effect under the `joined` in effect, which is
    its session's last episode's, so it is that episode's whatever the
    clocks say. Kept beside the log (log_memo)."""
    threads = sminos.threads_module()
    fold, said, eps, within = threads.Fold(), [], {}, {}
    for e in events:
        sid, kind = e.get("session"), e.get("kind")
        if kind not in ("joined", "retired", "channels") or not isinstance(sid, str) or not sid \
                or sminos.writer_session(e.get("writer") or "") != sid:
            continue
        if kind == "channels":
            fold.state(sid, e)
            if fold.stated.get(sid) is e:
                stamp = (fold.joined.get(sid) or {}).get("thread")
                said.append((sid, e["thread"], threads.stated_set(e), stamp if isinstance(stamp, str) else ""))
                if eps.get(sid):
                    within.setdefault((sid, len(eps[sid]) - 1), set()).add(e["thread"])
            continue
        before = fold.effect.get(sid)
        if fold.add(sid, e) is not None and kind == "joined":
            sminos.episode_step(eps.setdefault(sid, []), e, before)
    return {"said": said, "episodes": {sid: [(ep[1], within.get((sid, i), set())) for i, ep in enumerate(got)]
                                       for sid, got in eps.items()}}


def _stated_views():
    """[(view, what _stated folds of its log)] for every project's view the roster's sweep read."""
    return [(v, sminos.log_memo(v.events, "channel-statements", _stated)) for _, v in _sweep()["views"]]


def _listed(v, sid):
    r = v.info.get(sid)
    return r is not None and not sminos.unlisted_here(sid, r)


def once_in(channel):
    """Every thread that has ever been in the channel, as this reader's logs
    say (§1): the `thread` of each statement whose set holds it and that
    took effect, where the `joined` in effect then is stamped with that
    thread or is unstamped; a session the log shows unlisted to this reader
    left out. A statement that never took effect, and another writer's,
    count for nothing: a stamp alone is any writer's to set."""
    cid = getattr(channel, "id", channel)
    return {thread for v, folded in _stated_views() for sid, thread, chans, stamp in folded["said"]
            if cid in chans and stamp in ("", thread) and _listed(v, sid)}


def claimants(session_id):
    """The threads that have had a session, as this reader's logs say (§1):
    the mark of each of its episodes (its stretches under one thread, by
    _projection's rule) in every project's view known here, an episode the
    log shows unlisted to this reader left out. An unmarked episode counts
    with the threads of the statements that took effect in it (_stated:
    under its `joined`, in the fold's order); one that has neither makes it
    None: the id names no one thread. Not from displayed rows: View.ended
    leaves out seated rows, and a row's former_ids does not hold its own
    session."""
    out = set()
    for v, folded in _stated_views():
        if not _listed(v, session_id):
            continue
        for mark, said in folded["episodes"].get(session_id, ()):
            if not (mark or said):
                return None
            out |= {mark} if mark else said
    return out


def _current_rows(thread_id):
    """[(Project, Member)] of a thread's row (row_thread) in any project's view here now, not ended: where a
    thread is reached when it is not in the channel."""
    swept = _sweep()
    return [(p, m) for p, m in swept["rows"].values()
            if _thread_read(swept["read"][(p.id, m.session)][1:]) == thread_id
            and not sminos.has_ended(m) and m.state != "retired"]


def _threads_known():
    """Every thread a row of a project's view here names, current or ended."""
    swept = _sweep()
    known = set(swept["had"]) | {_thread_read(got[1:]) for got in swept["read"].values()}
    known.update(m.thread for _, v in swept["views"] for m in v.ended if m.thread)
    return known - {""}


def _labels(rows):
    return sminos.candidate_labels(rows, False) or "none of them can be reached from here"


def _no_member(channel, name, short, label, rows, at, elsewhere=None, then=""):
    """Exit 4 for a name no member of the channel answers to (§2), naming where it answers elsewhere: the rows
    `elsewhere` gives (a thread the name already came to), else those the name reaches in every project; `then`,
    a sentence said after that list (a say's `--in`: how to reach it there)."""
    inside = {(p.id, m.session) for p, m in rows}
    if elsewhere is None:
        elsewhere = sminos.one_per_session(sminos.match_members(name, short, sminos.org_scope()))
    elsewhere = [(p, m) for p, m in elsewhere if (p.id, m.session) not in inside]
    sminos.die("no member %s in channel %s%s" % (label, channel.name, "; elsewhere: %s%s" % (sminos.candidate_labels(
        elsewhere, True, at), ". " + then if then else "") if elsewhere else ""), sminos.EXIT_UNKNOWN)


def _torn(member):
    """Whether a row's stamp and its statement in effect name two threads (thread_of_row answers None)."""
    got = _kept_read(member)
    return got is not None and bool(got[0]) and bool(got[1]) and got[0] != got[1]


def _as_thread(channel, label, thread, addressed, once):
    """§1's answer for a name that came to one thread: its roster row ("in"), else, once in the channel, its
    row now ("out", None, None where it has none); None for a thread never in it. A row now whose stamp and
    statement name two threads is no one thread to send to, in the channel or out of it: exit 4, no recipient
    offered."""
    rows = [(p, m) for p, m, t in addressed if t[0] == thread]
    if rows:
        return ("in",) + rows[0]
    if thread not in once:
        return None
    now = _current_rows(thread)
    if now and _torn(now[0][1]):
        sminos.die("%s: not reached through %s (its row's membership names two threads: its stamp and its statement "
                   "disagree), and nothing is sent to it" % (label, channel.name), sminos.EXIT_UNKNOWN)
    return ("out",) + (now[0] if now else (None, None))


def _reach_by_id(channel, name, label, rows, at, then=""):
    """§1's table for a name in id form: (where, Project, Member, how), how
    "thread" for a thread id's prefix, "session" for a session's
    (claimants). None when the name is no thread's and no session's this
    reader can read, so it is looked up as an alias."""
    addressed = [(p, m, t) for p, m in rows if (t := thread_of_row(p, m)) is not None]
    hit = [(p, m) for p, m, t in addressed if t[0].startswith(name)]
    if len(hit) > 1:
        sminos.die("ambiguous %s in channel %s matches: %s" % (label, channel.name, _labels(hit)),
                   sminos.EXIT_UNKNOWN)
    if hit:
        return ("in",) + hit[0] + ("thread",)
    once = once_in(channel)
    named = sorted(t for t in once if t.startswith(name))
    if len(named) > 1:
        sminos.die("ambiguous %s in channel %s matches: %s" % (
            label, channel.name, _labels([r for t in named for r in _current_rows(t)])), sminos.EXIT_UNKNOWN)
    if named:
        return _as_thread(channel, label, named[0], addressed, once) + ("thread",)
    known = [t for t in _threads_known() if t.startswith(name)]
    if known:   # a thread never in the channel: no old reply
        _no_member(channel, name, "", label, rows, at, [r for t in known for r in _current_rows(t)], then)
    sessions = sorted({sid for v, _ in _stated_views() for sid in v.info if sid.startswith(name) and _listed(v, sid)})
    if not sessions:
        return None
    had, untold = set(), False
    for sid in sessions:
        c = claimants(sid)
        untold = untold or c is None
        had |= c or set()
    if untold or len(had) > 1:
        # Nothing is sent: a session's id typed by hand reaches a thread only when one thread alone has had it.
        theirs = [(p, m) for p, m, t in addressed if t[0] in had or m.session in sessions]
        why = "the session it names has been more than one thread's" if not untold else \
            "the session it names cannot be told to one thread from here (a membership of it an older copy left " \
            "unmarked)"
        sminos.die("ambiguous %s in %s: %s: %s — name the one you mean" % (
            label, channel.name, why, _labels(theirs)), sminos.EXIT_UNKNOWN)
    if not had:
        return None
    thread = had.pop()
    got = _as_thread(channel, label, thread, addressed, once)
    if got is None:
        _no_member(channel, name, "", label, rows, at, _current_rows(thread), then)
    return got + ("session",)


def reach_in(channel, name, short="", at="", how=False, then=""):
    """The member of the channel a name reaches (§1): ("in", Project,
    Member), the one row of roster(channel) it reaches with its own
    project; ("out", Project, Member) for a thread that was once in the
    channel and is not now, with its row in its own project (None, None
    where it has none: it ended, or this reader may not read it), its
    caller saying what that means. Every other miss exits 4, in §2's words;
    `at`, how a refusal's `elsewhere` names a row ("@" for a tag), and
    `then`, a sentence said after it (a say's `--in`, CH2's M4). With
    how=True a fourth value says what the name matched: "short", "thread",
    "session", "alias" or "former" (an alias the row held before).

    With `short` (`alias#short`): a row whose alias is `name` and whose
    session id begins with `short`. A name in id form: a thread id's prefix
    first, then a session's (_reach_by_id); one that is neither is looked
    up as an alias. An alias: the rows whose current alias it is, and only
    when there is none those that held it before (current_first). Two rows
    a name reaches are refused, each as alias#short."""
    rows = roster(channel)
    label = "%s#%s" % (name, short) if short else name
    got = None
    if short:
        found = [(p, m) for p, m in rows if m.alias == name and m.session.startswith(short)]
        kind = "short"
    elif id_form(name) and (got := _reach_by_id(channel, name, label, rows, at, then)) is not None:
        found, kind = [got[1:3]], got[3]
    else:
        hits = [(p, m, h) for p, m in rows if (h := sminos.alias_reach(m, name))]
        found = sminos.current_first(hits, name)
        kind = "former" if hits and all(h == "former" for _, _, h in hits) else "alias"
    if len(found) > 1:
        sminos.die("ambiguous %s in channel %s matches: %s" % (label, channel.name, _labels(found)),
                   sminos.EXIT_UNKNOWN)
    if not found:
        _no_member(channel, name, short, label, rows, at, then=then)
    answer = (got[0] if got is not None else "in",) + tuple(found[0])
    return answer + (kind,) if how else answer


# ------------------------------------------------------------ saying into a channel (CH2's M4, its §2 and §6)

# The sentences of §2 that are decisions (the plan's open point 4: its drafts of what a session and a person are told).
SELECTOR_NAMES_CHANNEL = '%s is a channel, and a selector names projects: sminos say --in %s "@all …" reaches its live members'
SELECTOR_BESIDE_IN = ('a selector picks the recipients itself, and --in %s names a channel: drop the selector — sminos say '
                      '--in %s "@all …" reaches its live members')
OPENS_NO_TAG = ("%s opens no tag (a tag's qualifier takes no #): nothing was recorded. Say it as sminos say --in %s "
                "\"@<alias> …\", or qualify the tag with the channel's id")
NO_DIRECTORYS = "%s is a channel, and no directory's project: say --in %s to speak in it"
NOT_A_MEMBER = "you are not in %s: replies to this come to you directly, in %s. sminos channel add %s places you in it"
NO_HOME = ("you are not in %s, and this session's project cannot be told, so a reply would have nowhere to "
           "reach you: nothing was recorded")
DROP_IN = "Drop --in to reach it in its own project"
SENT_DIRECTLY = "%s is not in %s now: sent to it directly, in %s"
CANNOT_REACH = ("%s was in %s and cannot be reached now (it has ended, or this machine may not read it): nothing was "
                "recorded")
LEFT_WITH_IN = ("%s is not in %s now (it left the channel, or its thread ended): nothing was recorded. " + DROP_IN)
ONE_LOG = "one message, one log: the tags name %s"
RESOLVES_OUTSIDE = "; %s resolves outside %s"   # an unqualified tag beside a channel's, no log claimed for it
RESOLVE_OUTSIDE = "; %s resolve outside %s"
HOST_IS_PROJECTS = ("%s is a channel, and what a session sends its human is in its own project's log: sminos chat "
                    "--host <project>")
NOT_IN_HERE = "recorded (it is not in %s on its machine now: not delivered)"
NOT_ADDRESSED = "not addressed (its membership of %s names two threads: nothing was recorded for it)"
NONE_ADDRESSED = "no thread this message names can be addressed in %s: nothing was recorded"


class Said(NamedTuple):
    """What a say into a channel's log gives sminos.say_into beside what a project's say does."""
    fields: dict          # what each event adds: the sender's `thread` (a say), an outsider's `from_project`
    copied: bool          # an outsider's: a copy in its own project, where record_copy keeps one
    after: str            # the line said after the `recorded` lines (an outsider's), or ""
    rows: dict            # {thread: (Project, Member)}: each recipient's row as the roster gave it


def _log_name(q):
    """How the refusal of a mix names the log a tag's qualifier names, read without a reconciliation."""
    c = sminos.names_channel(q)
    if c is not None:
        return c.name
    tiers = sminos.project_tiers(q)
    return tiers[0].name if tiers else q


def _bare_logs(t):
    """The logs the refusal of a mix names for an unqualified tag, found
    with no member looked up through a view (a refusal reconciles nothing
    and appends nothing): for `@alias#short` and a name in id form, the
    projects a short tag reaches (org_scope) whose log holds a member it
    answers to (sminos.logged_members). Empty for a bare alias, and where
    none answers: where a bare alias goes is the resolver's to say (the
    sender's project, or a channel-mate's through the rosters it reads),
    so the refusal claims no log for it and names the tag."""
    name, short = t["name"], t["short"]
    if not (short or id_form(name)):
        return set()
    return {p.name for p in sminos.org_scope() for m in sminos.logged_members(p)
            if m.state != "retired" and (sminos.alias_reach(m, name, short) if short else sminos.id_reach(m, name))}


def _entry_of(channel, p, m):
    """The `to` entry of a roster's row ({session, alias, thread}: the thread and the session from one reading of
    the row, thread_of_row), or None for a row that is not addressed, its line said."""
    got = thread_of_row(p, m)
    if got is None:
        print("%s: %s" % (m.alias, NOT_ADDRESSED % channel.name))
        return None
    return {"session": got[1], "alias": m.alias, "thread": got[0]}


def speak(channel, a, session, tags):
    """The door (§2): a say that names a channel, by `--in` or by a tag's
    qualifier, from a session or a person at a terminal (`session` ""). It
    decides, before anything is appended: the form (no selector beside it);
    the channel (registered here: a name no log answers to is the unknown
    name it is); that the machine's enrollment carries the channel's log
    (_refuse_uncarried, which spares a channel that has left this machine);
    that every tag is in this one channel (with `--in` each is looked up in
    its roster alone, in any form a tag takes; without it, the tags
    qualified by it, and a mix with another log is refused, naming each);
    the recipients (reach_in, `@all` the roster's live rows but the sender's,
    each entry's thread and session from one reading of its row); and who
    writes: a member, a person at a terminal and a machine's notice as a
    member; a session that is no member (channels_of, read once, here, from
    its own machine's record) with its project in `from_project`, its copy
    where record_copy keeps one, and one line; refused (NO_HOME) when its
    project cannot be told, never written as a member's. The sender's
    stamp is taken after the rosters' sweeps, which can make it a thread,
    and `@all` leaves out its row by session and by thread, each compared
    with its own kind. A tag qualified by the channel
    that names a thread that was in it and is not now (an old frame's reply
    line) goes to that thread directly, in its own project, by a project's
    say. An untagged post a person types at a terminal (no session, no
    `--notice`) is addressed to the lead in effect here (lead_of), if any.
    Then it appends and delivers as a project's say does
    (sminos.say_into)."""
    via_in = bool(a.in_) and sminos.names_channel(a.in_) is not None
    if sminos.selector_given(a):
        sminos.die(SELECTOR_BESIDE_IN % (channel.name, channel.name), 1)
    if a.in_ and not via_in:
        if session:
            sminos.die("--in is for an operator, not a session — tag @<project>/<name> to speak into another project")
        sminos.die(ONE_LOG % ", ".join(sorted({_log_name(a.in_), channel.name})), sminos.EXIT_UNKNOWN)
    found = sminos.known_project(channel.id)
    if found is None:
        sminos.die("no channel '%s' is known on this machine" % channel.name, sminos.EXIT_UNKNOWN)
    channel = found
    _refuse_uncarried(channel, "say into")
    threads = sminos.threads_module()
    if session:
        caller = sminos.caller_seat()
        home = sminos.caller_project(caller)
        sender = caller["alias"] if caller else sminos.default_from("")
        writer, kind = sminos.writer_id(session), "say"
        outsider = channel.id not in channels_of(session)
        if outsider and home is None:
            # No project to name in `from_project`, to keep its copy in, or for a reply to reach: a session that is
            # no member is never written as one for want of a project.
            sminos.die(NO_HOME % channel.name, 1)
    else:
        home, sender, writer, kind, outsider = None, "human", sminos.writer_id(), "human", False
    if any(sminos.is_all(t) for t in tags) and len(tags) != 1:
        sminos.die("@all stands alone")
    inside, others = [], []
    for t in tags:
        q = t["project"]
        if (via_in and not q) or (q and getattr(sminos.names_channel(q), "id", None) == channel.id):
            inside.append(t)
        else:
            others.append(t)
    if others:
        names, loose = {channel.name}, []
        for t in others:
            got = {_log_name(t["project"])} if t["project"] else _bare_logs(t)
            names |= got
            loose += [] if got else [t["raw"]]
        said = ONE_LOG % ", ".join(sorted(names))
        if loose:
            said += (RESOLVES_OUTSIDE if len(loose) == 1 else RESOLVE_OUTSIDE) % (", ".join(loose), channel.name)
        sminos.die(said, sminos.EXIT_UNKNOWN)
    recipients, raws, rows, wake = [], [], {}, False
    if any(sminos.is_all(t) for t in tags):
        wake = True
        rows_now = roster(channel)
        thread = threads.stamp(session) if session else ""   # after the sweep, which can make the sender a thread
        for p, m in rows_now:
            # The sender's own row left out by its session, or by its thread: a session compared with sessions, a
            # thread with threads (a seat's thread id is its first session's, which may be the sender now).
            if m.state not in sminos.FILLED or (session and m.session == session):
                continue
            r = _entry_of(channel, p, m)
            if r is not None and not (thread and r["thread"] == thread) and r["thread"] not in rows:
                recipients.append(r)
                rows[r["thread"]] = (p, m)
    else:
        au = sminos.audience_module()
        run = au.leading_run(a.text)[0]
        outs, held, skipped = {}, [], False
        for i, t in enumerate(inside):
            where, p, m, _ = reach_in(channel, t["name"], t["short"], at="@", how=True,
                                      then=DROP_IN if via_in else "")
            raw = run[i] if i < len(run) else t["raw"]
            if where == "out":
                if via_in:
                    sminos.die(LEFT_WITH_IN % (t["raw"], channel.name), sminos.EXIT_UNKNOWN)
                if m is None or p.id not in {q.id for q in sminos.org_scope()}:
                    # Ended, or in a project a short tag may not write into (retired in the org's directory, or
                    # left this machine): the guard `@<short>` meets, before anything is appended or said.
                    sminos.die(CANNOT_REACH % (t["raw"], channel.name), sminos.EXIT_UNKNOWN)
                outs.setdefault(p.id, (p, []))[1].append((t, m, (i, raw)))
                continue
            r = _entry_of(channel, p, m)
            if r is None:
                skipped = True
                continue
            at = next((j for j, x in enumerate(recipients) if x["thread"] == r["thread"]), None)
            if at is None:
                recipients.append(r)
                rows[r["thread"]] = (p, m)
                held.append([])
                at = len(recipients) - 1
            held[at].append((i, raw))
        if outs and (recipients or len(outs) > 1):
            sminos.die(ONE_LOG % ", ".join(sorted({channel.name} | {p.name for p, _ in outs.values()})),
                       sminos.EXIT_UNKNOWN)
        if tags and not recipients and not outs:
            sminos.die(NONE_ADDRESSED % channel.name, sminos.EXIT_UNKNOWN)
        if skipped:
            # A row given no entry has no tag in the text either, on either route (in the channel, or directly to a
            # thread that left it): a stream splitter rebuilds the text only for several audiences, and one
            # audience's event would name the row it skipped.
            kept = [x for places in held for x in places] + [place for _, got in outs.values() for _, _, place in got]
            a.text = au.split_text(a.text, [raw for _, raw in sorted(kept)])
        if outs:
            # Sent to the thread directly, in its own project, by a project's say (C5: a reply to a member that left).
            [(dest, got)] = outs.values()
            direct, draws = [], []
            for t, m, place in got:
                print(SENT_DIRECTLY % (t["raw"], channel.name, dest.name))
                at = next((j for j, x in enumerate(direct) if x["session"] == m.session), None)
                if at is None:
                    direct.append({"session": m.session, "alias": m.alias})
                    draws.append([])
                    at = len(direct) - 1
                draws[at].append(place)
            sminos.say_into(a, dest, home, session, sender, writer, kind, direct, False, draws)
            return
        raws = held
    if not tags and not session and a.notice is None:
        # An untagged post the person types at a terminal of this machine is addressed to the lead (CH2's M8, §5),
        # read here, where it is written; a session's, and a machine's notice, stay untagged.
        leader = lead_of(channel)
        if leader is not None and (r := _entry_of(channel, *leader)) is not None:
            recipients, rows, raws = [r], {r["thread"]: leader}, [[]]
    # The sender's stamp, taken after every sweep of the rosters above (any can make a live sender a thread).
    thread = threads.stamp(session) if session else ""
    fields = {"thread": thread} if kind == "say" and thread else {}
    if outsider:
        fields["from_project"] = home.id   # the sender's own project, where a reply finds it (C5)
    said = Said(fields, outsider, NOT_A_MEMBER % (channel.name, home.name, channel.name) if outsider else "", rows)
    sminos.say_into(a, channel, home, session, sender, writer, kind, recipients, wake, raws, said=said)


def owing_for(channel, thread):
    """(Owing or None, a line or "") for a recipient of this machine that a
    say's entry names (sminos.deliver_say): the line, NOT_IN_HERE, where the
    thread's record here has ended or does not hold the channel (the roster
    read a statement this machine's record has since left); else owing() with
    own_row(), None while it defers (an open entry, a session that defers),
    and the daemon's pass delivers it later."""
    threads = sminos.threads_module()
    record = threads.get(thread) if isinstance(thread, str) and thread else None
    if record is None or threads.record_ended(record) or channel.id not in threads.held_set(record):
        return None, NOT_IN_HERE % channel.name
    return owing(channel, record, own_row(record)), ""


SESSION_CURSOR = "session-%s"   # a channel's chat cursor of a session that is no thread (chat)


def chat(channel, a, session):
    """cmd_chat's read over a channel's log (§6), by sminos.chat_read: the
    channel's own view first (view_of, which reconciles a channel as a
    channel), never sminos.reconcile, which would run a project's
    reconciliation over what an older copy joined into it; a line whose
    event carries `from_project` with the frame's clause after its sender;
    `--host` refused. Any reader that can read the log may: a channel bounds
    no one's reach. The reader is its thread (stamp): the cursor is kept
    under it, as its delivery record is, so a hand-off carries nothing, and
    the thread's own messages are not unread, whichever of its sessions
    wrote them (sminos.frame_of's rule). A session that is no thread, and a
    person at a terminal, read as in a project: the cursor the session's
    (or the terminal's), its own writer's messages not unread. A session's
    is kept apart from a thread's (`session-<id>`): a seat's thread id is
    its first session's, which may read here when it is no thread."""
    if a.host:
        sminos.die(HOST_IS_PROJECTS % channel.name, 1)
    sminos.view_of(channel)
    kinds = tuple(a.kind) if a.kind else sminos.CHAT_KINDS
    events = sminos.log_read(channel)
    pool = [e for e in events if e["kind"] in kinds]
    thread = sminos.threads_module().stamp(session) if session else ""
    me = sminos.writer_id(session or None)
    sminos.chat_read(channel, a, events, pool, thread or (SESSION_CURSOR % session if session else ""),
                     (lambda e: e.get("thread") != thread) if thread else
                     (lambda e: sminos.writer_base(e["writer"]) != me),
                     lambda e, label: sminos.chat_line(
                         e, (" (not in %s)" % channel.name if e.get("from_project") else "") + label(e)))


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
    """`channel show <channel> [--json]` (§8): its heading, its lead while one
    is in effect for this reader (CH2's M8: a line after the heading, the key
    `lead` its thread id; neither without one), its members (the roster, each
    row with its project), its requests of the last seven days with what
    became of each, and its pool."""
    rows = roster(channel)
    shown = requests_shown(channel)
    held = pool(channel, rows)
    leader = lead_of(channel, rows)
    if as_json:
        print(json.dumps({"id": channel.id, "name": channel.name,
                          **({"lead": thread_of_row(*leader)[0]} if leader is not None else {}),
                          "members": [sminos.member_json(m, p) for p, m in rows],
                          "requests": shown, "pool": held}, indent=2))
        return
    print("# %s  %s" % (channel.name, channel.id))
    if leader is not None:
        print("lead  %s" % _label(leader[1].alias, leader[1].session))
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



# ------------------------------------------------------------ the lead (CH2's M8, its §5)
#
# A `channel-lead` in the channel's log, honoured only under a machine's human writer (plain, or under that writer's
# audience stream), names the thread an untagged message the owner types into the channel at a terminal of the
# writing machine is addressed to. It is read where a post is written (speak); the receiving side reads no lead, it
# delivers an addressed event. The event takes the audience of the thread it names, as a request does, and a plain
# `{"thread": null}` goes before one that goes under a stream: a reader that may not read the lead reads none.

# The sentences of §5 that are decisions (the plan's open point 4).
LEAD_IN_SESSION = ("channel lead is for a person at a terminal, and this runs inside a session: nothing was written. "
                   "Report it to your human instead")
LEAD_NO_TERMINAL = ("naming a channel's lead needs its owner at a terminal to confirm it, and this has none: nothing "
                    "was written")
LEAD_PROMPT = ("Make %s the lead of %s? A message you type into %s with no tag, on this machine, is then addressed to "
               "it. Confirm? [y/N] ")
LEAD_CLEAR_PROMPT = "Clear the lead of %s? Confirm? [y/N] "
NOT_CONFIRMED = "not confirmed: nothing was written"
LEAD_NOT_IN = "%s is not in %s: sminos channel add %s <thread> places it first"
LEADS = "%s leads %s"
LEAD_ELSEWHERE = "(on %s: a message you type here reaches it as a peer's, not as its human's words)"
LEAD_PRIVATE = "(private: only machines that may read it see that it leads)"
NO_LEAD = "%s has no lead"
LEAD_TORN = "%s: its membership of %s names two threads (its stamp and its statement disagree): nothing was written"
LEAD_CHANGED = ("%s changed while you answered (it left %s, ended, or went on in another session): nothing was written. "
                "Run it again")
LEAD_WAITS = ("the lead of %s was not written: this machine's writer waits for its head after its enrolment, so the "
              "clearing event a private lead goes behind cannot go first: nothing was written. Run it again once its "
              "daemon has caught up")
LEAD_RENAMED = "this machine's name changed while you answered (%s, now %s): nothing was written. Run it again"
LEAD_RESET_ONLY = ("the lead of %s: its clearing event was written (%s has no lead now); the private lead was not, "
                   "because this machine's name changed (%s, now %s). Run it again")
LEAD_AUDIENCE = "%s's audience changed while its lead was written: nothing was written. Run it again"
LEAD_RESET_AUDIENCE = ("the lead of %s: its clearing event was written (%s has no lead now); the private lead was not, "
                       "because %s's audience changed while it was written. Run it again")
LEAD_UNMARKED = "this machine's name (%s) is no machine name a reader honours a lead under: nothing was written"


def is_lead(e):
    """Whether an event is a lead a reader honours (§5): kind `channel-lead`;
    its plain writer `<machine>/human` with a machine's name by the notice's
    grammar (sminos.NOTICE_MACHINE_RE, never `hub` or `legacy`), an audience
    stream of it included; no `notice` and no `to`; and `thread` a non-empty
    string with a non-empty string `session`, or None with no `session`
    under the plain writer (a clearing event is plain, C2)."""
    if not isinstance(e, dict) or e.get("kind") != "channel-lead" or "thread" not in e or "notice" in e or "to" in e:
        return False
    machine, _, last = sminos.writer_base(str(e.get("writer") or "")).rpartition("/")
    if last != "human" or not sminos.NOTICE_MACHINE_RE.fullmatch(machine) or machine.lower() in sminos.NOT_MACHINES:
        return False
    thread = e.get("thread")
    if thread is None:
        return "session" not in e and not sminos.is_stream(e["writer"])   # a clearing event is plain (C2)
    return isinstance(thread, str) and bool(thread) and isinstance(e.get("session"), str) and bool(e["session"])


def lead_of(channel, rows=None):
    """(Project, Member) of the channel's lead in effect for this reader, or
    None (§5): the last is_lead event of the merged log this machine holds
    decides, whoever wrote the ones before it; None for a `thread` of None;
    else the roster's row (`rows`, the roster by default) addressed as that
    thread (thread_of_row); None when no row is (it ended, left, or this
    reader may not read it). An earlier lead never comes back in its place,
    so a log with a writer's file here that cannot be read gives none: the
    lead in effect may be in it (a stream this machine was never served is
    no file here, and no gap)."""
    last = None
    files, events = sminos._store_whole(channel, "log", shared=True)
    if any(key is None for _, key in files):
        return None
    for e in events:
        if is_lead(e):
            last = e
    if last is None or last["thread"] is None:
        return None
    for p, m in (roster(channel) if rows is None else rows):
        got = thread_of_row(p, m)
        if got is not None and got[0] == last["thread"]:
            return p, m
    return None


def _in_roster(rows, name, short):
    """Whether a name, as a tag would take it, answers a row of the roster (reach_in's forms), so the channel's
    own resolution decides it."""
    for p, m in rows:
        if short:
            if m.alias == name and m.session.startswith(short):
                return True
        elif sminos.alias_reach(m, name):   # a name in id form no id begins with is an alias too (reach_in)
            return True
        elif id_form(name):
            got = thread_of_row(p, m)
            if m.session.startswith(name) or (got is not None and got[0].startswith(name)):
                return True
    return False


def _lead_row(channel, q):
    """The roster's row a name for the lead reaches: through the channel's roster (reach_in) when it answers a
    row there, so a member is named from any directory; else as any verb names a thread (_target: exit 4 for a
    name unknown or ambiguous), refused with exit 1 when that thread has no row in the roster."""
    rows = roster(channel)
    if "/" not in q:
        name, _, short = q.partition("#")
        if _in_roster(rows, name, short):
            where, p, m = reach_in(channel, name, short)
            if where == "in":
                return p, m
    t = _target(q)
    for p, m in rows:
        got = thread_of_row(p, m)
        if t.thread and got is not None and got[0] == t.thread:
            return p, m
    sminos.die(LEAD_NOT_IN % (t.label, channel.name, channel.name), 1)


def _lead_choice(channel, session, alias, label):
    """The one stream a lead naming that session goes under (sminos.stream_choice for that one recipient, from
    the machine's human writer): (writer, audience); exit 1 in the choice's own words where it refuses."""
    choice, refusal = sminos.stream_choice(channel, "", [{"session": session, "alias": alias}], "the lead %s" % label)
    if refusal:
        sminos.die(refusal[0], 1)
    return choice[0][0], choice[0][1]


class _NotWritten(Exception):
    """An append of the lead's that its guard refused (lead): nothing written, the reason kept by the caller."""


def lead(q, name):
    """`channel lead <channel> <thread|none>` (§5): refused inside a session
    before anything is read; without the capability; where the enrollment
    does not carry the channel's log; on a machine whose name no reader
    would honour a lead under; for a thread that has no row in the roster;
    where the stream choice refuses; then the owner's typed yes at the
    terminal (sminos_visibility.confirmed, which refuses where there is
    none). After the answer the thread is read again by its id, and the
    machine's name as its files say. The event goes under the machine's
    human writer, plain for a thread that is not private, under that
    writer's audience stream after a plain clearing event for one that is,
    which must land first (refused, nothing queued, while the plain writer
    waits for its head: _append(queue=False)). Each append checks the name
    again under its writer's lock. The exit code."""
    if os.environ.get("CLAUDE_CODE_SESSION_ID"):
        sminos.die(LEAD_IN_SESSION, 1)
    if not sminos.audience_module().advertised("channels"):
        sminos.die(CAPABILITY_REFUSAL, 1)
    channel = find_channel(q)
    _refuse_uncarried(channel, "name the lead of")
    writer = sminos.writer_id()
    if not is_lead({"kind": "channel-lead", "writer": writer, "thread": None}):
        sminos.die(LEAD_UNMARKED % sminos.writer_base(writer).rpartition("/")[0], 1)
    row = None
    if name == "none":
        prompt = LEAD_CLEAR_PROMPT % channel.name
    else:
        row = _lead_row(channel, name)
        got = thread_of_row(*row)
        if got is None:   # a torn row is addressed as no thread (M4 refuses it for a tag)
            sminos.die(LEAD_TORN % (_label(row[1].alias, row[1].session), channel.name), sminos.EXIT_UNKNOWN)
        thread, session = got
        label = _label(row[1].alias, session)
        _lead_choice(channel, session, row[1].alias, label)
        prompt = LEAD_PROMPT % (label, channel.name, channel.name)
    if not sminos.sibling_module("sminos_visibility").confirmed("", None, prompt=prompt, none=LEAD_NO_TERMINAL):
        sminos.die(NOT_CONFIRMED, 1)
    if row is not None:
        # The person may have taken a while: the thread chosen is read again by its id (its row in the roster and
        # the session that row holds); a change refuses, and the name is not resolved again.
        sminos.forget_caches()
        row = next(((p, m) for p, m in roster(channel) if (got := thread_of_row(p, m)) is not None
                    and got[0] == thread), None)
        if row is None or thread_of_row(*row)[1] != session:
            sminos.die(LEAD_CHANGED % (label, channel.name), 1)
    # Both writers come from the machine's name as its files say now, and each append checks it again under the
    # writer's own lock (_append's guard): a rename while the prompt was read writes nothing under either name.
    machine = sminos.writer_base(writer).rpartition("/")[0]
    if sminos.machine_name_now() != machine:
        sminos.die(LEAD_RENAMED % (machine, sminos.machine_name_now()), 1)
    renamed = []

    def same_name(_events):
        if sminos.machine_name_now() != machine:
            renamed.append(sminos.machine_name_now())
        return not renamed

    def same_stream(events):
        # The stream was chosen before the writer's locks were waited for: a thread that turned private (or public)
        # meanwhile would get its lead under the wrong writer, the plain one naming it to every reader.
        if not same_name(events):
            return False
        choice, refusal = sminos.stream_choice(channel, "", [{"session": session, "alias": row[1].alias}], label)
        return not refusal and (choice[0][0], choice[0][1]) == (stream, audience)

    def append(w, fields, queue=True, guard=same_name):
        got = sminos._append(channel, w, [{"kind": "channel-lead", **fields}], guard=guard, queue=queue)
        if not got:
            raise _NotWritten()
        return got[0]
    cleared = False
    try:
        if row is None:
            e = append(writer, {"thread": None})
        else:
            # Chosen again at the append: the person may have taken a while at the prompt.
            stream, audience = _lead_choice(channel, session, row[1].alias, label)
            if sminos.writer_base(stream) != writer:
                sminos.die(LEAD_RENAMED % (machine, sminos.writer_base(stream).rpartition("/")[0]), 1)
            if audience is not None:
                # The private event goes only behind a plain clearing event that has landed. A writer waits for its
                # head on its own, so the reset is refused rather than queued (queue=False: _append's one reading
                # of the wait, under the writer's lock): a reset left queued would clear the earlier lead with no
                # `none` run, and the private event would go up ahead of it.
                append(writer, {"thread": None}, queue=False)
                cleared = True
            sminos.keep_stream(channel, stream, audience)
            e = append(stream, {"thread": thread, "session": session}, guard=same_stream)
    except sminos.HeadWaits:
        sminos.die(LEAD_WAITS % channel.name, 1)
    except _NotWritten:
        if not renamed:
            sminos.die(LEAD_RESET_AUDIENCE % (channel.name, channel.name, label) if cleared
                       else LEAD_AUDIENCE % label, 1)
        sminos.die(LEAD_RESET_ONLY % (channel.name, channel.name, machine, renamed[0]) if cleared
                   else LEAD_RENAMED % (machine, renamed[0]), 1)
    except (OSError, sminos.audience_module().StreamUnknown) as err:
        sminos.die("the lead of %s was not written%s: %s" % (
            channel.name, " (a clearing event was: it has no lead now)" if cleared else "", err), 1)
    sminos.nudge_daemon()
    if e["seq"] is None:
        print(sminos.waits_line(channel, e["writer"]))
        return 0
    if row is None:
        print(NO_LEAD % channel.name)
        return 0
    print(LEADS % (label, channel.name))
    if not row[1].local:
        print(LEAD_ELSEWHERE % row[1].machine)
    if audience is not None:
        print(LEAD_PRIVATE)
    return 0


# ------------------------------------------------------------ what a channel owes a thread (CH2's M2; its §3)
#
# In a channel a message is owed to a thread, by its thread id (the `thread` of an entry of its `to`), and never
# by a session: one delivery record and one delivery lock a thread there, `delivered/<thread id>.json` and
# `.lock`, whatever session the thread holds. The selection applies where the membership began itself, so
# nothing is written into a delivery record when a membership begins, ends, returns or changes session, and a
# thread whose record does not hold the channel is owed nothing from it. Nothing here pushes: the delivery
# operation (M3) takes its choice from owed().


class Debt(NamedTuple):
    """What the selection needs, read from the thread's record alone."""
    channel: object       # the channel's Project
    thread: str           # the thread the debt is owed to: the key of its delivery record and of its lock
    session: str          # the session its record names as current when this was read
    boundary: dict        # where its membership began (began_of), as read then


class Owing(NamedTuple):
    """A Debt's four fields, and what a push needs beside them."""
    channel: object
    thread: str
    session: str          # where a push or a wake goes
    boundary: dict
    project: object       # the thread's own project: where its membership is read
    member: object        # its row there: what the delivery operation takes as `member`
    reach: object         # reach_token(session) as read then: None for a session with no record


def debt(channel, record):
    """The thread's Debt in the channel, from the record given and nothing
    else: no view, no reconciliation, no lock, no write. None when the
    record has ended, holds no session, or does not hold the channel. An
    open entry hides no debt (owing() is where it stops a delivery)."""
    threads = sminos.threads_module()
    if record is None or threads.record_ended(record) or not record.get("current") \
            or channel.id not in threads.held_set(record):
        return None
    return Debt(channel, record["thread"], record["current"], _boundary(record, channel.id))


def _session_read(session):
    """(defers, reach token) of the session's record, read one way wherever
    eligibility is decided (owing, still_owed), as CH1's last guard reads it
    (sminos_threads._last_reads): one that is not there (FileNotFoundError
    alone) is lane A and does not defer, its token None; one that is there
    and cannot be read defers, as lane B does."""
    records = sminos.records_module()
    rec = records.read(session)
    if rec is None:
        return not _gone(records.record_path(session)), None
    return records.lane_of(rec) == "B", _token(rec)


def owing(channel, record, row):
    """debt(), then what a push needs: an Owing, or None. Reads only, and
    looks no row up: `row` is (the thread's own project, its Member there),
    given by the caller, and None for it is None. None also while the
    record holds an open journal entry (`pending`, whatever its operation:
    its current session is not settled yet) and while the session's record
    defers (_session_read)."""
    d = debt(channel, record)
    if d is None or row is None or record.get("pending"):
        return None
    defers, token = _session_read(d.session)
    if defers:
        return None
    project, member = row
    return Owing(d.channel, d.thread, d.session, d.boundary, project, member, token)


def _count(x):
    return type(x) is int and x >= 0


def _seq_pair(x, second):
    return isinstance(x, list) and len(x) == 2 and type(x[0]) is int and second(x[1])


def whole_entry(v):
    """Whether a writer's entry is one its writers write (sminos._entry, in
    the form _delivered_write puts on disk): `settled` and `attempts`
    counts, `pending` a seq or null, all three always there; and, when
    there, `revoked` a list of seqs, `held` a list of [seq, thread] pairs,
    `pushed` [seq, one of PUSHED]. Anything else is no entry whose settled
    prefix and marks can be known: the projects' loader passes such a mark
    by, which here would drop a revocation or a hold."""
    if not (isinstance(v, dict) and _count(v.get("settled")) and _count(v.get("attempts")) and "pending" in v
            and (v["pending"] is None or type(v["pending"]) is int)):
        return False
    if "revoked" in v and not (isinstance(v["revoked"], list) and all(type(s) is int for s in v["revoked"])):
        return False
    if "held" in v and not (isinstance(v["held"], list)
                            and all(_seq_pair(x, lambda t: isinstance(t, str) and t) for x in v["held"])):
        return False
    return "pushed" not in v or _seq_pair(v["pushed"], lambda o: o in sminos.PUSHED)


def _whole(d):
    """Whether a delivery record's JSON is a whole one: an object of writer
    entries, each whole (whole_entry); {} is an empty record."""
    return isinstance(d, dict) and all(whole_entry(v) for v in d.values())


def delivered(channel, thread):
    """The thread's delivery record under the channel, read strictly: {} when
    no file is there; None when one is there and cannot be read or is no
    whole record (_whole): neither empty nor settled, so nothing owed is
    claimed for that thread. sminos.delivered_load, which answers {} to
    both, is left for projects."""
    path = os.path.join(channel.home, "delivered", thread + ".json")
    try:
        d = sminos.json_at(path)
    except FileNotFoundError:
        return {} if _gone(path) else None   # a link to nothing is there, and cannot be read
    except (OSError, ValueError):
        return None
    return sminos.delivered_entries(d) if _whole(d) else None


def _names_a_thread(e):
    to = e.get("to")
    if not isinstance(to, list) or "copy" in e or e["writer"].startswith("legacy/"):
        return ()
    return tuple(dict.fromkeys(r["thread"] for r in to
                               if isinstance(r, dict) and isinstance(r.get("thread"), str) and r["thread"]))


def _addressed(events):
    out = {}
    for e in events:
        for t in _names_a_thread(e):
            out.setdefault(t, []).append(e)
    return out


def addressed_threads(events):
    """{thread id: the events whose `to` names it, in the log's order}: the
    part of a channel's log owed() reads for each thread, read once for all
    of them and once for a log that has not moved (sminos.log_memo; read it,
    never change it). An entry with no `thread`, or one that is no string,
    names no one; a copy is owed to no one."""
    return sminos.log_memo(events, "thread-addressees", _addressed)


def owed(d, events, record=None):
    """THE selection, and the only one, of a Debt or an Owing: the events of
    the channel's log (`events`, its merged list), in the log's order, each
    once, an entry of whose `to` names d.thread, that lie past d.boundary
    for their writer, and are neither settled nor revoked in the thread's
    delivery record (`record`, or delivered() read here). An event the
    thread itself wrote (its own `thread`) is none. None when the delivery
    record cannot be read: nothing is claimed. Given the shared merged log
    (sminos._store_whole's, as a deliverer reads it), the index by thread is
    built once for every thread asked about."""
    if record is None:
        record = delivered(d.channel, d.thread)
        if record is None:
            return None
    out = []
    for e in addressed_threads(events).get(d.thread, ()):
        if e.get("thread") == d.thread or not _past(e, d.boundary):
            continue
        w = sminos._delivery(record, e["writer"])
        if e["seq"] > w["settled"] and e["seq"] not in w.get("revoked", ()):
            out.append(e)
    return out


def _past(e, boundary):
    held = boundary.get(e["writer"])
    return e["seq"] > (held if type(held) is int else 0)


def first_owed(d, writer, events):
    """owed()'s first event of `writer`, or None."""
    return next((e for e in owed(d, events) or () if e["writer"] == writer), None)


def still_owed(o, e=None, reach=False):
    """The last check, on files as they are (a deliverer makes it holding the
    thread's delivery lock), by the reads of CH1's last guard
    (sminos_threads._last_reads): o.thread's own file reads, has not ended,
    holds no open entry, holds the channel and names o.session as current;
    the session's current record read afresh is that thread's and holds no
    open entry; the session's record does not defer (_session_read); its
    own events in o.project leave it a member there, and o.project is where
    it is now (sminos._current_here: literal paths, a tie for neither);
    with `reach`, its reach token is still o.reach; and, given `e`, the
    event lies past the boundary as it is now. False settles nothing."""
    threads = sminos.threads_module()
    t = threads.get(o.thread)
    if t is None or threads.record_ended(t) or t.get("pending") or o.channel.id not in threads.held_set(t) \
            or t["current"] != o.session:
        return False
    now = threads.current_record(o.session, fresh=True)
    if now is None or now["thread"] != o.thread or now.get("pending"):
        return False
    defers, token = _session_read(o.session)
    if defers or (reach and token != o.reach):
        return False
    own = sminos.own_events_now(o.project, o.session)
    if not threads.member(own) or not sminos._current_here(o.session, o.project, threads.in_effect(own)):
        return False
    return e is None or _past(e, _boundary(t, o.channel.id))


def owed_here(channel):
    """What `daemon owed` counts for a channel: (Debt, its owed events, or
    None where its delivery record cannot be read) for each thread of this
    machine that holds the channel (sminos_threads.set_holders: records that
    read alone), from debt(), delivered() and the log: no Member, no view,
    no lock, no write."""
    holders = [t for t in sminos.threads_module().set_holders().values() if debt(channel, t) is not None]
    if not holders:
        return []
    _, events = sminos._store_whole(channel, "log", shared=True)   # read, never changed: its index is kept with it
    out = []
    for t in sorted(holders, key=lambda t: t["thread"]):
        d = debt(channel, t)
        out.append((d, owed(d, events)))
    return out


# ------------------------------------------------------------ pushing and waking from a channel's log (CH2's M3)
#
# The delivery operation (sminos.deliver_next, deliver_verdict, deliver_reach) takes a channel's log with an Owing,
# and only so: the thread's delivery lock and record, the thread's selection (owed), the session for every process,
# the thread's own project for membership. What is here chooses whom to give it to, and keeps the record
# consistent with the boundary.


def own_row(record):
    """(the thread's own project, its row there), or None: the project the
    thread's current session is a member of now (_project_now), never a
    channel, and its row read without a reconciliation (sminos.member_row):
    what finishes a thread's open entry is the daemon's tick of its
    project, never a channel's pass for another thread."""
    session = (record or {}).get("current")
    project = _project_now(session) if session else None
    if project is None:
        return None
    member = sminos.member_row(project, session)
    return (project, member) if member is not None else None


def _project_now(session):
    """The project the session is a member of now, by its own membership
    events of this machine in every project's files, read under their
    literal paths (sminos.registration_paths, as the last check's
    _current_here reads them: a home whose path holds a glob's bracket is
    read as any other): the project of the newest one in effect when it is
    a `joined`; for a `retired` `moved`, its destination when the session's
    `joined` there is in effect (a dual membership of one tick); else
    None. A channel is no session's project."""
    threads = sminos.threads_module()
    identity = sminos.machine_identity_now()
    best, at = None, ""
    for path in sminos.registration_paths():
        pid = os.path.basename(os.path.dirname(path))
        p = None if sminos.is_channel_id(pid) else sminos.known_project(pid)
        last = threads.in_effect(sminos._own_events(p, session, identity=identity)) if p is not None else None
        if last is not None and str(last.get("ts") or "") >= at:
            best, at = (p, last), str(last.get("ts") or "")
    if best is None or best[1]["kind"] == "joined":
        return best and best[0]
    dest = str(best[1].get("project") or "") if best[1].get("reason") == "moved" else ""
    # A synced event's `project`: checked as a name before any lookup reads a path built from it.
    p = sminos.known_project(dest) if dest and sminos.valid_name(dest) and not sminos.is_channel_id(dest) else None
    last = threads.in_effect(sminos._own_events(p, session, identity=identity)) if p is not None else None
    return p if last is not None and last["kind"] == "joined" else None


def normalize(o):
    """The thread's delivery record made consistent with its boundary, under
    its delivery lock and after still_owed: a writer's `pending` whose seq is
    at or below the boundary read afresh for that writer (the thread's own
    file) is cleared, with the attempt count and the pushed note that ride
    with it, in one write. That is the only evidence: a `pending` whose event
    the selection merely does not hold (a writer file that could not be read)
    stays. The settled prefix, the revoked seqs and the held marks are as
    they were. Without it a failed attempt on an event a removal and an add
    (or a return) put below the boundary would stop its writer for good
    (sminos._next_check). Nothing over a record that cannot be read."""
    record = delivered(o.channel, o.thread)
    t = sminos.threads_module().get(o.thread)
    if not record or t is None:
        return
    boundary = _boundary(t, o.channel.id)
    cleared = {}
    for w, entry in record.items():
        if entry["pending"] is not None and not _past({"writer": w, "seq": entry["pending"]}, boundary):
            cleared[w] = {k: v for k, v in entry.items() if k != "pushed"}
            cleared[w].update(pending=None, attempts=0)
    if cleared:
        record.update(cleared)
        sminos._delivered_write(o.channel, o.thread, record)


def deliver(channel):
    """The channel's delivery pass, (events delivered, the aliases reached):
    the daemon's channel pass, last, after the view and carry_due (a request
    honoured in the tick has set its boundary first). For each thread of this
    machine that holds the channel (sminos_threads.set_holders) and that the
    log names (addressed_threads, the log's own index: a thread nothing names
    is passed by with no lock and no record read), owing() with own_row(),
    and sminos.deliver_next(channel, o.member, owing=o) when owed() is not
    empty. A thread whose record holds an open entry is passed by (what
    finishes entries is the daemon's reconciliation of projects, never this
    pass; own_row reads no view, so no other thread's pass finishes one). A
    thread whose whole backlog was held for a fact is passed by on the memory
    of a full pass while nothing it read has changed (the daemon's
    _HELD_PASSES, the projects' memory, keyed by the channel and the thread).
    A machine that holds no member of the channel reads nothing of its log,
    and forgets what it remembered of the channel's passes."""
    threads = sminos.threads_module()
    holders = [t for t in threads.set_holders().values() if channel.id in threads.held_set(t)]
    daemon = sminos.daemon_module()
    if not holders:
        daemon.held_pass_forget(channel.id, set())   # what a pass remembered holds the merged log it read
        return 0, []
    events = sminos._store_whole(channel, "log", shared=True)[1]   # read, never changed: its index is kept with it
    index = addressed_threads(events)
    total, reached, present = 0, [], set()
    for t in sorted(holders, key=lambda t: t["thread"]):
        if t["thread"] not in index:
            continue
        key = (channel.id, t["thread"])
        present.add(key)
        session = t["current"]
        held = sminos.hold_for(session)
        reads = daemon.channel_held_reads(channel, events, t["thread"], session) if held else None
        if daemon.held_pass_skips(key, reads):
            continue
        d = debt(channel, t)
        if d is None or t.get("pending"):
            continue
        chosen = owed(d, events)
        if not chosen:
            continue
        o = owing(channel, t, own_row(t))
        if o is None:
            continue
        try:
            result = sminos.deliver_next(channel, o.member, owing=o)
        except sminos.DeliveryUnreadable as e:
            sminos.daemon_log("delivery: %s" % e)
            continue
        if held and daemon.all_held(result, chosen):
            # The delivery record as the pass left it: its own write is the hold it decided.
            daemon.held_pass_keep(key, reads, daemon.channel_held_reads(channel, events, t["thread"], session))
        if result["delivered"]:
            total += result["delivered"]
            reached.append(o.member.alias)
    daemon.held_pass_forget(channel.id, present)
    return total, reached


# ------------------------------------------------------------ asking the endpoint, and carrying its word out (CH2's M6)
#
# The uplink asks about a channel's messages and keeps each answer in a file (asks_due, keep_word); the daemon's
# channel pass carries it out (carry_words), in a process of its own: nothing a channel's message causes on the
# uplink's consumer thread pushes, launches or waits on a lock without a bound (the plan's §4).

WORD_KEPT = 60   # seconds within which a kept word may begin to be carried out (§4: what the endpoint's word is good for)
WORDS_DIR = "words"   # under a channel's home: the kept words, <thread>.<ask id>.json, each created whole


def word_key(o, e):
    """What a kept word is remembered under by the uplink (Link.words_kept)
    and passed over by asks_due while it is good: the channel, the thread,
    the session and the reach it was asked for, and the event (writer, seq,
    hash). A hand-off or a change of reach makes another key, so the event
    is asked about again at once, for the session and the reach as they are
    then."""
    return (o.channel.id, o.thread, o.session, o.reach, e["writer"], e["seq"], sminos.event_hash(e))


def asks_due(channel, rows, kept=()):
    """The uplink's choice of what to ask the endpoint about a channel's
    messages, [(Owing, event, "words?" | "reach?")]: reads only, and no lock
    waited for. `rows`: {session: (Project, Member)} as the plane holds them.
    For each thread of this machine in the channel (set_holders) that the
    log names: one whose session `rows` does not hold is passed by before
    owing() is asked (owing looks no row up, so nothing here reaches a
    view); else owing() with that row, and the first owed event of each
    writer by the thread's selection, as sminos.words_due and reach_due
    choose for a project given the Owings (a held session asked nothing; an
    outside event on a read-only machine, one noted pushed, a recipient
    whose record cannot be read, none), less one whose word_key is in
    `kept`. "words?" where words_route says ask, else "reach?" where the
    reach gate needs the endpoint's word. An event a receipt is held for is
    planned with the receipts' lock only tried (reach_due: a busy one leaves
    it for a later pass), and asked about when sminos.holder_due says it is
    next pushed."""
    threads = sminos.threads_module()
    holders = [t for t in threads.set_holders().values() if channel.id in threads.held_set(t)]
    if not holders:
        return []
    events = sminos._store_whole(channel, "log", shared=True)[1]   # read, never changed: its index is kept with it
    index = addressed_threads(events)
    owings = {}
    for t in sorted(holders, key=lambda t: t["thread"]):
        session = t.get("current")
        if t["thread"] not in index or session not in rows:
            continue   # nothing names it; or the plane holds no row for its session yet: asked after its next read
        o = owing(channel, t, rows[session])
        if o is not None:
            owings[session] = o
    if not owings:
        return []
    out = []
    for kind, due in (("words?", sminos.words_due(channel, [], owing=owings)),
                      ("reach?", sminos.reach_due(channel, [], owing=owings))):
        for session, es in sorted(due.items()):
            o = owings[session]
            out.extend((o, e, kind) for e in es if word_key(o, e) not in kept)
    return out


def _words_dir(channel_id):
    return os.path.join(sminos.root(), "projects", channel_id, WORDS_DIR)


def keep_word(channel_id, thread, ask, word):
    """The uplink's one write for a channel's answer: `word` (§4's fields:
    kind, verdict, reason, thread, session, reach, writer, seq, hash, at) as
    projects/<channel id>/words/<thread>.<ask>.json, created whole (written
    aside, then renamed into place) and never rewritten, its path built from
    the ids alone: no registration read, no lock. The path."""
    d = _words_dir(channel_id)
    os.makedirs(d, mode=0o700, exist_ok=True)
    path = os.path.join(d, "%s.%s.json" % (thread, ask))
    tmp = os.path.join(d, ".%s.%s.%d.tmp" % (thread, ask, os.getpid()))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(word, f, sort_keys=True)
    os.replace(tmp, path)
    return path


def _as_kept(x):
    """A value as a kept word's JSON holds it (a reach token's tuples are lists there)."""
    return json.loads(json.dumps(x))


def _read_word(path):
    try:
        with open(path, encoding="utf-8") as f:
            w = json.load(f)
    except (OSError, ValueError):
        return None
    if not (isinstance(w, dict) and w.get("kind") in ("reach", "words") and isinstance(w.get("thread"), str)
            and isinstance(w.get("session"), str) and isinstance(w.get("writer"), str) and type(w.get("seq")) is int
            and isinstance(w.get("at"), (int, float)) and isinstance(w.get("verdict"), str)):
        return None
    return w


def take_word(o, e, path, verdict):
    """A kept word taken by the one that carries it out, under the thread's
    delivery lock (sminos.deliver_verdict, deliver_reach): its file read
    again and removed; the word when it was still there, is younger than
    WORD_KEPT, names o.thread, o.session and o.reach, the event `e` (its
    writer, seq and hash) and `verdict`; else None, and nothing is to be
    done on it. A second carrier of the same word finds no file."""
    w = _read_word(path)
    try:
        os.unlink(path)
    except OSError:
        return None   # gone: another carrier took it
    if w is None or not 0 <= time.time() - w["at"] < WORD_KEPT:
        return None
    if (w["thread"], w["session"], w.get("reach")) != (o.thread, o.session, _as_kept(o.reach)) \
            or (w["writer"], w["seq"], w.get("hash")) != (e["writer"], e["seq"], sminos.event_hash(e)) \
            or w["verdict"] != verdict:
        return None
    return w


def carry_words(channel):
    """The daemon's channel pass, before deliver: the kept words of the
    channel carried out, taking no delivery lock itself. For each thread
    with kept words, oldest first: one older than WORD_KEPT, one whose
    thread has no owing() now (with own_row(); an open entry, an end, a
    removal, a lane that defers), and one whose event is no longer its
    writer's first owed with that body, are removed where they lie; each
    other is handed to sminos.deliver_reach or deliver_verdict with the
    Owing and its path, which takes the thread's lock once and there reads
    the word again, checks it and removes it (take_word). How many were
    carried out."""
    d = _words_dir(channel.id)
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return 0
    by_thread = {}
    for name in names:
        if name.startswith(".") or not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        w = _read_word(path)
        if w is None or name[:-len(".json")].rpartition(".")[0] != w["thread"]:
            _drop(path)   # no word of this code's
            continue
        by_thread.setdefault(w["thread"], []).append((w["at"], path, w))
    if not by_thread:
        return 0
    threads = sminos.threads_module()
    events = sminos._store_whole(channel, "log", shared=True)[1]
    carried = 0
    for thread in sorted(by_thread):
        t = threads.get(thread)
        o = owing(channel, t, own_row(t)) if t is not None and not t.get("pending") else None
        for at, path, w in sorted(by_thread[thread], key=lambda x: (x[0], x[1])):
            if o is None or not 0 <= time.time() - at < WORD_KEPT:
                _drop(path)
                continue
            e = first_owed(o, w["writer"], events)
            if e is None or e["seq"] != w["seq"] or sminos.event_hash(e) != w.get("hash"):
                _drop(path)
                continue
            try:
                if w["kind"] == "reach":
                    outcome = sminos.deliver_reach(channel, o.member, e, w["verdict"], w.get("reason"), owing=o,
                                                   word=path)
                else:
                    outcome = sminos.deliver_verdict(channel, o.member, e, w["verdict"], owing=o, word=path)
            except sminos.DeliveryUnreadable as err:
                sminos.daemon_log("delivery: %s" % err)
                continue
            if outcome is not None:
                carried += 1
    return carried


def _drop(path):
    try:
        os.unlink(path)
    except OSError:
        pass


UNSENT_KINDS = sminos.CHAT_KINDS + ("channel-lead",)   # what keeps a channel's log open until it has gone up


def unsent(channel):
    """Whether this machine's writers hold in the channel's log a message (a
    `say` or a `human`) or a lead (`channel-lead`, a clearing one included:
    CH2's M8, which a machine with no member writes too) the upstream has
    not taken (past the channel's
    `uplink-taken.json`, as `daemon owed` counts `upload`), or a queued one
    (`queued`): while either holds, a followed channel does not leave this
    machine, and one that left comes back (sminos_uplink.Link.may_leave),
    so what was said here goes up. Requests keep their own rule
    (outstanding). This machine's writers are those whose machine is
    exactly this one's, as HubLog.own reads them (`<host>.peer/…` is
    another machine's). A file it cannot read keeps the channel too."""
    hublog = sminos.sibling_module("sminos_hublog")
    for path in glob.glob(os.path.join(glob.escape(channel.home), sminos.QUEUED, "*.jsonl")):
        if any(e.get("kind") in UNSENT_KINDS for e in sminos.queued_events(path)):
            return True
    try:
        with open(os.path.join(channel.home, hublog.TAKEN_FILE), encoding="utf-8") as f:
            held = json.load(f)
    except FileNotFoundError:
        held = {}
    except (OSError, ValueError):
        return True
    if not isinstance(held, dict):
        return True
    taken = hublog.HubLog.seqs(held.get("taken"))
    machine = sminos.machine_name_now()
    prefix = machine.replace("/", ".") + "."   # the files to read; whose they are is the writer's exact machine
    log_dir = os.path.join(channel.home, "log")
    try:
        names = os.listdir(log_dir)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    for name in names:
        if not (name.startswith(prefix) and name.endswith(".jsonl")):
            continue
        path = os.path.join(log_dir, name)
        writer, last, _ = hublog.writer_and_last(path)
        if writer and writer.startswith(machine + "/") and last > taken.get(writer, 0) \
                and any(e["seq"] > taken.get(writer, 0) and e["kind"] in UNSENT_KINDS
                        for e in hublog.read_events(path)):
            return True
    return False
