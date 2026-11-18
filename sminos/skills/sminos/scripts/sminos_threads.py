#!/usr/bin/env python3
"""sminos_threads — the thread record of every lane A member of this
machine, the stamp its lifecycle events carry, the one reducer every reader
of membership goes through, and the journal that finishes a transition its
process died in (contract X1 and X7 of
docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md;
Interfaces §1, §2, §3 and §6 of
docs/doperpowers/plans/2026-11-17-sminos-threads-t1.md).

Two stores behind one view:

- a spawned thread's record is its seat record, `$SMINOS_HOME/<seat>.json`,
  with the keys `opened`, `sessions`, `launch`, `channels`, `stopped`,
  `swept`, `ended`, `released` and `pending` added, under `.metalock` (the
  board pipeline reads and writes the same file under the same lock); its
  `thread`, `current` and `alias` are the seat's own id, `current` and
  `alias`;
- a thread its human opened is `threads/<thread>.json`, under
  `threads/.lock`, where no sminos from before threads looks for a seat;
  its end moves it to `threads/ended/<thread>.json`, and a return brings it
  back. Its id is minted, never a session's.

A record is written first, and a transition that owes events journals them
in it (`pending`): begin() makes the record's change and the entry in one
write, finish() appends each event the log does not hold yet (each carries
the entry's id in `op`), then clears the entry in the write that sets the
record aside or deletes it. Any process may finish an entry, any number of
times; nothing else changes a record while its entry is open.
"""
import contextlib
import copy
import fcntl
import json
import os
import re
import struct
import sys
import time
import uuid

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos  # noqa: E402

V = 1
OPENED = ("spawned", "human")
OPS = ("advance", "absorb", "end", "return", "release")
# The keys only a journaled operation writes (begin); update() refuses them.
JOURNALED = ("current", "sessions", "ended", "released", "pending")
# What a seat record gains; its `thread`, `current` and `alias` are its own.
SEAT_KEYS = ("opened", "sessions", "launch", "channels", "stopped", "swept", "ended", "released", "pending")

# The engine's options `launch.options` keeps, in the order the process was
# given them: those a first background resume may carry (T2 reads them, and
# extends the list). Nothing outside it is kept; a value that is inline JSON
# or names a session is never kept (sminos_records' rule: no secret in a
# record). _FLAGS take no value; _MANY take every value up to the next option.
LAUNCH_OPTIONS = ("--permission-mode", "--model", "--fallback-model", "--effort", "--settings", "--add-dir",
                  "--agent", "--plugin-dir", "--mcp-config", "--strict-mcp-config", "--allowedTools",
                  "--allowed-tools", "--disallowedTools", "--disallowed-tools", "--dangerously-skip-permissions",
                  "--allow-dangerously-skip-permissions")
_FLAGS = frozenset(("--strict-mcp-config", "--dangerously-skip-permissions", "--allow-dangerously-skip-permissions"))
_MANY = frozenset(("--add-dir", "--mcp-config", "--allowedTools", "--allowed-tools", "--disallowedTools",
                   "--disallowed-tools"))
_SESSION_IN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# ------------------------------------------------------------ the reducer (§3)


def stamped(event):
    """Whether an event carries the thread stamp: `thread` a non-empty string."""
    t = (event or {}).get("thread")
    return isinstance(t, str) and bool(t)


def passed_by(event, latest_joined):
    """Whether a session's own `event` is absent to every reader: a
    `retired` with reason `ended` that carries no stamp (only a sminos from
    before threads writes one), after a `joined` that does (`latest_joined`,
    the latest `joined` of the session before it in its own order)."""
    return (event.get("kind") == "retired" and event.get("reason") == "ended" and not stamped(event)
            and latest_joined is not None and stamped(latest_joined))


