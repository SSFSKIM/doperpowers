#!/usr/bin/env bash
# board-list.sh — board view with computed eligibility.
#
# Usage: board-list.sh [state]
#
# Eligible = a dispatchable lane state (ready-for-architect /
# ready-for-implementer) + every blocked_by ticket done — for a LEAF. An
# epic is eligible only on its own carve-out (ready-for-architect with a
# recomposition or reconciliation claim); both come from B.eligible.
# Tags: epic | ELIGIBLE | waiting:<numbers> | STUCK(wontfix blocker)
# Rows print in dispatch order: priority first (P0 on top, unprioritized
# last), issue number as tiebreaker — the top ELIGIBLE row is the next pick.
# Off-machine label states surface as untracked / conflict (fix via
# board-transition.sh; board-lint.sh names them all).
# API mode is thinner and says so: rows come back in the server's order (which
# is not dispatch order — the header line says as much) as
# `#<id> <state> <priority> <title>`, with no tags.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

# API mode: the server owns the queue. It computes eligibility and hands back
# rows in its own order, so this prints them as given — no local re-derivation
# of ELIGIBLE/waiting/CLOSE? tags, which here would be a second, weaker opinion
# about a decision the board already made (and blocked-by edges and PR linkage,
# which those tags read, are not in the v1 payload at all).
if [ "$BOARD_BINDING" = api ]; then
  T_STATE="${1:-}" _api_py - <<'PY'
import os
import _board_api as A

rows = A.tickets(state=os.environ["T_STATE"] or None, principal="automation")
print("# dispatch order is server-owned in API mode")
for t in rows:
    print("#%s %s %s %s" % (t["id"], t["state"], t.get("priority") or "-", t["title"]))
PY
  exit 0
fi

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
        # An epic is dispatchable too — E2: awaiting recomposition or
        # reconciliation in ready-for-architect — and the dispatcher WILL
        # claim it. The predicate that decides that is B.eligible, so ask
        # it rather than re-deriving the carve-out here.
        if B.eligible(tickets, tid):
            tags.append("ELIGIBLE")
    elif n["state"] in B.DISPATCHABLE:
        blockers = [b for b in n["blocked_by"]
                    if tickets.get(b, {}).get("state") != "done"]
        if not blockers:
            tags.append("ELIGIBLE")
        else:
            tags.append("waiting:" + ",".join("#%s" % b for b in blockers))
            if any(tickets.get(b, {}).get("state") == "wontfix" for b in blockers):
                tags.append("STUCK(wontfix blocker)")
    # Derived close-candidate cue (all linked PRs merged/closed, ≥1 merged):
    # verify & close before dispatching — the ticket may already be done.
    if n.get("close_candidate"):
        tags.append("CLOSE?")
    extra = ("  [%s]" % " ".join(tags)) if tags else ""
    # One row per ticket: flatten embedded newlines so no field can spoof rows.
    title = " ".join(n["title"].split())
    note = ("  — %s" % " ".join(n["note"].split())) if n.get("note") else ""
    prio = n["priority"] or "-"
    print("#%-5s %-3s %-15s %-11s %s%s%s"
          % (tid, prio, n["state"], n["category"], title, extra, note))
PY
