#!/usr/bin/env python3
"""manager — the session manager skill's command: read-only views of the sessions the owner follows.

    manager transcript <member> --since T [--until T] [--max-chars N]
    manager pending [--since T] [--until T]
    manager subscriptions
    manager subscriptions add <initiative> <member>...
    manager subscriptions remove <member>...
    manager ledger
    manager ledger apply (--file PATH | -)
    manager query <member> "<question>" [--timeout S]

Every command takes --json and --name N (which manager's state: $SMINOS_HOME/managers/<N>.json, default
`default`). T is local time: 9am, 14:30 (today; a clock time later than now means yesterday), a duration back
from now (10h, 90m, 2d), or an ISO-8601 time. Exit codes are sminos's: 0, 1 a failure, 2 usage (and a ledger
change refused), 4 an unknown or ambiguous member.

Nothing here writes to a session or a project log: it reads transcripts and host events, and writes only the
manager's own state file and its archive; `query` asks a fork of the session, which the session never sees.
Resolving a member may let sminos reconcile a project's membership, as any sminos read does. Detail: CLAUDE.md
beside this file.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from types import SimpleNamespace
from typing import Any, NamedTuple

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "sminos",
                                                 "scripts")))

import sminos as S  # noqa: E402
import sminos_bridge as B  # noqa: E402
import sminos_fork as F  # noqa: E402
import manager_ledger as L  # noqa: E402
import manager_window as W  # noqa: E402

SHORT_RE = re.compile(r"^[0-9a-f]{8}$")
DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)([mhd])$")
CLOCK_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.I)
DURATION_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


class Usage(Exception):
    """A malformed command line: exit 2."""


def fail(msg, code=1):
    sys.stderr.write("manager: %s\n" % msg)
    sys.exit(code)


# ------------------------------------------------------------------ time

def parse_time(text, now=None):
    """A local time as the owner writes one (the module's T), as an aware datetime."""
    now = now or datetime.datetime.now().astimezone()
    s = (text or "").strip()
    m = DURATION_RE.match(s)
    if m:
        return now - datetime.timedelta(**{DURATION_UNITS[m.group(2)]: float(m.group(1))})
    m = CLOCK_RE.match(s)
    if m and (m.group(2) is not None or m.group(3)):
        hour, minute, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if half:
            if not 1 <= hour <= 12:
                raise Usage("'%s' is not a time" % text)
            hour = hour % 12 + (12 if half == "pm" else 0)
        if hour > 23 or minute > 59:
            raise Usage("'%s' is not a time" % text)
        at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return at - datetime.timedelta(days=1) if at > now else at
    try:
        at = datetime.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        at = None
    if at is None:
        raise Usage("'%s' is not a time: 9am, 14:30, 10h, 90m, 2d or an ISO-8601 time" % text)
    return at.astimezone() if at.tzinfo else at.replace(tzinfo=now.tzinfo)


def _local(ts):
    t = S._ts_epoch(ts)
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t is not None else str(ts)


# ------------------------------------------------------------------ members

class Target(NamedTuple):
    alias: str
    project: Any            # sminos Project, or None when no project's log holds the session
    sessions: list          # the lineage, oldest first
    member: Any             # sminos Member; None for a session membership no longer holds (historical)
    machine: str
    local: bool

    @property
    def session(self):
        """The id a subscription stores: the member's session now, or the historical session asked for."""
        return self.member.session if self.member is not None and getattr(self.member, "session", "") \
            else self.sessions[0]


def _member_target(project, m):
    sessions = list(reversed([m.session] + list(m.former)))
    nxt = B.successor(m.session) if m.session and m.local else ""
    if nxt and nxt not in sessions:
        sessions.append(nxt)
    return Target(m.alias, project, sessions, m, m.machine, m.local)


def _project_by_id(pid):
    return next((p for p in S.known_projects() if p.id == pid), None) if pid else None


def historical(sid, project=None, alias=""):
    """A session membership no longer holds (sminos retires a seat-less session once its process ends), read
    from what stays on disk: its own events in a project's log, its transcript, the sessions it continued in.
    None when nothing on this machine knows it."""
    events = S._own_events(project, sid) if project is not None else []
    if project is None:
        for p in S.known_projects():
            events = S._own_events(p, sid)
            if events:
                project = p
                break
    joined = [e for e in events if e.get("kind") == "joined"]
    last = joined[-1] if joined else {}
    machine = str(last.get("machine") or "")
    if project is None and not S.transcript_now(sid):
        return None
    sessions, nxt = [sid], sid
    while (nxt := S.continued_in(nxt)) and nxt not in sessions:
        sessions.append(nxt)
    local = S.is_self(machine, sid) if machine else True
    return Target(alias or str(last.get("alias") or "") or sid[:8], project, sessions, None,
                  machine or S.host_name(), local)


def _seat_target(seat, bound):
    project = S.seat_project(seat)
    for m in S.members(project) if project is not None else []:
        if m.seat and m.seat.get("seat_id") == seat.get("seat_id") and (not bound or bound in (m.session,) + m.former):
            return _member_target(project, m)
    sid = bound or seat.get("current") or ""
    t = historical(sid, project, seat.get("alias") or "") if sid else None
    if t is None:
        fail("%s holds no session on this machine" % seat.get("alias"), 1)
    return t


def _alias_anywhere(q):
    """A bare alias find_target did not find in the caller's project, matched exactly among the local members
    of every project known here; several matches exit 4 naming each as <project>/<alias>."""
    hits = {}
    for p in S.known_projects():
        for m in S.members(p):
            if m.local and m.alias == q and m.session:
                hits.setdefault(m.session, (p, m))
    if len(hits) > 1:
        fail("ambiguous '%s' matches: %s" % (q, ", ".join(sorted("%s/%s" % (p.name, m.alias) for p, m in hits.values()))),
             S.EXIT_UNKNOWN)
    return ("member",) + next(iter(hits.values())) if hits else ("none",)


def _from_hit(hit):
    if hit[0] == "member":
        return _member_target(hit[1], hit[2])
    if hit[0] == "seat":
        return _seat_target(hit[1], hit[2])
    return None


def resolve(q):
    """The member a name on the command line names, across every project on this machine (the order is the
    spec's: find_target first; a bare alias it does not find, among every project's local members; a full
    uuid membership no longer holds, historically)."""
    bare = not (S.UUID_RE.match(q) or "/" in q or "#" in q or SHORT_RE.match(q))
    hit = S.find_target(q)
    if hit[0] == "none" and bare:
        hit = _alias_anywhere(q)
    t = _from_hit(hit) or (historical(q) if S.UUID_RE.match(q) else None)
    if t is None:
        fail("no member matching '%s' on this machine" % q, S.EXIT_UNKNOWN)
    return t


def resolve_stored(entry):
    """A subscription's member, by the session id it stored (aliases recur and change): through find_target as a
    full uuid, on to the session it continued in; historically when membership no longer holds it. None when
    nothing on this machine knows it."""
    sid = str(entry.get("session") or "")
    t = _from_hit(S.find_target(sid)) if S.UUID_RE.match(sid) else None
    return t or historical(sid, _project_by_id(entry.get("project")), str(entry.get("alias") or ""))


def refuse_remote(t):
    if not t.local:
        fail("%s runs on %s; this version reads sessions on this machine only" % (t.alias, t.machine), 1)


# ------------------------------------------------------------------ state

def load_state(name):
    """The manager's state, version 2 (manager_ledger); a file that cannot be read, or whose content does not
    hold, exits 1 naming it."""
    try:
        return L.load(name)
    except (OSError, ValueError) as e:
        fail("%s is unreadable (%s)" % (L.path(name), e), 1)
    except L.Invalid as e:
        fail("%s does not hold:\n  %s" % (L.path(name), "\n  ".join(e.problems)), 1)


def _entries(st):
    for i in st["initiatives"]:
        for e in i.get("sessions") or []:
            yield i, e


def _drop(st, sessions):
    for i in st["initiatives"]:
        i["sessions"] = [e for e in i.get("sessions") or [] if e.get("session") not in sessions]
    st["initiatives"] = [i for i in st["initiatives"] if i["sessions"]]


# ------------------------------------------------------------------ commands

def emit(a, data, text):
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    elif text:
        print(text)


def _paths(t):
    """(session id, its transcript here or "") for each session of the member's lineage, oldest first."""
    return [(sid, S.transcript_now(sid)) for sid in t.sessions]


def cmd_transcript(a):
    t = resolve(a.member)
    refuse_remote(t)
    since = parse_time(a.since)
    until = parse_time(a.until) if a.until else None
    if until is not None and until <= since:
        raise Usage("--until must be later than --since")
    if a.max_chars < 1:
        raise Usage("--max-chars must be positive")
    paths = _paths(t)
    if not any(p for _, p in paths):
        fail("no transcript of %s on this machine" % t.alias, 1)
    owner = {}

    def corroborate(text):
        if "words" not in owner:
            owner["words"] = W.OwnerWords(S.log_read(t.project) if t.project is not None else [], t.sessions)
        return owner["words"].corroborates(text)

    try:
        got = W.window(paths, since.timestamp(), until.timestamp() if until else None, a.max_chars, corroborate)
    except W.Unreadable as e:
        fail("cannot read the transcript %s: %s" % (e.path, e.error), 1)
    for sid in got["missing"]:
        sys.stderr.write("manager: %s's session %s has no transcript on this machine; the window leaves it out\n"
                         % (t.alias, sid[:8]))
    if a.json:
        emit(a, {"member": t.alias, "sessions": t.sessions, "since": since.isoformat(),
                 "until": until.isoformat() if until else None, "truncated": got["truncated"],
                 "missing": got["missing"], "entries": got["entries"]}, "")
        return
    lines = [W.render(e) for e in got["entries"]]
    if not lines:
        lines.append("(nothing in %s's transcript since %s)" % (t.alias, since.strftime("%Y-%m-%d %H:%M")))
    if got["truncated"]:
        at = got["stopped_at"]
        lines.append("manager: stopped at %s characters; the window shown ends at %s. Read on with --since %s, or "
                     "narrow the window with --until." % (
                         format(a.max_chars, ","), _local(at) if at else since.strftime("%Y-%m-%d %H:%M"),
                         datetime.datetime.fromtimestamp(S._ts_epoch(at)).astimezone().isoformat(timespec="seconds")
                         if at else since.isoformat(timespec="seconds")))
    print("\n".join(lines))


def pending_of(targets, until=None):
    """Async questions with no answer of the same src (any age; with `until`, only what was asked and answered
    before it), across the log and the host store of every session of each target's lineage; and the targets
    sminos holds `waiting` (a permission prompt or a native question on screen). `waiting` is a state as of now,
    which no record lets a past moment reconstruct: with `until` it is left empty and `waiting_known` is false."""
    cut = until.timestamp() if until is not None else None
    unanswered, waiting = [], []
    for t in targets:
        questions, answered = {}, set()
        for sid in t.sessions if t.project is not None else []:
            for e in S._own_events(t.project, sid, "log") + S._own_events(t.project, sid, S.HOST_STORE):
                at = S._ts_epoch(e.get("ts"))
                if cut is not None and (at is None or at >= cut):
                    continue
                if e.get("kind") == "answered":
                    answered.add(e.get("src"))
                elif e.get("kind") == "question" and e.get("src") and e["src"] not in questions:
                    questions[e["src"]] = (sid, e)
        for src, (sid, e) in questions.items():
            if src not in answered:
                text = e.get("text")
                unanswered.append({"member": t.alias, "session": sid, "asked": e.get("ts"),
                                   "question": "\n".join(map(str, text)) if isinstance(text, list) else str(text or ""),
                                   "choices": list(e.get("choices") or []), "src": src})
        m = t.member
        if cut is None and m is not None and getattr(m, "state", "") == "waiting":
            age = getattr(m, "state_age", None)
            since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age)).strftime(
                "%Y-%m-%dT%H:%M:%SZ") if age is not None else None
            waiting.append({"member": t.alias, "session": t.sessions[-1], "since": since})
    unanswered.sort(key=lambda q: S._ts_epoch(q["asked"]) or 0)
    return {"unanswered": unanswered, "waiting": waiting, "waiting_known": cut is None}


