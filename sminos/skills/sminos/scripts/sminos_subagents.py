"""A session's subagents as `sminos list --subagents` shows them (the view
that stands in for the engine's ListAgents): each one's lifecycle, from the
engine where the session's bridge answers, else read from the disk the
engine writes for it, and apart from it what the agent is doing (in Bash
12m, no write 14m).

The engine's word is the bridge's (GET /agents): the agents the engine's own
list (`$.agent.list()`, hooks/mods/bridge-agents.tsx) and the spawn hooks
reported, each with whether its loop runs and, where the list said it, the
list's status (running, idle, waiting, completed, failed, killed). An agent
the engine holds as running runs, however long since its transcript was
written (a long inference writes nothing); one it holds as ended has ended,
and the disk says how when the engine gave no word.

The disk is the session's `<transcript>/subagents/`: per agent its meta
(`agent-<id>.meta.json`, every key optional) and its transcript
(`agent-<id>.jsonl`). The meta's `finished` is written when a turn ends,
even while a background task it started still runs and before a
SendMessage revives it, so the transcript decides: its last conversation
row says whether the turn is open (a tool in flight, or the model at work)
or closed (an `end_turn` reply, or a result that ends the turn, as a
handback's does). A closed turn whose shells, monitors or background child
agents still run is waiting on them; whether a task still runs is what the
desk's ledger says from every row of the loop's own naming it (sminos_jobs:
its start, a notification, a `task_status`, a TaskStop), and then the main
loop's TaskStops and the bridge's stop notes (which leave no notification),
and the notices the engine queued in the main loop's transcript that a task
ended (a task that ends as its agent hands back has its notice queued for
the agent and never delivered, so no row of the agent's says it ended),
never the absence of a notification alone. An open turn whose agent was
stopped by its parent (TaskStop) leaves no word in its own rows: the parent
loop's TaskStops on it, made since that turn began, say so. A revival
(`revivedAt`, a SendMessage to an ended agent) opens a turn again; the
bridge, which learns an agent's end but no revival, is then not believed
over the rows.

A loop runs only inside the session's process, so an agent whose transcript
was last written before the running process started (or whose session runs
no process) is past: ended if its turn closed or its parent's rows end it,
orphaned if it was cut off. Each agent reads its transcript's tail backwards
(mmap, the engine's request records skipped unparsed) to its last
conversation row, an open turn back to where it began. The main loop's
transcript, often hundreds of megabytes, is read only from where its rows
reach the time asked (found by bisection on the rows' timestamps): its
TaskStops back to the earliest open turn asking, its stop notes and queued
notices back to the running process's start; each byte at most once a view.

Lifecycle: running, waiting (on background), stalled (disk only: open,
nothing in flight, no write for `stall` seconds), orphaned, and the ended
ones: completed, failed, stopped (by the user, by TaskStop, or killed).

A past agent — no word of the engine's on it, and none of its files written
by the running process, or no process runs — is therefore ended or
orphaned, never running or waiting, nor can it hold a parent waiting. The
default view lists the agents running, waiting or stalled, and those that
ended in the last ten minutes, and counts every other one: a past agent is
counted from its directory's listing and stats alone, its meta and
transcript unread. --all, --done and --json derive each agent they carry.

An ended state the disk gives is final until the agent's own files change
(a revival by SendMessage writes its meta's `revivedAt` and its transcript),
so it is kept, per session (`cache`), and read back while the files'
identities hold (inode, size, the times of the last write and status
change). The key holds what else the state was read from: the parent whose
loop's TaskStops can end it (a loop's transcript only grows: a stop once
found stays found), and whether the running process wrote it, with that
process's start — a closed turn of the running process is completed only
while no background task it started runs (its own rows, then the main
loop's stops since that start, which only add ends) and no child of it is
live; a child runs again with no write to its parent's files, so that is
asked again on every use. Only completed, failed and stopped are kept, and
only where the disk decides: where the engine holds the agent its word is
asked first, every time, and never kept. A file missing, unreadable or of
another version, or an entry that is not well formed, is ignored, and the
file written again.
"""

import datetime
import json
import mmap
import os
import re
import tempfile
import time

import sminos_jobs as jobs

STALL_SECONDS = 600
QUIET_SECONDS = 60   # an agent with nothing in flight and no write for this long says so (`no write 3m`)
# A loop's transcript is read from this long before the time asked: rows are written about in time order, not
# exactly (a row's own timestamp is its start).
EVIDENCE_MARGIN = 120.0
# The bridge's notes that it stopped a task (sminos_jobs.STOP_NOTE, INTERRUPT_ORIGINS), found by these phrases.
STOP_NOTE_PHRASES = (b"a background task, was stopped from", b"The interrupt came from")
# The engine's queue records enqueuing notices (sminos_jobs.queued_notice), found by these bytes: the engine writes
# keys unescaped, so a row's text, or a request record repeating it, never holds the first.
QUEUE_RECORD = b'"queue-operation"'
NOTICE_OPEN = b"<task-notification>"
TASKSTOP_CALL = b'"name":"TaskStop"'
ACTIVE = ("running", "waiting", "stalled")   # what the default view lists as live
ENDED = ("completed", "failed", "stopped")
# The default view's recently ended: those that ended this long ago at most, this many of them.
RECENT_SECONDS = 600
RECENT_CAP = 5
WORDS = {"running": "running", "waiting": "waiting on background", "stalled": "stalled", "orphaned": "orphaned",
         "completed": "completed", "failed": "failed", "stopped": "stopped"}
