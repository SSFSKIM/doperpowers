#!/usr/bin/env python3
"""sminos — one fleet registry for Claude Code sessions.

The unit is the PROJECT (a committed .smns, else the owning repository) and
its family: every session working under it is a MEMBER, with no join step and
no host — the human is the host. A SEAT is a named position, with a role and a
brief, that a session sminos spawned fills; it outlives the process that fills
it and can be filled again (`fill --resume` continues the same session id;
`fill` spawns a fresh one). Every background session spawned through sminos is
a seat, board pipeline workers included. A session the human opened is a
member too, seat-less, from the first call that reads its project.

    sminos spawn    <alias> <task> [--role R] [--brief B] [--cwd C] [--worktree W]
                   [--model M] [--settings S] [--effort E] [--wait]
    sminos seat add <group> <alias> [--role R] [--brief B] [--session S]
    sminos fill     <seat> <task> [--resume] [--model M] [--settings S] [--effort E] [--wait]
    sminos resume   <seat> <msg> [--wait]                 # process-level continuation (stops a live turn first)
                   A resumed background session keeps its SAVED options (name, permission
                   mode, model, settings, effort): --model/--settings/--effort are accepted
                   on resume for argv compatibility but ignored — use fill without --resume
                   to change them.
    sminos send     <member|session name|codex thread> <msg> [--wait] [--from F]
                   # a live member: inbox socket; a stopped seat: resumed. A live session by
                   # name, or a codex thread (its id, or codex:<id|exact name>, through
                   # codex's queue); --wait needs a seat.
    sminos say      [--in <project>] <text>                # untagged: recorded; @alias / @"a b" / @alias#short /
                   @short / @project/alias: delivered; @all: every live member
    sminos chat     [<project>] [-n N] [--since TS] [--kind K] [--json]   # no flags: unread, advancing the cursor
    sminos chat     [<project>] --host [-n N] [--since TS] [--json]       # what the members sent their human
    sminos charge   [<member>] "<one line>"               # what the member is in charge of (a session: its own)
    sminos derive   <member> | --all                      # ask a session its line, by a headless internal fork
    sminos record                                         # the Stop / SessionStart hook's verb (payload on stdin)
    sminos watch    <member> [--json]                     # a session's live stream through its bridge: the
                   conversation as it streams, subagents labelled (--json: the endpoint's lines)
    sminos bridge   --session <id>                        # the bridge mod's child: serves the session's
                   endpoint at $SMINOS_HOME/bridge/<id>.sock (not for a person to run)
    sminos project  init [--name N] [--remote URL] [--hub] | show [DIR] | attach [DIR]
                   # --hub: the project syncs through this machine's desk hub, never git
    sminos daemon   run [--interval 5] | tick | install | status   # mirror sync and delivery, per machine
    sminos hub      enroll [--name N] [--replace] | show   # this machine at the desk hub: its name
                   there is its name everywhere (the writer host of what it writes). The code is
                   pasted at a hidden prompt, or piped on stdin — never an argument: it carries the org key
    sminos reply    <seat>                                # latest reply text
    sminos sync     [<seat>] [--all]                      # reconcile status from the harness
    sminos status   <member> <one line>                   # the member's own "now" line
    sminos retire   <member> [--purge]                    # stop; keep (or purge) a seat's record
    sminos remove   <seat>                                # stop and delete the record
    sminos list     [project] [--state W] [--json] [--all]  # the working directory's project; every project
                   from none or with --all. W: busy idle waiting stopped gone vacant retired;
                   retired and gone fold into a "+N hidden" tail until --all or --state names them
    sminos chart    [project] [--all] [--width N]        # the members as boxes, grouped by project
    sminos tui      [project] [--all] [--no-tmux]        # the chart, interactive, inside tmux: arrows move, enter attaches
    sminos attach   <seat>                                # claude attach <short>
    sminos migrate  [--quiet]                             # (also runs implicitly)
    sminos meta     get <seat> <field> | set <seat> <field> <value> [<field> <value>...]

A member's name is its alias: a seat's alias (a seat sminos spawns runs under
it as its harness name), or a seat-less session's harness name. Aliases are
display names and can collide; `alias#short` (the session's first eight hex
digits) tells two apart. A bare name resolves in the working directory's
project (a seat's own, for a seat), `project/alias` in another, and from a
directory that is no project across every project known here; a seat also
answers to `group/alias`. Scripts may pass a full seat id or session id.

Messaging is one verb, `send`: to a live seat it writes a frame to the
session's inbox socket — the socket the harness's native cross-session
SendMessage tool also rides — which the harness delivers as a peer message
(an idle session starts a new turn, a busy one reads it at its next tool
round); a stopped seat is resumed with the frame as its message. `resume` is
the process-level continuation the board pipeline relays through: a fresh
`claude --bg --resume` carrying the invoking environment.

State lives under $SMINOS_HOME (default ~/.claude/sminos; $DAEMON_HOME is the
older name of the same root and is honored). Records are <seat-id>.json at the
root — seat id = the first session's uuid — and the board pipeline reads and
writes them directly under the shared flock file .metalock. A project (a
committed .smns, else the owning git repository) keeps its append-only event
log, one file per writer, at projects/<id>/log/, with each reader's cursor and
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
import glob
import hashlib
import heapq
import importlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid as uuidlib
from contextlib import contextmanager
from typing import NamedTuple, NoReturn, Optional

# Fleet state is private to the agent fleet: everything this CLI creates is
# 700/600. All agents run as the same OS user, so nothing needs group/other.
os.umask(0o077)

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import sminos_marks  # noqa: E402 — the mark grammar of hooks/mods/to-human.tsx, ported

LAUNCHER = os.path.join(SCRIPT_DIR, "sminos")
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
# HIDDEN: what list, chart, and tui fold by default — a seat only a `fill`
# can act on. The word decides; the hide rule asks nothing more.
HIDDEN = ("retired", "gone")
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


def seats(group=None):
    out = []
    for p in record_files():
        try:
            s = load_seat(p)
        except Exception:
            continue  # an unparsable or half-written record is not a seat
        if group is None or s["group"] == group:
            out.append(s)
    return out


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
# A project is the unit of shared work state: a committed `.smns` names it; a
# git repository without one is a local project named after its owning
# repository; any other directory is no project. Everything that crosses
# sessions is one event in the project's append-only log — one file per
# writer under $SMINOS_HOME/projects/<id>/log/, so a file has one writer and
# replication is a copy. Delivery is the deliverer's own record (delivered/),
# never a rewrite of the log. Design: docs/doperpowers/specs/
# 2026-10-13-smns-project-log-design.md.


class Project(NamedTuple):
    id: str          # uuid from .smns, or "local-<name>"
    name: str
    remote: str      # "" for a local project
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
LIFECYCLE = MEMBERSHIP + ("renamed", "state", "in-charge", "status")
# The harness session kinds that are members on sight; any other is not.
JOINABLE_KINDS = ("interactive", "bg")
# A headless or SDK run (`claude -p`, the agent SDKs) registers as
# `interactive` too (harness 2.1.299: `kind: "interactive", entrypoint:
# "sdk-cli"`); its entrypoint is what tells it apart, and it is no member.
HEADLESS_ENTRYPOINT = "sdk"
_PROJECTS = {}
_HOMES = set()
_VIEWS = {}  # project id → View, per invocation; a lifecycle append drops it


def projects_root():
    return os.path.join(root(), "projects")


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name)[:64]
    return name if valid_name(name) else ""


def _owning_repo_fs(d):
    """owning_repo read off the filesystem, no process: the nearest `.git`
    upward — a directory names its checkout; a file (a linked worktree)
    points at its gitdir, whose `commondir` leads to the main checkout's.
    None when the layout is not one of those, for the caller to ask git."""
    while True:
        dot = os.path.join(d, ".git")
        if os.path.isdir(dot):
            return d
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
            return os.path.dirname(os.path.abspath(common))
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def owning_repo(cwd):
    """The owning repository of a directory — for a linked worktree, the main
    checkout, through the common git dir — asked of its nearest existing
    ancestor, so a removed worktree still resolves. "" outside git. Read off
    the filesystem when it can be: every reading verb resolves the cwd of
    every seat and live session, and a process per directory adds up."""
    d = os.path.abspath(cwd)
    while not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent
    repo = _owning_repo_fs(d)
    if repo is not None:
        return repo
    try:
        p = subprocess.run(["git", "-C", d, "rev-parse", "--git-common-dir"],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    common = p.stdout.strip() if p.returncode == 0 else ""
    if not common:
        return ""
    if not os.path.isabs(common):
        common = os.path.join(d, common)
    return os.path.dirname(os.path.abspath(common))


def make_project(pid, name, remote, root_dir, hub=None):
    return Project(pid, name, remote, root_dir, os.path.join(projects_root(), pid), hub)


def read_smns(path):
    """(id, name, remote, hub) from a .smns, or None — with a warning — when it
    is unreadable or names no valid id: a broken file in one repository must
    not stop every verb that resolves a seat living there. A `hub` key that is
    not {url, org} — null included — still makes a hub project, which git
    never syncs and no hub feeds (hub_wellformed), with a warning: two live
    transports are worse than none."""
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
            warn("%s: its hub is not {url, org}; the project syncs through neither git nor a hub until it is" % path)
            hub = {"url": "", "org": ""}  # a hub project nothing feeds
    return pid, str(d.get("name") or pid), str(d.get("remote") or ""), hub


def hub_wellformed(hub):
    """Whether a .smns `hub` is {url, org}, both non-empty strings: the only
    hub a project syncs through. Any other value still bars git."""
    return isinstance(hub, dict) and all(isinstance(hub.get(k), str) and hub[k] for k in ("url", "org"))


def resolve_project(cwd):
    """The project of a directory: the first .smns walking up; else the local
    project of the owning git repository; else None (no project)."""
    cwd = os.path.abspath(os.path.expanduser(cwd or "."))
    if cwd in _PROJECTS:
        return _PROJECTS[cwd]
    project, d = None, cwd
    while True:
        smns = read_smns(os.path.join(d, SMNS)) if os.path.isfile(os.path.join(d, SMNS)) else None
        if smns:
            project = make_project(smns[0], smns[1], smns[2], d, smns[3])
            break
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    if project is None:
        repo = owning_repo(cwd)
        if repo:
            name = safe_name(os.path.basename(repo)) or "repo"
            project = make_project("local-" + name, name, "", repo)
    _PROJECTS[cwd] = project
    return project


def seat_project(seat):
    """A seat's project, from its recorded cwd. A seat spawned where there is
    no project belongs to the local project named after that directory: the
    seat record is the explicit registration automatic discovery never makes.
    A record with no cwd at all (written by hand, or before cwd was recorded)
    belongs to the local project named after its group, so it stays in view."""
    if not seat:
        return None
    cwd = str(seat.get("cwd") or "")
    if not cwd:
        name = safe_name(str(seat.get("group") or "")) or "fleet"
        return make_project("local-" + name, name, "", "")
    project = resolve_project(cwd)
    if project is None:
        name = safe_name(os.path.basename(os.path.normpath(cwd))) or "fleet"
        project = make_project("local-" + name, name, "", os.path.abspath(cwd))
    return project


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


def project_path(project, *parts):
    """A path under the project's home; the first use creates the home and
    records project.json (the .smns as last resolved, plus its root)."""
    if project.id not in _HOMES:
        os.makedirs(os.path.join(project.home, "log"), mode=0o700, exist_ok=True)
        info = {"project": project.id, "name": project.name, "remote": project.remote, "root": project.root}
        if project.hub is not None:
            info["hub"] = project.hub
        path = os.path.join(project.home, "project.json")
        try:
            with open(path) as f:
                same = json.load(f) == info
        except (OSError, ValueError):
            same = False
        if not same:
            write_json(path, info)
        _HOMES.add(project.id)
    path = os.path.join(project.home, *parts)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    return path


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


def find_project(q, required=True):
    """A project known locally, by id or by name; with required=False, None
    when none is (an ambiguous name still exits)."""
    known = known_projects()
    for match in (lambda p: p.id == q, lambda p: p.name == q):
        hits = [p for p in known if match(p)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            die("ambiguous project '%s': %s" % (q, ", ".join(sorted("%s (%s)" % (p.name, p.id) for p in hits))),
                EXIT_UNKNOWN)
    if not required:
        return None
    die("no project '%s' is known on this machine" % q, EXIT_UNKNOWN)


def caller_project(caller=None):
    """The project a call speaks in by default: the caller seat's, else the
    working directory's (None: no project)."""
    return seat_project(caller) if caller else resolve_project(os.getcwd())


