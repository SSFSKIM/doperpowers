#!/usr/bin/env python3
"""bench_rig — what the open's instruments stand on (the desk open-fast
spec, docs/doperpowers/specs/2026-10-20-desk-open-fast-design.md, M2):
bench_open.py's runs and bench_scale.py's opens.

- The hubs: hub_standin.py (`Standin`), or the hub's own Worker on a local
  runtime from a MAWS worktree (`Local`: `pnpm --filter desk-hub local` with
  a state directory of its own and a free port, its stdout read and stamped
  as its request log), each with its browser client: the stand-in's
  `/control/send` and stamped `sessions` (`StandinBrowser`), or the
  project's socket on the local hub (`LocalBrowser`, ws_client).
- The sessions: fake_session.py's scripted one or a synthetic transcript
  (`FakeKind`, `synthetic_transcript`), or an isolated headless live one
  (`LiveKind`, mods/live-bridge-check.py's Live) with a probe subscription
  on its bridge from the start.
- The machine (`Rig`): a temporary HOME and SMINOS_HOME (a live session's
  own), the enrollment, the project, and this checkout's uplink, run under
  a bootstrap (`python3 bench_rig.py _uplink <scripts> <tee>`) that tees
  each subscription's first bridge lines, its sub beside them, from the
  plane's reader thread (`install_tee`, read back by `read_tees`): the
  plane's code wrapped, not changed.
"""

import base64
import collections
import glob
import http.client
import importlib.util
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid as uuidlib

