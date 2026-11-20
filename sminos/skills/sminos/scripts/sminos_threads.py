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

Which hosts a thread owns is devcloud's answer, never a copy kept here
(contract X9; M5): owned_by() is the one function that runs devcloud, and
owned_vms() asks it about a thread's sessions.
"""
import contextlib
import copy
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from typing import NamedTuple

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
# What a seat record gains; its `thread`, `current` and `alias` are its own. `waking` is T2's (its plan's §7).
SEAT_KEYS = ("opened", "sessions", "launch", "channels", "stopped", "swept", "ended", "released", "pending",
             "waking")
# A seat's marks that belong to the occupant they were written for: a seat that takes another session drops them.
# `waking` (T2) is one too: an earlier occupant back (A, B, A) never finds its old line or failures valid again.
OCCUPANT_MARKS = ("ended", "stopped", "swept", "waking")

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


@contextlib.contextmanager
def claims_held(deadline=None):
    """Both stores' locks, in their order: no record is made, claimed or
    changed for any session while they are held (_create_human, claim_seat,
    every _change). What a writer that must know a session is still no
    thread decides and appends under (sminos.retire_member's exempt retire);
    the log's locks are taken inside them, never the reverse."""
    with _seat_lock(deadline), _human_lock(deadline):
        yield


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
    `updated`. A `current` that moved without `sessions` (one that is not
    their last: a new occupant, or an earlier one back) is another
    occupant's: it is read as the last of `sessions`, and the end and stop
    marks the seat holds (`ended`, `stopped`, `swept`) were its
    predecessor's, not read as its own."""
    sessions = _stored_sessions(s)
    cur = str(s.get("current") or "")
    moved = _moved(s)
    if cur and sessions[-1:] != [cur]:
        sessions = [x for x in sessions if x != cur] + [cur]
    ended = s.get("ended") if isinstance(s.get("ended"), dict) and not moved else None
    if ended is None and s.get("status") == "retired":
        ended = {"at": str(s.get("updated") or ""), "reason": "retire", "by": "", "pid": None}
    launch = s.get("launch") if isinstance(s.get("launch"), dict) else {"cwd": str(s.get("cwd") or "")}
    rec = {"thread": s["seat_id"], "opened": "spawned", "sessions": sessions, "current": cur,
           "alias": str(s.get("alias") or ""), "launch": dict(launch),
           "channels": [c for c in s.get("channels") if isinstance(c, str)] if isinstance(s.get("channels"), list)
           else [], "created": str(s.get("created") or ""), "updated": str(s.get("updated") or "")}
    for k in ("stopped", "swept", "released", "pending"):
        if s.get(k) and not (moved and k in OCCUPANT_MARKS):
            rec[k] = copy.deepcopy(s[k])
    if isinstance(s.get("waking"), dict) and not moved:
        rec["waking"] = copy.deepcopy(s["waking"])   # its reader checks the session it names too (waking)
    if ended is not None:
        rec["ended"] = dict(ended)
    return rec


def _stored_sessions(s):
    return [x for x in s.get("sessions") if isinstance(x, str) and x] if isinstance(s.get("sessions"), list) else []


def _moved(s):
    """Whether an adopted seat's `current` moved without its `sessions` (an
    older copy's refill or `seat add`, the board pipeline): it is not their
    last."""
    cur = str(s.get("current") or "")
    return bool(cur) and "opened" in s and _stored_sessions(s)[-1:] != [cur]


def _is_thread(seat):
    """Whether a seat is a thread (§1): one with the thread keys, one with no
    session, or one whose session is lane A. A seat with no keys holding a
    lane B session (`seat add` made it for one; or one from before threads)
    is none, as a lane B session has no record (D1): no lookup of the
    store answers it (all_threads, get, thread_of). Nor, until its record
    reads, one with no keys whose session's record cannot be read: its lane
    is unknown, so it is neither adopted nor a stamp."""
    if "opened" in seat or not seat.get("current"):
        return True
    return not sminos.records_module().unreadable(seat["current"]) and _lane_a(seat["current"])


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
    and a former session that runs again is another thread. Only a thread
    whose current session it is (an open entry's included) stamps it: one
    that only had the session (it went on in another) names it for a lookup
    (thread_of), never for the session's own events now, which a journaled
    transition of that thread stamps itself."""
    t = thread_of(session, ended=False)
    return t["thread"] if t is not None and t["current"] == session else ""


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
            if _moved(raw):
                # A `current` another writer moved: the record the change is made on is the one every reader reads
                # (_of_seat), its occupant last and its predecessor's marks gone, so a mark written now is its own.
                cur = str(raw["current"])
                raw["sessions"] = [x for x in _stored_sessions(raw) if x != cur] + [cur]
                for k in OCCUPANT_MARKS:
                    raw.pop(k, None)
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


def holds(thread_id, pred, lock_until=None, missing=False):
    """pred(record), read under the record's own store lock (nothing
    written); `missing` for a record that is gone."""
    out = []

    def read(view, raw):
        out.append(bool(pred(view)))
        return False
    _change(thread_id, read, lock_until)
    return out[0] if out else missing


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


def launch_of(cwd, options=None, dropped=None):
    """A record's `launch`: the directory of the engine process that last
    started the thread's current session and, when they could be read, its
    options (launch_options) and the names of those dropped for their value
    (launch_dropped); `options` absent means unknown, never none, and a
    launch written before T2 has no `dropped`."""
    launch = {"cwd": str(cwd or ""), "at": sminos.now()}
    if options is not None:
        launch["options"] = list(options)
    if dropped is not None:
        launch["dropped"] = list(dropped)
    return launch


def note_launch(thread_id, cwd, options=None, dropped=None, lock_until=None):
    """The launch noted on its own (launch_of), a change that owes no event."""
    return update(thread_id, {"launch": launch_of(cwd, options, dropped)}, lock_until=lock_until)


def set_channels(thread_id, channels):
    """CH's writer of the declared channels."""
    return update(thread_id, {"channels": [str(c) for c in channels]})


# ------------------------------------------------------------ the wake's field (T2's plan, §7)


def waking(record, session=None):
    """The record's `waking` (T2's §7), only as written for the session that
    fills it now (and is `session`, when given): {} otherwise, so a field an
    older copy carried over to another occupant, or one left for a session
    the thread has since left, is never read."""
    w = (record or {}).get("waking")
    if not isinstance(w, dict) or not w.get("session") or w["session"] != (record or {}).get("current"):
        return {}
    if session is not None and w["session"] != session:
        return {}
    return copy.deepcopy(w)


def _waking_change(thread_id, session, change, lock_until=None):
    """change(field) on the `waking` written for `session`, made through
    update() only while the record's current session is `session` and the
    field is still what it was read as; the field removed when nothing but
    its session is left. change answers the new field, or None for no
    write. A write that lost the field to another writer reads it again;
    one refused for another reason (an open entry, another occupant) writes
    nothing."""
    for _ in range(3):
        rec = get(thread_id)
        if rec is None or rec["current"] != session or not session:
            return False
        before = rec.get("waking")
        new = change(waking(rec, session) or {"session": session})
        if new is None:
            return False
        new["session"] = session

        def same(r, before=before):
            return r["current"] == session and r.get("waking") == before
        if set(new) - {"session"}:
            done = update(thread_id, {"waking": new}, guard=same, lock_until=lock_until)
        else:
            done = update(thread_id, {}, remove=("waking",), guard=same, lock_until=lock_until)
        if done:
            return True
        now = get(thread_id)
        if now is None or now["current"] != session or now.get("pending") or now.get("waking") == before:
            return False
    return False


def wake_line(thread_id, session, line, lock_until=None):
    """`waking.line` set for the wake about to launch (§2, §7)."""
    def change(w):
        w["line"] = copy.deepcopy(line)
        return w
    return _waking_change(thread_id, session, change, lock_until)


def wake_failed(thread_id, session, line_id, lock_until=None):
    """A wake failed: `failed` counted, `at` now, and the line it wrote removed."""
    def change(w):
        w["failed"] = (w["failed"] if isinstance(w.get("failed"), int) and w["failed"] > 0 else 0) + 1
        w["at"] = sminos.now(ms=True)
        if (w.get("line") or {}).get("id") == line_id:
            w.pop("line")
        return w
    return _waking_change(thread_id, session, change, lock_until)


def wake_done(thread_id, session, saved=None, lock_until=None):
    """A wake made the session live: the failures forgotten, and `saved` set
    when given (the engine said the session keeps saved options, §3 row 12)."""
    def change(w):
        w.pop("failed", None)
        w.pop("at", None)
        if saved:
            w["saved"] = True
        return w
    return _waking_change(thread_id, session, change, lock_until)


def wake_line_sent(thread_id, session, line_id, lock_until=None):
    """The line pushed: removed, only while it is still the one of `line_id`."""
    def change(w):
        if (w.get("line") or {}).get("id") != line_id:
            return None
        w.pop("line")
        return w
    return _waking_change(thread_id, session, change, lock_until)


def wake_forget(thread_id, session, lock_until=None):
    """`saved` removed: sminos removed the session's row (§3), so the next wake is a first one."""
    def change(w):
        if "saved" not in w:
            return None
        w.pop("saved")
        return w
    return _waking_change(thread_id, session, change, lock_until)


def note_alias(session, alias, lock_until=None, project=None):
    """The alias a human-opened thread's latest `joined` or `renamed` carried,
    copied into its record for readers without the log (lifecycle). With
    `project`, the log it was appended to, copied only while the session is
    still a member there and it is still the latest its own events there
    carry, read under the record's lock: two copies made in the other order than their appends leave the
    later one."""
    t = thread_of(session, ended=False)
    if t is None or t["opened"] != "human" or t["current"] != session or t.get("alias") == alias:
        return False

    def latest(r):
        if r["current"] != session:
            return False
        if project is None:
            return True
        own = sminos._own_events(project, session)
        if sminos.latest_membership(own) != "joined":
            return False   # it has left that project (a move): what it publishes elsewhere is its name now
        named = [e for e in own if e["kind"] in ("joined", "renamed") and e.get("alias")]
        last = sminos.latest_across_writers(named) if named else None
        return last is None or str(last["alias"]) == alias
    return update(t["thread"], {"alias": alias}, guard=latest, lock_until=lock_until)


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
    when it moved without it: last, with the occupants the log shows it
    had meanwhile (an older copy's `seat add` writes their `joined` and no
    `history`), and without its predecessor's marks."""
    tid = seat["seat_id"]
    if "opened" in seat and not _moved(seat):
        return _of_seat(seat)
    project = project if project is not None else (sminos.seat_project(seat) if seat["current"] else None)
    rebuilt = _seat_sessions(seat, project if not sminos.guessed(project) else None, events)
    moved = _moved(seat)

    def mutate(view, raw):
        if "opened" not in raw:
            raw["opened"] = "spawned"
            raw["sessions"] = rebuilt
            raw.setdefault("launch", {"cwd": str(raw.get("cwd") or "")})
            raw.setdefault("channels", [])
        elif moved and view["current"] == seat["current"]:   # its tail and marks set by _change already
            cur = view["current"]
            had = [x for x in view["sessions"] if x != cur]
            raw["sessions"] = had + [x for x in rebuilt if x not in had and x != cur] + [cur]
            for k in OCCUPANT_MARKS:   # its predecessor's (_of_seat)
                raw.pop(k, None)
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


def repoint_seat(seat_id, fields, deadline=None, expect=None):
    """An existing seat given `fields["current"]` by a plain write (no event
    owed: `seat add --session` where no journal applies; a first spawn's
    seat naming its child), under both stores' locks only while no other
    record holds that session (_holder), as every claim, and while the seat
    has no open entry (§6, 6: nothing writes through one); its lifecycle
    generation moved. A seat that takes another session drops what was its
    predecessor's: its end, stop and wake marks (OCCUPANT_MARKS) and, for a lane
    B session, the thread keys, since a lane B session's seat is no thread
    (D1; _is_thread). False, nothing written, when another record holds the
    session, an entry is open, the seat is gone, or (`expect`) it no longer
    holds the occupant the caller displaces."""
    session = fields["current"]
    with _seat_lock(deadline), _human_lock(deadline):
        path = sminos.meta_path(seat_id)
        try:
            with open(path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return False
        if not isinstance(raw, dict) or raw.get("pending") or _holder(session, seat_id) is not None:
            return False
        if expect is not None and str(raw.get("current", seat_id) or "") != expect:
            return False
        if str(raw.get("current") or "") != session:
            for k in OCCUPANT_MARKS if _lane_a(session) else SEAT_KEYS:
                raw.pop(k, None)
            if "opened" in raw:
                raw["sessions"] = [x for x in _stored_sessions(raw) if x != session] + [session]
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
    if not _lane_a(session) or sminos.records_module().unreadable(session):
        # A lane B session is never made a thread, nor returned: only a live record it has is its own. Nor one
        # whose record cannot be read, whose lane is unknown until it can be.
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
    joined: an ended record the process does not return, which for a seat
    a fill may still return).

    A session whose record cannot be read is held: its lane is unknown, and
    an adoption is not undone. A lane B session revives no thread: it keeps a live record whose
    current session it is (its end stamped, row 13), never one set aside
    nor one that only had it, and makes none. A lane A
    session's thread is §1's: a human-opened record whose current session
    it is, set aside or not, before a seat (an older copy can have seated
    such a session; the seat is then left as it is); else ensure()'s, which
    makes the record when there is none. An ended thread, of either kind,
    returns by a process its end did not see (returns). LockBusy past
    `lock_until`."""
    if sminos.records_module().unreadable(session):
        return None, "hold"   # its lane unknown until its record reads: nothing joined, no record made
    if not _lane_a(session):
        t = thread_of(session, ended=False)
        if t is not None and t["current"] != session:
            t = None   # a thread that only had the session (it went on in another): not this session's to stamp
        return (t, "hold") if t is not None and record_ended(t) else (t, "join")
    t = thread_of(session)
    if t is None or t["opened"] != "human" or t["current"] != session:
        t = ensure(session, seat, project, events, lock_until)
    if t is None or not record_ended(t):
        return t, "join"
    if t["current"] == session and returns(t, peer):
        return t, "return"
    return t, "hold"


def seat_ended(record):
    """Whether a spawned thread's end is held in its seat record (`ended`,
    this code's), rather than read from its `status` alone (a seat an older
    copy retired, §1): what that copy's retire saw of a process, nothing on
    the record says (returns)."""
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


def returns(record, peer, known=None):
    """Whether the process of `peer` (an engine record), holding an ended
    thread's session, returns it (§6, row 12): one the end did not see. An
    end that recorded no process (the rule, a retire of a stopped thread)
    saw none, so any process returns it: one that started a moment before
    the end, unseen by its check, must not stay ended while it runs. An end
    that recorded one (a retire of a running session, a self-retire) is
    returned by another pid, or by one started after the end: the process
    the retire saw runs on in its human's terminal and does not. A seat an
    older copy retired (its `status` alone, read as ended at its `updated`:
    seat_ended false) says nothing of what that retire saw, so only a
    process started after it returns it. "After" is at the end's own
    precision, whole seconds (sminos.now): a process started within the
    second of its end is not after it. `known`: whether the end's own
    process is recorded (this code's end, not an older copy's), as a caller
    read it while the record still stood (a purge deletes the seat file
    seat_ended reads); read here otherwise."""
    ended = (record or {}).get("ended") or {}
    peer = peer or {}
    if not ended or not peer.get("pid"):
        return False
    if known is None:
        known = record["opened"] == "human" or seat_ended(record)
    if known and ended.get("pid") in (None, ""):
        return True
    if known and str(ended["pid"]) != str(peer.get("pid")):
        return True
    started, at = sminos.process_started(peer), sminos._ts_epoch(ended.get("at"))
    return started is not None and at is not None and int(started) > at


def stop_seen(session, lock_until=None):
    """A process holds the session again (§6, row 8), as its hook or a
    launch sees it before the sweep can: the stop mark of the thread whose
    current session it is, `stopped` and `swept`, removed, so the clock of
    the rule starts again at its next stop and never runs on a mark from
    before. Nothing for a record with no mark, an ended one (its return
    lifts the mark) or one with an open entry."""
    t = thread_of(session, ended=False)
    if t is None or t["current"] != session or not (t.get("stopped") or t.get("swept")) or record_ended(t):
        return False
    return update(t["thread"], {}, remove=("stopped", "swept"),
                  guard=lambda r: r["current"] == session and not record_ended(r), lock_until=lock_until)


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
        if op == "return" and entry.get("settle"):
            # Under the record's lock, the positions the events addressed to the session have reached in the
            # local log, each writer's seq: what the return settles, and nothing a clock decides. A settlement
            # that read the log before this write sees the record ended when it asks under the same lock
            # (sminos_outcomes.end_stands), so it read nothing past them.
            entry["until"] = sminos.positions_to(project, entry["settle"])
        _apply(entry, view, raw, fields, remove)
        return "live" if op == "return" or more.get("last") == "purge" else True   # an open purge is read live

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
    an absorption's prior values kept in the entry (`was`, `unset`). A
    change of occupant drops `waking`: it was written for the session the
    change replaces."""
    if "current" in (fields or {}) and str(fields["current"] or "") != str(raw.get("current") or ""):
        remove = tuple(remove) + ("waking",)
    if entry["op"] == "absorb":
        keys = [*(fields or {}), *remove, "sessions"]
        entry["was"] = {k: copy.deepcopy(raw[k]) for k in keys if k in raw}
        entry["unset"] = [k for k in keys if k not in raw]
    for k, v in (fields or {}).items():
        raw[k] = copy.deepcopy(v)
    for k in remove:
        raw.pop(k, None)
    current = str(raw.get("current") or "")
    if current and view["sessions"][-1:] != [current]:
        # An advance or an absorption names its new session: it is the last of `sessions` (an earlier one back too).
        raw["sessions"] = [x for x in view["sessions"] if x != current] + [current]
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


