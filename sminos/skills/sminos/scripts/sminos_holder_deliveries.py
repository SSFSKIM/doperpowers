"""sminos_holder_deliveries — durable receipts for the deliveries a MAWS lane
B observer's process takes, and the per-process mode that decides whether a
delivery prepares one (O12 M4b; the accepted O16 Interfaces §E settlement
amendment). Machine-local: nothing here is a hub or RL10 frame, and nothing
here is OX10's wire.

Without a receipt, a log event handed to a session's inbox is settled at the
handoff (sminos.deliver_next advances the delivered cursor once push_live
returns). A process recorded `gate` settles it later: at the first model
request the bridge mod admits with the event's row in it (a `proceed`, an
unarmed admission, or the observer's lease-expiry proceed). On the host's
`stop` it stays owed. Everything below lives under

    $SMINOS_HOME/holder-deliveries/            0700
        <keyhash>.json                         0600   one receipt
        receipts.lock                                 every receipt's read-modify-write
        launches/<pid>-<start>.json            0600   one process's delivery mode
        launches/<pid>-<start>.lock                   its mode lock
        sessions/<session>                     0600   the session was served by a `gate` process once

## The process mode

A claude process is `pid` plus `start` (its start, whole epoch seconds, as
`ps -o lstart=` reads it: process()), so a reused pid is another process.
Its record is chosen once, under the process's mode lock, and never changes:

    {"v": 1, "pid", "start", "mode": "gate" | "legacy", "launch": <M7's launch id> | null,
     "session": <the session it was chosen for> | null, "by": "activation" | "observer" | "handoff",
     "since": <ISO 8601>, "retained": [<receipt id>...]}

- `gate`: the bridge child activated receipts (activate()) before any
  legacy handoff to the process. Every log-backed delivery to it then
  prepares a receipt, whether or not its child or mod is up.
- `legacy`: a deliverer handed something off first (handoff()), or the
  process was already running an M4a observer when M4b loaded
  (observer_upgrade()). It keeps handoff settlement for its life; M4a's
  observer keeps observing.
- No record: nothing was handed off and nothing activated. The next
  deliverer records `legacy` under the lock and hands off, except while a
  young process of a session a `gate` process served before may still
  activate (ACTIVATION_GRACE_S): that delivery waits, owed, for at most the
  grace.
- A record present but unreadable, or naming another mode: fail closed. The
  delivery stays owed (no attempt counted) and activation is refused. Unknown
  support is not legacy.

## The receipt

    {"v": 1, "id": "<keyhash>.<token>", "key": {"project", "session", "writer", "seq"}, "hash": <the event's>,
     "words": true | false | null, "created": <ISO>,
     "attempt": {"n", "pid", "start", "launch", "body": "full" | "wake", "state": "prepared" | "pushed", "at"},
     "released": {"attempt": n, "present": bool, "at"} | null,
     "admitted": {"pid", "start", "launch", "at"} | null}

`keyhash` names the full (project, recipient session, writer, seq) and is the
file's name; `token` is random, made at the first prepare and kept, so an id
cannot be derived from what a log shows. A receipt is good only for the
event whose hash it holds: another body at that position (a git merge put
another line there) is none. The id rides each delivery's text as its first
line, `[sminos receipt <id>]` (marker()); the bridge mod reads it from the
observed row and reports it through the child, which checks it here: text
alone settles nothing. `attempt` is the current one: a resume or a retry
changes the attempt, never the id.

What a deliverer does with an event (plan(), under the recipient's delivery
lock, sminos.deliver_next and deliver_verdict):
- admitted → settle it now, on the outcome `sent` (the normal reconciler:
  the outside-origin outcome is recorded first, then the cursor; then the
  receipt is removed, settled()).
- no live process, and a receipt → owed (a later launch retries it).
- a `legacy` process → today's handoff; a receipt it carried goes with it.
- a `gate` process:
  - no receipt → prepare one (attempt 1, the full body), durably, before the
    inbox write; then push; then mark it pushed (pushed());
  - the attempt is this process's and still `prepared` (a crash between the
    prepare and the push, or a push that failed before it reached the
    session) → push the same attempt again;
  - the attempt is this process's, pushed, and the mod released it since
    (release()) → one more attempt in the same launch: a wake when the row is
    still in the conversation, else the full body;
  - the attempt is this process's otherwise → owed, nothing pushed, no
    attempt counted: the writer stops here;
  - the attempt was another process's (a resume) → a new attempt, the same
    id: a wake when activation found the row retained in the resumed
    conversation (`retained`), else the full body.

## What the bridge child calls (T6)

All of these run in the bridge child (the mod has no pid of its own: `pid`
is claude's, the child's os.getppid()). None takes a delivery lock; each
takes only this module's short locks, so none waits on a deliverer's push.

    activate(pid, launch, session, observer_started=False, retained=()) -> record
        Before the OX10 hello, on M3's `match` verdict. Under the mode lock:
        a record that exists is returned as it is (a reload, a child restart
        or a /clear never changes it); with none, `gate` is written with
        `launch` and `retained` (receipt ids the mod found in the live
        conversation's rows, for a resume's reconciliation) and the session
        marked as one a `gate` process served — or `legacy` when
        `observer_started` (an M4a observer's process: observer_upgrade).
        Raises Unreadable (do not enable receipts; say so). Enable the
        receipt path only when the record returned is `gate`.
    observer_upgrade(pid) -> record
        An existing M4a observer's process (its kept `observerStarted`, no
        M4b activation of its own): `legacy` unless a record exists. Call it
        before handling any delivery or activation; keep the observer
        connected and fencing either way. Raises Unreadable.
    admit(ids, pid, session) -> {"ok": True, "receipts": {id: state}} | {"ok": False, "code", "error"}
        The mod admitted a model request carrying these receipts' rows (a
        `proceed`, no fence, or lease-expiry). Durable before it answers, and
        idempotent: replay it until it answers ok. state is `admitted` (now
        or before), `gone` (no such receipt: settled and removed, or never
        made — nothing to do), `unknown` (an id whose token is not the
        receipt's: settles nothing) or `foreign` (the receipt is another
        session's: an old child's report after a /clear). Refused whole
        (`ok` false) when the process is not `gate` (`code` legacy, mode or
        process). The daemon is nudged; its next delivery pass settles.
    release(items, pid, launch, session) -> {"ok": True, "receipts": {id: state}} | {"ok": False, "code", "error"}
        items: [{"id", "present": bool}]. A stopped receipt in this same
        launch may be retried: the matching `disarm` (same epoch and fence)
        came, or every applicable hold expired plus the margin — the mod
        decides that against its current fences, never on a welcome alone;
        `present` says whether its row is still in the conversation (a wake
        then; a rewind or /clear dropped it: the full body). Checked here
        against the current process and launch: the receipt's attempt must
        be this process's (pid and start) in `launch`. state is `released`,
        `admitted`, `gone`, `unknown`, `foreign` or `stale` (the attempt is
        another process's or launch's: nothing to release here). One
        release allows one retry; a later stop needs another.
    marker(id) / MARKER_RE / markers(text)
        The text marker: a line `[sminos receipt <id>]`, the first line of
        each delivery's text (a wake's too).

`stop` records nothing: no admission, no cursor. A receipt whose process
ended is retried by the next launch, with the same id.

Recovery: sweep() removes the mode records of processes that are gone and
the receipts whose event the delivery record has settled (a crash between
the settlement and settled()); `sminos daemon run` sweeps with its other
sweeps.
"""