HERE = os.path.dirname(os.path.realpath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts")
SMINOS = os.path.join(SCRIPTS, "sminos")
sys.path.insert(0, HERE)

KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"   # the stand-in's org key: bytes(range(32)), base64url
BASE_KEYS = ("PATH", "TERM", "LANG", "USER", "LOGNAME", "SHELL", "TMPDIR")
TEE_LINES = 3          # bridge lines teed per subscription: its snapshot, and what follows to place it


# ------------------------------------------------------------- the uplink's bootstrap


def install_tee(P, path):
    """Each subscription's first TEE_LINES bridge lines, with its sub and
    their arrival, appended to `path` from the reader's thread: a snapshot
    line's place among the session's events is found from the event that
    follows it (place_snapshots). The plane's code is wrapped, not changed."""
    lock = threading.Lock()
    f = open(path, "a", buffering=1)
    reader_init, reader_put, sub_init = P.BridgeReader.__init__, P.BridgeReader.put, P.Subscription.__init__

    def flush(r):
        b = r._bench
        if b["sub"] is None:
            return
        while b["written"] < len(b["lines"]):
            at, obj = b["lines"][b["written"]]
            f.write(json.dumps({"sub": b["sub"], "k": b["written"], "at": at, "line": obj}) + "\n")
            b["written"] += 1

    def init(self, *args, **kwargs):
        reader_init(self, *args, **kwargs)
        self._bench = {"sub": None, "lines": [], "written": 0}

    def put(self, item):
        b = getattr(self, "_bench", None)
        if b is not None and item[0] == "line" and len(b["lines"]) < TEE_LINES:
            with lock:
                b["lines"].append((time.time(), item[1]))
                flush(self)
        reader_put(self, item)

    def subscription(self, *args, **kwargs):
        sub_init(self, *args, **kwargs)
        r = self.reader
        if r is not None and getattr(r, "_bench", None) is not None:
            with lock:
                r._bench["sub"] = self.sub
                flush(r)

    P.BridgeReader.__init__, P.BridgeReader.put, P.Subscription.__init__ = init, put, subscription


def uplink_main(scripts, tee):
    sys.path.insert(0, os.path.abspath(scripts))
    import sminos_plane
    install_tee(sminos_plane, tee)
    import sminos
    sminos.main(["daemon", "uplink"])


def read_tees(path):
    """The uplink's teed bridge lines, per sub: [{"sub", "lines"}]."""
    by = collections.OrderedDict()
    try:
        with open(path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                by.setdefault(rec["sub"], []).append((rec["k"], rec["at"], rec["line"]))
    except FileNotFoundError:
        pass
    return [{"sub": s, "lines": [(at, obj) for _, at, obj in sorted(v, key=lambda x: x[0])]} for s, v in by.items()]


# ------------------------------------------------------------- http


def call(url, method, path, body=None, headers=None, timeout=30):
    u = urllib.parse.urlsplit(url)
    c = http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    c.request(method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        r = c.getresponse()
        raw = r.read()
        try:
            return r.status, json.loads(raw or b"{}")
        except ValueError:
            return r.status, {"raw": raw.decode("utf-8", "replace")[:300]}
    finally:
        c.close()


def wait_for(what, seconds, fn, every=0.05):
    deadline = time.time() + seconds
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))


def free_pair():
    """A port n with n and n + 1 free on 127.0.0.1 (the local hub takes both)."""
    for _ in range(200):
        n = random.randint(20000, 60000)
        socks = []
        try:
            for p in (n, n + 1):
                s = socket.socket()
                s.bind(("127.0.0.1", p))
                socks.append(s)
            return n
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    raise RuntimeError("no free port pair")


def sub_id():
    return base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()   # DX3: 128 bits, base64url


# ------------------------------------------------------------- the hubs and their browsers


class StandinBrowser:
    """A browser of the project as the stand-in plays it: a subscribe is a
    frame written down the uplink's stream (its `at`, when flushed, the
    open's start), and what the uplink posted is the stand-in's stamped
    `sessions`."""

    def __init__(self, url, project, machine):
        self.url, self.project, self.machine = url, project, machine
        self.seen, self.msgs = 0, []

    def send(self, frame_):
        status, body = call(self.url, "POST", "/control/send", {"frames": [frame_]})
        if status != 200:
            raise RuntimeError("the stand-in did not write the frame: %s %s" % (status, body))
        return body.get("at") or time.time()

    def poll(self):
        status, body = call(self.url, "GET", "/control/since?sessions=%d" % self.seen)
        got = body.get("sessions") or []
        self.seen += len(got)
        self.msgs += [(e.get("at") or e.get("received"), e["message"]) for e in got]

    def subscribe(self, session, agent=None):
        sub = sub_id()
        return sub, self.send({"t": "subscribe", "project": self.project, "session": session, "agentId": agent,
                               "sub": sub})

    def unsubscribe(self, sub):
        self.send({"t": "unsubscribe", "project": self.project, "sub": sub})

    def close(self):
        pass


class LocalBrowser:
    """A browser of the project on the local hub: DX3 over its socket, each
    frame stamped on arrival (ws_client)."""

    def __init__(self, url, project, machine):
        import ws_client
        self.project, self.machine = project, machine
        ws_url = "ws" + url[len("http"):] + "/api/projects/%s/socket" % project
        self.ws = wait_for("the project's socket at the local hub", 30, lambda: self.connect(ws_client, ws_url), 0.2)
        self.seen, self.msgs = 0, []

    @staticmethod
    def connect(ws_client, url):
        try:
            return ws_client.WebSocket(url)
        except OSError:
            return None

    def send(self, frame_):
        at = time.time()
        self.ws.send(frame_)
        return at

    def poll(self):
        got = self.ws.stamped(self.seen)
        self.seen += len(got)
        self.msgs += [(at, f["message"]) for at, f in got if f.get("t") == "session"]

    def subscribe(self, session, agent=None):
        sub = sub_id()
        return sub, self.send({"t": "subscribe", "session": session, "agentId": agent, "sub": sub,
                               "machine": self.machine})

    def unsubscribe(self, sub):
        self.send({"t": "unsubscribe", "sub": sub})

    def close(self):
        self.ws.close()


class Standin:
    """hub_standin.py: one machine, `testhost`, enrolled already."""

    name, org, machine = "standin", "org-1", "testhost"

    def __init__(self, rig):
        port_file = os.path.join(rig.root, "hub.port")
        self.proc = rig.spawn([sys.executable, os.path.join(HERE, "hub_standin.py"), port_file, "cid-1", "secret-1",
                               "2000"], log="standin.out")
        self.url = "http://127.0.0.1:%s" % wait_for("the stand-in's port", 10, lambda: _read(port_file))
        self.key = KEY

    def enroll(self, rig):
        rig.write_credential({"hub": self.url, "org": self.org, "machine": self.machine, "client_id": "cid-1",
                              "client_secret": "secret-1", "key": KEY})

    def browser(self, rig):
        return StandinBrowser(self.url, rig.project, self.machine)

    def requests(self, since, until):
        status, st = call(self.url, "GET", "/control/state")
        return [{"status": p.get("status"), "conn": p.get("conn")} for p in st.get("posted") or []]

    def close(self):
        pass


class Local:
    """The hub's own Worker on a local runtime behind its stand-in for Access
    (`pnpm --filter desk-hub local`), from the MAWS worktree named, with a
    state directory of its own and a free port; its stdout, read here line by
    line and stamped, is its request log."""

    name, org = "local", "local"

    def __init__(self, rig, maws):
        if not maws or not os.path.isdir(os.path.join(maws, "apps", "desk-hub")):
            sys.exit("bench_open: --hub local needs --maws <a MAWS worktree with apps/desk-hub>")
        port = free_pair()
        self.url = "http://127.0.0.1:%d" % port
        self.machine = "bench-" + uuidlib.uuid4().hex[:6]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))}
        self.proc = subprocess.Popen(["pnpm", "--filter", "desk-hub", "local", "--state",
                                      os.path.join(rig.root, "hubstate"), "--port", str(port)],
                                     cwd=maws, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self.log, self.lock = [], threading.Lock()
        self.ready = threading.Event()
        threading.Thread(target=self.read, daemon=True).start()
        if not self.ready.wait(180):
            tail = "\n".join(l for _, l in self.log[-15:])
            self.close()
            sys.exit("bench_open: the local hub did not come up in 180 s:\n" + tail)
        self.key = None

    def read(self):
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\n")
            with self.lock:
                self.log.append((time.time(), line))
            if "Ready on http" in line:
                self.ready.set()

    def code(self, machine, key=None):
        status, body = call(self.url, "POST", "/standin/enrollment-code",
                            {"machine": machine, **({"key": key} if key else {})})
        if status != 200:
            raise RuntimeError("no enrollment code: %s %s" % (status, body))
        return body

    def enroll(self, rig):
        body = self.code(self.machine)
        self.key = body["key"]
        r = subprocess.run([SMINOS, "hub", "enroll", "--name", self.machine], input=body["code"].encode(),
                           env=rig.env, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("sminos hub enroll failed: %s" % (r.stdout + r.stderr).decode()[-500:])

    def mint(self, machine):
        """Another machine of the org, its credential redeemed here."""
        body = self.code(machine, self.key)
        status, cred = call(self.url, "POST", "/machine/enroll", {"token": body["token"], "machine": machine})
        if status != 200:
            raise RuntimeError("the redemption failed: %s %s" % (status, cred))
        return cred

    def browser(self, rig):
        return LocalBrowser(self.url, rig.project, self.machine)

    def requests(self, since, until):
        """The request log's machine POSTs between the stamps: {status, ms}."""
        pat = re.compile(r"POST /machine/frames (\d+) .*\((\d+)ms\)")
        with self.lock:
            lines = [(at, l) for at, l in self.log if since <= at <= until]
        out = []
        for at, l in lines:
            m = pat.search(l)
            if m:
                out.append({"at": at, "status": int(m[1]), "ms": int(m[2])})
        return out

    def close(self):
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(20)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


# ------------------------------------------------------------- the transcript shapes


def synthetic_transcript(path, rows, cwd, sid, seed=7):
    """A transcript of `rows` rows shaped like a working session's: turns of
    a prompt, a tool call, its result (most of the bytes, its output twice
    as the engine keeps it), and an answer, each row with the engine's
    metadata and a line of its bookkeeping beside it (no uuid: the plane
    passes such lines over unparsed), on one parent chain: about 11 KB a row,
    as the build measurement of the spec's Surprises & Discoveries shaped one
    (15,000 rows, 163 MB). The uuids repeat from `seed`."""
    rnd = random.Random(seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    filler = "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz      \n") for _ in range(26000))
    parent = None
    with open(path, "w") as f:
        for i in range(rows):
            uid = str(uuidlib.UUID(int=rnd.getrandbits(128), version=4))
            stamp = "2026-10-20T%02d:%02d:%02d.000Z" % (i // 3600 % 24, i // 60 % 60, i % 60)
            base = {"parentUuid": parent, "isSidechain": False, "userType": "external", "cwd": cwd,
                    "sessionId": sid, "version": "2.1.304", "gitBranch": "main", "slug": "bench-session",
                    "uuid": uid, "timestamp": stamp}
            usage = {"input_tokens": 3 + i % 7, "cache_creation_input_tokens": 120 + i % 50,
                     "cache_read_input_tokens": 40000 + i, "output_tokens": 30 + i % 90, "service_tier": "standard",
                     "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 120 + i % 50}}
            phase = i % 4
            if phase == 0:
                row = {**base, "type": "user", "message": {"role": "user", "content": "step %d: carry on" % i}}
            elif phase == 1:
                row = {**base, "type": "assistant", "requestId": "req_%024d" % i, "message": {
                    "id": "msg_%024d" % i, "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                    "content": [{"type": "tool_use", "id": "toolu_%020d" % i, "name": "Bash",
                                 "input": {"command": "grep -rn pattern%d src/" % i, "description": "Search"}}],
                    "stop_reason": "tool_use", "stop_sequence": None, "usage": usage}}
            elif phase == 2:
                out = filler[i % 500:][:12000]
                row = {**base, "type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_%020d" % (i - 1), "content": out,
                     "is_error": False}]},
                    "toolUseResult": {"stdout": out, "stderr": "", "interrupted": False, "isImage": False}}
            else:
                row = {**base, "type": "assistant", "requestId": "req_%024d" % i, "message": {
                    "id": "msg_%024d" % i, "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                    "content": [{"type": "text", "text": filler[:2000]}], "stop_reason": "end_turn",
                    "stop_sequence": None, "usage": usage}}
            f.write(json.dumps(row) + "\n")
            f.write(json.dumps({"type": "api-request", "sessionId": sid, "timestamp": stamp,
                                "detail": filler[:4000]}) + "\n")
            parent = uid


