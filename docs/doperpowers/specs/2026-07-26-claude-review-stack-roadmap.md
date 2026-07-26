# Claude Review Stack Roadmap (2026-07-26)

> **Parent:** root — the fork's standing purpose (CLAUDE.local.md "What
> this repo is": a personal fork customized to how the human actually
> works, powering the autonomous board pipeline). **Consumes:** —.
> Children dispatch per their track hint; each child spec opens by citing
> this document (path + child id).

## Purpose

Claude models have overtaken the GPT models the review stack was built
around. This unit converts the stack's defaults to Claude end to end,
without losing review quality: the review *methodology* moves from the
native `codex exec review` engine to the argus-review plugin (improved
first against what Claude's native review skills know that it doesn't),
argus learns to choose its own effort instead of demanding a named level,
and the board pipeline's worker daemons default to plain Claude models
instead of the clodex gateway. Two repos participate: `SSFSKIM/argus-review`
(local clone `~/Developer/GitHub/codex-review`) carries the methodology
children; `doperpowers` carries the pipeline children.

## Parent-Level Acceptance

The unit closes when, on the live pipeline with no per-PR labels or
overrides:

1. A dispatched PR review runs on a plain-Claude worker whose review
   engine is an argus-review invocation, with the effort level selected by
   the skill itself — and the X1 benchmark, run side by side against the
   old codex engine, shows seeded-bug recall at least equal and no
   meaningful false-positive growth (the C4 gate, re-checkable at close).
2. The execplan exit-gate and the reviewing-prs documentation name
   argus-review as the primary review method; `codex exec review` appears
   only as opt-in or fallback.
3. A dispatched implement ticket runs on a plain-Claude worker by default;
   `engine:codex` still opts a ticket or PR back into the clodex route.

## Grounding Baseline

- Review engine today: `skills/reviewing-prs/scripts/review-engine.sh`
  runs `codex exec review --base` (default `gpt-5.6-sol`, effort xhigh) as
  a PURE engine; the worker's compliance audit is separate and stays.
- Worker routes today: `review-dispatch.sh`, `land-dispatch.sh`
  (reviewing-prs) and `implement-dispatch.sh` (implementing-tickets) all
  default to the clodex gateway (GPT via cliproxy); `engine:claude` label
  opts into plain Claude. The label picks the worker's model route only —
  the review engine is codex regardless of route.
- Second methodology touchpoint: `skills/execplan/SKILL.md:39` names
  `codex exec review` as the primary final-branch reviewer (Claude
  subagent as fallback).
- argus-review v0.3.0: skill + `argus-reviewer` (plain) +
  `argus-finder`/`argus-verifier` (medium/high/xhigh/max ladder). Effort
  is explicit-only; no level named means plain. Provenance
  (`references/provenance.md`) records the codex-app detached path as
  examined and deliberately not ported (no context isolation, prompt-only
  tool restriction, upstream-unfinished).
- Comparison sources on disk: official `code-review` plugin
  (`~/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-review/`),
  Claude Code built-in `/review` and `/code-review` prompt sources in the
  stable checkout `~/Developer/GitHub/codex_somersault/Claude Code Src/src/commands/`
  (`review.ts`, `review/` incl. ultrareview, `security-review.ts`).

## Children

### C1: Methodology comparison & benchmark definition — spike (findings, never a merge)

- **Purpose:** Establish what Claude's native review methodologies know
  that argus doesn't (and vice versa), and build the measuring stick every
  later child's "no regression" claim stands on. Compare argus-review
  against the official `code-review` plugin and the built-in `/review` and
  `/code-review` — mechanism AND content: rubric wording, lens texts,
  false-positive guidance, confidence-scoring rubrics (native's 0–100
  confidence filter vs argus's CONFIRMED/PLAUSIBLE verdicts is the known
  axis of interest). The codex-app path is settled by provenance.md and is
  not re-examined.
