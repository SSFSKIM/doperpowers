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
   daemon.log says when it was created, when the stream's reader took it,
   and its age, so a hold on the way can be told from a late send;
5. the machine's policy (sminos_policy): read-only refuses every RPC
   (`read-only`); a spawn runs only in a known checkout of the project
   (`unknown-checkout`), under a permission mode no looser than the ceiling
   (`above-ceiling`; no mode asked is the ceiling, passed explicitly);
6. the args' shape (`bad-shape`): nothing reaches a command line that could
   be read as a flag;
7. for an answer or a decision, the digest (DX1's `{session, request, tool,
   input_sha256}`) against the request still pending in the session, as its
   bridge reports it (`digest-mismatch`, `not-pending`), a scoped allow's
   rule resolved from that request's own suggestions (`not-pending` when they
   changed, `bad-shape` for one it may not take), and the decision fitting
   that request by the bridge's own rule (`bad-shape`);
8. the session's kind against §5's table (`unsupported`); a Resume, against
   the transcript this machine holds of the session (`unsupported` when it
   holds none: `claude --resume` would start an empty session under its id);
9. for a stop, the task: a background shell or monitor the session's jobs
   index holds as running, the main loop's or a subagent's, read from the
   rows as the plane reads them (sminos_jobs.running_task; `unknown-task`);
   for a stop-agent or a tell, the agent: one the session's subagent tree
   holds as running, by its id, else by the name of exactly one running
   agent (`unknown-agent`; `ambiguous-agent` for a shared name), as the
   bridge's child keeps the tree from the engine's list (GET /agents) and
   the plane is fed it. The id it resolved goes to the bridge, which acts on
   that agent alone.

A refusal from 1 or 2 precedes the ledger and is not kept in it: it goes up
while its project is open on the stream (an `unknown-project` never is, and
is only said in daemon.log). From 3 on, a nonce has one answer, kept.

At most once (DX6): `daemon/rpcs.json` claims the nonce before the RPC has
any effect and records the outcome before the result goes up; entries are
kept a day. Each keeps the RPC's `created` and the time its outcome was kept
(`done_at`) beside its claim's `at` (and a Resume's `launched_at`), so one
RPC's click, claim, launch and end read off its entry. An outcome whose write fails is held here, never sent, and
written again until it is kept. A nonce left claimed (the uplink stopped
between the two writes) is reconciled from the action's own trace — a
spawned seat carries its nonce on its record (`rpc_nonce`); a steer carries
it to the bridge, whose child keeps the mod's answer under it (DX5's kept
file, `rpcs`), since a row's text alone cannot tell this steer from the same
words sent another way — for as long as that trace may still appear, then
answered `failed` `interrupted`.

Execution (§5) goes through the session's bridge (DC2's DX5): steer,
interrupt, stop, model, compact, and a slash command (`command`, the desk
control surface's DX6) as commands; an answer or a decision as the
request's decision, by the member. A steer to a live session without a
bridge takes `sminos steer`'s own fallbacks (the supervisor's `reply`, the
inbox frame), so its result names no row. Spawn and retire run `sminos spawn`
and `sminos retire`, which record `joined` and `retired` as they always do.

Resume runs `claude --bg --resume <session>` in the session's working
directory with nothing else on the line (any flag makes the engine start a
copy), one per session at a time, once no process of this machine holds the
session (`session-live`: its transcript is here, so here is everywhere it
can run; checked before the claim, and again under the lock). The launch
is kept in the claim before it runs, and its job once known: a claim left
by a stop is `done` only when a --bg process of that job holds the session;
one whose job was never kept (`claude --bg` outlives the daemon that ran
it) is `done` when a --bg process started since its launch holds it and no
other Resume of the session, still running then, could have started it,
and `interrupted` once its window passes without one; a kept job the
harness reports under another session is a copy, stopped, the RPC failed
`copy-started`. The engine continues it
under its own id unless it finds the session open meanwhile, when it starts
a copy and says so: the copy is stopped and the RPC fails `copy-started`. The session rejoins as any session
that runs again does (sminos's reconciliation, at the daemon's next tick,
which the Resume asks for at once), and what was recorded for it while it
was closed is delivered then.

A compaction's outcome reaches browsers as DX4 `compact`, carrying the RPC's
nonce, from the bridge's `compact` events for the command this daemon issued
(read by the requests' readers, sminos_requests). The command's id is kept on
the RPC's ledger entry until its compaction ends, so one held for its turn's
end that runs after a restart still carries the nonce. The messages are owed
as a settlement is (sminos_owed): until a POST's answer takes them, kept in
`daemon/rpcs-owed.json` across restarts.

A desk command's outcome reaches browsers the same way, as DX4 `op` (the desk
control surface, §3): the bridge answers the command `queued` at once, and
its run's `run` events — each carrying the RPC's nonce, which the bridge's
child keeps until the run's end — become `op` messages, owed as compactions
are. The command's name and arguments are kept on the claim before it goes
(`op_name`, `op_args`, and for a reload the child that takes it,
`op_child`), and its id once the bridge answered (`op_id`), until the end;
a claim the daemon stopped between the two is reconciled from the child's
kept answer, and its id kept then. So an end the stream did not bring (it
came while the daemon was stopped, or between two of its readers) is read
from the child's kept file, where the end is kept beside the command's
answer. A `/reload-plugins` ends by returned text if its module survives,
otherwise when another child answers (`effect`); neither within
RELOAD_WAIT_S is a timeout. The first end wins, including for `sminos
command`, which carries no nonce and is tracked by its start.
A hub whose welcome does not list `op` is sent none.

One subagent stopped or told (`stop-agent`, `tell`; the desk control
surface's MW4) answers when the bridge has: TaskStop and the engine's send
answer at once, so the result is the outcome and no `op` follows; the
agent's end reaches browsers in the subagent tree. Each carries its nonce to
the bridge, whose child keeps the answer under it, so a claim the daemon
stopped between the two is reconciled from that answer, as a steer's is.

An upload (`media`, the desk control surface's MW5) is saved by this daemon
under the session's live working directory, read from its bridge, without
following a link (sminos_media), and handed to the bridge, which reads each
file into the conversation by a Read of its own; it is answered `queued` only
once the bridge holds it, and its attachments' states follow as `op`, the
upload being the nonce. Its root and files are kept on the claim before
anything is written, so a restart answers it from the child's kept answer.

Checks 1-6 and the ledger's lookup run on the uplink's main thread, which
alone may call sminos (its caches are module globals); the digest, the kind,
the claim, and the execution run on a worker of their own, since a bridge
command waits seconds and a spawn much longer. What a worker finishes is
queued, and the main thread posts it.
"""

import calendar
import collections
import glob
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
import sminos_jobs as jobs  # noqa: E402
import sminos_media as media  # noqa: E402
import sminos_owed as owed  # noqa: E402
import sminos_policy as policy  # noqa: E402

LEDGER_FILE = "rpcs.json"
OWED_FILE = "rpcs-owed.json"  # daemon/: the compaction and op messages not yet the hub's (sminos_owed)
FRESH_S = 60              # an RPC older (or younger) than this by the machine's clock is stale
KEPT_S = 86400            # the ledger keeps an entry a day
LOOSE_S = 600             # a refusal kept out of the ledger waits this long for its project to open
STEER_TRACE_S = 30        # a claimed steer's answer is looked for this long after its claim
SPAWN_TRACE_S = 420       # a claimed spawn's seat: `claude --bg` may take 300 s, its uuid poll more
RESUME_TRACE_S = 420      # a claimed Resume's job: the same launch and poll
RESUME_HELD_S = 30        # how long a Resume waits for its job's process to hold the session
LAUNCH_TIMEOUT = 300      # `claude --bg` hands the launch to the harness's supervisor
COMPACT_HELD_S = 60       # a `compact` event waits at most this long for its command's result to name it
RELOAD_WAIT_S = 60        # a `/reload-plugins` is done once its bridge answers from another child within this
OPS_ENDED_KEPT = 1000     # nonces of ops whose end went up, kept so another copy of that end is passed by
NAME_MAX = 128            # DX6 `command`: a name as $.command.list() spells it
ARGS_MAX = 4096           # and its arguments' text
PROMPT_MAX = 8192         # DX6 `btw`: a side question's text
INSTRUCTIONS_MAX = 4096   # DX6 `compact`: its instructions' text
AGENT_MAX = 128           # DX6 `stop-agent`, `tell`: an agent's id or name (a name may hold a space)
SCOPE_DESTINATIONS = ("session", "localSettings")   # DX6 `decide.scope` (§11): nothing saved, or the checkout's own
SCOPED_TYPES = ("addRules", "addDirectories")        # the suggestions a scoped allow takes (MW3)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
RELOAD = "reload-plugins"
RECONCILE_EVERY = 1.0     # how often claims left by a stop are looked at again
SPAWN_TIMEOUT = 600
VERB_TIMEOUT = 120
SNAPSHOT_TIMEOUT = 8      # the bridge holds its stream up to 5 s until the mod's first resync
DECISION_TIMEOUT = 15     # an async question's answer is relayed to the mod, which waits 5 s
SPAWN_TASK = "Begin with your brief."
RPC_NAMES = ("steer", "interrupt", "answer", "decide", "model", "compact", "spawn", "retire", "resume", "stop",
             "command", "btw", "stop-agent", "tell", "media")
TASK_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")   # DX6 `stop`'s taskId, as the engine spells task ids
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
OP_OF = {"run": "command", "btw": "btw", "media": "media"}  # a bridge's event → the DX4 `op` it reports
EVENT_OF = {op: event for event, op in OP_OF.items()}  # an op (the RPC that issued it) → the bridge's event of it
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,199}")
WORKTREE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
CREATED_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]{1,9})?Z")
SEAT_RE = re.compile(r"\[[0-9a-f]+ / ([0-9a-f-]{36})\]")
STEER_ROW_RE = re.compile(r"\(row ([0-9a-f-]{36})\)")
BG_SHORT_RE = re.compile(r"backgrounded · ([0-9a-f]+)")
COPY_RE = re.compile(r"started a copy as ([0-9a-f]+)")
IDLE = "no turn is running"   # the mod's steer refusal (DX5): "no turn is running to steer: send it instead"
# A verb runs on the daemon's own Python, as its derivation and its uplink do:
# the launcher would take the first python3 on the service's PATH, which the
# install did not pin (sminos_daemon.interpreter).
SMINOS_CLI = [sys.executable, os.path.join(os.path.dirname(os.path.realpath(__file__)), "sminos.py")]


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


def created_of(rpc):
    """{"created": epoch s} of the RPC's own `created`, for its ledger
    entry; {} when it does not parse."""
    at = created_at(rpc.get("created"))
    return {} if at is None else {"created": at}


def stamp(epoch):
    """An epoch time as the hub writes `created` (UTC, milliseconds)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + ".%03dZ" % int(epoch % 1 * 1000)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def alias_for(nonce):
    """A spawned seat's alias: where it came from, and its nonce's, so a
    second launch under one nonce could only collide with the first."""
    return "web-" + sha256(nonce)[:6]


# ------------------------------------------------------------- the ledger


class Ledger:
    """`daemon/rpcs.json`: nonce → {project, rpc, session, created?, at,
    launched_at?, job?, compact_id?, outcome?, done_at?, acked?}: `created`
    is the RPC's own (epoch s, when it parses), `at` its claim, `done_at`
    when its outcome was kept. An entry without `outcome` is a claim. Written whole at every change, under a lock (the main thread and
    the workers write); entries older than KEPT_S go at every write. A
    change whose write fails is not kept in memory either: what is here is
    what the file holds.

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
        """Raises OSError when the entry could not be written."""
        with self.lock:
            self.change(nonce, entry)

    def change(self, nonce, entry):
        """The nonce's entry replaced and written, or, when the write fails,
        left as it was (OSError raised). The caller holds the lock."""
        before = self.entries.get(nonce)
        self.entries[nonce] = entry
        try:
            self.save()
        except OSError:
            if before is None:
                self.entries.pop(nonce, None)
            else:
                self.entries[nonce] = before
            raise

    def answer(self, nonce, outcome):
        """The outcome kept. Raises OSError when it could not be written:
        the claim stays as it was, so nothing can send the outcome, which the
        caller holds to write again (a restart reconciles the claim)."""
        with self.lock:
            e = self.entries.get(nonce)
            now = self.clock()
            self.change(nonce, {**(e if e is not None else {"at": now}), "outcome": outcome, "done_at": now,
                                "acked": False})

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
        self.resume_locks = {}    # session → the lock a Resume of it runs under
        self.locks_lock = threading.Lock()
        self.op_ids = {}          # a bridge's command id → the op this daemon issued ({project, session, nonce, at,
        #                           name, args, child}), until its end
        self.ops_ended = collections.OrderedDict()   # (session, id) → None: ended ops, including CLI runs without a nonce
        self.kinds = frozenset()  # the session kinds the stream's welcome listed (DX2): `op` goes only where listed
        self.flying = {}          # id(frame) → frame: compact and op messages on a lane, their POST not yet answered
        self.kept = owed.Kept(OWED_FILE, log)
        self.messages = [f for f in self.kept.load() if is_owed(f)]   # DX4 compact and op messages owed, as frames
        self.unwritten = {}       # nonce → its outcome, whose ledger write failed: never sent until it is kept
        self.copies_asked = set()  # claimed Resumes whose kept job the harness was asked about (check_copy)
        self.next_reconcile = 0.0
        self.restore_compacts()
        self.restore_ops()
        self.reconcile()

    # ---------------------------------------------------- frames down

    def receive(self, rpc, here, received=None):
        """An `rpc` frame's RPC, on the main thread: checks 1-6, then a
        worker for the rest. `here` is what the uplink knows of this machine
        (project, has_session, record, checkouts); `received`, when the
        stream's reader took the frame (epoch s; now when not given)."""
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
            self.admit(rpc, project, args, here, self.clock() if received is None else received)
        except Refused as r:
            self.keep(rpc, r.outcome)
            return
        record = here.record(sid) if sid else None
        facts = {"running": record is not None, "bg": control.bg_job(record or {}), "root": project.root,
                 "checkout": args.get("checkout"), "status": (record or {}).get("status")}
        if name in ("stop", "resume"):
            facts["transcript"] = sminos.transcript_now(sid)
        if name == "resume":
            seat = next((s for s in sminos.seats() if s["current"] == sid), None)
            facts.update(cwd=here.cwd(project, sid),
                         retired_seat=seat["alias"] if seat and seat["status"] == "retired" else None)
        self.flight.add(nonce)
        if name == "compact":
            self.compact_flight[nonce] = sid
        threading.Thread(target=self.run, args=(rpc, facts), name="rpc-" + name, daemon=True).start()

    def admit(self, rpc, project, args, here, received):
        """Checks 4-6: freshness, the policy, the args' shape. Refused, or
        nothing; a spawn's `permission_mode` is set to what it runs under."""
        at, now = created_at(rpc.get("created")), self.clock()
        if at is None or abs(now - at) > FRESH_S:
            raise Refused("stale", "created %s, received %s, %s old when checked: more than %d s from this "
                          "machine's clock" % (rpc.get("created"), stamp(received),
                                               "%.3f s" % (now - at) if at is not None else "of no known age",
                                               FRESH_S))
        p = policy.load()
        if p["read_only"]:
            raise Refused("read-only", "this machine is read-only: it runs no RPC")
        name = rpc["rpc"]
        if name == "spawn":
            admit_spawn(args, p["ceiling"], here.checkouts(project))
        shape(name, args, rpc.get("member"))
        if name == "command" and args["name"] == "cd":
            # Resolve no relative path against the daemon's cwd (nor a stale
            # joined cwd): only a literal absolute checkout is unambiguous.
            target = (args.get("args") or "").strip()  # shape admits absent/null optional args
            reason = "cd needs the absolute path of a known checkout of this project"
            if not os.path.isabs(target):
                raise Refused("unknown-checkout", reason)
            try:
                target = os.path.realpath(target)
                known = {os.path.realpath(c["path"]) for c in here.checkouts(project)}
            except (ValueError, UnicodeError, OSError) as error:
                raise Refused("unknown-checkout", reason) from error
            if target not in known:
                raise Refused("unknown-checkout", reason)
            args["args"] = target

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
        now = self.clock()
        e = {"project": rpc["project"], "rpc": rpc["rpc"], "session": rpc["args"].get("session"),
             **created_of(rpc), "at": now, "outcome": outcome, "done_at": now, "acked": False}
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
            except Exception as e:  # noqa: BLE001 — a check that broke is a refusal, said: nothing ran
                self.keep(rpc, failed("failed", "%s: %s (nothing ran)" % (type(e).__name__, e)))
                return
            claim = {"project": rpc["project"], "rpc": rpc["rpc"], "session": rpc["args"].get("session"),
                     **created_of(rpc), "at": self.clock()}
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
            self.record(nonce, outcome)
            if outcome["state"] == "failed":
                log("%s %s failed %s: %s" % (rpc["rpc"], nonce, outcome["error"]["code"], outcome["error"]["message"]))
        finally:
            self.finished.put(("done", nonce))
            self.wake()

    def record(self, nonce, outcome):
        """A worker's outcome, kept in the ledger before anything may send
        it. One whose write fails is handed to the main thread, which writes
        it again until it is kept (reconcile); until then it is sent nowhere."""
        try:
            self.ledger.answer(nonce, outcome)
        except OSError as err:
            log("the outcome of %s could not be kept in %s (%s): it is sent once it is kept"
                % (nonce, self.ledger.path, err))
            self.finished.put(("unwritten", (nonce, outcome)))

    def plan(self, rpc, facts):
        """The action an RPC runs once claimed, or Refused (checks 7-8)."""
        name, args, nonce = rpc["rpc"], rpc["args"], rpc["nonce"]
        if name == "spawn":
            return lambda: spawn(args, nonce, facts["checkout"], rpc["member"])
        sid = args["session"]
        if name == "resume":
            if facts["retired_seat"]:
                # A retired seat's session would run outside the family:
                # sminos re-joins a retired seat only through its own verbs.
                raise Refused("unsupported", "the seat %s holding it was retired: `sminos fill` or `sminos send` "
                                             "brings it back" % facts["retired_seat"])
            live = holders(sid)
            if live:
                raise Refused("session-live", "the session is running here (%s): only an ended session is resumed"
                              % held_by(live))
            if not facts["transcript"]:
                # A --bg copy that ended before it wrote a row leaves none;
                # `claude --resume` would start an empty session under its id.
                raise Refused("unsupported", "this machine holds no transcript of it, so there is nothing to resume")
            return lambda: resume(sid, facts["cwd"], self.lock_of(self.resume_locks, sid),
                                  lambda **fields: self.note(nonce, fields))
        path = bridge.endpoint(sid)
        status = bridge.probe(path)
        bridged = status is not None and status.get("session") == sid
        if name == "answer":
            decision = {"behavior": "allow", "updatedInput": {"answers": args["answers"]}, "by": rpc["member"]}
        elif name == "decide":
            decision = {"behavior": args["decision"], "by": rpc["member"]}
            if "message" in args:
                decision["message"] = args["message"]
        if name in ("answer", "decide") and bridged:
            check_digest(path, sid, args["digest"], decision, args.get("scope") if name == "decide" else None)
        if name == "retire":
            return lambda: retire(sid, facts["root"], rpc["member"])
        if not facts["running"]:
            raise Refused("unsupported", "the session is not running: only Resume brings it back")
        if bridged:
            if name == "steer":
                return lambda: steer(path, args["text"], nonce)
            if name == "interrupt":
                return lambda: interrupt(path)
            if name == "model":
                return lambda: model(path, sid, args, self.lock_of(self.model_locks, sid))
            if name == "compact":
                return lambda: self.compact(path, rpc, sid)
            if name == "command":
                return lambda: self.desk_command(path, rpc, sid, status)
            if name == "btw":
                return lambda: self.side_question(path, rpc, sid)
            if name == "media":
                return lambda: self.media(path, rpc, sid)
            if name in ("answer", "decide"):
                return lambda: decide(path, args["digest"]["request"], decision)
            if name in ("stop-agent", "tell"):
                agent = resolve_agent(path, args["agentId"])
                if name == "stop-agent":
                    return lambda: stop_agent(path, args["agentId"], agent, nonce)
                return lambda: tell(path, args["agentId"], agent, args["text"], nonce)
            if name == "stop":
                if not jobs.running_task(facts["transcript"], args["taskId"]):
                    raise Refused("unknown-task", "the session's jobs hold no background shell or monitor %s running"
                                  % args["taskId"])
                return lambda: stop(path, args["taskId"])
        if name == "steer":
            if facts["status"] == "idle":
                # The engine's own record says no turn runs (composite 21c32db7).
                raise Refused("idle", "no turn is running to steer: send it instead")
            return lambda: steer_without_bridge(sid, args["text"], facts["root"])
        raise Refused("unsupported", "%s needs the session's bridge; %s has none (§5)" % (
            name, "this --bg job" if facts["bg"] else "this terminal session"))

    def note(self, nonce, fields):
        """The action's own evidence added to its claim before the effect it
        names (a Resume's launch, then its job), so a restart can tell that
        launch's trace from anything else. Raises OSError when it could not
        be kept."""
        with self.ledger.lock:
            e = self.ledger.entries.get(nonce)
            if e is None or "outcome" in e:
                return
            self.ledger.change(nonce, {**e, **fields})

    def lock_of(self, locks, sid):
        """The session's lock in `locks` (one RPC kind's)."""
        with self.locks_lock:
            return locks.setdefault(sid, threading.Lock())

    def compact(self, path, rpc, sid):
        instructions = rpc["args"].get("instructions")
        result, cid = command(path, {"op": "compact", **({"instructions": instructions} if instructions else {})})
        if not result["ok"]:
            raise Refused("failed", refusal(result))
        if cid:
            # Kept on the claim as well: a compaction held for its turn's end
            # may run after a restart, and still carries this nonce.
            try:
                self.note(rpc["nonce"], {"compact_id": cid})
            except OSError as e:
                log("compact %s: its command %s could not be kept in the ledger (%s): a restart before it "
                    "ends relays it unnamed" % (rpc["nonce"], cid, e))
            self.finished.put(("compact", (cid, rpc["project"], sid, rpc["nonce"])))
        r = result.get("result") or {}
        return done({"at": "turn-end" if r.get("queued") else "now"})

    def desk_command(self, path, rpc, sid, status):
        """A slash command run in the session by its bridge (DX5 `command`),
        which routes it and answers at once; its run's outcome follows on the
        stream (`ops`). The bridge's refusal is the RPC's failure, its code
        the message's first word. Its id is kept on the claim until its end;
        a `/reload-plugins` also keeps the child that answered before it, by
        whose replacement it is done (`effects`)."""
        args, nonce = rpc["args"], rpc["nonce"]
        name, text = args["name"], args.get("args") or ""
        child = None
        if name == RELOAD:
            try:
                child = [os.stat(path).st_ino, status.get("pid")]
            except OSError:
                pass
        try:
            # Before it goes: a restart that finds the claim answered by the
            # child knows what ran, and which child a reload replaces.
            self.note(nonce, {"op_name": name, "op_args": text, **({"op_child": child} if child else {})})
        except OSError as e:
            log("command %s: what it runs could not be kept in the ledger (%s)" % (nonce, e))
        out, cid = command(path, {"op": "command", "name": name, "args": text, "rpc": nonce, "from": "desk"})
        outcome = commanded(out)
        if outcome["state"] != "done":
            self.forget(nonce, ("op_name", "op_args", "op_child"), "command")   # nothing ran: nothing follows
            return outcome
        oid = outcome["result"]["id"] or cid
        try:
            self.note(nonce, {"op_id": oid})
        except OSError as e:
            log("command %s: its id %s could not be kept in the ledger (%s): an end a restart misses is not "
                "sent" % (nonce, oid, e))
        self.finished.put(("op", (oid, rpc["project"], sid, nonce, name, text, child, "command")))
        return done({**outcome["result"], "id": oid})

    def side_question(self, path, rpc, sid):
        """A side question asked of the session's bridge (DX5 `btw`), which
        answers `started` at once; its answer follows on the stream (`ops`),
        as a desk command's run does. The bridge's refusal is the RPC's
        failure, its code the message's first word. Its id is kept on the
        claim until its end."""
        nonce = rpc["nonce"]
        out, cid = command(path, {"op": "btw", "prompt": rpc["args"]["prompt"], "rpc": nonce})
        outcome = started(out)
        if outcome["state"] != "done":
            return outcome
        oid = outcome["result"]["id"] or cid
        try:
            self.note(nonce, {"op_id": oid})
        except OSError as e:
            log("btw %s: its id %s could not be kept in the ledger (%s): an end a restart misses is not sent"
                % (nonce, oid, e))
        self.finished.put(("op", (oid, rpc["project"], sid, nonce, None, "", None, "btw")))
        return done({"started": True, "id": oid})

    def media(self, path, rpc, sid):
        """An upload (DX6 `media`, the desk control surface's MW5): saved under
        the session's live working directory, read from its bridge now
        (`/cd` moves it), without following a link (sminos_media), then handed
        to the bridge, which reads each file into the conversation by a Read
        of its own. Answered `queued` only once the bridge holds the upload
        (a duplicate is held); a refusal removes the files saved for it. The
        upload is the nonce: its root and files are kept on the claim before
        anything is written, so a restart answers from the child's kept
        answer, and its states follow on the stream as `op` (`ops`)."""
        args, nonce = rpc["args"], rpc["nonce"]
        out, _ = command(path, {"op": "read", "what": "status"})
        cwd = (out.get("result") or {}).get("cwd") if out.get("ok") else None
        if not (isinstance(cwd, str) and os.path.isabs(cwd)):
            raise Refused("failed", "the session did not say where it works: %s" % (out.get("error") or cwd))
        base = os.path.realpath(cwd)
        root = media.root_of(base, sid)
        names = [media.file_name(nonce, n, a["mediaType"]) for n, a in enumerate(args["attachments"])]
        kept = {"media_root": root, "media_paths": names}
        try:
            self.note(nonce, kept)
        except OSError as e:
            raise Refused("failed", "the upload could not be kept in the ledger (%s): nothing was saved" % e)
        try:
            media.save(base, sid, nonce, args["attachments"])   # rolls back what it made its own
        except (media.Unsafe, OSError) as e:
            raise Refused("failed", "the upload was not saved: %s" % e)
        try:
            media.exclude(base)
        except (media.Unsafe, OSError, subprocess.SubprocessError) as e:
            log("media %s: %s was not excluded from git (%s)" % (nonce, root, e))
        files = [{"n": n, "path": os.path.join(root, name), "name": a["name"], "mediaType": a["mediaType"]}
                 for n, (name, a) in enumerate(zip(names, args["attachments"]))]
        out, _ = command(path, {"op": "media", "upload": nonce, "root": root, "files": files, "rpc": nonce})
        outcome = media_held(out, kept)
        if outcome["state"] != "done":
            media.remove(root, names)
            return outcome
        try:
            self.note(nonce, {"op_id": nonce})
        except OSError as e:
            log("media %s: its upload could not be kept in the ledger (%s): an end a restart misses is not sent"
                % (nonce, e))
        self.finished.put(("op", (nonce, rpc["project"], sid, nonce, None, "", None, "media")))
        return outcome

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
            elif kind == "unwritten":
                nonce, outcome = data
                self.unwritten[nonce] = outcome
            elif kind == "compact":
                cid, pid, sid, nonce = data
                self.compact_ids[cid] = (pid, sid, nonce, self.clock())
            elif kind == "op":
                oid, pid, sid, nonce, name, text, child, op = data
                self.op_ids[oid] = {"project": pid, "session": sid, "nonce": nonce, "at": self.clock(), "name": name,
                                    "args": text, "child": child, "op": op}

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
            self.owe(named[0] if named else pid, named[1] if named else sid, "compact", body)
            if e.get("phase") == "end" and self.compact_ids.pop(cid, None) is not None:
                self.forget_compact(named[2])
        self.compact_ids = {c: v for c, v in self.compact_ids.items() if now - v[3] < KEPT_S}

    def restore_compacts(self):
        """The compact commands this daemon issued whose compaction has not
        ended, as their claims keep them (`compact_id`): what a restart
        relays under their nonce."""
        for nonce, e in self.ledger.items():
            cid = e.get("compact_id")
            if isinstance(cid, str) and cid and isinstance(e.get("at"), (int, float)):
                self.compact_ids[cid] = (e.get("project"), e.get("session"), nonce, e["at"])

    def forget_compact(self, nonce):
        """A compaction ended: its command is no longer kept on the claim."""
        self.forget(nonce, ("compact_id",), "compact")

    def forget(self, nonce, fields, what):
        """`fields` of a claim no longer kept: what they named has ended."""
        with self.ledger.lock:
            e = self.ledger.entries.get(nonce)
            if e is None or not any(f in e for f in fields):
                return
            for f in fields:
                e.pop(f, None)
            try:
                self.ledger.save()
            except OSError as err:
                log("the ledger could not be written (%s): %s %s's command is kept until the entry goes"
                    % (err, what, nonce))

    def owe(self, pid, sid, kind, body):
        """A DX4 session-wide message, owed until the hub takes it."""
        self.messages.append({"t": "session", "message": {
            "project": pid, "machine": self.machine, "session": sid, "kind": kind, "sub": None, "n": None,
            "body": body}})
        self.kept.save(self.messages)

    def ops(self, items):
        """The bridges' `run` and `btw` events (session, project id, event):
        each run of a desk command, and each side question, becomes DX4 `op`
        (the desk control surface, §3), carrying the nonce of the DX6
        `command` or `btw` that asked for it — the event's own (the bridge's
        child names it), else the one this daemon kept for it — or null for
        one nobody here asked for."""
        self.take()
        for sid, pid, e in items:
            if isinstance(e, dict) and pid and e.get("type") in OP_OF:
                self.op_event(sid, pid, e)

    def op_event(self, sid, pid, e, ended_by=None):
        oid = e.get("id")
        key = (sid, oid)
        if key in self.ops_ended:
            return   # an end already won: neither a late end nor a replayed start re-arms it
        held = self.op_ids.get(oid)
        nonce = e.get("rpc") if isinstance(e.get("rpc"), str) else held["nonce"] if held else None
        child = e.get("child") if isinstance(e.get("child"), list) else None
        if e.get("phase") == "start" and e.get("name") == RELOAD and isinstance(oid, str):
            # A reload can be finished by its effect, whoever sent it (`sminos
            # command` sends no nonce): tracked from its start, which names
            # the child it replaces.
            if held is None:
                held = self.op_ids[oid] = {"project": pid, "session": sid, "nonce": nonce, "at": self.clock(),
                                           "name": RELOAD, "args": e.get("args") or "", "child": child, "op": "command"}
            elif held["child"] is None:
                held["child"] = child
        body = {"rpc": nonce, "op": OP_OF[e["type"]], **{k: v for k, v in e.items() if k not in ("type", "rpc", "n")}}
        self.owe(held["project"] if held else pid, held["session"] if held else sid, "op", body)
        if e.get("phase") == "end":
            if self.op_ids.pop(oid, None) is not None:
                self.forget(nonce, ("op_id", "op_name", "op_args", "op_child"), OP_OF[e["type"]])
            self.ops_ended[key] = None
            while len(self.ops_ended) > OPS_ENDED_KEPT:
                self.ops_ended.popitem(last=False)
            if e.get("name") == RELOAD:
                how = ended_by or (e.get("readback") or {}).get("how", "none")
                log("reload-plugins end id=%s session=%s how=%s ok=%s" %
                    (oid, sid, how, (e.get("settled") or {}).get("ok")))

    def effects(self, answering):
        """The ops this daemon finishes itself, by their effect: a
        `/reload-plugins` reloads the bridge mod, whose successor says nothing
        of the run (§2), so it is done once `answering(session)` — the child
        the plane's probe last found answering, (socket inode, pid), that
        probe's number, and how many have begun — is another than the one that
        took it; failed when none has by RELOAD_WAIT_S after its claim. Only a
        probe begun after the op was first looked at here counts: the plane
        may still hold a child that was replaced before the reload was sent."""
        now = self.clock()
        for oid, op in list(self.op_ids.items()):
            if op["name"] != RELOAD:
                continue
            child, probe, begun = answering(op["session"])
            if "probes" not in op:
                op["probes"] = begun   # the probes begun when it was first looked at: none of them counts
            if child is not None and probe > op["probes"] and op["child"] is not None \
                    and list(child) != list(op["child"]):
                end = {"settled": {"ok": True}, "readback": {"how": "effect"}}
            elif now - op["at"] >= RELOAD_WAIT_S:
                end = {"settled": {"ok": False, "error": "the session's bridge did not answer from a reloaded "
                                                         "module within %d s" % RELOAD_WAIT_S},
                       "readback": {"how": "none"}}
            else:
                continue
            self.op_event(op["session"], op["project"], {"type": "run", "phase": "end", "id": oid, "rpc": op["nonce"],
                                                         "name": op["name"], "args": op["args"], **end,
                                                         "t": int(now * 1000)},
                          ended_by="effect" if end["settled"]["ok"] else "timeout")

    def recover_ops(self):
        """The ends of ops this daemon issued that no stream brought (they
        came while it was stopped, or between two of a bridge's readers),
        read from the bridge's kept file, where its child keeps a run's end
        beside the command's answer — a reload's too, when the module that
        took it survived or the engine refused it. A replaced module leaves no
        end, so its reload is finished by its effect (`effects`)."""
        for oid, op in list(self.op_ids.items()):
            if not op["session"] or op["nonce"] is None:
                continue
            end = ((bridge.load_kept(op["session"]).get("rpcs") or {}).get(op["nonce"]) or {}).get("end")
            if isinstance(end, dict) and end.get("id") == oid and end.get("phase") == "end":
                self.op_event(op["session"], op["project"], {**end, "type": EVENT_OF[op["op"]], "rpc": op["nonce"]})
        now = self.clock()
        for oid in [o for o, op in self.op_ids.items() if now - op["at"] >= KEPT_S]:
            del self.op_ids[oid]

    def rearm(self, nonce):
        """A command or side question claim about to be reconciled `done`
        from the child's kept answer (the daemon stopped after the bridge
        answered it and before its id was kept): its id kept on the claim
        first, while the claim is still open, so that a stop before its
        outcome is written leaves a claim the next restart reconciles again;
        then its outcome followed as one this daemon saw answered — its end, if the child
        kept it meanwhile, sent at once (recover_ops). False when the id
        could not be kept: the claim stays open, reconciled again."""
        with self.ledger.lock:
            e = self.ledger.entries.get(nonce)
            if e is None or not e.get("session"):
                return True
            answered = (bridge.load_kept(e["session"]).get("rpcs") or {}).get(nonce) or {}
            oid = (answered.get("result") or {}).get("upload" if e.get("rpc") == "media" else "id")
            if not isinstance(oid, str) or not oid:
                return True
            end = answered["end"] if isinstance(answered.get("end"), dict) else {}
            e = {**e, "op_id": oid, "op_name": e.get("op_name") or end.get("name"),
                 "op_args": e["op_args"] if "op_args" in e else end.get("args") or ""}
            try:
                self.ledger.change(nonce, e)
            except OSError as err:
                log("command %s, claimed before a stop: its id %s could not be kept (%s): it is reconciled again"
                    % (nonce, oid, err))
                return False
        child = e.get("op_child")
        self.op_ids[oid] = {"project": e.get("project"), "session": e["session"], "nonce": nonce, "at": e["at"],
                            "name": e["op_name"], "args": e["op_args"], "child": child if isinstance(child, list) else None,
                            "op": e["rpc"]}
        return True

    def restore_ops(self):
        """The commands this daemon issued whose end has not gone up, as
        their claims keep them (`op_id`): what a restart relays under their
        nonce, and finishes by effect."""
        for nonce, e in self.ledger.items():
            oid = e.get("op_id")
            if isinstance(oid, str) and oid and isinstance(e.get("at"), (int, float)):
                child = e.get("op_child")
                self.op_ids[oid] = {"project": e.get("project"), "session": e.get("session"), "nonce": nonce,
                                    "at": e["at"], "name": e.get("op_name"), "args": e.get("op_args") or "",
                                    "child": child if isinstance(child, list) else None,
                                    "op": e.get("rpc") if e.get("rpc") in EVENT_OF else "command"}

    def reconcile(self):
        """Outcomes whose ledger write failed, written again; then claims no
        worker holds: answered from their trace, or `interrupted` once no
        trace can come any more (main thread: it reads the seats and the
        bridges' kept files); a command so answered has its id kept before
        its outcome and is followed to its end (rearm, recover_ops). A claimed Resume whose job is kept, and does
        not hold the session, has the harness asked once, on a worker,
        whether that job is a copy (check_copy)."""
        now = self.clock()
        self.next_reconcile = now + RECONCILE_EVERY
        for nonce, outcome in list(self.unwritten.items()):
            try:
                self.ledger.answer(nonce, outcome)
            except OSError:
                continue
            del self.unwritten[nonce]
            log("the outcome of %s is kept now: it is sent" % nonce)
        claims = self.ledger.items()
        for nonce, e in claims:
            if "outcome" in e or nonce in self.flight or nonce in self.unwritten:
                continue
            outcome, window = trace(nonce, e, [x for n, x in claims if n != nonce])
            if outcome is None and kept_job(e) and nonce not in self.copies_asked:
                self.copies_asked.add(nonce)
                self.flight.add(nonce)
                threading.Thread(target=self.check_copy, args=(nonce, e), name="rpc-resume-copy",
                                 daemon=True).start()
                continue
            if outcome is None and window and now - e.get("at", 0) < window:
                continue
            if outcome is None:
                outcome = failed("interrupted", "the daemon stopped while it ran: it is not run again")
            if e.get("rpc") == "media" and outcome["state"] == "failed" and isinstance(e.get("media_root"), str) and \
                    ((bridge.load_kept(e["session"]).get("rpcs") or {}).get(nonce) or {}).get("ok") is False:
                media.remove(e["media_root"], e["media_paths"])   # the bridge refused it: its files go
            if e.get("rpc") in EVENT_OF and outcome["state"] == "done" and not self.rearm(nonce):
                continue
            try:
                self.ledger.answer(nonce, outcome)
            except OSError as err:
                log("%s %s, claimed before a stop, reconciled %s, could not be kept (%s): it is sent once it is"
                    % (e.get("rpc"), nonce, outcome["state"], err))
                self.unwritten[nonce] = outcome
                continue
            log("%s %s, claimed before a stop, reconciled: %s" % (e.get("rpc"), nonce, outcome["state"]))
        self.recover_ops()

    def check_copy(self, nonce, e):
        """A claimed Resume's kept job, asked of the harness (a worker: it
        polls `claude agents`): a job it reports under another session is a
        copy the engine started, stopped now, the RPC failed `copy-started`.
        Any other answer leaves the claim to its trace."""
        try:
            reported = job_session(e["job"])
            if reported is not None and reported != e["session"]:
                self.record(nonce, copy_started(e["job"], sminos.claude_stop(e["job"])))
                log("resume %s, claimed before a stop: its job %s is a copy (%s)" % (nonce, e["job"], reported))
        finally:
            self.finished.put(("done", nonce))
            self.wake()

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
        results, then DX4 compact and op messages. Not taken until
        `sending`. An op message a hub that does not list `op` would refuse
        is dropped here, said."""
        self.take()
        if self.clock() >= self.next_reconcile:
            self.reconcile()
        if "op" not in self.kinds:
            unlisted = [f for f in self.messages if f["message"]["kind"] == "op"]
            if unlisted:
                log("the hub lists no `op` messages: %d of them dropped" % len(unlisted))
                self.messages = [f for f in self.messages if f["message"]["kind"] != "op"]
                self.kept.save(self.messages)
        owed_now = [f for f in self.messages if f["message"]["project"] in opened and id(f) not in self.flying]
        return self.results(set(opened), False) + owed_now

    def opening(self, pid):
        """What follows a project's `hello` on a new stream: every result of
        it the hub has not acknowledged (DX2)."""
        self.take()
        return self.results({pid}, True)

    def sending(self, frames):
        """`frames` were queued on a lane. A result is taken as sent on this
        stream now (every connect sends it again until `rpc-ack`, and so does
        every re-open); a compact or op message, which nothing rebuilds, is in
        flight until `delivered`, `unsent`, or the next stream's `reset`."""
        for f in frames:
            if f.get("t") == "rpc-result":
                self.sent_here.add(f["nonce"])
            else:
                self.flying[id(f)] = f

    def delivered(self, frames, refused):
        """The POST carrying `frames` was answered 200, `refused` naming
        ({id(frame): reason}) those the hub refused whole: a compact or op
        message it took leaves `messages`; one refused `not-open` stays owed (its
        project is opened again), and a result so refused goes again; one
        refused otherwise would be refused again, and leaves, said."""
        took = set()
        for f in frames:
            reason = refused.get(id(f))
            if f.get("t") == "rpc-result":
                if reason == "not-open":
                    self.sent_here.discard(f["nonce"])
            elif self.flying.pop(id(f), None) is not None and reason != "not-open":
                took.add(id(f))
                if reason is not None:
                    log("the hub refused a %s message of %s (%s): not sent again" % (
                        f["message"]["kind"], f["message"]["session"], reason))
        if took:
            self.messages = [f for f in self.messages if id(f) not in took]
            self.kept.save(self.messages)

    def unsent(self, frames):
        """Frames dropped from a lane before any POST carried them (a
        re-open's `hold`): no longer in flight, owed as they stand."""
        for f in frames:
            if f.get("t") == "rpc-result":
                self.sent_here.discard(f["nonce"])
            else:
                self.flying.pop(id(f), None)

    def sent(self, frames):
        """`frames` reached the hub (queued and answered at once)."""
        self.sending(frames)
        self.delivered(frames, {})

    def reset(self):
        """A new stream: nothing is taken as sent on it yet, and what was in
        flight on the last one is owed as it stands."""
        self.sent_here.clear()
        self.flying.clear()


