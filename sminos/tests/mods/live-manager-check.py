#!/usr/bin/env python3
"""Live acceptance of the session manager's queries and derive on `btw`, in a
real throwaway session (design docs/doperpowers/specs/2026-10-31-session-manager-design.md,
acceptance 1, 4–7, 9 and 10, run by M5 before merge).

Everything goes through the shipped commands, as the owner runs them:
`manager query` for 4–7, `sminos derive` for 9. Each check prints a verdict
line with its figures:
- 1: the manager skill is offered in the slash menu, and the session's
  model-visible skill listing names `sminos:sminos` and not `sminos:manager`;
- 4: a query on an idle live session answers `via fork agent`, its cache read
  at least 90% of the session's last request, the main transcript gaining no
  user or assistant row and no main turn starting;
- 5: the idle answer quotes the last message; mid-turn (`sleep 20`), the answer
  names that call;
- 6: "the newest commit on your branch" answered from git; a `touch` refused,
  no file, no permission prompt;
- 9: `sminos derive` prints its line and says `via btw` on stderr, its cache
  read near the session's context;
- 10: across the queries, the session's project log gains no event but
  membership's `joined`/`retired`;
- 7: the session stopped, a query answers `via headless fork`; and a stopped
  member's derive (observed: a terminal session is retired from membership once
  its process ends, so derive may no longer find it).

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand with the model gateway's keys in the environment. Isolation is
live-ask-check.py's (whose class it extends): a temporary HOME under /tmp
whose .claude is the session's config dir, a temporary SMINOS_HOME, copies of
the worktree's sminos and doperpowers plugins loaded with --plugin-dir, a tmux
server of its own, the gateway keys in a 0600 env file removed at the end.

    sminos/tests/mods/live-manager-check.py [--keep] [--model haiku|sonnet|opus]
"""

import argparse
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_ask_check", os.path.join(HERE, "live-ask-check.py"))
LA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LA)
LB, wait_for = LA.LB, LA.wait_for

MANAGER = os.path.join(LA.REPO, "sminos", "skills", "manager", "scripts", "manager")
VIA = re.compile(r"^via (fork agent|headless fork) · cache read ([\d,]+) · cache write ([\d,]+) · input ([\d,]+) · output ([\d,]+)$")


def num(s):
    return int(s.replace(",", ""))


