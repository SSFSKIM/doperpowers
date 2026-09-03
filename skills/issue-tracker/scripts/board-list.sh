#!/usr/bin/env bash
# board-list.sh — board view with computed eligibility.
#
# Usage: board-list.sh [--all-repos] [state]
#
# --all-repos (API binding only) widens the read past the repo the binding
# speaks for, to every repo the board service holds — a browse convenience, and
# the header says when it is on. Everything else in the toolkit always narrows.
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

state="" all_repos=0
while [ $# -gt 0 ]; do
  case "$1" in
    --all-repos) all_repos=1; shift ;;
    -*) usage_from_header "$0" >&2; exit 2 ;;
    *) [ -n "$state" ] && { usage_from_header "$0" >&2; exit 2; }
       state="$1"; shift ;;
  esac
done

# API mode: the server owns the queue. It computes eligibility and hands back
# rows in its own order, so this prints them as given — no local re-derivation
# of ELIGIBLE/waiting/CLOSE? tags, which here would be a second, weaker opinion
# about a decision the board already made (and blocked-by edges and PR linkage,
# which those tags read, are not in the v1 payload at all).
if [ "$BOARD_BINDING" = api ]; then
  T_STATE="$state" T_ALL_REPOS="$all_repos" _api_py - <<'PY'
import os
import _board_api as A

# `states=` is the paged surface's promoted plural filter, and the single state
# name this verb takes is a one-element list server-side — so the argument goes
# through verbatim. The walk either completes or raises: a half-read board can
# never print as the board.
all_repos = os.environ["T_ALL_REPOS"] == "1"
rows = A.tickets_all(states=os.environ["T_STATE"] or None, principal="automation",
                     all_repos=all_repos)
# The header carries the scope beside the order caveat: rows from several repos
# look exactly like rows from one, and #12 means a different ticket in each.
print("# dispatch order is server-owned in API mode"
      + (" — all repos" if all_repos else ""))
for t in rows:
    print("#%s %s %s %s" % (t["id"], t["state"], t.get("priority") or "-", t["title"]))
PY
  exit 0
fi

# gh mode: one repo, so there is nothing to widen to. Refused rather than
# dropped — a documented invocation that silently loses its argument is worse
# than one that fails (the --states / --repair-path precedent).
[ "$all_repos" -eq 0 ] \
  || { echo "board-list: --all-repos is API-binding only — a gh board is one repo" >&2; exit 2; }

T_FILTER="$state" _py - <<'PY'
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
