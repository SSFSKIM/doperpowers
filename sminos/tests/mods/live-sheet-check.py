#!/usr/bin/env python3
"""Live check of the question sheet's mod against the engine itself (plan
docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, "The live
check": M3 builds it, M4 to M6 add cases, M7 runs it whole).

What only a running engine shows, pinned so a release that breaks it fails
loudly: the tool as the model reads it, a call's result, the references read
through the engine's own Read and refused where the session's permissions
refuse them, the record the step keeps, the door's verdicts through the
bridge, a fork's ids, and the start choice where the sheet is not chosen.
Its expectations are those of the engine C0 probed (2.1.331); a case that
rests on a probe's answer names it.

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand on a Mac with the model gateway's keys in the environment. Isolation is
live-bridge-check.py's (whose class it extends): a temporary HOME whose
.claude is the config dir, a temporary SMINOS_HOME, a copy of the checkout's
sminos plugin loaded with --plugin-dir, a tmux server of its own, and the
stand-in surface (sminos/tests/sheet_surface.py); every process it started is
stopped at its end.

    sminos/tests/mods/live-sheet-check.py [--case <name>]... [--guard-plugin <dir>] [--keep]

`--guard-plugin` loads the owner's secrets guard (devcloud's, as installed: give its directory, found on the
machine at run time) into the scratch sessions beside the checkout's sminos, so `secret` observes what that guard
does to a capture; without it that part of `secret` is SKIPPED, never passed.

Cases (M3's): many, revise, withdraw, two-surfaces, secret, fork (one
terminal session asks, revises, withdraws; a subagent's acts; the door;
the refused references; its copies by --fork-session and /branch, and what
each copy's first context says), then no-surface and nested (sessions of
their own). `many` comes first whatever is asked: the cases after it act on
its questions. M4's, in a session of their own that asks for them: rendering
(an envelope by each route, read back where the mod's landing hook and a
start's search read it), subset, note, dismiss, compaction, both, subagent,
agent-open, then stopped (the session ended, answered, resumed); and
max-send, in one more session. M5's: the band line and the rows in `many` and
`withdraw`, and import (a session's asks of today's tool, made with the
setting off, moved onto the sheet when it resumes under it: not on a read
that cannot be whole, once after more resumes, and never into a fork). It
ends `live-sheet-check: N passed` and
exits 0; a failing check prints `FAIL <case>: <what was observed>`.
"""
import os.path, runpy  # noqa: E401 — the caller's repository kept out first (#623)
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../git_isolation.py"))

import glob
import importlib.util
import json
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

SHEET_TOOL = "mcp__sminos__AskUserQuestion"
SURFACE = os.path.join(HERE, "..", "sheet_surface.py")
NO_SURFACE = "No surface can show these questions right now; they wait on the sheet and show when one returns."
NOTES = "first line of the notes\nsecond line of the notes\n"
SECRET = "LIVE_SHEET_SECRET_VALUE_7f3a"
OUTSIDE = "LIVE_SHEET_OUTSIDE_MARKER_c91e"
# A token of a credential's shape, made at run time (nothing of the kind is in the repository): what a secrets
# guard is for.
GUARDED = "ghp_" + uuid.uuid4().hex + uuid.uuid4().hex[:4]
DOOR_S = 1.0          # M3's At its end: a `put` to a live session prints its verdict within a second
DELIVERY = ("rendering", "subset", "note", "dismiss", "compaction", "both", "subagent", "agent-open", "stopped")
CASES = ("many", "revise", "withdraw", "two-surfaces", "secret", "fork", "import", "no-surface", "nested") + DELIVERY + ("max-send",)
SURFACE_URL = "http://sheet.localhost:47590"     # the stand-in's default
MOVED = "Moved onto the sheet from the earlier question tool: "
READ_LIMIT = 4 * 1024 * 1024                     # what ask.tsx reads whole; a transcript past it is searched
# What a session that delivers is told once, so the model's reply shows what it read (the cases match words of it).
REPEAT = ("When answers from the human's question sheet reach you later, reply by repeating each one: its question "
          "id, the option picked, and the human's text word for word, and name every question dismissed. Do not read "
          "any file an answer points to. ")
SUBAGENT_OPENING = "From the human, through the question tool, not from your coordinator: answers to questions you put on the sheet."
BLOCK = re.compile(r"^<sheet-delivery>(.*)</sheet-delivery>$")


def envelope_head(text):
    """An envelope's first line: a plugin prompt's row opens with the engine's frame first."""
    lines = text.split("\n")
    return lines[1] if lines[0] == "The sminos plugin sent a message:" and len(lines) > 1 else lines[0]


def blocks(text):
    """The <sheet-delivery> blocks a text holds, each a whole line (I7): (keys, answered ids, dismissed ids, more)."""
    out = []
    for line in (text or "").split("\n"):
        m = BLOCK.match(line)
        if not m:
            continue
        try:
            b = json.loads(m.group(1))
        except ValueError:
            continue
        out.append((b.get("keys", []), [a.get("id") for a in b.get("answered", [])], b.get("dismissed", []), bool(b.get("more"))))
    return out


def call_prompt(payload, preface=""):
    return (preface + "Call the tool %s exactly once, with exactly this JSON as its input: %s . "
            "Then reply with only the first line of the tool's result." % (SHEET_TOOL, json.dumps(payload)))


def gist(payload):
    """A call's input by its questions, their references' paths and its withdrawals: what a model copying the input
    keeps, whatever it adds."""
    payload = payload if isinstance(payload, dict) else {}
    return ([(e.get("question"), [r.get("path") for r in e.get("references") or [] if isinstance(r, dict)])
             for e in payload.get("ask") or [] if isinstance(e, dict)], payload.get("withdraw") or [])


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


