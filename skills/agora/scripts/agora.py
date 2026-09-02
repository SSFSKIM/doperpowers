#!/usr/bin/env python3
"""agora — one fleet registry for Claude Code sessions.

The unit is the SEAT: a named position in a GROUP, with a role, that a Claude
Code session fills. A seat outlives the process that fills it: when the session
stops or dies the seat stays, with its role, brief, and history, and can be
filled again (`fill --resume` continues the same session id; `fill` spawns a
fresh one). Every background session spawned through agora is a seat, board
pipeline workers included, so `list` is the whole fleet and `view <group>` is
one group's organisation chart with live state on every node.

    agora spawn    <alias> <task> [--group G] [--parent P] [--role R] [--brief B]
                   [--cwd C] [--worktree W] [--model M] [--settings S] [--effort E]
                   [--addr A] [--wait]
    agora seat add <group> <alias> [--role R] [--brief B] [--parent P] [--addr A] [--session S]
    agora fill     <seat> <task> [--resume] [--model M] [--settings S] [--effort E] [--wait]
    agora wake     <seat> <msg> [--wait] [--from F]     # live: inbox socket; stopped: resume
    agora resume   <seat> <msg> [--wait]                 # process-level continuation (stops a live turn first)
                   A resumed background session keeps its SAVED options (name, permission
                   mode, model, settings, effort): --model/--settings/--effort are accepted
                   on resume for argv compatibility but ignored — use fill without --resume
                   to change them.
    agora send     <seat|addr> <msg> [--from F]         # live sessions only
    agora reply    <seat>                                # latest reply text
    agora sync     [<seat>] [--all]                      # reconcile status from the harness
    agora mark     <seat> <status> [note]                # orchestrator judgment state
    agora status   <seat> <one line>                     # the agent's own "now" line
    agora retire   <seat> [--purge]                      # stop; keep (or purge) the record
    agora remove   <seat>                                # stop and delete the record
    agora list     [group] [--status S] [--json]
    agora view     <group>                               # tree with role · live · now
    agora topology <group>                               # JSON: seats + edges
    agora chart    [group] [--all] [--width N]          # box organisation chart as text (fleet without a group)
    agora groups
    agora post     <group> [--from F] [--title T] [text...]   # stdin if no text
    agora board    <group> [-n N|--id I] [--json]
    agora attach   <seat>                                # claude attach <short>
    agora migrate  [--quiet]                             # (also runs implicitly)
    agora meta     get <seat> <field> | set <seat> <field> <value> [<field> <value>...]

A seat is addressed by `group/alias`, by a bare alias when it is unique, by its
seat id (or a prefix), or by the current session's short or full id.

Messaging between agents is the harness's native cross-session SendMessage
tool (a seat's addr is the target). agora's own `send`/`wake` exist for the
shell: they write a frame to the target session's inbox socket, which the
harness delivers as a peer message (an idle session starts a new turn).
`resume` is the process-level continuation the board pipeline relays through:
a fresh `claude --bg --resume` carrying the invoking environment.

State lives under $AGORA_HOME (default ~/.claude/agora; $DAEMON_HOME is the
older name of the same root and is honored). Records are <seat-id>.json at the
root — seat id = the first session's uuid — and the board pipeline reads and
writes them directly under the shared flock file .metalock. Group boards live
at groups/<group>/board.jsonl. Names are [A-Za-z0-9._-]{1,64}; `human` is the
reserved operator identity: never a seat, but may post to any board.

Exit codes: 0 ok, 1 harness failure, 2 usage, 4 unknown seat/group, target not
live, or a seat/name that is already taken.
"""

import argparse
import datetime
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid as uuidlib
from typing import NoReturn

# Fleet state is private to the agent fleet: everything this CLI creates is
# 700/600. All agents run as the same OS user, so nothing needs group/other.
os.umask(0o077)

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
LAUNCHER = os.path.join(SCRIPT_DIR, "agora")
PREAMBLE_PATH = os.path.join(SCRIPT_DIR, "..", "references", "spawn-preamble.md")

EXIT_USAGE = 2
EXIT_UNKNOWN = 4

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# A real session uuid, 8-4-4-4-12 hex — used to decide whether a --session value
# names a seat's on-disk identity (and transcript filename) or is junk.
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FILLED = ("busy", "idle", "blocked")
# A seat whose session can be re-filled fresh: no live turn is attached.
REFILLABLE = ("vacant", "stopped", "gone")
TERMINAL = ("done", "done-blocked", "blocked", "failed", "stopped", "error")
# Model-visible surfaces never carry a credential: the pipeline colonizes the
# record with run_bearer and friends, and a seat's JSON is read by agents.
SECRET_RE = re.compile(r"bearer|token|secret", re.I)


def public_seat(s):
    """A seat dict with the task body and any secret-shaped field removed —
    for every model-facing surface (list, list --json, view, topology)."""
    return {k: v for k, v in s.items() if k != "task" and not SECRET_RE.search(k)}


def home_dir():
    return os.path.expanduser("~")


def default_root():
    return os.path.join(home_dir(), ".claude", "agora")


def root():
    return os.environ.get("AGORA_HOME") or os.environ.get("DAEMON_HOME") or default_root()


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg, code=EXIT_USAGE) -> NoReturn:
    sys.stderr.write("agora: %s\n" % msg)
    sys.exit(code)


def warn(msg):
    sys.stderr.write("agora: warning: %s\n" % msg)


def valid_name(n):
    # '.' and '..' are path segments, not names: they would resolve to the
    # registry root itself. Names that merely contain dots (v1.2) are fine.
    return bool(n) and n not in (".", "..") and bool(NAME_RE.match(n))


def poll_interval():
    return float(os.environ.get("AGORA_POLL_INTERVAL", "2"))


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


