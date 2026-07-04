# Issue Board Interactive HTML Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the board's human view with an interactive, self-contained `MAP.html` (layered DAG: pan/zoom, click-to-detail, state filter, collapsible epics) while shrinking the Mermaid `MAP.md` to a minimal node/state table kept as a GitHub-inline fallback.

**Architecture:** All change is contained to `skills/issue-tracker/scripts/board-map.sh` plus one new sibling template `board-map.template.html`. `board-map.sh`'s Python computes a **deterministic** layered-DAG layout from `map.json` and injects a data payload into the template to write `MAP.html`; a second, smaller Python emits the minimal Markdown table to stdout and to `MAP.md`. Every other board script already ends with `board-map.sh --write` and is **not touched** — the new behavior rides entirely inside `board-map.sh`. The interactive layer is inline vanilla JS/SVG (no external requests, no vendored library); the layout is a pure function of `map.json` (no `Date.now`/randomness) so committed diffs stay stable and tests assert structure.

**Tech Stack:** Bash + inline `python3` (existing board toolkit pattern), self-contained HTML/CSS/SVG + vanilla JS. Tested by the hermetic bash harness `tests/issue-tracker/test-board-scripts.sh`.

## Global Constraints

- **Zero third-party dependencies.** No CDN references, external stylesheets, fonts, or vendored graph libraries. `MAP.html` is one self-contained file, openable offline. (`CLAUDE.md`: "zero-dependency plugin by design".)
- **Single-writer rule is untouched.** `board-map.sh` sources `_lib.sh`, which refuses to run from a linked worktree. Do not change `_lib.sh`.
- **Deterministic output.** The layout and payload are pure functions of `map.json`. No wall-clock, no randomness. The header timestamp is `max(ticket.updated)` from the data.
- **Both render files are committed caches** of `map.json`: `MAP.html` (primary) and `MAP.md` (fallback). Never hand-edited.
- **Append-only test additions.** The suite asserts exact `log.jsonl` line counts and `board-list` row counts at fixed points (e.g. `tests/issue-tracker/test-board-scripts.sh:127`, `:297`). New tests append **after** the last such assertion; do not renumber earlier tickets.
- **XSS/breakout hardening.** Ticket titles/notes are semi-trusted text. The JSON embedded in a `<script>` block escapes `<`, `>`, `&`; the detail panel escapes text before `innerHTML`. (Matches the board's existing title/evidence hardening.)
- **Lint gate:** `scripts/lint-shell.sh` must pass on `board-map.sh` (it runs `shellcheck --severity=warning --external-sources --source-path=SCRIPTDIR`).

---

### Task 1: HTML render pipeline (additive — Mermaid `MAP.md` untouched)

Add the interactive `MAP.html` output. In this task `board-map.sh --write` writes **both** the existing Mermaid `MAP.md` (unchanged) and the new `MAP.html`. Because nothing existing changes, the current suite stays green and we only *add* assertions. Task 2 then shrinks `MAP.md`.

**Files:**
- Create: `skills/issue-tracker/scripts/board-map.template.html`
- Modify: `skills/issue-tracker/scripts/board-map.sh` (add an HTML-rendering `python3` block to the `--write` branch)
- Test: `tests/issue-tracker/test-board-scripts.sh` (append a new `board-map (html)` section after the existing `board-edge` section, i.e. after line 408)

**Interfaces:**
- Produces — the injected payload schema that the template's JS consumes:
  ```
  { "meta":  {"updated": <str>, "count": <int>},
    "nodes": [ {"id","state","eligible","cls","label","title","category","note",
                "blocked_by":[...],"spawned_by","relates_to":[...],"branch","pr",
                "md","created","updated","x","y"} ],
    "edges": [ {"from","to","kind"} ],   // kind ∈ block-active | block-done | spawned | relates
    "epics": [ {"id","descendants":[...]} ] }
  ```
  `cls` reuses the current Mermaid class mapping (`s_done/s_prog/s_rev/s_elig/s_wait/s_blk/s_info/s_def/s_wf`); `label` reuses the current state-line rule (`ELIGIBLE` / `waiting: T..` / raw state); `x,y` are top-left pixel coordinates.
- Consumes — `board-map.template.html` must contain the literal token `__BOARD_PAYLOAD__` exactly once, inside `<script id="board-data" type="application/json">…</script>`.

- [ ] **Step 1: Write the failing test (append after line 408 of `tests/issue-tracker/test-board-scripts.sh`, before the `# ---- summary ----` block)**

```bash
# ---- board-map (interactive HTML) --------------------------------------------
# Fresh probes with known states so assertions don't depend on the board's
# accumulated end-state. Highest ticket so far is T29 → T30 next.
echo "board-map (html):"

run board-register.sh "HTML blocker" enhancement >/dev/null              # T30
run board-register.sh "HTML dependent" enhancement --blocked-by T30 >/dev/null  # T31
run board-register.sh "HTML spawned child" enhancement --spawned-by T31 >/dev/null # T32
run board-register.sh "HTML epic" enhancement >/dev/null                 # T33
run board-register.sh "HTML epic child" enhancement --parent T33 >/dev/null # T34
run board-relate.sh T30 T32 >/dev/null

run board-map.sh --write >/dev/null 2>&1
assert_file_exists "$BOARD/MAP.html" "--write saves MAP.html in the board dir"

# Whitespace-stripped view lets us grep the injected JSON as compact substrings.
html="$(tr -d '[:space:]' < "$BOARD/MAP.html")"
assert_contains "$html" '"id":"T31","state":"ready-for-agent"' "node T31 present with its state"
assert_contains "$html" '"from":"T30","to":"T31","kind":"block-active"' "active block edge in payload"
assert_contains "$html" '"label":"waiting:T30"' "T31 carries the unmet-blocker label"
assert_contains "$html" '"from":"T31","to":"T32","kind":"spawned"' "spawned lineage edge in payload"
assert_contains "$html" '"from":"T30","to":"T32","kind":"relates"' "relates edge in payload (single direction)"
printf '%s' "$html" | grep -Fq '"from":"T32","to":"T30","kind":"relates"' \
    && fail "relates edge de-duplicated to one direction" || pass "relates edge de-duplicated to one direction"
assert_contains "$html" '"id":"T33","descendants":["T34"]' "epic T33 lists its descendant"
assert_contains "$html" '"id":"T31","eligible":false' "blocked dependent is not eligible"

# Self-contained: no external references anywhere in the file.
ext="$(grep -Eic 'src="https?://|href="https?://[^"]*\.css|cdnjs|unpkg|jsdelivr' "$BOARD/MAP.html" || true)"
assert_equals "$ext" "0" "MAP.html has no external references (self-contained)"

# block-done appears once the blocker lands.
run board-transition.sh T30 in-progress >/dev/null
run board-transition.sh T30 "done" >/dev/null
run board-map.sh --write >/dev/null 2>&1
html="$(tr -d '[:space:]' < "$BOARD/MAP.html")"
assert_contains "$html" '"from":"T30","to":"T31","kind":"block-done"' "satisfied block flips to block-done"
assert_contains "$html" '"id":"T31","eligible":true' "dependent becomes eligible once blocker is done"

# The template token was fully substituted.
printf '%s' "$html" | grep -Fq '__BOARD_PAYLOAD__' \
    && fail "payload token fully substituted" || pass "payload token fully substituted"
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | sed -n '/board-map (html)/,$p'`
Expected: FAIL on "`--write saves MAP.html`" (the file does not exist yet) and the payload greps.

- [ ] **Step 3: Create the template `skills/issue-tracker/scripts/board-map.template.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Issue Board Map</title>
<style>
  :root { font-family: -apple-system, Segoe UI, Roboto, sans-serif; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; }
  body { display: flex; flex-direction: column; height: 100vh; overflow: hidden; color: #212529; }
  #controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
              padding: 8px 12px; border-bottom: 1px solid #dee2e6; background: #f8f9fa; font-size: 13px; }
  #meta { color: #495057; }
  #chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { border: 1px solid #ced4da; background: #fff; border-radius: 12px;
          padding: 2px 10px; font-size: 12px; cursor: pointer; color: #495057; }
  .chip.off { opacity: .4; text-decoration: line-through; }
  .chip.on  { background: #2b8a3e; color: #fff; border-color: #2b8a3e; }
  #reset { margin-left: auto; border: 1px solid #ced4da; background: #fff;
           border-radius: 6px; padding: 3px 10px; cursor: pointer; font-size: 12px; }
  #stage { position: relative; flex: 1; min-height: 0; }
  #board { width: 100%; height: 100%; background: #fff; cursor: grab; }
  #board:active { cursor: grabbing; }
  .edge { fill: none; stroke: #868e96; stroke-width: 2; }
  .edge.block-active { stroke: #495057; stroke-width: 2.5; }
  .edge.block-done   { stroke: #adb5bd; stroke-dasharray: 4 4; }
  .edge.spawned      { stroke: #adb5bd; stroke-dasharray: 2 4; }
  .edge.relates      { stroke: #adb5bd; stroke-dasharray: 1 5; }
  .elabel { fill: #868e96; font-size: 10px; }
  .node { cursor: pointer; }
  .node.dim { opacity: .2; }
  .node .card { stroke-width: 1.5; }
  .node .nid { font-weight: 700; font-size: 12px; }
  .node .ntitle { font-size: 11px; }
  .node .nstate { font-size: 10px; font-style: italic; }
  .epicbox { fill: rgba(73,80,87,.05); stroke: #adb5bd; stroke-dasharray: 3 4; }
  .epiclabel { fill: #868e96; font-size: 11px; font-weight: 600; }
  /* state palette — identical to the Mermaid classDef fills/strokes/text */
  .node.s_done .card { fill: #d3f9d8; stroke: #2b8a3e; } .node.s_done text { fill: #1b4332; }
  .node.s_prog .card { fill: #d0ebff; stroke: #1971c2; } .node.s_prog text { fill: #1c3f5e; }
  .node.s_rev  .card { fill: #e5dbff; stroke: #6741d9; } .node.s_rev  text { fill: #3b2b73; }
  .node.s_elig .card { fill: #ffffff; stroke: #2b8a3e; stroke-width: 3; } .node.s_elig text { fill: #1b4332; }
  .node.s_wait .card { fill: #f1f3f5; stroke: #adb5bd; } .node.s_wait text { fill: #495057; }
  .node.s_blk  .card { fill: #ffe3e3; stroke: #c92a2a; } .node.s_blk  text { fill: #5f1414; }
  .node.s_info .card { fill: #fff3bf; stroke: #e67700; } .node.s_info text { fill: #5c3c00; }
  .node.s_def  .card { fill: #f1f3f5; stroke: #adb5bd; stroke-dasharray: 5 5; } .node.s_def text { fill: #868e96; }
  .node.s_wf   .card { fill: #dee2e6; stroke: #495057; stroke-dasharray: 3 3; } .node.s_wf text { fill: #495057; }
  #detail { position: absolute; top: 0; right: 0; width: 320px; max-width: 90%; height: 100%;
            overflow: auto; background: #fff; border-left: 1px solid #dee2e6;
            padding: 16px; font-size: 13px; box-shadow: -4px 0 12px rgba(0,0,0,.06); }
  #detail[hidden] { display: none; }
  #detail h2 { font-size: 15px; margin: 0 30px 12px 0; word-break: break-word; }
  #dclose { position: absolute; top: 8px; right: 10px; border: 0; background: none;
            font-size: 22px; line-height: 1; cursor: pointer; color: #868e96; }
  .drow { display: grid; grid-template-columns: 84px 1fr; gap: 8px; padding: 4px 0; border-top: 1px solid #f1f3f5; }
  .drow span { color: #868e96; } .drow b { font-weight: 500; word-break: break-word; }
  #legend { padding: 6px 12px; border-top: 1px solid #dee2e6; background: #f8f9fa;
            font-size: 11px; color: #495057; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .lg { border-radius: 4px; padding: 1px 7px; border: 1px solid; }
  .lg.s_done{background:#d3f9d8;border-color:#2b8a3e;color:#1b4332}
  .lg.s_prog{background:#d0ebff;border-color:#1971c2;color:#1c3f5e}
  .lg.s_rev{background:#e5dbff;border-color:#6741d9;color:#3b2b73}
  .lg.s_elig{background:#fff;border-color:#2b8a3e;color:#1b4332}
  .lg.s_wait{background:#f1f3f5;border-color:#adb5bd;color:#495057}
  .lg.s_blk{background:#ffe3e3;border-color:#c92a2a;color:#5f1414}
  .lg.s_info{background:#fff3bf;border-color:#e67700;color:#5c3c00}
  .lg.s_def{background:#f1f3f5;border-color:#adb5bd;color:#868e96}
  .lg.s_wf{background:#dee2e6;border-color:#495057;color:#495057}
  .le { color: #868e96; } .le::before { content: "— "; }
</style>
</head>
<body>
<header id="controls">
  <span id="meta"></span>
  <span id="chips"></span>
  <button id="reset">reset view</button>
</header>
<div id="stage">
  <svg id="board" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
              orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#868e96"/></marker>
    </defs>
    <g id="viewport"></g>
  </svg>
  <aside id="detail" hidden></aside>
</div>
<div id="legend"></div>
<script id="board-data" type="application/json">__BOARD_PAYLOAD__</script>
<script>
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var NODE_W = 180, NODE_H = 54;
  var BOARD = JSON.parse(document.getElementById("board-data").textContent);
  var SVG = document.getElementById("board");
  var VP = document.getElementById("viewport");
  var nodeById = {}, epicById = {};
  BOARD.nodes.forEach(function (n) { nodeById[n.id] = n; });
  BOARD.epics.forEach(function (e) { epicById[e.id] = e; });

  var collapsed = {}, hiddenStates = {}, eligibleOnly = false;
  var tx = 40, ty = 40, k = 1;

  function el(tag, attrs, cls) {
    var e = document.createElementNS(NS, tag), key;
    for (key in attrs) if (attrs.hasOwnProperty(key)) e.setAttribute(key, attrs[key]);
    if (cls) e.setAttribute("class", cls);
    return e;
  }
  function txt(x, y, s, cls) { var t = el("text", { x: x, y: y }, cls); t.textContent = s; return t; }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function clip(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  // Resolve an id to the outermost COLLAPSED epic that hides it (or itself).
  function resolve(id) {
    var hit = BOARD.epics.filter(function (e) {
      return collapsed[e.id] && (e.id === id || e.descendants.indexOf(id) >= 0);
    });
    if (!hit.length) return id;
    var outer = hit.filter(function (e) {
      return !hit.some(function (o) { return o !== e && o.descendants.indexOf(e.id) >= 0; });
    });
    return (outer[0] || hit[0]).id;
  }
  function hiddenBy(n) { return hiddenStates[n.state] || (eligibleOnly && !n.eligible); }
  function bbox(ids) {
    var xs = ids.map(function (i) { return nodeById[i].x; });
    var ys = ids.map(function (i) { return nodeById[i].y; });
    var x = Math.min.apply(null, xs), y = Math.min.apply(null, ys);
    return { x: x, y: y, w: Math.max.apply(null, xs) + NODE_W - x, h: Math.max.apply(null, ys) + NODE_H - y };
  }

  function edgePath(s, t, kind) {
    var x1 = s.x + NODE_W / 2, y1 = s.y + NODE_H, x2 = t.x + NODE_W / 2, y2 = t.y;
    var dy = (y2 - y1) / 2;
    var d = "M" + x1 + "," + y1 + " C" + x1 + "," + (y1 + dy) + " " + x2 + "," + (y2 - dy) + " " + x2 + "," + y2;
    var attrs = { d: d };
    if (kind === "block-active" || kind === "block-done" || kind === "spawned") attrs["marker-end"] = "url(#arrow)";
    return el("path", attrs, "edge " + kind);
  }
  function nodeCard(n) {
    var isEpic = !!epicById[n.id];
    var g = el("g", { transform: "translate(" + n.x + "," + n.y + ")", "data-id": n.id },
      "node " + n.cls + (hiddenBy(n) ? " dim" : ""));
    g.appendChild(el("rect", { x: 0, y: 0, width: NODE_W, height: NODE_H, rx: 8 }, "card"));
    g.appendChild(txt(10, 20, n.id + (isEpic ? (collapsed[n.id] ? "  ▸" : "  ▾") : ""), "nid"));
    g.appendChild(txt(10, 37, clip(n.title, 26), "ntitle"));
    g.appendChild(txt(10, 50, clip(n.label, 30), "nstate"));
    g.addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (isEpic) toggleEpic(n.id);
      showDetail(n);
    });
    return g;
  }

  function render() {
    while (VP.firstChild) VP.removeChild(VP.firstChild);
    var vis = {};
    BOARD.nodes.forEach(function (n) { if (resolve(n.id) === n.id) vis[n.id] = true; });

    BOARD.epics.forEach(function (e) {
      if (collapsed[e.id] || resolve(e.id) !== e.id) return;
      var members = [e.id].concat(e.descendants).filter(function (id) { return vis[id]; });
      if (members.length < 2) return;
      var b = bbox(members);
      VP.appendChild(el("rect", { x: b.x - 14, y: b.y - 26, width: b.w + 28, height: b.h + 40, rx: 10 }, "epicbox"));
      VP.appendChild(txt(b.x - 8, b.y - 12, e.id + " · epic", "epiclabel"));
    });

    var seen = {};
    BOARD.edges.forEach(function (e) {
      var a = resolve(e.from), b = resolve(e.to);
      if (a === b || !vis[a] || !vis[b]) return;
      var key = a + ">" + b + ":" + e.kind;
      if (seen[key]) return; seen[key] = true;
      var p = edgePath(nodeById[a], nodeById[b], e.kind);
      VP.appendChild(p);
      if (e.kind === "spawned" || e.kind === "relates") {
        var s = nodeById[a], t = nodeById[b];
        VP.appendChild(txt((s.x + t.x) / 2 + NODE_W / 2, (s.y + t.y) / 2 + NODE_H / 2, e.kind, "elabel"));
      }
    });

    BOARD.nodes.forEach(function (n) { if (vis[n.id]) VP.appendChild(nodeCard(n)); });
    applyTransform();
  }

  function applyTransform() { VP.setAttribute("transform", "translate(" + tx + "," + ty + ") scale(" + k + ")"); }
  function toggleEpic(id) { if (collapsed[id]) delete collapsed[id]; else collapsed[id] = true; render(); }

  function showDetail(n) {
    var d = document.getElementById("detail");
    function row(kk, vv) {
      return vv ? '<div class="drow"><span>' + kk + "</span><b>" + esc(vv) + "</b></div>" : "";
    }
    var pr = n.pr ? '<div class="drow"><span>PR</span><b><a href="' + esc(n.pr) +
      '" target="_blank" rel="noopener">' + esc(n.pr) + "</a></b></div>" : "";
    d.innerHTML = '<button id="dclose">×</button><h2>' + esc(n.id) + " · " + esc(n.title) + "</h2>" +
      row("state", n.label) + row("category", n.category) + row("note", n.note) +
      row("blocked by", (n.blocked_by || []).join(", ")) + row("spawned by", n.spawned_by) +
      row("relates", (n.relates_to || []).join(", ")) + row("branch", n.branch) + pr +
      row("md", n.md) + row("created", n.created) + row("updated", n.updated);
    d.hidden = false;
    document.getElementById("dclose").onclick = function () { d.hidden = true; };
  }

  function buildChips() {
    var states = [], seen = {}, c = document.getElementById("chips");
    BOARD.nodes.forEach(function (n) { if (!seen[n.state]) { seen[n.state] = true; states.push(n.state); } });
    states.forEach(function (s) {
      var b = document.createElement("button");
      b.className = "chip"; b.textContent = s; b.setAttribute("data-state", s);
      b.onclick = function () {
        if (hiddenStates[s]) { delete hiddenStates[s]; b.classList.remove("off"); }
        else { hiddenStates[s] = true; b.classList.add("off"); }
        render();
      };
      c.appendChild(b);
    });
    var eb = document.createElement("button");
    eb.className = "chip"; eb.textContent = "ELIGIBLE only";
    eb.onclick = function () { eligibleOnly = !eligibleOnly; eb.classList.toggle("on", eligibleOnly); render(); };
    c.appendChild(eb);
  }
  function buildLegend() {
    var L = [["done", "s_done"], ["in-progress", "s_prog"], ["in-review", "s_rev"], ["ELIGIBLE", "s_elig"],
      ["waiting", "s_wait"], ["blocked", "s_blk"], ["needs-info", "s_info"], ["deferred", "s_def"], ["wontfix", "s_wf"]];
    document.getElementById("legend").innerHTML = "<b>state</b> " +
      L.map(function (p) { return '<span class="lg ' + p[1] + '">' + p[0] + "</span>"; }).join(" ") +
      ' &nbsp; <b>edges</b> <span class="le">solid=active block</span> <span class="le">dotted=satisfied/spawned/relates</span>';
  }

  SVG.addEventListener("wheel", function (e) {
    e.preventDefault();
    var r = SVG.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    var nk = Math.min(3, Math.max(0.2, k * Math.exp(-e.deltaY * 0.0015)));
    tx = mx - (mx - tx) * (nk / k); ty = my - (my - ty) * (nk / k); k = nk; applyTransform();
  }, { passive: false });
  var drag = null;
  SVG.addEventListener("mousedown", function (e) {
    if (e.target.closest(".node")) return;
    drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty };
  });
  window.addEventListener("mousemove", function (e) {
    if (!drag) return; tx = drag.tx + (e.clientX - drag.x); ty = drag.ty + (e.clientY - drag.y); applyTransform();
  });
  window.addEventListener("mouseup", function () { drag = null; });
  SVG.addEventListener("click", function (e) {
    if (!e.target.closest(".node")) document.getElementById("detail").hidden = true;
  });
  document.getElementById("reset").onclick = function () { tx = 40; ty = 40; k = 1; applyTransform(); };

  document.getElementById("meta").textContent = BOARD.meta.count + " tickets · updated " + BOARD.meta.updated;
  buildChips(); buildLegend(); render();
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Add the HTML-rendering `python3` block to `board-map.sh`'s `--write` branch**

Replace the final `if [ "$write" -eq 1 ]; then … fi` block (currently `board-map.sh:154-157`) with:

```bash
if [ "$write" -eq 1 ]; then
  printf '%s\n' "$out" > "$BOARD_DIR/MAP.md"
  BOARD_TEMPLATE="$SCRIPT_DIR/board-map.template.html" BOARD_HTML="$BOARD_DIR/MAP.html" _py - <<'PY'
import json, os

with open(os.environ["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]

def num(t): return int(t[1:])
order = sorted(tickets, key=num)
epics = {n["parent"] for n in tickets.values() if n.get("parent")}

def eligible(tid, n):
    if tid in epics or n["state"] != "ready-for-agent":
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n.get("blocked_by", []))

CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev", "blocked": "s_blk",
         "needs-info": "s_info", "deferred": "s_def", "wontfix": "s_wf"}
def cls(tid, n):
    if n["state"] == "ready-for-agent":
        return "s_elig" if eligible(tid, n) else "s_wait"
    return CLASS.get(n["state"], "s_wait")

def state_label(tid, n):
    if n["state"] == "ready-for-agent":
        unmet = [b for b in n.get("blocked_by", []) if tickets.get(b, {}).get("state") != "done"]
        return ("waiting: " + ",".join(unmet)) if unmet else "ELIGIBLE"
    return n["state"]

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

# Coordinates: cluster a layer's nodes by their epic root, then by id.
COL, ROW = 210, 110
by_layer = {}
for t in order:
    by_layer.setdefault(LAYER[t], []).append(t)
pos = {}
for lv in sorted(by_layer):
    for i, t in enumerate(sorted(by_layer[lv], key=lambda t: (num(root(t)), num(t)))):
        pos[t] = (i * COL, lv * ROW)

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
updated = max((n.get("updated") or "" for n in tickets.values()), default="")
payload = {"meta": {"updated": updated, "count": len(tickets)},
           "nodes": nodes, "edges": edges, "epics": epx}

# Embed in a <script> block: neutralize <, >, & so a title can't break out.
data = json.dumps(payload, indent=2).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
with open(os.environ["BOARD_TEMPLATE"]) as f:
    tpl = f.read()
with open(os.environ["BOARD_HTML"], "w") as f:
    f.write(tpl.replace("__BOARD_PAYLOAD__", data))
PY
  echo "wrote $BOARD_DIR/MAP.md and $BOARD_DIR/MAP.html" >&2
fi
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -30`
Expected: the `board-map (html):` block reports all `[PASS]`, and the final line is `ALL TESTS PASSED`.

- [ ] **Step 6: Lint**

Run: `scripts/lint-shell.sh skills/issue-tracker/scripts/board-map.sh`
Expected: exit 0, "Linting 1 shell files" (or the repo's clean-pass wording).

- [ ] **Step 7: Commit**

```bash
git add skills/issue-tracker/scripts/board-map.template.html \
        skills/issue-tracker/scripts/board-map.sh \
        tests/issue-tracker/test-board-scripts.sh
git commit -m "issue-tracker: render interactive MAP.html alongside the Mermaid map"
```

---

### Task 2: Shrink `MAP.md` to a minimal fallback table + repoint the Mermaid assertions

Now that `MAP.html` carries the graph, replace the Mermaid Markdown builder with a graphless node/state table (stdout + `MAP.md`), and repoint the suite's Mermaid-content assertions to `MAP.html` / the new table.

**Files:**
- Modify: `skills/issue-tracker/scripts/board-map.sh` (replace the Mermaid `out` builder and the header comment)
- Test: `tests/issue-tracker/test-board-scripts.sh` (rewrite the `board-map:` section lines 303-323, and the three Mermaid-on-`MAP.md` assertions at lines 338-340 and 356)

**Interfaces:**
- Consumes: the `MAP.html` payload greps and helpers introduced in Task 1.
- Produces: `MAP.md` as a Markdown table `| ticket | state | title | PR |`, one row per ticket in numeric-id order; the eligible label rule is unchanged (`ELIGIBLE` for a dispatchable `ready-for-agent`).

- [ ] **Step 1: Rewrite the `board-map:` test section to expect the table + HTML (replace lines 303-323 of `tests/issue-tracker/test-board-scripts.sh`)**

```bash
# ---- board-map (minimal MD fallback + HTML graph) -----------------------------
echo "board-map:"

run board-register.sh "Map edge probe" enhancement --blocked-by T14 >/dev/null      # T15
run board-register.sh "Map lineage probe" enhancement --spawned-by T15 >/dev/null   # T16
run board-register.sh "Map epic child probe" enhancement --parent T16 >/dev/null    # T17

# Default stdout is now the graphless fallback table, not a mermaid block.
out="$(run board-map.sh)"
assert_contains "$out" "| ticket | state | title | PR |" "map stdout is the fallback table"
printf '%s' "$out" | grep -Fq '```mermaid' && fail "no mermaid in the fallback" || pass "no mermaid in the fallback"
echo "$out" | grep "T14" | grep -q "blocked" && pass "T14 row shows its state" || fail "T14 row shows its state"

run board-map.sh --write >/dev/null 2>&1
assert_file_exists "$BOARD/MAP.md" "--write saves MAP.md (fallback table)"
assert_file_exists "$BOARD/MAP.html" "--write saves MAP.html (graph)"
assert_contains "$(cat "$BOARD/MAP.md")" "| T15 |" "MAP.md table has a row per ticket"

# The graph facts that used to be asserted on the mermaid MAP.md now live in MAP.html.
html="$(tr -d '[:space:]' < "$BOARD/MAP.html")"
assert_contains "$html" '"from":"T14","to":"T15","kind":"block-active"' "active block edge in MAP.html"
assert_contains "$html" '"from":"T15","to":"T16","kind":"spawned"' "lineage edge in MAP.html"
assert_contains "$html" '"id":"T16","descendants":["T17"]' "epic + child in MAP.html"
assert_contains "$html" '"id":"T14","state":"blocked"' "state travels into MAP.html"

# Every board WRITE auto-refreshes BOTH render caches — they cannot go stale.
run board-transition.sh T17 in-progress >/dev/null
assert_contains "$(tr -d '[:space:]' < "$BOARD/MAP.html")" '"id":"T17","state":"in-progress"' \
    "a board write auto-refreshes MAP.html"
assert_contains "$(cat "$BOARD/MAP.md")" "in-progress" "a board write auto-refreshes MAP.md"
```

- [ ] **Step 2: Repoint the board-relate Mermaid assertions (replace lines 338-340)**

Replace:
```bash
cnt="$(run board-map.sh | grep -Fc -- "-. relates .-")"
assert_equals "$cnt" "1" "symmetric edge renders exactly once in the map"
assert_contains "$(cat "$BOARD/MAP.md")" "T18 -. relates .- T19" "relate auto-refreshed MAP.md"
```
with:
```bash
run board-map.sh --write >/dev/null 2>&1
rel="$(tr -d '[:space:]' < "$BOARD/MAP.html")"
assert_contains "$rel" '"from":"T18","to":"T19","kind":"relates"' "relate auto-refreshed MAP.html"
printf '%s' "$rel" | grep -Fq '"from":"T19","to":"T18","kind":"relates"' \
    && fail "symmetric relate renders exactly once (no reverse dup)" \
    || pass "symmetric relate renders exactly once (no reverse dup)"
```

- [ ] **Step 3: Repoint the board-edge Mermaid assertion (replace line 356)**

Replace:
```bash
assert_contains "$(cat "$BOARD/MAP.md")" "T20 ==> T21" "block auto-refreshed MAP.md (active-block arrow)"
```
with:
```bash
assert_contains "$(tr -d '[:space:]' < "$BOARD/MAP.html")" '"from":"T20","to":"T21","kind":"block-active"' \
    "block auto-refreshed MAP.html (active-block edge)"
```

- [ ] **Step 4: Replace the Mermaid `out` builder in `board-map.sh` with the fallback-table builder**

Change the header comment block (`board-map.sh:2-14`) to describe the two outputs, and replace the entire `out="$(_py - <<'PY' … PY)"` assignment (`board-map.sh:24-151`) with:

```bash
out="$(_py - <<'PY'
import json, os

with open(os.environ["BOARD_MAP"]) as f:
    board = json.load(f)
tickets = board["tickets"]

def num(t): return int(t[1:])
order = sorted(tickets, key=num)
epics = {n["parent"] for n in tickets.values() if n.get("parent")}

def eligible(tid, n):
    if tid in epics or n["state"] != "ready-for-agent":
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n.get("blocked_by", []))