# ------------------------------------------------------------- the sessions


class FakeKind:
    """fake_session.py's scripted session in the project (`bridged`), or a
    synthetic transcript with no bridge: a `sleep` stands for its process,
    under an engine record in the project's checkout."""

    def __init__(self, rig, synthetic_rows=None):
        import fake_session
        self.rig = rig
        self.sid = str(uuidlib.uuid4())
        self.fake = fake_session.FakeSession(rig.home, rig.smh, self.sid)
        self.stamps = []
        lose = self.fake.lose

        def stamped(events):
            self.stamps += [time.time()] * len(events)
            lose(events)

        self.fake.lose = stamped
        self.holder = rig.spawn(["sleep", "86399"])
        self.record({"status": "idle"})
        self.name = "synthetic" if synthetic_rows else "fake"
        if synthetic_rows:
            synthetic_transcript(self.fake.path(None), synthetic_rows, rig.work, self.sid)
            self.bridged = False
        else:
            self.fake.user_row("hello")
            m = self.fake.message()
            m.text(0, "Hello there.")
            m.row(0)
            m.end()
            self.bridged = True

    def record(self, fields):
        path = os.path.join(self.rig.home, ".claude", "sessions", "%d.json" % self.holder.pid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rec = {"pid": self.holder.pid, "sessionId": self.sid, "cwd": self.rig.work, "kind": "interactive",
               "name": "bench", "nameSource": "derived", **fields}
        with open(path + ".tmp", "w") as f:
            json.dump(rec, f)
        os.replace(path + ".tmp", path)

    def start(self):
        if self.bridged:
            self.fake.start_bridge()

    def transcript(self):
        return self.fake.path(None)

    def dx5(self):
        return list(zip(self.stamps, self.fake.emitted))

    def close(self):
        self.fake.stop_bridge()


class LiveKind:
    """An isolated headless session (mods/live-bridge-check.py's Live,
    started headless), a probe subscription on its bridge from the start:
    the probe's events are the DX5 source the inventory reads."""

    name = "live"
    bridged = True

    def __init__(self, rig, a):
        self.rig, self.live = rig, rig.live
        self.thinking, self.model = a.thinking, a.model

    def start(self):
        live = self.live
        live.start_session(headless=True, thinking=self.thinking, model=self.model)
        sock_dir = os.path.join(live.smh, "bridge")
        found = wait_for("the session's bridge socket", 120, lambda: [
            n[:-5] for n in os.listdir(sock_dir) if n.endswith(".sock") and not n.startswith(".")]
            if os.path.isdir(sock_dir) else None, 0.1)
        self.sid = live.session = found[0]
        wait_for("the bridge to answer", 30, live.status, 0.1)
        threading.Thread(target=live.subscribe_forever, daemon=True).start()
        wait_for("the probe's subscription", 15, lambda: live.subscriptions > 0)

    def prompt(self, text):
        t0 = time.time()
        self.live.send(text)
        return t0

    def turn_done(self, since):
        return bool(self.live.turns_done(since))

    def events(self, since=0.0):
        with self.live.lock:
            return [(t, e) for t, e in self.live.events if t >= since]

    def transcript(self):
        found = glob.glob(os.path.join(self.live.cfg, "projects", "*", self.sid + ".jsonl"))
        return found[0] if found else os.path.join(self.live.cfg, "projects", "none", self.sid + ".jsonl")

    def dx5(self):
        return self.events()

    def close(self):
        pass


# ------------------------------------------------------------- the rig


class Rig:
    """One run's machine: a temporary HOME and SMINOS_HOME (a live
    session's own, under --live), the hub, the project, the uplink."""

    def __init__(self, a):
        self.a, self.procs, self.live = a, [], None
        if a.live:
            lbc = _load_live_check()
            missing = [k for k in lbc.GATEWAY_KEYS if k not in os.environ]
            if missing:
                sys.exit("bench_open --live: the gateway keys are not in the environment: %s" % ", ".join(missing))
            self.live = lbc.Live(a.keep)
            self.live.setup()
            self.root, self.home, self.smh, self.work = self.live.root, self.live.home, self.live.smh, self.live.work
        else:
            self.root = tempfile.mkdtemp(prefix="bo.", dir="/tmp")
            self.home, self.smh = os.path.join(self.root, "home"), os.path.join(self.root, "s")
            self.work = os.path.join(self.root, "work")
            os.makedirs(os.path.join(self.home, ".claude", "sessions"))
            os.makedirs(self.smh, mode=0o700)
        stub = os.path.join(self.root, "bin")
        os.makedirs(stub, exist_ok=True)
        with open(os.path.join(stub, "claude"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
        os.chmod(os.path.join(stub, "claude"), 0o755)
        self.env = {k: os.environ[k] for k in BASE_KEYS if k in os.environ}
        self.env.update(HOME=self.home, SMINOS_HOME=self.smh, CLAUDE_CONFIG_DIR=os.path.join(self.home, ".claude"),
                        PATH=stub + os.pathsep + os.environ.get("PATH", ""), SMINOS_DERIVE_EVERY="0",
                        PYTHONDONTWRITEBYTECODE="1")
        self.tee = os.path.join(self.root, "tee.jsonl")
        self.uplink = None
        self.hub = Local(self, a.maws) if a.hub == "local" else Standin(self)
        self.hub.enroll(self)
        if not a.live:
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
            subprocess.run(git + ["init", "-q", self.work], check=True)
            self.sminos("project", "init", "--name", "benchproj")
        smns = os.path.join(self.work, ".smns")
        with open(smns) as f:
            d = json.load(f)
        d["hub"] = {"url": self.hub.url, "org": self.hub.org}
        with open(smns, "w") as f:
            json.dump(d, f, indent=2)
        self.project = d["project"]
        self.browser = None

    def spawn(self, argv, log=None, env=None):
        out = open(os.path.join(self.root, log), "ab") if log else subprocess.DEVNULL
        p = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT if log else subprocess.DEVNULL,
                             env=env if env is not None else None)
        self.procs.append(p)
        return p

    def sminos(self, *args):
        return subprocess.run([SMINOS, *args], cwd=self.work, env=self.env, capture_output=True, check=True)

    def write_credential(self, cred):
        path = os.path.join(self.smh, "daemon", "hub.json")
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cred, f)
        os.replace(path + ".tmp", path)

    def point_uplink_at(self, url):
        """The credential's hub (the pause proxy's URL, for `held`)."""
        path = os.path.join(self.smh, "daemon", "hub.json")
        with open(path) as f:
            cred = json.load(f)
        cred["hub"] = url
        self.write_credential(cred)

    def daemon_log(self):
        return os.path.join(self.smh, "daemon.log")

    def start_uplink(self):
        self.uplink = self.spawn([sys.executable, os.path.realpath(__file__), "_uplink", SCRIPTS, self.tee],
                                 log="uplink.out", env=self.env)
        return time.time()

    def stop_uplink(self):
        if self.uplink is None:
            return
        self.uplink.send_signal(signal.SIGTERM)
        try:
            self.uplink.wait(30)
        except subprocess.TimeoutExpired:
            self.uplink.kill()
            self.uplink.wait()
        self.uplink = None

    def close(self):
        if self.browser is not None:
            self.browser.close()
        self.stop_uplink()
        for p in reversed(self.procs):
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
        self.hub.close()
        if self.live is not None:
            self.live.cleanup()
        elif not self.a.keep:
            shutil.rmtree(self.root, ignore_errors=True)
        else:
            print("kept: %s" % self.root, file=sys.stderr)


def _load_live_check():
    spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "mods",
                                                                                  "live-bridge-check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__" and sys.argv[1:2] == ["_uplink"]:
    uplink_main(sys.argv[2], sys.argv[3])
