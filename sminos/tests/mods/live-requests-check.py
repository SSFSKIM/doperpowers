#!/usr/bin/env python3
"""Live check of requests from outside and their settlement (DC2 M3).

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session and a `--bg` job:
- the engine raises a `tool_decision` record through `telemetry.log` for
  each decision, naming its call and who decided (the bridge settles on it);
  a witness mod, `live-decision-probe/`, writes what it receives;
- a permission prompt is raised and settled once, naming the side whose
  answer the engine used, in DC2.G3's four cases: answered from the CLI
  first (settled while the call still runs), in the terminal first (the
  request settles within 2 s of the key),
  both at once (the winner agrees with the engine's own mark in the
  transcript), and the CLI answering after the terminal did (refused as
  already settled); a deny from the CLI carries its message to the model;
- an interrupt with a dialog open withdraws the request;
- a background subagent's request carries a 3-second deadline, its dialog is
  drawn only after it, and past it only the terminal answers;
- the ask mod's question answered with `sminos answer` reaches the model,
  blocking (through the engine's dialog) and async (by the ask mod's own
  delivery);
- a `--bg` job's permission prompt is answered from the CLI;
- every block-row names a transcript row of its block's kind, and whether a
  step's nth response row is its block n is counted.

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand at a milestone with the model gateway's keys in the environment.
Isolation is live-control-check.py's (whose class it extends), with no
permission allowed in the config's settings, so every Bash call asks.

    sminos/tests/mods/live-requests-check.py [--keep]
"""

import glob
import importlib.util
import json
import os
import shlex
import shutil
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


LC = _load("live_control_check", "live-control-check.py")
LB = LC.LB
NAME = LB.NAME
wait_for = LB.wait_for
is_main = LC.is_main
DIALOG = "Do you want to proceed"
KIND = {"text": "text", "thinking": "thinking", "redacted_thinking": "thinking", "tool_use": "tool"}


