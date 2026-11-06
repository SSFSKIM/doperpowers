#!/usr/bin/env python3
"""sminos_visibility — who may reach a session, as its owner sets it (P5 O18 M4).

The design is MAWS's `docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md`
(D6 "Changes over time", D10; Interfaces §C). Reach is visibility: a
session's `access` (private < listed < org-view < org-converse) and its
`shares` (a member's grade, list < view < converse < approve) say whose
agents may message it, and its record on its own machine keeps them
(sminos_records.set_policy: under the records lock, policyRev bumped).

    sminos access <member> private|listed|org-view|org-converse
    sminos share  <member> <person> list|view|converse|approve|none

Both are set_visibility, which M5's executor calls too. Narrowing (lowering
access, removing a share, lowering a grade) is any shell's; widening
(anything that raises any member's reach) runs only as the operator, with no
CLAUDE_CODE_SESSION_ID, confirmed at /dev/tty: an agent cannot open a
session to more people than its owner chose. An endpoint that cannot carry a
session's visibility (no `access`) takes only `listed`.

A change is told to the log once the endpoint has answered it: the session's
audience is the endpoint's word, sent as its `audience` frame at the new
policyRev after the uplink publishes the session's member frame with it. So
set_visibility records a pending transition (TRANSITIONS: the session, its
new policyRev, its audience before the change as known then) and nudges the
daemon; the uplink completes it when that frame comes (or at a tick, once it
is kept, so a restart completes it too):
- a change that withdraws members writes D6's `unlisted` notice first,
  `{ts, writer, seq, kind: "unlisted", session}` under
  `<machine>/<session>~<digest of the withdrawn>`, written before the
  frame's audience is kept, so nothing of the session goes under its new
  stream before it (the hub judges a notice against its registry rows from
  before the batch: a snapshot uploaded earlier would make it stale), and
  the upload draws a notice's writer first (sminos_hublog);
- then the snapshot, `joined` and `state`, under the session's new stream,
  or its plain writer once listed.
The withdrawn members are the frame's `withdrawn` when it names them, else
the audience before the change minus the new one when both are known; a
session the whole org reached before (listed or org-wide) going private,
with no `withdrawn`, writes its snapshot alone and says in daemon.log why no
notice could be: the org's members are the endpoint's to name. That fails
closed: the hub's registry and the recipient's `reach?` refuse what the
withdrawn members send it. The endpoint adds the notice's `policyRev` and
`audience` at signing, as it does a snapshot's.
"""
import fcntl
import json
import os
import re
import sys
import time
from contextlib import contextmanager

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos as S  # noqa: E402
import sminos_audience as au  # noqa: E402

TRANSITIONS = "visibility.json"   # under daemon/: {v: 1, sessions: {sid: transition}}
# A transition: {policyRev, access, previous? (the audience before the change, null for the whole org; absent: not
# known), at, notice? (the notice's writer, "" for none; absent: not yet decided), why? (no notice could be written),
# snapshot? (the writers it was written under), done? (when)}. A done one is kept a day, for the CLI to read.
DONE_KEPT_S = 86400
WAIT_S = 5.0   # what the CLI waits, while a daemon runs, for the transition to be written
ACCESS_RANK = {a: i for i, a in enumerate(au.ACCESS)}       # private < listed < org-view < org-converse
GRADE_RANK = {g: i + 1 for i, g in enumerate(au.GRADES)}    # none < list < view < converse < approve
MEMBER_RE = re.compile(r"[0-9a-f]{32}")
WIDENING = "widening reach needs its owner: run this in a terminal, or use MAWS"
NO_CAPABILITY = ("this machine's endpoint cannot carry a session's visibility (it advertised no `access`): a session "
                 "set so could write nothing until it can; only `access <member> listed` is taken")


class Refused(Exception):
    """The change is refused; nothing was written."""


