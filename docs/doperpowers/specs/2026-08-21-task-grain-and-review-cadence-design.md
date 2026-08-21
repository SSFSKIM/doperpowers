# Task Grain and Review Cadence — Design

The controlled track (doperpowers:writing-plans → doperpowers:subagent-driven-
execution) pays a fixed cost at every task boundary: a fresh executor orients
in the codebase, a fresh reviewer orients in the diff, any fixer orients
again, and the controller composes a dispatch, reads a report, adjudicates
⚠️ items, and writes the ledger. writing-plans' standing rule — "a task is the
smallest unit that carries its own test cycle and is worth a fresh reviewer's
gate" — maximizes the number of those boundaries. Telemetry over the last four
real runs (§3) shows where the time actually goes: reviewer time often equals
or exceeds executor time, fixer dispatches are of the same order as
executor dispatches — each a fresh orientation — and practice has already
drifted to fewer, larger tasks than the rule describes. This
design moves the doctrine to where practice is heading and removes two
structural repetitions of orientation — per-task review when nothing
downstream needs it yet, and fresh fixers where the executor that wrote the
code could simply continue.

After this lands one can observe: writing-plans sizes tasks by ownability and
interface frontiers, not minimality; subagent-driven-execution reviews at
dependency frontiers (batching sibling tasks, reviewers concurrent) and fixes
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

On the direct track this spec is the only record of the wording: §1 and §2
quote the skill-bound text verbatim; commentary sits outside the quotes.

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

Supporting edits in the same skill, each quoted as it lands:

- Task Structure template, `Consumes:` line — the controller's source for
  the dependency frontier in §2 (the plan declares dependencies; the
  controller derives the review schedule at run time):

  > - Consumes: [what this task uses from earlier tasks, naming the task —
  >   "from Task 2: `walk(cursor) -> list[dict]`" — exact signatures. The
  >   controller schedules reviews from these: a producer is reviewed before
  >   its consumer dispatches.]

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

The loop's steps 3–5 become:

> 3. **Per task, in plan order:** extract the brief (`scripts/task-brief
>    PLAN_FILE N`), record BASE (the current commit), dispatch the executor
>    ([executor-prompt.md](executor-prompt.md)) and write the task's
>    `executed` ledger line with its agent handle (Durable Progress below)
>    — fixes resume it. Answer its questions before it proceeds. One
>    executor at a time — parallel executors conflict in a shared worktree.
> 4. **Review at the frontier:** a task is reviewed clean — findings fixed
>    and re-reviewed — before any task that consumes what it produced
>    dispatches; the briefs' Interfaces name the producers, and the plan's
>    final verification task consumes the whole branch. Tasks nothing
>    downstream consumes yet may keep executing and are reviewed together
>    when the frontier closes (the next task consumes from them, or the
>    plan ends): one review package per task (`scripts/review-package
>    PLAN_FILE BASE HEAD`, each task's own BASE..HEAD), one task reviewer
>    per task ([task-reviewer-prompt.md](task-reviewer-prompt.md)) with the
>    printed path, dispatched together when their focused tests cannot
>    collide — reviews read their package, not the tree, so hermetic suites
>    run concurrently; suites that share mutable state — a test database, a
>    fixed port — run one reviewer at a time.
>    Where no interface is declared but two tasks touch the same files,
>    judge from their Files lists: an overlap that looks load-bearing is
>    reviewed before the later task dispatches. The frontier is the ceiling
>    on deferral, not the floor: a DONE_WITH_CONCERNS, a doubt of your own,
>    or a first task whose brief style the executor may have misread are
>    reasons to review that task now.
>    A deferred review reads a tree that has moved past its package —
>    Task 1's package is BASE1..HEAD1 while the checkout sits at the
>    wave's last HEAD. Name the current HEAD and what landed since the
>    task's own HEAD (the sibling commits and files) in the dispatch, so
>    a sibling's effect is not read as this task's; a check that must see
>    the task's own tree — a focused test, a named risk — runs in a
>    detached worktree at the packaged HEAD (`git worktree add --detach
>    <workspace>/review-N <HEAD_N>`, removed after the review) rather
>    than in the shared checkout.
> 5. **Findings:** Critical/Important findings go back to the executor that
>    wrote the code — resume it with the findings; it holds the task's
>    context and skips the orientation a fresh fixer pays. Several tasks
>    with findings in one wave resume one at a time (shared worktree).
>    Re-review by resuming the reviewer with the fix commits' package
>    (`scripts/review-package PLAN_FILE FIX_BASE FIX_HEAD` — the fix range:
>    the reviewer already holds the task's original package, and a deferred
>    task's fix lands past its siblings' commits); repeat until both
>    verdicts are clean. That message names the fix range, sends the
>    reviewer back to the report (the executor appended the fix's test
>    evidence there), and carries the refreshed checkout head and what
>    landed since — plus a fresh detached worktree at the fix head if the
>    review needs the task's own tree. A resumed reviewer otherwise judges
>    the fix against its pre-fix memory. A fresh fixer when the executor
>    cannot be resumed, or when its frame is the problem — two failed
>    re-reviews is the usual sign. Record Minor findings in the ledger —
>    the final review triages that list, so it is read, not discarded. Fix
>    through a worker, not your own edits: manual fixes pollute your
>    context and skip review.

The skill's opening sentence says "a task review (spec compliance + code
quality) at each dependency frontier". Worked schedules (commentary, not
skill text): the PR #74 plan — helper primitives; four sibling migrations
consuming them; legacy removal consuming all four; final verification — gives
{1} | {2, 3, 4, 5} | {6} | {7}: four review points instead of seven, the
middle four reviewers concurrent; Tasks 3 and 4 share `test-read-verbs.sh`
without a declared interface, which is exactly the Files-list judgment call
the rule names. The PR #76 plan is a chain — Task 3 consumes Task 2's test
scaffolding, Task 4 consumes both — so its schedule is per-task: the rule
reproduces today's cadence where the plan gives it no siblings.