def is_owed(frame):
    """Whether a kept item is a DX4 compact or op message as `owe` makes it."""
    m = frame.get("message") if isinstance(frame, dict) else None
    return isinstance(m, dict) and frame.get("t") == "session" and m.get("kind") in ("compact", "op") \
        and isinstance(m.get("project"), str) and isinstance(m.get("body"), dict)


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


def is_agent(ref):
    return is_text(ref) and len(ref) <= AGENT_MAX and not CONTROL_RE.search(ref)


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
            if "scope" in args:
                sc = args["scope"]
                need(args["decision"] == "allow", "a scope goes with an allow")
                need(isinstance(sc, dict) and type(sc.get("suggestion")) is int and sc["suggestion"] >= 0,
                     "scope.suggestion is the index of one of the request's suggestions")
                need(isinstance(sc.get("sha256"), str) and SHA256_RE.fullmatch(sc["sha256"]),
                     "scope.sha256 is the lowercase hex SHA-256 of that suggestion's canonical JSON")
                need(sc.get("destination") in SCOPE_DESTINATIONS,
                     "scope.destination is session or localSettings: the terminal changes any other settings")
    elif name == "model":
        m, e = args.get("model"), args.get("effort")
        need(m is not None or e is not None, "a model, an effort, or both")
        need(m is None or (isinstance(m, str) and MODEL_RE.fullmatch(m)), "model is an id, an alias, or default")
        need(e is None or e in control.EFFORTS, "effort is one of %s" % ", ".join(control.EFFORTS))
    elif name == "stop":
        need(isinstance(args.get("taskId"), str) and TASK_RE.fullmatch(args["taskId"]),
             "taskId is a background task's id")
    elif name in ("stop-agent", "tell"):
        need(is_agent(args.get("agentId")), "agentId is an agent's id or name: 1-%d characters, not blank, none a "
                                            "control" % AGENT_MAX)
        if name == "tell":
            need(is_text(args.get("text")), "text is the message's text")
    elif name == "command":
        n, a = args.get("name"), args.get("args")
        need(isinstance(n, str) and 1 <= len(n) <= NAME_MAX and not CONTROL_RE.search(n),
             "name is a command's name as the session lists it (1-%d characters, none a control)" % NAME_MAX)
        need(a is None or (isinstance(a, str) and len(a) <= ARGS_MAX),
             "args is text of at most %d characters" % ARGS_MAX)
    elif name == "btw":
        p = args.get("prompt")
        need(is_text(p) and len(p) <= PROMPT_MAX, "prompt is the question's text, at most %d characters" % PROMPT_MAX)
    elif name == "media":
        need("text" not in args, "the words go as a Send, not with the upload")
        need(args.get("delivery") == "queued-turn", "delivery is queued-turn")
        why = media.why_not(args.get("attachments"))
        need(why is None, why)
    elif name == "compact":
        i = args.get("instructions")
        need(i is None or (isinstance(i, str) and len(i) <= INSTRUCTIONS_MAX),
             "instructions is text of at most %d characters" % INSTRUCTIONS_MAX)
    elif name == "spawn":
        need(is_text(args.get("brief")), "brief is the session's brief")
        wt, m, e = args.get("worktree"), args.get("model"), args.get("effort")
        need(wt is None or (isinstance(wt, str) and WORKTREE_RE.fullmatch(wt)), "worktree is a name")
        need(m is None or (isinstance(m, str) and MODEL_RE.fullmatch(m)), "model is a model id or alias")
        need(e is None or e in control.EFFORTS, "effort is one of %s" % ", ".join(control.EFFORTS))


