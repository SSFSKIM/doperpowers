// The review panel: one lens-free native sweep, up to five diff-derived
// scalpel lenses, and one binding verifier. This file is a pure orchestration
// script on the `workflow` verb's engine — every model judgment lives in a
// turn, everything else here is deterministic.
import { extractStubs } from "./lib/extract.mjs";

export const meta = { name: "code-review", description: "Multi-lens codex review panel: native sweep + diff-derived scalpels + one binding verifier" };

// The panel's mandate cap is the owner's, not the model's: it binds the derived
// lenses and a caller's `args.lenses` alike.
const MAX_LENSES = 5;

// Both schemas ride to the API as a STRICT output schema, which is a narrower
// dialect than JSON Schema: every object must carry `additionalProperties:
// false`, and `required` must list every property it declares. An optional
// field is therefore spelled as a required one whose type admits null (see
// duplicateOf/priority below) — omit any of this and the turn is rejected 400
// before the model ever runs (live-proven, 2026-08-03 X1 run).
const DERIVER_SCHEMA = {
  type: "object", additionalProperties: false, required: ["lenses"],
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
// The sentinel rides the FINDINGS channel, not the final message. Asking a
// finder to end its message with a sentinel line does NOT work on the native
// review path — a review turn renders reviewText from codex's own review
// pipeline, and a live run on a known-clean diff came back as free-form prose
// with the instruction in place (evidence:
// tests/review-bench/results/2026-08-03-native-clean-render-probe/notes.md).
// The same channel DOES reliably shape findings — the LENSPROBE-7Q probe had a
// marker finding added on demand
// (tests/review-bench/results/2026-08-03-appserver-devinstr-probe/) — so a
// finder that found nothing says so in the only vocabulary the render has.
// Raw multi-line developer_instructions survives the `-c` carrier intact
// (specs/2026-07-12-native-review-recovery-design.md).
const CLEAN_SENTINEL =
  'If and only if your review finds no material issues, report exactly one finding titled "NO-MATERIAL-FINDINGS" at the lowest priority, pointing at any changed file.';

const VERIFIER_SCHEMA = {
  type: "object", additionalProperties: false, required: ["verdicts"],
  properties: { verdicts: { type: "array", items: {
    type: "object", additionalProperties: false,
    required: ["id", "verdict", "duplicateOf", "priority", "comment"],
    properties: {
      id: { type: "string" },
      verdict: { type: "string", enum: ["CONFIRMED", "REFUTED"] },
      // null = not a duplicate / no priority assigned. Everything downstream
      // reads these through a falsy or nullish test, so a null reads exactly
      // as the absent field it replaces.
      duplicateOf: { type: ["string", "null"] },
      priority: { type: ["string", "null"], enum: ["P0", "P1", "P2", "P3", null] },
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

// A candidate id is prefixed with the finder that raised it, so the roster tells
// the verifier what each reviewer was pointed at. A claim from a mandated lens
// reads differently from the same claim raised unprompted by the sweep.
const lensRoster = (finders) => finders
  .map(({ finderId, mandate }) => `- ${finderId}: ${mandate ?? "(lens-free sweep)"}`)
  .join("\n");

const VERIFIER_PROMPT = (base, finders, pool) =>
  `You are the binding verifier of a multi-reviewer panel. The candidate findings below came from independent reviewers of the diff against merge-base(HEAD, ${base}) — re-inspect the code yourself before judging. For EVERY candidate id return exactly one verdict: CONFIRMED (you can name the concrete failure) or REFUTED (state why it is wrong or not a real defect). Mark true duplicates with duplicateOf pointing at the strongest formulation (null when the finding is not a duplicate), assign priority P0-P3 to confirmed findings (null on a refuted one), and put your evidence in comment.

The reviewers, and the lens each was given (a candidate id carries its reviewer's label):
${lensRoster(finders)}

Candidates (JSON):
${JSON.stringify(pool, null, 2)}`;

// The repair rides a FRESH thread — the engine's agent() opens one per call — so
// whatever this prompt omits, the repairing verifier does not know: not its
// role, not the base, not what CONFIRMED means. Its answer is binding when it
// passes, so it carries the WHOLE contract, with the violation on top.
const REPAIR_PROMPT = (base, errs, finders, pool) =>
  `Your verdict set violated the contract: ${errs.join("; ")}. The full contract follows again, unchanged.

${VERIFIER_PROMPT(base, finders, pool)}

Return the FULL corrected verdicts array covering every candidate id exactly once.`;

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
    const attempt = await agent(VERIFIER_PROMPT(base, finders, pool), { ...opts, label: "verifier" }).catch(() => null);
    const errs = attempt ? checkPostconditions(attempt.verdicts, pool) : ["verifier failed"];
    if (errs.length === 0) verified = attempt.verdicts;
    else {
      log(`verifier postconditions failed: ${errs.join("; ")} — retrying`);
      // A FRESH agent() call, not a resumed thread: content-keyed separately, so
      // a resume never conflates the rejected answer with its replacement.
      const retry = await agent(REPAIR_PROMPT(base, errs, finders, pool), { ...opts, label: "verifier-retry" }).catch(() => null);
      const errs2 = retry ? checkPostconditions(retry.verdicts, pool) : ["verifier retry failed"];
      verified = errs2.length === 0 ? retry.verdicts : null;
    }
  }

  // Assembly. Every judgement has already been made — the finders raised, the
  // verifier ruled, coverage recorded what the panel actually got — so what is
  // left is deterministic. Its only real subject is honesty: which losses a
  // verdict is still allowed to stand on top of.
  const sweepDead = coverage.find((c) => c.finder === "sweep" && c.status !== "ok");
  const lostLenses = coverage.filter((c) => c.status !== "ok");

  // Unjudged candidates are not findings — nobody re-inspected them — but they
  // are also the only thing this run produced, so they ride along raw instead of
  // being thrown away with the verdict.
  if (verified === null) {
    return { verdict: "interrupted", findings: [], coverage, lenses, pool,
      explanation: "verifier did not produce a contract-valid verdict set; raw candidate pool attached" };
  }

  const byId = new Map(verified.map((v) => [v.id, v]));
  const stubById = new Map(pool.map((s) => [s.id, s]));
  // A duplicate may point at another duplicate — the postconditions forbid a
  // cycle and a refuted target, not a chain — so credit follows the chain to the
  // primary it ends at rather than stopping at the link it named. Otherwise the
  // third finder to raise a defect silently stops counting as having raised it.
  const rootOf = (v) => { let cur = v; while (cur.duplicateOf) cur = byId.get(cur.duplicateOf); return cur.id; };
  const sourcesOf = (v) => [...new Set(
    [v, ...verified.filter((d) => d.duplicateOf && rootOf(d) === v.id)].map((d) => d.id.split("#")[0])
  )];

  // One published finding per surviving formulation: the location the finder
  // reported, the judgement the verifier reached, and the lanes that raised it.
  const ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 };
  const findings = verified
    .filter((v) => v.verdict === "CONFIRMED" && !v.duplicateOf)
    .map((v) => {
      const stub = stubById.get(v.id);
      return {
        id: v.id, priority: v.priority ?? stub.priority, title: stub.title,
        file: stub.file, lines: stub.lines, comment: v.comment, sources: sourcesOf(v)
      };
    })
    .sort((a, b) => ORDER[a.priority] - ORDER[b.priority]);

  let verdict = findings.length > 0 ? "incorrect" : "correct";
  let explanation = findings.length > 0
    ? `confirmed: ${findings.slice(0, 3).map((f) => f.title).join("; ")}`
    : "no confirmed findings";
  // An empty verdict set means two different things — every lane reported and
  // found nothing, or the lanes that would have found something never reported.
  // Only coverage tells them apart, so a clean verdict is asserted only when
  // nothing was lost. A lost lane next to a CONFIRMED finding is the opposite
  // case: it costs the panel its claim to completeness, never a real defect.
  if (verdict === "correct" && lostLenses.length > 0) {
    verdict = "interrupted";
    explanation = `coverage incomplete (${lostLenses.map((c) => c.finder).join(", ")}) — a clean verdict cannot be asserted`;
  }
  if (verdict === "incorrect" && lostLenses.length > 0) {
    explanation += `; coverage partial: ${lostLenses.map((c) => c.finder).join(", ")}`;
  }
  // The sweep is the only lane that reads the whole diff, so without it the
  // panel cannot say what it missed: losing it fails the ROUND, whatever the
  // scalpels confirmed. The confirmed findings stay attached — interrupted
  // withholds the claim of completeness, not the evidence.
  if (sweepDead) {
    verdict = "interrupted";
    explanation = "the lens-free sweep did not complete — round is interrupted" +
      (findings.length > 0 ? `; ${findings.length} confirmed finding(s) attached as partial evidence` : "");
  }
  // A whole panel that found nothing is the shape a mis-aimed diff also makes.
  if (verdict === "correct" && pool.length === 0) {
    explanation += " (note: all finders returned zero findings — verify the diff target is what you intended)";
  }
  return { verdict, findings, coverage, lenses, explanation };
}
