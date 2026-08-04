# Codex Review Panel Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `skills/codex-companion/workflows/code-review.mjs` — the multi-lens review panel (1 native sweep + up to 5 diff-derived scalpel lenses at sol/xhigh, one binding verifier at sol/high) — and gate it on the X1 review benchmark.

**Architecture:** A pure orchestration script on the Plan-A engine (`workflow` verb). No engine changes. Extraction and postcondition validation are deterministic script code; all model judgment lives in the finder/verifier turns. Spec: `docs/doperpowers/specs/2026-08-03-codex-workflow-engine-design.md` (v2.2 §First consumer). Depends on: Plan `2026-08-03-codex-workflow-engine.md` complete.

**Tech Stack:** Node ESM workflow script, mock-driven tests via the Plan-A harness, live X1 bench run.

## Global Constraints

- Panel models are FIXED defaults (args-overridable): lens deriver `gpt-5.6-sol`/`medium`; finders `gpt-5.6-sol`/`xhigh`; verifier `gpt-5.6-sol`/`high`.
- Lens mandates: at most FIVE, each at most TWO simple sentences (owner constraint). K (0–5) is the deriver's judgment — no numeric thresholds in the prompt beyond the cap.
- Scalpels ride native review with `developer_instructions` (live-proven: `tests/review-bench/results/2026-08-03-appserver-devinstr-probe/`); the sweep is a lens-free native review.
- Verifier verdicts are binding; postconditions are mechanically validated (exact-set, acyclic non-refuted `duplicateOf`).
- Coverage honesty: dead/extraction-failed finder ⇒ named lens loss; would-be-clean verdict degrades to `interrupted`; dead sweep or dead verifier ⇒ always `interrupted`; unverified candidates never published, never silently dropped.
- Quality gate (predeclared, X1): seeded recall ≥ the recorded single-codex baseline; FP growth ≤ +1 across the whole seeded set. The panel is not referenced by any skill prose until it passes.
- Test discrimination rule: every assert must fail against the parent commit with a naming signature. Extraction fixtures come from REAL codex review outputs, never hand-idealized text.
- No new npm dependencies; no attribution trailers in commits.

## File Structure

```
skills/codex-companion/workflows/code-review.mjs        (Tasks 1–4: the panel)
skills/codex-companion/workflows/lib/extract.mjs        (Task 2: stub extraction — plain module, imported by the workflow)
tests/codex-companion/test-panel-extract.mjs            (Task 2)
tests/codex-companion/test-panel-flow.sh                (Tasks 3–4: mock e2e)
tests/codex-companion/fixtures/review-texts/            (Task 2: real captured outputs)
tests/review-bench/run-case-workflow.sh                 (Task 5: X1 adapter)
tests/review-bench/results/<run-id>/                    (Task 5: live scores)
```

**Interfaces:**
- Consumes (from Plan A): the `workflow` verb CLI; hooks `agent(prompt, {model, effort, schema, label})`, `review({base, model, effort, lens, label})` → `{reviewText, threadId, status}`, `parallel`, `log`, `args`.
- Produces: workflow result object
  `{ verdict: "correct"|"incorrect"|"interrupted", findings: [{id, priority, title, file, lines, comment, sources}], explanation, coverage: [{finder, lens|null, status, stubs}], pool? }`
  (`pool` attached only on `interrupted` verifier paths).

---

### Task 1: Panel skeleton — args, lens derivation

**Files:**
- Create: `skills/codex-companion/workflows/code-review.mjs`
- Test: extend `tests/codex-companion/test-panel-flow.sh` (created here)

- [ ] **Step 1: Write the failing test** (mock scenario: deriver turn returns 2 lenses; assert the workflow requests exactly 1 sweep + 2 scalpel reviews — count via mock `turns.jsonl` method/params, scalpel spawns carry `-c developer_instructions=<mandate>`; also: `--args '{"base":"main","lenses":["only one mandate."]}'` bypasses the deriver — no deriver turn consumed, exactly 1 sweep + 1 scalpel).

- [ ] **Step 2: Implement the skeleton + deriver.**

