#!/usr/bin/env node
// Functional test of board-map.template.html's view logic — the surface the
// shell suite can't reach (it asserts on rendered artifacts, never executes
// the template JS). A minimal DOM shim runs the REAL template <script> and
// drives the kanban view: close-candidate relocation, state-chip hiding of a
// relocated card (must follow the card's REAL state — graph-view parity), and
// ELIGIBLE-only filtering.
//
// Run standalone (node test-board-template.cjs) or via test-board-scripts.sh,
// which skips it with a notice when node is absent. Exit 0 = all pass.
"use strict";
const fs = require("fs");
const path = require("path");

// ---- minimal DOM shim (only what the template script touches) -------------
function makeEl(tag) {
  const el = {
    tag, children: [], style: {}, attrs: {}, hidden: false, className: "",
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); },
    },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, setAttribute(k, v) { this.attrs[k] = v; },
    getBoundingClientRect() { return { width: 1200, height: 800 }; },
    closest() { return null; },
  };
  let _text = "";
  Object.defineProperty(el, "textContent", {
    get: () => _text,
    set: (v) => { _text = String(v); el.children = []; },  // real DOM: wipes children
  });
  Object.defineProperty(el, "clientWidth", { get: () => 1200 });
  Object.defineProperty(el, "clientHeight", { get: () => 800 });
  return el;
}

const ids = {};
["cy", "kb", "detail", "chips", "gctls", "edgelegend", "vgraph", "vkanban",
 "zin", "zout", "fit", "meta", "progfill", "progtxt", "hcounts"]
  .forEach((i) => { ids[i] = makeEl(i); });

// Four tickets covering the routing matrix: relocated candidate, plain ready,
// active (in-progress) candidate that must stay put, and a default-hidden done.
// #5 is a fifth, lane-split probe: an in-design ticket, which unlike the
// architect/implementer queues is NOT a KB_CORE column (it renders only when
// populated — this node is what populates it). It is also a close candidate,
// which must NOT relocate it: in-design is an active state.
const payload = {
  meta: { count: 5, updated: "2026-07-08" },
  nodes: [
    { id: "#1", state: "ready-for-implementer", eligible: true, cls: "s_elig", label: "ELIGIBLE",
      title: "candidate ready", close_candidate: true, blocked_by: [], relates_to: [], prs: [], x: 0, y: 0 },
    { id: "#2", state: "ready-for-implementer", eligible: true, cls: "s_elig", label: "ELIGIBLE",
      title: "plain ready", close_candidate: false, blocked_by: [], relates_to: [], prs: [], x: 0, y: 100 },
    { id: "#3", state: "in-progress", eligible: false, cls: "s_prog", label: "in-progress",
      title: "active candidate", close_candidate: true, blocked_by: [], relates_to: [], prs: [], x: 240, y: 0 },
    { id: "#4", state: "done", eligible: false, cls: "s_done", label: "done",
      title: "landed", close_candidate: false, blocked_by: [], relates_to: [], prs: [], x: 240, y: 100 },
    { id: "#5", state: "in-design", eligible: false, cls: "s_design", label: "designing",
      title: "lane split probe", close_candidate: true, blocked_by: [], relates_to: [], prs: [], x: 480, y: 0 },
  ],
  // #2 is blocked by #5 (the in-design ticket) and by #4 (done). The first is
  // the telemetry probe: an Architect mid-design is _board.ACTIVE, so that
  // dependency is a MOVING path, not an amber stall.
  edges: [{ from: "#5", to: "#2", kind: "block-active" },
          { from: "#4", to: "#2", kind: "block-done" }],
  epics: [],
};
ids["board-data"] = { textContent: JSON.stringify(payload) };

global.document = {
  getElementById: (i) => ids[i],
  createElement: (t) => makeEl(t),
  createElementNS: (_ns, t) => makeEl(t),
  addEventListener() {},
};
global.window = { addEventListener() {} };
global.location = { protocol: "file:", href: "file:///BOARD.html" };  // LIVE off — no poll loop
global.fetch = () => Promise.resolve({ ok: false });

// ---- run the real template script -----------------------------------------
// eval() is the test's whole point and is safe here: the evaluated string is
// THIS repo's checked-in template (never external input), executed so the
// assertions exercise the exact shipped view logic — same convention as the
// documented eval in test-board-scripts.sh's state() helper.
const tpl = fs.readFileSync(path.join(__dirname, "../../skills/issue-tracker/scripts/board-map.template.html"), "utf8");
eval(tpl.match(/<script>([\s\S]*?)<\/script>/)[1]);

