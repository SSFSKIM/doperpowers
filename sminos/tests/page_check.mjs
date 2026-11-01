// Runs the manager page's script (sminos/skills/manager/assets/page.html) in a Node VM over a small stand-in DOM,
// with fetch and EventSource the caller drives, for test_manager_serve.py. No dependency beyond Node.
//
//   node page_check.mjs <page.html> refresh
//
// `refresh`: the first ledger fetch is held; the event stream opens and announces `changed` while it is in
// flight; then the held fetch answers with the old ledger. The page must fetch again and show the new one.
// Prints one JSON line: {fetches, shown, errors}.
import { readFileSync } from "node:fs";
import vm from "node:vm";

class Node_ {
  constructor(tag) {
    this.tagName = tag; this.children = []; this._text = ""; this.className = ""; this.dataset = {};
    this.listeners = {}; this.hidden = false; this.open = false; this.id = ""; this.href = "";
    const self = this;
    this.classList = { add(c) { self.className = (self.className + " " + c).trim(); } };
  }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(k, f) { (this.listeners[k] = this.listeners[k] || []).push(f); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this._text = String(v); this.children = []; }
}

function run(page, scenario) {
  const html = readFileSync(page, "utf8");
  const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
  const byId = {};
  for (const id of ["fresh", "window", "summary", "ledger"]) { byId[id] = new Node_("div"); byId[id].id = id; }
  const document = {
    title: "",
    createElement: (t) => new Node_(t),
    createTextNode: (t) => { const n = new Node_("#text"); n._text = String(t); return n; },
    getElementById: (id) => byId[id] || null,
  };
  const fetches = [], errors = [];
  let stream = null;
  const ledger = (title) => ({
    updated: "2026-11-01T10:00:00.000Z", window: { since: "2026-11-01T00:00:00.000Z", until: "2026-11-01T10:00:00.000Z" },
    initiatives: [{ name: "P5", brief: null, items: [{ id: "w1", lane: "work", initiative: "P5", title, meaning: "m",
      status: "in progress", started: "2026-11-01T09:00:00.000Z", refs: [] }] }],
  });
  const ctx = {
    document, console, Date, Math, String, Set, Promise, Error, JSON, isNaN,
    setInterval: () => 0,
    window: { scrollY: 0, scrollTo() {} },
    fetch: () => new Promise((resolve) => fetches.push(resolve)),
    EventSource: class { constructor(u) { this.url = u; this.l = {}; stream = this; }
      addEventListener(k, f) { this.l[k] = f; } },
  };
  vm.createContext(ctx);
  try { vm.runInContext(script, ctx); } catch (e) { errors.push(String(e)); }
  const answer = (i, title) => fetches[i]({ ok: true, status: 200, json: async () => ledger(title) });
  const settle = () => new Promise((r) => setTimeout(r, 20));
  return (async () => {
    if (scenario === "refresh") {
      stream.onopen();                      // the stream opens while the first fetch is in flight
      stream.l.changed();                   // and an update lands before it answers
      answer(0, "the old ledger");
      await settle();
      if (fetches.length > 1) answer(1, "the new ledger");
      await settle();
    }
    const shown = byId.ledger.textContent;
    return { fetches: fetches.length, shown: shown.includes("the new ledger") ? "new" : shown.includes("the old ledger") ? "old" : "none", errors };
  })();
}

const [page, scenario] = process.argv.slice(2);
run(page, scenario).then((r) => console.log(JSON.stringify(r)));