# Writers: one appender each. `<machine>/<session-uuid>` for a session,
# `<machine>/human` for the operator, `legacy/<host-seat-id>` for an imported
# family chat. The file name replaces `/` with `.`.


def writer_id(session_uuid=None):
    return "%s/%s" % (host_name(), session_uuid or "human")


def writer_session(writer):
    last = writer.rsplit("/", 1)[-1]
    return last if UUID_RE.match(last) else ""


def writer_short(writer):
    session = writer_session(writer)
    return session[:8] if session else writer


def event_ref(e):
    return "%s:%d" % (writer_short(e["writer"]), e["seq"])


def writer_path(project, writer):
    return project_path(project, "log", writer.replace("/", ".") + ".jsonl")


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


def _append(project, writer, events, skip_src=False, guard=None):
    """Append events to the writer's file under `.sync.lock` shared (git never
    rewrites log/ while an appender writes) and the file's own lock (seq is the
    last line's plus one). With `guard`, the file's events are read under the
    lock and nothing is appended unless guard(events) holds — a check and its
    append no other appender can come between. Returns the events as written."""
    if any(e["kind"] in LIFECYCLE for e in events):
        _VIEWS.pop(project.id, None)
    path = writer_path(project, writer)
    log = os.path.dirname(path)
    with flocked(os.path.join(log, ".sync.lock"), exclusive=False), flocked(path + ".lock"):
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
            seq = _last_seq(f)
            out = []
            for fields in events:
                seq += 1
                rest = {k: v for k, v in fields.items() if k != "kind"}
                out.append({"ts": now(ms=True), "writer": writer, "seq": seq, "kind": fields["kind"], **rest})
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


def log_append_batch(project, writer, events, skip_src=True):
    """Several events of one writer under one taking of the locks; with
    skip_src, an event whose (kind, src) the file already holds is dropped
    inside them, so a retried export appends each source once. `src` is a
    correlation id: a `question` and its `answered` share one."""
    return _append(project, writer, events, skip_src)


def addressed_to(e, session):
    to = e.get("to")
    return isinstance(to, list) and any(isinstance(r, dict) and r.get("session") == session for r in to)


def log_read(project, since=None, kinds=(), to_session=None):
    """The project's events: each writer's stream in seq order (authoritative
    within a writer), merged by taking the next line from whichever stream's
    head has the earlier (ts, writer). Only the top-level *.jsonl are read."""
    streams = {}
    for path in sorted(glob.glob(os.path.join(project.home, "log", "*.jsonl"))):
        try:
            f = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for line in f:
                e = parse_event(line)
                if (e is None or (since and e["seq"] <= int(since.get(e["writer"], 0)))
                        or (kinds and e["kind"] not in kinds) or (to_session and not addressed_to(e, to_session))):
                    continue
                streams.setdefault(e["writer"], []).append(e)
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
# with its attempt count. A deliverer never settles past an unsettled event of
# the same writer, so a later success cannot bury an earlier failure.


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
            out[str(w)] = {"settled": int(v.get("settled") or 0),
                           "pending": pending if type(pending) is int else None,
                           "attempts": int(v.get("attempts") or 0)}
    return out


def _delivery(record, writer):
    return record.get(writer) or {"settled": 0, "pending": None, "attempts": 0}


def _next_check(record, writer, seq):
    w = _delivery(record, writer)
    if seq <= w["settled"] or (w["pending"] is not None and seq != w["pending"]):
        raise ValueError("delivery of %s:%d out of order (settled %d, pending %s)" % (
            writer, seq, w["settled"], w["pending"]))
    return w


def delivered_settle(project, session_uuid, writer, seq):
    """Settle the writer's next owed event — every event between the settled
    prefix and seq is not owed to this session, so the prefix moves to seq.
    The caller holds delivered/<session>.lock."""
    record = delivered_load(project, session_uuid)
    _next_check(record, writer, seq)
    record[writer] = {"settled": seq, "pending": None, "attempts": 0}
    write_json(project_path(project, "delivered", reader_key(session_uuid) + ".json"), record)


def delivered_fail(project, session_uuid, writer, seq):
    """Note a failed attempt at the writer's next owed event; returns the count."""
    record = delivered_load(project, session_uuid)
    w = _next_check(record, writer, seq)
    attempts = w["attempts"] + 1 if w["pending"] == seq else 1
    record[writer] = {"settled": w["settled"], "pending": seq, "attempts": attempts}
    write_json(project_path(project, "delivered", reader_key(session_uuid) + ".json"), record)
    return attempts


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
    name_source: str      # seat | user | derived
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


def member_json(m, project=None):
    """A member as list --json carries it: no task body, no credential."""
    d = {"alias": m.alias, "session": m.session, "short": m.short, "name_source": m.name_source,
         "machine": m.machine, "local": m.local, "state": m.state, "state_age": m.state_age,
         "charge": m.charge, "charge_source": m.charge_source, "by": m.by, "status": m.status,
         "worktree": m.worktree, "seat": public_seat(m.seat) if m.seat else None}
    if project is not None:
        d = {"project": project.name, "project_id": project.id, **d}
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


def caller_alias():
    """Who a lifecycle event names as its actor (`by`): the calling session's
    seat alias (a provisional seat's too), else its harness name; "" for the
    operator."""
    if not os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return ""
    caller = caller_seat()
    return caller["alias"] if caller else default_from("")


def joined_fields(alias, name_source, cwd, worktree="", role="", seat="", by=""):
    return {"alias": alias, "name_source": name_source, "machine": host_name(), "cwd": cwd,
            "worktree": worktree, "role": role, "seat": seat, "by": by}


def latest_membership(events):
    """The kind of the last joined/retired among a session's own events, or None."""
    return next((e["kind"] for e in reversed(events) if e["kind"] in MEMBERSHIP), None)


class LogWriteFailed(Exception):
    """A required lifecycle event could not be appended. The verb's local
    operation already happened; main() exits 1 saying both."""


def lifecycle(project, session, kind, guard=None, required=True, **fields):
    """Append one lifecycle event for a session on this machine to the
    session's own file: a session's lifecycle has one writer, so its order is
    its seq. A failure raises LogWriteFailed — the event is part of the verb —
    except for reconciliation's own appends (`required=False`), which a
    reading verb only warns about and the next one retries. A guard reads
    the session's events under this machine's former names first: a rename
    moves where its lifecycle goes on, not what it is."""
    if project is None or not session:
        return []
    before = _former_events(project, session) if guard is not None else []
    if before:
        guard = (lambda inner: lambda evs: inner(before + evs))(guard)
    try:
        return _append(project, writer_id(session), [{"kind": kind, "session": session, **fields}], guard=guard)
    except OSError as e:
        msg = "recording %s of %s in %s's log failed: %s" % (kind, session[:8], project.name, e)
        if required:
            raise LogWriteFailed(msg)
        warn(msg)
        return []


