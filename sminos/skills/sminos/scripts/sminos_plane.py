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

The build — the index, the loop's jobs ledger and its chain — is saved under
daemon/plane/ as it is first made and as it grows, as it leaves memory, and
at the uplink's stop, and a process that has not built a file loads it
while the file still holds, before the saved end, the very bytes it read (a
CRC-32 of that prefix), so a restart costs an open a load, not a parse. The
live members of the stream's open projects have their main transcripts held
and extended in the background (Warmer): a warm job runs only while its
worker has no foreground job — an open's build, a page, a look, an
`output` — queued, at most one per transcript and WARM_PARALLEL across the
process, round-robin; so a live session's first open is warm and never
waits behind another's. Every job shares the process's GIL with the main
thread, so the first round begins WARM_EVERY after the warmer's first tick
and no warm job starts while an open awaits its snapshot.
The look at the disk facts is off the open's path: the snapshot goes with
the facts as they stand, the look is asked right after it, and the first
`subagents` carries what it found.

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
`subagents`, `usage`, each numbered, and `end` (a `chunk` carries the bridge's
stamp `t`, so the web can say how long one took to be drawn). Rows come from the transcript on disk and everything live from the
bridge's DX5 stream, so the two are joined in one order — the disk's (DX5's
row order, composite cd2667d8):

- every row the mod observes gets one notice on the bridge's stream once the
  engine has taken it, so within a loop notice order is write order and a
  notice may trail the flush: `block-row` for a response row, `row-seen` for
  any other;
- the bridge's snapshot carries `cut`, per loop the last notice it applied,
  seeded at the module's load with the loop's last row then: history is the
  loop's rows up to and including it when that row is on disk, and every row
  on disk when it is not — rows reach disk in notice order within a loop, so
  nothing past a row not yet flushed is flushed either — and the snapshot
  waits for nothing; a null cut (or a loop it does not name) means the loop
  had no rows at load, so its history is empty and every row of it is live;
- a block stays in the bridge's `streaming` after its `block-row`, carrying
  `uuid` (its row) and `namedAt`, until its step ends, since the engine
  flushes a message's rows at its end: the snapshot carries such a block
  while its row is not on disk (its block-row the first messages after the
  snapshot, its row awaited as a notice of its step), and drops it from
  this loop's entries once its row is in history; a block of another loop
  the subscription carries is kept and its block-row relayed. The cut's own
  row, not on disk at the snapshot, is awaited as a notice too, so it goes
  out as it lands; nothing drawn waits on it, so past its due it is
  forgotten rather than ending anything. A streaming block whose text
  passed the bridge's BLOCK_TAIL (65,536 characters: a huge tool input)
  carries only its tail there, marked `truncated: true`, which the snapshot
  passes on as it is: its chunks, and its row once it lands, are whole;