def subscriptions_of(st):
    """(initiative name, entry, target, why not) for every subscription: its target when it still resolves to a
    member of this machine, else None and why."""
    out = []
    for i, e in _entries(st):
        try:
            t = resolve_stored(e)
        except SystemExit:      # a seat with no session here, said on stderr by the resolver
            t = None
        if t is None:
            out.append((i["name"], e, None, "it does not resolve"))
        elif not t.local:
            out.append((i["name"], e, None, "it runs on %s; this version reads sessions on this machine only"
                        % t.machine))
        else:
            out.append((i["name"], e, t, None))
    return out


class NoWindow(Exception):
    """A member none of whose sessions has a transcript on this machine."""


def seen_window(t, since, until=None, stored=None):
    """{"seen", "last_activity"} over the member's window from `since` to `until` (epoch seconds), read forward
    with the window reader across its lineage: `seen` the newer of the mark held (`stored`) and the newest entry
    that shows the owner in the session's own window (manager_window.owner_present); `last_activity` the newest
    entry kept. Raises NoWindow, or manager_window.Unreadable."""
    paths = _paths(t)
    missing = [sid[:8] for sid, p in paths if not p]
    if missing:
        # A session of the lineage that cannot be read is a stretch the update cannot vouch for: an error, so the
        # subscription keeps its covered point instead of reading as inactive and read through.
        raise NoWindow("%s of its lineage %s no transcript on this machine: the read is incomplete" % (
            ", ".join(missing), "has" if len(missing) == 1 else "have"))
    entries = W.window(paths, since, until, float("inf"))["entries"]
    present = [L.parse(e["ts"]) for e in entries if W.owner_present(e)] + ([L.parse(stored)] if stored else [])
    present = [x for x in present if x is not None]
    active = [x for x in (L.parse(e["ts"]) for e in entries) if x is not None]
    return {"seen": L.stamp(max(present)) if present else None,
            "last_activity": L.stamp(max(active)) if active else None}


