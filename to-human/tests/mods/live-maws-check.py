#!/usr/bin/env python3
"""Live check of the message tool in a session launched as MAWS launches one.

MAWS runs every session headless: `claude -p`, stream-json both ways, its
permission requests over stdio (`--permission-prompt-tool stdio`), the flags
of MAWS's `ENGINE_FLAGS` (src/engine-host/launch.ts), with
`MAWS_NATIVE_TO_HUMAN` naming its contract version. From version 8 on MAWS
offers no message tool of its own (MAWS's Decision Log 92), and its sessions
send through this plugin's; from 9 on MAWS reads this plugin's view on its
own surface (the plugin's maws-surface.json declares the number). This check
launches one so, with the `doperpowers:to-human` style and the `default`
permission mode, three times: with `MAWS_NATIVE_TO_HUMAN=8`, with 9, and with
9 and `TO_HUMAN_FOLD_SUMMARIES=off` in the settings env. In each, one turn
asks the model to send a message with `final: true` and do nothing else. A
probe plugin, outermost, records each step (whether a request was made) and
each prompt the engine submits.

It prints PASS or FAIL for each item, in each launch:
1. the tool is registered: the stream's `system` init frame lists it;
2. its call raised no permission request: no `can_use_tool` control request
   on stdout (one that comes is answered allow, so the run goes on, and
   fails this item);
3. the turn made one request: the step after the final message was answered
   by to-human with none, and the turn ended in a `result` frame, success;
4. the transcript keeps the made-up response as the turn's last assistant
   row, with the engine's `answeredWithoutRequest` flag and no request id;
5. no notification was raised: a MAWS session's notification surface is MAWS.
In the launches at 9 a second turn runs one command and then sends a final
message, which closes a run of working record, and the check prints:
6. at 9: the run's summary is asked for and kept within the call's limit:
   the session's folds file (`to-human/folds/<session id>.json` in the config
   dir) holds a run whose first row is the command's call, with a summary;
7. at 9: that file is kept as the contract a client reads, at `shape: 2`;
8. at 9 with TO_HUMAN_FOLD_SUMMARIES=off: the command ran (a run was due its
   summary) and none was asked for in that time: the probe saw no summary
   call, whatever such a call would have come to, and no folds file.
It also prints, for MAWS's live normalizer, every stdout frame from the
call's to the `result` (its type, subtype, the content's blocks, and the
keys at its top level), whether the made-up response came out as an
`assistant` frame, and whether that frame carries `answeredWithoutRequest`;
and whether the engine submitted the turn's prompt through `prompt.submit`,
the event the reminder rides.

It spends model calls (about eight across the three launches, the summary's
among them, haiku unless --model says otherwise), so
no suite runs it: run it by hand with the model gateway's keys in the
environment. It is built on live-message-check.py's isolated config and
live-final-check.py's probe (a temporary HOME, SMINOS_HOME and project,
copies of the worktree's plugins); the session runs as a child process here,
with no terminal.

    to-human/tests/mods/live-maws-check.py [--keep] [--model haiku]
"""

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_final_check", os.path.join(HERE, "live-final-check.py"))
final = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(final)
base = final.base

MESSAGE_TOOL = base.MESSAGE_TOOL
FINAL_ANSWER = final.FINAL_ANSWER
TEXT = "Closing delta: the MAWS-launched turn is done."
PROMPT = ("This is a test of your tools. Call the tool %s once, with its text exactly `%s` and final set to true. "
          "Call nothing else and write nothing else." % (MESSAGE_TOOL, TEXT))
STRETCH_TEXT = "The command ran."
STRETCH = ("This is a test of your tools. First run the Bash command `echo stretch-check` once. Then call the tool %s "
           "once, with its text exactly `%s` and final set to true. Call nothing else and write nothing else."
           % (MESSAGE_TOOL, STRETCH_TEXT))
# The summary call's own limit (folds.tsx, timeoutMs), and a margin for the file's write.
SUMMARY_WAIT = 45
# MAWS's ENGINE_FLAGS, in its order (MAWS src/engine-host/launch.ts).
ENGINE_FLAGS = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--permission-prompt-tool", "stdio", "--include-partial-messages", "--forward-subagent-text",
                "--replay-user-messages", "--include-hook-events", "--setting-sources", "user,project,local"]
