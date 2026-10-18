#!/usr/bin/env python3
"""sminos_plane — the session plane on this machine (DC7 of the desk: DX4 as
its machine-side producer, DX2's session frames, DX5 as a consumer).

The uplink (sminos_uplink.py) holds the stream and posts; this module says
what the machine's sessions are doing and serves the hub's subscriptions.
Everything here runs on the uplink's main thread but the readers of the
bridges' streams, the diff runs, and every read of a transcript's bulk —
which only read sockets, run git, and read files, and hand what they read
over through queues. A transcript's bulk is read on its worker (Transcript),
one per file, one read at a time: an open's build and every `rows` page,
through the file's offset index (Index: each row's uuid, byte offset and
length, built once per file, extended from where it stopped, shared by every
subscription on it and kept a while after the last one goes). The main
thread parses only the bytes flushed since its subscription's Tail last read.

Presence. For every session of a hub project on this machine, its record in
the engine's registry (`~/.claude/sessions/<pid>.json`: `status`,
`waitingFor`, `needs`, verbatim; null once no process holds it) and whether
its bridge answers (DX5's `GET /status`) reach the hub as DX4 `presence`
when either changes, and all of them after every connect. The log's
debounced `state` events stay the record for an offline machine.

Subscriptions. The hub's `subscribe` names a session and a transcript — the
main one (`agentId` null) or one subagent's. The answer is DX4's: a snapshot
(rows newest first, as many as fit the budget, up to the last row flushed;
the subagent tree; presence; the bridge's streaming entries; usage on a main
one), then `row`, `chunk`, `block-row`, `step-end` (a model request ended:
DX5's step end, or the turn's end cutting it off, after its block-rows),
`subagents`, `usage`, each numbered, and `end`. Rows come from the transcript on disk and everything live from the
bridge's DX5 stream, so the two are joined in one order — the disk's (DX5's
row order, composite cd2667d8):

- every row the mod observes gets one notice on the bridge's stream once the
  engine has taken it, so within a loop notice order is write order and a
  notice may trail the flush: `block-row` for a response row, `row-seen` for
  any other;
- the bridge's snapshot carries `cut`, per loop the last notice it applied,
  seeded at the module's load with the loop's last row then: history is the
  loop's rows up to and including it, once that row is on disk (NOTICE_WAIT,
  else the subscription ends), so no block still streaming has its row in
  history; a null cut (or a loop it does not name) means the loop had no
  rows at load, so its history is empty and every row of it is live;
- live, each loop's rows go out strictly in disk order: a row past the cut
  is released by its own notice, by a notice for any later row of the loop,
  or UNNAMED_WAIT after it was first seen on disk with neither (rows written
  together go out together), and every later row waits behind it; a notice
  whose row is not on disk within NOTICE_WAIT ends the subscription;
- a `row-seen` for a row already emitted is passed over; a `block-row` for a
  row already emitted as unnamed ends the subscription, whose fresh snapshot
  heals what would otherwise be drawn twice (the real child closes a step's
  pairing at its end, so this comes only from a notice later than the 2 s);
  so does one for a history row whose block the subscriber still holds,
  which the seeded cut rules out and is kept as a guard.

A gap in the bridge's stream, and its end while the session runs (the child
ends every subscription on a module reload), end the subscription with
`discontinuity`: the browser subscribes again. Without a bridge the rows come
from the transcript alone, streaming empty and usage null.

What the session runs (DX4, "Jobs and agent status"; DC8 M4): the snapshot
and every `subagents` message carry the widened body sminos_jobs derives —
each subagent's status with its evidence, the loop's background shells and
monitors, its MCP names — from the loop's rows (a jobs ledger the open's
build feeds and the Tail keeps feeding), the bridge's agent state (its
snapshot's `agents`, then every `agent` spawn and stop), and disk facts
looked at on the worker every METAS_EVERY, each file stat'ed and read only
when it changed (Disk): the metas, each agent transcript's facts, and the
ledger of each loop that ran a nested agent. A `subagents` message goes
whenever that body changes, and when the process goes, since then every
entry is derived again. An agent's subscription carries its own entry
(derived from the loops above it) and its own loop's jobs. `output` reads
the last bytes of a task's output file the loop's rows named, on the worker,
under the session's canonical roots (output_roots).

A subscription outlives its session (DX4, "History and ended sessions"):
once the session is not running and what it flushed is drawn, it goes on
transcript-only and idle, answering pages until it is unsubscribed, the
stream ends, or a discontinuity ends it — a bridge answering for the session
again (Resume) among them. A session with no process is served the same way,
a snapshot from disk, then pages. Only a subscription to a session with no
process whose transcript this machine does not hold ends `session-ended`, at
`n` 0. An idle subscription answers `output` too.
"""

import collections
import glob
import http.client
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_bridge as bridge  # noqa: E402
import sminos_jobs as jobs  # noqa: E402

UNNAMED_WAIT = 2.0        # s: a row past the cut that no notice named is drawn after this
NOTICE_WAIT = 5.0         # s: a row a notice named that is not on disk by then ends the subscription
OPEN_WAIT = 20.0          # s: a bridge that sends no snapshot by then ends the subscription (the reader's 503 retries take up to 15)
END_GRACE = 1.0           # s: once the session is not running, what it still flushes is drawn this long
ROWS_BUDGET = 512 * 1024  # bytes of row JSON in a snapshot or a page: "as many as fit"
ROW_KEY = b'"uuid"'       # a line without these bytes holds no row: it is not parsed
READ_BLOCK = 8 << 20      # bytes an index reads at a time
INDEX_KEEP = 4            # transcripts whose index is kept after their last subscription went
PRESENCE_EVERY = 0.2      # s: how often the engine's records are looked at
BRIDGE_RECHECK = 2.0      # s: how often a bridge that answered is asked again
METAS_EVERY = 0.5         # s: how often a main subscription's subagent tree is looked at
LOCATE_EVERY = 1.0        # s: how often a transcript not found yet is looked for
MEMBERS_EVERY = 10.0      # s: how often the members are read again when no session came or went
IDENTITY_EVERY = 10.0     # s: how stale a running pid's identity may be (its start time read this often)
TOMBSTONE_FILE = "presence.json"  # under daemon/: project id → the time its sessions' leaving was last said and taken
TOMBSTONE_MARGIN = 60.0   # s: a session that left this long before that time is said again (clock steps, a write in flight)
DIFF_MAX = 4 << 20        # bytes of diff text; the rest is cut and said so
GIT_TIMEOUT = 30
PROBE_TIMEOUT = 1.0
CONNECT_WAIT = 10.0       # s: the bridge holds GET /events until ready, at most 5 s
NOT_READY_WINDOW = 5.0    # s: a 503 (not ready) is asked again this long, as `sminos watch` does
RECORD_FIELDS = ("status", "waitingFor", "needs")
AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")   # DX3 `output`'s taskId, as the engine spells task ids
OUTPUT_TAIL_MAX = 524288  # bytes an `output` may ask for: the answer fits one frame (DX3)
DISK_KEEP = 4096          # files whose facts the disk cache keeps (metas, agent transcripts, parent loops)
STAMP_BLOCK = 64 << 10    # bytes read at a time looking backward for an agent transcript's last row
SLUG_MAX = 200            # UTF-16 units of the engine's slug before it is cut and hashed (2.1.300 `xge`)
# What a parent loop's ledger parses — only what an agent's outcome reads (Loop.add): a call of Agent, Task or
# TaskStop; a notification or a task_status; a result of a call it holds. Every other line (the loop's Bash,
# Read, Edit calls and their results: most of an agent transcript's bytes) is passed over unparsed.
AGENT_CALL = re.compile(rb'"name":\s*"(?:Agent|Task)')   # TaskStop and the Task tools too
OUTCOME_KEYS = (b"task-notification", b'"task_status"', b": it is not running")   # the last: in each stopped line of the bridge's notes (sminos_jobs.STOP_NOTE)
RESULT_OF = re.compile(rb'"tool_use_id":\s*"([^"\\]+)"')


def envelope(project, machine, session, kind, sub, n, body):
    return {"project": project, "machine": machine, "session": session, "kind": kind, "sub": sub, "n": n,
            "body": body}


def frame(message):
    return {"t": "session", "message": message}


def log(line):
    sminos.daemon_log("plane: " + line)


# ------------------------------------------------------------- the transcript


