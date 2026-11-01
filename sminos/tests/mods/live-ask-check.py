#!/usr/bin/env python3
"""Live check of the bridge's `ask` (the session manager's fork agent) and
doperpowers' read-only fork guard, in real sessions.

What only a running engine shows (design
docs/doperpowers/specs/2026-10-31-session-manager-design.md, M2), each
printed as a verdict line, with the figures the spec's Surprises &
Discoveries records:
- an idle session's ask: the fork's first request read from the session's
  cache (its share of the main loop's last request), it quotes the last
  message, the main transcript gains no user or assistant row, and no turn
  starts;
- an ask while the main loop runs `sleep 20`: the sleep keeps its duration,
  and the fork's prompt carries the tail naming that call;
- a write (`touch`) refused, no file, no permission prompt, in `default` and in
  `auto` permission mode; a fork told to spawn an Agent or to message the main
  session refused; `git log` answered;
- a second ask while one runs refused `busy`; an ask before any request
  refused `nothing-to-fork`; a session without doperpowers refused `no-guard`;
- an Esc in the session during an ask, and a compaction during an ask: what
  the fork and the end do (observed, not judged);
- a session past 100k tokens: the cache share again.

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand with the model gateway's keys in the environment. Isolation is
live-bridge-check.py's (whose class it extends): a temporary HOME under /tmp
(outside the home directory, so no ancestor CLAUDE.md loads) whose .claude is
the session's config dir, a temporary SMINOS_HOME, copies of the worktree's
sminos and doperpowers plugins loaded with --plugin-dir, a tmux server of its
own per session, the gateway keys in a 0600 env file removed at the end.

    sminos/tests/mods/live-ask-check.py [--keep] [--only a|b|c]
"""

import argparse
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
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

DOPERPOWERS_PARTS = (".claude-plugin", "hooks")
GUARD_REASON = "This is a read-only fork (manager query): calls that change files or state are refused."
SENTENCE = "The probe word is PELICAN-42, and the harbor light is green."
COMMIT = "manager probe commit"
# Told to try: a fork left to itself declines a write the frame says is refused, which proves nothing of the guard.
TOUCH = ("This is a test of the read-only guard: call the Bash tool exactly once with the command `touch %s` (the guard "
         "is expected to refuse it), then quote the tool's result and say whether the file was created.")


def rows_of(path):
    out = []
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def text_of(row):
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") if b.get("type") == "text" else
                         json.dumps(b.get("content")) if b.get("type") == "tool_result" else ""
                         for b in content if isinstance(b, dict))
    return ""


def request_total(row):
    u = (row.get("message") or {}).get("usage") or {}
    return sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