class Widening(Refused):
    """The change widens reach: the operator's to make (WIDENING)."""

    def __init__(self, before, after):
        super().__init__(WIDENING)
        self.before, self.after = before, after


# ------------------------------------------------------------- the change


def changed(before, access=None, share=None):
    """(access, shares) of `before` with the change made: `access` set, or
    `share` (member, grade or None: removed)."""
    by = {s["member"]: s["grade"] for s in before[1]}
    if share is not None:
        member, grade = share
        if grade is None:
            by.pop(member, None)
        else:
            by[member] = grade
    return access or before[0], [{"member": m, "grade": g} for m, g in sorted(by.items())]


def widens(before, after):
    """Whether `after` raises any member's reach over `before`: a higher
    access, a share added or a grade raised."""
    if ACCESS_RANK[after[0]] > ACCESS_RANK[before[0]]:
        return True
    was = {s["member"]: GRADE_RANK[s["grade"]] for s in before[1]}
    return any(GRADE_RANK[s["grade"]] > was.get(s["member"], 0) for s in after[1])


def set_visibility(sid, *, access=None, share=None, operator):
    """The session's access set, or one share's grade (`share`: (member id,
    grade or None to remove it)), on its record here (sminos_records.
    set_policy), and the transition it makes recorded for the uplink to
    write (see the module); the daemon nudged. `operator`: the caller may
    widen (the CLI's operator who confirmed at the terminal; M5's executor
    with the act's proof); otherwise a widening raises Widening, decided
    under the records lock against the record as it is then. Refused for a
    session with no readable record here, or a change this machine's
    endpoint cannot carry. {record, changed, transition (None for no
    change)}."""
    if access is not None and access not in au.ACCESS:
        raise ValueError("access is one of %s" % "|".join(au.ACCESS))
    if share is not None and not (MEMBER_RE.fullmatch(str(share[0])) and (share[1] is None or share[1] in au.GRADES)):
        raise ValueError("a share is (a member id, %s or None)" % "|".join(au.GRADES))
    records = S.records_module()
    capable = au.capable()
    seen = {}

    def mutate(old_access, old_shares):
        before = records.checked_policy(old_access, old_shares)
        after = records.checked_policy(*changed(before, access, share))
        seen["before"] = before
        if after == before:
            return after
        if not capable and not (after[0] == "listed" and after[1] == before[1]):
            raise Refused(NO_CAPABILITY)
        if widens(before, after) and not operator:
            raise Widening(before, after)
        return after

    # The policy's change and its pending entry under one lock, the transitions': two setters never interleave
    # between them, so the entry kept is always the latest revision's, and its `previous` reads the one before.
    with _locked() as sessions:
        try:
            rec, moved = records.set_policy(sid, mutate)
        except records.NoRecord as e:
            raise Refused("%s: its visibility is kept on its record, on its own machine" % e)
        if not moved:
            return {"record": rec, "changed": False, "transition": None}
        t = {"policyRev": rec["policyRev"], "access": rec["access"],
             **previous_known(sid, seen["before"][0], rec["policyRev"], sessions.get(sid)), "at": S.now(ms=True)}
        sessions[sid] = t
    S.nudge_daemon()
    return {"record": rec, "changed": True, "transition": t}


def previous_known(sid, old_access, rev, held):
    """{"previous": the session's audience before the change at `rev`} as
    known here, or {} when it is not: behind a change the endpoint never
    answered (`held`, the session's kept transition), the audience before
    that one (the endpoint then compares against the same); else the whole
    org (None) for a session that was not private; else the endpoint's word
    kept at the policyRev before."""
    if held is not None and not held.get("done") and held.get("policyRev", rev) < rev:
        return {"previous": held["previous"]} if "previous" in held else {}
    if old_access != "private":
        return {"previous": None}
    try:
        entry = au.entry_of(sid)
    except au.StreamUnknown:
        return {}
    if entry is not None and entry.get("policyRev") == rev - 1 and entry.get("members"):
        return {"previous": list(entry["members"])}
    return {}


