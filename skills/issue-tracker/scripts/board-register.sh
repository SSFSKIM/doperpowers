#!/usr/bin/env bash
# board-register.sh — add a ticket to the board (lazy-creates it on first use).
#
# Usage:
#   board-register.sh <title> <category> [--state S] [--note TEXT] [--parent TID]
#                     [--blocked-by TID[,TID...]] [--spawned-by TID]
#
#   category  bug | enhancement
#   --state   birth state: ready-for-agent (default) | needs-info | blocked | deferred
#             (needs-info / blocked require --note)
#
# Prints "<id> <md-relpath>" — the caller (orchestrator) writes that markdown.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
title="$1" category="$2"
shift 2
state="ready-for-agent" note="" parent="" blocked_by="" spawned_by=""
while [ $# -gt 0 ]; do
  case "$1" in
    --state) _need_arg "$1" "${2:-}"; state="$2"; shift 2 ;;
    --note) _need_arg "$1" "${2:-}"; note="$2"; shift 2 ;;
    --parent) _need_arg "$1" "${2:-}"; parent="$2"; shift 2 ;;
    --blocked-by) _need_arg "$1" "${2:-}"; blocked_by="$2"; shift 2 ;;
    --spawned-by) _need_arg "$1" "${2:-}"; spawned_by="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done

_board_init
T_TITLE="$title" T_CATEGORY="$category" T_STATE="$state" T_NOTE="$note" \
T_PARENT="$parent" T_BLOCKED="$blocked_by" T_SPAWNED="$spawned_by" \
T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, re, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
# Titles are one line: collapse newlines/whitespace runs so a title can never
# spoof extra rows in line-oriented views (board-list).
title = " ".join(env["T_TITLE"].split())
category, state, note = env["T_CATEGORY"], env["T_STATE"], env["T_NOTE"]
if not title:
    die("title must be non-empty")
if category not in ("bug", "enhancement"):
    die("category must be bug|enhancement")
BIRTH = ("ready-for-agent", "needs-info", "blocked", "deferred")
if state not in BIRTH:
    die("birth state must be one of: %s" % ", ".join(BIRTH))
if state in ("needs-info", "blocked") and not note:
    die("--note is required for state %s" % state)

with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
parent, spawned = env["T_PARENT"], env["T_SPAWNED"]
blocked = [b for b in env["T_BLOCKED"].split(",") if b]
for ref in [parent, spawned] + blocked:
    if ref and ref not in tickets:
        die("unknown ticket ref: %s" % ref)

tid = "T%d" % board["next_id"]
board["next_id"] += 1
slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-")[:40] or "ticket"
md = "tickets/%s-%s.md" % (tid, slug)
tickets[tid] = {
    "title": title, "md": md, "state": state, "category": category,
    "note": note or None, "parent": parent or None,
    "blocked_by": blocked, "spawned_by": spawned or None, "relates_to": [],
    "branch": None, "pr": None, "gh": None, "labels": [],
    "created": env["T_TODAY"], "updated": env["T_TODAY"],
}
tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2)
    f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    f.write(json.dumps({"ts": env["T_NOW"], "ticket": tid, "from": None,
                        "to": state, "note": note or None}) + "\n")
print("%s %s" % (tid, md))
PY

# BOARD.md is a pure render cache of board.json — refresh it on every board write
# so the human view can never go stale by discipline alone. Non-fatal: the
# board write above already landed.
"$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
  || echo "warning: BOARD.md refresh failed (board-map.sh)" >&2
