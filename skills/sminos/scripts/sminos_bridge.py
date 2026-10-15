"""The bridge's session endpoint and its local client (DC2, contract DX5).

`sminos bridge --session <id>` is the child the bridge mod
(hooks/mods/bridge.tsx) spawns for the life of a session. It serves the
session's endpoint, HTTP over the Unix socket $SMINOS_HOME/bridge/<id>.sock
in an owner-only directory:

    GET  /status          who serves here: session, pid, protocol, the mod's last word
    POST /events          the mod's events, a JSON array in the order they happened
    GET  /events          a subscription: one snapshot line, then every event, numbered n from 1
    POST /command[?wait=ms]  a command for the mod: relayed as one line on stdout

The mod reads the child's stdout line by line: first `{"op": "hello", ...}`
once the socket answers, then one JSON object per command, `id` first. It
answers a command with a `result` event carrying the same id, which the child
hands back to the client that waited for it. The socket answering is the
bridge-presence signal; a socket file nobody answers is stale, and whoever
finds it removes it (remove_stale). A newer child for the session takes the
path over (a module reload spawns one before the old one is gone), and the
older one, finding the path no longer its own, exits without removing it.

`sminos watch <member>` subscribes and prints the stream: the conversation as
it streams, subagents labelled; `--json`, the lines as they come.
"""

import http.client
import json
import os
import queue
import signal
import socket
import socketserver
import sys
import threading
import time
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import sminos as S

PROTOCOL = 1
SOCKET_PATH_MAX = 103          # sun_path on macOS (104 with the NUL); Linux allows 107
BODY_MAX = 32 * 1024 * 1024
SUBSCRIBER_BACKLOG = 10000     # a subscriber this far behind is cut off and resubscribes
COMMAND_WAIT_MAX = 25000       # ms: under the 30 s an engine fetch waits
AGENTS_KEPT = 200
WATCHDOG_EVERY = 0.5


def bridge_dir():
    return os.path.join(S.root(), "bridge")


def endpoint(session):
    return os.path.join(bridge_dir(), session + ".sock")


# ------------------------------------------------------------------ the client


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("bridge", timeout=timeout)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def request(path, method, url, body=None, timeout=10):
    """One request to an endpoint: (status, parsed JSON or None). Raises
    OSError when nothing answers."""
    c = _UnixConnection(path, timeout)
    try:
        data = None if body is None else json.dumps(body).encode()
        c.request(method, url, body=data, headers={"content-type": "application/json"})
        r = c.getresponse()
        text = r.read().decode()
        try:
            return r.status, json.loads(text) if text else None
        except ValueError:
            return r.status, None
    finally:
        c.close()


def probe(path):
    """The endpoint's /status when a bridge answers there, else None."""
    try:
        status, body = request(path, "GET", "/status", timeout=3)
    except (OSError, http.client.HTTPException):
        return None
    return body if status == 200 and isinstance(body, dict) else None


def remove_stale(path):
    """Removes a socket file nobody listens on, and only that file: the inode
    is read before the connect and checked again before the unlink, so a
    child that moved its socket into place meanwhile keeps it."""
    try:
        before = os.lstat(path).st_ino
    except OSError:
        return
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(path)
        return  # someone listens: not stale
    except OSError:
        pass
    finally:
        s.close()
    try:
        if os.lstat(path).st_ino == before:
            os.unlink(path)
    except OSError:
        pass


def subscribe(path):
    """The endpoint's stream: yields each line, parsed, until it ends. Raises
    OSError when nothing answers."""
    c = _UnixConnection(path, timeout=None)
    try:
        c.request("GET", "/events")
        r = c.getresponse()
        if r.status != 200:
            raise OSError("the bridge refused the subscription (%d)" % r.status)
        while True:
            line = r.readline()
            if not line:
                return
            line = line.strip()
            if line:
                yield json.loads(line)
    finally:
        c.close()


# ------------------------------------------------------------------ the child


def _key(e):
    return "%s|%s|%s" % (e.get("turnId"), e.get("agentId"), e.get("step"))


