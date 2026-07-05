#!/usr/bin/env bash
# board-meta.sh — set a ticket's sync metadata: the GitHub link and free labels.
#
# Usage:
#   board-meta.sh <id> --gh N          link the GitHub issue number (0 clears)
#   board-meta.sh <id> --add-label L   add a free label (repeatable, idempotent)
#   board-meta.sh <id> --rm-label L    remove a free label (repeatable)
#
# The fields board-sync reconciles. Kept behind a script — not hand edits — so
# writes stay atomic and BOARD.* re-renders, exactly like board-transition/edge.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1"; shift
gh="" adds="" rms=""
while [ $# -gt 0 ]; do
  case "$1" in
    --gh) _need_arg "$1" "${2:-}"; gh="$2"; shift 2 ;;
    --add-label) _need_arg "$1" "${2:-}"; adds="$adds${adds:+,}$2"; shift 2 ;;
    --rm-label) _need_arg "$1" "${2:-}"; rms="$rms${rms:+,}$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_ID="$tid" T_GH="$gh" T_ADDS="$adds" T_RMS="$rms" \
T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, sys

def die(m): sys.stderr.write("error: %s\n" % m); sys.exit(1)

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
tid = env["T_ID"]
if tid not in tickets:
    die("unknown ticket: %s" % tid)
n = tickets[tid]
log = []

gh = env["T_GH"]
if gh != "":
    try:
        v = int(gh)
    except ValueError:
        die("--gh must be an integer issue number (0 to clear)")
    n["gh"] = None if v == 0 else v
    log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "gh", "op": "set", "value": n["gh"]})

labels = list(n.get("labels") or [])
for l in [x for x in env["T_ADDS"].split(",") if x]:
    if l not in labels:
        labels.append(l)
        log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "labels", "op": "add", "value": l})
for l in [x for x in env["T_RMS"].split(",") if x]:
    if l in labels:
        labels.remove(l)
        log.append({"ts": env["T_NOW"], "ticket": tid, "meta": "labels", "op": "rm", "value": l})
n["labels"] = labels
n["updated"] = env["T_TODAY"]

tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2); f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    for e in log:
        f.write(json.dumps(e) + "\n")
for e in log:
    print("%s: %s %s %s" % (tid, e["meta"], "=" if e["meta"] == "gh" else ("+=" if e["op"] == "add" else "-="), e["value"]))
PY

# BOARD.md is a pure render cache — refresh it on every board write. Non-fatal.
"$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
  || echo "warning: BOARD.md refresh failed (board-map.sh)" >&2
