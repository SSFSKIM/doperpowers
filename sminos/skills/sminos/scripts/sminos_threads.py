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
# The mark an absorption leaves, as an entry, on the record it absorbs while
# its own entry is open (finish): never begun, so no other operation starts
# there, update() leaves it alone, and the hook reads it as an open entry.
RESERVED = "reserved"
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


class Fold:
    """The reducer folded one event at a time: the one place membership's
    state moves. Each session's own `joined` and `retired` events are added
    in its writer's order; `effect` holds, per session, the event in effect
    (the latest not passed by), `joined` its latest `joined`. in_effect is
    a fold of one session's events; a reader that reads a whole log in one
    pass folds every session's in one (sminos._memberships, _projection,
    _lineage_scan)."""
    __slots__ = ("effect", "joined")

    def __init__(self):
        self.effect, self.joined = {}, {}

    def add(self, session, event):
        """Folds one own `joined` or `retired` of `session`: the event when
        it takes effect, None when it is passed by."""
        if event["kind"] == "joined":
            self.joined[session] = event
        elif event.get("reason") == "ended" and passed_by(event, self.joined.get(session)):
            return None
        self.effect[session] = event
        return event


def in_effect(events):
    """The event that decides a session's membership: among its own events,
    in its writer's order, the latest `joined` or `retired` that is not
    passed by; None for a session with none. Folded from its latest
    `joined` on (what came before it no longer decides anything)."""
    start = 0
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("kind") == "joined":
            start = i
            break
    fold = Fold()
    for e in events[start:]:
        if e.get("kind") in ("joined", "retired"):
            fold.add("", e)
    return fold.effect.get("")


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


# Taking both stores' locks, the seats' comes first, never the reverse: a
# seat that takes a session as its current one (begin) and a human-opened
# record made for it (_create_human) each read the other store under both.


def _finish_lock(thread_id, deadline=None):
    """The record's own finisher lock (finish): one finisher of a record at a
    time, whichever store the record is in; beside the thread store's lock,
    where no sminos from before threads looks."""
    return _locked(os.path.join(store_dir(), ".finish", thread_id + ".lock"), deadline)


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


def _is_thread(seat):
    """Whether a seat is a thread (§1): one with the thread keys, one with no
    session, or one whose session is lane A. A seat with no keys holding a
    lane B session (`seat add` made it for one; or one from before threads)
    is none, as a lane B session has no record (D1): no lookup of the
    store answers it (all_threads, get, thread_of)."""
    return "opened" in seat or not seat.get("current") or _lane_a(seat["current"])


def _seat_threads():
    return [_of_seat(s) for s in sminos.seats() if _is_thread(s)]


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
    return [_of_seat(s) for s in seats if s.get("pending") and _is_thread(s)] + [t for t in human if t.get("pending")]


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
        return _of_seat(s) if s is not None and _is_thread(s) else None
    if not _ID_RE.fullmatch(tid):
        return None
    return _human_at(_human_path(tid)) or _human_at(_human_path(tid, aside=True))


_ASIDE = []   # [the set-aside store's stat key, {session: [thread ids of the records set aside that had it]}]
RACY_NS = 1_000_000_000   # a listing is kept once its directory held still this long before it (a coarse clock)


def _aside_index():
    """{session: [thread ids]} of the records set aside, each session under
    every record that had it: the set-aside store grows with every end, so
    it is read whole again only once its directory moved (a record goes in
    or out, or is written, by a rename there), and an index taken while it
    may still move is not kept."""
    d = aside_dir()
    before = time.time_ns()
    try:
        st = os.stat(d)
    except OSError:
        return {}
    key = (st.st_ino, st.st_mtime_ns)
    if _ASIDE and _ASIDE[0] == key:
        return _ASIDE[1]
    index = {}
    for t in _human_threads(aside=True):
        for x in t["sessions"] + [t["current"]]:
            if x and t["thread"] not in index.setdefault(x, []):
                index[x].append(t["thread"])
    _ASIDE[:] = [key, index] if before - st.st_mtime_ns >= RACY_NS else []
    return index


def _aside_holding(session, live):
    have = {t["thread"] for t in live}
    out = []
    for tid in _aside_index().get(session, ()):
        t = _human_at(_human_path(tid, aside=True)) if tid not in have else None
        if t is not None and (t["current"] == session or session in t["sessions"]):
            out.append(t)
    return out