class Requests(LC.Control):
    def setup(self):
        LB.Live.setup(self)  # settings.json stays {}: every Bash call asks
        self.decisions = os.path.join(self.root, "decisions.json")
        # A copy: the engine writes its type stubs into a plugin it loads.
        self.probe = os.path.join(self.root, "probe")
        shutil.copytree(os.path.join(HERE, "live-decision-probe"), self.probe)
        with open(self.envfile, "a") as f:
            f.write("export CLAUDE_CODE_DAEMON_COLD_START=transient\n")
            f.write("export LIVE_DECISIONS=%s\n" % shlex.quote(self.decisions))

    def start_session(self):
        inner = "set -e; . %s; cd %s; exec claude --plugin-dir %s --plugin-dir %s --model haiku --permission-mode default -n %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), shlex.quote(self.plugin), shlex.quote(self.probe), NAME)
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "brl", "-x", "200", "-y", "50", cmd], check=True)

    def records(self):
        try:
            with open(self.decisions) as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    # -- helpers

    def raised(self, stream, since, pred, what, seconds=90):
        return wait_for("the request for " + what, seconds, lambda: stream.seen_at(
            lambda e: e.get("type") == "raised" and pred(e), since))[0]

    def settled(self, stream, rid, seconds=60):
        return wait_for("request %s's settlement" % rid[:16], seconds, lambda: stream.seen_at(
            lambda e: e.get("type") == "settled" and e.get("request") == rid))[0]

    def all_settled(self, stream, rid):
        return stream.seen(lambda e: e.get("type") == "settled" and e.get("request") == rid)

    def bash_marker(self, m):
        return lambda e: e.get("tool") == "Bash" and m in json.dumps(e.get("input"))

    def call_results(self, stream, rid):
        return stream.seen(lambda e: e.get("type") == "tool" and e.get("phase") == "result" and e.get("toolUseId") == rid)

    def marked(self, session, rid):
        """The engine's own record that it used a PermissionRequest hook's answer."""
        rows = self.transcript_rows(session)
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", session, "subagents", "*.jsonl")):
            with open(p) as f:
                rows += [json.loads(line) for line in f if line.strip()]
        return [r for r in rows if (r.get("attachment") or {}).get("type") == "hook_permission_decision"
                and r["attachment"].get("toolUseID") == rid]

    def dialog(self):
        return DIALOG in self.pane()

    def ask_bash(self, stream, m, sleep=0):
        t = time.time()
        code = "import time; time.sleep(%d); print(\"%s\")" % (sleep, m) if sleep else "print(\"%s\")" % m
        self.prompt("Run exactly this Bash command, then reply in one short sentence: python3 -c '%s'" % code)
        at, raised = self.raised(stream, t, self.bash_marker(m), m)
        return t, at, raised

    def outcome(self, s):
        return "%s/%s/%s" % (s.get("winner"), s.get("outcome"), s.get("by"))

    # -- the checks

    def cli_first(self, term):
        m = self.marker + "cli"
        # A call that runs on: the settlement comes from the engine's record of
        # the decision, at once, not from the call's end.
        t, at, raised = self.ask_bash(term, m, sleep=12)
        rid = raised["request"]
        t0 = time.time()
        r = self.cli("decide", NAME, rid, "allow")
        st, s = self.settled(term, rid)
        running = not self.call_results(term, rid)
        self.turn_end(term, t)
        ran = any(m in str(e.get("text")) for e in self.call_results(term, rid))
        self.check("CLI first: raised with its tool, input and tool-use id; the CLI's allow settles it as the CLI's, while the call still runs",
                   r.returncode == 0 and "settled from here: allow" in r.stdout and rid.startswith("toolu_")
                   and self.outcome(s) == "other/allow/cli" and ran and len(self.all_settled(term, rid)) == 1
                   and running and st - t0 <= 2.5,
                   "%s; settled %s %.2f s after the decide began, the call still running: %s; ran %s"
                   % ((r.stdout + r.stderr).strip(), self.outcome(s), st - t0, running, ran))
        self.check("CLI first: the engine marked the hook's answer as the one it used", self.marked(self.session, rid),
                   "%d mark rows" % len(self.marked(self.session, rid)))
        self.idle(self.endpoint())

    def cli_deny(self, term):
        m = self.marker + "deny"
        t, at, raised = self.ask_bash(term, m)
        rid = raised["request"]
        r = self.cli("decide", NAME, rid, "deny", "--message", "Not now: say the word WALNUT instead.")
        _, s = self.settled(term, rid)
        # The model may try the same call again: each retry is its own request
        # (a call never takes an earlier identical one's id), denied the same way.
        retries = []
        deadline = time.time() + 150
        while not term.seen(lambda e: is_main(e, "turn", "complete"), t):
            if time.time() > deadline:
                raise TimeoutError("the deny's turn did not end")
            for e in term.seen(lambda e: e.get("type") == "raised" and self.bash_marker(m)(e), t):
                if e["request"] not in retries + [rid]:
                    retries.append(e["request"])
                    self.cli("decide", NAME, e["request"], "deny", "--message", "Still no. Reply with the word WALNUT and stop.")
            time.sleep(0.3)
        res = self.call_results(term, rid)
        self.check("a CLI deny carries its message to the model",
                   r.returncode == 0 and self.outcome(s) == "other/deny/cli" and res and res[0].get("isError")
                   and "WALNUT" in str(res[0].get("text")) and "WALNUT" in LC.main_text(term, t),
                   "%s; settled %s; result %r%s" % (r.stdout.strip(), self.outcome(s), str(res[0].get("text"))[:80] if res else None,
                                                    "; the model retried %d time(s), each raised under its own id %s" % (len(retries), retries) if retries else ""))
        self.idle(self.endpoint())

    def terminal_first(self, term):
        m = self.marker + "term"
        # A call that runs on: its settlement must come from the engine's record of the key, not from its result.
        t, at, raised = self.ask_bash(term, m, sleep=8)
        rid = raised["request"]
        wait_for("the dialog", 20, self.dialog)
        time.sleep(1)
        t0 = time.time()
        self.keys("Enter")
        st, s = self.settled(term, rid)
        res = self.call_results(term, rid)
        took = st - t0
        self.check("terminal first: the request settles as the terminal's within 2 s of the key",
                   self.outcome(s) == "terminal/allow/terminal" and took <= 2.0 and not res,
                   "%s after %.2f s, the call still running: %s" % (self.outcome(s), took, not res))
        late = self.cli("decide", NAME, rid, "deny")
        self.check("the CLI answering after the terminal is refused as already settled",
                   late.returncode == 1 and "already settled" in late.stderr, late.stderr.strip())
        self.turn_end(term, t)
        self.check("terminal first: no mark of a hook's answer, and the call ran",
                   not self.marked(self.session, rid) and any(m in str(e.get("text")) for e in self.call_results(term, rid)),
                   "%d mark rows" % len(self.marked(self.session, rid)))
        self.idle(self.endpoint())

    def both_at_once(self, term, n, key_lead):
        """The key and the CLI's decision about at once: `key_lead` seconds
        between the CLI's start and the key (negative: the key first). The
        CLI takes a few tenths of a second to reach the child."""
        m = self.marker + "both%d" % n
        t, at, raised = self.ask_bash(term, m)
        rid = raised["request"]
        wait_for("the dialog", 20, self.dialog)
        time.sleep(1)
        out = {}

        def decide():
            out["r"] = self.cli("decide", NAME, rid, "allow")
        th = threading.Thread(target=decide)
        if key_lead < 0:
            self.keys("Enter")
            time.sleep(-key_lead)
            th.start()
        else:
            th.start()
            time.sleep(key_lead)
            self.keys("Enter")
        th.join(60)
        _, s = self.settled(term, rid)
        self.turn_end(term, t)
        time.sleep(2)
        r = out.get("r")
        marks = self.marked(self.session, rid)
        ran = [e for e in self.call_results(term, rid) if m in str(e.get("text"))]
        cli_won = s.get("by") == "cli"
        self.check("both at once (%d): one settlement, its winner the side the engine's mark names, the CLI told the same" % n,
                   r is not None and len(self.all_settled(term, rid)) == 1 and bool(marks) == cli_won
                   and (r.returncode == 0) == cli_won and len(ran) == 1,
                   "settled %s; marks %d; CLI rc %s: %s" % (self.outcome(s), len(marks), r and r.returncode,
                                                            r and (r.stdout + r.stderr).strip()))
        self.idle(self.endpoint())

    def interrupt_open(self, term):
        m = self.marker + "int"
        t, at, raised = self.ask_bash(term, m)
        rid = raised["request"]
        wait_for("the dialog", 20, self.dialog)
        t0 = time.time()
        r = self.cli("interrupt", NAME)
        took = time.time() - t0
        _, s = self.settled(term, rid)
        aborted = wait_for("the aborted turn", 15, lambda: term.seen(
            lambda e: is_main(e, "turn", "complete") and e.get("reason") == "aborted", t))
        gaps = term.seen(lambda e: e.get("type") == "gap", t)
        self.check("an interrupt with a dialog open withdraws the request, the CLI answered at once",
                   r.returncode == 0 and took <= 3 and self.outcome(s) == "other/withdrawn/bridge" and aborted
                   and self.call_results(term, rid) and not gaps,
                   "%s in %.2f s; settled %s; gaps %d" % ((r.stdout + r.stderr).strip(), took, self.outcome(s), len(gaps)))
        self.idle(self.endpoint())

    def background(self, term, label, within):
        m = self.marker + "bg" + label
        t = time.time()
        self.prompt("Use the Agent tool once with run_in_background set to true, subagent_type general-purpose, "
                    "asking it to run exactly this Bash command and report its output: python3 -c 'print(\"%s\")'. "
                    "Then end your turn." % m)
        at, raised = self.raised(term, t, self.bash_marker(m), m)
        rid = raised["request"]
        deadline = raised.get("deadline")
        # The deadline is the engine clock's at the raise plus 3 s; the event's
        # `t` is stamped as it is emitted, a millisecond or so later.
        window = deadline - raised["t"] if isinstance(deadline, int) else None
        is_window = window is not None and abs(window - 3000) <= 50
        if within:
            r = self.cli("decide", NAME, rid, "allow")
            _, s = self.settled(term, rid)
            self.check("a background subagent's request: a 3 s deadline, answerable from the CLI within it",
                       raised.get("agentId") and is_window and r.returncode == 0 and self.outcome(s) == "other/allow/cli",
                       "agent %s, window %s ms; %s; settled %s" % (raised.get("agentId"), window, r.stdout.strip(), self.outcome(s)))
        else:
            drawn_early = []
            while time.time() < deadline / 1000 - 0.3:
                drawn_early.append(self.dialog())
                time.sleep(0.2)
            seen = wait_for("the dialog after the window", 10, lambda: self.dialog() and time.time())
            r = self.cli("decide", NAME, rid, "allow")
            time.sleep(1)
            # A key that lands as the dialog mounts can be lost (one live run):
            # pressed again while the dialog stays, and the presses counted.
            presses, s = 0, None
            while s is None and presses < 3:
                self.keys("Enter")
                presses += 1
                try:
                    _, s = self.settled(term, rid, seconds=6)
                except TimeoutError:
                    if not self.dialog():
                        _, s = self.settled(term, rid)
            self.check("a background subagent's dialog is drawn only after its 3 s window",
                       is_window and drawn_early and not any(drawn_early) and seen - deadline / 1000 < 3,
                       "window %s ms; drawn %.2f s after the deadline" % (window, seen - deadline / 1000))
            self.check("past the window only the terminal answers it",
                       r.returncode == 1 and "window" in r.stderr and s and self.outcome(s) == "terminal/allow/terminal",
                       "%s; settled %s (Enter pressed %d times)" % (r.stderr.strip(), s and self.outcome(s), presses))
        wait_for("the subagent's result", 90, lambda: term.seen(
            lambda e: e.get("type") == "tool" and e.get("phase") == "result" and e.get("toolUseId") == rid))
        self.idle(self.endpoint(), 150)

    def question(self, term):
        t = time.time()
        self.prompt("Ask me with your question tool (not async) which fruit I prefer, options Apple and Mango. "
                    "Then tell me my choice in one sentence.")
        at, raised = self.raised(term, t, lambda e: "questions" in json.dumps(e.get("input")), "the question")
        rid = raised["request"]
        wait_for("the question's dialog", 20, lambda: "Apple" in self.pane() and "Mango" in self.pane())
        r = self.cli("answer", NAME, rid, "mango")
        _, s = self.settled(term, rid)
        # The turn the question was asked in: a background subagent's
        # completion can open a main turn of its own around this prompt, whose
        # end is not this one's.
        started = [e for t_e, e in term.seen_at(lambda e: is_main(e, "turn", "start")) if t_e <= at]
        turn = started[-1].get("turnId") if started else None
        if turn is not None:
            wait_for("the question's turn to end", 150, lambda: term.seen(
                lambda e: is_main(e, "turn", "complete") and e.get("turnId") == turn, t))
        else:
            self.turn_end(term, t)
        text = LC.main_text(term, t)
        turns = [(str(e.get("text"))[:40], e.get("turnId", "")[:8]) for e in term.seen(lambda e: is_main(e, "turn", "start"), t)]
        self.check("a question answered with sminos answer reaches the model (the ask mod loaded)",
                   r.returncode == 0 and self.outcome(s) == "other/answered/cli" and "mango" in text.lower(),
                   "%s; raised as %s in turn %s; settled %s; model said %r; main turns since the prompt %s" % (
                       r.stdout.strip(), raised.get("tool"), turn and turn[:8], self.outcome(s), text[-100:], turns))
        self.idle(self.endpoint())

    def async_question(self, term):
        t = time.time()
        self.prompt("Ask me with your question tool, async true, which color I prefer: Red or Blue. "
                    "Then end your turn saying waiting.")
        at, raised = self.raised(term, t, lambda e: e.get("async") is True, "the async question")
        rid = raised["request"]
        self.turn_end(term, t)
        self.idle(self.endpoint())
        t1 = time.time()
        r = self.cli("answer", NAME, rid, "2")
        _, s = self.settled(term, rid)
        woke = wait_for("the delivered answer", 60, lambda: term.seen(
            lambda e: is_main(e, "turn", "start") and "Blue" in str(e.get("text")), t1))
        self.turn_end(term, t1)
        self.check("an async question answered with sminos answer is delivered by the ask mod",
                   r.returncode == 0 and raised.get("tool") == "mcp__sminos__AskUserQuestion"
                   and self.outcome(s) == "other/answered/cli" and woke,
                   "%s; settled %s; prompt %r" % (r.stdout.strip(), self.outcome(s), str(woke[0].get("text"))[:90]))
        self.idle(self.endpoint())

    def bg_job(self):
        m = self.marker + "job"
        # A --bg job starts in permission mode `auto` (live, 2.1.300), which runs the call unasked.
        self.claude(["--bg", "--plugin-dir", self.plugin, "--model", "haiku", "--permission-mode", "default", "-n", "brreq",
                     "Run exactly this Bash command, then reply in one short sentence: python3 -c 'print(\"%s\")'" % m])
        rec = wait_for("the bg job's record", 60, lambda: self.record("brreq"))
        self.jobs.append(rec.get("jobId"))
        sock = os.path.join(self.smh, "bridge", rec["sessionId"] + ".sock")
        wait_for("the bg job's endpoint", 60, lambda: os.path.exists(sock) and LB.request(sock, "GET", "/status", timeout=3)[0] == 200)
        bg = LC.Stream(sock)
        wait_for("the bg subscription", 10, lambda: bg.subscriptions > 0)
        _, raised = self.raised(bg, 0, self.bash_marker(m), m)
        rid = raised["request"]
        r = self.cli("decide", "brreq", rid, "allow")
        _, s = self.settled(bg, rid)
        res = wait_for("the job's call result", 60, lambda: self.call_results(bg, rid))
        self.check("a --bg job's permission prompt is answered from the CLI",
                   r.returncode == 0 and self.outcome(s) == "other/allow/cli" and m in str(res[0].get("text")),
                   "%s; settled %s" % (r.stdout.strip(), self.outcome(s)))
        bg.stop.set()

    def records_check(self, term):
        """Every settled request whose call the engine decided has its
        `tool_decision` record, as a mod receives it, naming who decided."""
        records = {r.get("tool_use_id"): r for r in self.records() if isinstance(r, dict)}
        expect = {"cli": {"hook"}, "terminal": {"user_temporary", "user_permanent", "user_reject"}, "bridge": {"user_abort"}}
        rows, bad = 0, []
        for s in term.seen(lambda e: e.get("type") == "settled"):
            rid, by = s.get("request"), s.get("by")
            raised = term.seen(lambda e, rid=rid: e.get("type") == "raised" and e.get("request") == rid)
            if not raised or raised[0].get("async") or by not in expect:
                continue
            rows += 1
            rec = records.get(rid)
            if rec is None or rec.get("source") not in expect[by] or not rec.get("tool_name"):
                bad.append("%s %s: %s" % (rid[:20], by, rec))
        sources = sorted({str(r.get("source")) for r in records.values()})
        self.check("the engine's tool_decision records reach a mod through telemetry.log, naming each call and who decided",
                   rows >= 8 and not bad, "%d settlements matched to their record; sources seen %s%s"
                   % (rows, sources, ("; mismatched: " + "; ".join(bad)) if bad else ""))

    def block_rows(self, term):
        """Every block-row names a transcript row of its block's kind; counts
        the steps whose nth response row named block n."""
        starts, steps = {}, {}
        for e in term.seen(lambda e: e.get("type") in ("chunk", "block-row")):
            if e["type"] == "chunk" and isinstance(e["chunk"].get("index"), int):
                starts.setdefault((e["turnId"], e["agentId"], e["step"]), {}).setdefault(e["chunk"]["index"], e["chunk"]["kind"])
            elif e["type"] == "block-row":
                steps.setdefault((e["turnId"], e["agentId"], e["step"]), []).append(e)
        rows = {}
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", "*.jsonl")) + \
                glob.glob(os.path.join(self.cfg, "projects", "*", "*", "subagents", "*.jsonl")):
            with open(p) as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("uuid"):
                        rows[row["uuid"]] = row
        n = kind_ok = in_order = 0
        for k, brs in steps.items():
            in_order += [b["index"] for b in brs] == list(range(len(brs)))
            for b in brs:
                n += 1
                content = ((rows.get(b["uuid"]) or {}).get("message") or {}).get("content") or [{}]
                kind_ok += KIND.get(content[0].get("type")) == starts.get(k, {}).get(b["index"])
        self.check("every block-row names a transcript row of its block's kind", n and kind_ok == n,
                   "%d block-rows over %d steps, %d of their kind; steps whose nth row named block n: %d of %d"
                   % (n, len(steps), kind_ok, in_order, len(steps)))

    def run(self):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer", 20, self.status)
        term = LC.Stream(self.endpoint())
        wait_for("the subscription", 10, lambda: term.subscriptions > 0)

        self.cli_first(term)
        self.cli_deny(term)
        self.terminal_first(term)
        self.both_at_once(term, 1, 0.3)
        self.both_at_once(term, 2, 0.0)
        self.both_at_once(term, 3, -0.05)
        self.interrupt_open(term)
        self.background(term, "in", within=True)
        self.background(term, "out", within=False)
        self.question(term)
        self.async_question(term)
        self.records_check(term)
        self.block_rows(term)
        self.bg_job()


def main():
    live = Requests("--keep" in sys.argv[1:])
    print("live requests check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
        print("  pane at the failure:\n" + "\n".join("    " + line for line in live.pane().rstrip().splitlines()[-25:]))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed), len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