```js
export const meta = { name: "code-review", description: "Multi-lens codex review panel: native sweep + diff-derived scalpels + one binding verifier" };

const DERIVER_SCHEMA = {
  type: "object", required: ["lenses"],
  properties: { lenses: { type: "array", items: { type: "string" } } }
};

const DERIVER_PROMPT = (base) => `You are preparing a multi-reviewer code-review panel for the diff between merge-base(HEAD, ${base}) and HEAD in this repository. Run \`git diff $(git merge-base HEAD ${base}) --stat\` and skim the largest hunks with \`git diff\`.

Write between 0 and 5 scalpel lens mandates. Each mandate is AT MOST TWO SIMPLE SENTENCES naming one structural risk surface of THIS diff (example of the calibre required: "Pay attention to authorization and actor-identity assumptions in the changed API routes."). A separate lens-free reviewer already sweeps everything, so a mandate must earn its slot: fewer, sharper mandates beat coverage padding — a small single-concern diff deserves zero or one. Consider, only where this diff actually raises them: changed-logic accuracy, cross-file contract impact, behavior lost with removed/moved code, security surface, performance/resources.

Return JSON: {"lenses": ["...", ...]}`;

export default async function run({ agent, review, parallel, log, args }) {
  if (!args?.base) throw new Error("code-review workflow requires args.base");
  const base = args.base;
  const finderModel  = args.finderModel  ?? "gpt-5.6-sol";
  const finderEffort = args.finderEffort ?? "xhigh";

  let lenses = args.lenses;
  if (!Array.isArray(lenses)) {
    const derived = await agent(DERIVER_PROMPT(base), {
      model: args.finderModel ?? "gpt-5.6-sol", effort: "medium",
      schema: DERIVER_SCHEMA, label: "lens-deriver"
    });
    lenses = derived.lenses;
  }
  lenses = lenses.slice(0, 5).map((l) => String(l).trim()).filter(Boolean);
  log(`panel: sweep + ${lenses.length} scalpels`);
  // … Tasks 3–4 continue here …
}
```

- [ ] **Step 3: RED→GREEN, commit.** `git commit -am "feat(codex-companion): review panel workflow — args + adaptive lens derivation (≤5, ≤2 sentences)"`

### Task 2: Stub extraction from real review text

**Files:**
- Create: `skills/codex-companion/workflows/lib/extract.mjs`
- Create: `tests/codex-companion/fixtures/review-texts/{probe.md,campaign-r14.md,campaign-r15.md,no-findings.md,drifted.md}`
- Test: `tests/codex-companion/test-panel-extract.mjs`

**Interfaces:**
- Produces: `extractStubs(reviewText, finderId) → {stubs, clean, failed}` with a STRICT trichotomy: `stubs.length > 0` (findings parsed); `clean: true` ONLY when the text matches a recognized no-findings rendering (read `lib/render.mjs` for the exact phrasing(s) the runtime emits and match those, not a guess); `failed: true` for EVERYTHING else — blank output, untagged drift, unrecognized prose. Zero stubs is never silently "ok": an unrecognized empty answer is a dead finder, not a clean one.

- [ ] **Step 1: Build fixtures from REAL outputs** (mock-fidelity rule):
  - `probe.md` ← copy of `tests/review-bench/results/2026-08-03-appserver-devinstr-probe/probe-out.md` (2 findings, one without a `[P#]` tag — the LENSPROBE line; extraction must tolerate untagged entries by defaulting priority `P3`).
  - `campaign-r14.md` / `campaign-r15.md` ← the E2 campaign round-14/15 rendered outputs (recover from the session scratch or re-render from any recent codex review; 2–3 findings each with `[P1]`/`[P2]`/`[P3]` tags, multi-line indented bodies, `path:start-end` and `path:line-line` variants).
  - `no-findings.md` ← a real clean-run rendering (`No findings` phrasing as the runtime renders it — check `lib/render.mjs` for the exact no-findings text).
  - `drifted.md` ← campaign-r15.md with the leading `- ` list markers stripped (simulated format drift: `[P` present, list structure gone).
  - `blank.md` ← empty file; `untagged-drift.md` ← findings-like prose with NO `[P#]` tags and no recognized no-findings phrasing (e.g. the campaign fixture with tags stripped). Both must classify `failed: true` — output loss can never become a clean finder.

- [ ] **Step 2: Write the failing test**: probe.md → 2 stubs (LENSPROBE entry priority `"P3"`, file + lines parsed); campaign fixtures → exact expected counts/titles/line-ranges (hand-derive from the fixture ONCE, assert literally); no-findings.md → `{stubs: [], clean: true, failed: false}`; drifted.md, blank.md, untagged-drift.md → `failed: true`; ids are `<finderId>#<ordinal>`.

- [ ] **Step 3: Implement `extract.mjs`.**

```js
const HEAD_RE = /^\s*(?:[-*]\s*)?(?:\[(P[0-3])\]\s*)?(.+?)\s+—\s+(\S+?):(\d+)(?:-(\d+))?\s*$/;

export function extractStubs(reviewText, finderId) {
  const lines = String(reviewText ?? "").split("\n");
  const stubs = [];
  let current = null;
  for (const line of lines) {
    const m = line.match(HEAD_RE);
    if (m && (m[1] || line.trimStart().startsWith("-") || line.trimStart().startsWith("*"))) {
      if (current) stubs.push(current);
      current = {
        id: `${finderId}#${stubs.length + 1}`,
        priority: m[1] ?? "P3",
        title: m[2].trim(),
        file: m[3],
        lines: m[5] ? `${m[4]}-${m[5]}` : m[4],
        body: ""
      };
    } else if (current && line.trim()) {
      current.body += (current.body ? "\n" : "") + line.trim();
    } else if (current && !line.trim()) {
      stubs.push(current); current = null;
    }
  }
  if (current) stubs.push(current);
  if (stubs.length > 0) return { stubs, clean: false, failed: false };
  const text = String(reviewText ?? "").trim();
  const clean = NO_FINDINGS_PATTERNS.some((re) => re.test(text));  // from render.mjs phrasings
  return { stubs, clean, failed: !clean };
}
```

  `NO_FINDINGS_PATTERNS` is built in Step 3 from the exact renderings found in `lib/render.mjs` — everything that is neither parsed findings nor a recognized clean rendering is `failed`.

  Calibrate the regex against the fixtures — the fixtures are the contract, the regex serves them (adjust separator variants — `—` vs `--` — to whatever the real renders contain; NEVER edit a fixture to make the regex pass).

- [ ] **Step 4: RED→GREEN, commit.** `git commit -am "feat(codex-companion): panel stub extraction calibrated on real review renders (drift guard included)"`

### Task 3: Finders fan-out + verifier with postconditions

**Files:**
- Modify: `skills/codex-companion/workflows/code-review.mjs`
- Test: extend `tests/codex-companion/test-panel-flow.sh`

- [ ] **Step 1: Write the failing tests** (mock scenarios):
  (a) happy: sweep 2 findings + 2 scalpels 1 finding each (fixture-real texts); verifier returns exact-set verdicts (1 CONFIRMED, 1 REFUTED, 1 duplicate→CONFIRMED primary, 1 CONFIRMED); assert result findings = 2 primaries ordered P0→P3, `verdict: "incorrect"`, coverage rows for all 3 finders.
  (b) verifier omission: verifier first response misses one id → assert one repair retry consumed; second still short → `verdict: "interrupted"`, `pool` attached, findings empty.
  (c) cyclic duplicateOf (a→b, b→a) → repair → interrupted (same path).

- [ ] **Step 2: Implement.** Add at the top of `code-review.mjs`:

```js
import { extractStubs } from "./lib/extract.mjs";
```

Then continue `run()`:

```js
  const finders = [
    { finderId: "sweep", lens: null },
    ...lenses.map((lens, i) => ({ finderId: `scalpel-${i + 1}`, lens })),
  ];
  const reviews = await parallel(finders.map(({ finderId, lens }) => async () => {
    const r = await review({ base, lens: lens ?? undefined, model: finderModel, effort: finderEffort, label: finderId });
    return { finderId, lens, ...r };
  }));

  const coverage = [];
  const pool = [];
  reviews.forEach((r, i) => {
    const f = finders[i];
    if (!r) { coverage.push({ finder: f.finderId, lens: f.lens, status: "dead", stubs: 0 }); return; }
    const { stubs, clean, failed } = extractStubs(r.reviewText, f.finderId);
    if (failed) { coverage.push({ finder: f.finderId, lens: f.lens, status: "extraction-failed", stubs: 0 }); return; }
    // clean === true (recognized no-findings rendering) or stubs parsed
    coverage.push({ finder: f.finderId, lens: f.lens, status: "ok", stubs: stubs.length });
    pool.push(...stubs);
  });

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

  function checkPostconditions(verdicts) {
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

  let verified = null;
  if (pool.length > 0) {
    const VERIFIER_PROMPT = `You are the binding verifier of a multi-reviewer panel. The candidate findings below came from independent reviewers of the diff against merge-base(HEAD, ${base}) — re-inspect the code yourself before judging. For EVERY candidate id return exactly one verdict: CONFIRMED (you can name the concrete failure) or REFUTED (state why it is wrong or not a real defect). Mark true duplicates with duplicateOf pointing at the strongest formulation, assign priority P0-P3 to confirmed findings, and put your evidence in comment.

Candidates (JSON):
${JSON.stringify(pool, null, 2)}`;
    const attempt = await agent(VERIFIER_PROMPT, {
      model: args.verifierModel ?? "gpt-5.6-sol", effort: args.verifierEffort ?? "high",
      schema: VERIFIER_SCHEMA, label: "verifier"
    }).catch(() => null);
    const errs = attempt ? checkPostconditions(attempt.verdicts) : ["verifier failed"];
    if (errs.length === 0) verified = attempt.verdicts;
    else {
      log(`verifier postconditions failed: ${errs.join("; ")} — retrying`);
      const retry = await agent(
        `Your verdict set violated the contract: ${errs.join("; ")}. Return the FULL corrected verdicts array covering every candidate id exactly once.\n\nCandidates (JSON):\n${JSON.stringify(pool, null, 2)}`,
        { model: args.verifierModel ?? "gpt-5.6-sol", effort: args.verifierEffort ?? "high",
          schema: VERIFIER_SCHEMA, label: "verifier-retry" }).catch(() => null);
      const errs2 = retry ? checkPostconditions(retry.verdicts) : ["verifier retry failed"];
      if (errs2.length === 0) verified = retry.verdicts;
    }
  } else {
    verified = [];
  }
```

  (Verifier retry is a FRESH `agent()` call — content-keyed separately, so resume never conflates the two.)

- [ ] **Step 3: RED→GREEN, commit.** `git commit -am "feat(codex-companion): panel finders fan-out + binding verifier with mechanical postconditions"`

### Task 4: Assembly + coverage honesty

**Files:**
- Modify: `skills/codex-companion/workflows/code-review.mjs`
- Test: extend `tests/codex-companion/test-panel-flow.sh`

- [ ] **Step 1: Write the failing tests**: (a) dead scalpel (mock `die` ×2) with otherwise zero findings → `verdict: "interrupted"`, coverage names the mandate; (b) dead scalpel WITH a surviving CONFIRMED elsewhere → `verdict: "incorrect"` + coverage caveat (a lost scalpel never suppresses a confirmed defect); (c) dead sweep WITH a surviving CONFIRMED elsewhere → `verdict: "interrupted"` AND the confirmed finding still present in `findings` (sweep loss is unconditional — this is the exact case the assembly must not leak as `incorrect`); (d) all finders ok, zero stubs (each returning the recognized no-findings rendering) → `verdict: "correct"` with the zero-findings coverage note; (e) verifier dead twice → `interrupted` + `pool` attached; (f) one finder returning BLANK output → treated as extraction-failed: coverage row `extraction-failed`, would-be-clean verdict `interrupted`.

- [ ] **Step 2: Implement assembly.**

```js
  const sweepDead = coverage.find((c) => c.finder === "sweep" && c.status !== "ok");
  const lostLenses = coverage.filter((c) => c.status !== "ok");

  if (verified === null) {
    return { verdict: "interrupted", findings: [], coverage, pool,
      explanation: "verifier did not produce a contract-valid verdict set; raw candidate pool attached" };
  }

  const byId = new Map(verified.map((v) => [v.id, v]));
  const stubById = new Map(pool.map((s) => [s.id, s]));
  const primaries = verified.filter((v) => v.verdict === "CONFIRMED" && !v.duplicateOf);
  const ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 };
  const findings = primaries.map((v) => {
    const stub = stubById.get(v.id);
    const dupSources = verified.filter((d) => d.duplicateOf === v.id).map((d) => stubById.get(d.id)?.id);
    return { id: v.id, priority: v.priority ?? stub.priority, title: stub.title,
      file: stub.file, lines: stub.lines, comment: v.comment,
      sources: [v.id, ...dupSources].map((id) => String(id).split("#")[0]) };
  }).sort((a, b) => ORDER[a.priority] - ORDER[b.priority]);

  let verdict = findings.length > 0 ? "incorrect" : "correct";
  let explanation = findings.length > 0
    ? `confirmed: ${findings.slice(0, 3).map((f) => f.title).join("; ")}`
    : "no confirmed findings";
  if (verdict === "correct" && lostLenses.length > 0) {
    verdict = "interrupted";
    explanation = `coverage incomplete (${lostLenses.map((c) => c.finder).join(", ")}) — a clean verdict cannot be asserted`;
  }
  if (verdict === "incorrect" && lostLenses.length > 0) {
    explanation += `; coverage partial: ${lostLenses.map((c) => c.finder).join(", ")}`;
  }
  if (sweepDead) {
    // Sweep loss UNCONDITIONALLY forces interrupted (round-failure rule) —
    // confirmed findings stay in `findings` as explicitly partial evidence.
    verdict = "interrupted";
    explanation = `the lens-free sweep did not complete — round is interrupted` +
      (findings.length > 0 ? `; ${findings.length} confirmed finding(s) attached as partial evidence` : "");
  }
  if (verdict === "correct" && coverage.every((c) => c.status === "ok") && pool.length === 0) {
    explanation += " (note: all finders returned zero findings — verify the diff target is what you intended)";
  }
  return { verdict, findings, coverage, explanation };
