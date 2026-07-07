#!/usr/bin/env bash
# board-map.sh — human telemetry for the board.
#
# Usage: board-map.sh [--write | --serve | --stop]
#
#   (default)  print the fallback table (ticket · state · title · PR) to stdout
#   --write    render two caches of the live GitHub board into
#              doperpowers/issue-tracker/ (gitignored — render caches never
#              commit): BOARD.html — the primary view: an interactive
#              layered-DAG (pan/zoom, click a node for detail, filter by state,
#              collapse epics) with a kanban toggle (the same tickets pivoted
#              into state columns), opened in a browser; and BOARD.md — a
#              minimal node/state table.
#   --serve    --write, plus serve the render dir over http on 127.0.0.1 (a
#              deterministic per-repo port; override with $BOARD_PORT) and open
#              the board in a browser ($BOARD_NO_OPEN=1 suppresses). Served
#              tabs HOT-RELOAD: the page polls for changes and re-renders in
#              place, so any later render — an explicit --write, or the
#              automatic one every mutating board script fires while the
#              server is up — appears without a manual refresh. file:// opens
#              of BOARD.html stay static (a file page cannot fetch anything).
#   --stop     stop the --serve server.
#
# Reading BOARD.html: dependencies flow left→right (a blocker sits left of its
# dependents). Card color = state; ELIGIBLE (ready-for-agent + all blockers done,
# not an epic) glows blue; in-progress pulses green. An amber arrow is an ACTIVE
# block (green while its blocker is itself being worked), a dim dashed one a
# satisfied dependency; labeled dashed lines carry spawned/relates lineage; each
# epic is a labeled box around its members (click the epic's card to collapse).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"

write=0 serve=0
case "${1:-}" in
  "") ;;
  --write) write=1 ;;
  --serve) write=1; serve=1 ;;
  --stop)
    if srv_pid="$(_board_server_pid)"; then
      kill "$srv_pid"
      echo "board server stopped" >&2
    else
      echo "no board server running" >&2
    fi
    rm -f "$BOARD_DIR/.server.pid"
    exit 0
    ;;
  *) die "unknown option: $1 (usage: board-map.sh [--write | --serve | --stop])" ;;
esac
[ "$write" -eq 1 ] && _render_dir

# Serialize renders: concurrent --write runs (the background ones mutating
# scripts fire) fetch independently, so an older, slower render could otherwise
# os.replace AFTER a newer one and revert the page to a stale snapshot. Holding
# the lock across fetch+render makes replace order = fetch order. mkdir is the
# portable atomic lock; a crashed holder's stale lock is broken after ~20s
# (far beyond any real render) rather than blocking forever.
if [ "$write" -eq 1 ]; then
  _render_lock="$BOARD_DIR/.render.lock"
  _lock_ok=0
  for _ in $(seq 1 40); do
    if mkdir "$_render_lock" 2>/dev/null; then _lock_ok=1; break; fi
    sleep 0.5
  done
  if [ "$_lock_ok" -eq 0 ]; then   # stale lock: break it and take over
    rmdir "$_render_lock" 2>/dev/null || true
    mkdir "$_render_lock" 2>/dev/null || true
  fi
  trap 'rmdir "$_render_lock" 2>/dev/null' EXIT
fi

# One python pass per call: it always prints the fallback table to stdout, and
# on --write it also writes BOARD.md and renders BOARD.html — the table and the
# graph share the single board snapshot (one fetch, not two).
BOARD_DIR="$BOARD_DIR" BOARD_TEMPLATE="$SCRIPT_DIR/board-map.template.html" \
BOARD_WRITE="$write" _py - <<'PY'
import json
import os
import _board as B

env = os.environ
tickets = B.snapshot()

def num(t): return int(t)
order = sorted(tickets, key=num)
epics = {n["parent"] for n in tickets.values() if n.get("parent")}

def eligible(tid, n):
    if tid in epics or n["state"] != "ready-for-agent":
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n.get("blocked_by", []))

def state_label(tid, n):
    if n["state"] == "ready-for-agent":
        unmet = [b for b in n.get("blocked_by", []) if tickets.get(b, {}).get("state") != "done"]
        return ("waiting: " + ",".join("#%s" % b for b in unmet)) if unmet else "ELIGIBLE"
    return n["state"]

updated = max((n.get("updated") or "" for n in tickets.values()), default="")