def in_effect(events):
    """The event that decides a session's membership: among its own events,
    in its writer's order, the latest `joined` or `retired` that is not
    passed by; None for a session with none. Read backwards to its latest
    `joined`, which is the latest `joined` before every `retired` after it."""
    after = []
    for e in reversed(events):
        kind = e.get("kind")
        if kind == "joined":
            return next((r for r in after if not passed_by(r, e)), e)
        if kind == "retired":
            after.append(e)
    return after[0] if after else None


def member(events):
    """Whether a session's own events leave it a member."""
    e = in_effect(events)
    return e is not None and e.get("kind") == "joined"


# ------------------------------------------------------------ the stores


def store_dir():
    return os.path.join(sminos.root(), "threads")


def aside_dir():
    return os.path.join(store_dir(), "ended")


def _human_path(tid, aside=False):
    return os.path.join(aside_dir() if aside else store_dir(), tid + ".json")


_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@contextlib.contextmanager
def _locked(path, deadline=None):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "a") as lf:
        sminos.flock_until(lf, deadline)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _human_lock(deadline=None):
    return _locked(os.path.join(store_dir(), ".lock"), deadline)


def _seat_lock(deadline=None):
    return _locked(os.path.join(sminos.root(), ".metalock"), deadline)


_FILES = {}   # path → ((st_ino, st_size, st_mtime_ns), the record read there)


def _valid(rec):
    return (isinstance(rec, dict) and isinstance(rec.get("thread"), str) and _ID_RE.fullmatch(rec["thread"])
            and rec.get("opened") == "human" and isinstance(rec.get("current"), str)
            and isinstance(rec.get("sessions"), list) and all(isinstance(s, str) for s in rec["sessions"]))


def _human_at(path):
    """A human-opened record as its file holds it, read again only once it
    changed (records are written by atomic replace); None for a file that
    is no record."""
    try:
        st = os.stat(path)
    except OSError:
        _FILES.pop(path, None)
        return None
    key = (st.st_ino, st.st_size, st.st_mtime_ns)
    held = _FILES.get(path)
    if held is None or held[0] != key:
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            rec = None
        held = _FILES[path] = (key, rec if _valid(rec) else None)
    return copy.deepcopy(held[1]) if held[1] is not None else None


def _human_files(aside=False):
    d = aside_dir() if aside else store_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return [os.path.join(d, n) for n in sorted(names) if n.endswith(".json") and _ID_RE.fullmatch(n[:-5])]


def store_key():
    """The live thread store as the plane's idle read compares it: each
    record file's stat (a record is written by atomic replace)."""
    out = []
    for p in _human_files():
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.append((os.path.basename(p), st.st_ino, st.st_size, st.st_mtime_ns))
    return tuple(out)


def _of_seat(s):
    """A seat as a thread record (§1): what the seat holds, the keys it
    lacks read with defaults, `sessions` repaired when `current` moved
    without it (an older CLI's refill, the board pipeline), and a seat whose
    `status` is `retired` that holds no `ended` read as ended at its
    `updated`."""
    sessions = [x for x in s.get("sessions") if isinstance(x, str) and x] if isinstance(s.get("sessions"), list) \
        else []
    cur = str(s.get("current") or "")
    if cur and cur not in sessions:
        sessions.append(cur)
    ended = s.get("ended") if isinstance(s.get("ended"), dict) else None
    if ended is None and s.get("status") == "retired":
        ended = {"at": str(s.get("updated") or ""), "reason": "retire", "by": "", "pid": None}
    launch = s.get("launch") if isinstance(s.get("launch"), dict) else {"cwd": str(s.get("cwd") or "")}
    rec = {"thread": s["seat_id"], "opened": "spawned", "sessions": sessions, "current": cur,
           "alias": str(s.get("alias") or ""), "launch": dict(launch),
           "channels": [c for c in s.get("channels") if isinstance(c, str)] if isinstance(s.get("channels"), list)
           else [], "created": str(s.get("created") or ""), "updated": str(s.get("updated") or "")}
    for k in ("stopped", "swept", "released", "pending"):
        if s.get(k):
            rec[k] = copy.deepcopy(s[k])
    if ended is not None:
        rec["ended"] = dict(ended)
    return rec


