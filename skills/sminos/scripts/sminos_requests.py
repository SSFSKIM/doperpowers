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

- DX4 `raised` `{request, session, tool, input, deadline?, async?}`: the
  bridge's fields; a background subagent's `deadline` (epoch ms on DX5) as
  ISO 8601 UTC with milliseconds, after which the hub marks the request
  `terminal_only`; the rest of DX5's (agentId, truncated) is not DX4's;
- DX4 `settled` `{request, winner, outcome, by}` as the bridge settled it;
- DX2 `pending` `{project, raised}`: the machine's complete set for the
  project, after every connect, and whenever a request left the set with no
  settlement the bridge reported (its bridge gone, a snapshot without it):
  the hub drops what the set no longer holds; nothing is settled in a
  bridge's name.

The state outlives the stream (the uplink keeps one Requests): a settlement
made while the hub is out of reach goes up after the next connect, ahead of
the complete set; a raise made then is in that set. A reader whose stream
ends while the bridge still answers subscribes again, and its snapshot is
reconciled against what was held: a request no longer pending that the
snapshot lists as settled is sent settled, a new one raised.

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

RETRY = 1.0                # s: a reader whose stream ended subscribes again after this
CONNECT_WAIT = 10.0        # s: the bridge holds GET /events until it is ready, at most 5 s
OUTBOX_MAX = 2000          # messages kept for the hub while it is out of reach; the oldest go first
WANTED = (b'"raised"', b'"settled"', b'"resync"')   # a line carrying none of these is no line of ours


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
    return d


def settled_draft(e):
    d = {k: e.get(k) for k in ("request", "winner", "outcome", "by")}
    return d if all(isinstance(v, str) and v for v in d.values()) else None