def parse_row(line):
    """The row a line holds — a JSON object with a string uuid (the engine's
    bookkeeping records, which have none, are not rows) — or None. A line
    without the bytes `"uuid"` holds no such key at any depth (the engine
    writes keys unescaped) and is not parsed: records of that kind can be
    most of a transcript's bytes (129 of 178 MB in one measured on
    2026-10-17, most of them `api-request` bodies)."""
    if ROW_KEY not in line:
        return None
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) and isinstance(row.get("uuid"), str) and row["uuid"] else None


def parse_rows(lines):
    """(uuid, row) for each line that is a row."""
    out = []
    for line in lines:
        row = parse_row(line)
        if row is not None:
            out.append((row["uuid"], row))
    return out


class Reset(Exception):
    """The transcript shrank or was replaced: what was read of it no longer holds."""


class Tail:
    """One transcript file read forward in whole lines: `read` returns the
    rows flushed since the last read; a line not yet ended waits."""

    def __init__(self):
        self.path = ""
        self.offset = 0
        self.ino = None

    def read(self, path):
        if not path:
            return []
        if self.path and path != self.path:
            raise Reset("the transcript moved to %s" % path)
        self.path = path
        try:
            with open(path, "rb") as f:
                st = os.fstat(f.fileno())
                if self.ino is not None and (st.st_ino != self.ino or st.st_size < self.offset):
                    raise Reset("the transcript was replaced or shrank")
                self.ino = st.st_ino
                f.seek(self.offset)
                data = f.read()
        except FileNotFoundError:
            if self.ino is not None:
                raise Reset("the transcript is gone") from None
            return []
        end = data.rfind(b"\n")
        if end < 0:
            return []
        self.offset += end + 1
        return parse_rows(data[:end].split(b"\n"))


class Index:
    """One transcript file's rows in file order — each one's uuid, the byte
    offset of its line and the line's length — read forward from where it
    stopped, so a page reads its own rows' bytes and nothing else. Used on
    its transcript's worker alone. Once it has read the file, `extend` and
    `rows` raise Reset when the file was replaced, shrank, or is gone."""

    def __init__(self, path):
        self.path = path
        self.ino = None
        self.end = 0           # just past the last whole line read
        self.uuids, self.offsets, self.lengths = [], [], []
        self.at = {}           # uuid → its first position
        self.parsed = 0        # bytes handed to the parser, all told: what building it cost

    def check(self, st, through):
        if self.ino is not None and (st.st_ino != self.ino or st.st_size < through):
            raise Reset("the transcript was replaced or shrank")
        self.ino = st.st_ino

    def extend(self, on_row=None):
        """Reads what was flushed past `end`, in blocks; a line not yet ended
        waits. `on_row`, if given, sees each new row as it is parsed."""
        try:
            f = open(self.path, "rb")
        except FileNotFoundError:
            if self.ino is not None:
                raise Reset("the transcript is gone") from None
            return
        with f:
            self.check(os.fstat(f.fileno()), self.end)
            f.seek(self.end)
            carry, at = b"", self.end
            while True:
                block = f.read(READ_BLOCK)
                if not block:
                    break
                lines = (carry + block).split(b"\n")
                carry = lines.pop()
                for line in lines:
                    if ROW_KEY in line:
                        self.parsed += len(line)
                        row = parse_row(line)
                        if row is not None:
                            self.at.setdefault(row["uuid"], len(self.uuids))
                            self.uuids.append(row["uuid"])
                            self.offsets.append(at)
                            self.lengths.append(len(line))
                            if on_row is not None:
                                on_row(row)
                    at += len(line) + 1
            self.end = at

    def rows(self, lo, hi):
        """The rows at positions lo … hi-1, oldest first: one seek and one
        read of the span from the first one's line through the last's."""
        if lo >= hi:
            return []
        start, stop = self.offsets[lo], self.offsets[hi - 1] + self.lengths[hi - 1]
        try:
            with open(self.path, "rb") as f:
                self.check(os.fstat(f.fileno()), self.end)
                f.seek(start)
                data = f.read(stop - start)
        except FileNotFoundError:
            raise Reset("the transcript is gone") from None
        if len(data) < stop - start:
            raise Reset("the transcript shrank")
        out = []
        for i in range(lo, hi):
            row = parse_row(data[self.offsets[i] - start:self.offsets[i] - start + self.lengths[i]])
            if row is not None:
                out.append(row)
        return out

    def older(self, hi, limit):
        """Where a page of the rows before position `hi` starts: the newest of
        them that fit ROWS_BUDGET (at least one) and `limit` (None: no limit).
        A row counts its line's bytes as the engine wrote it."""
        lo, used = hi, 0
        while lo > 0:
            size = self.lengths[lo - 1]
            if lo < hi and (used + size > ROWS_BUDGET or (limit is not None and hi - lo >= limit)):
                break
            used += size
            lo -= 1
        return lo


class Transcript:
    """One transcript file's index, its loop's jobs ledger, and the worker
    that reads it: every read of the file's bulk — an open's build, a page,
    a look at the disk facts, an `output` — is a job run here, one at a
    time, in the order submitted. A job is `job(transcript)` and hands its
    own result over; the index and the ledger, fed every row the index reads,
    are touched by jobs alone."""

    def __init__(self, path):
        self.path = path
        self.index = Index(path)
        self.ledger = jobs.Ledger()
        self.users = 0         # the subscriptions holding it (under Transcripts' lock)
        self.lock = threading.Lock()
        self.jobs = collections.deque()
        self.working = False

    def submit(self, job):
        with self.lock:
            self.jobs.append(job)
            if self.working:
                return
            self.working = True
        threading.Thread(target=self.work, name="plane-transcript", daemon=True).start()

    def work(self):
        while True:
            with self.lock:
                if not self.jobs:
                    self.working = False
                    return
                job = self.jobs.popleft()
            job(self)

    def extended(self):
        """The index, brought up to the file's end. A file replaced or shrunk
        since leaves a fresh index for whoever reads next, and the Reset says
        so to the reader holding rows of the old one."""
        try:
            self.index.extend(self.ledger.add)
        except Reset:
            self.index, self.ledger = Index(self.path), jobs.Ledger()
            raise
        return self.index


class Transcripts:
    """The transcripts the subscriptions read, by path: one Transcript per
    file, shared by every subscription on it, and kept after the last one
    goes — the `keep` released last — so a second subscription, or the same
    browser subscribing again, builds nothing. One per process
    (TRANSCRIPTS), kept across the uplink's streams."""

    def __init__(self, keep=INDEX_KEEP):
        self.keep = keep
        self.lock = threading.Lock()
        self.held = collections.OrderedDict()   # path → Transcript, the least recently used first

    def acquire(self, path):
        with self.lock:
            t = self.held.pop(path, None) or Transcript(path)
            t.users += 1
            self.held[path] = t
            return t

    def release(self, t):
        with self.lock:
            t.users -= 1
            if self.held.get(t.path) is t:
                self.held.move_to_end(t.path)
            idle = [p for p, held in self.held.items() if held.users <= 0]
            for p in idle[:max(0, len(idle) - self.keep)]:
                del self.held[p]


TRANSCRIPTS = Transcripts()


class Built:
    """An open's build, read on the transcript's worker: what a subscription
    starts from. `ino` and `offset` are where its Tail picks up (`ino` None:
    no file yet); `emitted` the history's uuids; `shown` the history's newest
    rows that fit, newest first, `more` whether older ones are left; `past`
    the rows past the cut, (uuid, row) oldest first, which go out live;
    `ledger` the loop's jobs ledger as of `offset`, the subscription's own to
    feed from there; `facts` the disk facts, once looked at."""

    def __init__(self, ino, offset, emitted, shown, more, past, ledger):
        self.ino, self.offset = ino, offset
        self.emitted, self.shown, self.more, self.past = emitted, shown, more, past
        self.ledger = ledger
        self.facts = None


def build(t, cut, bridged):
    """An open's build on the worker: the index brought up to the file's end
    (a file replaced since an earlier subscription read it starts over: this
    one holds nothing of the old), the history to the cut, the newest of it
    that fits read back, and the rows past the cut. ("waiting", None) while
    the cut's row is not on disk."""
    try:
        index = t.extended()
    except Reset:
        index = t.extended()
    n = len(index.uuids)
    if cut is not None:
        at = index.at.get(cut)
        if at is None:
            return "waiting", None
        split = at + 1
    else:
        # No cut: a bridged loop had no rows when the module loaded (all are
        # live); without a bridge every row is history.
        split = 0 if bridged else n
    lo = index.older(split, None)
    return "built", Built(index.ino, index.end, dict.fromkeys(index.uuids[:split], "history"),
                          index.rows(lo, split)[::-1], lo > 0, [(r["uuid"], r) for r in index.rows(split, n)],
                          t.ledger.copy())


