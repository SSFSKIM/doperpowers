#!/usr/bin/env python3
"""Live check that to-human survives a reload in a long session.

A module that starts over in a running session (an update the autoreload
applied, a `/reload-plugins`) reads the session's whole transcript before its
first answer, and the engine asks it about every row at once. On 2026-10-20
the reads ran 6 to 10 s on transcripts of 207 to 437 MB; the draws that
waited on them ran past the engine's fixed 10 s budget, deaf to their
signal, and the engine ended the hooks worker and unloaded the plugin
("to-human was unloaded: it crashed the hooks worker"), in three sessions at
once. This resumes a copy of a long transcript the caller names, fullscreen,
changes the module and types `/reload-plugins` (a reload keeps a module
whose files did not change), and passes when
neither the resume (whose first load reads the same way) nor the reload
leaves a to-human hook skipped, an overrun or an unload in the debug log.

It spends no model calls: nothing is sent to the model, and the session
holds a token that reaches no server. Everything it starts is isolated: a
temporary HOME whose .claude is the session's config dir, a temporary
SMINOS_HOME, copies of the to-human folder under test (the worktree's
unless --to-human names another, such as an installed version as a control)
and of the worktree's sminos (to-human depends on it), loaded with
--plugin-dir, and a tmux server of its own. The transcript's copy is
removed at the end; with --keep the directory stays, holding the frames and
the debug log.

    to-human/tests/mods/live-reload-check.py --transcript <path.jsonl> [--to-human <dir>] [--keep]
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
BASE_KEYS = ("PATH", "TERM", "LANG", "USER", "LOGNAME", "SHELL", "TMPDIR")
PARTS = (".claude-plugin", "hooks", "skills", "types")
# What the engine logs when it gives up on one of to-human's hooks, or on the plugin.
LOGGED = re.compile(r"[^\n]*(hook failed: to-human|hook overran: to-human|ignored its signal|crashed the hooks worker|hooks worker: [^\n]*respawning)[^\n]*")


def wait_for(what, seconds, fn, every=0.5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))


class Live:
    def __init__(self, args):
        self.args = args
        self.root = tempfile.mkdtemp(prefix="threload.", dir="/tmp")
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.home, ".claude")
        self.work = os.path.join(self.root, "work")
        self.log = os.path.join(self.root, "debug.log")
        self.tmux = ["tmux", "-L", "threload-%d" % os.getpid(), "-f", "/dev/null"]
        self.session = str(uuid.uuid4())
        self.dirs = []

    def setup(self):
        os.makedirs(self.cfg)
        os.makedirs(self.work)
        os.makedirs(os.path.join(self.root, "s"), mode=0o700)
        for name, source in (("to-human", self.args.to_human), ("sminos", os.path.join(REPO, "sminos"))):
            dest = os.path.join(self.root, name)
            for part in PARTS:
                if os.path.isdir(os.path.join(source, part)):
                    shutil.copytree(os.path.join(source, part), os.path.join(dest, part),
                                    ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
            self.dirs.append(dest)
        trusted = {"hasTrustDialogAccepted": True}
        with open(os.path.join(self.cfg, ".claude.json"), "w") as f:
            json.dump({"hasCompletedOnboarding": True,
                       "projects": {self.work: trusted, os.path.realpath(self.work): trusted}}, f)
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump({"tui": "fullscreen"}, f)
        # The copy, under the work directory's project, every row its session's.
        project = os.path.join(self.cfg, "projects", re.sub(r"[^a-zA-Z0-9]", "-", os.path.realpath(self.work)))
        os.makedirs(project)
        with open(self.args.transcript, "rb") as src, open(os.path.join(project, self.session + ".jsonl"), "wb") as dst:
            for line in src:
                dst.write(re.sub(rb'"sessionId":"[^"]*"', b'"sessionId":"%s"' % self.session.encode(), line))
        size = os.path.getsize(os.path.join(project, self.session + ".jsonl"))
        print("transcript: %.0f MB, a copy of %s" % (size / 1e6, self.args.transcript))

    def start(self):
        env = {k: os.environ[k] for k in BASE_KEYS if k in os.environ}
        env.update(HOME=self.home, SMINOS_HOME=os.path.join(self.root, "s"), CLAUDE_CONFIG_DIR=self.cfg,
                   CLAUDE_CODE_ENABLE_FUNCTION_HOOKS="1", ANTHROPIC_BASE_URL="http://127.0.0.1:9",
                   ANTHROPIC_AUTH_TOKEN="reaches-no-server")
        exports = "; ".join("export %s=%s" % (k, shlex.quote(v)) for k, v in sorted(env.items()))
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.dirs)
        inner = "%s; cd %s; exec claude %s --debug-file %s --resume %s" % (
            exports, shlex.quote(self.work), dirs, shlex.quote(self.log), self.session)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "t", "-x", "160", "-y", "45",
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)

    def stop(self):
        subprocess.run(self.tmux + ["kill-server"], capture_output=True)
        time.sleep(1)

    def pane(self):
        return subprocess.run(self.tmux + ["capture-pane", "-p", "-t", "t", "-S", "-"],
                              capture_output=True, text=True).stdout

    def keys(self, *keys):
        subprocess.run(self.tmux + ["send-keys", "-t", "t"] + list(keys), check=True)

    def logged(self):
        return open(self.log, errors="replace").read() if os.path.exists(self.log) else ""

    def run(self):
        self.setup()
        self.start()
        started = time.time()
        wait_for("to-human to load", 300, lambda: re.search(r"hooks module to-human[^\n]* loaded", self.logged()))
        time.sleep(self.args.settle)
        print("resumed, and watched %.0f s" % (time.time() - started))
        before = len(self.logged())
        # A reload keeps a module whose files did not change: this one starts
        # over, as an update would have it.
        with open(os.path.join(self.dirs[0], "hooks", "mods", "to-human.tsx"), "a") as f:
            f.write("\n// changed for the reload\n")
        self.keys("-l", "/reload-plugins")
        time.sleep(0.5)
        self.keys("Enter")
        wait_for("the reload", 120, lambda: "Reloaded" in self.logged()[before:] or "Reloaded" in self.pane())
        reloaded = time.time()
        time.sleep(self.args.watch)
        frame = self.pane()
        with open(os.path.join(self.root, "frame.txt"), "w") as f:
            f.write(frame)
        whole = self.logged()
        print("watched %.0f s after the reload" % (time.time() - reloaded))
        # The screen is not read: a resumed history draws the notices its own
        # session was shown, the engine's failures of this kind among them.
        restarted = "session.start: raised for to-human (loaded later)" in whole[before:]
        print("%s  the reload starts to-human over" % ("PASS" if restarted else "FAIL"))
        ok = restarted
        for phase, text in (("the resume", whole[:before]), ("the reload", whole[before:])):
            logged = [m.group(0) for m in LOGGED.finditer(text)]
            for line in logged[:10]:
                print("  log, %s: %s" % (phase, line[:240]))
            ok = ok and not logged
        print("%s  the resume and the reload leave to-human loaded, no hook of it skipped" % ("PASS" if ok else "FAIL"))
        return ok

    def cleanup(self):
        self.stop()
        if self.args.keep:
            for path in glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl")):
                os.unlink(path)
            print("kept (the transcript's copy removed): %s" % self.root)
        else:
            shutil.rmtree(self.root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--transcript", required=True, help="a long session's transcript, copied and resumed")
    parser.add_argument("--to-human", default=os.path.join(REPO, "to-human"), help="the to-human folder to load")
    parser.add_argument("--settle", type=float, default=45, help="seconds to watch the resume before the reload")
    parser.add_argument("--watch", type=float, default=45, help="seconds to watch after the reload")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(1))
    live = Live(args)
    try:
        ok = live.run()
    finally:
        live.cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
