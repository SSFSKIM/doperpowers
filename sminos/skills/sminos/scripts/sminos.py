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
member too, seat-less, from the first call that reads its project, and stays
one when its process ends: stopped. A message addressed to a stopped session,
of either kind, wakes it: its process is started again in the background under
the same id, with no message, and the message is then pushed to it, followed by
a `[sminos] ` line telling it that it was woken and that its human is not
watching. One its machine does not wake (its directory or its conversation
gone, another config dir, a session its human opened in or above a folder
macOS protects, $HOME among them, a mode that asks for approval, its own or
a first wake's capped by the machine's ceiling, a wake that failed, a launch
whose process never came up included, tried again at widening intervals)
holds the message until a process of it runs before it ends, and the sender
is told why. After a /clear the new session takes its alias, and the one left
goes by its short id. A
session ends when it is retired, or once it has been stopped for three days
(while a devcloud host of its own remains, or devcloud cannot tell, it stays
stopped instead); what was held for it is then settled, and a message to it
is refused. Its human reopening it brings it back as itself; a seat comes
back by a fill.

    sminos spawn    <alias> <task> [--role R] [--brief B] [--cwd C] [--worktree W]
                   [--model M] [--settings S] [--effort E] [--wait]   # a background session in a seat
                   of this project (--cwd's); --brief is its in-charge line until its first derived one; --wait prints the reply.
                   --wait only watches, for DAEMON_TIMEOUT (default 18000 s): the seat works on after,
                   and `reply` reads its live transcript
    sminos seat add <group> <alias> [--role R] [--brief B] [--session S]   # register a vacant seat for a
                   later fill, or, with --session, give a running session a seat (refused for a session
                   its human opened that is already a member: its own record keeps it)
    sminos fill     <seat> <task> [--resume] [--model M] [--settings S] [--effort E] [--wait]
                   # a fresh session in the seat; --resume continues its saved one
    sminos resume   <seat|member> <msg> [--wait]          # process-level continuation: a live background turn is
                   stopped first, only once its wake is read to start it again
                   A seat or a session its human opened alike: the message recorded, the session woken and
                   the message pushed; one its machine does not wake records it, starts nothing, says why
                   and exits 4 (the daemon pushes it when a process of it runs). Whenever the message is
                   left owed and not pushed, whatever the exit, a line `owed: <session id>` says so (for a
                   script). A fresh fill of a session its human opened is refused, and so is fill --resume
                   of a live one.
                   A retired seat is resumed by fill --resume alone (resume refuses it, exit 4).
                   A resumed background session keeps its SAVED options (name, permission
                   mode, model, settings, effort): --model/--settings/--effort are accepted
                   on resume for argv compatibility but ignored — use fill without --resume
                   to change them.
    sminos send     <member|session name|codex thread> <msg> [--wait] [--from F]
                   # a live member: inbox socket; a stopped one: woken, or recorded and held (with
                   # --wait, exit 4: nothing is started). --wait prints the reply to this message: what
                   # follows its row, or the bridge's wake naming it, up to the next prompt that starts a
                   # turn. On a machine not enrolled, a live session in
                   # no project by its name; a codex thread (its id, or codex:<id|exact name>, through
                   # codex's queue); --wait needs a seat or a thread of this machine.
    sminos say      [--in <project>] <text>                # untagged: recorded; @alias / @"a b" / @alias#short /
                   @short / @project/alias: delivered; @all: every live member
    sminos say      [--org] [--project P,..] [--machine M,..] [--here] [--state W,..] <text>   # list's filters:
                   every live session of that scope but you (`list` with the same flags shows them), each woken
                   as @all wakes; recorded in each project it reaches, copied into yours; no @tags beside it
    sminos chat     [<project>] [-n N] [--since TS] [--kind K] [--json]   # no flags: unread, advancing the cursor
    sminos chat     [<project>] --host [-n N] [--since TS] [--json]       # what the members sent their human
    sminos charge   [<member>] "<one line>"               # what the member is in charge of, until its next
                   derived line: the line is derived in the background (derive), so sessions are not taught this
    sminos join     <project> | --cwd                     # this session's project, declared: a session is in
                   its launch directory's project (a `cd` moves nothing) until it joins another; --cwd goes
                   back; alone: which project it is in, and why. Not for a seat
    sminos derive   <member> | --all [--refreshes N]      # ask a session its line, by its bridge's side question
                   (btw), else a headless internal fork, once its model made ten tool calls; a session under a
                   name the engine made up (or one sminos gave it) is also asked for a charge name, handed to
                   its name mod as $SMINOS_HOME/names/<session>.json. --all (the daemon's, every five
                   minutes) derives first lines before refreshes and holds a member whose fork failed out for
                   an hour; --refreshes caps the members with a line it forks (the daemon passes 2), oldest
                   line first
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
    sminos hub      show                                  # this machine's name, hub and org, as its endpoint
                   gave them at its latest welcome: its name there is its name everywhere (the writer host
                   of what it writes). Enrolling is the endpoint's: mawsd endpoint enroll|status
    sminos rpc-query [--created T] -- <opId>              # what became of a desk RPC, as the daemon's ledger
                   file holds it (RL4's query, JSON): done, refused, in-progress, expired, not-received;
                   --created, its opCreated. `--` before the id: a base64url id may start with `-`.
                   The file alone: one a worker holds before its claim reads not-received here. It
                   changes nothing
    sminos reply    <seat|member>                         # latest reply text (a seat-less session's: its transcript's)
    sminos sync     [<seat>] [--all]                      # reconcile status from the harness
    sminos status   <member> <one line>                   # the member's own "now" line
    sminos retire   <member> [--purge] [--owner-unknown]  # end it (recorded first), then stop what can be
                   stopped; --purge deletes its record (a seat's, or a session its human opened). Refused for
                   a session that made a devcloud host that still exists (naming it: devcloud vm down <name>),
                   and when devcloud cannot tell; --owner-unknown retires it then, for a person at a terminal
    sminos access   <member> private|listed|org-view|org-converse   # who may reach a session of this
                   machine: private, its owners' agents and its shares'; listed or org-wide, every member's
    sminos share    <member> <person> list|view|converse|approve|none   # a member's grade on it (<person> an
                   org member id, or an email this machine holds one for); list ("Can message") lets their
                   agents message it, view and up read it too. Narrowing is any shell's; widening (access up,
                   a share added or raised) only the owner's, in a terminal, confirmed there, or MAWS
    sminos remove   <seat|member>                         # retire --purge: end it, stop it, delete its record
    sminos list     [project] [--project P,..] [--machine M,..] [--state W,..] [--org] [--here] [--stopped] [--all] [--json]
                   [words..]  # the caller's project (a session's own, else the working directory's;
                   every project from none); any filter
                   widens to every project known here, then narrows: --machine by prefix, words (all of
                   them) in the alias, short, project, repo, branch, in-charge, now line or title; --org
                   every project; --here this machine, plus every running session in no project.
                   W: busy idle waiting stopped gone vacant retired; stopped, retired and gone fold into a
                   "+N hidden" tail; --stopped adds stopped, --all shows all, --state selects named states.
                   A session that ended (retired, or stopped three days) is shown only by --all or
                   --state retired, saying why.
                   A row: alias [short], kind, state,
                   @machine, (project,) repo@branch, in charge (age), · active <age>. Inside a session
                   it says who you are and ends with how many of your subagents run (list --subagents
                   for them); --here ends with the live sessions that are no member
    sminos list     --subagents [member] [--done N] [--depth N] [--stall MIN] [--all] [--json]
                   # your session's subagents (a member's on this machine: inspection only), in place of
                   ListAgents: how many run, wait on background or stall, at every depth, those as a
                   tree, each with its lifecycle, its source (the engine through the bridge, else the
                   disk) and what it does (in Bash 12m, no write 14m); then the ones ended in the last
                   10 minutes (5 at most, newest first: completed 3m ago), and "+N done (on disk)" for
                   every other one, ended or orphaned, an earlier process's counted without being read;
                   --all every agent with its lifecycle (running, waiting on background, stalled,
                   orphaned; completed, failed, stopped) and the counts of each; --done N the N ended
                   last, newest first, with their outcome (SendMessage to an agentId resumes it);
                   --depth N the top N levels, a row saying what it folds; --stall MIN (10) the quiet
                   that makes an open turn stalled when only the disk speaks;
                   --json {self, scope, counts, agents, notes}, every agent whatever its state
    sminos find     <words..>                             # list --org <words>: every session they match
    sminos who      [<commit|PR>] [--session S]           # the session a commit (its Sminos-Session trailer)
                   or a PR (its body's last line, else its commits' trailers; a number or URL, through gh)
                   was made by, as it is now: alias, project, machine, state, the session it went on as,
                   how to reach or resume it. Alone, inside a session: the line its commits carry
    sminos projects [--all]                               # every project known here: kind (hub, machine,
                   local), live and waiting sessions, their machines; --all: a retired machine's too
    sminos machines                                       # every machine enrolled in the org: its newest
                   event (the endpoint says nothing of who is online), or retired; its live sessions and
                   their projects
    sminos chart    [project] [--stopped] [--all] [--width N]        # the members as boxes, grouped by project
    sminos tui      [project] [--all] [--no-tmux]        # the chart, interactive, inside tmux: arrows move, enter attaches
    sminos attach   <seat>                                # claude attach <short>
    sminos migrate  [--quiet]                             # (also runs implicitly)
    sminos meta     get <seat> <field> | set <seat> <field> <value> [<field> <value>...]
                   # read or write a seat record's fields under the record lock (the board pipeline's
                   ticket, role, run_id...); never a credential

A verb's prose given as `-` is read from standard input (say's <text>, send's and
resume's <msg>, spawn's and fill's <task>, steer's <text>, compact's [instructions]):
inside double quotes the shell runs a backtick span and expands a `$` before sminos
sees the text, where a heredoc with a quoted delimiter passes it as written:

    sminos say - <<'EOF'
    @parser `parse()` now rejects "" in `name`
    EOF

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
`group/alias`. Scripts may pass a full seat id or session id. A session a
member went on from — one it handed to a background job, a seat's earlier
occupant — is named, as `@short`, `alias#short` or its full id, by the
session the member is now, unless it runs again: then it is a member of its
own, and its id names it.

Messaging is one verb, `send`: to a live seat it writes a frame to the
session's inbox socket — the socket the harness's native cross-session
SendMessage tool also rides, wrapped in that tool's own envelope — which the
harness delivers as a peer message (an idle session starts a new turn, a busy
one reads it at its next tool round); a stopped one is woken first, and the
frame pushed to it as to a live one. A peer's message always takes the inbox. The owner's
(owner_event) takes a session's bridge (the bridge mod) instead, as the
human's words, submitted once per log event however often it is delivered,
and a --bg job with no bridge takes it through the engine supervisor's
`reply`. `resume` is
the process-level continuation the board pipeline relays through: a wake
(`claude --bg --resume <id>` with no message, in the environment the
engine's background launch gives it, not the terminal's it was opened in)
and the push of its message.

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
import types
import unicodedata
import uuid as uuidlib
from contextlib import ExitStack, contextmanager
from fractions import Fraction
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
# A declared channel's id (CH1 of docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md, C4; the parent's
# D3): a UUID of version 8 with RFC 9562's variant, which no project's id is (minted version 4, derived version 5).
# MAWS's isChannelId, held to the shared vectors' `ids` (sminos/tests/vectors/maws/channel-rule.json).
CHANNEL_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-8[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def is_channel_id(value):
    """Whether `value` is a declared channel's id: a str CHANNEL_ID_RE
    matches whole. No I/O: a channel is told from a project by its id alone,
    wherever the id came from (the org's directory, a .smns, a join
    override, an argument)."""
    return isinstance(value, str) and CHANNEL_ID_RE.fullmatch(value) is not None
# A seat's one state word — see state(). FILLED: a live session holds the
# seat. REFILLABLE: no live turn is attached, so a fresh fill may take it.
STATES = ("busy", "idle", "waiting", "stopped", "gone", "vacant", "retired")
FILLED = ("busy", "idle", "waiting")
REFILLABLE = ("vacant", "stopped", "gone")
# HIDDEN is display-only: list, chart, and tui fold these state words.
# A stopped seat can still be resumed by sending to it.
HIDDEN = ("stopped", "retired", "gone")
# The states whose `state` event says whether the thread's machine wakes it (X3): stopped, and a `gone` thread that
# has not ended (its conversation is not on its machine), its `why` read as a stopped one's.
HELD_STATES = ("stopped", "gone")
# The reasons of a `retired` that ends a thread (T1's M4), whoever wrote it: an explicit retire, and the end by
# the rule (and a lane B session's with its process). A session whose membership in effect is one has ended.
END_REASONS = ("retire", "ended")
# What a seat's record loses when its occupant is replaced (a refill): an end, the stop mark of the session
# that left (its clock is not the new session's: §6, row 8), and what its wakes kept (`waking`, T2's §7).
REPLACED_DROPS = ("ended", "stopped", "swept", "waking")
TERMINAL = ("done", "done-blocked", "blocked", "failed", "stopped", "error")
# Model-visible surfaces never carry a credential: the pipeline colonizes the
# record with run_bearer and friends, and a seat's JSON is read by agents.
SECRET_RE = re.compile(r"bearer|token|secret", re.I)


def public_seat(s):
    """A seat dict with the task body, any secret-shaped field and the
    thread record's keys (sminos_threads.SEAT_KEYS: its earlier sessions,
    its launch's options, an open entry's events) removed — for every
    model-facing surface (list, list --json, chart). A member's row carries
    its `thread` and `opened`."""
    hidden = threads_module().SEAT_KEYS
    return {k: v for k, v in s.items() if k != "task" and k not in hidden and not SECRET_RE.search(k)}


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
    return bool(n) and n not in (".", "..") and bool(NAME_RE.fullmatch(n))


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
        lambda s: s["alias"] == q and (scope is None or getattr(seat_project(s), "id", None) == scope.id),
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
# A delivery to a `gate` process (O12 M4b) handed to its inbox with a
# receipt, or waiting for it: owed until the receipt's admission, no attempt
# counted. "held:<why>": its process's mode cannot be read (fail closed).
HOLDER_AWAITING = "awaiting-admission"
# A session's membership is its latest of these, in its own file, by seq.
MEMBERSHIP = ("joined", "retired")
# The facts about a session the projection reads; whoever writes one for a
# session on its machine appends it to that session's file. `unlisted` is a
# session's transition notice (P5 O18 D6): the members it is addressed to no
# longer see the session. `channels` is a thread's statement of the declared
# channels it is in (CH1's C2), which only its thread's journaled operation
# writes (sminos_threads.set_channels, through finish).
LIFECYCLE = MEMBERSHIP + ("renamed", "state", "titled", "in-charge", "status", "unlisted", "channels")
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


# ------------------------------------------- macOS's protected folders
#
# On macOS the first look a process takes inside a folder the privacy system
# (TCC) protects asks the person, in a dialog charged to the responsible
# process: for the daemon, a launchd agent, the daemon itself, whose grants
# are not the Terminal's, and the dialog waits for someone at the screen (the
# Mac mini's CI runner, 2026-11-07, held by one raised for derive's fork in
# $HOME, which the engine's startup scans). So a sminos process reads inside
# such a folder only when its own working directory is inside the same one —
# a session's CLI and hooks, run where the session works under the grant it
# holds — and a child it starts on its own initiative starts neither inside
# one nor above one (launch_refused). Inside-ness is the absolute path's
# string alone: any look at the path would be the touch. What a refused read
# would have resolved is told from what this machine recorded (Guessed).

TCC = sys.platform == "darwin"   # whether this platform's privacy folders ask (the tests set it)
PROTECTED_IN_HOME = ("Desktop", "Documents", "Downloads", "Library/Mobile Documents", "Library/CloudStorage")
_GUARD = threading.local()       # .refused: the reads this thread was refused, which taint a resolution


def _abs(path):
    return os.path.abspath(os.path.expanduser(path))


def _under(path, folder):
    """Whether `path` is `folder` or inside it, by string, case-blind as
    macOS's file system is."""
    p, f = path.casefold(), folder.casefold().rstrip("/")
    return p == f or p.startswith(f + "/")


def protected_folders():
    home = os.path.expanduser("~")
    return [os.path.join(home, f) for f in PROTECTED_IN_HOME]


def protected_folder(path):
    """The protected folder an absolute path is in, or is ("/Volumes/<name>"
    for a volume's), or ""."""
    for f in protected_folders():
        if _under(path, f):
            return f
    parts = path.split("/")
    return "/".join(parts[:3]) if len(parts) > 2 and parts[1].casefold() == "volumes" and parts[2] else ""


def _own_cwd():
    try:
        return os.getcwd()
    except OSError:
        return ""   # an unreadable working directory is outside every folder


def withheld(path):
    """Whether this process may not look at `path` (read_refused), asked
    without counting a refusal: for a look that is only skipped when it
    would be refused, and decides nothing on its own. The working
    directory is asked only for a path inside a protected folder (macOS's
    getcwd is five calls): outside every one it cannot be why a look is
    refused."""
    if not TCC or not path:
        return False
    folder = protected_folder(_abs(path))
    if not folder:
        return False
    here = _own_cwd()
    return not (here and _under(here, folder))


def read_refused(path):
    """Whether this process may not look at `path`: on macOS, it is in a
    protected folder its own working directory is not in. Each refusal is
    counted for the thread (refusals), so a resolution that met one reads as
    told rather than read."""
    if not withheld(path):
        return False
    _GUARD.refused = refusals() + 1
    return True


def refusals():
    return getattr(_GUARD, "refused", 0)


def git_refused(d):
    """Whether git run in `d`, or a read through its checkout's metadata,
    would look where this process may not (read_refused): `d` itself, or
    the gitdir a linked worktree's `.git` file names, or that gitdir's
    commondir. The `.git` file is read where it is, beside the checkout,
    never followed first. Every site that runs git in, or reads git's files
    for, a session's directory asks this."""
    if not TCC:
        return False
    d = _abs(d)
    if read_refused(d):
        return True
    while True:
        dot = os.path.join(d, ".git")
        if os.path.isdir(dot):
            return False
        if os.path.isfile(dot):
            try:
                with open(dot) as f:
                    line = f.readline().strip()
            except OSError:
                return False
            if not line.startswith("gitdir:"):
                return False
            gitdir = os.path.join(d, line[len("gitdir:"):].strip())
            if read_refused(gitdir):
                return True
            try:
                with open(os.path.join(gitdir, "commondir")) as f:
                    common = f.read().strip()
            except OSError:
                return False
            return bool(common) and read_refused(os.path.join(gitdir, common))
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def launch_refused(d):
    """Why a child sminos starts on its own initiative may not start in `d`,
    or "": on macOS, `d` is in a protected folder this process's working
    directory is not in, or holds one ($HOME, /Users, /, /Volumes, a
    folder's other ancestors), where the engine's startup scan of its
    directory's children reaches into it — unless `d` is this process's own
    working directory."""
    if not TCC or not d:
        return ""
    d, here = _abs(d), _own_cwd()
    if here and here.casefold().rstrip("/") == d.casefold().rstrip("/"):
        return ""
    folder = protected_folder(d)
    if folder:
        return "" if here and _under(here, folder) else \
            "its directory is in %s, which macOS asks the person about before anyone reads it" % folder
    held = protected_held(d)
    return "its directory holds %s, which macOS asks the person about before anyone reads it" % held if held else ""


def protected_held(d):
    """The protected folder an absolute directory holds, or "": $HOME,
    /Users, / and a folder's other ancestors hold one, /Volumes its
    volumes. A launch there reaches into it, since the engine's startup
    scans its directory's children."""
    return next((f for f in protected_folders() + ["/Volumes"] if _under(f, d)), "")


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
            if read_refused(gitdir):
                return ""   # a linked worktree whose repository is in a protected folder: not read
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
    removed worktree still resolves. "" outside git, and for a directory
    this process may not read (read_refused). Read off the filesystem
    when it can be: every reading verb resolves the cwd of every seat and
    live session, and a process per directory adds up."""
    d = os.path.abspath(cwd)
    if read_refused(d):
        return ""
    while not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent
    common = _common_git_dir_fs(d)
    if common is not None:
        return common
    if git_refused(d):
        return ""
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
        d = json_at(path)   # resolved again each cache generation: a stat while the file holds still
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
    names a hub (well-formed or not: either bars git); None, unknown, for a
    root this process may not read (read_refused)."""
    if read_refused(root):
        return None
    path = os.path.join(root, SMNS) if root else ""
    smns = read_smns(path) if path and os.path.isfile(path) else None
    return smns is not None and smns[0] == pid and smns[3] is not None


def registration(pid):
    """A project's project.json as it is now (project_path), or {}."""
    try:
        d = json_at(os.path.join(projects_root(), pid, "project.json"))
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
# On an enrolled machine (daemon/identity.json names a hub, an org and a machine)
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
    daemon/identity.json's, the identity its endpoint gave at a welcome
    (sminos_rl10.cutover); None when it is not enrolled (no identity.json,
    or one that cannot be read as an identity). A hub.json is none."""
    if not _ENROLLED:
        ident = sibling_module("sminos_rl10").cutover()
        _ENROLLED.append({"url": ident["hub"], "org": ident["org"], "machine": ident["name"]}
                         if ident is not None else None)
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
    latest `org` frame, with `retired` the names (lower-cased) of the machines
    it retires (machine_retired), `locations` the stored statements its
    `locations` carries (_stated) and `declared` every declared location
    that counts (_declared) — or None before the first (or when it is
    unreadable)."""
    if not _ORG_DIR:
        try:
            d = json_at(org_path())   # the uplink writes it whole, by rename
        except (OSError, ValueError):
            d = None
        ok = isinstance(d, dict) and isinstance(d.get("projects"), list) and isinstance(d.get("machines"), list)
        if ok:
            projects = [p for p in d["projects"] if isinstance(p, dict) and isinstance(p.get("id"), str)]
            machines = [m for m in d["machines"] if isinstance(m, dict) and isinstance(m.get("name"), str)]
            retired = {m["name"] for m in machines if m.get("retired") is True}
            retired |= {str(p.get("machine") or p.get("name") or "") for p in projects   # a channel by its id first
                        if p.get("kind") == "machine" and p.get("retired") is True and not is_channel_id(p["id"])}
            d = {"projects": projects, "machines": machines, "at": str(d.get("at") or ""),
                 "retired": frozenset(n.lower() for n in retired if n), "locations": _stated(d.get("locations")),
                 "declared": _declared(d.get("locations"))}
        _ORG_DIR.append(d if ok else None)
    return _ORG_DIR[0]


def org_entry(pid):
    """The org directory's entry for a project, or None."""
    d = org_directory()
    return next((p for p in d["projects"] if p["id"] == pid), None) if d else None


def org_retired(pid):
    """Whether the org's directory marks the project retired (a revoked
    machine's project). With no directory yet, nothing is."""
    return (org_entry(pid) or {}).get("retired") is True


LEAVING_FILE = "leaving.json"
_LEFT = []    # [the ids daemon/leaving.json's kept set holds], per invocation


def leaving_path():
    return os.path.join(root(), "daemon", LEAVING_FILE)


def leaving_kept():
    """daemon/leaving.json as the uplink keeps it (the project registry's
    §E.4, sminos_uplink.Leaving): {counted: {project id: seconds counted},
    left: [project ids]}; both empty with no file or one that cannot be
    read."""
    try:
        d = json_at(leaving_path())   # written whole, by rename
    except (OSError, ValueError):
        d = None
    d = d if isinstance(d, dict) else {}
    counted = d.get("counted") if isinstance(d.get("counted"), dict) else {}
    left = d.get("left") if isinstance(d.get("left"), list) else []
    return {"counted": {k: float(v) for k, v in counted.items()
                        if isinstance(k, str) and type(v) in (int, float) and v >= 0},
            "left": [x for x in left if isinstance(x, str)]}


def has_left(p):
    """Whether a project has left this machine (§E.4): a followed project
    with no folder here that complete directories lacked for the counted
    period, its id in the uplink's kept set. The uplink's subscription
    (hub_projects) and the org scope (org_scope, list's widened scope) both
    leave it out; its log stays, and a directory that lists it again, or a
    folder or a session of it here, takes it out of the set (the uplink's
    scan)."""
    if not _LEFT:
        _LEFT.append(frozenset(leaving_kept()["left"]))
    return p.id in _LEFT[0]


def machine_retired(name):
    """Whether the org's directory retires machine `name`: its `machines`
    entry says `retired: true` (RL10's endpoint, for a machine no certificate
    stands for any more, such as a deleted VM) or its machine project is
    retired (the hub retires a revoked machine's). Names compare lower-cased,
    as the hub compares them. A directory that says neither (an older
    endpoint's), or none yet, retires no machine."""
    d = org_directory()
    return d is not None and str(name or "").lower() in d["retired"]


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
                 "(mawsd endpoint enroll)" % (name, hub["org"], " in it" if e else ""))
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


# ------------------------------------------- one rule for a directory's project
#
# Design §8 of docs/doperpowers/specs/2026-11-10-project-registry-design.md
# (MAWS), which MAWS's deriveOrg applies too; the two are held to one vector
# file, sminos/tests/vectors/maws/project-rule.json (project_rule_parity.py).
# Walking up from a directory, the nearer of a .smns and a stored statement
# decides (at one folder a link, then a minted id, then the file), a statement
# above a repository that derives a remote not counting; else the remote;
# else the machine's own project. A linked worktree is in its main checkout's
# project: that checkout's own statement first, then a .smns on the
# worktree's path, then the rule at the main checkout. The stored statements
# are this machine's declared locations as its endpoint last sent them, kept
# in org.json's `locations` (stated_here); with none kept the walk is today's,
# over the path as given, and with them over its canonical form (the real
# path, NFC), the form MAWS writes a statement's path in.

BIRTH_SLACK_NS = 1000   # an anchor's birth equals a reading within this (Python's float of seconds, Node's integer)


class Decision(NamedTuple):
    by: str           # link | minted | smns | remote | machine | local, or "" for no project
    at: str           # the folder that decided ("" for machine and none): for remote, the main checkout
    project: Optional[Project]


def canonical(path):
    """A path in the form both sides compare: the real path, NFC."""
    return unicodedata.normalize("NFC", os.path.realpath(path))


def birth_ns(seconds):
    """A birth time in nanoseconds, exactly the float of seconds Python
    reads (a Fraction: a float times 1e9 would round), or None for none."""
    return Fraction(seconds) * 1_000_000_000 if seconds else None


def anchor_same(anchor, dev, ino, birth):
    """Whether a folder read as (dev, ino, birth in ns or None) is the one
    a statement's anchor names (§D): device and inode exactly, and the birth
    within BIRTH_SLACK_NS only where both sides have one (Python on Linux
    reads none; a filesystem with none writes "0")."""
    if anchor["dev"] != str(dev) or anchor["ino"] != str(ino):
        return False
    a = int(anchor["birth"])
    return not (a and birth) or abs(birth - a) <= BIRTH_SLACK_NS


def _stated(raw):
    """{canonical path: (by, project id, anchor)} of an org file's
    `locations`, the entries a stored statement decides at and that still
    count (not `replaced`, an anchor that reads), or None when the file
    holds no `locations` (an endpoint that sends none). One naming a
    channel's id is none, its folder resolving as if it were absent (CH1,
    the holder's ruling): a channel is no folder's project."""
    if not isinstance(raw, dict) or not isinstance(raw.get("at"), list):
        return None
    out = {}
    for e in raw["at"]:
        if not isinstance(e, dict) or e.get("stated") not in ("minted", "linked") or e.get("state") == "replaced":
            continue
        path, pid, anchor = e.get("path"), e.get("project"), e.get("anchor")
        if not (isinstance(path, str) and path.startswith("/") and isinstance(pid, str) and valid_name(pid)
                and not is_channel_id(pid) and isinstance(anchor, dict)
                and all(isinstance(anchor.get(k), str) and re.fullmatch(r"[0-9]+", anchor[k])
                        for k in ("dev", "ino", "birth"))):
            continue
        out.setdefault(unicodedata.normalize("NFC", path),
                       ("link" if e["stated"] == "linked" else "minted", pid, anchor))
    return out


def stated_here():
    """This machine's stored statements (_stated) from the kept org file,
    on an enrolled machine: {} for a `locations` that holds none, None where
    the file holds no `locations`."""
    d = org_directory() if enrollment() is not None else None
    return d["locations"] if d else None


_UNKNOWN = []   # locations_unknown's answer, per cache generation


def locations_unknown():
    """Whether this machine's stored statements are not known yet (the
    registry's constraint 4, §E.3): it is enrolled, the last welcome its
    endpoint gave listed `locations` (kept in daemon/audiences.json at every
    welcome), and the kept org file holds no `locations` — no frame since
    the upgrade, or the file gone. Files alone would then decide what the
    statements may contradict a moment later, so a session keeps the
    project it is recorded in (_session_project). Beside an endpoint that
    lists no such capability, or none known, this is never so."""
    if not _UNKNOWN:
        _UNKNOWN.append(enrollment() is not None and stated_here() is None
                        and sibling_module("sminos_audience").advertised("locations"))
    return _UNKNOWN[0]


class Declared(NamedTuple):
    path: str       # canonical, as MAWS writes it
    project: str    # the rule's answer as MAWS holds it
    hub: bool       # False where the entry says `hub: false` (its .smns names no hub of this org)


def _declared(raw):
    """[Declared] of an org file's `locations`: every entry that is neither
    `missing` nor `replaced` (§E.2), whatever decided its project; None when
    the file holds no `locations`."""
    if not isinstance(raw, dict) or not isinstance(raw.get("at"), list):
        return None
    out = []
    for e in raw["at"]:
        if not isinstance(e, dict) or e.get("state") in ("missing", "replaced"):
            continue
        path, pid = e.get("path"), e.get("project")
        if isinstance(path, str) and path.startswith("/") and isinstance(pid, str) and valid_name(pid):
            out.append(Declared(unicodedata.normalize("NFC", path), pid, e.get("hub") is not False))
    return out


def declared_here(pid=None):
    """This machine's declared locations (_declared) from the kept org file,
    on an enrolled machine — of project `pid` alone when given — [] where
    the file holds none."""
    d = org_directory() if enrollment() is not None else None
    return [x for x in (d["declared"] or ()) if pid is None or x.project == pid] if d else []


def register_declared():
    """Register each declared location's project rooted there with this
    org's hub (§E.2), so the uplink holds it rather than follows it: an
    entry that says `hub: false` keeps the registration and transport its
    .smns gives (registering it with the hub would rewrite its transport),
    and one in this machine's own project registers nothing. Only where the
    folder resolves here to the entry's project as a hub project of this
    org; of several locations of one project the registered root stands
    while it is still the project's (kept_root)."""
    e = enrollment()
    if e is None:
        return
    own = machine_project_id(e["org"], e["machine"])
    for loc in declared_here():
        if not loc.hub or loc.project == own or read_refused(loc.path) or not os.path.isdir(loc.path):
            continue
        p = resolve_project(loc.path)
        if p is None or p.id != loc.project or not (isinstance(p.hub, dict) and p.hub.get("org") == e["org"]):
            continue
        # Looked at again whatever used the home in this cache generation
        # (an upload's callback on a followed, rootless registration):
        # project_path writes only what differs.
        _HOMES.discard(p.id)
        project_path(p._replace(root=loc.path), "log")


def statement_at(stated, d):
    """The stored statement that counts at folder `d` as the walk reached
    it: (by, project id), or None — none there, or the folder now at its
    path is not the one it was made on (its anchor)."""
    s = stated.get(unicodedata.normalize("NFC", d))
    if s is None:
        return None
    try:
        st = os.stat(d)
    except OSError:
        return None
    return s[:2] if anchor_same(s[2], st.st_dev, st.st_ino, birth_ns(getattr(st, "st_birthtime", 0))) else None


def _smns_in(d):
    path = os.path.join(d, SMNS)
    return read_smns(path) if os.path.isfile(path) else None


def _ancestors(d, stop=""):
    """`d` and each folder above it, up to `stop` (not included) or `/`."""
    while d != stop:
        yield d
        parent = os.path.dirname(d)
        if parent == d:
            return
        d = parent


def _checkout_root(d):
    """The folder holding the nearest `.git` (a directory, or a linked
    worktree's file) at or above `d`, or "" outside git."""
    return next((x for x in _ancestors(d) if os.path.lexists(os.path.join(x, ".git"))), "")


def _git_bare(common):
    """Whether a common git dir's config says `core.bare` is true."""
    try:
        text = file_bytes(os.path.join(common, "config")).decode("utf-8-sig", "replace")
    except OSError:
        return False
    section = ""
    for line in text.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
        elif section == "core" and "=" in line:
            k, v = (x.strip().lower() for x in line.split("=", 1))
            if k == "bare":
                return v in ("true", "yes", "on", "1")
    return False


def main_checkout(common):
    """The main checkout whose common git dir is `common`, or "": a bare
    repository has none (its common dir no `<main>/.git`, or `core.bare`)."""
    if not common or os.path.basename(common) != ".git" or _git_bare(common):
        return ""
    return os.path.dirname(common)


def _within(d, folder):
    return d == folder or d.startswith(folder.rstrip("/") + "/")


def worktree_main(d):
    """The main checkout of the linked worktree `d` is in — its nearest
    `.git` a file naming a gitdir that has a `commondir`, which is a main
    checkout's (main_checkout) — or ""; "" too where that gitdir is one
    this process may not read (read_refused)."""
    top = _checkout_root(d)
    dot = os.path.join(top, ".git") if top else ""
    if not dot or not os.path.isfile(dot):
        return ""
    try:
        with open(dot) as f:
            line = f.readline().strip()
    except OSError:
        return ""
    if not line.startswith("gitdir:"):
        return ""
    gitdir = os.path.join(top, line[len("gitdir:"):].strip())
    if read_refused(gitdir):
        return ""
    try:
        with open(os.path.join(gitdir, "commondir")) as f:
            common = f.read().strip()
    except OSError:
        return ""
    return main_checkout(os.path.abspath(os.path.join(gitdir, common))) if common else ""


def worktree_stop(d):
    """For a directory in a linked worktree, the first folder above it that
    holds the worktree's gitdir (git keeps it at <common dir>/worktrees/<id>:
    for a main checkout's worktree, the checkout itself, or the first folder
    the worktree shares with it); "" for any other directory. A .smns on the
    worktree's own path is one below it. A `.git` file is a linked worktree
    only where its gitdir holds a `commondir`: a checkout whose git dir lives
    elsewhere (`--separate-git-dir`) and a submodule (`.git/modules/<name>`)
    have none. A gitdir this process may not read is not looked at (withheld)
    and proves no worktree; the walk is then the whole one, as before."""
    gitdir = gitfile_dir(d)
    if not gitdir or withheld(gitdir) or not os.path.isfile(os.path.join(gitdir, "commondir")):
        return ""
    return next((x for x in _ancestors(d) if _within(gitdir, x)), "")


def gitfile_dir(d):
    """The gitdir the nearest `.git` at or above `d` names when it is a
    file, read off its text alone; "" for a `.git` directory or none."""
    top = _checkout_root(d)
    dot = os.path.join(top, ".git") if top else ""
    if not dot or not os.path.isfile(dot):
        return ""
    try:
        with open(dot) as f:
            line = f.readline().strip()
    except OSError:
        return ""
    if not line.startswith("gitdir:"):
        return ""
    return os.path.abspath(os.path.join(top, line[len("gitdir:"):].strip()))


def decision(cwd, fresh=False):
    """How design §8's rule decides a directory's project (Decision). On a
    machine not enrolled no statement is kept and the last rung is the
    owning repository's local project (none outside git)."""
    cwd = os.path.abspath(os.path.expanduser(cwd or "."))
    if read_refused(cwd):
        return Decision("", "", None)
    # The kept org file holding `locations` at all, even with no entry, is
    # what puts the new rule in force: never how many statements it holds.
    stated = stated_here()
    return _decide_files(cwd, fresh) if stated is None else _decide_stated(cwd, stated, fresh)


def _first_smns(folders):
    for d in folders:
        smns = _smns_in(d)
        if smns:
            return _smns_decision(d, smns)
    return None


def _decide_files(cwd, fresh):
    """The rule with no `locations` kept, on the reads resolution made
    before the registry: a .smns walking up, then the remote, the machine,
    the local repository. A linked worktree's walk stops below the first
    folder it shares with its main checkout, and goes on from the checkout,
    so a .smns above the checkout is the worktree's too (the one corner
    design §8 names); a .smns on a shared folder is found either way."""
    stop = worktree_stop(cwd)
    found = _first_smns(_ancestors(cwd, stop))
    if found:
        return found
    before = refusals()
    common = common_git_dir(cwd)
    repo = os.path.dirname(common) if common else ""
    readable = bool(repo) and not read_refused(repo)
    main = main_checkout(common) if stop and readable else ""
    found = _first_smns(_ancestors(main or stop)) if main or stop else None
    if found:
        _GUARD.refused = before   # a main checkout not read leaves the walk above the worktree as it was
        return found
    if readable and not main:
        found = _first_smns([repo])
        if found:
            return found
    return _last_rungs(cwd, fresh)


def _last_rungs(d, fresh):
    project = repo_project(d, fresh)
    if project is not None:
        return Decision("remote", project.root, project)
    project = own_machine_project()
    if project is not None:
        return Decision("machine", "", project)
    repo = owning_repo(d)
    if repo:
        name = safe_name(os.path.basename(repo)) or "repo"
        return Decision("local", repo, make_project("local-" + name, name, "", repo))
    return Decision("", "", None)


def _decide_stated(cwd, stated, fresh):
    """The rule with `locations` kept (an empty one too), over the canonical
    path. A linked worktree: its main checkout's own statement; else a .smns
    on its own path (below worktree_stop); else the rule at the main
    checkout. A gitdir or main checkout this process may not read leaves a
    .smns on the path to decide, up to the first folder a statement holds;
    past it, the directory is unread."""
    walk = os.path.realpath(cwd)
    gitdir = gitfile_dir(walk)
    if gitdir and withheld(gitdir):
        # A gitdir this process may not read: whether this is a linked
        # worktree, and its main checkout, are unknown. A .smns on the path
        # below the first folder a statement holds is what the rule gives
        # either way; past it, it is unread, as a repository not read is.
        for d in _ancestors(walk):
            found = _first_smns([d])
            if found:
                return found
            if statement_at(stated, d):
                break
        read_refused(gitdir)
        return Decision("", "", None)
    stop = worktree_stop(walk)
    before = refusals()
    main = worktree_main(walk) if stop else ""
    main = os.path.realpath(main) if main and not read_refused(main) else ""
    refused = refusals() != before
    if main:
        s = statement_at(stated, main)
        if s:
            return _stated_decision(s, main)
    if stop:
        found = _first_smns(_ancestors(walk, stop))
        if not found and refused:
            for d in _ancestors(stop):
                if statement_at(stated, d):
                    break   # its weight is the main checkout's rule, not read
                found = _first_smns([d])
                if found:
                    break
        if found:
            _GUARD.refused = before   # read, not told: the refusal took nothing it needed
            return found
        if refused:
            return Decision("", "", None)
    return _decide_at(main or walk, stated, fresh)


def _decide_at(walk, stated, fresh):
    above = None   # (the checkout root, whether it derives a remote), read at the first statement met
    for d in _ancestors(walk):
        s = statement_at(stated, d)
        if s and above is None:
            root = _checkout_root(walk)
            above = (os.path.realpath(root) if root else "", bool(root) and bool(derivation(walk, fresh).key))
        # A folder above a repository that derives a remote does not take
        # the clone beneath it; a .smns still does.
        if s and not (above[1] and above[0].startswith(d.rstrip("/") + "/")):
            return _stated_decision(s, d)
        smns = _smns_in(d)
        if smns:
            return _smns_decision(d, smns)
    return _last_rungs(walk, fresh)


_SMNS_CHANNEL_SAID = set()   # the .smns files whose channel id this process has warned of


def _smns_decision(d, smns):
    """A .smns's project. One that names a channel's id is no project's
    (CH1, §8): the directory is in the machine's project (on a machine not
    enrolled, what the last rungs give), said once on standard error naming
    the file. Outside decision's pin to MAWS's project-rule.json, whose cases
    hold no version-8 id: the rule is sminos's own (test_channels.py)."""
    pid, name, remote, hub = smns
    if is_channel_id(pid):
        path = os.path.join(d, SMNS)
        if path not in _SMNS_CHANNEL_SAID:
            _SMNS_CHANNEL_SAID.add(path)
            warn("ignoring %s: it names a channel's id, and a channel is no project; this directory is in the "
                 "machine's project" % path)
        project = own_machine_project()
        return Decision("machine", "", project) if project is not None else _last_rungs(d, False)
    return Decision("smns", d, make_project(pid, name, remote, d, hub_here(pid, name, hub)))


def _stated_decision(s, d):
    """A stored statement's project: a hub project of this machine's org
    (a link into any other is refused where it is made), rooted at its
    folder, named as the org's directory or this machine already names it."""
    by, pid = s
    e = enrollment()
    name = str((org_entry(pid) or {}).get("name") or registration(pid).get("name")
               or safe_name(os.path.basename(d)) or "project")
    return Decision(by, d, make_project(pid, name, "", d, {"url": e["url"], "org": e["org"]}))


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
    if read_refused(common):
        return Derivation(os.path.dirname(common), "", "", "", "its repository is in a protected folder, not read here")
    if fresh or common not in _REPO_REMOTE:
        _REPO_REMOTE[common] = _derive(os.path.dirname(common), common)
    return _REPO_REMOTE[common]


def _derive(repo, common):
    try:
        # Each cache generation derives every checkout again; the bytes are
        # read again only once the file moved (git writes it whole, by rename).
        remotes = git_config_remotes(file_bytes(os.path.join(common, "config")).decode("utf-8-sig", "replace"))
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
        key = json_at(os.path.join(projects_root(), pid, REMOTE_FILE)).get("key")
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
    for pid in _registered_at(project.root):
        if pid == project.id:
            continue
        held = registration(pid)
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


def registration_paths():
    """`projects/*/project.json` in sorted order, as sorted(glob) gives
    them, but from the listing alone: the read that follows each fails for
    one that is not there, so glob's lstat of every one is spent twice."""
    root = projects_root()
    try:
        names = os.listdir(root)
    except OSError:
        return []
    return sorted(os.path.join(root, name, "project.json") for name in names if not name.startswith("."))


_ROOTS = []   # [{registered root: [project ids]}], per cache generation (_registered_at)


def _registered_at(root):
    """The projects registered here at `root`, in id order: every
    registration read once per cache generation, however many projects
    remote_moved looks for (one each pass for each remote-derived project
    with no checkout registered)."""
    if not _ROOTS:
        roots = {}
        for path in sorted(glob.glob(os.path.join(projects_root(), "*", "project.json"))):
            pid = os.path.basename(os.path.dirname(path))
            roots.setdefault(str(registration(pid).get("root") or ""), []).append(pid)
        _ROOTS.append(roots)
    return _ROOTS[0].get(root, [])


class Guessed(Project):
    """A project told from what this machine recorded, for a directory this
    process may not read (read_refused): shown and addressed as the project,
    never what a reconciliation joins, moves or retires a session on."""
    __slots__ = ()


def guessed(project):
    return isinstance(project, Guessed)


def registered_guess(cwd):
    """The project registered here whose root is `cwd` or its nearest
    ancestor, by the path's string alone, as a Guessed — of several at one
    root the latest registered, and on an enrolled machine never a local one
    (no directory resolves to one there) — or None: unknown. A channel an
    older copy registered rooted at a folder (a channel-valued .smns) is no
    project of it (CH1, §1)."""
    _registered_at("")   # every registration read, once per cache generation
    roots, local_ok = _ROOTS[0], enrollment() is None
    d = _abs(cwd)
    while True:
        held = [p for p in (known_project(pid) for pid in roots.get(d, []))
                if p is not None and (local_ok or not p.id.startswith("local-")) and not is_channel_id(p.id)]
        if held:
            return Guessed(*max(held, key=lambda p: (mtime_of(os.path.join(p.home, "project.json")), p.id)))
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def mtime_of(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


_RECORDED = {}   # session → the project its membership is recorded in, per cache generation (recorded_project)


def recorded_project(session):
    """The project whose log holds `session`, of this machine, as a member
    now (its own latest membership `joined`) — of several, the one it joined
    last — as a Guessed; None for none. What a session whose directory this
    process may not read is told to be in."""
    if session not in _RECORDED:
        best, at = None, ""
        for p, listed in _holding_projects(session):
            last = threads_module().in_effect(_own_events(p, session, listed=listed))
            if last is not None and last["kind"] == "joined" and str(last.get("ts") or "") >= at:
                best, at = p, str(last.get("ts") or "")
        _RECORDED[session] = Guessed(*best) if best is not None else None
    return _RECORDED[session]


_LOG_LISTED = {}   # project dir name → its log/'s (names, stream bases), per cache generation (_log_listed)
_PROJECT_DIRS = []  # [the names under projects/, as listed], per cache generation (_holding_projects)


def _log_listed(name):
    """(the names in projects/<name>/log, the plain writer file names its
    audience stream files are of: `<host>.<session>` for each
    `<host>.<session>~<digest>.jsonl`), listed once per cache generation;
    empty for a directory that is not there; None when it cannot be listed
    (EMFILE is no empty directory), not kept: read as if unlisted."""
    if name not in _LOG_LISTED:
        try:
            names = frozenset(os.listdir(os.path.join(projects_root(), name, "log")))
        except (FileNotFoundError, NotADirectoryError):
            names = frozenset()
        except OSError:
            return None
        _LOG_LISTED[name] = (names, frozenset(m.group(1) for m in map(STREAM_FILE_RE.fullmatch, names) if m))
    return _LOG_LISTED[name]


STREAM_FILE_RE = re.compile(r"(.+)~[0-9a-f]{16}\.jsonl")


def _holding_projects(session):
    """(project, its log's listing or None) for each project registered
    here whose log holds a writer file of `session` under this machine's
    name now or a former one that held it — its plain writer's or an
    audience stream's — in the order the projects directory lists them:
    where recorded_project reads its own events. Each log directory is
    listed once a cache generation, as its answers are kept, rather than
    every one of its files opened under every name for every session a pass
    asks about (the MacBook's uplink, 2026-11-11: 26 sessions × 101
    projects × 1.65 names a generation, nearly every open failing). A file
    made since the listing is seen in the next generation, which is only as
    stale as a Guessed may be: nothing joins, moves or retires a session on
    one. last_project, whose answer a reconciliation acts on, never reads
    through here."""
    if not _PROJECT_DIRS:
        try:
            _PROJECT_DIRS.append(os.listdir(projects_root()))
        except OSError:
            return
    hosts = [host for host, held in machine_identity()[1].items() if session in held] + [host_name()]
    for name in _PROJECT_DIRS[0]:
        if name.startswith("."):
            continue   # what glob's `*` passes by
        listed = _log_listed(name)
        if listed is not None:
            names, bases = listed
            plain = ["%s.%s" % (host, session) for host in hosts]
            if not any(f + ".jsonl" in names for f in plain) \
                    and not any(("%s/%s" % (host, session)).replace("/", ".") in bases for host in hosts):
                continue
        if is_channel_id(name):
            continue   # a channel, which is no session's project (CH1): asked only of a log that holds the session
        p = known_project(name)
        if p is not None:
            yield p, listed


def project_source(cwd):
    """Where resolve_project finds a directory's project, as `project show`
    says it: `a link at <dir>`, `a stored id at <dir>`, `.smns at <dir>`,
    `remote <name> → <key>`, the machine project and why no remote derives
    one, or a machine not enrolled's local project."""
    cwd = os.path.abspath(os.path.expanduser(cwd or "."))
    if read_refused(cwd):
        return "the registrations here: %s is in a protected folder, not read from here" % cwd
    found = decision(cwd)
    if found.by in ("link", "minted", "smns"):
        return dict(STATED_WORDS, smns=".smns at %s")[found.by] % found.at
    if found.by == "local":
        return "the repository at %s, a local project: this machine is not enrolled" % found.at
    d = derivation(cwd)
    return "remote %s → %s" % (d.remote, d.key) if found.by == "remote" else \
        "machine project: %s" % d.why if found.by == "machine" else "-"


STATED_WORDS = {"link": "a link at %s", "minted": "a stored id at %s"}   # a stored statement, as project show and init name it


def overridden_smns(cwd):
    """Where a stored statement decides a directory's project, each .smns
    that takes part in the walk the statement wins and names another
    project, each a (file's Decision, statement's Decision), nearest first:
    for a linked worktree under its main checkout's statement, the nearest
    file on the worktree's own path; then the file at the statement's own
    folder. Read on decision()'s walk, the canonical path, so a file seen
    only through a symlink's lexical parents is none of them. A file above
    the statement's folder is an outer project the statement nests in, and
    one below it would have decided: neither is overridden."""
    found = decision(cwd)
    if found.by not in STATED_WORDS:
        return []
    walk = os.path.realpath(os.path.expanduser(cwd or "."))
    files = []
    stop = worktree_stop(walk)
    main = worktree_main(walk) if stop else ""
    if main and canonical(main) == canonical(found.at):
        files.append(_first_smns(_ancestors(walk, stop)))
    files.append(_first_smns([found.at]))
    return [(f, found) for f in files if f and f.project.id != found.project.id]


def statement_over_file(top):
    """The Decision of a stored statement that decides folder `top` even
    with a .smns at `top` — one at `top` itself (at one folder a statement
    is above the file), or, for a linked worktree, its main checkout's own —
    else None: a file written at `top` would then decide."""
    found = decision(top, fresh=True)
    if found.by not in STATED_WORDS:
        return None
    at = canonical(found.at)
    if at == canonical(top):
        return found
    main = worktree_main(os.path.realpath(top))
    return found if main and canonical(main) == at else None


UNREAD = object()   # a directory's project this process could not read and nothing recorded tells (_resolve)


def resolve_project(cwd, fresh=False):
    """The project of a directory by design §8's rule (decision): the
    nearer of a .smns and a stored statement walking up (a linked worktree
    in its main checkout's project); else, on an enrolled machine, the
    project its repository's remote derives (repo_project), else the
    machine's own project; else the local project of the owning git
    repository; else None (no project). A directory this process may
    not read, or whose resolution met one (read_refused), is told from the
    registrations (registered_guess): a Guessed, else None. Kept for the
    cache generation; `fresh` reads the directory as it is now."""
    project = _resolve(cwd, fresh)
    return None if project is UNREAD else project


def _resolve(cwd, fresh=False):
    """resolve_project's answer, UNREAD where it is unknown rather than no
    project."""
    cwd = os.path.abspath(os.path.expanduser(cwd or "."))
    if not fresh and cwd in _PROJECTS:
        return _PROJECTS[cwd]
    before = refusals()
    project = None if read_refused(cwd) else _read_project(cwd, fresh)
    if refusals() != before:
        project = registered_guess(cwd) or UNREAD
    _PROJECTS[cwd] = project
    return project


def _read_project(cwd, fresh):
    return decision(cwd, fresh).project


def seat_project(seat, fresh=False):
    """A seat's project, from its recorded cwd. A seat spawned where there is
    no project belongs to the local project named after that directory: the
    seat record is the explicit registration automatic discovery never makes.
    One whose directory this process may not read, and that nothing recorded
    tells, is in none (None) rather than in one made up for it.
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
    project = _session_project(key[0], seat_cwd(seat, fresh), fresh)
    if project is UNREAD or project is not None and is_channel_id(project.id):
        # In a directory this process may not read, nothing recorded telling: unknown, not local. And a seat is
        # never in a channel, whatever an older copy registered (CH1, §1): asked here, once a generation, so
        # known_projects' seats hold none and its every call asks no seat's project of its id again.
        project = None
    elif project is None:
        name = safe_name(os.path.basename(os.path.normpath(cwd))) or "fleet"
        project = make_project("local-" + name, name, "", os.path.abspath(cwd))
    if _SEAT_PROJECTS.get(key, project) != project:
        _SEAT_PIDS.clear()   # a fresh look moved the seat: every later read of the generation sees where to
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


def write_json(path, data, mode=0o600, durable=False):
    """Atomic replace: a reader sees the old file or the new one, never half.
    `durable`: the file's bytes synced before the rename and its directory
    after it, so a write that returns survives a crash or a power loss (for
    a write something outside the machine is told of); any step's failure
    raises."""
    parent = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
            if durable:
                f.flush()
                os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if durable:
        dfd = os.open(parent or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


def kept_root(project, held):
    """The root project_path registers a rooted project at, given the
    registration `held`: its registered root when that differs from the
    project's own and, as the directories are now, still resolves to this
    very project (another clone of the repository, another checkout of the
    .smns, its name and hub the same), or one this process may not read
    (read_refused); else the project's own."""
    root = str(held.get("root") or "") if isinstance(held, dict) else ""
    if not project.root or not root or root == project.root:
        return project.root
    if read_refused(root):
        return root   # a registered root this process may not read stands as registered
    if not os.path.isdir(root):
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
        _ensure_dir(os.path.join(project.home, "log"))
        path = os.path.join(project.home, "project.json")

        def held_now():
            try:
                return json_at(path)   # written whole, by rename: a stat tells it unchanged
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
                    and names_hub(str(held.get("root") or ""), project.id) is not False
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
    _ensure_dir(os.path.dirname(path))
    return path


def _ensure_dir(d):
    """A directory made (0700, with its parents) when it is not one yet: one
    stat when it is, as it is on every call but the first."""
    if not os.path.isdir(d):
        os.makedirs(d, mode=0o700, exist_ok=True)


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


_REGISTRATION_FILES = {}  # project.json → ((st_ino, st_size, st_mtime_ns), its JSON), for known_projects


def _registration_at(path):
    """A project.json's JSON, read again only once it changed (it is written
    whole, by rename: a new inode); None when it cannot be read. The daemon
    and the uplink list every project several times a minute."""
    try:
        st = os.stat(path)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        held = _REGISTRATION_FILES.get(path)
        if held is None or held[0] != key:
            with open(path) as f:
                held = _REGISTRATION_FILES[path] = (key, json.load(f))
    except (OSError, ValueError):
        _REGISTRATION_FILES.pop(path, None)
        return None
    return held[1]


_FILE_BYTES = {}  # path → ((st_ino, st_size, st_mtime_ns, st_ctime_ns), its bytes), for file_bytes


def file_bytes(path):
    """A small file's bytes, read again only once its inode, size, mtime or
    ctime moved (every file read through here is written whole, by rename: a
    new inode; a chmod moves the ctime, so a file made unreadable is opened
    again and fails as it would have); OSError as open raises it. The daemon's loop asks for the same
    records, registrations and settings every tick, most of them unchanged
    for days: a stat instead of an open. Callers parse the bytes each time,
    so nothing they hold is shared."""
    try:
        st = os.stat(path)
    except OSError:
        _FILE_BYTES.pop(path, None)
        raise
    key = (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    held = _FILE_BYTES.get(path)
    if held is None or held[0] != key:
        with open(path, "rb") as f:
            held = _FILE_BYTES[path] = (key, f.read())
    return held[1]


def json_at(path):
    """file_bytes, parsed: a new object on every call. OSError or ValueError
    as open and json.load raise them."""
    return json.loads(file_bytes(path))


_REGISTERED = {}  # project.json → (its JSON as _registration_at holds it, projects_root(), the log it makes, whether
#                   that log is a channel's)


def _registered_project(path, d):
    """The project a registration makes, or None: a function of its JSON
    (which _registration_at reads again only once the file moved, a new
    object then) and of where the projects live, so known_projects makes
    it again only once either moved (the uplink lists every project at
    every scan)."""
    try:
        pid = str(d["project"])
    except (KeyError, TypeError):
        return None
    if not (valid_name(pid) and os.path.basename(os.path.dirname(path)) == pid):
        return None
    return make_project(pid, str(d.get("name") or pid), str(d.get("remote") or ""), str(d.get("root") or ""),
                        dict(d["hub"]) if isinstance(d.get("hub"), dict) else None)


def _known(all_seats):
    """({id: project}, {id: channel}) of every log registered here, and the
    seats' projects: known_logs' two halves, a registration's kind kept with
    it, so telling them apart costs no call per log."""
    projects, channels = {}, {}
    home = projects_root()
    for path in registration_paths():
        d = _registration_at(path)
        held = _REGISTERED.get(path)
        if held is None or held[0] is not d or held[1] != home:
            p = _registered_project(path, d)
            held = _REGISTERED[path] = (d, home, p, p is not None and is_channel_id(p.id))
        if held[2] is not None:
            (channels if held[3] else projects)[held[2].id] = held[2]
    for s in seats() if all_seats is None else all_seats:
        p = seat_project(s)
        if p:
            projects.setdefault(p.id, p)
    return projects, channels


def known_projects(all_seats=None):
    """Every project this machine knows: those with a home here, and those of
    the seats it holds (`all_seats`: a seat read the caller already made).
    No channel (CH1, §1): what lists or looks up projects for a person or a
    session never meets one, and what opens, reconciles or leaves logs asks
    known_logs."""
    return list(_known(all_seats)[0].values())


def known_channels():
    """The logs registered here whose id is a channel's (is_channel_id), the
    org's directory's and this machine's own alike."""
    return list(_known([])[1].values())


def known_kinds(all_seats=None):
    """(known_projects, known_channels) from one read of the registrations,
    for a caller that takes each its own way (the daemon's tick): the kind
    kept with each registration, asked of no log again."""
    projects, channels = _known(all_seats)
    return list(projects.values()), list(channels.values())


def known_logs(all_seats=None):
    """Every log this machine knows, projects and channels: for what opens,
    reconciles or leaves logs (the uplink's subscription, the leaving rule,
    the daemon's tick), never for a listing."""
    projects, channels = _known(all_seats)
    return list(projects.values()) + list(channels.values())


def project_tiers(q):
    """The projects `q` names, in the order a name is looked up in them: its
    id alone; else, by name, the hub project, then the machine project; the
    rest (local-* and git-mirrored ones) only when neither has the name, so a
    local project named after its repository never shadows the repository's
    hub project. [] when none has it; an ambiguous name exits (the one
    refusal, ambiguous_name), and so does a name that is a channel's: a
    channel is no project (CH1, §8). A verb takes the first (find_project); a
    tag `@<q>/<alias>` reads the next only when the first has no such member
    — a team names its project deliberately and a machine is named after a
    host, so the project is the likelier meaning."""
    if is_channel_id(q):   # a channel's id, registered or not, before any name: no project's name shadows it
        die(not_a_project(q), EXIT_UNKNOWN)
    out, clash = _name_tiers(q)
    if clash:
        die(ambiguous_name(q, clash), EXIT_UNKNOWN)
    if out and is_channel_id(out[0].id):
        die(not_a_project(q), EXIT_UNKNOWN)
    return out


def _name_tiers(q):
    """(tiers, clash): project_tiers' lookup over every log known here
    (known_logs), and the logs of the first tier it consults that holds
    several (the tiers before it in `tiers`), rather than an exit. An id
    names its log, then a name exactly as it is (`#` is a name's character:
    `project init` takes it); only a `q` no log is named reads as
    `<name>#<short>`, split at its last `#`: the logs of that name whose id
    is `short` or begins with it, `short` eight hex digits or more. A channel is
    in no tier: a name a channel answers to along with any other log, a
    second channel included, is a clash of every log of that name; a name
    only one channel answers to names it. Among projects alone the tiers,
    their order and their clash are today's."""
    known = known_logs()
    hits = [p for p in known if p.id == q]
    if hits:
        return hits[:1], []
    named = [p for p in known if p.name == q]
    name, sep, short = q.rpartition("#")
    if sep and not named:
        prefix = len(short) >= 8 and all(c in "0123456789abcdef" for c in short)
        hits = [p for p in known if p.name == name and (p.id == short or prefix and p.id.startswith(short))]
        return (hits, []) if len(hits) < 2 else ([], hits)
    if any(is_channel_id(p.id) for p in named):
        return (named, []) if len(named) == 1 else ([], named)
    out = []
    for kind in ("hub", "machine", "local"):
        if kind == "local" and out:
            break   # a tier never consulted: its ambiguity is no one's
        hits = [p for p in named if project_kind(p) == kind]
        if len(hits) > 1:
            return out, hits
        out += hits
    return out, []


LOG_KINDS = {"channel": "channel", "hub": "project", "machine": "machine project", "local": "local project"}


def log_label(p):
    """How the one refusal names a log: `<name>#<the first eight of its id>
    (<kind>)`, a log whose id is no UUID by its whole id, each only when
    _name_tiers takes it back to that log alone (a log may be named exactly
    as another's short spelling); else `<name>#<its whole id>`, else its
    bare id, which names it first."""
    for spelling in ("%s#%s" % (p.name, p.id[:8]) if UUID_RE.fullmatch(p.id) else None, "%s#%s" % (p.name, p.id)):
        if spelling is not None:
            out, clash = _name_tiers(spelling)
            if not clash and [x.id for x in out] == [p.id]:
                return "%s (%s)" % (spelling, LOG_KINDS[project_kind(p)])
    return "%s (%s)" % (p.id, LOG_KINDS[project_kind(p)])


def ambiguous_name(q, logs):
    """The one refusal for a name several logs answer to (_name_tiers' clash),
    for every caller: each log as log_label names it."""
    return "ambiguous name '%s': %s — name one as listed, or by its id" % (q, ", ".join(sorted(map(log_label, logs))))


def not_a_project(q):
    """What a verb that takes a project says of a name that is a channel's."""
    return "'%s' is a channel, not a project: sminos channel show %s prints it" % (q, q)


def names_channel(q):
    """The channel `q` names (by its id, `name#short` or a name only it
    answers to), else None; a name several logs answer to, a channel among
    them, exits with the one refusal. An id of a channel's form is a
    channel's, registered here or not. A clash of projects alone is None:
    asked first by the paths that say why a channel cannot be used there
    (say, a tag, a verb's target, join), this decides nothing of a store
    with no channel, whose errors come in the order they came before
    channels (the verb's own lookup refuses that clash where it did)."""
    if is_channel_id(q):
        return known_project(q) or make_project(q, q, "", "")
    out, clash = _name_tiers(q)
    if clash:
        if any(is_channel_id(p.id) for p in clash):
            die(ambiguous_name(q, clash), EXIT_UNKNOWN)
        return None
    return out[0] if out and is_channel_id(out[0].id) else None


def tag_project(p):
    """How a tag names project `p`: by its name when the name reaches it (a
    tier project_tiers consults for it; `@<name>/alias#short` reads them in
    turn until one holds the member), else by its id — a `local-*` or
    git-mirrored project named as a hub or machine project is, or one whose
    name several logs share."""
    tiers, clash = _name_tiers(p.name)
    return p.name if not clash and any(t.id == p.id for t in tiers) else p.id


def find_project(q, required=True):
    """A project known locally, by id or by name (project_tiers' first);
    with required=False, None when none is, a channel's name or id among
    them, registered here or not (an ambiguous name still exits)."""
    channel = is_channel_id(q)   # a channel's id, registered or not, before any name: no project's name shadows it
    out, clash = ([], []) if channel else _name_tiers(q)
    if clash:
        die(ambiguous_name(q, clash), EXIT_UNKNOWN)
    if channel or out and is_channel_id(out[0].id):
        if not required:
            return None
        die(not_a_project(q), EXIT_UNKNOWN)
    if out:
        return out[0]
    if not required:
        return None
    die("no project '%s' is known on this machine" % q, EXIT_UNKNOWN)


def org_scope():
    """The projects an org-wide name (`@short`, `@alias#short`) is looked up
    in: every project known here, the followed ones included, but one the
    org's directory retires and one that has left this machine (has_left)."""
    return [p for p in known_projects() if not org_retired(p.id) and not has_left(p)]


def project_label(pid):
    """A log's id as a reader names it: its name when it is known here (a
    channel's too: an older copy can have moved a session into one)."""
    return next((p.name for p in known_logs() if p.id == pid), pid)


def caller_project(caller=None):
    """The project a call speaks in by default: the caller seat's; else, from
    inside a session, the session's own (session_project: its override, else
    its launch directory's — never where its shell has moved since); else,
    for the operator, the working directory's (None: no project)."""
    if caller:
        return seat_project(caller)
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if UUID_RE.fullmatch(sid):
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
            _ensure_dir(os.path.dirname(launch_cache_path(session)))
            write_json(launch_cache_path(session), entry)
        except OSError:
            pass   # read again next time
    return launch


def override_path(session):
    return os.path.join(root(), "sessions", session + ".json")


def override_of(session):
    """The project id a session's join override names, or "" for none. Read
    as it is now each time (a missing file is one failed stat; one written
    since, by rename, a new inode): `join` writes it while the daemon's tick
    reads, and a tick deciding on a stale read would move the session back
    and forth."""
    try:
        d = json_at(override_path(session))
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


_MOVING = set()   # the sessions this process's `join` is moving


@contextmanager
def moving(session):
    """`join`'s move of the calling session, held from before its override
    is written or removed until both memberships are: a reconciliation in
    another process that sees the override meanwhile leaves the session's
    join to the verb (moving_elsewhere), so the joined says `join`, never
    `move`. The lock file stays: one removed while held would leave a
    waiting join on a file no other process can find, and two joins each
    holding a lock of its own."""
    path = override_path(session) + ".lock"
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with flocked(path):
        _MOVING.add(session)
        try:
            yield
        finally:
            _MOVING.discard(session)


def moving_elsewhere(session):
    """Whether another process's `join` is moving the session now (moving)."""
    if session in _MOVING:
        return False
    try:
        fd = os.open(override_path(session) + ".lock", os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def known_project(pid):
    """A project registered here (its project.json), by id, or None."""
    return _registered_as(pid, registration(pid))


def _registered_as(pid, d):
    """The project a registration's JSON `d` makes for `pid`, or None."""
    if not valid_name(pid) or not isinstance(d, dict) or str(d.get("project") or "") != pid:
        return None
    return make_project(pid, str(d.get("name") or pid), str(d.get("remote") or ""), str(d.get("root") or ""),
                        d["hub"] if isinstance(d.get("hub"), dict) else None)


def join_refusal(project):
    """Why a session cannot be in `project` by its own declaration, or "":
    on an enrolled machine only an active hub project of its org will do — a
    local project is kept here as history and a retired one is closed, and a
    session in either would leave the desk and every other machine's reach;
    on a machine not enrolled any project known here. A channel never, on
    any machine (CH1, §8): `join` moves a thread's project, and a channel is
    none, so an override an older copy wrote that names one is read as
    absent (session_project) and the session moves back."""
    if is_channel_id(project.id):
        return channel_join_refusal(project.name)
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


def channel_join_refusal(q):
    """Why no session joins channel `q` (join_refusal's words for one)."""
    return ("it is a channel, not a project — sminos channel add %s places a thread in it, and its project stays "
            "where it is" % q)


def session_project(session, launch_cwd, fresh=False):
    """A session's project (§1): its join override, when the file names a
    project known here that it may be in (join_refusal; an ineligible one is
    read as absent, so the session moves back); else its launch directory's
    (resolve_project; `fresh`: as it is now). A launch directory this
    process may not read (read_refused) tells nothing: the session is in the
    project its membership is recorded in (recorded_project), else the one
    the registrations tell for the directory, each a Guessed. While the
    machine's stored statements are not known yet (locations_unknown) a
    session last a member of a project other than the one its directory's
    files give is in that one (last_project). None for a session in no
    project, or in one nothing tells."""
    project = _session_project(session, launch_cwd, fresh)
    return None if project is UNREAD else project


def _session_project(session, launch_cwd, fresh=False):
    pid = override_of(session) if session else ""
    if pid:
        target = known_project(pid)
        if target is not None and not join_refusal(target):
            return target
    if not launch_cwd:
        return None
    project = _resolve(launch_cwd, fresh)
    if session and (project is UNREAD or guessed(project)):
        project = recorded_project(session) or project
    elif session and locations_unknown():
        # Files alone answered while the statements are not known yet: a
        # session recorded elsewhere stays there, a resumed one rejoining it,
        # until a frame's `locations` decide; one recorded nowhere joins here.
        held = last_project(session)
        if held is not None and (project is None or held.id != project.id):
            project = held
    return project


_LAST = {}   # session → last_project's answer, per cache generation


def last_project(session):
    """The project known here that `session`'s latest own membership event,
    of this machine, puts it in, read rather than told: the project of a
    `joined`, or of a retirement other than by a move (a session that ended
    there and is resumed rejoins it); for a `moved` retirement, the project
    it names, every move recording its destination (retire_moved, `join`'s
    move to none: "", so None), since a move whose destination's `joined`
    was never written (an interrupted daemon, a failed join) is still that
    move. None for none. Where a session is in while the machine's stored
    statements are not known yet (_session_project), which a reconciliation
    acts on: so each project's files are read as they are when it is asked,
    never from a listing an earlier lookup of the generation took
    (_holding_projects is recorded_project's alone). Every project's files
    under every name, but only until the first frame's `locations`."""
    if session not in _LAST:
        best, at = None, ""
        for path in glob.glob(os.path.join(projects_root(), "*", "project.json")):
            pid = os.path.basename(os.path.dirname(path))
            # A channel is no session's project (CH1): an older copy's `join` into one is a move to read past.
            p = known_project(pid) if not is_channel_id(pid) else None
            last = threads_module().in_effect(_own_events(p, session)) if p is not None else None
            if last is not None and str(last.get("ts") or "") >= at:
                best, at = (p, last), str(last.get("ts") or "")
        if best is not None and best[1]["kind"] == "retired" and best[1].get("reason") == "moved":
            dest = str(best[1].get("project") or "")
            _LAST[session] = known_project(dest) if dest and valid_name(dest) and not is_channel_id(dest) else None
        else:
            _LAST[session] = best[0] if best is not None else None
    return _LAST[session]


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


# Audience streams (P5 O18 D6; MAWS docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md, Interfaces §A): an
# event with an audience (the sorted member ids who may read it) is written under a writer of its own,
# `<writer>~<digest>`, the digest the first 16 hex characters of SHA-256 over the JSON of its audience, so the hub
# serves each reader a whole writer or none of it. MAWS's `streamOf` and `audienceDigest`
# (apps/org-protocol/src/names.ts), pinned to these by sminos/tests/audience-vectors.json.
STREAM_RE = re.compile(r"^([^/]+/[^~]+)~([0-9a-f]{16})$")


# What a writer's name says, by name: a function of the name alone, asked of every own writer file at every upload
# pass and of every owed event at every words pass (2026-11-12: 129 k regex matches in 30 s of an idle uplink).
# Forgotten whole once it holds WRITER_NAMES_KEPT names.
_STREAM_OF = {}
_WRITER_SESSION = {}
WRITER_NAMES_KEPT = 1 << 16


def stream_of(writer):
    """(the plain writer, the audience's digest) of a writer: (writer, None)
    for a plain one."""
    if not isinstance(writer, str):
        return writer, None
    held = _STREAM_OF.get(writer)
    if held is None:
        m = STREAM_RE.fullmatch(writer)
        held = (m.group(1), m.group(2)) if m else (writer, None)
        if len(_STREAM_OF) >= WRITER_NAMES_KEPT:
            _STREAM_OF.clear()
        _STREAM_OF[writer] = held
    return held


def writer_base(writer):
    """The plain writer a writer is a stream of, or the writer itself."""
    return stream_of(writer)[0]


def is_stream(writer):
    return stream_of(writer)[1] is not None


def audience_digest(members):
    """The digest a stream's writer ends in (`audienceDigest`)."""
    text = json.dumps(sorted(set(members)), separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def stream_writer(base, audience):
    """The writer of `base`'s events for `audience`: its stream, or `base`
    itself for none (the whole org)."""
    return base if audience is None else "%s~%s" % (base, audience_digest(audience))


def writer_session(writer):
    held = _WRITER_SESSION.get(writer) if isinstance(writer, str) else None
    if held is None:
        last = writer_base(writer).rsplit("/", 1)[-1]
        held = last if UUID_RE.fullmatch(last) else ""
        if len(_WRITER_SESSION) >= WRITER_NAMES_KEPT:
            _WRITER_SESSION.clear()
        _WRITER_SESSION[writer] = held
    return held


def owner_event(e):
    """Whether a log event is the owner's words: a `human` event written by
    the owner's own writer — `<machine>/human` (sminos run with no session)
    or the hub's `hub/<member>` (a send from the desk, which the hub stores
    only as a `human`). A session's `say`, and anything else, is a peer's:
    it reaches a session as a peer message, never as the human's words."""
    writer = writer_base(str(e.get("writer") or ""))
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
# has no mark, and nothing of it waits. Each audience stream of the operator
# writer, `<name>/human~<digest>` (P5 O18 D6: the operator's words to a
# private session), is an operator writer too, waiting for and released on
# its own head; the first `have` seen under the enrolment is kept as the
# operator writers it named a head for (`headed`), and a writer it did not
# name, a stream opened later included, has nothing upstream to wait for.
HEADS_FILE = "heads.json"
HEADS_KEPT = 8   # enrolments daemon/heads.json keeps marked: one replacing another leaves the other marked
QUEUED = "queued"


def enrolment_stamp():
    """(name, enrolled) of this machine's enrolment now, identity.json's;
    None when it is not enrolled."""
    ident = sibling_module("sminos_rl10").cutover()
    return (ident["name"], ident.get("enrolled")) if ident is not None else None


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


def operator_writer(writer):
    """Whether a writer is an operator writer, `<name>/human` or an audience
    stream of it, under any name."""
    base = writer_base(writer) if isinstance(writer, str) else ""
    return base.endswith("/human") and base.count("/") == 1


def waits_for_head(project, writer):
    """Whether an append to `writer` in `project` waits for the upstream's
    head (the rule above): this machine's operator writer or a stream of it,
    in a project of its upstream, under a marked enrolment, not yet known
    for it — and once the enrolment's first `have` was kept (keep_headed),
    only while that `have` named a head for it, or a queue of it is still
    there (what it queued goes first: the release drains it under the
    writer's locks, which this is read under)."""
    if writer_base(writer) != writer_id():
        return False
    e = enrollment()
    if e is None or not (isinstance(project.hub, dict) and project.hub.get("org") == e["org"]):
        return False
    now = enrolment_stamp()
    if now is None or now not in _marks():
        return False
    known = _stamped(os.path.join(project.home, HEADS_FILE), now)
    if known is None:
        return True
    if writer in (known.get("known") or []):
        return False
    headed = known.get("headed")
    return not (isinstance(headed, list) and writer not in headed
                and not os.path.exists(queued_path(project, writer)))


def keep_headed(project, writers):
    """The operator writers the upstream holds a head for (`writers`), as
    the first `have` seen under this machine's enrolment named them
    (HubLog.release_heads), kept in the project's heads.json once per
    marked enrolment: a writer it did not name has nothing upstream to wait
    for (waits_for_head)."""
    now = enrolment_stamp()
    if now is None or now not in _marks():
        return
    known = _stamped(os.path.join(project.home, HEADS_FILE), now) or {"name": now[0], "enrolled": now[1]}
    if "headed" not in known:
        known["headed"] = sorted(writers)
        write_json(project_path(project, HEADS_FILE), known)


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
    writers (the plain one and its streams), under its name now or a former
    one (a welcome that renamed the machine while an append waited)."""
    me, former = machine_identity()
    names = {me, *former}
    out = {}
    for path in glob.glob(os.path.join(glob.escape(project.home), QUEUED, "*.jsonl")):
        got = queued_events(path)
        if got and operator_writer(got[0]["writer"]) and writer_base(got[0]["writer"]).rpartition("/")[0] in names:
            out[got[0]["writer"]] = path
    return out


def namesake(writer, name):
    """An operator writer under `name`: the plain one for the plain one, the
    stream of the same digest for a stream."""
    digest = stream_of(writer)[1]
    return "%s/human" % name if digest is None else "%s/human~%s" % (name, digest)


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
        # name (a former name's writer is no upload's), each queue into its
        # namesake (a stream into the stream of its digest). Each queue is
        # drained under its own writer's locks, which an appender still
        # running as a former name takes to queue there.
        with ExitStack() as stack:
            queues = {w: p for w, p in queued_operators(project).items()
                      if namesake(w, writer_base(writer).rpartition("/")[0]) == writer}
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
            # Appended whatever the enrolment says meanwhile (a welcome
            # naming another under this name): its head was found reached.
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


def stream_choice(project, session, recipients, why):
    """(choice, None): the one stream an addressed append of `session`'s to
    `recipients` goes under (streams_for); or (None, (message, exit code))
    when the choice refuses (D4), cannot be made (D10) or splits. Local: it
    appends nothing and asks no endpoint, so a verb can run it before it
    starts anything (fill --resume's return)."""
    au = audience_module()
    try:
        choice = streams_for(project, session, recipients)
    except au.Unreachable as e:
        return None, (str(e), EXIT_UNKNOWN)
    except au.StreamUnknown as e:
        return None, ("%s: %s" % (why, e), 1)
    if len(choice) != 1:
        return None, ("%s: its recipients' audiences differ; send to each on its own" % why, EXIT_UNKNOWN)
    return choice, None


def addressed_append(project, session, recipients, kind, fields, why):
    """One event of `session`'s (the operator's: "") naming `recipients`
    ([{session, alias}]), under the writer the stream choice gives it
    (streams_for): it must give one, since nothing here splits. Dies when
    the choice refuses (D4) or cannot be made (D10), saying `why`. Returns
    the event appended (seq None when it waits for the head)."""
    choice, refusal = stream_choice(project, session, recipients, why)
    if refusal:
        die(*refusal)
    writer, aud, _, _ = choice[0]
    keep_stream(project, writer, aud)
    return log_append(project, writer, kind, **fields)


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
    head, _, tail = writer_base(str(e.get("writer") or "")).rpartition("/")
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
# (project home, store) → (its files' (path, key) as last read whole, their events merged in log order — the
# _LOG_FILES dicts themselves, copied for each reader): a whole read, merged again only once a file of it moved
_MERGED = {}
_PROJECTED = {}  # project id → (its log's files' keys, _projection of that log): view_of's, while no file moved


def _log_file_events(path):
    """A writer file's well-formed events, parsed again only once its inode,
    size or mtime moved: the daemon and the uplink read every project's
    whole log many times a minute. [] for a file that cannot be read."""
    return _log_file_held(path)[1]


def _log_file_held(path):
    """(the file's (inode, size, mtime) or None, _log_file_events)."""
    try:
        st = os.stat(path)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        held = _LOG_FILES.get(path)
        if held is None or held[0] != key:
            with open(path, encoding="utf-8", errors="replace") as f:
                held = _LOG_FILES[path] = (key, [e for e in map(parse_event, f) if e is not None])
    except OSError:
        _LOG_FILES.pop(path, None)
        return None, []
    return held


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
    if not (since or kinds or to_session):
        return _store_whole(project, store)[1]
    streams = {}
    for path in _store_paths(project, store):
        for e in _log_file_events(path):
            if ((since and e["seq"] <= int(since.get(e["writer"], 0)))
                    or (kinds and e["kind"] not in kinds) or (to_session and not addressed_to(e, to_session))):
                continue
            streams.setdefault(e["writer"], []).append(dict(e))
    return _merge(streams)


def _store_paths(project, store):
    """The store's writer files, its top-level *.jsonl, sorted; the directory's own path taken literally (a
    state directory may be named `state[1]`)."""
    return sorted(glob.glob(os.path.join(glob.escape(os.path.join(project.home, store)), "*.jsonl")))


def _merge(streams):
    for stream in streams.values():
        stream.sort(key=lambda e: e["seq"])
    return list(heapq.merge(*streams.values(), key=lambda e: (e["ts"], e["writer"])))


def _store_whole(project, store, shared=False):
    """(the store's files' (path, key), every event of it as _store_read
    returns them, each a copy of its own): merged again only once a file
    moved. A machine's history is tens of thousands of events that do not
    change, and the daemon's tick merged every project's every 5 s.
    `shared`: the merged list itself, no copy, for a reader that changes
    nothing in it (view_of's View); what is derived from it is kept with it
    (log_memo) until a file moves."""
    files = tuple((path, *_log_file_held(path)) for path in _store_paths(project, store))
    sig = tuple((path, key) for path, key, _ in files)
    held = _MERGED.get((project.home, store))
    if held is None or held[0] != sig:
        if held is not None:
            _MEMOS.pop(id(held[1]), None)
        streams = {}
        for _, _, events in files:
            for e in events:
                streams.setdefault(e["writer"], []).append(e)
        held = _MERGED[(project.home, store)] = (sig, _merge(streams))
        _MEMOS[id(held[1])] = (held[1], len(held[1]), {})
    return sig, held[1] if shared else [dict(e) for e in held[1]]


# id(a merged log _store_whole keeps) → (that list, its length, {name: what log_memo derived from it})
_MEMOS = {}


def log_memo(events, name, compute):
    """compute(events), kept beside the merged log `events` is when it is
    one (_store_whole's shared list: a moved file replaces the list and
    drops what was kept), else computed for this caller alone. Each pass of
    the daemon asks every project's log for the same indexes; only a log
    that moved is scanned again. What is kept is shared: read it, never
    change it."""
    held = _MEMOS.get(id(events))
    if held is None or held[0] is not events or held[1] != len(events):
        return compute(events)
    kept = held[2]
    if name not in kept:
        kept[name] = compute(events)
    return kept[name]


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
# never delivered, and passed by the prefix only in order. An owed event
# this machine decided held for its session (`held`: its seqs above the
# prefix, delivered_held, T1's M3: no process held a thread its human
# opened) is owed from then until a push to the thread's process succeeds
# or the thread ends (held_owed).


def delivered_load(project, session_uuid):
    try:
        d = json_at(os.path.join(project.home, "delivered", reader_key(session_uuid) + ".json"))
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
            held = {}
            for x in v.get("held") if isinstance(v.get("held"), list) else ():
                # [seq, thread] pairs, the one form written (_delivered_write); anything else is no mark
                if isinstance(x, list) and len(x) == 2 and type(x[0]) is int and x[0] > settled \
                        and isinstance(x[1], str):
                    held[x[0]] = x[1]
            if held:
                out[str(w)]["held"] = held   # {seq: the thread the hold was decided for}
    return out


def _delivery(record, writer):
    return record.get(writer) or {"settled": 0, "pending": None, "attempts": 0}


def settled_already(project, session, writer, seq):
    """Whether the event `writer`:`seq` is in its writer's settled prefix of
    the session's delivery record: another deliverer took it (the daemon,
    between a sender's release of the lock and the sender's own pass),
    which that pass then has no outcome for. Nothing keeps what that
    deliverer made of it: a settled entry keeps no outcome, and the uplink's
    outcomes are of events written outside this machine alone, never a
    sender's own (sminos_outcomes). What it was is said by settled_words."""
    return seq <= _delivery(delivered_load(project, session), writer)["settled"]


# What a sender is told of its event another deliverer settled first: delivered only on evidence of a push, its
# frame in the conversation; a settlement alone proves none, since a stale hold, an @all whose recipient stopped and
# a refusal settle too.
DELIVERED_ELSEWHERE = "delivered by a concurrent delivery"
SETTLED_UNSEEN = "settled by another delivery, which could not be confirmed to have reached %s"


# Where each recipient's transcript ended as this call found it, before it appended its message
# (note_transcripts): {session: (device, inode, size), or None for none}. A frame another deliverer pushed during the
# call was appended after that, so frame_landed reads only what follows.
TRANSCRIPT_AT = {}


def note_transcripts(sessions):
    """Note where each session's transcript ends now, just before this call
    appends a message for it (a stat of the indexed path; nothing read): a
    process that sends again notes again."""
    for session in sessions:
        path = transcript_path(session)
        try:
            st = os.stat(path) if path else None
        except OSError:
            st = None
        TRANSCRIPT_AT[session] = (st.st_dev, st.st_ino, st.st_size) if st else None


def frame_landed(project, session, e):
    """Whether the event's frame is in the session's conversation, at one
    look over what it gained during this call (_transcript_holds), and only
    where a push puts a frame: the first thing its row delivers
    (_delivered_text), a frame quoted anywhere else being none. A send's
    is known by its head, which names its id; a chat event's by its head and
    its text together, and never when another chat event of the log shows
    the same reference and a text that frame would show as well (event_ref
    drops a stream's suffix, and each stream numbers its own events): such a
    frame cannot be told from the other's, and claims no push. A frame after
    another in one push of several is not told from a quote either, and
    claims none."""
    if e.get("msg_id"):
        framed = re.compile(r"\[sminos message from [^\n]* id=%s\](?:\n|$)" % re.escape(e["msg_id"]))
        return _transcript_holds(session, ("id=%s]" % e["msg_id"]).encode(),
                                 lambda text: framed.match(text) is not None)
    ref, body = event_ref(e), sender_text(str(e.get("text") or ""))
    if any(x.get("kind") in CHAT_KINDS and (x.get("writer"), x.get("seq")) != (e["writer"], e["seq"])
           and event_ref(x) == ref and sender_text(str(x.get("text") or "")).startswith(body)
           for x in log_read(project) if x.get("writer") is not None and x.get("seq") is not None):
        return False
    head = re.compile(r"\[sminos chat %s %s from [^\n]*\]\n" % (re.escape(project.name), re.escape(ref)))

    def holds(text):
        m = head.match(text)
        return m is not None and text.startswith(body, m.end()) \
            and text[m.end() + len(body):m.end() + len(body) + 1] in ("", "\n")
    return _transcript_holds(session, (" %s from " % ref).encode(), holds)


# What a push puts before its frame: a receipt's marker (sminos_holder_deliveries.MARKER), and on the inbox the
# engine's envelope (peer_envelope), with the line the engine opens it with.
DELIVERED_MARKER_RE = re.compile(r"\[sminos receipt [0-9a-f]{24}\.[0-9a-f]{16} attempt [1-9][0-9]{0,8}(?: wake)?\]\n")


def _delivered_text(row):
    """The text a prompt row delivers, from its start, when a push of
    sminos's can have made the row, else "": an inbox frame's body (the
    engine's `origin.body`, else unwrapped from its envelope); the bridge's
    prompt (the plugin's origin, appended or submitted); the engine
    supervisor's `reply` (of human origin, queued and marked to skip slash
    commands, 2.1.330). A prompt its human typed, at once or queued behind a
    turn, and a row that names no origin, are none: a frame pasted at its
    start is no push. A receipt's marker before the frame is passed over."""
    text = _prompt_text(row)
    origin = row.get("origin") if isinstance(row.get("origin"), dict) else {}
    kind = origin.get("kind")
    if text is None:
        return ""
    if kind == "peer":
        if isinstance(origin.get("body"), str):
            text = origin["body"]
        else:
            opened = re.match(r"(?:[^\n<]*\n)?<%s[^>\n]*>\n" % PEER_TAG, text)
            text = text[opened.end():] if opened else ""
    elif kind == "plugin" and origin.get("name") == "sminos":
        pass
    elif not (kind == "human" and row.get("promptSource") == "queued" and row.get("queueSkipSlashCommands") is True):
        return ""
    marked = DELIVERED_MARKER_RE.match(text)
    return text[marked.end():] if marked else text


def _transcript_holds(session, needle, holds):
    """Whether a prompt row the session's transcript gained since this call
    noted it (TRANSCRIPT_AT; the whole file when it noted none there, or the
    file is another or shorter now), up to where the file ended when this
    opened it, delivers a text `holds` accepts (_delivered_text): read a
    line at a time to the first that does, a line parsed only when it holds
    the bytes `needle`, nothing kept."""
    path = transcript_now(session)
    if not path:
        return False
    at = TRANSCRIPT_AT.get(session)
    try:
        with open(path, "rb") as f:
            st = os.fstat(f.fileno())
            start = at[2] if at and (st.st_dev, st.st_ino) == at[:2] and st.st_size >= at[2] else 0
            f.seek(start)
            left = st.st_size - start
            while left > 0:
                line = f.readline(left)
                if not line:
                    break
                left -= len(line)
                if needle not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and holds(_delivered_text(row)):
                    return True
    except OSError:
        pass
    return False


def settled_words(project, session, e, alias):
    """(pushed, what is said) of an event another deliverer settled first
    (settled_already): DELIVERED_ELSEWHERE when its frame is in the
    conversation (frame_landed), else SETTLED_UNSEEN, which claims no push
    and no absence of one."""
    if frame_landed(project, session, e):
        return True, DELIVERED_ELSEWHERE
    return False, SETTLED_UNSEEN % alias


def settled_sent(project, session, e, alias):
    """A send's line for its event another deliverer settled first (settled_words)."""
    pushed, said = settled_words(project, session, e, alias)
    return "sent to %s (%s)" % (alias, said) if pushed else "recorded %s for %s: %s" % (event_ref(e), alias, said)


def _entry(settled, pending=None, attempts=0, revoked=(), pushed=None, held=()):
    """A writer's delivery entry as written: of its revoked seqs, those
    directly above the settled prefix are passed by it (none is owed, so the
    prefix moves over them in order), the rest kept; `revoked` only when it
    holds one, so a record with none is written as before; `held` ({seq:
    the thread the hold was decided for}, delivered_held) above the prefix
    alone, likewise. The entry is in the form delivered_load gives, which
    _delivered_write alone turns into the form on disk."""
    marked = sorted({s for s in revoked if s > settled})
    while marked and marked[0] == settled + 1 and marked[0] != pending:
        settled = marked.pop(0)
    w = {"settled": settled, "pending": pending, "attempts": attempts}
    if pushed is not None:
        w["pushed"] = pushed
    if marked:
        w["revoked"] = marked
    held = {s: t for s, t in dict(held or {}).items() if s > settled}
    if held:
        w["held"] = held
    return w


def _next_check(record, writer, seq):
    w = _delivery(record, writer)
    if seq <= w["settled"] or (w["pending"] is not None and seq != w["pending"]) or seq in w.get("revoked", ()):
        raise ValueError("delivery of %s:%d out of order (settled %d, pending %s%s)" % (
            writer, seq, w["settled"], w["pending"], ", revoked" if seq in w.get("revoked", ()) else ""))
    return w


def _delivered_write(project, session_uuid, record):
    """A delivery record, in delivered_load's form, written in the form on
    disk: every writer's `held` ({seq: thread}) as sorted [seq, thread]
    pairs, which JSON cannot key by int. The one place the forms meet, so
    no writer's marks are written in the other form whichever writer a
    caller changed (`revoked` and `pushed` are lists in both)."""
    disk = {w: (dict(v, held=sorted([s, t] for s, t in v["held"].items())) if isinstance(v.get("held"), dict)
                else v) for w, v in record.items()}
    write_json(project_path(project, "delivered", reader_key(session_uuid) + ".json"), disk)


def delivered_settle(project, session_uuid, writer, seq):
    """Settle the writer's next owed event — every event between the settled
    prefix and seq is not owed to this session, so the prefix moves to seq.
    The caller holds delivered/<session>.lock."""
    record = delivered_load(project, session_uuid)
    w = _next_check(record, writer, seq)
    record[writer] = _entry(seq, revoked=w.get("revoked", ()), held=w.get("held", ()))
    _delivered_write(project, session_uuid, record)


def delivered_fail(project, session_uuid, writer, seq):
    """Note a failed attempt at the writer's next owed event; returns the count."""
    record = delivered_load(project, session_uuid)
    w = _next_check(record, writer, seq)
    attempts = w["attempts"] + 1 if w["pending"] == seq else 1
    record[writer] = _entry(w["settled"], seq, attempts, w.get("revoked", ()), held=w.get("held", ()))
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
                                w.get("revoked", ()), [seq, outcome], w.get("held", ()))
        _delivered_write(project, session_uuid, record)
    except OSError as err:
        daemon_log("delivery: the push of %s:%d to %s could not be noted (%s): a later pass pushes it again" % (
            writer, seq, session_uuid, err))


def delivered_held(project, session_uuid, writer, seq, thread=None):
    """Note that this machine decided the writer's owed event `seq` held for
    the session (T1's M3: a thread its human opened that no process held):
    from now it is owed until a push to that thread's process succeeds or
    the thread ends (held_owed), whatever a later pass finds. Once per
    event, for the thread it was decided for (`thread`, the session's stamp
    by default): an obligation of that thread alone (stale_hold). The
    caller holds delivered/<session>.lock."""
    record = delivered_load(project, session_uuid)
    w = _delivery(record, writer)
    if seq <= w["settled"] or seq in w.get("held", {}):
        return
    held = dict(w.get("held", {}))
    held[seq] = threads_module().stamp(session_uuid) if thread is None else thread
    record[writer] = _entry(w["settled"], w["pending"], w["attempts"], w.get("revoked", ()), w.get("pushed"), held)
    _delivered_write(project, session_uuid, record)


def stale_hold(record, session, e):
    """Whether `e` was decided held for a thread the session no longer fills
    (it went on in a job, or the thread ended and the id is another
    thread's now): that obligation is not this thread's, and its text is
    pushed to no process of another thread (settled `recorded`, as the
    continuation rule settles what a session handed off was owed)."""
    thread = _delivery(record, e["writer"]).get("held", {}).get(e["seq"])
    if thread is None:
        return False
    now = threads_module().stamp(session)
    # Another thread positively holding the session settles it; with none, a marked thread whose record cannot be
    # read is not known displaced (held_unreadable defers it).
    return thread != now and (bool(now) or not threads_module().unreadable(thread))


def held_unreadable(record, e):
    """The thread an event's hold mark names when that thread's record is
    there and cannot be read, else "": no binding of the session is known
    (stale_hold settles it once another thread positively holds the
    session), so it stays owed, held `unknown` for that thread, and is
    pushed nothing, asked about nothing and counted nothing until the
    record reads again."""
    thread = _delivery(record, e["writer"]).get("held", {}).get(e["seq"])
    return thread if thread and threads_module().unreadable(thread) else ""


def stale_line():
    """What a sender is told of a message whose recipient no longer fills
    the thread it was chosen as by the time its hold was noted (it went on
    in another session, its id another thread's now): the stale-hold case."""
    return ("the session no longer fills the thread it was sent to (it went on in another session): pushed to no "
            "one; it stays in the log")


def held_record(project, session, alias, sender, via, text, msg_id, thread):
    """A sender's message to a session it found held, recorded and its hold
    noted in one step against the delivery pass: under the session's
    delivery lock, the append and the mark (delivered_held), so no pass
    settles the event between them, whatever process holds the session by
    then: the sender's decision is the hold, and the event is owed from it
    until it is pushed to its thread's process or the thread ends. The mark
    names `thread`, the thread the recipient was chosen as at the lookup:
    one the session no longer fills by the time the lock is held is the
    stale-hold case (stale_hold: pushed to no one). (the event or
    WaitingSend, "held" | "stale" | "queued"): a WaitingSend has no seq yet,
    and the pass decides it once it is appended."""
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        e = record_message(project, session, alias, sender, via, text, msg_id, deliver=False)
        if isinstance(e, WaitingSend):
            return e, "queued"
        delivered_held(project, session, e["writer"], e["seq"], thread)
        return e, "held" if threads_module().stamp(session) == thread else "stale"


def held_decided(project, session, e, outcome):
    """A delivery's outcome for the event `e` as the hold decides it, under
    the session's delivery lock, before it is concluded: a thread's hold
    decided now (`held:<why>` of HOLDS: a reason it is not woken, a wake
    that failed, or one that passes on its own) is kept for the event
    (delivered_held), so that from then on it is owed until it is pushed to
    its thread's process or the thread ends, whatever a later pass finds of
    that process (held_owed); any other outcome goes through held_owed."""
    record = delivered_load(project, session)
    if hold_why(outcome):
        delivered_held(project, session, e["writer"], e["seq"], getattr(outcome, "thread", None))
        return outcome
    return held_owed(project, session, record, e, outcome)


def held_owed(project, session, record, e, outcome):
    """What a pass's outcome for an event decided held for the session
    (delivered_held) becomes: anything short of a push — `recorded` (no
    inbox yet, or one that does not answer) or a failure before the text
    reached its process (the inbox write, a receipt prepared and not
    handed) — is `held:`, owed with no attempt counted, while the session is
    the current one of a thread that has not ended, of either kind
    (thread_owed), and still a member here. Every other outcome, and any
    outcome for an event never decided held, stands."""
    if e["seq"] not in _delivery(record, e["writer"]).get("held", {}) or stale_hold(record, session, e):
        return outcome
    if outcome != "recorded" and not outcome.startswith("failed"):
        return outcome
    if (unknown := held_unreadable(record, e)):
        return hold_outcome("unknown", unknown)   # its thread's record unreadable: owed, nothing counted
    if not thread_owed(session) or latest_membership(_own_events(project, session)) != "joined":
        return outcome
    return "held:not pushed to its process yet (%s)" % outcome


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
        record[writer] = _entry(w["settled"], None, 0, revoked, held=w.get("held", ()))
    else:
        record[writer] = _entry(w["settled"], w["pending"], w["attempts"], revoked, w.get("pushed"), w.get("held", ()))
    _delivered_write(project, session_uuid, record)
    return True


def revoke_owed(project, member, revoked):
    """What a revocation stops at once: every event owed to the member whose
    stored signer the set names (sminos_rl10.event_revoked), asked or not,
    marked revoked (delivered_revoke), under its delivery lock. One whose
    push is noted, or whose receipt went to its `gate` process (O12 M4b:
    an attempt reached its inbox, or it was admitted), was delivered before
    the revocation, and is left to its settlement; a receipt only prepared
    is marked like any owed event, and removed; one that cannot be read is
    deferred, kept, its event left owed (its delivery holds while it stays
    so, and a push after takes the revocation check). The events marked."""
    session = member.session
    if not session:
        return []
    rl10 = sibling_module("sminos_rl10")
    marked = []
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        record = delivered_load(project, session)
        for e in _owed(log_read(project, to_session=session), session, record):
            noted = _delivery(record, e["writer"]).get("pushed")
            if not rl10.event_revoked(e, revoked) or (noted and noted[0] == e["seq"]) \
                    or holder_module().handed(project.id, session, e) is not False:
                continue
            if delivered_revoke(project, session, e["writer"], e["seq"]):
                holder_module().settled(project.id, session, e)
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
    thread: str = ""      # the thread it fills (its latest joined's stamp, X2); "" for none
    opened: str = ""      # how its thread was opened: spawned | human; "" for no thread
    thread_sessions: tuple = ()   # the other sessions of its thread (by the log's episodes) `former` does not hold,
                                  # newest first: a refill's predecessors, a session that left it (X2, §4)
    wake: str = ""        # another machine's stopped session: whether its machine wakes it, as its latest `state`
                          # published it (X3: woken | held); "" for none, and for a session of this machine
    why: str = ""         # with `wake` held: why, as that `state` published it (X3, T2's §5); "" for none (1.51's)
    end: str = ""         # why it has ended (T1's M4, has_ended): retire | ended (its membership in effect a
                          # `retired` of that reason, whoever wrote it) | machine (its machine retired); "" for none
    end_by: str = ""      # who retired it (the `retired`'s `by`), for a row that says why
    named: str = ""       # the thread a name of it resolves through (§4, row_thread): its stamp, else the seat its
                          # unstamped `joined` names, which a remote row holds no seat record to give
    channels: tuple = ()  # the declared channels it is in, as the log states them (CH1's §5: its statement in effect,
                          # sminos_threads.stated_set); () for none


def project_kind(project):
    """channel | hub | machine | local: a declared channel, by its id alone
    whatever the org's directory calls its entry (CH1, §1), so nothing that
    asks "is this a hub project" answers yes for one by default; a machine's
    own project (this machine's by its id, another's by the org's
    directory), a project that syncs through a desk hub, or one that does
    not."""
    if is_channel_id(project.id):
        return "channel"
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
         "thread": m.thread or None, "opened": m.opened or None,
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


_INTERNAL = []   # [(the peer_records read it was listed after, internal_pids as listed then)]


def internal_pids():
    """Pids `derive` marked as its own headless forks: never members (§5).
    Listed once for each read of the engine's records (peer_records), and
    after it: derive marks a fork before the fork can start its engine, so
    every fork whose record that read holds is in a listing taken after it.
    Every view asks."""
    peers = peer_records()
    if not (_INTERNAL and _INTERNAL[0][0] is peers):
        try:
            listed = frozenset(n for n in os.listdir(os.path.join(root(), "internal")) if n.isdigit())
        except OSError:
            listed = frozenset()
        _INTERNAL[:] = [(peers, listed)]
    return _INTERNAL[0][1]


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
    daemon handed none, or one that does not parse as a JSON
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


_THREADS = []   # sminos_threads, once imported: the reducer is asked for every membership read


def wake_module():
    """What a wake reads and says (sminos_wake; T2)."""
    return sibling_module("sminos_wake")


def channels_module():
    """What reads and decides for declared channels (sminos_channels; CH1)."""
    return sibling_module("sminos_channels")


def threads_module():
    if not _THREADS:
        _THREADS.append(sibling_module("sminos_threads"))
    return _THREADS[0]


def audience_module():
    return sibling_module("sminos_audience")


def streams_here(project):
    """Whether the project's events may go under audience streams (P5 O18
    D6): a project the hub syncs (a hub project, or a machine's own). A
    git-mirrored or local project's log never reaches the hub, which is what
    filters streams, so it keeps every event under its plain writer."""
    return project is not None and project_kind(project) != "local"


def own_stream(project, session):
    """(writer, audience): where the session's own events go in `project`'s
    log now (sminos_audience.own_writer); the plain writer outside a hub
    project. StreamUnknown, the audience module's, when it cannot be told."""
    base = writer_id(session or None)
    if not session or not streams_here(project):
        return base, None
    aud = audience_module().own_audience(session)
    return stream_writer(base, aud), aud


def streams_for(project, session, recipients, text=None, raws=None):
    """[(writer, audience, recipients, text)]: the events an addressed
    append makes (sminos_audience.stream_for, D4), split by audience; one,
    under the plain writer, outside a hub project. Unreachable or
    StreamUnknown as there."""
    if not streams_here(project):
        return [(writer_id(session or None), None, list(recipients), text)]
    return audience_module().stream_for(project, session, recipients, text, raws)


def keep_stream(project, writer, audience):
    """A stream writer's audience, kept before its first event (the
    uplink's voids claim it); nothing for a plain writer."""
    if audience is not None:
        audience_module().keep_stream(project, writer, audience)


def published_redacted(event, audience):
    """`event` with its provenance references that would widen what a
    session's id reaches written null (sminos_audience.redact); in place."""
    return audience_module().redact(event, audience)


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
    Log 17): owners that are the token alone are left off, and every reader
    takes a member that publishes none as the machine's, the same value.
    Owners an owner added beside the token (sminos_records.add_owner) are
    published as the endpoint resolved them at the record's policyRev
    (mixed_owners), and left off while it has not: a reader then takes them
    as the machine's alone, never as a member list missing the machine's.
    Nothing for a provisional record or none, so readers elsewhere fall
    back to the machine's default without being bound to it."""
    records = records_module()
    rec = records.read(sid) if sid else None
    if not records.is_final(rec):
        return {}
    owners = list(rec["owners"])
    if records.MACHINE in owners:
        owners = mixed_owners(sid, rec) if owners != [records.MACHINE] else None
    pub = {**({"owners": owners} if owners else {}), "origin": dict(rec["origin"])}
    if isinstance(pub["origin"].get("spawnerSession"), str):
        # A spawner whose audience does not contain the session's own is named to no one (P5 O18 D4): the
        # session's `joined` carries it null. A session whose own audience cannot be told carries it null too.
        try:
            aud = audience_module().own_audience(sid)
        except audience_module().StreamUnknown:
            pub["origin"]["spawnerSession"] = None
        else:
            published_redacted(pub, aud)
    return pub


def mixed_owners(sid, rec):
    """A record's owners holding `@machine` beside member ids, as member ids:
    the owners the endpoint gave for the session at the record's policyRev
    (sminos_audience's kept word, where `@machine` is resolved), when they
    hold every member beside the token; else None."""
    au = audience_module()
    try:
        entry = au.entry_of(sid)
    except au.StreamUnknown:
        return None
    resolved = (entry or {}).get("owners")
    if not (isinstance(resolved, list) and resolved and entry.get("policyRev") == au.policy_of(rec)[2]):
        return None
    beside = [o for o in rec["owners"] if o != records_module().MACHINE]
    return sorted(set(resolved)) if set(beside) <= set(resolved) else None


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
    index = log_memo(events, "lineage", _lineage_scan)
    _LINEAGE_INDEX[:] = [events, len(events), index]
    return index


def _lineage_scan(events):
    fold = threads_module().Fold()
    conts, published = {}, {}
    for e in events:
        sid = e.get("session")
        if not isinstance(sid, str) or e["kind"] not in MEMBERSHIP or writer_session(e["writer"]) != sid:
            continue
        if fold.add(sid, e) is None:
            continue
        if e["kind"] == "retired" and e.get("reason") == "continued" and UUID_RE.fullmatch(str(e.get("to") or "")):
            conts[e["to"]] = sid
        elif publishes(e):
            published[sid] = e
    return conts, published, {sid: e["kind"] for sid, e in fold.effect.items()}


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
    none, its policy read from where it sits: from_joined); else the first
    provisional record, the fallback, so a provisional
    session between it and a final ancestor never hides the ancestor. The
    session's own publications are never evidence: they say what its record
    already is. A predecessor whose record file cannot be read ends the walk
    (sminos_records.unreadable): nothing past it is evidence, since its own
    may hold owners changed since. `former` given, even empty, is the whole
    lineage."""
    records = records_module()
    chain = list(former) if former is not None else (
        lineage_of(project, sid, peer, events) if project is not None else [])
    fallback = None
    for i, old in enumerate(chain):
        rec = records.read(old)
        if rec is None and records.unreadable(old):
            chain = chain[:i]
            break
        if rec is not None:
            if records.is_final(rec):
                return records.inherited(rec, chain[:i + 1])
            fallback = fallback or records.inherited(rec, chain[:i + 1])
    if project is not None:
        for s in chain:
            j = last_published(project, s, events)
            if j is not None:
                return records.from_joined({"owners": owners_of(j) or [records.MACHINE], "origin": j.get("origin"),
                                            "writer": j["writer"]}, chain)
    return fallback


def ensure_record(project, sid, seat=None, peer=None, evidence=None, former=None, events=None):
    """The session's record: written if it has none, and replaced only by
    strictly stronger evidence (sminos_records.stronger: launch, then
    lineage, then the hook's, then the defaults; final over provisional).
    The candidate is its lineage (lineage_provenance; `former`, a hand-off's
    predecessor, when the caller knows it), else `evidence` (the hook's:
    the session's own environment), else the machine's defaults; a session
    with no record whose candidate carries no policy is private with no
    shares when a stream of its own is catalogued (has_own_stream). A record a
    launch established, or a final lineage, has nothing stronger to look
    for but a claim (sminos_records.claim); a final hook record looks for a
    lineage only where one can appear, a background job or a hand-off. Then,
    whether or not it changed, a member whose `joined` does not carry what
    its record publishes is joined again (publish_owners). A record that
    cannot be written is a warning: membership never waits on it. A record
    file that exists but cannot be read is left as it is, said once per
    process in daemon.log, and None returned. Returns the record, or None."""
    records = records_module()
    if records.unreadable(sid):
        _unreadable_said(sid)
        return None
    rec = records.read(sid)
    settled = rec is not None and (records.basis(rec) == "launch" or records.strength(rec) == (2, True)
                                   or (records.strength(rec) == (1, True) and not former
                                       and str((peer or {}).get("kind") or "") != "bg"))
    if not settled:
        try:
            prov = lineage_provenance(project, sid, peer, former, events) \
                or evidence or records.default_provenance()
            if records.stronger(prov, rec):
                if rec is None and not records.policy_carried(prov) and has_own_stream(sid):
                    # A record lost (deleted, a restore without it) of a session that was private: its own stream
                    # says so, its shares unknown — the narrowest, for its owner to widen (O18 D10).
                    prov = {**prov, "access": "private", "shares": []}
                floor = policy_rev_floor(sid) if rec is None and prov.get("access") == "private" else 0
                if floor > prov.get("policyRev", 0):
                    # Above every revision of it kept here, a predecessor's (inherited) included.
                    prov = {**prov, "policyRev": floor}
                rec = records.establish(sid, prov, _RECORD_DEADLINE)[0]
        except (OSError, LockBusy, ValueError) as e:
            warn("the record of session %s could not be written: %s" % (sid[:8], e))
    if rec is not None and records.is_final(rec) and project is not None:
        publish_owners(project, sid, events)
    return rec


def policy_rev_floor(sid):
    """The policyRev a session's recreated record starts at: above every
    revision of it this machine still holds — its endpoint's audience entry
    (daemon/audiences.json) and its kept transition (visibility.json) — or 0
    when it holds none. The endpoint's word at a revision the lost record
    had would never match a record restarted below it (audience_of needs
    its own revision, and an entry is replaced only by a newer one), so the
    session would stay unwritable; above them, the endpoint restates its
    audience at the new revision once its member frame carries it."""
    revs = []
    try:
        entry = audience_module().entry_of(sid)
    except audience_module().StreamUnknown:
        entry = None
    held = sibling_module("sminos_visibility").transitions().get(sid)
    for rev in ((entry or {}).get("policyRev"), (held or {}).get("policyRev")):
        if type(rev) is int and rev >= 0:
            revs.append(rev + 1)
    return max(revs, default=0)


def has_own_stream(sid):
    """Whether a session has an audience stream of its own writer, under
    this machine's name now or a former one, catalogued in any project
    known here (streams.json, sminos_audience.keep_stream): it was private
    when that stream was written. Read only when a record is about to be
    written for a session that has none."""
    me, former = machine_identity()
    mine = {"%s/%s" % (name, sid) for name in (me, *former)}
    return any(is_stream(w) and writer_base(w) in mine
               for p in known_logs(all_seats=[]) for w in audience_module().streams_of(p))


_UNREADABLE_SAID = set()


def _unreadable_said(sid):
    if sid in _UNREADABLE_SAID:
        return
    _UNREADABLE_SAID.add(sid)
    try:
        daemon_log("record: session %s has a record file that cannot be read: left as it is, nothing written over it"
                   % sid[:8])
    except OSError:
        pass


def publish_owners(project, sid, events=None):
    """A member whose latest publishing `joined` does not carry what its
    record publishes now (published_provenance: it became final after the
    member joined, its record was replaced by stronger evidence since, or an
    earlier publication's append failed) is joined again, carrying it: its
    alias as the log holds it, the rest as its last `joined` had them, `by`
    empty. Once per change of the record, which only moves up (default,
    hook, lineage, launch), or gains an owner: while a change of it waits for
    the endpoint's audience (a pending transition, sminos_visibility), it is
    that transition's snapshot that publishes it, not this. With `events` (a reconciliation's log), a member
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
    held = sibling_module("sminos_visibility").transitions().get(sid)
    if held is not None and not held.get("done"):
        return []   # an owner added (sminos_visibility.add_owner): its pending transition's snapshot carries it

    def guard(evs):
        return latest_membership(evs) == "joined" and missing(evs, published_provenance(sid))

    guard = record_settled(threads_module().thread_of(sid, ended=False), guard)   # never around an open entry

    return lifecycle(project, sid, "joined", guard=guard, required=False, **joined_again(own, sid))


def joined_again(own, sid):
    """The fields of a `joined` the session is joined again with
    (publish_owners, and the daemon's restatement of a withheld one,
    sminos_daemon.restate_withheld): its alias as its own events (`own`)
    hold it, the rest as its last `joined` had them, `by` empty; None when
    they hold no `joined`."""
    last = next((e for e in reversed(own) if e["kind"] == "joined"), None)
    if last is None:
        return None
    alias, source = own_alias(own, sid)
    return joined_fields(alias or str(last.get("alias") or sid[:8]),
                         source or str(last.get("name_source") or "derived"), str(last.get("cwd") or ""),
                         str(last.get("worktree") or ""), str(last.get("role") or ""), str(last.get("seat") or ""),
                         "", str(last.get("session_kind") or ""), session=sid)


def latest_membership(events):
    """The kind of the membership in effect among a session's own events
    (sminos_threads.in_effect: the latest joined or retired that is not
    passed by), or None."""
    e = threads_module().in_effect(events)
    return e["kind"] if e is not None else None


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
    retirement's, is one of `fields`.) No `joined` goes into a project told
    rather than read (Guessed), whoever asks; and nothing but a `retired`
    into a channel's log (CH1: a thread's facts go to its own project; the
    one retirement undoes a `joined` an older copy wrote there)."""
    if log_project is None or not session or (kind == "joined" and guessed(log_project)) \
            or (kind != "retired" and is_channel_id(log_project.id)):
        return []
    try:
        writer, aud = own_stream(log_project, session)
    except audience_module().StreamUnknown as e:
        # Fail closed (P5 O18 D10): a session whose stream cannot be chosen writes nothing.
        msg = "%s of %s is not recorded in %s's log: %s" % (kind, session[:8], log_project.name, e)
        if required:
            raise LogWriteFailed(msg)
        warn(msg)
        return []
    # A guard reads the session's whole own history: its former names', and its other streams' (a policy change
    # moves where its lifecycle goes on, P5 O18 D6), merged with the file it appends to by ts.
    before = _own_events_but(log_project, session, writer) if guard is not None else []
    if before:
        guard = (lambda inner: lambda evs: inner(list(heapq.merge(before, evs, key=lambda e: e["ts"]))))(guard)
    if "thread" not in fields:
        # The stamp (X2): every lifecycle event of a session that is a thread names it.
        thread = threads_module().stamp(session)
        if thread:
            fields["thread"] = thread
    elif fields["thread"] is None:
        del fields["thread"]   # the caller's choice of no thread: written unstamped, no stamp looked up
    if kind == "state" and "wake" not in fields and fields.get("thread"):
        # X3: a stopped thread's state says whether its machine wakes it, and why not, whichever of its writers
        # writes it; a `gone` one that has not ended (a spawned thread with no conversation here) says its hold.
        wake, why = state_wake(session, fields.get("state"))
        if wake:
            fields["wake"] = wake
        if why:
            fields["why"] = why
    event = {"kind": kind, "session": session, **fields}
    if kind == "joined":
        # What a joined publishes of the session's record was read before the
        # file's lock; under it, it is read again, so a writer that paused
        # between never appends provenance older than a publication since.
        guard = (lambda inner: lambda evs: _fresh_publication(event) and (inner is None or inner(evs)))(guard)
    elif kind == "retired" and isinstance(event.get("to"), str):
        published_redacted(event, aud)   # a successor named to no one its audience does not hold
    try:
        keep_stream(log_project, writer, aud)
        out = _append(log_project, writer, [event], guard=guard)
    except OSError as e:
        msg = "recording %s of %s in %s's log failed: %s" % (kind, session[:8], log_project.name, e)
        if required:
            raise LogWriteFailed(msg)
        warn(msg)
        return []
    if out and kind in ("joined", "renamed") and event.get("alias") and event.get("thread"):
        # The record keeps a copy of a human-opened thread's alias for readers without the log.
        try:
            threads_module().note_alias(session, str(event["alias"]), lock_until=_RECORD_DEADLINE,
                                        project=log_project)
        except (OSError, LockBusy) as e:
            warn("the alias of %s was not copied into its thread record: %s" % (session[:8], e or "its lock is busy"))
    return out


def join_seat(seat, by="", returns=False):
    """joined for the session a seat holds, unless its latest membership
    already is: a resume's, a `seat add`'s, a hand-off's. A seat this code
    ended (its record holds `ended`) returns by the journaled return
    (sminos_threads.begin): `ended` lifted and the `joined` owed in one
    write of the record, only when a fill authorized it (`returns`:
    `fill --resume`) or a process its end did not see holds its session
    (return_guard); else an ended seat is joined by nothing here (D1:
    nothing else returns it; a `seat add --session` of its own occupant
    no more than a resume)."""
    if not seat or not seat["current"]:
        return []
    project = seat_project(seat)
    if guessed(project):
        return []   # told, not read: its session's own hook joins it where it runs
    if project is not None:
        ensure_record(project, seat["current"], seat)
    fields = joined_fields(seat["alias"], "seat", seat_cwd(seat), seat["worktree"], seat["role"],
                           seat["seat_id"], by, "seat", session=seat["current"])
    thread = None
    if project is not None:
        threads = threads_module()
        finish_thread(seat["seat_id"], project=project)   # an open entry is finished before the record changes
        thread = threads.ensure(seat["current"], seat=reload_seat(seat["seat_id"]) or seat, project=project)
        fresh = reload_seat(seat["seat_id"]) or seat
        if thread is not None and threads.record_ended(thread) and thread["current"] == fresh["current"]:
            if not (returns or threads.returns(thread, running_now(fresh["current"]))):
                return []
            return thread_transition(project, thread["thread"], "return",
                                     [{"kind": "joined", "session": seat["current"], **fields}],
                                     guard=return_guard(thread, seat["current"], returns), **return_change(thread))
    return lifecycle(project, seat["current"], "joined",
                     guard=record_settled(thread, lambda evs: latest_membership(evs) != "joined"), **fields)


def record_settled(thread, guard):
    """`guard` with the thread's record read again under the writer file's
    lock, where the event is appended: an ordinary `joined` goes in only
    while the record has no open entry (a return's begun since owes its own
    `joined`) and has not ended (a return is journaled). `guard` alone for a session that is no thread."""
    if thread is None:
        return guard
    threads, tid = threads_module(), thread["thread"]

    def settled(evs):
        rec = threads.get(tid)
        if rec is not None and (rec.get("pending") or threads.record_ended(rec)):
            return False
        return guard is None or guard(evs)
    return settled


def thread_transition(project, thread_id, op, events, required=False, began=None, **begin):
    """One journaled transition of a thread record (sminos_threads.begin,
    then finish): the record's change and what it owes in one write, then
    the events. Returns the events this process appended; [] when the record
    refused it (an open entry finished first, then the guard), or when
    another finisher appended them. `began`, a list, gains the entry as
    begin wrote it, whoever finishes it: the one way to tell a transition
    begun from one refused. With `required`, an entry whose events could
    not all be appended raises LogWriteFailed: the record's change stands,
    and the next reconciliation finishes the entry."""
    threads = threads_module()
    if wake_held(thread_id) is None:
        finish_thread(thread_id, project=project, lock_until=begin.get("lock_until"))
    elif (threads.get(thread_id) or {}).get("pending"):
        # A caller's wake lock is never held across a replay (held_settled proved none open when it took it).
        release_wake(thread_id)
        return []
    # An absorption changes the owner of the record it absorbs: both wake locks for its begin, taken in ascending
    # order of thread id (each a bounded poll), so a wake of either is before it or after it, never across it.
    other, extra = begin.get("other"), []
    try:
        if other and op != "release":
            for tid in sorted({thread_id, other}):
                if wake_held(tid) is None:
                    transition_hold(tid, begin.get("lock_until"))
                    extra.append(tid)
        entry = threads.begin(thread_id, op, project, events, **begin)
    finally:
        release_wake(thread_id)   # a hold the caller took for its begin ends there: nothing is settled under it
        for tid in extra:
            release_wake(tid)
    if entry is None:
        return []
    if began is not None:
        began.append(entry)
    appended = []
    if not finish_thread(thread_id, appended, project, begin.get("lock_until")) and required:
        owed = [e for e in entry["events"] if not any(x["kind"] == e["kind"] and x.get("op") == entry["id"]
                                                      for x in appended)]
        if not owed and entry.get("settle"):
            raise LogWriteFailed("the %s of %s could not be completed yet (what is owed to it settled, or a seat it "
                                 "brings in line written); its record holds it, and the next reading verb finishes it"
                                 % (op, entry["settle"][:8]))
        e = owed[0] if owed else {"kind": op, "session": thread_id}
        raise LogWriteFailed("recording %s of %s in %s's log failed; its record holds it, and the next reading verb "
                             "finishes it" % (e["kind"], e["session"][:8], project.name))
    return appended


def finish_thread(thread_id, appended=None, project=None, lock_until=None):
    """sminos_threads.finish, its events appended through this module's own
    lifecycle, a hand-off's carry run by it (carry_hand_offs) and an end's
    settlement (settle_ended), so the caches a verb reads afterwards (its
    views) see them, whichever copy of this module loaded the threads
    module."""
    return threads_module().finish(thread_id, appended, project, append=lifecycle, lock_until=lock_until,
                                   before=carry_hand_offs, settle=settle_ended, stop=purge_stop)


def purge_stop(record, entry):
    """A purge entry's stop (sminos_threads.finish), from whichever process
    finishes it: the process the record's end recorded, while that same
    process still holds the session the entry settles (still running it,
    not started after the end: a process the end did not see returns the
    thread and is never stopped for it), by its harness row, or for a seat
    by the seat's recorded short (stop_seen_turn's rule). Nothing for an end
    that recorded no process, or a record that holds another session."""
    threads = threads_module()
    sid, ended = entry.get("settle"), record.get("ended") or {}
    if not sid or record.get("current") != sid or not ended.get("pid"):
        return
    seen = running_now(sid)
    if not seen or str(seen.get("pid")) != str(ended["pid"]) or threads.returns(record, seen, known=True):
        return
    seat = reload_seat(record["thread"]) if record["opened"] == "spawned" else None
    if seat is not None:
        stop_seen_turn(seat, seen, None)
        return
    agents_refresh()
    row = agent_row(session_id=sid)
    if row and row.get("id") and still_seen(seen, sid):
        claude_stop(row["id"])


def positions_to(project, session):
    """{writer: the seq} the events addressed to the session have reached in
    the local log, each writer's latest: a return's boundary (its `until`),
    which a writer's seq places whatever the clock of the machine that
    wrote it."""
    out = {}
    for e in log_read(project, to_session=session):
        out[e["writer"]] = max(out.get(e["writer"], 0), int(e["seq"]))
    return out


def channel_positions(channel_id):
    """{writer: its latest seq} in the channel's log as this machine holds it
    now (CH1's §4): where a membership that begins now begins. {} for a log
    that holds nothing, and for a channel not registered here (no
    registration file); PositionsUnread for a registration, a log or a
    writer file that is there and cannot be read. Read with no
    lock, each writer file's last line (_last_seq), its writer its first
    line's: by set_channels for a channel entering a set, by a return for
    every channel of its set, each under the record's store lock."""
    if not is_channel_id(channel_id):
        return {}
    # The registration read here, not through the tolerant lookup (registration reads a file it cannot read as
    # none): a channel registered and unreadable for a moment is no channel without a log.
    try:
        d = json_at(os.path.join(projects_root(), channel_id, "project.json"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise PositionsUnread("the registration of channel %s could not be read: %s" % (channel_id[:8], e)) from e
    project = _registered_as(channel_id, d)
    if project is None:
        raise PositionsUnread("the registration of channel %s is no registration of it" % channel_id[:8])
    where = os.path.join(project.home, "log")   # read as it is: nothing is made for a log that holds nothing
    try:
        names = sorted(n for n in os.listdir(where) if n.endswith(".jsonl"))
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise PositionsUnread("the log of channel %s could not be listed: %s" % (channel_id[:8], e)) from e
    out = {}
    for name in names:
        try:
            with open(os.path.join(where, name), "rb") as f:
                first = next((e for e in (parse_event(line.decode("utf-8", "replace")) for line in f
                                          if line.strip()) if e), None)
                if first is not None:
                    out[first["writer"]] = max(out.get(first["writer"], 0), _last_seq(f))
        except OSError as e:
            # A writer file that is there and cannot be read is no empty history: a boundary taken without it
            # would stand for good. The transition is not made.
            raise PositionsUnread("%s of channel %s could not be read: %s" % (name, channel_id[:8], e)) from e
    return out


class PositionsUnread(Exception):
    """channel_positions met a log or a writer file that is there and could
    not be read: where a membership begins is not known, and nothing is
    written (sminos_threads.set_channels lets it through)."""


def settle_ended(project, session, lock_until=None, until=None):
    """An end's settlement (Interfaces §6, step 3), or a return's, of what
    reached the log up to `until` (positions_to): what is owed to the session of a thread
    that ended, settled `recorded` (sminos_outcomes.settle_ended); whether
    nothing is owed to it now."""
    return sibling_module("sminos_outcomes").settle_ended(project, session, lock_until, until=until)


def seats_by_session(project, all_seats):
    """{session: seat}: the seat that binds a session in the project's
    projection. The legacy conversion can leave one session in seats of
    several projects, and there the project's own seat (its cwd resolves to
    the project) binds it, never another project's. A session the project
    holds no seat for is bound by the seat that holds it elsewhere: a seat
    whose cwd moved still stands for the session it holds, one seat one
    target (find_target)."""
    out, own = {}, set()
    for s, pid in _seat_pids(all_seats):
        sid = s["current"]
        if not sid:
            continue
        mine = pid == project.id
        if mine or sid not in own:
            out[sid] = s
            if mine:
                own.add(sid)
    return out


_SEAT_PIDS = {}   # id(a seat read) → (that read, [(seat, its project's id or None)]), per cache generation


def _seat_pids(all_seats):
    """Each seat of a seat read with its project's id (seat_project), once
    per read and cache generation: every project's view asks of every seat."""
    held = _SEAT_PIDS.get(id(all_seats))
    if held is None or held[0] is not all_seats or len(held[1]) != len(all_seats):
        held = _SEAT_PIDS[id(all_seats)] = (all_seats, [(s, (p.id if (p := seat_project(s)) else None))
                                                        for s in all_seats])
    return held[1]


def _local_sessions(project, all_seats):
    """This machine's evidence of sessions in the project: {session: {"seat",
    "peer"}} for every seat whose cwd resolves to it and every running harness
    session whose project it is (record_project: its launch directory's, or
    the one it joined), internal forks aside. A session whose project was
    told rather than read (Guessed: its directory is one this process may
    not read) is evidence of nothing: what is recorded of it stands."""
    local = {}
    for s, pid in _seat_pids(all_seats):
        if s["current"] and pid == project.id and not guessed(seat_project(s)):
            local.setdefault(s["current"], {})["seat"] = s
    internal = internal_pids()
    for rec in peer_records():
        sid, cwd = rec.get("sessionId"), rec.get("cwd")
        if not (isinstance(sid, str) and UUID_RE.fullmatch(sid) and isinstance(cwd, str) and cwd):
            continue
        if str(rec.get("pid")) in internal:
            continue
        p = record_project(rec)
        if p is not None and not guessed(p) and p.id == project.id and peer_running(rec):
            local.setdefault(sid, {})["peer"] = rec
    return local


def _reconcile(project, events, local, by_session, all_seats=None):
    """Append joined for this machine's sessions the log does not hold as
    members: a live session whose latest membership is absent or retired (a
    live process is evidence of activation), and a seat with no membership
    event at all. A seat whose record is retired is re-joined here only by
    its return (T1's M4): a process its end did not see holds its session
    (its human reopened it); a session still answering after `retire` saw
    it is not a revival, and a seat an older copy retired returns by a fill
    alone. Each check is repeated under the session file's lock, so a
    concurrent retire cannot be undone.

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
    latest, joined, effect = log_memo(events, "memberships", _memberships)
    threads = threads_module()
    out, busy = [], set()
    human = threads.human_threads()
    # A transition whose process died is finished first, and nothing else is
    # done to its record in this pass (Interfaces §6, the replay).
    for t in threads.open_entries(project, human, seats() if all_seats is None else all_seats):
        busy.update(str(e.get("session") or "") for e in t["pending"].get("events") or [])
        busy.add(t["current"])
        finish_thread(t["thread"], out, project)
    out += older_writes(project, human, effect, joined, busy)
    out += older_hand_offs(project, human, effect, joined, busy)
    # The sessions of this machine's live human-opened records, not ended: when no process holds one, it is a
    # stopped thread, which no reconciliation retires (M3); the lane is asked of no other.
    stopped = {t["current"] for t in human if t["current"] and not threads.record_ended(t) and not t.get("pending")}
    for sid, e in joined.items():
        if latest[sid] != "joined" or sid in local or sid in busy or not is_self(str(e.get("machine") or ""), sid):
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
            if (sid, successor) not in _HANDOFF_REFUSED:
                continue
        if sid in stopped and threads.stamped(e) and threads.lane_a(sid):
            continue   # a stopped thread, adopted already: it stays a member (the sweep marks the stop)
        out += end_closed(project, sid, events, e)
    # A verb a marked session's tools run speaks for that session alone; an
    # internal fork's, for none.
    own = (os.environ.get("CLAUDE_CODE_SESSION_ID")
           if os.environ.get(MEMBER_MARK) and not os.environ.get("SMNS_INTERNAL") else None)
    for sid, ev in local.items():
        seat, peer = by_session.get(sid), ev.get("peer")
        if sid in busy:
            continue
        if (latest.get(sid) == "joined") if peer else (sid in latest):
            if latest.get(sid) == "joined" and seat is not None and not peer and (ended := end_lane_b_seat(
                    project, sid, seat)):
                out += ended   # row 13 for a seat: a spawned thread turned lane B, its process ended
                continue
            if latest.get(sid) == "joined":
                # A member with no record (an older binary joined it), or a
                # provisional one its lineage can now settle (an older
                # binary's hand-off), has it written or replaced here.
                ensure_record(project, sid, seat, peer, events=events)
                out += adopt(project, sid, seat, peer, joined[sid], events)
                out += refresh_joined(project, sid, joined[sid])
            continue
        out += join_on_sight(project, sid, seat, peer, bool(peer), recheck=lambda ev=ev: here_now(project, ev),
                             marked=sid == own and member_mark(peer), events=events)
    for sid, ev in local.items():
        seat = ev.get("seat")
        if seat and "peer" not in ev and seat["status"] != "retired" and (successor := continued_in(sid)):
            out += hand_off(project, sid, successor)
    return out


def _reconcile_channel(project, events, by_session):
    """A channel's reconciliation: the one write C4 allows there, the undo of
    an older copy's `joined` of a session of this machine, `retired` `moved`
    to the project the session is in, written only while a seat or a process
    holds the session (retire_moved, its project read again under the
    lock). A closed session's `joined` is left as it is until the session
    runs again; nothing else of _reconcile runs (no join, no end, no thread
    made or adopted, no hand-off)."""
    latest, joined, _ = log_memo(events, "memberships", _memberships)
    out = []
    for sid, e in joined.items():
        if latest[sid] != "joined" or not is_self(str(e.get("machine") or ""), sid):
            continue
        seat = by_session.get(sid)
        if seat is not None and seat["current"] == sid:
            out += retire_moved(project, sid, seat_project(seat), lambda seat=seat: seat_project(seat, fresh=True))
            continue
        rec = session_running(sid)
        if rec is not None and str(rec.get("pid")) not in internal_pids():
            out += retire_moved(project, sid, record_project(rec), lambda rec=rec: record_project(rec, fresh=True))
    return out


def end_closed(project, sid, events, joined=None):
    """A seat-less member of this machine whose process no longer runs and
    that no seat holds. A thread (lane A) stays a member, `stopped` (M3: the
    sweep marks the stop; what is addressed to it is held), adopted here when
    it has no record yet, and joined again, stamped, when its `joined` in
    effect (`joined`) is an older copy's (§6, row 3). A lane B session
    leaves with its process, `retired` `ended`: stamped, its record ended
    first (Interfaces §6, the end: `ended` and the event owed in one write,
    the record set aside last), when it has a thread record from an earlier
    lane A life (row 13); today's unstamped event otherwise."""
    threads = threads_module()

    def gone():
        return not session_running(sid) and not any(s["current"] == sid for s in seats())

    thread = threads.thread_of(sid)
    if threads.lane_a(sid):
        if thread is None or thread["current"] != sid:
            try:
                thread = threads.ensure(sid, project=project, events=events)
            except (OSError, LockBusy) as e:
                warn("the thread record of %s could not be made: %s" % (sid[:8], e or "its lock is busy"))
                return []
        if thread is None or thread.get("pending") or threads.record_ended(thread) or joined is None \
                or threads.stamped(joined):
            return []
        return join_stopped(project, sid, thread, lambda e: e["kind"] == "joined" and not threads.stamped(e))
    if thread is not None and thread["opened"] == "human" and thread["current"] == sid \
            and not threads.record_ended(thread):
        return end_human_lane_b(project, sid, thread, gone)

    def ended(evs):
        return latest_membership(evs) == "joined" and gone()

    return lifecycle(project, sid, "retired", guard=ended, required=False, by="", reason="ended")


def end_human_lane_b(project, sid, thread, gone):
    """Row 13 for a record its human opened: the session's end journaled in
    the thread store (`ended` and the stamped `retired` it owes in one
    write, the record set aside last), while gone() holds under its lock."""
    threads = threads_module()
    return thread_transition(
        project, thread["thread"], "end", [{"kind": "retired", "session": sid, "by": "", "reason": "ended"}],
        fields={"ended": {"at": now(), "reason": "ended", "by": "", "pid": None}},
        guard=lambda t: t["current"] == sid and not threads.record_ended(t) and gone(), settle=sid, last="aside",
        seat=seat_over(sid, "retired", thread["thread"]))


def end_by_rule(thread, stopped, asked=None):
    """A thread stopped for more than the period ended by the rule (T1's M4,
    Interfaces §6 row 10), by the thread sweep alone (sminos_daemon's ending
    pass): the record first — `ended`, reason `ended` and no process, and
    for a seat its `status` retired (the form older code reads as a retired
    seat, D7) — with the stamped `retired` `ended` owed; then the event,
    the settlement of what was held for it, and a record its human opened
    set aside last. Begun only while, under the record's lock, its stop
    mark is still `stopped`, its current session the same, and no process
    holds that session by the engine's records read afresh, every
    session it has had is among the short ids devcloud was asked about
    (`asked`, M5: its answer was none for them), and it is the session's
    canonical record (thread_of: never a seat an older copy made over a
    thread its human opened). In the session's own
    project: a seat's, else the one its membership in effect puts it in.
    The events appended."""
    threads = threads_module()
    cur, tid = thread["current"], thread["thread"]
    seat = reload_seat(tid) if thread["opened"] == "spawned" else None
    project = seat_project(seat) if seat is not None else last_project(cur)
    if project is None or guessed(project):
        return []
    at = now()
    fields = {"ended": {"at": at, "reason": "ended", "by": "", "pid": None}}
    if seat is not None:
        fields.update(status="retired", updated=at)

    def guard(r):
        # Only the canonical record of the session (thread_of): a seat an older copy made over a thread its human
        # opened is not ended for it, whose own record (and its owners) decide that thread's end.
        return r["current"] == cur and r.get("stopped") == stopped and not threads.record_ended(r) \
            and threads.asked_all(r, asked) and not running_now(cur) \
            and (threads.thread_of(cur) or {}).get("thread") == tid

    return thread_transition(project, tid, "end", [{"kind": "retired", "session": cur, "by": "", "reason": "ended"}],
                             fields=fields, guard=guard, settle=cur, last="aside" if seat is None else None,
                             seat=seat_over(cur, "retired", tid) if seat is None else None)


def end_lane_b_seat(project, sid, seat):
    """Row 13 for a seated session (Interfaces §6): a thread whose session
    turned lane B and whose process then ended leaves with its process. The
    record is the one thread_of reads for it, never the seat row alone: a
    record its human opened that an older CLI also seated ends in the thread
    store (end_human_lane_b), its entry bringing the seat in line; a spawned thread, the
    seat's own record, ends as end_seat journals one — the record first
    (`status` retired and `ended`, reason `ended`, with the event owed, in
    one write), then the stamped `retired` — and the seat stays, reading
    `retired`. A lane A session's seat is not touched; nor one whose process
    runs, or whose record ended already or holds an open entry."""
    threads = threads_module()
    if threads.lane_a(sid) or session_running(sid):
        return []
    t = threads.thread_of(sid)
    if t is None or t["current"] != sid or t.get("pending") or threads.record_ended(t):
        return []
    if t["opened"] == "human":
        return end_human_lane_b(project, sid, t, lambda: not session_running(sid))
    if t["thread"] != seat["seat_id"]:
        return []
    at = now()
    return thread_transition(
        project, seat["seat_id"], "end", [{"kind": "retired", "session": sid, "by": "", "reason": "ended"}],
        fields={"status": "retired", "updated": at, "ended": {"at": at, "reason": "ended", "by": "", "pid": None}},
        guard=lambda t: t["current"] == sid and not threads.record_ended(t) and not session_running(sid),
        settle=sid)


def join_stopped(project, sid, thread, in_effect):
    """A stopped thread's session joined again, stamped, as adoption joins a
    member again (joined_again; §6, row 3): when an older copy's `joined`
    is its membership in effect, or an older copy's `ended` after one
    (§6, "An older copy's writes"). Under the writer file's lock, only while
    in_effect(the event in effect) still holds, no process runs the session
    (a reopened one is joined on sight instead) and the record is settled
    (record_settled)."""
    threads = threads_module()
    fields = joined_again(_own_events(project, sid), sid)
    if fields is None:
        return []
    fields["thread"] = thread["thread"]

    def guard(evs):
        e = threads.in_effect(evs)
        return e is not None and in_effect(e) and not session_running(sid)

    return lifecycle(project, sid, "joined", guard=record_settled(thread, guard), required=False, **fields)


def older_writes(project, live, effect, joined, busy):
    """What an older sminos on this machine wrote that this record must
    follow (Interfaces §6, "An older copy's writes"), for a human-opened
    record with no open entry whose current session is in the project and
    whose record does not say it ended: an unstamped `retire` in effect is
    an end that owes no event, with its `by`, `pid` and time; an unstamped
    `ended` in effect (its `joined` unstamped too: an older hook's, or one
    written before threads) is, while no process holds the session, undone:
    a lane A thread is joined again, stamped, as adoption writes one (it is
    stopped, M3), and a lane B one is ended, reason `ended`, owing no event.
    An
    unstamped `ended` after a stamped `joined` is passed by and needs
    nothing. Only in the project whose membership is in effect for the
    session (membership_here: no later own event in another project, such
    as a reopening joined there); under the record's lock, as the end is
    begun, the retirement read is still the one in effect (still_in_effect:
    no joined since) and the project still the session's. `live`: this machine's human-opened records as the
    pass read them."""
    threads = threads_module()
    holding = {t["current"]: t for t in live if t["current"]}
    out = []
    for sid, e in effect.items():
        if sid not in holding or e["kind"] != "retired" or e.get("reason") not in ("retire", "ended") \
                or threads.stamped(e) or sid in busy:
            continue
        t = holding[sid]
        j = joined.get(sid) or {}
        if t.get("pending") or threads.record_ended(t) or not is_self(str(j.get("machine") or ""), sid):
            continue
        if e["reason"] == "ended" and session_running(sid):
            continue
        if not membership_here(project, sid):
            continue
        if e["reason"] == "ended" and threads.lane_a(sid):
            # From M3 an older copy's `ended` for a stopped thread is undone: joined again, stamped.
            out += join_stopped(project, sid, t, lambda x, e=e: (x.get("writer"), x.get("seq"))
                                == (e.get("writer"), e.get("seq")))
            continue
        ended = {"at": str(e.get("ts") or now()), "reason": e["reason"], "by": str(e.get("by") or ""),
                 "pid": e.get("pid") or None}
        out += thread_transition(project, t["thread"], "end", [], fields={"ended": ended},
                                 guard=lambda r, sid=sid, e=e: r["current"] == sid and not threads.record_ended(r)
                                 and still_in_effect(project, sid, e) and membership_here(project, sid),
                                 settle=sid, last="aside", seat=seat_over(sid, "retired", t["thread"]))
    return out


def older_hand_offs(project, live, effect, joined, busy):
    """A hand-off whose log part an older sminos wrote (its `continued`
    retirement, and maybe the job's unstamped `joined`) while the thread's
    record still names the session it left: finished as any hand-off is
    (hand_off, which owes the job's `joined` under the thread's stamp and
    not the retirement again), for a human-opened record of this machine
    with no open entry that has not ended. A seat needs none: an older copy
    moved the seat itself, and adoption stamps the job's `joined`. `live`:
    this machine's human-opened records as the pass read them."""
    threads = threads_module()
    out = []
    for t in live:
        sid = t["current"]
        e = effect.get(sid)
        if not sid or e is None or e["kind"] != "retired" or e.get("reason") != "continued" or sid in busy \
                or t.get("pending") or threads.record_ended(t) or threads.stamped(e):
            continue
        if not UUID_RE.fullmatch(str(e.get("to") or "")) or not is_self(str((joined.get(sid) or {}).get("machine")
                                                                             or ""), sid):
            continue
        out += hand_off(project, sid, e["to"])
    return out


def still_in_effect(project, sid, event):
    """Whether `event` (a reconciliation's reading) is still the session's
    membership in effect in the project's log, read afresh."""
    now_in = threads_module().in_effect(_own_events(project, sid))
    return now_in is not None and (now_in.get("writer"), now_in.get("seq")) == (event.get("writer"), event.get("seq"))


def membership_here(project, sid):
    """Whether the session's membership in effect, across the projects known
    here, is the one it holds in `project`: its latest own membership event
    of this machine is there (last_project, read afresh)."""
    _LAST.pop(sid, None)
    p = last_project(sid)
    return p is not None and p.id == project.id


def adopt(project, sid, seat, peer, last, events):
    """A local lane A member whose membership in effect is an unstamped
    `joined` (`last`: one from before threads, or one an older copy's hooks
    wrote since) gets its thread record, its sessions rebuilt from the log,
    and is joined again, stamped, once (Interfaces §6, row 3; the fields
    as publish_owners joins a member again). A record that says the thread
    ended is returned instead, when the process holding the session is one
    the end did not see (row 12). Returns the events appended."""
    threads = threads_module()
    if threads.stamped(last):
        return []
    if project.hub is not None and writer_base(str(last.get("writer") or "")) != writer_id(sid):
        return []   # joined under a former name of this machine: the daemon's rejoin_former joins it again, stamped
    if seat is None and threads.awaits_seat(sid, peer, sid == os.environ.get("CLAUDE_CODE_SESSION_ID")):
        return []
    if not threads.lane_a(sid):
        return []   # row 3 adopts a lane A member alone
    try:
        thread, action = threads.choose(sid, seat, project, events, peer)
    except (OSError, LockBusy) as e:
        warn("the thread record of %s could not be made: %s" % (sid[:8], e or "its lock is busy"))
        return []
    fields = joined_again(_own_events(project, sid), sid) if thread is not None and action != "hold" else None
    if fields is None:
        return []
    fields["thread"] = thread["thread"]   # the event names the thread chosen here, whatever stamp() reads
    if thread["opened"] == "spawned":
        # A seat's thread joins under its seat, as joined_fields gives a seat (its older joined can predate
        # the binding: a bg join with no seat); a human thread keeps the legacy fields as they are.
        fields.update(seat=thread["thread"], alias=thread["alias"] or fields["alias"], name_source="seat")
    if action == "return":
        return thread_transition(project, thread["thread"], "return", [{"kind": "joined", "session": sid, **fields}],
                                 guard=return_guard(thread, sid), **return_change(thread))

    def guard(evs):
        e = threads.in_effect(evs)
        return e is not None and e["kind"] == "joined" and not threads.stamped(e)

    return lifecycle(project, sid, "joined", guard=record_settled(thread, guard), required=False, **fields)


def _memberships(events):
    """({session: the kind of its own membership event in effect}, {session:
    its latest own joined}, {session: that event}) of a log as read, for
    _reconcile: the reducer folded over it (sminos_threads.Fold)."""
    fold = threads_module().Fold()
    for e in events:
        if e["kind"] in MEMBERSHIP and e.get("session") and writer_session(e["writer"]) == e["session"]:
            fold.add(e["session"], e)
    return {sid: e["kind"] for sid, e in fold.effect.items()}, fold.joined, fold.effect


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
        if p is not None and not guessed(p) and p.id == project.id:
            return project
    return None


def retire_moved(project, sid, where, recheck=None):
    """`retired`, reason `moved`, for a member of the project whose project
    is now `where`, naming it; nothing when `where` is the project itself,
    no project (a session in none stays where it was), or one told rather
    than read (Guessed: its directory is one this process may not read, so
    what is recorded stands). `recheck`, when
    given, resolves the session's project again under the session file's
    lock: what a reconciliation read a moment ago may have changed since (a
    `join` meanwhile), and the move is written only if it still holds."""
    if where is None or guessed(where) or where.id == project.id:
        return []

    def guard(evs):
        if latest_membership(evs) != "joined":
            return False
        now_in = recheck() if recheck else where
        return now_in is not None and not guessed(now_in) and now_in.id == where.id

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
    project. The `by` of its joined says so (`move`): from a channel too, where
    an older copy's `join` put it."""
    for p in known_logs():
        if p.id == project.id:
            continue
        last = threads_module().in_effect(_own_events(p, sid))
        if last and (last["kind"] == "joined" or (last.get("reason") == "moved" and last.get("project") == project.id)):
            return True
    return False


def joinable(seat, peer, marked=False):
    """Whether a session of this machine is a member on sight: a seat whose
    record is not retired, or a retired one whose session a process holds,
    which returns it when its end did not see that process
    (sminos_threads.choose, returns; T1's M4: its human reopening it); or a
    seat-less session the harness records as
    `interactive` or `bg` whose entrypoint is no headless or SDK run (`sdk-*`:
    another tool's `claude -p` is no member, whatever its kind) unless its
    host marked it (`marked`, member_mark)."""
    if seat:
        return seat["status"] != "retired" or bool(peer)
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


def retirement_holds(events, peer, ended=False):
    """Whether a seat-less session's `retire` still holds against the process
    its harness record shows. With `ended`, the session's thread record says
    its thread ended: a `retire` is then the record's to answer
    (sminos_threads.returns, from the end's own process and time; T1's M4),
    and only a hand-off or a refill holds here. A retirement holds for the life of the process
    that ran when it was recorded: an interactive session has nothing the
    harness can stop, so its process runs on in its human's terminal, and
    re-joining it on sight would undo the retire at the next reading verb.
    The record shows a different process when its pid differs from the one
    the retirement recorded, or when it started after the retirement (a
    resume opens a new process, so a resumed session re-joins, §2). So does
    a hand-off (`continued`): the process that handed its session to a
    background job runs on for a while as it exits, and so does a refill
    (`replaced`), which names no process: the one that ran then is told by
    its start. A retirement for any other reason (`ended`: its process was
    not seen) does not hold against a running process."""
    last = threads_module().in_effect(events)
    if not last or last["kind"] != "retired" or last.get("reason") not in ("retire", "continued", "replaced") \
            or ended and last["reason"] == "retire":
        return False
    peer = peer or {}
    if last.get("pid") not in (None, "") and str(last["pid"]) != str(peer.get("pid")):
        return False
    started, retired = process_started(peer), _ts_epoch(last.get("ts"))
    return started is None or retired is None or started <= retired


def join_on_sight(project, sid, seat, peer, running, by=None, recheck=None, marked=False, evidence=None,
                  events=None, own=None):
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
    the joined carries what it publishes once it is final. Never into a
    project told rather than read (Guessed): the session's own process joins
    it where it works.

    The thread comes before the `joined`, chosen by sminos_threads.choose
    (as adopt chooses it): a human-opened record before a seat, a seat's
    keys, else a record of its own under a minted id; none revived for a
    lane B session. The event names it explicitly. A spawn's child that no seat holds yet joins nothing
    (awaits_seat; `own`, the caller runs for the session: its hook, a verb
    of its own). A session whose record says its thread ended returns by
    the journaled return, when its process is one the end did not see. A
    record the hook cannot have its lock for in time is skipped, the joined
    written unstamped, for the next reconciliation to adopt."""
    if guessed(project) or not joinable(seat, peer, marked):
        return []
    threads = threads_module()
    own = sid == os.environ.get("CLAUDE_CODE_SESSION_ID") if own is None else own
    if not seat and threads.awaits_seat(sid, peer, own):
        return []
    # A retire of a thread is its record's to answer (choose, from the end's process): only a hand-off and a
    # refill hold here, and a retire of a session that has no record saying it ended (lane B; an older copy's).
    ended = threads.record_ended(threads.thread_of(sid)) if not seat and running else False
    if not seat and running and retirement_holds(_own_events(project, sid), peer, ended):
        # The process that handed its session off (or whose seat was refilled) runs on as it exits: no thread
        # record and no joined for it. Only another process, or one started after, makes it a thread again.
        return []
    returning = []   # the choice below is a return: an ended seat it returns reads `retired` until then

    def guard(evs):
        last = latest_membership(evs)
        if (last == "joined") if running else (last is not None):
            return False
        if not seat and retirement_holds(evs, peer, ended):
            return False
        if recheck is not None and ((p := recheck()) is None or p.id != project.id):
            return False
        if recheck is not None and moving_elsewhere(sid):
            return False   # a `join` is moving it here: its own join follows, by `join` (read after the override)
        fresh = reload_seat(seat["seat_id"]) if seat else None
        return not (seat and (fresh is None or fresh["status"] == "retired" and not returning))

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
            if not old:
                old = handed_to(project, sid)   # retired to it already: its thread's advance may still be owed
            if old:
                out += hand_off(project, old, sid, old_peer)
                if (old, sid) in _HANDOFF_REFUSED:
                    old = None   # not its continuation: it joins as a thread of its own
            if old:
                held = own_alias(_own_events(project, old), old)
        ensure_record(project, sid, seat, peer, evidence, events=events)
        alias, source = held_alias(*held, peer, sid, shadowing(project, sid))
        fields = joined_fields(alias or sid[:8], source or "derived",
                               launch_cwd(sid, fallback=str(peer.get("cwd") or ""), fresh=True), by=by,
                               session_kind=str(peer.get("kind") or ""), session=sid)
    chosen = True   # choose answered: its None is a join stamped with no thread, never a stamp looked up
    try:
        thread, action = threads.choose(sid, seat, peer=peer, lock_until=_RECORD_DEADLINE)
    except LockBusy:
        chosen = False
        thread, action = None, "join"
        try:
            daemon_log("record: the thread record of %s waits for its lock: the next reconciliation makes it"
                       % sid[:8])
        except OSError:
            pass
    except OSError as e:
        thread, action, chosen = None, "join", False
        warn("the thread record of %s could not be written: %s" % (sid[:8], e))
    if thread is not None and thread.get("pending"):
        # An open entry is its record's until it is finished (§6, 6): never a join around it. The hook,
        # whose wait is bounded, leaves it to the next reconciliation's replay and writes nothing.
        if _RECORD_DEADLINE is not None or not finish_thread(thread["thread"], project=project):
            return out
        thread, action = threads.choose(sid, seat, peer=peer)
    if action == "hold":
        return out
    if thread is not None:
        fields["thread"] = thread["thread"]   # the event names the thread chosen here, whatever stamp() reads
    elif chosen:
        fields["thread"] = None   # no thread chosen (a lane B session a thread only had): none looked up either
    if action == "return":
        returning.append(True)
        if not guard(_own_events(project, sid)):
            return out
        try:
            joined = thread_transition(project, thread["thread"], "return",
                                       [{"kind": "joined", "session": sid, **fields}],
                                       guard=return_guard(thread, sid), lock_until=_RECORD_DEADLINE,
                                       **return_change(thread))
        except LockBusy:
            return out
    else:
        joined = lifecycle(project, sid, "joined", guard=record_settled(thread, guard), required=False, **fields)
    if joined:
        position_carry(project, sid)
    return out + joined


def return_guard(thread, sid, authorized=False):
    """A return's guard, run under the record's lock as it begins (§6, row
    12): the record still holds the very end the return was chosen for
    (`ended`, its time, its `by` and its process: a newer end, a
    self-retire since, is not undone), still for `sid`, and the session's
    process, read afresh (running_now), is one that end did not see
    (sminos_threads.returns) — unless a fill authorized it (`authorized`:
    `fill --resume`, which launched that process for the seat)."""
    threads, end = threads_module(), thread.get("ended")

    def guard(t):
        return t["current"] == sid and threads.record_ended(t) and t.get("ended") == end \
            and (authorized or threads.returns(t, running_now(sid)))
    return guard


def return_change(thread):
    """What a return writes in the record (Interfaces §6, row 12): `ended`,
    `stopped` and `swept` removed (a record set aside is brought back by
    `begin`), and a seat's `status` no longer `retired`; begin()'s `fields`
    and `remove`. Its entry settles what reached the log for the session
    while the end stood (`settle`, up to `until`, the log positions begin reads under the record's lock:
    sminos_threads.finish) before its `joined`, so the returned session is
    pushed nothing of its ended interval, and what comes after is its own.
    A seat an older copy gave a human-opened thread, retired with it, is
    brought back in the same entry (`seat`, sminos_threads._project_seat)."""
    remove = ("ended", "stopped", "swept")
    owed = {"settle": thread["current"]}   # its `until` is set by begin, under the record's lock
    if thread["opened"] == "spawned":
        return {"fields": {"status": "idle", "updated": now()}, "remove": remove, **owed}
    # A seat an older copy gave it, retired with it, follows it back in the same entry.
    seat = next((x for x in seats() if x["current"] == thread["current"] and x["status"] == "retired"), None)
    return {"remove": remove, **owed, **({"seat": {"id": seat["seat_id"], "session": thread["current"],
                                                   "to": "idle"}} if seat else {})}


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
        last = threads_module().in_effect(_own_events(project, old))
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
    already held: the address stays the one its peers know. Nor does the
    engine's own title, whatever source its record gives it
    (titled_by_engine).

    Nor is a harness name taken that would shadow a live identity, the alias
    of a seat or of another current member of the project (`shadowed`, from
    shadowing): a `--bg` copy inherits its source's name, and the engine's
    record says `user` for it as for a /rename. The session keeps the alias
    it holds, else its short id, and its title still shows the name.

    Nor is the name a session gave up at a `/clear` (its thread record's
    `released`, M3) taken back by it while the release stands: the session
    that took its place holds it (sminos_threads.released_alias)."""
    name = str((peer or {}).get("name") or "")
    source = str((peer or {}).get("nameSource") or "derived")
    if logged == session[:8]:   # the placeholder a nameless session joined under
        logged = ""
    if name or logged:
        released = threads_module().released_alias(session, peer)
        if released:
            name = "" if name == released else name
            logged, logged_source = ("", "") if logged == released else (logged, logged_source)
    if name and logged and name != logged and source not in GENERATED_NAMES and titled_by_engine(session, name):
        source = "auto"   # the engine's own title, restored as a given name: made up all the same
    if name and (source not in GENERATED_NAMES or not logged) \
            and not (name != logged and shadowed is not None and shadowed(name)):
        return name, source
    return (logged, logged_source) if logged else ("", "")


def shadowing(project, session, info=None, all_seats=None, released=()):
    """held_alias's `shadowed` for a session of `project`: whether a name is
    the alias of a seat of the project that is not retired, or of a current
    member of it (its latest membership `joined`) other than the session and
    the sessions it continues. A member that gave the name up at a `/clear`
    (its record's `released`, M3; `released`, the sessions a caller knows
    to be giving it up now: cleared_witness) holds it no more. `info`
    (_projection) and `all_seats` when the caller holds them; else read at
    the first question, which only a harness name that differs from the
    alias the session holds raises."""
    if project is None:
        return None

    def shadowed(name):
        nonlocal info, all_seats
        if info is None:
            info = _projection(log_read(project, kinds=MEMBERSHIP + ("renamed",)))
        mine = {session, *lineage(session, info), *released}
        threads = threads_module()
        if any(sid not in mine and r["latest"] and r["latest"]["kind"] == "joined"
               and logged_alias(sid, info)[0] == name and threads.released_alias(sid) != name
               for sid, r in info.items()):
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
                    found = to if UUID_RE.fullmatch(to) and to != session else ""
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
        if (isinstance(old, str) and old != session and UUID_RE.fullmatch(old) and rec.get("kind") == "interactive"
                and peer_running(rec) and (p := record_project(rec)) is not None
                and p.id == project.id and continued_in(old) == session):
            return old, rec
    for s in project_seats(project):
        old = s["current"]
        if old and old != session and s["status"] != "retired" and not session_running(old) \
                and continued_in(old) == session:
            return old, None
    return None, None


_HANDOFF_REFUSED = set()   # (old, new) whose absorption this process refused (hand_off): said once, never retried


def hand_off(project, old, new, old_peer=None):
    """Record that the member `old` stood for continues in session `new`
    (continued_in), and return the events appended. The continuation is
    the engine's, read as today; what it carries is the thread (Interfaces
    §6, rows 4 and 5): the record of the thread `old` is the current
    session of — a seat, or one its human opened — advances to `new` by one
    journaled write (`current` and `sessions`, and a seat's short), which
    owes `old`'s retirement, reason `continued`, naming `new` (and the
    process it saw, which may still be exiting: retirement_holds), then
    `new`'s `joined` under the thread's stamp and alias. The entry names
    the pair it carries (`carry`), whatever it owes: before the events
    (sminos_threads.finish's `before`, so a replay does it too) the steps
    each safe to repeat: `new`'s record takes `old`'s provenance by
    ensure_record(…, former=[old]), the one call that carries reach, and
    the chat cursor and the join override are carried (carry_hand_off);
    until that provenance is `new`'s record (carried) nothing is appended,
    and the entry stays open. A retirement already in the log (an older
    copy wrote it) is not owed again; the carry and the `joined` still are.
    The membership read before the lock (`old`'s event in effect, and the
    project it is in) is read again in the guard, under the record's lock.

    A job that joined before its hand-off was written has a record of its
    own by then: the advance absorbs it, deleting it as the entry's last
    step, when it is one its human opened, has not ended, holds that one
    session and has no open entry. Those guards are read before anything
    is carried; when they fail the hand-off is not recorded at all, nothing
    of reach moves, the two stay two threads, and daemon.log says so once
    (`_HANDOFF_REFUSED`: the caller then reads `old` as any session whose
    process is gone). The job's record is held from the entry's first step,
    under its own lock (sminos_threads.finish): one changed by then undoes
    the advance, and the hand-off is refused the same way. A session that
    is no thread (lane B) is handed off as before threads
    (hand_off_untracked). The hook, whose wait is bounded, leaves an open
    entry, and a record lock it cannot have in time, to the next
    reconciliation."""
    threads = threads_module()
    thread = threads.thread_of(old, ended=False)
    try:
        if thread is None and threads.lane_a(old):
            thread = threads.ensure(old, project=project, lock_until=_RECORD_DEADLINE)   # adopted first
        if thread is None:
            return hand_off_untracked(project, old, new, old_peer)
        if thread.get("pending"):
            if _RECORD_DEADLINE is not None or not finish_thread(thread["thread"], project=project):
                return []
            thread = threads.get(thread["thread"])
    except (OSError, LockBusy) as e:
        warn("the hand-off of %s to %s waits: %s" % (old[:8], new[:8], e or "its record's lock is busy"))
        return []
    if thread is None or thread["current"] != old or threads.record_ended(thread):
        return []
    own = _own_events(project, old)
    last = threads.in_effect(own)
    if last is None:
        return []
    owed = []
    if last["kind"] == "joined":
        owed.append({"kind": "retired", "session": old, "by": "", "reason": "continued", "to": new,
                     **({"pid": old_peer.get("pid")} if old_peer else {})})
    elif last.get("reason") != "continued" or last.get("to") != new:
        return []   # retired otherwise since: nothing goes on in `new`
    other = threads.thread_of(new)
    if other is not None and other["thread"] == thread["thread"]:
        other = None
    if other is not None and not threads.absorbable(other, new):
        refuse_hand_off(old, new, other)
        return []
    fields, seat = {"current": new}, None
    # What `new` cannot say for itself until it runs (a job the engine named and never started has no transcript
    # and no process) it takes from the `joined` of the session it continues: its directory, and who joined it.
    before = next((e for e in reversed(own) if e["kind"] == "joined"), {})
    by = str(before.get("by") or "")
    if thread["opened"] == "spawned":
        seat = reload_seat(thread["thread"])
        if seat is None:
            return []
        joined = joined_fields(seat["alias"], "seat", seat_cwd(seat, fresh=True), seat["worktree"], seat["role"],
                               seat["seat_id"], by, "seat", session=new)
        fields.update(short=str((agent_row(session_id=new) or {}).get("id") or ""), updated=now())
    else:
        peer = session_running(new) or {}
        alias, source = held_alias(*own_alias(own, old), peer, new, shadowing(project, new))
        joined = joined_fields(alias or new[:8], source or "derived",
                               launch_cwd(new, fallback=str(peer.get("cwd") or before.get("cwd") or ""), fresh=True),
                               by=by, session_kind=str(peer.get("kind") or "bg"), session=new)
    other_id = other["thread"] if other is not None else None

    def guard(t):
        if t["current"] != old or threads.record_ended(t):
            return False
        if not still_in_effect(project, old, last) or not membership_here(project, old):
            return False   # retired, joined or moved since it was read: that decision stands
        return other_id is None or threads.absorbable(threads.get(other_id), new)

    try:
        locks = lock_seat(seat, refusal=ResumeRefused) if seat is not None else []
    except ResumeRefused:
        return []   # another command holds the seat: nothing moved, and the next reconciliation tries it whole
    try:
        out = thread_transition(project, thread["thread"], "absorb" if other_id else "advance",
                                owed + [{"kind": "joined", "session": new, **joined}], fields=fields, guard=guard,
                                other=other_id, carry=[old, new], absorbs=True, lock_until=_RECORD_DEADLINE,
                                # What is owed to the session left (held for it included) is settled as it goes
                                # on in the job, which reads it through the carried cursor: a later reuse of the
                                # id, as a thread of its own, is pushed none of it.
                                settle=old)
    except LockBusy:
        return []
    finally:
        unlock(locks)
    held = threads.get(other_id) if other_id else None
    if other_id and (threads.get(thread["thread"]) or {}).get("current") == old \
            and not threads.absorbable(held, new):
        refuse_hand_off(old, new, held or other)   # the job's record changed before it was held: undone
    return out


def refuse_hand_off(old, new, other):
    """An absorption whose guards failed (hand_off): said once in daemon.log,
    and remembered so the caller reads `old` as a session whose process is
    gone, the two left two threads."""
    if (old, new) in _HANDOFF_REFUSED:
        return
    _HANDOFF_REFUSED.add((old, new))
    try:   # once on this machine, not once per process: a marker per pair, made by whichever process says it first
        d = os.path.join(root(), "daemon", "handoff-refused")
        os.makedirs(d, mode=0o700, exist_ok=True)
        os.close(os.open(os.path.join(d, "%s.%s" % (old, new)), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        return
    except OSError:
        pass
    why = ("it has ended" if threads_module().record_ended(other) else
           "its entry is open" if other.get("pending") else "it holds another session")
    try:
        daemon_log("hand-off: %s continues in %s, whose own thread record cannot be absorbed (%s): not recorded, "
                   "nothing of %s's reach carried; they stay two threads" % (old[:8], new[:8], why, old[:8]))
    except OSError:
        pass


def carry_hand_off(project, old, new):
    """The steps of a hand-off that come before its events (Interfaces §6,
    step 2), each safe to repeat: `new`'s record takes `old`'s provenance
    (ensure_record(…, former=[old]): the one call that carries reach; a
    record already final stays), its chat cursor merged into `new`'s, and
    `old`'s join override carried where `new` has none. Whether the cursor
    and the override were carried (a failed write is a warning, and False:
    a journaled hand-off then stays open, carry_hand_offs)."""
    ensure_record(project, new, former=[old])
    ok = True
    try:
        carried = cursor_load(project, old)
        mine = writer_id(old)
        for e in _own_events(project, old):
            if writer_base(e["writer"]) == mine:   # its plain writer and its streams (P5 O18 D6)
                carried[e["writer"]] = max(carried.get(e["writer"], 0), e["seq"])
        if carried:
            cursor_save(project, new, carried)
    except OSError as e:
        warn("carrying %s's chat cursor to %s failed: %s" % (old[:8], new[:8], e))
        ok = False
    try:
        if override_of(old) and not override_of(new):
            write_override(new, override_of(old))
    except OSError as e:
        warn("carrying %s's join override to %s failed: %s" % (old[:8], new[:8], e))
        ok = False
    return ok


def carry_hand_offs(project, entry):
    """sminos_threads.finish's step for an entry that carries a hand-off's
    reach (`carry`): the hand-off's steps, so a replay carries what a
    process that died after its record's write did not; whether all of it
    is durable (the cursor and the override written, and the provenance
    carried), without which nothing of the entry is appended. An entry whose
    `carry` does not read carries nothing durable: it stays open."""
    pair = entry.get("carry")
    if not (isinstance(pair, list) and len(pair) == 2 and all(UUID_RE.fullmatch(str(x)) for x in pair)):
        return False
    old, new = pair
    return carry_hand_off(project, old, new) and carried(project, old, new)


def carried(project, old, new):
    """Whether `new`'s record holds what a hand-off from `old` carries: the
    provenance ensure_record(…, former=[old]) would take (lineage_provenance)
    no stronger than the record `new` has. A predecessor's record that
    cannot be read is not carried yet (what it holds is unknown); one with
    nothing to carry (no record, no publication) is."""
    records = records_module()
    if records.unreadable(old) or records.unreadable(new):
        return False
    prov = lineage_provenance(project, new, None, [old])
    return prov is None or not records.stronger(prov, records.read(new))


def hand_off_untracked(project, old, new, old_peer=None):
    """A hand-off of a session that is no thread (lane B), as before threads:
    its reach, cursor and override carried (carry_hand_off), a seat that
    held `old` moved to `new`, `old` retired, reason `continued`, naming
    `new` (and the process it saw), and `new`, if it already joined under a
    name the harness made up, renamed to the alias `old` held. Ordered so
    one cut short is finished by the next: the retirement comes only after
    the seat moved, and the rename runs while `old` stands retired to
    `new`, whoever retired it."""
    def still_joined(evs):
        return latest_membership(evs) == "joined"

    carry_hand_off(project, old, new)
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
    last = threads_module().in_effect(theirs)
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
    """Move a seat that is no thread (one holding a lane B session) from
    `old` to the session it continues in, under the seat's lock: the same
    occupant goes on, so nothing else of the record changes. A seat that no longer holds `old` is left as it is; a seat
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
    charge names design). `unlisted`: the highest policyRev of a transition
    notice of its own writers the log holds (P5 O18 D6; 0 for none), and
    `policyRev` the highest its own `joined` and `state` snapshots carry (0
    for none, or none carrying one): an arriving event carries what its
    endpoint signed, this machine's own carry neither (unlisted_here).

    `episodes` (X2, Interfaces §4): its stretches under one thread, each
    `[start ts, mark, latest joined, first by]`, a new one beginning at a
    `joined` stamped otherwise than the one before, or after its own
    retirement `continued` or `replaced` (it left its thread for another
    session); the mark is the episode's stamp, else, for naming alone, the
    seat its unstamped `joined` names, else "". An unstamped `joined` starts
    none: it is the episode's it falls in. `named`: (alias, ts, its stamp)
    of each own `joined` and `renamed` carrying an alias, and `statuses`
    every status line, for a row read per episode (_member). `marked`: its
    latest own `renamed`, `state` and `titled` under each stamp ("" for
    none), which a row read per episode takes from the episodes that count
    (_episode_view), as it does its alias and status. `stated`: its
    statement in effect (CH1's C2, sminos_threads.Fold.state), None for
    none."""
    info = {}
    fold = threads_module().Fold()   # the membership in effect: `latest` and `joined` are its

    def row(sid):
        return info.setdefault(sid, {"latest": None, "joined": None, "by": "", "renamed": None, "state": None,
                                     "titled": None, "in_charge": [], "status": [], "to": "", "continues": "",
                                     "aliases": {}, "owned": None, "unlisted": 0, "policyRev": 0,
                                     "episodes": [], "named": [], "marked": {}, "stated": None})

    for e in events:
        sid, kind = e.get("session"), e["kind"]
        if kind not in LIFECYCLE or not isinstance(sid, str) or not sid:
            continue
        own = writer_session(e["writer"]) == sid
        if kind == "channels":
            if own:   # another writer's states nothing, and makes no row
                fold.state(sid, e)
                row(sid)["stated"] = fold.stated.get(sid)
            continue
        r = row(sid)
        rev = e.get("policyRev") if type(e.get("policyRev")) is int else 0
        if kind == "unlisted":
            if own and rev >= 1:
                r["unlisted"] = max(r["unlisted"], rev)
            continue
        if kind in MEMBERSHIP or kind in ("renamed", "state", "titled"):
            if not own or (kind in MEMBERSHIP and fold.add(sid, e) is None):
                continue
            if kind in ("joined", "state"):
                r["policyRev"] = max(r["policyRev"], rev)
            if kind in ("joined", "renamed") and e.get("alias"):
                held, ts = str(e["alias"]), str(e.get("ts") or "")
                r["aliases"][held] = max(r["aliases"].get(held, ""), ts)
                r["named"].append((held, ts, e["thread"] if isinstance(e.get("thread"), str) else ""))
            if kind in MEMBERSHIP:
                before = r["latest"]
                r["latest"], r["joined"] = fold.effect[sid], fold.joined.get(sid)
                r["stated"] = None   # a membership event in effect ends the statement (Fold.add)
                if kind == "joined":
                    stamp = e["thread"] if isinstance(e.get("thread"), str) else ""
                    mark, eps = stamp or str(e.get("seat") or ""), r["episodes"]
                    if not eps or (stamp and eps[-1][1] and stamp != eps[-1][1]) or (
                            before is not None and before["kind"] == "retired"
                            and before.get("reason") in ("continued", "replaced")):
                        eps.append([str(e.get("ts") or ""), mark, e, str(e.get("by") or "")])
                    else:
                        ep = eps[-1]
                        if stamp or (mark and not ep[1]):
                            ep[1] = mark
                        ep[2] = e
                        if not ep[3] and e.get("by"):
                            ep[3] = str(e["by"])
                    r["to"] = ""
                    if not r["by"] and e.get("by"):
                        r["by"] = str(e["by"])
                    if publishes(e):
                        r["owned"] = e
                elif e.get("reason") == "continued" and UUID_RE.fullmatch(str(e.get("to") or "")):
                    r["to"] = str(e["to"])
            else:
                r[kind] = e
                stamp = e["thread"] if isinstance(e.get("thread"), str) else ""
                r["marked"].setdefault(stamp, {})[kind] = e
        elif kind == "in-charge":
            r["in_charge"].append(e)
        else:
            r["status"].append(e)
    for sid, r in list(info.items()):
        if r["to"] and r["to"] != sid:
            row(r["to"])["continues"] = sid
    for r in info.values():
        if len(r["episodes"]) > 1:
            r["statuses"] = r["status"]   # read per episode (_member)
        r["status"] = latest_across_writers(r["status"])
    return info


def episode_mark(r, e):
    """The thread an event of a session belongs to, from its _projection row
    `r` (Interfaces §4): its own stamp, else the mark of the episode its
    time falls in (the first episode for one before any); "" for none."""
    stamp = e.get("thread")
    if isinstance(stamp, str) and stamp:
        return stamp
    eps = r["episodes"]
    if not eps:
        return ""
    ts = str(e.get("ts") or "")
    mark = eps[0][1]
    for ep in eps[1:]:
        if ep[0] > ts:
            break
        mark = ep[1]
    return mark


def row_thread(r):
    """The thread a _projection row's session is in, for naming and for its
    row (§4): its latest episode's mark — its latest joined's stamp, else
    the seat an unstamped one names; "" for none."""
    eps = (r or {}).get("episodes") or ()
    return eps[-1][1] if eps else ""


_THREAD_INDEX = [None, None]   # [a projection (info) asked about, {thread: {session: its latest start there}}]


def thread_sessions(info, thread, sid, former):
    """The other sessions of `thread` in a projection, newest first: those
    with an episode marked with it (a refill's predecessors, a session that
    left it and runs on under another), less `sid` and its continuation
    chain (`former`), and less any the log shows unlisted to this reader
    (unlisted_here): a withdrawal hides its history from the thread's other
    rows too. Indexed once per projection."""
    if not thread:
        return ()
    if _THREAD_INDEX[0] is not info:
        index = {}
        for x, r in info.items():
            if unlisted_here(x, r):
                continue
            for ep in r["episodes"]:
                if ep[1]:
                    seen = index.setdefault(ep[1], {})
                    seen[x] = max(seen.get(x, ""), ep[0])
        _THREAD_INDEX[:] = [info, index]
    seen = _THREAD_INDEX[1].get(thread) or {}
    skip = {sid, *former}
    return tuple(x for x, _ in sorted(((x, at) for x, at in seen.items() if x not in skip),
                                      key=lambda xa: (xa[1], xa[0]), reverse=True))


def _episode_view(sid, r, thread, chain):
    """What a _projection row `r` says of session `sid` within the episodes
    marked `thread` (§4): its in-charge lines, status lines, worktree, `by`,
    the aliases it held, its latest name (`renamed`, else the `joined`
    there), its published state and title, as _member reads a row. For a
    session of the continuation chain (`chain`) an episode with no mark
    (from before threads) counts too; another session of the thread counts
    only where it was in the thread. A row whose episodes all count is
    itself."""
    eps = r["episodes"]

    def counts(mark):
        return mark == thread or (chain and not mark)

    if len(eps) <= 1 and counts(eps[0][1] if eps else ""):
        return r   # one episode, and it counts: a thread is joined anew whenever it changes, so all of it does
    kept = [ep for ep in eps if counts(ep[1])]
    statuses = [e for e in r.get("statuses") or ([r["status"]] if r["status"] else []) if counts(episode_mark(r, e))]
    aliases = {}
    for alias, ts, stamp in r["named"]:
        if counts(episode_mark(r, {"thread": stamp, "ts": ts})):
            aliases[alias] = max(aliases.get(alias, ""), ts)

    def latest(kind):
        held = [m[kind] for m in r["marked"].values() if kind in m and counts(episode_mark(r, m[kind]))]
        return max(held, key=lambda e: str(e.get("ts") or "")) if held else None

    return {**r, "in_charge": [e for e in r["in_charge"] if counts(episode_mark(r, e))],
            "renamed": latest("renamed"), "state": latest("state"), "titled": latest("titled"),
            "status": latest_across_writers(statuses), "aliases": aliases,
            "joined": kept[-1][2] if kept else None, "by": next((ep[3] for ep in kept if ep[3]), ""),
            "owned": r["owned"] if chain else None}


def unlisted_here(sid, r):
    """Whether the log shows the session unlisted to this machine's reader
    (P5 O18 D6): it holds a notice of the session's own writers — the hub
    serves one only to the members its change withdrew — at a policyRev no
    snapshot of the session it holds reaches. Then the session is none of
    the projection's members, so no listing, search, tag or broadcast
    reaches it. Never a session of this machine's: its record is here."""
    return r["unlisted"] > r["policyRev"] and not audience_module().is_local(sid)


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
    (§5) the latest of its `set` and `derived` in-charge lines — a set line
    until a line derived after it (a compaction derives over a set line:
    derive_refusal), "after" as latest_across_writers orders them —, the
    other of the two when the latest is written empty, the name the human
    gave it, and its title — read from its transcript on this machine, else the one its machine `published` (`titled`); ("", "", "")
    when none is. `ts` is the line's event's, "" for a line no event wrote (a
    name, a title). A set or derived line written empty is no line. `events`
    is the log, or any part of it holding the member's in-charge events, each
    writer's in seq order. With title=False the transcript is not read (the
    daemon's tick has no use for the line). A line set for a session the
    member continues (`former`) is the member's."""
    sessions = (member.session,) + tuple(member.former) + tuple(member.thread_sessions)
    mine = [e for e in events if e["kind"] == "in-charge" and e.get("session") in sessions]
    lines = {}
    for source in ("set", "derived"):
        e = latest_across_writers([x for x in mine if x.get("source") == source])
        lines[source] = (str(e.get("text") or "").strip(), str(e.get("ts") or "")) if e else ("", "")
    # Which source is the later decided by the one latest event of both: seq
    # within a writer, ts only between writers (a session's charge and its
    # derive share its file, where a clock step or a ts tie must not decide).
    latest = latest_across_writers([x for x in mine if x.get("source") in ("set", "derived")])
    order = ("derived", "set") if latest and latest.get("source") == "derived" else ("set", "derived")
    for source in order + ("name", "title"):
        ts = ""
        if source == "name":
            line = member.alias if member.name_source == "user" else ""
        elif source == "title":
            if member.local:
                line = transcript_title(member.session) if title and member.session else ""
            else:
                line = published
        else:
            line, ts = lines[source]
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
    thread_mark = row_thread(r)
    others = thread_sessions(info, thread_mark, sid, former)
    j = (r or {}).get("joined") or {}
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
    # A thread's row reads the episodes of its id (§4): of its session and its
    # chain (theirs from before threads too), and of its other sessions.
    named, own = info, r
    if thread_mark and (others or any(len(x["episodes"]) > 1 for x in chain)):
        parts = [(x, info[x], True) for x in (sid,) + former if info.get(x)] + \
            [(x, info[x], False) for x in others if info.get(x)]
        chain = [_episode_view(x, xr, thread_mark, mine) for x, xr, mine in parts]
        views = {x: v for (x, _, _), v in zip(parts, chain)}
        named, own = {x: views.get(x, info[x]) for x in (sid,) + former if x in info}, views.get(sid, r)
    if seat:
        alias, name_source = seat["alias"], "seat"
    else:
        alias, name_source = held_alias(*logged_alias(sid, named), peer, sid, shadowed)
    in_charge = sorted((e for x in chain for e in x["in_charge"]), key=lambda e: (e["writer"], e["seq"]))
    published = {}
    gone_machine = not local and machine_retired(machine)
    if not local:
        published = (own or {}).get("state") or {}
        state_word, age = str(published.get("state") or ""), (ts_age(published["ts"]) if published else None)
        active = age
        # A machine the org retired (a deleted VM) publishes nothing more,
        # and its last word was never taken back: its sessions are gone.
        if gone_machine:
            state_word = "gone"
    elif seat:
        state_word = seat_state(seat, rec)
    elif rec:
        state_word = peer_state(rec)
    else:
        # A thread its human opened that no process holds is stopped by its record, transcript or none.
        state_word = "stopped" if threads_module().stopped_human(sid) or transcript_path(sid) else "gone"
    if rec and isinstance(rec.get("updatedAt"), (int, float)) and not isinstance(rec["updatedAt"], bool):
        active = max(0.0, time.time() - rec["updatedAt"] / 1000.0)
    if seat:
        kind = "seat"
    elif rec and rec.get("kind"):
        kind = str(rec["kind"])
    else:
        kind = str(j.get("session_kind") or "")
    cwd = str(j.get("cwd") or "") or (seat or {}).get("cwd") or str((rec or {}).get("cwd") or "")
    # Read where it works, but where this process may not look: as its join recorded them.
    repo, branch = repo_branch(cwd) if local and not read_refused(cwd) else \
        (str(j.get("repo") or ""), str(j.get("branch") or ""))
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
    # Owners are read along the continuation chain alone, never a thread's other sessions (§4).
    owned = next((x["owned"] for x in chain[:1 + len(former)] if x.get("owned")), None) or {}
    owners = tuple(record["owners"] if record else owners_of(owned) or ())
    origin = record["origin"] if record else (owned.get("origin") if isinstance(owned.get("origin"), dict) else None)
    thread = str(j.get("thread") or "") if isinstance(j.get("thread"), str) else ""
    latest = (r or {}).get("latest") or {}
    # A machine the org retired governs over an end its log shows: nothing there returns it.
    ended = latest.get("kind") == "retired" and latest.get("reason") in END_REASONS and not gone_machine
    end = "machine" if gone_machine else str(latest["reason"]) if ended else ""
    if ended and seat:
        state_word = "retired"   # the end in effect (the fold) governs, whatever the seat's own status says
    m = Member(
        session=sid, short=sid[:8], alias=alias or sid[:8], name_source=name_source,
        machine=host_name() if local else machine, local=local, state=state_word, state_age=age,
        charge="", charge_source="",
        status=str(status.get("text") or "") if status else (seat["now"] if seat else ""),
        by=next((x["by"] for x in chain if x["by"]), ""), worktree=seat["worktree"] if seat else worktree,
        seat=seat, former=former, former_aliases=tuple(sorted(held.items())), kind=kind, cwd=cwd, repo=repo, branch=branch, active_age=active,
        title="" if local else published_title(own), owners=owners, origin=origin, record=record,
        thread=thread, opened=("spawned" if thread == str(j.get("seat") or "") else "human") if thread else "",
        thread_sessions=others,
        wake=str(published.get("wake") or "") if not local and not gone_machine and state_word in HELD_STATES
        else "",
        why=str(published.get("why") or "") if not local and not gone_machine and state_word in HELD_STATES else "",
        end=end, end_by=str(latest.get("by") or "") if ended else "", named=thread_mark,
        channels=threads_module().stated_set(r["stated"]) if r and r.get("stated") else ())   # no call for none
    charge, source, ts = charge_of(m, in_charge, title, published_title(own))
    return m._replace(charge=charge, charge_source=source, charge_age=ts_age(ts) if ts else None)


def vacant_member(s):
    """The row of a seat that holds no session."""
    repo, branch = repo_branch(s["cwd"])
    return Member(session="", short="", alias=s["alias"], name_source="seat", machine=host_name(), local=True,
                  state=state(s), state_age=None, charge="", charge_source="", status=s["now"], by="",
                  worktree=s["worktree"], seat=s, kind="seat", cwd=s["cwd"], repo=repo, branch=branch,
                  thread=s["seat_id"], opened="spawned")


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
    ended: "Rows" = ()    # the rows of the project's ended threads no seat here stands for (ended_rows), newest
                          # end first, built when first read


class Rows:
    """A view's rows built from `make()` when first read (View.ended: the
    daemon's tick reads a view every few seconds and never these)."""
    __slots__ = ("_make", "_rows")

    def __init__(self, make):
        self._make, self._rows = make, None

    def _all(self):
        if self._rows is None:
            self._rows = self._make()
        return self._rows

    def __iter__(self):
        return iter(self._all())

    def __len__(self):
        return len(self._all())

    def __getitem__(self, i):
        return self._all()[i]


def ended_rows(info, bound, held, titles=True):
    """The rows of a projection's ended threads (T1's M4): each session
    whose membership in effect is a `retired` of an END_REASONS reason,
    whoever wrote it (has_ended), as a row whose word is `retired` and whose
    `end` says why — read from the log alone, on its own machine as on any
    other. Not a session a seat of this machine holds (`bound`: its seat's
    row stands for it, retired), nor one the log shows unlisted to this
    reader, nor a second row of a thread a row already holds (`held`, the
    thread ids of the view's other rows: one row per thread, §4). Newest
    end first; no horizon (the composite: Deferred)."""
    found = [(sid, r) for sid, r in info.items()
             if r["latest"] and r["latest"]["kind"] == "retired" and r["latest"].get("reason") in END_REASONS
             and r["joined"] and sid not in bound and not unlisted_here(sid, r)]
    found.sort(key=lambda x: (str(x[1]["latest"].get("ts") or ""), x[0]), reverse=True)
    held, out = set(held), []
    for sid, r in found:
        thread = row_thread(r)
        if thread and thread in held:
            continue
        if thread:
            held.add(thread)
        m = _member(sid, r, None, None, False, titles, info)
        out.append(m._replace(state="gone" if m.end == "machine" else "retired"))
    return out


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
    read, events = _store_whole(project, "log", shared=True)
    channel = is_channel_id(project.id)
    appended = (_reconcile_channel(project, events, by_session) if channel
                else _reconcile(project, events, local, by_session, all_seats))
    # Read again: what anyone appended since the read above is in the view — this reconciliation's own
    # events, and another process's join (or retire, rename, hand-off) that its guards then declined to
    # repeat (#581). The same merged list when no file moved. An append that waits for its writer's head
    # is in no log file yet: it is added as written.
    sig, events = _store_whole(project, "log", shared=True)
    if appended or sig != read:
        # The seats as that log has them: a hand-off, this process's or another's, may have moved a seat to
        # the session it continues in.
        all_seats = seats()
        by_session = seats_by_session(project, all_seats)
        local = _local_sessions(project, all_seats)
    queued = [e for e in appended if e.get("seq") is None]
    if queued:
        events = events + queued
    if channel:
        # A channel's view has no members, by construction and whatever its log holds (CH1, C1): an older
        # copy's `joined` there, undone above while a process or a seat holds its session, is no member
        # before or after, so nothing reads one to publish, deliver or address under a channel id. Its
        # roster is a read of its own.
        view = View([], [], [], events, {}, len(appended))
        if titles:
            _VIEWS[project.id] = view
        return view
    # The projection of a log no file of which moved is the one made last:
    # a read-only View, as the generation's cache (_VIEWS) shares it too.
    held = None if queued else _PROJECTED.get(project.id)
    if held is not None and held[0] == sig:
        info = held[1]
    else:
        info = _projection(events)
        if not queued:
            _PROJECTED[project.id] = (sig, info)
    internal = internal_pids()
    forks = {r.get("sessionId") for r in peer_records() if str(r.get("pid")) in internal}
    joined = [(sid, r) for sid, r in info.items()
              if r["latest"] and r["latest"]["kind"] == "joined" and sid not in forks and not unlisted_here(sid, r)]
    joined.sort(key=lambda x: (x[1]["joined"]["ts"], x[0]), reverse=True)
    # One row per thread (§4): a read that spans a transition (each writer file is read in turn, and a
    # retirement can be owed still) or a remote log behind holds two of its sessions, or a seat whose
    # thread a member row stands for; the current one stays, the others are its `thread_sessions`.
    out = thread_current([_member(sid, r, by_session.get(sid), local.get(sid, {}).get("peer"), sid in local, titles,
                                  info, shadowing(project, sid, info, all_seats))
                          for sid, r in joined], lambda m: m.thread or row_thread(info.get(m.session)))
    sessions = {m.session for m in out}
    held = {m.thread or row_thread(info.get(m.session)) for m in out} - {""}
    rest = sorted((s for s, pid in _seat_pids(all_seats) if (not s["current"] or s["current"] not in sessions)
                   and pid == project.id and s["seat_id"] not in held), key=lambda s: s["updated"], reverse=True)
    rows = [_member(s["current"], info.get(s["current"]), s, None, True, titles, info) if s["current"] else
            vacant_member(s) for s in rest]
    # Seat-less sessions the log holds as retired, by alias: what a tag that
    # names one is told. One that continues in another session is not: its
    # name is the continuation's now. One that moved names where it went.
    retired = [(str((r["renamed"] or r["joined"]).get("alias") or sid[:8]), sid[:8], str(r["latest"].get("reason") or ""),
                str(r["latest"].get("project") or ""))
               for sid, r in info.items()
               if r["latest"] and r["latest"]["kind"] == "retired" and r["joined"] and sid not in by_session
               and r["latest"].get("reason") != "continued" and not unlisted_here(sid, r)]
    held_rows = held | {s["seat_id"] for s in rest}
    view = View(out, rows, retired, events, info, len(appended),
                Rows(lambda: ended_rows(info, by_session, held_rows, titles)))
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
                          seats_by_session(project, all_seats), all_seats))


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


def _owed_kept(events, to, session, record):
    """_owed of a member's share (`to`, addressees of the merged log
    `events`), kept beside that log (log_memo) while the member's delivery
    record reads the same: a function of the two alone, which the words and
    reach passes ask of every member every WORDS_EVERY. Read it, never
    change it."""
    kept = log_memo(events, "owed", lambda _events: {})
    held = kept.get(session)
    if held is None or held[0] != record:
        held = kept[session] = (record, _owed(to.get(session, ()), session, record))
    return held[1]


def addressees(events):
    """{session: the events addressed to it, in the log's order}: the part of
    the log _owed reads for each session, read once for all of them (the
    daemon asks for every member of every project each tick), and once for
    a log that has not moved (log_memo; read it, never change it)."""
    return log_memo(events, "addressees", _addressees)


def _addressees(events):
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


def push_words(project, session, e, gate, owed):
    """The verdict a push of `e` is made under: a held receipt's for its
    retry (the verdict taken with it), else the words gate's (WordsGate.words)."""
    if owed == HOLDER_RETRY:
        return holder_module().words_of(project.id, session, e)
    return gate.words(e)


# What holds a delivery to a thread (T2's §4), each the outcome `held:<why>`: owed, no attempt counted
# (holder_waiting), nothing pushed, and the event marked held for its thread (held_decided). The reasons a thread
# is not woken (sminos_wake.REASONS), a wake that failed and is not due, and what passes on its own: a process
# started whose inbox does not answer yet, another wake in flight, the sweep's moment, an open entry, a record or
# lane that cannot be read, the seat's lifecycle lock held by a verb.
HOLD_PASSING = ("starting", "in flight", "sweep", "pending", "unknown", "busy")
HOLDS = ("config", "transcript", "cwd", "protected", "mode", "failed") + HOLD_PASSING


def hold_outcome(why, thread=None):
    """`held:<why>`, carrying the thread the hold was decided for (`thread`,
    else a Hold's own) to the mark held_decided writes."""
    return threads_module().Hold("held:%s" % why, thread or getattr(why, "thread", None))


def hold_why(outcome):
    """The thread's hold an outcome is (`held:<why>` of HOLDS), else ""."""
    why = outcome[len("held:"):] if isinstance(outcome, str) and outcome.startswith("held:") else ""
    return why if why in HOLDS else ""


def hold_for(session):
    """Whether this machine holds delivery for the session, as a view or a
    pass reads it (sminos_threads.hold_of, through its index): "" when it
    delivers to it or would wake it now, else why it holds (HOLDS: a reason
    the thread is not woken, or `failed` while its wake is not due). Never
    the last word before a push, an ask or a counted attempt: that is
    hold_now's."""
    return threads_module().hold_of(session)


def hold_now(session):
    """The fresh hold (sminos_threads.hold_now): the engine's records read
    afresh for the process's session id, and the record thread_of reads.
    What every push, ask and counted attempt asks last, under the delivery
    lock where one is held."""
    return threads_module().hold_now(session)


def has_ended(member):
    """Whether a member's thread has ended (T1's M4, Interfaces §8): its
    membership in effect is a `retired` with reason `retire` or `ended`,
    whoever wrote it, or its machine is retired in the org's state
    (Member.end). Read from the log and the org's state alone, on any
    machine: no record is needed."""
    return bool(member.end)


def state_wake(session, state):
    """(wake, why) a `state` event of a thread of this machine carries (X3):
    a `stopped` one's wake_published; a `gone` one's only while it is the
    current session of a thread that has not ended and is held (a spawned
    thread whose conversation is not here: `transcript`), the state word
    itself unchanged (X5); else (None, "")."""
    if state == "stopped":
        return wake_published(session)
    if state == "gone" and threads_module().current_record(session) is not None:
        wake, why = wake_published(session)
        if wake == "held" and why:
            return wake, why
    return None, ""


def wake_published(session):
    """(wake, why) of a stopped thread of this machine as its `state`
    publishes them (X3, T2's §5): ("held", why) or ("woken", ""). `why` is
    `read-only` on a machine whose policy is read-only, whatever else holds
    (what a sender on another machine must be told: what it sends is
    refused here); else the reason the thread is not woken
    (sminos_wake.published_reason: the last turn read whole where the tail
    did not say); else `failed` while its record counts a failed wake,
    due or not, so that what is published does not turn with the
    schedule."""
    if sibling_module("sminos_policy").read_only():
        return "held", "read-only"
    return wake_here(session)


def wake_here(session):
    """wake_published but for `read-only`, which refuses only what comes
    from another machine: what a sender on this machine meets."""
    t = threads_module().current_record(session)
    if t is None:
        return ("held", "") if hold_for(session) else ("woken", "")
    if session_running(session):
        return "woken", ""   # a process holds it: nothing is held for it
    why = wake_module().published_reason(t, session)
    if not why:
        failed = threads_module().waking(t, session).get("failed")
        why = "failed" if type(failed) is int and failed > 0 else ""
    return ("held", why) if why else ("woken", "")


def wake_of(member):
    """Whether a stopped member's machine wakes it (X3, Interfaces §5):
    "ended" for one whose thread has ended (has_ended); else "woken" or
    "held", on this machine as it publishes it (wake_published), elsewhere
    from its latest `state` (Member.wake); None where its machine published
    none (an older sminos there: the sender is told what it is told
    today)."""
    if has_ended(member):
        return "ended"
    if member.local:
        return wake_published(member.session)[0]
    return member.wake or None


def why_of(member):
    """Why a stopped member's machine holds it (X3's `why`), or "": on this
    machine as it publishes it, elsewhere from its latest `state`
    (Member.why: "" for a `held` written before T2, which is 1.51's)."""
    if has_ended(member):
        return ""
    if member.local:
        return wake_published(member.session)[1]
    return member.why if member.wake == "held" else ""


def held_send(delivery, alias, why=None, thread=None):
    """A send to a held session, recorded (its SendDelivery, or the
    WaitingSend of an append that waits for its writer's head, which has no
    seq yet and is said as it is): released, pushed nothing, the sender told
    why (`why`, a PushHeld that is no hold of the thread's, said instead),
    and the daemon nudged. Under the delivery lock the send holds, the hold
    is read afresh and noted for the event (delivered_held), for `thread`:
    the thread the recipient was chosen as at the lookup (held_record); the
    session's thread now when none is given."""
    if delivery is None:
        return
    if isinstance(delivery, WaitingSend):
        delivery.recorded_owed(alias)
        return
    said = "not pushed now: %s" % why
    if why is None or getattr(why, "hold", ""):
        seq = delivery.event["seq"]
        if seq <= _delivery(delivered_load(delivery.project, delivery.session), delivery.writer)["settled"]:
            said = "settled by a delivery pass between its record and this check"
        elif (hold := hold_now(delivery.session)):
            chosen = threads_module().stamp(delivery.session) if thread is None else thread
            delivered_held(delivery.project, delivery.session, delivery.writer, seq, chosen)
            said = held_line(hold, session=delivery.session) if threads_module().stamp(delivery.session) == chosen \
                else stale_line()
        else:
            said = "its session runs again, and the daemon delivers it to its process"
    delivery.release()
    print("recorded %s for %s: %s" % (event_ref(delivery.event), alias, said), flush=True)
    nudge_daemon()


def woken_line(machine):
    """What a sender is told of a message to a stopped member another
    machine published `woken` for (X3): that machine resumes it with it."""
    return "recorded (on %s): the session is stopped, and its machine wakes it with this" % machine


def remote_line(member):
    """The sender's line for a member of another machine by what that
    machine published of it (X3, T2's §5): held, and why (`read-only`: it
    refuses there what comes from elsewhere; a `held` with no `why`, or one
    this code does not know, 1.51's); woken; or None for nothing published
    (today's line, the caller's)."""
    wake = wake_of(member) if member.state in HELD_STATES else None
    if wake == "woken" and member.state == "stopped":
        return woken_line(member.machine)
    if wake != "held":
        return None
    why = why_of(member)
    if why == "read-only":
        return "recorded: %s admits nothing from another machine, and refuses it there" % member.machine
    return held_line(why, member.machine) if why in HOLD_WORDS else held_line_151(member.machine)


def held_line_151(machine=""):
    """1.51's line for a held session (a `held` with no `why`: a thread its
    human opened, before the wake shipped), `machine` the one it waits on."""
    return ("recorded and held%s: the session is stopped, and a session its human opened is not woken; it is pushed "
            "only if its human reopens the session before it ends (three days stopped, or a retire), else it stays in "
            "the log" % (" on %s" % machine if machine else ""))


# Why a thread is not woken, as a sender reads it (T2's §5).
HOLD_WORDS = {
    "config": "it runs under another config dir",
    "transcript": "no conversation of it is on that machine",
    "cwd": "its directory is gone",
    "protected": "its directory is in, or holds, a folder macOS protects, where a background launch would stop at "
                 "a prompt for its human",
    "mode": "a wake would run it in a mode that asks for approval",
    "failed": "waking it failed, and its machine tries again",
}
# `mode` on the thread's own machine when its ceiling, not the thread's own mode, is the cause (the plan's Decision
# Log, "The `mode` words"): the ceiling's value and whose setting it is, never how to raise it.
CEILING_WORDS = "this machine's ceiling (%s) would start it in a mode that asks for approval; the ceiling is its " \
                "owner's setting (sminos daemon policy shows it)"
PASSING_LINE = "recorded: its process is starting, and the daemon delivers it"   # a launch under way
# A record, a lane or a job list its machine could not read: no launch is under way, nothing is known to clear.
UNREAD_LINE = "recorded: its machine could not read the session's state just now, and the daemon delivers it when " \
              "it can"


def hold_words(why, session=""):
    """Why a thread is held, in §5's words (HOLD_WORDS), `session` a local
    thread's, for `mode`'s cause (sminos_wake.mode_case): the ceiling named
    when it, not the thread's own mode, is the cause."""
    words = HOLD_WORDS[why]
    if why == "mode" and session:
        t = threads_module().current_record(session, fresh=True)
        if t is not None and wake_module().mode_case(t, session) == "ceiling":
            words = CEILING_WORDS % sibling_module("sminos_policy").machine_policy()["ceiling"]
    return words


def held_line(why, machine="", session=""):
    """What a sender is told of a message held for a thread (T2's §5), `why`
    the hold (HOLDS), `machine` the one it waits on when that is another;
    `session`, a local thread's, for `mode`'s cause (hold_words). A hold
    that passes on its own is said as one the daemon delivers, in words
    true for it: a process starting only for a launch under way (`starting`,
    `in flight`)."""
    if why not in HOLD_WORDS:
        if why in ("starting", "in flight"):
            return PASSING_LINE
        if why == "unknown":
            return UNREAD_LINE
        return "recorded: %s, and the daemon delivers it" % wake_words(why)
    return ("recorded and held%s: the session is stopped and is not woken: %s; it is pushed when a process of it runs "
            "again before it ends (three days stopped, or a retire), else it stays in the log"
            % (" on %s" % machine if machine else "", hold_words(why, session)))


def verb_hold_words(why, session):
    """What a verb that records its message and starts nothing says last,
    before it exits 4 (T2's §6): why nothing was started, for a reason the
    thread is not woken or a failed wake; that nothing is waited for, for a
    hold that passes on its own."""
    if why in HOLD_WORDS:
        return "nothing was started: %s" % hold_words(why, session)
    return "not woken now: %s; the daemon delivers it, and no reply is waited for" % wake_words(why)


def held_now(session, due=False):
    """hold_now for a deliverer: `due` (a sender's own call) passes over a
    failed wake's schedule alone, never a reason the thread is not woken."""
    hold = hold_now(session)
    return "" if due and hold == "failed" else hold


def deliver_next(project, member, due=False):
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
    is revoked is marked, never pushed (delivered_revoke).

    A recipient process recorded `gate` (O12 M4b, sminos_holder_deliveries)
    settles nothing at the handoff: each event is pushed to its inbox with a
    receipt prepared first, and is HOLDER_AWAITING — owed, its writer
    stopped there, no attempt counted — until the bridge child records the
    receipt's admission; this pass or a later one then settles it like a
    push (holder_owed, before any other check). A receipt proves it was
    prepared, not handed off: one whose next step pushes (a retry, or a
    push that failed before) takes the revocation and read-only checks
    first, as a fresh push does; its words verdict was taken with it.

    Where the endpoint decides reach (P5 O18 D8) a push of a peer frame is
    the uplink's alone, on the endpoint's `deliver` (deliver_reach): such a
    writer stops at that event, a receipt's retry too, left owed and listed
    in `gated` like a person's words (ReachGate.needs: one owner's sessions
    of this machine excepted).

    A session this machine holds (sminos_threads.hold_of, T2's §4: a stopped
    thread of either kind that is not woken, or whose wake failed and is
    not due) is pushed nothing and asked nothing: where a writer's next step
    would be a push, or a question to the endpoint about one, its outcome is
    `held:<why>`, owed with no attempt counted and marked for its thread,
    and the writer stops there; what settles without a push still settles
    (a push noted, an admitted receipt, a revoked signer, the read-only
    refusal), and an event for the live alone (`wake`: an @all, a
    broadcast) settles `recorded`. A stopped thread that is not held is
    woken by the push of an addressed event (holder_push), at most once a
    call: a wake that leaves it held holds the rest of the call too.
    `due`: a sender's own call for the event it wrote (`say` with a tag,
    `send`), which a failed wake's schedule does not hold back (only
    `failed` is passed over); the daemon's passes and the uplink's
    deliveries follow the schedule."""
    session = member.session
    result = {"delivered": 0, "pending": 0, "outcomes": []}
    if not session:
        return result
    policy = sibling_module("sminos_policy")
    outcomes = sibling_module("sminos_outcomes")
    gate = WordsGate(project) if sibling_module("sminos_rl10").cut_over() else None
    reach = ReachGate(project) if gate is not None else None
    if gate is not None:
        result["gated"] = []
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        hold = None   # asked at the first push, afresh (hold_for)
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
                elif (owed := holder_owed(project, member, session, e, events, cursor)) not in (None, HOLDER_RETRY):
                    outcome = owed
                else:
                    held = gate.held(e, session) if gate is not None else None
                    if held == "revoked":
                        result["outcomes"].append((e, outcomes.REFUSED_REVOKED))
                        holder_module().settled(project.id, session, e)
                        continue
                    if held is not None:
                        result["pending"] += len(queue) - i
                        break
                    if outside and policy.read_only():
                        outcome = outcomes.READ_ONLY
                    elif stale_hold(record, session, e):
                        outcome = "recorded"   # held for a thread this session no longer fills: pushed to none
                    elif (unknown := held_unreadable(record, e)):
                        outcome = hold_outcome("unknown", unknown)   # no binding known: deferred, pushed nothing
                    elif hold or hold is None and (hold := held_now(session, due)):
                        # Held (T2's §4): pushed nothing and asked nothing. An event for the live alone (an @all,
                        # a broadcast) settles as for a stopped member; an addressed one stays owed.
                        outcome = "recorded" if e.get("wake") else hold_outcome(hold)
                    elif gate is not None and owed is None and gate.gated(e) or reach is not None \
                            and reach.needs(e, session, push_words(project, session, e, gate, owed)):
                        result["gated"].append(e)
                        result["pending"] += len(queue) - i
                        break
                    else:
                        outcome = holder_push(project, member, session, e, events, cursor,
                                              words=gate.words(e) if gate is not None else None,
                                              retry=owed is not None, due=due)
                        if gate is not None:
                            gate.said(e, outcome)
                        if hold_why(outcome):
                            # A wake that left it held: one attempt a call, the rest held for the same thread.
                            hold = threads_module().Hold(hold_why(outcome), getattr(outcome, "thread", None))
                outcome = held_decided(project, session, e, outcome)
                if hold_why(outcome):
                    # The same hold for the rest of the writer's queue, which this pass stops before: each
                    # addressed event of it decided held now, as the first is.
                    for later in queue[i + 1:]:
                        if not later.get("wake"):
                            delivered_held(project, session, writer, later["seq"], getattr(outcome, "thread", None))
                result["outcomes"].append((e, outcome))
                if not _conclude(project, member, session, e, outcome, outside):
                    result["pending"] += len(queue) - i
                    break
                holder_module().settled(project.id, session, e)
                if outcome in PUSHED:
                    result["delivered"] += 1
    return result


def _conclude(project, member, session, e, outcome, outside):
    """A push's outcome, settled as deliver_next settles it; whether it
    settled. A failure under DELIVERY_ATTEMPTS stays pending; one past it is
    given up with a daemon.log line and settled. An outside-origin event is
    settled only once its outcome is kept: else it stays pending and the
    next pass records it again — a push noted, so never made twice. The
    caller holds the session's delivery lock. A delivery whose receipt
    awaits its admission (O12 M4b), or whose process's mode cannot be read,
    stays owed with no attempt counted, as does one the reach gate holds
    (`held:reach`). A `refused-reach` is settled here alone: no outcome goes
    back (P5 O18 D3: a refusal here stays here)."""
    outcomes = sibling_module("sminos_outcomes")
    if holder_waiting(outcome):
        return False
    if outcome.startswith("failed"):
        if delivered_fail(project, session, e["writer"], e["seq"]) < DELIVERY_ATTEMPTS:
            return False
        daemon_log("gave up delivering %s (%s) to %s after %d attempts: %s" % (
            event_ref(e), project.name, session, DELIVERY_ATTEMPTS, outcome))
    if outside and outcome != outcomes.REFUSED_REACH and not outcomes.record(project, e, session, outcome, member):
        if outcome in PUSHED:
            delivered_pushed(project, session, e["writer"], e["seq"], outcome)
        return False
    delivered_settle(project, session, e["writer"], e["seq"])
    return True


# Receipts (O12 M4b, sminos_holder_deliveries): a log event handed to the
# inbox of a process recorded `gate` — a MAWS lane B observer's, whose
# bridge activated them before any legacy handoff — is settled at the first
# model request its bridge mod admits with the event's row in it, not at the
# handoff, and stays owed on the host's `stop`. The receipt is prepared
# before the inbox write, under the session's delivery lock; the process's
# mode is read from its record alone, never from whether its bridge answers.


def holder_module():
    return sibling_module("sminos_holder_deliveries")


def holder_waiting(outcome):
    """Whether a delivery's outcome leaves it owed with no attempt counted:
    its receipt awaits its admission (HOLDER_AWAITING), or its process's
    mode cannot be read (`held:`)."""
    return outcome == HOLDER_AWAITING or outcome.startswith("held:")


# What holder_owed answers for a held receipt whose next step is a push (a
# retry under its id, a push that failed before it reached, or a handoff to
# a process now `legacy`): the deliverer checks its policy, then pushes it
# through holder_push. Never an outcome.
HOLDER_RETRY = "holder-retry"


def holder_owed(project, member, session, e, events, cursor):
    """An event a receipt is held for, as far as it goes without a push:
    `sent` once admitted (admission alone settles it, whatever the policy
    says since: it reached the model); HOLDER_AWAITING while it waits (a
    hold, no live process, a process that may yet activate); `held:<why>`
    when its mode or receipt cannot be read; HOLDER_RETRY when its next step
    pushes (nothing written or chosen yet: the caller checks the revocation
    and read-only policy first, then holder_push(retry=True)). None when no
    receipt is held for it. Checked before any other rule. The caller holds
    the session's delivery lock."""
    hd = holder_module()
    if not hd.exists(project.id, session, e):
        return None
    peer = peer_for_session(session)
    plan = hd.plan(project.id, session, e, event_hash(e), peer.get("pid") if peer else None, existing_only=True,
                   prepare=False)
    if plan is None:
        return None
    if plan.kind in ("push", "legacy"):
        return HOLDER_RETRY
    if plan.kind == "awaiting" and peer is None and threads_module().lane_a(session) \
            and threads_module().current_record(session, fresh=True) is not None:
        # Handed to a process that is gone, never admitted, and its session now the current one of a lane A thread
        # (a lane B process's receipt, the session since reopened as lane A and closed): its next step is a push
        # to the process a wake starts, as for any event owed to a stopped thread (T1's limit: at most one copy
        # more), never a wait that keeps the thread from being woken.
        return HOLDER_RETRY
    return holder_carry(plan, project, member, session, e, events, cursor, peer)


def holder_push(project, member, session, e, events, cursor, words=None, retry=False, due=False):
    """push_event behind the receipt boundary: to a live process recorded
    `gate`, the event goes to its inbox with a receipt prepared first, and
    is HOLDER_AWAITING; a live process with no record is recorded `legacy`
    (unless it may yet activate: sminos_holder_deliveries.handoff) and the
    event pushed as today, as it is to a `legacy` one or to no live process.
    An addressed event to a session no process holds wakes its thread
    first (wake_member, T2's §4): once woken, the session is delivered to
    exactly as one found live, receipts included, its outcome a push's
    `woken` (`woken?`) for `sent` (`sent?`), and a seat's `turns` and
    `status` written for the push; a wake that does not make it live is
    the wake's outcome. `words` as push_event. `retry`: a held receipt
    holder_owed found due, its policy checked — carried on under its id.
    `due` as deliver_next's. The caller holds the session's delivery lock."""
    peer = peer_for_session(session)
    locks = None
    if peer is None and not e.get("wake"):
        # A retry wakes too: a receipt whose process is gone is pushed to the one the wake starts (holder_owed).
        got, locks = wake_member(project, member, session, e, words, due)
        if got and got != "woken":
            return got
    try:
        if locks is not None:
            peer = peer_for_session(session)   # under the locks the wake kept, let go below whatever comes
        if locks is not None and peer is None:
            return woken_unpushed(session)   # its inbox went between the wake's look and this one
        if not retry and (peer is None or peer.get("pid") is None
                          or (member.seat is None and latest_membership(_own_events(project, session)) == "retired")):
            outcome = push_event(project, member, session, e, events, cursor, words=words)
        else:
            # A retry's process may have ended since holder_owed saw it: no pid,
            # and plan() leaves the receipt owed for a later launch.
            plan = holder_module().plan(project.id, session, e, event_hash(e), peer.get("pid") if peer else None,
                                        words=words)
            outcome = holder_carry(plan, project, member, session, e, events, cursor, peer)
        if locks is not None:
            outcome = {"sent": "woken", "sent?": "woken?"}.get(outcome, outcome)
            if outcome == "recorded":
                # A push after a wake that handed nothing over (no process answered by then) settles nothing:
                # `recorded` is an end's or a stale hold's alone.
                outcome = woken_unpushed(session, outcome)
            t = threads_module().current_record(session, fresh=True)
            if t is not None and t["opened"] == "spawned" and (outcome in PUSHED or outcome == HOLDER_AWAITING):
                seat = reload_seat(t["thread"])
                if seat is not None:
                    seat_pushed(seat)
        return outcome
    finally:
        unlock(locks or [])


def woken_unpushed(session, outcome="recorded"):
    """What a push made after a wake (holder_push) that handed nothing over
    comes to: owed, `held:starting` for its thread, while the session is
    still the current one of a thread that has not ended (thread_owed's
    rule); else `outcome`, which an end or a stale hold settles."""
    t = threads_module().current_record(session, fresh=True)
    if t is None:
        return outcome
    return hold_outcome("starting", t["thread"])


_HOLDER_SAID = {}   # session → why its deliveries are held, as last said in daemon.log
class HandedOff(str):
    """HOLDER_AWAITING for a frame this push handed to a receipt's process
    (holder_carry): equal to it wherever an outcome is compared or kept, and
    `handed`, the evidence on the call's own outcome that a frame went
    (verb_delivered); a receipt still pending is the plain string."""
    handed = True

    def __new__(cls):
        return super().__new__(cls, HOLDER_AWAITING)


def holder_carry(plan, project, member, session, e, events, cursor, peer):
    """A receipt plan (sminos_holder_deliveries.plan) carried out; the
    delivery's outcome."""
    if plan.kind != "held":
        _HOLDER_SAID.pop(session, None)
    if plan.kind == "settle":
        return "sent"
    if plan.kind == "awaiting":
        return HOLDER_AWAITING
    if plan.kind == "held":
        if _HOLDER_SAID.get(session) != plan.why:
            _HOLDER_SAID[session] = plan.why
            daemon_log("delivery: what is owed to %s waits: %s" % (session, plan.why))
        return "held:%s" % plan.why
    if plan.kind == "legacy":
        return push_event(project, member, session, e, events, cursor, words=plan.words)
    text = frame_of(project, e, events, session, cursor) if plan.body == "full" else holder_wake(project, e)
    try:
        # The receipt's verdict rides along: the reach gate tells a peer's push from a person's words by it.
        control_module().push_live(peer, session, text, e, project.id, words=plan.words,
                                   marker=holder_module().marker(plan.receipt, plan.attempt, plan.body))
    except PushHeld as err:
        return err.outcome()   # its receipt stays prepared: its next step is a push (HOLDER_RETRY)
    except SendFailed as err:
        if err.phase == "before":
            return "failed:%s" % err
    holder_module().pushed(plan.receipt, plan.attempt)
    return HandedOff()


def holder_wake(project, e):
    """The text of a retry whose body the conversation already holds (a row
    its bridge found retained): a pointer to it, the same receipt's marker
    put before it by push_live."""
    return "[sminos chat %s %s from %s → @you, again]\nIt is above in this conversation, delivered before: read it " \
           "there." % (project.name, event_ref(e), frame_alias(str(e.get("via") or e.get("from") or "")))


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


# Message reach (P5 O18 D3, D8; MAWS docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md). On a machine
# whose endpoint advertises `reach` (sminos_audience.reach_capable), every log event handed to a session as a
# peer frame is the endpoint's to admit at that moment: `reach? {id, project, session, event}`, answered on the
# socket the uplink alone holds. So the gate sits inside the push primitives (push_live, resume_session), and
# only the uplink can let a push through it: it grants a single-use permit for exactly the push the endpoint
# answered `deliver` for, immediately before carrying it out, and clears it after (reach_permit). Every other
# deliverer leaves such an event owed at its writer, as it leaves a person's words, for the uplink's reach pass
# (reach_due, deliver_reach). No earlier answer, admission or receipt stands for a later push.
#
# One case needs no ask (the coordinator's ruling): a session of this machine messaging another session of this
# machine whose record names literally the same owners — an identity comparison of two local records, `@machine`
# on one machine being one owner set, never grade logic (same_owner_local) — in a log where the writer name is
# this machine's provenance (own_writers_here): a git mirror's merge can bring a line under any name.

_REACH_PERMITS = set()   # (project id, session, writer, seq, event hash): pushes the uplink may make now
PROJECTLESS = "%s has no project, so only its owners' sessions reach it"


def reach_key(project_id, session, e):
    return (project_id, session, e.get("writer"), e.get("seq"), event_hash(e))


@contextmanager
def reach_permit(project, session, e):
    """The push of `e` to `session` that the endpoint answered `deliver`
    for, let through the reach gate for as long as the block runs, once:
    the uplink's, around the one delivery it carries out."""
    key = reach_key(project.id, session, e)
    _REACH_PERMITS.add(key)
    try:
        yield
    finally:
        _REACH_PERMITS.discard(key)


def own_writers_here(project):
    """Whether a line under this machine's own name in `project`'s log was
    written here: a project with no git remote that is a hub project of this
    machine's org, where the hub brings this machine's writers back only as
    its own signed echoes, or that nothing syncs. Not a project with a
    remote, whatever its transport: a git mirror's merge can import a line
    under any writer name, and `project init --hub` keeps the log and the
    remote (its archive since), so a converted mirror still holds what git
    imported. Not a project unknown here."""
    if project is None or project.remote:
        return False
    if project.hub is not None:
        e = enrollment()
        return e is not None and project.hub.get("org") == e["org"]
    return True


def same_owner_local(e, session, project):
    """Whether `e` is a session of this machine's own event (its writer
    `<this machine's name>/<session>` or a stream of it, in a log where that
    name is provenance: own_writers_here) to another session of this
    machine, both records reading and naming the same owners: a person's
    own sessions on one machine, which no reach ever restricts."""
    if not own_writers_here(project):
        return False
    writer = str(e.get("writer") or "")
    sender = writer_session(writer)
    if not sender or writer_base(writer) != "%s/%s" % (host_name(), sender):
        return False
    records, au = records_module(), audience_module()
    if not (au.is_local(sender) and au.is_local(session)):
        return False
    a, b = records.read(sender), records.read(session)
    oa, ob = (a or {}).get("owners"), (b or {}).get("owners")
    return isinstance(oa, list) and isinstance(ob, list) and bool(oa) and set(oa) == set(ob)


class ReachGate:
    """The one push check of message reach (P5 O18 D8), asked inside the
    push primitives for each log event they hand over as a peer frame."""

    def __init__(self, project):
        self.project = project if isinstance(project, str) or project is None else project.id
        self.home = project if isinstance(project, Project) else known_project(project) if project else None
        self.capable = audience_module().reach_capable()

    def applies(self, e, words=None):
        """Whether the push of `e` is the gate's: a log event handed over as
        a peer frame on a machine whose endpoint decides reach. A person's
        words (`words` True, or with no verdict a writer push_live takes as
        the owner's) are the words gate's."""
        if not self.capable or e is None:
            return False
        return not (words if words is not None else owner_event(e))

    def needs(self, e, session, words=None):
        """Whether the push needs the endpoint's `deliver`: the gate's, and
        not between one owner's sessions of this machine (same_owner_local).
        What every deliverer but the uplink leaves owed."""
        return self.applies(e, words) and not same_owner_local(e, session, self.home)

    def held(self, e, session, words=None, keep=False):
        """None when the push may go; "owed" when it may not now — no permit
        this process holds for exactly it (popped as it is checked, unless
        `keep`: a wake's check ahead of the push that spends it, T2's M2),
        or a recipient whose record cannot be read (D10: never asked about,
        owed until it reads again). A refusal is settled where the answer
        comes (deliver_reach), so the gate itself never answers "refused"."""
        if not self.needs(e, session, words):
            return None
        if records_module().unreadable(session):
            return "owed"
        key = reach_key(self.project, session, e)
        if key in _REACH_PERMITS:
            if not keep:
                _REACH_PERMITS.discard(key)
            return None
        return "owed"


def reach_hold(project, session, events, words=None, keep=False):
    """The reach gate over every event a push carries: ReachHeld (nothing
    handed over) when it holds any of them. `keep`: the permits checked are
    left for the push that follows (a wake's check, which consumes nothing)."""
    events = [e for e in events if e is not None]
    if not events:
        return
    gate = ReachGate(project)
    if not gate.capable:
        return
    held = [e for e in events if gate.held(e, session, words, keep) is not None]
    if held:
        raise ReachHeld("owed", held, "%s to %s waits for its endpoint's word on its reach" % (
            ", ".join(event_ref(e) for e in held), session[:8]))


def owners_meet(sender, recipient):
    """Whether a push no log event stands for may go (D8's projectless
    push): the sender's owners — the session's (`sender`), or with none the
    operator's, the machine's (`@machine`) — meet the recipient session's.
    The endpoint's resolved ids where both are known (the machine's as it
    resolved a `@machine` session's: sminos_audience.machine_owners), else
    the records' tokens; unknown is no."""
    records, au = records_module(), audience_module()

    def owners(sid):
        if not sid:
            resolved = au.machine_owners()
            return (set(resolved) if resolved else None), {records.MACHINE}
        resolved = au.owners_of(sid)
        rec = records.read(sid) if au.is_local(sid) else None
        tokens = rec.get("owners") if rec and isinstance(rec.get("owners"), list) else []
        return (set(resolved) if resolved else None), set(tokens)
    try:
        rs, ts = owners(sender)
        rr, tr = owners(recipient)
    except au.StreamUnknown:
        return False
    if rs and rr:
        return bool(rs & rr)
    return bool(ts & tr)


def projectless_refusal(recipient, alias):
    """D8's refusal of a push with no log event to ask about, toward a
    session whose owners the sender's do not meet; None when it may go (or
    nothing here decides reach)."""
    if not audience_module().reach_capable():
        return None
    if owners_meet(os.environ.get("CLAUDE_CODE_SESSION_ID", ""), recipient):
        return None
    return PROJECTLESS % alias


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
    first. To a process recorded `gate` (O12 M4b) the push prepares a
    receipt first and the outcome is HOLDER_AWAITING (holder_push); an
    event whose receipt is held already is carried on under its id
    (holder_owed), its retry checked against the revocation set and the
    read-only policy as a fresh push is. The outcome, or None."""
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
        cursor = cursor_load(project, session)
        if noted and noted[0] == e["seq"]:
            outcome = noted[1]
        elif (owed := holder_owed(project, member, session, e, events, cursor)) not in (None, HOLDER_RETRY):
            outcome = owed
        else:
            held = WordsGate(project).held(e, session)
            if held == "revoked":
                holder_module().settled(project.id, session, e)
                return outcomes.REFUSED_REVOKED
            if held is not None:
                return None
            if outside and policy.read_only():
                outcome = outcomes.READ_ONLY
            elif verdict == "refuse":
                outcome = outcomes.REFUSED_WORDS
                daemon_log(WORDS_REFUSED_SAID % (event_ref(e), project.name, session, refused_key(project, session, e)))
            elif stale_hold(delivered_load(project, session), session, e):
                outcome = "recorded"   # held for a thread this session no longer fills: pushed to none
            elif (unknown := held_unreadable(delivered_load(project, session), e)):
                outcome = hold_outcome("unknown", unknown)   # no binding known: deferred, pushed nothing
            elif (hold := hold_now(session)):
                # Held since it was asked about: pushed nothing (T2's §4); an event for the live alone settles
                # `recorded` as the pass settles it, never debt; an addressed one stays owed for its thread.
                outcome = "recorded" if e.get("wake") else hold_outcome(hold)
            else:
                outcome = holder_push(project, member, session, e, events, cursor, words=verdict == "words",
                                      retry=owed is not None)
        outcome = held_decided(project, session, e, outcome)
        if _conclude(project, member, session, e, outcome, outside):
            holder_module().settled(project.id, session, e)
        return outcome


# The daemon.log lines of the endpoint's refusals of an event (deliver_verdict's of a person's words,
# deliver_reach's of a peer's reach): the one record of either here, which a returned seat's `fill --resume`
# reads, by the event's identity, to say its task was refused (refusal_logged).
# Each names the event by its identity, `refused_key`'s: the project's id, the writer whole, the seq and the
# session's id whole, never a display label.
WORDS_REFUSED_SAID = "the endpoint refused %s (%s) as words into %s: nothing delivered [%s]"
REACH_REFUSED_SAID = "the endpoint refused %s (%s) reach into %s: %s; nothing delivered [%s]"


def refused_key(project, session, e):
    """The identity a refusal's daemon.log line carries (WORDS_REFUSED_SAID,
    REACH_REFUSED_SAID) and refusal_logged matches."""
    return "event %s %s:%d to %s" % (project.id, e["writer"], e["seq"], session)


def refusal_logged(project, session, e):
    """Whether daemon.log says the endpoint refused event `e` to `session`,
    as words or its reach, by the event's identity (refused_key), from the
    log's last 256 KiB."""
    try:
        with open(os.path.join(root(), "daemon.log"), "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - (256 << 10)))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    return ("; nothing delivered [%s]\n" % refused_key(project, session, e)) in tail \
        or (": nothing delivered [%s]\n" % refused_key(project, session, e)) in tail


def words_unanswered(project, member, event, why):
    """The endpoint gave no verdict on a words-gated event in time (O12 M6):
    a failed attempt, as a failed push is (delivered_fail; given up after
    DELIVERY_ATTEMPTS), when it is still its writer's first owed. The
    attempts, or None. For a session this machine holds now (held: it
    stopped while asked about) no attempt is counted: 0."""
    session = member.session
    if not session:
        return None
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        record = delivered_load(project, session)
        e = _first_owed(session, event["writer"], log_read(project), record)
        if e is None or e["seq"] != event["seq"]:
            return None
        if hold_now(session):   # under the delivery lock, afresh: a held session counts no attempt
            return 0
        if held_owed(project, session, record, e, "failed:unanswered") != "failed:unanswered":
            return 0   # decided held, its thread live: a missing verdict is no refusal, and settles nothing
        _conclude(project, member, session, e, "failed:%s" % why,
                  sibling_module("sminos_policy").outside_origin(e))
        return _delivery(delivered_load(project, session), e["writer"]).get("attempts")


def words_due(project, members):
    """{session: [event]}: for each of the members, the first owed event of
    each words-gated writer (words_route "ask") that no deliverer holds —
    none noted as pushed or holding a receipt (O12 M4b: handed to a `gate`
    process, awaiting its admission), none another event of its writer
    stands before.
    The project's log read once, and split by addressee once (addressees),
    as the daemon's delivery pass splits it: each member's owed events are
    read from its own share, not from the whole log again. What the uplink
    asks `words?` about. An outside event on a read-only machine is none:
    deliver_next settles it `refused-read-only` unasked. The log is the
    shared merged list (_store_whole), so the split is kept while no file
    of it moves: what is handed out is read, never changed (the uplink's
    asks keep the events, its frames copy them, and deliver_verdict reads
    the log again)."""
    policy = sibling_module("sminos_policy")
    holder = holder_module()
    read_only = policy.read_only()
    events = _store_whole(project, "log", shared=True)[1]
    to = addressees(events)
    out = {}
    for m in members:
        if not m.session or m.session not in to:
            continue
        record = delivered_load(project, m.session)
        firsts = {}
        for e in _owed_kept(events, to, m.session, record):
            firsts.setdefault(e["writer"], e)
        due = [e for w, e in sorted(firsts.items())
               if words_route(project, e) == "ask" and (_delivery(record, w).get("pushed") or [None])[0] != e["seq"]
               and not (read_only and policy.outside_origin(e)) and not holder.exists(project.id, m.session, e)
               and not held_unreadable(record, e)]
        if due and not hold_for(m.session):   # a held session is asked about nothing (M3)
            out[m.session] = due
    return out


REACH_VERDICTS = ("deliver", "refuse")


def reach_due(project, members):
    """{session: [event]}: for each of the members, the first owed event of
    each writer that a push would hand over as a peer frame the endpoint
    must admit (ReachGate.needs) — the uplink's to ask `reach?` about. None
    a person's words the words pass asks first (words_route "ask", with no
    receipt), none noted as pushed, none whose receipt awaits its admission
    or settles it (one whose next step is a push, HOLDER_RETRY, is due:
    each push asks again), none to a session whose record cannot be read
    (D10: owed, never asked), none an outside event on a read-only machine
    (deliver_next settles it unasked). Read as words_due reads the log."""
    policy = sibling_module("sminos_policy")
    holder = holder_module()
    records = records_module()
    gate = ReachGate(project)
    if not gate.capable:
        return {}
    words = WordsGate(project)
    read_only = policy.read_only()
    events = _store_whole(project, "log", shared=True)[1]
    to = addressees(events)
    out = {}
    for m in members:
        if not m.session or m.session not in to or records.unreadable(m.session):
            continue
        record = delivered_load(project, m.session)
        firsts = {}
        for e in _owed_kept(events, to, m.session, record):
            firsts.setdefault(e["writer"], e)
        due = []
        for w, e in sorted(firsts.items()):
            if (_delivery(record, w).get("pushed") or [None])[0] == e["seq"] \
                    or (read_only and policy.outside_origin(e)) or held_unreadable(record, e):
                continue
            if holder.exists(project.id, m.session, e):
                peer = peer_for_session(m.session)
                plan = holder.plan(project.id, m.session, e, event_hash(e), peer.get("pid") if peer else None,
                                   existing_only=True, prepare=False)
                if plan is None or plan.kind not in ("push", "legacy"):
                    continue
                verdict = holder.words_of(project.id, m.session, e)
            elif words_route(project, e) == "ask":
                continue
            else:
                verdict = words.words(e)
            if gate.needs(e, m.session, verdict):
                due.append(e)
        if due and not hold_for(m.session):   # a held session is asked about nothing (M3)
            out[m.session] = due
    return out


def deliver_reach(project, member, event, verdict, reason=None):
    """The endpoint's `reach` answer on an owed event (`deliver` or
    `refuse`, P5 O18 D3) carried out, as deliver_verdict carries out a words
    verdict: under the session's delivery lock, and only while the event is
    still its writer's first owed with the same body (None, nothing done,
    else). The revocation set and the read-only policy are read again
    first; a receipt held for it goes as holder_owed says. `deliver` pushes
    it as deliver_next would (holder_push: a receipt first to a `gate`
    process), the reach gate let through for this one push (reach_permit):
    a `human` event as a peer's, the words verdict that sent it here having
    been `peer`. `refuse` pushes nothing: it settles `refused-reach` on this
    machine alone, said in one daemon.log line that names the position, the
    recipient and the reason, never the text, and no outcome goes back. The
    outcome, or None."""
    session = member.session
    if not session or verdict not in REACH_VERDICTS:
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
        cursor = cursor_load(project, session)
        if noted and noted[0] == e["seq"]:
            outcome = noted[1]
        elif (owed := holder_owed(project, member, session, e, events, cursor)) not in (None, HOLDER_RETRY):
            outcome = owed
        else:
            gate = WordsGate(project)
            held = gate.held(e, session)
            if held == "revoked":
                holder_module().settled(project.id, session, e)
                return outcomes.REFUSED_REVOKED
            if held is not None:
                return None
            if outside and policy.read_only():
                outcome = outcomes.READ_ONLY
            elif verdict == "refuse":
                outcome = outcomes.REFUSED_REACH
                daemon_log(REACH_REFUSED_SAID % (event_ref(e), project.name, session[:8], reason or "no reason given",
                                                 refused_key(project, session, e)))
            elif stale_hold(delivered_load(project, session), session, e):
                outcome = "recorded"   # held for a thread this session no longer fills: pushed to none
            elif (unknown := held_unreadable(delivered_load(project, session), e)):
                outcome = hold_outcome("unknown", unknown)   # no binding known: deferred, pushed nothing
            elif (hold := hold_now(session)):
                # Held since it was asked about: pushed nothing (T2's §4); an event for the live alone settles
                # `recorded` as the pass settles it, never debt; an addressed one stays owed for its thread.
                outcome = "recorded" if e.get("wake") else hold_outcome(hold)
            else:
                with reach_permit(project, session, e):
                    outcome = holder_push(project, member, session, e, events, cursor, words=gate.words(e),
                                          retry=owed is not None)
                gate.said(e, outcome)
        outcome = held_decided(project, session, e, outcome)
        if _conclude(project, member, session, e, outcome, outside):
            holder_module().settled(project.id, session, e)
        return outcome


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


# What the line after a wake opens with at a line's start (sminos_wake.LINE_HEAD, T2's §2): sminos's alone, so a
# sender's line that opens with it is given one leading space when its frame is composed (sender_text). A line
# starts after any break str.splitlines knows, as ALIAS_QUOTED reads one.
LINE_START = "[sminos] "
LINE_START_RE = re.compile("(^|[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029])(?=%s)" % re.escape(LINE_START))


def sender_text(text):
    """A sender's text as its frame carries it: each line that opens with
    LINE_START given one leading space, nothing else changed."""
    return LINE_START_RE.sub("\\1 ", text)


def compose_chat_frame(project_name, ref, sender, target, unread, text, label=""):
    """A chat event's frame; `label` is what follows the sender's alias
    (sender_labels, frame_alias); the text as sender_text gives it."""
    return "[sminos chat %s %s from %s%s → %s%s]\n%s" % (
        project_name, ref, frame_alias(sender), label, target, (" | unread %d" % unread) if unread else "",
        sender_text(text))


# What would let an alias pass for a frame's own syntax: the label's `,` and
# ` (`, a quote, the arrow and brackets, and any line break (str.splitlines').
ALIAS_QUOTED = frozenset(',()"→[]\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029')
# What a quoted alias writes as a `\uXXXX` escape: the line breaks JSON leaves
# raw (JavaScript's `.` stops at U+2028 and U+2029), and every angle the peer
# envelope's closing-tag escape starts at (ALIAS_ANGLES), which would put a
# backslash into the literal.
ALIAS_RAW_BREAKS = frozenset("\x85\u2028\u2029")


def frame_alias(alias):
    """A sender's alias as a frame or a `sminos chat` line writes it. The
    alias is the writer's own claim and the label after it sminos's
    (sender_labels), so an alias that could read as a label, as the frame's
    syntax or as an envelope's tag is a JSON string literal with no line
    break and no angle raw, which nothing on the way rewrites; any other is
    written bare, as always. A reader decodes an alias that opens with `"`
    and reads a bare one to its first `,` or ` (`."""
    if not ALIAS_QUOTED.intersection(alias) and not ALIAS_ANGLES.intersection(alias):
        return alias
    escaped = ALIAS_RAW_BREAKS | ALIAS_ANGLES
    return "".join("\\u%04x" % ord(c) if c in escaped else c for c in json.dumps(alias, ensure_ascii=False))


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


def former_ids(m):
    """The ids that name member `m` besides its session (X2, Interfaces §4):
    the sessions it continues, its thread's other sessions, and its thread
    id (a seat's is its seat id)."""
    thread = m.thread or ((m.seat or {}).get("seat_id") or "") or m.named
    return tuple(m.former) + tuple(m.thread_sessions) + ((thread,) if thread and thread != m.session else ())


def id_reach(m, name, full=True, short=True):
    """How `name` reaches member `m` as an id: "id" when it is its session
    (in full, or its first eight characters: `full`, `short` say which
    count), "former-id" when it is another id that names it (former_ids),
    which a name that is some member's current session or alias comes
    before (current_first); "" when neither."""
    if not m.session:
        return ""
    for how, ids in (("id", (m.session,)), ("former-id", former_ids(m))):
        if any(x and ((full and name == x) or (short and name == x[:8])) for x in ids):
            return how
    return ""


def alias_reach(m, name, short=""):
    """How `name` reaches member `m` by alias, the one rule every name lookup
    shares (§4 of the charge names design): "alias" when it is the member's
    alias, "former" when it is an alias the member held before
    (former_aliases), "" when neither. With `short` (`name#short`), only a
    member the short of whose session, or of another id that names it
    (former_ids: a session it continues, its thread's), starts so; by
    another id it is "former-id", which a match by the session's own short
    comes before. A retired row (a seat find_target still finds by its own
    name) answers to no alias it held before."""
    weak = False
    if short and not (m.session and m.session[:8].startswith(short)):
        if not any(s and s[:8].startswith(short) for s in former_ids(m)):
            return ""
        weak = True
    if name == m.alias:
        return "former-id" if weak else "alias"
    return "former" if m.state != "retired" and any(a == name for a, _ in m.former_aliases) else ""


def current_first(hits, name):
    """A lookup pass's (project, member) pairs from its (project, member, how)
    `hits`: those a current alias or id reached, when any did; else those
    another id of theirs reached (former_ids: a session they continue, their
    thread's); else those that held `name` before, narrowed to its latest
    holder — the latest ts of a joined or renamed carrying it — every holder
    tied at that ts kept, for the caller to refuse as ambiguous."""
    current = [(p, m) for p, m, how in hits if how not in ("former", "former-id")]
    if current or not hits:
        return current
    other = [(p, m) for p, m, how in hits if how == "former-id"]
    if other:
        return other

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


def thread_current(found, thread_of=lambda m: m.thread):
    """`found`, members newest join first, with one member per thread: a
    thread two rows hold at once answers by its latest `joined` alone (§4);
    the other's ids still name it (former_ids, thread_sessions).
    `thread_of(m)`: the thread a row is for, for this rule alone (a
    legacy row's is the seat its unstamped `joined` names, as for naming)."""
    seen, out = set(), []
    for m in found:
        t = thread_of(m) if m.session else ""
        if t:
            if t in seen:
                continue
            seen.add(t)
        out.append(m)
    return out


def match_members(name, short, projects, alias=True, ids=True):
    """The (project, member) pairs a tag's name answers to among the projects'
    members: their alias (with `short`, an alias whose short starts so), their
    short (`@short`), or their session id — another id that names them (a
    session they continue, their thread's other sessions, their thread id:
    former_ids) answering as theirs does, after a member's own; and, when
    none of those answers, an alias a member held before (current_first).
    With alias=False a bare name is matched against shorts and ids alone,
    with ids=False against aliases alone. A retired member answers to
    nothing, and neither does one whose thread has ended (has_ended: a
    member of a machine the org retired)."""
    hits = []
    for p in projects:
        for m in members(p):
            if m.state == "retired" or has_ended(m):
                continue
            if short:
                how = alias_reach(m, name, short)
            elif ids and (how := id_reach(m, name)):
                pass
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


def unreachable_hint(raw, name, short, projects, at="@", ids_only=False):
    """The refusal for a tag no member answers to that still names someone: a
    retired or vacant seat; a thread that has ended (T1's M4: a message to it
    is refused when it is sent), saying how it returns; a member of a
    machine the org retired; a seat-less session whose membership ended
    before threads (it is never resumed, so an untagged line is how to leave
    it a note), or one that moved to another project — where its short
    (`<at>short`) still reaches it. With `ids_only`, what the name names as
    a session id or short alone: the tier a bare name reads past its
    project (no_member's `ids`)."""
    for p in projects:
        if ids_only:
            view = view_of(p)
            seat = next((r.seat for r in view.rows if r.seat and r.seat["status"] == "retired" and id_reach(r, name)),
                        None)
            if seat is not None:
                return '%s is retired — a fill returns it: sminos fill %s/%s "<task>"' % (
                    raw, seat["group"], seat["alias"])
            m = next((m for m in [m for m in view.members if m.end == "machine"] + list(view.ended)
                      if id_reach(m, name)), None)
            if m is not None and m.end == "machine":
                return ("%s: %s's machine %s was retired; its sessions there have ended, and nothing reaches them"
                        % (raw, m.alias, m.machine))
            if m is not None and m.thread:
                return ended_refusal(raw, m)
            continue
        for s in project_seats(p):
            if s["alias"] == name and s["current"][:8].startswith(short):
                if s["status"] == "retired":
                    return '%s is retired — a fill returns it: sminos fill %s/%s "<task>"' % (
                        raw, s["group"], s["alias"])
                if not s["current"]:
                    return "%s is vacant — fill it to reach it" % raw
        view = view_of(p)
        for m in [m for m in view.members if m.end == "machine"] + list(view.ended):
            if not (alias_reach(m, name, short) if short else id_reach(m, name) or alias_reach(m, name)):
                continue
            if m.end == "machine":
                return ("%s: %s's machine %s was retired; its sessions there have ended, and nothing reaches them"
                        % (raw, m.alias, m.machine))
            if m.thread:
                return ended_refusal(raw, m)
        for alias, sh, reason, moved_to in retired_sessions(p):
            if alias == name and sh.startswith(short):
                if reason == "ended":
                    return ("%s: %s's session ended; say it untagged to leave a note — it reads the chat when "
                            "it is resumed" % (raw, alias))
                if reason == "moved" and moved_to:
                    return "%s moved to %s; %s%s reaches it" % (raw, project_label(moved_to), at, sh)
                return "%s is retired; it re-joins when its session runs again" % raw
    return ""


def ended_refusal(raw, m):
    """What a sender is told of a message to a thread that has ended (T1's
    M4): why, and what returns it — its human reopening its session, or for
    a spawned one, a fill."""
    why = "was retired" + (" by %s" % m.end_by if m.end_by else "") if m.end == "retire" \
        else "has ended (it stopped and was not reopened)"
    back = ("a fill of its seat%s returns it" % ("" if m.local else " on %s" % m.machine)) \
        if m.opened == "spawned" else "it returns when its human reopens its session"
    return "%s: %s %s; nothing was recorded for it — %s" % (raw, m.alias, why, back)


BARE_NAME = "a bare name reaches only your project; %s reaches anyone"


def no_member(raw, name, short, scope, elsewhere=(), at="@", ids=()):
    """Exit 4 for a name no member of `scope` answers to: what the scope still
    knows of it (unreachable_hint), then what the projects a bare name is
    read in as an id (`ids`: the org, the tier its live lookup read) know of
    it as one; else the members of other projects with that alias
    (`elsewhere`), each as the name that reaches it; else plainly none."""
    hint = unreachable_hint(raw, name, short, scope, at) or unreachable_hint(raw, name, short, ids, at, ids_only=True)
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
        if names_channel(t["project"]) is not None:
            die(channel_say_refusal(t["project"]), 1)   # nothing is said into a channel yet (CH1, §8)
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
        no_member(raw, name, short, tiers, ids=() if short else tiers)
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
              [(p, m) for p, m in match_members(name, "", org_scope(), ids=False) if p.id != project.id],
              ids=org_scope())


def resolve_tags(project, text, raws=None):
    """Resolve a message's leading tags at submission (resolve_tag). Returns
    (destination, recipients [{session, alias}], text, wake). The destination
    is the sender's project, or the one the tags reach; tags reaching two
    projects are refused, as are a tag matching no member and one matching
    several (named as alias#short). `@all` is the members of the sender's
    project live at submission. `raws`, a list given, is filled with each
    recipient's tags as [(their place in the run, their raw text)], for a
    split's text (sminos_audience.stream_for); left empty for `@all`, which
    names no session."""
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

    for t in tags:
        if t["project"] and names_channel(t["project"]) is not None:
            die(channel_say_refusal(t["project"]), 1)   # before any member is looked up, which reconciles (CH1, §8)
    destinations, recipients, held = {}, [], []
    run = audience_module().leading_run(text)[0]
    for i, t in enumerate(tags):
        p, m = resolve_tag(project, t)
        destinations[p.id] = p
        at = next((j for j, r in enumerate(recipients) if r["session"] == m.session), None)
        if at is None:
            recipients.append({"session": m.session, "alias": m.alias})
            held.append([])
            at = len(recipients) - 1
        held[at].append((i, run[i] if i < len(run) else t["raw"]))
    if raws is not None:
        raws[:] = held
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
    provisional = [s for s in all_seats if not s["current"] and s["short"]]
    if not provisional:
        return None   # no seat the harness's rows could name: `claude agents` is not asked
    row = agent_row(session_id=sid)
    if row:
        return next((s for s in provisional if s["short"] == row.get("id")), None)
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


# What the thread sweep writes in a wake lock it holds (sminos_daemon.resume_lock_out), and a journaled transition
# (TRANSITION_HOLD), so a wake that meets either waits it out rather than refusing; how long it waits. A launch
# writes LAUNCH_HOLD's line: the one holder a wake that finds the lock busy past the wait reads as `in flight`.
SWEEP_HOLD = "the thread sweep"
TRANSITION_HOLD = "a transition of the thread"
LAUNCH_HOLD = "pid %d since %s"
SWEEP_WAIT = 5.0


class LockBusy(Exception):
    """A lock could not be had before a deadline."""


class WakeBusy(LockBusy):
    """A transition met a wake of its thread holding the wake lock past its
    deadline (T2's M2): nothing was changed. A hook leaves it for the next
    reconciliation (a LockBusy); a verb exits 1 saying so (main)."""

    def __init__(self, thread_id):
        super().__init__("a wake of %s is in flight: nothing was changed; run it again" % thread_id[:8])
        self.message = str(self)


# (this process's thread, thread id) → its WakeHold: a hold is passed down, never taken twice. One registry per
# process, whichever copy of this module holds it: a copy loaded with no place in sys.modules (a test's
# spec_from_file_location) has siblings bound to another copy, and flock on a second descriptor of the same file
# would wait on its own process.
_WAKE_HOLDS = sys.modules.setdefault("_sminos_wake_holds", types.ModuleType("_sminos_wake_holds")).__dict__ \
    .setdefault("holds", {})


class WakeHold:
    """The wake lock of one thread (`<thread id>.resume.lock` at the root of
    SMINOS_HOME, flock), held by this thread of this process: a wake for the
    whole of its steps (§3), a transition while it opens its journal entry
    and reads what that entry records of the thread's process, the sweep for
    its decision. Registered while held, so a callee asked to take it
    (sminos_threads.begin) uses the hold its caller has: flock on a second
    descriptor of the same file would wait on its own process. Released by
    whoever ends it first (release is idempotent): a transition's hold ends
    at its begin, before anything is settled."""

    def __init__(self, thread_id, f):
        self.thread_id, self.f = thread_id, f
        _WAKE_HOLDS[(threading.get_ident(), thread_id)] = self

    def release(self):
        key = (threading.get_ident(), self.thread_id)
        if _WAKE_HOLDS.get(key) is self:
            del _WAKE_HOLDS[key]
        if self.f.closed:
            return
        try:
            self.f.seek(0)
            self.f.truncate()   # emptied before it is let go: the next holder never reads this one's name
            self.f.flush()
        except OSError:
            pass
        self.f.close()


def wake_lock_path(thread_id):
    return os.path.join(root(), thread_id + ".resume.lock")


def wake_held(thread_id):
    """The hold this thread of this process has on the thread's wake lock, or None."""
    hold = _WAKE_HOLDS.get((threading.get_ident(), thread_id))
    return hold if hold is not None and not hold.f.closed else None


def release_wake(thread_id):
    """The hold this thread has on the thread's wake lock, ended (nothing when none)."""
    hold = wake_held(thread_id)
    if hold is not None:
        hold.release()


def wake_lock(thread_id, until=None, holder=TRANSITION_HOLD, create=True):
    """The thread's wake lock, taken by a bounded poll until `until` (an
    epoch; SWEEP_WAIT from now by default) and named `holder` in its file:
    (WakeHold, "") once taken, or the one this thread holds already; (None,
    why) when it stays busy, `why` "in flight" when a launch holds it (its
    file names LAUNCH_HOLD's line twice, a poll apart) and else "sweep" (the
    sweep's moment or a transition's: a file that names no holder, or the
    previous holder's for a moment, is one of those). The file is created
    when absent (`create`), whichever store the record is in, so the sweep
    and a first wake meet on one file."""
    held = wake_held(thread_id)
    if held is not None:
        return held, ""
    path = wake_lock_path(thread_id)
    try:
        f = open(path, "a+" if create else "r+")
    except OSError:
        return None, "sweep"
    until = time.time() + SWEEP_WAIT if until is None else until
    named, why = None, "sweep"
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            pass
        try:
            f.seek(0)
            now_holder = f.read().strip()
        except OSError:
            now_holder = ""
        launch = now_holder.startswith("pid ")
        why = "in flight" if launch and now_holder == named else "sweep"
        named = now_holder if launch else None
        if time.time() >= until:
            f.close()
            return None, why
        time.sleep(0.05)
    try:
        f.seek(0)
        f.truncate()
        f.write(holder)
        f.flush()
    except OSError:
        pass
    return WakeHold(thread_id, f), ""


def transition_hold(thread_id, lock_until=None):
    """The wake lock for a journaled transition of the thread (T2's M2:
    an end, an advance, an absorption, a return): this thread's hold when it
    has one, else taken until `lock_until` (SWEEP_WAIT by default). Returns
    (hold, whether this call took it); WakeBusy when a wake holds it past
    the deadline."""
    held = wake_held(thread_id)
    if held is not None:
        return held, False
    hold, _ = wake_lock(thread_id, lock_until)
    if hold is None:
        raise WakeBusy(thread_id)
    return hold, True


def held_settled(thread_id, project, lock_until=None, tries=3):
    """The wake lock for an end that records the process it sees (T2's M2),
    taken only over a record with no open entry: the entry is replayed
    first with no hold (its settlement waits on delivery locks, and an
    absorption's on another record's wake lock, neither of which a wake
    lock is held across), then the hold is taken and the record read again
    under it; an entry that appeared meanwhile lets the hold go and is
    replayed again. (hold, took); WakeBusy when a wake holds it past the
    deadline, LogWriteFailed when an entry stays open."""
    threads = threads_module()
    for _ in range(tries):
        finish_thread(thread_id, project=project, lock_until=lock_until)
        hold, took = transition_hold(thread_id, lock_until)
        if not (threads.get(thread_id) or {}).get("pending"):
            return hold, took
        if took:
            hold.release()
    raise LogWriteFailed("thread %s holds an operation that could not be finished yet; nothing was done, and the "
                         "next reading verb finishes it" % thread_id[:8])


class ResumeHeld(ResumeRefused):
    """resume_session's hold (T1's M3): the seat holds a session its human
    opened (an older copy gave it a seat, D7), which is its own record's to
    wake, never the seat's; the caller records its message and delivers it
    as a verb aimed at that thread does (record: verb_delivered, T2's M4).
    `seat`: the seat as it was checked under its lock, whose session and
    project the message goes to."""

    def __init__(self, message, seat):
        super().__init__(message)
        self.seat = seat

    def record(self, text, verb="filled"):
        """The verb's message to the session the check found, as a verb
        aimed at a thread its human opened delivers it (verb_delivered)."""
        project = seat_project(self.seat)
        alias, session = self.seat["alias"], self.seat["current"]
        sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        via = default_from("")
        msg_id = uuidlib.uuid4().hex[:8]
        delivery = record_message(project, session, alias, "human" if not sid else via, via, text, msg_id)
        ended_after_record(project, alias, session, delivery)
        verb_delivered(project, session, alias, delivery, msg_id, verb)


def opened_by_human(session):
    """Whether a thread record its human opened (live or set aside) names the
    session as its current one, whatever a seat says of it: no verb but the
    wake (T2) starts a process for it (D1)."""
    t = threads_module().thread_of(session) if session else None
    return t is not None and t["opened"] == "human" and t["current"] == session


def human_refusal(alias):
    return ("%s is a session its human opened: its sessions are its human's to open, and sminos starts no fresh one "
            "for it (a message to it wakes the one it has where its machine can, and is held otherwise)" % alias)


def thread_owed(session):
    """Whether what is addressed to the session is owed until it is pushed
    to its process or its thread ends (D1, for every thread from T2): its
    canonical record (thread_of, the live stores) a thread of either kind,
    not ended, whose current session it is, whatever seat an older copy
    made over it; what was decided held for it stays owed until it is
    pushed or the thread ends (held_owed)."""
    return threads_module().current_record(session, fresh=True) is not None


def verb_to_thread(project, m, text, wait, verb, stop_turn=False, sender=None, via=None):
    """`resume`, `fill --resume` and `send --wait` aimed at a thread of this
    machine that holds no seat here, of either kind (T2's §6): refused for
    one that has ended, nothing recorded; else the message recorded first,
    as `send` records one, and delivered as the verb's own call delivers it
    (verb_delivered): a stopped thread woken and pushed to, a live one
    pushed to, or the message held and the verb exiting 4. `verb`: "resumed"
    or "filled", "" for `send --wait`; `stop_turn` (`resume`): a live
    background turn stopped first."""
    if has_ended(m):
        die(ended_refusal(m.alias, m), EXIT_UNKNOWN)
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    via = via or default_from("")
    sender = sender or ("human" if not sid else via)
    msg_id = uuidlib.uuid4().hex[:8]
    delivery = record_message(project, m.session, m.alias, sender, via, text, msg_id)
    ended_after_record(project, m.alias, m.session, delivery)   # ended since it was looked up: said so, exit 4
    verb_delivered(project, m.session, m.alias, delivery, msg_id, verb, wait, stop_turn)


# The line a verb prints, on stdout, when its message is recorded and owed to the session but not pushed (T2's M4):
# the daemon delivers it. A script (the board's `_resume_one`) reads it rather than the exit code or the prose.
OWED_LINE = "owed: %s"


def say_owed(session):
    print(OWED_LINE % session, flush=True)


def landed(session, msg_id):
    """Whether the message `msg_id` is in the session's conversation, waited
    for within the ack window (SMINOS_ACK_TIMEOUT): the evidence of a push."""
    tail = TranscriptTail(session)
    deadline = time.time() + float(os.environ.get("SMINOS_ACK_TIMEOUT", "120"))
    while not reply_to(session, msg_id, tail.read())[0]:
        if time.time() >= deadline:
            return False
        time.sleep(poll_interval())
    return True


def returned_task(delivery, session, ref, msg_id, wait=False):
    """A returned seat's task held for the endpoint's verdict (`fill
    --resume` of a retired seat on a cut-over machine), waited for within
    SMINOS_VERDICT_WAIT (30 s) and said with the return (the holder's ruling
    for M4): pushed (its id in the conversation), True, the one outcome
    whose reply `--wait` waits for; refused, as words or its reach
    (refusal_logged), exit 4, the seat returned and nothing pushed; else
    neither confirmed (an admitted task may still be queued before its
    conversation shows it): still owed (OWED_LINE), the daemon delivering
    it on the answer, a refusal said in daemon.log should it come: False,
    and with `wait` exit 4, no reply waited for."""
    if isinstance(delivery, WaitingSend):
        # Its append waits for its writer's head (no seq yet): the seat returned, and its task is queued, which the
        # daemon appends and delivers; no verdict is asked of an event not in the log.
        say_owed(session)
        print("%s: its task is queued, not in the log yet; the daemon delivers it once it is recorded" % ref,
              flush=True)
        if wait:
            die("no reply is waited for: the task is not in the log yet", EXIT_UNKNOWN)
        return False
    tail = TranscriptTail(session)
    deadline = time.time() + float(os.environ.get("SMINOS_VERDICT_WAIT", "30"))
    while True:
        if reply_to(session, msg_id, tail.read())[0]:
            print("%s: the endpoint admitted its task, and it was pushed to the returned session" % ref, flush=True)
            return True
        if refusal_logged(delivery.project, session, delivery.event):
            die("%s returned and its session runs, and the endpoint refused its task: nothing was pushed to it"
                % ref, EXIT_UNKNOWN)
        if time.time() >= deadline:
            say_owed(session)
            print("%s: no push of its task and no refusal of it are confirmed yet; the daemon delivers it on the "
                  "endpoint's answer" % ref, flush=True)
            if wait:
                die("no reply is waited for: the task is not pushed yet", EXIT_UNKNOWN)
            return False
        time.sleep(poll_interval())


def settled_elsewhere(session, alias, e, msg_id, verb, waiter):
    """A verb's message another deliverer settled between its record and
    this call: said delivered, and its reply waited for (`waiter`, None
    without --wait), only on evidence of a push (landed); a settlement alone
    proves none, since a stale or refused event settles too. No turn is
    stopped for it."""
    if not landed(session, msg_id):
        die("%s was %s: nothing is waited for" % (event_ref(e), SETTLED_UNSEEN % alias), EXIT_UNKNOWN)
    print("%s %s (%s)" % (verb or "sent to", alias, DELIVERED_ELSEWHERE), flush=True)
    if waiter is not None:
        waiter()


def verb_delivered(project, session, alias, delivery, msg_id, verb="", wait=False, stop_turn=False):
    """A verb's recorded message to a session no seat of this machine is
    for (T2's §6), delivered as a sender's own call delivers it
    (deliver_next, `due`), and what it prints: pushed (` (woken)` after a
    wake; with `stop_turn` a live background job's turn stopped first, a
    terminal's process left as it is and said so), then with `wait` the
    reply to it (wait_session_reply); held for its thread, §5's line and
    exit 4, nothing started; held for a moment, recorded and exit 4,
    nothing waited for. A send held for the endpoint's verdict, or behind
    an event it waits for, is left owed as `send` leaves it (exit 0, no
    turn stopped). One another deliverer settled before this call's lock
    stops no turn (settled_elsewhere). Whatever is left owed and unpushed
    prints OWED_LINE. `delivery`: its SendDelivery or WaitingSend, released
    here."""
    waiter = (lambda: wait_session_reply(session, alias, msg_id)) if wait else None
    if isinstance(delivery, WaitingSend):
        delivery.recorded_owed(alias)
        say_owed(session)
        if wait:
            die("nothing was started: the message is not in the log yet; the daemon delivers it once it is, and no "
                "reply is waited for", EXIT_UNKNOWN)
        return
    if delivery.held and not hold_now(session):
        # Owed for the endpoint's verdict, or behind an event it waits for, as a send held for it is; the thread's
        # own hold, when there is one, is decided first (T2's §4), below.
        if stop_turn:
            delivery.held += "; no turn was stopped, and the message follows on that answer"
        delivery.recorded_owed(alias)
        say_owed(session)
        if waiter is not None:
            waiter()
        return
    seq, writer = delivery.event["seq"], delivery.writer
    if all(e["seq"] != seq for e in delivery.queue):
        # Settled by another deliverer between the append and this lock: its turn is not this verb's to stop.
        delivery.release()
        settled_elsewhere(session, alias, delivery.event, msg_id, verb, waiter)
        return
    rec = running_now(session)
    terminal = rec is not None and str(rec.get("kind") or "bg") != "bg"
    t = threads_module().current_record(session, fresh=True) if stop_turn and rec is not None else None
    hold = None
    if t is not None and not terminal:
        # The stop and the wake that follows run under one hold of the wake lock (§3, W1), taken before anything
        # is read or stopped and kept through this call's delivery pass, whose wake uses it: the sweep and a
        # transition cannot act between them, and what would refuse the wake is decided under it, before the stop
        # (wake_refusal). A lock that cannot be had stops nothing, and the hold is the answer. (Taken under the
        # delivery lock; the pass's delivery lock is then taken under it, which only a deliverer polling this wake
        # lock, for its bounded wait, can meet.) A session no record holds is no thread a wake would start again:
        # nothing of it is stopped.
        if wake_held(t["thread"]) is None:
            hold, why = launch_hold(t["thread"])
            if hold is None:
                delivery.release()
                print("recorded %s for %s: %s" % (event_ref(delivery.event), alias, held_line(why, session=session)),
                      flush=True)
                say_owed(session)
                nudge_daemon()
                die(verb_hold_words(why, session), EXIT_UNKNOWN)
        try:
            reason = wake_refusal(t["thread"], session)
            if reason:
                turn_kept(alias, reason, session)   # a turn is stopped only for a wake that would start it again
            else:
                stop_background_turn(session, "", alias)
        except ResumeRefused as e:
            if hold is not None:
                hold.release()
            delivery.release()
            nudge_daemon()
            say_owed(session)
            die("%s; %s is recorded, and the daemon delivers it to the process that runs" % (
                e.message, event_ref(delivery.event)), e.code)
        except BaseException:
            if hold is not None:
                hold.release()
            raise
    delivery.release()
    member = next((x for x in members(project) if x.session == session), None)
    ref = event_ref(delivery.event)
    if member is None:
        if hold is not None:
            hold.release()
        print("recorded %s for %s: the daemon delivers it" % (ref, alias), flush=True)
        say_owed(session)
        nudge_daemon()
        die("no reply is waited for: %s is not a member of %s here" % (alias, project.name), EXIT_UNKNOWN)
    try:
        got = deliver_next(project, member, due=True)
    finally:
        if hold is not None:
            hold.release()
    mine = [o for ev, o in got["outcomes"] if (ev["writer"], ev["seq"]) == (writer, seq)]
    first = next((o for ev, o in got["outcomes"] if ev["writer"] == writer), "")
    entry = _delivery(delivered_load(project, session), writer)
    outcome = mine[0] if mine else ""
    if outcome in PUSHED or getattr(outcome, "handed", False):
        # Pushed, or handed by this call to its process's inbox (HandedOff), whose admission settles it (a
        # receipt): the frame is there. A receipt pending with no hand-off (no peer, a process yet to activate) is
        # owed, below; a handed one stays owed until its admission, so the owed line comes before any waiter.
        if outcome == HOLDER_AWAITING:
            say_owed(session)
        woken = outcome in ("woken", "woken?")
        said = "%s %s%s" % (verb or "sent to", alias, " (woken)" if woken else "")
        if terminal and stop_turn:
            said += ": a terminal holds it, so its turn runs on; the message went to it"
        print(said, flush=True)
        if waiter is not None:
            waiter()
        return
    if not mine and seq <= entry["settled"]:
        settled_elsewhere(session, alias, delivery.event, msg_id, verb, waiter)
        return
    why = hold_why(outcome) or (hold_why(first) if not mine and seq in entry.get("held", {}) else "")
    if why:
        print("recorded %s for %s: %s" % (ref, alias, held_line(why, session=session)), flush=True)
        say_owed(session)
        nudge_daemon()
        die(verb_hold_words(why, session), EXIT_UNKNOWN)
    if canonical_end(session, project):
        die("%s has ended: %s was recorded and is settled with its end, pushed nowhere" % (alias, ref), EXIT_UNKNOWN)
    nudge_daemon()
    if not mine:
        print("recorded %s for %s: owed behind an earlier message (%s)" % (ref, alias, first or "pending"), flush=True)
        say_owed(session)
        die("no reply is waited for: it is delivered after the earlier one", EXIT_UNKNOWN)
    if outcome == "recorded":
        die("nothing was pushed: %s no longer fills a thread sminos wakes; %s stays in the log" % (alias, ref),
            EXIT_UNKNOWN)
    print("recorded %s for %s: %s" % (ref, alias, outcome), flush=True)
    say_owed(session)
    if holder_waiting(outcome):
        # Not handed to its process (its mode cannot be read): owed with no attempt counted, nothing pushed.
        die("not pushed now: %s; the daemon delivers it, and no reply is waited for" % (
            outcome[len("held:"):] if outcome.startswith("held:") else "its receipt waits for its process"),
            EXIT_UNKNOWN)
    die("not pushed now (%s): the daemon tries it again" % outcome, 1)


def remote_held_wait(project, m, text, sender, via):
    """`send --wait` to a stopped thread another machine published as held
    (X3), on its `stopped` state or a `gone` one (a spawned thread whose
    conversation is not there, state_wake): recorded for its machine, the
    sender told what that machine
    published (remote_line), and exit 4: no reply is waited for here. A
    machine published `read-only` refuses the message there, which no
    process of the thread waits for."""
    e = record_message(project, m.session, m.alias, sender, via, text, uuidlib.uuid4().hex[:8], deliver=False)
    if isinstance(e, WaitingSend):
        e.recorded_owed(m.alias)
    else:
        print("recorded %s for %s: %s" % (event_ref(e), m.alias, remote_line(m) or held_line_151(m.machine)),
              flush=True)
        nudge_daemon()
    die("nothing was started: %s runs on %s, which %s it; no reply is waited for" % (
        m.alias, m.machine, "refuses" if why_of(m) == "read-only" else "holds"), EXIT_UNKNOWN)


def push_member(member, text, tagged, session=None, event=None, project=None, words=None):
    """Push one frame to a member that runs: to the live session (push_live:
    an owner's event through its bridge, keyed by `event`, the log event the
    frame carries, and `project`, the id of the project whose log holds it,
    or its supervisor; a peer's, and whatever those do not take, through its
    inbox socket). A session no process holds is pushed nothing here: an
    addressed event wakes its thread before this push (holder_push,
    wake_member), and what is left is `recorded`, or the hold's outcome for
    a thread this machine holds now (`tagged`: an addressed event; for an
    event decided held, deliver_next keeps it owed, held_owed). Given
    `session`, a seat that now holds another session is not this message's
    recipient: delivery goes by session id, so a replacement cannot
    misroute it. `words`: the endpoint's verdict on a person's words, which
    push_live takes in place of the writer on a cut-over machine. A push the
    reach gate holds (ReachHeld, inside push_live) is `held:reach …`, owed
    with no attempt counted."""
    session = session or member.session
    verdict = {} if words is None else {"words": words}   # a machine not cut over calls as it always has
    t = threads_module().current_record(session) if member.seat is not None else None
    # A session its human opened is reached by its session alone, whatever seat an older copy made over it.
    member_seat = None if t is not None and t["opened"] == "human" else member.seat
    if member_seat is not None:
        fresh = reload_seat(member_seat["seat_id"])
        if fresh is None or fresh["status"] == "retired":
            if fresh is not None and tagged:
                warn("%s is retired; re-fill it to reach it" % fresh["alias"])
            return "recorded"
        if session and fresh["current"] != session or not fresh["current"]:
            return "recorded"
        if fresh["engine"] == "codex":
            return "failed:legacy codex record"
        session = fresh["current"]
    # First, afresh: a process's record that names another session now (a `/clear`) is no peer of this one.
    hold = hold_now(session)
    peer = None if hold else peer_for_session(session)
    if not peer:
        return hold_outcome(hold) if hold and tagged else "recorded"
    try:
        control_module().push_live(peer, session, text, event, project, **verdict)
        return "sent"
    except PushHeld as e:
        return e.outcome()
    except SendFailed as e:
        return "sent?" if e.phase == "after" else "failed:%s" % e


def wake_member(project, member, session, e, words=None, due=False):
    """The wake an addressed event's push makes of a stopped thread (T2's
    §4, step 2), under the session's delivery lock: ("", None) when there is
    no thread to wake (a session that is no thread, an ended or a
    seat-less retired one), and the push goes on as before; ("woken",
    locks) when its process runs now and its inbox answers, read again as a
    live delivery reads it at its start (the thread still the session's and
    not ended, a seat still holding it), the push to follow, the seat's
    lifecycle lock in `locks` to be released after it; else (the outcome,
    None): §3's last paragraph (`gone`, `ended` and `lane` `recorded`,
    every other `held:<why>`). A seat's own steps (its lifecycle lock, only
    tried under the delivery lock: busy is `held:busy`; the reach check
    that consumes nothing) are resume_session's; a thread its human opened
    is woken from its own record, whatever seat an older copy made over
    it. `due` as deliver_next's."""
    threads = threads_module()
    if member.seat is None and latest_membership(_own_events(project, session)) == "retired":
        return "", None
    t = threads.current_record(session, fresh=True)
    if t is None:
        # No record to wake: a session that is no thread, unless the thread its membership is stamped with has a
        # record there that cannot be read (W2's `unknown`): owed, marked for that thread, nothing started.
        tid = str((threads.in_effect(_own_events(project, session)) or {}).get("thread") or "")
        if tid and threads.unreadable(tid):
            return hold_outcome("unknown", tid), None
        return "", None
    locks, hold = [], []

    def held():
        # W1, taken here (under the seat's lifecycle lock for a seat) and kept through the push that follows
        # (holder_push): every transition opens its entry under this lock, so none opens between the reading
        # below and the frame's handoff, and the push goes to the session the thread holds then. One this thread
        # holds already (a verb's, taken for its stop) is its own. Busy: §3's rows 1 and 2, the session pushed to
        # as a live one (at the moment of the push, as any live push) when a process holds it now.
        if wake_held(t["thread"]) is not None:
            return ""
        got, why = launch_hold(t["thread"])
        if got is None:
            return "" if live_now(session) else why
        hold.append(got)
        return ""
    try:
        # The thread the event's hold mark names, when it has one, is the one woken and pushed to: a mark for
        # another thread than the one chosen (the session went to it after the pass passed the mark) is the stale
        # hold, settled `recorded` as stale_hold settles one, nothing woken or pushed, whether or not the lock is
        # free. The mark is fixed under the delivery lock held here, and the wake's W2 reads the session still
        # this thread's under the wake lock.
        mark = _delivery(delivered_load(project, session), e["writer"]).get("held", {}).get(e["seq"])
        if mark is not None and mark != t["thread"]:
            return "recorded", None
        if t["opened"] == "spawned":
            s = reload_seat(t["thread"])
            if s is None or s["status"] == "retired" or s["current"] != session:
                return "recorded", None
            if s["engine"] == "codex":
                return "failed:legacy codex record", None
            try:
                locks = lock_seat(s, refusal=ResumeRefused)
            except ResumeRefused:
                return hold_outcome("busy", t["thread"]), None   # a verb holds the seat: owed, no attempt counted
            s = reload_seat(t["thread"])
            if s is None or s["status"] == "retired" or s["current"] != session:
                return "recorded", None
            busy = held()
            if busy:
                return wake_outcome(busy, t["thread"]), None
            try:
                woke = resume_session(s, locks, quiet=True, event=e, project=project.id, words=words, due=due)
            except ResumeRefused:
                return "recorded", None   # vacant or vanished since it was read
        else:
            reach_hold(project, session, [e], words, keep=True)   # ahead of the wake, consuming nothing
            busy = held()
            if busy:
                return wake_outcome(busy, t["thread"]), None
            woke = wake(t, session, due=due)
        if not woke.live:
            return wake_outcome(woke.why, t["thread"]), None
        # The member read again, as a live delivery reads it at its start: the thread still the session's, not
        # ended and with no entry open (an end, a hand-off, an absorption that began before the wake's hold, or
        # an older copy's, which takes none).
        now = threads.current_record(session, fresh=True)
        if now is None or now["thread"] != t["thread"] or canonical_end(session, project):
            return "recorded", None
        if now.get("pending"):
            return hold_outcome("pending", t["thread"]), None
        if t["opened"] == "spawned":
            again = reload_seat(t["thread"])
            if again is None or again["status"] == "retired" or again["current"] != session:
                return "recorded", None
        forget_caches()
        if peer_for_session(session) is None:
            return hold_outcome("starting", t["thread"]), None   # its process runs, its inbox not answering yet
        kept, locks, hold = locks + hold, [], []
        return "woken", kept   # its lifecycle lock and its wake lock kept for the push that follows
    except ReachHeld as err:
        return err.outcome(), None
    finally:
        unlock(locks + hold)


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
    written is a warning, since the message was delivered. A copy under an
    audience stream has the stream's audience kept in `home` first, and goes
    into a hub project's home alone (streams_here): elsewhere the log is
    published whole, so none is written, and a warning says so."""
    groups = {}
    for dest, e in delivered:
        groups.setdefault(e["writer"], []).append((dest, e))
    if len(groups) > 1:
        # One copy per audience among the delivering events (P5 O18 D4): each under its own stream, as theirs.
        return [c for group in groups.values() for c in [record_copy(home, group)] if c is not None]
    first = delivered[0][1]
    if is_stream(first["writer"]):
        if not streams_here(home):
            # A git-mirrored or local home publishes its whole log (the mirror stages everything): an audience
            # stream's body goes nowhere the hub does not filter it.
            warn("delivered; its copy is not kept in %s: the message is for a private session's audience alone, "
                 "and %s's log is not filtered by audience" % (home.name, home.name))
            return None
    fields = {k: v for k, v in first.items() if k not in ("writer", "seq", "kind", "from_project")}
    fields["to"] = [dict(r, project=dest.id) for dest, e in delivered for r in e["to"] if isinstance(r, dict)]
    refs = ["%s:%s:%d" % (dest.id, e["writer"], e["seq"]) for dest, e in delivered]
    fields["copy"] = refs[0] if len(refs) == 1 else refs
    try:
        if is_stream(first["writer"]):
            # Its audience kept in the home too, before the copy (the uplink's voids, the session's own reads),
            # as the delivering project kept it; one that cannot be kept fails the copy, never the delivery.
            keep_stream(home, first["writer"], next(
                (a for dest, _ in delivered for a in [audience_module().stream_audience(dest, first["writer"])]
                 if a is not None), None))
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
            # once this machine's daemon has pushed it: ask for that now. A
            # stopped session its machine says it holds (X3) is said so.
            print("%s: %s" % (name(r), remote_line(member) or "recorded (on %s)" % member.machine))
            nudge_daemon()
            continue
        result = deliver_next(dest, member, due=True) if member else {"outcomes": []}
        mine = [o for ev, o in result["outcomes"] if ev["writer"] == writer and ev["seq"] == e["seq"]]
        first = next((o for ev, o in result["outcomes"] if ev["writer"] == writer), "")
        if member and e["seq"] in _delivery(delivered_load(dest, member.session), writer).get("held", {}) \
                and (not mine or mine[0].startswith("held:")):
            # This very event decided held, and still owed: why, as its writer's pass found it (T2's §5).
            why = hold_why(mine[0] if mine else first) or hold_now(member.session) or "starting"
            print("%s: %s" % (name(r), held_line(why, session=member.session)))
            continue
        if mine:
            woken = {"woken": "sent (woken)", "woken?": "sent? (woken)"}   # §5: a live push's words, woken
            print("%s: %s" % (name(r), woken.get(mine[0], mine[0])))
            continue
        if member and settled_already(dest, member.session, writer, e["seq"]):
            pushed, said = settled_words(dest, member.session, e, name(r))
            print("%s: %s" % (name(r), "sent (%s)" % said if pushed else said))
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
    au = audience_module()
    for dest, ms in groups:
        try:
            # A broadcast wakes only what it may reach: each audience its own event (P5 O18 D4).
            splits = streams_for(dest, sid, [{"session": m.session, "alias": m.alias} for m in ms], a.text)
        except (au.Unreachable, au.StreamUnknown) as err:
            warn("not recorded in %s, so not sent to its %d: %s" % (dest.name, len(ms), err))
            lost = True
            continue
        # Where each recipient's transcript ends before its event is appended (frame_landed reads what follows).
        note_transcripts(r["session"] for _, _, rs, _ in splits for r in rs)
        for split_writer, aud, rs, _text in splits:
            fields = {"from": sender, "to": rs, "text": a.text, "wake": True, "scope": scope}
            if home is not None and home.id != dest.id:
                fields["from_project"] = home.id  # the sender's own project, where a reply finds it
            try:
                keep_stream(dest, split_writer, aud)
                e = log_append(dest, split_writer, kind, **fields)
            except OSError as err:
                warn("not recorded in %s, so not sent to its %d: %s" % (dest.name, len(rs), err))
                lost = True
                continue
            if e["seq"] is None:
                print(waits_line(dest, split_writer))
                continue
            delivered.append((dest, e))
            print("recorded %s in %s" % (event_ref(e), dest.name))
    if home is not None and delivered and all(p.id != home.id for p, _ in groups):
        record_copy(home, delivered)
    for dest, e in delivered:
        deliver_say(dest, e, e["writer"], e["to"], lambda r: "%s#%s" % (r["alias"], r["session"][:8]))
    if lost:
        sys.exit(1)


def channel_say_refusal(q):
    """What a say that names a channel is told (CH1, §8): speaking in one
    comes in a later version, and the plain tag works today."""
    return ("%s is a channel, and speaking in a channel is not available in this version of sminos yet: nothing was "
            "recorded. Tag the thread itself (@<alias>#<short> or @<short>), which reaches it in its own project as "
            "today" % q)


def cmd_say(a):
    """Record a message in a project's log, and deliver it to whom it tags;
    with a selector, to every live session of its scope (say_scoped).
    Nothing is said into a channel yet: `--in <channel>`, a selector naming
    one and a tag qualified by one (_resolve_tag) are refused before anything
    is appended, from a session and from a terminal."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    for q in ([a.in_] if a.in_ else []) + list(a.projects):
        if names_channel(q) is not None:
            die(channel_say_refusal(q), 1)
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
    raws = []
    dest, recipients, _text, wake = resolve_tags(home, a.text, raws)
    if dest is None:
        die("say outside a project: run it in a project's directory, or name one with --in <project>")
    if is_channel_id(dest.id):
        die(channel_say_refusal(dest.name), 1)   # however it was reached: an older copy's rooted registration
    if sid:
        if wake:
            recipients = [r for r in recipients if r["session"] != sid]
        elif any(r["session"] == sid for r in recipients):
            die("you cannot tag yourself")
    # One event per audience its recipients give, each with only its own recipients' tags (P5 O18 D4), refused
    # whole before anything is written when one of them is out of reach.
    au = audience_module()
    try:
        splits = streams_for(dest, sid, recipients, a.text, None if wake else raws)
    except au.Unreachable as err:
        die(str(err), EXIT_UNKNOWN)
    except au.StreamUnknown as err:
        die("say could not be recorded: %s" % err, 1)
    recorded = []
    note_transcripts(r["session"] for _, _, rs, _ in splits for r in rs)   # before the appends (frame_landed)
    for split_writer, aud, rs, text in splits:
        fields = {"from": sender, "to": rs if (rs or wake) else "*", "text": text}
        if wake:
            fields["wake"] = True
        if sid and home is not None and home.id != dest.id:
            fields["from_project"] = home.id  # the sender's own project, where a reply finds it
        try:
            keep_stream(dest, split_writer, aud)
            e = log_append(dest, split_writer, kind, **fields)
        except OSError as err:
            die("say could not be recorded: %s" % err, 1)
        if e["seq"] is None:
            print(waits_line(dest, split_writer))
            continue
        print("recorded %s in %s" % (event_ref(e), dest.name))
        recorded.append((e, rs))
    if recorded and sid and home is not None and home.id != dest.id:
        record_copy(home, [(dest, e) for e, _ in recorded])
    for e, rs in recorded:
        deliver_say(dest, e, e["writer"], rs)


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
    delivered it. `label` follows the sender (sender_labels, frame_alias)."""
    lines = str(e.get("text") or "").split("\n")
    target = target_label(e)
    copy = e.get("copy")
    refs = [copy] if isinstance(copy, str) else [r for r in copy if isinstance(r, str)] if isinstance(copy, list) else []
    if refs:
        target += " → %s" % ", ".join(project_label(r.partition(":")[0]) for r in refs)
    out = ["%s %s %s%s → %s  %s" % (e["ts"][11:19], event_ref(e), frame_alias(str(e.get("from", ""))), label, target,
                                    lines[0])]
    out += ["    " + line for line in lines[1:]]
    return "\n".join(out)


TS_RE = re.compile(r"^(\d{4}-\d\d-\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,3}))?)?)?Z?$")


def normalize_ts(ts):
    """A user-given time as the log's ts shape, so string order is time order."""
    m = TS_RE.fullmatch(ts.strip())
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
        above = [e for e in pool if writer_base(e["writer"]) != mine and e["seq"] > cursor.get(e["writer"], 0)]
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
_TITLES = {}  # session -> ((path, size, mtime_ns), (custom, ai)): valid while the file is unchanged


def transcript_title(session_id):
    """A session's title on this machine, as the harness names it ("Session
    name" in /status): the latest `custom-title` record of its transcript (set
    by /rename; an empty one clears it), else the latest `ai-title`; "" for
    neither. The ai title follows the conversation's topic; the custom one is
    the name the human gave it. The last fallback of the in-charge line (§5),
    and what the daemon publishes as `titled` (§8)."""
    custom, ai = transcript_titles(session_id)
    return custom or ai or ""


def transcript_titles(session_id):
    """(custom, ai): the latest `custom-title` and `ai-title` of a session's
    transcript, None for one not found. Read backward from the end, at most
    8 MiB, and at most TITLE_REACH past the latest ai title, or past a
    custom one found first (the harness re-appends both together, so the
    other is within that window when it is current); cached while the file
    is unchanged."""
    path = transcript_path(session_id)
    if not path:
        return None, None
    try:
        st = os.stat(path)
        key = (path, st.st_size, st.st_mtime_ns)
        held = _TITLES.get(session_id)
        if held and held[0] == key:
            return held[1]
        custom = ai = None
        reach = None   # where the window opened: the latest ai title, else a custom one that names something
        with open(path, "rb") as f:
            for at, line in _lines_backward(f, _complete_end(f), budget=8 << 20):
                if reach is not None and reach - at > TITLE_REACH:
                    break
                if b'-title"' not in line:
                    continue
                r = _record(line) or {}
                if custom is None and r.get("type") == "custom-title" and isinstance(r.get("customTitle"), str):
                    custom = " ".join(r["customTitle"].split())
                    reach = at if reach is None and custom else reach
                elif ai is None and r.get("type") == "ai-title" and isinstance(r.get("aiTitle"), str):
                    ai = " ".join(r["aiTitle"].split())
                    reach = at
                if custom is not None and ai is not None:
                    break
        _TITLES[session_id] = (key, (custom, ai))
        return custom, ai
    except OSError:
        return None, None


def titled_by_engine(session, name):
    """Whether `name` is the title the engine wrote for the session itself
    (its latest `ai-title`) and not the one its human gave it (its latest
    `custom-title`): a name the engine made up, whatever source its record
    gives it. 2.1.330's background worker titles a woken session and names
    its record by the title (`nameSource auto`); a later process of the
    session restores that name from the transcript as `user`."""
    if not name:
        return False
    custom, ai = transcript_titles(session)
    name = " ".join(name.split())
    return ai == name and custom != name


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


def _writer_events(project, host, session, store="log", listed=None):
    """The events of the writer `<host>/<session>` and of its audience
    streams (`<host>/<session>~<digest>`, P5 O18 D6), read directly: the
    plain file's, then each stream's, merged by ts, each file in its own
    order. `listed`: the log directory's listing (_log_listed), which a
    file must be in to be opened, and a stream of the writer to be looked
    for."""
    where = os.path.join(project.home, store)
    paths = [os.path.join(where, "%s.%s.jsonl" % (host, session))]
    if store == "log" and (listed is None or ("%s/%s" % (host, session)).replace("/", ".") in listed[1]):
        # Its streams are those this machine kept the audience of as it wrote their first event (keep_stream): a
        # stat while the project's streams.json holds, never a listing of the log on every read.
        base = "%s/%s" % (host, session)
        # Literal paths, as the plain writer's: a read creates nothing (writer_path reaches project_path, which may
        # make the home or write its registration), so a reader under a store lock takes no other lock (CH1's §3).
        paths += [os.path.join(where, w.replace("/", ".") + ".jsonl")
                  for w in sorted(audience_module().streams_of(project)) if writer_base(w) == base]
    if listed is not None:
        paths = [path for path in paths if os.path.dirname(path) != where or os.path.basename(path) in listed[0]]
    files = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                files.append([e for e in map(parse_event, f) if e])
        except OSError:
            continue
    if len(files) <= 1:
        return files[0] if files else []
    return list(heapq.merge(*files, key=lambda e: e["ts"]))


def _former_events(project, session, store="log", listed=None):
    """The session's events under the names this machine wrote under before
    it enrolled, for a session it held under them (is_self), oldest name
    first: still the session's own, though nothing appends to them any more."""
    return [e for host, held in machine_identity()[1].items() if session in held
            for e in _writer_events(project, host, session, store, listed)]


def _own_events(project, session, store="log", listed=None):
    """The session's own writer files, read directly (the hook reads nothing
    else of the log): under this machine's former names, then its name now
    (its plain writer and its audience streams, merged by ts). `listed`:
    the log's listing, which a file must be in (_writer_events)."""
    return _former_events(project, session, store, listed) \
        + _writer_events(project, host_name(), session, store, listed)


def _own_events_but(project, session, writer):
    """The session's own events but those of `writer`'s file: what a guard
    on that file reads beside it (lifecycle)."""
    return [e for e in _own_events(project, session) if e["writer"] != writer]


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
            if other == session or not UUID_RE.fullmatch(other):
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


QUESTION_CLOSED = "closed: the session stopped before this was answered"   # Interfaces §2


def close_questions(thread):
    """Each `question` a stopped thread's sessions asked within the thread
    with no `answered` for its `src`, closed in the project it was asked in
    (T1's M3, D1: its state lived in the process that asked): an `answered`
    with QUESTION_CLOSED and the marker `closed: stopped`, through
    append_host (which chooses the store and the asker's writer, and appends
    a second answer to one ask never). A question of a session's episode
    stamped with another thread (a former session that runs on as a thread
    of its own) is that thread's, and stays open. Every project known here
    that holds the session's own events is read: a session that joined
    elsewhere after asking left its question where it asked it. Only a
    question positively the thread's (its episode marked with the thread's
    id) is closed, but for the current session in the project it is in now,
    where a question of an unmarked episode (from before threads) is its own
    too: an unmarked episode of a former session, or elsewhere, may be
    another conversation's. The events appended."""
    out, tid, cur = [], thread["thread"], thread["current"]
    projects, home = known_projects(), last_project(cur)
    for sid in dict.fromkeys(thread["sessions"] + [cur]):
        if not sid:
            continue
        for project in projects:
            marks = ("", tid) if sid == cur and home is not None and project.id == home.id else (tid,)
            log = _own_events(project, sid)
            own = log + _own_events(project, sid, HOST_STORE)
            asked = [q for q in own if q["kind"] == "question" and q.get("src")]
            if not asked:
                continue
            r = _projection(log).get(sid)
            answered = {e.get("src") for e in own if e["kind"] == "answered"}
            closing = [{"kind": "answered", "from": str(q.get("from") or ""), "src": q["src"],
                        "text": QUESTION_CLOSED, "closed": "stopped"}
                       for q in asked if q["src"] not in answered and (episode_mark(r, q) if r else "") in marks]
            if closing:
                out += append_host(project, sid, list({e["src"]: e for e in closing}.values()))
    return out


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
    there. Returns the events appended. A channel's log takes no host event
    (CH1): its session's project is never a channel (join_refusal, the .smns
    rule), and this raises if one is."""
    if is_channel_id(project.id):
        raise LogWriteFailed("%s is a channel: what a session sends its human goes to its own project" % project.name)
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


def record_session(project, session, tpath, event, last_message="", source="", override=None):
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
    evidence, former = session_evidence(session, seat, marked)
    if event == "SessionStart":
        position_init(project, session, tpath, since)
    if entry_open(session):
        return   # its thread's open entry is the next reconciliation's to finish: nothing restated around it
    ensure_record(project, session, seat, peer, evidence, former)
    if seat is None and threads_module().awaits_seat(session, peer, True):
        return   # a spawn's child: its seat joins it once its launcher learns its id
    if event == "SessionStart" and source == "clear" and seat is None:
        # At a `/clear` the alias goes with the process (M3): the session left gives it up first.
        left, given_up, where, clearing = cleared_witness(session, source)
        if left:
            try:
                # In the project the session left is a member of, against the process the /clear was witnessed in.
                release_alias(where, left, given_up, clearing)
            except (OSError, LockBusy, LogWriteFailed) as e:
                daemon_log("record: the alias of %s was not released to %s: %s" % (left[:8], session[:8], e))
    alias = _member_alias(project, session, seat, peer, marked, evidence, override)
    if event == "SessionStart" and alias is not None:
        # Its process holds the session again (§6, row 8), maybe before any sweep sees it: the stop mark goes, so
        # the rule's clock never runs on a mark from before this process (T1's M4).
        try:
            threads_module().stop_seen(session, lock_until=_RECORD_DEADLINE)
        except (OSError, LockBusy):
            pass
    if event == "SessionStart" and source in ("startup", "resume") and alias is not None and seat is None:
        note_launch_of(session, peer)
    if event != "Stop" or alias is None:
        return
    until = time.time() + FLUSH_WAIT
    if _RECORD_DEADLINE is not None:
        until = min(until, _RECORD_DEADLINE - 0.5)
    await_flush(tpath, last_message, until)
    export_host(project, session, tpath, alias)


def entry_open(session):
    """Whether the session's thread (the live stores') has an open entry
    that is the session's — its current session, or one of the sessions
    its events name: the hook then appends nothing for it (Interfaces §6,
    6), neither a `joined` nor a publication of its record, and leaves the
    entry to the next reconciliation. A session the thread only had (one
    that runs again, a thread of its own) is not held by its entry."""
    t = threads_module().thread_of(session, ended=False) or {}
    entry = t.get("pending")
    return bool(entry) and (t["current"] == session
                            or any(e.get("session") == session for e in entry.get("events") or []))


def note_launch_of(session, peer):
    """The launch of the process that started a human-opened thread's
    current session, from its own hook (`CLAUDE_PID`): the directory, and the
    options its argument vector holds (sminos_threads.launch_options) and the
    names of those it drops for their value (launch_dropped), read with
    their exact boundaries; absent where the vector cannot be read. A
    background process (the engine's record says `kind` `bg`: a wake's, or
    one the engine pre-started, whose arguments are not the session's)
    keeps the options and dropped names the record holds (T2's M2). A lock
    not had in time skips it."""
    threads = threads_module()
    thread = threads.thread_of(session)
    if thread is None or thread["opened"] != "human" or thread["current"] != session:
        return
    cwd = launch_cwd(session, fallback=str((peer or {}).get("cwd") or ""))
    if str((peer or {}).get("kind") or "") == "bg":
        # A background process (a wake's, or one the engine pre-started): no launch its human made, so the
        # record keeps its options and what they dropped, which the next first wake reads (T2's M2).
        kept = thread.get("launch") if isinstance(thread.get("launch"), dict) else {}
        options, dropped = kept.get("options"), kept.get("dropped")
        options = list(options) if isinstance(options, list) else None
        dropped = list(dropped) if isinstance(dropped, list) else None
    else:
        argv = threads.process_argv(os.environ.get("CLAUDE_PID"))
        options = threads.launch_options(argv) if argv is not None else None
        dropped = threads.launch_dropped(argv) if argv is not None else None
    try:
        threads.note_launch(thread["thread"], cwd, options, dropped, lock_until=_RECORD_DEADLINE)
    except (OSError, LockBusy):
        pass


def session_evidence(session, seat, marked):
    """(evidence, former) for ensure_record from the hook or the bridge
    child: nothing for a seat or a session whose launch is pending (its
    provenance came with its launch), else the session's own environment
    (sminos_records.hook_provenance). A marked session MAWS launched for a
    remote member (MAWS_LAUNCHED_BY, O12 M11) binds the variable's
    appSessionId (sminos_records.bind_launched): its first session is the
    spawner's; a later one (a /clear, a resume that started a fresh session)
    continues the sessions bound before it, `former`, the latest first, so
    an owner change made on its predecessor carries over and the variable
    never grants the spawner again over a record. Walking them newest first,
    a readable record lets lineage decide; a record file that cannot be read
    is a barrier: no lineage past it and no evidence (`former` empty), so
    the session gets at most the provisional defaults, which publish
    nothing, until it reads again. Only when none of them has a record file
    (the first hook bound the app session, but the records' lock kept its
    record off) is the spawner its fallback, as for the first: no owner
    change can have been made without a record. The spawner's proof is read
    only while the session's own record is not final yet. A session whose
    own record cannot be read, or a binding that cannot be made, gives no
    evidence."""
    records = records_module()
    if seat or launch_pending(session):
        return None, None
    if records.unreadable(session):
        return None, None   # ensure_record leaves it as it is
    launched = records.launched_by() if marked else None
    if launched is None:
        return records.hook_provenance(marked), None
    plain = {k: v for k, v in os.environ.items() if k != records.LAUNCHED_ENV}
    try:
        earlier = records.bind_launched(launched["appSessionId"], session, _RECORD_DEADLINE)
    except (OSError, LockBusy) as e:
        try:
            daemon_log("record: session %s could not bind its launch's app session: %s" % (session[:8], e))
        except OSError:
            pass
        return None, None
    former = earlier or None
    for s in earlier:
        if records.read(s) is not None:
            return records.hook_provenance(marked, plain), former
        if records.unreadable(s):
            return None, []
    if records.is_final(records.read(session)):
        return records.hook_provenance(marked, plain), former
    return records.hook_provenance(marked, session=session), former


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


def _member_alias(project, session, seat, peer, marked=False, evidence=None, override=None):
    """Joins a joinable session the log does not hold as a member yet (a live
    process is evidence of activation), and returns the alias its messages to
    the host carry: its seat's, else the one it goes by (held_alias over the
    last name the log gave it). None when it is no member. `override`: the
    session's join override (override_of) as it was when the caller resolved
    `project`, read here when not given. The join is the `join` verb's to
    write while one moves the session (moving_elsewhere), and none is written
    once the override has changed since (a `join` that moved it)."""
    held = override_of(session) if override is None else override
    own = _own_events(project, session)
    if latest_membership(own) != "joined":
        join_on_sight(project, session, seat, peer, True, marked=marked, evidence=evidence, own=True,
                      recheck=lambda: project if override_of(session) == held else None)
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
    override = override_of(session)   # as the project is resolved: a `join` after it changes it (_member_alias)
    project = session_project(session, launch_cwd(session, fallback=cwd))
    if project is None:
        return []
    seen = _on_sight(project, session)
    marked = seen is not None and member_mark(seen[1])
    if seen is None or not joinable(*seen, marked):
        return []
    evidence, former = session_evidence(session, seen[0], marked)
    ensure_record(project, session, *seen, evidence, former)
    alias = _member_alias(project, session, *seen, marked, evidence, override)
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
    nothing for an internal fork, the engine's spare, a session in no
    project, or a non-member;
    a failure is a line in daemon.log, never an exit that blocks a turn
    (run_record bounds it in time)."""
    if os.environ.get("SMNS_INTERNAL"):
        return
    payload = hook_payload() if payload is None else payload
    if payload is None:
        return
    session, cwd = str(payload.get("session_id") or ""), str(payload.get("cwd") or "")
    tpath, event = str(payload.get("transcript_path") or ""), str(payload.get("hook_event_name") or "")
    if not (UUID_RE.fullmatch(session) and cwd and tpath) or hook_spare(session):
        return   # a spare is no session anyone opened (engine_spare): nothing of it is written
    try:
        # Its engine's config dir, from its own environment, before anything
        # reads the files the engine keeps there; not recorded, the rest goes on.
        record_config_dir(session)
    except OSError as e:
        try:
            daemon_log("record %s %s: its config dir was not recorded: %s" % (event, session[:8], e))
        except OSError:
            pass
    try:
        # The payload's cwd is where the session's shell is now; its project
        # is its launch directory's, which the transcript names (§1c).
        override = override_of(session)   # as the project is resolved (_member_alias)
        project = session_project(session, launch_cwd(session, tpath, fallback=cwd))
        if project is not None:
            record_session(project, session, tpath, event, str(payload.get("last_assistant_message") or ""),
                           str(payload.get("source") or ""), override=override)
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
# of. A live session whose bridge offers the side question (`btw`) is asked
# through it: one tool-less completion over the session's last request,
# reading the session's own cache, which derive's recent activity keeps warm
# (about a seventh of the headless fork's price; sminos_fork). Any other
# session, and one whose side question fails, is forked headless, and the
# fork is internal: SMNS_INTERNAL keeps the hook from recording it, and
# $SMINOS_HOME/internal/<pid>, written before the fork starts, keeps
# reconciliation from joining it (§5).
#
# The headless fork starts in safe mode — without the session's plugins,
# hooks, mods and MCP servers, which a fork answering from the conversation has no use
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

DERIVE_QUESTION = ("In one line of at most 120 characters: what is this session in charge of in this project — its "
                   "standing responsibility, not its latest step?")
DERIVE_PROMPT = DERIVE_QUESTION + " Answer with the line only."
# A member that has a line is shown it, with the bar for changing it: other
# sessions and the human find a session by its line and its name, so a line
# reworded at every derive (1,005 of 1,018 re-derives, 2026-11-08 to 11-19,
# when the fork was not shown its line) reads as new work each time.
DERIVE_KEEP = ("\nIts current line is: %s\nOther sessions and your human partner follow this session by its line, so "
               "answer with it unchanged while it still holds. Write a new line only when it is wrong about the "
               "responsibility or the responsibility itself changed: work taken on or handed off, a goal reached, a move to other work.")
DERIVE_MIN_TOOL_CALLS = 10
DERIVE_EVERY = 6 * 3600
# A compaction derives the member's line again only at every this many
# compactions since its last derived line (counted in $SMINOS_HOME/compactions/;
# SMINOS_DERIVE_COMPACTIONS overrides it).
DERIVE_COMPACTIONS = 3
DERIVE_LINE_MAX = 120
# A member whose fork failed is held out of `derive --all` this long (the
# daemon runs it every five minutes, and a fork that timed out tends to time
# out again); a derive that names the member does not wait.
DERIVE_RETRY = 3600
# A failed fork's line carries why, cut to this many characters.
DERIVE_WHY_MAX = 200

# A member sminos may name (charge_naming) is asked for a charge name with its
# line: the prompt is derive_prompt's, and the answer's name is kept only in
# this form — what can follow `@` in a message unquoted.
NAMING_ASK = ("On a second line, name the session after that responsibility: `name: ` followed by 2 to 4 lowercase "
              "English words joined by hyphens, specific enough that another session reading only the name knows "
              "what this one owns. Leave out the project's name, which is shown beside it.")
NAMING_KEEP = (" Its current name is `%s`: answer with it unchanged unless it no longer fits the responsibility, as "
               "for the line. A better wording is no reason: a name that changes is a session others lose track of.")
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
            why = "the line of %s was not recorded in %s's log" % (m.alias, project.name)
            try:
                got = addressed_append(project, sid, [{"session": m.session, "alias": m.alias}], "in-charge",
                                       {"session": m.session, "text": line, "source": "set"}, why)
            except OSError as e:
                die("%s: %s" % (why, e), 1)
            if got["seq"] is None:
                print(waits_line(project, got["writer"]))
        name = m.alias
    print("%s in charge of: %s" % (name, line or "(cleared)"))


class DeriveFailed(Exception):
    def __init__(self, reason, stderr=""):
        super().__init__(reason)
        self.reason, self.stderr = reason, stderr


class DeriveSkipped(Exception):
    """No fork may start where the member works (launch_refused)."""


class DeriveHeld(DeriveSkipped):
    """No fork of the session is started: this machine holds it (hold_now, T1's M3)."""


DERIVE_HELD = "it is stopped, and its human opened it: no fork of it is started until its human reopens it"


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


def derive_refusal(project, m, compacted=False):
    """Why a member is not derived, or "": only a local member with at least
    ten tool calls by its model, and no derived line in the
    last six hours (§5; whatever its name, which only decides whether derive
    may also name it: charge_naming); and one with a derived line only once
    its transcript was written since that line — the same conversation gives
    the same answer, and forking an idle session rebuilds its prompt cache.
    A stopped session its human opened (stopped_human) is not forked (T1's M3).
    `compacted` (the compaction hook's derive) waives those two pacing rules:
    a compaction is the evidence that much has happened. A set line (a
    spawn's brief, an operator's `charge`) never refuses: it stands only
    until the next derived line (charge_of;
    docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md §2, §4, §6)."""
    if not m.session:
        return "it holds no session"
    if not m.local:
        return "it runs on %s" % m.machine
    if threads_module().stopped_human(m.session):
        # T1's rule, by its own predicate (T2: the hold now names why a thread is not woken, and one that would be
        # woken is held by none): no engine is forked in the directory of a session its human closed (for a
        # protected folder, the system's dialog would be the daemon's); it is derived again once it runs.
        # derive_line asks again, afresh, at each fork.
        return DERIVE_HELD
    foreign = foreign_config(m.session)
    if foreign:
        return ("its engine runs under %s, not this process's config dir (%s), where a fork from here would look "
                "for it, on that dir's credentials" % (foreign, config_dir()))
    path = transcript_path(m.session)
    if not path:
        return "no transcript of it on this machine"
    derived = None if compacted else latest_across_writers(
        [e for e in log_read(project, kinds=("in-charge",)) if e.get("session") == m.session and e.get("source") == "derived"])
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
    `--resume` to find the transcript: the first of its directories that is
    one, or that this process may not look at (read_refused), which
    launch_refused then turns away."""
    candidates = [(m.seat or {}).get("cwd"), (session_running(m.session) or {}).get("cwd")]
    candidates += [e.get("cwd") for e in reversed(_own_events(project, m.session)) if e["kind"] == "joined"]
    return next((c for c in candidates if isinstance(c, str) and c and (read_refused(c) or os.path.isdir(c))),
                project.root or os.getcwd())


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


def derive_prompt(naming, current=""):
    """The derive prompt: the question, the member's `current` line to keep
    (DERIVE_KEEP) when it has one, and, where it may be named (a
    ChargeNaming), the ask for a charge name with the line; the taken list
    names only what could be answered (the kept form)."""
    question = DERIVE_QUESTION + (DERIVE_KEEP % current if current else "")
    if naming is None:
        return question + ("\n" if current else " ") + "Answer with the line only."
    shown = sorted(t for t in naming.taken if CHARGE_NAME_RE.fullmatch(t) and len(t) <= CHARGE_NAME_MAX)
    return "%s\n%s%s%s\nAnswer with the two lines only." % (
        question, NAMING_ASK, NAMING_KEEP % naming.current if naming.current else "",
        NAMING_TAKEN % ", ".join(shown) if shown else "")


def current_line(project, m):
    """The member's set or derived in-charge line as its row shows it (the
    line _member read from the episodes of its thread, §4), "" for none (a
    name or a title is no line to keep). The line is one plain
    line, NULs dropped and whitespace runs (newlines of a multi-line brief
    included) collapsed: answer_line keeps only an answer's first line, and a
    NUL would make the headless fork's argv raise ValueError."""
    line = m.charge if m.charge_source in ("set", "derived") else ""
    return " ".join(line.replace("\x00", "").split())


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
    try:
        names = os.listdir(d) if os.path.isdir(d) else ()
    except OSError:
        return
    for name in names:
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


def derive_line(project, m, prompt=DERIVE_PROMPT):
    """Ask the member's session `prompt` through a fork and return (line,
    answer): its one-line answer (answer_line) and the whole text the
    answer's name is read from. A live session whose bridge offers `btw` is
    asked through it, reading the session's own warm cache (sminos_fork); a
    side question that fails in any way (refused, an API error, aborted,
    silent past the timeout, no line in its answer) falls back to the
    headless fork, as does a session with no such bridge: safe mode,
    uncached, persisting nothing, no tools (the section's note), so derive
    succeeds wherever it did before, but where the fork may not start
    (DeriveSkipped: launch_refused). How it asked goes to stderr; a failure
    of the headless fork says why (DeriveFailed). Each fork is preceded by
    the fresh reading of T1's rule (stopped_human: a session that stopped, or
    whose process moved to another, since derive_refusal read it):
    DeriveHeld, nothing asked."""
    fork = sibling_module("sminos_fork")
    timeout = float(os.environ.get("SMINOS_DERIVE_TIMEOUT") or 120)
    if threads_module().stopped_human(m.session, fresh=True):
        raise DeriveHeld(DERIVE_HELD)
    if fork.bridge_offers(m.session, "btw"):
        try:
            got = fork.ask_btw(m.session, prompt, timeout=timeout)
            line = answer_line(got.text)
            why = "" if line else "its answer has no line"
        except fork.ForkFailed as e:
            why, line = e.reason, ""
        if line:
            _derive_said(m, got)
            return line, got.text
        sys.stderr.write("sminos: derive %s: btw gave no line (%s); asking a headless fork\n" % (m.alias, why))
    if threads_module().stopped_human(m.session, fresh=True):   # again: the side question may have taken its timeout
        raise DeriveHeld(DERIVE_HELD)
    refused = launch_refused(member_cwd(project, m))
    if refused:
        raise DeriveSkipped(refused)
    try:
        got = fork.headless_fork(project, m, prompt, tools=False, cache=False, timeout=timeout)
    except fork.ForkFailed as e:
        raise DeriveFailed(e.reason, e.stderr)
    line = answer_line(got.text)
    if not line:
        raise DeriveFailed("the fork answered nothing")
    _derive_said(m, got)
    return line, got.text


def _derive_said(m, got):
    """How derive asked, on stderr (its printed line does not change)."""
    sys.stderr.write("sminos: derive %s via %s · cache read %s · input %s\n" % (
        m.alias, got.via, format(got.usage["cacheRead"], ","), format(got.usage["input"], ",")))


def cmd_derive(a):
    """`derive <member> [--compacted] | --all`: ask a local member what it is
    in charge of, by a headless internal fork, and record the answer as a
    derived line — only where §5 allows (derive_refusal). --compacted (the
    compaction hook's, smns-derive.sh): the member just compacted, so the
    pacing rules are waived. --all: every local member of every
    project known here, as the daemon runs it every five minutes, but a
    member whose fork failed within the hour (DERIVE_RETRY); first lines
    before refreshes (derive_order). --refreshes N (the daemon's): at most N
    members that already have a derived line are forked, so a run, whose
    forks go one after another, never holds a first line back for long."""
    if bool(a.member) == bool(a.all) or (a.compacted and a.all):
        die("usage: sminos derive <member> [--compacted] | --all")
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
            m = next((x for x in members(p) if x.seat and x.seat["seat_id"] == s["seat_id"]), None) if p else None
            if m is None:
                die("%s/%s holds no member session to ask" % (s["group"], s["alias"]), EXIT_UNKNOWN)
            targets = [(p, m)]
        else:
            targets = [target[1:]]
    if a.all:
        sweep_pending_names()
        sweep_older("derive-failed", DERIVE_RETRY)
        sweep_older("compactions", 30 * 86400)
        targets = derive_order(targets)
    else:
        targets = [(p, m, False) for p, m in targets]
    if a.compacted:
        for project, m, _ in targets:
            clear_status(project, m)
        targets = [(p, m, r) for p, m, r in targets if compaction_due(m)]
    forked_refreshes = failed = 0
    for project, m, refresh in targets:
        spent = refresh and a.refreshes is not None and forked_refreshes >= a.refreshes
        outcome = derive_member(project, m, held_off=a.all, refreshes_spent=a.refreshes if spent else None,
                                compacted=a.compacted)
        failed += outcome == "failed"
        forked_refreshes += refresh and outcome in ("derived", "failed")
    if failed:
        sys.exit(1)


def compactions_path(session):
    return os.path.join(root(), "compactions", session)


def compaction_due(m):
    """Count one more compaction of the member and say whether its line is
    due again: at every DERIVE_COMPACTIONS-th since its last derived line
    (derive_member resets the count). A count that cannot be kept derives,
    as every compaction did before."""
    try:
        every = int(os.environ.get("SMINOS_DERIVE_COMPACTIONS") or DERIVE_COMPACTIONS)
    except ValueError:
        every = DERIVE_COMPACTIONS
    path = compactions_path(m.session)
    try:
        try:
            with open(path) as f:
                n = int(f.read().strip() or 0) + 1
        except FileNotFoundError:
            n = 1
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w") as f:
            f.write(str(n))
    except (OSError, ValueError) as e:
        warn("the compactions of %s could not be counted: %s" % (m.session[:8], e))
        return True
    if n < every:
        print("%s: not derived — compaction %d of %d since its last line" % (m.alias, n, every))
        return False
    return True


def clear_status(project, m):
    """A compaction clears a local member's `now:` status line: the line said
    what it was doing at some step before the compaction, and nothing else
    ever refreshes it. A seat's local `now` goes with it, as `status ""` does."""
    if not m.local or not m.status:
        return
    try:
        lifecycle(project, m.session, "status", text="")
        if m.seat:
            meta_set(m.seat["seat_id"], {"now": "", "updated": now()}, bump=False, create=False)
    except (OSError, LogWriteFailed) as e:
        warn("the status of %s was not cleared: %s" % (m.alias, e))
    else:
        print("%s now: (cleared at compaction)" % m.alias)


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


def derive_member(project, m, held_off=False, refreshes_spent=None, compacted=False):
    """Derive one member's line where §5 allows (derive_refusal), and, where
    it may be named (charge_naming), its charge name with it: kept only when
    the answer gives one in the charge-name form and free, and when the
    engine name it would replace, read before the fork, is still the
    session's after it (an owner's /rename meanwhile wins). A kept name rides
    on the in-charge event and is handed to the session (hand_name). A
    failed fork is stamped, and with `held_off` (--all) the member is not
    forked again until DERIVE_RETRY has passed; a derive that succeeds clears
    the stamp. One whose fork may not start where it works (DeriveSkipped) is
    refused, said once in daemon.log. `refreshes_spent`, the run's cap on
    refreshes once it is reached: a member that would be forked is left to
    the next run. `compacted`: derive_refusal's. Returns
    "refused", "deferred", "derived", or "failed" (nothing recorded)."""
    why = derive_refusal(project, m, compacted=compacted)
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
        line, answer = derive_line(project, m, derive_prompt(naming, current_line(project, m)))
    except DeriveHeld as e:
        # As derive_refusal's hold: refused, nothing stamped, so its reopening derives it at the next run.
        print("%s: not derived — %s" % (m.alias, e))
        return "refused"
    except DeriveSkipped as e:
        # Said once per session (daemon.log), not with every run's refusals.
        said = "derive %s (%s): no fork started, nothing recorded: %s" % (m.alias, m.session[:8], e)
        if not said_once(project.id, "unforked-" + m.session):
            try:
                daemon_log(said)
            except OSError:
                pass
        if not held_off:
            print("%s: not derived — %s" % (m.alias, e))
        else:
            # Held off as a failed fork is: its side question, asked first, may
            # fail every run (a member whose bridge has nothing to fork yet).
            derive_failed_mark(m.session, True)
        return "refused"
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
    try:
        os.unlink(compactions_path(m.session))   # the compactions count from this line
    except OSError:
        pass
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
    if not UUID_RE.fullmatch(a.session):
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
        shadow = "".join(
            "\nfile     .smns at %s names another project, %s (%s): the %s at %s decides here, project %s" % (
                f.at, f.project.name, f.project.id, "link" if by.by == "link" else "stored id", by.at, by.project.id)
            for f, by in overridden_smns(d))
        print("project  %s\nid       %s\nkind     %s\nsource   %s%s\nremote   %s\nhub      %s\nroot     %s\nhome     %s" % (
            p.name, p.id, kind, project_source(d), shadow, p.remote or "-", hub, p.root or "-", p.home))
    else:
        project_attach(a)


def project_init(a):
    """Write .smns at the repository's root; with --hub, name this machine's
    hub in it — added to a .smns that exists, which changes nothing else. A
    hub .smns for a repository that resolves by its remote pins the project
    it is now (its derived id, and its name unless --name gives one), so
    committing the file moves no session and splits no history. Where a
    stored statement on this machine decides the folder over any file there
    (statement_over_file), the file takes the id in effect, the
    statement's, as a hub project of this org, and init says the file is
    not what decides; sminos never writes a statement."""
    top = git_toplevel(os.getcwd())
    if not top:
        die("project init needs a git repository: .smns is committed at its root; "
            "a plain folder is declared with `maws project add`")
    path = os.path.join(top, SMNS)
    stated = statement_over_file(top)
    hub = stated.project.hub if stated else hub_module().enrolled_hub() if a.hub else None

    def decides(written=False, named=False):
        return "a stored statement on this machine decides this folder's project, %s%s: the .smns%s is not what decides here" % (
            STATED_WORDS[stated.by] % stated.at, ", project %s (%s)" % (stated.project.name, stated.project.id) if named else "",
            " just written, which names the id in effect," if written else "")

    if os.path.exists(path):
        smns = read_smns(path)
        if a.hub and smns:
            hub_module().add_hub(path, smns, hub, a)
            forget_caches()
            project_path(resolve_project(top), "log")
            if stated:
                print(decides())
            return
        if stated and smns and smns[0] == stated.project.id:
            print("%s already names project %s (%s), the id in effect\n%s" % (path, smns[1], smns[0], decides()))
            return
        die("%s is already project %s (%s)%s" % (top, smns[1], smns[0], "; " + decides(named=True) if stated else "")
            if smns else
            "%s exists but is unreadable — fix or remove it first" % path)
    pinned = repo_project(top, fresh=True) if hub and not stated and decision(top, fresh=True).by == "remote" else None
    given = stated.project if stated else pinned
    name = a.name or (given.name if given else safe_name(os.path.basename(owning_repo(top) or top)) or "project")
    if "/" in name or "\n" in name or not name.strip():
        die("a project name is one line without '/': %r" % name)
    data = {"project": stated.project.id if stated else pinned.id if pinned else str(uuidlib.uuid4()),
            "name": name, "remote": a.remote or ""}
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
    if stated:
        print(decides(True))


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


def resolve_seat_or_opened(q, verb, found=None):
    """What the verbs that start a process (`resume`, `fill`) name, by
    find_target's precedence (a name `send` refuses as ambiguous is refused
    here, exit 4): (seat, the session the name bound, None) for a seat — the
    bound session kept for locked_fresh, so a refill between this lookup and
    the lock cannot put another session behind `alias#short` — or (None, "",
    (project, member)) for a thread its human opened that holds no seat. A
    name find_target does not know is looked up as resolve_seat does. Exit 4
    for none, for a member that is neither, and for another machine's
    session. `found`: find_target's answer, when the caller has it."""
    found = find_target(q) if found is None else found
    if found[0] == "seat":
        return found[1], found[2], None
    if found[0] == "member":
        project, m = found[1], found[2]
        if m.opened == "human" or m.local and opened_by_human(m.session):
            if not m.local:
                die("%s runs on %s: %s from there, or sminos say/send reaches it from here" % (
                    m.alias, m.machine, verb), EXIT_UNKNOWN)
            return None, "", (project, m)
        die("no seat matching '%s'" % q, EXIT_UNKNOWN)
    if find_seat(q, caller_scope())[0] == "none":
        ended_or_gone(q)   # a thread that has ended is said so, and what returns it (T2's §6), exit 4
    return resolve_seat(q), "", None


def ended_or_gone(q):
    """Exit 4 with what the projects a name is read in still know of it
    when no member answers to it (unreachable_hint: a thread that has
    ended, and what returns it), in the tiers `send` reads it in: the
    projects `<project>/` names, the org for a full session id, else the
    caller's project, then the org for the name as an id; nothing when they
    know nothing of it."""
    proj, _, rest = q.rpartition("/")
    name, _, short = rest.partition("#")
    if proj:
        tiers = project_tiers(proj)
        hint = tiers and (unreachable_hint(q, name, short, tiers, "")
                          or not short and unreachable_hint(q, name, short, tiers, "", ids_only=True))
    elif UUID_RE.fullmatch(q.lower()):
        hint = unreachable_hint(q, q.lower(), "", org_scope(), "", ids_only=True)
    else:
        # As the live lookup reads it: `alias#short` in every project known here, a bare name in the caller's
        # project and then the org as an id.
        scope = caller_scope()
        hint = scope is not None and unreachable_hint(q, name, short, [scope], "") \
            or unreachable_hint(q, name, short, org_scope(), "", ids_only=not short)
    if hint:
        die(hint, EXIT_UNKNOWN)


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
            if (p := seat_project(res)) is not None:
                reconcile(p)  # the verb reads the project; no liveness probe needed
            res = reload_seat(res["seat_id"]) or res
            return ("seat", res, res["current"] if bound else "")
        return None

    def group_seat(group, alias):
        hits = [s for s in seats() if s["group"] == group and s["alias"] == alias]
        return exact("ambiguous" if len(hits) > 1 else "ok" if hits else "none", hits if len(hits) > 1 else
                     (hits[0] if hits else None))

    if UUID_RE.fullmatch(q):
        kind, res = find_seat(q)
        # A seat named by its id whose first session runs on as a thread of its own (§6, row 15): the id is that
        # session's, a current one, before the seat's (current_first, below).
        left = kind == "ok" and res["seat_id"] == q and res["current"] != q
        if not (left and any(m.session == q for p in known_projects() for m in members(p))):
            if left and running_now(q):
                # Its process runs, not joined yet (one its retirement may still have seen, retirement_holds): the
                # id names that session as much as the seat, and is never taken for the seat it left.
                die("'%s' is seat %s/%s's id and also session %s, which runs outside it and is not a member yet: "
                    "name the seat (%s/%s) to reach whoever holds it, or the session once it joins"
                    % (q, res["group"], res["alias"], q[:8], res["group"], res["alias"]), EXIT_UNKNOWN)
            hit = exact(kind, res)
            if hit:
                return hit
    proj, _, rest = q.rpartition("/")
    name, _, short = rest.partition("#")
    if proj and names_channel(proj) is not None:
        # No thread is found through a channel in this version (CH1, §8): a verb's fact goes to the thread's own
        # project, which a lookup through a channel's roster would not name.
        die("'%s' names a thread through a channel, which is not available in this version of sminos yet: name it "
            "by its own name (<alias>#<short> or <short>)" % q, EXIT_UNKNOWN)
    tiers = project_tiers(proj) if proj else []
    if proj and not short and not tiers:
        return group_seat(proj, name) or ("none",)

    def matches(projects, by_short):
        hits = []
        for p in projects:
            ms, rows = project_view(p)
            for m in ms + rows:
                if short:
                    how = alias_reach(m, name, short)
                elif by_short:
                    how = id_reach(m, name, full=False)
                else:
                    how = id_reach(m, name, short=False) or alias_reach(m, name)
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
    if UUID_RE.fullmatch(q):
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
    # An id binds in full or by its short (id_reach reads both), the seat's own id (its thread's) alone not.
    bound = short or any(name in (x, x[:8]) for x in (m.session,) + m.former + m.thread_sessions if x) \
        or alias_reach(m, name) == "former"
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
    if cwd and (read_refused(cwd) or os.path.isdir(cwd)):
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
    """Each lock let go: a lock file closed, a wake lock's hold (WakeHold) released."""
    for lf in locks:
        try:
            (lf.release if isinstance(lf, WakeHold) else lf.close)()
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
    _RECORDED_DIRS[0] = None
    for index in [_TINDEX, *list(_TINDEXES.values())]:
        index.stale()
    _PROJECTS.clear()
    _SEAT_PROJECTS.clear()
    _RECORD_PROJECTS.clear()
    _REPO_BRANCH.clear()
    _REPO_REMOTE.clear()
    _HOMES.clear()
    _VIEWS.clear()
    _ENROLLED.clear()
    _ORG_DIR.clear()
    _LEFT.clear()
    _UNKNOWN.clear()
    _SEAT_PIDS.clear()
    _ROOTS.clear()
    _RECORDED.clear()
    _LOG_LISTED.clear()
    _PROJECT_DIRS.clear()
    _LAST.clear()
    _BOOT.clear()
    _GENERATION[0] += 1


_GENERATION = [0]   # how many cache generations this process began (forget_caches)


def refresh_caches():
    """forget_caches, then the harness's agents rows read afresh."""
    forget_caches()
    return agents_json()


def harness_ok():
    return agents_json() is not None


# ------------------------------------------------------------ the engine's config dirs
#
# The engine writes a session's records (sessions/<pid>.json) and transcript
# (projects/<dir>/<id>.jsonl) under its own process's config dir:
# CLAUDE_CONFIG_DIR, else ~/.claude. Only the session's own processes see that
# environment, so a session whose engine runs under another dir has it
# recorded by its hook (record_config_dir), and each reader of a session's
# engine files asks session_config_dir; a reader of every session reads the
# default and every recorded dir (engine_dirs). A `claude --resume` launched
# from here looks in this process's own dir and runs on its credentials, so
# nothing resumes a session another dir holds (foreign_config).

CONFIG_DIRS = "config-dirs"   # under $SMINOS_HOME: <session>.json, {"configDir": <absolute path>, "at"}
# The registry as read: ({session: its recorded config dir}, [(engine dir,
# the sessions its records speak for, None for every one)]). Once a cache generation; and a listing kept, beyond the generation,
# while its directory's identity holds, once the directory held still
# REGISTRY_RACY_NS before it was read (a coarse clock): the plane's presence
# asks for it as it is now five times a second.
_RECORDED_DIRS = [None]
_RECORDED_LISTING = [None]    # (the directory, its inode, its mtime_ns), the registry
REGISTRY_RACY_NS = 1_000_000_000


def config_dir(env=None):
    """The engine's config dir as a process with this environment (this
    process's when None) runs it: CLAUDE_CONFIG_DIR, else ~/.claude;
    absolute. `config_dir({})` is the default."""
    env = os.environ if env is None else env
    return os.path.abspath(os.path.expanduser(env.get("CLAUDE_CONFIG_DIR") or os.path.join(home_dir(), ".claude")))


def config_dir_path(session):
    return os.path.join(root(), CONFIG_DIRS, session + ".json")


def _same_dir(a, b):
    return os.path.realpath(a) == os.path.realpath(b)


def _read_registry(d):
    recorded = {}
    try:
        names = os.listdir(d)
    except OSError:
        names = []
    for name in names:
        sid, ext = os.path.splitext(name)
        if ext != ".json" or not UUID_RE.fullmatch(sid):
            continue
        try:
            cfg = json_at(os.path.join(d, name)).get("configDir")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(cfg, str) and os.path.isabs(cfg):
            recorded[sid] = cfg
    owners = {}
    for sid, cfg in recorded.items():
        owners.setdefault(os.path.realpath(cfg), set()).add(sid)
    default = config_dir({})
    dirs, seen = [(default, None)], {os.path.realpath(default)}
    for cfg in sorted(set(recorded.values())):
        real = os.path.realpath(cfg)
        if real not in seen:
            seen.add(real)
            dirs.append((cfg, frozenset(owners[real])))
    return recorded, dirs


def _registry(fresh=False):
    """(recorded_config_dirs, [(dir, owners)]): once a cache generation; `fresh`,
    as the directory is now — a stat of it while a kept listing's identity
    holds. A transcript found for a session whose recorded dir changed is
    looked for again."""
    held = None if fresh else _RECORDED_DIRS[0]
    if held is None:
        d = os.path.join(root(), CONFIG_DIRS)
        try:
            st = os.stat(d)
            key = (d, st.st_ino, st.st_mtime_ns)
        except OSError:
            key = None
        listing = _RECORDED_LISTING[0]
        if key is not None and listing is not None and listing[0] == key:
            held = listing[1]
        else:
            began = time.time_ns()
            held = _read_registry(d)
            _RECORDED_LISTING[0] = (key, held) if key is not None and began - key[2] >= REGISTRY_RACY_NS else None
        before = _RECORDED_DIRS[0]
        if before is not None and before[0] != held[0]:
            for sid in set(before[0]) | set(held[0]):
                if before[0].get(sid) != held[0].get(sid):
                    _TRANSCRIPTS.pop(sid, None)
        _RECORDED_DIRS[0] = held
    return held


def recorded_config_dirs(fresh=False):
    """{session: config dir}: each session whose hook recorded a config dir
    other than the default (_registry)."""
    return _registry(fresh)[0]


def session_config_dir(session):
    """The config dir a session's engine writes its records and transcript
    under: the one its hook recorded, else the default. Every reader of one
    session's engine files asks this."""
    return recorded_config_dirs().get(session) or config_dir({})


def engine_dirs(fresh=False):
    """Every config dir whose engine files sminos reads: the default, then
    each one a session's hook recorded, each once."""
    return [d for d, _ in _registry(fresh)[1]]


def engine_record_paths(fresh=False):
    """[(path, owners)]: every engine session record under every config dir
    sminos knows (`fresh`, as recorded now), with the sessions its dir speaks
    for (speaks_for)."""
    return [(p, owners) for d, owners in _registry(fresh)[1]
            for p in glob.glob(os.path.join(glob.escape(d), "sessions", "*.json"))]


def speaks_for(owners, rec):
    """Whether an engine record found under a dir whose `owners` these are
    is its session's: the default's records speak for every session (None),
    another dir's only for the sessions registered to it — a dir copied from
    ~/.claude carries other sessions' records, live ones among them."""
    return owners is None or rec.get("sessionId") in owners


def record_config_dir(session, env=None):
    """A session's own hook's (and `join`'s, run from inside it): its config
    dir, from its own environment, recorded when it is not the default, a
    record removed once it is; written only when that changed."""
    mine, path = config_dir(env), config_dir_path(session)
    try:
        held = json_at(path).get("configDir")
    except (OSError, ValueError, AttributeError):
        held = None
    if _same_dir(mine, config_dir({})):
        if held is None:
            return
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    elif held != mine:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        write_json(path, {"configDir": mine, "at": now(ms=True)})
    else:
        return
    _RECORDED_DIRS[0] = _RECORDED_LISTING[0] = None
    _TRANSCRIPTS.pop(session, None)


def foreign_config(session):
    """The config dir a session's engine runs under when it is not this
    process's own, else "": a `claude --resume` of it launched from here
    would look for it in this process's dir, on that dir's credentials."""
    theirs = session_config_dir(session)
    return "" if _same_dir(theirs, config_dir()) else theirs


def engine_spare(rec):
    """Whether an engine session record is a spare's (2.1.330): a session
    the engine's supervisor claimed from its pool of pre-started processes
    with no prompt yet, under an id of its own, its record saying
    `"spare": true` until its first frame runs a turn in it. No reader of
    the records takes it for a session: no one opened it, and a wake's own
    claim carries no flag."""
    return rec.get("spare") is True


def hook_spare(session):
    """Whether the engine running this hook (CLAUDE_PID, beside the
    CLAUDE_CODE_SESSION_ID that names `session`) records it as a spare: its
    SessionStart fires at the claim, after the record is written. Read from
    the hook's own config dir (config_dir, its CLAUDE_CONFIG_DIR), which no
    one may have registered yet: the hook records it only after this."""
    pid = os.environ.get("CLAUDE_PID", "")
    if os.environ.get("CLAUDE_CODE_SESSION_ID") != session or not pid.isdigit():
        return False
    try:
        rec = json_at(os.path.join(config_dir(), "sessions", pid + ".json"))
    except (OSError, ValueError):
        return False
    return isinstance(rec, dict) and rec.get("sessionId") == session and engine_spare(rec)


def spare_now(session):
    """Whether a live process the engine records as a spare names the
    session (engine_spare), read afresh: its bridge's socket, which the
    bridge mod's child opens at its SessionStart, is then no process
    holding a session (process_holds). Read again at every call, so the
    session counts as any once its first frame drops the flag."""
    for p, owners in engine_record_paths(fresh=True):
        try:
            rec = json_at(p)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("sessionId") == session and engine_spare(rec) \
                and speaks_for(owners, rec) and pid_alive(rec.get("pid")):
            return True
    return False


def peer_records():
    """The harness's peer registry: one JSON per live-ish session under
    <config dir>/sessions/<pid>.json, for every config dir sminos knows
    (engine_record_paths, each speaking for the sessions its dir does), a
    spare's left out (engine_spare). Records of dead sessions linger, so
    callers check the pid before trusting one."""
    global _PEERS, _PEERS_UNREAD
    if _PEERS is None:
        recs, unread = [], []
        for p, owners in engine_record_paths():
            try:
                with open(p) as f:
                    d = json.load(f)
            except FileNotFoundError:
                continue   # its session ended while the directory was read
            except Exception:
                unread.append(os.path.basename(p))
                continue
            if not isinstance(d, dict):
                unread.append(os.path.basename(p))
            elif speaks_for(owners, d) and not engine_spare(d):
                recs.append(d)
        _PEERS, _PEERS_UNREAD = recs, unread
    return _PEERS


_PEERS_UNREAD = []


def peer_notes():
    """What the engine's session records could not tell, for a view that
    rests on them: [note], empty when every record was read."""
    peer_records()
    dirs = [os.path.join(d, "sessions") for d in engine_dirs()]
    if not any(os.path.isdir(d) for d in dirs):
        return ["no engine session records here (%s): no session reads as running" % ", ".join(dirs)]
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


_BOOT = {}   # a /proc's btime, as _linux_start read it, per cache generation


def _linux_start(pid):
    """A process's start, in whole epoch seconds, as Linux's ps reckons it
    (procps's pr_lstart): /proc/stat's boot time, a whole second, plus the
    start's offset in whole seconds. Its text is then ps's own, the same on
    every read: a record of it is compared as text (derive_running), and the
    harness records ps's reading (same_process). The process's true start
    can fall in the second after. 0 when there is no such process; None
    when /proc cannot tell (no Linux /proc), for ps to answer."""
    # The boot time, read once a cache generation (the kernel writes all of
    # /proc/stat out for each read, and every running session asks); a step
    # of the wall clock moves it, which the next generation reads. The
    # file's presence is still asked each time.
    boot = _BOOT.get(PROC)
    try:
        if boot is None:
            with open(os.path.join(PROC, "stat")) as f:
                boot = _BOOT[PROC] = next(int(line.split()[1]) for line in f if line.startswith("btime "))
        else:
            os.stat(os.path.join(PROC, "stat"))
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


def bound_peer(peer, session):
    """The last hop's peer, bound to its recipient: the engine's record of
    the process that runs `session` now — the records read afresh, the
    session id, the pid and the socket resolved together, its inbox
    answering — which must be the process the caller looked at (`peer`, its
    pid and socket; None for none looked at). What every push hands over
    through (push_live, and the one raw frame of a projectless send), so no
    caller hands in a peer it read before a `/clear` moved its pid to
    another session. With no process running it now: PushHeld (its `hold`)
    when this machine holds it (hold_now), else SendFailed("before"), as a socket
    that does not answer. PushHeld when another process runs it than the one
    looked at. Nothing is pushed either way."""
    global _PEERS
    _PEERS = None
    now = peer_for_session(session)
    if now is None:
        hold = hold_now(session)
        if hold:
            raise PushHeld("session %s is held: %s" % (session[:8], hold), hold=hold)
        raise SendFailed("before", "session %s runs in no process that answers now" % session[:8])
    if peer is not None and (str(now.get("pid")), socket_path_of(now)) != (str(peer.get("pid")),
                                                                        socket_path_of(peer)):
        raise PushHeld("session %s runs in another process than the one looked at: pushed at its next pass"
                       % session[:8])
    return now


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


class PushHeld(SendFailed):
    """A push the last hop held before anything was handed over (phase
    "before"): the delivery is left owed with no attempt counted, its
    outcome `held:…` (`held:<hold>` for a session this machine holds,
    `hold` one of HOLDS). bound_peer raises it; so, as ReachHeld, does the
    reach gate."""

    def __init__(self, why, hold=""):
        super().__init__("before", why)
        self.hold = hold

    def outcome(self):
        return hold_outcome(self.hold) if self.hold else "held:%s" % self


class ReachHeld(PushHeld):
    """A push the reach gate held (ReachGate, P5 O18 D8): nothing was handed
    over, nothing stopped or launched (phase "before"). `verdict` the
    gate's, "owed": no answer this process may act on, so the delivery is
    left owed with no attempt counted; `events` the ones it held."""

    def __init__(self, verdict, events, why):
        super().__init__(why)
        self.verdict, self.events = verdict, list(events)

    def outcome(self):
        """The delivery's outcome: `held:reach …`, which _conclude leaves
        owed with no attempt counted."""
        return "held:reach %s" % self


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
ALIAS_ANGLES = frozenset(_OPEN + _CLOSE)   # frame_alias
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
    (named by this install's path, which the recipient shares: delivery is
    always on its own machine; the plugin's bin/ may not be on its PATH, as
    in a session started before the plugin had one, or an SDK session). The tag names
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
    return "stopped" if threads_module().stopped_human(seat["current"]) or transcript_path(seat["current"]) \
        else "gone"


def state(seat):
    """A seat's one state word (seat_state)."""
    return seat_state(seat, None)


_SELF = None  # (this machine's name, {former name: its sessions}), per invocation


def machine_identity():
    """(name, former): this installation's machine name — the name its
    endpoint gave it (daemon/identity.json, on a machine cut over to RL10),
    else DAEMON_HOST, else the system's host name — and, for each name it
    wrote under before, the sessions it held under that name then ({name:
    frozenset}, oldest name first; none before the cutover)."""
    global _SELF
    if _SELF is None:
        ident = sibling_module("sminos_rl10").cutover()
        if ident is not None:
            _SELF = (ident["name"], {n: frozenset(ss) for n, ss in ident["former"].items()})
        else:
            _SELF = (os.environ.get("DAEMON_HOST") or socket.gethostname(), {})
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
    own, never an observer; and MAWS_HOLDER_SOCKET, the engine host's holder
    socket (O12 M4a), whose gate a seat never says hello on. So is
    MAWS_LAUNCHED_BY, the spawner MAWS launched a lane B session for (O12
    M11): the seat copies its parent's record instead. So is
    SMINOS_DESK_PROOF, a desk spawn's proof (O12 M7): its record keeps it,
    and no session inherits it. An EMPTY settings
    value declares the PLAIN route, enforced below the argv by dropping the
    gateway transport env too.
    """
    env = dict(os.environ)
    env.pop("RUNNER_TRACKING_ID", None)
    env.pop(records_module().LAUNCH_ENV, None)
    env.pop("MAWS_LANE", None)
    env.pop("MAWS_HOLDER_SOCKET", None)
    env.pop(records_module().LAUNCHED_ENV, None)
    env.pop(DESK_PROOF_ENV, None)
    if not settings:
        for k in gateway_env_keys():
            env.pop(k, None)
    return env


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def run_claude_bg(args, cwd, settings):
    """Run `claude --bg …` in cwd; return (short, banner). short is "" on
    failure, a launch past SMINOS_LAUNCH_TIMEOUT (300 s) included. A cwd that
    is no directory, at the look before the launch or as the engine is
    started there, launches nothing: the banner is then a NoLaunchDir, which
    each caller answers in its own way (a wake's hold `cwd`, a spawn's exit);
    an unattended worker is never silently launched somewhere else. One this
    process may not look at (read_refused: a resume, on its seat's word) is
    launched in unlooked-at."""
    if not (cwd and (read_refused(cwd) or os.path.isdir(cwd))):
        return "", NoLaunchDir(cwd)
    timeout = float(os.environ.get("SMINOS_LAUNCH_TIMEOUT") or 300)
    try:
        p = subprocess.run(["claude"] + args, cwd=cwd, env=launch_env(settings),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=timeout)
        banner = LaunchOutput(ANSI_RE.sub("", p.stdout or ""), status=p.returncode)
        if p.returncode != 0:
            return "", banner
    except subprocess.TimeoutExpired as e:
        return "", LaunchOutput(str(e), timeout=timeout)
    except (FileNotFoundError, NotADirectoryError) as e:
        # The directory gone since the look above: the engine's start there (its chdir) failed, nothing launched.
        return "", NoLaunchDir(cwd) if e.filename == cwd else LaunchOutput(str(e))
    except Exception as e:  # noqa: BLE001 — any launch failure is a failure
        return "", LaunchOutput(str(e))
    m = BANNER_RE.search(banner)   # the engine's banner line, never a title's words
    return (m.group(1) if m else ""), banner


class LaunchOutput(str):
    """What a launch printed (run_claude_bg), as text, with how it ended:
    `status` its exit status (None when it did not run to an end), `timeout`
    the bound it was stopped at (None when it was not)."""

    def __new__(cls, text, status=None, timeout=None):
        out = super().__new__(cls, text)
        out.status, out.timeout = status, timeout
        return out


class NoLaunchDir(LaunchOutput):
    """run_claude_bg's answer for a launch directory that is no directory:
    nothing was launched, and its text is what a verb exits with."""

    def __new__(cls, cwd):
        return super().__new__(cls, "launch cwd does not exist or is not a directory: %s" % cwd)


# A path inside a message (the engine's, an exception's): the text from a `/` or `~/` that starts a word or follows a
# quote, a bracket, `=` or `:` to the next space or quote.
PATH_IN_TEXT_RE = re.compile(r"(?<![^\s'\"(\[=:,])~?/[^\s'\"),\]]*")


def engine_said(text, limit=200):
    """A message from the engine as daemon.log carries it: one line, every
    path in it written `<path>`, at most `limit` characters."""
    return PATH_IN_TEXT_RE.sub("<path>", " ".join(str(text or "").split()))[:limit]


def launch_failed(flags, out):
    """What daemon.log says of a launch that failed (run_claude_bg's
    output): the names of the options it passed, never their values or the
    argument vector; its exit status or the bound it timed out at; and the
    engine's message with every path removed (none for a timeout, whose
    text is the argument vector)."""
    names = [t for t in flags if t.startswith("-")]
    how = "timed out after %gs" % out.timeout if getattr(out, "timeout", None) is not None else \
        "exit %d" % out.status if getattr(out, "status", None) is not None else "it did not run"
    said = "" if getattr(out, "timeout", None) is not None else engine_said(out)
    return "the launch failed (%s; %s)%s" % ("options " + ", ".join(names) if names else "no option", how,
                                             ": " + said if said else "")


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
    take is refused loudly rather than papered over. "stopped" once the
    turn is confirmed down, by a job list that reads; at the bound,
    "unknown" when the last listing did not read (a row missing from no
    listing is no confirmation), else "running"."""
    deadline = time.time() + float(os.environ.get("SMINOS_STOP_TIMEOUT", "30"))
    while True:
        listed = agents_refresh() is not None
        row = agent_row(short=short) if short else harness_row(s)
        running = bool(row) and normalize_state(row) in ("working", "blocked")
        if listed and not running and running_now(cur) is None:
            return "stopped"
        if time.time() >= deadline:
            return "running" if listed else "unknown"
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
    """Every session's transcript under one config dir's projects directory
    (one index each: transcript_index), by session id. A
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

    def paths(self, base, session_id, within=None):
        """The transcripts of a session found under the projects directory
        `base`, from a listing begun at most `within` seconds ago (None: the
        cache generation's, up to TRANSCRIPT_FRESH old). A process's first
        TRANSCRIPT_GLOBS asks glob for the one id instead: a verb asks a few,
        and building the index costs as much as several globs."""
        with self.lock:
            if self.at is None and self.globbed < TRANSCRIPT_GLOBS:
                self.globbed += 1
                return glob.glob(os.path.join(glob.escape(base), "*", session_id + ".jsonl"))
            age = None if self.at is None else self.clock() - self.at
            if age is None or base != self.base or (within is not None and age >= within) or (
                    self.forgot and age >= TRANSCRIPT_FRESH):
                self.refresh(base)
            return [os.path.join(base, d, session_id + ".jsonl") for d in self.by.get(session_id, ())]


_TINDEX = TranscriptIndex()   # the default config dir's
_TINDEXES = {}                # another config dir's projects directory → its index


def transcript_index(base):
    """The index of a config dir's projects directory `base`."""
    if base == os.path.join(config_dir({}), "projects"):
        return _TINDEX
    return _TINDEXES.get(base) or _TINDEXES.setdefault(base, TranscriptIndex())


def transcripts_now():
    """The transcripts read as the directories are now, for what follows: a
    caller about to act on a transcript's absence or its age (the daemon's
    sweeps, which remove what a session left once its transcript is gone)."""
    _TRANSCRIPTS.clear()
    recorded_config_dirs(fresh=True)
    for base, index in [(os.path.join(config_dir({}), "projects"), _TINDEX), *list(_TINDEXES.items())]:
        with index.lock:
            index.refresh(base)


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
    base = os.path.join(session_config_dir(session_id), "projects")
    hits = transcript_index(base).paths(base, session_id, within)
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
            seat_id = sess if UUID_RE.fullmatch(sess) else det_id
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
    return ts[:-1] + ".000Z" if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ts) else ts


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
    {{ALIAS}} and {{BY}} (the spawner, or "the operator") filled. It names
    the CLI `sminos`, which the plugin's bin/ puts on the seat's PATH."""
    try:
        with open(PREAMBLE_PATH) as f:
            t = f.read()
    except OSError:
        die("preamble template missing: %s" % PREAMBLE_PATH, 1)
    return (t.replace("{{PROJECT}}", project).replace("{{ALIAS}}", alias)
             .replace("{{BY}}", by or "the operator"))


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
    into the wrong repo with no one watching. Nor one this process may not
    look at (read_refused): the launch is made from inside its folder."""
    cwd = os.path.abspath(cwd or os.getcwd())
    if read_refused(cwd):
        die("%s: %s is in %s, which macOS asks the person about before this process reads it: run sminos %s from "
            "inside that folder" % (verb, cwd, protected_folder(cwd), verb), EXIT_USAGE)
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
    if seat_id and not finish_thread(seat_id):
        # As every transition does before its own begin: the seat's open entry first, and nothing launched over it.
        die("seat %s has an operation that could not be finished yet (%s); nothing was launched — try again once "
            "its log can be written" % (seat_id[:8], (threads_module().get(seat_id) or {}).get("pending", {}).get("op")),
            EXIT_UNKNOWN)
    if seat_id and reload_seat(seat_id) is None:
        die("seat %s was removed (its purge finished); nothing was launched" % seat_id[:8], EXIT_UNKNOWN)
    prev = reload_seat(seat_id) if seat_id else None
    if prev is not None and opened_by_human(prev["current"]):
        # Under the seat's lock (the caller's): a seat an older copy gave a session its human opened (D7) is
        # never filled fresh over it (T1's M3).
        die("%s/%s holds %s; nothing was launched" % (group, alias, human_refusal("session %s" % prev["current"][:8])),
            EXIT_UNKNOWN)
    project = seat_project({"cwd": cwd, "group": group})
    if project is None:   # its repository is in a protected folder this process may not read (read_refused)
        die("spawn: the project of %s is not read from here: its repository is in a folder macOS asks the person "
            "about; run sminos spawn from inside that folder" % cwd, EXIT_USAGE)
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
        if isinstance(banner, NoLaunchDir):
            die(banner, EXIT_USAGE)
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

    displaced, launched_entry, claimed = "", None, True
    if seat_id is None:
        rec_id = str(uuidlib.uuid4())
        meta_set(rec_id, {"uuid": rec_id, "now": "", "note": "", "created": now(), "attempts": 1,
                          "history": [], **launch})
    else:
        # A re-fill is a genuinely new session: clear the previous occupant's
        # `now` line (the orchestrator's `note` is kept), keep the seat id, its
        # `created`, and every pipeline-owned field the launch dict omits. The
        # legacy codex fields go too — the new occupant is a claude session.
        # Its thread's open entry, if one was left, is finished first. The
        # launch write is the journaled advance that owes the displaced
        # session's retirement (refill_launch), and the new session comes into
        # the thread by a second one once its id is known (below), which lifts
        # an end the seat had.
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
        write = {**launch, "now": "", "attempts": (prev["attempts"] if prev else 0) + 1, "history": history[-10:]}
        remove = tuple(k for k in drop if k not in launch) + REPLACED_DROPS
        launched_entry = refill_launch(prev, write, remove, by, log_failed) if prev and prev["current"] else None
        if launched_entry is False:
            # The seat still holds its session, whose retirement no entry owes: nothing is written over it, and
            # the session just launched, which no record names, is stopped.
            stopped = claude_stop(short)
            unlock(locks)
            die("%s: seat %s/%s could not record its launch, and still holds session %s; the session launched (%s) %s"
                % (verb, group, alias, prev["current"][:8], short,
                   "was stopped" if stopped else "could not be stopped: stop it with claude stop %s" % short), 1)
        if launched_entry is None:
            meta_set(rec_id, write, remove=remove)
            displaced = prev["current"] if prev else ""   # its `replaced` is recorded once the new session is
    polled = poll_uuid(short)
    if not polled or not UUID_RE.fullmatch(polled[0]):
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
        # The child named as every claim names a session (sminos_threads.repoint_seat): while a record its own
        # hook made meanwhile holds it (a launcher slower than the spawner's bound), the seat stays vacant until
        # its journaled absorption (below) takes it, so a cut between the two never leaves both claiming it.
        promoted = {"uuid": rec_id, "cwd": runcwd or cwd, "updated": now()}
        claimed = threads_module().repoint_seat(rec_id, {**promoted, "current": uuid})
        if not claimed:
            meta_set(rec_id, promoted)
    else:
        # `current` is the advance's, below: the record's one write that also owes the events.
        meta_set(rec_id, {"cwd": runcwd or cwd, "host": host_name(), "boot_id": boot_id(), "updated": now()})
    project = seat_project({"cwd": runcwd or cwd, "group": group})
    journaled = project is not None and not guessed(project)
    if seat_id is not None and not journaled:
        meta_set(rec_id, {"current": uuid, "updated": now()}, remove=REPLACED_DROPS)   # no log to owe its events to
    try:
        # Bound to the session the harness names for this launch, unless its
        # own SessionStart bound it already; claimed unless it claimed.
        if records.bind(launch_id, uuid) == uuid:
            records.claim(launch_id, uuid)
    except (OSError, LockBusy) as e:
        warn("the record of session %s could not be claimed: %s" % (uuid[:8], e))
    if project is not None:
        ensure_record(project, uuid, reload_seat(rec_id))
    # The thread: the seat's keys (sminos_threads.ensure), with the launch's
    # options. A launcher slower than the spawner's bound finds the record
    # its child's own hook made meanwhile, holding that one session: the
    # seat absorbs it (Interfaces §6, row 5), its joined owed under the
    # seat's stamp and that record deleted last.
    threads = threads_module()
    other = threads.thread_of(uuid)
    if not threads.absorbable(other, uuid):
        other = None
    if journaled:
        try:
            threads.ensure(uuid, seat=reload_seat(rec_id), project=project)
        except (OSError, LockBusy) as e:
            warn("the thread record of seat %s could not be written: %s" % (rec_id[:8], e or "its lock is busy"))
    if displaced and displaced != uuid:
        # A seat whose session the launch's advance could not owe a retirement to (no log here, or no thread).
        record("the displaced session %s stays a member until a reading verb finds it no longer runs"
               % displaced[:8], seat_project(prev), displaced, "retired", by=by, reason="replaced")
    fields = joined_fields(alias, "seat", runcwd or cwd, worktree or "", role or "", rec_id, by, "seat", session=uuid)
    launch_argv = ["claude"] + claude_args(alias, model, merged, effort, worktree, permission_mode)
    launched = threads.launch_of(runcwd or cwd, threads.launch_options(launch_argv),
                                 threads.launch_dropped(launch_argv))
    if journaled and (seat_id is not None or other is not None or not claimed):
        # A refill (Interfaces §6, row 6): the thread keeps its id, alias and
        # in-charge line, and takes its new session by a journaled write that
        # owes its `joined` under the seat's stamp, the displaced session's
        # `retired` (reason `replaced`, no `to`) owed by the launch's
        # (refill_launch); the launch's directory and options are in the same
        # write, so a replay keeps them. Its owners and reach are its own
        # launch's (ensure_record above), never its predecessor's.
        other_id = other["thread"] if other is not None else None
        fills = seat_id is not None or not claimed   # the advance is what makes the session the seat's current one
        poll = dict(fields={"current": uuid, "launch": launched} if fills else {"launch": launched},
                    remove=REPLACED_DROPS if seat_id is not None else (), other=other_id, absorbs=True)
        try:
            for _ in range(3):
                began = []
                thread_transition(project, rec_id, "absorb" if other_id else "advance",
                                  [{"kind": "joined", "session": uuid, **fields}], required=True, began=began,
                                  guard=lambda t: t["current"] == ("" if fills else uuid) and (
                                      other_id is None or threads.absorbable(threads.get(other_id), uuid)),
                                  **poll)
                if began:
                    break
                fresh = threads.get(rec_id) or {}
                behind = fresh.get("pending")
                holder = threads.thread_of(uuid)
                if not behind and launched_entry is not None and fresh.get("current") == "" \
                        and (holder is None or holder["thread"] == rec_id or holder["thread"] == other_id):
                    continue   # this launch's entry was finished meanwhile, and the seat is still vacant: again
                if not behind or launched_entry is None or behind["id"] != launched_entry:
                    log_failed.append("the seat's record did not take session %s: %s" % (
                        uuid[:8], "another record holds it" if not behind else "another operation's entry is open"))
                    break
                # This launch's own entry could not finish (its retirement is still owed): the poll's advance
                # waits behind it, recorded in it, and is begun by the write that clears it (sminos_threads.follow).
                # One finished meanwhile is gone by then: the advance is begun again.
                if threads.follow(rec_id, launched_entry, "absorb" if other_id else "advance", project,
                                  [{"kind": "joined", "session": uuid, **fields}], **poll):
                    log_failed.append("session %s's joined waits behind the displaced session's retirement — "
                                      "the next reading verb finishes both" % uuid[:8])
                    break
        except LogWriteFailed as e:
            log_failed.append("%s — the next reading verb finishes it" % e)
    elif not claimed:
        log_failed.append("the seat's record did not take session %s: another record holds it" % uuid[:8])
    else:
        record("the seat re-joins its project on the next reading verb, but its spawner (by %s) is not recorded"
               % (by or "the operator"), project, uuid, "joined", **fields)
        if journaled:
            try:
                threads.update(rec_id, {"launch": launched})
            except (OSError, LockBusy) as e:
                warn("the launch of seat %s was not noted: %s" % (rec_id[:8], e or "its lock is busy"))
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
      its record is (or when it has none); its access and shares copied
      too, so a spawn never widens reach (O18 D10), and private with no
      shares when its record file cannot be read (its policy unknown); the
      child's policyRev its own, from 0;
    - from an operator's terminal: the machine's owners, origin
      `sminos-spawn`; the default policy, as for a desk spawn.
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
        parent = records.read(caller)
        policy = {"access": "private", "shares": []} if parent is None and records.unreadable(caller) \
            else {k: v for k, v in records.policy_carried(parent or {}).items() if k != "policyRev"}
        parent = parent or records.default_provenance()
        return {**{k: parent[k] for k in records.PROVENANCE}, **policy,
                "origin": {"kind": "sminos-spawn", "spawnerSession": caller},
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
            die("seat %s/%s: the previous occupant (session %s) still answers — stop it first%s" % (
                group, alias, existing["current"][:8], "" if live == "retired" else ", or use sminos resume"),
                EXIT_UNKNOWN)
        if existing["engine"] == "codex" and existing["status"] in ("working", "blocked"):
            die("seat %s/%s is a legacy codex-CLI worker still marked %s — retire it before re-filling" % (
                group, alias, existing["status"]), EXIT_UNKNOWN)
        # vacant / stopped / gone / retired → re-fill this very seat, keeping its
        # id and the seat-describing pipeline fields. The board pipeline's
        # retire-then-respawn of a deterministic alias (review-pr-<n>) lands
        # here instead of erroring.
    else:
        # The alias of a session its human opened, a member of the project (stopped ones hold theirs, D1), is
        # not spawned onto (T1's M3).
        project = seat_project({"cwd": cwd, "group": group})
        held = next((m for m in (members(project) if project is not None else [])
                     if m.alias == alias and (m.opened == "human" or m.local and opened_by_human(m.session))),
                    None)
        if held is not None:
            die("%s is the alias of a session its human opened (%s, %s), a member of %s: its sessions are its "
                "human's to open — spawn under another alias" % (alias, held.short, held.state, project.name),
                EXIT_UNKNOWN)
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
    if session and not UUID_RE.fullmatch(session):
        die("--session must be a session uuid (8-4-4-4-12 hex): %s" % session)
    locks = lock_names([seat_key(a.group, a.alias)])
    if session:
        thread = threads_module().thread_of(session)
        if thread is not None and thread["opened"] == "human":
            unlock(locks)
            die("session %s is a session its human opened, and its record already keeps it: it takes no seat"
                % session[:8], EXIT_UNKNOWN)
    existing = [s for s in seats(a.group) if s["alias"] == a.alias]
    if existing and (why := displace_refusal(existing[0], session)):
        unlock(locks)
        die(why, EXIT_UNKNOWN)
    # A registered session's short is whatever the harness shows for it right
    # now (a `seat add --session` seat was never spawned by sminos, so nothing
    # else records it); absent a row it is cleared, never left stale.
    row = agent_row(session_id=session) if session else None
    short = str((row or {}).get("id") or "")
    refill, displaced_stamp = None, ""
    if existing:
        s = existing[0]
        seat_id = s["seat_id"]
        if not finish_thread(seat_id):   # an entry left open is finished before the record changes
            unlock(locks)
            die("seat %s/%s holds a transition not finished yet (its events or settlement could not be completed "
                "now): nothing was changed, and the next reading verb finishes it" % (a.group, a.alias), 1)
        # What the replay left is what is displaced: its occupant read again, and checked again.
        s = reload_seat(seat_id)
        if s is None:
            unlock(locks)
            die("seat %s/%s was removed (a purge of it, left open, was finished): nothing was changed; run it again "
                "to add the seat anew" % (a.group, a.alias), EXIT_UNKNOWN)
        if (why := displace_refusal(s, session)):
            unlock(locks)
            die(why, EXIT_UNKNOWN)
        existing = [s]
        fields = {"role": a.role if a.role is not None else s["role"],
                  "brief": a.brief if a.brief is not None else s["brief"], "updated": now()}
        if session:
            fields.update({"short": short, "status": "idle", "host": host_name(), "boot_id": boot_id()})
            project = seat_project(reload_seat(seat_id) or s)
            if session != s["current"] and project is not None and not guessed(project) \
                    and threads_module().lane_a(session):
                refill = project   # `current` is the advance's (below); a lane B session's seat is no thread
            elif session != s["current"]:
                # No journal (a project not read here, a lane B session), but the claim is any claim's: under both
                # stores' locks, refused when another record holds the session or an entry was begun since the
                # one finished above (sminos_threads.repoint_seat). The displaced session's retirement keeps the
                # stamp it had, though a lane B session's seat is no thread once it takes it.
                displaced_stamp = threads_module().stamp(s["current"]) if s["current"] else ""
                if not threads_module().repoint_seat(seat_id, {**fields, "current": session}, expect=s["current"]):
                    unlock(locks)
                    now_ = reload_seat(seat_id) or {}
                    if now_.get("pending"):
                        die("seat %s/%s holds a transition begun meanwhile: nothing was changed, and the next "
                            "reading verb finishes it" % (a.group, a.alias), 1)
                    if now_.get("current") != s["current"]:
                        die("seat %s/%s changed meanwhile (it holds %s now): nothing was changed; run it again"
                            % (a.group, a.alias, str(now_.get("current") or "no session")[:8]), EXIT_UNKNOWN)
                    die("session %s is another thread's (a record its human opened, or another seat, holds it): it "
                        "takes no seat" % session[:8], EXIT_UNKNOWN)
                fields = None
            if refill is not None:
                refill = (refill, fields)   # written by the refill's own advance, with `current`, or not at all
                fields = None
        if fields is not None and not meta_set_if(seat_id, fields, lambda data: keep_end(data, fields, session)):
            unlock(locks)
            die("seat %s/%s holds a transition begun meanwhile, or is gone: nothing was changed" % (a.group, a.alias), 1)
    else:
        seat_id = session if session else str(uuidlib.uuid4())
        if os.path.exists(meta_path(seat_id)):
            die("a seat record for session %s already exists (%s/%s)" % (
                session, meta_get(seat_id, "group"), meta_get(seat_id, "alias") or meta_get(seat_id, "name")), EXIT_UNKNOWN)
        made = {
            "uuid": seat_id, "current": session, "short": short, "name": a.alias, "alias": a.alias,
            "group": a.group, "role": a.role or "",
            "brief": a.brief or "", "task": "", "now": "", "note": "", "cwd": os.getcwd(), "worktree": "",
            "model": "", "settings": "", "effort": "", "status": "idle" if session else "vacant",
            "host": host_name() if session else "", "boot_id": boot_id() if session else "",
            "created": now(), "updated": now(), "turns": "0", "preamble": "1", "attempts": 1, "history": []}
        if not session:
            meta_set(seat_id, made)
        elif not threads_module().claim_seat(seat_id, made):
            unlock(locks)
            die("session %s is another thread's (a record its human opened, or another seat, holds it): it takes "
                "no seat" % session[:8], EXIT_UNKNOWN)
    if refill is not None:
        # The session joins as this seat, displacing the one it held, as by a
        # fill: the refill's journaled advance (Interfaces §6, row 6).
        refill_seat(refill[0], reload_seat(seat_id), existing[0]["current"], session, caller_alias(), refill[1])
        if (reload_seat(seat_id) or {}).get("current") != session:
            unlock(locks)
            die("session %s is another thread's (a record its human opened, or another seat, holds it): it takes "
                "no seat" % session[:8], EXIT_UNKNOWN)
    elif session:
        # The session joins as this seat; a session the seat held before is
        # displaced, as by a fill.
        if existing and existing[0]["current"] and existing[0]["current"] != session:
            lifecycle(seat_project(existing[0]), existing[0]["current"], "retired", by=caller_alias(),
                      reason="replaced", **({"thread": displaced_stamp} if displaced_stamp else {}))
        join_seat(reload_seat(seat_id), by=caller_alias())
    unlock(locks)
    retired = bool(session) and (reload_seat(seat_id) or {}).get("status") == "retired"
    print("seat %s/%s %s (%s)%s" % (a.group, a.alias, "updated" if existing else "added",
                                    ("session: " + session) if session else "vacant",
                                    "; it stays retired: a fill returns it" if retired else ""))


def displace_refusal(s, session):
    """Why `seat add --session` may not put `session` in seat `s`'s place,
    or "": its occupant still runs (repointing a seat is how a record
    forgets which process it describes: that process would run on with
    nothing in the fleet naming it), or is a session its human opened,
    which its record keeps (D7: an older copy's seat of it is never its
    authority). Whether it runs is its process's, read afresh
    (running_now): whether its inbox answers yet is delivery's question."""
    cur = s["current"]
    if not session or not cur or session == cur:
        return ""
    peer = running_now(cur)
    if peer:
        return ("seat %s/%s still holds a live session (%s, pid %s) — repointing it would strand that process "
                "outside the fleet; retire or remove the seat first" % (s["group"], s["alias"], cur[:8], peer.get("pid")))
    if opened_by_human(cur):
        return ("seat %s/%s holds session %s, a session its human opened, which its record keeps: seat add does not "
                "displace it" % (s["group"], s["alias"], cur[:8]))
    return ""


def refill_launch(seat, fields, remove, by, failed):
    """The launch write of a refill onto a seat that holds a session
    (spawn_fresh): the launch's fields, and the displaced session's
    `retired`, reason `replaced`, no `to`, owed in that session's own
    project, by one journaled advance of the seat's record (Interfaces §6,
    row 6), so no write detaches the session the seat held but the one
    that owes its retirement, whichever project the refill moves the seat
    to. The seat's `current` is then "" until the new session's id is known
    (the first turn's lookup by short reads a seat so: caller_seat), and the
    advance at poll time owes the new session's `joined`. The id of the
    advance's entry when it was begun (a failed append is in `failed`, the
    entry left open: the poll's advance may queue behind it alone); None for
    a seat whose session has no log here to owe it to, or that is no thread
    (a lane B session's): the caller writes the launch's fields as before
    threads; False when it applies and was not begun (its record could not
    be written, or changed meanwhile): the caller writes nothing over the
    session the seat holds."""
    old, threads = seat["current"], threads_module()
    project = seat_project(seat)
    if project is None or guessed(project):
        return None
    began = []
    try:
        if threads.ensure(old, seat=seat, project=project) is None:
            return None
        # What was held for the session displaced is settled in the entry (T2's M3), as a hand-off's advance
        # settles it: a seat given that session again holds no debt from before.
        thread_transition(project, seat["seat_id"], "advance",
                          [{"kind": "retired", "session": old, "by": by, "reason": "replaced"}],
                          required=True, began=began, fields=fields, remove=remove,
                          guard=lambda t: t["current"] == old, settle=old)
    except LogWriteFailed as e:
        failed.append("%s — the next reading verb finishes it" % e)
    except (OSError, LockBusy) as e:
        warn("the thread record of seat %s could not be written: %s" % (seat["seat_id"][:8], e or "its lock is busy"))
    # The entry as begin wrote it, whichever process appended its events or cleared it.
    return began[0]["id"] if began else False


def refill_seat(project, seat, old, new, by, edit=None):
    """A seat given another session by `seat add --session` (Interfaces §6,
    row 6): the thread keeps its id, alias and in-charge line, and takes
    `new` by one journaled write of the seat record (`current`, `sessions`,
    an end lifted, and the seat's own fields the verb changes, `edit`, so
    none is written when the claim is refused), which owes `old`'s
    `retired`, reason `replaced`, no `to` (when it held one), and `new`'s
    `joined`, one stamp. `new`'s owners and reach are its own
    (ensure_record, never `old`'s). A seat from before threads is adopted
    first, its earlier sessions found."""
    threads = threads_module()
    edit = dict(edit or {})
    ensure_record(project, new, seat)
    threads.ensure(old or new, seat=seat, project=project)   # its keys, and its earlier sessions found
    role = edit.get("role", seat["role"])
    fields = joined_fields(seat["alias"], "seat", seat_cwd(seat, fresh=True), seat["worktree"], role,
                           seat["seat_id"], by, "seat", session=new)
    owed = [{"kind": "retired", "session": old, "by": by, "reason": "replaced"}] if old else []
    # What was held for `old` is settled in the entry, as a hand-off's advance settles it (T2's M3).
    return thread_transition(project, seat["seat_id"], "advance", owed + [{"kind": "joined", "session": new, **fields}],
                             required=True, fields={**edit, "current": new}, remove=REPLACED_DROPS,
                             guard=lambda t: t["current"] == old, **({"settle": old} if old else {}))


def legacy_codex_refusal(s):
    return ("seat %s/%s is a legacy codex-CLI worker; its resume path was retired — "
            "retire or remove the seat" % (s["group"], s["alias"]))


def refuse_codex(s):
    if s["engine"] == "codex":
        die(legacy_codex_refusal(s), EXIT_UNKNOWN)


def cmd_fill(a):
    s0, bound, opened = resolve_seat_or_opened(a.seat, "fill it")
    if opened is not None:
        m = opened[1]
        if not a.resume:
            die("%s; a fresh fill of it is refused, and nothing was recorded" % human_refusal(m.alias), EXIT_UNKNOWN)
        warn_resume_flags(a)
        rec = running_now(m.session) if not has_ended(m) else None
        if rec is not None:
            # A live one is refused as a filled seat is (T2's §6), nothing recorded: send reaches it.
            die("%s is filled (%s) — use sminos send" % (m.alias, peer_state(rec)), EXIT_UNKNOWN)
        verb_to_thread(opened[0], m, a.task, a.wait, "filled")
        return
    refuse_codex(s0)
    # Re-load under the lock and act on the fresh values: between resolve and
    # lock the seat could have been re-filled or retired (and a bound session replaced: refused).
    locks, s = locked_fresh(s0, "fill", bound)
    refuse_codex(s)
    live = state(s)
    if live in FILLED:
        die("seat %s/%s is filled (%s) — use sminos send" % (s["group"], s["alias"], live), EXIT_UNKNOWN)
    if peer_for_session(s["current"]):  # a retired seat whose session still runs
        die("seat %s/%s: the previous occupant (session %s) still answers — stop it first%s" % (
            s["group"], s["alias"], s["current"][:8], "" if live == "retired" else ", or use sminos resume"),
            EXIT_UNKNOWN)
    if a.resume:
        if not s["current"]:
            die("seat %s/%s has no session to resume — fill it fresh (without --resume)" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        warn_resume_flags(a)
        if live != "retired":
            # A stopped seat: its task recorded first, as `send` records one, then the wake and the push (T2's M2).
            unlock(locks)
            deliver_verb(s, s["current"], a.task, a.wait, "filled")
            return
        # A retired seat returns: the wake first, which returns it (its W8, journaled) once its process runs; then
        # the task, recorded after the return's entry was begun (a return settles what was addressed before it)
        # and delivered as `send` delivers it, counted as the woken push it is. What can refuse the task without
        # asking anyone is checked before anything starts (its stream; a seat whose project is not read here, where
        # no return could be journaled); a wake that does not make it live leaves it retired, nothing recorded.
        project = seat_project(s)   # none read here: resume_session refuses the return, which nothing could record
        # The stream the task's event would go under (D4, D10): chosen here, appended after the return.
        refusal = stream_choice(project, os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
                                [{"session": s["current"], "alias": s["alias"]}],
                                "send not delivered: it could not be recorded in %s's log" % project.name)[1] \
            if project is not None and not guessed(project) else None
        if refusal:
            unlock(locks)
            die(*refusal)
        try:
            woke = resume_session(s, locks, returns=True)
        except ResumeHeld as e:
            e.record(a.task)   # the session its human opened is its own record's to wake (T2's M4)
            return
        except ResumeRefused as e:
            unlock(locks)
            die(e.message, e.code)
        if not woke.live:
            unlock(locks)
            die("seat %s/%s was not woken: %s; nothing was recorded" % (s["group"], s["alias"], wake_words(woke.why)),
                EXIT_UNKNOWN if woke.why in ("gone", "lane", "ended", "transcript") else
                EXIT_USAGE if woke.why == "cwd" else 1)
        # The seat's lifecycle lock kept from the return through its task's record and push (send_to_seat takes it
        # over): no other verb's change of the seat comes between them.
        deliver_verb(reload_seat(s["seat_id"]) or s, s["current"], a.task, a.wait, "filled", woke=True, locks=locks)
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


# ------------------------------------------------------------ the wake (T2's M2, the plan's §3)


class WakeResult(NamedTuple):
    """What a wake answers (§3): `live`, a process holds the session now
    (launched here or found); `why`, "" or why not; `short`, the job's short
    when this call launched it."""
    live: bool
    why: str = ""
    short: str = ""


# The engine's three notes of a copy (E14), each a line of its own, read whole: the session it names and the copy's
# short (copy_note). A title in a banner can say anything; only these lines are the engine's word.
COPY_NOTES = (
    ("open", re.compile(r"note: session ([0-9a-f]{8}) is open in another Claude Code process, so this started a copy "
                        r"as ([0-9a-f]{8})\. The original conversation is unchanged\.")),
    ("running", re.compile(r"note: session ([0-9a-f]{8}) is already running in the background, so this started a "
                           r"copy as ([0-9a-f]{8})\. `claude attach \1` opens the original\.")),
    ("saved", re.compile(r"note: background session ([0-9a-f]{8}) keeps its own saved options, so the flags you "
                         r"passed started a copy as ([0-9a-f]{8})\. Without flags, the same command continues \1 "
                         r"itself\.")),
)
BANNER_RE = re.compile(r"^backgrounded · ([0-9a-f]+)", re.M)


def job_holds(session):
    """E5's second signal, the job list read afresh: True when it lists a
    job of the session whose process runs, False when none, None when the
    list cannot be read (a held session, never a free one)."""
    rows = agents_refresh()
    if rows is None:
        return None
    return any(isinstance(r, dict) and r.get("sessionId") == session and r.get("pid") and pid_alive(r.get("pid"))
               for r in rows)


def bridge_holds(session):
    """E5's third signal: sminos's bridge socket for the session answers."""
    return socket_ok(os.path.join(root(), "bridge", session + ".sock"))


def bridge_spare(session):
    """Whether the process sminos's bridge for the session serves is a spare
    by its own record: the one its child names (sminos_bridge.parent_path),
    in whatever config dir that process runs, registered here or not. A
    record not there yet (a session whose engine has not written it) is no
    spare: the bridge's signal stands."""
    try:
        named = json_at(os.path.join(root(), "bridge", session + ".parent")).get("record")
        rec = json_at(named) if isinstance(named, str) else None
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(rec, dict) and rec.get("sessionId") == session and engine_spare(rec) \
        and pid_alive(rec.get("pid"))


def process_holds(session):
    """(held, readable): whether a process holds the session by E5's three
    signals (the engine's record of a process, the job list, the bridge's
    socket), each read afresh; `readable` False when one could not be read
    (the job list failing) and none says held. A spare's bridge answering
    holds nothing: its parent's record, as its child names it, says spare
    (bridge_spare), or a record of a dir known here does (spare_now)."""
    if running_now(session) is not None or (bridge_holds(session) and not bridge_spare(session)
                                            and not spare_now(session)):
        return True, True
    job = job_holds(session)
    return bool(job), job is not None


def live_now(session):
    """A process holds the session and its inbox answers, read afresh."""
    forget_caches()
    return peer_for_session(session) is not None


def wake_line_for(peer, session):
    """(thread id, line) when the record of the session's thread holds a
    wake's line for it (`waking.line`, T2's §7) that belongs to the process
    that holds it, `peer`: the text pushed to it now closes with that line
    (push_live). The line belongs to the launch that wrote it (line_owner),
    and is otherwise removed and not sent: met for a process its human
    started (a terminal reopened the session), one of another job, one
    started before the line was written, or with no job at all (its launch
    never was accepted). None otherwise, and for a line whose launch is
    still in flight that is not this process's, which is left for it."""
    threads = threads_module()
    try:
        t = threads.thread_of(session, ended=False)
        line = threads.waking(t, session).get("line") if t is not None and t["current"] == session else None
        if not isinstance(line, dict) or not line.get("id"):
            return None
        owner = line_owner(t["thread"], line, peer or {})
        if owner == "left":
            return None
        if owner != "this":
            threads.wake_line_sent(t["thread"], session, line["id"])
            return None
    except (OSError, LockBusy):
        return None
    return t["thread"], line


def line_owner(thread_id, line, peer):
    """Whether a wake's line is the process `peer`'s: "this", "other"
    (removed), or "left" (its launch still in flight, the line kept for
    it). Only a background process (its record's `kind` `bg`) holds a
    line, and only one its launch started: of the job the launch's banner
    named (the line's `short`, the record's `jobId`) and claimed no earlier
    than the line was written (its `at`, against the record's start,
    process_started, at a whole second's precision). The short is the
    session's own job, which a background resume of the same id by hand
    shares, so it binds the line to a background run of this session, and
    the start to one since the line was written; what tells this launch's
    worker from a later one of the same job is that a launch that never
    went live is counted failed with its line removed (§3, the accepted
    job). A line with no short yet (the engine's record of the process and
    its inbox precede the banner, E18) is the process's only while a launch
    holds the thread's wake lock (launch_in_flight) and the process started
    since the line was written: the first text pushed to it carries the
    line, even another sender's before the launcher read its banner."""
    if str(peer.get("kind") or "") != "bg":
        return "other"
    started, at = process_started(peer), _ts_epoch(line.get("at"))
    since = None if started is None or at is None else int(started) >= int(at)
    if line.get("short"):
        return "this" if str(peer.get("jobId") or "") == line["short"] and since is not False else "other"
    if not launch_in_flight(thread_id):
        return "other"
    return "this" if since else "left"


def launch_in_flight(thread_id):
    """Whether a launch holds the thread's wake lock now, in another thread
    or process: the lock busy and its file naming a launch (LAUNCH_HOLD).
    Never waits. A hold this thread has is no launch in flight: the wake it
    took it for has returned, and its line is bound or gone."""
    if wake_held(thread_id) is not None:
        return False
    try:
        with open(wake_lock_path(thread_id)) as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                return f.read().strip().startswith(LAUNCH_HOLD.split("%", 1)[0])
            return False   # not held: let go as the file closes
    except OSError:
        return False


def wake_line_pushed(thread_id, session, line):
    """The line pushed (push_live): removed, only while it is still that wake's."""
    wake_line_dropped(thread_id, session, line["id"])


def wake_line_dropped(thread_id, session, line_id):
    """The line `line_id` removed, only while it is still that one: pushed,
    or its launch made no process it belongs to (a copy removed)."""
    try:
        threads_module().wake_line_sent(thread_id, session, line_id)
    except (OSError, LockBusy) as e:
        warn("the wake's line for %s was not cleared: %s" % (session[:8], e or "its lock is busy"))


def copy_note(banner, session, short):
    """The engine's note of a copy in a wake's output (E14): ("open" |
    "running" | "saved", the copy's short) for a line that is one of its
    three notes whole, names this session and names as the copy the job
    this launch's banner named (`short`); None otherwise, whatever else
    the output says."""
    for line in banner.splitlines():
        line = line.strip()
        for kind, rx in COPY_NOTES:
            m = rx.fullmatch(line)
            if m and m.group(1) == session[:8] and m.group(2) == short:
                return kind, short
    return None


def job_of(short):
    """The job list's entry of `short`, read afresh: (readable, entry or None)."""
    rows = agents_refresh()
    if rows is None:
        return False, None
    return True, next((r for r in rows if isinstance(r, dict) and r.get("id") == short), None)


def remove_copy(short, cause):
    """A copy the wake's launch made, removed (§3): `claude rm`, its removal
    confirmed only by a job list that reads and no longer lists it; one
    that cannot be removed or confirmed is stopped and said in daemon.log.
    Only a job the launch's own banner named and the engine's word or its
    entry shows is another session's is ever passed here."""
    try:
        p = subprocess.run(["claude", "rm", short], capture_output=True, text=True, timeout=60)
        removed = p.returncode == 0
    except Exception:  # noqa: BLE001 — a removal that cannot run is one that failed
        removed = False
    readable, entry = job_of(short)
    if removed and readable and entry is None:
        return True
    if claude_stop(short):
        daemon_log("a wake's copy %s (%s) could not be removed; it was stopped" % (short, cause))
    else:
        daemon_log("a wake's copy %s (%s) could not be removed, and claude stop failed: it may still run"
                   % (short, cause))
    return False


def background_job(row, session):
    """Whether a job list's entry is a background job of `session`, positively:
    its session id is the session's and its kind is the engine's background
    one. A terminal's row is never one (a session a terminal holds is
    delivered to or left, never stopped)."""
    return isinstance(row, dict) and row.get("sessionId") == session and row.get("kind") == "background" \
        and bool(row.get("id"))


def stop_lingering(session, row):
    """W3: the background job of the session (background_job) that the job
    list shows working or blocked while no process holds the session,
    stopped and waited for (wait_stopped); only when the session's own row
    is there. "" when nothing is in the way; "unknown" when the job list
    does not read, here or through the stop's confirmation (the latest job
    signal unknown: nothing is launched on it); "live" when a process holds
    the session again since W2 (nothing is stopped under it); "failed" when
    the job could not be stopped."""
    if not isinstance(row, dict):
        return ""
    rows = agents_refresh()
    if rows is None:
        return "unknown"
    for r in rows:
        if background_job(r, session) and normalize_state(r) in ("working", "blocked"):
            if running_now(session) is not None:
                return "live"
            if not claude_stop(r["id"]):
                return "failed"
            stopped = wait_stopped({"current": session, "short": ""}, r["id"], session)
            if stopped != "stopped":
                return "unknown" if stopped == "unknown" else "failed"
    return ""


def own_failed_row(session):
    """§3's one removable row: the session's row there now reads failed and
    its `detail` begins `exit 1 before init` (E20). The caller has read that
    W4 found no row and that the banner's job is this session's and reads
    failed."""
    row = wake_module().row_of(session)
    return isinstance(row, dict) and wake_module().row_failed(row) \
        and str(row.get("detail") or "").startswith("exit 1 before init")


def wake(record, session, due=False, returns=False, on_live=None):
    """The wake (D2, the plan's §3): the one function that starts a process
    for a stopped thread, either kind of record, and hands it nothing. Its
    steps W1 to W8 under the thread's wake lock; what it found, as §3's
    table says, in a WakeResult. Nothing is settled or pushed here: the
    caller delivers to a session that is live, and holds what it brought
    otherwise. `record`: the thread the caller chose (read again here by its
    id); `due`: a sender's or a verb's own call, which no schedule holds
    back; `returns`: `fill --resume` of the seat it names, the one caller
    for which an ended record is woken, a spawned thread's alone;
    `on_live(short)`: called at W8, under the lock and with its hold, for
    what the caller writes once the process is live (a seat's fields, a
    retired seat's return)."""
    tid = record["thread"]
    mine = wake_held(tid) is None   # a hold this thread has already (its caller's) is its caller's to end
    hold, why = launch_hold(tid)
    if hold is None:
        return WakeResult(True) if live_now(session) else WakeResult(False, why)   # rows 1 and 2
    try:
        return _wake_held(tid, session, due, returns, on_live)
    finally:
        if mine:
            hold.release()


def launch_hold(thread_id):
    """W1: the thread's wake lock for a wake, by wake_lock's bounded poll,
    named as a launch's (LAUNCH_HOLD); the one this thread holds already
    when it has one. A caller that must act before the wake under the same
    hold (`resume`'s stop of a live turn) or after it (the push to the
    woken process) takes it here and ends it; the wake then uses it and
    leaves it held. (hold, "") or (None, why)."""
    return wake_lock(thread_id, holder=LAUNCH_HOLD % (os.getpid(), now()))


def _wake_thread(tid, session, returns):
    """W2's reads ahead of the process, in §3's order: (the record, "") to
    go on, or (None, the result's `why`) for rows 3 to 6."""
    threads = threads_module()
    forget_caches()
    try:
        if threads.unreadable(tid) or records_module().unreadable(session):
            return None, "unknown"                                       # row 3
        t = threads.get(tid)
        owner = threads.thread_of(session)
    except (OSError, ValueError):
        return None, "unknown"
    if t is None or owner is None or owner["thread"] != tid or t["current"] != session or threads.reservation(t):
        return None, "gone"                                              # row 3a
    if threads.record_ended(t) and not (returns and t["opened"] == "spawned"):
        return None, "ended"                                             # row 4: a return is a seat's alone
    if t.get("pending"):
        return None, "pending"                                           # row 5
    if not threads.lane_a(session):
        return None, "lane"                                              # row 6
    return t, ""


def wake_refusal(tid, session, returns=False):
    """What `resume` reads under the wake lock it took before it stops a
    live turn (T2's §6), so that a turn is stopped only for a wake that
    would start it again: "" then, else why not. W2's reads in §3's order
    but the process, which runs (it is the turn to stop): the record, the
    session's thread and its reservation, its end, an open entry, the lane,
    a reason of not_woken with the last turn read whole, and a job an
    earlier wake accepted that is still within its grace (`starting`: never
    stopped, and the wake that follows finds its process)."""
    t, why = _wake_thread(tid, session, returns)
    if t is None:
        return why
    return wake_module().not_woken(t, session, whole=True) \
        or ("starting" if wake_module().starting(t, session) is not None else "")


def _wake_found(tid, session, due, returns, flagless):
    """W2: what the wake reads again under its lock, in §3's order: (the
    record, "") to go on, or (None, the result's `why`; "live" for row 7)."""
    wm = wake_module()
    t, why = _wake_thread(tid, session, returns)
    if t is None:
        return None, why
    held, readable = process_holds(session)
    if held:
        return None, "live"                                              # row 7
    if not readable:
        return None, "unknown"                                           # row 8
    reason = wm.not_woken(t, session, whole=True, flagless=flagless)
    if reason:
        return None, reason                                              # row 9
    if not due and not wm.wake_due(t, session):
        return None, "failed"                                            # row 10
    return t, ""


def _wake_held(tid, session, due, returns, on_live):
    threads, wm = threads_module(), wake_module()
    flagless = saved = False
    while True:
        t, why = _wake_found(tid, session, due, returns, flagless)
        if t is None:
            return WakeResult(why == "live", "" if why == "live" else why)
        job = threads.waking(t, session).get("job")
        if isinstance(job, dict) and job.get("short"):
            if wm.starting(t, session) is not None:
                # A job an earlier wake's banner named, its process not seen yet and its grace not passed: one
                # still starting while the job list shows it working, which no wake stops as lingering or launches
                # beside.
                readable, entry = job_of(job["short"])
                if not readable:
                    return WakeResult(False, "unknown")
                if entry is not None and str(entry.get("sessionId") or session) == session \
                        and normalize_state(entry) in ("working", "blocked"):
                    return WakeResult(False, "starting")
            # Dead, failed or gone, or its grace passed while no process holds the session (W2): that launch
            # failed, counted as one, so §4's schedule holds the next; this wake goes on only while one is due.
            if not accepted_failed(tid, session, job):
                continue   # a process's hook cleared it first: W2 again, which reads what holds the session now
            if not due and not wm.wake_due(threads.get(tid), session):
                return WakeResult(False, "failed")
        row = wm.row_of(session)
        lingering = stop_lingering(session, row)                         # W3
        if lingering == "live":
            return WakeResult(True)   # a process holds it again, this wake's launch none of it: nothing of W8
        if lingering == "unknown":
            return WakeResult(False, "unknown")   # row 8's answer: passed on, no attempt counted
        if lingering:
            return _wake_failed(tid, session, None, "its earlier job could not be stopped")
        first = not flagless and wm.passes_flags(t, session, row)       # W4: row 12's retry passes none
        flags, not_carried = wm.first_wake(t, session) if first else ([], [])
        if first and wm.asks(wm.options_mode(flags)):
            # The launch checks its own flags: W2 read the policy and the row once, the flags read them again (a
            # ceiling lowered, a row gone since), and a launch is never made in a mode that asks for approval.
            return WakeResult(False, "mode")
        turn = wm.last_turn(session, whole=True)
        note = wm.line_note(first, flags if first else wm.row_options(row) if isinstance(row, dict) else [], turn,
                            not_carried, t["opened"])
        try:
            written = threads.wake_line(tid, session, note)
        except (OSError, LockBusy):
            written = False
        if not written:
            # Nothing is launched on a record this wake could not write (an entry an older copy opened since W2,
            # with no wake lock): the table's answer for what is found now, else `unknown`.
            _, why = _wake_found(tid, session, due, returns, flagless)
            return WakeResult(why == "live", "" if why == "live" else why or "unknown")
        seat = reload_seat(tid) if t["opened"] == "spawned" else None
        settings = seat["settings"] if seat is not None else wm.option(flags, "--settings")
        short, banner = run_claude_bg(wm.wake_argv(session, flags), wm.thread_cwd(t), settings)   # W5, W6
        if isinstance(banner, NoLaunchDir):
            # Gone since W2 read it, as the launch boundary found it: the hold not_woken answers for it, never an
            # exit, which no wake makes (a deliverer, the daemon or the uplink, goes on past it).
            wake_line_dropped(tid, session, note["id"])
            return WakeResult(False, "cwd")
        if not short:                                                    # row 14
            rec = running_now(session)
            if rec is not None and str(rec.get("kind") or "") == "bg":
                # The launch timed out or lost its banner, and a background process of the session runs: this
                # launch's, positively, so W8 as for any live launch, its short the one its record names, if any,
                # and its line bound to that job.
                job = str(rec.get("jobId") or "")
                if job:
                    try:
                        threads.wake_line_bound(tid, session, note["id"], job)
                    except (OSError, LockBusy) as e:
                        warn("the wake of %s did not bind its line: %s" % (session[:8], e or "its lock is busy"))
                return _wake_live(tid, session, saved, on_live, job)
            if rec is not None or process_holds(session)[0]:
                wake_line_dropped(tid, session, note["id"])   # held by a process this launch did not start: live,
                return WakeResult(True)                        # nothing of W8, and its line no one's
            return _wake_failed(tid, session, note["id"], launch_failed(flags, banner))
        noted = copy_note(banner, session, short)
        if noted is not None:
            if noted[0] in ("open", "running"):                          # row 11
                remove_copy(short, "the session was held")
                wake_line_dropped(tid, session, note["id"])
                return WakeResult(True) if process_holds(session)[0] else WakeResult(False, "starting")
            if flags and not flagless:                                   # row 12
                remove_copy(short, "the session keeps saved options")
                wake_line_dropped(tid, session, note["id"])   # the copy's: the retry writes its own, or none
                flagless = saved = True
                try:
                    threads.wake_saved(tid, session)   # kept whatever the retry comes to: the next wake passes none
                except (OSError, LockBusy) as e:
                    warn("the wake of %s did not note its saved options: %s" % (session[:8], e or "its lock is busy"))
                continue
            remove_copy(short, "the engine started a copy")              # row 13
            return _wake_failed(tid, session, note["id"], "the engine started a copy")
        try:
            # The job the banner named, accepted before its process is seen (W6): a launch that is still starting at
            # W7's bound is neither stopped as lingering nor launched beside by the next wake, nor ended by the sweep.
            # Its line is bound to it in the same write, and goes to that job's process alone.
            threads.wake_job(tid, session, short, line_id=note["id"])
        except (OSError, LockBusy) as e:
            warn("the wake of %s did not note its job: %s" % (session[:8], e or "its lock is busy"))
        got = _wake_wait(session, short)                                 # W7
        if got == "copy":                                                # row 13: the banner's job is another's
            remove_copy(short, "the banner's job names another session")
            return _wake_failed(tid, session, note["id"], "the engine started a copy")
        if got in ("failed", "failed-unowned"):                          # row 15
            if got == "failed" and row is None and own_failed_row(session):
                try:
                    p = subprocess.run(["claude", "rm", short], capture_output=True, text=True, timeout=60)
                    if p.returncode != 0:
                        raise OSError("exit %d%s" % (p.returncode, ": " + engine_said(p.stderr) if p.stderr.strip()
                                                     else ""))
                    threads.wake_forget(tid, session)
                except subprocess.TimeoutExpired as e:
                    daemon_log("the failed first wake of %s left its row: claude rm %s timed out after %gs"
                               % (session[:8], short, e.timeout))
                except Exception as e:  # noqa: BLE001 — said, and the next wake finds a row
                    daemon_log("the failed first wake of %s left its row: claude rm %s: %s"
                               % (session[:8], short, e if isinstance(e, OSError) and not e.errno
                                  else engine_said(e)))
            return _wake_failed(tid, session, note["id"], "its worker failed before it started")
        if got != "live":                                                # row 16
            return WakeResult(False, "starting", short)
        return _wake_live(tid, session, saved, on_live, short)          # W8, row 17


def _wake_live(tid, session, saved, on_live, short):
    """W8: a launch of this wake made the session live: its failures and the
    stop mark of the record it decided on cleared, then the caller's
    `on_live(short)` under the hold (`short` "" when no record names it)."""
    threads = threads_module()
    try:
        threads.wake_done(tid, session, saved=saved or None)
        threads.stop_seen(session, thread_id=tid)
    except (OSError, LockBusy) as e:
        warn("the wake of %s was not noted: %s" % (session[:8], e or "its lock is busy"))
    if on_live is not None:
        on_live(short)
    return WakeResult(True, "", short)


def _wake_wait(session, short):
    """W7, for poll_uuid's bound, on the job this launch's banner named
    (`short`), its owner read first: "copy" once its entry names another
    session; "live" once the engine's record shows a process holding the
    session and the entry is this session's (or, while the list shows no
    session for it, the short is the session's own); "failed" once the
    entry, this session's, reads failed and no process holds the session
    ("failed-unowned" when the failed entry names no session: counted,
    nothing removed); "" when none of these came."""
    tries = int(os.environ.get("SMINOS_UUID_POLL") or os.environ.get("DAEMON_UUID_POLL") or "30")
    for i in range(max(tries, 1)):
        readable, entry = job_of(short)
        owner = str((entry or {}).get("sessionId") or "")
        if owner and owner != session:
            return "copy"
        running = running_now(session) is not None
        if running and (owner == session or (not owner and short == session[:8])):
            return "live"
        if entry is not None and not running and normalize_state(entry) == "failed":
            return "failed" if owner == session else "failed-unowned"
        if i + 1 < tries:
            time.sleep(poll_interval())
    return ""


def _wake_failed(tid, session, line_id, what, job=None):
    """§3's "failed": the failure counted in `waking`, this wake's line
    removed, said in daemon.log; not live. With `job` (accepted_failed),
    None when the record holds that job no more: nothing counted or said."""
    threads = threads_module()
    try:
        if not threads.wake_failed(tid, session, line_id, job=job) and job is not None:
            return None
    except (OSError, LockBusy) as e:
        warn("the failed wake of %s was not counted: %s" % (session[:8], e or "its lock is busy"))
    daemon_log("the wake of %s failed: %s" % (session[:8], what))
    if threads.waking(threads.get(tid), session).get("failed") == WAKE_SAID_AT:
        # Once, at the fifth failure in a row (§4): its machine goes on trying, up to an hour apart.
        daemon_log("the wake of thread %s (session %s) has failed %d times in a row, the last: %s; it is tried again "
                   "up to an hour apart until it wakes or the thread ends" % (tid, session[:8], WAKE_SAID_AT, what))
    return WakeResult(False, "failed")


WAKE_SAID_AT = 5   # the failure in a row at which daemon.log names the thread (§4)


def accepted_failed(tid, session, job):
    """§3's "failed" for a launch whose banner's job was accepted (`waking.job`)
    and never ran: the job dead, failed or gone from the job list, or its
    grace passed while no process held the session. Counted as any failed
    wake, with the line bound to that job (its `short`) removed: no process
    of that launch will take it. Under the caller's wake lock, which the
    record hook does not take: so only while the record still holds the job
    observed (`job`, its `short` and `at`), decided in the field's own
    compare-and-set (wake_failed), and a process that came up meanwhile,
    whose hook cleared the job first (stop_seen), keeps its line, nothing
    counted. Whether it was counted."""
    return _wake_failed(tid, session, None, "its job %s was accepted and never ran" % job["short"], job=job) \
        is not None


def wake_lapsed(tid, session):
    """The sweep's half of an accepted job that never ran (accepted_failed):
    under the wake lock it holds out (sminos_daemon.resume_lock_out), the
    record read again, and a job there whose grace has passed while no
    process holds the session (the engine's records, read afresh) counted
    as a failed wake. The sweep reads no job list for it, so an idle tick
    stays a stat; a wake reads the list within the grace. Whether it
    counted."""
    threads, wm = threads_module(), wake_module()
    t = threads.get(tid)
    if t is None or t["current"] != session or t.get("pending") or threads.record_ended(t):
        return False
    job = threads.waking(t, session).get("job")
    if not isinstance(job, dict) or not job.get("short") or wm.starting(t, session) is not None \
            or running_now(session) is not None:
        return False
    return accepted_failed(tid, session, job)


def resume_session(s, locks=None, quiet=False, event=None, project=None, carried=None, words=None, returns=False,
                   stop_turn=False, due=True):
    """A seat's wake (T2's M2): the seat's own steps ahead of it, then the
    wake of its record (wake), which starts its session's process under the
    same id and hands it nothing. The WakeResult; the caller pushes what it
    brought to the process that runs, as to a live session, and writes the
    seat's `turns` and `status` once it has pushed (seat_pushed). What is
    the seat's alone happens here: its lifecycle lock (taken when `locks`
    is None), the refusal of a codex record, a vacant seat, a retired one
    for any caller but `fill --resume` (`returns`, which the wake's W8
    returns, journaled, once the process runs); with `stop_turn` (`sminos
    resume`) the stop of a live background turn, as before, unless a reason
    the thread is not woken holds (a session under another config dir, a
    directory that is gone, …: the wake's to answer, a hold, T2's M4); and
    at W8 the
    seat's `short`, `host` and `boot_id` (on_live). No `pending_short` is
    written.

    Message reach (P5 O18 D8), before anything is stopped or launched: a
    caller that carries log events (`event`, the last, in the log of the
    project whose id is `project`; `carried`, every one; `words` the verdict
    they go under, as push_live's) passes the reach gate for each or raises
    ReachHeld. The check consumes nothing: the push that follows spends it.

    A seat whose session a thread record its human opened names (an older
    copy seated it, D7) is that record's to wake (wake_member, from
    delivery, and its record's verb_delivered, from a verb): checked under
    the seat's lock, before any gate, nothing stopped or launched —
    ResumeHeld (ResumeRefused for an ended one). `due` is the deliverer's
    (deliver_next) from delivery (`quiet`)."""
    if locks is not None and not quiet and opened_by_human(s["current"]):
        if canonical_end(s["current"], seat_project(s)):
            # Ended (opened_by_human reads the records set aside too): nothing is recorded or held for it, since
            # its end settles what is owed, pushed nowhere; it returns when its human reopens it.
            unlock(locks)
            raise ResumeRefused("seat %s/%s's session has ended: nothing was recorded for it — it returns when its "
                                "human reopens its session" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        unlock(locks)
        raise ResumeHeld(human_refusal("%s/%s" % (s["group"], s["alias"])), s)
    if event is not None:
        reach_hold(project, s["current"], [event] if carried is None else carried, words, keep=True)
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
        if not quiet and opened_by_human(s["current"]):
            unlock(locks)
            raise ResumeHeld(human_refusal("%s/%s" % (s["group"], s["alias"])), s)
    if not s["current"]:
        raise ResumeRefused("seat %s/%s is vacant — fill it with: sminos fill %s/%s \"<task>\"" % (
            s["group"], s["alias"], s["group"], s["alias"]), EXIT_UNKNOWN)
    if s["status"] == "retired" and not returns:
        raise ResumeRefused(retired_seat_refusal(s), EXIT_UNKNOWN)
    if returns:
        home = seat_project(s)
        if home is None or guessed(home):
            # The return is journaled in the seat's project (join_seat, W8): with none read here, a process
            # started would run under a seat left retired.
            raise ResumeRefused("seat %s/%s cannot return from here: its project cannot be read, and its return is "
                                "recorded in that project's log — nothing was started" % (s["group"], s["alias"]),
                                EXIT_UNKNOWN)
    seat_id = s["seat_id"]
    # Its config dir and its directory are the wake's to answer (not_woken: a hold, T2's §6), for a verb as for a
    # delivery. A live turn is stopped only for a wake that would start it again: with a reason not to, the message
    # goes to the process that runs, its turn left as it is.
    took = None
    if stop_turn:
        # The stop and the wake that follow run under one hold of the wake lock (§3, W1), taken before anything is
        # read or stopped: the sweep and a transition cannot act between them, a lock that cannot be had stops
        # nothing, and what would refuse the wake (wake_refusal) is decided under it, before the stop.
        if wake_held(seat_id) is None:
            took, why = launch_hold(seat_id)
            if took is None:
                return WakeResult(False, why)
        try:
            reason = wake_refusal(seat_id, s["current"], returns)
            if not reason:
                stop_live_turn(s)
            elif running_now(s["current"]) is not None:
                turn_kept("%s/%s" % (s["group"], s["alias"]), reason, s["current"])
        except BaseException:
            if took is not None:
                took.release()
            raise

    def on_live(short):
        # The seat's fields once its process runs (W8): the job's short and where it runs; `turns` and `status`
        # wait for the push (seat_pushed). A retired seat returns here, journaled, with the wake's hold.
        # Bound to the session this wake decided on: a seat another writer moved to another occupant meanwhile
        # (an older copy's refill) gets neither the fields nor the joined.
        woken = s["current"]
        fields = {"host": host_name(), "boot_id": boot_id(), "updated": now(), **({"short": short} if short else {})}
        if not meta_set_if(seat_id, fields, lambda d: str(d.get("current") or "") == woken, remove=("pending_short",)):
            return
        fresh = reload_seat(seat_id)
        if fresh is None or fresh["current"] != woken:
            return
        try:
            join_seat(fresh, by=caller_alias(), returns=returns)
        except LogWriteFailed as e:
            if not quiet:
                raise
            warn("%s/%s was woken, but %s" % (s["group"], s["alias"], e))

    try:
        woke = wake(threads_module().get(seat_id) or {"thread": seat_id}, s["current"], due=due, returns=returns,
                    on_live=on_live)
    finally:
        if took is not None:
            took.release()
    if woke.live and returns and ((threads_module().get(seat_id) or {}).get("pending") or {}).get("op") == "return":
        # Nothing is written through an open entry (§6, 6): nothing is pushed until its return is finished.
        raise ResumeRefused("%s/%s was woken and its session runs, but its return is not finished (its record holds "
                            "it): its joined waits for the next reconciliation" % (s["group"], s["alias"]), 1)
    return woke


def turn_kept(ref, why, session):
    """What `resume` says of a live turn it left running, the wake that
    would follow its stop refused (wake_refusal's `why`): for a reason of
    not_woken, that the message goes to the process that runs."""
    if why in wake_module().REASONS:
        warn("the turn of %s was not stopped: a wake would not start it again (%s); the message goes to the process "
             "that runs" % (ref, hold_words(why, session)))
    else:
        warn("the turn of %s was not stopped: %s" % (ref, wake_words(why)))


def stop_live_turn(s):
    """`sminos resume`'s own step ahead of a seat's wake (T2's M2):
    stop_background_turn for the seat's session, its recorded short
    preferred among its finished jobs."""
    stop_background_turn(s["current"], s["short"], "%s/%s" % (s["group"], s["alias"]))


def stop_background_turn(cur, short, ref):
    """A live background turn of the session stopped (`claude stop`, then a
    bounded wait until its row no longer runs and no engine record of the
    session names a running process), so that the wake starts its process
    again. Only a job the job list shows is a background job of this
    session (background_job) is stopped, never a short recorded alone
    (`short` only chooses among its finished jobs); a session a terminal
    holds is left as it is (the wake finds it live and the message is
    pushed to it); one that runs with no such job is refused, as a launch
    beside it would start a copy. ResumeRefused for a stop that did not
    take."""
    rec = running_now(cur)
    if rec is not None and rec.get("kind") and str(rec.get("kind")) != "bg":
        return   # a terminal's process: delivered to, never stopped
    jobs = [r for r in agents_refresh() or [] if background_job(r, cur)
            and normalize_state(r) in ("working", "blocked", "done", "done-blocked")]
    job = next((r for r in jobs if normalize_state(r) in ("working", "blocked")), None) \
        or next((r for r in jobs if short and r["id"] == short), None) or (jobs[-1] if jobs else None)
    if job is not None:
        if not claude_stop(job["id"]):
            raise ResumeRefused("claude stop %s failed for %s — not resuming over a turn that may still be running"
                                % (job["id"], ref), 1)
        stopped = wait_stopped({"current": cur, "short": ""}, job["id"], cur)
        if stopped == "unknown":
            raise ResumeRefused("the job list could not be read to confirm that the turn of %s (%s) stopped after "
                                "claude stop — not waking it (a launch would start a copy if it still runs)"
                                % (ref, job["id"]), 1)
        if stopped != "stopped":
            raise ResumeRefused("the current turn of %s (%s) is still running %ss after claude stop — not waking "
                                "it (a launch would start a copy)" % (ref, job["id"],
                                                                     os.environ.get("SMINOS_STOP_TIMEOUT", "30")), 1)
    elif rec is not None:
        raise ResumeRefused("the session of %s (%s) still runs, and the job list shows no background job of it "
                            "sminos can stop — not waking it (a launch would start a copy)" % (ref, cur[:8]), 1)


def seat_pushed(s):
    """A seat's `turns` and `status` once a message was pushed to its woken
    session (T2's M2), only while it still holds that session."""
    fresh = reload_seat(s["seat_id"]) or s
    meta_set_if(s["seat_id"], {"status": "working", "updated": now(), "turns": str(int(fresh["turns"] or "0") + 1)},
                lambda d: str(d.get("current") or "") == s["current"])


# What a sender or a verb is told of a wake that did not make the session live (WakeResult.why).
WAKE_WORDS = {
    "sweep": "its wake waits for the thread sweep or a transition of it, which holds its lock",
    "in flight": "a wake of it is already in flight",
    "starting": "its process was started and does not answer yet",
    "pending": "it holds a transition not finished yet, which the next reading verb finishes",
    "unknown": "its record, its lane or the engine's jobs could not be read just now",
    "busy": "a verb holds its seat",
    "gone": "its session no longer fills its thread",
    "lane": "its session is one MAWS reopens, which sminos never wakes",
    "ended": "it has ended",
    "failed": "waking it failed",
    "config": "it runs under another config dir",
    "transcript": "no conversation of it is on this machine",
    "cwd": "its directory is gone",
    "protected": "its directory is in, or holds, a folder macOS protects, where a background launch would stop at a "
                 "prompt",
    "mode": "a wake would run it in a mode that asks for approval",
}


def wake_words(why):
    return WAKE_WORDS.get(why, why)


def wake_outcome(why, thread=None):
    """A delivery's outcome for a wake that did not make the session live
    (§3's last paragraph): a session that no longer fills the thread (the
    stale hold), one MAWS reopens (delivered to as a session that is no
    thread) and an ended one `recorded`; every other `held:<why>`, owed
    with no attempt counted and marked for its thread (T2's M3: a wake that
    failed is held, never counted), `thread` the one the wake was decided
    for."""
    if why in ("gone", "lane", "ended"):
        return "recorded"
    return hold_outcome(why, thread)


def canonical_end(session, project):
    """The end in effect for a session, read afresh, whatever a seat says of
    it: its thread's record (thread_of) ended, or its membership in effect
    (the fold, its own events in `project`) a `retired` of END_REASONS;
    None when it has not ended."""
    if not session:
        return None
    threads = threads_module()
    t = threads.thread_of(session)
    if t is not None and t["current"] == session and threads.record_ended(t):
        return t["ended"]
    if project is None:
        return None
    e = threads.in_effect(_own_events(project, session))
    return e if e is not None and e["kind"] == "retired" and e.get("reason") in END_REASONS else None


def queued_after_end(waiting):
    """What a sender is told of a send queued for its writer's head
    (WaitingSend) to a session whose thread ended meanwhile: it is not in
    the log yet, so no end has settled it; once appended it is settled with
    the end if the end still stands, and delivered if the session has
    returned by then."""
    return ("the message is queued, not in the log yet (%s); once appended it is settled with the end if the "
            "session is still ended, and delivered to it if it has returned" % waiting.held)


def ended_after_record(project, alias, session, recorded):
    """The end found after a send's record (canonical_end, read afresh; the
    caller holds the session's delivery lock where `recorded` is a
    SendDelivery): exit 4, saying what becomes of the message — settled with
    the end, or for one still queued (WaitingSend) queued_after_end. Nothing
    when the session has not ended."""
    if not canonical_end(session, project):
        return
    if isinstance(recorded, WaitingSend):
        die("%s has ended: %s" % (alias, queued_after_end(recorded)), EXIT_UNKNOWN)
    event = recorded.event if isinstance(recorded, SendDelivery) else recorded
    if isinstance(recorded, SendDelivery):
        recorded.release()
    die("%s has ended: %s was recorded and is settled with its end, pushed nowhere" % (alias, event_ref(event)),
        EXIT_UNKNOWN)


def refuse_ended_seat(s, ref, recorded=None, ended=False):
    """Exit 4 for a send to a seat whose session's thread has ended
    (canonical_end; `ended`: already decided by the caller), saying what
    returns it: a fill, or for a thread its human opened (an older copy
    seated it), its human reopening it. `recorded`: the send's delivery
    (SendDelivery, or a WaitingSend whose append waits for its writer's
    head) made before the end was found, which the end settles."""
    if not ended and not canonical_end(s["current"], seat_project(s)):
        return
    if opened_by_human(s["current"]):
        if recorded is None:
            what = "nothing was recorded for it"
        elif isinstance(recorded, WaitingSend):
            what = queued_after_end(recorded)
        else:
            what = "%s was recorded and is settled with its end, pushed nowhere" % event_ref(recorded.event)
        die("seat %s's session has ended: %s — it returns when its human reopens its session" % (ref, what),
            EXIT_UNKNOWN)
    die(retired_seat_refusal(s), EXIT_UNKNOWN)


def retired_seat_refusal(s):
    """What `resume` (and a send) aimed at a retired seat is told: its thread
    ended, and a fill returns it (T1's M4)."""
    ref = "%s/%s" % (s["group"], s["alias"])
    return ('seat %s is retired — a fill returns it: sminos fill %s --resume "<task>" continues its session, '
            'sminos fill %s "<task>" starts a fresh one' % (ref, ref, ref))


def cmd_resume(a):
    """`sminos resume <seat> <msg>`: a live background turn of the seat
    stopped, the seat woken, and its message pushed to it (T2's M2). The
    message is recorded first, as `send` records one (record_send), so it
    is durable before anything is launched and has an id `--wait` looks
    for; it is then delivered as `send` delivers it (send_to_seat)."""
    s0, bound, opened = resolve_seat_or_opened(a.seat, "resume it")
    warn_resume_flags(a)
    if opened is not None:
        verb_to_thread(opened[0], opened[1], a.msg, a.wait, "resumed", stop_turn=True)
        return
    deliver_verb(s0, bound, a.msg, a.wait, "resumed", stop_turn=True)


def deliver_verb(s, bound, msg, wait, verb, stop_turn=False, woke=False, locks=None):
    """A verb's message to a seat (`resume`, `fill --resume`), recorded and
    delivered as `send` records and delivers one (T2's M2); `locks`, the
    seat's lifecycle locks its caller holds already (a retired seat's
    return), which the send takes over."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    frm = default_from("")
    sender = "human" if not sid else ((caller_seat() or {}).get("alias") or frm)
    msg_id = uuidlib.uuid4().hex[:8]
    try:
        send_to_seat(s, compose_frame(frm, msg_id, msg), msg_id, wait,
                     record=lambda seat: record_send(seat, sender, frm, msg, msg_id), session=bound, sender=frm,
                     verb=verb, stop_turn=stop_turn, woke=woke, locks=locks)
    except ResumeRefused as e:   # the seat's own refusals ahead of the wake (resume_session), as `send` exits on them
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


def _prompt_text(row):
    """A prompt row's text (a user row that is no tool result), else None."""
    if row.get("type") != "user":
        return None
    c = (row.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        texts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
        return "".join(texts) if texts else None
    return None


class TranscriptTail:
    """A session's transcript read incrementally (`--wait`'s polls): the rows
    parsed so far, each poll reading only what was appended since, a line
    not ended yet kept for the next; read whole again when the file is
    another one (another path, or another file at the same path: its device
    and inode) or shorter than what was read."""

    def __init__(self, session):
        self.session, self.file, self.at, self.part, self.rows = session, None, 0, b"", []

    def read(self):
        path = transcript_now(self.session)
        try:
            st = os.stat(path) if path else None
        except OSError:
            st = None
        if st is None:
            return self.rows
        file = (path, st.st_dev, st.st_ino)
        if file != self.file or st.st_size < self.at:
            self.file, self.at, self.part, self.rows = file, 0, b"", []
        if st.st_size <= self.at:
            return self.rows
        try:
            with open(path, "rb") as f:
                if (os.fstat(f.fileno()).st_dev, os.fstat(f.fileno()).st_ino) != file[1:]:
                    return self.rows   # replaced between the look and the open: the next poll reads the new one
                f.seek(self.at)
                data = f.read()
        except OSError:
            return self.rows
        self.at += len(data)
        lines = (self.part + data).split(b"\n")
        self.part = lines.pop()
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                self.rows.append(row)
        return self.rows


def _put_in_turn(row):
    """Whether a prompt row (_prompt_text) was put into the turn that runs
    rather than starting one: the engine keeps such a row isMeta, from a
    plugin (the bridge's second delivery to a busy session, its notes) or
    from itself (no origin: a skill's text, a stop hook's feedback). A
    peer's message, a task's notification and a prompt a plugin submitted
    as the human's (`asUser`) each start a turn of their own."""
    if row.get("isMeta") is not True:
        return False
    origin = row.get("origin")
    if not isinstance(origin, dict):
        return True
    return origin.get("kind") == "plugin" and origin.get("asUser") is not True


# The bridge's wake (bridge.tsx, wakeText): its first line, and the line that names the frame line of each row it
# points at (frameOf: a delivered text's first line), joined by a space. Sent on the inbox after a stop, it is a
# peer's message from this name (sminos_bridge.WAKE_SENDER), in the engine's envelope.
WAKE_LINE = "[sminos bridge]"
WAKE_UNREAD = "Unread: "
WAKE_PEER = "sminos bridge"
# A frame's head at a line's start (compose_frame, compose_chat_frame): one line, a quoted alias (frame_alias)
# holding no break.
FRAME_HEAD_RE = re.compile(r"^\[sminos (?:message from|chat) [^\n]*\]$", re.M)


def _wake_payload(row):
    """The text a prompt row carries from the bridge, where its wake would
    be: the prompt it submits as the human's (a plugin's, `asUser`) as
    submitted, or the body of the one it sends on the inbox after a stop (a
    peer's, WAKE_PEER), its `origin.body` or else unwrapped from the
    engine's envelope; "" for any other row."""
    origin = row.get("origin") if isinstance(row.get("origin"), dict) else {}
    if origin.get("kind") == "plugin" and origin.get("asUser") is True:
        return _prompt_text(row) or ""
    if origin.get("kind") != "peer" or origin.get("name") != WAKE_PEER:
        return ""
    if isinstance(origin.get("body"), str):
        return origin["body"]
    text = _prompt_text(row) or ""
    opened = re.search(r"<%s[^>\n]*>\n" % PEER_TAG, text)
    return text[opened.end():] if opened else ""


def _wake_names(row, head):
    """Whether a prompt row is the bridge's wake naming the frame line
    `head` on its `Unread:` line: a payload of the bridge's (_wake_payload)
    whose first line is the wake's own, never a message that quotes one."""
    lines = _wake_payload(row).split("\n")
    if lines[0] != WAKE_LINE:
        return False
    unread = next((line for line in lines[1:] if line.startswith(WAKE_UNREAD)), None)
    return unread is not None and " %s " % head in " %s " % unread[len(WAKE_UNREAD):]


def reply_to(session, msg_id, rows=None):
    """(found, the reply to the message `msg_id`, closed: whether the next
    prompt that starts a turn ends it): what `--wait` prints (T2's M2),
    whatever another sender's message got before or after it. The message
    is in the first prompt row holding its frame's head at a line's start
    (R), never its id quoted in a body. The reply is the assistant text
    after R, or, when the bridge's wake naming R's first frame line follows
    R (_wake_names: R went in while a turn that never read it was ending,
    or after a stop), after that wake: what was said before it is the turn
    that did not read R. It runs to the next prompt that starts a turn; a
    row put into the turn that runs (_put_in_turn) ends nothing, and the
    turn's end is the waiter's to read. `rows`: the transcript's rows as
    read (TranscriptTail), else read whole."""
    rows = transcript_rows(session) if rows is None else rows
    framed = re.compile(r"^\[sminos message from [^\n]* id=%s\]$" % re.escape(msg_id), re.M)
    start = next((i for i, r in enumerate(rows) if framed.search(_prompt_text(r) or "")), None)
    if start is None:
        return False, "", False
    head = FRAME_HEAD_RE.search(_prompt_text(rows[start])).group(0)
    start = next((i for i in range(start + 1, len(rows)) if _wake_names(rows[i], head)), start)
    results = {str(b.get("tool_use_id") or ""): b for r in rows if r.get("type") == "user"
               for b in _blocks(r, "tool_result")}
    said, closed = [], False
    for r in rows[start + 1:]:
        if _prompt_text(r) is not None and not _put_in_turn(r):
            closed = True
            break
        if r.get("type") == "assistant" and r.get("answeredWithoutRequest") is not True:
            text = _said(r, results)
            if text:
                said.append(text)
    return True, "\n\n".join(said), closed


def wait_reply(s, msg_id, guard):
    """`--wait` after a push to a seat (T2's M2): wait_session_reply, the
    seat's reply file and `status` written under `guard`, for `sminos reply`
    and the list, only while its process is idle (a later prompt's turn may
    run); nothing is printed from that shared file."""
    _wait_reply(s["current"], "%s/%s" % (s["group"], s["alias"]), s["alias"], msg_id, (s, guard))


def wait_session_reply(session, name, msg_id):
    """`--wait` after a push to a thread with no seat here (T2's M4), as a
    seat's waits: its reply to this message printed, else `(no reply yet)`;
    a watcher that expires names `sminos reply <name>`."""
    _wait_reply(session, name, name, msg_id, None)


def _wait_reply(cur, ref, name, msg_id, seat):
    """The message's id in the session's transcript, waited for
    (SMINOS_ACK_TIMEOUT), then the turn that holds it to its end — the next
    prompt that starts a turn (which delimits the reply; a row put into the
    turn that runs does not, reply_to), or the engine's record of
    the process reading `idle` with an answer after the prompt, or for a
    second look a poll later, or no process left — then the reply to that
    message printed (reply_to). The transcript is read incrementally
    (TranscriptTail). A busy job alone is no evidence: an idle woken job is
    listed before any turn. `seat`: (seat, guard) whose fields are written,
    or None. No evidence, or a turn still running when the watcher expires,
    exits 1."""
    tail = TranscriptTail(cur)
    deadline = time.time() + float(os.environ.get("SMINOS_ACK_TIMEOUT", "120"))
    while not reply_to(cur, msg_id, tail.read())[0]:
        if time.time() >= deadline:
            sys.stderr.write("sminos: no evidence that %s received the message within the ack window (no transcript "
                             "marker) — not waiting for a reply\n" % ref)
            sys.exit(1)
        time.sleep(poll_interval())
    iterations, i, idle_before = watcher_iterations(), 0, False
    while True:
        found, text, closed = reply_to(cur, msg_id, tail.read())
        if closed:
            break   # the next prompt ends this one's reply, whatever the process does now
        rec = running_now(cur)
        idle = rec is None or rec.get("status") == "idle"
        if idle and (text or idle_before or rec is None):
            break
        idle_before = idle
        i += 1
        if iterations and i >= iterations:
            if seat is not None:
                meta_set_if(seat[0]["seat_id"], {"status": "working", "updated": now()}, seat[1])
                sys.stderr.write("sminos: watcher expired; the turn of %s is still running (status=working). Read it "
                                 "later with: sminos reply %s\n" % (ref, name))
            else:
                sys.stderr.write("sminos: watcher expired; the turn of %s is still running. Read its reply later "
                                 "with: sminos reply %s\n" % (ref, name))
            sys.exit(1)
        time.sleep(poll_interval())
    rec = running_now(cur)
    if seat is not None and (rec is None or rec.get("status") == "idle"):
        # The seat-wide word (its status, its reply file) only while no turn runs: the next prompt that ended this
        # wait may have started another sender's turn, which is not this waiter's to publish as done.
        meta_set_if(seat[0]["seat_id"], {"status": "idle", "updated": now()}, seat[1], reply=(cur, "done", name))
    print("--- reply ---")
    print(reply_to(cur, msg_id, tail.read())[1] or "(no reply yet)")


WAKE_POINTER = 'wake was folded into send — sminos send <seat> "<msg>" [--wait] [--from F]'


def cmd_wake(_a):
    die(WAKE_POINTER)


def compose_frame(sender, msg_id, msg, label=""):
    """Every delivery — socket, resume, codex queue — opens with this line; the
    id is what `--wait` looks for in the target's transcript. `label` is what
    follows the sender (sender_labels, frame_alias); the message as
    sender_text gives it."""
    return "[sminos message from %s%s id=%s]\n%s" % (frame_alias(sender), label, msg_id, sender_text(msg))


UNRECORDED = "nothing was started: %s is in no project log here to record the message in, and nothing is woken " \
             "for a message no log holds"


def send_to_seat(s0, text, msg_id, wait, record=None, session="", sender="", verb="", stop_turn=False, woke=False,
                 locks=None):
    """Deliver a frame to one seat under its lifecycle lock. The lock covers
    target selection, the wake, the socket delivery, and the status write,
    so a concurrent fill/resume/retire cannot slip between them. A live seat
    takes the frame (push_live: the owner's through its bridge, a peer's
    through its inbox socket) and is recorded `working`; a stopped one is
    woken (resume_session: its process started under the same id, with no
    message) and then pushed the frame as a live one is (T2's M2); vacant,
    retired, and gone seats are refused, pointing at the verb that can reach
    them. Given `session`, the one the name bound (find_target), a seat that
    no longer holds it is refused. `verb` ("resumed", "filled"): the verb
    that sent it, named in what is printed; `stop_turn` (`sminos resume`): a
    live background turn is stopped and the seat woken again before the
    push; `woke`: the caller woke it just before (`fill --resume` of a
    retired seat), so the push is a woken one's (no @all, its turn counted);
    `locks`: the seat's lifecycle locks that caller holds already, taken
    over here (let go on every path, as the ones taken here are).

    `record(seat)`, when given, appends the message to the seat's project log
    once the seat is known reachable and returns its SendDelivery (or None
    when the seat has no project): the push then carries every earlier event
    of the same writer still owed to the seat, in order, and the delivery
    record is settled on sent or uncertain and noted as failed otherwise —
    so a send that dies on the way is the daemon's to retry. A held send
    (SendDelivery.held: on a cut-over machine an operator's, which the
    uplink delivers on the endpoint's verdict, or one behind an event the
    revocation set cannot clear) is recorded and pushed nothing. `--wait`
    waits for the reply to this message (wait_reply)."""
    refuse_codex(s0)
    locks, s = locked_fresh(s0, "send", session, locks)
    ref = "%s/%s" % (s["group"], s["alias"])
    chosen = threads_module().stamp(s["current"])   # the thread its session is, as looked up: what a hold names
    try:
        refuse_codex(s)
        # ONE liveness probe (pid alive AND socket answers) decides both the word
        # and the route: a second probe could see a session come up and send a
        # live seat to a wake.
        peer = peer_for_session(s["current"]) if needs_probe(s) else None
        st = seat_state(s, peer)
        # The end in effect decides, before the seat's own status (an older copy's seat over a thread its human
        # opened).
        refuse_ended_seat(s, ref)
        # A plain send to a thread no process answers for is delivered as a tagged say is (T2's M3): recorded,
        # then woken or held for its thread by the delivery pass, never refused for what holds it (no
        # transcript, a process whose inbox does not answer yet, its directory or config dir). A verb and --wait
        # aimed at a thread record their message first too, and go on to the wake, which holds it (T2's §6).
        threaded = record is not None and not peer and st not in ("vacant", "retired") \
            and seat_project(s) is not None and threads_module().current_record(s["current"], fresh=True) is not None
        delivered = threaded and not (verb or wait or stop_turn or woke) \
            and (st == "gone" or st in FILLED or bool(hold_now(s["current"])))
        held_verb = threaded and bool(verb or wait) and not woke
        if st == "retired" and verb:
            die(retired_seat_refusal(s), EXIT_UNKNOWN)
        if st in ("vacant", "retired"):
            die('seat %s is %s — fill it with: sminos fill %s "<task>"' % (ref, st, ref), EXIT_UNKNOWN)
        if st == "gone" and not (delivered or held_verb):
            die('seat %s is gone — no transcript for its session on this machine; sminos fill %s "<task>" '
                "or sminos retire %s" % (ref, ref, ref), EXIT_UNKNOWN)
        if not peer and st in FILLED and not stop_turn and not (delivered or held_verb):
            # Its process runs (the engine's record): a launch would start a copy
            # of the running session, so nothing is sent.
            die(quiet_inbox_refusal(ref), EXIT_UNKNOWN)
    except SystemExit:
        unlock(locks)   # a refusal leaves no seat lock open behind it
        raise
    delivery = record(s) if record else None
    refusal = projectless_refusal(s["current"], s["alias"]) if delivery is None else None
    if refusal:
        # No log event to ask the endpoint about (P5 O18 D8): only the recipient's owners' sessions reach it.
        unlock(locks)
        die(refusal, EXIT_UNKNOWN)
    if delivery is None and record is not None and (verb or stop_turn or not peer) and not woke:
        # A verb's message is a logged event, and a wake is made only for a recorded message (T2's §6; the
        # holder: whatever must be written is writable before the launch): with no log here, nothing is stopped
        # or woken. A live seat still takes a plain send by the owner-checked projectless push (D8). (A retired
        # seat's return has refused this before its launch.)
        unlock(locks)
        die(UNRECORDED % ref, EXIT_UNKNOWN)
    if canonical_end(s["current"], seat_project(s)):
        # Ended since the check above (an end, which settles what is owed to it, holds no seat lock): its event is
        # the end's to settle, and nothing is pushed. Decided here, under the locks: a return after they are
        # released does not reopen the route.
        unlock(locks)
        if delivery is not None:
            delivery.release()
        refuse_ended_seat(s, ref, recorded=delivery, ended=True)
    if opened_by_human(s["current"]) and (not peer or hold_now(s["current"])):
        # A session its human opened that an older copy seated (D7): resolved here under the seat's lock, after
        # the append and before both the live route and the wake, the gates and the wait. The fresh hold at this
        # last hop: a peer this process read before a `/clear` moved its pid to another session is no route. A
        # plain send is delivered as every deliverer delivers (T2's M3: its record's own wake, or the hold); a
        # verb and a wait as a verb aimed at that thread delivers its message (T2's M4).
        unlock(locks)
        if (verb or wait) and isinstance(delivery, (SendDelivery, WaitingSend)):
            verb_delivered(delivery.project, s["current"], s["alias"], delivery, msg_id, verb, wait, stop_turn)
            return
        if not (wait or delivery is None or verb or isinstance(delivery, WaitingSend)
                or delivery.held and not hold_now(s["current"])):
            delivery.release()
            deliver_sent(delivery.project, s["current"], s["alias"], delivery)
            return
        held_send(delivery, s["alias"], thread=chosen)
        if wait or delivery is None or verb:
            die("nothing was started: %s has no log here to record it in; no reply is waited for" % ref,
                EXIT_UNKNOWN)
        return
    if delivered and delivery is not None and delivery.held and hold_now(s["current"]):
        # Held for its thread (T2's §4): the hold first, asking the endpoint nothing; the words and reach gates
        # decide only a push, which a held thread is not given.
        unlock(locks)
        delivery.release()
        deliver_sent(delivery.project, s["current"], s["alias"], delivery)
        return
    if held_verb and delivery is not None and delivery.held and hold_now(s["current"]):
        # Held for its thread (T2's §4) as a plain send is: the hold first, the endpoint asked nothing about a
        # message that is not pushed; the verb records, starts nothing and exits 4, waiting for nothing.
        unlock(locks)
        verb_delivered(delivery.project, s["current"], s["alias"], delivery, msg_id, verb, wait, stop_turn)
        return
    if delivery and (delivery.held or not delivery.queue):
        # A concurrent deliverer pushed it between the append and our lock, or
        # it is held (O12 M6: a person's words the uplink delivers on the
        # endpoint's verdict, or behind an event the revocation set cannot
        # clear): no push here, but --wait still waits on this message's id.
        guard = same_gen(current_gen(s["seat_id"]))
        waiter = (lambda: wait_reply(s, msg_id, guard)) if wait else None
        if delivery.held:
            # Recorded first, so a resume's message the endpoint is to admit stops no turn; a returned seat's task
            # waits for the endpoint's answer, which is said with the return (the holder's ruling for M4).
            if woke:
                delivery.held = "%s returned and its session runs; its task waits: %s" % (ref, delivery.held)
            elif stop_turn:
                delivery.held += "; no turn was stopped, and the message follows on that answer"
            delivery.recorded_owed(s["alias"])
        else:
            delivery.release()
        unlock(locks)
        if not delivery.held:
            if verb or wait:
                settled_elsewhere(s["current"], ref, delivery.event, msg_id, verb, waiter)
            else:
                print(settled_sent(delivery.project, s["current"], delivery.event, ref), flush=True)
            return
        if woke:
            if returned_task(delivery, s["current"], ref, msg_id, wait) and waiter is not None:
                waiter()
            return
        if verb or wait:
            say_owed(s["current"])
        if waiter is not None:
            waiter()
        return

    if delivered and delivery is not None:
        unlock(locks)
        delivery.release()
        deliver_sent(delivery.project, s["current"], s["alias"], delivery)
        return

    def reach_held():
        # The reach gate held the push (P5 O18 D8): nothing went, nothing was stopped; owed for the uplink.
        delivery.held = "the endpoint decides its delivery"
        delivery.recorded_owed(s["alias"])
        if verb or wait:
            say_owed(s["current"])
        unlock(locks)

    def unsent():
        # Nothing pushed: an attempt counted (the daemon's next pass delivers it), or for a queued send released.
        if isinstance(delivery, SendDelivery):
            delivery.fail()
        elif delivery is not None:
            delivery.release()

    def woken_peer():
        """The wake, then the peer the push goes to; None once a wake that
        did not make the session live was handled (returned, or exited)."""
        try:
            woke = resume_session(s, locks, stop_turn=stop_turn,
                                  **({"event": delivery.queue[-1], "project": delivery.project.id,
                                      "carried": delivery.carried(False)} if delivery else {}))
        except ReachHeld:
            reach_held()
            return None
        except ResumeHeld as e:
            # The seat holds a session its human opened (T1's M3), its own record's to wake: a verb and a wait
            # deliver as a verb aimed at it does (T2's M4); a plain send stays owed, no attempt counted.
            unlock(locks)
            if delivery is None:
                die(e.message, EXIT_UNKNOWN)
            if wait or verb:
                verb_delivered(delivery.project, s["current"], s["alias"], delivery, msg_id, verb, wait, stop_turn)
                return None
            held_send(delivery, s["alias"], thread=chosen)
            return None
        except ResumeRefused:
            unsent()
            unlock(locks)
            if (verb or wait) and isinstance(delivery, SendDelivery) and thread_owed(s["current"]):
                say_owed(s["current"])   # an attempt counted: the daemon's next pass delivers it
            raise
        if woke.live:
            forget_caches()
            got = peer_for_session(s["current"])
            if got is not None:
                return got
            woke = WakeResult(False, "starting")
        unlock(locks)
        words = wake_words(woke.why)
        if woke.why == "ended":
            if delivery is not None:
                delivery.release()
            refuse_ended_seat(s, ref, recorded=delivery, ended=True)
        if woke.why in HOLDS and delivery is not None:
            # Held for its thread (T2's M3), never a failed attempt: each event the send carries marked (a stale one
            # aside: it is no one's), owed until pushed to its process or the thread ends; the sender told why
            # (§5). A verb and a wait record, start nothing and exit 4 (§6).
            if isinstance(delivery, SendDelivery):
                for x in delivery.carried(False):
                    # Marked for the thread the wake decided for: the seat's record, which resume_session woke.
                    delivered_held(delivery.project, delivery.session, delivery.writer, x["seq"], s["seat_id"])
                delivery.release()
                print("recorded %s for %s: %s" % (event_ref(delivery.event), s["alias"],
                                                  held_line(woke.why, session=s["current"])), flush=True)
            else:
                delivery.recorded_owed(s["alias"])
            nudge_daemon()
            if verb or wait:
                say_owed(s["current"])
                die(verb_hold_words(woke.why, s["current"]), EXIT_UNKNOWN)
            return None   # a plain send to a held thread: recorded and held, exit 0 (T2's §6)
        unsent()
        if (verb or wait) and isinstance(delivery, SendDelivery) and thread_owed(s["current"]):
            say_owed(s["current"])   # an attempt counted: the daemon's next pass delivers it
        die("%s was not woken: %s" % (ref, words), EXIT_UNKNOWN if woke.why in ("gone", "lane", "transcript") else
            EXIT_USAGE if woke.why == "cwd" else 1)

    woken = woke and peer is not None
    # A terminal's process is never stopped (W3): `resume` pushes to it as `send` does, and says so. Nor is a live
    # background job's turn when a wake would not start it again (not_woken): the message goes to the process that
    # runs, with no wake (T2's §6).
    terminal = peer is not None and str(peer.get("kind") or "bg") != "bg"
    kept = ""
    if peer is not None and stop_turn and not woken and not terminal:
        t = threads_module().get(s["seat_id"])
        kept = wake_module().not_woken(t, s["current"], whole=True) if t is not None else ""
    if not peer or (stop_turn and not woken and not terminal and not kept):
        peer = woken_peer()
        if peer is None:
            return
        woken = True
    while True:
        try:
            if delivery:
                # An @all reaches only the live: to a session this send woke it is settled by passing (payload).
                control_module().push_live(peer, s["current"], delivery.payload(not woken), delivery.queue[-1],
                                           delivery.project.id, carried=delivery.carried(not woken))
            else:
                send_frame(socket_path_of(bound_peer(peer, s["current"])), text, sender)
            break
        except ReachHeld:
            reach_held()
            return
        except PushHeld as e:
            # The last hop, bound afresh, found the session held, gone or in another process: nothing pushed, owed.
            unlock(locks)
            if delivery is None:
                die("nothing was sent: %s" % e, EXIT_UNKNOWN)
            held_send(delivery, s["alias"], e, thread=chosen)
            if verb or wait:
                say_owed(s["current"])
            if wait:
                die("nothing was started: %s; no reply is waited for" % e, EXIT_UNKNOWN)
            return
        except SendFailed as e:
            if e.phase == "before":
                # Nothing reached the peer. A session that exited between the liveness check and the write is
                # woken; one whose process still runs (its record, read again), or one just woken, is not: a
                # launch would start a copy of it.
                if woken or running_now(s["current"]):
                    unsent()
                    unlock(locks)
                    if (verb or wait) and isinstance(delivery, SendDelivery) and thread_owed(s["current"]):
                        say_owed(s["current"])
                    die(quiet_inbox_refusal(ref), EXIT_UNKNOWN)
                if delivery is None:
                    unlock(locks)
                    die(UNRECORDED % ref, EXIT_UNKNOWN)   # gone mid-send: no wake for an unrecorded message
                warn("inbox socket delivery to %s failed before the frame was written (%s); waking it instead"
                     % (ref, e))
                peer = woken_peer()
                if peer is None:
                    return
                woken = True
                continue
            if delivery:
                delivery.settle()  # uncertain after a write: never pushed again
            unlock(locks)
            die("delivery to %s is UNCERTAIN — the frame was written but the close-out failed (%s). Not "
                "waking it and not re-sending id=%s; check the seat with sminos reply/attach before retrying." % (
                    ref, e, msg_id), 1)
    if delivery:
        delivery.settle()
    if woken:
        seat_pushed(s)
        wrote = True
    else:
        wrote = meta_set_if(s["seat_id"], {"status": "working", "updated": now()}, same_gen(s["gen"]))
    # The watcher's guard: the generation right after our write, read while
    # the lifecycle lock is still held.
    guard = same_gen(current_gen(s["seat_id"]))
    unlock(locks)
    if not wrote:
        warn("record of %s changed during delivery; status left as is" % ref)
    if verb and terminal and not woken:
        print("%s %s: a terminal holds it, so its turn runs on; the message went to it" % (verb, ref), flush=True)
    elif verb and kept and not woken:
        print("%s %s: its turn was not stopped, since a wake would not start it again (%s); the message went to the "
              "process that runs" % (verb, ref, hold_words(kept, s["current"])), flush=True)
    elif verb:
        fresh = reload_seat(s["seat_id"]) or s
        print("%s %s  [%s / %s]  via --bg --resume  status=working  turns=%s" % (
            verb, ref, fresh["short"], s["seat_id"], fresh["turns"]), flush=True)
    else:
        print("sent to %s%s" % (ref, " (woken)" if woken else ""), flush=True)
    if wait:
        wait_reply(s, msg_id, guard)


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
    die("--wait needs a seat, or a thread of this machine: '%s' is neither, so there is no reply to watch for — send "
        "without --wait" % target)


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
    holds the send owed (`held` too), for the daemon to deliver in order.
    Where the endpoint decides reach (P5 O18 D8) a queue holding any event
    the endpoint must admit (ReachGate.needs) is `held` as well: the uplink
    asks `reach?` about each, in order, and delivers each on its answer, so a
    refused earlier one is left out and the later ones go.

    An event decided held for a thread the session no longer fills
    (stale_hold: its sender was told it goes to no one) is left out of the
    text and settled in the writer's order, never ahead of an owed event
    before it (`stale`, settled as `skipped` is); one decided held for a
    thread whose record cannot be read (held_unreadable) holds the send
    owed, as deliver_next defers it (T2's M4)."""

    def __init__(self, project, session, writer, event):
        self.project, self.session, self.writer, self.event = project, session, writer, event
        self.lock = open(project_path(project, "delivered", reader_key(session) + ".lock"), "a")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.events = log_read(project)
        record = delivered_load(project, session)
        self.queue = [e for e in _owed(self.events, session, record)
                      if e["writer"] == writer and e["seq"] <= event["seq"]]
        self.stale = [e for e in self.queue if stale_hold(record, session, e)]
        unknown = next((e for e in self.queue if e not in self.stale and held_unreadable(record, e)), None)
        self.cursor = cursor_load(project, session)
        self.skipped = []
        self.held = "the endpoint decides its delivery" if words_held(event) else (
            self.checked() if sibling_module("sminos_rl10").cut_over() else None)
        if self.held is None and unknown is not None:
            self.held = "it waits behind %s, held for a thread whose record cannot be read" % event_ref(unknown)
        if self.held is None and self.queue:
            reach = ReachGate(project)
            if any(reach.needs(e, session) for e in self.queue if e not in self.stale):
                self.held = "the endpoint decides its delivery"   # P5 O18 D8: the uplink's, on its `reach` answer

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

    def carried(self, live):
        """The events the push's text carries (payload), each of which the
        reach gate checks: no stale one."""
        return [e for e in self.queue if (live or not e.get("wake")) and e not in self.stale]

    def payload(self, live):
        """The text of the one push. Ordinary delivery's policy applies: an
        @all (`wake`) reaches only the live, so to a stopped member it is
        settled by passing and left out of the resume; a stale hold is
        pushed to no one."""
        self.skipped = [e for e in self.queue if e.get("wake") and not live]
        return "\n\n".join(frame_of(self.project, e, self.events, self.session, self.cursor)
                             for e in self.queue if e not in self.skipped and e not in self.stale)

    def settle(self):
        for e in self.queue:
            delivered_settle(self.project, self.session, self.writer, e["seq"])
        self.queue = []
        self.release()

    def fail(self):
        # The skipped broadcasts and stale holds ahead of the first pushed
        # event settle; that event is the one pending.
        for e in self.queue:
            if e in self.skipped or e in self.stale:
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
    project = seat_project(s)
    if not s["current"] or project is None:   # a projectless seat: the owner-checked push (D8), no log to record in
        return None
    return record_message(project, s["current"], s["alias"], sender, via, text, msg_id)


def record_message(project, session, alias, sender, via, text, msg_id, deliver=True):
    """Append a `send` to the project's log, addressed to one session — from
    a session of another project, copied into that project's log too
    (record_copy) — and, unless the recipient is another machine's to
    deliver, open its SendDelivery. A message the log cannot hold is not
    sent: exit 1 first."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    fields = {"from": sender, "to": [{"session": session, "alias": alias}], "text": text, "msg_id": msg_id}
    if via and via != sender:
        fields["via"] = via
    home = caller_scope() if sid else None
    if home is not None and home.id != project.id:
        fields["from_project"] = home.id  # the sender's own project, where a reply finds it
    note_transcripts([session])   # before the append: what a concurrent push adds follows it (frame_landed)
    try:
        event = addressed_append(project, sid, fields["to"], "say" if sid else "human", fields,
                                 "send not delivered: it could not be recorded in %s's log" % project.name)
        writer = event["writer"]
        if event["seq"] is None:
            return WaitingSend(project, writer, event)
        if "from_project" in fields:
            record_copy(home, [(project, event)])
        return SendDelivery(project, session, writer, event) if deliver else event
    except OSError as e:
        die("send not delivered: it could not be recorded in %s's log (%s)" % (project.name, e), 1)


def deliver_sent(project, session, alias, delivery):
    """A send recorded for a session no process answers for, delivered as
    the sender's own call (deliver_next, `due`: T2's M3): woken and pushed,
    held for its thread and said why (§5), settled by another deliverer
    (settled_already, settled_sent), or owed behind an earlier event; what
    was printed, as `send` prints it. `delivery`, released."""
    member = next((m for m in members(project) if m.session == session), None)
    if member is None:
        print("recorded %s for %s: the daemon delivers it" % (event_ref(delivery.event), alias))
        nudge_daemon()
        return
    got = deliver_next(project, member, due=True)
    seq = delivery.event["seq"]
    mine = [o for ev, o in got["outcomes"] if (ev["writer"], ev["seq"]) == (delivery.writer, seq)]
    first = next((o for ev, o in got["outcomes"] if ev["writer"] == delivery.writer), "")
    marked = seq in _delivery(delivered_load(project, session), delivery.writer).get("held", {})
    if marked and (not mine or mine[0].startswith("held:")):
        why = hold_why(mine[0] if mine else first) or hold_now(session) or "starting"
        print("recorded %s for %s: %s" % (event_ref(delivery.event), alias, held_line(why, session=session)))
    elif mine and mine[0] in PUSHED:
        print("sent to %s%s" % (alias, " (woken)" if mine[0] in ("woken", "woken?") else ""))
        return
    elif not mine and settled_already(project, session, delivery.writer, seq):
        print(settled_sent(project, session, delivery.event, alias))
        return
    elif not mine:
        print("recorded %s for %s: owed behind an earlier message (%s)" % (event_ref(delivery.event), alias,
                                                                            first or "pending"))
    else:
        print("recorded %s for %s: %s" % (event_ref(delivery.event), alias, mine[0]))
    nudge_daemon()


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
        said = remote_line(m)
        print("recorded %s for %s%s" % (event_ref(e), m.alias, ": %s" % said if said else
                                        " on %s — its machine delivers it" % m.machine))
        nudge_daemon()
        return
    hold = held_now(m.session, due=True)   # first: the engine's records read afresh for what follows
    # What a hold's mark names: the thread the hold was decided for (Hold.thread), else the thread the recipient
    # is, as looked up; never the session's stamp read again after the decision.
    chosen = getattr(hold, "thread", None) or threads_module().stamp(m.session)
    peer = None if hold else peer_for_session(m.session)
    if not peer and hold:
        # A stopped thread this machine holds (T2's §4: not woken, for a reason): recorded and held, as a tagged
        # say is. The record and the hold decided in one step against the delivery pass (held_record).
        e, held = held_record(project, m.session, m.alias, sender, via, text, msg_id, chosen)
        ended_after_record(project, m.alias, m.session, e)   # ended since it was looked up: said so, exit 4
        if isinstance(e, WaitingSend):
            e.recorded_owed(m.alias)
            return
        print("recorded %s for %s: %s" % (event_ref(e), m.alias, stale_line() if held == "stale" else
                                          held_line(hold, session=m.session)))
        nudge_daemon()
        return
    if not peer and threads_module().current_record(m.session, fresh=True) is None:
        die("%s is not live (%s) — a session sminos did not spawn is reached only while it runs; "
            "sminos say records for it" % (m.alias, m.state), EXIT_UNKNOWN)
    if not peer:
        # No process answers for it (T2's M3): recorded, then delivered as every deliverer delivers, a stopped
        # thread woken by it or its message held, decided under the delivery lock (deliver_next, this call's own).
        delivery = record_message(project, m.session, m.alias, sender, via, text, msg_id)
        ended_after_record(project, m.alias, m.session, delivery)   # ended since it was looked up: said so, exit 4
        if isinstance(delivery, WaitingSend) or delivery.held:
            delivery.recorded_owed(m.alias)
            return
        delivery.release()
        deliver_sent(project, m.session, m.alias, delivery)
        return
    delivery = record_message(project, m.session, m.alias, sender, via, text, msg_id)
    # Ended since it was looked up (an end holds no lock this send holds before its settlement, which waits for
    # this delivery lock): decided here, under it, so the end's settlement is what becomes of it.
    ended_after_record(project, m.alias, m.session, delivery)
    if not isinstance(delivery, WaitingSend) and hold_now(m.session):
        held_send(delivery, m.alias, thread=chosen)   # the last hop, under the delivery lock: stopped since looked at
        return
    if delivery.held:
        delivery.recorded_owed(m.alias)
        return
    if not delivery.queue:
        delivery.release()
        print(settled_sent(project, m.session, delivery.event, m.alias))
        return
    if holder_module().handoff(peer.get("pid"), m.session) != "legacy":
        # O12 M4b: the process takes log-backed deliveries only with
        # receipts (or its mode is not chosen yet, or cannot be read): the
        # boundary every deliverer shares delivers the writer's owed events,
        # each with its own, this send among them.
        delivery.release()
        got = deliver_next(project, m)
        mine = [o for ev, o in got["outcomes"] if (ev["writer"], ev["seq"]) == (delivery.writer, delivery.event["seq"])]
        if not mine and settled_already(project, m.session, delivery.writer, delivery.event["seq"]):
            print(settled_sent(project, m.session, delivery.event, m.alias))
            return
        print("sent to %s (%s)" % (m.alias, mine[0] if mine else "owed behind an earlier message"))
        return
    try:
        control_module().push_live(peer, m.session, delivery.payload(True), delivery.queue[-1], project.id,
                                   carried=delivery.carried(True))
    except ReachHeld:
        delivery.held = "the endpoint decides its delivery"
        delivery.recorded_owed(m.alias)
        return
    except PushHeld as e:
        held_send(delivery, m.alias, e, thread=chosen)   # the last hop, bound afresh: nothing pushed, owed
        return
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
        if sid and m.session == sid:
            die("you cannot send to yourself")
        if has_ended(m):
            die(unreachable_hint(a.target, m.alias, m.short, [project], at="") or ended_refusal(a.target, m),
                EXIT_UNKNOWN)
        if a.wait and m.local and threads_module().current_record(m.session, fresh=True) is not None:
            # A thread of this machine with no seat here (T2's §6): woken if it is stopped, pushed to, and its
            # reply to this message waited for; or recorded, held and exit 4.
            verb_to_thread(project, m, a.msg, True, "", sender=sender, via=frm)
            return
        if a.wait and not m.local and m.state in HELD_STATES and wake_of(m) == "held":
            # Another machine's hold, as it published it: on a `stopped` state, or a `gone` one (state_wake).
            remote_held_wait(project, m, a.msg, sender, frm)
        if a.wait:
            refuse_wait(a.target)
        send_to_member(project, m, sender, frm, a.msg, msg_id)
        return
    if a.wait:
        ended_or_gone(a.target)   # a thread that has ended is said so, exit 4, as without --wait
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
        no_member(a.target, name, short, tiers, at="", ids=() if short else tiers)
    if UUID_RE.fullmatch(a.target.lower()):
        # A full session id, as the live lookup reads it across the org: what the org still knows of it.
        hint = unreachable_hint(a.target, a.target.lower(), "", org_scope(), "", ids_only=True)
        if hint:
            die(hint, EXIT_UNKNOWN)
    if scope is not None and not UUID_RE.fullmatch(a.target.lower()):
        no_member(a.target, name, short, [scope], () if short else
                  [(p, m) for p, m in match_members(name, "", org_scope(), ids=False) if p.id != scope.id], at="",
                  ids=() if short else org_scope())
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
    if codex_here and UUID_RE.fullmatch(a.target.lower()):
        tid, qid = codex_queue_send(a.target, text)
        if tid:
            report_codex_queued(tid, qid)
            return
    what = "no seat, live session, or codex thread" if codex_here else "no seat or live session"
    die("%s matching '%s'" % (what, a.target), EXIT_UNKNOWN)


# ------------------------------------------------ reply / sync / status


def cmd_reply(a):
    kind, found = find_seat(a.seat, caller_scope())
    if kind == "ambiguous":
        die(ambiguous_seat(a.seat, found), EXIT_UNKNOWN)
    if kind != "ok":
        # A session with no seat (T2's M4: what a `--wait` that expired names): its transcript's last reply.
        target = find_target(a.seat)
        if target[0] != "member":
            die("no seat or session matching '%s'" % a.seat, EXIT_UNKNOWN)
        m = target[2]
        if not m.local:
            die("%s runs on %s: its reply is read there" % (m.alias, m.machine), EXIT_UNKNOWN)
        print("%s  [%s]  state=%s" % (m.alias, m.short, m.state))
        print("--- latest reply ---")
        print(transcript_reply(m.session, m.alias) or "(no reply yet)")
        return
    s = found
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
            why = "status of %s not recorded in %s's log" % (m.alias, project.name)
            try:
                got = [addressed_append(project, os.environ.get("CLAUDE_CODE_SESSION_ID") or "",
                                        [{"session": m.session, "alias": m.alias}], "status",
                                        {"session": m.session, "text": line}, why)]
            except OSError as e:
                die("%s: %s" % (why, e), 1)
            writer = got[0]["writer"]
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


def seat_files(seat_id):
    """Every file of a seat: its record, its reply, its error, its resume lock."""
    return (meta_path(seat_id), reply_path(seat_id), err_path(seat_id), os.path.join(root(), seat_id + ".resume.lock"))


def unlink_seat_files(seat_id):
    """Delete a seat's files under .metalock, so a guarded writer holding the
    same lock sees the record gone (and stands down) rather than racing the
    unlink with its os.replace."""
    with open(os.path.join(root(), ".metalock"), "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            for p in seat_files(seat_id):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def locked_fresh(s0, verb, session="", locks=None):
    """Take the seat's lifecycle locks (or use `locks`, those its caller
    holds already) and re-load the record; (locks, seat). Given `session`,
    the one a name bound (find_target), a seat that no longer holds it is
    refused: an address names a session, and a refill after the name was
    resolved must not put another session in its place."""
    locks = lock_seat(s0) if locks is None else locks
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
    """End one member's thread and stop what sminos can stop. Nothing it
    spawned goes with it: a spawner is provenance, not a host. A thread that
    made a host devcloud still has is not ended, nor one whose answer is
    unknown unless a person at a terminal passes it (`--owner-unknown`,
    refused inside a session; owner_guard). The end is recorded before
    anything is stopped (T1's M4): a session that retires itself may be
    ended by the stop."""
    if a.owner_unknown and os.environ.get("CLAUDE_CODE_SESSION_ID"):
        die("--owner-unknown is for a person at a terminal, and this runs inside a session: nothing was retired. "
            "Report the refusal to your human instead", 1)
    # A purge left open (its verb cut short), as it stands before the lookup's reconciliation finishes it.
    purging = {x["seat_id"]: x for x in seats() if (x.get("pending") or {}).get("last") == "purge"}
    target, bound = find_target(a.seat), None
    if target[0] == "none" and (ended := ended_target(a.seat)) is not None:
        target, bound = ended, ended[2].thread
    if target[0] == "none":
        die("no seat or member matching '%s'" % a.seat, EXIT_UNKNOWN)
    how = OwnerAsk(a.seat, "purge" if a.purge else "retire", a.owner_unknown)
    if target[0] == "seat":
        if a.purge and replayed_purge(purging, target[1], "purged"):
            return
        _retire_one(target[1], a.purge, target[2], how)
        return
    project, m = target[1], target[2]
    if not m.local:
        die("%s is on %s" % (m.alias, m.machine), EXIT_UNKNOWN)
    retire_member(project, m, a.purge, how=how, thread_id=bound)


def ended_target(q):
    """("member", project, member) for a thread its human opened, of this
    machine, that has ended and holds no seat, named by a full id — its
    session's or the thread's own — as its ended row (View.ended) answers
    to: what `retire --purge` and `remove` reach once no member and no seat
    answers the name (find_target), the record set aside to purge. None
    for none. A row is the log's and outlives its record: only one whose
    thread's record is still this machine's, ended, with that session
    current, answers, and the verb acts on that thread's record alone
    (retire_member's `thread_id`), never on another thread its session has
    been since."""
    if not UUID_RE.fullmatch(q):
        return None
    threads = threads_module()

    def archived(m):
        t = threads.get(m.thread) if m.thread else None
        return t is not None and t["opened"] == "human" and t["current"] == m.session and threads.record_ended(t)
    hits = [(p, m) for p in known_projects() for m in view_of(p).ended
            if m.local and m.opened == "human" and q in (m.session, m.thread) and archived(m)]
    if not hits:
        return None
    last = last_project(hits[0][1].session)
    project, m = next(((p, m) for p, m in hits if last is not None and p.id == last.id), hits[0])
    return ("member", project, m)


class OwnerAsk(NamedTuple):
    """How a verb that ends a thread on purpose asks devcloud first
    (owner_guard): the name it was given, the verb ("retire", "purge" or
    "remove"), and whether a person at a terminal passes an unknown answer
    (`retire --owner-unknown`)."""
    name: str
    verb: str
    owner_unknown: bool = False


def owner_guard(how, records, label):
    """The question every end on purpose asks before it writes anything
    (T1's M5): devcloud's answer about every session the thread has had
    (`records`: its record, and a seat that follows it; sminos_threads.
    owner_sessions). Owned: refused, exit 1, naming each host and
    `devcloud vm down <name>` as the way on; unknown: refused naming what
    could not be asked, unless the verb was given `--owner-unknown` and the
    person confirms it at the controlling terminal (exit 1 where there is
    none). Returns the short ids asked, which the end rechecks under the
    record's lock (sminos_threads.asked_all): a session the thread gained
    since was not asked about."""
    threads = threads_module()
    shorts = threads.shorts_of([x for r in records for x in threads.owner_sessions(r)])
    owned = threads.owned_among(threads.owned_by(shorts), shorts) if shorts else threads.Owned("none", [], [], [])
    if owned.answer == "none":
        return owned.asked
    done = {"retire": "retired", "purge": "retired", "remove": "removed"}[how.verb]
    what = threads.owned_words(owned)
    if owned.answer == "owned":
        die("%s is not %s: %s" % (label, done, what), 1)
    anyway = "sminos retire %s%s --owner-unknown" % (shlex.quote(how.name), "" if how.verb == "retire" else " --purge")
    if not how.owner_unknown:
        die("%s is not %s: %s. Its human, at a terminal, may retire it anyway: %s" % (label, done, what, anyway), 1)
    prompt = "%s: %s. Retire it anyway? [y/N] " % (label, what)
    if not sibling_module("sminos_visibility").confirmed(
            label, None, prompt=prompt, none="--owner-unknown needs a person at a terminal to confirm it, and this "
                                             "has none: nothing was retired"):
        die("%s: not confirmed; nothing was retired" % label, 1)
    return owned.asked


def retire_member(project, m, purge, verb="retired", how=None, thread_id=None):
    """The end of a member of this machine that holds no seat (`retire`,
    `retire --purge`, `remove`; Interfaces §6 rows 9 and 11). A thread its
    human opened ends by its record (end_human): `ended`, with the process
    seen, and the stamped `retired` `retire` owed, in one write; then the
    event, the settlement of what was held for it, and as the last step the
    record set aside, or for a purge deleted. A session no record tracks
    (lane B) is retired as before, by its event alone. Then, once the
    retirement is in the log (retired_in_log), its harness row, if the
    harness lists it with an id (a background session), is stopped; an
    interactive session has none, and runs on in its human's terminal. The
    end names the process it saw and holds for that process's life: only
    another process, or one started after it, returns it (its human
    reopening it). `thread_id`: the thread the name named (ended_target),
    whose record alone is acted on, refused when it is gone or no longer
    has this session current."""
    threads = threads_module()
    thread = threads.thread_of(m.session) if thread_id is None else threads.get(thread_id)
    if thread_id is not None and (thread is None or thread["current"] != m.session):
        die("thread %s has no record of this machine with session %s any more (purged, or its session is another "
            "thread's now): nothing was %s" % (thread_id[:8], m.short, verb), EXIT_UNKNOWN)
    human = thread is not None and thread["opened"] == "human" and thread["current"] == m.session
    if purge and not human:
        die("%s holds no seat and no thread record of this machine: there is no record to purge" % m.alias)
    if thread is None or thread["current"] != m.session:
        asked = threads.Exempt("no-thread")
    elif threads.record_ended(thread) and not purge:
        asked = threads.Exempt("ended")
    else:
        asked = owner_guard(how or OwnerAsk(m.alias, "purge" if purge else "retire"), [thread],
                            "%s (session %s)" % (m.alias, m.short))
    # The record's wake lock before the process is looked for, held through the end's begin (T2's M2): a wake
    # cannot start a process between what the end records of it (`ended.pid`) and its write.
    if human:
        held_settled(thread["thread"], project)
        fresh = threads.get(thread["thread"])
        if fresh is None or fresh["current"] != m.session or threads.record_ended(fresh) != threads.record_ended(thread):
            release_wake(thread["thread"])
            die("%s changed while its end was decided (an operation left open was finished): nothing was written; "
                "run it again" % m.alias, EXIT_UNKNOWN)
        thread = fresh
    try:
        agents_refresh()
        row = agent_row(session_id=m.session)
        proc = running_now(m.session)
        by, pid = caller_alias(), (proc.get("pid") if proc else None)
        if human and end_human(project, thread, m.session, by, pid, purge, asked) == "already":
            die("%s was retired already; nothing more was recorded" % m.alias, EXIT_UNKNOWN)
    finally:
        if human:
            release_wake(thread["thread"])
    if not human:
        # Decided and appended under both thread stores' locks, which every record made or claimed for a session
        # takes (sminos_threads.claims_held), the log's locks inside them: a session a reconciliation made a
        # thread since (lane A now) is no longer what was cleared, asked about or exempt (asked_all), and none is
        # made for it before the retirement is in the log.
        with threads.claims_held():
            forget_caches()
            t = threads.thread_of(m.session)
            if not (t is None or t["current"] != m.session or threads.asked_all(t, asked)):
                die("%s changed while its end was decided (it is a thread of this machine now): nothing was written; "
                    "run it again" % m.alias, EXIT_UNKNOWN)
            lifecycle(project, m.session, "retired", by=by, reason="retire", **({"pid": pid} if proc else {}))
    # The turn the end saw (its row then), never a process started since (still_seen).
    stopped = bool(row and row.get("id")) and (proc is None or still_seen(proc, m.session)) \
        and retired_in_log(project, m.session) and claude_stop(row["id"])
    kept = "its record deleted" if purge else "it returns when its human reopens it" if human \
        else "it holds no seat, so nothing is kept"
    if proc and not stopped:
        print("%s %s (session %s%s): %s's session keeps running in its terminal; it re-joins when resumed as a new "
              "process" % (verb, m.alias, m.short, "; its record deleted" if purge else "", m.alias))
    else:
        print("%s %s (session %s; %s)" % (verb, m.alias, m.short, kept))


def end_human(project, thread, sid, by, pid, purge, asked=None):
    """A retire of a thread its human opened, journaled on its record:
    "ended" once this call's end (or, for a purge, the purge) began;
    "already" when the record had ended already and no purge was asked.
    Begun only while, under the record's lock, it is still the record whose
    current session is `sid`, not ended, and the session's membership in
    effect is a `joined` in `project` (membership_here); a record that
    changed so is refused, exit 4, with nothing written. A purge that finds
    the record ended (by another retire, or the rule, that won the claim)
    purges that end: its own entry, owing a `retired` only while the log
    still holds the session a member. Never a second, unjournaled
    retirement, and never a deletion reported that did not begin. Every
    session the record has had is among the short ids devcloud was asked
    about (`asked`, owner_guard), read again under the lock."""
    threads = threads_module()
    tid = thread["thread"]
    fields = {"by": by, "reason": "retire", **({"pid": pid} if pid else {})}
    seat = seat_over(sid, "purge" if purge else "retired", tid)

    def live_member(t):
        return t["opened"] == "human" and t["current"] == sid and not threads.record_ended(t) \
            and threads.asked_all(t, asked) \
            and latest_membership(_own_events(project, sid)) == "joined" and membership_here(project, sid)

    began = []
    if not threads.record_ended(thread):
        thread_transition(project, tid, "end", [{"kind": "retired", "session": sid, **fields}], required=True,
                          began=began, fields={"ended": {"at": now(), "reason": "retire", "by": by, "pid": pid}},
                          guard=live_member, settle=sid, last="purge" if purge else "aside", seat=seat)
        if began:
            return "ended"
    t = threads.get(tid)
    if t is None or t["current"] != sid or not threads.record_ended(t):
        die("%s changed while its end was decided (no longer this record's session, or no longer a member here): "
            "nothing was written" % sid[:8], EXIT_UNKNOWN)
    if not purge:
        if seat is not None:
            threads.project_seat(seat, tid)   # an end made before its seat followed it: in line now
        return "already"
    member = latest_membership(_own_events(project, sid)) == "joined"
    thread_transition(project, tid, "end", [{"kind": "retired", "session": sid, **fields}] if member else [],
                      required=True, began=began,
                      guard=lambda r: r["current"] == sid and threads.record_ended(r) and threads.asked_all(r, asked),
                      settle=sid, last="purge", seat=seat)
    if not began:
        die("the purge of %s could not begin (its record changed meanwhile): nothing was deleted" % sid[:8],
            EXIT_UNKNOWN)
    return "ended"


def keep_end(data, fields, session):
    """An edit of a seat (`seat add` of an existing one), under the record's
    lock: a seat whose end stands for the session it keeps (`ended`, or an
    older copy's `status` retired) keeps it, `status` and the `updated` an
    older copy's end is dated by left as they are (D1: its own occupant
    added again is no return; join_seat returns it to a process its end did
    not see). `fields` changed in place. False, nothing written, for a
    record with an open entry (§6, 6: nothing writes through it)."""
    if data.get("pending"):
        return False
    same = not session or str(data.get("current") or "") == session
    if same and (isinstance(data.get("ended"), dict) or data.get("status") == "retired"):
        fields.pop("status", None)
        fields.pop("updated", None)
    return True


def seat_over(sid, to, thread_id):
    """The seat an older copy gave the session of a thread its human opened,
    as that record's entry brings it in line (`to`: "retired", "idle" or
    "purge"; sminos_threads._project_seat), or None for none. The seat is
    never the thread's authority: it is written only by the record's own
    journal, and only to follow it. `thread_id`: the record that ends, read
    by its id (a session's canonical record by then may be another's)."""
    t = threads_module().get(thread_id) if sid else None
    if t is None or t["opened"] != "human" or t["current"] != sid:
        return None
    s = next((s for s in seats() if s["current"] == sid), None)
    return {"id": s["seat_id"], "session": sid, "to": to} if s is not None else None


def retired_in_log(project, sid):
    """Whether the session's membership in effect, read afresh from the log,
    is a `retired` that ends it (END_REASONS): what a verb's stop waits for
    (T1's M4), since stopping a session that retires itself ends its caller.
    A record that says ended, or an open end entry, is no evidence of it."""
    if not sid or project is None:
        return True   # no log to hold it: the record is the whole of the end
    e = threads_module().in_effect(_own_events(project, sid))
    return e is not None and e["kind"] == "retired" and e.get("reason") in END_REASONS


def seat_owner_guard(s0, purge, how):
    """owner_guard for a seat's end, asked before its locks are taken (the
    question can take a minute): the record that ends (its session's
    canonical one, else the seat's own) and the seat. Nothing is asked for
    a seat that is no thread (a lane B session's) or a retire of one ended
    already, which ends nothing: an Exempt saying which, which the end
    proves again under the locks (end_and_stop, asked_all)."""
    threads = threads_module()
    cur = s0["current"]
    t = threads.thread_of(cur) if cur else None
    own = threads.get(s0["seat_id"])
    t = t if t is not None and t["current"] == cur else own
    if t is None:
        return threads.Exempt("no-thread")
    if threads.record_ended(t) and not purge:
        return threads.Exempt("ended")
    return owner_guard(how, [t] + ([own] if own is not None and own is not t else []),
                       "%s/%s (session %s)" % (s0["group"], s0["alias"], cur[:8]) if cur
                       else "%s/%s" % (s0["group"], s0["alias"]))


def _retire_one(s0, purge, session="", how=None):
    asked = seat_owner_guard(s0, purge, how or OwnerAsk("%s/%s" % (s0["group"], s0["alias"]),
                                                        "purge" if purge else "retire"))
    locks, s = locked_fresh(s0, "retire", session)
    try:
        if s["engine"] == "codex":
            hint = "legacy codex-CLI worker — no resume path; remove with: sminos remove %s/%s" % (s["group"], s["alias"])
        elif s["current"]:
            hint = 'sminos fill %s/%s --resume "<task>"' % (s["group"], s["alias"])
        else:
            hint = 'sminos fill %s/%s "<task>"' % (s["group"], s["alias"])
        end_and_stop(s, purge, asked)
        if purge:
            print("purged %s/%s [%s] from the registry (session transcript left intact)%s" % (
                s["group"], s["alias"], s["seat_id"], worktree_note(s)))
        else:
            print("retired %s/%s [%s] (seat kept; re-fill with: %s)%s" % (
                s["group"], s["alias"], s["seat_id"], hint, worktree_note(s)))
    finally:
        unlock(locks)


def end_and_stop(s, purge, asked=None):
    """A seat's end, then its turn stopped (stop_session) only once the
    retirement is in the log (retired_in_log): a session that retires
    itself, whose stop can end its caller, is stopped only after its record
    and its event are written (T1's M4), and an end whose event could not be
    appended stops nothing. Only what the end saw is stopped, while it is
    still that (stop_seen_turn): a process started since is one the end did
    not see, which returns the seat. Which record
    ends is the canonical one of the seat's session (thread_of): a thread
    its human opened that an older copy seated ends by that record
    (end_human), its entry bringing the seat in line, retired or for a
    purge deleted; else the seat's own (end_seat). The verb's lifecycle
    locks are held. What may keep a thread from its end (M5: devcloud's
    answer) is asked by the verb before this (seat_owner_guard), and what
    cleared it (`asked`: the short ids asked about, or why none was needed)
    is proved again here, under the seat's locks, and by the end under the
    record's lock (sminos_threads.asked_all)."""
    cur = s["current"]
    threads = threads_module()
    thread = threads.thread_of(cur) if cur else None
    record = thread if thread is not None and thread["current"] == cur else threads.get(s["seat_id"])
    # Whether the end that stands recorded its process, read while its record stands (a purge deletes it).
    known = record is not None and (record["opened"] == "human" or threads.seat_ended(record))
    if record is not None and not threads.asked_all(record, asked):
        # Read under the seat's locks: a refill or a return since devcloud was asked (or since no question was
        # needed) put this seat in a state the question did not clear.
        die("seat %s/%s changed while its end was decided (it now holds %s): nothing was written; run it again"
            % (s["group"], s["alias"], cur[:8] or "no session"), EXIT_UNKNOWN)
    project = seat_project(s)
    if record is not None:
        # The record's wake lock before the process is looked for, held through the end's begin (T2's M2): a wake
        # cannot start a process between what the end records of it and its write. Taken over a record with no open
        # entry (held_settled), whose replay is done before it, never under it.
        held_settled(record["thread"], project)
        fresh_seat, fresh = reload_seat(s["seat_id"]), threads.get(record["thread"])
        if fresh_seat is None or fresh_seat["current"] != cur or fresh is None or fresh["current"] != record["current"] \
                or threads.record_ended(fresh) != threads.record_ended(record):
            release_wake(record["thread"])
            die("seat %s/%s changed while its end was decided (an operation left open was finished): nothing was "
                "written; run it again" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        s, record = fresh_seat, fresh
        if thread is not None and thread["thread"] == record["thread"]:
            thread = record
    seen = running_now(cur) if cur else None   # the process the end sees, and records
    agents_refresh()
    turn = harness_row(s) if cur else None   # and the harness's turn of it, by its id
    try:
        if thread is not None and thread["opened"] == "human" and thread["current"] == cur:
            project = last_project(cur) or project
            end_human(project, thread, cur, caller_alias(), seen.get("pid") if seen else None, purge, asked)
            if purge:
                purge_superseded(s, cur)   # the seat over it, kept by the entry when it holds another session now
        else:
            end_seat(s, purge, asked)
    finally:
        if record is not None:
            release_wake(record["thread"])
        if retired_in_log(project, cur) and end_saw(record, seen, known):
            stop_seen_turn(s, seen, turn)


def end_saw(before, seen, known):
    """Whether the end that stands after a verb's end is one that saw
    `seen`, the process this verb saw, so that stopping it stops what that
    end ended: the verb's own end (the record, `before`, read under the
    seat's locks, had none; or no record tracks the seat), else an end that
    recorded that very process (sminos_threads.returns: a process an end did
    not see returns its thread, and a repeated retire never stops it).
    `known`: whether that end's process is recorded, read with `before`,
    before a purge deleted the record it is read from."""
    threads = threads_module()
    if before is None or not threads.record_ended(before):
        return True
    after = threads.get(before["thread"])
    if threads.record_ended(after):
        return seen is not None and not threads.returns(after, seen)
    return seen is not None and not threads.returns(before, seen, known=known)


def stop_seen_turn(s, seen, turn):
    """The stop of what an end saw of a seat's session, and only that: its
    harness turn (`turn`, the row then) while the harness still shows that
    row's id for it, the process the end saw (`seen`) still that process
    (still_seen); a process the end saw with no row, by the row the harness
    shows for its session now or else the seat's recorded short, only if,
    read after that query and right before the stop, the process is still
    the one the end saw: nothing is rediscovered unbound. Nothing when the
    end saw neither: a process started since is one the end did not see,
    which returns the seat."""
    if s["engine"] == "codex" or (seen is not None and not still_seen(seen, s["current"])):
        return
    if turn and turn.get("id"):
        agents_refresh()
        now_ = harness_row(s)
        if now_ and now_.get("id") == turn["id"]:
            claude_stop(turn["id"])
    elif seen is not None:
        agents_refresh()
        row = harness_row(s)
        target = str(row["id"]) if row and row.get("id") else \
            s["short"] if s["short"] and identity_local(s["host"], s["boot_id"], s["current"]) else ""
        if target and still_seen(seen, s["current"]):   # the identity again, after the harness's answer
            claude_stop(target)


def still_seen(seen, sid):
    """Whether the process an end saw (`seen`, its engine record then) still
    holds the session, read afresh: the same pid, started at the same time.
    False when the end saw none."""
    if not seen:
        return False
    now_ = running_now(sid)
    return bool(now_) and str(now_.get("pid")) == str(seen.get("pid")) \
        and process_started(now_) == process_started(seen)


def end_seat(s, purge, asked=None):
    """A seat's end (retire, retire --purge, remove), under its lifecycle
    locks: the record first — `status` retired and `ended`, with the event
    owed, in one write (Interfaces §6, the end) — then the event, then, for
    a purge, the seat's files deleted as the entry's last step. A purge of
    a seat whose record says it ended already is journaled too: the entry
    (owing the `retired` only while the log still holds the session a
    member), then the deletion, so a cut leaves the entry to replay. An
    open entry the record holds is finished first; one that cannot be
    (its log not written) stops the verb with nothing else done. The
    process seen running the session is recorded (`pid`): the end holds
    against it, and only another process returns the seat. A seat that is
    no thread (no session, a lane B session's) is retired as before: the
    record, then the event; purged, the event, then its files. Begun only
    while every session the record has had is among the short ids devcloud
    was asked about (`asked`, T1's M5)."""
    by = caller_alias()
    project = seat_project(s)
    threads = threads_module()
    proc = session_running(s["current"]) if s["current"] else None
    pid = proc.get("pid") if proc else None   # the process the end saw: it does not return the seat (§6, row 12)
    if s.get("pending"):
        # An open entry, whatever the seat holds (a refill cut with the seat vacant and its new session queued
        # behind the launch's entry): finished before anything else, as every transition does before its own.
        if not finish_thread(s["seat_id"], project=project if project is not None and not guessed(project) else None):
            raise LogWriteFailed("%s/%s holds a transition whose events could not all be recorded; nothing more "
                                 "was done, and the next reading verb finishes it" % (s["group"], s["alias"]))
        fresh = reload_seat(s["seat_id"])
        if fresh is None:
            return   # the replay finished a purge: the seat is gone, and its end recorded
        if fresh["current"] != s["current"]:
            die("seat %s/%s changed while its end was decided (an operation left open was finished, and it now "
                "holds %s): nothing was written; run it again" % (s["group"], s["alias"],
                                                                  fresh["current"][:8] or "no session"), EXIT_UNKNOWN)
    if s["current"] and project is not None and not guessed(project):
        if not finish_thread(s["seat_id"], project=project):
            raise LogWriteFailed("%s/%s holds a transition whose events could not all be recorded in %s's log; "
                                 "nothing more was done, and the next reading verb finishes it"
                                 % (s["group"], s["alias"], project.name))
        if reload_seat(s["seat_id"]) is None:
            return   # the replay finished a purge: the seat is gone, and its end recorded
        thread = threads.ensure(s["current"], seat=reload_seat(s["seat_id"]) or s, project=project)
        fresh = reload_seat(s["seat_id"])
        if thread is not None and fresh is not None:
            cur = s["current"]
            retired = {"kind": "retired", "session": cur, "by": by, "reason": "retire", **({"pid": pid} if pid else {})}
            began = []
            if not isinstance(fresh.get("ended"), dict):
                at = now()
                # Begun only for the record as read: its session, and no end of this code's since (an older
                # copy's, its `status` alone, is the one this end writes over).
                thread_transition(
                    project, s["seat_id"], "end", [retired], required=True, began=began,
                    fields={"status": "retired", "updated": at,
                            "ended": {"at": at, "reason": "retire", "by": by, "pid": pid}},
                    guard=lambda t: t["current"] == cur and not threads.seat_ended(t) and threads.asked_all(t, asked),
                    settle=cur, last="purge" if purge else None)
                fresh = reload_seat(s["seat_id"])
                if began and purge:
                    purge_superseded(s, cur)
                if began or fresh is None:
                    return   # ended by its record, or purged by a replay meanwhile
                if fresh["current"] != cur or not isinstance(fresh.get("ended"), dict):
                    die("seat %s/%s changed while its end was decided: nothing was written" % (
                        s["group"], s["alias"]), EXIT_UNKNOWN)
            if purge:
                # Ended already (the rule, another retire): that end's record purged, journaled.
                member = latest_membership(_own_events(project, cur)) == "joined"
                thread_transition(project, s["seat_id"], "end", [retired] if member else [], required=True,
                                  began=began, guard=lambda t: t["current"] == cur and threads.record_ended(t)
                                  and threads.asked_all(t, asked), settle=cur, last="purge")
                if not began and reload_seat(s["seat_id"]) is not None:
                    die("the purge of seat %s/%s could not begin (its record changed meanwhile): nothing was "
                        "deleted" % (s["group"], s["alias"]), EXIT_UNKNOWN)
                if began:
                    purge_superseded(s, cur)
            return
    # Decided and written under both thread stores' locks, which every record made or claimed for a session takes
    # (sminos_threads.claims_held), the log's locks inside them: a seat a reconciliation made a thread since (its
    # session lane A now) is no longer what was cleared or exempt (asked_all), and is neither retired nor deleted
    # here by a write outside its journal.
    with threads.claims_held():
        forget_caches()
        cur = s["current"]
        fresh = reload_seat(s["seat_id"])
        t = threads.thread_of(cur) if cur else None
        t = t if t is not None and t["current"] == cur else threads.get(s["seat_id"])
        if fresh is None or fresh["current"] != cur or fresh.get("pending") \
                or (t is not None and not threads.asked_all(t, asked)):
            die("seat %s/%s changed while its end was decided: nothing was written; run it again" % (
                s["group"], s["alias"]), EXIT_UNKNOWN)
        if purge:
            # The event before the files (T1's M4): a cut never leaves the session joined with nothing here saying
            # why.
            lifecycle(project, cur, "retired", by=by, reason="retire", **({"pid": pid} if pid else {}))
            for path in seat_files(s["seat_id"]):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            return
        path = meta_path(s["seat_id"])
        with open(path) as f:
            data = json.load(f)
        data.update(status="retired", updated=now(), gen=int(data.get("gen") or 0) + 1)
        _write_record(path, data)
        lifecycle(project, cur, "retired", by=by, reason="retire", **({"pid": pid} if pid else {}))


def replayed_purge(purging, s0, verb):
    """Whether a purge of seat `s0` was left open before this verb (its
    snapshot in `purging`, taken before the lookup) and its lookup's
    reconciliation has finished it: then the verb starts no purge of its
    own, and reports the entry's outcome for the session it settled —
    done (the seat gone; its stop was the entry's, purge_stop), or
    superseded, exit 4 (another sminos gave the seat another session, which
    the entry's last step keeps). False when there was none, or it is open
    still (the verb's own end finishes it)."""
    snap = purging.get(s0["seat_id"])
    now_ = reload_seat(s0["seat_id"])
    if snap is None or (now_ is not None and now_.get("pending")):
        return False
    if now_ is None:
        print("%s %s/%s [%s] (a purge of it left open was finished; chat history kept)%s" % (
            verb, s0["group"], s0["alias"], s0["seat_id"], worktree_note(s0)))
        return True
    purge_superseded(now_, snap["pending"].get("settle") or snap["current"])
    return False


def purge_superseded(s, cur):
    """A purge of seat `s` whose session `cur` the seat no longer holds once
    the purge finished (an older sminos refilled it meanwhile: the entry's
    last step deletes no record that holds another session): exit 4 saying
    the seat was not removed, the end of `cur` recorded."""
    fresh = reload_seat(s["seat_id"])
    if fresh is not None and fresh["current"] != cur:
        die("seat %s/%s was not removed: it holds session %s now (another sminos gave it that session while it was "
            "purged); the end of session %s is recorded — retire or remove the seat again for the session it holds"
            % (s["group"], s["alias"], fresh["current"][:8] or "none", cur[:8]), EXIT_UNKNOWN)


def cmd_remove(a):
    """A seat's end and its record deleted, or a thread's its human opened
    (D1: the verbs that only manage a record apply to every thread)."""
    how = OwnerAsk(a.seat, "remove")
    # A purge left open (its verb cut short), as it stands before the lookup's reconciliation finishes it.
    purging = {x["seat_id"]: x for x in seats() if (x.get("pending") or {}).get("last") == "purge"}
    # find_target's precedence, as retire's: a full id that is a seat's own and also the current session of a
    # thread of its own (its first occupant, reopened) names that session, never the seat it left.
    found = find_target(a.seat)
    if found[0] == "none" and (ended := ended_target(a.seat)) is not None:
        retire_member(ended[1], ended[2], True, verb="removed", how=how, thread_id=ended[2].thread)
        return
    s0, bound, opened = resolve_seat_or_opened(a.seat, "remove it", found=found)
    if opened is not None:
        retire_member(opened[0], opened[1], True, verb="removed", how=how)
        return
    if found[0] == "seat" and replayed_purge(purging, s0, "removed"):
        return
    asked = seat_owner_guard(s0, True, how)
    locks, s = locked_fresh(s0, "remove", bound)
    try:
        # A removed seat's session leaves the family with it.
        end_and_stop(s, True, asked)
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
    word (`gone` once the org retired its machine), `@<machine>`, and how
    long ago it was published."""
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
    (view_projects). Any filter widens to every project known here but one
    that has left this machine (has_left) before it narrows: a project named
    first (as before), or with --project; --machine, --state, --here, --org
    and words narrow the rows. Under --org or --project every argument is a
    word."""
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
    return sorted((p for p in known_projects() if not has_left(p)), key=lambda p: (p.name, p.id)), words, False


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
        if not (isinstance(sid, str) and UUID_RE.fullmatch(sid) and isinstance(cwd, str) and cwd) or sid in seen:
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
        if not (isinstance(sid, str) and UUID_RE.fullmatch(sid)) or sid in shown or sid == me:
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
    `· not woken:` why this machine holds a stopped thread of it, of either
    kind (hold_for, the cached hold: T2's §5 words, the ceiling named when
    it is the cause), `· active` the age of its last activity."""
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
    # A stopped row's hold (T2's §5): a `gone` row says already that no conversation of it is here.
    why = hold_for(m.session) if m.local and m.session and m.state == "stopped" else ""
    if why:
        rest.append("· not woken: " + hold_words(why, m.session))
    if m.end == "retire":
        rest.append("· retired" + (" by " + m.end_by if m.end_by else ""))
    elif m.end == "ended":
        rest.append("· ended after it stopped")
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


SUBAGENT_STATES = "subagents"   # under $SMINOS_HOME: <session>.json, a session's ended subagents' states (sminos_subagents.Memo)


def subagents_view(session, stall_minutes=None):
    """(view, scope): a session's subagents (sminos_subagents.Subagents) with
    the engine's word from its bridge when one answers, and the scope the
    view read — its transcript, whether its process runs, where the
    lifecycle came from (`engine` with a bridge, else `disk`). The view's
    notes say what could not be read; its ended states are kept under
    $SMINOS_HOME/subagents/<session>.json (`view.keep()` writes them)."""
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
            session[:8], os.path.join(session_config_dir(session), "projects"),
            "only the agents its bridge holds are listed" if bridge is not None else "no subagent can be read"))
    notes += peer_notes()
    stall = V.STALL_SECONDS if stall_minutes is None else stall_minutes * 60
    cache = os.path.join(root(), SUBAGENT_STATES, session + ".json") if UUID_RE.fullmatch(session) else None
    view = V.Subagents(tpath or "", live=rec is not None, started=started, bridge=bridge, stall=stall, notes=notes,
                       cache=cache)
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
    if UUID_RE.fullmatch(q):
        return q
    target = find_target(q)
    if target[0] == "none":
        # A running session of this machine that is no member: by the engine's name for it, or its short.
        hits = {r["sessionId"] for r in peer_records()
                if isinstance(r.get("sessionId"), str) and UUID_RE.fullmatch(r["sessionId"]) and peer_running(r)
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
    another session's on this machine. Text: who you are, how many run, wait
    on background or stall, at every depth, those as a tree (--depth: the
    top levels, a row saying what it folds), then those ended in the last
    ten minutes (five at most, newest first), and how many else are done —
    each past agent (sminos_subagents.Subagents.past) counted, never read;
    --all: the counts of every state and every agent in the tree; --done N:
    the N ended last, newest first, each with its outcome. --json: {self,
    scope, counts, agents, notes}, every agent of the tree (or the --done
    list), whatever its state."""
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
    # Every agent's state only where the output carries it: the default view derives the live ones alone.
    counts = view.counts() if a.json or (a.all and a.done is None) else None
    ended = []
    if a.done is not None:
        agents = view.done(a.done)
    else:
        agents = view.tree(every=a.all or a.json, depth=a.depth)
        if counts is None:
            ended = view.recent()
    if inspection:
        for e in agents:
            e["inspectionOnly"] = True
    if a.json:
        print(json.dumps({"self": me, "scope": scope, "counts": counts, "agents": agents, "notes": view.notes},
                         indent=2))
        view.keep()
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
        header = V.counts_line(counts) if a.all else V.active_line(view.active_counts())
        print((whose + " " if not inspection else "  ") + header
              + ("" if scope["live"] else " — the session runs no process"))
        lines = V.tree_lines(agents, ended)
        if lines:
            print("\n".join(lines))
        elif not view.agents:
            print("  (no subagents in session %s: %s)" % (session[:8], view.dir or "no transcript"))
        else:
            print("  (none is live)")
        done = 0 if a.all else view.done_count(ended)
        if done:
            print("  %s — sminos list --subagents%s --done 10" % (V.done_line(done), " " + member if member else ""))
    for n in view.notes:
        print("note: " + n)
    view.keep()


def cmd_list(a):
    """The members of the caller's project, or what the filters pick from
    every project known here (list_scope): one row each (row_cells), under
    the project's heading when one project shows, flat with the project
    column when several do; --here adds `(no project)`. Stopped, retired and
    gone fold into a tail line; --stopped adds stopped, --all shows all, and
    --state keeps the named states. An ended thread no seat here stands for
    (View.ended: a session its human opened, another machine's) is a row
    only with --all or --state retired, in text and in --json alike: they
    have no horizon, so they are not counted among the hidden; --here ends with the live sessions that
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
    ended = a.all or "retired" in a.state
    for p in projects:
        every = project_rows(p) + (list(view_of(p).ended) if ended else [])
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
    """The age of daemon/org.json when it is older than a minute. An old
    one is no fault: the endpoint restates it only at a connection and at a
    new head or certificate set."""
    d = org_directory()
    at = _ts_epoch(d["at"]) if d else None
    if at is not None and time.time() - at > 60:
        print("(the org's directory is %s old: the endpoint restates it only when the org changes or the daemon "
              "reconnects)" % short_age(time.time() - at))


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


def newest_events(projects):
    """{machine name, lower-cased: epoch seconds} of the newest event the
    logs of `projects` hold from each machine's writers (`<machine>/…`)."""
    newest = {}
    for p in projects:
        for ev in view_of(p).events:
            name, ts = str(ev.get("writer") or "").rpartition("/")[0].lower(), str(ev.get("ts") or "")
            if name and ts > newest.get(name, ""):
                newest[name] = ts
    return {name: at for name, at in ((n, _ts_epoch(ts)) for n, ts in newest.items()) if at is not None}


def cmd_machines(_a):
    """`machines`: every machine enrolled in the org (daemon/org.json) —
    this machine, another's newest event, or retired — with its live
    sessions and the projects they are in, read from the logs this machine
    holds. The endpoint carries no presence (it sends every machine
    `online: false`, and `seen` only as of its last restatement), so another
    machine's newest event is the frame's `seen` or the logs', whichever is
    later. On a machine that is not enrolled, this machine alone."""
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
        print("this machine is not enrolled at a desk hub (mawsd endpoint enroll): it knows only itself")
        rows = [row(host_name(), "this machine")]
    elif org is None:
        print("no org directory yet: the endpoint has not sent one (sminos daemon status)")
        rows = [row(e["machine"], "this machine")]
    else:
        rows, heard = [], newest_events(projects)
        for m in sorted(org["machines"], key=lambda m: m["name"].lower()):
            seen = _ts_epoch(m.get("seen"))
            if machine_retired(m["name"]):
                state = "retired"
            elif m["name"].lower() == e["machine"].lower():
                state = "this machine"
            else:
                seen = max((t for t in (seen, heard.get(m["name"].lower())) if t is not None), default=None)
                state = "last event %s ago" % short_age(max(0.0, time.time() - seen)) if seen is not None \
                    else "no event yet"
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
    if not UUID_RE.fullmatch(sid):
        die("join declares the calling session's project: run it from inside a session")
    if a.cwd and a.project:
        die("usage: sminos join <project> | --cwd | (nothing: which project this session is in)")
    if a.project and names_channel(a.project) is not None:   # before anything is read or written, a seat's refusal too
        die("cannot join %s: %s" % (a.project, channel_join_refusal(a.project)), 1)
    try:
        record_config_dir(sid)   # from the session's own environment, as its hook does: its move reads its engine record
    except OSError as e:
        warn("the session's config dir was not recorded (%s)" % e)
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
        elif now_in is not None and (home is None or now_in.id != home.id) and locations_unknown():
            print("%s is in %s, where it was last a member: this machine's endpoint has not sent its stored folder "
                  "statements yet, so its launch directory (%s) is not resolved again until it does; no override"
                  % (me, now_in.name, launch))
        else:
            print("%s is in %s; no override" % (me, home_line))
        return
    if caller_seat():
        die("a seat's project is where it was spawned: %s stays in %s" % (me, now_in.name if now_in else "it"), 1)
    if a.cwd:
        if not held:
            print("%s has no override: it is in %s" % (me, home_line))
            return
        if guessed(home) or _resolve(launch) is UNREAD:   # its project would be told, not read
            die("its launch directory, %s, is in a folder macOS asks the person about before this process reads it: "
                "run sminos join --cwd from inside that folder" % launch, 1)
        with moving(sid):
            # The membership the move leaves, read under the move's lock: another join may have moved it meanwhile.
            forget_caches()
            if not override_of(sid):
                print("%s has no override: it is in %s" % (me, home_line))
                return
            now_in = session_project(sid, launch)
            remove_override(sid)
            move_session(sid, now_in, home, "join")
        print("%s is back in %s" % (me, home_line))
        return
    target = find_project(a.project)
    why = join_refusal(target)
    if why:
        die("cannot join %s: %s" % (target.name, why), 1)
    with moving(sid):
        forget_caches()
        now_in = session_project(sid, launch)
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


CLEARED = "cleared"      # under $SMINOS_HOME: the note of a /clear (smns-cleared.sh), one per engine pid
CLEARED_BELIEVED = 60    # seconds a note is believed: its two hooks were half a second apart, on an idle machine


def cleared_note_path(pid):
    return os.path.join(root(), CLEARED, "%s.json" % pid)


def cleared_from(session, source):
    """The session the process of a `SessionStart` hook left at a `/clear`
    (Interfaces §8), "" for none: read from the note sminos/hooks/
    smns-cleared.sh keeps of the engine's `SessionEnd` with reason `clear`,
    the one the hook's own engine (`CLAUDE_PID`, beside a
    CLAUDE_CODE_SESSION_ID that names `session`) wrote, only for a start
    whose source is `clear`, when the note is younger than
    CLEARED_BELIEVED, was written after that process started, and names
    another session. Read and left: the record hook and the guide hook each
    read it, in either order; the daemon's sweep removes it once its process
    is gone. The witness is for the name alone: never a continuation."""
    pid = os.environ.get("CLAUDE_PID", "")
    if source != "clear" or not pid.isdigit() or os.environ.get("CLAUDE_CODE_SESSION_ID") != session \
            or pid in internal_pids():
        return ""
    path = cleared_note_path(pid)
    try:
        written = os.stat(path).st_mtime
        with open(path, encoding="utf-8") as f:
            note = json.load(f)
    except (OSError, ValueError):
        return ""
    if not isinstance(note, dict) or note.get("reason") != "clear" or not 0 <= time.time() - written < CLEARED_BELIEVED:
        return ""
    rec = next((r for r in peer_records() if str(r.get("pid")) == pid and peer_running(r)), None)
    started = process_started(rec) if rec is not None else None
    left = str(note.get("session_id") or "")
    if started is None or written < started or not UUID_RE.fullmatch(left) or left == session:
        return ""
    return left


def cleared_witness(session, source):
    """(the session a `/clear` left, the alias it gives up, the project it
    is a member of) when the start of `session` has a witness of one
    (cleared_from) and the session it names is a human-opened member of this
    machine — in the project its membership in effect puts it in
    (last_project, through the fold), wherever that is: a `join` of the
    session left is not the new session's, which goes by its own launch —
    whose alias is the engine's name for the process (its record, by
    CLAUDE_PID), and that process's engine record: ("", "", None, None)
    otherwise. What both hooks act on, the record hook's release and the
    guide's first line (§6, row 16)."""
    left = cleared_from(session, source)
    none = "", "", None, None
    if not left:
        return none
    t = threads_module().thread_of(left, ended=False)
    if t is None or t["opened"] != "human" or t["current"] != left or threads_module().record_ended(t):
        return none
    where = last_project(left)
    own = _own_events(where, left) if where is not None else []
    joined = next((e for e in reversed(own) if e["kind"] == "joined"), {})
    if latest_membership(own) != "joined" or not is_self(str(joined.get("machine") or ""), left):
        return none
    pid = os.environ.get("CLAUDE_PID", "")
    rec = next((r for r in peer_records() if str(r.get("pid")) == pid and peer_running(r)), None)
    alias = own_alias(own, left)[0]
    if rec is None or not alias or str(rec.get("name") or "") != alias:
        return none
    return left, alias, where, rec


def release_alias(project, left, alias, clearing=None):
    """The release at a `/clear` (§6, row 16): on the thread of the session
    left, `released` (the alias, and when) and the `renamed` to its short id
    it owes, in one journaled operation, the event in `project`, the one the
    session left is a member of (cleared_witness); the next joins take the
    name by today's rule, and nothing of the session left (its project, its
    reach) moves to the new one. A release a process started after it has
    outlived (the session reopened, not swept yet) is replaced: outlived by
    `clearing`, the engine record of the process the `/clear` was witnessed
    in (cleared_witness), which names the new session by now; without one,
    the process that runs the session left. The events appended."""
    threads = threads_module()
    t = threads.thread_of(left, ended=False)
    if t is None:
        return []
    return thread_transition(
        project, t["thread"], "release",
        [{"kind": "renamed", "session": left, "alias": left[:8], "name_source": "derived"}],
        fields={"released": {"alias": alias, "at": now()}},
        guard=lambda r: r["opened"] == "human" and r["current"] == left and not threads.record_ended(r)
        and (not r.get("released") or threads.release_outlived(
            r["released"], clearing if clearing is not None else running_now(left))),
        lock_until=_RECORD_DEADLINE)


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
    # The alias it goes by, as its own say would sign it (default_from); after a `/clear`, the one the session
    # left gives up whichever hook runs first (cleared_witness).
    left = cleared_witness(session, source)[0] if seat is None else ""
    alias = seat["alias"] if seat else \
        held_alias(*own_alias(_own_events(project, session), session), peer, session,
                   shadowing(project, session, released=(left,) if left else ()))[0]
    who = "%s [%s]" % (alias, session[:8]) if alias and alias != session[:8] else "[%s]" % session[:8]
    # The plugin's bin/ puts the CLI on the session's PATH, so the verb lines
    # name it `sminos`, as the session runs it.
    cli = "sminos"
    if home is not None and home.id != project.id and not override_of(session) and locations_unknown():
        where = ("where you were last a member: this machine's endpoint has not sent its stored folder statements "
                 "yet, so your launch directory, %s, is not resolved again until it does" % launch)
    elif home is not None and home.id != project.id:
        where = ("by your own `sminos join` (your launch directory, %s, is in %s; `%s join --cwd` returns you there)"
                 % (launch, home.name, cli))
    elif project_kind(project) == "machine":
        where = "this machine's own project, since no .smns or repository remote claims your launch directory, %s" \
            % launch
    elif decision(launch).by == "remote":
        where = "the project of your repository's remote, %s (your launch directory, %s)" % (
            derivation(launch).key, launch)
    else:
        where = "the project of your launch directory, %s" % launch
    join = [] if seat else ["  %s join <project>  when your directory files you in the wrong project (a scratch copy)"
                            " or your standing work belongs to another; once, not per repository you visit" % cli]
    # The fork line (T1's M2 and M6, evaluated: a closing "with the task you were forked for" sent forks
    # looking for a task their context does not name; the peer clause is main's 1.49.1).
    fork = (" You are a fork of another session: a copy, with a session id and a name of your own. Every sminos"
            " line above this one was written for the session you were copied from, and messages addressed to it"
            " are not for you; you are its peer.") if source == "fork" else ""
    return "\n".join([
        "sminos: you are %s in project %s on machine %s: %s. A `cd` does not change your project.%s"
        % (who, project.name, enrollment()["machine"], where, fork),
        "Other Claude sessions work in this org, on every enrolled machine and in every repository. "
        "To find one or tell it something, run sminos in Bash:",
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
        "  %s say - <<'EOF'   the text on stdin, as written: for text with backticks, quotes, $ or several lines"
        " (the shell runs a backtick inside double quotes)" % cli,
    ] + join + [
        "Peers are symmetric: each decides within its own work, and a peer's message informs, asks or proposes."
        " Who answers to whom is your human partner's to set.",
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
            to = [r for r in to if isinstance(r, dict) and UUID_RE.fullmatch(str(r.get("session") or ""))]
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
    if not UUID_RE.fullmatch(session):
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
    if os.environ.get("SMNS_INTERNAL") or not UUID_RE.fullmatch(session or ""):
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
    rows = [(p, m) for p in scope for m in view_of(p).members + view_of(p).rows if m.session]
    for p, m in rows:
        if m.short == short:
            best.setdefault(m.session, (p, m, ""))
    # Another id that names a member (a session it continues, its thread's
    # other sessions, its thread id: former_ids) answers as the member it
    # went on as, unless a session of that short is a member itself.
    named = {m.session for _, m, _ in best.values()}
    for p, m in rows:
        if m.session not in best and any(x[:8] == short and x not in named for x in former_ids(m)):
            best.setdefault(m.session, (p, m, "continued"))
    went_on = {x for _, m, how in best.values() if how == "continued" for x in former_ids(m)}
    for p in scope:
        view = view_of(p)
        for sid, r in view.info.items():
            latest = r["latest"] or {}
            if sid[:8] != short or sid in best or sid in went_on or latest.get("kind") != "retired" \
                    or not r["joined"] or (latest.get("reason") == "moved" and latest.get("project") in known):
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
            # A stopped seat by this machine's hold of it, as a view reads it (hold_for): one a wake would not start
            # is said held and why (T2's §5), never resumed.
            why = "" if m.state in FILLED else hold_for(m.session)
            out.append('  reach: sminos say "@%s ..."%s' % (m.short, "" if m.state in FILLED else
                                                             "  (the stopped seat is not woken: %s; the message is "
                                                             "held until a process of it runs)"
                                                             % hold_words(why, m.session) if why else
                                                             "  (the stopped seat is resumed)"))
        elif m.state != "gone" or not m.local:
            where = "here" if m.local else "on %s" % m.machine
            out.append("  resume it %s: cd %s && claude --resume %s" % (where, shlex.quote(m.cwd or "."), m.session))
            # What its machine published (on a `gone` state too, state_wake); a sender here meets this machine's
            # hold, which `read-only` is not: it refuses only what comes from another machine.
            wakes = wake_of(m) if m.thread and m.state in HELD_STATES else None
            why = why_of(m) if wakes == "held" else ""
            if m.local and why == "read-only":
                wakes, why = wake_here(m.session)
            if wakes == "woken" and m.state == "stopped":
                # A stopped thread its machine wakes (T2): an addressed message starts it again.
                out.append('  or message it, which wakes it: sminos say "@%s ..."' % m.short)
            elif why == "read-only":
                # Its machine refuses what this one sends it (T2's §5): nothing to leave it from here.
                out.append("  no message from here reaches it: %s admits nothing from another machine, and refuses "
                           "it there" % m.machine)
            elif wakes == "held":
                # One its machine holds: an addressed message waits for a process of it (T1's M3, T2's §5).
                out.append('  or leave it a message, held until a process of it runs%s: sminos say "@%s ..."' % (
                    " (%s)" % (hold_words(why, m.session if m.local else "") if why in HOLD_WORDS else why)
                    if why else "", m.short))
            else:
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


def cmd_access(a):
    sibling_module("sminos_visibility").cmd_access(a)


def cmd_share(a):
    sibling_module("sminos_visibility").cmd_share(a)


def tick(project):
    """One daemon tick of one project (§8): integrate, reconcile, publish,
    deliver, push. {"integrated", "reconciled", "published", "delivered",
    "pushed"}, plus "to" (the aliases delivered to) and "error"."""
    return daemon_module().tick(project)


def cmd_daemon(a):
    if not a.op:
        die("usage: sminos daemon run [--interval N] | tick | install | status | owed | policy [--read-only on|off] "
            "[--ceiling MODE|settings] | profile [--seconds S] [--of uplink|run]")
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
    dv.add_argument("--compacted", action="store_true")
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
    dc = dsub.add_parser("census", add_help=False)   # the ending pass's child (T1's M5); no person runs it
    dc.add_argument("threads", nargs="*")
    dc.add_argument("--reap", action="store_true")
    dpr = dsub.add_parser("profile", add_help=False)
    dpr.add_argument("--seconds", type=float, default=20.0)
    dpr.add_argument("--of", choices=("uplink", "run"), default="uplink")
    dp = dsub.add_parser("policy", add_help=False)
    dp.add_argument("--read-only", dest="read_only", choices=("on", "off"), default=None)
    dp.add_argument("--ceiling", default=None)
    dm.set_defaults(fn=cmd_daemon)

    # `hub` takes its words as `wake` does (no word is an option to argparse,
    # so its parse never fails): sminos_hub parses them and never prints one.
    # An old enrollment code typed after `hub enroll` must not reach
    # argparse's error, which echoes the word it could not place.
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
    rt.add_argument("--owner-unknown", dest="owner_unknown", action="store_true")
    rt.set_defaults(fn=cmd_retire)

    ac = sub.add_parser("access", add_help=False)
    ac.add_argument("member")
    ac.add_argument("level", choices=("private", "listed", "org-view", "org-converse"))
    ac.set_defaults(fn=cmd_access)

    sh = sub.add_parser("share", add_help=False)
    sh.add_argument("member")
    sh.add_argument("person")
    sh.add_argument("grade", choices=("list", "view", "converse", "approve", "none"))
    sh.set_defaults(fn=cmd_share)

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


# The prose a session composes, by verb: given as `-`, it is read from
# standard input, so a heredoc with a quoted delimiter (`<<'EOF'`) carries any
# text verbatim, where a double-quoted argument has the shell run its backticks
# and expand its `$` before sminos sees it.
STDIN_BODIES = {"say": "text", "send": "msg", "spawn": "task", "steer": "text", "resume": "msg", "fill": "task",
                "compact": "instructions"}


def stdin_body(a):
    """Reads the verb's prose from standard input when it was given as `-`:
    the text whole, less the line ending a heredoc or an echo adds. Refused
    from a terminal (nothing is piped) and when stdin holds no text."""
    field = STDIN_BODIES.get(a.cmd)
    if field is None or getattr(a, field, None) != "-":
        return
    if sys.stdin is None or sys.stdin.isatty():
        die("%s -: the text is read from standard input; pipe it, or give it as a heredoc:\n"
            "  sminos %s ... - <<'EOF'\n  <text>\n  EOF" % (a.cmd, a.cmd))
    text = sys.stdin.buffer.read().decode("utf-8", "replace")
    text = text[:-2] if text.endswith("\r\n") else text[:-1] if text.endswith("\n") else text
    if not text.strip():
        die("%s -: no text on standard input" % a.cmd)
    setattr(a, field, text)


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
    if a.cmd == "daemon" and a.op in ("owed", "profile"):
        # B2's gate on a machine about to cut over (O14), and a profile of the
        # running daemon, run beside it: neither migrates or takes a lock.
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
    stdin_body(a)
    migrate()
    HINTS["on"] = a.cmd in READING_VERBS
    try:
        a.fn(a)
    except LogWriteFailed as e:
        die("%s completed, but %s" % (a.cmd, e), 1)
    except WakeBusy as e:
        die(e.message, 1)


if __name__ == "__main__":
    main()