def thread_of(session, ended=True):
    """The record of the thread `session` is in, or None: in this order, the
    thread whose open entry makes the session its current one; the thread
    whose current session it is, one its human opened (set aside or not)
    before a seat (an older CLI can have given such a session a seat); one
    that had it: a live one, the latest changed, else one set aside, the
    latest changed. A session one only had is that thread's for a lookup
    (the stamp of an event about it, a name); a process that runs it again
    makes it a thread of its own (ensure). The records set aside are looked
    up through their index (_aside_index), and not at all with `ended`
    False (stamp)."""
    if not session:
        return None
    live = all_threads()
    first = _live_rule(session, live)
    if first is not None:
        return first
    current = [t for t in live if t["current"] == session]
    aside = _aside_holding(session, live) if ended else []
    human = [t for t in aside if t["current"] == session]
    if human:
        return max(human, key=lambda t: t.get("updated") or "")
    if current:
        return current[0]
    had = [t for t in live if session in t["sessions"]] or aside
    return max(had, key=lambda t: t.get("updated") or "") if had else None


def stamp(session):
    """The thread id an event of this session carries; "" for a session
    that is no thread. From the live stores and their open entries alone,
    never the records set aside: after an end, what a session's thread
    writes is the journal's (or a return's), each event naming its thread,
    and a former session that runs again is another thread."""
    return (thread_of(session, ended=False) or {}).get("thread", "")


def _live_rule(session, live):
    """thread_of's first two rules, over the live records `live` (seats
    first, as all_threads lists them): the first record whose open entry,
    not a reservation, makes the session its current one; else the
    human-opened record whose current session it is (one before a seat an
    older CLI gave it). None when neither: the one rule thread_of and the
    hold's index (_live_index) share."""
    for t in live:
        if t.get("pending") and not reservation(t) and t["current"] == session:
            return t
    return next((t for t in live if t["current"] == session and t["opened"] == "human"), None)


def hold_of(session, fresh=False):
    """Whether this machine holds delivery for a session (Interfaces §5): ""
    when it delivers to the session or wakes it; "human" when it holds, for a
    thread its human opened that has not ended, whose current session it is
    and no process holds (the hold: what is addressed to it is recorded and
    stays owed, and no process is started for it until its human reopens
    it). T2 adds its reasons. The record is thread_of's for the session
    (from the live stores: an ended thread is not held, what is owed to it
    is settled; a seat is a spawned thread), through its index. `fresh`, at
    a boundary that would push or ask (a delivery, a verdict's handler, the
    uplink's question): the engine's records read afresh (sminos.running_now),
    since a live pid alone is no evidence that its process still runs this
    session (a `/clear` moves the same process to another id), and the
    record is thread_of's own, read from the stores as they are, not the
    index's (hold_now)."""
    if not session:
        return ""
    # The live stores alone, fresh or not: an ended record holds nothing, so the archive is never read here.
    t = thread_of(session, ended=False) if fresh else _live_index().get(session)
    if t is None or t["opened"] != "human" or t["current"] != session or record_ended(t) or reservation(t):
        return ""
    return "" if (sminos.running_now if fresh else sminos.session_running)(session) else "human"


def hold_now(session):
    """The fresh hold (hold_of with `fresh`): what every push, every ask and
    every counted attempt asks last, under the delivery lock where one is
    held."""
    return hold_of(session, fresh=True)


_LIVE = []   # [the cache generation it was checked in, the stores' stat key, {current session: record}]


def _live_index():
    """{current session: record} as thread_of reads it from the live stores
    (_live_rule, the one rule both read), for the sessions some live record
    names as current:
    the delivery pass, a view's alias selection and the publication of a
    stopped session's state ask it of every member. Checked once per cache
    generation (sminos.forget_caches: an invocation, a tick) and on this
    process's own writes (_forget_live); read whole again only once a
    store's directory moved (a record is written by a rename there: the
    thread store's, or the root the seats are in), and not kept while one
    may still move (as _aside_index). Of the seats only those with an open
    entry are read: no other seat outranks a human-opened record."""
    gen = sminos._GENERATION[0]
    if _LIVE and _LIVE[0] == gen:
        return _LIVE[2]
    before = time.time_ns()
    try:
        st = os.stat(store_dir())
    except OSError:
        st = None
    try:
        rt = os.stat(sminos.root())
    except OSError:
        rt = None
    key = tuple((x.st_ino, x.st_mtime_ns) if x else None for x in (st, rt))
    if _LIVE and _LIVE[1] == key:
        _LIVE[0] = gen
        return _LIVE[2]
    human = _human_threads() if st else []
    seats = [_of_seat(x) for x in sminos.seats() if x.get("pending") and _is_thread(x)] if rt else []
    by_current = {}
    for t in seats + human:   # grouped by current session, each group in all_threads' order (seats first)
        if t["current"]:
            by_current.setdefault(t["current"], []).append(t)
    index = {}
    for cur, records in by_current.items():
        t = _live_rule(cur, records)
        if t is not None:
            index[cur] = t
    newest = max((x.st_mtime_ns for x in (st, rt) if x), default=0)
    _LIVE[:] = [gen, key, index] if before - newest >= RACY_NS else []
    return index


