"""`sminos spawn --on <vm>|new` (EN.G1's plan,
docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, Interfaces §7
and §8): a session opened on a devcloud VM from a session on a Mac.

The Mac side (spawn_on) decides everything it can by itself before devcloud
runs, in §7's order: usage, this machine (a host, not enrolled, named
itself), the caller's route back (an address, a project this enrollment
carries, a reach that is this machine's default), devcloud's CLI, and for
`new` the projects the VM checks out. Then `devcloud vm up --enroll --keep
--expect-creator <short>` for `new`, and the VM side over `devcloud vm ssh
<vm> -- env -u CLAUDE_CODE_SESSION_ID sminos spawn <alias> - --asked-from
<request> …`, the task on standard input. It prints a spawn only on one
whole outcome line from the VM that it can hold to its call; anything else
is an outcome that is not known. It writes nothing in sminos's store.

The VM side is `cmd_spawn` itself (read_request, Answering, admit,
expand_home, hold_to_origin, hold_to_org, hold_to_spawner): the same spawn
under the same locks, refused where this machine is not enrolled, is of
another org, holds another repository's checkout where the Mac inferred the
directory, would put the session in a project its enrollment does not
carry, or has not read the spawner the request names from its log yet
(which the Mac waits out), and ending, for
every way it ends after the request was read, with the outcome line. The
line's shape is one, printed here and accepted here (outcome_whole).

`--channel` (EN.G2's plan, docs/doperpowers/plans/2026-11-23-sminos-
environments-en-g2.md, Interfaces §1): the Mac resolves and checks the
channels before devcloud runs (channels_asked) and sends them in the
request; the VM side holds them to its kept welcome and its enrollment
before the launch (hold_to_channels; `welcome-unknown` the Mac waits out),
gives and asks the spawner's qualified address (spawner_tag), places the
thread after the launch (sminos_channels.place_spawned) and reports each
placement in the outcome's `channels` (placed_whole), which the Mac holds
to its call (judge) and says, one line a channel (said_placements); a call
lost after the request names every seat on the VM, its engine's jobs and
each channel's roster (Call.look)."""
import contextlib
import io
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
# `vm up`'s recount saying it deleted the VM it made, in its two forms, the whole line on standard error.
DELETED_RE = re.compile(r"devcloud vm: (?:over the count cap \(.*\); deleted (?P<cap>\S+): ask the person, then pass "
                        r"--confirmed|the recount after the create failed: .*; deleted (?P<failed>\S+))")
MAYBE = ("spawn --on new: a VM may have been made all the same, since a provider can make one and lose the answer that "
         "names it: before running this again, devcloud vm ls shows it, kept and owned by %s, and devcloud vm down "
         "<name> removes it")
ENROLL_WAIT, ENROLL_POLL, REMOTE_TIMEOUT = 660, 30, 480   # seconds; SMINOS_ON_ENROLL_WAIT, _POLL, SMINOS_ON_TIMEOUT
LS_REMOTE_TIMEOUT = 30
PIPE_DRAIN, PIPE_GRACE = 10, 1   # seconds devcloud's output is read for once it exited unbounded; past a deadline

# `new` always means a VM to be made: a host of that name is reached with `devcloud vm ssh`, never with --on.
NEW = "new"
OUTCOME = "sminos-spawn"
NONCE_RE = re.compile(r"[0-9a-f]{16}")
SHORT_RE = re.compile(r"[0-9a-f]{8}")
HEAD_RE = re.compile(r"[0-9a-f]{40}")
# §8's table: each `why` the VM side says, with the exits it says it with.
WHYS = {"not-enrolled": (1,), "other-org": (1,), "other-repository": (1,), "spawner-unknown": (1,),
        "spawner-shadowed": (1,), "welcome-unknown": (1,), "other": (1, 2, 4)}