def meta_set(seat_id, fields, remove=(), bump=True, create=True):
    """Merge fields into a seat record (creating it if absent, unless create=False).

    The read-modify-write is serialized across processes with an advisory flock
    on the shared lock file: the board pipeline's own writers take the same
    lock, so concurrent stamps never clobber each other's fields.

    `gen` is the record's lifecycle generation: every lifecycle write (spawn,
    fill, resume, wake, retire, mark, seat add, sync's own finalize) bumps it,
    so a finalizer or sync that took its snapshot before, say, a retire can see
    the record moved on and stand down. The agent's own `now` line and raw
    `meta set` are NOT lifecycle writes (bump=False): an agent updating its
    status mid-turn must not make the turn's watcher refuse to record the reply.
    create=False (status / mark / meta set) refuses to resurrect a record that
    a concurrent remove just deleted. Returns True iff it wrote.
    """
    path = meta_path(seat_id)
    os.makedirs(root(), exist_ok=True)
    with open(os.path.join(root(), ".metalock"), "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
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
    addr/role, so every read site goes through here.
    """
    with open(path) as f:
        m = json.load(f)
    seat_id = os.path.basename(path)[:-5]
    m["uuid"] = str(m.get("uuid") or seat_id)
    m["seat_id"] = seat_id
    name = str(m.get("name") or m.get("alias") or "")
    m["name"] = name
    m["alias"] = str(m.get("alias") or name)
    m["addr"] = str(m.get("addr") or m["alias"])
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


def find_seat(q):
    """Resolve a query to a seat WITHOUT printing or exiting.

    Returns ("ok", seat) | ("none", None) | ("ambiguous", [seats]). Order:
    `group/alias`, seat id (or prefix), current turn's short id or session id
    (or prefix), then a bare alias when exactly one seat has it.
    """
    if not q:
        return "none", None
    all_seats = seats()
    if "/" in q:
        g, a = q.split("/", 1)
        hits = [s for s in all_seats if s["group"] == g and s["alias"] == a]
        return ("ok", hits[0]) if len(hits) == 1 else ("none", None)
    hits = [s for s in all_seats if s["seat_id"] == q or s["seat_id"].startswith(q)]
    if not hits:
        hits = [s for s in all_seats
                if (s["short"] and (s["short"] == q or s["short"].startswith(q)))
                or (s["current"] and (s["current"] == q or s["current"].startswith(q)))]
    if not hits:
        hits = [s for s in all_seats if s["alias"] == q]
    if len(hits) == 1:
        return "ok", hits[0]
    if not hits:
        return "none", None
    return "ambiguous", hits


def resolve_seat(q):
    kind, res = find_seat(q)
    if kind == "ok":
        return res
    if kind == "ambiguous":
        die("ambiguous seat '%s' matches: %s" % (
            q, ", ".join("%s/%s [%s]" % (s["group"], s["alias"], s["seat_id"][:8]) for s in res)), EXIT_UNKNOWN)
    die("no seat matching '%s'" % q, EXIT_UNKNOWN)


def group_dir(g):
    return os.path.join(root(), "groups", g)


def group_exists(g):
    return os.path.isdir(group_dir(g)) or any(True for _ in seats(g))


def derive_group(cwd):
    """Default group for a seat spawned without --group: the OWNING repository.

    Board-pipeline workers spawn in a linked worktree (<repo>/.claude/worktrees/
    <name>), whose toplevel is the worktree dir — grouping on that would file
    every worker under its own name. The common git dir points at the main
    checkout's .git, so its parent is the owning repo; all a repo's workers
    share one group. Non-git cwd falls back to the directory basename.
    """
    name = ""
    if cwd and os.path.isdir(cwd):
        try:
            common = subprocess.run(["git", "-C", cwd, "rev-parse", "--git-common-dir"],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            common = ""
        if common:
            if not os.path.isabs(common):
                common = os.path.join(cwd, common)
            name = os.path.basename(os.path.dirname(os.path.abspath(common)))
        else:
            name = os.path.basename(os.path.normpath(cwd))
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name)[:64]
    if not valid_name(name):
        name = "fleet"
    return name


def group_for_record(m):
    """The group of a legacy record: its own agora_group if present (the daemon
    dimension already knew it), else derived from cwd."""
    return str(m.get("agora_group") or "") or derive_group(str(m.get("cwd") or ""))


def lock_names(names, label, blocking=False):
    """One lifecycle change per harness NAME at a time: spawn / fill / seat add /
    resume / wake / retire / remove / sync hold these flocks from their
    availability check through the record commit (through process start, for
    resume). The key is the harness address (addr, default alias) — never
    group__alias: an addr is the machine-wide SendMessage name, so two seats
    that share an explicit --addr, or a same-alias spawn in another group, must
    serialize or two live sessions would answer to one address. Names are
    locked in the given order (alias first, then addr) so no two callers can
    deadlock. The kernel releases every lock the moment the holder exits."""
    d = os.path.join(root(), "locks")
    os.makedirs(d, exist_ok=True)
    locks = []
    # sha1 of the exact name: no lossy sanitization can alias two names onto one
    # lock file. Sorted acquisition: every caller takes its set in the same
    # order, so an alias/addr pair can never deadlock against another caller.
    for nm in sorted(dict.fromkeys(n for n in names if n)):
        lf = open(os.path.join(d, "name__%s.lock" % hashlib.sha1(nm.encode()).hexdigest()), "a+")
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError:
            for held in locks:
                held.close()
            lf.close()
            die("'%s' (%s) is being changed by another agora process — retry shortly" % (nm, label), EXIT_UNKNOWN)
        locks.append(lf)
    return locks


def lock_seat(s, blocking=False):
    return lock_names([s["alias"], s["addr"]], "%s/%s" % (s["group"], s["alias"]), blocking)


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


def refresh_caches():
    """Forget everything cached from the harness — the agents rows, the peer
    registry, and process start times — so a long-lived reader (the chart TUI)
    sees the fleet as it is now rather than as it was at launch."""
    global _AGENTS_LOADED, _PEERS
    _AGENTS_LOADED = False
    _PEERS = None
    _PSTART.clear()
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


def peer_live(rec):
    """A peer record is live only if its pid is alive, the pid is the SAME
    process the record described (its start time matches the record's
    `procStart` — a recycled pid fails this), AND its inbox socket accepts a
    connection (a dead session can leave its socket FILE behind; only a
    successful connect proves a listener). When either start time cannot be
    parsed, the start-time check is skipped and the pid+socket rule decides."""
    if not pid_alive(rec.get("pid")):
        return False
    recorded, live = _parse_lstart(rec.get("procStart")), _parse_lstart(proc_start(rec.get("pid")))
    if recorded and live and recorded != live:
        return False
    return socket_ok(socket_path_of(rec))


def peer_for_session(session_id):
    if not session_id:
        return None
    for rec in peer_records():
        if rec.get("sessionId") == session_id and peer_live(rec):
            return rec
    return None


def live_name_holders(name):
    return [r for r in peer_records() if r.get("name") == name and peer_live(r)]


def refuse_live_name(alias, addr, allow_session=""):
    """A seat's alias is its session's harness name and SendMessage address,
    and those names are machine-wide: a live session already answering to it
    would make every send ambiguous. Refuse before any side effect — unless the
    caller is registering that very session as the seat."""
    for nm in dict.fromkeys([alias, addr]):
        for r in live_name_holders(nm):
            if allow_session and r.get("sessionId") == allow_session:
                continue
            die("a live session already answers to '%s' (pid %s, session %s) — SendMessage names are "
                "machine-wide; pick another alias, or pass --session %s to register that session as this seat"
                % (nm, r.get("pid"), str(r.get("sessionId") or "")[:8], str(r.get("sessionId") or "<id>")),
                EXIT_UNKNOWN)


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
    turn. Then the recorded short (the latest launch agora knows), then any
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


def live_state(seat):
    """Harness-derived liveness: busy, idle, blocked, stopped, gone, vacant —
    or unknown when the harness itself could not be asked."""
    cur = seat.get("current") or ""
    if not cur:
        return "vacant"
    if not harness_ok():
        return "unknown"
    row = harness_row(seat)
    peer = peer_for_session(cur)
    if row:
        st = normalize_state(row)
        if st == "working":
            return "busy"
        if st == "blocked":
            return "blocked"
        if st in ("done", "done-blocked"):
            return "idle" if peer else "stopped"
        if st in ("stopped", "failed", "error"):
            return "stopped"
        return "idle" if peer else "stopped"
    if peer:
        return "busy" if peer.get("status") == "busy" else "idle"
    return "gone"


def host_name():
    return os.environ.get("DAEMON_HOST") or socket.gethostname()


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


def identity_local(host, boot):
    """True iff a record's recorded host/boot identity belongs to this boot.
    Empty values preserve legacy local behavior."""
    if host and host != host_name():
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
    """After `claude stop`, wait (bounded by AGORA_STOP_TIMEOUT, default 30s)
    until the old turn's harness row is gone or no longer running AND no live
    peer socket answers for the session. Resuming while the old process still
    runs makes the harness start a copy; a stop that did not take is refused
    loudly rather than papered over. True iff the turn is confirmed down."""
    deadline = time.time() + float(os.environ.get("AGORA_STOP_TIMEOUT", "30"))
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
        max_iter = int(os.environ.get("AGORA_UUID_POLL") or os.environ.get("DAEMON_UUID_POLL") or "30")
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
    so glob for the transcript by its unique session id instead."""
    if not session_id:
        return ""
    hits = glob.glob(os.path.join(home_dir(), ".claude", "projects", "**", session_id + ".jsonl"),
                     recursive=True)
    return hits[0] if hits else ""


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
                'agora wake %s "<answer>"]\n' % seat_ref) + "\n".join(pending)
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
                "instruction via agora wake (the pending call is interrupted), or 'claude attach' "
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
    without any agora verb in it: nothing marks the record working, nothing
    finalizes it, and the recorded reply keeps describing the PREVIOUS turn.
    The transcript's mtime is the evidence that a turn happened anyway."""
    tx = transcript_path(turn_id)
    if not tx:
        return False
    return _mtime(tx) > _mtime(reply_path(seat_id))


# ----------------------------------------------------------------- migration


def convert_v2_nodes(r):
    """Convert v2 groups/<g>/nodes/*.json into seat records. Removes only the
    node files it actually converts and rmdir's the nodes/ dir only when it is
    empty (never rmtree — an unreadable node file must survive for a human)."""
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
            # time (which would multiply the seat on every retry).
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
            if existing is not None:
                meta_set(seat_id, {"group": g, "alias": alias, "parent": str(n.get("parent") or ""),
                                   "addr": str(n.get("addr") or alias), "brief": str(n.get("desc") or "")})
            else:
                meta_set(seat_id, {
                    "uuid": seat_id, "current": sess, "short": "", "name": alias, "alias": alias,
                    "group": g, "parent": str(n.get("parent") or ""),
                    "addr": str(n.get("addr") or alias), "role": "", "brief": str(n.get("desc") or ""),
                    "task": "", "now": "", "note": "", "cwd": str(n.get("cwd") or ""), "worktree": "",
                    "model": "", "settings": "", "effort": "", "status": "retired",
                    "host": "", "boot_id": "", "created": str(n.get("joined") or now()),
                    "updated": now(), "turns": "0", "preamble": "1"})
            os.unlink(nf)
            converted += 1
        try:
            os.rmdir(nodes_dir)  # only if now empty
        except OSError:
            pass
    return converted


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
    os.unlink(src)
    return True


