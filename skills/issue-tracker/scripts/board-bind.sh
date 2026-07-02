#!/usr/bin/env bash
# board-bind.sh — bind a spawned daemon to a ticket.
#
# Usage: board-bind.sh <daemon-uuid-or-prefix> <ticket-id>
#
# Writes a `ticket` key into the daemon's registry meta (additive JSON merge —
# zero changes to the orchestrating-daemons toolkit). The registry is the ONLY
# home of the binding: machine-lifetime data never enters the map.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_Q="$1" T_ID="$2" T_DHOME="$DAEMON_HOME" T_NOW="$(_now)" _py - <<'PY'
import glob, json, os, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
if env["T_ID"] not in board["tickets"]:
    die("unknown ticket: %s" % env["T_ID"])
hits = []
for p in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
    u = os.path.basename(p)[:-5]
    if u == env["T_Q"] or u.startswith(env["T_Q"]):
        hits.append(p)
if len(hits) != 1:
    die("%d daemons match '%s'" % (len(hits), env["T_Q"]))
with open(hits[0]) as f:
    meta = json.load(f)
meta["ticket"] = env["T_ID"]
meta["updated"] = env["T_NOW"]
tmp = hits[0] + ".tmp"
with open(tmp, "w") as f:
    json.dump(meta, f, indent=2)
os.replace(tmp, hits[0])
print("bound %s ← %s" % (env["T_ID"], os.path.basename(hits[0])[:-5]))
PY
