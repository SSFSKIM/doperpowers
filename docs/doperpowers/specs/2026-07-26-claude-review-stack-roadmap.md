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
  Claude Code built-in `/review` and `/code-review` prompt sources
  (`~/Developer/GitHub/codex_somersault/Claude Code Src`,
  `~/.claude/jobs/*/src/commands/review`).

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
- **Edges:** blocked-by: —; blocks: C2.
- **Contracts:** owns X1.
- **Required:** required.
- **Status:** not-dispatched (dispatchable now).

### C2: argus methodology improvements — autonomous expected; confirm at dispatch

- **Purpose:** Land C1's adopted candidates in the argus-review repo —
  the methodology upgrade that justifies making argus the default. Skill
  and agent-text changes follow the writing-skills discipline.
- **Acceptance:** an argus-review release whose changes trace one-to-one
  to C1 adoption decisions, with the X1 benchmark re-run showing the new
  argus at least matching baseline argus.
- **Edges:** blocked-by: C1; blocks: C3.
- **Contracts:** consumes X1.
- **Required:** required.
- **Status:** not-dispatched (blocked-by C1).

### C3: Effort auto-routing — autonomous expected; confirm at dispatch

- **Purpose:** Make argus choose its own effort level from the diff's
  size and stakes instead of demanding a named level, so headless callers
  (and casual interactive ones) get the right machinery without knowing
  the ladder exists.
- **Acceptance:** with no level named, the skill selects and announces a
  level derived from the change under review; an explicitly named level
  still wins (X3); the selection logic is observable (the announcement
  states what drove the choice).
- **Edges:** blocked-by: C2 (routes over the post-C2 ladder); blocks: C4.
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
  codex engine needed.
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
  "meaningful" is; later children re-litigate none of it.
- **X2 — headless invocability** (binds C3, C4). argus-review must be
  invocable non-interactively by a worker daemon (plugin installed in the
  worker harness, e.g. a `claude -p` slash invocation), producing the
  standard Findings/Verdict contract with no human present — which is why
  effort auto-routing (C3) precedes the engine swap (C4). C4 names the
  minimum argus version it requires.
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
  skill is less proven than driving a CLI binary. Mitigation: C4 is
  execplan-expected with a feasibility milestone first; if invocation
  can't meet the engine contract (compact findings file, bounded wait),
  the discovery flows back here before C5 dispatches.
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

| Child | Spec / ticket | Status |
|---|---|---|
| C1 | — | not-dispatched (dispatchable now) |
| C2 | — | not-dispatched (blocked-by C1) |
| C3 | — | not-dispatched (blocked-by C2) |
| C4 | — | not-dispatched (blocked-by C2, C3) |
| C5 | — | not-dispatched (blocked-by C4) |
| C6 | — | not-dispatched (dispatchable now) |

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
- **Built-in `/review`/`/code-review` prompt sources are on disk** (the
  codex_somersault checkout carries Claude Code source; `~/.claude/jobs/`
  carries command sources) — C1 needs no extraction work.

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION check:
verify Parent-Level Acceptance as written — all children landed is not the
same event — then retrospect.

## Revision Notes

—
