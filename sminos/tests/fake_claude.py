#!/usr/bin/env python3
"""A stand-in for `claude` (tests only; test_rpcs.py puts it first on PATH):
`agents`, `stop <short>`, and a fresh `--bg` launch, each call logged, every
launch a row of `agents`. A `--bg` job is named by its session id's first 8
characters (2.1.304: one job per session). `bg-sleep` in the state directory
holds every launch that many seconds. Nothing the tests drive resumes a
session (`--bg --resume`), so the stand-in has no resume."""
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
    with open(os.path.join(state, "agents", short + ".json"), "w") as f:
        json.dump({"id": short, "sessionId": sid, "kind": "background", "name": name, "state": "working",
                   "cwd": os.getcwd()}, f)


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
