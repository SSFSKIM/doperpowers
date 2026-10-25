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
TaskStops back to the earliest open turn asking, its stop notes back to
the running process's start; each byte at most once a view.

Lifecycle: running, waiting (on background), stalled (disk only: open,
nothing in flight, no write for `stall` seconds), orphaned, and the ended
ones: completed, failed, stopped (by the user, by TaskStop, or killed).
"""

import datetime
import json
import mmap
import os
import re
import time

import sminos_jobs as jobs

STALL_SECONDS = 600
QUIET_SECONDS = 60   # an agent with nothing in flight and no write for this long says so (`no write 3m`)
# A loop's transcript is read from this long before the time asked: rows are written about in time order, not
# exactly (a row's own timestamp is its start).
EVIDENCE_MARGIN = 120.0
# The bridge's notes that it stopped a task (sminos_jobs.STOP_NOTE, INTERRUPT_ORIGINS), found by these phrases.
STOP_NOTE_PHRASES = (b"a background task, was stopped from", b"The interrupt came from")
TASKSTOP_CALL = b'"name":"TaskStop"'
LIVE = ("running", "waiting", "stalled", "orphaned")
ENDED = ("completed", "failed", "stopped")
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


def _first_stamp(mm):
    """The time of the transcript's first row that carries one."""
    start = 0
    while start < len(mm):
        end = mm.find(b"\n", start)
        end = len(mm) if end < 0 else end
        try:
            row = json.loads(mm[start:end])
        except ValueError:
            row = None
        if isinstance(row, dict) and _epoch(row.get("timestamp")) is not None:
            return _epoch(row["timestamp"])
        start = end + 1
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
    and the bridge's stop notes ({task id: time}), read back from the end only as far as asked (`reach`), each
    stretch once."""

    def __init__(self, path):
        self.path, self.reached, self.offset = path, None, None
        self.stops, self.notes, self.unreadable = {}, {}, False

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

    def ended(self, task):
        """Whether this loop's rows (as far as read) stop the task."""
        return task in self.notes or task in self.stops


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
                    out["openedAt"] = _first_stamp(mm)
                return out
        out["openedAt"] = earliest
        return out
    finally:
        mm.close()


def live_background(path, main=None):
    """The background shells and monitors this loop started that the rows do not end, [{taskId, kind,
    description, command, startedAt}]: each start found by its id, then every row of the loop's naming that task
    read through the desk's ledger (sminos_jobs.task_rows); a task they leave running is then asked of `main` (a
    LoopStops of the main loop), whose TaskStops and bridge stop notes end it with no notification."""
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
        if not any(j["taskId"] == task and j["status"] == "running" for j in ledger.jobs_body(True)):
            continue
        if main is not None and main.ended(task):
            continue
        for j in ledger.jobs_body(True):
            if j["taskId"] == task and j["status"] == "running":
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


