#!/usr/bin/env python3
"""Live check of stopping a background job through the bridge (the desk's DC10).

What only a running engine shows, pinned so a release that breaks it fails
loudly, in a terminal session with the bridge:
- the daemon's `stop` command (sminos_rpc.stop, as DX6 `stop` runs it) stops
  a main-loop background shell, a main-loop monitor, and a background
  subagent's monitor, each with TaskStop through `$.tool.call`, and the
  process is gone;
- each job then reads `stopped` from the session's own rows within 2 s (the
  derivation DX4 sends, sminos_jobs), from the bridge's note: a plugin's
  TaskStop writes no row of its own;
- the daemon's check (sminos_jobs.running_task) holds each as running before
  and not after;
- a second stop of a stopped task is the engine's refusal, in its words, and
  an agent's id is refused by the mod before any TaskStop;
- the model, reading the notes, knows the jobs are stopped.

It spends model calls (haiku, short prompts, one subagent), so no suite runs
it: run it by hand with the model gateway's keys in the environment.
Isolation is live-bridge-check.py's (whose class it extends): a temporary
HOME whose .claude is the session's config dir, a temporary SMINOS_HOME, a
copy of the worktree's plugin, a tmux server of its own, the gateway keys in
a 0600 env file removed at the end.

    sminos/tests/mods/live-stop-check.py [--keep]
"""

import glob
import importlib.util
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_bridge_check", os.path.join(HERE, "live-bridge-check.py"))
LB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LB)
wait_for = LB.wait_for
SCRIPTS = os.path.join(LB.PLUGIN_ROOT, "skills", "sminos", "scripts")


