"""What a session is running, derived from its transcript rows: the desk's DX4
widened `subagents` body ({subagents, jobs, mcp}) and its `output` answer
(the desk composite, DX4 "Jobs and agent status", "Precedence", "`output`";
DC8 M1).

Pure: rows in, facts and bodies out. A `Ledger` takes one loop's rows in file
order and keeps only what the body needs: the calls of Agent/Task, Bash,
Monitor and TaskStop until their results, each status word a row says about a
task (a result, a task-notification, a `task_status`, a TaskStop), the
background shells and monitors, the latest output path the rows named for each
task, and the MCP names. Fed a parent agent's transcript, the same ledger
yields its nested agents' outcomes. `derive` joins a ledger with the metas,
the bridge's agent state, the agent files' facts, the parents' ledgers and
whether the session's process runs; `output_answer` reads a task's output file
under the canonical roots its caller derives. The plane feeds these (M4); the
shared vectors (tests/dx4-jobs.json, vendored by DC9's fake machine)
pin them, with the rules spelled out in their `about`.
"""

import copy
import errno
import fcntl
import json
import mmap
import os
import re
import stat

# DX4's one normalization table: raw word → (status, terminal). A word not in
# it changes no status and is kept in `outcome.raw`.
TABLE = {
    "completed": ("completed", True),
    "failed": ("failed", True),
    "error": ("failed", True),
    "stopped": ("stopped", True),
    "killed": ("stopped", True),
    "cancelled": ("stopped", True),
    "interrupted": ("stopped", True),
    "running": ("running", False),
    "pending": ("running", False),
}
# A background agent's launch result: the engine's word that it started, running
# evidence from the rows, never terminal (DC8's Decision Log, 2026-10-17).
LAUNCHED = "async_launched"
# The engine's launch texts, which name a launch whether or not its row has a toolUseResult (some are written
# without one, a fork's always): the background agent's first line (with or without the later parenthetical) then
# its agentId line, or a fork's whole text (2.1.2xx-2.1.300, read from this machine's transcripts; DC8's fix wave).
LAUNCH_TEXT = re.compile(r"Async agent launched successfully\.(?: \([^\n]*\))?\nagentId: ")
FORK_STARTED = "Fork started — processing in background"
# A monitor's expiry notice: a task-notification for a monitor with no <status> whose <event> is the engine's
# expiry line (2.1.300). It ends the monitor as `completed` (the word MAWS's backfill gives a notification with
# no status), raw `expired` (DC8's Decision Log, 2026-10-17).
EXPIRED = "expired"
EXPIRY_EVENTS = ("[Monitor expired after ", "[Monitor timed out")
NOTIFICATION_PREAMBLE = "[SYSTEM NOTIFICATION - NOT USER INPUT]\n"
# The bridge's notes of tasks it stopped with TaskStop (hooks/mods/bridge.tsx): a plugin's TaskStop writes no row
# of its own, and for a task of the main loop's the engine queues no notification, so the note the bridge appends
# for the model is the rows' only word that the task stopped. The engine keeps the note's user row isMeta with
# origin {kind: plugin}, as it keeps a steer's text, so a note is known by its row's whole text, never by a line
# found inside it: a stop's note (stopNote) is the whole text; an interrupt's (interruptNote) is its origin line,
# then one line per task the interrupt moved to the background, stopped or not. Only a stopped line is evidence,
# and a text with any other line is no note. A steer's row opens with its own line (bridge.tsx STEER_LINE), so it is
# never either; one an older bridge appended has no such line, and the whole-text reading tells it apart.
TASK_ID = r"([A-Za-z0-9_-]{1,64})"
STOP_NOTE = re.compile(r"Task %s, a background task, was stopped from (?:the desk|outside the terminal): "
                       r"it is not running\." % TASK_ID)
INTERRUPT_ORIGINS = ("The interrupt came from the desk.", "The interrupt came from outside the terminal.")
INTERRUPT_STOPPED = re.compile(r"Task %s, the Bash command the interrupt moved to the background, was then stopped: "
                               r"it is not running, and no notification will come for it\." % TASK_ID)