def merge_asides(r):
    """Finish an interrupted cutover. An `<root>.v2-*` aside is a former default
    root that was set aside so the daemon root could take its place; its groups/
    are merged back and it is removed when empty. Runs on EVERY migrate, so a
    crash between the rename and the merge self-heals on the next command. A
    colliding board.jsonl is appended into the root's (ids renumbered); any
    other collision is left in place and named on stderr on every run until a
    human resolves it. Returns (asides_removed, warnings)."""
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
        if os.path.isdir(aside) and not os.listdir(aside):
            os.rmdir(aside)
            merged += 1
        elif os.path.isdir(aside):
            for entry in os.listdir(aside):
                if entry != "groups":
                    warnings.append(os.path.join(aside, entry))
    return merged, warnings


def migrate(quiet=False):
    """Bring a pre-seat state root up to date. Idempotent; runs before every verb.

    The whole cutover is serialized by an exclusive flock on
    ~/.claude/.agora-migrate.lock, so two agora processes starting at once can't
    both try to rename the old root. Steps:

    1. Old root: when the default root is in use and ~/.claude/orchestrating-daemons
       is a real directory, the old root is renamed INTO place as one atomic
       step (any existing ~/.claude/agora is set aside first), and a symlink is
       left at the old path so anything still holding it keeps resolving. The
       set-aside root's groups/ are merged back by merge_asides, which also runs
       on every later call — so a crash mid-cutover self-heals.
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
       0600 (the old substrate left 0755/0644); the legacy path is a symlink to
       the root whenever it is missing (a crash after the rename must not leave
       legacy consumers without a path); an aside left over from an interrupted
       cutover is merged (colliding boards appended with renumbered ids) and
       anything it still holds is named on stderr on every run.
    """
    r = root()
    did = []
    lockdir = os.path.join(home_dir(), ".claude")
    os.makedirs(lockdir, exist_ok=True)
    with open(os.path.join(lockdir, ".agora-migrate.lock"), "a") as mlf:
        fcntl.flock(mlf, fcntl.LOCK_EX)
        try:
            old = os.path.join(home_dir(), ".claude", "orchestrating-daemons")
            if r == default_root() and os.path.isdir(old) and not os.path.islink(old):
                if os.path.lexists(r):
                    os.rename(r, r + ".v2-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
                os.rename(old, r)
                did.append("renamed %s -> %s" % (old, r))
            if r == default_root() and os.path.isdir(r) and not os.path.lexists(old):
                os.symlink(r, old)
                did.append("linked %s -> %s" % (old, r))
            merged, leftovers = merge_asides(r)
            if merged:
                did.append("merged an interrupted v2 aside back into the root")
            for lp in leftovers:
                sys.stderr.write("agora: warning: unmerged aside entry left in place: %s\n" % lp)
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
                    meta_set(sid, fields, bump=False)
            n = convert_v2_nodes(r)
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
                    meta_set(sid, fields, bump=False, create=False)
                    deduped += 1
            if stamped or retired or deduped:
                did.append("stamped group on %d record(s), retired %d legacy codex record(s), renamed %d duplicate alias(es)" % (
                    stamped, retired, deduped))
        finally:
            fcntl.flock(mlf, fcntl.LOCK_UN)
    if did and not quiet:
        sys.stderr.write("agora: migrated: %s\n" % "; ".join(did))
    return did


# --------------------------------------------------------------- spawn / fill


def render_preamble(group, alias, parent):
    try:
        with open(PREAMBLE_PATH) as f:
            t = f.read()
    except OSError:
        die("preamble template missing: %s" % PREAMBLE_PATH, 1)
    return (t.replace("{{GROUP}}", group).replace("{{ALIAS}}", alias)
             .replace("{{PARENT}}", parent or "none").replace("{{AGORA_CLI}}", LAUNCHER))


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
    (also conditionally) and the reply is readable later with `agora reply`."""
    uuid, state, _cwd, finished = poll_until_done(short, watcher_iterations())
    if not finished:
        meta_set_if(seat_id, {"status": "working", "updated": now()}, guard)
        sys.stderr.write("agora: watcher expired; turn %s of %s is still running (status=working). "
                         "Read it later with: agora reply %s\n" % (short, alias, alias))
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


def spawn_fresh(seat_id, alias, addr, group, parent, role, brief, task, cwd, worktree,
                model, settings, effort, preamble_flag, wait, locks, verb):
    """Launch a fresh background session for a seat and register it.

    seat_id None → a brand-new seat: a provisional record exists during the
    first turn (so the agent can post / be looked up), then is promoted to the
    first session's uuid as the seat id. seat_id set → an in-place re-fill: the
    record keeps its id, `note`/`created`, and every pipeline-owned field; the
    launch + definition fields are overwritten, `attempts` is bumped and the
    previous occupant is appended to `history` (last 10) for the pipeline's
    outage-streak logic. The session launches under -n <addr> so the seat's
    advertised address is its live SendMessage name. The banner's bracket is
    always `[<short> / <RECORD FILENAME>]` — the pipeline parses that value and
    board-bind matches it against filenames, so on a re-fill it is the seat id,
    never the new session's uuid. Returns nothing (prints; may exit)."""
    prev = reload_seat(seat_id) if seat_id else None
    prev_event_log = str(prev.get("event_log") or "") if prev and prev["engine"] == "codex" else ""
    preamble = render_preamble(group, alias, parent or "") if preamble_flag else ""
    task_text = compose_task(task, brief or "", preamble)
    short, banner = run_claude_bg(claude_args(addr, model, settings, effort, worktree) + [task_text], cwd, settings)
    if not short:
        sys.stderr.write("agora: %s failed — could not parse background id from:\n%s\n" % (verb, banner))
        sys.exit(1)
    launch = {
        "current": "", "short": short, "name": addr, "alias": alias, "group": group,
        "parent": parent or "", "addr": addr, "role": role or "", "brief": brief or "",
        "task": task_text, "cwd": cwd, "worktree": worktree or "", "model": model or "",
        "settings": settings, "effort": effort, "status": "working", "host": host_name(),
        "boot_id": boot_id(), "updated": now(), "turns": "1", "preamble": "1" if preamble_flag else "",
    }
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
        meta_set(rec_id, {**launch, "now": "", "attempts": (prev["attempts"] if prev else 0) + 1,
                          "history": history[-10:]},
                 remove=("pending_short", "engine", "pid", "event_log", "run_id", "run_bearer", "fence",
                         "bind_confirmed", "nonce", "run_ended_at", "ticket", "board", "closure_package",
                         "retired_from", "relayed_comment", "sweep_recoveries"))
    polled = poll_uuid(short)
    if not polled or not UUID_RE.match(polled[0]):
        meta_set(rec_id, {"status": "error", "pending_short": short, "updated": now()})
        sys.stderr.write("agora: %s: session %s produced no usable session uuid; record %s kept "
                         "(status=error, pending_short)\n" % (verb, short, rec_id[:8]))
        sys.exit(1)
    uuid, state, runcwd = polled
    if seat_id is None:
        # Promote the provisional record to the first session's uuid — the
        # pipeline resolves seats by that filename prefix. The rename is atomic;
        # do it under .metalock so it can't race a concurrent meta_set on either
        # path, and merge ONLY the fields we now know — never replay empties over
        # a `now`/`note` a first-turn `agora status` may have written to prov.
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
        if prev_event_log:
            # The launch succeeded and the record is promoted: only now is the
            # predecessor's codex scratch safe to drop.
            purge_codex_runs(prev_event_log)
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
    print("seat %s: %s/%s  [%s / %s]  status=%s%s  (reply: agora reply %s)" % (
        verb, group, alias, short, rec_id, status, wt, short))
    if wait:
        print_reply_block(rec_id)


def cmd_spawn(a):
    alias = a.alias
    if not valid_name(alias):
        die("bad alias: %s" % alias)
    if alias == "human":
        die("the alias 'human' is reserved for the operator")
    if a.parent and not valid_name(a.parent):
        die("bad parent alias: %s" % a.parent)
    cwd = cwd_or_die(a.cwd, "spawn")
    explicit_group = a.group is not None
    group = a.group if explicit_group else derive_group(cwd)
    if not valid_name(group):
        die("bad group name: %s" % group)
    label = "%s/%s" % (group, alias)
    names = [alias, a.addr or ""]
    locks = lock_names(names, label)
    # Read under the lock: whether the seat is filled/refillable is only true as
    # of now, not as of any earlier read. If the seat's recorded addr is a name
    # we did not lock, release and re-take the whole (sorted) set, then re-read.
    addr = a.addr or alias
    existing = None
    for _ in range(3):
        existing = next((s for s in seats(group) if s["alias"] == alias), None)
        addr = a.addr or (existing["addr"] if existing else alias)
        if addr in names or not existing:
            break
        unlock(locks)
        names = [alias, a.addr or "", addr]
        locks = lock_names(names, label)
    if existing:
        if peer_for_session(existing["current"]):
            die("seat %s/%s: the previous occupant (session %s) still answers — use agora wake/resume, or "
                "stop it first" % (group, alias, existing["current"][:8]), EXIT_UNKNOWN)
        live = live_state(existing)
        if live in FILLED or live == "unknown":
            die("seat %s/%s is filled (live: %s) — message it with agora send/wake" % (group, alias, live), EXIT_UNKNOWN)
        if existing["engine"] == "codex" and existing["status"] in ("working", "blocked"):
            die("seat %s/%s is a legacy codex-CLI worker still marked %s — retire it before re-filling" % (
                group, alias, existing["status"]), EXIT_UNKNOWN)
        # vacant / stopped / gone / retired → re-fill this very seat, keeping its
        # id and the seat-describing pipeline fields. The board pipeline's
        # retire-then-respawn of a deterministic alias (review-pr-<n>) lands
        # here instead of erroring.
    refuse_live_name(alias, addr)  # the previous occupant is NOT an allowed holder
    settings = env_default(a.settings, "DAEMON_CLAUDE_SETTINGS")
    effort = env_default(a.effort, "DAEMON_CLAUDE_EFFORT")
    if existing:
        # Definition fields change only when EXPLICITLY given (argparse default
        # None keeps the seat's own); task/model/settings/effort/cwd/worktree are
        # per-fill and always come from this call.
        parent = a.parent if a.parent is not None else existing["parent"]
        role = a.role if a.role is not None else existing["role"]
        brief = a.brief if a.brief is not None else existing["brief"]
        preamble_flag = explicit_group or bool(existing["preamble"])
    else:
        parent, role, brief, preamble_flag = a.parent or "", a.role or "", a.brief or "", explicit_group
    spawn_fresh(existing["seat_id"] if existing else None, alias, addr, group, parent, role, brief,
                a.task, cwd, a.worktree or "", a.model or "", settings, effort, preamble_flag, a.wait, locks, "spawned")


def cmd_seat_add(a):
    if not valid_name(a.group):
        die("bad group name: %s" % a.group)
    if not valid_name(a.alias):
        die("bad alias: %s" % a.alias)
    if a.alias == "human":
        die("the alias 'human' is reserved for the operator")
    if a.parent and not valid_name(a.parent):
        die("bad parent alias: %s" % a.parent)
    session = a.session or ""
    if session and not UUID_RE.match(session):
        die("--session must be a session uuid (8-4-4-4-12 hex): %s" % session)
    label = "%s/%s" % (a.group, a.alias)
    names = [a.alias, a.addr or ""]
    locks = lock_names(names, label)
    existing = []
    addr = a.addr or a.alias
    for _ in range(3):
        existing = [s for s in seats(a.group) if s["alias"] == a.alias]
        addr = a.addr or (existing[0]["addr"] if existing else a.alias)
        if addr in names or not existing:
            break
        unlock(locks)  # re-take the whole sorted set including the recorded addr
        names = [a.alias, a.addr or "", addr]
        locks = lock_names(names, label)
    if existing and ((a.addr and a.addr != existing[0]["addr"])
                     or (session and session != existing[0]["current"])):
        # Repointing a seat is how a record forgets which process it describes.
        # If the current occupant is still live under the OLD address, that
        # process would keep running with nothing in the fleet naming it —
        # unstoppable by retire/remove and invisible to every view.
        peer = peer_for_session(existing[0]["current"])
        if peer:
            unlock(locks)
            die("seat %s/%s still holds a live session (%s, pid %s) at addr '%s' — repointing it would strand "
                "that process outside the fleet; retire or remove the seat first"
                % (a.group, a.alias, existing[0]["current"][:8], peer.get("pid"), existing[0]["addr"]),
                EXIT_UNKNOWN)
    refuse_live_name(a.alias, addr, allow_session=session or (existing[0]["current"] if existing else ""))
    # A registered session's short is whatever the harness shows for it right
    # now (a `seat add --session` seat was never spawned by agora, so nothing
    # else records it); absent a row it is cleared, never left stale.
    row = agent_row(session_id=session) if session else None
    short = str((row or {}).get("id") or "")
    if existing:
        s = existing[0]
        seat_id = s["seat_id"]
        fields = {"parent": a.parent if a.parent is not None else s["parent"],
                  "addr": addr, "role": a.role if a.role is not None else s["role"],
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
            "group": a.group, "parent": a.parent or "", "addr": addr, "role": a.role or "",
            "brief": a.brief or "", "task": "", "now": "", "note": "", "cwd": os.getcwd(), "worktree": "",
            "model": "", "settings": "", "effort": "", "status": "idle" if session else "vacant",
            "host": host_name() if session else "", "boot_id": boot_id() if session else "",
            "created": now(), "updated": now(), "turns": "0", "preamble": "1", "attempts": 1, "history": []})
    os.makedirs(os.path.join(group_dir(a.group), "locks"), exist_ok=True)
    unlock(locks)
    print("seat %s/%s %s (parent: %s, addr: %s%s)" % (
        a.group, a.alias, "updated" if existing else "added", a.parent or "none", addr,
        (", session: " + session) if session else ", vacant"))


