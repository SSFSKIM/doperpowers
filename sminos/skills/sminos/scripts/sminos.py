#!/usr/bin/env python3
"""sminos — one fleet registry for Claude Code sessions.

The unit is the PROJECT (a committed .smns; else, on a machine enrolled at a
desk hub, the project the repository's remote derives, else the machine's own
project; else the owning repository) and
its family: every session working under it is a MEMBER, with no join step and
no host — the human is the host. A SEAT is a named position, with a role and a
brief, that a session sminos spawned fills; it outlives the process that fills
it and can be filled again (`fill --resume` continues the same session id;
`fill` spawns a fresh one). Every background session spawned through sminos is
a seat, board pipeline workers included. A session the human opened is a
member too, seat-less, from the first call that reads its project.

    sminos spawn    <alias> <task> [--role R] [--brief B] [--cwd C] [--worktree W]
                   [--model M] [--settings S] [--effort E] [--wait]   # a background session in a seat
                   of this project (--cwd's); --brief is its in-charge line; --wait prints the reply.
                   --wait only watches, for DAEMON_TIMEOUT (default 18000 s): the seat works on after,
                   and `reply` reads its live transcript
    sminos seat add <group> <alias> [--role R] [--brief B] [--session S]   # register a vacant seat for a
                   later fill, or, with --session, give a running session a seat
    sminos fill     <seat> <task> [--resume] [--model M] [--settings S] [--effort E] [--wait]
                   # a fresh session in the seat; --resume continues its saved one
    sminos resume   <seat> <msg> [--wait]                 # process-level continuation (stops a live turn first)
                   A resumed background session keeps its SAVED options (name, permission
                   mode, model, settings, effort): --model/--settings/--effort are accepted
                   on resume for argv compatibility but ignored — use fill without --resume
                   to change them.
    sminos send     <member|session name|codex thread> <msg> [--wait] [--from F]
                   # a live member: inbox socket; a stopped seat: resumed. On a machine not
                   # enrolled, a live session in no project by its name; a codex thread (its id,
                   # or codex:<id|exact name>, through codex's queue); --wait needs a seat.
    sminos say      [--in <project>] <text>                # untagged: recorded; @alias / @"a b" / @alias#short /
                   @short / @project/alias: delivered; @all: every live member
    sminos say      [--org] [--project P,..] [--machine M,..] [--here] [--state W,..] <text>   # list's filters:
                   every live session of that scope but you (`list` with the same flags shows them), each woken
                   as @all wakes; recorded in each project it reaches, copied into yours; no @tags beside it
    sminos chat     [<project>] [-n N] [--since TS] [--kind K] [--json]   # no flags: unread, advancing the cursor
    sminos chat     [<project>] --host [-n N] [--since TS] [--json]       # what the members sent their human
    sminos charge   [<member>] "<one line>"               # what the member is in charge of (a session: its own)
    sminos join     <project> | --cwd                     # this session's project, declared: a session is in
                   its launch directory's project (a `cd` moves nothing) until it joins another; --cwd goes
                   back; alone: which project it is in, and why. Not for a seat
    sminos derive   <member> | --all [--refreshes N]      # ask a session its line, by a headless internal fork,
                   once its model made ten tool calls; a session under a name the engine made up (or one sminos
                   gave it) is also asked for a charge name, handed to its name mod as
                   $SMINOS_HOME/names/<session>.json. --all (the daemon's, every five minutes) derives first
                   lines before refreshes and holds a member whose fork failed out for an hour; --refreshes
                   caps the members with a line it forks (the daemon passes 2), oldest line first
    sminos name-due --session <id>                        # the name mod's check: the session's pending
                   name when it is due, else nothing (not for a person to run)
    sminos record                                         # the Stop / SessionStart hook's verb (payload on stdin);
                   a session with the bridge has its marks exported as they are written, and this finds them there
    sminos guide                                          # the SessionStart guidance hook's verb (payload on stdin):
                   who the session is, its project and why, the verbs that reach the org; nothing unenrolled
    sminos watch    <member> [--json]                     # a session's live stream through its bridge: the
                   conversation as it streams, subagents labelled (--json: the endpoint's lines); a stream
                   the bridge ends (its state resent, the child restarted) is followed on
    sminos steer    <member> <text>                       # into the running turn, read at its next model
                   request; the running tool goes on (no bridge: a --bg job's supervisor, else a frame)
    sminos interrupt <member>                             # stop the running turn, and any Bash it moved to
                   the background, as Esc does (needs the bridge)
    sminos stop     <member> <task>                       # stop a background shell or monitor of its, the main
                   loop's or a subagent's, with TaskStop (needs the bridge)
    sminos model    <member> <model|default> [--effort E] # the model (and effort) of this session's next
                   requests; the user's settings untouched (needs the bridge)
    sminos compact  <member> [instructions]               # compact now, or when the running turn ends
                   (needs the bridge)
    sminos command  <member> <name> [args...]             # a slash command run in it as the desk runs one:
                   routed by the bridge, queued, then the line it printed (needs the bridge)
    sminos read     <member> <what> [--breakdown full]    # one of its bridge's reads, as JSON: status, catalog,
                   usage (the token-count API's exact count with --breakdown full), config, settings, mcp
    sminos decide   <member> <request> allow|deny [--message M]   # a permission prompt the session raised
                   (`watch` prints its id; a unique prefix will do), racing the terminal's own dialog
    sminos answer   <member> <request> <answer>...        # a question it asked, one answer per question
                   (an option's label or number; multi-select: "1,3"); its async questions too
    sminos bridge   --session <id>                        # the bridge mod's child: serves the session's
                   endpoint at $SMINOS_HOME/bridge/<id>.sock (not for a person to run)
    sminos project  init [--name N] [--remote URL] [--hub] | show [DIR] | attach [DIR]
                   # --hub: the project syncs through the desk hub of this machine's org, never git;
                   .smns names the org alone, each machine's enrollment the hub's URL; in a repository
                   that resolves by its remote it pins that project's id. show: its source, or why none
    sminos daemon   run [--interval 5] | tick | install | status   # mirror sync and delivery, per machine
    sminos daemon   owed                                  # what this machine still owes, a line per
                   project: deliveries and words not yet made, its own events and kept messages not
                   yet taken upstream; exit 0 only when nothing is (events waiting for closed
                   sessions owe nothing). Reads beside a running daemon; never a message body
    sminos daemon   policy [--read-only on|off] [--ceiling MODE|settings]   # the owner's setting: what this
                   machine admits from outside. Read-only records what is written elsewhere and delivers
                   none of it; the ceiling bounds a spawn. A session reports it, never changes it unasked
    sminos hub      enroll [--name N] [--replace] | show   # this machine at the desk hub: its name
                   there is its name everywhere (the writer host of what it writes). The code is
                   pasted at a hidden prompt, or piped on stdin — never an argument: it carries the org key
    sminos rpc-query [--created T] -- <opId>              # what became of a desk RPC, as the daemon's ledger
                   file holds it (RL4's query, JSON): done, refused, in-progress, expired, not-received;
                   --created, its opCreated. `--` before the id: a base64url id may start with `-`.
                   The file alone: one a worker holds before its claim reads not-received here. It
                   changes nothing
    sminos reply    <seat>                                # latest reply text
    sminos sync     [<seat>] [--all]                      # reconcile status from the harness
    sminos status   <member> <one line>                   # the member's own "now" line
    sminos retire   <member> [--purge]                    # stop; keep (or purge) a seat's record
    sminos remove   <seat>                                # stop and delete the record
    sminos list     [project] [--project P,..] [--machine M,..] [--state W,..] [--org] [--here] [--stopped] [--all] [--json]
                   [words..]  # the caller's project (a session's own, else the working directory's;
                   every project from none); any filter
                   widens to every project known here, then narrows: --machine by prefix, words (all of
                   them) in the alias, short, project, repo, branch, in-charge, now line or title; --org
                   every project; --here this machine, plus every running session in no project.
                   W: busy idle waiting stopped gone vacant retired; stopped, retired and gone fold into a
                   "+N hidden" tail; --stopped adds stopped, --all shows all, --state selects named states.
                   A row: alias [short], kind, state,
                   @machine, (project,) repo@branch, in charge (age), · active <age>. Inside a session
                   it says who you are and ends with how many of your subagents run (list --subagents
                   for them); --here ends with the live sessions that are no member
    sminos list     --subagents [member] [--done N] [--depth N] [--stall MIN] [--all] [--json]
                   # your session's subagents (a member's on this machine: inspection only), in place of
                   ListAgents: counts at every depth, the live ones as a tree, each with its lifecycle
                   (running, waiting on background, stalled, orphaned; completed, failed, stopped), its
                   source (the engine through the bridge, else the disk) and what it does (in Bash 12m,
                   no write 14m); --done N the N ended last, newest first, with their outcome (SendMessage
                   to an agentId resumes it); --depth N the top N levels, a row saying what it folds;
                   --stall MIN (10) the quiet that makes an open turn stalled when only the disk speaks;
                   --json {self, scope, counts, agents, notes}
    sminos find     <words..>                             # list --org <words>: every session they match
    sminos who      [<commit|PR>] [--session S]           # the session a commit (its Sminos-Session trailer)
                   or a PR (its body's last line, else its commits' trailers; a number or URL, through gh)
                   was made by, as it is now: alias, project, machine, state, the session it went on as,
                   how to reach or resume it. Alone, inside a session: the line its commits carry
    sminos projects [--all]                               # every project known here: kind (hub, machine,
                   local), live and waiting sessions, their machines; --all: a retired machine's too
    sminos machines                                       # every machine enrolled in the org: online or
                   last seen, its live sessions and their projects
    sminos chart    [project] [--stopped] [--all] [--width N]        # the members as boxes, grouped by project
    sminos tui      [project] [--all] [--no-tmux]        # the chart, interactive, inside tmux: arrows move, enter attaches
    sminos attach   <seat>                                # claude attach <short>
    sminos migrate  [--quiet]                             # (also runs implicitly)
    sminos meta     get <seat> <field> | set <seat> <field> <value> [<field> <value>...]
                   # read or write a seat record's fields under the record lock (the board pipeline's
                   ticket, role, run_id...); never a credential

A member's name is its alias: a seat's alias (a seat sminos spawns runs under
it as its harness name), or a seat-less session's harness name. Aliases are
display names and can collide; `alias#short` (the session's first eight hex
digits) tells two apart. A seat-less session never takes, from its harness
name, an alias a seat or another current member of its project holds (a
`--bg` copy inherits its source's name): it keeps the alias it has, else its
short. A bare name resolves only in the caller's project (a
seat's own, for a seat); `@short` and `alias#short` reach a session in any
project known here, `project/alias` (a stray: `machine/alias`) one in another;
on a machine not enrolled, from a directory that is no project, a bare name
resolves across every project known here. A seat also answers to
`group/alias`. Scripts may pass a full seat id or session id.

Messaging is one verb, `send`: to a live seat it writes a frame to the
session's inbox socket — the socket the harness's native cross-session
SendMessage tool also rides, wrapped in that tool's own envelope — which the
harness delivers as a peer message (an idle session starts a new turn, a busy
one reads it at its next tool round); a stopped seat is resumed with the
frame as its message. A peer's message always takes the inbox. The owner's
(owner_event) takes a session's bridge (the bridge mod) instead, as the
human's words, submitted once per log event however often it is delivered,
and a --bg job with no bridge takes it through the engine supervisor's
`reply`. `resume` is
the process-level continuation the board pipeline relays through: a fresh
`claude --bg --resume` carrying the invoking environment.

State lives under $SMINOS_HOME (default ~/.claude/sminos; $DAEMON_HOME is the
older name of the same root and is honored). Records are <seat-id>.json at the
root — seat id = the first session's uuid — and the board pipeline reads and
writes them directly under the shared flock file .metalock. A project (a
committed .smns; else, on an enrolled machine, the repository's remote's
project, else the machine's own; else the owning git repository) keeps its
append-only event log, one file per writer, at projects/<id>/log/, with each reader's cursor and
each recipient's delivery record beside it. Names are [A-Za-z0-9._-]{1,64};
`human` is the reserved operator identity.

Exit codes: 0 ok, 1 harness failure, 2 usage (including `wake`, folded into
`send`), 4 unknown seat/group, a target `send` cannot reach (not live, or a
vacant, retired, or gone seat), or a seat that is already filled.
"""

import argparse
import calendar
import datetime
import fcntl
import functools
import glob
import hashlib
import heapq
import http.client
import importlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid as uuidlib
from contextlib import ExitStack, contextmanager
from typing import NamedTuple, NoReturn, Optional

# The oldest Python sminos runs on (its annotations are evaluated: `float |
# None`). The launcher runs the first python3 on PATH, which on a Mac whose
# PATH leads to /usr/bin is macOS's own 3.9: say what fixes it rather than
# fail mid-import. Everything above this line runs on 3.9.
MIN_PYTHON = (3, 10)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(
        "sminos needs Python %d.%d or newer, and %s is %d.%d. Install a newer one (brew install python, or "
        "python.org) and put it first on PATH, or run sminos with it: <that python3> %s ...\n"
        % (MIN_PYTHON[0], MIN_PYTHON[1], sys.executable or "python3", sys.version_info[0], sys.version_info[1],
           os.path.realpath(__file__)))
    sys.exit(1)

# Fleet state is private to the agent fleet: everything this CLI creates is
# 700/600. All agents run as the same OS user, so nothing needs group/other.
os.umask(0o077)

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import sminos_marks  # noqa: E402 — the mark grammar of to-human/hooks/mods/to-human.tsx, ported

LAUNCHER = os.path.join(SCRIPT_DIR, "sminos")
# The engine's permission modes (2.1.300), least permissive first.
PERMISSION_MODES = ("plan", "default", "acceptEdits", "auto", "dontAsk", "bypassPermissions")
PREAMBLE_PATH = os.path.join(SCRIPT_DIR, "..", "references", "spawn-preamble.md")

EXIT_USAGE = 2
EXIT_UNKNOWN = 4

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# A real session uuid, 8-4-4-4-12 hex — used to decide whether a --session value
# names a seat's on-disk identity (and transcript filename) or is junk.
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# A seat's one state word — see state(). FILLED: a live session holds the
# seat. REFILLABLE: no live turn is attached, so a fresh fill may take it.
STATES = ("busy", "idle", "waiting", "stopped", "gone", "vacant", "retired")
FILLED = ("busy", "idle", "waiting")
REFILLABLE = ("vacant", "stopped", "gone")
# HIDDEN is display-only: list, chart, and tui fold these state words.
# A stopped seat can still be resumed by sending to it.
HIDDEN = ("stopped", "retired", "gone")
TERMINAL = ("done", "done-blocked", "blocked", "failed", "stopped", "error")
# Model-visible surfaces never carry a credential: the pipeline colonizes the
# record with run_bearer and friends, and a seat's JSON is read by agents.
SECRET_RE = re.compile(r"bearer|token|secret", re.I)


def public_seat(s):
    """A seat dict with the task body and any secret-shaped field removed —
    for every model-facing surface (list, list --json, chart)."""
    return {k: v for k, v in s.items() if k != "task" and not SECRET_RE.search(k)}


def home_dir():
    return os.path.expanduser("~")


def default_root():
    return os.path.join(home_dir(), ".claude", "sminos")


def root():
    # The tool was `agora`: a leftover $AGORA_HOME would point every consumer at
    # a fresh, empty registry, and dispatchers would launch over live seats.
    if os.environ.get("AGORA_HOME") is not None:
        die("AGORA_HOME is set, but the tool is now sminos — export SMINOS_HOME instead (and unset AGORA_HOME)")
    return os.environ.get("SMINOS_HOME") or os.environ.get("DAEMON_HOME") or default_root()


def now(ms=False):
    """UTC ISO-8601. The log's `ts` carries milliseconds (ms=True); seat
    records keep whole seconds, the shape the board pipeline compares."""
    t = datetime.datetime.now(datetime.timezone.utc)
    if ms:
        return t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg, code=EXIT_USAGE) -> NoReturn:
    sys.stderr.write("sminos: %s\n" % msg)
    sys.exit(code)


def warn(msg):
    sys.stderr.write("sminos: warning: %s\n" % msg)


def note(msg):
    """Something the caller should know that is not a fault: stderr, so a
    stdout contract (--json) is unchanged."""
    sys.stderr.write("sminos: note: %s\n" % msg)


def valid_name(n):
    # '.' and '..' are path segments, not names: they would resolve to the
    # registry root itself. Names that merely contain dots (v1.2) are fine.
    return bool(n) and n not in (".", "..") and bool(NAME_RE.match(n))


def poll_interval():
    return float(os.environ.get("SMINOS_POLL_INTERVAL", "2"))


# ------------------------------------------------------------------ registry


def meta_path(seat_id):
    return os.path.join(root(), seat_id + ".json")


def reply_path(seat_id):
    return os.path.join(root(), seat_id + ".reply.txt")


def err_path(seat_id):
    return os.path.join(root(), seat_id + ".err")


def _write_record(path, data):
    """Atomic replace at the mode the record already has, never at the umask: a
    bookkeeping write on a record carrying the board run bearer would otherwise
    republish that secret world-readable; a record carrying `run_bearer` is
    forced to 0600 either way. A record that does not exist yet gets 0600."""
    tmp = path + ".tmp"
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o600
    if data.get("run_bearer") or mode & 0o077:
        mode = 0o600
    try:
        os.unlink(tmp)  # a tmp left by an earlier crash
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, mode)  # umask narrowing
    os.replace(tmp, path)


def meta_set(seat_id, fields, remove=(), bump=True, create=True, lock_until=None):
    """Merge fields into a seat record (creating it if absent, unless create=False).

    The read-modify-write is serialized across processes with an advisory flock
    on the shared lock file: the board pipeline's own writers take the same
    lock, so concurrent stamps never clobber each other's fields.

    `gen` is the record's lifecycle generation: every lifecycle write (spawn,
    fill, resume, send, retire, seat add, sync's own finalize) bumps it,
    so a finalizer or sync that took its snapshot before, say, a retire can see
    the record moved on and stand down. The agent's own `now` line and raw
    `meta set` are NOT lifecycle writes (bump=False): an agent updating its
    status mid-turn must not make the turn's watcher refuse to record the reply.
    create=False (status / meta set) refuses to resurrect a record that
    a concurrent remove just deleted. Returns True iff it wrote. With
    lock_until (the record hook's migration), the lock is waited for only until
    then: LockBusy, the record untouched.
    """
    path = meta_path(seat_id)
    os.makedirs(root(), exist_ok=True)
    with open(os.path.join(root(), ".metalock"), "a") as lf:
        flock_until(lf, lock_until)
        try:
            try:
                with open(path) as f:
                    data = json.load(f)
            except FileNotFoundError:
                if not create:
                    return False
                data = {}
            except json.JSONDecodeError:
                data = {}
            for k, v in fields.items():
                data[k] = v
            for k in remove:
                data.pop(k, None)
            if bump:
                data["gen"] = int(data.get("gen") or 0) + 1
            _write_record(path, data)
            return True
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def meta_set_if(seat_id, fields, guard, remove=(), reply=None):
    """meta_set, but under the SAME flock re-read the record and apply the
    write only if `guard(data)` holds. Never creates a missing record.

    A `--wait` watcher (or `sync`) took a snapshot minutes ago; while it waited,
    the seat could have been purged, retired, or re-filled into a different
    session. Writing the stale turn's reply/status then would resurrect a purged
    record, undo a retire, or clobber the live occupant. When `reply` is given
    as (turn_id, state, seat_ref) the reply file is written INSIDE the same
    critical section, so a reply can never land next to a record that moved on.
    A successful write bumps `gen`. Returns True if it wrote.
    """
    path = meta_path(seat_id)
    os.makedirs(root(), exist_ok=True)
    with open(os.path.join(root(), ".metalock"), "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            try:
                with open(path) as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return False  # purged or unreadable — never recreate
            if not guard(data):
                return False
            for k, v in fields.items():
                data[k] = v
            for k in remove:
                data.pop(k, None)
            data["gen"] = int(data.get("gen") or 0) + 1
            if not os.path.exists(path):
                return False  # removed under this very lock by a purge — never recreate
            _write_record(path, data)
            if reply is not None:
                record_reply(reply[0], seat_id, reply[1], reply[2])
            return True
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def current_gen(seat_id):
    try:
        return int(meta_get(seat_id, "gen") or 0)
    except (TypeError, ValueError):
        return 0


def same_gen(gen):
    """The guard for a deferred finalize: the record's lifecycle generation is
    the one we snapshotted, and nobody has retired the seat meanwhile (a retire
    is an operator verdict no watcher may overturn)."""
    return lambda data: int(data.get("gen") or 0) == gen and str(data.get("status") or "") != "retired"


def meta_get(seat_id, field):
    try:
        with open(meta_path(seat_id)) as f:
            v = json.load(f).get(field, "")
    except Exception:
        return ""
    return "" if v is None else v


def record_files():
    for p in sorted(glob.glob(os.path.join(root(), "*.json"))):
        if p.endswith(".reply.json"):
            continue
        yield p


def load_seat(path):
    """Load a record and apply read-time fallbacks so no view prints null.

    The state root is persistent and machine-global: records written before a
    field existed (pre-seat daemon metas, v2 nodes) carry none of alias/group/
    role, so every read site goes through here. A seat has one name, its alias:
    `name` reads as the alias, and the `addr` an older record may still carry
    (a second, harness-facing name) is dropped unread.
    """
    with open(path) as f:
        m = json.load(f)
    seat_id = os.path.basename(path)[:-5]
    m["uuid"] = str(m.get("uuid") or seat_id)
    m["seat_id"] = seat_id
    m["alias"] = str(m.get("alias") or m.get("name") or "")
    m["name"] = m["alias"]
    m.pop("addr", None)
    m["group"] = str(m.get("group") or "fleet")
    # A legacy daemon record has NO `current` key: the old resume fallback used
    # the record's own uuid as the session to continue. A v2 converted node has
    # `current` present but empty — a genuinely vacant seat. So the fallback is
    # keyed on the KEY's absence, not on emptiness.
    if "current" not in m:
        m["current"] = seat_id
    for k in ("parent", "role", "brief", "now", "note", "current", "short", "cwd",
              "worktree", "model", "settings", "effort", "task", "host", "boot_id",
              "created", "updated", "engine", "preamble"):
        v = m.get(k)
        m[k] = "" if v is None else str(v)
    m["status"] = str(m.get("status") or "?")
    m["turns"] = str(m.get("turns") or "0")
    try:
        m["gen"] = int(m.get("gen") or 0)
    except (TypeError, ValueError):
        m["gen"] = 0
    try:
        m["attempts"] = int(m.get("attempts") or 1)
    except (TypeError, ValueError):
        m["attempts"] = 1
    m["history"] = m.get("history") if isinstance(m.get("history"), list) else []
    return m


_SEAT_FILES = {}  # record file → ((st_ino, st_size, st_mtime_ns), the seat load_seat read)


def seats(group=None):
    out = []
    for p in record_files():
        s = _seat_at(p)
        if s is not None and (group is None or s["group"] == group):
            out.append(s)
    return out


def _seat_at(path):
    """load_seat, the file read again only once it changed (a record is
    written by atomic replace: a new inode), as a copy the caller may change;
    None for a file that is no seat (unparsable, or half-written). The
    daemon and the uplink read every seat many times a minute."""
    try:
        st = os.stat(path)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        held = _SEAT_FILES.get(path)
        if held is None or held[0] != key:
            held = _SEAT_FILES[path] = (key, load_seat(path))
    except Exception:
        _SEAT_FILES.pop(path, None)
        return None
    return {**held[1], "history": list(held[1]["history"])}


def find_seat(q, scope=None):
    """Resolve a query to a seat WITHOUT printing or exiting.

    Returns ("ok", seat) | ("none", None) | ("ambiguous", [seats]). Order:
    `group/alias`, else `project/alias` (by the project's name or id); an
    exact seat id or session id (how scripts address a seat); a bare alias
    when exactly one seat has it — among the seats of `scope`, the caller's
    project, when one is given. Nothing is matched by prefix and the harness
    short id names no seat, so a short alias such as `a` is never lost to an
    id that happens to start with it.
    """
    if not q:
        return "none", None
    all_seats = seats()
    if "/" in q:
        g, a = q.split("/", 1)
        hits = [s for s in all_seats if s["group"] == g and s["alias"] == a]
        if not hits:
            hits = [s for s in all_seats if s["alias"] == a and (p := seat_project(s)) and g in (p.id, p.name)]
        if len(hits) > 1:
            return "ambiguous", hits
        return ("ok", hits[0]) if hits else ("none", None)
    stages = (
        lambda s: q in (s["seat_id"], s["current"]),
        lambda s: s["alias"] == q and (scope is None or seat_project(s).id == scope.id),
    )
    for match in stages:
        hits = [s for s in all_seats if match(s)]
        if len(hits) == 1:
            return "ok", hits[0]
        if hits:
            return "ambiguous", hits
    return "none", None


# --------------------------------------------------------- projects and the log
#
# A project is the unit of shared work state: a committed `.smns` names it; on
# a machine enrolled at a desk hub, any other directory is in the machine's own
# project; elsewhere a git repository without one is a local project named
# after its owning repository, and any other directory is no project. Everything that crosses
# sessions is one event in the project's append-only log — one file per
# writer under $SMINOS_HOME/projects/<id>/log/, so a file has one writer and
# replication is a copy. Delivery is the deliverer's own record (delivered/),
# never a rewrite of the log. Design: docs/doperpowers/specs/
# 2026-10-13-smns-project-log-design.md.


class Project(NamedTuple):
    id: str          # uuid from .smns, one derived from a remote or a machine, or "local-<name>"
    name: str
    remote: str      # the log's git archive, "" for none (never the repository's remote)
    root: str        # directory holding .smns, or the owning repository
    home: str        # $SMINOS_HOME/projects/<id>
    hub: Optional[dict] = None  # .smns's {url, org}: synced through the desk hub, never through git


SMNS = ".smns"
# The conversation `chat` shows and a frame's `unread` counts.
CHAT_KINDS = ("say", "human")
# A push that failed before anything was written is retried this many times,
# then settled with a line in $SMINOS_HOME/daemon.log.
DELIVERY_ATTEMPTS = 60
PUSHED = ("sent", "woken", "sent?", "woken?")
# A session's membership is its latest of these, in its own file, by seq.
MEMBERSHIP = ("joined", "retired")
# The facts about a session the projection reads; whoever writes one for a
# session on its machine appends it to that session's file.
LIFECYCLE = MEMBERSHIP + ("renamed", "state", "titled", "in-charge", "status")
# The harness session kinds that are members on sight; any other is not.
JOINABLE_KINDS = ("interactive", "bg")
# A headless or SDK run (`claude -p`, the agent SDKs) registers as
# `interactive` too (harness 2.1.299: `kind: "interactive", entrypoint:
# "sdk-cli"`); its entrypoint is what tells it apart, and it is no member.
HEADLESS_ENTRYPOINT = "sdk"
# Unless the host that launched it marks it as one: an app whose sessions are
# its human's work (MAWS) sets this in the environment of each engine it
# spawns, to its own pid. The harness record carries no environment, so the
# mark is read only inside the session's own process tree (its hooks, its
# bridge's child, a verb its tools run), and it holds only for an engine the
# process it names spawned itself: a run started from inside a marked
# session inherits the variable, not that parent (member_mark). Internal
# forks still never join: SMNS_INTERNAL and the pid marker are read first.
MEMBER_MARK = "SMNS_MEMBER"
# The name sources the harness makes up itself (harness 2.1.300): `derived`,
# the directory's name and one random byte drawn again by every process;
# `auto`, a title it wrote; `collision`, a given name it suffixed because
# another live session held it. Any other source is a name someone gave.
GENERATED_NAMES = ("derived", "auto", "collision")
_PROJECTS = {}
_SEAT_PROJECTS = {}  # (session, recorded cwd) → a seat's project, per cache generation (seat_project)
_RECORD_PROJECTS = {}  # (session, record's cwd) → its project, per cache generation (record_project)
_REPO_BRANCH = {}    # cwd → (repository, branch), per cache generation (repo_branch)
_REPO_REMOTE = {}    # common git dir → its Derivation, per cache generation (derivation)
_DERIVED = {}        # remote-derived project id → its remote key, as derived in this process (repo_project)
_HOMES = set()
_VIEWS = {}  # project id → View, per invocation; a lifecycle append drops it


def projects_root():
    return os.path.join(root(), "projects")


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name)[:64]
    return name if valid_name(name) else ""


def _common_git_dir_fs(d):
    """common_git_dir read off the filesystem, no process: the nearest `.git`
    upward — a directory is it; a file (a linked worktree) points at its
    gitdir, whose `commondir` leads to the main checkout's. "" outside git;
    None when the layout is not one of those, for the caller to ask git."""
    while True:
        dot = os.path.join(d, ".git")
        if os.path.isdir(dot):
            return dot
        if os.path.isfile(dot):
            try:
                with open(dot) as f:
                    line = f.readline().strip()
            except OSError:
                return None
            if not line.startswith("gitdir:"):
                return None
            gitdir = os.path.join(d, line[len("gitdir:"):].strip())
            try:
                with open(os.path.join(gitdir, "commondir")) as f:
                    common = os.path.join(gitdir, f.read().strip())
            except FileNotFoundError:
                common = gitdir
            except OSError:
                return None
            return os.path.abspath(common)
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def common_git_dir(cwd):
    """The common git dir of a directory's checkout — for a linked worktree,
    the main checkout's — asked of its nearest existing ancestor, so a
    removed worktree still resolves. "" outside git. Read off the filesystem
    when it can be: every reading verb resolves the cwd of every seat and
    live session, and a process per directory adds up."""
    d = os.path.abspath(cwd)
    while not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent
    common = _common_git_dir_fs(d)
    if common is not None:
        return common
    try:
        p = subprocess.run(["git", "-C", d, "rev-parse", "--git-common-dir"],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    common = p.stdout.strip() if p.returncode == 0 else ""
    if not common:
        return ""
    return os.path.abspath(common if os.path.isabs(common) else os.path.join(d, common))


def owning_repo(cwd):
    """The owning repository of a directory — for a linked worktree, the main
    checkout — the directory holding its common git dir. "" outside git."""
    common = common_git_dir(cwd)
    return os.path.dirname(common) if common else ""


def make_project(pid, name, remote, root_dir, hub=None):
    return Project(pid, name, remote, root_dir, os.path.join(projects_root(), pid), hub)


def read_smns(path):
    """(id, name, remote, hub) from a .smns, or None — with a warning — when it
    is unreadable or names no valid id: a broken file in one repository must
    not stop every verb that resolves a seat living there. `hub` is the file's
    {url, org} as written — `url` "" when it names none, the shape a new hub
    project takes (its URL is the enrollment's: hub_here) — or None. A `hub`
    key that names no org — null included — still makes a hub project, which
    git never syncs and no hub feeds (hub_wellformed), with a warning: two
    live transports are worse than none."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        warn("ignoring unreadable %s: %s" % (path, e))
        return None
    pid = str(d.get("project") or "") if isinstance(d, dict) else ""
    if not valid_name(pid):
        warn("ignoring %s: it names no valid project id" % path)
        return None
    hub = None
    if "hub" in d:
        raw = d["hub"] if isinstance(d["hub"], dict) else {}
        hub = {k: raw[k] if isinstance(raw.get(k), str) else "" for k in ("url", "org")}
        if not hub_wellformed(hub):
            warn("%s: its hub names no org; the project syncs through neither git nor a hub until it does" % path)
            hub = {"url": "", "org": ""}  # a hub project nothing feeds
    return pid, str(d.get("name") or pid), str(d.get("remote") or ""), hub


def names_hub(root, pid):
    """Whether the .smns at `root`, read as it is now, is project `pid`'s and
    names a hub (well-formed or not: either bars git)."""
    path = os.path.join(root, SMNS) if root else ""
    smns = read_smns(path) if path and os.path.isfile(path) else None
    return smns is not None and smns[0] == pid and smns[3] is not None


def registration(pid):
    """A project's project.json as it is now (project_path), or {}."""
    try:
        with open(os.path.join(projects_root(), pid, "project.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def hub_wellformed(hub):
    """Whether a .smns `hub` names an org (a non-empty string), its `url`
    absent or a string: the only hub a project syncs through. Any other value
    still bars git."""
    return isinstance(hub, dict) and isinstance(hub.get("org"), str) and bool(hub["org"]) \
        and isinstance(hub.get("url", ""), str)


def hub_synced(hub):
    """Whether a project's hub, as this machine resolved it (hub_here), is one
    this machine syncs through: its org's, with the enrollment's URL. A hub
    project of an org this machine is not enrolled in has url "" — local here,
    with a hub marker."""
    return hub_wellformed(hub) and bool(hub.get("url"))


# ------------------------------------------- the enrollment and the org's directory
#
# On an enrolled machine (daemon/hub.json names a hub, an org and a machine)
# a .smns names only the org; the URL is the enrollment's, so moving the hub
# never means editing committed files. Every session there is in a project the
# hub syncs: a directory no .smns claims is in the machine's own project. The
# uplink keeps the hub's latest `org` frame — every project of the org, with
# its kind and whether it is retired, and every enrolled machine — at
# daemon/org.json, the one local source of a project's kind and retirement.
# Design: docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md §1–§3.

ORG_FILE = "org.json"
WARNED_URL = "warned-url"   # in a project's home: its .smns url, differing from the enrollment's, was said
HINTED = "hinted"           # in a project's home: when the not-enrolled hint was last said (its mtime)
HINT_EVERY = 86400
# Set by main() for the verbs a person reads: only they print the daily hint,
# so a hook or the daemon never spends it.
HINTS = {"on": False}
READING_VERBS = ("list", "find", "who", "chat", "projects", "machines", "project", "chart")
_ENROLLED = []   # [the enrollment or None], per invocation
_ORG_DIR = []    # [daemon/org.json as read or None], per invocation
_SAID = set()    # (marker, project id) said or checked in this invocation


def enrollment():
    """This machine's enrollment as resolution reads it, {url, org, machine}:
    on a machine cut over to its endpoint, daemon/identity.json's (RL10's
    welcome, sminos_rl10.cutover); else daemon/hub.json's; None when it is
    not enrolled (hub.json absent, unreadable, or lacking one of the three)."""
    if not _ENROLLED:
        ident = sibling_module("sminos_rl10").cutover()
        if ident is not None:
            _ENROLLED.append({"url": ident["hub"], "org": ident["org"], "machine": ident["name"]})
            return _ENROLLED[0]
        try:
            with open(os.path.join(root(), "daemon", "hub.json")) as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = None
        ok = isinstance(d, dict) and all(isinstance(d.get(k), str) and d[k] for k in ("hub", "org", "machine"))
        _ENROLLED.append({"url": d["hub"], "org": d["org"], "machine": d["machine"]} if ok else None)
    return _ENROLLED[0]


def machine_project_id(org, machine):
    """The id of an enrolled machine's own project: a UUID v5 of the org and
    the machine's name, lower-cased as the hub compares names (the hub
    computes the same; tests/machine-project-id.json pins both)."""
    return str(uuidlib.uuid5(uuidlib.NAMESPACE_URL, "smns-machine:%s:%s" % (org, machine.lower())))


def machine_project(org, machine):
    """The machine project of `machine` in `org`: named after the machine, no
    checkout anywhere (root ""), synced through the enrollment's hub."""
    e = enrollment()
    url = e["url"] if e and e["org"] == org else ""
    return make_project(machine_project_id(org, machine), machine, "", "", {"url": url, "org": org})


def own_machine_project():
    """This machine's own project, the project of every session here no .smns
    claims; None on a machine that is not enrolled."""
    e = enrollment()
    return machine_project(e["org"], e["machine"]) if e else None


def org_path():
    return os.path.join(root(), "daemon", ORG_FILE)


def org_directory():
    """daemon/org.json — {projects, machines, at} as the uplink kept the hub's
    latest `org` frame — or None before the first (or when it is unreadable)."""
    if not _ORG_DIR:
        try:
            with open(org_path()) as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = None
        ok = isinstance(d, dict) and isinstance(d.get("projects"), list) and isinstance(d.get("machines"), list)
        _ORG_DIR.append({"projects": [p for p in d["projects"] if isinstance(p, dict) and isinstance(p.get("id"), str)],
                         "machines": [m for m in d["machines"] if isinstance(m, dict) and isinstance(m.get("name"), str)],
                         "at": str(d.get("at") or "")} if ok else None)
    return _ORG_DIR[0]


def org_entry(pid):
    """The org directory's entry for a project, or None."""
    d = org_directory()
    return next((p for p in d["projects"] if p["id"] == pid), None) if d else None


def org_retired(pid):
    """Whether the org's directory marks the project retired (a revoked
    machine's project). With no directory yet, nothing is."""
    return (org_entry(pid) or {}).get("retired") is True


def said_once(pid, marker):
    """Whether the marker file in the project's home already holds — made
    now when it did not (O_EXCL: one verb says it, whichever comes first)."""
    if (marker, pid) in _SAID:
        return True
    _SAID.add((marker, pid))
    home = os.path.join(projects_root(), pid)
    try:
        os.makedirs(home, mode=0o700, exist_ok=True)
        os.close(os.open(os.path.join(home, marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except OSError:
        return True   # held already; or a marker that cannot be made, which says nothing rather than every time
    return False


def hint_due(pid):
    """Whether the daily not-enrolled hint is due for the project, marking it
    said when it is (the marker's mtime is when)."""
    if (HINTED, pid) in _SAID:
        return False
    _SAID.add((HINTED, pid))
    path = os.path.join(projects_root(), pid, HINTED)
    try:
        if time.time() - os.stat(path).st_mtime < HINT_EVERY:
            return False
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w"):
            pass
        os.utime(path)
    except OSError:
        return False
    return True


def hub_here(pid, name, hub):
    """A .smns hub as this machine syncs it: on a machine enrolled in its org,
    {url, org} with the enrollment's URL — a different `url` in the file is
    said once per project here (stderr and daemon.log) and never used, since
    refusing would make a committed file an outage; elsewhere {url: "", org}:
    a local project with a hub marker, which git never syncs and no uplink
    opens, and which a reading verb says so of once a day."""
    if not hub_wellformed(hub):
        return hub
    e = enrollment()
    if e is None or e["org"] != hub["org"]:
        if HINTS["on"] and hint_due(pid):
            warn("project %s syncs through the desk hub of org %s; this machine is not enrolled%s "
                 "(sminos hub enroll)" % (name, hub["org"], " in it" if e else ""))
        return {"url": "", "org": hub["org"]}
    if hub["url"] and hub["url"] != e["url"] and not said_once(pid, WARNED_URL):
        line = ("project %s: its .smns names the hub %s, but this machine is enrolled at %s for org %s; "
                "the enrollment's is used (drop `url` from .smns)" % (name, hub["url"], e["url"], e["org"]))
        warn(line)
        try:
            daemon_log(line)
        except OSError:
            pass
    return {"url": e["url"], "org": hub["org"]}


def smns_at(cwd):
    """(directory, read_smns) of the first .smns walking up from cwd; else,
    for a linked worktree at a head that predates the file, its main
    checkout's (owning_repo), so an old branch never splits the repository
    into two projects; else None."""
    d = cwd
    while True:
        path = os.path.join(d, SMNS)
        smns = read_smns(path) if os.path.isfile(path) else None
        if smns:
            return d, smns
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    repo = owning_repo(cwd)
    path = os.path.join(repo, SMNS) if repo else ""
    smns = read_smns(path) if path and os.path.isfile(path) else None
    return (repo, smns) if smns else None


# ------------------------------------------- a repository's project, by its remote
#
# On an enrolled machine a repository no .smns claims is a hub project by its
# remote: its id a function of the org and the remote's normalized form (its
# remote key), so the same repository on any machine, in any clone or
# worktree, is one project with nothing committed. The remote is `origin`,
# else the only one; several and none named origin, none at all, or a local
# path derive nothing, and the session is a stray in the machine project. Read
# from the common git dir's config, no process. A .smns still wins: it is how
# a project is declared rather than inferred.
# Design: docs/doperpowers/specs/2026-10-19-smns-remote-identity-design.md §1–§4.

REMOTE_SCHEMES = {"ssh": 22, "git+ssh": 22, "ssh+git": 22, "git": 9418, "http": 80, "https": 443}  # their default ports
WARNED_REMOTE = "warned-remote"   # in a project's home: its root's remote changed under it, was said
REMOTE_FILE = "remote.json"       # in a remote-derived project's home: {"key"}, the remote key its id derives from
_URL_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*)://([^/]*)(/.*)?", re.S)
_HELPER_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*::")   # git's `<transport>::<address>`
_AUTHORITY_RE = re.compile(r"(\[[^\]/]+\]|[^\[\]:/]*)(?::([0-9]*))?")
_SCP_RE = re.compile(r"(?:[^@/]*@)?(\[[^\]/]+\]|[^\[\]:/@]+):(.*)", re.S)
_GIT_SECTION_RE = re.compile(r'\[([A-Za-z0-9.-]+)(?:\s+"((?:[^"\\\n]|\\[^\n])*)")?\]')
_GIT_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
_GIT_ESCAPES = {"t": "\t", "b": "\b", "n": "\n", "\\": "\\", '"': '"'}


def _git_value(s, i):
    """A git config value from s[i] to its line's end, read as git's
    parse_value reads it — blanks around it dropped and each blank inside one
    space, quotes, escapes, `#`/`;` comments, a trailing `\\` continuing it
    on the next line — and where the next line starts; None for one git
    refuses."""
    out, quote, comment, space, n = "", False, False, 0, len(s)
    while i < n:
        c = s[i]
        i += 1
        if c == "\n":
            return (None if quote else out), i
        if comment:
            continue
        if c in " \t\r\v\f" and not quote:
            space += 1 if out else 0
            continue
        if c in ";#" and not quote:
            comment = True
            continue
        out, space = out + " " * space, 0
        if c == "\\":
            c = _GIT_ESCAPES.get(s[i]) if i < n and s[i] != "\n" else ("" if i < n else None)
            i += 1
            if c is None:
                return None, i
        elif c == '"':
            quote = not quote
            continue
        out += c
    return (None if quote else out), i


def git_config_remotes(text):
    """{remote name: its first `url`, "" for none} of a git config file's
    text, in the order it names them, read as git's config parser reads it:
    section names case-blind, subsections not, the deprecated
    `[remote.name]` form, quoted and escaped values, comments, continued
    lines. `include` and `includeIf` are not followed. None for a text git
    itself would refuse."""
    s = text.replace("\r\n", "\n")
    out, section, sub, i, n = {}, "", None, 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
        elif c in "#;":
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
        elif c == "[":
            m = _GIT_SECTION_RE.match(s, i)
            if not m:
                return None
            section, sub = m.group(1).lower(), m.group(2)
            if sub is not None:
                sub = re.sub(r"\\(.)", r"\1", sub)
            elif "." in section:
                section, _, sub = section.partition(".")
            i = m.end()
        else:
            m = _GIT_KEY_RE.match(s, i)
            if not m:
                return None
            key, i = m.group(0).lower(), m.end()
            while i < n and s[i] in " \t":
                i += 1
            value = None
            if i < n and s[i] == "=":
                value, i = _git_value(s, i + 1)
                if value is None:
                    return None
            elif i < n and s[i] != "\n":
                return None
            if section == "remote" and sub:
                out.setdefault(sub, None)
                if key == "url" and out[sub] is None:
                    out[sub] = value or ""
    return {k: v or "" for k, v in out.items()}


def parse_remote(url):
    """(host[:port], path, "") of a remote URL in one of git's two network
    forms — `scheme://[user[:pass]@]host[:port]/path` for ssh, git and
    http(s), and the scp-like `[user@]host:path` — the userinfo dropped, the
    host lower-cased, a port kept only when it is not the scheme's default,
    the path with repeated `/` collapsed and its leading and trailing `/` and
    one trailing `.git` dropped, its case as written. Else ("", "", why): a
    local path (git's own rule: no colon, or a `/` before the first),
    `file://`, a transport helper's address, any other scheme, an empty host
    or path. The why never quotes the URL, which may carry a credential."""
    url = (url or "").strip()
    if not url:
        return "", "", "names no url"
    m = _URL_RE.fullmatch(url)
    if m:
        scheme = m.group(1).lower()
        if scheme == "file":
            return "", "", "is a local path, which names nothing another machine can agree on"
        hp = _AUTHORITY_RE.fullmatch(m.group(2).rpartition("@")[2]) if scheme in REMOTE_SCHEMES else None
        if not hp or not hp.group(1):
            return "", "", "has a url that is neither scheme://host/path (ssh, git, http, https) nor host:path"
        host, port = hp.group(1).lower(), hp.group(2)
        if port and int(port) != REMOTE_SCHEMES[scheme]:
            host += ":%d" % int(port)
        path = m.group(3) or ""
    elif _HELPER_RE.match(url):
        return "", "", "has a url that is neither scheme://host/path (ssh, git, http, https) nor host:path"
    else:
        colon, slash = url.find(":"), url.find("/")
        if colon < 0 or 0 <= slash < colon:
            return "", "", "is a local path, which names nothing another machine can agree on"
        s = _SCP_RE.fullmatch(url)
        if not s:
            return "", "", "has a url that is neither scheme://host/path (ssh, git, http, https) nor host:path"
        host, path = s.group(1).lower(), s.group(2)
    path = re.sub(r"/{2,}", "/", path).strip("/")
    if path[-4:].lower() == ".git":
        path = path[:-4].rstrip("/")
    return (host, path, "") if path else ("", "", "has a url that names no repository path")


def remote_key(url):
    """The remote key of a remote URL — `host[:port]/path`, the path
    lower-cased as GitHub, GitLab, Bitbucket and Gitea compare it, so
    `git@github.com:SSFSKIM/MAWS.git` and `https://github.com/ssfskim/maws`
    are one key — or "" for a URL that derives no project (parse_remote)."""
    host, path, _ = parse_remote(url)
    return "%s/%s" % (host, path.lower()) if host else ""


def remote_name(url):
    """The name a remote gives its project: the last segment of its path as
    written (`MAWS`, `ci-kit`), through safe_name; "" for a URL that
    derives no project."""
    host, path, _ = parse_remote(url)
    return (safe_name(path.rsplit("/", 1)[-1]) or "repo") if host else ""


def repo_project_id(org, key):
    """The id of the project a remote key derives in an org: a UUID v5 of
    both, the machine project's construction under another prefix
    (tests/remote-key.json pins it). The org is in it, so a repository is a
    project per org, as a machine is."""
    return str(uuidlib.uuid5(uuidlib.NAMESPACE_URL, "smns-repo:%s:%s" % (org, key)))


class Derivation(NamedTuple):
    repo: str     # the owning repository's main checkout, "" outside git
    remote: str   # the remote the project derives from, "" when none does
    key: str      # its remote key, "" when the repository derives no project
    name: str     # the project's name, as the remote writes it
    why: str      # why the repository derives no project, as `project show` says it


def derivation(cwd, fresh=False):
    """How a directory's repository derives a project from its remote: the
    remote `origin`, else the only one, its first `url` (`pushurl` and
    `insteadOf` aside), read from the common git dir's config, so a linked
    worktree reads its main checkout's. Kept per repository for the cache
    generation; `fresh` reads the config as it is now."""
    common = common_git_dir(os.path.abspath(os.path.expanduser(cwd or ".")))
    if not common:
        return Derivation("", "", "", "", "no git repository")
    if fresh or common not in _REPO_REMOTE:
        _REPO_REMOTE[common] = _derive(os.path.dirname(common), common)
    return _REPO_REMOTE[common]


def _derive(repo, common):
    try:
        with open(os.path.join(common, "config"), encoding="utf-8-sig", errors="replace") as f:
            remotes = git_config_remotes(f.read())
    except FileNotFoundError:
        remotes = {}
    except OSError:
        remotes = None
    if remotes is None:
        return Derivation(repo, "", "", "", "its git config is not one git reads")
    if not remotes:
        return Derivation(repo, "", "", "", "the repository has no remote — add one, or `sminos project init --hub`")
    if "origin" not in remotes and len(remotes) > 1:
        return Derivation(repo, "", "", "", "remotes %s, none named origin — name one origin, or `sminos project init --hub`"
                          % ", ".join("`%s`" % r for r in remotes))
    remote = "origin" if "origin" in remotes else next(iter(remotes))
    host, path, why = parse_remote(remotes[remote])
    if not host:
        return Derivation(repo, remote, "", "", "remote `%s` %s — `sminos project init --hub` declares a project"
                          % (remote, why))
    return Derivation(repo, remote, "%s/%s" % (host, path.lower()), safe_name(path.rsplit("/", 1)[-1]) or "repo", "")


def repo_project(cwd, fresh=False):
    """On an enrolled machine, the hub project a directory's repository
    derives from its remote (derivation), rooted at the main checkout and
    synced through the enrollment's hub. Its name is the one its id already
    has — the org directory's (the hub keeps the name of the first hello
    that registered it), else this machine's registration — and only for a
    project new to both the remote's own spelling: two clones that spell one
    remote differently (`SSFSKIM/MAWS`, `ssfskim/maws`) are one project
    under one name. None on a machine not enrolled, or for a repository that
    derives none."""
    e = enrollment()
    if e is None:
        return None
    d = derivation(cwd, fresh)
    if not d.key:
        return None
    pid = repo_project_id(e["org"], d.key)
    _DERIVED[pid] = d.key
    held = registration(pid)
    name = str((org_entry(pid) or {}).get("name") or held.get("name") or d.name)
    project = make_project(pid, name, "", d.repo, {"url": e["url"], "org": e["org"]})
    if not held.get("root"):
        remote_moved(project, d.key)
    return project


def derived_key(pid):
    """The remote key a project registered here was derived from (its
    REMOTE_FILE), or ""."""
    try:
        with open(os.path.join(projects_root(), pid, REMOTE_FILE)) as f:
            key = json.load(f).get("key")
    except (OSError, ValueError, AttributeError):
        return ""
    return key if isinstance(key, str) else ""


def remote_moved(project, key):
    """Say once per project (stderr from the verb that sees it, a daemon.log
    line; WARNED_REMOTE in its home) that a remote-derived project registered
    at `project`'s root is that repository's project no more: the remote's
    key changed under it (`git remote set-url`, a clone renamed), so its
    sessions there move to `project`. Looked for by repo_project only while
    `project` has no checkout registered here, the first sight of the new
    key: once it has one, the old project was said already, or never stood
    at a root here."""
    for path in sorted(glob.glob(os.path.join(projects_root(), "*", "project.json"))):
        pid = os.path.basename(os.path.dirname(path))
        held = registration(pid) if pid != project.id else {}
        if str(held.get("root") or "") != project.root:
            continue
        old = derived_key(pid)
        if not old or old == key or said_once(pid, WARNED_REMOTE):
            continue
        line = ("project %s (%s): the remote of %s is now %s, not %s, so its sessions there move to project %s (%s); "
                "a .smns pins a project against its remote: `sminos project init --hub`, run before a remote changes"
                % (held.get("name") or pid, pid, project.root, key, old, project.name, project.id))
        warn(line)
        try:
            daemon_log(line)
        except OSError:
            pass


def project_source(cwd):
    """Where resolve_project finds a directory's project, as `project show`
    says it: `.smns at <dir>`, `remote <name> → <key>`, the machine project
    and why no remote derives one, or a machine not enrolled's local project."""
    cwd = os.path.abspath(os.path.expanduser(cwd or "."))
    found = smns_at(cwd)
    if found:
        return ".smns at %s" % found[0]
    d = derivation(cwd)
    if enrollment() is None:
        return "the repository at %s, a local project: this machine is not enrolled" % d.repo if d.repo else "-"
    return "remote %s → %s" % (d.remote, d.key) if d.key else "machine project: %s" % d.why


def resolve_project(cwd, fresh=False):
    """The project of a directory: the first .smns walking up (a linked
    worktree without one, its main checkout's); else, on an enrolled
    machine, the project its repository's remote derives (repo_project),
    else the machine's own project; else the local project of the owning
    git repository; else None (no project). Kept for the cache generation;
    `fresh` reads the directory as it is now."""
    cwd = os.path.abspath(os.path.expanduser(cwd or "."))
    if not fresh and cwd in _PROJECTS:
        return _PROJECTS[cwd]
    project = None
    found = smns_at(cwd)
    if found:
        d, (pid, name, remote, hub) = found
        project = make_project(pid, name, remote, d, hub_here(pid, name, hub))
    else:
        project = repo_project(cwd, fresh) or own_machine_project()
        if project is None:
            repo = owning_repo(cwd)
            if repo:
                name = safe_name(os.path.basename(repo)) or "repo"
                project = make_project("local-" + name, name, "", repo)
    _PROJECTS[cwd] = project
    return project


def seat_project(seat, fresh=False):
    """A seat's project, from its recorded cwd. A seat spawned where there is
    no project belongs to the local project named after that directory: the
    seat record is the explicit registration automatic discovery never makes.
    A record with no cwd at all (written by hand, or before cwd was recorded)
    belongs to the local project named after its group, so it stays in view.
    Its directory is its session's launch directory (seat_cwd: where the
    engine last moved it, the recorded cwd until its transcript names one);
    a seat cannot join elsewhere.

    Kept for the cache generation (forget_caches): a reconciliation asks it
    of every seat for every project, and the daemon reconciles every project
    each tick. What a stale answer would decide is written only once the
    write's guard has asked again with `fresh` — the .smns, the transcript
    and the join override read as they are now (_reconcile)."""
    if not seat:
        return None
    cwd = str(seat.get("cwd") or "")
    if not cwd:
        name = safe_name(str(seat.get("group") or "")) or "fleet"
        return make_project("local-" + name, name, "", "")
    key = (str(seat.get("current") or ""), cwd)
    if not fresh and key in _SEAT_PROJECTS:
        return _SEAT_PROJECTS[key]
    project = session_project(key[0], seat_cwd(seat, fresh), fresh)
    if project is None:
        name = safe_name(os.path.basename(os.path.normpath(cwd))) or "fleet"
        project = make_project("local-" + name, name, "", os.path.abspath(cwd))
    _SEAT_PROJECTS[key] = project
    return project


def seat_cwd(seat, fresh=False):
    """The directory a seat's session runs in, as a session's: its launch
    directory (launch_cwd; `fresh`, its transcript looked for as the
    directories are now), the seat's recorded cwd — where its spawner
    launched it — standing in until the transcript names one."""
    cwd = str(seat.get("cwd") or "")
    sid = str(seat.get("current") or "")
    return launch_cwd(sid, fallback=cwd, fresh=fresh) if sid and cwd else cwd


def write_json(path, data, mode=0o600):
    """Atomic replace: a reader sees the old file or the new one, never half."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def kept_root(project, held):
    """The root project_path registers a rooted project at, given the
    registration `held`: its registered root when that differs from the
    project's own and, as the directories are now, still resolves to this
    very project (another clone of the repository, another checkout of the
    .smns, its name and hub the same); else the project's own."""
    root = str(held.get("root") or "") if isinstance(held, dict) else ""
    if not project.root or not root or root == project.root or not os.path.isdir(root):
        return project.root
    there = resolve_project(root)
    return root if there is not None and there._replace(root=project.root) == project else project.root


def project_path(project, *parts):
    """A path under the project's home; the first use creates the home and
    records project.json (the .smns as last resolved, plus its root) — the
    registration both transports read, the tick's git phases and the uplink.
    Every checkout of a project shares its log, so a hub named in one of them
    holds the registration while that checkout's .smns still names it: a
    checkout whose .smns names none (a worktree from before the conversion)
    does not take it back to git. A registration to change is read, checked
    and written under project.json.lock (a leaf: nothing is taken while it is
    held), so a conversion registering meanwhile is never written over. A
    second checkout of a project here (another clone of its repository)
    leaves the registered root standing while that root is still the
    project's (kept_root). A remote-derived project's home records the key
    its id derives from (REMOTE_FILE), for remote_moved."""
    if project.id not in _HOMES:
        os.makedirs(os.path.join(project.home, "log"), mode=0o700, exist_ok=True)
        path = os.path.join(project.home, "project.json")

        def held_now():
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None

        def info_for(held):
            info = {"project": project.id, "name": project.name, "remote": project.remote,
                    "root": kept_root(project, held)}
            if project.hub is not None:
                info["hub"] = project.hub
            return info

        held = held_now()
        if held != info_for(held):
            with flocked(path + ".lock"):
                held = held_now()
                info = info_for(held)
                hub_elsewhere = project.hub is None and isinstance(held, dict) and held.get("hub") is not None \
                    and str(held.get("root") or "") != project.root \
                    and names_hub(str(held.get("root") or ""), project.id)
                # A project known without a checkout (one the org's directory
                # names, read before its checkout registered) never takes the
                # root away: no checkout resolves to a rootless project.
                root_kept = not project.root and isinstance(held, dict) and bool(held.get("root"))
                if held != info and not hub_elsewhere and not root_kept:
                    write_json(path, info)
        key = _DERIVED.get(project.id)
        if key and derived_key(project.id) != key:
            write_json(os.path.join(project.home, REMOTE_FILE), {"key": key})
        _HOMES.add(project.id)
    path = os.path.join(project.home, *parts)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    return path


def register_if_absent(project):
    """Register a project known here without a checkout (the org's
    directory names it): project.json written only when there is none,
    checked and written under the lock project_path takes, so a registration
    a CLI or hook makes meanwhile — with its real root — is kept."""
    path = os.path.join(project.home, "project.json")
    os.makedirs(os.path.join(project.home, "log"), mode=0o700, exist_ok=True)
    with flocked(path + ".lock"):
        if registration(project.id):
            return
        info = {"project": project.id, "name": project.name, "remote": project.remote, "root": project.root}
        if project.hub is not None:
            info["hub"] = project.hub
        write_json(path, info)


def known_projects(all_seats=None):
    """Every project this machine knows: those with a home here, and those of
    the seats it holds (`all_seats`: a seat read the caller already made)."""
    out = {}
    for path in sorted(glob.glob(os.path.join(projects_root(), "*", "project.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
            pid = str(d["project"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if valid_name(pid) and os.path.basename(os.path.dirname(path)) == pid:
            out[pid] = make_project(pid, str(d.get("name") or pid), str(d.get("remote") or ""), str(d.get("root") or ""),
                                    d["hub"] if isinstance(d.get("hub"), dict) else None)
    for s in seats() if all_seats is None else all_seats:
        p = seat_project(s)
        if p:
            out.setdefault(p.id, p)
    return list(out.values())


def project_tiers(q):
    """The projects `q` names, in the order a name is looked up in them: its
    id alone; else, by name, the hub project, then the machine project; the
    rest (local-* and git-mirrored ones) only when neither has the name, so a
    local project named after its repository never shadows the repository's
    hub project. [] when none has it; an ambiguous name exits. A verb takes
    the first (find_project); a tag `@<q>/<alias>` reads the next only when
    the first has no such member — a team names its project deliberately and
    a machine is named after a host, so the project is the likelier meaning."""
    out, clash = _name_tiers(q)
    if clash:
        die("ambiguous project '%s': %s" % (q, ", ".join(sorted("%s (%s)" % (p.name, p.id) for p in clash))),
            EXIT_UNKNOWN)
    return out


def _name_tiers(q):
    """(tiers, clash): project_tiers' lookup, and the projects of the first
    tier it consults that holds several (the tiers before it in `tiers`),
    rather than an exit."""
    known = known_projects()
    hits = [p for p in known if p.id == q]
    if hits:
        return hits[:1], []
    named = [p for p in known if p.name == q]
    out = []
    for kind in ("hub", "machine", "local"):
        if kind == "local" and out:
            break   # a tier never consulted: its ambiguity is no one's
        hits = [p for p in named if project_kind(p) == kind]
        if len(hits) > 1:
            return out, hits
        out += hits
    return out, []


def tag_project(p):
    """How a tag names project `p`: by its name when the name reaches it (a
    tier project_tiers consults for it; `@<name>/alias#short` reads them in
    turn until one holds the member), else by its id — a `local-*` or
    git-mirrored project named as a hub or machine project is, or one whose
    name several projects share."""
    tiers, clash = _name_tiers(p.name)
    return p.name if not clash and any(t.id == p.id for t in tiers) else p.id


def find_project(q, required=True):
    """A project known locally, by id or by name (project_tiers' first);
    with required=False, None when none is (an ambiguous name still exits)."""
    tiers = project_tiers(q)
    if tiers:
        return tiers[0]
    if not required:
        return None
    die("no project '%s' is known on this machine" % q, EXIT_UNKNOWN)


def org_scope():
    """The projects an org-wide name (`@short`, `@alias#short`) is looked up
    in: every project known here, the followed ones included, but one the
    org's directory retires."""
    return [p for p in known_projects() if not org_retired(p.id)]


def project_label(pid):
    """A project id as a reader names it: the project's name when it is known here."""
    return next((p.name for p in known_projects() if p.id == pid), pid)


def caller_project(caller=None):
    """The project a call speaks in by default: the caller seat's; else, from
    inside a session, the session's own (session_project: its override, else
    its launch directory's — never where its shell has moved since); else,
    for the operator, the working directory's (None: no project)."""
    if caller:
        return seat_project(caller)
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if UUID_RE.match(sid):
        return session_project(sid, launch_cwd(sid, fallback=os.getcwd()))
    return resolve_project(os.getcwd())


# ------------------------------------------- a session's project
#
# A session's project is resolved from its launch directory, never the
# directory its shell is in now: the hook payload's cwd, the engine record's
# and every transcript row's follow the shell, and a session `cd`ing between
# two repositories would split its exports across their projects. The launch
# directory is the one the engine keys the session's transcript by and
# `claude --resume` needs, read as the engine reads it for its own session
# list: the transcript's latest `relocated` row (the engine's `/cd`, or
# EnterWorktree, moved the session and its transcript), else the first row
# that carries a cwd. The engine appends the `relocated` row again with the
# session's other metadata as the file grows, so it stays near the end.
# Ahead of the directory stands the session's join override (`sminos join`).
# Design: docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md §1c, §7.

LAUNCH_REACH = 1 << 20   # the engine keeps a session's relocated row near the end; read wider than its 64 KiB
FIRST_ROWS = 1000        # the rows read for the first cwd (the engine writes it in its first few)
_LAUNCH = {}             # session → {"transcript", "size", "launch"}, as cached under launch/


def launch_cache_path(session):
    return os.path.join(root(), "launch", session + ".json")


def _relocated_in(f, start, end):
    """(the latest relocatedCwd among the complete lines in [start, end), or
    "", the offset just past the last complete line read). A `start` inside a
    line skips to the next one."""
    f.seek(start)
    data = f.read(end - start)
    last = data.rfind(b"\n")
    if last < 0:
        return "", start
    first = 0
    if start > 0:
        f.seek(start - 1)
        if f.read(1) != b"\n":
            first = data.find(b"\n") + 1
    for line in reversed(data[first:last].split(b"\n")):
        if b'"relocated"' not in line:
            continue
        r = _record(line) or {}
        if r.get("type") == "relocated" and isinstance(r.get("relocatedCwd"), str) and r["relocatedCwd"]:
            return r["relocatedCwd"], start + last + 1
    return "", start + last + 1


def _first_cwd(f):
    """The top-level cwd of a transcript's first whole row that carries one,
    or "" before one is written. Each row is read to its end, however long
    (a first prompt can be a long paste): a row cut short at a read boundary
    would not parse, and the caller's current directory would stand in for
    a launch directory the transcript does hold. Rows ahead of it (the
    engine's mode and snapshot rows) are a few; FIRST_ROWS bounds the look."""
    f.seek(0)
    for _ in range(FIRST_ROWS):
        line = f.readline()
        if not line.endswith(b"\n"):
            return ""   # none yet, or the row being written
        if b'"cwd"' in line:
            r = _record(line) or {}
            if isinstance(r.get("cwd"), str) and r["cwd"]:
                return r["cwd"]
    return ""


def launch_cwd(session, transcript="", fallback="", fresh=False):
    """The directory a session was launched in (or the engine last moved it
    to), from its transcript (`transcript`, else found by its id; `fresh`,
    looked for again when the index has none, transcript_path's `fresh`: for
    a write that rests on it); `fallback`
    when the transcript does not exist yet or names none — before its first
    turn, when no tool has moved its shell, so the caller's current
    directory is the launch directory then. Cached under launch/<session>.json
    with the transcript's size read, so a later call reads only what the
    engine appended since; a transcript at another path (the engine moved
    it) or shorter than read is read again."""
    path = transcript or transcript_path(session) or (transcript_path(session, fresh=True) if fresh else "")
    try:
        st = os.stat(path) if path else None
    except OSError:
        st = None
    if st is None and not transcript and path:
        path = transcript_path(session, fresh=True)   # moved since it was found: look again
        try:
            st = os.stat(path) if path else None
        except OSError:
            st = None
    if st is None:
        return fallback
    hit = _LAUNCH.get(session)
    if hit is None:
        try:
            with open(launch_cache_path(session)) as f:
                hit = json.load(f)
        except (OSError, ValueError):
            hit = None
        if not (isinstance(hit, dict) and isinstance(hit.get("transcript"), str)
                and isinstance(hit.get("size"), int) and isinstance(hit.get("launch"), str) and hit["launch"]):
            hit = None
    if hit and hit["transcript"] == path and hit["size"] == st.st_size:
        _LAUNCH[session] = hit
        return hit["launch"]
    try:
        with open(path, "rb") as f:
            if hit and hit["transcript"] == path and hit["size"] < st.st_size:
                moved, size = _relocated_in(f, max(hit["size"], st.st_size - LAUNCH_REACH), st.st_size)
                launch = moved or hit["launch"]
            else:
                moved, size = _relocated_in(f, max(0, st.st_size - LAUNCH_REACH), st.st_size)
                launch = moved or _first_cwd(f)
    except OSError:
        return fallback
    if not launch:
        return fallback
    entry = {"transcript": path, "size": size, "launch": launch}
    _LAUNCH[session] = entry
    if entry != hit:
        try:
            os.makedirs(os.path.dirname(launch_cache_path(session)), mode=0o700, exist_ok=True)
            write_json(launch_cache_path(session), entry)
        except OSError:
            pass   # read again next time
    return launch


def override_path(session):
    return os.path.join(root(), "sessions", session + ".json")


def override_of(session):
    """The project id a session's join override names, or "" for none. Read
    afresh each time (a missing file is one failed open): `join` writes it
    while the daemon's tick reads, and a tick deciding on a stale read would
    move the session back and forth."""
    try:
        with open(override_path(session)) as f:
            d = json.load(f)
        pid = str(d.get("project") or "") if isinstance(d, dict) else ""
    except (OSError, ValueError):
        pid = ""
    return pid if valid_name(pid) else ""


def write_override(session, pid):
    os.makedirs(os.path.dirname(override_path(session)), mode=0o700, exist_ok=True)
    write_json(override_path(session), {"project": pid, "at": now(ms=True)})


def remove_override(session):
    try:
        os.unlink(override_path(session))
    except FileNotFoundError:
        pass


def known_project(pid):
    """A project registered here (its project.json), by id, or None."""
    d = registration(pid)
    if not valid_name(pid) or str(d.get("project") or "") != pid:
        return None
    return make_project(pid, str(d.get("name") or pid), str(d.get("remote") or ""), str(d.get("root") or ""),
                        d["hub"] if isinstance(d.get("hub"), dict) else None)


def join_refusal(project):
    """Why a session cannot be in `project` by its own declaration, or "":
    on an enrolled machine only an active hub project of its org will do — a
    local project is kept here as history and a retired one is closed, and a
    session in either would leave the desk and every other machine's reach;
    on a machine not enrolled any project known here."""
    e = enrollment()
    if e is None:
        return ""
    if project.id.startswith("local-"):
        return ("%s is a local project, kept on a machine enrolled at the desk hub only as history: "
                "a session there would leave the desk" % project.name)
    if (project.hub or {}).get("org") != e["org"]:
        return "%s is not a project of org %s: a session there would sync nowhere" % (project.name, e["org"])
    if org_retired(project.id):
        return "%s is retired in the org's directory" % project.name
    return ""


def session_project(session, launch_cwd, fresh=False):
    """A session's project (§1): its join override, when the file names a
    project known here that it may be in (join_refusal; an ineligible one is
    read as absent, so the session moves back); else its launch directory's
    (resolve_project; `fresh`: as it is now). None for a session in no
    project."""
    pid = override_of(session) if session else ""
    if pid:
        target = known_project(pid)
        if target is not None and not join_refusal(target):
            return target
    return resolve_project(launch_cwd, fresh) if launch_cwd else None


def record_project(rec, fresh=False):
    """The project of the session an engine record names, from its launch
    directory (the record's cwd only until its transcript names one). Kept
    for the cache generation, as seat_project is, `fresh` reading it anew."""
    sid, cwd = str(rec.get("sessionId") or ""), str(rec.get("cwd") or "")
    if not fresh and (sid, cwd) in _RECORD_PROJECTS:
        return _RECORD_PROJECTS[(sid, cwd)]
    project = _RECORD_PROJECTS[(sid, cwd)] = session_project(sid, launch_cwd(sid, fallback=cwd, fresh=fresh), fresh)
    return project


# Writers: one appender each. `<machine>/<session-uuid>` for a session,
# `<machine>/human` for the operator, `legacy/<host-seat-id>` for an imported
# family chat. The file name replaces `/` with `.`.


def writer_id(session_uuid=None):
    return "%s/%s" % (host_name(), session_uuid or "human")


def writer_session(writer):
    last = writer.rsplit("/", 1)[-1]
    return last if UUID_RE.match(last) else ""


def owner_event(e):
    """Whether a log event is the owner's words: a `human` event written by
    the owner's own writer — `<machine>/human` (sminos run with no session)
    or the hub's `hub/<member>` (a send from the desk, which the hub stores
    only as a `human`). A session's `say`, and anything else, is a peer's:
    it reaches a session as a peer message, never as the human's words."""
    writer = str(e.get("writer") or "")
    return e.get("kind") == "human" and (writer.startswith("hub/") or writer.rsplit("/", 1)[-1] == "human")


def writer_short(writer):
    session = writer_session(writer)
    return session[:8] if session else writer


def event_ref(e):
    return "%s:%d" % (writer_short(e["writer"]), e["seq"])


def writer_path(project, writer):
    return store_path(project, "log", writer)


def store_path(project, store, writer):
    """A writer's file in one of the project's stores: `log` (the log, which
    git and the hub carry) or HOST_STORE (a cut-over machine's to-human
    events, host_store_holds)."""
    return project_path(project, store, writer.replace("/", ".") + ".jsonl")


@contextmanager
def flocked(path, exclusive=True, lock_until=None):
    """flock held for the block; with lock_until, LockBusy if it cannot be had by then."""
    with open(path, "a") as lock:
        flock_until(lock, lock_until, exclusive)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def parse_event(line):
    """One well-formed event, or None: a malformed line is skipped on read and
    never rewritten."""
    try:
        e = json.loads(line)
    except ValueError:
        return None
    if not (isinstance(e, dict) and isinstance(e.get("writer"), str) and isinstance(e.get("ts"), str)
            and isinstance(e.get("kind"), str) and type(e.get("seq")) is int):
        return None
    return e


def _last_seq(f):
    """The seq of the last well-formed line of an open writer file; 0 if none.
    Reads backwards from the end: a long-lived writer's file is never read whole."""
    end = f.seek(0, os.SEEK_END)
    size = 1 << 16
    while True:
        start = max(0, end - size)
        f.seek(start)
        lines = f.read(end - start).split(b"\n")
        if start:
            lines = lines[1:]  # the first may be the tail of an earlier line
        for line in reversed(lines):
            e = parse_event(line.decode("utf-8", "replace")) if line.strip() else None
            if e:
                return e["seq"]
        if not start:
            return 0
        size *= 4


UPLINK_STATE = "uplink.json"  # a hub project's uplink state, in its home (sminos_hublog)


def spent_seqs(project, writer):
    """The positions of `writer` the uplink spent — an event from the hub was
    refused there (sminos_hublog): a tombstone, never allocated."""
    try:
        with open(os.path.join(project.home, UPLINK_STATE)) as f:
            ss = json.load(f)["spent"][writer]
    except (OSError, ValueError, KeyError, TypeError):
        return set()
    return {s for s in ss if type(s) is int} if isinstance(ss, list) else set()


@contextmanager
def writer_locks(path, held=False):
    """A writer file's locks as _append takes them: its directory's
    `.sync.lock` shared, then the file's own lock. `held`: the caller holds
    them already (append_host, which decides a host event's route under the
    log's)."""
    if held:
        yield
        return
    with flocked(os.path.join(os.path.dirname(path), ".sync.lock"), exclusive=False), flocked(path + ".lock"):
        yield


# An own writer of no session waits for its upstream's head (#147). A machine
# that enrols, is cut over or is renamed may hold none of what its upstream
# holds already under the name it now writes as (a VM recreated under its old
# name, an enrolment with --replace, the endpoint's welcome). Its session
# writers are new UUIDs and never collide; its operator writer, `<name>/human`,
# would take seqs from 1 that the upstream holds: never uploaded (the
# uplink's `sent` starts at the upstream's head) and a fork of the log. So
# from that moment — daemon/heads.json names the enrolment, written by `hub
# enroll` and by a welcome that cuts over or renames — an append to it in a
# project of the upstream waits in projects/<id>/queued/ until the uplink has
# seen the upstream's head for the writer and the log has reached it, an
# import or positions spent (sminos_hublog.HubLog.release_heads); the
# project's heads.json then names the writer known for the enrolment, and what
# waited is appended above that head, in order and with the ts it was said
# at, and goes up with the next upload. A machine enrolled before this rule
# has no mark, and nothing of it waits.
HEADS_FILE = "heads.json"
HEADS_KEPT = 8   # enrolments daemon/heads.json keeps marked: one replacing another leaves the other marked
QUEUED = "queued"


def enrolment_stamp():
    """(name, enrolled) of this machine's enrolment now: identity.json's on a
    cut-over machine, else hub.json's; None when it is not enrolled."""
    ident = sibling_module("sminos_rl10").cutover()
    if ident is not None:
        return ident["name"], ident.get("enrolled")
    try:
        with open(os.path.join(root(), "daemon", "hub.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return (d["machine"], d.get("enrolled")) if isinstance(d, dict) and isinstance(d.get("machine"), str) else None


def _marks():
    """[(name, enrolled)] daemon/heads.json marks, oldest first."""
    try:
        with open(os.path.join(root(), "daemon", HEADS_FILE)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    raw = d.get("marks") if isinstance(d, dict) else None
    return [(m.get("name"), m.get("enrolled")) for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []


def mark_enrolled(name, enrolled):
    """A new enrolment under `name` (enrol, a cutover, a rename): from now on
    the operator writer of each upstream project waits for its head. Added
    to the enrolments marked, so the one it replaces stays marked until it
    is replaced in fact."""
    os.makedirs(os.path.join(root(), "daemon"), mode=0o700, exist_ok=True)
    marks = [m for m in _marks() if m != (name, enrolled)] + [(name, enrolled)]
    write_json(os.path.join(root(), "daemon", HEADS_FILE),
               {"marks": [{"name": n, "enrolled": e} for n, e in marks[-HEADS_KEPT:]]})


def _stamped(path, now):
    """The heads file at `path` when it names the enrolment `now`, else None."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and (d.get("name"), d.get("enrolled")) == now else None


def waits_for_head(project, writer):
    """Whether an append to `writer` in `project` waits for the upstream's
    head (the rule above): this machine's operator writer, in a project of
    its upstream, under a marked enrolment, not yet known for it."""
    if writer != writer_id():
        return False
    e = enrollment()
    if e is None or not (isinstance(project.hub, dict) and project.hub.get("org") == e["org"]):
        return False
    now = enrolment_stamp()
    if now is None or now not in _marks():
        return False
    known = _stamped(os.path.join(project.home, HEADS_FILE), now)
    return not (known is not None and writer in (known.get("known") or []))


def queued_path(project, writer):
    return os.path.join(project.home, QUEUED, writer.replace("/", ".") + ".jsonl")


def queued_events(path):
    """A queued file's events, in order, each without a seq; [] for none."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if isinstance(e, dict) and isinstance(e.get("writer"), str) and isinstance(e.get("kind"), str):
            out.append(e)
    return out


def queued_read(project, writer):
    """What waits for the writer's head, in order."""
    return [e for e in queued_events(queued_path(project, writer)) if e["writer"] == writer]


def queued_operators(project):
    """{writer: path} of the project's queues of this machine's operator
    writer, under its name now or a former one (a welcome that renamed the
    machine while an append waited)."""
    me, former = machine_identity()
    names = {me, *former}
    out = {}
    for path in glob.glob(os.path.join(glob.escape(project.home), QUEUED, "*.jsonl")):
        got = queued_events(path)
        if got and got[0]["writer"].endswith("/human") and got[0]["writer"].rpartition("/")[0] in names:
            out[got[0]["writer"]] = path
    return out


def queued_counts():
    """[(project name, events)] of every project with appends that wait for a
    head, in name order."""
    out = []
    for p in sorted(known_projects(all_seats=[]), key=lambda p: (p.name, p.id)):
        n = sum(len(queued_events(path)) for path in glob.glob(os.path.join(glob.escape(p.home), QUEUED, "*.jsonl")))
        if n:
            out.append((p.name, n))
    return out


def said_order(queues):
    """The events of queued_operators' `queues`, in the order they were said.
    Within one queue its file order is that order: appends to it are
    serialized by its writer's locks, whatever the clock says. Across queues
    the ts is the only signal, and it carries milliseconds alone, so two
    appends in one millisecond tie; on a tie a former name's event goes
    before a later name's (oldest name first, the name now last), since the
    rename that made the later name came between them. So the queues are
    merged, not sorted: each keeps its own order, and no tie is left to the
    order the queues were found in (each name has one queue, one rank)."""
    me, former = machine_identity()
    rank = {n: i for i, n in enumerate(former)}
    rank[me] = len(rank)
    runs = [[(str(e.get("ts") or ""), rank[w.rpartition("/")[0]], e) for e in queued_events(p) if e["writer"] == w]
            for w, p in queues.items()]
    return [e for _, _, e in heapq.merge(*runs, key=lambda x: x[:2])]


def release_queued(project, writer):
    """The upstream's head for `writer` is known and the log reached it: the
    writer known for this enrolment, and what waited for it appended above
    that head, in order and with the ts it was said at. Under the writer
    file's locks, which an append that would queue takes too, so nothing
    queues after the release. What the log holds already (a release cut
    short after its append) is not appended again. The events appended."""
    path = writer_path(project, writer)
    with writer_locks(path):
        now = enrolment_stamp()
        if now is None:
            return []
        known = _stamped(os.path.join(project.home, HEADS_FILE), now) or {"name": now[0], "enrolled": now[1]}
        if writer not in (known.get("known") or []):
            known["known"] = sorted(set(known.get("known") or []) | {writer})
            write_json(project_path(project, HEADS_FILE), known)
        # What waited under a former name too, the operator's now under this
        # name (a former name's writer is no upload's). Each queue is drained
        # under its own writer's locks, which an appender still running as a
        # former name takes to queue there.
        with ExitStack() as stack:
            queues = queued_operators(project)
            for w in sorted(queues):
                if w != writer:
                    stack.enter_context(writer_locks(writer_path(project, w)))
            waiting = [{k: v for k, v in e.items() if k not in ("writer", "seq")} for e in said_order(queues)]
            if waiting:
                # A release cut short after its append, under this name or a
                # former one, left its queue: what a log holds is not appended again.
                since = min(str(x.get("ts") or "") for x in waiting)
                held = {json.dumps({k: v for k, v in e.items() if k not in ("writer", "seq")}, sort_keys=True)
                        for w in {writer, *queues} for e in _log_file_events(writer_path(project, w))
                        if e["ts"] >= since}
                waiting = [e for e in waiting if json.dumps(e, sort_keys=True) not in held]
            # Appended whatever the enrolment says meanwhile (a `hub enroll`
            # publishing another under this name): its head was found reached.
            out = _append(project, writer, waiting, held=True, released=True) if waiting else []
            for p in queues.values():
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
    return out


def _queue(project, writer, events):
    """An append that waits for its writer's head (waits_for_head), kept
    under the writer file's locks: each event as it would be written, its
    seq None."""
    out = [{"ts": now(ms=True), "writer": writer, "seq": None, **e} for e in events]
    os.makedirs(os.path.join(project.home, QUEUED), mode=0o700, exist_ok=True)
    fd = os.open(queued_path(project, writer), os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "r+b") as f:
        end = f.seek(0, os.SEEK_END)
        if end:
            # An interrupted append can leave a fragment without its newline,
            # as in the log: end it, so this event is a line of its own.
            f.seek(end - 1)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write("".join(json.dumps({k: v for k, v in e.items() if k != "seq"}, ensure_ascii=False) + "\n"
                        for e in out).encode("utf-8"))
    return out


def waits_line(project, writer):
    """What a verb says of an append that waits for its writer's head."""
    nudge_daemon()
    return ("it waits in %s for the upstream's head of %s (this machine's enrolment is new): it is recorded, and "
            "delivered, once the uplink has seen it" % (project.name, writer))


def _append(project, writer, events, skip_src=False, guard=None, store="log", held=False, released=False):
    """Append events to the writer's file under `.sync.lock` shared (git never
    rewrites log/ while an appender writes) and the file's own lock (seq is the
    last line's plus one, past any position the uplink spent, which it spends
    under the same lock). With `guard`, the file's events are read under the
    lock and nothing is appended unless guard(events) holds — a check and its
    append no other appender can come between. `store`: the writer's file in
    another of the project's stores (HOST_STORE), by the same rule in its own
    directory, its seqs its own; `held`, its locks are the caller's
    (writer_locks). An own writer's `human` events in the log get their
    append receipts under the same lock, first (_write_receipts). Returns
    the events as written."""
    if any(e["kind"] in LIFECYCLE for e in events):
        _VIEWS.pop(project.id, None)
    path = store_path(project, store, writer)
    with writer_locks(path, held):
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "r+b") as f:
            if guard is not None:
                f.seek(0)
                if not guard([x for x in map(parse_event, f.read().decode("utf-8", "replace").split("\n")) if x]):
                    return []
            if skip_src:
                f.seek(0)
                # (kind, src): a question and its answer share the call id.
                present = {(x["kind"], x["src"]) for x in map(parse_event, f.read().decode("utf-8", "replace").split("\n"))
                           if x and x.get("src") is not None}
                kept = []
                for e in events:
                    key = (e["kind"], e.get("src"))
                    if key[1] is None or key not in present:
                        if key[1] is not None:
                            present.add(key)
                        kept.append(e)
                events = kept
            if not events:
                return []
            if store == "log" and not released and waits_for_head(project, writer):
                return _queue(project, writer, events)
            seq = _last_seq(f)
            spent = spent_seqs(project, writer) if store == "log" else set()
            out = []
            for fields in events:
                seq += 1
                while seq in spent:
                    seq += 1
                rest = {k: v for k, v in fields.items() if k != "kind"}
                out.append({"ts": now(ms=True), "writer": writer, "seq": seq, "kind": fields["kind"], **rest})
            if store == "log":
                _write_receipts(project, writer, out)   # the log's own writers' words alone (O12 M6)
            end = f.seek(0, os.SEEK_END)
            if end:
                # An interrupted append can leave a fragment without its
                # newline; end it so this event is a line of its own.
                f.seek(end - 1)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in out).encode())
    return out


def log_append(project, writer, kind, **fields):
    return _append(project, writer, [{"kind": kind, **fields}])[0]


# Append receipts (O12 M6): the provenance of this machine's operator words.
# The writer name is not provenance — a git mirror's merge can bring a
# `<thisname>/human` line no one here wrote — so each `human` event _append
# stores under this machine's own writer gets a machine-private receipt,
# `projects/<id>/receipts/<writer>.jsonl`, one `{seq, hash}` line, written in
# the same append under the writer file's lock, before the event itself: an
# event appended here always has one. The directory is outside log/, so git
# never mirrors it and the uplink never uploads it; a receipt stays under the
# writer name the append used, so a former name keeps its own. On a cut-over
# machine the words gate asks the endpoint about an own-writer event only
# when its receipt matches (receipted); any other goes as an unverified peer.

RECEIPTS = "receipts"


def event_hash(e):
    """SHA-256 (hex) of an event's canonical body (RFC 8785) as stored, the
    endpoint's verdict (`verified`) left out; None for one with no canonical
    form (a lone surrogate), which no receipt can then name."""
    codes = sibling_module("sminos_codes")
    try:
        text = codes.canonical({k: v for k, v in e.items() if k != "verified"})
    except codes.NotCanonical:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def receipt_path(project, writer):
    return os.path.join(project.home, RECEIPTS, writer.replace("/", ".") + ".jsonl")


def _write_receipts(project, writer, events):
    """The receipts of the `human` events an append stores under this
    machine's own writer (its name now); the caller holds the writer file's
    lock. One whose body has no canonical form gets none."""
    if writer.rpartition("/")[0] != host_name():
        return
    lines = [{"seq": e["seq"], "hash": h} for e in events if e["kind"] == "human" and (h := event_hash(e))]
    if not lines:
        return
    path = project_path(project, RECEIPTS, writer.replace("/", ".") + ".jsonl")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write("".join(json.dumps(r) + "\n" for r in lines))


def receipt_of(project, writer, seq):
    """The hash the append receipt holds for the writer's seq, or None. A
    seq written twice (an append whose event could not be written after its
    receipt was) is the last line's."""
    try:
        with open(receipt_path(project, writer)) as f:
            lines = f.read().split("\n")
    except OSError:
        return None
    for line in reversed(lines):
        try:
            r = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if isinstance(r, dict) and type(r.get("seq")) is int and r["seq"] == seq and isinstance(r.get("hash"), str):
            return r["hash"]
    return None


def receipted(project, e):
    """Whether the stored event is the one this machine appended at its
    position: its append receipt names its hash."""
    h = receipt_of(project, e["writer"], e["seq"])
    return h is not None and h == event_hash(e)


def own_operator_event(e):
    """Whether an event claims this machine's operator writer — a `human`
    event of `<name>/human`, `name` this machine's name now or a former one
    — which only its append receipt bears out (receipted)."""
    head, _, tail = str(e.get("writer") or "").rpartition("/")
    name, former = machine_identity()
    return e.get("kind") == "human" and tail == "human" and (head == name or head in former)


def log_append_batch(project, writer, events, skip_src=True):
    """Several events of one writer under one taking of the locks; with
    skip_src, an event whose (kind, src) the file already holds is dropped
    inside them, so a retried export appends each source once. `src` is a
    correlation id: a `question` and its `answered` share one."""
    return _append(project, writer, events, skip_src)


def addressed_to(e, session):
    """Whether the event is owed to the session. A `copy` — the sender's own
    log's record of a message another project's log delivers (§6 of the org
    directory design) — is owed to no one: its `to` names who the other
    event reached."""
    to = e.get("to")
    return (isinstance(to, list) and "copy" not in e
            and any(isinstance(r, dict) and r.get("session") == session for r in to))


_LOG_FILES = {}  # writer file → ((st_ino, st_size, st_mtime_ns), its well-formed events)


def _log_file_events(path):
    """A writer file's well-formed events, parsed again only once its inode,
    size or mtime moved: the daemon and the uplink read every project's
    whole log many times a minute. [] for a file that cannot be read."""
    try:
        st = os.stat(path)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        held = _LOG_FILES.get(path)
        if held is None or held[0] != key:
            with open(path, encoding="utf-8", errors="replace") as f:
                held = _LOG_FILES[path] = (key, [e for e in map(parse_event, f) if e is not None])
    except OSError:
        _LOG_FILES.pop(path, None)
        return []
    return held[1]


def log_read(project, since=None, kinds=(), to_session=None):
    """The project's events: each writer's stream in seq order (authoritative
    within a writer), merged by taking the next line from whichever stream's
    head has the earlier (ts, writer). Only the top-level *.jsonl are read."""
    return _store_read(project, "log", since, kinds, to_session)


def host_read(project, since=None):
    """The project's host store (HOST_STORE), read as log_read reads the log:
    on a cut-over machine, what its sessions sent their person since the
    cutover. Empty where the machine keeps them in the log."""
    return _store_read(project, HOST_STORE, since)


def _store_read(project, store, since=None, kinds=(), to_session=None):
    streams = {}
    for path in sorted(glob.glob(os.path.join(project.home, store, "*.jsonl"))):
        for e in _log_file_events(path):
            if ((since and e["seq"] <= int(since.get(e["writer"], 0)))
                    or (kinds and e["kind"] not in kinds) or (to_session and not addressed_to(e, to_session))):
                continue
            streams.setdefault(e["writer"], []).append(dict(e))
    for stream in streams.values():
        stream.sort(key=lambda e: e["seq"])
    return list(heapq.merge(*streams.values(), key=lambda e: (e["ts"], e["writer"])))


def reader_key(session_uuid):
    key = session_uuid or "human"
    if not valid_name(key):
        die("not a session id: %s" % key)
    return key


def cursor_load(project, session_uuid):
    """What a reader has read: {writer: seq}."""
    try:
        with open(os.path.join(project.home, "cursors", reader_key(session_uuid) + ".json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(w): int(s) for w, s in d.items() if type(s) is int} if isinstance(d, dict) else {}


def cursor_save(project, session_uuid, cursor):
    """Advance a reader's cursor to `cursor`, merged per writer with what is
    persisted under the cursor's lock: overlapping reads never move it back."""
    path = project_path(project, "cursors", reader_key(session_uuid) + ".json")
    with flocked(path[:-len(".json")] + ".lock"):
        merged = cursor_load(project, session_uuid)
        for writer, seq in cursor.items():
            merged[writer] = max(merged.get(writer, 0), int(seq))
        write_json(path, merged)


# Delivery records: per recipient session, per writer, the seq up to which
# every event owed to it is settled, and the one pending event that failed
# with its attempt count — or that was pushed and could not be settled yet
# (`pushed`: [seq, outcome], deliver_next). A deliverer never settles past an
# unsettled event of the same writer, so a later success cannot bury an
# earlier failure. On a cut-over machine an owed event whose signer was
# revoked is marked (`revoked`: its seqs above the prefix, delivered_revoke):
# never delivered, and passed by the prefix only in order.


def delivered_load(project, session_uuid):
    try:
        with open(os.path.join(project.home, "delivered", reader_key(session_uuid) + ".json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for w, v in (d.items() if isinstance(d, dict) else ()):
        if isinstance(v, dict):
            pending = v.get("pending")
            settled = int(v.get("settled") or 0)
            out[str(w)] = {"settled": settled,
                           "pending": pending if type(pending) is int else None,
                           "attempts": int(v.get("attempts") or 0)}
            pushed = v.get("pushed")
            if isinstance(pushed, list) and len(pushed) == 2 and type(pushed[0]) is int and pushed[0] == pending \
                    and pushed[1] in PUSHED:
                out[str(w)]["pushed"] = pushed
            marked = v.get("revoked")
            marked = sorted({s for s in marked if type(s) is int and s > settled}) if isinstance(marked, list) else []
            if marked:
                out[str(w)]["revoked"] = marked
    return out


def _delivery(record, writer):
    return record.get(writer) or {"settled": 0, "pending": None, "attempts": 0}


def _entry(settled, pending=None, attempts=0, revoked=(), pushed=None):
    """A writer's delivery entry as written: of its revoked seqs, those
    directly above the settled prefix are passed by it (none is owed, so the
    prefix moves over them in order), the rest kept; `revoked` only when it
    holds one, so a record with none is written as before."""
    marked = sorted({s for s in revoked if s > settled})
    while marked and marked[0] == settled + 1 and marked[0] != pending:
        settled = marked.pop(0)
    w = {"settled": settled, "pending": pending, "attempts": attempts}
    if pushed is not None:
        w["pushed"] = pushed
    if marked:
        w["revoked"] = marked
    return w


def _next_check(record, writer, seq):
    w = _delivery(record, writer)
    if seq <= w["settled"] or (w["pending"] is not None and seq != w["pending"]) or seq in w.get("revoked", ()):
        raise ValueError("delivery of %s:%d out of order (settled %d, pending %s%s)" % (
            writer, seq, w["settled"], w["pending"], ", revoked" if seq in w.get("revoked", ()) else ""))
    return w


def _delivered_write(project, session_uuid, record):
    write_json(project_path(project, "delivered", reader_key(session_uuid) + ".json"), record)


def delivered_settle(project, session_uuid, writer, seq):
    """Settle the writer's next owed event — every event between the settled
    prefix and seq is not owed to this session, so the prefix moves to seq.
    The caller holds delivered/<session>.lock."""
    record = delivered_load(project, session_uuid)
    w = _next_check(record, writer, seq)
    record[writer] = _entry(seq, revoked=w.get("revoked", ()))
    _delivered_write(project, session_uuid, record)


def delivered_fail(project, session_uuid, writer, seq):
    """Note a failed attempt at the writer's next owed event; returns the count."""
    record = delivered_load(project, session_uuid)
    w = _next_check(record, writer, seq)
    attempts = w["attempts"] + 1 if w["pending"] == seq else 1
    record[writer] = _entry(w["settled"], seq, attempts, w.get("revoked", ()))
    _delivered_write(project, session_uuid, record)
    return attempts


def delivered_pushed(project, session_uuid, writer, seq, outcome):
    """Note that the writer's next owed event was pushed (`outcome`, one of
    PUSHED) and stays unsettled: the next pass settles it on that outcome
    without pushing it again. Kept best effort — a note that cannot be
    written leaves the push to be made again, at least once as before."""
    try:
        record = delivered_load(project, session_uuid)
        w = _next_check(record, writer, seq)
        record[writer] = _entry(w["settled"], seq, w["attempts"] if w["pending"] == seq else 0,
                                w.get("revoked", ()), [seq, outcome])
        _delivered_write(project, session_uuid, record)
    except OSError as err:
        daemon_log("delivery: the push of %s:%d to %s could not be noted (%s): a later pass pushes it again" % (
            writer, seq, session_uuid, err))


def delivered_revoke(project, session_uuid, writer, seq):
    """Mark the writer's owed event `seq` revoked (O12 M6): its signer's key,
    device or member was revoked, so it is never delivered — _owed leaves it
    out, _next_check refuses it — and its `refused-revoked` outcome is
    recorded for the uplink first (an outside-origin event's, as
    deliver_next records). It is not settled: a member's devices share its
    `hub/<member>` writer, and settling seq 2 would move the prefix past an
    owed seq 1 (P1-2), so the prefix passes a marked seq only in order — at
    once when it is the writer's next, else when the events below it settle.
    Revoking the pending event clears it and its attempts. Whether it was
    marked: one whose outcome cannot be kept stays owed, for a later pass to
    record and mark. The caller holds delivered/<session>.lock."""
    record = delivered_load(project, session_uuid)
    w = _delivery(record, writer)
    if seq <= w["settled"]:
        raise ValueError("revoking %s:%d, which is settled (settled %d)" % (writer, seq, w["settled"]))
    if seq in w.get("revoked", ()):
        return True
    e = {"writer": writer, "seq": seq}
    outcomes = sibling_module("sminos_outcomes")
    if sibling_module("sminos_policy").outside_origin(e) \
            and not outcomes.record(project, e, session_uuid, outcomes.REFUSED_REVOKED, None):
        return False
    revoked = list(w.get("revoked", ())) + [seq]
    if w["pending"] == seq:
        record[writer] = _entry(w["settled"], None, 0, revoked)
    else:
        record[writer] = _entry(w["settled"], w["pending"], w["attempts"], revoked, w.get("pushed"))
    _delivered_write(project, session_uuid, record)
    return True


def revoke_owed(project, member, revoked):
    """What a revocation stops at once: every event owed to the member whose
    stored signer the set names (sminos_rl10.event_revoked), asked or not,
    marked revoked (delivered_revoke), under its delivery lock. One whose
    push is noted was delivered before the revocation, and is left to its
    settlement. The events marked."""
    session = member.session
    if not session:
        return []
    rl10 = sibling_module("sminos_rl10")
    marked = []
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        record = delivered_load(project, session)
        for e in _owed(log_read(project, to_session=session), session, record):
            noted = _delivery(record, e["writer"]).get("pushed")
            if not rl10.event_revoked(e, revoked) or (noted and noted[0] == e["seq"]):
                continue
            if delivered_revoke(project, session, e["writer"], e["seq"]):
                marked.append(e)
    return marked


# --------------------------------------------------------------- the family
#
# A member is a session whose latest membership event (joined/retired, in its
# own file, by seq) is joined — plus, on this machine, every live harness
# session and every seat whose cwd resolves to the project, joined into the log
# on sight by reconcile(). Derived, never declared. There is no host and no
# tree: `by` is the spawner, recorded as provenance and nothing more.


class Member(NamedTuple):
    session: str
    short: str
    alias: str
    name_source: str      # seat | the engine's (user, derived, auto, hook, peer, collision)
    machine: str
    local: bool
    state: str            # one of STATES; for a remote member its last published word, or ""
    state_age: float | None
    charge: str
    charge_source: str    # set | name | derived | title | "" (charge_of)
    status: str
    by: str
    worktree: str
    seat: dict | None     # the seat record this session fills, when it is a seat on this machine
    former: tuple = ()    # the sessions it continues (lineage), newest first
    former_aliases: tuple = ()  # (alias, ts): aliases it or they held before its alias now, each at its latest event
    kind: str = ""      # interactive | bg | seat (a joined's session_kind); "" when nothing says
    cwd: str = ""         # where it works: its latest joined's cwd, else its seat's, else its record's
    repo: str = ""        # the owning repository's basename ("" outside one)
    branch: str = ""      # the branch checked out there ("" when detached or none)
    charge_age: float | None = None   # seconds since its in-charge line's event; None for a line with none
    active_age: float | None = None   # seconds since its engine record's updatedAt here, its last state remotely
    title: str = ""       # another machine's session: the title its machine published (here, the transcript's)
    owners: tuple = ()    # whose session it is (RL6): its record's here, else the latest joined along its lineage publishing them
    origin: dict | None = None   # how it started, beside `owners`
    record: dict | None = None   # its record on this machine (session_record), for a local member that has one


def project_kind(project):
    """hub | machine | local: a machine's own project (this machine's by its
    id, another's by the org's directory), a project that syncs through a desk
    hub, or one that does not."""
    e = enrollment()
    if (e and project.id == machine_project_id(e["org"], e["machine"])) \
            or (org_entry(project.id) or {}).get("kind") == "machine":
        return "machine"
    return "hub" if project.hub else "local"


DEFAULT_OWNERS = ("@machine",)
DEFAULT_ORIGIN = {"kind": "terminal"}


def member_json(m, project=None, private=True):
    """A member as list --json carries it: no task body, no credential.
    `owners` and `origin` for every member with a session (the machine's
    terminal default where nothing says otherwise); `ownersProof`,
    `principal`, `inference` and `controller` too for one of this machine,
    from its record (null when it has none), unless the view is the org's
    (`private` False: the listing's public fields alone)."""
    d = {"alias": m.alias, "session": m.session, "short": m.short, "name_source": m.name_source,
         "kind": m.kind or None, "machine": m.machine, "local": m.local, "state": m.state,
         "state_age": m.state_age, "active_age": m.active_age, "charge": m.charge,
         "charge_source": m.charge_source, "charge_age": m.charge_age, "by": m.by, "status": m.status,
         "cwd": m.cwd, "repo": m.repo, "branch": m.branch, "worktree": m.worktree,
         "seat": public_seat(m.seat) if m.seat else None, "former": list(m.former),
         "owners": list(m.owners or DEFAULT_OWNERS) if m.session else None,
         "origin": dict(m.origin or DEFAULT_ORIGIN) if m.session else None}
    if m.local and private:
        rec = m.record or {}
        d.update(ownersProof=rec.get("ownersProof"), principal=rec.get("principal"), inference=rec.get("inference"),
                 controller=rec.get("controller"))
    rec = session_running(m.session) if m.local and m.session else None
    d["engine"] = engine_facts(rec) if rec else None
    if project is not None:
        d = {"project": project.name, "project_id": project.id, "project_kind": project_kind(project), **d}
    return d


def member_label(m, rows):
    """A member's display name: its alias, with #short when another row of the
    project shares it."""
    shared = sum(1 for r in rows if r.alias == m.alias) > 1
    return "%s#%s" % (m.alias, m.short) if shared and m.short else m.alias


def internal_pids():
    """Pids `derive` marked as its own headless forks: never members (§5)."""
    try:
        return {n for n in os.listdir(os.path.join(root(), "internal")) if n.isdigit()}
    except OSError:
        return set()


DESK_MEMBER_ENV = "SMINOS_DESK_MEMBER"  # set by the daemon running a verb for a desk RPC: the member's id
DESK_PROOF_ENV = "SMINOS_DESK_PROOF"    # and for a remote spawn, its signed action (canonical JSON, O12 M7)
MEMBER_ID_RE = re.compile(r"[0-9a-f]{32}")


def desk_member():
    """The desk member a verb acts for, when the daemon runs it for an RPC
    (32 hex, else nothing); never inside a session."""
    m = os.environ.get(DESK_MEMBER_ENV, "")
    return m if not os.environ.get("CLAUDE_CODE_SESSION_ID") and MEMBER_ID_RE.fullmatch(m) else ""


def desk_proof():
    """A remote desk spawn's proof (O12 M7), as the daemon handed it to the
    verb: [the signed action], the new session's ownersProof; [] when the
    daemon handed none (a DX2 spawn), or one that does not parse as a JSON
    object, which daemon.log says. The endpoint authorized the spawn: a
    proof it cannot keep is the attestation's loss, never a refusal."""
    text = os.environ.get(DESK_PROOF_ENV)
    if text is None:
        return []
    try:
        proof = json.loads(text)
    except ValueError:
        proof = None
    if not isinstance(proof, dict):
        daemon_log("spawn: the desk spawn's proof does not parse as a JSON object: the session's ownersProof is []")
        return []
    return [proof]


def caller_alias():
    """Who a lifecycle event names as its actor (`by`): the calling session's
    seat alias (a provisional seat's too), else its harness name; for the
    operator, the desk member a daemon verb acts for, else ""."""
    if not os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return desk_member()
    caller = caller_seat()
    return caller["alias"] if caller else default_from("")


def repo_branch(cwd):
    """(the owning repository's basename, the branch checked out at `cwd`),
    each "" when there is none: what a row shows as repo@branch. Kept for
    the cache generation: every view reads it for every member."""
    if not cwd:
        return "", ""
    if cwd not in _REPO_BRANCH:
        _REPO_BRANCH[cwd] = os.path.basename(owning_repo(cwd)), sibling_module("sminos_policy").git_branch(cwd)
    return _REPO_BRANCH[cwd]


def joined_fields(alias, name_source, cwd, worktree="", role="", seat="", by="", session_kind="", session=""):
    """A joined event's fields. `session_kind` is the session's kind
    (interactive, bg, seat) — never `kind`, every event's own discriminator;
    `repo` and `branch` are read where it works as it joins, and are not
    published again when they change. With `session`, what its record
    publishes once it is final: its `origin`, and its `owners` unless they
    hold `@machine` (published_provenance)."""
    repo, branch = repo_branch(cwd)
    return {"alias": alias, "name_source": name_source, "machine": host_name(), "cwd": cwd,
            "worktree": worktree, "role": role, "seat": seat, "by": by, "session_kind": session_kind,
            "repo": repo, "branch": branch, **published_provenance(session)}


# ------------------------------------------------------------ the session record
# Each session sminos joins has a machine-held record (O12 M1, RL6), kept by
# sminos_records: who owns it, how it started, what inference it runs on.
# Every path that joins a session first makes sure it has one
# (ensure_record), so the `joined` it writes can carry the record's owners
# and origin; only a final record's are published, only on `joined`, and
# never the `@machine` token.


def records_module():
    return sibling_module("sminos_records")


def session_record(sid):
    """The session's record on this machine (RL6), or None."""
    return records_module().read(sid)


def set_session_controller(sid, lane, since=None):
    """The session's current controller lane (A or B) on its existing record,
    its provenance untouched; False when it has no record yet."""
    return records_module().set_controller(sid, lane, since)


def owners_of(event):
    """The owners a `joined` carries, a list of strings, or None."""
    owners = event.get("owners")
    if isinstance(owners, list) and owners and all(isinstance(o, str) and o for o in owners):
        return owners
    return None


def publishes(event):
    """Whether a `joined` carries its session's final provenance: its
    `origin` (every final record's), or its `owners`."""
    return event.get("kind") == "joined" and (isinstance(event.get("origin"), dict) or bool(owners_of(event)))


def published_provenance(sid):
    """What a `joined` of the session carries of its record, once the record
    is final: its `origin`, and its `owners` when they name members only.
    `@machine` never leaves the machine (RL6, the remote layer's Decision
    Log 17): owners that hold it are left off, and every reader takes a
    member that publishes none as the machine's, the same value. Nothing for
    a provisional record or none, so readers elsewhere fall back to the
    machine's default without being bound to it."""
    records = records_module()
    rec = records.read(sid) if sid else None
    if not records.is_final(rec):
        return {}
    owners = list(rec["owners"])
    return {**({"owners": owners} if records.MACHINE not in owners else {}), "origin": dict(rec["origin"])}


_LINEAGE_INDEX = [None, -1, None]   # the events last indexed, their count, (continuations, publications, memberships)


def publication(event):
    """What a `joined` publishes of its session's record, in
    published_provenance's shape, or None for a joined that publishes nothing."""
    if not publishes(event):
        return None
    owners = owners_of(event)
    origin = event.get("origin") if isinstance(event.get("origin"), dict) else None
    return {**({"owners": owners} if owners else {}), **({"origin": origin} if origin else {})}


def _lineage_index(events):
    """({session: the session it continues}, {session: its latest own joined
    that publishes}, {session: its latest own membership event's kind}) of
    a log as read, in one pass: each `continued` retirement in its writer's
    own file, the latest naming a session winning. Kept for the events last
    asked about (their identity and length), so a reconciliation indexes
    its log once, and a member whose publication is current costs no scan."""
    if _LINEAGE_INDEX[0] is events and _LINEAGE_INDEX[1] == len(events):
        return _LINEAGE_INDEX[2]
    conts, published, membership = {}, {}, {}
    for e in events:
        sid = e.get("session")
        if not isinstance(sid, str) or e["kind"] not in MEMBERSHIP or writer_session(e["writer"]) != sid:
            continue
        membership[sid] = e["kind"]
        if e["kind"] == "retired" and e.get("reason") == "continued" and UUID_RE.match(str(e.get("to") or "")):
            conts[e["to"]] = sid
        elif publishes(e):
            published[sid] = e
    _LINEAGE_INDEX[:] = [events, len(events), (conts, published, membership)]
    return conts, published, membership


def lineage_of(project, sid, peer=None, events=None):
    """The sessions `sid` continues, newest first, as this machine's log and
    engine tell: the `continued` retirements naming each (events, else the
    project's retirements read), and, for a background job none names yet,
    the session still exiting whose transcript hands it on (predecessor)."""
    conts = _lineage_index(events if events is not None else log_read(project, kinds=("retired",)))[0]
    head = conts.get(sid)
    if head is None and str((peer or {}).get("kind") or "") == "bg":
        head = predecessor(project, sid)[0]
    chain = []
    while head and head != sid and head not in chain and len(chain) < 32:
        chain.append(head)
        head = conts.get(head)
    return chain


def own_events_of(project, sid, events=None):
    """The session's own events: from `events` (a log as read) when given,
    else read from its writer files (_own_events)."""
    if events is None:
        return _own_events(project, sid)
    return [e for e in events if e.get("session") == sid and writer_session(e["writer"]) == sid]


def last_published(project, sid, events=None):
    """The latest `joined` in the session's own file that publishes, or None."""
    if events is not None:
        return _lineage_index(events)[1].get(sid)
    return next((e for e in reversed(_own_events(project, sid)) if publishes(e)), None)


def lineage_provenance(project, sid, peer=None, former=None, events=None):
    """A provenance from the sessions `sid` continues, or None. The first
    final record along them wins; else the latest `joined` among them, the
    nearest first, that publishes (its owners the machine's when it names
    none); else the first provisional record, the fallback, so a provisional
    session between it and a final ancestor never hides the ancestor. The
    session's own publications are never evidence: they say what its record
    already is."""
    records = records_module()
    chain = list(former) if former else (lineage_of(project, sid, peer, events) if project is not None else [])
    fallback = None
    for i, old in enumerate(chain):
        rec = records.read(old)
        if rec is not None:
            if records.is_final(rec):
                return records.inherited(rec, chain[:i + 1])
            fallback = fallback or records.inherited(rec, chain[:i + 1])
    if project is not None:
        for s in chain:
            j = last_published(project, s, events)
            if j is not None:
                return records.from_joined({"owners": owners_of(j) or [records.MACHINE], "origin": j.get("origin")},
                                           chain)
    return fallback


def ensure_record(project, sid, seat=None, peer=None, evidence=None, former=None, events=None):
    """The session's record: written if it has none, and replaced only by
    strictly stronger evidence (sminos_records.stronger: launch, then
    lineage, then the hook's, then the defaults; final over provisional).
    The candidate is its lineage (lineage_provenance; `former`, a hand-off's
    predecessor, when the caller knows it), else `evidence` (the hook's:
    the session's own environment), else the machine's defaults. A record a
    launch established, or a final lineage, has nothing stronger to look
    for but a claim (sminos_records.claim); a final hook record looks for a
    lineage only where one can appear, a background job or a hand-off. Then,
    whether or not it changed, a member whose `joined` does not carry what
    its record publishes is joined again (publish_owners). A record that
    cannot be written is a warning: membership never waits on it. Returns
    the record, or None."""
    records = records_module()
    rec = records.read(sid)
    settled = rec is not None and (records.basis(rec) == "launch" or records.strength(rec) == (2, True)
                                   or (records.strength(rec) == (1, True) and not former
                                       and str((peer or {}).get("kind") or "") != "bg"))
    if not settled:
        try:
            prov = lineage_provenance(project, sid, peer, former, events) \
                or evidence or records.default_provenance()
            if records.stronger(prov, rec):
                rec = records.establish(sid, prov, _RECORD_DEADLINE)[0]
        except (OSError, LockBusy, ValueError) as e:
            warn("the record of session %s could not be written: %s" % (sid[:8], e))
    if rec is not None and records.is_final(rec) and project is not None:
        publish_owners(project, sid, events)
    return rec


def publish_owners(project, sid, events=None):
    """A member whose latest publishing `joined` does not carry what its
    record publishes now (published_provenance: it became final after the
    member joined, its record was replaced by stronger evidence since, or an
    earlier publication's append failed) is joined again, carrying it: its
    alias as the log holds it, the rest as its last `joined` had them, `by`
    empty. Once per change of the record, which only moves up (default,
    hook, lineage, launch). With `events` (a reconciliation's log), a member
    whose publication is current is told from the log's index, no scan.
    Under the session file's lock the record is read again (lifecycle), so
    what is appended is the record as it is then, and nothing is appended
    when the latest publication already carries it. Returns the events
    appended."""
    pub = published_provenance(sid)
    if not pub:
        return []
    if events is not None:
        _, published, membership = _lineage_index(events)
        latest = published.get(sid)
        if membership.get(sid) != "joined" or (latest is not None and publication(latest) == pub):
            return []
    own = own_events_of(project, sid, events)
    last = next((e for e in reversed(own) if e["kind"] == "joined"), None)
    if last is None or latest_membership(own) != "joined":
        return []

    def missing(evs, now):
        latest = next((e for e in reversed(evs) if publishes(e)), None)
        return bool(now) and (latest is None or publication(latest) != now)

    if not missing(own, pub):
        return []

    def guard(evs):
        return latest_membership(evs) == "joined" and missing(evs, published_provenance(sid))

    alias, source = own_alias(own, sid)
    fields = joined_fields(alias or str(last.get("alias") or sid[:8]),
                           source or str(last.get("name_source") or "derived"), str(last.get("cwd") or ""),
                           str(last.get("worktree") or ""), str(last.get("role") or ""), str(last.get("seat") or ""),
                           "", str(last.get("session_kind") or ""), session=sid)
    return lifecycle(project, sid, "joined", guard=guard, required=False, **fields)


def latest_membership(events):
    """The kind of the last joined/retired among a session's own events, or None."""
    return next((e["kind"] for e in reversed(events) if e["kind"] in MEMBERSHIP), None)


class LogWriteFailed(Exception):
    """A required lifecycle event could not be appended. The verb's local
    operation already happened; main() exits 1 saying both."""


def _fresh_publication(event):
    """A joined's `owners` and `origin` set to what its session's record
    publishes now (published_provenance); always True, for a guard."""
    event.pop("owners", None)
    event.pop("origin", None)
    event.update(published_provenance(event["session"]))
    return True


def lifecycle(log_project, session, kind, guard=None, required=True, **fields):
    """Append one lifecycle event for a session on this machine to the
    session's own file: a session's lifecycle has one writer, so its order is
    its seq. A failure raises LogWriteFailed — the event is part of the verb —
    except for reconciliation's own appends (`required=False`), which a
    reading verb only warns about and the next one retries. A guard reads
    the session's events under this machine's former names first: a rename
    moves where its lifecycle goes on, not what it is. (`log_project` is
    the log written to: an event's own `project` field, a `moved`
    retirement's, is one of `fields`.)"""
    if log_project is None or not session:
        return []
    before = _former_events(log_project, session) if guard is not None else []
    if before:
        guard = (lambda inner: lambda evs: inner(before + evs))(guard)
    event = {"kind": kind, "session": session, **fields}
    if kind == "joined":
        # What a joined publishes of the session's record was read before the
        # file's lock; under it, it is read again, so a writer that paused
        # between never appends provenance older than a publication since.
        guard = (lambda inner: lambda evs: _fresh_publication(event) and (inner is None or inner(evs)))(guard)
    try:
        return _append(log_project, writer_id(session), [event], guard=guard)
    except OSError as e:
        msg = "recording %s of %s in %s's log failed: %s" % (kind, session[:8], log_project.name, e)
        if required:
            raise LogWriteFailed(msg)
        warn(msg)
        return []


def join_seat(seat, by=""):
    """joined for the session a seat holds, unless its latest membership
    already is: how fill --resume, resume, and send revive a retired seat."""
    if not seat or not seat["current"]:
        return []
    project = seat_project(seat)
    if project is not None:
        ensure_record(project, seat["current"], seat)
    return lifecycle(project, seat["current"], "joined",
                     guard=lambda evs: latest_membership(evs) != "joined",
                     **joined_fields(seat["alias"], "seat", seat_cwd(seat), seat["worktree"], seat["role"],
                                     seat["seat_id"], by, "seat", session=seat["current"]))


def seats_by_session(project, all_seats):
    """{session: seat}: the seat that binds a session in the project's
    projection. The legacy conversion can leave one session in seats of
    several projects, and there the project's own seat (its cwd resolves to
    the project) binds it, never another project's. A session the project
    holds no seat for is bound by the seat that holds it elsewhere: a seat
    whose cwd moved still stands for the session it holds, one seat one
    target (find_target)."""
    out, own = {}, set()
    for s in all_seats:
        sid = s["current"]
        if not sid:
            continue
        mine = (p := seat_project(s)) is not None and p.id == project.id
        if mine or sid not in own:
            out[sid] = s
            if mine:
                own.add(sid)
    return out


def _local_sessions(project, all_seats):
    """This machine's evidence of sessions in the project: {session: {"seat",
    "peer"}} for every seat whose cwd resolves to it and every running harness
    session whose project it is (record_project: its launch directory's, or
    the one it joined), internal forks aside."""
    local = {}
    for s in all_seats:
        if s["current"] and (p := seat_project(s)) and p.id == project.id:
            local.setdefault(s["current"], {})["seat"] = s
    internal = internal_pids()
    for rec in peer_records():
        sid, cwd = rec.get("sessionId"), rec.get("cwd")
        if not (isinstance(sid, str) and UUID_RE.match(sid) and isinstance(cwd, str) and cwd):
            continue
        if str(rec.get("pid")) in internal:
            continue
        p = record_project(rec)
        if p is not None and p.id == project.id and peer_running(rec):
            local.setdefault(sid, {})["peer"] = rec
    return local


def _reconcile(project, events, local, by_session):
    """Append joined for this machine's sessions the log does not hold as
    members: a live session whose latest membership is absent or retired (a
    live process is evidence of activation), and a seat with no membership
    event at all. A seat whose record is retired is never re-joined here — a
    session still answering after `retire` stopped it is not a revival; only
    fill, resume, and send revive. Each check is repeated under the session
    file's lock, so a concurrent retire cannot be undone.

    A seat-less session joins on sight only when the harness records it as
    `interactive` or `bg`: another tool's headless run is no member. And the
    absence of the process ends what its presence began: a seat-less member
    of this machine whose session no longer runs is retired, reason `ended`,
    and re-joins if it runs again — unless the harness handed it to a
    background job, which it continues (hand_off). A seat's lifecycle stays
    with retire, fill, and resume, but for the same hand-off: a seat whose
    session no longer runs and names a job it continues in moves to it. The
    job may have joined before the harness wrote that record, and a hand-off
    a held seat lock cut short is left to be tried again, so every
    reconciliation looks.

    A member of this machine whose project is now another — a .smns came or
    went under its launch directory, its join override was written or
    removed, a seat's directory resolves elsewhere — is retired here, reason
    `moved`, naming the project it moved to; that project's reconciliation
    joins it (§1a). One may join before the other retires: a dual membership
    of one tick. A member the engine relocated within the project is joined
    again where it runs now (refresh_joined). Which project a session is in
    is read from the cache generation's resolution (seat_project); a move or
    a join it decides is written only if the session's project, resolved
    afresh under the lock, still says so (here_now, retire_moved)."""
    latest, joined = {}, {}
    for e in events:
        if e["kind"] in MEMBERSHIP and e.get("session") and writer_session(e["writer"]) == e["session"]:
            latest[e["session"]] = e["kind"]
            if e["kind"] == "joined":
                joined[e["session"]] = e
    out = []
    for sid, e in joined.items():
        if latest[sid] != "joined" or sid in local or not is_self(str(e.get("machine") or ""), sid):
            continue
        seat = by_session.get(sid)
        if seat is not None:
            if seat["current"] == sid:
                out += retire_moved(project, sid, seat_project(seat), lambda seat=seat: seat_project(seat, fresh=True))
            continue
        rec = session_running(sid)
        if rec is not None:
            if str(rec.get("pid")) not in internal_pids():
                out += retire_moved(project, sid, record_project(rec), lambda rec=rec: record_project(rec, fresh=True))
            continue
        successor = continued_in(sid, fresh=True)   # before an `ended` that would bury a hand-off
        if successor:
            out += hand_off(project, sid, successor)
            continue

        def ended(evs, sid=sid):
            return (latest_membership(evs) == "joined" and not session_running(sid)
                    and not any(s["current"] == sid for s in seats()))

        out += lifecycle(project, sid, "retired", guard=ended, required=False, by="", reason="ended")
    # A verb a marked session's tools run speaks for that session alone; an
    # internal fork's, for none.
    own = (os.environ.get("CLAUDE_CODE_SESSION_ID")
           if os.environ.get(MEMBER_MARK) and not os.environ.get("SMNS_INTERNAL") else None)
    for sid, ev in local.items():
        seat, peer = by_session.get(sid), ev.get("peer")
        if (latest.get(sid) == "joined") if peer else (sid in latest):
            if latest.get(sid) == "joined":
                # A member with no record (an older binary joined it), or a
                # provisional one its lineage can now settle (an older
                # binary's hand-off), has it written or replaced here.
                ensure_record(project, sid, seat, peer, events=events)
                out += refresh_joined(project, sid, joined[sid])
            continue
        out += join_on_sight(project, sid, seat, peer, bool(peer), recheck=lambda ev=ev: here_now(project, ev),
                             marked=sid == own and member_mark(peer), events=events)
    for sid, ev in local.items():
        seat = ev.get("seat")
        if seat and "peer" not in ev and seat["status"] != "retired" and (successor := continued_in(sid)):
            out += hand_off(project, sid, successor)
    return out


def here_now(project, ev):
    """The project, when what made a session this machine's in it (`ev`, its
    _local_sessions entry: a seat, a running engine record) still resolves
    to it as the directories, the transcript and the join override are now;
    else None. A join's recheck: a reconciliation decides on the cache
    generation's resolution, which may predate a .smns written or a join
    made since (a re-join after a move, F3 of the org directory's
    acceptance run)."""
    seat, peer = ev.get("seat"), ev.get("peer")
    for p in (seat_project(seat, fresh=True) if seat else None, record_project(peer, fresh=True) if peer else None):
        if p is not None and p.id == project.id:
            return project
    return None


def retire_moved(project, sid, where, recheck=None):
    """`retired`, reason `moved`, for a member of the project whose project
    is now `where`, naming it; nothing when `where` is the project itself or
    no project (a session in none stays where it was). `recheck`, when
    given, resolves the session's project again under the session file's
    lock: what a reconciliation read a moment ago may have changed since (a
    `join` meanwhile), and the move is written only if it still holds."""
    if where is None or where.id == project.id:
        return []

    def guard(evs):
        if latest_membership(evs) != "joined":
            return False
        now_in = recheck() if recheck else where
        return now_in is not None and now_in.id == where.id

    return lifecycle(project, sid, "retired", guard=guard, required=False, by="", reason="moved", project=where.id)


def refresh_joined(project, sid, last):
    """A member the engine relocated within this project (EnterWorktree, an
    exit from one, a `/cd` inside the repository) is joined again where it
    runs now: `joined` with `relocated: true`, its alias and the rest as its
    last `joined` had them, `by` empty, `cwd` (and repo, branch) the launch
    directory — the one Resume and known_checkouts read, whose old value may
    name a directory since removed. Written only when the transcript names a
    launch directory other than the last joined's `cwd`, checked again under
    the session file's lock, so it is one event per relocation, never one per
    tick."""
    launch = launch_cwd(sid)   # the transcript's; nothing where it names none
    if not launch or launch == str(last.get("cwd") or ""):
        return []

    def guard(evs):
        if latest_membership(evs) != "joined":
            return False
        j = next((e for e in reversed(evs) if e["kind"] == "joined"), None)
        return j is not None and str(j.get("cwd") or "") != launch

    alias, source = own_alias(_own_events(project, sid), sid)
    fields = joined_fields(alias or str(last.get("alias") or sid[:8]),
                           source or str(last.get("name_source") or "derived"), launch,
                           str(last.get("worktree") or ""), str(last.get("role") or ""), str(last.get("seat") or ""),
                           "", str(last.get("session_kind") or ""), session=sid)
    return lifecycle(project, sid, "joined", guard=guard, required=False, relocated=True, **fields)


def moved_here(project, sid):
    """Whether a session joining the project comes from another project here:
    its own events there end in a membership (joined, not yet retired by the
    reconciliation that sees it gone) or in a `moved` retirement naming this
    project. The `by` of its joined says so (`move`)."""
    for p in known_projects():
        if p.id == project.id:
            continue
        last = next((e for e in reversed(_own_events(p, sid)) if e["kind"] in MEMBERSHIP), None)
        if last and (last["kind"] == "joined" or (last.get("reason") == "moved" and last.get("project") == project.id)):
            return True
    return False


def joinable(seat, peer, marked=False):
    """Whether a session of this machine is a member on sight: a seat whose
    record is not retired, or a seat-less session the harness records as
    `interactive` or `bg` whose entrypoint is no headless or SDK run (`sdk-*`:
    another tool's `claude -p` is no member, whatever its kind) unless its
    host marked it (`marked`, member_mark)."""
    if seat:
        return seat["status"] != "retired"
    peer = peer or {}
    return (str(peer.get("kind") or "") in JOINABLE_KINDS
            and (marked or not str(peer.get("entrypoint") or "").startswith(HEADLESS_ENTRYPOINT)))


def member_mark(peer):
    """Whether the session `peer` records, the one this process runs for (the
    hook's, the bridge child's, or the one a verb's caller is), was launched
    by a host that marked it a member: MEMBER_MARK names the pid that spawned
    its engine. A run started from inside a marked session inherits the
    variable but has another parent, so it is no member; a /clear keeps the
    engine, and the mark holds for the session it goes on as."""
    mark = os.environ.get(MEMBER_MARK, "")
    return mark.isdigit() and int(mark) > 1 and parent_pid((peer or {}).get("pid")) == int(mark)


def parent_pid(pid):
    """A live process's parent pid, or None when ps cannot tell."""
    try:
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(int(pid))], capture_output=True, text=True,
                             timeout=5).stdout.strip()
    except (TypeError, ValueError, OSError, subprocess.SubprocessError):
        return None
    return int(out) if out.isdigit() else None


def _ts_epoch(ts):
    """A log `ts` (UTC, milliseconds) as epoch seconds, or None."""
    s = str(ts or "")
    try:
        whole = calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    frac = re.match(r"\.(\d+)", s[19:])
    return whole + (float("0." + frac.group(1)) if frac else 0.0)


def process_started(rec):
    """When a harness record's process started, in epoch seconds: its
    `startedAt` (ms), else its `procStart` read as UTC (same_process); None
    when neither is there."""
    started = rec.get("startedAt")
    if isinstance(started, (int, float)) and not isinstance(started, bool) and started > 0:
        return started / 1000.0
    parsed = _parse_lstart(rec.get("procStart"))
    return calendar.timegm(parsed) if parsed else None


def retirement_holds(events, peer):
    """Whether a seat-less session's `retire` still holds against the process
    its harness record shows. A retirement holds for the life of the process
    that ran when it was recorded: an interactive session has nothing the
    harness can stop, so its process runs on in its human's terminal, and
    re-joining it on sight would undo the retire at the next reading verb.
    The record shows a different process when its pid differs from the one
    the retirement recorded, or when it started after the retirement (a
    resume opens a new process, so a resumed session re-joins, §2). So does
    a hand-off (`continued`): the process that handed its session to a
    background job runs on for a while as it exits. A retirement for any
    other reason (`ended`: its process was not seen) does not hold against a
    running process."""
    last = next((e for e in reversed(events) if e["kind"] in MEMBERSHIP), None)
    if not last or last["kind"] != "retired" or last.get("reason") not in ("retire", "continued"):
        return False
    peer = peer or {}
    if last.get("pid") not in (None, "") and str(last["pid"]) != str(peer.get("pid")):
        return False
    started, retired = process_started(peer), _ts_epoch(last.get("ts"))
    return started is None or retired is None or started <= retired


def join_on_sight(project, sid, seat, peer, running, by=None, recheck=None, marked=False, evidence=None,
                  events=None):
    """joined for a session seen on this machine, when it is joinable and
    the log does not already hold it as a member: a running session whose
    latest membership is absent or retired (a live process is evidence of
    activation), a seat that is not running only when it has no membership
    event at all; a seat-less session retired by `retire` only once a new
    process runs it (retirement_holds). Checked again under the session
    file's lock, the seat record re-read there, so a concurrent retire cannot
    be undone. Shared by reconciliation and the hook (§2, §4).

    A seat-less session joins under the alias it already holds (held_alias);
    a background job the harness forked from an interactive session that is
    still exiting joins as that member's continuation (hand_off), under its
    alias. Its `cwd` is its launch directory (launch_cwd), the one Resume
    needs; `by` is `move` when it comes from another project here
    (moved_here), unless the caller names it (`join`). `recheck`, when
    given, resolves the session's project again under the lock, and the
    join is written only if it is still this one (retire_moved). `marked`:
    its host marked it (member_mark). Its record is made sure of first
    (ensure_record, with the hook's `evidence` when the hook joins it), so
    the joined carries what it publishes once it is final."""
    if not joinable(seat, peer, marked):
        return []

    def guard(evs):
        last = latest_membership(evs)
        if (last == "joined") if running else (last is not None):
            return False
        if not seat and retirement_holds(evs, peer):
            return False
        if recheck is not None and ((p := recheck()) is None or p.id != project.id):
            return False
        fresh = reload_seat(seat["seat_id"]) if seat else None
        return not (seat and (fresh is None or fresh["status"] == "retired"))

    out = []
    if by is None:
        by = "move" if moved_here(project, sid) else ""
    if seat:
        ensure_record(project, sid, seat, peer, evidence, events=events)
        fields = joined_fields(seat["alias"], "seat", seat_cwd(seat, fresh=True), seat["worktree"], seat["role"],
                               seat["seat_id"], by, "seat", session=sid)
    else:
        held = own_alias(_own_events(project, sid), sid)
        if str(peer.get("kind") or "") == "bg" and not held[0]:
            old, old_peer = predecessor(project, sid)
            if old:
                out += hand_off(project, old, sid, old_peer)
            else:
                old = handed_to(project, sid)
            if old:
                held = own_alias(_own_events(project, old), old)
        ensure_record(project, sid, seat, peer, evidence, events=events)
        alias, source = held_alias(*held, peer, sid, shadowing(project, sid))
        fields = joined_fields(alias or sid[:8], source or "derived",
                               launch_cwd(sid, fallback=str(peer.get("cwd") or ""), fresh=True), by=by,
                               session_kind=str(peer.get("kind") or ""), session=sid)
    joined = lifecycle(project, sid, "joined", guard=guard, required=False, **fields)
    if joined:
        position_carry(project, sid)
    return out + joined


def handed_to(project, session):
    """The session of this machine whose membership of the project ended
    handing it to `session` (hand_off: its latest membership a `continued`
    retirement naming `session`), or None. A reconciliation finishes such a
    hand-off before the job has joined here when the old session exited
    before any tick saw the job beside it, or when the old one was in the
    project only by a join override the job held only once the hand-off
    carried it; the job then joins under the alias the old one held."""
    for e in reversed(log_read(project, kinds=("retired",))):
        old = str(e.get("session") or "")
        if e.get("reason") != "continued" or e.get("to") != session or writer_session(e["writer"]) != old:
            continue
        last = next((x for x in reversed(_own_events(project, old)) if x["kind"] in MEMBERSHIP), None)
        if last and last["kind"] == "retired" and last.get("reason") == "continued" and last.get("to") == session:
            return old
    return None


def held_alias(logged, logged_source, peer, session, shadowed=None):
    """(alias, name_source) a seat-less session goes by: its harness name
    when someone gave it, else the alias the log already holds for it
    (`logged`, own_alias: its own, or the one of the session it continues),
    else its harness name; ("", "") for none. A name the harness made up
    (GENERATED_NAMES) changes with each process — a resume draws a new
    suffix, a background job gets a title — so it never replaces an alias
    already held: the address stays the one its peers know.

    Nor is a harness name taken that would shadow a live identity, the alias
    of a seat or of another current member of the project (`shadowed`, from
    shadowing): a `--bg` copy inherits its source's name, and the engine's
    record says `user` for it as for a /rename. The session keeps the alias
    it holds, else its short id, and its title still shows the name."""
    name = str((peer or {}).get("name") or "")
    source = str((peer or {}).get("nameSource") or "derived")
    if logged == session[:8]:   # the placeholder a nameless session joined under
        logged = ""
    if name and (source not in GENERATED_NAMES or not logged) \
            and not (name != logged and shadowed is not None and shadowed(name)):
        return name, source
    return (logged, logged_source) if logged else ("", "")


def shadowing(project, session, info=None, all_seats=None):
    """held_alias's `shadowed` for a session of `project`: whether a name is
    the alias of a seat of the project that is not retired, or of a current
    member of it (its latest membership `joined`) other than the session and
    the sessions it continues. `info` (_projection) and `all_seats` when the
    caller holds them; else read at the first question, which only a harness
    name that differs from the alias the session holds raises."""
    if project is None:
        return None

    def shadowed(name):
        nonlocal info, all_seats
        if info is None:
            info = _projection(log_read(project, kinds=MEMBERSHIP + ("renamed",)))
        mine = {session, *lineage(session, info)}
        if any(sid not in mine and r["latest"] and r["latest"]["kind"] == "joined"
               and logged_alias(sid, info)[0] == name for sid, r in info.items()):
            return True
        if all_seats is None:
            all_seats = seats()
        return any(s["alias"] == name and s["status"] != "retired" and s["current"] not in mine
                   and (p := seat_project(s)) is not None and p.id == project.id for s in all_seats)

    return shadowed


def own_alias(events, session):
    """(alias, name_source) of the latest joined or renamed among a session's
    own events; ("", "") for none, or the placeholder (its short id)."""
    named = [e for e in events if e["kind"] in ("joined", "renamed") and e.get("alias")]
    if not named or str(named[-1]["alias"]) == session[:8]:
        return "", ""
    return str(named[-1]["alias"]), str(named[-1].get("name_source") or "")


# How much of a transcript's end is read for its hand-off record: the harness
# appends it as the session leaves (a few KiB of bookkeeping follow), and
# reads 1 MiB back for it itself.
HANDOFF_REACH = 1 << 20
_HANDOFFS = {}  # session -> ((path, size, mtime_ns), successor): valid while the file is unchanged


def continued_in(session, fresh=False):
    """The session `session` continues in, when the harness sent it to the
    background (`/background`, the agents view's ←): that starts a job as a
    fork, a new session id and process, lets the old process exit, and
    appends `{"type": "continued-in", "continuedInSessionId": <new>}` to the
    old transcript — the record its own /resume reads to hide the old
    session (harness 2.1.300). Read as the harness reads it: the latest such
    record with no turn after it, so an old session resumed and worked in
    again is its own again. "" when there is none. `fresh`: a transcript
    the index has not listed yet looked for (transcript_path's `fresh`)."""
    path = transcript_path(session) or (transcript_path(session, fresh=True) if fresh else "")
    try:
        st = os.stat(path) if path else None
    except OSError:
        st = None
    if st is None:
        return ""
    key = (path, st.st_size, st.st_mtime_ns)
    hit = _HANDOFFS.get(session)
    if hit and hit[0] == key:
        return hit[1]
    found = ""
    try:
        with open(path, "rb") as f:
            for _, line in _lines_backward(f, _complete_end(f), HANDOFF_REACH):
                if b'"continued-in"' not in line and b'"user"' not in line and b'"assistant"' not in line:
                    continue
                r = _record(line) or {}
                if r.get("type") == "continued-in":
                    to = str(r.get("continuedInSessionId") or "")
                    found = to if UUID_RE.match(to) and to != session else ""
                    break
                if is_turn_record(r):
                    break
    except OSError:
        return ""
    _HANDOFFS[session] = (key, found)
    return found


COMMAND_ROW_TAGS = ("<local-command-stdout>", "<local-command-stderr>", "<command-name>", "<command-message>")


def is_turn_record(r):
    """Whether a transcript record is part of a turn, as the harness tells
    one after a hand-off: a finished assistant message (not an API error), or
    a prompt the human typed. A slash command's echo or output is none: the
    engine (2.1.303) writes `/background`'s empty `<local-command-stdout>`
    right after the hand-off record."""
    if r.get("type") == "assistant":
        msg = r.get("message") if isinstance(r.get("message"), dict) else {}
        return r.get("isApiErrorMessage") is not True and isinstance(msg.get("stop_reason"), str)
    if r.get("type") != "user" or r.get("isMeta"):
        return False
    content = (r.get("message") or {}).get("content") if isinstance(r.get("message"), dict) else None
    if isinstance(content, str) and content.lstrip().startswith(COMMAND_ROW_TAGS):
        return False
    return (isinstance(content, str) and bool(content.strip())) or (
        isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in content))


def predecessor(project, session):
    """(session, harness record) of the session `session` continues: a
    running interactive session of this machine in the project (only one can
    be sent to the background), still exiting, whose transcript names
    `session` (continued_in); else a session a seat of the project holds that
    no longer runs, with no record; (None, None) for none. A seat-less one
    that has exited already is reconciliation's to find, as its membership
    ends."""
    for rec in peer_records():
        old = rec.get("sessionId")
        if (isinstance(old, str) and old != session and UUID_RE.match(old) and rec.get("kind") == "interactive"
                and peer_running(rec) and (p := record_project(rec)) is not None
                and p.id == project.id and continued_in(old) == session):
            return old, rec
    for s in project_seats(project):
        old = s["current"]
        if old and old != session and s["status"] != "retired" and not session_running(old) \
                and continued_in(old) == session:
            return old, None
    return None, None


def hand_off(project, old, new, old_peer=None):
    """Record that the member `old` stood for continues in session `new`
    (continued_in): its chat cursor and its join override carried to `new`;
    a seat that held `old` moved to `new`; `old` retired, reason `continued`,
    naming `new` (and the process it saw, which may still be exiting:
    retirement_holds); and `new`, if it already joined under a name the
    harness made up, renamed to the alias `old` held. The projection
    (lineage) carries the rest: by, the in-charge line, status, worktree.
    Returns the events appended.

    Ordered so a hand-off cut short is finished by the next one: the cursor
    merge is idempotent, the retirement comes only after the seat moved (a
    seat whose lock another command holds leaves `old` joined, and the next
    reconciliation tries the whole of it again), and the rename runs while
    `old` stands retired to `new`, whoever retired it. The record goes first:
    `new`'s is `old`'s provenance (ensure_record), unless it has a final one."""
    def still_joined(evs):
        return latest_membership(evs) == "joined"

    ensure_record(project, new, former=[old])

    try:
        carried = cursor_load(project, old)
        mine = writer_id(old)
        seqs = [e["seq"] for e in _own_events(project, old) if e["writer"] == mine]
        if seqs:
            carried[mine] = max(carried.get(mine, 0), max(seqs))
        if carried:
            cursor_save(project, new, carried)
    except OSError as e:
        warn("carrying %s's chat cursor to %s failed: %s" % (old[:8], new[:8], e))
    try:
        if override_of(old) and not override_of(new):
            write_override(new, override_of(old))
    except OSError as e:
        warn("carrying %s's join override to %s failed: %s" % (old[:8], new[:8], e))
    out = []
    seat = next((s for s in seats() if s["current"] == old and (p := seat_project(s)) and p.id == project.id), None)
    if seat:
        try:
            out += follow_seat(seat, old, new)
        except ResumeRefused:
            return out
    fields = {"pid": old_peer.get("pid")} if old_peer else {}
    out += lifecycle(project, old, "retired", guard=still_joined, required=False, by="", reason="continued",
                     to=new, **fields)
    theirs = _own_events(project, old)
    last = next((e for e in reversed(theirs) if e["kind"] in MEMBERSHIP), None)
    if not last or last["kind"] != "retired" or last.get("reason") != "continued" or last.get("to") != new:
        return out
    alias, source = own_alias(theirs, old)
    own = _own_events(project, new)
    if alias and latest_membership(own) == "joined":
        mine_alias, mine_source = own_alias(own, new)
        if (not mine_alias or mine_source in GENERATED_NAMES) and (mine_alias, mine_source) != (alias, source):
            out += lifecycle(project, new, "renamed", guard=still_joined, required=False,
                             alias=alias, name_source=source)
    return out


def follow_seat(seat, old, new):
    """Move a seat from `old` to the session it continues in, under the
    seat's lock: the same occupant goes on, so nothing else of the record
    changes. A seat that no longer holds `old` is left as it is; a seat
    whose lock another command holds raises ResumeRefused, for the caller
    to try again later. Returns the events appended."""
    locks = lock_seat(seat, refusal=ResumeRefused)
    try:
        fresh = reload_seat(seat["seat_id"])
        if fresh is None or fresh["current"] != old:
            return []
        row = agent_row(session_id=new)
        meta_set(seat["seat_id"], {"current": new, "short": str((row or {}).get("id") or ""), "updated": now()})
        return join_seat(reload_seat(seat["seat_id"]))
    finally:
        unlock(locks)


def latest_across_writers(events):
    """Each writer's latest event by seq (authoritative within a writer),
    then the later ts between writers (§3); None for no events. `events` holds
    each writer's stream in seq order, so the last one seen of a writer is its
    latest."""
    last = {}
    for e in events:
        last[e["writer"]] = e
    return max(last.values(), key=lambda e: e["ts"]) if last else None


def _projection(events):
    """Per session, what the log says of it: its latest membership event and
    latest joined (by seq, in its own file), the first non-empty `by`, its
    latest rename, published state, and published title (its own file), its
    in-charge events (for charge_of), and its status: each writer's latest by
    seq, the later ts between writers (§3). `owned`: its latest joined that
    publishes its record (RL6's listing fields: a record moves only up, and
    each move is published again; a later joined that publishes nothing, an
    older binary's, never erases them). And its hand-offs: `to`, the
    session it continues in (the latest `retired` reason `continued` of its
    own, unless it joined again since: a session resumed after it was handed
    off is its own member, and the job keeps what its own events hold), and
    `continues`, the session that names it so (lineage). `aliases`: every
    alias its own joined and renamed events carried, each with the latest ts
    among them (the former aliases a name still reaches it by, §4 of the
    charge names design)."""
    info = {}

    def row(sid):
        return info.setdefault(sid, {"latest": None, "joined": None, "by": "", "renamed": None, "state": None,
                                     "titled": None, "in_charge": [], "status": [], "to": "", "continues": "",
                                     "aliases": {}, "owned": None})

    for e in events:
        sid, kind = e.get("session"), e["kind"]
        if kind not in LIFECYCLE or not isinstance(sid, str) or not sid:
            continue
        own = writer_session(e["writer"]) == sid
        r = row(sid)
        if kind in MEMBERSHIP or kind in ("renamed", "state", "titled"):
            if not own:
                continue
            if kind in ("joined", "renamed") and e.get("alias"):
                held, ts = str(e["alias"]), str(e.get("ts") or "")
                r["aliases"][held] = max(r["aliases"].get(held, ""), ts)
            if kind in MEMBERSHIP:
                r["latest"] = e
                if kind == "joined":
                    r["joined"] = e
                    r["to"] = ""
                    if not r["by"] and e.get("by"):
                        r["by"] = str(e["by"])
                    if publishes(e):
                        r["owned"] = e
                elif e.get("reason") == "continued" and UUID_RE.match(str(e.get("to") or "")):
                    r["to"] = str(e["to"])
            else:
                r[kind] = e
        elif kind == "in-charge":
            r["in_charge"].append(e)
        else:
            r["status"].append(e)
    for sid, r in list(info.items()):
        if r["to"] and r["to"] != sid:
            row(r["to"])["continues"] = sid
    for r in info.values():
        r["status"] = latest_across_writers(r["status"])
    return info


def lineage(sid, info):
    """The sessions `sid` continues (hand_off), newest first: the one it was
    forked from, that one's, and so on."""
    out, cur = [], (info.get(sid) or {}).get("continues")
    while cur and cur != sid and cur not in out:
        out.append(cur)
        cur = (info.get(cur) or {}).get("continues")
    return out


def logged_alias(sid, info):
    """(alias, name_source) the log holds for a session (own_alias, read off
    the projection): its own latest name when someone gave it, else the
    oldest alias along the sessions it continues, a given name there first.
    ("", "") for none."""
    held = ("", "")
    for s in [sid] + lineage(sid, info):
        r = info.get(s)
        named = (r["renamed"] or r["joined"] or {}) if r else {}
        alias, source = str(named.get("alias") or ""), str(named.get("name_source") or "")
        if not alias or alias == s[:8]:
            continue
        if source not in GENERATED_NAMES:
            return alias, source
        held = alias, source
    return held


def charge_of(member, events, title=True, published=""):
    """(line, source, ts): what a member is in charge of, the first present of
    (§5) the latest `set` in-charge line, the latest `derived` line, the name
    the human gave it, and its title — read from its transcript on this
    machine, else the one its machine `published` (`titled`); ("", "", "")
    when none is. `ts` is the line's event's, "" for a line no event wrote (a
    name, a title). A set or derived line written empty is no line. `events`
    is the log, or any part of it holding the member's in-charge events, each
    writer's in seq order. With title=False the transcript is not read (the
    daemon's tick has no use for the line). A line set for a session the
    member continues (`former`) is the member's."""
    sessions = (member.session,) + tuple(member.former)
    mine = [e for e in events if e["kind"] == "in-charge" and e.get("session") in sessions]
    for source in ("set", "derived", "name", "title"):
        ts = ""
        if source == "name":
            line = member.alias if member.name_source == "user" else ""
        elif source == "title":
            if member.local:
                line = transcript_title(member.session) if title and member.session else ""
            else:
                line = published
        else:
            e = latest_across_writers([x for x in mine if x.get("source") == source])
            line, ts = (str(e.get("text") or "").strip(), str(e.get("ts") or "")) if e else ("", "")
        if line:
            return line, source, ts
    return "", "", ""


def charge_shown(m):
    """The in-charge line a row draws: not a name the alias column already shows."""
    return "" if m.charge_source == "name" else m.charge


def ts_age(ts):
    try:
        then = calendar.timegm(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    return max(0.0, time.time() - then)


def proposed_names(events, sessions):
    """(names, latest): the charge names sminos proposed for a member — the
    `name`s of the derived in-charge events of `sessions` (its session and
    the ones it continues) — and the newest of them, "" for none. `events`
    holds each writer's in seq order."""
    named = [e for e in events if e.get("kind") == "in-charge" and e.get("session") in sessions
             and e.get("source") == "derived" and isinstance(e.get("name"), str) and e["name"]]
    latest = latest_across_writers(named)
    return {e["name"] for e in named}, (latest["name"] if latest else "")


def _member(sid, r, seat, peer, local, title=True, info=None, shadowed=None):
    """One row of the projection: what the log says of the session, and, on
    this machine, its seat record and its process. A session that continues
    others (lineage, in `info`) is the member they stood for: what it has
    not set of its own — its alias (held_alias), its spawner, its status,
    its worktree, its in-charge line, its owners — it carries on from them.
    A member of this machine with a record takes its owners and origin
    from it: the record wins over the log."""
    info = info if info is not None else ({sid: r} if r else {})
    former = tuple(lineage(sid, info))
    chain = [info[s] for s in (sid,) + former if info.get(s)]
    j = (r or {}).get("joined") or {}
    if seat:
        alias, name_source = seat["alias"], "seat"
    else:
        alias, name_source = held_alias(*logged_alias(sid, info), peer, sid, shadowed)
    machine = str(j.get("machine") or "")
    local = local or bool(seat) or not machine or is_self(machine, sid)
    age = active = None
    # Here, the engine's record of the session decides whether it runs and
    # its word, for a seat as for a seat-less member, whatever directory the
    # record names (the session may have joined where a turn of it ran); the
    # inbox socket is delivery's question, never the word's (board:646).
    rec = (peer or session_running(sid)) if local else None
    # charge_of reads each writer's events in seq order, and one writer (a
    # remote operator) may have set a line for each session of the chain.
    in_charge = sorted((e for x in chain for e in x["in_charge"]), key=lambda e: (e["writer"], e["seq"]))
    if not local:
        published = (r or {}).get("state") or {}
        state_word, age = str(published.get("state") or ""), (ts_age(published["ts"]) if published else None)
        active = age
    elif seat:
        state_word = seat_state(seat, rec)
    elif rec:
        state_word = peer_state(rec)
    else:
        state_word = "stopped" if transcript_path(sid) else "gone"
    if rec and isinstance(rec.get("updatedAt"), (int, float)) and not isinstance(rec["updatedAt"], bool):
        active = max(0.0, time.time() - rec["updatedAt"] / 1000.0)
    if seat:
        kind = "seat"
    elif rec and rec.get("kind"):
        kind = str(rec["kind"])
    else:
        kind = str(j.get("session_kind") or "")
    cwd = str(j.get("cwd") or "") or (seat or {}).get("cwd") or str((rec or {}).get("cwd") or "")
    repo, branch = repo_branch(cwd) if local else (str(j.get("repo") or ""), str(j.get("branch") or ""))
    status = max((x["status"] for x in chain if x["status"]), key=lambda e: e["ts"], default=None)
    worktree = next((str((x["joined"] or {}).get("worktree") or "") for x in chain
                     if (x["joined"] or {}).get("worktree")), "")
    held = {}
    for x in chain:
        for a, ts in x["aliases"].items():
            held[a] = max(held.get(a, ""), ts)
    for current in (alias or sid[:8],) + tuple(s[:8] for s in (sid,) + former):
        held.pop(current, None)
    record = session_record(sid) if local else None
    owned = next((x["owned"] for x in chain if x.get("owned")), None) or {}
    owners = tuple(record["owners"] if record else owners_of(owned) or ())
    origin = record["origin"] if record else (owned.get("origin") if isinstance(owned.get("origin"), dict) else None)
    m = Member(
        session=sid, short=sid[:8], alias=alias or sid[:8], name_source=name_source,
        machine=host_name() if local else machine, local=local, state=state_word, state_age=age,
        charge="", charge_source="",
        status=str(status.get("text") or "") if status else (seat["now"] if seat else ""),
        by=next((x["by"] for x in chain if x["by"]), ""), worktree=seat["worktree"] if seat else worktree,
        seat=seat, former=former, former_aliases=tuple(sorted(held.items())), kind=kind, cwd=cwd, repo=repo, branch=branch, active_age=active,
        title="" if local else published_title(r), owners=owners, origin=origin, record=record)
    charge, source, ts = charge_of(m, in_charge, title, published_title(r))
    return m._replace(charge=charge, charge_source=source, charge_age=ts_age(ts) if ts else None)


def vacant_member(s):
    """The row of a seat that holds no session."""
    repo, branch = repo_branch(s["cwd"])
    return Member(session="", short="", alias=s["alias"], name_source="seat", machine=host_name(), local=True,
                  state=state(s), state_age=None, charge="", charge_source="", status=s["now"], by="",
                  worktree=s["worktree"], seat=s, kind="seat", cwd=s["cwd"], repo=repo, branch=branch)


def published_title(r):
    """The title the session's machine last published (`titled`, in the
    session's own file), from a _projection row; "" for none."""
    return " ".join(str(((r or {}).get("titled") or {}).get("title") or "").split())


class View(NamedTuple):
    members: list         # the members, newest join first
    rows: list            # the seats no member stands for (vacant, retired, or replaced), newest first
    retired: list         # (alias, short, reason, project moved to) of seat-less sessions the log holds as retired
    events: list          # the log as read, with what reconciliation appended
    info: dict            # _projection(events)
    reconciled: int       # how many events reconciliation appended


def project_view(project):
    """(members, seat rows): the project's members, newest join first, after
    reconciling this machine's sessions into the log; and the project's seats
    no member stands for (vacant, retired, or replaced), newest first. One
    log_read; cached for the invocation until a lifecycle event is appended."""
    return view_of(project)[:2]


def view_of(project, all_seats=None, titles=True):
    """The whole View project_view draws from. `all_seats`: a seat read the
    caller already made (the daemon's tick reads once for every project).
    With titles=False no member's
    in-charge line falls back to its transcript's title (the daemon's tick,
    every few seconds, reads no transcript for a line it never shows); such a
    view is not cached, so no view that shows lines ever lacks one."""
    if titles and project.id in _VIEWS:
        return _VIEWS[project.id]
    all_seats = seats() if all_seats is None else all_seats
    by_session = seats_by_session(project, all_seats)
    local = _local_sessions(project, all_seats)
    events = log_read(project)
    appended = _reconcile(project, events, local, by_session)
    if appended:   # a hand-off may have moved a seat to the session it continues in
        all_seats = seats()
        by_session = seats_by_session(project, all_seats)
        local = _local_sessions(project, all_seats)
    events = events + appended
    info = _projection(events)
    internal = internal_pids()
    forks = {r.get("sessionId") for r in peer_records() if str(r.get("pid")) in internal}
    joined = [(sid, r) for sid, r in info.items()
              if r["latest"] and r["latest"]["kind"] == "joined" and sid not in forks]
    joined.sort(key=lambda x: (x[1]["joined"]["ts"], x[0]), reverse=True)
    out = [_member(sid, r, by_session.get(sid), local.get(sid, {}).get("peer"), sid in local, titles, info,
                   shadowing(project, sid, info, all_seats))
           for sid, r in joined]
    sessions = {m.session for m in out}
    rest = sorted((s for s in all_seats if (not s["current"] or s["current"] not in sessions)
                   and (p := seat_project(s)) and p.id == project.id), key=lambda s: s["updated"], reverse=True)
    rows = [_member(s["current"], info.get(s["current"]), s, None, True, titles, info) if s["current"] else
            vacant_member(s) for s in rest]
    # Seat-less sessions the log holds as retired, by alias: what a tag that
    # names one is told. One that continues in another session is not: its
    # name is the continuation's now. One that moved names where it went.
    retired = [(str((r["renamed"] or r["joined"]).get("alias") or sid[:8]), sid[:8], str(r["latest"].get("reason") or ""),
                str(r["latest"].get("project") or ""))
               for sid, r in info.items()
               if r["latest"] and r["latest"]["kind"] == "retired" and r["joined"] and sid not in by_session
               and r["latest"].get("reason") != "continued"]
    view = View(out, rows, retired, events, info, len(appended))
    if titles:
        _VIEWS[project.id] = view
    return view


def members(project):
    """The project's members (see project_view)."""
    return project_view(project)[0]


def retired_sessions(project):
    """(alias, short, reason, project) of the project's seat-less sessions
    whose membership the log holds as retired — `ended` with their process,
    retired by hand, or `moved` to `project` (an id; "" for none)."""
    return view_of(project).retired


def reconcile(project):
    """Join this machine's unrecorded sessions in the project; how many."""
    _VIEWS.pop(project.id, None)
    all_seats = seats()
    return len(_reconcile(project, log_read(project), _local_sessions(project, all_seats),
                          seats_by_session(project, all_seats)))


def _owed(events, session, record):
    # Imported history was delivered by the old chat: it is never owed; nor
    # is a copy, by its `copy` key alone (addressed_to), so a reader without
    # that rule owes it to no one either — its recipients are another log's.
    # An event marked revoked (delivered_revoke) is owed no more.
    out = []
    for e in events:
        if e["writer"].startswith("legacy/") or writer_session(e["writer"]) == session \
                or not addressed_to(e, session):
            continue
        w = _delivery(record, e["writer"])
        if e["seq"] > w["settled"] and e["seq"] not in w.get("revoked", ()):
            out.append(e)
    return out


def addressees(events):
    """{session: the events addressed to it, in the log's order}: the part of
    the log _owed reads for each session, read once for all of them (the
    daemon asks for every member of every project each tick)."""
    out = {}
    for e in events:
        to = e.get("to")
        if not isinstance(to, list) or not to or "copy" in e:
            continue
        for s in dict.fromkeys(r.get("session") for r in to if isinstance(r, dict)):
            if isinstance(s, str) and s:
                out.setdefault(s, []).append(e)
    return out


def owed(project, member):
    """The events owed to a member, each writer's in seq order from its
    settled prefix."""
    session = member.session
    if not session:
        return []
    return _owed(log_read(project, to_session=session), session, delivered_load(project, session))


def nudge_daemon():
    """Ask this machine's `daemon run` for a tick now rather than at its next
    interval: a message to another machine's member is pushed at once. A
    touch of daemon/nudge, which the loop watches; nothing when no daemon
    ever ran here (the directory is the loop's to make)."""
    path = os.path.join(root(), "daemon", "nudge")
    try:
        with open(path, "a"):
            pass
        os.utime(path)
    except OSError:
        pass


def daemon_log(line):
    with open(os.path.join(root(), "daemon.log"), "a") as f:
        f.write("%s %s\n" % (now(ms=True), line))


def deliver_next(project, member):
    """The one delivery operation, for the sender's fast path and the daemon
    alike. Under delivered/<session>.lock, from choosing through the push to
    the settlement: per writer, push the owed events in seq order, settling
    each, and stop that writer at the first failure (it stays pending, retried
    by the next call, and is settled with a daemon.log line after
    DELIVERY_ATTEMPTS). Returns {"delivered", "pending", "outcomes"}, and
    on a cut-over machine "gated" (below).

    The machine's policy is the boundary here, for every caller: on a
    read-only machine an event written outside it (another machine's, or the
    hub's) is pushed nothing — no frame, no resume — and settled undelivered
    as `refused-read-only` (sminos_policy, read at each such event). Every
    settlement of an outside-origin event of a hub project leaves its outcome
    for the uplink (sminos_outcomes), recorded before the settlement: an
    outcome that cannot be recorded leaves the event pending for a later
    pass, which records it again; a push already made is noted in the
    delivery record (delivered_pushed), so that pass settles it on the same
    outcome without pushing it again (a peer's frame has no bridge key to
    drop a second copy).

    On a machine cut over to its endpoint (O12 M6) a person's words are the
    endpoint's to decide, and its revocations bind every delivery
    (WordsGate): a words-gated writer stops at its first owed such event,
    which is left owed for the uplink to ask `words?` about and deliver on
    the verdict (deliver_verdict) and is listed in `gated`; a `human` event
    no one may ask about goes as a peer's; and an event whose stored signer
    is revoked is marked, never pushed (delivered_revoke)."""
    session = member.session
    result = {"delivered": 0, "pending": 0, "outcomes": []}
    if not session:
        return result
    policy = sibling_module("sminos_policy")
    outcomes = sibling_module("sminos_outcomes")
    gate = WordsGate(project) if sibling_module("sminos_rl10").cut_over() else None
    if gate is not None:
        result["gated"] = []
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        events = log_read(project)
        record = delivered_load(project, session)
        streams = {}
        for e in _owed(events, session, record):
            streams.setdefault(e["writer"], []).append(e)
        cursor = cursor_load(project, session)
        for writer, queue in streams.items():
            outside = policy.outside_origin({"writer": writer})
            noted = _delivery(record, writer).get("pushed")
            for i, e in enumerate(queue):
                if noted and noted[0] == e["seq"]:
                    outcome = noted[1]
                else:
                    held = gate.held(e, session) if gate is not None else None
                    if held == "revoked":
                        result["outcomes"].append((e, outcomes.REFUSED_REVOKED))
                        continue
                    if held is not None:
                        result["pending"] += len(queue) - i
                        break
                    if outside and policy.read_only():
                        outcome = outcomes.READ_ONLY
                    elif gate is not None and gate.gated(e):
                        result["gated"].append(e)
                        result["pending"] += len(queue) - i
                        break
                    else:
                        outcome = push_event(project, member, session, e, events, cursor,
                                             words=gate.words(e) if gate is not None else None)
                        if gate is not None:
                            gate.said(e, outcome)
                result["outcomes"].append((e, outcome))
                if not _conclude(project, member, session, e, outcome, outside):
                    result["pending"] += len(queue) - i
                    break
                if outcome in PUSHED:
                    result["delivered"] += 1
    return result


def _conclude(project, member, session, e, outcome, outside):
    """A push's outcome, settled as deliver_next settles it; whether it
    settled. A failure under DELIVERY_ATTEMPTS stays pending; one past it is
    given up with a daemon.log line and settled. An outside-origin event is
    settled only once its outcome is kept: else it stays pending and the
    next pass records it again — a push noted, so never made twice. The
    caller holds the session's delivery lock."""
    outcomes = sibling_module("sminos_outcomes")
    if outcome.startswith("failed"):
        if delivered_fail(project, session, e["writer"], e["seq"]) < DELIVERY_ATTEMPTS:
            return False
        daemon_log("gave up delivering %s (%s) to %s after %d attempts: %s" % (
            event_ref(e), project.name, session, DELIVERY_ATTEMPTS, outcome))
    if outside and not outcomes.record(project, e, session, outcome, member):
        if outcome in PUSHED:
            delivered_pushed(project, session, e["writer"], e["seq"], outcome)
        return False
    delivered_settle(project, session, e["writer"], e["seq"])
    return True


# A person's words on a machine cut over to its endpoint (O12 M6). The
# endpoint decides them (`words?`, answered on the socket the uplink holds),
# and its revocation set (daemon/revoked.json) binds every delivery. Whose
# `human` events are asked — the words-gated writers — and how the rest go:
#   - `hub/<member>` (a device's), and another machine's `<name>/human` that
#     arrived over the hub (it carries `verified`): asked;
#   - this machine's own `<name>/human` (a current or former name): asked
#     when its append receipt bears it out (receipted), else — a git mirror's
#     import under this name, an event appended before receipts — an
#     unverified peer's, never asked; the writer name is not provenance;
#   - another machine's `<name>/human` with no `verified` (a git mirror's):
#     an unverified peer's, never asked;
#   - a legacy signer's: a peer's, marked so by its label, never asked.
# The uplink alone asks and delivers on the verdict (deliver_verdict); every
# other deliverer leaves a words-gated writer owed at its first such event,
# so no writer's order is split.

WORDS_VERDICTS = ("words", "peer", "refuse")
WORDS_RECORDED = "recorded; the endpoint decides its delivery"


def words_held(e):
    """Whether a log event is a person's words this process may not push: a
    `human` event on a machine cut over to its endpoint, whose delivery is
    the uplink's, after `words?` (O12 M6)."""
    return e.get("kind") == "human" and sibling_module("sminos_rl10").cut_over()


def words_route(project, e):
    """How a `human` event reaches a session on a cut-over machine: "ask"
    (the endpoint's verdict decides), "unverified" (an unverified peer's: a
    git mirror's, or an operator line no append receipt bears out), "legacy"
    (a legacy signer's, a peer's); None for what is no person's words."""
    if e.get("kind") != "human":
        return None
    verified = e.get("verified")
    signer = verified.get("signer") if isinstance(verified, dict) else None
    if isinstance(signer, dict) and signer.get("kind") == "legacy":
        return "legacy"
    if own_operator_event(e):
        return "ask" if receipted(project, e) else "unverified"
    if str(e.get("writer") or "").startswith("hub/") or isinstance(verified, dict):
        return "ask"
    return "unverified"


_UNREADABLE = {"said": None}   # the unreadable revocation set's error, as last said (WordsGate.revoked)


class WordsGate:
    """What a deliverer on a cut-over machine checks of an owed event before
    it pushes it: the revocation set (read again for each event that carries
    a verdict, so a revocation kept mid-batch stops the events after it) and
    the words rule (words_route)."""

    def __init__(self, project):
        self.project = project
        self.rl10 = sibling_module("sminos_rl10")

    def revoked(self):
        """The revocation set as it is now; None when it cannot be read, said
        in daemon.log once while it stays so."""
        try:
            got = self.rl10.revoked()
        except self.rl10.RevokedUnreadable as e:
            if _UNREADABLE["said"] != str(e):
                _UNREADABLE["said"] = str(e)
                daemon_log("delivery: %s — nothing that carries a signer is delivered until it can be read" % e)
            return None
        _UNREADABLE["said"] = None
        return got

    def held(self, e, session):
        """What the revocation set says of an event: None when nothing holds
        it; "revoked" when its stored signer is (marked: delivered_revoke),
        "unmarked" when it is and its outcome could not be kept (it stays
        owed), "unchecked" when it carries a signer and the set cannot be
        read (it waits: fail-closed). An event with no `verified` (this
        machine's own, a git mirror's) names no signer to check. The caller
        holds the session's delivery lock."""
        if not isinstance(e.get("verified"), dict):
            return None
        revoked = self.revoked()
        if revoked is None:
            return "unchecked"
        if not self.rl10.event_revoked(e, revoked):
            return None
        if not delivered_revoke(self.project, session, e["writer"], e["seq"]):
            return "unmarked"
        daemon_log("%s (%s) is signed by a revoked key: marked refused-revoked for %s, never delivered"
                   % (event_ref(e), self.project.name, session))
        return "revoked"

    def gated(self, e):
        """Whether the endpoint's verdict decides the event (words_route
        "ask"): left owed for the uplink."""
        return words_route(self.project, e) == "ask"

    def words(self, e):
        """The verdict an event the gate let through is pushed under: a
        `human` event as a peer's, anything else as push_live decides it
        (None)."""
        return False if words_route(self.project, e) else None

    def said(self, e, outcome):
        """A `human` event nothing verified, once it reached the session,
        said in daemon.log."""
        if outcome in PUSHED and words_route(self.project, e) == "unverified":
            daemon_log("%s (%s) is delivered as an unverified peer message, never asked: %s" % (
                event_ref(e), self.project.name,
                "no append receipt bears it out" if own_operator_event(e) else "it came through a git mirror"))


def _first_owed(session, writer, events, record):
    return next((x for x in _owed(events, session, record) if x["writer"] == writer), None)


def deliver_verdict(project, member, event, verdict):
    """The endpoint's verdict on a words-gated event (`words`, `peer` or
    `refuse`, O12 M6) carried out, as deliver_next carries out a push: under
    the session's delivery lock, and only while the event is still its
    writer's first owed, the same body (a revocation, another deliverer or
    the attempts given up settled it meanwhile, or a git merge put another
    line there: None, nothing done). `words` pushes it as the person's words
    (the bridge, then a --bg job's supervisor), `peer` as an inbox frame,
    `refuse` not at all: it settles `refused-words`, its outcome kept for
    the uplink. The revocation set and the read-only policy are read again
    first. The outcome, or None."""
    session = member.session
    if not session or verdict not in WORDS_VERDICTS:
        return None
    policy = sibling_module("sminos_policy")
    outcomes = sibling_module("sminos_outcomes")
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        events = log_read(project)
        record = delivered_load(project, session)
        e = _first_owed(session, event["writer"], events, record)
        if e is None or e["seq"] != event["seq"] or event_hash(e) != event_hash(event):
            return None
        outside = policy.outside_origin(e)
        noted = _delivery(record, e["writer"]).get("pushed")
        if noted and noted[0] == e["seq"]:
            outcome = noted[1]
        else:
            held = WordsGate(project).held(e, session)
            if held == "revoked":
                return outcomes.REFUSED_REVOKED
            if held is not None:
                return None
            if outside and policy.read_only():
                outcome = outcomes.READ_ONLY
            elif verdict == "refuse":
                outcome = outcomes.REFUSED_WORDS
                daemon_log("the endpoint refused %s (%s) as words into %s: nothing delivered" % (
                    event_ref(e), project.name, session))
            else:
                outcome = push_event(project, member, session, e, events, cursor_load(project, session),
                                     words=verdict == "words")
        _conclude(project, member, session, e, outcome, outside)
        return outcome


def words_unanswered(project, member, event, why):
    """The endpoint gave no verdict on a words-gated event in time (O12 M6):
    a failed attempt, as a failed push is (delivered_fail; given up after
    DELIVERY_ATTEMPTS), when it is still its writer's first owed. The
    attempts, or None."""
    session = member.session
    if not session:
        return None
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        record = delivered_load(project, session)
        e = _first_owed(session, event["writer"], log_read(project), record)
        if e is None or e["seq"] != event["seq"]:
            return None
        _conclude(project, member, session, e, "failed:%s" % why,
                  sibling_module("sminos_policy").outside_origin(e))
        return _delivery(delivered_load(project, session), e["writer"]).get("attempts")


def words_due(project, members):
    """{session: [event]}: for each of the members, the first owed event of
    each words-gated writer (words_route "ask") that no deliverer holds —
    none noted as pushed, none another event of its writer stands before.
    The project's log read once, and split by addressee once (addressees),
    as the daemon's delivery pass splits it: each member's owed events are
    read from its own share, not from the whole log again. What the uplink
    asks `words?` about. An outside event on a read-only machine is none:
    deliver_next settles it `refused-read-only` unasked."""
    policy = sibling_module("sminos_policy")
    read_only = policy.read_only()
    to = addressees(log_read(project))
    out = {}
    for m in members:
        if not m.session or m.session not in to:
            continue
        record = delivered_load(project, m.session)
        firsts = {}
        for e in _owed(to[m.session], m.session, record):
            firsts.setdefault(e["writer"], e)
        due = [e for w, e in sorted(firsts.items())
               if words_route(project, e) == "ask" and (_delivery(record, w).get("pushed") or [None])[0] != e["seq"]
               and not (read_only and policy.outside_origin(e))]
        if due:
            out[m.session] = due
    return out


def frame_of(project, e, events, session, cursor):
    """The frame an event is pushed as. A `send` keeps its own frame (its id
    is what `send --wait` looks for), its sender shown as the `--from`
    override when it had one, then the label; anything else is a chat frame,
    whose target is `@you`, or a broadcast's scope (target_label: `@all`,
    `@all on mini`).
    Its unread count leaves out copies: each is a record of a message
    another log carries, not one spoken here."""
    if e.get("msg_id"):
        return compose_frame(str(e.get("via") or e.get("from") or ""), e["msg_id"], str(e.get("text") or ""),
                             sender_labels(project)(e))
    unread = sum(1 for x in events if x is not e and x["kind"] in CHAT_KINDS and "copy" not in x and
                 writer_session(x["writer"]) != session and x["seq"] > cursor.get(x["writer"], 0))
    return compose_chat_frame(project.name, event_ref(e), str(e.get("from") or ""),
                              target_label(e) if e.get("wake") else "@you", unread, str(e.get("text") or ""),
                              sender_labels(project)(e))


def push_event(project, member, session, e, events, cursor, words=None):
    """Push one event to one member. An addressed event resumes a stopped
    member; an @all (`wake`) reaches only the live. A seat-less member's
    membership is read again from its own file first: `member` may be a
    snapshot taken before a `retire`, which leaves an interactive session's
    process running (§2), and a retired member is pushed nothing — the event
    settles as recorded, as it does for a retired seat. `words`: the
    endpoint's verdict on a person's words (push_live)."""
    if member.seat is None and latest_membership(_own_events(project, session)) == "retired":
        return "recorded"
    verdict = {} if words is None else {"words": words}   # a machine not cut over calls as it always has
    return push_member(member, frame_of(project, e, events, session, cursor), not e.get("wake"), session=session,
                       event=e, project=project.id, **verdict)


def compose_chat_frame(project_name, ref, sender, target, unread, text, label=""):
    """A chat event's frame; `label` is what follows the sender's alias
    (sender_labels)."""
    return "[sminos chat %s %s from %s%s → %s%s]\n%s" % (
        project_name, ref, sender, label, target, (" | unread %d" % unread) if unread else "", text)


def sender_labels(project):
    """e → the clause after a sender's alias that says whose session sent
    the event (the label, O12 M6), read from the stored line's `verified`
    alone — the endpoint's verdict, never resolved through an alias:
    `, owned by <email>[, <email>]` (an owner by its id where the endpoint
    had no email for it), ` (owners unverified)` when the endpoint attested
    none, ` (unverified, legacy)` for a legacy signer, and ` (signed by a
    revoked key)` for a signer in the revocation set, however old the event,
    never `owned by`; with the set unreadable nothing reads as owned. An
    event claiming this machine's operator writer without its append receipt
    (a git mirror's import, an event from before receipts) is
    ` (unverified)` when it is later than the cutover (identity.json's
    `cutover`; the owner's ruling): history from before it reads as it did
    then, though delivery still never takes such an event as words. Anything
    else, and everything on a machine not cut over, carries none. The
    revocation set is read once, when first needed."""
    rl10 = sibling_module("sminos_rl10")
    if not rl10.cut_over():
        return lambda e: ""
    held = {}
    since = _ts_epoch((rl10.cutover() or {}).get("cutover"))

    def after_cutover(e):
        """Whether the event is later than the cutover; when either time
        cannot be read, so (the clause stays)."""
        at = _ts_epoch(e.get("ts"))
        return since is None or at is None or at > since

    def revoked():
        if "set" not in held:
            try:
                held["set"] = rl10.revoked()
            except rl10.RevokedUnreadable:
                held["set"] = None
        return held["set"]

    def label(e):
        verified = e.get("verified")
        if not isinstance(verified, dict):
            return " (unverified)" if own_operator_event(e) and after_cutover(e) and not receipted(project, e) else ""
        signer = verified.get("signer")
        if isinstance(signer, dict) and signer.get("kind") == "legacy":
            return " (unverified, legacy)"
        if revoked() is None:
            return " (owners unverified)"
        if rl10.signer_revoked(signer, revoked()):
            return " (signed by a revoked key)"
        owners = verified.get("owners")
        if not isinstance(owners, list):
            return ""
        names = [n for n in map(owner_name, owners) if n]
        return ", owned by " + ", ".join(names) if names else " (owners unverified)"
    return label


def owner_name(owner):
    """An attested owner as the label shows it: the email the endpoint
    annotated, else its member id."""
    if isinstance(owner, dict):
        email, mid = owner.get("email"), owner.get("id")
        return email if isinstance(email, str) and email else mid if isinstance(mid, str) else ""
    return owner if isinstance(owner, str) else ""


# ------------------------------------------------------------------ addressing

TAG_RE = re.compile(r'@(?:"([^"\n]+)"|([\w.-]+(?:/[\w.-]+)?))(?:#([0-9a-f]{1,8}))?')
SPACE_RE = re.compile(r"\s*")


def leading_tags(text):
    """The tags that open a message — `@name`, `@"name with spaces"`,
    `@name#short`, `@short`, each optionally `project/`-qualified — trailing
    `,:;` allowed. Only this leading run addresses anyone: an @ later in the
    text (a quoted alias, an error message naming a seat) is just text.
    Returns [{"raw", "project", "name", "short"}]."""
    tags, pos = [], 0
    while True:
        pos = SPACE_RE.match(text, pos).end()
        m = TAG_RE.match(text, pos)
        if not m:
            return tags
        end = m.end()
        while end < len(text) and text[end] in ",:;":
            end += 1
        if end < len(text) and not text[end].isspace():
            return tags
        project, _, name = (m.group(1) or m.group(2)).rpartition("/")
        tags.append({"raw": m.group(0), "project": project, "name": name, "short": m.group(3) or ""})
        pos = end


def project_seats(project):
    """The seats whose cwd resolves to the project."""
    return [s for s in seats() if (p := seat_project(s)) and p.id == project.id]


def is_all(tag):
    return tag["name"] == "all" and not tag["project"] and not tag["short"]


def alias_reach(m, name, short=""):
    """How `name` reaches member `m` by alias, the one rule every name lookup
    shares (§4 of the charge names design): "alias" when it is the member's
    alias, "former" when it is an alias the member held before
    (former_aliases), "" when neither. With `short` (`name#short`), only a
    member the short of whose session, or of one it continues, starts so.
    A retired row (a seat find_target still finds by its own name) answers
    to no alias it held before."""
    if short and not any(s and s[:8].startswith(short) for s in (m.session,) + m.former):
        return ""
    if name == m.alias:
        return "alias"
    return "former" if m.state != "retired" and any(a == name for a, _ in m.former_aliases) else ""


def current_first(hits, name):
    """A lookup pass's (project, member) pairs from its (project, member, how)
    `hits`: those a current alias or id reached, when any did; else those that
    held `name` before, narrowed to its latest holder — the latest ts of a
    joined or renamed carrying it — every holder tied at that ts kept, for the
    caller to refuse as ambiguous."""
    current = [(p, m) for p, m, how in hits if how != "former"]
    if current or not hits:
        return current

    def held_at(m):
        return max(ts for a, ts in m.former_aliases if a == name)

    latest = max(held_at(m) for _, m, _ in hits)
    return [(p, m) for p, m, _ in hits if held_at(m) == latest]


def note_former(name, short, p, m, home):
    """Tell the caller, on stderr, that `name` reached member `m` (of project
    `p`) by an alias it held before, naming it as it goes now — behind its
    project when that is not the caller's `home`. Nothing when the name is its
    alias or id."""
    if alias_reach(m, name, short) == "former":
        qualify = home is None or p.id != home.id
        # candidate_labels puts the `at` before a project; a bare label takes it here.
        note("@%s is now %s%s" % (name, "" if qualify else "@", candidate_labels([(p, m)], qualify, "@")))


def match_members(name, short, projects, alias=True, ids=True):
    """The (project, member) pairs a tag's name answers to among the projects'
    members: their alias (with `short`, an alias whose short starts so), their
    short (`@short`), or their session id — a session they continue (`former`)
    answering as theirs does; and, when none of those answers, an alias a
    member held before (current_first). With alias=False a bare name is
    matched against shorts and ids alone, with ids=False against aliases
    alone. A retired member answers to nothing."""
    hits = []
    for p in projects:
        for m in members(p):
            if m.state == "retired":
                continue
            if short:
                how = alias_reach(m, name, short)
            elif ids and any(name in (s, s[:8]) for s in (m.session,) + m.former):
                how = "id"
            else:
                how = alias_reach(m, name) if alias else ""
            if how:
                hits.append((p, m, how))
    return current_first(hits, name)


def one_per_session(found, key=lambda m: m.session):
    """`found` with each session (each `key`) once. A session two projects'
    logs hold as a member at once — a move's dual membership of one tick
    (§1a of the org directory design) — answers in the one it joined last."""
    best = {}
    for p, m in found:
        k = key(m)
        ts = str(((view_of(p).info.get(m.session) or {}).get("joined") or {}).get("ts") or "")
        if k not in best or ts > best[k][0]:
            best[k] = (ts, p, m)
    return [(p, m) for _, p, m in best.values()]


def candidate_labels(found, qualify, at=""):
    """The candidates a name was ambiguous between, each as the name that tells
    it apart: alias#short, behind its project when they span projects
    (`<at><project>/alias#short`, `at` "@" for a tag; the project as a tag
    reaches it, tag_project)."""
    return ", ".join(sorted(("%s%s/" % (at, tag_project(p)) if qualify else "") + "%s#%s" % (m.alias, m.short)
                            for p, m in found))


def unreachable_hint(raw, name, short, projects, at="@"):
    """The refusal for a tag no member answers to that still names someone: a
    retired or vacant seat, a seat-less session whose membership ended (it is
    never resumed, so an untagged line is how to leave it a note), or one that
    moved to another project — where its short (`<at>short`) still reaches it."""
    for p in projects:
        for s in project_seats(p):
            if s["alias"] == name and s["current"][:8].startswith(short):
                if s["status"] == "retired":
                    return "%s is retired; re-fill it to reach it" % raw
                if not s["current"]:
                    return "%s is vacant — fill it to reach it" % raw
        for alias, sh, reason, moved_to in retired_sessions(p):
            if alias == name and sh.startswith(short):
                if reason == "ended":
                    return ("%s: %s's session ended; say it untagged to leave a note — it reads the chat when "
                            "it is resumed" % (raw, alias))
                if reason == "moved" and moved_to:
                    return "%s moved to %s; %s%s reaches it" % (raw, project_label(moved_to), at, sh)
                return "%s is retired; it re-joins when its session runs again" % raw
    return ""


BARE_NAME = "a bare name reaches only your project; %s reaches anyone"


def no_member(raw, name, short, scope, elsewhere=(), at="@"):
    """Exit 4 for a name no member of `scope` answers to: what the scope still
    knows of it (unreachable_hint); else the members of other projects with
    that alias (`elsewhere`), each as the name that reaches it; else plainly
    none."""
    hint = unreachable_hint(raw, name, short, scope, at)
    if hint:
        die(hint, EXIT_UNKNOWN)
    names = sorted({p.name for p in scope})
    where = "project %s" % names[0] if len(names) == 1 else "any project known here"
    if elsewhere:
        die("no member %s in %s; elsewhere: %s\n%s" % (raw, where, candidate_labels(elsewhere, True, at),
                                                        BARE_NAME % ("@short" if at else "a session's short")),
            EXIT_UNKNOWN)
    die("no member %s in %s" % (raw, where), EXIT_UNKNOWN)


def one_member(raw, found, qualify):
    """The one (project, member) of `found`; exit 4 naming each when several."""
    if len(found) > 1:
        die("ambiguous %s matches: %s" % (raw, candidate_labels(found, qualify, "@")), EXIT_UNKNOWN)
    return found[0]


def resolve_tag(project, t):
    """The (project, member) one tag reaches (_resolve_tag), the sender told
    when it reached it by an alias the member held before (note_former)."""
    p, m = _resolve_tag(project, t)
    note_former(t["name"], t["short"], p, m, project)
    return p, m


def _resolve_tag(project, t):
    """The (project, member) one tag reaches, `project` the sender's (§5 of
    the org directory design), or exit 4 saying why not. In each scope below
    an alias a member held before answers only when no current alias or id
    does (match_members):

    - `@<p>/<alias>`: in the projects `p` names (project_tiers), the next one
      read only when the one before has no such member — so a project named
      after a machine is read before that machine's project;
    - `@alias#short`: in every project known here (org_scope);
    - `@alias`: the sender's project; a name no alias there answers to is
      read as a short or a session id, across every project known here. A
      bare name never reaches another project's alias: the board spawns the
      same seat names in every repository, so `@executor` would otherwise
      wake another repository's executor. The refusal names those members.
    - From no project (a machine not enrolled), every project known here."""
    raw, name, short = t["raw"], t["name"], t["short"]
    if t["project"]:
        tiers = project_tiers(t["project"])
        if not tiers:
            die("no project '%s' is known on this machine" % t["project"], EXIT_UNKNOWN)
        # A project the org's directory retires is closed, as for @short: a
        # message written into it would never leave this machine.
        tiers = [p for p in tiers if not org_retired(p.id)]
        if not tiers:
            die("project '%s' is retired in the org's directory" % t["project"], EXIT_UNKNOWN)
        for p in tiers:
            found = match_members(name, short, [p])
            if found:
                return one_member(raw, found, False)
        no_member(raw, name, short, tiers)
    if project is None:
        scope = org_scope()
        found = one_per_session(match_members(name, short, scope))
        return one_member(raw, found, True) if found else no_member(raw, name, short, scope)
    if short:
        found = one_per_session(match_members(name, short, org_scope()))
        return one_member(raw, found, True) if found else no_member(raw, name, short, org_scope())
    found = match_members(name, "", [project], ids=False)
    if found:
        return one_member(raw, found, False)
    found = one_per_session(match_members(name, "", org_scope(), alias=False))
    if found:
        return one_member(raw, found, True)
    no_member(raw, name, short, [project],
              [(p, m) for p, m in match_members(name, "", org_scope(), ids=False) if p.id != project.id])


def resolve_tags(project, text):
    """Resolve a message's leading tags at submission (resolve_tag). Returns
    (destination, recipients [{session, alias}], text, wake). The destination
    is the sender's project, or the one the tags reach; tags reaching two
    projects are refused, as are a tag matching no member and one matching
    several (named as alias#short). `@all` is the members of the sender's
    project live at submission."""
    tags = leading_tags(text)
    if not tags:
        return project, [], text, False
    if any(is_all(t) for t in tags):
        if len(tags) != 1:
            die("@all stands alone")
        if project is None:
            die("@all needs a project: say it in a project's directory, or with --in <project>")
        if project_kind(project) == "machine":
            # Its members share nothing but a machine.
            die("a machine project is not a team: tag who you mean")
        live = [m for m in members(project) if m.state in FILLED]
        return project, [{"session": m.session, "alias": m.alias} for m in live], text, True

    destinations, recipients = {}, []
    for t in tags:
        p, m = resolve_tag(project, t)
        destinations[p.id] = p
        if all(r["session"] != m.session for r in recipients):
            recipients.append({"session": m.session, "alias": m.alias})
    if len(destinations) > 1:
        die("one message, one project: the tags name %s" % ", ".join(sorted(p.name for p in destinations.values())))
    return next(iter(destinations.values())), recipients, text, False


def caller_seat():
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        return None
    all_seats = seats()
    for s in all_seats:
        if s["current"] == sid:
            return s
    row = agent_row(session_id=sid)
    if row:
        return next((s for s in all_seats if not s["current"] and s["short"] and s["short"] == row.get("id")), None)
    return None


def caller_scope():
    """The project a bare name resolves in: the calling seat's, else the
    working directory's; None from a directory that is no project."""
    return caller_project(caller_seat() if os.environ.get("CLAUDE_CODE_SESSION_ID") else None)


class ResumeRefused(Exception):
    def __init__(self, message, code=EXIT_UNKNOWN):
        super().__init__(message)
        self.message = message
        self.code = code


def push_member(member, text, tagged, session=None, event=None, project=None, words=None):
    """Push one frame to a member: to the live session (push_live: an
    owner's event through its bridge, keyed by `event`, the log event the
    frame carries, and `project`, the id of the project whose log holds it,
    or its supervisor; a peer's, and whatever those do not take, through its
    inbox socket); for a seat, a resume when it is stopped and the message is
    addressed to it (`tagged`), the frame then its resumed prompt whoever sent
    it. A session sminos did not spawn is never
    resumed: it is the human's to reopen, and reads the chat when it is back.
    Given `session`, a seat that now holds another session is not this
    message's recipient: delivery goes by session id, so a replacement cannot
    misroute it. `words`: the endpoint's verdict on a person's words, which
    push_live takes in place of the writer on a cut-over machine."""
    session = session or member.session
    verdict = {} if words is None else {"words": words}   # a machine not cut over calls as it always has
    if member.seat is None:
        peer = peer_for_session(session)
        if not peer:
            return "recorded"
        try:
            control_module().push_live(peer, session, text, event, project, **verdict)
            return "sent"
        except SendFailed as e:
            return "sent?" if e.phase == "after" else "failed:%s" % e
    seat_id = member.seat["seat_id"]

    def unreachable(s):
        # Decided on the record as it is now, never on the fan-out's snapshot:
        # an earlier member's resume can outlast a later member's retirement.
        if s is None or s["status"] == "retired":
            if s is not None and tagged:
                warn("%s is retired; re-fill it to reach it" % s["alias"])
            return True
        return bool(session) and s["current"] != session

    fresh = reload_seat(seat_id)
    if unreachable(fresh):
        return "recorded"
    if fresh["engine"] == "codex":
        return "failed:legacy codex record"
    if not fresh["current"]:
        return "recorded"
    peer = peer_for_session(fresh["current"])
    if peer:
        try:
            control_module().push_live(peer, fresh["current"], text, event, project, **verdict)
            return "sent"
        except SendFailed as e:
            return "sent?" if e.phase == "after" else "failed:%s" % e
    if not tagged:
        return "recorded"
    st = seat_state(fresh, None)  # the probe above found no live peer
    if st == "gone" and transcript_now(fresh["current"]):
        st = "stopped"   # its transcript is newer than the index
    if st == "gone":
        # A resume of a session with no transcript here cannot work: say so,
        # as for a retired member, rather than attempt it.
        warn("%s is gone — no transcript for its session on this machine; fill it to reach it" % fresh["alias"])
        return "recorded"
    if st != "stopped":
        return "recorded"
    locks = []
    try:
        # The lifecycle lock spans the recheck and the resume, so a concurrent
        # retire either finishes first (and is seen) or waits for the resume.
        locks = lock_seat(fresh, refusal=ResumeRefused)
        fresh = reload_seat(seat_id)
        if unreachable(fresh) or not fresh["current"]:
            return "recorded"
        return resume_session(fresh, text, False, locks, quiet=True)
    except ResumeRefused as e:
        return "failed:%s" % e.message
    finally:
        unlock(locks)


# ------------------------------------------------------------------ say / chat


def record_copy(home, delivered):
    """A message a session spoke into other projects, copied into the
    session's own project's log `home` (§6 of the org directory design;
    §5a for a broadcast). `delivered`: (project, the event its log delivers
    it by) for each project it went to. The copy is the first event under
    the same writer, with its ts, `from`, text and the rest but
    `from_project`; `to` every recipient with its project; and `copy`
    naming the delivering event as `<project id>:<writer>:<seq>`, a list of
    those when several projects' events deliver it — no one is owed it
    (addressed_to). Written after the delivering events; one that cannot be
    written is a warning, since the message was delivered."""
    first = delivered[0][1]
    fields = {k: v for k, v in first.items() if k not in ("writer", "seq", "kind", "from_project")}
    fields["to"] = [dict(r, project=dest.id) for dest, e in delivered for r in e["to"] if isinstance(r, dict)]
    refs = ["%s:%s:%d" % (dest.id, e["writer"], e["seq"]) for dest, e in delivered]
    fields["copy"] = refs[0] if len(refs) == 1 else refs
    try:
        c = log_append(home, first["writer"], first["kind"], **fields)
    except OSError as err:
        warn("delivered, but its copy could not be recorded in %s: %s" % (home.name, err))
        return None
    print("copy %s in %s" % (event_ref(c), home.name))
    return c


def deliver_say(dest, e, writer, recipients, name=lambda r: r["alias"]):
    """Deliver a recorded say (`e`, in `dest`'s log) to its recipients, a
    line each, the recipient as `name` gives it: one of this machine's now
    (deliver_next); another machine's by that machine's daemon, which this
    machine's is asked to push it to at once. On a cut-over machine a
    person's words this pass leaves owed for the endpoint's verdict (O12 M6)
    are said so, and the daemon nudged: its uplink asks."""
    by_session = {m.session: m for m in members(dest)}
    for r in recipients:
        member = by_session.get(r["session"])
        if member is not None and not member.local:
            # Owed to it in the log; its own machine's daemon delivers it,
            # once this machine's daemon has pushed it: ask for that now.
            print("%s: recorded (on %s)" % (name(r), member.machine))
            nudge_daemon()
            continue
        result = deliver_next(dest, member) if member else {"outcomes": []}
        mine = [o for ev, o in result["outcomes"] if ev["writer"] == writer and ev["seq"] == e["seq"]]
        if mine:
            print("%s: %s" % (name(r), mine[0]))
            continue
        if any(ev["writer"] == writer for ev in result.get("gated", ())):
            print("%s: %s" % (name(r), WORDS_RECORDED))
            nudge_daemon()
            continue
        held = next((o for ev, o in result["outcomes"] if ev["writer"] == writer), "")
        print("%s: pending%s" % (name(r), " behind an earlier undelivered message (%s)" % held if held else ""))


# A broadcast's scope (§5a of the org directory design): list's filters, put
# to sending. `sminos list` with the same flags shows the sessions it reaches.


def selector_given(a):
    return bool(a.org or a.projects or a.machine or a.state or a.here)


def say_scope(a):
    """The `scope` a broadcast's events carry, from say's selector: each key
    only when its flag is given — `projects` the ids --project names,
    `machines` --machine's prefixes as given, `here` this machine's name,
    `states` --state's words. {} is the whole org (--org alone). A named
    project the org's directory retires is refused: a message into it would
    never leave this machine."""
    scope = {}
    if a.projects:
        named = [find_project(q) for q in a.projects]
        for p in named:
            if org_retired(p.id):
                die("project '%s' is retired in the org's directory" % p.name, EXIT_UNKNOWN)
        scope["projects"] = list(dict.fromkeys(p.id for p in named))
    if a.machine:
        scope["machines"] = list(a.machine)
    if a.here:
        scope["here"] = host_name()
    if a.state:
        scope["states"] = list(a.state)
    return scope


def scope_label(scope):
    """How chat, a frame and the TUI name a broadcast's scope: `@org` for the
    whole org, else `@all` narrowed by ` in <projects>` and ` on <machines>`;
    then ` (<states>)` when it reached only those."""
    def words(key):
        v = scope.get(key)
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []

    projects = [project_label(p) for p in words("projects")]
    here = scope.get("here")
    machines = words("machines") + ([here] if isinstance(here, str) and here else [])
    label = "@all" if projects or machines else "@org"
    if projects:
        label += " in " + ",".join(projects)
    if machines:
        label += " on " + ",".join(machines)
    if words("states"):
        label += " (%s)" % ",".join(words("states"))
    return label


def scope_members(a, sender):
    """[(project, [member])]: the rows `list` shows with say's selector
    (list_scope, row_matches) that are live members, `sender` left out, each
    session once (where it joined last), grouped by project. A project the
    org's directory retires is passed over."""
    projects, _, _ = list_scope(a)
    found = one_per_session([(p, m) for p in projects if not org_retired(p.id) for m in members(p)
                             if m.session and m.session != sender and m.state in FILLED and row_matches(m, p, a, [])])
    groups = {}
    for p, m in found:
        groups.setdefault(p.id, (p, []))[1].append(m)
    return list(groups.values())


def say_scoped(a, home, sender, writer, kind, sid):
    """A say with a selector: delivered to every live session of its scope
    (scope_members) as @all is, waking each, no stopped one resumed. One
    event in each project with a recipient — `to` those recipients, `scope`
    the selector (say_scope), `wake` — and, from a session whose own project
    `home` has none of them, a copy there (record_copy). The operator (no
    session) writes no copy, as for a cross-project tag."""
    if a.state and not set(a.state) & set(FILLED):
        die("a broadcast reaches live sessions only (%s): --state %s names none" % (", ".join(FILLED), ",".join(a.state)))
    scope = say_scope(a)
    label = scope_label(scope)
    groups = scope_members(a, sid)
    count = sum(len(ms) for _, ms in groups)
    if not count:
        die("no live session in %s but you: nothing sent (sminos list with the same flags shows who is there)"
            % label, EXIT_UNKNOWN)
    print("%s: %d session%s in %s" % (label, count, "" if count == 1 else "s", ", ".join(p.name for p, _ in groups)))
    delivered, lost = [], False
    for dest, ms in groups:
        fields = {"from": sender, "to": [{"session": m.session, "alias": m.alias} for m in ms], "text": a.text,
                  "wake": True, "scope": scope}
        if home is not None and home.id != dest.id:
            fields["from_project"] = home.id  # the sender's own project, where a reply finds it
        try:
            e = log_append(dest, writer, kind, **fields)
        except OSError as err:
            warn("not recorded in %s, so not sent to its %d: %s" % (dest.name, len(ms), err))
            lost = True
            continue
        if e["seq"] is None:
            print(waits_line(dest, writer))
            continue
        delivered.append((dest, e))
        print("recorded %s in %s" % (event_ref(e), dest.name))
    if home is not None and delivered and all(p.id != home.id for p, _ in groups):
        record_copy(home, delivered)
    for dest, e in delivered:
        deliver_say(dest, e, writer, e["to"], lambda r: "%s#%s" % (r["alias"], r["session"][:8]))
    if lost:
        sys.exit(1)


def cmd_say(a):
    """Record a message in a project's log, and deliver it to whom it tags;
    with a selector, to every live session of its scope (say_scoped)."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    scoped = selector_given(a)
    if scoped and leading_tags(a.text):
        die("a selector picks the recipients itself: drop the opening @tags, or the selector — tags name "
            "sessions, a selector names a scope, and one message takes one")
    if sid:
        if a.in_:
            die("--in is for an operator, not a session — tag @<project>/<name> to speak into another project")
        caller = caller_seat()
        home = caller_project(caller)
        sender = caller["alias"] if caller else default_from("")
        writer, kind = writer_id(sid), "say"
    else:
        if scoped and a.in_:
            die("--in names the project a say is spoken in; a selector names its own (--project)")
        home = find_project(a.in_) if a.in_ else None if scoped else caller_project()
        sender, writer, kind = "human", writer_id(), "human"
    if scoped:
        say_scoped(a, home if sid else None, sender, writer, kind, sid)
        return
    dest, recipients, _text, wake = resolve_tags(home, a.text)
    if dest is None:
        die("say outside a project: run it in a project's directory, or name one with --in <project>")
    if sid:
        if wake:
            recipients = [r for r in recipients if r["session"] != sid]
        elif any(r["session"] == sid for r in recipients):
            die("you cannot tag yourself")
    fields = {"from": sender, "to": recipients if (recipients or wake) else "*", "text": a.text}
    if wake:
        fields["wake"] = True
    if sid and home is not None and home.id != dest.id:
        fields["from_project"] = home.id  # the sender's own project, where a reply finds it
    try:
        e = log_append(dest, writer, kind, **fields)
    except OSError as err:
        die("say could not be recorded: %s" % err, 1)
    if e["seq"] is None:
        print(waits_line(dest, writer))
        return
    print("recorded %s in %s" % (event_ref(e), dest.name))
    if "from_project" in fields:
        record_copy(home, [(dest, e)])
    deliver_say(dest, e, writer, recipients)


def target_label(e):
    to = e.get("to")
    if to == "*":
        return "*"
    if e.get("wake"):
        return scope_label(e["scope"]) if isinstance(e.get("scope"), dict) else "@all"
    if isinstance(to, list):
        return " ".join("@" + str(r.get("alias") or "?") for r in to if isinstance(r, dict)) or "-"
    return str(to or "-")


def moved_line(e, events):
    """A `moved` retirement as chat prints it: `<ts> <ref> <alias> retired
    (moved to <project>)` — a member that left for another project, which a
    reader of the conversation it left should see."""
    alias = next((str(x.get("alias") or "") for x in reversed(events)
                  if x["kind"] in ("joined", "renamed") and x.get("session") == e.get("session") and x.get("alias")),
                 "") or str(e.get("session") or "")[:8]
    pid = str(e.get("project") or "")
    to = project_label(pid) if pid else "no project"
    return "%s %s %s retired (moved to %s)" % (e["ts"][11:19], event_ref(e), alias, to)


def is_moved(e):
    return e["kind"] == "retired" and e.get("reason") == "moved"


def chat_line(e, label=""):
    """`<ts> <ref> <from>[<label>] → <target>  <text>`; a copy (record_copy)
    marked `→ <project>, …` after its target, the projects whose logs
    delivered it. `label` follows the sender (sender_labels)."""
    lines = str(e.get("text") or "").split("\n")
    target = target_label(e)
    copy = e.get("copy")
    refs = [copy] if isinstance(copy, str) else [r for r in copy if isinstance(r, str)] if isinstance(copy, list) else []
    if refs:
        target += " → %s" % ", ".join(project_label(r.partition(":")[0]) for r in refs)
    out = ["%s %s %s%s → %s  %s" % (e["ts"][11:19], event_ref(e), e.get("from", ""), label, target, lines[0])]
    out += ["    " + line for line in lines[1:]]
    return "\n".join(out)


TS_RE = re.compile(r"^(\d{4}-\d\d-\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,3}))?)?)?Z?$")


def normalize_ts(ts):
    """A user-given time as the log's ts shape, so string order is time order."""
    m = TS_RE.match(ts.strip())
    if not m:
        die("--since takes an ISO-8601 UTC time such as 2026-10-13T08:00:00Z: %s" % ts)
    day, hh, mm, ss, ms = m.groups()
    return "%sT%s:%s:%s.%sZ" % (day, hh or "00", mm or "00", ss or "00", (ms or "0").ljust(3, "0"))


def cmd_chat(a):
    """Read a project's chat. With no flags: what is above the reader's
    cursor (at most 30, then +N earlier), advancing it; -n tails and --since
    reads from a time, neither moving it. --host reads what the members sent
    their human instead (chat_host)."""
    if a.n is not None and a.n < 1:
        die("chat -n must be positive")
    if a.host and a.kind:
        die("chat --host reads the host kinds (%s); it takes no --kind" % ", ".join(HOST_KINDS))
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    project = find_project(a.project) if a.project else caller_project(caller_seat() if sid else None)
    if project is None:
        die("chat outside a project: run it in a project's directory, or name one: sminos chat <project>")
    reconcile(project)
    if a.host:
        chat_host(project, a)
        return
    kinds = tuple(a.kind) if a.kind else CHAT_KINDS
    events = log_read(project)
    # A member that moved to another project is part of the conversation it left.
    pool = [e for e in events if e["kind"] in kinds or (not a.kind and is_moved(e))]
    earlier = 0
    if a.since is not None:
        since = normalize_ts(a.since)
        window, head = [e for e in pool if e["ts"] >= since], "since %s" % a.since
    elif a.n is not None:
        window, head = pool[-a.n:], "last %d of %d" % (min(a.n, len(pool)), len(pool))
    else:
        cursor = cursor_load(project, sid)
        mine = writer_id(sid or None)
        above = [e for e in pool if e["writer"] != mine and e["seq"] > cursor.get(e["writer"], 0)]
        window = above[-30:]
        earlier = len(above) - len(window)
        head = "%d new" % len(above)
        advanced = dict(cursor)
        for e in events:
            advanced[e["writer"]] = max(advanced.get(e["writer"], 0), e["seq"])
        if advanced != cursor:
            cursor_save(project, sid, advanced)
    if a.json:
        for e in window:
            print(json.dumps(e, ensure_ascii=False))
        if earlier:
            sys.stderr.write("+%d earlier — sminos chat %s -n %d\n" % (earlier, project.name, len(window) + earlier))
        return
    print("chat %s · %s" % (project.name, head))
    if earlier:
        print("+%d earlier — sminos chat %s -n %d" % (earlier, project.name, len(window) + earlier))
    label = sender_labels(project)
    for e in window:
        print(moved_line(e, events) if is_moved(e) else chat_line(e, label(e)))
    if not window:
        print("(no new messages)" if a.since is None and a.n is None else "(no messages)")


# ------------------------------------------------------------ messages to the host
#
# What a session sends its human — a <message> mark, an async ask, the answer
# the human gave it — reaches the project's log through the Stop and
# SessionStart hook (hooks/smns-record.sh → `sminos record`), read from the
# session's transcript past its export position (§4). Every event carries a
# `src`, and the batch drops a (kind, src) already present, so replaying an
# export appends nothing.
#
# On a machine cut over to its endpoint (RL10), a hub project's host events
# stay on the machine (O12 M8): they go to its host store, HOST_STORE beside
# log/, never to the log the hub carries — a writer's seqs are contiguous and
# a withheld event a permanent gap, so they cannot sit in a writer's log file
# and be left out of its upload. The store has the log's event shape and
# writer names, its own seqs, and the same (kind, src) rule; the uplink sends
# each event up RL10 itself (sminos_uplink's host pass), and a subscription
# of the session carries them (sminos_plane). Events the log took before the
# cutover stay there; `chat --host` reads both.

HOST_KINDS = ("message", "question", "answered")
HOST_STORE = "host"   # projects/<id>/host/<writer>.jsonl: a cut-over machine's to-human events of a hub project
# The message tools a transcript may hold: the to-human plugin's
# (to-human/hooks/mods/message.tsx), and MAWS's own, which a MAWS launch
# registers in its place. A session sends its human a message before another
# tool call through one (a span written there comes back from the API as a
# progress note's paraphrase, without its tags); a call whose result is in
# and is no error is a message at the call's place, src its call id. sminos
# declares no dependency on either, so it knows them by name.
MESSAGE_TOOLS = ("mcp__to-human__message", "mcp__maws__message")
# The ask tool's names a transcript may hold (hooks/mods/ask.tsx ASK_TOOLS):
# the sminos plugin's, where it moves, and the doperpowers plugin's, where it
# was first. Sessions are resumed and copied across the move: read either.
ASK_TOOLS = ("mcp__sminos__AskUserQuestion", "mcp__doperpowers__AskUserQuestion")
# What the tool returns for an async call it accepted (hooks/mods/ask.tsx).
ASYNC_RESULT = ("Your questions are waiting for the human; this call does not wait for them. Their answer will "
                "reach you in a later message that quotes each question. Go on with work that does not depend on it.")
# A delivery of the human's answer, in whichever row the engine stored it.
DELIVERY_RE = re.compile(r"The human responded to your async AskUserQuestion \(call ([^)\s]+)\): ")
# The engine's framing before a prompt the ask's plugin submitted, under
# either plugin's name (ask.tsx PLUGIN_PROMPTS).
PLUGIN_PROMPTS = ("The sminos plugin sent a message:\n", "The doperpowers plugin sent a message:\n")
# The engine's framing after the text of a prompt a plugin submitted.
PLUGIN_FRAMING = "\n\nThis is how Claude Code surfaces a prompt a plugin submits"
# MAWS's ask tool, which a session under MAWS asks through instead (MAWS owns
# the shape, in its src/shared/maws/ask.ts; tests/maws-ask-*.jsonl are
# transcripts of it): called with `blocking` false, it answers at once with
# {"status": "asked", "askId": ...} as JSON, the askId being the call id, or
# MAWS's request id when the engine named no call, and the answers come later
# as the human's prompt, a steer, which opens with `[MAWS ask <askId>] ` and
# ends with the answered result in a json fence.
MAWS_ASK_TOOL = "mcp__maws__ask"
MAWS_STEER_RE = re.compile(r"\[MAWS ask ([^\]\s]+)\] ")
MAWS_STEER_HEADER = "The user answered the questions you asked:"
MAWS_FENCE_OPEN, MAWS_FENCE_CLOSE = "\n```json\n", "\n```"


def extract_marks(text):
    """[{"kind": "message", "text"}]: the marked spans of one assistant text,
    read as the to-human mod reads them (sminos_marks): tags in code are
    literal, nested marks are runs of their own, an unclosed mark runs to the
    end, and every alias is a message."""
    return [{"kind": s["kind"], "text": s["text"]} for s in sminos_marks.parse(text)["spans"] if s["text"]]


def _blocks(record, kind=None):
    """A transcript record's content blocks of one type, or all of them in
    order with none; a string content is one text block."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if kind in ("text", None) else []
    return [b for b in content if isinstance(b, dict) and kind in (b.get("type"), None)] if isinstance(content, list) else []


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


def _delivery_texts(record):
    """The texts of a record that can deliver an answer, as ask.tsx reads
    them: a context attachment's entries, and a prompt the plugin submitted.
    Never the model's own rows, a tool's output, or the human quoting one."""
    if record.get("type") == "attachment":
        att = record.get("attachment")
        if isinstance(att, dict) and att.get("type") == "hook_additional_context":
            content = att.get("content")
            return [t for t in (content if isinstance(content, list) else [content]) if isinstance(t, str)]
        return []
    if record.get("type") != "user":
        return []
    return [t for t in (b.get("text") for b in _blocks(record, "text"))
            if isinstance(t, str) and t.startswith(PLUGIN_PROMPTS)]


def _deliveries(text):
    """(call id, answer) for each delivery head in a text: the answer is the
    engine's result text, up to the next head, without the engine's framing."""
    heads = list(DELIVERY_RE.finditer(text))
    out = []
    for i, head in enumerate(heads):
        answer = text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        cut = answer.find(PLUGIN_FRAMING)
        out.append((head.group(1), (answer[:cut] if cut >= 0 else answer).rstrip()))
    return out


def _is_human(record):
    """Whether a row or attachment is the human's: its origin says so, or it names none."""
    origin = record.get("origin")
    return not isinstance(origin, dict) or origin.get("kind", "human") == "human"


def _maws_steer_texts(record):
    """The texts of a record that can be a MAWS steer: the human's prompt, as
    a user row, or as the queued_command attachment the engine writes for a
    prompt it took into a running turn. Never a text of another origin (a
    peer's, a plugin's), which could only quote a steer."""
    if record.get("type") == "attachment":
        att = record.get("attachment")
        if not (isinstance(att, dict) and att.get("type") == "queued_command" and att.get("commandMode") == "prompt" and _is_human(att)):
            return []
        prompt = att.get("prompt")
        return [prompt if isinstance(prompt, str) else _result_text(prompt)]
    return [b["text"] for b in _blocks(record, "text") if isinstance(b.get("text"), str)] \
        if record.get("type") == "user" and _is_human(record) else []


def _maws_answer(text):
    """(askId, answer) of a MAWS steer, read as MAWS's parseAskSteer reads
    one: its tag names the ask, and its last json fence, which ends the text,
    holds the answered result of the same ask. The answer is the steer's own
    lines between the two, one per question, without MAWS's header line. None
    for any other text."""
    tag = MAWS_STEER_RE.match(text)
    if tag is None or not text.endswith(MAWS_FENCE_CLOSE):
        return None
    end = len(text) - len(MAWS_FENCE_CLOSE)
    start = text.rfind(MAWS_FENCE_OPEN, tag.end() - 1, end)
    try:
        result = json.loads(text[start + len(MAWS_FENCE_OPEN):end]) if start >= 0 else None
    except ValueError:
        return None
    if not isinstance(result, dict) or result.get("status") != "answered" or result.get("askId") != tag.group(1):
        return None
    body = text[tag.end():start]
    return tag.group(1), (body[len(MAWS_STEER_HEADER):] if body.startswith(MAWS_STEER_HEADER) else body).strip("\n")


def _maws_asked(text):
    """The askId a MAWS ask's result names when it is its acceptance as an
    async ask (the call id, or MAWS's request id when the engine named no
    call), else None."""
    try:
        result = json.loads(text)
    except ValueError:
        return None
    ask = result.get("askId") if isinstance(result, dict) and result.get("status") == "asked" else None
    return ask if isinstance(ask, str) and ask else None


def _ask_events(records):
    """(record index, event) for the async asks the records hold, in record
    order: a `question` for each tool_use of an ask tool called async (the
    plugin's with `async` not false, MAWS's with `blocking` false) whose paired
    tool_result is that tool's acceptance (for the plugin's, the result is
    what says: a call written before `async` defaulted to true has no key
    whether it blocked or not), and an `answered` for each delivery
    (the plugin's) or steer (MAWS's) of an answer. Each src is the call id;
    for MAWS's, the askId its acceptance and steer name, which is the call id
    unless the engine named no call to MAWS (then MAWS's request id). A
    blocking ask — the plugin's with `async` false, MAWS's by default or in a
    subagent, or the native AskUserQuestion — is no event: the session waits,
    and the human goes to it."""
    calls, results, out = [], {}, []
    for i, r in enumerate(records):
        for b in _blocks(r, "tool_use"):
            inp, name = b.get("input"), b.get("name")
            if isinstance(inp, dict) and b.get("id") and (
                    (name in ASK_TOOLS and inp.get("async") is not False) or (name == MAWS_ASK_TOOL and inp.get("blocking") is False)):
                calls.append((i, str(b["id"]), name, inp))
        for b in _blocks(r, "tool_result"):
            results[str(b.get("tool_use_id") or "")] = b
        for text in _delivery_texts(r):
            out += [(i, {"kind": "answered", "src": call, "text": answer}) for call, answer in _deliveries(text)]
        for call, answer in filter(None, map(_maws_answer, _maws_steer_texts(r))):
            out.append((i, {"kind": "answered", "src": call, "text": answer}))
    for i, call, name, inp in calls:
        res = results.get(call)
        text = _result_text(res.get("content")) if res is not None and res.get("is_error") is not True else None
        if text is None:
            continue
        src = _maws_asked(text) if name == MAWS_ASK_TOOL else (call if text == ASYNC_RESULT else None)
        if src is None:
            continue
        questions = [q for q in inp.get("questions") or [] if isinstance(q, dict)]
        out.append((i, {"kind": "question", "text": [str(q.get("question") or "") for q in questions],
                        "choices": [str(o.get("label") or "") for q in questions
                                    for o in q.get("options") or [] if isinstance(o, dict)], "src": src}))
    out.sort(key=lambda x: x[0])
    return out


def extract_asks(records):
    """The async asks and their answers the transcript records hold, in order:
    {"kind": "question", "src": the ask's id, "text": [questions], "choices": [labels]}
    and {"kind": "answered", "src": the ask's id, "text": the engine's result text},
    the ask's id being its call id, or MAWS's askId."""
    return [e for _, e in _ask_events(records)]


def _sent_text(block, results):
    """The text a message tool's call sent: its input's text, once the call's
    result is among `results` and is no error (a refused, failed or
    interrupted call sent nothing). None for any other block, and for a call
    with no text to send."""
    if block.get("type") != "tool_use" or block.get("name") not in MESSAGE_TOOLS or not block.get("id"):
        return None
    inp, res = block.get("input"), results.get(str(block["id"]))
    text = inp.get("text") if isinstance(inp, dict) else None
    if not isinstance(text, str) or not text.strip() or res is None or res.get("is_error") is True:
        return None
    return text


def host_events(records, alias):
    """The events a run of transcript records holds for the host, in record
    order, ready for log_append_batch: each marked span of an assistant record
    as a `message` (src `<record uuid>#<span index>`), each accepted call of a
    message tool as a `message` at its place among the spans (src its call
    id), each accepted async ask as a `question`, each delivery of an answer as
    `answered` (src the call id, or MAWS's askId)."""
    results = {str(b.get("tool_use_id") or ""): b for r in records for b in _blocks(r, "tool_result")}
    out = []
    for i, r in enumerate(records):
        if r.get("type") != "assistant" or not isinstance(r.get("uuid"), str) or not r["uuid"]:
            continue
        n = 0
        for b in _blocks(r):
            if b.get("type") == "text":
                for s in extract_marks(str(b.get("text") or "")):
                    out.append((i, {"kind": "message", "from": alias, "to": "host", "text": s["text"], "src": "%s#%d" % (r["uuid"], n)}))
                    n += 1
            elif (text := _sent_text(b, results)) is not None:
                out.append((i, {"kind": "message", "from": alias, "to": "host", "text": text, "src": str(b["id"])}))
    for i, e in _ask_events(records):
        if e["kind"] == "question":
            out.append((i, {"kind": "question", "from": alias, "to": "host", "text": e["text"],
                            "choices": e["choices"], "src": e["src"]}))
        else:
            out.append((i, {"kind": "answered", "from": alias, "src": e["src"], "text": e["text"]}))
    out.sort(key=lambda x: x[0])
    return [e for _, e in out]


# The transcript is read by byte offset and never whole: an architect
# session's reaches 155MB. Only complete lines count; the line being written
# is the next reader's.


def _record(line):
    try:
        r = json.loads(line)
    except ValueError:
        return None
    return r if isinstance(r, dict) else None


def _complete_end(f):
    """The offset just past the file's last newline."""
    pos = f.seek(0, os.SEEK_END)
    while pos > 0:
        size = min(1 << 16, pos)
        f.seek(pos - size)
        at = f.read(size).rfind(b"\n")
        if at >= 0:
            return pos - size + at + 1
        pos -= size
    return 0


def _lines_backward(f, end, budget=None):
    """(offset, line) for the complete lines before `end`, the last first;
    with `budget`, reading at most that many bytes."""
    pos, head = end, b""
    while pos > 0 and (budget is None or end - pos < budget):
        size = min(1 << 16, pos)
        pos -= size
        f.seek(pos)
        parts = (f.read(size) + head).split(b"\n")
        head = parts[0]
        at, lines = pos + len(parts[0]) + 1, []
        for part in parts[1:]:
            lines.append((at, part))
            at += len(part) + 1
        for item in reversed(lines):
            if item[1]:
                yield item
    if pos == 0 and head:
        yield 0, head


# How far before the latest `ai-title` a `custom-title` that outranks it is
# looked for. The harness re-appends both whenever either has left the last
# 32 KiB of the transcript, the custom one first (planReAppendSessionMetadata),
# so a current custom title sits within that window of the latest ai title.
TITLE_REACH = 256 << 10
_TITLES = {}  # session -> ((path, size, mtime_ns), title): valid while the file is unchanged


def transcript_title(session_id):
    """A session's title on this machine, as the harness names it ("Session
    name" in /status): the latest `custom-title` record of its transcript (set
    by /rename; an empty one clears it), else the latest `ai-title`; "" for
    neither. The ai title follows the conversation's topic; the custom one is
    the name the human gave it. The last fallback of the in-charge line (§5),
    and what the daemon publishes as `titled` (§8). Read backward from the end,
    at most 8 MiB, and at most TITLE_REACH past the latest ai title."""
    path = transcript_path(session_id)
    if not path:
        return ""
    try:
        st = os.stat(path)
        key = (path, st.st_size, st.st_mtime_ns)
        held = _TITLES.get(session_id)
        if held and held[0] == key:
            return held[1]
        custom, ai, ai_at = None, None, 0
        with open(path, "rb") as f:
            for at, line in _lines_backward(f, _complete_end(f), budget=8 << 20):
                if ai is not None and ai_at - at > TITLE_REACH:
                    break
                if b'-title"' not in line:
                    continue
                r = _record(line) or {}
                if custom is None and r.get("type") == "custom-title" and isinstance(r.get("customTitle"), str):
                    custom = " ".join(r["customTitle"].split())
                    if custom or ai is not None:
                        break
                elif ai is None and r.get("type") == "ai-title" and isinstance(r.get("aiTitle"), str):
                    ai, ai_at = " ".join(r["aiTitle"].split()), at
                    if custom is not None:
                        break
        title = custom or ai or ""
        _TITLES[session_id] = (key, title)
        return title
    except OSError:
        return ""


def _position_path(project, session):
    return project_path(project, "cursors", "export", reader_key(session) + ".json")


def _position_load(project, session, path=None):
    try:
        with open(path or _position_path(project, session)) as f:
            pos = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(pos, dict) and isinstance(pos.get("uuid"), str) and type(pos.get("offset")) is int:
        return pos
    return None


def position_carry(project, session):
    """A session that joins the project — a move, a `join`, a return to a
    project it was in before — exports from where its exports stopped,
    whichever project they ran in: the furthest export position it holds in
    any project here becomes its position in this one, unless the one held
    here is as far already. A position is per project, and the one a session
    left here may be a stint old (A → B → A): resumed from there, its export
    would append again to A what it sent its human while in B. What it wrote
    before the move that no export took yet goes to the project it is in
    now, not nowhere. (Other projects' positions are read in place, never
    through project_path, which would register their homes.)"""
    key = reader_key(session) + ".json"
    best = None
    for p in known_projects():
        pos = _position_load(p, session, os.path.join(p.home, "cursors", "export", key))
        if pos is not None and (best is None or pos["offset"] > best["offset"]):
            best = pos
    if best is None:
        return
    with flocked(project_path(project, "cursors", "export", reader_key(session) + ".lock")):
        here = _position_load(project, session)
        if here is None or here["offset"] < best["offset"]:
            write_json(_position_path(project, session), best)


def _resume_at(f, pos, end):
    """Where an export resumes: just past the position's record, found at its
    offset or else from the end of the file; for a position with no record
    (a transcript that was empty), its offset. None when it does not hold."""
    offset, uid = pos["offset"], pos["uuid"]
    if not 0 <= offset <= end:
        return None
    if not uid:
        if offset:
            f.seek(offset - 1)
            if f.read(1) != b"\n":
                return None
        return offset
    f.seek(offset)
    line = f.readline()
    if line.endswith(b"\n") and (_record(line) or {}).get("uuid") == uid:
        return offset + len(line)
    for at, line in _lines_backward(f, end):
        if uid.encode() in line and (_record(line) or {}).get("uuid") == uid:
            return at + len(line) + 1
    return None


def _trailing_run(f, end):
    """Where the trailing run of assistant records begins: past the last user
    record — the first-use policy for a session with no position."""
    for at, line in _lines_backward(f, end):
        if b'"user"' in line and (_record(line) or {}).get("type") == "user":
            return at + len(line) + 1
    return 0


def position_init(project, session, tpath, since=None):
    """At SessionStart, set the export position to the transcript's current
    end — only when the session has none, so a resume keeps it and a mark
    written before the process died is still exported. With `since` (a
    copy's start), the records written before it are not the session's: a
    copy of a session (source `fork`) starts with its transcript unwritten,
    and the engine writes the conversation it copied there, the original's
    records with their own times, ahead of the copy's first."""
    with flocked(project_path(project, "cursors", "export", reader_key(session) + ".lock")):
        path = _position_path(project, session)
        if os.path.exists(path):
            return
        pos = {"uuid": "", "offset": 0}
        try:
            with open(tpath, "rb") as f:
                end = _complete_end(f)
                pos["offset"] = end
                last = next(_lines_backward(f, end), None)
                uid = (_record(last[1]) or {}).get("uuid") if last else None
                if isinstance(uid, str) and uid:
                    pos = {"uuid": uid, "offset": last[0]}
        except OSError:
            pass
        if since:
            pos["since"] = since
        write_json(path, pos)


def _records_past(project, session, tpath):
    """(records, start, held): the transcript's complete main-chain records
    past the session's export position, as (offset, record), the offset they
    start at, and whether the position held (else the trailing run, §4);
    None when the transcript cannot be opened. A record older than the
    position's `since` is a copy's of its original's (position_init)."""
    pos = _position_load(project, session)
    since = pos.get("since") if pos else None
    try:
        f = open(tpath, "rb")
    except OSError:
        return None
    with f:
        end = _complete_end(f)
        start = _resume_at(f, pos, end) if pos else None
        held = start is not None
        if not held:
            start = _trailing_run(f, end)
        f.seek(start)
        records, at = [], start
        while at < end:
            line = f.readline()
            r = _record(line)
            if r is not None and not r.get("isSidechain") and not (since and str(r.get("timestamp") or since) < since):
                records.append((at, r))
            at += len(line)
    return records, start, held


# The harness queues transcript writes and flushes them every 100 ms, and
# starts the Stop hooks without a flush first (bundle 2.1.292, the write
# queue's FLUSH_INTERVAL_MS and the Stop dispatch): a Stop can read the
# transcript before the turn's last records are on it. Seen live (M6
# acceptance): one mark in 24 exported a turn late.
FLUSH_WAIT = 2.0
FLUSH_POLL = 0.1


def _last_message_text(tpath):
    """The text of the transcript's last message, read from its end, when that
    message is an assistant's: its text blocks joined by newlines, as the
    harness writes a Stop payload's `last_assistant_message` (one message's
    blocks may span several records, one per block, joined by their message
    id). None when the last message is a user-role record — a prompt, a tool
    result, a peer frame: the turn's answer is not on the transcript yet — or
    when the transcript cannot be read. Records of other types and sidechain
    records are passed over."""
    try:
        f = open(tpath, "rb")
    except OSError:
        return None
    key, texts = None, []
    with f:
        for _, line in _lines_backward(f, _complete_end(f)):
            r = _record(line)
            if not r or r.get("isSidechain") or r.get("type") not in ("user", "assistant"):
                continue
            if r["type"] == "user":
                break
            message = r.get("message") if isinstance(r.get("message"), dict) else {}
            k = message.get("id") or r.get("uuid")
            if key is not None and k != key:
                break
            key = k
            texts[:0] = [str(b.get("text") or "") for b in _blocks(r, "text")]
    return "\n".join(texts) if key is not None else None


def _message_call_open(tpath):
    """Whether the transcript's last message is an assistant's holding a call
    of a message tool whose result is not on the transcript yet, read from its
    end past the tool results after it. False when it cannot be read."""
    try:
        f = open(tpath, "rb")
    except OSError:
        return False
    key, answered = None, set()
    with f:
        for _, line in _lines_backward(f, _complete_end(f)):
            r = _record(line)
            if not r or r.get("isSidechain") or r.get("type") not in ("user", "assistant"):
                continue
            if r["type"] == "user":
                results = _blocks(r, "tool_result")
                if key is not None or not results:
                    break
                answered.update(str(b.get("tool_use_id") or "") for b in results)
                continue
            message = r.get("message") if isinstance(r.get("message"), dict) else {}
            k = message.get("id") or r.get("uuid")
            if key is not None and k != key:
                break
            key = k
            if any(b.get("name") in MESSAGE_TOOLS and str(b.get("id") or "") not in answered for b in _blocks(r, "tool_use")):
                return True
    return False


def await_flush(tpath, last_message, until):
    """Before a Stop's export: wait, polling, until the transcript's last
    message is the turn's answer — an assistant message reading the payload's
    `last_assistant_message` — or until `until` (epoch seconds). The same text
    earlier in the transcript is not the answer: a mark the turn repeats is
    still waited for. While the last message holds a message tool's call, the
    wait is also for that call's result: a turn can end on it with no answer
    after it (an Esc, a hook that stops the continuation, a turn end the
    engine asked for), the payload's last message then empty, and a call
    exported only with its result. True when it is there; at the deadline the
    export takes what is there, and the next Stop the rest."""
    text = str(last_message or "").strip()
    while True:
        last = _last_message_text(tpath) if text else None
        if (not text or (last is not None and last.strip() == text)) and not _message_call_open(tpath):
            return True
        if time.time() + FLUSH_POLL > until:
            return False
        time.sleep(FLUSH_POLL)


def export_host(project, session, tpath, alias):
    """Append what the transcript holds for the host past the session's export
    position, as one batch, then advance the position to the last assistant
    record read whose ask and message calls all have their results (so a
    question or a message is never split from the result that accepts it).
    With no position, the trailing run of assistant records is exported (§4).
    Exports of a session are serialised by its export lock, taken before the
    log's locks."""
    with flocked(project_path(project, "cursors", "export", reader_key(session) + ".lock")):
        past = _records_past(project, session, tpath)
        if past is None:
            return 0
        records, start, held = past
        events = host_events([r for _, r in records], alias)
        if events:
            append_host(project, session, events)
        new, pending = None, set()
        for at, r in records:
            for b in _blocks(r, "tool_use"):
                if b.get("name") in (*ASK_TOOLS, MAWS_ASK_TOOL, *MESSAGE_TOOLS) and b.get("id"):
                    pending.add(str(b["id"]))
            for b in _blocks(r, "tool_result"):
                pending.discard(str(b.get("tool_use_id") or ""))
            if r.get("type") == "assistant" and isinstance(r.get("uuid"), str) and r["uuid"] and not pending:
                new = {"uuid": r["uuid"], "offset": at}
        if new is None and not held:
            new = {"uuid": "", "offset": start}
        if new is not None:
            write_json(_position_path(project, session), new)
        return len(events)


def _writer_events(project, host, session, store="log"):
    """The events of the writer `<host>/<session>`, read directly."""
    path = os.path.join(project.home, store, "%s.%s.jsonl" % (host, session))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [e for e in map(parse_event, f) if e]
    except OSError:
        return []


def _former_events(project, session, store="log"):
    """The session's events under the names this machine wrote under before
    it enrolled, for a session it held under them (is_self), oldest name
    first: still the session's own, though nothing appends to them any more."""
    return [e for host, held in machine_identity()[1].items() if session in held
            for e in _writer_events(project, host, session, store)]


def _own_events(project, session, store="log"):
    """The session's own writer files, read directly (the hook reads nothing
    else of the log): under this machine's former names, then its name now."""
    return _former_events(project, session, store) + _writer_events(project, host_name(), session, store)


def host_store_holds(project):
    """Whether the project's host events go to its host store rather than its
    log: on a machine cut over to its endpoint (RL10's first welcome), for
    its own project and every hub project. A git-mirrored or local project
    keeps them in its log, which git mirrors as before; so does every
    project of a machine not cut over."""
    return sibling_module("sminos_rl10").cut_over() and project_kind(project) != "local"


def _askers(project, session, srcs):
    """{src: (writer, question)} for each src whose question another session
    of this machine holds under its own writer — in the log, or in the host
    store (a question asked since the cutover) — and the session's own does
    not. Each file is read only if it holds one of the srcs."""
    srcs = srcs - {e.get("src") for store in ("log", HOST_STORE) for e in _own_events(project, session, store)
                   if e["kind"] == "question"}
    prefix, found = host_name() + ".", {}
    for store in ("log", HOST_STORE):
        where = os.path.join(project.home, store)
        try:
            names = sorted(os.listdir(where)) if srcs else []
        except OSError:
            continue
        for name in names:
            other = name[len(prefix):-len(".jsonl")] if name.startswith(prefix) and name.endswith(".jsonl") else ""
            if other == session or not UUID_RE.match(other):
                continue
            try:
                with open(os.path.join(where, name), "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if any(s.encode() in data for s in srcs):
                for e in map(parse_event, data.decode("utf-8", "replace").split("\n")):
                    if e and e["kind"] == "question" and e.get("src") in srcs:
                        found.setdefault(e["src"], (writer_id(other), e))
    return found


def append_host(project, session, events):
    """Appends a session's host events under its writer, except an answer to
    a question another session of this machine asked: that goes under the
    asker's writer, as its alias's. A copy of a session (a resume the engine
    starts under a new id) answers the questions its original asked, and
    the hub counts a question open by (session, ask) from the writer its
    question came under; under the same writer and src, the original's own
    later export of that answer appends nothing. Where the host store holds
    the project's host events (host_store_holds), they go there, and an event
    whose (kind, src) the writer's log file took before the cutover is not
    appended again. Each writer's route is decided, that check made and the
    append done under the writer's log locks (the store's own taken inside
    them), so two exports of one event on either side of the cutover (the
    bridge's and the Stop hook's) leave one copy: one that chose the log
    before identity.json existed logs it, and one waiting behind it finds it
    there. Returns the events appended."""
    asked = {e["src"] for e in events if e["kind"] == "question"}
    answers = {e["src"] for e in events if e["kind"] == "answered" and e.get("src") and e["src"] not in asked}
    askers = _askers(project, session, answers) if answers else {}
    batches = {writer_id(session): []}
    for e in events:
        writer, question = askers.get(e.get("src"), (None, None)) if e["kind"] == "answered" else (None, None)
        if writer is None:
            batches[writer_id(session)].append(e)
        else:
            batches.setdefault(writer, []).append({**e, "from": question.get("from", e.get("from"))})
    out = []
    for writer, batch in batches.items():
        if not batch:
            continue
        path = writer_path(project, writer)
        with writer_locks(path):
            if not host_store_holds(project):
                out += _append(project, writer, batch, skip_src=True, held=True)
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    logged = {(x["kind"], x["src"]) for x in map(parse_event, f)
                              if x and x["kind"] in HOST_KINDS and x.get("src") is not None}
            except FileNotFoundError:
                logged = set()
            batch = [e for e in batch if (e["kind"], e.get("src")) not in logged]
            if batch:
                out += _append(project, writer, batch, skip_src=True, store=HOST_STORE)
    return out


def host_events_of(project, session):
    """The session's events in the project's host store — its writer's file
    under this machine's name now, and under each former name that held the
    session. Read as the log's files are read
    (_log_file_events: again only once a file changed), for the uplink's
    subscriptions, which look at it on every pump. In host_order."""
    names = [host for host, held in machine_identity()[1].items() if session in held] + [host_name()]
    return host_order([e for host in dict.fromkeys(names)
                       for e in _log_file_events(os.path.join(project.home, HOST_STORE, "%s.%s.jsonl" % (host, session)))])


def host_order(events):
    """Host events in the order they go: each writer's in seq order, the
    writers merged by time. Never by time alone: a clock stepped back would
    put a writer's later seq ahead of an earlier one, and the cursors that
    follow them (the uplink's host_sent, a subscription's) are per writer
    by seq."""
    writers = {}
    for e in events:
        writers.setdefault(e["writer"], []).append(e)
    return list(heapq.merge(*(sorted(es, key=lambda e: e["seq"]) for es in writers.values()),
                            key=lambda e: (e["ts"], e["writer"])))


def record_session(project, session, tpath, event, last_message="", source=""):
    """The hook's work for one session (§4). Membership on sight, as
    reconciliation decides it: a seat whose record is not retired, or a
    session the harness records as `interactive` or `bg` (an SDK run only
    when its host marked it, member_mark), and never an internal fork.
    SessionStart sets a member's export position, then joins
    it: the position first, so a join cut short by the hook's bound (a lock
    held elsewhere) still leaves the first Stop a position rather than the
    trailing-run fallback. Stop joins it if it is not yet (its harness record
    may not have existed at its start) and exports. A session the harness
    has not registered yet at its start is not joined on no evidence, but its
    position is set, so its first turn counts whole at its Stop. A session
    that is not a member records nothing. At Stop, the export first waits a
    little for the turn's last message to reach the transcript (await_flush).
    A copy's position (source `fork`) leaves out what it copied."""
    seen = _on_sight(project, session)
    if seen is None:
        return
    seat, peer = seen
    since = now(ms=True) if source == "fork" else None
    if seat is None and peer is None:
        if event == "SessionStart":
            position_init(project, session, tpath, since)
        return
    marked = member_mark(peer)
    if not joinable(seat, peer, marked):
        return
    # A session nobody launched through sminos is what its own environment,
    # the hook's, says; a seat's provenance came with its launch.
    evidence = None if seat or launch_pending(session) else records_module().hook_provenance(marked)
    if event == "SessionStart":
        position_init(project, session, tpath, since)
    ensure_record(project, session, seat, peer, evidence)
    alias = _member_alias(project, session, seat, peer, marked, evidence)
    if event != "Stop" or alias is None:
        return
    until = time.time() + FLUSH_WAIT
    if _RECORD_DEADLINE is not None:
        until = min(until, _RECORD_DEADLINE - 0.5)
    await_flush(tpath, last_message, until)
    export_host(project, session, tpath, alias)


def _on_sight(project, session):
    """(seat, peer): the seat that binds a session of this machine in the
    project, and the harness's record of it, either None when there is none;
    None for derive's internal fork, which is never a member. The record is
    the running one when there is one: an engine that crashed leaves its
    record beside the one its resume writes, and the mark, a retirement and
    the name are the running process's."""
    seat = seats_by_session(project, [s for s in seats() if s["current"] == session]).get(session)
    recs = [r for r in peer_records() if r.get("sessionId") == session]
    peer = next((r for r in recs if peer_running(r)), recs[0] if recs else None)
    if peer is not None and str(peer.get("pid")) in internal_pids():
        return None
    return seat, peer


def _member_alias(project, session, seat, peer, marked=False, evidence=None):
    """Joins a joinable session the log does not hold as a member yet (a live
    process is evidence of activation), and returns the alias its messages to
    the host carry: its seat's, else the one it goes by (held_alias over the
    last name the log gave it). None when it is no member."""
    own = _own_events(project, session)
    if latest_membership(own) != "joined":
        join_on_sight(project, session, seat, peer, True, marked=marked, evidence=evidence)
        own = _own_events(project, session)
    if latest_membership(own) != "joined":
        return None
    return (seat or {}).get("alias") or held_alias(*own_alias(own, session), peer, session,
                                                    shadowing(project, session))[0] or session[:8]


def export_live(cwd, session, records):
    """The bridge's export (DC2 G4, desk §3): the host events of transcript
    records the session just wrote, as the bridge's child received them, in
    the shape host_events reads, into the session's project. They are
    appended as the Stop hook's export appends them: the same writer, the
    same (kind, src), one batch that drops what the file already holds, so
    whichever of the two comes second adds nothing.
    Membership on sight as the hook decides it; the export position is the
    hook's and is not moved. The child lives as long as its session, so each
    export starts from nothing cached, as each hook run does: the project is
    resolved again (a .smns added, or one that came to name a hub, moves it),
    and so are this machine's identity (an enrollment renames the writer) and
    the harness's records. That costs a few stats and small reads beside the
    writer file the append reads whole, a few times a turn. The project is
    the session's own (session_project), from its launch directory: `cwd`,
    what the session started in as the bridge heard it, only until its
    transcript names one. Returns the events appended."""
    forget_caches()
    project = session_project(session, launch_cwd(session, fallback=cwd))
    if project is None:
        return []
    seen = _on_sight(project, session)
    marked = seen is not None and member_mark(seen[1])
    if seen is None or not joinable(*seen, marked):
        return []
    evidence = None if seen[0] or launch_pending(session) else records_module().hook_provenance(marked)
    ensure_record(project, session, *seen, evidence)
    alias = _member_alias(project, session, *seen, marked, evidence)
    events = host_events(records, alias) if alias is not None else []
    return append_host(project, session, events) if events else []


# The hook is bounded in time (§4: it never blocks a turn): its waits are,
# never a migration step. See run_record.
RECORD_TIMEOUT = 5
_RECORD_DEADLINE = None   # run_record's, for the flush wait to end inside it


class RecordTimeout(BaseException):
    """The hook's time ran out, most likely behind a lock a stalled holder
    keeps. A BaseException, so no `except Exception` on the way swallows it."""


def _record_expired(_signum, _frame):
    raise RecordTimeout()


def _record_gave_up(seconds, behind):
    try:
        daemon_log("record: gave up after %gs, %s; the next Stop retries" % (seconds, behind))
    except OSError:
        pass


def run_record():
    """`sminos record` within SMNS_RECORD_TIMEOUT seconds (default 5).

    Only waiting is bounded, never a mutation that is not safe to cut short.
    migrate's lock is taken by a non-blocking retry against the deadline, and
    when it cannot be had in time, the call records nothing at all. The
    migration steps then run whole, with no timer — one of them (a colliding
    aside board's merge: append, then delete the source) would append twice
    if cut between — and each lock a step takes inside (.metalock for a seat
    record, the log's .sync.lock for a chat import) is waited for only until
    the deadline: a step that cannot have its lock is skipped untouched, logged
    in daemon.log, and done by a later call. Only then is
    an interval timer armed, for the time that is left, around the export —
    the export lock, the log's locks, the batch — where an interruption
    heals: the position moves only after the batch, so the next Stop retries,
    and a batch cut mid-write is completed then, since the batch drops what
    the file already holds and an append ends a torn line. Every other verb
    keeps waiting on the same locks.

    Before all of it, a spawned session's SessionStart claims the provenance
    its launch left for it (claim_launch): it needs only the payload's
    session id, so no migration, missing registry entry or transcript can
    keep a seat from claiming before anything it starts could."""
    if os.environ.get("SMNS_INTERNAL"):
        return
    global _RECORD_DEADLINE
    seconds = float(os.environ.get("SMNS_RECORD_TIMEOUT") or RECORD_TIMEOUT)
    deadline = _RECORD_DEADLINE = time.time() + seconds
    payload = hook_payload()
    if payload is None:
        return
    claim_launch(payload, deadline)
    try:
        migrate(lock_until=deadline)
    except LockBusy:
        _record_gave_up(seconds, "migrate's lock held elsewhere")
        return
    left = deadline - time.time()
    if left <= 0:
        _record_gave_up(seconds, "spent on the migration")
        return
    previous = signal.signal(signal.SIGALRM, _record_expired)
    signal.setitimer(signal.ITIMER_REAL, left)
    try:
        cmd_record(None, payload)
    except RecordTimeout:
        _record_gave_up(seconds, "a lock the export needs held elsewhere")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def hook_payload():
    """The hook's payload on stdin: a JSON object, else None."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def claim_launch(payload, deadline=None):
    """A spawned session's claim of the provenance its spawner left for it,
    under the launch id its merged settings' env carries (SMINOS_LAUNCH).
    Its first SessionStart, a startup, binds the launch to its own session
    id (sminos_records.bind: no lock, so it holds even when the records'
    lock does not come in time) unless it has a final record already; every
    hook of the session the launch is bound to then claims it until one
    succeeds (sminos_records.claim, honoured for that session alone). A
    resume, a /reload-plugins' hooks, or a `claude` started from the seat's
    Bash with the variable inherited (its SessionStart comes after the
    seat's own, which bound it) claims nothing. A failure is a daemon.log
    line."""
    records = records_module()
    launch, session = os.environ.get(records.LAUNCH_ENV, ""), str(payload.get("session_id") or "")
    if not (records.LAUNCH_RE.fullmatch(launch) and UUID_RE.fullmatch(session)):
        return
    try:
        bound = records.bound_to(launch)
        if not bound and payload.get("hook_event_name") == "SessionStart" and payload.get("source") == "startup" \
                and not records.is_final(records.read(session)):
            bound = records.bind(launch, session)
        if bound == session and os.path.exists(records.pending_path(launch)) \
                and records.claim(launch, session, deadline) is not None:
            daemon_log("record: session %s claimed launch %s" % (session[:8], launch[:8]))
    except (OSError, LockBusy) as e:
        try:
            daemon_log("record: session %s could not claim launch %s: %s" % (session[:8], launch[:8], e))
        except OSError:
            pass


def launch_pending(session):
    """Whether the launch in this process's environment is bound to the
    session and still waits for its claim: the session is a spawn's, and its
    own environment is no evidence of a terminal."""
    records = records_module()
    launch = os.environ.get(records.LAUNCH_ENV, "")
    return bool(records.LAUNCH_RE.fullmatch(launch)) and records.bound_to(launch) == session \
        and os.path.exists(records.pending_path(launch))


def cmd_record(_a, payload=None):
    """The hook's verb: one Stop or SessionStart payload on stdin. Records
    nothing for an internal fork, a session in no project, or a non-member;
    a failure is a line in daemon.log, never an exit that blocks a turn
    (run_record bounds it in time)."""
    if os.environ.get("SMNS_INTERNAL"):
        return
    payload = hook_payload() if payload is None else payload
    if payload is None:
        return
    session, cwd = str(payload.get("session_id") or ""), str(payload.get("cwd") or "")
    tpath, event = str(payload.get("transcript_path") or ""), str(payload.get("hook_event_name") or "")
    if not (UUID_RE.match(session) and cwd and tpath):
        return
    try:
        # The payload's cwd is where the session's shell is now; its project
        # is its launch directory's, which the transcript names (§1c).
        project = session_project(session, launch_cwd(session, tpath, fallback=cwd))
        if project is not None:
            record_session(project, session, tpath, event, str(payload.get("last_assistant_message") or ""),
                           str(payload.get("source") or ""))
    except Exception as e:  # noqa: BLE001 — a logging failure must never fail the turn
        try:
            daemon_log("record %s %s: %s: %s" % (event, session[:8], type(e).__name__, e))
        except OSError:
            pass


def _asked(question):
    text = question.get("text")
    return " / ".join(str(t) for t in text) if isinstance(text, list) else str(text or "")


def host_line(e, related=None):
    """One host event as `chat --host` prints it. A question carries its
    answer (`related`) under it, or is marked open; an answer printed apart
    from its question names the call, with the question (`related`) beneath
    it as context when the log holds it."""
    head = "%s %s" % (e["ts"][11:19], e.get("from", ""))
    if e["kind"] == "question":
        out = ["%s asks%s: %s" % (head, "" if related else " (open)", _asked(e))]
        if e.get("choices"):
            out.append("    choices: " + " · ".join(str(c) for c in e["choices"]))
        if related:
            lines = str(related.get("text") or "").split("\n")
            out += ["    answered: " + lines[0]] + ["      " + line for line in lines[1:]]
        return "\n".join(out)
    if e["kind"] == "answered":
        head = "%s answered (call %s)" % (head, e.get("src", ""))
    lines = str(e.get("text") or "").split("\n")
    out = ["%s: %s" % (head, lines[0])] + ["    " + line for line in lines[1:]]
    if e["kind"] == "answered" and related:
        out.append("    to: %s (asked %s %s)" % (_asked(related), related["ts"][:10], related["ts"][11:16]))
    return "\n".join(out)


def chat_host(project, a):
    """What the members sent their human: messages, questions, and answers,
    from the log and, on a cut-over machine, the host store, merged by time.
    A view, not a cursor read: the last 30 host events (-n N), or those since
    a time (--since TS), chosen before anything is grouped; the reader's chat
    cursor never moves. A question shows its answer under it, or is marked
    open; an answer whose question falls outside the window is shown where it
    falls, its question beneath it as context (with --json, the question
    first)."""
    events = list(heapq.merge(log_read(project, kinds=HOST_KINDS), host_read(project),
                              key=lambda e: (e["ts"], e["writer"])))
    questions, answers = {}, {}
    for e in events:
        if e.get("src") and e["kind"] == "question":
            questions.setdefault(e["src"], e)
        elif e.get("src") and e["kind"] == "answered":
            answers.setdefault(e["src"], e)
    if a.since is not None:
        since = normalize_ts(a.since)
        window, head = [e for e in events if e["ts"] >= since], "since %s" % a.since
    else:
        n = a.n if a.n is not None else 30
        window, head = events[-n:], "last %d of %d" % (min(n, len(events)), len(events))
    shown = {id(e) for e in window}

    def context(e):
        """An answer's question, when the window does not hold it."""
        q = questions.get(e.get("src"))
        return q if e["kind"] == "answered" and q is not None and id(q) not in shown else None

    if a.json:
        for e in window:
            if context(e):
                print(json.dumps(context(e), ensure_ascii=False))
            print(json.dumps(e, ensure_ascii=False))
        return
    print("host %s · %s" % (project.name, head))
    if len(events) > len(window) and a.since is None:
        print("+%d earlier — sminos chat %s --host -n %d" % (len(events) - len(window), project.name, len(events)))
    for e in window:
        if e["kind"] == "answered" and not context(e) and e.get("src") in questions \
                and answers.get(e["src"]) is e:
            continue  # printed under its question
        if e["kind"] == "question":
            print(host_line(e, answers.get(e.get("src"))))
        else:
            print(host_line(e, context(e)))
    if not window:
        print("(no messages to the host)")


# ------------------------------------------------------------ the in-charge line
#
# `charge` sets a member's line; `derive` asks a session what it is in charge
# of by forking it headless, and the fork is internal: SMNS_INTERNAL keeps the
# hook from recording it, and $SMINOS_HOME/internal/<pid>, written before the
# fork starts, keeps reconciliation from joining it (§5).
#
# The fork starts in safe mode — without the session's plugins, hooks, mods
# and MCP servers, which a fork answering from the conversation has no use
# for (with them it was offered their tools) — persists nothing, and is sent
# uncached (DISABLE_PROMPT_CACHING): its tool list is not the session's, so
# it never reads a cache, and the hour-long one it would write (the
# session's setting) is read by nothing, the session's next fork being six
# hours away. The plugins were most of its start, and where it failed: on
# the owner's MacBook (2026-10-17 to 10-21, board #111) 30 of 264 forks
# timed out at 120 s, and those that left logs had taken a median 12.5 s and
# 33 s to start the plugins' local MCP servers (cua_repl, ptc; 8 of 13 ptc
# starts hit the 30 s limit) where sessions starting in the same minutes
# took 1.3 s and 2.9 s: the daemon's processes ran in launchd's lower
# scheduling band, which a loaded machine starves (the plist's ProcessType).

DERIVE_QUESTION = ("In one line: what is this session in charge of in this project — its standing responsibility, "
                   "not its latest step?")
DERIVE_PROMPT = DERIVE_QUESTION + " Answer with the line only."
DERIVE_MIN_TOOL_CALLS = 10
DERIVE_EVERY = 6 * 3600
DERIVE_LINE_MAX = 120
# A member whose fork failed is held out of `derive --all` this long (the
# daemon runs it every five minutes, and a fork that timed out tends to time
# out again); a derive that names the member does not wait.
DERIVE_RETRY = 3600
# A failed fork's line carries why, cut to this many characters.
DERIVE_WHY_MAX = 200

# A member sminos may name (charge_naming) is asked for a charge name with its
# line: the prompt is naming_prompt's, and the answer's name is kept only in
# this form — what can follow `@` in a message unquoted.
NAMING_ASK = ("On a second line, name the session after that responsibility: `name: ` followed by 2 to 4 lowercase "
              "English words joined by hyphens, specific enough that another session reading only the name knows "
              "what this one owns. Leave out the project's name, which is shown beside it.")
NAMING_KEEP = (" Its current name is `%s`: keep it unless it no longer describes the standing responsibility well, "
               "because the responsibility changed or became clearer than when the name was chosen.")
NAMING_TAKEN = " Taken by other sessions: %s."
CHARGE_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){1,3}")
CHARGE_NAME_MAX = 48
NAME_LINE_RE = re.compile(r"\s*name:", re.IGNORECASE)
# A pending name its session never took up in a week (no prompt reached it)
# is swept by `derive --all`; its next derive writes a fresh one.
PENDING_NAME_STALE = 7 * 86400


def cmd_charge(a):
    """`charge [<member>] "<line>"`: the member's in-charge line, set. From a
    session, with no member, its own. An empty line clears it."""
    if len(a.args) > 2:
        die('usage: sminos charge [<member>] "<one line>" — quote the line')
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    line = " ".join(a.args[-1].split())
    if len(a.args) == 2:
        target = find_target(a.args[0])
        if target[0] == "none":
            die("no seat or member matching '%s'" % a.args[0], EXIT_UNKNOWN)
    elif not sid:
        die('charge from a terminal names the member: sminos charge <member> "<one line>"')
    else:
        caller = caller_seat()
        project = caller_project(caller)
        me = next((m for m in (members(project) if project else []) if m.session == sid), None)
        if me is None:
            die("this session is no member of a project here: sminos charge <member> \"<one line>\"", EXIT_UNKNOWN)
        target = ("seat", me.seat) if me.seat else ("member", project, me)
    if target[0] == "seat":
        s = target[1]
        if not s["current"]:
            die("%s/%s holds no session to be in charge" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        lifecycle(seat_project(s), s["current"], "in-charge", text=line, source="set")
        name = "%s/%s" % (s["group"], s["alias"])
    else:
        project, m = target[1], target[2]
        if m.local:
            lifecycle(project, m.session, "in-charge", text=line, source="set")
        else:
            # Another machine's session file is that machine's to write (§3).
            try:
                got = _append(project, writer_id(sid or None),
                              [{"kind": "in-charge", "session": m.session, "text": line, "source": "set"}])
            except OSError as e:
                die("the line of %s was not recorded in %s's log: %s" % (m.alias, project.name, e), 1)
            if got and got[0]["seq"] is None:
                print(waits_line(project, writer_id(sid or None)))
        name = m.alias
    print("%s in charge of: %s" % (name, line or "(cleared)"))


class DeriveFailed(Exception):
    def __init__(self, reason, stderr=""):
        super().__init__(reason)
        self.reason, self.stderr = reason, stderr


def model_tool_calls(path, enough):
    """How many tool calls the session's own model made in a transcript,
    counted up to `enough`: the tool_use blocks of its main conversation's
    assistant records (a subagent's sidechain is not its own), each block
    once. Stops at `enough`, so a long transcript is read only that far."""
    seen = set()
    with open(path, "rb") as f:
        for line in f:
            if b'"tool_use"' not in line:
                continue
            r = _record(line)
            if not r or r.get("type") != "assistant" or r.get("isSidechain"):
                continue
            for i, b in enumerate(_blocks(r, "tool_use")):
                seen.add(b.get("id") or (r.get("uuid"), i))
            if len(seen) >= enough:
                break
    return len(seen)


def derive_refusal(project, m):
    """Why a member is not derived, or "": only a local member with no set
    line, at least ten tool calls by its model, and no derived line in the
    last six hours (§5; whatever its name, which only decides whether derive
    may also name it: charge_naming); and one with a derived line only once
    its transcript was written since that line — the same conversation gives
    the same answer, and forking an idle session rebuilds its prompt cache."""
    if not m.session:
        return "it holds no session"
    if not m.local:
        return "it runs on %s" % m.machine
    if m.charge_source == "set":
        return "its line is set"
    path = transcript_path(m.session)
    if not path:
        return "no transcript of it on this machine"
    derived = latest_across_writers([e for e in log_read(project, kinds=("in-charge",))
                                     if e.get("session") == m.session and e.get("source") == "derived"])
    age = ts_age(derived["ts"]) if derived else None
    if age is not None and age < DERIVE_EVERY:
        return "derived %s ago" % short_age(age)
    # The line's own milliseconds: a transcript last written earlier in the
    # same second is idle too.
    then = _ts_epoch(derived["ts"]) if derived else None
    try:
        if age is not None and then is not None and os.path.getmtime(path) <= then:
            return "no activity since its last line, %s ago" % short_age(age)
        n = model_tool_calls(path, DERIVE_MIN_TOOL_CALLS)
    except OSError as e:
        return "its transcript is unreadable: %s" % e
    if n < DERIVE_MIN_TOOL_CALLS:
        return "%d tool call%s, needs %d" % (n, "" if n == 1 else "s", DERIVE_MIN_TOOL_CALLS)
    return ""


def member_cwd(project, m):
    """Where a member's session runs — where its fork must start for
    `--resume` to find the transcript."""
    candidates = [(m.seat or {}).get("cwd"), (session_running(m.session) or {}).get("cwd")]
    candidates += [e.get("cwd") for e in reversed(_own_events(project, m.session)) if e["kind"] == "joined"]
    return next((c for c in candidates if isinstance(c, str) and c and os.path.isdir(c)), project.root or os.getcwd())


def answer_text(text):
    """The fork's answer as it is read: its first mark span's text when it
    has marks (the fork runs under the session's output style), else the
    whole text, tags stripped."""
    spans = extract_marks(text)
    return sminos_marks.TAG.sub("", spans[0]["text"] if spans else text)


def answer_line(text):
    """The fork's answer as an in-charge line: its first line that is not a
    `name:` line, at most 120 characters."""
    return next((x.strip() for x in answer_text(text).splitlines()
                 if x.strip() and not NAME_LINE_RE.match(x)), "")[:DERIVE_LINE_MAX]


def answer_name(text):
    """The name the answer's first `name:` line gives, lowercased, its
    surrounding backticks and quotes and one trailing period trimmed; None
    when it has no such line."""
    line = next((x for x in answer_text(text).splitlines() if NAME_LINE_RE.match(x)), None)
    if line is None:
        return None
    name = line[NAME_LINE_RE.match(line).end():].strip().strip("`'\"")
    name = name[:-1] if name.endswith(".") else name
    return name.strip("`'\"").lower()


def charge_name_refusal(name, taken):
    """Why an answer's name (answer_name) is not kept, or ""."""
    if name is None:
        return "the answer has no name line"
    if not CHARGE_NAME_RE.fullmatch(name):
        return "'%s' is not 2 to 4 lowercase words joined by hyphens" % name
    if len(name) > CHARGE_NAME_MAX:
        return "'%s' is longer than %d characters" % (name, CHARGE_NAME_MAX)
    if name in taken:
        return "'%s' is taken by another session" % name
    return ""


def names_taken(project, session, former=()):
    """The names a session of `project` may not take, lowercased: the
    aliases of the project's other non-retired members, on any machine, and
    of its seats (sminos would not take a harness name that shadows one:
    shadowing), and the engine names of this machine's other running
    sessions, derive's forks aside (the engine yields a suffixed name for
    one a live session holds). The session's own and those of the sessions it continues
    (`former`) are its own."""
    mine = {session, *former}
    ms, rows = project_view(project)
    taken = {m.alias for m in ms if m.session not in mine}
    taken |= {r.alias for r in rows if r.seat and r.seat.get("status") != "retired"}
    internal = internal_pids()   # derive's forks are no sessions
    taken |= {str(r.get("name") or "") for r in peer_records()
              if r.get("sessionId") not in mine and str(r.get("pid")) not in internal and peer_running(r)}
    return {t.lower() for t in taken if t}


class ChargeNaming(NamedTuple):
    before: str     # the engine name a proposal replaces, read before the fork
    pid: object     # the process that held it
    current: str    # the name the fork is told to keep, "" for none
    taken: set      # names_taken


def charge_naming(project, m):
    """Whether derive asks member `m` for a charge name (§2 of the charge
    names design), read from its running engine record as it is now, never
    from the member row (held_alias can keep an alias the engine no longer
    holds): a ChargeNaming, or None for a seat, a stopped session, or a name
    neither the engine made up (`derived`, `auto`) nor sminos proposed."""
    if m.seat or not m.session:
        return None
    rec = running_now(m.session)
    if rec is None:
        return None
    name, source = str(rec.get("name") or ""), str(rec.get("nameSource") or "derived")
    names, latest = proposed_names(log_read(project, kinds=("in-charge",)), (m.session,) + m.former)
    if source not in ("derived", "auto") and name not in names:
        return None
    return ChargeNaming(name, rec.get("pid"), name if name in names else latest,
                        names_taken(project, m.session, m.former))


def naming_prompt(naming):
    """The derive prompt that asks for a charge name with the line; the taken
    list names only what could be answered (the kept form)."""
    shown = sorted(t for t in naming.taken if CHARGE_NAME_RE.fullmatch(t) and len(t) <= CHARGE_NAME_MAX)
    return "%s\n%s%s%s\nAnswer with the two lines only." % (
        DERIVE_QUESTION, NAMING_ASK, NAMING_KEEP % naming.current if naming.current else "",
        NAMING_TAKEN % ", ".join(shown) if shown else "")


def pending_name_path(session):
    return os.path.join(root(), "names", session + ".json")


def hand_name(session, name, before, line):
    """Hand a charge name to its session's mod: the pending file, unless the
    engine holds the name already (then none stays)."""
    path = pending_name_path(session)
    try:
        if before == name:
            if os.path.exists(path):
                os.unlink(path)
            return
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        os.chmod(os.path.dirname(path), 0o700)
        write_json(path, {"session": session, "name": name, "from": before, "line": line, "ts": now()})
    except OSError as e:
        warn("the name %s for %s was recorded, but not handed to its session: %s" % (name, session[:8], e))


def sweep_older(subdir, seconds):
    """Remove the files of $SMINOS_HOME/<subdir> older than `seconds`."""
    d = os.path.join(root(), subdir)
    for name in (os.listdir(d) if os.path.isdir(d) else ()):
        path = os.path.join(d, name)
        try:
            if time.time() - os.path.getmtime(path) > seconds:
                os.unlink(path)
        except OSError:
            pass


def sweep_pending_names():
    """Pending names older than a week: their sessions were never renamed since."""
    sweep_older("names", PENDING_NAME_STALE)


def sweep_internal():
    """Markers of internal forks older than a day: their forks are long gone."""
    sweep_older("internal", 86400)


def derive_failed_path(session):
    return os.path.join(root(), "derive-failed", session)


def derive_failed_age(session):
    """Seconds since the member's last fork failed, or None when its last
    derive did not fail (no stamp)."""
    try:
        return max(0.0, time.time() - os.path.getmtime(derive_failed_path(session)))
    except OSError:
        return None


def derive_failed_mark(session, failed):
    """Stamp a member's failed fork, or clear the stamp once a derive succeeds."""
    path = derive_failed_path(session)
    try:
        if failed:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            open(path, "w").close()
        elif os.path.exists(path):
            os.unlink(path)
    except OSError as e:
        warn("the failed derive of %s could not be %s: %s" % (session[:8], "stamped" if failed else "cleared", e))


def fork_failure(obj, err):
    """Why a fork ended without an answer, as one line of at most
    DERIVE_WHY_MAX characters: its result's error text when it reported an
    error, else the head of its stderr; "" when it said nothing."""
    said = []
    if obj and obj.get("is_error"):
        errors = obj.get("errors")
        said = [str(obj.get("result") or "")] + ([str(e) for e in errors] if isinstance(errors, list) else [])
    text = " ".join(" ".join(said).split()) or " ".join((err or "").split())
    return text[:DERIVE_WHY_MAX]


def derive_line(project, m, prompt=DERIVE_PROMPT):
    """Fork the member's session headless, ask it `prompt`, and return
    (line, answer): its one-line answer (answer_line) and the whole text the
    answer's name is read from. The fork starts behind a gate: its pid is marked internal before it can
    register. It starts in safe mode, uncached, and persists nothing (the
    section's note); its session id is minted here (`--session-id`) all the
    same, so a transcript an engine wrote anyway is known and deleted
    whatever the outcome — an answer, a crash, a timeout — and so is the
    marker. A failure says why (fork_failure). The prompt comes last:
    `--tools` takes several values and would swallow a prompt right after
    it."""
    fork = str(uuidlib.uuid4())
    env = {**os.environ, "SMNS_INTERNAL": "1", "DISABLE_PROMPT_CACHING": "1"}
    args = ["claude", "-p", "--resume", m.session, "--fork-session", "--session-id", fork, "--safe-mode",
            "--no-session-persistence", "--tools", "", "--output-format", "json", prompt]
    gate_r, gate_w = os.pipe()
    marker = ""
    out = err = ""
    obj = None
    try:
        try:
            proc = subprocess.Popen(["/bin/sh", "-c", 'read -r _ <&%d; exec %d<&-; exec "$@"' % (gate_r, gate_r), "sh"]
                                    + args, cwd=member_cwd(project, m), env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, pass_fds=(gate_r,))
        except OSError as e:
            raise DeriveFailed("the fork did not start: %s" % e)
        finally:
            os.close(gate_r)
        os.makedirs(os.path.join(root(), "internal"), mode=0o700, exist_ok=True)
        marker = os.path.join(root(), "internal", str(proc.pid))
        try:
            open(marker, "w").close()
        except OSError as e:
            proc.kill()
            proc.communicate()
            raise DeriveFailed("its fork could not be marked internal: %s" % e)
        os.write(gate_w, b"\n")
        os.close(gate_w)
        gate_w = -1
        timeout = float(os.environ.get("SMINOS_DERIVE_TIMEOUT") or 120)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            why = fork_failure(None, err)
            raise DeriveFailed("the fork timed out after %ds%s" % (timeout, ": " + why if why else ""), err)
        for raw in reversed((out or "").splitlines()):
            if raw.strip().startswith("{"):
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    obj = d
                    break
        if proc.returncode != 0 or obj is None or obj.get("is_error"):
            why = fork_failure(obj, err)
            raise DeriveFailed("the fork failed (exit %d)%s" % (proc.returncode, ": " + why if why else ""), err)
        answer = str(obj.get("result") or "")
        line = answer_line(answer)
        if not line:
            raise DeriveFailed("the fork answered nothing", err)
        return line, answer
    finally:
        if gate_w != -1:
            os.close(gate_w)
        for sid in {fork, str((obj or {}).get("session_id") or "")}:
            path = transcript_now(sid) if UUID_RE.match(sid) and sid != m.session else ""
            if path:
                os.unlink(path)
        if marker:
            try:
                os.unlink(marker)
            except FileNotFoundError:
                pass


def cmd_derive(a):
    """`derive <member> | --all`: ask a local member what it is in charge of,
    by a headless internal fork, and record the answer as a derived line —
    only where §5 allows (derive_refusal). --all: every local member of every
    project known here, as the daemon runs it every five minutes, but a
    member whose fork failed within the hour (DERIVE_RETRY); first lines
    before refreshes (derive_order). --refreshes N (the daemon's): at most N
    members that already have a derived line are forked, so a run, whose
    forks go one after another, never holds a first line back for long."""
    if bool(a.member) == bool(a.all):
        die("usage: sminos derive <member> | --all")
    if a.refreshes is not None and (not a.all or a.refreshes < 0):
        die("usage: sminos derive --all [--refreshes N] — N, at least 0, with --all only")
    sweep_internal()
    if a.all:
        targets = [(p, m) for p in known_projects() for m in members(p) if m.local]
    else:
        target = find_target(a.member)
        if target[0] == "none":
            die("no seat or member matching '%s'" % a.member, EXIT_UNKNOWN)
        if target[0] == "seat":
            s = target[1]
            p = seat_project(s)
            m = next((x for x in members(p) if x.seat and x.seat["seat_id"] == s["seat_id"]), None)
            if m is None:
                die("%s/%s holds no member session to ask" % (s["group"], s["alias"]), EXIT_UNKNOWN)
            targets = [(p, m)]
        else:
            targets = [target[1:]]
    if a.all:
        sweep_pending_names()
        sweep_older("derive-failed", DERIVE_RETRY)
        targets = derive_order(targets)
    else:
        targets = [(p, m, False) for p, m in targets]
    forked_refreshes = failed = 0
    for project, m, refresh in targets:
        spent = refresh and a.refreshes is not None and forked_refreshes >= a.refreshes
        outcome = derive_member(project, m, held_off=a.all, refreshes_spent=a.refreshes if spent else None)
        failed += outcome == "failed"
        forked_refreshes += refresh and outcome in ("derived", "failed")
    if failed:
        sys.exit(1)


def derive_order(targets):
    """--all's order: (project, member, refresh) with the members that have
    no derived line first, so a first line never waits behind other members'
    forks, then the refreshes, the oldest line first."""
    lines = {}
    for p in {p.id: p for p, _ in targets}.values():
        for e in log_read(p, kinds=("in-charge",)):
            if e.get("source") == "derived":
                lines.setdefault((p.id, e.get("session")), []).append(e)
    last = {k: str(latest_across_writers(v).get("ts") or "") for k, v in lines.items()}
    ordered = [(p, m, last.get((p.id, m.session), "")) for p, m in targets]
    ordered.sort(key=lambda t: (bool(t[2]), t[2]))
    return [(p, m, bool(ts)) for p, m, ts in ordered]


def derive_member(project, m, held_off=False, refreshes_spent=None):
    """Derive one member's line where §5 allows (derive_refusal), and, where
    it may be named (charge_naming), its charge name with it: kept only when
    the answer gives one in the charge-name form and free, and when the
    engine name it would replace, read before the fork, is still the
    session's after it (an owner's /rename meanwhile wins). A kept name rides
    on the in-charge event and is handed to the session (hand_name). A
    failed fork is stamped, and with `held_off` (--all) the member is not
    forked again until DERIVE_RETRY has passed; a derive that succeeds clears
    the stamp. `refreshes_spent`, the run's cap on refreshes once it is
    reached: a member that would be forked is left to the next run. Returns
    "refused", "deferred", "derived", or "failed" (nothing recorded)."""
    why = derive_refusal(project, m)
    if not why and held_off:
        age = derive_failed_age(m.session)
        if age is not None and age < DERIVE_RETRY:
            why = "its last fork failed %s ago" % short_age(age)
    if why:
        print("%s: not derived — %s" % (m.alias, why))
        return "refused"
    if refreshes_spent is not None:
        print("%s: not derived — left to the next run, which refreshes at most %d" % (m.alias, refreshes_spent))
        return "deferred"
    naming = charge_naming(project, m)
    try:
        line, answer = derive_line(project, m, naming_prompt(naming) if naming else DERIVE_PROMPT)
    except DeriveFailed as e:
        tail = [x for x in (e.stderr or "").splitlines() if x.strip()][-5:]
        sys.stderr.write("sminos: derive %s failed: %s; nothing recorded\n%s" % (
            m.alias, e.reason, "".join("    %s\n" % x for x in tail)))
        derive_failed_mark(m.session, True)
        return "failed"
    derive_failed_mark(m.session, False)
    name = why_not = ""
    if naming:
        rec = running_now(m.session)
        if rec is None or str(rec.get("name") or "") != naming.before or rec.get("pid") != naming.pid:
            why_not = "renamed during derive"
        else:
            name = answer_name(answer)
            why_not = charge_name_refusal(name, naming.taken)
            name = "" if why_not else name
    lifecycle(project, m.session, "in-charge", text=line, source="derived", **({"name": name} if name else {}))
    print("%s: %s" % (m.alias, line))
    if name:
        print("%s: name %s" % (m.alias, name))
        hand_name(m.session, name, naming.before, line)
    elif why_not:
        print("%s: no name: %s" % (m.alias, why_not))
    return "derived"


def cmd_name_due(a):
    """`name-due --session <id>`: the session's pending charge name, printed
    when it is due, nothing when not — the name mod's check before it applies
    one. Exits 0 but on a usage error: the mod reads stdout, and a prompt
    must never fail on it."""
    if not UUID_RE.match(a.session):
        die("usage: sminos name-due --session <session id>")
    try:
        name = name_due(a.session)
    except Exception as e:
        warn("name-due %s: %s" % (a.session[:8], e))
        name = ""
    if name:
        print(name)


def name_due(session):
    """The pending name of a session (hand_name's file) when it is due: the
    session's running engine record still holds the name the file replaces
    (`from`, so nothing renamed it since: not the owner, not a resume into a
    new process) and not the name itself; the session may still be named, as
    derive judges it (charge_naming: an owner's /rename to the very name it
    had, or a seat it took since, ends that); and the name is still free
    (names_taken: no other member of its project holds it, on any machine,
    and no other running session here). "" otherwise."""
    try:
        with open(pending_name_path(session)) as f:
            pending = json.load(f)
    except (OSError, ValueError):
        return ""
    name, before = (pending.get(k) if isinstance(pending, dict) else None for k in ("name", "from"))
    if not (isinstance(name, str) and CHARGE_NAME_RE.fullmatch(name) and isinstance(before, str)):
        return ""
    rec = session_running(session)
    held = str((rec or {}).get("name") or "")
    if rec is None or held != before or held == name:
        return ""
    project = record_project(rec)
    if project is None:
        return ""
    me = next((m for m in members(project) if m.session == session), None)
    naming = charge_naming(project, me) if me else None
    if naming is None or naming.before != before:
        return ""
    return "" if name in naming.taken else name


# ------------------------------------------------------------------ project verb


def git_toplevel(cwd):
    try:
        p = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def cmd_project(a):
    if a.op == "init":
        project_init(a)
    elif a.op == "show":
        d = os.path.abspath(a.dir or os.getcwd())
        p = resolve_project(d)
        if p is None:
            die("no project at %s: no .smns above it and no git repository around it" % d, EXIT_UNKNOWN)
        kind = project_kind(p)
        if p.hub is not None and not hub_wellformed(p.hub):
            kind, hub = "hub (malformed)", "names no org: no git, no hub"
        elif p.hub is not None and not hub_synced(p.hub):
            kind, hub = "hub (not enrolled)", "org %s — not synced here: this machine is not enrolled in it" % p.hub["org"]
        else:
            hub = "%s (org %s)" % (p.hub["url"], p.hub["org"]) if p.hub is not None else "-"
        print("project  %s\nid       %s\nkind     %s\nsource   %s\nremote   %s\nhub      %s\nroot     %s\nhome     %s" % (
            p.name, p.id, kind, project_source(d), p.remote or "-", hub, p.root or "-", p.home))
    else:
        project_attach(a)


def project_init(a):
    """Write .smns at the repository's root; with --hub, name this machine's
    hub in it — added to a .smns that exists, which changes nothing else. A
    hub .smns for a repository that resolves by its remote pins the project
    it is now (its derived id, and its name unless --name gives one), so
    committing the file moves no session and splits no history."""
    top = git_toplevel(os.getcwd())
    if not top:
        die("project init needs a git repository: .smns is committed at its root")
    path = os.path.join(top, SMNS)
    hub = hub_module().enrolled_hub() if a.hub else None
    if os.path.exists(path):
        smns = read_smns(path)
        if hub and smns:
            hub_module().add_hub(path, smns, hub, a)
            forget_caches()
            project_path(resolve_project(top), "log")
            return
        die("%s is already project %s (%s)" % (top, smns[1], smns[0]) if smns else
            "%s exists but is unreadable — fix or remove it first" % path)
    pinned = repo_project(top, fresh=True) if hub and smns_at(top) is None else None
    name = a.name or (pinned.name if pinned else safe_name(os.path.basename(owning_repo(top) or top)) or "project")
    if "/" in name or "\n" in name or not name.strip():
        die("a project name is one line without '/': %r" % name)
    data = {"project": pinned.id if pinned else str(uuidlib.uuid4()), "name": name, "remote": a.remote or ""}
    if hub:
        data["hub"] = {"org": hub["org"]}  # the URL is each machine's enrollment's (hub_here)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(path, 0o644)  # committed: every clone reads it
    forget_caches()
    project_path(resolve_project(top), "log")
    print("project %s (%s) at %s%s%s — commit it, so every clone is the same project" % (
        name, data["project"], path, ", a hub project of org %s (through %s here)" % (hub["org"], hub["url"]) if hub else "",
        ", pinning the id its remote %s gave it" % derivation(top).key if pinned else ""))


def project_attach(a):
    """Adopt the existing log/ as a working tree of the project's remote —
    the mirror's first half; sminos_daemon owns the mirror. A hub project has
    no mirror: it syncs through its hub alone."""
    p = resolve_project(os.path.abspath(a.dir or os.getcwd()))
    if p is None:
        die("no project here to attach", EXIT_UNKNOWN)
    if p.hub is not None:
        die("project %s syncs through its hub (%s), never through git: there is no mirror to attach%s" % (
            p.name, p.hub["url"] or ("org %s, not enrolled here" % p.hub["org"] if p.hub["org"] else "malformed"),
            "; its remote is the log's archive" if p.remote else ""), 1)
    if not p.remote:
        die("project %s names no remote in its .smns: nothing to attach to" % p.name)
    daemon_module().attach(p)


def resolve_seat(q):
    """The one seat a query names (find_seat, a bare alias in the caller's
    project), or exit 4 naming why not."""
    kind, res = find_seat(q, caller_scope())
    if kind == "ok":
        return res
    if kind == "ambiguous":
        die(ambiguous_seat(q, res), EXIT_UNKNOWN)
    die("no seat matching '%s'" % q, EXIT_UNKNOWN)


def find_target(q):
    """What a member verb (send, status, retire) names: ("seat", seat, session)
    for a seat; ("member", project, member) for a member that holds no seat
    here; else exit 4 — ambiguous (named so they can be told apart) or
    unknown. ("none",) when nothing answers. A seat's `session` is the one the
    name bound — `alias#short`, or a session id that is not the seat's own id —
    and "" when the name named the seat: a verb that re-reads the seat under
    its lifecycle lock refuses when the seat no longer holds that session
    (locked_fresh), so a refill in between cannot take the bound session's
    place. The seat and its session are read after the reconcile: a name of
    the session the seat held binds the job it went on in, when the
    reconcile handed the seat off to one.

    A full id — a seat id or session id — names its seat directly, and so
    does `group/alias` when the qualifier is a group and no project. Any other
    name, `<project>/<alias>` by the project's name or id included, is
    resolved as a tag is (resolve_tag): its projects (those it names; for
    `alias#short` every project known here; else the caller's, then for a
    short every project known here) are
    reconciled, and the name is matched against every member and every seat
    no member stands for (vacant, retired), so a seat and a seat-less session
    sharing an alias are refused as ambiguous rather than the seat being
    taken. A qualifier that is both a project and a group falls back to the
    group when the project has no match."""
    scope = caller_scope()

    def exact(kind, res):
        if kind == "ambiguous":
            die(ambiguous_seat(q, res), EXIT_UNKNOWN)
        if kind == "ok":
            # The reconcile can hand the seat off to the job its session went on
            # in, so the record is read again after it, and a name that bound the
            # session the seat held binds the session it holds now.
            bound = res["current"] == q and res["seat_id"] != q
            reconcile(seat_project(res))  # the verb reads the project; no liveness probe needed
            res = reload_seat(res["seat_id"]) or res
            return ("seat", res, res["current"] if bound else "")
        return None

    def group_seat(group, alias):
        hits = [s for s in seats() if s["group"] == group and s["alias"] == alias]
        return exact("ambiguous" if len(hits) > 1 else "ok" if hits else "none", hits if len(hits) > 1 else
                     (hits[0] if hits else None))

    if UUID_RE.match(q):
        hit = exact(*find_seat(q))
        if hit:
            return hit
    proj, _, rest = q.rpartition("/")
    name, _, short = rest.partition("#")
    tiers = project_tiers(proj) if proj else []
    if proj and not short and not tiers:
        return group_seat(proj, name) or ("none",)

    def matches(projects, by_short):
        hits = []
        for p in projects:
            ms, rows = project_view(p)
            for m in ms + rows:
                ids = (m.session,) + m.former if m.session else ()
                if short:
                    how = alias_reach(m, name, short)
                elif by_short:
                    how = "id" if any(name == s[:8] for s in ids) else ""
                else:
                    how = "id" if name in ids else alias_reach(m, name)
                if how:
                    hits.append((p, m, how))
        # A current alias or id before an alias held before (match_members).
        # One seat is one target, though its session joined one project and
        # its record now resolves to another (a cwd that moved); one session
        # two logs hold at once is the member where it joined last.
        return one_per_session(current_first(hits, name), lambda m: m.seat["seat_id"] if m.seat else m.session)

    # Where the name is looked up, in order, the first pass with a match
    # deciding (§5 of the org directory design, as a tag is resolved): a full
    # id in every project known here; `<project>/<alias>` in the projects the
    # qualifier names (an ordinary project before a machine's of its name);
    # `alias#short` in every project known here at once, so a match in the
    # caller's project never hides one elsewhere; else the caller's project,
    # then a bare name as a short in every project known here. A bare alias
    # never leaves the caller's project.
    if UUID_RE.match(q):
        passes = [(known_projects(), False)]
    elif proj:
        passes = [([p], False) for p in tiers]
    elif scope is None:
        passes = [(known_projects(), False)]
    elif short:
        passes = [(org_scope(), False)]
    else:
        passes = [([scope], False), (org_scope(), True)]
    found, projects = [], []
    for projects, by_short in passes:
        found = matches(projects, by_short)
        if found:
            break
    if len(found) > 1:
        if all(m.seat for _, m in found):
            die(ambiguous_seat(q, [m.seat for _, m in found]), EXIT_UNKNOWN)
        labels = sorted("%s/%s" % (m.seat["group"], m.seat["alias"]) if m.seat else
                        ("%s/" % p.name if len(projects) > 1 else "") + "%s#%s" % (m.alias, m.short)
                        for p, m in found)
        die("ambiguous '%s' matches: %s" % (q, ", ".join(labels)), EXIT_UNKNOWN)
    if not found:
        return (proj and not short and group_seat(proj, name)) or ("none",)
    project, m = found[0]
    note_former(name, short, project, m, scope)
    # A name that bound the session, not the seat — its short, an id, or an
    # alias the session held before the seat took it — binds that session.
    bound = short or name in (m.session,) + m.former or alias_reach(m, name) == "former"
    return ("seat", m.seat, m.session if bound else "") if m.seat else ("member", project, m)


def ambiguous_seat(q, hits):
    """The refusal for a name several seats answer to: each by the name that
    tells it apart (`group/alias`), never by an id."""
    return "ambiguous seat '%s' matches: %s" % (
        q, ", ".join(sorted("%s/%s" % (s["group"], s["alias"]) for s in hits)))


def derive_group(cwd):
    """Default group for a seat spawned without --group: the OWNING repository.

    Board-pipeline workers spawn in a linked worktree (<repo>/.claude/worktrees/
    <name>), whose toplevel is the worktree dir — grouping on that would file
    every worker under its own name. owning_repo follows the common git dir to
    the main checkout, so all a repo's workers share one group (the same rule
    names a local project, resolve_project). Non-git cwd falls back to the
    directory basename.
    """
    name = ""
    if cwd and os.path.isdir(cwd):
        repo = owning_repo(cwd)
        name = os.path.basename(repo) if repo else os.path.basename(os.path.normpath(cwd))
    return safe_name(name) or "fleet"


def group_for_record(m):
    """The group of a legacy record: its own agora_group if present (the daemon
    dimension already knew it), else derived from cwd."""
    return str(m.get("agora_group") or "") or derive_group(str(m.get("cwd") or ""))


def lock_names(names, blocking=False, refusal=None):
    """One lifecycle change per SEAT at a time: spawn / fill / seat add /
    resume / send / retire / remove / sync hold these flocks from their
    availability check through the record commit (through process start, for
    resume). The name locked is the seat key `group/alias` (`seat_key`):
    aliases are unique per group, so a same-alias seat in another group is a
    different seat and does not wait. Names are taken in sorted order so no
    two callers can deadlock. The kernel releases every lock the moment the
    holder exits."""
    d = os.path.join(root(), "locks")
    os.makedirs(d, exist_ok=True)
    locks = []
    # sha1 of the exact name: no lossy sanitization can alias two names onto one
    # lock file. Sorted acquisition: every caller takes its set in the same
    # order, so no set can deadlock against another caller's.
    for nm in sorted(dict.fromkeys(n for n in names if n)):
        lf = open(os.path.join(d, "name__%s.lock" % hashlib.sha1(nm.encode()).hexdigest()), "a+")
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError:
            for held in locks:
                held.close()
            lf.close()
            message = "'%s' is being changed by another sminos process — retry shortly" % nm
            if refusal:
                raise refusal(message, EXIT_UNKNOWN)
            die(message, EXIT_UNKNOWN)
        locks.append(lf)
    return locks


def seat_key(group, alias):
    return "%s/%s" % (group, alias)


def lock_seat(s, blocking=False, refusal=None):
    return lock_names([seat_key(s["group"], s["alias"])], blocking, refusal)


def unlock(locks):
    for lf in locks:
        try:
            lf.close()
        except OSError:
            pass


def reload_seat(seat_id):
    """Re-read one record after taking its lock; None if it vanished."""
    try:
        return load_seat(meta_path(seat_id))
    except Exception:
        return None


# ------------------------------------------------------------------- harness

_AGENTS = None
_PEERS = None


_AGENTS_LOADED = False


def agents_json():
    """Rows from `claude agents --json --all`, or None when the HARNESS failed
    (nonzero exit, timeout, unparseable output) — distinct from [] (an empty
    fleet). Callers that would claim something about a seat's liveness must
    treat None as "unknown" and claim nothing."""
    global _AGENTS, _AGENTS_LOADED
    if not _AGENTS_LOADED:
        _AGENTS_LOADED = True
        try:
            p = subprocess.run(["claude", "agents", "--json", "--all"],
                               capture_output=True, text=True, timeout=60)
            if p.returncode != 0:
                _AGENTS = None
            else:
                parsed = json.loads(p.stdout) if p.stdout.strip() else []
                _AGENTS = parsed if isinstance(parsed, list) else None
        except Exception:
            _AGENTS = None
    return _AGENTS


def agents_refresh():
    global _AGENTS_LOADED
    _AGENTS_LOADED = False
    return agents_json()


def forget_caches():
    """Forget everything cached for the invocation — the agents rows, the peer
    registry, process start times, transcript paths, resolved projects and
    their views — so a long-lived process (the chart TUI, the daemon's loop)
    sees the fleet as it is now rather than as it was at launch. Nothing is
    read until asked. (A launch directory stays: it is checked against its
    transcript's size on every read.)"""
    global _AGENTS_LOADED, _PEERS, _SELF
    _AGENTS_LOADED = False
    _PEERS = None
    _SELF = None
    _PSTART.clear()
    _TRANSCRIPTS.clear()
    _TINDEX.stale()
    _PROJECTS.clear()
    _SEAT_PROJECTS.clear()
    _RECORD_PROJECTS.clear()
    _REPO_BRANCH.clear()
    _REPO_REMOTE.clear()
    _HOMES.clear()
    _VIEWS.clear()
    _ENROLLED.clear()
    _ORG_DIR.clear()


def refresh_caches():
    """forget_caches, then the harness's agents rows read afresh."""
    forget_caches()
    return agents_json()


def harness_ok():
    return agents_json() is not None


def peer_records():
    """The harness's peer registry: one JSON per live-ish session under
    ~/.claude/sessions/<pid>.json. Records of dead sessions linger, so callers
    check the pid before trusting one."""
    global _PEERS, _PEERS_UNREAD
    if _PEERS is None:
        recs, unread = [], []
        for p in glob.glob(os.path.join(home_dir(), ".claude", "sessions", "*.json")):
            try:
                with open(p) as f:
                    d = json.load(f)
            except FileNotFoundError:
                continue   # its session ended while the directory was read
            except Exception:
                unread.append(os.path.basename(p))
                continue
            if isinstance(d, dict):
                recs.append(d)
            else:
                unread.append(os.path.basename(p))
        _PEERS, _PEERS_UNREAD = recs, unread
    return _PEERS


_PEERS_UNREAD = []


def peer_notes():
    """What the engine's session records could not tell, for a view that
    rests on them: [note], empty when every record was read."""
    peer_records()
    d = os.path.join(home_dir(), ".claude", "sessions")
    if not os.path.isdir(d):
        return ["no engine session records here (%s): no session reads as running" % d]
    if _PEERS_UNREAD:
        return ["%d engine session record%s could not be read (%s): %s session%s may be missing or read as not "
                "running" % (len(_PEERS_UNREAD), "" if len(_PEERS_UNREAD) == 1 else "s",
                             ", ".join(sorted(_PEERS_UNREAD)[:3]) + (", …" if len(_PEERS_UNREAD) > 3 else ""),
                             "its" if len(_PEERS_UNREAD) == 1 else "their",
                             "" if len(_PEERS_UNREAD) == 1 else "s")]
    return []


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True
    return True


_PSTART = {}


def read_proc_start(pid):
    """The live process's start time as `ps -o lstart=` prints it, whitespace
    normalised; "" when ps cannot tell. Asked afresh, no cache: what a
    thread beside the one owning the invocation's caches reads. It is read
    where ps reads it, without running ps — the kernel's process table on
    macOS, /proc on Linux: a long-lived reader of every live session (the
    uplink) asked this about each of them, a fork and an exec apiece, which
    on a loaded Linux host held its tick, and every subscribe behind it,
    for tens of seconds."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return ""
    started = _darwin_start(pid) if sys.platform == "darwin" else _linux_start(pid)
    if started is not None:
        return _lstart_text(started) if started else ""
    try:
        # The harness records procStart in the C locale ("Tue Sep  1 20:27:08
        # 2026"); ps must print the same shape, not the user's locale.
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=5, env={**os.environ, "LC_ALL": "C", "LANG": "C"}).stdout
    except Exception:
        out = ""
    return " ".join(out.split())


KINFO_PROC_SIZE = 648  # sizeof(struct kinfo_proc) on 64-bit macOS
_SYSCTL = None         # (ctypes, sysctl) once looked up; False where there is none


def _darwin_start(pid):
    """A process's start, in whole epoch seconds, from `sysctl
    kern.proc.pid` — the kinfo_proc ps reads, whose kp_proc opens with
    p_starttime and holds p_pid at byte 40; 0 when there is no such process;
    None when this cannot tell (no sysctl, or a record of another shape),
    for ps to answer."""
    global _SYSCTL
    if _SYSCTL is None:
        try:
            import ctypes
            sysctl = ctypes.CDLL(None, use_errno=True).sysctl
            sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p,
                               ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
            sysctl.restype = ctypes.c_int
            _SYSCTL = (ctypes, sysctl)
        except (ImportError, OSError, AttributeError):
            _SYSCTL = False
    if not _SYSCTL:
        return None
    ctypes, sysctl = _SYSCTL
    mib = (ctypes.c_int * 4)(1, 14, 1, pid)  # CTL_KERN, KERN_PROC, KERN_PROC_PID
    buf = ctypes.create_string_buffer(KINFO_PROC_SIZE)
    size = ctypes.c_size_t(KINFO_PROC_SIZE)
    if sysctl(mib, 4, buf, ctypes.byref(size), None, 0) != 0:
        return None
    if size.value == 0:
        return 0
    sec, = struct.unpack_from("=q", buf, 0)
    p_pid, = struct.unpack_from("=i", buf, 40)
    return sec if size.value == KINFO_PROC_SIZE and p_pid == pid and sec > 0 else None


_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _lstart_text(epoch):
    """An instant as `ps -o lstart=` prints it in the C locale and the local
    zone, whitespace normalised."""
    t = time.localtime(epoch)
    return "%s %s %d %02d:%02d:%02d %d" % (_DAYS[t.tm_wday], _MONTHS[t.tm_mon - 1], t.tm_mday,
                                           t.tm_hour, t.tm_min, t.tm_sec, t.tm_year)


PROC = "/proc"  # Linux's process table (tests point it at a stand-in)


def _start_ticks(pid):
    """A process's start, in clock ticks since boot, from /proc/<pid>/stat."""
    with open(os.path.join(PROC, str(int(pid)), "stat")) as f:
        # The command name, in parentheses, may hold spaces and
        # parentheses: the fields are counted after the last ")".
        return int(f.read().rsplit(")", 1)[1].split()[19])


def proc_started_at(pid):
    """When a live process started, in epoch seconds to the clock tick, read
    off /proc on Linux; None elsewhere, or when it cannot tell. `ps -o
    lstart` on Linux adds the start's offset to /proc/stat's boot time,
    which is truncated to the second, so it can read up to a second before
    the process began; here the boot instant is now less the uptime, and the
    reading is within a tick of the true start."""
    try:
        ticks = _start_ticks(pid)
        with open(os.path.join(PROC, "uptime")) as f:
            uptime = float(f.read().split()[0])
        return time.time() - uptime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, TypeError):
        return None


def _linux_start(pid):
    """A process's start, in whole epoch seconds, as Linux's ps reckons it
    (procps's pr_lstart): /proc/stat's boot time, a whole second, plus the
    start's offset in whole seconds. Its text is then ps's own, the same on
    every read: a record of it is compared as text (derive_running), and the
    harness records ps's reading (same_process). proc_started_at's truer
    instant can fall in the second after. 0 when there is no such process;
    None when /proc cannot tell (no Linux /proc), for ps to answer."""
    try:
        with open(os.path.join(PROC, "stat")) as f:
            boot = next(int(line.split()[1]) for line in f if line.startswith("btime "))
    except (OSError, ValueError, IndexError, StopIteration):
        return None
    try:
        ticks = _start_ticks(pid)
    except (FileNotFoundError, ProcessLookupError):
        return 0
    except (OSError, ValueError, IndexError):
        return None
    return boot + ticks // os.sysconf("SC_CLK_TCK")


def proc_start(pid):
    """read_proc_start, cached for the invocation."""
    key = str(pid)
    if key not in _PSTART:
        _PSTART[key] = read_proc_start(pid)
    return _PSTART[key]


def _parse_lstart(s):
    return _lstart_struct(" ".join(str(s).split()))


@functools.lru_cache(maxsize=4096)
def _lstart_struct(text):
    """strptime, kept: the same few start times are compared again and again
    (every live session, every reconciling read), and strptime is slow."""
    try:
        return time.strptime(text, "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None


def same_process(rec, fresh=False):
    """Is the record's pid still the process the record described? (`fresh`:
    its start time read afresh, read_proc_start.)

    Both sides are wall-clock strings with no zone in them: `ps -o lstart=`
    prints the LOCAL zone, while the harness writes `procStart` in UTC (every
    record on this machine, harness 2.1.251 through 2.1.259, is offset by
    exactly the local UTC offset). Comparing them as text therefore fails on
    any machine that is not on UTC, which read every live seat as `stopped`
    and made `sminos send` refuse everything. So compare INSTANTS, and accept
    the recorded string under either reading — a recycled pid would have to
    have started at the very same wall-clock second (or exactly a whole zone
    offset away) to slip through, and a wrong guess only costs a failed socket
    connect. When either side cannot be parsed the check is skipped and the
    pid + socket rule decides.
    """
    live = _parse_lstart(read_proc_start(rec.get("pid")) if fresh else proc_start(rec.get("pid")))
    recorded = _parse_lstart(rec.get("procStart"))
    if not live or not recorded:
        return True
    live_epoch = time.mktime(live)
    return any(abs(reading - live_epoch) <= 2
               for reading in (time.mktime(recorded), calendar.timegm(recorded)))


def peer_live(rec):
    """A peer record is live only if its pid is alive, the pid is the SAME
    process the record described (see same_process — a recycled pid fails
    this), AND its inbox socket accepts a connection (a dead session can leave
    its socket FILE behind; only a successful connect proves a listener)."""
    if not pid_alive(rec.get("pid")):
        return False
    if not same_process(rec):
        return False
    return socket_ok(socket_path_of(rec))


def peer_running(rec):
    """The record's process runs: its pid is alive and is the process the
    record described. Membership follows the process (§2); whether its inbox
    answers is delivery's question (peer_live), not membership's."""
    return pid_alive(rec.get("pid")) and same_process(rec)


def session_running(session_id):
    """A harness record for the session whose process runs, or None."""
    return next((r for r in peer_records() if session_id and r.get("sessionId") == session_id and peer_running(r)),
                None)


def running_now(session_id):
    """session_running over the engine's records read afresh, not this
    invocation's copy: what a route about to resume a session asks last."""
    global _PEERS
    _PEERS = None
    return session_running(session_id)


def quiet_inbox_refusal(ref):
    return ('seat %s runs, but its inbox does not answer — nothing was sent; try again, or sminos resume %s '
            '"<msg>" stops its turn and resumes it' % (ref, ref))


def peer_for_session(session_id):
    if not session_id:
        return None
    for rec in peer_records():
        if rec.get("sessionId") == session_id and peer_live(rec):
            return rec
    return None


def live_name_holders(name):
    return [r for r in peer_records() if r.get("name") == name and peer_live(r)]


def socket_path_of(rec):
    p = str(rec.get("messagingSocketPath") or "")
    return p[4:] if p.startswith("uds:") else p


def socket_ok(path):
    if not path:
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(path)
        return True
    except OSError:
        return False
    finally:
        s.close()


class SendFailed(OSError):
    """A socket delivery failed. `phase` is "before" when nothing reached the
    peer (connect/sendall failed — safe to try another path), or "after" when
    the frame had been fully written and only the close-out failed — delivery
    is then UNCERTAIN and the same message must not be sent again by any path."""

    def __init__(self, phase, err):
        super().__init__(str(err))
        self.phase = phase


PEER_TAG = "cross-session-message"
# The engine's closing-tag escape for an envelope's body (2.1.300 `KXe`/`w`/`K`,
# cli.pretty.js ≈ 941747-941780), rebuilt so the envelope round-trips its parser:
# an opening angle or a lookalike, not already followed by a backslash, then a run
# of filler (anything but a word character or an angle), a slash or a lookalike,
# filler, and the tag name, invisible characters allowed between its letters and
# each `-` any dash or connector, then no word character. The match's angle
# becomes `<\\` (one backslash).
_OPEN = "<\uff1c\ufe64\u2329\u27e8\u3008\u2039\u02c2\u1438\u276c\u276e\u2770\u29fc\u226e\u227a\u22d6"
_CLOSE = ">\uff1e\ufe65\u232a\u27e9\u3009\u203a\u02c3\u1433\u276d\u276f\u2771\u29fd\u226f\u227b\u22d7"
_SLASH = "/\uff0f\u2215\u2044"
# \p{Pd}, \p{Pc} and the engine's extra dashes, as one class.
_DASH = ("\u002d\u005f\u02cd\u02d7\u058a\u05be\u0640\u07fa\u1400\u1806\u2010\u2011\u2012\u2013\u2014\u2015"
         "\u2017\u203f\u2040\u2043\u2054\u207b\u208b\u2212\u2796\u2e17\u2e1a\u2e3a\u2e3b\u2e40\u2e5d\u301c"
         "\u3030\u30a0\u30fc\ufe31\ufe32\ufe33\ufe34\ufe4d\ufe4e\ufe4f\ufe58\ufe63\uff0d\uff3f\uff70\U00010ead")
# Between the name's letters only invisible, combining and control characters
# (the engine's `qXe`: its `t$t`, `du` and C0/C1 controls).
_INVIS = ("\u00ad\u034f\u0600-\u0605\u061c\u06dd\u070f\u0890\u0891\u08e2\u115f\u1160\u17b4\u17b5"
          "\u180b-\u180f\u200b-\u200f\u202a-\u202e\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0"
          "\ufff0-\ufffb\U000110bd\U000110cd\U00013430-\U0001343f\U0001bca0-\U0001bca3"
          "\U0001d173-\U0001d17a\U00016fe4\U000e0000-\U000e0fff"
          "\u0300-\u0344\u0346-\u036f\u0483-\u0489\u0591-\u05bd\u05bf\u05c1\u05c2\u05c4\u05c5\u05c7"
          "\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed"
          "\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\u3099\u309a\ufe20-\ufe2f"
          "\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029")
_LETTERS = "[%s]*" % _INVIS
_FILL = "[^A-Za-z0-9_\\-%s%s]*" % (re.escape(_OPEN), re.escape(_CLOSE))
_FILL_SLASH = "[^A-Za-z0-9_\\-%s%s%s]*" % (re.escape(_OPEN), re.escape(_CLOSE), re.escape(_SLASH))
CLOSING_TAG_RE = re.compile("[%s](?!\\\\)(?=%s[%s]%s%s(?:[^A-Za-z0-9_\\-]|$))" % (
    re.escape(_OPEN), _FILL_SLASH, re.escape(_SLASH), _FILL,
    _LETTERS.join("[%s]" % re.escape(_DASH) if ch == "-" else re.escape(ch) for ch in PEER_TAG)),
    re.IGNORECASE)
# What the engine strips from `from-name`: quotes and angles, then control,
# format, surrogate and line/paragraph-separator characters.
NAME_DROP = ("Cc", "Cf", "Cs", "Zl", "Zp")


def reply_line(session, project=""):
    """The body's closing line for a peer's frame: how to answer the session
    that sent it, as a command a model that knows nothing of sminos can run
    (the CLI is not on PATH, so it is named by this install's path, which the
    recipient shares: delivery is always on its own machine). The tag names
    the sender by its short in its own project (`@<project id>/<short>`: the
    event's `from_project` when it spoke into another project's log, else the log's
    own), so a reply reaches it from any project and on any machine; the
    envelope carries no `from` address, so SendMessage has none to answer.
    The project part sits inside a double-quoted shell argument and arrives in
    synced log events, so one that is not id-shaped (valid_name) is left out."""
    if not valid_name(project):
        project = ""
    return '[To reply, run in Bash: %s say "@%s%s <your reply>"]' % (
        shlex.quote(os.path.join(SCRIPT_DIR, "sminos")), "%s/" % project if project else "", session[:8])


def peer_envelope(text, sender="", reply_to="", project=""):
    """The text wrapped as the engine's own SendMessage wraps a peer message
    (2.1.300 SPEC §38.23.1): `<cross-session-message from-name="…">`, the
    body, the closing tag. The receiving engine reads `from-name` into the
    message's origin (the speaker its transcript and MAWS draw) when the
    envelope round-trips its parser: the name stripped as it strips one, and
    a closing tag in the body escaped as it escapes one. No `from` address:
    there is no inbox a reply could reach through SendMessage — a member
    answers with `sminos say`, which, given `reply_to` (the sending session),
    the body's last line spells out (reply_line)."""
    if reply_to:
        text = "%s\n%s" % (text, reply_line(reply_to, project))
    name = "".join(ch for ch in re.sub(r'["<>]', "", sender) if unicodedata.category(ch) not in NAME_DROP)
    name = name.strip()[:64].strip()  # the engine keeps 64 code points, trimmed
    body = CLOSING_TAG_RE.sub("<\\\\", text)
    return "<%s%s>\n%s\n</%s>" % (PEER_TAG, ' from-name="%s"' % name if name else "", body, PEER_TAG)


def send_frame(path, text, sender="", reply_to="", project=""):
    """Write one message frame to a session's inbox socket.

    The frame is a plain user message whose content is the text in the peer
    envelope (peer_envelope, naming `sender`, closed by how to answer the
    session `reply_to` of the project `project` when a session sent it); the
    harness delivers it as a
    peer message ("Another Claude session sent a message"), never as its
    user's words. Callers also put identity in the text's first line.
    Raises SendFailed(phase) — see the class.
    """
    frame = {"type": "user", "message": {"role": "user", "content": peer_envelope(text, sender, reply_to, project)}}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        try:
            s.connect(path)
            s.sendall((json.dumps(frame) + "\n").encode())
        except OSError as e:
            raise SendFailed("before", e)
        try:
            s.shutdown(socket.SHUT_WR)
        except OSError as e:
            raise SendFailed("after", e)
        try:
            # The engine's inbox writes nothing back (tests/inbox_standin.py):
            # this returns at its close, which follows our end, or at the timeout.
            s.recv(4096)
        except OSError:
            pass
    finally:
        s.close()


def agent_row(session_id=None, short=None):
    for r in agents_json() or []:
        if session_id and r.get("sessionId") == session_id:
            return r
        if short and r.get("id") == short and r.get("sessionId"):
            return r
    return None


def harness_row(seat):
    """The harness row for a seat's current session. After a resume the old
    (stopped) job and the new one share a session id. A RUNNING row for the
    session wins outright — an out-of-band same-id revival leaves the old,
    stopped row under the recorded short, and that must not shadow the live
    turn. Then the recorded short (the latest launch sminos knows), then any
    row for the session."""
    rows = agents_json() or []
    cands = [r for r in rows if seat["current"] and r.get("sessionId") == seat["current"]]
    for r in cands:
        if normalize_state(r) in ("working", "blocked"):
            return r
    if seat["short"]:
        for r in rows:
            if r.get("id") == seat["short"] and r.get("sessionId") and (
                    not seat["current"] or r.get("sessionId") == seat["current"]):
                return r
    return cands[-1] if cands else None


def normalize_state(row):
    """The harness's `state` alone lies for a finished background session
    whose process lingers — it stays "working" (or "blocked") indefinitely;
    `status` is the turn signal (busy → idle). Fold the two lingering shapes
    into done / done-blocked before anyone switches on the state."""
    st = row.get("state") or ""
    status = row.get("status") or ""
    if row.get("kind") == "interactive" and not st:
        return "working" if status == "busy" else "done"
    if st == "working" and status == "idle":
        return "done"
    if st == "blocked" and status == "idle":
        return "done-blocked"
    return st


def peer_state(rec):
    """busy | idle | waiting from a LIVE peer record's `status` (idle and
    waiting exact; anything else, including absent or `shell`, is busy)."""
    st = rec.get("status")
    return st if st in ("idle", "waiting") else "busy"


def needs_probe(seat):
    """Whether a seat's word depends on a liveness probe of its session: a
    retired or vacant seat's word is settled by its record alone."""
    return bool(seat.get("current")) and seat.get("status") != "retired"


def seat_state(seat, peer):
    """A seat's one state word, one of STATES. `peer` is a running record of
    its `current` session a caller already holds (a delivery's probe,
    `peer_for_session`, whose inbox answered), or None. Read in this order:
    retired (the recorded status), vacant (no `current`), then the record —
    `peer`, else the session record the harness's own ListAgents reads whose
    process runs (session_running), whether or not its inbox answers — then
    stopped when the session's transcript is on this machine (what a
    `claude --bg --resume` needs), else gone. So a running process is never
    `stopped`, and a delivery that found no inbox never resumes it: its
    inbox's silence is the route's question, not the word's. The harness
    listing is never asked."""
    if seat.get("status") == "retired":
        return "retired"
    if not seat.get("current"):
        return "vacant"
    rec = peer or session_running(seat["current"])
    if rec:
        return peer_state(rec)
    return "stopped" if transcript_path(seat["current"]) else "gone"


def state(seat):
    """A seat's one state word (seat_state)."""
    return seat_state(seat, None)


_SELF = None  # (this machine's name, {former name: its sessions}), per invocation


def machine_identity():
    """(name, former): this installation's machine name — the name its
    endpoint gave it (daemon/identity.json, on a machine cut over to RL10),
    else the name it enrolled under at a desk hub (daemon/hub.json, written by
    `hub enroll`), else DAEMON_HOST, else the system's host name — and, for
    each name it wrote under before, the sessions it held under that name
    then ({name: frozenset}, oldest name first)."""
    global _SELF
    if _SELF is None:
        ident = sibling_module("sminos_rl10").cutover()
        if ident is not None:
            _SELF = (ident["name"], {n: frozenset(ss) for n, ss in ident["former"].items()})
            return _SELF
        try:
            with open(os.path.join(root(), "daemon", "hub.json")) as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = None
        name, former = "", {}
        if isinstance(d, dict) and isinstance(d.get("machine"), str) and valid_name(d["machine"]):
            name = d["machine"]
            if isinstance(d.get("former"), dict):
                former = {n: frozenset(s for s in ss if isinstance(s, str) and s)
                          for n, ss in d["former"].items() if n and isinstance(ss, list)}
        _SELF = (name or os.environ.get("DAEMON_HOST") or socket.gethostname(), former)
    return _SELF


def host_name():
    """The machine every writer this installation creates is named after."""
    return machine_identity()[0]


def is_self(name, session=""):
    """Whether what a record says ran on machine `name` (a member's `machine`,
    a seat's `host`), for `session`, ran here: `name` is this machine's name
    now, or a name it wrote under before it enrolled and `session` one it held
    under that name. Another machine may enroll under a former name, so a
    former name alone is never this machine."""
    me, former = machine_identity()
    return name == me or (bool(session) and session in former.get(name, ()))


def boot_id():
    """A pid (and a `claude agents` short id) is only meaningful in the host's
    current boot; the boot id catches a rebuilt/rebooted machine that kept its
    name but received a fresh pid namespace."""
    if os.environ.get("DAEMON_BOOT_ID") is not None:
        return os.environ["DAEMON_BOOT_ID"]
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        pass
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True,
                             text=True, timeout=5).stdout
        # Anchor on the LEADING `{ sec = N,` field: a greedy match lands on the
        # `sec` inside `usec = ` and records the microseconds instead.
        m = re.match(r"^\{ sec = (\d+),", out.strip())
        return m.group(1) if m else ""
    except Exception:
        return ""


def identity_local(host, boot, session=""):
    """True iff a record's recorded host/boot identity, for `session`, belongs
    to this boot. Empty values preserve legacy local behavior."""
    if host and not is_self(host, session):
        return False
    mine = boot_id()
    if boot and mine and boot != mine:
        return False
    return True


def gateway_env_keys():
    """Names (never values) of the gateway settings file's `env` keys.

    A caller can itself run inside a gateway-routed session whose settings
    file exported ANTHROPIC_BASE_URL, the auth token, model aliases, … into the
    environment; a plain-route child would inherit them — first turn on the
    gateway, nothing recorded, so the first resume silently changes provider.
    Plain-route launches drop every key this returns. PATH is never included:
    the scrub exists to block transport redirection, and PATH is how the
    `claude` binary itself is found.
    """
    f = os.environ.get("CLODEX_SETTINGS") or os.path.join(home_dir(), ".claude", "clodex-settings.json")
    try:
        with open(f) as fh:
            env = json.load(fh).get("env")
    except Exception:
        return []
    if not isinstance(env, dict):
        return []
    return [k for k in env if isinstance(k, str) and k and k != "PATH"]


def launch_env(settings):
    """The environment for a `claude --bg` launch.

    RUNNER_TRACKING_ID is always dropped: under a GitHub Actions runner the
    job env carries it and the runner's post-job cleanup kills any surviving
    process whose environ still has it — nohup/--bg detach the session, not
    the env. So is SMINOS_LAUNCH: a launch id is its own launch's, carried
    in its settings, never one a spawning seat inherited. So is MAWS_LANE,
    MAWS's lane B marker (O12 M3): a seat a lane B session spawns is sminos's
    own, never an observer. So is SMINOS_DESK_PROOF, a desk spawn's proof
    (O12 M7): its record keeps it, and no session inherits it. An EMPTY settings
    value declares the PLAIN route, enforced below the argv by dropping the
    gateway transport env too.
    """
    env = dict(os.environ)
    env.pop("RUNNER_TRACKING_ID", None)
    env.pop(records_module().LAUNCH_ENV, None)
    env.pop("MAWS_LANE", None)
    env.pop(DESK_PROOF_ENV, None)
    if not settings:
        for k in gateway_env_keys():
            env.pop(k, None)
    return env


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def run_claude_bg(args, cwd, settings):
    """Run `claude --bg …` in cwd; return (short, banner). short is "" on failure.
    cwd must be a real directory — callers validate with cwd_or_die; an
    unattended worker is never silently launched somewhere else."""
    if not (cwd and os.path.isdir(cwd)):
        die("launch cwd does not exist or is not a directory: %s" % cwd, EXIT_USAGE)
    try:
        p = subprocess.run(["claude"] + args, cwd=cwd, env=launch_env(settings),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=300)
        banner = ANSI_RE.sub("", p.stdout or "")
        if p.returncode != 0:
            return "", banner
    except Exception as e:  # noqa: BLE001 — any launch failure is a failure
        return "", str(e)
    m = re.search(r"backgrounded · ([0-9a-f]+)", banner)
    return (m.group(1) if m else ""), banner


def claude_stop(short):
    """`claude stop <short>`; True iff the supervisor accepted it."""
    if not short:
        return True
    try:
        p = subprocess.run(["claude", "stop", short], capture_output=True, text=True, timeout=60)
    except Exception:
        return False
    return p.returncode == 0


def wait_stopped(s, short, cur):
    """After `claude stop`, wait (bounded by SMINOS_STOP_TIMEOUT, default 30s)
    until the old turn's harness row is gone or no longer running AND no
    engine record of the session names a running process (running_now: its
    process, whether or not its inbox answers). Resuming while the old
    process still runs makes the harness start a copy; a stop that did not
    take is refused loudly rather than papered over. True iff the turn is
    confirmed down."""
    deadline = time.time() + float(os.environ.get("SMINOS_STOP_TIMEOUT", "30"))
    while True:
        agents_refresh()
        row = agent_row(short=short) if short else harness_row(s)
        running = bool(row) and normalize_state(row) in ("working", "blocked")
        if not running and running_now(cur) is None:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(poll_interval())


def poll_uuid(short, max_iter=None):
    """Wait for the harness row of a just-launched short id to carry a session
    id — the row can lag the banner by a beat. Returns (uuid, state, cwd) or None."""
    if max_iter is None:
        max_iter = int(os.environ.get("SMINOS_UUID_POLL") or os.environ.get("DAEMON_UUID_POLL") or "30")
    for _ in range(max_iter):
        agents_refresh()
        row = agent_row(short=short)
        if row and row.get("sessionId"):
            return row["sessionId"], normalize_state(row), row.get("cwd") or ""
        time.sleep(poll_interval())
    return None


def poll_until_done(short, max_iter):
    """Poll the harness until a turn ends. Returns (uuid, state, cwd, finished).
    max_iter 0 = no cap. `state` is normalized (done / done-blocked / blocked /
    failed / stopped) so the lingering-finished shape reads as done."""
    i = 0
    uuid, state, cwd = "", "timeout", ""
    while True:
        agents_refresh()
        row = agent_row(short=short)
        if row and row.get("sessionId"):
            uuid, state, cwd = row["sessionId"], normalize_state(row), row.get("cwd") or ""
            if state in TERMINAL:
                return uuid, state, cwd, True
        i += 1
        if max_iter and i >= max_iter:
            return uuid, (state if state != "working" else "timeout"), cwd, False
        time.sleep(poll_interval())


def watcher_iterations():
    """How many poll iterations a --wait watcher runs: DAEMON_TIMEOUT seconds
    divided by the poll interval (0 = watch forever). No extra /2 — that halved
    the real budget and rounded to nothing at sub-second intervals."""
    t = int(os.environ.get("DAEMON_TIMEOUT") or "18000")
    if t == 0:
        return 0
    return max(1, int(t / poll_interval()))


def status_for_state(state):
    if state == "done":
        return "idle"
    if state in ("blocked", "done-blocked"):
        return "blocked"
    if state in ("failed", "stopped", "error"):
        return "error"
    return "working"


# session -> its transcript's path, per invocation: reconciliation and state()
# ask for the same stopped sessions' each pass.
_TRANSCRIPTS = {}
# How stale the index may be when a new cache generation (forget_caches) first
# asks it: a long-lived process forgets every few seconds, and a refresh is a
# stat of every project directory. A caller reading or waiting for one
# session's transcript, which may have appeared since, asks transcript_now.
TRANSCRIPT_FRESH = 5.0
TRANSCRIPT_GLOBS = 4   # a process's asks answered by a glob for the one id, before it builds the index
# A `fresh` ask this soon after a refresh began takes that listing as now: the
# writes of one pass (a .smns landing moves every seat under it at once) share
# a refresh rather than pay one each.
TRANSCRIPT_SHARED = 0.25


class TranscriptIndex:
    """Every session's transcript under ~/.claude/projects, by session id. A
    transcript sits directly in its project directory (projects/<dir>/<id>.jsonl;
    only subagent files nest deeper), and the harness mangles the cwd into the
    directory's name, so a session is found by its id, not by its cwd. One
    look per id was a glob, one lstat per project directory — 1,500 of them on
    the owner's Macs, 6 to 36 ms — and a session with no transcript here (an
    old seat's, which the engine cleaned up) paid it on every ask: thousands
    a tick once every machine followed every org project. The index lists a
    directory again only when its mtime moved (a transcript created, moved or
    removed there), so a refresh costs one stat per directory; it is built
    once a process has asked more than a few times (paths), and refreshed
    when asked `fresh` and when a cache generation first asks it once it is
    TRANSCRIPT_FRESH old. Shared with the session plane's threads: one lock."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.base = None
        self.dirs = {}       # directory name → (its mtime_ns as listed, the session ids of its transcripts)
        self.by = {}         # session → [directory name]
        self.at = None       # when the last refresh began (self.clock)
        self.forgot = False  # a cache generation began since (forget_caches)
        self.globbed = 0     # asks answered by a glob, before the index was first built
        self.refreshes = 0

    def stale(self):
        self.forgot = True

    def refresh(self, base):
        began = self.clock()
        held = self.dirs if base == self.base else {}
        dirs = {}
        try:
            entries = list(os.scandir(base))
        except OSError:
            entries = []
        for e in entries:
            try:
                if not e.is_dir():
                    continue
                mtime = e.stat().st_mtime_ns   # before the listing: a file made after it moves the mtime again
                d = held.get(e.name)
                if d is None or d[0] != mtime:
                    d = (mtime, tuple(n[:-6] for n in os.listdir(e.path) if n.endswith(".jsonl")))
            except OSError:
                continue
            dirs[e.name] = d
        by = {}
        for name, (_, sids) in dirs.items():
            for sid in sids:
                by.setdefault(sid, []).append(name)
        self.base, self.dirs, self.by, self.at, self.forgot = base, dirs, by, began, False
        self.refreshes += 1

    def paths(self, session_id, within=None):
        """The transcripts of a session found under the projects directory,
        from a listing begun at most `within` seconds ago (None: the cache
        generation's, up to TRANSCRIPT_FRESH old). A process's first
        TRANSCRIPT_GLOBS asks glob for the one id instead: a verb asks a few,
        and building the index costs as much as several globs."""
        base = os.path.join(home_dir(), ".claude", "projects")
        with self.lock:
            if self.at is None and self.globbed < TRANSCRIPT_GLOBS:
                self.globbed += 1
                return glob.glob(os.path.join(glob.escape(base), "*", session_id + ".jsonl"))
            age = None if self.at is None else self.clock() - self.at
            if age is None or base != self.base or (within is not None and age >= within) or (
                    self.forgot and age >= TRANSCRIPT_FRESH):
                self.refresh(base)
            return [os.path.join(base, d, session_id + ".jsonl") for d in self.by.get(session_id, ())]


_TINDEX = TranscriptIndex()


def transcripts_now():
    """The transcripts read as the directories are now, for what follows: a
    caller about to act on a transcript's absence or its age (the daemon's
    sweeps, which remove what a session left once its transcript is gone)."""
    _TRANSCRIPTS.clear()
    with _TINDEX.lock:
        _TINDEX.refresh(os.path.join(home_dir(), ".claude", "projects"))


def transcript_path(session_id, fresh=False):
    """The path of a session's transcript on this machine, or "" (TranscriptIndex).
    A session found under two project dirs (a repository that moved) answers
    with the one written last. `fresh`: from a listing begun within
    TRANSCRIPT_SHARED — for a write of a pass resting on a transcript that
    may have appeared since, or one found missing since it was looked up
    (the engine moved it); see transcript_now."""
    return _transcript(session_id, TRANSCRIPT_SHARED if fresh else None)


def _transcript(session_id, within):
    if not session_id:
        return ""
    hit = None if within is not None else _TRANSCRIPTS.get(session_id)   # one lookup: the plane's threads ask while the uplink forgets
    if hit:
        return hit
    hits = _TINDEX.paths(session_id, within)
    if not hits:
        _TRANSCRIPTS.pop(session_id, None)
        return ""
    _TRANSCRIPTS[session_id] = path = max(hits, key=_mtime) if len(hits) > 1 else hits[0]
    return path


def transcript_now(session_id):
    """transcript_path, a miss looked for again as the directories are now:
    for a caller that reads or acts on one session's transcript once — a
    reply, a poll, a fork's cleanup — which may have appeared a moment ago,
    even by this process's own hand; never a pass over every session."""
    return transcript_path(session_id) or _transcript(session_id, 0.0)


def transcript_rows(session_id):
    f = transcript_now(session_id)
    rows = []
    if not f:
        return rows
    try:
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return rows


def transcript_contains(session_id, marker):
    f = transcript_now(session_id)
    if not f:
        return False
    try:
        with open(f) as fh:
            return marker in fh.read()
    except OSError:
        return False


def _said(record, results):
    """What an assistant record said: its text, else what it sent its human
    through a message tool (MESSAGE_TOOLS), whose text is in the call's input,
    each call once its result is no error (_sent_text). "" for neither."""
    c = (record.get("message") or {}).get("content")
    if not isinstance(c, list):
        return str(c or "").strip()
    text = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text").strip()
    if text:
        return text
    sent = (_sent_text(b, results) for b in c if isinstance(b, dict))
    return "\n\n".join(t.strip() for t in sent if t and t.strip())


def transcript_reply(session_id, seat_ref="<seat>"):
    """The last thing a session's transcript says (_said: an assistant's text,
    or a message it sent its human through a message tool), plus a rendering
    of a pending AskUserQuestion (a turn can end blocked on it; the question
    lives in the tool_use INPUT, not in text — without rendering it the reply
    would be empty and the orchestrator would have to dig the transcript by
    hand). A response a hook answered in place of a request
    (`answeredWithoutRequest`: to-human's `Message sent to the human.` after a
    final message) says nothing of the session's own and is passed over, so
    a turn that ended on a final message replies with that message."""
    rows = [r for r in transcript_rows(session_id) if r.get("answeredWithoutRequest") is not True]
    results = {str(b.get("tool_use_id") or ""): b for r in rows if r.get("type") == "user" for b in _blocks(r, "tool_result")}
    text = ""
    for r in reversed(rows):
        if r.get("type") == "assistant":
            text = _said(r, results)
            if text:
                break
    pending = []
    last = next((r for r in reversed(rows) if r.get("type") == "assistant"), None)
    if last:
        c = last.get("message", {}).get("content")
        for b in (c if isinstance(c, list) else []):
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                for q in (b.get("input") or {}).get("questions", []):
                    opts = " / ".join(o.get("label", "") for o in q.get("options", []) if isinstance(o, dict))
                    pending.append("Q: %s%s" % (q.get("question", ""), ("\n   options: " + opts) if opts else ""))
    out = text
    if pending:
        out += ('\n[pending AskUserQuestion — the seat is blocked on it; answer with '
                'sminos send %s "<answer>"]\n' % seat_ref) + "\n".join(pending)
    return out.strip()


def record_reply(turn_id, seat_id, state, seat_ref="<seat>"):
    """Write a turn's reply to the seat's reply file, annotating the one blocked
    shape the transcript cannot show: state=blocked with NO pending
    AskUserQuestion — a harness-level prompt holding a tool call that never
    reached the transcript (observed live). Without the marker the reply reads
    like a finished statement and there is nothing to act on."""
    out = transcript_reply(turn_id, seat_ref)
    if state in ("blocked", "done-blocked") and "[pending AskUserQuestion" not in out:
        out += ("\n[blocked on a harness prompt — no pending AskUserQuestion in the transcript, "
                "most likely a permission prompt holding a tool call. Resume with an answer/"
                "instruction via sminos send (the pending call is interrupted), or 'claude attach' "
                "the session to approve it interactively.]")
    os.makedirs(root(), exist_ok=True)
    with open(reply_path(seat_id), "w") as f:
        f.write(out.strip() + "\n")


def reply_text(seat_id):
    try:
        with open(reply_path(seat_id)) as f:
            return f.read().rstrip("\n")
    except OSError:
        return ""


def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


def reply_stale(seat_id, turn_id):
    """True when the session's transcript has moved on since the seat's reply
    file was last written (or there is no reply file yet).

    A seat can be woken by the harness's own SendMessage and run a whole turn
    without any sminos verb in it: nothing marks the record working, nothing
    finalizes it, and the recorded reply keeps describing the PREVIOUS turn.
    The transcript's mtime is the evidence that a turn happened anyway."""
    tx = transcript_now(turn_id)
    if not tx:
        return False
    return _mtime(tx) > _mtime(reply_path(seat_id))


# ----------------------------------------------------------------- migration


def convert_v2_nodes(r, lock_until=None):
    """Convert v2 groups/<g>/nodes/*.json into seat records. Removes only the
    node files it actually converts and rmdir's the nodes/ dir only when it is
    empty (never rmtree — an unreadable node file must survive for a human).
    With lock_until, a node whose record lock cannot be had by then is left
    as it is, for a later call."""
    converted = 0
    # Sorted, so a session v2 seeded in two groups converts the same way on
    # every machine: the first group by name keeps the session's seat id.
    for nodes_dir in sorted(glob.glob(os.path.join(r, "groups", "*", "nodes"))):
        g = os.path.basename(os.path.dirname(nodes_dir))
        for nf in sorted(glob.glob(os.path.join(nodes_dir, "*.json"))):
            try:
                with open(nf) as f:
                    n = json.load(f)
            except Exception:
                continue  # leave an unreadable node file in place — never lose it
            sess = str(n.get("session") or "")
            alias = str(n.get("alias") or os.path.basename(nf)[:-5])
            # A sessionless node gets a DETERMINISTIC id, so a run interrupted
            # mid-convert re-derives the same seat instead of a fresh uuid4 each
            # time (which would multiply the seat on every retry). The namespace
            # keeps the tool's former name: this id must equal the one an
            # interrupted conversion already wrote for the same node.
            det_id = str(uuidlib.uuid5(uuidlib.NAMESPACE_URL, "agora:%s/%s" % (g, alias)))
            seat_id = sess if UUID_RE.match(sess) else det_id
            existing = None
            if os.path.exists(meta_path(seat_id)):
                try:
                    with open(meta_path(seat_id)) as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}
                same_seat = (str(existing.get("group") or existing.get("agora_group") or "") == g
                             and str(existing.get("alias") or existing.get("name") or "") == alias)
                if not same_seat:
                    # The same session id already backs a seat in ANOTHER group
                    # (v2 let one session join two groups). Never overwrite it —
                    # this node gets its deterministic id instead.
                    seat_id = det_id
                    existing = None if not os.path.exists(meta_path(det_id)) else {}
            try:
                _convert_node(seat_id, existing, n, g, alias, sess, lock_until)
            except LockBusy:
                migration_skipped("converting v2 node %s/%s" % (g, alias), ".metalock")
                continue
            os.unlink(nf)
            converted += 1
        try:
            os.rmdir(nodes_dir)  # only if now empty
        except OSError:
            pass
    return converted


def _convert_node(seat_id, existing, n, g, alias, sess, lock_until):
    if existing is not None:
        meta_set(seat_id, {"group": g, "alias": alias, "parent": str(n.get("parent") or ""),
                           "brief": str(n.get("desc") or "")}, lock_until=lock_until)
    else:
        meta_set(seat_id, {
            "uuid": seat_id, "current": sess, "short": "", "name": alias, "alias": alias,
            "group": g, "parent": str(n.get("parent") or ""),
            "role": "", "brief": str(n.get("desc") or ""),
            "task": "", "now": "", "note": "", "cwd": str(n.get("cwd") or ""), "worktree": "",
            "model": "", "settings": "", "effort": "", "status": "retired",
            "host": "", "boot_id": "", "created": str(n.get("joined") or now()),
            "updated": now(), "turns": "0", "preamble": "1"}, lock_until=lock_until)


def _append_board(src, dst):
    """Merge an aside group's board into the root's: the aside posts are
    appended with ids renumbered after the root's last, so no two posts share an
    id and nothing is dropped. Returns True when src was fully merged."""
    base = 0
    for line in open(dst):
        if line.strip():
            base += 1
    moved = []
    for line in open(src):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return False  # an unreadable aside post: leave the file for a human
        base += 1
        rec["id"] = base
        moved.append(json.dumps(rec))
    with open(dst, "a") as f:
        for m in moved:
            f.write(m + "\n")
    if os.environ.get("SMINOS_TEST_MERGE_PAUSE"):  # tests: hold the merge between its append and its delete
        time.sleep(float(os.environ["SMINOS_TEST_MERGE_PAUSE"]))
    os.unlink(src)
    return True


def merge_asides(r):
    """Finish an interrupted cutover. An `<root>.v2-*` aside is a former default
    root that was set aside so the daemon root could take its place; its groups/
    are merged back and it is removed when empty. Runs on EVERY migrate, so a
    crash between the rename and the merge self-heals on the next command. A
    colliding board.jsonl is appended into the root's (ids renumbered). Entries
    at the aside's top level — seat records, reply files, pipeline dirs that an
    older plugin wrote into a recreated former root — move into the root when
    it has nothing of that name; lock dirs and colliding dot-files (locks,
    stamps, markers: no fleet state) are dropped. Any other collision is left
    in place and named on stderr on every run until a human resolves it.
    Returns (asides_removed, warnings)."""
    merged, warnings = 0, []
    for aside in sorted(glob.glob(r + ".v2-*")):
        if not os.path.isdir(aside) or os.path.islink(aside):
            continue
        ag = os.path.join(aside, "groups")
        if os.path.isdir(ag):
            os.makedirs(os.path.join(r, "groups"), exist_ok=True)
            for g in os.listdir(ag):
                src, dst = os.path.join(ag, g), os.path.join(r, "groups", g)
                if os.path.isdir(dst):
                    for sub in os.listdir(src):
                        sp, dp = os.path.join(src, sub), os.path.join(dst, sub)
                        if not os.path.exists(dp):
                            shutil.move(sp, dp)
                        elif sub == "board.jsonl" and os.path.isfile(sp) and os.path.isfile(dp):
                            if not _append_board(sp, dp):
                                warnings.append(sp)
                        elif sub == "locks" and os.path.isdir(sp):
                            shutil.rmtree(sp, ignore_errors=True)  # a lock dir carries no state
                        else:
                            warnings.append(sp)
                    if not os.listdir(src):
                        os.rmdir(src)
                else:
                    shutil.move(src, dst)
            if not os.listdir(ag):
                os.rmdir(ag)
        if os.path.isdir(aside):
            for entry in os.listdir(aside):
                if entry == "groups":
                    continue
                sp, dp = os.path.join(aside, entry), os.path.join(r, entry)
                if entry in ("locks", "surface-locks") and os.path.isdir(sp):
                    shutil.rmtree(sp, ignore_errors=True)  # a lock dir carries no state
                elif not os.path.lexists(dp):
                    os.makedirs(r, exist_ok=True)
                    shutil.move(sp, dp)  # a seat record, its reply, a pipeline dir: never strand it
                elif entry.startswith(".") and os.path.isfile(sp):
                    os.unlink(sp)  # .metalock, a stamp, a marker: the root already has its own
                else:
                    warnings.append(sp)
        if os.path.isdir(aside) and not os.listdir(aside):
            os.rmdir(aside)
            merged += 1
    return merged, warnings


LEGACY_ROOT_NAMES = ("orchestrating-daemons", "agora")  # oldest first


def legacy_roots():
    """Former default roots, oldest first: the daemon substrate's, then
    sminos's under its former name."""
    return [os.path.join(home_dir(), ".claude", n) for n in LEGACY_ROOT_NAMES]


def set_aside(path, r):
    """Move `path` out of the way as a `<root>.v2-<ts>` aside for merge_asides
    to fold back in. Returns the aside path — unique even within one second, so
    two former roots set aside by one run cannot collide."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    aside, n = r + ".v2-" + stamp, 0
    while os.path.lexists(aside):
        n += 1
        aside = "%s.v2-%s-%d" % (r, stamp, n)
    os.rename(path, aside)
    return aside


class LockBusy(Exception):
    """A lock could not be had before a deadline."""


def flock_until(f, deadline, exclusive=True):
    """A flock on f, exclusive or shared; with a deadline, retried without
    blocking until it, then LockBusy. Without one, it waits as long as it takes."""
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    if deadline is None:
        fcntl.flock(f, mode)
        return
    while True:
        try:
            fcntl.flock(f, mode | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.time() >= deadline:
                raise LockBusy()
            time.sleep(0.02)


def migration_skipped(step, lock):
    """A migration step the record hook left for a later call: its lock was
    held past the hook's deadline, so the step mutated nothing."""
    try:
        daemon_log("migrate: skipped %s — %s held past the deadline; a later call does it" % (step, lock))
    except OSError:
        pass


def migrate(quiet=False, lock_until=None):
    """Bring a pre-seat state root up to date. Idempotent; runs before every verb.

    The whole cutover is serialized by an exclusive flock on
    ~/.claude/.agora-migrate.lock — under the tool's former name on purpose, so
    a still-cached older `agora` binary and this one never run a migration
    pass concurrently during the upgrade. Steps:

    1. Former roots, when the default root is in use. The registry has lived at
       ~/.claude/orchestrating-daemons (the daemon substrate) and then at
       ~/.claude/agora (sminos's former name). A former root that is still a
       real directory is renamed INTO place as one atomic step while the new
       root holds no records (a bare new root — a consumer's mkdir — is set
       aside first); once the root holds records, a real directory at a former
       path is set aside beside it instead, so the registry is never displaced
       by a directory recreated at an old path. A symlink is left at every
       former path so anything still holding one keeps resolving. Set-aside
       groups/ are merged back by merge_asides, which also runs on every later
       call — so a crash mid-cutover self-heals.
    2. Every run, per record (the scan is cheap), BEFORE any v2 node conversion:
       a record lacking `group` is stamped (its own agora_group if it had one,
       else derived from cwd); a legacy codex-CLI worker record (engine: codex)
       is retired when its status is already terminal or its recorded pid is
       dead — a working/blocked one with a live pid is left alone (refill
       refuses it). Demotions never touch `updated`: the pipeline picks the
       record with the greatest `updated`, so a bumped loser would displace the
       canonical seat.
    3. v2 layout: groups/<g>/nodes/*.json become seat records (retired); a node
       matches a daemon record on `group` or `agora_group`.
    4. Alias dedupe, decided from the records as read (before any demotion
       rewrite): when several records share (group, alias) — the old substrate
       respawned workers under one name — a claude record beats a codex one,
       then the newest `updated` wins; each loser becomes `<alias>@<short>` and
       retired, `updated` and `name` (pipeline fields) untouched.
    5. Every run: the root is 0700 and no record/reply/err file is wider than
       0600 (the old substrate left 0755/0644); each former path is a symlink to
       the root whenever it is missing (a crash after the rename must not leave
       older consumers without a path); an aside left over from an interrupted
       cutover is merged (colliding boards appended with renumbered ids) and
       anything it still holds is named on stderr on every run.
    """
    r = root()
    did = []
    lockdir = os.path.join(home_dir(), ".claude")
    os.makedirs(lockdir, exist_ok=True)
    # The former name, shared with cached older `agora` binaries (see docstring).
    with open(os.path.join(lockdir, ".agora-migrate.lock"), "a") as mlf:
        # lock_until (the record hook's deadline): LockBusy before any step
        # runs; inside, each step's own lock is waited for only until then,
        # and a step that cannot have it is skipped untouched for a later call.
        flock_until(mlf, lock_until)
        try:
            if r == default_root():
                for old in legacy_roots():
                    if not os.path.isdir(old) or os.path.islink(old):
                        continue
                    if os.path.isdir(r) and any(True for _ in record_files()):
                        did.append("set aside %s as %s" % (old, set_aside(old, r)))
                    else:
                        if os.path.lexists(r):
                            set_aside(r, r)
                        os.rename(old, r)
                        did.append("renamed %s -> %s" % (old, r))
                for old in legacy_roots():
                    if os.path.isdir(r) and not os.path.lexists(old):
                        try:
                            os.symlink(r, old)
                        except FileExistsError:
                            continue  # an older consumer recreated the path in the gap; the next run folds it in
                        did.append("linked %s -> %s" % (old, r))
            merged, leftovers = merge_asides(r)
            if merged:
                did.append("merged an interrupted v2 aside back into the root")
            for lp in leftovers:
                sys.stderr.write("sminos: warning: unmerged aside entry left in place: %s\n" % lp)
            if os.path.isdir(r):
                if os.stat(r).st_mode & 0o077:
                    os.chmod(r, 0o700)
                    did.append("tightened the root to 0700")
                tight = 0
                for p in glob.glob(os.path.join(r, "*")):
                    if os.path.isfile(p) and (p.endswith(".json") or p.endswith(".reply.txt") or p.endswith(".err")):
                        if os.stat(p).st_mode & 0o077:
                            os.chmod(p, 0o600)
                            tight += 1
                if tight:
                    did.append("tightened %d file(s) to 0600" % tight)
            # Pass 1 — stamp groups and retire dead codex records. Decide the
            # alias winners from the records AS READ, before any rewrite.
            stamped = retired = 0
            by_key = {}
            for p in record_files():
                try:
                    with open(p) as f:
                        m = json.load(f)
                except Exception:
                    continue
                sid = os.path.basename(p)[:-5]
                fields = {}
                if not m.get("group"):
                    fields["group"] = group_for_record(m)
                    stamped += 1
                if m.get("engine") == "codex" and m.get("status") != "retired":
                    if m.get("status") not in ("working", "blocked") or not pid_alive(m.get("pid")):
                        fields["status"] = "retired"  # never `updated`: demotions must not win recency
                        retired += 1
                alias = str(m.get("alias") or m.get("name") or "")
                if alias:
                    key = (str(m.get("group") or fields.get("group") or ""), alias)
                    by_key.setdefault(key, []).append((m.get("engine") != "codex", str(m.get("updated") or ""), sid, m))
                if fields:
                    try:
                        meta_set(sid, fields, bump=False, lock_until=lock_until)
                    except LockBusy:
                        migration_skipped("migrating record %s" % sid[:8], ".metalock")
                        stamped -= "group" in fields
                        retired -= fields.get("status") == "retired"
            n = convert_v2_nodes(r, lock_until)
            if n:
                did.append("converted %d v2 node(s) into seats" % n)
            # Pass 2 — dedupe (group, alias): a claude record beats a codex one,
            # then the newest `updated` keeps the alias.
            deduped = 0
            for (g, alias), recs in by_key.items():
                if len(recs) < 2:
                    continue
                recs.sort(key=lambda t: (t[0], t[1]), reverse=True)
                for _claude, _upd, sid, m in recs[1:]:
                    tag = str(m.get("short") or "") or sid[:8]
                    fields = {"alias": "%s@%s" % (alias, tag)}
                    if m.get("status") != "retired":
                        fields["status"] = "retired"  # `updated` untouched
                    try:
                        meta_set(sid, fields, bump=False, create=False, lock_until=lock_until)
                    except LockBusy:
                        migration_skipped("renaming duplicate alias %s of %s" % (alias, sid[:8]), ".metalock")
                        continue
                    deduped += 1
            if stamped or retired or deduped:
                did.append("stamped group on %d record(s), retired %d legacy codex record(s), renamed %d duplicate alias(es)" % (
                    stamped, retired, deduped))
            imported = import_chats(lock_until)
            if imported:
                did.append("imported %d family chat(s) into project logs" % imported)
        finally:
            fcntl.flock(mlf, fcntl.LOCK_UN)
    if did and not quiet:
        sys.stderr.write("sminos: migrated: %s\n" % "; ".join(did))
    return did


def legacy_ts(ts):
    """A family chat's whole-second ts in the log's millisecond shape."""
    ts = str(ts or "")
    return ts[:-1] + ".000Z" if re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", ts) else ts


def import_chats(lock_until=None):
    """Fold each former per-host family chat (chats/<host-seat-id>.jsonl) into
    the project log of the host's cwd, as writer legacy/<host-seat-id>: ts,
    sender and text kept, a tag resolved against the host's group to the
    session its seat holds (an unresolvable one stays as text, and the event
    is to "*"). The writer file is written whole and renamed into place; the
    chat file is then set aside as .imported, so the import runs once. The
    chat's own lock (chats/<host-seat-id>.lock, under which the previous CLI
    appends to and rewrites it) is held from the read through the set-aside,
    so a line it appends meanwhile is never archived without being imported.
    A chat whose host record is gone stays, its project unknown. With
    lock_until, a chat whose own lock or log lock cannot be had by then is
    left as it is, for a later call."""
    files = sorted(glob.glob(os.path.join(root(), "chats", "*.jsonl")))
    if not files:
        return 0
    by_id = {s["seat_id"]: s for s in seats()}
    imported = 0
    for path in files:
        host_id = os.path.basename(path)[:-len(".jsonl")]
        host = by_id.get(host_id)
        project = seat_project(host) if host else None
        if project is None:
            continue
        try:
            with flocked(path[:-len(".jsonl")] + ".lock", lock_until=lock_until):
                imported += _import_chat(path, host_id, host, project, by_id, lock_until)
        except LockBusy:
            migration_skipped("importing chat %s" % host_id[:8], "chats/%s.lock" % host_id)
    return imported


def _import_chat(path, host_id, host, project, by_id, lock_until):
    """One chat's import, under its lock (import_chats): 1 when it is set
    aside as imported, 0 when it is left for a later call."""
    writer = "legacy/" + host_id
    target = writer_path(project, writer)
    if not os.path.exists(target):
        sessions = {s["alias"]: s["current"] for s in by_id.values()
                    if s["group"] == host["group"] and s["current"]}
        rows = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and type(r.get("id")) is int:
                    rows.append(r)
        events = []
        for seq, r in enumerate(sorted(rows, key=lambda r: r["id"]), 1):
            to = [{"session": sessions[alias], "alias": alias} for alias in r.get("to") or []
                  if r.get("mode") == "tagged" and isinstance(alias, str) and alias in sessions]
            sender = str(r.get("from") or "")
            events.append({"ts": legacy_ts(r.get("ts")), "writer": writer, "seq": seq,
                           "kind": "human" if sender == "human" else "say", "from": sender,
                           "to": to or "*", "text": str(r.get("text") or "")})
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-")
        with os.fdopen(fd, "w") as f:
            f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
        try:
            with flocked(os.path.join(os.path.dirname(target), ".sync.lock"), exclusive=False,
                         lock_until=lock_until):
                os.replace(tmp, target)
        except LockBusy:
            os.unlink(tmp)
            migration_skipped("importing chat %s" % host_id[:8], "the log's .sync.lock")
            return 0
    os.replace(path, path + ".imported")
    return 1


# --------------------------------------------------------------- spawn / fill


def render_preamble(project, alias, by=""):
    """The spawn preamble every spawn renders (§6), with {{PROJECT}},
    {{ALIAS}}, {{BY}} (the spawner, or "the operator"), and {{SMINOS_CLI}}
    filled."""
    try:
        with open(PREAMBLE_PATH) as f:
            t = f.read()
    except OSError:
        die("preamble template missing: %s" % PREAMBLE_PATH, 1)
    return (t.replace("{{PROJECT}}", project).replace("{{ALIAS}}", alias)
             .replace("{{BY}}", by or "the operator").replace("{{SMINOS_CLI}}", LAUNCHER))


def compose_task(task, brief, preamble):
    parts = []
    if preamble:
        parts.append(preamble.rstrip("\n"))
    if brief:
        parts.append("Your seat's brief: %s" % brief)
    parts.append(task)
    return "\n\n".join(parts)


def claude_args(alias, model, settings, effort, worktree="", permission_mode="auto"):
    """argv for a FRESH background launch. Never used for a resume: a resumed
    background session keeps its saved options, and any flag on
    `claude --bg --resume` makes the harness start a COPY instead (observed
    live, v2.1.257: "keeps its own saved options, so the flags you passed
    started a copy")."""
    args = ["--bg", "--permission-mode", permission_mode, "-n", alias]
    if worktree:
        args += ["--worktree", re.sub(r"[^a-zA-Z0-9._-]", "-", worktree)]
    if model:
        args += ["--model", model]
    if settings:
        args += ["--settings", settings]
    if effort:
        args += ["--effort", effort]
    return args


def launch_settings(settings, launch):
    """The settings a fresh seat launches with: the caller's, plus
    `env.SMINOS_LAUNCH`, the launch id under which its provenance waits for
    it to claim (sminos_records), and, when SMINOS_HOME (or the legacy
    DAEMON_HOME) is set, `env.SMINOS_HOME` naming this registry.

    `claude --bg` hands the launch to the harness's supervisor, which claims
    a pre-started process: the seat's environment is the supervisor's, not
    this process's (observed live, harness 2.1.299: a seat spawned with
    SMINOS_HOME set printed none). A seat whose sminos calls and hook ran
    against the default registry would talk to a different family, and under
    a test registry would migrate the human's real one. A seat takes one
    settings source, so a caller's `--settings` (a file or a JSON object) is
    merged into one file, written under this registry's `settings/` and
    named by its content: a resume keeps the launch's options, this path
    among them. Only the argv changes: the route a seat runs on is still
    decided by the caller's own settings (launch_env). The file is written
    under the default home too, so inline settings are always a private
    file the seat's record can name, never content it holds."""
    home = os.environ.get("SMINOS_HOME") or os.environ.get("DAEMON_HOME")
    merged = {}
    if settings:
        text = settings
        if not settings.lstrip().startswith("{"):
            try:
                with open(os.path.expanduser(settings)) as f:
                    text = f.read()
            except OSError as e:
                die("--settings %s: %s" % (settings, e.strerror or e), EXIT_USAGE)
        try:
            merged = json.loads(text)
        except ValueError:
            merged = None
        if not isinstance(merged, dict):
            die("--settings %s: not a JSON object" % settings, EXIT_USAGE)
    env = merged.get("env") if isinstance(merged.get("env"), dict) else {}
    merged["env"] = {**env, **({"SMINOS_HOME": root()} if home else {}), records_module().LAUNCH_ENV: launch}
    body = json.dumps(merged, indent=2, sort_keys=True) + "\n"
    path = os.path.join(root(), "settings", hashlib.sha256(body.encode()).hexdigest()[:16] + ".json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w") as f:
            f.write(body)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    return path


def env_default(value, env_name):
    return value if value is not None else os.environ.get(env_name, "")


def finish_turn(seat_id, short, alias, uuid_hint, guard):
    """--wait: watch a turn to its end, record the reply, return the status.

    The final write is CONDITIONAL on `guard`: minutes may pass in the watcher,
    during which the seat could be purged or re-filled into a different session.
    meta_set_if re-reads under the lock and writes only if the record still
    exists and the guard (same session, and same launch when we know its short)
    still holds — never resurrecting a purged record nor clobbering a newer
    session. A watcher timeout is not a finished turn: status stays working
    (also conditionally) and the reply is readable later with `sminos reply`."""
    uuid, state, _cwd, finished = poll_until_done(short, watcher_iterations())
    if not finished:
        meta_set_if(seat_id, {"status": "working", "updated": now()}, guard)
        sys.stderr.write("sminos: watcher expired; turn %s of %s is still running (status=working). "
                         "Read it later with: sminos reply %s\n" % (short, alias, alias))
        sys.exit(1)
    status = status_for_state(state)
    # The reply rides the same guarded, in-lock write: never a reply file next
    # to a record that was retired, purged, or re-filled while we waited.
    meta_set_if(seat_id, {"status": status, "updated": now()}, guard, reply=(uuid or uuid_hint, state, alias))
    return status


def print_reply_block(seat_id):
    print("--- reply ---")
    print(reply_text(seat_id) or "(no reply yet)")


def cwd_or_die(cwd, verb):
    """Resolve a launch cwd, or die: an unattended auto-mode worker must run in a
    real directory. Never silently substitute HOME — that would drop the worker
    into the wrong repo with no one watching."""
    cwd = os.path.abspath(cwd or os.getcwd())
    if not os.path.isdir(cwd):
        die("%s: cwd does not exist or is not a directory: %s" % (verb, cwd), EXIT_USAGE)
    return cwd


def parse_stamps(items):
    """`--stamp field=value`, repeatable, as a dict merged into the launch record.

    For provenance a caller needs on the record from its FIRST write rather than
    a moment later. A separate `meta set` after the spawn never runs when the
    uuid poll times out or the caller dies inside it, and the board client reads
    `board_dispatch` precisely to tell a dispatched seat from an operator's own
    — a marker that can go missing is a marker that fails open.
    """
    out = {}
    for item in items or []:
        field, sep, value = item.partition("=")
        field = field.strip()
        if not sep or not field:
            die("--stamp takes field=value: %s" % item, EXIT_USAGE)
        if SECRET_RE.search(field):
            # Same refusal `meta set` makes: a launch record is written before
            # anything narrows its mode, so a credential stamped here would
            # exist world-readable for the width of that write.
            die("'%s' is a credential field — not writable through --stamp" % field, EXIT_USAGE)
        out[field] = value
    return out


def spawn_fresh(seat_id, alias, group, role, brief, task, cwd, worktree,
                model, settings, effort, wait, locks, verb, stamp=None, permission_mode="auto"):
    """Launch a fresh background session for a seat and register it.

    seat_id None → a brand-new seat: a provisional record exists during the
    first turn (so the agent can post / be looked up), then is promoted to the
    first session's uuid as the seat id. seat_id set → an in-place re-fill: the
    record keeps its id, `note`/`created`, and every pipeline-owned field; the
    launch + definition fields are overwritten, `attempts` is bumped and the
    previous occupant is appended to `history` (last 10) for the pipeline's
    outage-streak logic. The session launches under -n <alias>: the seat's one
    name is also the harness name the native SendMessage reaches it by. The
    banner's bracket is always `[<short> / <RECORD FILENAME>]` — the pipeline
    parses that value and board-bind matches it against filenames, so on a
    re-fill it is the seat id, never the new session's uuid.

    In the project's log: `retired` (replaced) for the session a re-fill
    displaces, then `joined` for the new one with its spawner as `by`, then,
    when the seat has a brief, the brief as its `in-charge` line. Every spawn
    renders the preamble. Returns nothing (prints; may exit).

    The new session's record (spawn_provenance) is fixed before it exists:
    left pending under a launch id its settings carry, claimed by its own
    first SessionStart, else by this spawn once the harness names it."""
    prev = reload_seat(seat_id) if seat_id else None
    project = seat_project({"cwd": cwd, "group": group})
    by = caller_alias()
    # A desk member is the human, whom the preamble calls "the operator".
    preamble = render_preamble(project.name, alias, "" if desk_member() else by)
    task_text = compose_task(task, brief or "", preamble)
    records = records_module()
    launch_id = records.new_launch()
    merged = launch_settings(settings, launch_id)
    records.write_pending(launch_id, spawn_provenance(settings, merged))
    short, banner = run_claude_bg(claude_args(alias, model, merged, effort, worktree,
                                              permission_mode) + [task_text], cwd, settings)
    if not short:
        records.drop_pending(launch_id)
        sys.stderr.write("sminos: %s failed — could not parse background id from:\n%s\n" % (verb, banner))
        sys.exit(1)
    launch = {
        "current": "", "short": short, "name": alias, "alias": alias, "group": group,
        "role": role or "", "brief": brief or "",
        "task": task_text, "cwd": cwd, "worktree": worktree or "", "model": model or "",
        "settings": settings, "effort": effort, "status": "working", "host": host_name(),
        "boot_id": boot_id(), "updated": now(), "turns": "1", "preamble": "1",
    }
    # Merged into the launch dict itself, so the caller's fields are on the
    # record's very first write and cannot be lost to a later failure.
    launch.update(stamp or {})
    if seat_id is None:
        rec_id = str(uuidlib.uuid4())
        meta_set(rec_id, {"uuid": rec_id, "now": "", "note": "", "created": now(), "attempts": 1,
                          "history": [], **launch})
    else:
        # A re-fill is a genuinely new session: clear the previous occupant's
        # `now` line (the orchestrator's `note` is kept), keep the seat id, its
        # `created`, and every pipeline-owned field the launch dict omits. The
        # legacy codex fields go too — the new occupant is a claude session.
        rec_id = seat_id
        history = list(prev["history"]) if prev else []
        if prev and (prev["current"] or prev["short"]):
            entry = {"current": prev["current"], "short": prev["short"], "status": prev["status"],
                     "ticket": str(prev.get("ticket") or ""), "ended": now()}
            # A retirement erases the status it replaced (`retire` writes
            # `retired` over the terminal one), so the pipeline's `retired_from`
            # stamp — and the note explaining it — are the only durable evidence
            # that this occupant failed. The outage streak reads them off history
            # entries exactly as off records; drop them and the failure cap can
            # never be reached for the retire-then-respawn cycle it exists for.
            for k in ("retired_from", "note"):
                if prev.get(k):
                    entry[k] = str(prev[k])
            history.append(entry)
        # The predecessor's run and board binding belonged to ITS run: board-bind
        # re-stamps the new occupant (`lane` and `role` describe the seat and stay).
        # `board_dispatch` is per-OCCUPANT, like the run binding beside it: a seat
        # a dispatcher once launched, re-filled by hand, would otherwise still
        # read as dispatched — and the board client refuses a dispatched seat
        # whose bind never lands. A dispatched re-fill re-stamps it, so the drop
        # skips anything this launch supplies (meta_set removes AFTER it merges).
        # `board_detached` goes with them for the same reason: it records that
        # the board refused a lifecycle call on the PREDECESSOR's run, and a
        # seat that outlived that refusal is not detached — it is unbound, and
        # the next bind decides. Left behind, the stamp would hide the new
        # occupant from every registry scan on the machine.
        drop = ("pending_short", "engine", "pid", "event_log", "run_id", "run_bearer", "fence",
                "bind_confirmed", "nonce", "run_ended_at", "ended_run_id", "ticket", "board", "board_dispatch",
                "board_detached", "closure_package", "retired_from", "relayed_comment",
                "sweep_recoveries")
        meta_set(rec_id, {**launch, "now": "", "attempts": (prev["attempts"] if prev else 0) + 1,
                          "history": history[-10:]},
                 remove=tuple(k for k in drop if k not in launch))
    polled = poll_uuid(short)
    if not polled or not UUID_RE.match(polled[0]):
        meta_set(rec_id, {"status": "error", "pending_short": short, "updated": now()})
        sys.stderr.write("sminos: %s: session %s produced no usable session uuid; record %s kept "
                         "(status=error, pending_short)\n" % (verb, short, rec_id[:8]))
        sys.exit(1)
    uuid, state, runcwd = polled
    if seat_id is None:
        # Promote the provisional record to the first session's uuid — the
        # pipeline resolves seats by that filename prefix. The rename is atomic;
        # do it under .metalock so it can't race a concurrent meta_set on either
        # path, and merge ONLY the fields we now know — never replay empties over
        # a `now`/`note` a first-turn `sminos status` may have written to prov.
        with open(os.path.join(root(), ".metalock"), "a") as _lf:
            fcntl.flock(_lf, fcntl.LOCK_EX)
            try:
                if rec_id != uuid and not os.path.exists(meta_path(uuid)):
                    os.replace(meta_path(rec_id), meta_path(uuid))
                elif rec_id != uuid:
                    os.unlink(meta_path(rec_id))
            finally:
                fcntl.flock(_lf, fcntl.LOCK_UN)
        rec_id = uuid
        meta_set(rec_id, {"uuid": rec_id, "current": uuid, "cwd": runcwd or cwd, "updated": now()})
    else:
        meta_set(rec_id, {"current": uuid, "cwd": runcwd or cwd, "host": host_name(),
                          "boot_id": boot_id(), "updated": now()})
    project = seat_project({"cwd": runcwd or cwd, "group": group})
    try:
        # Bound to the session the harness names for this launch, unless its
        # own SessionStart bound it already; claimed unless it claimed.
        if records.bind(launch_id, uuid) == uuid:
            records.claim(launch_id, uuid)
    except (OSError, LockBusy) as e:
        warn("the record of session %s could not be claimed: %s" % (uuid[:8], e))
    if project is not None:
        ensure_record(project, uuid, reload_seat(rec_id))
    # The session already runs, so a failed append does not fail the spawn: an
    # exit 1 would make a dispatcher release the run and leave the worker
    # running unbound. Each event is attempted on its own, and each one that
    # fails is named loudly after the banner with what it loses.
    log_failed = []

    def record(what_is_lost, p, session, kind, **fields):
        try:
            lifecycle(p, session, kind, **fields)
        except LogWriteFailed as e:
            log_failed.append("%s — %s" % (e, what_is_lost))

    if prev and prev["current"] and prev["current"] != uuid:
        record("the displaced session %s stays a member until a reading verb finds it no longer runs"
               % prev["current"][:8], seat_project(prev), prev["current"], "retired", by=by, reason="replaced")
    record("the seat re-joins its project on the next reading verb, but its spawner (by %s) is not recorded"
           % (by or "the operator"), project, uuid, "joined",
           **joined_fields(alias, "seat", runcwd or cwd, worktree or "", role or "", rec_id, by, "seat",
                           session=uuid))
    if brief:
        record("its in-charge line (%s) is not recorded" % brief, project, uuid, "in-charge", text=brief, source="set")
    status = "working"
    if state in TERMINAL:
        # Don't blindly claim working — a fast first turn may already be over.
        status = status_for_state(state)
        meta_set_if(rec_id, {"status": status, "updated": now()}, same_gen(current_gen(rec_id)),
                    reply=(uuid, state, alias))
    # The watcher's guard is the generation as of NOW — read while the lifecycle
    # lock is still held, right after our own writes; never re-read after the wait.
    guard = same_gen(current_gen(rec_id))
    unlock(locks)
    if wait:
        status = finish_turn(rec_id, short, alias, uuid, guard)
    wt = ("  worktree=%s (branch worktree-%s)" % (runcwd, re.sub(r"[^a-zA-Z0-9._-]", "-", worktree))) if worktree else ""
    if verb == "spawned" and seat_id is not None:
        verb = "re-filled"
    print("seat %s: %s/%s  [%s / %s]  status=%s%s  (reply: sminos reply %s)" % (
        verb, group, alias, short, rec_id, status, wt, short), flush=True)
    if wait:
        print_reply_block(rec_id)
    for failure in log_failed:
        warn("%s completed, but %s" % ("fill" if verb == "filled" else "spawn", failure))


def spawn_provenance(settings, merged):
    """A spawned session's provenance (sminos_records), fixed at its launch:
    - for a desk member (a desk RPC's spawn, desk_member): owned by them,
      their principal, origin `maws` naming them the requester;
    - from inside a session: its record's owners, proofs, principal and
      inference copied, origin `sminos-spawn` naming it, provisional when
      its record is (or when it has none);
    - from an operator's terminal: the machine's owners, origin
      `sminos-spawn`.
    A seat launched with settings of its own runs on them: its inference is
    the merged launch file (`merged`), never its content. Otherwise the
    spawner's slot, or the parent's inference, stands."""
    records = records_module()
    route = {"kind": "route", "settingsRef": merged} if settings else None
    member = desk_member()
    caller = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if member:
        return {**records.default_provenance("launch"), "origin": {"kind": "maws", "requester": member},
                "owners": [member], "ownersProof": desk_proof(), "principal": member,
                "inference": route or records.slot()}
    if UUID_RE.fullmatch(caller):
        parent = records.read(caller) or records.default_provenance()
        return {**{k: parent[k] for k in records.PROVENANCE}, "origin": {"kind": "sminos-spawn", "spawnerSession": caller},
                "inference": route or parent["inference"], "source": "launch" if records.is_final(parent) else "default",
                "basis": "launch"}
    return {**records.default_provenance("launch"), "origin": {"kind": "sminos-spawn"},
            "inference": route or records.slot()}


def cmd_spawn(a):
    """Start a session in the working directory's project (or --cwd's), as a
    seat, recorded as joined by its spawner: a sibling, never a child."""
    alias = a.alias
    if not valid_name(alias):
        die("bad alias: %s" % alias)
    if alias in ("human", "all"):
        die("the alias '%s' is reserved" % alias)
    cwd = cwd_or_die(a.cwd, "spawn")
    # The group is the seat's namespace on this machine: its alias is unique in
    # it and its lifecycle lock is keyed by it. It derives from the cwd's
    # owning repository, as it always did without --group.
    group = derive_group(cwd)
    locks = lock_names([seat_key(group, alias)])
    # Read under the lock: whether the seat is filled/refillable is only true as
    # of now, not as of any earlier read.
    existing = next((s for s in seats(group) if s["alias"] == alias), None)
    if existing:
        live = state(existing)
        if live in FILLED:
            die("seat %s/%s is filled (%s) — message it with sminos send" % (group, alias, live), EXIT_UNKNOWN)
        if peer_for_session(existing["current"]):  # a retired seat whose session still runs
            die("seat %s/%s: the previous occupant (session %s) still answers — use sminos resume, or "
                "stop it first" % (group, alias, existing["current"][:8]), EXIT_UNKNOWN)
        if existing["engine"] == "codex" and existing["status"] in ("working", "blocked"):
            die("seat %s/%s is a legacy codex-CLI worker still marked %s — retire it before re-filling" % (
                group, alias, existing["status"]), EXIT_UNKNOWN)
        # vacant / stopped / gone / retired → re-fill this very seat, keeping its
        # id and the seat-describing pipeline fields. The board pipeline's
        # retire-then-respawn of a deterministic alias (review-pr-<n>) lands
        # here instead of erroring.
    settings = env_default(a.settings, "DAEMON_CLAUDE_SETTINGS")
    effort = env_default(a.effort, "DAEMON_CLAUDE_EFFORT")
    if existing:
        # Definition fields change only when EXPLICITLY given (argparse default
        # None keeps the seat's own); task/model/settings/effort/cwd/worktree are
        # per-fill and always come from this call.
        role = a.role if a.role is not None else existing["role"]
        brief = a.brief if a.brief is not None else existing["brief"]
    else:
        role, brief = a.role or "", a.brief or ""
    spawn_fresh(existing["seat_id"] if existing else None, alias, group, role, brief,
                a.task, cwd, a.worktree or "", a.model or "", settings, effort, a.wait, locks, "spawned",
                stamp=parse_stamps(a.stamp), permission_mode=a.permission_mode)


def cmd_seat_add(a):
    if not valid_name(a.group):
        die("bad group name: %s" % a.group)
    if not valid_name(a.alias):
        die("bad alias: %s" % a.alias)
    if a.alias in ("human", "all"):
        die("the alias '%s' is reserved" % a.alias)
    session = a.session or ""
    if session and not UUID_RE.match(session):
        die("--session must be a session uuid (8-4-4-4-12 hex): %s" % session)
    locks = lock_names([seat_key(a.group, a.alias)])
    existing = [s for s in seats(a.group) if s["alias"] == a.alias]
    if existing and session and session != existing[0]["current"]:
        # Repointing a seat is how a record forgets which process it describes.
        # If the current occupant is still live, that process would keep
        # running with nothing in the fleet naming it — unstoppable by
        # retire/remove and invisible to every view.
        peer = peer_for_session(existing[0]["current"])
        if peer:
            unlock(locks)
            die("seat %s/%s still holds a live session (%s, pid %s) — repointing it would strand "
                "that process outside the fleet; retire or remove the seat first"
                % (a.group, a.alias, existing[0]["current"][:8], peer.get("pid")),
                EXIT_UNKNOWN)
    # A registered session's short is whatever the harness shows for it right
    # now (a `seat add --session` seat was never spawned by sminos, so nothing
    # else records it); absent a row it is cleared, never left stale.
    row = agent_row(session_id=session) if session else None
    short = str((row or {}).get("id") or "")
    if existing:
        s = existing[0]
        seat_id = s["seat_id"]
        fields = {"role": a.role if a.role is not None else s["role"],
                  "brief": a.brief if a.brief is not None else s["brief"], "updated": now()}
        if session:
            fields.update({"current": session, "short": short, "status": "idle",
                           "host": host_name(), "boot_id": boot_id()})
        meta_set(seat_id, fields)
    else:
        seat_id = session if session else str(uuidlib.uuid4())
        if os.path.exists(meta_path(seat_id)):
            die("a seat record for session %s already exists (%s/%s)" % (
                session, meta_get(seat_id, "group"), meta_get(seat_id, "alias") or meta_get(seat_id, "name")), EXIT_UNKNOWN)
        meta_set(seat_id, {
            "uuid": seat_id, "current": session, "short": short, "name": a.alias, "alias": a.alias,
            "group": a.group, "role": a.role or "",
            "brief": a.brief or "", "task": "", "now": "", "note": "", "cwd": os.getcwd(), "worktree": "",
            "model": "", "settings": "", "effort": "", "status": "idle" if session else "vacant",
            "host": host_name() if session else "", "boot_id": boot_id() if session else "",
            "created": now(), "updated": now(), "turns": "0", "preamble": "1", "attempts": 1, "history": []})
    if session:
        # The session joins as this seat; a session the seat held before is
        # displaced, as by a fill.
        if existing and existing[0]["current"] and existing[0]["current"] != session:
            lifecycle(seat_project(existing[0]), existing[0]["current"], "retired", by=caller_alias(),
                      reason="replaced")
        join_seat(reload_seat(seat_id), by=caller_alias())
    unlock(locks)
    print("seat %s/%s %s (%s)" % (a.group, a.alias, "updated" if existing else "added",
                                  ("session: " + session) if session else "vacant"))


def legacy_codex_refusal(s):
    return ("seat %s/%s is a legacy codex-CLI worker; its resume path was retired — "
            "retire or remove the seat" % (s["group"], s["alias"]))


def refuse_codex(s):
    if s["engine"] == "codex":
        die(legacy_codex_refusal(s), EXIT_UNKNOWN)


def cmd_fill(a):
    s0 = resolve_seat(a.seat)
    refuse_codex(s0)
    locks = lock_seat(s0)
    # Re-load under the lock and act on the fresh values: between resolve and
    # lock the seat could have been re-filled or retired.
    s = reload_seat(s0["seat_id"])
    if s is None:
        unlock(locks)
        die("seat %s/%s vanished before the fill could start" % (s0["group"], s0["alias"]), EXIT_UNKNOWN)
    refuse_codex(s)
    live = state(s)
    if live in FILLED:
        die("seat %s/%s is filled (%s) — use sminos send" % (s["group"], s["alias"], live), EXIT_UNKNOWN)
    if peer_for_session(s["current"]):  # a retired seat whose session still runs
        die("seat %s/%s: the previous occupant (session %s) still answers — use sminos resume, or stop it "
            "first" % (s["group"], s["alias"], s["current"][:8]), EXIT_UNKNOWN)
    if a.resume:
        if not s["current"]:
            die("seat %s/%s has no session to resume — fill it fresh (without --resume)" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        warn_resume_flags(a)
        try:
            resume_session(s, a.task, a.wait, locks, verb="filled")
        except ResumeRefused as e:
            die(e.message, e.code)
        return
    settings = a.settings if a.settings is not None else (s["settings"] or os.environ.get("DAEMON_CLAUDE_SETTINGS", ""))
    effort = a.effort if a.effort is not None else (s["effort"] or os.environ.get("DAEMON_CLAUDE_EFFORT", ""))
    model = a.model if a.model is not None else s["model"]
    # The seat's cwd is already the worktree path when it had one, so no
    # --worktree on a re-fill: the fresh session runs where the seat lives.
    cwd = cwd_or_die(s["cwd"], "fill")
    spawn_fresh(s["seat_id"], s["alias"], s["group"], s["role"], s["brief"],
                a.task, cwd, "", model, settings, effort, a.wait, locks, "filled")


# ------------------------------------------------------------ resume / send


def warn_resume_flags(a):
    if any(getattr(a, k, None) is not None for k in ("model", "settings", "effort")):
        sys.stderr.write("sminos: a resumed background session keeps its saved options; "
                         "--model/--settings/--effort ignored (use fill without --resume to change them)\n")


def resume_session(s, msg, wait, locks=None, verb="resumed", quiet=False, on_launched=None):
    """Process-level continuation of a seat's session.

    A live current turn is stopped first (`claude stop`, then a bounded wait
    until the harness row is no longer running and no peer socket answers —
    resuming while the old process still runs makes the harness start a copy,
    so a stop that did not take is refused loudly). Then exactly
    `claude --bg --resume <current> <msg>` runs the session in the background
    under the same id, in the seat's recorded cwd (which must still exist — an
    unattended worker is never launched somewhere else; `fill` fresh with a
    valid --cwd is the recourse), with THIS process's environment (gateway
    scrub applied per the seat's recorded route): the board pipeline prefixes
    the call with its run credentials and needs a fresh process to carry them —
    a socket frame cannot. NO other flag rides the resume: a background session
    keeps its saved options (-n, --permission-mode, --model, --settings,
    --effort), and any flag makes the harness start a COPY (observed live,
    v2.1.257). ONE resume per seat at a time (flock, released when this process
    dies). If the banner says a copy started, or the harness reports a
    different session id, the copy is stopped, the record is left untouched,
    and the command fails loudly.

    `on_launched`, when given, is called once the message is in a launched
    process — confirmed, or uncertain because no session id came back — and
    before any wait: `send` settles its delivery record there. At the same
    point a seat whose session was retired re-joins the project's family.
    """
    def launched():
        # The delivery settles first: a failed re-join (LogWriteFailed) must
        # not leave a launched message owed, to be pushed again. On a fan-out
        # (`quiet`, from deliver_next) the message is in a launched process, so
        # the outcome stands and the fan-out goes on: the failure is a warning.
        if on_launched:
            on_launched()
        try:
            join_seat(s, by=caller_alias())
        except LogWriteFailed as e:
            if not quiet:
                raise
            warn("%s/%s was resumed with the message, but %s" % (s["group"], s["alias"], e))

    if s["engine"] == "codex":
        raise ResumeRefused(legacy_codex_refusal(s))
    if locks is None:
        locks = lock_seat(s, refusal=ResumeRefused if quiet else None)
        fresh = reload_seat(s["seat_id"])
        if fresh is None:
            unlock(locks)
            raise ResumeRefused("seat %s/%s vanished before the resume could start" % (s["group"], s["alias"]))
        s = fresh
        if s["engine"] == "codex":
            raise ResumeRefused(legacy_codex_refusal(s))
    if not s["current"]:
        raise ResumeRefused("seat %s/%s is vacant — fill it with: sminos fill %s/%s \"<task>\"" % (
            s["group"], s["alias"], s["group"], s["alias"]), EXIT_UNKNOWN)
    # Where the engine keeps its session now (a /cd or EnterWorktree moved it), else where it was spawned.
    cwd = os.path.abspath(os.path.expanduser(seat_cwd(s)))
    if not os.path.isdir(cwd):
        raise ResumeRefused("resume of %s/%s: cwd does not exist or is not a directory: %s" % (
            s["group"], s["alias"], cwd), EXIT_USAGE)
    lock_path = os.path.join(root(), s["seat_id"] + ".resume.lock")
    lf = open(lock_path, "a+")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lf.seek(0)
        holder = lf.read().strip()
        raise ResumeRefused("a send/resume of %s/%s is already in flight%s — not starting a twin" % (
            s["group"], s["alias"], (" (%s)" % holder) if holder else ""), 1)
    lf.seek(0)
    lf.truncate()
    lf.write("pid %d since %s" % (os.getpid(), now()))
    lf.flush()
    cur = s["current"]
    agents_refresh()
    row = harness_row(s)
    stop_short = ""
    if row and normalize_state(row) in ("working", "blocked", "done", "done-blocked") and row.get("id"):
        # Release the live turn (idempotent — harmless if already stopped). A
        # row is host-local by construction; only a RECORDED short is gated on
        # the record's host identity, because shorts are reusable across boots.
        stop_short = row["id"]
    elif not row and running_now(cur) and s["short"] and identity_local(s["host"], s["boot_id"], cur):
        # Its process runs (the engine's record), whether or not its inbox
        # answers: the recorded short is the turn to release.
        stop_short = s["short"]
    if stop_short:
        if not claude_stop(stop_short):
            raise ResumeRefused("claude stop %s failed for %s/%s — not resuming over a turn that may still be running" % (
                stop_short, s["group"], s["alias"]), 1)
        if not wait_stopped(s, stop_short, cur):
            raise ResumeRefused("the current turn of %s/%s (%s) is still running %ss after claude stop — not launching a "
                "resume (it would start a copy)" % (s["group"], s["alias"], stop_short,
                                                    os.environ.get("SMINOS_STOP_TIMEOUT", "30")), 1)
    elif running_now(cur):
        raise ResumeRefused("the session of %s/%s (%s) still runs, and there is no turn of it sminos can stop (no "
                            "harness row, no recorded short) — not launching a resume (it would start a copy)"
                            % (s["group"], s["alias"], cur[:8]), 1)
    prev_status = s["status"]
    short, banner = run_claude_bg(["--bg", "--resume", cur, msg], cwd, s["settings"])
    if not short:
        meta_set(s["seat_id"], {"status": "error", "updated": now()})
        raise ResumeRefused("resume failed — did not launch or produced no background id: %s" % banner, 1)

    def copy_started(copy_id):
        claude_stop(short)
        meta_set(s["seat_id"], {"status": prev_status, "updated": now()})
        raise ResumeRefused("resume of %s/%s started a COPY (%s) — the session %s was still running or the harness refused "
            "to continue it; the copy was stopped and the record left untouched. Use sminos send for a "
            "live seat." % (s["group"], s["alias"], copy_id[:8], cur[:8]), 1)

    m = re.search(r"started a copy as ([0-9a-f]+)", banner)
    if m:
        copy_started(m.group(1))
    polled = poll_uuid(short)
    if not polled:
        meta_set(s["seat_id"], {"status": "error", "pending_short": short, "updated": now()})
        launched()  # launched with the message: delivery is uncertain, not failed
        if quiet:
            unlock(locks)
            return "woken?"
        raise ResumeRefused("resume: session %s produced no usable session uuid; kept previous current (recover via pending_short)" % short, 1)
    uuid, state, _cwd = polled
    if uuid != cur:
        copy_started(uuid)
    launched()
    turns = int(s["turns"] or "0") + 1
    # model/settings/effort stay as recorded at spawn/fill: the resumed session
    # runs on its saved options, whatever this call was passed.
    meta_set(s["seat_id"], {"current": cur, "short": short, "host": host_name(), "boot_id": boot_id(),
                            "status": "working", "updated": now(), "turns": str(turns)}, remove=("pending_short",))
    status = "working"
    if state in TERMINAL:
        status = status_for_state(state)
        meta_set_if(s["seat_id"], {"status": status, "updated": now()}, same_gen(current_gen(s["seat_id"])),
                    reply=(uuid, state, s["alias"]))
    # Snapshot the generation while the lifecycle lock is still held, right
    # after our writes; the watcher never re-reads it after the wait.
    guard = same_gen(current_gen(s["seat_id"]))
    unlock(locks)
    if wait:
        status = finish_turn(s["seat_id"], short, s["alias"], uuid, guard)
    if quiet:
        return "woken"
    print("%s %s/%s  [%s / %s]  via --bg --resume  status=%s  turns=%d" % (
        verb, s["group"], s["alias"], short, s["seat_id"], status, turns))
    if wait:
        print_reply_block(s["seat_id"])


def cmd_resume(a):
    s = resolve_seat(a.seat)
    warn_resume_flags(a)
    try:
        resume_session(s, a.msg, a.wait)
    except ResumeRefused as e:
        die(e.message, e.code)


def default_from(explicit):
    """The sender identity for send and say.

    The harness exports CLAUDE_CODE_SESSION_ID to Bash tools, so an AGENT is
    identified by it: the alias of the seat whose `current` is that session,
    else the alias it goes by in the working directory's project (held_alias:
    its harness name unless that is a made-up one the log already holds
    another alias for), else `session:<id8>`.
    An agent may not claim to be the operator: `--from human` with a session id
    in the environment is refused. Without a session id (a real terminal) the
    default stays `human`."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        return explicit or "human"
    if explicit == "human":
        die("--from human is refused inside a Claude session (CLAUDE_CODE_SESSION_ID is set): an agent is "
            "never the operator — omit --from, or name your seat", EXIT_UNKNOWN)
    if explicit:
        return explicit
    for s in seats():
        if s["current"] == sid:
            return s["alias"]
    peer = next((r for r in peer_records() if r.get("sessionId") == sid), None)
    project = caller_project()
    held = own_alias(_own_events(project, sid), sid) if project is not None else ("", "")
    return held_alias(*held, peer, sid, shadowing(project, sid))[0] or "session:%s" % sid[:8]


def wait_socket_turn(s, marker, was_idle, guard):
    """After a socket delivery: wait (bounded) for EVIDENCE the message landed,
    then wait for the turn to end. The evidence is the marker in the target's
    transcript; a busy harness row counts ONLY if the seat was idle when we sent
    (a fresh turn started) — if it was already busy, a busy row proves nothing
    about OUR message, so we require the marker. No evidence within the bound is
    a failed wait, not a silent one: nothing is printed as a reply."""
    cur = s["current"]
    deadline = time.time() + float(os.environ.get("SMINOS_ACK_TIMEOUT", "120"))
    seen = False
    while time.time() < deadline:
        if transcript_contains(cur, marker):
            seen = True
            break
        if was_idle:
            agents_refresh()
            row = harness_row(s)
            if row and normalize_state(row) in ("working", "blocked"):
                seen = True
                break
        time.sleep(poll_interval())
    if not seen:
        sys.stderr.write("sminos: no evidence that %s/%s received the message within the ack window "
                         "(no transcript marker%s) — not waiting for a reply\n" % (
                             s["group"], s["alias"], "" if was_idle else ", and it was already busy at send time"))
        sys.exit(1)
    agents_refresh()
    row = harness_row(s)
    short = (row or {}).get("id") or s["short"]
    if not short:
        return "idle"
    return finish_turn(s["seat_id"], short, s["alias"], cur, guard)


WAKE_POINTER = 'wake was folded into send — sminos send <seat> "<msg>" [--wait] [--from F]'


def cmd_wake(_a):
    die(WAKE_POINTER)


def compose_frame(sender, msg_id, msg, label=""):
    """Every delivery — socket, resume, codex queue — opens with this line; the
    id is what `--wait` looks for in the target's transcript. `label` is what
    follows the sender (sender_labels)."""
    return "[sminos message from %s%s id=%s]\n%s" % (sender, label, msg_id, msg)


def send_to_seat(s0, text, msg_id, wait, record=None, session="", sender=""):
    """Deliver a frame to one seat under its lifecycle lock. The lock covers
    target selection, the socket delivery, and the status write, so a
    concurrent fill/resume/retire cannot slip between them. A live seat takes
    the frame (push_live: the owner's through its bridge, a peer's through its
    inbox socket) and is recorded
    `working`; a stopped one is
    resumed with the frame as its message; vacant, retired, and gone seats
    are refused, pointing at the verb that can reach them. Given `session`,
    the one the name bound (find_target), a seat that no longer holds it is
    refused.

    `record(seat)`, when given, appends the message to the seat's project log
    once the seat is known reachable and returns its SendDelivery (or None
    when the seat has no project): the push then carries every earlier event
    of the same writer still owed to the seat, in order, and the delivery
    record is settled on sent, woken, or uncertain and noted as failed
    otherwise — so a send that dies on the way is the daemon's to retry. A
    held send (SendDelivery.held: on a cut-over machine an operator's, which
    the uplink delivers on the endpoint's verdict, or one behind an event the
    revocation set cannot clear) is recorded and pushed nothing."""
    refuse_codex(s0)
    locks, s = locked_fresh(s0, "send", session)
    refuse_codex(s)
    ref = "%s/%s" % (s["group"], s["alias"])
    # ONE liveness probe (pid alive AND socket answers) decides both the word
    # and the route: a second probe could see a session come up and send a
    # live seat to a resume, which stops and relaunches its turn.
    peer = peer_for_session(s["current"]) if needs_probe(s) else None
    st = seat_state(s, peer)
    if st in ("vacant", "retired"):
        die('seat %s is %s — fill it with: sminos fill %s "<task>"' % (ref, st, ref), EXIT_UNKNOWN)
    if st == "gone":
        die('seat %s is gone — no transcript for its session on this machine; sminos fill %s "<task>" '
            "or sminos retire %s" % (ref, ref, ref), EXIT_UNKNOWN)
    if not peer and st in FILLED:
        # Its process runs (the engine's record): a resume would start a copy
        # of the running session, so nothing is sent.
        die(quiet_inbox_refusal(ref), EXIT_UNKNOWN)
    delivery = record(s) if record else None
    if delivery and (delivery.held or not delivery.queue):
        # A concurrent deliverer pushed it between the append and our lock, or
        # it is held (O12 M6: a person's words the uplink delivers on the
        # endpoint's verdict, or behind an event the revocation set cannot
        # clear): no push here, but --wait still waits on this message's id.
        row = harness_row(s)
        was_idle = (normalize_state(row) not in ("working", "blocked")) if row else (
            not peer or peer.get("status") != "busy")
        guard = same_gen(current_gen(s["seat_id"]))
        if delivery.held:
            delivery.recorded_owed(s["alias"])
        else:
            delivery.release()
        unlock(locks)
        if not delivery.held:
            print("sent to %s (delivered by a concurrent delivery)" % ref, flush=True)
        if wait:
            wait_socket_turn(s, msg_id, was_idle, guard)
            print_reply_block(s["seat_id"])
        return
    settle = delivery.settle if delivery else None

    def resume(locks):
        try:
            resume_session(s, delivery.payload(False) if delivery else text, wait, locks,
                           verb="sent to", on_launched=settle)
        except ResumeRefused:
            if delivery:
                delivery.fail()
            raise

    if not peer:
        resume(locks)
        return
    sock = socket_path_of(peer)
    row = harness_row(s)
    # Idle-at-send: from the harness row when there is one; with no row, from
    # the peer record's own status — never from normalising an empty state.
    was_idle = (normalize_state(row) not in ("working", "blocked")) if row else (peer.get("status") != "busy")
    try:
        if delivery:
            control_module().push_live(peer, s["current"], delivery.payload(True), delivery.queue[-1],
                                       delivery.project.id)
        else:
            send_frame(sock, text, sender)
    except SendFailed as e:
        if e.phase == "before":
            # Nothing reached the peer. A session that exited between the
            # liveness check and the write is resumed; one whose process
            # still runs (its record, read again) is not: a resume would
            # start a copy of it.
            if running_now(s["current"]):
                if delivery:
                    delivery.fail()
                unlock(locks)
                die(quiet_inbox_refusal(ref), EXIT_UNKNOWN)
            warn("inbox socket delivery to %s failed before the frame was written (%s); resuming instead" % (ref, e))
            resume(locks)
            return
        if delivery:
            delivery.settle()  # uncertain after a write: never pushed again
        unlock(locks)
        die("delivery to %s is UNCERTAIN — the frame was written but the close-out failed (%s). Not "
            "resuming and not re-sending id=%s; check the seat with sminos reply/attach before retrying." % (
                ref, e, msg_id), 1)
    if delivery:
        delivery.settle()
    wrote = meta_set_if(s["seat_id"], {"status": "working", "updated": now()}, same_gen(s["gen"]))
    # The watcher's guard: the generation right after our write, read while
    # the lifecycle lock is still held.
    guard = same_gen(current_gen(s["seat_id"]))
    unlock(locks)
    if not wrote:
        warn("record of %s changed during delivery; status left as is" % ref)
    print("sent to %s" % ref, flush=True)
    if wait:
        wait_socket_turn(s, msg_id, was_idle, guard)
        print_reply_block(s["seat_id"])


CODEX_PREFIX = "codex:"
CODEX_QUEUED_RE = re.compile(r"Queued message ([^\s.]+) for thread ([^\s.]+)")


def codex_queue_send(target, text):
    """Deliver `text` to a Codex thread through Codex's durable message queue.

    `codex queue --thread <id|exact name>` writes one row to the queue every
    Codex app-server shares (~/.codex/queue_1.sqlite); the process hosting the
    thread reads it BETWEEN turns — at once when the thread is idle (its host
    polls every 10 s), after the current turn when it is busy, at the next
    resume when nothing hosts it. That is the only door into a Codex thread
    from outside its process (a desktop-app thread has no reachable socket),
    and it never loses a message, so unlike the inbox path this does not
    refuse a target that is not live — it parks the message. The thread must
    already be on disk (a session that has not finished its first turn is
    refused as unknown).

    Returns (thread_id, queued_id) on success; ("", "") when codex knows no
    such thread; dies on any other codex failure.
    """
    if not shutil.which("codex"):
        return "", ""
    try:
        p = subprocess.run(["codex", "queue", "--thread", target, "--message", text],
                           capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001 — a launch failure is a delivery failure
        die("codex queue could not run: %s" % e, 1)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        if "No active session found matching" in out or "no rollout found for thread" in out:
            return "", ""
        die("codex queue failed for '%s': %s" % (target, " ".join(out.split())[:400]), 1)
    m = CODEX_QUEUED_RE.search(out)
    return (m.group(2), m.group(1)) if m else (target, "")


def report_codex_queued(tid, qid):
    print("queued for codex thread %s%s — read between turns (idle: within 10s; busy: after the turn; "
          "unhosted: at the next resume)" % (tid, " (%s)" % qid if qid else ""))


def cmd_send(a):
    try:
        _send(a)
    except ResumeRefused as e:
        die(e.message, e.code)


def refuse_wait(target):
    die("--wait needs a seat: '%s' is not one, so there is no record to watch — send without --wait" % target)


class SendDelivery:
    """One `send` through the recipient's delivery record: holds
    delivered/<session>.lock from choosing to settling, and carries, in writer
    order, every event of the sender's writer still owed to the seat up to and
    including this send — an earlier pending one goes first, in the same push.
    On a cut-over machine (O12 M6) an operator's `send` is a person's words
    (words_held): `held`, its sender pushes nothing and releases it at once
    (recorded_owed); the uplink delivers the writer's owed events, this one
    last, on the endpoint's verdict. A session's is checked as every
    deliverer checks (checked): an earlier event signed by a revoked key is
    marked and left out, and one whose signer the unreadable set cannot clear
    holds the send owed (`held` too), for the daemon to deliver in order."""

    def __init__(self, project, session, writer, event):
        self.project, self.session, self.writer, self.event = project, session, writer, event
        self.lock = open(project_path(project, "delivered", reader_key(session) + ".lock"), "a")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.events = log_read(project)
        self.queue = [e for e in _owed(self.events, session, delivered_load(project, session))
                      if e["writer"] == writer and e["seq"] <= event["seq"]]
        self.cursor = cursor_load(project, session)
        self.skipped = []
        self.held = "the endpoint decides its delivery" if words_held(event) else (
            self.checked() if sibling_module("sminos_rl10").cut_over() else None)

    def checked(self):
        """The queue through the revocation set (WordsGate.held), under the
        lock: a revoked event marked (delivered_revoke) and left out, the
        valid ones kept. Why the send stays owed, when an event cannot be
        cleared (fail-closed), else None. A held send's writer is the
        operator's; a session's writer holds no person's words, so nothing
        here is the endpoint's to ask."""
        gate, kept = WordsGate(self.project), []
        for e in self.queue:
            held = gate.held(e, self.session)
            if held == "unchecked":
                return "it waits behind %s, whose signer the revocation set, unreadable, cannot clear" % event_ref(e)
            if held == "unmarked":
                return "it waits behind %s, signed by a revoked key, whose refusal could not be kept" % event_ref(e)
            if held is None:
                kept.append(e)
        self.queue = kept
        return None

    def payload(self, live):
        """The text of the one push. Ordinary delivery's policy applies: an
        @all (`wake`) reaches only the live, so to a stopped member it is
        settled by passing and left out of the resume."""
        self.skipped = [e for e in self.queue if e.get("wake") and not live]
        return "\n\n".join(frame_of(self.project, e, self.events, self.session, self.cursor)
                             for e in self.queue if e not in self.skipped)

    def settle(self):
        for e in self.queue:
            delivered_settle(self.project, self.session, self.writer, e["seq"])
        self.queue = []
        self.release()

    def fail(self):
        # The skipped broadcasts ahead of the first pushed event settle; that
        # event is the one pending.
        for e in self.queue:
            if e in self.skipped:
                delivered_settle(self.project, self.session, self.writer, e["seq"])
                continue
            delivered_fail(self.project, self.session, self.writer, e["seq"])
            break
        self.release()

    def release(self):
        if not self.lock.closed:
            self.lock.close()

    def recorded_owed(self, alias):
        """A held send (`held`) left owed — to the endpoint's verdict, or the
        daemon's next pass: released, said why, and the daemon nudged."""
        self.release()
        print("recorded %s for %s; %s" % (event_ref(self.event), alias, self.held), flush=True)
        nudge_daemon()


class WaitingSend:
    """A `send` whose append waits for its writer's head (waits_for_head):
    held, as a held SendDelivery is — nothing pushed, nothing to release —
    and delivered by the daemon once it is recorded."""

    def __init__(self, project, writer, event):
        self.project, self.writer, self.event = project, writer, event
        self.held, self.queue = waits_line(project, writer), []

    def release(self):
        pass

    def recorded_owed(self, alias):
        print("for %s: %s" % (alias, self.held), flush=True)


def record_send(s, sender, via, text, msg_id):
    """`send` is recorded in the target's project log — `human` from the
    operator, `say` from a session — to the one session it reaches, then
    delivered through that session's delivery record (SendDelivery). A message
    the log cannot hold is not sent: the failure exits non-zero first."""
    if not s["current"]:
        return None
    return record_message(seat_project(s), s["current"], s["alias"], sender, via, text, msg_id)


def record_message(project, session, alias, sender, via, text, msg_id, deliver=True):
    """Append a `send` to the project's log, addressed to one session — from
    a session of another project, copied into that project's log too
    (record_copy) — and, unless the recipient is another machine's to
    deliver, open its SendDelivery. A message the log cannot hold is not
    sent: exit 1 first."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    writer = writer_id(sid or None)
    fields = {"from": sender, "to": [{"session": session, "alias": alias}], "text": text, "msg_id": msg_id}
    if via and via != sender:
        fields["via"] = via
    home = caller_scope() if sid else None
    if home is not None and home.id != project.id:
        fields["from_project"] = home.id  # the sender's own project, where a reply finds it
    try:
        event = log_append(project, writer, "say" if sid else "human", **fields)
        if event["seq"] is None:
            return WaitingSend(project, writer, event)
        if "from_project" in fields:
            record_copy(home, [(project, event)])
        return SendDelivery(project, session, writer, event) if deliver else event
    except OSError as e:
        die("send not delivered: it could not be recorded in %s's log (%s)" % (project.name, e), 1)


def send_to_member(project, m, sender, via, text, msg_id):
    """send to a member that holds no seat here. A remote member's send is
    recorded and owed: its own machine's daemon delivers it. A local one is
    reached while it runs (push_live: the owner's through its bridge, a peer's
    through its inbox socket); a
    session sminos did not spawn is never resumed — it is the human's to
    reopen. A held send (SendDelivery.held: on a cut-over machine an
    operator's, which the uplink delivers on the endpoint's verdict, or one
    behind an event the revocation set cannot clear) is recorded and pushed
    nothing."""
    if not m.local:
        e = record_message(project, m.session, m.alias, sender, via, text, msg_id, deliver=False)
        if isinstance(e, WaitingSend):
            e.recorded_owed(m.alias)
            return
        print("recorded %s for %s on %s — its machine delivers it" % (event_ref(e), m.alias, m.machine))
        nudge_daemon()
        return
    peer = peer_for_session(m.session)
    if not peer:
        die("%s is not live (%s) — a session sminos did not spawn is reached only while it runs; "
            "sminos say records for it" % (m.alias, m.state), EXIT_UNKNOWN)
    delivery = record_message(project, m.session, m.alias, sender, via, text, msg_id)
    if delivery.held:
        delivery.recorded_owed(m.alias)
        return
    if not delivery.queue:
        delivery.release()
        print("sent to %s (delivered by a concurrent delivery)" % m.alias)
        return
    try:
        control_module().push_live(peer, m.session, delivery.payload(True), delivery.queue[-1], project.id)
    except SendFailed as e:
        if e.phase == "after":
            delivery.settle()
            die("delivery to %s is UNCERTAIN — the frame was written but the close-out failed (%s); "
                "do not blindly re-send" % (m.alias, e), 1)
        delivery.fail()
        die("%s went away mid-send (%s) — not live; the message stays owed" % (m.alias, e), EXIT_UNKNOWN)
    delivery.settle()
    print("sent to %s" % m.alias)


def _send(a):
    caller = caller_seat()
    frm = default_from(a.frm)
    msg_id = uuidlib.uuid4().hex[:8]
    text = compose_frame(frm, msg_id, a.msg)
    if a.target.startswith(CODEX_PREFIX):
        if a.wait:
            refuse_wait(a.target)
        # `codex:<id|name>` skips the seat and harness lookups — for a Codex
        # thread whose name happens to collide with an alias.
        raw = a.target[len(CODEX_PREFIX):]
        tid, qid = codex_queue_send(raw, text)
        if not tid:
            die("no codex thread matching '%s'%s" % (
                raw, "" if shutil.which("codex") else " (codex CLI not on PATH)"), EXIT_UNKNOWN)
        report_codex_queued(tid, qid)
        return
    # A genuine match that is ambiguous never falls through to a raw name
    # lookup — that would hide the ambiguity (find_target exits 4 naming it).
    target = find_target(a.target)
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    sender = "human" if not sid else ((caller or {}).get("alias") or default_from(""))
    if target[0] == "seat":
        res = target[1]
        if sid and res["current"] == sid:
            die("you cannot send to yourself")
        send_to_seat(res, text, msg_id, a.wait, record=lambda s: record_send(s, sender, frm, a.msg, msg_id),
                     session=target[2], sender=frm)
        return
    if target[0] == "member":
        project, m = target[1], target[2]
        if a.wait:
            refuse_wait(a.target)
        if sid and m.session == sid:
            die("you cannot send to yourself")
        send_to_member(project, m, sender, frm, a.msg, msg_id)
        return
    if a.wait:
        refuse_wait(a.target)
    # Nothing answers. A name of projects known here is refused saying what
    # they know of it; from inside a project a bare name never reaches past
    # it: another project's member is <project>/<alias> (named in the
    # refusal), and a message to it is recorded in that project's log.
    scope = caller_scope()
    proj, _, rest = a.target.rpartition("/")
    name, _, short = rest.partition("#")
    tiers = project_tiers(proj) if proj else []
    if tiers:
        no_member(a.target, name, short, tiers, at="")
    if scope is not None and not UUID_RE.match(a.target.lower()):
        no_member(a.target, name, short, [scope], () if short else
                  [(p, m) for p, m in match_members(name, "", org_scope(), ids=False) if p.id != scope.id], at="")
    # From no project on a machine not enrolled, the one unrecorded route: a
    # live session that is in no project either (any session in a project
    # answered above, as a member), by its harness name. There is no log for
    # it to be recorded in. On an enrolled machine every session is in a
    # project (its machine's, at least), so the route is never taken there.
    peers = [] if enrollment() is not None else [
        r for r in live_name_holders(a.target) if not (isinstance(r.get("cwd"), str) and r["cwd"] and record_project(r))]
    if len(peers) == 1:
        try:
            send_frame(socket_path_of(peers[0]), text, frm)
        except SendFailed as e:
            if e.phase == "after":
                die("delivery to session '%s' is UNCERTAIN — the frame was written but the close-out failed (%s); "
                    "do not blindly re-send" % (a.target, e), 1)
            die("session '%s' went away mid-send (%s) — not live" % (a.target, e), EXIT_UNKNOWN)
        print("sent to session %s (pid %s)" % (a.target, peers[0].get("pid")))
        return
    if len(peers) > 1:
        die("ambiguous: %d live sessions are named '%s'" % (len(peers), a.target), EXIT_UNKNOWN)
    # Only when NO seat and NO live harness session matched, and only for a
    # thread ID: codex resolves an id in about a second but a NAME by paging
    # through the whole thread history (63 s for 7,000 threads, observed), so a
    # mistyped alias must not pay that — names go through `codex:<name>`.
    codex_here = bool(shutil.which("codex"))
    if codex_here and UUID_RE.match(a.target.lower()):
        tid, qid = codex_queue_send(a.target, text)
        if tid:
            report_codex_queued(tid, qid)
            return
    what = "no seat, live session, or codex thread" if codex_here else "no seat or live session"
    die("%s matching '%s'" % (what, a.target), EXIT_UNKNOWN)


# ------------------------------------------------ reply / sync / status


def cmd_reply(a):
    s = resolve_seat(a.seat)
    print("%s/%s  [%s]  state=%s  turns=%s" % (s["group"], s["alias"], s["seat_id"], state(s), s["turns"]))
    first = (s["task"].strip().splitlines() or [""])[0]
    print("task: %s" % first)
    print("--- latest reply ---")
    cur = s["current"] or s["seat_id"]
    ref = "%s/%s" % (s["group"], s["alias"])
    if s["status"] == "working":
        # A turn is in flight (or a watcher expired on it): the recorded reply
        # file belongs to a PREVIOUS turn — the live truth is the transcript.
        print(transcript_reply(cur, ref) or reply_text(s["seat_id"]) or "(no reply yet)")
    else:
        # The recorded reply can still be stale/empty — the spawn watcher gave
        # up before the first turn finished, or the seat was woken natively and
        # finished a turn no sminos verb ever recorded. A transcript newer than
        # the reply file is that turn, and it wins.
        fresh = transcript_reply(cur, ref) if reply_stale(s["seat_id"], cur) else ""
        print(fresh or reply_text(s["seat_id"]) or transcript_reply(cur, ref) or "(no reply yet)")


def sync_one(s0):
    """Reconcile one seat's mirror status from the harness. Returns one word.

    Runs under the seat's lifecycle lock (BLOCKING — a sync waits for an
    in-flight fill/resume rather than reporting `absent` over a legitimate
    transition) and re-reads the record under it before deciding. Every
    status/reply write is CONDITIONAL on the record's generation, and the reply
    file is written in the same critical section, so a stale finalize can never
    clobber a re-fill, a resume, or a retire. An `idle` record whose harness row
    shows a running turn was woken natively (SendMessage, no sminos write):
    promote it to working. One whose row is terminal but whose transcript is
    newer than its reply file ran a whole natively-woken turn since the last
    sync: re-record the reply so the seat's answer is not the previous turn's.
    """
    if s0["engine"] == "codex" or s0["status"] not in ("working", "blocked", "idle"):
        return "noop"
    locks = lock_seat(s0, blocking=True)
    try:
        s = reload_seat(s0["seat_id"])
        if s is None:
            return "absent"
        if s["engine"] == "codex" or s["status"] not in ("working", "blocked", "idle"):
            return "noop"
        cur = s["current"] or s["seat_id"]
        guard = same_gen(s["gen"])
        agents_refresh()
        if not harness_ok():
            return "live"  # the harness could not be asked: claim nothing
        row = harness_row(s)
        blocked_ended = bool(row and normalize_state(row) == "blocked" and not peer_for_session(cur))
        state = "done-blocked" if blocked_ended else normalize_state(row) if row else ""
        if s["status"] == "idle":
            # An idle seat the harness shows as running NOW was woken natively
            # (SendMessage) with no sminos write. Promote it.
            if row and state in ("working", "blocked"):
                meta_set_if(s["seat_id"], {"status": "working", "updated": now()}, guard)
                return "live"
            # A natively-woken turn can also have STARTED AND ENDED between two
            # syncs: the record never left idle and the reply file still
            # describes the previous turn. The transcript is the only witness.
            if row and state in ("done", "done-blocked", "failed", "stopped") \
                    and reply_stale(s["seat_id"], cur):
                if meta_set_if(s["seat_id"], {"updated": now()}, guard,
                               reply=(cur, "blocked" if state == "done-blocked" else state, s["alias"])):
                    return "idle"
            if blocked_ended and (not os.path.exists(reply_path(s["seat_id"])) or
                                  reply_stale(s["seat_id"], cur)):
                return "idle" if meta_set_if(s["seat_id"], {"updated": now()}, guard,
                                              reply=(cur, "blocked", s["alias"])) else "live"
            return "noop"
        if row is None:
            return "absent"
        state = "done-blocked" if blocked_ended else normalize_state(row)
        if state in ("working", "blocked"):
            return "live"
        if state == "done":
            return "idle" if meta_set_if(s["seat_id"], {"status": "idle", "updated": now()}, guard,
                                         reply=(cur, "done", s["alias"])) else "live"
        if state == "done-blocked":
            # An ended blocked-shape turn: the session is over and resumable; the
            # reply carries the pending question or the harness-prompt marker.
            return "idle" if meta_set_if(s["seat_id"], {"status": "idle", "updated": now()}, guard,
                                         reply=(cur, "blocked", s["alias"])) else "live"
        if state in ("failed", "stopped", "error"):
            return "error" if meta_set_if(s["seat_id"], {"status": "error", "updated": now()}, guard,
                                          reply=(cur, state, s["alias"])) else "live"
        return "live"  # unknown/new harness states: claim nothing, finalize nothing
    finally:
        unlock(locks)


def cmd_sync(a):
    if a.all or not a.seat:
        # --all includes idle seats too, to catch natively-woken ones; a seat
        # that needed no reconciliation (noop) is not printed.
        for s in seats():
            if s["status"] in ("working", "blocked", "idle"):
                word = sync_one(s)
                if word != "noop":
                    print("%s/%s %s" % (s["group"], s["alias"], word))
        return
    print(sync_one(resolve_seat(a.seat)))


def cmd_status(a):
    """A member's one-line status: a `status` event in its own file, which
    every machine reads, and — for a seat — the local `now` line beside it."""
    target = find_target(a.seat)
    line = " ".join(a.line).strip()
    if target[0] == "none":
        die("no seat or member matching '%s'" % a.seat, EXIT_UNKNOWN)
    if target[0] == "member":
        project, m = target[1], target[2]
        if m.local:
            lifecycle(project, m.session, "status", text=line)
        else:
            # Another machine's session file is that machine's to write: the
            # line goes in this caller's own file, and the later ts wins (§3).
            writer = writer_id(os.environ.get("CLAUDE_CODE_SESSION_ID") or None)
            try:
                got = _append(project, writer, [{"kind": "status", "session": m.session, "text": line}])
            except OSError as e:
                die("status of %s not recorded in %s's log: %s" % (m.alias, project.name, e), 1)
            if got and got[0]["seq"] is None:
                print(waits_line(project, writer))
        print("%s now: %s" % (m.alias, line or "(cleared)"))
        return
    s = target[1]
    # The agent's own status line is not a lifecycle write: it must never make
    # the turn's watcher refuse to record the reply (bump=False). Nor may it
    # resurrect a seat a concurrent remove just deleted (create=False).
    if not meta_set(s["seat_id"], {"now": line, "updated": now()}, bump=False, create=False):
        die("seat %s/%s was removed before the status could land" % (s["group"], s["alias"]), EXIT_UNKNOWN)
    if s["current"]:
        lifecycle(seat_project(s), s["current"], "status", text=line)
    print("%s/%s now: %s" % (s["group"], s["alias"], line or "(cleared)"))


# ------------------------------------------------------------ retire / remove


def stop_session(s):
    """Stop the seat's current turn. The short to stop is the CURRENT session's
    harness row when there is one (a `seat add --session` seat recorded none,
    and a recorded short goes stale after a native resume); a row is host-local
    by construction. Only the fallback to the RECORDED short is gated on the
    record's host identity — shorts are host-local and reusable, so a foreign
    one may name an unrelated local session. Legacy codex records have no
    Claude process to stop and remain read-only until removed."""
    if s["engine"] == "codex":
        return
    agents_refresh()
    row = harness_row(s) if s["current"] else None
    if row and row.get("id"):
        claude_stop(row["id"])
    elif s["short"] and identity_local(s["host"], s["boot_id"], s["current"]):
        claude_stop(s["short"])


def worktree_note(s):
    if not s["worktree"]:
        return ""
    return "  NOTE: work is on branch worktree-%s — merge or remove its worktree yourself." % re.sub(
        r"[^a-zA-Z0-9._-]", "-", s["worktree"])


def unlink_seat_files(seat_id):
    """Delete a seat's files under .metalock, so a guarded writer holding the
    same lock sees the record gone (and stands down) rather than racing the
    unlink with its os.replace."""
    with open(os.path.join(root(), ".metalock"), "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            for p in (meta_path(seat_id), reply_path(seat_id), err_path(seat_id),
                      os.path.join(root(), seat_id + ".resume.lock")):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def locked_fresh(s0, verb, session=""):
    """Take the seat's lifecycle locks and re-load the record; (locks, seat).
    Given `session`, the one a name bound (find_target), a seat that no
    longer holds it is refused: an address names a session, and a refill
    after the name was resolved must not put another session in its place."""
    locks = lock_seat(s0)
    s = reload_seat(s0["seat_id"])
    if s is None:
        unlock(locks)
        die("seat %s/%s vanished before the %s could start" % (s0["group"], s0["alias"], verb), EXIT_UNKNOWN)
    if session and s["current"] != session:
        unlock(locks)
        die("no %s: session %s left seat %s/%s, which now holds %s — name the seat to reach whoever holds it" % (
            verb, session[:8], s["group"], s["alias"], s["current"][:8] or "no session"), EXIT_UNKNOWN)
    return locks, s


def cmd_retire(a):
    """Stop one member and record it retired. Nothing it spawned goes with it:
    a spawner is provenance, not a host."""
    target = find_target(a.seat)
    if target[0] == "none":
        die("no seat or member matching '%s'" % a.seat, EXIT_UNKNOWN)
    if target[0] == "seat":
        _retire_one(target[1], a.purge, target[2])
        return
    project, m = target[1], target[2]
    if not m.local:
        die("%s is on %s" % (m.alias, m.machine), EXIT_UNKNOWN)
    if a.purge:
        die("%s holds no seat: there is no record to purge" % m.alias)
    # A session sminos did not spawn: its harness row, if the harness lists
    # it with an id (a background session), is what stops it. An interactive
    # session has none, and runs on in its human's terminal. Either way the
    # retirement names the process it saw, and holds for that process's life
    # (retirement_holds): only a new process — a resume — re-joins it.
    agents_refresh()
    row = agent_row(session_id=m.session)
    stopped = bool(row and row.get("id")) and claude_stop(row["id"])
    proc = session_running(m.session)
    lifecycle(project, m.session, "retired", by=caller_alias(), reason="retire",
              **({"pid": proc.get("pid")} if proc else {}))
    if proc and not stopped:
        print("retired %s (session %s): %s's session keeps running in its terminal; it re-joins when resumed as a "
              "new process" % (m.alias, m.short, m.alias))
    else:
        print("retired %s (session %s; it holds no seat, so nothing is kept)" % (m.alias, m.short))


def _retire_one(s0, purge, session=""):
    locks, s = locked_fresh(s0, "retire", session)
    try:
        stop_session(s)
        if s["engine"] == "codex":
            hint = "legacy codex-CLI worker — no resume path; remove with: sminos remove %s/%s" % (s["group"], s["alias"])
        elif s["current"]:
            hint = 'sminos fill %s/%s --resume "<task>"' % (s["group"], s["alias"])
        else:
            hint = 'sminos fill %s/%s "<task>"' % (s["group"], s["alias"])
        # The record first, then the event: reconciliation re-reads the record
        # under the session file's lock, so it cannot re-join in between.
        if purge:
            unlink_seat_files(s["seat_id"])
        else:
            meta_set(s["seat_id"], {"status": "retired", "updated": now()})
        lifecycle(seat_project(s), s["current"], "retired", by=caller_alias(), reason="retire")
        if purge:
            print("purged %s/%s [%s] from the registry (session transcript left intact)%s" % (
                s["group"], s["alias"], s["seat_id"], worktree_note(s)))
        else:
            print("retired %s/%s [%s] (seat kept; re-fill with: %s)%s" % (
                s["group"], s["alias"], s["seat_id"], hint, worktree_note(s)))
    finally:
        unlock(locks)


def cmd_remove(a):
    locks, s = locked_fresh(resolve_seat(a.seat), "remove")
    try:
        stop_session(s)
        unlink_seat_files(s["seat_id"])
        # A removed seat's session leaves the family with it.
        lifecycle(seat_project(s), s["current"], "retired", by=caller_alias(), reason="retire")
        print("removed %s/%s [%s] (chat history kept)%s" % (s["group"], s["alias"], s["seat_id"], worktree_note(s)))
    finally:
        unlock(locks)


# --------------------------------------------------------------------- views


def view_projects(q, every=False):
    """(projects, fleet): the projects a view shows — the one named; with
    `every`, every project known here; else the caller's (its seat's, or the
    working directory's), and from a directory that is no project, every
    project known here — and whether that is the fleet, every project."""
    if q:
        return [find_project(q)], False
    here = None if every else caller_scope()
    if here is not None:
        return [here], False
    return sorted(known_projects(), key=lambda p: (p.name, p.id)), True


def project_rows(project):
    """A view's rows for a project: its members, newest join first, then the
    seats no member stands for (vacant, retired, replaced)."""
    ms, rest = project_view(project)
    return ms + rest


def short_age(seconds):
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return "%d%s" % (seconds // size, unit)
    return "%ds" % seconds


def state_column(m):
    """The state word; for a member on another machine, its last published
    word, `@<machine>`, and how long ago it was published."""
    if m.local:
        return m.state
    return " ".join(x for x in (m.state or "?", "@" + m.machine,
                                short_age(m.state_age) if m.state_age is not None else "") if x)


LABEL_WIDTH = 36   # a row's `alias [short]` pads to at most this many cells, and is never cut


def comma_list(value):
    return [w for w in (x.strip() for x in str(value).split(",")) if w]


def state_words(value):
    """--state's comma list: each one of STATES."""
    words = comma_list(value)
    bad = [w for w in words if w not in STATES]
    if bad or not words:
        raise argparse.ArgumentTypeError("invalid state %r (each of: %s)" % (",".join(bad) or value, ", ".join(STATES)))
    return words


def list_scope(a):
    """(projects, words, picked): the projects a list reads, the words its
    rows must match, and whether projects were named (so a session in no
    project is none of them). With no filter, the caller's project
    (view_projects). Any filter widens to every project known here before it
    narrows: a project named first (as before), or with --project;
    --machine, --state, --here, --org and words narrow the rows. Under --org
    or --project every argument is a word."""
    args = list(a.args)
    if a.org or a.projects:
        named, words = "", args
    else:
        named, words = (args[0], args[1:]) if args else ("", [])
    if not (named or a.projects or a.machine or a.state or a.org or a.here or words):
        return view_projects("")[0], [], False
    if named:
        return [find_project(named)], words, True
    if a.projects:
        picked = {}
        for q in a.projects:
            p = find_project(q)
            picked.setdefault(p.id, p)
        return list(picked.values()), words, True
    return sorted(known_projects(), key=lambda p: (p.name, p.id)), words, False


def row_matches(m, project, a, words):
    """Whether a row passes list's filters: its machine by prefix (--machine)
    or this machine exactly (--here: `mini` is not `mini2`), its word
    (--state), and every word, case-insensitively, in its alias, short,
    project, repository, branch, in-charge line, status line or title."""
    prefixes = [x.lower() for x in a.machine]
    if (prefixes or a.here) and not ((a.here and m.local)
                                     or any(m.machine.lower().startswith(x) for x in prefixes)):
        return False
    if a.state and m.state not in a.state:
        return False
    if not words:
        return True
    # Its title whatever line won its in-charge: its transcript's here, the
    # one its machine published (Member.title) for another machine's.
    title = (transcript_title(m.session) if m.session else "") if m.local else m.title
    hay = " ".join((m.alias, m.short, project.name if project else "", m.repo, m.branch, m.charge, m.status,
                    title)).lower()
    return all(w.lower() in hay for w in words)


def unprojected_rows(members_known):
    """--here's `(no project)`: a row for every running engine session on
    this machine whose launch directory resolves to no project and that no project
    holds as a member — what the harness's ListAgents shows and no project
    does. A member's record may name a directory of no project (it joined
    where a turn of it ran), so membership is asked, not the directory
    alone. Internal forks and headless runs are none (joinable)."""
    out, seen, internal = [], set(members_known), internal_pids()
    for rec in peer_records():
        sid, cwd = rec.get("sessionId"), rec.get("cwd")
        if not (isinstance(sid, str) and UUID_RE.match(sid) and isinstance(cwd, str) and cwd) or sid in seen:
            continue
        if str(rec.get("pid")) in internal or not joinable(None, rec) or not peer_running(rec):
            continue
        cwd = launch_cwd(sid, fallback=cwd)
        if session_project(sid, cwd) is not None:
            continue
        seen.add(sid)
        repo, branch = repo_branch(cwd)
        updated = rec.get("updatedAt")
        active = (max(0.0, time.time() - updated / 1000.0)
                  if isinstance(updated, (int, float)) and not isinstance(updated, bool) else None)
        title = transcript_title(sid)
        out.append(Member(session=sid, short=sid[:8], alias=str(rec.get("name") or "") or sid[:8],
                          name_source=str(rec.get("nameSource") or "derived"), machine=host_name(), local=True,
                          state=peer_state(rec), state_age=None, charge=title, charge_source="title" if title else "",
                          status="", by="", worktree="", seat=None, kind=str(rec.get("kind") or ""), cwd=cwd,
                          repo=repo, branch=branch, active_age=active))
    return out


# What marks an engine process that serves no session yet: a spare launched
# to be claimed later (`--await-claim`), parked until a host claims it. The
# engine's own peer list leaves such endpoints out; the record's words are
# matched since no field of its own is known to name them.
UNCLAIMED_WORDS = ("spare", "parked")


def engine_facts(rec):
    """What the engine's record of a running session says beyond membership,
    as list --json carries it: its raw status, kind and entrypoint, how long
    since its process started, whether Claude Desktop hosts it, and the name
    it went by last when it was renamed."""
    started = rec.get("startedAt")
    former = rec.get("formerNames")
    last = former[-1] if isinstance(former, list) and former and isinstance(former[-1], dict) else {}
    return {"status": rec.get("status") or None, "kind": rec.get("kind") or None,
            "entrypoint": rec.get("entrypoint") or None,
            "startedAge": max(0.0, time.time() - started / 1000.0)
            if isinstance(started, (int, float)) and not isinstance(started, bool) else None,
            "desktop": rec.get("entrypoint") == "claude-desktop" or bool(rec.get("hostSessionId")),
            "formerName": last.get("name") if isinstance(last.get("name"), str) else None}


def other_live_sessions(shown):
    """--here's last tail: every session of this machine whose inbox listens
    and that no row above shows — the engine's peers that are no member
    (another tool's SDK run, a kind sminos does not join) — as the engine's
    own peer list shows them, the caller, internal forks and unclaimed spares
    left out. [{session, short, name, status, kind, entrypoint, startedAge}]."""
    me, internal, out = os.environ.get("CLAUDE_CODE_SESSION_ID", ""), internal_pids(), []
    for rec in peer_records():
        sid = rec.get("sessionId")
        if not (isinstance(sid, str) and UUID_RE.match(sid)) or sid in shown or sid == me:
            continue
        if str(rec.get("pid")) in internal or any(str(rec.get(k) or "") in UNCLAIMED_WORDS for k in ("kind", "status")):
            continue
        if not peer_live(rec):
            continue
        shown.add(sid)
        out.append({"session": sid, "short": sid[:8], "name": str(rec.get("name") or "") or sid[:8],
                    "member": False, **engine_facts(rec)})
    return out


def row_cells(m, project=None):
    """(columns, the rest) of a list row: `alias [short]`, kind, word,
    @machine, the project (a flat list only), repo@branch; then the
    in-charge line with its age, `· now:` the status, `· by` the spawner,
    `· active` the age of its last activity."""
    label = "%s [%s]" % (m.alias, m.short) if m.short else m.alias
    where = (m.repo + ("@" + m.branch if m.branch else "")) if m.repo else ""
    rec = session_running(m.session) if m.local and m.session else None
    kind = (m.kind or "?") + (" desktop" if rec and engine_facts(rec)["desktop"] else "")
    cells = [label, kind, m.state or "?", "@" + m.machine] + ([project.name] if project else []) + [where]
    rest = []
    if charge_shown(m):
        rest.append("in charge: %s%s" % (charge_shown(m), " (%s)" % short_age(m.charge_age)
                                         if m.charge_age is not None else ""))
    if m.status:
        rest.append("· now: " + m.status)
    if m.by:
        rest.append("· by " + m.by)
    if m.active_age is not None:
        rest.append("· active " + short_age(m.active_age))
    return cells, rest


def print_table_rows(rows):
    """Cells as aligned columns, two spaces in from the margin, as print_rows draws a list's rows."""
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]) - 1)]
    for r in rows:
        print(("  " + "  ".join([c.ljust(w) for c, w in zip(r, widths)] + [r[-1]])).rstrip())


def print_rows(rows):
    """Rows (row_cells) as aligned columns; a column empty on every row is left out."""
    widths = [max(len(cells[i]) for cells, _ in rows) for i in range(len(rows[0][0]))]
    widths[0] = min(widths[0], LABEL_WIDTH)
    for cells, rest in rows:
        parts = [c.ljust(w) for c, w in zip(cells, widths) if w]
        print(("  " + "  ".join(parts + rest)).rstrip())


def subagents_module():
    return sibling_module("sminos_subagents")


def subagents_view(session, stall_minutes=None):
    """(view, scope): a session's subagents (sminos_subagents.Subagents) with
    the engine's word from its bridge when one answers, and the scope the
    view read — its transcript, whether its process runs, where the
    lifecycle came from (`engine` with a bridge, else `disk`). The view's
    notes say what could not be read."""
    V = subagents_module()
    rec = session_running(session)
    tpath = transcript_path(session)
    started = rec.get("startedAt") if rec else None
    started = started / 1000.0 if isinstance(started, (int, float)) and not isinstance(started, bool) else None
    bridge, said, notes = None, "none", []
    if rec is not None:
        b = bridge_module()
        sock = b.endpoint(session)
        if os.path.exists(sock):
            try:
                code, body = b.request(sock, "GET", "/agents", timeout=3)
            except (OSError, http.client.HTTPException) as e:
                code, body = None, str(e)
            if code == 200 and isinstance(body, dict) and body.get("ready") and isinstance(body.get("agents"), list):
                bridge, said = body["agents"], "answered"
            else:
                said = "unreachable"
                notes.append("the session's bridge did not answer (%s): lifecycle is inferred from its transcripts, "
                             "so an agent in a long inference may read as stalled" % (
                                 "HTTP %s" % code if code else body or "no answer"))
        else:
            notes.append("no bridge runs in this session: lifecycle is inferred from its transcripts")
    if not tpath:
        notes.append("no transcript of session %s on this machine (%s): %s" % (
            session[:8], os.path.join(home_dir(), ".claude", "projects"),
            "only the agents its bridge holds are listed" if bridge is not None else "no subagent can be read"))
    notes += peer_notes()
    stall = V.STALL_SECONDS if stall_minutes is None else stall_minutes * 60
    view = V.Subagents(tpath or "", live=rec is not None, started=started, bridge=bridge, stall=stall)
    view.notes[:0] = notes
    scope = {"session": session, "short": session[:8], "transcript": tpath or None,
             "subagentsDir": view.dir, "live": rec is not None, "bridge": said}
    return view, scope


def self_identity():
    """The calling session as `list` names it, or None outside a session:
    {session, short, alias}."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        return None
    return {"session": sid, "short": sid[:8], "alias": caller_alias() or sid[:8]}


def self_line(me):
    return "you: %s [%s]" % (me["alias"], me["short"])


def subagents_session(q):
    """The session `--subagents <member>` names on this machine, or exit 4
    saying why not (a member on another machine keeps its subagents
    there)."""
    if UUID_RE.match(q):
        return q
    target = find_target(q)
    if target[0] == "none":
        # A running session of this machine that is no member: by the engine's name for it, or its short.
        hits = {r["sessionId"] for r in peer_records()
                if isinstance(r.get("sessionId"), str) and UUID_RE.match(r["sessionId"]) and peer_running(r)
                and (r.get("name") == q or r["sessionId"].startswith(q.lower()) and len(q) >= 4)}
        if len(hits) == 1:
            return hits.pop()
        die("no member matching '%s'" % q if not hits else
            "'%s' names %d running sessions here: give its session id" % (q, len(hits)), EXIT_UNKNOWN)
    if target[0] == "seat":
        s = target[1]
        session = target[2] or s.get("current") or ""
        if not session:
            die("%s/%s holds no session" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        return session
    m = target[2]
    if not m.local:
        die("%s runs on %s: its subagents are on that machine's disk (run sminos list --subagents there)" % (
            q, m.machine or "another machine"), EXIT_UNKNOWN)
    return m.session


def subagent_summary_line(session):
    """The one line `list` ends with inside a session that has subagents:
    how many run, cheaply — the bridge's live list, else the turns its
    transcripts leave open in the running process — and where the whole
    view is (`list --subagents`); "" with none."""
    view, scope = subagents_view(session)
    if not view.agents:
        return ""
    c = view.live_summary()
    if c["source"] == "engine":
        said = "%d running" % c["running"] if c["running"] else "none running"
    else:
        said = ("%d with a turn open (read from transcripts)" % c["open"] if c["open"]
                else "none with a turn open (read from transcripts)" if scope["live"] else "none running: the session "
                "runs no process")
    return "subagents: %s — sminos list --subagents" % said


def cmd_subagents(a):
    """`list --subagents [member] [--done N] [--depth N] [--all] [--stall MIN]
    [--json]`: the caller's own session's subagents, or (inspection only)
    another session's on this machine. Text: who you are, the counts at every
    depth, then the live agents as a tree (--all: the ended too; --depth:
    the top levels, a row saying what it folds), and the count of those
    ended; --done N: the N ended last, newest first, each with its outcome.
    --json: {self, scope, counts, agents, notes}, every agent of the tree
    (or the --done list), whatever its state."""
    V = subagents_module()
    me = self_identity()
    member = a.subagents or ""
    if member:
        session = subagents_session(member)
    elif me:
        session = me["session"]
    else:
        die("outside a session, name whose subagents: sminos list --subagents <member>")
    inspection = me is None or session != me["session"]
    if a.depth is not None and a.depth < 1:
        die("--depth is 1 or more")
    if a.done is not None and a.done < 1:
        die("--done is 1 or more")
    view, scope = subagents_view(session, a.stall)
    scope.update(member=member or None, inspectionOnly=inspection, depth=a.depth, all=a.all, done=a.done,
                 machine=host_name())
    counts = view.counts()
    if a.done is not None:
        agents = view.done(a.done)
    else:
        agents = view.tree(every=a.all or a.json, depth=a.depth)
    if inspection:
        for e in agents:
            e["inspectionOnly"] = True
    if a.json:
        print(json.dumps({"self": me, "scope": scope, "counts": counts, "agents": agents, "notes": view.notes},
                         indent=2))
        return
    if me:
        print(self_line(me))
    whose = "subagents" if not inspection else "subagents of %s [%s]" % (member or session[:8], session[:8])
    if inspection:
        print("%s — inspection only: SendMessage reaches only your own session's subagents; reach this session "
              "with sminos send" % whose)
        whose = "  "
    if a.done is not None:
        print("%s, the %d ended last, newest first:" % (
            "ended subagents" if not inspection else "  ended subagents", a.done))
        lines = V.done_lines(agents)
        print("\n".join(lines) if lines else "  (none has ended)")
        if lines and not inspection:
            print("SendMessage to an agentId resumes that agent, when its work should go on")
    else:
        print((whose + " " if not inspection else "  ") + V.counts_line(counts)
              + ("" if scope["live"] else " — the session runs no process"))
        lines = V.tree_lines(agents)
        if lines:
            print("\n".join(lines))
        elif not view.agents:
            print("  (no subagents in session %s: %s)" % (session[:8], view.dir or "no transcript"))
        else:
            print("  (none is live)")
        ended = V.ended_line(counts)
        if ended and not a.all:
            print("  %s — sminos list --subagents%s --done 10" % (ended, " " + member if member else ""))
    for n in view.notes:
        print("note: " + n)


def cmd_list(a):
    """The members of the caller's project, or what the filters pick from
    every project known here (list_scope): one row each (row_cells), under
    the project's heading when one project shows, flat with the project
    column when several do; --here adds `(no project)`. Stopped, retired and
    gone fold into a tail line; --stopped adds stopped, --all shows all, and
    --state keeps the named states; --here ends with the live sessions that
    are no member (other_live_sessions). Inside a session, the list says who
    the caller is and ends with one cheap line on its subagents
    (subagent_summary_line); with --subagents or --done it is the subagent
    view alone (cmd_subagents)."""
    if a.subagents is not None or a.done is not None:
        cmd_subagents(a)
        return
    projects, words, picked = list_scope(a)
    sections, out, hidden, members_known = [], [], 0, set()
    folded = [word for word in HIDDEN if not (a.stopped and word == "stopped")]
    for p in projects:
        every = project_rows(p)
        members_known |= {m.session for m in every if m.session}
        rows = [m for m in every if row_matches(m, p, a, words)]
        if a.json:
            out += [member_json(m, p, private=not a.org) for m in rows]
            continue
        # Visibility options only affect text; --json keeps every matching row.
        # An explicit --state also reveals the words it selects.
        if not a.all:
            hidden += sum(1 for m in rows if m.state in folded and m.state not in a.state)
            rows = [m for m in rows if m.state not in folded or m.state in a.state]
        if rows:
            sections.append((p, rows))
    loose = []
    if a.here and not picked:   # a session in no project is in none of the projects named
        for p in known_projects():
            if p.id not in {q.id for q in projects}:
                members_known |= {m.session for m in project_rows(p) if m.session}
        loose = [m for m in unprojected_rows(members_known) if row_matches(m, None, a, words)]
    others = []
    if a.here and not picked and not words and not a.state and not a.machine:
        others = other_live_sessions(members_known | {m.session for m in loose})
    notes = peer_notes() if (a.here or a.org or not projects) else []
    if a.json:
        out += [{"project": None, "project_id": None, "project_kind": None, **member_json(m, private=not a.org)}
                for m in loose]
        out += [{"project": None, "project_id": None, "project_kind": None, "alias": o["name"],
                 "session": o["session"], "short": o["short"], "machine": host_name(), "local": True,
                 "member": False, "state": None, "engine": {k: o[k] for k in
                                                            ("status", "kind", "entrypoint", "startedAge", "desktop",
                                                             "formerName")}}
                for o in others]
        print(json.dumps(out, indent=2))
        for n in notes:
            print("note: " + n, file=sys.stderr)
        return
    if not sections and not loose:
        print("(no members in %s)" % (", ".join(p.name for p in projects) if projects else "any project known here"))
    if len(sections) == 1:
        print(sections[0][0].name)
        print_rows([row_cells(m) for m in sections[0][1]])
    elif sections:
        print_rows([row_cells(m, p) for p, rows in sections for m in rows])
    if loose:
        print("(no project)")
        print_rows([row_cells(m) for m in loose])
    if others:
        print("other live sessions (not members)")
        print_table_rows([["%s [%s]" % (o["name"], o["short"]), o["kind"] or "?", o["status"] or "?",
                           o["entrypoint"] or "?",
                           "started " + short_age(o["startedAge"]) if o["startedAge"] is not None else ""]
                          for o in others])
    if hidden:
        hint = "--all" if a.stopped else "--stopped shows stopped; --all shows all"
        print("+%d hidden (%s) — sminos list %s" % (hidden, ", ".join(folded), hint))
    for n in notes:
        print("note: " + n)
    me = self_identity()
    if me and not a.find:
        print(self_line(me))
        line = subagent_summary_line(me["session"])
        if line:
            print(line)


def cmd_find(a):
    """`find <words>`: list --org <words>."""
    a.org = True
    cmd_list(a)


def live_members(projects):
    """{project id: its live members (busy, idle, waiting)} of each project."""
    return {p.id: [m for m in members(p) if m.state in FILLED] for p in projects}


def print_table(header, rows):
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header) - 1)]
    for r in [header] + rows:
        print("  ".join([c.ljust(w) for c, w in zip(r, widths)] + [r[-1]]).rstrip())


def org_age_line():
    """The age of daemon/org.json when it is older than a minute: the
    directory is the hub's as of then."""
    d = org_directory()
    at = _ts_epoch(d["at"]) if d else None
    if at is not None and time.time() - at > 60:
        print("(the org's directory is %s old: the daemon's stream has said nothing newer)" % short_age(time.time() - at))


def cmd_projects(a):
    """`projects [--all]`: every project known here — its name, kind, live
    and waiting sessions, and the machines they run on. A project the org's
    directory marks retired (a revoked machine's) only with --all."""
    known = sorted(known_projects(), key=lambda p: (p.name.lower(), p.id))
    shown = [p for p in known if a.all or not org_retired(p.id)]
    live = live_members(shown)
    kinds = {p.id: project_kind(p) for p in known}
    rows = []
    for p in shown:
        ms = live[p.id]
        # A name answers to one project (find_project): one that loses it is
        # shown by its id, the name it answers to.
        shadowed = any(q.name == p.name and q.id != p.id and ("hub", "machine", "local").index(kinds[q.id])
                       < ("hub", "machine", "local").index(kinds[p.id]) for q in known)
        rows.append((p.id if shadowed else p.name, kinds[p.id] + (" (retired)" if org_retired(p.id) else ""), str(len(ms)),
                     str(sum(1 for m in ms if m.state == "waiting")),
                     ", ".join(sorted({m.machine for m in ms}, key=str.lower)) or "-"))
    if not rows:
        print("no project is known on this machine")
        return
    print_table(("PROJECT", "KIND", "LIVE", "WAITING", "MACHINES"), rows)
    org_age_line()


def cmd_machines(_a):
    """`machines`: every machine enrolled in the org (daemon/org.json) —
    online, or when it was last seen — with its live sessions and the
    projects they are in, read from the logs this machine holds. On a machine
    that is not enrolled, this machine alone."""
    e = enrollment()
    org = org_directory() if e else None
    by_machine = {}
    projects = known_projects()
    live = live_members(projects)
    for p in projects:
        for m in live[p.id]:
            sessions, names = by_machine.setdefault(m.machine.lower(), (set(), set()))
            sessions.add(m.session)
            names.add(p.name)

    def row(name, state):
        sessions, names = by_machine.get(name.lower(), (set(), set()))
        return name, state, str(len(sessions)), ", ".join(sorted(names, key=str.lower)) or "-"

    if e is None:
        print("this machine is not enrolled at a desk hub (sminos hub enroll): it knows only itself")
        rows = [row(host_name(), "this machine")]
    elif org is None:
        print("no org directory yet: the daemon has not connected to the hub (sminos daemon run)")
        rows = [row(e["machine"], "this machine")]
    else:
        rows = []
        for m in sorted(org["machines"], key=lambda m: m["name"].lower()):
            seen = _ts_epoch(m.get("seen"))
            state = "online" if m.get("online") is True else \
                "last seen %s ago" % short_age(max(0.0, time.time() - seen)) if seen is not None else "never seen"
            rows.append(row(m["name"], state))
    print_table(("MACHINE", "STATE", "LIVE", "PROJECTS"), rows)
    if org is not None:
        org_age_line()


def move_session(sid, old, new, by):
    """The calling session's move from project `old` to `new` (None: no
    project), as join writes it before it returns: `retired` (moved) in the
    old log, `joined` (`by`) in the new, then both reconciled. Returns the
    events appended."""
    out = []
    if old is not None and new is None:
        out += lifecycle(old, sid, "retired", guard=lambda evs: latest_membership(evs) == "joined",
                         by="", reason="moved", project="")
    elif old is not None:
        out += retire_moved(old, sid, new)
    peer = session_running(sid)
    if new is not None and peer is not None and latest_membership(_own_events(new, sid)) != "joined":
        out += join_on_sight(new, sid, None, peer, True, by=by)
    for p in (old, new):
        if p is not None:
            reconcile(p)
    return out


def cmd_join(a):
    """`join <project>`: the calling session declares its project, which a
    `.smns` under its launch directory never overrides (an override file,
    §7); `join --cwd` removes the declaration and goes back to its launch
    directory's project; `join` alone says which project it is in and why.
    The move is written before the verb returns. A seat stays where it was
    spawned; a target must be one the session can sync in (join_refusal)."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not UUID_RE.match(sid):
        die("join declares the calling session's project: run it from inside a session")
    if a.cwd and a.project:
        die("usage: sminos join <project> | --cwd | (nothing: which project this session is in)")
    launch = launch_cwd(sid, fallback=os.getcwd())
    home = resolve_project(launch)
    held = override_of(sid)
    now_in = session_project(sid, launch)
    me = default_from("")
    home_line = ("%s, its launch directory's project (%s)" % (home.name, launch)) if home else \
        "no project: its launch directory (%s) resolves to none" % launch
    if not a.project and not a.cwd:
        if held and now_in is not None and now_in.id == held:
            print("%s is in %s, by its override (sminos join --cwd returns it to %s)" % (me, now_in.name, home_line))
        elif held:
            target = known_project(held)
            why = join_refusal(target) if target else "not known here"
            print("%s is in %s; its override names %s, which it cannot be in (%s)" % (
                me, home_line, target.name if target else held, why))
        else:
            print("%s is in %s; no override" % (me, home_line))
        return
    if caller_seat():
        die("a seat's project is where it was spawned: %s stays in %s" % (me, now_in.name if now_in else "it"), 1)
    if a.cwd:
        if not held:
            print("%s has no override: it is in %s" % (me, home_line))
            return
        remove_override(sid)
        move_session(sid, now_in, home, "join")
        print("%s is back in %s" % (me, home_line))
        return
    target = find_project(a.project)
    why = join_refusal(target)
    if why:
        die("cannot join %s: %s" % (target.name, why), 1)
    if now_in is not None and now_in.id == target.id:
        print("%s is already in %s" % (me, target.name))
        return
    write_override(sid, target.id)
    move_session(sid, now_in, target, "join")
    print("%s joined %s (was in %s); sminos join --cwd returns it to %s" % (
        me, target.name, now_in.name if now_in else "no project", home.name if home else "no project"))


GUIDE_RECORD_WAIT = 1.5   # seconds the guide waits for the engine's record; the hook's bound is 10


def _hook_engine(session, title=""):
    """(None, record) standing for `session` when no engine record names it
    yet, from the record of the engine running its SessionStart hook. A
    session that replaces another in the same process — `/branch`, an
    in-session `/resume` — fires its hook while the engine's record still
    names the session it left: the engine (2.1.303) rewrites it only after
    the SessionStart hooks return, so no wait sees it. The process is the new
    session's all the same (its kind, entrypoint, pid and its host's mark),
    and so is its name, unless the payload gives the title the engine names
    it by next (`/branch`'s, as the user's). The hook's environment says
    which engine: CLAUDE_PID, written beside CLAUDE_CODE_SESSION_ID, which
    must name this session (a pair inherited from an outer engine names
    another). None when there is no such record, or for derive's internal
    fork."""
    pid = os.environ.get("CLAUDE_PID", "")
    if os.environ.get("CLAUDE_CODE_SESSION_ID") != session or not pid.isdigit() or pid in internal_pids():
        return None
    rec = next((r for r in peer_records() if str(r.get("pid")) == pid and peer_running(r)), None)
    if rec is None:
        return None
    return None, dict(rec, sessionId=session, **({"name": title, "nameSource": "user"} if title else {}))


def guide_text(session, launch, source="", title=""):
    """The SessionStart guidance (§9) for a session launched in `launch` on
    this enrolled machine: who it is and where its project comes from, then
    the verbs that find and reach the org's other sessions. Only for a
    session that is a member on sight, as the record hook decides it
    (joinable: a headless or SDK run its host did not mark, or one the
    engine has not recorded, is told nothing it is not), and no `join` for a
    seat, which cannot. A fork (`source`, the payload's) is told so: its
    context holds the guidance the session it was forked from read, which
    names that session. Only facts the model cannot derive, and only lines
    the evals showed move behavior."""
    global _PEERS
    project = session_project(session, launch)
    seen = _on_sight(project, session) if project is not None else None
    if seen == (None, None):
        seen = _hook_engine(session, title) or seen
    # Neither a seat nor the engine's record names it yet: the engine may
    # write the record a moment after the hook starts, so it is looked for
    # again, briefly, before the session is left unguided for its whole run.
    until = time.time() + GUIDE_RECORD_WAIT
    while seen == (None, None) and time.time() < until:
        time.sleep(0.1)
        _PEERS = None
        seen = _on_sight(project, session)
    if seen is None or not joinable(*seen, member_mark(seen[1])):
        return ""
    seat, peer = seen
    home = resolve_project(launch)
    # The alias it goes by, as its own say would sign it (default_from).
    alias = seat["alias"] if seat else \
        held_alias(*own_alias(_own_events(project, session), session), peer, session,
                   shadowing(project, session))[0]
    who = "%s [%s]" % (alias, session[:8]) if alias and alias != session[:8] else "[%s]" % session[:8]
    # The CLI is off PATH: its installed path is given once, and the verb lines
    # name it `sminos` (an eval round showed no session typed the bare name).
    path, cli = os.path.join(SCRIPT_DIR, "sminos"), "sminos"
    if home is not None and home.id != project.id:
        where = ("by your own `sminos join` (your launch directory, %s, is in %s; `%s join --cwd` returns you there)"
                 % (launch, home.name, cli))
    elif project_kind(project) == "machine":
        where = "this machine's own project, since no .smns or repository remote claims your launch directory, %s" \
            % launch
    elif smns_at(launch) is None and derivation(launch).key:
        where = "the project of your repository's remote, %s (your launch directory, %s)" % (
            derivation(launch).key, launch)
    else:
        where = "the project of your launch directory, %s" % launch
    join = [] if seat else ["  %s join <project>  when your directory files you in the wrong project (a scratch copy)"
                            " or your standing work belongs to another; once, not per repository you visit" % cli]
    fork = " You are a fork of another session: any sminos line above this one was written for it, not you." \
        if source == "fork" else ""
    return "\n".join([
        "sminos: you are %s in project %s on machine %s: %s. A `cd` does not change your project.%s"
        % (who, project.name, enrollment()["machine"], where, fork),
        "Other Claude sessions work in this org, on every enrolled machine and in every repository. "
        "To find one or tell it something, use sminos. It is not on PATH; run it as",
        "  %s" % path,
        "  %s list            peer sessions in your project; --here sessions on this machine, --org every connected"
        " host and project" % cli,
        "  %s list --subagents   your subagents (--done N: finished ones, resumed by SendMessage to the agentId);"
        " these two replace ListAgents: use them instead" % cli,
        "  %s who <commit|PR> the session a commit or PR names in its Sminos-Session line, and how to reach it" % cli,
        '  %s say "..."       recorded in your project\'s log, read at its sessions\' next chat; wakes no one:'
        " status nobody must act on goes here" % cli,
        '  %s say "@<short> ..."   reaches that session wherever it runs, as does "@<project>/<alias> ...";'
        " a bare @alias reaches only your project" % cli,
        '  %s say --org|--project P|--machine M|--here "..."   wakes every live session list shows with the'
        " same flags (they combine) but you" % cli,
    ] + join + [
        '  %s charge "<line>" what you are in charge of, shown beside you in every list' % cli,
    ])


ROSTER_SOURCES = ("compact", "resume")   # a session that goes on with its own conversation, summarized or old
ROSTER_CAP = 10        # peers the roster names
ROSTER_BUDGET = 3.0    # seconds the roster may spend, inside the hook's bound of 10


def _roster_exchanges(session, projects):
    """{(project id, peer session): {"in", "out", "at", "alias"}}: when
    `session`, with the sessions it continues, last wrote each peer a tagged
    sminos message (`out`) and last was written one by it (`in`), "" for
    neither, as the logs of `projects` hold them; `alias` is the peer's as the
    latest of them named it (`at`). A message into another project is read
    off the copy its own project's log keeps (record_copy), whose recipients
    name their project; one from another project names the sender's
    (`from_project`). An untagged line or an @all names no one in
    particular, and the engine's own SendMessage is in no log."""
    out, seen = {}, set()

    def note(key, way, ts, alias):
        row = out.setdefault(key, {"in": "", "out": "", "at": "", "alias": ""})
        row[way] = max(row[way], ts)
        if ts >= row["at"]:
            row["at"], row["alias"] = ts, alias

    for p in projects:
        events = log_read(p)
        mine = {session, *lineage(session, _projection(events))}
        for e in events:
            to = e.get("to")
            if e["kind"] != "say" or e.get("wake") or not isinstance(to, list):
                continue
            sender = writer_session(e["writer"])
            if "copy" in e and sender not in mine:
                continue   # a copy counts only as the session's own message out; a peer's would hide its delivery
            # Seen only once counted: a log that does not hold a hand-off reads
            # the session it continues as a stranger, and another log may not.
            ref = str(e.get("copy") or "%s:%s:%d" % (p.id, e["writer"], e["seq"]))
            if ref in seen:
                continue
            to = [r for r in to if isinstance(r, dict) and UUID_RE.match(str(r.get("session") or ""))]
            if sender in mine:
                seen.add(ref)
                for r in to:
                    if r["session"] not in mine:
                        note((str(r.get("project") or p.id), r["session"]), "out", e["ts"], str(r.get("alias") or ""))
            elif sender and any(r["session"] in mine for r in to):
                seen.add(ref)
                note((str(e.get("from_project") or p.id), sender), "in", e["ts"], str(e.get("from") or ""))
    return out


def _roster_peer(pid, sid, all_seats):
    """(project, member, ended, projection) a peer is now: followed into the
    session it continues in (a hand-off) and into the project it moved to;
    `ended` when its membership there is retired. None when no project known
    here holds it."""
    for _ in range(4):   # a move chain, bounded
        p = known_project(pid)
        if p is None:
            return None
        info = _projection(log_read(p))
        hops = []
        while (info.get(sid) or {}).get("to") and sid not in hops:
            hops.append(sid)
            sid = info[sid]["to"]
        r = info.get(sid)
        latest = (r or {}).get("latest") or {}
        moved_to = str(latest.get("project") or "") if latest.get("reason") == "moved" else ""
        if latest.get("kind") == "retired" and moved_to and moved_to != p.id:
            pid = moved_to
            continue
        if r is None:
            return None
        m = _member(sid, r, seats_by_session(p, all_seats).get(sid), None, False, True, info)
        return p, m, latest.get("kind") == "retired", info
    return None


def _roster_tag(p, m, here, info):
    """The tag that reaches member `m` of `p` from a session of `here`:
    `@alias` in its own project, `@<project>/<alias>` from another (§5), with
    `#short` when another member there holds the alias too; quoted when the
    bare form would not parse back whole (leading_tags), and `@<short>` when
    neither form does."""
    alias = m.alias
    if not alias or alias == m.short:
        return "@" + m.short
    project = "" if here is not None and p.id == here.id else tag_project(p)
    body = (project + "/" if project else "") + alias
    shared = any(s != m.session and r["latest"] and r["latest"]["kind"] == "joined"
                 and logged_alias(s, info)[0] == alias for s, r in info.items())
    short = m.short if shared else ""
    for tag in ("@" + body, '@"%s"' % body):
        tag += "#" + short if short else ""
        if [(t["raw"], t["project"], t["name"], t["short"]) for t in leading_tags(tag)] == [(tag, project, alias, short)]:
            return tag
    return "@" + m.short


def _roster_when(ts):
    """A log ts as the roster says it: `HH:MMZ, 35m ago`, the date first when
    it is not today's."""
    age = ts_age(ts)
    if age is None:
        return ts
    ago = "%dm" % (age // 60) if age < 5400 else "%dh" % (age // 3600) if age < 172800 else "%dd" % (age // 86400)
    day = "" if ts[:10] == time.strftime("%Y-%m-%d", time.gmtime()) else ts[5:10] + " "
    return "%s%sZ, %s ago" % (day, ts[11:16], ago)


def roster_text(session, launch):
    """The roster a session reads after a compaction or a resume, below its
    guidance: the members it exchanged sminos messages with, newest exchange
    first, at most ROSTER_CAP, each with where it is now (alias [short],
    project, machine), its state and in-charge line, the tag that reaches it
    now, when the last exchange was and which way, and whether its last
    message is unanswered. Read from the logs, never the conversation: a
    summary keeps addresses (an engine socket, an alias) that have gone
    stale. The logs read are its project's and its launch directory's; a
    peer reached only through the engine's SendMessage is in neither. ""
    when it exchanged none. Read-only, and bounded by ROSTER_BUDGET: what does
    not fit is left out."""
    until = time.time() + ROSTER_BUDGET
    here = session_project(session, launch)
    if here is None:
        return ""
    home = resolve_project(launch)
    rows = _roster_exchanges(session, [here] + ([home] if home is not None and home.id != here.id else []))
    all_seats = seats()
    peers, lines = {}, []
    for (pid, sid), row in sorted(rows.items(), key=lambda kv: max(kv[1]["in"], kv[1]["out"]), reverse=True):
        if len(peers) >= ROSTER_CAP or time.time() > until:
            break
        now = _roster_peer(pid, sid, all_seats)
        if now is not None and now[1].session == session:
            continue
        key = (now[0].id, now[1].session) if now else (pid, sid)
        if key in peers:   # two sessions of one member, the newer exchange read first
            held = peers[key][2]
            held["in"], held["out"] = max(held["in"], row["in"]), max(held["out"], row["out"])
            continue
        peers[key] = (now, sid, dict(row))
    for now, sid, row in peers.values():
        last = max(row["in"], row["out"])
        way = "it wrote you" if row["in"] == last else "you wrote it"
        tail = "last: %s %s%s" % (way, _roster_when(last), ", unanswered" if row["in"] > row["out"] else "")
        if now is None:
            lines.append("  %s [%s], in no project known here; %s" % (row["alias"] or sid[:8], sid[:8], tail))
            continue
        p, m, ended, info = now
        who = "%s [%s], %s on %s" % (m.alias, m.short, p.name, m.machine or "?")
        if ended:
            lines.append("  %s: its session ended, no tag reaches it; %s" % (who, tail))
            continue
        charge = charge_shown(m)
        lines.append("  %s  %s, %s%s; %s" % (_roster_tag(p, m, here, info), who, m.state or "state unknown",
                                             ', in charge: "%s"' % charge if charge else "", tail))
    if not lines:
        return ""
    return "\n".join(["sminos: who you exchanged sminos messages with, newest first, as the logs hold them now"
                      " (a SendMessage peer is in no log). Reach them by these tags: an address your context kept"
                      " may be stale."] + lines)


def cmd_guide(_a):
    """The SessionStart hook's verb (§9): its payload on stdin, the guidance
    on stdout. Nothing on a machine not enrolled at a desk hub, for an
    internal fork, or for a payload naming no session — the gate is here, so
    the hook stays a few lines. After a compaction or a resume the guidance
    ends with the roster of the session's peers (roster_text). It reads and
    never migrates (the record hook beside it does, bounded): a session's
    start must not wait on a lock."""
    if os.environ.get("SMNS_INTERNAL") or enrollment() is None or sys.stdin.isatty():
        return
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    session, cwd = str(payload.get("session_id") or ""), str(payload.get("cwd") or "")
    if not UUID_RE.match(session):
        return
    text = ""
    try:
        launch = launch_cwd(session, str(payload.get("transcript_path") or ""), fallback=cwd)
        text = guide_text(session, launch, str(payload.get("source") or ""), str(payload.get("session_title") or ""))
        roster = roster_text(session, launch) if text and payload.get("source") in ROSTER_SOURCES else ""
        text += "\n" + roster if roster else ""
    except Exception as e:  # noqa: BLE001 — guidance is a courtesy; a failure must never fail the session's start
        try:
            daemon_log("guide %s: %s: %s" % (session[:8], type(e).__name__, e))
        except OSError:
            pass
    if text:   # a roster that failed leaves the guidance whole
        print(text)


# ------------------------------------------- a session's address in what it writes
#
# Every commit and pull request a member writes carries its address — a commit
# as a git trailer, a PR body as its last line — so a reader of the artifact
# reaches the session that made it in one step (`who`). The sminos plugin's mod
# hooks/mods/address.tsx hands the line to the engine's attribution text; the
# line is composed here, where the session's identity is.

ADDRESS_KEY = "Sminos-Session"
ADDRESS_RE = re.compile(r"Sminos-Session:[ \t]*(?:(?P<alias>\S.*?)#)?(?P<short>[0-9a-f]{8})[ \t]+"
                        r"\((?P<project>[^\s()]+) on (?P<machine>[^\s()]+)\)[ \t]*")
ADDRESS_ALIAS_RE = re.compile(r"[^\s#()][^\n#()]{0,63}")   # one short line, no character the line's form uses


def session_address(session, fallback_cwd=""):
    """The `Sminos-Session: <alias>#<short> (<project> on <machine>)` line of a
    session of this machine — `<short>` alone for a session with no name fit
    for it — or "" when it has none: in no project, an internal fork, or no
    member (its log holds no membership and it is no member on sight,
    joinable). The alias is the one its own `say` signs with (guide_text's)."""
    if os.environ.get("SMNS_INTERNAL") or not UUID_RE.match(session or ""):
        return ""
    project = session_project(session, launch_cwd(session, fallback=fallback_cwd))
    if project is None:
        return ""
    seen = _on_sight(project, session)
    if seen is None:
        return ""
    seat, peer = seen
    own = _own_events(project, session)
    if latest_membership(own) != "joined" and not joinable(seat, peer, member_mark(peer)):
        return ""
    alias = seat["alias"] if seat else held_alias(*own_alias(own, session), peer, session,
                                                  shadowing(project, session))[0]
    # A name that is no name — a `claude --bg "<prompt>"` job joins under its
    # prompt, the harness's first name for it — would make the line a
    # paragraph the model rewrites: the short goes alone.
    who = "%s#%s" % (alias, session[:8]) if ADDRESS_ALIAS_RE.fullmatch(alias or "") and alias != session[:8] \
        else session[:8]
    return "%s: %s (%s on %s)" % (ADDRESS_KEY, who, project.name, host_name())


def parse_addresses(text, last_paragraph=False):
    """The addresses a text carries, [{line, alias, short, project, machine}]
    in order, each line once (alias "" for a line naming the short alone); with last_paragraph, only its last paragraph's
    (where a commit's trailers stand)."""
    if last_paragraph:
        paras = [p for p in re.split(r"\n[ \t]*\n", (text or "").strip()) if p.strip()]
        text = paras[-1] if paras else ""
    out, seen = [], set()
    for line in (text or "").splitlines():
        m = ADDRESS_RE.fullmatch(line.strip())
        if m and line.strip() not in seen:
            seen.add(line.strip())
            out.append(dict(m.groupdict(), alias=m.group("alias") or "", line=line.strip()))
    return out


PR_RE = re.compile(r"https?://[^/\s]+/[^/\s]+/[^/\s]+/pull/\d+(?:[/?#].*)?|#?\d+")


def is_pr_target(target):
    """Whether `who`'s target names a pull request: its URL, `#N`, or a plain
    number — one of seven digits or more only when no commit here is
    abbreviated by it."""
    if not PR_RE.fullmatch(target):
        return False
    if target.isdigit() and len(target) >= 7:
        r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", target + "^{commit}"],
                           capture_output=True, text=True)
        return r.returncode != 0
    return True


def addresses_of(target):
    """(what the addresses were read from, [addresses]) for `who`'s target: a
    commit's trailers (git, in the working directory's repository); a PR's
    body line, else its commits' trailers (gh)."""
    if is_pr_target(target):
        try:
            r = subprocess.run(["gh", "pr", "view", target.lstrip("#"), "--json", "number,body,commits"],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            die("who: gh could not read pull request %s: %s" % (target, e), 1)
        if r.returncode != 0:
            die("who: gh could not read pull request %s: %s" % (target, r.stderr.strip() or "exit %d" % r.returncode), 1)
        pr = json.loads(r.stdout)
        found = parse_addresses(pr.get("body") or "")
        if found:
            return "pull request #%s's body" % pr.get("number"), found[-1:]
        found, seen = [], set()
        for c in pr.get("commits") or []:
            for addr in parse_addresses(c.get("messageBody") or "", last_paragraph=True):
                if addr["line"] not in seen:
                    seen.add(addr["line"])
                    found.append(addr)
        return "pull request #%s's commits" % pr.get("number"), found
    r = subprocess.run(["git", "log", "-1", "--format=%H%n%(trailers:key=" + ADDRESS_KEY + ",unfold)", target, "--"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        why = (r.stderr.strip().splitlines() or ["git log failed"])[-1]
        die("who: %s is no commit here and no pull request (%s)" % (target, why), EXIT_UNKNOWN)
    sha, _, trailers = r.stdout.partition("\n")
    return "commit %s" % sha[:12], parse_addresses(trailers)


def who_matches(short):
    """(project, member, how) for each session of the org known here a short
    names, one per session: the member that is that session (`how` ""), the
    member that continues it (`continued`: it went to the background, or on
    in another process; `former`), or a session whose membership the log
    holds as retired — its process ended, it was retired, or it moved to a
    project not known here (`how` the retirement's reason, "retired" for
    none) — drawn as a member would be, so its state is list's word. A
    session handed off to one that has since ended too answers as the last
    session of its hand-offs (`continued`); as itself ("handed off") when
    no successor joined in its project."""
    best = {}
    scope = org_scope()
    known = {p.id for p in scope}
    for p in scope:
        view = view_of(p)
        for m in view.members + view.rows:
            if not m.session:
                continue
            if m.short == short:
                best.setdefault(m.session, (p, m, ""))
            elif any(s[:8] == short for s in m.former):
                best.setdefault(m.session, (p, m, "continued"))
    for p in scope:
        view = view_of(p)
        for sid, r in view.info.items():
            latest = r["latest"] or {}
            if sid[:8] != short or sid in best or latest.get("kind") != "retired" or not r["joined"] \
                    or (latest.get("reason") == "moved" and latest.get("project") in known):
                continue
            how = str(latest.get("reason") or "retired")
            if how == "continued" and r["to"]:
                if any(sid in m.former for _, m, _ in best.values()):
                    continue
                last, seen = sid, {sid}
                while True:
                    c = view.info.get(last) or {}
                    nxt = c.get("to") or ""
                    if (c.get("latest") or {}).get("reason") != "continued" or not nxt or nxt in seen \
                            or not (view.info.get(nxt) or {}).get("joined"):
                        break
                    seen.add(nxt)
                    last = nxt
                if last in best:
                    continue
                best[last] = (p, _member(last, view.info[last], None, None, False, True, view.info),
                              "continued" if last != sid else "handed off")
                continue
            best[sid] = (p, _member(sid, r, None, None, False, True, view.info), how)
    return list(best.values())


def who_lines(addr):
    """What `who` says of one address: the line as the artifact carries it,
    then who that session is now and how to reach it — or what the line
    says, when no session known here answers to its short."""
    out = [addr["line"]]
    hits = who_matches(addr["short"])
    if not hits:
        out.append("  no session %s in the org's directory known here: the line is all there is — %s in "
                   "project %s on machine %s" % (addr["short"], addr["alias"] or addr["short"], addr["project"],
                                                 addr["machine"]))
        return out
    for p, m, how in hits:
        label = "%s#%s" % (m.alias, m.short)
        if how == "continued":
            out.append("  went on as %s (%s), %s on %s: %s" % (label, m.kind or "?", p.name, m.machine, m.state or "?"))
        elif how == "moved":
            out.append("  %s left %s for a project not known here (%s on %s)" % (label, p.name, m.state or "?", m.machine))
        else:
            out.append("  now %s, %s on %s: %s%s" % (label, p.name, m.machine, m.state or "?",
                                                     " (its session %s)" % how if how else ""))
        if addr["alias"] and m.alias != addr["alias"]:
            out.append("  (the line names it %s; it goes by %s now)" % (addr["alias"], m.alias))
        if charge_shown(m):
            out.append("  in charge: %s" % charge_shown(m))
        if m.state in FILLED or (m.seat and m.state != "retired"):
            out.append('  reach: sminos say "@%s ..."%s' % (m.short, "" if m.state in FILLED else
                                                             "  (the stopped seat is resumed)"))
        elif m.state != "gone" or not m.local:
            where = "here" if m.local else "on %s" % m.machine
            out.append("  resume it %s: cd %s && claude --resume %s" % (where, shlex.quote(m.cwd or "."), m.session))
            out.append('  or leave it a note it reads when resumed: sminos say --in %s "..."' % tag_project(p))
    return out


def cmd_who(a):
    """`who [<commit|PR>]`: the session a commit or pull request names in its
    Sminos-Session line, as it is now and how to reach it. Without a target,
    the line this session's commits carry (`--session` names another of this
    machine's: the address mod's call), nothing when it has none."""
    if not a.target:
        sid = a.session or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        if not sid:
            die("usage: sminos who <commit|PR>  (inside a session, alone: the line its commits carry)")
        line = session_address(sid, os.getcwd())
        if line:
            print(line)
        return
    what, found = addresses_of(a.target)
    if not found:
        die("who: %s carries no %s line" % (what, ADDRESS_KEY), EXIT_UNKNOWN)
    print("%s:" % what)
    for addr in found:
        print("\n".join(who_lines(addr)))


def cmd_attach(a):
    s = resolve_seat(a.seat)
    live = state(s)
    row = harness_row(s) if s["current"] else None
    short = (row or {}).get("id") or s["short"]
    if not short:
        die("%s/%s has no session to attach to (%s)" % (s["group"], s["alias"], live), EXIT_UNKNOWN)
    if live in FILLED and sys.stdout.isatty() and not os.environ.get("SMINOS_NO_EXEC"):
        os.execvp("claude", ["claude", "attach", short])
    print("claude attach %s" % short)


def sibling_module(name):
    """Import a sibling module (sminos_chart, sminos_tui) bound to THIS module
    instance: when sminos.py runs as __main__ a plain `import sminos` inside the
    sibling would execute the file a second time and give it its own, separate
    harness caches. A copy loaded without a place in sys.modules (a test's
    spec_from_file_location) has none to bind: its sibling imports its own."""
    me = sys.modules.get(__name__)
    if me is not None:
        sys.modules.setdefault("sminos", me)
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    return importlib.import_module(name)


def chart_module():
    return sibling_module("sminos_chart")


def daemon_module():
    return sibling_module("sminos_daemon")


def bridge_module():
    return sibling_module("sminos_bridge")


def control_module():
    return sibling_module("sminos_control")


def cmd_bridge(a):
    bridge_module().cmd_bridge(a)


def cmd_watch(a):
    bridge_module().cmd_watch(a)


def cmd_steer(a):
    control_module().cmd_steer(a)


def cmd_interrupt(a):
    control_module().cmd_interrupt(a)


def cmd_stop(a):
    control_module().cmd_stop(a)


def cmd_model(a):
    control_module().cmd_model(a)


def cmd_compact(a):
    control_module().cmd_compact(a)


def cmd_command(a):
    control_module().cmd_command(a)


def cmd_read(a):
    control_module().cmd_read(a)


def cmd_decide(a):
    control_module().cmd_decide(a)


def cmd_answer(a):
    control_module().cmd_answer(a)


def tick(project):
    """One daemon tick of one project (§8): integrate, reconcile, publish,
    deliver, push. {"integrated", "reconciled", "published", "delivered",
    "pushed"}, plus "to" (the aliases delivered to) and "error"."""
    return daemon_module().tick(project)


def cmd_daemon(a):
    if not a.op:
        die("usage: sminos daemon run [--interval N] | tick | install | status | owed | policy [--read-only on|off] "
            "[--ceiling MODE|settings]")
    daemon_module().cmd_daemon(a)


def hub_module():
    return sibling_module("sminos_hub")


def cmd_hub(a):
    hub_module().cmd_hub(a.words)


def cmd_rpc_query(a):
    sibling_module("sminos_rpc").cmd_rpc_query(a)


def cmd_chart(a):
    """The members as boxes, flat: one project's in a column, or — for every
    project — each project a rounded box with its members beside it; hidden
    members folded into '+N hidden'; --stopped adds stopped and --all shows
    all members; then one summary line."""
    projects, boxed = view_projects(a.project, a.all)
    chart = chart_module()
    roots, meta = chart.snapshot(projects, a.all, boxed, show_stopped=a.stopped)
    folded = [word for word in HIDDEN if not (a.stopped and word == "stopped")]
    hint = "sminos chart%s %s" % ((" " + a.project) if a.project else "",
                                "--all" if a.stopped else "--stopped shows stopped; --all shows all")
    lay = chart.layout(roots)
    width = a.width or (shutil.get_terminal_size((120, 40)).columns if sys.stdout.isatty() else 120)
    if lay["boxes"]:
        scr = chart.GridScreen(width, lay["height"])
        chart.paint_chart(scr, lay)
        print(scr.text())
    else:
        print("(no members to chart%s)" % ("" if not meta["hidden"] else
              " — all %d are hidden (%s); %s" % (meta["hidden"], ", ".join(folded), hint)))
    bits = []
    if boxed:
        bits.append("%d projects" % meta["projects"])
    bits += ["%d members" % meta["members"], "%d live" % meta["live"]]
    if meta["hidden"]:
        hid = "%d hidden (%s)" % (meta["hidden"], ", ".join(folded))
        if meta["hidden_projects"]:
            hid += " in %d project(s) folded away" % meta["hidden_projects"]
        bits.append(hid + " — " + hint)
    if lay["width"] > width:
        bits.append("%d cells clipped on the right (--width %d)" % (lay["width"] - width, width))
    print(" · ".join(bits))


def cmd_tui(a):
    """The chart as an interactive screen (sminos_tui): headless when asked,
    otherwise a real terminal inside tmux."""
    view_projects(a.project, a.all)  # an unknown project exits 4 before any screen
    sibling_module("sminos_tui").cmd_tui(a)


# ---------------------------------------------------------------------- meta


def cmd_meta(a):
    s = resolve_seat(a.seat)
    if a.op == "get":
        if not a.field:
            die("usage: sminos meta get <seat> <field>")
        if SECRET_RE.search(a.field):
            # The CLI is model-callable; the pipeline reads credentials from the
            # record file directly, never through here.
            die("'%s' is a credential field — not readable through the sminos CLI" % a.field, EXIT_UNKNOWN)
        v = meta_get(s["seat_id"], a.field)
        print(v if isinstance(v, str) else json.dumps(v))
        return
    pairs = ([a.field] if a.field else []) + list(a.values)
    if not pairs or len(pairs) % 2 != 0:
        die("usage: sminos meta set <seat> <field> <value> [<field> <value>...]")
    fields = {pairs[i]: pairs[i + 1] for i in range(0, len(pairs), 2)}
    # Raw field edits are not lifecycle writes, and never recreate a removed seat.
    if not meta_set(s["seat_id"], fields, bump=False, create=False):
        die("seat %s/%s was removed before the write could land" % (s["group"], s["alias"]), EXIT_UNKNOWN)
    print("set %s on %s/%s" % (", ".join(sorted(fields)), s["group"], s["alias"]))


# ------------------------------------------------------------------ dispatch


def usage():
    print((__doc__ or "").strip())


def build_parser():
    p = argparse.ArgumentParser(prog="sminos", add_help=False)
    sub = p.add_subparsers(dest="cmd")

    def route_flags(sp):
        sp.add_argument("--model", default=None)
        sp.add_argument("--settings", default=None)
        sp.add_argument("--effort", default=None)
        sp.add_argument("--wait", action="store_true")

    sp = sub.add_parser("spawn", add_help=False)
    sp.add_argument("alias")
    sp.add_argument("task")
    # Definition flags default to None so a re-fill can tell "not given" (keep
    # the seat's value) from "given as empty". --group and --parent left with
    # the family tree: the project is the group, and there is no parent.
    sp.add_argument("--role", default=None)
    sp.add_argument("--brief", default=None)
    sp.add_argument("--cwd", default="")
    sp.add_argument("--worktree", default="")
    sp.add_argument("--stamp", action="append", default=None,
                    metavar="FIELD=VALUE", help="merge a field into the launch record (repeatable)")
    # The mode the session runs under; `auto` unless a caller bounds it (the
    # desk's spawn RPC passes the machine's ceiling, or a stricter mode).
    sp.add_argument("--permission-mode", default="auto", choices=PERMISSION_MODES)
    sp.add_argument("--no-wait", action="store_true", help="accepted and ignored (no-wait is the default)")
    route_flags(sp)
    sp.set_defaults(fn=cmd_spawn)

    seat = sub.add_parser("seat", add_help=False)
    ssub = seat.add_subparsers(dest="seat_op")
    sa = ssub.add_parser("add", add_help=False)
    sa.add_argument("group")
    sa.add_argument("alias")
    sa.add_argument("--role", default=None)
    sa.add_argument("--brief", default=None)
    sa.add_argument("--session", default="")
    sa.set_defaults(fn=cmd_seat_add)

    f = sub.add_parser("fill", add_help=False)
    f.add_argument("seat")
    f.add_argument("task")
    f.add_argument("--resume", action="store_true")
    route_flags(f)
    f.set_defaults(fn=cmd_fill)

    # `wake` was folded into `send`. Its parser takes any argv — a NUL prefix
    # char never occurs in one, so even `--wait` is a plain word here — and its
    # handler prints the pointer, so no old-shape call reaches a seat lookup.
    w = sub.add_parser("wake", add_help=False, prefix_chars="\0")
    w.add_argument("rest", nargs="*")
    w.set_defaults(fn=cmd_wake)

    rs = sub.add_parser("resume", add_help=False)
    rs.add_argument("seat")
    rs.add_argument("msg")
    route_flags(rs)
    rs.set_defaults(fn=cmd_resume)

    s = sub.add_parser("send", add_help=False)
    s.add_argument("target")
    s.add_argument("msg")
    s.add_argument("--wait", action="store_true")
    s.add_argument("--from", dest="frm", default="")
    s.set_defaults(fn=cmd_send)

    def scope_flags(sp):
        sp.add_argument("--project", dest="projects", type=comma_list, default=[])
        sp.add_argument("--machine", type=comma_list, default=[])
        sp.add_argument("--state", type=state_words, default=[])
        sp.add_argument("--org", action="store_true")
        sp.add_argument("--here", action="store_true")

    say = sub.add_parser("say", add_help=False)
    say.add_argument("text")
    say.add_argument("--in", dest="in_", default="")
    scope_flags(say)
    say.set_defaults(fn=cmd_say, args=[])

    chat = sub.add_parser("chat", add_help=False)
    chat.add_argument("project", nargs="?", default="")
    chat.add_argument("-n", type=int, default=None)
    chat.add_argument("--since", default=None)
    chat.add_argument("--kind", action="append", default=None)
    chat.add_argument("--json", action="store_true")
    chat.add_argument("--host", action="store_true")
    chat.set_defaults(fn=cmd_chat)

    cg = sub.add_parser("charge", add_help=False)
    cg.add_argument("args", nargs="+")
    cg.set_defaults(fn=cmd_charge)

    jn = sub.add_parser("join", add_help=False)
    jn.add_argument("project", nargs="?", default="")
    jn.add_argument("--cwd", action="store_true")
    jn.set_defaults(fn=cmd_join)

    dv = sub.add_parser("derive", add_help=False)
    dv.add_argument("member", nargs="?", default="")
    dv.add_argument("--all", action="store_true")
    dv.add_argument("--refreshes", type=int, default=None)
    dv.set_defaults(fn=cmd_derive)

    nd = sub.add_parser("name-due", add_help=False)
    nd.add_argument("--session", required=True)
    nd.set_defaults(fn=cmd_name_due)

    rec = sub.add_parser("record", add_help=False)
    rec.set_defaults(fn=cmd_record)

    gd = sub.add_parser("guide", add_help=False)
    gd.set_defaults(fn=cmd_guide)

    pj = sub.add_parser("project", add_help=False)
    psub = pj.add_subparsers(dest="op")
    pi = psub.add_parser("init", add_help=False)
    pi.add_argument("--name", default="")
    pi.add_argument("--remote", default="")
    pi.add_argument("--hub", action="store_true")
    pi.set_defaults(fn=cmd_project)
    for op in ("show", "attach"):
        po = psub.add_parser(op, add_help=False)
        po.add_argument("dir", nargs="?", default="")
        po.set_defaults(fn=cmd_project)

    dm = sub.add_parser("daemon", add_help=False)
    dsub = dm.add_subparsers(dest="op")
    dr = dsub.add_parser("run", add_help=False)
    dr.add_argument("--interval", type=float, default=5.0)
    for op in ("tick", "install", "status", "owed", "uplink", "probe"):
        dsub.add_parser(op, add_help=False)
    dp = dsub.add_parser("policy", add_help=False)
    dp.add_argument("--read-only", dest="read_only", choices=("on", "off"), default=None)
    dp.add_argument("--ceiling", default=None)
    dm.set_defaults(fn=cmd_daemon)

    # `hub` takes its words as `wake` does (no word is an option to argparse,
    # so its parse never fails): sminos_hub parses them and never prints one.
    # An enrollment code typed on the command line must not reach argparse's
    # error, which echoes the word it could not place.
    hb = sub.add_parser("hub", add_help=False, prefix_chars="\0")
    hb.add_argument("words", nargs="*")
    hb.set_defaults(fn=cmd_hub)

    rq = sub.add_parser("rpc-query", add_help=False)
    rq.add_argument("op")
    rq.add_argument("--created", default=None)
    rq.set_defaults(fn=cmd_rpc_query)

    br = sub.add_parser("bridge", add_help=False)
    br.add_argument("--session", default="")
    br.add_argument("--lane", default=None)   # the process's lane verdict its module holds (O12 M3)
    br.add_argument("--launch", default=None)   # the process's launch its module minted (O12 M7): `--launch=<id>`
    br.set_defaults(fn=cmd_bridge)

    wa = sub.add_parser("watch", add_help=False)
    wa.add_argument("member")
    wa.add_argument("--json", action="store_true")
    wa.set_defaults(fn=cmd_watch)

    se = sub.add_parser("steer", add_help=False)
    se.add_argument("member")
    se.add_argument("text")
    se.set_defaults(fn=cmd_steer)

    it = sub.add_parser("interrupt", add_help=False)
    it.add_argument("member")
    it.set_defaults(fn=cmd_interrupt)

    st = sub.add_parser("stop", add_help=False)
    st.add_argument("member")
    st.add_argument("task")
    st.set_defaults(fn=cmd_stop)

    mo = sub.add_parser("model", add_help=False)
    mo.add_argument("member")
    mo.add_argument("model")
    mo.add_argument("--effort", default=None, choices=("low", "medium", "high", "xhigh", "max"))
    mo.set_defaults(fn=cmd_model)

    co = sub.add_parser("compact", add_help=False)
    co.add_argument("member")
    co.add_argument("instructions", nargs="?", default="")
    co.set_defaults(fn=cmd_compact)

    cm = sub.add_parser("command", add_help=False)
    cm.add_argument("member")
    cm.add_argument("name")
    cm.add_argument("args", nargs="*")
    cm.set_defaults(fn=cmd_command)

    rd = sub.add_parser("read", add_help=False)
    rd.add_argument("member")
    rd.add_argument("what")
    rd.add_argument("--breakdown", choices=("summary", "full"))
    rd.set_defaults(fn=cmd_read)

    de = sub.add_parser("decide", add_help=False)
    de.add_argument("member")
    de.add_argument("request")
    de.add_argument("behavior", choices=("allow", "deny"))
    de.add_argument("--message", default="")
    de.set_defaults(fn=cmd_decide)

    an = sub.add_parser("answer", add_help=False)
    an.add_argument("member")
    an.add_argument("request")
    an.add_argument("answers", nargs="+")
    an.set_defaults(fn=cmd_answer)

    r = sub.add_parser("reply", add_help=False)
    r.add_argument("seat")
    r.set_defaults(fn=cmd_reply)

    sy = sub.add_parser("sync", add_help=False)
    sy.add_argument("seat", nargs="?", default="")
    sy.add_argument("--all", action="store_true")
    sy.set_defaults(fn=cmd_sync)

    st = sub.add_parser("status", add_help=False)
    st.add_argument("seat")
    st.add_argument("line", nargs="*")
    st.set_defaults(fn=cmd_status)

    rt = sub.add_parser("retire", add_help=False)
    rt.add_argument("seat")
    rt.add_argument("--purge", action="store_true")
    rt.set_defaults(fn=cmd_retire)

    rm = sub.add_parser("remove", add_help=False)
    rm.add_argument("seat")
    rm.set_defaults(fn=cmd_remove)

    def list_flags(sp):
        scope_flags(sp)
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--all", action="store_true")
        sp.add_argument("--stopped", action="store_true")

    ls = sub.add_parser("list", add_help=False)
    ls.add_argument("args", nargs="*")
    list_flags(ls)
    ls.add_argument("--subagents", nargs="?", const="", default=None)
    ls.add_argument("--done", type=int, default=None)
    ls.add_argument("--depth", type=int, default=None)
    ls.add_argument("--stall", type=float, default=None)
    ls.set_defaults(fn=cmd_list, find=False)

    fd = sub.add_parser("find", add_help=False)
    fd.add_argument("args", nargs="+")
    list_flags(fd)
    fd.set_defaults(fn=cmd_find, find=True, subagents=None, done=None)

    wh = sub.add_parser("who", add_help=False)
    wh.add_argument("target", nargs="?", default="")
    wh.add_argument("--session", default="")
    wh.set_defaults(fn=cmd_who)

    pjs = sub.add_parser("projects", add_help=False)
    pjs.add_argument("--all", action="store_true")
    pjs.set_defaults(fn=cmd_projects)

    mcs = sub.add_parser("machines", add_help=False)
    mcs.set_defaults(fn=cmd_machines)

    ch = sub.add_parser("chart", add_help=False)
    ch.add_argument("project", nargs="?", default="")
    ch.add_argument("--all", action="store_true")
    ch.add_argument("--stopped", action="store_true")
    ch.add_argument("--width", type=int, default=0)
    ch.set_defaults(fn=cmd_chart)

    tu = sub.add_parser("tui", add_help=False)
    tu.add_argument("project", nargs="?", default="")
    tu.add_argument("--all", action="store_true")
    tu.add_argument("--headless", action="store_true")
    tu.add_argument("--keys", default="")
    tu.add_argument("--width", type=int, default=0)
    tu.add_argument("--height", type=int, default=0)
    tu.add_argument("--no-tmux", dest="no_tmux", action="store_true")
    tu.set_defaults(fn=cmd_tui)

    at = sub.add_parser("attach", add_help=False)
    at.add_argument("seat")
    at.set_defaults(fn=cmd_attach)

    mg = sub.add_parser("migrate", add_help=False)
    mg.add_argument("--quiet", action="store_true")
    mg.set_defaults(fn=None)

    me = sub.add_parser("meta", add_help=False)
    me.add_argument("op", choices=["get", "set"])
    me.add_argument("seat")
    me.add_argument("field", nargs="?", default="")
    me.add_argument("values", nargs="*")
    me.set_defaults(fn=cmd_meta)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        usage()
        sys.exit(0 if argv else EXIT_USAGE)
    parser = build_parser()
    try:
        a = parser.parse_args(argv)
    except SystemExit:
        sys.exit(EXIT_USAGE)
    if a.cmd == "migrate":
        did = migrate(quiet=True)
        if did and not a.quiet:
            print("sminos: migrated: %s" % "; ".join(did))
        return
    if a.cmd == "record":
        run_record()
        return
    if a.cmd == "bridge":
        # A session's own child, started in every session: it reads no
        # registry, so it runs no migration (which takes the registry's lock).
        cmd_bridge(a)
        return
    if a.cmd == "guide":
        # A SessionStart hook's: the record hook beside it migrates, bounded;
        # a session's start never waits here on the registry's lock.
        cmd_guide(a)
        return
    if a.cmd == "rpc-query":
        # A diagnostic: it reads the RPC ledger's file and changes nothing,
        # so no migration rewrites a record or takes the registry's lock.
        cmd_rpc_query(a)
        return
    if a.cmd == "daemon" and a.op == "owed":
        # B2's gate on a machine about to cut over (O14), run beside its
        # daemon: it reads what is owed and never migrates or takes a lock.
        cmd_daemon(a)
        return
    if a.cmd == "who" and not a.target:
        # The address mod's, before a session's model requests: it reads and
        # never migrates, and never waits on the registry's lock.
        cmd_who(a)
        return
    if not getattr(a, "fn", None):
        if a.cmd == "seat":
            die("usage: sminos seat add <group> <alias> [--role R] [--brief B] [--session S]")
        if a.cmd == "project":
            die("usage: sminos project init [--name N] [--remote URL] [--hub] | show [DIR] | attach [DIR]")
        die("unknown command: %s (try: sminos help)" % argv[0])
    migrate()
    HINTS["on"] = a.cmd in READING_VERBS
    try:
        a.fn(a)
    except LogWriteFailed as e:
        die("%s completed, but %s" % (a.cmd, e), 1)


if __name__ == "__main__":
    main()