- **Acceptance:** G1 (required): a findings document recording, per
  methodology, the mechanism map, the content-level comparison, and a
  list of adoption candidates for argus each marked adopt/reject with
  reasons. G2 (required): the X1 benchmark exists and has been run once
  against both the current codex engine and current argus (v0.3.0),
  producing the baseline numbers later children measure against.
  G3 (required): the headless-invocation probe — a daemon-style
  non-interactive invocation of current argus (an explicitly pinned
  level; no C2/C3 work needed) produces the standard Findings/Verdict
  contract captured to a file within a bounded wait. This proves X2
  feasibility before any downstream child spends effort, and the probe
  harness becomes the invocation context the X1 bench uses for its argus
  runs. If the probe fails, the failure flows back here before C2
  dispatches.
- **Edges:** blocked-by: —; blocks: C2.
- **Contracts:** owns X1; proves X2 feasibility (G3).
- **Required:** required.
- **Status:** not-dispatched (dispatchable now).

### C2: argus methodology improvements — autonomous expected; confirm at dispatch

- **Purpose:** Land C1's adopted candidates in the argus-review repo —
  the methodology upgrade that justifies making argus the default. Skill
  and agent-text changes follow the writing-skills discipline.
- **Acceptance:** an argus-review release whose changes trace to C1
  adoption decisions and the human's close-of-C1 direction, with the X1
  benchmark re-run showing: G1 (required) — **single-agent plain reaches
  the codex bar** (recall ≥ codex baseline on the seeded set, no
  meaningful FP growth) — the fair weight-class target, since codex is
  itself a single inline reviewer; G2 (required) — the multi-agent
  ladder's **subagent economy is repriced**: levels spend subagents
  proportionally to the diff (no fixed large fleet), and the re-run
  shows no recall loss at high versus baseline high.
- **Edges:** blocked-by: C1; blocks: C3.
- **Contracts:** consumes X1.
- **Required:** required.
- **Status:** LANDED 2026-07-26 (in-session, human-directed). argus-review
  v0.4.0 (G1 uplift + G2 repricing) + v0.4.1 (injection-sink boundary).
  Both bars met on the post-#36 fixtures: G1 — plain r3 17/17 seeded,
  FP 0, vs codex r3 17/17 FP 0; G2 — high r2 17/17 (= baseline high),
  FP 2→0, finder wave 5→2, wall time ~halved. Scoring:
  `tests/review-bench/results/2026-07-26-c2-scores.json`.

### C3: Effort auto-routing over a multi-lens reviewer ladder — autonomous expected; confirm at dispatch

- **Purpose:** Two coupled moves, the second added by human direction
  2026-07-27. (a) Auto-routing: make argus choose its own effort from
  the diff's size and stakes instead of demanding a named level, so
  headless callers (and casual interactive ones) get the right machinery
  without knowing the ladder exists. (b) Ladder rearchitecture: retire
  the finder/verifier species entirely — every level dispatches only
  full reviewers (the plain rubric), higher levels adding reviewers with
  lens-scoped mandates partitioned to minimize diff overlap. Effort IS
  the reviewer count; there is no other machinery to route.
- **Acceptance:** with no level named, the skill selects and announces a
  level derived from the change under review; an explicitly named level
  still wins (X3); the selection logic is observable (the announcement
  states what drove the choice); no finder/verifier dispatch remains at
  any level; a scored X1 re-run at the rearchitected top level shows no
  recall loss against C2's high r2 (19/20 full denominator, FP 0).
- **Edges:** blocked-by: C2 (routes over the post-C2 reviewer prompt);
  blocks: C4.
- **Contracts:** owns X3; participates in X2.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C2).

### C4: Review engine swap in doperpowers — execplan expected; re-gate at dispatch

- **Purpose:** Replace `codex exec review` with argus-review at every
  point doperpowers calls a review *methodology*: the reviewing-prs loop
  engine (`review-engine.sh` and the worker protocol around it) and the
  execplan final-branch exit-gate, plus the documentation prose that names
  the method. Non-review codex uses are out of scope (standing exclusion).
- **Acceptance:** G1 (required): a dispatched PR review on the live loop
  runs argus as its engine and the X1 side-by-side bench passes per the
  bar fixed in X1. G2 (required): execplan's exit-gate and reviewing-prs
  docs name argus first, codex as fallback at most.
- **Edges:** blocked-by: C2, C3; blocks: C5.
- **Contracts:** consumes X1, X2.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C2, C3).