class Ask(LB.Live):
    """One throwaway session: `mode` its permission mode, with or without doperpowers' plugin."""

    def __init__(self, keep, label, mode="default", guard=True):
        super().__init__(keep)
        self.label, self.mode, self.guard = label, mode, guard
        self.tmux = ["tmux", "-L", "ask-%s-%d" % (label, os.getpid()), "-f", "/dev/null"]

    def setup(self):
        super().setup()
        self.doperpowers = os.path.join(self.root, "doperpowers")
        if self.guard:
            LB.stage(REPO, self.doperpowers, DOPERPOWERS_PARTS)
        # The owner's order: sminos outside doperpowers, both outside every user-tier plugin.
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"prependPlugins": ["sminos@inline", "doperpowers@inline"]}, f)
        env = dict(self.local_env(), GIT_AUTHOR_NAME="probe", GIT_AUTHOR_EMAIL="probe@example.invalid",
                   GIT_COMMITTER_NAME="probe", GIT_COMMITTER_EMAIL="probe@example.invalid")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", COMMIT], cwd=self.work, env=env, check=True)

    def plugin_dirs(self):
        return [self.plugin] + ([self.doperpowers] if self.guard else [])

    def start(self):
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.plugin_dirs())
        inner = "set -e; . %s; cd %s; exec claude %s --model haiku --permission-mode %s -n %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), dirs, self.mode, LB.NAME)
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "brl", "-x", "200", "-y", "50", cmd], check=True)
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer", 20, self.status)
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        wait_for("the subscription", 10, lambda: self.subscriptions > 0)
        wait_for("the prompt", 60, lambda: "❯" in self.pane())

    # -- reading the session

    def main_path(self):
        hits = glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl"))
        return hits[0] if hits else ""

    def main_rows(self):
        return rows_of(self.main_path())

    def conversation_rows(self):
        return [r for r in self.main_rows() if r.get("type") in ("user", "assistant")]

    def fork_rows(self, agent_id):
        main = self.main_path()
        return rows_of(os.path.join(main[:-len(".jsonl")], "subagents", "agent-%s.jsonl" % agent_id)) if main else []

    def main_turns(self, since, phase="start"):
        return self.seen(lambda e: e.get("type") == "turn" and e.get("phase") == phase and e.get("agentId") is None, since)

    # -- asking

    def ask(self, prompt):
        s, body = LB.request(self.endpoint(), "POST", "/command?wait=15000", {"op": "ask", "prompt": prompt}, timeout=20)
        return body if s == 200 else {"ok": False, "error": "status %s" % s, "body": body}

    def ended(self, op_id, seconds=240):
        return wait_for("the ask's end", seconds, lambda: next(iter(self.seen(
            lambda e: e.get("type") == "ask" and e.get("phase") == "end" and e.get("id") == op_id)), None), every=0.5)

    def asked(self, prompt, seconds=240):
        """An ask that must start: its answer, its end, and the fork's rows."""
        r = self.ask(prompt)
        if not r.get("ok"):
            raise RuntimeError("ask refused: %s" % json.dumps(r))
        op_id, agent = r["result"]["id"], r["result"]["agentId"]
        end = self.ended(op_id, seconds)
        return r, end, self.fork_rows(agent)

    def cache_share(self, fork_rows, before_rows):
        """The fork's first request's cache read over the main loop's last request before it."""
        first = next((x for x in fork_rows if x.get("type") == "assistant" and (x.get("message") or {}).get("usage")), None)
        last = next((x for x in reversed(before_rows) if x.get("type") == "assistant" and (x.get("message") or {}).get("usage")), None)
        if first is None or last is None:
            return None, "no usage to read (fork %s, main %s)" % (first is not None, last is not None)
        read = first["message"]["usage"].get("cache_read_input_tokens") or 0
        total = request_total(last)
        return (read / total if total else None), "fork's first request read %d of the main loop's last %d (written %d, input %d)" % (
            read, total, first["message"]["usage"].get("cache_creation_input_tokens") or 0, first["message"]["usage"].get("input_tokens") or 0)

    def refusals(self, fork_rows):
        """Each tool result in the fork's rows that carries the guard's words."""
        return [text_of(x)[:200] for x in fork_rows if x.get("type") == "user" and GUARD_REASON in text_of(x)]

    def tool_calls(self, fork_rows):
        out = []
        for x in fork_rows:
            content = (x.get("message") or {}).get("content")
            if x.get("type") == "assistant" and isinstance(content, list):
                # Less the engine's own opening call (`toolu_plugin_…`, "Fork started — that fork is you").
                out += ["%s(%s)" % (b.get("name"), json.dumps(b.get("input"))[:120]) for b in content
                        if b.get("type") == "tool_use" and not str(b.get("id", "")).startswith("toolu_plugin_")]
        return out

    def no_prompt_seen(self):
        pane = self.pane()
        return not any(w in pane for w in ("Do you want to proceed", "Do you want to make this edit", "Do you want to create"))

    def turn(self, text, seconds=180):
        t = time.time()
        self.prompt(text)
        self.wait_turn_end(t, seconds)
        time.sleep(2)