class Subagents:
    """One session's subagents. `main` the session's transcript; `live` whether its process runs, `started` (epoch
    seconds) when that process started; `bridge` the bridge's agents (GET /agents), or None when no bridge
    answered; `stall` seconds. States are derived on demand and kept: `tree` reads every agent, `done` only the
    newest. `notes` says what could not be read, and so what may be missing or inferred."""

    def __init__(self, main, *, live, started=None, bridge=None, stall=STALL_SECONDS, now=None):
        self.main, self.live, self.started, self.stall = main, live, started, stall
        self.engine_answered = bridge is not None
        self.now = time.time() if now is None else now
        self.held = {str(b["agentId"]): b for b in bridge or () if isinstance(b, dict) and b.get("agentId")}
        self.dir = main[:-len(".jsonl")] + "/subagents" if main.endswith(".jsonl") else None
        self.agents, self.states, self.notes, self.loops, self.tails = {}, {}, [], {}, {}
        self._read_dir()
        for agent_id, b in self.held.items():
            # An agent the bridge knows only by a SubagentStop, never spawned and with no file, is the engine's own
            # (a hook's or a classifier's agent, its type empty): no subagent of the session's.
            if agent_id not in self.agents and (_str(b.get("subagentType")) or _str(b.get("description"))):
                self.agents[agent_id] = {"agentId": agent_id, "meta": {}, "born": None, "metaAt": None,
                                         "path": None, "at": None}
        self.children = {}
        for a in self.agents.values():
            self.children.setdefault(self.parent(a), []).append(a["agentId"])

    def _read_dir(self):
        """The agents the session's directory holds: its own subagents', and each workflow's
        (`workflows/<run>/`)."""
        if self.dir is None:
            return
        unreadable = []
        self._read_agents(self.dir, None, unreadable)
        try:
            runs = sorted(n for n in os.listdir(os.path.join(self.dir, "workflows")) if not n.startswith("."))
        except OSError:
            runs = []
        for run in runs:
            self._read_agents(os.path.join(self.dir, "workflows", run), run, unreadable)
        if unreadable:
            one = len(unreadable) == 1
            self.notes.append("%d agent meta file%s could not be read (%s): %s listed from %s transcript alone, "
                              "with no type, description, parent or worktree" % (
                                  len(unreadable), "" if one else "s",
                                  ", ".join(unreadable[:5]) + (", …" if len(unreadable) > 5 else ""),
                                  "it is" if one else "they are", "its" if one else "each one's"))

    def _read_agents(self, d, workflow, unreadable):
        try:
            names = os.listdir(d)
        except FileNotFoundError:
            return   # no subagent ever wrote here
        except OSError as e:
            self.notes.append("%s could not be read (%s): none of its agents are listed" % (d, e.strerror or e))
            return
        metas = {n[len("agent-"):-len(".meta.json")] for n in names
                 if n.startswith("agent-") and n.endswith(".meta.json")}
        transcripts = {n[len("agent-"):-len(".jsonl")] for n in names if n.startswith("agent-") and n.endswith(".jsonl")}
        for agent_id in sorted(metas | transcripts):
            meta_path = os.path.join(d, "agent-%s.meta.json" % agent_id)
            st, meta = _stat(meta_path), None
            if agent_id in metas:
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    meta = None
                if not isinstance(meta, dict):
                    unreadable.append(agent_id)
                    meta = None
            transcript = os.path.join(d, "agent-%s.jsonl" % agent_id)
            tst = _stat(transcript) if agent_id in transcripts else None
            first = st if st is not None else tst
            if first is None:
                continue
            self.agents[agent_id] = {"agentId": agent_id, "meta": meta or {}, "born": _born(first),
                                     "metaAt": st.st_mtime if st is not None else None,
                                     "path": transcript if tst else None, "at": tst.st_mtime if tst else None,
                                     "metaUnread": agent_id in metas and meta is None, "workflow": workflow}

    # -- facts
    def parent(self, a):
        p = _str(a["meta"].get("parentAgentId")) or _str((self.held.get(a["agentId"]) or {}).get("parentAgentId"))
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
            self.notes.append("the transcript of %s could not be read: an agent or task it stopped may read as "
                              "orphaned, running or waiting" % ("the main loop" if parent is None else parent))
            stops.unreadable = None   # said once
        return stops

    def parent_stop(self, a, tail):
        """When the loop that ran this agent stopped it with TaskStop since its open turn began, or None."""
        if a.get("workflow"):
            return None
        # The open turn began at its first row after the last that closed one; a TaskStop closes nothing, so after a
        # stop and a revival that row may be an earlier revival's, and only the latest revival bounds the turn.
        revived = a["meta"].get("revivedAt")
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

    def _waiting(self, a, since, source):
        """Waiting on background when a task this loop started, or a background child agent, still runs."""
        main = self.loop_stops(None, self.started or 0) if self.main else None
        tasks = live_background(a["path"], main) if a["path"] else []
        kids = [k for k in self.children.get(a["agentId"], ()) if self.state(k)["state"] in ("running", "waiting", "stalled")]
        if tasks or kids:
            return {"state": "waiting", "source": source, "since": since, "background": tasks, "waitingOn": kids}
        return None

    def _derive(self, a):
        meta, held = a["meta"], self.held.get(a["agentId"])
        if held is not None and self.live and not self._revived(a, held):
            return self._engine(a, held)
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
        revived = a["meta"].get("revivedAt")
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
                out["stoppedBy"] = "user" if a["meta"].get("stoppedByUser") is True else "killed"
            return out
        # Ended with no word (SubagentStop, or it left the list): its rows say how.
        if tail and tail["failed"]:
            return {"state": "failed", "source": "engine", "since": tail["at"] or since}
        if tail and tail["closed"]:
            waiting = self._waiting(a, tail["at"], "engine")
            return waiting or {"state": "completed", "source": "engine", "since": since}
        if tail is None or not tail["last"]:
            return {"state": "completed" if a["meta"].get("finished") else "stopped", "source": "engine",
                    "since": since, **({} if a["meta"].get("finished") else {"stoppedBy": "killed"})}
        return {"state": "stopped", "source": "engine", "since": since,
                "stoppedBy": "user" if a["meta"].get("stoppedByUser") is True else "killed"}

    # -- views
    def entry(self, agent_id, depth=0):
        """An agent as the view carries it (list --subagents --json)."""
        a = self.agents[agent_id]
        meta, held = a["meta"], self.held.get(agent_id) or {}
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
            mm = _open_map(a["path"]) if a["path"] else None
            try:
                a["spawned"] = (_first_stamp(mm) if mm is not None else None) or a["born"] or 0
            finally:
                if mm is not None:
                    mm.close()
        return a["spawned"]

    def _spawn_order(self, ids):
        return sorted(ids, key=lambda i: (self.spawned(self.agents[i]), i))

    def tree(self, every=False, depth=None):
        """The agents in spawn order nested under their parents, [entry]; without `every` only the live ones (each
        under its nearest live ancestor). With `depth`, only that many levels: a row whose shown descendants are
        cut off carries them as `folded` {count, states}."""
        shown = {i for i in self.agents if every or self.state(i)["state"] in LIVE}

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
            if a["path"] and self._current(a["at"]) and a["meta"].get("stoppedByUser") is not True:
                t = self.tail(a)
                n += bool(t and t["last"] and not t["closed"] and not t["failed"])
        return {"source": "disk", "open": n}

    def counts(self):
        """{state: how many agents are in it}, every state named, every depth counted."""
        c = dict.fromkeys(WORDS, 0)
        for i in self.agents:
            c[self.state(i)["state"]] += 1
        return c

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


