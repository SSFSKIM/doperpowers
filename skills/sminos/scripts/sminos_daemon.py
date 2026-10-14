#!/usr/bin/env python3
"""sminos_daemon — the mirror and the daemon (§8 of the .smns design).

A project whose .smns names a remote keeps its log/ as a git working tree of
that remote: the MIRROR. Every machine writes only files named after itself,
so integrating the remote never conflicts; `machines/<machine>.json` claims a
name for one instance (`$SMINOS_HOME/daemon/machine.json`), and a daemon that finds
its name claimed by another instance refuses to run.

The sync invariant: local events are committed before anything from the
remote is integrated. `log/.sync.lock` is taken shared by every appender and
exclusive here, for the phases that touch the working tree and for nothing
else — the fetch and the push wait on the network outside it, each bounded,
so an unreachable remote never stalls a `say` or a Stop export. The
integration phase commits whatever was appended during the fetch and merges
under one hold. One sync per project at a time (`log/.sync-op.lock`).

The daemon is one process per machine. `daemon tick` is one iteration over
every project known here, each in the order of §8:

  1. integrate   (mirrored projects) commit, fetch, merge — the daemon
                 attaches a mirror it has not seen before
  2. reconcile   as every reading verb does
  3. publish     (mirrored projects) `state` once a word has held for two
                 ticks, the first at once; (every project) `renamed` on a
                 harness rename
  4. deliver     everything owed to a local member, through deliver_next
  5. push        (mirrored projects) commit what the tick appended, push
  6. derive      once an hour, `derive --all` as a child it does not wait on

`daemon run` loops the tick; `install` writes the launchd agent (it loads
nothing); `status` prints the last tick per project.
"""

import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid as uuidlib
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

# The fetch and the push wait on the network, never under .sync.lock, each at
# most this long; SMINOS_GIT_TIMEOUT overrides it (tests).
GIT_TIMEOUT = 30
# A push the remote rejected because it moved is retried, after another fetch
# and integration, this many times.
PUSH_RETRIES = 3
# `derive --all` runs at most this often; SMINOS_DERIVE_EVERY overrides it in
# seconds, and a value of 0 or less turns derivation off.
DERIVE_EVERY = 3600
LABEL = "com.doperpowers.sminos-daemon"
PLIST_TEMPLATE = os.path.join(sminos.SCRIPT_DIR, "..", "references", "sminos-daemon.plist")
REJECTED_RE = re.compile(r"\[rejected\]|non-fast-forward|fetch first|\[remote rejected\].*(?:stale|lock)")
_DERIVE = None  # the derivation child this process started, while it may run


class SyncFailed(Exception):
    """A sync phase failed: logged, and the tick goes on with the stale mirror."""


class MachineClaimed(Exception):
    """This machine's name is claimed by another instance: the daemon refuses
    to run (two machines under one name would write the same files)."""


def git_timeout():
    try:
        return float(os.environ.get("SMINOS_GIT_TIMEOUT") or GIT_TIMEOUT)
    except ValueError:
        return GIT_TIMEOUT