class Mgr(LA.Ask):
    model = "haiku"

    def start(self):
        """Ask.start's session on this check's `model` (a fork inherits its session's model)."""
        real = subprocess.run

        def run_on_model(argv, *a, **kw):
            if argv[:len(self.tmux)] == self.tmux and "new-session" in argv:
                argv = argv[:-1] + [argv[-1].replace("--model haiku", "--model %s" % self.model)]
            return real(argv, *a, **kw)
        subprocess.run = run_on_model
        try:
            super().start()
        finally:
            subprocess.run = real

    def tool_env(self):
        """What the owner's shell gives a command: the isolation, and the gateway's keys for a headless fork."""
        env = self.local_env()
        env.update({k: os.environ[k] for k in LB.GATEWAY_KEYS})
        return env

    def run_cmd(self, argv, timeout=400):
        r = subprocess.run(argv, cwd="/tmp", env=self.tool_env(), capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr

    def query(self, question, member=None):
        """`manager query`: its exit, the answer, and the `via` line's figures (or None)."""
        code, out, err = self.run_cmd([MANAGER, "query", member or self.session, question])
        lines = out.rstrip("\n").splitlines()
        m = VIA.match(lines[-1]) if lines else None
        via = {"via": m.group(1), "cacheRead": num(m.group(2)), "cacheWrite": num(m.group(3)),
               "input": num(m.group(4)), "output": num(m.group(5))} if m else None
        text = "\n".join(lines[:-1]) if m else out
        print("  (query) %r -> exit %d, %s, %r%s" % (question[:60], code, json.dumps(via), text[:200],
                                                     (" stderr %r" % err[-300:]) if err.strip() else ""), flush=True)
        return code, text, via

    def last_request_total(self):
        last = next((x for x in reversed(self.main_rows()) if x.get("type") == "assistant"
                     and (x.get("message") or {}).get("usage")), None)
        return LA.request_total(last) if last else 0

    def log_events(self):
        out = []
        for path in glob.glob(os.path.join(self.smh, "projects", "*", "log", "*.jsonl")):
            out += LA.rows_of(path)
        return out

    def skill_listing(self):
        """The skill names the session's model was shown: the listing attachments in its transcript."""
        text = "\n".join(json.dumps(r) for r in self.main_rows() if r.get("type") == "attachment"
                         or "skill" in json.dumps(r.get("attachment") or {}))
        return text


def run(live):
    live.setup()
    live.start()

    # 1. The slash menu offers the skill; the model's listing does not.
    live.keys("-l", "/sminos:manag")
    time.sleep(2)
    menu = live.pane()
    live.keys("C-u")
    time.sleep(0.5)
    live.check("1: the slash menu offers /sminos:manager", "sminos:manager" in menu,
               "pane lines with 'manager': %r" % [l.strip() for l in menu.splitlines() if "manager" in l][:4])
    live.turn("Reply with exactly this sentence and nothing else: The cache warms up.")
    listing = live.skill_listing()
    live.check("1: the model-visible skill listing names sminos:sminos and not sminos:manager",
               "sminos:sminos" in listing and "sminos:manager" not in listing,
               "sminos:sminos %s, sminos:manager %s (listing rows %d chars)" % (
                   "sminos:sminos" in listing, "sminos:manager" in listing, len(listing)))

    live.turn("Run these ten Bash commands one at a time, each its own tool call: echo one, echo two, echo three, "
              "echo four, echo five, echo six, echo seven, echo eight, echo nine, echo ten. Then reply: COUNTED.", 240)
    live.turn("Reply with exactly this sentence and nothing else: %s" % LA.SENTENCE)

    log_before = live.log_events()
    conv_before = len(live.conversation_rows())
    lines_before = len(live.main_rows())

    # 4. A cheap answer from an idle live session, with nothing added to it.
    total = live.last_request_total()
    t = time.time()
    code, text, via = live.query("What are you waiting on from the human right now?")
    time.sleep(5)
    share = via["cacheRead"] / total if via and total else None
    live.check("4: an idle live session answers via fork agent, cache read >= 90% of its last request",
               code == 0 and via and via["via"] == "fork agent" and share is not None and share >= 0.9,
               "exit %d; via %s; last request %d; share %s" % (code, json.dumps(via), total, share and round(share, 4)))
    live.check("4: the main transcript gains no user or assistant row", len(live.conversation_rows()) == conv_before,
               "%d before, %d after (all lines %d -> %d)" % (conv_before, len(live.conversation_rows()), lines_before,
                                                            len(live.main_rows())))
    live.check("4: no main turn starts", not live.main_turns(t), "turn starts since: %d" % len(live.main_turns(t)))

    # 5. Current: idle, the last message.
    code, text, via = live.query("Quote the first sentence of your last message to the human.")
    live.check("5: idle, the answer quotes the last message", code == 0 and "PELICAN-42" in text, repr(text[:200]))

    # 6. Tools, held read-only.
    code, text, via = live.query("What is the newest commit on your branch?")
    live.check("6: the newest commit answered from git", code == 0 and LA.COMMIT in text, repr(text[:200]))
    # A path inside a directory this run made, so no file of anyone else's is ever touched or removed.
    probe_dir = tempfile.mkdtemp(prefix="manager-probe-")
    probe = os.path.join(probe_dir, "probe")
    code, text, via = live.query("Run: touch %s — then say whether it worked." % probe)
    refused = re.search(r"refus|denied|not allowed|read-only|blocked|could not|did not|didn't|cannot|can't", text, re.I)
    live.check("6: touch refused, no file, no permission prompt",
               code == 0 and refused and not os.path.exists(probe) and live.no_prompt_seen(),
               "file exists %s; refusal words %s; %r" % (os.path.exists(probe), bool(refused), text[:200]))
    if os.path.exists(probe):
        os.unlink(probe)
    os.rmdir(probe_dir)

    # 5. Current: mid-turn.
    t = time.time()
    live.prompt("Run the Bash command `sleep 20`, then reply with exactly: SLEEP-DONE.")
    wait_for("main's sleep to start", 90, lambda: [x for x in live.main_rows() if x.get("type") == "assistant"
                                                   and "sleep 20" in json.dumps((x.get("message") or {}).get("content"))
                                                   and x.get("timestamp", "") >= time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))])
    time.sleep(2)
    code, text, via = live.query("What is the latest tool call you made, with its exact command? Answer without using tools.")
    live.check("5: mid-turn, the answer knows the latest tool call", code == 0 and "sleep 20" in text, repr(text[:200]))
    live.wait_turn_end(t, 120)
    time.sleep(2)

    # 10. Nothing written by the queries.
    conv_now = len(live.conversation_rows())
    new_events = [e for e in live.log_events() if e not in log_before]
    foreign = [e for e in new_events if e.get("kind") not in ("joined", "retired")]
    live.check("10: after the queries, the project log gained no event but membership's",
               not foreign, "new events %s" % [e.get("kind") for e in new_events])
    # The mid-turn prompt added the session's own turn; the queries themselves added none (checked at 4).
    print("  (observed) conversation rows %d before the queries, %d after (the sleep turn is the session's own)" % (
        conv_before, conv_now), flush=True)

    # 9. derive on btw.
    total = live.last_request_total()
    code, out, err = live.run_cmd([live.sminos(), "derive", live.session], timeout=300)
    m = re.search(r"via (btw|headless fork) · cache read ([\d,]+) · input ([\d,]+)", err)
    read = num(m.group(2)) if m else None
    live.check("9: derive of a live member prints its line and goes via btw, cache read near the context",
               code == 0 and out.strip() and m and m.group(1) == "btw" and read and read >= 0.9 * total,
               "exit %d; line %r; stderr %r; context %d" % (code, out.strip()[:160], err.strip()[-240:], total))

    # 7. A stopped session still answers.
    session = live.session
    live.prompt("/exit")
    try:
        wait_for("the session's process to end", 60, lambda: not os.path.exists(live.endpoint()) or not live.status(), every=1.0)
    except TimeoutError:
        subprocess.run(live.tmux + ["kill-server"], capture_output=True)
        time.sleep(5)
    code, text, via = live.query("What is the probe word in your last message?", member=session)
    live.check("7: a stopped session answers via headless fork", code == 0 and via and via["via"] == "headless fork"
               and "PELICAN-42" in text, "exit %d; via %s; %r" % (code, json.dumps(via), text[:200]))
    code, out, err = live.run_cmd([live.sminos(), "derive", session], timeout=300)
    print("  (observed) derive of the stopped member: exit %d; line %r; stderr %r" % (code, out.strip()[:160], err.strip()[-300:]),
          flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--model", default="haiku", help="the session's model, which its forks inherit (default haiku)")
    args = ap.parse_args()
    live = Mgr(args.keep, "m", "default", True)
    live.model = args.model
    print("live manager check (%s, default mode, with doperpowers): %s" % (args.model, live.root), flush=True)
    try:
        run(live)
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
