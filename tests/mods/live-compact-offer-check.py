#!/usr/bin/env python3
"""Live check of the compact mod's offer (a prompt it submits at a turn's end) in a real session.

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session with the plugin:
- at a main turn's end the offer enters as the plugin's prompt ("The
  doperpowers plugin sent a message:" with the figures and the offer), a
  turn of its own after the one it follows: the model's decline line ends
  it, and that turn's end offers nothing more, even with the gate at zero;
- the person's terminal draws no Stop hook row for it;
- a prompt the person queued while the turn ran goes first, its turn ends
  with no second offer, and the offer then enters with the figures read
  as it enters (the last response's, not the earlier turn's);
- an offer the model takes compacts the conversation at the end of the
  offer's turn and the resume prompt it wrote enters and is answered;
- the model's tool list carries compact alone (context_usage is gone).

It spends model calls (haiku, short prompts, one compaction), so no suite
runs it: run it by hand with the model gateway's keys in the environment.
Isolation is sminos/tests/mods/live-bridge-check.py's (whose class it extends): a temporary
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
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DOPERPOWERS_PARTS = (".claude-plugin", "hooks", "skills", "agents", "output-styles")
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(REPO, "sminos", "tests", "mods",
                                                                                 "live-bridge-check.py"))
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


def is_offer(row):
    """The offer as the transcript keeps it: a user row the plugin submitted, in the engine's frame."""
    origin = row.get("origin") or {}
    text = text_of(row)
    return (row.get("type") == "user" and origin.get("kind") == "plugin" and origin.get("name") == "doperpowers"
            and "Context:" in text and COMPACT in text)


def offered_figure(row):
    """The token count the offer states ("Context: 12,345 tokens; ...")."""
    m = re.search(r"Context: ([\d,]+) tokens", text_of(row))
    return int(m.group(1).replace(",", "")) if m else None


def input_total(row):
    """What a response was answered over: its input tokens, cached and not."""
    u = (row.get("message") or {}).get("usage") or {}
    return sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def answers(rows):
    """The indexes of the assistant rows that carry text."""
    return [i for i, r in enumerate(rows) if r.get("type") == "assistant" and text_of(r).strip()]


def is_compaction(row):
    return (row.get("type") == "system" and row.get("subtype") == "compact_boundary") or bool(row.get("isCompactSummary"))