**Model selection**, first paragraph:

> Dispatch workers — executors, task reviewers, fixers — on opus at high
> reasoning effort; the task grain is calibrated to that tier. A simple
> task — a doc update, a mechanical rename, a verification walk with every
> command given — can go to sonnet. Never dispatch workers on the top tier
> (fable): it adds cost without adding reliability and is the controller's
> tier, not the worker's — the plan and the brief absorb the difficulty,
> not the model. When a worker reports BLOCKED on reasoning capacity rather
> than missing context, a sonnet task moves to opus; from opus there is no
> tier above — the difficulty moves into the brief: resolve the hard call
> yourself and re-dispatch, or split the task.

The final-whole-branch-review paragraph and "name the model in every
dispatch" are unchanged. Executor statuses, DONE — the old "review package
→ task reviewer" contradicted step 4's deferral: "**DONE** → review at the
frontier (step 4): package and reviewer now when something downstream
consumes the task or an early-review reason applies, otherwise it waits for
the wave." BLOCKED: "reasoning capacity (sonnet → opus; from opus,
resolve the hard call in the brief)". The two
prompt templates' `[MODEL]` placeholders read "opus at high reasoning effort
per SKILL.md Model Selection (sonnet for a simple task; never the top tier)";
executor-prompt.md's escalation sentence becomes "The controller can provide
more context, resolve the hard call in your brief, move the task to a
stronger worker tier where one exists, or break the task into smaller
pieces."

**task-reviewer-prompt.md**, Diff Under Review: `[HEAD_SHA]` is documented
as "the task's last commit — the package's head", and an optional line
follows **Head:** in the block —

>     **Checkout:** [CHECKOUT_SHA] — the shared tree sits here, past this
>     task's head; landed since: [SINCE]

— filled for a deferred review with the sibling commits and files that
landed since the packaged head, and omitted when the checkout is at
`[HEAD_SHA]`. The fallback `git diff [BASE_SHA]..[HEAD_SHA]` stays: it is
task-scoped. One added sentence tells the reviewer that a check which must
see the task's own tree runs in the detached worktree the controller names
(step 4), not in this moved-on checkout.

**Dispatch hygiene**, the fix-message bullet:

