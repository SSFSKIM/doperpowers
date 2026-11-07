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
        launches/<pid>-<start>.grace           0600   a deliverer waits for its activation (said once)
        sessions/<session>                     0600   the session was served by a `gate` process once

## The process mode

A claude process is `pid` plus `start`, its identity (process()): on macOS
the start XNU stored at fork, in whole epoch seconds; on Linux the boot id
and the start in ticks since that boot. Neither moves when the wall clock
steps, so every reader (deliverers, the child, the sweep) names the same
process alike, and a reused pid is another process. Where it cannot be
read, there is none: deliveries hold, activation is refused. Its record is
chosen once, under the process's mode lock, and never changes:

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
  activate (ACTIVATION_GRACE_S, at most 30 s; 0 is the plain rule): that
  delivery waits, owed, no attempt counted. daemon.log says when the wait
  starts, and when it ends in `legacy`.
- A record present but unreadable, or naming another mode: fail closed. The
  delivery stays owed (no attempt counted) and activation is refused. Unknown
  support is not legacy.

## The receipt

    {"v": 1, "id": "<keyhash>.<token>", "key": {"project", "session", "writer", "seq"}, "hash": <the event's>,
     "words": true | false | null, "created": <ISO>,
     "attempt": {"n", "pid", "start", "launch", "body": "full" | "wake", "state": "prepared" | "pushed", "at"},
     "handed": true (an attempt reached the inbox, or may have) | absent,
     "released": {"attempt": n, "present": bool, "at"} | null,
     "admitted": {"pid", "start", "launch", "at"} | null}

`keyhash` names the full (project, recipient session, writer, seq) and is the
file's name; `token` is random, made at the first prepare and kept, so an id
cannot be derived from what a log shows. A receipt is good only for the
event whose hash it holds: another body at that position (a git merge put
another line there) is none. The id and its attempt ride each delivery's
text as its first line, `[sminos receipt <id> attempt <n>]` (marker()); the
bridge mod reads them from the observed row and reports them through the
child, which checks them here: text alone settles nothing. `attempt` is the
current one: a resume or a retry changes the attempt, never the id.