# The engine list's words (AgentStatus): a loop alive, or how it ended.
ENGINE_ENDED = {"completed": "completed", "failed": "failed", "killed": "stopped"}
# An assistant row whose stop ends the turn; `tool_use` (and `pause_turn`) leave it open.
CLOSING_STOPS = ("end_turn", "stop_sequence", "max_tokens", "refusal")
# A background shell's or monitor's start, as its result row names it (Bash backgroundTaskId, Monitor taskId).
TASK_START = re.compile(rb'"(?:backgroundTaskId|taskId)"\s*:\s*"([A-Za-z0-9_-]{1,64})"')
# How far back an open turn is walked to find where it began; past it, the transcript's first row stands in.
OPENER_BYTES = 8 << 20
DESCRIPTION_WIDTH = 56
MEMO_VERSION = 1


def _epoch(stamp):
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _iso(t):
    if t is None:
        return None
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _str(value):
    return value if isinstance(value, str) and value else None


def _open_map(path):
    """The file mapped for reading, or None when it is empty or cannot be read."""
    try:
        with open(path, "rb") as f:
            if os.fstat(f.fileno()).st_size == 0:
                return None
            return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        return None


def _rows_back(mm):
    """(row, its line's length) for each row of the transcript, last first; the engine's request records (which
    repeat the conversation, and hold no row) are passed over unparsed."""
    end = len(mm)
    while end > 0:
        start = mm.rfind(b"\n", 0, end) + 1
        if start < end and mm[start:start + len(jobs.REQUEST_RECORD)] != jobs.REQUEST_RECORD:
            try:
                row = json.loads(mm[start:end])
            except ValueError:
                row = None
            if isinstance(row, dict) and _str(row.get("uuid")):
                yield row, end - start
        end = start - 1


def _first_stamp(lines):
    """The time of the transcript's first row that carries one, from its `lines` in order."""
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        if isinstance(row, dict) and _epoch(row.get("timestamp")) is not None:
            return _epoch(row["timestamp"])
    return None


def _message(row):
    """The row's message when it is a conversation row (user or assistant), else None."""
    if row.get("type") not in ("user", "assistant"):
        return None
    msg = row.get("message")
    return msg if isinstance(msg, dict) else None


def _closes(row, msg):
    """Whether this conversation row ends its turn."""
    if row.get("type") == "user":
        return row.get("toolEndsTurn") is True
    if row.get("isApiErrorMessage") is True:
        return True
    content = msg.get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content):
        return False
    return msg.get("stop_reason") in CLOSING_STOPS


def _lines_holding(mm, needle, start=0, end=None):
    """The (start, end) of each line of `mm` from `start` (a line's start) up to `end` holding `needle`, in order."""
    end = len(mm) if end is None else end
    out, at = [], start
    while True:
        i = mm.find(needle, at, end)
        if i < 0:
            return out
        s = mm.rfind(b"\n", 0, i) + 1
        e = mm.find(b"\n", i)
        e = len(mm) if e < 0 else e
        out.append((s, e))
        at = e + 1


def _row(mm, span):
    """The row on a line, None for a request record or no row."""
    line = mm[span[0]:span[1]]
    if line.startswith(jobs.REQUEST_RECORD):
        return None
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) and _str(row.get("uuid")) else None


def _stamp(mm, start):
    """(the time of the row on the line starting at `start`, its own top-level `timestamp` — a row's message,
    written before it, may hold older ones — or None for a request record or a line with none; the next line's
    start)."""
    end = mm.find(b"\n", start)
    end = len(mm) if end < 0 else end
    row = _row(mm, (start, end))
    return (_epoch(row.get("timestamp")) if row else None), end + 1


def offset_since(mm, t):
    """The start of a line at or before the first row written at `t` or later, by bisection on the rows'
    timestamps (to within a megabyte); 0 when they cannot tell."""
    lo, hi = 0, len(mm)
    while hi - lo > 1 << 20:
        mid = (lo + hi) // 2
        start = mm.rfind(b"\n", 0, mid) + 1
        if start <= lo:
            break
        stamp, nxt = None, start
        for _ in range(16):
            if nxt >= len(mm):
                break
            stamp, nxt = _stamp(mm, nxt)
            if stamp is not None:
                break
        if stamp is None:
            break
        if stamp < t:
            lo = start
        else:
            hi = start
    return lo