def seen_marks(subs, since, end):
    """`pending`'s `seen`: one entry per subscription, over its window (from `since` when given, else its
    `covered`, else a day back; to `end`), or the reason it cannot be read."""
    out = []
    for initiative, e, t, why in subs:
        entry = {"member": t.alias if t is not None else e.get("alias"), "session": e.get("session"),
                 "initiative": initiative}
        if why:
            out.append(dict(entry, error=why))
            continue
        frm = since if since is not None else L.parse(e.get("covered")) or end - L.FIRST_WINDOW
        entry.update({"from": L.stamp(frm), "until": L.stamp(end)})
        try:
            entry.update(seen_window(t, frm, end, e.get("seen")))
        except NoWindow as x:
            entry = dict(entry, error=str(x))
        except W.Unreadable as x:
            entry = dict(entry, error="cannot read the transcript %s: %s" % (x.path, x.error))
        out.append(entry)
    return out


def cmd_pending(a):
    since = parse_time(a.since) if a.since else None
    until = parse_time(a.until) if a.until else None
    if since is not None and until is not None and until <= since:
        raise Usage("--until must be later than --since")
    subs = subscriptions_of(load_state(a.name))
    got = pending_of([t for _, _, t, _ in subs if t is not None], until)
    now = time.time()
    got["seen"] = seen_marks(subs, since.timestamp() if since else None, until.timestamp() if until else now)
    lines = []
    if got["unanswered"]:
        lines.append("Unanswered questions (%d):" % len(got["unanswered"]))
        for q in got["unanswered"]:
            choices = " [%s]" % " | ".join(q["choices"]) if q["choices"] else ""
            lines.append("  %s  %s  %s%s  (src %s)" % (q["member"], _local(q["asked"]), q["question"].replace(
                "\n", " / "), choices, q["src"]))
    if got["waiting"]:
        lines.append("Waiting on a prompt in the session (%d):" % len(got["waiting"]))
        lines += ["  %s  since %s" % (w["member"], _local(w["since"]) if w["since"] else "?") for w in got["waiting"]]
    if not lines:
        lines.append("No unanswered questions." if not got["waiting_known"] else "Nothing pending.")
    if not got["waiting_known"]:
        lines.append("(Sessions waiting on a prompt are not shown for a past --until: that state is not recorded.)")
    if got["seen"]:
        lines.append("Seen marks (each session's window, the owner's last words there, its last activity):")
        width = max(len(str(s["member"])) for s in got["seen"])
        for s in got["seen"]:
            if "error" in s:
                lines.append("  %s  %s" % (str(s["member"]).ljust(width), s["error"]))
                continue
            lines.append("  %s  %s–%s  %s · %s" % (
                str(s["member"]).ljust(width), L.clock(s["from"], now), L.clock(s["until"], now),
                "seen %s" % L.clock(s["seen"], now) if s["seen"] else "not seen",
                "active %s" % L.clock(s["last_activity"], now) if s["last_activity"] else "no activity"))
    emit(a, got, "\n".join(lines))