def join_seat(seat, by=""):
    """joined for the session a seat holds, unless its latest membership
    already is: how fill --resume, resume, and send revive a retired seat."""
    if not seat or not seat["current"]:
        return []
    return lifecycle(seat_project(seat), seat["current"], "joined",
                     guard=lambda evs: latest_membership(evs) != "joined",
                     **joined_fields(seat["alias"], "seat", seat["cwd"], seat["worktree"], seat["role"],
                                     seat["seat_id"], by))


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
    "peer"}} for every seat whose cwd resolves to it and every harness session
    whose process runs in it, internal forks aside."""
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
        p = resolve_project(cwd)
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
    and re-joins if it runs again. A seat's lifecycle stays with retire, fill,
    and resume."""
    latest, joined = {}, {}
    for e in events:
        if e["kind"] in MEMBERSHIP and e.get("session") and writer_session(e["writer"]) == e["session"]:
            latest[e["session"]] = e["kind"]
            if e["kind"] == "joined":
                joined[e["session"]] = e
    out = []
    for sid, e in joined.items():
        if (latest[sid] != "joined" or sid in by_session or sid in local
                or not is_self(str(e.get("machine") or ""), sid) or session_running(sid)):
            continue

        def ended(evs, sid=sid):
            return (latest_membership(evs) == "joined" and not session_running(sid)
                    and not any(s["current"] == sid for s in seats()))

        out += lifecycle(project, sid, "retired", guard=ended, required=False, by="", reason="ended")
    for sid, ev in local.items():
        seat, peer = by_session.get(sid), ev.get("peer")
        if (latest.get(sid) == "joined") if peer else (sid in latest):
            continue
        out += join_on_sight(project, sid, seat, peer, bool(peer))
    return out


def joinable(seat, peer):
    """Whether a session of this machine is a member on sight: a seat whose
    record is not retired, or a seat-less session the harness records as
    `interactive` or `bg` whose entrypoint is no headless or SDK run (`sdk-*`:
    another tool's `claude -p` is no member, whatever its kind)."""
    if seat:
        return seat["status"] != "retired"
    peer = peer or {}
    return (str(peer.get("kind") or "") in JOINABLE_KINDS
            and not str(peer.get("entrypoint") or "").startswith(HEADLESS_ENTRYPOINT))


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
    resume opens a new process, so a resumed session re-joins, §2). A
    retirement for any other reason (`ended`: its process was not seen) does
    not hold against a running process."""
    last = next((e for e in reversed(events) if e["kind"] in MEMBERSHIP), None)
    if not last or last["kind"] != "retired" or last.get("reason") != "retire":
        return False
    peer = peer or {}
    if last.get("pid") not in (None, "") and str(last["pid"]) != str(peer.get("pid")):
        return False
    started, retired = process_started(peer), _ts_epoch(last.get("ts"))
    return started is None or retired is None or started <= retired


def join_on_sight(project, sid, seat, peer, running):
    """joined for a session seen on this machine, when it is joinable and
    the log does not already hold it as a member: a running session whose
    latest membership is absent or retired (a live process is evidence of
    activation), a seat that is not running only when it has no membership
    event at all; a seat-less session retired by `retire` only once a new
    process runs it (retirement_holds). Checked again under the session
    file's lock, the seat record re-read there, so a concurrent retire cannot
    be undone. Shared by reconciliation and the hook (§2, §4)."""
    if not joinable(seat, peer):
        return []

    def guard(evs):
        last = latest_membership(evs)
        if (last == "joined") if running else (last is not None):
            return False
        if not seat and retirement_holds(evs, peer):
            return False
        fresh = reload_seat(seat["seat_id"]) if seat else None
        return not (seat and (fresh is None or fresh["status"] == "retired"))

    if seat:
        fields = joined_fields(seat["alias"], "seat", seat["cwd"], seat["worktree"], seat["role"], seat["seat_id"])
    else:
        fields = joined_fields(str(peer.get("name") or sid[:8]), str(peer.get("nameSource") or "derived"),
                               str(peer.get("cwd") or ""))
    return lifecycle(project, sid, "joined", guard=guard, required=False, **fields)


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
    latest rename and published state (its own file), its in-charge events
    (for charge_of), and its status: each writer's latest by seq, the later
    ts between writers (§3)."""
    info = {}
    for e in events:
        sid, kind = e.get("session"), e["kind"]
        if kind not in LIFECYCLE or not isinstance(sid, str) or not sid:
            continue
        own = writer_session(e["writer"]) == sid
        r = info.setdefault(sid, {"latest": None, "joined": None, "by": "", "renamed": None, "state": None,
                                  "in_charge": [], "status": []})
        if kind in MEMBERSHIP or kind in ("renamed", "state"):
            if not own:
                continue
            if kind in MEMBERSHIP:
                r["latest"] = e
                if kind == "joined":
                    r["joined"] = e
                    if not r["by"] and e.get("by"):
                        r["by"] = str(e["by"])
            else:
                r[kind] = e
        elif kind == "in-charge":
            r["in_charge"].append(e)
        else:
            r["status"].append(e)
    for r in info.values():
        r["status"] = latest_across_writers(r["status"])
    return info


def charge_of(member, events, title=True):
    """(line, source): what a member is in charge of, the first present of
    (§5) the latest `set` in-charge line, the name the human gave it, the
    latest `derived` line, and — on this machine only — its transcript's
    latest title; ("", "") when none is. A set or derived line written
    empty is no line. `events` is the log, or any part of it holding the
    member's in-charge events, each writer's in seq order. With title=False
    the transcript is not read (the daemon's tick has no use for the line)."""
    mine = [e for e in events if e["kind"] == "in-charge" and e.get("session") == member.session]
    for source in ("set", "name", "derived", "title"):
        if source == "name":
            line = member.alias if member.name_source == "user" else ""
        elif source == "title":
            line = transcript_title(member.session) if title and member.local and member.session else ""
        else:
            e = latest_across_writers([x for x in mine if x.get("source") == source])
            line = str(e.get("text") or "").strip() if e else ""
        if line:
            return line, source
    return "", ""


def charge_shown(m):
    """The in-charge line a row draws: not a name the alias column already shows."""
    return "" if m.charge_source == "name" else m.charge


def ts_age(ts):
    try:
        then = calendar.timegm(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    return max(0.0, time.time() - then)


def _member(sid, r, seat, peer, local, title=True):
    """One row of the projection: what the log says of the session, and, on
    this machine, its seat record and its process."""
    j = (r or {}).get("joined") or {}
    alias, name_source = str(j.get("alias") or ""), str(j.get("name_source") or "")
    if r and r["renamed"]:
        alias, name_source = str(r["renamed"].get("alias") or alias), str(r["renamed"].get("name_source") or name_source)
    if seat:
        alias, name_source = seat["alias"], "seat"
    elif peer and peer.get("name"):
        alias, name_source = str(peer["name"]), str(peer.get("nameSource") or name_source or "derived")
    machine = str(j.get("machine") or "")
    local = local or bool(seat) or not machine or is_self(machine, sid)
    age = None
    if not local:
        published = (r or {}).get("state") or {}
        state_word, age = str(published.get("state") or ""), (ts_age(published["ts"]) if published else None)
    elif seat:
        # A seat's word is the one its route reads: the inbox must answer.
        state_word = state(seat)
    elif peer:
        state_word = peer_state(peer)
    else:
        state_word = "stopped" if transcript_path(sid) else "gone"
    status = (r or {}).get("status")
    m = Member(
        session=sid, short=sid[:8], alias=alias or sid[:8], name_source=name_source,
        machine=host_name() if local else machine, local=local, state=state_word, state_age=age,
        charge="", charge_source="",
        status=str(status.get("text") or "") if status else (seat["now"] if seat else ""),
        by=(r or {}).get("by") or "", worktree=seat["worktree"] if seat else str(j.get("worktree") or ""),
        seat=seat)
    charge, source = charge_of(m, (r or {}).get("in_charge") or [], title)
    return m._replace(charge=charge, charge_source=source)


class View(NamedTuple):
    members: list         # the members, newest join first
    rows: list            # the seats no member stands for (vacant, retired, or replaced), newest first
    retired: list         # (alias, short, reason) of seat-less sessions the log holds as retired
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
    events = events + appended
    info = _projection(events)
    internal = internal_pids()
    forks = {r.get("sessionId") for r in peer_records() if str(r.get("pid")) in internal}
    joined = [(sid, r) for sid, r in info.items()
              if r["latest"] and r["latest"]["kind"] == "joined" and sid not in forks]
    joined.sort(key=lambda x: (x[1]["joined"]["ts"], x[0]), reverse=True)
    out = [_member(sid, r, by_session.get(sid), local.get(sid, {}).get("peer"), sid in local, titles)
           for sid, r in joined]
    sessions = {m.session for m in out}
    rest = sorted((s for s in all_seats if (not s["current"] or s["current"] not in sessions)
                   and (p := seat_project(s)) and p.id == project.id), key=lambda s: s["updated"], reverse=True)
    rows = [_member(s["current"], info.get(s["current"]), s, None, True, titles) if s["current"] else
            Member(session="", short="", alias=s["alias"], name_source="seat", machine=host_name(), local=True,
                   state=state(s), state_age=None, charge="", charge_source="", status=s["now"], by="",
                   worktree=s["worktree"], seat=s)
            for s in rest]
    # Seat-less sessions the log holds as retired, by alias: what a tag that
    # names one is told.
    retired = [(str((r["renamed"] or r["joined"]).get("alias") or sid[:8]), sid[:8], str(r["latest"].get("reason") or ""))
               for sid, r in info.items()
               if r["latest"] and r["latest"]["kind"] == "retired" and r["joined"] and sid not in by_session]
    view = View(out, rows, retired, events, info, len(appended))
    if titles:
        _VIEWS[project.id] = view
    return view


def members(project):
    """The project's members (see project_view)."""
    return project_view(project)[0]


def retired_sessions(project):
    """(alias, short, reason) of the project's seat-less sessions whose
    membership the log holds as retired — `ended` with their process, or
    retired by hand."""
    return view_of(project).retired


def reconcile(project):
    """Join this machine's unrecorded sessions in the project; how many."""
    _VIEWS.pop(project.id, None)
    all_seats = seats()
    return len(_reconcile(project, log_read(project), _local_sessions(project, all_seats),
                          seats_by_session(project, all_seats)))


def _owed(events, session, record):
    # Imported history was delivered by the old chat: it is never owed.
    return [e for e in events
            if not e["writer"].startswith("legacy/")
            and writer_session(e["writer"]) != session and addressed_to(e, session)
            and e["seq"] > _delivery(record, e["writer"])["settled"]]


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
    DELIVERY_ATTEMPTS). Returns {"delivered", "pending", "outcomes"}."""
    session = member.session
    result = {"delivered": 0, "pending": 0, "outcomes": []}
    if not session:
        return result
    with flocked(project_path(project, "delivered", reader_key(session) + ".lock")):
        events = log_read(project)
        streams = {}
        for e in _owed(events, session, delivered_load(project, session)):
            streams.setdefault(e["writer"], []).append(e)
        cursor = cursor_load(project, session)
        for writer, queue in streams.items():
            for i, e in enumerate(queue):
                outcome = push_event(project, member, session, e, events, cursor)
                result["outcomes"].append((e, outcome))
                if outcome.startswith("failed"):
                    if delivered_fail(project, session, writer, e["seq"]) < DELIVERY_ATTEMPTS:
                        result["pending"] += len(queue) - i
                        break
                    daemon_log("gave up delivering %s (%s) to %s after %d attempts: %s" % (
                        event_ref(e), project.name, session, DELIVERY_ATTEMPTS, outcome))
                elif outcome in PUSHED:
                    result["delivered"] += 1
                delivered_settle(project, session, writer, e["seq"])
    return result


def frame_of(project, e, events, session, cursor):
    """The frame an event is pushed as. A `send` keeps its own frame (its id
    is what `send --wait` looks for), its sender shown as the `--from`
    override when it had one; anything else is a chat frame."""
    if e.get("msg_id"):
        return compose_frame(str(e.get("via") or e.get("from") or ""), e["msg_id"], str(e.get("text") or ""))
    unread = sum(1 for x in events if x is not e and x["kind"] in CHAT_KINDS and
                 writer_session(x["writer"]) != session and x["seq"] > cursor.get(x["writer"], 0))
    return compose_chat_frame(project.name, event_ref(e), str(e.get("from") or ""),
                              "@all" if e.get("wake") else "@you", unread, str(e.get("text") or ""))


def push_event(project, member, session, e, events, cursor):
    """Push one event to one member. An addressed event resumes a stopped
    member; an @all (`wake`) reaches only the live. A seat-less member's
    membership is read again from its own file first: `member` may be a
    snapshot taken before a `retire`, which leaves an interactive session's
    process running (§2), and a retired member is pushed nothing — the event
    settles as recorded, as it does for a retired seat."""
    if member.seat is None and latest_membership(_own_events(project, session)) == "retired":
        return "recorded"
    return push_member(member, frame_of(project, e, events, session, cursor), not e.get("wake"), session=session)


def compose_chat_frame(project_name, ref, sender, target, unread, text):
    return "[sminos chat %s %s from %s → %s%s]\n%s" % (
        project_name, ref, sender, target, (" | unread %d" % unread) if unread else "", text)


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


def match_members(name, short, projects):
    """The (project, member) pairs a tag's name answers to among the projects'
    members: their alias (with `short`, an alias whose short starts so), their
    short (`@short`), or their session id. A retired member answers to nothing."""
    found = []
    for p in projects:
        for m in members(p):
            if m.state == "retired":
                continue
            if short:
                hit = m.alias == name and m.short.startswith(short)
            else:
                hit = name in (m.alias, m.short, m.session)
            if hit:
                found.append((p, m))
    return found


def candidate_labels(found, qualify):
    """The candidates a name was ambiguous between, each as the name that tells
    it apart: alias#short, behind its project when several were searched."""
    return ", ".join(sorted(("%s/" % p.name if qualify else "") + "%s#%s" % (m.alias, m.short) for p, m in found))


