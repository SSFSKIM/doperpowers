#!/usr/bin/env python3
"""sminos_outcomes — what became of each event from outside this machine
that delivery settled (DC7 of the desk; DX4's `delivery`).

`deliver_next` is the one boundary every delivery passes, whichever process
runs it (the uplink's immediate delivery, the daemon's tick and its retries,
a sender's fast path). When it settles an event written outside this machine
(sminos_policy.outside_origin) for a recipient of a hub project, it records
the outcome here, in the project's `outcomes.jsonl`, before the settlement:

    {"event": {"writer", "seq"}, "session", "outcome", "reason"}

`outcome` is DX4's (composite 6fa2252d): `delivered` (pushed to the live
session, or the stopped seat resumed with it), `uncertain` (the frame was
written and no answer came: settled, never pushed again), `recorded` (the
recipient was not running and is pushed nothing), `refused-read-only` (the
machine's policy), `failed` (given up after DELIVERY_ATTEMPTS); on a machine
cut over to its endpoint (RL10, O12 M6) also `refused-words` (the endpoint
refused a person's words into the session) and `refused-revoked` (the
event's signer was revoked: it is marked, never delivered, and settles in
order, sminos.delivered_revoke). An owner's
event is pushed through the session's bridge, whose later refusal follows as
below; a peer's is written to the session's inbox socket, which answers
nothing more: its `delivered` says the frame was written, and the engine's
own gate may still hold it for its user's approval (a session that bypasses
permission prompts holds a peer message that asserts no permission mode, as
sminos's frame does) or drop it (its per-sender rate limit), unreported. An
outcome that cannot be written leaves the event unsettled, so it is recorded
again later — a push made is noted, so not made twice (sminos.deliver_next);
a crash between the push and the settlement pushes and records it again. The
hub keeps the latest per event and recipient.

One outcome comes without a settlement: an event owed to a closed terminal
session (a stopped thread this machine holds, T2's §4; or
a seat-less session of this machine whose membership ended with its process)
is reported `recorded` once, when it first becomes owed to it
(report_closed; a held thread's after its delivery pass, report_held, the
reason its hold in T2's §5 words), and stays owed; if the session comes back (Resume) and the
event is delivered, `delivered` follows for the same key. Delivery pushes a
held session nothing and leaves what it holds owed, and never reaches a
session whose membership ended: on a read-only machine the report applies
the policy itself, settling what is owed to it from outside undelivered as
`refused-read-only`, as deliver_next would. What was reported
is kept per session in the project's `recorded/<session>.json` ({writer: the
last seq reported}).

A second outcome comes for a delivery the session's engine dropped after its
bridge answered `submitted` (DC8.G5): `delivered` says the text entered the
session's queue, not that it was taken in, and the bridge reports the drop
later, which its child keeps (`refused` in its kept file). The daemon's
delivery pass reports each once as `failed` with the bridge's reason
(report_refused), after the first outcome for the same key and session.

The uplink drains the file: it sends each record as DX4 `delivery`
(`message`) and drops what was written to the endpoint.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

OUTBOX = "outcomes.jsonl"
READ_ONLY = "refused-read-only"
REFUSED_WORDS = "refused-words"       # the endpoint's verdict on a person's words: refuse (O12 M6)
REFUSED_REVOKED = "refused-revoked"   # signed by a key, device or member since revoked (O12 M6)
REFUSED_REACH = "refused-reach"       # the endpoint's `reach` answer: refuse (P5 O18 D3); settled here, never reported
# What is known of an uncertain push: the frame was written, and no answer came; never that the session took it.
UNCERTAIN = {"sent?": "uncertain: the message was written to the session, and no answer came to say it took it",
             "woken?": "uncertain: the stopped session was woken and the message written to it, and no answer came "
                       "to say it took it"}


def of_push(push, member):
    """(DX4 outcome, reason) for what delivery made of an event: a push's
    outcome (sminos.push_event's), or READ_ONLY for one the policy refused."""
    if push == READ_ONLY:
        return READ_ONLY, "this machine is read-only: nothing written outside it is delivered"
    if push == REFUSED_WORDS:
        return REFUSED_WORDS, "the endpoint refused it as words into this session: nothing was delivered"
    if push == REFUSED_REVOKED:
        return REFUSED_REVOKED, "its signer's key, device or member was revoked: it is never delivered"
    if push == "sent":
        return "delivered", "pushed to the live session"
    if push == "woken":
        return "delivered", "the stopped session was woken with it"   # a seat's or one its human opened (T2's §4)
    if push in UNCERTAIN:
        return "uncertain", UNCERTAIN[push]
    if push.startswith("failed"):
        return "failed", "given up after %d attempts: %s" % (sminos.DELIVERY_ATTEMPTS, push[len("failed:"):])
    if member.seat is None:
        return "recorded", ("the session is not running here (closed, or its membership ended): it is pushed "
                            "nothing, and reads the log when it is back")
    return "recorded", "the seat is not live and was not resumed for it (retired, holding another session, or an @all)"


class Outbox:
    """One project's outcomes not yet posted."""

    def __init__(self, project):
        self.project = project

    @property
    def path(self):
        return os.path.join(self.project.home, OUTBOX)

    def lock(self):
        return sminos.flocked(sminos.project_path(self.project, OUTBOX + ".lock"))

    def record(self, e, session, outcome, reason):
        line = json.dumps({"event": {"writer": e["writer"], "seq": e["seq"]}, "session": session,
                           "outcome": outcome, "reason": reason}, ensure_ascii=True) + "\n"
        with self.lock():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(line)

    def take(self):
        """(the records waiting, oldest first; how many lines they took): a
        line that is no record is counted and skipped, so `drop` takes it too."""
        try:
            with open(self.path) as f:
                lines = f.read().split("\n")[:-1]
        except OSError:
            return [], 0
        out = []
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
        return out, len(lines)

    def read(self):
        return self.take()[0]

    def waiting(self):
        """Whether anything waits, without reading it."""
        try:
            return os.path.getsize(self.path) > 0
        except OSError:
            return False

    def drop(self, n):
        """The first `n` lines were posted: they go. Lines appended meanwhile stay."""
        if n <= 0:
            return
        with self.lock():
            try:
                with open(self.path) as f:
                    lines = f.read().split("\n")[:-1]
            except OSError:
                return
            rest = lines[n:]
            tmp = "%s.%d.tmp" % (self.path, os.getpid())
            with open(tmp, "w") as f:
                f.write("".join(line + "\n" for line in rest))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)


