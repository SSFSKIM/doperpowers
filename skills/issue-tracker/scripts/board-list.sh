#!/usr/bin/env bash
# board-list.sh — board view with computed eligibility.
#
# Usage: board-list.sh [state]
#
# Eligible = ready-for-agent + every blocked_by ticket done + not an epic.
# Tags: epic | ELIGIBLE | waiting:<numbers> | STUCK(wontfix blocker)
# Rows print in dispatch order: priority first (P0 on top, unprioritized
# last), issue number as tiebreaker — the top ELIGIBLE row is the next pick.
# Off-machine label states surface as untracked / conflict (fix via
# board-transition.sh; board-lint.sh names them all).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

T_FILTER="${1:-}" _py - <<'PY'
import os
import _board as B

tickets = B.snapshot()
flt = os.environ["T_FILTER"]
epics = B.epics(tickets)

# Dispatch order: priority rank (P0 first, unprioritized after P3), then number.
def rank(tid):
    p = tickets[tid]["priority"]
    return (B.PRIORITIES.index(p) if p in B.PRIORITIES else len(B.PRIORITIES),
            int(tid))

for tid in sorted(tickets, key=rank):
    n = tickets[tid]
    if flt and n["state"] != flt:
        continue
    tags = []
    if tid in epics:
        tags.append("epic")
    elif n["state"] == "ready-for-agent":
        blockers = [b for b in n["blocked_by"]
                    if tickets.get(b, {}).get("state") != "done"]
        if not blockers:
            tags.append("ELIGIBLE")
        else:
            tags.append("waiting:" + ",".join("#%s" % b for b in blockers))
            if any(tickets.get(b, {}).get("state") == "wontfix" for b in blockers):
                tags.append("STUCK(wontfix blocker)")
    extra = ("  [%s]" % " ".join(tags)) if tags else ""
    # One row per ticket: flatten embedded newlines so no field can spoof rows.
    title = " ".join(n["title"].split())
    note = ("  — %s" % " ".join(n["note"].split())) if n.get("note") else ""
    prio = n["priority"] or "-"
    print("#%-5s %-3s %-15s %-11s %s%s%s"
          % (tid, prio, n["state"], n["category"], title, extra, note))
PY