def finish(thread_id, appended=None, project=None, append=None, lock_until=None, before=None, settle=None,
           stop=None):
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
    before its last step: `settle(project, session, lock_until, until)`, by
    default sminos.settle_ended (what is owed to the session settled
    `recorded`, under its delivery lock), answers whether it is done; while
    it answers False the entry stays open, and the record is neither set
    aside nor deleted. A return's (`settle` with `until`, each writer's
    seq the events addressed to the session had reached in the local log as
    it began) comes before its events: what reached the log for the session
    while its end stood, up to those positions, is settled before its
    `joined` makes it a member again, and nothing after them is.

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
    turn.

    A purge's stop is its entry's too (`stop(record, entry)`, by default
    sminos.purge_stop): after its events and its settlement, before the
    record goes, the process its end recorded is stopped while that same
    process still holds the session, whoever finishes the entry (a verb
    cut before its own stop, a reading verb, a tick), since the record that
    names the process is gone after it. No store lock is held through it:
    only the record's finisher lock."""
    appended = [] if appended is None else appended
    if not (get(thread_id) or {}).get("pending"):
        return True
    with _finish_lock(thread_id, lock_until):
        return _finish(thread_id, appended, project, append or sminos.lifecycle, lock_until,
                       before or sminos.carry_hand_offs, settle or sminos.settle_ended, stop or sminos.purge_stop)