INTERRUPT_RUNNING = re.compile(r"Task %s, the Bash command the interrupt moved to the background, could not be "
                               r"stopped: it may still be running\." % TASK_ID)
ENDED = ("completed", "failed", "stopped", "exited")
SPAWN_FIELDS = ("parentAgentId", "subagentType", "description", "name", "background", "model", "toolUseId")
CALLS = ("Agent", "Task", "Bash", "Monitor", "TaskStop")
OUTPUT_PATH = re.compile(r"Output is being written to: (\S+)")
# The engine's request records (`api-request`, `api-request-blob`, `api-request-shape`): no row, and each repeats
# the conversation, so a task's id is in most of them.
REQUEST_RECORD = b'{"type":"api-request'
ELEMENT = {name: re.compile(r"<%s>([\s\S]*?)</%s>" % (name, name))
           for name in ("task-id", "tool-use-id", "output-file", "status", "summary", "event")}


def normalize(raw):
    """(status, terminal) for a raw word of the table, None for any other."""
    return TABLE.get(raw) if isinstance(raw, str) else None


def _word(raw):
    return ("running", False) if raw == LAUNCHED else normalize(raw)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content
                       if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def _launch_text(text):
    """Whether an Agent result's text is one of the engine's launch texts, matched exactly."""
    return text == FORK_STARTED or LAUNCH_TEXT.match(text) is not None


def _output_path(text):
    """The path after "Output is being written to:", up to whitespace, the sentence's period dropped (MAWS's
    parseOutputPath)."""
    m = OUTPUT_PATH.search(text)
    if not m:
        return None
    path = m.group(1)[:-1] if m.group(1).endswith(".") else m.group(1)
    return path or None


def _element(prompt, name):
    m = ELEMENT[name].search(prompt)
    return m.group(1).strip() if m else None


def _plain_notification(row, content):
    """The notification text of a plain user row the engine wrote for one, or None. The engine marks the row
    `origin.kind: "task-notification"` (no prompt a person types carries it) and writes one notification as the
    row's whole text: bare in the main loop's transcript, after its fixed `[SYSTEM NOTIFICATION - NOT USER INPUT]`
    preamble (ending in a blank line) in a subagent's. The text must then start with `<task-notification>`, as
    MAWS's parseTaskNotification requires."""
    origin = row.get("origin")
    if row.get("type") != "user" or not isinstance(origin, dict) or origin.get("kind") != "task-notification":
        return None
    text = content if isinstance(content, str) else _text(content)
    if text.startswith(NOTIFICATION_PREAMBLE):
        cut = text.find("\n\n<task-notification>")
        text = text[cut + 2:] if cut >= 0 else ""
    return text if text.startswith("<task-notification>") else None


def _stop_records(row, content):
    """(task, line) for each task the bridge's note in this plugin's user row says it stopped (STOP_NOTE)."""
    origin = row.get("origin")
    if row.get("type") != "user" or row.get("isMeta") is not True or not isinstance(origin, dict) \
            or origin.get("kind") != "plugin":
        return ()
    text = content if isinstance(content, str) else _text(content)
    m = STOP_NOTE.fullmatch(text)
    if m:
        return ((m.group(1), text),)
    lines = text.split("\n")
    if lines[0] not in INTERRUPT_ORIGINS:
        return ()
    out = []
    for line in lines[1:]:
        m = INTERRUPT_STOPPED.fullmatch(line)
        if m:
            out.append((m.group(1), line))
        elif not INTERRUPT_RUNNING.fullmatch(line):
            return ()
    return out


def _str(value):
    return value if isinstance(value, str) and value else None