# The fallback table: stdout always; BOARD.md on --write.
md = ["# Issue Board", "",
      "_Board updated %s · %d tickets · full interactive graph in "
      "`BOARD.html` (open in a browser)_" % (updated, len(tickets)), "",
      "| ticket | priority | state | title | PR |", "|---|---|---|---|---|"]
for tid in order:
    n = tickets[tid]
    title = " ".join(str(n["title"]).split()).replace("|", "\\|")
    # Prefer the native GitHub-linked PRs (same source the HTML panel uses); fall
    # back to the manual pr: meta so a hand-entered PR URL still shows.
    prs = n.get("prs") or []
    pr_cell = " ".join("#%s" % p["num"] for p in prs) or (n.get("pr") or "")
    md.append("| #%s | %s | %s | %s | %s |"
              % (tid, n.get("priority") or "", state_label(tid, n), title, pr_cell))
table = "\n".join(md)
print(table)

if env["BOARD_WRITE"] != "1":
    raise SystemExit(0)

with open(env["BOARD_DIR"] + "/BOARD.md", "w") as f:
    f.write(table + "\n")

# --- the interactive graph (BOARD.html) ---
CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev", "blocked": "s_blk",
         "needs-info": "s_info", "deferred": "s_def", "wontfix": "s_wf",
         "conflict": "s_conflict", "untracked": "s_untracked"}
def cls(tid, n):
    if n["state"] == "ready-for-agent":
        return "s_elig" if eligible(tid, n) else "s_wait"
    return CLASS.get(n["state"], "s_wait")

# Longest-path layering over blocked_by (blockers above dependents); memoized,
# and cycle-tolerant (a back-edge just resolves to 0).
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

# Rendered edges that can visually cross: blocked_by (block), spawned_by
# (spawned), relates_to (relates). Parent edges draw as epic BOXES, not lines,
# so they never cross — the neighbor set below deliberately excludes them.
nbr = {t: set() for t in order}
for t in order:
    n = tickets[t]
    for b in n.get("blocked_by", []):
        if b in tickets:
            nbr[t].add(b); nbr[b].add(t)
    sb = n.get("spawned_by")
    if sb in tickets:
        nbr[t].add(sb); nbr[sb].add(t)
    for r in n.get("relates_to", []) or []:
        if r in tickets:
            nbr[t].add(r); nbr[r].add(t)

# Within-layer ordering: crossing minimization by barycenter, constrained to a
# cluster's own band (a node never leaves its swimlane, so an epic's bounding
# box stays honest). Fully deterministic (no Date/random) and never worse than
# the id-stable baseline: the numeric-id order is always a candidate and we keep
# whichever order has the fewest actual crossings — a graph the heuristic can't
# improve renders byte-identical to before.
def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])
def _seg_cross(p1, p2, p3, p4):  # proper intersection; shared endpoints don't count
    return ((_ccw(p3, p4, p1) > 0) != (_ccw(p3, p4, p2) > 0) and
            (_ccw(p1, p2, p3) > 0) != (_ccw(p1, p2, p4) > 0))
def _bary(t, ix, cset):
    ns = [ix[u] for u in nbr[t] if u in cset]
    return sum(ns) / len(ns) if ns else ix[t]

def order_cluster(members):
    cset = set(members)
    per_layer = {}
    for t in members:
        per_layer.setdefault(LAYER[t], []).append(t)
    for lv in per_layer:
        per_layer[lv].sort(key=num)
    # this cluster's rendered edges, once each (as BOARD.html draws them),
    # as (u, v) segments — direction is irrelevant to a crossing count.
    ce, seen_rel = [], set()
    for t in sorted(cset, key=num):
        n = tickets[t]
        for b in n.get("blocked_by", []):
            if b in cset: ce.append((b, t))
        sb = n.get("spawned_by")
        if sb in cset: ce.append((sb, t))
        for r in n.get("relates_to", []) or []:
            if r in cset and (r, t) not in seen_rel:
                seen_rel.add((t, r)); ce.append((t, r))
    def slots(o):
        m = {}
        for lst in o.values():
            for i, t in enumerate(lst): m[t] = i
        return m
    def crossings(o):
        xy = {t: (i, LAYER[t]) for t, i in slots(o).items()}
        c = 0
        for i in range(len(ce)):
            a, b = ce[i]
            for j in range(i + 1, len(ce)):
                d, e = ce[j]
                if len({a, b, d, e}) == 4 and _seg_cross(xy[a], xy[b], xy[d], xy[e]):
                    c += 1
        return c
    best = {lv: list(v) for lv, v in per_layer.items()}
    best_x = crossings(best)
    cur = {lv: list(v) for lv, v in per_layer.items()}
    for it in range(6):
        seq = sorted(per_layer, reverse=bool(it % 2))
        ix = slots(cur)
        for lv in seq:
            cur[lv] = sorted(cur[lv], key=lambda t, ix=ix: (_bary(t, ix, cset), num(t)))
            ix = slots(cur)
        x = crossings(cur)
        if x < best_x:
            best_x, best = x, {lv: list(v) for lv, v in cur.items()}
        if best_x == 0:
            break
    return best