def check_digest(path, sid, digest, decision, scope=None):
    """Check 7: the request as the browser drew it is the one still
    pending in the session, as its bridge reports it, and the decision fits
    it by the bridge's own rule (composite dd908dfa): an async question is
    answered, never denied; a permission is allowed or denied, never
    answered; a question's allow carries answers keyed by its questions. A
    scoped allow's rule is resolved from that request (scoped_rule) into the
    decision. The bridge's 400 stays behind it, after the claim."""
    rid = digest["request"]
    try:
        status, body = bridge.request(path, "GET", "/requests/" + urllib.parse.quote(rid, safe=""))
    except (OSError, http.client.HTTPException) as e:
        # An HTTPException: the bridge went away mid-answer (IncompleteRead).
        raise Refused("not-pending", "the session's bridge did not answer for %s: %s" % (rid, unanswered(e)))
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
    if scope is not None:
        if bridge.is_question(body):
            raise Refused("bad-shape", "decide: a question is answered; a scope goes with a permission's allow")
        decision["updatedPermissions"] = [scoped_rule(body.get("suggestions"), scope)]
    why = bridge._check_decision(body, decision)
    if why:
        raise Refused("bad-shape", why)


def scoped_rule(suggestions, scope):
    """A scoped allow's one rule (§7, §11, MW3): the suggestion at the
    scope's index in the list the bridge holds now, never one the browser
    sent, under the scope's destination. The browser's hash is of the
    suggestion as it drew it: a list that changed under the card (another
    suggestion there, or none) is `not-pending`. Only a rule or a directory
    the engine suggested is taken, and `localSettings` only where the
    suggestion itself names it; `session` may replace any destination."""
    i = scope["suggestion"]
    s = suggestions[i] if isinstance(suggestions, list) and i < len(suggestions) else None
    try:
        held = codes.input_sha256(s) if isinstance(s, dict) else None  # the canonical JSON's SHA-256
    except (codes.NotCanonical, RecursionError):
        held = None
    if held is None or held != scope["sha256"]:
        raise Refused("not-pending", "the suggestions changed: the request no longer offers the one shown")
    if s.get("type") not in SCOPED_TYPES:
        raise Refused("bad-shape", "decide: a scope takes a rule or a directory the engine suggested "
                                   "(addRules, addDirectories), not %s" % s.get("type"))
    if scope["destination"] == "localSettings" and s.get("destination") != "localSettings":
        raise Refused("bad-shape", "decide: localSettings only where the engine suggested it; this suggestion is "
                                   "for %s" % s.get("destination"))
    return dict(s, destination=scope["destination"])


