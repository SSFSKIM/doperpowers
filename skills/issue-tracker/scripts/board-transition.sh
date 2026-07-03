#!/usr/bin/env bash
# board-transition.sh — move a ticket to a new state, enforcing the invariants.
#
# Usage:
#   board-transition.sh <id> <to-state> [note] [--branch NAME] [--pr URL]
#
# Enforces transition legality and mandatory notes (blocked/needs-info/wontfix),
# records branch/pr, appends every applied change to log.jsonl, and sweeps:
#   → in-progress : the first active child pulls its parent epic(s) to in-progress
#   → done/wontfix: an epic closes when every child is terminal and at least one
#                   is done; a done ticket prints its newly-eligible dependents
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1" to="$2"
shift 2
note="" branch="" pr=""
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then note="$1"; shift; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) _need_arg "$1" "${2:-}"; branch="$2"; shift 2 ;;
    --pr) _need_arg "$1" "${2:-}"; pr="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_ID="$tid" T_TO="$to" T_NOTE="$note" T_BRANCH="$branch" T_PR="$pr" \
T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
LEGAL = {
    "ready-for-agent": {"in-progress", "needs-info", "blocked", "wontfix", "deferred"},
    "in-progress":     {"needs-info", "blocked", "in-review", "done", "wontfix", "deferred"},
    "needs-info":      {"ready-for-agent", "in-progress", "wontfix", "deferred"},
    "blocked":         {"ready-for-agent", "in-progress", "wontfix", "deferred"},
    "in-review":       {"in-progress", "done", "wontfix", "deferred"},
    "deferred":        {"ready-for-agent", "needs-info", "blocked", "wontfix"},
    "done":            set(),   # terminal
    "wontfix":         set(),   # terminal
}
NOTE_REQUIRED = {"blocked", "needs-info", "wontfix"}
TERMINAL = {"done", "wontfix"}

with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
tid, to, note = env["T_ID"], env["T_TO"], env["T_NOTE"]
if tid not in tickets:
    die("unknown ticket: %s" % tid)
if to not in LEGAL:
    die("unknown state: %s" % to)
cur = tickets[tid]["state"]
if to == cur:
    die("%s is already %s" % (tid, cur))
if to not in LEGAL[cur]:
    die("illegal transition: %s → %s (%s)" % (cur, to, tid))
if to in NOTE_REQUIRED and not note:
    die("a note is required when moving to %s" % to)
if to == "in-review" and not env.get("T_PR"):
    die("a PR link is required when moving to in-review (--pr URL)")

applied = []
def apply(t, new, why):
    old = tickets[t]["state"]
    tickets[t]["state"] = new
    tickets[t]["updated"] = env["T_TODAY"]
    tickets[t]["note"] = why or None       # stale notes cleared on every move
    applied.append({"ts": env["T_NOW"], "ticket": t, "from": old, "to": new,
                    "note": why or None})

apply(tid, to, note)
if env["T_BRANCH"]:
    tickets[tid]["branch"] = env["T_BRANCH"]
if env["T_PR"]:
    tickets[tid]["pr"] = env["T_PR"]

def children(p):
    return [t for t, n in tickets.items() if n.get("parent") == p]

# Sweep: first active child pulls its epic chain to in-progress.
if to == "in-progress":
    p = tickets[tid].get("parent")
    while p and tickets[p]["state"] in ("ready-for-agent", "needs-info", "blocked", "deferred"):
        apply(p, "in-progress", "epic: child %s started" % tid)
        p = tickets[p].get("parent")

# Sweep: a terminal child may close its epic chain (all children terminal,
# at least one done — an all-wontfix epic is left for human judgment).
if to in TERMINAL:
    p = tickets[tid].get("parent")
    while p:
        kids = children(p)
        if kids and tickets[p]["state"] not in TERMINAL \
           and all(tickets[k]["state"] in TERMINAL for k in kids) \
           and any(tickets[k]["state"] == "done" for k in kids):
            apply(p, "done", "epic: all children terminal")
            p = tickets[p].get("parent")
        else:
            break

# Report dependents this `done` made eligible (derived, nothing written).
if to == "done":
    for t, n in sorted(tickets.items(), key=lambda kv: int(kv[0][1:])):
        if n["state"] == "ready-for-agent" and tid in n.get("blocked_by", []) \
           and all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"]):
            print("now eligible: %s  %s" % (t, " ".join(str(n["title"]).split())))

tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2)
    f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    for e in applied:
        f.write(json.dumps(e) + "\n")
for e in applied:
    print("%s: %s → %s" % (e["ticket"], e["from"], e["to"]))
PY

# MAP.md is a pure render cache of map.json — refresh it on every board write
# so the human view can never go stale by discipline alone. Non-fatal: the
# board write above already landed.
"$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
  || echo "warning: MAP.md refresh failed (board-map.sh)" >&2
