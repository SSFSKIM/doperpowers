#!/usr/bin/env node
// render-panel-findings.mjs — flatten the code-review panel's stdout JSON
// ({runId, result: {verdict, findings, coverage, lenses, explanation}}) into
// the rendered-findings text the reviewing-prs worker reads at JOIN, so the
// panel route and the single-review route land in --out with one contract.
//
// `interrupted` exits 4: the panel withheld its verdict (lost lane, no
// contract-valid verifier set, or the reviewed head moved), so there is no
// findings file to write — the caller treats it like any other engine
// failure (retry, then the ENGINE-UNAVAILABLE fallback). Any partial
// evidence stays in the .panel.json beside --out for the review trail.
//
// Usage: render-panel-findings.mjs <panel.json>   (findings text on stdout)
import { readFileSync } from "node:fs";

const raw = JSON.parse(readFileSync(process.argv[2], "utf8"));
const r = raw?.result ?? {};
if (r.verdict === "interrupted") {
  console.error(`panel interrupted: ${r.explanation ?? "no explanation"}`);
  process.exit(4);
}
if (r.verdict !== "correct" && r.verdict !== "incorrect") {
  console.error(`panel returned no verdict (got ${JSON.stringify(r.verdict)})`);
  process.exit(4);
}

const findings = r.findings ?? [];
const lenses = (r.lenses ?? []).length;
const out = [];
out.push(
  `Panel verdict: ${r.verdict} — ${findings.length} verifier-confirmed ` +
  `finding${findings.length === 1 ? "" : "s"} (sweep + ${lenses} lens${lenses === 1 ? "" : "es"} + verifier)`
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