> - Fix messages — to a resumed executor or a fresh fixer — carry the
>   executor contract: re-run the covering tests (name them — a one-line
>   fix doesn't need the whole suite), report the command and output;
>   confirm all three are in the fix report before re-review. A resumed
>   executor's view of the tree ends at its own HEAD: name what landed
>   since (commits and files) and have it re-read before editing; its
>   covering tests include sibling suites touching the same files.

Two more hygiene bullets change — what a deferred review's dispatch carries,
and the range a re-review's package spans:

> - The task reviewer gets three paths — brief, report, review package — plus
>   the plan's binding constraints copied verbatim (exact values, formats,
>   stated relationships) and, for a deferred review, the checkout head and
>   what landed since (the template's Checkout line). Its template already
>   carries the process rules.
> - `review-package` BASE is the commit you recorded before dispatching the
>   executor — never `HEAD~1`, which silently drops all but the last
>   commit of a multi-commit task. A re-review's BASE is the ledger's
>   `fix-base` — the HEAD when the fix dispatched — so the package is the
>   fix alone.

**Durable progress** — with frontier review, several tasks can be executed
but unreviewed at once, and the old resume rule ("resume at the first task
without a `complete` line") would re-execute them after compaction — the
skill's own named most-expensive failure. The ledger bullets become:

> - The ledger lives at `<workspace>/progress.md`, first line
>   `# SDE ledger — plan: <plan file path>`. If that line names your plan,
>   tasks with a `Task <N>: complete` line are done; a task with an
>   `executed` line but no `complete` line is awaiting review or fixes —
>   resume its review (or its handles), never re-execute it; resume
>   executing at the first task with neither. A ledger naming a different
>   plan file is another plan's progress: leave it, start your own.
> - At dispatch, append `Task N: executed (base <sha7>, executor
>   <handle>)`; add `head <sha7>` when the executor returns and
>   `reviewer <handle>` when the review dispatches — a fix resumes those
>   handles, and after compaction the ledger is the only place they
>   survive. When a fix dispatches append `fix-base <sha7>` (the HEAD at
>   that moment) and `fix-head <sha7>` when it lands: a deferred task's
>   fix commits sit past its siblings', so `base..head` no longer bounds
>   the task's history.
> - When a task's review comes back clean, append `Task N: complete
>   (commits <base7>..<head7>[, fix <base7>..<head7>], review clean)`.

Unchanged: pre-flight; ⚠️ resolution by the controller; the remaining
dispatch hygiene bullets (including the final-review fix wave's single
fixer); the reviewer prompt's rubric, tests rule, and output format; the
final whole-branch review; Integration.

## §3 Telemetry, baseline, and the monitoring protocol

`scripts/sde-telemetry SESSION_JSONL [...]` (recovered from the closed PR
#72 branch, with the dispatch list sorted by start time and carrying the
model) prints, per session: wall-clock span, dispatch counts by role
(executor / task-reviewer / fixer / other, classified by dispatch
description), token totals by model for controller and workers, and the
dispatch list. Subagent transcripts are read from
`<transcript-dir>/<session-id>/subagents/`.

**Baseline** — the four controlled-track runs of 2026-08-18..20 (session
`e92c7422`, all workers opus; times are summed dispatch spans, with active time — idle gaps over 15 minutes excluded, the measure monitoring rows compare against — in parentheses; run B's
reviewer time includes one review inflated to 3h47m by the 2026-08-18 opus
incident):

| Run | Tasks | Dispatches | Executor n / span (active) | Reviewer n / span (active) | Fixer n / span (active) | Tasks needing a fix | Span (first executor → last task-level dispatch) |
|---|---|---|---|---|---|---|---|
| A arkho#11 read-surface | 11 | 37 | 11 / 1h49m (1h49m active) | 10 / 3h39m (3h15m active) | 14 / 2h05m (2h05m active) | 9 of 10 | 9h50m (incl. PR-review fix waves) |
| B dp PR #74 paged-reads | 7 | 22 | 8 / 6h00m (3h29m active) | 7 / 5h08m (2h04m active)* | 5 / 1h14m (1h14m active) | 2 of 7 | 8h13m |
| C arkho#17 search | 6 | 17 | 6 / 2h02m (2h02m active) | 7 / 0h38m (0h38m active) | 2 / 0h30m (0h30m active) | 2 of 6 | 3h34m |
| D dp PR #76 client reads | 5 | 14 | 5 / 0h44m (0h44m active) | 5 / 0h42m (0h42m active) | 2 / 0h11m (0h11m active) | 1 of 5 | 3h59m (1h33m to last task) |

The collector reports both span and active time per dispatch and per role
— active excludes idle gaps over 15 minutes, so a resumed agent's waiting
does not count — and deduplicates token totals by message id; the table
carries both measures, active in parentheses.

Fix rounds per task never exceeded two in the baseline (run A's tasks 2 and
8 took two fixers each; every other fixed task took one). Escaped defects at
the final whole-branch gate, where codex's P1 maps to Critical and P2 to
Important: B — four P2 over four codex rounds (all in the walk contract's
fail-closed edges, i.e. cross-task); D — none Critical/Important (two
Minors); C — none (two API.md polish clauses). Per-task reviews in B caught
two Important findings, both vacuous-assertion / undrilled-branch classes.

**Protocol.** After each of the next three controlled-track features
finishes, run the collector over that session and append a row here (under
Surprises & Discoveries) with: tasks, dispatches by role, executor / reviewer
/ fixer time, tasks needing a fix, fix rounds per task, final-review
Critical+Important count, any executor BLOCKED citing task size. Reopen this
decision when any of these holds: two consecutive monitored features show
final-review Critical+Important above the baseline's worst (four); an
executor is BLOCKED citing task size; a task needs more than two fix rounds
(above the baseline maximum — the fresh-fixer fallback firing is itself the
signal). The instruction to run the collector lives here and in memory, not
in skill text — it is the monitoring window's, not the method's.

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
   Right-Sizing"; `grep -c "smallest unit that carries its own test cycle"
   skills/writing-plans/SKILL.md` prints `0` and `grep -c "isn't the
   smallest unit" skills/writing-plans/SKILL.md` prints `1`; the Task
   Structure `Consumes:` line names the producing task.
2. `skills/subagent-driven-execution/SKILL.md` carries the §2 text (loop
   steps 3–5, model selection, the DONE status line, the fix-message and
   two changed hygiene bullets, the three ledger bullets);
   task-reviewer-prompt.md carries the Checkout line and its placeholder
   docs; both prompt templates' `[MODEL]` placeholders and
   executor-prompt.md's escalation sentence read as §2 states.
3. Wording smoke check (doperpowers:writing-skills micro-test, three reps —
   a smoke check on the wording's binding effect, not the eval; the eval is
   §3's monitoring): a fresh opus subagent given the new writing-plans
   skill and the PR #74 spec
   (`docs/doperpowers/specs/2026-08-18-board-client-paged-reads-design.md`)
   against a checkout at the spec's fork point (64967f79), asked only for
   the task breakdown with Interfaces, returns a breakdown in which every
   `Consumes` from an earlier task names its producer, in all three reps;
   the reps' median task count is no higher than a control rep on the old
   text (same spec, same checkout).
4. A fresh opus subagent given the new subagent-driven-execution skill and
   the PR #74 plan (`docs/doperpowers/plans/2026-08-18-board-client-paged-
   reads.md`), asked for its review schedule before dispatching anything,
   answers a frontier schedule — Task 1 alone, Task 7 alone, the four
   migrations batched ({2,3,4,5}) or split only at the Task 3→4
   `test-read-verbs.sh` overlap it names as load-bearing ({2,3} | {4,5}) —
   with concurrent reviewers inside each multi-task set, in at least two of
   three reps; inferring the producers from the briefs where that plan's
   older Interfaces blocks do not name them (the inference is intended; the
   old skill text reviews after every task by construction, so no control
   rep is needed). Asked what it appends to the ledger at dispatch and what
   it does after compaction with `executed`-but-not-`complete` tasks, it
   writes the `executed` line and does not re-execute them.
5. `scripts/sde-telemetry ~/.claude/projects/<dir>/e92c7422-….jsonl` prints
   `dispatches: N total` with N ≥ 277 (the session is still live), the
   four role counts summing to N, and a dispatch list in start-time order.
6. `tests/claude-code/run-skill-tests.sh --test
   test-subagent-driven-execution.sh` passes with `claude` shimmed to
   `--plugin-dir <this worktree>` so the keyword test reads the edited
   skill, not the installed plugin; `scripts/bump-version.sh --check`
   reports the new version in sync.

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

- Decision: undeclared dependencies — shared files without an interface —
  are the controller's call from the Files lists, reviewing the earlier
  task first when the overlap looks load-bearing; the ceiling clause
  ("review that task now") covers the rest. Residual exposure accepted: a
  sibling fix landing after a later sibling executed on the same file.
  Rationale: the independent review showed both worked examples carry this
  case (PR #74 Tasks 3→4; PR #76 Tasks 2→3); in the schedule micro-test,
  reps flagged the PR #74 overlap unprompted and resolved it the same way.
  Date/Author: 2026-08-21 / fable session (review finding adopted)

- Decision: per-task review depth unchanged — the reviewer judges how deep
  to go.
  Rationale: mutation batteries are where the reviewer time goes, and also
  where PR #74's two Important findings came from; "lighter per-task,
  heavier final" was considered and declined for now — revisit with
  monitoring data.
  Date/Author: 2026-08-21 / human

- Decision: fix by resuming the executor by default; a fresh fixer when
  resume is impossible or the executor's frame is the problem (two failed
  re-reviews the usual sign) — phrased as a default with its reason, not a
  gate.
  Rationale: fixer dispatches are of the same order as executors (70 to 92
  over the session; 13 to 11 in run A) and every one re-orients; the
  executor holds the context; the reviewer's re-review — not the fixer's
  freshness — is the independence guard. Upstream's SDD resumes the
  implementer for rounds ≤ 3 (prior art). The resume message names what
  landed since the executor's HEAD, because its context predates its
  siblings' commits.
  Date/Author: 2026-08-21 / fable session

- Decision: the ledger gains an `executed` line at dispatch (base, executor
  handle; head and reviewer handle added as they arrive), and the resume
  rule distinguishes executed-awaiting-review from not-started.
  Rationale: frontier review leaves several tasks executed-but-unreviewed;
  the old rule would re-execute them after compaction — the failure the
  section exists to prevent. Handles in the ledger are what make resume
  survive compaction at all.
  Date/Author: 2026-08-21 / fable session (review finding adopted)

- Decision: the right-sizing text carries criteria only — no diff-line cap,
  no target task count.
  Rationale: the human's call: the reading model sizes by judgment; numbers
  become gates. The author's expectations (roughly ≤ 500 changed lines per
  task; a feature the old rule cut into 8–12 tasks landing around 3–6) are
  recorded here for the monitoring readout, not in the skill. The smoke
  check (Surprises) read out 6–7 tasks against a control of 8 on the same
  spec — a modest shift, consistent with judgment rather than a cap.
  Date/Author: 2026-08-21 / human

- Decision: worker model text = opus/high default, sonnet for simple tasks,
  never fable; reasoning-capacity BLOCKED escalates sonnet → opus, and from
  opus into the brief or a split, not up the tier.
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

- Decision: one reviewer per task within a wave, concurrent — over one
  reviewer for the whole wave diff.
  Rationale: per-task packages already exist and keep each review within
  one pass; cross-task interplay is the final whole-branch review's job
  today and stays there. Reviews read the package, not the tree, so
  concurrency in a shared worktree is safe as long as their focused tests
  are hermetic; suites that share mutable state — a test database, a fixed
  port — run one reviewer at a time.
  Date/Author: 2026-08-21 / fable session

- Decision: parallel executors and plan resolution out of scope (§4).
  Rationale: separate designs; bundling them would make the grain outcome
  unattributable.
  Date/Author: 2026-08-21 / human

- Decision: direct track with a spec (no plan, no SDE), telemetry
  instruction in spec + memory rather than skill text; the spec quotes the
  skill-bound text verbatim.
  Rationale: ~150 lines of doctrine prose — a plan would be the diff
  itself; the spec is needed as the durable home of the baseline and the
  monitoring protocol; on a direct track it is also the only record of the
  wording; the collector instruction is the monitoring window's.
  Date/Author: 2026-08-21 / human

- Decision: a deferred review's dispatch names the current HEAD and what
  landed since the package's HEAD, and a check that must see the task's
  own tree runs in a detached worktree at the packaged HEAD — the
  conditional default, not every deferred review.
  Rationale: once review is deferred to the frontier the shared checkout
  sits at the wave's last HEAD, so a focused test or named-risk check
  outside the package's diff observes sibling changes and can hide a
  failure or manufacture one. Always-detaching was declined: a fresh
  worktree may need its dependencies installed before anything runs — a
  real per-review cost — and most deferred reviews read the package
  rather than run something outside it.
  Date/Author: 2026-08-21 / fable session (codex finding adopted)

- Decision: fix loops record their own commit range (fix-base/fix-head)
  and re-review packages cover only that range.
  Rationale: a deferred task's fix lands after sibling commits; the
  original base..head no longer bounds it, and a package from the original
  base would drag siblings into a task-scoped re-review.
  Date/Author: 2026-08-21 / fable session (codex finding adopted)

- Decision: declined — codex round 3 asked for adversarial before/after
  pressure evals (a real run exercising deferred review, fixes, and
  compaction) before release.
  Rationale: the human chose adopt-now-and-monitor as the evidence path
  (first Decision Log entry); the monitored next features are exactly that
  before/after run on real work, with reopen criteria pre-stated in §3; the
  smoke checks cover the wording's binding effect. Recorded so the
  disagreement is visible, not relitigated.
  Date/Author: 2026-08-21 / fable session

## Surprises & Discoveries

- Observation: across the four runs reviewer time equals or exceeds executor
  time in two (A: 3h39m vs 1h50m; D: 42m vs 45m) — reviewers run mutation
  batteries, 20–40 minutes and 26–77k output tokens per review in run A.
  Evidence: `scripts/sde-telemetry` + per-dispatch durations, session
  `e92c7422`, computed 2026-08-21.
- Observation: fixer dispatches are of the same order as executors, not
  more numerous as the pre-v2 classification read — session-wide 70 fixers
  to 92 executors; within run A's task window (2026-08-18 01:30–08:30 UTC)
  13 to 11, where they do outnumber them. Each fixer is a fresh dispatch
  paying orientation again.
  Evidence: same, recomputed 2026-08-21 after the collector learned the
  task-prefixed description forms (`T1 implementer: …`).
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
- Observation: the controller's own output (2.9M tokens, fable) is about a
  third of all workers combined (9.0M) over the session, and larger than any
  single worker role except executors (3.5M) — the "frontier plans once,
  cheap executes" picture understates the controller: every task costs
  controller turns, so fewer tasks cut controller cost too.
  Evidence: telemetry token totals, deduplicated by message id; the earlier
  7.0M / 8.8M reading double-counted multi-row assistant messages, which
  inflated the fable controller far more than the workers.
- Observation: PR #72's recommended feature (arkho#9 paged envelope) had
  already shipped in arkho PR #11 on 2026-08-18, the day before the spec was
  written — the experiment's target was stale at birth.
  Evidence: memory `read-surface-epic-shipped`; arkho#11 merge 591ba00.
- Observation (acceptance 3 smoke check, 2026-08-21): three opus planners on
  the new writing-plans text cut the PR #74 spec into 7, 6, 6 tasks (median
  6); every `Consumes` from an earlier task named its producer in all
  three. The control rep on the old text cut it into 8 — splitting the
  primitives into a by-id task and a walk task and giving drill-lib its own
  task, the "smallest unit" rule in action. The shipped plan, written by a
  frontier session under the old text, had 7. The shift is modest and in
  the expected direction; the wording's firmly binding effect is structural
  (producer-naming Consumes).
  Evidence: four subagent transcripts, this session.
- Observation (acceptance 4, 2026-08-21): three opus controllers on the new
  subagent-driven-execution text all answered {1} | {2,3,4,5} | {6} | {7}
  for the PR #74 plan, each describing serial executors, per-task BASE,
  concurrent reviewers, and resume-based fixes; two of three flagged the
  Task 3/4 shared-file overlap unprompted as a reason to review Task 3
  early if load-bearing. Inference was needed — that plan's Interfaces
  blocks predate producer naming.
  Evidence: three subagent transcripts, this session.
- Observation (acceptance 4 re-run on the v1.1 text, 2026-08-21): two more
  opus controllers answered {1} | {2,3} | {4,5} | {6} | {7} and
  {1} | {2,3,4,5} | {6} | {7} respectively — the new undeclared-overlap
  clause tipped one rep to review Task 3 before Task 4 (matching the real
  run's ledger, which recorded that handoff as MUST-carry) and left the
  other batching with the promotion rule held ready. Both wrote the
  `executed` ledger line with base and executor handle, refused to
  re-execute executed-but-unreviewed tasks after a simulated compaction,
  and resumed Task 3's executor with the list of what landed since its
  HEAD. Five of five reps across both texts produced a frontier schedule
  with at least one multi-task set and concurrent reviewers — the old text
  cannot produce that.
  Evidence: two subagent transcripts, this session.
- Observation: `claude -p --plugin-dir <worktree>` loads the worktree's
  skill text over the installed plugin (probe quoted both new sentences
  verbatim), so the keyword tests can exercise an unreleased edit through a
  one-line `claude` shim.
  Evidence: `plugin-dir-probe.txt`, this session.

## Outcomes & Retrospective

Shipped 2026-08-21 as v7.59.0 on `task-grain-cadence` (direct track with this
spec; no plan, no SDE run). Everything the purpose named is in place:
writing-plans sizes tasks by ownability and interface frontiers in the
human's wording, with `Consumes` naming its producer; subagent-driven-
execution reviews clean at dependency frontiers, batches siblings with
concurrent reviewers when their tests are hermetic, resumes the executor
for fixes and the reviewer for re-reviews over a fix-range package, and
keeps an `executed`/fix-range ledger that survives compaction without
re-executing; the worker-model text matches the standing directive; and
`scripts/sde-telemetry` reports dispatches by role with span, active time,
and message-id-deduplicated tokens.

Review shape: one independent spec review (fable, 15 findings, all but the
relitigation of settled human calls adopted in v1.1) and five codex native
rounds over the branch (3 → 2 → 4 → 1 → clean), each fixed by a single
fix-wave subagent. Every codex finding was a real seam the first drafts
left open — concurrent reviewers racing shared test state, the telemetry's
double-counted usage rows and idle-inflated spans, a deferred review's
moved-on checkout, fix commits breaking a task's contiguous range, the DONE
status row contradicting deferral, a resumed reviewer's stale report. One
codex finding was declined on the human's evidence decision (before/after
pressure evals before release) and is recorded as such.

Evidence collected: the four-run baseline; the wording smoke checks
(7/6/6 tasks vs 8 on the old text; producer-naming Consumes 3/3; frontier
schedules with batched siblings 5/5; ledger `executed` lines and no
re-execution after simulated compaction); the SDE keyword test green
against the worktree skill through a `--plugin-dir` shim.

Lessons: the first telemetry read overstated the controller's share by
2.5× (duplicate `message.id` rows) — verify a collector's arithmetic on
one transcript before quoting its totals; a direct-track spec that quotes
the skill text verbatim made five review rounds cheap to apply and check
(byte-identical quote checks); step 4 of the SDE loop is dense after those
rounds — each clause closes a validated gap, but a wording-diet pass is the
natural follow-up once monitoring shows which clauses bind.

Residue: the §3 monitoring duty (next three controlled-track features);
the version collision with PR #80 (both 7.59.0 — whichever merges second
rebumps on the manifest conflict); §4's deferred levers (parallel
executors, plan resolution, reviewer depth).

## Revision Notes

- v1 (2026-08-21): initial design, approved in session (direct track with
  spec); §1 text is the human's wording.
- v1.1 (2026-08-21): independent review (fable) adopted — acceptance 1's
  grep was self-defeating (new text contains "smallest unit"); acceptance 4
  dropped the "stricter schedule" clause that admitted per-task behavior
  and states that inference from older Interfaces is intended; acceptance 5
  pinned to a live session (≥ 277, roles sum); acceptance 3 relabeled a
  smoke check with its real criterion; §2 now quotes the skill-bound text
  verbatim; frontier rule gained "reviewed clean", the final-task clause,
  the undeclared-dependency default, and "in plan order"; concurrency
  claim narrowed to package-reading reviews; fresh-fixer clause rephrased
  as a default with reason; resume messages carry what landed since the
  executor's HEAD; ledger gained `executed` lines and the executed-vs-not-
  started resume rule; escalation text covers sonnet → opus and the
  executor prompt's "more capable model" sentence; PR #76 example corrected
  (it is a chain — per-task schedule); baseline max fix rounds (2) and the
  P1/P2 mapping recorded.
- v1.2 (2026-08-21): acceptance 4 admits the split-at-overlap reading the
  v1.1 clause licenses; re-test observations recorded.
- v1.3 (2026-08-21): codex review adopted — concurrent-review predicate,
  telemetry dedupe and active time; token figures recomputed.
- v1.4 (2026-08-21): codex round 2 adopted — deferred-review tree clause;
  telemetry recognizes task-prefixed noun descriptions; dispatch-count
  citations corrected.
- v1.5 (2026-08-21): codex round 3 — fix-range ledger and re-review
  packaging, DONE routes through the frontier, reviewer template gains
  task-head/checkout-head; eval-before-release finding recorded as
  declined.
- v1.6 (2026-08-21): codex round 4 — re-review messages refresh the
  reviewer's report, checkout, and worktree inputs.
