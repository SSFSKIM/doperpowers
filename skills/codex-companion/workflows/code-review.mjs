// The review panel: one lens-free native sweep, up to five diff-derived
// scalpel lenses, and one binding verifier. This file is a pure orchestration
// script on the `workflow` verb's engine — every model judgment lives in a
// turn, everything else here is deterministic.
import { extractStubs } from "./lib/extract.mjs";

export const meta = { name: "code-review", description: "Multi-lens codex review panel: native sweep + diff-derived scalpels + one binding verifier" };

// The panel's mandate cap is the owner's, not the model's: it binds the derived
// lenses and a caller's `args.lenses` alike.
const MAX_LENSES = 5;

const DERIVER_SCHEMA = {
  type: "object", required: ["lenses"],
  properties: { lenses: { type: "array", items: { type: "string" } } }
};

const DERIVER_PROMPT = (base) => `You are preparing a multi-reviewer code-review panel for the diff between merge-base(HEAD, ${base}) and HEAD in this repository. Run \`git diff $(git merge-base HEAD ${base}) --stat\` and skim the largest hunks with \`git diff\`.

Write between 0 and 5 scalpel lens mandates. Each mandate is AT MOST TWO SIMPLE SENTENCES naming one structural risk surface of THIS diff (example of the calibre required: "Pay attention to authorization and actor-identity assumptions in the changed API routes."). A separate lens-free reviewer already sweeps everything, so a mandate must earn its slot: fewer, sharper mandates beat coverage padding — a small single-concern diff deserves zero or one. Consider, only where this diff actually raises them: changed-logic accuracy, cross-file contract impact, behavior lost with removed/moved code, security surface, performance/resources.

Return JSON: {"lenses": ["...", ...]}`;

// The one instruction EVERY finder carries, sweep included. A real clean native
// review is free-form prose with no stable phrasing of its own (probe:
// tests/review-bench/results/2026-08-03-native-clean-render-probe/), so without
// this a finder that found nothing reads exactly like one that went dark, and
// extractStubs must call both a failure. It steers rendering only — the sweep
// stays the lens-free reviewer, because nothing here points its attention.
// A scalpel's lens is therefore two lines; raw multi-line developer_instructions
// is live-proven to survive the `-c` carrier intact (specs/2026-07-12-native-
// review-recovery-design.md, "raw multi-line developer_instructions survives").
const CLEAN_SENTINEL =
  "If your review finds no issues, end your final message with exactly this line: No material findings.";

const VERIFIER_SCHEMA = {
  type: "object", required: ["verdicts"],
  properties: { verdicts: { type: "array", items: {
    type: "object", required: ["id", "verdict", "comment"],
    properties: {
      id: { type: "string" },
      verdict: { type: "string", enum: ["CONFIRMED", "REFUTED"] },
      duplicateOf: { type: "string" },
      priority: { type: "string", enum: ["P0", "P1", "P2", "P3"] },
      comment: { type: "string" }
    } } } }
};

// The verifier's contract, checked in code rather than trusted: exactly one
// verdict per candidate and no more, and a duplicateOf graph that actually
// resolves — no phantom target, no duplicate of something refuted, no cycle.
// A schema-valid verdict set can violate every one of these, and each violation
// silently loses or double-counts a finding downstream.
function checkPostconditions(verdicts, pool) {
  const errs = [];
  const ids = new Set(pool.map((s) => s.id));
  const seen = new Map();
  for (const v of verdicts) {
    if (!ids.has(v.id)) errs.push(`phantom id ${v.id}`);
    seen.set(v.id, (seen.get(v.id) ?? 0) + 1);
  }
  for (const s of pool) if (!seen.has(s.id)) errs.push(`missing verdict for ${s.id}`);
  for (const [id, n] of seen) if (n > 1) errs.push(`duplicate verdict for ${id}`);
  const byId = new Map(verdicts.map((v) => [v.id, v]));
  for (const v of verdicts) {
    if (!v.duplicateOf) continue;
    const target = byId.get(v.duplicateOf);
    if (!target) { errs.push(`duplicateOf ${v.duplicateOf} does not exist`); continue; }
    if (target.verdict === "REFUTED") errs.push(`duplicateOf targets refuted ${v.duplicateOf}`);
    let hops = 0, cur = target;
    while (cur?.duplicateOf && hops++ < verdicts.length) cur = byId.get(cur.duplicateOf);
    if (cur?.duplicateOf) errs.push(`duplicateOf cycle at ${v.id}`);
  }
  return errs;
}