def _forget_live():
    _LIVE.clear()


def released_alias(session, peer=None):
    """The alias a human-opened thread whose current session is `session`
    gave up at a `/clear` (its record's `released`, §1), "" for none: alias
    selection refuses that name to the session while it stands
    (sminos.held_alias, sminos.shadowing), and stops when a process started
    after the release holds the session (`peer`, its engine record; the
    sweep then removes the mark). Through the live store's index."""
    released = (_live_index().get(session) or {}).get("released") if session else None
    if not isinstance(released, dict):
        return ""
    if peer and release_outlived(released, peer):
        return ""
    return str(released.get("alias") or "")


def release_outlived(released, peer):
    """Whether the process of `peer` (an engine record) started after the
    release `released` (a record's `released`): it ends the release (§6,
    row 8)."""
    started, at = sminos.process_started(peer or {}), sminos._ts_epoch((released or {}).get("at"))
    return started is not None and at is not None and started > at


def reservation(record):
    """The mark of the absorption that holds `record` (RESERVED), or None."""
    entry = (record or {}).get("pending") or {}
    return entry if entry.get("op") == RESERVED else None


def record_ended(record):
    """Whether this machine's record says the thread has ended."""
    return bool((record or {}).get("ended"))


def absorbable(record, session):
    """Whether a thread that goes on in `session` may absorb `record`, the
    record that session got of its own before its hand-off was read
    (Interfaces §6, row 5): one its human opened, not ended, holding that
    one session, with no open entry. Read before anything of reach is
    carried."""
    return (record is not None and record["opened"] == "human" and not record_ended(record)
            and record["current"] == session and record["sessions"] == [session] and not record.get("pending"))


# ------------------------------------------------------------ writing


def _write_human(tid, rec, aside):
    """The record written whole where it belongs, and its other copy gone."""
    os.makedirs(aside_dir(), mode=0o700, exist_ok=True)
    sminos.write_json(_human_path(tid, aside), rec)
    try:
        os.unlink(_human_path(tid, not aside))
    except FileNotFoundError:
        pass
    _forget_live()


def _change(tid, mutate, deadline=None, bump=False, both=False):
    """mutate(view, raw) under the record's store lock, on a fresh read:
    `raw` is the stored object, changed in place; mutate returns False to
    write nothing, or, for a record its human opened, where it goes
    ("live", "aside" or "delete"; True is where it was). For a seat, `bump`
    moves its lifecycle generation (a journaled transition is a lifecycle
    write: a watcher whose snapshot predates it stands down), and `both`
    holds the thread store's lock too, taken after the seats' (a change that
    takes a session reads both stores and writes under both: _claimed).
    True when something was written."""
    if os.path.exists(sminos.meta_path(tid)):
        with _seat_lock(deadline), (_human_lock(deadline) if both else contextlib.nullcontext()):
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
                # The record, which carries the journal, last: a cut leaves the entry to replay.
                for p in reversed(sminos.seat_files(tid)):
                    try:
                        os.unlink(p)
                    except FileNotFoundError:
                        pass
                _forget_live()
                return True
            if bump:
                raw["gen"] = int(raw.get("gen") or 0) + 1
            sminos._write_record(path, raw)
            _forget_live()
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
            for p in (aside, live):   # the live copy, which carries an open entry, last
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
            _forget_live()
            return True
        _write_human(tid, raw, where == "aside")
        return True


def update(thread_id, fields, remove=(), guard=None, lock_until=None):
    """A change that owes no event (the stop mark, `swept`, a launch noted,
    the alias's copy, CH's channels, the end of a release: `released`
    removed once a process started after it holds the session): merged under
    the store's lock, applied only if guard(record) holds and the record has
    no open entry. Never a key a journaled operation owns, but that
    removal."""
    owned = (set(fields) & set(JOURNALED)) | (set(remove) & (set(JOURNALED) - {"released"}))
    if owned:
        raise ValueError("update() never writes %s" % ", ".join(sorted(owned)))

    def mutate(view, raw):
        if view.get("pending") or (guard is not None and not guard(view)):
            return False   # nothing else changes a record while its entry is open (§6, 6)
        if view["opened"] == "spawned" and "alias" in fields:
            return False   # a seat's alias is the seat's own
        for k, v in fields.items():
            raw[k] = copy.deepcopy(v)
        for k in remove:
            raw.pop(k, None)
        return True

    return _change(thread_id, mutate, lock_until)


