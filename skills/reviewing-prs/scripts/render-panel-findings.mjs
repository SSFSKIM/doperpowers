#!/usr/bin/env node
// render-panel-findings.mjs — flatten the code-review panel's stdout JSON
// ({runId, result: {verdict, findings, coverage, lenses, explanation}}) into
// the rendered-findings text the reviewing-prs worker reads at JOIN, so the
// panel route and the single-review route land in --out with one contract.
//
// FAIL CLOSED on anything but a well-formed verdict: the worker derives its
// approval from unresolved critical/high findings, so a malformed result
// rendered as "0 findings" would read as clean. `interrupted` and every
// malformed/inconsistent shape exit 4 — the caller treats that like any
// engine failure (retry, then the ENGINE-UNAVAILABLE fallback). Any partial
// evidence stays in the .panel.json beside --out for the review trail.
//
// Usage: render-panel-findings.mjs <panel.json>   (findings text on stdout)
import { readFileSync } from "node:fs";

const refuse = (why) => { console.error(`panel result rejected: ${why}`); process.exit(4); };

let raw;
try {
  raw = JSON.parse(readFileSync(process.argv[2], "utf8"));
} catch (e) {
  refuse(`unreadable panel JSON (${e.message})`);
}
const r = raw?.result ?? {};
if (r.verdict === "interrupted") {
  console.error(`panel interrupted: ${r.explanation ?? "no explanation"}`);
  process.exit(4);
}
if (r.verdict !== "correct" && r.verdict !== "incorrect") {
  refuse(`no verdict (got ${JSON.stringify(r.verdict)})`);
}
if (!Array.isArray(r.findings)) refuse("findings is not an array");
for (const f of r.findings) {
  if (typeof f?.priority !== "string" || typeof f?.title !== "string" || typeof f?.file !== "string") {
    refuse(`malformed finding ${JSON.stringify(f).slice(0, 120)}`);
  }
}
// The panel constructs the verdict FROM the findings (incorrect ⟺ confirmed
// findings exist), so a disagreement here is a mangled result, not a verdict.
if ((r.verdict === "incorrect") !== (r.findings.length > 0)) {
  refuse(`verdict ${r.verdict} inconsistent with ${r.findings.length} findings`);
}

const findings = r.findings;
const out = [];
// Participation from COVERAGE (what actually ran), never from the configured
// lens list — a dead lane must not be rendered as a participant in the trail.
const coverage = Array.isArray(r.coverage) ? r.coverage : [];
const lanes = coverage.length
  ? ` (lanes: ${coverage.map((c) => `${c.finder} ${c.status}`).join(", ")})`
  : "";
out.push(
  `Panel verdict: ${r.verdict} — ${findings.length} verifier-confirmed ` +
  `finding${findings.length === 1 ? "" : "s"}${lanes}`
);
if (r.explanation) out.push("", String(r.explanation).trim());
for (const f of findings) {
  const loc = f.lines ? `${f.file}:${f.lines}` : f.file;
  out.push("", `- [${f.priority}] ${f.title} (${loc})`);
  if (f.comment) out.push(`  ${String(f.comment).trim().replace(/\n/g, "\n  ")}`);
  if (f.sources?.length > 1) out.push(`  raised independently by: ${f.sources.join(", ")}`);
}
if (findings.length === 0) out.push("", "No verifier-confirmed findings.");
console.log(out.join("\n"));