# The VM side's refusals the Mac waits out (row 26, 26a; `welcome-unknown`, EN.G2's §1, answered only to a request
# that carries channels).
WAITED_ON = ("not-enrolled", "spawner-unknown", "welcome-unknown")
EXIT_LATER = 75   # row 27a: the VM had not read the spawner by the wait's end; sysexits' EX_TEMPFAIL, try again later
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
    hex), and on any line the optional `not_carried`, where it is, a
    string (on a success, present at all, the seat is not carried, a word
    this Mac does not know included); a key beyond these is ignored."""
    if not isinstance(d, dict) or not isinstance(d.get("not_carried", ""), str):
        return False
    if d.get("ok") is True and "channels" in d and not placed_whole(d["channels"]):
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


def placed_whole(v):
    """Whether a success's `channels` reads as EN.G2's §1 has it: a list of
    {id, state, why}, each id a channel's, `applied` with why "" or
    `unchanged`, `refused` with `limit`, `failed` with a word (one this copy
    does not know included: it is printed as itself)."""
    if not isinstance(v, list):
        return False
    for e in v:
        if not (isinstance(e, dict) and sminos.is_channel_id(e.get("id")) and isinstance(e.get("why"), str)):
            return False
        state, why = e.get("state"), e["why"]
        if not (state == "applied" and why in ("", "unchanged") or state == "refused" and why == "limit"
                or state == "failed" and why):
            return False
    return True


def outcome_line(nonce, d):
    return "%s %s %s" % (OUTCOME, nonce, json.dumps(d, separators=(",", ":"), ensure_ascii=False))


def judge(lines, nonce, alias, code, channels=None):
    """What the Mac reads in the VM side's standard output (§8): ("ok", d)
    or ("refused", d) for one whole outcome line it holds to its call (the
    alias asked, `devcloud vm ssh`'s exit, and where `channels` were asked,
    a success's `channels` naming exactly their ids in order, or none at
    all: an older VM's), else ("unknown", the reason, as row 29 words it)."""
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
    if d["ok"] and channels and "channels" in d and [e["id"] for e in d["channels"]] != list(channels):
        return "unknown", "the outcome line's channels are not the ones asked"
    return ("ok" if d["ok"] else "refused"), d


# ------------------------------------------------------------------ the VM side (cmd_spawn under --asked-from)


def request_whole(d):
    """Whether `d` is a request of §8's shape, and where it carries
    `channels` (EN.G2's §1), a list of 1 to 128 {id, name}, each id a
    channel's, each name a name, no id twice: the VM side's test, which the
    Mac runs on the request it will send before it calls devcloud."""
    by = d.get("by") if isinstance(d, dict) else None
    return bool(isinstance(d, dict) and type(d.get("v")) is int and d["v"] == 1 and isinstance(d.get("nonce"), str)
                and NONCE_RE.fullmatch(d["nonce"]) and _text(d.get("org"))
                and "origin" in d and (d["origin"] is None or isinstance(d["origin"], str))
                and "by" in d and (by is None or isinstance(by, dict)
                                   and all(isinstance(by.get(k), str) for k in BY_KEYS)
                                   and SHORT_RE.fullmatch(by["short"]))
                and ("channels" not in d or channels_whole(d["channels"])))


def channels_whole(v):
    return (isinstance(v, list) and 1 <= len(v) <= sminos.threads_module().CHANNEL_LIMIT
            and all(isinstance(c, dict) and sminos.is_channel_id(c.get("id")) and isinstance(c.get("name"), str)
                    and sminos.valid_name(c["name"]) for c in v)
            and len({c["id"] for c in v}) == len(v))


def read_request(a):
    """`--asked-from`'s value, held to §8's shape (request_whole); exit 2
    with no outcome line for anything else. `--wait` beside it is a usage
    error, answered."""
    try:
        d = json.loads(a.asked_from)
    except ValueError:
        d = None
    if not request_whole(d):
        sminos.die("spawn: --asked-from is not a request this version reads", sminos.EXIT_USAGE)
    by = d["by"]
    if a.wait:
        with Answering(d["nonce"]):
            sminos.die("spawn: --asked-from with --wait: the machine that asked watches nothing here")
    # The protocol's fields alone: what this side marks on the request (`launched`, `unanswered`) is its own,
    # never a key the wire carried.
    # The spawner's full session id, which an older Mac does not send: kept only whole and begun by its short, so the
    # VM side can hold the launch until its own log answers for that session (hold_to_spawner).
    session = by.get("session") if by is not None else None
    whole_id = isinstance(session, str) and sminos.UUID_RE.fullmatch(session) and session[:8] == by["short"]
    req = {"v": d["v"], "nonce": d["nonce"], "org": d["org"], "origin": d["origin"],
           "by": None if by is None else {**{k: by[k] for k in BY_KEYS}, **({"session": session} if whole_id else {})}}
    if "channels" in d:
        req["channels"] = [{"id": c["id"], "name": c["name"]} for c in d["channels"]]
    return req


class Answering:
    """The VM side's last line on standard output, for every way it ends:
    `ok` prints the success; leaving otherwise (an exit, an exception)
    prints a refusal with the exit it ends with and the `why` set last
    (`refuse`), "other" unless set. Once the launcher returned a job
    (spawn_fresh marks the request `launched`), any end but a whole success
    prints none, an exit or an exception alike: the job may run without a
    seat, so nothing is a refusal, and the asking machine says the outcome
    is not known; the job is named here. So too where the launcher was
    started and gave no answer (`unanswered`): a job may run that no one
    can name."""

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
        # Where channels were placed, the seat's project and its carriage as the placement's own fresh reads found
        # them (§1), one result: a project it read is the one named; none read, the launch's, with a word that
        # promises no reach. A spawn without channels reads its carriage here, as G1 does.
        carriage = spawned.get("carriage") if self.request.get("channels") else None
        if carriage is not None and carriage["project"] is not None:
            project = carriage["project"]
        d = {"ok": True, "refilled": spawned["verb"] == "re-filled", "group": spawned["group"],
             "alias": spawned["alias"], "short": spawned["short"], "seat": spawned["seat"],
             "session": spawned["session"], "status": spawned["status"],
             "project": {"id": project.id, "name": project.name} if project is not None else None,
             "machine": sminos.host_name(), "cwd": spawned["cwd"], "head": head_of(spawned["cwd"])}
        # The project the seat was filed in (the engine's directory, a --worktree's included), when this machine's
        # enrollment does not carry it: one of sminos.NOT_CARRIED_WORDS, which an older Mac ignores, or
        # sminos_channels.CARRIAGE_UNREAD.
        if carriage is not None:
            why = carriage["not_carried"]
        else:
            why = sminos.not_carried(project, self.request["org"]) if project is not None and self.request else ""
        if why:
            d["not_carried"] = why
        if self.request.get("channels"):
            d["channels"] = spawned.get("channels") or []   # one entry a channel asked (place_spawned)
        if not outcome_whole(d):
            sminos.die("spawn: seat %s/%s was spawned here (session %s), and its result could not be reported in the "
                       "outcome line's shape (%s): sminos list here shows it"
                       % (d["group"], d["alias"], d["session"], json.dumps(d, ensure_ascii=False)), 1)
        self.done = True
        print(outcome_line(self.nonce, d), flush=True)

    def __exit__(self, kind, error, tb):
        if self.done:
            return False
        code = (error.code if type(error.code) is int else 0 if error.code is None else 1) \
            if isinstance(error, SystemExit) else 1
        if self.request.get("unanswered"):
            return False   # spawn_fresh said why: a job may run, so this is no refusal either (§8 step 8)
        if (job := self.request.get("launched")):
            # After a launch nothing is a refusal, an exit or an exception alike (§8 steps 6 and 8).
            what = "it ended with exit %d, its own line above saying why" % code if isinstance(error, SystemExit) \
                else str(error)
            sys.stderr.write("sminos: spawn: session %s was launched here, and then this failed: %s; no outcome is "
                             "reported for it, so the machine that asked says it is not known: sminos list here shows "
                             "whether it runs, and claude stop %s stops it\n" % (job, what, job))
            return False
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


def hold_to_spawner(req, cwd, alias, answer):
    """Step 4b: where the request names the spawner's session, the child's
    own first `say "@<short>"`, asked before the launch: the resolver
    that `say` runs (sminos._resolve_tag), from the project the seat
    would be filed in, the child's alias standing where its seat will. It
    resolves to the spawner's session in the request's project: the
    launch goes on. To no one (a machine enrolled moments ago holds no
    row of the spawner until its first download of the project's log
    reaches the spawner's writer): `spawner-unknown`, which the Mac waits
    out (row 26a). To anyone else, the child itself, another member, or
    the spawner's row in another project: `spawner-shadowed`, at once,
    never waited on. A request without the session (an older Mac's) asks
    nothing of the log; a `--worktree` checkout the engine has not made
    yet is checked as the directory asked for (§10).

    Where the request asks for channels (EN.G2's §1), the tag asked is the
    one the preamble then gives, the spawner's qualified address
    (spawner_tag): read in the spawner's project alone, never through a
    channel's roster, so no alias in another project can take it."""
    by = req["by"]
    if by is None or "session" not in by:
        return
    project = sminos.seat_project({"cwd": cwd, "group": sminos.derive_group(cwd)})
    short = by["short"]
    qualified = bool(req.get("channels"))
    tag = spawner_tag(by, qualified)
    what = "address" if qualified else "short"

    def shadowed(whom, advice=""):
        answer.refuse("spawner-shadowed", "spawn: the spawner's %s, %s, names %s on this machine, so the "
                                          "session's first message to its spawner, %s, would reach it instead: "
                                          "nothing was spawned%s" % (what, tag, whom, by["alias"], advice))
    # Its alias answers the tag before any id does, in the project its seat is filed in (_resolve_tag); a qualified
    # tag is read in the spawner's project alone.
    if alias == short and (not qualified or project is not None and project.id == by["project"]):
        shadowed("the session asked for itself (its alias %s)" % alias, ". Name the session otherwise: spawn it "
                 "under another alias")
    if project is not None:
        sminos.project_path(project, "log")   # known here, as the seat about to be written makes it (known_projects)
    said = io.StringIO()
    try:
        with contextlib.redirect_stderr(said):
            p, m = sminos._resolve_tag(project, sminos.leading_tags(tag)[0])
    except SystemExit:
        # The resolver's own answer is its die, the last thing it writes; what a read printed before it (a warning,
        # a note) is passed on as it was.
        diagnostics, words = said_last(said.getvalue())
        sys.stderr.write(diagnostics)
        if words.startswith("ambiguous"):
            shadowed("more than one member (%s)" % words)
        answer.refuse("spawner-unknown", "spawn: this machine has not read the spawner, %s (%s), from the project's "
                                         "log yet (a machine enrolled moments ago downloads it first), so the "
                                         "session's first message to it would reach no one: nothing was spawned"
                      % (by["alias"], tag))
    sys.stderr.write(said.getvalue())
    if not (m.session == by["session"] and p.id == by["project"]):
        shadowed("%s (@%s, in %s)" % (m.alias, m.short, p.name))
    why = sminos.not_carried(p, req["org"])
    if why:
        # Where the tag reaches is a project whose registration here this enrollment does not carry (a stale
        # checkout's .smns naming another org, say): the reply would be written to a log the uplink never sends.
        answer.refuse("other", "spawn: the spawner's %s, %s, reaches %s in project %s, whose registration on this "
                               "machine its enrollment does not carry (%s), so the session's first message to its "
                               "spawner would be written to a log that never leaves this machine: nothing was "
                               "spawned" % (what, tag, m.alias, p.name, why))


def spawner_tag(by, qualified):
    """The tag the new thread is given for its spawner, and the one
    hold_to_spawner asks: `@<short>` (G1's), or, for a thread placed in
    channels, which reads a bare name through its channels' rosters first
    (CH2), `@<project id>/<short>`, the form a frame's reply line gives
    (sminos.reply_line), read in that one project (EN.G2's §1, R17)."""
    return "@%s/%s" % (by["project"], by["short"]) if qualified else "@" + by["short"]


def hold_to_channels(req, answer):
    """The VM side's checks of the channels a request asks for (EN.G2's §1),
    after hold_to_spawner and before the launch, writing nothing: this
    machine's kept welcome not known yet, `welcome-unknown` (waited out by
    the Mac); one that lists no `channels`, `other`; a channel this machine
    knows whose log its enrollment does not carry against the request's org
    (but for one that has left this machine, which a placement brings back),
    `other`. A channel it does not know is registered when it is placed."""
    asked = req.get("channels")
    if not asked:
        return
    kept = sminos.audience_module().kept_capability("channels")
    if kept is None:
        answer.refuse("welcome-unknown", "spawn: this machine has kept no welcome of its endpoint yet, so whether it "
                                         "serves channels is not known: nothing was spawned")
    if kept is False:
        answer.refuse("other", "spawn: this machine's endpoint serves no channels (its welcome listed none), so the "
                               "session could be placed in none: nothing was spawned")
    for c in asked:
        known = sminos.known_project(c["id"])
        why = sminos.not_carried(known, req["org"]) if known is not None else ""
        if why and why != sminos.LEFT_HERE:
            answer.refuse("other", "spawn: this machine's enrollment does not carry the log of channel %s (%s) as it "
                                   "registers it (%s): nothing was spawned" % (known.name, c["id"], why))


def said_last(text):
    """(what came before, the last message) of what sminos wrote on standard error: each message opens
    `sminos: ` at a line's start, and die's is the last; its words without the prefix."""
    at = text.rfind("\nsminos: ") + 1   # 0 where it is the only one
    last = text[at:]
    return text[:at], (last[len("sminos: "):] if last.startswith("sminos: ") else last).strip()


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
        self.deleted = set()      # the VMs its recount said it deleted (DELETED_RE)
        self.past_caps = False    # whether it printed its caps line, after which it may make a VM
        self.up_exit = None       # its exit, once it ended other than 0
        self.devcloud = ""
        self.checked = None       # (branch, commit, the checkout derived for it) of a derived project, for row 33
        self.reaching = None      # the VM a run of the VM side was started on whose outcome is not yet read
        self.channels = None      # --channel's channels, [{"id", "name"}] with this machine's names (EN.G2's §1)

    def vm(self):
        """The VM made: the one `vm up` was seen to name, once one was: its
        `ready` line, else its `created` line where its recount did not say
        it deleted it. Only `ready` lets the VM side start (make_vm)."""
        if self.made or len(self.ready) == 1:
            return self.made or self.ready[0]
        if len(self.created) == 1 and self.created[0] not in self.deleted:
            return self.created[0]
        return None

    def maybe(self):
        """Whether a VM may exist that `vm up` named nowhere: it named none,
        got past its caps line, and did not end with a cap's (4) or a
        provider's refusal (3), the two ways it ends there having made
        nothing."""
        return not (self.made or self.ready or self.created) and self.past_caps and self.up_exit not in (3, 4)

    def owner(self):
        thread = sminos.threads_module().thread_of(self.session) if self.session else None
        return "this session's thread" if thread is not None else "this session"

    def kept(self):
        vm = self.vm()
        if vm is None:
            return ""
        return KEPT % {"vm": vm, "owner": self.owner()}

    def look(self, vm):
        """Where to look after a call to `vm` whose outcome is not known:
        G1's `sminos list` there, or, where channels were asked (EN.G2's §1),
        every seat on the VM in any project, the engine's jobs there, and
        each channel's roster, which shows nothing about the launch."""
        if not self.channels:
            return ", and devcloud vm ssh %s -- sminos list shows" % vm
        each = ". ".join("devcloud vm ssh %s -- sminos list %s shows who is in %s there" % (vm, ch["id"], ch["name"])
                         for ch in self.channels)
        return (". Do not spawn it again before looking: devcloud vm ssh %s -- sminos list --here --all lists every "
                "seat on %s, in any project, and devcloud vm ssh %s -- claude agents the engine's jobs there, if a "
                "session started and no seat was recorded. %s; a channel that does not list it shows nothing about "
                "whether it was launched" % (vm, vm, vm, each))

    def refuse(self, words, code=1):
        """Every refusal or unknown outcome after usage, `vm up`'s failure, a
        stop and an unusable `ready` output among them, says what may exist:
        a VM named (KEPT), or one that may have been made (MAYBE, last)."""
        if self.maybe():
            sys.stderr.write("sminos: %s\n" % words)
            sminos.die(MAYBE % self.owner(), code)
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
                     "there%s" % (c.reaching, c.look(c.reaching)))
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
    c.channels = channels_asked(c, enrolled, by)
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
    if c.channels:
        request["channels"] = c.channels   # the same on every try (remote)
    remote(c, vm, request, directory, enrolled)


