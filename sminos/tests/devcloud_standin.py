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

Two more verbs, for `sminos spawn --on` (EN.G1's plan, §11), set in the same
file:

  up           `vm up …`: {lines: what it prints (by default a whole up's:
               the account and caps lines, `created`, `<name>  ready in
               0m01s` and the five lines after it), name (dc-x-0001),
               stderr, exit (0), gate (a path: no answer until it exists),
               creator (the short id devcloud reads: `--expect-creator`
               naming another is refused as devcloud refuses it, and
               null is no creating session read), said and hold (after
               its lines, a path touched, and no exit until another
               exists)}
  sminos       the launcher that stands for `sminos` at the head of a line
               `vm ssh` runs
  ssh_hosts    `vm ssh <name> -- <words>`: {name: {env, exit, stdout, said,
               hold}}; said and hold, before anything: a path touched, and
               no going on until another exists.
               The words are joined as devcloud joins them (shlex.join)
               and run with /bin/sh -c, standard input passed on, under
               the host's `env` (HOME, SMINOS_HOME, DAEMON_HOST and PATH
               each required, one lacking exit 2 with nothing run; any
               more) and none of this process's session variables; `stdout`,
               when set, is printed in place of what the line printed.
               With `exit`, or with no `env`, nothing is run: `stdout` is
               printed and `exit` (0) answered (2: a copy that predates the
               call; 255: a host that does not answer). Any other name:
               devcloud's `no VM named`, exit 1.

Each call appends a line to $HOME/devcloud-standin.calls: its arguments, its
pid, the PATH it was given, and its child's pid."""
import json
import os
import shlex
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


HOST_ENV = ("HOME", "SMINOS_HOME", "DAEMON_HOST", "PATH")


def held(d):
    if d.get("said"):
        open(d["said"], "w").close()
    while d.get("hold") and not os.path.exists(d["hold"]):
        time.sleep(0.05)


def up(argv):
    u = cfg.get("up") or {}
    name = u.get("name", "dc-x-0001")
    while u.get("gate") and not os.path.exists(u["gate"]):
        time.sleep(0.05)
    # As devcloud's parser reads it: `--expect-creator=<short>`, or the flag and its value as two words.
    given = [w.split("=", 1)[1] for w in argv if w.startswith("--expect-creator=")] + \
        [argv[i + 1] for i, w in enumerate(argv[:-1]) if w == "--expect-creator"]
    if given and "creator" in u:
        expected = given[-1]
        if u["creator"] is None:
            sys.stderr.write("devcloud vm: --expect-creator: the caller expects @%s as this host's creator, and "
                             "devcloud read no creating session here (sminos who --session gave it no address it "
                             "reads): nothing was made\n" % expected)
            sys.exit(1)
        if expected != u["creator"]:
            sys.stderr.write("devcloud vm: --expect-creator: the caller expects @%s as this host's creator, and "
                             "devcloud read @%s: nothing was made\n" % (expected, u["creator"]))
            sys.exit(1)
    lines = u["lines"] if "lines" in u else [
        "account   main (fake)  location fsn1  type medium (4 vCPU, 8 GB, 160 GB disk)  lifetime keep  price 0.1 EUR/h",
        "caps      unconfirmed 0/3 ok, size 4/8 vCPU ok, disk 160/200 GB ok",
        "created   %s (id 1) from base, slow path" % name,
        "%s  ready in 0m01s" % name,
        "  provider  fake  location fsn1  type medium", "  tailnet   %s" % name, "  lease     none (keep)",
        "  price     0.1 EUR/h", "  image     built from base, slow path"]
    for line in lines:
        print(line, flush=True)
    held(u)
    sys.stderr.write(u.get("stderr", ""))
    sys.exit(u.get("exit", 0))


def ssh(argv):
    name = argv[0] if argv else ""
    host = (cfg.get("ssh_hosts") or {}).get(name)
    if host is None:
        sys.stderr.write("devcloud vm: no VM named %s in any usable account\n" % name)
        sys.exit(1)
    held(host)
    if "exit" in host or "env" not in host:
        # Nothing run: no host's environment to run it under (never this process's HOME).
        sys.stdout.write(host.get("stdout", ""))
        sys.exit(host.get("exit", 0))
    lacking = [k for k in HOST_ENV if not host["env"].get(k)]
    if lacking:
        # A host's environment, whole, or nothing runs: what it lacks would be this machine's.
        sys.stderr.write("devcloud stand-in: ssh_hosts.%s.env lacks %s, which every host has: nothing was run\n"
                         % (name, ", ".join(lacking)))
        sys.exit(2)
    words = argv[argv.index("--") + 1:] if "--" in argv else []
    if words[:1] == ["sminos"] and cfg.get("sminos"):
        words = [cfg["sminos"]] + words[1:]
    line = shlex.join(words)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE_", "SMNS_", "MAWS_", "FAKE_CLAUDE_")) and k not in ("HOME", "SMINOS_HOME",
                                                                                         "DAEMON_HOST")}
    env.update(host.get("env") or {})
    done = subprocess.run(["/bin/sh", "-c", line], env=env, stdout=subprocess.PIPE if "stdout" in host else None)
    if "stdout" in host:
        sys.stdout.write(host["stdout"])
    sys.exit(done.returncode)


if sys.argv[1:3] == ["vm", "up"]:
    up(sys.argv[3:])
if sys.argv[1:3] == ["vm", "ssh"]:
    ssh(sys.argv[3:])
if sys.argv[1:3] != ["vm", "owned-by"] or len(sys.argv) < 4:
    sys.stderr.write("devcloud stand-in: only vm owned-by <short>..., vm up and vm ssh\n")
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