def _seat_threads():
    return [_of_seat(s) for s in sminos.seats()]


def _human_threads(aside=False):
    return [r for r in (_human_at(p) for p in _human_files(aside)) if r is not None]


def human_threads():
    """The live records of the threads their humans opened."""
    return _human_threads()


def open_threads(human=None, seats=None):
    """This machine's records with an open entry (an entry is never set
    aside); `human` and `seats`, the live records and seats as the caller
    read them."""
    human = _human_threads() if human is None else human
    seats = sminos.seats() if seats is None else seats
    return [_of_seat(s) for s in seats if s.get("pending")] + [t for t in human if t.get("pending")]


def all_threads(ended=False):
    """This machine's threads of both stores; those set aside (ended
    threads its human opened) only on request. A record both live and set
    aside (an end or a return cut between its two writes) is the live one."""
    live = _seat_threads() + _human_threads()
    if not ended:
        return live
    have = {t["thread"] for t in live}
    return live + [t for t in _human_threads(aside=True) if t["thread"] not in have]


def get(thread_id):
    """The thread's record, wherever it is, or None."""
    tid = str(thread_id or "")
    if not tid or not sminos.valid_name(tid):
        return None
    if os.path.exists(sminos.meta_path(tid)):
        s = sminos.reload_seat(tid)
        return _of_seat(s) if s is not None else None
    if not _ID_RE.fullmatch(tid):
        return None
    return _human_at(_human_path(tid)) or _human_at(_human_path(tid, aside=True))


def thread_of(session):
    """The record of the thread `session` is in, or None: in this order, the
    thread whose open entry makes the session its current one; the thread
    whose current session it is, one its human opened before a seat (an
    older CLI can have given such a session a seat); one that had it, those
    set aside included, the latest changed first."""
    if not session:
        return None
    live = all_threads()
    for t in live:
        if t.get("pending") and t["current"] == session:
            return t
    current = [t for t in live if t["current"] == session]
    if current:
        return min(current, key=lambda t: t["opened"] != "human")
    had = [t for t in live if session in t["sessions"]]
    if not had:
        have = {t["thread"] for t in live}
        had = [t for t in _human_threads(aside=True) if session in t["sessions"] and t["thread"] not in have]
    return max(had, key=lambda t: t.get("updated") or "") if had else None


def stamp(session):
    """The thread id an event of this session carries; "" for a session
    that is no thread."""
    return (thread_of(session) or {}).get("thread", "")


def record_ended(record):
    """Whether this machine's record says the thread has ended."""
    return bool((record or {}).get("ended"))


# ------------------------------------------------------------ writing


def _write_human(tid, rec, aside):
    """The record written whole where it belongs, and its other copy gone."""
    os.makedirs(aside_dir(), mode=0o700, exist_ok=True)
    sminos.write_json(_human_path(tid, aside), rec)
    try:
        os.unlink(_human_path(tid, not aside))
    except FileNotFoundError:
        pass


def _change(tid, mutate, deadline=None, bump=False):
    """mutate(view, raw) under the record's store lock, on a fresh read:
    `raw` is the stored object, changed in place; mutate returns False to
    write nothing, or, for a record its human opened, where it goes
    ("live", "aside" or "delete"; True is where it was). For a seat, `bump`
    moves its lifecycle generation (a journaled transition is a lifecycle
    write: a watcher whose snapshot predates it stands down). True when
    something was written."""
    if os.path.exists(sminos.meta_path(tid)):
        with _seat_lock(deadline):
            path = sminos.meta_path(tid)
            try:
                with open(path) as f:
                    raw = json.load(f)
            except (OSError, ValueError):
                return False
            s = sminos.reload_seat(tid)
            if s is None or not isinstance(raw, dict):
                return False
            where = mutate(_of_seat(s), raw)
            if where is False:
                return False
            if where == "delete":
                for p in sminos.seat_files(tid):
                    try:
                        os.unlink(p)
                    except FileNotFoundError:
                        pass
                return True
            if bump:
                raw["gen"] = int(raw.get("gen") or 0) + 1
            sminos._write_record(path, raw)
            return True
    if not _ID_RE.fullmatch(str(tid or "")):
        return False
    with _human_lock(deadline):
        live, aside = _human_path(tid), _human_path(tid, aside=True)
        raw, was = _human_at(live), "live"
        if raw is None:
            raw, was = _human_at(aside), "aside"
        if raw is None:
            return False
        where = mutate(copy.deepcopy(raw), raw)
        if where is False:
            return False
        if where is True:
            where = was
        raw["updated"] = sminos.now()
        if where == "delete":
            for p in (live, aside):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
            return True
        _write_human(tid, raw, where == "aside")
        return True


