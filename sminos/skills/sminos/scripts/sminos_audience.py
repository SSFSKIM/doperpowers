#!/usr/bin/env python3
"""sminos_audience — which writer stream an event goes under (P5 O18 M3).

The design is MAWS's `docs/doperpowers/plans/2026-11-05-p5-o18-message-reach.md`
(D4, D6, D7, D10; Interfaces §A–§C). sminos holds no grade logic: what a
session's audience is, and whose owners a session has, is its endpoint's
word, sent down RL10 as `audience {session, owners, members, digest,
policyRev}` frames (members null: listed, the whole org) for every local
session and every remote one the endpoint's policy cache holds. The uplink
keeps them in `daemon/audiences.json` (AUDIENCES), with the capabilities the
endpoint's welcome advertised; the CLI's writers read them here. Everything
else is set arithmetic.

- An event's audience is the intersection of the audiences of its writing
  session (when private) and of every session it addresses (when private);
  an event naming no private session has none, and goes under its plain
  writer (stream_for).
- It is sent only when every recipient's owners, and the writing session's,
  are inside it: a private session's agent messaging outside its audience is
  refused before anything is written (Unreachable).
- A `say` to sessions of different audiences is split, one event per
  audience, each carrying only its own recipients' leading tags.
- A provenance reference (a spawner, a continuation's successor) whose
  session's audience does not contain the event's is redacted: written null.
- Nothing of this runs unless the endpoint advertised `access` (D9): with an
  old endpoint, or none, every event goes under its plain writer as before.
  A session whose record says private while its audience is not known at its
  `policyRev` (or the endpoint lacks the capability), or whose record file
  exists and cannot be read, has no stream to choose: StreamUnknown, and
  nothing of it is written (D10, fail closed).

Each stream writer's audience is kept in the project's home, `streams.json`
(keep_stream), when its first event is written: the uplink's `void` (a
content-free event at a position the endpoint refused, which revives a
stream) carries it as sminos's claim.
"""
import fcntl
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos  # noqa: E402

AUDIENCES = "audiences.json"   # under daemon/: {v, capabilities, sessions: {sid: {owners, members, policyRev}}}
STREAMS = "streams.json"       # under a project's home: {writer: audience}
ACCESS = ("private", "listed", "org-view", "org-converse")
GRADES = ("list", "view", "converse", "approve")
DEFAULT_ACCESS = "listed"


class StreamUnknown(Exception):
    """The writing session's stream cannot be chosen (fail closed)."""


class Unreachable(Exception):
    """D4's refusal: a recipient outside the event's audience."""


# ------------------------------------------------------------- what an event names


def _session_id(v):
    return isinstance(v, str) and v != "" and len(v) <= 256


def session_refs(event):
    """Every structured session reference `event` carries, its writing
    session aside (D4): [{session, role, path}], `role` addressing or
    provenance. MAWS's `sessionRefs` (apps/org-protocol/src/audience.ts),
    pinned by sminos/tests/audience-vectors.json. A redacted one (null, or
    left out) is none."""
    if not isinstance(event, dict):
        return []
    out = []
    own = sminos.writer_session(event.get("writer")) if isinstance(event.get("writer"), str) else ""
    own = own or None
    to = event.get("to")
    if isinstance(to, list):
        for i, r in enumerate(to):
            if isinstance(r, dict) and _session_id(r.get("session")):
                out.append({"session": r["session"], "role": "addressing", "path": "to.%d.session" % i})
    if _session_id(event.get("session")) and event["session"] != own:
        out.append({"session": event["session"], "role": "addressing", "path": "session"})
    origin = event.get("origin")
    if isinstance(origin, dict) and _session_id(origin.get("spawnerSession")):
        out.append({"session": origin["spawnerSession"], "role": "provenance", "path": "origin.spawnerSession"})
    attest = event.get("attest")
    if isinstance(attest, dict) and isinstance(attest.get("origin"), dict) \
            and _session_id(attest["origin"].get("spawnerSession")):
        out.append({"session": attest["origin"]["spawnerSession"], "role": "provenance",
                    "path": "attest.origin.spawnerSession"})
    if event.get("kind") == "retired" and event.get("reason") == "continued" and _session_id(event.get("to")):
        out.append({"session": event["to"], "role": "provenance", "path": "to"})
    return out


