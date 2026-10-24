#!/usr/bin/env python3
"""Live check of the message tool end to end: acceptance 1-5 of
docs/doperpowers/specs/2026-10-20-to-human-message-tool-design.md.

A live interactive session under the `doperpowers:to-human` output style (the
tool registers only under it) runs two turns:
- turn one runs `echo`, then in one response sends a message through
  `mcp__to-human__message` and runs `sleep`, then ends on a `<message>` span;
- turn two dispatches a general-purpose subagent told to call the tool.

It prints PASS or FAIL for each item:
1. the call sits in the same response as the command's, its result is
   `sent`, and no permission prompt appeared;
2. the report view draws it as a message row between the working-record
   runs, and draws no row for its result;
3. a `Notification` hook received a `plugin_notification` carrying its first
   line;
4. the project's log holds it once, word for word, as `kind: "message"` with
   `src` the tool-use id: while the `sleep` still runs (the bridge's live
   export), and again after each turn's Stop hook (no second copy);
5. the subagent's call is refused, and nothing is drawn, notified or exported
   for it.

It spends model calls (about 8 to 12, haiku unless --model says otherwise),
so no suite runs it: run it by hand with the model gateway's keys in the
environment. Everything it starts is isolated, as live-resume-check.py's is: a
temporary HOME whose .claude is the session's config dir, a temporary
SMINOS_HOME and a project of its own (`sminos project init` in a fresh
repository), copies of the worktree's to-human and sminos plugins and a
doperpowers plugin carrying only the worktree's output style, loaded with
--plugin-dir, a tmux server of its own; the gateway keys reach the session
through a 0600 env file in the temporary directory, removed at the end
whatever happens. With --keep the directory stays (minus the env file),
holding the frames, the notifications and the debug log.

    to-human/tests/mods/live-message-check.py [--keep] [--model haiku] [--permission-mode default]
"""

import argparse
import glob
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
GATEWAY_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY")
BASE_KEYS = ("PATH", "TERM", "LANG", "USER", "LOGNAME", "SHELL", "TMPDIR")
PLUGINS = {"to-human": (".claude-plugin", "hooks"), "sminos": (".claude-plugin", "hooks", "skills", "types")}
MESSAGE_TOOL = "mcp__to-human__message"
STYLE = "doperpowers:to-human"
LABEL = "● message"
TEXT = "Checkpoint alpha: the first step ran."
SUB = "subzebra"  # what the subagent is told to send, spelled out so no prompt carries it whole
REFUSAL = "message is for the main conversation"
PROMPT_ONE = ("This is a test of your tools; do exactly these steps. Step 1: run the Bash command `echo first-step`. "
              "Step 2: in one single response, call the tool %s with its text exactly `%s` and also call Bash with "
              "`sleep 12`, both in that same response. Step 3: when the sleep is done, reply with exactly "
              "<message>turn one done</message> and nothing else." % (MESSAGE_TOOL, TEXT))
PROMPT_TWO = ("Use the Agent tool once, subagent_type general-purpose, with this prompt: 'Call the tool %s once, with "
              "its text set to the letters s, u, b, z, e, b, r, a joined into one lowercase word. Then reply with "
              "exactly what the tool returned.' When the agent has finished, reply with exactly "
              "<message>turn two done</message> and nothing else." % MESSAGE_TOOL)
PERMISSION = re.compile(r"Do you want to (proceed|allow|make)")


def wait_for(what, seconds, fn, every=0.5, during=None):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if during:
            during()
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))