# ------------------------------------------------------------- execution


def unanswered(e):
    """A failed bridge call, said with its kind: an IncompleteRead's text
    alone reads as a byte count."""
    return "%s: %s" % (type(e).__name__, e)


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


def steer(path, text, nonce):
    """The steer as a bridge command carrying the RPC's nonce, under which the
    bridge's child keeps the mod's answer: the trace a restart finds it by."""
    out, _ = command(path, {"op": "steer", "text": text, "rpc": nonce})
    return steered(out)


def steered(out):
    """A steer's outcome from the mod's answer to its command."""
    if out.get("ok"):
        return done({"row": (out.get("result") or {}).get("row")})
    if IDLE in str(out.get("error") or ""):
        return failed("idle", "no turn is running to steer: send it instead")
    return failed("failed", refusal(out))


def refused_op(out):
    """An op the bridge refused, as the RPC's failure: its code the
    message's first word, its reason after."""
    code = out.get("code")
    return failed("failed", "%s: %s" % (code, refusal(out)) if isinstance(code, str) and code else refusal(out))


def commanded(out):
    """A desk command's outcome from the bridge's answer to it (DX6): queued,
    or the bridge's refusal."""
    if out.get("ok"):
        r = out.get("result") or {}
        return done({"queued": r.get("queued") is True, "route": r.get("route"), "id": r.get("id")})
    return refused_op(out)