def is_audience(v):
    """An audience as an event carries it: member ids, at least one, sorted,
    distinct."""
    return isinstance(v, list) and bool(v) and all(isinstance(m, str) and m for m in v) \
        and all(v[i - 1] < v[i] for i in range(1, len(v)))


# ------------------------------------------------------------- the endpoint's word


def audiences_path():
    return os.path.join(sminos.root(), "daemon", AUDIENCES)


def _read_audiences():
    """The kept file as a dict; {} when there is none; StreamUnknown when it
    is there and cannot be read (fail closed: a remote session's privacy is
    unknown)."""
    d = _read_kept()
    return {} if d is None else d


def _read_kept():
    """_read_audiences, None when there is no file: what one read found."""
    try:
        d = sminos.json_at(audiences_path())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise StreamUnknown("%s cannot be read (%s): no event naming another session is written until it can"
                            % (AUDIENCES, e))
    if not isinstance(d, dict) or d.get("v") != 1:
        raise StreamUnknown("%s is not a version this sminos reads" % AUDIENCES)
    return d


def capable():
    """Whether this machine's endpoint advertised `access` (D9): only then
    does sminos send visibility, or write a stream. An unreadable file is
    taken as capable, so the writers below read it and fail closed."""
    try:
        d = _read_audiences()
    except StreamUnknown:
        return True
    return "access" in (d.get("capabilities") or [])


def reach_capable():
    """Whether every peer push here is the endpoint's to decide (`reach?`,
    P5 O18 D3, D8): the machine is cut over to its endpoint and the
    endpoint's welcome advertised `reach`. On a cut-over machine a file that
    is not there yet, or cannot be read, is taken as capable, so the pushes
    are held owed (fail closed) until a welcome says: keep_capabilities
    writes it at every welcome, an old endpoint's empty list included."""
    if not sminos.sibling_module("sminos_rl10").cut_over():
        return False
    try:
        d = _read_kept()   # one read decides: a welcome may write the file just after it
    except StreamUnknown:
        return True
    return d is None or "reach" in (d.get("capabilities") or [])


def widening_through_app():
    """Whether widening a session's reach here is the app's alone, so the
    CLI refuses it ("use MAWS") from a terminal too and keeps narrowing (P5
    Decision Logs 231 and 232; the architect's ruling, sminos chat 1164):
    the machine is cut over to its endpoint and that endpoint's welcome
    advertised `record`, meaning it serves the Share sheet's `record.access`,
    `record.shares` and `record.owners` acts, from any member's MAWS. The
    word is the last welcome's, kept: an endpoint away, stopped or
    unreachable leaves it standing, so stopping mawsd never hands widening
    back to the terminal; only a later welcome without `record` (a MAWS
    rollback) does. On a cut-over machine a file not there yet, or one that
    cannot be read, counts as `record`: every welcome writes it, so the word
    is not known yet (fail closed). A machine not cut over has no endpoint to
    carry an act, so the operator's terminal stays its gate (a machine
    enrolled at no hub: no hub, no welcome)."""
    if not sminos.sibling_module("sminos_rl10").cut_over():
        return False
    try:
        d = _read_kept()
    except StreamUnknown:
        return True
    return d is None or "record" in (d.get("capabilities") or [])


def _write_audiences(d):
    path = audiences_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(d, f, ensure_ascii=True, sort_keys=True)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _held_for_write():
    try:
        d = _read_audiences()
    except StreamUnknown:
        d = {}
    return {"v": 1, "capabilities": list(d.get("capabilities") or []),
            "sessions": dict(d.get("sessions") or {}) if isinstance(d.get("sessions"), dict) else {}}


def keep_capabilities(capabilities):
    """The endpoint's welcome: what it advertised, kept (the uplink's)."""
    caps = sorted({c for c in capabilities if isinstance(c, str)}) if isinstance(capabilities, list) else []
    d = _held_for_write()
    if d["capabilities"] != caps or not os.path.exists(audiences_path()):
        d["capabilities"] = caps
        _write_audiences(d)