def fold(evidence, outcome=None):
    """The outcome a run of evidence comes to, in row order: a recognized word replaces the outcome unless the
    outcome is terminal and the word is not; an unrecognized word replaces only `raw` of an outcome there is."""
    for ev in evidence:
        word = ("completed", True) if ev.get("expiry") else _word(ev["raw"])
        if word is None:
            if outcome is not None:
                outcome = dict(outcome, raw=ev["raw"])
            continue
        status, terminal = word
        if outcome is not None and outcome["status"] != "running" and not terminal:
            continue
        outcome = {"status": status, "raw": ev["raw"], "at": ev["at"]}
        for key in ("summary", "outputFile"):
            if key in ev:
                outcome[key] = ev[key]
    return outcome


class Ledger:
    """One loop's rows, reduced to what the body and `output` read. Feed rows in file order, in any batches."""

    def __init__(self):
        self.calls = {}      # toolUseId → the call, until its result: {name, at, description?, command?, taskId?}
        self.evidence = []   # every status word a row said, in row order: {raw, at, result?, summary?, outputFile?}
        self.by_task = {}    # task id → indexes into evidence
        self.by_tool = {}    # toolUseId → indexes into evidence
        self.known = {}      # every task id a job, a notification or a task_status named → True
        self.jobs = {}       # task id → {kind, toolUseId, startedAt, description, command?}, in start order
        self.outputs = {}    # task id → the latest output path a row named
        self.mcp = []        # MCP server names added and not removed, in order

    def copy(self):
        return copy.deepcopy(self)

    def view(self, agents, tools):
        """A ledger holding only the evidence that names these agent ids or calls, in row order: all
        `agent_outcome` reads of a parent loop for the agents it ran, small enough to hand to another thread
        where a copy of the whole would not be. Its entries are this ledger's own, never changed once said."""
        picks = {}
        for key, ids, index in (("by_task", agents, self.by_task), ("by_tool", tools, self.by_tool)):
            for name in ids:
                for i in index.get(name, ()):
                    picks.setdefault(i, []).append((key, name))
        out = Ledger()
        for i in sorted(picks):
            out.evidence.append(self.evidence[i])
            for key, name in picks[i]:
                getattr(out, key).setdefault(name, []).append(len(out.evidence) - 1)
        return out

    def feed(self, rows):
        for row in rows:
            self.add(row)

    def add(self, row):
        if not isinstance(row, dict):
            return
        at = row.get("timestamp")
        att = row.get("attachment")
        if isinstance(att, dict):
            self._attachment(att, at)
        msg = row.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        plain = _plain_notification(row, content)
        if plain is not None:
            self._notification(plain, at)
        for task, line in _stop_records(row, content):
            self._said({"raw": "stopped", "at": at, "summary": line}, task=task)
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    self._call(block, at)
                elif block.get("type") == "tool_result":
                    self._result(block, row.get("toolUseResult"), at)

    # -- rows
    def _call(self, block, at):
        name, tid = block.get("name"), block.get("id")
        if name not in CALLS or not isinstance(tid, str):
            return
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        call = {"name": name, "at": at}
        for key, field in (("description", "description"), ("command", "command"), ("taskId", "task_id")):
            if isinstance(inp.get(field), str):
                call[key] = inp[field]
        if name in ("Agent", "Task") and inp.get("run_in_background") in (True, "true"):
            call["background"] = True
        self.calls[tid] = call

    def _result(self, block, tur, at):
        tid = block.get("tool_use_id")
        call = self.calls.pop(tid, None) if isinstance(tid, str) else None
        if call is None:
            return
        # A launch's text names it only on a row with no toolUseResult: where there is one, its status decides (an
        # agent's own answer may begin as a launch does).
        by_text = tur is None
        tur = tur if isinstance(tur, dict) else {}
        is_error = block.get("is_error") is True
        name = call["name"]
        if name in ("Agent", "Task"):
            status = tur.get("status")
            launch = status == LAUNCHED or by_text and not is_error and _launch_text(_text(block.get("content")))
            raw = LAUNCHED if launch else "error" if is_error else status if isinstance(status, str) else "completed"
            ev = {"raw": raw, "at": at, "result": True}
            if raw == LAUNCHED and _str(tur.get("outputFile")):
                ev["outputFile"] = tur["outputFile"]
            if call.get("background"):
                ev["background"] = True
            self._said(ev, tool=tid)
        elif name == "Bash" and _str(tur.get("backgroundTaskId")):
            task = tur["backgroundTaskId"]
            self._start(task, "shell", tid, call)
            path = _output_path(_text(block.get("content")))
            if path:
                self.outputs[task] = path
        elif name == "Monitor" and _str(tur.get("taskId")):
            self._start(tur["taskId"], "monitor", tid, call)
        elif name == "TaskStop" and call.get("taskId") and not is_error:
            ev = {"raw": "stopped", "at": at}
            if _str(tur.get("message")):
                ev["summary"] = tur["message"]
            self._said(ev, task=call["taskId"])

    def _attachment(self, att, at):
        kind = att.get("type")
        if kind == "task_status":
            task = _str(att.get("taskId"))
            if task is None:
                return
            self.known[task] = True
            path = _str(att.get("outputFilePath"))
            if path:
                self.outputs[task] = path
            if isinstance(att.get("status"), str):
                ev = {"raw": att["status"], "at": at}
                if _str(att.get("deltaSummary")):
                    ev["summary"] = att["deltaSummary"]
                if path:
                    ev["outputFile"] = path
                self._said(ev, task=task)
        elif kind == "queued_command" and att.get("commandMode") == "task-notification":
            if isinstance(att.get("prompt"), str):
                self._notification(att["prompt"], at)
        elif kind == "mcp_instructions_delta":
            removed, added = att.get("removedNames"), att.get("addedNames")
            for name in removed if isinstance(removed, list) else ():
                if name in self.mcp:
                    self.mcp.remove(name)
            for name in added if isinstance(added, list) else ():
                if isinstance(name, str) and name not in self.mcp:
                    self.mcp.append(name)

    def _notification(self, prompt, at):
        """One task-notification's text, from either form the engine writes it in."""
        task, tool = _element(prompt, "task-id") or None, _element(prompt, "tool-use-id") or None
        path, raw = _element(prompt, "output-file") or None, _element(prompt, "status")
        if task:
            self.known[task] = True
            if path:
                self.outputs[task] = path
        if raw is not None and (task or tool):
            ev = {"raw": raw, "at": at}
            summary = _element(prompt, "summary")
            if summary:
                ev["summary"] = summary
            if path:
                ev["outputFile"] = path
            self._said(ev, task=task, tool=tool)
        elif raw is None and task and self.jobs.get(task, {}).get("kind") == "monitor":
            event = _element(prompt, "event")
            if event and event.startswith(EXPIRY_EVENTS):
                self._said({"raw": EXPIRED, "at": at, "expiry": True, "summary": event}, task=task)

    def _start(self, task, kind, tid, call):
        self.known[task] = True
        if task not in self.jobs:
            job = {"kind": kind, "toolUseId": tid, "startedAt": call["at"], "description": call.get("description", "")}
            if "command" in call:
                job["command"] = call["command"]
            self.jobs[task] = job

    def _said(self, ev, task=None, tool=None):
        self.evidence.append(ev)
        if task:
            self.by_task.setdefault(task, []).append(len(self.evidence) - 1)
        if tool:
            self.by_tool.setdefault(tool, []).append(len(self.evidence) - 1)

    # -- reading
    def agent_outcome(self, agent_id, tool_use_id, background):
        """The outcome the rows give an agent: what names its task id (its agent id) or its call's toolUseId. A
        background agent's result row counts only as its launch: `background` as the meta or the spawn says, or
        as its call's input did."""
        found = set(self.by_task.get(agent_id, ())) | set(self.by_tool.get(tool_use_id, ()) if tool_use_id else ())
        evidence = [self.evidence[i] for i in sorted(found)]
        evidence = [ev for ev in evidence
                    if not (ev.get("result") and ev["raw"] != LAUNCHED and (background or ev.get("background")))]
        return fold(evidence)

    def jobs_body(self, session_running, also=None):
        """The loop's jobs. `also`, a ledger of the main loop's rows for a subagent's loop: its words on these
        tasks count after the loop's own, since the bridge's record of a subagent's task it stopped is in the
        main loop's transcript (the engine's own notice reaches the subagent only at its next tool batch)."""
        out = []
        for task, job in self.jobs.items():
            said = [self.evidence[i] for i in self.by_task.get(task, ())]
            if also is not None:
                said += [also.evidence[i] for i in also.by_task.get(task, ())]
            o = fold(said, {"status": "running", "raw": "running", "at": job["startedAt"]})
            entry = {"taskId": task, "kind": job["kind"], "toolUseId": job["toolUseId"], "startedAt": job["startedAt"],
                     "description": job["description"], "outputFile": self.outputs.get(task)}
            if "command" in job:
                entry["command"] = job["command"]
            if o["status"] != "running":
                entry["status"], entry["endedAt"] = o["status"], o["at"]
            else:
                entry["status"] = "running" if session_running else "exited"
            if "summary" in o:
                entry["summary"] = o["summary"]
            out.append(entry)
        return out


