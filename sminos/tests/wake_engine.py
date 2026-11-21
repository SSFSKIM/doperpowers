#!/usr/bin/env python3
"""The test engine (T2's plan, Interfaces §8): a `claude` for the suites,
first on PATH, that can be woken and pushed to, so that the argument vector,
the banner, the engine's notes, its records and `rm` are exercised where
patches of `run_claude_bg` and `poll_uuid` are not. Its behaviours are the
engine's as `docs/doperpowers/research/2026-11-17-sminos-channels/
wake-spike-2.md` measured them on 2.1.329; the shell stub of
run-sminos-tests.sh hands it a wake with no message, and the stop or the
removal of one of its jobs, so the two forms behave alike.

Its state is `$WAKE_ENGINE_STATE`: `jobs/<short>.json` (the job list's
entries, `claude agents --json --all`), `calls.log` (each call, `{argv,
cwd}`), `launches` (a count of the `--bg` launches entered), `inputs/<id>`
(every frame its inbox took, whole), `violations` (a resume that carried a
message, refused unless `accept-message` is set: from T2's M2 no launch
sminos makes carries one, and every suite's teardown fails on a
`violations` that is not empty), `helpers/<pid>` (its processes, each
naming its spec), `owned/<id>` (the worker it started for a session, known
from its start, before any public signal of it: its pid and spec, trusted
only while that pid's command line still names the spec, and removed by the
worker as it exits) and `ready/<pid>.<stage>` (a worker's
record and job written, its inbox listening).
The engine's own files are under the config dir (`CLAUDE_CONFIG_DIR`, else
`~/.claude`): `sessions/<pid>.json` (the record of a process), `jobs/<first
eight>/state.json` (a session's row) and `projects/<dir>/<id>.jsonl`.

- **A wake.** `--bg --resume <id> [flags]` starts a helper process that
  writes the record (`kind` `bg`, the directory, the name kept, its inbox),
  the job's entry and the row (`sessionId`, `cwd`, `respawnFlags`), and
  serves the inbox; the launch prints its banner once the record is there
  (E18). Flags with no row: the same id, the row written with them. Flags
  with a row: a copy and the note that the session keeps its saved options.
  No flag with a row: the same id and the note that it woke with them. A
  process that holds the session (a live record of it): a copy and the
  note of a session open elsewhere or running in the background, run under
  the settings' defaults. A bypass mode without the user settings'
  `skipDangerousModePermissionPrompt` is refused (E22); `--output-style`
  fails the worker before it starts (E12, E20). A message after the id runs
  as the first turn and renames the session (E17), only under `accept-message`.
- **A turn.** Each frame its inbox takes is a prompt row holding the
  frame's text (in the mode it runs under), the record `busy`, then an
  assistant row (`reply to <the frame's id=…>`, with its model and a
  `requestId`) and the record `idle`. A frame naming another `session_id`
  is refused (wake-spike-2.md §16).
- **`stop <short>`** ends the helper and leaves the row; **`rm <short>`**
  removes the row and the job, stopping a live helper.

Switches, each a file in the state directory (its content a value where one
is taken): `accept-message`; `held` (`open` or `running`: either note, and a
copy); `silent-copy`; `row-elsewhere` (the engine keeps its rows in the
state directory, where sminos does not look); `fail-before-start`;
`fail-job` (a job that fails otherwise, its row kept); `rm-refuses` (the
shorts it names, every one when empty); `late-inbox` and `late-process`
(seconds); `agents-fail`; `no-banner` (seconds the launch sleeps, its
process started, before it exits with nothing printed); `barrier` (each
launch waits until the file is removed; `launches` counts those entered);
`no-reply`, `reply-delay` (seconds), `reply-reversed` (two frames' whole
turns run the second first: its prompt and reply, then the first's); `bridge` (the helper serves sminos's bridge
socket for the session, a signal of E5's beside its record and its job); `spare` (each launch also leaves a
session claimed from the engine's spare pool with no prompt yet, as 2.1.330 does: a helper whose record says
`"spare": true` under a session id of its own, with an inbox and no job in the list, which drops the flag at its
first frame; `spare(cwd)` starts one for a test directly).
"""
import contextlib
import fcntl
import glob
import json
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.realpath(__file__)
VALUED = frozenset(("--permission-mode", "--model", "--effort", "--settings", "--output-style", "-n", "--name",
                    "--fallback-model", "--agent", "--append-system-prompt", "--system-prompt", "--session-id",
                    "--worktree", "-w", "--resume", "-r", "--resume-session-at", "--setting-sources"))
