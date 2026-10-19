#!/usr/bin/env python3
"""sminos_requests — the requests this machine's sessions raise, relayed to
the hub (DC7 of the desk: DX4's `raised` and `settled`, DX2's `pending`,
DX1's codes; DX5's requests as the consumer).

A bridge (DC2) raises each permission prompt or question the engine puts to
its dialog as `raised`, and settles it once as `settled`; its snapshot holds
the requests pending now and the last settlements. For every session of an
open hub project whose bridge answers, one reader holds the bridge's DX5
stream (`GET /events`) and takes from it only those: the snapshot's
`pending` and `settled`, and each `raised`, `settled`, and `resync` (the
mod's whole state again, which replaces the bridge's pending set). Chunks
and everything else are passed over unparsed.

What goes up, each sealed with the org key under a fresh nonce (DX1), and
nothing without one — the daemon signs only what its bridges reported, as
they reported it:

- DX4 `raised` `{request, session, tool, input, agentId?, truncated?,
  deadline?, async?, toolUseId?}` (composite 6fa2252d, 43a27604): the
  bridge's fields; `agentId` only for a subagent's request, `truncated` only
  as true, `toolUseId` (the call an ask mod's dialog belongs to) only where
  it differs from `request`; a background
  subagent's `deadline` (epoch ms on DX5) as ISO 8601 UTC with
  milliseconds, after which the hub marks the request `terminal_only`;
- DX4 `settled` `{request, winner, outcome, by}` as the bridge settled it,
  once per raise, and never after a later raise of the same request (the
  open ask a resumed session raises again under its call's id). A
  settlement is its request and the bridge's `t`: every one a bridge
  reports, live or in a snapshot's recent list, goes up unless it went
  before. One still waiting here when its request is raised again, or
  listed beside that request pending again, never goes: the raise
  supersedes it, the hub holding the request pending under the same id.
  The ones sent or superseded are kept in `daemon/requests.json` across
  restarts (the hub records each it is sent as a decision). The file's
  older entries, bare request ids, are not read: the first start on a file
  of that form sends again what live bridges still list, which the hub
  takes as resends of requests no longer pending;
- DX2 `pending` `{project, raised}`: the machine's complete set for the
  project, after every connect, and whenever a request left the set with no
  settlement the bridge reported (its bridge gone, a snapshot without it):
  the hub drops what the set no longer holds; nothing is settled in a
  bridge's name. A set is complete only once the bridges of the project's
  sessions have been read (a snapshot each, or a reader that could get
  none), so it waits for that, at most HOLD_MAX: an uplink that starts with
  requests already pending does not empty the hub's set first.

The state outlives the stream (the uplink keeps one Requests): a settlement
made while the hub is out of reach goes up after the next connect, ahead of
the complete set, and is never dropped; a raise made then is in that set. A
reader whose stream ends while the bridge still answers subscribes again,
and its snapshot is reconciled against what was held.

Readers only read the bridge's socket and queue what they read; everything
else runs on the uplink's main thread.
"""

import http.client
import json
import os
import queue
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_bridge as bridge  # noqa: E402
import sminos_codes as codes  # noqa: E402

RETRY = 1.0                # s: a reader whose stream ended subscribes again after this,
RETRY_MAX = 30.0           # doubling up to this while its bridge gives no snapshot
CONNECT_WAIT = 10.0        # s: the bridge holds GET /events until it is ready, at most 5 s
HOLD_MAX = 8.0             # s: the complete set waits for the bridges' snapshots at most this long
OUTBOX_MAX = 2000          # messages kept for the hub while it is out of reach (settlements: all of them)
RELAYED_FILE = "requests.json"  # daemon/: the settlements done with, per session
RELAYED_KEPT = 200
RELAYED_SESSIONS = 1000
TOOL_USE_ID_MAX = 512      # the hub's bound on `raised.toolUseId` (DC3, MAWS 4b5d0a67)
WANTED = (b'"raised"', b'"settled"', b'"resync"', b'"compact"')   # a line carrying none of these is no line of ours