def file_facts(rows, size, mtime_ms):
    """An agent transcript's facts: its size and mtime as stat'ed, and the timestamps of its first and last rows
    that carry one (null when none does)."""
    stamps = [r["timestamp"] for r in rows if isinstance(r, dict) and isinstance(r.get("timestamp"), str)]
    return {"size": size, "mtimeMs": mtime_ms, "firstAt": stamps[0] if stamps else None,
            "lastAt": stamps[-1] if stamps else None}


def derive(ledger, metas, *, bridge, files, parents, session_running, also=None):
    """DX4's widened `subagents` body. `ledger` is the loop's; `metas` [{agentId, meta}] in order (one entry
    each); `bridge` the bridge's agents (each with `running`), or None for no bridge; `files` {agentId: facts}
    for the agent files there are; `parents` {agentId: Ledger, or None when that agent's transcript is gone or
    unreadable}; `session_running` whether the session's process runs; `also` the main loop's words on a
    subagent loop's tasks (Ledger.jobs_body)."""
    held = {a.get("agentId"): a for a in bridge or () if isinstance(a, dict)}
    meta_of = {m["agentId"]: m["meta"] for m in metas}
    done, busy = {}, set()

    def entry(agent_id):
        if agent_id in done:
            return done[agent_id]
        busy.add(agent_id)
        meta = meta_of[agent_id]
        spawn = held.get(agent_id)
        live = spawn if session_running else None
        background = meta.get("requestShape") == "background" or (spawn or {}).get("background") is True
        parent = _str(meta.get("parentAgentId")) or _str((spawn or {}).get("parentAgentId"))
        tool = _str(meta.get("toolUseId")) or _str((spawn or {}).get("toolUseId"))
        loop = parents.get(parent) if parent else ledger
        outcome = loop.agent_outcome(agent_id, tool, background) if loop is not None else None
        running = live.get("running") if live is not None and isinstance(live.get("running"), bool) else None
        if outcome is not None and outcome["status"] != "running":
            status, evidence = outcome["status"], "rows"
        elif not session_running:
            status, evidence = "exited", "session"
        elif parent and parent in meta_of and parent not in busy and entry(parent)["status"] in ENDED:
            status, evidence = "exited", "parent"
        elif running is False:
            status, evidence = "exited", "bridge"
        elif running is True:
            status, evidence = "running", "bridge"
        elif outcome is not None:
            status, evidence = "running", "rows"
        else:
            status, evidence = "unknown", "none"
        e = {"agentId": agent_id, "meta": meta, "status": status, "evidence": evidence}
        if running is not None:
            e["running"] = running
        if spawn is not None:
            e["spawn"] = {k: spawn[k] for k in SPAWN_FIELDS if k in spawn}
        if outcome is not None:
            e["outcome"] = outcome
        if files.get(agent_id) is not None:
            e["file"] = files[agent_id]
        busy.discard(agent_id)
        done[agent_id] = e
        return e

    return {"subagents": [entry(m["agentId"]) for m in metas], "jobs": ledger.jobs_body(session_running, also),
            "mcp": [{"name": n} for n in ledger.mcp]}


