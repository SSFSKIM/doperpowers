#!/usr/bin/env python3
"""Probe (not a check): when does an async ask's answer, given in an idle
session, fail to start the plugin-prompt turn the ask mod submits?

Each scenario runs in a fresh terminal session (fullscreen renderer, so the
`[ answer ]` button takes a mouse press) with a debug log; the model asks an
async question, the turn ends, the button is pressed, the dialog is answered
on the scenario's schedule, and what happened after the Submit is reported:
the plugin-prompt turn and its delay, else the route the answer took (a
human prompt is sent to find out), the mod's debug lines and toasts, and the
transcript's queue-operation rows.

Isolation is live-walk-check.py's (whose classes it extends).

    tests/mods/live-ask-delivery-probe.py [--keep] [--mods-from REF] SCENARIO...

    --mods-from REF          stage the plugin copy's hooks/mods/ from a git ref
                             (e.g. main), to run a version before a fix

    subagent:child[:wait]    the model launches a background agent that sleeps
                             S1 s, then spawns a foreground child (so a
                             subagent's turn.start fires after the main turn
                             ended); answer once the child's start is seen;
                             with :wait, the background agent's notification
                             turn is awaited before any human prompt
    subagent:nochild[:wait]  the control: the same agent, only sleeping;
                             answer at the same moment
    baseline                 answer within a few seconds
    dwell:SECONDS            leave the dialog open SECONDS, then answer
    bg:bash:SLEEP:WHEN       a background Bash `sleep SLEEP; echo done`;
    bg:agent:SLEEP:WHEN      or a background Agent that sleeps SLEEP;
                             WHEN after: answer 12 s after its notification
                             is queued; during: answer while it still runs
    running:bash             answer while the turn's Bash call runs
    running:text             answer while the turn streams its final text
"""

import glob
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LW = _load("live_walk_check", "live-walk-check.py")
LC, LB = LW.LC, LW.LB
wait_for = LB.wait_for
is_main = LC.is_main

ASK = ("Ask me with your question tool (mcp__doperpowers__AskUserQuestion), async true, which fruit I prefer, "
       "header Fruit, options Apple and Pear. ")
DIALOG = lambda pane: "Enter to select" in pane and "Pear" in pane  # noqa: E731
DELIVERY = "responded to your async"
DEBUG_KEEP = re.compile(r"ask: |\$\.prompt\.submit|prompt\.submit|absorb|fold|queue|drain|notification|turn-start|"
                        r"left_queued|removed from the queue|ui\.press|ui\.ask|dialog", re.I)
PANE_KEEP = ("did not reach the model", "not delivered yet", "could not be asked", "goes with the next message")
S1, S2, S3 = 15, 25, 60  # s: the subagent scenarios' background agent: sleep, its child's sleep, sleep again


def _hms(t):
    return time.strftime("%H:%M:%S", time.gmtime(t)) + ".%03d" % int((t % 1) * 1000)