def unreachable_hint(raw, name, short, projects):
    """The refusal for a tag no member answers to that still names someone: a
    retired or vacant seat, or a seat-less session whose membership ended
    (it is never resumed, so an untagged line is how to leave it a note)."""
    for p in projects:
        for s in project_seats(p):
            if s["alias"] == name and s["current"][:8].startswith(short):
                if s["status"] == "retired":
                    return "%s is retired; re-fill it to reach it" % raw
                if not s["current"]:
                    return "%s is vacant — fill it to reach it" % raw
        for alias, sh, reason in retired_sessions(p):
            if alias == name and sh.startswith(short):
                if reason == "ended":
                    return ("%s: %s's session ended; say it untagged to leave a note — it reads the chat when "
                            "it is resumed" % (raw, alias))
                return "%s is retired; it re-joins when its session runs again" % raw
    return ""


def name_scope(project, explicit=""):
    """The projects a name is looked up in: the one it names, else the
    speaker's, else — from a directory that is no project — every project
    known here."""
    if explicit:
        return [find_project(explicit)]
    return [project] if project is not None else known_projects()


def resolve_tags(project, text):
    """Resolve a message's leading tags at submission. Returns (destination,
    recipients [{session, alias}], text, wake). The destination is the
    sender's project, or the one the tags name (from no project, the one the
    names are found in); tags naming two projects are refused, as are a tag
    matching no member and one matching several (named as alias#short).
    `@all` is the members live at submission."""
    tags = leading_tags(text)
    if not tags:
        return project, [], text, False
    if any(is_all(t) for t in tags):
        if len(tags) != 1:
            die("@all stands alone")
        if project is None:
            die("@all needs a project: say it in a project's directory, or with --in <project>")
        live = [m for m in members(project) if m.state in FILLED]
        return project, [{"session": m.session, "alias": m.alias} for m in live], text, True

    def one_project(projects):
        if len(projects) > 1:
            die("one message, one project: the tags name %s" % ", ".join(sorted(p.name for p in projects.values())))

    one_project({p.id: p for t in tags for p in [find_project(t["project"]) if t["project"] else project] if p})
    destinations, recipients = {}, []
    for t in tags:
        scope = name_scope(project, t["project"])
        found = match_members(t["name"], t["short"], scope)
        if len(found) > 1:
            die("ambiguous %s matches: %s" % (t["raw"], candidate_labels(found, len(scope) > 1)), EXIT_UNKNOWN)
        if not found:
            hint = unreachable_hint(t["raw"], t["name"], t["short"], scope)
            if hint:
                die(hint, EXIT_UNKNOWN)
            die("no member %s in %s" % (t["raw"], "project %s" % scope[0].name if len(scope) == 1 else
                                        "any project known here"), EXIT_UNKNOWN)
        p, m = found[0]
        destinations[p.id] = p
        if all(r["session"] != m.session for r in recipients):
            recipients.append({"session": m.session, "alias": m.alias})
    one_project(destinations)
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


def push_member(member, text, tagged, session=None):
    """Push one frame to a member: its inbox socket when live; for a seat, a
    resume when it is stopped and the message is addressed to it (`tagged`).
    A session sminos did not spawn is never resumed: it is the human's to
    reopen, and reads the chat when it is back. Given `session`, a seat that
    now holds another session is not this message's recipient: delivery goes
    by session id, so a replacement cannot misroute it."""
    session = session or member.session
    if member.seat is None:
        peer = peer_for_session(session)
        if not peer:
            return "recorded"
        try:
            send_frame(socket_path_of(peer), text)
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
            send_frame(socket_path_of(peer), text)
            return "sent"
        except SendFailed as e:
            return "sent?" if e.phase == "after" else "failed:%s" % e
    if not tagged:
        return "recorded"
    st = seat_state(fresh, None)  # the probe above found no live peer
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


def cmd_say(a):
    """Record a message in a project's log, and deliver it to whom it tags."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if sid:
        if a.in_:
            die("--in is for an operator, not a session — tag @<project>/<name> to speak into another project")
        caller = caller_seat()
        home = caller_project(caller)
        sender = caller["alias"] if caller else default_from("")
        writer, kind = writer_id(sid), "say"
    else:
        home = find_project(a.in_) if a.in_ else caller_project()
        sender, writer, kind = "human", writer_id(), "human"
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
    try:
        e = log_append(dest, writer, kind, **fields)
    except OSError as err:
        die("say could not be recorded: %s" % err, 1)
    print("recorded %s in %s" % (event_ref(e), dest.name))
    by_session = {m.session: m for m in members(dest)}
    for r in recipients:
        member = by_session.get(r["session"])
        if member is not None and not member.local:
            # Owed to it in the log; its own machine's daemon delivers it,
            # once this machine's daemon has pushed it: ask for that now.
            print("%s: recorded (on %s)" % (r["alias"], member.machine))
            nudge_daemon()
            continue
        result = deliver_next(dest, member) if member else {"outcomes": []}
        mine = [o for ev, o in result["outcomes"] if ev["writer"] == writer and ev["seq"] == e["seq"]]
        if mine:
            print("%s: %s" % (r["alias"], mine[0]))
            continue
        held = next((o for ev, o in result["outcomes"] if ev["writer"] == writer), "")
        print("%s: pending%s" % (r["alias"], " behind an earlier undelivered message (%s)" % held if held else ""))


def target_label(e):
    to = e.get("to")
    if to == "*":
        return "*"
    if e.get("wake"):
        return "@all"
    if isinstance(to, list):
        return " ".join("@" + str(r.get("alias") or "?") for r in to if isinstance(r, dict)) or "-"
    return str(to or "-")


def chat_line(e):
    lines = str(e.get("text") or "").split("\n")
    out = ["%s %s %s → %s  %s" % (e["ts"][11:19], event_ref(e), e.get("from", ""), target_label(e), lines[0])]
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
    pool = [e for e in events if e["kind"] in kinds]
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
    for e in window:
        print(chat_line(e))
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

HOST_KINDS = ("message", "question", "answered")
ASK_TOOL = "mcp__doperpowers__AskUserQuestion"
# What the tool returns for an async call it accepted (hooks/mods/ask.tsx).
ASYNC_RESULT = ("Your questions are waiting for the human; this call does not wait for them. Their answer will "
                "reach you in a later message that quotes each question. Go on with work that does not depend on it.")
# A delivery of the human's answer, in whichever row the engine stored it.
DELIVERY_RE = re.compile(r"The human responded to your async AskUserQuestion \(call ([^)\s]+)\): ")
PLUGIN_PROMPT = "The doperpowers plugin sent a message:\n"
# The engine's framing after the text of a prompt a plugin submitted.
PLUGIN_FRAMING = "\n\nThis is how Claude Code surfaces a prompt a plugin submits"


def extract_marks(text):
    """[{"kind": "message", "text"}]: the marked spans of one assistant text,
    read as the to-human mod reads them (sminos_marks): tags in code are
    literal, nested marks are runs of their own, an unclosed mark runs to the
    end, and every alias is a message."""
    return [{"kind": s["kind"], "text": s["text"]} for s in sminos_marks.parse(text)["spans"] if s["text"]]


def _blocks(record, kind):
    """A transcript record's content blocks of one type; a string content is
    one text block."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if kind == "text" else []
    return [b for b in content if isinstance(b, dict) and b.get("type") == kind] if isinstance(content, list) else []


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
            if isinstance(t, str) and t.startswith(PLUGIN_PROMPT)]


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