def log(line):
    sminos.daemon_log("requests: " + line)


def iso_ms(epoch_ms):
    ms = int(epoch_ms)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms // 1000)) + ".%03dZ" % (ms % 1000)


def raised_draft(sid, e):
    """DX4's `raised` for a request as the bridge reported it, without its
    code; None for one that names no request, tool, or input."""
    rid, tool, tool_input = e.get("request"), e.get("tool"), e.get("input")
    if not (isinstance(rid, str) and rid and isinstance(tool, str) and tool and isinstance(tool_input, dict)):
        return None
    d = {"request": rid, "session": sid, "tool": tool, "input": tool_input}
    deadline = e.get("deadline")
    if isinstance(deadline, (int, float)) and not isinstance(deadline, bool) and deadline >= 0:
        d["deadline"] = iso_ms(deadline)
    if e.get("async") is True:
        d["async"] = True
    if isinstance(e.get("agentId"), str) and e["agentId"]:
        d["agentId"] = e["agentId"]
    if e.get("truncated") is True:
        d["truncated"] = True
    call = e.get("toolUseId")
    if isinstance(call, str) and call and call != rid and len(call) <= TOOL_USE_ID_MAX:
        d["toolUseId"] = call
    return d


def settled_draft(e):
    d = {k: e.get(k) for k in ("request", "winner", "outcome", "by")}
    return d if all(isinstance(v, str) and v for v in d.values()) else None


