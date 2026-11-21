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
"""
import os
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
    "expired": "not carried out: the request is more than seven days old",
    "not-here": "not carried out: it names a session that is no longer that thread's, or a thread that has ended",
}
# Why a thread's own add or remove was not recorded (change's `failed`), in `nothing was recorded (<why>)`.
OWN_FAILED = {
    "wake": "it is being woken",
    "entry": "its record holds an unfinished operation",
    "vacant": "the thread holds no session now",
    "between": "its session is between two projects",
    "moved": "this session is no longer its thread's current one, or the thread has ended",
    "unreadable": "the channel's log is there and could not be read",
}
CAPABILITY_REFUSAL = ("this machine's endpoint does not serve channels (its welcome listed no channels): nothing "
                      "was written")
LIMIT_REFUSAL = "%s is in 128 channels, the limit: nothing was written"
CARRIED = ("applied", "refused")   # the outcomes a write records; every other is said and writes nothing


def is_request(e):
    """Whether an event is a `channel-request` of §2's shape: `op` add or
    remove, and a `session`, a `thread` and an `id`, each a string that is
    not empty. A reader takes one that lacks any as no request."""
    return isinstance(e, dict) and e.get("kind") == "channel-request" and e.get("op") in ("add", "remove") \
        and all(isinstance(e.get(k), str) and e[k] for k in ("session", "thread", "id", "writer"))


def _logged_requests(events):
    return [e for e in events if is_request(e)]


def requests_of(channel):
    """(signature, requests): the ordered input of a carrying out (§6). The
    channel log's requests in the merged read's order, then those among this
    machine's queued appends for that log (an append that waits for its
    writer's head), in the queue's order, each with `seq` None, read without
    changing the queue; one whose writer and id the log holds already (a
    release cut short) once. The signature is of the files both were read
    from: a carrying out compares it at the record's write."""
    sig, events = sminos._store_whole(channel, "log", shared=True)
    logged = sminos.log_memo(events, "channel-requests", _logged_requests)
    queues = sminos.queued_operators(channel)
    keys = []
    for path in sorted(queues.values()):
        try:
            st = os.stat(path)
            keys.append((path, st.st_ino, st.st_size, st.st_mtime_ns))
        except OSError:
            keys.append((path, None))
    held = {(e["writer"], e["id"]) for e in logged}
    queued = [{**e, "seq": None} for e in sminos.said_order(queues) if is_request(e)
              and (e["writer"], e["id"]) not in held] if queues else []
    return (sig, tuple(keys)), [dict(e) for e in logged] + queued


def event_key(channel, request):
    """What a word of the endpoint's is asked and kept under (§6): the
    channel's id, the request's writer, its seq and its event hash, as a
    reach permit is keyed. A word answers the event it was asked about and
    no other request, whatever id that other carries."""
    return (getattr(channel, "id", channel), request.get("writer"), request.get("seq"), sminos.event_hash(request))


