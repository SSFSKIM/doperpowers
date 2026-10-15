#!/usr/bin/env python3
"""sminos_rpc — the RPCs a browser sends this machine through the hub (DC7 M3
of the desk: DX6's shapes and the machine's policy, DX1's code, §5's paths,
§6's boundary).

An RPC arrives as DX2's `rpc` frame and leaves as `rpc-result`, republished
after every connect until the hub's `rpc-ack`. The daemon is the execution
boundary: an RPC runs only once every check below holds, in this order, and
the first that fails is its answer, as DX6's error code:

1. its code (DX1, `smns-hub-rpc-v1`, under the project it names): `bad-code`;
2. where it runs, since every enrolled machine holds the org key: `machine`
   is this machine's enrolled name (`wrong-machine`), `project` a hub project
   of this machine in its org (`unknown-project`), the session one that
   joined that project from this machine, ended or not (`no-session`);
3. the ledger: a nonce it knows is answered from it and never run again;
4. freshness: `created` within 60 s of this machine's clock, either way
   (`stale`), so the ledger's day covers every nonce that could still pass;
5. the machine's policy (sminos_policy): read-only refuses every RPC
   (`read-only`); a spawn runs only in a known checkout of the project
   (`unknown-checkout`), under a permission mode no looser than the ceiling
   (`above-ceiling`; no mode asked is the ceiling, passed explicitly);
6. the args' shape (`bad-shape`): nothing reaches a command line that could
   be read as a flag;
7. for an answer or a decision, the digest (DX1's `{session, request, tool,
   input_sha256}`) against the request still pending in the session, as its
   bridge reports it (`digest-mismatch`, `not-pending`);
8. the session's kind against §5's table (`unsupported`).

A refusal from 1 or 2 precedes the ledger and is not kept in it: it goes up
while its project is open on the stream (an `unknown-project` never is, and
is only said in daemon.log). From 3 on, a nonce has one answer, kept.

At most once (DX6): `daemon/rpcs.json` claims the nonce before the RPC has
any effect and records the outcome before the result goes up; entries are
kept a day. A nonce left claimed (the uplink stopped between the two writes)
is reconciled from the action's own trace — a spawned seat carries its nonce
on its record (`rpc_nonce`), a steer's row is in the transcript — for as long
as that trace may still appear, then answered `failed` `interrupted`.

Execution (§5) goes through the session's bridge (DC2's DX5): steer,
interrupt, model, and compact as commands; an answer or a decision as the
request's decision, by the member. A steer to a live session without a
bridge takes `sminos steer`'s own fallbacks (the supervisor's `reply`, the
inbox frame), so its result names no row. Spawn and retire run `sminos spawn`
and `sminos retire`, which record `joined` and `retired` as they always do.
Resume is DC7's M4: answered `unsupported` until it lands.

A compaction's outcome reaches browsers as DX4 `compact`, carrying the RPC's
nonce, from the bridge's `compact` events for the command this daemon issued
(read by the requests' readers, sminos_requests).

Checks 1-6 and the ledger's lookup run on the uplink's main thread, which
alone may call sminos (its caches are module globals); the digest, the kind,
the claim, and the execution run on a worker of their own, since a bridge
command waits seconds and a spawn much longer. What a worker finishes is
queued, and the main thread posts it.
"""

import calendar
import hashlib
import http.client
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_bridge as bridge  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_control as control  # noqa: E402
import sminos_policy as policy  # noqa: E402

LEDGER_FILE = "rpcs.json"
FRESH_S = 60              # an RPC older (or younger) than this by the machine's clock is stale
KEPT_S = 86400            # the ledger keeps an entry a day
LOOSE_S = 600             # a refusal kept out of the ledger waits this long for its project to open
STEER_TRACE_S = 30        # a claimed steer's row is looked for this long after its claim
SPAWN_TRACE_S = 420       # a claimed spawn's seat: `claude --bg` may take 300 s, its uuid poll more
COMPACT_HELD_S = 60       # a `compact` event waits at most this long for its command's result to name it
RECONCILE_EVERY = 1.0     # how often claims left by a stop are looked at again
SPAWN_TIMEOUT = 600
VERB_TIMEOUT = 120
SNAPSHOT_TIMEOUT = 8      # the bridge holds its stream up to 5 s until the mod's first resync
DECISION_TIMEOUT = 15     # an async question's answer is relayed to the mod, which waits 5 s
SPAWN_TASK = "Begin with your brief."
RPC_NAMES = ("steer", "interrupt", "answer", "decide", "model", "compact", "spawn", "retire", "resume")
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,199}")
WORKTREE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
CREATED_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]{1,9})?Z")
SEAT_RE = re.compile(r"\[[0-9a-f]+ / ([0-9a-f-]{36})\]")
STEER_ROW_RE = re.compile(r"\(row ([0-9a-f-]{36})\)")
IDLE = "no turn is running"   # the mod's steer refusal (DX5): "no turn is running to steer: send it instead"
SMINOS_CLI = os.path.join(os.path.dirname(os.path.realpath(__file__)), "sminos")