def _finish(thread_id, appended, project, append, deadline, before, settle, stop):
    home = project.id if project is not None else None
    while True:
        t = get(thread_id)
        entry = (t or {}).get("pending")
        if not entry:
            return True
        if entry.get("op") == RESERVED:
            holder = get(entry.get("by"))
            if ((holder or {}).get("pending") or {}).get("id") == entry["id"]:
                finish(holder["thread"], appended, project, append, deadline, before, settle, stop)
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
        if entry.get("carry") and not entry.get("carried"):
            if not before(project, entry):
                return False
            # Carried once: a replay does not carry again what a later deliberate change undid (a `join --cwd`
            # that removed the job's override after the copy, while an event was still owed).
            _change(thread_id, lambda view, raw: _mark_carried(view, raw, entry), deadline)
        returning = entry.get("op") == "return"
        if returning and entry.get("settle") and not settle(project, entry["settle"], deadline, entry.get("until")):
            return False   # what reached it while it was ended is settled before it is a member again
        for event in entry.get("events") or []:
            if not _owe(project, entry, event, sink, append):
                return False
        if not returning and entry.get("settle") and not settle(project, entry["settle"], deadline, None):
            return False   # what is held for it is settled before the record is set aside or deleted (§6, 3)
        if entry.get("last") == "purge" and entry.get("settle"):
            stop(t, entry)   # tried once a finish: a stop that fails does not keep the purge open
        if entry.get("seat") and not _project_seat(entry["seat"], deadline):
            return False   # the seat could not be read or written: the entry stays open for the replay
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
            if last == "purge" and entry.get("settle") and view["current"] != entry["settle"]:
                # Another occupant since (an older copy's refill merged its `current` past the entry): the purge
                # was of the session it settled, and deletes no record that now holds another.
                return True
            if last == "purge":
                return "delete"
            if last == "aside" and view["opened"] == "human":
                return "aside"
            return True

        _change(thread_id, clear, deadline, both=True)
        if not chained:
            return not (get(thread_id) or {}).get("pending")