def cmd_subscriptions(a):
    words = a.words
    if not words:
        return list_subscriptions(a)
    verb, rest = words[0], words[1:]
    if verb == "add":
        if len(rest) < 2:
            raise Usage("subscriptions add <initiative> <member>...")
        return add_subscriptions(a, rest[0], rest[1:])
    if verb == "remove":
        if not rest:
            raise Usage("subscriptions remove <member>...")
        return remove_subscriptions(a, rest)
    raise Usage("subscriptions [add <initiative> <member>... | remove <member>...]")


def list_subscriptions(a):
    st = load_state(a.name)
    current = {(name, e.get("session")): t for name, e, t, _ in subscriptions_of(st)}
    data, lines = {"initiatives": []}, []
    for i in st["initiatives"]:
        rows = []
        lines.append(i["name"])
        for e in i.get("sessions") or []:
            t = current.get((i["name"], e.get("session")))
            rows.append(dict(e, current_alias=t.alias if t else None, current_session=t.sessions[-1] if t else None))
            now = "" if t is None or t.alias == e.get("alias") else "  (now %s)" % t.alias
            gone = "  (does not resolve)" if t is None else ""
            lines.append("  %s  %s  %s%s%s" % (e.get("alias"), str(e.get("session"))[:8],
                                               e.get("project_name") or e.get("project") or "-", now, gone))
        data["initiatives"].append({"name": i["name"], "sessions": rows})
    emit(a, data, "\n".join(lines) or "No subscriptions.")