class Live:
    def __init__(self, keep, model, mode):
        self.keep, self.model, self.mode = keep, model, mode
        self.root = tempfile.mkdtemp(prefix="thmsg.", dir="/tmp")
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.home, ".claude")
        self.work = os.path.join(self.root, "work")
        self.smhome = os.path.join(self.root, "s")
        self.envfile = os.path.join(self.root, "env")
        self.notes = os.path.join(self.root, "notifications.jsonl")
        self.debug = os.path.join(self.root, "debug.log")
        self.tmux = ["tmux", "-L", "thmsg-%d" % os.getpid(), "-f", "/dev/null"]
        self.session = str(uuid.uuid4())
        self.sminos = os.path.join(self.root, "sminos", "skills", "sminos", "scripts", "sminos")
        self.dirs, self.results, self.prompts = [], [], []

    # -- the isolated config, the plugins, the project

    def setup(self):
        missing = [k for k in GATEWAY_KEYS if k not in os.environ]
        if missing:
            sys.exit("live-message-check: the gateway keys are not in the environment: %s" % ", ".join(missing))
        os.makedirs(self.cfg)
        os.makedirs(self.work)
        os.makedirs(self.smhome, mode=0o700)
        for name, parts in PLUGINS.items():
            dest = os.path.join(self.root, name)
            for part in parts:
                shutil.copytree(os.path.join(REPO, name, part), os.path.join(dest, part),
                                ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
            self.dirs.append(dest)
        # doperpowers carries the style; nothing else of it is needed, so nothing else of it loads.
        style = os.path.join(self.root, "doperpowers")
        os.makedirs(os.path.join(style, ".claude-plugin"))
        os.makedirs(os.path.join(style, "output-styles"))
        with open(os.path.join(REPO, ".claude-plugin", "plugin.json")) as f:
            version = json.load(f)["version"]
        with open(os.path.join(style, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "doperpowers", "version": version, "description": "the output style alone"}, f)
        shutil.copy(os.path.join(REPO, "output-styles", "to-human.md"), os.path.join(style, "output-styles"))
        self.dirs.append(style)
        trusted = {"hasTrustDialogAccepted": True}
        with open(os.path.join(self.cfg, ".claude.json"), "w") as f:
            json.dump({"hasCompletedOnboarding": True,
                       "projects": {self.work: trusted, os.path.realpath(self.work): trusted}}, f)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"outputStyle": STYLE,
                       "permissions": {"allow": ["Bash(echo:*)", "Bash(sleep:*)"]},
                       "hooks": {"Notification": [{"hooks": [{"type": "command", "command":
                                 "cat >> %s; echo >> %s" % (shlex.quote(self.notes), shlex.quote(self.notes))}]}]}}, f)
        env = {k: os.environ[k] for k in BASE_KEYS if k in os.environ}
        env.update(HOME=self.home, SMINOS_HOME=self.smhome, CLAUDE_CONFIG_DIR=self.cfg,
                   CLAUDE_CODE_ENABLE_FUNCTION_HOOKS="1")
        self.env = dict(env)
        env.update({k: os.environ[k] for k in GATEWAY_KEYS})
        fd = os.open(self.envfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            for k, v in sorted(env.items()):
                f.write("export %s=%s\n" % (k, shlex.quote(v)))
        subprocess.run(["git", "init", "-q", self.work], check=True, env=self.env)
        self.cli("project", "init", "--name", "livemsg")
        with open(os.path.join(self.work, ".smns")) as f:
            self.project = json.load(f)["project"]

    def cli(self, *args):
        return subprocess.run([self.sminos] + list(args), cwd=self.work, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def start(self):
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.dirs)
        mode = " --permission-mode %s" % shlex.quote(self.mode) if self.mode else ""
        inner = "set -e; . %s; cd %s; exec claude %s --model %s --session-id %s --debug-file %s%s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), dirs, shlex.quote(self.model), self.session,
            shlex.quote(self.debug), mode)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "t", "-x", "160", "-y", "60",
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)

    def stop(self):
        try:
            subprocess.run(self.tmux + ["kill-server"], capture_output=True)
        except FileNotFoundError:
            return
        time.sleep(1)

    def pane(self):
        return subprocess.run(self.tmux + ["capture-pane", "-p", "-t", "t", "-S", "-"],
                              capture_output=True, text=True).stdout

    def keys(self, *keys):
        subprocess.run(self.tmux + ["send-keys", "-t", "t"] + list(keys), check=True)

    def watch_prompts(self):
        """Every permission prompt the pane shows while a turn runs."""
        m = PERMISSION.search(self.pane())
        if m and m.group(0) not in self.prompts:
            self.prompts.append(m.group(0))

    def check(self, name, ok, detail):
        self.results.append((name, ok))
        print("%s  %s: %s" % ("PASS" if ok else "FAIL", name, detail))

    # -- what the session left behind

    def rows(self, path=None):
        found = [path] if path else glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl"))
        out = []
        for line in open(found[0]) if found and os.path.exists(found[0]) else []:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    @staticmethod
    def blocks(rows, kind):
        """(row, block) for every content block of this type."""
        for row in rows:
            content = row.get("message", {}).get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == kind:
                    yield row, block

    def result_of(self, rows, use_id):
        for _, block in self.blocks(rows, "tool_result"):
            if block.get("tool_use_id") == use_id:
                return block
        return None

    @staticmethod
    def result_text(block):
        content = block.get("content")
        if isinstance(content, list):
            return "".join(c.get("text", "") for c in content if isinstance(c, dict))
        return str(content)

    def turn_done(self, marker):
        """Whether the turn that wrote the marker has ended: an assistant row
        carries it, and the engine's Stop-hook summary row follows it."""
        rows = self.rows()
        said = [i for i, r in enumerate(rows) if r.get("type") == "assistant"
                and any(marker in b.get("text", "") for _, b in self.blocks([r], "text"))]
        return bool(said) and any(r.get("type") == "system" and r.get("subtype") == "stop_hook_summary"
                                  for r in rows[said[-1]:])

    def log_events(self):
        out = self.cli("chat", self.project, "--host", "--json", "-n", "500")
        return [json.loads(line) for line in out.splitlines() if line.strip()]

    def notifications(self):
        if not os.path.exists(self.notes):
            return []
        out = []
        for line in open(self.notes):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    # -- the run

    def send(self, prompt):
        self.keys("-l", prompt)
        time.sleep(0.5)
        self.keys("Enter")

    def run(self):
        self.setup()
        self.start()
        wait_for("the prompt", 60, lambda: "❯" in self.pane())

        # Turn one: echo, then the message and a sleep in one response, then a span.
        self.send(PROMPT_ONE)
        use = wait_for("the message call", 180, lambda: next(
            (b for _, b in self.blocks(self.rows(), "tool_use") if b.get("name") == MESSAGE_TOOL), None),
            during=self.watch_prompts)
        live_events = None

        def during_sleep():
            nonlocal live_events
            self.watch_prompts()
            rows = self.rows()
            sleeping = any(b.get("name") == "Bash" and "sleep" in str(b.get("input", {}).get("command"))
                           and self.result_of(rows, b["id"]) is None for _, b in self.blocks(rows, "tool_use"))
            if sleeping and live_events is None:
                found = [e for e in self.log_events() if e.get("src") == use["id"]]
                if found:
                    live_events = found
        wait_for("turn one's end", 180, lambda: self.turn_done("turn one done"), during=during_sleep)
        time.sleep(3)  # the Stop hook's export has run; let the view settle
        frame_one = self.pane()
        after_one = [e for e in self.log_events() if e.get("src") == use["id"]]

        # Turn two: a subagent calls the tool.
        self.send(PROMPT_TWO)
        wait_for("turn two's end", 300, lambda: self.turn_done("turn two done"), during=self.watch_prompts)
        time.sleep(3)
        frame_two = self.pane()
        with open(os.path.join(self.root, "frame.txt"), "w") as f:
            f.write(frame_two)
        rows = self.rows()
        events = self.log_events()
        notes = self.notifications()
        self.stop()

        # 1. The call, its response, its result, no prompt.
        call_row = next(r for r, b in self.blocks(rows, "tool_use") if b.get("id") == use["id"])
        same = [b.get("name") for r, b in self.blocks(rows, "tool_use")
                if r.get("message", {}).get("id") == call_row.get("message", {}).get("id")]
        result = self.result_of(rows, use["id"])
        sent = result is not None and not result.get("is_error") and self.result_text(result).strip() == "sent"
        self.check("1 the call beside the command, sent, no prompt", "Bash" in same and sent and not self.prompts,
                   "response's calls %s; result %r; prompts %s" % (same, result and self.result_text(result),
                                                                   self.prompts or "none"))

        # 2. The report: a message row between working-record runs, no row for the result.
        # Read below the prompt, which names the tool and carries the text.
        frame_one = frame_one[frame_one.find("and nothing else."):]
        at = frame_one.find(TEXT)
        label = frame_one.rfind(LABEL, 0, at) if at >= 0 else -1
        before = frame_one.rfind("› working record", 0, label) if label >= 0 else -1
        after = frame_one.find("› working record", at) if at >= 0 else -1
        raw = re.search(r"to-human.{0,4}message|⎿\s+sent\s*$", frame_one, re.M)
        self.check("2 drawn as a message row between the tool calls",
                   label >= 0 and frame_one[label:at].count("\n") <= 2 and 0 <= before < label and after > at and not raw,
                   "label at %d, text at %d, working record before %d and after %d, engine row %r" % (
                       label, at, before, after, raw and raw.group(0)))

        # 3. The notification.
        mine = [n for n in notes if n.get("notification_type") == "plugin_notification" and n.get("message") == TEXT]
        self.check("3 a plugin_notification with its first line", len(mine) == 1,
                   "%d of %d notifications carry it: %s" % (len(mine), len(notes),
                                                            [(n.get("notification_type"), n.get("message")) for n in notes]))

        # 4. The log: once, word for word, kind message, src the tool-use id; live, then after each Stop.
        final = [e for e in events if e.get("src") == use["id"]]
        shape = lambda es: len(es) == 1 and es[0].get("kind") == "message" and es[0].get("text") == TEXT
        self.check("4 the log holds it once (live export, then each Stop)",
                   live_events is not None and shape(live_events) and shape(after_one) and shape(final),
                   "during the sleep %s, after turn one %d, after turn two %d; event %s" % (
                       "1" if live_events else "none", len(after_one), len(final),
                       final and {k: final[0].get(k) for k in ("kind", "src", "text")}))

        # 5. The subagent's call: refused; not drawn, notified or exported.
        subs = glob.glob(os.path.join(self.cfg, "projects", "*", self.session, "subagents", "*.jsonl"))
        sub_rows = [r for path in subs for r in self.rows(path)]
        sub_uses = [b for _, b in self.blocks(sub_rows, "tool_use") if b.get("name") == MESSAGE_TOOL]
        refused = [self.result_of(sub_rows, b["id"]) for b in sub_uses]
        refused_ok = bool(sub_uses) and all(r is not None and REFUSAL in self.result_text(r) for r in refused)
        drawn = any(SUB in frame_two[m.end():m.end() + 200] for m in re.finditer(re.escape(LABEL), frame_two))
        notified = any(SUB in str(n.get("message")) for n in notes)
        exported = any(SUB in str(e.get("text")) for e in events)
        self.check("5 a subagent's call is refused, and goes nowhere",
                   refused_ok and not drawn and not notified and not exported,
                   "%d subagent call(s), results %s; drawn %s, notified %s, exported %s" % (
                       len(sub_uses), [r and self.result_text(r)[:80] for r in refused], drawn, notified, exported))
        return all(ok for _, ok in self.results)

    def cleanup(self):
        # The keys first: nothing after this may keep them on disk.
        if os.path.exists(self.envfile):
            os.unlink(self.envfile)
        self.stop()
        if self.keep:
            print("kept: %s" % self.root)
        else:
            shutil.rmtree(self.root, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--permission-mode", help="default: the engine's own (auto on 2.1.306)")
    args = ap.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    live = Live(args.keep, args.model, args.permission_mode)
    try:
        ok = live.run()
    finally:
        live.cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
