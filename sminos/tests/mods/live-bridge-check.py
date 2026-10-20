#!/usr/bin/env python3
"""Live check of the bridge mod and its child (DC2 M1) in a real session.

What only a running engine shows, pinned so a release that breaks it fails
loudly: a command line reaches the mod idle, mid-model, with a permission
dialog open and mid-Bash; a subagent's chunks carry its agentId; a child
killed outright is replaced at its endpoint by a successor that answers; a
module reload kills the child and spawns the next; a /clear moves the bridge
to the new session id at once; `sminos watch` prints the
stream, by session id and by name, and says so for a session with no bridge.

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand at a milestone, from anywhere, with the model gateway's keys in the
environment. Everything it starts is isolated: a temporary HOME whose
.claude is the session's config dir, a temporary SMINOS_HOME, a copy of the
worktree's sminos plugin loaded with --plugin-dir, a tmux server of its own. The
gateway keys reach the session through a 0600 env file in that temporary
directory, removed at the end whatever happens; nothing else of the caller's
environment does.

    sminos/tests/mods/live-bridge-check.py [--keep]     # --keep: leave the temp dir (minus the env file)
"""

import http.client
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))
GATEWAY_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY")
BASE_KEYS = ("PATH", "TERM", "LANG", "USER", "LOGNAME", "SHELL", "TMPDIR")
PLUGIN_PARTS = (".claude-plugin", "hooks", "skills", "types")
NAME = "brlive"
THINKING_BUDGET = 2048    # MAX_THINKING_TOKENS for a session started with thinking on


class Conn(http.client.HTTPConnection):
    def __init__(self, path, timeout=10):
        super().__init__("bridge", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def request(path, method, url, body=None, timeout=10):
    c = Conn(path, timeout)
    try:
        c.request(method, url, body=None if body is None else json.dumps(body))
        r = c.getresponse()
        text = r.read().decode()
        return r.status, (json.loads(text) if text else None)
    finally:
        c.close()


def stage(source, dest, parts):
    """A copy of a plugin's parts, as --plugin-dir or a marketplace loads them."""
    for part in parts:
        shutil.copytree(os.path.join(source, part), os.path.join(dest, part),
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules"))


def wait_for(what, seconds, fn, every=0.2):
    deadline = time.time() + seconds
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))


