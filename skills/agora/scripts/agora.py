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
import json
import os
import re
import shutil
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
UUID_RE = re.compile(r"^[0-9a-f-]{36}$")
FILLED = ("busy", "idle", "blocked")
TERMINAL = ("done", "done-blocked", "blocked", "failed", "stopped", "error")


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


def meta_set(seat_id, fields, remove=()):
    """Merge fields into a seat record (creating it if absent).

    The read-modify-write is serialized across processes with an advisory flock
    on the shared lock file: the board pipeline's own writers take the same
    lock, so concurrent stamps never clobber each other's fields. The record is
    recreated at the mode it already has, never at the umask: a bookkeeping
    write on a record carrying the board run bearer would otherwise republish
    that secret world-readable; a record carrying `run_bearer` is forced to
    0600 either way. A record that does not exist yet gets the umask default.
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
                data = {}
            for k, v in fields.items():
                data[k] = v
            for k in remove:
                data.pop(k, None)
            tmp = path + ".tmp"
            try:
                mode = os.stat(path).st_mode & 0o777
            except FileNotFoundError:
                mode = None
            if data.get("run_bearer"):
                mode = 0o600
            if mode is None:
                with open(tmp, "w") as f:
                    json.dump(data, f, indent=2)
            else:
                try:
                    os.unlink(tmp)  # a tmp left by an earlier crash
                except FileNotFoundError:
                    pass
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2)
                os.chmod(tmp, mode)  # umask narrowing
            os.replace(tmp, path)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


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
    for k in ("parent", "role", "brief", "now", "note", "current", "short", "cwd",
              "worktree", "model", "settings", "effort", "task", "host", "boot_id",
              "created", "updated", "engine", "preamble"):
        v = m.get(k)
        m[k] = "" if v is None else str(v)
    m["status"] = str(m.get("status") or "?")
    m["turns"] = str(m.get("turns") or "0")
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


def resolve_seat(q):
    """Resolve a query to a seat record.

    Order: `group/alias`, seat id (or prefix), current turn's short id or
    session id (or prefix), then a bare alias when exactly one seat has it.
    """
    if not q:
        die("empty seat reference")
    all_seats = seats()
    if "/" in q:
        g, a = q.split("/", 1)
        hits = [s for s in all_seats if s["group"] == g and s["alias"] == a]
        if len(hits) == 1:
            return hits[0]
        die("no seat %s" % q, EXIT_UNKNOWN)
    hits = [s for s in all_seats if s["seat_id"] == q or s["seat_id"].startswith(q)]
    if not hits:
        hits = [s for s in all_seats
                if (s["short"] and (s["short"] == q or s["short"].startswith(q)))
                or (s["current"] and (s["current"] == q or s["current"].startswith(q)))]
    if not hits:
        hits = [s for s in all_seats if s["alias"] == q]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        die("no seat matching '%s'" % q, EXIT_UNKNOWN)
    die("ambiguous seat '%s' matches: %s" % (
        q, ", ".join("%s/%s [%s]" % (s["group"], s["alias"], s["seat_id"][:8]) for s in hits)),
        EXIT_UNKNOWN)


def group_dir(g):
    return os.path.join(root(), "groups", g)


def group_exists(g):
    return os.path.isdir(group_dir(g)) or any(True for _ in seats(g))


def derive_group(cwd):
    """Default group for a seat spawned without --group: the repository name.

    Board-pipeline workers therefore group by repository without their
    dispatchers learning about groups.
    """
    name = ""
    if cwd and os.path.isdir(cwd):
        try:
            top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            top = ""
        name = os.path.basename(top) if top else os.path.basename(os.path.normpath(cwd))
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name)[:64]
    if not valid_name(name):
        name = "fleet"
    return name


def lifecycle_lock(group, alias):
    """One lifecycle change per seat at a time: spawn / fill / seat add / resume
    hold this flock from their availability check through the record commit
    (through process start, for resume), so two concurrent spawns of the same
    seat cannot both pass the "is it free?" check and double-spawn. The kernel
    releases it the moment the holder exits."""
    d = os.path.join(root(), "locks")
    os.makedirs(d, exist_ok=True)
    lf = open(os.path.join(d, "%s__%s.lock" % (group, alias)), "a+")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        die("seat %s/%s is being changed by another agora process — retry shortly" % (group, alias), EXIT_UNKNOWN)
    return lf


# ------------------------------------------------------------------- harness

_AGENTS = None
_PEERS = None


def agents_json():
    """Rows from `claude agents --json --all`; [] when the harness is unavailable."""
    global _AGENTS
    if _AGENTS is None:
        try:
            out = subprocess.run(["claude", "agents", "--json", "--all"],
                                 capture_output=True, text=True, timeout=60).stdout
            parsed = json.loads(out) if out.strip() else []
            _AGENTS = parsed if isinstance(parsed, list) else []
        except Exception:
            _AGENTS = []
    return _AGENTS


def agents_refresh():
    global _AGENTS
    _AGENTS = None
    return agents_json()


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


def peer_for_session(session_id):
    if not session_id:
        return None
    for rec in peer_records():
        if rec.get("sessionId") == session_id and pid_alive(rec.get("pid")):
            return rec
    return None


def live_name_holders(name):
    return [r for r in peer_records() if r.get("name") == name and pid_alive(r.get("pid"))]


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


def send_frame(path, text):
    """Write one message frame to a session's inbox socket.

    The frame the harness documents for scripts is a plain user message; it is
    delivered as a peer message ("another Claude session sent…"). The frame
    carries no sender name, so callers put identity in the text's first line.
    """
    frame = {"type": "user", "message": {"role": "user", "content": text}}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect(path)
        s.sendall((json.dumps(frame) + "\n").encode())
        s.shutdown(socket.SHUT_WR)
        try:
            s.recv(4096)
        except OSError:
            pass
    finally:
        s.close()


def agent_row(session_id=None, short=None):
    for r in agents_json():
        if session_id and r.get("sessionId") == session_id:
            return r
        if short and r.get("id") == short and r.get("sessionId"):
            return r
    return None


def harness_row(seat):
    """The harness row for a seat's current session. After a resume the old
    (stopped) job and the new one share a session id, so the recorded short —
    the latest launch — wins; among session-id matches a running turn wins."""
    rows = agents_json()
    if seat["short"]:
        for r in rows:
            if r.get("id") == seat["short"] and r.get("sessionId") and (
                    not seat["current"] or r.get("sessionId") == seat["current"]):
                return r
    cands = [r for r in rows if seat["current"] and r.get("sessionId") == seat["current"]]
    for r in cands:
        if normalize_state(r) in ("working", "blocked"):
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
    """Harness-derived liveness: busy, idle, blocked, stopped, gone, vacant."""
    cur = seat.get("current") or ""
    if not cur:
        return "vacant"
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
    """Run `claude --bg …` in cwd; return (short, banner). short is "" on failure."""
    if not (cwd and os.path.isdir(cwd)):
        cwd = home_dir()
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
    if short:
        subprocess.run(["claude", "stop", short], capture_output=True, text=True, timeout=60)


def poll_uuid(short, max_iter=None):
    """Wait for the harness row of a just-launched short id to carry a session
    id — the row can lag the banner by a beat. Returns (uuid, state, cwd) or None."""
    if max_iter is None:
        max_iter = int(os.environ.get("AGORA_UUID_POLL") or os.environ.get("DAEMON_UUID_POLL") or "30")
    for i in range(max_iter):
        if i:
            agents_refresh()
        else:
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
    t = int(os.environ.get("DAEMON_TIMEOUT") or "18000")
    if t == 0:
        return 0
    iv = poll_interval()
    return max(1, int(t / 2 / iv)) if iv >= 1 else max(1, t // 2)


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


# ----------------------------------------------------------------- migration


def convert_v2_nodes(r):
    converted = 0
    for nodes_dir in glob.glob(os.path.join(r, "groups", "*", "nodes")):
        g = os.path.basename(os.path.dirname(nodes_dir))
        for nf in glob.glob(os.path.join(nodes_dir, "*.json")):
            try:
                with open(nf) as f:
                    n = json.load(f)
            except Exception:
                continue
            sess = str(n.get("session") or "")
            seat_id = sess if UUID_RE.match(sess) else str(uuidlib.uuid4())
            alias = str(n.get("alias") or os.path.basename(nf)[:-5])
            if os.path.exists(meta_path(seat_id)):
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
            converted += 1
        shutil.rmtree(nodes_dir, ignore_errors=True)
    return converted


def migrate(explicit=False, quiet=False):
    """Bring a pre-seat state root up to date. Idempotent; runs before every verb.

    1. Old root: when the default root is in use and ~/.claude/orchestrating-daemons
       is a real directory, the old root is renamed INTO place as one atomic
       step (any existing ~/.claude/agora is set aside first and its groups/
       merged back), and a symlink is left at the old path so anything still
       holding it keeps resolving. Entry-by-entry copying would leave two half
       roots on a crash; a rename cannot.
    2. v2 layout: groups/<g>/nodes/*.json become seat records (retired).
    3. Once: records lacking `group` are stamped from their cwd, and legacy
       codex-CLI worker records (engine: codex) are marked retired — their
       resume path no longer exists.
    """
    r = root()
    did = []
    old = os.path.join(home_dir(), ".claude", "orchestrating-daemons")
    if r == default_root() and os.path.isdir(old) and not os.path.islink(old):
        aside = ""
        if os.path.lexists(r):
            aside = r + ".v2-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            os.rename(r, aside)
        os.rename(old, r)
        if aside:
            ag = os.path.join(aside, "groups")
            if os.path.isdir(ag):
                os.makedirs(os.path.join(r, "groups"), exist_ok=True)
                for g in os.listdir(ag):
                    src, dst = os.path.join(ag, g), os.path.join(r, "groups", g)
                    if os.path.isdir(dst):
                        for sub in os.listdir(src):
                            if not os.path.exists(os.path.join(dst, sub)):
                                shutil.move(os.path.join(src, sub), os.path.join(dst, sub))
                        if not os.listdir(src):
                            os.rmdir(src)
                    else:
                        shutil.move(src, dst)
                if not os.listdir(ag):
                    os.rmdir(ag)
            if os.path.isdir(aside) and not os.listdir(aside):
                os.rmdir(aside)
            elif os.path.isdir(aside):
                did.append("left %s aside (unmerged entries)" % aside)
        os.symlink(r, old)
        did.append("renamed %s -> %s (old path is now a symlink)" % (old, r))
    n = convert_v2_nodes(r)
    if n:
        did.append("converted %d v2 node(s) into seats" % n)
    marker = os.path.join(r, ".migrated-v3")
    if os.path.isdir(r) and not os.path.exists(marker):
        stamped = retired = 0
        for p in record_files():
            try:
                with open(p) as f:
                    m = json.load(f)
            except Exception:
                continue
            fields = {}
            if not m.get("group"):
                fields["group"] = derive_group(str(m.get("cwd") or ""))
                stamped += 1
            if m.get("engine") == "codex" and m.get("status") != "retired":
                fields["status"] = "retired"
                fields["updated"] = now()
                retired += 1
            if fields:
                meta_set(os.path.basename(p)[:-5], fields)
        with open(marker, "w") as f:
            f.write(now() + "\n")
        if stamped or retired:
            did.append("stamped group on %d record(s), retired %d legacy codex record(s)" % (stamped, retired))
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


def finish_turn(seat_id, short, alias, uuid_hint=""):
    """--wait: watch a turn to its end, record the reply, return the status.
    A watcher timeout is not a finished turn: status stays working and the
    reply is readable later with `agora reply`."""
    uuid, state, _cwd, finished = poll_until_done(short, watcher_iterations())
    if not finished:
        meta_set(seat_id, {"status": "working", "updated": now()})
        sys.stderr.write("agora: watcher expired; turn %s of %s is still running (status=working). "
                         "Read it later with: agora reply %s\n" % (short, alias, alias))
        sys.exit(1)
    status = status_for_state(state)
    record_reply(uuid or uuid_hint, seat_id, state, alias)
    meta_set(seat_id, {"status": status, "updated": now()})
    return status


def print_reply_block(seat_id):
    print("--- reply ---")
    print(reply_text(seat_id) or "(no reply yet)")


def cmd_spawn(a):
    alias = a.alias
    if not valid_name(alias):
        die("bad alias: %s" % alias)
    if alias == "human":
        die("the alias 'human' is reserved for the operator")
    if a.parent and not valid_name(a.parent):
        die("bad parent alias: %s" % a.parent)
    cwd = os.path.abspath(a.cwd or os.getcwd())
    explicit_group = a.group is not None
    group = a.group if explicit_group else derive_group(cwd)
    if not valid_name(group):
        die("bad group name: %s" % group)
    lock = lifecycle_lock(group, alias)
    for s in seats(group):
        if s["alias"] == alias:
            live = live_state(s)
            if live in FILLED:
                die("seat %s/%s is filled (live: %s) — message it with agora send/wake" % (group, alias, live), EXIT_UNKNOWN)
            die("seat %s/%s exists (%s) — fill it with: agora fill %s/%s \"<task>\" [--resume]" % (
                group, alias, live, group, alias), EXIT_UNKNOWN)
    addr = a.addr or alias
    refuse_live_name(alias, addr)
    settings = env_default(a.settings, "DAEMON_CLAUDE_SETTINGS")
    effort = env_default(a.effort, "DAEMON_CLAUDE_EFFORT")
    preamble = render_preamble(group, alias, a.parent or "") if explicit_group else ""
    task_text = compose_task(a.task, a.brief or "", preamble)

    short, banner = run_claude_bg(claude_args(alias, a.model or "", settings, effort, a.worktree or "") + [task_text],
                                  cwd, settings)
    if not short:
        sys.stderr.write("agora: spawn failed — could not parse background id from:\n%s\n" % banner)
        sys.exit(1)
    # The seat exists as soon as the launch is known to have SUCCEEDED and
    # before the first turn is polled — the agent may post or be looked up in
    # the topology during its very first turn, while a failed launch must
    # leave no phantom seat behind.
    prov = str(uuidlib.uuid4())
    fields = {
        "uuid": prov, "current": "", "short": short, "name": alias, "alias": alias, "group": group,
        "parent": a.parent or "", "addr": addr, "role": a.role or "", "brief": a.brief or "",
        "task": task_text, "now": "", "note": "", "cwd": cwd, "worktree": a.worktree or "",
        "model": a.model or "", "settings": settings, "effort": effort, "status": "working",
        "host": host_name(), "boot_id": boot_id(), "created": now(), "updated": now(), "turns": "1",
        "preamble": "1" if explicit_group else "",
    }
    meta_set(prov, fields)
    polled = poll_uuid(short)
    if not polled or not re.match(r"^[0-9a-f-]+$", polled[0]):
        meta_set(prov, {"status": "error", "pending_short": short, "updated": now()})
        sys.stderr.write("agora: spawn: session %s produced no usable session uuid; record %s kept "
                         "(status=error, pending_short)\n" % (short, prov[:8]))
        sys.exit(1)
    uuid, state, runcwd = polled
    seat_id = uuid
    # The record is named after the first session's uuid — the pipeline
    # resolves seats by that filename prefix.
    if seat_id != prov and not os.path.exists(meta_path(seat_id)):
        os.replace(meta_path(prov), meta_path(seat_id))
    elif seat_id != prov:
        os.unlink(meta_path(prov))
    fields.update({"uuid": seat_id, "current": uuid, "cwd": runcwd or cwd, "updated": now()})
    meta_set(seat_id, fields)
    status = "working"
    if state in TERMINAL:
        # Don't blindly claim working — a fast first turn may already be over.
        status = status_for_state(state)
        record_reply(uuid, seat_id, state, alias)
        meta_set(seat_id, {"status": status, "updated": now()})
    lock.close()
    if a.wait:
        status = finish_turn(seat_id, short, alias, uuid)
    wt = ("  worktree=%s (branch worktree-%s)" % (runcwd, re.sub(r"[^a-zA-Z0-9._-]", "-", a.worktree))) if a.worktree else ""
    print("seat spawned: %s  [%s / %s]  group=%s  status=%s%s  (reply: agora reply %s)" % (
        alias, short, uuid, group, status, wt, short))
    if a.wait:
        print_reply_block(seat_id)


def cmd_seat_add(a):
    if not valid_name(a.group):
        die("bad group name: %s" % a.group)
    if not valid_name(a.alias):
        die("bad alias: %s" % a.alias)
    if a.alias == "human":
        die("the alias 'human' is reserved for the operator")
    if a.parent and not valid_name(a.parent):
        die("bad parent alias: %s" % a.parent)
    lock = lifecycle_lock(a.group, a.alias)
    existing = [s for s in seats(a.group) if s["alias"] == a.alias]
    addr = a.addr or (existing[0]["addr"] if existing else a.alias)
    session = a.session or ""
    refuse_live_name(a.alias, addr, allow_session=session or (existing[0]["current"] if existing else ""))
    if existing:
        s = existing[0]
        seat_id = s["seat_id"]
        fields = {"parent": a.parent if a.parent is not None else s["parent"],
                  "addr": addr, "role": a.role if a.role is not None else s["role"],
                  "brief": a.brief if a.brief is not None else s["brief"], "updated": now()}
        if session:
            fields.update({"current": session, "status": "idle", "host": host_name(), "boot_id": boot_id()})
        meta_set(seat_id, fields)
    else:
        seat_id = session if UUID_RE.match(session) else str(uuidlib.uuid4())
        if os.path.exists(meta_path(seat_id)):
            die("a seat record for session %s already exists (%s/%s)" % (
                session, meta_get(seat_id, "group"), meta_get(seat_id, "alias") or meta_get(seat_id, "name")), EXIT_UNKNOWN)
        meta_set(seat_id, {
            "uuid": seat_id, "current": session, "short": "", "name": a.alias, "alias": a.alias,
            "group": a.group, "parent": a.parent or "", "addr": addr, "role": a.role or "",
            "brief": a.brief or "", "task": "", "now": "", "note": "", "cwd": os.getcwd(), "worktree": "",
            "model": "", "settings": "", "effort": "", "status": "idle" if session else "vacant",
            "host": host_name() if session else "", "boot_id": boot_id() if session else "",
            "created": now(), "updated": now(), "turns": "0", "preamble": "1"})
    os.makedirs(os.path.join(group_dir(a.group), "locks"), exist_ok=True)
    lock.close()
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
    s = resolve_seat(a.seat)
    refuse_codex(s)
    lock = lifecycle_lock(s["group"], s["alias"])
    live = live_state(s)
    if live in FILLED:
        die("seat %s/%s is filled (live: %s) — use agora wake or agora send" % (s["group"], s["alias"], live), EXIT_UNKNOWN)
    refuse_live_name(s["alias"], s["addr"], allow_session=s["current"])
    settings = a.settings if a.settings is not None else (s["settings"] or os.environ.get("DAEMON_CLAUDE_SETTINGS", ""))
    effort = a.effort if a.effort is not None else (s["effort"] or os.environ.get("DAEMON_CLAUDE_EFFORT", ""))
    model = a.model if a.model is not None else s["model"]
    if a.resume:
        if not s["current"]:
            die("seat %s/%s has no session to resume — fill it fresh (without --resume)" % (s["group"], s["alias"]), EXIT_UNKNOWN)
        warn_resume_flags(a)
        resume_session(s, a.task, a.wait, lock, verb="filled")
        return
    preamble = render_preamble(s["group"], s["alias"], s["parent"]) if s["preamble"] else ""
    task_text = compose_task(a.task, s["brief"], preamble)
    cwd = s["cwd"] or os.getcwd()
    # The seat's cwd is already the worktree path when it had one, so no
    # --worktree on a re-fill: the fresh session runs where the seat lives.
    short, banner = run_claude_bg(claude_args(s["alias"], model, settings, effort) + [task_text], cwd, settings)
    if not short:
        sys.stderr.write("agora: fill failed — could not parse background id from:\n%s\n" % banner)
        sys.exit(1)
    meta_set(s["seat_id"], {"short": short, "status": "working", "task": task_text, "model": model,
                            "settings": settings, "effort": effort, "updated": now()})
    polled = poll_uuid(short)
    if not polled:
        meta_set(s["seat_id"], {"status": "error", "pending_short": short, "updated": now()})
        sys.stderr.write("agora: fill: session %s produced no usable session uuid (status=error, pending_short)\n" % short)
        sys.exit(1)
    uuid, state, runcwd = polled
    meta_set(s["seat_id"], {"current": uuid, "cwd": runcwd or cwd, "host": host_name(), "boot_id": boot_id(),
                            "turns": "1", "updated": now()}, remove=("pending_short",))
    status = "working"
    if state in TERMINAL:
        status = status_for_state(state)
        record_reply(uuid, s["seat_id"], state, s["alias"])
        meta_set(s["seat_id"], {"status": status, "updated": now()})
    lock.close()
    if a.wait:
        status = finish_turn(s["seat_id"], short, s["alias"], uuid)
    print("seat filled: %s/%s  [%s / %s]  status=%s  (fresh session; seat id %s)" % (
        s["group"], s["alias"], short, uuid, status, s["seat_id"][:8]))
    if a.wait:
        print_reply_block(s["seat_id"])


# ------------------------------------------------------- resume / wake / send


def warn_resume_flags(a):
    if any(getattr(a, k, None) is not None for k in ("model", "settings", "effort")):
        sys.stderr.write("agora: a resumed background session keeps its saved options; "
                         "--model/--settings/--effort ignored (use fill without --resume to change them)\n")


def resume_session(s, msg, wait, lock=None, verb="resumed"):
    """Process-level continuation of a seat's session.

    A live current turn is stopped first (`claude stop`), then exactly
    `claude --bg --resume <current> <msg>` runs the session in the background
    under the same id, in the seat's cwd, with THIS process's environment
    (gateway scrub applied per the seat's recorded route): the board pipeline
    prefixes the call with its run credentials and needs a fresh process to
    carry them — a socket frame cannot. NO other flag rides the resume: a
    background session keeps its saved options (-n, --permission-mode, --model,
    --settings, --effort), and any flag makes the harness start a COPY (observed
    live, v2.1.257). ONE resume per seat at a time (flock, released when this
    process dies): two concurrent resumes would start a copy. If the banner
    says a copy started, or the harness reports a different session id, the
    copy is stopped, the record is left untouched, and the command fails loudly.
    """
    refuse_codex(s)
    if not s["current"]:
        die("seat %s/%s is vacant — fill it with: agora fill %s/%s \"<task>\"" % (
            s["group"], s["alias"], s["group"], s["alias"]), EXIT_UNKNOWN)
    own_lock = lock is None
    if own_lock:
        lock = lifecycle_lock(s["group"], s["alias"])
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
    if row and normalize_state(row) in ("working", "blocked", "done", "done-blocked") and row.get("id"):
        # Release the live turn (idempotent — harmless if already stopped). A
        # row is host-local by construction; only a RECORDED short is gated on
        # the record's host identity, because shorts are reusable across boots.
        claude_stop(row["id"])
    elif not row and peer_for_session(cur) and s["short"] and identity_local(s["host"], s["boot_id"]):
        claude_stop(s["short"])
    prev_status = s["status"]
    short, banner = run_claude_bg(["--bg", "--resume", cur, msg], s["cwd"] or home_dir(), s["settings"])
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
    lock.close()
    status = "working"
    if state in TERMINAL:
        status = status_for_state(state)
        record_reply(uuid, s["seat_id"], state, s["alias"])
        meta_set(s["seat_id"], {"status": status, "updated": now()})
    if wait:
        status = finish_turn(s["seat_id"], short, s["alias"], uuid)
    print("%s %s/%s  [%s / %s]  via --bg --resume  status=%s  turns=%d" % (
        verb, s["group"], s["alias"], short, s["seat_id"], status, turns))
    if wait:
        print_reply_block(s["seat_id"])


def cmd_resume(a):
    s = resolve_seat(a.seat)
    warn_resume_flags(a)
    resume_session(s, a.msg, a.wait)


def wait_socket_turn(s, marker):
    """After a socket delivery: wait (bounded) for EVIDENCE the message landed —
    the marker in the target's transcript, or a busy harness row — then wait
    for the turn to end. No evidence within the bound is a failed wait, not a
    silent one: nothing is printed as a reply."""
    cur = s["current"]
    deadline = time.time() + float(os.environ.get("AGORA_ACK_TIMEOUT", "120"))
    seen = False
    while time.time() < deadline:
        if transcript_contains(cur, marker):
            seen = True
            break
        agents_refresh()
        row = harness_row(s)
        if row and normalize_state(row) in ("working", "blocked"):
            seen = True
            break
        time.sleep(poll_interval())
    if not seen:
        sys.stderr.write("agora: no evidence that %s/%s received the message within the ack window "
                         "(no transcript marker, session never busy) — not waiting for a reply\n" % (s["group"], s["alias"]))
        sys.exit(1)
    agents_refresh()
    row = harness_row(s)
    short = (row or {}).get("id") or s["short"]
    if not short:
        return "idle"
    return finish_turn(s["seat_id"], short, s["alias"], cur)


def cmd_wake(a):
    s = resolve_seat(a.seat)
    refuse_codex(s)
    if not s["current"]:
        die("seat %s/%s is vacant — fill it with: agora fill %s/%s \"<task>\"" % (
            s["group"], s["alias"], s["group"], s["alias"]), EXIT_UNKNOWN)
    frm = a.frm or "human"
    msg_id = uuidlib.uuid4().hex[:8]
    text = "[agora wake from %s id=%s]\n%s" % (frm, msg_id, a.msg)
    peer = peer_for_session(s["current"])
    sock = socket_path_of(peer) if peer else ""
    if peer and socket_ok(sock):
        send_frame(sock, text)
        meta_set(s["seat_id"], {"status": "working", "updated": now()})
        status = "working"
        if a.wait:
            status = wait_socket_turn(s, msg_id)
        print("woke %s/%s  [%s / %s]  via inbox socket  status=%s" % (
            s["group"], s["alias"], s["short"] or "-", s["seat_id"], status))
        if a.wait:
            print_reply_block(s["seat_id"])
        return
    resume_session(s, text, a.wait, verb="woke")


def cmd_send(a):
    frm = a.frm or "human"
    text = "[agora message from %s]\n%s" % (frm, a.msg)
    s = None
    try:
        s = resolve_seat(a.target)
    except SystemExit:
        s = None
    if s is not None:
        peer = peer_for_session(s["current"]) if s["current"] else None
        sock = socket_path_of(peer) if peer else ""
        if peer and socket_ok(sock):
            send_frame(sock, text)
            print("sent to %s/%s (%s)" % (s["group"], s["alias"], peer.get("name") or s["addr"]))
            return
        die("%s/%s is not live (%s) — use: agora wake %s/%s \"<msg>\"" % (
            s["group"], s["alias"], live_state(s), s["group"], s["alias"]), EXIT_UNKNOWN)
    peers = [p for p in live_name_holders(a.target) if socket_ok(socket_path_of(p))]
    if len(peers) == 1:
        send_frame(socket_path_of(peers[0]), text)
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
        # The recorded reply can still be stale/empty when the spawn watcher
        # gave up before the first turn finished — fall back to the transcript.
        print(reply_text(s["seat_id"]) or transcript_reply(cur, ref) or "(no reply yet)")


def sync_one(s):
    """Reconcile one seat's mirror status from the harness. Returns one word."""
    if s["engine"] == "codex":
        return "noop"
    if s["status"] not in ("working", "blocked"):
        return "noop"
    cur = s["current"] or s["seat_id"]
    agents_refresh()
    row = harness_row(s)
    if row is None:
        return "absent"
    state = normalize_state(row)
    if state in ("working", "blocked"):
        return "live"
    if state == "done":
        record_reply(cur, s["seat_id"], "done", s["alias"])
        meta_set(s["seat_id"], {"status": "idle", "updated": now()})
        return "idle"
    if state == "done-blocked":
        # An ended blocked-shape turn: the session is over and resumable; the
        # reply carries the pending question or the harness-prompt marker.
        record_reply(cur, s["seat_id"], "blocked", s["alias"])
        meta_set(s["seat_id"], {"status": "idle", "updated": now()})
        return "idle"
    if state in ("failed", "stopped", "error"):
        record_reply(cur, s["seat_id"], state, s["alias"])
        meta_set(s["seat_id"], {"status": "error", "updated": now()})
        return "error"
    return "live"  # unknown/new harness states: claim nothing, finalize nothing


def cmd_sync(a):
    if a.all or not a.seat:
        for s in seats():
            if s["status"] in ("working", "blocked"):
                print("%s/%s %s" % (s["group"], s["alias"], sync_one(s)))
        return
    print(sync_one(resolve_seat(a.seat)))


def cmd_mark(a):
    s = resolve_seat(a.seat)
    note = " ".join(a.note)
    meta_set(s["seat_id"], {"status": a.status, "updated": now(), "note": note})
    print("marked %s/%s [%s] -> %s%s" % (s["group"], s["alias"], s["seat_id"], a.status, ("  (%s)" % note) if note else ""))


def cmd_status(a):
    s = resolve_seat(a.seat)
    line = " ".join(a.line).strip()
    meta_set(s["seat_id"], {"now": line, "updated": now()})
    print("%s/%s now: %s" % (s["group"], s["alias"], line or "(cleared)"))


# ------------------------------------------------------------ retire / remove


def stop_session(s):
    """`claude stop` the seat's current turn when its identity is local.
    Never through a foreign short: shorts are host-local and reusable."""
    if s["short"] and s["engine"] != "codex" and identity_local(s["host"], s["boot_id"]):
        claude_stop(s["short"])


def worktree_note(s):
    if not s["worktree"]:
        return ""
    return "  NOTE: work is on branch worktree-%s — merge or remove its worktree yourself." % re.sub(
        r"[^a-zA-Z0-9._-]", "-", s["worktree"])


def unlink_seat_files(seat_id):
    for p in (meta_path(seat_id), reply_path(seat_id), err_path(seat_id),
              os.path.join(root(), seat_id + ".resume.lock")):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


def cmd_retire(a):
    s = resolve_seat(a.seat)
    stop_session(s)
    if s["current"]:
        hint = "agora fill %s/%s --resume \"<task>\"" % (s["group"], s["alias"])
    else:
        hint = "agora fill %s/%s \"<task>\"" % (s["group"], s["alias"])
    if a.purge:
        unlink_seat_files(s["seat_id"])
        print("purged %s/%s [%s] from the registry (session transcript left intact)%s" % (
            s["group"], s["alias"], s["seat_id"], worktree_note(s)))
    else:
        meta_set(s["seat_id"], {"status": "retired", "updated": now()})
        print("retired %s/%s [%s] (seat kept; re-fill with: %s)%s" % (
            s["group"], s["alias"], s["seat_id"], hint, worktree_note(s)))


def cmd_remove(a):
    s = resolve_seat(a.seat)
    stop_session(s)
    unlink_seat_files(s["seat_id"])
    print("removed %s/%s [%s] (board history kept)%s" % (s["group"], s["alias"], s["seat_id"], worktree_note(s)))


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
            d = {k: v for k, v in s.items() if k != "task"}
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
        d = {k: v for k, v in s.items() if k != "task"}
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
    frm = a.frm or os.environ.get("AGORA_ALIAS") or "human"
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
        rec = {"id": len(read_board(g)) + 1, **body}
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
        v = meta_get(s["seat_id"], a.field)
        print(v if isinstance(v, str) else json.dumps(v))
        return
    pairs = ([a.field] if a.field else []) + list(a.values)
    if not pairs or len(pairs) % 2 != 0:
        die("usage: agora meta set <seat> <field> <value> [<field> <value>...]")
    fields = {pairs[i]: pairs[i + 1] for i in range(0, len(pairs), 2)}
    meta_set(s["seat_id"], fields)
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
    sp.add_argument("--group", default=None)
    sp.add_argument("--parent", default="")
    sp.add_argument("--role", default="")
    sp.add_argument("--brief", default="")
    sp.add_argument("--cwd", default="")
    sp.add_argument("--worktree", default="")
    sp.add_argument("--addr", default="")
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
        did = migrate(explicit=True, quiet=True)
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