class LoopStops:
    """What a loop's transcript says it stopped: its TaskStop calls that succeeded ({task id: [the call's time]}),
    the bridge's stop notes ({task id: time}), and the engine's queue records enqueuing notices (`queued`, a jobs
    ledger of them alone), read back from the end only as far as asked (`reach`), each stretch once."""

    def __init__(self, path):
        self.path, self.reached, self.offset = path, None, None
        self.stops, self.notes, self.queued, self.unreadable = {}, {}, jobs.Ledger(), False

    def reach(self, t):
        """Read back to rows written at `t` (less EVIDENCE_MARGIN), from where an earlier reach stopped."""
        if self.unreadable or (self.reached is not None and t >= self.reached):
            return self
        mm = _open_map(self.path) if self.path else None
        if mm is None:
            self.unreadable = bool(self.path) and not (os.path.isfile(self.path) and os.path.getsize(self.path) == 0)
            self.reached = float("-inf")
            return self
        try:
            start = offset_since(mm, t - EVIDENCE_MARGIN) if t > float("-inf") else 0
            end = len(mm) if self.offset is None else self.offset
            if start < end:
                self._read(mm, start, end)
            self.offset, self.reached = min(start, end), t
        finally:
            mm.close()
        return self

    def _read(self, mm, start, end):
        for span in _lines_holding(mm, TASKSTOP_CALL, start, end):
            row = _row(mm, span)
            msg = row.get("message") if row else None
            for b in msg.get("content") or () if isinstance(msg, dict) and isinstance(msg.get("content"), list) else ():
                if not (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "TaskStop"
                        and isinstance(b.get("input"), dict) and _str(b["input"].get("task_id")) and _str(b.get("id"))):
                    continue
                if self._succeeded(mm, b["id"], span[1]):
                    self.stops.setdefault(b["input"]["task_id"], []).append(_epoch(row.get("timestamp")))
        for phrase in STOP_NOTE_PHRASES:
            for span in _lines_holding(mm, phrase, start, end):
                row = _row(mm, span)
                if row is None:
                    continue
                msg = row.get("message")
                for task, _line in jobs._stop_records(row, msg.get("content") if isinstance(msg, dict) else None):
                    self.notes[task] = _epoch(row.get("timestamp"))
        for span in _lines_holding(mm, QUEUE_RECORD, start, end):
            line = mm[span[0]:span[1]]
            if NOTICE_OPEN not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and jobs.queued_notice(rec) is not None:
                # Stretches are read newest first, so not in file order: only whether a task ended is asked of
                # them, which no order changes (a terminal word is replaced only by another).
                self.queued.add(rec)

    @staticmethod
    def _succeeded(mm, call, after):
        """Whether the call's result, written after it, is no error: the first row after it naming the call as a
        result, however far (a request record, which repeats the conversation, or any other line between is
        passed over unparsed). False while no result is written yet."""
        needle = ('"tool_use_id":"%s"' % call).encode()
        at = after
        while True:
            i = mm.find(needle, at)
            if i < 0:
                return False
            s = mm.rfind(b"\n", 0, i) + 1
            e = mm.find(b"\n", i)
            e = len(mm) if e < 0 else e
            row = _row(mm, (s, e))
            msg = row.get("message") if row else None
            for b in msg.get("content") or () if isinstance(msg, dict) and isinstance(msg.get("content"), list) else ():
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") == call:
                    return b.get("is_error") is not True
            at = e + 1

    def ended(self, task, monitor=False):
        """Whether this loop's rows (as far as read) stop the task, or hold the engine's queued notice that it ended
        (a monitor's expiry counting for a task the asking loop holds as a monitor)."""
        if task in self.notes or task in self.stops:
            return True
        o = self.queued.outcome(task, monitor)
        return o is not None and o["status"] != "running"


def read_tail(path, opener=False):
    """What the end of an agent's transcript says of its turn: {last, closed, failed, at, inflight, openedAt}.
    `last` whether any conversation row was found; `at` the time of the last one; `inflight` the calls of the
    turn's last reply with no result yet, [{name, at}]; with `opener`, for an open turn, `openedAt`, when the turn
    began (the first row after the last row that closed one, or the transcript's first row). None when the file
    cannot be read."""
    mm = _open_map(path)
    if mm is None:
        return None
    try:
        out = {"last": False, "closed": False, "failed": False, "at": None, "inflight": [], "openedAt": None}
        answered, reply, earliest, walked = set(), None, None, 0
        for row, size in _rows_back(mm):
            msg = _message(row)
            if msg is None:
                continue
            at = _epoch(row.get("timestamp"))
            if not out["last"]:
                out.update(last=True, at=at, closed=_closes(row, msg), failed=row.get("isApiErrorMessage") is True)
                if out["closed"]:
                    return out
            elif _closes(row, msg):
                out["openedAt"] = earliest
                return out
            content = msg.get("content") if isinstance(msg.get("content"), list) else []
            if row["type"] == "user":
                answered |= {b.get("tool_use_id") for b in content
                             if isinstance(b, dict) and b.get("type") == "tool_result"}
            elif reply is None or msg.get("id") == reply:
                # The turn's last reply, which the engine writes a block a row: its calls without a result run.
                reply = msg.get("id") or row["uuid"]
                for b in reversed(content):
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in answered:
                        out["inflight"].insert(0, {"name": str(b.get("name") or "?"), "at": at})
            elif not opener:
                return out
            earliest = at if at is not None else earliest
            walked += size
            if walked > OPENER_BYTES:
                if opener:
                    mm.seek(0)
                    out["openedAt"] = _first_stamp(iter(mm.readline, b""))
                return out
        out["openedAt"] = earliest
        return out
    finally:
        mm.close()


def live_background(path, main=None):
    """The background shells and monitors this loop started that the rows do not end, [{taskId, kind,
    description, command, startedAt}]: each start found by its id, then every row of the loop's naming that task
    read through the desk's ledger (sminos_jobs.task_rows); a task they leave running is then asked of `main` (a
    LoopStops of the main loop), whose TaskStops, bridge stop notes and queued notices end it with no
    notification in this loop's rows."""
    mm = _open_map(path)
    if mm is None:
        return []
    try:
        tasks = sorted({m.group(1).decode() for m in TASK_START.finditer(mm)})
    finally:
        mm.close()
    out = []
    for task in tasks:
        ledger = jobs.Ledger()
        ledger.feed(jobs.task_rows(path, task))
        for j in ledger.jobs_body(True):
            if j["taskId"] != task or j["status"] != "running":
                continue
            if main is not None and main.ended(task, j["kind"] == "monitor"):
                continue
            out.append({"taskId": task, "kind": j["kind"], "description": j["description"],
                        "command": j.get("command"), "startedAt": j["startedAt"]})
    return out


def _stat(path):
    try:
        return os.stat(path)
    except OSError:
        return None


