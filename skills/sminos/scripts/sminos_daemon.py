#!/usr/bin/env python3
"""sminos_daemon — the mirror and the daemon (§8 of the .smns design).

A project whose .smns names a remote, and no desk hub, keeps its log/ as a
git working tree of that remote: the MIRROR. A hub project syncs through its
hub alone (the uplink), never through git: two live transports writing the
same writer files would bring back the conflicts one writer per file
removed; its remote is only the log's archive, which the one machine the hub
designates writes from a clone of its own (sminos_archive.py). Every machine writes only files named after itself,
so integrating the remote never conflicts; `machines/<machine>.json` claims a
name for one instance (`$SMINOS_HOME/daemon/machine.json`), and a daemon that finds
its name claimed by another instance refuses to run.

The sync invariant: local events are committed before anything from the
remote is integrated. `log/.sync.lock` is taken shared by every appender and
exclusive here, for the phases that touch the working tree and for nothing
else — the fetch and the push wait on the network outside it, each bounded,
so an unreachable remote never stalls a `say` or a Stop export. The
integration phase commits whatever was appended during the fetch and merges
under one hold. One sync per project at a time (`log/.sync-op.lock`);
`project init --hub` takes the same lock to make a mirrored project a hub
project, and every git phase reads .smns again under it, so what is left of
a tick that began before the switch neither integrates nor pushes.

The daemon is one process per machine. `daemon tick` is one iteration over
every project known here, each in the order of §8:

  1. integrate   (mirrored projects) commit, fetch, merge — the daemon
                 attaches a mirror it has not seen before
  2. reconcile   as every reading verb does
  3. publish     (mirrored and hub projects) `state` once a word has held
                 for two ticks, the first at once; (every project)
                 `renamed` on a harness rename
  4. deliver     everything owed to a local member, through deliver_next
  5. push        (mirrored projects) commit what the tick appended, push
  6. archive     (hub projects with a remote, on the machine the hub
                 designates) copy the log into the archive clone, push
  7. derive      once an hour, `derive --all` as a child it does not wait on

`daemon run` loops the tick, and beside it supervises the uplink to the desk
hub (`daemon uplink`, sminos_uplink.py) as a child process it restarts with
backoff — a process, not a thread, because sminos's caches are module globals
the tick clears, and so a hang or a crash of either side never stops the
other; `install` writes the machine's service, a launchd agent on macOS or a
systemd user unit on Linux (it loads nothing); `status` prints the last tick
per project.
"""

import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import threading
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
# The uplink is restarted after this many seconds, doubling from 1 while it
# keeps exiting within the bound; one that ran longer starts the count again.
UPLINK_BACKOFF_MAX = 60
# A stopped uplink has this long to end after SIGTERM before it is killed.
UPLINK_STOP_GRACE = 3
# The pid of the `daemon run` that spawned an uplink, in the uplink's
# environment: it ends whenever its parent is another process.
UPLINK_PARENT_ENV = "SMINOS_UPLINK_PARENT"
# The scripts `daemon run` runs, itself and its uplink child: a change to one
# ends the loop for a restart on the new code.
OWN_CODE = ("sminos.py", "sminos_marks.py", "sminos_daemon.py", "sminos_uplink.py", "sminos_hublog.py",
            "sminos_codes.py", "sminos_archive.py", "sminos_plane.py", "sminos_bridge.py", "sminos_policy.py",
            "sminos_outcomes.py", "sminos_requests.py", "sminos_rpc.py", "sminos_control.py")
LABEL = "com.doperpowers.sminos-daemon"
PLIST_TEMPLATE = os.path.join(sminos.SCRIPT_DIR, "..", "references", "sminos-daemon.plist")
UNIT = "sminos-daemon.service"
UNIT_TEMPLATE = os.path.join(sminos.SCRIPT_DIR, "..", "references", UNIT)
REJECTED_RE = re.compile(r"\[rejected\]|non-fast-forward|fetch first|\[remote rejected\].*(?:stale|lock)")
_DERIVE = None  # the derivation child this process started, while it may run
# A bridge's kept file outlives its session's end this long (Resume soon after
# keeps the session's model choice); the sweep runs at most this often.
BRIDGE_QUIET_S = 86400
BRIDGE_SWEEP_EVERY = 3600
_BRIDGE_SWEPT = 0.0  # when this process last swept the bridges' files