def log(line):
    sminos.daemon_log("rpc: " + line)


def done(result):
    return {"state": "done", "result": result}


def failed(code, message, **fields):
    """DX6's failed outcome; `fields` are RpcError's `winner`, `by`,
    `terminalOnly`, each only when given."""
    return {"state": "failed", "error": {"code": code, "message": message,
                                         **{k: v for k, v in fields.items() if v is not None}}}


class Refused(Exception):
    """An RPC answered `failed` with one of DX6's codes."""

    def __init__(self, code, message, **fields):
        super().__init__(message)
        self.outcome = failed(code, message, **fields)


def who_won(body):
    """RpcError's `winner`, `by`, `terminalOnly` from the fields a bridge's
    refusal carries (DX5's 409s; a request's `settled`), never from its
    text."""
    s = body.get("settled") if isinstance(body.get("settled"), dict) else {}
    out = {"winner": body.get("winner", s.get("winner")), "by": body.get("by", s.get("by"))}
    out = {k: v for k, v in out.items() if isinstance(v, str) and v}
    if body.get("terminalOnly") is True:
        out["terminalOnly"] = True
    return out


def created_at(text):
    """Epoch seconds of an ISO 8601 UTC time (`…Z`), or None."""
    m = CREATED_RE.fullmatch(text) if isinstance(text, str) else None
    if not m:
        return None
    try:
        whole = calendar.timegm(tuple(int(g) for g in m.groups()[:6]) + (0, 0, 0))
    except (ValueError, OverflowError):
        return None
    return whole + float(m.group(7) or 0)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def alias_for(nonce):
    """A spawned seat's alias: where it came from, and its nonce's, so a
    second launch under one nonce could only collide with the first."""
    return "web-" + sha256(nonce)[:6]


# ------------------------------------------------------------- the ledger