def channels_asked(c, enrolled, by):
    """--channel on the Mac (EN.G2's §1), after this machine is known to be
    enrolled and the spawner's route back is read, before devcloud is looked
    for: the names resolved and folded here, refused as a spawn here refuses
    them (sminos_channels.for_spawn, but for the welcome, which is the VM's
    to read); a spawner whose project id no tag's qualifier takes refused,
    since the thread could be given no address a channel-mate's name cannot
    take; and the request it will send held to the VM side's own test. None
    without --channel."""
    if not c.a.channel:
        return None
    asked = sminos.channels_module().for_spawn(c.a.channel, here=False)
    if by is not None and not sminos.valid_name(by["project"]):
        c.refuse("spawn --on: this session's project id is not one a tag's qualifier takes, so the thread placed in "
                 "channels could be given no address for its spawner that a channel-mate's name cannot take: nothing "
                 "was spawned. Spawn it without --channel and add it after")
    probe = {"v": 1, "nonce": "0" * 16, "org": enrolled["org"], "origin": None, "by": by, "channels": asked}
    if not request_whole(probe):
        c.refuse("spawn --on: the request this sminos would send does not read as one (the channels %s), which is "
                 "this sminos's fault: nothing was spawned" % json.dumps(asked, ensure_ascii=False))
    return asked


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
    enrollment, its reach; the spawner the request names, its alias, short
    id and project as sminos holds them (address_of), never read back out
    of the formatted line."""
    named = sminos.address_of(c.session, os.getcwd())
    if named is None:
        c.refuse("spawn --on: this session is no member of a project yet (sminos who prints no address), so the "
                 "session opened there would have no one to answer: nothing was spawned")
    alias, project = named
    why = sminos.not_carried(project, enrolled["org"])
    if why:
        c.refuse("spawn --on: this session's project, %s, is not one this machine's enrollment carries (%s), so "
                 "nothing a session on another machine says would reach it: nothing was spawned. Run it from a "
                 "session in a project the org shares" % (project.name, why))
    reach(c)
    return {"alias": alias or c.session[:8], "short": c.session[:8],
            "project": project.id, "project_name": project.name,
            "machine": sminos.host_name(), "session": c.session}


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
    c.checked = (branch, commit, "%s/%s" % (CHECKOUTS, repo[1]))
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
    error's text when kept, whether the bound passed, whether its standard
    output ended). `timeout` is one deadline for the run and the reading of
    its output together: past it, what still holds the output (a descendant
    of devcloud, the ssh under `vm ssh`) is left, with PIPE_GRACE to finish,
    and the output is said not to have ended. Each line of its
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
            if up and (m := DELETED_RE.fullmatch(text.rstrip("\n"))):
                c.deleted.add(m.group("cap") or m.group("failed"))
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
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            code = proc.wait(timeout)
        except subprocess.TimeoutExpired:
            threads.stop_tree(proc.pid, proc.wait)
            code, timed_out = proc.wait(), True
        drained(pumps, PIPE_GRACE if timed_out else PIPE_DRAIN if deadline is None
                else max(0.0, deadline - time.monotonic()) + PIPE_GRACE)
    except (Stopped, KeyboardInterrupt):
        if proc is not None:
            if proc.returncode is None:
                threads.stop_tree(proc.pid, proc.wait)
            drained([(t, f) for t, f in pumps if t.ident is not None], PIPE_GRACE)
        if vm is not None:
            c.refuse("spawn --on: stopped while devcloud vm ssh ran, and devcloud was stopped with it: a session may "
                     "or may not have started there%s" % c.look(vm))
        c.refuse("spawn --on: stopped while devcloud ran; devcloud was stopped with it, and its own lines above say "
                 "what became of anything it made")
    finally:
        signal.signal(signal.SIGTERM, previous)
    return code, lines, "".join(err), timed_out, not pumps[0][0].is_alive()


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
    """(h): `devcloud vm up` for `new`; the host its `ready` line names.
    Each value is one `--flag=value` word, so that devcloud's parser reads
    one that opens with `-` (a label `-review`) as the value it is."""
    a = c.a
    args = ["--enroll", "--keep", "--expect-creator=%s" % c.session[:8]]
    if LABEL_RE.fullmatch(a.alias):
        args.append("--label=%s" % a.alias)
    for p in projects:
        args.append("--project=%s" % p)
    if a.vm_confirmed:
        args.append("--confirmed")
    sminos.note("making a VM (a few minutes; devcloud's own lines follow): devcloud vm up %s" % shlex.join(args))
    code, _, _, _, _ = run_devcloud(c, ["vm", "up"] + args, keep_err=True)
    if code != 0:
        # A VM made with --keep has no lease to bound it: what may exist is said (Call.refuse).
        c.up_exit = code
        c.refuse("spawn --on new: devcloud vm up exited %d; its own lines above say why, and what became of any VM it "
                 "made. Nothing was spawned%s" % (code, ". The cap is the person's: after their yes to this exact "
                                                       "request, pass --vm-confirmed" if code == 4 else ""), code)
    if len(c.ready) != 1:
        c.refuse("spawn --on new: devcloud vm up succeeded and did not name one host where sminos reads it: find the "
                 "VM with devcloud vm ls, then sminos spawn --on <name>")
    c.made = c.ready[0]
    return c.made


def carried(a, directory):
    """The VM side's flags: the directory, the mode, and each carried flag
    given, each value as one `--flag=value` word, so that a value the
    Mac's parser took (`--brief=--review`) is not read there as a flag."""
    out = ["--cwd=%s" % directory, "--permission-mode=%s" % a.permission_mode]
    for flag, value in (("--role", a.role), ("--brief", a.brief), ("--worktree", a.worktree or None),
                        ("--model", a.model), ("--effort", a.effort)):
        if value is not None:
            out.append("%s=%s" % (flag, value))
    for stamp in a.stamp or []:
        out.append("--stamp=%s" % stamp)
    return out