class Reader(threading.Thread):
    """One bridge's stream, read for its requests: ("snapshot" | "resync",
    (pending, settled)), ("raised" | "settled", event), and its end,
    ("closed", why), each queued as (reader, kind, data)."""

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
                if kind in ("snapshot", "resync"):
                    if isinstance(e.get("pending"), list):
                        self.put(kind, (e["pending"], e.get("settled") if isinstance(e.get("settled"), list) else []))
                elif kind in ("raised", "settled"):
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

    def __init__(self, key, machine, wake=lambda: None):
        self.key = key
        self.machine = machine
        self.wake = wake
        self.items = queue.Queue()
        self.readers = {}     # session → its Reader
        self.retry_at = {}    # session → when its reader may subscribe again
        self.followed = {}    # session → project id: the sessions whose bridges answer now
        self.project_of = {}  # session → project id, kept while it holds requests
        self.pending = {}     # session → {request: sealed DX4 raised}, in the order raised
        self.outbox = []      # [(project id, frame)]: raised and settled messages not yet sent, in order
        self.stale = set()    # project ids whose complete pending set is owed
        self.dropped = 0

    # ---------------------------------------------------- the readers

    def follow(self, sessions):
        """{session: project id} of the open projects' sessions whose bridge
        answers: a reader for each. A session no longer here keeps its
        reader until its stream ends; one with none loses its requests."""
        self.followed = dict(sessions)
        self.project_of.update(sessions)
        for sid in [s for s in self.pending if s not in sessions and s not in self.readers]:
            self.drop(sid)
        self.start_due()

    def start_due(self):
        now = time.monotonic()
        for sid in self.followed:
            if sid not in self.readers and self.retry_at.get(sid, 0.0) <= now:
                r = self.readers[sid] = Reader(sid, self.items, lambda: self.wake())
                r.start()

    def drop(self, sid):
        """A session whose bridge is gone: its requests leave the set."""
        if self.pending.pop(sid, None) and self.project_of.get(sid):
            self.stale.add(self.project_of[sid])
        self.retry_at.pop(sid, None)
        if sid not in self.followed:
            self.project_of.pop(sid, None)

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
                self.reconcile(sid, pid, *data)
            elif kind == "raised":
                self.raised(sid, pid, data)
            elif kind == "settled":
                self.settled(sid, pid, data)
            elif kind == "closed":
                del self.readers[sid]
                if sid in self.followed and os.path.exists(bridge.endpoint(sid)):
                    self.retry_at[sid] = time.monotonic() + RETRY
                else:
                    self.drop(sid)
        self.start_due()

    def seal(self, kind, pid, draft):
        try:
            return codes.seal(self.key, kind, pid, draft, codes.b64url(os.urandom(codes.NONCE_BYTES)))
        except codes.NotCanonical as e:
            log("a %s of %s has no canonical form (%s): not sent" % (kind, draft.get("session") or "", e))
            return None

    def queue(self, pid, sid, kind, body):
        self.outbox.append((pid, {"t": "session", "message": {
            "project": pid, "machine": self.machine, "session": sid, "kind": kind, "sub": None, "n": None,
            "body": body}}))
        if len(self.outbox) > OUTBOX_MAX:
            del self.outbox[0]
            self.dropped += 1
            if self.dropped == 1:
                log("more than %d messages wait for the hub: the oldest go (the complete set after the next "
                    "connect still holds what is pending)" % OUTBOX_MAX)

    def raised(self, sid, pid, e):
        draft = raised_draft(sid, e)
        if draft is None:
            log("a raised from %s's bridge without a request, tool, or input: passed by" % sid)
            return
        held = self.pending.setdefault(sid, {})
        old = held.get(draft["request"])
        if old is not None and {k: v for k, v in old.items() if k != "mac"} == draft:
            return
        body = self.seal("raised", pid, draft)
        if body is not None:
            held[draft["request"]] = body
            self.queue(pid, sid, "raised", body)

    def settled(self, sid, pid, e):
        draft = settled_draft(e)
        if draft is None:
            log("a settled from %s's bridge without request, winner, outcome, or by: passed by" % sid)
            return
        self.pending.get(sid, {}).pop(draft["request"], None)
        body = self.seal("settled", pid, draft)
        if body is not None:
            self.queue(pid, sid, "settled", body)

    def reconcile(self, sid, pid, pending, settled):
        """A snapshot or a resync: the session's pending set as the bridge
        holds it now. Requests held here and gone there are sent settled when
        it lists them as settled, else the complete set goes again; new ones
        are raised."""
        now = [r for r in pending if isinstance(r, dict) and isinstance(r.get("request"), str)]
        ids = {r["request"] for r in now}
        by = {s.get("request"): s for s in settled if isinstance(s, dict)}
        for rid in [rid for rid in self.pending.get(sid, {}) if rid not in ids]:
            if rid in by:
                self.settled(sid, pid, by[rid])
            else:
                self.pending[sid].pop(rid, None)
                self.stale.add(pid)
        for r in now:
            self.raised(sid, pid, r)

    # ---------------------------------------------------- what goes up

    def pending_frame(self, pid):
        return {"t": "pending", "project": pid,
                "raised": [b for sid, held in self.pending.items() if self.project_of.get(sid) == pid
                           for b in held.values()]}

    def due(self, opened):
        """The frames owed to the hub for the projects open on the stream, in
        order: raised and settled messages, then each complete set owed. Not
        taken until `sent`."""
        out = [f for pid, f in self.outbox if pid in opened]
        return out + [self.pending_frame(pid) for pid in sorted(self.stale & set(opened))]

    def opening(self, pid):
        """What follows `hello` for a project on a new stream: the
        settlements the hub has not had, then the complete pending set (the
        raises it holds are not sent apart)."""
        self.outbox = [(p, f) for p, f in self.outbox if p != pid or f["message"]["kind"] != "raised"]
        return [f for p, f in self.outbox if p == pid] + [self.pending_frame(pid)]

    def sent(self, frames):
        """`frames` reached the hub (a POST answered 200)."""
        ids = {id(f) for f in frames}
        self.outbox = [(p, f) for p, f in self.outbox if id(f) not in ids]
        for f in frames:
            if f.get("t") == "pending":
                self.stale.discard(f["project"])