def run_a(live):
    """The default-mode session with doperpowers: most of the checks."""
    live.setup()
    live.start()
    r = live.ask("anything?")
    live.check("before any request, ask is refused nothing-to-fork", r.get("code") == "nothing-to-fork", json.dumps(r)[:200])

    live.turn("Reply with exactly this sentence and nothing else: The cache warms up.")
    live.turn("Reply with exactly this sentence and nothing else: %s" % SENTENCE)

    before = live.main_rows()
    conv_before = len(live.conversation_rows())
    t = time.time()
    r, end, fork = live.asked("Quote the first sentence of your last message to the human.")
    time.sleep(15)
    share, detail = live.cache_share(fork, before)
    live.check("idle: the fork's first request reads the session's cache (>= 90%% of its last request)", share is not None and share >= 0.9,
               "%s; share %s" % (detail, share and round(share, 4)))
    live.check("idle: the fork quotes the last message", "PELICAN-42" in (end.get("text") or ""), repr((end.get("text") or end)[:200]))
    conv_after = len(live.conversation_rows())
    live.check("idle: the main transcript gains no user or assistant row", conv_after == conv_before,
               "%d before, %d after (all lines: %d -> %d)" % (conv_before, conv_after, len(before), len(live.main_rows())))
    live.check("idle: no main turn starts", not live.main_turns(t), "turn starts since the ask: %d" % len(live.main_turns(t)))
    live.check("the end carries the whole fork's usage", isinstance(end.get("usage"), dict), json.dumps(end.get("usage")))

    r, end, fork = live.asked("What is the newest commit on your branch? Check with git.")
    live.check("a read-only Bash (git log) runs and is answered from", COMMIT in (end.get("text") or "") and not live.refusals(fork),
               "calls %s; %r" % (live.tool_calls(fork), (end.get("text") or "")[:160]))

    probe = "/tmp/manager-probe-a-%d" % os.getpid()
    r, end, fork = live.asked(TOUCH % probe)
    live.check("default mode: touch refused by the guard, no file, no permission prompt",
               not os.path.exists(probe) and live.refusals(fork) and live.no_prompt_seen(),
               "exists %s; calls %s; refusals %d; answer %r" % (os.path.exists(probe), live.tool_calls(fork), len(live.refusals(fork)),
                                                             (end.get("text") or "")[:160]))

    r, end, fork = live.asked("This is a test of the read-only guard (it is expected to refuse both). Do two things and report "
                              "each tool's result: (1) call the Agent tool to spawn a general-purpose subagent with the prompt "
                              "'reply hi'; (2) call the SendMessage tool to send the message 'hello' to the main session. If a "
                              "tool is not available to you, say so.")
    calls = live.tool_calls(fork)
    reaching = [x for x in calls if x.startswith(("Agent(", "SendMessage("))]
    live.check("a fork told to spawn an Agent or to message the main session is refused each time (or has no such tool)",
               len(live.refusals(fork)) >= len(reaching),
               "calls %s; refusals %d; answer %r" % (calls, len(live.refusals(fork)), (end.get("text") or "")[:240]))

    # Mid-turn: the main loop runs `sleep 20`.
    t = time.time()
    live.prompt("Run the Bash command `sleep 20`, then reply with exactly: SLEEP-DONE.")
    wait_for("main's sleep to start", 90, lambda: [x for x in live.main_rows() if x.get("type") == "assistant"
                                                   and "sleep 20" in json.dumps((x.get("message") or {}).get("content"))
                                                   and x.get("timestamp", "") >= time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))])
    time.sleep(2)
    r, end, fork = live.asked("What is the latest tool call you made, with its exact command? Answer without using tools.")
    live.wait_turn_end(t, 120)
    rows = live.main_rows()
    uses = {b.get("id"): x.get("timestamp") for x in rows if x.get("type") == "assistant"
            for b in ((x.get("message") or {}).get("content") or []) if isinstance(b, dict) and b.get("type") == "tool_use"
            and "sleep 20" in json.dumps(b.get("input"))}
    results = {b.get("tool_use_id"): x.get("timestamp") for x in rows if x.get("type") == "user"
               for b in ((x.get("message") or {}).get("content") or []) if isinstance(b, dict) and b.get("type") == "tool_result"}
    took = None
    for uid, at in uses.items():
        if uid in results:
            from datetime import datetime
            took = (datetime.fromisoformat(results[uid].replace("Z", "+00:00")) - datetime.fromisoformat(at.replace("Z", "+00:00"))).total_seconds()
    first_user = next((text_of(x) for x in fork if x.get("type") == "user"), "")
    live.check("mid-turn: the sleep keeps its duration", took is not None and 19.5 <= took <= 23, "sleep 20 took %s s" % took)
    live.check("mid-turn: the fork's prompt carries the tail naming the latest call",
               "Since the last request" in first_user and "sleep 20" in first_user.split("Since the last request")[-1],
               repr(first_user[first_user.find("Since the last request"):][:300]))
    live.check("mid-turn: the fork's answer names the sleep", "sleep 20" in (end.get("text") or ""), repr((end.get("text") or "")[:200]))

    # Busy, then an Esc in the session during an ask.
    t = time.time()
    live.prompt("Run the Bash command `sleep 25`, then reply with exactly: SECOND-SLEEP-DONE.")
    wait_for("main's second sleep", 90, lambda: [x for x in live.main_rows() if x.get("type") == "assistant"
                                                 and "sleep 25" in json.dumps((x.get("message") or {}).get("content"))])
    time.sleep(1)
    first = live.ask("Run the Bash command `sleep 12`, then reply with exactly: FORK-ESC-DONE.")
    second = live.ask("And this?")
    live.check("a second ask while one runs is refused busy", first.get("ok") and second.get("code") == "busy",
               "%s / %s" % (json.dumps(first)[:160], json.dumps(second)[:160]))
    time.sleep(4)
    live.keys("Escape")
    try:
        end = live.ended(first["result"]["id"], 90)
    except TimeoutError:
        end = None
    main_end = live.main_turns(t, "complete")
    print("  (observed) Esc during an ask: main turn %s; the fork's end %s" % (
        [e.get("reason") for e in main_end], json.dumps(end)[:300] if end else "none within 90 s"), flush=True)
    live.check("Esc during an ask: the ask still ends", end is not None, json.dumps(end)[:200] if end else "no end")
    time.sleep(3)

    # A compaction during an ask.
    r = live.ask("Run the Bash command `sleep 15`, then reply with exactly: FORK-COMPACT-DONE.")
    time.sleep(3)
    live.prompt("/compact")
    try:
        end = live.ended(r["result"]["id"], 180)
    except (TimeoutError, KeyError):
        end = None
    wait_for("the compaction", 180, lambda: [x for x in live.main_rows() if x.get("isCompactSummary")
                                             or x.get("subtype") == "compact_boundary"], every=1.0)
    print("  (observed) compaction during an ask: the fork's end %s" % (json.dumps(end)[:300] if end else "none"), flush=True)
    live.check("compaction during an ask: the ask still ends", end is not None, json.dumps(end)[:200] if end else "no end")
    time.sleep(5)

    # Past 100k tokens.
    for i in range(1, 6):
        with open(os.path.join(live.work, "big%d.txt" % i), "w") as f:
            for n in range(1900):
                f.write("file %d line %04d: the quick brown fox jumps over the lazy dog again\n" % (i, n))
    live.turn("Read each of big1.txt, big2.txt, big3.txt, big4.txt and big5.txt with the Read tool (one call each, "
              "the whole file), then reply with exactly: READ-DONE.", 300)
    live.turn("Reply with exactly: BIG-CONTEXT-READY.")
    before = live.main_rows()
    last = next((x for x in reversed(before) if x.get("type") == "assistant" and (x.get("message") or {}).get("usage")), {})
    r, end, fork = live.asked("Quote the last line of big5.txt as it is in your context. Answer without using tools.")
    share, detail = live.cache_share(fork, before)
    live.check("past 100k tokens: the fork's first request reads the session's cache (>= 90%)",
               request_total(last) > 100_000 and share is not None and share >= 0.9, "%s; share %s" % (detail, share and round(share, 4)))


