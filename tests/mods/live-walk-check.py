#!/usr/bin/env python3
"""DC2's acceptance walk (M4), live, in a terminal session and a `--bg` job.

The plan's Concrete Steps, each against a real session through the CLI:
`sminos watch` (chunks stream, subagents tagged), `steer` during a Python
sleep, `interrupt` (a backgrounded Bash ends), `decide … deny`, `answer …
"B"`, `compact` during a turn, `model … sonnet` (settings.json untouched);
DC2.G4, a `<message>` span and an async question reaching the project's log
as they complete, before the turn's end, which the Stop hook's export then
finds there; and the items earlier milestones carried here: a module reload
in the middle of a streaming response, `send --wait` through a bridged seat,
model and compact on the `--bg` job, a foreground subagent's Bash under
interrupt, an async question's `[ answer ]` pressed in the terminal (an SGR
mouse press written to the pane), and on the `--bg` job the settlement cases
a job can show (the CLI first; the terminal first through `claude attach`;
a late answer refused; a client reconnecting after the settlement). Last,
the row notices (DX5's row order) are compared with the transcripts: none
twice, none for a row never written, no block-row after a notice for a row
later on disk (a row-seen out of disk order is the engine's write-order quirk,
reported);
every row kind that got no notice is reported, and so is the largest lag
from a row's flush (the transcripts polled every DISK_POLL) to its notice,
overall and while chunks stream, against the consumer's 2 s window.

It spends model calls (haiku, short prompts, two compactions), so no suite
runs it: run it by hand with the model gateway's keys in the environment.
Isolation is live-control-check.py's (whose classes it extends): a temporary
HOME whose .claude is the config dir, a temporary SMINOS_HOME, a copy of the
worktree's plugin, a tmux server of its own, the gateway keys in a 0600 env
file removed at the end, the `--bg` jobs and the temporary supervisor
stopped before it exits. Python calls are allowed in the config's settings,
so the sleeps run unasked; every other Bash call asks.

    tests/mods/live-walk-check.py [--keep] [--only terminal,bg,seat,press]
"""

import glob
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LR = _load("live_requests_check", "live-requests-check.py")
LC = LR.LC
LB = LC.LB
NAME = LB.NAME
BG = "brwalk"
SEAT = "brseat"
wait_for = LB.wait_for
is_main = LC.is_main
DIALOG = LR.DIALOG
NOTICES = ("block-row", "row-seen")
# Long enough to still be streaming when the walk subscribes to the job's endpoint.
FIRST_PROMPT = "Count from one to eighty in words, one number per line, then write READY on its own line. Use no tools."
DISK_POLL = 0.01        # s: how often the transcripts are read for rows newly flushed
UNNAMED_AFTER = 2.0     # s: the consumer's window for a row with no notice (DX5)


class DiskWatch:
    """When each row of a session's transcripts (main and subagents) was
    first on disk, the files polled every DISK_POLL."""

    def __init__(self, cfg, session):
        self.cfg, self.session = cfg, session
        self.first_seen = {}
        self.offsets = {}
        self.stop = threading.Event()
        threading.Thread(target=self.run, daemon=True).start()

    def files(self):
        mains = glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl"))
        subs = glob.glob(os.path.join(self.cfg, "projects", "*", self.session, "subagents", "agent-*.jsonl"))
        return mains + subs

    def run(self):
        files, n = [], 0
        while not self.stop.is_set():
            if n % 20 == 0:
                files = self.files()
            n += 1
            for path in files:
                try:
                    with open(path, "rb") as f:
                        f.seek(self.offsets.get(path, 0))
                        data = f.read()
                except OSError:
                    continue
                end = data.rfind(b"\n")
                if end < 0:
                    continue
                self.offsets[path] = self.offsets.get(path, 0) + end + 1
                now = time.time()
                for line in data[:end].split(b"\n"):
                    try:
                        uuid = json.loads(line).get("uuid")
                    except (ValueError, AttributeError):
                        continue
                    if isinstance(uuid, str):
                        self.first_seen.setdefault(uuid, now)
            time.sleep(DISK_POLL)


