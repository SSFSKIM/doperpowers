"""`sminos spawn --on <vm>|new` (EN.G1's plan,
docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, Interfaces §7
and §8): a session opened on a devcloud VM from a session on a Mac.

The Mac side (spawn_on) decides everything it can by itself before devcloud
runs, in §7's order: usage, this machine (a host, not enrolled, named
itself), the caller's route back (an address, a project this enrollment
carries, a reach that is this machine's default), devcloud's CLI, and for
`new` the projects the VM checks out. Then `devcloud vm up --enroll --keep
--expect-creator <short>` for `new`, and the VM side over `devcloud vm ssh
<vm> -- sminos spawn <alias> - --asked-from <request> …`, the task on
standard input. It prints a spawn only on one whole outcome line from the VM
that it can hold to its call; anything else is an outcome that is not known.
It writes nothing in sminos's store.

The VM side is `cmd_spawn` itself (read_request, Answering, admit,
expand_home, hold_to_origin, hold_to_org): the same spawn under the same
locks, refused where this machine is not enrolled, is of another org, holds
another repository's checkout where the Mac inferred the directory, or
would put the session in a project its enrollment does not carry, and ending, for
every way it ends after the request was read, with the outcome line. The
line's shape is one, printed here and accepted here (outcome_whole)."""
import json
import math
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import threading
import time

import sminos

HOST_MARKER = "/etc/devcloud/boot.env"      # devcloud's own test of a host
DEVCLOUD_ON_MIN = (0, 18, 0)                 # the devcloud that has `up --enroll --expect-creator` and `vm owner`
CHECKOUTS = "~/Developer/GitHub"             # where a host's boot checks projects out
LABEL_RE = re.compile(r"[a-z0-9-]{1,20}")    # devcloud's rule for --label
READY_RE = re.compile(r"(\S+)  ready in \d+m\d\ds")   # the one line in which `vm up` names its host
CREATED_RE = re.compile(r"created   (\S+) \(id [^)]*\) from .*")   # where `vm up` first names the VM it made
CAPS_LINE = "caps      "                   # `vm up`'s caps line, printed before it makes anything
ENROLL_WAIT, ENROLL_POLL, REMOTE_TIMEOUT = 660, 30, 480   # seconds; SMINOS_ON_ENROLL_WAIT, _POLL, SMINOS_ON_TIMEOUT
LS_REMOTE_TIMEOUT = 30
PIPE_DRAIN, PIPE_GRACE = 10, 1   # seconds devcloud's output is drained for once it exited; once its bound passed

# `new` always means a VM to be made: a host of that name is reached with `devcloud vm ssh`, never with --on.
NEW = "new"
OUTCOME = "sminos-spawn"
NONCE_RE = re.compile(r"[0-9a-f]{16}")
SHORT_RE = re.compile(r"[0-9a-f]{8}")
HEAD_RE = re.compile(r"[0-9a-f]{40}")
# §8's table: each `why` the VM side says, with the exits it says it with.
WHYS = {"not-enrolled": (1,), "other-org": (1,), "other-repository": (1,), "other": (1, 2, 4)}
BY_KEYS = ("alias", "short", "project", "project_name", "machine")

VM_ONLY = "--vm-project and --vm-confirmed are for the VM that --on new makes: drop them, or pass --on new"
KEPT = ". The VM %(vm)s is kept and %(owner)s owns it: devcloud vm down %(vm)s ends it"
UNREAD = ("spawn --on: this session's reach could not be read (%s), and a session is opened on another machine only "
          "from one whose reach is known to be this machine's default: nothing was spawned")
GONE = "its record is not settled: no running process of it is found on this machine"
NOT_DEFAULT = ("spawn --on: this session's reach is not this machine's default (%s), and a session opened on another "
               "machine takes that machine's default, which could be wider: nothing was spawned. Spawn it here, or "
               "from a session whose reach is the default")


def seconds(name, default):
    try:
        v = float(os.environ.get(name) or default)
    except ValueError:
        return float(default)
    return v if v > 0 else float(default)


# ------------------------------------------------------------------ the outcome line (§8), one shape for both sides


def _text(v):
    return isinstance(v, str) and bool(v)