def _ask_events(records):
    """(record index, event) for the async asks the records hold, in record
    order: a `question` for each tool_use of the tool with `async` true whose
    paired tool_result is the tool's accepted result, and an `answered` for
    each delivery. A blocking ask — the plugin's without async, or the native
    AskUserQuestion — is no event: the session waits, and the human goes to it."""
    calls, results, out = [], {}, []
    for i, r in enumerate(records):
        for b in _blocks(r, "tool_use"):
            inp = b.get("input")
            if b.get("name") == ASK_TOOL and isinstance(inp, dict) and inp.get("async") is True and b.get("id"):
                calls.append((i, str(b["id"]), inp))
        for b in _blocks(r, "tool_result"):
            results[str(b.get("tool_use_id") or "")] = b
        for text in _delivery_texts(r):
            out += [(i, {"kind": "answered", "src": call, "text": answer}) for call, answer in _deliveries(text)]
    for i, call, inp in calls:
        res = results.get(call)
        if res is None or res.get("is_error") is True or _result_text(res.get("content")) != ASYNC_RESULT:
            continue
        questions = [q for q in inp.get("questions") or [] if isinstance(q, dict)]
        out.append((i, {"kind": "question", "text": [str(q.get("question") or "") for q in questions],
                        "choices": [str(o.get("label") or "") for q in questions
                                    for o in q.get("options") or [] if isinstance(o, dict)], "src": call}))
    out.sort(key=lambda x: x[0])
    return out


def extract_asks(records):
    """The async asks and their answers the transcript records hold, in order:
    {"kind": "question", "src": call id, "text": [questions], "choices": [labels]}
    and {"kind": "answered", "src": call id, "text": the engine's result text}."""
    return [e for _, e in _ask_events(records)]


def host_events(records, alias):
    """The events a run of transcript records holds for the host, in record
    order, ready for log_append_batch: each marked span of an assistant record
    as a `message` (src `<record uuid>#<span index>`), each accepted async ask
    as a `question`, each delivery of an answer as `answered` (src the call id)."""
    out = []
    for i, r in enumerate(records):
        if r.get("type") != "assistant" or not isinstance(r.get("uuid"), str) or not r["uuid"]:
            continue
        spans = [s for b in _blocks(r, "text") for s in extract_marks(str(b.get("text") or ""))]
        out += [(i, {"kind": "message", "from": alias, "to": "host", "text": s["text"], "src": "%s#%d" % (r["uuid"], n)})
                for n, s in enumerate(spans)]
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


def transcript_title(session_id):
    """The latest `ai-title` record of a session's transcript on this machine:
    the harness rewrites it as the conversation moves, so it is the current
    topic, the last fallback of the in-charge line (§5). Looked for in the
    file's last 8 MiB."""
    path = transcript_path(session_id)
    if not path:
        return ""
    try:
        with open(path, "rb") as f:
            for _, line in _lines_backward(f, _complete_end(f), budget=8 << 20):
                if b'"ai-title"' in line:
                    r = _record(line)
                    if r and r.get("type") == "ai-title" and isinstance(r.get("aiTitle"), str):
                        return " ".join(r["aiTitle"].split())
    except OSError:
        pass
    return ""


def _position_path(project, session):
    return project_path(project, "cursors", "export", reader_key(session) + ".json")


def _position_load(project, session):
    try:
        with open(_position_path(project, session)) as f:
            pos = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(pos, dict) and isinstance(pos.get("uuid"), str) and type(pos.get("offset")) is int:
        return pos
    return None


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


def position_init(project, session, tpath):
    """At SessionStart, set the export position to the transcript's current
    end — only when the session has none, so a resume keeps it and a mark
    written before the process died is still exported."""
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
        write_json(path, pos)


def _records_past(project, session, tpath):
    """(records, start, held): the transcript's complete main-chain records
    past the session's export position, as (offset, record), the offset they
    start at, and whether the position held (else the trailing run, §4);
    None when the transcript cannot be opened."""
    pos = _position_load(project, session)
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
            if r is not None and not r.get("isSidechain"):
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


def await_flush(tpath, last_message, until):
    """Before a Stop's export: wait, polling, until the transcript's last
    message is the turn's answer — an assistant message reading the payload's
    `last_assistant_message` — or until `until` (epoch seconds). The same text
    earlier in the transcript is not the answer: a mark the turn repeats is
    still waited for. True when it is there; at the deadline the export takes
    what is there, and the next Stop the rest."""
    text = str(last_message or "").strip()
    if not text:
        return True
    while True:
        last = _last_message_text(tpath)
        if last is not None and last.strip() == text:
            return True
        if time.time() + FLUSH_POLL > until:
            return False
        time.sleep(FLUSH_POLL)


def export_host(project, session, tpath, alias):
    """Append what the transcript holds for the host past the session's export
    position, as one batch, then advance the position to the last assistant
    record read whose async asks all have their results (so a question is
    never split from the result that accepts it). With no position, the
    trailing run of assistant records is exported (§4). Exports of a session
    are serialised by its export lock, taken before the log's locks."""
    with flocked(project_path(project, "cursors", "export", reader_key(session) + ".lock")):
        past = _records_past(project, session, tpath)
        if past is None:
            return 0
        records, start, held = past
        events = host_events([r for _, r in records], alias)
        if events:
            log_append_batch(project, writer_id(session), events)
        new, pending = None, set()
        for at, r in records:
            for b in _blocks(r, "tool_use"):
                if b.get("name") == ASK_TOOL and b.get("id"):
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


def _writer_events(project, host, session):
    """The events of the writer `<host>/<session>`, read directly."""
    path = os.path.join(project.home, "log", "%s.%s.jsonl" % (host, session))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [e for e in map(parse_event, f) if e]
    except OSError:
        return []


def _former_events(project, session):
    """The session's events under the names this machine wrote under before
    it enrolled, for a session it held under them (is_self), oldest name
    first: still the session's own, though nothing appends to them any more."""
    return [e for host, held in machine_identity()[1].items() if session in held
            for e in _writer_events(project, host, session)]


def _own_events(project, session):
    """The session's own writer files, read directly (the hook reads nothing
    else of the log): under this machine's former names, then its name now."""
    return _former_events(project, session) + _writer_events(project, host_name(), session)