const VERIFIER_PROMPT = (base, pool) =>
  `You are the binding verifier of a multi-reviewer panel. The candidate findings below came from independent reviewers of the diff against merge-base(HEAD, ${base}) — re-inspect the code yourself before judging. For EVERY candidate id return exactly one verdict: CONFIRMED (you can name the concrete failure) or REFUTED (state why it is wrong or not a real defect). Mark true duplicates with duplicateOf pointing at the strongest formulation, assign priority P0-P3 to confirmed findings, and put your evidence in comment.

Candidates (JSON):
${JSON.stringify(pool, null, 2)}`;

const REPAIR_PROMPT = (errs, pool) =>
  `Your verdict set violated the contract: ${errs.join("; ")}. Return the FULL corrected verdicts array covering every candidate id exactly once.

Candidates (JSON):
${JSON.stringify(pool, null, 2)}`;

export default async function run({ agent, review, parallel, log, args }) {
  if (!args?.base) throw new Error("code-review workflow requires args.base");
  const base = args.base;
  const finderModel  = args.finderModel  ?? "gpt-5.6-sol";
  const finderEffort = args.finderEffort ?? "xhigh";

  let lenses = args.lenses;
  if (!Array.isArray(lenses)) {
    // Deliberately the finder model: the deriver reads the same diff the
    // finders will, so re-routing the finders re-routes the read of what they
    // should look at. Its effort is fixed low — this is a skim, not a review.
    const derived = await agent(DERIVER_PROMPT(base), {
      model: finderModel, effort: "medium",
      schema: DERIVER_SCHEMA, label: "lens-deriver"
    });
    lenses = derived.lenses;
  }
  lenses = lenses.slice(0, MAX_LENSES).map((l) => String(l).trim()).filter(Boolean);
  log(`panel: sweep + ${lenses.length} scalpels`);

  // The finders, all at once: the sweep carries no mandate, each scalpel
  // exactly one. `parallel` turns a dead worker into a null rather than losing
  // the whole panel with it, so the array stays index-aligned with `finders`.
  const finders = [
    { finderId: "sweep", mandate: null },
    ...lenses.map((mandate, i) => ({ finderId: `scalpel-${i + 1}`, mandate })),
  ];
  const reviews = await parallel(finders.map(({ finderId, mandate }) => () =>
    review({
      base,
      lens: mandate ? `${mandate}\n${CLEAN_SENTINEL}` : CLEAN_SENTINEL,
      model: finderModel, effort: finderEffort, label: finderId
    })));

  // Coverage is the panel's own account of what it actually got, per finder.
  // A lane that died or drifted is named as such: the verifier only ever sees
  // the pool, so a lost finder that left no coverage row would read downstream
  // as a lane that simply found nothing.
  const coverage = [];
  const pool = [];
  reviews.forEach((r, i) => {
    const { finderId, mandate } = finders[i];
    if (!r) { coverage.push({ finder: finderId, lens: mandate, status: "dead", stubs: 0 }); return; }
    const { stubs, failed } = extractStubs(r.reviewText, finderId);
    if (failed) { coverage.push({ finder: finderId, lens: mandate, status: "extraction-failed", stubs: 0 }); return; }
    // Whatever is left is a finder that was understood: parsed stubs, or a
    // recognized clean rendering, which is zero stubs and still a real verdict.
    coverage.push({ finder: finderId, lens: mandate, status: "ok", stubs: stubs.length });
    pool.push(...stubs);
  });

  // `verified` is a three-state answer: the verdicts, an empty array when there
  // was nothing to judge, or null when the verifier could not be made to honour
  // its contract — which Task 4 renders as an interrupted panel rather than a
  // clean one. It is never a partially-trusted set.
  let verified = [];
  if (pool.length > 0) {
    const opts = {
      model: args.verifierModel ?? "gpt-5.6-sol", effort: args.verifierEffort ?? "high",
      schema: VERIFIER_SCHEMA
    };
    const attempt = await agent(VERIFIER_PROMPT(base, pool), { ...opts, label: "verifier" }).catch(() => null);
    const errs = attempt ? checkPostconditions(attempt.verdicts, pool) : ["verifier failed"];
    if (errs.length === 0) verified = attempt.verdicts;
    else {
      log(`verifier postconditions failed: ${errs.join("; ")} — retrying`);
      // A FRESH agent() call, not a resumed thread: content-keyed separately, so
      // a resume never conflates the rejected answer with its replacement.
      const retry = await agent(REPAIR_PROMPT(errs, pool), { ...opts, label: "verifier-retry" }).catch(() => null);
      const errs2 = retry ? checkPostconditions(retry.verdicts, pool) : ["verifier retry failed"];
      verified = errs2.length === 0 ? retry.verdicts : null;
    }
  }

  // … Task 4 continues here: final assembly. Until it lands the run reports the
  // panel's raw material, so the fan-out and the verifier contract are observable.
  return { lenses, coverage, pool, verified };
}