class Sheet(LB.Live):
    def __init__(self, keep, cases, guard=None):
        super().__init__(keep)
        self.guard = guard
        self.skipped = []        # (name, why)
        self.tmux = ["tmux", "-L", "shl-%d" % os.getpid(), "-f", "/dev/null"]
        self.cases = cases
        self.surface = None
        self.panes = {}          # tmux session name -> the engine session id it holds now
        self.outside = os.path.join(self.root, "outside", "elsewhere.txt")

    # -- isolation

    def setup(self):
        super().setup()
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": [SHEET_TOOL, "Agent", "Task", "Bash(sleep:*)"], "deny": ["Read(**/.env)"]}}, f)
        with open(os.path.join(self.work, "notes.txt"), "w") as f:
            f.write(NOTES)
        with open(os.path.join(self.work, ".env"), "w") as f:
            f.write("TOKEN=%s\n" % SECRET)
        os.makedirs(os.path.dirname(self.outside))
        with open(self.outside, "w") as f:
            f.write(OUTSIDE + "\n")
        with open(os.path.join(self.work, "deploy.cfg"), "w") as f:
            f.write("github_token = %s\n" % GUARDED)
        self.surface_up()

    def surface_up(self):
        self.surface = subprocess.Popen([sys.executable, "-B", SURFACE, "--every", "2"], env=self.local_env(),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(self.surface)
        wait_for("the stand-in's registration", 10, lambda: self.surfaces_alive())

    def surface_down(self):
        self.surface.send_signal(signal.SIGTERM)
        self.surface.wait(10)
        wait_for("the stand-in's registration gone", 10, lambda: not self.surfaces_alive())

    def surfaces_alive(self):
        r = self.cli("sheet", "surfaces", "--json")
        return [s for s in json.loads(r.stdout or "{}").get("surfaces", []) if s.get("alive")] if r.returncode == 0 else []

    def cli(self, *args, stdin=None, timeout=60):
        return subprocess.run([self.sminos(), *args], cwd=self.work, env=self.local_env(), input=stdin,
                              capture_output=True, text=True, timeout=timeout)

    # -- a terminal session

    def open(self, name, args=(), env=None):
        """A terminal session in this check's tmux server, `env` exported over the env file's, with a debug log."""
        exports = "".join("export %s=%s; " % (k, shlex.quote(v)) for k, v in (env or {}).items())
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in [self.plugin] + ([self.guard] if self.guard else []))
        debug = os.path.join(self.root, "debug-%s.log" % name)
        inner = "set -e; . %s; %scd %s; exec claude %s --model haiku --permission-mode default --debug-file %s %s" % (
            shlex.quote(self.envfile), exports, shlex.quote(self.work), dirs, shlex.quote(debug),
            " ".join(shlex.quote(a) for a in args))
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        known = set(self.presences())
        subprocess.run(self.tmux + ["new-session", "-d", "-s", name, "-x", "200", "-y", "50", cmd], check=True)
        # The engine's presence record of the process: the pane's own pid need not be the engine's (a launcher
        # on PATH may start it as a child), so the record that is new names both.
        pid, sid = wait_for("%s's session" % name, 90, lambda: next(iter(set(self.presences()) - known), None))
        self.panes[name] = (pid, sid)
        wait_for("%s's bridge" % name, 60, lambda: self.ping(sid))
        return sid

    def close(self, name):
        subprocess.run(self.tmux + ["kill-session", "-t", name], capture_output=True)

    def presences(self):
        """(pid, session id) of each live process's presence record."""
        out = []
        for p in glob.glob(os.path.join(self.cfg, "sessions", "*.json")):
            try:
                with open(p) as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if rec.get("pid") and rec.get("sessionId") and LB._alive(rec["pid"]):
                out.append((rec["pid"], rec["sessionId"]))
        return out

    def session_of(self, pid):
        return next((sid for p, sid in self.presences() if p == pid), None)

    def debug(self, name):
        try:
            with open(os.path.join(self.root, "debug-%s.log" % name), errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def ping(self, sid):
        try:
            s, body = LB.request(os.path.join(self.smh, "bridge", sid + ".sock"), "POST", "/command?wait=8000",
                                 {"op": "ping"}, timeout=15)
        except OSError:
            return None
        return body if s == 200 and body.get("ok") else None

    def idle(self, sid, seconds=180):
        calm = None
        deadline = time.time() + seconds
        while time.time() < deadline:
            body = self.ping(sid)
            if body is not None and body["result"]["state"]["mainTurn"] is None:
                calm = calm or time.time()
                if time.time() - calm >= 2:
                    return
            else:
                calm = None
            time.sleep(0.5)
        raise TimeoutError("the session did not go idle")

    def say(self, name, text):
        self.keys_to(name, "-l", text)
        time.sleep(0.4)
        self.keys_to(name, "Enter")

    def pane_of(self, name):
        r = subprocess.run(self.tmux + ["capture-pane", "-p", "-t", name], capture_output=True, text=True)
        return r.stdout

    def keys_to(self, name, *keys):
        subprocess.run(self.tmux + ["send-keys", "-t", name] + list(keys), check=True)

    def rows(self, sid, sub=False):
        pattern = os.path.join(self.cfg, "projects", "*", sid, "subagents", "*.jsonl") if sub else \
            os.path.join(self.cfg, "projects", "*", sid + ".jsonl")
        out = []
        for p in glob.glob(pattern):
            with open(p, errors="replace") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        return out

    def calls(self, sid, sub=False, ids=False):
        """The sheet tool's calls in a transcript, in order: (input, result text or None), with each call's id
        first when `ids`."""
        uses, results = [], {}
        for row in self.rows(sid, sub):
            content = (row.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "tool_use" and b.get("name") == SHEET_TOOL:
                    uses.append((b["id"], b.get("input")))
                elif b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = text_of(b.get("content"))
        return [(u, i, results.get(u)) if ids else (i, results.get(u)) for u, i in uses]

    def ask(self, name, payload, seconds=180, preface=""):
        """The agent calls the tool with `payload`: its result, once the turn is over."""
        sid = self.panes[name][1]
        # Known by its input, not its place: a fork's transcript is written with the conversation it copied only
        # once its first prompt is (C0's P5), after the count a place would rest on.
        before = {u for u, _, _ in self.calls(sid, ids=True)}
        self.say(name, call_prompt(payload, preface))
        got = wait_for("the call's result", seconds, lambda: [
            r for u, i, r in self.calls(sid, ids=True) if u not in before and gist(i) == gist(payload) and r is not None])
        self.idle(sid)
        return got[0]

    def show(self, sid):
        r = self.cli("sheet", "show", "--session", sid, "--json")
        return json.loads(r.stdout) if r.returncode == 0 else None

    def state(self, sid):
        with open(os.path.join(self.smh, "sheet", sid, "state.json")) as f:
            return json.load(f)

    def put(self, sid, lines):
        r = self.cli("sheet", "put", "--session", sid, stdin="".join(json.dumps(x) + "\n" for x in lines))
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stderr.strip()

    def check(self, name, ok, detail):
        self.results.append((name, bool(ok), detail))
        print("  %s %s — %s" % ("ok  " if ok else "FAIL", name, detail), flush=True)

    def skip(self, name, why):
        self.skipped.append((name, why))
        print("  SKIP %s — %s" % (name, why), flush=True)

    def timed_put(self, sid, lines):
        """`put`, and how long it took to print."""
        t0 = time.monotonic()
        code, out, err = self.put(sid, lines)
        return code, out, err, time.monotonic() - t0

    def wants(self, case):
        return not self.cases or case in self.cases

    # -- the cases

    def run(self):
        self.setup()
        main = self.open("main", env={"SMINOS_QUESTION_SHEET": "1"})
        self.case_many(main)
        if self.wants("revise"):
            self.case_revise(main)
        if self.wants("withdraw"):
            self.case_withdraw(main)
        if self.wants("two-surfaces"):
            self.case_two_surfaces(main)
        if self.wants("secret"):
            self.case_secret(main)
        if self.wants("fork"):
            self.case_fork(main)
        self.close("main")
        if self.wants("import"):
            self.case_import()
        if any(self.wants(c) for c in DELIVERY):
            self.delivery()
        if self.wants("max-send"):
            self.case_max_send()
        if self.wants("no-surface"):
            self.case_no_surface()
        if self.wants("nested"):
            self.case_nested()

    def case_many(self, sid):
        entries = [{"question": "Question %d: which fruit?" % i, "header": "Fruit %d" % i,
                    "options": [{"label": "Apple"}, {"label": "Pear"}]} for i in range(1, 9)]
        entries[0]["references"] = [{"path": "notes.txt"}]
        result = self.ask("main", {"ask": entries})
        first = result.splitlines()[0] if result else ""
        self.check("many: one call adds eight questions", first == "Added q1, q2, q3, q4, q5, q6, q7, q8.", repr(result))
        m = self.show(sid) or {}
        opened = [q["id"] for q in m.get("open", [])]
        ref = ((m.get("open") or [{}])[0].get("references") or [{}])[0]
        body = ""
        if ref.get("sha256"):
            with open(os.path.join(self.smh, "sheet", sid, "refs", ref["sha256"]), errors="replace") as f:
                body = f.read()
        self.check("many: show lists the eight and the file as captured", opened == ["q%d" % i for i in range(1, 9)]
                   and body == NOTES and ref.get("changed") is False, "open %s; reference %s; body %r" % (opened, ref, body))
        with open(os.path.join(self.work, "notes.txt"), "a") as f:
            f.write("a line added after the question\n")
        ref = (((self.show(sid) or {}).get("open") or [{}])[0].get("references") or [{}])[0]
        self.check("many: the file edited since reads changed", ref.get("changed") is True, ref)
        tools = self.debug("main")
        self.check("many: the start chose the sheet", "sheet: sheet (terminal)" in tools,
                   [line for line in tools.splitlines() if "sheet: " in line][:3])
        self.check_band("many", "main", sid, 8)
        pane = self.pane_of("main")
        lines = ["q%d Fruit %d — Question %d: which fruit?" % (i, i, i) for i in range(1, 9)]
        self.check("many: the call's row lists its eight questions, one line each, under the engine's head",
                   all(x in pane for x in lines) and "⎿  q1 Fruit 1 — " in pane, self.pane_lines("main", "q"))

    def band(self, sid, n):
        return "%d open question%s · %s/s/%s" % (n, "" if n == 1 else "s", SURFACE_URL, sid)

    def check_band(self, case, name, sid, n):
        """The line above the prompt names the `n` open questions and the stand-in's link to the session's sheet."""
        try:
            wait_for("the band line", 20, lambda: self.band(sid, n) in self.pane_of(name))
        except TimeoutError:
            pass
        self.check("%s: the line above the prompt reads %r" % (case, self.band(sid, n)), self.band(sid, n) in self.pane_of(name),
                   self.pane_lines(name, "open question"))

    def pane_lines(self, name, needle):
        return [x.strip() for x in self.pane_of(name).splitlines() if needle in x]

    def case_revise(self, sid):
        result = self.ask("main", {"ask": [{"id": "q2", "question": "Question 2, revised: which colour?",
                                            "options": [{"label": "Red"}, {"label": "Blue"}]}]})
        self.check("revise: the agent revises q2", re.match(r"Revised q2\b", result or ""), repr(result))
        r = self.cli("sheet", "answer", "--session", sid, "q2", "--pick", "1")
        self.check("revise: an answer to q2 at its first revision is refused, naming q2@2",
                   r.returncode == 2 and "q2@2" in r.stderr, "exit %s: %s" % (r.returncode, r.stderr.strip()))
        key = "live-stale-%s" % uuid.uuid4().hex[:12]
        code, out, err, took = self.timed_put(sid, [{"v": 1, "key": key, "kind": "answer", "id": "q2", "revision": 1,
                                                     "picks": ["Apple"], "by": "cli"}])
        verdict = ((out or {}).get("results") or [{}])[0]
        self.check("revise: a door line at revision 1 is stale, current 2, its verdict printed within %ss (the "
                   "bridge's sheet op answered it)" % DOOR_S,
                   code == 0 and verdict.get("state") == "stale" and verdict.get("current") == 2 and took < DOOR_S,
                   "%.2fs; %s" % (took, (code, out, err)))
        r = self.cli("sheet", "answer", "--session", sid, "q2@2", "--pick", "1")
        out = json.loads(r.stdout) if r.returncode == 0 else {}
        m = self.show(sid) or {}
        pending = [o for o in m.get("pending", []) if o.get("id") == "q2"]
        closed = (m.get("closed") or {}).get("q2") or {}
        # From M4 the answer is delivered at once to an idle session: pending, or already delivered, it picked Red.
        self.check("revise: q2@2 --pick 1 is applied to the new first option",
                   r.returncode == 0 and ((pending and pending[0].get("picks") == ["Red"]) or closed.get("receipt") == "Red"),
                   "%s; pending %s; closed %s" % (out or r.stderr.strip(), pending, closed))
        self.idle(sid)

    def case_withdraw(self, sid):
        result = self.ask("main", {"withdraw": ["q3"]})
        opened = [q["id"] for q in (self.show(sid) or {}).get("open", [])]
        self.check("withdraw: the agent withdraws q3; show no longer lists it",
                   result.startswith("Withdrew q3.") and "q3" not in opened, "%r; open %s" % (result, opened))
        self.check("withdraw: the call's row draws q3 · Withdrawn", "⎿  q3 · Withdrawn" in self.pane_of("main"),
                   self.pane_lines("main", "q3"))
        self.check_band("withdraw", "main", sid, len(opened))
        inner = call_prompt({"ask": [{"id": "q4", "question": "Changed by a subagent?"}], "withdraw": ["q5"]})
        before = len(self.calls(sid, sub=True))
        self.say("main", "Use the Agent tool once (subagent_type general-purpose) with this as its whole prompt: %s "
                         "Then reply with only what the agent reported." % json.dumps(inner))
        try:
            got = wait_for("the subagent's call's result", 240,
                           lambda: [r for _, r in self.calls(sid, sub=True)[before:] if r is not None])
        except TimeoutError:
            got = []
        self.idle(sid)
        qs = {q["id"]: q for q in self.state(sid)["questions"]}
        q4 = qs.get("q4") or {}
        self.check("withdraw: a subagent's revise and withdraw of the main agent's questions are both refused",
                   got and "Not done:" in got[0] and q4.get("revision") == 1 and q4.get("asker") == "main" and "q5" in qs,
                   "subagent's result %r; q4 revision %s asker %s; q5 %s" % (
                       got[0] if got else None, q4.get("revision"), q4.get("asker"), "open" if "q5" in qs else "gone"))

    def case_two_surfaces(self, sid):
        one, two = ("live-two-%d-%s" % (n, uuid.uuid4().hex[:10]) for n in (1, 2))
        line = {"v": 1, "kind": "answer", "id": "q6", "revision": 1, "picks": ["Pear"], "by": "cli"}
        _, a, _, ta = self.timed_put(sid, [dict(line, key=one)])
        _, b, _, tb = self.timed_put(sid, [dict(line, key=two)])
        sa, sb = (((x or {}).get("results") or [{}])[0].get("state") for x in (a, b))
        self.idle(sid)
        self.check("two-surfaces: two answers to one question: the first taken, the second closed, each verdict "
                   "within %ss" % DOOR_S,
                   sa in ("accepted", "applied", "delivered") and sb == "closed" and max(ta, tb) < DOOR_S,
                   "%.2fs, %.2fs; %s" % (ta, tb, (a, b)))
        self.surface_down()
        result = self.ask("main", {"ask": [{"question": "Asked with no surface up?"}]})
        self.check("two-surfaces: with the stand-in stopped the result ends with the no-surface sentence",
                   result.rstrip().endswith(NO_SURFACE), repr(result))
        self.surface_up()
        added = re.match(r"Added (q\d+)\.", result)
        opened = [q["id"] for q in (self.show(sid) or {}).get("open", [])]
        self.check("two-surfaces: the stand-in back, show lists the question",
                   added and added.group(1) in opened, "open %s" % opened)

    def case_secret(self, sid):
        result = self.ask("main", {"ask": [
            {"question": "About the env file?", "references": [{"path": ".env"}]},
            {"question": "About the file elsewhere?", "references": [{"path": self.outside}]},
            {"question": "About the notes?", "references": [{"path": "notes.txt", "lines": [1, 1]}]},
        ]})
        self.check("secret: the denied and the outside references refuse their entries, naming each",
                   re.match(r"Added q\d+ \(entry 3\)\.", result or "") and "entry 1, the reference .env could not be read" in result
                   and "entry 2, the reference %s could not be read" % self.outside in result, repr(result))
        found, scan = self.scan(SECRET, OUTSIDE)
        self.check("secret: nothing of either file is staged or under refs/", scan == 1 and not found,
                   "grep exit %s; files %s" % (scan, found))
        if not self.guard:
            self.skip("secret: the owner's secrets guard", "no --guard-plugin given")
            return
        result = self.ask("main", {"ask": [{"question": "About the deploy config?", "references": [{"path": "deploy.cfg"}]}]})
        found, scan = self.scan(GUARDED)
        added = re.match(r"Added (q\d+)\.", result or "")
        held, body = None, None
        if added:
            q = next((x for x in self.state(sid)["questions"] if x["id"] == added.group(1)), {})
            held = next((r for r in q.get("references") or [] if r.get("path") == "deploy.cfg"), None)
            try:
                with open(os.path.join(self.smh, "sheet", sid, "refs", (held or {}).get("sha256", "-")), errors="replace") as f:
                    body = f.read()
            except OSError:
                body = None
        # The guard scrubs a Read rather than refusing it (seen at M3): the stored body holds its replacement.
        self.check("secret: under the owner's guard the capture is stored as the guard left it: the reference and its "
                   "body there, the body holding the guard's replacement, the token nowhere under the sheet's files",
                   scan == 1 and not found and held is not None and body is not None and "[redacted:" in body
                   and GUARDED not in body,
                   "%s; reference %s; body %r; grep exit %s; files %s" % (repr(result), held and held.get("path"), body, scan, found))

    def scan(self, *needles):
        """grep over the sheet's files: (the files holding any needle, grep's exit: 0 found, 1 none, 2 an error)."""
        args = ["grep", "-rlF"] + [x for n in needles for x in ("-e", n)] + [os.path.join(self.smh, "sheet")]
        r = subprocess.run(args, capture_output=True, text=True)
        return r.stdout.split(), r.returncode

    def highest(self, sid):
        """The highest id the conversation's sheet results name on their first line."""
        ids = [int(n) for _, r in self.calls(sid) if r for n in re.findall(r"q(\d+)", r.splitlines()[0])]
        return max(ids or [0])

    def case_fork(self, sid):
        floor = self.highest(sid)
        copy = self.open("forked", args=["--resume", sid, "--fork-session"], env={"SMINOS_QUESTION_SHEET": "1"})
        wait_for("the fork's record", 30, lambda: os.path.exists(os.path.join(self.smh, "sheet", copy, "state.json")))
        m = self.show(copy) or {}
        result = self.ask("forked", {"ask": [{"question": "Asked in the fork?"}]})
        added = re.match(r"Added q(\d+)\.", result or "")
        self.check("fork (--fork-session): the copy's sheet starts empty and its next id is past every id it holds",
                   copy != sid and m.get("open") == [] and added and int(added.group(1)) > floor,
                   "copy %s; open %s; floor q%d; result %r" % (copy, m.get("open"), floor, result))
        said = self.first_contexts(copy)
        self.check("fork (--fork-session): the copy's first context says its sheet starts empty",
                   any(t.startswith("[sheet v1] This conversation is a copy") for t in said), [t[:100] for t in said])
        self.close("forked")
        pid, _ = self.panes["main"]
        self.say("main", "/branch")
        branch = wait_for("the /branch's session", 60, lambda: (lambda s: s if s and s != sid else None)(self.session_of(pid)))
        self.panes["main"] = (pid, branch)
        wait_for("the branch's record", 30, lambda: os.path.exists(os.path.join(self.smh, "sheet", branch, "state.json")))
        wait_for("the branch's bridge", 60, lambda: self.ping(branch))
        m = self.show(branch) or {}
        result = self.ask("main", {"ask": [{"question": "Asked in the branch?"}]})
        added = re.match(r"Added q(\d+)\.", result or "")
        self.check("fork (/branch): the copy's sheet starts empty and its next id is past every id it holds",
                   m.get("open") == [] and added and int(added.group(1)) > floor,
                   "branch %s; open %s; floor q%d; result %r" % (branch, m.get("open"), floor, result))
        said = self.first_contexts(branch)
        self.check("fork (/branch): the copy's first context says its sheet starts empty",
                   any(t.startswith("[sheet v1] This conversation is a copy") for t in said), [t[:100] for t in said])

    # -- import (M5)

    def today_calls(self, sid):
        """The calls of today's question tool the transcript holds: (call id, questions, result text or None)."""
        return [(u, i.get("questions") or [], r) for u, i, r in self.calls(sid, ids=True)
                if isinstance(i, dict) and "questions" in i]

    def imported(self, sid):
        """The record's imported questions: (id, question, call id, index); None while there is no record."""
        try:
            qs = self.state(sid)["questions"]
        except (OSError, ValueError):
            return None
        return [(q["id"], q["question"], q["importedFrom"]["callId"], q["importedFrom"]["index"])
                for q in qs if q.get("importedFrom")]

    def told(self, sid):
        """The contexts that tell the agent of an import: a start's, on its SessionStart or its first route."""
        return [t for _, k, t, _ in self.envelopes(sid) if k in ("SessionStart", "prompt.submit", "tool.call") and MOVED in t]

    def resumed(self, name, sid, env=None, args=()):
        """`sid` resumed under the sheet in a session of its own, once its start's step has made the record."""
        got = self.open(name, args=["--resume", sid, *args], env=dict({"SMINOS_QUESTION_SHEET": "1"}, **(env or {})))
        wait_for("%s's record" % name, 30, lambda: os.path.exists(os.path.join(self.smh, "sheet", got, "state.json")))
        self.idle(got, 60)
        return got

    def case_import(self):
        name = "legacy"
        sid = self.open(name)
        self.say(name, "Use your AskUserQuestion tool twice, one call after the other, each with async true and one "
                       "question: first ask me which colour I prefer, Red or Blue; then ask me which fruit I prefer, "
                       "Apple or Pear. Then reply with only: asked.")
        try:
            wait_for("the two asks' results", 180, lambda: len([c for c in self.today_calls(sid) if c[2]]) >= 2)
        except TimeoutError:
            pass
        self.idle(sid)
        self.close(name)
        calls = self.today_calls(sid)
        asked = [(q.get("question"), u, n) for u, qs, r in calls if r and r.startswith("Your questions are waiting")
                 for n, q in enumerate(qs)]
        self.check("import: with the setting off, today's tool asks twice without waiting; no record",
                   len(asked) >= 2 and not os.path.exists(os.path.join(self.smh, "sheet", sid, "state.json")),
                   [(u, [q.get("question") for q in qs], (r or "")[:60]) for u, qs, r in calls])
        if len(asked) < 2:
            return
        # A read that cannot be whole: the transcript padded past what one read takes (a row of a type the engine
        # does not know), so it is searched, and the asks' search fails: first on PATH, a perl that exits 2 for it (it
        # names its stored forms, more than the floor's four arguments) and runs the real one for the rest, and a grep
        # that exits 2.
        path = glob.glob(os.path.join(self.cfg, "projects", "*", sid + ".jsonl"))[0]
        with open(path, "a") as f:
            f.write(json.dumps({"type": "live-check-padding", "padding": "x" * (READ_LIMIT + 65536)}) + "\n")
        stubs = os.path.join(self.root, "failing-search")
        os.makedirs(stubs, exist_ok=True)
        bodies = {"perl": '#!/bin/sh\n[ "$#" -gt 4 ] && exit 2\nexec %s "$@"\n' % shlex.quote(shutil.which("perl")),
                  "grep": "#!/bin/sh\nexit 2\n"}
        for tool, body in bodies.items():
            with open(os.path.join(stubs, tool), "w") as f:
                f.write(body)
            os.chmod(os.path.join(stubs, tool), 0o755)
        first = self.resumed("import-1", sid, env={"PATH": stubs + ":" + os.environ.get("PATH", "")})
        unread = self.debug_lines("import-1", "asks of today's tool was not definite")
        held = self.imported(first)
        self.check("import: resumed under the sheet when the read cannot be whole, nothing is imported or recorded "
                   "as imported", first == sid and unread and held == [] and not self.state(sid)["import"]["calls"],
                   "session %s; the start's debug %s; imported %s; import %s" % (first, [x[-120:] for x in unread[:1]], held,
                                                                          self.state(sid).get("import")))
        self.close("import-1")
        self.resumed("import-2", sid)
        self.check_band("import", "import-2", sid, len(asked))
        self.say("import-2", "Reply with only: ok.")
        self.idle(sid)
        held = self.imported(sid)
        told = self.told(sid)
        want = [(q, u, n) for q, u, n in asked]
        self.check("import: resumed again with a whole read, each open ask is on the sheet once, as asked, and the "
                   "agent is told",
                   [(q, u, n) for _, q, u, n in held or []] == want and len(told) == 1
                   and all(i in told[0] for i, _, _, _ in held),
                   "imported %s; asked %s; told %r" % (held, want, [t[t.find(MOVED):][:200] for t in told]))
        self.close("import-2")
        for n in (3, 4):
            self.resumed("import-%d" % n, sid)
            self.close("import-%d" % n)
        again = self.imported(sid)
        told = self.told(sid)
        self.check("import: after two more resumes the asks are still there once, and told once",
                   again == held and len((self.state(sid))["questions"]) == len(want) and len(told) == 1,
                   "imported %s; questions %d; told %d" % (again, len(self.state(sid)["questions"]), len(told)))
        copy = self.resumed("import-fork", sid, args=["--fork-session"])
        m = self.show(copy) or {}
        never = self.state(copy)["import"]["never"]
        # Its transcript is written with the copied conversation only at its first prompt (C0's P5).
        self.say("import-fork", "Reply with only: ok.")
        self.idle(copy)
        self.close("import-fork")
        self.resumed("import-fork-2", copy)
        self.close("import-fork-2")
        m2 = self.show(copy) or {}
        self.check("import: a fork of the session starts with an empty sheet, marked never to import, and stays empty "
                   "when resumed", copy != sid and m.get("open") == [] and never is True and m2.get("open") == []
                   and self.imported(copy) == [],
                   "copy %s; open %s then %s; never %s; imported %s" % (copy, m.get("open"), m2.get("open"), never,
                                                                       self.imported(copy)))

    # -- delivery (M4)

    def envelopes(self, sid, sub=False):
        """The envelopes a transcript holds in rows of the routes' kinds and the SessionStart's, as a start's search
        reads them: (row index, kind, the entry's text, its blocks). Kinds: tool.call, prompt.submit and SessionStart
        (a hook's context), plugin (this plugin's prompt)."""
        out = []
        for i, row in enumerate(self.rows(sid, sub)):
            a = row.get("attachment") if row.get("type") == "attachment" else None
            if isinstance(a, dict) and a.get("type") == "hook_additional_context":
                content = a.get("content")
                for text in content if isinstance(content, list) else [content]:
                    if isinstance(text, str):
                        out.append((i, a.get("hookName"), text, blocks(text)))
            elif row.get("type") == "user" and row.get("origin") == {"kind": "plugin", "name": "sminos"}:
                text = text_of((row.get("message") or {}).get("content"))
                out.append((i, "plugin", text, blocks(text)))
        return out

    def contexts(self, sid, kind):
        return [t for _, k, t, _ in self.envelopes(sid) if k == kind]

    def first_contexts(self, sid):
        """A start's context: on its SessionStart, or on the first route when the start had no session yet."""
        return [t for _, k, t, _ in self.envelopes(sid) if k in ("SessionStart", "prompt.submit", "tool.call")]

    def carrying(self, sid, key, sub=False):
        """The envelope rows that deliver `key`: [(kind, text, keys)]."""
        return [(k, t, b[0]) for _, k, t, bs in self.envelopes(sid, sub) for b in bs if key in b[0]]

    def replies(self, sid, since):
        """The model's text in the rows after `since`."""
        return "\n".join(text_of((r.get("message") or {}).get("content")) for r in self.rows(sid)[since:]
                         if r.get("type") == "assistant")

    def put_answers(self, sid, answers):
        """One call of the door: [(q, revision, text, pick or None)] answered; the keys, in order."""
        keys = ["live-%s" % uuid.uuid4().hex[:16] for _ in answers]
        lines = [dict({"v": 1, "key": k, "kind": "answer", "id": q, "revision": rev, "text": text, "by": "cli"},
                      **({"picks": [pick]} if pick else {})) for k, (q, rev, text, pick) in zip(keys, answers)]
        code, out, err = self.put(sid, lines)
        return keys if code == 0 else []

    def dismiss(self, sid, q):
        key = "live-%s" % uuid.uuid4().hex[:16]
        self.put(sid, [{"v": 1, "key": key, "kind": "dismiss", "id": q, "by": "cli"}])
        return key

    def landed(self, sid, keys, seconds=120):
        """Waits until no key is pending; whether they all left."""
        try:
            wait_for("the keys delivered", seconds, lambda: not {o["key"] for o in self.state(sid)["pending"]} & set(keys))
            return True
        except TimeoutError:
            return False

    def running_turn(self, sid, seconds=60):
        wait_for("a main turn", seconds, lambda: (self.ping(sid) or {}).get("result", {}).get("state", {}).get("mainTurn"))

    def debug_lines(self, name, needle):
        return [line for line in self.debug(name).splitlines() if needle in line]

    def delivery(self):
        name = "deliver"
        sid = self.open(name, env={"SMINOS_QUESTION_SHEET": "1"})
        labels = {13: ["Saturn", "Jupiter"], 14: ["Oak", "Pine"]}
        entries = [{"question": "D%d: which colour?" % i, "header": "Colour %d" % i,
                    "options": [{"label": x} for x in labels.get(i, ["Red", "Blue"])]} for i in range(1, 16)]
        first = self.ask(name, {"ask": entries[:8]}, preface=REPEAT)
        second = self.ask(name, {"ask": entries[8:]})
        ok = first.startswith("Added q1, q2, q3, q4, q5, q6, q7, q8.") and second.startswith("Added q9, q10, q11, q12, q13, q14, q15.")
        if not ok:
            self.check("delivery: the session's fifteen questions", False, (first, second))
            return
        if any(self.wants(c) for c in ("rendering",)):
            self.case_rendering(name, sid)
        if self.wants("subset"):
            self.case_subset(name, sid)
        if self.wants("note"):
            self.case_note(name, sid)
        if self.wants("dismiss"):
            self.case_dismiss(name, sid)
        if self.wants("compaction"):
            self.case_compaction(name, sid)
        if self.wants("both") or self.wants("subagent") or self.wants("agent-open"):
            self.case_subagents(name, sid)
        if self.wants("stopped"):
            self.case_stopped(name, sid)
        self.close(name)

    def case_rendering(self, name, sid):
        # The idle route: an answer while no turn runs is this plugin's prompt, which starts a turn.
        keys = self.put_answers(sid, [("q1", 1, "alpha-idle", "Red")])
        try:
            wait_for("the idle prompt's row", 60, lambda: self.carrying(sid, keys[0]))
        except TimeoutError:
            pass
        self.idle(sid)
        rows = self.carrying(sid, keys[0])
        seen = self.debug_lines(name, 'a prompt row ({"kind":"plugin","name":"sminos"}) landed 1 key: %s' % keys[0])
        self.check("rendering: the idle route's prompt, its row seen by the mod's own session.append (door prompt, origin "
                   "this plugin's) and stored as a user row of this plugin's origin",
                   [k for k, _, _ in rows] == ["plugin"] and seen and self.landed(sid, keys, 5),
                   "rows %s; debug %s" % ([k for k, _, _ in rows], seen[:1]))
        # The result route: an answer while a turn runs rides its next tool result.
        since = len(self.rows(sid))
        self.say(name, "Run the Bash command `sleep 6` with the Bash tool, then reply with only: done.")
        self.running_turn(sid)
        keys = self.put_answers(sid, [("q2", 1, "beta-result", "Blue")])
        self.idle(sid)
        rows = self.carrying(sid, keys[0])
        seen = self.debug_lines(name, 'a hook-context row ({"kind":"plugin","event":"tool.call"}) landed 1 key: %s' % keys[0])
        self.check("rendering: the result route's context, door hook-context with origin tool.call, stored as a "
                   "hook_additional_context attachment of hookName tool.call",
                   [k for k, _, _ in rows] == ["tool.call"] and seen and self.landed(sid, keys, 5),
                   "rows %s; debug %s; replies %r" % ([k for k, _, _ in rows], seen[:1], self.replies(sid, since)[-200:]))
        # The prompt route: a dismissal starts no turn and rides the next prompt that enters.
        key = self.dismiss(sid, "q3")
        time.sleep(4)
        self.say(name, "Reply with only: ok.")
        self.idle(sid)
        rows = self.carrying(sid, key)
        seen = self.debug_lines(name, 'a hook-context row ({"kind":"plugin","event":"prompt.submit"}) landed 1 key: %s' % key)
        self.check("rendering: the prompt route's context, door hook-context with origin prompt.submit, stored as a "
                   "hook_additional_context attachment of hookName prompt.submit",
                   [k for k, _, _ in rows] == ["prompt.submit"] and seen and self.landed(sid, [key], 5),
                   "rows %s; debug %s" % ([k for k, _, _ in rows], seen[:1]))

    def case_subset(self, name, sid):
        opened = len((self.show(sid) or {}).get("open", []))
        since = len(self.rows(sid))
        self.say(name, "Run the Bash command `sleep 8` with the Bash tool, then reply with only: done.")
        self.running_turn(sid)
        keys = self.put_answers(sid, [("q4", 1, "kiwi-4", None), ("q5", 1, "plum-5", None), ("q6", 1, "fig-6", None)])
        self.idle(sid)
        rows = self.carrying(sid, keys[0])
        said = self.replies(sid, since)
        left = len((self.show(sid) or {}).get("open", []))
        self.check("subset: three answers sent as one while a turn runs reach it in one envelope with three keys; the agent "
                   "quotes them; the rest stay open",
                   len(rows) == 1 and set(rows[0][2]) == set(keys) and all(w in said for w in ("kiwi-4", "plum-5", "fig-6"))
                   and left == opened - 3, "rows %s; open %d -> %d; replies %r" % ([(k, len(ks)) for k, _, ks in rows], opened, left, said[-300:]))
        since = len(self.rows(sid))
        keys = self.put_answers(sid, [("q7", 1, "lime-7", None), ("q8", 1, "pear-8", None), ("q9", 1, "date-9", None)])
        try:
            wait_for("a turn the answers start", 60, lambda: self.carrying(sid, keys[0]))
        except TimeoutError:
            pass
        self.idle(sid)
        rows = self.carrying(sid, keys[0])
        said = self.replies(sid, since)
        self.check("subset: three more while idle start a turn by themselves, one envelope, quoted",
                   [k for k, _, _ in rows] == ["plugin"] and set(rows[0][2]) == set(keys) and all(w in said for w in ("lime-7", "pear-8", "date-9")),
                   "rows %s; replies %r" % ([(k, len(ks)) for k, _, ks in rows], said[-300:]))

    def case_note(self, name, sid):
        since = len(self.rows(sid))
        keys = self.put_answers(sid, [("q10", 1, "only on tuesdays", "Blue")])
        try:
            wait_for("the answer's turn", 60, lambda: self.carrying(sid, keys[0]))
        except TimeoutError:
            pass
        self.idle(sid)
        said = self.replies(sid, since)
        self.check("note: an answer with a pick and a text; the agent repeats both",
                   "Blue" in said and "only on tuesdays" in said.lower(), repr(said[-300:]))

    def case_dismiss(self, name, sid):
        since = len(self.rows(sid))
        key = self.dismiss(sid, "q11")
        time.sleep(20)
        turned = [r for r in self.rows(sid)[since:] if r.get("type") in ("assistant",) or r.get("origin") == {"kind": "plugin", "name": "sminos"}]
        self.check("dismiss: a dismissal in an idle session starts no turn within 20 s", not turned and self.carrying(sid, key) == [],
                   "%d rows of a turn" % len(turned))
        keys = self.put_answers(sid, [("q12", 1, "last-12", None)])
        try:
            wait_for("the answer's turn", 60, lambda: self.carrying(sid, keys[0]))
        except TimeoutError:
            pass
        self.idle(sid)
        rows = self.carrying(sid, key)
        said = self.replies(sid, since)
        self.check("dismiss: after another answer the agent is told of the dismissal with it, and names it",
                   rows and key in rows[0][2] and keys[0] in rows[0][2] and "q11" in said, "rows %s; replies %r" % ([(k, ks) for k, _, ks in rows], said[-300:]))

    def case_compaction(self, name, sid):
        self.say(name, "/compact")
        try:
            wait_for("the compaction", 240, lambda: any(r.get("subtype") == "compact_boundary" for r in self.rows(sid)))
        except TimeoutError:
            pass
        self.idle(sid)
        since = len(self.rows(sid))
        self.say(name, "Without calling any tool, list the ids of the questions still open on your question sheet, each with its options.")
        self.idle(sid)
        said = self.replies(sid, since)
        told = [t for t in self.contexts(sid, "SessionStart") if t.startswith("[sheet v1] Your question sheet, after a compaction.")]
        self.check("compaction: after a compaction the agent names its open questions and their options without a tool",
                   told and all(w in said for w in ("q13", "q14", "Saturn", "Oak")), "context %r; replies %r" % ((told or [""])[-1][:160], said[-400:]))

    def sub_files(self, sid):
        return glob.glob(os.path.join(self.cfg, "projects", "*", sid, "subagents", "*.jsonl"))

    def subagent_q(self, sid, mark):
        return next((q for q in (self.show(sid) or {}).get("open", []) if mark in q.get("question", "")), None)

    def case_subagents(self, name, sid):
        # A subagent asks and keeps running (a sleep) while one put answers it and the main agent's q15.
        inner = call_prompt({"ask": [{"question": "Sub-A: which planet?", "options": [{"label": "Mars"}, {"label": "Venus"}]}]})
        inner = inner.replace("Then reply with only the first line of the tool's result.",
                              "Then run the Bash command `sleep 25` with the Bash tool. Then reply with any message you received while working, word for word.")
        subs = set(self.sub_files(sid))
        self.say(name, "Use the Agent tool once (subagent_type general-purpose, description sheet-asker) with this as its whole prompt: %s "
                       "Then reply with only what the agent reported." % json.dumps(inner))
        q = None
        try:
            q = wait_for("the subagent's question", 180, lambda: self.subagent_q(sid, "Sub-A"))
        except TimeoutError:
            pass
        asker = (q or {}).get("asker")
        if self.wants("subagent"):
            self.check("subagent: a subagent asks; show names it as the asker", isinstance(asker, dict) and asker.get("agentId"), q)
        keys = self.put_answers(sid, [(q["id"], 1, "sub-only-a", "Mars"), ("q15", 1, "main-only-b", "Red")]) if q else []
        self.idle(sid, 300)
        sub_text = "".join(open(p, errors="replace").read() for p in self.sub_files(sid) if p not in subs)
        main_rows = self.envelopes(sid)
        main_keys = {k for _, _, _, bs in main_rows for b in bs for k in b[0]}
        # Asserted whatever the setup gave: a question that never appeared, or a put that failed, is a failure here.
        took = len(keys) == 2
        if self.wants("subagent"):
            self.check("subagent: answered while it runs, its own transcript holds the envelope under its opening line, the main one does not",
                       took and keys[0] in sub_text and SUBAGENT_OPENING in sub_text and keys[0] not in main_keys,
                       "question %s; keys %s; sub has key %s, opening %s; main has it %s" % (
                           q and q["id"], keys, took and keys[0] in sub_text, SUBAGENT_OPENING in sub_text, took and keys[0] in main_keys))
        if self.wants("both"):
            self.check("both: one put answers the main agent's question and a running subagent's; each conversation holds its own key only",
                       took and keys[0] in sub_text and keys[1] not in sub_text and keys[1] in main_keys and keys[0] not in main_keys,
                       "question %s; keys %s; sub %s; main %s" % (q and q["id"], keys, [k in sub_text for k in keys], [k in main_keys for k in keys]))
        # A subagent asks and ends: the main conversation's next route names its open question; the answer given after
        # it ended goes to the main conversation, naming it, and does not resume it.
        inner = call_prompt({"ask": [{"question": "Sub-B: which metal?", "options": [{"label": "Gold"}, {"label": "Iron"}]}]})
        # The engine runs the main loop's Agent in the background (2.1.331 launches it async even when asked
        # run_in_background false): the main turn ends first, and the agent's completion enters as a prompt a few
        # milliseconds after its SubagentStop, the next route to open. No answer is put until the notice is out.
        self.say(name, "Use the Agent tool once (subagent_type general-purpose, description metal-asker) with this as its "
                       "whole prompt: %s Then reply with only: asked." % json.dumps(inner))
        q = None
        try:
            q = wait_for("the second subagent's question", 180, lambda: self.subagent_q(sid, "Sub-B"))
        except TimeoutError:
            pass
        ended = lambda: [(k, t) for _, k, t, _ in self.envelopes(sid) if "ended with questions still open" in t]
        try:
            wait_for("the ended notice", 180, ended)
        except TimeoutError:
            pass
        self.idle(sid, 240)
        noticed = ended()
        if self.wants("agent-open"):
            self.check("agent-open: a subagent that ends with a question open is named on the main conversation's next "
                       "route (its completion's prompt, or a tool result), once",
                       q and len(noticed) == 1 and noticed[0][0] in ("prompt.submit", "tool.call", "plugin") and q["id"] in noticed[0][1],
                       "question %s; notices %r" % (q and q["id"], [(k, t[:160]) for k, t in noticed]))
        if q is None:
            return
        sub_files = self.sub_files(sid)
        sizes = {p: os.path.getsize(p) for p in sub_files}
        keys = self.put_answers(sid, [(q["id"], 1, "late-gold", "Gold")])
        try:
            wait_for("the late answer's turn", 60, lambda: self.carrying(sid, keys[0]))
        except TimeoutError:
            pass
        self.idle(sid)
        rows = self.carrying(sid, keys[0])
        grown = [p for p in sub_files if os.path.getsize(p) != sizes[p]]
        if self.wants("subagent"):
            self.check("subagent: answered after it ended, the main conversation's envelope names it; it was not resumed",
                       rows and "which has ended" in rows[0][1] and "from the subagent" in rows[0][1] and not grown,
                       "rows %r; transcripts grown %d" % ([t[:200] for _, t, _ in rows], len(grown)))

    def case_stopped(self, name, sid):
        self.close(name)
        pid = self.panes[name][0]
        wait_for("the session's process gone", 30, lambda: not LB._alive(pid))
        m = self.show(sid) or {}
        opened = [q["id"] for q in m.get("open", [])]
        a = self.cli("sheet", "answer", "--session", sid, "q13", "--pick", "Saturn", "--text", "rings")
        b = self.cli("sheet", "answer", "--session", sid, "q14", "--pick", "Oak")
        ka = ((json.loads(a.stdout) if a.returncode == 0 else {}).get("results") or [{}])[0]
        kb = ((json.loads(b.stdout) if b.returncode == 0 else {}).get("results") or [{}])[0]
        r = self.cli("sheet", "retract", "--session", sid, kb.get("key", "-"))
        self.check("stopped: show lists a stopped session's questions; answer prints queued; retract takes one back",
                   "q13" in opened and "q14" in opened and ka.get("state") == "queued" and kb.get("state") == "queued" and r.returncode == 0,
                   "open %s; %s %s; retract exit %s %s" % (opened, ka, kb, r.returncode, r.stdout.strip()[:120]))
        resumed = self.open("resumed", args=["--resume", sid], env={"SMINOS_QUESTION_SHEET": "1"})
        since = len(self.rows(sid))
        time.sleep(6)
        started = [x for x in self.rows(sid)[since:] if x.get("type") == "assistant"]
        self.say("resumed", "Reply with only: ok.")
        self.idle(resumed)
        rows = self.carrying(sid, ka.get("key", "-"))
        dropped = self.carrying(sid, kb.get("key", "-"))
        self.check("stopped: resumed, the first prompt carries the answer with its two times, and not the one taken back; "
                   "no turn started by itself",
                   [k for k, _, _ in rows] == ["prompt.submit"] and "while this session was stopped" in rows[0][1]
                   and "rings" in rows[0][1] and not dropped and not started,
                   "rows %r; retracted's rows %d; turns before the prompt %d" % ([t[:240] for _, t, _ in rows], len(dropped), len(started)))
        self.close("resumed")

    def case_max_send(self):
        name = "max"
        sid = self.open(name, env={"SMINOS_QUESTION_SHEET": "1"})
        ids = []
        for n, (lo, hi) in enumerate(((1, 21), (21, 41), (41, 51))):
            result = self.ask(name, {"ask": [{"question": "M%d?" % i} for i in range(lo, hi)]},
                              preface=("When answers from the human's question sheet reach you, reply with only: received. "
                                       "Never read a file an answer points to. ") if n == 0 else "")
            ids += re.findall(r"q\d+", (result or "").split("\n")[0])
        if len(ids) != 50:
            self.check("max-send: fifty questions asked", False, ids)
            return
        text = lambda i: ("answer %02d " % i) + ("abcdefghij" * 2000)[:20000 - 10]
        keys = self.put_answers(sid, [(q, 1, text(i), None) for i, q in enumerate(ids)])
        done = self.landed(sid, keys, 600)
        self.idle(sid, 300)
        rows = [(k, t, b) for _, k, t, bs in self.envelopes(sid) for b in bs if set(b[0]) & set(keys)]
        carried = [k for _, _, b in rows for k in b[0]]
        files_ok, full = True, 0
        for _, t, _ in rows:
            for m in re.finditer(r"their text, 20,000 characters, is in (\S+) and begins: ", t):
                files_ok = files_ok and os.path.exists(m.group(1))
            full += sum(1 for i in range(50) if text(i) in t)
        heads = sum(len(re.findall(r"their text, 20,000 characters, is in ", t)) for _, t, _ in rows)
        mores = [b[3] for _, _, b in rows]
        self.check("max-send: fifty answers of 20,000 characters arrive whole: every envelope uncut with at most 200 keys, "
                   "each text in full or by its head and a file that exists, every key landed, each but the last saying more follows",
                   done and sorted(carried) == sorted(keys) and all(len(b[0]) <= 200 for _, _, b in rows) and files_ok
                   and full + heads == 50 and mores == [True] * (len(rows) - 1) + [False]
                   and all("More follows." in envelope_head(t) for _, t, b in rows if b[3]),
                   "landed %s; envelopes %d (%s); in full %d, by file %d; files exist %s" % (
                       done, len(rows), [(k, len(b[0]), b[3]) for k, _, b in rows], full, heads, files_ok))
        self.close(name)

    def case_no_surface(self):
        ssh = {"SSH_CONNECTION": "192.0.2.1 50000 192.0.2.2 22"}
        for label, env, up in (("setting off", {}, True), ("no registration", {"SMINOS_QUESTION_SHEET": "1"}, False),
                               ("SSH, a local surface only", dict(ssh, SMINOS_QUESTION_SHEET="1"), True)):
            if up != bool(self.surfaces_alive()):
                self.surface_up() if up else self.surface_down()
            name = "today-%d" % len(self.results)
            sid = self.open(name, env=env)
            self.say(name, "Ask me with your question tool, with async set to false so that you wait for my answer, which "
                           "colour I prefer, Red or Blue.")
            # Today's tool, blocking: the engine's own dialog, which the mod raises as the built-in with today's
            # `questions` (the debug log names the raise) and the terminal draws with both options.
            raised = "$.tool.call (sminos): AskUserQuestion (questions)"
            try:
                wait_for("the engine's dialog", 180, lambda: raised in self.debug(name)
                         and "Red" in self.pane_of(name) and "Blue" in self.pane_of(name))
                up = True
            except TimeoutError:
                up = False
            uses = [i for i, _ in self.calls(sid)]
            chose = [line.split("sheet: ", 1)[1] for line in self.debug(name).splitlines() if "sheet: today" in line]
            self.check("no-surface (%s): today's tool, its blocking dialog up, no record" % label,
                       up and chose and not any("ask" in (i or {}) for i in uses)
                       and not os.path.exists(os.path.join(self.smh, "sheet", sid, "state.json")),
                       "dialog %s; choice %s; pane: %s" % ("up" if up else "not seen", chose[:1],
                                                           " | ".join(x.strip() for x in self.pane_of(name).splitlines() if x.strip())[-300:]))
            self.keys_to(name, "Escape")
            self.close(name)
        if not self.surfaces_alive():
            self.surface_up()

    def case_nested(self):
        other = str(uuid.uuid4())
        debug = os.path.join(self.root, "debug-nested.log")
        inner = ("set -e; . %s; export MAWS_QUESTION_SHEET=%s SMINOS_QUESTION_SHEET=1; cd %s; exec claude -p "
                 "--plugin-dir %s --model haiku --output-format stream-json --verbose --debug-file %s 'Reply with ok.'") % (
            shlex.quote(self.envfile), other, shlex.quote(self.work), shlex.quote(self.plugin), shlex.quote(debug))
        r = subprocess.run(["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c", inner], capture_output=True,
                           text=True, timeout=180)
        init = next((json.loads(x) for x in r.stdout.splitlines() if '"subtype":"init"' in x), {})
        sid = init.get("session_id", "")
        with open(debug, errors="replace") as f:
            said = [line for line in f if "MAWS_QUESTION_SHEET" in line]
        self.check("nested: a claude -p naming another session takes no sheet, and its debug log says the variable did not match",
                   r.returncode == 0 and sid and any("names another session (%s, not %s)" % (other, sid) in s for s in said)
                   and not os.path.exists(os.path.join(self.smh, "sheet", sid, "state.json")),
                   "exit %s; session %s; debug %s" % (r.returncode, sid, [s.strip()[-160:] for s in said][:2]))


def main():
    args = sys.argv[1:]
    cases = [args[i + 1] for i, a in enumerate(args) if a == "--case" and i + 1 < len(args)]
    unknown = [c for c in cases if c not in CASES]
    if unknown:
        sys.exit("live-sheet-check: no case %s (cases: %s)" % (", ".join(unknown), ", ".join(CASES)))
    guard = next((args[i + 1] for i, a in enumerate(args) if a == "--guard-plugin" and i + 1 < len(args)), None)
    if guard and not os.path.isfile(os.path.join(guard, ".claude-plugin", "plugin.json")):
        sys.exit("live-sheet-check: --guard-plugin takes a plugin's directory (one holding .claude-plugin/plugin.json)")
    live = Sheet("--keep" in args, cases, guard)
    print("live sheet check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    for name, _, detail in failed:
        print("FAIL %s: %s" % (name.split(":")[0], detail))
    for name, why in live.skipped:
        print("SKIPPED %s: %s" % (name, why))
    print("live-sheet-check: %d passed%s%s" % (len(live.results) - len(failed), ", %d failed" % len(failed) if failed else "",
                                             ", %d skipped" % len(live.skipped) if live.skipped else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
