#!/usr/bin/env python3
"""Live check of fold summaries: acceptance 1 to 6 and 7's "one summary" of
docs/doperpowers/specs/2026-11-12-fold-summaries-design.md.

Three isolated interactive sessions (haiku):
- the main one, under the `doperpowers:to-human` output style:
  turn A sends a message, starts a background command, waits on a foreground
  one while it finishes (a delivery folded into the running turn), and ends
  on a final message; a `/reload-plugins` that starts the plugin's module
  over follows; turn B runs commands and ends on plain text, sending no
  message; the session quits right after B's summary shows and is resumed;
- one whose summary calls name a model that does not exist
  (`TO_HUMAN_FOLD_MODEL`);
- one without the output style.

It prints PASS or FAIL for each item, with what it judged:
1. while A waits, the fold under its first message reads `› ` and a running
   call's line (its description);
2. within 30 s of A's final message, that fold reads the summary the
   session's file holds for the stretch: not `working record`, not a call's
   line;
3. B's fold reads its summary once B's turn ended, nothing typed since;
4. after the reload, A's fold still reads its summary; after the quit and
   `claude --resume`, A's and B's folds both do;
5. with the call failing, the closed fold reads `› working record`, the
   failure is in the debug log, and the next turn runs as ever (pressing the
   button to unfold the run is the kit's test, folds.test.ts: the main
   screen takes no click from tmux);
6. without the output style, no summary is made (no session file, no
   summary line in the debug log) and no fold button is drawn;
7. A's stretch, which took the background command's notification mid-turn,
   draws one fold with one summary.
Haiku does not always follow a script (a message and a call in one response
or two, an extra note): each item reads what the transcript shows was done,
and says "not exercised" where haiku's turn left nothing to judge.

It spends model calls (about 15 to 20, haiku), so no suite runs it: run it by
hand with the model gateway's keys in the environment. It is built on
live-message-check.py's isolated session (a temporary HOME whose .claude is
the session's config dir, SMINOS_HOME and project, copies of the worktree's
plugins, the to-human one with its `types`, a tmux server of its own, the
keys in a 0600 env file removed at the end). With --keep each session's
directory stays (minus the env file), holding the frames and the debug log.

    to-human/tests/mods/live-folds-check.py [--keep]
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("live_message_check", os.path.join(HERE, "live-message-check.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

MESSAGE_TOOL = base.MESSAGE_TOOL
# A fold's button: `› ` and its label at the start of a line (the band's `full transcript ›` ends its line).
FOLD = re.compile(r"^\s*› (.+?)\s*$", re.M)
SUMMARY_WAIT = 30

PROMPT_A = (
    "This is a test of your tools. Do these steps in order. "
    "1. Call the tool %s with the text `Starting alpha.` "
    "2. Run the Bash command `sleep 4` with run_in_background set to true and the description `Background nap`. "
    "3. Run the Bash command `sleep 12` in the foreground with the description `Wait for alpha`. "
    "4. Run the Bash command `echo alpha-done` with the description `Print alpha done`. "
    "5. Call the tool %s with the text `Alpha finished.` and final set to true." % (MESSAGE_TOOL, MESSAGE_TOOL))
PROMPT_B = (
    "This is a silent maintenance step: do not call %s and do not write any message for the human. "
    "Run the Bash command `echo bravo-one` with the description `Echo bravo one`, then the Bash command "
    "`echo bravo-two` with the description `Echo bravo two`, then reply with the plain text `bravo ok` and "
    "nothing else." % MESSAGE_TOOL)
PROMPT_C = (
    "This is a test of your tools. 1. Call the tool %s with the text `Starting charlie.` "
    "2. Run the Bash command `echo charlie-one` with the description `Echo charlie`. "
    "3. Call the tool %s with the text `Charlie finished.` and final set to true." % (MESSAGE_TOOL, MESSAGE_TOOL))
PROMPT_C2 = "Call the tool %s with the text `Charlie again.` and final set to true." % MESSAGE_TOOL
PROMPT_D = ("Run the Bash command `echo delta-one` with the description `Echo delta`, then reply with the plain "
            "text `delta ok` and nothing else.")


def blocks(rows, kind):
    return base.Live.blocks(rows, kind)


class Session(base.Live):
    """One isolated session, as live-message-check.py makes it, quit and resumed at will."""

    def __init__(self, keep, name, env=None, style=True):
        super().__init__(keep, "haiku", "default")
        self.name, self.extra, self.style = name, env or {}, style
        self.frames = []

    def setup(self):
        super().setup()
        if self.extra:
            with open(self.envfile, "a") as f:
                for k, v in sorted(self.extra.items()):
                    f.write("export %s=%s\n" % (k, shlex.quote(v)))
        if not self.style:
            path = os.path.join(self.cfg, "settings.json")
            with open(path) as f:
                settings = json.load(f)
            settings.pop("outputStyle", None)
            with open(path, "w") as f:
                json.dump(settings, f)

    def resume(self):
        """Starts the session again from its transcript, as `claude --resume` does."""
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.dirs)
        inner = "set -e; . %s; cd %s; exec claude %s --model %s --resume %s --debug-file %s --permission-mode %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), dirs, shlex.quote(self.model), self.session,
            shlex.quote(self.debug + ".resumed"), shlex.quote(self.mode))
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "t", "-x", "160", "-y", "60",
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)

    def is_running(self):
        return subprocess.run(self.tmux + ["has-session", "-t", "t"], capture_output=True).returncode == 0

    def snap(self, label):
        frame = self.pane()
        self.frames.append((label, frame))
        return frame

    def logged(self, suffix=""):
        path = self.debug + suffix
        return open(path, errors="replace").read() if os.path.exists(path) else ""

    def stops(self):
        return sum(1 for r in self.rows() if r.get("type") == "system" and r.get("subtype") == "stop_hook_summary")

    def turn(self, prompt, seconds=240, during=None):
        """Sends a prompt and waits for its turn's end; the rows it added."""
        before, stops = len(self.rows()), self.stops()
        self.send(prompt)
        base.wait_for("%s: the turn's end" % self.name, seconds, lambda: self.stops() > stops, during=during)
        return self.rows()[before:]

    def stored(self):
        path = os.path.join(self.cfg, "to-human", "folds", self.session + ".json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return json.load(f).get("runs", [])

    def cleanup(self):
        if self.keep:
            with open(os.path.join(self.root, "frames.txt"), "w") as f:
                for label, frame in self.frames:
                    f.write("=== %s\n%s\n" % (label, frame))
        super().cleanup()


def ids_of(rows):
    """Every id a run can start at: the rows' own, and their calls'."""
    out = set()
    for row in rows:
        if row.get("uuid"):
            out.add(row["uuid"])
        for _, b in blocks([row], "tool_use"):
            out.add(b.get("id"))
    return out


def lines_of(rows):
    """The live lines a call of these rows could have shown: a Bash call's description or its command."""
    out = set()
    for _, b in blocks(rows, "tool_use"):
        inp = b.get("input") or {}
        for k in ("description", "command"):
            if isinstance(inp.get(k), str) and inp[k].strip():
                out.add(inp[k].strip().split("\n")[0])
    return out


def messages(rows):
    return [(r, b) for r, b in blocks(rows, "tool_use") if b.get("name") == MESSAGE_TOOL]


def labels(frame):
    return [m.group(1) for m in FOLD.finditer(frame)]


def stretch(rows, opener, closer):
    """The rows between the message whose text holds `opener` and the next whose text holds `closer`."""
    at = [i for i, r in enumerate(rows) for _, b in blocks([r], "tool_use")
          if b.get("name") == MESSAGE_TOOL and opener in str(b.get("input", {}).get("text", "")).lower()]
    end = [i for i, r in enumerate(rows) for _, b in blocks([r], "tool_use")
           if b.get("name") == MESSAGE_TOOL and closer in str(b.get("input", {}).get("text", "")).lower()]
    if not at or not end:
        return None
    # A response's blocks are kept as rows of their own; the opener's row holds it, the closer's ends the stretch.
    return rows[at[0]:end[-1] + 1]


def summary_shown(frame, summary):
    """Whether a fold reads the summary (the terminal may wrap a long one: its start is enough)."""
    return any(label == summary or (len(label) >= 40 and summary.startswith(label)) for label in labels(frame))


def run(keep):
    results = []

    def check(name, ok, detail):
        results.append(ok)
        print("%s  %s: %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    # -- the main session: A, a reload, B, a quit and a resume
    main = Session(keep, "main")
    try:
        main.setup()
        main.start()
        base.wait_for("the prompt", 60, lambda: "❯" in main.pane())

        live_seen = []

        def watch_a():
            rows = main.rows()
            frame = main.pane()
            running = [b for _, b in blocks(rows, "tool_use")
                       if b.get("name") == "Bash" and main.result_of(rows, b["id"]) is None]
            for b in running:
                line = (b.get("input") or {}).get("description")
                if line and line in labels(frame) and line not in live_seen:
                    live_seen.append(line)
                    main.frames.append(("A, %s running" % line, frame))

        a_rows = main.turn(PROMPT_A, during=watch_a)
        a_ended = time.time()
        frame = main.snap("A's end")
        # 1. A live line while A waits.
        check("1 a live fold reads its newest call's line", bool(live_seen),
              "seen while running: %s; labels at the end: %s" % (live_seen or "none", labels(frame)))

        # 2 and 7. A's stretch: one run, summarized within 30 s.
        body = stretch(a_rows, "starting alpha", "alpha finished")
        a_runs, a_summary = [], None
        if body is None:
            check("2 a closed fold reads its summary", False,
                  "not exercised: haiku sent %s" % [str(b.get("input", {}).get("text"))[:40] for _, b in messages(a_rows)])
        else:
            ids = ids_of(body)

            def summarized():
                runs = [r for r in main.stored() if r[0] in ids]
                return runs if runs and summary_shown(main.pane(), runs[-1][2]) else None
            try:
                a_runs = base.wait_for("A's summary", SUMMARY_WAIT, summarized)
            except TimeoutError:
                a_runs = [r for r in main.stored() if r[0] in ids]
            frame = main.snap("A summarized")
            a_summary = a_runs[-1][2] if a_runs else None
            line_shown = [label for label in labels(frame) if label in lines_of(body)]
            check("2 a closed fold reads its summary within %d s" % SUMMARY_WAIT,
                  a_summary is not None and summary_shown(frame, a_summary) and a_summary != "working record",
                  "%.0f s after the turn's end; stored %s; labels %s; a call's line still shown: %s" % (
                      time.time() - a_ended, a_runs, labels(frame), line_shown or "none"))

            # 7. A delivery folded into the running turn, and still one fold, one summary.
            # The file keeps a prompt folded into a running turn as a `queued_command` attachment.
            delivered = [r for r in body if "<task-notification>" in json.dumps(r.get("message", {}))
                         or (r.get("attachment") or {}).get("type") == "queued_command"]
            texts = [str(b.get("input", {}).get("text")) for _, b in messages(body)]
            at, end = frame.rfind("Starting alpha"), frame.rfind("Alpha finished")
            between = labels(frame[at:end]) if 0 <= at < end else None
            if not delivered:
                check("7 a run that took a prompt mid-turn: one fold, one summary", False,
                      "not exercised: no task notification was kept inside A's stretch")
            else:
                check("7 a run that took a prompt mid-turn: one fold, one summary",
                      len(a_runs) == 1 and between is not None and len(between) == 1,
                      "%d notification(s) in the stretch; stored runs %s; folds between the messages %s; messages %s" % (
                          len(delivered), a_runs, between, texts))

        # 4a. A reload that starts the module over.
        before = len(main.logged())
        with open(os.path.join(main.dirs[0], "hooks", "mods", "folds.tsx"), "a") as f:
            f.write("\n// changed for the reload\n")
        main.send("/reload-plugins")
        base.wait_for("the reload", 120, lambda: "Reloaded" in main.logged()[before:] or "Reloaded" in main.pane())
        restarted = "session.start: raised for to-human (loaded later)" in main.logged()[before:]
        reloaded_ok = False
        if a_summary is not None:
            try:
                reloaded_ok = base.wait_for("A's summary after the reload", 20, lambda: summary_shown(main.pane(), a_summary))
            except TimeoutError:
                pass
        frame = main.snap("after the reload")
        check("4a after /reload-plugins the fold still reads its summary", bool(reloaded_ok) and restarted,
              "module started over: %s; labels %s" % (restarted, labels(frame)))

        # 3. B: a silent turn, summarized at its end.
        b_rows = main.turn(PROMPT_B)
        b_ended = time.time()
        b_runs, b_summary = [], None
        sent = messages(b_rows)
        if sent:
            check("3 a turn that ends without a message is summarized", False,
                  "not exercised: haiku sent %s" % [str(b.get("input", {}).get("text"))[:40] for _, b in sent])
        else:
            ids = ids_of(b_rows)

            def b_summarized():
                runs = [r for r in main.stored() if r[0] in ids]
                return runs if runs and summary_shown(main.pane(), runs[-1][2]) else None
            try:
                b_runs = base.wait_for("B's summary", SUMMARY_WAIT, b_summarized)
            except TimeoutError:
                b_runs = [r for r in main.stored() if r[0] in ids]
            frame = main.snap("B summarized")
            b_summary = b_runs[-1][2] if b_runs else None
            check("3 a turn that ends without a message is summarized",
                  b_summary is not None and summary_shown(frame, b_summary),
                  "%.0f s after the turn's end; stored %s; labels %s" % (time.time() - b_ended, b_runs, labels(frame)))

        # 4b. Quit right away, resume, and both summaries read again.
        main.send("/exit")
        try:
            base.wait_for("the quit", 30, lambda: not main.is_running())
        except TimeoutError:
            main.stop()
        main.resume()
        expected = [s for s in (a_summary, b_summary) if s is not None]
        resumed_ok = False
        if len(expected) == 2:
            try:
                resumed_ok = base.wait_for("the summaries after the resume", 60,
                                           lambda: all(summary_shown(main.pane(), s) for s in expected))
            except TimeoutError:
                pass
        frame = main.snap("after the resume")
        check("4b after a quit and --resume both folds read their summaries", bool(resumed_ok),
              "expected %s; labels %s" % (expected, labels(frame)))
        main.stop()
    finally:
        main.cleanup()

    # -- 5. the summary call fails
    failing = Session(keep, "failing", env={"TO_HUMAN_FOLD_MODEL": "claude-nonexistent-0-0"})
    try:
        failing.setup()
        failing.start()
        base.wait_for("the prompt", 60, lambda: "❯" in failing.pane())
        c_rows = failing.turn(PROMPT_C)
        time.sleep(15)
        frame = failing.snap("C's end")
        at, end = frame.rfind("Starting charlie"), frame.rfind("Charlie finished")
        between = labels(frame[at:end]) if 0 <= at < end else None
        failed = re.findall(r"[^\n]*to-human: a fold's summary[^\n]*", failing.logged())
        again = failing.turn(PROMPT_C2)
        went_on = any("charlie again" in str(b.get("input", {}).get("text", "")).lower() for _, b in messages(again))
        check("5 a failing summary call leaves `working record` and the session goes on",
              between == ["working record"] and bool(failed) and went_on and not failing.stored(),
              "folds between the messages %s; logged %s; next turn sent its message: %s; calls %s" % (
                  between, [line[-160:] for line in failed[:2]], went_on,
                  [b.get("name") for _, b in blocks(c_rows, "tool_use")]))
        failing.stop()
    finally:
        failing.cleanup()

    # -- 6. a session without the output style
    plain = Session(keep, "plain", style=False)
    try:
        plain.setup()
        plain.start()
        base.wait_for("the prompt", 60, lambda: "❯" in plain.pane())
        plain.turn(PROMPT_D)
        time.sleep(15)
        frame = plain.snap("D's end")
        summaries = re.findall(r"[^\n]*to-human: a fold's summary[^\n]*", plain.logged())
        folds_dir = os.path.join(plain.cfg, "to-human", "folds")
        files = os.listdir(folds_dir) if os.path.isdir(folds_dir) else []
        check("6 without the output style no summary is made and nothing folds",
              not files and not summaries and not labels(frame),
              "session files %s; summary lines in the debug log %d; fold labels %s" % (files, len(summaries), labels(frame)))
        plain.stop()
    finally:
        plain.cleanup()

    return all(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    sys.exit(0 if run(args.keep) else 1)


if __name__ == "__main__":
    main()