def update(thread_id, fields, remove=(), guard=None, lock_until=None):
    """A change that owes no event (the stop mark, `swept`, a launch noted,
    the alias's copy, CH's channels): merged under the store's lock, applied
    only if guard(record) holds. Never a key a journaled operation owns."""
    if set(fields) & set(JOURNALED) or set(remove) & set(JOURNALED):
        raise ValueError("update() never writes %s" % ", ".join(sorted((set(fields) | set(remove)) & set(JOURNALED))))

    def mutate(view, raw):
        if guard is not None and not guard(view):
            return False
        if view["opened"] == "spawned" and "alias" in fields:
            return False   # a seat's alias is the seat's own
        for k, v in fields.items():
            raw[k] = copy.deepcopy(v)
        for k in remove:
            raw.pop(k, None)
        return True

    return _change(thread_id, mutate, lock_until)


def note_launch(thread_id, cwd, options=None, lock_until=None):
    """The launch of the engine process that last started the thread's
    current session: its directory and, when they could be read, its
    options (launch_options); `options` absent means unknown, never none."""
    launch = {"cwd": str(cwd or ""), "at": sminos.now()}
    if options is not None:
        launch["options"] = list(options)
    return update(thread_id, {"launch": launch}, lock_until=lock_until)


def set_channels(thread_id, channels):
    """CH's writer of the declared channels."""
    return update(thread_id, {"channels": [str(c) for c in channels]})


def note_alias(session, alias, lock_until=None):
    """The alias a human-opened thread's latest `joined` or `renamed` carried,
    copied into its record for readers without the log (lifecycle)."""
    t = thread_of(session)
    if t is None or t["opened"] != "human" or t["current"] != session or t.get("alias") == alias:
        return False
    return update(t["thread"], {"alias": alias}, guard=lambda r: r["current"] == session, lock_until=lock_until)


# ------------------------------------------------------------ making a record


def _seat_sessions(seat, project, events):
    """Every session a seat from before threads has had, oldest first: its
    `history`, the sessions whose `joined` in the project's log names the
    seat, the hand-offs among them (lineage_of), then its current one."""
    out = [str(h.get("current") or "") for h in seat.get("history") or [] if isinstance(h, dict)]
    if project is not None:
        evs = events if events is not None else sminos.log_read(project, kinds=sminos.MEMBERSHIP)
        out += [e["session"] for e in sorted((e for e in evs if e.get("kind") == "joined"
                                              and e.get("seat") == seat["seat_id"] and isinstance(e.get("session"), str)
                                              and sminos.writer_session(e["writer"]) == e["session"]),
                                             key=lambda e: e["ts"])]
        for s in list(out) + [seat["current"]]:
            if s:
                out += list(reversed(sminos.lineage_of(project, s, events=events)))
    out.append(seat["current"])
    seen, kept = set(), []
    for s in out:
        if s and sminos.UUID_RE.fullmatch(s) and s not in seen and s != seat["current"]:
            seen.add(s)
            kept.append(s)
    return kept + ([seat["current"]] if seat["current"] else [])


