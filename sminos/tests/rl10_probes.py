"""What rl10_conformance.py checks over the whole conversation in place of its
probes, and the event its `machine-event` scene binds: pure functions over
what sminos sent and what this machine holds, so a test can drive them. A
conversation holds more than one log (two projects, a channel) and sessions
staged at any case, so a position is a log's, a words? is held to the log it
names, and a member is a session the replay staged on this machine."""

import json


def bodies_twice(uploads):
    """[(log id, writer, seq)] uploaded with more than one body. `uploads`:
    (log id, event) pairs, as the `events` frames named their log."""
    bodies = {}
    for log, e in uploads:
        bodies.setdefault((log, e["writer"], e["seq"]), set()).add(json.dumps(e, sort_keys=True))
    return [k for k, v in bodies.items() if len(v) > 1]


def _stored(f, logs):
    held = logs.get(f.get("project"))
    return held(f["event"]["writer"], f["event"]["seq"]) if held is not None else None


def not_as_stored(asks, logs):
    """The ids of the words? whose event is not the one the log they name
    stores, its verdict left out. `logs`: {log id: (writer, seq) → the stored
    event or None}, every log this machine knows."""
    wrong = []
    for f in asks:
        stored = _stored(f, logs)
        if stored is None or {k: v for k, v in stored.items() if k != "verified"} != f["event"]:
            wrong.append(f["id"])
    return wrong


def not_in_its_log(asks, logs):
    """The ids of the words? whose `project` names no log holding their event's position."""
    return [f["id"] for f in asks if _stored(f, logs) is None]


def not_members(asks, members):
    """The ids of the words? that name no session the replay staged on this machine (`members`)."""
    members = set(members)
    return [f["id"] for f in asks if f["session"] not in members]


def machine_event(step, at, kid):
    """The event a `machine-event` scene binds, as the endpoint sends it down:
    signed, and attested to the scene's owners; a scene that names none (an
    operator's event) is unattested."""
    attest = {"attest": {"owners": step["owners"], "ownersProof": [], "origin": {"kind": "terminal"},
                         "stateVersion": 6}} if "owners" in step else {}
    return {"ts": at, "created": at, "writer": "%s/%s" % (step["machine"], step["session"]), "seq": step["seq"],
            **step["body"], **attest, "sig": {"kid": kid, "value": "AQ"}}


def asked_again(asks, log, writer, seq):
    """The ids of the words? about `log`'s event at (writer, seq): a device's
    words whose signer was revoked are never asked again, while the same
    writer's position in another log (a channel's) is another event."""
    return [f["id"] for f in asks if f.get("project") == log and f["event"].get("writer") == writer
            and f["event"].get("seq") == seq]


def _session_of(writer):
    """The session template a writer `{{name}}/{{session:Sn}}` names, else None."""
    tail = str(writer or "").rpartition("/")[2]
    return tail if tail.startswith("{{session:") else None


def order_edges(cases):
    """{(case, step): [(case, step)]}: the lines a channel's line waits for,
    read off the lines themselves in the fixture's order. An `events` up
    waits for the latest member frame of its writer's session and of each
    session it writes to (none for a `to` that is no list, "*"); a words?
    or reach? waits for the latest member frame of the session it asks
    about, and, for an own event (given inline), for the upload that
    carried it. A line of no channel waits for none."""
    member, uploaded, edges = {}, {}, {}
    for ci, case in enumerate(cases):
        for si, step in enumerate(case["steps"]):
            line = step.get("up")
            if not isinstance(line, dict):
                continue
            if line.get("t") == "member":
                member[line.get("session")] = (ci, si)
                continue
            if not str(line.get("project") or "").startswith("{{channel:"):
                continue
            deps = set()
            if line.get("t") == "events":
                for e in line.get("events") or []:
                    to = e.get("to") if isinstance(e.get("to"), list) else []   # "*", everyone: no one session's frame
                    for s in [_session_of(e.get("writer"))] + [t.get("session") for t in to]:
                        if s in member:
                            deps.add(member[s])
                    uploaded[(line["project"], e.get("writer"), e.get("seq"))] = (ci, si)
            elif line.get("t") in ("words?", "reach?"):
                if line.get("session") in member:
                    deps.add(member[line["session"]])
                e = line.get("event")
                if isinstance(e, dict) and (line["project"], e.get("writer"), e.get("seq")) in uploaded:
                    deps.add(uploaded[(line["project"], e.get("writer"), e.get("seq"))])
            if deps:
                edges[(ci, si)] = sorted(deps)
    return edges


def after_index(deps, matched, conn):
    """The index on connection `conn` a line is matched past: the latest of
    its `deps`' matches there (`matched`: (case, step) → (connection,
    index)); -1 where none of them was matched on it."""
    return max((at[1] for at in (matched.get(d) for d in deps) if at is not None and at[0] == conn), default=-1)
