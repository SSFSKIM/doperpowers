#!/usr/bin/env python3
"""Live check of the lane B observer (O12 M4a): the bridge's gate client and
the mod's fence in a real `claude -p`, against a private stand-in of MAWS's
engine host and a scripted stand-in of the Messages API.

What only a running engine shows, pinned so a release that breaks it fails
loudly:
- with no prompt (zero inference): the gate's hello names the engine session,
  claude's pid and the bridge child's pid; the welcome is taken and `hb` goes
  at once and every 5 s; a host that replaces its socket gets a fresh hello
  after the 5 s backoff; a bridge child killed outright is replaced by one
  whose hello keeps the session and claude's pid and names its own; M3's
  refused controls stand (`lane-b`);
- against the stub (no inference): query, cron, task and peer main turns
  are told to the host as `turn` with their origin before their request (an
  arm meeting a reloaded module's unknown turn state is told `unknown`); a
  `proceed` lets exactly one request through, a `stop` makes none; an arm
  that meets a running main turn sends its `turn` before its `armed`, a
  subagent's requests are never fenced, and later main steps ask again; every
  renewal gets its own `armed`, in order; a fence installed before a child's
  replacement still holds the next request;
- the held wait (decisions C1): an arm of 10 s answered by no `turn` holds
  the request until its lease and the margin (about 15 s from the arm), past
  the engine's 10 s own-time hook budget, and the plugin stays loaded;
- evidence, not gates: what the request and the host see when the bridge
  child dies under a hold (once, and in a crash loop), and the stream-json
  frame order of engine-initiated turns (cron, task, peer) up to their first
  model request (C2), beside a stdin-driven one and MAWS's p4 fixture.

The gate stand-in is this process: a Unix socket speaking OX10 (O16
Interfaces §E; the fixture `sminos/tests/p5-o16-gate.jsonl`) at production
timings, which launches the native engine itself, so `SMNS_MEMBER` is its own
pid and the session is a marked lane B process. The Messages API stand-in is
a Python equivalent of MAWS's `spikes/protocol-probe/stub-api.mjs` (read at
MAWS master 2342f11da): every request recorded and answered by a content-keyed
script, nothing spent and no key needed (`ANTHROPIC_AUTH_TOKEN` is a dummy).

No suite runs it: run it by hand at a milestone, with Python 3.10+ (it puts
its own interpreter first on the engine's PATH). Everything it starts is
isolated: a temporary HOME whose .claude is the session's config dir, a
temporary SMINOS_HOME, a scratch sminos project, a copy of the worktree's
plugin loaded with --plugin-dir, the engine's environment built from nothing.
One engine runs at a time, and every process it started is stopped at the end.

    sminos/tests/mods/live-observer-check.py [--keep]     # --keep: leave the temp dir
"""

import datetime
import http.server
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

ENGINE = os.path.realpath(os.path.expanduser("~/.local/bin/claude"))
NAME = "obslive"
LEASE_MS = 10_000            # OX10's production lease
OBSERVER_MARGIN_S = 5.0      # the observer's fallback past a lease
BACKOFF_S = 5.0              # the observer's reconnect backoff
HEARTBEAT_S = 5.0
STOP_REASON = "The holder ended this session; reopening it continues the conversation."
MAWS_REVISION = "2342f11da"  # the MAWS master stub-api.mjs and the p4 fixture were read at
# MAWS spikes/protocol-probe/fixtures/p4/p4-a2p-stub-full.jsonl (at MAWS_REVISION): a stdin-driven turn, frame by frame.
P4_ORDER = ["user (stdin)", "system/session_state_changed:running", "command_lifecycle", "command_lifecycle",
            "system/init", "system/status:requesting", "user (replay)", "assistant"]


def now():
    return time.monotonic()


# -- the Messages API stand-in (stub-api.mjs, in Python)

def text_turn(text):
    return {"blocks": [{"type": "text", "text": text}], "stop": "end_turn"}


def tool_turn(name, payload, text=None):
    return {"blocks": ([{"type": "text", "text": text}] if text else []) + [{"type": "tool_use", "name": name, "input": payload}],
            "stop": "tool_use"}


