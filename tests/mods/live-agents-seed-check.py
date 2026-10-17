#!/usr/bin/env python3
"""Live check of the bridge's agent seed (DC8 M3, DX5 "For DC8") in a real
session: an agent that runs while the module reloads is known to the new
module only from `$.agent.list()`, so the new child's first snapshot carries
it, running, with what the list gives and nothing else; its end then reaches
the stream as a stop.

It spends model calls (haiku, short prompts), so no suite runs it: run it by
hand, with the model gateway's keys in the environment. It runs in
live-bridge-check.py's isolation (a temporary HOME and SMINOS_HOME, a copy of
the worktree's plugin loaded with --plugin-dir, a tmux server of its own).

    tests/mods/live-agents-seed-check.py [--keep]
"""

import importlib.util
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))
spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
lbc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lbc)

# What the list gives a spawn, and the state's own flag (DX5 "For DC8").
SEEDED = {"agentId", "parentAgentId", "subagentType", "description", "name", "running"}


class Seed(lbc.Live):
    def snapshot(self):
        c = lbc.Conn(self.endpoint(), timeout=10)
        try:
            c.request("GET", "/events")
            return json.loads(c.getresponse().readline())
        finally:
            c.close()

    def run(self):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = lbc.wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                                 if n.endswith(".sock") and not n.startswith(".")]
                             if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        lbc.wait_for("the endpoint to answer", 20, self.status)
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        lbc.wait_for("the subscription", 10, lambda: self.subscriptions > 0)

        t0 = time.time()
        self.prompt("Use the Agent tool exactly once, subagent_type general-purpose, with run_in_background set to "
                    "true, asking it to write a 1500-word essay about lighthouses and reply with it, using no tools. "
                    "Then say only 'launched' and end your turn without waiting for it.")
        spawned = lbc.wait_for("the agent's spawn", 120, lambda: self.seen(
            lambda e: e.get("type") == "agent" and e.get("phase") == "spawn", t0))
        agent = spawned[0]["agentId"]
        self.check("the module that saw it spawn reports it with the spawn's record",
                   spawned[0].get("toolUseId") and "background" in spawned[0], json.dumps(spawned[0])[:200])

        old = self.status()["pid"]
        with open(os.path.join(self.plugin, "hooks", "mods", "bridge.tsx"), "a") as f:
            f.write("\n// live-agents-seed-check: a change that reloads the module\n")
        lbc.wait_for("the child after a module reload", 60,
                     lambda: (self.status() or {}).get("pid") not in (None, old) and self.status())
        snap = lbc.wait_for("the new child's snapshot", 20, lambda: self.snapshot())
        mine = [a for a in snap.get("agents") or [] if a.get("agentId") == agent]
        stopped_before = self.seen(lambda e: e.get("type") == "agent" and e.get("phase") == "stop"
                                   and e.get("agentId") == agent, t0)
        self.check("after the reload, the new child's first snapshot holds the agent, seeded from the list",
                   mine and (mine[0]["running"] or stopped_before),
                   "%s; stopped before the reload: %s" % (json.dumps(mine)[:300], bool(stopped_before)))
        self.check("the seeded entry carries what the list gives and nothing else",
                   mine and set(mine[0]) <= SEEDED | {"agentType"} and "toolUseId" not in mine[0],
                   "fields %s" % (sorted(mine[0]) if mine else None))
        if mine and mine[0]["running"]:
            t1 = time.time()
            stop = lbc.wait_for("the agent's end", 240, lambda: self.seen(
                lambda e: e.get("type") == "agent" and e.get("phase") == "stop" and e.get("agentId") == agent, t1))
            self.check("its end reaches the stream as a stop", stop, json.dumps(stop[0])[:200])


def main():
    live = Seed("--keep" in sys.argv[1:])
    print("live agents seed check (%s):" % live.root, flush=True)
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
