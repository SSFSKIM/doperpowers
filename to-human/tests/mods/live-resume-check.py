#!/usr/bin/env python3
"""Live check of how a resumed session's marked history draws (board #105).

What only a running engine shows, pinned so a release that changes it is
seen. On a `claude --resume` start the engine draws the resumed transcript
in its first frame, before the plugins' hooks modules load (about 0.2 to
1 s later), so that frame is the engine's own drawing: `⏺ <message>…`. Once
the module loads, the engine asks to-human about every mounted row and the
view folds them all from its first answer (the history's own marks turn it
on; nothing new is needed). Where the frame is redrawn, that is the end of
it. Where it is not, it is not:
- fullscreen (`tui: "fullscreen"`, the alternate screen): the whole history
  draws folded, to its first row;
- the main screen (the default): the rows on the screen fold, but the rows
  the first frame pushed past the screen's top sit in the terminal's
  scrollback, which the engine never writes again (it ignores a change
  above the screen, and its full reset clears and repaints the screen's rows
  alone); they stay raw for good, a new marked message included.
No hook can reach the scrollback, so this is the engine's to change: load
the modules before the first transcript frame, or hold a row a module that
has not loaded yet will draw, as it holds a hooked row whose answer is
pending. The main-screen check fails, saying so, the day the scrollback
comes out folded.

It spends model calls (haiku, two short prompts), so no suite runs it: run
it by hand with the model gateway's keys in the environment. Everything it
starts is isolated: a temporary HOME whose .claude is the session's config
dir, a temporary SMINOS_HOME, copies of the worktree's to-human and sminos
plugins (to-human depends on sminos) loaded with --plugin-dir, a tmux server
of its own; the gateway keys reach the session through a 0600 env file in
the temporary directory, removed at the end whatever happens. With --keep
the directory stays (minus the env file), holding the frames and the debug
logs.

    to-human/tests/mods/live-resume-check.py [--keep]
"""

import datetime
import glob
import json
import os
import shlex
import shutil
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
RAW = "⏺ <message>"
LABEL = "● message"
# The long message runs past a 30-row screen, the short one ends the history.
LONG = ("Reply with one <message> block whose body is the numbers 1 to 60, one per line, then the word "
        "endlong on its own line, and nothing outside the block.")
SHORT = "Reply with exactly this and nothing else: <message>got it short</message>"


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def wait_for(what, seconds, fn, every=0.2):
    deadline = time.time() + seconds
    while time.time() < deadline:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError("timed out after %ss waiting for %s" % (seconds, what))