def started(out):
    """A side question's outcome from the bridge's answer to it (DX6 `btw`):
    started, or the bridge's refusal (`nothing-to-fork`)."""
    if out.get("ok"):
        return done({"started": True, "id": (out.get("result") or {}).get("id")})
    return refused_op(out)


def interrupt(path):
    """The interrupt as a bridge command saying it came from the desk, which
    the record the mod leaves the model names."""
    out, _ = command(path, {"op": "interrupt", "from": "desk"})
    if not out.get("ok"):
        raise Refused("failed", refusal(out))
    r = out.get("result") or {}
    return done({"turnId": r.get("turnId"), "stopped": list(r.get("stopped") or []),
                 "running": list(r.get("running") or [])})


def stop(path, task):
    """A background shell or monitor stopped through the session's bridge,
    which runs TaskStop for it (DX5 `stop`). The engine's refusal is the
    RPC's failure, in the engine's words; the job's `stopped` reaches
    browsers on the session's DX4 body, not here."""
    out, _ = command(path, {"op": "stop", "taskId": task, "from": "desk"})
    if not out.get("ok"):
        raise Refused("failed", refusal(out))
    return done({"taskId": task})


def resolve_agent(path, ref):
    """The id of the running agent `ref` names in the session's subagent tree,
    as its bridge's child keeps it (GET /agents): an id the tree holds first,
    else the name of exactly one running agent. Refused `unknown-agent` when
    none runs by it, `ambiguous-agent` when two running agents share the name."""
    try:
        code, body = bridge.request(path, "GET", "/agents", timeout=3)
    except (OSError, http.client.HTTPException) as e:
        raise Refused("failed", "the session's bridge did not say which agents run (%s): nothing ran" % unanswered(e))
    if code != 200 or not isinstance(body, dict) or not isinstance(body.get("agents"), list):
        raise Refused("failed", "the session's bridge did not say which agents run (HTTP %s): nothing ran" % code)
    agents = [a for a in body["agents"] if isinstance(a, dict) and isinstance(a.get("agentId"), str)]
    by_id = next((a for a in agents if a["agentId"] == ref), None)
    if by_id is not None:
        if by_id.get("running") is True:
            return ref
        raise Refused("unknown-agent", "agent %s is not running" % ref)
    named = [a["agentId"] for a in agents if a.get("running") is True and a.get("name") == ref]
    if len(named) > 1:
        raise Refused("ambiguous-agent", "%d running agents are named %s (%s): name one by its id"
                      % (len(named), ref, ", ".join(named)))
    if not named:
        raise Refused("unknown-agent", "the session's subagent tree holds no running agent by the id or name %s" % ref)
    return named[0]