MANY = frozenset(("--add-dir", "--mcp-config", "--allowedTools", "--allowed-tools", "--disallowedTools",
                  "--disallowed-tools", "--plugin-dir", "--tools"))
BYPASS_REFUSAL = ("--bg with bypassPermissions requires accepting the disclaimer first. Run `claude "
                  "--dangerously-skip-permissions` once interactively.")
IDLE = " (idle — send a prompt to start)"


# ------------------------------------------------------------ places


def state():
    s = os.environ.get("WAKE_ENGINE_STATE", "")
    if not s:
        sys.exit("wake_engine: WAKE_ENGINE_STATE is not set")
    return s


def config():
    return os.path.abspath(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR")
                                              or os.path.join(os.path.expanduser("~"), ".claude")))


def sminos_home():
    return os.environ.get("SMINOS_HOME") or os.path.join(os.path.expanduser("~"), ".claude", "sminos")


def switch(name, st=None):
    """The switch's content ("" when set with none), or None when it is not set."""
    try:
        with open(os.path.join(st or state(), name)) as f:
            return f.read().strip()
    except OSError:
        return None


def seconds(name, default=0.0):
    v = switch(name)
    try:
        return float(v) if v else default
    except ValueError:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def append(path, line):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(line + "\n")


@contextlib.contextmanager
def locked(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def count(name, st=None):
    path = os.path.join(st or state(), name)
    with locked(path + ".lock"):
        n = launches(st or state(), name) + 1
        with open(path, "w") as f:
            f.write(str(n))
    return n


def launches(st, name="launches"):
    """How many `--bg` launches the engine has entered (a test's counter)."""
    try:
        with open(os.path.join(st, name)) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def violations(st):
    """The resumes that carried a message (a suite's teardown fails on any)."""
    try:
        with open(os.path.join(st, "violations")) as f:
            return [line for line in f if line.strip()]
    except OSError:
        return []


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True
    return True


def job_path(short):
    return os.path.join(state(), "jobs", short + ".json")


def rows_dir():
    return os.path.join(state(), "rows") if switch("row-elsewhere") is not None else os.path.join(config(), "jobs")


def row_path(sid):
    return os.path.join(rows_dir(), sid[:8], "state.json")


def transcript_of(sid):
    hits = glob.glob(os.path.join(glob.escape(config()), "projects", "*", sid + ".jsonl"))
    return max(hits, key=os.path.getmtime) if hits else ""


def transcript_for(sid, cwd):
    return os.path.join(config(), "projects", re.sub(r"[^A-Za-z0-9]", "-", cwd), sid + ".jsonl")


def settings():
    d = read_json(os.path.join(config(), "settings.json"))
    return d if isinstance(d, dict) else {}


# ------------------------------------------------------------ the argument vector


def parse(argv):
    """(the session resumed, the option tokens but --bg and --resume's, the positionals)."""
    resume, flags, positional, i = "", [], [], 0
    while i < len(argv):
        tok = argv[i]
        i += 1
        if tok == "--":
            positional += argv[i:]
            break
        if not tok.startswith("-") or tok == "-":
            positional.append(tok)
            continue
        name, eq, _ = tok.partition("=")
        if name in ("--resume", "-r"):
            if eq:
                resume = tok.split("=", 1)[1]
            elif i < len(argv):
                resume, i = argv[i], i + 1
            continue
        if name == "--bg":
            continue
        flags.append(tok)
        if eq:
            continue
        if name in MANY:
            while i < len(argv) and not argv[i].startswith("-"):
                flags.append(argv[i])
                i += 1
        elif name in VALUED and i < len(argv):
            flags.append(argv[i])
            i += 1
    return resume, flags, positional


def has_positional(argv):
    """Whether a launch's arguments carry a message (a positional)."""
    return bool(parse([a for a in argv if a != "--has-positional"])[2])


def value(flags, name):
    out = ""
    for i, tok in enumerate(flags):
        if tok == name and i + 1 < len(flags):
            out = flags[i + 1]
        elif tok.startswith(name + "="):
            out = tok.split("=", 1)[1]
    return out


def without(flags, name):
    out, skip = [], False
    for tok in flags:
        if skip:
            skip = False
            continue
        if tok == name:
            skip = True
            continue
        if tok.startswith(name + "="):
            continue
        out.append(tok)
    return out


def names(flags):
    return [t.split("=", 1)[0] for t in flags if t.startswith("-")]


def mode_of(flags, defaults=False):
    """The mode a process runs under, as its transcript writes it (`manual` as `default`, E24)."""
    mode = "" if defaults else value(flags, "--permission-mode")
    if not mode and not defaults and "--dangerously-skip-permissions" in flags:
        mode = "bypassPermissions"
    if not mode:
        mode = ((settings().get("permissions") or {}).get("defaultMode")) or "default"
    return "default" if mode == "manual" else mode


def model_of(flags, defaults=False):
    return ("" if defaults else value(flags, "--model")) or settings().get("model") or "claude-test-default"


def bypass(flags):
    return value(flags, "--permission-mode") == "bypassPermissions" or any(
        t in flags for t in ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions"))


# ------------------------------------------------------------ the launch


def owned_path(sid):
    return os.path.join(state(), "owned", sid)


def helper_pid(pid, spec_path):
    """`pid` while it is the helper this engine started on `spec_path` (its
    command line names both), else 0: a pid alone may since have been reused
    by any process of the machine, which a stop must never signal."""
    try:
        pid = int(pid)
        args = subprocess.run(["ps", "-ww", "-o", "args=", "-p", str(pid)], capture_output=True,
                              text=True, timeout=10).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    return pid if spec_path and "--helper" in args and spec_path in args else 0


def owned_pid(sid):
    """The engine's own worker for the session, while it runs: known to the
    engine from its start (Popen), whatever its public signals (the record,
    the job's pid) show yet, as a late process holds them back."""
    try:
        with open(owned_path(sid)) as f:
            pid, _, spec_path = f.read().strip().partition(" ")
    except OSError:
        return 0
    return helper_pid(pid, spec_path)


def held_by(sid):
    """The kind of a live process that holds the session ("interactive" or "bg"), else ""."""
    if owned_pid(sid):
        return "bg"
    for p in glob.glob(os.path.join(glob.escape(config()), "sessions", "*.json")):
        rec = read_json(p)
        if isinstance(rec, dict) and rec.get("sessionId") == sid and pid_alive(rec.get("pid")) \
                and not recycled(rec):
            return str(rec.get("kind") or "interactive")
    return ""


def recycled(rec):
    """A record whose `procStart` is not its live pid's start (a suite's
    recycled pid): the process it names is another, which holds nothing."""
    start = " ".join(str(rec.get("procStart") or "").split())
    if not start:
        return False
    try:
        now = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(rec["pid"]))], capture_output=True, text=True,
                             timeout=10, env=dict(os.environ, LC_ALL="C", LANG="C")).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return " ".join(now.split()) != start