def outcome_whole(d):
    """Whether `d` is an outcome of §8's shape: a success's fields each of
    its type, or a refusal whose `why` and `exit` are a row of the table.
    Every key of the shape is there with its type (`head` too, null or 40
    hex); a key beyond these is ignored."""
    if not isinstance(d, dict):
        return False
    if d.get("ok") is True:
        p = d.get("project")
        return ("head" in d and isinstance(d.get("refilled"), bool)
                and all(_text(d.get(k)) for k in ("group", "alias", "short", "status", "machine", "cwd"))
                and all(isinstance(d.get(k), str) and sminos.UUID_RE.fullmatch(d[k]) for k in ("seat", "session"))
                and isinstance(p, dict) and _text(p.get("id")) and _text(p.get("name"))
                and (d.get("head") is None or isinstance(d["head"], str) and bool(HEAD_RE.fullmatch(d["head"]))))
    if d.get("ok") is False:
        code, why = d.get("exit"), d.get("why")
        return type(code) is int and isinstance(why, str) and why in WHYS and code in WHYS[why]
    return False


def outcome_line(nonce, d):
    return "%s %s %s" % (OUTCOME, nonce, json.dumps(d, separators=(",", ":"), ensure_ascii=False))


def judge(lines, nonce, alias, code):
    """What the Mac reads in the VM side's standard output (§8): ("ok", d)
    or ("refused", d) for one whole outcome line it holds to its call (the
    alias asked, `devcloud vm ssh`'s exit), else ("unknown", the reason, as
    row 29 words it)."""
    mark = "%s %s " % (OUTCOME, nonce)
    hits = [i for i, line in enumerate(lines) if line.startswith(mark)]
    if not hits:
        return "unknown", "no outcome line came back"
    if len(hits) > 1:
        return "unknown", "more than one outcome line came back"
    if hits[0] != len(lines) - 1:
        return "unknown", "the outcome line is not the last line it printed"
    try:
        d = json.loads(lines[hits[0]][len(mark):])
    except ValueError:
        d = None
    if not outcome_whole(d):
        return "unknown", "the outcome line does not read as one"
    if d["ok"] and d["alias"] != alias:
        return "unknown", "the outcome line names another alias than the one asked"
    if (d["ok"] and code != 0) or (not d["ok"] and d["exit"] != code):
        return "unknown", "the outcome line and the exit status disagree"
    return ("ok" if d["ok"] else "refused"), d


# ------------------------------------------------------------------ the VM side (cmd_spawn under --asked-from)


def read_request(a):
    """`--asked-from`'s value, held to §8's shape; exit 2 with no outcome
    line for anything else. `--wait` beside it is a usage error, answered."""
    try:
        d = json.loads(a.asked_from)
    except ValueError:
        d = None
    by = d.get("by") if isinstance(d, dict) else None
    whole = (isinstance(d, dict) and type(d.get("v")) is int and d["v"] == 1 and isinstance(d.get("nonce"), str)
             and NONCE_RE.fullmatch(d["nonce"]) and _text(d.get("org"))
             and "origin" in d and (d["origin"] is None or isinstance(d["origin"], str))
             and "by" in d and (by is None or isinstance(by, dict) and all(isinstance(by.get(k), str) for k in BY_KEYS)
                  and SHORT_RE.fullmatch(by["short"])))
    if not whole:
        sminos.die("spawn: --asked-from is not a request this version reads", sminos.EXIT_USAGE)
    if a.wait:
        with Answering(d["nonce"]):
            sminos.die("spawn: --asked-from with --wait: the machine that asked watches nothing here")
    return d


class Answering:
    """The VM side's last line on standard output, for every way it ends:
    `ok` prints the success; leaving otherwise (an exit, an exception)
    prints a refusal with the exit it ends with and the `why` set last
    (`refuse`), "other" unless set. An exception once the launcher returned
    a job (spawn_fresh marks the request `launched`) prints none: the job
    may run without a seat, so nothing is a refusal, and the asking machine
    says the outcome is not known; the job is named here."""

    def __init__(self, nonce, request=None):
        self.nonce, self.request, self.why, self.done = nonce, request or {}, "other", False

    def __enter__(self):
        return self

    def refuse(self, why, words):
        self.why = why
        sminos.die(words, 1)

    def ok(self, spawned):
        """The success, held to the shape the asking machine reads: where it
        does not read as one, the spawn is said here and the line is a
        refusal, so that nothing short of a whole success is taken for one."""
        project = spawned["project"]
        d = {"ok": True, "refilled": spawned["verb"] == "re-filled", "group": spawned["group"],
             "alias": spawned["alias"], "short": spawned["short"], "seat": spawned["seat"],
             "session": spawned["session"], "status": spawned["status"],
             "project": {"id": project.id, "name": project.name} if project is not None else None,
             "machine": sminos.host_name(), "cwd": spawned["cwd"], "head": head_of(spawned["cwd"])}
        if not outcome_whole(d):
            sminos.die("spawn: seat %s/%s was spawned here (session %s), and its result could not be reported in the "
                       "outcome line's shape (%s): sminos list here shows it"
                       % (d["group"], d["alias"], d["session"], json.dumps(d, ensure_ascii=False)), 1)
        self.done = True
        print(outcome_line(self.nonce, d), flush=True)

    def __exit__(self, kind, error, tb):
        if self.done:
            return False
        if isinstance(error, SystemExit):
            code = error.code if type(error.code) is int else 0 if error.code is None else 1
        elif (job := self.request.get("launched")):
            sys.stderr.write("sminos: spawn: session %s was launched here, and then this failed: %s; no outcome is "
                             "reported for it, so the machine that asked says it is not known: sminos list here shows "
                             "whether it runs, and claude stop %s stops it\n" % (job, error, job))
            return False
        else:
            code = 1
        sys.stdout.flush()
        print(outcome_line(self.nonce, {"ok": False, "exit": code, "why": self.why}), flush=True)
        return False