class Reader(threading.Thread):
    """One bridge's stream, read for its requests: ("snapshot" | "resync",
    (pending, settled)), ("raised" | "settled", event), and its end,
    ("closed", why), each queued as (reader, kind, data). A compaction's
    `compact` events ride along, for the RPCs (sminos_rpc)."""

    def __init__(self, sid, items, wake):
        super().__init__(name="requests-reader", daemon=True)
        self.sid = sid
        self.items = items
        self.wake = wake
        self.closing = threading.Event()
        self.sock = None

    def put(self, kind, data):
        self.items.put((self, kind, data))
        self.wake()

    def run(self):
        conn = bridge._UnixConnection(bridge.endpoint(self.sid), CONNECT_WAIT)
        try:
            conn.connect()
            self.sock = conn.sock
            if self.closing.is_set():
                self.sock.shutdown(socket.SHUT_RDWR)
            conn.request("GET", "/events")
            resp = conn.getresponse()
            if resp.status != 200:
                self.put("closed", "the bridge answered %d" % resp.status)
                return
            self.sock.settimeout(None)
            first = True
            while True:
                line = resp.readline()
                if not line:
                    self.put("closed", "the bridge ended the stream")
                    return
                if not first and not any(w in line for w in WANTED):
                    continue
                e = json.loads(line)
                kind = e.get("type") if isinstance(e, dict) else None
                if first:
                    first = False
                    if kind != "snapshot":
                        self.put("closed", "the bridge's stream began without a snapshot")
                        return
                listed = e.get("settled") if isinstance(e.get("settled"), list) else []
                if kind == "snapshot":
                    self.put(kind, (e.get("pending") if isinstance(e.get("pending"), list) else [], listed))
                elif kind == "resync" and isinstance(e.get("pending"), list):
                    self.put(kind, (e["pending"], listed))
                elif kind in ("raised", "settled", "compact"):
                    self.put(kind, e)
        except (OSError, ValueError, http.client.HTTPException) as e:
            self.put("closed", "closed here" if self.closing.is_set() else str(e) or repr(e))
        finally:
            conn.close()

    def close(self):
        self.closing.set()
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Requests:
    """The pending requests of the machine's bridged sessions and the
    messages owed to the hub about them. Kept across streams by the uplink;
    `wake` is the current stream's."""

    def __init__(self, key, machine, wake=lambda: None, clock=time.monotonic):
        self.key = key
        self.machine = machine
        self.wake = wake
        self.clock = clock
        self.items = queue.Queue()
        self.readers = {}     # session → its Reader
        self.read = set()     # the readers that delivered their snapshot
        self.retry_at = {}    # session → when its reader may subscribe again
        self.fails = {}       # session → readers in a row that ended without a snapshot
        self.followed = {}    # session → project id: the open projects' sessions with an endpoint
        self.project_of = {}  # session → project id, kept while it holds requests
        self.pending = {}     # session → {request: sealed DX4 raised}, in the order raised
        self.synced = set()   # sessions whose bridge's state is known: a snapshot read, or none to be had
        self.outbox = []      # [(project id, frame)]: raised and settled messages not yet sent, in order
        self.stale = set()    # project ids whose complete pending set is owed
        self.holding = {}     # project id → since when its owed set waits for its sessions' snapshots
        self.queued = {}      # (session, request, t) → the outbox's frame carrying that settlement
        self.relayed = load_relayed()  # session → [(request, t)]: the settlements done with (sent or superseded)
        self.compacts = []    # [(session, project id, event)]: the bridges' `compact` events, for the RPCs
        self.said = set()

    def say_once(self, key, line):
        if key not in self.said:
            self.said.add(key)
            log(line)

    # ---------------------------------------------------- the readers

    def follow(self, sessions):
        """{session: project id} of the open projects' sessions whose
        endpoint exists: a reader for each. A session no longer here keeps
        its reader until its stream ends; one with none loses its requests."""
        self.followed = dict(sessions)
        self.project_of.update(sessions)
        for sid in [s for s in self.pending if s not in sessions and s not in self.readers]:
            self.drop(sid)
        self.start_due()

    def start_due(self):
        now = self.clock()
        for sid in self.followed:
            if sid not in self.readers and self.retry_at.get(sid, 0.0) <= now:
                r = self.readers[sid] = Reader(sid, self.items, lambda: self.wake())
                r.start()

    def drop(self, sid):
        """A session whose bridge is gone: its requests leave the set."""
        if self.pending.pop(sid, None) and self.project_of.get(sid):
            self.stale.add(self.project_of[sid])
        self.retry_at.pop(sid, None)
        self.fails.pop(sid, None)
        self.synced.discard(sid)
        if sid not in self.followed:
            self.project_of.pop(sid, None)

    def ready(self, pid):
        """Whether every followed session of the project has had its
        bridge's state read (or has none to be read): only then is the set
        held here complete."""
        return all(sid in self.synced for sid, p in self.followed.items() if p == pid)

    def close(self):
        for r in self.readers.values():
            r.close()
        self.readers.clear()

    # ---------------------------------------------------- what the readers read

    def take(self):
        """Everything the readers queued, applied in order; readers due again
        started."""
        while True:
            try:
                r, kind, data = self.items.get_nowait()
            except queue.Empty:
                break
            if self.readers.get(r.sid) is not r:
                continue
            sid = r.sid
            pid = self.project_of.get(sid)
            if kind in ("snapshot", "resync"):
                if kind == "snapshot":
                    self.read.add(r)
                    self.synced.add(sid)
                    self.fails.pop(sid, None)
                self.reconcile(sid, pid, *data)
            elif kind == "raised":
                self.raised(sid, pid, data)
            elif kind == "settled":
                self.settled(sid, pid, data)
            elif kind == "compact":
                self.compacts.append((sid, pid, data))
            elif kind == "closed":
                del self.readers[sid]
                snapped = r in self.read
                self.read.discard(r)
                if sid in self.followed and os.path.exists(bridge.endpoint(sid)):
                    fails = 0 if snapped else self.fails.get(sid, 0) + 1
                    self.fails[sid] = fails
                    self.retry_at[sid] = self.clock() + min(RETRY * 2 ** max(fails - 1, 0), RETRY_MAX)
                    if not snapped:
                        # No state to be had from it now: what is held stands,
                        # and the set need not wait for it.
                        self.synced.add(sid)
                        self.say_once(("unread", sid), "%s's bridge could not be read (%s): its requests are "
                                                       "read again when it answers" % (sid, data))
                else:
                    self.drop(sid)
        self.start_due()

    def take_compacts(self):
        """The `compact` events read since the last call, in order."""
        out, self.compacts = self.compacts, []
        return out

    def seal(self, kind, pid, draft):
        try:
            return codes.seal(self.key, kind, pid, draft, codes.b64url(os.urandom(codes.NONCE_BYTES)))
        except codes.NotCanonical as e:
            log("a %s of %s has no canonical form (%s): not sent" % (kind, draft.get("session") or "", e))
            return None

    def queue(self, pid, sid, kind, body):
        frame = {"t": "session", "message": {
            "project": pid, "machine": self.machine, "session": sid, "kind": kind, "sub": None, "n": None,
            "body": body}}
        self.outbox.append((pid, frame))
        if len(self.outbox) > OUTBOX_MAX:
            # A raise is rebuilt by the complete set after the next connect;
            # a settlement is not, so settlements are never dropped.
            i = next((i for i, (_, f) in enumerate(self.outbox) if f["message"]["kind"] == "raised"), None)
            if i is not None:
                # The set held here still has it: the complete set goes, so
                # the hub is told of it on this stream too.
                self.stale.add(self.outbox[i][0])
                del self.outbox[i]
                self.say_once("full", "more than %d messages wait for the hub: the oldest raises go (the "
                                      "complete set, sent next, carries what is pending)" % OUTBOX_MAX)
        return frame

    def raised(self, sid, pid, e):
        draft = raised_draft(sid, e)
        if draft is None:
            log("a raised from %s's bridge without a request, tool, or input: passed by" % sid)
            return
        self.supersede([k for k in self.queued if k[:2] == (sid, draft["request"])])
        held = self.pending.setdefault(sid, {})
        old = held.get(draft["request"])
        if old is not None and {k: v for k, v in old.items() if k != "mac"} == draft:
            return
        body = self.seal("raised", pid, draft)
        if body is not None:
            held[draft["request"]] = body
            self.queue(pid, sid, "raised", body)

    def seen(self, key):
        return key in self.queued or key[1:] in self.relayed.get(key[0], ())

    def done(self, key):
        held = self.relayed.setdefault(key[0], [])
        if key[1:] not in held:
            held.append(key[1:])
            del held[:-RELAYED_KEPT]

    def supersede(self, keys):
        """Settlements a later raise of their request supersedes: never sent
        (one in the outbox leaves it) and kept as done with, so no snapshot
        brings them back. The hub holds the request pending under the same
        id."""
        keys = [k for k in keys if k[1:] not in self.relayed.get(k[0], ())]
        if not keys:
            return
        gone = {id(self.queued.pop(k)) for k in keys if k in self.queued}
        self.outbox = [(p, f) for p, f in self.outbox if id(f) not in gone]
        for k in keys:
            self.done(k)
        save_relayed(self.relayed)

    def settled(self, sid, pid, e):
        draft = settled_draft(e)
        if draft is None:
            log("a settled from %s's bridge without request, winner, outcome, or by: passed by" % sid)
            return
        key = settlement(sid, e)
        if self.seen(key):
            # It went before, or waits to: any raise held here came after it, and stays.
            return
        self.pending.get(sid, {}).pop(draft["request"], None)
        body = self.seal("settled", pid, draft)
        if body is not None:
            self.queued[key] = self.queue(pid, sid, "settled", body)

    def reconcile(self, sid, pid, pending, settled):
        """A snapshot or a resync: the session's pending set as the bridge
        holds it now, and its recent settlements. Every settlement not yet
        relayed goes up (one raised and settled while no reader was there
        too), but not one of a request pending there again, which that raise
        supersedes; a request held here and gone there with none sends the
        complete set again; new ones are raised."""
        now = [r for r in pending if isinstance(r, dict) and isinstance(r.get("request"), str)]
        ids = {r["request"] for r in now}
        for s in settled:
            if not isinstance(s, dict):
                continue
            if isinstance(s.get("request"), str) and s["request"] in ids:
                self.supersede([settlement(sid, s)])
            else:
                self.settled(sid, pid, s)
        for rid in [rid for rid in self.pending.get(sid, {}) if rid not in ids]:
            self.pending[sid].pop(rid, None)
            self.stale.add(pid)
        for r in now:
            self.raised(sid, pid, r)

    # ---------------------------------------------------- what goes up

    def pending_frame(self, pid):
        return {"t": "pending", "project": pid,
                "raised": [b for sid, held in self.pending.items() if self.project_of.get(sid) == pid
                           for b in held.values()]}

    def set_due(self, pid):
        """Whether the project's owed set may go now: once its sessions'
        bridges are read, or HOLD_MAX after it began to wait."""
        if self.ready(pid):
            return True
        since = self.holding.setdefault(pid, self.clock())
        if self.clock() - since < HOLD_MAX:
            return False
        self.say_once(("held", pid, since), "the pending set of %s went after %ds without every bridge read" % (
            pid, HOLD_MAX))
        return True

    def due(self, opened):
        """The frames owed to the hub for the projects open on the stream, in
        order: raised and settled messages, then each complete set owed and
        due. Not taken until `sent`."""
        out = [f for pid, f in self.outbox if pid in opened]
        return out + [self.pending_frame(pid) for pid in sorted(self.stale & set(opened)) if self.set_due(pid)]

    def opening(self, pid):
        """What follows `hello` for a project on a new stream: the
        settlements the hub has not had, then the complete pending set — at
        once when its sessions' bridges are read, else from `due` once they
        are (within HOLD_MAX). The raises it carries are not sent apart."""
        self.outbox = [(p, f) for p, f in self.outbox if p != pid or f["message"]["kind"] != "raised"]
        self.stale.add(pid)
        backlog = [f for p, f in self.outbox if p == pid]
        return backlog + ([self.pending_frame(pid)] if self.set_due(pid) else [])

    def sent(self, frames):
        """`frames` reached the hub (a POST answered 200). A settlement among
        them that a raise superseded meanwhile is done with already."""
        ids = {id(f) for f in frames}
        self.outbox = [(p, f) for p, f in self.outbox if id(f) not in ids]
        for f in frames:
            if f.get("t") == "pending":
                self.stale.discard(f["project"])
                self.holding.pop(f["project"], None)
        took = [k for k, f in self.queued.items() if id(f) in ids]
        for k in took:
            del self.queued[k]
            self.done(k)
        if took:
            save_relayed(self.relayed)


