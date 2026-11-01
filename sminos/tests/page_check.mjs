// Runs the manager page's script (sminos/skills/manager/assets/page.html) in a Node VM over a small stand-in DOM,
// with fetch and EventSource the caller drives, for test_manager_serve.py. No dependency beyond Node.
//
//   node page_check.mjs <page.html> refresh|ko|en|remembered|roadmap
//
// `refresh`: the first ledger fetch is held; the event stream opens and announces `changed` while it is in
// flight; then the held fetch answers with the old ledger. The page must fetch again and show the new one.
// `ko` / `en`: one ledger with an item of each kind the page words, its `lang` `ko` or absent.
// `remembered`: the last ledger's language is kept (`ko`) and the first fetch has not answered yet.
// `roadmap`: the `en` ledger; the reader opens one roadmap row, then an update re-renders the page.
// Prints one JSON line: {fetches, shown, errors, lang (<html lang>), title, h1, text (the page's text), stored},
// and for `roadmap` a `roadmap` object: the initiative's section order, the roadmap's rows, metas, C1's changes as
// listed, the opened row's state after the re-render, and the header summary's links.
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
  for (const id of ["title", "fresh", "window", "summary", "ledger"]) { byId[id] = new Node_("div"); byId[id].id = id; }
  const document = {
    title: "",
    documentElement: { lang: "en" },
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
  const kinds = (lang) => ({
    ...(lang ? { lang } : {}),
    updated: "2026-11-01T10:00:00.000Z", window: { since: "2026-10-15T12:00:00.000Z", until: "2026-11-01T10:00:00.000Z" },
    initiatives: [{ name: "P5", brief: { initiative: "P5", written: "2026-11-01T10:00:00.000Z",
      since: "2026-11-01T00:00:00.000Z", text: "brief text" }, items: [
      { id: "y1", lane: "yours", initiative: "P5", member: "CI-opt", session: "a45b97a3", type: "decide",
        blocking: true, need: "need text", raised: "2026-11-01T09:00:00.000Z", source: "quoted source",
        status: "pending", seen: false, reported: "2026-11-01T10:00:00.000Z" },
      { id: "y2", lane: "yours", initiative: "P5", member: "CI-opt", session: "a45b97a3", type: "act",
        blocking: false, need: "other need", raised: "2026-11-01T08:00:00.000Z", source: "s", status: "answered",
        unverified: true, status_at: "2026-11-01T09:30:00.000Z", evidence: "e", seen: true },
      { id: "w1", lane: "work", initiative: "P5", members: ["CI-opt"], title: "work title", meaning: "m",
        status: "stalled", waits_on: "a login", started: "2026-11-01T07:00:00.000Z", refs: [] }],
      roadmap: plan() }],
  });
  // A roadmap with every status, three levels, and changes on both sides of the window's start (Oct 15 12:00).
  const plan = () => ({ initiative: "P5", written: "2026-11-01T10:00:00.000Z", source: "repo docs/plan.md @ main",
    purpose: "purpose text", done_when: "done-when text", parts: [
      { id: "C1", title: "part one", status: "done", owner: "builder", summary: "summary text", now: "now text",
        refs: ["PR #138"], changes: [{ at: "2026-10-01T00:00:00.000Z", text: "old change" },
          { at: "2026-11-01T09:00:00.000Z", text: "new change" }, { at: "2026-10-20T00:00:00.000Z", text: "middle change" }],
        parts: [{ id: "C1.1", title: "part one one", status: "waiting", summary: "s", waits_on: "the owner's login",
          parts: [{ id: "C1.1.1", title: "part deep", status: "not started", summary: "s" }] }] },
      { id: "C2", title: "part two", status: "in progress", summary: "s" },
      { id: "C3", title: "part three", status: "deferred", summary: "s" },
      { id: "C4", title: "part four", status: "dropped", summary: "s" }] });
  const store = scenario === "remembered" ? { "ledger-lang": "ko" } : {};
  const ctx = {
    document, console, Date, Math, String, Set, Promise, Error, JSON, isNaN,
    setInterval: () => 0,
    window: { scrollY: 0, scrollTo() {},
      localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } } },
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
    } else if (scenario === "ko" || scenario === "en") {
      fetches[0]({ ok: true, status: 200, json: async () => kinds(scenario === "ko" ? "ko" : null) });
      await settle();
    } else if (scenario === "roadmap") {
      fetches[0]({ ok: true, status: 200, json: async () => kinds(null) });
      await settle();
      const row = find(byId.ledger, (n) => n.dataset.id === "rm-P5-C1.1");    // the reader opens a row
      row.open = true;
      (row.listeners.toggle || []).forEach((f) => f());
      stream.onopen();                                                           // and an update re-renders the page
      fetches[fetches.length - 1]({ ok: true, status: 200, json: async () => kinds(null) });
      await settle();
    }
    const shown = byId.ledger.textContent;
    const text = ["fresh", "window", "summary", "ledger"].map((id) => byId[id].textContent).join("\n");
    const out = { fetches: fetches.length, shown: shown.includes("the new ledger") ? "new" : shown.includes("the old ledger") ? "old" : "none",
      errors, lang: document.documentElement.lang, title: document.title, h1: byId.title.textContent, text,
      stored: store["ledger-lang"] ?? null };
    if (scenario === "roadmap") {
      const ini = find(byId.ledger, (n) => n.className === "initiative");
      const rm = find(ini, (n) => /\broadmap\b/.test(n.className));
      const step = (id) => find(rm, (n) => n.dataset.id === "rm-P5-" + id);
      const meta = (id) => find(step(id), (n) => n.className === "meta").textContent;
      out.roadmap = {
        sections: ini.children.filter((n) => n.tagName === "section").map((n) => n.className),
        id: rm.id, heading: rm.children[0].textContent,
        rows: all(rm, (n) => /\bstep\b/.test(n.className)).map((n) => n.className.split(" ").slice(0, 2).join(" ") + " "
          + n.children[0].dataset.id),
        meta: { C1: meta("C1"), "C1.1": meta("C1.1"), C2: meta("C2") },
        changes: all(step("C1"), (n) => n.tagName === "li").map((n) => n.textContent),
        open: step("C1.1").open, closed: step("C1").open,
        link: all(byId.summary, (n) => n.tagName === "a").map((n) => n.textContent + " " + n.href),
        summary: byId.summary.textContent,
      };
    }
    return out;
  })();
}

function all(node, pred, out = []) {
  for (const c of node.children) { if (pred(c)) out.push(c); all(c, pred, out); }
  return out;
}
function find(node, pred) { return all(node, pred)[0]; }

const [page, scenario] = process.argv.slice(2);
run(page, scenario).then((r) => console.log(JSON.stringify(r)));