A receipt proves it was prepared, not that anything was handed off. Only
`handed` (or an admission) exempts its event from a revocation
(sminos.revoke_owed); and every step that would push — a retry, a push that
failed before it reached — is checked first against the revocation set and
the read-only policy, as a fresh push is (plan(prepare=False) says so
without writing; sminos.holder_owed answers HOLDER_RETRY). Only an
admission settles a receipt unasked.

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
        marked as one a `gate` process served (an existing `gate` record
        marks the session it now serves too: a /clear's) — or `legacy` when
        `observer_started` (an M4a observer's process: observer_upgrade).
        Raises Unreadable (do not enable receipts; say so). Enable the
        receipt path only when the record returned is `gate`.
    observer_upgrade(pid) -> record
        An existing M4a observer's process (its kept `observerStarted`, no
        M4b activation of its own): `legacy` unless a record exists. Call it
        before handling any delivery or activation; keep the observer
        connected and fencing either way. Raises Unreadable.
    admit(ids, pid, session) -> {"ok": True, "receipts": {id: state}} | {"ok": False, "code", "error"[, "receipts"]}
        The mod admitted a model request carrying these receipts' rows (a
        `proceed`, no fence, or lease-expiry): ids only, an admission of
        any attempt settles. Durable before it answers, and idempotent:
        replay it until it answers ok. state is `admitted` (now or before),
        `gone` (no such receipt: settled and removed, or never made —
        nothing to do), `unknown` (an id whose token is not the receipt's:
        settles nothing) or `foreign` (the receipt is another session's: an
        old child's report after a /clear). `ok` false: refused whole when
        the process is not `gate` (`code` legacy, mode or process); `code`
        storage when an item could not be recorded durably (its receipt
        there and unreadable, a write failed: state `unavailable`, the
        others recorded beside it) — retryable: replay the whole report.
        The daemon is nudged; its next delivery pass settles.
    release(items, pid, launch, session) -> same shape as admit
        items: [{"id", "attempt": n, "present": bool}], `attempt` the one
        the stopped row's marker named. A stopped attempt in this same
        launch may be retried: the matching `disarm` (same epoch and fence)
        came, or every applicable hold expired plus the margin — the mod
        decides that against its current fences, never on a welcome alone;
        `present` says whether its row is still in the conversation (a wake
        then; a rewind or /clear dropped it: the full body). Checked here,
        under the receipts lock, against the receipt's current attempt: it
        must be `attempt`, this process's (pid and start), in `launch`.
        state is `released` (now, or a replay of this attempt's release),
        `admitted`, `gone`, `unknown`, `foreign`, `unavailable` (code
        storage, as admit) or `stale` (the attempt named is not the current
        one — a replay after its retry was made, or none named — or is
        another process's or launch's: nothing released). One release
        allows one retry; the retry's stop needs a release of its attempt.
    marker(id, attempt, body="full") / MARKER_RE / markers(text) -> [(id, attempt)]
        The text marker: a line `[sminos receipt <id> attempt <n>]`, the
        first line of each delivery's text; a wake's is
        `[sminos receipt <id> attempt <n> wake]`, since it carries no body:
        the mod admits a wake only while the body (its row, or an earlier
        attempt's full one) is in the request's conversation, else releases
        it `present` false for a full retry.

`stop` records nothing: no admission, no cursor. A receipt whose process
ended is retried by the next launch, with the same id.

Recovery: sweep() removes the mode records of processes that are gone (or
whose pid names another process: never one merely unreadable now) and
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
MARKER = "[sminos receipt %s attempt %d]"
WAKE_MARKER = "[sminos receipt %s attempt %d wake]"   # a wake's: the mod admits it only with its body in the conversation
ID_RE = re.compile(r"^([0-9a-f]{24})\.([0-9a-f]{16})$")
MARKER_RE = re.compile(r"^\[sminos receipt ([0-9a-f]{24}\.[0-9a-f]{16}) attempt ([1-9][0-9]{0,8})(?: wake)?\]$", re.M)
GRACE_MAX_S = 30.0
RETAINED_MAX = 512           # receipt ids an activation keeps as found in the conversation
SESSION_KEPT_S = 30 * 86400  # a session marker unrefreshed this long is swept


def _grace():
    try:
        v = float(os.environ.get("SMINOS_HOLDER_ACTIVATION_GRACE") or GRACE_MAX_S)
    except ValueError:
        return GRACE_MAX_S
    return min(max(v, 0.0), GRACE_MAX_S)


# How long a deliverer waits, owed, for a young process of a session a `gate`
# process served before to activate, before it records the process `legacy`:
# a resume races its own bridge's activation, and the first handoff wins.
# Never more than GRACE_MAX_S; 0 is the record-alone rule with no wait.
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
    """{"pid", "start", "age"} of a live process: `start` its identity, the
    same for every reader (deliverers, the child, the sweep) whatever the
    wall clock did since it began, and `age` its seconds since then on the
    boot clock (_boot_now), which no wall-clock step moves; infinite when
    that cannot be read (no grace: the record-alone rule). None
    when it does not run or its identity cannot be read (no reader falls
    back to a clock-derived one: two readers could tell two processes)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 1:
        return None
    got = _darwin_identity(pid) if sys.platform == "darwin" else _linux_identity(pid)
    return None if got is None else {"pid": pid, "start": got[0], "age": got[1]}


def _boot_now():
    """Now on the clock a process's start is kept in, beside its wall-clock
    one: mach absolute time on macOS (time.monotonic's), CLOCK_BOOTTIME on
    Linux (/proc/<pid>/stat's start ticks). Shared by every process of one
    boot; no wall-clock step moves it."""
    return time.monotonic() if sys.platform == "darwin" else time.clock_gettime(time.CLOCK_BOOTTIME)


def _darwin_identity(pid):
    """macOS: kinfo_proc's p_starttime, the wall-clock instant XNU stores in
    the proc at fork (kern_fork.c, microtime into p_start) and reads back
    as it is: a later clock step moves no stored start. The age from the
    start XNU keeps in mach absolute time (_darwin_boot_start)."""
    start = S._darwin_start(pid)
    if not start:
        return None
    begun = _darwin_boot_start(pid)
    return str(int(start)), float("inf") if begun is None else max(_boot_now() - begun, 0.0)


_LIBPROC = None   # (proc_pid_rusage, seconds per mach tick) once looked up; False where there is none
RUSAGE_INFO_V2 = 2
RI_PROC_START_ABSTIME = 80   # offset in rusage_info_v2: ri_uuid[16], then eight uint64s before it


def _darwin_boot_start(pid):
    """A process's start in mach absolute time, as seconds (time.monotonic's
    scale), from proc_pid_rusage's ri_proc_start_abstime; None when it
    cannot be read (another user's process, no libproc)."""
    global _LIBPROC
    if _LIBPROC is None:
        try:
            import ctypes

            class Timebase(ctypes.Structure):
                _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]
            rusage = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True).proc_pid_rusage
            rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
            rusage.restype = ctypes.c_int
            tb = Timebase()
            if ctypes.CDLL(None).mach_timebase_info(ctypes.byref(tb)) != 0 or not tb.denom:
                raise OSError("no mach timebase")
            _LIBPROC = (ctypes, rusage, tb.numer / tb.denom / 1e9)
        except (ImportError, OSError, AttributeError):
            _LIBPROC = False
    if not _LIBPROC:
        return None
    ctypes, rusage, scale = _LIBPROC
    buf = ctypes.create_string_buffer(256)
    if rusage(int(pid), RUSAGE_INFO_V2, buf) != 0:
        return None
    ticks = int.from_bytes(buf.raw[RI_PROC_START_ABSTIME:RI_PROC_START_ABSTIME + 8], sys.byteorder)
    return ticks * scale if ticks else None


def _linux_identity(pid):
    """Linux: the boot (/proc/sys/kernel/random/boot_id) and the start in
    clock ticks since it (/proc/<pid>/stat), neither read off the wall
    clock; ps's epoch start adds /proc/stat's btime, which a clock step
    moves. The age on CLOCK_BOOTTIME, the clock the ticks count on."""
    try:
        with open(os.path.join(S.PROC, "sys", "kernel", "random", "boot_id")) as f:
            boot = f.read().strip().replace("-", "").lower()
        ticks = S._start_ticks(pid)
    except (OSError, ValueError, IndexError):
        return None
    if not re.fullmatch(r"[0-9a-f]{32}", boot):
        return None
    return "%s-%d" % (boot, ticks), max(_boot_now() - ticks / os.sysconf("SC_CLK_TCK"), 0.0)


def _gone(pid):
    """Whether the process `pid` positively no longer runs."""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError, ValueError):
        return False
    return False


def _mode_path(proc, ext=".json"):
    return os.path.join(home(), LAUNCHES, "%d-%s%s" % (proc["pid"], proc["start"], ext))


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
        try:
            os.unlink(_mode_path(proc, ".grace"))
            if mode == "legacy":
                S.daemon_log("delivery: process %d of %s did not activate receipts within %ds: legacy, handed off"
                             % (proc["pid"], session, ACTIVATION_GRACE_S))
        except FileNotFoundError:
            pass
        return rec


def _grace_started(proc, session):
    """A deliverer waits for the process's activation: said once."""
    try:
        os.close(os.open(_mode_path(proc, ".grace"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        return
    S.daemon_log("delivery: process %d of %s may yet activate receipts (a gate process served its session): "
                 "what is owed to it waits, up to %ds" % (proc["pid"], session, ACTIVATION_GRACE_S))


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
    kept = [r for r in dict.fromkeys(retained) if isinstance(r, str) and ID_RE.fullmatch(r)][:RETAINED_MAX]
    rec = _choose(_process_of(pid), "gate", "activation", launch=launch, session=session, retained=kept)
    if rec["mode"] == "gate" and session:
        # Every session a gate process serves is marked (a /clear's too), for
        # C5's grace at its later resume; the record, mode and launch, stand.
        _mark_session(session)
    return rec


def observer_upgrade(pid, by="observer"):
    """A process already running when M4b loaded: `legacy` unless it has a
    record (see the module's contract). `by` says which: an M4a observer's
    (`observer`), or one no observer served (`existing`)."""
    return _choose(_process_of(pid), "legacy", by)


def handoff(pid, session, choose=True):
    """What a deliverer may do with a live process `pid` of `session`:
    "legacy" (its record says so, or it had none and now does: hand off),
    "gate" (prepare a receipt), "wait" (no record, and the process is a
    young one of a session a `gate` process served: stays owed), or
    "held:<why>" (fail closed). Without `choose`, a process with no record
    is "legacy" unrecorded: what a handoff would make it."""
    try:
        proc = _process_of(pid)
        rec = read_mode(proc)
        if rec is not None:
            return rec["mode"]
        if _served(session) and proc["age"] < ACTIVATION_GRACE_S:
            _grace_started(proc, session)
            return "wait"
        if not choose:
            return "legacy"
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


def marker(receipt_id, attempt, body="full"):
    """The marker line of an attempt; a wake's says so, since a wake carries
    no body: the mod admits it only while the body is in the conversation."""
    return (WAKE_MARKER if body == "wake" else MARKER) % (receipt_id, attempt)


def markers(text):
    """[(receipt id, attempt)] a text's marker lines name, in order."""
    return [(rid, int(n)) for rid, n in MARKER_RE.findall(text or "")]


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


def words_of(project_id, session, e):
    """The verdict the event's held receipt was prepared under (`words`:
    True a person's words, False a peer's, None none taken); None when no
    receipt is held for it or it cannot be read. What a retry pushes under,
    and so whether the reach gate decides it (P5 O18 D8)."""
    path = _receipt_path(key_hash(project_id, session, e["writer"], e["seq"]), create=False)
    try:
        r = _read(path) if os.path.exists(path) else None
    except Unreadable:
        return None
    return r.get("words") if r is not None and r.get("hash") == S.event_hash(e) else None


def handed(project_id, session, e):
    """Whether the event's receipt went to its process: True when an attempt
    reached its inbox (or may have) or the mod admitted it; False when there
    is none for the event, or it was only prepared (a push that failed
    before it reached the session: nothing handed off); None when it is
    there and cannot be read — not known, so nothing may be decided of it
    (revoke_owed defers the event, its receipt kept)."""
    path = _receipt_path(key_hash(project_id, session, e["writer"], e["seq"]), create=False)
    if not os.path.exists(path):
        return False
    try:
        r = _read(path)
    except Unreadable:
        return None
    return r is not None and r.get("hash") == S.event_hash(e) and bool(r.get("handed") or r.get("admitted"))


def _attempt(n, proc, launch, body):
    return {"n": n, "pid": proc["pid"], "start": proc["start"], "launch": launch, "body": body,
            "state": "prepared", "at": S.now(ms=True)}


def plan(project_id, session, e, event_hash, peer_pid, words=None, existing_only=False, prepare=True):
    """What a deliverer does with the log event `e` owed to `session`, whose
    live process is `peer_pid` (None: none runs), as the module's contract
    says, preparing a receipt durably when it is to be pushed. The caller
    holds the session's delivery lock. With `existing_only`, None when no
    receipt is held for the event. `words`: the verdict a fresh push is made
    under, kept for a later legacy handoff of the same receipt. Without
    `prepare`, nothing is written or chosen: "push" and "legacy" say a
    handoff would be made, for the caller to check its policy first."""
    keyhash = key_hash(project_id, session, e["writer"], e["seq"])
    path = _receipt_path(keyhash)
    with _receipts_lock():
        try:
            r = _read(path)
        except Unreadable as err:
            return Plan("held", why=str(err))
        if r is not None and (r.get("hash") != event_hash or not isinstance(r.get("attempt"), dict)
                              or not ID_RE.fullmatch(str(r.get("id") or ""))):
            r = None   # another body at this position, or no whole receipt: none for this event
        if r is None and existing_only:
            return None
        rid = r["id"] if r else None
        if r and r.get("admitted"):
            return Plan("settle", rid)
        if peer_pid is None:
            return Plan("awaiting", rid) if r else Plan("legacy", words=words)
        mode = handoff(peer_pid, session, choose=prepare)
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
        if not prepare:
            if r is not None and (a.get("pid"), a.get("start")) == (proc["pid"], proc["start"]) \
                    and a.get("state") != "prepared" \
                    and (r.get("released") or {}).get("attempt") != a.get("n"):
                return Plan("awaiting", rid)
            return Plan("push", rid)
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
    m = ID_RE.fullmatch(receipt_id or "")
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
        r["handed"] = True
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
    """(path, receipt) for an id this session may report, else (None,
    state). Raises Unreadable when the receipt is there and cannot be read:
    whether the id is valid is not known, and the report is not recorded."""
    m = ID_RE.fullmatch(receipt_id) if isinstance(receipt_id, str) else None
    if not m:
        return None, "unknown"
    path = _receipt_path(m.group(1))
    r = _read(path)
    if r is None:
        return None, "gone"
    if r.get("id") != receipt_id:
        return None, "unknown"
    if (r.get("key") or {}).get("session") != session:
        return None, "foreign"
    return (path, r), None


def _report(items, session, key, record):
    """A child's report (admit, release) recorded item by item under the
    receipts lock. key(item) is the receipt id an item names;
    record(path, receipt, item) writes what the item changes, returns its
    state and whether it wrote. Every item that can be recorded is; any
    that cannot (its receipt there and unreadable, a write that failed)
    makes the answer a retryable failure, `code` storage, with the others'
    states beside it: replayed whole, the recorded ones are idempotent."""
    out, changed, failed = {}, False, None
    try:
        with _receipts_lock():
            for item in items if isinstance(items, (list, tuple)) else ():
                rid = key(item)
                try:
                    held, state = _held_receipt(rid, session)
                    if held is None:
                        out[str(rid)] = state
                        continue
                    out[rid], wrote = record(held[0], held[1], item)
                    changed = changed or wrote
                except (Unreadable, OSError) as e:
                    out[str(rid)] = "unavailable"
                    failed = failed or str(e)
    except OSError as e:
        failed = str(e)
    if changed:
        S.nudge_daemon()
    if failed:
        return {"ok": False, "code": "storage", "error": "not recorded, replay the report: %s" % failed,
                "receipts": out}
    return {"ok": True, "receipts": out}


def admit(ids, pid, session):
    """The admission of receipts, as the module's contract says."""
    got, refusal = _gate_process(pid)
    if refusal:
        return refusal
    proc, rec = got

    def record(path, r, _rid):
        if r.get("admitted"):
            return "admitted", False
        r["admitted"] = {"pid": proc["pid"], "start": proc["start"], "launch": rec["launch"], "at": S.now(ms=True)}
        _write(path, r)
        return "admitted", True
    return _report(ids, session, lambda rid: rid, record)


def release(items, pid, launch, session):
    """A stopped attempt's retry in the same launch, as the module's
    contract says."""
    got, refusal = _gate_process(pid)
    if refusal:
        return refusal
    proc, rec = got
    if launch != rec["launch"]:
        return {"ok": False, "code": "launch", "error": "process %d is launch %s, not %s" % (
            proc["pid"], rec["launch"], launch)}

    def record(path, r, item):
        a = r.get("attempt") or {}
        n = item.get("attempt")
        if r.get("admitted"):
            return "admitted", False
        if (a.get("pid"), a.get("start"), a.get("launch")) != (proc["pid"], proc["start"], launch) \
                or type(n) is not int or n != a.get("n"):
            return "stale", False
        if (r.get("released") or {}).get("attempt") == n:
            return "released", False
        r["released"] = {"attempt": n, "present": item.get("present") is True, "at": S.now(ms=True)}
        _write(path, r)
        return "released", True
    return _report(items, session, lambda item: item.get("id") if isinstance(item, dict) else None, record)


# ------------------------------------------------------------------ recovery


def sweep(project_of):
    """Removes what nothing will read again: the mode records (and locks) of
    processes that positively no longer run (gone, or their pid another
    process's now), the receipts whose event the recipient's
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
        m = re.fullmatch(r"(\d+)-([0-9a-f-]+)\.(json|lock|grace)", name)
        if not m:
            continue
        # Only on proof the process ended: it is gone, or its pid now names
        # another process. A live one whose identity cannot be read now
        # keeps its sticky mode.
        if _gone(m.group(1)) or (process(m.group(1)) or {}).get("start", m.group(2)) != m.group(2):
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
            if not re.fullmatch(r"[0-9a-f]{24}\.json", name):
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
