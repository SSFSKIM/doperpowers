"""The Task Board: the store of what sessions asked the human to do, its commands, the door, the start line
(child B1 of docs/doperpowers/specs/2026-11-27-task-board-design.md; execution document
docs/doperpowers/plans/2026-11-27-task-board-b1.md, §1 to §3 and §5, its M1).

One store a machine, $SMINOS_HOME/tasks/state.json (X1), written only by the commands here, each change one step:
take tasks/.lock (an exclusive flock, 10 s, the file never unlinked), read the store, refuse a newer `version`,
change the parsed object in place, replace it whole (a synced temporary file in tasks/ and os.replace), let go;
`seq` + 1 when anything changed. The lock is a leaf: whoever holds it takes no other lock of sminos's, reads thread
records only through reads that write nothing (member_row and the threads' module's getters), and appends to no
log. A reader takes no lock and writes nothing. What another repository reads is the published set,
sminos/types/tasks/, written by sminos/tests/tasks-contract.gen.py and never by this module.

    asker_of(session, agent=None) -> {thread, session, alias, agent}
    target_of(store, task, memo=None) -> {session, thread, project, state, runner, wake, why, via}
    is_asker(store, task, session, memo=None) -> bool
    keeps(thread, period, now=None) -> str | None     # why the three-day rule leaves a thread (D7; child B1a)
    cleared(left, begun, wait=LOCK_WAIT) -> None      # a witnessed /clear's pair, before the alias is released
    bind(store, session) -> bool                      # in place: binds the pairs naming this session to its thread
    bind_step(session, wait=LOCK_WAIT) -> None        # the same as a step of its own, when one waits
    apply_line(line, memo=None) -> verdict            # one of the door's lines, checked, in a step of its own
    notice_text, ended_line, start_line               # §5's texts, word for word (X6)

Nothing is sent from here until M2: every outcome is written with `send: null`, and the door's `told` is
`next-start` wherever M2's will be `now` or `wake`.
"""

import argparse
import calendar
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid

import sminos

V = 1
VERSION = 1                 # the store's contract version this module writes (X1)
LOCK_WAIT = 10.0            # the store's lock, as the sheet's door waits for its own
HOOK_LOCK_WAIT = 3.0        # remind's bind is skipped past this; only a /clear's pair waits the full LOCK_WAIT
OPEN_MAX = 500
KEPT = 30 * 86400           # a closed task is listed as closed for 30 days (D3)
START_NAMED = 20            # the outcomes a start line names; the rest are counted
LINES_MAX = 50
TEXT_MAX, TITLE_MAX, BODY_MAX, TAGS_MAX = 10000, 200, 20000, 8
EXIT_FAIL, EXIT_USAGE, EXIT_REFUSED, EXIT_BUSY = 1, 2, 3, 75

TASK_ID = re.compile(r"t[1-9][0-9]*")              # D2's, uncapped, wherever an id is read
OUTCOME_KEY = re.compile(r"(t[1-9][0-9]*)\.[1-9][0-9]*")
HANDLE = re.compile(r"(t[1-9][0-9]*)(?:@([1-9][0-9]*))?")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TAG = re.compile(r"[a-z0-9-]{1,32}")
AGENT_ID = re.compile(r"[A-Za-z0-9_.@-]{1,128}")
NAME_OUT = re.compile(r"[^A-Za-z0-9_.-]+")
CLASSES = ("blocking", "needed", "optional")
SPACED = re.compile("\r\n|[\t\n\x0b\x0c\r\x85  ]")
CONTROLS = re.compile("[\x00-\x1f\x7f-\x9f]")
LINE_FIELDS = {
    "done": ("v", "key", "act", "task", "revision", "text", "wake"),
    "decline": ("v", "key", "act", "task", "revision", "text", "wake"),
    "comment": ("v", "key", "act", "task", "text", "wake"),
    "seen": ("v", "key", "act", "task", "seq"),
    "shown": ("v", "key", "act", "task", "session", "keys"),
}
KIND = {"done": "done", "decline": "declined", "comment": "comment"}

NOTICE = {
    "asker": "[tasks v1] The human %s, a task you assigned. Read it: sminos task show %s",
    "successor": "[tasks v1] The human %s, a task assigned by the conversation this one replaced at a /clear. "
                 "Read it: sminos task show %s",
    "subagent": "[tasks v1] The human %s, a task your subagent %s assigned. Read it: sminos task show %s",
}
ENDED = "tasks: %s was %s; the conversation that assigned it has ended. It is on the board: sminos task show %s"
FORK = ("This conversation is a fork: the tasks the conversation it was forked from assigned to the human stay "
        "with that conversation, and what the human does on them is told there, not here.")
IN_SESSION = ("an agent's session does not complete the human's task: the human acts from a terminal that is no "
              "session, or from a surface (CLAUDE_CODE_SESSION_ID is set here)")
NEEDS_SESSION = "only a session assigns and changes a task for the human (CLAUDE_CODE_SESSION_ID is not set)"