def record(project, e, session, push, member):
    """Delivery's record of an outside-origin event settled for `session`,
    for a hub project (nothing for another): whether it is kept. One that
    cannot be written is said in daemon.log and returns False — the caller
    does not settle the event."""
    if not project.hub:
        return True
    outcome, reason = of_push(push, member)
    try:
        Outbox(project).record(e, session, outcome, reason)
    except OSError as err:
        sminos.daemon_log("delivery: the outcome of %s for %s could not be recorded (%s): it stays owed" % (
            sminos.event_ref(e), session, err))
        return False
    return True


CLOSED = "a terminal session that was closed: kept owed, and delivered if it comes back"
HELD = "the session is stopped and is not woken: %s; kept owed, and delivered when a process of it runs again"
HELD_PASSING = "the session is stopped and not woken yet: kept owed, and delivered when a process of it runs"


def held_reason(sid):
    """Why what is owed to a member this machine holds is not delivered, as
    report_held sends it up: its hold now (sminos.hold_for) in the words a
    sender reads (T2's §5, HOLD_WORDS), a hold that passes on its own in
    general ones. Of either kind of thread: a spawned one was never a
    terminal's."""
    why = str(sminos.hold_for(sid) or "")
    return HELD % sminos.HOLD_WORDS[why] if why in sminos.HOLD_WORDS else HELD_PASSING


def closed_sessions(view, held=True):
    """The closed terminal sessions of this machine in a view: the members
    it holds (sminos.hold_for: a stopped thread not woken, T2's §4; left
    out with `held` False), and the seat-less sessions that joined from here
    whose membership ended with their process (retired, reason `ended`: one
    from before threads, or a lane B one; reconciliation retires a seat
    never so)."""
    out = set()
    for sid, r in view.info.items():
        latest, joined = (r or {}).get("latest"), (r or {}).get("joined") or {}
        if not (latest and joined and sminos.is_self(str(joined.get("machine") or ""), sid)):
            continue
        if latest["kind"] == "retired" and latest.get("reason") == "ended" \
                or held and latest["kind"] == "joined" and sminos.hold_for(sid):
            out.add(sid)
    return out