def _project_seat(seat, deadline, holds=None):
    """The seat an older copy gave a thread its human opened, brought in
    line with that record by the record's own entry (`seat`: its id, the
    session, and `to`, "retired", "idle" or "purge"), before the entry is
    cleared: so a cut leaves it to the replay, and the seat never holds a
    state of its own for that thread. Only while the seat still holds that
    session; safe to repeat. Whether it is done: True for a seat brought
    in line, one that is gone, or one that holds another session now; False
    (the entry stays open) for one that could not be read or written."""
    seen = []

    def mutate(view, raw):
        seen.append(view["current"] == seat["session"])
        if not seen[-1] or (holds is not None and not holds()):
            return False
        if seat["to"] == "purge":
            return "delete"
        raw["status"] = seat["to"]
        raw["updated"] = sminos.now()
        return True
    try:
        _change(seat["id"], mutate, deadline, bump=True, both=holds is not None)
    except OSError:
        return False
    if seen:
        return True
    return not os.path.exists(sminos.meta_path(seat["id"]))   # gone is done; unreadable is not


def project_seat(seat, thread_id, deadline=None):
    """_project_seat outside an entry: for an end found in place already
    (a verb that met it), the older copy's seat brought in line once more,
    only while that end of the record `thread_id` still stands, read under
    both stores' locks (a return finished since brought the seat back to
    idle, and nothing journals a write over it)."""
    return _project_seat(seat, deadline, holds=lambda: record_ended(get(thread_id)))


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