# ------------------------------------------------------------- the pending transitions, kept


def transitions_path():
    return os.path.join(S.root(), "daemon", TRANSITIONS)


def transitions():
    """{session: transition} as kept; {} when none is, or the file cannot
    be read."""
    try:
        d = S.json_at(transitions_path())
    except (OSError, ValueError):
        return {}
    sessions = d.get("sessions") if isinstance(d, dict) and d.get("v") == 1 else None
    return {sid: t for sid, t in sessions.items() if isinstance(t, dict) and type(t.get("policyRev")) is int} \
        if isinstance(sessions, dict) else {}


@contextmanager
def _locked():
    """The kept transitions, {session: transition}, for the block to change
    under their lock; written whole when it ends without raising and changed
    them, a done one past DONE_KEPT_S dropped."""
    path = transitions_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            sessions = transitions()
            was = json.dumps(sessions, sort_keys=True)
            yield sessions
            if json.dumps(sessions, sort_keys=True) == was:
                return
            cut = time.time() - DONE_KEPT_S
            sessions = {sid: t for sid, t in sessions.items()
                        if not t.get("done") or (S._ts_epoch(t["done"]) or 0) >= cut}
            tmp = "%s.%d.tmp" % (path, os.getpid())
            with open(tmp, "w", encoding="ascii") as f:
                json.dump({"v": 1, "sessions": sessions}, f, ensure_ascii=True, sort_keys=True)
                f.write("\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def set_pending(sid, t):
    """The session's transition: `t` in place of any kept."""
    with _locked() as sessions:
        sessions[sid] = dict(t)


def _amend(sid, rev, **fields):
    with _locked() as sessions:
        if sessions.get(sid, {}).get("policyRev") == rev:
            sessions[sid] = {**sessions[sid], **fields}


# ------------------------------------------------------------- the uplink's side: completing a transition


def withdrawn_of(t, entry):
    """(the members the transition withdrew, sorted, or None; why no notice
    can be written, or ""). `entry` is the endpoint's word kept at its
    policyRev (None: it gives none, an endpoint without `access`)."""
    if entry is not None and entry.get("withdrawn"):
        return list(entry["withdrawn"]), ""
    new = entry.get("members") if entry is not None else None
    if new is None:
        return None, ""   # the whole org reaches it now: no one is withdrawn
    if "previous" not in t:
        return None, ("its audience before the change is not known here, and the endpoint named no members it "
                      "withdrew")
    if t["previous"] is None:
        return None, ("the whole org reached it before, whose members are the endpoint's to name, and the endpoint "
                      "named none it withdrew")
    return sorted(set(t["previous"]) - set(new)) or None, ""


def _notice(sid, t, entry, project):
    """The transition's notice written, or the decision that there is none
    kept (with daemon.log's line why, when one was owed and cannot be)."""
    withdrawn, why = withdrawn_of(t, entry)
    if withdrawn and not S.streams_here(project):
        withdrawn, why = None, "its project's log is not the hub's, which alone filters a notice to its audience"
    writer = ""
    if withdrawn:
        writer = S.stream_writer(S.writer_id(sid), withdrawn)
        S.keep_stream(project, writer, withdrawn)
        S.log_append(project, writer, "unlisted", session=sid)
    elif why:
        S.daemon_log("visibility: no unlisted notice for session %s at policyRev %d: %s; its snapshot goes alone, "
                     "and the hub's registry and the recipient's reach? refuse what a withdrawn member sends it"
                     % (sid[:8], t["policyRev"], why))
    _amend(sid, t["policyRev"], notice=writer, **({"why": why} if why else {}))


def notice_before(frame, project_of):
    """An `audience` frame from the endpoint, before it is kept: the notice
    of the session's pending transition at its policyRev written (or none
    decided), so it precedes every event of the session's new stream.
    `project_of(sid)` is the project the session's member frame named."""
    got = au.audience_entry(frame) if isinstance(frame, dict) else None
    if got is None:
        return
    sid, entry = got
    t = transitions().get(sid)
    if t is None or t.get("done") or "notice" in t or t["policyRev"] != entry["policyRev"]:
        return
    project = project_of(sid)
    if project is not None:
        _notice(sid, t, entry, project)


def complete(project_of, sessions=None):
    """Each pending transition (of `sessions`, else every one) whose
    audience the endpoint gave at its policyRev — kept, as on_audience
    keeps it — or, with an endpoint that carries no visibility, one going
    listed: its notice written if not yet (a restart between), then its
    snapshot. The sessions completed."""
    pending = {sid: t for sid, t in transitions().items()
               if not t.get("done") and (sessions is None or sid in sessions)}
    if not pending:
        return []
    capable, out = au.capable(), []
    for sid, t in sorted(pending.items()):
        try:
            entry = au.entry_of(sid)
        except au.StreamUnknown:
            continue
        if entry is None or entry.get("policyRev") != t["policyRev"]:
            if capable or t["access"] == "private":
                continue
            entry = None
        project = project_of(sid)
        if project is None:
            continue
        if "notice" not in t:
            _notice(sid, t, entry, project)
        written = snapshot(sid, project)
        _amend(sid, t["policyRev"], snapshot=written, done=S.now(ms=True))
        out.append(sid)
    return out


def snapshot(sid, project):
    """The session's snapshot written again under the writer its policy
    gives now: `joined`, as its last joined had it, and its `state`. The
    writers written under; nothing for a session not a joined member here."""
    view = S.view_of(project, titles=False)
    m = next((m for m in view.members if m.session == sid and m.local), None)
    if m is None:
        return []
    j = (view.info.get(sid) or {}).get("joined") or {}
    fields = S.joined_fields(m.alias, m.name_source or str(j.get("name_source") or "derived"),
                             *(str(j.get(k) or "") for k in ("cwd", "worktree", "role", "seat")), "",
                             str(j.get("session_kind") or m.kind or ""), session=sid)
    got = S.lifecycle(project, sid, "joined", guard=lambda evs: S.latest_membership(evs) == "joined",
                      required=False, **fields)
    if got and m.state:
        got += S.lifecycle(project, sid, "state", required=False, state=m.state, machine=S.host_name())
    return sorted({e["writer"] for e in got})


# ------------------------------------------------------------- the verbs


def target(q):
    """(session, its project or None) a member name names on this machine;
    exit 4 for none, or for another machine's session, naming its machine."""
    found = S.find_target(q)
    if found[0] == "seat":
        seat = found[1]
        sid = found[2] or seat.get("current") or ""
        if not sid:
            S.die("%s/%s holds no session" % (seat["group"], seat["alias"]), S.EXIT_UNKNOWN)
        return sid, S.seat_project(seat)
    if found[0] == "member":
        project, m = found[1], found[2]
        if not m.local:
            S.die("%s runs on %s: its visibility is set on that machine" % (q, m.machine or "another machine"),
                  S.EXIT_UNKNOWN)
        return m.session, project
    if S.UUID_RE.fullmatch(q) and au.is_local(q):
        return q, None
    S.die("no member matching '%s'" % q, S.EXIT_UNKNOWN)


def person_id(p, project):
    """The org member id `p` names: an id as given, or an email one member
    id carries in the verified owners of the project's log (every hub
    project's known here, for a session in none)."""
    if MEMBER_RE.fullmatch(p):
        return p
    if "@" not in p:
        S.die("%s is no member id: name the person by the org member's id (32 lowercase hex characters)" % p, 1)
    projects = [project] if project is not None else [x for x in S.known_projects() if S.streams_here(x)]
    ids = set()
    for x in projects:
        for e in S.log_read(x):
            owners = (e.get("verified") or {}).get("owners") if isinstance(e.get("verified"), dict) else None
            for o in owners if isinstance(owners, list) else ():
                if isinstance(o, dict) and str(o.get("email") or "").lower() == p.lower() \
                        and MEMBER_RE.fullmatch(str(o.get("id") or "")):
                    ids.add(o["id"])
    if len(ids) == 1:
        return ids.pop()
    S.die("%s: %s; name the person by the org member's id (32 lowercase hex characters)"
          % (p, "no member id is known here for it" if not ids else "it names several members here"), 1)


def described(before, after):
    """What a change does, in a line: `access a → b`, `share m: g → h`."""
    out = ["access %s → %s" % (before[0], after[0])] if before[0] != after[0] else []
    was, now = ({s["member"]: s["grade"] for s in x[1]} for x in (before, after))
    out += ["share %s: %s → %s" % (m, was.get(m, "none"), now.get(m, "none"))
            for m in sorted(set(was) | set(now)) if was.get(m) != now.get(m)]
    return "; ".join(out)


def confirmed(name, w):
    """The operator's yes at the controlling terminal, /dev/tty itself (no
    stand-in for it: an agent could set one); exit 1 when there is none."""
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        S.die("widening reach needs its owner at a terminal to confirm it, and this has none: run this in a "
              "terminal, or use MAWS", 1)
    try:
        os.write(fd, ("%s: %s widens who may reach it. Confirm? [y/N] " % (name, described(w.before, w.after)))
                 .encode("utf-8"))
        answer = b""
        while len(answer) < 256:
            c = os.read(fd, 1)
            if not c or c in b"\r\n":
                break
            answer += c
    finally:
        os.close(fd)
    return answer.decode("utf-8", "replace").strip().lower() in ("y", "yes")


def daemon_runs():
    try:
        d = S.daemon_module()
        return bool(d.held_by(d.run_lock_path()))
    except OSError:
        return False


def report(name, sid, out):
    """The verb's line: the policy as it stands, its policyRev, and what of
    the transition is written (waited for briefly while a daemon runs)."""
    rec = out["record"]
    access, shares, rev = au.policy_of(rec)
    policy = "access %s%s, policyRev %d" % (access, "; shares %s" % ", ".join(
        "%s %s" % (s["member"], s["grade"]) for s in shares) if shares else "", rev)
    if not out["changed"]:
        print("%s: %s: nothing changed" % (name, policy))
        return
    end = time.monotonic() + (WAIT_S if daemon_runs() else 0)
    t = transitions().get(sid) or {}
    while not t.get("done") and time.monotonic() < end:
        time.sleep(0.1)
        t = transitions().get(sid) or {}
    if t.get("policyRev") != rev:
        state = "a later change stands in its place"
    elif t.get("done"):
        state = ("its unlisted notice written, then its snapshot" if t.get("notice") else
                 "its snapshot written; no unlisted notice: %s" % t["why"] if t.get("why") else
                 "its snapshot written (it withdrew no one)")
    else:
        state = ("its unlisted notice (if it withdraws anyone) and its snapshot are pending: the daemon writes them "
                 "once the endpoint gives its audience at policyRev %d" % rev)
    print("%s: %s; %s" % (name, policy, state))


def _run(name, sid, change):
    try:
        out = set_visibility(sid, operator=False, **change)
    except Widening as w:
        if os.environ.get("CLAUDE_CODE_SESSION_ID"):
            S.die(WIDENING, 1)
        if not confirmed(name, w):
            S.die("%s: not confirmed; nothing changed" % name, 1)
        try:
            out = set_visibility(sid, operator=True, **change)
        except Refused as e:
            S.die(str(e), 1)
    except Refused as e:
        S.die(str(e), 1)
    report(name, sid, out)


def cmd_access(a):
    _run(a.member, target(a.member)[0], {"access": a.level})


def cmd_share(a):
    sid, project = target(a.member)
    _run(a.member, sid, {"share": (person_id(a.person, project), None if a.grade == "none" else a.grade)})