def settlement(sid, e):
    """A settlement's key: its session, its request, and the bridge's `t`
    (None when it carries no number), which tells two settlements of one
    request apart."""
    t = e.get("t")
    return sid, e.get("request"), t if isinstance(t, (int, float)) and not isinstance(t, bool) else None


def relayed_path():
    return os.path.join(sminos.root(), "daemon", RELAYED_FILE)


def load_relayed():
    """The settlements done with, per session, as kept across restarts:
    [request, t] each (a bare request id, the older form, is none)."""
    try:
        with open(relayed_path()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    return {sid: [(k[0], k[1]) for k in keys if isinstance(k, list) and len(k) == 2 and isinstance(k[0], str)
                  and (k[1] is None or isinstance(k[1], (int, float)) and not isinstance(k[1], bool))]
            for sid, keys in d.items() if isinstance(keys, list)}


def save_relayed(relayed):
    """Kept whole, the most recent RELAYED_SESSIONS sessions (each with its
    last RELAYED_KEPT settlements: a bridge's snapshot lists its last 100).
    A write that fails is said and costs at most a settlement sent twice."""
    while len(relayed) > RELAYED_SESSIONS:
        del relayed[next(iter(relayed))]
    try:
        os.makedirs(os.path.dirname(relayed_path()), mode=0o700, exist_ok=True)
        sminos.write_json(relayed_path(), relayed)
    except OSError as e:
        log("the settlements relayed could not be kept in %s: %s" % (relayed_path(), e))
