#!/usr/bin/env python3
"""Live check of the bridge's control verbs and delivery (DC2 M2).

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session and in `--bg` jobs:
- a steer during a long Bash call does not end it, and the model acts on it
  at its next request; the terminal shows the mirror line; a steer given
  during the final answer wakes the session once, without repeating it;
- an interrupt ends the turn within 2 s and stops the Bash call the abort
  moved to the background, and leaves the model a record of both: Esc's
  marker in a row of its own, then a note (from the desk, as the daemon's RPC
  sends it, in the terminal session; through `sminos interrupt` in the --bg
  job), which the next request carries after the moved call's result, and no
  notification for the stopped task follows;
- a model change takes the next request, survives a module reload, and leaves
  the config's settings.json untouched;
- a compact asked during a turn runs after it;
- a human's `sminos say` reaches a bridged session as the human's words, and
  one key delivered three times is submitted once;
- a --bg job with no bridge gets a human's message through the engine
  supervisor's `reply`, and refuses what needs the bridge.

It spends model calls (haiku, short prompts, one compaction), so no suite
runs it: run it by hand at a milestone with the model gateway's keys in the
environment. Isolation is live-bridge-check.py's (whose class it extends): a
temporary HOME whose .claude is the sessions' config dir (so the `--bg`
supervisor it starts is that config's, never the owner's), a temporary
SMINOS_HOME, a copy of the worktree's plugin, a tmux server of its own, the
gateway keys in a 0600 env file removed at the end. The `--bg` jobs are
stopped and that supervisor stopped before it exits.

    tests/mods/live-control-check.py [--keep]
"""

import glob
import hashlib
import http.client
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
NAME = LB.NAME
wait_for = LB.wait_for


class Stream:
    """A subscription to one session's endpoint, kept open across child restarts."""

    def __init__(self, path):
        self.path = path
        self.events = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.subscriptions = 0
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while not self.stop.is_set():
            try:
                c = LB.Conn(self.path, timeout=None)
                c.request("GET", "/events")
                r = c.getresponse()
                self.subscriptions += 1
                while not self.stop.is_set():
                    line = r.readline()
                    if not line:
                        break
                    with self.lock:
                        self.events.append((time.time(), json.loads(line)))
                c.close()
            except (OSError, ValueError, http.client.HTTPException):
                pass
            time.sleep(0.2)

    def seen(self, pred, since=0.0):
        with self.lock:
            return [e for t, e in self.events if t >= since and pred(e)]

    def seen_at(self, pred, since=0.0):
        with self.lock:
            return [(t, e) for t, e in self.events if t >= since and pred(e)]


def is_main(e, kind, phase=None):
    return e.get("type") == kind and (phase is None or e.get("phase") == phase) and e.get("agentId") is None


def main_text(stream, since):
    return "".join(e["chunk"].get("text") or "" for e in stream.seen(
        lambda e: is_main(e, "chunk") and e["chunk"].get("kind") == "text", since))