def page_of(t, ino, before, limit):
    """A `rows` page on the worker: the index extended first, so rows flushed
    since the open are pageable; then the rows before `before` that fit,
    newest first, read off their own span. A file not the one the
    subscription read (`ino`) is a Reset."""
    index = t.extended()
    if index.ino != ino:
        raise Reset("the transcript was replaced")
    at = index.at.get(before)
    if not at:
        return "page", {"rows": [], "before": before, "more": False}
    lo = index.older(at, limit)
    return "page", {"rows": index.rows(lo, at)[::-1], "before": before, "more": lo > 0}


def agent_path(main, agent):
    """A subagent's transcript beside the session's (the engine's layout:
    <session>/subagents/agent-<id>.jsonl)."""
    return "%s/subagents/agent-%s.jsonl" % (main[:-len(".jsonl")], agent) if main.endswith(".jsonl") else ""


# ------------------------------------------------------------- the disk facts


def read_lines(f, start, on_line):
    """Every whole line of `f` from byte `start`, in blocks, to `on_line`; a
    line not yet ended waits. Returns the offset just past the last one."""
    f.seek(start)
    carry, at = b"", start
    while True:
        block = f.read(READ_BLOCK)
        if not block:
            return at
        lines = (carry + block).split(b"\n")
        carry = lines.pop()
        for line in lines:
            on_line(line)
            at += len(line) + 1


def stamp_of(line):
    row = parse_row(line)
    return row["timestamp"] if row is not None and isinstance(row.get("timestamp"), str) else None


def first_stamp(f):
    """The timestamp of the file's first whole row that has one, or None:
    read forward, which in a transcript stops at its first line."""
    f.seek(0)
    for line in f:
        if not line.endswith(b"\n"):
            return None
        stamp = stamp_of(line[:-1])
        if stamp is not None:
            return stamp
    return None


def last_stamp(f, size):
    """The timestamp of the last whole row before byte `size` that has one,
    or None: the line feeds found backward a block at a time, each line read
    once found, newest first."""
    stop = None   # the line feed ending the line looked at next
    pos = size
    while pos > 0:
        n = min(STAMP_BLOCK, pos)
        pos -= n
        f.seek(pos)
        block = f.read(n)
        i = len(block)
        while True:
            i = block.rfind(b"\n", 0, i)
            if i < 0:
                break
            if stop is not None:
                f.seek(pos + i + 1)
                stamp = stamp_of(f.read(stop - pos - i - 1))
                if stamp is not None:
                    return stamp
            stop = pos + i
    if stop:
        f.seek(0)
        return stamp_of(f.read(stop))
    return None


class Loop:
    """A parent loop's transcript read forward into a jobs ledger, from where
    it stopped, again only when the file's size or mtime changed; started
    over when it was replaced or shrank. The ledger holds what the agents
    the loop ran come to — all a view of it is read for — so only the lines
    that can say it are parsed: its jobs and MCP names are not kept."""

    def __init__(self):
        self.lock = threading.Lock()   # one reader at a time, which views are taken under
        self.sig = None
        self.ino = None
        self.offset = 0
        self.ledger = jobs.Ledger()

    def add(self, line):
        if ROW_KEY not in line:
            return
        if not (AGENT_CALL.search(line) or any(k in line for k in OUTCOME_KEYS)
                or (b'"tool_result"' in line
                    and any(i.decode("ascii", "replace") in self.ledger.calls for i in RESULT_OF.findall(line)))):
            return
        row = parse_row(line)
        if row is not None:
            self.ledger.add(row)

    def read(self, path, disk):
        st = os.stat(path)
        sig = (st.st_ino, st.st_size, st.st_mtime_ns)
        if sig == self.sig:
            return
        with open(path, "rb") as f:
            disk.count()
            st = os.fstat(f.fileno())
            if st.st_ino != self.ino or st.st_size < self.offset:
                self.ino, self.offset, self.ledger = st.st_ino, 0, jobs.Ledger()
            self.offset = read_lines(f, self.offset, self.add)
        self.sig = sig


class Disk:
    """What the subscriptions know of the files they only look at — each
    subagent's meta, each agent transcript's facts, each parent loop's
    ledger — kept by path and read again only when the file's size or mtime
    changed: an unchanged check is a stat. One per process (DISK), shared by
    every transcript's worker; `opened` counts the files opened, all told."""

    def __init__(self, keep=DISK_KEEP):
        self.keep = keep
        self.lock = threading.Lock()
        self.held = collections.OrderedDict()   # (kind, path) → entry, the least recently used first
        self.opened = 0

    def count(self):
        with self.lock:
            self.opened += 1

    def get(self, key):
        with self.lock:
            entry = self.held.get(key)
            if entry is not None:
                self.held.move_to_end(key)
            return entry

    def put(self, key, entry):
        with self.lock:
            self.held[key] = entry
            self.held.move_to_end(key)
            while len(self.held) > self.keep:
                self.held.popitem(last=False)

    def meta(self, path, st):
        """The meta file verbatim (a dict), or None when it is not one."""
        sig = (st.st_ino, st.st_size, st.st_mtime_ns)
        held = self.get(("meta", path))
        if held is not None and held[0] == sig:
            return held[1]
        try:
            with open(path, "rb") as f:
                self.count()
                meta = json.load(f)
        except (OSError, ValueError):
            meta = None
        meta = meta if isinstance(meta, dict) else None
        self.put(("meta", path), (sig, meta))
        return meta

    def facts(self, path, st):
        """An agent transcript's DX4 `file`: {size, mtimeMs, firstAt, lastAt}
        (the timestamps of its first and last rows that carry one), or None
        when it cannot be read. A file that only grew keeps its firstAt."""
        sig = (st.st_ino, st.st_size, st.st_mtime_ns)
        held = self.get(("file", path))
        if held is not None and held[0] == sig:
            return held[1]
        grown = held is not None and held[1] is not None and held[0][0] == st.st_ino and held[0][1] <= st.st_size
        try:
            with open(path, "rb") as f:
                self.count()
                first = held[1]["firstAt"] if grown and held[1]["firstAt"] else first_stamp(f)
                facts = {"size": st.st_size, "mtimeMs": st.st_mtime_ns / 1e6, "firstAt": first,
                         "lastAt": last_stamp(f, st.st_size)}
        except OSError:
            facts = None
        self.put(("file", path), (sig, facts))
        return facts

    def view(self, path, agents, tools):
        """What a parent loop's rows say of the agents it ran (`agents` and
        their calls `tools`): a view of its ledger (jobs.Ledger.view), or None
        when its transcript is gone or unreadable."""
        key = ("loop", path)
        loop = self.get(key)
        if loop is None:
            loop = Loop()
            self.put(key, loop)
        with loop.lock:
            try:
                loop.read(path, self)
            except OSError:
                return None
            return loop.ledger.view(agents, tools)


DISK = Disk()


class Facts:
    """What a subscription's widened `subagents` body reads off disk, looked
    at on its transcript's worker: `metas` [{agentId, meta}] in the order the
    meta files were written; `files` {agentId: DX4 file}; `parents`
    {agentId: a view of that agent's ledger for the agents it ran, or None:
    its transcript is gone or unreadable}; `main` (an agent's subscription)
    the main loop's view for the agents it ran."""

    def __init__(self, metas=(), files=None, parents=None, main=None, stops=None):
        self.metas, self.files, self.parents, self.main = list(metas), files or {}, parents or {}, main
        self.stops = stops   # (an agent's) the main loop's view for the agent's own jobs: the bridge's records


def subagents_dir(main):
    return os.path.join(main[:-len(".jsonl")], "subagents") if main.endswith(".jsonl") else ""


