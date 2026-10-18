#!/usr/bin/env python3
"""Live check of the compact mod's offer (its classic.Stop hook) in a real session.

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session with the plugin:
- at a main turn's end the hook's block reaches the model as "Stop hook
  feedback:" with the figures and the offer, inside the same turn: one
  offer, one more step, the model's decline line, and the turn ends (the
  Stop after the step carries stop_hook_active and passes);
- an offer the model takes compacts the conversation at the turn's end and
  the resume prompt it wrote enters and is answered;
- the model's tool list carries compact alone (context_usage is gone).

It spends model calls (haiku, short prompts, one compaction), so no suite
runs it: run it by hand with the model gateway's keys in the environment.
Isolation is live-bridge-check.py's (whose class it extends): a temporary
HOME whose .claude is the session's config dir, a temporary SMINOS_HOME, a
copy of the worktree's plugin, a tmux server of its own, the gateway keys in
a 0600 env file removed at the end. The gate is set to zero through
DOPERPOWERS_COMPACT_OFFER_FLOOR and _STEP, so a session this small is
offered at every turn's end.

    tests/mods/live-compact-offer-check.py [--keep]
"""

import glob
import importlib.util
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

COMPACT = "mcp__doperpowers__compact"


def text_of(row):
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def tool_uses(row):
    content = (row.get("message") or {}).get("content")
    if row.get("type") != "assistant" or not isinstance(content, list):
        return []
    return [b.get("name") for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def offer_text(row):
    """The offer as the transcript keeps it: the Stop hook's additional context (an attachment row), or, were
    it a block, the "Stop hook feedback:" user row the engine makes of a block's reason."""
    if row.get("type") == "attachment":
        a = row.get("attachment") or {}
        if a.get("type") == "hook_additional_context" and a.get("hookEvent") == "Stop":
            return "\n".join(a.get("content") or [])
        return ""
    if row.get("type") == "user" and text_of(row).startswith("Stop hook feedback:"):
        return text_of(row)
    return ""


def is_offer(row):
    return "mcp__doperpowers__compact" in offer_text(row) and "Context:" in offer_text(row)


def is_compaction(row):
    return (row.get("type") == "system" and row.get("subtype") == "compact_boundary") or bool(row.get("isCompactSummary"))


class Offer(LB.Live):
    def setup(self):
        super().setup()
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": [COMPACT]}}, f)
        with open(self.envfile, "a") as f:
            f.write("export DOPERPOWERS_COMPACT_OFFER_FLOOR=0\nexport DOPERPOWERS_COMPACT_OFFER_STEP=0\n")

    def rows(self):
        out = []
        for path in glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")):
            with open(path) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        return out

    def main_turn_ends(self, since):
        return self.seen(lambda e: e.get("type") == "turn" and e.get("phase") == "complete" and e.get("agentId") is None, since)

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

        # A turn the model declines: the offer is one step inside the turn.
        t1 = time.time()
        self.prompt("Reply with the single word ready and nothing else.")
        wait_for("the first turn's end", 120, lambda: self.main_turn_ends(t1))
        # The transcript's rows land a moment after the turn's end event.
        def offered_and_answered():
            rows = self.rows()
            offers = [i for i, r in enumerate(rows) if is_offer(r)]
            return rows if offers and any(r.get("type") == "assistant" and text_of(r).strip() for r in rows[offers[0] + 1:]) else None
        rows = wait_for("the offer and the model's reply in the transcript", 20, offered_and_answered)
        offers = [i for i, r in enumerate(rows) if is_offer(r)]
        offer = offer_text(rows[offers[0]]) if offers else ""
        self.check("the turn's end puts the offer to the model",
                   len(offers) == 1 and "Context:" in offer and "tokens; window" in offer and COMPACT in offer,
                   "%d offer(s); first row %s: %r" % (len(offers), json.dumps({k: rows[offers[0]][k] for k in ("type", "attachment") if k in rows[offers[0]]})[:160] if offers else None, offer[:100]))
        after = [r for r in rows[offers[0] + 1:] if r.get("type") == "assistant"] if offers else []
        replies = [text_of(r) for r in after]
        self.check("the model declines in a line and the turn ends on it: one step, no loop",
                   len(after) >= 1 and any("not compacting" in t.lower() for t in replies)
                   and not any(COMPACT in tool_uses(r) for r in after) and len(self.main_turn_ends(t1)) == 1,
                   "replies after the offer %r, main turn ends %d" % ([t[:60] for t in replies], len(self.main_turn_ends(t1))))
        pane = self.pane()
        self.check("the person sees it under the stop hooks as feedback, not as an error",
                   "Stop hook feedback" in pane and "Stop hook error" not in pane,
                   "pane lines: %r" % [l.strip()[:80] for l in pane.splitlines() if "stop hook" in l.lower()])
        tools = set()
        for r in rows:
            tools.update(tool_uses(r))
        used_usage = any(n == "mcp__doperpowers__context_usage" for n in tools)
        self.check("context_usage is not among the tools the model reaches for", not used_usage, "tools used: %s" % sorted(tools))

        # A turn the model takes the offer in: the compaction at the turn's
        # end, then the resume prompt, answered.
        t2 = time.time()
        self.prompt("This is a test of the compaction offer. Reply with the single word ok and call no tool now. When the "
                    "offer then comes at the end of this turn, you must take it whatever the context size: call "
                    "mcp__doperpowers__compact with resume set to exactly: Say done.")
        wait_for("the second turn's end, the compaction, and the resume prompt's turn", 240,
                 lambda: len(self.main_turn_ends(t2)) >= 2)
        # The resume prompt enters under the plugin's name, in the engine's frame ("The doperpowers plugin sent a message: ...").
        def resumes(rows):
            # After the compaction, the prompt itself: not the person's prompt naming it, not the summary quoting it.
            boundary = [i for i, r in enumerate(rows) if is_compaction(r)]
            return [i for i, r in enumerate(rows) if boundary and i > boundary[-1] and r.get("type") == "user"
                    and not r.get("isCompactSummary") and "Say done." in text_of(r)]

        def resumed_and_answered():
            rows = self.rows()
            resumed = resumes(rows)
            return rows if resumed and any(r.get("type") == "assistant" and text_of(r).strip() for r in rows[resumed[0] + 1:]) else None
        rows = wait_for("the resume prompt and its answer in the transcript", 30, resumed_and_answered)
        offers = [i for i, r in enumerate(rows) if is_offer(r)]
        second = offers[1] if len(offers) > 1 else None
        taken = [i for i, r in enumerate(rows) if COMPACT in tool_uses(r)]
        compactions = [i for i, r in enumerate(rows) if is_compaction(r)]
        resumed = resumes(rows)
        answered = [i for i, r in enumerate(rows) if r.get("type") == "assistant" and i > (resumed[0] if resumed else len(rows))
                    and "done" in text_of(r).lower()]
        self.check("an offer the model takes is a compact call after the offer",
                   second is not None and taken and taken[0] > second,
                   "offers at %s, compact calls at %s" % (offers, taken))
        self.check("the turn's end compacts and the resume prompt enters and is answered",
                   compactions and taken and compactions[0] > taken[0] and resumed and resumed[0] > compactions[0] and answered,
                   "compaction rows at %s, resume at %s, answered at %s" % (compactions, resumed, answered[:1]))


def main():
    live = Offer("--keep" in sys.argv[1:])
    print("live compact-offer check (%s):" % live.root, flush=True)
    try:
        live.run()
    except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
        live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
        print("  pane at the failure:\n" + "\n".join("    " + l for l in live.pane().rstrip().splitlines()[-25:]))
    finally:
        live.cleanup()
    failed = [r for r in live.results if not r[1]]
    print("%s: %d of %d checks passed" % ("FAILED" if failed else "passed", len(live.results) - len(failed),
                                         len(live.results)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
