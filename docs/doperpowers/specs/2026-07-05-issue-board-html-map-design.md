# Issue Board — Interactive HTML Map — Design

**Goal:** Give the human reading the issue board an interactive, self-contained HTML graph (`MAP.html`) they can open in a browser — pan/zoom a layered DAG, click a node to see its full ticket detail, filter by state, and collapse epics — replacing the Mermaid `MAP.md` as the *primary* view. `MAP.md` survives, shrunk to a minimal node/state table so GitHub's web UI can still answer "what tickets exist" inline. The board's data model, scripts, and single-writer rules are untouched: this changes only what the human *sees*, not what the machine does.

## Problem

The board's only human view is `MAP.md` — a Mermaid `flowchart TD` regenerated on every board write by `board-map.sh --write` (`skills/issue-tracker/scripts/board-map.sh`). Mermaid renders inline on GitHub, which is its one real virtue, but as the board grows it stops being usable:

1. **No navigation.** Mermaid renders a fixed image. On a board of a few dozen tickets you cannot pan, zoom, or focus a subgraph — you scroll a wall.
2. **No detail on demand.** A node shows `id · title · state`. The ticket's note, PR link, blockers, lineage, and markdown path — all present in `map.json` — are invisible unless you go read `map.json` or run `board-show.sh` per ticket.
3. **No filtering.** "Show me only what's dispatchable" or "dim everything that's done" is impossible; every node competes for attention equally.
4. **Epics don't scale.** Mermaid wraps each epic in a `subgraph` box. Nested epics on a large board produce deep, cramped boxes with no way to collapse a finished epic out of view.

The data to do far better is already in `map.json` (`board-register.sh` writes the full node schema: `title, md, state, category, note, parent, blocked_by[], spawned_by, relates_to[], branch, pr, created, updated`). Only the *renderer* is the limit. An HTML file lifts every one of these ceilings — at the cost that GitHub will not render a raw `.html` inline, which is why the Mermaid view is kept as a shrunken fallback rather than deleted.

## Design Overview

The change is contained to one script plus one new template file. Every other board script (`board-register.sh`, `board-transition.sh`, `board-edge.sh`, `board-relate.sh`) calls `board-map.sh --write` as its final line and is **not touched** — the new behavior rides entirely inside `board-map.sh`.

- **`skills/issue-tracker/scripts/board-map.sh`** — reworked. `--write` now emits **two** files: `MAP.html` (primary, rich interactive graph, committed) and `MAP.md` (minimal fallback table). With no argument it prints the minimal table to stdout (terminal telemetry — the slot the current default occupied).
- **`skills/issue-tracker/scripts/board-map.template.html`** *(new)* — the self-contained HTML shell: all CSS and vanilla JS inline, plus a single sentinel token (`/*__BOARD_PAYLOAD__*/`) where the Python injects the data-and-layout JSON. Kept as a real `.html` file, not a bash heredoc, so the JS/CSS is editable with syntax highlighting and the Python stays small.

`MAP.html` and `MAP.md` are both pure render caches of `map.json` — regenerated on every board write, never hand-edited, both committed (a fresh clone opens the graph with no regeneration step).

### Zero-dependency, self-contained

Doperpowers is a zero-dependency plugin by design, and these files are committed into the *consumer* repo. So: no CDN references, no external stylesheets or fonts, no vendored graph library. The DAG layout is computed in Python (which already parses `map.json`); a few hundred lines of inline vanilla JS render the SVG and handle interaction. A single self-contained HTML file with everything inlined — openable offline by double-click.

## Layout — computed in Python, deterministic

`board-map.sh`'s Python reads `map.json` in numeric-id order (as the current Mermaid emission already does) and computes a **layered DAG**:

- **Layer assignment.** Longest-path layering over the `blocked_by` dependency graph: a node with no blockers sits at layer 0; every other node sits one layer below the deepest blocker it (transitively) waits on. Result: blockers are always drawn above their dependents — the natural top-to-bottom DAG reading. Hand-edited cycles in `map.json` cannot hang the walk (a visited-set clamps them), mirroring the cycle-tolerance the Mermaid emitter already has.
- **Ordering within a layer.** Stable by numeric id (deterministic). Epic members are kept adjacent within their layer so an epic's bounding box is contiguous. Crossing-minimization (barycenter passes) is explicitly deferred — noted in Revision Notes — because it trades determinism for aesthetics and the id-stable order is good enough at board sizes we expect.
- **Coordinates.** `y` from layer, `x` from position-within-layer, centered. Epics get a bounding rectangle around their (adjacent) children.
- **Determinism is a hard requirement.** No `Date.now()`, no randomness — anywhere. The layout is a pure function of `map.json`, so committed `MAP.html` diffs stay stable across writes that don't change the graph, and tests can assert structural facts rather than fighting nondeterministic output. (The `updated` timestamp shown in the header comes from the ticket data itself, already in `map.json`.)