import hashlib
import json
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from typing import NamedTuple, Optional

import sminos as S

DIR = "holder-deliveries"
LAUNCHES = "launches"
SESSIONS = "sessions"
MODES = ("gate", "legacy")
BODIES = ("full", "wake")
MARKER = "[sminos receipt %s]"
ID_RE = re.compile(r"^([0-9a-f]{24})\.([0-9a-f]{16})$")
MARKER_RE = re.compile(r"^\[sminos receipt ([0-9a-f]{24}\.[0-9a-f]{16})\]$", re.M)
RETAINED_MAX = 512           # receipt ids an activation keeps as found in the conversation
SESSION_KEPT_S = 30 * 86400  # a session marker unrefreshed this long is swept


def _grace():
    try:
        v = float(os.environ.get("SMINOS_HOLDER_ACTIVATION_GRACE") or 30)
    except ValueError:
        return 30.0
    return max(v, 0.0)


# How long a deliverer waits, owed, for a young process of a session a `gate`
# process served before to activate, before it records the process `legacy`:
# a resume races its own bridge's activation, and the first handoff wins.
ACTIVATION_GRACE_S = _grace()


class Unreadable(Exception):
    """A mode record or a receipt is present and cannot be read, or a
    process's identity cannot be: fail closed."""


class Plan(NamedTuple):
    """What a deliverer does with one event (plan()).
    kind: legacy | push | awaiting | settle | held."""
    kind: str
    receipt: Optional[str] = None
    attempt: int = 0
    body: str = "full"
    words: Optional[bool] = None
    why: str = ""