def sse_of(turn, msg_id, model):
    def ev(kind, data):
        return "event: %s\ndata: %s\n\n" % (kind, json.dumps({"type": kind, **data}))
    out = ev("message_start", {"message": {"id": msg_id, "type": "message", "role": "assistant", "model": model, "content": [],
                                           "stop_reason": None, "stop_sequence": None,
                                           "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0,
                                                     "cache_read_input_tokens": 0}}})
    for i, b in enumerate(turn["blocks"]):
        if b["type"] == "text":
            out += ev("content_block_start", {"index": i, "content_block": {"type": "text", "text": ""}})
            out += ev("content_block_delta", {"index": i, "delta": {"type": "text_delta", "text": b["text"]}})
        else:
            out += ev("content_block_start", {"index": i, "content_block": {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
            out += ev("content_block_delta", {"index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}})
        out += ev("content_block_stop", {"index": i})
    out += ev("message_delta", {"delta": {"stop_reason": turn["stop"], "stop_sequence": None}, "usage": {"output_tokens": 1}})
    return out + ev("message_stop", {})


def one_shot_cron(at=None):
    """A one-shot cron at the first whole minute at least 70 s away (the engine runs under TZ=UTC), as O16 M0's probe."""
    t = datetime.datetime.fromtimestamp((at or time.time()) + 70, datetime.timezone.utc).replace(second=0, microsecond=0)
    t += datetime.timedelta(minutes=1)
    return "%d %d %d %d *" % (t.minute, t.hour, t.day, t.month), t.timestamp()


def _blocks(m):
    if not isinstance(m, dict) or m.get("role") != "user":
        return []
    c = m.get("content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])


def _text(blocks):
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class Stub:
    """Every POST /v1/messages recorded (`requests`) and answered by the plan
    a `[[T3:<PLAN>]]` marker in the last user message names, a tool_result
    continuing the plan of the tool_use it answers, a task notification
    answered as one; a request with no loop tools is a side request. A
    request whose conversation opens with the subagent's marker is the
    subagent's, not the main loop's."""

    def __init__(self):
        self.requests = []
        self.cond = threading.Condition()
        self.issued = {}
        self.n = 0
        self.cron_at = None

    def plan(self, name, step, names):
        agent = "Agent" if "Agent" in names else "Task"
        if name == "QUERY":
            return [lambda: (tool_turn(agent, {"description": "Sleep briefly", "subagent_type": "general-purpose",
                                               "run_in_background": False,
                                               "prompt": "[[T3:SUBTASK]] Run the sleep, then say so."}), 1),
                    lambda: (text_turn("Query done."), 2)][step]()
        if name == "SUBTASK":
            return [lambda: (tool_turn("Bash", {"command": "sleep 5", "description": "t3 subagent sleep"}), 1),
                    lambda: (text_turn("Sub done."), 2)][step]()
        if name == "NOTE":
            return [lambda: (tool_turn("Bash", {"command": "sleep 6", "description": "t3 background sleep",
                                                "run_in_background": True}), 1),
                    lambda: (text_turn("Started."), 2)][step]()
        if name == "CRON":
            if step == 0 and "CronCreate" not in names:
                return tool_turn("ToolSearch", {"query": "select:CronCreate", "max_results": 1}), 1
            if step <= 1:
                cron, self.cron_at = one_shot_cron()
                return tool_turn("CronCreate", {"cron": cron, "prompt": "[[T3:FIRE]] one-shot job", "recurring": False}), 2
            return text_turn("Scheduled."), 3
        return text_turn({"FIRE": "Fired.", "NOTIFIED": "Noted.", "PEER": "Got it."}.get(name, "OK.")), None

    def answer(self, body):
        tools = body.get("tools") or []
        names = [t.get("name") for t in tools if isinstance(t, dict)]
        msgs = body.get("messages") or []
        if not any(n in ("Bash", "Read") for n in names):
            return {"kind": "side"}, text_turn("ok")
        first = _text(_blocks(msgs[0])) if msgs else ""
        kind = "sub" if "[[T3:SUBTASK]]" in first else "main"
        last = next((_blocks(m) for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "user"), [])
        text = _text(last)
        prior = next((self.issued[b.get("tool_use_id")] for b in last
                      if b.get("type") == "tool_result" and b.get("tool_use_id") in self.issued), None)
        marks = [m.split("]]")[0] for m in text.split("[[T3:")[1:]]
        if prior is not None and prior[1] is not None:
            plan, step = prior[0], prior[1]
        elif marks:
            plan, step = marks[-1], 0
        elif "task-notification" in text or "<task-id>" in text:
            plan, step = "NOTIFIED", 0
        else:
            plan, step = "UNSCRIPTED", 0
        turn, after = self.plan(plan, step, names)
        for b in turn["blocks"]:
            if b["type"] == "tool_use":
                self.n += 1
                b["id"] = "toolu_t3_%03d" % self.n
                self.issued[b["id"]] = (plan, after)
        return {"kind": kind, "plan": plan, "step": step, "head": text[:160], "messages": len(msgs),
                "tools": sorted(n for n in names if n)}, turn

    def start(self):
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def _record(self, entry):
                with stub.cond:
                    entry.update(n=len(stub.requests) + 1, t=now(), at=datetime.datetime.now(datetime.timezone.utc).isoformat())
                    stub.requests.append(entry)
                    stub.cond.notify_all()

            def _send(self, status, ctype, data):
                self.send_response(status)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length") or 0))
                path = self.path.split("?")[0]
                if path == "/v1/messages/count_tokens":
                    self._record({"path": path, "kind": "count"})
                    return self._send(200, "application/json", b'{"input_tokens":1000}')
                if path != "/v1/messages":
                    self._record({"path": path, "kind": "other", "status": 404})
                    return self._send(404, "application/json", b'{"type":"error","error":{"type":"not_found_error","message":"stub"}}')
                body = json.loads(raw or b"{}")
                with stub.cond:
                    why, turn = stub.answer(body)
                self._record({"path": path, **why})
                msg_id = "msg_t3_%d" % len(stub.requests)
                if body.get("stream"):
                    return self._send(200, "text/event-stream", sse_of(turn, msg_id, body.get("model") or "stub").encode())
                return self._send(200, "application/json", json.dumps({
                    "id": msg_id, "type": "message", "role": "assistant", "model": body.get("model") or "stub",
                    "content": turn["blocks"], "stop_reason": turn["stop"], "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1}}).encode())

            def do_GET(self):
                self._record({"path": self.path, "kind": "other", "method": "GET", "status": 404})
                self._send(404, "application/json", b"{}")

            do_HEAD = do_GET

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def mark(self):
        with self.cond:
            return len(self.requests)

    def since(self, mark, kind=None, plan=None):
        with self.cond:
            return [r for r in self.requests[mark:] if (kind is None or r.get("kind") == kind)
                    and (plan is None or r.get("plan") == plan)]

    def wait(self, what, seconds, mark, kind="main", plan=None):
        deadline = now() + seconds
        with self.cond:
            while True:
                got = [r for r in self.requests[mark:] if r.get("kind") == kind and (plan is None or r.get("plan") == plan)]
                if got:
                    return got[0]
                left = deadline - now()
                if left <= 0:
                    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))
                self.cond.wait(min(left, 0.5))

    def close(self):
        self.server.shutdown()
        self.server.server_close()


# -- the engine host's gate, standing in

class Gate:
    """OX10's host side on a Unix socket of its own: every frame each way
    recorded with its time and connection; each hello welcomed at once; each
    `turn` answered as `policy` says for its fence (`proceed`: proceed then
    disarm, as a host that cancels its reap; `stop`: stop with the reason;
    else held, unanswered)."""

    def __init__(self, path):
        self.path = path
        self.cond = threading.Condition()
        self.events = []
        self.conns = {}
        self.n = 0
        self.current = None
        self.listener = None
        self.policy = {}

    def note(self, conn, direction, frame):
        with self.cond:
            self.events.append({"t": now(), "conn": conn, "dir": direction, "frame": frame})
            self.cond.notify_all()

    def listen(self):
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.path)
        os.chmod(self.path, 0o600)
        s.listen(8)
        self.listener = s
        threading.Thread(target=self._accept, args=(s,), daemon=True).start()
        self.note(None, "meta", {"listen": True})

    def replace(self):
        """The host replaced: its socket closed and every connection with it, a new one listening at the same path."""
        self.note(None, "meta", {"replace": True})
        old, self.listener = self.listener, None
        old.close()
        with self.cond:
            conns, self.conns, self.current = dict(self.conns), {}, None
        for c in conns.values():
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()
        self.listen()

    def _accept(self, s):
        while True:
            try:
                c, _ = s.accept()
            except OSError:
                return
            with self.cond:
                self.n += 1
                n = self.n
                self.conns[n] = c
            self.note(n, "meta", {"accept": n})
            threading.Thread(target=self._read, args=(n, c), daemon=True).start()

    def _read(self, n, c):
        buf = b""
        while True:
            try:
                chunk = c.recv(65536)
            except OSError:
                chunk = b""
            if not chunk:
                self.note(n, "meta", {"closed": n})
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    frame = json.loads(line)
                except ValueError:
                    self.note(n, "meta", {"unparsable": line[:200].decode(errors="replace")})
                    continue
                self.note(n, "in", frame)
                self._react(n, frame)

    def _react(self, n, frame):
        t = frame.get("t")
        if t == "hello":
            with self.cond:
                self.current = n
            self.send({"t": "welcome", "protocol": 1}, n)
        elif t == "turn":
            policy = self.policy.get(frame.get("fence"))
            if policy == "proceed":
                self.send({"t": "proceed", "fence": frame["fence"]}, n)
                self.send({"t": "disarm", "fence": frame["fence"]}, n)
            elif policy == "stop":
                self.send({"t": "stop", "fence": frame["fence"], "reason": STOP_REASON}, n)

    def send(self, frame, n=None):
        with self.cond:
            n = self.current if n is None else n
            c = self.conns.get(n)
        if c is None:
            raise RuntimeError("no gate connection to send %s on" % frame)
        c.sendall((json.dumps(frame) + "\n").encode())
        self.note(n, "out", frame)
        return now()

    def mark(self):
        with self.cond:
            return len(self.events)

    def find(self, pred, since=0):
        with self.cond:
            return [e for e in self.events[since:] if pred(e)]

    def wait(self, what, seconds, pred, since=0):
        deadline = now() + seconds
        with self.cond:
            while True:
                got = [e for e in self.events[since:] if pred(e)]
                if got:
                    return got[0]
                left = deadline - now()
                if left <= 0:
                    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))
                self.cond.wait(min(left, 0.5))


def is_in(t, **fields):
    return lambda e: e["dir"] == "in" and e["frame"].get("t") == t and all(e["frame"].get(k) == v for k, v in fields.items())


def is_meta(key):
    return lambda e: e["dir"] == "meta" and key in e["frame"]


def frame_line(e, t0):
    tag = {"in": "observer→host", "out": "host→observer", "meta": "host"}[e["dir"]]
    return "%+8.3f s  conn %s  %s %s" % (e["t"] - t0, e["conn"], tag, json.dumps(e["frame"]))


# -- the engine

class Engine:
    """One `claude -p` reading stream-json on a pipe and writing it, each
    frame it writes recorded with its time."""

    def __init__(self):
        self.proc = None
        self.frames = []
        self.cond = threading.Condition()

    def start(self, argv, env, cwd, stderr):
        self.proc = subprocess.Popen(argv, env=env, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=stderr, bufsize=0)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in iter(self.proc.stdout.readline, b""):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            with self.cond:
                self.frames.append((now(), obj))
                self.cond.notify_all()

    def send(self, text):
        frame = {"type": "user", "message": {"role": "user", "content": text}}
        with self.cond:
            self.frames.append((now(), {"type": "__sent__", "text": text}))
        self.proc.stdin.write((json.dumps(frame) + "\n").encode())
        self.proc.stdin.flush()

    def mark(self):
        with self.cond:
            return len(self.frames)

    def wait(self, what, seconds, pred, since=0):
        deadline = now() + seconds
        with self.cond:
            while True:
                got = [(i, t, o) for i, (t, o) in enumerate(self.frames) if i >= since and pred(o)]
                if got:
                    return got[0]
                left = deadline - now()
                if left <= 0:
                    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))
                self.cond.wait(min(left, 0.5))


def is_result(o):
    return o.get("type") == "result"


def label(o):
    t = o.get("type")
    if t == "__sent__":
        return "user (stdin)"
    if t == "system":
        sub = o.get("subtype")
        extra = o.get("state") if sub == "session_state_changed" else o.get("status") if sub == "status" else None
        return "system/%s%s" % (sub, ":" + str(extra) if extra is not None else "")
    if t == "stream_event":
        return "stream_event/%s" % (o.get("event") or {}).get("type")
    if t == "user":
        return "user (replay)" if o.get("isReplay") else "user"
    return str(t)


# -- the check

class Observer:
    def __init__(self, keep):
        self.live = LB.Live(keep)
        self.root = self.live.root
        self.home, self.cfg, self.smh, self.work, self.plugin = (self.live.home, self.live.cfg, self.live.smh,
                                                                 self.live.work, self.live.plugin)
        self.gate = Gate(os.path.join(self.root, "gate.sock"))
        self.stub = Stub()
        self.engine = Engine()
        self.session = str(uuid.uuid4())
        self.results = []
        self.evidence = []
        self.fence = 0
        self.t0 = now()

    # -- reporting

    def check(self, name, ok, detail):
        self.results.append((name, bool(ok), detail))
        print("  %s %s — %s" % ("ok  " if ok else "FAIL", name, detail), flush=True)

    def note(self, name, lines):
        self.evidence.append((name, lines))
        print("  evidence: %s" % name, flush=True)
        for line in lines:
            print("      " + line, flush=True)

    # -- isolation

    def path(self):
        return ":".join([os.path.dirname(sys.executable), os.path.dirname(ENGINE), os.path.expanduser("~/.local/bin"),
                         "/usr/bin", "/bin", "/usr/sbin", "/sbin"])

    def local_env(self):
        env = {k: os.environ[k] for k in ("LANG", "USER", "LOGNAME", "TMPDIR") if k in os.environ}
        env.update(HOME=self.home, SMINOS_HOME=self.smh, CLAUDE_CONFIG_DIR=self.cfg, PATH=self.path(), SHELL="/bin/bash")
        return env

    def sminos(self):
        return os.path.join(self.plugin, "skills", "sminos", "scripts", "sminos")

    def cli(self, *args, timeout=60):
        return subprocess.run([self.sminos(), *args], cwd=self.work, env=self.local_env(), capture_output=True,
                              text=True, timeout=timeout)

    def setup(self, stub_url):
        os.makedirs(self.cfg)
        os.makedirs(self.smh, mode=0o700)
        os.makedirs(self.work)
        LB.stage(LB.PLUGIN_ROOT, self.plugin, LB.PLUGIN_PARTS)
        trusted = {"hasTrustDialogAccepted": True, "hasCompletedProjectOnboarding": True}
        with open(os.path.join(self.cfg, ".claude.json"), "w") as f:
            json.dump({"hasCompletedOnboarding": True,
                       "projects": {self.work: trusted, os.path.realpath(self.work): trusted}}, f)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash", "Agent", "Task", "ToolSearch", "CronCreate", "CronList"]}}, f)
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", self.work], check=True)
        r = self.cli("project", "init", "--name", NAME)
        if r.returncode != 0:
            raise RuntimeError("sminos project init: %s" % (r.stderr or r.stdout))
        env = self.local_env()
        env.update(TERM="dumb", TZ="UTC", ANTHROPIC_BASE_URL=stub_url, ANTHROPIC_AUTH_TOKEN="stub-token",
                   CLAUDE_CODE_ENABLE_FUNCTION_HOOKS="1", CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS="1",
                   DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", ENABLE_TOOL_SEARCH="true",
                   SMNS_MEMBER=str(os.getpid()), MAWS_LANE="B", MAWS_HOLDER_SOCKET=self.gate.path,
                   # A --plugin-dir is watched for changes (the module reload) only with this set.
                   CLAUDE_CODE_PLUGIN_DIR_WATCH="1")
        self.engine_env = env

    def launch(self):
        argv = [ENGINE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--include-partial-messages", "--replay-user-messages", "--include-hook-events",
                "--model", "haiku", "--setting-sources", "user,project,local", "--permission-mode", "default",
                "--session-id", self.session, "--plugin-dir", self.plugin,
                "--debug-file", os.path.join(self.root, "debug.log"), "-n", NAME]
        self.stderr = open(os.path.join(self.root, "engine.stderr"), "wb")
        self.engine.start(argv, self.engine_env, self.work, self.stderr)
        self.claude = self.engine.proc.pid

    # -- what the host reads of the process tree

    def bridges(self):
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
        rows = []
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and int(parts[1]) == self.claude and " bridge " in parts[2] and "--session" in parts[2]:
                rows.append((int(parts[0]), parts[2]))
        return rows

    def endpoint(self):
        return os.path.join(self.smh, "bridge", self.session + ".sock")

    def status(self):
        try:
            s, body = LB.request(self.endpoint(), "GET", "/status", timeout=3)
            return body if s == 200 else None
        except OSError:
            return None

    def registry(self):
        try:
            with open(os.path.join(self.cfg, "sessions", "%d.json" % self.claude)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    # -- the gate's moves

    def next_fence(self):
        self.fence += 1
        return self.fence

    def arm(self, fence, lease=LEASE_MS):
        return self.gate.send({"t": "arm", "fence": fence, "leaseMs": lease})

    def hello_after(self, mark, seconds=30):
        return self.gate.wait("a hello", seconds, is_in("hello"), mark)

    def armed(self, fence, mark, seconds=10):
        return self.gate.wait("armed {fence: %d}" % fence, seconds, is_in("armed", fence=fence), mark)

    def turn(self, fence, mark, seconds=30):
        return self.gate.wait("turn {fence: %d}" % fence, seconds, is_in("turn", fence=fence), mark)

    def result_after(self, mark, seconds=90):
        return self.engine.wait("the turn's result", seconds, is_result, mark)

    def prompt(self, plan, words=""):
        self.engine.send("[[T3:%s]] %s" % (plan, words or "Answer as scripted."))

    def order(self, since, until=None, gate_since=None, stub_since=None):
        """The engine's frames from `since` to its first assistant output
        (inclusive), with the stub's requests and the gate's frames put in by
        time: the C2 capture."""
        with self.engine.cond:
            frames = list(self.engine.frames[since:until])
        rows = [(t, "engine  " + label(o)) for t, o in frames]
        end = None
        for t, o in frames:
            if o.get("type") == "assistant" or (o.get("type") == "stream_event" and o.get("parent_tool_use_id") is None):
                end = t
                break
        if end is None:
            end = frames[-1][0] if frames else now()
        if stub_since is not None:
            rows += [(r["t"], "stub    request #%d %s (%s)" % (r["n"], r.get("kind"), r.get("plan", r.get("path"))))
                     for r in self.stub.since(stub_since) if r["t"] <= end + 0.001]
        if gate_since is not None:
            rows += [(e["t"], "gate    %s %s" % ({"in": "observer→host", "out": "host→observer"}[e["dir"]], json.dumps(e["frame"])))
                     for e in self.gate.find(lambda e: e["dir"] != "meta" and e["frame"].get("t") != "hb", gate_since)
                     if e["t"] <= end + 0.001]
        rows.sort(key=lambda r: r[0])
        start = rows[0][0] if rows else now()
        out, last, count = [], None, 0
        for t, text in [r for r in rows if r[0] <= end + 0.001]:
            if text == last and text.startswith("engine  stream_event"):
                count += 1
                out[-1] = "%+8.3f s  %s ×%d" % (t - start, text, count + 1)
                continue
            last, count = text, 0
            out.append("%+8.3f s  %s" % (t - start, text))
        labels = [r[1] for r in rows if r[0] <= end + 0.001 and r[1].startswith("engine")]
        return out, labels

    @staticmethod
    def precedes(labels):
        def first(pred):
            return next((i for i, x in enumerate(labels) if pred(x)), None)
        running = first(lambda x: x == "engine  system/session_state_changed:running")
        requesting = first(lambda x: x == "engine  system/status:requesting")
        output = first(lambda x: x.startswith("engine  stream_event") or x == "engine  assistant")
        return running, requesting, output

    # -- the run

    def run(self):
        url = self.stub.start()
        self.setup(url)
        self.gate.listen()
        self.launch()
        print("  engine %s (pid %d), session %s" % (ENGINE, self.claude, self.session), flush=True)
        self.zero_inference()
        self.with_stub()

    def zero_inference(self):
        g = self.gate
        hello = self.hello_after(0, 120)
        welcome = g.wait("the welcome", 5, lambda e: e["dir"] == "out" and e["frame"].get("t") == "welcome", 0)
        f = hello["frame"]
        bridges = wait_for("the bridge child in the process tree", 10, self.bridges)
        child = f.get("childPid")
        reg = self.registry()
        self.check("hello names the engine session, claude's pid and the bridge child's pid",
                   f.get("protocol") == 1 and f.get("session") == self.session and reg.get("sessionId") == self.session
                   and f.get("pid") == self.claude and [p for p, _ in bridges] == [child],
                   "hello %s; registry sessionId %s; claude pid %d; bridge child %s" % (
                       json.dumps(f), reg.get("sessionId"), self.claude, bridges))
        st = wait_for("the bridge's /status with the holder ready", 30,
                      lambda: (lambda s: s if s and (s.get("holder") or {}).get("ready") and (s.get("holder") or {}).get("epoch") else None)(self.status()))
        self.check("the child is welcomed: /status's holder is ready on an epoch",
                   st["holder"]["ready"] and st["holder"]["epoch"] and st.get("lane") == "match",
                   "holder %s, lane %s" % (st["holder"], st.get("lane")))
        beats = wait_for("four heartbeats", 25, lambda: (lambda hb: hb if len(hb) >= 4 else None)(
            g.find(lambda e: e["conn"] == hello["conn"] and e["dir"] == "in" and e["frame"].get("t") == "hb")))
        first = beats[0]["t"] - welcome["t"]
        gaps = [round(b["t"] - a["t"], 2) for a, b in zip(beats, beats[1:])]
        self.check("an hb at once on the welcome, then every 5 s",
                   first < 1.0 and all(4.7 <= x <= 5.6 for x in gaps),
                   "first hb %.3f s after the welcome; then %s s apart" % (first, gaps))

        # M3's refusals stand beside the gate.
        caps = st.get("capabilities") or {}
        controls = caps.get("controls") or {}
        refused = controls and all(v == {"available": False, "reason": "MAWS controls this session"} for v in controls.values())
        steer = self.cli("steer", self.session, "hello")
        self.check("M3's controls stay refused: every control 'MAWS controls this session', no ops, steer refused lane-b",
                   refused and caps.get("ops") == [] and steer.returncode != 0 and "lane-b" in (steer.stdout + steer.stderr),
                   "%d controls, ops %s; steer rc %d: %s" % (len(controls), caps.get("ops"), steer.returncode,
                                                             (steer.stdout + steer.stderr).strip()[:160]))

        # The host replaces its socket: a fresh hello after the backoff.
        m = g.mark()
        epoch = st["holder"]["epoch"]
        replaced = now()
        g.replace()
        again = self.hello_after(m, 30)
        st2 = wait_for("the new epoch", 10, lambda: (lambda s: s if s and (s.get("holder") or {}).get("epoch") not in (None, epoch) else None)(self.status()))
        delay = again["t"] - replaced
        self.check("a host that replaces its socket gets a fresh hello after the 5 s backoff",
                   BACKOFF_S <= delay <= BACKOFF_S + 2 and again["frame"] == f and again["conn"] != hello["conn"],
                   "hello %.3f s after the replacement, on connection %d, the same ids; epoch %s → %s" % (
                       delay, again["conn"], epoch, st2["holder"]["epoch"]))
        self.zero_requests = self.stub.since(0, kind=None)
        self.check("no model request with no prompt (zero inference so far)", not [r for r in self.zero_requests if r["path"] == "/v1/messages"],
                   "%d requests to the stub: %s" % (len(self.zero_requests), [r["path"] for r in self.zero_requests]))

        # The bridge child killed outright: the mod's next child says hello
        # with the same session and claude pid, and its own pid. A fence
        # installed first must outlive the replacement (shown with the stub).
        fence = self.next_fence()
        m = g.mark()
        self.kept_arm = self.arm(fence)
        self.armed(fence, m)
        killed = now()
        os.kill(child, signal.SIGKILL)
        fresh = self.hello_after(m, 30)
        new = fresh["frame"].get("childPid")
        bridges = wait_for("the new bridge child", 10, lambda: (lambda b: b if b and b[0][0] == new else None)(self.bridges()))
        self.check("a killed bridge child is replaced: the new hello keeps the session and claude's pid, with the new childPid",
                   fresh["frame"].get("session") == self.session and fresh["frame"].get("pid") == self.claude
                   and new not in (None, child) and [p for p, _ in bridges] == [new],
                   "killed %d; hello %.3f s later: %s; tree %s" % (child, fresh["t"] - killed, json.dumps(fresh["frame"]), bridges))
        self.kept_fence = fence
        self.kept_mark = m

    def with_stub(self):
        g, stub, eng = self.gate, self.stub, self.engine

        # A fence installed before the child's replacement still holds: the
        # next request waits for its lease and margin, and no `turn` can go
        # for it (its connection is gone).
        sm, gm, em = stub.mark(), g.mark(), eng.mark()
        self.prompt("PLAIN")
        req = stub.wait("the held request", 40, sm)
        self.result_after(em)
        held = req["t"] - self.kept_arm
        turns = g.find(is_in("turn"), gm)
        self.check("a fence installed before the child's replacement holds the next request until its lease and margin",
                   LEASE_MS / 1000 + OBSERVER_MARGIN_S - 0.3 <= held <= LEASE_MS / 1000 + OBSERVER_MARGIN_S + 2.5 and not turns,
                   "request %.3f s after the arm (fence %d of the killed child's epoch); turns on the new connection: %s" % (
                       held, self.kept_fence, [e["frame"] for e in turns]))

        self.query_turn()
        self.stop_turn()
        self.task_turn()
        self.peer_turn()
        self.cron_turn()
        self.unknown_turn()
        self.held_wait()
        self.no_child_route()

    def query_turn(self):
        """A query turn: arm idle, proceed lets its one request through; an
        arm while the main turn waits on a subagent tells the host the turn
        before its ack; the subagent's requests go unfenced; the main loop's
        next step asks again."""
        g, stub, eng = self.gate, self.stub, self.engine
        f1 = self.next_fence()
        gm, sm, em = g.mark(), stub.mark(), eng.mark()
        self.arm(f1)
        self.armed(f1, gm)
        g.policy[f1] = "proceed"
        self.prompt("QUERY")
        turn = self.turn(f1, gm)
        first = stub.wait("the query's first request", 20, sm)
        before = [r for r in stub.since(sm, "main") if r["t"] < turn["t"]]
        proceed = g.wait("proceed", 5, lambda e: e["dir"] == "out" and e["frame"].get("t") == "proceed" and e["frame"].get("fence") == f1, gm)
        self.check("a query turn: turn {origin: query} before its request, which goes once on proceed",
                   turn["frame"].get("origin") == "query" and not before and first["t"] >= proceed["t"]
                   and first.get("plan") == "QUERY" and first.get("step") == 0,
                   "turn %s; request #%d %.3f s after the proceed" % (json.dumps(turn["frame"]), first["n"], first["t"] - proceed["t"]))
        # The subagent sleeps: arm while the main loop waits on it.
        sub0 = stub.wait("the subagent's first request", 30, sm, kind="sub")
        time.sleep(1.0)
        f2 = self.next_fence()
        gm2, sm2 = g.mark(), stub.mark()
        self.arm(f2)
        t2 = self.turn(f2, gm2)
        a2 = self.armed(f2, gm2)
        self.check("an arm while a main turn runs (a subagent working) sends turn before armed",
                   t2["t"] <= a2["t"] and g.events.index(t2) < g.events.index(a2) and t2["frame"].get("origin") == "query",
                   "turn %s then armed, %.3f s apart" % (json.dumps(t2["frame"]), a2["t"] - t2["t"]))
        sub1 = stub.wait("the subagent's next request", 20, sm2, kind="sub")
        try:
            wait_for("step 1's turn", 10, lambda: len(g.find(is_in("turn", fence=f2), gm2)) >= 2)
        except TimeoutError:
            pass
        time.sleep(1.0)
        mains = stub.since(sm2, "main")
        turns2 = g.find(is_in("turn", fence=f2), gm2)
        self.check("the subagent's request goes while the fence holds, and the main loop's next step waits and asks again",
                   sub1 and not mains and len(turns2) == 2,
                   "subagent request #%d (and #%d before); main requests meanwhile %d; turn {fence %d} frames %d (one at the arm, one from step 1)" % (
                       sub1["n"], sub0["n"], len(mains), f2, len(turns2)))
        released = g.send({"t": "proceed", "fence": f2})
        g.send({"t": "disarm", "fence": f2})
        step1 = stub.wait("the main loop's step 1", 20, sm2)
        self.result_after(em)
        steps = stub.since(sm, "main")
        self.check("later main steps: step 1 goes on its proceed, the turn makes one request per step",
                   step1["t"] >= released and step1.get("step") == 1 and len(steps) == 2,
                   "step 1 request #%d %.3f s after the proceed; main requests in the turn: %s" % (
                       step1["n"], step1["t"] - released, [(r["n"], r["plan"], r["step"]) for r in steps]))
        lines, labels = self.order(em, gate_since=gm, stub_since=sm)
        self.stdin_order = (lines, labels)

    def stop_turn(self):
        g, stub, eng = self.gate, self.stub, self.engine
        f = self.next_fence()
        gm, sm, em = g.mark(), stub.mark(), eng.mark()
        self.arm(f)
        self.armed(f, gm)
        g.policy[f] = "stop"
        self.prompt("PLAIN")
        turn = self.turn(f, gm)
        _, _, result = self.result_after(em)
        time.sleep(2.0)
        g.send({"t": "disarm", "fence": f})
        self.check("stop: no model request; the turn ends with the reason as its text",
                   not stub.since(sm, "main") and result.get("result") == STOP_REASON and turn["frame"].get("origin") == "query",
                   "turn %s; main requests %d; result %s: %s" % (json.dumps(turn["frame"]), len(stub.since(sm, "main")),
                                                                   result.get("subtype"), json.dumps(result.get("result"))[:120]))

    def engine_turn(self, name, origin, trigger, plan, seconds, renew=False):
        """An engine-started turn: armed while idle (renewed every 8 s when
        `renew`, each renewal acknowledged), told as `turn {origin}`, let
        through by proceed with one request; its frame order captured."""
        g, stub, eng = self.gate, self.stub, self.engine
        f = self.next_fence()
        em = eng.mark()
        trigger()
        self.result_after(em, 90)
        gm, sm, em2 = g.mark(), stub.mark(), eng.mark()
        g.policy[f] = "proceed"
        arms = [self.arm(f)]
        self.armed(f, gm)
        deadline = now() + seconds
        turn = None
        while turn is None and now() < deadline:
            try:
                turn = self.turn(f, gm, seconds=min(8.0, deadline - now()))
            except TimeoutError:
                if renew:
                    arms.append(self.arm(f))
                else:
                    break
        if turn is None:
            self.check("a %s turn: turn {origin: %s} before its request, one request on proceed" % (name, origin), False,
                       "no turn {fence %d} within %ss" % (f, seconds))
            return
        req = stub.wait("the %s turn's request" % name, 20, sm, plan=plan)
        result = self.result_after(em2, 60)
        proceed = g.wait("proceed", 5, lambda e: e["dir"] == "out" and e["frame"].get("t") == "proceed" and e["frame"].get("fence") == f, gm)
        mains = stub.since(sm, "main")
        self.check("a %s turn: turn {origin: %s} before its request, one request on proceed" % (name, origin),
                   turn["frame"].get("origin") == origin and req["t"] >= proceed["t"] and len(mains) == 1,
                   "turn %s %.3f s after the last arm; request #%d (%s) %.3f s after the proceed; main requests %d" % (
                       json.dumps(turn["frame"]), turn["t"] - arms[-1], req["n"], req.get("head", "")[:60].replace("\n", " "),
                       req["t"] - proceed["t"], len(mains)))
        if renew:
            acks = g.find(is_in("armed", fence=f), gm)
            acked_before = [a for a in acks if a["t"] <= turn["t"]]
            self.check("every renewal of the %s turn's fence got its own armed, in order" % name,
                       len(acks) == len(arms) and len(acked_before) >= len(arms) - 1,
                       "%d arms (1 + %d renewals), %d armed" % (len(arms), len(arms) - 1, len(acks)))
        lines, labels = self.order(em2, until=None, gate_since=gm, stub_since=sm)
        running, requesting, output = self.precedes(labels)
        self.note("C2: the %s turn, engine-started, from the trigger's idle to its first assistant output" % name, lines + [
            "session_state_changed:running at %s, status:requesting at %s, first assistant output at %s (engine frame indices); "
            "running before requesting: %s; running before any assistant output: %s" % (
                running, requesting, output,
                running is not None and requesting is not None and running < requesting,
                running is not None and output is not None and running < output)])
        return result

    def task_turn(self):
        self.engine_turn("task", "task", lambda: self.prompt("NOTE"), "NOTIFIED", 30)

    def cron_turn(self):
        def schedule():
            self.prompt("CRON")
        self.engine_turn("cron", "cron", schedule, "FIRE", 200, renew=True)

    def peer_turn(self):
        def say():
            alias = None
            r = self.cli("list", "--json")
            try:
                rows = json.loads(r.stdout)
                rows = rows if isinstance(rows, list) else rows.get("members", [])
                alias = next((m.get("alias") for m in rows if m.get("session") == self.session), None)
            except ValueError:
                pass
            said = self.cli("say", "@%s [[T3:PEER]] a word from another session" % (alias or NAME))
            self.peer_said = (alias, said.returncode, (said.stdout + said.stderr).strip()[:200])
            # say's turn has no result of its own: the engine's peer turn is the one awaited.
        g, eng = self.gate, self.engine
        em = eng.mark()
        f = self.next_fence()
        gm, sm = g.mark(), self.stub.mark()
        g.policy[f] = "proceed"
        self.arm(f)
        self.armed(f, gm)
        say()
        try:
            turn = self.turn(f, gm, seconds=20)
        except TimeoutError:
            self.check("a peer turn: turn {origin: peer} before its request, one request on proceed", False,
                       "no turn after `sminos say` (%s)" % (self.peer_said,))
            return
        req = self.stub.wait("the peer turn's request", 20, sm, plan="PEER")
        self.result_after(em, 60)
        proceed = g.wait("proceed", 5, lambda e: e["dir"] == "out" and e["frame"].get("t") == "proceed" and e["frame"].get("fence") == f, gm)
        self.check("a peer turn: turn {origin: peer} before its request, one request on proceed",
                   turn["frame"].get("origin") == "peer" and req["t"] >= proceed["t"] and len(self.stub.since(sm, "main")) == 1,
                   "say %s; turn %s; request #%d %.3f s after the proceed" % (self.peer_said, json.dumps(turn["frame"]), req["n"],
                                                                              req["t"] - proceed["t"]))
        lines, labels = self.order(em, gate_since=gm, stub_since=sm)
        running, requesting, output = self.precedes(labels)
        self.note("C2: the peer turn (sminos say, refused as words in lane B and delivered to the inbox), from the say to its first assistant output",
                  lines + ["session_state_changed:running at %s, status:requesting at %s, first assistant output at %s; "
                           "running before requesting: %s; running before any assistant output: %s" % (
                               running, requesting, output,
                               running is not None and requesting is not None and running < requesting,
                               running is not None and output is not None and running < output)])

    def unknown_turn(self):
        """`unknown`, live: a reloaded module cannot know whether a main turn
        runs (on 2.1.316 the engine polls an idle --plugin-dir every 30 s,
        and a change made mid-turn was applied only once the turn ended, so
        a reload mid-turn cannot be staged here). An arm then tells the host a
        `turn {origin: unknown}` before its ack (the reap is cancelled, the
        safe side), until the module learns the session is idle; how long
        that takes is recorded."""
        g = self.gate
        gm = g.mark()
        old = self.bridges()
        touched = now()
        with open(os.path.join(self.plugin, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-observer-check: a change that reloads the module\n")
        hello = self.hello_after(gm, 75)
        self.check("a module reload: the new child's hello keeps session and pid with a new childPid",
                   hello["frame"].get("session") == self.session and hello["frame"].get("pid") == self.claude
                   and hello["frame"].get("childPid") not in [p for p, _ in old],
                   "hello %.3f s after the change; before %s; hello %s" % (hello["t"] - touched, [p for p, _ in old], json.dumps(hello["frame"])))
        f = self.next_fence()
        g.policy[f] = "proceed"
        gm2 = g.mark()
        self.arm(f)
        a = self.armed(f, gm2)
        turns = [e for e in g.find(is_in("turn", fence=f), gm2) if e["t"] <= a["t"]]
        self.check("an arm meeting the reloaded module's unknown turn state: turn {origin: unknown} before armed",
                   turns and turns[0]["frame"].get("origin") == "unknown",
                   "frames %s" % [e["frame"] for e in g.find(lambda e: e["dir"] != "meta" and e["frame"].get("t") != "hb", gm2)])
        # How long an idle session's arms keep being told a turn after the reload.
        lines, resolved = [], None
        deadline = now() + 40
        while now() < deadline:
            time.sleep(2.0)
            f = self.next_fence()
            g.policy[f] = "proceed"
            m = g.mark()
            self.arm(f)
            a = self.armed(f, m)
            told = [e["frame"] for e in g.find(is_in("turn", fence=f), m) if e["t"] <= a["t"]]
            lines.append("%+7.3f s after the reload's hello: arm {fence %d} → %s" % (a["t"] - hello["t"], f, told or "armed, no turn"))
            if not told:
                resolved = a["t"] - hello["t"]
                g.send({"t": "disarm", "fence": f})
                break
        lines.append("an idle arm stopped meeting an unknown turn state %s" % (
            "%.3f s after the reload's hello" % resolved if resolved is not None else "never within 40 s"))
        self.note("after a reload, an idle session's arms and the turns they were told", lines)
    def held_wait(self):
        """C1: an arm answered by no `turn` reply holds the request for its
        lease and the margin, at production timings, and the plugin stays."""
        g, stub, eng = self.gate, self.stub, self.engine
        f = self.next_fence()
        gm, sm, em = g.mark(), stub.mark(), eng.mark()
        armed_at = self.arm(f)
        self.armed(f, gm)
        self.prompt("PLAIN")
        turn = self.turn(f, gm)
        req = stub.wait("the held request", 30, sm)
        self.result_after(em, 30)
        held = req["t"] - armed_at
        self.check("C1: a 10 s arm with no answer holds the request until its lease and margin (≈15 s), past the 10 s hook budget",
                   LEASE_MS / 1000 + OBSERVER_MARGIN_S - 0.3 <= held <= LEASE_MS / 1000 + OBSERVER_MARGIN_S + 1.5,
                   "turn %s %.3f s after the arm; request %.3f s after the arm" % (json.dumps(turn["frame"]), turn["t"] - armed_at, held))
        g.send({"t": "disarm", "fence": f})
        # The plugin is still loaded: the bridge answers and a later turn fences.
        f2 = self.next_fence()
        g.policy[f2] = "proceed"
        gm2, sm2, em2 = g.mark(), stub.mark(), eng.mark()
        self.arm(f2)
        self.armed(f2, gm2)
        self.prompt("PLAIN")
        t2 = self.turn(f2, gm2)
        r2 = stub.wait("the next request", 20, sm2)
        self.result_after(em2)
        st = self.status()
        unloads = self.debug_lines()
        self.check("C1: the plugin stays loaded after the hold: the bridge answers and the next turn fences",
                   st is not None and t2["frame"].get("origin") == "query" and r2["t"] >= t2["t"] and not unloads,
                   "/status %s; turn %s; request #%d after it; debug lines naming an unload or overrun: %s" % (
                       "answers" if st else "silent", json.dumps(t2["frame"]), r2["n"], unloads[:3]))

    def no_child_route(self):
        """C1's edge, evidence: the bridge child dies while a request waits
        at a hold whose turn is sent and unanswered: once, then in a loop."""
        for variant, loop_s in (("killed once", 0.0), ("killed in a loop for 14 s", 14.0)):
            g, stub, eng = self.gate, self.stub, self.engine
            f = self.next_fence()
            gm, sm, em = g.mark(), stub.mark(), eng.mark()
            armed_at = self.arm(f)
            self.armed(f, gm)
            self.prompt("PLAIN")
            turn = self.turn(f, gm)
            time.sleep(2.0)
            kills = []
            first_kill = now()
            for pid, _ in self.bridges():
                os.kill(pid, signal.SIGKILL)
                kills.append((now(), pid))
            while now() - first_kill < loop_s:
                for pid, _ in self.bridges():
                    if pid not in [p for _, p in kills]:
                        os.kill(pid, signal.SIGKILL)
                        kills.append((now(), pid))
                time.sleep(0.02)
            try:
                req = stub.wait("the request", 40, sm)
            except TimeoutError:
                req = None
            try:
                self.result_after(em, 60)
            except TimeoutError:
                pass
            back = None
            try:
                back = wait_for("a bridge child back", 60, lambda: self.bridges() and self.status())
            except TimeoutError:
                pass
            lines = ["arm {fence %d, leaseMs %d} at +0.000 s; turn %s at %+.3f s" % (f, LEASE_MS, json.dumps(turn["frame"]), turn["t"] - armed_at)]
            lines += ["SIGKILL bridge child %d at %+.3f s" % (pid, t - armed_at) for t, pid in kills]
            lines.append("the stub saw the request start at %s" % ("%+.3f s (%.3f s after the first kill)" % (req["t"] - armed_at, req["t"] - first_kill) if req else "never (40 s)"))
            lines += ["gate: " + frame_line(e, armed_at) for e in g.find(lambda e: not (e["dir"] == "in" and e["frame"].get("t") == "hb"), gm)]
            hbs = g.find(is_in("hb"), gm)
            lines.append("gate: %d hb frames meanwhile (not listed)" % len(hbs))
            lines.append("afterwards: bridge %s; debug lines naming an unload or overrun: %s" % (
                "answers (child %s)" % back.get("pid") if back else "not back in 60 s", self.debug_lines()[:3]))
            self.note("C1 edge, the bridge child %s under a hold with its turn sent and unanswered" % variant, lines)
        # After it all, the plugin still fences a turn (or says it does not).
        try:
            f2 = self.next_fence()
            g.policy[f2] = "proceed"
            gm2, sm2, em2 = g.mark(), stub.mark(), eng.mark()
            wait_for("a welcomed connection", 30, lambda: self.status() and (self.status().get("holder") or {}).get("epoch"))
            self.arm(f2)
            self.armed(f2, gm2)
            self.prompt("PLAIN")
            t2 = self.turn(f2, gm2)
            stub.wait("the request", 20, sm2)
            self.result_after(em2)
            self.note("after the C1 edge runs", ["a later turn fences: %s, then its request" % json.dumps(t2["frame"])])
        except (TimeoutError, RuntimeError) as e:
            self.note("after the C1 edge runs", ["a later turn did not fence: %s" % e])

    def debug_lines(self):
        """The engine's debug lines saying a hook overran its budget or a plugin was unloaded for it."""
        words = ("was unloaded", "crashed the hooks worker", "ignored its signal", "overran")
        try:
            with open(os.path.join(self.root, "debug.log"), errors="replace") as f:
                return [l.strip()[:200] for l in f if any(w in l for w in words)]
        except OSError:
            return []

    # -- the record

    def versions(self):
        rev = subprocess.run(["git", "-C", LB.PLUGIN_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", LB.PLUGIN_ROOT, "status", "--porcelain", "--", "."], capture_output=True, text=True).stdout.strip()
        with open(os.path.join(LB.PLUGIN_ROOT, ".claude-plugin", "plugin.json")) as f:
            version = json.load(f)["version"]
        with open(os.path.join(LB.PLUGIN_ROOT, "tests", "p5-o16-gate.source.json")) as f:
            fixture = json.load(f)
        engine = subprocess.run([ENGINE, "--version"], capture_output=True, text=True).stdout.strip()
        init = next((o for _, o in self.engine.frames if o.get("type") == "system" and o.get("subtype") == "init"), {})
        return ["engine %s (%s); init frame claude_code_version %s" % (engine, ENGINE, init.get("claude_code_version")),
                "sminos plugin %s at doperpowers %s%s" % (version, rev, " (with uncommitted changes)" if dirty else ""),
                "gate fixture: MAWS %s %s (blob %s)" % (fixture["commit"], fixture["path"], fixture["blob"]),
                "stub: a Python equivalent of MAWS %s spikes/protocol-probe/stub-api.mjs, in this script" % MAWS_REVISION,
                "python %s (%s)" % (sys.version.split()[0], sys.executable)]

    def report_orders(self):
        if getattr(self, "stdin_order", None):
            lines, labels = self.stdin_order
            running, requesting, output = self.precedes(labels)
            self.note("C2: the stdin-driven query turn, for comparison", lines + [
                "running before requesting: %s; running before any assistant output: %s" % (
                    running is not None and requesting is not None and running < requesting,
                    running is not None and output is not None and running < output)])
        self.note("C2: MAWS %s p4-a2p-stub-full.jsonl, a stdin-driven turn (transcribed)" % MAWS_REVISION, P4_ORDER)

    def cleanup(self):
        p = self.engine.proc
        if p is not None and p.poll() is None:
            try:
                p.stdin.close()
            except OSError:
                pass
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        for pid, _ in self.bridges() if p is not None else []:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        self.stub.close()
        try:
            self.gate.listener and self.gate.listener.close()
        except OSError:
            pass
        try:
            wait_for("every process of the check to end", 20, lambda: not LB._strays(self.root))
        except TimeoutError:
            for pid in LB._strays(self.root):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        left = LB._strays(self.root)
        print("  cleanup: %s" % ("nothing left running" if not left else "STILL RUNNING: %s" % left), flush=True)
        if self.live.keep:
            print("  kept: %s" % self.root)
        else:
            import shutil
            shutil.rmtree(self.root, ignore_errors=True)


def main():
    if sys.version_info < (3, 10):
        sys.exit("live-observer-check: Python 3.10+ (sminos refuses older)")
    obs = Observer("--keep" in sys.argv[1:])
    print("live observer check (%s):" % obs.root, flush=True)
    try:
        obs.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        import traceback
        traceback.print_exc()
        obs.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
    finally:
        try:
            obs.report_orders()
            obs.note("versions", obs.versions())
        except Exception as e:  # noqa: BLE001
            print("  (versions not read: %s)" % e)
        obs.cleanup()
    failed = [r for r in obs.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(obs.results) - len(failed), len(obs.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