def cmd_join(a):
    # v2 argument order, kept because long-lived sessions still carry v2 preambles.
    a.brief = a.desc
    cmd_seat_add(a)


def refuse_codex(s):
    if s["engine"] == "codex":
        die("seat %s/%s is a legacy codex-CLI worker; its resume path was retired — "
            "retire or remove the seat" % (s["group"], s["alias"]), EXIT_UNKNOWN)


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
    live = live_state(s)
    if live in FILLED or live == "unknown":
        die("seat %s/%s is filled (live: %s) — use agora wake or agora send" % (s["group"], s["alias"], live), EXIT_UNKNOWN)
    if a.resume:
        if not s["current"]:
            die("seat %s/%s has no session to resume — fill it fresh (without --resume)" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        refuse_live_name(s["alias"], s["addr"], allow_session=s["current"])  # resume continues that very session
        warn_resume_flags(a)
        resume_session(s, a.task, a.wait, locks, verb="filled")
        return
    if peer_for_session(s["current"]):
        die("seat %s/%s: the previous occupant (session %s) still answers — use agora wake/resume, or stop it "
            "first" % (s["group"], s["alias"], s["current"][:8]), EXIT_UNKNOWN)
    refuse_live_name(s["alias"], s["addr"])  # a fresh fill: the previous occupant is NOT an allowed holder
    settings = a.settings if a.settings is not None else (s["settings"] or os.environ.get("DAEMON_CLAUDE_SETTINGS", ""))
    effort = a.effort if a.effort is not None else (s["effort"] or os.environ.get("DAEMON_CLAUDE_EFFORT", ""))
    model = a.model if a.model is not None else s["model"]
    # The seat's cwd is already the worktree path when it had one, so no
    # --worktree on a re-fill: the fresh session runs where the seat lives.
    cwd = cwd_or_die(s["cwd"], "fill")
    spawn_fresh(s["seat_id"], s["alias"], s["addr"], s["group"], s["parent"], s["role"], s["brief"],
                a.task, cwd, "", model, settings, effort, bool(s["preamble"]), a.wait, locks, "filled")


# ------------------------------------------------------- resume / wake / send


def warn_resume_flags(a):
    if any(getattr(a, k, None) is not None for k in ("model", "settings", "effort")):
        sys.stderr.write("agora: a resumed background session keeps its saved options; "
                         "--model/--settings/--effort ignored (use fill without --resume to change them)\n")


def resume_session(s, msg, wait, locks=None, verb="resumed"):
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
    """
    refuse_codex(s)
    if locks is None:
        locks = lock_seat(s)
        fresh = reload_seat(s["seat_id"])
        if fresh is None:
            unlock(locks)
            die("seat %s/%s vanished before the resume could start" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        s = fresh
        refuse_codex(s)
    if not s["current"]:
        die("seat %s/%s is vacant — fill it with: agora fill %s/%s \"<task>\"" % (
            s["group"], s["alias"], s["group"], s["alias"]), EXIT_UNKNOWN)
    cwd = cwd_or_die(s["cwd"], "resume of %s/%s" % (s["group"], s["alias"]))  # before any side effect
    lock_path = os.path.join(root(), s["seat_id"] + ".resume.lock")
    lf = open(lock_path, "a+")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lf.seek(0)
        holder = lf.read().strip()
        die("a wake/resume of %s/%s is already in flight%s — not starting a twin" % (
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
    elif not row and peer_for_session(cur) and s["short"] and identity_local(s["host"], s["boot_id"]):
        stop_short = s["short"]
    if stop_short:
        if not claude_stop(stop_short):
            die("claude stop %s failed for %s/%s — not resuming over a turn that may still be running" % (
                stop_short, s["group"], s["alias"]), 1)
        if not wait_stopped(s, stop_short, cur):
            die("the current turn of %s/%s (%s) is still running %ss after claude stop — not launching a "
                "resume (it would start a copy)" % (s["group"], s["alias"], stop_short,
                                                    os.environ.get("AGORA_STOP_TIMEOUT", "30")), 1)
    prev_status = s["status"]
    short, banner = run_claude_bg(["--bg", "--resume", cur, msg], cwd, s["settings"])
    if not short:
        meta_set(s["seat_id"], {"status": "error", "updated": now()})
        sys.stderr.write("agora: resume failed — did not launch or produced no background id:\n%s\n" % banner)
        sys.exit(1)

    def copy_started(copy_id):
        claude_stop(short)
        meta_set(s["seat_id"], {"status": prev_status, "updated": now()})
        die("resume of %s/%s started a COPY (%s) — the session %s was still running or the harness refused "
            "to continue it; the copy was stopped and the record left untouched. Use agora wake/send for a "
            "live seat." % (s["group"], s["alias"], copy_id[:8], cur[:8]), 1)

    m = re.search(r"started a copy as ([0-9a-f]+)", banner)
    if m:
        copy_started(m.group(1))
    polled = poll_uuid(short)
    if not polled:
        meta_set(s["seat_id"], {"status": "error", "pending_short": short, "updated": now()})
        sys.stderr.write("agora: resume: session %s produced no usable session uuid; kept previous "
                         "current (recover via pending_short)\n" % short)
        sys.exit(1)
    uuid, state, _cwd = polled
    if uuid != cur:
        copy_started(uuid)
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
    print("%s %s/%s  [%s / %s]  via --bg --resume  status=%s  turns=%d" % (
        verb, s["group"], s["alias"], short, s["seat_id"], status, turns))
    if wait:
        print_reply_block(s["seat_id"])


def cmd_resume(a):
    s = resolve_seat(a.seat)
    warn_resume_flags(a)
    resume_session(s, a.msg, a.wait)


def default_from(explicit):
    """The sender identity for send/wake/post.

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
    deadline = time.time() + float(os.environ.get("AGORA_ACK_TIMEOUT", "120"))
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
        sys.stderr.write("agora: no evidence that %s/%s received the message within the ack window "
                         "(no transcript marker%s) — not waiting for a reply\n" % (
                             s["group"], s["alias"], "" if was_idle else ", and it was already busy at send time"))
        sys.exit(1)
    agents_refresh()
    row = harness_row(s)
    short = (row or {}).get("id") or s["short"]
    if not short:
        return "idle"
    return finish_turn(s["seat_id"], short, s["alias"], cur, guard)


def cmd_wake(a):
    s0 = resolve_seat(a.seat)
    refuse_codex(s0)
    # The lifecycle lock covers target selection, the socket delivery, and the
    # status write, so a concurrent fill/resume/retire cannot slip between them.
    locks = lock_seat(s0)
    s = reload_seat(s0["seat_id"])
    if s is None:
        unlock(locks)
        die("seat %s/%s vanished before the wake could start" % (s0["group"], s0["alias"]), EXIT_UNKNOWN)
    refuse_codex(s)
    if not s["current"]:
        die("seat %s/%s is vacant — fill it with: agora fill %s/%s \"<task>\"" % (
            s["group"], s["alias"], s["group"], s["alias"]), EXIT_UNKNOWN)
    frm = default_from(a.frm)
    msg_id = uuidlib.uuid4().hex[:8]
    text = "[agora wake from %s id=%s]\n%s" % (frm, msg_id, a.msg)
    peer = peer_for_session(s["current"])  # live = pid alive AND socket answers
    if peer:
        sock = socket_path_of(peer)
        row = harness_row(s)
        # Idle-at-send: from the harness row when there is one; with no row, from
        # the peer record's own status — never from normalising an empty state.
        was_idle = (normalize_state(row) not in ("working", "blocked")) if row else (peer.get("status") != "busy")
        try:
            send_frame(sock, text)
        except SendFailed as e:
            if e.phase == "before":
                # Nothing reached the peer (the session exited between the
                # liveness check and the write): fall through to the resume path.
                warn("inbox socket delivery to %s/%s failed before the frame was written (%s); resuming instead" % (
                    s["group"], s["alias"], e))
                resume_session(s, text, a.wait, locks, verb="woke")
                return
            unlock(locks)
            die("delivery to %s/%s is UNCERTAIN — the frame was written but the close-out failed (%s). Not "
                "resuming and not re-sending id=%s; check the seat with agora reply/attach before retrying." % (
                    s["group"], s["alias"], e, msg_id), 1)
        wrote = meta_set_if(s["seat_id"], {"status": "working", "updated": now()}, same_gen(s["gen"]))
        # The watcher's guard: the generation right after our write, read while
        # the lifecycle lock is still held.
        guard = same_gen(current_gen(s["seat_id"]))
        unlock(locks)
        if not wrote:
            warn("record of %s/%s changed during delivery; status left as is" % (s["group"], s["alias"]))
        status = "working"
        if a.wait:
            status = wait_socket_turn(s, msg_id, was_idle, guard)
        print("woke %s/%s  [%s / %s]  via inbox socket  status=%s" % (
            s["group"], s["alias"], s["short"] or "-", s["seat_id"], status))
        if a.wait:
            print_reply_block(s["seat_id"])
        return
    resume_session(s, text, a.wait, locks, verb="woke")


def cmd_send(a):
    frm = default_from(a.frm)
    text = "[agora message from %s]\n%s" % (frm, a.msg)
    kind, res = find_seat(a.target)
    if kind == "ambiguous":
        # A genuine seat match that is ambiguous must NOT silently fall through
        # to a raw name lookup — that would hide the ambiguity.
        die("ambiguous seat '%s' matches: %s" % (
            a.target, ", ".join("%s/%s" % (s["group"], s["alias"]) for s in res)), EXIT_UNKNOWN)
    if kind == "ok":
        s = res
        peer = peer_for_session(s["current"]) if s["current"] else None
        sock = socket_path_of(peer) if peer else ""
        if peer and socket_ok(sock):
            try:
                send_frame(sock, text)
            except SendFailed as e:
                if e.phase == "after":
                    die("delivery to %s/%s is UNCERTAIN — the frame was written but the close-out failed (%s); "
                        "do not blindly re-send" % (s["group"], s["alias"], e), 1)
                die("%s/%s went away mid-send (%s) — use: agora wake %s/%s \"<msg>\"" % (
                    s["group"], s["alias"], e, s["group"], s["alias"]), EXIT_UNKNOWN)
            print("sent to %s/%s (%s)" % (s["group"], s["alias"], peer.get("name") or s["addr"]))
            return
        die("%s/%s is not live (%s) — use: agora wake %s/%s \"<msg>\"" % (
            s["group"], s["alias"], live_state(s), s["group"], s["alias"]), EXIT_UNKNOWN)
    # Only when NO seat matched: fall back to a raw live harness-session name.
    peers = live_name_holders(a.target)  # live already means the socket answers
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
    die("no seat or live session matching '%s'" % a.target, EXIT_UNKNOWN)


# ------------------------------------------------ reply / sync / mark / status


def cmd_reply(a):
    s = resolve_seat(a.seat)
    print("%s/%s  [%s]  status=%s  turns=%s  live=%s" % (
        s["group"], s["alias"], s["seat_id"], s["status"], s["turns"], live_state(s)))
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
        # finished a turn no agora verb ever recorded. A transcript newer than
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
    shows a running turn was woken natively (SendMessage, no agora write):
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
        if s["status"] == "idle":
            # An idle seat the harness shows as running NOW was woken natively
            # (SendMessage) with no agora write. Promote it.
            if row and normalize_state(row) in ("working", "blocked"):
                meta_set_if(s["seat_id"], {"status": "working", "updated": now()}, guard)
                return "live"
            # A natively-woken turn can also have STARTED AND ENDED between two
            # syncs: the record never left idle and the reply file still
            # describes the previous turn. The transcript is the only witness.
            if row and normalize_state(row) in ("done", "done-blocked", "failed", "stopped") \
                    and reply_stale(s["seat_id"], cur):
                if meta_set_if(s["seat_id"], {"updated": now()}, guard,
                               reply=(cur, normalize_state(row), s["alias"])):
                    return "idle"
            return "noop"
        if row is None:
            return "absent"
        state = normalize_state(row)
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


def cmd_mark(a):
    s = resolve_seat(a.seat)
    note = " ".join(a.note)
    if not meta_set(s["seat_id"], {"status": a.status, "updated": now(), "note": note}, create=False):
        die("seat %s/%s was removed before the mark could land" % (s["group"], s["alias"]), EXIT_UNKNOWN)
    print("marked %s/%s [%s] -> %s%s" % (s["group"], s["alias"], s["seat_id"], a.status, ("  (%s)" % note) if note else ""))


def cmd_status(a):
    s = resolve_seat(a.seat)
    line = " ".join(a.line).strip()
    # The agent's own status line is not a lifecycle write: it must never make
    # the turn's watcher refuse to record the reply (bump=False). Nor may it
    # resurrect a seat a concurrent remove just deleted (create=False).
    if not meta_set(s["seat_id"], {"now": line, "updated": now()}, bump=False, create=False):
        die("seat %s/%s was removed before the status could land" % (s["group"], s["alias"]), EXIT_UNKNOWN)
    print("%s/%s now: %s" % (s["group"], s["alias"], line or "(cleared)"))


# ------------------------------------------------------------ retire / remove


def wait_codex_rc(event_log, timeout=10.0):
    """Block until a signalled legacy codex worker has actually finished.

    The wrapper's finalizer writes `<run>.rc` as the last thing it does, so
    between the SIGTERM and that file it can still create or rewrite the run's
    scratch — and a retire or remove that returned earlier would find its purge
    undone. Absent an event log, or if the rc never lands, the wait expires and
    the caller proceeds. Returns True iff the barrier was observed."""
    el = str(event_log or "")
    if not el.endswith(".events.jsonl"):
        return False
    rc = el[: -len(".events.jsonl")] + ".rc"
    deadline = time.time() + timeout
    while not os.path.exists(rc) and time.time() < deadline:
        time.sleep(0.5)
    return os.path.exists(rc)


def stop_session(s):
    """Stop the seat's current turn. The short to stop is the CURRENT session's
    harness row when there is one (a `seat add --session` seat recorded none,
    and a recorded short goes stale after a native resume); a row is host-local
    by construction. Only the fallback to the RECORDED short is gated on the
    record's host identity — shorts are host-local and reusable, so a foreign
    one may name an unrelated local session. A legacy codex worker is a
    detached process we own: signalled by its recorded pid, as the old retire
    did, when its identity is local, then waited out to its finalizer's `.rc`
    barrier so nothing it writes lands after a caller's purge."""
    if s["engine"] == "codex":
        pid = meta_get(s["seat_id"], "pid")
        if s["status"] in ("working", "blocked") and identity_local(s["host"], s["boot_id"]) and pid_alive(pid):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError, TypeError, PermissionError):
                pass
            else:
                wait_codex_rc(meta_get(s["seat_id"], "event_log"))
        return
    agents_refresh()
    row = harness_row(s) if s["current"] else None
    if row and row.get("id"):
        claude_stop(row["id"])
    elif s["short"] and identity_local(s["host"], s["boot_id"]):
        claude_stop(s["short"])


