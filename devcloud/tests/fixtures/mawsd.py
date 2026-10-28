#!/usr/bin/env python3
"""The stand-in `mawsd` wrapper (`<profile>/mawsd/bin/mawsd`): what devcloud
relies on of MAWS's endpoint (the O14 spec's Interfaces §B and O2's exit
codes: 0 done, 1 refused, 2 no endpoint module, 3 not running, 4 enrolled
with the hub but not yet listed), and nothing else (Python 3.9 compatible).

  keys --json       prints `keys.json` from the state directory, else an
                    unenrolled endpoint's answer; exits with `keys.exit`
                    ("<code> [stderr line]", 0 when absent)
  endpoint provision --name <name> --wait <s>
                    reads the code from stdin (never from argv) and exits with
                    the next line of `provision.exit` (0 when absent)
  endpoint retire --json
                    exits with the next line of `retire.exit` (0 when absent);
                    on 0 prints `retire.out`, else a `retired` outcome

Every call is one JSON line in `mawsd-calls.jsonl`, with its argv and a digest
of what stdin held, never the value itself. State lives in $FAKE_MAWSD_STATE,
else ~/.local/state/devcloud-test."""
import hashlib
import json
import os
import pathlib
import sys

home = pathlib.Path.home()
state = pathlib.Path(os.environ.get("FAKE_MAWSD_STATE") or home / ".local/state/devcloud-test")
args = sys.argv[1:]


def record(**fields):
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "mawsd-calls.jsonl", "a") as log:
        log.write(json.dumps(dict(argv=args, **fields)) + "\n")


def next_line(name, default):
    path = state / name
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return default
    if not lines:
        return default
    path.write_text("".join(line + "\n" for line in lines[1:]))
    return lines[0]


def exit_with(line, out=None):
    code, _, message = line.partition(" ")
    if message:
        print(message, file=sys.stderr)
    if out is not None and code in ("0", "4"):
        print(out)
    sys.exit(int(code))


if args == ["keys", "--json"]:
    record()
    try:
        keys = (state / "keys.json").read_text().strip()
    except FileNotFoundError:
        keys = json.dumps({"enrollment": "none", "ref": "made-up-ref", "delegated": False})
    exit_with(next_line("keys.exit", "0"), keys)
elif args[:2] == ["endpoint", "provision"]:
    code = sys.stdin.read().strip()
    record(stdin_sha256=hashlib.sha256(code.encode()).hexdigest() if code else None)
    exit_with(next_line("provision.exit", "0"), "provisioned (stand-in)")
elif args == ["endpoint", "retire", "--json"]:
    record()
    try:
        out = (state / "retire.out").read_text().strip()
    except FileNotFoundError:
        out = json.dumps({"kind": "retired", "name": "dc-build-7f3a", "keyId": "made-up-key-id",
                          "notAfter": "2026-10-28T12:01:00.000Z"})
    exit_with(next_line("retire.exit", "0"), out)
else:
    sys.exit(f"stand-in mawsd: {' '.join(args)} is not played here")
