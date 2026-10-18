"""Whether the installed Claude Code engine still writes and reads a session's
directory the way sminos.launch_cwd reads it (§1c of the org directory's
design): the producer stamps `{type: "relocated", sessionId, relocatedCwd}`
when it moves a session (`/cd`, EnterWorktree), and the engine's own reader
takes the tail's latest `relocated` row's `relocatedCwd`, else the head's
first `cwd`. Read from the engine binary itself — the JavaScript it runs is
plain text inside it — found as the real user's `~/.local/bin/claude`
resolved (never $HOME's, which the suites replace), or $SMINOS_ENGINE.

Prints `ok <what>` or `FAIL <what>` per check, or one `SKIP <why>` line and
exits 0 where no engine is installed (CI). Exits 1 on a failed check: the
engine changed shape, and launch_cwd would fall back to the first row's cwd
for every relocated session — sessions would stop following `/cd` and
EnterWorktree, never move to where their shell is (see launch_cwd)."""

import os
import pwd
import re
import sys

PRODUCER = re.compile(rb'\{type:"relocated",(?:sessionId:[\w$.]+,)?relocatedCwd:[\w$.]+(?:,sessionId:[\w$.]+)?\}')
READER = re.compile(rb'[\w$]+\([\w$]+\.tail,"relocated","relocatedCwd"\)\?\?[\w$]+\([\w$]+\.head,"cwd"\)')


def engine():
    path = os.environ.get("SMINOS_ENGINE") or os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".local", "bin", "claude")
    path = os.path.realpath(path)
    return path if os.path.isfile(path) else ""


def main():
    path = engine()
    if not path:
        print("SKIP no Claude Code engine installed here (~/.local/bin/claude): the relocated shape is not checked")
        return 0
    with open(path, "rb") as f:
        data = f.read()
    if b"CLAUDE_CODE_SESSION_ID" not in data:
        print("SKIP %s does not hold the engine's JavaScript as text: the relocated shape is not checked" % path)
        return 0
    failed = 0
    for what, rx in (("the engine stamps {type: \"relocated\", relocatedCwd} when it moves a session", PRODUCER),
                     ("and reads a session's directory as the tail's relocatedCwd, else the head's first cwd", READER)):
        if rx.search(data):
            print("ok %s (%s)" % (what, os.path.basename(path)))
        else:
            print("FAIL %s (%s): the engine changed shape — re-read its transcript writer and "
                  "update sminos.launch_cwd" % (what, path))
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