def purge_codex_runs(event_log):
    """A codex worker's turn scratch (the event log and its siblings) lives
    outside the record; drop the whole set once nothing references it any more
    (the record is purged, or a fresh occupant has replaced the codex worker)."""
    el = str(event_log or "")
    if el.endswith(".events.jsonl"):
        for p in glob.glob(el[:-len(".events.jsonl")] + ".*"):
            try:
                os.unlink(p)
            except OSError:
                pass


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


def locked_fresh(s0, verb):
    """Take the seat's lifecycle locks and re-load the record; (locks, seat)."""
    locks = lock_seat(s0)
    s = reload_seat(s0["seat_id"])
    if s is None:
        unlock(locks)
        die("seat %s/%s vanished before the %s could start" % (s0["group"], s0["alias"], verb), EXIT_UNKNOWN)
    return locks, s


def cmd_retire(a):
    locks, s = locked_fresh(resolve_seat(a.seat), "retire")
    try:
        stop_session(s)
        if s["engine"] == "codex":
            hint = "legacy codex-CLI worker — no resume path; remove with: agora remove %s/%s" % (s["group"], s["alias"])
        elif s["current"]:
            hint = "agora fill %s/%s --resume \"<task>\"" % (s["group"], s["alias"])
        else:
            hint = "agora fill %s/%s \"<task>\"" % (s["group"], s["alias"])
        if a.purge:
            if s["engine"] == "codex":
                purge_codex_runs(meta_get(s["seat_id"], "event_log"))
            unlink_seat_files(s["seat_id"])
            print("purged %s/%s [%s] from the registry (session transcript left intact)%s" % (
                s["group"], s["alias"], s["seat_id"], worktree_note(s)))
        else:
            meta_set(s["seat_id"], {"status": "retired", "updated": now()})
            print("retired %s/%s [%s] (seat kept; re-fill with: %s)%s" % (
                s["group"], s["alias"], s["seat_id"], hint, worktree_note(s)))
    finally:
        unlock(locks)