# Coordinates: the board renders as a left→right layered DAG (the agent-harness
# orientation: layer = x, so a blocker sits LEFT of its dependents). Each
# top-level cluster (epic tree or lone node) gets its own disjoint band on the
# slot axis, so an epic's bounding box can only ever enclose its own members.
# Band width is the max nodes-per-layer (order-independent). Two levers cut
# crossings without ever breaking that containment: WITHIN a band, the slot a
# node takes (order_cluster, above); and the ORDER of the bands themselves
# (below), which cuts crossings among the edges that span clusters. All of the
# ordering math runs in abstract (slot, layer) units — the transpose to screen
# px happens only at the final pos emit (segment crossings are invariant under
# swapping axes, so the minimization is orientation-blind).
XCOL, YROW = 240, 100   # px per layer step (card 168 + edge gap) / per slot step (card 74 + gap)
clusters = {}
for t in order:
    clusters.setdefault(root(t), []).append(t)

# Within-band slot + band width, computed once per cluster. The within-band
# barycenter looks only inside its own band (order_cluster's cset filter), so
# this is independent of where the band eventually sits — the two levers stay
# orthogonal, and band reordering never disturbs a settled within-band layout.
local, width = {}, {}
for rt in clusters:
    slot, w = {}, 0
    for lv, lst in order_cluster(clusters[rt]).items():
        w = max(w, len(lst))
        for i, t in enumerate(lst):
            slot[t] = i
    local[rt], width[rt] = slot, w

# Band order: reorder the swimlanes along the slot axis to cut crossings among
# the edges that span two clusters. Same discipline as the within-band pass — pure,
# deterministic, never worse than the id-stable baseline (id-order is the first
# candidate and we only ever keep a strictly-fewer-crossings order). The classic
# Sugiyama recipe: a barycenter sweep for a good global order, then a transpose
# pass (adjacent-band swaps) to clear the crossings barycenter's mirror-symmetry
# leaves behind. Skipped wholesale when no edge spans clusters — then id-order is
# already optimal and the bands render byte-identical to before.
roots = sorted(clusters, key=num)
gce, seen_g = [], set()
for t in order:
    n = tickets[t]
    for b in n.get("blocked_by", []):
        if b in tickets: gce.append((b, t))
    sb = n.get("spawned_by")
    if sb in tickets: gce.append((sb, t))
    for r in n.get("relates_to", []) or []:
        if r in tickets and (r, t) not in seen_g:
            seen_g.add((t, r)); gce.append((t, r))
rootof = {t: root(t) for t in order}
cl_nbr = {rt: set() for rt in roots}
gspan = [rootof[u] != rootof[v] for (u, v) in gce]  # does this edge span two bands?
for (u, v), sp in zip(gce, gspan):
    if sp:
        cl_nbr[rootof[u]].add(rootof[v]); cl_nbr[rootof[v]].add(rootof[u])

def _starts(seq):
    cs, acc = {}, 0
    for rt in seq:
        cs[rt] = acc; acc += width[rt]
    return cs
# Only crossings that involve a cluster-SPANNING edge can change with band order:
# permuting bands slides whole clusters (frozen internal shape) across disjoint
# column ranges, so intra-cluster pairs are invariant. Counting just the pairs
# that touch a spanning edge drops the same constant from every candidate — the
# argmin (and the never-worse-than-baseline guarantee) is preserved while the
# cost falls from O(E^2) to O(S*E), which matters on a large board with few
# cross-epic edges (this runs on every board write).
def board_crossings(seq):
    cs = _starts(seq)
    xy = {t: (cs[rt] + local[rt][t], LAYER[t]) for rt in seq for t in clusters[rt]}
    c = 0
    for i in range(len(gce)):
        a, b = gce[i]
        si = gspan[i]
        for j in range(i + 1, len(gce)):
            if not (si or gspan[j]):
                continue
            d, e = gce[j]
            if len({a, b, d, e}) == 4 and _seg_cross(xy[a], xy[b], xy[d], xy[e]):
                c += 1
    return c