def _ensure_seat(seat, project, events, deadline):
    """A seat's thread keys, added when it has none (a seat from before
    threads, adopted; or one just made), and `current` added to `sessions`
    when it moved without it."""
    tid = seat["seat_id"]
    if "opened" in seat and seat["current"] in (seat.get("sessions") or []):
        return _of_seat(seat)
    project = project if project is not None else (sminos.seat_project(seat) if seat["current"] else None)
    rebuilt = None if "opened" in seat else _seat_sessions(seat, project if not sminos.guessed(project) else None,
                                                           events)

    def mutate(view, raw):
        if "opened" not in raw:
            raw["opened"] = "spawned"
            raw["sessions"] = rebuilt if rebuilt is not None else view["sessions"]
            raw.setdefault("launch", {"cwd": str(raw.get("cwd") or "")})
            raw.setdefault("channels", [])
        elif view["current"] and view["current"] not in (raw.get("sessions") or []):
            raw["sessions"] = view["sessions"]
        else:
            return False
        return True

    _change(tid, mutate, deadline)
    return get(tid)


def _create_human(session, sessions, cwd, deadline):
    """A record for a session no thread holds, under a minted id; under the
    store's lock the store is read again, and the record that holds the
    session by then (another process made it, or an ended one had it) is
    the answer instead."""
    with _human_lock(deadline):
        for t in _human_threads() + _human_threads(aside=True):
            if t["current"] == session or session in t["sessions"]:
                return t
        at = sminos.now()
        rec = {"v": V, "thread": str(uuid.uuid4()), "opened": "human", "sessions": sessions, "current": session,
               "alias": "", "launch": {"cwd": cwd, "at": at}, "channels": [], "created": at, "updated": at}
        os.makedirs(aside_dir(), mode=0o700, exist_ok=True)
        sminos.write_json(_human_path(rec["thread"]), rec)
        return rec


def ensure(session, seat=None, project=None, events=None, lock_until=None):
    """The record of the thread the session fills, made when there is none:
    for a seat, its seat record's keys (`project` and `events`, the log its
    earlier sessions are found in); for a session no seat holds, a record
    in the thread store under a minted id, whose `sessions` are its
    continuation chain in `project`'s log (`events`) when one is given — an
    adoption — and the session alone otherwise. None for a lane B session.
    A spawn's child that no seat holds yet is the caller's to leave alone
    first (awaits_seat). LockBusy past `lock_until`, nothing written."""
    if seat is not None:
        return _ensure_seat(seat, project, events, lock_until)
    have = thread_of(session)
    if have is not None:
        return have
    if sminos.records_module().lane_of(sminos.records_module().read(session)) != "A":
        return None
    chain = list(reversed(sminos.lineage_of(project, session, events=events))) if project is not None else []
    cwd = sminos.launch_cwd(session, fallback=str((sminos.session_running(session) or {}).get("cwd") or ""))
    return _create_human(session, [s for s in chain if s != session] + [session], cwd, lock_until)


def spawner_bound():
    """How long a spawn's child that no seat holds is given before it joins
    as any session does, counted from its process's start: twice the
    launcher's own wait for its session's id (poll_uuid: its iterations
    times poll_interval; 120 s as shipped)."""
    iterations = int(os.environ.get("SMINOS_UUID_POLL") or os.environ.get("DAEMON_UUID_POLL") or "30")
    return 2 * iterations * sminos.poll_interval()


def _young(peer):
    started = sminos.process_started(peer or {}) if peer else None
    return started is not None and time.time() - started < spawner_bound()


def awaits_seat(session, peer, own):
    """Whether a session no seat holds is a spawn's child its launcher has
    not named yet, which makes no record and writes no `joined` (§8).
    `own`: the caller runs for that session (its hook, a verb of its own),
    whose environment carries its launch's token (SMINOS_LAUNCH) when a
    spawn started it. The token counts while its launch is pending, or the
    process is younger than the spawner's bound, and stops counting once it
    is positively gone: bound to another session (a `claude` started from a
    seat's shell inherits it), or neither pending nor young (a launcher that
    failed). Another process sees no token: it waits on a background
    session younger than the bound."""
    records = sminos.records_module()
    if not own:
        return str((peer or {}).get("kind") or "") == "bg" and _young(peer)
    token = os.environ.get(records.LAUNCH_ENV, "")
    if not records.LAUNCH_RE.fullmatch(token):
        return False
    bound = records.bound_to(token)
    if bound and bound != session:
        return False
    return os.path.exists(records.pending_path(token)) or _young(peer)