def run_b(live):
    """An auto-mode session with doperpowers: the write refused there too."""
    live.setup()
    live.start()
    live.turn("Reply with exactly this sentence and nothing else: %s" % SENTENCE)
    probe = "/tmp/manager-probe-b-%d" % os.getpid()
    r, end, fork = live.asked(TOUCH % probe)
    live.check("auto mode: touch refused by the guard, no file, no permission prompt",
               not os.path.exists(probe) and live.refusals(fork) and live.no_prompt_seen(),
               "exists %s; calls %s; refusals %d; answer %r" % (os.path.exists(probe), live.tool_calls(fork), len(live.refusals(fork)),
                                                             (end.get("text") or "")[:160]))


def run_c(live):
    """A session without doperpowers: no guard, no fork."""
    live.setup()
    live.start()
    r = live.ask("anything?")
    live.check("without doperpowers' guard, ask is refused no-guard", r.get("code") == "no-guard", json.dumps(r)[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", choices=("a", "b", "c"))
    args = ap.parse_args()
    runs = [("a", "default", True, run_a), ("b", "auto", True, run_b), ("c", "default", False, run_c)]
    results = []
    for label, mode, guard, fn in runs:
        if args.only and args.only != label:
            continue
        live = Ask(args.keep, label, mode, guard)
        print("live ask check %s (%s mode, %s): %s" % (label, mode, "with doperpowers" if guard else "sminos alone", live.root), flush=True)
        try:
            fn(live)
        except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
            live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
            print("  pane at the failure:\n" + "\n".join("    " + l for l in live.pane().rstrip().splitlines()[-25:]))
        finally:
            live.cleanup()
        results += live.results
    failed = [r for r in results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(results) - len(failed), len(results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