def add_subscriptions(a, initiative, names):
    if not initiative.strip():
        raise Usage("an initiative needs a name")
    own = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    targets = []
    for q in names:
        t = resolve(q)
        if own and own in t.sessions:
            fail("%s is this manager's own session: it cannot follow itself" % t.alias, 1)
        refuse_remote(t)
        targets.append(t)
    with L.lock(a.name):
        st = load_state(a.name)
        for t in targets:
            ids = set(t.sessions) | {t.session}
            held = next((e for _, e in _entries(st) if e.get("session") in ids), None)
            _drop(st, ids)
            group = next((i for i in st["initiatives"] if i["name"] == initiative), None)
            if group is None:
                group = {"name": initiative, "sessions": []}
                st["initiatives"].append(group)
            added = S.now(ms=True)
            # A new subscription reads from a day before it; a member moved between initiatives keeps its marks.
            group["sessions"].append({"session": t.session, "alias": t.alias,
                                      "project": t.project.id if t.project is not None else "",
                                      "project_name": t.project.name if t.project is not None else "",
                                      "added": held["added"] if held else added,
                                      "covered": held["covered"] if held else L.stamp(L.parse(added) - L.FIRST_WINDOW),
                                      "seen": held.get("seen") if held else None})
        L.save(a.name, st)
    emit(a, {"initiative": initiative, "added": [{"session": t.session, "alias": t.alias} for t in targets]},
         "subscribed under %s: %s" % (initiative, ", ".join("%s (%s)" % (t.alias, t.session[:8]) for t in targets)))