def returns(record, peer):
    """Whether a process holding an ended thread's session returns it (§6,
    row 12): one the end did not see. An end by the rule saw none; a retire
    saw the process it recorded, which runs on in its human's terminal: only
    another pid, or one started after the end, returns it."""
    ended = (record or {}).get("ended") or {}
    if not ended:
        return False
    if ended.get("reason") != "retire":
        return True
    peer = peer or {}
    if ended.get("pid") not in (None, "") and str(ended["pid"]) != str(peer.get("pid")):
        return True
    started, at = sminos.process_started(peer), sminos._ts_epoch(ended.get("at"))
    return started is not None and at is not None and started > at


# ------------------------------------------------------------ the journal (§6)


def begin(thread_id, op, project, events, fields=None, remove=(), guard=None, lock_until=None, **more):
    """The one way a journaled operation starts: under the store's lock,
    when the record has no open entry and guard(record) holds, the record's
    change (`fields` merged, `remove` dropped; a return brings a record set
    aside back) and the entry, in one write. Each event owed is whole (its
    kind, its session, its fields), stamped with the thread when it names
    no thread of its own. `more`: the entry's other keys (`settle`, `last`,
    `other`). The entry as written, None when nothing was."""
    if op not in OPS:
        raise ValueError("not a journaled operation: %r" % (op,))
    owed = []
    for e in events:
        e = dict(e)
        if not stamped(e):
            e["thread"] = thread_id
        owed.append(e)
    entry = {"id": uuid.uuid4().hex, "op": op, "at": sminos.now(), "project": project.id, "events": owed,
             **{k: v for k, v in more.items() if v is not None}}

    def mutate(view, raw):
        if view.get("pending") or (guard is not None and not guard(view)):
            return False
        for k, v in (fields or {}).items():
            raw[k] = copy.deepcopy(v)
        for k in remove:
            raw.pop(k, None)
        raw["pending"] = entry
        return "live" if op == "return" else True

    return entry if _change(thread_id, mutate, lock_until, bump=True) else None


def _holds(project, session, kind, op):
    return any(x["kind"] == kind and x.get("op") == op for x in sminos.own_events_of(project, session))


def _owe(project, entry, event, appended, append):
    """One event the entry owes, appended unless the session's own events
    hold one of its kind under the entry's id already, whoever appended it;
    whether the log holds it now."""
    kind, session = event["kind"], event["session"]
    fields = {k: v for k, v in event.items() if k not in ("kind", "session", "op")}

    def none_yet(evs):
        return not any(x["kind"] == kind and x.get("op") == entry["id"] for x in evs)

    got = append(project, session, kind, guard=none_yet, required=False, op=entry["id"], **fields)
    appended += got
    return bool(got) or _holds(project, session, kind, entry["id"])