```

- [ ] **Step 3: RED→GREEN**, full runner + shell lint. **Commit.** `git commit -am "feat(codex-companion): panel deterministic assembly with coverage-honesty rules"`

### Task 5: X1 bench adapter + LIVE quality gate

**Files:**
- Create: `tests/review-bench/run-case-workflow.sh`
- Create: `tests/review-bench/results/<run-id>/` (live outputs + scores)
- Modify (on pass only): `docs/doperpowers/specs/2026-08-03-codex-workflow-engine-design.md` (Surprises + Outcomes)

- [ ] **Step 1: Read `tests/review-bench/run-case.sh`** — mirror its scratch-repo materialization exactly (it builds the committed `bench-change` branch vs `main`). Write `run-case-workflow.sh` with the same interface (`--case <dir> --out <file>`): materialize the case, then run
  `node <runtime> workflow --script skills/codex-companion/workflows/code-review.mjs --args '{"base":"main"}' --cwd <scratch> > <out>.json 2> <out>.events.log`
  and render `<out>` as a findings list (title/file/lines/comment per finding + the verdict line) so the existing adjudication flow reads it like any engine output.

- [ ] **Step 2: Smoke one seeded case live** (`case1`). Confirm mechanics only (finders spawn, journal complete, output renders); fix mechanical issues before the full run.

- [ ] **Step 3: Full live run — all five seeded cases.** One at a time (each panel is already ~2–6 concurrent xhigh reviews). Collect into `tests/review-bench/results/<run-id>/case<N>.workflow.txt`.

- [ ] **Step 4: Adjudicate per X1 rules** (mechanism-match against each case's `truth.json`; baits flagged = FP) into `scores.json`, and compare against the recorded codex-engine baseline in the existing results. **The predeclared bar: seeded recall ≥ baseline AND total FP ≤ baseline + 1.**
  - PASS → record scores + panel-vs-baseline table in the spec's Surprises, write the Outcomes line for the panel, commit.
  - FAIL → record honestly in Surprises; the panel ships as an experimental workflow with the failure documented, and is NOT referenced from any skill prose; open the follow-up (lens tuning / verifier effort escalation per spec Open Question 2). Do not weaken the bar.
  - Optionally (time permitting): the PR752 real case for the union-vs-13 comparison; comparative only.

- [ ] **Step 5: Final verification.** Full `tests/codex-companion/run-workflow-tests.sh`, `tests/claude-code/run-skill-tests.sh`, `scripts/lint-shell.sh` — all green. Commit results.
  `git commit -am "test(review-bench): panel workflow X1 run — scores vs codex baseline"`