class SyncFailed(Exception):
    """A sync phase failed: logged, and the tick goes on with the stale mirror."""


class BecameHub(Exception):
    """The project's .smns names a hub now: git no longer syncs it."""


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


@contextlib.contextmanager
def sync_op(log):
    """One sync of a project at a time (`log/.sync-op.lock`), the mirror's
    stale git locks cleared first."""
    with lock(log, ".sync-op.lock"):
        clear_stale_locks(log)
        yield


def clear_stale_locks(log):
    """Remove git's lock files in the mirror older than the git bound. The
    caller holds .sync-op.lock, so no git of ours runs in the mirror: such a
    lock was left by a git killed mid-step (the bound's own kill, a daemon
    killed in a commit), and every sync after it would fail on it — a stale
    index.lock stops the commit, a stale ref lock the fetch. A fresh one is
    left alone."""
    gitdir, bound = os.path.join(log, ".git"), git_timeout()
    for d, dirs, files in os.walk(gitdir):
        if d == gitdir and "objects" in dirs:
            dirs.remove("objects")  # git keeps no lock there worth a walk every tick
        for f in files:
            if not f.endswith(".lock"):
                continue
            path = os.path.join(d, f)
            try:
                age = time.time() - os.stat(path).st_mtime
                if age <= bound:
                    continue
                os.unlink(path)
            except OSError:
                continue
            sminos.daemon_log("removed %s, a git lock %ds old (past the %gs git bound) left by a git killed mid-step"
                              % (path, age, bound))


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
            "the machine name %s is claimed by another instance (%s) in %s — this daemon refuses to run. "
            "Events already written under this name cannot be published under another name. "
            "Choose a unique DAEMON_HOST before this registry's first say or attach. If this registry already holds "
            "events, keep the name and remove machines/%s.json from the remote only when the other machine is gone "
            "and pushed nothing under this name, or accept that the pre-attach events stay local"
            % (name, held[:8], log, name))


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


def ensure_mirrored(project):
    """Raise BecameHub when the project names a hub now: the .smns of the
    checkout the tick read, or the project's registration (project.json) —
    the checkout the uplink reads, whose .smns is read as it is now, or the
    hub it recorded when that checkout is gone. Every checkout of a project
    shares its log, so a hub any of them names bars git (project_path keeps
    a hub checkout registered while it names one). A tick syncs the Project
    it read when it began; `project init --hub` rewrites .smns and registers
    it under .sync-op.lock, which every caller here holds, so a git phase
    that looks again under it never integrates or pushes a project that has
    become a hub project (an .smns changed by any other hand is caught at
    the next phase)."""
    reg = sminos.registration(project.id)
    root = str(reg.get("root") or "")
    for where in dict.fromkeys(r for r in (project.root, root) if r):
        if sminos.names_hub(where, project.id):
            raise BecameHub("%s names a hub now: git no longer syncs %s" % (
                os.path.join(where, sminos.SMNS), project.name))
    if reg.get("hub") is not None and not (root and os.path.isdir(root)):
        raise BecameHub("%s is registered as a hub project: git no longer syncs it" % project.name)


def integrate(project, log):
    """The integration phase, under one exclusive hold: the claim checked,
    what was appended during the fetch committed, then the remote merged —
    never releasing between the two, so the merge never meets an append."""
    ensure_mirrored(project)
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
        ensure_mirrored(project)
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
    """Duty 1: attach on first sight, fetch, integrate. True when it
    integrated; False when the project turned out to be a hub project now
    (BecameHub), with nothing of the remote integrated."""
    log = log_dir(project)
    try:
        with sync_op(log):
            ensure_mirrored(project)
            if not attached(project, log):
                prepare(project, log)
            fetch(log)
            integrate(project, log)
    except BecameHub as e:
        sminos.daemon_log("sync %s: %s" % (project.name, e))
        return False
    return True