class Refused(Exception):
    """A command's refusal: its exit code and what it says."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def clock():
    """Now, in epoch seconds: every step's one reading (a fixture's replay sets it)."""
    return time.time()


def stamp(t):
    """ISO-8601 in UTC with milliseconds (§1), truncated as sminos.now(ms=True) is: one millisecond count gives
    both the seconds and their fraction."""
    ms = int(t * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms // 1000)) + ".%03dZ" % (ms % 1000)


def epoch(ts):
    """A stored time in epoch seconds; None for one that does not read."""
    m = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,6}))?Z", str(ts or ""))
    if not m:
        return None
    whole = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))
    return whole + (int(m.group(2)) / 10 ** len(m.group(2)) if m.group(2) else 0)


def threads():
    return sminos.threads_module()


def records():
    return sminos.sibling_module("sminos_records")


# ------------------------------------------------------------ the store


def tasks_dir():
    return os.path.join(sminos.root(), "tasks")


def state_path():
    return os.path.join(tasks_dir(), "state.json")


def lock_path():
    return os.path.join(tasks_dir(), ".lock")


def new_state():
    return {"v": V, "version": VERSION, "seq": 0, "nextId": 1, "tasks": {}, "applied": {}, "successors": {}}


def _shaped(s):
    return (isinstance(s, dict) and type(s.get("seq")) is int and type(s.get("nextId")) is int
            and type(s.get("version")) is int and isinstance(s.get("tasks"), dict)
            and isinstance(s.get("applied"), dict) and isinstance(s.get("successors"), dict))


def read_state():
    """The store as its file holds it, or None when there is none; Refused (1) for one that cannot be read. A
    replace is whole, so one read is one state."""
    try:
        with open(state_path(), "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Refused(EXIT_FAIL, "the store could not be read: %s" % e)
    try:
        state = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise Refused(EXIT_FAIL, "the store, %s, is not a store's JSON" % state_path())
    if not _shaped(state):
        raise Refused(EXIT_FAIL, "the store, %s, is not a store's JSON" % state_path())
    return state


def newer(state):
    return state["version"] > VERSION


class Step:
    """One change of the store, under its lock: `seq` is the store's at this step (the one every history entry the
    step adds carries), `at` its time; `changed` set by whatever changed the state."""

    def __init__(self, state, now):
        self.state = state
        self.now = now
        self.at = stamp(now)
        self.seq = state["seq"] + 1
        self.changed = False


def step(change, create=False, wait=LOCK_WAIT):
    """change(Step) under the store's lock, or change(None) where there is no store (and `create` is false); the
    store replaced when the step changed it. What change returns is returned."""
    if not create and not os.path.exists(state_path()):
        return change(None)
    d = tasks_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        with sminos.flocked(lock_path(), lock_until=time.time() + wait):
            _leftovers(d)
            state = read_state()
            if state is not None and newer(state):
                raise Refused(EXIT_FAIL, "the store is of version %d, newer than this sminos writes (%d): update "
                                         "the sminos plugin" % (state["version"], VERSION))
            if state is None:
                if not create:
                    return change(None)
                state = new_state()
            st = Step(state, clock())
            answer = change(st)
            if st.changed:
                state["seq"] = st.seq
                _replace(state)
            return answer
    except sminos.LockBusy:
        raise Refused(EXIT_BUSY, "the store's lock (%s) was not had in %d s" % (lock_path(), wait))


def _leftovers(d):
    """A temporary file a step that died left: only a step holding the lock writes one, so any is a dead one's."""
    for n in os.listdir(d):
        if n.startswith(".tmp-"):
            try:
                os.unlink(os.path.join(d, n))
            except FileNotFoundError:
                pass


