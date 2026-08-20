# Task Grain and Review Cadence — Design

The controlled track (doperpowers:writing-plans → doperpowers:subagent-driven-
execution) pays a fixed cost at every task boundary: a fresh executor orients
in the codebase, a fresh reviewer orients in the diff, any fixer orients
again, and the controller composes a dispatch, reads a report, adjudicates
⚠️ items, and writes the ledger. writing-plans' standing rule — "a task is the
smallest unit that carries its own test cycle and is worth a fresh reviewer's
gate" — maximizes the number of those boundaries. Telemetry over the last four
real runs (§3) shows where the time actually goes: reviewer time often equals
or exceeds executor time, fixer dispatches outnumber executors, and practice
has already drifted to fewer, larger tasks than the rule describes. This
design moves the doctrine to where practice is heading and removes two
structural repetitions of orientation — per-task review when nothing
downstream needs it yet, and fresh fixers where the executor that wrote the
code could simply continue.

After this lands one can observe: writing-plans sizes tasks by ownability and
interface frontiers, not minimality; subagent-driven-execution reviews at
dependency frontiers (batching sibling tasks, reviewers in parallel) and fixes
by resuming the executor; `scripts/sde-telemetry` prints per-role dispatch
counts, durations, and tokens for any session; and this spec carries the
four-run baseline and the monitoring protocol that decides whether the change
stands.

Human-confirmed frame (2026-08-21): scope = grain + cadence + fix-loop
resume; wave boundary = dependency frontier; per-task review depth unchanged
(reviewer's judgment); evidence path = adopt now, monitor the next features
with the collector; track = direct, with this spec as the durable record.
Plan resolution (No Placeholders, complete code in every step) and
single-executor sequential execution are untouched.

## §1 Task right-sizing (doperpowers:writing-plans)

The "Task Right-Sizing" section is replaced by the following text (the
human's wording; criteria, no calibration numbers — the reading model sizes
by judgment):

> A task is the unit one executor can reliably own from a single
> self-contained brief, but it isn't the smallest unit a reviewer could
> gate. Every task boundary costs a fresh worker's orientation (executor,
> reviewer, and any fixer each read in from zero) plus your own
> dispatch-and-adjudicate turn; draw the fewest boundaries that keep these
> true:
>
> - **Interface frontiers.** Anything a later task consumes must be
>   produced — and reviewed — before that task dispatches: keep producer
>   and consumer in one task, or put the contract at a task edge.
>   Interfaces internal to a task are free.
> - **Reviewable diff.** One reviewer reads one task's diff in a single
>   pass.
> - **Ownability.** One task holds one coherent verification strategy and
>   closely related state owners; its brief needs nothing from neighbors
>   beyond the declared Interfaces.
>
> Fold setup, configuration, scaffolding, and documentation into the task
> whose deliverable needs them. Inside a task, organize the work as
> sequential deliverables, each with its full step sequence and its own
> commit.

Supporting edits in the same skill:

- **Interfaces block names the producer.** In the Task Structure template,
  `Consumes:` entries name the task they come from ("from Task 2:
  `walk(cursor) -> list[dict]`"). This is the controller's source for the
  dependency frontier in §2 — the plan declares dependencies; the controller
  derives the review schedule at run time.
- The section "Bite-Sized Task Granularity" is retitled "Bite-Sized Steps"
  — its content is about steps (2–5 minutes each), and "task granularity"
  now means the opposite of bite-sized. The overview's "bite-sized tasks"
  becomes "tasks built from bite-sized steps". Step content is unchanged.
- The Execution Handoff line "Fresh subagent per task + two-stage review"
  becomes "Fresh executor per task; reviews at dependency frontiers; fixes
  resume the executor".

Unchanged, deliberately: Scope Check, Conditional Sub-Slicing (its "fewest
boundaries that make each important invariant independently understandable
and testable" already points the same way), File Structure, No Placeholders,
Spike Tasks, Final Verification Task, Self-Review.

## §2 Review cadence and fix loop (doperpowers:subagent-driven-execution)

**Review at the frontier.** A task is reviewed before any task that consumes
what it produced dispatches — the briefs' Interfaces name the producers.
Tasks nothing downstream consumes yet may keep executing and are reviewed
together when the frontier closes: the next task consumes from them, or the
plan ends. A wave review is one review package per task (`scripts/review-
package PLAN_FILE BASE HEAD`, each task's own BASE..HEAD as recorded before
its executor ran) and one task reviewer per task, dispatched in parallel —
reviews are read-only, so they cannot conflict. The frontier is the ceiling
on deferral, not the floor: a DONE_WITH_CONCERNS, a doubt of the controller's
own, or a first task whose brief style the executor may have misread are
reasons to review now.

Applied to the PR #74 plan (seven tasks: helper primitives; four sibling
migrations consuming them; legacy removal consuming all four; final
verification) the schedule is {1} | {2, 3, 4, 5} | {6} | {7}: four review
points instead of seven, the middle four reviewers concurrent. Applied to a
plan already cut coarse (PR #76, five tasks) it is {1} | {2, 3} | {4} | {5}
— small gain, because the grain already did the work.

**Fix by resuming the executor.** Critical/Important findings go back to the
executor that wrote the code — resume it (SendMessage to its agent handle)
with the findings; it already holds the task's context and skips the
orientation a fresh fixer pays. Several tasks with findings in one wave
resume one at a time (shared worktree). Re-review resumes the reviewer with
the fix commits' package; the loop repeats until both verdicts are clean. A
fresh fixer is dispatched only when the executor cannot be resumed (handle
lost, a harness without resume) or its fix has failed re-review twice — then
the executor's own frame is the problem. Minor findings still go to the
ledger for the final review's triage. The final-review fix wave is unchanged
(one fixer with the complete list).

**Ledger carries the handles.** The ledger records each task's executor and
reviewer agent handles beside its BASE, so a resume survives compaction — the
same reason the ledger, not the controller's memory, holds task completion.

**Model selection (text aligned to the standing directive).** Workers —
executors, task reviewers, fixers — run on opus at high reasoning effort;
the task grain above is calibrated to that tier. A simple task — a doc
update, a mechanical rename, a verification walk with every command given —
can go to sonnet. Workers never run on the top tier (fable): it adds cost
without reliability and is the controller's tier, not the worker's. With
opus the ceiling, a BLOCKED on reasoning capacity escalates into the brief,
not up the tier: the controller resolves the hard call and re-dispatches, or
splits the task. The two prompt templates' `[MODEL]` placeholders say the
same. The final whole-branch review keeps its own rule (codex native review;
a top-tier Claude reviewer if codex is unavailable).

Unchanged: one executor at a time in the shared worktree; executor and
reviewer prompt contracts; pre-flight; ⚠️ resolution by the controller;
dispatch hygiene; the final whole-branch review and its single fixer.

## §3 Telemetry, baseline, and the monitoring protocol

`scripts/sde-telemetry SESSION_JSONL [...]` (recovered from the closed PR
#72 branch, with the dispatch list sorted by start time and carrying the
model) prints, per session: wall-clock span, dispatch counts by role
(executor / task-reviewer / fixer / other, classified by dispatch
description), token totals by model for controller and workers, and the
dispatch list. Subagent transcripts are read from
`<transcript-dir>/<session-id>/subagents/`.

**Baseline** — the four controlled-track runs of 2026-08-18..20 (session
`e92c7422`, all workers opus; times are summed dispatch durations; run B's
reviewer time includes one review inflated to 3h47m by the 2026-08-18 opus
incident):

| Run | Tasks | Dispatches | Executor n / time | Reviewer n / time | Fixer n / time | Tasks needing a fix | Span (first executor → last task-level dispatch) |
|---|---|---|---|---|---|---|---|
| A arkho#11 read-surface | 11 | 37 | 11 / 1h50m | 10 / 3h39m | 16 / 2h18m | 9 of 10 | 9h50m (incl. PR-review fix waves) |
| B dp PR #74 paged-reads | 7 | 22 | 8 / 6h01m | 7 / 5h09m* | 6 / 1h21m | 2 of 7 | 8h13m |
| C arkho#17 search | 6 | 17 | 6 / 2h03m | 7 / 0h38m | 3 / 0h32m | 2 of 6 | 3h34m |
| D dp PR #76 client reads | 5 | 14 | 5 / 0h45m | 5 / 0h42m | 3 / 0h12m | 1 of 5 | 3h59m (1h33m to last task) |

Escaped defects at the final whole-branch gate: B — four P2 over four codex
rounds (all in the walk contract's fail-closed edges, i.e. cross-task); D —
none Critical/Important (two Minors); C — none (two API.md polish clauses).
Per-task reviews in B caught two Important findings, both vacuous-assertion /
undrilled-branch classes.

**Protocol.** After each of the next three controlled-track features
finishes, run the collector over that session, and append a row here (under
Surprises & Discoveries) with: tasks, dispatches by role, executor / reviewer
/ fixer time, tasks needing a fix, fix rounds per task, final-review
Critical+Important count, any executor BLOCKED citing task size. Reopen this
decision when any of these holds: two consecutive monitored features show
final-review Critical+Important above the baseline's worst (four); an
executor is BLOCKED citing task size; a task needs more than two fix rounds.
The instruction to run the collector lives here and in memory, not in skill
text — it is the monitoring window's, not the method's.

## §4 Out of scope (recorded so they are not re-derived)

- **Parallel executors** for independent tasks (worktree-isolated dispatch
  off the Interfaces DAG). The most direct wall-clock lever, but tasks in
  one plan routinely touch the same files (PR #74's Task-3→4 handoff on
  `test-read-verbs.sh`), so it needs its own merge design. Separate goal.
- **Plan resolution.** Opus executors could take brief-level plans, but the
  complete-code plan is the controlled track's stated advantage (frontier
  intelligence spent once, up front) and changing it with the grain would
  make any outcome unattributable.
- **Reviewer depth.** Reviewers' mutation batteries are expensive and have
  caught real vacuous-assertion classes; depth stays the reviewer's call.

## Acceptance

1. `skills/writing-plans/SKILL.md` carries the §1 text under "Task
   Right-Sizing"; `grep -c "smallest unit" skills/writing-plans/SKILL.md`
   prints `0`; the Task Structure `Consumes:` line names the producing task.
2. `skills/subagent-driven-execution/SKILL.md` states the frontier rule, the
   resume-based fix loop, the ledger handles, and the opus/sonnet/never-fable
   model text; both prompt templates' `[MODEL]` placeholders agree.
3. Wording sanity (doperpowers:writing-skills micro-test): a fresh opus
   subagent given the new writing-plans skill and the PR #74 spec
   (`docs/doperpowers/specs/2026-08-18-board-client-paged-reads-design.md`),
   asked only for the task breakdown with Interfaces, returns ≤ 6 tasks with
   every `Consumes` naming its producer in at least two of three reps; a
   control rep on the old text returns more tasks than the new reps' median
   (the shipped plan under the old text had seven).
4. A fresh opus subagent given the new subagent-driven-execution skill and
   the PR #74 plan (`docs/doperpowers/plans/2026-08-18-board-client-paged-
   reads.md`), asked for the review schedule, answers {1} | {2–5} | {6} |
   {7} (or a stricter schedule that reviews earlier) in at least two of
   three reps.
5. `scripts/sde-telemetry ~/.claude/projects/<dir>/<session>.jsonl` on
   session `e92c7422` prints `dispatches: 277 total` with executor/fixer/
   task-reviewer/other counts and a start-time-sorted dispatch list.
6. `tests/claude-code/run-skill-tests.sh --test test-subagent-driven-execution`
   passes; `scripts/bump-version.sh --check` reports the new version in sync.

## Decision Log

- Decision: adopt the doctrine change now and monitor, instead of the
  pre-registered paired double-run (PR #72, closed 2026-08-20 unmerged).
  Rationale: the human chose this path; double-implementing a feature is the
  costliest possible evidence; the four-run telemetry is a real baseline for
  the same metrics; the change is a text revert away; the §3 protocol
  reopens it on regression. This spec supersedes
  `2026-08-19-task-grain-experiment.md` (never merged), whose V1 treatment
  text seeded §1 and whose V2 (wave cadence) became §2.
  Date/Author: 2026-08-21 / fable session + human

- Decision: wave boundary = dependency frontier, over fixed batches (every
  2–3 tasks) and over end-only review.
  Rationale: fixed batches let a consumer build on an unreviewed interface
  (rework if the review fails); end-only moves the vacuous-assertion class
  per-task reviews have caught to the end, where fixes are largest. The
  frontier is the one boundary the plan already declares.
  Date/Author: 2026-08-21 / human

- Decision: per-task review depth unchanged — the reviewer judges how deep
  to go.
  Rationale: mutation batteries are where the reviewer time goes, and also
  where PR #74's two Important findings came from; "lighter per-task,
  heavier final" was considered and declined for now — revisit with
  monitoring data.
  Date/Author: 2026-08-21 / human

- Decision: fix by resuming the executor; fresh fixer only when resume is
  impossible or a fix has failed re-review twice.
  Rationale: fixer dispatches outnumber executors (70 vs 57 over the
  session; 16 vs 11 in run A) and every one re-orients; the executor holds
  the context; the reviewer's re-review — not the fixer's freshness — is
  the independence guard. Upstream's SDD resumes the implementer for rounds
  ≤ 3 (prior art). Two failed re-reviews is the observable signal that the
  executor's frame is the problem.
  Date/Author: 2026-08-21 / fable session

- Decision: the right-sizing text carries criteria only — no diff-line cap,
  no target task count.
  Rationale: the human's call: the reading model sizes by judgment; numbers
  become gates. The author's expectations (roughly ≤ 500 changed lines per
  task; a feature the old rule cut into 8–12 tasks landing around 3–6) are
  recorded here for the monitoring readout, not in the skill.
  Date/Author: 2026-08-21 / human

- Decision: worker model text = opus/high default, sonnet for simple tasks,
  never fable; reasoning-capacity BLOCKED escalates into the brief or a
  split, not up the tier.
  Rationale: the skill still said sonnet while every session overrode it to
  opus by standing directive (2026-08-04, corrected 2026-08-19: fable
  workers are not an acceptable fallback even as an upgrade); the grain is
  calibrated to the worker tier, so the text must name it. With opus the
  ceiling, "stronger model" had nowhere to go.
  Date/Author: 2026-08-21 / human

- Decision: the plan declares dependencies (Consumes names the producer);
  the controller derives waves at run time — over plan-declared waves.
  Rationale: run-time signals (DONE_WITH_CONCERNS, a controller doubt) can
  close a wave early; the plan author cannot foresee them.
  Date/Author: 2026-08-21 / fable session

- Decision: one reviewer per task within a wave, in parallel — over one
  reviewer for the whole wave diff.
  Rationale: per-task packages already exist and keep each review within
  one pass; cross-task interplay is the final whole-branch review's job
  today and stays there.
  Date/Author: 2026-08-21 / fable session

- Decision: parallel executors and plan resolution out of scope (§4).
  Rationale: separate designs; bundling them would make the grain outcome
  unattributable.
  Date/Author: 2026-08-21 / human

- Decision: direct track with a spec (no plan, no SDE), telemetry
  instruction in spec + memory rather than skill text.
  Rationale: ~150 lines of doctrine prose — a plan would be the diff
  itself; the spec is needed as the durable home of the baseline and the
  monitoring protocol; the collector instruction is the monitoring window's.
  Date/Author: 2026-08-21 / human

## Surprises & Discoveries

- Observation: across the four runs reviewer time equals or exceeds executor
  time in two (A: 3h39m vs 1h50m; D: 42m vs 45m) — reviewers run mutation
  batteries, 20–40 minutes and 50–77k output tokens per review in run A.
  Evidence: `scripts/sde-telemetry` + per-dispatch durations, session
  `e92c7422`, computed 2026-08-21.
- Observation: fixer dispatches outnumber executors (session-wide 70 vs 57;
  run A 16 vs 11); each fixer is a fresh dispatch paying orientation again.
  Evidence: same.
- Observation: practice had drifted coarse before the doctrine moved — July
  plans carried 8–17 tasks, the four August runs 11/7/6/5; the coarsest
  (PR #76, 300- and 276-line briefs) was the fastest to last task (1h33m)
  with the lowest fix rate (1 of 5). n=1, directional.
  Evidence: `docs/doperpowers/plans/*.md` task counts; telemetry.
- Observation: in PR #74 the per-task gate's catches were test-quality
  classes (vacuous drill, undrilled branch); the four correctness holes were
  cross-task walk-contract edges, all found by the final codex review. The
  per-task gate's unique value is early, local; correctness across tasks is
  the final gate's.
  Evidence: `.doperpowers/sde/2026-08-18-board-client-paged-reads/progress.md`.
- Observation: the controller's own output (7.0M tokens, fable) is of the
  same order as all workers combined (8.8M) over the session — the
  "frontier plans once, cheap executes" picture does not hold; every task
  costs controller turns, so fewer tasks cut controller cost too.
  Evidence: telemetry token totals.
- Observation: PR #72's recommended feature (arkho#9 paged envelope) had
  already shipped in arkho PR #11 on 2026-08-18, the day before the spec was
  written — the experiment's target was stale at birth.
  Evidence: memory `read-surface-epic-shipped`; arkho#11 merge 591ba00.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1 (2026-08-21): initial design, approved in session (direct track with
  spec); §1 text is the human's wording.