best_seq = list(roots)
if any(cl_nbr.values()):
    best_x = board_crossings(best_seq)
    cur = list(roots)
    for it in range(6):  # barycenter sweep, keeping the fewest-crossings order
        idx = {rt: i for i, rt in enumerate(cur)}
        bary = {}
        for rt in cur:
            ns = [idx[o] for o in cl_nbr[rt]]
            bary[rt] = sum(ns) / len(ns) if ns else idx[rt]
        cur = sorted(cur, key=lambda rt: (bary[rt], num(rt)))
        x = board_crossings(cur)
        if x < best_x:
            best_x, best_seq = x, list(cur)
        if best_x == 0:
            break
    passes = 0                       # transpose refinement on the true count
    while best_x and passes < len(best_seq):
        passes += 1
        moved = False
        for i in range(len(best_seq) - 1):
            cand = list(best_seq)
            cand[i], cand[i + 1] = cand[i + 1], cand[i]
            x = board_crossings(cand)
            if x < best_x:
                best_x, best_seq, moved = x, cand, True
        if not moved:
            break

# Shelf-pack the top-level bands into a grid instead of one long strip, so the
# board fills the frame. In the transposed (left→right) orientation a band is a
# ROW of the screen: N mostly independent tickets laid in a single column of
# bands is an N-tall, ~1-wide sliver that auto-fits tiny; wrapping the bands
# into shelves (stacked vertically, shelves side by side) fills the frame and
# multiplies the readable zoom. Each cluster stays a contiguous block placed at
# one shelf origin, so the disjoint-band guarantee still holds — an epic's
# bounding box encloses only its own members. best_seq's crossing-minimized
# order is preserved; we only wrap it. Shelf capacity = the one whose packed
# bounding box best matches a landscape aspect (fitView in the template does
# the final viewport scaling). The packer itself works in abstract
# (slot, layer) units; only the score and the pos emit apply the transpose.
cheight = {rt: 1 + max(LAYER[t] for t in clusters[rt]) for rt in clusters}
TARGET_ASPECT = 2.4      # packed width:height — landscape, near a typical viewport

def _pack(shelf_cols):
    place, cx, top, sh, maxx = {}, 0, 0, 0, 0
    for rt in best_seq:
        w = width[rt]
        if cx and cx + w > shelf_cols:          # this cluster overflows the shelf → wrap
            top += sh; cx = sh = 0
        place[rt] = (cx, top)
        maxx = max(maxx, cx + w); cx += w; sh = max(sh, cheight[rt])
    return place, maxx, top + sh

shelf = {}
if clusters:   # an empty board still renders (the Pages workflow runs pre-first-ticket)
    _widest, _total = max(width.values()), sum(width.values())
    _best = None
    for _sc in range(_widest, _total + 1):       # widest single cluster … one full shelf
        _place, _slots, _layers = _pack(_sc)
        # transposed screen extents: layers run along x, slots along y
        _score = abs((_layers * XCOL) / (_slots * YROW) - TARGET_ASPECT)
        if _best is None or _score < _best[0]:
            _best = (_score, _place)
    shelf = _best[1]

pos = {}   # the one transpose point: x ← layer axis, y ← slot axis
for rt in best_seq:
    b_slot, b_layer = shelf[rt]
    for t in clusters[rt]:
        pos[t] = ((b_layer + LAYER[t]) * XCOL, (b_slot + local[rt][t]) * YROW)

# Payload ids are display ids ("#42") — nodes, edges, and epics use them
# consistently, so the template needs no notion of the raw number.
def did(t): return "#" + t

nodes = []
for t in order:
    n = tickets[t]; x, y = pos[t]
    nodes.append({
        "id": did(t), "state": n["state"], "eligible": eligible(t, n),
        "cls": cls(t, n), "label": state_label(t, n),
        "title": " ".join(str(n["title"]).split()),
        "category": n.get("category"), "note": n.get("note"),
        "blocked_by": [did(b) for b in n.get("blocked_by", [])],
        "spawned_by": did(n["spawned_by"]) if n.get("spawned_by") else None,
        "relates_to": [did(r) for r in n.get("relates_to", []) or []],
        "priority": n.get("priority"),
        "branch": n.get("branch"), "pr": n.get("pr"), "prs": n.get("prs") or [],
        "md": n.get("url"),
        "created": n.get("created"), "updated": n.get("updated"),
        "x": x, "y": y,
    })

