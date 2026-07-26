# C1 findings — review-methodology comparison & X1 benchmark (2026-07-26)

> Child **C1** of `docs/doperpowers/specs/2026-07-26-claude-review-stack-roadmap.md`
> (epic doperpowers#27, ticket #28). Spike deliverable: findings + the X1
> benchmark. Sources: argus-review v0.3.0 (read in full), the official
> `code-review` marketplace plugin (read in full), and the built-in
> `/review` / `/code-review` / `/ultrareview` pipelines extracted from the
> installed Claude Code 2.1.220 binary (byte-offset citations available in
> ticket #28's extraction record; the `codex_somersault` checkout predates
> the modern `/code-review`).

## 1. The landscape — five pipelines, three philosophies

| Pipeline | Fan-out | Verification | Confidence | Isolation | Severity |
|---|---|---|---|---|---|
| argus plain | 1 isolated reviewer | none (rubric'd single pass) | Verdict block w/ confidence float | **full** (fresh context) | P0–P3 |
| argus medium…max | 3–6 finders + verifier/group (+2 refuters/severe @max) | independent re-derivation, 3 postures | CONFIRMED/PLAUSIBLE/REFUTED | **full** at every role | P0–P3 |
| built-in `/code-review` | 0 (low) / 8 (med,high) / 10 (xhigh,max) angles; workflow: 4–6 agents | 1 verifier per candidate (or per file:line group) | CONFIRMED/PLAUSIBLE/REFUTED | **none** — runs in a fork inheriting the conversation | none (ordinal) |
| official plugin | 5 Sonnet lenses + Haiku scorers | Haiku score per issue | 0–100, cutoff ≥80 | per-agent fresh, orchestrated in PR session | none |
| built-in `/review` | none | none | none | none | none |

Philosophies: **argus** = native codex inline review (isolation + rubric)
extended with an isolated multi-agent ladder; **built-in `/code-review`** =
the same ladder FORM (argus's ladder deliberately followed it — provenance
deviation 8) with richer angle content but no context isolation; **official
plugin** = precision-filtered context-source review (repo standards,
history), superseded in spirit by the built-in.

## 2. Content-level comparison (the meat)

### 2.1 Correctness lenses/angles

Near-isomorphic pairs: built-in Angle A (line-by-line hunk scan) ≈ argus
L1; Angle B (removed-behavior auditor) ≈ argus L3; Angle C (cross-file
tracer) ≈ argus L2. Divergences:

- Built-in **Angle D — language-pitfall specialist** (falsy-zero, `==`
  coercion, mutable default args, late-binding closures, nil-map writes,
  range-var capture, TZ/DST, float equality): argus has no counterpart;
  these defect families hide inside L1's generic "logic defects" with no
  prompting pressure to hunt them.
- Built-in **Angle E — wrapper/proxy correctness** (delegate routing,
  method forwarding): no argus counterpart; a recurring real-world bug
  shape.
- argus **L4 (security surface)** and **L5 (performance/resources)**: no
  built-in correctness counterpart (Efficiency is a cleanup angle, not a
  defect hunt; security lives in `/security-review`).

### 2.2 Verification

Both modern systems use the same 3-state ladder — argus's verifier
postures (neutral / recall-biased / refuter) against the built-in's two
ladders (standard + "PLAUSIBLE by default" recall guidance at high+).
Substantive differences:

- argus verifiers **re-derive from the code** with an explicit judging
  standard (the 8 rubric criteria) and never execute code; built-in
  verifiers get "the diff, the relevant file(s), and the candidate".
- argus max adds the **adversarial vote** (2 refuters per severe finding,
  drop only on double-REFUTED, promotion on refuter-CONFIRMED); the
  built-in has **no adversarial pass at any level**.
- The built-in workflow variant drops unverified candidates ("so
  unverified candidates never reach the report as fabricated PLAUSIBLE")
  — argus's failure handling reaches the same invariant.

### 2.3 False-positive doctrine

- argus: the 8 bug criteria (impact, discrete, rigor-match, introduced,
  author-would-fix, no unstated assumptions, provable cross-file impact,
  not-intentional).
- Official plugin adds exclusions argus lacks: **"issues a linter,
  typechecker, or compiler would catch (safe to assume CI runs them)"**
  and **"called out in CLAUDE.md but explicitly silenced in the code
  (lint-ignore)"**.
- The built-in at high+ runs the OPPOSITE direction: "PLAUSIBLE by
  default", "REFUTED only when constructible", "a single non-REFUTED vote
  carries the finding" — recall-biased by design, matching argus's
  high/xhigh posture. The plugin's ≥80 precision cutoff is the outlier,
  and the built-in's own evolution away from numeric scoring to the
  3-state ladder reads as a verdict on it.

### 2.4 Context-source review (what argus cannot see at all)

The official plugin's lenses #1/#3/#4/#5 (CLAUDE.md compliance, git
blame/history, prior-PR comments, code-comment guidance) and the built-in's
**Conventions angle** (find governing CLAUDE.md files, quote the exact rule
+ the exact violating line, "no style preferences, no vague spirit-of-the-doc
inferences") review the change against **repo context**. argus at every
level reviews only the diff and code reachable from it — it cannot flag
"this violates the repo's stated conventions" or "this regressed what PR
#N fixed".

### 2.5 Effort routing (C3's prior art)

The built-in already auto-routes:

- Default level derives from the **session effort setting** when the user
  names none (clamped by org policy, default medium).
- Sonnet-5 high+ cells compute a **finder budget from diff size**:
  `git diff --numstat` → "Spawn about ceil(lines/150) finder subagents
  (min 2, max 8) — scale your investigation depth to the diff size rather
  than using a fixed large fleet", with a "treat as a floor when
  uncommitted changes aren't counted" variant.
- `xhigh` vs `max` differ ONLY in the orchestrator's API reasoning effort
  — structure is identical. Effort scales three things: angle count,
  per-angle candidate budget, pipeline depth (verify → verify+sweep).

### 2.6 Structural differentiators argus should keep

- **Isolation.** Built-in `/code-review` runs in a fork that inherits the
  full conversation — the authoring context reviews its own code. argus
  isolates every role; the orchestrator never judges. This is argus's
  strongest structural claim and the native inline path's core property.
- **P0–P3 severity tags** (native-derived): the built-in is ordinal-only;
  the loop's verdict derivation (approve unless critical/high unresolved)
  needs severity, so argus's tags are load-bearing for C4.
- **The adversarial max pass**: beyond anything the built-in runs.
- **Prompt-injection defense** as explicit conduct text (repo content is
  data; injection attempts in the change are themselves findings).

## 3. Adoption decisions (C2's adopt list)

Each candidate marked **ADOPT** (C2 implements), **REJECT** (with reason),
or **ROUTE** (input to another child).

- **AC1 ADOPT — lint/CI-catchable exclusion.** Add to the argus reviewer
  guidelines and verifier criteria: don't flag what a linter, typechecker,
  compiler, or CI would catch, and don't flag rules explicitly silenced in
  code. Cheapest cut of the commonest noise class. (Source: official
  plugin FP list; consistent with the built-in's angle texts.)
- **AC2 ADOPT — language-pitfall and wrapper/proxy hunting pressure.**
  Fold Angle D's pitfall families and Angle E's wrapper/delegate checks
  into argus: enrich L1's lens text with the pitfall families and add
  wrapper/proxy routing to the sweep's focus list (or a 6th lens at
  high+ — C2 decides the exact carrier after eval). Real defect families
  with no current prompting pressure.
- **AC3 ADOPT (flagged) — a Conventions/CLAUDE.md lens.** Adopt the
  built-in Conventions angle's discipline verbatim-adapted (quote the
  exact rule + exact line, else nothing). Flag for C2/C4: the loop engine
  is deliberately PURE correctness (ticket/spec compliance is the review
  worker's own audit) — the lens must be omittable in engine context, or
  its findings must carry a distinct category the worker can triage
  separately. C2 designs the wiring; the tension is recorded here.
- **AC4 REJECT — 0–100 numeric confidence scoring.** The 3-state ladder
  argus already shares with the built-in encodes the actionable
  distinction; numeric anchors invite false precision, and the built-in's
  own move away from them is evidence. (Also rejected: score-cutoff
  precision filtering as the default posture — argus's per-level postures
  already cover the precision/recall dial.)
- **AC5 REJECT — cleanup/altitude angles (Reuse, Simplification,
  Efficiency, Altitude).** Argus's role — and the C4 engine role — is
  correctness review; cleanup is a different product (the `/simplify`
  shape). Keeping the review PURE keeps the loop's verdict derivation
  clean. Recorded as deferred: an argus "cleanup mode" could exist, but
  not in this unit.
- **AC6 REJECT — finding floors** ("at least min(files,4) findings").
  Directly conflicts with the rubric's "prefer outputting no findings"
  precision stance and invites invention; the built-in itself caveats it.
- **AC7 REJECT — Haiku-tier verification.** argus mandates sonnet-class+
  for verifiers ("verification quality is the product"); the built-in
  uses same-tier subagents too. The plugin's Haiku scorers are the
  weakest link of the weakest pipeline.
- **AC8 ROUTE → C3 — diff-size-scaled routing.** The finderBudgetHint
  mechanism (numstat → ceil(lines/150), clamp) plus session-effort-derived
  default level is the shape C3 should adapt: route the LEVEL from diff
  size/stakes signals, keep explicit names as override (X3). Concrete
  seed: measure numstat + changed-file criticality; small mechanical diff
  → plain; medium/large or high-stakes paths → medium/high; the ladder's
  cost curve (subagent counts) is documented in effort-levels.md.
- **AC9 ROUTE → C4 — sweep/second-tier focus parity.** argus's sweep
  text already covers the built-in's gap list (defaults evaluated once,
  setup/teardown asymmetry, moved-code anchors); add the built-in's
  "second-tier footguns" examples (hash nondeterminism, lock-scope
  shrink, predicate side effects) to the sweep assignment during C2 —
  one-line enrichment, no structural change.

## 4. G3 — headless invocation probe (X2 feasibility): PASS

`claude -p "/argus-review:argus-review …" --permission-mode auto` from a
fixture repo (daemon conditions mirrored): skill triggered, plain
argus-reviewer dispatched, full `## Findings`/`## Verdict` contract
captured to a file, rc=0, ~10 min wall on an 11-line diff. Both seeded
bugs found; both intentional-change baits correctly unflagged (0 FP).
Consumer caveats for C4: extract the Findings/Verdict block tolerantly
(wrapper prose surrounds it — native parses tolerantly too); paths may be
absolute; budget ~10 min floor even for tiny diffs (the loop's current
engine bound is 45 min).

## 5. X1 benchmark — design and baselines

Contract and scoring: `tests/review-bench/README.md`. 5 seeded cases
(L1–L5 spread + FP baits) + 3 real merged PRs (#12, #19, #21). Both
engines review the identical committed branch-vs-base range; argus always
via the headless path.

**Engine-availability surprise (2026-07-26):** the codex engine's
configured default `gpt-5.6-sol` was 400-rejected by the backend during
baseline setup (as were 5.6, 5.6-codex, 5.3-codex; only `gpt-5.5`
worked). Human ruling: a transient subscription-tier outage, restored the
same day — `gpt-5.6-sol` re-verified, stopgap #34 closed wontfix. The
codex baseline runs on the production default **gpt-5.6-sol xhigh**. The
fragility datum stands for the roadmap: the codex route depends on an
account tier that can silently revoke the engine's model.

Smoke datum (not baseline; gathered during the outage): on the 11-line
probe fixture, argus plain found 2/2 seeded bugs, codex (gpt-5.5 xhigh,
94 s) found 1/2 — both 0 FP.

**Baseline results (final, 17 seeded bugs across 5 cases):**

| Engine | Seeded recall | FP | FP severity | Time/case |
|---|---|---|---|---|
| codex `gpt-5.6-sol` xhigh (production default) | **17/17** — identical across two runs (stability met) | 1 | [P1] | 4–13 min |
| argus **plain** (Opus 5, effort high, headless) | 16/17 | **0** | — | 2–4.5 min |
| argus **high** (same model/effort, multi-lens ladder) | **17/17** | 2 | both [P3] | 10–19 min |

- argus plain's sole miss (the case4 L4 ssh injection) is **found at
  high** — the ladder's security lens working as designed.
- Every FP on both engines' side involved the same unreachable-TOCTOU
  fixture finding; codex tagged it [P1] (verdict-flipping in the loop's
  approve/needs-attention derivation), argus [P3] (verdict-neutral).
  Severity-weighted FP cost favors argus.
- **X1 bar verdict**: argus at HIGH passes (recall 17 = codex 17; FP +1,
  within the bar). argus at PLAIN fails on recall (16<17). → the C4
  engine must deploy argus at high (or C3 must auto-escalate to high for
  the engine context); plain remains the fast, zero-FP interactive
  default.
- Real-PR side (comparative): both engines converge on the same core
  defect on pr19; pr12/pr21 show argus more doc-consistency-oriented,
  codex slightly broader. Full mapping in `results/*/scores.json`.

## 6. Flow-back to the roadmap

- Recorded in the roadmap's Surprises: the engine-model outage; the
  checkout lacking modern `/code-review` (extraction came from the
  installed binary).
- C3's section gains no new constraints; AC8 is its design seed.
- C4 consumers: G3 caveats (tolerant parsing, timing floor) + AC3's
  engine-purity flag.