def audience_entry(frame):
    """An `audience` frame as kept, or None when it is no such frame: its
    owners (member ids), its members (an audience, or None: listed), its
    policyRev; its digest, when sent, must be its members'. A local
    session's frame may name `withdrawn`, the members its change at that
    policyRev withdrew (as the endpoint checks an `unlisted` notice), kept
    with it when it names any (O18 M4)."""
    sid, owners, members, rev = frame.get("session"), frame.get("owners"), frame.get("members"), frame.get("policyRev")
    if not (sminos.UUID_RE.match(str(sid or "")) and isinstance(owners, list)
            and all(isinstance(o, str) and o for o in owners) and type(rev) is int and rev >= 0):
        return None
    if members is not None:
        if not isinstance(members, list) or not all(isinstance(m, str) and m for m in members) or not members:
            return None
        members = sorted(set(members))
        if frame.get("digest") is not None and frame.get("digest") != sminos.audience_digest(members):
            return None
    elif frame.get("digest") is not None:
        return None
    entry = {"owners": sorted(set(owners)), "members": members, "policyRev": rev}
    withdrawn = frame.get("withdrawn")
    if withdrawn is not None:
        if not isinstance(withdrawn, list) or not all(isinstance(m, str) and m for m in withdrawn):
            return None
        if withdrawn:
            entry["withdrawn"] = sorted(set(withdrawn))
    return sid, entry


def keep_audience(frame):
    """One `audience` frame kept (the uplink's): an entry is replaced only by
    one of the same or a newer policyRev. Whether the frame was taken."""
    got = audience_entry(frame) if isinstance(frame, dict) else None
    if got is None:
        return False
    sid, entry = got
    d = _held_for_write()
    held = d["sessions"].get(sid)
    if isinstance(held, dict) and type(held.get("policyRev")) is int and held["policyRev"] > entry["policyRev"]:
        return True
    if held != entry:
        d["sessions"][sid] = entry
        _write_audiences(d)
    return True


def entry_of(sid, held=None):
    d = held if held is not None else _read_audiences()
    entry = (d.get("sessions") or {}).get(sid)
    return entry if isinstance(entry, dict) else None


# ------------------------------------------------------------- a session's policy and audience


def policy_of(rec):
    """(access, shares, policyRev) of a record, the defaults where it says
    nothing."""
    rec = rec or {}
    access = rec.get("access") if rec.get("access") in ACCESS else DEFAULT_ACCESS
    shares = [{"member": s["member"], "grade": s["grade"]} for s in rec.get("shares") or []
              if isinstance(s, dict) and isinstance(s.get("member"), str) and s.get("grade") in GRADES]
    rev = rec.get("policyRev") if type(rec.get("policyRev")) is int and rec.get("policyRev") >= 0 else 0
    return access, shares, rev


def is_local(sid):
    """Whether the session is this machine's: it has a record file here."""
    records = sminos.records_module()
    return bool(sminos.UUID_RE.match(str(sid or ""))) and os.path.lexists(records.record_path(sid))


def audience_of(sid, held=None):
    """A session's audience as an event that names it must stay within: None
    for a listed or org-wide one (the whole org), else its sorted members.
    A local session's from its record and the endpoint's word at its
    policyRev; a remote one's from the endpoint's word alone (unknown: none,
    the hub's registry the backstop). StreamUnknown for a local session whose
    record cannot be read, or that is private with no audience known at its
    policyRev."""
    if not sid:
        return None
    held = held if held is not None else _read_audiences()
    if is_local(sid):
        records = sminos.records_module()
        rec = records.read(sid)
        if rec is None and records.unreadable(sid):
            raise StreamUnknown("session %s has a record that cannot be read: nothing of it is written" % sid[:8])
        access, _, rev = policy_of(rec)
        if access != "private":
            return None
        if "access" not in (held.get("capabilities") or []):
            raise StreamUnknown("session %s is private and this machine's endpoint cannot carry it" % sid[:8])
        entry = entry_of(sid, held)
        if entry is None or entry.get("policyRev") != rev or not entry.get("members"):
            raise StreamUnknown("session %s is private and its endpoint has not given its audience at policyRev %d "
                                "yet: nothing of it is written until it does" % (sid[:8], rev))
        return list(entry["members"])
    entry = entry_of(sid, held)
    return list(entry["members"]) if entry and entry.get("members") else None