def _born(st):
    """When a file was created where the filesystem says (macOS), else when it was last written."""
    return getattr(st, "st_birthtime", None) or st.st_mtime


def _ident(st):
    """A file's identity as the kept states key it, or None for no file."""
    return None if st is None else [st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


class Memo:
    """The ended states of one session's agents, kept at `path` ({version, agents: {id: {key, state, kids?}}}):
    loaded when first asked, written whole (temp file and rename, 0600) by `save` when an entry changed."""

    def __init__(self, path):
        self.path, self.entries, self.loaded, self.changed = path, {}, False, False

    def _load(self):
        if self.loaded:
            return
        self.loaded = True
        try:
            with open(self.path, "rb") as f:
                d = json.loads(f.read())
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            d = None
        if isinstance(d, dict) and d.get("version") == MEMO_VERSION and isinstance(d.get("agents"), dict):
            self.entries = d["agents"]
        else:
            self.changed = True   # rewritten at the save, whatever it held

    def get(self, agent_id, key):
        """(state, kids) kept under this key — `kids` that it holds only while no child is live — or None."""
        self._load()
        e = self.entries.get(agent_id)
        s = e.get("state") if isinstance(e, dict) and e.get("key") == key else None
        if not (isinstance(s, dict) and s.get("state") in ENDED and s.get("source") == "disk" and "since" in s
                and set(s) <= {"state", "source", "since", "stoppedBy"}):
            return None
        since, by = s["since"], s.get("stoppedBy", "")
        if since is not None and (isinstance(since, bool) or not isinstance(since, (int, float))) \
                or not isinstance(by, str):
            return None
        return dict(s), e.get("kids") is True

    def put(self, agent_id, key, state, kids):
        self._load()
        entry = {"key": key, "state": dict(state), **({"kids": True} if kids else {})}
        if self.entries.get(agent_id) != entry:
            self.entries[agent_id], self.changed = entry, True

    def drop(self, agent_id):
        self._load()
        if self.entries.pop(agent_id, None) is not None:
            self.changed = True

    def save(self, agents):
        """Write the entries of `agents` (the agents the view holds) when any changed; a write that fails leaves the
        file to the next view."""
        if not self.loaded or not (self.changed or set(self.entries) - set(agents)):
            return
        entries = {i: e for i, e in self.entries.items() if i in agents}
        d, tmp = os.path.dirname(self.path), None
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
            with os.fdopen(fd, "w") as f:
                json.dump({"version": MEMO_VERSION, "agents": entries}, f, separators=(",", ":"))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            tmp = None
        except OSError:
            return
        finally:
            if tmp is not None and os.path.exists(tmp):
                os.unlink(tmp)
        self.entries, self.changed = entries, False


def read_meta(path):
    """An agent's meta, or None when it cannot be read or is no object."""
    try:
        with open(path) as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


class Subagents:
    """One session's subagents. `main` the session's transcript; `live` whether its process runs, `started` (epoch
    seconds) when that process started; `bridge` the bridge's agents (GET /agents), or None when no bridge
    answered; `stall` seconds; `notes` what the caller already has to say. States are derived on demand and kept:
    `counts` and `tree(every=True)` read every agent, `done` only the newest, and the default view (`active_counts`,
    `tree`, `recent`, `done_count`) only those that are not past (`past`), whose metas alone are read at the start.
    `notes` says what could not be read, and so what may be missing or inferred. `cache` the file the session's
    ended states are kept in (Memo), None to keep none; `keep` writes it."""

    def __init__(self, main, *, live, started=None, bridge=None, stall=STALL_SECONDS, now=None, notes=(),
                 cache=None):
        self.main, self.live, self.started, self.stall = main, live, started, stall
        self.memo = Memo(cache) if cache else None
        self.engine_answered = bridge is not None
        self.now = time.time() if now is None else now
        self.held = {str(b["agentId"]): b for b in bridge or () if isinstance(b, dict) and b.get("agentId")}
        self.dir = main[:-len(".jsonl")] + "/subagents" if main.endswith(".jsonl") else None
        self.agents, self.states, self.loops, self.tails = {}, {}, {}, {}
        self._given, self._dir_notes, self._later = list(notes), [], []
        self._read_dir()
        for agent_id, b in self.held.items():
            # An agent the bridge knows only by a SubagentStop, never spawned and with no file, is the engine's own
            # (a hook's or a classifier's agent, its type empty): no subagent of the session's.
            if agent_id not in self.agents and (_str(b.get("subagentType")) or _str(b.get("description"))):
                self.agents[agent_id] = {"agentId": agent_id, "meta": {}, "born": None, "metaAt": None,
                                         "path": None, "at": None, "past": self._past(agent_id, ())}
        # Who may hold a parent waiting: a past child is never live, so only the others are its children here.
        self.children = {}
        for a in self.agents.values():
            if not a["past"]:
                self.children.setdefault(self.parent(a), []).append(a["agentId"])

    def _read_dir(self):
        """The agents the session's directory holds: its own subagents', and each workflow's
        (`workflows/<run>/`)."""
        if self.dir is None:
            return
        self._read_agents(self.dir, None)
        try:
            runs = sorted(n for n in os.listdir(os.path.join(self.dir, "workflows")) if not n.startswith("."))
        except OSError:
            runs = []
        for run in runs:
            self._read_agents(os.path.join(self.dir, "workflows", run), run)

    def _read_agents(self, d, workflow):
        """The agents a directory holds, from its listing and each file's stats; the meta read now unless the agent
        is past (read when first asked: `meta`)."""
        try:
            names = os.listdir(d)
        except FileNotFoundError:
            return   # no subagent ever wrote here
        except OSError as e:
            self._dir_notes.append("%s could not be read (%s): none of its agents are listed" % (d, e.strerror or e))
            return
        metas = {n[len("agent-"):-len(".meta.json")] for n in names
                 if n.startswith("agent-") and n.endswith(".meta.json")}
        transcripts = {n[len("agent-"):-len(".jsonl")] for n in names if n.startswith("agent-") and n.endswith(".jsonl")}
        for agent_id in sorted(metas | transcripts):
            meta_path = os.path.join(d, "agent-%s.meta.json" % agent_id)
            st = _stat(meta_path)
            transcript = os.path.join(d, "agent-%s.jsonl" % agent_id)
            tst = _stat(transcript) if agent_id in transcripts else None
            first = st if st is not None else tst
            if first is None:
                continue
            a = {"agentId": agent_id, "meta": None if agent_id in metas else {}, "metaPath": meta_path,
                 "born": _born(first), "metaAt": st.st_mtime if st is not None else None,
                 "path": transcript if tst else None, "at": tst.st_mtime if tst else None,
                 "metaUnread": False, "workflow": workflow, "ids": [_ident(tst), _ident(st)]}
            a["past"] = self._past(agent_id, (a["at"], a["metaAt"], a["born"]))
            self.agents[agent_id] = a
            if not a["past"]:
                self.meta(a)

    def meta(self, a):
        """The agent's meta ({} when it has none or it cannot be read, `metaUnread` then saying so), read once."""
        if a["meta"] is None:
            meta = read_meta(a["metaPath"])
            a["meta"], a["metaUnread"] = meta or {}, meta is None
        return a["meta"]

    @property
    def notes(self):
        """What could not be read: the caller's notes, the directories', the metas read so far, the loops'."""
        unreadable = [i for i, a in self.agents.items() if a.get("metaUnread")]
        out = self._given + self._dir_notes
        if unreadable:
            one = len(unreadable) == 1
            out.append("%d agent meta file%s could not be read (%s): %s listed from %s transcript alone, "
                       "with no type, description, parent or worktree" % (
                           len(unreadable), "" if one else "s",
                           ", ".join(unreadable[:5]) + (", …" if len(unreadable) > 5 else ""),
                           "it is" if one else "they are", "its" if one else "each one's"))
        return out + self._later

    def _past(self, agent_id, writes):
        """Whether the agent is past: the engine holds no word on it (or no bridge answered) and the running process
        wrote none of its files (`writes`, their times), or the session runs no process. By the doctrine such an
        agent is ended or orphaned, never running or waiting, so the default view counts it unread."""
        if not self.live:
            return True
        if agent_id in self.held or self.started is None:
            return False
        return all(t is None or t < self.started for t in writes)

    # -- facts
    def parent(self, a):
        p = _str(self.meta(a).get("parentAgentId")) or _str((self.held.get(a["agentId"]) or {}).get("parentAgentId"))
        return p if p in self.agents and p != a["agentId"] else None

    def _current(self, at):
        """Whether a write at `at` was the running process's."""
        return self.live and at is not None and (self.started is None or at >= self.started)

    def _loop_path(self, parent_id):
        return self.main if parent_id is None else self.agents[parent_id]["path"]

    def tail(self, a):
        """The agent's transcript tail (read_tail), read once, an open turn back to where it began."""
        if a["agentId"] not in self.tails:
            self.tails[a["agentId"]] = read_tail(a["path"], opener=True) if a["path"] else None
        return self.tails[a["agentId"]]

    def loop_stops(self, parent, since):
        """The stops the loop that ran `parent`'s agents (the main loop's for None) made, read back to `since`."""
        if parent not in self.loops:
            self.loops[parent] = LoopStops(self._loop_path(parent))
        stops = self.loops[parent].reach(since)
        if stops.unreadable:
            self._later.append("the transcript of %s could not be read: an agent or task it stopped may read as "
                              "orphaned, running or waiting" % ("the main loop" if parent is None else parent))
            stops.unreadable = None   # said once
        return stops

    def parent_stop(self, a, tail):
        """When the loop that ran this agent stopped it with TaskStop since its open turn began, or None."""
        if a.get("workflow"):
            return None
        # The open turn began at its first row after the last that closed one; a TaskStop closes nothing, so after a
        # stop and a revival that row may be an earlier revival's, and only the latest revival bounds the turn.
        revived = self.meta(a).get("revivedAt")
        since = max(tail.get("openedAt") or a["born"] or 0,
                    revived / 1000.0 if isinstance(revived, (int, float)) and not isinstance(revived, bool) else 0)
        stops = self.loop_stops(self.parent(a), since)
        made = [t for t in stops.stops.get(a["agentId"], ()) if t is not None and t >= since - 1]
        return max(made) if made else None

    def state(self, agent_id):
        """{state, source, since, stoppedBy?, tool?, quiet?, background?, waitingOn?} for one agent."""
        if agent_id not in self.states:
            self.states[agent_id] = None   # a cycle in the parents reads as no live child
            self.states[agent_id] = self._derive(self.agents[agent_id])
        return self.states[agent_id] or {"state": "completed", "source": "disk", "since": None}

    def _live_kids(self, a):
        return [k for k in self.children.get(a["agentId"], ()) if self.state(k)["state"] in ACTIVE]

    def _waiting(self, a, since, source):
        """Waiting on background when a task this loop started, or a background child agent, still runs."""
        main = self.loop_stops(None, self.started or 0) if self.main else None
        tasks = live_background(a["path"], main) if a["path"] else []
        kids = self._live_kids(a)
        if tasks or kids:
            return {"state": "waiting", "source": source, "since": since, "background": tasks, "waitingOn": kids}
        return None

    def _derive(self, a):
        held = self.held.get(a["agentId"])
        if held is not None and self.live and not self._revived(a, held):
            return self._engine(a, held)
        if self.memo is None:
            return self._disk(a)
        # The kept state where the disk decides (the module's doctrine says what the key holds, and why).
        current = self._current(a["at"])
        key = [a["path"], a.get("metaPath"), *(a.get("ids") or (None, None)), self.parent(a), current,
               self.started if current else None]
        kept = self.memo.get(a["agentId"], key)
        if kept is not None and not (kept[1] and self._live_kids(a)):
            return kept[0]
        out = self._disk(a)
        if out["state"] in ENDED:
            # A completed closed turn of the running process was asked whether its children run.
            self.memo.put(a["agentId"], key, out, kids=out["state"] == "completed" and current)
        else:
            self.memo.drop(a["agentId"])
        return out

    def _disk(self, a):
        """The agent's state as its files, and its loops', say it."""
        meta = self.meta(a)
        if a["path"] is None:
            if meta.get("finished") is True:
                return {"state": "completed", "source": "disk", "since": a["metaAt"]}
            if self._current(a["born"]):
                return {"state": "running", "source": "disk", "since": a["born"]}
            return {"state": "orphaned", "source": "disk", "since": a["metaAt"]}
        current = self._current(a["at"])
        revived = isinstance(meta.get("revivedAt"), (int, float)) and a["at"] * 1000 >= meta["revivedAt"]
        by_user = meta.get("stoppedByUser") is True and not revived
        if by_user and not current:
            return {"state": "stopped", "source": "disk", "since": a["at"], "stoppedBy": "user"}
        tail = self.tail(a)
        if tail is None or not tail["last"]:
            if current:
                return {"state": "running", "source": "disk", "since": a["born"]}
            if meta.get("finished") is True:   # no row the transcript holds says otherwise
                return {"state": "completed", "source": "disk", "since": a["at"]}
            return {"state": "orphaned", "source": "disk", "since": a["at"]}
        if tail["failed"]:
            return {"state": "failed", "source": "disk", "since": tail["at"] or a["at"]}
        if tail["closed"]:
            if by_user:
                return {"state": "stopped", "source": "disk", "since": a["at"], "stoppedBy": "user"}
            if current:
                waiting = self._waiting(a, tail["at"], "disk")
                if waiting:
                    return waiting
            return {"state": "completed", "source": "disk", "since": a["at"]}
        if by_user:
            return {"state": "stopped", "source": "disk", "since": a["at"], "stoppedBy": "user"}
        stopped = self.parent_stop(a, tail)
        if stopped is not None:
            return {"state": "stopped", "source": "disk", "since": stopped, "stoppedBy": "TaskStop"}
        if not current:
            return {"state": "orphaned", "source": "disk", "since": a["at"]}
        return self._open(a, tail, "disk")

    def _open(self, a, tail, source):
        """An open turn of the running process: running, its activity beside it; stalled only when nothing but the
        disk speaks for it."""
        since = (tail or {}).get("openedAt") or a["born"]
        quiet = None if a["at"] is None else self.now - a["at"]
        if tail and tail["inflight"]:
            return {"state": "running", "source": source, "since": since, "tool": tail["inflight"][-1]}
        if source == "disk" and quiet is not None and quiet > self.stall:
            return {"state": "stalled", "source": source, "since": a["at"]}
        out = {"state": "running", "source": source, "since": since}
        if quiet is not None and quiet >= QUIET_SECONDS:
            out["quiet"] = a["at"]
        return out

    def _revived(self, a, held):
        """Whether the engine's word that an agent ended is older than the turn its rows hold open: a SendMessage
        revived it (`revivedAt`) and wrote since, and the bridge, which learns an agent's end but no revival (nor
        keeps when it learned the end, past a resync), still holds the end. The rows decide then."""
        revived = self.meta(a).get("revivedAt")
        if held.get("running") is not False or not isinstance(revived, (int, float)) or a["at"] is None \
                or a["at"] * 1000 < revived:
            return False
        tail = self.tail(a)
        return bool(tail and tail["last"] and not tail["closed"])

    def _engine(self, a, held):
        """The engine's word first: alive runs (or waits on its background work once its turn closed); ended is
        how the list said it ended, else as its rows say."""
        tail = self.tail(a)
        word = _str(held.get("status"))
        if held.get("running") is True:
            if tail and tail["last"] and tail["closed"]:
                waiting = self._waiting(a, tail["at"], "engine")
                if waiting:
                    return waiting
            return self._open(a, tail, "engine")
        since = a["at"] or a["metaAt"]
        if word in ENGINE_ENDED:
            state = ENGINE_ENDED[word]
            if state == "completed":
                waiting = self._waiting(a, (tail or {}).get("at") or since, "engine")
                if waiting:
                    return waiting
            out = {"state": state, "source": "engine", "since": since}
            if state == "stopped":
                out["stoppedBy"] = "user" if self.meta(a).get("stoppedByUser") is True else "killed"
            return out
        # Ended with no word (SubagentStop, or it left the list): its rows say how.
        if tail and tail["failed"]:
            return {"state": "failed", "source": "engine", "since": tail["at"] or since}
        if tail and tail["closed"]:
            waiting = self._waiting(a, tail["at"], "engine")
            return waiting or {"state": "completed", "source": "engine", "since": since}
        if tail is None or not tail["last"]:
            finished = self.meta(a).get("finished")
            return {"state": "completed" if finished else "stopped", "source": "engine",
                    "since": since, **({} if finished else {"stoppedBy": "killed"})}
        return {"state": "stopped", "source": "engine", "since": since,
                "stoppedBy": "user" if self.meta(a).get("stoppedByUser") is True else "killed"}

    # -- views
    def entry(self, agent_id, depth=0):
        """An agent as the view carries it (list --subagents --json)."""
        a = self.agents[agent_id]
        meta, held = self.meta(a), self.held.get(agent_id) or {}
        s = self.state(agent_id)

        def age(t):
            return None if t is None else max(0, int(self.now - t))

        e = {"agentId": agent_id, "parentAgentId": self.parent(a), "depth": depth,
             "type": _str(meta.get("agentType")) or _str(held.get("subagentType")) or "?",
             "model": _str(meta.get("model")) or _str(held.get("model")), "effort": _str(meta.get("effort")),
             "description": _str(meta.get("description")) or _str(held.get("description")) or "",
             "name": _str(held.get("name")), "state": s["state"], "source": s["source"],
             "engineStatus": _str(held.get("status")) if held else None,
             "since": _iso(s["since"]), "seconds": age(s["since"]), "stoppedBy": s.get("stoppedBy"),
             "tool": None, "quietSeconds": age(s.get("quiet")) if s.get("quiet") is not None else None,
             "background": s.get("background", []), "waitingOn": s.get("waitingOn", []),
             "worktree": _str(meta.get("worktreePath")), "inheritedWorktree": _str(meta.get("inheritedWorktreePath")),
             "lastWrite": _iso(a["at"]), "revived": _iso(meta["revivedAt"] / 1000)
             if isinstance(meta.get("revivedAt"), (int, float)) else None}
        if a.get("metaUnread"):
            e["metaUnread"] = True
        if a.get("workflow"):
            e["workflow"] = a["workflow"]
        if s.get("tool"):
            t = s["tool"]
            e["tool"] = {"name": t["name"], "since": _iso(t["at"]), "seconds": age(t["at"])}
        return e

    def spawned(self, a):
        """When the agent was spawned: its transcript's first row's time (the prompt it was given), the same on
        every filesystem; else when its meta file was made (macOS) or last written."""
        if "spawned" not in a:
            stamp = None
            if a["path"]:
                try:
                    with open(a["path"], "rb") as f:   # its head alone: a read, cheaper than a map
                        stamp = _first_stamp(f)
                except OSError:
                    pass
            a["spawned"] = stamp or a["born"] or 0
        return a["spawned"]

    def _spawn_order(self, ids):
        return sorted(ids, key=lambda i: (self.spawned(self.agents[i]), i))

    def tree(self, every=False, depth=None):
        """The agents in spawn order nested under their parents, [entry]; without `every` only the live ones —
        running, waiting, stalled — each under its nearest live ancestor, a past agent never derived. With `depth`,
        only that many levels: a row whose shown descendants are cut off carries them as `folded` {count, states}."""
        shown = {i for i, a in self.agents.items() if every or not a["past"] and self.state(i)["state"] in ACTIVE}

        def anchor(i):
            p, seen = self.parent(self.agents[i]), set()
            while p is not None and p not in shown and p not in seen:
                seen.add(p)
                p = self.parent(self.agents[p])
            return p if p in shown else None

        under = {}
        for i in self._spawn_order(shown):
            under.setdefault(anchor(i), []).append(i)
        out = []

        def below(i):
            for k in under.get(i, ()):
                yield k
                yield from below(k)

        def walk(parent, level):
            for i in under.get(parent, ()):
                e = self.entry(i, level)
                out.append(e)
                if depth is not None and level + 1 >= depth:
                    cut = list(below(i))
                    if cut:
                        states = {}
                        for k in cut:
                            states[self.state(k)["state"]] = states.get(self.state(k)["state"], 0) + 1
                        e["folded"] = {"count": len(cut), "states": states}
                    continue
                walk(i, level + 1)

        walk(None, 0)
        return out

    def live_summary(self):
        """The cheap count `sminos list` shows: {source, running} — the agents the engine holds as running, where
        the bridge answered; else, from the disk, {source, open}: those of the running process whose turn its
        transcript leaves open (running, or stalled: telling them apart, or a closed turn waiting on background
        work, takes the deep reads this leaves to `tree`)."""
        if self.engine_answered and self.live:
            return {"source": "engine", "running": sum(1 for i, b in self.held.items()
                                                       if b.get("running") is True and i in self.agents)}
        n = 0
        for a in self.agents.values():
            if a["path"] and self._current(a["at"]) and self.meta(a).get("stoppedByUser") is not True:
                t = self.tail(a)
                n += bool(t and t["last"] and not t["closed"] and not t["failed"])
        return {"source": "disk", "open": n}

    def counts(self):
        """{state: how many agents are in it}, every state named, every depth counted."""
        c = dict.fromkeys(WORDS, 0)
        for i in self.agents:
            c[self.state(i)["state"]] += 1
        return c

    # -- the default view: the live ones and those ended in the last minutes, every other one counted unread
    def active_counts(self):
        """{running, waiting, stalled}: how many agents are live, every depth counted, a past agent never derived."""
        c = dict.fromkeys(ACTIVE, 0)
        for i, a in self.agents.items():
            if not a["past"] and self.state(i)["state"] in ACTIVE:
                c[self.state(i)["state"]] += 1
        return c

    def recent(self, seconds=RECENT_SECONDS, cap=RECENT_CAP):
        """The agents that ended in the last `seconds`, newest first, at most `cap`, [entry]: of those that are not
        past (a past agent ended before the running process started)."""
        ended = [(self.state(i)["since"], i) for i, a in self.agents.items()
                 if not a["past"] and self.state(i)["state"] in ENDED and self.state(i)["since"] is not None
                 and self.now - self.state(i)["since"] <= seconds]
        return [self.entry(i) for _since, i in sorted(ended, key=lambda x: (-x[0], x[1]))[:cap]]

    def keep(self):
        """Write the session's kept ended states (`cache`) when they changed."""
        if self.memo is not None:
            self.memo.save(self.agents)

    def done_count(self, recent=None):
        """How many agents the default view does not list (neither live nor among `recent`, the `recent()` it
        shows): ended or orphaned, now or in an earlier process."""
        shown = self.recent() if recent is None else recent
        return len(self.agents) - sum(self.active_counts().values()) - len(shown)

    def done(self, n):
        """The `n` agents ended last, newest first, [entry]: read newest written first, stopping at `n`."""
        out = []
        for i in sorted(self.agents, key=lambda i: -(self.agents[i]["at"] or self.agents[i]["metaAt"] or 0)):
            if len(out) >= n:
                break
            if self.state(i)["state"] in ENDED:
                out.append(self.entry(i))
        return out


# -- text
def short_age(seconds):
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return "%d%s" % (seconds // size, unit)
    return "%ds" % seconds


def _home(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path and home != "/" and path.startswith(home + "/") else path


def _cut(text, width):
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1] + "…"


def counts_line(c):
    return "[%d running · %d waiting on background · %d stalled · %d orphaned]" % (
        c["running"], c["waiting"], c["stalled"], c["orphaned"])


def active_line(c):
    """The default view's header: `[2 running · 1 waiting on background]`, `· 1 stalled` added when one is."""
    return "[%d running · %d waiting on background%s]" % (
        c["running"], c["waiting"], " · %d stalled" % c["stalled"] if c["stalled"] else "")


def done_line(n):
    """`+1118 done (on disk)`: every agent the default view does not list."""
    return "+%d done (on disk)" % n


def ended_text(e):
    """A recently ended agent's outcome and how long ago: `completed 3m ago`, `stopped 30s ago · by TaskStop`."""
    return WORDS[e["state"]] + " " + short_age(e["seconds"]) + " ago" + (" · by " + e["stoppedBy"]
                                                                          if e["stoppedBy"] else "")


def state_text(e):
    """The lifecycle, how long, and where it came from; then what the agent is doing:
    `running 14m (engine) · in Bash 3m`, `running 40m (engine) · no write 14m`, `waiting on background 5m (disk)`,
    `stopped 2h (disk) · by TaskStop`. The background jobs a wait is on are left to --json."""
    out = WORDS[e["state"]] + ("" if e["seconds"] is None else " " + short_age(e["seconds"])) + " (%s)" % e["source"]
    if e["tool"]:
        out += " · in %s%s" % (e["tool"]["name"], "" if e["tool"]["seconds"] is None
                               else " " + short_age(e["tool"]["seconds"]))
    elif e["quietSeconds"] is not None:
        out += " · no write " + short_age(e["quietSeconds"])
    if e["stoppedBy"]:
        out += " · by " + e["stoppedBy"]
    if e.get("folded"):
        f = e["folded"]
        odd = ", ".join("%d %s" % (n, WORDS[s]) for s, n in sorted(f["states"].items()) if s != "running")
        out += " · +%d below%s" % (f["count"], " (%s)" % odd if odd else "")
    return out


def _type_text(e):
    extra = ", ".join(x for x in (e["model"], e["effort"]) if x)
    return e["type"] + (" (%s)" % extra if extra else "")


def tree_lines(entries, ended=()):
    """The tree's rows, columns aligned: the id (indented by depth; the engine's name for it beside it), type and
    model, description, lifecycle and activity, its own worktree; then the `ended` (recent), each with how long ago
    it ended, in the same columns."""
    rows = []
    for e in entries:
        label = "  " * e["depth"] + e["agentId"] + (" (%s)" % e["name"] if e["name"] else "")
        rows.append([label, _type_text(e), _cut(e["description"], DESCRIPTION_WIDTH), state_text(e),
                     "wt " + _home(e["worktree"]) if e["worktree"] else ""])
    for e in ended:
        rows.append([e["agentId"] + (" (%s)" % e["name"] if e["name"] else ""), _type_text(e),
                     _cut(e["description"], DESCRIPTION_WIDTH), ended_text(e),
                     "wt " + _home(e["worktree"]) if e["worktree"] else ""])
    return _aligned(rows)


def done_lines(entries):
    """The --done rows: when it ended (local time), the id, type, description, and its outcome."""
    rows = []
    for e in entries:
        at = _epoch(e["since"]) if e["since"] else None
        when = time.strftime("%m-%d %H:%M", time.localtime(at)) if at is not None else "?"
        outcome = e["state"] + (" by " + e["stoppedBy"] if e["stoppedBy"] else "")
        rows.append([when, e["agentId"], _type_text(e), _cut(e["description"], DESCRIPTION_WIDTH), outcome])
    return _aligned(rows)


def _aligned(rows):
    if not rows:
        return []
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]) - 1)]
    return [("  " + "  ".join([c.ljust(w) for c, w in zip(r, widths) if w] + [r[-1]])).rstrip() for r in rows]
