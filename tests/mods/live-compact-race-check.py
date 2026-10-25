#!/usr/bin/env python3
"""Live check of the compact mod against a prompt that arrives while a compaction is due.

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session with the plugin:
- a prompt the person types over the turn that called compact, after the
  call, waits for the compaction (the mod holds it at prompt.submit): the
  conversation compacts at the end of that turn, then the prompt is
  answered, then the resume prompt the model wrote enters; let through, it
  started its turn ahead of the compaction about half the time, so the
  check runs it ROUNDS times;
- a message that reaches the session through the bridge (the human's words
  from the desk) while that turn runs wakes it at the turn's end, and the
  engine starts that wake before the turn.complete hooks run, so the
  compaction finds a turn begun and does not run (2.1.310); the prompt that
  follows says so, in the resume prompt's place, and the model's next
  compact call compacts, its resume prompt entering after.

It spends model calls (haiku, short prompts, four to six compactions), so
no suite runs it: run it by hand with the model gateway's keys in the
environment. Isolation is sminos/tests/mods/live-bridge-check.py's, as in
live-compact-offer-check.py, whose transcript readers it uses; the offer is
kept out of the way with a floor no session this small reaches.

    tests/mods/live-compact-race-check.py [--keep]
"""

import importlib.util
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OC = load("live_compact_offer_check", os.path.join(HERE, "live-compact-offer-check.py"))
LB = OC.LB
wait_for = LB.wait_for
COMPACT = OC.COMPACT
text_of, answers, is_compaction = OC.text_of, OC.answers, OC.is_compaction

def is_ours(row):
    """A prompt this plugin submitted, as the transcript keeps it (not the summary quoting one)."""
    origin = row.get("origin") or {}
    return (row.get("type") == "user" and not row.get("isCompactSummary") and origin.get("kind") == "plugin"
            and origin.get("name") == "doperpowers")


ROUNDS = 3

ASK = ("This is a test of the compact tool. Call mcp__doperpowers__compact now, with resume set to exactly: "
       "Say done. When it returns, %s")


class Race(OC.Offer):
    def setup(self):
        LB.Live.setup(self)
        self.doperpowers = os.path.join(self.root, "doperpowers")
        LB.stage(REPO, self.doperpowers, OC.DOPERPOWERS_PARTS)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": [COMPACT]}}, f)
        with open(self.envfile, "a") as f:
            f.write("export DOPERPOWERS_COMPACT_OFFER_FLOOR=100000000\n")

    def compact_result(self, since):
        return self.seen(lambda e: e.get("type") == "tool" and e.get("phase") == "result"
                         and e.get("tool") == COMPACT and e.get("agentId") is None, since)

    def after(self, start):
        """The transcript's rows from index `start` on."""
        return self.rows()[start:]

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
        self.prompt("Reply with the single word ready and nothing else.")
        wait_for("the first turn's end", 120, lambda: self.main_turn_ends(0))

        # Typed over the turn, after the compact call: it waits for the compaction.
        for n in range(1, ROUNDS + 1):
            start = len(self.rows())
            t1 = time.time()
            self.prompt(ASK % "write a paragraph of about 150 words on how ocean tides work as your final reply, "
                               "and call no other tool.")
            wait_for("the compact call's result", 120, lambda: self.compact_result(t1))
            self.prompt("Reply with the single word queued and nothing else.")
            wait_for("the turn's end, the queued prompt's and the resume prompt's", 300,
                     lambda: len(self.main_turn_ends(t1)) >= 3)
            time.sleep(3)
            rows = self.after(start)
            boundary = [i for i, r in enumerate(rows) if is_compaction(r)]
            queued = [i for i, r in enumerate(rows) if r.get("type") == "user" and "single word queued" in text_of(r)]
            queued_said = [i for i in answers(rows) if text_of(rows[i]).strip().lower().rstrip(".") == "queued"]
            resumed = [i for i, r in enumerate(rows) if is_ours(r) and "Say done." in text_of(r)]
            told = [i for i, r in enumerate(rows) if is_ours(r) and "did not run" in text_of(r)]
            self.check("round %d: a prompt typed over the turn that asked waits: the turn's end compacts, then it is "
                       "answered, then the resume prompt enters and is answered" % n,
                       boundary and queued and queued_said and resumed and not told
                       and boundary[0] < queued[-1] < queued_said[0] < resumed[0] and answers(rows)[-1] > resumed[0],
                       "compaction rows at %s, queued prompt at %s, answered at %s, resume at %s, told %s" % (
                           boundary, queued, queued_said[:1], resumed[:1], told))

        # The human's words through the bridge while the turn runs: the wake
        # at the turn's end starts before the compaction can.
        start = len(self.rows())
        t2 = time.time()
        self.prompt(ASK % "write a paragraph of about 150 words on how rainbows form as your final reply, and "
                           "call no other tool. If you are later told the compaction did not run, call "
                           "mcp__doperpowers__compact again the same way.")
        wait_for("the compact call's result", 120, lambda: self.compact_result(t2))
        status, body = LB.request(self.endpoint(), "POST", "/command?wait=8000",
                              {"op": "deliver", "key": {"writer": "live/human", "seq": 1},
                               "text": "Reply with the single word delivered and nothing else."}, timeout=15)
        print("    (deliver: %s %s)" % (status, (body or {}).get("result")), flush=True)
        wait_for("the turns through the resume prompt's answer", 400, lambda: self.resumed_after(start))
        time.sleep(3)
        rows = self.after(start)
        boundary = [i for i, r in enumerate(rows) if is_compaction(r)]
        ours = [i for i, r in enumerate(rows) if is_ours(r)]
        told = [i for i in ours if "did not run" in text_of(rows[i])]
        calls = [i for i, r in enumerate(rows) if COMPACT in OC.tool_uses(r)]
        raced = bool(told) or not boundary or (ours and boundary[0] > ours[0])
        print("    (the wake %s the compaction)" % ("raced ahead of" if raced else "waited for"), flush=True)
        if raced:
            self.check("a compaction a waiting prompt's turn kept from running is told: the first prompt of the "
                       "plugin's after it says it did not run, and hands the resume prompt back",
                       told and ours[0] == told[0] and "Your resume prompt was: Say done." in text_of(rows[told[0]]),
                       "plugin prompts %r" % [text_of(rows[i])[:120] for i in ours])
            self.check("told, the model compacts again, and its resume prompt enters after the compaction",
                       told and len(calls) >= 2 and boundary and calls[-1] > told[0] and boundary[-1] > calls[-1]
                       and [i for i in ours if i > boundary[-1] and "Say done." in text_of(rows[i])],
                       "told at %s, compact calls at %s, compaction rows at %s" % (told[:1], calls, boundary))
        else:
            self.check("the wake waited: the compaction ran and the resume prompt followed it",
                       boundary and [i for i in ours if i > boundary[0] and "Say done." in text_of(rows[i])],
                       "compaction rows at %s, plugin prompts at %s" % (boundary, ours))

    def resumed_after(self, start):
        """The rows from `start`, once a resume prompt of the plugin's after a compaction has been answered."""
        rows = self.after(start)
        boundary = [i for i, r in enumerate(rows) if is_compaction(r)]
        resumed = [i for i, r in enumerate(rows) if boundary and i > boundary[-1] and is_ours(r) and "Say done." in text_of(r)]
        return rows if resumed and any(i > resumed[0] for i in answers(rows)) else None

def main():
    live = Race("--keep" in sys.argv[1:])
    print("live compact-race check (%s):" % live.root, flush=True)
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
