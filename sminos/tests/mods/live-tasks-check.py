#!/usr/bin/env python3
"""The Task Board's side in a session, live (the plan docs/doperpowers/plans/2026-11-27-task-board-b1.md, M4;
the composite's U1 and A7).

What only a running engine shows, each case in a terminal session of its own:

- `attributed` (U1). A subagent runs three assigning commands, one Bash call each: `task assign-human` under an
  allow rule for the verb (`Bash(task assign-human:*)`), `sminos task assign` under a rule that names arguments
  after the verb (`Bash(sminos task assign --class needed:*)`), and a `task assign-human` whose command also holds
  a secret's handle, with devcloud's secrets guard loaded and a stand-in value in the isolated home's store. A
  classic `PreToolUse` hook in the settings logs each call's input. Written down as found, none asserted
  beforehand: whether each call raised the permission dialog and what the dialog showed of the command, what the
  `PreToolUse` hook received, whether the handle was restored. Checked: each task names the subagent.
- `subagent` (A7). A subagent assigns a blocking task and keeps working (two 25 s waits); `sminos task done`, run as
  the human from no session, answers `told: now`, and the message reaches the subagent itself: it is in the
  subagent's transcript, with whatever the bridge's `tell` puts before it, and no `[tasks v1]` line for the task
  is in the main one. A second subagent assigns a task and ends; completed then, the notice reaches the main
  conversation in the subagent's-thread form, naming the subagent's id. Seen too: the line above the prompt and
  the notifications the settings' `Notification` hook receives (one a new blocking task).

Everything runs on this worktree's plugins loaded with --plugin-dir (sminos with its bin/, task, and devcloud for
`attributed`) under live-bridge-check.py's isolation, whose class it extends: a temporary HOME whose .claude is the
session's config dir, a temporary SMINOS_HOME, a tmux server of its own, the gateway keys in a 0600 env file removed
at the end. Nothing here depends on the installed plugins.

It spends model calls (haiku), so no suite runs it: run it by hand with the model gateway's keys in the environment.

    sminos/tests/mods/live-tasks-check.py [attributed] [subagent] [--keep]     # no case named: both
"""

import glob
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for
REPO = os.path.abspath(os.path.join(LB.PLUGIN_ROOT, ".."))
SECRET_KEY = "LIVE_TASKS_TOKEN"
DIALOG = re.compile(r"Do you want to proceed|Allow this|permission", re.I)