def report_one(project, box, sid, events, refuse=True, reason=CLOSED):
    """report_closed for one session; its caller holds the session's
    delivery lock. `refuse` False (a held member, report_held): no read-only
    refusal here, deliver_next's own. `reason` what each `recorded` says."""
    n = 0
    settled = sminos.delivered_load(project, sid)
    if sminos.sibling_module("sminos_policy").read_only():
        return refuse_owed(project, sid, events, settled) if refuse else 0
    if not project.hub:
        return 0
    path = sminos.project_path(project, "recorded", sminos.reader_key(sid) + ".json")
    reported = recorded_load(path)
    before = dict(reported)
    for e in unreported(events, reported, settled):
        w = e["writer"]
        try:
            box.record(e, sid, "recorded", reason)
        except OSError as err:
            sminos.daemon_log("delivery: the outcome of %s for %s could not be recorded (%s): reported later"
                              % (sminos.event_ref(e), sid, err))
            break
        reported[w] = e["seq"]
        n += 1
    if reported != before:
        sminos.write_json(path, reported)
    return n


def recorded_load(path):
    """A closed session's `recorded/<session>.json`: {writer: the last seq
    reported}, {} for none (written whole, by rename: sminos.json_at)."""
    try:
        reported = sminos.json_at(path)
    except (OSError, ValueError):
        return {}
    return reported if isinstance(reported, dict) else {}


def unreported(events, reported, settled):
    """Those of `events` (owed to one closed session) neither settled for it,
    reported, nor marked revoked (its outcome is `refused-revoked`), each
    writer's in seq order."""
    out = []
    for e in sorted(events, key=lambda e: (e["writer"], e["seq"])):
        w = sminos._delivery(settled, e["writer"])
        if e["seq"] <= max(int(reported.get(e["writer"]) or 0), w["settled"]) or e["seq"] in w.get("revoked", ()):
            continue
        out.append(e)
    return out


def owes_report(project, sid, events, refuse=True):
    """Whether report_one has anything to do for the session, looked at
    without its delivery lock: what is settled and what is reported only
    grow, so nothing to do now is nothing to do under the lock. The tick
    asks for every closed session each pass, and almost always the answer
    is no."""
    settled = sminos.delivered_load(project, sid)
    if sminos.sibling_module("sminos_policy").read_only():
        return refuse and bool(sminos._owed(events, sid, settled))
    if not project.hub:
        return False
    reported = recorded_load(os.path.join(project.home, "recorded", sminos.reader_key(sid) + ".json"))
    return bool(unreported(events, reported, settled))


def refuse_owed(project, sid, events, settled):
    """On a read-only machine, what is owed to a closed session from outside
    is settled undelivered as deliver_next settles it (a closed session is
    no member, so deliver_next never sees it): `refused-read-only` recorded,
    then settled, each writer in seq order from its settled prefix; one whose
    outcome cannot be kept stops its writer, owed for the next pass. The
    caller holds the session's delivery lock."""
    n, stopped = 0, set()
    for e in sminos._owed(sorted(events, key=lambda e: (e["writer"], e["seq"])), sid, settled):
        if e["writer"] in stopped:
            continue
        if not record(project, e, sid, READ_ONLY, None):
            stopped.add(e["writer"])
            continue
        sminos.delivered_settle(project, sid, e["writer"], e["seq"])
        n += 1
    return n


def report_closed(project, view):
    """`recorded` for each outside-origin event newly owed to a closed
    terminal session of a hub project, once per event and session; the
    event is not settled. On a read-only machine, of any project (the policy
    is machine-wide, as deliver_next applies it), each is settled
    `refused-read-only` instead (refuse_owed). How many were reported."""
    policy = sminos.sibling_module("sminos_policy")
    if not (project.hub or policy.read_only()):
        return 0
    # A held member is reported after its delivery pass (report_held): what settles without a push first.
    closed = closed_sessions(view, held=False)
    if not closed:
        return 0
    # A copy is owed to no one (sminos.addressed_to), and addressees leaves it out.
    to = sminos.addressees(view.events)
    n = 0
    box = Outbox(project)
    for sid in [s for s in to if s in closed]:
        events = [e for e in to[sid] if policy.outside_origin(e)]
        if not (events and owes_report(project, sid, events)):
            continue
        # Under the session's delivery lock, as deliver_next holds it: a
        # session back meanwhile is either delivered first (its settled
        # prefix then covers the event) or after this record, never between.
        with sminos.flocked(sminos.project_path(project, "delivered", sminos.reader_key(sid) + ".lock")):
            n += report_one(project, box, sid, events)
    return n


