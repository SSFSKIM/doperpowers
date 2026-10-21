#!/usr/bin/env python3
"""Live check of the name mod (charge names, M5) in real sessions.

What only a running engine shows, pinned so a release that changes it fails
loudly (docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md §3;
if an engine fact below fails, that section is revisited, not patched
around):
- an idle interactive session with a pending name whose `from` is its engine
  name is renamed by the mod's timer through the engine's `/rename`, with no
  prompt: the engine record shows the name with `nameSource: "user"`, the
  transcript a `custom-title` record and the engine's meta row naming it, and
  no model turn starts;
- a session its owner /renamed after the pending file's `from` was read
  keeps its own name;
- a `--bg` job, renamed the same way between turns;
- an SDK session as MAWS launches one (`claude -p`, stream-json in and out,
  `CLAUDE_CODE_ENTRYPOINT=sdk-ts`), renamed the same way between prompts.

Every pending file is written as `sminos derive` hands it (the spec's
Interfaces), and the real `sminos name-due` decides, so the CLI's checks run
too. It spends model calls (haiku, a few one-word turns), so no suite runs
it: run it by hand with the model gateway's keys in the environment.
Isolation is live-bridge-check.py's (whose class it extends): a temporary
HOME whose .claude is the sessions' config dir (so a `--bg` job's
supervisor is the check's own), a temporary SMINOS_HOME, a copy of the
worktree's sminos plugin loaded with --plugin-dir, a tmux server of its own,
the gateway keys in a 0600 env file removed at the end. Each session is
started without a name, so the engine generates one.

    python3 sminos/tests/mods/live-name-check.py [--keep]
"""

import datetime
import glob
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

CHARGE = "live-charge-name"
SECOND = "live-second-name"
OWNER = "owner-chosen-name"
BG = "live-bg-name"
SDK = "live-sdk-name"
# The mod's timer (POLL_MS, 15 s), `name-due`'s bound (10 s) and a margin.
APPLY_S = 45