def _mark_carried(view, raw, entry):
    if (view.get("pending") or {}).get("id") != entry["id"]:
        return False
    raw["pending"]["carried"] = True
    return True


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
    return _launch_tokens(argv)[0]


def launch_dropped(argv):
    """The names of the options of LAUNCH_OPTIONS that launch_options drops
    for their value (inline JSON, or a session named), in order, each once:
    `launch.dropped`, which a first wake reports as not carried (T2)."""
    out = []
    for name in _launch_tokens(argv)[1]:
        if name not in out:
            out.append(name)
    return out


def _launch_tokens(argv):
    """(the tokens kept, the names of the options dropped for their value)."""
    out, dropped, i, args = [], [], 1, list(argv or [])
    while i < len(args):
        tok = args[i]
        i += 1
        if tok == "--":
            break   # the end of the options: what follows is positional, whatever it is spelled like
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
        if not values:
            continue
        if any(_secretive(v) for v in values):
            dropped.append(name)
            continue
        out += [name] + values
    return out, dropped


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


# ------------------------------------------------------------ which hosts a thread owns (X9; M5)

ANSWERS = ("owned", "none", "unknown")
DEVCLOUD_MIN = (0, 17, 2)       # from this version on, exit 6 is devcloud's word that its driver does not run here
DEVCLOUD_TIMEOUT = 60           # seconds one question may take; SMINOS_DEVCLOUD_TIMEOUT
DEVCLOUD_GRACE = 5              # seconds between the driver's SIGTERM and the kill of it and its descendants
_MANIFEST = os.path.join(".claude-plugin", "plugin.json")


class Exempt(NamedTuple):
    """No question was asked because none was needed, and why (`why`):
    "ended", a retire of a record that had ended already, which ends
    nothing; "no-thread", a session no record tracks (lane B). An end
    proves the exemption again where it writes (asked_all), and a record
    that no longer fits it is refused."""
    why: str


class Owned(NamedTuple):
    """devcloud's answer about some short ids (Interfaces §7): `answer`
    "owned", "none" or "unknown"; `vms` devcloud's matching hosts; `unknown`
    devcloud's entries for what it could not ask, or the one entry sminos
    makes for no answer; `asked` the short ids asked about."""
    answer: str
    vms: list
    unknown: list
    asked: list