def cmd_remove(a):
    locks, s = locked_fresh(resolve_seat(a.seat), "remove")
    try:
        stop_session(s)
        if s["engine"] == "codex":
            purge_codex_runs(meta_get(s["seat_id"], "event_log"))
        unlink_seat_files(s["seat_id"])
        print("removed %s/%s [%s] (board history kept)%s" % (s["group"], s["alias"], s["seat_id"], worktree_note(s)))
    finally:
        unlock(locks)


def cmd_leave(a):
    a.seat = "%s/%s" % (a.group, a.alias)
    cmd_remove(a)


# --------------------------------------------------------------------- views


def now_or_reply(s):
    if s["now"]:
        return s["now"]
    return " ".join(reply_text(s["seat_id"]).split())[:46]


def cmd_list(a):
    rows = seats(a.group)
    if a.status:
        rows = [s for s in rows if s["status"] == a.status]
    rows.sort(key=lambda s: s["updated"], reverse=True)
    if a.json:
        out = []
        for s in rows:
            d = public_seat(s)
            d["live"] = live_state(s)
            out.append(d)
        print(json.dumps(out, indent=2))
        return
    if not rows:
        print("(no seats)")
        return
    fmt = "%-18s %-14s %-12s %-14s %-8s %-9s %-18s %s"
    print(fmt % ("ALIAS", "GROUP", "ROLE", "STATUS", "LIVE", "SHORT", "ADDR", "NOW"))
    for s in rows:
        print(fmt % (s["alias"][:18], s["group"][:14], (s["role"] or "-")[:12], s["status"][:14], live_state(s),
                     (s["short"] or s["seat_id"][:8])[:8], s["addr"][:18], now_or_reply(s)[:46]))


def children_of(group_seats, alias):
    return [s for s in group_seats if s["parent"] == alias]


def tree(group):
    """(depth, seat) rows in render order; orphans (parent unknown) are roots too."""
    gs = sorted(seats(group), key=lambda s: s["alias"])
    aliases = {s["alias"] for s in gs}
    out = []

    def walk(s, depth):
        out.append((depth, s))
        for c in children_of(gs, s["alias"]):
            walk(c, depth + 1)
    for s in gs:
        if not s["parent"] or s["parent"] not in aliases:
            walk(s, 0)
    return out


def seat_row(s):
    head = s["alias"] + (" [%s]" % s["role"] if s["role"] else "")
    bits = [head, live_state(s)]
    if s["now"]:
        bits.append(s["now"])
    return " · ".join(bits)


def render_tree(gs, s, line_prefix, child_prefix, out):
    # line_prefix draws THIS row, child_prefix is what every descendant row
    # inherits — so depth accumulates instead of resetting.
    out.append(line_prefix + seat_row(s))
    kids = children_of(gs, s["alias"])
    for i, k in enumerate(kids):
        last = i == len(kids) - 1
        render_tree(gs, k, child_prefix + ("└── " if last else "├── "), child_prefix + ("    " if last else "│   "), out)