def git(log, *args, timeout=None):
    """git -C log …, never prompting, never signing. In its own process group:
    a timeout kills git and whatever transport it started (an ssh that hangs
    would otherwise hold the pipes open past the bound)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(k, None)
    p = subprocess.Popen(["git", "-c", "commit.gpgsign=false", "-C", log, *args], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                         start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        raise SyncFailed("git %s in %s timed out after %ds" % (args[0], log, timeout))
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def said(p):
    return " ".join((p.stderr or p.stdout or "").split())[:300]


def git_ok(log, *args, timeout=None):
    """A git step the sync cannot go on without."""
    p = git(log, *args, timeout=timeout)
    if p.returncode != 0:
        raise SyncFailed("git %s in %s failed: %s" % (" ".join(args[:2]), log, said(p)))
    return p


def daemon_path(name):
    """A file of this machine's daemon, under $SMINOS_HOME/daemon/ — never at
    the root, whose *.json are the seat records (sminos and the board scripts
    glob them)."""
    d = os.path.join(sminos.root(), "daemon")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return os.path.join(d, name)


def log_dir(project):
    return os.path.dirname(sminos.writer_path(project, sminos.writer_id()))


def lock(log, name, exclusive=True):
    return sminos.flocked(os.path.join(log, name), exclusive)


# ------------------------------------------------------------- the instance


def instance_id():
    """This machine's random instance id, written on first use
    ($SMINOS_HOME/daemon/machine.json)."""
    path = daemon_path("machine.json")
    for _ in range(2):
        try:
            with open(path) as f:
                got = str(json.load(f).get("instance") or "")
            if got:
                return got
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError):
            break
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        mine = str(uuidlib.uuid4())
        with os.fdopen(fd, "w") as f:
            json.dump({"instance": mine}, f)
            f.write("\n")
        return mine
    raise SyncFailed("%s is unreadable: fix or remove it" % path)


def claim_of(text):
    try:
        return str(json.loads(text).get("instance") or "")
    except (ValueError, AttributeError):
        return ""


def check_claim(log):
    """Refuse when the remote, or this log, holds this machine's name under
    another instance id."""
    name, mine = sminos.host_name(), instance_id()
    theirs = git(log, "show", "origin/main:machines/%s.json" % name)
    held = claim_of(theirs.stdout) if theirs.returncode == 0 else ""
    if not held:
        try:
            with open(os.path.join(log, "machines", name + ".json")) as f:
                held = claim_of(f.read())
        except OSError:
            pass
    if held and held != mine:
        raise MachineClaimed(
            "the machine name %s is claimed by another instance (%s) in %s — two machines under one name would "
            "write the same files, so this daemon refuses to run. Give this machine its own name (DAEMON_HOST), or, "
            "if the claim is this machine's own from an earlier $SMINOS_HOME, remove machines/%s.json from the "
            "remote" % (name, held[:8], log, name))


def write_claim(log):
    path = os.path.join(log, "machines", sminos.host_name() + ".json")
    data = {"machine": sminos.host_name(), "instance": instance_id()}
    try:
        with open(path) as f:
            if json.load(f) == data:
                return
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    sminos.write_json(path, data)


# ------------------------------------------------------------- the mirror


def commit_log(log, message):
    """Commit whatever the appenders wrote; the caller holds `.sync.lock`
    exclusive. A first commit is made even with nothing to commit."""
    git_ok(log, "add", "-A")
    if git(log, "rev-parse", "--verify", "-q", "HEAD").returncode == 0 and \
            not git_ok(log, "status", "--porcelain").stdout.strip():
        return
    git_ok(log, "commit", "-q", "--allow-empty", "-m", message)


def attached(project, log):
    if not os.path.isdir(os.path.join(log, ".git")):
        return False
    url = git(log, "remote", "get-url", "origin")
    return url.returncode == 0 and url.stdout.strip() == project.remote


def prepare(project, log):
    """Adopt log/ as a working tree of the remote: init when it is not yet a
    repository, the first commit, the remote. The caller holds .sync-op.lock."""
    with lock(log, ".sync.lock"):
        if not os.path.isdir(os.path.join(log, ".git")):
            git_ok(log, "init", "-q", "-b", "main")
        git_ok(log, "config", "user.name", "sminos")
        git_ok(log, "config", "user.email", "sminos@%s" % sminos.host_name())
        exclude = os.path.join(log, ".git", "info", "exclude")
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "w") as f:
            f.write("# locks are this machine's, never the mirror's\n*.lock\n")
        commit_log(log, "sminos: %s attaches %s" % (sminos.host_name(), project.name))
        if git(log, "remote", "get-url", "origin").returncode == 0:
            git_ok(log, "remote", "set-url", "origin", project.remote)
        else:
            git_ok(log, "remote", "add", "origin", project.remote)


def fetch(log):
    git_ok(log, "fetch", "-q", "origin", timeout=git_timeout())


def integrate(project, log):
    """The integration phase, under one exclusive hold: the claim checked,
    what was appended during the fetch committed, then the remote merged —
    never releasing between the two, so the merge never meets an append."""
    with lock(log, ".sync.lock"):
        check_claim(log)
        write_claim(log)
        commit_log(log, "sminos: %s" % sminos.host_name())
        if git(log, "rev-parse", "--verify", "-q", "origin/main").returncode != 0:
            return
        merge = git(log, "merge", "-q", "--no-edit", "--allow-unrelated-histories", "origin/main")
        if merge.returncode != 0:
            git(log, "merge", "--abort")
            raise SyncFailed("integrating %s into %s failed: %s" % (project.remote, log, said(merge)))


def ahead(log):
    if git(log, "rev-parse", "--verify", "-q", "HEAD").returncode != 0:
        return False
    if git(log, "rev-parse", "--verify", "-q", "origin/main").returncode != 0:
        return True
    count = git(log, "rev-list", "--count", "origin/main..HEAD")
    return count.returncode != 0 or count.stdout.strip() != "0"


def push(project, log):
    """Commit what was appended and push; a push the remote rejected because
    it moved is retried after another fetch and integration, PUSH_RETRIES
    times. True when something was pushed. The caller holds .sync-op.lock."""
    for attempt in range(PUSH_RETRIES + 1):
        with lock(log, ".sync.lock"):
            commit_log(log, "sminos: %s" % sminos.host_name())
        if not ahead(log):
            return False
        p = git(log, "push", "-q", "origin", "HEAD:main", timeout=git_timeout())
        if p.returncode == 0:
            return True
        if not REJECTED_RE.search((p.stderr or "") + (p.stdout or "")):
            raise SyncFailed("git push in %s failed: %s" % (log, said(p)))
        if attempt == PUSH_RETRIES:
            raise SyncFailed("git push in %s was rejected %d times: the remote keeps moving" % (log, attempt + 1))
        fetch(log)
        integrate(project, log)
    return False


def sync_in(project):
    """Duty 1: attach on first sight, fetch, integrate."""
    log = log_dir(project)
    with lock(log, ".sync-op.lock"):
        if not attached(project, log):
            prepare(project, log)
        fetch(log)
        integrate(project, log)


def sync_out(project):
    """Duty 5: commit what this tick appended and push it."""
    log = log_dir(project)
    with lock(log, ".sync-op.lock"):
        return push(project, log)


def attach(project):
    """`sminos project attach`: adopt log/ as a working tree of the remote,
    fetch, integrate (unrelated histories expected on a first attach), and
    push this machine's claim. An unreachable remote ends it after the remote
    is set, leaving the first sync to the daemon."""
    log = log_dir(project)
    try:
        with lock(log, ".sync-op.lock"):
            prepare(project, log)
            try:
                fetch(log)
            except SyncFailed as e:
                print("attached %s to %s; the remote is unreachable for now (%s) — the daemon syncs once it "
                      "answers" % (project.name, project.remote, e))
                return
            integrate(project, log)
            try:
                push(project, log)
            except SyncFailed as e:
                print("attached %s to %s; the push did not land (%s) — the daemon pushes on its next tick" % (
                    project.name, project.remote, e))
                return
    except (SyncFailed, MachineClaimed) as e:
        sminos.die(str(e), 1)
    print("attached %s to %s" % (project.name, project.remote))


# ------------------------------------------------------------- the duties


def daemon_record(project):
    """This machine's own notes on a project, never mirrored: the last tick,
    and which members' state differed from the published word last tick."""
    try:
        with open(os.path.join(project.home, "daemon.json")) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def publish_state(project, view, record):
    """Duty 3, for a mirrored project: for each local member, a `state` event
    once a word other than the last one published for it has held for two
    consecutive ticks (one tick of persistence drops the flip inside a tool
    round) — the first word at once, so another machine never waits on an
    unpublished member. The word each member was last seen holding while it
    differed (its candidate) is kept in `record` between ticks. Into the
    session's own file. Only another machine reads a published word (a local
    view computes it live), so a project with no remote publishes none.
    Returns how many events it appended."""
    before = record.get("candidates")
    before = before if isinstance(before, dict) else {}
    candidates, n = {}, 0
    for m in view.members:
        if not (m.local and m.session):
            continue
        last = ((view.info.get(m.session) or {}).get("state") or {}).get("state")
        if m.state == last:
            continue
        if last is None or before.get(m.session) == m.state:
            n += len(sminos.lifecycle(project, m.session, "state", required=False,
                                      state=m.state, machine=sminos.host_name()))
        else:
            candidates[m.session] = m.state
    record.pop("differed", None)
    record["candidates"] = candidates
    return n


