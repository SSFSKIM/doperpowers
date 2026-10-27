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
session, or the stopped seat resumed with it), `uncertain` (the push was taken
and its answer never came: settled, never pushed again), `recorded` (the
recipient was not running and is pushed nothing), `refused-read-only` (the
machine's policy), `failed` (given up after DELIVERY_ATTEMPTS). An owner's
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
session (a seat-less session of this machine whose membership ended with its
process) is reported `recorded` once, when it first becomes owed to it
(report_closed), and stays owed; if the session comes back (Resume) and the
event is delivered, `delivered` follows for the same key. A closed session is
no member, so delivery never reaches it: on a read-only machine the report
applies the policy itself, settling what is owed to it from outside
undelivered as `refused-read-only`, as deliver_next would. What was reported
is kept per session in the project's `recorded/<session>.json` ({writer: the
last seq reported}).

A second outcome comes for a delivery the session's engine dropped after its
bridge answered `submitted` (DC8.G5): `delivered` says the text entered the
session's queue, not that it was taken in, and the bridge reports the drop
later, which its child keeps (`refused` in its kept file). The daemon's
delivery pass reports each once as `failed` with the bridge's reason
(report_refused), after the first outcome for the same key and session.

The uplink drains the file: it seals each record with the org key (DX1,
`smns-hub-delivery-v1`) as it posts it, and drops what a POST answered 200
carried. Nothing leaves this machine without its code.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402

OUTBOX = "outcomes.jsonl"
READ_ONLY = "refused-read-only"
UNCERTAIN = {"sent?": "uncertain: the session took the message and its answer never came",
             "woken?": "uncertain: the stopped seat was resumed with it and reported no session id"}


def of_push(push, member):
    """(DX4 outcome, reason) for what delivery made of an event: a push's
    outcome (sminos.push_event's), or READ_ONLY for one the policy refused."""
    if push == READ_ONLY:
        return READ_ONLY, "this machine is read-only: nothing written outside it is delivered"
    if push == "sent":
        return "delivered", "pushed to the live session"
    if push == "woken":
        return "delivered", "the stopped seat was resumed with it"
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


def closed_sessions(view):
    """The closed terminal sessions of this machine in a view: seat-less
    sessions that joined from here whose membership ended with their process
    (retired, reason `ended`; reconciliation retires a seat never so)."""
    out = set()
    for sid, r in view.info.items():
        latest, joined = (r or {}).get("latest"), (r or {}).get("joined") or {}
        if latest and latest["kind"] == "retired" and latest.get("reason") == "ended" and joined \
                and sminos.is_self(str(joined.get("machine") or ""), sid):
            out.add(sid)
    return out


def report_one(project, box, sid, events):
    """report_closed for one session; its caller holds the session's
    delivery lock."""
    n = 0
    settled = sminos.delivered_load(project, sid)
    if sminos.sibling_module("sminos_policy").read_only():
        return refuse_owed(project, sid, events, settled)
    if not project.hub:
        return 0
    path = sminos.project_path(project, "recorded", sminos.reader_key(sid) + ".json")
    try:
        with open(path) as f:
            reported = json.load(f)
    except (OSError, ValueError):
        reported = {}
    reported = reported if isinstance(reported, dict) else {}
    before = dict(reported)
    for e in sorted(events, key=lambda e: (e["writer"], e["seq"])):
        w = e["writer"]
        if e["seq"] <= max(int(reported.get(w) or 0), sminos._delivery(settled, w)["settled"]):
            continue
        try:
            box.record(e, sid, "recorded", CLOSED)
        except OSError as err:
            sminos.daemon_log("delivery: the outcome of %s for %s could not be recorded (%s): reported later"
                              % (sminos.event_ref(e), sid, err))
            break
        reported[w] = e["seq"]
        n += 1
    if reported != before:
        sminos.write_json(path, reported)
    return n


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
    closed = closed_sessions(view)
    if not closed:
        return 0
    owed = {}
    for e in view.events:
        to = e.get("to")
        if not isinstance(to, list) or "copy" in e or not policy.outside_origin(e):
            continue   # a copy is owed to no one (sminos.addressed_to)
        for sid in {r.get("session") for r in to if isinstance(r, dict)} & closed:
            owed.setdefault(sid, []).append(e)
    n = 0
    box = Outbox(project)
    for sid, events in owed.items():
        # Under the session's delivery lock, as deliver_next holds it: a
        # session back meanwhile is either delivered first (its settled
        # prefix then covers the event) or after this record, never between.
        with sminos.flocked(sminos.project_path(project, "delivered", sminos.reader_key(sid) + ".lock")):
            n += report_one(project, box, sid, events)
    return n


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
    try:
        names = os.listdir(bridge.bridge_dir())
    except OSError:
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


def message(key, machine, project_id, r):
    """A record as DX4's `delivery` message, sealed under a fresh nonce; None
    when it has no canonical form (said in daemon.log). With no key (RL10,
    where nothing carries a code) the body is the draft as it is."""
    draft = {"event": r.get("event"), "session": r.get("session"), "outcome": r.get("outcome"),
             "reason": r.get("reason")}
    if key is None:
        body = draft
    else:
        try:
            body = codes.seal(key, "delivery", project_id, draft, codes.b64url(os.urandom(codes.NONCE_BYTES)))
        except codes.NotCanonical as err:
            sminos.daemon_log("delivery: an outcome in %s has no canonical form (%s): not sent" % (project_id, err))
            return None
    return {"t": "session", "message": {"project": project_id, "machine": machine, "session": r.get("session"),
                                        "kind": "delivery", "sub": None, "n": None, "body": body}}