def cmd_view(a):
    g = a.group
    if not valid_name(g):
        die("bad group name: %s" % g)
    if not group_exists(g):
        die("no such group: %s" % g, EXIT_UNKNOWN)
    gs = sorted(seats(g), key=lambda s: s["alias"])
    aliases = {s["alias"] for s in gs}
    print("agora group: %s" % g)
    out = []
    for s in gs:
        if not s["parent"]:
            render_tree(gs, s, "", "", out)
    if not gs:
        out.append("(no seats)")
    for s in [s for s in gs if s["parent"] and s["parent"] not in aliases]:
        out.append("(dangling — parent '%s' unknown)" % s["parent"])
        render_tree(gs, s, "    ", "    ", out)
    print("\n".join(out))
    posts = read_board(g)
    if posts:
        last = posts[-1]
        print("board: %d post(s) — latest: #%s%s by %s @ %s" % (
            len(posts), last.get("id"), (' "%s"' % last["title"]) if last.get("title") else "", last.get("from"), last.get("ts")))


def cmd_topology(a):
    g = a.group
    if not valid_name(g):
        die("bad group name: %s" % g)
    if not group_exists(g):
        die("no such group: %s" % g, EXIT_UNKNOWN)
    gs = sorted(seats(g), key=lambda s: s["alias"])
    nodes = []
    for s in gs:
        d = public_seat(s)
        d["live"] = live_state(s)
        nodes.append(d)
    edges = [{"from": s["parent"], "to": s["alias"]} for s in gs if s["parent"]]
    # `nodes` is the v2 key; kept for one release so v2 preambles keep parsing.
    print(json.dumps({"group": g, "seats": nodes, "nodes": nodes, "edges": edges}, indent=2))


def cmd_groups(a):
    names = {s["group"] for s in seats()}
    for gp in glob.glob(os.path.join(root(), "groups", "*")):
        if os.path.isdir(gp):
            names.add(os.path.basename(gp))
    if not names:
        print("(no groups)")
        return
    for g in sorted(names):
        gs = seats(g)
        live = sum(1 for s in gs if live_state(s) in FILLED)
        posts = read_board(g)
        last = posts[-1].get("ts", "-") if posts else "-"
        print("%-24s %3d seats (%d live)   last post: %s" % (g, len(gs), live, last))


def cmd_attach(a):
    s = resolve_seat(a.seat)
    live = live_state(s)
    row = harness_row(s) if s["current"] else None
    short = (row or {}).get("id") or s["short"]
    if not short:
        die("%s/%s has no session to attach to (%s)" % (s["group"], s["alias"], live), EXIT_UNKNOWN)
    if live in FILLED and sys.stdout.isatty() and not os.environ.get("AGORA_NO_EXEC"):
        os.execvp("claude", ["claude", "attach", short])
    print("claude attach %s" % short)


def chart_module():
    """Import agora_chart bound to THIS module instance (when agora.py runs as
    __main__ a plain `import agora` would execute the file a second time and
    give the chart its own, separate harness caches)."""
    sys.modules.setdefault("agora", sys.modules[__name__])
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import agora_chart
    return agora_chart


def chart_group_or_die(g):
    if g is not None:
        if not valid_name(g):
            die("bad group name: %s" % g)
        if not group_exists(g):
            die("no such group: %s" % g, EXIT_UNKNOWN)


def cmd_chart(a):
    """The organisation chart as text: boxes left-to-right, dead seats folded
    into '+N retired' unless --all, then one summary line."""
    g = a.group
    chart_group_or_die(g)
    chart = chart_module()
    roots, meta = chart.snapshot(g, a.all)
    lay = chart.layout(roots)
    width = a.width or (shutil.get_terminal_size((120, 40)).columns if sys.stdout.isatty() else 120)
    if lay["boxes"]:
        scr = chart.GridScreen(width, lay["height"])
        chart.paint_chart(scr, lay)
        print(scr.text())
    else:
        print("(no seats to chart%s)" % ("" if a.all or not meta["hidden"] else " — all %d are retired; agora chart --all" % meta["hidden"]))
    bits = []
    if g is None:
        bits.append("%d groups" % meta["groups"])
    bits += ["%d seats" % meta["seats"], "%d live" % meta["live"]]
    if meta["hidden"]:
        hid = "%d hidden" % meta["hidden"]
        if meta["hidden_groups"]:
            hid += " in %d group(s) folded away" % meta["hidden_groups"]
        bits.append(hid + ("" if a.all else " (agora chart%s --all)" % ((" " + g) if g else "")))
    if lay["width"] > width:
        bits.append("%d cells clipped on the right (--width %d)" % (lay["width"] - width, width))
    print(" · ".join(bits))


# --------------------------------------------------------------------- board

# The board is the group's communal surface: durable long-form posts, JSONL
# on disk, rendered as markdown inside XML envelopes on read. Delivery is the
# poster's job: after writing, nudge the seats who should read it now with a
# one-line native SendMessage naming the post id (the command prints their
# addrs). A seat that is never nudged still finds the post — the board is the
# durable record and `view` summarizes it.


def board_lock(g):
    """mkdir spinlock: portable, no flock semantics needed. A lock dir that
    stays for >30s is presumed leaked by a killed process and is broken."""
    lk = os.path.join(group_dir(g), "locks", "board.lock")
    os.makedirs(os.path.dirname(lk), exist_ok=True)
    tries = 0
    while True:
        try:
            os.mkdir(lk)
            return lk
        except FileExistsError:
            tries += 1
            if tries > 200:
                try:
                    if time.time() - os.stat(lk).st_mtime > 30:
                        os.rmdir(lk)
                except OSError:
                    pass
                tries = 0
            time.sleep(0.05)


def board_unlock(lk):
    try:
        os.rmdir(lk)
    except OSError:
        pass


def read_board(g):
    out = []
    try:
        with open(os.path.join(group_dir(g), "board.jsonl")) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return out


def git_branch(cwd):
    try:
        return subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def cmd_post(a):
    g = a.group
    if not valid_name(g):
        die("bad group name: %s" % g)
    if not group_exists(g):
        die("no such group: %s (a group is created by its first seat)" % g, EXIT_UNKNOWN)
    frm = default_from(a.frm or os.environ.get("AGORA_ALIAS") or "")
    text = " ".join(a.text).strip() if a.text else sys.stdin.read()
    if not text.strip():
        die("post: empty body")
    if not valid_name(frm):
        die("bad --from alias: %s" % frm)
    gs = seats(g)
    if frm != "human" and not any(s["alias"] == frm for s in gs):
        die("poster %s is not a seat in %s (run: agora seat add %s %s)" % (frm, g, g, frm), EXIT_UNKNOWN)
    cwd = os.getcwd()
    # cwd/branch are snapshotted at post time — the seat's registry values
    # describe where it started, not where this post was written.
    body = {"ts": now(), "from": frm, "title": a.title or "", "cwd": cwd, "branch": git_branch(cwd), "text": text}
    lk = board_lock(g)
    try:
        bf = os.path.join(group_dir(g), "board.jsonl")
        # One past the HIGHEST id ever stored, not one past the count:
        # `read_board` skips lines it cannot parse, so a single corrupt line
        # would otherwise hand the new post an id a live post already holds,
        # and every `board --id N` after it would be ambiguous.
        ids = [p["id"] for p in read_board(g) if isinstance(p, dict) and isinstance(p.get("id"), int)]
        rec = {"id": (max(ids) + 1) if ids else 1, **body}
        with open(bf, "a") as f:
            f.write(json.dumps(rec) + "\n")
    finally:
        board_unlock(lk)
    others = [s["addr"] for s in gs if s["alias"] != frm and s["status"] != "retired"]
    print("posted #%d to %s board" % (rec["id"], g))
    if others:
        print("  nudge readers via SendMessage — addrs: %s" % ", ".join(others))
        print("  e.g.: agora board post #%d by %s%s · read with: agora board %s --id %d" % (
            rec["id"], frm, (' — "%s"' % a.title) if a.title else "", g, rec["id"]))


def html_attr(v):
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def esc_body(v):
    # Only the envelope's own grammar is neutralized: a body carrying
    # '</agora-post>' would otherwise close the frame early and forge an
    # apparent next post with fake provenance. Everything else stays raw;
    # readable markdown is the whole point of the board.
    return str(v).replace("<agora-post", "&lt;agora-post").replace("</agora-post", "&lt;/agora-post")


