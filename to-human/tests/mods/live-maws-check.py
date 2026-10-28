#!/usr/bin/env python3
"""Live check of the message tool in a session launched as MAWS launches one.

MAWS runs every session headless: `claude -p`, stream-json both ways, its
permission requests over stdio (`--permission-prompt-tool stdio`), the flags
of MAWS's `ENGINE_FLAGS` (src/engine-host/launch.ts), with
`MAWS_NATIVE_TO_HUMAN` naming its contract version. From version 8 on MAWS
offers no message tool of its own (MAWS's Decision Log 92), and its sessions
send through this plugin's. This check launches one so, with
`MAWS_NATIVE_TO_HUMAN=8`, the `doperpowers:to-human` style and the `default`
permission mode, and one turn asks the model to send a message with
`final: true` and do nothing else. A probe plugin, outermost, records each
step (whether a request was made) and each prompt the engine submits.

It prints PASS or FAIL for each item:
1. the tool is registered: the stream's `system` init frame lists it;
2. its call raised no permission request: no `can_use_tool` control request
   on stdout (one that comes is answered allow, so the run goes on, and
   fails this item);
3. the turn made one request: the step after the final message was answered
   by to-human with none, and the turn ended in a `result` frame, success;
4. the transcript keeps the made-up response as the turn's last assistant
   row, with the engine's `answeredWithoutRequest` flag and no request id;
5. no notification was raised: a MAWS session's notification surface is MAWS.
It also prints, for MAWS's live normalizer, every stdout frame from the
call's to the `result` (its type, subtype, the content's blocks, and the
keys at its top level), whether the made-up response came out as an
`assistant` frame, and whether that frame carries `answeredWithoutRequest`;
and whether the engine submitted the turn's prompt through `prompt.submit`,
the event the reminder rides.

It spends model calls (one or two, haiku unless --model says otherwise), so
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
# MAWS's ENGINE_FLAGS, in its order (MAWS src/engine-host/launch.ts).
ENGINE_FLAGS = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--permission-prompt-tool", "stdio", "--include-partial-messages", "--forward-subagent-text",
                "--replay-user-messages", "--include-hook-events", "--setting-sources", "user,project,local"]
# What the probe adds: the prompts the engine submits.
PROBE_PROMPTS = r"""
  on('prompt.submit', { text: /^/ }, async ($, e, next) => {
    lines.push(JSON.stringify({ ev: 'prompt', text: e.text.slice(0, 60), context: e.context?.length ?? 0 }))
    await $.fs.write(OUT, lines.join('\n') + '\n')
    return next(e)
  })
}
"""


class Maws(final.Final):
    def setup(self):
        super().setup()
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
        env["MAWS_NATIVE_TO_HUMAN"] = "8"
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

    def run(self):
        self.setup()
        self.start()
        self.write({"type": "user", "message": {"role": "user", "content": PROMPT},
                    "parent_tool_use_id": None, "session_id": self.session})
        result = base.wait_for("the turn's result frame", 180,
                               lambda: next((f for f in self.frames if f.get("type") == "result"), None))
        time.sleep(2)
        rows = self.rows()
        steps = [r for r in self.probe() if r["ev"] == "step" and r["agentId"] is None]
        prompts = [r for r in self.probe() if r["ev"] == "prompt"]
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
        at = next((i for i, f in enumerate(self.frames) if f.get("type") == "assistant" and any(
            isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == MESSAGE_TOOL
            for b in (f.get("message") or {}).get("content") or [])), None)
        print("frames from the call's assistant frame to the result (stream_event frames counted, not listed):")
        streamed = 0
        for f in self.frames[at:] if at is not None else []:
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
        madeup = [f for f in self.frames if f.get("type") == "assistant" and any(
            isinstance(b, dict) and b.get("text") == FINAL_ANSWER for b in (f.get("message") or {}).get("content") or [])]
        print("the made-up response as an assistant frame: %s; answeredWithoutRequest on it: %s" % (
            bool(madeup), [f.get("answeredWithoutRequest") for f in madeup]))
        print("prompts the engine submitted through prompt.submit: %s" % prompts)
        return all(ok for _, ok in self.results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--model", default="haiku")
    args = ap.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    live = Maws(args.keep, args.model, None)
    try:
        ok = live.run()
    finally:
        live.cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