class Walk(LR.Requests):
    def __init__(self, keep, only):
        super().__init__(keep)
        self.only = only
        self.target = "brl"
        self.watchers = {}      # who → (process, output file)
        self.streams = {}       # session → Stream

    def setup(self):
        LB.Live.setup(self)
        self.disks = {}
        # Python calls (the sleeps) run unasked; the calls the requests are
        # walked with are node's, which ask (2.1.300 runs a plain `echo`
        # unasked in the default mode, as read-only).
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash(python3:*)"]}}, f)
        with open(self.envfile, "a") as f:
            f.write("export CLAUDE_CODE_DAEMON_COLD_START=transient\n")
            # With the fork-subagent gate on (2.1.300's default here), every
            # Agent call runs in the background whatever run_in_background
            # says; off, a foreground subagent is possible.
            f.write("export CLAUDE_CODE_FORK_SUBAGENT=0\n")

    def start_session(self):
        LB.Live.start_session(self)

    def pane(self):
        r = subprocess.run(self.tmux + ["capture-pane", "-p", "-t", self.target], capture_output=True, text=True)
        return r.stdout

    def keys(self, *keys):
        subprocess.run(self.tmux + ["send-keys", "-t", self.target] + list(keys), check=True)

    # -- the project's log and the export position

    def log_events(self, session):
        out = []
        for p in glob.glob(os.path.join(self.smh, "projects", "*", "log", "*.%s.jsonl" % session)):
            with open(p) as f:
                out += [json.loads(line) for line in f if line.strip()]
        return out

    def position_mtime(self, session):
        ps = glob.glob(os.path.join(self.smh, "projects", "*", "cursors", "export", session + ".json"))
        return os.stat(ps[0]).st_mtime if ps else 0

    def all_rows(self, session):
        """(loop, row) for every row of the session's transcript and its subagents'."""
        out = []
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", session + ".jsonl")):
            with open(p) as f:
                out += [("main", json.loads(line)) for line in f if line.strip()]
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", session, "subagents", "agent-*.jsonl")):
            loop = os.path.basename(p)[len("agent-"):-len(".jsonl")]
            with open(p) as f:
                out += [(loop, json.loads(line)) for line in f if line.strip()]
        return out

    def watch(self, who):
        path = os.path.join(self.root, "watch-%s.txt" % who)
        p = subprocess.Popen([self.sminos(), "watch", who], cwd=self.work, env=self.local_env(),
                             stdout=open(path, "w"), stderr=subprocess.STDOUT)
        self.procs.append(p)
        self.watchers[who] = (p, path)

    def watched(self, who):
        with open(self.watchers[who][1]) as f:
            return f.read()

    # -- the steps, on one session (`who`, reached through `prompt`)

    def export_check(self, who, stream, session, prompt, label):
        """DC2.G4: a <message> span reaches the log as its row is written, not
        at Stop: its event is stamped within moments of the row's notice and
        before the turn's end (the Stop hook runs only after it); the Stop
        hook's export then finds it there. The model is asked to write the
        mark before a Bash call, where the turn still has work to do."""
        m = self.marker + "x" + label
        t = time.time()
        prompt("In one response, write this line exactly, tags included, and call the Bash tool with the command "
               "below; reply with one short sentence after it runs. The line: <message>EXPORT-%s</message> "
               "The command: python3 -c 'import time; time.sleep(10); print(\"%s\")'" % (m, m))
        wait_for("the message in the log", 90, lambda: [
            e for e in self.log_events(session) if e.get("kind") == "message" and "EXPORT-" + m in str(e.get("text"))])
        end = self.turn_end(stream, t)
        complete = stream.seen(lambda e: is_main(e, "turn", "complete"), t)[0]
        stop_ran = wait_for("the Stop hook's export", 20, lambda: self.position_mtime(session) >= complete["t"] / 1000 - 0.5)
        events = self.log_events(session)
        mine = [e for e in events if e.get("kind") == "message" and "EXPORT-" + m in str(e.get("text"))]
        keys = [(e["kind"], e.get("src")) for e in events if e.get("src")]
        src = mine[0].get("src", "") if mine else ""
        uuid = src.split("#")[0]
        row = next((r for _, r in self.all_rows(session) if r.get("uuid") == uuid), None)
        notice = stream.seen(lambda e: e.get("type") in NOTICES and e.get("uuid") == uuid)
        logged_ms = _ms(mine[0]["ts"]) if mine else 0
        after_notice = (logged_ms - notice[0]["t"]) / 1000 if notice else None
        before_end = (complete["t"] - logged_ms) / 1000
        bash = stream.seen(lambda e: is_main(e, "tool", "result") and m in str(e.get("text")), t)
        before_bash = (bash[0]["t"] - logged_ms) / 1000 if bash else None
        self.check("%s: G4 — a <message> span reaches the log as its row is written, before the turn ends (so not at Stop)" % label,
                   end and notice and after_notice is not None and after_notice < 2 and before_end > 0,
                   "logged %.2f s after its row's notice, %.2f s before the turn's end%s" % (
                       after_notice if after_notice is not None else float("nan"), before_end,
                       "; %.1f s before its Bash call's result (the mark written before the call)" % before_bash
                       if before_bash is not None and before_bash > 0 else
                       "; the model wrote the mark in its final reply, after the Bash call"))
        self.check("%s: G4 — the Stop hook's export then finds it there: one event for its (kind, src), keyed by its transcript row" % label,
                   stop_ran and len(mine) == 1 and row is not None and len(keys) == len(set(keys))
                   and "EXPORT-" + m in json.dumps(row.get("message")),
                   "src %s; %d event(s) for it; the session's file %d keyed events, %d distinct"
                   % (src, len(mine), len(keys), len(set(keys))))
        self.idle(self.endpoint_of(session))

    def async_question_check(self, stream, session, press=False):
        """G4's async question, live; then, with `press`, its `[ answer ]`
        pressed in the terminal."""
        m = self.marker + "q"
        t = time.time()
        self.prompt("Ask me with your question tool, async true, which fruit I prefer, options Apple and Pear. "
                    "Then run exactly this Bash command: python3 -c 'import time; time.sleep(8); print(\"%s\")' "
                    "Then end your turn saying waiting." % m)
        _, raised = self.raised(stream, t, lambda e: e.get("async") is True, "the async question")
        rid = raised["request"]
        logged = wait_for("the question in the log", 60, lambda: [
            e for e in self.log_events(session) if e.get("kind") == "question" and e.get("src") == rid])
        self.turn_end(stream, t)
        complete = stream.seen(lambda e: is_main(e, "turn", "complete"), t)[0]
        self.idle(self.endpoint())
        before_end = (complete["t"] - _ms(logged[0]["ts"])) / 1000
        self.check("terminal: G4 — an async question reaches the log as the call returns, before the turn ends (so not at Stop)",
                   before_end > 0, "question %s logged %.1f s before the turn's end" % (rid[:20], before_end))
        if not press:
            return
        # The `[ answer ]` button: a mouse press at its cell, as the terminal would send it.
        t1 = time.time()
        dialog, _, why = self.press_open("[ answer ]", lambda: "Enter to select" in self.pane() and "Pear" in self.pane())
        s, presses = None, 0
        while dialog and s is None and presses < 4:
            self.keys("Enter")
            presses += 1
            try:
                _, s = self.settled(stream, rid, seconds=5)
            except TimeoutError:
                pass
        woke = []
        if s is not None:
            woke = wait_for("the delivered answer", 60, lambda: stream.seen(
                lambda e: is_main(e, "turn", "start") and "responded to your async" in str(e.get("text")), t1))
            self.turn_end(stream, t1)
            time.sleep(4)
        answered = [e for e in self.log_events(session) if e.get("kind") == "answered" and e.get("src") == rid]
        questions = [e for e in self.log_events(session) if e.get("kind") == "question" and e.get("src") == rid]
        self.check("terminal: an async question's [ answer ] pressed in the terminal answers it, settled as the terminal's",
                   dialog and s is not None and self.outcome(s) == "terminal/answered/terminal" and woke,
                   "%s; settled %s after %d Enter(s); delivered %s"
                   % (why, s and self.outcome(s), presses, bool(woke)))
        self.check("terminal: the question is in the log once, and its answer joins it at the delivering turn's Stop",
                   len(questions) == 1 and len(answered) == 1, "%d question, %d answered" % (len(questions), len(answered)))
        self.idle(self.endpoint())

    def press_walk(self):
        """The ask mod's `[ answer ]` pressed in a terminal. The engine reads
        the mouse only in its fullscreen renderer (CLAUDE_CODE_NO_FLICKER=1),
        so this runs in a session of its own, in its own tmux session."""
        inner = ("set -e; . %s; cd %s; export CLAUDE_CODE_NO_FLICKER=1; exec claude --plugin-dir %s --model haiku "
                 "--permission-mode default -n brpress") % (shlex.quote(self.envfile), shlex.quote(self.work), shlex.quote(self.plugin))
        known = set(os.listdir(os.path.join(self.smh, "bridge"))) if os.path.isdir(os.path.join(self.smh, "bridge")) else set()
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "brp", "-x", "200", "-y", "50",
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)
        found = wait_for("the pressed session's socket", 90, lambda: [
            n for n in os.listdir(os.path.join(self.smh, "bridge")) if n.endswith(".sock") and not n.startswith(".")
            and n not in known] if os.path.isdir(os.path.join(self.smh, "bridge")) else None)
        saved = (self.session, self.target)
        self.session, self.target = found[0][:-5], "brp"
        try:
            wait_for("its endpoint, ready", 20, lambda: (self.status() or {}).get("ready"))
            st = self.streams[self.session] = LC.Stream(self.endpoint())
            wait_for("its subscription", 10, lambda: st.subscriptions > 0)
            self.async_question_check(st, self.session, press=True)
        finally:
            self.session, self.target = saved

    def press(self, label):
        """An SGR mouse press and release on the first cell of `label` on screen."""
        for y, line in enumerate(self.pane().splitlines()):
            x = line.find(label)
            if x >= 0:
                col, row = x + 3, y + 1
                self.keys("-l", "\x1b[<0;%d;%dM" % (col, row))
                self.keys("-l", "\x1b[<0;%d;%dm" % (col, row))
                return "%d,%d" % (col, row)
        return None

    def settle_pane(self, seconds=5):
        """The pane once two captures half a second apart agree (the screen
        redraws, so a cell found on a moving screen may be gone by the press)."""
        deadline, last = time.time() + seconds, None
        while time.time() < deadline:
            now = self.pane()
            if now == last:
                break
            last = now
            time.sleep(0.5)
        return last

    def press_open(self, label, opened, attempts=3, wait=10, appear=15):
        """Press `label` until `opened()` holds: each attempt finds the label
        again on the settled screen, presses it, and waits `wait` s for the
        dialog; no press goes out once it is open. Bounded (`attempts` presses
        over about attempts * (wait + settle) s) so a button that never works
        still fails. Returns (opened, presses, what happened)."""
        presses, cells = 0, []
        for _ in range(attempts):
            try:
                wait_for("%s on screen" % label, appear, lambda: opened() or (self.settle_pane() and label in self.pane()))
            except TimeoutError:
                break
            if opened():
                # A dialog already up before any press was not opened by the button.
                if presses == 0:
                    return False, 0, "the dialog was already open before %s was pressed" % label
                return True, presses, "dialog open after %d press(es) at %s" % (presses, cells)
            cell = self.press(label)
            if cell is None:
                continue
            presses += 1
            cells.append(cell)
            try:
                wait_for("the dialog", wait, opened)
                return True, presses, "dialog open after %d press(es) at %s" % (presses, cells)
            except TimeoutError:
                pass
        if presses == 0:
            return False, 0, "%s never appeared on screen (waited %ds)" % (label, appear)
        return False, presses, "%s pressed %d time(s) at %s and no dialog opened" % (label, presses, cells)

    def subagent_interrupt_check(self, stream):
        """A foreground subagent's Bash under interrupt: the abort ends the
        subagent and moves its Bash to the background; the interrupt stops it."""
        m = self.marker + "sub"
        t = time.time()
        self.prompt("Use the Agent tool exactly once, subagent_type general-purpose, run_in_background false, "
                    "asking it to run exactly this Bash command and then reply done: "
                    "python3 -c 'import time; time.sleep(60); print(\"%s\")'" % m)
        call = wait_for("the subagent's Bash call", 120, lambda: stream.seen(
            lambda e: e.get("type") == "tool" and e.get("phase") == "call" and e.get("agentId")
            and m in json.dumps(e.get("input")), t))
        agent = call[0]["agentId"]
        spawn = stream.seen(lambda e: e.get("type") == "agent" and e.get("phase") == "spawn" and e.get("agentId") == agent, t)
        chunks = stream.seen(lambda e: e.get("type") == "chunk" and e.get("agentId") == agent, t)
        time.sleep(2)
        before = self.running(m)
        r = self.cli("interrupt", NAME)
        time.sleep(3)
        after = self.running(m)
        watched = self.watched(NAME)
        foreground = bool(spawn) and spawn[0].get("background") is False
        self.check("terminal: watch — a subagent's chunks stream tagged with its agentId, and watch labels them",
                   chunks and "[general-purpose " in watched,
                   "agent %s, %d chunks; watch lines %s" % (agent, len(chunks), [l for l in watched.splitlines() if "general-purpose" in l][:2]))
        self.check("terminal: interrupt with a foreground subagent's Bash running stops that Bash too",
                   foreground and before and not after and r.returncode == 0 and "stopped" in r.stdout,
                   "spawned in the %s; python before %s, after %s; %s" % (
                       "foreground" if foreground else "background (the engine's choice)", before, after,
                       (r.stdout + r.stderr).strip()))
        self.idle(self.endpoint(), 150)

    def subagent_check(self, who, stream, endpoint, prompt, label):
        t = time.time()
        prompt("Use the Agent tool exactly once, subagent_type general-purpose, run_in_background false, "
               "asking it to reply with one short sentence about the sea. Then repeat its reply.")
        sub = wait_for("a subagent's text chunk", 150, lambda: stream.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") and e["chunk"].get("kind") == "text", t))
        self.turn_end(stream, t, 180)
        watched = self.watched(who)
        self.check("%s: watch — the stream prints, a subagent's text under its own label" % label,
                   sub and "[main] " in watched and "[general-purpose " in watched,
                   "agent %s; watch lines %s" % (sub[0]["agentId"], [l for l in watched.splitlines() if "general-purpose" in l][:2]))
        self.idle(endpoint)

    def deny_check(self, who, stream, endpoint, prompt, label, session):
        m = self.marker + "deny" + label
        t = time.time()
        prompt("Run exactly this Bash command, then reply in one short sentence: node -e 'console.log(\"%s\")'" % m)
        at, raised = self.raised(stream, t, self.bash_marker(m), m, seconds=120)
        rid = raised["request"]
        if label == "terminal":
            wait_for("the dialog", 20, self.dialog)
        r = self.cli("decide", who, rid, "deny", "--message", "Not now: reply with the word WALNUT and stop.")
        _, s = self.settled(stream, rid)
        closed = True
        if label == "terminal":
            try:
                closed = wait_for("the dialog to close", 5, lambda: not self.dialog())
            except TimeoutError:
                closed = False
        retries = []
        deadline = time.time() + 150
        while not stream.seen(lambda e: is_main(e, "turn", "complete"), t):
            if time.time() > deadline:
                raise TimeoutError("the deny's turn did not end")
            for e in stream.seen(lambda e: e.get("type") == "raised" and self.bash_marker(m)(e), t):
                if e["request"] not in retries + [rid]:
                    retries.append(e["request"])
                    self.cli("decide", who, e["request"], "deny", "--message", "Still no. Reply with the word WALNUT and stop.")
            time.sleep(0.3)
        time.sleep(1)
        rows = [row for _, row in self.all_rows(session) if row.get("type") == "user"
                and rid in json.dumps(row.get("message"))]
        result = next((b for row in rows for b in (row.get("message") or {}).get("content") or []
                       if isinstance(b, dict) and b.get("tool_use_id") == rid), None)
        self.check("%s: decide deny — %sthe transcript shows the denial with its message" % (
                       label, "the terminal's dialog closes; " if label == "terminal" else ""),
                   r.returncode == 0 and self.outcome(s) == "other/deny/cli" and closed and result is not None
                   and result.get("is_error") and "WALNUT" in json.dumps(result),
                   "%s; settled %s; dialog closed %s; result %s%s" % (
                       r.stdout.strip(), self.outcome(s), closed, json.dumps(result)[:120] if result else None,
                       "; the model retried %d time(s)" % len(retries) if retries else ""))
        self.idle(endpoint)
        return rid

    def answer_check(self, who, stream, endpoint, prompt, label):
        t = time.time()
        prompt("Ask me with your question tool (not async) which option I pick, with exactly three options "
               "labelled A, B and C. Then tell me my choice in one sentence, naming its label.")
        at, raised = self.raised(stream, t, lambda e: "questions" in json.dumps(e.get("input")), "the question", seconds=120)
        rid = raised["request"]
        if label == "terminal":
            wait_for("the question's dialog", 20, lambda: "A" in self.pane() and "C" in self.pane())
        r = self.cli("answer", who, rid, "B")
        st, s = self.settled(stream, rid)
        self.turn_end(stream, t)
        text = LC.main_text(stream, st)
        self.check("%s: answer \"B\" — the question continues with B" % label,
                   r.returncode == 0 and self.outcome(s) == "other/answered/cli" and "B" in text,
                   "%s; raised as %s; settled %s; model said %r" % (r.stdout.strip(), raised.get("tool"),
                                                                    self.outcome(s), text[-100:]))
        self.idle(endpoint)

    def compact_check(self, who, stream, endpoint, prompt, label):
        m = self.marker + "c" + label
        t = time.time()
        prompt("Run exactly this Bash command, then reply with one word: "
               "python3 -c 'import time; time.sleep(8); print(\"%s\")'" % m)
        self.bash_call(stream, m, t)
        r = self.cli("compact", who)
        done = self.turn_end(stream, t)
        end = wait_for("the compaction's end", 180, lambda: stream.seen(
            lambda e: e.get("type") == "compact" and e.get("phase") == "end", t))
        start = stream.seen_at(lambda e: e.get("type") == "compact" and e.get("phase") == "start", t)
        turn_t = stream.seen_at(lambda e: is_main(e, "turn", "complete"), t)[0][0]
        self.check("%s: compact during a turn — queued, run at its end" % label,
                   r.returncode == 0 and "queued" in r.stdout and start and start[0][0] >= turn_t
                   and end[0].get("tokensAfter") is not None and done,
                   "%s; then %s" % (r.stdout.strip(), {k: end[0].get(k) for k in ("tokensBefore", "tokensAfter", "error", "skip")}))
        self.idle(endpoint, 180)

    def model_check(self, who, stream, endpoint, prompt, label):
        settings = os.path.join(self.cfg, "settings.json")
        with open(settings, "rb") as f:
            before = (f.read(), os.stat(settings).st_mtime_ns)
        r = self.cli("model", who, "sonnet")
        t = time.time()
        prompt("Reply with exactly: hi")
        self.turn_end(stream, t)
        starts = stream.seen(lambda e: is_main(e, "step", "start"), t)
        used = [str((e.get("usage") or {}).get("model")) for e in stream.seen(lambda e: is_main(e, "step", "end"), t)]
        with open(settings, "rb") as f:
            after = (f.read(), os.stat(settings).st_mtime_ns)
        self.check("%s: model sonnet — the next request on sonnet; settings.json unchanged" % label,
                   r.returncode == 0 and starts and "sonnet" in str(starts[0].get("model")) and used
                   and all("sonnet" in u for u in used) and before == after,
                   "%s; requested %s, answered by %s; settings.json %s" % (
                       r.stdout.strip(), [e.get("model") for e in starts], used, "same" if before == after else "CHANGED"))
        self.idle(endpoint)
        r = self.cli("model", who, "default")
        t = time.time()
        prompt("Reply with exactly: back")
        self.turn_end(stream, t)
        used = [str((e.get("usage") or {}).get("model")) for e in stream.seen(lambda e: is_main(e, "step", "end"), t)]
        self.check("%s: model default returns the session to its own" % label, used and all("haiku" in u for u in used),
                   "%s; answered by %s" % (r.stdout.strip(), used))
        self.idle(endpoint)

    def reload_check(self, stream, session):
        """A module reload in the middle of a streaming response: the reload
        kills the child, the new module's state starts empty, and its resync
        holds nothing of the message in flight."""
        m = self.marker + "rl"
        t = time.time()
        self.prompt("Write a 400-word story about a lighthouse keeper. Use no tools. "
                    "End it with this line exactly, tags included: <message>RELOAD-%s</message>" % m)
        wait_for("the story streaming", 90, lambda: len(stream.seen(
            lambda e: is_main(e, "chunk") and e["chunk"].get("kind") == "text", t)) >= 5)
        old = self.status()["pid"]
        t_reload = time.time()
        with open(os.path.join(self.plugin, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-walk-check: a change that reloads the module mid-response\n")
        new = wait_for("the child after the reload", 60, lambda: (s := self.status()) and s.get("pid") != old and s.get("ready") and s)
        sub = LB.Conn(self.endpoint(), timeout=10)
        sub.request("GET", "/events")
        snap = json.loads(sub.getresponse().readline())
        sub.close()
        # The turn's end, from the session record (the stream may never see it).
        wait_for("the session idle", 150, lambda: self.presence().get("status") == "idle")
        time.sleep(5)
        after = stream.seen_at(lambda e: True, t_reload)
        chunks_after = [e for _, e in after if is_main(e, "chunk")]
        turn_ids = {e["turnId"] for e in stream.seen(lambda e: is_main(e, "turn", "start"), t)}
        completed = [e for _, e in after if is_main(e, "turn", "complete") and e.get("turnId") in turn_ids]
        before_text = "".join(e["chunk"].get("text") or "" for e in stream.seen(
            lambda e: is_main(e, "chunk") and e["chunk"].get("kind") == "text", t) if e["turnId"] in turn_ids)
        claims = [(b.get("text"), before_text) for msg in snap.get("streaming") or [] for b in msg.get("blocks") or []
                  if b.get("kind") == "text" and not before_text.startswith(b.get("text") or "")]
        logged = [e for e in self.log_events(session) if e.get("kind") == "message" and "RELOAD-" + m in str(e.get("text"))]
        t2 = time.time()
        self.prompt("Reply with exactly: ok")
        self.turn_end(stream, t2)
        next_turn = stream.seen(lambda e: is_main(e, "chunk"), t2)
        self.check("terminal: a module reload mid-response — a new child serves, its snapshot claims nothing it did not see, the next turn streams",
                   new and not claims and next_turn,
                   "old %s, new %s; new snapshot: %d streaming, %d turns, cut %s; after the reload %d main chunks, the turn's end %s; next turn %d chunks"
                   % (old, new["pid"], len(snap.get("streaming") or []), len(snap.get("turns") or []), snap.get("cut"),
                      len(chunks_after), "seen" if completed else "not seen", len(next_turn)))
        self.check("terminal: the message the reloaded response carried reaches the log once",
                   len(logged) == 1, "%d event(s), src %s" % (len(logged), logged and logged[0].get("src")))
        self.reload_note = {"chunks_after": len(chunks_after), "completed": bool(completed), "snap_streaming": snap.get("streaming"),
                            "snap_turns": snap.get("turns"), "cut": snap.get("cut")}
        self.idle(self.endpoint())

    def notices_check(self, session, stream, label):
        """Every row the transcripts hold (main and subagents) against the row
        notices the stream carried: each kind with no notice is reported."""
        notices = [e for e in stream.seen(lambda e: e.get("type") in NOTICES)]
        named = {}
        for e in notices:
            named.setdefault(e["uuid"], []).append(e["type"])
        rows = [(loop, r) for loop, r in self.all_rows(session) if r.get("uuid")]
        # A row at or before a later snapshot's cut was named while this
        # subscription was down (a resync, a reload): the snapshot accounts for it.
        covered = set()
        for snap in stream.seen(lambda e: e.get("type") == "snapshot"):
            for loop, at in (snap.get("cut") or {}).items():
                disk = [r["uuid"] for lp, r in rows if lp == loop]
                if at in disk:
                    covered.update(disk[:disk.index(at) + 1])
        missing, kinds = {}, {}
        for loop, r in rows:
            kind = "%s%s" % (r.get("type"), "/" + str((r.get("attachment") or {}).get("type") or r.get("subtype") or "")
                             if r.get("type") in ("attachment", "system") else "")
            kinds[kind] = kinds.get(kind, 0) + 1
            if r["uuid"] not in named and r["uuid"] not in covered:
                missing.setdefault(kind, []).append((loop, r["uuid"][:8], r.get("timestamp")))
        twice = {u: t for u, t in named.items() if len(t) > 1}
        on_disk = {r["uuid"] for _, r in rows}
        unwritten = [u for u in named if u not in on_disk]
        unwritten_doors = {}
        for e in notices:
            if e["uuid"] in unwritten:
                key = "%s/%s" % (e["type"], e.get("door") or "")
                unwritten_doors[key] = unwritten_doors.get(key, 0) + 1
        # Notice order against disk order. A notice that comes after one for a
        # row later on disk is a break. A row-seen break is the engine's disk
        # writer putting a row ahead of its own parentUuid chain within one
        # batch (2.1.300, a first prompt's attachments): the consumer releases
        # the passed-over row unnamed and ignores its late row-seen, so it is
        # reported by kind. A block-row break the rule cannot absorb (it ends
        # the subscription): it fails.
        kind_of = {r["uuid"]: "%s/%s" % (r.get("type"), (r.get("attachment") or {}).get("type") or r.get("subtype") or "")
                   for _, r in rows}
        breaks, quirks = [], {}
        for loop in {lp for lp, _ in rows}:
            at = {r["uuid"]: i for i, (lp, r) in enumerate((lp, r) for lp, r in rows if lp == loop)}
            furthest = None
            for e in notices:
                if (e.get("agentId") or "main") != loop or e["uuid"] not in at:
                    continue
                i = at[e["uuid"]]
                if furthest is not None and i < at[furthest]:
                    if e["type"] == "block-row":
                        breaks.append((loop, e["uuid"][:8], kind_of.get(e["uuid"]), "after", furthest[:8], kind_of.get(furthest)))
                    else:
                        key = "%s before %s" % (kind_of.get(furthest), kind_of.get(e["uuid"]))
                        quirks[key] = quirks.get(key, 0) + 1
                if furthest is None or i > at[furthest]:
                    furthest = e["uuid"]
        # From a row's flush to its notice: the consumer releases a row with
        # no notice after UNNAMED_AFTER, so a lag near it would break a
        # response row from its streaming block. While chunks stream, posts
        # carry them beside the notices: measured there too.
        disk = self.disks.get(session)
        steps = {}
        for t_e, e in stream.seen_at(lambda e: e.get("type") == "step"):
            key = (e.get("turnId"), e.get("agentId"), e.get("step"))
            steps.setdefault(key, [None, None])[0 if e.get("phase") == "start" else 1] = t_e
        windows = [(a, b if b is not None else float("inf")) for a, b in steps.values() if a is not None]
        lags = []
        for t_n, e in stream.seen_at(lambda e: e.get("type") in NOTICES):
            flushed = disk.first_seen.get(e["uuid"]) if disk else None
            if flushed is not None:
                lags.append((t_n - flushed, any(a <= flushed <= b for a, b in windows), e["uuid"][:8], e["type"]))
        top = max(lags, default=None)
        top_streaming = max((x for x in lags if x[1]), default=None)
        lag = {"measured": len(lags), "max_s": top and round(top[0], 3), "max_row": top and top[2:],
               "max_while_streaming_s": top_streaming and round(top_streaming[0], 3),
               "while_streaming": sum(1 for x in lags if x[1]), "poll_s": DISK_POLL}
        # A step's end follows every block-row of that step on the stream
        # (DX4's step-end, which DC7 relays, relies on it).
        late_rows, ended = [], {}
        for e in stream.seen(lambda e: e.get("type") in ("step", "block-row")):
            key = (e.get("turnId"), e.get("agentId"), e.get("step"))
            if e["type"] == "step" and e.get("phase") == "end":
                ended[key] = True
            elif e["type"] == "block-row" and ended.get(key):
                late_rows.append((e["uuid"][:8],) + key)
        # Live thinking: what a thinking chunk carries (2.1.300's transcript keeps it omitted).
        thinking = stream.seen(lambda e: e.get("type") == "chunk" and (e.get("chunk") or {}).get("kind") == "thinking")
        think = {"chunks": len(thinking), "text_chars": sum(len((e["chunk"].get("text") or "")) for e in thinking),
                 "keys": sorted({k for e in thinking for k in e["chunk"]}),
                 "sample": [str(e["chunk"])[:160] for e in thinking[:2]]}
        with open(os.path.join(self.root, "notices-%s.json" % label), "w") as f:
            json.dump({"notices": notices, "rows": rows, "lags": lags}, f)
        self.notice_report = getattr(self, "notice_report", {})
        self.notice_report[label] = {"rows": len(rows), "kinds": kinds, "missing": {k: len(v) for k, v in missing.items()},
                                     "missing_examples": {k: v[:3] for k, v in missing.items()},
                                     "twice": len(twice), "unwritten": len(unwritten), "unwritten_doors": unwritten_doors,
                                     "order_breaks": breaks, "write_order_quirks": quirks, "covered_by_a_snapshot": len(covered),
                                     "subscriptions": stream.subscriptions, "flush_to_notice": lag,
                                     "block_rows_after_step_end": late_rows, "thinking": think}
        self.check("%s: row notices against the transcripts (main and subagents): none twice, none for a row never written, no block-row after a notice for a row later on disk, each within the 2 s window of its flush; the kinds with none, and the engine's write-order quirks, reported" % label,
                   not twice and not unwritten and not breaks and (top is None or top[0] < UNNAMED_AFTER),
                   "%d rows, %d notices; without one, by kind: %s; noticed twice %d; noticed, never written %d %s; block-row breaks %s; "
                   "write-order quirks (row-seen) %s; "
                   "flush to notice: max %s s (%s), while chunks stream %s s over %d rows; subscriptions %d"
                   % (len(rows), len(notices), {k: len(v) for k, v in missing.items()} or "none", len(twice), len(unwritten),
                      unwritten_doors, breaks or 0, quirks or "none", lag["max_s"], lag["max_row"], lag["max_while_streaming_s"],
                      lag["while_streaming"], stream.subscriptions))
        self.check("%s: every block-row reaches the stream before its step's end" % label, not late_rows,
                   "%d block-rows, %d after their step's end %s" % (
                       len(stream.seen(lambda e: e.get("type") == "block-row")), len(late_rows), late_rows[:5]))

    def endpoint_of(self, session):
        return os.path.join(self.smh, "bridge", session + ".sock")

    # -- the --bg job's settlement cases

    def bg_settlement(self, short, stream, endpoint, prompt, rid):
        late = self.cli("decide", BG, rid, "allow")
        sub = LB.Conn(endpoint, timeout=10)
        sub.request("GET", "/events")
        snap = json.loads(sub.getresponse().readline())
        sub.close()
        self.check("bg: a late answer is refused as already settled; a client reconnecting after it sees it settled",
                   late.returncode == 1 and "already settled" in late.stderr
                   and any(s.get("request") == rid for s in snap.get("settled") or [])
                   and not any(p.get("request") == rid for p in snap.get("pending") or []),
                   late.stderr.strip())
        # The terminal first: the job attached in a terminal, its dialog answered there.
        inner = "set -e; . %s; cd %s; exec claude attach %s" % (shlex.quote(self.envfile), shlex.quote(self.work), short)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "att", "-x", "200", "-y", "50",
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)
        target = "att"
        m = self.marker + "att"
        t = time.time()
        prompt("Run exactly this Bash command, then reply in one short sentence: node -e 'console.log(\"%s\")'" % m)
        _, raised = self.raised(stream, t, self.bash_marker(m), m, seconds=120)
        pane = lambda: subprocess.run(self.tmux + ["capture-pane", "-p", "-t", target], capture_output=True, text=True).stdout  # noqa: E731
        shown = False
        try:
            shown = wait_for("the dialog in the attached terminal", 30, lambda: DIALOG in pane())
        except TimeoutError:
            pass
        s = None
        if shown:
            time.sleep(1)
            subprocess.run(self.tmux + ["send-keys", "-t", target, "Enter"], check=True)
            try:
                _, s = self.settled(stream, raised["request"], seconds=20)
            except TimeoutError:
                pass
        if s is None:
            self.cli("decide", BG, raised["request"], "allow")
            _, s = self.settled(stream, raised["request"])
        self.turn_end(stream, t)
        self.check("bg: the terminal first — the job attached with `claude attach`, its dialog answered there, settled as the terminal's",
                   shown and self.outcome(s) == "terminal/allow/terminal",
                   "dialog in the attached terminal %s; settled %s%s" % (
                       shown, self.outcome(s), "" if shown else "; last screen: %r" % pane().strip()[-200:]))
        subprocess.run(self.tmux + ["kill-session", "-t", target], capture_output=True)
        self.idle(endpoint)

    # -- the walk

    def terminal(self):
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer, ready", 20, lambda: (self.status() or {}).get("ready"))
        self.disks[self.session] = DiskWatch(self.cfg, self.session)
        term = self.streams[self.session] = LC.Stream(self.endpoint())
        wait_for("the subscription", 10, lambda: term.subscriptions > 0)
        self.watch(NAME)
        self.export_check(NAME, term, self.session, self.prompt, "terminal")
        self.subagent_interrupt_check(term)
        self.steer_check(NAME, term, self.endpoint(), self.prompt, "terminal")
        self.interrupt_check(NAME, term, self.endpoint(), self.prompt, "terminal")
        self.deny_check(NAME, term, self.endpoint(), self.prompt, "terminal", self.session)
        self.answer_check(NAME, term, self.endpoint(), self.prompt, "terminal")
        self.async_question_check(term, self.session)
        self.compact_check(NAME, term, self.endpoint(), self.prompt, "terminal")
        self.model_check(NAME, term, self.endpoint(), self.prompt, "terminal")
        self.reload_check(term, self.session)
        watched = self.watched(NAME)
        self.check("terminal: watch printed the walk — the conversation, requests raised and settled",
                   "[main] " in watched and "permission: Bash" in watched and "settled: deny (cli)" in watched,
                   "%d lines" % len(watched.splitlines()))
        self.notices_check(self.session, term, "terminal")

    def bg(self):
        r = self.claude(["--bg", "--plugin-dir", self.plugin, "--model", "haiku", "--permission-mode", "default",
                         "-n", BG, FIRST_PROMPT])
        rec = wait_for("the bg job's record", 60, lambda: self.record(BG))
        short = rec.get("jobId")
        self.jobs.append(short)
        session = rec["sessionId"]
        sock = self.endpoint_of(session)
        wait_for("the bg job's endpoint", 60, lambda: os.path.exists(sock)
                 and (LB.request(sock, "GET", "/status", timeout=3)[1] or {}).get("ready"))
        self.disks[session] = DiskWatch(self.cfg, session)
        bg = self.streams[session] = LC.Stream(sock)
        wait_for("the bg subscription", 10, lambda: bg.subscriptions > 0)
        self.idle(sock)
        self.check("bg: the job has a bridge, ready", rec.get("kind") == "bg", "job %s, session %s" % (short, session[:8]))
        # A job started with a prompt: the module loads before the prompt's
        # row (no message at load), so its main loop is fresh and its first
        # reply streams, though its request may begin before the child's hello.
        first = "".join(e["chunk"].get("text") or "" for e in bg.seen(lambda e: is_main(e, "chunk") and e["chunk"].get("kind") == "text"))
        self.check("bg: a fresh job's first reply streams (its main loop seen from its first row, no seed held it back)",
                   "READY" in first, "%d characters streamed, ending %r" % (len(first), first[-40:]))
        self.watch(BG)

        def say_bg(text):
            out = self.cli("say", "@%s %s" % (BG, text))
            if out.returncode != 0 or "sent" not in out.stdout:
                raise RuntimeError("say to %s: %s" % (BG, (out.stdout + out.stderr).strip()))
        self.export_check(BG, bg, session, say_bg, "bg")
        self.subagent_check(BG, bg, sock, say_bg, "bg")
        self.steer_check(BG, bg, sock, say_bg, "bg")
        self.interrupt_check(BG, bg, sock, say_bg, "bg")
        rid = self.deny_check(BG, bg, sock, say_bg, "bg", session)
        self.bg_settlement(short, bg, sock, say_bg, rid)
        self.answer_check(BG, bg, sock, say_bg, "bg")
        self.compact_check(BG, bg, sock, say_bg, "bg")
        self.model_check(BG, bg, sock, say_bg, "bg")
        watched = self.watched(BG)
        self.check("bg: watch printed the walk — the conversation, requests raised and settled",
                   "[main] " in watched and "permission: Bash" in watched and "settled: deny (cli)" in watched,
                   "%d lines" % len(watched.splitlines()))
        self.notices_check(session, bg, "bg")

    def seat(self):
        settings = json.dumps({"env": {"CLAUDE_CODE_PLUGIN_DIRS": self.plugin}})
        # Launched from the session's own environment (the env file): a seat
        # launched without the gateway's keys answered "Not logged in".
        args = " ".join(shlex.quote(a) for a in (self.sminos(), "spawn", SEAT, "Reply with exactly the word READY.",
                                                  "--model", "haiku", "--settings", settings))
        r = subprocess.run(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", "set -e; . %s; cd %s; exec %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), args)], capture_output=True, text=True, timeout=300)
        rec = wait_for("the seat's record", 90, lambda: self.record(SEAT))
        self.jobs.append(rec.get("jobId"))
        sock = self.endpoint_of(rec["sessionId"])
        wait_for("the seat's endpoint", 60, lambda: os.path.exists(sock)
                 and (LB.request(sock, "GET", "/status", timeout=3)[1] or {}).get("ready"))
        st = self.streams[rec["sessionId"]] = LC.Stream(sock)
        wait_for("the seat subscription", 10, lambda: st.subscriptions > 0)
        self.idle(sock)
        t = time.time()
        sent = self.cli("send", SEAT, "Reply with exactly the word FIG.", "--wait", timeout=300)
        delivered = st.seen(lambda e: e.get("type") == "delivered" and e.get("outcome") == "submitted", t)
        started = st.seen(lambda e: is_main(e, "turn", "start") and "FIG" in str(e.get("text")), t)
        self.check("seat: send --wait through a bridged seat — delivered through the bridge, the reply waited for",
                   r.returncode == 0 and sent.returncode == 0 and "FIG" in sent.stdout and delivered and started,
                   "spawn rc %d; send rc %d: %r; delivered %d, turn %s" % (
                       r.returncode, sent.returncode, (sent.stdout + sent.stderr).strip()[-160:], len(delivered),
                       started and str(started[0].get("text"))[:60]))

    def run(self):
        self.setup()
        if "terminal" in self.only:
            self.terminal()
        if "bg" in self.only:
            self.bg()
        if "seat" in self.only:
            self.seat()
        if "press" in self.only:
            self.press_walk()

    def cleanup(self):
        for p, _ in self.watchers.values():
            if p.poll() is None:
                p.terminate()
        for st in self.streams.values():
            st.stop.set()
        for d in getattr(self, "disks", {}).values():
            d.stop.set()
        super().cleanup()


def _ms(ts):
    """An ISO 8601 UTC stamp with milliseconds, as epoch ms."""
    import calendar
    head, _, frac = ts.rstrip("Z").partition(".")
    return calendar.timegm(time.strptime(head, "%Y-%m-%dT%H:%M:%S")) * 1000 + int((frac or "0")[:3].ljust(3, "0"))


def main():
    args = sys.argv[1:]
    only = {"terminal", "bg", "seat", "press"}
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    live = Walk("--keep" in args, only)
    print("live walk (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a walk that cannot go on is a failed check
        live.check("the walk ran to its end", False, "%s: %s" % (type(e).__name__, e))
        print("  pane at the failure:\n" + "\n".join("    " + line for line in live.pane().rstrip().splitlines()[-25:]))
    finally:
        for label, rep in (getattr(live, "notice_report", None) or {}).items():
            print("  notices (%s): %s" % (label, json.dumps(rep)))
        if getattr(live, "reload_note", None):
            print("  reload mid-response: %s" % json.dumps(live.reload_note)[:600])
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed), len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
