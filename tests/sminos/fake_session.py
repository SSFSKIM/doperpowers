"""A scripted session for the session plane's tests (DC7 M1): the engine's
transcript on disk and the bridge's DX5 endpoint, each moved by the test's
own hand, so that a row can reach disk ahead of its notice, a notice ahead of
its row, a chunk arrive while a snapshot is built, and a module reload end a
subscription — the orders the real engine and mod produce, and the ones
they produce only rarely.

The endpoint follows DX5 as DC2's M4 agreed it with the composite's writer
(DC2's plan, Decision Log "M4 scope, agreed with the composite's writer for
DC7", rules 1–4), not DC2's code:

- every row the mod observes gets one notice on the ordered stream, before it
  is written: `block-row` for a response row, `row-seen` for any other;
- the snapshot carries `cut`, the last notice applied per loop (`"main"` or
  the agent id), under the lock that applies chunks and block-rows;
- `GET /status` says `ready` once the mod's first `resync` is applied, and
  `GET /events` holds until then (at most 5 s, else 503);
- a later `resync` ends every open subscription.

    session = FakeSession(home, sminos_home, session_id)
    session.start_bridge(ready=True)       # the endpoint, $SMINOS_HOME/bridge/<id>.sock
    m = session.message(agent=None)        # a model request of the main loop
    m.text(0, "Hello, ")                   # a chunk of block 0
    u = m.row(0, post=True, disk=True)     # its notice, then its row
    session.user_row("ok")                 # a row-seen, then the row
"""

import json
import os
import queue
import socket
import socketserver
import threading
import time
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler

READY_HOLD = 5.0