def launch_of(cwd, options=None):
    """A record's `launch`: the directory of the engine process that last
    started the thread's current session and, when they could be read, its
    options (launch_options); `options` absent means unknown, never none."""
    launch = {"cwd": str(cwd or ""), "at": sminos.now()}
    if options is not None:
        launch["options"] = list(options)
    return launch


def note_launch(thread_id, cwd, options=None, lock_until=None):
    """The launch noted on its own (launch_of), a change that owes no event."""
    return update(thread_id, {"launch": launch_of(cwd, options)}, lock_until=lock_until)


def set_channels(thread_id, channels):
    """CH's writer of the declared channels."""
    return update(thread_id, {"channels": [str(c) for c in channels]})


def note_alias(session, alias, lock_until=None):
    """The alias a human-opened thread's latest `joined` or `renamed` carried,
    copied into its record for readers without the log (lifecycle)."""
    t = thread_of(session, ended=False)
    if t is None or t["opened"] != "human" or t["current"] != session or t.get("alias") == alias:
        return False
    return update(t["thread"], {"alias": alias}, guard=lambda r: r["current"] == session, lock_until=lock_until)


# ------------------------------------------------------------ making a record


def _seat_sessions(seat, project, events):
    """Every session a seat from before threads has had, oldest first, its
    current one last: those its `history` names (the last ten occupants),
    those whose `joined` in the project's log names the seat (an occupant
    older than the history's window among them), and the hand-offs that
    led to each (lineage_of). Ordered by when each first shows: its first
    own membership event in the log; a history entry the log does not hold
    by the time it ended, else after the one before it."""
    cur = seat["current"]
    history = [str(h.get("current") or "") for h in seat.get("history") or [] if isinstance(h, dict)]
    ended = {str(h.get("current") or ""): str(h.get("ended") or "") for h in seat.get("history") or []
             if isinstance(h, dict)}
    first, found = {}, list(history)
    if project is not None:
        evs = events if events is not None else sminos.log_read(project, kinds=sminos.MEMBERSHIP)
        for e in evs:
            x = e.get("session")
            if e.get("kind") in sminos.MEMBERSHIP and isinstance(x, str) and sminos.writer_session(e["writer"]) == x:
                first[x] = min(first.get(x) or e["ts"], e["ts"])
                if e["kind"] == "joined" and e.get("seat") == seat["seat_id"]:
                    found.append(x)
        for x in list(found) + [cur]:
            if x:
                found += list(reversed(sminos.lineage_of(project, x, events=events)))
    keys, at = {}, ""
    for i, x in enumerate(history):   # a history entry the log lacks keeps its place after the one before it
        at = first.get(x) or ended.get(x) or at
        keys[x] = (at, i)
    kept = []
    for x in found:
        if x and x != cur and sminos.UUID_RE.fullmatch(x) and x not in kept:
            kept.append(x)
    kept.sort(key=lambda x: (first[x], -1) if x in first else keys.get(x, ("", -1)))
    return kept + ([cur] if cur else [])


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
    """A record for a session no thread holds as its current one, under a
    minted id. Under both stores' locks (the seats' first) both are read
    again, and the record whose current session it is by then is the answer
    instead: a seat that took it (a refill, a hand-off's advance, an open
    entry making it current), another process's record, or an ended one."""
    with _seat_lock(deadline), _human_lock(deadline):
        for seat in sminos.seats():
            if seat["current"] == session and _is_thread(seat):
                return _of_seat(seat)
        live = _human_threads()
        for t in live + _aside_holding(session, live):
            if t["current"] == session:
                return t
        at = sminos.now()
        rec = {"v": V, "thread": str(uuid.uuid4()), "opened": "human", "sessions": sessions, "current": session,
               "alias": "", "launch": {"cwd": cwd, "at": at}, "channels": [], "created": at, "updated": at}
        os.makedirs(aside_dir(), mode=0o700, exist_ok=True)
        sminos.write_json(_human_path(rec["thread"]), rec)
        _forget_live()
        return rec