The Python emits a payload object injected into the template:

```
{
  "meta":  { "updated": "<max ticket updated>", "count": <n> },
  "nodes": [ { "id","title","state","category","x","y","eligible",
               "note","pr","branch","parent","blocked_by","spawned_by",
               "relates_to","md","created","updated" }, ... ],
  "edges": [ { "from","to","kind" }, ... ],   // kind: block-active | block-done | spawned | relates
  "epics": [ { "id","title","state","x","y","w","h","children":[...] }, ... ]
}
```

## Interaction — inline vanilla JS

- **Render.** SVG. Nodes are rounded-rect cards showing `id · title` and a state line; **state color reuses the existing Mermaid palette verbatim** (`board-map.sh`'s `classDef` fills/strokes) so the two views stay visually consistent. ELIGIBLE (ready-for-agent + all blockers done + not an epic) gets the thick green border. Edges preserve today's Mermaid semantics 1:1: an **active** block is a solid arrow, a **satisfied** block (blocker already done) is dotted, `spawned` and `relates` are labeled dotted lines. Epics render as translucent labeled boxes behind their children.
- **Pan / zoom.** Mouse-wheel zoom and background-drag pan via the SVG `viewBox`.
- **Node click → detail panel.** A side panel shows the full node: id, title, category, state, note, `blocked_by`, `spawned_by`, `relates_to`, branch, PR (as a link), and the ticket markdown path.
- **State filter / highlight.** Top-bar chips toggle states (dim/undim) and offer an "ELIGIBLE only" highlight.
- **Collapse / expand epics.** Clicking an epic's header collapses it to a single node: its children and their internal edges hide, and edges that crossed the epic boundary re-route to the collapsed epic node. Clicking again expands. This is the primary interactive win for large boards — and the main JS-complexity item.
- **Legend.** Same color/edge vocabulary as the Mermaid legend, rendered in-page.

## MD fallback — "what exists", for GitHub

`MAP.md` shrinks to a graphless minimal table, readable inline on GitHub:

```
# Issue Board

_Board updated <date> · <N> tickets · full interactive graph in MAP.html (open in a browser)_

| ticket | state | title | PR |
|---|---|---|---|
| T1 | ELIGIBLE | … | … |
```

Rows are in numeric-id order. A `ready-for-agent` node that is eligible shows `ELIGIBLE` in the state column (the same label rule the Mermaid view uses today). The PR column links when a `pr` is set.

## Testing

The board toolkit's hermetic bash suite (`tests/issue-tracker/test-board-scripts.sh`) currently asserts Mermaid content in `MAP.md` (e.g. `T20 ==> T21` for an active block, `-. relates .-` for a relates edge, epic subgraph lines). Because those visuals move to `MAP.html`, those assertions are **repointed**:

- **`MAP.html` structural assertions** (grep the emitted file): the payload sentinel is gone (data injected), each expected node id is present with its state class, edges of each `kind` are present (a `block-active`/`block-done` pair, a `spawned`, a `relates`), epic entries render, and the `eligible` flag is set on the right node. Assert *structure*, not pixel coordinates — deterministic layout makes this reliable without being brittle.
- **`MAP.md` fallback assertions**: the new table has a row per ticket, the header count is right, `ELIGIBLE` appears for the eligible node, and a PR cell links when set.
- **Auto-refresh coverage stays**: every write script still triggers a `MAP.html` + `MAP.md` refresh; the existing "MAP.md auto-refreshed on write" checks become "both files refreshed on write".

New tests append after the existing sections so the suite's exact log-line and row-count assertions at earlier fixed points stay valid (the same append-only discipline the current suite requires).

## Acceptance (observable behavior)

From a throwaway consumer repo with a registered board:

1. `board-map.sh --write` writes both `doperpowers/issue-tracker/MAP.html` and `.../MAP.md`; stdout is the minimal table.
2. `MAP.html` is a single self-contained file: `grep -Eic 'src="https?://|href="https?://[^"]*\.css|cdn' MAP.html` returns 0 (no external references).
3. Opening `MAP.html` in a browser shows the layered DAG; blockers sit above dependents; wheel-zoom and drag-pan work; clicking a node opens a panel with that ticket's note/PR/blockers/md-path; a state filter dims non-matching nodes; clicking an epic header collapses and re-expands it.
4. `MAP.md` renders on GitHub as a table with one row per ticket and `ELIGIBLE` on the dispatchable node.
5. Every board-mutating script (`board-register/transition/edge/relate`) leaves both files freshly regenerated.
6. `tests/issue-tracker/test-board-scripts.sh` passes with the repointed assertions.
7. `scripts/lint-shell.sh` passes on `board-map.sh`.

## Decision Log

- Decision: `MAP.html` becomes the **primary** view; `MAP.md` is kept but shrunk to a graphless node/state table.
  Rationale: The human reads the board locally where a rich interactive graph wins decisively; but a raw `.html` does not render inline on GitHub, so deleting the Mermaid view would lose the "glance at what exists on GitHub" affordance. Shrinking rather than deleting keeps both surfaces without maintaining two full graph renderers. Rejected: **replace `MAP.md` entirely** (loses GitHub inline view). Rejected: **coexist as two full views** (Mermaid graph + HTML graph both maintained — double the render surface and diff noise for a view nobody reads once the HTML exists).
  Date: 2026-07-05 (human partner chose "HTML primary, MD shrinks to fallback")

- Decision: The HTML is **interactive** (pan/zoom, click-to-detail, state filter, collapsible epics), not a static image.
  Rationale: Mermaid already produces a static graph; a static SVG would be a marginal gain over what exists. The interaction *is* the reason to move to HTML. Rejected: **static positioned SVG with hover tooltips** (barely better than Mermaid; a big board can't be navigated). Rejected: **middle — static layout with pan/zoom only, no filter/detail** (leaves the highest-value affordances, detail-on-demand and epic collapse, on the table).
  Date: 2026-07-05 (human partner chose "interactive")

- Decision: Self-contained single HTML, **layout computed in Python + inline vanilla JS**; no vendored graph library.
  Rationale: Zero-dependency is a hard project rule and the file is committed into every consumer repo — vendoring a ~1 MB library (cytoscape/vis) into a committed, per-write-regenerated file is against the repo ethos and bloats consumer repos. Python already parses `map.json`, so it owns the deterministic layout (as it already owns Mermaid emission); JS owns only rendering and interaction. Rejected: **vendor a graph library inlined** (megabyte blob committed per consumer repo; non-deterministic library layout breaks stable diffs and tests).
  Date: 2026-07-05

- Decision: Epics are **collapsible** (click header to collapse to a single node / expand).
  Rationale: The board's "for humans" pain is worst on large boards with nested epics; collapse is the single most valuable large-board affordance. Rejected: **static translucent bounding box** (1:1 with today's Mermaid subgraph, simpler — but on a board of dozens of nodes the boxes crowd and there's no way to fold a finished epic out of view).
  Date: 2026-07-05 (human partner chose "collapsible")

- Decision: `MAP.html` is **committed** to the consumer repo (like `MAP.md`).
  Rationale: A fresh clone opens the graph immediately with no regeneration step, and board state lives in git history. Deterministic layout keeps the committed diffs stable. Rejected: **gitignore `MAP.html`** (requires a manual `board-map.sh --write` after clone before the graph exists; the fallback `MAP.md` alone would be the only committed human view).
  Date: 2026-07-05 (human partner chose "commit")

- Decision: The HTML shell lives in a separate `board-map.template.html`, not a bash/Python heredoc.
  Rationale: A few hundred lines of CSS+JS in a heredoc is unmaintainable (no syntax highlighting, quoting hazards, and it bloats the script). A real `.html` template with one injection sentinel keeps the JS editable and the Python small. Trade-off: `board-map.sh` now depends on a sibling file existing — acceptable, it ships in the same `scripts/` directory.
  Date: 2026-07-05

- Decision: State colors and edge semantics are carried over **verbatim** from the current Mermaid renderer.
  Rationale: The two views coexist; visual consistency (same green=done, blue=in-progress, thick-green-border=ELIGIBLE, solid=active-block, dotted=satisfied) means a reader's learned vocabulary transfers between them for free.
  Date: 2026-07-05

- Decision: Layout is **deterministic** (no `Date.now`/randomness); crossing-minimization deferred.
  Rationale: A committed, per-write-regenerated file must diff cleanly, and tests must be able to assert output; both require determinism. Barycenter crossing-reduction is an aesthetic improvement that would introduce ordering instability — deferred to a later revision if board sizes make crossings a real problem.
  Date: 2026-07-05

- Decision: Each top-level cluster (an epic's whole subtree, or a lone node) gets its own **disjoint column band**; nodes are placed within their cluster's band per layer.
  Rationale: The first implementation ordered a layer's nodes by (epic-root, id) but let clusters share columns. Browser verification (Task 1) showed a non-member ticket landing *inside* an epic's bounding box — the box is the bbox over the epic's members, and an outsider positioned in that rectangle's empty cell is visually enclosed, misstating membership. Per-cluster bands guarantee an epic's bbox spans only its own band, so it can never enclose a foreign node. Costs horizontal compactness (bands don't interleave); correctness of the containment cue wins. Coordinates aren't asserted by tests, so no test churn.
  Date: 2026-07-05 (found in browser verification, during execution)

- Decision: On load (and on window resize, and on "reset view"), the graph is **fit to the viewport, centered, capped at 100% zoom**.
  Rationale: A wide board otherwise opens with nodes off the right edge, requiring a blind pan to discover them — a poor first impression. Fitting frames the whole graph immediately. The 100% cap keeps a small board readable instead of blowing it up to fill the screen. "reset view" becomes "fit everything" (more useful than returning to a fixed offset). Rejected: **a fixed initial offset** (the shipped-then-replaced behavior) and **always-fit with no zoom cap** (magnifies a 2-node board absurdly).
  Date: 2026-07-05 (follow-up, human partner requested)

## Surprises & Discoveries

- Observation: No live board exists in the doperpowers repo itself — `doperpowers/issue-tracker/` is lazily created in the *consumer* repo on first `board-register.sh`.
  Evidence: `ls doperpowers/issue-tracker/` returns nothing in this repo; `_board_init` (`_lib.sh`) creates the dir/map on first register. Implication: the work is pure toolkit change, validated through the hermetic test harness, not against a real board.

- Observation: A bounding-box epic drawn over scattered members can enclose a non-member — the machine tests (structure-only) never catch it; only opening the page does.
  Evidence: with the first layout, the scratch board rendered T6 (blocked_by T5, no parent) geometrically inside the T1 epic box, because T6's grid cell fell within the box's x/y span. Fixed by per-cluster column bands (see Decision Log). Lesson: for a visual deliverable, browser verification is not optional polish — it caught a correctness bug the payload-grep tests were structurally blind to.

- Observation: Three assertion bugs in the plan's test code were caught in the pre-execution review, not at runtime.
  Evidence: (1) payload key order is `id, state, eligible, …`, so a whitespace-stripped grep for `"id":"T31","eligible":false` never matches — the assertion must include the intervening `"state":"…"`. (2) `tr -d '[:space:]'` deletes the literal characters `[:space]` on BSD/macOS `tr`, not whitespace — the portable form here is `tr -d ' \n\t'`. (3) A `VAR=x _py …` prefix's export-through-a-shell-function is shell-dependent; the HTML render calls `python3` directly with an explicit env prefix (guaranteed exported to an external command) instead. All three were corrected before the first test run.

## Outcomes & Retrospective

**2026-07-05, at finish.** Everything in the design shipped in three commits: `MAP.html` rendered alongside the Mermaid map (additive), then `MAP.md` shrunk to the fallback table with the suite's Mermaid assertions repointed to the `MAP.html` payload, then the SKILL.md toolkit row and this spec's living tail. The full hermetic suite passes (`ALL TESTS PASSED`, including the new `board-map (html)` section), `scripts/lint-shell.sh` is clean on the two touched shell files, and every spec acceptance check verified on a scratch board — including a real browser pass (via `playwright-cli`) confirming pan/zoom, click-to-detail, state filter, and epic collapse/expand with no JS console errors.

The design held: the change stayed contained to `board-map.sh` + the new template; no other board script was touched. The one substantive deviation was the layout algorithm — the swimlane-band redesign forced by browser verification (see Surprises), which the machine tests could not have surfaced. Remains open by design: crossing-minimization (deferred). The initial fit-to-viewport, first noted here as a future polish, was added as a follow-up the same day (see Revision Notes).

## Revision Notes

- 2026-07-05: Initial version — terminal artifact of the brainstorm (move the board's human view from Mermaid `MAP.md` to an interactive self-contained `MAP.html`, Mermaid kept as a shrunken fallback). Four design forks decided with the human partner: HTML-primary/MD-fallback, interactive, collapsible epics, committed `MAP.html`.
- 2026-07-05: Decision Log extended with the per-cluster column-band layout (replacing shared-column ordering) after browser verification found an epic box enclosing a non-member; Surprises & Discoveries records that plus three plan-test assertion bugs caught in review. Outcomes & Retrospective written at finish.
- 2026-07-05: Follow-up (human partner requested) — the deferred initial fit-to-viewport shipped. `MAP.html` now frames the whole graph on load and on window resize, centered, never zooming past 100%; the "reset view" button calls the same fit. Template-only change (no payload/test change; browser-verified all nodes in view on load). See Decision Log.