def _lines_holding(mm, needle):
    """The (start, end) of each line of `mm` that holds `needle`, found at the scan's speed rather than a row's
    parse."""
    out, at = set(), 0
    while True:
        i = mm.find(needle, at)
        if i < 0:
            return out
        start = mm.rfind(b"\n", 0, i) + 1
        end = mm.find(b"\n", i)
        end = len(mm) if end < 0 else end
        out.add((start, end))
        at = end + 1


def _task_calls(row, task):
    """The calls a row ties to `task` as a task: the tool_results of a row whose toolUseResult started it
    (backgroundTaskId, taskId), and a TaskStop call naming it (input.task_id)."""
    msg = row.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    tur = row.get("toolUseResult")
    started = isinstance(tur, dict) and task in (tur.get("backgroundTaskId"), tur.get("taskId"))
    out = set()
    for block in content if isinstance(content, list) else ():
        if not isinstance(block, dict):
            continue
        if started and block.get("type") == "tool_result" and _str(block.get("tool_use_id")):
            out.add(block["tool_use_id"])
        elif block.get("type") == "tool_use" and block.get("name") == "TaskStop" and _str(block.get("id")) \
                and isinstance(block.get("input"), dict) and block["input"].get("task_id") == task:
            out.add(block["id"])
    return out


