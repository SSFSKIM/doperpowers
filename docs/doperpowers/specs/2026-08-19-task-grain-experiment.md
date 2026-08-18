# Task-Grain Experiment — controlled track, paired double-run

**Purpose.** The controlled track defines a task as the *smallest* unit worth a
fresh reviewer's gate (doperpowers:writing-plans, "Task Right-Sizing"). A
mid-size feature therefore cuts into 8–12 tasks, and the pipeline pays its
dominant fixed cost — worker re-orientation (executor reads brief and orients
in the codebase; reviewer orients in the diff; fixers re-orient again) — 20–30
times per feature. If a mid-tier executor can reliably own larger units, the
same feature ships with materially fewer dispatches and less wall-clock at
equal quality. Changing Task Right-Sizing is a behavior-shaping skill change;
this repo's own bar ("Skill Changes Require Evaluation") demands eval evidence
first. This experiment produces that evidence.

After this experiment one can observe: a metrics table comparing two complete
implementations of the same real feature — one under current doctrine, one
under a coarse-grain variant — a blinded comparative review verdict, and a
recorded adopt / reject / iterate decision in this spec's Decision Log.

## Hypotheses

- **H1 (grain).** Tasks sized as "the largest unit a mid-tier executor
  reliably owns from one self-contained brief" preserve quality — no increase
  in escaped defects, no executor-reliability red flags — while cutting total
  dispatches and wall-clock substantially (expectation: ≥25%).
- **H2 (cadence, contingent).** If H1 fails specifically on *executor*
  reliability, batching reviews into dependency-frontier waves at the current
  fine grain captures most of the review-count savings without enlarging the
  executor's unit. H2 is not run in this experiment; it becomes the follow-up
  treatment only if H1 fails that way.

## Arms

**Arm B (baseline).** Current doctrine verbatim: doperpowers:writing-plans →
doperpowers:subagent-driven-execution, untouched.

**Arm V1 (coarse grain).** Identical doctrine with exactly one substitution:
the treatment text below replaces writing-plans' "Task Right-Sizing" section.
Everything else applies unchanged — No Placeholders (complete code in every
step), Interfaces blocks, bite-sized steps *inside* a task, codex adversarial
plan review, SDE's per-task two-stage review, and the final whole-branch codex
review. Worker model is held identical in both arms at current practice —
opus for executors/reviewers/fixers, per the standing human directive that
overrides the skill's sonnet default. This keeps the manipulation single-variable: only
the partitioning of the same plan content changes, so an outcome difference is
attributable to task grain, not to plan resolution or review machinery.

### V1 treatment text (copied verbatim into the variant session's instructions)

> **Task Right-Sizing (coarse-grain variant).** A task is the **largest** unit
> a mid-tier executor can reliably own from one self-contained brief — not the
> smallest reviewable one. Draw boundaries by:
>
> - **Interface frontiers.** Any interface consumed by a *different* task must
>   be produced — and therefore reviewed — before the consuming task
>   dispatches: place produced-then-consumed contracts at task edges, or keep
>   producer and consumer inside the same task. Within-task interfaces are
>   free.
> - **Reviewable diff.** Expected diff stays under ~500 changed lines per
>   task; past that, single-pass review reliability drops — split.
> - **Ownability.** Everything in one task fits one executor's working
>   context: closely related state owners, one coherent verification strategy,
>   a brief needing nothing from neighbors beyond its declared Interfaces.
> - **Target.** Where the fine-grained doctrine would produce 8–12 tasks, aim
>   for 3–5. Inside a task, organize the work as sequential deliverables, each
>   keeping its full TDD step sequence (failing test → verify fail → implement
>   → verify pass → commit).

Note the first-task calibration gate is automatic in V1: per-task review is
retained, so the first (larger) task is still fully reviewed before the second
dispatches — if the executor systematically misreads the coarser brief, it
surfaces at task 1.

## Feature under test

**Recommended: arkho#9** — paged envelope for `/queue/decisions` and
`/tickets` (currently read whole; contract pin filed during A2). Why it fits:

- Mid-size: estimated 8–10 tasks under current doctrine (envelope schema,
  cursor semantics, two endpoints, ordering/limit guarantees, tests, spec
  update, final verification) — squarely in the regime where SDE overhead
  bites.