class Live:
    def __init__(self, keep):
        self.keep = keep
        self.root = tempfile.mkdtemp(prefix="threl.", dir="/tmp")
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.home, ".claude")
        self.work = os.path.join(self.root, "work")
        self.envfile = os.path.join(self.root, "env")
        self.tmux = ["tmux", "-L", "threl-%d" % os.getpid(), "-f", "/dev/null"]
        self.session = str(uuid.uuid4())
        self.dirs = []
        self.results = []

    def setup(self):
        missing = [k for k in GATEWAY_KEYS if k not in os.environ]
        if missing:
            sys.exit("live-resume-check: the gateway keys are not in the environment: %s" % ", ".join(missing))
        os.makedirs(self.cfg)
        os.makedirs(self.work)
        os.makedirs(os.path.join(self.root, "s"), mode=0o700)
        for name, parts in PLUGINS.items():
            dest = os.path.join(self.root, name)
            for part in parts:
                shutil.copytree(os.path.join(REPO, name, part), os.path.join(dest, part),
                                ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
            self.dirs.append(dest)
        trusted = {"hasTrustDialogAccepted": True}
        with open(os.path.join(self.cfg, ".claude.json"), "w") as f:
            json.dump({"hasCompletedOnboarding": True,
                       "projects": {self.work: trusted, os.path.realpath(self.work): trusted}}, f)
        env = {k: os.environ[k] for k in BASE_KEYS if k in os.environ}
        env.update(HOME=self.home, SMINOS_HOME=os.path.join(self.root, "s"), CLAUDE_CONFIG_DIR=self.cfg,
                   CLAUDE_CODE_ENABLE_FUNCTION_HOOKS="1")
        env.update({k: os.environ[k] for k in GATEWAY_KEYS})
        fd = os.open(self.envfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            for k, v in sorted(env.items()):
                f.write("export %s=%s\n" % (k, shlex.quote(v)))

    def settings(self, values):
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            json.dump(values, f)

    def start(self, args, rows):
        dirs = " ".join("--plugin-dir %s" % shlex.quote(d) for d in self.dirs)
        inner = "set -e; . %s; cd %s; exec claude %s --model haiku %s" % (
            shlex.quote(self.envfile), shlex.quote(self.work), dirs, args)
        subprocess.run(self.tmux + ["new-session", "-d", "-s", "t", "-x", "160", "-y", str(rows),
                                    "env -i /bin/bash --noprofile --norc -c %s" % shlex.quote(inner)], check=True)

    def stop(self):
        subprocess.run(self.tmux + ["kill-server"], capture_output=True)
        time.sleep(1)

    def pane(self):
        """The pane and its whole scrollback."""
        return subprocess.run(self.tmux + ["capture-pane", "-p", "-t", "t", "-S", "-"],
                              capture_output=True, text=True).stdout

    def keys(self, *keys):
        subprocess.run(self.tmux + ["send-keys", "-t", "t"] + list(keys), check=True)

    def check(self, name, ok, detail):
        self.results.append((name, ok))
        print("%s  %s: %s" % ("PASS" if ok else "FAIL", name, detail))

    def transcript(self):
        found = glob.glob(os.path.join(self.cfg, "projects", "*", self.session + ".jsonl"))
        return found[0] if found else None

    def assistant_rows(self):
        """The transcript's assistant text rows: (uuid, text)."""
        path = self.transcript()
        rows = []
        for line in open(path) if path else []:
            row = json.loads(line)
            content = row.get("message", {}).get("content") if row.get("type") == "assistant" else None
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "text":
                    rows.append((row["uuid"], block["text"]))
        return rows

    def save(self, name, text):
        with open(os.path.join(self.root, name), "w") as f:
            f.write(text)

    # -- the history: two marked messages, the first past the screen's height

    def make_history(self):
        self.settings({})
        self.start("--session-id %s" % self.session, 50)
        wait_for("the prompt", 30, lambda: "❯" in self.pane())
        for prompt, marker in ((LONG, "endlong"), (SHORT, "got it short")):
            self.keys("-l", prompt)
            time.sleep(0.5)
            self.keys("Enter")
            wait_for("the reply carrying %r" % marker, 120,
                     lambda: any(marker in text for _, text in self.assistant_rows()))
            time.sleep(2)
        self.stop()
        rows = self.assistant_rows()
        self.long_id = next(u for u, text in rows if "endlong" in text)

    # -- a resumed start, its frames sampled until it settles

    def resume(self, tag, settings, rows):
        self.settings(settings)
        log = os.path.join(self.root, "debug-%s.log" % tag)
        self.start("--debug-file %s --resume %s" % (shlex.quote(log), self.session), rows)
        first_raw = None
        start = time.time()
        while time.time() - start < 10:
            if first_raw is None and RAW in self.pane():
                first_raw = now()
            time.sleep(0.02)
        loaded = None
        asked = False
        for line in open(log):
            if loaded is None and "hooks module to-human" in line and " loaded " in line:
                loaded = datetime.datetime.fromisoformat(line[:24].replace("Z", "+00:00"))
            asked = asked or ("ui.render settled" in line and "to-human" in line and "key=" + self.long_id in line)
        return first_raw, loaded, asked

    def run(self):
        self.setup()
        self.make_history()

        # Main screen, 30 rows: the long message runs past the screen's top.
        first_raw, loaded, asked = self.resume("main", {}, 30)
        frame = self.pane()
        self.save("frame-main.txt", frame)
        self.check("main: the first frame draws before the module loads", first_raw is not None and loaded is not None
                   and first_raw < loaded, "raw at %s, to-human loaded at %s" % (first_raw, loaded))
        self.check("main: the module is asked about the long message's row", asked, "key=%s" % self.long_id)
        self.check("main: the history's marks turn the view on", "to-human view ·" in frame, "the band above the prompt")
        tail = frame[frame.rfind("got it short") - 200:]
        self.check("main: the rows on the screen fold", "⏺ <message>got it short" not in frame and LABEL in tail,
                   "the short message draws under its label")
        head = frame[:frame.find("got it short")]  # the short prompt follows the long reply
        self.check("main: the scrollback keeps the first frame (the engine's, board #105)", RAW in head,
                   "raw head in scrollback" if RAW in head else
                   "CHANGED: the scrollback came out folded; the engine now repaints it or loads the modules first,"
                   " so #105 can close and this check change")
        self.stop()

        # Fullscreen: the alternate screen is repainted whole; page to the top.
        self.resume("fullscreen", {"tui": "fullscreen"}, 30)
        for _ in range(8):
            self.keys("PageUp")
            time.sleep(0.5)
        frame = self.pane()
        self.save("frame-fullscreen-top.txt", frame)
        self.check("fullscreen: the long message's head draws folded", LABEL in frame and RAW not in frame,
                   "top of the history")
        self.stop()
        return all(ok for _, ok in self.results)

    def cleanup(self):
        self.stop()
        if os.path.exists(self.envfile):
            os.unlink(self.envfile)
        if self.keep:
            print("kept: %s" % self.root)
        else:
            shutil.rmtree(self.root, ignore_errors=True)


def main():
    live = Live("--keep" in sys.argv[1:])
    try:
        ok = live.run()
    finally:
        live.cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