class Ledger:
    """`daemon/rpcs.json`: nonce → {project, rpc, session, at, text_sha256?,
    outcome?, acked?}. An entry without `outcome` is a claim. Written whole
    at every change, under a lock (the main thread and the workers write);
    entries older than KEPT_S go at every write.

    A ledger that exists and cannot be read could hold claims and answered
    nonces: it is never replaced (`broken` says why), and `readable` tries it
    again, so the RPCs wait for it rather than run a nonce twice."""

    def __init__(self, clock):
        self.clock = clock
        self.path = os.path.join(sminos.root(), "daemon", LEDGER_FILE)
        self.lock = threading.Lock()
        self.broken = None
        self.entries = {}
        self.load()

    def load(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("not an object")
        except FileNotFoundError:
            d = {}
        except (OSError, ValueError) as e:
            if self.broken is None:
                log("the ledger %s cannot be read (%s): no RPC runs until it can" % (self.path, e))
            self.broken = str(e) or type(e).__name__
            return
        if self.broken is not None:
            log("the ledger %s can be read again" % self.path)
        self.broken = None
        self.entries = {n: e for n, e in d.items() if isinstance(e, dict)}

    def readable(self):
        """Whether the ledger is known: a broken one is read again first."""
        with self.lock:
            if self.broken is not None:
                self.load()
            return self.broken is None

    def save(self):
        """Raises OSError when the ledger could not be written, or must not
        be: a ledger that could not be read is never replaced."""
        if self.broken is not None:
            raise OSError("the ledger %s cannot be read (%s): it is not replaced" % (self.path, self.broken))
        cutoff = self.clock() - KEPT_S
        self.entries = {n: e for n, e in self.entries.items()
                        if isinstance(e.get("at"), (int, float)) and e["at"] >= cutoff}
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        sminos.write_json(self.path, self.entries)

    def get(self, nonce):
        with self.lock:
            e = self.entries.get(nonce)
            return dict(e) if e is not None else None

    def put(self, nonce, entry):
        with self.lock:
            self.entries[nonce] = entry
            self.save()

    def answer(self, nonce, outcome):
        """The outcome kept; False when it could not be written (the claim
        stays on disk, and a restart reconciles it)."""
        with self.lock:
            e = self.entries.setdefault(nonce, {"at": self.clock()})
            e["outcome"], e["acked"] = outcome, False
            try:
                self.save()
                return True
            except OSError as err:
                log("the outcome of %s could not be kept in %s: %s" % (nonce, self.path, err))
                return False

    def acked(self, nonce, value=True):
        with self.lock:
            e = self.entries.get(nonce)
            if e is None or e.get("acked") is value:
                return
            e["acked"] = value
            try:
                self.save()
            except OSError as err:
                log("the ledger could not be written (%s): %s is sent again after the next connect" % (err, nonce))

    def items(self):
        with self.lock:
            return [(n, dict(e)) for n, e in self.entries.items()]


# ------------------------------------------------------------- the RPCs


class Rpcs:
    """The RPCs this machine was sent, and their results owed to the hub.
    Kept across streams by the uplink; `wake` is the current stream's."""

    def __init__(self, key, machine, wake=lambda: None, clock=time.time):
        self.key = key
        self.machine = machine
        self.wake = wake
        self.clock = clock
        self.ledger = Ledger(clock)
        self.loose = {}           # nonce → (project id, outcome, at): refusals the ledger does not keep
        self.flight = set()       # nonces a worker holds
        self.finished = queue.Queue()  # what workers finished, for the main thread
        self.sent_here = set()    # nonces whose result went up on this stream
        self.compact_ids = {}     # a bridge's compact command id → (project id, session, nonce, at)
        self.compact_held = []    # [(project id, session, event, at)]: events whose command is not named yet
        self.compact_flight = {}  # nonce → session: compact RPCs whose command's id is not known yet
        self.model_locks = {}     # session → the lock its model and effort are read and changed under
        self.locks_lock = threading.Lock()
        self.compact_out = []     # DX4 compact messages owed, as frames
        self.next_reconcile = 0.0
        self.reconcile()

    # ---------------------------------------------------- frames down

    def receive(self, rpc, here):
        """An `rpc` frame's RPC, on the main thread: checks 1-6, then a
        worker for the rest. `here` is what the uplink knows of this machine
        (project, has_session, record, checkouts)."""
        if not isinstance(rpc, dict):
            log("an rpc frame without an RPC: passed by")
            return
        nonce, pid, name = rpc.get("nonce"), rpc.get("project"), rpc.get("rpc")
        if not isinstance(pid, str) or codes.failure(self.key, "rpc", pid, rpc) is not None:
            return self.refuse_loose(rpc, "bad-code", "the RPC's code does not verify under the org key")
        # A copy from here on: what the checks normalize is not the RPC the
        # code covered.
        args = dict(rpc["args"]) if isinstance(rpc.get("args"), dict) else {}
        rpc = {**rpc, "args": args}
        if name not in RPC_NAMES:
            return self.refuse_loose(rpc, "unsupported", "no RPC %r on this machine" % (name,))
        if rpc.get("machine") != self.machine:
            return self.refuse_loose(rpc, "wrong-machine", "this is %s, not %s" % (self.machine, rpc.get("machine")))
        project = here.project(pid)
        if project is None:
            return self.refuse_loose(rpc, "unknown-project",
                                     "%s is no hub project of this machine in its org" % pid)
        sid = args.get("session")
        if name != "spawn" and not (isinstance(sid, str) and sminos.UUID_RE.match(sid)
                                    and here.has_session(project, sid)):
            return self.refuse_loose(rpc, "no-session", "no session %s of %s on this machine" % (sid, project.name))
        if not self.ledger.readable():
            return self.refuse_loose(rpc, "failed", "this machine's RPC ledger cannot be read (%s): no RPC runs "
                                     "until it can, so none runs twice" % self.ledger.broken)
        known = self.ledger.get(nonce)
        if known is not None or nonce in self.flight:
            if known is not None and "outcome" in known:
                self.sent_here.discard(nonce)       # forwarded again: the hub lost it, so it goes again
                self.ledger.acked(nonce, False)
            return                                  # in flight, or a claim being reconciled: its result follows
        try:
            self.admit(rpc, project, args, here)
        except Refused as r:
            self.keep(rpc, r.outcome)
            return
        record = here.record(sid) if sid else None
        facts = {"running": record is not None, "bg": control.bg_job(record or {}), "root": project.root,
                 "checkout": args.get("checkout"), "status": (record or {}).get("status")}
        self.flight.add(nonce)
        if name == "compact":
            self.compact_flight[nonce] = sid
        threading.Thread(target=self.run, args=(rpc, facts), name="rpc-" + name, daemon=True).start()

    def admit(self, rpc, project, args, here):
        """Checks 4-6: freshness, the policy, the args' shape. Refused, or
        nothing; a spawn's `permission_mode` is set to what it runs under."""
        at = created_at(rpc.get("created"))
        if at is None or abs(self.clock() - at) > FRESH_S:
            raise Refused("stale", "created %s, more than %d s from this machine's clock" % (
                rpc.get("created"), FRESH_S))
        p = policy.load()
        if p["read_only"]:
            raise Refused("read-only", "this machine is read-only: it runs no RPC")
        name = rpc["rpc"]
        if name == "spawn":
            admit_spawn(args, p["ceiling"], here.checkouts(project))
        shape(name, args, rpc.get("member"))

    def refuse_loose(self, rpc, code, message):
        """A refusal before the ledger: up while its project is open, else
        said only here."""
        nonce, pid = rpc.get("nonce"), rpc.get("project")
        log("%s %s refused %s: %s" % (rpc.get("rpc"), nonce, code, message))
        if codes.b64url_bytes(nonce, codes.NONCE_BYTES) is None or not isinstance(pid, str):
            return
        self.loose[nonce] = (pid, failed(code, message), self.clock())

    def keep(self, rpc, outcome):
        """A refusal from the ledger on: the nonce's one answer (from a
        worker too: what it cannot keep reaches `loose` through the main
        thread)."""
        e = {"project": rpc["project"], "rpc": rpc["rpc"], "session": rpc["args"].get("session"),
             "at": self.clock(), "outcome": outcome, "acked": False}
        try:
            self.ledger.put(rpc["nonce"], e)
        except OSError as err:
            log("the ledger could not be written (%s): %s answered without it" % (err, rpc["nonce"]))
            self.finished.put(("loose", (rpc["nonce"], rpc["project"], outcome)))
        if outcome["state"] == "failed":
            log("%s %s refused %s: %s" % (rpc["rpc"], rpc["nonce"], outcome["error"]["code"],
                                          outcome["error"]["message"]))

    def ack(self, frame):
        nonce = frame.get("nonce")
        if self.loose.pop(nonce, None) is None:
            self.ledger.acked(nonce)

    # ---------------------------------------------------- a worker

    def run(self, rpc, facts):
        """Checks 7-8, the claim, the execution, the outcome kept: off the
        main thread, calling nothing of sminos's cached state."""
        nonce = rpc["nonce"]
        try:
            try:
                act = self.plan(rpc, facts)
            except Refused as r:
                self.keep(rpc, r.outcome)
                return
            claim = {"project": rpc["project"], "rpc": rpc["rpc"], "session": rpc["args"].get("session"),
                     "at": self.clock()}
            if rpc["rpc"] == "steer":
                claim["text_sha256"] = sha256(rpc["args"]["text"])
            try:
                self.ledger.put(nonce, claim)
            except OSError as e:
                self.finished.put(("loose", (nonce, rpc["project"],
                                             failed("failed", "the ledger could not be written: %s" % e))))
                return
            try:
                outcome = act()
            except Refused as r:
                outcome = r.outcome
            except Exception as e:  # noqa: BLE001 — an execution that broke is a failure, said
                outcome = failed("failed", "%s: %s" % (type(e).__name__, e))
            if not self.ledger.answer(nonce, outcome):
                self.finished.put(("loose", (nonce, rpc["project"], outcome)))
            if outcome["state"] == "failed":
                log("%s %s failed %s: %s" % (rpc["rpc"], nonce, outcome["error"]["code"], outcome["error"]["message"]))
        finally:
            self.finished.put(("done", nonce))
            self.wake()

    def plan(self, rpc, facts):
        """The action an RPC runs once claimed, or Refused (checks 7-8)."""
        name, args, nonce = rpc["rpc"], rpc["args"], rpc["nonce"]
        if name == "spawn":
            return lambda: spawn(args, nonce, facts["checkout"], rpc["member"])
        sid = args["session"]
        if name == "resume":
            raise Refused("unsupported", "Resume is not built on this machine yet (DC7's M4)")
        path = bridge.endpoint(sid)
        status = bridge.probe(path)
        bridged = status is not None and status.get("session") == sid
        if name in ("answer", "decide") and bridged:
            check_digest(path, sid, args["digest"])
        if name == "retire":
            return lambda: retire(sid, facts["root"], rpc["member"])
        if not facts["running"]:
            raise Refused("unsupported", "the session is not running: only Resume brings it back")
        if bridged:
            if name == "steer":
                return lambda: steer(path, args["text"])
            if name == "interrupt":
                return lambda: interrupt(path)
            if name == "model":
                return lambda: model(path, sid, args, self.model_lock(sid))
            if name == "compact":
                return lambda: self.compact(path, rpc, sid)
            if name == "answer":
                body = {"behavior": "allow", "updatedInput": {"answers": args["answers"]}, "by": rpc["member"]}
                return lambda: decide(path, args["digest"]["request"], body)
            body = {"behavior": args["decision"], "by": rpc["member"]}
            if "message" in args:
                body["message"] = args["message"]
            return lambda: decide(path, args["digest"]["request"], body)
        if name == "steer":
            if facts["status"] == "idle":
                # The engine's own record says no turn runs (composite 21c32db7).
                raise Refused("idle", "no turn is running to steer: send it instead")
            return lambda: steer_without_bridge(sid, args["text"], facts["root"])
        raise Refused("unsupported", "%s needs the session's bridge; %s has none (§5)" % (
            name, "this --bg job" if facts["bg"] else "this terminal session"))

    def model_lock(self, sid):
        with self.locks_lock:
            return self.model_locks.setdefault(sid, threading.Lock())

    def compact(self, path, rpc, sid):
        result, cid = command(path, {"op": "compact"})
        if not result["ok"]:
            raise Refused("failed", refusal(result))
        if cid:
            self.finished.put(("compact", (cid, rpc["project"], sid, rpc["nonce"])))
        r = result.get("result") or {}
        return done({"at": "turn-end" if r.get("queued") else "now"})

    # ---------------------------------------------------- frames up

    def take(self):
        while True:
            try:
                kind, data = self.finished.get_nowait()
            except queue.Empty:
                return
            if kind == "done":
                self.flight.discard(data)
                self.compact_flight.pop(data, None)
            elif kind == "loose":
                nonce, pid, outcome = data
                self.loose[nonce] = (pid, outcome, self.clock())
            elif kind == "compact":
                cid, pid, sid, nonce = data
                self.compact_ids[cid] = (pid, sid, nonce, self.clock())

    def compacted(self, items):
        """The bridges' `compact` events (session, project id, event): every
        compaction of a bridged session becomes DX4 `compact` (composite
        21c32db7), carrying the nonce of the DX6 `compact` that asked for it,
        or null for one nobody here asked for. An event no command is known
        to have issued waits while a compact RPC of its session is still
        waiting for its command's id, since the bridge may say the compaction
        started before it answers the command (at most COMPACT_HELD_S)."""
        self.take()
        now = self.clock()
        pending = self.compact_held + [(pid, sid, e, now) for sid, pid, e in items if isinstance(e, dict) and pid]
        self.compact_held = []
        asking = set(self.compact_flight.values())
        for pid, sid, e, at in pending:
            cid = e.get("id")
            named = self.compact_ids.get(cid)
            if named is None and sid in asking and now - at < COMPACT_HELD_S:
                self.compact_held.append((pid, sid, e, at))
                continue
            body = {"rpc": named[2] if named else None, "phase": e.get("phase")}
            for k in ("tokensBefore", "tokensAfter", "skip", "error"):
                if k in e:
                    body[k] = e[k]
            self.compact_out.append({"t": "session", "message": {
                "project": named[0] if named else pid, "machine": self.machine, "session": named[1] if named else sid,
                "kind": "compact", "sub": None, "n": None, "body": body}})
            if e.get("phase") == "end":
                self.compact_ids.pop(cid, None)
        self.compact_ids = {c: v for c, v in self.compact_ids.items() if now - v[3] < KEPT_S}

    def reconcile(self):
        """Claims no worker holds: answered from their trace, or
        `interrupted` once no trace can come any more (main thread: it reads
        the seats and the transcripts)."""
        now = self.clock()
        self.next_reconcile = now + RECONCILE_EVERY
        for nonce, e in self.ledger.items():
            if "outcome" in e or nonce in self.flight:
                continue
            outcome, window = trace(nonce, e)
            if outcome is None and window and now - e.get("at", 0) < window:
                continue
            if outcome is None:
                outcome = failed("interrupted", "the daemon stopped while it ran: it is not run again")
            self.ledger.answer(nonce, outcome)
            log("%s %s, claimed before a stop, reconciled: %s" % (e.get("rpc"), nonce, outcome["state"]))

    def results(self, pids, again):
        """`rpc-result` frames of these projects not yet acknowledged; with
        `again`, also those already sent on this stream."""
        out = []
        for nonce, e in self.ledger.items():
            if "outcome" in e and not e.get("acked") and e.get("project") in pids \
                    and (again or nonce not in self.sent_here):
                out.append({"t": "rpc-result", "project": e["project"], "nonce": nonce, "outcome": e["outcome"]})
        now = self.clock()
        for nonce, (pid, outcome, at) in list(self.loose.items()):
            if now - at > LOOSE_S:
                del self.loose[nonce]
            elif pid in pids and (again or nonce not in self.sent_here):
                out.append({"t": "rpc-result", "project": pid, "nonce": nonce, "outcome": outcome})
        return out

    def due(self, opened):
        """What goes up now for the projects open on the stream: new
        results, then DX4 compact messages. Not taken until `sent`."""
        self.take()
        if self.clock() >= self.next_reconcile:
            self.reconcile()
        compacts = [f for f in self.compact_out if f["message"]["project"] in opened]
        return self.results(set(opened), False) + compacts

    def opening(self, pid):
        """What follows a project's `hello` on a new stream: every result of
        it the hub has not acknowledged (DX2)."""
        self.take()
        return self.results({pid}, True)

    def sent(self, frames):
        """`frames` reached the hub (a POST answered 200)."""
        ids = {id(f) for f in frames}
        self.compact_out = [f for f in self.compact_out if id(f) not in ids]
        self.sent_here.update(f["nonce"] for f in frames if f.get("t") == "rpc-result")

    def reset(self):
        """A new stream: nothing is taken as sent on it yet."""
        self.sent_here.clear()


# ------------------------------------------------------------- checks


def admit_spawn(args, ceiling, checkouts):
    """A spawn's policy (§6): into a known checkout of the project on this
    machine, under a mode no looser than the ceiling; the mode it runs
    under, written into `args` (absent: the ceiling)."""
    checkout = args.get("checkout")
    known = {os.path.realpath(c["path"]) for c in checkouts}
    if not (isinstance(checkout, str) and checkout and os.path.realpath(checkout) in known):
        raise Refused("unknown-checkout", "%s is not a checkout of the project on this machine" % (checkout,))
    args["checkout"] = os.path.realpath(checkout)
    mode = args.get("permission_mode", ceiling)
    modes = policy.MODES
    if ceiling not in modes:
        raise Refused("above-ceiling", "the ceiling %r is no permission mode this machine knows" % (ceiling,))
    if mode not in modes or modes.index(mode) > modes.index(ceiling):
        raise Refused("above-ceiling", "%r is looser than this machine's ceiling, %s" % (mode, ceiling))
    args["permission_mode"] = mode


def is_text(v):
    return isinstance(v, str) and v.strip() != ""


def is_digest(d):
    return isinstance(d, dict) and all(isinstance(d.get(k), str) and d[k] for k in
                                       ("session", "request", "tool", "input_sha256"))


def shape(name, args, member):
    """Check 6: the args' shape, as DX6 has them (and, for a decision, the
    member it is made by)."""
    def need(ok, what):
        if not ok:
            raise Refused("bad-shape", "%s: %s" % (name, what))

    if name == "steer":
        need(is_text(args.get("text")), "text is the steer's text")
    elif name in ("answer", "decide"):
        need(isinstance(member, str) and codes.MEMBER_RE.fullmatch(member), "the member is a member's id")
        need(is_digest(args.get("digest")), "digest is {session, request, tool, input_sha256}")
        need(args["digest"]["session"] == args["session"], "the digest names another session")
        if name == "answer":
            a = args.get("answers")
            need(isinstance(a, dict) and a and all(isinstance(k, str) and isinstance(v, str) for k, v in a.items()),
                 "answers maps each question to its answer")
        else:
            need(args.get("decision") in ("allow", "deny"), "decision is allow or deny")
            need(isinstance(args.get("message", ""), str), "message is text")
    elif name == "model":
        m, e = args.get("model"), args.get("effort")
        need(m is not None or e is not None, "a model, an effort, or both")
        need(m is None or (isinstance(m, str) and MODEL_RE.fullmatch(m)), "model is an id, an alias, or default")
        need(e is None or e in control.EFFORTS, "effort is one of %s" % ", ".join(control.EFFORTS))
    elif name == "spawn":
        need(is_text(args.get("brief")), "brief is the session's brief")
        wt, m, e = args.get("worktree"), args.get("model"), args.get("effort")
        need(wt is None or (isinstance(wt, str) and WORKTREE_RE.fullmatch(wt)), "worktree is a name")
        need(m is None or (isinstance(m, str) and MODEL_RE.fullmatch(m)), "model is a model id or alias")
        need(e is None or e in control.EFFORTS, "effort is one of %s" % ", ".join(control.EFFORTS))


def check_digest(path, sid, digest):
    """Check 7: the request as the browser drew it is the one still
    pending in the session, as its bridge reports it."""
    rid = digest["request"]
    try:
        status, body = bridge.request(path, "GET", "/requests/" + urllib.parse.quote(rid, safe=""))
    except OSError as e:
        raise Refused("not-pending", "the session's bridge did not answer for %s: %s" % (rid, e))
    if status == 410:
        s = (body or {}).get("settled") or {}
        raise Refused("not-pending", "already settled: %s by %s" % (s.get("outcome"), s.get("by")),
                      **who_won(body if isinstance(body, dict) else {}))
    if status != 200 or not isinstance(body, dict):
        raise Refused("not-pending", "no request %s is pending in the session" % rid)
    tool_input = body.get("input")
    try:
        drawn = codes.input_sha256(tool_input)
    except codes.NotCanonical:
        drawn = None
    if (body.get("session"), body.get("request"), body.get("tool"), drawn) != \
            (sid, rid, digest["tool"], digest["input_sha256"]):
        raise Refused("digest-mismatch", "the request pending is not the one shown")


# ------------------------------------------------------------- execution


def command(path, body):
    """A command on the session's bridge, waiting for the mod's answer:
    ({ok, result?, error?}, the command's id). Refused `failed` when it did
    not reach the mod, or reached it and no answer came."""
    try:
        r = control.post_command(path, body)
    except control.Unanswered as e:
        raise Refused("failed", "the bridge took it and gave no answer (%s): it may have run" % e)
    if r is None:
        raise Refused("failed", "the session's bridge went away before the command reached it")
    status, out = r
    out = out if isinstance(out, dict) else {}
    if status == 504:
        raise Refused("failed", "the session did not answer within %d s: it may still run it" % (
            control.COMMAND_WAIT_MS // 1000))
    if status != 200:
        raise Refused("failed", "the bridge answered %d: %s" % (status, out.get("error")))
    return out, out.get("id")


def refusal(out):
    """The mod's reason for refusing a command, as the RPC's message: a
    refusal is the session's answer (a turn state it cannot know yet after a
    reload, a model it cannot map), never a success."""
    return str(out.get("error") or "the session refused it")


def steer(path, text):
    out, _ = command(path, {"op": "steer", "text": text})
    if not out.get("ok"):
        error = str(out.get("error") or "")
        if IDLE in error:
            raise Refused("idle", "no turn is running to steer: send it instead")
        raise Refused("failed", refusal(out))
    return done({"row": (out.get("result") or {}).get("row")})


def interrupt(path):
    out, _ = command(path, {"op": "interrupt"})
    if not out.get("ok"):
        raise Refused("failed", refusal(out))
    r = out.get("result") or {}
    return done({"turnId": r.get("turnId"), "stopped": list(r.get("stopped") or []),
                 "running": list(r.get("running") or [])})


def bridge_snapshot(path):
    """The first line of the bridge's DX5 stream: its snapshot, which
    carries the child's in-memory `override` as the mod last said it.
    Raises OSError (or ValueError) when it cannot be had."""
    c = bridge._UnixConnection(path, SNAPSHOT_TIMEOUT)
    try:
        c.request("GET", "/events")
        r = c.getresponse()
        if r.status != 200:
            raise OSError("the bridge answered %d" % r.status)
        snap = json.loads(r.readline())
        if not isinstance(snap, dict) or snap.get("type") != "snapshot":
            raise ValueError("the bridge's stream began without a snapshot")
        return snap
    finally:
        c.close()


def model(path, sid, args, lock):
    """The mod replaces model and effort together, so a change naming one
    keeps the other as the session's bridge holds it now: read live from
    the child (its snapshot's `override`, what every writer's `model` event
    left, the owner's `sminos model` included), never from its kept file,
    whose write can fail (DX5). The read and the command are one step per
    session, so two partial changes at once take turns. A live read that
    fails refuses the change; a change naming both reads nothing."""
    with lock:
        body = {"op": "model", "model": args.get("model"), "effort": args.get("effort")}
        if "model" not in args or "effort" not in args:
            try:
                live = bridge_snapshot(path).get("override") or {}
            except (OSError, ValueError, http.client.HTTPException) as e:
                raise Refused("failed", "the model and effort in force could not be read from the session's "
                                        "bridge (%s): name both, or try again" % e)
            for k in ("model", "effort"):
                if k not in args:
                    body[k] = live.get(k)
        out, _ = command(path, body)
        if not out.get("ok"):
            raise Refused("failed", refusal(out))
        r = out.get("result") or {}
        return done({"model": r.get("model"), "effort": r.get("effort")})


def decide(path, rid, body):
    """A pending request's decision, by the member (DX5's decision route):
    taken, or `not-pending` with the bridge's reason (another side won, the
    terminal answered, a background window closed)."""
    try:
        status, out = bridge.request(path, "POST", "/requests/%s/decision" % urllib.parse.quote(rid, safe=""), body,
                                     timeout=DECISION_TIMEOUT)
    except OSError as e:
        raise Refused("failed", "the session's bridge gave no answer: %s" % e)
    out = out if isinstance(out, dict) else {}
    if status == 200:
        return done({})
    if status == 400:
        raise Refused("bad-shape", str(out.get("error")))
    if status in (404, 409, 410):
        s = out.get("settled") if isinstance(out.get("settled"), dict) else None
        raise Refused("not-pending", "already settled: %s by %s" % (s.get("outcome"), s.get("by")) if s
                      else str(out.get("error") or "not pending"), **(who_won(out) if status != 404 else {}))
    raise Refused("failed", "the bridge answered %d: %s" % (status, out.get("error")))


def verb_env(member=None):
    """The daemon's environment for a `sminos` verb, as the operator's: never
    a session's (a CLAUDE_CODE_SESSION_ID would make the verb a member's).
    With `member`, the verb's lifecycle events name the desk member it acts
    for as `by` (composite 21c32db7)."""
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.pop(sminos.DESK_MEMBER_ENV, None)
    if member:
        env[sminos.DESK_MEMBER_ENV] = member
    return env


def run_verb(argv, cwd, timeout, member=None):
    """(exit code, stdout, stderr) of a `sminos` verb."""
    try:
        p = subprocess.run([SMINOS_CLI] + argv, cwd=cwd, env=verb_env(member), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Refused("failed", "sminos %s did not finish within %d s" % (argv[0], timeout))
    return p.returncode, p.stdout, p.stderr


def last_line(text):
    lines = [x for x in (text or "").strip().splitlines() if x.strip()]
    return lines[-1] if lines else ""


def steer_without_bridge(sid, text, root):
    """§5's steer for a live session with no bridge: `sminos steer`'s own
    paths (the supervisor's `reply` for a --bg job, else the inbox frame).
    No row is named (the session appends none of its own)."""
    rc, out, err = run_verb(["steer", "--", sid, text], root, VERB_TIMEOUT)
    if rc == 0:
        m = STEER_ROW_RE.search(out)
        return done({"row": m.group(1) if m else None})
    if rc == sminos.EXIT_UNKNOWN:
        raise Refused("unsupported", last_line(err) or "the session is not live")
    if IDLE in err:
        raise Refused("idle", "no turn is running to steer: send it instead")
    raise Refused("failed", last_line(err) or "sminos steer exited %d" % rc)


def spawn(args, nonce, checkout, member):
    """`sminos spawn` into the checkout, the RPC's nonce stamped on the
    seat's record from its first write, the brief as its in-charge line."""
    alias = alias_for(nonce)
    argv = ["spawn", "--cwd=" + checkout, "--brief=" + args["brief"], "--permission-mode=" + args["permission_mode"],
            "--stamp=rpc_nonce=" + nonce]
    for flag in ("worktree", "model", "effort"):
        if args.get(flag):
            argv.append("--%s=%s" % (flag, args[flag]))
    rc, out, err = run_verb(argv + ["--", alias, SPAWN_TASK], checkout, SPAWN_TIMEOUT, member)
    if rc != 0:
        raise Refused("failed", last_line(err) or "sminos spawn exited %d" % rc)
    found = spawned(nonce)
    if found is not None:
        return found
    m = SEAT_RE.search(out)
    if m and sminos.UUID_RE.match(m.group(1)):
        return done({"session": m.group(1), "alias": alias})
    raise Refused("failed", "sminos spawn named no session: %s" % last_line(out))


def spawned(nonce):
    """The outcome a seat stamped with this nonce stands for, or None when
    there is none yet: no seat, or a provisional one still waiting for the
    harness to name its session (spawn_fresh polls for the uuid after the
    launch). Only a launch spawn_fresh gave up on (`status` error) has
    failed. Seat records are read from their files, no cache."""
    for s in sminos.seats():
        if s.get("rpc_nonce") == nonce:
            if s["current"] and sminos.UUID_RE.match(s["current"]):
                return done({"session": s["current"], "alias": s["alias"]})
            if s["status"] == "error":
                return failed("failed", "the spawn started no session the harness named (seat %s)" % s["seat_id"])
            return None
    return None


def retire(sid, root, member):
    rc, _, err = run_verb(["retire", "--", sid], root, VERB_TIMEOUT, member)
    if rc != 0:
        raise Refused("failed", last_line(err) or "sminos retire exited %d" % rc)
    return done({})


# ------------------------------------------------------------- traces


def steer_row(sid, text_sha, since):
    """The uuid of a user row in the session's transcript whose one text is
    the steer's, written at or after its claim (a little slack for clocks),
    or None."""
    path = sminos.transcript_path(sid)
    if not path:
        return None
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("type") != "user" or not isinstance(row.get("uuid"), str):
            continue
        at = created_at(row.get("timestamp"))
        content = (row.get("message") or {}).get("content")
        texts = [b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text"] \
            if isinstance(content, list) else []
        if at is not None and at >= since - 5 and len(texts) == 1 and isinstance(texts[0], str) \
                and sha256(texts[0]) == text_sha:
            return row["uuid"]
    return None


def trace(nonce, e):
    """(the outcome a claim's trace shows, or None; how long after its claim
    a trace may still appear)."""
    if e.get("rpc") == "spawn":
        return spawned(nonce), SPAWN_TRACE_S
    if e.get("rpc") == "steer" and e.get("session") and e.get("text_sha256"):
        row = steer_row(e["session"], e["text_sha256"], e.get("at", 0))
        return (done({"row": row}) if row else None), STEER_TRACE_S
    return None, 0