def devcloud_timeout():
    """The bound on one question: SMINOS_DEVCLOUD_TIMEOUT seconds, else a minute."""
    try:
        v = float(os.environ.get("SMINOS_DEVCLOUD_TIMEOUT") or DEVCLOUD_TIMEOUT)
    except ValueError:
        return float(DEVCLOUD_TIMEOUT)
    return v if v > 0 else float(DEVCLOUD_TIMEOUT)


def plugin_root():
    """The running sminos plugin's root (this file is its
    skills/sminos/scripts/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))


def devcloud_places():
    """Where the devcloud CLI is looked for, in order (M5), each (what the
    place is, the path there or "" for none): the path in SMINOS_DEVCLOUD;
    devcloud/bin/devcloud beside this sminos plugin's root (the same clone
    or checkout, never older than it); the same file in the doperpowers
    marketplace clone, found as the daemon's installed_cli finds it (a CLI
    run from the plugin cache, which holds sminos alone); `devcloud` on
    PATH, last, since a long-lived PATH can name the cache of a devcloud
    from before 0.17.2."""
    beside = os.path.join(os.path.dirname(plugin_root()), "devcloud", "bin", "devcloud")
    clone = sminos.daemon_module().marketplace_clone()
    return [("$SMINOS_DEVCLOUD", os.environ.get("SMINOS_DEVCLOUD") or ""),
            ("beside sminos", beside),
            ("the marketplace clone", os.path.join(clone, "devcloud", "bin", "devcloud") if clone else ""),
            ("PATH", shutil.which("devcloud") or "")]


def find_devcloud():
    """(the place, its path) of the first copy that exists; (None, every
    place looked at, said) when none does."""
    places = devcloud_places()
    for where, path in places:
        if path and os.path.isfile(path):
            return where, path
    return None, "; ".join("%s (%s)" % (where, path or "none") for where, path in places)


def devcloud_version(path):
    """The version of the devcloud plugin a copy of its CLI belongs to,
    read from the manifest beside it (its bin/'s parent, as the launcher
    finds its own directory), as a tuple of three ints; None when it cannot
    be read."""
    manifest = os.path.join(os.path.dirname(os.path.realpath(os.path.dirname(path))), _MANIFEST)
    try:
        with open(manifest) as f:
            version = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", version) if isinstance(version, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def no_answer(shorts, reason):
    """An unknown sminos makes where devcloud gave no answer it stands
    behind: one entry with devcloud's keys, `failed` "query"."""
    return Owned("unknown", [], [{"account": None, "provider": None, "failed": "query", "reason": reason}],
                 list(shorts))


def shorts_of(sessions):
    """The short ids of session ids, bare, each once, in order."""
    out = []
    for x in sessions:
        if isinstance(x, str) and x and x[:8] not in out:
            out.append(x[:8])
    return out


def owned_by(shorts):
    """Which hosts name these short ids, by devcloud's own word (X9): the
    one function that runs devcloud. `devcloud vm owned-by <short>...`, the
    CLI found by find_devcloud, bounded by devcloud_timeout() (then
    stop_tree), with the directory of sminos's own interpreter first on its
    PATH (the driver needs a Python 3.11, and finds a provider's tool on
    the PATH it is given) and nothing else of the environment changed. Only
    devcloud's own word reads as none: exit 0 with `answer` none, or exit 6
    (the driver does not run here) from a devcloud of 0.17.2 or later, or
    from the copy SMINOS_DEVCLOUD names, which has no manifest and is taken
    at its word. Every other way of getting no answer is unknown, with the
    reason: no copy found, a copy older than 0.17.2 or of no readable
    version (not asked), any other exit, a timeout, output that is not the
    answer, a launcher that cannot be run. No short ids: none, unasked."""
    shorts = shorts_of(shorts)
    if not shorts:
        return Owned("none", [], [], [])
    where, path = find_devcloud()
    if where is None:
        return no_answer(shorts, "no devcloud CLI was found here, so nothing said its driver does not run (looked "
                                 "at: %s)" % path)
    if where != "$SMINOS_DEVCLOUD":
        version = devcloud_version(path)
        if version is None or version < DEVCLOUD_MIN:
            return no_answer(shorts, "the devcloud at %s is %s, older than %s, whose answer sminos does not read" % (
                path, ".".join(map(str, version)) if version else "of no readable version",
                ".".join(map(str, DEVCLOUD_MIN))))
    timeout = devcloud_timeout()
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen([path, "vm", "owned-by"] + shorts, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=err, env=env)
        except OSError as e:
            return no_answer(shorts, "the devcloud at %s could not be run: %s" % (path, e.strerror or e))
        try:
            code = proc.wait(timeout)
        except BaseException as e:   # past the bound, or this process stopped (a census's SIGTERM, a Ctrl-C)
            stop_tree(proc.pid, proc.wait)
            if not isinstance(e, subprocess.TimeoutExpired):
                raise
            return no_answer(shorts, "devcloud vm owned-by gave no answer within %gs, and was stopped" % timeout)
        printed = [_text(f) for f in (out, err)]
    if code == 6:
        return Owned("none", [], [], shorts)
    first = next((line.strip() for text in (printed[1], printed[0]) for line in text.splitlines() if line.strip()),
                 "it printed nothing")
    if code != 0:
        return no_answer(shorts, "devcloud vm owned-by exited %d: %s" % (code, first[:300]))
    reply = _reply(printed[0], shorts)
    if reply is None:
        return no_answer(shorts, "devcloud vm owned-by exited 0 without a well-formed answer (a malformed answer): %s"
                         % first[:300])
    return Owned(reply["answer"], reply["vms"], reply["unknown"], shorts)