edges = []
seen_rel = set()
for t in order:
    n = tickets[t]
    for b in n.get("blocked_by", []):
        if b in tickets:
            edges.append({"from": did(b), "to": did(t),
                          "kind": "block-done" if tickets[b]["state"] == "done" else "block-active"})
    sb = n.get("spawned_by")
    if sb in tickets:
        edges.append({"from": did(sb), "to": did(t), "kind": "spawned"})
    for r in n.get("relates_to", []) or []:
        if r in tickets and (r, t) not in seen_rel:
            seen_rel.add((t, r))
            edges.append({"from": did(t), "to": did(r), "kind": "relates"})

epx = [{"id": did(e), "descendants": [did(d) for d in descendants(e)]}
       for e in sorted(epics, key=num) if e in tickets]
payload = {"meta": {"updated": updated, "count": len(tickets)},
           "nodes": nodes, "edges": edges, "epics": epx}

# Embed in a <script> block: neutralize <, >, & so a title can't break out.
data = json.dumps(payload, indent=2).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
with open(env["BOARD_TEMPLATE"]) as f:
    tpl = f.read()
# Atomic swap: a --serve http.server (and its hot-reloading tabs) must never
# see a half-written page; unique tmp names keep concurrent renders (the
# background ones mutating scripts fire) from clobbering each other's tmp.
import tempfile
import time
fd, tmp = tempfile.mkstemp(dir=env["BOARD_DIR"], prefix=".BOARD.html.")
with os.fdopen(fd, "w") as f:
    f.write(tpl.replace("__BOARD_PAYLOAD__", data))
os.replace(tmp, env["BOARD_DIR"] + "/BOARD.html")
# Exact change token for the hot-reload poller: header fingerprinting alone
# (second-resolution Last-Modified + Content-Length) can miss a same-second,
# same-length rewrite — the rev file cannot.
fd, tmp = tempfile.mkstemp(dir=env["BOARD_DIR"], prefix=".BOARD.rev.")
with os.fdopen(fd, "w") as f:
    f.write(str(time.time_ns()))
os.replace(tmp, env["BOARD_DIR"] + "/BOARD.rev")
PY

if [ "$write" -eq 1 ]; then
  echo "wrote $BOARD_DIR/BOARD.md and $BOARD_DIR/BOARD.html" >&2
fi

if [ "$serve" -eq 1 ]; then
  # Deterministic per-repo port (boards in different checkouts don't collide);
  # cksum is POSIX and stable across runs, unlike python's randomized hash().
  port="${BOARD_PORT:-$(printf %s "$BOARD_DIR" | cksum | awk '{ print 8420 + ($1 % 500) }')}"
  url="http://127.0.0.1:$port/BOARD.html"
  pidfile="$BOARD_DIR/.server.pid"
  if _board_server_pid >/dev/null 2>&1; then
    echo "board server already up — open tabs hot-reload on every render: $url" >&2
  else
    # A dumb static server is all hot reload needs: the page polls its own
    # caching headers and re-fetches itself when a render changes the file.
    # exec makes the backgrounded subshell BECOME python, so $! is the real
    # server pid (killable by --stop) and no wrapper shell lingers holding
    # this script's stdout pipe open.
    (cd "$BOARD_DIR" && exec nohup python3 -m http.server "$port" --bind 127.0.0.1 \
       >/dev/null 2>&1) &
    srv_pid=$!
    echo "$srv_pid" > "$pidfile"
    # Return only once the server actually answers (a bind failure exits python
    # immediately, so alive + answering ⇒ it is OUR server on the port).
    ready=0
    for _ in $(seq 1 12); do
      kill -0 "$srv_pid" 2>/dev/null || break
      if curl -fsS -o /dev/null --max-time 1 "$url" 2>/dev/null; then ready=1; break; fi
      sleep 0.25
    done
    [ "$ready" -eq 1 ] \
      || { kill "$srv_pid" 2>/dev/null || true; rm -f "$pidfile"
           die "server failed to start — port $port in use? (set BOARD_PORT)"; }
    echo "board server started: $url" >&2
    if [ -z "${BOARD_NO_OPEN:-}" ]; then
      case "$(uname)" in
        Darwin) open "$url" ;;
        *) xdg-open "$url" >/dev/null 2>&1 || true ;;
      esac
    fi
  fi
  echo "$url"
fi