def claim_seat(seat_id, record, deadline=None):
    """A new seat record holding `record["current"]`, written under both
    stores' locks (the seats' first) only while no human-opened record,
    live or set aside, has that session current: `seat add --session`'s
    claim and a record made for the session (_create_human) are one at a
    time. False when one has it, another seat holds it as current (an open
    entry's making it current included), or the seat's file exists;
    nothing written."""
    session = record["current"]
    with _seat_lock(deadline), _human_lock(deadline):
        path = sminos.meta_path(seat_id)
        if os.path.exists(path) or _holder(session, seat_id) is not None:
            return False
        sminos._write_record(path, {**record, "gen": 1})
        return True


def repoint_seat(seat_id, fields, deadline=None):
    """An existing seat given `fields["current"]` by a plain write (no event
    owed: `seat add --session` where no journal applies), under both stores'
    locks only while no other record holds that session (_holder), as every
    claim; its lifecycle generation moved. False, nothing written, when one
    does or the seat is gone."""
    session = fields["current"]
    with _seat_lock(deadline), _human_lock(deadline):
        path = sminos.meta_path(seat_id)
        try:
            with open(path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return False
        if not isinstance(raw, dict) or _holder(session, seat_id) is not None:
            return False
        raw.update(fields)
        raw["gen"] = int(raw.get("gen") or 0) + 1
        sminos._write_record(path, raw)
        return True


def ensure(session, seat=None, project=None, events=None, lock_until=None):
    """The record of the thread the session fills, made when there is none:
    for a seat, its seat record's keys (`project` and `events`, the log its
    earlier sessions are found in); for a session no seat holds, a record
    in the thread store under a minted id, whose `sessions` are its
    continuation chain in `project`'s log (`events`) when one is given — an
    adoption — and the session alone otherwise. A session a thread only had
    (one it handed off, a seat's replaced occupant) that runs again is
    another thread (Interfaces §6, row 15): it gets a record of its own, and
    the thread that went on keeps it in its `sessions`. A thread is
    established for a lane A session alone: for a lane B session, the live record it
    has (its end is stamped: §6, row 13), else None, never one set aside. A spawn's child that no seat holds yet is the caller's to leave
    alone first (awaits_seat). LockBusy past `lock_until`, nothing written."""
    if seat is not None:
        if not _is_thread(seat):
            return None
        return _ensure_seat(seat, project, events, lock_until)
    if not _lane_a(session):
        # A lane B session is never made a thread, nor returned: only a live record it has is its own.
        return thread_of(session, ended=False)
    have = thread_of(session)
    if have is not None and have["current"] == session:
        return have
    chain = list(reversed(sminos.lineage_of(project, session, events=events))) if project is not None else []
    cwd = sminos.launch_cwd(session, fallback=str((sminos.session_running(session) or {}).get("cwd") or ""))
    return _create_human(session, [s for s in chain if s != session] + [session], cwd, lock_until)


def _lane_a(session):
    records = sminos.records_module()
    return records.lane_of(records.read(session)) == "A"


lane_a = _lane_a


def choose(session, seat=None, project=None, events=None, peer=None, lock_until=None):
    """The one choice of the thread a session joins or returns under, for
    every join (sminos.join_on_sight) and adoption (sminos.adopt): (thread,
    action), action `join` (thread None: an unstamped join), `return` (the
    journaled return of an ended record, §6 row 12) or `hold` (nothing is
    joined: an ended record the process does not return, or a seat an older
    copy retired, which a fill returns).

    A lane B session revives no thread: it keeps a live record it has (its
    end stamped, row 13), never one set aside, and makes none. A lane A
    session's thread is §1's: a human-opened record whose current session
    it is, set aside or not, before a seat (an older copy can have seated
    such a session; the seat is then left as it is); else ensure()'s, which
    makes the record when there is none. A spawned thread this code ended
    returns as a human-opened one does (seat_ended): by a process its end
    did not see. LockBusy past `lock_until`."""
    if not _lane_a(session):
        t = thread_of(session, ended=False)
        return (t, "hold") if t is not None and record_ended(t) else (t, "join")
    t = thread_of(session)
    if t is None or t["opened"] != "human" or t["current"] != session:
        t = ensure(session, seat, project, events, lock_until)
    if t is None or not record_ended(t):
        return t, "join"
    if t["current"] == session and (t["opened"] == "human" or seat_ended(t)) and returns(t, peer):
        return t, "return"
    return t, "hold"


def seat_ended(record):
    """Whether a spawned thread's end is this code's, held in its seat
    record (`ended`): its human reopening its session returns it (M4). A
    seat an older copy retired (its `status` alone: read as ended, §1) is
    returned by a fill alone, as it was: what that copy's retire saw of a
    process, nothing on the record says."""
    seat = sminos.reload_seat(record["thread"]) if record and record["opened"] == "spawned" else None
    return isinstance((seat or {}).get("ended"), dict)


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
    """Whether the process of `peer` (an engine record), holding an ended
    thread's session, returns it (§6, row 12): one the end did not see. An
    end that recorded no process (the rule, a retire of a stopped thread)
    saw none, so any process returns it: one that started a moment before
    the end, unseen by its check, must not stay ended while it runs. An end
    that recorded one (a retire of a running session, a self-retire) is
    returned by another pid, or by one started after the end: the process
    the retire saw runs on in its human's terminal and does not."""
    ended = (record or {}).get("ended") or {}
    peer = peer or {}
    if not ended or not peer.get("pid"):
        return False
    if ended.get("pid") in (None, ""):
        return True
    if str(ended["pid"]) != str(peer.get("pid")):
        return True
    started, at = sminos.process_started(peer), sminos._ts_epoch(ended.get("at"))
    return started is not None and at is not None and started > at


# ------------------------------------------------------------ the journal (§6)


def begin(thread_id, op, project, events, fields=None, remove=(), guard=None, lock_until=None, absorbs=False,
          **more):
    """The one way a journaled operation starts: under the store's lock,
    when the record has no open entry and guard(record) holds, the record's
    change (`fields` merged, `remove` dropped; a return brings a record set
    aside back) and the entry, in one write. Each event owed is whole (its
    kind, its session, its fields), stamped with the thread when it names
    no thread of its own. `more`: the entry's other keys (`settle`, `last`,
    `other`, `carry`). A `current` the change sets is added to `sessions`,
    last (an advance, an absorption). An absorption keeps what its change
    replaced (`was`), for finish to undo when the record it absorbs can no
    longer be held. A change that makes a session current is checked, under
    the thread store's lock (a seat's taken inside its own), against a
    human-opened record whose current session it is (_claimed): one the
    entry absorbs already passes; with `absorbs` (a session that may have
    made a record of its own first: a hand-off's job, a spawn's child), an
    absorbable one makes an advance an absorption of it; any other refuses
    the change. The entry as written, None when nothing was."""
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
        if not _claimed(thread_id, entry, view, fields, absorbs):
            return False
        _apply(entry, view, raw, fields, remove)
        return "live" if op == "return" else True

    return entry if _change(thread_id, mutate, lock_until, bump=True,
                            both=bool((fields or {}).get("current"))) else None


def _holder(session, thread_id):
    """The record other than `thread_id` that holds `session` as its current
    one: a seat (an open entry making it current included: `current` is the
    entry's change), else a human-opened record, live or set aside; None for
    none. Read under both stores' locks by every claim of a session."""
    for seat in sminos.seats():
        if seat["seat_id"] != thread_id and seat["current"] == session:
            return _of_seat(seat)
    live = _human_threads()
    return next((t for t in live + _aside_holding(session, live)
                 if t["thread"] != thread_id and t["current"] == session), None)


def _claimed(thread_id, entry, view, fields, absorbs):
    """Whether a change that makes a session current may: no other record
    holds it (_holder) but the one the entry absorbs; with `absorbs`, an
    absorbable human-opened one turns an advance into its absorption (entry
    changed in place). The caller holds both stores' locks: a seat's write
    takes the thread store's inside its own (_change's `both`), and a
    human-opened record's is the thread store's, which every seat's claim
    holds too."""
    session = str((fields or {}).get("current") or "")
    if not session or session == view["current"]:
        return True
    found = _holder(session, thread_id)
    if found is None or found["thread"] == entry.get("other"):
        return True
    if absorbs and found["opened"] == "human" and entry["op"] == "advance" and not entry.get("other") \
            and absorbable(found, session):
        entry["op"], entry["other"] = "absorb", found["thread"]
        return True
    return False


def _apply(entry, view, raw, fields, remove):
    """An entry's change made in `raw`, the entry written in it: `fields`
    merged, `remove` dropped, a `current` it sets added to `sessions`, last;
    an absorption's prior values kept in the entry (`was`, `unset`)."""
    if entry["op"] == "absorb":
        keys = [*(fields or {}), *remove, "sessions"]
        entry["was"] = {k: copy.deepcopy(raw[k]) for k in keys if k in raw}
        entry["unset"] = [k for k in keys if k not in raw]
    for k, v in (fields or {}).items():
        raw[k] = copy.deepcopy(v)
    for k in remove:
        raw.pop(k, None)
    current = str(raw.get("current") or "")
    if current and current not in view["sessions"]:
        # An advance or an absorption names its new session: `sessions` gains it, last.
        raw["sessions"] = view["sessions"] + [current]
    raw["pending"] = entry


def follow(thread_id, after, op, project, events, fields=None, remove=(), lock_until=None, **more):
    """An operation queued behind the open entry `after` (its id: the
    caller's own earlier operation, never another's), as that entry's
    `next`: finish begins it in the write that clears `after`, so a change
    that could not begin while `after` stays open (a refill's poll behind
    its launch's) is not lost. Under the record's finisher lock, so it is
    one at a time with finish, which reads `next` under it. True when it was
    queued; False when `after` is no longer the record's open entry (it was
    finished meanwhile: the caller begins its operation itself) or one is
    queued already."""
    if op not in OPS:
        raise ValueError("not a journaled operation: %r" % (op,))
    queued = {"op": op, "project": project.id, "events": [dict(e) for e in events],
              "fields": copy.deepcopy(fields or {}), "remove": list(remove),
              **{k: v for k, v in more.items() if v is not None}}

    def mutate(view, raw):
        entry = view.get("pending") or {}
        if entry.get("id") != after or entry.get("next"):
            return False
        raw["pending"]["next"] = queued
        return True

    with _finish_lock(thread_id, lock_until):
        return _change(thread_id, mutate, lock_until)


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


def finish(thread_id, appended=None, project=None, append=None, lock_until=None, before=None, settle=None):
    """Carries out the record's open entry from where it stands, and clears
    it (§6, steps 2 to 4): each event the log does not hold yet; then, in
    one write, the entry removed and an end's record set aside or deleted
    as its `last` says. True when the record has no open entry left.
    `appended`, a list, gains the events appended to the caller's project's
    log (`project`, else the first entry's). `project`: the caller's,
    when it is the entry's (a project need not be registered here to be
    resolved); else the entry's is looked up. `append`: the caller's
    sminos.lifecycle (a test may load its own copy of sminos, whose view
    cache an append must clear). `lock_until`: the hook's deadline for each
    lock (LockBusy past it, the entry left open). The alias a human-opened
    thread's owed `joined` or `renamed` carries is copied in the last
    write, since update() leaves a record with an open entry alone.

    One finisher of a record at a time (its finisher lock, held throughout:
    a finish and its undo are one at a time), and every step is the open
    entry's as read under that lock, so a finisher never acts for an entry
    another one cleared or undid meanwhile.

    An entry that carries a hand-off's reach (`carry`) appends nothing
    until that reach is durable: `before(project, entry)`, by default
    sminos.carry_hand_offs (the reach, the cursor, the override, each safe
    to repeat), answers whether it is; while it answers False the entry
    stays open.

    An end's settlement (`settle`, its session) comes after its events and
    before its last step: `settle(project, session, lock_until)`, by default
    sminos.settle_ended (what is owed to the session settled `recorded`,
    under its delivery lock), answers whether it is done; while it answers
    False the entry stays open, and the record is neither set aside nor
    deleted.

    An absorption first holds the record it absorbs, under that record's
    own lock (_hold): marked RESERVED by this entry while it is still
    absorbable; one with an open entry of its own is waited for; one that
    no longer is absorbable undoes a hand-off's advance, nothing appended
    (_undo: the two stay two threads), and leaves a refill's seat to go on
    without it. The absorbed record is deleted after the events, only while
    this entry's mark is on it. A record marked RESERVED is finished
    through the entry that holds it, or released when that entry is gone.
    An entry with an operation queued behind it (`next`: follow) begins
    that operation in the write that clears it, and it is finished in
    turn."""
    appended = [] if appended is None else appended
    if not (get(thread_id) or {}).get("pending"):
        return True
    with _finish_lock(thread_id, lock_until):
        return _finish(thread_id, appended, project, append or sminos.lifecycle, lock_until,
                       before or sminos.carry_hand_offs, settle or sminos.settle_ended)


def _finish(thread_id, appended, project, append, deadline, before, settle):
    home = project.id if project is not None else None
    while True:
        t = get(thread_id)
        entry = (t or {}).get("pending")
        if not entry:
            return True
        if entry.get("op") == RESERVED:
            holder = get(entry.get("by"))
            if ((holder or {}).get("pending") or {}).get("id") == entry["id"]:
                finish(holder["thread"], appended, project, append, deadline, before, settle)
            else:
                _change(thread_id, lambda view, raw: _release(view, raw, entry), deadline)
            return not (get(thread_id) or {}).get("pending")
        if project is None or project.id != entry.get("project"):
            project = sminos.known_project(str(entry.get("project") or ""))
        if project is None:
            return False
        home = home or project.id
        # The events `appended` returns are the caller's project's alone: a queued entry may owe another's (a
        # refill that moved its seat), which the caller would otherwise take for its own log's.
        sink = appended if project.id == home else []
        session, other = t["current"], entry.get("other") if entry.get("op") == "absorb" else None
        if other:
            held = _hold(thread_id, entry, session, deadline)
            if held == "busy":
                return False
            if held == "lost" and entry.get("carry"):
                return _undo(thread_id, entry, deadline)
        if entry.get("carry") and not before(project, entry):
            return False
        for event in entry.get("events") or []:
            if not _owe(project, entry, event, sink, append):
                return False
        if entry.get("settle") and not settle(project, entry["settle"], deadline):
            return False   # what is held for it is settled before the record is set aside or deleted (§6, 3)
        if other:
            _change(other, lambda view, raw: "delete" if (view.get("pending") or {}).get("id") == entry["id"]
                    else False, deadline)
        chained = []

        def clear(view, raw):
            if (view.get("pending") or {}).get("id") != entry["id"]:
                return False
            raw.pop("pending", None)
            if view["opened"] == "human":
                for e in entry.get("events") or []:
                    if e["kind"] in ("joined", "renamed") and e["session"] == view["current"] and e.get("alias"):
                        raw["alias"] = str(e["alias"])
            queued = (view.get("pending") or {}).get("next")
            if queued:
                nxt = _queued_entry(thread_id, queued)
                after = {**view, "current": str(raw.get("current") or ""), "pending": None}
                if not _claimed(thread_id, nxt, after, queued["fields"], queued.get("absorbs")):
                    return False   # its session is a record's that cannot be absorbed: the entry stays open
                _apply(nxt, after, raw, queued["fields"], queued["remove"])
                if view["opened"] == "spawned":
                    raw["gen"] = int(raw.get("gen") or 0) + 1   # a journaled transition begins: a lifecycle write
                chained.append(nxt)
                return True
            last = entry.get("last")
            if last == "purge":
                return "delete"
            if last == "aside" and view["opened"] == "human":
                return "aside"
            return True

        _change(thread_id, clear, deadline, both=True)
        if not chained:
            return not (get(thread_id) or {}).get("pending")


def _queued_entry(thread_id, queued):
    """The entry a queued operation (follow) begins as: its events stamped
    with the thread when they name none, under a new id."""
    owed = []
    for e in queued.get("events") or []:
        e = dict(e)
        if not stamped(e):
            e["thread"] = thread_id
        owed.append(e)
    rest = {k: v for k, v in queued.items() if k not in ("op", "project", "events", "fields", "remove", "absorbs")}
    return {"id": uuid.uuid4().hex, "op": queued["op"], "at": sminos.now(), "project": queued["project"],
            "events": owed, **rest}


def _release(view, raw, mark):
    if (view.get("pending") or {}).get("id") != mark["id"]:
        return False
    raw.pop("pending", None)
    return True


def _hold(thread_id, entry, session, deadline):
    """The absorption's hold on the record it absorbs (finish): "held" once
    the record carries this entry's mark (or is gone: deleted by an earlier
    attempt), "busy" while it has an open entry of its own, "lost" when it
    is no longer absorbable into `session`. Read and written under that
    record's lock, whichever store the absorbing thread is in."""
    got = []

    def hold(view, raw):
        mine = view.get("pending")
        if mine:
            got.append("held" if mine.get("id") == entry["id"] else "busy")
            return False
        if not absorbable(view, session):
            got.append("lost")
            return False
        raw["pending"] = {"id": entry["id"], "op": RESERVED, "by": thread_id, "at": sminos.now(),
                          "project": entry["project"], "events": []}
        got.append("held")
        return True

    _change(entry["other"], hold, deadline)
    return got[0] if got else "held"


def _undo(thread_id, entry, deadline):
    """A hand-off's absorption backed off before anything was carried or
    appended: the record's change undone (`was`, `unset`) and its entry
    cleared in one write."""
    def undo(view, raw):
        if (view.get("pending") or {}).get("id") != entry["id"]:
            return False
        for k, v in (entry.get("was") or {}).items():
            raw[k] = copy.deepcopy(v)
        for k in entry.get("unset") or ():
            raw.pop(k, None)
        raw.pop("pending", None)
        return True

    _change(thread_id, undo, deadline, bump=True)
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