def remote(c, vm, request, directory, enrolled):
    """(i): the VM side, each run preceded by the spawner's route back
    read afresh, the reach rule with it (route_back, after
    sminos.forget_caches: a spawner whose project changed on disk while
    the VM was made or enrolled is sent as it is now, under the request's
    one nonce, and its address and carried project are refused as at (e)),
    tried again on the VM's own `not-enrolled`, for `new` only, and on its
    `spawner-unknown`, within one wait from the first of either; then the
    line (rows 25 to 33)."""
    a = c.a
    bound = seconds("SMINOS_ON_TIMEOUT", REMOTE_TIMEOUT)
    wait = seconds("SMINOS_ON_ENROLL_WAIT", ENROLL_WAIT)
    deadline, waited_on = None, []

    def wait_over(left):
        """The wait's end, by its last refusal (rows 27a and 27), once `left` (one read of the clock) is none."""
        if left > 0:
            return
        if waited_on[-1] == "welcome-unknown":
            c.refuse("spawn --on: %s's sminos had kept no welcome of its endpoint within %d minutes, so whether it "
                     "serves channels is not known: no thread was opened there. devcloud vm ssh %s -- sminos daemon "
                     "status shows its uplink; once it is connected, sminos spawn --on %s opens it"
                     % (vm, round(wait / 60), vm, vm), EXIT_LATER)
        if waited_on[-1] == "spawner-unknown":
            c.refuse("spawn --on: %s had not read this session from the project's log within %d minutes (it is "
                     "still downloading the log): no thread was opened there. Once it has, sminos spawn --on %s "
                     "opens it" % (vm, round(wait / 60), vm), EXIT_LATER)
        c.refuse("spawn --on new: %s did not enroll within %d minutes: nothing was spawned. Once sminos "
                 "machines lists it, sminos spawn --on %s spawns there" % (vm, round(wait / 60), vm))
    while True:
        if deadline is not None:
            wait_over(deadline - time.monotonic())   # past the wait's end, before the route back: the end is said
        if c.session:
            sminos.forget_caches()   # what the session's project and this machine's enrollment are read from, now
            now = sminos.enrollment()
            if now is None:
                c.refuse("spawn --on: this machine is no longer enrolled in the org, so the session on %s could "
                         "tell this one nothing: nothing was spawned" % vm)
            if now["org"] != enrolled["org"]:
                c.refuse("spawn --on: this machine is now enrolled in another org than when the VM was asked for "
                         "(%s, not %s), so the session on %s and this one could not reach each other: nothing was "
                         "spawned" % (now["org"], enrolled["org"], vm))
            request = {**request, "by": route_back(c, enrolled)}   # the reach rule read with it
        # The positionals after `--`, so that an alias the Mac's parser took after its own (`-alias`) is one there.
        # The session variable cleared there for this call alone: where a client sends it and a host accepts it,
        # the VM's sminos would refuse the transport's call as a session's (§8 step 0).
        args = (["vm", "ssh", vm, "--", "env", "-u", "CLAUDE_CODE_SESSION_ID", "sminos", "spawn",
                 "--asked-from=%s" % json.dumps(request, separators=(",", ":"), ensure_ascii=False)]
                + carried(a, directory) + ["--", a.alias, "-"])
        given = bound
        if deadline is not None:
            # The wait bounds every try it starts: none at or past its end, and each given only what is left,
            # read last before the try (the reach rule's read takes time too).
            left = deadline - time.monotonic()   # one read: what decides is what the try is given
            wait_over(left)
            given = min(bound, left)
        c.reaching = vm
        code, lines, err, timed_out, ended = run_devcloud(c, args, stdin=a.task, timeout=given, keep_err=True,
                                                          vm=vm, nonce=request["nonce"])
        if timed_out:
            c.refuse("spawn --on: %s gave no outcome within %d minutes, and the call was stopped: a session may or may "
                     "not have started there%s" % (vm, math.ceil(given / 60), c.look(vm)))
        # Output that never ended may hold more after what was read: no line read is the last one.
        verdict, d = judge(lines, request["nonce"], a.alias, code,
                           [ch["id"] for ch in c.channels] if c.channels else None) if ended else (
            "unknown", "its output did not end: something it started still holds it open")
        if verdict == "unknown":
            unknown(c, vm, d, code, err)
        if verdict == "ok":
            break
        if d["why"] not in WAITED_ON:
            c.refuse("spawn --on: %s's sminos answered exit %d; its line above says why, and what, if anything, exists "
                     "there" % (vm, d["exit"]), d["exit"])
        c.reaching = None   # it answered that it is not enrolled, or has not read the spawner: nothing was spawned
        if d["why"] == "not-enrolled" and not c.new:
            c.refuse("spawn --on: %s is not enrolled in the org (no endpoint on it has been welcomed: a host made "
                     "without the MAWS project, or one whose enrollment has not finished; devcloud vm ssh %s -- "
                     "devcloud status shows its maws step), so no other machine would see a session there: nothing "
                     "was spawned" % (vm, vm))
        if deadline is None:
            deadline = time.monotonic() + wait
            if d["why"] == "not-enrolled":
                sminos.note("%s is up and not enrolled in the org yet: waiting up to %d minutes for its endpoint (the "
                            "host tries again every 5), then spawning" % (vm, round(wait / 60)))
            elif d["why"] == "welcome-unknown":
                sminos.note("%s's sminos has kept no welcome of its endpoint yet (a machine enrolled moments ago "
                            "keeps it once its uplink connects): waiting up to %d minutes for it, then spawning"
                            % (vm, round(wait / 60)))
            else:
                sminos.note("%s has not read this session from the project's log yet (a machine enrolled moments ago "
                            "downloads it first): waiting up to %d minutes for it, then spawning" % (vm, round(wait / 60)))
        elif d["why"] == "spawner-unknown" and "spawner-unknown" not in waited_on:
            sminos.note("%s has not read this session from the project's log yet (a machine enrolled moments ago "
                        "downloads it first): waiting for it, within the same %d minutes, then spawning"
                        % (vm, round(wait / 60)))
        elif d["why"] == "welcome-unknown" and "welcome-unknown" not in waited_on:
            sminos.note("%s's sminos has kept no welcome of its endpoint yet: waiting for it, within the same %d "
                        "minutes, then spawning" % (vm, round(wait / 60)))
        waited_on.append(d["why"])
        time.sleep(min(seconds("SMINOS_ON_ENROLL_POLL", ENROLL_POLL), max(0.0, deadline - time.monotonic())))
    line = "seat %s on %s: %s/%s  [%s / %s]  status=%s" % ("re-filled" if d["refilled"] else "spawned", d["machine"],
                                                          d["group"], d["alias"], d["short"], d["seat"], d["status"])
    why = d.get("not_carried")
    if why == sminos.channels_module().CARRIAGE_UNREAD:
        print(line, flush=True)
        sminos.note("%s filed this seat in its project %s, and whether its enrollment carries that project could not "
                    "be read once it was placed: it may not be listed here, and what is said from here may not reach "
                    "it" % (d["machine"], d["project"]["name"]))
    elif why is not None:   # a string (outcome_whole): present at all, the seat is not carried
        # Launched in a project its machine's enrollment does not carry (a --worktree's checkout, say): no promise.
        print(line, flush=True)
        sminos.note("%s filed this seat in its project %s, which its enrollment does not carry%s: it will not be "
                    "listed here, and nothing said from here reaches it" % (
                        d["machine"], d["project"]["name"],
                        " (%s)" % why if why in sminos.NOT_CARRIED_WORDS else ""))
    else:
        # In channels, by the session's whole id: a local member or a channel-mate may be named for its short, and a
        # bare name is read as an alias before an id (sminos._resolve_tag). Without channels, G1's words.
        print("%s  (message it: sminos say \"@%s …\"; it is listed here once %s's events arrive)"
              % (line, d["session"] if c.channels else d["session"][:8], d["machine"]), flush=True)
    if c.channels:
        said_placements(c, d)
    if c.made is not None:
        sminos.note(c.kept()[len(". The VM "):] + ", and it sends a notice after three idle days")
        # Only where the session runs in the checkout the branch was derived for, which an explicit --cwd or a
        # --worktree need not be.
        if c.checked is not None and in_checkout(d["cwd"], c.checked[2]) and d["head"] and d["head"] != c.checked[1]:
            # Read after the job started, the VM's HEAD shows a difference, not its cause.
            sminos.note("the VM's checkout is at %s, not at %s, the commit origin's %s was at when it was checked"
                        % (d["head"], c.checked[1], c.checked[0]))
    sys.exit(0)