def cmd_board(a):
    g = a.group
    if not valid_name(g):
        die("bad group name: %s" % g)
    if not group_exists(g):
        die("no such group: %s" % g, EXIT_UNKNOWN)
    posts = read_board(g)
    if not posts:
        if not a.json:
            print("(no posts)")
        return
    if a.id is not None:
        # --id is what a nudge names: a post number, fetchable individually —
        # a seat with several nudges queued reads each one, not just the latest.
        sel = [p for p in posts if p.get("id") == a.id]
        if not sel:
            die("no such post on the %s board: #%d" % (g, a.id), EXIT_UNKNOWN)
    elif a.n and a.n > 0:
        sel = posts[-a.n:]
    else:
        sel = posts
    if a.json:
        for p in sel:
            print(json.dumps(p))
        return
    for p in sel:
        head = '<agora-post id="%s" from="%s" ts="%s"' % (p.get("id"), html_attr(p.get("from", "")), html_attr(p.get("ts", "")))
        if p.get("branch"):
            head += ' branch="%s"' % html_attr(p["branch"])
        head += ' cwd="%s">' % html_attr(p.get("cwd", ""))
        body = ""
        if p.get("title"):
            body += "\n## " + esc_body(p["title"])
        body += "\n" + esc_body(p.get("text", "")) + "\n</agora-post>\n"
        print(head + body)


# ---------------------------------------------------------------------- meta


def cmd_meta(a):
    s = resolve_seat(a.seat)
    if a.op == "get":
        if not a.field:
            die("usage: agora meta get <seat> <field>")
        if SECRET_RE.search(a.field):
            # The CLI is model-callable; the pipeline reads credentials from the
            # record file directly, never through here.
            die("'%s' is a credential field — not readable through the agora CLI" % a.field, EXIT_UNKNOWN)
        v = meta_get(s["seat_id"], a.field)
        print(v if isinstance(v, str) else json.dumps(v))
        return
    pairs = ([a.field] if a.field else []) + list(a.values)
    if not pairs or len(pairs) % 2 != 0:
        die("usage: agora meta set <seat> <field> <value> [<field> <value>...]")
    fields = {pairs[i]: pairs[i + 1] for i in range(0, len(pairs), 2)}
    # Raw field edits are not lifecycle writes, and never recreate a removed seat.
    if not meta_set(s["seat_id"], fields, bump=False, create=False):
        die("seat %s/%s was removed before the write could land" % (s["group"], s["alias"]), EXIT_UNKNOWN)
    print("set %s on %s/%s" % (", ".join(sorted(fields)), s["group"], s["alias"]))


# ------------------------------------------------------------------ dispatch


def usage():
    print((__doc__ or "").strip())


def build_parser():
    p = argparse.ArgumentParser(prog="agora", add_help=False)
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
    # the seat's value) from "given as empty".
    sp.add_argument("--group", default=None)
    sp.add_argument("--parent", default=None)
    sp.add_argument("--role", default=None)
    sp.add_argument("--brief", default=None)
    sp.add_argument("--cwd", default="")
    sp.add_argument("--worktree", default="")
    sp.add_argument("--addr", default=None)
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
    sa.add_argument("--parent", default=None)
    sa.add_argument("--addr", default="")
    sa.add_argument("--session", default="")
    sa.set_defaults(fn=cmd_seat_add)

    j = sub.add_parser("join", add_help=False)
    j.add_argument("group")
    j.add_argument("alias")
    j.add_argument("--parent", default=None)
    j.add_argument("--desc", default=None)
    j.add_argument("--role", default=None)
    j.add_argument("--session", default="")
    j.add_argument("--addr", default="")
    j.set_defaults(fn=cmd_join)

    f = sub.add_parser("fill", add_help=False)
    f.add_argument("seat")
    f.add_argument("task")
    f.add_argument("--resume", action="store_true")
    route_flags(f)
    f.set_defaults(fn=cmd_fill)

    w = sub.add_parser("wake", add_help=False)
    w.add_argument("seat")
    w.add_argument("msg")
    w.add_argument("--wait", action="store_true")
    w.add_argument("--from", dest="frm", default="")
    w.set_defaults(fn=cmd_wake)

    rs = sub.add_parser("resume", add_help=False)
    rs.add_argument("seat")
    rs.add_argument("msg")
    route_flags(rs)
    rs.set_defaults(fn=cmd_resume)

    s = sub.add_parser("send", add_help=False)
    s.add_argument("target")
    s.add_argument("msg")
    s.add_argument("--from", dest="frm", default="")
    s.set_defaults(fn=cmd_send)

    r = sub.add_parser("reply", add_help=False)
    r.add_argument("seat")
    r.set_defaults(fn=cmd_reply)

    sy = sub.add_parser("sync", add_help=False)
    sy.add_argument("seat", nargs="?", default="")
    sy.add_argument("--all", action="store_true")
    sy.set_defaults(fn=cmd_sync)

    m = sub.add_parser("mark", add_help=False)
    m.add_argument("seat")
    m.add_argument("status")
    m.add_argument("note", nargs="*")
    m.set_defaults(fn=cmd_mark)

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

    lv = sub.add_parser("leave", add_help=False)
    lv.add_argument("group")
    lv.add_argument("alias")
    lv.set_defaults(fn=cmd_leave)

    ls = sub.add_parser("list", add_help=False)
    ls.add_argument("group", nargs="?", default=None)
    ls.add_argument("--status", default="")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(fn=cmd_list)

    v = sub.add_parser("view", add_help=False)
    v.add_argument("group")
    v.set_defaults(fn=cmd_view)

    t = sub.add_parser("topology", add_help=False)
    t.add_argument("group")
    t.add_argument("--json", action="store_true")
    t.set_defaults(fn=cmd_topology)

    ch = sub.add_parser("chart", add_help=False)
    ch.add_argument("group", nargs="?", default=None)
    ch.add_argument("--all", action="store_true")
    ch.add_argument("--width", type=int, default=0)
    ch.set_defaults(fn=cmd_chart)

    g = sub.add_parser("groups", add_help=False)
    g.set_defaults(fn=cmd_groups)

    po = sub.add_parser("post", add_help=False)
    po.add_argument("group")
    po.add_argument("--from", dest="frm", default="")
    po.add_argument("--title", default="")
    po.add_argument("text", nargs="*")
    po.set_defaults(fn=cmd_post)

    b = sub.add_parser("board", add_help=False)
    b.add_argument("group")
    b.add_argument("-n", type=int, default=0)
    b.add_argument("--id", type=int, default=None)
    b.add_argument("--json", action="store_true")
    b.set_defaults(fn=cmd_board)

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


def parse_post(argv):
    """`post <group> [--from F] [--title T] [text...]` by hand: argparse cannot
    take free text after options once a zero-or-more positional has matched."""
    ns = argparse.Namespace(cmd="post", frm="", title="", text=[], group=None, fn=cmd_post)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            ns.text.extend(argv[i + 1:])
            break
        if a in ("--from", "--title"):
            if i + 1 >= len(argv):
                die("post: %s needs a value" % a)
            setattr(ns, "frm" if a == "--from" else "title", argv[i + 1])
            i += 2
            continue
        if a.startswith("--from="):
            ns.frm = a.split("=", 1)[1]
        elif a.startswith("--title="):
            ns.title = a.split("=", 1)[1]
        elif ns.group is None:
            ns.group = a
        else:
            ns.text.append(a)
        i += 1
    if ns.group is None:
        die("usage: agora post <group> [--from F] [--title T] [text...]")
    return ns


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        usage()
        sys.exit(0 if argv else EXIT_USAGE)
    if argv[0] in ("listen", "log"):
        die("'%s' is gone — messaging rides the harness SendMessage tool (a seat's addr in 'agora topology' "
            "is the target); from a terminal use 'agora send'; the board (agora post/board) is the durable record" % argv[0])
    if argv[0] == "post":
        a = parse_post(argv[1:])
        migrate()
        cmd_post(a)
        return
    parser = build_parser()
    try:
        a = parser.parse_args(argv)
    except SystemExit:
        sys.exit(EXIT_USAGE)
    if a.cmd == "migrate":
        did = migrate(quiet=True)
        if did and not a.quiet:
            print("agora: migrated: %s" % "; ".join(did))
        return
    if not getattr(a, "fn", None):
        if a.cmd == "seat":
            die("usage: agora seat add <group> <alias> [--role R] [--brief B] [--parent P] [--addr A] [--session S]")
        die("unknown command: %s (try: agora help)" % argv[0])
    migrate()
    a.fn(a)


if __name__ == "__main__":
    main()