def remove_subscriptions(a, names):
    with L.lock(a.name):
        st = load_state(a.name)
        removed = []
        for q in names:
            hits = {e.get("session") for i, e in _entries(st)
                    if q in (e.get("session"), str(e.get("session"))[:8], e.get("alias"),
                             "%s/%s" % (e.get("project_name"), e.get("alias")))}
            if not hits:
                t = resolve(q)
                hits = {e.get("session") for _, e in _entries(st) if e.get("session") in set(t.sessions) | {t.session}}
            if not hits:
                fail("%s is not subscribed" % q, 1)
            removed += sorted(hits)
            _drop(st, hits)
        L.save(a.name, st)
    emit(a, {"removed": removed}, "unsubscribed: %s" % ", ".join(s[:8] for s in removed))


def cmd_ledger(a):
    """`ledger`: the ledger per initiative. `ledger apply`: one update's ledger change (manager_ledger.apply),
    under the state's lock; a change that does not hold exits 2 naming every problem, the file unchanged."""
    words, now = a.words, time.time()
    if not words:
        if a.file:
            raise Usage("ledger apply (--file PATH | -)")
        v = L.view(load_state(a.name), now)
        return emit(a, v, L.render(v, now))
    if words[0] != "apply" or len(words) > 2 or (len(words) == 2) == bool(a.file) or (len(words) == 2 and words[1] != "-"):
        raise Usage("ledger apply (--file PATH | -)")
    try:
        raw = sys.stdin.read() if len(words) == 2 else open(a.file).read()
    except OSError as e:
        fail("cannot read %s: %s" % (a.file, e), 1)
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise Usage("the ledger change is not JSON: %s" % e)
    with L.lock(a.name):
        st = load_state(a.name)
        try:
            st, report = L.apply(st, doc, now)
        except L.Invalid as e:
            fail("the ledger change was not applied:\n  %s" % "\n  ".join(e.problems), 2)
        L.append_archive(a.name, report["archived"])
        L.save(a.name, st)
    emit(a, {k: report[k] for k in ("new", "changed", "unchanged_open")}, L.summary(st, report))


QUERY_REFUSALS = {
    "busy": "%s is already answering another manager query (busy)",
    "nothing-to-fork": "%s has made no model request yet, so there is nothing to fork (nothing-to-fork)",
}
# The `ask` refusals a headless fork answers in its place: a session whose bridge cannot run a guarded fork agent,
# or whose engine refused the spawn (a session stopped by Esc refuses one until it gets input).
QUERY_HEADLESS = {
    "no-guard": "runs no read-only fork guard",
    "spawn-refused": "refused to spawn a fork agent (an Esc leaves a session refusing until it gets input)",
}


def _fork_subject(t, session):
    """(project, member) for the headless fork of `session`, the member's newest: the member itself while it holds
    that session, else a stand-in naming it (a session membership no longer holds), whose fork starts where the
    project's log last saw it joined, else at the project's root."""
    if t.project is None:
        fail("%s is in no project on this machine: there is no directory to fork it from" % t.alias, 1)
    m = t.member
    if m is None or getattr(m, "session", "") != session:
        m = SimpleNamespace(session=session, seat=None)
    return t.project, m