function columns() {
  const out = {};
  for (const col of ids.kb.children)
    out[col.children[0].children[0].textContent] =
      col.children.slice(1).map((c) => c.children[0].children[0].textContent);
  return out;
}
let failures = 0;
function expect(desc, cond) {
  console.log("  [" + (cond ? "PASS" : "FAIL") + "] " + desc);
  if (!cond) failures++;
}

// ---- lane-split telemetry (M6 left these two behind the column exemption) --
// The header's "running" tally and the blocker-edge color both encode "a worker
// is on this", and both read that off the state list. _board.ACTIVE is
// (in-design, in-progress, in-review), so an in-design ticket is running and
// its blocked edge is live — #5 is the only in-design node and #3 the only
// in-progress one, so "2 running" is exactly the fix.
expect("header counts the Architect lane as running",
  ids.hcounts.textContent.indexOf("2 running") === 0);
function edgeClasses() {   // graph view: every rendered <path class="gedge ...">
  return ids.cy.children[0].children[0].children
    .filter((e) => e.tag === "path" && String(e.attrs["class"] || "").startsWith("gedge"))
    .map((e) => e.attrs["class"]);
}
const gedges = edgeClasses();
expect("an in-design blocker draws a LIVE edge, not an idle amber wait",
  gedges.some((c) => c.indexOf("block-live") >= 0) &&
  !gedges.some((c) => c.indexOf("block-wait") >= 0));

ids.vkanban.onclick();                       // switch to kanban (done hidden by default)
let cols = columns();
expect("candidate relocated to close-candidate column", (cols["close-candidate"] || []).includes("#1"));
expect("plain ready stays in ready-for-implementer", (cols["ready-for-implementer"] || []).includes("#2"));
expect("active (in-progress) candidate stays in its column", (cols["in-progress"] || []).includes("#3"));
expect("done hidden by default", !("done" in cols));

// lane split (E1): the architect queue is a KB_CORE column, so it renders
// empty (no #-ticket is in that state here); in-design is NOT core, so its
// column exists only because #5 populates it; and the three lane columns
// render in KB_STATES declaration order (architect queue, then design, then
// implementer queue).
expect("architect-queue core column renders with no tickets in it", "ready-for-architect" in cols);
expect("empty core column carries no cards", (cols["ready-for-architect"] || []).length === 0);
expect("in-design ticket renders its own (non-core) column", (cols["in-design"] || []).includes("#5"));
// #5 is ALSO a close candidate: in-design is an ACTIVE state (_board.ACTIVE),
// so a merged linked PR under an Architect mid-design is ordinary mid-flight
// shape, not a close cue — it stays in its lane like in-progress/in-review.
expect("in-design candidate is not relocated out of its lane",
  !(cols["close-candidate"] || []).includes("#5"));
const laneOrder = Object.keys(cols);
expect("lane columns render in KB_STATES order (architect, design, implementer)",
  laneOrder.indexOf("ready-for-architect") >= 0 &&
  laneOrder.indexOf("ready-for-architect") < laneOrder.indexOf("in-design") &&
  laneOrder.indexOf("in-design") < laneOrder.indexOf("ready-for-implementer"));

const rfaChip = ids.chips.children.find((b) => b.textContent === "ready-for-implementer");
rfaChip.onclick();                           // hide the ready-for-implementer state
cols = columns();
expect("hiding a REAL state also hides its relocated candidate", !(cols["close-candidate"] || []).includes("#1"));
expect("hiding a state removes its own column", !("ready-for-implementer" in cols));
expect("other columns unaffected by the hide", (cols["in-progress"] || []).includes("#3"));

rfaChip.onclick();                           // un-hide, then ELIGIBLE-only
ids.chips.children.find((b) => b.textContent === "ELIGIBLE only").onclick();
cols = columns();
expect("ELIGIBLE-only keeps the eligible candidate", (cols["close-candidate"] || []).includes("#1"));
expect("ELIGIBLE-only drops the non-eligible active candidate", !(cols["in-progress"] || []).includes("#3"));

if (failures) { console.log(failures + " template test(s) FAILED"); process.exit(1); }
console.log("template kanban tests: all pass");