class Endpoint:
    """The child's state as DX5 has it, with M4's cut and readiness: one
    lock applies each event and fans it out, and takes a snapshot and adds a
    subscriber."""

    def __init__(self, session):
        self.session = session
        self.lock = threading.Condition()
        self.streaming = {}   # (turnId, agentId, step) → {turnId, agentId, step, model, upTo, blocks: {index: block}}
        self.cut = {}         # loop → uuid of the last notice applied
        self.usage = None
        self.agents = {}
        self.subscribers = []
        self.ready = False
        self.resyncs = 0
        self.sent = 0         # events fanned out

    def snapshot(self):
        return {"type": "snapshot", "session": self.session, "protocol": 1, "pid": os.getpid(),
                "sessionInfo": {"session": self.session}, "turns": [],
                "streaming": [{"turnId": m["turnId"], "agentId": m["agentId"], "step": m["step"], "model": m["model"],
                               "upTo": m["upTo"], "blocks": [dict(m["blocks"][i]) for i in sorted(m["blocks"])]}
                              for m in self.streaming.values()],
                "agents": list(self.agents.values()), "usage": self.usage, "override": None,
                "pending": [], "settled": [], "cut": dict(self.cut)}

    def post(self, events):
        with self.lock:
            for e in events:
                self._apply(e)

    def _apply(self, e):
        kind = e["type"]
        loop = e.get("agentId") or "main"
        if kind == "resync":
            self.resyncs += 1
            self.ready = True
            if self.resyncs > 1:
                for q in self.subscribers:
                    q.put(None)
                self.subscribers = []
            self.lock.notify_all()
            return
        key = (e.get("turnId"), e.get("agentId"), e.get("step"))
        if kind == "step":
            if e["phase"] == "start":
                self.streaming[key] = {"turnId": key[0], "agentId": key[1], "step": key[2], "model": "m",
                                       "upTo": -1, "blocks": {}}
            else:
                self.streaming.pop(key, None)
        elif kind == "chunk":
            m = self.streaming[key]
            c = e["chunk"]
            m["upTo"] = e["chunkIndex"]
            b = m["blocks"].setdefault(c["index"], {"index": c["index"], "kind": c["kind"], "text": "", "upTo": -1})
            b["text"] += c.get("text", "")
            b["upTo"] = e["chunkIndex"]
        elif kind == "block-row":
            m = self.streaming.get(key)
            if m is not None:
                m["blocks"].pop(e["index"], None)
            self.cut[loop] = e["uuid"]
        elif kind == "row-seen":
            self.cut[loop] = e["uuid"]
        elif kind == "usage":
            self.usage = dict(e)
        elif kind == "agent":
            self.agents[e["agentId"]] = {"agentId": e["agentId"], "running": e["phase"] != "stop"}
        self.sent += 1
        for q in self.subscribers:
            q.put({"n": self.sent, **e})

    def subscribe(self):
        with self.lock:
            deadline = time.time() + READY_HOLD
            while not self.ready and time.time() < deadline:
                self.lock.wait(deadline - time.time())
            if not self.ready:
                return None, None
            q = queue.Queue()
            self.subscribers.append(q)
            return self.snapshot(), q

    def end_all(self):
        with self.lock:
            for q in self.subscribers:
                q.put(None)
            self.subscribers = []


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def address_string(self):
        return "local"

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self):
        ep = self.server.endpoint
        if self.path == "/status":
            return self._send(200, {"session": ep.session, "pid": os.getpid(), "protocol": 1, "ready": ep.ready})
        if self.path != "/events":
            return self._send(404, {"error": "no route"})
        snap, q = ep.subscribe()
        if snap is None:
            return self._send(503, {"error": "not ready"})
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write((json.dumps(snap) + "\n").encode())
            self.wfile.flush()
            while True:
                e = q.get()
                if e is None or self.server.closing:
                    return
                self.wfile.write((json.dumps(e) + "\n").encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            with ep.lock:
                if q in ep.subscribers:
                    ep.subscribers.remove(q)
            self.close_connection = True


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    closing = False


class Message:
    """One model request of a loop, streamed chunk by chunk; `row` ends a
    block: its notice and its row, each when the test says."""

    def __init__(self, fake, agent, turn, step):
        self.fake, self.agent, self.turn, self.step = fake, agent, turn, step
        self.next_chunk = 0
        self.texts = {}
        fake.post([{"type": "step", "phase": "start", "turnId": turn, "agentId": agent, "step": step,
                    "model": "m", "t": 0}])

    def ids(self):
        return {"turnId": self.turn, "agentId": self.agent, "step": self.step}

    def text(self, index, text):
        self.texts[index] = self.texts.get(index, "") + text
        e = {"type": "chunk", **self.ids(), "chunkIndex": self.next_chunk,
             "chunk": {"kind": "text", "index": index, "text": text}, "t": 0}
        self.next_chunk += 1
        self.fake.post([e])

    def notice(self, index, uuid):
        self.fake.post([{"type": "block-row", "uuid": uuid, **self.ids(), "index": index, "t": 0}])

    def row(self, index, post=True, disk=True, uuid=None):
        """The block's row: its uuid; `post` sends its block-row, `disk` writes
        it (the notice first when both)."""
        uuid = uuid or str(uuidlib.uuid4())
        if post:
            self.notice(index, uuid)
        if disk:
            self.write(index, uuid)
        return uuid

    def write(self, index, uuid):
        self.fake.write_row(self.agent, {"type": "assistant", "uuid": uuid, "agentId": self.agent,
                                         "message": {"role": "assistant",
                                                     "content": [{"type": "text", "text": self.texts.get(index, "")}]}})

    def end(self):
        self.fake.post([{"type": "step", "phase": "end", **self.ids(), "t": 0}])


class FakeSession:
    """The transcript files of one session under $HOME/.claude/projects, and
    its endpoint under $SMINOS_HOME/bridge."""

    def __init__(self, home, sminos_home, session, project_dir="proj"):
        self.home, self.sminos_home, self.session = home, sminos_home, session
        self.dir = os.path.join(home, ".claude", "projects", project_dir)
        os.makedirs(self.dir, exist_ok=True)
        self.endpoint = None
        self.server = None
        self.turns = 0

    # -------------------------------------------------- the transcript

    def path(self, agent=None):
        if agent is None:
            return os.path.join(self.dir, self.session + ".jsonl")
        return os.path.join(self.dir, self.session, "subagents", "agent-%s.jsonl" % agent)

    def write_row(self, agent, row):
        p = self.path(agent)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(row) + "\n")

    def write_partial(self, agent, text):
        """Bytes of a row the engine has not finished writing (no line feed)."""
        with open(self.path(agent), "a") as f:
            f.write(text)

    def meta(self, agent, meta):
        p = os.path.join(self.dir, self.session, "subagents", "agent-%s.meta.json" % agent)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(meta, f)

    def rows(self, agent=None):
        try:
            with open(self.path(agent)) as f:
                return [json.loads(line) for line in f if line.endswith("\n") and line.strip()]
        except OSError:
            return []

    def user_row(self, text, agent=None, post=True, disk=True, uuid=None):
        uuid = uuid or str(uuidlib.uuid4())
        if post:
            self.post([{"type": "row-seen", "uuid": uuid, "agentId": agent, "door": "append", "t": 0}])
        if disk:
            self.write_row(agent, {"type": "user", "uuid": uuid, "agentId": agent,
                                   "message": {"role": "user", "content": text}})
        return uuid

    # -------------------------------------------------- the endpoint

    def start_bridge(self, ready=True):
        d = os.path.join(self.sminos_home, "bridge")
        os.makedirs(d, mode=0o700, exist_ok=True)
        path = os.path.join(d, self.session + ".sock")
        try:
            os.unlink(path)
        except OSError:
            pass
        self.endpoint = Endpoint(self.session)
        self.server = _Server(path, _Handler)
        self.server.endpoint = self.endpoint
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        if ready:
            self.endpoint.post([{"type": "resync", "t": 0}])
        return path

    def stop_bridge(self, unlink=True):
        if self.server is None:
            return
        self.server.closing = True
        self.endpoint.end_all()
        self.server.shutdown()
        self.server.server_close()
        if unlink:
            try:
                os.unlink(os.path.join(self.sminos_home, "bridge", self.session + ".sock"))
            except OSError:
                pass
        self.server = None

    def post(self, events):
        if self.endpoint is not None:
            self.endpoint.post(events)

    def resync(self):
        self.post([{"type": "resync", "t": 0}])

    def gap(self):
        self.post([{"type": "gap", "dropped": 3, "t": 0}])

    def message(self, agent=None, turn=None, step=0):
        if turn is None:
            self.turns += 1
            turn = "turn-%d" % self.turns
        return Message(self, agent, turn, step)

    def usage(self, tokens):
        self.post([{"type": "usage", "context": {"tokens": tokens, "window": 200000, "percent": tokens / 2000},
                    "cost": {"usd": 0.01}, "t": 0}])


def stalled_socket(path):
    """A socket at `path` that accepts and never answers: a bridge whose
    child hangs."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.listen(8)
    return s
