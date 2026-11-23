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
