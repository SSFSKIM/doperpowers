#!/usr/bin/env python3
"""The stand-in sminos CLI, in a stand-in doperpowers marketplace clone: what
devcloud relies on, and nothing else (Python 3.9 compatible: a Mac's
/usr/bin/python3 runs it in the unit tests).

  daemon install    writes the systemd user unit as the real one does
  daemon run        the unit's program: records its environment and waits;
                    on SIGTERM (the daemon's stop) records that and exits
  hub check         exits with the next code of `check.exit` (I15: 0 accepted,
                    1 not enrolled here, 3 rejected, 4 undecided, 2 usage);
                    1 when the file is absent and no hub.json exists, else 0
  hub enroll --name <name> [--replace]
                    reads the code from stdin (never from argv) and exits with
                    the next line of `enroll.exit` ("<code> [stderr line]"),
                    0 when absent; on 0 writes hub.json. The call is recorded
                    with its argv and a digest of what stdin held, never the
                    value itself
  hub leave         exits with `leave.exit` (0 when absent); on 0 removes hub.json
  say <text>        records the text
  spawn <alias> <prompt>
                    launches a stand-in `claude` process directly, as the real
                    spawn does without the daemon

Every call is one JSON line in `calls.jsonl`. State lives in $FAKE_SMINOS_STATE,
else ~/.local/state/devcloud-test."""
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

home = pathlib.Path.home()
state = pathlib.Path(os.environ.get("FAKE_SMINOS_STATE") or home / ".local/state/devcloud-test")
sminos_home = pathlib.Path(os.environ.get("SMINOS_HOME") or home / ".claude/sminos")
hub_json = sminos_home / "daemon/hub.json"
args = sys.argv[1:]


def record(**fields):
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "calls.jsonl", "a") as log:
        log.write(json.dumps(dict(argv=args, **fields)) + "\n")


def next_line(name, default):
    """The first line of `name` in the state directory, consumed; `default`
    when the file is absent or spent."""
    path = state / name
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return default
    if not lines:
        return default
    path.write_text("".join(line + "\n" for line in lines[1:]))
    return lines[0]


def exit_with(line):
    code, _, message = line.partition(" ")
    if message:
        print(message, file=sys.stderr)
    sys.exit(int(code))


if args == ["daemon", "install"]:
    config = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    unit = pathlib.Path(config) / "systemd/user/sminos-daemon.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text("[Unit]\nDescription=stand-in sminos daemon\n\n[Service]\n"
                    f"ExecStart={sys.executable} {os.path.realpath(__file__)} daemon run\nRestart=always\n"
                    f'Environment="PATH={os.environ.get("PATH", "")}"\n\n[Install]\nWantedBy=default.target\n')
    unit.chmod(0o600)
    print(f"wrote {unit}")
elif args == ["daemon", "run"]:
    state.mkdir(parents=True, exist_ok=True)

    def stopped(*_):
        with open(state / "sminos-daemon.log", "a") as log:
            log.write(f"stop {os.getpid()}\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, stopped)
    keys = ("SESSION_MIRROR_HOST", "DEVCLOUD_PROBE_PROFILE", "PATH")
    (state / "sminos.json").write_text(json.dumps({**{k: os.environ.get(k) for k in keys}, "pid": os.getpid()}))
    with open(state / "sminos-daemon.log", "a") as log:
        log.write(f"start {os.getpid()}\n")
    while True:
        time.sleep(60)
elif args == ["hub", "check"]:
    record()
    exit_with(next_line("check.exit", "0" if hub_json.is_file() else "1"))
elif args[:2] == ["hub", "enroll"]:
    if args[2:3] != ["--name"] or len(args) not in (4, 5) or (len(args) == 5 and args[4] != "--replace"):
        record(error="usage")
        exit_with("2 sminos: usage: hub enroll --name <name> [--replace]")
    code = sys.stdin.read().strip()
    record(stdin_sha256=hashlib.sha256(code.encode()).hexdigest() if code else None)
    line = next_line("enroll.exit", "0")
    if line.split()[0] == "0":
        hub_json.parent.mkdir(parents=True, exist_ok=True)
        hub_json.write_text(json.dumps({"machine": args[3], "enrolled": time.time()}) + "\n")
    exit_with(line)
elif args == ["hub", "leave"]:
    record()
    line = next_line("leave.exit", "0")
    if line.split()[0] == "0":
        hub_json.unlink(missing_ok=True)
    exit_with(line)
elif args[:1] == ["say"] and len(args) == 2:
    record()
elif args[:1] == ["spawn"] and len(args) >= 3:
    record()
    claude = pathlib.Path(os.environ.get("FAKE_CLAUDE") or pathlib.Path(__file__).with_name("claude"))
    child = subprocess.Popen([str(claude), "-p", args[2]], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"spawned {args[1]} (pid {child.pid})")
else:
    sys.exit(f"stand-in sminos: {' '.join(args)} is not played here")
