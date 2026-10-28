#!/usr/bin/env python3
"""Live check that a final message ends the turn with no request after it.

A live interactive session under the `doperpowers:to-human` output style runs
two turns, each told to send one message through `mcp__to-human__message`
and do nothing else:
- turn one sends it without `final`, as a baseline: the engine asks the model
  again after the tool's result, so the turn makes two requests;
- turn two sends it with `final: true`: the plugin answers the step after the
  result itself, so the turn makes one request.

A probe plugin, loaded outermost through `prependPlugins`, records each step
it sees (whether the engine's bottom ran, so whether a request was made, and
the step's stop and usage) and each turn's `turn.complete` (reason, usage).
It records too what the model reads for each of the engine's style reminders.
It prints PASS or FAIL for each item:
1. turn one made two requests and ended `answer`;
2. turn two made one request, its next step answered by to-human with no
   request, and ended `answer`;
3. the transcript's rows for turn two: the call, its result `sent`, and the
   made-up response as the turn's last assistant row, with no request id and
   the engine's `answeredWithoutRequest` flag, which the view reads on a resume;
4. the terminal draws the message as a message row and nothing after it:
   no text of the made-up response, and no `› working record` for it;
5. sminos exports the final message to the project's log once, word for word;
6. the engine's style reminder, which every request of the main loop carries,
   reads the rule for a final message after the engine's words.

It spends model calls (about 4, haiku unless --model says otherwise), so no
suite runs it: run it by hand with the model gateway's keys in the
environment. It is built on live-message-check.py's isolated session (a
temporary HOME, SMINOS_HOME and project, copies of the worktree's plugins, a
tmux server of its own, the keys in a 0600 env file removed at the end).

    to-human/tests/mods/live-final-check.py [--keep] [--model haiku]
"""

import argparse
import importlib.util
import json
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_message_check", os.path.join(HERE, "live-message-check.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

MESSAGE_TOOL = base.MESSAGE_TOOL
FINAL_ANSWER = "Message sent to the human."
STYLE_FINAL = "When a message is the last thing you do in a turn, send it alone with `final: true`."
TEXT_ONE = "Baseline bravo: no final flag."
TEXT_TWO = "Closing charlie: the work is done."
PROMPT_ONE = ("This is a test of your tools. Call the tool %s once, with its text exactly `%s` and no other field. "
              "After its result, reply with the single word ok." % (MESSAGE_TOOL, TEXT_ONE))
PROMPT_TWO = ("This is a test of your tools. Call the tool %s once, with its text exactly `%s` and final set to true. "
              "Call nothing else and write nothing else." % (MESSAGE_TOOL, TEXT_TWO))

# The probe: every step it sees and every turn's end, as JSON lines.
PROBE = r"""import type { On } from 'claude-code'

const OUT = %(out)s
const lines: string[] = []

export function register(on: On) {
  on('turn.step', { turnId: /^/ }, async function* ($, e, next) {
    const result = yield* next(e)
    lines.push(JSON.stringify({
      ev: 'step', turnId: e.turnId, index: e.index, agentId: e.agentId ?? null,
      chain: next.trace.map((t) => t.plugin), answer: result?.answer, stopReason: result?.stopReason,
      usage: result?.usage ?? null, toolUses: result?.toolUses.map((u) => u.name),
    }))
    await $.fs.write(OUT, lines.join('\n') + '\n')
    return result
  })
  on('session.append', { door: /^/ }, async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined) {
      lines.push(JSON.stringify({ ev: 'row', door: e.door, name: e.message.name ?? null, role: e.message.role ?? null,
        blocks: e.message.content.map((b) => b.type) }))
      await $.fs.write(OUT, lines.join('\n') + '\n')
    }
    return result
  })
  on('prompt.attachment', { type: 'output_style' }, async ($, e, next) => {
    const result = await next(e)
    lines.push(JSON.stringify({ ev: 'style', agentId: e.agentId ?? null, text: result.text }))
    await $.fs.write(OUT, lines.join('\n') + '\n')
    return result
  })
  on('turn.complete', async ($, e, next) => {
    lines.push(JSON.stringify({ ev: 'complete', turnId: e.turnId, agentId: e.agentId ?? null, reason: e.reason, usage: e.usage ?? null }))
    await $.fs.write(OUT, lines.join('\n') + '\n')
    return next(e)
  })
}
"""