def look(disk, main, agent, spawns, tasks=()):
    """The disk facts of a main subscription (every subagent) or of an
    agent's (that agent and the chain of agents above it, whose ends end
    it); `spawns` {agentId: (parentAgentId, toolUseId)} from the bridge's
    agent state, for what a meta does not say; `tasks` an agent's own jobs,
    whose stop the bridge records in the main loop's rows. Each file
    stat'ed, read only when it changed (Disk)."""
    d = subagents_dir(main)
    if not d:
        return Facts()

    def meta_of(name):
        """(its meta file's mtime, {agentId, meta}), or None: no meta."""
        path = os.path.join(d, "agent-%s.meta.json" % name)
        try:
            st = os.stat(path)
        except OSError:
            return None
        meta = disk.meta(path, st)
        return (st.st_mtime_ns, {"agentId": name, "meta": meta}) if meta is not None else None

    def link(m):
        """Its parent's id and its call's toolUseId, None for none: the
        meta's, else the bridge's spawn's (as derive reads them)."""
        parent, tool = spawns.get(m["agentId"], (None, None))
        own = m["meta"].get("toolUseId")
        return _id(m["meta"].get("parentAgentId")) or _id(parent), own if isinstance(own, str) and own else tool

    if agent is None:
        try:
            names = os.listdir(d)
        except OSError:
            names = []
        ids = [n[len("agent-"):-len(".meta.json")] for n in names if n.startswith("agent-") and n.endswith(".meta.json")]
        found = [m for m in (meta_of(i) for i in ids if AGENT_ID.fullmatch(i)) if m is not None]
        metas = [m for _, m in sorted(found, key=lambda x: (x[0], x[1]["agentId"]))]
        filed = metas
    else:
        metas, name = [], agent   # the agent, then each one above it
        while name and AGENT_ID.fullmatch(name) and name not in {m["agentId"] for m in metas}:
            m = meta_of(name)
            if m is None:
                break
            metas.append(m[1])
            name = link(m[1])[0]
        filed = metas[:1]
    files = {}
    for m in filed:
        path = agent_path(main, m["agentId"])
        try:
            st = os.stat(path)
        except OSError:
            continue
        facts = disk.facts(path, st)
        if facts is not None:
            files[m["agentId"]] = facts
    loops = {}
    for m in metas:
        parent, tool = link(m)
        ids = loops.setdefault(parent, ([], []))
        ids[0].append(m["agentId"])
        if tool:
            ids[1].append(tool)
    parents = {p: disk.view(agent_path(main, p), *ids) for p, ids in loops.items() if p}
    top = disk.view(main, *loops[None]) if agent is not None and None in loops else None
    stops = disk.view(main, list(tasks), []) if agent is not None and tasks else None
    return Facts(metas, files, parents, top, stops)


def _id(value):
    return value if isinstance(value, str) and AGENT_ID.fullmatch(value) else None


def engine_slug(path):
    """The engine's name for a directory under its per-project roots (SPEC
    §35.2.1, `j0` in 2.1.300): every UTF-16 unit outside [A-Za-z0-9] a `-`;
    past SLUG_MAX units, cut there and the original's base-36 hash added."""
    raw = path.encode("utf-16-le", "surrogatepass")
    units = [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]
    slug = "".join(chr(u) if u < 128 and chr(u).isalnum() else "-" for u in units)
    if len(slug) <= SLUG_MAX:
        return slug
    h = 0
    for u in units:
        h = (h * 31 + u) & 0xFFFFFFFF
    h = abs(h - (1 << 32) if h >= 1 << 31 else h)
    digits = ""
    while True:
        h, d = divmod(h, 36)
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"[d] + digits
        if not h:
            break
    return "%s-%s" % (slug[:SLUG_MAX], digits)


def output_roots(session, main, cwds):
    """`output`'s canonical roots for a session (DX4; DC8's Decision Log),
    from this machine's state alone, never a row: the engine's tasks
    directory, <realpath of CLAUDE_CODE_TMPDIR or /tmp>/claude-<uid>/<slug>/
    <session>/tasks, for the slug of the transcript's project directory and
    for each working directory's engine slug, once each."""
    base = os.path.realpath(os.path.join(os.environ.get("CLAUDE_CODE_TMPDIR") or "/tmp", "claude-%d" % os.getuid()))
    slugs = [os.path.basename(os.path.dirname(main))] if main else []
    slugs += [engine_slug(cwd) for cwd in cwds if isinstance(cwd, str) and cwd]
    return [os.path.join(base, slug, session, "tasks") for slug in dict.fromkeys(slugs)]


# ------------------------------------------------------------- the bridge's stream


class BridgeReader(threading.Thread):
    """One subscription to a bridge's endpoint (`GET /events`): every line
    goes to `items` as ("line", obj), and the stream's fate as ("unavailable",
    why) when nothing answers there, ("refused", status) when the bridge
    turned the subscription down (503: not ready), or ("closed", why) when it
    ended. It calls nothing of sminos."""

    def __init__(self, path, wake):
        super().__init__(name="plane-bridge", daemon=True)
        self.path = path
        self.wake = wake
        self.items = queue.Queue()
        self.closing = threading.Event()
        self.sock = None

    def put(self, item):
        self.items.put(item)
        self.wake()

    def run(self):
        """A 503 (the child has not had the mod's first resync) is asked
        again until NOT_READY_WINDOW has passed since the first, as `sminos
        watch` retries it; then it is ("refused", 503)."""
        not_ready_until = None
        while True:
            conn = bridge._UnixConnection(self.path, CONNECT_WAIT)
            try:
                if not self.stream(conn):
                    return
            finally:
                conn.close()
            now = time.monotonic()
            not_ready_until = not_ready_until or now + NOT_READY_WINDOW
            if now >= not_ready_until or self.closing.is_set():
                self.put(("refused", 503))
                return
            time.sleep(0.1)

    def stream(self, conn):
        """One GET /events: True when it was answered 503 (try again), False
        once its fate is put."""
        try:
            try:
                conn.connect()
            except OSError as e:
                self.put(("unavailable", str(e)))
                return False
            # Held here: the response to a `Connection: close` request takes
            # the socket from `conn`, which forgets it.
            self.sock = conn.sock
            if self.closing.is_set():
                self.sock.shutdown(socket.SHUT_RDWR)
            conn.request("GET", "/events")
            resp = conn.getresponse()
            if resp.status == 503:
                return True
            if resp.status != 200:
                self.put(("refused", resp.status))
                return False
            self.sock.settimeout(None)
            while True:
                line = resp.readline()
                if not line:
                    self.put(("closed", "the bridge ended the stream"))
                    return False
                if line.strip():
                    self.put(("line", json.loads(line)))
        except (OSError, ValueError, http.client.HTTPException) as e:
            self.put(("closed", "closed here" if self.closing.is_set() else str(e) or repr(e)))
            return False

    def close(self):
        self.closing.set()
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


# ------------------------------------------------------------- one subscription