def _headless(t, session, question, timeout):
    foreign = S.foreign_config(session)
    if foreign:
        fail("%s's engine runs under %s, not this process's config dir (%s), where a headless fork from here would "
             "look for it, on that dir's credentials" % (t.alias, foreign, S.config_dir()), 1)
    project, m = _fork_subject(t, session)
    return F.headless_fork(project, m, F.FORK_FRAME + "\n\nThe question:\n\n" + question, tools=True, cache=True,
                           timeout=timeout)


def cmd_query(a):
    """A question put to a fork of the member's session: its fork agent through its bridge (`ask`) while it is
    live and its bridge can run one under the read-only guard, else a headless fork (a session not running, a
    bridge with no `ask`, an `ask` refused `no-guard`). The session never sees the exchange."""
    if not a.question.strip():
        raise Usage("a query is its question")
    if a.timeout <= 0:
        raise Usage("--timeout must be positive")
    t = resolve(a.member)
    refuse_remote(t)
    session = t.sessions[-1]
    got = None
    if F.bridge_offers(session, "ask"):
        try:
            got = F.ask_fork_agent(session, a.question, timeout=a.timeout)
        except F.ForkFailed as e:
            if e.code in QUERY_REFUSALS:
                fail(QUERY_REFUSALS[e.code] % t.alias, 1)
            if e.code not in QUERY_HEADLESS:
                fail("%s: %s" % (t.alias, e.reason), 1)
            sys.stderr.write("manager: %s %s (%s); asking a headless fork\n" % (t.alias, QUERY_HEADLESS[e.code], e.code))
    if got is None:
        try:
            got = _headless(t, session, a.question, a.timeout)
        except F.ForkFailed as e:
            tail = [x for x in (e.stderr or "").splitlines() if x.strip()][-5:]
            fail("%s: %s%s" % (t.alias, e.reason, "".join("\n    %s" % x for x in tail)), 1)
    u = got.usage
    via = "via %s · cache read %s · cache write %s · input %s · output %s" % (
        got.via, *(format(u[k], ",") for k in ("cacheRead", "cacheWrite", "input", "output")))
    cut = "\n(the answer was cut to 64 KiB)" if got.truncated else ""
    emit(a, {"member": t.alias, "via": got.via, "text": got.text, "truncated": got.truncated, "usage": u},
         "%s%s\n%s" % (got.text.rstrip("\n"), cut, via))


def parser():
    p = argparse.ArgumentParser(prog="manager", description="The session manager's read-only views.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def command(name, func, **kw):
        c = sub.add_parser(name, **kw)
        c.add_argument("--json", action="store_true", help="JSON for scripts")
        c.add_argument("--name", default="default", help="which manager's state (default: default)")
        c.set_defaults(func=func)
        return c

    c = command("transcript", cmd_transcript, help="a condensed window of a member's transcript")
    c.add_argument("member")
    c.add_argument("--since", required=True)
    c.add_argument("--until")
    c.add_argument("--max-chars", type=int, default=W.DEFAULT_MAX_CHARS)
    c = command("pending", cmd_pending, help="unanswered questions, waiting sessions, each session's seen mark")
    c.add_argument("--since", help="the seen marks' window for every member (default: each one's covered)")
    c.add_argument("--until")
    c = command("subscriptions", cmd_subscriptions, help="the sessions followed, by initiative")
    c.add_argument("words", nargs="*", metavar="add|remove ...")
    c = command("ledger", cmd_ledger, help="the ledger; `ledger apply` records an update's change")
    c.add_argument("words", nargs="*", metavar="apply [-]")
    c.add_argument("--file")
    c = command("query", cmd_query, help="a question put to a fork of a member's session")
    c.add_argument("member")
    c.add_argument("question")
    c.add_argument("--timeout", type=float, default=300, help="seconds to wait for the answer (default 300)")
    return p


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    if not S.valid_name(a.name):
        p.error("'%s' is not a manager name" % a.name)
    try:
        a.func(a)
    except Usage as e:
        p.error(str(e))


if __name__ == "__main__":
    main()
