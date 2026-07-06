#!/usr/bin/env bash
# board-bind.sh — bind a spawned daemon to a ticket.
#
# Usage: board-bind.sh <daemon-uuid-or-prefix> <ticket-number>
#
# Writes a `ticket` key into the daemon's registry meta (additive JSON merge —
# zero changes to the orchestrating-daemons toolkit). The registry is the ONLY
# home of the binding: machine-lifetime data never touches the issue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }

T_Q="$1" T_ID="$2" T_DHOME="$DAEMON_HOME" T_NOW="$(_now)" _py - <<'PY'
import glob
import json
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
hits = []
for p in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
    u = os.path.basename(p)[:-5]
    if u == env["T_Q"] or u.startswith(env["T_Q"]):
        hits.append(p)
if len(hits) != 1:
    B.die("%d daemons match '%s'" % (len(hits), env["T_Q"]))
with open(hits[0]) as f:
    meta = json.load(f)
meta["ticket"] = tid
meta["updated"] = env["T_NOW"]
tmp = hits[0] + ".tmp"
with open(tmp, "w") as f:
    json.dump(meta, f, indent=2)
os.replace(tmp, hits[0])
print("bound #%s ← %s" % (tid, os.path.basename(hits[0])[:-5]))
PY