def task_rows(path, task):
    """The rows of one loop's transcript that can say what task `task` is and how it stands, in file order: each
    row naming it exactly (its start's result, a notification, a `task_status`, a TaskStop call, a bridge's note),
    then each row naming a call those rows tie to the task (the start's own call, the TaskStop's result). Fed to a
    Ledger, they give the task the status the whole file would; a short id
    reads no more rows than it names. The file is searched, not parsed: only those rows are, and never the engine's
    request records, which repeat the conversation (most of a long transcript's bytes) and hold no row. Empty
    when the file never names the task or cannot be read."""
    try:
        with open(path, "rb") as f:
            if os.fstat(f.fileno()).st_size == 0:
                return []
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        return []
    try:
        rows = {}

        def take(spans):
            for span in spans - rows.keys():
                line = mm[span[0]:span[1]]
                row = None
                if not line.startswith(REQUEST_RECORD):
                    try:
                        row = json.loads(line)
                    except ValueError:
                        pass
                rows[span] = row if isinstance(row, dict) and _str(row.get("uuid")) else None

        # The task's exact references, never its bare id, which a short one shares with most rows: a whole JSON
        # string (backgroundTaskId, taskId, task_id), a notification's element, a bridge's note (STOP_NOTE).
        for needle in ('"%s"', "<task-id>%s</task-id>", "Task %s, "):
            take(_lines_holding(mm, (needle % task).encode()))
        ids = set()
        for row in [r for r in rows.values() if r is not None]:
            ids |= _task_calls(row, task)
        for i in sorted(ids):
            take(_lines_holding(mm, ('"%s"' % i).encode()))
        return [rows[span] for span in sorted(rows) if rows[span] is not None]
    finally:
        mm.close()


def running_task(main, task):
    """Whether `task` is a background shell or monitor the session's jobs index holds as running, its process
    running: the main loop's (`main`, its transcript) or any subagent's, each loop's rows read as the plane reads
    them (the job's start, then its notifications, `task_status` and TaskStop through the one table)."""
    if not main.endswith(".jsonl"):
        return False
    agents = os.path.join(main[:-len(".jsonl")], "subagents")
    try:
        loops = [main] + sorted(os.path.join(agents, n) for n in os.listdir(agents)
                                if n.startswith("agent-") and n.endswith(".jsonl"))
    except OSError:
        loops = [main]
    top = None
    for path in loops:
        ledger = Ledger()
        ledger.feed(task_rows(path, task))
        if top is None:
            top = ledger
        if task in ledger.jobs:
            body = ledger.jobs_body(True, None if ledger is top else top)
            return any(j["taskId"] == task and j["status"] == "running" for j in body)
    return False