def held_report_owed(project, sid, events):
    """Whether report_held still owes a held member a report of `events`
    (one it could not write, for its next pass): as report_held decides it,
    without the lock."""
    policy = sminos.sibling_module("sminos_policy")
    if not project.hub or policy.read_only():
        return False
    events = [e for e in events if policy.outside_origin(e)]
    return bool(events) and owes_report(project, sid, events, refuse=False)


def report_held(project, sid, events):
    """For a member this machine holds (M3), after its delivery pass:
    `recorded` once for each outside-origin event of `events` (addressed to
    it) still owed, as report_closed reports a nonmember's, saying why it is
    held (held_reason). What the pass
    settled (a noted push, an admitted receipt, a revoked signer, a
    broadcast for the live alone, the read-only refusal) is no longer owed,
    so it is reported never. How many were reported."""
    policy = sminos.sibling_module("sminos_policy")
    if not project.hub or policy.read_only():
        return 0
    events = [e for e in events if policy.outside_origin(e)]
    if not (events and owes_report(project, sid, events, refuse=False)):
        return 0
    with sminos.flocked(sminos.project_path(project, "delivered", sminos.reader_key(sid) + ".lock")):
        return report_one(project, Outbox(project), sid, events, refuse=False, reason=held_reason(sid))


ENDED = ("the session's thread has ended (retired, or stopped past the period): it is pushed nothing, and reads "
         "the log if it returns")


def settle_ended(project, sid, lock_until=None, until=None, end=None):
    """What is owed to the session of a thread that ended, settled as for a
    retired target (T1's M4, D1): pushed nothing, each owed event settled,
    each writer in seq order from its settled prefix; one from outside a hub
    project with its outcome kept first — `recorded` (ENDED), a push the
    record noted as made its own outcome, `refused-read-only` on a
    read-only machine, as deliver_next would settle it — and one whose
    outcome cannot be kept stops its writer. The events stay in the log,
    which a returned thread reads at its next `chat`; nothing is delivered
    again when it returns. Under the session's delivery lock, waited for
    until `lock_until` (by default a few seconds: a verb may hold it while
    it ends the thread it delivers to). Whether nothing is owed to it any
    more: the journal's settlement (sminos_threads.finish) is done only
    then. Bounded by the end it is for: a return's settlement (`until`, the
    positions, each writer's seq, the events addressed to the session had
    reached in the local log as the return began) settles only those; the
    late pass's (`end`, the `retired` in effect it read) only while, read
    afresh under the lock, that end still stands (end_stands), so what
    reaches a thread after it returns is delivered to it."""
    policy = sminos.sibling_module("sminos_policy")
    wait = lock_until if lock_until is not None else time.time() + SETTLE_WAIT
    try:
        with sminos.flocked(sminos.project_path(project, "delivered", sminos.reader_key(sid) + ".lock"),
                            lock_until=wait):
            record = sminos.delivered_load(project, sid)
            owed = sminos._owed(sorted(sminos.log_read(project, to_session=sid),
                                       key=lambda e: (e["writer"], e["seq"])), sid, record)
            # After the snapshot: a return that begins later sets its `until` after every event read here.
            if end is not None and not end_stands(project, sid, end):
                return False
            stopped, past = set(), set()
            for e in owed:
                if e["writer"] in stopped or e["writer"] in past:
                    continue
                if until is not None and e["seq"] > int(until.get(e["writer"]) or 0):
                    past.add(e["writer"])   # after the return began: the returned session's own, and not a failure
                    continue
                outside = policy.outside_origin(e)
                if outside and project.hub:
                    noted = sminos._delivery(record, e["writer"]).get("pushed")
                    # An admitted receipt reached the model whatever the policy says since (holder_owed).
                    outcome, reason = (of_push(noted[1], None) if noted and noted[0] == e["seq"] else
                                       of_push("sent", None) if sminos.holder_module().admitted(project.id, sid, e)
                                       else (READ_ONLY, of_push(READ_ONLY, None)[1]) if policy.read_only() else
                                       ("recorded", ENDED))
                    try:
                        Outbox(project).record(e, sid, outcome, reason)
                    except OSError as err:
                        sminos.daemon_log("delivery: the outcome of %s for %s could not be recorded (%s): it stays "
                                          "owed" % (sminos.event_ref(e), sid, err))
                        stopped.add(e["writer"])
                        continue
                sminos.delivered_settle(project, sid, e["writer"], e["seq"])
                sminos.holder_module().settled(project.id, sid, e)
            return not stopped
    except sminos.LockBusy:
        return False


