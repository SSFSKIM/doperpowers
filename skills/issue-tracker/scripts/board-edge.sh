#!/usr/bin/env bash
# board-edge.sh — re-cut a ticket's ordering/hierarchy edges after birth.
#
# Usage:
#   board-edge.sh <number> --block N      add a blocked_by edge (native dependency)
#   board-edge.sh <number> --unblock N    cut a blocked_by edge (e.g. a wontfix blocker)
#   board-edge.sh <number> --parent N     move the ticket under an(other) epic (sub-issue)
#   board-edge.sh <number> --orphan       clear the parent (leave the epic)
#
# One edge operation per call. spawned_by is provenance — never mutated.
# Register-time edges can't form cycles (a new node is in no chain yet);
# mutation can, so this script rejects self-edges, dependency cycles, parent
# cycles, and ancestor-epic blockers (a guaranteed deadlock). Membership
# changes re-derive epic states, so it runs the same sweeps as
# board-transition: an in-progress child pulls its new epic chain, and an
# epic whose last active child leaves may close.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

[ $# -ge 2 ] || { usage_from_header "$0" >&2; exit 2; }
tid="$1"
shift
op="" ref=""
while [ $# -gt 0 ]; do
  case "$1" in
    --block|--unblock|--parent)
      [ -z "$op" ] || die "one edge operation per call"
      op="${1#--}"; _need_arg "$1" "${2:-}"; ref="$2"; shift 2 ;;
    --orphan)
      [ -z "$op" ] || die "one edge operation per call"
      op="orphan"; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$op" ] || { usage_from_header "$0" >&2; exit 2; }

T_ID="$tid" T_OP="$op" T_REF="$ref" _py - <<'PY'
import os
import _board as B

env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_ID"], tickets)
op = env["T_OP"]
ref = B.resolve(env["T_REF"], tickets) if env["T_REF"] else ""
n = tickets[tid]

lines = []

if op == "block":
    if ref == tid:
        B.die("a ticket cannot block itself")
    if ref in n["blocked_by"]:
        B.die("#%s is already blocked by #%s" % (tid, ref))
    # No dependency cycles: the new blocker must not (transitively) wait on tid.
    seen, stack = set(), [ref]
    while stack:
        c = stack.pop()
        if c == tid:
            B.die("cycle: #%s already waits on #%s" % (ref, tid))
        if c in seen or c not in tickets:
            continue
        seen.add(c)
        stack.extend(tickets[c]["blocked_by"])
    # An ancestor epic closes only after this child is terminal — blocking on
    # it can never resolve.
    if ref in B.ancestors(tickets, tid):
        B.die("deadlock: #%s is an ancestor epic of #%s" % (ref, tid))
    B.add_blocked_by(n, tickets[ref])
    n["blocked_by"].append(ref)
    lines.append("#%s: blocked_by += #%s" % (tid, ref))

elif op == "unblock":
    if ref not in n["blocked_by"]:
        B.die("#%s is not blocked by #%s" % (tid, ref))
    B.remove_blocked_by(n, tickets[ref])
    n["blocked_by"].remove(ref)
    lines.append("#%s: blocked_by -= #%s" % (tid, ref))
    if n["state"] == "ready-for-agent" and tid not in B.epics(tickets) \
       and all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"]):
        lines.append("now eligible: #%s  %s" % (tid, " ".join(n["title"].split())))

elif op == "parent":
    if ref == tid:
        B.die("a ticket cannot be its own parent")
    if tid in B.ancestors(tickets, ref):
        B.die("cycle: #%s is an ancestor of #%s" % (tid, ref))
    old = n.get("parent")
    if old == ref:
        B.die("#%s already has parent #%s" % (tid, ref))
    B.add_sub_issue(tickets[ref], n, replace=bool(old))
    n["parent"] = ref
    lines.append("#%s: parent = #%s (was %s)" % (tid, ref, ("#%s" % old) if old else "none"))
    if n["state"] == "in-progress":
        B.pull_epics(tickets, tid, lines)
    if n["state"] in B.TERMINAL:
        B.close_epics(tickets, ref, lines)
    if old:
        B.close_epics(tickets, old, lines)

elif op == "orphan":
    old = n.get("parent")
    if not old:
        B.die("#%s has no parent" % tid)
    B.remove_sub_issue(tickets[old], n)
    n["parent"] = None
    lines.append("#%s: parent cleared (was #%s)" % (tid, old))
    B.close_epics(tickets, old, lines)

for ln in lines:
    print(ln)
PY
