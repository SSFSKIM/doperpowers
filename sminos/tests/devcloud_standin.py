#!/usr/bin/env python3
"""A stand-in for devcloud's CLI, `devcloud vm owned-by <short>...` (T1's M5;
contract X9), so that no test reaches a real devcloud driver: the suite's
shared setup points SMINOS_DEVCLOUD here (run-sminos-tests.sh, and
test_threads.py for the Python files that build on it).

It answers as the test sets it in $HOME/devcloud-standin.json (HOME is each
test's own), and with none when there is no such file:

  hosts        hosts as devcloud lists them ({name, account, provider,
               creator}); those whose creator is `@` and a short id asked
               about are the answer's `vms`, as the driver matches
  unknown      devcloud's `unknown` entries
  stdout       printed instead of the answer built from the two above
  stderr       printed to stderr
  exit         the exit code (0)
  gate         a path: no answer until it exists
  hang         never answer
  ignore_term  SIGTERM ignored
  child        start a child of its own (`sleep`) in a session of its own

Each call appends a line to $HOME/devcloud-standin.calls: its arguments, its
pid, the PATH it was given, and its child's pid."""
import json
import os
import signal
import subprocess
import sys
import time

home = os.environ.get("HOME") or "/nonexistent"
try:
    with open(os.path.join(home, "devcloud-standin.json")) as f:
        cfg = json.load(f)
except (OSError, ValueError):
    cfg = {}
if cfg.get("ignore_term"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen(["sleep", "600"], start_new_session=True).pid if cfg.get("child") else None
with open(os.path.join(home, "devcloud-standin.calls"), "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "pid": os.getpid(), "path": os.environ.get("PATH", ""),
                        "child": child}) + "\n")
if sys.argv[1:3] != ["vm", "owned-by"] or len(sys.argv) < 4:
    sys.stderr.write("devcloud stand-in: only vm owned-by <short>...\n")
    sys.exit(2)
while cfg.get("gate") and not os.path.exists(cfg["gate"]):
    time.sleep(0.05)
while cfg.get("hang"):
    time.sleep(1)
if "stdout" in cfg:
    sys.stdout.write(cfg["stdout"])
else:
    names = {"@" + n for n in sys.argv[3:]}
    vms = [h for h in cfg.get("hosts", []) if h.get("creator") in names]
    unknown = cfg.get("unknown", [])
    print(json.dumps({"answer": "owned" if vms else "unknown" if unknown else "none", "vms": vms,
                      "unknown": unknown, "listed": ["main"]}))
sys.stderr.write(cfg.get("stderr", ""))
sys.exit(cfg.get("exit", 0))
