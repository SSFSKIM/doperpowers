#!/usr/bin/env bash
# board-gh-plan.sh — compute the board↔GitHub reconcile plan (no mutation).
#
# Usage:
#   board-gh-plan.sh [--gh-json FILE]
#
# GitHub issues come from --gh-json FILE, or stdin if piped, else:
#   gh issue list --state all --limit 1000 --json number,state,stateReason,labels,body,title
# Reads .sync-state.json (the last-sync watermark). Emits a JSON plan on stdout.
# Pure: it never writes the board or GitHub.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP"

ghjson=""
while [ $# -gt 0 ]; do
  case "$1" in
    --gh-json) _need_arg "$1" "${2:-}"; ghjson="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
if [ -n "$ghjson" ]; then
  GH_SRC="$(cat "$ghjson")"
elif [ ! -t 0 ]; then
  GH_SRC="$(cat)"
else
  GH_SRC="$(gh issue list --state all --limit 1000 \
            --json number,state,stateReason,labels,body,title)"
fi

BOARD_GH="$GH_SRC" BOARD_SYNC="$BOARD_DIR/.sync-state.json" _py - <<'PY'
import json, os
env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
gh = {i["number"]: i for i in json.loads(env["BOARD_GH"] or "[]")}
try:
    with open(env["BOARD_SYNC"]) as f:
        wm = json.load(f).get("tickets", {})
except FileNotFoundError:
    wm = {}

def coarse(state):
    if state == "done":    return ["closed", "completed"]
    if state == "wontfix": return ["closed", "not_planned"]
    return ["open", None]

def gh_coarse(issue):
    if str(issue["state"]).lower() == "closed":
        r = str(issue.get("stateReason") or "completed").lower()
        return ["closed", "not_planned" if r == "not_planned" else "completed"]
    return ["open", None]

DONE_REACHABLE = {"in-progress", "in-review"}
actions, unlinked_board, unlinked_gh = [], [], []
linked = set()

for tid in sorted(tickets, key=lambda k: int(k[1:])):
    n = tickets[tid]
    num = n.get("gh")
    if not num:
        unlinked_board.append(tid); continue
    if num not in gh:
        actions.append({"ticket": tid, "gh": num, "facet": "state", "conflict": True,
                        "auto": False, "board": n["state"], "gh_state": None,
                        "watermark": (wm.get(tid) or {}).get("state"),
                        "reason": "linked issue #%d not found on GitHub" % num})
        continue
    linked.add(num)
    b_c, g_c = coarse(n["state"]), gh_coarse(gh[num])
    w = wm.get(tid)
    w_c = coarse(w["state"]) if w and "state" in w else None
    if b_c == g_c:
        continue  # agree → no action (apply refreshes the watermark)
    b_moved = (w_c is None) or (b_c != w_c)
    g_moved = (w_c is None) or (g_c != w_c)
    if w_c is not None and b_moved and not g_moved:
        actions.append({"ticket": tid, "gh": num, "facet": "state",
                        "direction": "board->gh", "auto": True,
                        "board": n["state"], "gh_state": str(gh[num]["state"]).lower(),
                        "target_gh": b_c, "reason": "board changed"})
    elif w_c is not None and g_moved and not b_moved:
        target, auto, reason = None, True, "github changed"
        if g_c == ["closed", "completed"]:
            if n["state"] in DONE_REACHABLE:
                target = ["done", None]
            else:
                auto = False
                reason = "GitHub closed completed but board is %s (never started)" % n["state"]
        elif g_c == ["closed", "not_planned"]:
            target = ["wontfix", "sync: GitHub closed as not planned"]
        else:  # reopened while board terminal — ambiguous target open state
            auto = False
            reason = "GitHub reopened; board is %s — target open state ambiguous" % n["state"]
        a = {"ticket": tid, "gh": num, "facet": "state", "direction": "gh->board",
             "auto": auto, "board": n["state"], "gh_state": str(gh[num]["state"]).lower(),
             "target_board": target, "reason": reason}
        if not auto:
            a["conflict"] = True
        actions.append(a)
    else:  # both moved and disagree, or first contact with no watermark
        actions.append({"ticket": tid, "gh": num, "facet": "state", "conflict": True,
                        "auto": False, "board": n["state"],
                        "gh_state": str(gh[num]["state"]).lower(),
                        "watermark": (w or {}).get("state"),
                        "reason": "both sides diverged" if w_c is not None
                                  else "first sync: sides disagree"})

for num in sorted(gh):
    if num not in linked and str(gh[num]["state"]).lower() == "open":
        unlinked_gh.append(num)

print(json.dumps({"generated_by": "board-gh-plan", "actions": actions,
                  "unlinked_board": unlinked_board, "unlinked_gh": unlinked_gh},
                 indent=2))
PY