def stop_agent(path, ref, agent, nonce):
    """One subagent stopped through the session's bridge, which stops the
    agent the tree resolved `ref` to (`agent`, refused if it no longer runs),
    runs TaskStop and leaves the parent its note (DX5 `stop-agent`),
    carrying the RPC's nonce, under which the bridge's child keeps the
    answer. The agent's end reaches browsers in the subagent tree."""
    out, _ = command(path, {"op": "stop-agent", "agentId": ref, "resolvedAgentId": agent, "from": "desk", "rpc": nonce})
    return agent_stopped(out)


def agent_stopped(out):
    """A stop-agent's outcome from the bridge's answer (DX6): the spelling
    asked, the id a name resolved to, and why the parent's note was not
    kept if it was not; or the bridge's refusal."""
    if not out.get("ok"):
        return refused_op(out)
    r = out.get("result") or {}
    extra = {k: r[k] for k in ("resolvedAgentId", "noteError") if isinstance(r.get(k), str) and r[k]}
    return done({"agentId": r.get("agentId"), "accepted": True, **extra})


def tell(path, ref, agent, text, nonce):
    """A message to one subagent through the session's bridge, which sends
    it with the engine's own delivery to the agent the tree resolved `ref`
    to (DX5 `tell`), carrying the RPC's nonce."""
    out, _ = command(path, {"op": "tell", "agentId": ref, "resolvedAgentId": agent, "text": text, "rpc": nonce})
    return told(out)


