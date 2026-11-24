#!/usr/bin/env python3
"""A stand-in for `claude` (tests only; test_rpcs.py puts it first on PATH):
`agents`, `stop <short>`, and a fresh `--bg` launch, each call logged, every
launch a row of `agents`. A `--bg` job is named by its session id's first 8
characters (2.1.304: one job per session). `bg-sleep` in the state directory
holds every launch that many seconds; `bg-cwd` names the directory a job's
row says it runs in (a --worktree's checkout), its own otherwise. Nothing the tests drive resumes a
session (`--bg --resume`), so the stand-in has no resume.

A `-p` call (find's model call, test_find.py and test_visibility.py; a headless
fork's too, `-p --resume`): its argv, environment, working directory,
whether its pid was marked internal ($SMINOS_HOME/internal/<pid>) and its
standard input go to `find-calls.log` (one JSON line), its standard input
to `find-prompt.txt` as well; it answers $FAKE_CLAUDE_FIND_RESULT (default:
no match) as `claude -p --output-format json` does, or by
$FAKE_CLAUDE_FIND_MODE: `crash` (exit 3, nothing on stdout), `error` (an
error result, exit 1), `sleep:<seconds>` before it answers."""
import glob
import json
import os
import sys
import time
import uuid

state = os.environ["FAKE_CLAUDE_STATE"]
os.makedirs(os.path.join(state, "agents"), exist_ok=True)
args = sys.argv[1:]
with open(os.path.join(state, "calls.log"), "a") as f:
    f.write(json.dumps(args) + "\n")


def row(short, sid, name):
    try:
        with open(os.path.join(state, "bg-cwd")) as f:
            cwd = f.read().strip()
    except OSError:
        cwd = os.getcwd()
    with open(os.path.join(state, "agents", short + ".json"), "w") as f:
        json.dump({"id": short, "sessionId": sid, "kind": "background", "name": name, "state": "working",
                   "cwd": cwd}, f)


if args[:1] == ["-p"]:
    stdin = sys.stdin.read()
    home = os.environ.get("SMINOS_HOME", "")
    with open(os.path.join(state, "find-calls.log"), "a") as f:
        f.write(json.dumps({"argv": args, "env": dict(os.environ), "cwd": os.getcwd(), "stdin": stdin,
                            "marker": os.path.exists(os.path.join(home, "internal", str(os.getpid())))}) + "\n")
    with open(os.path.join(state, "find-prompt.txt"), "w") as f:
        f.write(stdin)
    mode = os.environ.get("FAKE_CLAUDE_FIND_MODE", "")
    if mode.startswith("sleep:"):
        time.sleep(float(mode[len("sleep:"):]))
    if mode == "crash":
        sys.stderr.write("fake: the engine crashed\n")
        sys.exit(3)
    print(json.dumps({"type": "result", "is_error": mode == "error",
                      "result": os.environ.get("FAKE_CLAUDE_FIND_RESULT", '{"matches": [], "note": ""}'),
                      "session_id": args[args.index("--session-id") + 1] if "--session-id" in args else "",
                      "usage": {"input_tokens": 9, "output_tokens": 3}}))
    sys.exit(1 if mode == "error" else 0)
if args[:1] == ["agents"]:
    rows = []
    for p in sorted(glob.glob(os.path.join(state, "agents", "*.json"))):
        with open(p) as f:
            rows.append(json.load(f))
    print(json.dumps(rows))
    sys.exit(0)
if args[:1] == ["stop"]:
    p = os.path.join(state, "agents", args[1] + ".json")
    if os.path.exists(p):
        with open(p) as f:
            r = json.load(f)
        r["state"] = "stopped"
        with open(p, "w") as f:
            json.dump(r, f)
    print("stopped " + args[1])
    sys.exit(0)
if "--bg" in args:
    try:
        with open(os.path.join(state, "bg-sleep")) as f:
            time.sleep(float(f.read()))
    except (OSError, ValueError):
        pass
    new = str(uuid.uuid4())
    short = new[:8]
    name = args[args.index("-n") + 1]
    row(short, new, name)
    print("backgrounded · %s · %s" % (short, name))
    sys.exit(0)
sys.exit(0)
