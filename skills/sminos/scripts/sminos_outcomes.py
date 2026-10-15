#!/usr/bin/env python3
"""sminos_outcomes — what became of each event from outside this machine
that delivery settled (DC7 of the desk; DX4's `delivery`).

`deliver_next` is the one boundary every delivery passes, whichever process
runs it (the uplink's immediate delivery, the daemon's tick and its retries,
a sender's fast path). When it settles an event written outside this machine
(sminos_policy.outside_origin) for a recipient of a hub project, it records
the outcome here, in the project's `outcomes.jsonl`, before the settlement:

    {"event": {"writer", "seq"}, "session", "outcome", "reason"}

`outcome` is DX4's: `delivered` (pushed to the live session, or the stopped
seat resumed with it — also when the push was taken and its answer lost),
`recorded` (the recipient was not running and is pushed nothing),
`refused-read-only` (the machine's policy), `failed` (given up after
DELIVERY_ATTEMPTS). A crash between the record and the settlement records it
again at the next attempt; the hub keeps the latest per event and recipient.

The uplink drains the file: it seals each record with the org key (DX1,
`smns-hub-delivery-v1`) as it posts it, and drops what a POST answered 200
carried. Nothing leaves this machine without its code.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402

OUTBOX = "outcomes.jsonl"
READ_ONLY = "refused-read-only"
UNCERTAIN = {"sent?": "uncertain: the session took the message and its answer never came",
             "woken?": "uncertain: the stopped seat was resumed with it and reported no session id"}


def of_push(push, member):
    """(DX4 outcome, reason) for what delivery made of an event: a push's
    outcome (sminos.push_event's), or READ_ONLY for one the policy refused."""
    if push == READ_ONLY:
        return READ_ONLY, "this machine is read-only: nothing written outside it is delivered"
    if push == "sent":
        return "delivered", "pushed to the live session"
    if push == "woken":
        return "delivered", "the stopped seat was resumed with it"
    if push in UNCERTAIN:
        return "delivered", UNCERTAIN[push]
    if push.startswith("failed"):
        return "failed", "given up after %d attempts: %s" % (sminos.DELIVERY_ATTEMPTS, push[len("failed:"):])
    if member.seat is None:
        return "recorded", ("the session is not running here (closed, or its membership ended): it is pushed "
                            "nothing, and reads the log when it is back")
    return "recorded", "the seat is not live and was not resumed for it (retired, holding another session, or an @all)"


class Outbox:
    """One project's outcomes not yet posted."""

    def __init__(self, project):
        self.project = project

    @property
    def path(self):
        return os.path.join(self.project.home, OUTBOX)

    def lock(self):
        return sminos.flocked(sminos.project_path(self.project, OUTBOX + ".lock"))

    def record(self, e, session, outcome, reason):
        line = json.dumps({"event": {"writer": e["writer"], "seq": e["seq"]}, "session": session,
                           "outcome": outcome, "reason": reason}, ensure_ascii=True) + "\n"
        with self.lock():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(line)

    def take(self):
        """(the records waiting, oldest first; how many lines they took): a
        line that is no record is counted and skipped, so `drop` takes it too."""
        try:
            with open(self.path) as f:
                lines = f.read().split("\n")[:-1]
        except OSError:
            return [], 0
        out = []
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
        return out, len(lines)

    def read(self):
        return self.take()[0]

    def waiting(self):
        """Whether anything waits, without reading it."""
        try:
            return os.path.getsize(self.path) > 0
        except OSError:
            return False

    def drop(self, n):
        """The first `n` lines were posted: they go. Lines appended meanwhile stay."""
        if n <= 0:
            return
        with self.lock():
            try:
                with open(self.path) as f:
                    lines = f.read().split("\n")[:-1]
            except OSError:
                return
            rest = lines[n:]
            tmp = "%s.%d.tmp" % (self.path, os.getpid())
            with open(tmp, "w") as f:
                f.write("".join(line + "\n" for line in rest))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)


def record(project, e, session, push, member):
    """Delivery's record of an outside-origin event settled for `session`,
    for a hub project; nothing for another. A record that cannot be written
    is said in daemon.log and does not hold delivery up."""
    if not project.hub:
        return
    outcome, reason = of_push(push, member)
    try:
        Outbox(project).record(e, session, outcome, reason)
    except OSError as err:
        sminos.daemon_log("delivery: the outcome of %s for %s could not be recorded: %s" % (
            sminos.event_ref(e), session, err))


def message(key, machine, project_id, r):
    """A record as DX4's `delivery` message, sealed under a fresh nonce; None
    when it has no canonical form (said in daemon.log)."""
    draft = {"event": r.get("event"), "session": r.get("session"), "outcome": r.get("outcome"),
             "reason": r.get("reason")}
    try:
        body = codes.seal(key, "delivery", project_id, draft, codes.b64url(os.urandom(codes.NONCE_BYTES)))
    except codes.NotCanonical as err:
        sminos.daemon_log("delivery: an outcome in %s has no canonical form (%s): not sent" % (project_id, err))
        return None
    return {"t": "session", "message": {"project": project_id, "machine": machine, "session": r.get("session"),
                                        "kind": "delivery", "sub": None, "n": None, "body": body}}