SETTLE_WAIT = 5.0   # seconds settle_ended waits for a delivery lock when its caller set no deadline


def end_stands(project, sid, end):
    """Whether the end `end` (a `retired` event) still stands for the
    session, read afresh: its membership in effect is still that event, and
    its thread's record, where it still has the session, has no open entry
    (a return under way settles its own) and, for an end this code
    journaled (stamped), still says ended — the record read under its own
    lock (sminos_threads.holds), which a return's begin holds while it sets
    its `until`. Asked under the session's delivery lock after the
    settlement's snapshot of the log: a return not begun by then sets its
    `until` after every event the snapshot holds, so what is settled here is
    the end's alone."""
    threads = sminos.threads_module()
    e = threads.in_effect(sminos._own_events(project, sid))
    if e is None or (e.get("writer"), e.get("seq")) != (end.get("writer"), end.get("seq")):
        return False
    t = threads.thread_of(sid)
    if t is None or t["current"] != sid:
        return True
    return threads.holds(t["thread"], lambda r: r["current"] != sid or not r.get("pending") and (
        threads.record_ended(r) or not threads.stamped(end)), missing=True)


def settle_ended_owed(project, view):
    """For each session of this machine in the view whose thread has ended
    (_ended_threads), what reached the log for it since — an event from
    outside, an older sender's — settled the same way (settle_ended), only
    while that end still stands. Asked again for a session only once the
    events addressed to it moved, so a tick pays for ended threads the one
    comparison. How many sessions were settled."""
    ended = sminos.log_memo(view.events, "ended-threads", lambda _events: _ended_threads(view.info))
    if not ended:
        return 0
    to = sminos.addressees(view.events)
    n = 0
    for sid, end in ended.items():
        mine = to.get(sid)
        if not mine:
            continue
        key, seen = (project.id, sid), (id(mine), len(mine))
        if _SETTLED.get(key) == seen:
            continue
        if sminos._owed(mine, sid, sminos.delivered_load(project, sid)):
            if not settle_ended(project, sid, end=end):
                continue
            n += 1
        _SETTLED[key] = seen
    return n


_SETTLED = {}   # (project id, session) → the addressed events (their list's id and length) settled up to


def _ended_threads(info):
    """{session: the `retired` that ended it} for each session of this
    machine whose thread has ended: its membership in effect a stamped
    `retired`, reason `retire` or `ended` (an end this code journaled, whose
    entry settled what was owed then), or an older copy's explicit `retire`
    (unstamped) of a session a thread record still has as its current one.
    An unstamped `ended` is a lane B session's, never a thread's end."""
    threads = sminos.threads_module()
    out = {}
    for sid, r in info.items():
        latest, joined = r["latest"], r["joined"] or {}
        if not (latest and latest["kind"] == "retired" and sminos.is_self(str(joined.get("machine") or ""), sid)):
            continue
        reason = latest.get("reason")
        if threads.stamped(latest) and reason in sminos.END_REASONS or \
                reason == "retire" and (threads.thread_of(sid) or {}).get("current") == sid:
            out[sid] = latest
    return out


REFUSED = "the session dropped it after taking it, so it never entered the conversation: %s"
# refused/<session>.json paths whose last write failed → the keys reported, held by this process.
_UNWRITTEN = {}