def owners_of(sid, held=None):
    """A session's owners, as member ids, as the endpoint resolved them; a
    local one's record when its owners name members and the endpoint gave
    none; None when unknown."""
    held = held if held is not None else _read_audiences()
    entry = entry_of(sid, held)
    if entry and entry.get("owners"):
        return list(entry["owners"])
    if is_local(sid):
        rec = sminos.records_module().read(sid) or {}
        owners = rec.get("owners") if isinstance(rec.get("owners"), list) else []
        if owners and sminos.records_module().MACHINE not in owners:
            return sorted(set(owners))
    return None


def machine_owners(held=None):
    """The machine's owners (`@machine`) as the endpoint resolved them: the
    owners it gave a session of this machine whose record names exactly
    `@machine`; None when no such word is kept."""
    held = held if held is not None else _read_audiences()
    records = sminos.records_module()
    for sid, entry in sorted((held.get("sessions") or {}).items()):
        if isinstance(entry, dict) and entry.get("owners") and is_local(sid) \
                and (records.read(sid) or {}).get("owners") == [records.MACHINE]:
            return list(entry["owners"])
    return None


def meet(a, b):
    """The intersection of two audiences, None standing for the whole org."""
    if a is None:
        return None if b is None else list(b)
    if b is None:
        return list(a)
    return sorted(set(a) & set(b))


def contains(outer, inner):
    """Whether audience `outer` contains `inner` (None: the whole org)."""
    if outer is None:
        return True
    return inner is not None and set(inner) <= set(outer)


# ------------------------------------------------------------- the stream choice


def own_audience(sid):
    """The audience the session's own events (its lifecycle, its state) go
    under: None, or its members (StreamUnknown as audience_of). Plain with an
    endpoint that advertised no `access`, unless its record says private."""
    if not sid:
        return None
    held = _read_audiences()
    if "access" not in (held.get("capabilities") or []):
        rec = sminos.records_module().read(sid) if is_local(sid) else None
        if is_local(sid) and rec is None and sminos.records_module().unreadable(sid):
            raise StreamUnknown("session %s has a record that cannot be read: nothing of it is written" % sid[:8])
        if policy_of(rec)[0] == "private":
            raise StreamUnknown("session %s is private and this machine's endpoint cannot carry it" % sid[:8])
        return None
    return audience_of(sid, held)


def own_writer(sid):
    """The writer the session's own events go under now (own_audience)."""
    base = sminos.writer_id(sid or None)
    return sminos.stream_writer(base, own_audience(sid) if sid else None)


def leading_run(text):
    """(the raw text of each leading tag, the body after the run): each tag
    with its trailing `,:;`, as sminos.leading_tags reads the run."""
    raws, pos = [], 0
    while True:
        start = sminos.SPACE_RE.match(text, pos).end()
        m = sminos.TAG_RE.match(text, start)
        if not m:
            return raws, text[start:]
        end = m.end()
        while end < len(text) and text[end] in ",:;":
            end += 1
        if end < len(text) and not text[end].isspace():
            return raws, text[start:]
        raws.append(text[m.start():end])
        pos = end


def split_text(text, raws_kept):
    """`text` with its leading run rebuilt as `raws_kept` (in their order),
    the body after it unchanged."""
    _, body = leading_run(text)
    head = " ".join(raws_kept)
    return head + (" " + body if body and head else body)