def told(out):
    """A tell's outcome from the bridge's answer (DX6): sent, once the
    message is in the agent's queue; or the bridge's refusal."""
    return done({"sent": True}) if out.get("ok") else refused_op(out)


def media_held(out, claim):
    """An upload's outcome from the bridge's answer (DX6 `media`): queued once
    the bridge holds it (one it already held counts), its root and files as
    the claim keeps them; or the bridge's refusal."""
    if not out.get("ok"):
        return refused_op(out)
    r = out.get("result") or {}
    if not (r.get("queued") is True or r.get("duplicate") is True) or not isinstance(claim.get("media_root"), str):
        return failed("failed", "the bridge did not say it holds the upload")
    return done({"queued": True, "upload": r.get("upload"), "intake": "native-read", "root": claim["media_root"],
                 "paths": list(claim.get("media_paths") or [])})


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
    except (OSError, http.client.HTTPException) as e:
        raise Refused("failed", "the session's bridge gave no answer: %s" % unanswered(e))
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
        p = subprocess.run(SMINOS_CLI + argv, cwd=cwd, env=verb_env(member), stdin=subprocess.DEVNULL,
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


def holders(sid):
    """The engine's records of the processes of this machine holding the
    session: each record whose pid runs and is the process it describes.
    Read afresh, off sminos's caches (a worker's call)."""
    out = []
    for path in glob.glob(os.path.join(glob.escape(sminos.home_dir()), ".claude", "sessions", "*.json")):
        try:
            with open(path) as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("sessionId") == sid and sminos.pid_alive(rec.get("pid")) \
                and sminos.same_process(rec, fresh=True):
            out.append(rec)
    return out


def held_by(recs):
    return ", ".join("%s, pid %s" % ("a --bg job" if r.get("kind") == "bg" else "a terminal session", r.get("pid"))
                     for r in recs)


def launch_resume(sid, cwd):
    """`claude --bg --resume <session>` in `cwd`, nothing else on the line:
    (the job's short id, or "" when none started; the banner)."""
    env = verb_env()
    env.pop("RUNNER_TRACKING_ID", None)
    try:
        p = subprocess.run(["claude", "--bg", "--resume", sid], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=LAUNCH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return "", str(e)
    banner = sminos.ANSI_RE.sub("", p.stdout or "")
    m = BG_SHORT_RE.search(banner)
    return (m.group(1) if m and p.returncode == 0 else ""), banner


def job_session(short):
    """The session id the harness reports for a job it just started (its
    `claude agents` row can lag the banner), or None."""
    for _ in range(int(os.environ.get("SMINOS_UUID_POLL") or "30")):
        try:
            p = subprocess.run(["claude", "agents", "--json", "--all"], capture_output=True, text=True, timeout=60)
            rows = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else []
        except (OSError, ValueError, subprocess.TimeoutExpired):
            rows = []
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("id") == short and r.get("sessionId"):
                return r["sessionId"]
        time.sleep(sminos.poll_interval())
    return None


def started_at(rec):
    """When a holder's process started, in epoch seconds, or None: the
    engine's record, else /proc (Linux, to the clock tick), else `ps` (whole
    seconds, the start's own second on macOS — never one before it)."""
    at = sminos.process_started(rec)
    if at is not None:
        return at
    at = sminos.proc_started_at(rec.get("pid"))
    if at is not None:
        return at
    parsed = sminos._parse_lstart(sminos.read_proc_start(rec.get("pid")))
    return time.mktime(parsed) if parsed else None   # ps prints the local zone


def launched_by(rec, launched, job, rivals=()):
    """Whether a holder of the session is the --bg process of the launch made
    at `launched`, whose job is `job`: started no earlier than the launch's
    second, its job the one that launch started. With no `job` (a launch
    stopped before its banner was read), any --bg process started since
    then that none of `rivals` — the launch times of other Resumes of the
    session still running when this one launched — can own: one launched
    no later than the process's start could be its launch. (A job id does
    not tell launches apart: the engine names a session's every --bg job
    by the session id's first 8 characters.)"""
    started = started_at(rec)
    if rec.get("kind") != "bg" or started is None or started < int(launched):
        return False
    if job is not None:
        return rec.get("jobId") == job
    return not any(int(r) <= started for r in rivals)


def resume(sid, cwd, lock, note):
    """§5's Resume of a session no process of this machine holds. One per
    session at a time: the second of two finds the first's job holding it.
    The engine's own check is the last word on a reopen racing the launch:
    it starts a copy, which is stopped, and the RPC fails `copy-started`.
    The launch is kept in the claim before it runs (`note`), and its job
    once known, so a restart reconciles from this launch (trace); done only
    once that job's process holds the session."""
    with lock:
        live = holders(sid)
        if live:
            raise Refused("session-live", "the session is running here (%s): only an ended session is resumed"
                          % held_by(live))
        if not (cwd and os.path.isdir(cwd)):
            raise Refused("failed", "the session's working directory %r is gone: nothing was launched" % (cwd,))
        launched = time.time()
        try:
            note(launched_at=launched)
        except OSError as e:
            raise Refused("failed", "the launch could not be kept in the ledger (%s): nothing was launched" % e)
        short, banner = launch_resume(sid, cwd)
        if not short:
            raise Refused("failed", "claude --bg --resume started no job: %s" % (last_line(banner) or "no output"))
        try:
            note(job=short)
        except OSError as e:
            log("resume of %s: its job %s could not be kept in the ledger: %s" % (sid, short, e))
        copy = COPY_RE.search(banner)
        reported = None if copy else job_session(short)
        if copy or (reported is not None and reported != sid):
            return copy_started(short, sminos.claude_stop(short))
        if reported is None:
            raise Refused("failed", "the harness named no session for job %s: it may be running" % short)
        deadline = time.time() + RESUME_HELD_S
        while not any(launched_by(r, launched, short) for r in holders(sid)):
            if time.time() >= deadline:
                raise Refused("failed", "job %s took the session, but no process of it holds the session after "
                                        "%g s: it did not start, or has not yet" % (short, RESUME_HELD_S))
            time.sleep(0.1)
        sminos.nudge_daemon()   # its tick re-joins the session and delivers what was kept for it
        return done({"session": sid})


def copy_started(short, stopped):
    """A Resume whose job continued a copy of the session, not the session:
    the RPC's failure, saying whether the copy was stopped."""
    return failed("copy-started", "the session was opened elsewhere meanwhile, so the engine started a copy (%s) "
                                  "instead of continuing it; the copy %s" % (
                                      short, "was stopped" if stopped else
                                      "could not be stopped: `claude stop %s` failed" % short))


def retire(sid, root, member):
    rc, _, err = run_verb(["retire", "--", sid], root, VERB_TIMEOUT, member)
    if rc != 0:
        raise Refused("failed", last_line(err) or "sminos retire exited %d" % rc)
    return done({})


# ------------------------------------------------------------- traces


def kept_job(e):
    """A claimed Resume's job, as its launch kept it, or None."""
    job = e.get("job") if e.get("rpc") == "resume" else None
    return job if isinstance(job, str) and job and e.get("session") else None


def resume_rivals(e, others):
    """The launch times of other Resume claims of `e`'s session not finished
    before `e`'s launch: a process started since could be theirs. One
    answered before it is not: its process, if any, had ended by the time
    this launch found no process holding the session."""
    launched = e.get("launched_at")
    out = []
    for x in others:
        at, ended = x.get("launched_at"), x.get("done_at")
        if x.get("rpc") != "resume" or x.get("session") != e.get("session") \
                or not isinstance(at, (int, float)) or isinstance(at, bool):
            continue
        if isinstance(ended, (int, float)) and not isinstance(ended, bool) and ended < launched:
            continue
        out.append(at)
    return out


# The RPCs whose answer the bridge's child keeps under the nonce, each with how that answer reads as the outcome.
KEPT_READERS = {"steer": steered, "command": commanded, "btw": started, "stop-agent": agent_stopped, "tell": told}


def trace(nonce, e, others=()):
    """(the outcome a claim's trace shows, or None; how long after its claim
    a trace may still appear). `others`: the ledger's other entries."""
    if e.get("rpc") == "spawn":
        return spawned(nonce), SPAWN_TRACE_S
    if e.get("rpc") == "media" and e.get("session"):
        answered = (bridge.load_kept(e["session"]).get("rpcs") or {}).get(nonce)
        return (media_held(answered, e) if isinstance(answered, dict) else None), STEER_TRACE_S
    if e.get("rpc") in KEPT_READERS and e.get("session"):
        answered = (bridge.load_kept(e["session"]).get("rpcs") or {}).get(nonce)
        read = KEPT_READERS[e["rpc"]]
        outcome = read(answered) if isinstance(answered, dict) else None
        return outcome, STEER_TRACE_S
    if e.get("rpc") == "resume" and e.get("session"):
        launched, job = e.get("launched_at"), kept_job(e)
        if not isinstance(launched, (int, float)) or isinstance(launched, bool):
            return None, 0   # stopped before its launch: nothing ran
        # Stopped after the launch began: `claude --bg` outlives the uplink
        # that ran it, so its job may hold the session now or within the
        # window. Before its job was known, a --bg process started since the
        # launch is taken for it unless another Resume could have started it.
        rivals = resume_rivals(e, others) if job is None else ()
        ran = any(launched_by(r, launched, job, rivals) for r in holders(e["session"]))
        return (done({"session": e["session"]}) if ran else None), RESUME_TRACE_S
    return None, 0
