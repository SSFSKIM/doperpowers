#!/usr/bin/env python3
"""A stand-in for `claude` (tests only; test_rpcs.py puts it first on PATH):
`agents`, `stop <short>`, and a `--bg` launch, each call logged, every launch
a row of `agents`.

`--bg --resume <id>` does what the engine does with a session's full id
(2.1.300's resume planner): it continues the session under its own id,
unless a process of this machine holds it, or a flag rides along, when it
starts a copy under a new id and says so in the engine's words. A session it
runs is a process of its own (fake_holder.py) that the engine's record
names, kind `bg`, with an inbox socket whose frames it keeps; `stop` ends
it. `reopen-first` in the state directory makes the owner reopen the session
(a terminal process holding it) just before the engine looks, as a reopen
racing the launch does; `bg-sleep` holds every launch that many seconds."""
import glob
import json
import os
import subprocess
import sys
import time
import uuid

state = os.environ["FAKE_CLAUDE_STATE"]
os.makedirs(os.path.join(state, "agents"), exist_ok=True)
args = sys.argv[1:]
with open(os.path.join(state, "calls.log"), "a") as f:
    f.write(json.dumps(args) + "\n")
sessions = os.path.join(os.environ["HOME"], ".claude", "sessions")
HOLDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fake_holder.py")


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def hold(sid, kind, short=""):
    """A process holding the session, as the engine records it."""
    inbox = os.path.join(state, "in-%s-%s.sock" % (kind[:2], sid[:8]))
    p = subprocess.Popen([sys.executable, HOLDER, inbox, os.path.join(state, "inbox-%s.log" % sid)],
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    for _ in range(500):
        if os.path.exists(inbox):
            break
        time.sleep(0.02)
    rec = {"pid": p.pid, "sessionId": sid, "cwd": os.getcwd(), "kind": kind, "status": "idle",
           "name": "held-" + sid[:4], "messagingSocketPath": inbox}
    if short:
        rec["jobId"] = short
    with open(os.path.join(sessions, "%d.json" % p.pid), "w") as f:
        json.dump(rec, f)
    with open(os.path.join(state, "holders"), "a") as f:
        f.write("%d %s %s\n" % (p.pid, sid, short or "-"))


def held(sid):
    for path in glob.glob(os.path.join(sessions, "*.json")):
        try:
            with open(path) as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if rec.get("sessionId") == sid and alive(rec.get("pid")):
            return True
    return False


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
    try:
        with open(os.path.join(state, "holders")) as f:
            holders = [line.split() for line in f if line.strip()]
    except OSError:
        holders = []
    for pid, _sid, short in holders:
        if short == args[1]:
            try:
                os.kill(int(pid), 15)
            except OSError:
                pass
            try:
                os.unlink(os.path.join(sessions, "%s.json" % pid))
            except OSError:
                pass
    print("stopped " + args[1])
    sys.exit(0)
if "--bg" in args:
    try:
        with open(os.path.join(state, "bg-sleep")) as f:
            time.sleep(float(f.read()))
    except (OSError, ValueError):
        pass
    if "--resume" in args:
        sid = args[args.index("--resume") + 1]
        with open(os.path.join(state, "resumes.log"), "a") as f:
            f.write(json.dumps({"args": args, "cwd": os.getcwd()}) + "\n")
        reopen = os.path.join(state, "reopen-first")
        if os.path.exists(reopen):
            os.unlink(reopen)
            hold(sid, "interactive")
        note = ""
        if held(sid):
            note = "note: session %s is open in another Claude Code process, so this started a copy as %s. " \
                   "The original conversation is unchanged."
        elif args != ["--bg", "--resume", sid]:
            note = "note: background session %s keeps its own saved options, so the flags you passed started a " \
                   "copy as %s. Without flags, the same command continues it itself."
        new = str(uuid.uuid4()) if note else sid
        short = new[:8]
        hold(new, "bg", short)
        row(short, new, "resumed")
        print("backgrounded · %s · resumed" % short)
        if note:
            print(note % (sid[:8], short))
        sys.exit(0)
    short = os.urandom(4).hex()
    name = args[args.index("-n") + 1]
    row(short, str(uuid.uuid4()), name)
    print("backgrounded · %s · %s" % (short, name))
    sys.exit(0)
sys.exit(0)