class Subscription:
    """One DX4 subscription: the transcript of one loop of a session (main
    when `agent` is None) joined with the bridge's stream (`reader`, None
    without a bridge). `pump` returns the DX4 messages now due, in order."""

    def __init__(self, project, machine, session, agent, sub, locate, reader, presence, alive,
                 clock=time.monotonic, transcripts=None, wake=lambda: None, disk=None):
        self.project, self.machine, self.session, self.agent, self.sub = project, machine, session, agent, sub
        self.locate = locate          # () → the session's main transcript path, "" while there is none
        self.reader = reader
        self.presence = presence      # () → DX4 presence body
        self.alive = alive            # () → whether the session's process runs
        self.clock = clock
        self.transcripts = transcripts or TRANSCRIPTS
        self.wake = wake              # () → the uplink ticks soon: a worker answered
        self.loop = agent or "main"   # the cut's key for this transcript's loop
        self.n = None                 # the next message's n, once the snapshot is out
        self.ended = False
        self.opened = clock()
        self.snap = None              # the bridge's snapshot line
        self.snapped_at = None
        self.main = ""
        self.next_locate = 0.0
        self.tail = Tail()
        self.source = None            # the Transcript whose worker reads this one's bulk, once asked
        self.answers = queue.Queue()  # the worker's answers, in the order asked
        self.building = False         # an open's build is asked and not answered yet
        self.over = False             # the session ended and what it flushed is drawn: transcript-only, idle
        self.emitted = {}             # uuid → "history" | "named" | "unnamed"
        self.pool = collections.OrderedDict()  # uuid → [row, first seen]: past the cut, not yet emitted, disk order
        self.noticed = {}             # uuid → when: notices whose row is not emitted yet
        self.upto = {}                # (turnId, agentId, step) → the snapshot's watermark
        self.held = set()             # (turnId, agentId, step, index): blocks whose text the subscriber holds
        self.steps = set()            # (turnId, agentId, step): model requests open, whose step-end is still due
        self.stream_over = False      # the bridge's stream ended with the session
        self.ending_at = None
        # What the session runs (DX4's widened `subagents`): this loop's jobs
        # ledger, fed every row the Tail reads; the bridge's agent state (None
        # without a bridge), kept after its stream ends, since its spawn
        # records still say what they said; the disk facts, looked at on the
        # worker every METAS_EVERY; and the body last sent.
        self.disk = disk or DISK
        self.ledger = jobs.Ledger()
        self.agents = None            # agentId → the bridge's state of it: its spawn's fields, `running`
        self.facts = Facts()
        self.looking = False          # a look at the disk is asked and not answered yet
        self.looks = 0                # looks answered, all told
        self.next_look = 0.0
        self.body = None
        self.dirty = False            # something the body is derived from changed
        self.was_alive = None

    @property
    def bridged(self):
        return self.reader is not None

    def carried(self, agent):
        return self.agent is None or agent == self.agent

    def mine(self, agent):
        return (agent or None) == self.agent

    def message(self, kind, body):
        if self.n is None:
            n = 0
        else:
            n = self.n
            self.n += 1
        return envelope(self.project, self.machine, self.session, kind, self.sub, n, body)

    def path(self, now):
        """This loop's transcript, once the session's is found."""
        if not self.main and now >= self.next_locate:
            self.next_locate = now + LOCATE_EVERY
            self.main = self.locate() or ""
        if not self.main:
            return ""
        return self.main if self.agent is None else agent_path(self.main, self.agent)

    def close(self):
        if self.reader is not None:
            self.reader.close()
        if self.source is not None:
            self.transcripts.release(self.source)
            self.source = None

    def ask(self, path, read):
        """`read(transcript)` on the transcript's worker; its answer, (kind,
        value), comes back through `answers`. Any answer but "waiting" wakes
        the uplink; a Reset is ("reset", why), any other failure ("failed",
        why)."""
        if self.source is None:
            self.source = self.transcripts.acquire(path)
        answers, wake = self.answers, self.wake

        def job(t):
            try:
                answer = read(t)
            except Reset as e:
                answer = ("reset", str(e))
            except Exception as e:  # noqa: BLE001 — the subscription ends with it, not the worker
                answer = ("failed", "reading the transcript failed: %r" % e)
            answers.put(answer)
            if answer[0] != "waiting":
                wake()

        self.source.submit(job)

    def end(self, reason, message=None):
        if self.ended:
            return []
        self.ended = True
        self.close()
        return [self.message("end", {"reason": reason, **({"message": message} if message else {})})]

    # ---------------------------------------------------- the pump

    def pump(self):
        out = []
        if self.ended:
            return out
        now = self.clock()
        try:
            if self.n is None and not self.open(now, out):
                return out
            self.drain(now, out)
            if not self.ended:
                self.read(now)
                self.release(now, out)
            if not self.ended:
                self.answer(out)
            if not self.ended:
                self.subagents(now, out)
                self.finish(now, out)
        except Reset as e:
            out += self.end("discontinuity", str(e))
        return out

    def open(self, now, out):
        """The snapshot, once the bridge's (if any) is in and its cut's row
        is on disk; False while it waits."""
        if self.bridged and self.snap is None:
            while self.snap is None:
                try:
                    item = self.reader.items.get_nowait()
                except queue.Empty:
                    break
                if item[0] == "line" and isinstance(item[1], dict) and item[1].get("type") == "snapshot":
                    self.snap, self.snapped_at = item[1], now
                    self.agents = {a["agentId"]: dict(a) for a in self.snap.get("agents") or ()
                                   if isinstance(a, dict) and isinstance(a.get("agentId"), str)}
                elif item[0] == "unavailable":
                    self.reader = None   # no bridge after all: the transcript alone
                    break
                else:
                    why = {"refused": "the bridge refused the subscription (%s)" % (item[1],),
                           "closed": "the bridge's stream ended before its snapshot"}.get(item[0], "the bridge's stream began without a snapshot")
                    out += self.end("discontinuity", why)
                    return False
            if self.bridged and self.snap is None:
                if now - self.opened > OPEN_WAIT:
                    out += self.end("discontinuity", "the bridge sent no snapshot")
                return False
        # The history is read on the transcript's worker (build): asked once,
        # and again while the cut's row is not on disk. A null cut (or one
        # that does not name this loop) with a bridge: the loop had no rows
        # when the module loaded, and none was noticed since — the seed
        # covers every older row. Empty history; all rows live.
        cut = self.cut()
        path = self.path(now)
        if not self.building:
            if not path:
                return self.unlocated(now, cut, out)
            self.building = True
            bridged, looked = self.bridged, self.looker()

            def opening(t):
                kind, built = build(t, cut, bridged)
                if kind == "built":
                    built.facts = looked()
                return kind, built

            self.ask(path, opening)
            return False
        try:
            kind, built = self.answers.get_nowait()
        except queue.Empty:
            return False
        self.building = False
        if kind == "waiting":
            if now - self.snapped_at > NOTICE_WAIT:
                out += self.end("discontinuity", "the snapshot's cut, row %s, never reached the transcript" % cut)
            return False
        if kind != "built":
            out += self.end("discontinuity" if kind == "reset" else "error", built)
            return False
        if built.ino is None and not self.alive():
            out += self.end("session-ended", "no transcript of the session on this machine")
            return False
        self.tail.path, self.tail.offset, self.tail.ino = self.source.path, built.offset, built.ino
        self.ledger, self.facts = built.ledger, built.facts
        self.emitted = built.emitted
        for u, row in built.past:
            if u not in self.emitted and u not in self.pool:
                self.pool[u] = [row, now]
        return self.snapshot(now, built.shown, built.more, out)

    def unlocated(self, now, cut, out):
        """The open while the session's transcript is not found: with no
        process, `session-ended` (the machine does not hold it); a cut to
        wait for, as long as a cut row may take; else an empty snapshot,
        and its rows as they come."""
        if not self.alive():
            out += self.end("session-ended", "no transcript of the session on this machine")
            return False
        if cut is not None:
            if now - self.snapped_at > NOTICE_WAIT:
                out += self.end("discontinuity", "the snapshot's cut, row %s, never reached the transcript" % cut)
            return False
        return self.snapshot(now, [], False, out)

    def snapshot(self, now, shown, more, out):
        """The snapshot message, history's newest rows `shown` (newest
        first); True: the subscription is open."""
        streaming = []
        if self.bridged:
            for e in self.snap.get("streaming") or []:
                if not isinstance(e, dict) or not self.carried(e.get("agentId")):
                    continue
                key = (e.get("turnId"), e.get("agentId"), e.get("step"))
                self.upto[key] = e.get("upTo") if isinstance(e.get("upTo"), int) else -1
                self.steps.add(key)
                for b in e.get("blocks") or []:
                    if isinstance(b, dict):
                        self.held.add(key + (b.get("index"),))
                streaming.append(e)
        self.next_look = now + METAS_EVERY
        self.was_alive = self.alive()
        self.body = self.derive(self.was_alive)
        body = {"rows": shown, "more": more, **self.body, "presence": self.presence(), "streaming": streaming}
        if self.agent is None:
            body["usage"] = usage_of(self.snap.get("usage")) if self.bridged else None
        out.append(self.message("snapshot", body))
        self.n = 1
        return True

    def cut(self):
        if not self.bridged:
            return None
        cut = self.snap.get("cut")
        value = cut.get(self.loop) if isinstance(cut, dict) else None
        return value if isinstance(value, str) and value else None

    def drain(self, now, out):
        while self.bridged and not self.ended:
            try:
                item = self.reader.items.get_nowait()
            except queue.Empty:
                return
            if item[0] == "line":
                if isinstance(item[1], dict):
                    self.event(item[1], now, out)
            elif self.alive():
                out += self.end("discontinuity", "the bridge's stream ended (%s)" % (item[1],))
            else:
                self.reader = None
                self.stream_over = True

    def event(self, e, now, out):
        kind, agent = e.get("type"), e.get("agentId")
        if kind == "chunk":
            if not self.carried(agent):
                return
            key = (e.get("turnId"), agent, e.get("step"))
            index = e.get("chunkIndex")
            if key in self.upto and isinstance(index, int) and index <= self.upto[key]:
                return
            chunk = e.get("chunk")
            if isinstance(chunk, dict):
                self.held.add(key + (chunk.get("index"),))
            self.steps.add(key)
            out.append(self.message("chunk", {"turnId": e.get("turnId"), "agentId": agent, "step": e.get("step"),
                                              "chunkIndex": index, "chunk": chunk}))
        elif kind in ("block-row", "row-seen"):
            if not self.carried(agent):
                return
            if self.mine(agent):
                self.notice(e, now, out)
            elif kind == "block-row":
                out.append(self.message("block-row", block_row(e)))
        elif kind == "step" and self.carried(agent):
            # DX4 step-end: the model request ended. DX5 delivers a step's
            # block-rows before its end, so in DX5's order it follows them.
            key = (e.get("turnId"), agent, e.get("step"))
            if e.get("phase") == "start":
                self.steps.add(key)
            elif e.get("phase") == "end":
                self.steps.discard(key)
                out.append(self.message("step-end", {"turnId": key[0], "agentId": agent, "step": key[2]}))
        elif kind == "turn" and e.get("phase") == "complete":
            # A turn that ends cuts off its steps whose end never came (an abort).
            cut_off = [k for k in self.steps if k[0] == e.get("turnId")]
            for key in sorted(cut_off, key=lambda k: (str(k[1]), k[2] if isinstance(k[2], int) else -1)):
                self.steps.discard(key)
                out.append(self.message("step-end", {"turnId": key[0], "agentId": key[1], "step": key[2]}))
        elif kind == "usage":
            if self.agent is None:
                out.append(self.message("usage", usage_of(e)))
        elif kind == "agent" and isinstance(agent, str) and agent:
            # DX5's spawn or stop, folded in as the child folds it into the
            # `agents` its snapshot carries; any loop's, since an agent's
            # entry reads its parents'.
            a = self.agents.setdefault(agent, {"agentId": agent})
            a.update({k: v for k, v in e.items() if k not in ("type", "phase", "n")})
            a["running"] = e.get("phase") != "stop"
            self.dirty = True
        elif kind in ("gap", "resync", "snapshot"):
            out += self.end("discontinuity", "the bridge's stream %s" % (
                "lost events" if kind == "gap" else "started over"))

    def notice(self, e, now, out):
        u = e.get("uuid")
        if not isinstance(u, str) or not u:
            return
        kind = e.get("type")
        was = self.emitted.get(u)
        if was is not None or u in self.noticed:
            if kind == "row-seen":
                return
            block = (e.get("turnId"), e.get("agentId"), e.get("step"), e.get("index"))
            if was == "unnamed":
                out += self.end("discontinuity", "row %s was drawn before the block-row that names it" % u)
            elif was == "history" and block in self.held:
                out += self.end("discontinuity", "row %s, in the snapshot, settles a block still drawn" % u)
            return
        if kind == "block-row":
            out.append(self.message("block-row", block_row(e)))
        self.noticed[u] = now

    def read(self, now):
        for u, row in self.tail.read(self.path(now)):
            self.ledger.add(row)
            self.dirty = True
            if u not in self.emitted and u not in self.pool:
                self.pool[u] = [row, now]

    def release(self, now, out):
        """The rows past the cut, strictly in disk order: the first goes once
        its own notice came, or a notice for any later row of the loop (one
        whose row is not on disk yet is later than every row that is), or
        after UNNAMED_WAIT with neither; every later row waits behind it. A
        notice whose row is not on disk within NOTICE_WAIT ends the
        subscription."""
        wait = UNNAMED_WAIT if self.bridged else 0.0
        order = list(self.pool)
        upto = len(order) - 1 if any(u not in self.pool for u in self.noticed) else \
            max((i for i, u in enumerate(order) if u in self.noticed), default=-1)
        for i, u in enumerate(order):
            if i > upto and now - self.pool[u][1] < wait:
                break
            out.append(self.release_row(u))
        for u, at in self.noticed.items():
            if now - at > NOTICE_WAIT:
                out += self.end("discontinuity", "row %s, named by the bridge, did not reach the transcript "
                                                 "within %g s" % (u, NOTICE_WAIT))
                return

    def release_row(self, u):
        """The row message for a row past the cut; it counts as named when its
        own notice came."""
        row = self.pool.pop(u)[0]
        self.emitted[u] = "named" if self.noticed.pop(u, None) is not None else "unnamed"
        return self.message("row", {"row": row, "agentId": self.agent})

    def subagents(self, now, out):
        """DX4 `subagents` whenever the body derived changes: from a row the
        Tail read, the bridge's agent state, the disk facts (looked at on the
        worker every METAS_EVERY), or the process going — then every entry is
        derived again, so a `running` held from the bridge turns `exited` as a
        cold open of the ended session would have it."""
        alive = self.alive()
        if alive != self.was_alive:
            self.was_alive, self.dirty = alive, True
        if now >= self.next_look and not self.looking:
            path = self.path(now)
            if path and self.main:
                self.looking, self.next_look = True, now + METAS_EVERY
                looked = self.looker()
                self.ask(path, lambda t: ("facts", looked()))
        if self.dirty:
            self.dirty = False
            body = self.derive(alive)
            if body != self.body:
                self.body = body
                out.append(self.message("subagents", body))

    def looker(self):
        """The disk facts' look, to run on the worker: what it needs of this
        subscription taken now, on the main thread."""
        disk, main, agent = self.disk, self.main, self.agent
        spawns = {k: (a.get("parentAgentId"), a.get("toolUseId") if isinstance(a.get("toolUseId"), str) else None)
                  for k, a in (self.agents or {}).items()}
        tasks = list(self.ledger.jobs) if agent is not None else []
        return lambda: look(disk, main, agent, spawns, tasks)

    def derive(self, alive):
        """The widened body: for a main subscription the session's tree, its
        loop's jobs and MCP names; for an agent's, its own entry, derived from
        the loop that ran it (the chain of loops above it on disk), and its own
        loop's jobs and MCP names — two derivations (DC8's Decision Log)."""
        f, bridge = self.facts, list(self.agents.values()) if self.agents is not None else None
        if self.agent is None:
            return jobs.derive(self.ledger, f.metas, bridge=bridge, files=f.files, parents=f.parents,
                               session_running=alive)
        chain = jobs.derive(f.main or jobs.Ledger(), f.metas, bridge=bridge, files=f.files, parents=f.parents,
                            session_running=alive)
        own = jobs.derive(self.ledger, [], bridge=None, files={}, parents={}, session_running=alive, also=f.stops)
        return {**own, "subagents": [e for e in chain["subagents"] if e["agentId"] == self.agent]}

    def finish(self, now, out):
        """Once the session is not running: what it still flushes is drawn for
        END_GRACE, then the subscription goes on transcript-only and idle, no
        `end` sent: it answers pages until it is unsubscribed, the stream
        ends, or a discontinuity ends it (a bridge answering for the session
        again: Plane.tick). The bridge's notices bind no more."""
        if self.over:
            return
        if self.ending_at is None:
            if self.stream_over or not self.alive():
                self.ending_at = now + END_GRACE
            return
        if now < self.ending_at:
            return
        for u in list(self.pool):
            out.append(self.release_row(u))
        self.over = True
        self.noticed.clear()
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    # ---------------------------------------------------- on request

    def page(self, before, limit):
        """DX4 `rows`: the rows of this transcript older than `before`, newest
        first, as many as fit and at most `limit` — read on the transcript's
        worker, answered on a later pump (`answer`). Nothing read here yet:
        no older rows."""
        if self.ended or self.n is None:
            return []
        if self.tail.ino is None:
            return [self.message("rows", {"rows": [], "before": before, "more": False})]
        ino = self.tail.ino
        self.ask(self.tail.path, lambda t: page_of(t, ino, before, limit))
        return []

    def answer(self, out):
        """What the worker answered, in the order asked — pages, `output`s,
        looks at the disk; a transcript replaced under a page is a
        discontinuity."""
        while not self.ended:
            try:
                kind, value = self.answers.get_nowait()
            except queue.Empty:
                return
            if kind == "page":
                out.append(self.message("rows", value))
            elif kind == "output":
                out.append(self.message("output", value))
            elif kind == "facts":
                self.facts, self.looking, self.dirty = value, False, True
                self.looks += 1
            else:
                out += self.end("discontinuity" if kind == "reset" else "error", value)

    def output(self, task, tail, cwds):
        """DX4 `output` for task `task`, its last `tail` bytes: what this
        loop's rows say of the task taken now, the file read on the
        transcript's worker under the session's canonical roots (`cwds` its
        working directories as the machine knows them), answered on a later
        pump. An idle subscription answers too."""
        if self.ended or self.n is None:
            return []
        said = jobs.Ledger()   # only what output_answer reads, so the worker shares nothing with this thread
        if task in self.ledger.known:
            said.known[task] = True
        if task in self.ledger.outputs:
            said.outputs[task] = self.ledger.outputs[task]
        path = self.tail.path or self.path(self.clock())
        if not path:   # no transcript read: no row names any task
            return [self.message("output", jobs.output_answer({"taskId": task, "tail": tail}, said, self.session, []))]
        session, main = self.session, self.main

        def read(_t):
            return "output", jobs.output_answer({"taskId": task, "tail": tail}, said, session,
                                                output_roots(session, main, cwds))

        self.ask(path, read)
        return []

    def diffed(self, body):
        if self.ended or self.n is None:
            return []
        return [self.message("diff", body)]