class _Facts:
    """What judge() reads beside the record, each from its file as it is
    when first asked (no value this process cached for its invocation: the
    machine's identity and enrollment, the policy, the kept capabilities,
    the revocation set, the session records), taking no lock and writing
    nothing (§3). One evaluation's: a fact asked twice in it reads once."""

    def __init__(self):
        self._ident = ()
        self._current = {}

    def current_record(self, session):
        """The record whose current session `session` is, from the stores as they are."""
        if session not in self._current:
            self._current[session] = sminos.threads_module().current_record(session, fresh=True)
        return self._current[session]

    def ident(self):
        if self._ident == ():
            self._ident = sminos.sibling_module("sminos_rl10").cutover()
        return self._ident

    def name(self):
        ident = self.ident()
        return ident["name"] if ident is not None else sminos.machine_name_now()

    def is_self(self, name, session=""):
        ident = self.ident()
        former = ident["former"] if ident is not None else {}
        return name == self.name() or (bool(session) and session in former.get(name, ()))

    def outside_origin(self, e):
        """policy.outside_origin, by this machine's identity read now."""
        writer = str(e.get("writer") or "")
        head = writer.rpartition("/")[0]
        return not (head and self.is_self(head, sminos.writer_session(writer)))

    def own_writers_here(self, channel):
        """sminos.own_writers_here, by the enrollment read now."""
        if channel is None or channel.remote:
            return False
        if channel.hub is not None:
            ident = self.ident()
            return ident is not None and channel.hub.get("org") == ident["org"]
        return True

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
        """Row 10: the request's writer is this machine's own, in a log where
        its name is provenance, and shares the thread's owners: a session's
        writer by sminos.same_owner_local's rule, the human writer by
        sminos.owners_meet("", session); this machine's name read now."""
        if not self.own_writers_here(channel):
            return False
        writer = str(e.get("writer") or "")
        head, _, tail = sminos.writer_base(writer).rpartition("/")
        if head != self.name():
            return False
        if tail == "human":
            return sminos.owners_meet("", session)
        sender = sminos.writer_session(writer)
        records, au = sminos.records_module(), sminos.audience_module()
        if not sender or tail != sender or not (au.is_local(sender) and au.is_local(session)):
            return False
        a, b = records.read(sender), records.read(session)
        oa, ob = (a or {}).get("owners"), (b or {}).get("owners")
        return isinstance(oa, list) and isinstance(ob, list) and bool(oa) and set(oa) == set(ob)


def sender_verified(channel, request, facts=None):
    """Whether the request's sender is held as verified (C3): True for a
    writer of this machine in a log where its name is provenance
    (own_writers_here). Else from the key an import stores on the event,
    `verified`: False when it is no object or its signer is none or of kind
    `legacy`; None while the revocation set cannot be read; False when the
    set names the signer; else True."""
    facts = facts or _Facts()
    writer = str(request.get("writer") or "")
    if facts.own_writers_here(channel) and facts.is_self(sminos.writer_base(writer).rpartition("/")[0],
                                                         sminos.writer_session(writer)):
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
    now (read from the stores as they are), and the thread's session is not
    lane B."""
    threads = sminos.threads_module()
    if record is None or record["thread"] != request["thread"] or threads.record_ended(record):
        return False
    session = request["session"]
    if session != record["current"] and session not in record["sessions"]:
        return False
    other = facts.current_record(session)
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
    outside = facts.outside_origin(request)
    if outside and not facts.serves_channels():
        return Outcome("pending", "no-channels")
    if outside and facts.read_only():
        return Outcome("refused", "read-only")
    if not facts.shares_owners(channel, request, current):
        verified = sender_verified(channel, request, facts)
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


def carry_out(channel, request, word=None, asked=None, lock_until=None, wake_until=None):
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
    is given: a command waits as a transition does)."""
    threads = sminos.threads_module()
    cid, tid = channel.id, request["thread"]
    why = "moved"
    for _ in range(3):
        sig, requests = requests_of(channel)
        earlier = _earlier(requests, request)
        record = threads.get(tid)
        if record is not None and record.get("pending") and not threads.reservation(record) \
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
            if requests_of(channel)[0] != sig:
                said.append("input")
                return None
            out = judge(channel, request, rec, earlier, word, asked, project)
            said.append(out)
            if out.state not in CARRIED:
                return None
            chans = list(threads.stated_set({"channels": threads.held_set(rec)}))
            if out.state == "applied" and out.why != "unchanged":
                chans = chans + [cid] if request["op"] == "add" else [c for c in chans if c != cid]
            return {"project": project, "session": rec["current"], "channels": chans,
                    "answer": {"channel": cid, "id": request["id"], "ts": request["ts"], "result": out.state,
                               "reason": out.why if out.state == "refused" else ""}}
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
                sminos.finish_thread(tid, project=project, lock_until=lock_until)
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
        # The Change was refused by set_channels' last guard: the session is no member of `project` now.
        sminos.forget_caches()
        again = sminos.last_project(record["current"])
        if getattr(again, "id", None) == getattr(project, "id", None):
            return Outcome("pending", "between")
        why = "between"
    return Outcome("pending", why)