- that is for a bridge whose snapshot says `namedBlocks: true` (its child
  keeps named blocks and its mod's last resync declared it). Any other — a
  mod and child from before it, still running after the uplink was
  upgraded, which drop a block at its block-row, so its cut may name a row
  neither on disk nor carried — gets the wait from before: history waits for
  the cut's row to be on disk, a build asked again on each pump, and the
  subscription ends NOTICE_WAIT after the bridge's snapshot without it;
- live, each loop's rows go out strictly in disk order: a row past the cut
  is released by its own notice, by a notice for any later row of the loop,
  or UNNAMED_WAIT after it was first seen on disk with neither (rows written
  together go out together), and every later row waits behind it;
- a notice's row is due NOTICE_WAIT after the end of its loop's step that
  was open when the notice came (the `step` end, or its turn's `complete`
  cutting it off), or NOTICE_WAIT after the notice when none was (a prompt,
  a tool result between requests, a compaction's rows); a row not on disk
  by its due ends the subscription;
- a `row-seen` for a row already emitted is passed over; a `block-row` for a
  row already emitted as unnamed ends the subscription, whose fresh snapshot
  heals what would otherwise be drawn twice (the real child closes a step's
  pairing at its end, so this comes only from a notice later than the 2 s);
  so does one for a history row whose block the subscriber still holds,
  which the dropped history blocks rule out and is kept as a guard.

The live chain. The engine reads only the chain from a transcript's leaf; the
rows a branch left behind (an Esc's or a /rewind's, a response the engine
dropped) stay on disk. Each subscription follows its transcript's chain
(Chain: the build's, read with the index, then each row as it is released)
and marks what is off it, so a consumer can draw the conversation the engine
holds: the snapshot and every `rows` page carry `offChain`, the uuids of
their rows off the chain; a `row` carries `offChain` when it took rows off
(a branch's start: the rows it left behind; itself, when it is off), and
`onChain` when it put rows back on. Each is read off the subscription's own
chain as its message goes, so in message order the latest says.

Each open writes one daemon.log line (Subscription.noted): its outcome
after N s from the subscribe frame's arrival at the uplink's reader, then
where the time went — when the bridge's snapshot reached its reader and
when the open took it (the main thread's absence between), how the build
came (loaded from a saved build, warm in memory, or cold), its CPU on the
worker and the rows it holds, whether the cut's row was on disk, and
`waits` (how many builds answered
"waiting": 0 from a bridge that keeps named blocks, whose snapshot waits
for nothing).

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
import hashlib
import http.client
import itertools
import json
import os
import pickle
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_bridge as bridge  # noqa: E402
import sminos_jobs as jobs  # noqa: E402

UNNAMED_WAIT = 2.0        # s: a row past the cut that no notice named is drawn after this
NOTICE_WAIT = 5.0         # s: a noticed row not on disk this long after its step's end (or its notice, with none open) ends the subscription
OPEN_WAIT = 20.0          # s: a bridge that sends no snapshot by then ends the subscription (the reader's 503 retries take up to 15)
END_GRACE = 1.0           # s: once the session is not running, what it still flushes is drawn this long
ROWS_BUDGET = 512 * 1024  # bytes of row JSON in a snapshot or a page: "as many as fit"
ROW_KEY = b'"uuid"'       # a line without these bytes holds no row: it is not parsed
READ_BLOCK = 8 << 20      # bytes an index reads at a time
INDEX_KEEP = 32           # transcripts whose index is kept after their last subscription went (or the warmer let go)
WARM_EVERY = 2.0          # s: how often the live members are looked over and a round of warm jobs begins
WARM_PARALLEL = 2         # warm jobs queued or running at once, in the process
SAVE_GROWTH = 16 << 20    # bytes of transcript an index grows by before its build is saved again
STOP_SAVE_SECONDS = 5.0   # s: the uplink's stop waits this long for the held builds to be saved
BUILD_FORMAT = 2          # what a saved build holds: bumped whenever Index, jobs.Ledger or Chain change it
BUILD_KEEP_DAYS = 14      # a saved build not written or loaded this long is swept at the uplink's start
BUILD_DIR = "plane"       # under daemon/: the saved builds
PRESENCE_EVERY = 0.2      # s: how often the engine's records are looked at
BRIDGE_RECHECK = 2.0      # s: how often a bridge that answered is asked again
METAS_EVERY = 0.5         # s: how often a main subscription's subagent tree is looked at
LOCATE_EVERY = 1.0        # s: how often a transcript not found yet is looked for
MEMBERS_EVERY = 10.0      # s: how often the members are read again when no session came or went
IDENTITY_EVERY = 10.0     # s: how stale a running pid's identity may be (its start time read this often)
TOMBSTONE_FILE = "presence.json"  # under daemon/: project id → the time its sessions' leaving was last said and taken
TOMBSTONE_MARGIN = 60.0   # s: a session that left this long before that time is said again (clock steps, a write in flight)
# s: how long a leaver is kept for a re-open's heal (say_again), a bound on memory alone: which leavers a
# heal says again is decided by when the body it heals was queued, not by age. A body out an hour after its
# oldest line was queued would have ended its lane long before (16 MiB queued, or any POST past 60 s).
GONE_KEEP = 3600.0
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
    `rows` raise Reset when the file was replaced, shrank, or is gone.
    `crc` is the CRC-32 of the bytes before `end`, kept as they are read:
    what a saved build is checked against when it is loaded."""

    def __init__(self, path):
        self.path = path
        self.ino = None
        self.end = 0           # just past the last whole line read
        self.uuids, self.offsets, self.lengths = [], [], []
        self.at = {}           # uuid → its first position
        self.parsed = 0        # bytes handed to the parser, all told: what building it cost
        self.crc = 0           # zlib.crc32 of the file's bytes before `end`

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
                data = carry + block
                lines = data.split(b"\n")
                carry = lines.pop()
                self.crc = zlib.crc32(memoryview(data)[:len(data) - len(carry)], self.crc)
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


class Chain:
    """Which of a transcript's rows are on the conversation's live chain: the
    rows the engine holds. A transcript is a tree — each row names its
    `parentUuid` — and the engine reads only the chain from its leaf, while
    the rows a branch left behind stay in the file: a prompt sent again after
    an Esc handed it back, the turns a /rewind undid, a response the engine
    dropped when a message reached its turn mid-stream.

    Fed every row in file order, it follows the engine's writes. A row whose
    parent is the leaf extends the chain. A tool result names its issuing
    assistant rather than the leaf, so parallel calls' results hang off their
    own assistants (the engine's `sourceToolAssistantUUID`): it joins the
    chain while that assistant is on it, and so what the leaf's ancestry
    skips stays on — sibling results and everything delivered between a call
    and its result, as the live engine holds it (its resume-time loader
    keeps only the meta and attachment rows of those). Any other row whose
    parent is not the leaf starts a branch: the rows that joined after the
    branch point leave the chain (but a tool result whose assistant stays on
    it, or an assistant of a response that does, as the loader recovers
    them), and the branch's own rows rejoin it if a branch had taken them
    off. A tool result whose assistant is off the chain is off it too, and
    moves nothing.

    Rows are written out of order around a session's start (a child a few ms
    ahead of its parent), so a row whose parent is not placed yet waits for
    it and is placed with it; one whose parent never comes stays unplaced,
    and unmarked. A null parent (a compaction's boundary, a session's first
    row) continues the chain: the history before a compaction stays drawn.
    Progress rows pass their parent through and are never marked; in a main
    transcript, so are sidechain rows (an old engine's subagent rows).
    `add` returns the rows each row took off the chain and put back on."""

    def __init__(self, main=True):
        self.main = main
        self.parent = {}       # uuid → its parentUuid (None: a root), every row seen
        self.seq = {}          # uuid → its place in the file's order
        self.progress = set()
        self.source = {}       # a tool result's uuid → the assistant it answers
        self.group = {}        # an assistant's uuid → its response's message id
        self.groups = {}       # message id → the assistants of that response
        self.waiting = {}      # uuid → the rows seen whose parent it is, while it is not placed
        self.results = {}      # an assistant's uuid → the tool results that answer it
        self.line = []         # the chain, in the order its rows joined it
        self.pos = {}          # uuid → its index in `line`: the rows on the chain
        self.offs = set()      # the rows placed off it
        self.passed = set()    # the progress rows placed
        self.moved = {}        # while a row is added: each row it moved → whether that row was off before

    def copy(self):
        c = Chain(self.main)
        c.parent, c.seq, c.progress, c.source = dict(self.parent), dict(self.seq), set(self.progress), dict(self.source)
        c.group, c.groups = dict(self.group), {k: list(v) for k, v in self.groups.items()}
        c.results = {k: list(v) for k, v in self.results.items()}
        c.waiting = {k: list(v) for k, v in self.waiting.items()}
        c.line, c.pos, c.offs, c.passed = list(self.line), dict(self.pos), set(self.offs), set(self.passed)
        return c

    def off(self, uuid):
        return uuid in self.offs

    def placed(self, uuid):
        return uuid in self.pos or uuid in self.offs or uuid in self.passed

    def add(self, row):
        """One row, in file order: (off, on), the rows it took off the chain,
        itself among them when it was placed off it, and the rows it put back
        on. A row seen before changes nothing (the engine writes a uuid once)."""
        u = row.get("uuid")
        if not isinstance(u, str) or not u or u in self.parent or (self.main and row.get("isSidechain") is True):
            return [], []
        p = row.get("parentUuid")
        p = p if isinstance(p, str) and p else None
        self.parent[u] = p
        self.seq[u] = len(self.seq)
        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        content = message.get("content")
        if row.get("type") == "progress":
            self.progress.add(u)
        elif row.get("type") == "assistant":
            mid = message.get("id")
            if isinstance(mid, str) and mid:
                self.group[u] = mid
                self.groups.setdefault(mid, []).append(u)
        elif row.get("type") == "user" and isinstance(content, list) and \
                any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            src = row.get("sourceToolAssistantUUID")
            self.source[u] = src if isinstance(src, str) and src else p
            self.results.setdefault(self.source[u], []).append(u)
        if p is not None and not self.placed(p):
            self.waiting.setdefault(p, []).append(u)
            return [], []
        # A cascade of waiting rows can move one row more than once: what it
        # reports is each row's net move, in the order it first moved.
        self.moved = {}
        todo = collections.deque([u])
        while todo:
            x = todo.popleft()
            self.place(x)
            todo.extend(self.waiting.pop(x, ()))
        moved, self.moved = self.moved, {}
        return ([r for r, was in moved.items() if not was and r in self.offs],
                [r for r, was in moved.items() if was and r in self.pos])

    def through(self, p):
        while p in self.progress:
            p = self.parent[p]
        return p

    def note(self, x):
        self.moved.setdefault(x, x in self.offs)

    def join(self, x):
        self.note(x)
        self.offs.discard(x)
        self.pos[x] = len(self.line)
        self.line.append(x)

    def leave(self, x):
        self.note(x)
        self.offs.add(x)

    def place(self, x):
        if x in self.progress:   # passes its parent through; never the leaf, never marked
            self.passed.add(x)
            return
        p = self.through(self.parent[x])
        if p is None or (self.line and p == self.line[-1]):
            self.join(x)
        elif x in self.source:
            if p in self.pos or self.source[x] in self.pos:
                self.join(x)
            else:
                self.leave(x)
        else:
            self.branch(x, p)

    def kept(self, r):
        """Whether a row stays on, or comes back, with the chain: a tool
        result whose assistant is on it, or an assistant of a response that
        is (the engine's loader recovers both)."""
        return self.source.get(r) in self.pos or any(a in self.pos for a in self.groups.get(self.group.get(r), ()))

    def branch(self, x, p):
        """`x` starts a branch at `p`, a placed row other than the leaf: the
        rows after the last of p's ancestors on the chain leave it, and p's
        rows back to that ancestor (if a branch had taken them off) rejoin,
        with the responses' other rows and results the loader recovers."""
        walk, y = [], p
        while y is not None and y not in self.pos:
            walk.append(y)
            y = self.through(self.parent[y])
        at = self.pos[y] + 1 if y is not None else 0
        left = self.line[at:]
        for r in left:
            self.note(r)
            del self.pos[r]
        del self.line[at:]
        for r in left:
            if self.kept(r):
                self.join(r)
            else:
                self.leave(r)
        back, todo = set(), list(walk)
        while todo:
            r = todo.pop()
            if r not in back:
                back.add(r)
                todo.extend(a for a in self.groups.get(self.group.get(r), ()) if a in self.offs)
                todo.extend(t for t in self.results.get(r, ()) if t in self.offs)
        for r in sorted(back, key=self.seq.__getitem__):   # in the order they were written, as they first stood
            self.join(r)
        self.join(x)


def builds_dir():
    return os.path.join(sminos.root(), "daemon", BUILD_DIR)


def build_file(path):
    """Where a transcript's saved build lives: named by its realpath's hash."""
    real = os.path.realpath(path).encode("utf-8", "surrogateescape")
    return os.path.join(builds_dir(), hashlib.sha256(real).hexdigest()[:24] + ".build")


def sweep_builds(now=None):
    """At the uplink's start (one uplink at a time, so no save is under way):
    the saved builds neither written nor loaded for BUILD_KEEP_DAYS, and any
    write a crash left half done, removed."""
    now = time.time() if now is None else now
    d = builds_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return
    for name in names:
        path = os.path.join(d, name)
        try:
            if name.endswith(".tmp") or (name.endswith(".build") and
                                         now - os.stat(path).st_mtime > BUILD_KEEP_DAYS * 86400):
                os.unlink(path)
        except OSError:
            pass


def _remove(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _prefix_holds(index):
    """Whether the file still holds, before the saved index's `end`, the
    very bytes the index read: their CRC-32 against the one it kept. A
    checksum, not a digest: it catches a rewrite in place, not an adversary
    (the saved build is the daemon's own file). The file is read once, in
    blocks, without being parsed: 0.04 CPU-s for 317 MB, where a parse is
    0.75 (open-fast M7's Decision Log)."""
    crc, left = 0, index.end
    buf = bytearray(min(READ_BLOCK, max(left, 1)))
    view = memoryview(buf)
    with open(index.path, "rb") as f:
        while left:
            n = f.readinto(view[:min(len(buf), left)])
            if not n:
                return False
            crc = zlib.crc32(view[:n], crc)
            left -= n
    return crc == index.crc


def _shaped(obj, kind, fresh):
    """Whether a loaded object is a `kind` holding what a fresh one holds: a
    build saved by code whose classes held other fields is not used, even if
    BUILD_FORMAT was not bumped."""
    return type(obj) is kind and vars(obj).keys() == vars(fresh).keys()


class Transcript:
    """One transcript file's index, its loop's jobs ledger, its chain, and
    the worker that reads it: every read of the file's bulk — an open's
    build, a page, a look at the disk facts, an `output`, a warm job — is a
    job run here, one at a time. Two queues: `submit`'s, the foreground,
    what a subscription waits on, in the order submitted; and
    `submit_background`'s, the warmer's and the saves', taken only while no
    foreground job is queued. A running job is never interrupted. A job is
    `job(transcript)` and hands its own result over; the index, the ledger
    and the chain, fed every row the index reads, are touched by jobs alone.

    The build is saved to disk (save, build_file) after the first extend in
    this process and again whenever the index grew SAVE_GROWTH bytes past
    the last save — as a background step once the job that extended it is
    done, so a save delays no answer and no open queued behind it; the first
    extend loads the saved build (load) and reads on from its end."""

    def __init__(self, path):
        self.path = path
        self.index = Index(path)
        self.ledger = jobs.Ledger()
        self.chain = Chain(main=not is_agent_path(path))
        self.users = 0         # the subscriptions and the warmer holding it (under Transcripts' lock)
        self.indexed = False   # an extend has read the file since the index began: the next is warm
        self.tried = False     # the saved build was looked for (by the first extend)
        self.how = None        # how the index last came: "loaded" (a saved build), "cold" (parsed from the first byte) or "warm"
        self.cpu_ms = 0        # the CPU the last extend cost on this worker, a load included
        self.saved = None      # index.end as last saved or loaded (on disk): None, neither yet in this process
        self.tried_end = None  # index.end as last saved, loaded, or tried and failed: the growth rule's mark
        self.save_due = False  # the last extend calls for a save, taken when no foreground job is queued
        self.warming = False   # a warm job is queued or running (Warmer)
        self.lock = threading.Lock()
        self.jobs = collections.deque()
        self.background = collections.deque()
        self.working = False

    def submit(self, job):
        self.queue(self.jobs, job)

    def submit_background(self, job):
        self.queue(self.background, job)

    def queue(self, jobs_, job):
        with self.lock:
            jobs_.append(job)
            if self.working:
                return
            self.working = True
        threading.Thread(target=self.work, name="plane-transcript", daemon=True).start()

    def work(self):
        while True:
            with self.lock:
                if self.jobs:
                    job = self.jobs.popleft()
                elif self.save_due:
                    job = Transcript.save
                elif self.background:
                    job = self.background.popleft()
                else:
                    self.working = False
                    return
            job(self)

    def extended(self):
        """The index, brought up to the file's end — on the first extend in
        this process from the saved build's end, when one can be used. A file
        replaced or shrunk since leaves a fresh index for whoever reads next,
        and the Reset says so to the reader holding rows of the old one."""
        how, cpu = "warm" if self.indexed else "cold", time.thread_time()
        if not self.tried:
            self.tried = True
            if self.load():
                how = "loaded"
        ledger, chain = self.ledger, self.chain

        def on_row(row):
            ledger.add(row)
            chain.add(row)

        try:
            self.index.extend(on_row)
        except Reset:
            self.index, self.ledger, self.chain = Index(self.path), jobs.Ledger(), Chain(self.chain.main)
            self.indexed, self.saved, self.tried_end = False, None, None
            raise
        self.indexed = True
        self.how, self.cpu_ms = how, int(round((time.thread_time() - cpu) * 1000))
        if self.index.ino is not None and (self.tried_end is None or self.index.end - self.tried_end >= SAVE_GROWTH):
            self.save_due = True
        return self.index

    def load(self):
        """The saved build into the index, the ledger and the chain: True.
        False when there is none, or the one there cannot be used — of
        another format or shape, of another file (its realpath or inode), of
        a file now shorter than what it read or whose bytes before the saved
        end are not the ones it read (_prefix_holds), or unreadable — and
        then it is removed. A saved build is the daemon's own file under a
        0700 directory: loading it is trusted."""
        file = build_file(self.path)
        try:
            with open(file, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return False
        except OSError:
            _remove(file)
            return False
        try:
            fmt, real, ino, end, index, ledger, chain = pickle.loads(data)
            st = os.stat(self.path)
            ok = fmt == BUILD_FORMAT and real == os.path.realpath(self.path) and st.st_ino == ino \
                and st.st_size >= end and _shaped(index, Index, Index(self.path)) and index.end == end \
                and index.ino == ino and _shaped(ledger, jobs.Ledger, jobs.Ledger()) \
                and _shaped(chain, Chain, Chain(chain.main)) and chain.main == self.chain.main
            if ok:
                index.path = self.path
                ok = _prefix_holds(index)
        except Exception:  # noqa: BLE001 — any build that cannot be read is no build
            ok = False
        if not ok:
            _remove(file)
            return False
        index.path = self.path
        self.index, self.ledger, self.chain = index, ledger, chain
        self.indexed, self.saved, self.tried_end = True, end, end
        try:
            os.utime(file)   # used: the sweep keeps it
        except OSError:
            pass
        return True

    def save(self):
        """The build as of index.end written whole beside the saved builds
        (0600, under a 0700 directory) and moved into place: True once
        saved. One that fails is said in the log; the growth rule tries it
        again once the index grows SAVE_GROWTH more, an eviction or the stop
        at once (save_changed: `saved` still says what is on disk)."""
        self.save_due = False
        if self.index.ino is None:
            return False
        file = build_file(self.path)
        tmp = "%s.%d.%d.tmp" % (file, os.getpid(), threading.get_ident())
        end = self.index.end
        try:
            data = pickle.dumps((BUILD_FORMAT, os.path.realpath(self.path), self.index.ino, end, self.index,
                                 self.ledger, self.chain), protocol=5)
            os.makedirs(os.path.dirname(file), mode=0o700, exist_ok=True)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, file)
        except Exception as e:  # noqa: BLE001 — a build not saved costs a parse after a restart, nothing else
            _remove(tmp)
            log("the build of %s could not be saved (%r): it is parsed again after a restart" % (self.path, e))
            self.tried_end = end
            return False
        self.saved = self.tried_end = end
        return True

    def save_changed(self):
        """save, when the index read past what is on disk: whether the build
        on disk is now current (nothing to save, or saved)."""
        if self.index.ino is not None and self.saved != self.index.end:
            return self.save()
        return True


class Transcripts:
    """The transcripts the subscriptions and the warmer read, by path: one
    Transcript per file, shared by every holder, and kept after the last one
    lets go — the `keep` released last, each saved on its worker as it
    leaves — so a second subscription, or the same browser subscribing
    again, builds nothing, and one evicted loads. One per process
    (TRANSCRIPTS), kept across the uplink's streams.

    An evicted Transcript is `retiring` until its save has run: acquired
    again meanwhile, it is that same Transcript that comes back, so one
    worker per file orders every save of it and an older build never lands
    over a newer one. Each retirement has its own number, which an acquire
    voids: a save that ends lets go of its own retirement only, never of
    one that began after it."""

    def __init__(self, keep=INDEX_KEEP):
        self.keep = keep
        self.lock = threading.Lock()
        self.held = collections.OrderedDict()   # path → Transcript, the least recently used first
        self.retiring = {}                      # path → (an evicted Transcript whose save has not run yet, its retirement)
        self.retirements = itertools.count(1)

    def acquire(self, path):
        with self.lock:
            t = self.held.pop(path, None) or (self.retiring.pop(path, None) or (Transcript(path),))[0]
            t.users += 1
            self.held[path] = t
            return t

    def release(self, t):
        with self.lock:
            t.users -= 1
            if self.held.get(t.path) is t:
                self.held.move_to_end(t.path)
            idle = [p for p, held in self.held.items() if held.users <= 0]
            gone = [self.held.pop(p) for p in idle[:max(0, len(idle) - self.keep)]]
            retired = [(g, next(self.retirements)) for g in gone]
            for g, n in retired:
                self.retiring[g.path] = (g, n)
        for g, n in retired:
            g.submit_background(lambda t, n=n: self.retire(t, n))

    def retire(self, t, n):
        """Retirement `n`'s job: the build saved, then let go, unless the
        Transcript was acquired again meanwhile (and maybe retired anew)."""
        try:
            t.save_changed()
        finally:
            with self.lock:
                if self.retiring.get(t.path) == (t, n):
                    del self.retiring[t.path]

    def save_all(self, seconds=STOP_SAVE_SECONDS):
        """The uplink's stop: each held build saved where it read past its
        last save — the retiring ones too — a background job on its own
        worker, all of them waited for `seconds` at most: (how many builds
        are now current on disk, how many were held)."""
        with self.lock:
            held = list(self.held.values()) + [t for t, _ in self.retiring.values()]
        done = []
        for t in held:
            ev, ok = threading.Event(), []
            done.append((ev, ok))

            def job(tr, ev=ev, ok=ok):
                try:
                    ok.append(tr.save_changed())
                finally:
                    ev.set()
            t.submit_background(job)
        deadline = time.monotonic() + seconds
        for ev, _ in done:
            if not ev.wait(max(0.0, deadline - time.monotonic())):
                break
        return sum(1 for ev, ok in done if ev.is_set() and ok == [True]), len(done)


TRANSCRIPTS = Transcripts()


class Warmer:
    """The live sessions' builds kept current in the background (open-fast
    §4), so a live session's first open is warm, without starving the opens.
    Every WARM_EVERY `tick` holds the main transcript of each session it is
    handed — the live members of the stream's open projects, each located
    once — and lets go of the rest, taking them off the round in hand; once
    that round is done it begins another over those it holds. Each tick submits the round's next
    warm jobs while fewer than WARM_PARALLEL are queued or running in the
    process, passing over a transcript that has one. A warm job is a
    background job, taken only while its worker has no foreground job
    queued: it extends the index, and the Transcript's save rule follows. It
    does not look at the disk: a look is a subscription's. One per uplink
    process, kept across its streams as the Transcripts are.

    A worker's queue orders the jobs of one transcript; the GIL is shared by
    all of them and the uplink's main thread. So the first round begins
    WARM_EVERY after the first tick — a fresh process's cold builds would
    otherwise stretch its stream's handshake threefold, and the opens that
    arrive during it — and no warm job is submitted while an open awaits its
    snapshot (`opening`); one already running runs on."""

    def __init__(self, transcripts=None, locate=None, every=WARM_EVERY, parallel=WARM_PARALLEL):
        self.transcripts = transcripts or TRANSCRIPTS
        self.locate = locate or sminos.transcript_now
        self.every, self.parallel = every, parallel
        self.held = {}                      # session → its main Transcript, held while it is handed in
        self.round = collections.deque()    # the sessions this round has still to visit
        self.next_round = None
        self.lock = threading.Lock()
        self.running = 0                    # warm jobs queued or running (under the lock)
        self.failing = {}                   # path → the failure last said (under the lock)

    def tick(self, sessions, now=None, opening=False):
        now = time.monotonic() if now is None else now
        if self.next_round is None:
            self.next_round = now + self.every
        if now >= self.next_round:
            self.next_round = now + self.every
            self.hold(sessions)
            if self.round:
                self.round = collections.deque(sid for sid in self.round if sid in self.held)
            else:
                self.round.extend(self.held)
        while self.round and not opening:
            with self.lock:
                if self.running >= self.parallel:
                    return
                self.running += 1
            t = self.held.get(self.round.popleft())
            if t is None or t.warming:
                with self.lock:
                    self.running -= 1
                continue
            t.warming = True
            t.submit_background(self.warm)

    def hold(self, sessions):
        for sid in [s for s in self.held if s not in sessions]:
            self.transcripts.release(self.held.pop(sid))
        for sid in sorted(sessions):
            if sid not in self.held:
                path = self.locate(sid)   # a miss is looked for again next round
                if path:
                    self.held[sid] = self.transcripts.acquire(path)

    def warm(self, t):
        try:
            try:
                t.extended()
            except Reset:
                t.extended()   # the file was replaced: built again from its start
            with self.lock:
                self.failing.pop(t.path, None)
        except Exception as e:  # noqa: BLE001 — said once while it keeps failing; the next round tries again
            with self.lock:
                said, self.failing[t.path] = self.failing.get(t.path), repr(e)
            if said != repr(e):
                log("warming %s failed: %r" % (t.path, e))
        finally:
            t.warming = False
            with self.lock:
                self.running -= 1

    def close(self):
        """Lets go of everything held."""
        self.round.clear()
        for sid in list(self.held):
            self.transcripts.release(self.held.pop(sid))


class Built:
    """An open's build, read on the transcript's worker: what a subscription
    starts from. `ino` and `offset` are where its Tail picks up (`ino` None:
    no file yet); `emitted` the history's uuids; `shown` the history's newest
    rows that fit, newest first, `more` whether older ones are left; `past`
    the rows past the cut, (uuid, row) oldest first, which go out live;
    `ledger` the loop's jobs ledger and `chain` its chain as of `offset`, the
    subscription's own to feed from there; `how` the index came
    ("loaded", "warm" or "cold"), `cpu_ms` what its extend cost on the
    worker, `rows` the rows it holds — the open line's. It holds no disk
    facts: the look is off the open's path."""

    def __init__(self, ino, offset, emitted, shown, more, past, ledger, chain, how="cold", cpu_ms=0, rows=0):
        self.ino, self.offset = ino, offset
        self.emitted, self.shown, self.more, self.past = emitted, shown, more, past
        self.ledger, self.chain = ledger, chain
        self.how, self.cpu_ms, self.rows = how, cpu_ms, rows


def build(t, cut, bridged, wait=False):
    """An open's build on the worker: the index brought up to the file's end
    (a file replaced since an earlier subscription read it starts over: this
    one holds nothing of the old), the history to the cut — every row on
    disk while the cut's row is not, since nothing past it is flushed either
    — the newest of it that fits read back, and the rows past the cut.
    `wait`, for a bridge that does not keep named blocks: ("waiting", (how,
    cpu_ms, rows)) while the cut's row is not on disk instead, what the build
    that waited cost, for the open's line."""
    try:
        index = t.extended()
    except Reset:
        index = t.extended()
    n = len(index.uuids)
    if cut is not None:
        at = index.at.get(cut)
        if at is None and wait:
            return "waiting", (t.how, t.cpu_ms, n)
        split = n if at is None else at + 1
    else:
        # No cut: a bridged loop had no rows when the module loaded (all are
        # live); without a bridge every row is history.
        split = 0 if bridged else n
    lo = index.older(split, None)
    return "built", Built(index.ino, index.end, dict.fromkeys(index.uuids[:split], "history"),
                          index.rows(lo, split)[::-1], lo > 0, [(r["uuid"], r) for r in index.rows(split, n)],
                          t.ledger.copy(), t.chain.copy(), t.how, t.cpu_ms, n)


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


def is_agent_path(path):
    return os.path.basename(os.path.dirname(path)) == "subagents" and os.path.basename(path).startswith("agent-")


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
    goes to `items` as ("line", obj, at), and the stream's fate as
    ("unavailable", why, at) when nothing answers there, ("refused", status,
    at) when the bridge turned the subscription down (503: not ready), or
    ("closed", why, at) when it ended; `at` is when it arrived (`stamp`, the
    wall clock). It calls nothing of sminos."""

    def __init__(self, path, wake, stamp=time.time):
        super().__init__(name="plane-bridge", daemon=True)
        self.path = path
        self.wake = wake
        self.stamp = stamp
        self.items = queue.Queue()
        self.closing = threading.Event()
        self.sock = None

    def put(self, item):
        self.items.put(item + (self.stamp(),))
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
                 clock=time.monotonic, transcripts=None, wake=lambda: None, disk=None, received=None, wall=time.time):
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
        # The open is timed from the subscribe frame's arrival at the uplink's
        # reader (`received`, the wall clock), on this subscription's clock;
        # its waits (OPEN_WAIT) count from now, when it was asked.
        self.arrived = received if received is not None else wall()
        self.started = clock()
        self.opened = self.started - max(0.0, wall() - self.arrived)
        self.open_noted = False       # its open's one daemon.log line is written (noted)
        self.no_bridge = "no bridge socket" if reader is None else ""   # why it went transcript-only
        self.snap = None              # the bridge's snapshot line
        self.snapped_at = None        # when the open took it (clock)
        self.snap_arrived = None      # when it reached the reader (wall)
        # What the open line says of its builds — one, or, from a bridge that
        # does not keep named blocks, one per ask while the cut's row was not
        # on disk: how the first's index came, their CPU together, the rows
        # the last held; whether the cut's row was on disk; how many answered
        # "waiting".
        self.build_how = None
        self.cpu_ms = 0
        self.build_rows = 0
        self.cut_state = "null"
        self.waits = 0
        self.main = ""
        self.next_locate = 0.0
        self.tail = Tail()
        self.source = None            # the Transcript whose worker reads this one's bulk, once asked
        self.answers = queue.Queue()  # the worker's answers, in the order asked
        self.building = False         # an open's build is asked and not answered yet
        self.over = False             # the session ended and what it flushed is drawn: transcript-only, idle
        self.emitted = {}             # uuid → "history" | "named" | "unnamed"
        self.pool = collections.OrderedDict()  # uuid → [row, first seen]: past the cut, not yet emitted, disk order
        self.noticed = {}             # uuid → (its loop's step open at the notice, or None; when): row not emitted yet
        self.due = {}                 # uuid → when its row is due: NOTICE_WAIT after that step's end, or the notice
        self.loose = set()            # noticed rows nothing drawn awaits (the cut's own): past due, forgotten
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
        # The loop's chain (Chain): the build's, then fed each row as it is
        # released, so every mark this subscription sends is read off it in
        # the order the messages go.
        self.chain = Chain(main=agent is None)
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

    def counted(self, how, cpu_ms, rows):
        """One build's figures into the open line's."""
        self.build_how = self.build_how or how
        self.cpu_ms += cpu_ms
        self.build_rows = rows

    def noted(self, how):
        """The open's one daemon.log line, once: how long from the subscribe
        frame's arrival to its snapshot or its end before one, which wait
        ended it, and where the time went — the bridge's snapshot's arrival
        and when the open took it, how the build came, what it cost, whether
        the cut's row was on disk, how many builds waited for it."""
        if self.open_noted:
            return
        self.open_noted = True
        if self.snapped_at is not None:
            arrived = (self.snap_arrived - self.arrived) if self.snap_arrived is not None else 0.0
            bridge_clause = "bridge: snapshot arrived %.2f s, taken %.2f s" % (arrived, self.snapped_at - self.opened)
        else:
            bridge_clause = "bridge: no snapshot" if self.bridged else "no bridge"
        built = "%s %d ms %d rows" % (self.build_how, self.cpu_ms, self.build_rows) if self.build_how else "none"
        log("open %s of %s%s: %s after %.2f s from the subscribe's arrival (%s; build: %s, cut %s; waits %d)" % (
            self.sub, self.session[:8], "/" + self.agent if self.agent else "", how, self.clock() - self.opened,
            bridge_clause, built, self.cut_state, self.waits))

    def close(self):
        if self.n is None:
            self.noted("closed before its snapshot")
        if self.reader is not None:
            self.reader.close()
        if self.source is not None:
            self.transcripts.release(self.source)
            self.source = None

    def ask(self, path, read):
        """`read(transcript)` on the transcript's worker; its answer, (kind,
        value), comes back through `answers`; any answer but "waiting" wakes
        the uplink (a waiting build is asked again on the next pump, not at
        once, which would spin); a Reset is ("reset", why), any other failure
        ("failed", why)."""
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

    def end(self, reason, message=None, how=None):
        if self.ended:
            return []
        if self.n is None:
            self.noted(how or "%s before its snapshot%s" % (reason, ": " + message if message else ""))
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

    def keeps_named(self):
        """The bridge's snapshot declares that it keeps a block after its
        block-row (open-fast M5): only then does the open go without waiting
        for the cut's row. A bridge from before it — its mod and child, still
        running after the uplink was upgraded — drops the block at its
        block-row, so its cut may name a row neither on disk nor carried."""
        return self.snap.get("namedBlocks") is True

    def open(self, now, out):
        """The snapshot, once the bridge's (if any) is in and the build has
        answered — and, from a bridge that does not keep named blocks, once
        the cut's row is on disk; False while it waits."""
        if self.bridged and self.snap is None:
            while self.snap is None:
                try:
                    item = self.reader.items.get_nowait()
                except queue.Empty:
                    break
                if item[0] == "line" and isinstance(item[1], dict) and item[1].get("type") == "snapshot":
                    self.snap, self.snapped_at = item[1], now
                    self.snap_arrived = item[2] if len(item) > 2 else None
                    self.agents = {a["agentId"]: dict(a) for a in self.snap.get("agents") or ()
                                   if isinstance(a, dict) and isinstance(a.get("agentId"), str)}
                elif item[0] == "unavailable":
                    self.reader = None   # no bridge after all: the transcript alone
                    self.no_bridge = "the bridge did not answer"
                    break
                else:
                    why = {"refused": "the bridge refused the subscription (%s)" % (item[1],),
                           "closed": "the bridge's stream ended before its snapshot"}.get(item[0], "the bridge's stream began without a snapshot")
                    out += self.end("discontinuity", why)
                    return False
            if self.bridged and self.snap is None:
                if now - self.started > OPEN_WAIT:
                    out += self.end("discontinuity", "the bridge sent no snapshot",
                                    how="timeout: the bridge sent no snapshot in %g s" % OPEN_WAIT)
                return False
        # The history is read on the transcript's worker (build): once, or,
        # from a bridge that does not keep named blocks, again while the
        # cut's row is not on disk. A null cut (or one that does not name
        # this loop) with a bridge: the loop had no rows when the module
        # loaded, and none was noticed since — the seed covers every older
        # row. Empty history; all rows live.
        cut = self.cut()
        path = self.path(now)
        wait = self.bridged and not self.keeps_named()
        if not self.building:
            if not path:
                return self.unlocated(now, cut, wait, out)
            self.building = True
            bridged = self.bridged

            def opening(t):
                # The build alone: the snapshot goes with the facts as they
                # stand, and the look is asked on the pump right after it.
                return build(t, cut, bridged, wait)

            self.ask(path, opening)
            return False
        try:
            kind, built = self.answers.get_nowait()
        except queue.Empty:
            return False
        self.building = False
        if kind == "waiting":
            self.counted(*built)
            self.waits += 1
            self.cut_state = "not on disk"
            if now - self.snapped_at > NOTICE_WAIT:
                out += self.end("discontinuity", "the snapshot's cut, row %s, never reached the transcript" % cut)
            return False
        if kind != "built":
            out += self.end("discontinuity" if kind == "reset" else "error", built)
            return False
        self.counted(built.how, built.cpu_ms, built.rows)
        self.cut_state = "null" if cut is None else "on disk" if cut in built.emitted else "not on disk"
        if built.ino is None and not self.alive():
            out += self.end("session-ended", "no transcript of the session on this machine")
            return False
        self.tail.path, self.tail.offset, self.tail.ino = self.source.path, built.offset, built.ino
        self.ledger, self.chain = built.ledger, built.chain
        self.emitted = built.emitted
        for u, row in built.past:
            if u not in self.emitted and u not in self.pool:
                self.pool[u] = [row, now]
        return self.snapshot(now, built.shown, built.more, out)

    def unlocated(self, now, cut, wait, out):
        """The open while the session's transcript is not found: with no
        process, `session-ended` (the machine does not hold it); else an
        empty snapshot at once, cut or no cut, and its rows as they come —
        but with a cut and `wait` (a bridge that does not keep named
        blocks), as long as a cut row may take."""
        if not self.alive():
            out += self.end("session-ended", "no transcript of the session on this machine")
            return False
        if cut is not None:
            self.cut_state = "not on disk"
            if wait:
                if now - self.snapped_at > NOTICE_WAIT:
                    out += self.end("discontinuity", "the snapshot's cut, row %s, never reached the transcript" % cut)
                return False
        return self.snapshot(now, [], False, out)

    def snapshot(self, now, shown, more, out):
        """The snapshot message, history's newest rows `shown` (newest
        first), then a block-row for each named block it carries; True: the
        subscription is open. A named block of this loop whose row is in the
        history is left out (its row is drawn instead); one whose row is not
        on disk is kept and its row awaited as a notice of its step, as is
        the cut's own row (loose: nothing drawn waits on it); another loop's
        named block is kept, its block-row relayed."""
        streaming, kept = [], []
        if self.bridged:
            for e in self.snap.get("streaming") or []:
                if not isinstance(e, dict) or not self.carried(e.get("agentId")):
                    continue
                key = (e.get("turnId"), e.get("agentId"), e.get("step"))
                self.upto[key] = e.get("upTo") if isinstance(e.get("upTo"), int) else -1
                self.steps.add(key)
                blocks = []
                for b in e.get("blocks") or []:
                    if not isinstance(b, dict):
                        continue
                    u = b.get("uuid")
                    if isinstance(u, str) and u:
                        if self.mine(e.get("agentId")):
                            if u in self.emitted:
                                continue
                            self.noticed[u] = (key, now)
                        kept.append({"uuid": u, "turnId": key[0], "agentId": key[1], "step": key[2],
                                     "index": b.get("index")})
                    self.held.add(key + (b.get("index"),))
                    blocks.append(b)
                streaming.append({**e, "blocks": blocks})
            cut = self.cut()
            if cut is not None and cut not in self.emitted and cut not in self.noticed:
                self.noticed[cut] = (None, now)
                self.due[cut] = now + NOTICE_WAIT
                self.loose.add(cut)
        self.next_look = now   # the look, off the open's path: asked once this snapshot is out
        self.was_alive = self.alive()
        self.body = self.derive(self.was_alive)
        body = {"rows": shown, "more": more, "offChain": self.off_chain(shown), **self.body, "presence": self.presence(),
                "streaming": streaming}
        if self.agent is None:
            body["usage"] = usage_of(self.snap.get("usage")) if self.bridged else None
        out.append(self.message("snapshot", body))
        self.noted("bridge snapshot" if self.bridged else "transcript-only (%s)" % self.no_bridge)
        self.n = 1
        out.extend(self.message("block-row", k) for k in kept)
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
            body = {"turnId": e.get("turnId"), "agentId": agent, "step": e.get("step"), "chunkIndex": index, "chunk": chunk}
            # The bridge's stamp (ms on this machine's clock), for the web's chunk-to-drawn latency.
            if type(e.get("t")) in (int, float):
                body["t"] = e["t"]
            out.append(self.message("chunk", body))
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
                self.falls_due(now, lambda k: k == key)
                out.append(self.message("step-end", {"turnId": key[0], "agentId": agent, "step": key[2]}))
        elif kind == "turn" and e.get("phase") == "complete":
            # A turn that ends cuts off its steps whose end never came (an abort).
            cut_off = [k for k in self.steps if k[0] == e.get("turnId")]
            for key in sorted(cut_off, key=lambda k: (str(k[1]), k[2] if isinstance(k[2], int) else -1)):
                self.steps.discard(key)
                out.append(self.message("step-end", {"turnId": key[0], "agentId": key[1], "step": key[2]}))
            self.falls_due(now, lambda k: k[0] == e.get("turnId"))
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
        own = (e.get("turnId"), e.get("agentId"), e.get("step"))
        step = own if kind == "block-row" and own in self.steps else self.open_step(e.get("agentId"))
        self.noticed[u] = (step, now)
        if step is None:
            self.due[u] = now + NOTICE_WAIT

    def open_step(self, agent):
        """The loop's model request open now, if any (the latest)."""
        open_ = [k for k in self.steps if (k[1] or None) == (agent or None)]
        return max(open_, key=lambda k: (str(k[0]), k[2] if isinstance(k[2], int) else -1)) if open_ else None

    def falls_due(self, now, ended):
        """Rows noticed during the steps `ended` names are due from now."""
        for u, (step, _at) in self.noticed.items():
            if step is not None and u not in self.due and ended(step):
                self.due[u] = now + NOTICE_WAIT

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
        noticed row not on disk past its due (NOTICE_WAIT after its step's
        end, or after the notice with no step open) ends the subscription;
        a loose one is forgotten."""
        wait = UNNAMED_WAIT if self.bridged else 0.0
        order = list(self.pool)
        upto = len(order) - 1 if any(u not in self.pool for u in self.noticed) else \
            max((i for i, u in enumerate(order) if u in self.noticed), default=-1)
        for i, u in enumerate(order):
            if i > upto and now - self.pool[u][1] < wait:
                break
            out.append(self.release_row(u))
        for u, at in list(self.due.items()):
            if now <= at:
                continue
            if u in self.loose:
                self.forget(u)
                continue
            out += self.end("discontinuity", "row %s, named by the bridge, did not reach the transcript "
                                             "within %g s of its step's end or its notice" % (u, NOTICE_WAIT))
            return

    def forget(self, u):
        """`u`'s notice, done with: its row went out, or nothing waits on it."""
        self.loose.discard(u)
        self.due.pop(u, None)
        return self.noticed.pop(u, None)

    def release_row(self, u):
        """The row message for a row past the cut; it counts as named when its
        own notice came. It carries what the row did to the chain: the rows
        it took off (itself, when it is off it) and those it put back on."""
        row = self.pool.pop(u)[0]
        self.emitted[u] = "named" if self.forget(u) is not None else "unnamed"
        off, on = self.chain.add(row)
        if not off and not on and self.chain.off(u):   # placed by the build, which read past the cut
            off = [u]
        body = {"row": row, "agentId": self.agent}
        if off:
            body["offChain"] = off
        if on:
            body["onChain"] = on
        return self.message("row", body)

    def off_chain(self, rows):
        """The uuids of `rows` off the chain, as this subscription knows it now."""
        return [r["uuid"] for r in rows if isinstance(r, dict) and self.chain.off(r.get("uuid"))]

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
        self.due.clear()
        self.loose.clear()
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
            return [self.message("rows", {"rows": [], "before": before, "more": False, "offChain": []})]
        ino = self.tail.ino
        self.ask(self.tail.path, lambda t: page_of(t, ino, before, limit))
        return []

    def answer(self, out):
        """What the worker answered, in the order asked — pages, `output`s,
        looks at the disk; a transcript replaced under a page is a
        discontinuity. A page's rows are marked off the chain here, from this
        subscription's chain, in the order its messages go."""
        while not self.ended:
            try:
                kind, value = self.answers.get_nowait()
            except queue.Empty:
                return
            if kind == "page":
                out.append(self.message("rows", {**value, "offChain": self.off_chain(value["rows"])}))
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

    def answers(self, sid, now, socks=None):
        """`socks`: the sessions with a socket in the bridges' directory as
        just listed (bridge_socks), so a session with none costs no stat."""
        try:
            if socks is not None and sid not in socks:
                raise FileNotFoundError(sid)
            path = bridge.endpoint(sid)
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


def bridge_socks():
    """The sessions with a socket in the bridges' directory, from one listing."""
    try:
        return {n[:-len(".sock")] for n in os.listdir(bridge.bridge_dir()) if n.endswith(".sock")}
    except OSError:
        return set()


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

    def __init__(self, machine, wake, bridges=None, transcripts=None, disk=None, warmer=None):
        self.machine = machine
        self.wake = wake
        self.bridges = bridges or Bridges()   # kept across streams by the uplink: no answer is relearned
        self.bridges.wake = wake
        self.transcripts = transcripts or TRANSCRIPTS   # the process's: no index is rebuilt across streams
        self.disk = disk or DISK                        # and no meta or agent file read again unchanged
        # The warmer: kept across streams by the uplink, which hands one in,
        # so what it holds stays held; one of this plane's own lets go with it.
        self.own_warmer = warmer is None
        self.warmer = warmer or Warmer(self.transcripts)
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
        self.again = {}           # project id → since: its presence said again at the next look (say_again)
        self.gone = {}            # project id → {session: when first said not running}, not seen back (GONE_KEEP)
        self.subs = {}            # sub → Subscription
        self.diffs = queue.Queue()
        self.read_for = None      # the running sessions the members were last read for
        self.next_members = 0.0

    def close(self):
        for s in self.subs.values():
            s.close()
        self.subs.clear()
        if self.own_warmer:
            self.warmer.close()

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

    def presence_of(self, sid, now, socks=None):
        return {"record": record_body(self.live.get(sid)), "bridge": self.bridges.answers(sid, now, socks)}

    def presence(self, pid, force=False, now=None, socks=None):
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
        members = self.members.get(pid, ())
        gone = self.gone[pid] = {sid: at for sid, at in self.gone.get(pid, {}).items() if now - at <= GONE_KEEP}

        def not_running(sid):
            gone.setdefault(sid, now)   # when it was first said gone: a later say does not keep it longer
            out.append(envelope(pid, self.machine, sid, "presence", None, None, {"record": None, "bridge": False}))
        if force:
            self.live = self.records.scan()
            mark = tombstone_marks().get(pid)
            since = None if mark is None else mark - TOMBSTONE_MARGIN
            for sid, at in sorted(self.left.get(pid, {}).items()):
                if since is None or at is None or at >= since:
                    not_running(sid)
            if pid in self.read_at:
                self.tombstoned[pid] = self.read_at[pid]
        socks = bridge_socks() if socks is None else socks
        since = self.again.pop(pid, None)
        again = since is not None
        if again:
            said = {m["session"] for m in out}
            for sid in sorted(sid for sid, at in gone.items() if at >= since and sid not in members and sid not in said):
                not_running(sid)
        for sid in sorted(members):
            body = self.presence_of(sid, now, socks)
            if force or again or self.sent.get((pid, sid)) != body:
                self.sent[(pid, sid)] = body
                gone.pop(sid, None)
                out.append(envelope(pid, self.machine, sid, "presence", None, None, body))
        for key in [k for k in self.sent if k[0] == pid and k[1] not in members]:
            body = self.sent.pop(key)
            if body["record"] is not None or body["bridge"]:
                not_running(key[1])
        return out

    def say_again(self, pid, since):
        """The project's presence is said again at its next look, changed or
        not, since a copy older than the one last sent may reach the hub
        after it (a body in flight at a re-open, applied after the hello,
        whose oldest line of the project was queued at `since`, monotonic):
        every member's, and every leaver this plane first said gone at or
        after `since` and has not seen back. One said gone before can carry
        no live presence in that body, its live presence having been queued
        before its tombstone, however long either waited. A leaver said twice
        is harmless."""
        self.again[pid] = min(since, self.again.get(pid, since))

    def take_read(self, pid):
        """The read the forced presence just drawn for the project said its
        leavers from, taken by the POST that carries it (`accepted`'s
        `read`); None when there was none."""
        return self.tombstoned.pop(pid, None)

    def accepted(self, pid, read=None):
        """The hub answered 200 to the POST that carried a connect's presence
        for the project: its leavers are said, so the next connect says only
        those that left since that read — `read`, the one that POST's
        presence was drawn from (take_read), else the latest forced one's.
        Kept across restarts; a mark that cannot be written leaves the old
        one, which says more, never less."""
        at = self.tombstoned.pop(pid, None) if read is None else read
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

    def subscribe(self, project, frame_, received=None):
        """A `subscribe` frame; `received`, its arrival at the uplink's reader
        (epoch s), is where the open's time starts."""
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
            project.id, self.machine, sid, agent, sub, reader=reader,
            locate=lambda: sminos.transcript_now(sid),   # asked until found, every LOCATE_EVERY
            presence=lambda: self.presence_of(sid, time.monotonic()), alive=lambda: self.running(sid),
            transcripts=self.transcripts, wake=self.wake, disk=self.disk, received=received)
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
        MEMBERS_EVERY for what only the log changes (a seat retired). The
        warmer is handed the live members of those projects, and whether an
        open awaits its snapshot."""
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
        socks = bridge_socks()
        for pid in sorted(projects):
            out += self.presence(pid, now=now, socks=socks)
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
        self.warmer.tick({sid for pid in projects for sid in self.members.get(pid, ()) if sid in self.live}, now,
                         opening=any(s.n is None for s in self.subs.values()))
        while True:
            try:
                sub, body = self.diffs.get_nowait()
            except queue.Empty:
                break
            s = self.subs.get(sub)
            if s is not None:
                out += s.diffed(body)
        return out
