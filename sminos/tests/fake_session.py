"""A scripted session for the session plane's tests (DC7 M1): the engine's
transcript on disk and the bridge's DX5 endpoint, each moved by the test's
own hand, so that a row can reach disk ahead of its notice, a notice ahead of
its row, a chunk arrive while a snapshot is built, and a module reload end a
subscription — the orders the real engine and mod produce, and the ones
they produce only rarely.

The scripted endpoint follows the real child as DC2's M4 built it (DX5's M4
extension in DC2's plan, reviewed clean at f0242560):

- every row the mod observes gets one notice on the ordered stream once the
  append resolves — a row's notice follows its flush by default, and may
  come before it when the test says: `block-row` for a response row whose
  block streamed, `row-seen` for any other;
- the mod's first resync carries each loop's cut seeded with its last row on
  disk when the module loaded (the hello's `seed`); `null`, or a loop it does
  not name, means the loop had no rows then; a request begun before the
  module loaded never streams, and its rows are named by `row-seen`;
- a block-row names its block, which stays in `streaming` with its text,
  its row's `uuid` and `namedAt`, and takes no chunk more (the desk
  open-fast spec's section 2);
- a step's end follows its block-rows; once it is out the step's pairing is
  closed (a later row of it is named by `row-seen`), and its whole message
  leaves `streaming`, as a turn's end takes the turn's messages;
- the snapshot carries `cut`, the last notice applied per loop (`"main"` or
  the agent id), under the lock that applies chunks and block-rows;
- a `resync` replaces what streams with the mod's own copy (a block the
  mod named kept with its uuid, an unnamed copy of a settled one gone, the
  text so far of one still streaming kept);
- `GET /status` says `ready` once the mod's first `resync` is applied, and
  `GET /events` holds until then (at most 5 s, else 503); it carries the
  `capabilities` the last resync did (the desk control surface's DX5);
- `POST /command` answers the desk's `read` as the mod does (`status`, and
  "no read <what>" else); `silent` is a mod that never answered (504),
  `slow` one that answers after `Endpoint.hold` seconds;
- a later `resync`, or a subscriber BACKLOG events behind, ends a
  subscription.

The same FakeSession drives the real child (`sminos bridge --session`) in
place of the script with `start_bridge(real=True)`: this process is then its
mod, posting under the hello's nonce, its first resync carrying the hello's
seed.

    session = FakeSession(home, sminos_home, session_id)
    session.start_bridge()                 # the endpoint, $SMINOS_HOME/bridge/<id>.sock
    m = session.message(agent=None)        # a model request of the main loop
    m.text(0, "Hello, ")                   # a chunk of block 0
    u = m.row(0, post=True, disk=True)     # its row, then its notice
    session.user_row("ok")                 # the row, then its row-seen
"""

import http.client
import json
import os
import queue
import socket
import socketserver
import subprocess
import threading
import time
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler

READY_HOLD = 5.0
# `read status`'s answer, as the mod's (DX5).
STATUS = {"version": {"version": "2.1.307", "base": "2.1.307"}, "model": "claude-opus-5-5", "cwd": "/w", "root": "/w",
          "repo": None, "surfaces": ["terminal"], "override": None}
# What a bridge at MW1 answers `read mcp` with: the servers whose tools the model has.
MCP = {"exact": False, "servers": [{"name": "probe_server", "status": "connected", "tools": 2}]}
BACKLOG = 10000       # a subscriber this far behind is cut off, as the child cuts it off
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SMINOS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts", "sminos")