def publish_renames(project, view):
    """Duty 3, for every project: a `renamed` when a seat-less local member's
    harness name (or its source) moved from the last one the log holds. Rare,
    and the only record of a name change — a line derived from a name the
    human set leaves no `in-charge` of its own. Returns how many it appended."""
    n = 0
    for m in view.members:
        if not (m.local and m.session) or m.seat is not None:
            continue
        r = view.info.get(m.session) or {}
        known = r.get("renamed") or r.get("joined") or {}
        if known and (m.alias, m.name_source) != (str(known.get("alias") or ""), str(known.get("name_source") or "")):
            n += len(sminos.lifecycle(project, m.session, "renamed", required=False,
                                      alias=m.alias, name_source=m.name_source))
    return n


def deliver_owed(project, view):
    """Duty 4: for each local member with anything owed to it, deliver_next —
    the same operation the sender's fast path calls — in writer order from
    its settled prefix. Returns (events delivered, the aliases reached)."""
    total, reached = 0, []
    for m in view.members:
        if not (m.local and m.session):
            continue
        if not sminos._owed(view.events, m.session, sminos.delivered_load(project, m.session)):
            continue
        got = sminos.deliver_next(project, m)["delivered"]
        if got:
            total += got
            reached.append(m.alias)
    return total, reached


