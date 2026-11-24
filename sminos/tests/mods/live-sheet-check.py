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

    sminos/tests/mods/live-sheet-check.py [--case <name>]... [--keep]

Cases (M3's): many, revise, withdraw, two-surfaces, secret, fork (one
terminal session asks, revises, withdraws; a subagent's acts; the door;
the refused references; its copies by --fork-session and /branch), then
no-surface and nested (sessions of their own). `many` comes first whatever
is asked: the cases after it act on its questions. It ends
`live-sheet-check: N passed` and exits 0; a failing check prints
`FAIL <case>: <what was observed>`.
"""
import os.path, runpy  # noqa: E401 — the caller's repository kept out first (#623)
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../git_isolation.py"))

import glob
import importlib.util
import json
import re
import shlex
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
CASES = ("many", "revise", "withdraw", "two-surfaces", "secret", "fork", "no-surface", "nested")


def call_prompt(payload):
    return ("Call the tool %s exactly once, with exactly this JSON as its input: %s . "
            "Then reply with only the first line of the tool's result." % (SHEET_TOOL, json.dumps(payload)))


def gist(payload):
    """A call's input by its questions and withdrawals: what a model copying the input keeps, whatever it adds."""
    payload = payload if isinstance(payload, dict) else {}
    return ([e.get("question") for e in payload.get("ask") or [] if isinstance(e, dict)], payload.get("withdraw") or [])


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