class Bridge:
    """The session's live state as the mod's events build it, and the
    subscribers and command waiters it serves. One lock: an event is applied
    and handed to every subscriber in one step, and a snapshot is taken and a
    subscriber added in one step, so a subscriber misses nothing and sees
    nothing twice (subscribe before snapshot, DX4)."""

    def __init__(self, session, sock):
        self.session = session
        self.socket = sock
        self.started = time.time()
        self.lock = threading.Lock()
        self.out_lock = threading.Lock()
        self.subscribers = set()
        self.streaming = {}      # turnId|agentId|step → the message as streamed so far
        self.broken = set()      # messages a chunk was missing from: left out until a resync
        self.turns = {}          # turnId → the open turn
        self.agents = {}         # agentId → what its spawn said, and whether it runs
        self.session_info = None
        self.usage = None
        self.mod_events = 0
        self.mod_last = None
        self.waiters = {}        # command id → [threading.Event, result event]
        self.closing = threading.Event()

    # -- the mod's events

    def ingest(self, events):
        with self.lock:
            self.mod_events += len(events)
            self.mod_last = time.time()
            for e in events:
                self._apply(e)
                for sub in list(self.subscribers):
                    try:
                        sub.put_nowait(e)
                    except queue.Full:   # its writer drains the backlog, then ends it
                        self.subscribers.discard(sub)
                        sub.cut = True

    def _apply(self, e):
        kind, phase = e.get("type"), e.get("phase")
        if kind == "chunk":
            # A message's text is only ever whole up to its upTo: a chunk that
            # does not follow the last one (a post lost, a start missed) takes
            # the message out of the snapshot until the mod's resync.
            k = _key(e)
            m = self.streaming.get(k)
            index = e.get("chunkIndex")
            if k in self.broken:
                return
            if m is None and index == 0:
                m = self.streaming[k] = {"turnId": e.get("turnId"), "agentId": e.get("agentId"),
                                         "step": e.get("step"), "text": "", "thinking": "", "upTo": -1}
            if m is None or index != m["upTo"] + 1:
                self.streaming.pop(k, None)
                self.broken.add(k)
                return
            chunk = e.get("chunk") or {}
            if chunk.get("kind") == "text":
                m["text"] += str(chunk.get("text") or "")
            elif chunk.get("kind") == "thinking":
                m["thinking"] += str(chunk.get("text") or "")
            m["upTo"] = index
        elif kind == "resync":
            # The mod's own copy of the live state, whole: it replaces this one.
            self.turns = {t.get("turnId"): dict(t) for t in e.get("turns") or []}
            self.streaming = {_key(m): dict(m) for m in e.get("streaming") or []}
            self.agents = {a.get("agentId"): dict(a) for a in e.get("agents") or []}
            self.broken = set()
        elif kind == "step" and phase == "start":
            self.broken.discard(_key(e))
            self.streaming[_key(e)] = {"turnId": e.get("turnId"), "agentId": e.get("agentId"), "step": e.get("step"),
                                       "model": e.get("model"), "text": "", "thinking": "", "upTo": -1}
        elif kind == "step" and phase == "end":
            self.streaming.pop(_key(e), None)
            self.broken.discard(_key(e))
        elif kind == "turn" and phase == "start":
            self.turns[e.get("turnId")] = {"turnId": e.get("turnId"), "agentId": e.get("agentId"), "t": e.get("t")}
        elif kind == "turn" and phase == "complete":
            self.turns.pop(e.get("turnId"), None)
            for k in [k for k, m in self.streaming.items() if m["turnId"] == e.get("turnId")]:
                del self.streaming[k]
            self.broken = {k for k in self.broken if not k.startswith("%s|" % e.get("turnId"))}
        elif kind == "agent":
            a = self.agents.setdefault(e.get("agentId"), {"agentId": e.get("agentId")})
            a.update({k: v for k, v in e.items() if k not in ("type", "phase", "n")})
            a["running"] = phase != "stop"
            if len(self.agents) > AGENTS_KEPT:
                done = [k for k, v in self.agents.items() if not v["running"]]
                for k in done[:len(self.agents) - AGENTS_KEPT]:
                    del self.agents[k]
        elif kind == "session" and phase == "start":
            self.session_info = {k: v for k, v in e.items() if k not in ("type", "phase")}
        elif kind == "session":
            self.session_info = {**(self.session_info or {}), "ended": e.get("reason")}
        elif kind == "usage":
            self.usage = dict(e)
        elif kind == "result":
            w = self.waiters.get(e.get("id"))
            if w is not None:
                w[1] = e
                w[0].set()

    def snapshot(self):
        return {"type": "snapshot", "session": self.session, "protocol": PROTOCOL, "pid": os.getpid(),
                "sessionInfo": self.session_info, "turns": list(self.turns.values()),
                "streaming": [dict(m) for m in self.streaming.values()],
                "agents": list(self.agents.values()), "usage": self.usage,
                # Reserved for M3: the requests pending in the session, and the
                # ones settled recently, so a late subscriber sees a request
                # settled rather than still raised.
                "pending": [], "settled": []}

    def subscribe(self):
        q = queue.Queue(SUBSCRIBER_BACKLOG)
        q.cut = False
        with self.lock:
            snap = self.snapshot()
            self.subscribers.add(q)
        return snap, q

    def unsubscribe(self, q):
        with self.lock:
            self.subscribers.discard(q)

    def status(self):
        with self.lock:
            return {"session": self.session, "pid": os.getpid(), "protocol": PROTOCOL, "socket": self.socket,
                    "started": self.started, "subscribers": len(self.subscribers),
                    "mod": {"events": self.mod_events, "last": self.mod_last}}

    # -- the mod's input: one line on stdout

    def emit(self, obj):
        data = (json.dumps(obj) + "\n").encode()
        with self.out_lock:
            try:
                while data:
                    data = data[os.write(1, data):]
            except OSError:   # the mod is gone: so is the session
                self.closing.set()
                raise

    def command(self, body, wait_ms):
        cid = uuidlib.uuid4().hex
        line = {"id": cid, **{k: v for k, v in body.items() if k != "id"}}
        w = [threading.Event(), None]
        if wait_ms > 0:
            with self.lock:
                self.waiters[cid] = w
        try:
            self.emit(line)
            self.ingest([{"type": "command", "id": cid, "op": body["op"], "t": int(time.time() * 1000)}])
            if wait_ms <= 0:
                return 202, {"id": cid, "status": "sent"}
            if not w[0].wait(wait_ms / 1000.0):
                return 504, {"id": cid, "error": "the session did not answer within %d ms" % wait_ms}
            r = w[1]
            out = {"id": cid, "ok": bool(r.get("ok"))}
            for k in ("result", "error"):
                if k in r:
                    out[k] = r[k]
            return 200, out
        finally:
            with self.lock:
                self.waiters.pop(cid, None)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "sminos-bridge/%d" % PROTOCOL

    def log_message(self, *_args):
        pass

    def address_string(self):
        return "local"

    def _send(self, status, body=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > BODY_MAX:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"null")

    def do_GET(self):
        bridge = self.server.bridge
        route = urlparse(self.path).path
        if route == "/status":
            return self._send(200, bridge.status())
        if route == "/events":
            return self._stream(bridge)
        return self._send(404, {"error": "no route %s" % route})

    def do_POST(self):
        bridge = self.server.bridge
        url = urlparse(self.path)
        try:
            body = self._body()
        except ValueError as e:
            return self._send(400, {"error": "the body is not JSON: %s" % e})
        if url.path == "/events":
            events = body if isinstance(body, list) else [body]
            if not all(isinstance(e, dict) and isinstance(e.get("type"), str) for e in events):
                return self._send(400, {"error": "each event is an object with a type"})
            bridge.ingest(events)
            return self._send(204)
        if url.path == "/command":
            if not isinstance(body, dict) or not isinstance(body.get("op"), str) or not body["op"] \
                    or body["op"] == "hello":
                return self._send(400, {"error": "a command is an object with an op (not hello)"})
            try:
                wait = int((parse_qs(url.query).get("wait") or ["0"])[0])
            except ValueError:
                return self._send(400, {"error": "wait is milliseconds"})
            try:
                status, out = bridge.command(body, max(0, min(wait, COMMAND_WAIT_MAX)))
            except OSError:
                return self._send(503, {"error": "the session is gone"})
            return self._send(status, out)
        return self._send(404, {"error": "no route %s" % url.path})

    def _stream(self, bridge):
        """Close-delimited NDJSON: the snapshot line, then each event with its
        n. A subscriber that falls SUBSCRIBER_BACKLOG events behind is cut off;
        it subscribes again for a fresh snapshot (DX4's rule on a gap)."""
        snap, q = bridge.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write((json.dumps(snap) + "\n").encode())
            self.wfile.flush()
            n = 0
            while not bridge.closing.is_set():
                try:
                    e = q.get(timeout=1)
                except queue.Empty:
                    if q.cut:
                        return
                    continue
                n += 1
                self.wfile.write((json.dumps({"n": n, **e}) + "\n").encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            bridge.unsubscribe(q)
            self.close_connection = True


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        # A client that hung up mid-answer (a watcher closed, a session that
        # ended mid-post) is no error of the bridge's.
        if isinstance(sys.exc_info()[1], OSError):
            return
        super().handle_error(request, client_address)


def serve(session):
    """The child's life: bind beside the endpoint, listen, move the socket
    into place (so the path never names a socket nobody listens on yet), say
    hello, serve until the parent (the session) is gone, the path is another
    child's, or a signal; then remove the socket if it is still this child's."""
    path = endpoint(session)
    if len(path.encode()) > SOCKET_PATH_MAX:
        S.die("the endpoint's path is too long for a Unix socket (%d bytes, at most %d): %s — "
              "a shorter SMINOS_HOME fixes it" % (len(path.encode()), SOCKET_PATH_MAX, path), 1)
    d = bridge_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    tmp = os.path.join(d, ".%s.%d.sock" % (session[:8], os.getpid()))
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    server = _Server(tmp, _Handler, bind_and_activate=False)
    server.server_bind()
    os.chmod(tmp, 0o600)
    server.server_activate()
    # This child's identity is its own socket's inode, read before the move:
    # read after it, a newer child that moved its socket in meanwhile would
    # pass for this one, which would then take its path at exit.
    mine = os.lstat(tmp).st_ino
    os.replace(tmp, path)
    bridge = server.bridge = Bridge(session, path)
    parent = os.getppid()

    def watchdog():
        while not bridge.closing.wait(WATCHDOG_EVERY):
            try:
                ours = os.lstat(path).st_ino == mine
            except OSError:
                ours = False
            if os.getppid() != parent or not ours:
                bridge.closing.set()
        server.shutdown()

    def on_signal(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)
    try:
        bridge.emit({"op": "hello", "session": session, "pid": os.getpid(), "socket": path, "protocol": PROTOCOL})
        threading.Thread(target=watchdog, daemon=True).start()
        server.serve_forever(poll_interval=0.25)
    except (OSError, KeyboardInterrupt):
        pass
    finally:
        bridge.closing.set()
        try:
            if os.lstat(path).st_ino == mine:
                os.unlink(path)
        except OSError:
            pass
        server.server_close()


def cmd_bridge(a):
    if not S.UUID_RE.match(a.session or ""):
        S.die("bridge: %r is not a session id" % (a.session or ""))
    serve(a.session)


# ------------------------------------------------------------------ watch


def watch_session(q):
    """The session a member name names here, or exit 4 saying why not. A full
    session id is taken as given."""
    if S.UUID_RE.match(q):
        return q
    target = S.find_target(q)
    if target[0] == "none":
        S.die("no member matching '%s'" % q, S.EXIT_UNKNOWN)
    if target[0] == "seat":
        s = target[1]
        session = target[2] or s.get("current") or ""
        if not session:
            S.die("%s/%s holds no session" % (s["group"], s["alias"]), S.EXIT_UNKNOWN)
        return session
    m = target[2]
    if not m.local:
        S.die("%s runs on %s; its bridge is that machine's" % (q, m.machine or "another machine"), S.EXIT_UNKNOWN)
    return m.session


def _first_line(text, width=160):
    line = str(text or "").strip().split("\n", 1)[0]
    return line if len(line) <= width else line[:width - 1] + "…"


def _tool_summary(tool, value):
    if isinstance(value, dict):
        for k in ("command", "file_path", "path", "pattern", "url", "query", "description", "prompt"):
            if isinstance(value.get(k), str) and value[k]:
                return _first_line(value[k], 120)
        return _first_line(json.dumps(value, ensure_ascii=False), 120)
    return ""


class Renderer:
    """The stream as a person reads it: text as it streams under its loop's
    label, one line for each thing that happened between."""

    def __init__(self, out):
        self.out = out
        self.at_start = True
        self.source = None
        self.thinking = set()
        self.labels = {}

    def label(self, agent):
        if agent is None:
            return "main"
        return self.labels.get(agent) or "agent %s" % str(agent)[:12]

    def write(self, text):
        self.out.write(text)
        self.out.flush()
        if text:
            self.at_start = text.endswith("\n")

    def line(self, text):
        if not self.at_start:
            self.write("\n")
        self.source = None
        self.write(text + "\n")

    def stream(self, key, agent, text):
        if self.source != key:
            if not self.at_start:
                self.write("\n")
            self.write("[%s] " % self.label(agent))
            self.source = key
        self.write(text)

    def feed(self, e):
        kind, phase, agent = e.get("type"), e.get("phase"), e.get("agentId")
        if kind == "snapshot":
            for a in e.get("agents") or []:
                self._name(a)
            self.line("· watching session %s (bridge pid %s)" % (e.get("session"), e.get("pid")))
            for m in e.get("streaming") or []:
                if m.get("text"):
                    self.stream(_key(m), m.get("agentId"), m["text"])
        elif kind == "chunk":
            chunk = e.get("chunk") or {}
            if chunk.get("kind") == "text" and chunk.get("text"):
                self.stream(_key(e), agent, chunk["text"])
            elif chunk.get("kind") == "thinking" and (_key(e), chunk.get("index")) not in self.thinking:
                self.thinking.add((_key(e), chunk.get("index")))
                self.line("· [%s] thinking…" % self.label(agent))
        elif kind == "turn" and phase == "start":
            if agent is None:
                self.line("» %s" % (_first_line(e.get("text")) or "(a turn with no prompt)"))
            else:
                self.line("· [%s] turn started" % self.label(agent))
        elif kind == "turn" and phase == "complete":
            self.line("· [%s] turn ended: %s" % (self.label(agent), e.get("reason")))
        elif kind == "tool" and phase == "call":
            self.line("· [%s] %s %s" % (self.label(agent), e.get("tool"), _tool_summary(e.get("tool"), e.get("input"))))
        elif kind == "tool" and phase == "result" and (e.get("isError") or e.get("denied")):
            self.line("  ⎿ [%s] %s failed: %s" % (self.label(agent), e.get("tool"),
                                                  _first_line(e.get("denied") or e.get("text"))))
        elif kind == "agent" and phase == "spawn":
            self._name(e)
            self.line("· agent %s started: %s" % (self.label(agent), _first_line(e.get("description"), 100)))
        elif kind == "agent" and phase == "stop":
            self.line("· agent %s stopped" % self.label(agent))
        elif kind == "session":
            if phase == "start":
                self.line("· session started · %s" % (e.get("model") or "?"))
            else:
                self.line("· session ended (%s)" % e.get("reason"))
        elif kind == "usage":
            c = e.get("context") or {}
            if c.get("tokens") is not None and c.get("window"):
                self.line("· context %s of %s tokens" % (format(c["tokens"], ","), format(c["window"], ",")))
        elif kind == "result":
            self.line("· %s → %s" % (e.get("op"), "ok" if e.get("ok") else "refused: %s" % e.get("error")))
        elif kind == "gap":
            self.line("· %s events were lost on the way from the session" % e.get("dropped"))

    def _name(self, a):
        if a.get("agentId"):
            self.labels[a["agentId"]] = "%s %s" % (a.get("subagentType") or "agent", str(a["agentId"])[:12])


def _reconnect_window():
    try:
        return float(os.environ.get("SMINOS_BRIDGE_RECONNECT") or 5)
    except ValueError:
        return 5.0


def cmd_watch(a):
    session = watch_session(a.member)
    path = endpoint(session)
    if probe(path) is None:
        remove_stale(path)
        S.die("%s has no bridge on this machine (no session endpoint answers at %s)" % (a.member, path),
              S.EXIT_UNKNOWN)
    render = None if a.json else Renderer(sys.stdout)

    def show(e):
        if render is None:
            sys.stdout.write(json.dumps(e) + "\n")
            sys.stdout.flush()
        else:
            render.feed(e)

    def say(text):
        (render.line if render else lambda t: sys.stderr.write(t + "\n"))(text)

    ended = False
    try:
        while True:
            lost = False
            try:
                for e in subscribe(path):
                    show(e)
                    if e.get("type") == "session" and e.get("phase") == "end" and e.get("reason") != "clear":
                        ended = True
                    # What was printed misses the lost events: a fresh snapshot
                    # (DX4's rule on a gap) prints each message whole again.
                    # --json passes the gap and its resync on to its reader.
                    if e.get("type") == "gap" and render is not None:
                        lost = True
                        break
            except (OSError, http.client.HTTPException, ValueError):
                pass
            if ended:
                say("· the session ended")
                return
            if lost and probe(path) is not None:
                continue
            deadline = time.time() + _reconnect_window()
            while time.time() < deadline and probe(path) is None:
                time.sleep(0.1)
            if probe(path) is None:
                remove_stale(path)
                say("· the bridge ended")
                sys.exit(1)
            say("· the bridge restarted; reconnected")
    except KeyboardInterrupt:
        return