# What the probe adds: the prompts the engine submits, and each model call a plugin makes (a fold's summary
# among them, known by its system prompt), seen from outside to-human whatever the call came to.
PROBE_PROMPTS = r"""
  on('prompt.submit', { text: /^/ }, async ($, e, next) => {
    lines.push(JSON.stringify({ ev: 'prompt', text: e.text.slice(0, 60), context: e.context?.length ?? 0 }))
    await $.fs.write(OUT, lines.join('\n') + '\n')
    return next(e)
  })
  on('model.complete', { model: /^/ }, async ($, e, next) => {
    lines.push(JSON.stringify({ ev: 'model', model: e.model, system: (e.system ?? '').slice(0, 40) }))
    await $.fs.write(OUT, lines.join('\n') + '\n')
    return next(e)
  })
}
"""
# The opening of the summary call's system prompt (folds.tsx, LABEL_SYSTEM).
LABEL_OPENING = "You label folded stretches"


class Maws(final.Final):
    def __init__(self, keep, model, advertise, summaries_off=False):
        super().__init__(keep, model, None)
        self.advertise, self.summaries_off = advertise, summaries_off
        self.label = "%s%s" % (advertise, ", summaries off" if summaries_off else "")

    def check(self, name, ok, detail):
        super().check("[%s] %s" % (self.label, name), ok, detail)

    def setup(self):
        super().setup()
        if self.summaries_off:
            # The settings env, where MAWS writes it into a launch it decides while its switch is off.
            path = os.path.join(self.cfg, "settings.json")
            with open(path) as f:
                settings = json.load(f)
            settings.setdefault("env", {})["TO_HUMAN_FOLD_SUMMARIES"] = "off"
            with open(path, "w") as f:
                json.dump(settings, f)
        probe = os.path.join(self.root, "probe", "hooks", "mods", "probe.tsx")
        with open(probe) as f:
            source = f.read().rstrip()
        assert source.endswith("}")
        with open(probe, "w") as f:
            f.write(source[:-1] + PROBE_PROMPTS)
        self.frames, self.requests = [], []

    def start(self):
        env = dict(self.env)
        env.update({k: os.environ[k] for k in base.GATEWAY_KEYS})
        env["MAWS_NATIVE_TO_HUMAN"] = self.advertise
        args = ["claude"] + ENGINE_FLAGS + ["--permission-mode", "default", "--model", self.model,
                                            "--session-id", self.session, "--debug-file", self.debug]
        for d in self.dirs:
            args += ["--plugin-dir", d]
        self.proc = subprocess.Popen(args, cwd=self.work, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(os.path.join(self.root, "stderr.txt"), "w"), text=True, bufsize=1)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            self.frames.append(frame)
            if frame.get("type") == "control_request" and (frame.get("request") or {}).get("subtype") == "can_use_tool":
                self.requests.append(frame)
                request = frame["request"]
                self.write({"type": "control_response", "response": {
                    "subtype": "success", "request_id": frame.get("request_id"),
                    "response": {"behavior": "allow", "updatedInput": request.get("input") or {}}}})

    def write(self, frame):
        self.proc.stdin.write(json.dumps(frame) + "\n")
        self.proc.stdin.flush()

    def stop(self):
        proc = getattr(self, "proc", None)
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.stdin.close()
            proc.wait(timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()

    def turn(self, prompt, n):
        """Sends one prompt and waits for the n-th result frame."""
        self.write({"type": "user", "message": {"role": "user", "content": prompt},
                    "parent_tool_use_id": None, "session_id": self.session})
        return base.wait_for("turn %d's result frame" % (n + 1), 180,
                             lambda: ([f for f in self.frames if f.get("type") == "result"][n:] or [None])[0])

    def folds(self):
        path = os.path.join(self.cfg, "to-human", "folds", self.session + ".json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except ValueError:
            return {"unreadable": True}

    def run(self):
        self.setup()
        self.start()
        result = self.turn(PROMPT, 0)
        time.sleep(2)
        rows = self.rows()
        steps = [r for r in self.probe() if r["ev"] == "step" and r["agentId"] is None]
        prompts = [r for r in self.probe() if r["ev"] == "prompt"]
        frames = list(self.frames)
        if self.advertise == "9":
            self.summary()
        self.stop()
        with open(os.path.join(self.root, "frames.jsonl"), "w") as f:
            f.writelines(json.dumps(fr) + "\n" for fr in self.frames)

        # 1. Registered.
        init = next((f for f in self.frames if f.get("type") == "system" and f.get("subtype") == "init"), {})
        self.check("1 the tool is registered: the init frame lists it", MESSAGE_TOOL in (init.get("tools") or []),
                   "init tools carrying 'message': %s" % [t for t in init.get("tools") or [] if "message" in t])

        # 2. No permission request.
        self.check("2 its call raised no permission request (no can_use_tool on stdout)", not self.requests,
                   "%d can_use_tool request(s): %s" % (len(self.requests), [r["request"].get("tool_name") for r in self.requests]))

        # 3. One request; the step after the final message answered with none.
        made = [s for s in steps if "engine" not in s["chain"]]
        asked = [s for s in steps if "engine" in s["chain"]]
        alone = len(made) == 1 and made[0]["chain"][-1] == "to-human" and made[0]["answer"] == FINAL_ANSWER
        self.check("3 one request, the step after the final message answered with none, the turn a success",
                   len(asked) == 1 and alone and result.get("subtype") == "success" and not result.get("is_error"),
                   "%d request(s); the step after: %s; result %s, num_turns %s" % (
                       len(asked), made and {k: made[0][k] for k in ("chain", "stopReason", "answer")},
                       result.get("subtype"), result.get("num_turns")))

        # 4. The transcript's last assistant row.
        last = next((r for r in reversed(rows) if r.get("type") == "assistant"), {})
        texts = [b.get("text") for b in last.get("message", {}).get("content") or [] if isinstance(b, dict)]
        self.check("4 the transcript's last assistant row is the made-up response, flagged, with no request id",
                   texts == [FINAL_ANSWER] and last.get("answeredWithoutRequest") is True and not last.get("requestId"),
                   "texts %s, answeredWithoutRequest %s, requestId %s" % (
                       texts, last.get("answeredWithoutRequest"), last.get("requestId")))

        # 5. No notification.
        notes = open(self.notes).read().strip() if os.path.exists(self.notes) else ""
        self.check("5 no notification was raised", notes == "", "notifications: %r" % notes[:200])

        # For MAWS's normalizer: the frames from the call's on.
        at = next((i for i, f in enumerate(frames) if f.get("type") == "assistant" and any(
            isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == MESSAGE_TOOL
            for b in (f.get("message") or {}).get("content") or [])), None)
        print("frames from the call's assistant frame to the result (stream_event frames counted, not listed):")
        streamed = 0
        for f in frames[at:] if at is not None else []:
            if f.get("type") == "stream_event":
                streamed += 1
                continue
            content = (f.get("message") or {}).get("content")
            blocks = [(b.get("type"), (b.get("text") or b.get("name") or "")[:40]) for b in content
                      if isinstance(b, dict)] if isinstance(content, list) else content
            print("  %-16s %-14s blocks %s\n    keys %s%s" % (
                f.get("type"), f.get("subtype") or "", blocks, sorted(f.keys()),
                "  message.id %s, stop_reason %s" % ((f.get("message") or {}).get("id"),
                                                      (f.get("message") or {}).get("stop_reason"))
                if f.get("type") == "assistant" else ""))
        print("  (%d stream_event frames in that span)" % streamed)
        madeup = [f for f in frames if f.get("type") == "assistant" and any(
            isinstance(b, dict) and b.get("text") == FINAL_ANSWER for b in (f.get("message") or {}).get("content") or [])]
        print("the made-up response as an assistant frame: %s; answeredWithoutRequest on it: %s" % (
            bool(madeup), [f.get("answeredWithoutRequest") for f in madeup]))
        print("prompts the engine submitted through prompt.submit: %s" % prompts)
        return all(ok for _, ok in self.results)

    def summary(self):
        """At 9: a run of working record closed by a message, and what the tracker keeps of it."""
        self.turn(STRETCH, 1)
        calls = [b.get("id") for _, b in self.blocks(self.rows(), "tool_use") if b.get("name") == "Bash"]
        asked = lambda: [r for r in self.probe() if r["ev"] == "model" and r["system"].startswith(LABEL_OPENING)]
        if self.summaries_off:
            time.sleep(SUMMARY_WAIT)
            kept = self.folds()
            self.check("8 with TO_HUMAN_FOLD_SUMMARIES=off no summary is asked for, though a run was due one",
                       bool(calls) and not asked() and kept is None,
                       "the command's call %s; summary calls seen %s; the folds file: %s" % (calls, asked(), kept))
            return
        try:
            kept = base.wait_for("the folds file's summary", SUMMARY_WAIT, lambda: (lambda k: k if k and any(
                isinstance(run, list) and run and run[0] in calls for run in k.get("runs") or []) else None)(self.folds()))
        except TimeoutError:
            kept = self.folds()
        runs = (kept or {}).get("runs") or []
        mine = [run for run in runs if isinstance(run, list) and len(run) == 3 and run[0] in calls]
        self.check("6 the run closed by the message reads a summary within the call's limit, kept in the folds file",
                   bool(calls) and bool(mine) and bool(mine[0][2].strip()),
                   "the command's call %s; summary calls seen %s; its runs in the file: %s" % (calls, asked(), mine))
        self.check("7 the folds file is kept at shape 2", (kept or {}).get("shape") == 2, "the file: %s" % kept)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--model", default="haiku")
    args = ap.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    ok = True
    for advertise, summaries_off in (("8", False), ("9", False), ("9", True)):
        live = Maws(args.keep, args.model, advertise, summaries_off)
        try:
            ok = live.run() and ok
        finally:
            live.cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