def title_of(path):
    name = ""
    try:
        with open(path) as f:
            for line in f:
                if '"custom-title"' in line:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("type") == "custom-title" and isinstance(r.get("customTitle"), str):
                        name = r["customTitle"]
    except OSError:
        pass
    return name


def launch(argv):
    st = state()
    count("launches")
    if switch("barrier") is not None:
        end = time.monotonic() + 60
        while switch("barrier") is not None and time.monotonic() < end:
            time.sleep(0.01)
    resume, flags, positional = parse(argv)
    message = positional[-1] if positional else None
    if positional and resume and switch("accept-message") is None:
        append(os.path.join(st, "violations"), json.dumps({"argv": argv, "cwd": os.getcwd()}))
        print("wake_engine: a resume carried a message: %r" % positional, file=sys.stderr)
        return 2
    cwd = os.getcwd()
    with locked(os.path.join(st, "launch.lock")):
        if not resume:
            sid = str(uuid.uuid4())
            path = transcript_for(sid, cwd)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "a").close()
            return start(sid, flags, flags, cwd, path, message, row=None, note="")
        path = transcript_of(resume)
        if not path:
            print("No conversation found with session ID: %s" % resume, file=sys.stderr)
            return 1
        if bypass(flags) and settings().get("skipDangerousModePermissionPrompt") is not True:
            print(BYPASS_REFUSAL, file=sys.stderr)
            return 1
        held = switch("held")
        kind = held_by(resume) if held is None else ("interactive" if held == "open" else "bg")
        row = read_json(row_path(resume))
        row = row if isinstance(row, dict) and row.get("sessionId") == resume else None
        copy_sid = str(uuid.uuid4())
        if kind:
            note = ("note: session %s is open in another Claude Code process, so this started a copy as %s. The "
                    "original conversation is unchanged." if kind == "interactive" else
                    "note: session %s is already running in the background, so this started a copy as %s. "
                    "`claude attach %s` opens the original.") % ((resume[:8], copy_sid[:8]) + (
                        () if kind == "interactive" else (resume[:8],)))
            return copy(resume, copy_sid, flags, [], cwd, path, message, note, defaults=True)
        if switch("silent-copy") is not None:
            return copy(resume, copy_sid, flags, flags, cwd, path, message, "")
        if row is not None and flags:
            note = ("note: background session %s keeps its own saved options, so the flags you passed started a "
                    "copy as %s. Without flags, the same command continues %s itself."
                    % (resume[:8], copy_sid[:8], resume[:8]))
            return copy(resume, copy_sid, flags, flags, cwd, path, message, note)
        if row is not None:
            run_with = [t for t in row.get("respawnFlags") or [] if isinstance(t, str)]
            note = "note: woke session %s with its saved options (%s)." % (resume[:8], ", ".join(names(run_with)))
            return start(resume, run_with, run_with, row.get("cwd") or cwd, path, message, row=row, note=note)
        return start(resume, flags, flags, cwd, path, message, row=None, note="")


