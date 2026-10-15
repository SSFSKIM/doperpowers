#!/usr/bin/env python3
"""Live check of requests from outside and their settlement (DC2 M3).

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session and a `--bg` job:
- a permission prompt is raised and settled once, naming the side whose
  answer the engine used, in DC2.G3's four cases: answered from the CLI
  first, in the terminal first (the request settles within 2 s of the key),
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

    tests/mods/live-requests-check.py [--keep]
"""

import glob
import importlib.util
import json
import os
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
        with open(self.envfile, "a") as f:
            f.write("export CLAUDE_CODE_DAEMON_COLD_START=transient\n")

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
        t, at, raised = self.ask_bash(term, m)
        rid = raised["request"]
        r = self.cli("decide", NAME, rid, "allow")
        _, s = self.settled(term, rid)
        self.turn_end(term, t)
        ran = any(m in str(e.get("text")) for e in self.call_results(term, rid))
        self.check("CLI first: raised with its tool, input and tool-use id; the CLI's allow settles it as the CLI's",
                   r.returncode == 0 and "settled from here: allow" in r.stdout and rid.startswith("toolu_")
                   and self.outcome(s) == "other/allow/cli" and ran and len(self.all_settled(term, rid)) == 1,
                   "%s; settled %s; ran %s" % ((r.stdout + r.stderr).strip(), self.outcome(s), ran))
        self.check("CLI first: the engine marked the hook's answer as the one it used", self.marked(self.session, rid),
                   "%d mark rows" % len(self.marked(self.session, rid)))
        self.idle(self.endpoint())

    def cli_deny(self, term):
        m = self.marker + "deny"
        t, at, raised = self.ask_bash(term, m)
        rid = raised["request"]
        r = self.cli("decide", NAME, rid, "deny", "--message", "Not now: say the word WALNUT instead.")
        _, s = self.settled(term, rid)
        self.turn_end(term, t)
        res = self.call_results(term, rid)
        self.check("a CLI deny carries its message to the model",
                   r.returncode == 0 and self.outcome(s) == "other/deny/cli" and res and res[0].get("isError")
                   and "WALNUT" in str(res[0].get("text")) and "WALNUT" in LC.main_text(term, t),
                   "%s; settled %s; result %r" % (r.stdout.strip(), self.outcome(s), str(res[0].get("text"))[:80] if res else None))
        self.idle(self.endpoint())

    def terminal_first(self, term):
        m = self.marker + "term"
        # A call that runs on: its settlement must come from the poll ending, not from its result.
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
        window = deadline - raised["t"] if isinstance(deadline, int) else None
        if within:
            r = self.cli("decide", NAME, rid, "allow")
            _, s = self.settled(term, rid)
            self.check("a background subagent's request: a 3 s deadline, answerable from the CLI within it",
                       raised.get("agentId") and window == 3000 and r.returncode == 0 and self.outcome(s) == "other/allow/cli",
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
                       window == 3000 and drawn_early and not any(drawn_early) and seen - deadline / 1000 < 3,
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
        self.turn_end(term, t)
        text = LC.main_text(term, t)
        self.check("a question answered with sminos answer reaches the model (the ask mod loaded)",
                   r.returncode == 0 and self.outcome(s) == "other/answered/cli" and "mango" in text.lower(),
                   "%s; raised as %s; settled %s; model said %r" % (r.stdout.strip(), raised.get("tool"),
                                                                    self.outcome(s), text[-100:]))
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
                   r.returncode == 0 and raised.get("tool") == "mcp__doperpowers__AskUserQuestion"
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