class Endpoint:
    """The child's state as DX5 has it, with M4's cut and readiness: one
    lock applies each event and fans it out, and takes a snapshot and adds a
    subscriber. `legacy`: a child from before the open-fast spec's M5, which
    drops a block at its block-row and declares nothing; otherwise its
    snapshot says `namedBlocks` as the mod's last resync declared it."""

    def __init__(self, session, legacy=False):
        self.session = session
        self.legacy = legacy
        self.named_blocks = False   # the mod's last resync declared it keeps named blocks
        self.lock = threading.Condition()
        self.streaming = {}   # (turnId, agentId, step) → {turnId, agentId, step, model, upTo, blocks: {index: block}, settled}
        self.cut = {}         # loop → uuid of the last notice applied
        self.usage = None
        self.agents = {}
        self.subscribers = []
        self.ready = False
        self.resyncs = 0
        self.sent = 0         # events fanned out
        self.capabilities = None   # the last resync's (DX5)
        self.launch = None         # the process's launch its module named (`--launch`, O12 M7)
        self.hold = 0.0       # s: how long a `slow` read is held

    def snapshot(self):
        return {"type": "snapshot", "session": self.session, "protocol": 1, "pid": os.getpid(),
                "sessionInfo": {"session": self.session}, "turns": [],
                "streaming": [{"turnId": m["turnId"], "agentId": m["agentId"], "step": m["step"], "model": m["model"],
                               "upTo": m["upTo"], "blocks": [dict(m["blocks"][i]) for i in sorted(m["blocks"])]}
                              for m in self.streaming.values()],
                "agents": list(self.agents.values()), "usage": self.usage, "override": None,
                "pending": [], "settled": [], "cut": dict(self.cut),
                **({} if self.legacy else {"namedBlocks": self.named_blocks})}

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
            self.capabilities = e.get("capabilities") if isinstance(e.get("capabilities"), dict) else None
            self.cut = {k: v for k, v in (e.get("cut") or {}).items() if v}
            self.agents = {a.get("agentId"): dict(a) for a in e.get("agents") or []}
            self.named_blocks = e.get("namedBlocks") is True
            # The mod's own copy of what streams replaces this one, as the
            # child's resync does: a block the mod named is kept with its
            # uuid; an unnamed copy of a block either side settled is gone.
            streaming = {}
            for m in e.get("streaming") or []:
                key = (m["turnId"], m["agentId"], m["step"])
                settled = set(m.get("settled") or []) | (self.streaming.get(key) or {}).get("settled", set())
                streaming[key] = {
                    "turnId": m["turnId"], "agentId": m["agentId"], "step": m["step"], "model": m.get("model"),
                    "upTo": m.get("upTo", -1), "settled": settled,
                    "blocks": {b["index"]: dict(b) for b in m.get("blocks") or []
                               if b["index"] not in settled or (isinstance(b.get("uuid"), str) and not self.legacy)}}
            self.streaming = streaming
            if self.resyncs > 1:
                for q in self.subscribers:
                    q.put(None)
                self.subscribers = []
            self.lock.notify_all()
            return
        key = (e.get("turnId"), e.get("agentId"), e.get("step"))
        if kind == "step":
            if e["phase"] == "start":
                self.streaming[key] = {"turnId": key[0], "agentId": key[1], "step": key[2], "model": e.get("model"),
                                       "upTo": -1, "blocks": {}, "settled": set()}
            else:
                self.streaming.pop(key, None)
        elif kind == "turn" and e.get("phase") == "complete":
            for k in [k for k in self.streaming if k[0] == e.get("turnId")]:
                del self.streaming[k]
        elif kind == "chunk":
            m = self.streaming[key]
            c = e["chunk"]
            m["upTo"] = e["chunkIndex"]
            if c["index"] not in m["settled"]:
                b = m["blocks"].setdefault(c["index"], {"index": c["index"], "kind": c["kind"], "text": "", "upTo": -1})
                b["text"] += c.get("text", "")
                b["upTo"] = e["chunkIndex"]
        elif kind == "block-row":
            m = self.streaming.get(key)
            if m is not None:
                m["settled"].add(e["index"])
                if self.legacy:
                    m["blocks"].pop(e["index"], None)
                elif e["index"] in m["blocks"]:
                    m["blocks"][e["index"]].update(uuid=e["uuid"], namedAt=e.get("t"))
            self.cut[loop] = e["uuid"]
        elif kind == "row-seen":
            self.cut[loop] = e["uuid"]
        elif kind == "usage":
            self.usage = dict(e)
        elif kind == "agent":
            # As the child keeps it: what the spawn said, and whether it runs.
            a = self.agents.setdefault(e["agentId"], {"agentId": e["agentId"]})
            a.update({k: v for k, v in e.items() if k not in ("type", "phase", "n")})
            a["running"] = e["phase"] != "stop"
        self.sent += 1
        for q in list(self.subscribers):
            if q.qsize() >= BACKLOG:
                self.subscribers.remove(q)
                q.put(None)
            else:
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

    def command(self, body):
        """POST /command: (status, answer), as the child answers for its mod."""
        if body.get("op") != "read":
            return 200, {"id": "c0", "ok": False, "error": "unknown op: %s" % body.get("op")}
        what = body.get("what")
        if what == "silent":
            return 504, {"id": "c0", "error": "the session did not answer within 10000 ms"}
        if what == "slow":
            time.sleep(self.hold)
            return 200, {"id": "c0", "ok": True, "result": {"slow": True}}
        if what == "status":
            return 200, {"id": "c0", "ok": True, "result": STATUS}
        if what == "mcp":
            return 200, {"id": "c0", "ok": True, "result": MCP}
        return 200, {"id": "c0", "ok": False, "error": "no read %s" % what}

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
        try:
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass   # the client gave up first (a probe's short timeout): as the stream below, nothing to say
        self.close_connection = True

    def do_GET(self):
        ep = self.server.endpoint
        if self.path == "/status":
            return self._send(200, {"session": ep.session, "pid": os.getpid(), "protocol": 1, "ready": ep.ready,
                                    **({"launch": ep.launch} if ep.launch is not None else {}),
                                    **({"capabilities": ep.capabilities} if ep.capabilities is not None else {})})
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


    def do_POST(self):
        if not self.path.startswith("/command"):
            return self._send(404, {"error": "no route"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        return self._send(*self.server.endpoint.command(body))


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    closing = False


class RealChild:
    """The real child, `sminos bridge --session <id>`, spawned as the mod
    spawns it; this process is its mod. Its hello's `seed` is each loop's
    last row on disk as it read them."""

    def __init__(self, session, env=None):
        self.proc = subprocess.Popen([SMINOS, "bridge", "--session", session], stdout=subprocess.PIPE, text=True,
                                     env={**os.environ, **(env or {})})
        hello = json.loads(self.proc.stdout.readline())
        self.sock, self.nonce, self.seed = hello["socket"], hello["nonce"], hello.get("seed") or {}

    def post(self, events):
        class Conn(http.client.HTTPConnection):
            def connect(conn):
                conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.sock.settimeout(10)
                conn.sock.connect(self.sock)

        c = Conn("bridge")
        try:
            c.request("POST", "/events", json.dumps(events), {"X-Bridge-Nonce": self.nonce,
                                                              "Content-Type": "application/json"})
            status = c.getresponse().status
        finally:
            c.close()
        assert status == 204, "the child answered a post %d" % status

    def stop(self):
        self.proc.kill()
        self.proc.wait()
        self.proc.stdout.close()


class Message:
    """One model request of a loop, streamed chunk by chunk; `row` ends a
    block: its row and its notice, each when the test says. A request begun
    while no module was loaded, or under an earlier one, never streams (the
    seed rule): its chunks reach no child and its rows are named by
    `row-seen`. Once its step's end is out, its pairing is closed: a later
    row of it is named by `row-seen` too. Its start carries `model` and
    `effort` as the mod's does (the effort null when the request named
    none)."""

    def __init__(self, fake, agent, turn, step, model="m", effort=None):
        self.fake, self.agent, self.turn, self.step, self.model = fake, agent, turn, step, model
        self.module = fake.module
        self.ended = False
        self.next_chunk = 0
        self.texts = {}
        self.up_to = {}       # block index → its last chunk
        self.settled = set()  # blocks whose block-row the mod posted
        self.named = {}       # block index → (the row's uuid, the notice's stamp), as the mod marks the block
        fake.messages.append(self)
        self.post([{"type": "step", "phase": "start", "turnId": turn, "agentId": agent, "step": step,
                    "model": model, "effort": effort, "t": 0}])

    def streams(self):
        return self.module is not None and self.module is self.fake.module

    def post(self, events):
        if self.streams():
            self.fake.post(events)

    def ids(self):
        return {"turnId": self.turn, "agentId": self.agent, "step": self.step}

    def text(self, index, text):
        self.texts[index] = self.texts.get(index, "") + text
        self.up_to[index] = self.next_chunk
        e = {"type": "chunk", **self.ids(), "chunkIndex": self.next_chunk,
             "chunk": {"kind": "text", "index": index, "text": text}, "t": 1760000000000 + self.next_chunk}
        self.next_chunk += 1
        self.post([e])

    def notice(self, index, uuid, lost=False):
        """The row's notice; `lost`: posted, and dropped by a gap before the
        child applied it (the mod's own copy moves, the child's does not)."""
        if self.streams() and not self.ended:
            self.settled.add(index)
            at = int(time.time() * 1000)
            if index in self.texts:
                self.named[index] = (uuid, at)
            e = {"type": "block-row", "uuid": uuid, **self.ids(), "index": index, "t": at}
        else:
            e = {"type": "row-seen", "uuid": uuid, "agentId": self.agent, "door": "append", "t": 0}
        (self.fake.lose if lost else self.fake.post)([e])

    def row(self, index, post=True, disk=True, uuid=None, lost=False):
        """The block's row: its uuid; `disk` writes it, then `post` sends its
        block-row (the notice trails the flush, as the producer posts it once
        the engine has taken the row), which a gap takes when `lost`."""
        uuid = uuid or str(uuidlib.uuid4())
        if disk:
            self.write(index, uuid)
        if post or lost:
            self.notice(index, uuid, lost)
        return uuid

    def live(self):
        """Whether the mod still streams this request (its resync names it)."""
        return self.streams() and not self.ended

    def entry(self):
        """The request as the mod's resync carries it: its blocks' text so
        far, a named one with its row's uuid (none for a mod from before the
        open-fast spec's M5, `legacy`: it dropped them), and the blocks it
        settled."""
        named = {} if self.fake.legacy else self.named

        def block(i, t):
            b = {"index": i, "kind": "text", "text": t, "upTo": self.up_to[i]}
            if i in named:
                b.update(uuid=named[i][0], namedAt=named[i][1])
            return b
        return {**self.ids(), "model": self.model, "upTo": self.next_chunk - 1,
                "blocks": [block(i, t) for i, t in sorted(self.texts.items()) if i not in self.settled or i in named],
                "settled": sorted(self.settled)}

    def write(self, index, uuid):
        self.fake.write_row(self.agent, {"type": "assistant", "uuid": uuid, "agentId": self.agent,
                                         "message": {"role": "assistant",
                                                     "content": [{"type": "text", "text": self.texts.get(index, "")}]}})

    def end(self, t=0):
        """The step's end, stamped `t` (None: unstamped)."""
        self.post([{"type": "step", "phase": "end", **self.ids(), "stopReason": None, "usage": None,
                    **({} if t is None else {"t": t})}])
        self.ended = True

    def turn_complete(self, reason="aborted", t=0):
        """The turn ends, stamped `t` (None: unstamped); a step whose end
        never came is cut off with it."""
        self.post([{"type": "turn", "phase": "complete", "turnId": self.turn, "agentId": self.agent,
                    "reason": reason, "usage": None, **({} if t is None else {"t": t})}])
        self.ended = True


class FakeSession:
    """The transcript files of one session under $HOME/.claude/projects, and
    its endpoint under $SMINOS_HOME/bridge."""

    def __init__(self, home, sminos_home, session, project_dir="proj"):
        self.home, self.sminos_home, self.session = home, sminos_home, session
        self.dir = os.path.join(home, ".claude", "projects", project_dir)
        os.makedirs(self.dir, exist_ok=True)
        self.endpoint = None  # the scripted endpoint, while it serves
        self.server = None
        self.child = None     # or the real child
        self.module = None    # the module instance now loaded: what a Message streams under
        self.cut = {}         # the mod's own copy of each loop's cut, which its resyncs carry
        self.messages = []    # every request begun: the ones still streaming are in a resync
        self.agents = []      # the mod's agent state (the $.agent.list() seed included), which its resyncs carry
        self.turns = 0
        self.emitted = []     # every event the mod posted, lost or not: an inventory's DX5 source

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
        if disk:
            self.write_row(agent, {"type": "user", "uuid": uuid, "agentId": agent,
                                   "message": {"role": "user", "content": text}})
        if post:
            self.seen(uuid, agent)
        return uuid

    def seen(self, uuid, agent=None):
        """A row-seen notice for a row the engine took."""
        self.post([{"type": "row-seen", "uuid": uuid, "agentId": agent, "door": "append", "t": 0}])

    def seed(self):
        """Each loop's last whole row on disk (the child's hello `seed`)."""
        loops = {"main": self.path(None)}
        sub = os.path.join(self.dir, self.session, "subagents")
        for name in (os.listdir(sub) if os.path.isdir(sub) else []):
            if name.startswith("agent-") and name.endswith(".jsonl"):
                loops[name[len("agent-"):-len(".jsonl")]] = os.path.join(sub, name)
        out = {}
        for loop, p in loops.items():
            try:
                with open(p) as f:
                    rows = [json.loads(line) for line in f if line.endswith("\n") and line.strip()]
            except OSError:
                continue
            uuids = [r["uuid"] for r in rows if isinstance(r, dict) and r.get("uuid")]
            if uuids:
                out[loop] = uuids[-1]
        return out

    # -------------------------------------------------- the endpoint

    real = False          # start_bridge spawns the real child, not the script
    capabilities = None   # what the mod's resyncs say it can do (DX5): none, as a mod from before sminos 1.7.0
    launch = None         # the process's launch the scripted child says (O12 M7): none, as a mod from before it
    mode = None           # the mode fields the mod's resyncs carry (permissionMode, …At, …From): none, as before a report
    legacy = False        # the mod (and the scripted child) from before the open-fast spec's M5: named blocks dropped, nothing declared
    child_env = None

    def start_bridge(self, ready=True, real=None, env=None):
        """A module loads: the scripted endpoint (or the real child) at the
        session's path; its first resync, unless `ready` is false, carries
        each loop's cut seeded with the last row on disk."""
        real = self.real if real is None else real
        env = env if env is not None else self.child_env
        d = os.path.join(self.sminos_home, "bridge")
        os.makedirs(d, mode=0o700, exist_ok=True)
        path = os.path.join(d, self.session + ".sock")
        if real:
            self.child = self.module = RealChild(self.session, env)
            seed = self.child.seed
        else:
            try:
                os.unlink(path)
            except OSError:
                pass
            self.endpoint = self.module = Endpoint(self.session, legacy=self.legacy)
            self.endpoint.launch = self.launch
            self.server = _Server(path, _Handler)
            self.server.endpoint = self.endpoint
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            seed = self.seed()
        self.cut = dict(seed)
        if real:
            self.post([{"type": "session", "phase": "start", "session": self.session, "cwd": self.dir, "t": 0}])
        if ready:
            self.resync()
        return path

    def stop_bridge(self, unlink=True):
        """The module unloads (the child goes with it)."""
        self.module = None
        if self.child is not None:
            self.child.stop()
            self.child = None
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
        self.endpoint = None

    def kill_child(self):
        """The child dies on its own (killed): its socket stays at the path,
        nobody listening on it, and the module stays loaded, so what it
        posts meanwhile reaches no child."""
        if self.child is not None:
            self.child.stop()   # SIGKILL: the real child removes nothing
            self.child = None
            return
        self.server.closing = True
        self.endpoint.end_all()
        self.server.shutdown()
        self.server.server_close()   # the socket file stays
        self.server = None
        self.endpoint = None

    def respawn_child(self):
        """The module spawns the dead child's successor, as the mod does at
        once: it moves its own socket into place over the stale one, then the
        same module's start and resync (whatever it still streams) make it
        ready."""
        if self.real:
            self.child = RealChild(self.session, self.child_env)
            self.post([{"type": "session", "phase": "start", "session": self.session, "cwd": self.dir, "t": 0}])
        else:
            d = os.path.join(self.sminos_home, "bridge")
            tmp = os.path.join(d, ".%s.next.sock" % self.session[:8])
            self.endpoint = Endpoint(self.session, legacy=self.legacy)
            self.endpoint.launch = self.launch
            self.server = _Server(tmp, _Handler)
            self.server.endpoint = self.endpoint
            os.replace(tmp, os.path.join(d, self.session + ".sock"))
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.resync()

    def post(self, events):
        self.lose(events)
        if self.child is not None:
            self.child.post(events)
        elif self.endpoint is not None:
            self.endpoint.post(events)

    def lose(self, events):
        """Events the mod posted: its own copy moves. Alone, a gap took them
        before the child applied them."""
        self.emitted += events
        for e in events:
            if e.get("type") in ("block-row", "row-seen"):
                self.cut[e.get("agentId") or "main"] = e["uuid"]

    def resync(self):
        """The mod's whole state again (a gap's sequel, or a child's first
        post): what still streams under this module, and its cut."""
        streaming = [m.entry() for m in self.messages if m.live()]
        self.post([{"type": "resync", "turns": [], "streaming": streaming, "agents": [dict(a) for a in self.agents],
                    "cut": dict(self.cut), **({} if self.legacy else {"namedBlocks": True}),
                    **({"capabilities": self.capabilities} if self.capabilities is not None else {}),
                    **(self.mode or {}), "t": 0}])

    def agent(self, phase, agent_id, **fields):
        """An `agent` spawn or stop event (DX5), as the mod posts it."""
        self.post([{"type": "agent", "phase": phase, "agentId": agent_id, "t": 0, **fields}])

    def gap(self):
        self.post([{"type": "gap", "dropped": 3, "t": 0}])

    def message(self, agent=None, turn=None, step=0, **start):
        if turn is None:
            self.turns += 1
            turn = "turn-%d" % self.turns
        return Message(self, agent, turn, step, **start)

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
