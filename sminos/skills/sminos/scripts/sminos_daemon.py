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
  3. publish     (hub projects) a local member joined under a former name
                 of this machine joins again under its name now; (mirrored
                 and hub projects) `state` once a word has held for two
                 ticks, the first at once; (every project) `renamed` on a
                 harness rename
  4. deliver     everything owed to a local member, through deliver_next
  5. push        (mirrored projects) commit what the tick appended, push
  6. archive     (hub projects with a remote, on the machine the hub
                 designates) copy the log into the archive clone, push
  7. derive      once an hour, `derive --all` as a child it does not wait on;
                 and the sweep of the bridges' files and of join overrides

Before the first, every running session of this machine is mapped to its
project (sminos.record_project), which registers a project not known here
yet — a .smns committed under a live session — so it is ticked this tick and
the session moves within one interval (§1a of the org directory's design).

`daemon run` loops the tick, and beside it supervises the uplink to the desk
hub (`daemon uplink`, sminos_uplink.py) as a child process it restarts with
backoff — a process, not a thread, because sminos's caches are module globals
the tick clears, and so a hang or a crash of either side never stops the
other. When its scripts change (a plugin update), it stops the uplink and
executes itself again in the same process, so the service manager sees no
exit and its restart throttle never holds the machine off the hub. `install`
writes the machine's service, a launchd agent on macOS or a systemd user unit
on Linux (it loads nothing); `status` prints the last tick per project.
"""

import contextlib
import fcntl
import hashlib
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
# A stopped uplink has this long to end after SIGTERM before it is killed:
# its stream's close, then up to the plane's STOP_SAVE_SECONDS (5) saving the
# builds it holds, so the next uplink loads them rather than parsing.
UPLINK_STOP_GRACE = 8
# The pid of the `daemon run` that spawned an uplink, in the uplink's
# environment: it ends whenever its parent is another process.
UPLINK_PARENT_ENV = "SMINOS_UPLINK_PARENT"
# A change to the daemon's code is acted on once its scripts have held still
# this long (a git pull in progress finishes first), and at the latest this
# long after it was seen.
CODE_SETTLE = 1.0
CODE_SETTLE_MAX = 10.0
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
# A join override (and a launch directory cached) outlives its session's
# transcript's last change this long; the sweep runs at most this often.
OVERRIDE_QUIET_S = 30 * 86400
OVERRIDE_SWEEP_EVERY = 3600
_OVERRIDES_SWEPT = 0.0  # when this process last swept them


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
    alias (or its source) moved from the last one the log holds. Rare, and
    the only record of a name change — a line derived from a name the human
    set leaves no `in-charge` of its own. The alias is the one the member goes
    by (sminos.held_alias), so a harness name that would shadow a seat or
    another current member is never published as its alias; a member that
    goes by its short id has the source it joined with (`derived`). Returns
    how many it appended."""
    n = 0
    for m in view.members:
        if not (m.local and m.session) or m.seat is not None:
            continue
        r = view.info.get(m.session) or {}
        known = r.get("renamed") or r.get("joined") or {}
        source = m.name_source or ("derived" if m.alias == m.short else "")
        if known and (m.alias, source) != (str(known.get("alias") or ""), str(known.get("name_source") or "")):
            n += len(sminos.lifecycle(project, m.session, "renamed", required=False,
                                      alias=m.alias, name_source=source))
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


def rejoin_former(project, view=None):
    """Duty 3, for a hub project: each local member whose latest `joined`
    this machine wrote under a former name joins again under its name now,
    once: the hub takes only `<machine>/…` writers, so otherwise no other
    machine and no browser would see it. Its earlier history stays here — a
    rename or a state published under the former name included — so the new
    writer starts from what the member is now: its alias and name source in
    the `joined`, and its state after it (publish_renames and publish_state
    compare against those former events and would find nothing to say).
    The uplink runs it as it opens the project, so the vector and the upload
    carry it, and the tick runs it too: a former-named `joined` can come at
    any time while the stream is open, from a session whose Claude Code still
    runs a plugin from before the enrollment. Returns how many joined again."""
    if not sminos.machine_identity()[1]:
        return 0
    view = view or sminos.view_of(project, titles=False)
    n = 0
    for m in view.members:
        if not (m.local and m.session):
            continue
        j = (view.info.get(m.session) or {}).get("joined") or {}
        if not j or j.get("writer") == sminos.writer_id(m.session):
            continue

        def guard(evs, mine=sminos.writer_id(m.session)):
            last = next((e for e in reversed(evs) if e["kind"] in sminos.MEMBERSHIP), None)
            return last is not None and last["kind"] == "joined" and last["writer"] != mine

        got = sminos.lifecycle(project, m.session, "joined", guard=guard, required=False,
                               **sminos.joined_fields(m.alias, m.name_source, *(
                                   j.get(k, "") for k in ("cwd", "worktree", "role", "seat", "by")),
                                   session_kind=str(j.get("session_kind") or m.kind)))
        if got:
            n += 1
            if m.state:
                sminos.lifecycle(project, m.session, "state", required=False, state=m.state,
                                 machine=sminos.host_name())
            sminos.daemon_log("%s in %s joined again as %s (it had joined as %s)"
                              % (m.alias, project.name, sminos.host_name(), j.get("machine")))
    return n


def enrolled_at():
    """When this machine enrolled at its hub (daemon/hub.json's `enrolled`,
    whole seconds), in epoch seconds; None when it is not known."""
    try:
        with open(daemon_path("hub.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return sminos._ts_epoch(d.get("enrolled")) if isinstance(d, dict) else None


def notice_former_writers(project, view, record):
    """For a hub project: says once in daemon.log, for each writer of a name
    this machine wrote under before it enrolled that appended here after the
    enrollment, whose it is and what moves it. The hub never takes such a
    writer, so what that session writes there — its messages to its human
    included — stays on this machine, and nothing the daemon does moves the
    writer: the process appending to it runs code from before the enrollment
    (most likely a Claude Code's plugin, whose hooks name the writer after
    the host), and only that session can load newer code. An event under a
    former name that carries a code came from the hub, from another machine
    enrolled under that name: no sign. The writers said are kept in
    `record`."""
    former = sminos.machine_identity()[1]
    since = enrolled_at() if former else None
    if since is None:
        return
    said = record.get("former_writers")
    said = [w for w in said if isinstance(w, str)] if isinstance(said, list) else []
    late = {}
    for e in view.events:
        w = e["writer"]
        if w.partition("/")[0] in former and "mac" not in e and w not in said:
            t = sminos._ts_epoch(e.get("ts"))
            # `enrolled` is whole seconds: only an event a second past it is surely later.
            if t is not None and t >= since + 1:
                late[w] = e
    if not late:
        return
    me = sminos.host_name()
    aliases = {m.session: m.alias for m in view.members if m.session}
    for w, e in sorted(late.items()):
        sid = sminos.writer_session(w)
        sminos.daemon_log(
            "%s in %s still writes as %s, this machine's name before it enrolled as %s (%s at %s): the hub never "
            "takes that writer. That session runs sminos code from before the enrollment, most likely its Claude "
            "Code's plugin: /reload-plugins in it, or a restart, makes it write as %s"
            % (aliases.get(sid) or sid[:8] or w, project.name, w.partition("/")[0], me, sminos.event_ref(e),
               e.get("ts"), me))
        said.append(w)
    record["former_writers"] = said


def deliver_owed(project, view):
    """Duty 4: for each local member with anything owed to it, deliver_next —
    the same operation the sender's fast path calls — in writer order from
    its settled prefix. Returns (events delivered, the aliases reached).
    An event from outside owed to a closed terminal session is reported
    `recorded` once and stays owed (sminos_outcomes.report_closed); one a
    session's engine dropped after its bridge took it is reported `failed`
    once, after its delivery (sminos_outcomes.report_refused)."""
    outcomes = sminos.sibling_module("sminos_outcomes")
    try:
        outcomes.report_closed(project, view)
    except OSError as e:
        sminos.daemon_log("delivery: what is owed to closed sessions of %s could not be reported: %s" % (
            project.name, e))
    total, reached = 0, []
    to = sminos.addressees(view.events)
    for m in view.members:
        if not (m.local and m.session) or m.session not in to:
            continue
        if not sminos._owed(to[m.session], m.session, sminos.delivered_load(project, m.session)):
            continue
        got = sminos.deliver_next(project, m)["delivered"]
        if got:
            total += got
            reached.append(m.alias)
    try:
        outcomes.report_refused(project, view)
    except OSError as e:
        sminos.daemon_log("delivery: what the sessions of %s dropped could not be reported: %s" % (project.name, e))
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
    if project.hub is not None:
        rejoined = rejoin_former(project, view)
        if rejoined:
            # Read again, so what is published next compares against the joined just written.
            out["published"] = rejoined
            view = sminos.view_of(project, all_seats, titles=False)
        notice_former_writers(project, view, record)
    if shared(project):
        out["published"] += publish_state(project, view, record) + publish_titles(project, view)
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
    map_sessions()
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
    override_duty()


def map_sessions():
    """Every running engine session of this machine to its project, each
    project registered here (project_path writes its project.json), so
    known_projects lists a project that appeared under a live session this
    tick. Internal forks aside."""
    internal = sminos.internal_pids()
    for rec in sminos.peer_records():
        sid = rec.get("sessionId")
        if not (isinstance(sid, str) and sminos.UUID_RE.match(sid)) or str(rec.get("pid")) in internal \
                or not sminos.peer_running(rec):
            continue
        try:
            p = sminos.record_project(rec)
            if p is not None:
                sminos.project_path(p, "log")
        except OSError as e:
            sminos.daemon_log("tick: registering the project of %s failed: %s" % (sid[:8], e))


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
    if not (pid and sminos.pid_alive(pid) and sminos.proc_start(pid) == d.get("start")):
        return False
    # A child of this process it holds no handle on: one started before
    # `daemon run` restarted in place, which keeps the pid and its children.
    # Reaped here once it has ended, since its zombie reads as alive.
    try:
        return os.waitpid(int(pid), os.WNOHANG)[0] == 0
    except ChildProcessError:
        return True  # not this process's child: another's derivation


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
    main loop's caches, which tick_all has just forgotten, the transcripts
    as they are now (sminos.transcripts_now)."""
    bridge = sminos.sibling_module("sminos_bridge")
    d = bridge.bridge_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return
    sminos.transcripts_now()
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


def override_duty():
    """The sweep of join overrides, at most once every OVERRIDE_SWEEP_EVERY
    per loop (a one-shot tick sweeps each time)."""
    global _OVERRIDES_SWEPT
    if time.time() - _OVERRIDES_SWEPT < OVERRIDE_SWEEP_EVERY:
        return
    _OVERRIDES_SWEPT = time.time()
    sweep_overrides()


def sweep_overrides():
    """A join override (`$SMINOS_HOME/sessions/<id>.json`) whose session's
    transcript is gone or has not changed in OVERRIDE_QUIET_S, or whose
    target the session can no longer be in (not known here, or ineligible:
    sminos.join_refusal — a retired project), is removed, a daemon.log line
    naming the session and the target; the session itself already resolves
    as though it were absent (session_project). A cached launch directory
    (`launch/<id>.json`) goes by the transcript's rule alone."""
    sminos.transcripts_now()
    now = time.time()
    for sub in ("sessions", "launch"):
        d = os.path.join(sminos.root(), sub)
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            sid, ext = os.path.splitext(name)
            if ext != ".json" or not sminos.UUID_RE.fullmatch(sid):
                continue
            last = mtime(sminos.transcript_path(sid))
            why = "its transcript is gone" if last is None else \
                "its transcript has not changed in %d days" % ((now - last) // 86400) \
                if now - last >= OVERRIDE_QUIET_S else ""
            pid = sminos.override_of(sid) if sub == "sessions" else ""
            if sub == "sessions" and not why:
                target = sminos.known_project(pid) if pid else None
                why = "it names no project" if not pid else "that project is not known here" if target is None \
                    else sminos.join_refusal(target)
            if not why:
                continue
            try:
                os.unlink(os.path.join(d, name))
            except OSError:
                continue
            if sub == "sessions":
                sminos.daemon_log("removed the join override of session %s (to %s): %s" % (sid, pid or "-", why))


# ------------------------------------------------------------- the verbs


def run_lock_path():
    return daemon_path("run.lock")


_digests = {}   # script name -> ((mtime_ns, size), sha-256 of its bytes)


def own_code():
    """Every script beside this one, with a digest of its bytes: what this
    loop and its uplink import, now or later, is among them, and a script
    added or removed changes the set. When it changes (a plugin update), the
    loop restarts in place on the new code (restart_in_place).

    By content, not mtime: a marketplace update re-clones the whole
    marketplace (Claude Code's refresh clones afresh and swaps the directory
    in), so every script gets a new mtime whether or not sminos changed. The
    stat is the cheap test each tick; a script is read again only when its
    mtime or size moved."""
    here = os.path.dirname(os.path.realpath(__file__))
    out = {}
    try:
        names = os.listdir(here)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".py"):
            continue
        path = os.path.join(here, name)
        try:
            st = os.stat(path)
            sig = (st.st_mtime_ns, st.st_size)
            kept = _digests.get(name)
            if kept is None or kept[0] != sig:
                with open(path, "rb") as f:
                    kept = (sig, hashlib.sha256(f.read()).hexdigest())
                _digests[name] = kept
        except OSError:
            continue  # removed since the listing
        out[name] = kept[1]
    return out


def settle_code(seen, stop):
    """Waits until the scripts, `seen` when their change was noticed, have
    held still for CODE_SETTLE seconds, CODE_SETTLE_MAX at most, or until
    `stop` (SIGTERM) is set."""
    began = still = time.time()
    while not stop and time.time() - still < CODE_SETTLE and time.time() - began < CODE_SETTLE_MAX:
        time.sleep(0.1)
        now = own_code()
        if now != seen:
            seen, still = now, time.time()


def restart_in_place():
    """`daemon run` executed again in this process, on the code as it is now:
    the same interpreter with its options, script and arguments. The pid
    stays, so launchd or systemd sees no exit and applies no restart
    throttle. Across the exec go the pid, stdin, stdout and stderr (the
    service's log), the environment, the working directory and any child
    still running (a derivation, which derive_running reaps once it ends);
    every other descriptor is closed, the run lock's with it, which the new
    image takes again; signal handlers fall back to their defaults until it
    sets them. The uplink is stopped before. Returns only when the exec
    failed (OSError): code that fails to import exits from the new image, and
    the service manager restarts it under its throttle."""
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable] + sys.orig_argv[1:])


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


LEFT_THE_HUB = "this machine left the hub (hub.json is gone): the uplink stays stopped until the machine is enrolled again"


class UplinkSupervisor(threading.Thread):
    """`daemon run`'s keeper of the uplink: while the machine holds a hub
    credential (daemon/hub.json), one `daemon uplink` child runs, restarted
    with backoff whenever it exits, and at once on the credential it holds
    when hub.json changes (an enrollment replaced, or a first one). Once
    hub.json is gone (`sminos hub leave`), the child is stopped and none
    starts until an enrollment writes it again, which daemon.log says.
    `stop` ends it (SIGTERM, then a kill). The child's output goes to
    daemon.log."""

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
                now = credential_bytes()
                if now != held:
                    if now is None:
                        sminos.daemon_log("uplink (pid %d): %s" % (self.proc.pid, LEFT_THE_HUB))
                    else:
                        sminos.daemon_log("uplink (pid %d): hub.json changed; restarting it on the credential as "
                                          "it is now" % self.proc.pid)
                    self.stop_child()
                    backoff = 1
                    break
            else:
                if self.halt.is_set():
                    break
                rc = self.proc.returncode
                how = "on signal %d" % -rc if rc < 0 else "with %d" % rc
                if credential_bytes() is None:
                    # Gone while the child ended: nothing is restarted.
                    sminos.daemon_log("uplink (pid %d) exited %s; %s" % (self.proc.pid, how, LEFT_THE_HUB))
                    backoff = 1
                    continue
                if time.time() - started > UPLINK_BACKOFF_MAX:
                    backoff = 1
                sminos.daemon_log("uplink (pid %d) exited %s; restarting in %ds" % (self.proc.pid, how, backoff))
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
        """Whether the child is gone once the supervisor ended (it is, unless
        the supervisor did not end in time)."""
        self.halt.set()
        self.join(UPLINK_STOP_GRACE + 2)
        return not self.is_alive() and (self.proc is None or self.proc.poll() is not None)


def cmd_run(a):
    """The loop: a tick every `--interval` seconds (from one tick's start to
    the next), or at once when a sender touched daemon/nudge since the last
    one began; the uplink beside it (UplinkSupervisor). SIGTERM ends it after
    the tick in hand, the uplink stopped with it. A change to its scripts,
    once they hold still, stops the uplink and restarts the loop in place on
    the new code (restart_in_place)."""
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
            changed = own_code()
            if changed != code:
                settle_code(changed, stop)
                if stop:
                    break
                me = os.getpid()
                sminos.daemon_log("daemon run (pid %d): its code changed; restarting in place on the new code" % me)
                print("%s its code changed: restarting in place on the new code" % sminos.now())
                # An uplink left running would outlive the exec unnoticed: it
                # ends when its parent's pid changes, and the pid stays.
                if not uplink.stop():
                    sminos.daemon_log("daemon run (pid %d): its uplink did not stop; exiting instead, for the "
                                      "service manager to restart it" % me)
                elif not stop:  # a SIGTERM while the uplink stopped ends the loop instead
                    try:
                        restart_in_place()
                    except OSError as e:
                        sminos.daemon_log("daemon run (pid %d): could not restart in place (%s); exiting for the "
                                          "service manager to restart it" % (me, e))
                break
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
    kept up to date by the harness; the CLI is the sminos plugin's, in the
    clone's `sminos/` folder), and with no usable clone the install is
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
    stable = os.path.join(location, "sminos", "skills", "sminos", "scripts", "sminos.py") if location else ""
    if stable and os.path.isfile(stable):
        return stable
    sminos.die("daemon install: this sminos runs from the versioned plugin cache (%s), which a plugin update "
               "deletes, and the doperpowers marketplace clone it would run instead is missing (%s) — restore it "
               "(claude plugin marketplace add, or update the doperpowers marketplace), or run the install "
               "from a checkout of doperpowers (its sminos/ folder)" % (here, stable or "no doperpowers entry in %s" % known), 1)


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