def tick(project, all_seats=None):
    """One tick of one project, its duties in §8's order. `all_seats` is the
    seat read the caller shares across projects."""
    out = {"integrated": False, "reconciled": 0, "published": 0, "delivered": 0, "pushed": False, "to": [],
           "error": ""}
    errors = []
    record = daemon_record(project)
    if project.remote:
        try:
            sync_in(project)
            out["integrated"] = True
        except SyncFailed as e:
            errors.append(str(e))
    view = sminos.view_of(project, all_seats, titles=False)
    out["reconciled"] = view.reconciled
    if project.remote:
        out["published"] = publish_state(project, view, record)
    out["published"] += publish_renames(project, view)
    out["delivered"], out["to"] = deliver_owed(project, view)
    if out["integrated"]:
        try:
            out["pushed"] = sync_out(project)
        except SyncFailed as e:
            errors.append(str(e))
    out["error"] = "; ".join(errors)
    if out["error"] and out["error"] != record.get("error"):
        # Logged when it changes: an unreachable remote is one line, not one a tick.
        sminos.daemon_log("sync %s: %s" % (project.name, out["error"]))
    record.update({"tick": sminos.now(ms=True), "result": out, "error": out["error"]})
    sminos.write_json(sminos.project_path(project, "daemon.json"), record)
    return out


def tick_line(project, out):
    """A tick's outcome in one line: `<project>: synced · reconciled N ·
    published N · delivered N [to a, b] · pushed`."""
    bits = []
    if project.remote:
        bits.append("synced" if out.get("integrated") else "not synced")
    bits.append("reconciled %d" % (out.get("reconciled") or 0))
    if project.remote or out.get("published"):
        bits.append("published %d" % (out.get("published") or 0))
    to = out.get("to") or []
    bits.append("delivered %d%s" % (out.get("delivered") or 0, (" to " + ", ".join(to)) if to else ""))
    if out.get("pushed"):
        bits.append("pushed")
    if out.get("error"):
        bits.append("error: %s" % out["error"])
    return "%s: %s" % (project.name, " · ".join(bits))


def worth_saying(out, before):
    """For the loop's output: a tick that did something, or whose error is new."""
    return (out["reconciled"] or out["published"] or out["delivered"] or out["pushed"]
            or (out["error"] and out["error"] != before))


def tick_all(quiet=False):
    """One tick over every project known here: the caches forgotten first, one
    seat read and one harness-session read shared across the projects, then
    the derivation duty. A project whose tick fails is logged and skipped; a
    claimed machine name stops everything (MachineClaimed)."""
    sminos.forget_caches()
    all_seats = sminos.seats()
    projects = {}
    for p in sminos.known_projects(all_seats):
        # A project read off its .smns as it is now: the remote may have moved.
        fresh = sminos.resolve_project(p.root) if p.root and os.path.isdir(p.root) else None
        projects[p.id] = fresh if fresh is not None and fresh.id == p.id else p
    for p in sorted(projects.values(), key=lambda p: (p.name, p.id)):
        before = daemon_record(p).get("error", "")
        try:
            out = tick(p, all_seats)
        except MachineClaimed:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — one project's failure is not the daemon's
            sminos.daemon_log("tick %s failed: %r" % (p.name, e))
            print("%s: tick failed: %s" % (p.name, e), file=sys.stderr)
            continue
        if not quiet or worth_saying(out, before):
            print(("%s " % sminos.now() if quiet else "") + tick_line(p, out))
    derive_duty()


# ------------------------------------------------------------- derivation


def derive_every():
    try:
        return float(os.environ.get("SMINOS_DERIVE_EVERY") or DERIVE_EVERY)
    except ValueError:
        return DERIVE_EVERY


