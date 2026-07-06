#!/usr/bin/env bash
# board-show.sh — one ticket in full: node JSON, issue URL, bound daemon.
#
# Usage: board-show.sh <number>
#
# The daemon binding lives in the daemon registry (a `ticket` key in the
# daemon's meta JSON — see board-bind.sh), never on the issue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 1 ] || { usage_from_header "$0" >&2; exit 2; }

T_ID="$1" T_DHOME="$DAEMON_HOME" _py - <<'PY'
import glob
import json
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
n = dict(tickets[tid])
n.pop("body", None)   # the issue body is one `gh issue view` away — keep this scannable
n.pop("id", None)
print(json.dumps({"#" + tid: n}, indent=2))
for p in sorted(glob.glob(os.path.join(env["T_DHOME"], "*.json"))):
    try:
        with open(p) as f:
            m = json.load(f)
    except (ValueError, OSError):
        continue
    if str(m.get("ticket", "")).lstrip("#") == tid:
        print("daemon: %s  status=%s  cwd=%s  worktree=%s" %
              (m.get("uuid", os.path.basename(p)[:-5]), m.get("status"),
               m.get("cwd"), m.get("worktree") or "-"))
        break
else:
    print("daemon: (none bound)")
PY