class Probe(LW.Walk):
    def __init__(self, keep, scenarios, mods_from=None):
        super().__init__(keep, set())
        self.scenarios = scenarios
        self.mods_from = mods_from
        self.n = 0
        self.reports = []

    def setup(self):
        LB.Live.setup(self)
        if self.mods_from:
            # The staged copy's mods as they were at a git ref (the worktree's sources stay as they are).
            names = subprocess.run(["git", "-C", LB.REPO, "ls-tree", "--name-only", self.mods_from, "hooks/mods/"],
                                   capture_output=True, text=True, check=True).stdout.split()
            for name in names:
                body = subprocess.run(["git", "-C", LB.REPO, "show", "%s:%s" % (self.mods_from, name)],
                                      capture_output=True, check=True).stdout
                with open(os.path.join(self.plugin, name), "wb") as f:
                    f.write(body)
            print("  plugin copy's hooks/mods/ from %s (%d files)" % (self.mods_from, len(names)), flush=True)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"permissions": {"allow": ["Bash"]}}, f)
        with open(self.envfile, "a") as f:
            f.write("export CLAUDE_CODE_FORK_SUBAGENT=0\n")
            f.write("export CLAUDE_CODE_NO_FLICKER=1\n")

    # -- one fresh session per scenario

    def fresh(self, label):
        if self.n:
            subprocess.run(self.tmux + ["kill-session", "-t", self.target], capture_output=True)
            if getattr(self, "stream", None):
                self.stream.stop.set()
            time.sleep(2)
        self.n += 1
        self.target = "p%d" % self.n
        self.debug = os.path.join(self.root, "debug-%d-%s.log" % (self.n, re.sub(r"[^a-z0-9]+", "-", label)))
        bridge = os.path.join(self.smh, "bridge")
        known = set(os.listdir(bridge)) if os.path.isdir(bridge) else set()
        inner = ("set -e; . %s; cd %s; exec claude --plugin-dir %s --model haiku --permission-mode default -n %s "
                 "--debug-file %s") % (shlex.quote(self.envfile), shlex.quote(self.work), shlex.quote(self.plugin),
                                       "probe%d" % self.n, shlex.quote(self.debug))
        subprocess.run(self.tmux + ["new-session", "-d", "-s", self.target, "-x", "200", "-y", "50",
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)
        found = wait_for("the session's socket", 90, lambda: [
            n for n in os.listdir(bridge) if n.endswith(".sock") and not n.startswith(".") and n not in known]
            if os.path.isdir(bridge) else None)
        self.session = found[0][:-5]
        wait_for("its endpoint, ready", 30, lambda: (self.status() or {}).get("ready"))
        self.stream = self.streams[self.session] = LC.Stream(self.endpoint())
        wait_for("its subscription", 10, lambda: self.stream.subscriptions > 0)

    # -- observation

    def sample_pane(self, stop, seen, t0):
        while not stop.is_set():
            pane = self.pane()
            for line in pane.splitlines():
                for key in PANE_KEEP:
                    if key in line:
                        seen.setdefault(line.strip(), round(time.time() - t0, 1))
            time.sleep(0.3)

    def main_state(self):
        try:
            s, body = LB.request(self.endpoint(), "POST", "/command?wait=8000", {"op": "ping"}, timeout=15)
            return (body or {}).get("result", {}).get("state")
        except OSError as e:
            return {"error": str(e)}

    def debug_lines(self, offset=0):
        try:
            with open(self.debug, errors="replace") as f:
                f.seek(offset)
                text = f.read()
        except OSError:
            return []
        return [line.rstrip() for line in text.splitlines() if DEBUG_KEEP.search(line)]

    def debug_size(self):
        try:
            return os.path.getsize(self.debug)
        except OSError:
            return 0

    def rows(self):
        return self.transcript_rows(self.session)

    def queue_rows(self, since_iso):
        return [r for r in self.rows() if r.get("type") == "queue-operation" and r.get("timestamp", "") >= since_iso]

    def press_band(self, label="[ answer ]"):
        """A press on the bottom-most `label` (the band above the prompt, which does not scroll)."""
        lines = self.pane().splitlines()
        for y in range(len(lines) - 1, -1, -1):
            x = lines[y].find(label)
            if x >= 0:
                col, row = x + 3, y + 1
                self.keys("-l", "\x1b[<0;%d;%dM" % (col, row))
                self.keys("-l", "\x1b[<0;%d;%dm" % (col, row))
                return "%d,%d" % (col, row)
        return None

    def open_dialog(self, bottom=False):
        if not bottom:
            return self.press_open("[ answer ]", lambda: DIALOG(self.pane()))
        for i in range(4):
            cell = self.press_band()
            try:
                wait_for("the dialog", 6, lambda: DIALOG(self.pane()))
                return True, i + 1, "dialog open after %d band press(es), last at %s" % (i + 1, cell)
            except TimeoutError:
                pass
        return False, 4, "the band's [ answer ] pressed 4 times and no dialog opened"

    def submit(self, rid):
        """Enter until the dialog closes; the time of the Enter that closed it."""
        for i in range(4):
            t = time.time()
            self.keys("Enter")
            try:
                wait_for("the dialog to close", 5, lambda: not DIALOG(self.pane()))
                return t, i + 1
            except TimeoutError:
                pass
        return None, 4

    # -- a scenario

    def ask_turn(self, extra, wait_end=True):
        t = time.time()
        self.prompt(ASK + extra)
        _, raised = self.raised(self.stream, t, lambda e: e.get("async") is True, "the async question", seconds=120)
        if wait_end:
            self.turn_end(self.stream, t, seconds=180)
        return t, raised["request"]

    def scenario(self, spec):
        parts = spec.split(":")
        kind = parts[0]
        self.fresh(spec)
        rep = {"scenario": spec, "session": self.session, "debug": self.debug}
        iso0 = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 1))
        off0 = self.debug_size()
        bg_call = None
        dwell = 2.0
        when = None

        if kind in ("baseline", "dwell"):
            dwell = float(parts[1]) if kind == "dwell" else 2.0
            t_ask, rid = self.ask_turn("Then end your turn saying waiting.")
        elif kind == "bg":
            what, sleep, when = parts[1], int(parts[2]), parts[3]
            if what == "bash":
                extra = ("Then start this Bash command in the background (run_in_background true): "
                         "sleep %d; echo done. Then end your turn at once saying waiting; do not wait for it." % sleep)
            else:
                extra = ("Then launch one background agent with the Agent tool (run_in_background true, "
                         "subagent_type general-purpose, description 'sleeper') whose prompt is: Run the Bash "
                         "command `sleep %d` and then reply with the word done. Then end your turn at once "
                         "saying waiting; do not wait for it." % sleep)
            t_ask, rid = self.ask_turn(extra)
            tool = "Bash" if what == "bash" else "Agent"
            calls = self.stream.seen_at(lambda e: is_main(e, "tool", "call") and e.get("tool") == tool, t_ask)
            bg_call = calls[0][0] if calls else None
            rep["bg_started_after_ask_s"] = round(bg_call - t_ask, 1) if bg_call else None
        elif kind == "running":
            if parts[1] == "bash":
                extra = ("Then run exactly this Bash command in the foreground: python3 -c 'import time; "
                         "time.sleep(30); print(\"slept\")' Then reply with one short sentence.")
            else:
                extra = "Then, using no tools, write a 900-word story about a lighthouse keeper."
            t_ask, rid = self.ask_turn(extra, wait_end=False)
        elif kind == "subagent":
            child = parts[1] == "child"
            if child:
                job = ("First run the Bash command: sleep %d. Then use the Agent tool exactly once, in the "
                       "foreground (run_in_background false), subagent_type general-purpose, description 'child', "
                       "with the prompt: Run the Bash command sleep %d, then reply with the word hi. After it "
                       "returns, run the Bash command: sleep %d. Then reply with the word done." % (S1, S2, S3))
            else:
                job = ("First run the Bash command: sleep %d. Then run the Bash command: sleep %d. Then run the "
                       "Bash command: sleep %d. Then reply with the word done." % (S1, S2, S3))
            extra = ("Then launch one background agent with the Agent tool (run_in_background true, subagent_type "
                     "general-purpose, description 'nester') whose prompt is exactly: %s Then end your turn at once "
                     "saying waiting; do not wait for it." % job)
            t_ask, rid = self.ask_turn(extra)
            main_end = self.stream.seen_at(lambda e: is_main(e, "turn", "complete"), t_ask)[0][0]
            rep["main_turn_end"] = _hms(main_end)
            if child:
                # A subagent's run starting after the main turn's end: the child's.
                late = wait_for("a subagent's turn.start after the main turn's end", 150, lambda: self.stream.seen_at(
                    lambda e: e.get("type") == "turn" and e.get("phase") == "start" and e.get("agentId"), main_end))
                rep["late_subagent_start_after_main_end_s"] = round(late[0][0] - main_end, 1)
                time.sleep(1)
            else:
                # The same moment, with no subagent starting.
                time.sleep(max(0.0, main_end + S1 + 4 - time.time()))
        else:
            raise ValueError("unknown scenario %s" % spec)
        rep["call"] = rid

        if kind == "subagent":
            rep["state_before_press"] = self.main_state()
        elif kind != "running":
            self.idle(self.endpoint())
            rep["state_before_press"] = self.main_state()
        elif parts[1] == "bash":
            wait_for("the Bash call", 90, lambda: self.stream.seen(
                lambda e: is_main(e, "tool", "call") and e.get("tool") == "Bash", t_ask))
            time.sleep(1)
        else:
            wait_for("story text", 90, lambda: len(LC.main_text(self.stream, t_ask)) > 200)

        stop, seen = threading.Event(), {}
        t_press = time.time()
        threading.Thread(target=self.sample_pane, args=(stop, seen, t_press), daemon=True).start()
        opened, presses, why = self.open_dialog(bottom=(kind == "running"))
        t_open = time.time()
        rep["dialog"] = why
        if not opened:
            stop.set()
            rep["error"] = "the dialog did not open"
            return rep

        # The dwell: until the scenario's moment, noting what happens meanwhile.
        if kind == "bg" and when == "after":
            enq = None
            try:
                enq = wait_for("the task's notification in the queue", 300, lambda: [
                    r for r in self.queue_rows(iso0) if r.get("operation") == "enqueue"
                    and "<task-notification>" in str(r.get("content"))])
            except TimeoutError:
                rep["note"] = "no task-notification was queued within 300 s"
            if enq:
                rep["notification_queued_after_open_s"] = round(time.time() - t_open, 1)
            time.sleep(12)
        elif kind == "bg" and when == "during":
            time.sleep(5)
        else:
            time.sleep(max(0.0, t_open + dwell - time.time()))
        rep["dialog_still_open"] = DIALOG(self.pane())
        rep["turns_during_dialog"] = [str(e.get("text"))[:90] for e in self.stream.seen(
            lambda e: is_main(e, "turn", "start"), t_open)]
        rep["state_at_submit"] = self.main_state()
        rep["dwell_s"] = round(time.time() - t_open, 1)
        t_sub, enters = self.submit(rid)
        if t_sub is None:
            stop.set()
            rep["error"] = "the dialog did not close after %d Enters" % enters
            return rep
        rep["enters"] = enters

        # After the Submit.
        try:
            woke = wait_for("the plugin-prompt turn", 20 if kind == "subagent" else 75, lambda: self.stream.seen_at(
                lambda e: is_main(e, "turn", "start") and DELIVERY in str(e.get("text")), t_sub))
            rep["plugin_turn_after_submit_s"] = round(woke[0][0] - t_sub, 2)
            rep["plugin_turn_text"] = str(woke[0][1].get("text"))[:110]
            self.turn_end(self.stream, woke[0][0], seconds=180)
        except TimeoutError:
            rep["plugin_turn_after_submit_s"] = None
        if kind == "running" or kind == "bg":
            # Let any running turn (the scenario's own, a notification's) end.
            try:
                self.idle(self.endpoint(), 240)
            except TimeoutError:
                rep["note_idle"] = "the session did not go idle within 240 s"
        time.sleep(3)
        rep["turns_after_submit"] = [(round(t - t_sub, 1), str(e.get("text"))[:90]) for t, e in self.stream.seen_at(
            lambda e: is_main(e, "turn", "start"), t_sub)]
        rep["state_after"] = self.main_state()
        rep["pane_seen_before_probe_prompt"] = dict(seen)
        rep["route"] = self.route(rid)
        if rep["route"] is None and "wait" in parts[1:]:
            # The next main turn the session runs by itself: the background agent's notification.
            try:
                n = wait_for("the notification turn", 300, lambda: self.stream.seen_at(
                    lambda e: is_main(e, "turn", "start") and "<task-notification>" in str(e.get("text")), t_sub))
                rep["notification_turn_after_submit_s"] = round(n[0][0] - t_sub, 1)
                self.idle(self.endpoint(), 240)
                time.sleep(3)
            except TimeoutError:
                rep["note_wait"] = "no notification turn within 300 s"
            rep["route_after_notification_turn"] = self.route(rid)
        if rep["route"] is None and rep.get("route_after_notification_turn") is None:
            rep["row_reads_not_delivered_before_prompt"] = "not delivered yet" in self.pane()
            # Nothing reached the model yet: a human prompt finds the route left.
            t = time.time()
            self.prompt("Reply with exactly: ok")
            try:
                self.turn_end(self.stream, t, seconds=120)
            except TimeoutError:
                pass
            time.sleep(3)
            rep["route_after_human_prompt"] = self.route(rid)
        stop.set()
        rep["pane_seen"] = seen
        rep["debug_lines"] = self.debug_lines(off0)
        rep["queue_rows"] = [(r.get("timestamp", "")[11:23], r.get("operation"), r.get("reason"),
                              str(r.get("content", ""))[:70].replace("\n", " ")) for r in self.queue_rows(iso0)]
        rep["timeline"] = {"press": _hms(t_press), "open": _hms(t_open), "submit": _hms(t_sub)}
        # Every turn event the bridge streamed from the ask on (main and subagents), time since the Submit.
        rep["turn_events"] = [(round(t - t_sub, 1), e.get("phase"), (e.get("agentId") or "main")[:10], e.get("reason"),
                               str(e.get("text") or "")[:50].replace("\n", " "))
                              for t, e in self.stream.seen_at(lambda e: e.get("type") == "turn", t_ask)]
        return rep

    def route(self, rid):
        """How the call's answer reached the model, by the transcript."""
        for r in self.rows():
            if r.get("type") == "user":
                content = (r.get("message") or {}).get("content")
                texts = [content] if isinstance(content, str) else [b.get("text", "") for b in content or []
                                                                    if isinstance(b, dict) and b.get("type") == "text"]
                for text in texts:
                    if "(call %s)" % rid in text and text.startswith("The doperpowers plugin sent a message"):
                        mid = "while you were working" in text.split("\n")[0]
                        return {"route": "plugin prompt" + (" (mid-turn)" if mid else ""), "at": r.get("timestamp"),
                                "origin": r.get("origin")}
            if r.get("type") == "attachment" and (r.get("attachment") or {}).get("type") == "hook_additional_context":
                a = r["attachment"]
                if any("(call %s)" % rid in str(c) for c in (a.get("content") or [])):
                    return {"route": "context", "hookName": a.get("hookName"), "hookEvent": a.get("hookEvent"),
                            "at": r.get("timestamp")}
            if r.get("type") == "queue-operation" and "(call %s)" % rid in str(r.get("content")):
                pass
        return None

    def run(self):
        self.setup()
        for spec in self.scenarios:
            print("== %s" % spec, flush=True)
            try:
                rep = self.scenario(spec)
            except Exception as e:  # noqa: BLE001 — report and go on to the next scenario
                rep = {"scenario": spec, "error": "%s: %s" % (type(e).__name__, e),
                       "pane": self.pane().rstrip().splitlines()[-20:]}
            self.reports.append(rep)
            print(json.dumps(rep, indent=1, ensure_ascii=False), flush=True)


def main():
    args = sys.argv[1:]
    mods_from = None
    if "--mods-from" in args:
        i = args.index("--mods-from")
        mods_from = args[i + 1]
        del args[i:i + 2]
    keep = "--keep" in args
    args = [a for a in args if a != "--keep"]
    if not args:
        sys.exit(__doc__)
    live = Probe(keep, args, mods_from)
    print("ask delivery probe (%s):" % live.root, flush=True)
    try:
        live.run()
    finally:
        live.cleanup()
    with open(os.path.join(live.root if live.keep else "/tmp", "probe-report-%d.json" % os.getpid()), "w") as f:
        json.dump(live.reports, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