def admit(req, answer):
    """Steps 1 and 2: this machine enrolled, and in the org that asked."""
    mine = sminos.enrollment()
    if mine is None:
        answer.refuse("not-enrolled", "spawn: this machine is not enrolled in the org, and a session opened here for "
                                      "another machine would be seen by none: nothing was spawned")
    if mine["org"] != req["org"]:
        answer.refuse("other-org", "spawn: this machine is enrolled in another org than the machine that asked, so "
                                   "the session and its spawner could not reach each other: nothing was spawned")


def expand_home(cwd):
    """Step 3: a `--cwd` that opens `~/`, from this user's home (devcloud
    quotes each word it sends, so no shell expanded it)."""
    if cwd and cwd.startswith("~/"):
        return os.path.join(os.path.expanduser("~"), cwd[2:])
    return cwd


def git(cwd, *args, timeout=30):
    """(exit, stdout stripped) of git in `cwd`; (None, why) when it could not be run."""
    try:
        done = subprocess.run(["git", "-C", cwd, *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "no answer within %ds" % timeout
    except OSError as e:
        return None, "git could not be run: %s" % (e.strerror or e)
    return done.returncode, (done.stdout.strip() if done.returncode == 0 else done.stderr.strip())


def origin_url(cwd):
    """The url origin is configured with in `cwd`'s own worktree, as written
    (git's insteadOf is not applied: what is read is the repository the
    person named, which the VM clones from GitHub); "" for none."""
    code, out = git(cwd, "config", "--get", "remote.origin.url")
    return out if code == 0 else ""


def head_of(cwd):
    """The commit checked out at `cwd` (40 hex), or None where it is no checkout."""
    if not sminos.common_git_dir(cwd):
        return None
    code, out = git(cwd, "rev-parse", "HEAD")
    return out if code == 0 and HEAD_RE.fullmatch(out) else None


def hold_to_origin(req, cwd, answer):
    """Step 4: where the Mac inferred the directory (`origin` given), it
    must be a checkout of that repository."""
    if req["origin"] is None:
        return
    if not sminos.common_git_dir(cwd):
        what = "no checkout"
    else:
        key = sminos.remote_key(origin_url(cwd))
        what = "a checkout of %s" % key if key else "a checkout with no origin"
        if key == req["origin"]:
            return
    answer.refuse("other-repository", "spawn: %s is %s, and the machine that asked took it for its checkout of %s: "
                                      "nothing was spawned. Name the directory with --cwd" % (cwd, what, req["origin"]))


def hold_to_org(req, cwd, answer):
    """The project the spawn would be in (spawn_fresh's, of `cwd`'s group)
    is one this machine's enrollment carries, by the uplink's own test, as
    the Mac holds its spawner's: one it does not carry could neither reach
    the spawner nor be seen by it. An explicit --cwd included."""
    project = sminos.seat_project({"cwd": cwd, "group": sminos.derive_group(cwd)})
    why = sminos.not_carried(project, req["org"]) if project is not None else ""
    if why:
        answer.refuse("other", "spawn: %s is in project %s, which this machine's enrollment does not carry (%s), so "
                               "the session there and the machine that asked could not reach each other: nothing was "
                               "spawned. Name a directory of a project the org shares with --cwd"
                      % (cwd, project.name, why))


# ------------------------------------------------------------------ the Mac side


def reach_refusal(session):
    """Why `--on` is refused for the session's reach, as row 10 words it:
    it could not be read, or it is not this machine's default; "" when it
    is the default. Reads the record as it stands, and writes nothing."""
    records = sminos.records_module()
    if records.unreadable(session):
        return UNREAD % "its record cannot be read"
    rec = records.read(session)
    if rec is None:
        return UNREAD % "it has no record yet: its own hook writes one when a turn ends, and sminos list does"
    # The engine's record of its running process, read afresh (the first read is minutes old by the last), inbox
    # or not; where none is found, nothing says the record will not be replaced, whatever it rests on.
    peer = sminos.running_now(session)
    if peer is None:
        return UNREAD % GONE
    if not sminos.provenance_settled(rec, peer):
        if records.basis(rec) == "hook" and records.is_final(rec):
            return UNREAD % ("its record is not settled: it is a background job's, which may still take the reach "
                             "of a session it continues; sminos list records a hand-off, and a job that continues "
                             "none spawns from another session")
        return UNREAD % ("its record is not settled: it rests on this machine's defaults alone until its own hook, "
                         "at the end of a turn, or sminos list gives it more")
    audience = sminos.audience_module()
    access, shares, _ = audience.policy_of(rec)
    if access != audience.DEFAULT_ACCESS:
        return NOT_DEFAULT % ("its access is %s" % access)
    if shares:
        return NOT_DEFAULT % "it has shares"
    return ""


class Call:
    """One `spawn --on`: what was decided, and the VM once one was made."""

    def __init__(self, a):
        self.a = a
        self.new = a.on == NEW
        self.session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        if not sminos.UUID_RE.fullmatch(self.session):
            self.session = ""
        self.made = None          # the VM `vm up` made, once it did
        self.ready = []           # the hosts `vm up`'s ready lines named, as its output was read
        self.created = []         # the VMs its `created` lines named
        self.past_caps = False    # whether it printed its caps line, after which it may make a VM
        self.devcloud = ""
        self.checked = None       # (branch, commit) of a derived project, for row 33
        self.reaching = None      # the VM a run of the VM side was started on whose outcome is not yet read

    def vm(self):
        """The VM made: the one `vm up` was seen to name, once one was."""
        return self.made or (self.ready[0] if len(self.ready) == 1 else None)

    def owner(self):
        thread = sminos.threads_module().thread_of(self.session) if self.session else None
        return "this session's thread" if thread is not None else "this session"

    def kept(self):
        vm = self.vm()
        if vm is None:
            return ""
        return KEPT % {"vm": vm, "owner": self.owner()}

    def refuse(self, words, code=1):
        sminos.die(words + self.kept(), code)


def spawn_on(a):
    """`spawn` with --on: the checks in §7's order, `vm up` for `new`, the
    VM side over `devcloud vm ssh`, the wait, the line. Exits; returns nothing."""
    c = Call(a)
    usage(c)
    previous = signal.signal(signal.SIGTERM, _stopped)
    try:
        checked_and_run(c)
    except (Stopped, KeyboardInterrupt):
        # Outside a run of devcloud (run_devcloud says its own): between two tries of the wait, mostly.
        if c.reaching is not None:
            c.refuse("spawn --on: stopped before the outcome on %s was read: a session may or may not have started "
                     "there, and devcloud vm ssh %s -- sminos list shows" % (c.reaching, c.reaching))
        c.refuse("spawn --on: stopped: nothing was spawned")
    finally:
        signal.signal(signal.SIGTERM, previous)


def checked_and_run(c):
    """spawn_on's steps after usage, in §7's order."""
    a = c.a
    if os.path.exists(HOST_MARKER):
        c.refuse("spawn --on: this machine is a devcloud host, and devcloud's driver, which makes and reaches hosts, "
                 "runs on a Mac only: nothing was spawned. Run it from a session on a Mac; here, sminos spawn without "
                 "--on spawns on this machine")
    enrolled = sminos.enrollment()
    if enrolled is None:
        c.refuse("spawn --on: this machine is not enrolled in the org, so a session on another machine could tell "
                 "this one nothing and would not be listed here: nothing was spawned")
    if not c.new and a.on.lower() == sminos.host_name().lower():
        c.refuse("spawn --on: %s is this machine: drop --on" % a.on, sminos.EXIT_USAGE)
    by = route_back(c, enrolled) if c.session else None
    devcloud(c)
    cwd, projects = os.getcwd(), None
    if c.new:
        if not c.session:
            c.refuse("spawn --on new: no session runs this, so the VM would have no owner: run it from a session, or "
                     "make the VM yourself (devcloud vm up) and name it (sminos spawn --on <name>)")
        projects = a.vm_project or [derived_project(c, cwd)]
    directory, origin = where(c, cwd, projects)
    vm = make_vm(c, projects) if c.new else a.on
    request = {"v": 1, "nonce": secrets.token_hex(8), "org": enrolled["org"], "origin": origin, "by": by}
    remote(c, vm, request, directory)


def usage(c):
    a = c.a
    if not sminos.valid_name(a.alias):
        sminos.die("bad alias: %s" % a.alias)
    if a.alias in ("human", "all"):
        sminos.die("the alias '%s' is reserved" % a.alias)
    if (a.vm_project or a.vm_confirmed) and not c.new:
        sminos.die(VM_ONLY)
    if a.wait:
        sminos.die("spawn --on: --wait watches a seat of this machine, and this seat is made on another: drop it (the "
                   "session reports with sminos say)")
    if a.settings is not None:
        sminos.die("spawn --on: --settings names a file of this machine, which the other machine does not hold: drop "
                   "it (the session runs on that machine's settings)")
    if a.asked_from is not None:
        sminos.die("spawn --on: --asked-from is the form the other machine's sminos is called with: drop it")
    if a.cwd and not (os.path.isabs(a.cwd) or a.cwd.startswith("~/")):
        sminos.die("spawn --on: --cwd is a path on the other machine: give it absolute, or from the home there as ~/…")
    if a.task == "":
        # An unset variable, say: the other machine refuses it (cmd_spawn), after `new` has made a VM for it.
        sminos.die("spawn --on: the task is empty: give it as the argument, or as - with the text on standard input")
    sminos.parse_stamps(a.stamp)   # as the other machine's spawn reads them, refused here before anything is made


def route_back(c, enrolled):
    """(e): the calling session's address, its project carried by this
    enrollment, its reach; the spawner the request names."""
    address = sminos.session_address(c.session, os.getcwd())
    if not address:
        c.refuse("spawn --on: this session is no member of a project yet (sminos who prints no address), so the "
                 "session opened there would have no one to answer: nothing was spawned")
    project = sminos.session_project(c.session, sminos.launch_cwd(c.session, fallback=os.getcwd()))
    why = sminos.not_carried(project, enrolled["org"])
    if why:
        c.refuse("spawn --on: this session's project, %s, is not one this machine's enrollment carries (%s), so "
                 "nothing a session on another machine says would reach it: nothing was spawned. Run it from a "
                 "session in a project the org shares" % (project.name, why))
    reach(c)
    parsed = sminos.parse_addresses(address)
    alias = (parsed[0]["alias"] if parsed else "") or c.session[:8]
    return {"alias": alias, "short": c.session[:8], "project": project.id, "project_name": project.name,
            "machine": sminos.host_name()}


def reach(c):
    if c.session and (why := reach_refusal(c.session)):
        c.refuse(why)


def devcloud(c):
    """(f): devcloud's CLI, found as owned_by finds it, at DEVCLOUD_ON_MIN
    or later (the copy SMINOS_DEVCLOUD names is taken at its word)."""
    threads = sminos.threads_module()
    where, path = threads.find_devcloud()
    if where is None:
        c.refuse("spawn --on: no devcloud CLI was found here (looked at: %s), and the devcloud plugin is what makes "
                 "and reaches a VM: nothing was spawned" % path)
    if where != "$SMINOS_DEVCLOUD":
        version = threads.devcloud_version(path)
        if version is None or version < DEVCLOUD_ON_MIN:
            c.refuse("spawn --on: the devcloud at %s is %s, and spawn --on needs %s or later: update the devcloud "
                     "plugin; nothing was spawned" % (path, ".".join(map(str, version)) if version
                                                      else "of no readable version", ".".join(map(str, DEVCLOUD_ON_MIN))))
    c.devcloud = path


def checkout_url(cwd):
    """origin_url of `cwd`'s worktree; "" where `cwd` is no checkout."""
    return origin_url(cwd) if sminos.common_git_dir(cwd) else ""


def github_repo(url):
    """(owner, repo) of the repository at `url` when it is GitHub's; None otherwise."""
    host, path, _ = sminos.parse_remote(url) if url else ("", "", "")
    parts = path.split("/")
    return (parts[0], parts[1]) if host == "github.com" and len(parts) == 2 and all(parts) else None


def derived_project(c, cwd):
    """`<owner>/<repo>@<branch>` read in the caller's own worktree, taken
    only when origin, asked by the exact ref, holds the branch at this
    worktree's commit (rows 14 to 18). Origin is asked at the url read
    (origin_url): a linked worktree's own configuration can add a url to
    the remote, which `git ls-remote origin` would not take first."""
    url = checkout_url(cwd)
    repo = github_repo(url)
    if repo is None:
        c.refuse("spawn --on new: %s is in no repository whose origin is on GitHub, so there is nothing to tell the "
                 "VM to check out: name it with --vm-project owner/repo[@ref]" % cwd)
    name = "%s/%s" % repo
    # The full ref: --short answers heads/<branch> where a tag has the branch's name.
    code, ref = git(cwd, "symbolic-ref", "-q", "HEAD")
    branch = ref[len("refs/heads/"):] if code == 0 and ref.startswith("refs/heads/") else ""
    if not branch:
        c.refuse("spawn --on new: this checkout is on no branch, and the VM clones a branch or a ref from GitHub: "
                 "check a pushed branch out, or name the ref with --vm-project %s@<ref>" % name)
    _, commit = git(cwd, "rev-parse", "HEAD")
    code, out = git(cwd, "ls-remote", url, ref, timeout=LS_REMOTE_TIMEOUT)
    if code != 0:
        said = (out.splitlines() or [""])[-1] if code is not None else out
        c.refuse("spawn --on new: origin did not say where %s is (%s): try again, or name the ref with --vm-project "
                 "%s@<ref>" % (branch, said or "git ls-remote exited %s" % code, name))
    rows = [line.split("\t") for line in out.splitlines() if line.strip()]
    rows = [r for r in rows if len(r) == 2 and r[1] == ref]
    if not rows:
        c.refuse("spawn --on new: origin has no branch %s, and the VM clones from GitHub, so it would not get this "
                 "work: push it (git push -u origin %s), or name what the VM checks out with --vm-project %s@<ref>"
                 % (branch, branch, name))
    if rows[0][0] != commit:
        c.refuse("spawn --on new: origin's %s is at %s and this checkout is at %s, so the VM would clone without what "
                 "differs: push it, or name the ref with --vm-project %s@<ref>" % (branch, rows[0][0], commit, name))
    c.checked = (branch, commit)
    return "%s@%s" % (name, branch)


def where(c, cwd, projects):
    """(g): the session's directory on the VM and the request's `origin`:
    --cwd as given (origin null), else the VM's checkout of the repository,
    which the VM holds to it."""
    if c.a.cwd:
        return c.a.cwd, None
    if projects is not None:
        first = projects[0].split("@", 1)[0]
        parts = first.split("/")
        if len(parts) != 2 or not all(parts):
            c.refuse("spawn --on new: %s is a registry name, whose checkout only its registry places: name the "
                     "session's directory on the VM with --cwd" % projects[0], sminos.EXIT_USAGE)
        owner, repo = parts
    else:
        found = github_repo(checkout_url(cwd))
        if found is None:
            c.refuse("spawn --on: %s is in no repository whose origin is on GitHub, so the session's directory on %s "
                     "cannot be derived: name it with --cwd" % (cwd, c.a.on), sminos.EXIT_USAGE)
        owner, repo = found
    return "%s/%s" % (CHECKOUTS, repo), ("github.com/%s/%s" % (owner, repo)).lower()


def child_env():
    """This process's environment, with the directory of sminos's own
    interpreter first on PATH (as owned_by gives devcloud's driver)."""
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    return env


class Stopped(BaseException):
    """A SIGTERM to sminos while devcloud runs: given to devcloud (stop_tree)."""


def _stopped(signum, frame):
    raise Stopped()


def run_devcloud(c, args, stdin=None, timeout=None, keep_err=False, vm=None, nonce=None):
    """devcloud run with `args`: (exit, standard output's lines, standard
    error's text when kept, whether the bound passed). Each line of its
    output is written through as it comes, but this call's outcome lines
    (§8: `nonce`'s, on `vm ssh <vm>`'s stream), held for the judgment; its
    standard error likewise. A signal to sminos, from the moment the
    handler is in place, is given to devcloud (stop_tree), whose own
    handling decides what becomes of anything it made; then sminos exits,
    saying where a session may have started and what VM is kept."""
    threads = sminos.threads_module()
    lines, err, pumps, proc = [], [], [], None
    mark = "%s %s " % (OUTCOME, nonce) if nonce else None
    up = args[:2] == ["vm", "up"]

    def pump_out():
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            lines.append(line)
            if up and (m := READY_RE.fullmatch(line)):
                c.ready.append(m.group(1))
            if up and (m := CREATED_RE.fullmatch(line)):
                c.created.append(m.group(1))
            if up and line.startswith(CAPS_LINE):
                c.past_caps = True
            if mark is None or not line.startswith(mark):
                sys.stdout.write(line + "\n")
                sys.stdout.flush()

    def pump_err():
        for raw in proc.stderr:
            text = raw.decode("utf-8", "replace")
            if keep_err:
                err.append(text)
            sys.stderr.write(text)
            sys.stderr.flush()

    def feed():
        try:
            proc.stdin.write(stdin.encode("utf-8", "surrogateescape"))
            proc.stdin.close()
        except OSError:
            pass

    previous = signal.signal(signal.SIGTERM, _stopped)
    timed_out = False
    try:
        try:
            proc = subprocess.Popen([c.devcloud] + args,
                                    stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_env())
        except OSError as e:
            c.refuse("spawn --on: the devcloud at %s could not be run: %s" % (c.devcloud, e.strerror or e))
        pumps += [(threading.Thread(target=pump_out, daemon=True), proc.stdout),
                  (threading.Thread(target=pump_err, daemon=True), proc.stderr)]
        if stdin is not None:
            pumps.append((threading.Thread(target=feed, daemon=True), proc.stdin))
        for t, _ in pumps:
            t.start()
        try:
            code = proc.wait(timeout)
        except subprocess.TimeoutExpired:
            threads.stop_tree(proc.pid, proc.wait)
            code, timed_out = proc.wait(), True
        drained(pumps, PIPE_GRACE if timed_out else PIPE_DRAIN)
    except (Stopped, KeyboardInterrupt):
        if proc is not None:
            if proc.returncode is None:
                threads.stop_tree(proc.pid, proc.wait)
            drained([(t, f) for t, f in pumps if t.ident is not None], PIPE_DRAIN)
        if vm is not None:
            c.refuse("spawn --on: stopped while devcloud vm ssh ran, and devcloud was stopped with it: a session may "
                     "or may not have started there, and devcloud vm ssh %s -- sminos list shows" % vm)
        c.refuse("spawn --on: stopped while devcloud ran; devcloud was stopped with it, and its own lines above say "
                 "what became of anything it made")
    finally:
        signal.signal(signal.SIGTERM, previous)
    return code, lines, "".join(err), timed_out


def drained(pumps, within):
    """Each pump given what is left of `within` seconds to finish, then the
    pipes of those that did closed: one still blocked on its read is a pipe
    a descendant of devcloud holds open (the ssh under `vm ssh`), and a
    close of it would wait for that descendant, where this process's exit
    does not."""
    deadline = time.monotonic() + within
    for t, _ in pumps:
        t.join(max(0.0, deadline - time.monotonic()))
    closed([f for t, f in pumps if not t.is_alive()])


def closed(files):
    for f in files:
        if f is not None:
            f.close()


def make_vm(c, projects):
    """(h): `devcloud vm up` for `new`; the host its `ready` line names."""
    a = c.a
    args = ["--enroll", "--keep", "--expect-creator", c.session[:8]]
    if LABEL_RE.fullmatch(a.alias):
        args += ["--label", a.alias]
    for p in projects:
        args += ["--project", p]
    if a.vm_confirmed:
        args.append("--confirmed")
    sminos.note("making a VM (a few minutes; devcloud's own lines follow): devcloud vm up %s" % shlex.join(args))
    code, _, err, _ = run_devcloud(c, ["vm", "up"] + args, keep_err=True)
    if code != 0:
        words = ("spawn --on new: devcloud vm up exited %d; its own lines above say why, and what became of any VM it "
                 "made. Nothing was spawned%s" % (code, ". The cap is the person's: after their yes to this exact "
                                                       "request, pass --vm-confirmed" if code == 4 else ""))
        # A VM made with --keep has no lease to bound it: one devcloud named and did not delete (its recount's own
        # `deleted <name>`) is said kept, as after `ready`. None named after its caps line, other than a cap's or
        # a provider's refusal, may still exist: a provider can make one and lose the answer that names it.
        c.ready = []
        named = c.created[0] if len(c.created) == 1 else None
        if named is not None and not re.search(r"\bdeleted %s\b" % re.escape(named), err):
            c.made = named
        elif named is None and c.past_caps and code not in (3, 4):
            sys.stderr.write("sminos: %s\n" % words)
            sminos.die("spawn --on new: a VM may have been made all the same, since a provider can make one and lose "
                       "the answer that names it: before running this again, devcloud vm ls shows it, kept and owned "
                       "by %s, and devcloud vm down <name> removes it" % c.owner(), code)
        c.refuse(words, code)
    if len(c.ready) != 1:
        c.refuse("spawn --on new: devcloud vm up succeeded and did not name one host where sminos reads it: find the "
                 "VM with devcloud vm ls, then sminos spawn --on <name>")
    c.made = c.ready[0]
    return c.made


def carried(a, directory):
    """The VM side's flags: the directory, the mode, and each carried flag
    given, a free value as one `--flag=value` word, so that a value the
    Mac's parser took (`--brief=--review`) is not read there as a flag."""
    out = ["--cwd", directory, "--permission-mode", a.permission_mode]
    for flag, value in (("--role", a.role), ("--brief", a.brief), ("--worktree", a.worktree or None),
                        ("--model", a.model), ("--effort", a.effort)):
        if value is not None:
            out.append("%s=%s" % (flag, value))
    for stamp in a.stamp or []:
        out.append("--stamp=%s" % stamp)
    return out


def remote(c, vm, request, directory):
    """(i): the VM side, each run preceded by the reach rule read afresh,
    tried again only on its own `not-enrolled`, for `new` only; then the
    line (rows 25 to 33)."""
    a = c.a
    # The positionals after `--`, so that an alias the Mac's parser took after its own (`-alias`) is one there.
    args = ["vm", "ssh", vm, "--", "sminos", "spawn", "--asked-from",
            json.dumps(request, separators=(",", ":"), ensure_ascii=False)] + carried(a, directory) + ["--", a.alias, "-"]
    bound = seconds("SMINOS_ON_TIMEOUT", REMOTE_TIMEOUT)
    wait = seconds("SMINOS_ON_ENROLL_WAIT", ENROLL_WAIT)
    deadline = None
    while True:
        reach(c)
        given = bound
        if deadline is not None:
            # The wait bounds every try it starts: none at or past its end, and each given only what is left,
            # read last before the try (the reach rule's read takes time too).
            left = deadline - time.monotonic()
            if left <= 0:
                c.refuse("spawn --on new: %s did not enroll within %d minutes: nothing was spawned. Once sminos "
                         "machines lists it, sminos spawn --on %s spawns there" % (vm, round(wait / 60), vm))
            given = min(bound, left)
        c.reaching = vm
        code, lines, err, timed_out = run_devcloud(c, args, stdin=a.task, timeout=given, keep_err=True, vm=vm,
                                                   nonce=request["nonce"])
        if timed_out:
            c.refuse("spawn --on: %s gave no outcome within %d minutes, and the call was stopped: a session may or may "
                     "not have started there, and devcloud vm ssh %s -- sminos list shows"
                     % (vm, math.ceil(given / 60), vm))
        verdict, d = judge(lines, request["nonce"], a.alias, code)
        if verdict == "unknown":
            unknown(c, vm, d, code, err)
        if verdict == "ok":
            break
        if d["why"] != "not-enrolled":
            c.refuse("spawn --on: %s's sminos answered exit %d; its line above says why, and what, if anything, exists "
                     "there" % (vm, d["exit"]), d["exit"])
        c.reaching = None   # it answered that it is not enrolled: nothing was spawned by this try
        if not c.new:
            c.refuse("spawn --on: %s is not enrolled in the org (no endpoint on it has been welcomed: a host made "
                     "without the MAWS project, or one whose enrollment has not finished; devcloud vm ssh %s -- "
                     "devcloud status shows its maws step), so no other machine would see a session there: nothing "
                     "was spawned" % (vm, vm))
        if deadline is None:
            deadline = time.monotonic() + wait
            sminos.note("%s is up and not enrolled in the org yet: waiting up to %d minutes for its endpoint (the host "
                        "tries again every 5), then spawning" % (vm, round(wait / 60)))
        time.sleep(min(seconds("SMINOS_ON_ENROLL_POLL", ENROLL_POLL), max(0.0, deadline - time.monotonic())))
    print("seat %s on %s: %s/%s  [%s / %s]  status=%s  (message it: sminos say \"@%s …\"; it is listed here once %s's "
          "events arrive)" % ("re-filled" if d["refilled"] else "spawned", d["machine"], d["group"], d["alias"],
                              d["short"], d["seat"], d["status"], d["session"][:8], d["machine"]), flush=True)
    if c.made is not None:
        sminos.note(c.kept()[len(". The VM "):] + ", and it sends a notice after three idle days")
        # Only where the session runs in the checkout the branch was derived for: an explicit --cwd need not be it.
        if c.checked is not None and not a.cwd and d["head"] and d["head"] != c.checked[1]:
            sminos.note("origin's %s moved while the VM was made: the VM's checkout is at %s" % (c.checked[0], d["head"]))
    sys.exit(0)


def unknown(c, vm, reason, code, err):
    """Row 29, with row 24's note after it; exits."""
    words = ("spawn --on: the outcome on %s is not known (%s): a session may or may not have started there, and "
             "devcloud vm ssh %s -- sminos list shows" % (vm, reason, vm))
    if reason == "no outcome line came back":
        words += ". What devcloud or the host printed above may say why"
        if code == 2:
            words += ". It ended with a usage error, so its sminos may predate this call"
    sys.stderr.write("sminos: %s%s\n" % (words, c.kept()))
    if "devcloud vm: no VM named" in err and is_org_machine(vm):
        sminos.note("%s is a machine of this org that devcloud has no host for. If it is a Mac: a session is not opened "
                    "on a Mac from another machine in this version, since a Mac's login keychain is closed to an ssh "
                    "session and claude needs it; open it on that Mac" % vm)
    sys.exit(code or 1)


def is_org_machine(name):
    d = sminos.org_directory()
    return bool(d) and any(m["name"].lower() == name.lower() for m in d["machines"])