def copy(original, sid, flags, run_with, cwd, path, message, note, defaults=False):
    dest = transcript_for(sid, cwd)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(path, "rb") as src, open(dest, "wb") as out:
        out.write(src.read())
    return start(sid, flags, run_with, cwd, dest, message, row=None, note=note, defaults=defaults)


def start(sid, flags, run_with, cwd, path, message, row, note, defaults=False):
    """The job of `sid` started: its row, its entry, its process; the banner once its record is there."""
    short = sid[:8]
    name = value(flags, "-n") or value(flags, "--name")
    source = "user" if name else ""
    if message is not None:
        name, source = message[:40], "auto"
    if not name and row is not None and row.get("name"):
        name, source = row["name"], row.get("nameSource") or "user"
    if not name:
        name = title_of(path)
        source = "user" if name else "derived"
    name = name or short
    failing = switch("fail-before-start") is not None or "--output-style" in names(flags)
    if row is None:
        row = {"sessionId": sid, "resumeSessionId": sid, "cwd": cwd, "respawnFlags": list(run_with),
               "createdAt": int(time.time() * 1000)}
    row = dict(row, state="working", detail=IDLE.strip(" ()") if message is None else "", name=name,
               nameSource=source, updatedAt=int(time.time() * 1000))
    if failing:
        row["respawnFlags"] = without(row["respawnFlags"], "--output-style")
        row.update(state="failed", detail="exit 1 before init — error: unknown option '--output-style'")
    elif switch("fail-job") is not None:
        row.update(state="failed", detail="the worker exited with code 1")
    write_json(row_path(sid), row)
    entry = {"id": short, "sessionId": sid, "kind": "background", "name": name, "cwd": row["cwd"],
             "state": "working", "status": ""}
    if failing or switch("fail-job") is not None:
        write_json(job_path(short), dict(entry, state="failed"))
        print("backgrounded · %s%s" % (short, IDLE if message is None else ""))
        if note:
            print(note, file=sys.stderr)
        return 0
    write_json(job_path(short), entry)
    spec = {"sid": sid, "short": short, "cwd": row["cwd"], "name": name, "nameSource": source,
            "mode": mode_of(run_with, defaults), "model": model_of(run_with, defaults), "transcript": path,
            "message": message, "late_inbox": seconds("late-inbox"), "late_process": seconds("late-process"),
            "bridge": switch("bridge") is not None, "state": state()}
    spec_path = os.path.join(state(), "spec-%s.json" % uuid.uuid4().hex[:8])
    write_json(spec_path, spec)
    with open(os.path.join(state(), "helper.err"), "a") as err:
        proc = subprocess.Popen([sys.executable, "-B", HERE, "--helper", spec_path], cwd=row["cwd"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                                start_new_session=True, close_fds=True)
    for d in ("owned", "helpers"):
        os.makedirs(os.path.join(state(), d), exist_ok=True)
    with open(owned_path(sid), "w") as f:
        f.write("%d %s" % (proc.pid, spec_path))
    with open(os.path.join(state(), "helpers", str(proc.pid)), "w") as f:
        f.write(spec_path)
    # The banner once the process is ready (E18): its record, its job's pid and its inbox listening; a late
    # switch breaks that order on purpose (late-inbox: the record only; late-process: nothing).
    stage = None if spec["late_process"] else ("record" if spec["late_inbox"] else "inbox")
    if stage:
        mark = os.path.join(state(), "ready", "%d.%s" % (proc.pid, stage))
        end = time.monotonic() + 15
        while not os.path.exists(mark) and time.monotonic() < end and proc.poll() is None:
            time.sleep(0.005)
        if not os.path.exists(mark):
            print("Error: the background session did not start", file=sys.stderr)
            return 1
    hang = switch("no-banner")
    if hang is not None:
        time.sleep(float(hang) if hang else 600)
        return 1
    if switch("spare") is not None:
        start_spare(row["cwd"])
    label = " · %s" % name if note.startswith("note: woke") else ""
    print("backgrounded · %s%s%s" % (short, label, IDLE if message is None else ""))
    if note:
        print(note, file=sys.stderr)
    return 0


def record_path(pid):
    return os.path.join(config(), "sessions", "%d.json" % pid)


def spare(cwd):
    """A session claimed from the spare pool with no prompt yet (2.1.330: a
    claim the supervisor logs as `(spare)`): its helper writes a record with
    `"spare": true` under a session id of its own, kind `bg`, an inbox and
    no job entry, and drops the flag at its first frame, which runs a turn
    in that session. (sid, pid) once its inbox listens, started through a
    process of the engine's own, so the helper is no child of the caller's
    (a test's), as a launch's is not."""
    out = subprocess.run([sys.executable, "-B", HERE, "--spare", cwd], capture_output=True, text=True, timeout=30,
                         check=True).stdout.split()
    return out[0], int(out[1])


def start_spare(cwd):
    """spare's work, in the engine's process (a launch's, or `--spare`'s)."""
    sid = str(uuid.uuid4())
    spec = {"sid": sid, "short": sid[:8], "cwd": cwd, "name": sid[:8], "nameSource": "", "mode": "auto",
            "model": "claude-spare", "transcript": transcript_for(sid, cwd), "message": None, "late_inbox": 0,
            "late_process": 0, "bridge": False, "spare": True, "state": state()}
    spec_path = os.path.join(state(), "spec-%s.json" % uuid.uuid4().hex[:8])
    write_json(spec_path, spec)
    for d in ("helpers", "inputs"):
        os.makedirs(os.path.join(state(), d), exist_ok=True)
    with open(os.path.join(state(), "helper.err"), "a") as err:
        proc = subprocess.Popen([sys.executable, "-B", HERE, "--helper", spec_path], cwd=cwd,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                                start_new_session=True, close_fds=True)
    with open(os.path.join(state(), "helpers", str(proc.pid)), "w") as f:
        f.write(spec_path)
    mark = os.path.join(state(), "ready", "%d.inbox" % proc.pid)
    end = time.monotonic() + 15
    while not os.path.exists(mark) and time.monotonic() < end and proc.poll() is None:
        time.sleep(0.005)
    return sid, proc.pid


# ------------------------------------------------------------ the process


class Helper:
    def __init__(self, spec, spec_path):
        self.spec = spec
        self.spec_path = spec_path
        self.sid = spec["sid"]
        self.pid = os.getpid()
        self.st = spec["state"]
        self.record = record_path(self.pid)
        self.sock = self.short_path(os.path.join(self.st, "s%d.sock" % self.pid), "we%d.sock" % self.pid)
        self.bridge = os.path.join(sminos_home(), "bridge", self.sid + ".sock")
        self.frames = queue.Queue()
        self.lock = threading.Lock()
        self.turn = 0

    @staticmethod
    def short_path(path, name):
        return path if len(path) < 100 else os.path.join(tempfile.gettempdir(), name)

    def entry(self, **fields):
        with self.lock:
            path = os.path.join(self.st, "jobs", self.spec["short"] + ".json")
            e = read_json(path)
            if isinstance(e, dict) and e.get("sessionId") == self.sid:
                e.update(fields)
                write_json(path, e)

    def status(self, status):
        with self.lock:
            rec = read_json(self.record)
            if isinstance(rec, dict):
                rec["status"] = status
                write_json(self.record, rec)

    def unspare(self):
        """A spare's first frame makes it a session like any (2.1.330): the flag dropped, its pid, id and inbox
        kept."""
        self.spec["spare"] = False
        with self.lock:
            rec = read_json(self.record)
            if isinstance(rec, dict):
                rec.pop("spare", None)
                write_json(self.record, rec)

    def ready(self, stage):
        append(os.path.join(self.st, "ready", "%d.%s" % (self.pid, stage)), "")

    def cleanup(self, *_):
        owned = os.path.join(self.st, "owned", self.sid)
        try:
            with open(owned) as f:
                if f.read().strip() == "%d %s" % (self.pid, self.spec_path):
                    os.unlink(owned)
        except OSError:
            pass
        for p in (self.record, self.sock, self.bridge, os.path.join(self.st, "helpers", str(self.pid)),
                  os.path.join(self.st, "ready", "%d.record" % self.pid),
                  os.path.join(self.st, "ready", "%d.inbox" % self.pid)):
            try:
                if p != self.bridge or self.spec.get("bridge"):
                    os.unlink(p)
            except OSError:
                pass
        os._exit(0)

    def run(self):
        signal.signal(signal.SIGTERM, self.cleanup)
        late = self.spec.get("late_process") or 0
        if late:
            time.sleep(late)
        write_json(self.record, {"pid": self.pid, "sessionId": self.sid, "cwd": self.spec["cwd"], "kind": "bg",
                                 "name": self.spec["name"], "nameSource": self.spec["nameSource"],
                                 "messagingSocketPath": self.sock, "status": "idle", "jobId": self.spec["short"],
                                 "startedAt": int(time.time() * 1000), "version": "wake-engine",
                                 **({"spare": True} if self.spec.get("spare") else {})})
        self.entry(pid=self.pid, state="blocked", status="idle")
        self.ready("record")
        threading.Thread(target=self.turns, daemon=True).start()
        if self.spec.get("message") is not None:
            self.frames.put({"type": "user", "message": {"role": "user", "content": self.spec["message"]},
                             "launch": True})
        if self.spec.get("bridge"):
            self.serve_bridge()
        if self.spec.get("late_inbox"):
            time.sleep(self.spec["late_inbox"])
        srv = self.listener(self.sock)
        self.ready("inbox")
        self.serve(srv)

    def listener(self, path):
        try:
            os.unlink(path)
        except OSError:
            pass
        here = os.getcwd()
        os.chdir(os.path.dirname(path))   # bound by its name: a socket's path is limited to about 104 bytes
        try:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(os.path.basename(path))
            srv.listen(16)
        finally:
            os.chdir(here)
        return srv

    def serve_bridge(self):
        os.makedirs(os.path.dirname(self.bridge), exist_ok=True)
        srv = self.listener(self.bridge)

        def accept():
            while True:
                c, _ = srv.accept()
                c.close()
        threading.Thread(target=accept, daemon=True).start()

    def serve(self, srv):
        srv.settimeout(0.5)
        born = time.monotonic()
        life = float(os.environ.get("WAKE_ENGINE_MAX_LIFE") or 900)
        while os.path.isdir(self.st) and time.monotonic() - born < life:
            try:
                c, _ = srv.accept()
            except socket.timeout:
                continue
            c.settimeout(5)
            buf = b""
            try:
                while True:
                    chunk = c.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
            except OSError:
                pass
            c.close()
            if not buf:
                continue   # a liveness probe
            with open(os.path.join(self.st, "inputs", self.sid), "ab") as f:
                f.write(buf if buf.endswith(b"\n") else buf + b"\n")
            for line in buf.splitlines():
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                if isinstance(frame, dict) and frame.get("session_id") not in (None, self.sid):
                    continue   # the engine refuses a frame addressed to another session
                if isinstance(frame, dict):
                    self.frames.put(frame)
        self.cleanup()

    def text_of(self, frame):
        c = (frame.get("message") or {}).get("content")
        if isinstance(c, list):
            return "".join(str(p.get("text") or "") for p in c if isinstance(p, dict))
        return str(c or "")

    def write(self, row):
        row.setdefault("sessionId", self.sid)
        row.setdefault("cwd", self.spec["cwd"])
        row.setdefault("uuid", str(uuid.uuid4()))
        row.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()))
        os.makedirs(os.path.dirname(self.spec["transcript"]), exist_ok=True)
        with open(self.spec["transcript"], "a") as f:
            f.write(json.dumps(row) + "\n")

    def prompt(self, frame):
        text = self.text_of(frame)
        row = {"type": "user", "permissionMode": self.spec["mode"], "message": {"role": "user", "content": text}}
        if not frame.get("launch"):
            row.update(isMeta=True, origin={"kind": "peer"})
        self.write(row)
        return text

    def reply(self, text):
        self.turn += 1
        m = re.search(r"\bid=([0-9A-Za-z_-]+)\]", text)
        said = "reply to %s" % (m.group(1) if m else text[:60])
        self.write({"type": "assistant", "requestId": "req_%s_%d" % (self.spec["short"], self.turn),
                    "message": {"id": "msg_%s_%d" % (self.spec["short"], self.turn), "model": self.spec["model"],
                                "role": "assistant", "type": "message",
                                "content": [{"type": "text", "text": said}]}})

    def turns(self):
        while True:
            frame = self.frames.get()
            self.status("busy")
            self.entry(state="working", status="busy")
            if switch("reply-reversed", self.st) is not None:
                try:
                    second = self.frames.get(timeout=10)
                except queue.Empty:
                    second = None
                if second is not None:
                    self.reply(self.prompt(second))
                self.reply(self.prompt(frame))
                self.status("idle")
                self.entry(state="done", status="idle")
                continue
            text = self.prompt(frame)
            if self.spec.get("spare"):
                self.unspare()
            if switch("no-reply", self.st) is not None:
                pass
            else:
                delay = switch("reply-delay", self.st)
                if delay:
                    time.sleep(float(delay))
                self.reply(text)
            self.status("idle")
            self.entry(state="done", status="idle")


