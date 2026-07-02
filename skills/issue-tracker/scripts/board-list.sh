#!/usr/bin/env bash
# board-list.sh — board view with computed eligibility.
#
# Usage: board-list.sh [state]
#
# Eligible = ready-for-agent + every blocked_by ticket done + not an epic.
# Tags: epic | ELIGIBLE | waiting:<ids> | STUCK(wontfix blocker) | MISSING-MD
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_FILTER="${1:-}" _py - <<'PY'
import json, os

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
flt = env["T_FILTER"]
board_dir = os.path.dirname(env["BOARD_MAP"])
epics = {n["parent"] for n in tickets.values() if n.get("parent")}

for tid, n in sorted(tickets.items(), key=lambda kv: int(kv[0][1:])):
    if flt and n["state"] != flt:
        continue
    tags = []
    if tid in epics:
        tags.append("epic")
    elif n["state"] == "ready-for-agent":
        blockers = [b for b in n.get("blocked_by", [])
                    if tickets.get(b, {}).get("state") != "done"]
        if not blockers:
            tags.append("ELIGIBLE")
        else:
            tags.append("waiting:" + ",".join(blockers))
            if any(tickets.get(b, {}).get("state") == "wontfix" for b in blockers):
                tags.append("STUCK(wontfix blocker)")
    if not os.path.exists(os.path.join(board_dir, n["md"])):
        tags.append("MISSING-MD")
    extra = ("  [%s]" % " ".join(tags)) if tags else ""
    # One row per ticket: flatten embedded newlines (in a hand-edited title or a
    # multi-line note) so no field can spoof extra board rows.
    title = " ".join(str(n["title"]).split())
    note = ("  — %s" % " ".join(str(n["note"]).split())) if n.get("note") else ""
    print("%-5s %-15s %-11s %s%s%s" % (tid, n["state"], n["category"], title, extra, note))
PY