def _text(f, limit=1 << 20):
    f.seek(0)
    return f.read(limit).decode("utf-8", "replace")


def _reply(stdout, shorts):
    """devcloud's answer object (X9) about `shorts` from what it printed,
    or None when it is not one (x9_reply)."""
    try:
        d = json.loads(stdout)
    except ValueError:
        return None
    return x9_reply(d, shorts)


def x9_reply(d, shorts, ours=False):
    """`d` when it is an answer of X9's form to a question about `shorts`
    (short ids), else None; never an exception. `answer` one of the three;
    each of `vms` a host with its `name`, `account`, `provider` (null
    exactly for an adopted machine, whose `adopted` is true, and no other
    host's is) and a `creator` that is `@` and one of the short ids asked
    (devcloud matches nothing else, and a host
    naming another would drop out of the match and leave a none); each of
    `unknown` an `account`, a `provider`, `failed` ("account" or "listing";
    with `ours`, the census's own file, also sminos's "query", the one with
    no account) and a `reason`; `listed`, the accounts listed in full, on
    devcloud's own reply; and the answer consistent with them: owned with a
    host, none with neither hosts nor anything unknown, unknown with no host
    and something unknown."""
    try:
        return d if _x9_whole(d, {"@" + x for x in shorts}, ours) else None
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _x9_whole(d, tags, ours):
    if not (isinstance(d, dict) and d.get("answer") in ANSWERS and isinstance(d.get("vms"), list)
            and isinstance(d.get("unknown"), list)):
        return False
    if not ours and not (isinstance(d.get("listed"), list) and all(isinstance(a, str) for a in d["listed"])):
        return False
    for v in d["vms"]:
        if not (isinstance(v, dict) and isinstance(v.get("name"), str) and v["name"]
                and isinstance(v.get("account"), str) and v["account"] and v.get("creator") in tags
                and (isinstance(v.get("provider"), str) and v["provider"] and v.get("adopted") is not True
                     or v.get("provider") is None and v.get("adopted") is True)):
            return False
    failed = ("account", "listing", "query") if ours else ("account", "listing")
    for u in d["unknown"]:
        if not (isinstance(u, dict) and _text_or_none(u.get("account")) and _text_or_none(u.get("provider"))
                and u.get("failed") in failed and isinstance(u.get("reason"), str)
                and (isinstance(u.get("account"), str) or u.get("failed") == "query")):
            return False
    return {"owned": bool(d["vms"]), "none": not d["vms"] and not d["unknown"],
            "unknown": not d["vms"] and bool(d["unknown"])}[d["answer"]]


def _text_or_none(v):
    return v is None or isinstance(v, str)


def owned_among(reply, shorts):
    """One thread's answer, read from a reply about many (Interfaces §7):
    owned when a host's `creator` is `@` and one of its short ids, whatever
    else is unknown (named too); else unknown when the reply could not ask
    something; else none."""
    shorts = shorts_of(shorts)
    tags = {"@" + s for s in shorts}
    mine = [v for v in reply.vms if v.get("creator") in tags]
    if mine:
        return Owned("owned", mine, list(reply.unknown), shorts)
    if reply.unknown or reply.answer == "unknown":
        return Owned("unknown", [], list(reply.unknown), shorts) if reply.unknown else \
            no_answer(shorts, "devcloud answered unknown and named nothing it could not ask")
    return Owned("none", [], [], shorts)


def owner_sessions(thread):
    """Every session a thread has had, for the question: its `sessions`;
    for a seat, also the occupants its `history` names, and, for a seat from
    before threads not yet adopted, what adoption will rebuild its
    `sessions` from (_seat_sessions: the log's `joined`s naming the seat,
    and their hand-offs). A host names only the session that made it."""
    sessions = list(thread["sessions"]) + ([thread["current"]] if thread["current"] else [])
    seat = sminos.reload_seat(thread["thread"]) if thread["opened"] == "spawned" else None
    if seat is not None:
        sessions += [str(h.get("current") or "") for h in seat.get("history") or [] if isinstance(h, dict)]
        project = sminos.seat_project(seat)
        project = project if project is not None and not sminos.guessed(project) else None
        if "opened" not in seat or _moved(seat):   # what adoption, or the repair of a moved `current`, rebuilds
            sessions += _seat_sessions(seat, project if seat["current"] else None, None)
        elif project is not None:
            # An occupant an older copy's `seat add` put there and displaced between two reads of this code (A, B,
            # A leaves `sessions` as it was): its `joined` naming the seat is the evidence, one read of the joins.
            sessions += [str(e.get("session") or "") for e in sminos.log_read(project, kinds=("joined",))
                         if e.get("seat") == seat["seat_id"]]
    return sessions