class Live:
    def __init__(self, keep):
        self.keep = keep
        self.root = tempfile.mkdtemp(prefix="brl.", dir="/tmp")
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.home, ".claude")
        self.smh = os.path.join(self.root, "s")
        self.work = os.path.join(self.root, "work")
        self.plugin = os.path.join(self.root, "plugin")
        self.envfile = os.path.join(self.root, "env")
        self.tmux = ["tmux", "-L", "brl-%d" % os.getpid(), "-f", "/dev/null"]
        self.events = []          # (time, event) from the subscription
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.subscriptions = 0
        self.connections = []     # each subscription of the probe (subscribe_forever)
        self.failed = []          # (time, why) of each attempt that got no stream
        self.session = None
        self.results = []
        self.procs = []
        self.headless = None      # the headless session's process, once started so
        self.out = []             # (time, stream-json object) it wrote

    # -- isolation

    def local_env(self):
        env = {k: os.environ[k] for k in BASE_KEYS if k in os.environ}
        env.update(HOME=self.home, SMINOS_HOME=self.smh, CLAUDE_CONFIG_DIR=self.cfg)
        return env

    def setup(self):
        missing = [k for k in GATEWAY_KEYS if k not in os.environ]
        if missing:
            sys.exit("live-bridge-check: the gateway keys are not in the environment: %s" % ", ".join(missing))
        os.makedirs(self.cfg)
        os.makedirs(self.smh, mode=0o700)
        os.makedirs(self.work)
        stage(PLUGIN_ROOT, self.plugin, PLUGIN_PARTS)
        trusted = {"hasTrustDialogAccepted": True}
        with open(os.path.join(self.cfg, ".claude.json"), "w") as f:
            json.dump({"hasCompletedOnboarding": True,
                       "projects": {self.work: trusted, os.path.realpath(self.work): trusted}}, f)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            f.write("{}\n")
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", self.work], check=True)
        subprocess.run([self.sminos(), "project", "init", "--name", NAME], cwd=self.work, env=self.local_env(),
                       check=True, capture_output=True)
        env = self.local_env()
        env.update({k: os.environ[k] for k in GATEWAY_KEYS})
        env["CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"] = "1"
        fd = os.open(self.envfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            for k, v in sorted(env.items()):
                f.write("export %s=%s\n" % (k, shlex.quote(v)))

    def sminos(self):
        return os.path.join(PLUGIN_ROOT, "skills", "sminos", "scripts", "sminos")

    def plugin_dirs(self):
        """The plugins the session loads with --plugin-dir: sminos's copy; a check of another plugin's mods adds it."""
        return [self.plugin]

    def start_session(self, headless=False, thinking=False, model="haiku"):
        """The session, under setup()'s isolation: interactive in this
        check's tmux server, or `headless` — `claude -p` reading stream-json
        prompts on a pipe (`send`) and writing stream-json with partial
        messages, which a thread reads into `out` — with extended thinking
        on when `thinking` (the engine's budget, MAX_THINKING_TOKENS, through
        the env file) and `model` its --model."""
        if thinking:
            with open(self.envfile, "a") as f:
                f.write("export MAX_THINKING_TOKENS=%d\n" % THINKING_BUDGET)
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.plugin_dirs())
        if headless:
            # A `claude -p` run is no member of its project unless the host
            # that spawned it marks it (SMNS_MEMBER, the spawner's pid, as
            # MAWS marks its sessions): this process is its parent, the
            # shells before it exec'd away.
            with open(self.envfile, "a") as f:
                f.write("export SMNS_MEMBER=%d\n" % os.getpid())
            inner =("set -e; . %s; cd %s; exec claude -p --input-format stream-json --output-format stream-json "
                     "--include-partial-messages --verbose %s --model %s --permission-mode default -n %s") % (
                shlex.quote(self.envfile), shlex.quote(self.work), dirs, shlex.quote(model), NAME)
            self.headless = subprocess.Popen(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", inner],
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, bufsize=0)
            self.procs.append(self.headless)
            threading.Thread(target=self.read_headless, daemon=True).start()
            return
        inner = "set -e; . %s; cd %s; exec claude %s --model %s --permission-mode default -n %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), dirs, shlex.quote(model), NAME)
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "brl", "-x", "200", "-y", "50", cmd], check=True)

    def read_headless(self):
        for line in iter(self.headless.stdout.readline, b""):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            with self.lock:
                self.out.append((time.time(), obj))

    def send(self, text):
        """A prompt to the headless session, as a stream-json user message."""
        self.headless.stdin.write((json.dumps({"type": "user", "message": {"role": "user", "content": text}})
                                   + "\n").encode())
        self.headless.stdin.flush()

    def turns_done(self, since=0.0):
        """The headless session's `result` lines since `since`: one per turn it finished."""
        with self.lock:
            return [o for t, o in self.out if t >= since and o.get("type") == "result"]

    def pane(self):
        r = subprocess.run(self.tmux + ["capture-pane", "-p", "-t", "brl"], capture_output=True, text=True)
        return r.stdout

    def keys(self, *keys):
        subprocess.run(self.tmux + ["send-keys", "-t", "brl"] + list(keys), check=True)

    def prompt(self, text):
        self.keys("-l", text)
        time.sleep(0.3)
        self.keys("Enter")

    def endpoint(self):
        return os.path.join(self.smh, "bridge", self.session + ".sock")

    def presence(self):
        d = os.path.join(self.cfg, "sessions")
        for name in os.listdir(d) if os.path.isdir(d) else []:
            try:
                with open(os.path.join(d, name)) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if rec.get("sessionId") == self.session:
                return rec
        return {}

    # -- the endpoint

    def status(self):
        try:
            s, body = request(self.endpoint(), "GET", "/status", timeout=3)
            return body if s == 200 else None
        except OSError:
            return None

    def ping(self):
        s, body = request(self.endpoint(), "POST", "/command?wait=8000", {"op": "ping"}, timeout=15)
        return s, body

    def subscribe_forever(self):
        """The probe: one subscription after another for as long as the
        check runs, each in `connections` ({"opened", "first": the index of
        its snapshot in `events`, "closed", "why"}) and each attempt that got
        no stream in `failed` — so every gap between two of them is on
        record for whoever reads `events` as the session's DX5 source."""
        while not self.stop.is_set():
            conn = None
            try:
                c = Conn(self.endpoint(), timeout=None)
                c.request("GET", "/events")
                r = c.getresponse()
                if r.status != 200:
                    r.read()
                    c.close()
                    with self.lock:
                        self.failed.append((time.time(), "refused %d" % r.status))
                    time.sleep(0.2)
                    continue
                conn = {"opened": time.time(), "first": None, "closed": None, "why": None}
                with self.lock:
                    self.connections.append(conn)
                self.subscriptions += 1
                while not self.stop.is_set():
                    line = r.readline()
                    if not line:
                        conn["why"] = "the bridge ended the stream"
                        break
                    with self.lock:
                        if conn["first"] is None:
                            conn["first"] = len(self.events)
                        self.events.append((time.time(), json.loads(line)))
                c.close()
            except (OSError, ValueError, http.client.HTTPException) as e:
                with self.lock:
                    if conn is None:
                        self.failed.append((time.time(), repr(e)))
                    else:
                        conn["why"] = repr(e)
            if conn is not None:
                with self.lock:
                    conn["closed"] = time.time()
                    conn["why"] = conn["why"] or "the check stopped"
            time.sleep(0.2)

    def seen(self, pred, since=0.0):
        with self.lock:
            return [e for t, e in self.events if t >= since and pred(e)]

    def check(self, name, ok, detail):
        self.results.append((name, bool(ok), detail))
        print("  %s %s — %s" % ("ok  " if ok else "FAIL", name, detail), flush=True)

    def wait_turn_end(self, since, seconds=120):
        return wait_for("the main turn's end", seconds, lambda: self.seen(
            lambda e: e.get("type") == "turn" and e.get("phase") == "complete" and e.get("agentId") is None, since))

    # -- the checks

    def run(self):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer", 20, self.status)
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        wait_for("the subscription", 10, lambda: self.subscriptions > 0)
        first = self.status()
        self.check("the child serves the session's endpoint", first and first["session"] == self.session,
                   "session %s, child pid %s" % (self.session, first and first["pid"]))

        s, body = self.ping()
        self.check("a command reaches the mod idle", s == 200 and body.get("ok") and body["result"]["state"]["mainTurn"] is None,
                   "status %s, state %s" % (s, body and body.get("result", {}).get("state")))

        t0 = time.time()
        self.prompt("Write a 250-word story about a lighthouse keeper. Use no tools.")
        wait_for("main-loop text", 90, lambda: self.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") is None and e["chunk"].get("kind") == "text", t0))
        s, body = self.ping()
        state = body.get("result", {}).get("state", {}) if body else {}
        self.check("a command reaches the mod mid-model", s == 200 and body.get("ok") and state.get("isStreaming"),
                   "status %s, state %s" % (s, state))
        self.wait_turn_end(t0)
        chunks = self.seen(lambda e: e.get("type") == "chunk" and e.get("agentId") is None, t0)
        by_step = {}
        for e in chunks:
            by_step.setdefault((e["turnId"], e["step"]), []).append(e["chunkIndex"])
        sequential = all(v == list(range(len(v))) for v in by_step.values())
        self.check("main-loop chunks carry turn, step and their index, in order", chunks and sequential,
                   "%d chunks over %d model requests" % (len(chunks), len(by_step)))

        t1 = time.time()
        self.prompt("Run exactly this Bash command and nothing else: "
                    "python3 -c 'import time; time.sleep(8); print(\"brl-bash-done\")'")
        wait_for("the permission dialog", 90, lambda: self.presence().get("status") == "waiting"
                 or "Do you want to proceed" in self.pane())
        s, body = self.ping()
        self.check("a command reaches the mod with a permission dialog open", s == 200 and body.get("ok"),
                   "status %s, state %s, presence %s" % (s, body and body["result"]["state"],
                                                         {k: self.presence().get(k) for k in ("status", "waitingFor")}))
        self.keys("Enter")
        wait_for("the Bash call to run", 30, lambda: self.presence().get("status") in ("busy", "shell")
                 and "Do you want to proceed" not in self.pane())
        time.sleep(1.5)
        s, body = self.ping()
        state = body.get("result", {}).get("state", {}) if body else {}
        self.check("a command reaches the mod mid-Bash", s == 200 and body.get("ok") and "Bash" in state.get("tools", []),
                   "status %s, state %s" % (s, state))
        self.wait_turn_end(t1)
        out = self.seen(lambda e: e.get("type") == "tool" and e.get("phase") == "result" and e.get("tool") == "Bash", t1)
        self.check("the Bash call's result reached the stream", any("brl-bash-done" in str(e.get("text")) for e in out),
                   "%d Bash results" % len(out))

        t2 = time.time()
        self.prompt("Use the Agent tool exactly once, subagent_type general-purpose, in the foreground, asking it "
                    "to reply with one short sentence about the sea. Then repeat its reply.")
        sub = wait_for("a subagent's text chunk", 150, lambda: self.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") and e["chunk"].get("kind") == "text", t2))
        spawned = self.seen(lambda e: e.get("type") == "agent" and e.get("phase") == "spawn", t2)
        self.check("a subagent's chunks carry its agentId", sub and spawned and sub[0]["agentId"] == spawned[0]["agentId"],
                   "agent %s (%s), %d text chunks" % (sub[0]["agentId"], spawned and spawned[0].get("subagentType"), len(sub)))
        self.wait_turn_end(t2, 180)

        t3 = time.time()
        w = subprocess.Popen([self.sminos(), "watch", self.session], cwd=self.work, env=self.local_env(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(w)
        time.sleep(1.0)
        self.prompt("Say hello in five words.")
        self.wait_turn_end(t3)
        time.sleep(1.0)
        w.terminate()
        text = w.communicate(timeout=10)[0]
        self.check("sminos watch prints the stream as it happens", "» Say hello in five words." in text and "[main] " in text,
                   " / ".join(text.strip().splitlines()[:4])[:300])
        by_name = subprocess.Popen([self.sminos(), "watch", NAME, "--json"], cwd=self.work, env=self.local_env(),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(by_name)
        line = by_name.stdout.readline()
        by_name.terminate()
        by_name.communicate(timeout=10)
        try:
            snap = json.loads(line)
        except ValueError:
            snap = {}
        self.check("sminos watch finds the session by its name", snap.get("type") == "snapshot" and snap.get("session") == self.session,
                   line.strip()[:160])
        none = subprocess.run([self.sminos(), "watch", "00000000-0000-4000-8000-000000000000"], cwd=self.work,
                              env=self.local_env(), capture_output=True, text=True)
        self.check("sminos watch on a session with no bridge says so and exits non-zero",
                   none.returncode == 4 and "no bridge" in none.stderr, "rc %d: %s" % (none.returncode, none.stderr.strip()))

        # The mod starts a dead child's successor at once (open-fast §6), so
        # the socket the killed child leaves is stale for a fraction of a
        # second at most: what is checked is that the successor takes the
        # same endpoint over and answers there.
        old = self.status()["pid"]
        killed = time.time()
        os.kill(old, signal.SIGKILL)
        new = wait_for("a respawned child", 30, lambda: (self.status() or {}).get("pid") not in (None, old) and self.status(),
                       every=0.02)
        self.check("a child killed outright is replaced at its endpoint by a successor that answers",
                   new["pid"] != old, "killed %s, now %s answering after %.2f s" % (old, new["pid"], time.time() - killed))

        old = new["pid"]
        subs = self.subscriptions
        with open(os.path.join(self.plugin, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-bridge-check: a change that reloads the module\n")
        new = wait_for("the child after a module reload", 60,
                       lambda: (self.status() or {}).get("pid") not in (None, old) and self.status())
        gone = wait_for("the old child's end", 10, lambda: not _alive(old))
        s, body = self.ping()
        self.check("a module reload kills the child and spawns the next, which answers",
                   gone and s == 200 and body.get("ok"), "old %s, new %s, ping %s" % (old, new["pid"], s))
        wait_for("the subscription to follow", 10, lambda: self.subscriptions > subs)
        self.check("a subscriber follows the endpoint to the new child", self.subscriptions > subs,
                   "%d subscriptions in all" % self.subscriptions)

        # A /clear: the conversation ends and the process goes on under a new
        # id, with no session.start. The old child gets the end; the bridge
        # moves to the new id at once, not at the next heartbeat.
        old_session, old_endpoint = self.session, self.endpoint()
        t4 = time.time()
        self.prompt("/clear")
        fresh = wait_for("the new session's endpoint", 20, lambda: [
            n[:-5] for n in os.listdir(sock_dir)
            if n.endswith(".sock") and not n.startswith(".") and n[:-5] != old_session])
        moved_after = time.time() - t4
        self.session = fresh[0]
        st = wait_for("the new endpoint to answer", 10, self.status)
        ended = self.seen(lambda e: e.get("type") == "session" and e.get("phase") == "end" and e.get("reason") == "clear", t4)
        gone = wait_for("the old endpoint to go", 10, lambda: not os.path.exists(old_endpoint))
        s, body = self.ping()
        self.check("a /clear moves the bridge to the new session, the old child getting its end",
                   ended and gone and st["session"] == self.session and s == 200 and body.get("ok"),
                   "old %s, new %s, endpoint up %.1f s after /clear, end seen %s, old endpoint gone %s, ping %s" % (
                       old_session[:8], self.session[:8], moved_after, bool(ended), gone, s))

    def cleanup(self):
        self.stop.set()
        for p in self.procs:
            if p.poll() is None:
                p.kill()
        try:
            os.unlink(self.envfile)
        except OSError:
            pass
        subprocess.run(self.tmux + ["kill-server"], capture_output=True)
        try:
            wait_for("every process of the check to end", 20, lambda: not _strays(self.root))
        except TimeoutError:
            for pid in _strays(self.root):
                os.kill(pid, signal.SIGKILL)
        left = _strays(self.root)
        print("  cleanup: %s" % ("nothing left running" if not left else "STILL RUNNING: %s" % left), flush=True)
        if not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)
        else:
            print("  kept: %s" % self.root)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _strays(root):
    r = subprocess.run(["pgrep", "-f", root], capture_output=True, text=True)
    return [int(p) for p in r.stdout.split() if int(p) != os.getpid()]


def main():
    live = Live("--keep" in sys.argv[1:])
    print("live bridge check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
        print("  pane at the failure:\n" + "\n".join("    " + l for l in live.pane().rstrip().splitlines()[-25:]))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed), len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
