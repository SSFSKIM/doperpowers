#!/usr/bin/env bash
# board-gh-apply.sh — apply a board-gh-plan, then refresh the sync watermark.
#
# Usage:
#   board-gh-apply.sh --plan FILE --gh-json FILE [--dry-run] [--no-github]
#   ... | board-gh-apply.sh --gh-json FILE [--dry-run]        (plan on stdin)
#
# Executes only auto:true, non-conflict actions: board side via board-transition.sh,
# GitHub side via gh. --dry-run prints the commands and writes nothing. --no-github
# applies board-side actions but skips gh calls (test/board-only seam). On a real
# run, .sync-state.json is rewritten for every linked, non-conflict ticket.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP"

planfile="" ghjson="" dry="" nogh=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plan) _need_arg "$1" "${2:-}"; planfile="$2"; shift 2 ;;
    --gh-json) _need_arg "$1" "${2:-}"; ghjson="$2"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    --no-github) nogh=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$planfile" ] && PLAN="$(cat "$planfile")" || PLAN="$(cat)"
[ -n "$ghjson" ] && GH_SRC="$(cat "$ghjson")" || GH_SRC="[]"

# 1) board-side transitions the plan asks for (unless dry-run) — via the real script.
printf '%s' "$PLAN" | PLAN_JSON="$PLAN" python3 -c '
import json, os, sys
plan = json.loads(os.environ["PLAN_JSON"])
for a in plan["actions"]:
    if not a.get("auto") or a.get("conflict"): continue
    if a.get("direction") == "gh->board" and a.get("target_board"):
        st, note = a["target_board"]
        print("%s\t%s\t%s" % (a["ticket"], st, note or ""))
' | while IFS="$(printf '\t')" read -r tid st note; do
  [ -z "$tid" ] && continue
  if [ -n "$dry" ]; then
    echo "board: board-transition.sh $tid $st ${note:+\"$note\"}"
  else
    if [ -n "$note" ]; then "$SCRIPT_DIR/board-transition.sh" "$tid" "$st" "$note" >/dev/null
    else "$SCRIPT_DIR/board-transition.sh" "$tid" "$st" >/dev/null; fi
    echo "board: $tid -> $st"
  fi
done

# 2) GitHub-side changes (unless dry-run or --no-github) — via gh.
printf '%s' "$PLAN" | PLAN_JSON="$PLAN" python3 -c '
import json, os
plan = json.loads(os.environ["PLAN_JSON"])
for a in plan["actions"]:
    if not a.get("auto") or a.get("conflict"): continue
    if a.get("direction") == "board->gh" and a.get("target_gh"):
        state, reason = a["target_gh"]
        if state == "closed":
            print("close\t%d\t%s" % (a["gh"], reason))
        else:
            print("reopen\t%d\t" % a["gh"])
' | while IFS="$(printf '\t')" read -r op num reason; do
  [ -z "$op" ] && continue
  if [ -n "$dry" ]; then
    [ "$op" = "close" ] && echo "gh: issue close $num --reason $reason" || echo "gh: issue reopen $num"
  elif [ -z "$nogh" ]; then
    if [ "$op" = "close" ]; then gh issue close "$num" --reason "$reason" >/dev/null
    else gh issue reopen "$num" >/dev/null; fi
    echo "gh: $op $num"
  fi
done

[ -n "$dry" ] && { echo "(dry-run: watermark unchanged)"; exit 0; }

# 3) Refresh the watermark for every linked, non-conflict ticket.
BOARD_GH="$GH_SRC" BOARD_SYNC="$BOARD_DIR/.sync-state.json" PLAN_JSON="$PLAN" \
T_TODAY="$(_today)" _py - <<'PY'
import json, os
env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
gh = {i["number"]: i for i in json.loads(env["BOARD_GH"] or "[]")}
plan = json.loads(env["PLAN_JSON"])
conflicted = {a["ticket"] for a in plan["actions"] if a.get("conflict")}
try:
    with open(env["BOARD_SYNC"]) as f:
        state = json.load(f)
except FileNotFoundError:
    state = {"version": 1, "tickets": {}}
wm = state.setdefault("tickets", {})
for tid, n in tickets.items():
    num = n.get("gh")
    if not num or num not in gh or tid in conflicted:
        continue  # unlinked, missing issue, or contested → leave watermark as-is
    wm[tid] = {"gh": num, "state": n["state"],
               "labels": list(n.get("labels") or [])}
state["version"] = 1
state["synced_at"] = env["T_TODAY"]
tmp = env["BOARD_SYNC"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(state, f, indent=2); f.write("\n")
os.replace(tmp, env["BOARD_SYNC"])
print("watermark: refreshed %d linked ticket(s)" % sum(
    1 for t, n in tickets.items() if n.get("gh") and n["gh"] in gh and t not in conflicted))
PY