def machine_record():
    try:
        with open(daemon_path("state.json")) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def derive_running(d):
    """Whether the derivation child recorded in `d` still runs."""
    global _DERIVE
    if _DERIVE is not None:
        if _DERIVE.poll() is None:
            return True
        _DERIVE = None  # reaped: a zombie of ours would read as alive
    pid = d.get("pid")
    return bool(pid) and sminos.pid_alive(pid) and sminos.proc_start(pid) == d.get("start")


def derive_duty():
    """Duty 6: once an hour, `derive --all` as a child process this tick does
    not wait for — a fork's model call can take minutes, and the delivery
    interval must not; one derivation in flight at a time, across every
    process that ticks here: the check, the start, and the record of the
    child's pid are one step under daemon/derive.lock, released at once (the
    child does not inherit it)."""
    global _DERIVE
    every = derive_every()
    if every <= 0:
        return
    with sminos.flocked(daemon_path("derive.lock")):
        rec = machine_record()
        d = rec.get("derive") or {}
        if derive_running(d) or time.time() - float(d.get("started") or 0) < every:
            return
        with open(os.path.join(sminos.root(), "daemon.log"), "a") as out:
            _DERIVE = subprocess.Popen([sys.executable, os.path.join(sminos.SCRIPT_DIR, "sminos.py"), "derive", "--all"],
                                       stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        rec["derive"] = {"pid": _DERIVE.pid, "start": sminos.proc_start(_DERIVE.pid), "started": time.time()}
        sminos.write_json(daemon_path("state.json"), rec)
    sminos.daemon_log("derive --all started (pid %d)" % _DERIVE.pid)


# ------------------------------------------------------------- the verbs


def run_lock_path():
    return daemon_path("run.lock")


def own_code():
    """The scripts this loop runs, with their mtimes: when one changes (a plugin
    update), the loop ends and launchd's KeepAlive starts it on the new code."""
    out = {}
    for mod in (sminos, sminos.sminos_marks, sys.modules[__name__]):
        path = os.path.realpath(mod.__file__)
        try:
            out[path] = os.stat(path).st_mtime_ns
        except OSError:
            out[path] = None
    return out


def nudged_at():
    """When a sender last asked for a tick now (sminos.nudge_daemon); 0 if never."""
    try:
        return os.stat(daemon_path("nudge")).st_mtime_ns
    except OSError:
        return 0


def cmd_run(a):
    """The loop: a tick every `--interval` seconds (from one tick's start to
    the next), or at once when a sender touched daemon/nudge since the last
    one began. SIGTERM ends it after the tick in hand; so does a change to its
    own scripts, exiting 0 for launchd to restart it on the new code."""
    interval = a.interval
    if interval <= 0:
        sminos.die("--interval is a number of seconds above 0")
    lf = open(run_lock_path(), "a+")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lf.seek(0)
        sminos.die("a daemon already runs for %s (%s)" % (sminos.root(), lf.read().strip() or "pid unknown"), 1)
    lf.seek(0)
    lf.truncate()
    lf.write("pid %d since %s" % (os.getpid(), sminos.now()))
    lf.flush()
    stop = []
    # launchd's bootout and a plain kill send SIGTERM: the tick in hand ends,
    # then the loop.
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    sminos.daemon_log("daemon run started (pid %d, every %gs)" % (os.getpid(), interval))
    code = own_code()
    while not stop:
        started, nudge = time.time(), nudged_at()
        try:
            tick_all(quiet=True)
        except MachineClaimed as e:
            sminos.daemon_log("refused: %s" % e)
            sminos.die(str(e), 1)
        except Exception as e:  # noqa: BLE001 — the loop outlives one bad tick
            sminos.daemon_log("tick failed: %r" % e)
        sys.stdout.flush()
        if own_code() != code:
            sminos.daemon_log("daemon run (pid %d): its code changed; exiting for a restart on the new code"
                              % os.getpid())
            print("%s its code changed: exiting, to be restarted on the new code" % sminos.now())
            return
        while not stop and time.time() - started < interval and nudged_at() == nudge:
            time.sleep(0.05)
    sminos.daemon_log("daemon run stopped (pid %d)" % os.getpid())


def cmd_tick(_a):
    try:
        tick_all()
    except MachineClaimed as e:
        sminos.daemon_log("refused: %s" % e)
        sminos.die(str(e), 1)


def plist_path():
    return os.path.join(sminos.home_dir(), "Library", "LaunchAgents", LABEL + ".plist")


def launchd_env():
    """What a launchd-run sminos needs: its registry root, the PATH that finds
    `claude` and `git`, the machine name when it is set, and the gateway
    route (the transport keys the gateway settings name, as this environment
    sets them), since `derive` runs `claude`."""
    env = {"SMINOS_HOME": sminos.root(), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if os.environ.get("DAEMON_HOST"):
        env["DAEMON_HOST"] = os.environ["DAEMON_HOST"]
    for k in sminos.gateway_env_keys():
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def installed_cli():
    """The CLI the launchd agent runs: a path that outlives plugin updates. A
    CLI running from the plugin cache lives under a versioned directory an
    update prunes, so the agent runs the marketplace clone instead (its
    `installLocation` in ~/.claude/plugins/known_marketplaces.json, kept up to
    date by the harness), and with no usable clone the install is refused
    rather than pointed at a path the next update deletes. Anything else — a
    development checkout — is stable as it is, and runs itself."""
    here = os.path.realpath(sminos.LAUNCHER)
    plugins = os.path.join(sminos.home_dir(), ".claude", "plugins")
    if not here.startswith(os.path.realpath(os.path.join(plugins, "cache")) + os.sep):
        return here
    known = os.path.join(plugins, "known_marketplaces.json")
    try:
        with open(known) as f:
            location = str(((json.load(f) or {}).get("doperpowers") or {}).get("installLocation") or "")
    except (OSError, ValueError, AttributeError):
        location = ""
    stable = os.path.join(location, "skills", "sminos", "scripts", "sminos") if location else ""
    if stable and os.path.isfile(stable):
        return stable
    sminos.die("daemon install: this sminos runs from the versioned plugin cache (%s), which a plugin update "
               "deletes, and the doperpowers marketplace clone it would run instead is missing (%s) — restore it "
               "(claude plugin marketplace add, or update the doperpowers marketplace), or run the install "
               "from a checkout of doperpowers" % (here, stable or "no doperpowers entry in %s" % known), 1)


def cmd_install(_a):
    """Write the launchd agent. Loading it is the operator's step: nothing
    here calls launchctl."""
    with open(PLIST_TEMPLATE) as f:
        text = f.read()
    entries = "\n".join("    <key>%s</key><string>%s</string>" % (escape(k), escape(v))
                        for k, v in sorted(launchd_env().items()))
    for key, value in (("LABEL", escape(LABEL)), ("SMINOS_CLI", escape(installed_cli())),
                       ("ENV", entries), ("LOG", escape(os.path.join(sminos.root(), "daemon.out")))):
        text = text.replace("{{%s}}" % key, value)
    # launchd opens daemon.out in the registry before the daemon runs: on a
    # first install nothing has made the registry yet.
    os.makedirs(sminos.root(), mode=0o700, exist_ok=True)
    path = plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)  # it may carry the gateway route's token
    print("wrote %s\nload it:   launchctl bootstrap gui/$(id -u) %s\nunload it: launchctl bootout gui/$(id -u)/%s"
          % (path, path, LABEL))


def age(ts):
    seconds = sminos.ts_age(ts)
    return sminos.short_age(seconds) if seconds is not None else "?"


def cmd_status(_a):
    lf = open(run_lock_path(), "a+")
    try:
        fcntl.flock(lf, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(lf, fcntl.LOCK_UN)
        print("daemon: not running here")
    except OSError:
        lf.seek(0)
        print("daemon: running (%s)" % (lf.read().strip() or "pid unknown"))
    for p in sorted(sminos.known_projects(), key=lambda p: (p.name, p.id)):
        rec = daemon_record(p)
        if not rec.get("tick"):
            print("%s: never ticked" % p.name)
            continue
        print("%s: last tick %s ago — %s" % (p.name, age(rec["tick"]),
                                             tick_line(p, rec.get("result") or {}).split(": ", 1)[1]))
    d = machine_record().get("derive") or {}
    if d.get("started"):
        print("derive: last started %s ago%s" % (sminos.short_age(max(0, time.time() - float(d["started"]))),
                                                 ", still running" if derive_running(d) else ""))


def cmd_daemon(a):
    # The daemon acts for the machine, never as a session: a `by`, a sender,
    # or a derivation fork must not take the identity of whoever started it.
    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
    {"run": cmd_run, "tick": cmd_tick, "install": cmd_install, "status": cmd_status}[a.op](a)