def finish(thread_id, appended=None, project=None, append=None):
    """Carries out the record's open entry from where it stands, and clears
    it (§6, steps 2 to 4): each event the log does not hold yet; then, in
    one write, the entry removed and an end's record set aside or deleted
    as its `last` says, an absorption's other record deleted first. True
    when the record has no open entry left. `appended`, a list, gains the
    events appended. `project`: the caller's, when it is the entry's (a
    project need not be registered here to be resolved); else the entry's
    is looked up. `append`: the caller's sminos.lifecycle (a test may load
    its own copy of sminos, whose view cache an append must clear)."""
    appended = [] if appended is None else appended
    t = get(thread_id)
    entry = (t or {}).get("pending")
    if not entry:
        return True
    if project is None or project.id != entry.get("project"):
        project = sminos.known_project(str(entry.get("project") or ""))
    if project is None:
        return False
    for event in entry.get("events") or []:
        if not _owe(project, entry, event, appended, append or sminos.lifecycle):
            return False
    # What is held for `settle` is settled here once the hold exists (M3).
    if entry.get("op") == "absorb" and entry.get("other"):
        _change(entry["other"], lambda view, raw: "delete" if view["opened"] == "human" else False)

    def clear(view, raw):
        if (view.get("pending") or {}).get("id") != entry["id"]:
            return False
        raw.pop("pending", None)
        last = entry.get("last")
        if last == "purge":
            return "delete"
        if last == "aside" and view["opened"] == "human":
            return "aside"
        return True

    _change(thread_id, clear)
    return not (get(thread_id) or {}).get("pending")


def open_entries(project, human=None, seats=None):
    """The records of this machine whose open entry's events go to the
    project's log."""
    return [t for t in open_threads(human, seats) if (t.get("pending") or {}).get("project") == project.id]


# ------------------------------------------------------------ a launch's options


def launch_options(argv):
    """The option tokens of an engine's argument vector that `launch.options`
    keeps (LAUNCH_OPTIONS), in order, each `--name=value` as two tokens; an
    option whose value is inline JSON, or names a session, is dropped whole."""
    out, i, args = [], 1, list(argv or [])
    while i < len(args):
        tok = args[i]
        i += 1
        name, eq, inline = tok.partition("=") if tok.startswith("--") else (tok, "", "")
        if name not in LAUNCH_OPTIONS:
            continue
        if name in _FLAGS:
            if not eq:
                out.append(name)
            continue
        values = [inline] if eq else []
        if not eq:
            while i < len(args) and not args[i].startswith("-"):
                values.append(args[i])
                i += 1
                if name not in _MANY:
                    break
        if not values or any(_secretive(v) for v in values):
            continue
        out += [name] + values
    return out


def _secretive(value):
    v = value.strip()
    return v[:1] in ("{", "[") or bool(_SESSION_IN.search(v))


def process_argv(pid):
    """A process's argument vector with its exact boundaries: the kernel's
    (KERN_PROCARGS2) on macOS, /proc/<pid>/cmdline on Linux; None when it
    cannot be read."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 1:
        return None
    if sys.platform == "darwin":
        return _darwin_argv(pid)
    try:
        with open(os.path.join(sminos.PROC, str(pid), "cmdline"), "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if not raw:
        return None
    return [a.decode("utf-8", "surrogateescape") for a in raw.rstrip(b"\0").split(b"\0")]


def _darwin_argv(pid):
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        sysctl = libc.sysctl
        sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
        sysctl.restype = ctypes.c_int
        argmax = ctypes.c_int(0)
        size = ctypes.c_size_t(ctypes.sizeof(argmax))
        mib = (ctypes.c_int * 2)(1, 8)   # CTL_KERN, KERN_ARGMAX
        if sysctl(mib, 2, ctypes.byref(argmax), ctypes.byref(size), None, 0) != 0 or argmax.value <= 0:
            return None
        buf = ctypes.create_string_buffer(argmax.value)
        size = ctypes.c_size_t(argmax.value)
        mib = (ctypes.c_int * 3)(1, 49, pid)   # CTL_KERN, KERN_PROCARGS2
        if sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
            return None
    except (ImportError, OSError, AttributeError):
        return None
    raw = buf.raw[:size.value]
    if len(raw) < 4:
        return None
    argc, = struct.unpack_from("=i", raw, 0)
    rest = raw[4:]
    end = rest.find(b"\0")   # the executable's path, then NUL padding, then argv
    if end < 0:
        return None
    rest = rest[end:].lstrip(b"\0")
    parts = rest.split(b"\0")
    if argc <= 0 or len(parts) < argc:
        return None
    return [p.decode("utf-8", "surrogateescape") for p in parts[:argc]]