class Final(base.Live):
    def setup(self):
        super().setup()
        self.probe_out = os.path.join(self.root, "probe.jsonl")
        probe = os.path.join(self.root, "probe")
        os.makedirs(os.path.join(probe, ".claude-plugin"))
        os.makedirs(os.path.join(probe, "hooks", "mods"))
        with open(os.path.join(probe, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "probe", "version": "0.0.1", "description": "records steps and turn ends"}, f)
        with open(os.path.join(probe, "hooks", "hooks.json"), "w") as f:
            json.dump({"description": "probe", "modules": ["./mods/probe.tsx"]}, f)
        with open(os.path.join(probe, "hooks", "mods", "probe.tsx"), "w") as f:
            f.write(PROBE % {"out": json.dumps(self.probe_out)})
        self.dirs.insert(0, probe)
        path = os.path.join(self.cfg, "settings.json")
        with open(path) as f:
            settings = json.load(f)
        settings["prependPlugins"] = ["probe@inline", "to-human@inline", "sminos@inline"]
        with open(path, "w") as f:
            json.dump(settings, f)

    def probe(self):
        if not os.path.exists(self.probe_out):
            return []
        return [json.loads(line) for line in open(self.probe_out) if line.strip()]

    def ended(self, n):
        """The n-th main-loop turn.complete, once there is one."""
        done = [r for r in self.probe() if r["ev"] == "complete" and r["agentId"] is None]
        return done[n] if len(done) > n else None

    def run(self):
        self.setup()
        self.start()
        base.wait_for("the prompt", 60, lambda: "❯" in self.pane())

        self.send(PROMPT_ONE)
        one = base.wait_for("turn one's end", 180, lambda: self.ended(0), during=self.watch_prompts)
        time.sleep(2)
        self.send(PROMPT_TWO)
        two = base.wait_for("turn two's end", 180, lambda: self.ended(1), during=self.watch_prompts)
        time.sleep(4)  # the Stop hook's export has run; let the view settle
        frame = self.pane()
        with open(os.path.join(self.root, "frame.txt"), "w") as f:
            f.write(frame)
        rows = self.rows()
        events = self.log_events()
        steps = [r for r in self.probe() if r["ev"] == "step" and r["agentId"] is None]
        debug = open(self.debug, errors="replace").read() if os.path.exists(self.debug) else ""
        self.stop()

        def of(turn):
            return [s for s in steps if s["turnId"] == turn["turnId"]]

        def requests(turn):
            return [s for s in of(turn) if "engine" in s["chain"]]

        print("probe chain on a request: %s" % (requests(one)[0]["chain"] if requests(one) else "none"))
        for name, turn in (("one", one), ("two", two)):
            for s in of(turn):
                print("  turn %s step %d: chain %s, stop %s, usage %s, answer %r, calls %s" % (
                    name, s["index"], s["chain"], s["stopReason"], "yes" if s["usage"] else "none",
                    (s["answer"] or "")[:60], s["toolUses"]))
            print("  turn %s complete: reason %s, usage %s" % (name, turn["reason"], turn["usage"]))
        records = self.probe()
        start = next((i for i, r in enumerate(records) if r["ev"] == "complete" and r["turnId"] == one["turnId"]), 0)
        print("  turn two as the probe saw it, in order:")
        for r in records[start + 1:]:
            if r["ev"] == "row":
                print("    row  %-12s %-24s role %-9s blocks %s" % (r["door"], r["name"], r["role"], r["blocks"]))
            elif r["agentId"] is None:
                print("    %s %s" % (r["ev"], {k: r.get(k) for k in ("index", "chain", "stopReason", "reason") if k in r}))

        # 1. The baseline: two requests.
        self.check("1 a message without final: two requests, the turn ends answer",
                   len(requests(one)) == 2 and one["reason"] == "answer",
                   "%d request(s), reason %s" % (len(requests(one)), one["reason"]))

        # 2. The final message: one request, the step after it answered by to-human alone.
        madeup = [s for s in of(two) if "engine" not in s["chain"]]
        alone = len(madeup) == 1 and madeup[0]["chain"][-1] == "to-human" and madeup[0]["answer"] == FINAL_ANSWER \
            and madeup[0]["stopReason"] == "end_turn" and madeup[0]["usage"] is None
        self.check("2 a final message: one request, the next step answered with none, the turn ends answer",
                   len(requests(two)) == 1 and alone and two["reason"] == "answer",
                   "%d request(s); the step after: %s; reason %s; turn usage %s" % (
                       len(requests(two)), madeup and {k: madeup[0][k] for k in ("chain", "stopReason", "answer")},
                       two["reason"], two["usage"]))

        # 3. The transcript's rows for turn two.
        use = next((b for _, b in self.blocks(rows, "tool_use")
                    if b.get("name") == MESSAGE_TOOL and b.get("input", {}).get("text") == TEXT_TWO), None)
        at = next((i for i, r in enumerate(rows) for b in (r.get("message", {}).get("content") or [])
                   if isinstance(b, dict) and use and b.get("id") == use["id"]), None)
        tail = rows[at:] if at is not None else []
        summary = [(r.get("type"), r.get("subtype"), r.get("requestId"), r.get("message", {}).get("model"),
                    [(b.get("type"), (b.get("text") or b.get("name") or str(b.get("content")))[:40])
                     for b in (r.get("message", {}).get("content") or []) if isinstance(b, dict)]
                    if isinstance(r.get("message", {}).get("content"), list) else r.get("message", {}).get("content"))
                   for r in tail]
        with open(os.path.join(self.root, "rows.json"), "w") as f:
            json.dump(tail, f, indent=1)
        result = use and self.result_of(rows, use["id"])
        assistants = [r for r in tail if r.get("type") == "assistant"]
        last = assistants[-1] if assistants else {}
        texts = [b.get("text") for b in last.get("message", {}).get("content") or [] if isinstance(b, dict)]
        self.check("3 the rows: the call (final), its result sent, then the made-up response, no request id, flagged",
                   use is not None and use.get("input", {}).get("final") is True and result is not None
                   and self.result_text(result).strip() == "sent" and texts == [FINAL_ANSWER]
                   and not last.get("requestId") and last.get("answeredWithoutRequest") is True,
                   "\n    " + "\n    ".join(repr(s) for s in summary))

        # 4. The terminal: the message, and nothing of the made-up response, not even a fold.
        below = frame[frame.find("write nothing else."):]
        drawn = TEXT_TWO in below and below.rfind(base.LABEL, 0, below.find(TEXT_TWO)) >= 0
        after = below[below.find(TEXT_TWO):] if drawn else below
        shown = FINAL_ANSWER in below
        folded = "working record" in after
        self.check("4 the terminal draws the message as a message row, and nothing after it",
                   drawn and not shown and not folded,
                   "message row %s, made-up text drawn %s, a working record after it %s; frame below the prompt:\n%s" % (
                       drawn, shown, folded, "\n".join("    | " + line for line in below.splitlines()[:16])))

        # 5. The export.
        exported = [e for e in events if use and e.get("src") == use["id"]]
        self.check("5 sminos exports the final message once, word for word",
                   len(exported) == 1 and exported[0].get("kind") == "message" and exported[0].get("text") == TEXT_TWO,
                   "%d event(s): %s" % (len(exported), [{k: e.get(k) for k in ("kind", "src", "text")} for e in exported]))

        # 6. The engine's style reminder, as the model reads it.
        styles = [r["text"] for r in self.probe() if r["ev"] == "style" and r["agentId"] is None]
        self.check("6 the engine's style reminder reads the rule for a final message after its own words",
                   len(styles) >= 2 and all(t and t.startswith(base.STYLE) and t.endswith(" " + STYLE_FINAL) for t in styles),
                   "%d reminder(s): %s" % (len(styles), sorted(set(styles))))

        print("debug log, to-human's final lines: %s" % [line[-110:] for line in debug.splitlines()
                                                      if "final message" in line])
        return all(ok for _, ok in self.results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--model", default="haiku")
    args = ap.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    live = Final(args.keep, args.model, None)
    try:
        ok = live.run()
    finally:
        live.cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
