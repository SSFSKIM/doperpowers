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
const payload = {
  meta: { count: 4, updated: "2026-07-08" },
  nodes: [
    { id: "#1", state: "ready-for-agent", eligible: true, cls: "s_elig", label: "ELIGIBLE",
      title: "candidate ready", close_candidate: true, blocked_by: [], relates_to: [], prs: [], x: 0, y: 0 },
    { id: "#2", state: "ready-for-agent", eligible: true, cls: "s_elig", label: "ELIGIBLE",
      title: "plain ready", close_candidate: false, blocked_by: [], relates_to: [], prs: [], x: 0, y: 100 },
    { id: "#3", state: "in-progress", eligible: false, cls: "s_prog", label: "in-progress",
      title: "active candidate", close_candidate: true, blocked_by: [], relates_to: [], prs: [], x: 240, y: 0 },
    { id: "#4", state: "done", eligible: false, cls: "s_done", label: "done",
      title: "landed", close_candidate: false, blocked_by: [], relates_to: [], prs: [], x: 240, y: 100 },
  ],
  edges: [], epics: [],
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

ids.vkanban.onclick();                       // switch to kanban (done hidden by default)
let cols = columns();
expect("candidate relocated to close-candidate column", (cols["close-candidate"] || []).includes("#1"));
expect("plain ready stays in ready-for-agent", (cols["ready-for-agent"] || []).includes("#2"));
expect("active (in-progress) candidate stays in its column", (cols["in-progress"] || []).includes("#3"));
expect("done hidden by default", !("done" in cols));

const rfaChip = ids.chips.children.find((b) => b.textContent === "ready-for-agent");
rfaChip.onclick();                           // hide the ready-for-agent state
cols = columns();
expect("hiding a REAL state also hides its relocated candidate", !(cols["close-candidate"] || []).includes("#1"));
expect("hiding a state removes its own column", !("ready-for-agent" in cols));
expect("other columns unaffected by the hide", (cols["in-progress"] || []).includes("#3"));

rfaChip.onclick();                           // un-hide, then ELIGIBLE-only
ids.chips.children.find((b) => b.textContent === "ELIGIBLE only").onclick();
cols = columns();
expect("ELIGIBLE-only keeps the eligible candidate", (cols["close-candidate"] || []).includes("#1"));
expect("ELIGIBLE-only drops the non-eligible active candidate", !(cols["in-progress"] || []).includes("#3"));

if (failures) { console.log(failures + " template test(s) FAILED"); process.exit(1); }
console.log("template kanban tests: all pass");