def sync_out(project):
    """Duty 5: commit what this tick appended and push it. Nothing is pushed
    once the project is a hub project (BecameHub)."""
    log = log_dir(project)
    try:
        with sync_op(log):
            return push(project, log)
    except BecameHub as e:
        sminos.daemon_log("sync %s: %s" % (project.name, e))
        return False


def attach(project):
    """`sminos project attach`: adopt log/ as a working tree of the remote,
    fetch, integrate (unrelated histories expected on a first attach), and
    push this machine's claim. An unreachable remote ends it after the remote
    is set, leaving the first sync to the daemon."""
    log = log_dir(project)
    try:
        with sync_op(log):
            ensure_mirrored(project)
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
    except (SyncFailed, MachineClaimed, BecameHub) as e:
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
    """Duty 3, for a project another machine reads (`shared`): for each local member, a `state` event
    once a word other than the last one published for it has held for two
    consecutive ticks (one tick of persistence drops the flip inside a tool
    round) — the first word at once, so another machine never waits on an
    unpublished member. The word each member was last seen holding while it
    differed (its candidate) is kept in `record` between ticks. Into the
    session's own file. Only another machine reads a published word (a local
    view computes it live), so a project with neither a remote nor a hub
    publishes none.
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


# (project id, session, writer and seq of its `retired`): the retirements of
# this machine's sessions whose title this process has settled. A retired
# session's transcript stops changing, so one look per retirement keeps the
# tick from globbing for every session the project ever ended; a resume and
# a later retirement is another event, looked at again.
_TITLES_SETTLED = set()


def publish_titles(project, view):
    """Duty 3, for a project another machine reads (`shared`): a `titled`
    when the title of a session of this machine (sminos.transcript_title: its
    /rename name, else the harness's generated one) differs from the last one
    the log holds for it, into the session's own file — every tick for a
    local member, once per retirement for a session that has ended (one
    renamed and closed between two ticks is retired by this tick's
    reconciliation before it could be published; one that ended before this
    process ran was never its member). The desk and every other machine's
    views name the session by it, its ended sessions and an offline
    machine's included. The harness re-appends title records thousands of
    times a session, mostly unchanged; only a change is an event. A title
    that cannot be read says nothing, so "" is never published. Returns how
    many events it appended."""
    n = 0
    for m in view.members:
        if m.local and m.session:
            n += publish_title(project, m.session, view.info.get(m.session)) or 0
    for sid, r in view.info.items():
        last = r["latest"]
        if not (last and last["kind"] == "retired" and r["joined"]):
            continue
        key = (project.id, sid, last["writer"], last["seq"])
        if key in _TITLES_SETTLED or not sminos.is_self(str(r["joined"].get("machine") or ""), sid):
            continue
        got = publish_title(project, sid, r)
        if got is not None:
            n += got
            _TITLES_SETTLED.add(key)
    return n


def publish_title(project, session, r):
    """A `titled` for one session of this machine when its title is not
    empty and differs from the last one published (`r`: its _projection
    row). How many it appended; None when the append failed."""
    title = sminos.transcript_title(session)
    if not title or title == sminos.published_title(r):
        return 0
    return len(sminos.lifecycle(project, session, "titled", required=False, title=title)) or None


def deliver_owed(project, view):
    """Duty 4: for each local member with anything owed to it, deliver_next —
    the same operation the sender's fast path calls — in writer order from
    its settled prefix. Returns (events delivered, the aliases reached).
    An event from outside owed to a closed terminal session is reported
    `recorded` once and stays owed (sminos_outcomes.report_closed)."""
    try:
        sminos.sibling_module("sminos_outcomes").report_closed(project, view)
    except OSError as e:
        sminos.daemon_log("delivery: what is owed to closed sessions of %s could not be reported: %s" % (
            project.name, e))
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


def mirrored(project):
    """Whether git syncs the project: it names a remote and no hub. A hub
    project syncs through its hub alone; its remote is the log's archive."""
    return bool(project.remote) and project.hub is None


def shared(project):
    """Whether another machine reads the project's log, through git or a hub."""
    return bool(project.remote) or project.hub is not None


def tick(project, all_seats=None):
    """One tick of one project, its duties in §8's order. `all_seats` is the
    seat read the caller shares across projects."""
    out = {"integrated": False, "reconciled": 0, "published": 0, "delivered": 0, "pushed": False,
           "archived": False, "to": [], "error": ""}
    errors = []
    record = daemon_record(project)
    if mirrored(project):
        try:
            out["integrated"] = sync_in(project)
        except SyncFailed as e:
            errors.append(str(e))
    view = sminos.view_of(project, all_seats, titles=False)
    out["reconciled"] = view.reconciled
    if shared(project):
        out["published"] = publish_state(project, view, record) + publish_titles(project, view)
    out["published"] += publish_renames(project, view)
    out["delivered"], out["to"] = deliver_owed(project, view)
    if out["integrated"]:
        try:
            out["pushed"] = sync_out(project)
        except SyncFailed as e:
            errors.append(str(e))
    if project.hub is not None and project.remote:
        out["archived"], error = sminos.sibling_module("sminos_archive").duty(project, record)
        if error:
            errors.append("archive: %s" % error)
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
    if mirrored(project):
        bits.append("synced" if out.get("integrated") else "not synced")
    bits.append("reconciled %d" % (out.get("reconciled") or 0))
    if shared(project) or out.get("published"):
        bits.append("published %d" % (out.get("published") or 0))
    to = out.get("to") or []
    bits.append("delivered %d%s" % (out.get("delivered") or 0, (" to " + ", ".join(to)) if to else ""))
    if out.get("pushed"):
        bits.append("pushed")
    if out.get("archived"):
        bits.append("archived")
    if out.get("error"):
        bits.append("error: %s" % out["error"])
    return "%s: %s" % (project.name, " · ".join(bits))


def worth_saying(out, before):
    """For the loop's output: a tick that did something, or whose error is new."""
    return (out["reconciled"] or out["published"] or out["delivered"] or out["pushed"] or out["archived"]
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
    bridge_duty()


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


# ------------------------------------------------------------- the bridges' files


def bridge_duty():
    """The sweep of the bridges' files, at most once every BRIDGE_SWEEP_EVERY
    per loop (a one-shot tick sweeps each time)."""
    global _BRIDGE_SWEPT
    if time.time() - _BRIDGE_SWEPT < BRIDGE_SWEEP_EVERY:
        return
    _BRIDGE_SWEPT = time.time()
    sweep_bridges()


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except (OSError, TypeError):
        return None


def sweep_bridges():
    """What the bridge leaves under `$SMINOS_HOME/bridge/` for a session no
    process of this machine runs any more (DC2 keeps them for its reloads,
    and nothing else removed them): its kept file (`<id>.json`: the model
    choice and the delivery keys) once the session has been quiet
    BRIDGE_QUIET_S, neither its transcript nor the file touched that long, so
    a Resume soon after the end keeps the choice; and its socket as soon as
    nobody listens on it, which the child removes itself unless it was
    killed. A delivery key the file forgets is an event the daemon settled
    when the bridge took it, which is never pushed again. Read through the
    main loop's caches, which tick_all has just forgotten."""
    bridge = sminos.sibling_module("sminos_bridge")
    d = bridge.bridge_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return
    now = time.time()
    for name in names:
        sid, ext = os.path.splitext(name)
        if ext not in (".json", ".sock") or not sminos.UUID_RE.fullmatch(sid) or sminos.session_running(sid):
            continue
        path = os.path.join(d, name)
        if ext == ".sock":
            bridge.remove_stale(path)
            continue
        last = max([t for t in (mtime(sminos.transcript_path(sid)), mtime(path)) if t is not None], default=None)
        if last is None or now - last < BRIDGE_QUIET_S:
            continue
        try:
            os.unlink(path)
        except OSError:
            continue
        sminos.daemon_log("removed %s: its session has run nowhere here for %d h" % (path, (now - last) // 3600))


# ------------------------------------------------------------- the verbs


def run_lock_path():
    return daemon_path("run.lock")


def own_code():
    """The scripts this loop and its uplink run, with their mtimes: when one
    changes (a plugin update), the loop ends and the service manager starts it
    on the new code (launchd's KeepAlive, systemd's Restart=always)."""
    out = {}
    here = os.path.dirname(os.path.realpath(__file__))
    for name in OWN_CODE:
        path = os.path.realpath(os.path.join(here, name))
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


def credential_bytes():
    """daemon/hub.json as it is on disk, or None when there is none."""
    try:
        with open(daemon_path("hub.json"), "rb") as f:
            return f.read()
    except OSError:
        return None


class UplinkSupervisor(threading.Thread):
    """`daemon run`'s keeper of the uplink: while the machine holds a hub
    credential (daemon/hub.json), one `daemon uplink` child runs, restarted
    with backoff whenever it exits, and at once on the credential it holds
    when hub.json changes (an enrollment replaced, or a first one); `stop`
    ends it (SIGTERM, then a kill). The child's output goes to daemon.log."""

    def __init__(self):
        super().__init__(name="uplink-supervisor", daemon=True)
        self.halt = threading.Event()
        self.proc = None

    def run(self):
        backoff = 1
        while not self.halt.is_set():
            held = credential_bytes()
            if held is None:
                self.halt.wait(1)
                continue
            started = time.time()
            with open(os.path.join(sminos.root(), "daemon.log"), "a") as out:
                # The child is told who spawned it: an uplink whose parent is
                # gone before it could look must not take the service
                # manager (its new parent) for it.
                self.proc = subprocess.Popen(
                    [sys.executable, os.path.join(sminos.SCRIPT_DIR, "sminos.py"), "daemon", "uplink"],
                    stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                    env={**os.environ, UPLINK_PARENT_ENV: str(os.getpid())})
            while self.proc.poll() is None and not self.halt.wait(0.2):
                if credential_bytes() != held:
                    sminos.daemon_log("uplink (pid %d): hub.json changed; restarting it on the credential as it "
                                      "is now" % self.proc.pid)
                    self.stop_child()
                    backoff = 1
                    break
            else:
                if self.halt.is_set():
                    break
                rc = self.proc.returncode
                if time.time() - started > UPLINK_BACKOFF_MAX:
                    backoff = 1
                sminos.daemon_log("uplink (pid %d) exited %s; restarting in %ds" % (
                    self.proc.pid, "on signal %d" % -rc if rc < 0 else "with %d" % rc, backoff))
                if self.halt.wait(backoff):
                    break
                backoff = min(backoff * 2, UPLINK_BACKOFF_MAX)
        self.stop_child()

    def stop_child(self):
        p = self.proc
        if p is None or p.poll() is not None:
            return
        p.terminate()
        try:
            p.wait(UPLINK_STOP_GRACE)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()

    def stop(self):
        self.halt.set()
        self.join(UPLINK_STOP_GRACE + 2)


def cmd_run(a):
    """The loop: a tick every `--interval` seconds (from one tick's start to
    the next), or at once when a sender touched daemon/nudge since the last
    one began; the uplink beside it (UplinkSupervisor). SIGTERM ends it after
    the tick in hand; so does a change to its own scripts, exiting 0 for the
    service manager to restart it on the new code; the uplink is stopped
    either way."""
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
    # launchd's bootout, systemctl's stop and a plain kill send SIGTERM: the
    # tick in hand ends, then the loop.
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    sminos.daemon_log("daemon run started (pid %d, every %gs)" % (os.getpid(), interval))
    code = own_code()
    uplink = UplinkSupervisor()
    uplink.start()
    try:
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
    finally:
        uplink.stop()
    sminos.daemon_log("daemon run stopped (pid %d)" % os.getpid())


def cmd_tick(_a):
    try:
        tick_all()
    except MachineClaimed as e:
        sminos.daemon_log("refused: %s" % e)
        sminos.die(str(e), 1)


def service():
    """The service manager `install` writes for: launchd on macOS, a systemd
    user unit on Linux. SMINOS_SERVICE (launchd or systemd) overrides it
    (tests)."""
    forced = os.environ.get("SMINOS_SERVICE")
    if forced:
        if forced not in ("launchd", "systemd"):
            sminos.die("SMINOS_SERVICE is launchd or systemd, not %r" % forced)
        return forced
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform.startswith("linux"):
        return "systemd"
    sminos.die("daemon install writes a launchd agent (macOS) or a systemd user unit (Linux); this is %s"
               % sys.platform, 1)


def plist_path():
    return os.path.join(sminos.home_dir(), "Library", "LaunchAgents", LABEL + ".plist")


def unit_path():
    """Where the systemd user manager looks for the user's own units."""
    config = os.environ.get("XDG_CONFIG_HOME") or ""
    if not os.path.isabs(config):
        config = os.path.join(sminos.home_dir(), ".config")
    return os.path.join(config, "systemd", "user", UNIT)


def service_env():
    """What a service-run sminos needs (launchd's or systemd's): its registry
    root, the PATH that finds `claude` and `git`, the machine name when it is
    set, and the gateway route (the transport keys the gateway settings name,
    as this environment sets them), since `derive` runs `claude`."""
    env = {"SMINOS_HOME": sminos.root(), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if os.environ.get("DAEMON_HOST"):
        env["DAEMON_HOST"] = os.environ["DAEMON_HOST"]
    for k in sminos.gateway_env_keys():
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def installed_cli():
    """The CLI the service runs, its sminos.py: a path that outlives plugin
    updates. A CLI running from the plugin cache lives under a versioned
    directory an update prunes, so the service runs the marketplace clone
    instead (its `installLocation` in ~/.claude/plugins/known_marketplaces.json,
    kept up to date by the harness), and with no usable clone the install is
    refused rather than pointed at a path the next update deletes. Anything
    else — a development checkout — is stable as it is, and runs itself."""
    here = os.path.join(sminos.SCRIPT_DIR, "sminos.py")
    plugins = os.path.join(sminos.home_dir(), ".claude", "plugins")
    if not here.startswith(os.path.realpath(os.path.join(plugins, "cache")) + os.sep):
        return here
    known = os.path.join(plugins, "known_marketplaces.json")
    try:
        with open(known) as f:
            location = str(((json.load(f) or {}).get("doperpowers") or {}).get("installLocation") or "")
    except (OSError, ValueError, AttributeError):
        location = ""
    stable = os.path.join(location, "skills", "sminos", "scripts", "sminos.py") if location else ""
    if stable and os.path.isfile(stable):
        return stable
    sminos.die("daemon install: this sminos runs from the versioned plugin cache (%s), which a plugin update "
               "deletes, and the doperpowers marketplace clone it would run instead is missing (%s) — restore it "
               "(claude plugin marketplace add, or update the doperpowers marketplace), or run the install "
               "from a checkout of doperpowers" % (here, stable or "no doperpowers entry in %s" % known), 1)


def interpreter():
    """The Python the service runs sminos on: the one running this install,
    which imports sminos (sminos.MIN_PYTHON), pinned. Run through the
    launcher, the service would take the first python3 its PATH finds, and
    the PATH an install records can lead to one too old (macOS's own)."""
    if not (sys.executable and os.path.isabs(sys.executable)):
        sminos.die("daemon install: this Python does not say where it is (sys.executable is %r), so the service "
                   "cannot be pointed at it — run the install with a python3 from PATH" % sys.executable, 1)
    return sys.executable


def cmd_install(_a):
    """Write the machine's service: the launchd agent, or the systemd user
    unit. Loading it is the operator's step: nothing here calls launchctl or
    systemctl."""
    if service() == "systemd":
        install_systemd()
    else:
        install_launchd()


def write_private(path, text):
    """The service's file, readable only by its owner from its first byte:
    it may carry the gateway route's token."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(text)


def install_launchd():
    with open(PLIST_TEMPLATE) as f:
        text = f.read()
    entries = "\n".join("    <key>%s</key><string>%s</string>" % (escape(k), escape(v))
                        for k, v in sorted(service_env().items()))
    python, cli = interpreter(), installed_cli()
    for key, value in (("LABEL", escape(LABEL)), ("PYTHON", escape(python)), ("SMINOS_CLI", escape(cli)),
                       ("ENV", entries), ("LOG", escape(os.path.join(sminos.root(), "daemon.out")))):
        text = text.replace("{{%s}}" % key, value)
    # launchd opens daemon.out in the registry before the daemon runs: on a
    # first install nothing has made the registry yet.
    os.makedirs(sminos.root(), mode=0o700, exist_ok=True)
    path = plist_path()
    write_private(path, text)
    print("wrote %s: it runs %s on %s (Python %d.%d)\nload it:   launchctl bootstrap gui/$(id -u) %s\n"
          "unload it: launchctl bootout gui/$(id -u)/%s"
          % ((path, cli, python) + tuple(sys.version_info[:2]) + (path, LABEL)))


def unit_word(value, argument=False):
    """`value` as one double-quoted word of a unit file: quoted words are
    C-unescaped (the backslash, the quote, a line break escaped), and `%`
    starts a specifier (`%%`). A `$` stays as it is where nothing expands
    variables, in Environment= and in ExecStart's program path; an
    `argument` of ExecStart's has its variables expanded, so a `$` there is
    written `$$`."""
    if argument:
        value = value.replace("$", "$$")
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("%", "%%")


def install_systemd():
    """The systemd user unit, under the launchd agent's contract: the stable
    CLI, the same environment, a 0600 file, the output in daemon.out."""
    if "\n" in sminos.root() or "\r" in sminos.root():
        sminos.die("the registry path holds a line break, which the unit's output line cannot carry: %r"
                   % sminos.root(), 1)
    with open(UNIT_TEMPLATE) as f:
        text = f.read()
    log = os.path.abspath(os.path.join(sminos.root(), "daemon.out"))
    entries = "\n".join("Environment=%s" % unit_word("%s=%s" % (k, v)) for k, v in sorted(service_env().items()))
    python, cli = interpreter(), installed_cli()
    for key, value in (("PYTHON", unit_word(python)), ("SMINOS_CLI", unit_word(cli, argument=True)),
                       ("ENV", entries), ("LOG", log.replace("%", "%%"))):
        text = text.replace("{{%s}}" % key, value)
    # systemd opens daemon.out before the daemon runs: on a first install
    # nothing has made the registry yet.
    os.makedirs(sminos.root(), mode=0o700, exist_ok=True)
    path = unit_path()
    write_private(path, text)
    print("wrote %s: it runs %s on %s (Python %d.%d)\n"
          "load it:   systemctl --user daemon-reload && systemctl --user enable --now %s\n"
          "unload it: systemctl --user disable --now %s\n"
          "to keep it running with nobody logged in (and from boot), lingering, once per user:\n"
          "           loginctl enable-linger" % ((path, cli, python) + tuple(sys.version_info[:2]) + (UNIT, UNIT)))


def age(ts):
    seconds = sminos.ts_age(ts)
    return sminos.short_age(seconds) if seconds is not None else "?"


def held_by(path):
    """What a lock file's holder wrote in it ("pid N since T"), or "" when no
    process holds it."""
    with open(path, "a+") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(lf, fcntl.LOCK_UN)
            return ""
        except OSError:
            lf.seek(0)
            return lf.read().strip() or "pid unknown"


def cmd_status(_a):
    run = held_by(run_lock_path())
    print("daemon: running (%s)" % run if run else "daemon: not running here")
    if os.path.exists(daemon_path("hub.json")):
        up = held_by(daemon_path("uplink.lock"))
        print("uplink: running (%s)" % up if up else "uplink: not running")
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
    if a.op == "uplink":
        sminos.sibling_module("sminos_uplink").cmd_uplink(a)
        return
    if a.op == "policy":
        sminos.sibling_module("sminos_policy").cmd_policy(a)
        return
    {"run": cmd_run, "tick": cmd_tick, "install": cmd_install, "status": cmd_status}[a.op](a)