### C5: Review-loop worker default → Claude — autonomous expected; confirm at dispatch

- **Purpose:** Flip the default model route of the review and land
  workers (`review-dispatch.sh`, `land-dispatch.sh`) from the clodex
  gateway to plain Claude, and remove the nested-codex plumbing
  (TLS/CODEX_HOME/seatbelt workarounds in the engine path) that only the
  codex engine needed. To resolve the apparent tension with
  Parent-Level Acceptance 2: after C5 the loop's review engine is argus
  on EVERY worker route — `engine:codex` changes only the worker's model
  route (X4), never the engine — and the "codex as fallback" the parent
  acceptance permits lives in interactive/execplan contexts only, so the
  nested-codex plumbing has no remaining loop caller and is deleted.
- **Acceptance:** a label-less review dispatch spawns a plain-Claude
  worker end to end; `engine:codex` still opts back into the gateway
  route (X4); the removed plumbing has no remaining caller.
- **Edges:** blocked-by: C4; blocks: —.
- **Contracts:** participates in X4.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C4).

### C6: Implement worker default → Claude — autonomous (small, direct)

- **Purpose:** Flip `implement-dispatch.sh`'s default route from clodex
  to plain Claude. Independent of the review-stack sequence; the human
  has ruled a performance bench unnecessary (Opus 5-class models now beat
  the GPT route for implementation).
- **Acceptance:** a label-less implement dispatch spawns a plain-Claude
  worker; `engine:codex` still opts back into the gateway route (X4).
- **Edges:** blocked-by: —; blocks: —.
- **Contracts:** participates in X4.
- **Required:** required.
- **Status:** not-dispatched (dispatchable now).

## Cross-Child Contracts

- **X1 — the review benchmark** (owner: C1, delivered by C1.G2). A fixed,
  re-runnable diff set — seeded-bug diffs plus a handful of real
  previously-reviewed PRs — with a defined scoring: seeded-bug recall and
  false-positive count. The non-regression bar, binding C2 and C4: recall
  at least equal to the codex-engine baseline, no meaningful
  false-positive growth. C1 fixes the set, the metrics, and what
  "meaningful" is; later children re-litigate none of it. The argus side
  of every bench run is invoked through the headless path the C1.G3
  probe establishes — the same context C4 deploys — so baseline and
  deployment measure the same thing.
- **X2 — headless invocability** (binds C3, C4; feasibility proven by
  C1.G3). argus-review must be invocable non-interactively by a worker
  daemon (plugin installed in the worker harness, e.g. a `claude -p`
  slash invocation), producing the standard Findings/Verdict contract
  with no human present — which is why effort auto-routing (C3) precedes
  the engine swap (C4). The cheap feasibility probe runs at C1 (G3),
  before any downstream spend; C4 consumes the proven mechanism and
  names the minimum argus version it requires.
- **X3 — effort override semantics** (owner: C3). Auto-routing is the
  default only when no level is named; an explicitly named level always
  wins. Written to outlive this unit as part of argus's public contract.
- **X4 — route label semantics** (binds C5, C6). After the default flip,
  `engine:codex` label = clodex gateway opt-in; `engine:claude` becomes
  redundant-but-valid. The opt-in must survive so individual tickets/PRs
  can ride the GPT route.

## Ordering & Dependency Map

Forced sequence: C1 → C2 → C3 → C4 → C5 (methodology must be measured,
then improved, then self-routing, before it becomes the engine; the
worker flip rides after the engine swap so the codex-only plumbing can be
deleted in the same motion). C6 is parallel to everything and dispatchable
immediately. C1 and C6 can start today.

## Risks & Mitigations

- **Bench too weak to detect regression** (X1): seeded-bug recall on a
  small set is noisy. Mitigation: C1 sizes the set until the codex
  baseline is stable across two runs; the bar includes the FP axis so a
  recall win by spraying findings can't pass.
- **Headless skill invocation friction** (X2): a daemon driving a slash
  skill is less proven than driving a CLI binary. Mitigation: the C1.G3
  probe front-loads this — it runs today, with a pinned level, before
  C2/C3 spend anything; a failure flows back here while the whole chain
  is still undispatched.