def owned_vms(thread):
    """owned_by for the short ids of every session the thread has had
    (owner_sessions); a thread with none (a vacant seat never filled) is
    not asked about: none."""
    shorts = shorts_of(owner_sessions(thread))
    return owned_among(owned_by(shorts), shorts) if shorts else Owned("none", [], [], [])


def asked_all(record, asked):
    """Whether what an end was cleared by still holds for the record as it
    is now, read where the end writes (its guard, under the record's lock),
    since the answer was read before: for short ids asked about, every
    session the record has had among them, by the same reading the
    question was asked from (owner_sessions); for an Exempt, the reason no
    question was needed (a record that had ended has ended still; a session
    no record tracked has none, so any record refuses it). Nothing (None)
    clears nothing."""
    if isinstance(asked, Exempt):
        return asked.why == "ended" and record_ended(record)
    if asked is None:
        return False
    return set(shorts_of(owner_sessions(record))) <= set(asked)


def is_adopted(vm):
    """Whether a census host is an adopted machine, which `devcloud vm down`
    releases and leaves running, where it deletes a host devcloud made. X9's
    own marker decides, never the account's name (a provider's account may
    be named `adopted`): x9_reply passes `adopted` true only with a null
    provider, and a null provider only with `adopted` true."""
    return vm.get("adopted") is True


def host_words(vm):
    """One host as a person is told it: its name, with its provider and
    account, or as an adopted machine."""
    if is_adopted(vm):
        return "%s (an adopted machine)" % vm.get("name")
    return "%s (%s, account %s)" % (vm.get("name"), vm.get("provider"), vm.get("account"))


def unknown_words(entry):
    """One thing devcloud could not ask, or sminos's reason for no answer."""
    if entry.get("failed") == "query":
        return str(entry.get("reason") or "no answer")
    if entry.get("account") == "adopted" and entry.get("provider") is None:   # a provider's account may be named so
        return "the adopted machines' records: %s" % entry.get("reason")
    return "account %s (%s): %s" % (entry.get("account"), entry.get("provider"), entry.get("reason"))


def owned_words(owned):
    """What an answer that holds a thread says (owned or unknown): the hosts
    and the way on, and what could not be asked."""
    parts = []
    if owned.vms:
        # Whose call taking a host down is, said where it is read (T1's M6, evaluated): "take each down first"
        # had sessions asked only to retire delete the host themselves.
        kinds = {is_adopted(v) for v in owned.vms}
        made, act = (("made or adopted", "deleting or releasing") if len(kinds) == 2 else
                     ("adopted", "releasing") if True in kinds else ("made", "deleting"))
        parts.append("it %s hosts that still exist: %s; %s a host is its owner's call: once nothing on it is "
                     "needed, %s, and then it can be retired" % (
                         made, ", ".join(host_words(v) for v in owned.vms), act,
                         "; ".join("`devcloud vm down %s` %s" % (
                             shlex.quote(str(v.get("name"))),
                             "releases it and leaves it running" if is_adopted(v) else "deletes it")
                             for v in owned.vms)))
    if owned.unknown:
        parts.append("%sdevcloud could not tell whether it made a host that still exists: %s" % (
            "and " if parts else "", "; ".join(unknown_words(u) for u in owned.unknown)))
    return "; ".join(parts)


def descendants(pid):
    """The pids descended from `pid` in the process table as read now
    (`ps`), children first; [] when it cannot be read."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "ppid="], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [int(pid)]
    while todo:
        for child in children.get(todo.pop(0), []):
            if child not in found:
                found.append(child)
                todo.append(child)
    return found


def stop_tree(pid, wait, grace=None):
    """A question past its bound stopped (M5): SIGTERM to the process, which
    devcloud's driver handles by taking its provider's process group down
    with it; after the grace (DEVCLOUD_GRACE), if it still runs, a kill of
    it and of every process then descended from it, read from the process
    table before the kill: the driver starts a provider in a process session
    of its own, which a kill of the caller's group does not reach. `wait`,
    the process's wait(timeout) (Popen.wait), raises TimeoutExpired while
    it runs. A SIGTERM or SIGINT to this process waits until it is done, so
    that stopping the caller never leaves the driver behind."""
    before = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            wait(DEVCLOUD_GRACE if grace is None else grace)
            return
        except subprocess.TimeoutExpired:
            pass
        kill_tree(pid)
        try:
            wait(DEVCLOUD_GRACE)
        except subprocess.TimeoutExpired:
            pass
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, before)


def kill_tree(pid, still=None):
    """SIGKILL to a process and every process descended from it, the
    descendants read before the kill; with `still`, only while still()
    says the process is the one meant (read after the table)."""
    below = descendants(pid)
    if still is not None and not still():
        return
    for p in [pid] + below:
        try:
            os.kill(p, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