def record_session(project, session, tpath, event, last_message=""):
    """The hook's work for one session (§4). Membership on sight, as
    reconciliation decides it: a seat whose record is not retired, or a
    session the harness records as `interactive` or `bg`, and never an
    internal fork. SessionStart sets a member's export position, then joins
    it: the position first, so a join cut short by the hook's bound (a lock
    held elsewhere) still leaves the first Stop a position rather than the
    trailing-run fallback. Stop joins it if it is not yet (its harness record
    may not have existed at its start) and exports. A session the harness
    has not registered yet at its start is not joined on no evidence, but its
    position is set, so its first turn counts whole at its Stop. A session
    that is not a member records nothing. At Stop, the export first waits a
    little for the turn's last message to reach the transcript (await_flush)."""
    seat = seats_by_session(project, [s for s in seats() if s["current"] == session]).get(session)
    peer = next((r for r in peer_records() if r.get("sessionId") == session), None)
    if peer is not None and str(peer.get("pid")) in internal_pids():
        return
    if seat is None and peer is None:
        if event == "SessionStart":
            position_init(project, session, tpath)
        return
    if not joinable(seat, peer):
        return
    if event == "SessionStart":
        position_init(project, session, tpath)
    own = _own_events(project, session)
    if latest_membership(own) != "joined":
        join_on_sight(project, session, seat, peer, True)
        own = _own_events(project, session)
    if event != "Stop" or latest_membership(own) != "joined":
        return
    alias = (seat or {}).get("alias") or str((peer or {}).get("name") or "")
    if not alias:
        named = [e for e in own if e["kind"] in ("joined", "renamed") and e.get("alias")]
        alias = str(named[-1]["alias"]) if named else session[:8]
    until = time.time() + FLUSH_WAIT
    if _RECORD_DEADLINE is not None:
        until = min(until, _RECORD_DEADLINE - 0.5)
    await_flush(tpath, last_message, until)
    export_host(project, session, tpath, alias)


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
    keeps waiting on the same locks."""
    if os.environ.get("SMNS_INTERNAL"):
        return
    global _RECORD_DEADLINE
    seconds = float(os.environ.get("SMNS_RECORD_TIMEOUT") or RECORD_TIMEOUT)
    deadline = _RECORD_DEADLINE = time.time() + seconds
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
        cmd_record(None)
    except RecordTimeout:
        _record_gave_up(seconds, "a lock the export needs held elsewhere")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def cmd_record(_a):
    """The hook's verb: one Stop or SessionStart payload on stdin. Records
    nothing for an internal fork, a session in no project, or a non-member;
    a failure is a line in daemon.log, never an exit that blocks a turn
    (run_record bounds it in time)."""
    if os.environ.get("SMNS_INTERNAL"):
        return
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    session, cwd = str(payload.get("session_id") or ""), str(payload.get("cwd") or "")
    tpath, event = str(payload.get("transcript_path") or ""), str(payload.get("hook_event_name") or "")
    if not (UUID_RE.match(session) and cwd and tpath):
        return
    try:
        project = resolve_project(cwd)
        if project is not None:
            record_session(project, session, tpath, event, str(payload.get("last_assistant_message") or ""))
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
    """What the members sent their human: messages, questions, and answers.
    A view, not a cursor read: the last 30 host events (-n N), or those since
    a time (--since TS), chosen before anything is grouped; the reader's chat
    cursor never moves. A question shows its answer under it, or is marked
    open; an answer whose question falls outside the window is shown where it
    falls, its question beneath it as context (with --json, the question
    first)."""
    events = log_read(project, kinds=HOST_KINDS)
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

DERIVE_PROMPT = ("In one line: what is this session in charge of in this project — its standing responsibility, "
                 "not its latest step? Answer with the line only.")
DERIVE_MIN_PROMPTS = 10
DERIVE_EVERY = 6 * 3600
DERIVE_LINE_MAX = 120


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
                _append(project, writer_id(sid or None),
                        [{"kind": "in-charge", "session": m.session, "text": line, "source": "set"}])
            except OSError as e:
                die("the line of %s was not recorded in %s's log: %s" % (m.alias, project.name, e), 1)
        name = m.alias
    print("%s in charge of: %s" % (name, line or "(cleared)"))


class DeriveFailed(Exception):
    def __init__(self, reason, stderr=""):
        super().__init__(reason)
        self.reason, self.stderr = reason, stderr


def human_prompts(path, enough):
    """How many prompts the human typed into a transcript, counted up to
    `enough`: user records that are neither a tool's result, nor a delivery
    (a peer's frame, a plugin's or a notification's prompt), nor meta."""
    n = 0
    with open(path, "rb") as f:
        for line in f:
            if b'"user"' not in line:
                continue
            r = _record(line)
            if not r or r.get("type") != "user" or r.get("isMeta") or r.get("isSidechain"):
                continue
            origin = r.get("origin")
            if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
                continue
            message = r.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not content or _blocks(r, "tool_result"):
                continue
            n += 1
            if n >= enough:
                break
    return n


def derive_refusal(project, m):
    """Why a member is not derived, or "": only a local member with no set
    line and no name its human gave, at least ten prompts from its human, and
    no derived line in the last six hours (§5)."""
    if not m.session:
        return "it holds no session"
    if not m.local:
        return "it runs on %s" % m.machine
    if m.charge_source == "set":
        return "its line is set"
    if m.charge_source == "name":
        return "its human named it"
    path = transcript_path(m.session)
    if not path:
        return "no transcript of it on this machine"
    derived = latest_across_writers([e for e in log_read(project, kinds=("in-charge",))
                                     if e.get("session") == m.session and e.get("source") == "derived"])
    age = ts_age(derived["ts"]) if derived else None
    if age is not None and age < DERIVE_EVERY:
        return "derived %s ago" % short_age(age)
    try:
        n = human_prompts(path, DERIVE_MIN_PROMPTS)
    except OSError as e:
        return "its transcript is unreadable: %s" % e
    if n < DERIVE_MIN_PROMPTS:
        return "%d prompt(s) from its human, fewer than %d" % (n, DERIVE_MIN_PROMPTS)
    return ""


def member_cwd(project, m):
    """Where a member's session runs — where its fork must start for
    `--resume` to find the transcript."""
    candidates = [(m.seat or {}).get("cwd"), (session_running(m.session) or {}).get("cwd")]
    candidates += [e.get("cwd") for e in reversed(_own_events(project, m.session)) if e["kind"] == "joined"]
    return next((c for c in candidates if isinstance(c, str) and c and os.path.isdir(c)), project.root or os.getcwd())


def answer_line(text):
    """The fork's answer as an in-charge line: its marks stripped, its first
    line, at most 120 characters."""
    spans = extract_marks(text)
    text = sminos_marks.TAG.sub("", spans[0]["text"] if spans else text)
    return next((x.strip() for x in text.splitlines() if x.strip()), "")[:DERIVE_LINE_MAX]


def sweep_internal():
    """Markers of internal forks older than a day: their forks are long gone."""
    d = os.path.join(root(), "internal")
    for name in (os.listdir(d) if os.path.isdir(d) else ()):
        path = os.path.join(d, name)
        try:
            if time.time() - os.path.getmtime(path) > 86400:
                os.unlink(path)
        except OSError:
            pass


def derive_line(project, m):
    """Fork the member's session headless and return its one-line answer.
    The fork starts behind a gate: its pid is marked internal before it can
    register. Its session id is minted here (`--session-id`), so its
    transcript is known and deleted whatever the outcome — an answer, a
    crash, a timeout — and so is the marker. The prompt comes last: `--tools`
    takes several values and would swallow a prompt right after it."""
    fork = str(uuidlib.uuid4())
    args = ["claude", "-p", "--resume", m.session, "--fork-session", "--session-id", fork, "--tools", "",
            "--output-format", "json", DERIVE_PROMPT]
    gate_r, gate_w = os.pipe()
    marker = ""
    out = err = ""
    obj = None
    try:
        try:
            proc = subprocess.Popen(["/bin/sh", "-c", 'read -r _ <&%d; exec %d<&-; exec "$@"' % (gate_r, gate_r), "sh"]
                                    + args, cwd=member_cwd(project, m), env={**os.environ, "SMNS_INTERNAL": "1"},
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
            raise DeriveFailed("the fork timed out after %ds" % timeout, err)
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
            raise DeriveFailed("the fork failed (exit %d)" % proc.returncode, err)
        line = answer_line(str(obj.get("result") or ""))
        if not line:
            raise DeriveFailed("the fork answered nothing", err)
        return line
    finally:
        if gate_w != -1:
            os.close(gate_w)
        for sid in {fork, str((obj or {}).get("session_id") or "")}:
            path = transcript_path(sid) if UUID_RE.match(sid) and sid != m.session else ""
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
    project known here, as the daemon runs it hourly."""
    if bool(a.member) == bool(a.all):
        die("usage: sminos derive <member> | --all")
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
    failed = 0
    for project, m in targets:
        why = derive_refusal(project, m)
        if why:
            print("%s: not derived — %s" % (m.alias, why))
            continue
        try:
            line = derive_line(project, m)
        except DeriveFailed as e:
            failed += 1
            tail = [x for x in (e.stderr or "").splitlines() if x.strip()][-5:]
            sys.stderr.write("sminos: derive %s failed: %s; nothing recorded\n%s" % (
                m.alias, e.reason, "".join("    %s\n" % x for x in tail)))
            continue
        lifecycle(project, m.session, "in-charge", text=line, source="derived")
        print("%s: %s" % (m.alias, line))
    if failed:
        sys.exit(1)


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
        print("project  %s\nid       %s\nremote   %s\nhub      %s\nroot     %s\nhome     %s" % (
            p.name, p.id, p.remote or "-", ("%s (org %s)" % (p.hub["url"], p.hub["org"]) if hub_wellformed(p.hub) else "malformed: no git, no hub")
            if p.hub is not None else "-",
            p.root, p.home))
    else:
        project_attach(a)


def project_init(a):
    """Write .smns at the repository's root; with --hub, name this machine's
    hub in it — added to a .smns that exists, which changes nothing else."""
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
    name = a.name or safe_name(os.path.basename(owning_repo(top) or top)) or "project"
    if "/" in name or "\n" in name or not name.strip():
        die("a project name is one line without '/': %r" % name)
    data = {"project": str(uuidlib.uuid4()), "name": name, "remote": a.remote or ""}
    if hub:
        data["hub"] = hub
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(path, 0o644)  # committed: every clone reads it
    _PROJECTS.clear()
    project_path(resolve_project(top), "log")
    print("project %s (%s) at %s%s — commit it, so every clone is the same project" % (
        name, data["project"], path, ", a hub project of %s (org %s)" % (hub["url"], hub["org"]) if hub else ""))


def project_attach(a):
    """Adopt the existing log/ as a working tree of the project's remote —
    the mirror's first half; sminos_daemon owns the mirror. A hub project has
    no mirror: it syncs through its hub alone."""
    p = resolve_project(os.path.abspath(a.dir or os.getcwd()))
    if p is None:
        die("no project here to attach", EXIT_UNKNOWN)
    if p.hub is not None:
        die("project %s syncs through its hub (%s), never through git: there is no mirror to attach%s" % (
            p.name, p.hub["url"] or "malformed", "; its remote is the log's archive" if p.remote else ""), 1)
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
    place.

    A full id — a seat id or session id — names its seat directly, and so
    does `group/alias` when the qualifier is a group and no project. Any other
    name, `<project>/<alias>` by the project's name or id included, is
    resolved as a tag is: its projects (the one it names, else the caller's,
    else every project known here) are reconciled, and the name is matched
    against every member and every seat no member stands for (vacant,
    retired), so a seat and a seat-less session sharing an alias are refused
    as ambiguous rather than the seat being taken. A qualifier that is both a
    project and a group falls back to the group when the project has no match."""
    scope = caller_scope()

    def exact(kind, res):
        if kind == "ambiguous":
            die(ambiguous_seat(q, res), EXIT_UNKNOWN)
        if kind == "ok":
            reconcile(seat_project(res))  # the verb reads the project; no liveness probe needed
            return ("seat", res, q if res["current"] == q and res["seat_id"] != q else "")
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
    if proj and not short and find_project(proj, required=False) is None:
        return group_seat(proj, name) or ("none",)
    projects = known_projects() if UUID_RE.match(q) else name_scope(scope, proj)
    found, seen = [], set()
    for p in projects:
        ms, rows = project_view(p)
        for m in ms + rows:
            if short:
                hit = bool(m.short) and m.alias == name and m.short.startswith(short)
            else:
                hit = name == m.alias or (bool(m.session) and name == m.session)
            # One seat is one target, though its session joined one project
            # and its record now resolves to another (a cwd that moved).
            key = m.seat["seat_id"] if m.seat else m.session
            if hit and key not in seen:
                seen.add(key)
                found.append((p, m))
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
    return ("seat", m.seat, m.session if short or name == m.session else "") if m.seat else ("member", project, m)


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
    registry, process start times, resolved projects and their views — so a
    long-lived process (the chart TUI, the daemon's loop) sees the fleet as it
    is now rather than as it was at launch. Nothing is read until asked."""
    global _AGENTS_LOADED, _PEERS, _SELF
    _AGENTS_LOADED = False
    _PEERS = None
    _SELF = None
    _PSTART.clear()
    _PROJECTS.clear()
    _HOMES.clear()
    _VIEWS.clear()


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
    global _PEERS
    if _PEERS is None:
        recs = []
        for p in glob.glob(os.path.join(home_dir(), ".claude", "sessions", "*.json")):
            try:
                with open(p) as f:
                    d = json.load(f)
            except Exception:
                continue
            if isinstance(d, dict):
                recs.append(d)
        _PEERS = recs
    return _PEERS


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True
    return True


_PSTART = {}


def proc_start(pid):
    """The live process's start time as `ps -o lstart=` prints it, whitespace
    normalised; "" when ps cannot tell."""
    key = str(pid)
    if key not in _PSTART:
        try:
            # The harness records procStart in the C locale ("Tue Sep  1 20:27:08
            # 2026"); ps must print the same shape, not the user's locale.
            out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))], capture_output=True, text=True,
                                 timeout=5, env={**os.environ, "LC_ALL": "C", "LANG": "C"}).stdout
        except Exception:
            out = ""
        _PSTART[key] = " ".join(out.split())
    return _PSTART[key]


def _parse_lstart(s):
    try:
        return time.strptime(" ".join(str(s).split()), "%a %b %d %H:%M:%S %Y")
    except (ValueError, TypeError):
        return None


def same_process(rec):
    """Is the record's pid still the process the record described?

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
    live = _parse_lstart(proc_start(rec.get("pid")))
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


def send_frame(path, text):
    """Write one message frame to a session's inbox socket.

    The frame the harness documents for scripts is a plain user message; it is
    delivered as a peer message ("another Claude session sent…"). The frame
    carries no sender name, so callers put identity in the text's first line.
    Raises SendFailed(phase) — see the class.
    """
    frame = {"type": "user", "message": {"role": "user", "content": text}}
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
            s.recv(4096)  # an optional ack; nothing rides on it
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
    """A seat's one state word, one of STATES, given the result of ONE
    liveness probe of its `current` session (`peer_for_session`, or None when
    it found no live peer or `needs_probe` said not to probe). Read in this
    order: retired (the recorded status), vacant (no `current`), then the
    live peer — the session record the harness's own ListAgents reads —
    then stopped when the session's transcript is on this machine (what a
    `claude --bg --resume` needs), else gone. The harness listing is never
    asked. A caller that probes once and routes on the same probe passes it
    here, so the word and the route cannot disagree."""
    if seat.get("status") == "retired":
        return "retired"
    if not seat.get("current"):
        return "vacant"
    if peer:
        return peer_state(peer)
    return "stopped" if transcript_path(seat["current"]) else "gone"


def state(seat):
    """A seat's one state word — seat_state after one probe of its session."""
    return seat_state(seat, peer_for_session(seat["current"]) if needs_probe(seat) else None)


_SELF = None  # (this machine's name, {former name: its sessions}), per invocation


def machine_identity():
    """(name, former): this installation's machine name — the name it enrolled
    under at a desk hub (daemon/hub.json, written by `hub enroll`), else
    DAEMON_HOST, else the system's host name — and, for each name it wrote
    under before it enrolled, the sessions it held under that name then
    ({name: frozenset}, oldest name first)."""
    global _SELF
    if _SELF is None:
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
    the env. An EMPTY settings value declares the PLAIN route, enforced below
    the argv by dropping the gateway transport env too.
    """
    env = dict(os.environ)
    env.pop("RUNNER_TRACKING_ID", None)
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
    until the old turn's harness row is gone or no longer running AND no live
    peer socket answers for the session. Resuming while the old process still
    runs makes the harness start a copy; a stop that did not take is refused
    loudly rather than papered over. True iff the turn is confirmed down."""
    deadline = time.time() + float(os.environ.get("SMINOS_STOP_TIMEOUT", "30"))
    while True:
        agents_refresh()
        row = agent_row(short=short) if short else harness_row(s)
        running = bool(row) and normalize_state(row) in ("working", "blocked")
        global _PEERS
        _PEERS = None
        if not running and peer_for_session(cur) is None:
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


def transcript_path(session_id):
    """Munging-agnostic: the harness mangles the cwd into the project-dir name,
    so glob for the transcript by its unique session id instead. A session's
    transcript sits directly in its project dir (projects/<dir>/<id>.jsonl;
    only subagent files nest deeper), so one level is searched — a recursive
    glob walks every subagent file on the machine, ~0.6 s a call on a busy
    one, and state() asks this for every seat without a live peer. A session
    found under two project dirs (a repository that moved) answers with the
    one written last."""
    if not session_id:
        return ""
    hits = glob.glob(os.path.join(home_dir(), ".claude", "projects", "*", session_id + ".jsonl"))
    return max(hits, key=_mtime) if hits else ""


def transcript_rows(session_id):
    f = transcript_path(session_id)
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
    f = transcript_path(session_id)
    if not f:
        return False
    try:
        with open(f) as fh:
            return marker in fh.read()
    except OSError:
        return False


def transcript_reply(session_id, seat_ref="<seat>"):
    """The last assistant text of a session's transcript, plus a rendering of a
    pending AskUserQuestion (a turn can end blocked on it; the question lives
    in the tool_use INPUT, not in text — without rendering it the reply would
    be empty and the orchestrator would have to dig the transcript by hand)."""
    rows = transcript_rows(session_id)
    text = ""
    for r in reversed(rows):
        if r.get("type") == "assistant":
            c = r.get("message", {}).get("content")
            t = ""
            if isinstance(c, list):
                t = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            elif c:
                t = str(c)
            if t.strip():
                text = t.strip()
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
    tx = transcript_path(turn_id)
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
    for nodes_dir in glob.glob(os.path.join(r, "groups", "*", "nodes")):
        g = os.path.basename(os.path.dirname(nodes_dir))
        for nf in glob.glob(os.path.join(nodes_dir, "*.json")):
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


def claude_args(alias, model, settings, effort, worktree=""):
    """argv for a FRESH background launch. Never used for a resume: a resumed
    background session keeps its saved options, and any flag on
    `claude --bg --resume` makes the harness start a COPY instead (observed
    live, v2.1.257: "keeps its own saved options, so the flags you passed
    started a copy")."""
    args = ["--bg", "--permission-mode", "auto", "-n", alias]
    if worktree:
        args += ["--worktree", re.sub(r"[^a-zA-Z0-9._-]", "-", worktree)]
    if model:
        args += ["--model", model]
    if settings:
        args += ["--settings", settings]
    if effort:
        args += ["--effort", effort]
    return args


def launch_settings(settings):
    """The settings a fresh seat launches with: the caller's, plus, when
    SMINOS_HOME (or the legacy DAEMON_HOME) is set, `env.SMINOS_HOME` naming
    this registry.

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
    decided by the caller's own settings (launch_env)."""
    home = os.environ.get("SMINOS_HOME") or os.environ.get("DAEMON_HOME")
    if not home:
        return settings
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
    merged["env"] = {**env, "SMINOS_HOME": root()}
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
                model, settings, effort, wait, locks, verb, stamp=None):
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
    renders the preamble. Returns nothing (prints; may exit)."""
    prev = reload_seat(seat_id) if seat_id else None
    project = seat_project({"cwd": cwd, "group": group})
    by = caller_alias()
    preamble = render_preamble(project.name, alias, by)
    task_text = compose_task(task, brief or "", preamble)
    short, banner = run_claude_bg(claude_args(alias, model, launch_settings(settings), effort, worktree) + [task_text],
                                  cwd, settings)
    if not short:
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
           **joined_fields(alias, "seat", runcwd or cwd, worktree or "", role or "", rec_id, by))
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
                stamp=parse_stamps(a.stamp))


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
    cwd = os.path.abspath(os.path.expanduser(s["cwd"]))
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
    elif not row and peer_for_session(cur) and s["short"] and identity_local(s["host"], s["boot_id"], cur):
        stop_short = s["short"]
    if stop_short:
        if not claude_stop(stop_short):
            raise ResumeRefused("claude stop %s failed for %s/%s — not resuming over a turn that may still be running" % (
                stop_short, s["group"], s["alias"]), 1)
        if not wait_stopped(s, stop_short, cur):
            raise ResumeRefused("the current turn of %s/%s (%s) is still running %ss after claude stop — not launching a "
                "resume (it would start a copy)" % (s["group"], s["alias"], stop_short,
                                                    os.environ.get("SMINOS_STOP_TIMEOUT", "30")), 1)
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
    else the harness session name from the peer registry, else `session:<id8>`.
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
    for r in peer_records():
        if r.get("sessionId") == sid and r.get("name"):
            return str(r["name"])
    return "session:%s" % sid[:8]


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


def compose_frame(sender, msg_id, msg):
    """Every delivery — socket, resume, codex queue — opens with this line; the
    id is what `--wait` looks for in the target's transcript."""
    return "[sminos message from %s id=%s]\n%s" % (sender, msg_id, msg)


def send_to_seat(s0, text, msg_id, wait, record=None, session=""):
    """Deliver a frame to one seat under its lifecycle lock. The lock covers
    target selection, the socket delivery, and the status write, so a
    concurrent fill/resume/retire cannot slip between them. A live seat takes
    the frame on its inbox socket and is recorded `working`; a stopped one is
    resumed with the frame as its message; vacant, retired, and gone seats
    are refused, pointing at the verb that can reach them. Given `session`,
    the one the name bound (find_target), a seat that no longer holds it is
    refused.

    `record(seat)`, when given, appends the message to the seat's project log
    once the seat is known reachable and returns its SendDelivery (or None
    when the seat has no project): the push then carries every earlier event
    of the same writer still owed to the seat, in order, and the delivery
    record is settled on sent, woken, or uncertain and noted as failed
    otherwise — so a send that dies on the way is the daemon's to retry."""
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
    delivery = record(s) if record else None
    if delivery and not delivery.queue:
        # A concurrent deliverer pushed it between the append and our lock: no
        # second push, but --wait still waits on this message's id.
        delivery.release()
        row = harness_row(s)
        was_idle = (normalize_state(row) not in ("working", "blocked")) if row else (
            not peer or peer.get("status") != "busy")
        guard = same_gen(current_gen(s["seat_id"]))
        unlock(locks)
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
        send_frame(sock, delivery.payload(True) if delivery else text)
    except SendFailed as e:
        if e.phase == "before":
            # Nothing reached the peer (the session exited between the
            # liveness check and the write): fall through to the resume path.
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
    including this send — an earlier pending one goes first, in the same push."""

    def __init__(self, project, session, writer, event):
        self.project, self.session, self.writer = project, session, writer
        self.lock = open(project_path(project, "delivered", reader_key(session) + ".lock"), "a")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.events = log_read(project)
        self.queue = [e for e in _owed(self.events, session, delivered_load(project, session))
                      if e["writer"] == writer and e["seq"] <= event["seq"]]
        self.cursor = cursor_load(project, session)
        self.skipped = []

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


def record_send(s, sender, via, text, msg_id):
    """`send` is recorded in the target's project log — `human` from the
    operator, `say` from a session — to the one session it reaches, then
    delivered through that session's delivery record (SendDelivery). A message
    the log cannot hold is not sent: the failure exits non-zero first."""
    if not s["current"]:
        return None
    return record_message(seat_project(s), s["current"], s["alias"], sender, via, text, msg_id)


def record_message(project, session, alias, sender, via, text, msg_id, deliver=True):
    """Append a `send` to the project's log, addressed to one session, and —
    unless the recipient is another machine's to deliver — open its
    SendDelivery. A message the log cannot hold is not sent: exit 1 first."""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    writer = writer_id(sid or None)
    fields = {"from": sender, "to": [{"session": session, "alias": alias}], "text": text, "msg_id": msg_id}
    if via and via != sender:
        fields["via"] = via
    try:
        event = log_append(project, writer, "say" if sid else "human", **fields)
        return SendDelivery(project, session, writer, event) if deliver else event
    except OSError as e:
        die("send not delivered: it could not be recorded in %s's log (%s)" % (project.name, e), 1)


def send_to_member(project, m, sender, via, text, msg_id):
    """send to a member that holds no seat here. A remote member's send is
    recorded and owed: its own machine's daemon delivers it. A local one is
    reached over its inbox socket while it runs; a session sminos did not
    spawn is never resumed — it is the human's to reopen."""
    if not m.local:
        e = record_message(project, m.session, m.alias, sender, via, text, msg_id, deliver=False)
        print("recorded %s for %s on %s — its machine delivers it" % (event_ref(e), m.alias, m.machine))
        nudge_daemon()
        return
    peer = peer_for_session(m.session)
    if not peer:
        die("%s is not live (%s) — a session sminos did not spawn is reached only while it runs; "
            "sminos say records for it" % (m.alias, m.state), EXIT_UNKNOWN)
    delivery = record_message(project, m.session, m.alias, sender, via, text, msg_id)
    if not delivery.queue:
        delivery.release()
        print("sent to %s (delivered by a concurrent delivery)" % m.alias)
        return
    try:
        send_frame(socket_path_of(peer), delivery.payload(True))
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
                     session=target[2])
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
    # Nothing in the project answers. From inside a project a bare name never
    # reaches past it: another project's member is <project>/<alias>, and a
    # message to it is recorded in that project's log.
    scope = caller_scope()
    if scope is not None and not UUID_RE.match(a.target.lower()):
        die("no member '%s' in project %s — a member of another project is <project>/%s" % (
            a.target, scope.name, a.target), EXIT_UNKNOWN)
    # From no project, the one unrecorded route: a live session that is in no
    # project either (any session in a project answered above, as a member),
    # by its harness name. There is no log for it to be recorded in.
    peers = [r for r in live_name_holders(a.target)
             if not (isinstance(r.get("cwd"), str) and r["cwd"] and resolve_project(r["cwd"]))]
    if len(peers) == 1:
        try:
            send_frame(socket_path_of(peers[0]), text)
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
            try:
                _append(project, writer_id(os.environ.get("CLAUDE_CODE_SESSION_ID") or None),
                        [{"kind": "status", "session": m.session, "text": line}])
            except OSError as e:
                die("status of %s not recorded in %s's log: %s" % (m.alias, project.name, e), 1)
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


def list_row(m, label, width, state_width):
    rest = [charge_shown(m)] if charge_shown(m) else []
    if m.status:
        rest.append("· now: " + m.status)
    if m.by:
        rest.append("· by " + m.by)
    return ("  %-*s   %-*s  %s" % (width, label, state_width, state_column(m), "  ".join(rest))).rstrip()


def cmd_list(a):
    """One heading per project, its members newest first: alias (with #short
    when another member shares it), state word, in-charge line, `· now:` the
    status, `· by` the spawner."""
    projects, _fleet = view_projects(a.project, a.all)
    unfold = a.all or bool(a.state)
    sections, out, hidden = [], [], 0
    for p in projects:
        every = project_rows(p)
        rows = [m for m in every if not a.state or m.state == a.state]
        if a.json:
            out += [member_json(m, p) for m in rows]
            continue
        # The text view folds what only a `fill` (or the human) can act on,
        # as chart and tui do, unless --all or an explicit --state names the
        # word; the tail line says how many it folded. --json keeps every row.
        if not unfold:
            hidden += sum(1 for m in rows if m.state in HIDDEN)
            rows = [m for m in rows if m.state not in HIDDEN]
        if rows:
            sections.append((p, rows, every))
    if a.json:
        print(json.dumps(out, indent=2))
        return
    tail = ("+%d hidden (%s) — sminos list --all" % (hidden, ", ".join(HIDDEN))) if hidden else ""
    if not sections:
        print("(no members)")
    for p, rows, every in sections:
        labels = [member_label(m, every) for m in rows]
        width = min(max(len(x) for x in labels), 24)
        state_width = max(len(state_column(m)) for m in rows)
        print(p.name)
        for m, label in zip(rows, labels):
            print(list_row(m, label, width, state_width))
    if tail:
        print(tail)


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
    harness caches."""
    sys.modules.setdefault("sminos", sys.modules[__name__])
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    return importlib.import_module(name)


def chart_module():
    return sibling_module("sminos_chart")


def daemon_module():
    return sibling_module("sminos_daemon")


def bridge_module():
    return sibling_module("sminos_bridge")


def cmd_bridge(a):
    bridge_module().cmd_bridge(a)


def cmd_watch(a):
    bridge_module().cmd_watch(a)


def tick(project):
    """One daemon tick of one project (§8): integrate, reconcile, publish,
    deliver, push. {"integrated", "reconciled", "published", "delivered",
    "pushed"}, plus "to" (the aliases delivered to) and "error"."""
    return daemon_module().tick(project)


def cmd_daemon(a):
    if not a.op:
        die("usage: sminos daemon run [--interval N] | tick | install | status")
    daemon_module().cmd_daemon(a)


def hub_module():
    return sibling_module("sminos_hub")


def cmd_hub(a):
    hub_module().cmd_hub(a.words)


def cmd_chart(a):
    """The members as boxes, flat: one project's in a column, or — for every
    project — each project a rounded box with its members beside it; hidden
    members folded into '+N hidden' unless --all; then one summary line."""
    projects, boxed = view_projects(a.project, a.all)
    chart = chart_module()
    roots, meta = chart.snapshot(projects, a.all, boxed)
    lay = chart.layout(roots)
    width = a.width or (shutil.get_terminal_size((120, 40)).columns if sys.stdout.isatty() else 120)
    if lay["boxes"]:
        scr = chart.GridScreen(width, lay["height"])
        chart.paint_chart(scr, lay)
        print(scr.text())
    else:
        print("(no members to chart%s)" % ("" if a.all or not meta["hidden"] else " — all %d are hidden; sminos chart --all" % meta["hidden"]))
    bits = []
    if boxed:
        bits.append("%d projects" % meta["projects"])
    bits += ["%d members" % meta["members"], "%d live" % meta["live"]]
    if meta["hidden"]:
        hid = "%d hidden" % meta["hidden"]
        if meta["hidden_projects"]:
            hid += " in %d project(s) folded away" % meta["hidden_projects"]
        bits.append(hid + ("" if a.all else " (sminos chart%s --all)" % ((" " + a.project) if a.project else "")))
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

    say = sub.add_parser("say", add_help=False)
    say.add_argument("text")
    say.add_argument("--in", dest="in_", default="")
    say.set_defaults(fn=cmd_say)

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

    dv = sub.add_parser("derive", add_help=False)
    dv.add_argument("member", nargs="?", default="")
    dv.add_argument("--all", action="store_true")
    dv.set_defaults(fn=cmd_derive)

    rec = sub.add_parser("record", add_help=False)
    rec.set_defaults(fn=cmd_record)

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
    for op in ("tick", "install", "status", "uplink"):
        dsub.add_parser(op, add_help=False)
    dm.set_defaults(fn=cmd_daemon)

    # `hub` takes its words as `wake` does (no word is an option to argparse,
    # so its parse never fails): sminos_hub parses them and never prints one.
    # An enrollment code typed on the command line must not reach argparse's
    # error, which echoes the word it could not place.
    hb = sub.add_parser("hub", add_help=False, prefix_chars="\0")
    hb.add_argument("words", nargs="*")
    hb.set_defaults(fn=cmd_hub)

    br = sub.add_parser("bridge", add_help=False)
    br.add_argument("--session", default="")
    br.set_defaults(fn=cmd_bridge)

    wa = sub.add_parser("watch", add_help=False)
    wa.add_argument("member")
    wa.add_argument("--json", action="store_true")
    wa.set_defaults(fn=cmd_watch)

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

    ls = sub.add_parser("list", add_help=False)
    ls.add_argument("project", nargs="?", default="")
    ls.add_argument("--state", default="", choices=STATES)
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--all", action="store_true")
    ls.set_defaults(fn=cmd_list)

    ch = sub.add_parser("chart", add_help=False)
    ch.add_argument("project", nargs="?", default="")
    ch.add_argument("--all", action="store_true")
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
    if not getattr(a, "fn", None):
        if a.cmd == "seat":
            die("usage: sminos seat add <group> <alias> [--role R] [--brief B] [--session S]")
        if a.cmd == "project":
            die("usage: sminos project init [--name N] [--remote URL] [--hub] | show [DIR] | attach [DIR]")
        die("unknown command: %s (try: sminos help)" % argv[0])
    migrate()
    try:
        a.fn(a)
    except LogWriteFailed as e:
        die("%s completed, but %s" % (a.cmd, e), 1)


if __name__ == "__main__":
    main()