def ended_line(c):
    """`+492 ended (480 completed · 2 failed · 10 stopped)`, or "" when none has."""
    n = sum(c[s] for s in ENDED)
    if not n:
        return ""
    return "+%d ended (%s)" % (n, " · ".join("%d %s" % (c[s], s) for s in ENDED if c[s]))


def state_text(e):
    """The lifecycle, how long, and where it came from; then what the agent is doing:
    `running 14m (engine) · in Bash 3m`, `running 40m (engine) · no write 14m`, `waiting on background 5m (disk) ·
    shell: run the tests`, `stopped 2h (disk) · by TaskStop`."""
    out = WORDS[e["state"]] + ("" if e["seconds"] is None else " " + short_age(e["seconds"])) + " (%s)" % e["source"]
    if e["tool"]:
        out += " · in %s%s" % (e["tool"]["name"], "" if e["tool"]["seconds"] is None
                               else " " + short_age(e["tool"]["seconds"]))
    elif e["quietSeconds"] is not None:
        out += " · no write " + short_age(e["quietSeconds"])
    if e["background"]:
        out += " · " + ", ".join("%s: %s" % (b["kind"], _cut(b["description"] or b.get("command") or b["taskId"], 32))
                                 for b in e["background"])
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


def tree_lines(entries):
    """The tree's rows, columns aligned: the id (indented by depth; the engine's name for it beside it), type and
    model, description, lifecycle and activity, its own worktree."""
    rows = []
    for e in entries:
        label = "  " * e["depth"] + e["agentId"] + (" (%s)" % e["name"] if e["name"] else "")
        rows.append([label, _type_text(e), _cut(e["description"], DESCRIPTION_WIDTH), state_text(e),
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