def _replace(state):
    d = tasks_dir()
    data = (json.dumps(state, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, state_path())
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    dfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def open_count(state):
    return sum(1 for t in state["tasks"].values() if t.get("state") == "open")


def task_number(tid):
    return int(tid[1:]) if TASK_ID.fullmatch(str(tid)) else 0


# ------------------------------------------------------------ the asker and the target (§2)


def _fresh_engine():
    """The engine's records read once a call, then shared by every task of the call (session_running)."""
    sminos.running_now("")


def _running(session):
    return sminos.session_running(session) if session else None


def _membership(session):
    """(the project `session` is a member of now with a row there, its alias there), each None where none."""
    try:
        p = sminos.member_project_now(session)
        row = sminos.member_row(p, session) if p is not None else None
    except (OSError, ValueError):
        return None, None
    if row is None:
        return None, None
    return p.id, (row.alias or None)


def asker_of(session, agent=None, membership=None):
    """The asker an assign records: the session's thread (current_record, as sminos_channels._self reads it; none
    for a session with no record), the session, its alias in the project it is a member of now, and the agent."""
    t = threads().current_record(session, fresh=True)
    alias = (membership or _membership(session))[1]
    return {"thread": t["thread"] if t else None, "session": session, "alias": alias, "agent": agent}


_PAIRS = "successors"    # a call's memo: the pairs its entries were resolved under (no asker's key is a string)


def _memo_for(store, memo):
    """The call's memo, for a step reading `store`: valid while the store's pairs are what they were when its
    entries were resolved, emptied when a step of the same call reads other pairs (a /clear between two lines).
    Thread and process state are not checked: the memo is one call's reading of them by design."""
    pairs = store.get("successors") or {}
    if memo.get(_PAIRS) != pairs:
        memo.clear()
        memo[_PAIRS] = json.loads(json.dumps(pairs))
    return memo


def target_of(store, task, memo=None):
    """Whom the task's outcomes go to now (§2), resolved once for each distinct asker of a call through `memo`. It
    reads with no lock and writes nothing."""
    a = task["askers"][0]
    k = (a.get("thread"), a.get("session"))
    if memo is not None and k in memo:
        return dict(memo[k])
    got = _target(store, a)
    if memo is not None:
        memo[k] = dict(got)
    return got


def _target(store, a):
    return _describe(*_resolved(store, a))


def _resolved(store, a):
    """(session, thread id or None, via) of an asker's target: whom target_of describes, and what keeps() reads."""
    session, thread = a.get("session"), a.get("thread")
    if not thread:
        return session, None, "self"
    rec = threads().get(thread)
    first = rec["current"] if rec is not None and rec.get("current") else session
    pair = (store.get("successors") or {}).get(first)
    if isinstance(pair, dict) and not _opened_again(first, pair):
        last = _last_alive(store, first)
        if last is not None:
            return last[0], last[1], "cleared"
    return first, thread, "self"


def _opened_again(first, pair):
    """A process holds `first` that started after its pair was written: its human opened it again after the
    clear (the clearing process itself, still on record for it, started before)."""
    rec = _running(first)
    started = sminos.process_started(rec) if rec is not None else None
    at = epoch(pair.get("at"))
    return started is not None and at is not None and started > at


def _last_alive(store, first):
    """(session, thread id) of the last link of first's chain that is alive, or None. A session met twice ends the
    chain; no count cuts it short."""
    succ = store.get("successors") or {}
    seen, cur, last = {first}, first, None
    while True:
        pair = succ.get(cur)
        if not isinstance(pair, dict):
            return last
        nxt, tid, alive = _link(pair)
        if not nxt or nxt in seen:
            return last
        seen.add(nxt)
        if alive:
            last = (nxt, tid)
        cur = nxt


def _link(pair):
    """(the session a pair leads to, its thread id or None, whether that link is alive). A bound pair leads to its
    thread's current session; an unbound one to its session."""
    th = threads()
    s, tid = str(pair.get("session") or ""), pair.get("thread")
    if tid:
        rec = th.get(tid)
        if rec is None:
            # A record that cannot be read is not known to be gone: alive, and its target `unknown`, never sent to.
            return s, tid, th.unreadable(tid)
        return (rec.get("current") or s), tid, not th.record_ended(rec)
    if not s or _running(s) is None:
        return s, None, False
    p = sminos.last_project(s)
    return s, None, not (p is not None and sminos.retired_in_log(p, s))


def _describe(session, tid, via):
    out = {"session": session, "thread": tid, "project": None, "state": "gone", "runner": "terminal", "wake": None,
           "why": "", "via": via}
    rs = records()
    if rs.unreadable(session):
        out["state"] = "unknown"
        return out
    th = threads()
    if rs.lane_of(rs.read(session)) == "B":
        out["runner"] = "maws"
        out["state"] = "running" if _running(session) else "gone"   # MAWS reopens its own sessions
    else:
        rec = th.get(tid) if tid else None
        if tid and rec is None and th.unreadable(tid):
            out["state"] = "unknown"
            return out
        if rec is not None and th.record_ended(rec):
            out["state"] = "ended"       # even while a process still holds it: an end is deliberate
        elif _running(session):
            out["state"] = "running"
        elif rec is not None:
            out["state"] = "stopped"     # whether or not the sweep has set its stop mark yet
    out["project"] = _membership(session)[0]
    if out["state"] == "stopped":
        out["wake"], out["why"] = sminos.wake_here(session)
    return out


def keeps(thread, period, now=None):
    """Why the three-day rule does not end `thread` (D7), or None: it is the target of an open blocking task, or of
    an outcome whose act asked for a wake, not yet shown and less than `period` old, read from the act's own replace
    on. No store is no exemption; a store that cannot be read keeps it. Read with no lock, writing nothing; the
    target is target_of's, without the state it describes."""
    try:
        store = read_state()
    except Refused as e:
        return "the Task Board's store could not be read (%s)" % e.message
    if store is None:
        return None
    now = clock() if now is None else now
    resolved = {}
    for t in sorted(store["tasks"].values(), key=lambda t: task_number(t.get("id"))):
        why = None
        if t.get("state") == "open" and t.get("class") == "blocking":
            why = "it is the target of %s, a blocking task open on the Task Board" % t["id"]
        else:
            for o in t.get("outcomes") or []:
                at = epoch(o.get("at"))
                if o.get("wake") is True and o.get("shown") is None and at is not None and now - at < period:
                    why = "it is the target of %s, an outcome of the Task Board that asked for a wake and is not " \
                          "yet shown, until %s" % (o.get("key"), stamp(at + period))
                    break
        if why is None:
            continue
        a = t["askers"][0]
        k = (a.get("thread"), a.get("session"))
        if k not in resolved:
            resolved[k] = _resolved(store, a)[1]
        if resolved[k] == thread:
            return why
    return None


def is_asker(store, task, session, memo=None):
    """Whether `session` may revise, withdraw or reopen the task: its target; or the current session of the
    asker's thread; or, for a task with no thread, the asker's session. Nothing else (D2)."""
    if not session:
        return False
    if target_of(store, task, memo)["session"] == session:
        return True
    a = task["askers"][0]
    if a.get("thread"):
        rec = threads().get(a["thread"])
        return rec is not None and rec.get("current") == session
    return a.get("session") == session


def bind(state, session):
    """§2's `bind(store, session)`, in place, inside a step the caller holds (M2's hourly duty calls it in its own):
    each pair whose successor is `session` and not bound yet, bound to the thread whose current session it is now,
    when a live record has it. Whether anything changed."""
    pending = [p for p in (state.get("successors") or {}).values()
               if isinstance(p, dict) and p.get("session") == session and not p.get("thread")]
    if not pending:
        return False
    rec = threads().current_record(session, fresh=True)
    if rec is None:
        return False
    for p in pending:
        p["thread"] = rec["thread"]
    return True


def unbound_for(state, session):
    """Whether a pair names `session` as its successor and is not bound yet."""
    return any(isinstance(p, dict) and p.get("session") == session and not p.get("thread")
               for p in (state.get("successors") or {}).values())


def bind_step(session, wait=LOCK_WAIT):
    """The session's own step that binds the pairs naming it (bind), taken only when one waits to be bound."""
    state = read_state()
    if state is None or not unbound_for(state, session):
        return

    def change(st):
        if st is not None and bind(st.state, session):
            st.changed = True
    step(change, wait=wait)


def cleared(left, begun, wait=LOCK_WAIT):
    """A witnessed /clear's pair, `successors[left]`, in a step of its own (no thread lock is held here), when the
    store exists. One clear has two writers naming the same begun session: a pair already naming `begun` is that
    clear's, kept as it is. A pair naming another is an earlier clear's, of a session its human opened again since:
    this clear's replaces it, unbound, at its own time. Called where the witness is whole: before the alias of the
    session left is released."""
    if not left or not begun or left == begun or not os.path.exists(state_path()):
        return

    def change(st):
        if st is None:
            return
        succ = st.state["successors"]
        pair = succ.get(left)
        if not (isinstance(pair, dict) and pair.get("session") == begun):
            succ[left] = {"session": begun, "thread": None, "at": st.at}
            st.changed = True
        if bind(st.state, begun):
            st.changed = True
    step(change, wait=wait)


# ------------------------------------------------------------ the texts (§5, X6)


def word(kind, task_id):
    return {"done": "marked %s done", "declined": "declined %s", "comment": "commented on %s"}[kind] % task_id


def notice_text(clause, kind, task_id, agent=None):
    """A notice's text: clause `asker`, `successor` or `subagent` (which names the subagent by its id)."""
    if clause == "subagent":
        return NOTICE["subagent"] % (word(kind, task_id), agent, task_id)
    return NOTICE[clause] % (word(kind, task_id), task_id)


def ended_line(kind, task_id):
    how = {"done": "completed", "declined": "declined", "comment": "commented on"}[kind]
    return ENDED % (task_id, how, task_id)


def start_line(open_, blocking, outcomes, more):
    """The start line: the count of the target's open tasks, then the outcomes named, `(kind, task id)` each, and
    how many more wait; each sentence only when it has something to say."""
    parts = []
    if open_:
        parts.append("Tasks you assigned to the human: %d open (%d blocking)." % (open_, blocking))
    if outcomes:
        tail = " (and %d more: sminos task waiting --mine)" % more if more else ""
        parts.append("The human acted on tasks you assigned: %s%s. Read one: sminos task show %s"
                     % ("; ".join(word(k, t) for k, t in outcomes), tail, outcomes[0][1]))
    return "\n".join(parts)


def start_of(state, session, memo=None):
    """(the keys the start line names, the start line) for `session` as its tasks' target."""
    memo = {} if memo is None else memo
    mine = [t for t in state["tasks"].values() if target_of(state, t, memo)["session"] == session]
    open_ = [t for t in mine if t.get("state") == "open"]
    waiting = sorted(((o, t) for t in mine for o in t.get("outcomes") or [] if o.get("shown") is None),
                     key=lambda x: (x[0]["seq"], x[0]["key"]))
    named = waiting[:START_NAMED]
    line = start_line(len(open_), sum(1 for t in open_ if t.get("class") == "blocking"),
                      [(o["kind"], t["id"]) for o, t in named], len(waiting) - len(named))
    return [o["key"] for o, _ in named], line


# ------------------------------------------------------------ the door (§3, X2)


def _no_surrogate(s):
    return not any("\ud800" <= c <= "\udfff" for c in s)


def _refuse_constant(name):
    raise ValueError("%s is no JSON value" % name)


def check_line(obj, where="the line"):
    """The line when it is one of §3's, else Refused (2): every field its act lists and no other, each of its type
    exactly (a boolean is no integer and an integer no boolean, as JSON Schema reads them)."""
    def bad(why):
        raise Refused(EXIT_USAGE, "%s: %s" % (where, why))
    if not isinstance(obj, dict):
        bad("not a JSON object")
    act = obj.get("act")
    if not isinstance(act, str) or act not in LINE_FIELDS:
        bad("act is one of %s" % ", ".join(LINE_FIELDS))
    fields = LINE_FIELDS[act]
    extra, missing = sorted(set(obj) - set(fields)), [f for f in fields if f not in obj]
    if extra or missing:
        bad("a %s line has %s" % (act, "no field %s" % ", ".join(extra) if extra else "a %s" % ", ".join(missing)))
    if type(obj["v"]) is not int or obj["v"] != 1:
        bad("v is 1")
    if not (isinstance(obj["key"], str) and UUID.fullmatch(obj["key"])):
        bad("key is a UUID")
    if not (isinstance(obj["task"], str) and TASK_ID.fullmatch(obj["task"])):
        bad("task is an id, t<n>")
    if "revision" in obj and not (type(obj["revision"]) is int and obj["revision"] >= 1):
        bad("revision is an integer from 1")
    if "text" in obj:
        t = obj["text"]
        if not (isinstance(t, str) and len(t) <= TEXT_MAX and _no_surrogate(t)):
            bad("text is a string of at most %d characters" % TEXT_MAX)
        if act in ("decline", "comment") and not t:
            bad("a %s's text is not empty" % act)
    if "wake" in obj and not (obj["wake"] is None or type(obj["wake"]) is bool):
        bad("wake is true, false or null")
    if "seq" in obj and not (type(obj["seq"]) is int and obj["seq"] >= 0):
        bad("seq is an integer from 0")
    if "session" in obj and not (isinstance(obj["session"], str) and UUID.fullmatch(obj["session"])):
        bad("session is a session id")
    if "keys" in obj and not (isinstance(obj["keys"], list) and 1 <= len(obj["keys"]) <= 1000 and all(
            isinstance(k, str) and OUTCOME_KEY.fullmatch(k) for k in obj["keys"])):
        bad("keys is a list of outcome keys, t<n>.<m>")
    return obj


def read_lines(raw):
    """The door's lines, every one checked before any is applied."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(EXIT_USAGE, "standard input is not UTF-8")
    lines = [(i, s) for i, s in enumerate(text.split("\n"), 1) if s.strip()]
    if not lines:
        raise Refused(EXIT_USAGE, "no line on standard input")
    if len(lines) > LINES_MAX:
        raise Refused(EXIT_USAGE, "%d lines: at most %d a call" % (len(lines), LINES_MAX))
    out = []
    for i, s in lines:
        try:
            obj = json.loads(s, parse_constant=_refuse_constant)
        except ValueError:
            raise Refused(EXIT_USAGE, "line %d: not JSON" % i)
        out.append(check_line(obj, "line %d" % i))
    return out


def digest(line):
    return hashlib.sha256(json.dumps(line, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def told_of(target, outcome):
    """How the asker is to be told (§3's table, as M1 answers it): `ended` and `maws` as M2 will; `next-start`
    wherever M2 answers `now` or `wake`, since nothing is sent until it is installed."""
    if target["state"] == "ended":
        return "ended"
    if target["runner"] == "maws" and target["state"] == "gone" and outcome["wake"]:
        return "maws"
    return "next-start"


def apply_line(line, memo=None):
    """One checked line of the door in a step of its own: its verdict, whatever it is (applied, stale, closed,
    unknown), kept under its key in the replace that decides it, so the same line again answers the same, `told`
    included, and changes nothing; `refused` (key-reused) answers a key already kept and is not kept itself.
    `memo`: the call's targets, shared by every line of one call, so a task's target is resolved once for each
    distinct asker (§2)."""
    memo = {} if memo is None else memo
    key, act, tid = line["key"], line["act"], line["task"]
    head = {"v": V, "key": key, "act": act}

    def change(st):
        s = st.state
        _memo_for(s, memo)
        dg = digest(line)
        prior = s["applied"].get(key)
        if isinstance(prior, dict):
            if prior.get("digest") == dg and isinstance(prior.get("verdict"), dict):
                return prior["verdict"]
            return dict(head, verdict="refused", reason="key-reused")   # answers a key kept: not kept itself
        verdict = judged(st, s)
        # The first verdict, whatever it was, is the key's: the same line again answers it and changes nothing.
        s["applied"][key] = {"task": tid, "at": st.at, "digest": dg, "verdict": verdict}
        st.changed = True
        return verdict

    def judged(st, s):
        t = s["tasks"].get(tid)
        if not isinstance(t, dict):
            return dict(head, verdict="unknown", task=tid)
        where = {"task": tid, "revision": t["revision"], "state": t["state"]}
        if act in ("done", "decline", "comment") and t["state"] != "open":
            return dict(head, verdict="closed", **where)
        if act in ("done", "decline") and line["revision"] != t["revision"]:
            return dict(head, verdict="stale", **where)
        if act in KIND:
            verdict = _act(st, t, line, KIND[act], target_of(s, t, memo), head)
        elif act == "seen":
            t["seenSeq"] = max(t["seenSeq"], min(line["seq"], s["seq"]))
            verdict = dict(head, verdict="applied", **where)
        else:
            # Whose an outcome is decides a mark: resolved afresh against this step's store and thread records, never
            # from the call's memo, since a hand-off or a /clear between two lines moves it (§2).
            marked = []
            target = target_of(s, t)
            for k in line["keys"]:
                o = _outcome(t, k)
                if (o is not None and o.get("shown") is None and k not in marked
                        and target["session"] == line["session"]):
                    o["shown"] = {"at": st.at, "session": line["session"]}
                    marked.append(k)
            verdict = dict(head, verdict="applied", **where, keys=marked)
        return verdict
    # A line where no store is yet makes it: its verdict (unknown) is kept like any other.
    return step(change, create=True)


def _outcome(t, k):
    m = OUTCOME_KEY.fullmatch(k)
    if not m or m.group(1) != t["id"]:
        return None
    return next((o for o in t.get("outcomes") or [] if o.get("key") == k), None)


def _act(st, t, line, kind, target, head):
    """A done, a decline or a human's comment applied to the open task `t`: its outcome, and the verdict."""
    t["acts"] = t["acts"] + 1
    okey = "%s.%d" % (t["id"], t["acts"])
    wake = line["wake"] if line["wake"] is not None else t.get("class") == "blocking"
    if kind == "comment":
        t["comments"].append({"n": len(t["comments"]) + 1, "seq": st.seq, "by": "human", "at": st.at,
                              "text": line["text"], "outcome": okey})
    else:
        t["state"] = kind
        t["closed"] = {"how": kind, "seq": st.seq, "at": st.at, "text": line["text"]}
    outcome = {"key": okey, "seq": st.seq, "kind": kind, "at": st.at, "revision": t["revision"],
               "text": line["text"], "wake": wake, "shown": None, "send": None, "endedLine": None}
    t["outcomes"].append(outcome)
    return dict(head, verdict="applied", task=t["id"], revision=t["revision"], state=t["state"], outcome=okey,
                told=told_of(target, outcome))


def jline(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


VERDICT_ORDER = ("v", "key", "act", "verdict", "task", "revision", "state", "outcome", "told", "keys", "reason")


def verdict_line(v):
    """A verdict as the door prints it, its keys in §3's order whatever order the store kept them in."""
    return jline({**{k: v[k] for k in VERDICT_ORDER if k in v}, **{k: x for k, x in v.items() if k not in
                                                                   VERDICT_ORDER}})


# ------------------------------------------------------------ what a person reads


def safe(s):
    """Text someone else wrote, as a terminal prints it on one line (the sheet's `show` rule): CRLF one break, a
    line break or a tab a space, every other C0, DEL and C1 character out."""
    return CONTROLS.sub("", SPACED.sub(" ", str(s)))


def local_time(ts):
    t = epoch(ts)
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t is not None else str(ts)


def _project_name(pid):
    if not pid:
        return "—"
    try:
        p = sminos.known_project(pid)
    except (OSError, ValueError):
        p = None
    return safe(p.name) if p is not None and p.name else pid


def _who(a):
    alias = a.get("alias")
    return safe(alias) if alias else "[%s]" % str(a.get("session") or "")[:8]


def state_words(target):
    if target["runner"] == "maws":
        return "run by MAWS"
    if target["state"] == "stopped":
        return "stopped, to be woken" if target["wake"] != "held" else "stopped, held: %s" % (target["why"] or "?")
    return target["state"]


def row(t, target):
    cells = [t["id"], t["class"], '"%s"' % safe(t["title"]), _project_name(t.get("project")),
             "%s (%s)" % (_who(t["askers"][0]), state_words(target)), "due " + (t.get("due") or "—")]
    if t["agentSeq"] > t["seenSeq"]:
        cells.append("Updated")
    return "  ".join(cells)


def board_order(t):
    rank = CLASSES.index(t["class"]) if t.get("class") in CLASSES else len(CLASSES)
    return rank, (t.get("due") or "9999-99-99") if t.get("class") == "needed" else "", task_number(t["id"])


def reader_task(state, t, memo):
    out = dict(t)
    out["target"] = target_of(state, t, memo)
    out["updated"] = t["agentSeq"] > t["seenSeq"]
    return out


def closed_lately(t, now):
    c = t.get("closed")
    at = epoch(c.get("at")) if isinstance(c, dict) else None
    return t.get("state") != "open" and at is not None and now - at <= KEPT


def history(t):
    """A task's history by seq: each agent's comment, each act of the human with its word and its text, a
    withdrawal; a human's comment and its outcome are one line."""
    lines = []
    for c in t.get("comments") or []:
        if c.get("by") == "human":
            continue
        by = c.get("by") or {}
        who = _who(by)
        agent = by.get("agent") if isinstance(by.get("agent"), dict) else None
        if agent:
            who += ", subagent %s" % safe(agent.get("id"))
        lines.append((c["seq"], "comment  %s  %s  \"%s\"" % (local_time(c["at"]), who, safe(c["text"]))))
    for o in t.get("outcomes") or []:
        w = {"done": "done", "declined": "declined", "comment": "commented"}[o["kind"]]
        said = '  "%s"' % safe(o["text"]) if o.get("text") else ""
        lines.append((o["seq"], "%s  %s%s" % (w, local_time(o["at"]), said)))
    c = t.get("closed")
    if isinstance(c, dict) and c.get("how") == "withdrawn":
        said = '  "%s"' % safe(c["text"]) if c.get("text") else ""
        lines.append((c["seq"], "withdrawn  %s%s" % (local_time(c["at"]), said)))
    return [text for _, text in sorted(lines, key=lambda x: x[0])]


def show_text(t, target):
    a = t["askers"][0]
    out = [row(t, target)]
    asked = "asked by %s" % _who(a) + (" [%s]" % str(a.get("session"))[:8] if a.get("alias") else "")
    agent = a.get("agent") if isinstance(a.get("agent"), dict) else None
    if agent:
        asked += ", its subagent %s%s" % (safe(agent["id"]), " (%s)" % safe(agent["name"]) if agent.get("name") else "")
    out.append("  %s, at revision %d, %s" % (asked, t["revision"], t["state"]))
    if target["session"] != a.get("session") or target["via"] == "cleared":
        out.append("  told now: [%s] (%s%s)" % (target["session"][:8], state_words(target),
                                               ", after a /clear" if target["via"] == "cleared" else ""))
    body = str(t.get("body") or "")
    if body:
        out.append("")
        for ln in body.replace("\r\n", "\n").split("\n"):
            out.append("    " + CONTROLS.sub("", ln.replace("\t", " ")))
    hist = history(t)
    if hist:
        out.append("")
        out += ["  " + h for h in hist]
    return "\n".join(out)


# ------------------------------------------------------------ the commands


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused(EXIT_USAGE, message)


USAGE = ("usage: sminos task assign|revise|comment|withdraw|reopen|show|list|waiting|done|decline|act "
         "... (sminos help)")


def parser():
    p = _Parser(prog="sminos task", add_help=False)
    sub = p.add_subparsers(dest="op")

    def wake(o):
        o.add_argument("--wake", dest="wake", action="store_const", const=True, default=None)
        o.add_argument("--no-wake", dest="wake", action="store_const", const=False)

    o = sub.add_parser("assign", add_help=False)
    o.add_argument("--class", dest="cls", required=True, choices=CLASSES)
    o.add_argument("--title", required=True)
    o.add_argument("--body-file", default=None)
    o.add_argument("--due", default=None)
    o.add_argument("--no-due", action="store_true")
    o.add_argument("--tag", action="append", default=[])
    o.add_argument("--asker-agent", default=None)
    o.add_argument("--asker-name", default=None)
    o = sub.add_parser("revise", add_help=False)
    o.add_argument("id")
    o.add_argument("--title", default=None)
    o.add_argument("--body-file", default=None)
    o.add_argument("--class", dest="cls", default=None, choices=CLASSES)
    o.add_argument("--due", default=None)
    o.add_argument("--no-due", action="store_true")
    o.add_argument("--tag", action="append", default=[])
    o.add_argument("--no-tags", action="store_true")
    o = sub.add_parser("comment", add_help=False)
    o.add_argument("id")
    o.add_argument("text", nargs="?", default=None)
    o.add_argument("--body-file", default=None)
    o.add_argument("--key", default=None)
    wake(o)
    o = sub.add_parser("withdraw", add_help=False)
    o.add_argument("id")
    o.add_argument("--reason", default="")
    o = sub.add_parser("reopen", add_help=False)
    o.add_argument("id")
    o.add_argument("--comment", required=True)
    o = sub.add_parser("show", add_help=False)
    o.add_argument("id")
    o.add_argument("--json", action="store_true")
    o = sub.add_parser("list", add_help=False)
    o.add_argument("--closed", action="store_true")
    o.add_argument("--all", action="store_true")
    o.add_argument("--mine", action="store_true")
    o.add_argument("--json", action="store_true")
    o = sub.add_parser("waiting", add_help=False)
    o.add_argument("--mine", action="store_true")
    o.add_argument("--json", action="store_true")
    for op in ("done", "decline"):
        o = sub.add_parser(op, add_help=False)
        o.add_argument("handle")
        o.add_argument("--note" if op == "done" else "--reason", dest="text", default=None)
        o.add_argument("--key", default=None)
        wake(o)
    sub.add_parser("act", add_help=False)
    o = sub.add_parser("remind", add_help=False)
    o.add_argument("--session", required=True)
    o.add_argument("--source", default="")
    o = sub.add_parser("shown", add_help=False)
    o.add_argument("--session", required=True)
    o.add_argument("--keys", default="")
    return p


def caller():
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def need_session():
    s = caller()
    if not UUID.fullmatch(s):
        raise Refused(EXIT_REFUSED, NEEDS_SESSION)
    return s


def refuse_session():
    if caller():
        raise Refused(EXIT_REFUSED, IN_SESSION)


def session_arg(s):
    if not UUID.fullmatch(s or ""):
        raise Refused(EXIT_USAGE, "--session is a session id")
    return s


def task_arg(s):
    if not TASK_ID.fullmatch(s or ""):
        raise Refused(EXIT_USAGE, "%r is no task id (t<n>)" % s)
    return s


def checked_text(what, s, limit, empty=False):
    """Text for the store, held to the door's rule (check_line): empty means the empty string, nothing else."""
    if not isinstance(s, str) or not _no_surrogate(s):
        raise Refused(EXIT_USAGE, "%s is not text" % what)
    if not empty and not s:
        raise Refused(EXIT_USAGE, "%s is empty" % what)
    if len(s) > limit:
        raise Refused(EXIT_USAGE, "%s is longer than %d characters" % (what, limit))
    return s


def checked_title(s):
    checked_text("the title", s, TITLE_MAX)
    if not s.strip():
        raise Refused(EXIT_USAGE, "the title says nothing")
    if CONTROLS.search(s) or SPACED.search(s):
        raise Refused(EXIT_USAGE, "the title is one line, with no control character")
    return s


def checked_due(s):
    if not DATE.fullmatch(s or ""):
        raise Refused(EXIT_USAGE, "--due is a date, YYYY-MM-DD")
    try:
        datetime.date(int(s[:4]), int(s[5:7]), int(s[8:]))
    except ValueError:
        raise Refused(EXIT_USAGE, "--due %s is no date" % s)
    return s


def checked_tags(tags):
    if len(tags) > TAGS_MAX:
        raise Refused(EXIT_USAGE, "at most %d tags" % TAGS_MAX)
    for t in tags:
        if not TAG.fullmatch(t):
            raise Refused(EXIT_USAGE, "a tag is 1 to 32 of a-z, 0-9 and -: %r" % t)
    return list(dict.fromkeys(tags))


def body_from(source, what="the body"):
    """A body from `--body-file F`, or standard input for `-` (less one trailing line ending), strictly UTF-8."""
    try:
        if source == "-":
            if sys.stdin is None or sys.stdin.isatty():
                raise Refused(EXIT_USAGE, "%s -: standard input is a terminal; give it a heredoc or a file" % what)
            raw = sys.stdin.buffer.read()
        else:
            with open(source, "rb") as f:
                raw = f.read()
    except OSError as e:
        raise Refused(EXIT_USAGE, "%s could not be read: %s" % (what, e))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused(EXIT_USAGE, "%s is not UTF-8" % what)
    return text[:-2] if text.endswith("\r\n") else text[:-1] if text.endswith("\n") else text


def reduced_name(name):
    if not name:
        return None
    n = NAME_OUT.sub("-", name)[:64]
    return n or None


def _task_of(st, tid):
    if st is None or not isinstance(st.state["tasks"].get(tid), dict):
        raise Refused(EXIT_REFUSED, "no task %s on this machine's board" % tid)
    return st.state["tasks"][tid]


def _the_askers(st, t, session, verb):
    if not is_asker(st.state, t, session, {}):
        raise Refused(EXIT_REFUSED, "%s is not this session's to %s: only the session that asked (or the one that "
                                    "took its place at a /clear) does" % (t["id"], verb))


def cmd_assign(a):
    session = need_session()
    cls, title = a.cls, checked_title(a.title)
    body = checked_text("the body", body_from(a.body_file), BODY_MAX, empty=True) if a.body_file is not None else ""
    due = None if a.no_due or a.due is None else checked_due(a.due)
    tags = checked_tags(a.tag)
    agent = None
    if a.asker_agent is not None:
        if not AGENT_ID.fullmatch(a.asker_agent):
            raise Refused(EXIT_USAGE, "--asker-agent is 1 to 128 of A-Z, a-z, 0-9, _ . @ -")
        agent = {"id": a.asker_agent, "name": reduced_name(a.asker_name)}
    membership = _membership(session)
    asker = asker_of(session, agent, membership)

    def change(st):
        s = st.state
        if bind(s, session):
            st.changed = True
        n = open_count(s)
        if n >= OPEN_MAX:
            raise Refused(EXIT_REFUSED, "the board holds %d open tasks, its most: close some first" % n)
        tid = "t%d" % s["nextId"]
        s["nextId"] += 1
        s["tasks"][tid] = {
            "id": tid, "revision": 1, "state": "open", "class": cls, "title": title, "body": body, "due": due,
            "tags": tags, "project": membership[0], "askers": [asker], "born": st.seq, "createdAt": st.at,
            "agentSeq": st.seq, "seenSeq": st.seq, "comments": [], "closed": None, "acts": 0, "outcomes": []}
        st.changed = True
        return tid
    tid = step(change, create=True)
    print("%s %s %s" % (tid, cls, json.dumps(title, ensure_ascii=False)))


def cmd_revise(a):
    session = need_session()
    tid = task_arg(a.id)
    fields = {}
    if a.title is not None:
        fields["title"] = checked_title(a.title)
    if a.body_file is not None:
        fields["body"] = checked_text("the body", body_from(a.body_file), BODY_MAX, empty=True)
    if a.cls is not None:
        fields["class"] = a.cls
    if a.no_due:
        fields["due"] = None
    elif a.due is not None:
        fields["due"] = checked_due(a.due)
    if a.no_tags:
        fields["tags"] = []
    elif a.tag:
        fields["tags"] = checked_tags(a.tag)
    if not fields:
        raise Refused(EXIT_USAGE, "revise %s: nothing to change (--title, --body-file, --class, --due, --tag)" % tid)

    def change(st):
        t = _task_of(st, tid)
        if bind(st.state, session):
            st.changed = True
        _the_askers(st, t, session, "revise")
        if t["state"] != "open":
            raise Refused(EXIT_REFUSED, "%s is %s: only an open task is revised" % (tid, t["state"]))
        t.update(fields)
        t["revision"] += 1
        t["agentSeq"] = st.seq
        st.changed = True
        return t["revision"]
    print("%s revision %d" % (tid, step(change)))


def cmd_comment(a):
    tid = task_arg(a.id)
    if a.body_file is not None and a.text is not None:
        raise Refused(EXIT_USAGE, "comment %s: a text or --body-file, not both" % tid)
    text = body_from(a.body_file, "the comment") if a.body_file is not None else a.text
    if text is None:
        raise Refused(EXIT_USAGE, "comment %s: no text (a last argument, or --body-file F|-)" % tid)
    session = caller()
    if not session:
        # The human's comment is the door's line: the door's check is its only one.
        return human_act({"act": "comment", "task": tid, "text": text, "wake": a.wake}, a.key)
    need_session()
    checked_text("the comment", text, TEXT_MAX)
    if a.key is not None or a.wake is not None:
        raise Refused(EXIT_USAGE, "--key and --wake are the human's, at a terminal that is no session")
    alias = _membership(session)[1]

    def change(st):
        t = _task_of(st, tid)
        if bind(st.state, session):
            st.changed = True
        if t["state"] != "open":
            raise Refused(EXIT_REFUSED, "%s is %s: a closed task takes no comment" % (tid, t["state"]))
        n = len(t["comments"]) + 1
        t["comments"].append({"n": n, "seq": st.seq, "by": {"session": session, "alias": alias, "agent": None},
                              "at": st.at, "text": text, "outcome": None})
        t["agentSeq"] = st.seq
        st.changed = True
        return n
    print("%s comment %d" % (tid, step(change)))


def cmd_withdraw(a):
    session = need_session()
    tid = task_arg(a.id)
    reason = checked_text("the reason", a.reason, TEXT_MAX, empty=True)

    def change(st):
        t = _task_of(st, tid)
        if bind(st.state, session):
            st.changed = True
        _the_askers(st, t, session, "withdraw")
        if t["state"] != "open":
            raise Refused(EXIT_REFUSED, "%s is %s: only an open task is withdrawn" % (tid, t["state"]))
        t["state"] = "withdrawn"
        t["closed"] = {"how": "withdrawn", "seq": st.seq, "at": st.at, "text": reason}
        st.changed = True
    step(change)
    print("%s withdrawn" % tid)


def cmd_reopen(a):
    session = need_session()
    tid = task_arg(a.id)
    text = checked_text("the comment", a.comment, TEXT_MAX)
    alias = _membership(session)[1]

    def change(st):
        t = _task_of(st, tid)
        if bind(st.state, session):
            st.changed = True
        _the_askers(st, t, session, "reopen")
        if t["state"] != "done":
            raise Refused(EXIT_REFUSED, "%s is %s: only a done task is reopened" % (tid, t["state"]))
        n = open_count(st.state)
        if n >= OPEN_MAX:
            raise Refused(EXIT_REFUSED, "the board holds %d open tasks, its most: close some first" % n)
        t["state"] = "open"
        t["closed"] = None
        t["revision"] += 1
        t["comments"].append({"n": len(t["comments"]) + 1, "seq": st.seq,
                              "by": {"session": session, "alias": alias, "agent": None}, "at": st.at, "text": text,
                              "outcome": None})
        t["agentSeq"] = st.seq
        st.changed = True
        return t["revision"]
    print("%s reopened: revision %d" % (tid, step(change)))


def human_act(fields, key):
    """A door's line made for the caller (done, decline, the human's comment): its key printed on standard error
    before anything is applied, then the verdict; exit 0 for applied, 3 otherwise."""
    refuse_session()
    if key is None:
        key = str(uuid.uuid4())
    elif not UUID.fullmatch(key):
        raise Refused(EXIT_USAGE, "--key is a UUID")
    line = check_line({"v": V, "key": key, **fields})
    sys.stderr.write("key %s\n" % key)
    sys.stderr.flush()
    verdict = apply_line(line)
    print(verdict_line(verdict))
    return 0 if verdict["verdict"] == "applied" else EXIT_REFUSED


def cmd_done(a, act):
    refuse_session()
    m = HANDLE.fullmatch(a.handle or "")
    if not m:
        raise Refused(EXIT_USAGE, "%r is no task (t7, or t7@2 for the revision read)" % a.handle)
    # The door's line made for the caller: the door's check (check_line) is its only one.
    return human_act({"act": act, "task": m.group(1), "revision": int(m.group(2) or 1), "text": a.text or "",
                      "wake": a.wake}, a.key)


def cmd_act(_a):
    refuse_session()
    lines = read_lines(sys.stdin.buffer.read() if sys.stdin is not None else b"")
    memo = {}
    for line in lines:
        print(verdict_line(apply_line(line, memo)), flush=True)
    return 0


def _reader_state():
    state = read_state()
    return state if state is not None else new_state()


def _mine(a):
    if not a.mine:
        return None
    return need_session()


def cmd_list(a):
    mine = _mine(a)
    state, now, memo = _reader_state(), clock(), {}
    tasks = sorted(state["tasks"].values(), key=lambda t: task_number(t["id"]))
    if a.all:
        tasks = [t for t in tasks if t.get("state") == "open" or closed_lately(t, now)]
    elif a.closed:
        tasks = [t for t in tasks if closed_lately(t, now)]
    else:
        tasks = [t for t in tasks if t.get("state") == "open"]
    rows = [reader_task(state, t, memo) for t in tasks]
    if mine is not None:
        rows = [r for r in rows if r["target"]["session"] == mine]
    if a.json:
        print(jline({"v": V, "seq": state["seq"], "tasks": rows}))
        return 0
    if not rows:
        print("no %s on this machine's board" % ("tasks" if a.all else "closed tasks" if a.closed else "open tasks"))
        return 0
    for r in sorted(rows, key=board_order):
        print(row(r, r["target"]))
    return 0


def cmd_show(a):
    tid = task_arg(a.id)
    state = _reader_state()
    t = state["tasks"].get(tid)
    if not isinstance(t, dict):
        raise Refused(EXIT_REFUSED, "no task %s on this machine's board" % tid)
    r = reader_task(state, t, {})
    if a.json:
        print(jline({"v": V, "seq": state["seq"], "task": r}))
        return 0
    print(show_text(r, r["target"]), flush=True)
    if not caller():
        # The human read this snapshot: a `seen` for its seq, a step of its own after the print.
        try:
            apply_line({"v": V, "key": str(uuid.uuid4()), "act": "seen", "task": tid, "seq": state["seq"]})
        except (Refused, OSError) as e:
            sys.stderr.write("sminos: task show: what was read is not marked seen: %s\n"
                             % getattr(e, "message", e))
    return 0


def cmd_waiting(a):
    mine = _mine(a)
    state, memo = _reader_state(), {}
    rows = []
    for t in state["tasks"].values():
        target = None
        for o in t.get("outcomes") or []:
            if o.get("shown") is not None:
                continue
            target = target or target_of(state, t, memo)
            if mine is not None and target["session"] != mine:
                continue
            rows.append({"key": o["key"], "task": t["id"], "state": t["state"], "kind": o["kind"], "seq": o["seq"],
                         "at": o["at"], "wake": o["wake"], "send": o.get("send"), "target": target})
    rows.sort(key=lambda r: (r["seq"], r["key"]))
    if a.json:
        print(jline({"v": V, "seq": state["seq"], "waiting": rows}))
        return 0
    for r in rows:
        print("%s  %s  %s" % (r["key"], word(r["kind"], r["task"]), local_time(r["at"])))
    return 0


def cmd_remind(a):
    """The start hook's first call: a witnessed /clear's pair registered, this session's pairs bound, then the keys
    of the outcomes it is about to name on a line of their own, and the start line. It marks nothing."""
    session = session_arg(a.session)
    if not os.path.exists(state_path()):
        print("")
        return 0
    _fresh_engine()
    if a.source == "clear":
        try:
            left = sminos.cleared_witness(session, "clear")[0]
        except (OSError, ValueError):
            left = ""
        if left:
            try:
                cleared(left, session)       # the full wait: a pair not written here may be written nowhere
            except Refused as e:
                if e.code != EXIT_BUSY:
                    raise
    try:
        bind_step(session, wait=HOOK_LOCK_WAIT)
    except Refused as e:
        if e.code != EXIT_BUSY:
            raise
    state = _reader_state()
    keys, text = start_of(state, session)
    print(" ".join(keys))
    if text:
        print(text)
    if a.source == "fork" and open_count(state):
        print(FORK)
    return 0


def cmd_shown(a):
    """The start hook's second call: each key named that still waits and whose target is this session now, marked
    shown to it; nothing takes the place of one passed over. Its pairs bound in the same step."""
    session = session_arg(a.session)
    keys = [k for k in (a.keys or "").split(",") if k]
    for k in keys:
        if not OUTCOME_KEY.fullmatch(k):
            raise Refused(EXIT_USAGE, "--keys holds outcome keys, t<n>.<m>: %r" % k)
    if not keys:
        # An ordinary start's call with nothing to mark: the lock only when a pair waits to be bound.
        state = read_state()
        if state is None or not unbound_for(state, session):
            print("")
            return 0
    _fresh_engine()

    def change(st):
        if st is None:
            return []
        s, marked = st.state, []
        if bind(s, session):
            st.changed = True
        for k in keys:
            t = s["tasks"].get(k.split(".")[0])
            o = _outcome(t, k) if isinstance(t, dict) else None
            if o is not None and o.get("shown") is None and k not in marked \
                    and target_of(s, t)["session"] == session:   # afresh, as the door's shown (§2)
                o["shown"] = {"at": st.at, "session": session}
                marked.append(k)
        if marked:
            st.changed = True
        return marked
    print(" ".join(step(change)))
    return 0


VERBS = {"assign": cmd_assign, "revise": cmd_revise, "comment": cmd_comment, "withdraw": cmd_withdraw,
         "reopen": cmd_reopen, "show": cmd_show, "list": cmd_list, "waiting": cmd_waiting,
         "done": lambda a: cmd_done(a, "done"), "decline": lambda a: cmd_done(a, "decline"), "act": cmd_act,
         "remind": cmd_remind, "shown": cmd_shown}


def run(argv):
    if not argv:
        raise Refused(EXIT_USAGE, USAGE)
    a = parser().parse_args(argv)
    if a.op not in VERBS:
        raise Refused(EXIT_USAGE, USAGE)
    if a.op not in ("remind", "shown"):
        _fresh_engine()
    return VERBS[a.op](a) or 0


def cmd_task(a):
    """`sminos task …`: the verb's exit, or its refusal on standard error with its code."""
    argv = list(getattr(a, "argv", None) or [])
    try:
        code = run(argv)
    except Refused as e:
        sys.stdout.flush()
        sys.stderr.write("sminos: task%s: %s\n" % (" " + argv[0] if argv else "", e.message))
        sys.exit(e.code)
    except OSError as e:
        sys.stdout.flush()
        sys.stderr.write("sminos: task%s: the store could not be written: %s\n" % (" " + argv[0] if argv else "", e))
        sys.exit(EXIT_FAIL)
    sys.stdout.flush()
    if code:
        sys.exit(code)
