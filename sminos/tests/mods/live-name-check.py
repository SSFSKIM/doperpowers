#!/usr/bin/env python3
"""Live check of the name mod (charge names, M2) in a real session.

What only a running engine shows, pinned so a release that changes it fails
loudly (docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md §2,
§3; if an engine fact below fails, those sections are revisited, not patched
around):
- engine fact: `sessionTitle` from a `SessionStart` hook leaves the engine
  name as it was (a probe plugin of this check's own returns one);
- the mod: a pending name whose `from` is the session's engine name is
  applied at its next prompt — the engine record shows it with `nameSource:
  "hook"`, the transcript a `custom-title` and an `agent-name` record of it,
  and the model's context the one line saying so;
- engine fact: after a resume, the hook-set name is registered `user`;
- the mod: a session its owner /renamed before that prompt keeps its own name.

It spends model calls (haiku, a few one-word turns), so no suite runs it:
run it by hand with the model gateway's keys in the environment. Isolation
is live-bridge-check.py's (whose class it extends): a temporary HOME whose
.claude is the session's config dir, a temporary SMINOS_HOME, a copy of the
worktree's sminos plugin and the probe plugin loaded with --plugin-dir, a
tmux server of its own, the gateway keys in a 0600 env file removed at the
end. The session is started without a name, so the engine generates one.

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
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for

PROBE_TITLE = "probe-start-title"
CHARGE = "live-charge-name"
SECOND = "live-second-name"
OWNER = "owner-chosen-name"
CONTEXT = 'sminos renamed this session to "%s" after its standing responsibility' % CHARGE

PROBE_MANIFEST = {"name": "nameprobe", "version": "0.0.1", "description": "live-name-check: SessionStart sessionTitle"}
PROBE_HOOKS = {"modules": ["./mods/register.tsx"], "hooks": {}}
# Its SessionStart answers a title, and each run is logged, so the check
# knows the hook ran when it reads what the engine did with the title.
PROBE_MOD = """import type { On } from 'claude-code'

const LOG = %s
const lines: string[] = []