class Stop(LB.Live):
    def setup(self):
        super().setup()
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash", "Monitor", "Agent", "TaskStop"]}}, f)
        # The Monitor tool is behind a feature gate (2.1.300 `h4`, tengu_amber_sentinel) that a config reached
        # only through the model gateway never fetches: the temporary config's cache holds it on.
        state = os.path.join(self.cfg, ".claude.json")
        with open(state) as f:
            config = json.load(f)
        config["cachedGrowthBookFeatures"] = {"tengu_amber_sentinel": True}
        with open(state, "w") as f:
            json.dump(config, f)
        # sminos_rpc and sminos_jobs are imported into this process: under the check's own HOME and SMINOS_HOME.
        os.environ["HOME"], os.environ["SMINOS_HOME"] = self.home, self.smh
        sys.path.insert(0, SCRIPTS)
        global jobs, rpc
        import sminos_jobs as jobs  # noqa: E402
        import sminos_rpc as rpc  # noqa: E402

    def main_transcript(self):
        hits = glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl"))
        return hits[0] if hits else ""

    def all_jobs(self):
        """taskId → (loop, job) for every loop of the session, as DX4 derives them."""
        main = self.main_transcript()
        if not main:
            return {}
        loops = [("main", main)] + [(os.path.basename(p)[len("agent-"):-len(".jsonl")], p) for p in
                                     sorted(glob.glob(os.path.join(main[:-len(".jsonl")], "subagents", "agent-*.jsonl")))]
        top, out = None, {}
        for name, path in loops:
            ledger = jobs.Ledger()
            with open(path, "rb") as f:
                for line in f:
                    if line.startswith(jobs.REQUEST_RECORD):
                        continue
                    try:
                        ledger.add(json.loads(line))
                    except ValueError:
                        pass
            top = top or ledger
            for j in ledger.jobs_body(True, None if ledger is top else top):
                out[j["taskId"]] = (name, j)
        return out

    def run(self):
        self.setup()
        self.start_session()
        sock_dir = os.path.join(self.smh, "bridge")
        found = wait_for("the bridge's socket", 90, lambda: [n for n in os.listdir(sock_dir)
                                                             if n.endswith(".sock") and not n.startswith(".")]
                         if os.path.isdir(sock_dir) else None)
        self.session = found[0][:-5]
        wait_for("the endpoint to answer", 20, self.status)
        m = "dcten%d" % os.getpid()
        self.prompt(
            "Do exactly these three steps, then reply DONE. "
            "1) Call the Bash tool with run_in_background true and this command: "
            "python3 -c 'import time; time.sleep(600)' # %sshell "
            "2) Call the Monitor tool with description 'idle watch' and this command: tail -F /dev/null # %smon "
            "3) Call the Agent tool with subagent_type general-purpose, run_in_background true, description "
            "'watcher', and this prompt: 'Call the Monitor tool with description sub watch and this command: "
            "tail -F /dev/null # %ssub - then reply STARTED and nothing else.'" % (m, m, m))

        def three():
            js = self.all_jobs()
            kinds = {(loop == "main", j["kind"]): t for t, (loop, j) in js.items() if j["status"] == "running"}
            return kinds if len(kinds) >= 3 else None
        kinds = wait_for("a main shell, a main monitor and a subagent's monitor, running", 240, three, every=1.0)
        shell, mon, sub = kinds.get((True, "shell")), kinds.get((True, "monitor")), kinds.get((False, "monitor"))
        self.check("the session runs a main-loop shell, a main-loop monitor and a subagent's monitor",
                   shell and mon and sub, json.dumps({str(k): v for k, v in kinds.items()}))
        time.sleep(3)   # the main turn answers DONE; the stops below run with the session idle
        main = self.main_transcript()
        path = self.endpoint()
        for label, task, marker in (("main shell", shell, m + "shell"), ("main monitor", mon, m + "mon"),
                                    ("subagent's monitor", sub, m + "sub")):
            if not task:
                continue
            before = jobs.running_task(main, task)
            procs = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
            t0 = time.time()
            try:
                out = rpc.stop(path, task)
            except rpc.Refused as r:
                out = r.outcome
            took = None
            try:
                wait_for("%s reading stopped" % label, 10,
                         lambda: self.all_jobs().get(task, (None, {}))[1].get("status") == "stopped", every=0.05)
                took = time.time() - t0
            except TimeoutError:
                pass
            time.sleep(2)
            left = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
            self.check("%s: stop answers done {taskId}" % label, out == {"state": "done", "result": {"taskId": task}},
                       json.dumps(out))
            self.check("%s: the daemon's check held it running before, and not after" % label,
                       before and not jobs.running_task(main, task), "before %s" % before)
            self.check("%s: reads stopped from the session's rows within 2 s" % label, took is not None and took <= 2.0,
                       "%s s; %s" % (took and round(took, 2), json.dumps(self.all_jobs().get(task))[:200]))
            self.check("%s: its process is gone" % label, procs and not left, "before %s, after %s" % (procs, left))
        if shell:
            try:
                again = rpc.stop(path, shell)
            except rpc.Refused as r:
                again = r.outcome
            self.check("a second stop is the engine's refusal, in its words", again.get("state") == "failed"
                       and "<tool_use_error>" not in json.dumps(again), json.dumps(again))
        agents = [os.path.basename(p)[len("agent-"):-len(".jsonl")] for p in
                  glob.glob(os.path.join(main[:-len(".jsonl")], "subagents", "agent-*.jsonl"))]
        if agents:
            try:
                refused = rpc.stop(path, agents[0])
            except rpc.Refused as r:
                refused = r.outcome
            self.check("an agent's id is refused before any TaskStop", "is an agent" in json.dumps(refused),
                       json.dumps(refused))
        if sub:
            try:
                note = wait_for("the subagent's own notice of its stopped monitor", 20, lambda: [
                    l for p in glob.glob(os.path.join(main[:-len(".jsonl")], "subagents", "agent-*.jsonl"))
                    for l in open(p, encoding="utf-8") if sub in l and "<status>" in l], every=0.5)
                print("  (observed) the subagent's transcript: %s" % note[0][:240].replace("\n", " "), flush=True)
            except TimeoutError:
                print("  (observed) no notice of the stop in the subagent's transcript within 20 s", flush=True)
        t = time.time()
        self.subscribe_thread()
        self.prompt("Without calling any tool, answer in one word: are your background tasks (the python sleep and "
                    "the idle watch monitor) still running? Reply RUNNING or STOPPED.")
        try:
            self.wait_turn_end(t, 120)
        except TimeoutError:
            pass
        text = "".join(e["chunk"].get("text") or "" for e in self.seen(
            lambda e: e.get("type") == "chunk" and e.get("agentId") is None and e["chunk"].get("kind") == "text", t))
        self.check("the model, reading the notes, knows its jobs are stopped", "STOPPED" in text and "RUNNING" not in text,
                   repr(text[-120:]))

    def subscribe_thread(self):
        import threading
        threading.Thread(target=self.subscribe_forever, daemon=True).start()
        wait_for("the subscription", 10, lambda: self.subscriptions > 0)


def main():
    live = Stop("--keep" in sys.argv[1:])
    print("live stop check (%s):" % live.root, flush=True)
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