def stream_for(project, writer_session, recipients, text=None, raws=None):
    """[(writer, audience, recipients, text)]: the events one append makes,
    by D4. `recipients` [{session, alias}, ...] (none for a session's own
    events). `raws`, when given, is each recipient's leading tags as
    [(their place in the run, their raw text)], so a split's text names only
    its own recipients (D4); the text is untouched when nothing splits, or
    with no `raws` (a selector, `@all`). Unreachable when a recipient's
    owners, or the writing session's, fall outside the audience;
    StreamUnknown as own_audience."""
    base = sminos.writer_id(writer_session or None)
    own = own_audience(writer_session) if writer_session else None
    if not recipients:
        return [(sminos.stream_writer(base, own), own, [], text)]
    held = _read_audiences()
    if "access" not in (held.get("capabilities") or []):
        for r in recipients:
            if is_local(r["session"]):
                audience_of(r["session"], held)   # a private local recipient: StreamUnknown
        return [(sminos.stream_writer(base, own), own, list(recipients), text)]
    groups = {}
    for i, r in enumerate(recipients):
        aud = meet(own, audience_of(r["session"], held))
        groups.setdefault(None if aud is None else tuple(aud), []).append(i)
    writer_owners = owners_of(writer_session, held) if writer_session else None
    out = []
    for key, idx in groups.items():
        aud = None if key is None else list(key)
        rs = [recipients[i] for i in idx]
        if aud is not None:
            for r in rs:
                owners = owners_of(r["session"], held)
                if owners is not None and set(owners) <= set(aud):
                    continue
                name = r.get("alias") or r["session"][:8]
                if own is not None:
                    outside = sorted(set(owners or []) - set(aud))
                    raise Unreachable("%s can't be reached from this session: this session is unlisted; share it "
                                      "as Can message with %s first" % (name, ", ".join(outside) or "its owners"))
                raise Unreachable("no member @%s in project %s" % (name, project.name if project else "?"))
            if writer_session and (writer_owners is None or not set(writer_owners) <= set(aud)):
                name = rs[0].get("alias") or rs[0]["session"][:8]
                raise Unreachable("no member @%s in project %s" % (name, project.name if project else "?"))
        split = text
        if len(groups) > 1 and raws is not None and text is not None:
            split = split_text(text, [raw for _, raw in sorted(t for i in idx for t in raws[i])])
        out.append((sminos.stream_writer(base, aud), aud, rs, split))
    return out


# ------------------------------------------------------------- provenance


def redact(event, audience):
    """`event` with each provenance reference whose session's audience does
    not contain `audience` (the event's) written null (D4); a reference
    whose session's audience cannot be told is redacted too. In place;
    returns the event."""
    held = None
    for ref in session_refs(event):
        if ref["role"] != "provenance" or ref["path"].startswith("attest."):
            continue
        try:
            held = held if held is not None else _read_audiences()
            keep = contains(audience_of(ref["session"], held), audience)
        except StreamUnknown:
            keep = False
        if keep:
            continue
        if ref["path"] == "origin.spawnerSession":
            event["origin"] = {**event["origin"], "spawnerSession": None}
        elif ref["path"] == "to":
            event["to"] = None
    return event


# ------------------------------------------------------------- each stream's audience, kept


def streams_path(project):
    return os.path.join(project.home, STREAMS)


def streams_of(project):
    """{stream writer: audience} as kept in the project's home (keep_stream);
    {} when none is, or the file cannot be read."""
    try:
        d = sminos.json_at(streams_path(project))
    except (OSError, ValueError):
        return {}
    return {w: a for w, a in d.items() if isinstance(w, str) and is_audience(a)} if isinstance(d, dict) else {}


def stream_audience(project, writer):
    """A stream writer's audience as kept (keep_stream), or None."""
    try:
        d = sminos.json_at(streams_path(project))
    except (OSError, ValueError):
        return None
    got = d.get(writer) if isinstance(d, dict) else None
    return list(got) if is_audience(got) else None


def keep_stream(project, writer, audience):
    """A stream writer's audience, kept before its first event is written."""
    if audience is None or not sminos.is_stream(writer) or stream_audience(project, writer) == audience:
        return
    path = sminos.project_path(project, STREAMS)
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                d = sminos.json_at(path)
                d = d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                d = {}
            d[writer] = list(audience)
            tmp = "%s.%d.tmp" % (path, os.getpid())
            with open(tmp, "w", encoding="ascii") as f:
                json.dump(d, f, ensure_ascii=True, sort_keys=True)
                f.write("\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