def block_row(e):
    return {"uuid": e.get("uuid"), "turnId": e.get("turnId"), "agentId": e.get("agentId"), "step": e.get("step"),
            "index": e.get("index")}


def usage_of(e):
    """DX4 usage: the bridge's usage event's context and cost; None for none."""
    if not isinstance(e, dict):
        return None
    return {"context": e.get("context"), "cost": e.get("cost")}


# ------------------------------------------------------------- the diff


def working_diff(cwd):
    """DX4 `diff`: the session's working tree against its base branch — the
    remote's default branch, else `main` or `master` — from where HEAD left
    it; untracked files as new. Read only: git takes no optional lock."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}

    def git(*args):
        return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.quotepath=off", "-C", cwd, *args],
                              capture_output=True, timeout=GIT_TIMEOUT, env=env)

    if not (cwd and os.path.isdir(cwd)) or git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return {"base": "", "text": ""}
    head = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    base = head.stdout.decode().strip() if head.returncode == 0 else ""
    if not base:
        base = next((b for b in ("main", "master")
                     if git("rev-parse", "--verify", "--quiet", "refs/heads/" + b).returncode == 0), "HEAD")
    fork = git("merge-base", "HEAD", base)
    since = fork.stdout.decode().strip() if fork.returncode == 0 else base
    text = git("diff", "--no-color", "--no-ext-diff", since).stdout
    for name in git("ls-files", "--others", "--exclude-standard", "-z").stdout.split(b"\0"):
        if not name or len(text) > DIFF_MAX:
            continue
        text += git("diff", "--no-color", "--no-ext-diff", "--no-index", "--", "/dev/null",
                    name.decode("utf-8", "surrogateescape")).stdout
    if len(text) > DIFF_MAX:
        text = text[:DIFF_MAX] + b"\n[the diff goes on past %d bytes: cut here]\n" % DIFF_MAX
    return {"base": base, "text": text.decode("utf-8", "replace")}


# ------------------------------------------------------------- the engine's records


class Records:
    """The engine's session registry, read only where it changed: the record
    of every session whose process runs, by session id."""

    def __init__(self, clock=time.monotonic):
        self.files = {}      # path → (mtime_ns, size, record)
        self.same = {}       # (pid, procStart) → (whether the pid is that process, when that was read)
        self.clock = clock

    def scan(self):
        live = {}
        seen = set()
        for path in glob.glob(os.path.join(glob.escape(sminos.home_dir()), ".claude", "sessions", "*.json")):
            seen.add(path)
            try:
                st = os.stat(path)
            except OSError:
                continue
            held = self.files.get(path)
            if held is None or held[:2] != (st.st_mtime_ns, st.st_size):
                try:
                    with open(path) as f:
                        rec = json.load(f)
                except (OSError, ValueError):
                    rec = None
                held = self.files[path] = (st.st_mtime_ns, st.st_size, rec if isinstance(rec, dict) else None)
            rec = held[2]
            sid = rec.get("sessionId") if rec else None
            if isinstance(sid, str) and self.running(rec):
                old = live.get(sid)
                if old is None or (rec.get("updatedAt") or 0) > (old.get("updatedAt") or 0):
                    live[sid] = rec
        for path in set(self.files) - seen:
            del self.files[path]
        held = {(r.get("pid"), r.get("procStart")) for _, _, r in self.files.values() if r}
        self.same = {k: v for k, v in self.same.items() if k in held}
        return live

    def running(self, rec):
        """The record's pid is alive and is the process the record describes.
        The identity (the process's start time against the record's, read
        afresh) is read again every IDENTITY_EVERY, and at once once the pid
        is seen dead: a pid reused between two polls, alive at both, is found
        out within that bound. Polls between reads cost an os.kill each."""
        pid = rec.get("pid")
        if not sminos.pid_alive(pid):
            self.same = {k: v for k, v in self.same.items() if k[0] != pid}
            return False
        key, now = (pid, rec.get("procStart")), self.clock()
        held = self.same.get(key)
        if held is None or now - held[1] >= IDENTITY_EVERY:
            held = self.same[key] = (sminos.same_process(rec, fresh=True), now)
        return held[0]


def record_body(rec):
    return {k: rec[k] for k in RECORD_FIELDS if k in rec} if rec is not None else None


class Bridges:
    """Whether each session's bridge answers (DX5's `GET /status` with its
    session id), learned off the uplink's thread: `answers` returns what is
    known at once and starts a probe when the socket changed or the answer is
    BRIDGE_RECHECK old, one at a time per session, each on a thread of its
    own; a probe whose answer differs wakes the uplink. A bridge that listens
    and never answers holds only its own probe. Kept across streams."""

    def __init__(self):
        self.lock = threading.Lock()
        self.held = {}            # session → [socket inode, answered, probed at, probing]
        self.wake = lambda: None

    def answers(self, sid, now):
        path = bridge.endpoint(sid)
        try:
            ino = os.stat(path).st_ino
        except OSError:
            with self.lock:
                self.held.pop(sid, None)
            return False
        with self.lock:
            h = self.held.setdefault(sid, [ino, False, None, False])
            if not h[3] and (h[0] != ino or h[2] is None or now - h[2] >= BRIDGE_RECHECK):
                h[3] = True
                threading.Thread(target=self.probe, args=(sid, path, ino, now), name="plane-probe",
                                 daemon=True).start()
            return h[1]

    def probe(self, sid, path, ino, now):
        answered = False
        try:
            status, body = bridge.request(path, "GET", "/status", timeout=PROBE_TIMEOUT)
            answered = status == 200 and isinstance(body, dict) and body.get("session") == sid
        except (OSError, ValueError, http.client.HTTPException):
            pass
        with self.lock:
            h = self.held.get(sid)
            if h is None:
                return
            changed = h[1] != answered
            h[:] = [ino, answered, now, False]
        if changed:
            self.wake()

    def known(self, sid):
        with self.lock:
            h = self.held.get(sid)
            return bool(h and h[1])


def tombstone_path():
    return os.path.join(sminos.root(), "daemon", TOMBSTONE_FILE)


def tombstone_marks():
    """Project id → the time of the last read whose leavers the hub took
    (Plane.accepted); {} when none is kept or the file is unreadable, which
    says every leaver again."""
    try:
        with open(tombstone_path()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)} \
        if isinstance(d, dict) else {}


# ------------------------------------------------------------- the plane


class Plane:
    """One stream's session plane: the presence it has published, and the
    subscriptions it serves. Made anew with every stream; `close` lets the
    readers go."""

    def __init__(self, machine, wake, bridges=None, transcripts=None, disk=None):
        self.machine = machine
        self.wake = wake
        self.bridges = bridges or Bridges()   # kept across streams by the uplink: no answer is relearned
        self.bridges.wake = wake
        self.transcripts = transcripts or TRANSCRIPTS   # the process's: no index is rebuilt across streams
        self.disk = disk or DISK                        # and no meta or agent file read again unchanged
        self.records = Records()
        self.live = {}            # session → its engine record, as last scanned
        self.next_scan = 0.0
        self.here = {}            # project id → {session: cwd}: the sessions that joined it from this machine
        self.members = {}         # project id → {session}: its local members, whose presence is published
        self.left = {}            # project id → {session: when it left}: those of `here` no member now
        self.read_at = {}         # project id → when its members were last read (wall clock)
        self.tombstoned = {}      # project id → the read whose leavers a connect said, until the hub takes them
        self.wall = time.time
        self.sent = {}            # (project id, session) → presence body last sent
        self.subs = {}            # sub → Subscription
        self.diffs = queue.Queue()
        self.read_for = None      # the running sessions the members were last read for
        self.next_members = 0.0

    def close(self):
        for s in self.subs.values():
            s.close()
        self.subs.clear()

    # ---------------------------------------------------- who is here

    def refresh(self, project):
        """The project's sessions on this machine, from its log as this
        machine reconciles it (sminos calls: the main thread's)."""
        self.read_at[project.id] = self.wall()   # before the read: whoever leaves after it is newer than this
        view = sminos.view_of(project, titles=False)
        here = {}
        for sid, r in view.info.items():
            j = (r or {}).get("joined") or {}
            machine = str(j.get("machine") or "")
            if j and (not machine or sminos.is_self(machine, sid)):
                here[sid] = str(j.get("cwd") or "")
        self.here[project.id] = here
        self.members[project.id] = members = {m.session for m in view.members if m.local and m.session}
        self.left[project.id] = {sid: sminos._ts_epoch((view.info[sid].get("latest") or {}).get("ts"))
                                 for sid in here if sid not in members}

    # ---------------------------------------------------- presence

    def presence_of(self, sid, now):
        return {"record": record_body(self.live.get(sid)), "bridge": self.bridges.answers(sid, now)}

    def presence(self, pid, force=False, now=None):
        """DX4 presence for the project's sessions whose presence changed
        (every one when forced, after a connect); a member gone from the
        project is said once more as not running, then forgotten.

        The hub keeps a session's presence across connections, with no
        expiry, and this plane is new with its stream: when forced, each
        session that joined from here and is no member now is said as not
        running too, so one that ended while no stream was open, however
        long, is not left present at the hub. Not every session that ever
        ended here: only those that left (their latest membership event,
        which this machine writes when it sees the process gone) since the
        last read whose leavers the hub took (`accepted`), less
        TOMBSTONE_MARGIN; every one when no such read is kept (a first run).
        One whose leaving has no time is said every time."""
        now = time.monotonic() if now is None else now
        out = []
        if force:
            self.live = self.records.scan()
            mark = tombstone_marks().get(pid)
            since = None if mark is None else mark - TOMBSTONE_MARGIN
            for sid, at in sorted(self.left.get(pid, {}).items()):
                if since is None or at is None or at >= since:
                    out.append(envelope(pid, self.machine, sid, "presence", None, None,
                                        {"record": None, "bridge": False}))
            if pid in self.read_at:
                self.tombstoned[pid] = self.read_at[pid]
        for sid in sorted(self.members.get(pid, ())):
            body = self.presence_of(sid, now)
            if force or self.sent.get((pid, sid)) != body:
                self.sent[(pid, sid)] = body
                out.append(envelope(pid, self.machine, sid, "presence", None, None, body))
        for key in [k for k in self.sent if k[0] == pid and k[1] not in self.members.get(pid, ())]:
            body = self.sent.pop(key)
            if body["record"] is not None or body["bridge"]:
                out.append(envelope(pid, self.machine, key[1], "presence", None, None,
                                    {"record": None, "bridge": False}))
        return out

    def accepted(self, pid):
        """The hub answered 200 to the POST that carried a connect's presence
        for the project: its leavers are said, so the next connect says only
        those that left since that read. Kept across restarts; a mark that
        cannot be written leaves the old one, which says more, never less."""
        at = self.tombstoned.pop(pid, None)
        if at is None:
            return
        path = tombstone_path()
        marks = tombstone_marks()
        marks[pid] = at   # the latest taken read covers whoever left before it
        try:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            sminos.write_json(path, marks)
        except OSError as e:
            log("the presence mark of %s could not be kept (%s): the next connect says its leavers again" % (pid, e))

    # ---------------------------------------------------- the hub's frames

    def subscribe(self, project, frame_):
        sid, agent, sub = frame_.get("session"), frame_.get("agentId"), frame_.get("sub")
        if not isinstance(sub, str) or not sub:
            log("a subscribe without a sub: passed by")
            return []
        out = self.unsubscribe(sub, quiet=True)

        def refuse(message):
            return out + [envelope(project.id, self.machine, sid if isinstance(sid, str) else "", "end", sub, 0,
                                   {"reason": "error", "message": message})]

        if not (isinstance(sid, str) and sminos.UUID_RE.match(sid)):
            return refuse("session is a session id")
        if not (agent is None or (isinstance(agent, str) and AGENT_ID.match(agent))):
            return refuse("agentId is null or a subagent's id")
        if sid not in self.here.get(project.id, {}):
            sminos.forget_caches()
            self.refresh(project)
            if sid not in self.here.get(project.id, {}):
                return refuse("no session %s of %s on this machine" % (sid, project.name))
        self.live = self.records.scan()
        reader = None
        if os.path.exists(bridge.endpoint(sid)):
            # The reader finds out whether it answers, off this thread: a
            # socket nobody listens on is "unavailable", and the
            # subscription is served from the transcript alone.
            reader = BridgeReader(bridge.endpoint(sid), self.wake)
            reader.start()
        self.subs[sub] = Subscription(
            project.id, self.machine, sid, agent, sub, locate=lambda: sminos.transcript_path(sid), reader=reader,
            presence=lambda: self.presence_of(sid, time.monotonic()), alive=lambda: self.running(sid),
            transcripts=self.transcripts, wake=self.wake, disk=self.disk)
        return out + self.pump_one(sub)

    def running(self, sid):
        rec = self.live.get(sid)
        return rec is not None and sminos.pid_alive(rec.get("pid"))

    def unsubscribe(self, sub, quiet=False):
        s = self.subs.pop(sub, None)
        if s is None:
            return []
        if quiet:
            s.close()
            return []
        return s.end("unsubscribed")

    def rows(self, frame_):
        s = self.subs.get(frame_.get("sub"))
        before, limit = frame_.get("before"), frame_.get("limit")
        if s is None or not isinstance(before, str) or type(limit) is not int or limit < 1:
            return []
        return s.page(before, min(limit, 1000))

    def output(self, frame_):
        """DX2 `output`: answered as DX4 `output` on the sub, from the task's
        file under the session's canonical roots — derived from the working
        directories this machine knows for the session (the one it joined the
        project from, and its engine record's while it runs). A frame out of
        DX3's form is passed by, as the hub refuses it."""
        s = self.subs.get(frame_.get("sub"))
        task, tail = frame_.get("taskId"), frame_.get("tail")
        if s is None or not (isinstance(task, str) and TASK_ID.fullmatch(task)) \
                or type(tail) is not int or not 1 <= tail <= OUTPUT_TAIL_MAX:
            return []
        cwds = [self.here.get(s.project, {}).get(s.session), (self.live.get(s.session) or {}).get("cwd")]
        return s.output(task, tail, cwds)

    def diff(self, frame_):
        s = self.subs.get(frame_.get("sub"))
        if s is None or s.agent is not None:
            return []
        cwd = str((self.live.get(s.session) or {}).get("cwd") or self.here.get(s.project, {}).get(s.session) or "")

        def run(sub=s.sub):
            try:
                body = working_diff(cwd)
            except (OSError, subprocess.SubprocessError) as e:
                body = {"base": "", "text": "", "error": str(e)}
            self.diffs.put((sub, body))
            self.wake()

        threading.Thread(target=run, name="plane-diff", daemon=True).start()
        return []

    # ---------------------------------------------------- between frames

    def pump_one(self, sub):
        s = self.subs.get(sub)
        if s is None:
            return []
        out = s.pump()
        if s.ended:
            del self.subs[sub]
        return out

    def tick(self, projects):
        """Everything now due for the projects open on the stream ({id:
        project}): presence that changed, each subscription's messages,
        finished diffs. Envelopes, in the order to post them. The members are
        read again — a reconciling read of each log, which reads the start
        time of every live session — when a session came or went, and every
        MEMBERS_EVERY for what only the log changes (a seat retired)."""
        now = time.monotonic()
        out = []
        if now >= self.next_scan:
            self.next_scan = now + PRESENCE_EVERY
            self.live = self.records.scan()
        if set(self.live) != self.read_for or now >= self.next_members:
            sminos.forget_caches()  # the engine's records as they are now, not as sminos last read them
            for project in projects.values():
                self.refresh(project)
            self.read_for, self.next_members = set(self.live), now + MEMBERS_EVERY
        for pid in sorted(projects):
            out += self.presence(pid, now=now)
        for sub, s in list(self.subs.items()):
            if not s.bridged and not s.ended and s.n is not None and self.bridges.known(s.session) \
                    and self.running(s.session):
                # A bridge answers now for a session served from its
                # transcript alone: a fresh subscription streams.
                out += s.end("discontinuity", "the session's bridge answers now")
            else:
                out += s.pump()
            if s.ended:
                self.subs.pop(sub, None)
        while True:
            try:
                sub, body = self.diffs.get_nowait()
            except queue.Empty:
                break
            s = self.subs.get(sub)
            if s is not None:
                out += s.diffed(body)
        return out
