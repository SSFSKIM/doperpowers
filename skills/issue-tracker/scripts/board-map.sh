#!/usr/bin/env bash
# board-map.sh — human telemetry: render the board DAG as a Mermaid flowchart.
#
# Usage: board-map.sh [--write]
#
#   (default)  print the markdown (mermaid graph + legend + PR links) to stdout
#   --write    also save it to doperpowers/issue-tracker/MAP.md — committable,
#              and GitHub renders the mermaid block natively
#
# Reading the map: node color = state; ELIGIBLE (ready-for-agent + all
# blockers done, not an epic) gets a thick green border; a thick arrow is an
# ACTIVE block, a dotted arrow a satisfied one (blocker already done);
# labeled dotted arrows carry lineage (spawned) / relates edges; epics are
# boxes (subgraphs) around their children.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ -f "$MAP" ] || die "no board at $MAP (nothing registered yet)"

write=0
[ "${1:-}" = "--write" ] && write=1

out="$(_py - <<'PY'
import json, os

with open(os.environ["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]

def num(tid): return int(tid[1:])
order = sorted(tickets, key=num)
epics = {n["parent"] for n in tickets.values() if n.get("parent")}
children = {}
for tid in order:
    p = tickets[tid].get("parent")
    if p:
        children.setdefault(p, []).append(tid)

def eligible(tid, n):
    if tid in epics or n["state"] != "ready-for-agent":
        return False
    return all(tickets.get(b, {}).get("state") == "done"
               for b in n.get("blocked_by", []))

CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev",
         "blocked": "s_blk", "needs-info": "s_info", "deferred": "s_def",
         "wontfix": "s_wf"}
def cls(tid, n):
    if n["state"] == "ready-for-agent":
        return "s_elig" if eligible(tid, n) else "s_wait"
    return CLASS.get(n["state"], "s_wait")

def label(tid, n):
    # One-line title, quotes stripped (they would close the mermaid string),
    # truncated so the graph stays scannable; state as a second label line.
    t = " ".join(str(n["title"]).split()).replace('"', "'")
    if len(t) > 48:
        t = t[:47] + "…"
    state = n["state"]
    if state == "ready-for-agent":
        unmet = [b for b in n.get("blocked_by", [])
                 if tickets.get(b, {}).get("state") != "done"]
        state = ("waiting: " + ",".join(unmet)) if unmet else "ELIGIBLE"
    return '%s["%s · %s<br/><i>%s</i>"]' % (tid, tid, t, state)

lines = ["flowchart TD"]
for d in [
    "classDef s_done fill:#d3f9d8,stroke:#2b8a3e,color:#1b4332",
    "classDef s_prog fill:#d0ebff,stroke:#1971c2,color:#1c3f5e",
    "classDef s_rev fill:#e5dbff,stroke:#6741d9,color:#3b2b73",
    "classDef s_elig fill:#ffffff,stroke:#2b8a3e,stroke-width:3px,color:#1b4332",
    "classDef s_wait fill:#f1f3f5,stroke:#adb5bd,color:#495057",
    "classDef s_blk fill:#ffe3e3,stroke:#c92a2a,color:#5f1414",
    "classDef s_info fill:#fff3bf,stroke:#e67700,color:#5c3c00",
    "classDef s_def fill:#f1f3f5,stroke:#adb5bd,stroke-dasharray: 5 5,color:#868e96",
    "classDef s_wf fill:#dee2e6,stroke:#495057,stroke-dasharray: 3 3,color:#495057",
]:
    lines.append("  " + d)

emitted = set()
def emit(tid, indent):
    # Epics nest as subgraphs (recursion covers epics inside epics); a cycle
    # in hand-edited parent fields must not hang the renderer.
    if tid in emitted:
        return
    emitted.add(tid)
    pad = "  " * indent
    n = tickets[tid]
    if tid in epics:
        t = " ".join(str(n["title"]).split()).replace('"', "'")
        state = n["state"]
        lines.append('%ssubgraph %s["%s · %s · %s"]' % (pad, tid, tid, t, state))
        for c in children.get(tid, []):
            emit(c, indent + 1)
        lines.append("%send" % pad)
    else:
        lines.append(pad + label(tid, n))

for tid in order:
    if not tickets[tid].get("parent"):
        emit(tid, 1)
for tid in order:  # orphans under a cyclic/missing parent still render
    emit(tid, 1)

seen_rel = set()
for tid in order:
    n = tickets[tid]
    for b in n.get("blocked_by", []):
        if b not in tickets:
            continue
        arrow = "-.->" if tickets[b]["state"] == "done" else "==>"
        lines.append("  %s %s %s" % (b, arrow, tid))
    sb = n.get("spawned_by")
    if sb and sb in tickets:
        lines.append("  %s -. spawned .-> %s" % (sb, tid))
    for r in n.get("relates_to", []) or []:
        if r in tickets and (r, tid) not in seen_rel:
            seen_rel.add((tid, r))
            lines.append("  %s -. relates .- %s" % (tid, r))

for tid in order:
    lines.append("  class %s %s" % (tid, cls(tid, tickets[tid])))

updated = max((n.get("updated") or "" for n in tickets.values()), default="")
md = []
md.append("# Issue Board Map")
md.append("")
md.append("_Board updated %s · %d tickets · regenerate with `board-map.sh --write`_"
          % (updated, len(tickets)))
md.append("")
md.append("```mermaid")
md.extend(lines)
md.append("```")
md.append("")
md.append("**Legend** — green: done · blue: in-progress · violet: in-review · "
          "thick green border: ELIGIBLE (dispatchable now) · gray: waiting · "
          "red: blocked · amber: needs-info · dashed: deferred/wontfix. "
          "Thick arrow = active block, dotted = satisfied dependency; "
          "labeled dotted arrows = spawned/relates lineage. "
          "Epic boxes wrap their children.")
links = [(tid, tickets[tid]) for tid in order if tickets[tid].get("pr")]
if links:
    md.append("")
    md.append("| ticket | state | PR |")
    md.append("|---|---|---|")
    for tid, n in links:
        md.append("| %s | %s | %s |" % (tid, n["state"], n["pr"]))
print("\n".join(md))
PY
)"

printf '%s\n' "$out"
if [ "$write" -eq 1 ]; then
  printf '%s\n' "$out" > "$BOARD_DIR/MAP.md"
  echo "wrote $BOARD_DIR/MAP.md" >&2
fi