def rows_naming(path, agents, tools):
    """The rows of one loop's transcript that name any of these agent ids (as a whole JSON string, or a
    notification's task id) or calls (their toolUseId), in file order: every row `agent_outcome` reads for
    them (`sminos list --subagents` asks it of a parent loop for the agents whose own rows leave them open).
    Searched, not parsed, as task_rows is; None when the file cannot be read."""
    try:
        with open(path, "rb") as f:
            if os.fstat(f.fileno()).st_size == 0:
                return []
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        return None
    try:
        spans = set()
        for name in agents:
            for needle in ('"%s"', "<task-id>%s</task-id>"):
                spans |= _lines_holding(mm, (needle % name).encode())
        for tool in tools:
            spans |= _lines_holding(mm, ('"%s"' % tool).encode())
        rows = []
        for start, end in sorted(spans):
            line = mm[start:end]
            if line.startswith(REQUEST_RECORD):
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and _str(row.get("uuid")):
                rows.append(row)
        return rows
    finally:
        mm.close()


def _opened_path(fd):
    """The path of the file a descriptor holds, as the kernel names it (macOS F_GETPATH, Linux /proc), or None
    where it cannot say."""
    if hasattr(fcntl, "F_GETPATH"):
        try:
            return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
        except OSError:
            return None
    try:
        return os.readlink("/proc/self/fd/%d" % fd)
    except OSError:
        return None


def output_answer(request, ledger, session, roots):
    """DX4's `output` body for `request` {taskId, tail}: the last `tail` bytes of the file the loop's rows named
    for the task, only when it is <a root>/<taskId>.output once resolved and a regular file. `roots` are the
    session's canonical task directories, derived by the caller from the machine's own state, never from a row."""
    task, tail = request["taskId"], request["tail"]
    if task not in ledger.known:
        return {"taskId": task, "result": "unknown-task"}
    path = ledger.outputs.get(task)
    if path is None:
        return {"taskId": task, "result": "missing", "path": None}

    def refused(reason):
        return {"taskId": task, "result": "refused", "path": path, "reason": reason}

    name = task + ".output"
    if not os.path.isabs(path) or path.split("/")[-3:] != [session, "tasks", name]:
        return refused("The output file this task's rows named is not this session's (%s/tasks/%s)." % (session, name))
    real = os.path.realpath(path)
    if os.path.basename(real) != name or os.path.dirname(real) not in {os.path.realpath(r) for r in roots}:
        return refused("The output file this task's rows named resolves to another file, outside this session's "
                       "task directories or not this task's own.")
    try:
        fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        if e.errno == errno.ELOOP:  # a link put in its place since it was resolved: containment, not absence
            return refused("The output file was replaced by a link while it was opened.")
        # Gone, or nothing readable there: `refused` is the containment refusal alone (DX4).
        return {"taskId": task, "result": "missing", "path": path}
    try:
        # The pathname was checked; the open walks it again, and O_NOFOLLOW guards only its last component. What
        # the descriptor holds must itself be that file, so a directory above it swapped for a link meanwhile
        # cannot lead the read outside every root.
        if _opened_path(fd) != real:
            return refused("The output file this task's rows named moved outside this session's task directories "
                           "while it was opened.")
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return refused("The output path is not a regular file.")
        size = st.st_size
        start = max(0, size - tail)
        os.lseek(fd, start, os.SEEK_SET)
        data = b""
        while len(data) < size - start:
            chunk = os.read(fd, size - start - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    if start > 0:
        cut = data.find(b"\n")
        if cut >= 0:
            data, start = data[cut + 1:], start + cut + 1
    return {"taskId": task, "result": "ok", "path": path, "size": size, "from": start,
            "text": data.decode("utf-8", "replace"), "truncated": start > 0}