- **argus loses the bench at C4** — the unit's central risk: even after
  C2, argus recall may trail the codex baseline. Early warning: C2's
  acceptance reports the argus-vs-codex delta, so a large gap surfaces
  two children before the gate. Decision rule at C4 (so a dispatched
  worker is never stuck): one retry with the auto-routed default effort
  raised; if the bench still fails the X1 bar, C4 parks needs-human with
  the numbers and the discovery flows back here — whether to iterate C2
  again, ship despite the gap, or abandon the swap is the human's call,
  not the worker's.
- **argus release vs doperpowers pin skew**: the loop consumes argus via
  marketplace install. Mitigation: X2 makes C4 name its minimum argus
  version; C4's acceptance runs on the live loop, which catches skew.

## Deferred / Out of Scope

- **Deferred (may return):** retiring the clodex gateway entirely
  (triaging-feedback's Codex-SDK worker, orchestrating-daemons'
  codex-spawn infrastructure, the `engine:codex` opt-in itself) — next
  unit, seeded by this one's retrospective.
- **Explicitly out of scope:** non-review codex uses (triage worker,
  codex-spawn substrate) — this unit converts the review stack, it does
  not evict codex; re-examining the codex-app detached review path
  (settled by argus provenance.md, trusted per the human's ruling).

## Tracking Map

Epic: doperpowers#27. Materialized 2026-07-26 after approval.

| Child | Spec / ticket | Status |
|---|---|---|
| C1 | doperpowers#28 | landed (closed done 2026-07-26). Findings doc: `2026-07-26-c1-review-methodology-findings.md`; follow-ups #36 (fixtures), human direction → C2 |
| C2 | doperpowers#29 | landed (closed done 2026-07-26, in-session). argus-review v0.4.0+v0.4.1; both bars met; scoring `2026-07-26-c2-scores.json`; fixture follow-up ticket registered at close |
| C3 | doperpowers#30 | eligible (unblocked by C2 close) |
| C4 | doperpowers#31 | not-dispatched (blocked-by C2, C3) |
| C5 | doperpowers#32 | not-dispatched (blocked-by C4) |
| C6 | doperpowers#33 | in-flight (daemon worker, claude route) |

## Decision Log

- **Decomposing route over one controlled spec.** Four-plus deliverables
  across two repos with different verification strategies; a single spec
  would chain unrelated acceptances with "and". Rejected: one
  brainstorming→spec→plans pass.
- **C1 compares against Claude-native methods only; codex-app path
  trusted to provenance.md.** Grounding found provenance already examined
  the app's detached path and recorded the rejection rationale (no
  context isolation, prompt-only enforcement, upstream-unfinished; commit
  8f1ae79). The candidate wider sweep of codex-rs review surfaces was
  rejected by the human's testimony: guardian review is a tool-use
  auto-classifier, cloud-tasks is not the app review path.