def state_cell(tid, n):
    if n["state"] == "ready-for-agent":
        unmet = [b for b in n.get("blocked_by", []) if tickets.get(b, {}).get("state") != "done"]
        return ("waiting: " + ",".join(unmet)) if unmet else "ELIGIBLE"
    return n["state"]

updated = max((n.get("updated") or "" for n in tickets.values()), default="")
md = ["# Issue Board", "",
      "_Board updated %s · %d tickets · full interactive graph in "
      "`MAP.html` (open in a browser)_" % (updated, len(tickets)), "",
      "| ticket | state | title | PR |", "|---|---|---|---|"]
for tid in order:
    n = tickets[tid]
    title = " ".join(str(n["title"]).split()).replace("|", "\\|")
    md.append("| %s | %s | %s | %s |" % (tid, state_cell(tid, n), title, n.get("pr") or ""))
print("\n".join(md))
PY
)"
```

Leave the `printf '%s\n' "$out"` line and the Task 1 `--write` block (which writes `MAP.md` from `$out` and renders `MAP.html`) exactly as they are.

- [ ] **Step 5: Run the full suite**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -20`
Expected: `ALL TESTS PASSED`.

- [ ] **Step 6: Lint**

Run: `scripts/lint-shell.sh skills/issue-tracker/scripts/board-map.sh`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add skills/issue-tracker/scripts/board-map.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "issue-tracker: MAP.md shrinks to a fallback table; MAP.html is the primary view"
```

---

### Task 3: SKILL.md doc update + final verification

Update the doctrine's toolkit description to match the new behavior, then run the full suite, the lint gate, and the spec's acceptance checks.

**Files:**
- Modify: `skills/issue-tracker/SKILL.md` (the `board-map.sh` toolkit row, `board-map.sh:60`)
- Test: `tests/issue-tracker/test-board-scripts.sh` (full run)

- [ ] **Step 1: Update the `board-map.sh` toolkit row in `skills/issue-tracker/SKILL.md`**

Replace the current row (line 60):
```
| `board-map.sh [--write]` | human telemetry: the board DAG as a Mermaid flowchart (state colors, epic boxes, block/lineage edges). `MAP.md` is a pure render cache of `map.json`, auto-refreshed by every register/transition; `--write` re-renders it by hand |
```
with:
```
| `board-map.sh [--write]` | human telemetry. `--write` renders two render caches of `map.json`: **`MAP.html`** — an interactive layered-DAG (pan/zoom, click a node for its detail, filter by state, collapse epics), the primary view, opened in a browser; and **`MAP.md`** — a minimal node/state table, the GitHub-inline fallback. With no argument it prints the table to stdout. Both auto-refresh on every register/transition |
```

- [ ] **Step 2: Run the full board test suite**

Run: `bash tests/issue-tracker/test-board-scripts.sh`
Expected: ends with `ALL TESTS PASSED`, zero `[FAIL]`.

- [ ] **Step 3: Run the shell lint gate**

Run: `scripts/lint-shell.sh`
Expected: exit 0 (the repo-wide shellcheck baseline stays clean).

- [ ] **Step 4: Execute the spec's acceptance checks (from `docs/doperpowers/specs/2026-07-05-issue-board-html-map-design.md` §Acceptance)**

In a throwaway consumer repo with a registered board (the test harness builds exactly this; reuse its setup or a scratch repo):

1. `board-map.sh --write` writes both `doperpowers/issue-tracker/MAP.html` and `.../MAP.md`; stdout is the minimal table. Verify both files exist and stdout begins with `# Issue Board`.
2. Self-contained: `grep -Eic 'src="https?://|href="https?://[^"]*\.css|cdnjs|unpkg|jsdelivr' doperpowers/issue-tracker/MAP.html` returns `0`.
3. **Browser check (human/`/playwright-cli`):** open `MAP.html`; confirm the layered DAG renders with blockers above dependents; wheel-zoom and background-drag pan work; clicking a node opens a panel showing its note / PR / blockers / md-path; toggling a state chip dims non-matching nodes; clicking an epic card collapses its children and clicking again re-expands.
4. `MAP.md` renders on GitHub as a table with one row per ticket and `ELIGIBLE` on the dispatchable node (inspect the Markdown).
5. Every board-mutating script leaves both files freshly regenerated (covered by the suite's auto-refresh assertions; spot-check by running a `board-transition.sh` and diffing `MAP.html`).
6. `tests/issue-tracker/test-board-scripts.sh` passes.
7. `scripts/lint-shell.sh` passes.

- [ ] **Step 5: Update the spec's living tail and commit**

Append to `## Outcomes & Retrospective` (replacing "Pending — written at finish.") a short outcome-vs-purpose note, and add a dated line to `## Revision Notes`. Then:
```bash
git add skills/issue-tracker/SKILL.md docs/doperpowers/specs/2026-07-05-issue-board-html-map-design.md
git commit -m "issue-tracker: document MAP.html/MAP.md split; close the spec loop"
```

---

## Self-Review

**Spec coverage:**
- HTML primary / MD fallback → Task 1 (HTML) + Task 2 (MD shrink). ✓
- Interactive (pan/zoom, detail, filter, collapsible epics) → template JS in Task 1 Step 3; browser-verified in Task 3 Step 4. ✓
- Zero-dependency self-contained, Python layout + inline JS → Task 1 (no external refs; layout in the `--write` python; asserted by the "no external references" test). ✓
- Collapsible epics → `toggleEpic`/`resolve`/edge-reroute in the template; `epics[].descendants` payload from the layout python. ✓
- MAP.html committed → both commits `git add` the files; nothing gitignores them. ✓
- Deterministic layout → longest-path `layer()` + id-stable ordering, no clock/random. ✓
- State palette / edge semantics carried over verbatim → CSS `.s_*` fills copied from the Mermaid `classDef`; edge kinds map active/satisfied/spawned/relates. ✓
- Template as a separate file with one injection sentinel → `board-map.template.html` + `__BOARD_PAYLOAD__`. ✓
- Testing repointed MAP.md→MAP.html → Task 2 Steps 1-3. ✓
- Acceptance section executed → Task 3 Step 4 quotes the spec's checks. ✓

**Placeholder scan:** No TBD/TODO; every code step carries complete file content or an exact replace-this-with-that. The only literal sentinel (`__BOARD_PAYLOAD__`) is a required, tested token, not a placeholder.

**Type/name consistency:** payload field names (`cls`, `label`, `eligible`, `descendants`, `kind`) are identical in the layout python (producer) and the template JS (consumer); helper names (`resolve`, `render`, `toggleEpic`, `bbox`, `nodeById`, `epicById`) are used consistently; `NODE_W/NODE_H` (client) pair with `COL/ROW` (server) spacing.

**Spec drift:** Planning surfaced no wrong spec statement — the spec's field list matches `board-register.sh:71`, and the "one script + one template" claim holds (verified all four other write scripts call `board-map.sh --write` as their tail and read nothing from the render caches). No spec correction needed.
