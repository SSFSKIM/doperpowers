#!/usr/bin/env bash
# board-edge.sh — re-cut a ticket's ordering/hierarchy edges after birth.
#
# Usage:
#   board-edge.sh <id> --block TID      add a blocked_by edge
#   board-edge.sh <id> --unblock TID    cut a blocked_by edge (e.g. a wontfix blocker)
#   board-edge.sh <id> --parent TID     move the ticket under an(other) epic
#   board-edge.sh <id> --orphan         clear the parent (leave the epic)
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
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

T_ID="$tid" T_OP="$op" T_REF="$ref" T_NOW="$(_now)" T_TODAY="$(_today)" _py - <<'PY'
import json, os, sys

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]
tid, op, ref = env["T_ID"], env["T_OP"], env["T_REF"]
if tid not in tickets:
    die("unknown ticket: %s" % tid)
n = tickets[tid]

TERMINAL = {"done", "wontfix"}
PULLABLE = ("ready-for-agent", "needs-info", "blocked", "deferred")

applied = []   # swept state changes — logged in the transition shape
edges = []     # edge mutations — logged with an "edge" key
lines = []

def apply(t, new, why):
    old = tickets[t]["state"]
    tickets[t]["state"] = new
    tickets[t]["updated"] = env["T_TODAY"]
    tickets[t]["note"] = why or None
    applied.append({"ts": env["T_NOW"], "ticket": t, "from": old, "to": new,
                    "note": why or None})

def children(p):
    return [t for t, x in tickets.items() if x.get("parent") == p]

def ancestors(t):
    seen = set()
    p = tickets[t].get("parent")
    while p and p in tickets and p not in seen:
        seen.add(p)
        p = tickets[p].get("parent")
    return seen

def close_sweep(p):
    # Same rule as board-transition: an epic closes when every child is
    # terminal and at least one is done (an all-wontfix epic stays a human call).
    while p and p in tickets:
        kids = children(p)
        if kids and tickets[p]["state"] not in TERMINAL \
           and all(tickets[k]["state"] in TERMINAL for k in kids) \
           and any(tickets[k]["state"] == "done" for k in kids):
            apply(p, "done", "epic: all children terminal")
            p = tickets[p].get("parent")
        else:
            break

def edge_log(edge, eop, eref):
    edges.append({"ts": env["T_NOW"], "ticket": tid, "edge": edge,
                  "op": eop, "ref": eref})

if op == "block":
    if ref not in tickets:
        die("unknown ticket ref: %s" % ref)
    if ref == tid:
        die("a ticket cannot block itself")
    blocked = n.setdefault("blocked_by", [])
    if ref in blocked:
        die("%s is already blocked by %s" % (tid, ref))
    # No dependency cycles: the new blocker must not (transitively) wait on tid.
    seen, stack = set(), [ref]
    while stack:
        c = stack.pop()
        if c == tid:
            die("cycle: %s already waits on %s" % (ref, tid))
        if c in seen or c not in tickets:
            continue
        seen.add(c)
        stack.extend(tickets[c].get("blocked_by", []))
    # An ancestor epic closes only after this child is terminal — blocking on
    # it can never resolve.
    if ref in ancestors(tid):
        die("deadlock: %s is an ancestor epic of %s" % (ref, tid))
    blocked.append(ref)
    edge_log("blocked_by", "add", ref)
    lines.append("%s: blocked_by += %s" % (tid, ref))

elif op == "unblock":
    # ref may be a dangling blocker (hand-edited map): only the edge's
    # presence matters, so cutting doubles as repair.
    blocked = n.get("blocked_by") or []
    if ref not in blocked:
        die("%s is not blocked by %s" % (tid, ref))
    blocked.remove(ref)
    n["blocked_by"] = blocked
    edge_log("blocked_by", "cut", ref)
    lines.append("%s: blocked_by -= %s" % (tid, ref))
    epics = {x.get("parent") for x in tickets.values() if x.get("parent")}
    if n["state"] == "ready-for-agent" and tid not in epics \
       and all(tickets.get(b, {}).get("state") == "done" for b in blocked):
        lines.append("now eligible: %s  %s" % (tid, " ".join(str(n["title"]).split())))

elif op == "parent":
    if ref not in tickets:
        die("unknown ticket ref: %s" % ref)
    if ref == tid:
        die("a ticket cannot be its own parent")
    if tid in ancestors(ref):
        die("cycle: %s is an ancestor of %s" % (tid, ref))
    old = n.get("parent")
    if old == ref:
        die("%s already has parent %s" % (tid, ref))
    n["parent"] = ref
    edge_log("parent", "set", ref)
    lines.append("%s: parent = %s (was %s)" % (tid, ref, old or "none"))
    if n["state"] == "in-progress":
        p = ref
        while p and p in tickets and tickets[p]["state"] in PULLABLE:
            apply(p, "in-progress", "epic: child %s active" % tid)
            p = tickets[p].get("parent")
    if n["state"] in TERMINAL:
        close_sweep(ref)
    if old:
        close_sweep(old)

elif op == "orphan":
    old = n.get("parent")
    if not old:
        die("%s has no parent" % tid)
    n["parent"] = None
    edge_log("parent", "clear", old)
    lines.append("%s: parent cleared (was %s)" % (tid, old))
    close_sweep(old)

n["updated"] = env["T_TODAY"]

tmp = env["BOARD_MAP"] + ".tmp"
with open(tmp, "w") as f:
    json.dump(board, f, indent=2)
    f.write("\n")
os.replace(tmp, env["BOARD_MAP"])
with open(env["BOARD_LOG"], "a") as f:
    for e in edges + applied:
        f.write(json.dumps(e) + "\n")
for ln in lines:
    print(ln)
for e in applied:
    print("%s: %s → %s" % (e["ticket"], e["from"], e["to"]))
PY

# BOARD.md is a pure render cache of map.json — refresh it on every board write
# so the human view can never go stale by discipline alone. Non-fatal: the
# board write above already landed.
"$SCRIPT_DIR/board-map.sh" --write >/dev/null 2>&1 \
  || echo "warning: BOARD.md refresh failed (board-map.sh)" >&2