- **Benchmark defined inside C1, not its own child and not at C4 time.**
  The comparison spike needs an empirical leg anyway, and the baseline
  must be measured while the codex engine is still the default — deferring
  to C4 would lose the clean baseline. Rejected: separate bench child
  (no independent purpose), C4-time definition (measurement after the
  swap can't anchor "no regression").
- **C3 kept separate from C2.** Same repo, but independently verifiable
  deliverable (routing behavior vs review content) and C4 depends on C3
  specifically through X2. Rejected: folding auto-routing into the C2
  release.
- **C4 covers the execplan exit-gate, not just the loop engine.** Leaving
  the exit-gate on codex would contradict the unit's purpose ("default
  review methodology = argus"). Rejected: loop-only scope.
- **Non-regression bar = side-by-side bench (option a).** A qualitative
  spot-check (option b) was rejected as too weak to claim the "without
  losing performance" requirement verified.
- **Finder/verifier retired; effort = reviewer count** (human direction,
  2026-07-27). Codex is always a single agent; the only genuine lever
  higher effort adds is multiple full reviewers with lens-scoped
  mandates partitioned to minimize diff overlap, each investigating its
  lenses more thoroughly — no recall-biased finder feeding a separate
  verifier. Evidence: the native `/code-review medium` runs ZERO
  subagents and verifies inline by executing the code
  (transcript-checked during the builtin bench probe, 2026-07-27);
  the human's operational experience is that codex exec review findings
  are essentially never refuted, so a dedicated verification stage buys
  nothing; and in high r2 the verification layer actively cost a true
  positive (the case4-u2 refutation). v1.2 had already named this the
  "likely shape"; C2 repriced within the old machinery instead — that
  interim is superseded, and the rearchitecture lands in C3.
- **C6 split out of C5 with no edges.** The implement-worker flip is an
  independent shippable blocked by nothing; folding it into C5 would
  park it behind C4 for no reason. The human ruled a bench unnecessary
  for it. C5 stays behind C4 so the nested-codex plumbing removal lands
  with the flip. Rejected: one worker-flip child behind C4.

## Surprises & Discoveries

- **The `engine:` label does not select the review engine.** It selects
  the worker daemon's model route (`review-dispatch.sh:401-408`); the
  engine is `codex exec review` on every route. "Engine swap" (C4) and
  "worker flip" (C5/C6) are therefore fully separate code points —
  discovered in grounding, and it reshaped the cut.
- **provenance.md already covered the codex-app path.** The initiative's
  initial framing assumed it unexamined; the record (with rejection
  rationale) was already in the argus repo.
- **The codex engine's default model 400-failed, transiently** (found
  2026-07-26 during C1 baseline work): the backend rejected `gpt-5.6-sol`
  (and 5.6/5.6-codex/5.3-codex), leaving only `gpt-5.5` — the live loop
  would have parked every review ENGINE-UNAVAILABLE. Human ruling: a
  subscription-tier outage, since restored; `gpt-5.6-sol` re-verified
  working the same day and the stopgap ticket #34 closed wontfix. X1's
  codex baseline runs on the production default (`gpt-5.6-sol` xhigh).
  The fragility datum stands: the codex route sits on an external
  account tier that can silently revoke the engine's model.
- **X1 baseline outcome (C1 flow-back, 2026-07-26): argus passes the bar
  at HIGH, not at plain.** codex (gpt-5.6-sol xhigh): 17/17 seeded
  recall, 1 [P1] FP, stable across two runs. argus plain (Opus 5,
  effort high, headless): 16/17, 0 FP — misses only the L4 injection
  (plain has no security lens). argus high: 17/17, 2 [P3] FPs — recall
  tied, FP growth +1 (within the bar), and both FPs verdict-neutral
  where codex's is verdict-flipping. Consequence for C3/C4: the engine
  context deploys argus at high (or C3 auto-escalates to it); plain
  stays the interactive fast path.
- **Prompt content alone did not close plain's security gap — the
  boundary definition did** (C2, 2026-07-26). v0.4.0 gave plain the full
  seven-family investigation sweep, including a security family with the
  same wording whose L4 lens catches the case4 injection at high — and
  plain STILL missed it (16/17), a correlated-censorship effect: under
  the rubric's precision stance the reviewer resolves the ambiguity of
  "external input" conservatively (an operator-supplied `--label` didn't
  count). v0.4.1 codified the boundary the native standard actually
  applies — unconstrained value interpolated into a (remote-)shell
  command line is a sink regardless of provenance — and plain r3 went
  17/17 with FP still 0, tagging the injection the same P2 codex does.
  Lesson for skill text: hunting pressure fails at the margin unless the
  *qualifying boundary* is stated; the families say where to look, the
  boundary says what counts.
