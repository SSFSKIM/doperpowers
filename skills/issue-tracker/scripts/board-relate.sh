#!/usr/bin/env bash
# board-relate.sh — add or cut a symmetric relates edge between two tickets.
#
# Usage:
#   board-relate.sh <id-a> <id-b> [--cut]
#
# The edge is annotation only — it never affects eligibility. It is stored on
# BOTH nodes (relates_to) so either ticket's board-show sees it; board-map
# dedupes the pair and renders it once as a labeled dotted line.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
a="$1" b="$2"
shift 2
cut=0
while [ $# -gt 0 ]; do
  case "$1" in
    --cut) cut=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_A="$a" T_B="$b" T_CUT="$cut" T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
a, b, cut = env["T_A"], env["T_B"], env["T_CUT"] == "1"
if a not in tickets:
    die("unknown ticket: %s" % a)
if a == b:
    die("a ticket cannot relate to itself")

def rel(t):
    lst = tickets[t].get("relates_to") or []
    tickets[t]["relates_to"] = lst
    return lst

if cut:
    # b may be a dangling ref (hand-edited map): cut whichever halves exist.
    if b not in rel(a) and not (b in tickets and a in rel(b)):
        die("no relates edge between %s and %s" % (a, b))
    if b in rel(a):
        rel(a).remove(b)
    if b in tickets and a in rel(b):
        rel(b).remove(a)
    msg = "cut: %s -- %s" % (a, b)
else:
    if b not in tickets:
        die("unknown ticket: %s" % b)
    if b in rel(a) or a in rel(b):
        die("%s and %s are already related" % (a, b))
    rel(a).append(b)
    rel(b).append(a)
    msg = "related: %s -- %s" % (a, b)

tickets[a]["updated"] = env["T_TODAY"]
if b in tickets:
    tickets[b]["updated"] = env["T_TODAY"]

tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2)
    f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    f.write(json.dumps({"ts": env["T_NOW"], "ticket": a, "edge": "relates_to",
                        "op": "cut" if cut else "add", "ref": b}) + "\n")
print(msg)
PY

# MAP.md is a pure render cache of map.json — refresh it on every board write
# so the human view can never go stale by discipline alone. Non-fatal: the
# board write above already landed.
"$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
  || echo "warning: MAP.md refresh failed (board-map.sh)" >&2
