#!/usr/bin/env bash
# board-map.sh — human telemetry for the board.
#
# Usage: board-map.sh [--write]
#
#   (default)  print the fallback table (ticket · state · title · PR) to stdout
#   --write    render two caches of map.json into doperpowers/issue-tracker/:
#              BOARD.html — the primary view: an interactive layered-DAG (pan/zoom,
#              click a node for detail, filter by state, collapse epics), opened
#              in a browser; and BOARD.md — a minimal node/state table, the
#              GitHub-inline fallback. Both are pure render caches, refreshed by
#              every board write; --write re-renders them by hand.
#
# Reading BOARD.html: node color = state; ELIGIBLE (ready-for-agent + all blockers
# done, not an epic) gets a thick green border; a solid arrow is an ACTIVE block,
# a dotted one a satisfied dependency; labeled dotted lines carry spawned/relates
# lineage; each epic is a labeled box around its members (click to collapse).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

write=0
[ "${1:-}" = "--write" ] && write=1

# One python pass per call: it always prints the fallback table to stdout, and
# on --write it also writes BOARD.md and renders BOARD.html — the table and the
# graph share the single map.json parse (one process, not two).
BOARD_MAP="$MAP" BOARD_DIR="$BOARD_DIR" \
BOARD_TEMPLATE="$SCRIPT_DIR/board-map.template.html" \
BOARD_WRITE="$write" python3 - <<'PY'
import json, os

env = os.environ
with open(env["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]

def num(t): return int(t[1:])
order = sorted(tickets, key=num)
epics = {n["parent"] for n in tickets.values() if n.get("parent")}

def eligible(tid, n):
    if tid in epics or n["state"] != "ready-for-agent":
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n.get("blocked_by", []))

def state_label(tid, n):
    if n["state"] == "ready-for-agent":
        unmet = [b for b in n.get("blocked_by", []) if tickets.get(b, {}).get("state") != "done"]
        return ("waiting: " + ",".join(unmet)) if unmet else "ELIGIBLE"
    return n["state"]

updated = max((n.get("updated") or "" for n in tickets.values()), default="")

# The fallback table: stdout always; BOARD.md on --write. GitHub renders it inline.
md = ["# Issue Board", "",
      "_Board updated %s · %d tickets · full interactive graph in "
      "`BOARD.html` (open in a browser)_" % (updated, len(tickets)), "",
      "| ticket | state | title | PR |", "|---|---|---|---|"]
for tid in order:
    n = tickets[tid]
    title = " ".join(str(n["title"]).split()).replace("|", "\\|")
    md.append("| %s | %s | %s | %s |" % (tid, state_label(tid, n), title, n.get("pr") or ""))
table = "\n".join(md)
print(table)

if env["BOARD_WRITE"] != "1":
    raise SystemExit(0)

with open(env["BOARD_DIR"] + "/BOARD.md", "w") as f:
    f.write(table + "\n")

# --- the interactive graph (BOARD.html) ---
CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev", "blocked": "s_blk",
         "needs-info": "s_info", "deferred": "s_def", "wontfix": "s_wf"}
def cls(tid, n):
    if n["state"] == "ready-for-agent":
        return "s_elig" if eligible(tid, n) else "s_wait"
    return CLASS.get(n["state"], "s_wait")

# Longest-path layering over blocked_by (blockers above dependents); memoized,
# and cycle-tolerant for a hand-edited map (a back-edge just resolves to 0).
LAYER = {}
def layer(tid, seen):
    if tid in LAYER:
        return LAYER[tid]
    if tid in seen:
        return 0
    bs = [b for b in tickets[tid].get("blocked_by", []) if b in tickets]
    lv = 0 if not bs else 1 + max(layer(b, seen | {tid}) for b in bs)
    LAYER[tid] = lv
    return lv
for t in order:
    layer(t, set())

def root(tid):
    seen, p = set(), tid
    while tickets[p].get("parent") in tickets and tickets[p]["parent"] not in seen:
        seen.add(p); p = tickets[p]["parent"]
    return p

def descendants(tid):
    out, seen, stack = [], set(), [c for c in order if tickets[c].get("parent") == tid]
    while stack:
        c = stack.pop()
        if c in seen or c not in tickets:
            continue
        seen.add(c); out.append(c)
        stack.extend(k for k in order if tickets[k].get("parent") == c)
    return sorted(out, key=num)

# Coordinates: give each top-level cluster (epic tree or lone node) its own
# disjoint column band, so an epic's bounding box can only ever enclose its own
# members — a non-member lives in another band, at another x. Layer sets the row.
COL, ROW = 210, 110
clusters = {}
for t in order:
    clusters.setdefault(root(t), []).append(t)
col_start, next_col = {}, 0
for rt in sorted(clusters, key=num):
    per_layer = {}
    for t in clusters[rt]:
        per_layer.setdefault(LAYER[t], []).append(t)
    col_start[rt] = next_col
    next_col += max(len(v) for v in per_layer.values())
pos = {}
for rt in sorted(clusters, key=num):
    per_layer = {}
    for t in clusters[rt]:
        per_layer.setdefault(LAYER[t], []).append(t)
    for lv, members in per_layer.items():
        for i, t in enumerate(sorted(members, key=num)):
            pos[t] = ((col_start[rt] + i) * COL, lv * ROW)

nodes = []
for t in order:
    n = tickets[t]; x, y = pos[t]
    nodes.append({
        "id": t, "state": n["state"], "eligible": eligible(t, n),
        "cls": cls(t, n), "label": state_label(t, n),
        "title": " ".join(str(n["title"]).split()),
        "category": n.get("category"), "note": n.get("note"),
        "blocked_by": n.get("blocked_by", []), "spawned_by": n.get("spawned_by"),
        "relates_to": n.get("relates_to", []) or [], "branch": n.get("branch"),
        "pr": n.get("pr"), "md": n.get("md"),
        "created": n.get("created"), "updated": n.get("updated"),
        "x": x, "y": y,
    })

edges = []
seen_rel = set()
for t in order:
    n = tickets[t]
    for b in n.get("blocked_by", []):
        if b in tickets:
            edges.append({"from": b, "to": t,
                          "kind": "block-done" if tickets[b]["state"] == "done" else "block-active"})
    sb = n.get("spawned_by")
    if sb in tickets:
        edges.append({"from": sb, "to": t, "kind": "spawned"})
    for r in n.get("relates_to", []) or []:
        if r in tickets and (r, t) not in seen_rel:
            seen_rel.add((t, r))
            edges.append({"from": t, "to": r, "kind": "relates"})

epx = [{"id": e, "descendants": descendants(e)} for e in sorted(epics, key=num) if e in tickets]
payload = {"meta": {"updated": updated, "count": len(tickets)},
           "nodes": nodes, "edges": edges, "epics": epx}

# Embed in a <script> block: neutralize <, >, & so a title can't break out.
data = json.dumps(payload, indent=2).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
with open(env["BOARD_TEMPLATE"]) as f:
    tpl = f.read()
with open(env["BOARD_DIR"] + "/BOARD.html", "w") as f:
    f.write(tpl.replace("__BOARD_PAYLOAD__", data))
PY

if [ "$write" -eq 1 ]; then
  echo "wrote $BOARD_DIR/BOARD.md and $BOARD_DIR/BOARD.html" >&2
fi