export function register(on: On) {
  on('classic.SessionStart', async ($, e, next) => {
    const r = await next(e)
    lines.push(JSON.stringify({ source: e.source }))
    await $.fs.write(LOG, lines.join('\\n') + '\\n')
    return { ...r, sessionTitle: %s }
  })
}
"""


class NameCheck(LB.Live):
    def __init__(self, keep):
        super().__init__(keep)
        self.probe = os.path.join(self.root, "probe")
        self.probe_log = os.path.join(self.root, "probe.log")
        self.pid = None

    def setup(self):
        super().setup()
        os.makedirs(os.path.join(self.probe, ".claude-plugin"))
        os.makedirs(os.path.join(self.probe, "hooks", "mods"))
        with open(os.path.join(self.probe, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump(PROBE_MANIFEST, f)
        with open(os.path.join(self.probe, "hooks", "hooks.json"), "w") as f:
            json.dump(PROBE_HOOKS, f)
        with open(os.path.join(self.probe, "hooks", "mods", "register.tsx"), "w") as f:
            f.write(PROBE_MOD % (json.dumps(self.probe_log), json.dumps(PROBE_TITLE)))

    def plugin_dirs(self):
        return [self.plugin, self.probe]

    def launch(self, *args, probe=True):
        """The interactive session, no name given (the engine generates one), in this check's tmux server."""
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in (self.plugin_dirs() if probe else [self.plugin]))
        inner = "set -e; . %s; cd %s; exec claude %s --model haiku --permission-mode default %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), dirs, " ".join(shlex.quote(a) for a in args))
        cmd = "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)
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

    def record(self):
        """The engine's record of the session in the process this check started last."""
        return next((r for r in self.records() if r.get("sessionId") == self.session
                     and (self.pid is None or r.get("pid") == self.pid)), None)

    def ready(self, resumed=False):
        """Waits for the session's process: its engine record, then its bridge (the mods are loaded)."""
        if resumed:
            rec = wait_for("the resumed session's record", 90, lambda: next(
                (r for r in self.records() if r.get("sessionId") == self.session and r.get("pid") != self.pid
                 and LB._alive(r.get("pid"))), None))
        else:
            rec = wait_for("the session's record", 90, lambda: next(iter(self.records()), None))
            self.session = rec["sessionId"]
        self.pid = rec.get("pid")
        wait_for("the bridge's endpoint", 90, self.status)
        time.sleep(2)
        # Read afresh: the record found first was written before the session's hooks ran.
        return self.record() or {}

    def rows(self):
        rows = []
        for p in glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")):
            with open(p) as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        return rows

    def answered(self, word):
        """The model's reply carrying `word` is in the transcript."""
        return any(r.get("type") == "assistant" and word in json.dumps(r.get("message")) for r in self.rows())

    def turn(self, word):
        self.prompt("Reply with exactly the word %s and nothing else." % word)
        wait_for("the reply %s" % word, 120, lambda: self.answered(word))
        time.sleep(1)

    def pend(self, name, before):
        """A pending name as `sminos derive` hands it (the spec's Interfaces)."""
        d = os.path.join(self.smh, "names")
        os.makedirs(d, mode=0o700, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(os.path.join(d, self.session + ".json"), "w") as f:
            json.dump({"session": self.session, "name": name, "from": before,
                       "line": "Checks that the name mod applies a pending name.", "ts": ts}, f)

    def contexts(self):
        """How many times the model was handed the mod's line (a hook's additional context in the transcript)."""
        return sum(1 for r in self.rows() if r.get("type") == "attachment"
                   and (r.get("attachment") or {}).get("type") == "hook_additional_context"
                   for c in (r["attachment"].get("content") or []) if c.startswith(CONTEXT))

    def titles(self, kind, key):
        return [r.get(key) for r in self.rows() if r.get("type") == kind]

    def run(self):
        self.setup()
        self.launch()
        self.ready()
        ran = wait_for("the probe's SessionStart", 30, lambda: os.path.exists(self.probe_log)
                       and '"startup"' in open(self.probe_log).read() and open(self.probe_log).read())
        time.sleep(1)
        # The record as it stands after the probe's title was answered.
        rec = self.record() or {}
        generated = rec.get("name")
        self.check("engine fact: SessionStart's sessionTitle leaves the engine name as it was",
                   '"startup"' in ran and rec.get("nameSource") == "derived" and generated != PROBE_TITLE,
                   "probe ran %r; record %s (%s)" % (ran.strip(), generated, rec.get("nameSource")))

        self.pend(CHARGE, generated)
        self.turn("ALPHA")
        rec = self.record() or {}
        context = self.contexts() == 1
        self.check("a pending name is applied at the next prompt, registered hook",
                   rec.get("name") == CHARGE and rec.get("nameSource") == "hook",
                   "record %s (%s)" % (rec.get("name"), rec.get("nameSource")))
        self.check("and the transcript keeps it as custom-title and agent-name",
                   CHARGE in self.titles("custom-title", "customTitle") and CHARGE in self.titles("agent-name", "agentName"),
                   "custom-title %s; agent-name %s" % (self.titles("custom-title", "customTitle"),
                                                       self.titles("agent-name", "agentName")))
        self.check("and the model's context carries the line saying so", context, "context line %s" % (
            "found" if context else "MISSING"))

        self.turn("BRAVO")
        rec = self.record() or {}
        contexts = self.contexts()
        self.check("a second prompt leaves the applied name as it is, told once",
                   rec.get("name") == CHARGE and rec.get("nameSource") == "hook" and contexts == 1,
                   "record %s (%s); context lines %d" % (rec.get("name"), rec.get("nameSource"), contexts))

        old = self.pid
        self.prompt("/exit")
        wait_for("the session's exit", 60, lambda: not LB._alive(old))
        time.sleep(1)
        self.launch("--resume", self.session, probe=False)
        rec = self.ready(resumed=True)
        seen = [(rec.get("name"), rec.get("nameSource"))]
        deadline = time.time() + 20
        while time.time() < deadline:
            r = self.record() or {}
            if (r.get("name"), r.get("nameSource")) != seen[-1]:
                seen.append((r.get("name"), r.get("nameSource")))
            time.sleep(0.5)
        self.turn("DELTA")
        r = self.record() or {}
        if (r.get("name"), r.get("nameSource")) != seen[-1]:
            seen.append((r.get("name"), r.get("nameSource")))
        self.check("engine fact: after a resume, the hook-set name is registered user",
                   seen[-1] == (CHARGE, "user"), "record over time %s" % seen)

        self.pend(SECOND, CHARGE)
        self.prompt("/rename %s" % OWNER)
        wait_for("the owner's rename", 60, lambda: (self.record() or {}).get("name") in (OWNER, SECOND))
        self.turn("CHARLIE")
        rec = self.record() or {}
        self.check("a session its owner renamed before the prompt keeps its own name",
                   rec.get("name") == OWNER and rec.get("nameSource") == "user"
                   and SECOND not in self.titles("custom-title", "customTitle"),
                   "record %s (%s); custom-title %s" % (rec.get("name"), rec.get("nameSource"),
                                                        self.titles("custom-title", "customTitle")))


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