# ------------------------------------------------------------ the other verbs


def agents():
    if switch("agents-fail") is not None:
        print("wake_engine: agents unavailable", file=sys.stderr)
        return 1
    out = [e for e in (read_json(p) for p in sorted(glob.glob(os.path.join(glob.escape(state()), "jobs", "*.json"))))
           if isinstance(e, dict)]
    print(json.dumps(out))
    return 0


def stop_helper(entry):
    """End the session's helper: only through the engine's private, verified
    ownership; the job's public pid is evidence a test may fabricate."""
    pid = owned_pid(str(entry.get("sessionId") or ""))
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
        end = time.monotonic() + 10
        while pid_alive(pid) and time.monotonic() < end:
            time.sleep(0.01)
    try:
        os.unlink(owned_path(str(entry.get("sessionId") or "")))
    except OSError:
        pass


def stop(short):
    entry = read_json(job_path(short))
    if not isinstance(entry, dict):
        print("no background session %s" % short, file=sys.stderr)
        return 1
    stop_helper(entry)
    entry.pop("pid", None)
    entry.update(state="stopped", status="")
    write_json(job_path(short), entry)
    print("stopped " + short)
    return 0


def rm(short):
    entry = read_json(job_path(short))
    if not isinstance(entry, dict):
        print("no background session %s" % short, file=sys.stderr)
        return 1
    refused = switch("rm-refuses")
    if refused is not None and (not refused or short in refused.split()):
        print("could not remove %s" % short, file=sys.stderr)
        return 1
    stop_helper(entry)
    for d in (os.path.join(config(), "jobs"), os.path.join(state(), "rows")):
        try:
            os.unlink(os.path.join(d, short, "state.json"))
            os.rmdir(os.path.join(d, short))
        except OSError:
            pass
    os.unlink(job_path(short))
    print("removed " + short)
    return 0