def said_placements(c, d):
    """The Mac's lines for the placements a success reports (EN.G2's §1):
    one a channel, the name this machine's and the commands by the
    channel's id and the session's whole id; one warning where none was made
    (`identity`, `project-not-carried`, saying nothing of which channels the
    thread is in, since a refilled seat keeps what it held), or where the
    VM's sminos predates the flag and reported none."""
    alias, session, machine = d["alias"], d["session"], d["machine"]
    label = "%s#%s" % (alias, session[:8])
    names = {ch["id"]: ch["name"] for ch in c.channels}
    placed = d.get("channels")
    if placed is None:
        cmds = "; ".join("sminos list %s shows, once its events arrive, and sminos channel add %s %s asks its machine"
                         % (ch["id"], ch["id"], session) for ch in c.channels)
        told = (". It was told to reach you as @%s, which a member of a channel it is already in can answer to if "
                "that is its alias" % c.session[:8]) if c.session else ""
        sminos.warn("spawn completed, but %s's sminos did not carry out the placements asked for (it predates spawn "
                    "--channel). Which channels %s is in is not known here: %s%s" % (machine, label, cmds, told))
        return
    words = sminos.channels_module().placement_words
    if placed and all(p["state"] == "failed" and p["why"] == "identity" for p in placed):
        sminos.warn("spawn completed, but none of the placements asked for was made: %s is no longer enrolled in this "
                    "org" % machine)
        return
    if placed and all(p["state"] == "failed" and p["why"] == "project-not-carried" for p in placed):
        sminos.warn("none of the placements asked for (%s) was made: its project on %s is not carried, and this "
                    "project's memberships will not be seen from here"
                    % (", ".join(names[p["id"]] for p in placed), machine))
        return
    for p in placed:
        name = names[p["id"]]
        if p["state"] == "applied":
            print("%s: %s %s" % (label, "already in" if p["why"] == "unchanged" else "in", name), flush=True)
        else:
            sminos.warn("spawn completed, but %s was not placed in %s on %s (%s): sminos channel add %s %s asks its "
                        "machine, once sminos list --machine %s shows it here"
                        % (label, name, machine, words(p["state"], p["why"]), p["id"], session, machine))


def in_checkout(cwd, checkout):
    """Whether the VM's `cwd` is `checkout` (`~/…`, from the VM's home, which
    this machine does not know: the same path below some home)."""
    rel = checkout[2:] if checkout.startswith("~/") else None
    cwd = cwd.rstrip("/")
    return cwd == checkout.rstrip("/") if rel is None else cwd.endswith("/" + rel.rstrip("/"))


def unknown(c, vm, reason, code, err):
    """Row 29, with row 24's note after it; exits."""
    words = ("spawn --on: the outcome on %s is not known (%s): a session may or may not have started there%s"
             % (vm, reason, c.look(vm)))
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