class Sheet(LB.Live):
    def __init__(self, keep, cases):
        super().__init__(keep)
        self.tmux = ["tmux", "-L", "shl-%d" % os.getpid(), "-f", "/dev/null"]
        self.cases = cases
        self.surface = None
        self.panes = {}          # tmux session name -> the engine session id it holds now
        self.outside = os.path.join(self.root, "outside", "elsewhere.txt")

    # -- isolation

    def setup(self):
        super().setup()
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": [SHEET_TOOL, "Agent", "Task"], "deny": ["Read(**/.env)"]}}, f)
        with open(os.path.join(self.work, "notes.txt"), "w") as f:
            f.write(NOTES)
        with open(os.path.join(self.work, ".env"), "w") as f:
            f.write("TOKEN=%s\n" % SECRET)
        os.makedirs(os.path.dirname(self.outside))
        with open(self.outside, "w") as f:
            f.write(OUTSIDE + "\n")
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
        dirs = "--plugin-dir %s" % shlex.quote(self.plugin)
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

    def ask(self, name, payload, seconds=180):
        """The agent calls the tool with `payload`: its result, once the turn is over."""
        sid = self.panes[name][1]
        # Known by its input, not its place: a fork's transcript is written with the conversation it copied only
        # once its first prompt is (C0's P5), after the count a place would rest on.
        before = {u for u, _, _ in self.calls(sid, ids=True)}
        self.say(name, call_prompt(payload))
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

    def case_revise(self, sid):
        result = self.ask("main", {"ask": [{"id": "q2", "question": "Question 2, revised: which colour?",
                                            "options": [{"label": "Red"}, {"label": "Blue"}]}]})
        self.check("revise: the agent revises q2", re.match(r"Revised q2\b", result or ""), repr(result))
        r = self.cli("sheet", "answer", "--session", sid, "q2", "--pick", "1")
        self.check("revise: an answer to q2 at its first revision is refused, naming q2@2",
                   r.returncode == 2 and "q2@2" in r.stderr, "exit %s: %s" % (r.returncode, r.stderr.strip()))
        key = "live-stale-%s" % uuid.uuid4().hex[:12]
        code, out, err = self.put(sid, [{"v": 1, "key": key, "kind": "answer", "id": "q2", "revision": 1,
                                         "picks": ["Apple"], "by": "cli"}])
        verdict = ((out or {}).get("results") or [{}])[0]
        self.check("revise: a door line at revision 1 is stale, current 2 (the bridge's sheet op answered it)",
                   code == 0 and verdict.get("state") == "stale" and verdict.get("current") == 2, (code, out, err))
        r = self.cli("sheet", "answer", "--session", sid, "q2@2", "--pick", "1")
        out = json.loads(r.stdout) if r.returncode == 0 else {}
        pending = [o for o in (self.show(sid) or {}).get("pending", []) if o.get("id") == "q2"]
        self.check("revise: q2@2 --pick 1 is applied to the new first option",
                   r.returncode == 0 and pending and pending[0].get("picks") == ["Red"],
                   "%s; pending %s" % (out or r.stderr.strip(), pending))

    def case_withdraw(self, sid):
        result = self.ask("main", {"withdraw": ["q3"]})
        opened = [q["id"] for q in (self.show(sid) or {}).get("open", [])]
        self.check("withdraw: the agent withdraws q3; show no longer lists it",
                   result.startswith("Withdrew q3.") and "q3" not in opened, "%r; open %s" % (result, opened))
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
        _, a, _ = self.put(sid, [dict(line, key=one)])
        _, b, _ = self.put(sid, [dict(line, key=two)])
        sa, sb = (((x or {}).get("results") or [{}])[0].get("state") for x in (a, b))
        self.check("two-surfaces: two answers to one question: the first taken, the second closed",
                   sa in ("accepted", "applied", "delivered") and sb == "closed", (a, b))
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
        leaked = subprocess.run(["grep", "-rlF", "-e", SECRET, "-e", OUTSIDE, os.path.join(self.smh, "sheet")],
                                capture_output=True, text=True).stdout.split()
        self.check("secret: nothing of either file is staged or under refs/", not leaked, leaked)
        guard = [d for d in glob.glob(os.path.join(self.cfg, "plugins", "*")) if "devcloud" in d]
        self.check("secret: the owner's secrets guard is not in this scratch HOME (its denial is not observed here)",
                   True, "devcloud plugin dirs: %s" % (guard or "none"))

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

    def case_no_surface(self):
        ssh = {"SSH_CONNECTION": "192.0.2.1 50000 192.0.2.2 22"}
        for label, env, up in (("setting off", {}, True), ("no registration", {"SMINOS_QUESTION_SHEET": "1"}, False),
                               ("SSH, a local surface only", dict(ssh, SMINOS_QUESTION_SHEET="1"), True)):
            if up != bool(self.surfaces_alive()):
                self.surface_up() if up else self.surface_down()
            name = "today-%d" % len(self.results)
            sid = self.open(name, env=env)
            before = len(self.calls(sid))
            self.say(name, "Ask me with your question tool which colour I prefer, Red or Blue, then end your turn.")
            # Today's tool: an async call is stored with its input; a blocking one opens the engine's dialog, the
            # mod's raise of the built-in naming today's `questions` in the debug log, and is stored once answered.
            raised = "$.tool.call (sminos): AskUserQuestion (questions)"
            try:
                got = wait_for("the question's call", 180, lambda: [i for i, _ in self.calls(sid)[before:]]
                               or ([{"questions": "the dialog"}] if raised in self.debug(name) else None))
            except TimeoutError:
                got = []
            chose = [line.split("sheet: ", 1)[1] for line in self.debug(name).splitlines() if "sheet: today" in line]
            self.check("no-surface (%s): today's tool (questions in its input, or its dialog), no record" % label,
                       got and "questions" in got[0] and "ask" not in got[0] and chose
                       and not os.path.exists(os.path.join(self.smh, "sheet", sid, "state.json")),
                       "%s; choice %s" % ("the dialog raised" if got and got[0] == {"questions": "the dialog"}
                                          else "input keys %s" % (sorted(got[0]) if got else None), chose[:1]))
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
    live = Sheet("--keep" in args, cases)
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
    print("live-sheet-check: %d passed%s" % (len(live.results) - len(failed), ", %d failed" % len(failed) if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