class Tasks(LB.Live):
    case = ""
    settings = {}

    def setup(self):
        super().setup()
        # sminos's bin/ as well, so `sminos` is on the session's PATH as an installed plugin puts it.
        LB.stage(LB.PLUGIN_ROOT, self.plugin, ("bin",))
        self.task_plugin = os.path.join(self.root, "task-plugin")
        LB.stage(os.path.join(REPO, "task"), self.task_plugin, (".claude-plugin", "bin", "cli"))
        self.pretool = os.path.join(self.root, "pretool.jsonl")
        self.notes_log = os.path.join(self.root, "notifications.jsonl")
        settings = dict(self.settings)
        settings["hooks"] = {
            "PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": "cat >> %s; echo >> %s" % (self.pretool, self.pretool)}]}],
            "Notification": [{"hooks": [
                {"type": "command", "command": "cat >> %s; echo >> %s" % (self.notes_log, self.notes_log)}]}],
        }
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump(settings, f)
        with open(self.envfile, "a") as f:
            f.write("export TASK_SMINOS=%s\n" % os.path.join(self.plugin, "bin", "sminos"))

    def plugin_dirs(self):
        return [self.plugin, self.task_plugin]

    # -- reading what happened

    def cli(self, *args):
        """sminos as the human runs it: from a terminal that is no session."""
        return subprocess.run([self.sminos(), *args], cwd=self.work, env=self.local_env(), capture_output=True,
                              text=True, timeout=120)

    def store(self):
        try:
            with open(os.path.join(self.smh, "tasks", "state.json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"tasks": {}}

    def task_titled(self, title):
        return next((t for t in self.store()["tasks"].values() if t.get("title") == title), None)

    def jsonl(self, pattern):
        out = []
        for p in glob.glob(pattern, recursive=True):
            with open(p) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        return out

    def main_rows(self):
        return self.jsonl(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl"))

    def agent_rows(self, agent):
        return self.jsonl(os.path.join(self.cfg, "projects", "**", "agent-%s*.jsonl" % agent))

    def carrying(self, rows, word):
        return [r for r in rows if word in json.dumps(r)]

    def logged(self, path):
        return [o for o in self.jsonl(path)]

    def start(self, prompt):
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
        time.sleep(2)
        t = time.time()
        self.prompt(prompt)
        return t

    def note(self, name, detail):
        print("  seen %s — %s" % (name, detail), flush=True)
        self.results.append(("seen: " + name, True, detail))


def subagent_prompt(steps, reply="DONE"):
    lines = " ".join("(%d) %s" % (i + 1, s) for i, s in enumerate(steps))
    return ("Use the Agent tool exactly once, subagent_type general-purpose, with this prompt, then reply with one "
            "word, OK: 'Run each of these Bash commands exactly as written, one Bash call each, in order: %s. Then "
            "reply %s.'" % (lines, reply))


class Attributed(Tasks):
    case = "attributed"
    settings = {"permissions": {"allow": ["Bash(task assign-human:*)", "Bash(sminos task assign --class needed:*)",
                                          "Bash(printf:*)", "Bash(cat:*)"]}}
    TITLES = ("U1 prefix rule", "U1 argument rule", "U1 with a handle")

    def setup(self):
        super().setup()
        self.devcloud = os.path.join(self.root, "devcloud-plugin")
        LB.stage(os.path.join(REPO, "devcloud"), self.devcloud, (".claude-plugin", "hooks", "skills", "types"))
        self.secret = "lt" + secrets.token_hex(12)
        store = os.path.join(self.home, ".config", "claude-secrets")
        os.makedirs(store, mode=0o700)
        with open(os.path.join(store, SECRET_KEY), "w") as f:
            f.write(self.secret)

    def plugin_dirs(self):
        return super().plugin_dirs() + [self.devcloud]

    def which(self, command):
        """The case a command shown in a dialog is, by its head (a wrapped line may cut its title)."""
        command = command.strip()
        return (self.TITLES[2] if command.startswith("printf") else self.TITLES[1] if command.startswith("sminos")
                else self.TITLES[0] if command.startswith("task") else "?")

    def run(self):
        out = os.path.join(self.work, "u1-handle.txt")
        t = self.start(subagent_prompt([
            'task assign-human --class optional --title "%s"' % self.TITLES[0],
            'sminos task assign --class needed --title "%s"' % self.TITLES[1],
            'printf %%s "[secret:%s]" > u1-handle.txt && task assign-human --class optional --title "%s"'
            % (SECRET_KEY, self.TITLES[2]),
        ]))
        dialogs = []
        deadline = time.time() + 300
        while time.time() < deadline and not all(self.task_titled(x) for x in self.TITLES):
            pane = self.pane()
            if DIALOG.search(pane) and ("assign" in pane or "printf" in pane):
                dialogs.append(pane)
                time.sleep(1)
                self.keys("Enter")      # the dialog's first choice: yes, once
                time.sleep(2)
            time.sleep(0.5)
        self.wait_turn_end(t, 240)
        for title in self.TITLES:
            task = self.task_titled(title)
            agent = ((task or {}).get("askers") or [{}])[0].get("agent")
            self.check("%s: the task names the subagent" % title,
                       agent is not None and LB_AGENT.fullmatch(agent.get("id") or ""), "asker agent %s" % agent)
        for pane in dialogs:
            # The dialog's own lines: the command as it will run, the flag in it (the prompt typed above is not).
            shown = [line.strip(" │") for line in pane.splitlines() if "--asker-agent" in line]
            self.note("a permission dialog for %s" % self.which(" ".join(shown)), " | ".join(shown)[:400])
        self.note("dialogs raised", "%d" % len(dialogs))
        for e in self.logged(self.pretool):
            command = (e.get("tool_input") or {}).get("command") or ""
            if "assign" in command:
                self.note("PreToolUse received", "agent_id %s; command %r" % (e.get("agent_id"), command[:300]))
        try:
            with open(out) as f:
                got = f.read()
        except OSError:
            got = None
        self.note("the handle in the same command", "file %s" % (
            "absent" if got is None else "holds the stored value (restored)" if got == self.secret
            else "holds %r (not restored)" % got[:60]))


LB_AGENT = re.compile(r"a[0-9a-f]{16}")


class Subagent(Tasks):
    case = "subagent"
    settings = {"permissions": {"allow": ["Bash"]}}
    WHILE = "A7 while it runs"
    AFTER = "A7 after it ended"

    def run(self):
        # A plain `sleep` is refused by the engine as a wait (it tells the agent to use Monitor): a Python one runs.
        nap = "python3 -c 'import time; time.sleep(25)'"
        self.start(subagent_prompt(['task assign-human --class blocking --title "%s"' % self.WHILE, nap, nap]))
        task = wait_for("the subagent's task", 180, lambda: self.task_titled(self.WHILE))
        agent = (task["askers"][0].get("agent") or {}).get("id") or ""
        self.check("the task names the subagent", LB_AGENT.fullmatch(agent), "asker %s" % task["askers"][0])
        time.sleep(3)
        band = [line.strip() for line in self.pane().splitlines() if "for the human" in line]
        self.note("the line above the prompt", band or "none drawn")
        r = self.cli("task", "done", task["id"], "--note", "a7 note")
        verdict = json.loads(r.stdout or "{}")
        self.check("done while it runs answers told now", verdict.get("told") == "now", r.stdout.strip())
        # A subagent runs in the background (the Agent tool answers at once): its own transcript is watched.
        form_a = "[tasks v1] The human marked %s done, a task you assigned." % task["id"]
        try:
            in_agent = wait_for("the message in the subagent's transcript", 120,
                                lambda: self.carrying(self.agent_rows(agent), form_a), every=1)
        except TimeoutError:
            in_agent = []
        wait_for("the subagent's end", 180, lambda: self.carrying(self.main_rows(), "<task-id>%s</task-id>" % agent),
                 every=1)
        time.sleep(3)
        o = json.loads(self.cli("task", "show", task["id"], "--json").stdout)["task"]["outcomes"][0]
        in_main = self.carrying(self.main_rows(), form_a)
        self.check("the message is in the subagent's transcript and no [tasks v1] line for it in the main one",
                   (o.get("send") or {}).get("how") == "tell" and in_agent and not in_main,
                   "send %s; in the subagent's %d row(s), in the main %d" % (o.get("send"), len(in_agent), len(in_main)))
        for row in in_agent:
            # As the engine kept it (a queued command) and as the model was sent it (the request's system text).
            body = row.get("message") or row.get("attachment") or {}
            self.note("what the subagent's transcript holds (%s)" % row.get("type"), json.dumps(body)[:420])
        time.sleep(3)

        self.prompt(subagent_prompt(['task assign-human --class blocking --title "%s"' % self.AFTER]))
        task = wait_for("the second subagent's task", 180, lambda: self.task_titled(self.AFTER))
        agent = (task["askers"][0].get("agent") or {}).get("id") or ""
        wait_for("the second subagent's end", 180,
                 lambda: self.carrying(self.main_rows(), "<task-id>%s</task-id>" % agent), every=1)
        time.sleep(5)
        t = time.time()
        r = self.cli("task", "done", task["id"])
        form_c = "[tasks v1] The human marked %s done, a task your subagent %s assigned." % (task["id"], agent)
        rows = wait_for("the notice in the main conversation", 120,
                        lambda: self.carrying(self.main_rows(), form_c), every=1)
        o = json.loads(self.cli("task", "show", task["id"], "--json").stdout)["task"]["outcomes"][0]
        self.check("done after it ended: the notice is in the main conversation, naming the subagent's id",
                   json.loads(r.stdout).get("told") == "now" and rows and (o.get("send") or {}).get("how") == "notice",
                   "send %s; rows %d" % (o.get("send"), len(rows)))
        try:
            self.wait_turn_end(t, 180)
        except TimeoutError:
            pass
        notes = [(e.get("notification_type"), e.get("message")) for e in self.logged(self.notes_log)]
        self.note("notifications the Notification hook received", notes)


def main():
    argv = sys.argv[1:]
    keep = "--keep" in argv
    named = [a for a in argv if not a.startswith("--")]
    cases = {"attributed": Attributed, "subagent": Subagent}
    unknown = [n for n in named if n not in cases]
    if unknown:
        sys.exit("live-tasks-check: no case %s (attributed, subagent)" % ", ".join(unknown))
    failed = 0
    for name in named or list(cases):
        live = cases[name](keep)
        print("live tasks check, %s (%s):" % (name, live.root), flush=True)
        try:
            live.run()
        except Exception as e:  # noqa: BLE001 — a check that cannot go on is a failed check
            live.check("the check ran to its end", False, "%s: %s" % (type(e).__name__, e))
            print("  pane at the failure:\n" + "\n".join("    " + l for l in live.pane().rstrip().splitlines()[-25:]))
        finally:
            live.cleanup()
        bad = [r for r in live.results if not r[1]]
        failed += len(bad)
        print("%s: %d of %d checks passed" % ("FAILED" if bad else "passed", len(live.results) - len(bad),
                                                len(live.results)), flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