- Real backlog value: natural follow-on to the just-shipped read-surface epic;
  the winning branch merges and ships.
- Pure server-side code with a real test suite (281 green) — behavior-testable,
  no live side effects until merge (only the winner merges; merge = Render
  deploy).
- Delegable: contract work whose ambiguity a grill can exhaust up front.

Alternates considered and rejected: arkho A3 mirror writers (too big for a
first paired run; external GitHub side effects), dp#63 board-transition guard
(too small; shell-heavy, weak fit for TDD-pipeline metrics).

## Protocol

**Phase 0 — setup (after human go).** Confirm the feature. Run the standard
grill + brainstorming once and write the feature spec (in the arkho repo, per
its conventions); freeze it at a commit. Create two arkho worktrees from the
same base commit, branches `pe-x` and `pe-y` (arm-neutral names). Extract the
V1 treatment text into an instruction file for the variant session.

**Phase 1 — plan + execute, in parallel.** One fresh session per arm; each
session authors its plan from the frozen spec and runs SDE to completion in
its own worktree, including the codex adversarial plan review and the final
whole-branch codex review (same model and effort settings in both arms).
Neither session is told another arm exists; neither reads the other's worktree
or branch. Record each arm's session ID(s) for telemetry.

**Phase 2 — measure.** Run `scripts/sde-telemetry` over both arms' session
transcripts. Tally review findings, fix loops, ⚠️ items, and executor statuses
from each arm's SDE workspace (ledger, reports). Collect both final-review
finding lists.

**Phase 3 — blinded comparative judgment.** A fresh frontier judge receives
the frozen feature spec plus two *squashed* diffs labeled X and Y (no commit
history — commit granularity leaks arm identity; no mention of the experiment
or of task counts). It returns, per branch: defects found (with severity), and
which branch better satisfies the spec, with reasoning.

**Phase 4 — decide and merge.** Apply the decision rule below; record the
outcome in this spec's Decision Log. The human merges the winning branch;
the losing branch is tagged and preserved for audit, not deleted.

## Metrics (pre-registered)

| Metric | Source |
|---|---|
| Active time (primary): sum of dispatch durations + controller turn time; span (secondary — includes idle gaps) | transcript timestamps (phase boundary = first executor dispatch) |
| Dispatches by role: executor / task-reviewer / fixer | `subagents/*.meta.json` descriptions |
| Tokens by model, controller vs workers | `usage` sums over main + subagent transcripts |
| Review findings by severity, per review | reviewer reports in the SDE workspace |
| Fix-loop iterations per task | ledger + fix reports |
| ⚠️ (cannot-verify-from-diff) items and their resolution cost | reviewer reports |
| Executor statuses (DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT), model escalations | executor reports |
| Escaped defects: final whole-branch codex findings, severity-weighted | final review output |
| Comparative verdict | blinded judge (Phase 3) |
| Acceptance: feature spec's acceptance section passes | both branches; a failing branch = arm failure |

## Decision rule (pre-registered, before any run)

Adopt V1 — rewrite writing-plans' Task Right-Sizing, citing this spec as the
eval evidence — only if **all** hold:

1. **Quality non-inferior.** V1's escaped defects (Critical + Important, final
   review ∪ blinded judge) ≤ Arm B's, and the judge attributes no V1 defect
   class to under-review of oversized diffs.
2. **Cost materially better.** ≥25% reduction in total wall-clock **or** total
   tokens (expectation: both), with dispatch count reduced roughly in
   proportion to task count.
3. **Executor reliability holds.** No BLOCKED-on-reasoning-capacity
   escalation; no task exceeding 2 fix-loop iterations.

Failure routing:

- Rule 3 fails → H2 follow-up: wave-cadence variant (V2) at current grain, on
  the next comparable feature.
- Rule 1 fails via review-side misses (task reviewer missing what the final
  review catches on large diffs) → retry V1 with the diff cap tightened to
  ~300 lines, or fall back to V2.
- Ambiguous margins → one more paired feature before touching doctrine.