def named_meta(rows, name):
    """The engine's meta row telling the model the session was named `name`."""
    needle = 'named this session "%s"' % name

    def text(row):
        content = (row.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        return "".join(b.get("text", "") for b in content or [] if isinstance(b, dict))

    return any(r.get("type") == "user" and r.get("isMeta") and needle in text(r) for r in rows)


class NameCheck(LB.Live):
    def __init__(self, keep):
        super().__init__(keep)
        self.pid = None
        self.short = None

    def bash(self, inner, **kw):
        """`inner` under the check's env file, nothing else of the caller's environment."""
        return ["env", "-i", "/bin/bash", "--noprofile", "--norc", "-c",
                "set -e; . %s; cd %s; %s" % (shlex.quote(self.envfile), shlex.quote(self.work), inner)]

    def dirs(self):
        return " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.plugin_dirs())

    def launch(self):
        """The interactive session, no name given (the engine generates one), in this check's tmux server."""
        cmd = " ".join(shlex.quote(a) for a in self.bash(
            "exec claude %s --model haiku --permission-mode default" % self.dirs()))
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "brl", "-x", "200", "-y", "50", cmd], check=True)

    def records(self):
        out = []
        for p in glob.glob(os.path.join(self.cfg, "sessions", "*.json")):
            try:
                with open(p) as f:
                    out.append(json.load(f))
            except (OSError, ValueError):
                pass
        return out

    def record(self, session=None):
        session = session or self.session
        return next((r for r in self.records() if r.get("sessionId") == session and LB._alive(r.get("pid"))), None)

    def rows(self, session=None):
        rows = []
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", (session or self.session) + ".jsonl")):
            with open(p) as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        return rows

    def answered(self, word):
        return any(r.get("type") == "assistant" and word in json.dumps(r.get("message")) for r in self.rows())

    def turn(self, word):
        self.prompt("Reply with exactly the word %s and nothing else." % word)
        wait_for("the reply %s" % word, 120, lambda: self.answered(word))
        time.sleep(1)

    def main_starts(self, since):
        """The main turns the bridge's stream saw start since `since`."""
        return self.seen(lambda e: e.get("type") == "turn" and e.get("phase") == "start"
                         and e.get("agentId") is None, since)

    def pend(self, session, name, before):
        """A pending name as `sminos derive` hands it."""
        d = os.path.join(self.smh, "names")
        os.makedirs(d, mode=0o700, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(os.path.join(d, session + ".json"), "w") as f:
            json.dump({"session": session, "name": name, "from": before,
                       "line": "Checks that the name mod applies a pending name.", "ts": ts}, f)

    def titles(self, session=None):
        return [r.get("customTitle") for r in self.rows(session) if r.get("type") == "custom-title"]

    def settled(self, session, what):
        """The record once the engine's title promotion had its turn: an `auto` name, or the generated one after a while."""
        try:
            return wait_for(what, 30, lambda: (lambda r: r if r and r.get("nameSource") == "auto" else None)(
                self.record(session)))
        except TimeoutError:
            return self.record(session) or {}

    def applied(self, session, name):
        try:
            return wait_for("the rename to %s" % name, APPLY_S, lambda: (lambda r: r if r and r.get("name") == name else None)(
                self.record(session)))
        except TimeoutError:
            return self.record(session) or {}

    # -- the checks

    def interactive(self):
        self.launch()
        rec = wait_for("the session's record", 90, lambda: next(iter(self.records()), None))
        self.session = rec["sessionId"]
        wait_for("the bridge's endpoint (the mods are loaded)", 90, self.status)
        # The bridge's stream reports every turn as it starts, so a turn the
        # rename started is seen even before it writes a row.
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        wait_for("the subscription", 10, lambda: self.subscriptions > 0)
        t_alpha = time.time()
        self.turn("ALPHA")
        alpha_starts = self.main_starts(t_alpha)
        rec = self.record() or {}
        generated = rec.get("name")

        t_pend = time.time()
        self.pend(self.session, CHARGE, generated)
        rec = self.applied(self.session, CHARGE)
        self.check("an idle session's pending name is applied by the timer, registered user",
                   rec.get("name") == CHARGE and rec.get("nameSource") == "user",
                   "record %s -> %s (%s)" % (generated, rec.get("name"), rec.get("nameSource")))
        time.sleep(10)
        rows = self.rows()
        self.check("and the transcript keeps a custom-title record and the engine's meta row naming it",
                   CHARGE in self.titles() and named_meta(rows, CHARGE),
                   "custom-title %s; meta row %s" % (self.titles(), "found" if named_meta(rows, CHARGE) else "MISSING"))
        starts = self.main_starts(t_pend)
        unbroken = len(self.connections) == 1 and self.connections[0]["closed"] is None
        self.check("engine fact: the rename starts no model turn",
                   len(alpha_starts) == 1 and not starts and unbroken,
                   "main turn.start on the bridge's stream: %d for the prompt, %d from the pending file to 10 s "
                   "after the rename; one unbroken subscription: %s" % (len(alpha_starts), len(starts), unbroken))

        # The owner renames after derive read CHARGE as the name to replace.
        self.prompt("/rename %s" % OWNER)
        wait_for("the owner's rename", 60, lambda: (self.record() or {}).get("name") == OWNER)
        self.pend(self.session, SECOND, CHARGE)
        time.sleep(APPLY_S)
        rec = self.record() or {}
        self.check("a session its owner renamed after the file's `from` was read keeps its own name",
                   rec.get("name") == OWNER and rec.get("nameSource") == "user" and SECOND not in self.titles(),
                   "record %s (%s); custom-title %s" % (rec.get("name"), rec.get("nameSource"), self.titles()))
        subprocess.run(self.tmux + ["kill-server"], capture_output=True)

    def bg(self):
        r = subprocess.run(self.bash("exec claude --bg %s --model haiku --permission-mode default %s" % (
            self.dirs(), shlex.quote("Reply with exactly the word ALPHA and nothing else."))),
            capture_output=True, text=True, timeout=90)
        self.short = next((t for t in r.stdout.split() if len(t) == 8 and all(c in "0123456789abcdef" for c in t)), None)
        rec = wait_for("the --bg job's record", 90, lambda: next(
            (x for x in self.records() if x.get("kind") == "bg" and LB._alive(x.get("pid"))), None))
        session = rec["sessionId"]
        wait_for("its first reply", 120, lambda: any(
            x.get("type") == "assistant" and "ALPHA" in json.dumps(x.get("message")) for x in self.rows(session)))
        rec = self.settled(session, "its title promotion")
        before = rec.get("name")
        self.pend(session, BG, before)
        rec = self.applied(session, BG)
        self.check("a --bg job's pending name is applied between turns, registered user",
                   rec.get("name") == BG and rec.get("nameSource") == "user" and BG in self.titles(session),
                   "record %s (%s) -> %s (%s); custom-title %s" % (before, "kind bg", rec.get("name"),
                                                                    rec.get("nameSource"), self.titles(session)))

    def sdk(self):
        with open(self.envfile, "a") as f:
            f.write("export CLAUDE_CODE_ENTRYPOINT=sdk-ts\nexport SMNS_MEMBER=%d\n" % os.getpid())
        self.headless = subprocess.Popen(self.bash(
            "exec claude -p --input-format stream-json --output-format stream-json --verbose "
            "--include-partial-messages --replay-user-messages --permission-prompt-tool stdio %s "
            "--model haiku --permission-mode default" % self.dirs()),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.procs.append(self.headless)
        threading.Thread(target=self.read_headless, daemon=True).start()
        self.send("Reply with exactly the word ALPHA and nothing else.")
        wait_for("its first result", 120, lambda: self.turns_done())
        rec = wait_for("the SDK session's record", 30, lambda: next(
            (x for x in self.records() if x.get("entrypoint") == "sdk-ts" and LB._alive(x.get("pid"))), None))
        session = rec["sessionId"]
        rec = self.settled(session, "its title promotion")
        before = rec.get("name")
        self.pend(session, SDK, before)
        rec = self.applied(session, SDK)
        self.check("an SDK session's pending name is applied between prompts, registered user",
                   rec.get("name") == SDK and rec.get("nameSource") == "user" and SDK in self.titles(session),
                   "record %s (%s) -> %s (%s); custom-title %s" % (before, "sdk-ts", rec.get("name"),
                                                                    rec.get("nameSource"), self.titles(session)))

    def run(self):
        self.setup()
        self.interactive()
        self.bg()
        self.sdk()

    def cleanup(self):
        if self.short:
            subprocess.run(self.bash("claude stop %s" % shlex.quote(self.short)), capture_output=True, timeout=30)
        super().cleanup()


def main():
    live = NameCheck("--keep" in sys.argv[1:])
    print("live name check (%s):" % live.root, flush=True)
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
