#!/usr/bin/env python3
"""The ask's notifications, live, in a terminal session.

The settings' PreToolUse, PermissionRequest and Notification hooks each log
their payload, as a hook that notifies the person (the owner's notify.sh)
reads it. The model asks async, then blocking:

- each ask is announced once as it is asked, a `plugin_notification` whose
  message is its first question;
- the dialog the blocking ask raises reaches the PreToolUse and
  PermissionRequest hooks marked `metadata.source` sminos-ask, so such a
  hook can pass over it;
- while that dialog stands, past the engine's delay, the engine's
  `permission_prompt` reminder does not reach the Notification hooks.

`--from REF` stages the plugin's hooks/mods/ from a git ref (`--from main`
runs the code before the change, where the async ask is announced by no
hook and the reminder reaches them). An async ask's `[ answer ]` press opens
the same dialog through the same path (openDialog, the widening hook), which
the unit tests hold; it is not pressed here.

It spends model calls (haiku, two short prompts), so no suite runs it: run
it by hand with the model gateway's keys in the environment. Isolation is
live-bridge-check.py's (whose class it extends).

    sminos/tests/mods/live-ask-notify-check.py [--keep] [--from REF]
"""

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LB = _load("live_bridge_check", "live-bridge-check.py")
wait_for = LB.wait_for

ASYNC = ("Ask me with your question tool (mcp__sminos__AskUserQuestion), async true, which fruit I prefer, "
         "header Fruit, options Apple and Pear. Then reply with the single word done.")
BLOCKING = ("Ask me with your question tool (mcp__sminos__AskUserQuestion), async false, which color I prefer, "
            "header Color, options Red and Blue. Then reply with the single word done.")
DIALOG = lambda pane: "Enter to select" in pane and "Blue" in pane  # noqa: E731
REMINDER_WAIT = 20  # s the dialog stays up: past the engine's delay before its reminder


class Check(LB.Live):
    def __init__(self, keep, ref):
        super().__init__(keep)
        self.ref = ref
        self.log = os.path.join(self.root, "hooks.jsonl")

    def setup(self):
        os.environ.setdefault("CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "")
        super().setup()
        if self.ref is not None:
            mods = os.path.join(self.plugin, "hooks", "mods")
            with tempfile.TemporaryDirectory() as tmp:
                top = subprocess.run(["git", "-C", HERE, "rev-parse", "--show-toplevel"],
                                     check=True, capture_output=True, text=True).stdout.strip()
                archive = subprocess.run(["git", "-C", top, "archive", self.ref, "--", "sminos/hooks/mods"],
                                         check=True, capture_output=True).stdout
                subprocess.run(["tar", "-x", "-C", tmp], input=archive, check=True)
                shutil.rmtree(mods)
                shutil.copytree(os.path.join(tmp, "sminos", "hooks", "mods"), mods)
        command = lambda event: "/usr/bin/jq -c --arg ev %s '{ev: $ev, at: now, p: .}' >> %s" % (  # noqa: E731
            event, shlex.quote(self.log))
        hook = lambda event, matcher: [{"matcher": matcher, "hooks": [{"type": "command", "command": command(event)}]}]  # noqa: E731
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"hooks": {
                "PreToolUse": hook("PreToolUse", "AskUserQuestion|mcp__sminos__AskUserQuestion"),
                "PermissionRequest": hook("PermissionRequest", "AskUserQuestion"),
                "Notification": hook("Notification", ""),
            }}, f)

    def logged(self, since=0.0):
        rows = []
        if os.path.exists(self.log):
            with open(self.log) as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row["at"] >= since:
                        rows.append(row)
        return rows

    def plugin_notes(self, since):
        return [r["p"].get("message") for r in self.logged(since)
                if r["ev"] == "Notification" and r["p"].get("notification_type") == "plugin_notification"]

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

        t0 = time.time()
        self.prompt(ASYNC)
        self.wait_turn_end(t0)
        time.sleep(2)
        notes = self.plugin_notes(t0)
        self.check("an async ask is announced once as it opens, its first question",
                   len(notes) == 1 and "fruit" in (notes[0] or "").lower(), "plugin notifications %s" % notes)

        t1 = time.time()
        self.prompt(BLOCKING)
        wait_for("the blocking ask's dialog", 90, lambda: DIALOG(self.pane()))
        shown = time.time()
        notes = self.plugin_notes(t1)
        self.check("a blocking ask is announced once as it is asked, its first question",
                   len(notes) == 1 and "color" in (notes[0] or "").lower(), "plugin notifications %s" % notes)
        time.sleep(REMINDER_WAIT)
        rows = self.logged(t1)
        raised = [r for r in rows if r["ev"] in ("PreToolUse", "PermissionRequest") and r["p"].get("tool_name") == "AskUserQuestion"]
        sources = [(r["ev"], (r["p"].get("tool_input") or {}).get("metadata")) for r in raised]
        self.check("the dialog the ask raised reaches the PreToolUse and PermissionRequest hooks marked as the ask's",
                   raised and all(m == {"source": "sminos-ask"} for _, m in sources), "%s" % sources)
        reminders = [r["p"].get("message") for r in rows if r["ev"] == "Notification"
                     and r["p"].get("notification_type") == "permission_prompt"]
        self.check("the engine's reminder for the ask's dialog does not reach the Notification hooks",
                   not reminders, "%d s up; permission_prompt notifications %s" % (round(time.time() - shown), reminders))
        self.keys("Enter")
        self.wait_turn_end(t1)
        every = [(r["ev"], r["p"].get("notification_type") or r["p"].get("tool_name")) for r in self.logged(t0)]
        print("  every hook heard: %s" % every, flush=True)


def main():
    args = sys.argv[1:]
    ref = args[args.index("--from") + 1] if "--from" in args else None
    live = Check("--keep" in args, ref)
    print("live ask notify check (%s%s):" % (live.root, ", mods from %s" % ref if ref else ""), flush=True)
    try:
        live.run()
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