def report_refused(project, view):
    """A second outcome for a delivery the engine dropped after its bridge
    answered `submitted` (DC8.G5): for each session of a hub project whose
    bridge kept such a refusal (sminos_bridge, `refused` in its kept file),
    `failed` with the bridge's reason, recorded once per key and session
    (at least once, as every outcome here: the record comes before the
    marker that says it was made), for an outside-origin event of the
    project's log addressed to the session. Only once delivery has settled the event for the session, under
    the session's delivery lock as deliver_next holds it: its first outcome
    (`delivered`) is then recorded ahead of this one, and the hub keeps the
    latest. How many were recorded."""
    if not project.hub:
        return 0
    bridge = sminos.sibling_module("sminos_bridge")
    names = bridge_names(bridge)
    if names is None:
        return 0
    found = {}
    for name in names:
        sid, ext = os.path.splitext(name)
        if ext == ".json" and sid in view.info:
            # A bridge keeps the refusals of every project that delivered to
            # its session, and each project numbers a writer's events on its
            # own: one naming another project is that project's to report.
            # One naming none (a CLI older than the project in the key) is
            # matched here, as it always was.
            refused = [r for r in bridge.load_kept(sid).get("refused") or []
                       if r["key"].get("project", project.id) == project.id]
            if refused:
                found[sid] = refused
    if not found:
        return 0
    events = {(e["writer"], e["seq"]): e for e in view.events}
    box, n = Outbox(project), 0
    for sid, refused in found.items():
        with sminos.flocked(sminos.project_path(project, "delivered", sminos.reader_key(sid) + ".lock")):
            n += report_refusals(project, box, sid, refused, events)
    return n


_BRIDGE_NAMES = [None, None]   # [the cache generation, the bridge directory's names then, or None]


def bridge_names(bridge):
    """The bridge directory's names, listed once per cache generation
    (sminos.forget_caches): the tick asks for every hub project."""
    if _BRIDGE_NAMES[0] != sminos._GENERATION[0]:
        try:
            names = os.listdir(bridge.bridge_dir())
        except OSError:
            names = None
        _BRIDGE_NAMES[:] = [sminos._GENERATION[0], names]
    return _BRIDGE_NAMES[1]


def report_refusals(project, box, sid, refused, events):
    """report_refused for one session; its caller holds the session's
    delivery lock. What was reported is kept in the project's
    `refused/<session>.json` ([[writer, seq], …]), as long as the bridge
    keeps the refusal."""
    policy = sminos.sibling_module("sminos_policy")
    path = sminos.project_path(project, "refused", sminos.reader_key(sid) + ".json")
    try:
        with open(path) as f:
            reported = json.load(f)
    except (OSError, ValueError):
        reported = []
    reported = {(w, s) for w, s in (r for r in reported if isinstance(r, list) and len(r) == 2)} \
        if isinstance(reported, list) else set()
    reported |= _UNWRITTEN.get(path, set())
    settled = sminos.delivered_load(project, sid)
    n = 0
    for r in refused:
        k = (r["key"]["writer"], r["key"]["seq"])
        e = events.get(k)
        if k in reported or e is None or not sminos.addressed_to(e, sid) or not policy.outside_origin(e) \
                or k[1] > sminos._delivery(settled, k[0])["settled"]:
            continue
        try:
            box.record(e, sid, "failed", REFUSED % r["reason"])
        except OSError as err:
            sminos.daemon_log("delivery: the refusal of %s by %s could not be recorded (%s): reported later" % (
                sminos.event_ref(e), sid, err))
            break
        reported.add(k)
        n += 1
    keep = sorted(k for k in reported if any((r["key"]["writer"], r["key"]["seq"]) == k for r in refused))
    if n or len(keep) != len(reported) or path in _UNWRITTEN:
        try:
            sminos.write_json(path, [list(k) for k in keep])
        except OSError as err:
            # Delivery's outcomes are at least once: the marker comes after
            # the record, so a marker lost (here, or to a crash between the
            # two) costs a second identical `failed`, never a missing one.
            # This process remembers the keys meanwhile, and says so once.
            if path not in _UNWRITTEN:
                sminos.daemon_log("delivery: what was reported of %s's refusals could not be kept (%s): this "
                                  "process remembers it; another may report them again" % (sid, err))
            _UNWRITTEN[path] = set(keep)
        else:
            _UNWRITTEN.pop(path, None)
    return n


def message(machine, project_id, r):
    """A record as DX4's `delivery` message, its body the record's draft
    (RL10 carries no code)."""
    body = {"event": r.get("event"), "session": r.get("session"), "outcome": r.get("outcome"),
            "reason": r.get("reason")}
    return {"t": "session", "message": {"project": project_id, "machine": machine, "session": r.get("session"),
                                        "kind": "delivery", "sub": None, "n": None, "body": body}}