class Control(LB.Live):
    def __init__(self, keep):
        super().__init__(keep)
        self.jobs = []          # bg job shorts started
        self.marker = "brc%d" % os.getpid()

    def setup(self):
        super().setup()
        # Bash runs without a dialog: the checks here are about control, not permissions.
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash"]}}, f)
        with open(self.envfile, "a") as f:
            # A cold start with no service installed spawns a transient supervisor
            # for this config dir, never asks to install one.
            f.write("export CLAUDE_CODE_DAEMON_COLD_START=transient\n")

    def cli(self, *args, timeout=120):
        return subprocess.run([self.sminos(), *args], cwd=self.work, env=self.local_env(),
                              capture_output=True, text=True, timeout=timeout)

    def claude(self, args, timeout=120):
        inner = "set -e; . %s; cd %s; exec claude %s" % (shlex.quote(self.envfile), shlex.quote(self.work),
                                                          " ".join(shlex.quote(a) for a in args))
        return subprocess.run(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", inner],
                              capture_output=True, text=True, timeout=timeout)

    def record(self, name):
        d = os.path.join(self.cfg, "sessions")
        for p in glob.glob(os.path.join(d, "*.json")):
            try:
                with open(p) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if rec.get("name") == name:
                return rec
        return None

    def transcript_rows(self, session):
        rows = []
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", session + ".jsonl")):
            with open(p) as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        return rows

    def idle(self, endpoint, seconds=120):
        """Waits until the session's main loop has run no turn for 2 s."""
        def quiet():
            try:
                s, body = LB.request(endpoint, "POST", "/command?wait=8000", {"op": "ping"}, timeout=15)
            except OSError:
                return False
            return s == 200 and body["result"]["state"]["mainTurn"] is None
        deadline = time.time() + seconds
        calm_since = None
        while time.time() < deadline:
            if quiet():
                calm_since = calm_since or time.time()
                if time.time() - calm_since >= 2:
                    return True
            else:
                calm_since = None
            time.sleep(0.5)
        raise TimeoutError("the session did not go idle")

    def bash_call(self, stream, marker, since, seconds=90):
        return wait_for("the Bash call " + marker, seconds, lambda: stream.seen(
            lambda e: is_main(e, "tool", "call") and e.get("tool") == "Bash" and marker in json.dumps(e.get("input")), since))

    def turn_end(self, stream, since, seconds=150):
        return wait_for("the main turn's end", seconds, lambda: stream.seen(lambda e: is_main(e, "turn", "complete"), since))

    def running(self, marker):
        r = subprocess.run(["pgrep", "-f", "time.sleep.*" + marker], capture_output=True, text=True)
        return [int(p) for p in r.stdout.split()]

    # -- the checks, on one session reached as `who` through `stream`

    def steer_check(self, who, stream, endpoint, prompt, label):
        m = self.marker + "s" + label
        t = time.time()
        prompt("Run exactly this Bash command, then reply in one short sentence: "
               "python3 -c 'import time; time.sleep(15); print(\"%s\")'" % m)
        self.bash_call(stream, m, t)
        time.sleep(2)
        r = self.cli("steer", who, "End your reply with the word PINEAPPLE.")
        pane = ""
        if label == "terminal":
            # The mirror line draws at the terminal's next frame.
            try:
                pane = wait_for("the mirror line", 5, lambda: "steer: End your reply" in self.pane() and self.pane())
            except TimeoutError:
                pane = self.pane()
        self.turn_end(stream, t)
        results = stream.seen(lambda e: is_main(e, "tool", "result") and e.get("tool") == "Bash", t)
        ran = any(m in str(e.get("text")) and "background" not in str(e.get("text")) for e in results)
        text = main_text(stream, t)
        self.check("%s: a steer during a long Bash call is taken" % label, r.returncode == 0 and "row" in r.stdout,
                   (r.stdout + r.stderr).strip())
        self.check("%s: the Bash call runs on to its end" % label, ran,
                   "; ".join(str(e.get("text"))[:80] for e in results))
        self.check("%s: the model acts on the steer at its next request" % label, "PINEAPPLE" in text, text[-160:])
        if label == "terminal":
            self.check("terminal: the steer is mirrored in the transcript", "steer: End your reply" in pane,
                       next((l.strip() for l in pane.splitlines() if "steer:" in l), "(no mirror line on screen)"))
        self.idle(endpoint)

    def final_steer_check(self, who, stream, endpoint):
        """A steer given while the model writes its final answer: the turn ends
        before any request reads it, so the bridge wakes the session once, with a
        prompt that does not repeat the steer, and the next request reads the row."""
        t = time.time()
        self.prompt("Write a 600-word story about a lighthouse keeper. Use no tools.")
        wait_for("the story's text", 90, lambda: stream.seen(
            lambda e: is_main(e, "chunk") and e["chunk"].get("kind") == "text", t))
        r = self.cli("steer", who, "After the story, also say the word PINEAPPLE.")
        first = self.turn_end(stream, t)
        woke = wait_for("the wake turn", 60, lambda: stream.seen(
            lambda e: is_main(e, "turn", "start") and "added a note" in str(e.get("text")), t))
        self.idle(endpoint)
        starts = stream.seen(lambda e: is_main(e, "turn", "start"), t)
        text = main_text(stream, t)
        self.check("terminal: a steer during the final answer wakes the session once, read without repeating it",
                   r.returncode == 0 and first and len(woke) == 1 and len(starts) == 2
                   and "PINEAPPLE" not in str(woke[0].get("text")) and "PINEAPPLE" in text,
                   "%s; turns %d, wake prompt %r" % (r.stdout.strip(), len(starts), str(woke[0].get("text"))[:70]))

    def interrupt_check(self, who, stream, endpoint, prompt, label, desk=False):
        m = self.marker + "i" + label
        sid = os.path.basename(endpoint)[:-len(".sock")]
        t = time.time()
        prompt("Run exactly this Bash command and nothing else: "
               "python3 -c 'import time; time.sleep(90); print(\"%s\")'" % m)
        self.bash_call(stream, m, t)
        time.sleep(2)
        before = self.running(m)
        t0 = time.time()
        if desk:
            # The command the daemon sends for the desk's Interrupt (sminos_rpc.interrupt).
            s, body = LB.request(endpoint, "POST", "/command?wait=10000", {"op": "interrupt", "from": "desk"}, timeout=20)
            ok, said = s == 200 and (body or {}).get("ok") is True, json.dumps(body)
        else:
            r = self.cli("interrupt", who)
            ok, said = r.returncode == 0, (r.stdout + r.stderr).strip()
        ended = wait_for("the aborted turn", 15, lambda: stream.seen_at(
            lambda e: is_main(e, "turn", "complete") and e.get("reason") == "aborted", t0))
        took = ended[0][0] - t0
        time.sleep(2)
        after = self.running(m)
        self.check("%s: interrupt ends the turn within 2 s" % label, ok and took <= 2.0, "%.2f s; %s" % (took, said))
        self.check("%s: and stops the Bash call the abort moved to the background" % label,
                   before and not after and "stopped" in said,
                   "python running before %s, after %s" % (before, after))

        moved = re.compile(r"running in background with ID: ([A-Za-z0-9_-]+)")

        marker = "[Request interrupted by user]"

        def record():
            rows = self.transcript_rows(sid)
            users = [row for row in rows if row.get("type") == "user"]
            at = [i for i, row in enumerate(users) if (row.get("message") or {}).get("content") == [{"type": "text", "text": marker}]]
            note = [row for row in users[at[-1] + 1:] if row.get("isMeta")
                    and "The interrupt came from" in json.dumps(row.get("message"))] if at else []
            found = [moved.search(json.dumps(row.get("message"))) for row in users]
            found = [f.group(1) for f in found if f]
            if not (note and found):
                return None
            return users[at[-1]], "\n".join(b.get("text", "") for b in note[0]["message"]["content"]), found[-1]
        row, text, task = wait_for("the interrupt's record and the moved call's result", 15, record)
        where = "the desk" if desk else "outside the terminal"
        # The marker's row is Esc's text whole, which is how a transcript's reader knows the interrupt.
        self.check("%s: the interrupt's marker is a row of Esc's text alone, kept isMeta from the plugin" % label,
                   row.get("isMeta") is True and (row.get("origin") or {}).get("kind") == "plugin",
                   json.dumps({k: row.get(k) for k in ("isMeta", "origin", "message")}))
        self.check("%s: then a note for the model: from %s, the task it stopped not running" % (label, where),
                   text.startswith("The interrupt came from %s." % where)
                   and task in said and task in text and "is not running" in text, repr(text))
        self.idle(endpoint)
        t = time.time()
        prompt("Without running any tool, answer with one word: is the python sleep command from your last "
               "turn still running? Reply RUNNING or STOPPED.")
        self.turn_end(stream, t)
        answer = main_text(stream, t)
        # What the next request carried after the moved call's result, as the transcript keeps the request's messages.
        carried = []
        for row in self.transcript_rows(sid):
            content = (row.get("message") or {}).get("content") if row.get("type") == "api-request-blob" else None
            if isinstance(content, list) and any(b.get("type") == "tool_result" and task in json.dumps(b) for b in content):
                carried = [b.get("type") if b.get("type") != "text" else b.get("text", "").split("\n")[0] for b in content]
        self.check("%s: the next request carries the marker, then the note, after the moved call's result" % label,
                   carried[:3] == ["tool_result", marker, "The interrupt came from %s." % where], repr(carried))
        self.check("%s: and the model, reading it, knows the command is stopped" % label,
                   "STOPPED" in answer and "RUNNING" not in answer, repr(answer[-120:]))
        notes = [row for row in self.transcript_rows(sid) if "<task-notification>" in json.dumps(row)
                 and task is not None and task in json.dumps(row)]
        self.check("%s: and no notification for the stopped task follows" % label, not notes,
                   "%d notification rows" % len(notes))
        self.idle(endpoint)

    def run(self):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer", 20, self.status)
        term = Stream(self.endpoint())
        wait_for("the subscription", 10, lambda: term.subscriptions > 0)

        # -- the terminal session
        self.steer_check(NAME, term, self.endpoint(), self.prompt, "terminal")
        self.final_steer_check(NAME, term, self.endpoint())
        self.interrupt_check(NAME, term, self.endpoint(), self.prompt, "terminal", desk=True)

        settings = os.path.join(self.cfg, "settings.json")
        with open(settings, "rb") as f:
            before = (f.read(), os.stat(settings).st_mtime_ns)
        r = self.cli("model", NAME, "sonnet")
        t = time.time()
        self.prompt("Reply with exactly: hi")
        self.turn_end(term, t)
        starts = term.seen(lambda e: is_main(e, "step", "start"), t)
        ends = term.seen(lambda e: is_main(e, "step", "end"), t)
        used = [str((e.get("usage") or {}).get("model")) for e in ends]
        with open(settings, "rb") as f:
            after = (f.read(), os.stat(settings).st_mtime_ns)
        # `sonnet` is resolved as the engine resolves it first, through the
        # session's ANTHROPIC_DEFAULT_SONNET_MODEL: the request names that id.
        self.check("a model change takes the next request", r.returncode == 0 and starts and
                   "sonnet" in str(starts[0].get("model")) and used and all("sonnet" in u for u in used),
                   "%s; requested %s, answered by %s" % (r.stdout.strip(), [e.get("model") for e in starts], used))
        self.check("and leaves the config's settings.json untouched", before == after,
                   "%d bytes, mtime %s" % (len(after[0]), "same" if before[1] == after[1] else "CHANGED"))
        kept_path = os.path.join(self.smh, "bridge", self.session + ".json")
        with open(kept_path) as f:
            kept = json.load(f)
        old = self.status()["pid"]
        with open(os.path.join(self.plugin, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-control-check: a change that reloads the module\n")
        wait_for("the child after a module reload", 60,
                 lambda: (self.status() or {}).get("pid") not in (None, old) and self.status())
        t = time.time()
        self.prompt("Reply with exactly: ok")
        self.turn_end(term, t)
        ends = term.seen(lambda e: is_main(e, "step", "end"), t)
        used = [str((e.get("usage") or {}).get("model")) for e in ends]
        self.check("the model choice survives a module reload (kept by the child)",
                   "sonnet" in str((kept.get("override") or {}).get("model")) and used and all("sonnet" in u for u in used),
                   "kept %s; answered by %s" % (kept, used))
        r = self.cli("model", NAME, "default")
        t = time.time()
        self.prompt("Reply with exactly: back")
        self.turn_end(term, t)
        ends = term.seen(lambda e: is_main(e, "step", "end"), t)
        used = [str((e.get("usage") or {}).get("model")) for e in ends]
        self.check("model default returns the session to its own", used and all("haiku" in u for u in used),
                   "%s; answered by %s" % (r.stdout.strip(), used))
        self.idle(self.endpoint())

        m = self.marker + "c"
        t = time.time()
        self.prompt("Run exactly this Bash command, then reply with one word: "
                    "python3 -c 'import time; time.sleep(8); print(\"%s\")'" % m)
        self.bash_call(term, m, t)
        r = self.cli("compact", NAME)
        done = self.turn_end(term, t)
        end = wait_for("the compaction's end", 180, lambda: term.seen(
            lambda e: e.get("type") == "compact" and e.get("phase") == "end", t))
        start = term.seen_at(lambda e: e.get("type") == "compact" and e.get("phase") == "start", t)
        turn_t = term.seen_at(lambda e: is_main(e, "turn", "complete"), t)[0][0]
        self.check("a compact asked during a turn is queued and runs after it",
                   r.returncode == 0 and "queued" in r.stdout and start and start[0][0] >= turn_t
                   and end[0].get("tokensAfter") is not None and done,
                   "%s; then %s" % (r.stdout.strip(), {k: end[0].get(k) for k in ("tokensBefore", "tokensAfter", "error", "skip")}))
        self.idle(self.endpoint(), 180)

        t = time.time()
        r = self.cli("say", "@%s Reply with exactly the word BANANA." % NAME)
        started = wait_for("the delivered turn", 60, lambda: term.seen(
            lambda e: is_main(e, "turn", "start") and "BANANA" in str(e.get("text")), t))
        self.turn_end(term, t)
        rows = [row for row in self.transcript_rows(self.session) if row.get("type") == "user"
                and "Reply with exactly the word BANANA" in json.dumps(row.get("message"))]
        origin = rows[0].get("origin") if rows else None
        self.check("a human's say reaches the bridged session through the bridge, as the human's words",
                   r.returncode == 0 and "sent" in r.stdout and str(started[0].get("text")).startswith("[sminos chat")
                   and isinstance(origin, dict) and origin.get("asUser") is True
                   and term.seen(lambda e: e.get("type") == "delivered" and e.get("outcome") == "submitted", t)
                   and "BANANA" in main_text(term, t),
                   "%s; prompt %r; origin %s" % (r.stdout.strip(), str(started[0].get("text"))[:60], origin))
        self.idle(self.endpoint())
        t = time.time()
        key = {"writer": "live/human", "seq": 1}
        outcomes = []
        for _ in range(3):
            s, body = LB.request(self.endpoint(), "POST", "/command?wait=8000",
                                 {"op": "deliver", "key": key, "text": "Reply with exactly the word KIWI."}, timeout=15)
            outcomes.append(next(iter((body or {}).get("result") or {}), s))
        wait_for("the KIWI turn", 60, lambda: term.seen(lambda e: is_main(e, "turn", "start") and "KIWI" in str(e.get("text")), t))
        self.idle(self.endpoint())
        time.sleep(3)
        kiwis = term.seen(lambda e: is_main(e, "turn", "start") and "KIWI" in str(e.get("text")), t)
        self.check("one key delivered three times is submitted once", outcomes == ["submitted", "duplicate", "duplicate"]
                   and len(kiwis) == 1, "answers %s, %d turns" % (outcomes, len(kiwis)))

        # -- a --bg job with the bridge
        r = self.claude(["--bg", "--plugin-dir", self.plugin, "--model", "haiku", "-n", "brbg",
                         "Reply with exactly the word READY."])
        rec = wait_for("the bg job's record", 60, lambda: self.record("brbg"))
        self.jobs.append(rec.get("jobId"))
        bg_sock = os.path.join(self.smh, "bridge", rec["sessionId"] + ".sock")
        wait_for("the bg job's endpoint", 60, lambda: LB.request(bg_sock, "GET", "/status", timeout=3)[0] == 200
                 if os.path.exists(bg_sock) else False)
        bg = Stream(bg_sock)
        wait_for("the bg subscription", 10, lambda: bg.subscriptions > 0)
        self.idle(bg_sock)
        self.check("a --bg job has a bridge", rec.get("kind") == "bg", "job %s, session %s" % (rec.get("jobId"), rec["sessionId"][:8]))

        def say_bg(text):
            out = self.cli("say", "@brbg " + text)
            if out.returncode != 0 or "sent" not in out.stdout:
                raise RuntimeError("say to brbg: %s" % (out.stdout + out.stderr).strip())
        self.steer_check("brbg", bg, bg_sock, say_bg, "bg")
        self.interrupt_check("brbg", bg, bg_sock, say_bg, "bg")

        # -- a --bg job with no bridge: no plugin, so no mod
        r = self.claude(["--bg", "--model", "haiku", "-n", "brnob", "Reply with exactly the word READY."])
        nob = wait_for("the bridgeless job's record", 60, lambda: self.record("brnob"))
        self.jobs.append(nob.get("jobId"))
        wait_for("the bridgeless job's first answer", 90, lambda: any(
            row.get("type") == "assistant" for row in self.transcript_rows(nob["sessionId"])))
        time.sleep(3)
        r = self.cli("say", "@brnob Reply with exactly the word MANGO.")
        rows = wait_for("MANGO in the bridgeless job", 90, lambda: [
            row for row in self.transcript_rows(nob["sessionId"])
            if row.get("type") == "assistant" and "MANGO" in json.dumps(row.get("message"))])
        prompt = [row for row in self.transcript_rows(nob["sessionId"]) if row.get("type") == "user"
                  and "Reply with exactly the word MANGO" in json.dumps(row.get("message"))]
        shape = {k: prompt[0].get(k) for k in ("origin", "promptSource", "isMeta")} if prompt else None
        self.check("a human's say to a --bg job with no bridge goes through the supervisor's reply",
                   r.returncode == 0 and "sent" in r.stdout and rows and prompt
                   and "another Claude session" not in json.dumps(prompt[0].get("message")),
                   "%s; prompt row %s" % (r.stdout.strip(), shape))
        r = self.cli("interrupt", "brnob")
        self.check("what needs the bridge is refused on it, saying so", r.returncode == 4 and "no bridge" in r.stderr,
                   r.stderr.strip())

    def cleanup(self):
        for short in self.jobs:
            if short:
                try:
                    self.claude(["stop", short], timeout=60)
                except subprocess.SubprocessError:
                    pass
        lock = os.path.join(self.cfg, "daemon.lock")
        sup = None
        try:
            with open(lock) as f:
                sup = json.load(f).get("pid")
        except (OSError, ValueError):
            pass
        try:
            self.claude(["daemon", "stop", "--any"], timeout=60)
        except subprocess.SubprocessError:
            pass
        if sup:
            try:
                wait_for("the temporary supervisor's end", 20, lambda: not LB._alive(sup))
            except TimeoutError:
                os.kill(sup, signal.SIGTERM)
            print("  supervisor (pid %s): %s" % (sup, "stopped" if not LB._alive(sup) else "STILL RUNNING"), flush=True)
        # Its workers and spares name this config's socket root, not the temp dir.
        sock_root = "/tmp/cc-daemon-%d/%s" % (os.getuid(), hashlib.sha256(os.path.abspath(self.cfg).encode()).hexdigest()[:8])
        try:
            wait_for("the supervisor's workers to end", 20, lambda: not LB._strays(sock_root))
        except TimeoutError:
            for pid in LB._strays(sock_root):
                os.kill(pid, signal.SIGKILL)
        print("  workers under %s: %s" % (sock_root, "none left" if not LB._strays(sock_root) else
                                          "STILL RUNNING: %s" % LB._strays(sock_root)), flush=True)
        super().cleanup()


def main():
    live = Control("--keep" in sys.argv[1:])
    print("live control check (%s):" % live.root, flush=True)
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