**n=1 honesty.** The paired design controls the dominant confound (feature
difficulty) but not run-to-run variance; a single pair is directional
evidence, not proof. Adoption is therefore adopt-with-monitoring: the next
2–3 controlled-track features run the collector as standing telemetry, and a
quality regression reopens this decision.

## Confounds and mitigations

- **Feature difficulty** — controlled by the paired same-feature design.
- **Contamination** — fresh sessions per arm, parallel execution, no
  cross-reads, isolated worktrees, shared frozen spec.
- **Judge bias** — blinding via squashed arm-neutral diffs; the judge never
  learns the hypothesis.
- **Reviewer variance at the exit gate** — same codex model/effort for both
  final reviews.
- **Plan-author variance** — same model, same spec; irreducible at n=1, noted.

## Acceptance

- `scripts/sde-telemetry <arm-B-session-jsonl> <arm-V1-session-jsonl>` prints,
  for each session: wall-clock span, dispatch counts by role, and token totals
  by model for controller and subagents. (Runnable today against any past
  session transcript; verified against a real session during design.)
- Both arkho branches pass the feature spec's acceptance section as written.
- This spec's living tail contains the filled metrics table, the judge's
  verdict, and a Decision Log entry recording adopt / reject / iterate.

## Decision Log

- Decision: paired same-feature double-run, over historical-baseline
  comparison and synthetic eval-harness runs.
  Rationale: historical baselines are confounded by feature difficulty — the
  dominant variance source; the evals/ harness measures skill compliance, not
  pipeline economics. Double-implementation cost accepted and bounded by
  choosing a mid-size feature whose winner ships.
  Date/Author: 2026-08-19 / fable session

- Decision: single-variable treatment — only task partitioning changes; plan
  resolution (No Placeholders) and the SDE review loop stay untouched.
  Rationale: bundling coarse grain with wave review or lower plan resolution
  would make failure unattributable. Plan-resolution relaxation is a separate,
  deeper question deferred until grain results exist.
  Date/Author: 2026-08-19 / fable session

- Decision: V2 (wave cadence at fine grain) held as a contingent follow-up,
  not a third arm.
  Rationale: a 3-arm run costs 3× one feature; V1 already subsumes the
  review-count economics (fewer tasks ⇒ fewer reviews), so V2 is informative
  only if V1 fails on the executor side.
  Date/Author: 2026-08-19 / fable session

- Decision: blinded comparative judge reads squashed diffs only.
  Rationale: commit granularity reveals task structure and hence arm identity;
  an unblinded judge can pattern-match "more tasks = more rigor."
  Date/Author: 2026-08-19 / fable session

- Decision: feature = arkho#9 (paged envelope), pending human confirmation.
  Rationale: mid-size, real backlog, pure server code with a real suite, no
  side effects until merge. A3 (too big, external side effects) and dp#63
  (too small, shell-heavy) rejected.
  Date/Author: 2026-08-19 / fable session

- Decision: decision rule pre-registered before any run.
  Rationale: prevents post-hoc rationalization of whichever arm feels better.
  Date/Author: 2026-08-19 / fable session

## Surprises & Discoveries

- Observation: per-dispatch telemetry is fully recoverable post-hoc — each
  subagent leaves `subagents/agent-*.jsonl` (per-message `usage` + `model` +
  `timestamp`) beside a `.meta.json` carrying the dispatch description, so
  dispatches classify into executor/reviewer/fixer by description string with
  exact token attribution.
  Evidence: probe on session `0c5f5b2b` (2026-08-19): one dispatch, 10 usage
  turns, model claude-opus-5, 9,249 output tokens attributed.

- Observation: in a real 8-task SDE run (session `b380b6da`, 2026-08-01..05),
  fixer dispatches (11) outnumbered executor dispatches (8) — the review-fix
  loop, not execution, was the larger dispatch-count center, supporting the
  re-orientation-overhead premise. Workers ran on opus, confirming practice
  diverges from the skill's sonnet default.
  Evidence: `scripts/sde-telemetry` output, 2026-08-19: 37 dispatches =
  8 executor / 8 task-reviewer / 11 fixer / 10 other (a parallel panel wave).

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-08-19: Initial version — arms, treatment text, protocol, pre-registered
  metrics and decision rule.
