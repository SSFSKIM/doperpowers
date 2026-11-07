#!/usr/bin/env python3
"""The stand-in sminos CLI, in a stand-in doperpowers marketplace clone: what
devcloud relies on, and nothing else (Python 3.9 compatible: a Mac's
/usr/bin/python3 runs it in the unit tests).

  daemon install    writes the systemd user unit as the real one does
  daemon run        the unit's program: records its environment and waits;
                    on SIGTERM (the daemon's stop) records that and exits
  say <text>        records the text
  spawn <alias> <prompt>
                    launches a stand-in `claude` process directly, as the real
                    spawn does without the daemon

Anything else, a `hub` verb among them (devcloud enrolls nothing at the hub:
a machine's enrollment is its MAWS endpoint's), is recorded and exits 2.

Every call but the daemon's is one JSON line in `calls.jsonl`. State lives in
$FAKE_SMINOS_STATE, else ~/.local/state/devcloud-test."""
import fcntl
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
args = sys.argv[1:]


def record(**fields):
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "calls.jsonl", "a") as log:
        log.write(json.dumps(dict(argv=args, **fields)) + "\n")


def exit_with(line):
    code, _, message = line.partition(" ")
    if message:
        print(message, file=sys.stderr)
    sys.exit(int(code))


if args == ["daemon", "install"]:
    config = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    unit = pathlib.Path(config) / "systemd/user/sminos-daemon.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    sminos_home.mkdir(parents=True, exist_ok=True)
    unit.write_text("[Unit]\nDescription=stand-in sminos daemon\n\n[Service]\n"
                    f'ExecStart="{sys.executable}" "{os.path.realpath(__file__)}" daemon run\nRestart=always\n'
                    'KillMode=process\n'
                    f'StandardOutput=append:{sminos_home}/daemon.out\n'
                    f'StandardError=append:{sminos_home}/daemon.out\n'
                    f'Environment="PATH={os.environ.get("PATH", "")}"\n\n[Install]\nWantedBy=default.target\n')
    unit.chmod(0o600)
    print(f"wrote {unit}")
elif args == ["daemon", "run"]:
    state.mkdir(parents=True, exist_ok=True)
    # A surviving daemon must block a replacement, just as the real lock does.
    daemon_lock = open(state / "sminos-daemon.lock", "a")
    fcntl.flock(daemon_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def stopped(*_):
        if (state / "sminos-ignore-term").exists():
            return
        with open(state / "sminos-daemon.log", "a") as log:
            log.write(f"stop {os.getpid()}\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, stopped)
    keys = ("SESSION_MIRROR_HOST", "DEVCLOUD_PROBE_PROFILE", "PATH")
    (state / "sminos.json").write_text(json.dumps({**{k: os.environ.get(k) for k in keys}, "pid": os.getpid()}))
    with open(state / "sminos-daemon.log", "a") as log:
        log.write(f"start {os.getpid()}\n")
    # Made-up host values: prove the real user-unit wrapper learns both the
    # environment and file-only materializations before persisting output.
    if os.environ.get("EXAMPLE_API_KEY"):
        print("daemon stdout value", os.environ["EXAMPLE_API_KEY"], flush=True)
    if (home / ".pgpass").is_file():
        print("daemon stderr value", (home / ".pgpass").read_text().strip(), file=sys.stderr, flush=True)
    while True:
        time.sleep(60)
elif args[:1] == ["say"] and len(args) == 2:
    record()
elif args[:1] == ["spawn"] and len(args) >= 3:
    record()
    claude = pathlib.Path(os.environ.get("FAKE_CLAUDE") or pathlib.Path(__file__).with_name("claude"))
    child = subprocess.Popen([str(claude), "-p", args[2]], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"spawned {args[1]} (pid {child.pid})")
else:
    record(error="not played")
    exit_with(f"2 stand-in sminos: {' '.join(args)} is not played here")