class Offer(LB.Live):
    def setup(self):
        super().setup()
        self.doperpowers = os.path.join(self.root, "doperpowers")
        LB.stage(REPO, self.doperpowers, DOPERPOWERS_PARTS)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": [COMPACT]}}, f)
        with open(self.envfile, "a") as f:
            f.write("export DOPERPOWERS_COMPACT_OFFER_FLOOR=0\nexport DOPERPOWERS_COMPACT_OFFER_STEP=0\n")

    def plugin_dirs(self):
        return [self.plugin, self.doperpowers]

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

    def quiet(self, since, ends, seconds=8):
        """Waits `seconds` and answers whether the main turns ended since `since` are still `ends`."""
        time.sleep(seconds)
        return len(self.main_turn_ends(since)) == ends

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

        # A turn the model declines: the offer is a turn of its own, and its
        # end offers nothing more.
        t1 = time.time()
        self.prompt("Reply with the single word ready and nothing else.")
        wait_for("the turn's end and the offer's", 120, lambda: len(self.main_turn_ends(t1)) >= 2)
        quiet = self.quiet(t1, 2)

        def offered_and_answered():
            rows = self.rows()
            offers = [i for i, r in enumerate(rows) if is_offer(r)]
            return rows if offers and any(i > offers[0] for i in answers(rows)) else None
        rows = wait_for("the offer and the model's reply in the transcript", 20, offered_and_answered)
        offers = [i for i, r in enumerate(rows) if is_offer(r)]
        offer = text_of(rows[offers[0]]) if offers else ""
        self.check("the turn's end puts the offer to the model as the plugin's prompt, after the turn's answer",
                   len(offers) == 1 and "plugin sent a message" in offer and "tokens; window" in offer
                   and any(i < offers[0] for i in answers(rows)),
                   "%d offer(s): %r" % (len(offers), offer[:120]))
        after = [r for r in rows[offers[0] + 1:] if r.get("type") == "assistant"] if offers else []
        replies = [text_of(r) for r in after]
        self.check("the model declines in a line, and the offer's turn ends with no other offer (gate at zero)",
                   any("not compacting" in t.lower() for t in replies) and not any(COMPACT in tool_uses(r) for r in after)
                   and quiet,
                   "replies after the offer %r, main turn ends %d" % ([t[:60] for t in replies], len(self.main_turn_ends(t1))))
        pane = self.pane()
        self.check("the person's terminal draws no Stop hook row for it",
                   "stop hook" not in pane.lower(),
                   "pane lines: %r" % [l.strip()[:80] for l in pane.splitlines() if "stop hook" in l.lower()])
        tools = set()
        for r in rows:
            tools.update(tool_uses(r))
        used_usage = any(n == "mcp__doperpowers__context_usage" for n in tools)
        self.check("context_usage is not among the tools the model reaches for", not used_usage, "tools used: %s" % sorted(tools))

        # A prompt the person queues while the turn's answer streams goes
        # first; the offer waits, and enters with the figures as they are then.
        before = len(self.rows())
        t2 = time.time()
        self.prompt("Write about 300 words on how ocean tides work. Use no tools.")
        wait_for("the answer to stream", 90, lambda: self.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") is None and e["chunk"].get("kind") == "text", t2))
        self.prompt("Reply with the single word second and nothing else.")
        wait_for("the turn, the queued prompt's and the offer's", 180, lambda: len(self.main_turn_ends(t2)) >= 3)
        quiet = self.quiet(t2, 3)

        def queued_offer_answered():
            rows = self.rows()[before:]
            offers = [i for i, r in enumerate(rows) if is_offer(r)]
            return rows if offers and any(i > offers[0] for i in answers(rows)) else None
        rows = wait_for("the offer's answer in the transcript", 20, queued_offer_answered)
        offers = [i for i, r in enumerate(rows) if is_offer(r)]
        said = answers(rows)
        second = [i for i in said if text_of(rows[i]).strip().lower().rstrip(".") == "second"]
        tides = [i for i in said if "tide" in text_of(rows[i]).lower()]
        last_before = [i for i in said if offers and i < offers[0]]
        figure = offered_figure(rows[offers[0]]) if offers else None
        self.check("the queued prompt is answered before the offer enters, and one offer follows both",
                   len(offers) == 1 and tides and second and tides[0] < second[0] < offers[0] and quiet,
                   "tides at %s, second at %s, offers at %s, main turn ends %d" % (tides[:1], second[:1], offers,
                                                                                    len(self.main_turn_ends(t2))))
        self.check("the offer carries the figures as it enters: the queued prompt's answer, not the earlier turn's",
                   figure is not None and last_before and figure == input_total(rows[last_before[-1]])
                   and tides and figure != input_total(rows[tides[-1]]),
                   "offered %s; queued answer's input %s; earlier turn's %s" % (
                       figure, last_before and input_total(rows[last_before[-1]]), tides and input_total(rows[tides[-1]])))
        notices = [text_of(r) or r.get("content") for r in rows if r.get("type") == "system"
                   and ("Prompt not sent" in str(r.get("content")) or "dropped by a hook" in str(r.get("content")))]
        self.check("no prompt was dropped on the way", not notices, "notices %r" % notices)

        # A turn the model takes the offer in: the compaction at the end of
        # the offer's turn, then the resume prompt, answered.
        t3 = time.time()
        self.prompt("This is a test of the compaction offer. Reply with the single word ok and call no tool now. When the "
                    "offer then comes after this turn, you must take it whatever the context size: call "
                    "mcp__doperpowers__compact with resume set to exactly: Say done.")
        wait_for("the turn's end, the offer's turn, the compaction, and the resume prompt's turn", 240,
                 lambda: len(self.main_turn_ends(t3)) >= 3)
        # The resume prompt enters under the plugin's name, in the engine's frame ("The doperpowers plugin sent a message: ...").
        def resumes(rows):
            # After the compaction, the prompt itself: not the person's prompt naming it, not the summary quoting it.
            boundary = [i for i, r in enumerate(rows) if is_compaction(r)]
            return [i for i, r in enumerate(rows) if boundary and i > boundary[-1] and r.get("type") == "user"
                    and not r.get("isCompactSummary") and "Say done." in text_of(r)]

        def resumed_and_answered():
            rows = self.rows()
            resumed = resumes(rows)
            return rows if resumed and any(i > resumed[0] for i in answers(rows)) else None
        rows = wait_for("the resume prompt and its answer in the transcript", 30, resumed_and_answered)
        offers = [i for i, r in enumerate(rows) if is_offer(r)]
        taken = [i for i, r in enumerate(rows) if COMPACT in tool_uses(r)]
        compactions = [i for i, r in enumerate(rows) if is_compaction(r)]
        resumed = resumes(rows)
        answered = [i for i in answers(rows) if i > (resumed[0] if resumed else len(rows)) and "done" in text_of(rows[i]).lower()]
        asked = [i for i, r in enumerate(rows) if r.get("type") == "user" and "test of the compaction offer" in text_of(r)]
        offered = [i for i in offers if asked and i > asked[0]]
        self.check("an offer the model takes is a compact call in the offer's turn",
                   offered and taken and offered[0] < taken[0],
                   "prompt at %s, offers after it at %s, compact calls at %s" % (asked[:1], offered, taken))
        self.check("the offer's turn end compacts, and the resume prompt enters and is answered",
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