- **The economy repricing cost nothing measurable** (C2, 2026-07-26):
  bundling 5 lenses onto 2 finders on ~100–300-line diffs and packing
  verifiers (whole groups, ≤4 candidates) kept high at 17/17 while
  halving wall time (322–581 s vs 579–1133 s) and cutting the fleet to
  5–7 subagents/case. The r1 "high needs 2 FPs" datum also dissolved:
  both r1 FPs were fixture-bait artifacts (#36 defused them); high r2
  runs FP 0.
- **Cross-engine disagreement on a promoted truth**: case4-u2 (remote
  umask exposure) — codex finds it in every run; an argus high verifier
  actively REFUTED it in r2. Carried to the next fixture pass rather
  than adjudicated unilaterally.
- **Built-in `/review`/`/code-review` prompt sources are on disk** (the
  codex_somersault checkout carries Claude Code source at
  `Claude Code Src/src/commands/`) — C1 needs no extraction work. (An
  earlier draft also cited `~/.claude/jobs/*/src/commands/` — wrong: that
  directory is per-session-volatile and carries no command sources.)

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check:
verify Parent-Level Acceptance as written — all children landed is not the
same event — then retrospect.

## Revision Notes

- **2026-07-27 (v1.4, C3 rescope by human direction):** C3 now carries
  the ladder rearchitecture alongside auto-routing: finder/verifier
  retired at every level, multi-lens full reviewers only, effort =
  reviewer count (see the Decision Log entry of the same date for the
  evidence). C3's acceptance gains the no-finder/verifier check and an
  X1 non-regression bar against C2 high r2. C3 was not in flight; no
  worker flag needed. A builtin-engine bench round (`/review`,
  `/code-review medium` — background-session invocation, not headless)
  is in flight the same day as C4 comparison data.
- **2026-07-26 (v1.3, C2 close):** C2 landed as argus-review v0.4.0
  (INVESTIGATION SWEEP into plain — five lens families + language-pitfall
  and wrapper/delegation families from the built-in's angles D/E; AC1 FP
  exclusions mirrored into the verifier; AC3 conventions check with the
  correctness-only engine skip; the no-execute conduct sentence; G2
  diff-proportional finder fleet `ceil(lines/150)` clamped [2, lens
  count] with round-robin lens bundling, packed verifiers, AC9 sweep
  footguns) and v0.4.1 (the injection-sink boundary — see Surprises).
  Both C2 bars verified on post-#36 fixtures; scoring consolidated in
  `tests/review-bench/results/2026-07-26-c2-scores.json`. The v1.2
  interim consequence RESOLVES to: **the engine can deploy uplifted
  plain** (C4), with C3's dial escalating large/high-stakes diffs to the
  repriced high. Informational delta for C4 as required by C2's ticket:
  on the full 20-defect denominator codex r3 is 20/20 vs plain r3 17/20
  and high r2 19/20 — the remaining gap lives entirely in the promoted
  second-tier u-entries, which is C3-escalation territory, not further
  plain prompt growth. C3 is now eligible.
- **2026-07-26 (v1.2, C1 close — human direction reshapes C2):** The X1
  result "argus passes at high" carries a weight-class caveat the human
  named at spike close: codex is a single INLINE reviewer, argus high is
  a multi-agent panel — not a like-for-like win. C2's acceptance is
  restated accordingly: (G1) raise SINGLE-agent plain to the codex bar
  (fold security-hunting pressure into plain, referencing the native
  codex review mechanism in the codex_somersault source and the C1 adopt
  list; the built-in's o48 inline cells — 8 angles in one context, no
  subagents — are prior art for multi-angle single-pass); (G2) reprice
  the multi-agent ladder's subagent economy (argus high+ and built-in
  /code-review alike overspend agents; the likely shape is the same
  single-reviewer mechanism scoped to different seams rather than
  separate finder/verifier machinery, with fleet size scaled to the
  diff). The earlier "engine deploys high" consequence is downgraded to
  interim: if C2.G1 lands, the engine can deploy uplifted plain, with
  escalation reserved for large/high-stakes diffs (C3's dial). C2 was
  not in flight; no worker flag needed.
- **2026-07-26 (v1.1, pre-approval external review):** F1 — corrected the
  built-in command-source path (the volatile `~/.claude/jobs/` citation
  was wrong; the stable source is the codex_somersault checkout). F2 —
  added C1.G3, the headless-invocation probe, front-loading X2
  feasibility from C4 to C1. F3 — added the bench-loss risk with a
  decision rule for C4 (retry at raised effort, then park needs-human)
  and made C2 report the argus-vs-codex delta. F4 — C5 now states
  explicitly that post-C5 the loop engine is argus on every route and
  the parent's "codex fallback" is interactive/execplan-only. F5 — X1
  now pins the bench's argus invocation context to the C1.G3 headless
  path. No child was in flight; no flags needed.