def carry_due(channel, words=None, also=(), lock_until=None, wake_until=None):
    """The pass (§6): every request of the ordered input that is not expired
    and names a thread of this machine that has not ended, in order, then
    the requests of `also` it does not hold (a command's own, in hand), each
    through carry_out; a request its thread's record has answered already
    is passed by (judge's row 4, read from the record without a lock: it
    writes nothing either way), and a request pending leaves the later ones
    for its thread pending `earlier`. `words`: {event_key: (word, asked)}.
    [(request, Outcome)] of the requests carried."""
    threads = sminos.threads_module()
    words = words or {}
    _, requests = requests_of(channel)
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
        got = carry_out(channel, r, word, asked, lock_until=lock_until, wake_until=wake_until)
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
        s = found[1]
        return _local(threads.get(s["seat_id"]), found[2] or s["current"], s["alias"])
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


def _answered_line(op, channel, target):
    """A request this command wrote that its thread's machine answered first
    (the daemon's pass, between the append and the command's own): what the
    record holds now. (line, whether it says what was asked)."""
    threads = sminos.threads_module()
    held = channel.id in threads.held_set(threads.get(target.thread))
    if op == "add":
        return ("in %s" % channel.name, True) if held else (
            "not in %s: its machine answered the request first and refused it" % channel.name, False)
    return ("out of %s" % channel.name, True) if not held else (
        "still in %s: its machine answered the request first" % channel.name, False)


def place(channel, op, targets, session):
    """Each target added to or removed from the channel (§8): the caller's
    own thread by a statement alone (change), any other by a request
    written into the channel's log under the caller's writer there (the
    stream sminos.stream_choice gives for that one recipient; the
    machine's human writer from a terminal) and, for a thread of this
    machine, carried out at once from the request in hand (carry_due, which
    carries the channel's other due requests too). [(target, outcome or
    None, line)] in the targets' order, a target named twice once, and
    whether any was refused or could not be recorded."""
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
        choice, refusal = sminos.stream_choice(channel, session, [{"session": t.session, "alias": t.alias}],
                                               "the request for %s" % t.label)
        if refusal:
            rows.append([t, None, "refused: not reachable: %s" % refusal[0]])
            bad = True
            continue
        writer, audience, _, _ = choice[0]
        sminos.keep_stream(channel, writer, audience)
        try:
            e = sminos.log_append(channel, writer, "channel-request", op=op, session=t.session, thread=t.thread,
                                  id=uuid.uuid4().hex)
        except OSError as err:
            sminos.die("the request for %s could not be written in %s's log: %s" % (t.label, channel.name, err), 1)
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
                    row[2], ok = _answered_line(op, channel, row[0])
                    bad = bad or not ok
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


def _print_rows(rows):
    for t, _, line in rows:
        print("%s: %s" % (t.label, line))


def cmd_channel(a):
    """`sminos channel create|add|remove` (§8): refused before anything is
    written where the kept welcome lists no `channels`."""
    if not sminos.audience_module().advertised("channels"):
        sminos.die(CAPABILITY_REFUSAL, 1)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if a.channel_op == "create":
        sys.exit(_create(a.name, a.thread, session))
    channel = find_channel(a.channel)
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
    back = None
    if named:
        if len(named) == 1 and sminos.is_channel_id(named[0].id) and _memberless(named[0]):
            back = named[0]
        else:
            sminos.die("cannot create channel %s: %s already answers to that name — name it otherwise: nothing was "
                       "written" % (name, ", ".join(sorted(map(sminos.log_label, named)))), 1)
    if back is None:
        cid = mint_channel_id()
        try:
            channel = register(cid, name)
        except ValueError as e:
            sminos.die("cannot create channel %s: %s" % (name, e), 1)
    else:
        channel = back
    rows, bad = place(channel, "add", [first], session)
    t, outcome, line = rows[0]
    done = isinstance(outcome, Outcome) and outcome.state == "applied"
    if back is None:
        print("created channel %s (%s)%s" % (channel.name, channel.id, " with %s" % t.label if done else ""))
    else:
        print("%s exists and has no member%s" % (channel.name, ": %s is in it again" % t.label if done else ""))
    if not done:
        print("%s: %s" % (t.label, line))
    return 1 if bad else 0