# ------------------------------------------------------------------ places


def home(create=True):
    """$SMINOS_HOME/holder-deliveries, made private on first use (`create`)."""
    path = os.path.join(S.root(), DIR)
    if create:
        for d in (path, os.path.join(path, LAUNCHES), os.path.join(path, SESSIONS)):
            os.makedirs(d, mode=0o700, exist_ok=True)
    return path


def _write(path, data):
    """Atomic and durable: the file and its directory synced before the
    rename is relied on (a receipt is prepared before an inbox write)."""
    d = os.path.dirname(path)
    tmp = os.path.join(d, ".tmp-%s-%d" % (os.path.basename(path), os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    dfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _read(path):
    """The JSON object at path; None when there is no file; Unreadable when
    there is one and it is not a JSON object."""
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Unreadable("%s cannot be read: %s" % (os.path.basename(path), e))
    if not isinstance(d, dict):
        raise Unreadable("%s is not a record" % os.path.basename(path))
    return d


# ------------------------------------------------------------------ the process mode


def process(pid):
    """{"pid", "start"} of a live process, its start in whole epoch seconds;
    None when it does not run or its start cannot be read."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 1:
        return None
    # Epoch seconds where the kernel says so (no local-time text between two
    # processes that may not share a TZ); ps's text where it cannot.
    start = S._darwin_start(pid) if sys.platform == "darwin" else S._linux_start(pid)
    if start is None:
        parsed = S._parse_lstart(S.read_proc_start(pid))
        start = int(time.mktime(parsed)) if parsed else 0
    return {"pid": pid, "start": int(start)} if start else None


def _mode_path(proc, ext=".json"):
    return os.path.join(home(), LAUNCHES, "%d-%d%s" % (proc["pid"], proc["start"], ext))


def read_mode(proc):
    """The process's mode record, or None when it has none; Unreadable when
    one is there and is not a whole record of this process (fail closed)."""
    rec = _read(_mode_path(proc))
    if rec is None:
        return None
    if rec.get("mode") not in MODES or rec.get("pid") != proc["pid"] or rec.get("start") != proc["start"]:
        raise Unreadable("the delivery mode of process %d is unknown: %s" % (
            proc["pid"], json.dumps(rec, sort_keys=True)[:200]))
    return rec


@contextmanager
def _mode_lock(proc):
    with S.flocked(_mode_path(proc, ".lock")):
        yield


def _choose(proc, mode, by, launch=None, session=None, retained=()):
    """Under the process's mode lock: the record there, else `mode` written."""
    with _mode_lock(proc):
        rec = read_mode(proc)
        if rec is not None:
            return rec
        rec = {"v": 1, "pid": proc["pid"], "start": proc["start"], "mode": mode,
               "launch": launch if mode == "gate" else None, "session": session or None, "by": by,
               "since": S.now(ms=True), "retained": list(retained) if mode == "gate" else []}
        _write(_mode_path(proc), rec)
        if mode == "gate" and session:
            _mark_session(session)
        return rec


def _session_path(session):
    return os.path.join(home(), SESSIONS, session)


def _mark_session(session):
    if S.valid_name(session):
        _write(_session_path(session), {"since": S.now(ms=True)})


def _served(session):
    return bool(session) and S.valid_name(session) and os.path.exists(_session_path(session))


def _process_of(pid):
    proc = process(pid)
    if proc is None:
        raise Unreadable("process %s does not run, or its start cannot be read" % pid)
    return proc


def activate(pid, launch, session, observer_started=False, retained=()):
    """The bridge child's activation of receipts for claude's process `pid`
    (see the module's contract): the record that holds after it."""
    if observer_started:
        return observer_upgrade(pid)
    if not (isinstance(launch, str) and launch):
        raise ValueError("activation names the process's launch")
    kept = [r for r in dict.fromkeys(retained) if isinstance(r, str) and ID_RE.match(r)][:RETAINED_MAX]
    return _choose(_process_of(pid), "gate", "activation", launch=launch, session=session, retained=kept)


def observer_upgrade(pid):
    """An M4a observer's process seen by M4b: `legacy` unless it has a
    record (see the module's contract)."""
    return _choose(_process_of(pid), "legacy", "observer")


def handoff(pid, session):
    """What a deliverer may do with a live process `pid` of `session`:
    "legacy" (its record says so, or it had none and now does: hand off),
    "gate" (prepare a receipt), "wait" (no record, and the process is a
    young one of a session a `gate` process served: stays owed), or
    "held:<why>" (fail closed)."""
    try:
        proc = _process_of(pid)
        rec = read_mode(proc)
        if rec is not None:
            return rec["mode"]
        if _served(session) and time.time() - proc["start"] < ACTIVATION_GRACE_S:
            return "wait"
        return _choose(proc, "legacy", "handoff", session=session)["mode"]
    except (Unreadable, OSError) as e:
        return "held:%s" % e


# ------------------------------------------------------------------ receipts


def key_hash(project_id, session, writer, seq):
    return hashlib.sha256(json.dumps([project_id, session, writer, seq]).encode()).hexdigest()[:24]


def _receipt_path(keyhash, create=True):
    return os.path.join(home(create), keyhash + ".json")


@contextmanager
def _receipts_lock():
    with S.flocked(os.path.join(home(), "receipts.lock")):
        yield


def marker(receipt_id):
    return MARKER % receipt_id


def markers(text):
    """The receipt ids a text's marker lines name, in order."""
    return MARKER_RE.findall(text or "")


def exists(project_id, session, e):
    """Whether a receipt is held for the event: it was handed to a `gate`
    process and is not settled. One for another body at its position is
    none; one that cannot be read is held (fail closed: plan() holds it).
    Reads nothing when there is no file, as for every event of a process
    that never took a receipt."""
    path = _receipt_path(key_hash(project_id, session, e["writer"], e["seq"]), create=False)
    if not os.path.exists(path):
        return False
    try:
        r = _read(path)
    except Unreadable:
        return True
    return r is not None and r.get("hash") == S.event_hash(e)


def _attempt(n, proc, launch, body):
    return {"n": n, "pid": proc["pid"], "start": proc["start"], "launch": launch, "body": body,
            "state": "prepared", "at": S.now(ms=True)}


def plan(project_id, session, e, event_hash, peer_pid, words=None, existing_only=False):
    """What a deliverer does with the log event `e` owed to `session`, whose
    live process is `peer_pid` (None: none runs), as the module's contract
    says, preparing a receipt durably when it is to be pushed. The caller
    holds the session's delivery lock. With `existing_only`, None when no
    receipt is held for the event. `words`: the verdict a fresh push is made
    under, kept for a later legacy handoff of the same receipt."""
    keyhash = key_hash(project_id, session, e["writer"], e["seq"])
    path = _receipt_path(keyhash)
    with _receipts_lock():
        try:
            r = _read(path)
        except Unreadable as err:
            return Plan("held", why=str(err))
        if r is not None and (r.get("hash") != event_hash or not isinstance(r.get("attempt"), dict)
                              or not ID_RE.match(str(r.get("id") or ""))):
            r = None   # another body at this position, or no whole receipt: none for this event
        if r is None and existing_only:
            return None
        rid = r["id"] if r else None
        if r and r.get("admitted"):
            return Plan("settle", rid)
        if peer_pid is None:
            return Plan("awaiting", rid) if r else Plan("legacy", words=words)
        mode = handoff(peer_pid, session)
        if mode == "wait":
            return Plan("awaiting", rid, why="its process may yet activate receipts")
        if mode.startswith("held:"):
            return Plan("held", rid, why=mode[len("held:"):])
        if mode == "legacy":
            return Plan("legacy", rid, words=r.get("words") if r else words)
        try:
            proc = _process_of(peer_pid)
            rec = read_mode(proc)
        except Unreadable as err:
            return Plan("held", rid, why=str(err))
        if rec is None or rec["mode"] != "gate":
            return Plan("held", rid, why="the process's mode changed under the deliverer")
        a = r.get("attempt") if r else None
        if r is None:
            r = {"v": 1, "id": "%s.%s" % (keyhash, secrets.token_hex(8)),
                 "key": {"project": project_id, "session": session, "writer": e["writer"], "seq": e["seq"]},
                 "hash": event_hash, "words": words, "created": S.now(ms=True),
                 "attempt": _attempt(1, proc, rec["launch"], "full"), "released": None, "admitted": None}
        elif (a.get("pid"), a.get("start")) == (proc["pid"], proc["start"]):
            released = r.get("released")
            if a.get("state") == "prepared":
                r["released"] = None   # this attempt is pushed again, whatever was released of it
            elif isinstance(released, dict) and released.get("attempt") == a.get("n"):
                r["attempt"] = _attempt(int(a.get("n") or 0) + 1, proc, rec["launch"],
                                        "wake" if released.get("present") else "full")
                r["released"] = None
            else:
                return Plan("awaiting", rid)
        else:
            body = "wake" if rid in (rec.get("retained") or ()) else "full"
            r["attempt"] = _attempt(int(a.get("n") or 0) + 1, proc, rec["launch"], body)
            r["released"] = None
        _write(path, r)
        a = r["attempt"]
        return Plan("push", r["id"], a["n"], a["body"] if a["body"] in BODIES else "full", r.get("words"))


def pushed(receipt_id, attempt):
    """The attempt's text reached the session's inbox (or may have: an
    uncertain close-out). Best effort: an attempt left `prepared` is pushed
    again by the next pass, at least once."""
    m = ID_RE.match(receipt_id or "")
    if not m:
        return
    path = _receipt_path(m.group(1))
    with _receipts_lock():
        try:
            r = _read(path)
        except Unreadable:
            return
        if r is None or r.get("id") != receipt_id or (r.get("attempt") or {}).get("n") != attempt:
            return
        r["attempt"]["state"] = "pushed"
        _write(path, r)


def settled(project_id, session, e):
    """The event's delivery settled (the cursor moved past it): its receipt,
    if one is held, is removed."""
    path = _receipt_path(key_hash(project_id, session, e["writer"], e["seq"]), create=False)
    if not os.path.exists(path):
        return
    with _receipts_lock():
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


# ------------------------------------------------------------------ the child's reports (T6)


def _gate_process(pid):
    """(process, its `gate` record), or a refusal answer."""
    proc = process(pid)
    if proc is None:
        return None, {"ok": False, "code": "process", "error": "process %s does not run, or its start cannot be "
                                                               "read" % pid}
    try:
        rec = read_mode(proc)
    except Unreadable as e:
        return None, {"ok": False, "code": "mode", "error": str(e)}
    if rec is None or rec["mode"] != "gate":
        return None, {"ok": False, "code": "legacy", "error": "process %d does not take receipts (%s)" % (
            proc["pid"], rec["mode"] if rec else "no mode")}
    return (proc, rec), None


def _held_receipt(receipt_id, session):
    """(path, receipt) for an id this session may report, else (None, state)."""
    m = ID_RE.match(receipt_id) if isinstance(receipt_id, str) else None
    if not m:
        return None, "unknown"
    path = _receipt_path(m.group(1))
    try:
        r = _read(path)
    except Unreadable:
        return None, "unknown"
    if r is None:
        return None, "gone"
    if r.get("id") != receipt_id:
        return None, "unknown"
    if (r.get("key") or {}).get("session") != session:
        return None, "foreign"
    return (path, r), None


def admit(ids, pid, session):
    """The admission of receipts, as the module's contract says."""
    got, refusal = _gate_process(pid)
    if refusal:
        return refusal
    proc, rec = got
    out, newly = {}, False
    with _receipts_lock():
        for rid in ids if isinstance(ids, (list, tuple)) else ():
            held, state = _held_receipt(rid, session)
            if held is None:
                out[str(rid)] = state
                continue
            path, r = held
            if not r.get("admitted"):
                r["admitted"] = {"pid": proc["pid"], "start": proc["start"], "launch": rec["launch"],
                                 "at": S.now(ms=True)}
                _write(path, r)
                newly = True
            out[rid] = "admitted"
    if newly:
        S.nudge_daemon()
    return {"ok": True, "receipts": out}


def release(items, pid, launch, session):
    """A stopped receipt's retry in the same launch, as the module's
    contract says."""
    got, refusal = _gate_process(pid)
    if refusal:
        return refusal
    proc, rec = got
    if launch != rec["launch"]:
        return {"ok": False, "code": "launch", "error": "process %d is launch %s, not %s" % (
            proc["pid"], rec["launch"], launch)}
    out, newly = {}, False
    with _receipts_lock():
        for item in items if isinstance(items, (list, tuple)) else ():
            rid = item.get("id") if isinstance(item, dict) else None
            held, state = _held_receipt(rid, session)
            if held is None:
                out[str(rid)] = state
                continue
            path, r = held
            a = r.get("attempt") or {}
            if r.get("admitted"):
                out[rid] = "admitted"
            elif (a.get("pid"), a.get("start"), a.get("launch")) != (proc["pid"], proc["start"], launch):
                out[rid] = "stale"
            else:
                r["released"] = {"attempt": a.get("n"), "present": item.get("present") is True, "at": S.now(ms=True)}
                _write(path, r)
                out[rid] = "released"
                newly = True
    if newly:
        S.nudge_daemon()
    return {"ok": True, "receipts": out}


# ------------------------------------------------------------------ recovery


def sweep(project_of):
    """Removes what nothing will read again: the mode records (and locks) of
    processes that no longer run, the receipts whose event the recipient's
    delivery record has settled past (a crash between the settlement and
    settled()), and session markers unrefreshed for SESSION_KEPT_S.
    `project_of(id)` is the project registered here, or None (its receipts
    are kept). (mode records, receipts) removed; nothing is made where
    nothing was ever kept."""
    base = home(create=False)
    if not os.path.isdir(base):
        return 0, 0
    home()
    modes = receipts = 0
    for name in os.listdir(os.path.join(base, LAUNCHES)):
        m = re.match(r"^(\d+)-(-?\d+)\.(json|lock)$", name)
        if not m:
            continue
        proc = process(m.group(1))
        if proc is None or proc["start"] != int(m.group(2)):
            try:
                os.unlink(os.path.join(base, LAUNCHES, name))
                modes += m.group(3) == "json"
            except FileNotFoundError:
                pass
    now = time.time()
    for name in os.listdir(os.path.join(base, SESSIONS)):
        path = os.path.join(base, SESSIONS, name)
        try:
            if now - os.stat(path).st_mtime > SESSION_KEPT_S:
                os.unlink(path)
        except FileNotFoundError:
            pass
    with _receipts_lock():
        for name in os.listdir(base):
            if not re.match(r"^[0-9a-f]{24}\.json$", name):
                continue
            try:
                r = _read(os.path.join(base, name))
            except Unreadable:
                continue
            key = (r or {}).get("key") or {}
            project = project_of(key.get("project")) if isinstance(key.get("project"), str) else None
            if project is None or not isinstance(key.get("session"), str) or type(key.get("seq")) is not int:
                continue
            w = S.delivered_load(project, key["session"]).get(str(key.get("writer")))
            if w and (key["seq"] <= w["settled"] or key["seq"] in w.get("revoked", ())):
                try:
                    os.unlink(os.path.join(base, name))
                    receipts += 1
                except FileNotFoundError:
                    pass
    return modes, receipts