def stop_all(st):
    """Every process the engine of state directory `st` started, ended (a test's teardown)."""
    for p in glob.glob(os.path.join(glob.escape(st), "helpers", "*")):
        try:
            with open(p) as f:
                spec_path = f.read().strip()
            pid = helper_pid(os.path.basename(p), spec_path)
            if not pid:
                continue
            os.kill(pid, signal.SIGTERM)
        except (ValueError, OSError):
            continue
        end = time.monotonic() + 5
        while pid_alive(pid) and time.monotonic() < end:
            time.sleep(0.01)
        if helper_pid(pid, spec_path):   # still its own: the helper may have exited and its pid been reused
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def main(argv):
    if argv[:1] == ["--helper"]:
        Helper(read_json(argv[1]), argv[1]).run()
        return 0
    if argv[:1] == ["--spare"]:
        print("%s %d" % start_spare(argv[1]))
        return 0
    if argv[:1] == ["--has-positional"]:
        return 0 if has_positional(argv[1:]) else 1
    os.makedirs(os.path.join(state(), "inputs"), exist_ok=True)
    append(os.path.join(state(), "calls.log"), json.dumps({"argv": argv, "cwd": os.getcwd()}))
    if argv[:1] == ["agents"]:
        return agents()
    if argv[:1] == ["stop"] and len(argv) > 1:
        return stop(argv[1])
    if argv[:1] == ["rm"] and len(argv) > 1:
        return rm(argv[1])
    if "--bg" in argv:
        return launch(argv)
    print("wake_engine: unhandled invocation: %s" % " ".join(argv), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
