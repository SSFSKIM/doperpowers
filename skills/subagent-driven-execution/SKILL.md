---
name: subagent-driven-execution
description: The execution loop for a doperpowers:execspec spec whose Plan of Work has several milestones, for running such a spec in this session.
---

# Subagent-Driven Execution

Execute a spec's Plan of Work by dispatching a fresh executor subagent per
milestone, a task review (spec compliance + code quality) at each
dependency frontier, and a broad whole-branch review at the end. Each
milestone of the spec is one task of this loop — the ledger and the scripts
count tasks.

**Why subagents:** each worker starts from the spec and the code, with no
session history and no other tasks' noise, and your own context stays free
for coordination. Quality comes from the loop: fresh executor, independent
review, fixes re-reviewed.

**Working posture:** execute all tasks without pausing to check in — stop
only for a BLOCKED you cannot resolve, a product, taste, or substantive
design decision the spec does not cover, or completion. Between tool calls, narrate at
most a line; the ledger and tool results carry the record.

**The spec is the only requirements document.** Every executor and
reviewer reads it whole; each milestone entry says where that task's
boundaries are and points into the design for the rest. The spec cannot
foresee every gap and is not expected to: executors resolve gaps in the
spirit of its intent and report what they decided
([../execspec/references/living-spec.md](../execspec/references/living-spec.md),
"While the spec is being executed"). You are the spec's one writer while
the loop runs.

## When to use

A spec whose Plan of Work has several milestones (the shape in
[../execspec/references/living-spec.md](../execspec/references/living-spec.md)),
executed in this session. One milestone, or no spec yet → work it directly
or brainstorm first.

## The loop

1. Read the spec once. Note the constraints that open its execution
   section, make sure you are on an isolated checkout
   ([isolated-workspace.md](isolated-workspace.md)), resolve the artifact
   workspace (`scripts/sde-workspace SPEC_FILE`) and check for an existing
   ledger (Durable Progress below) before dispatching anything.
2. **Pre-flight:** check the milestones' order against what each consumes,
   and look for anything in the spec two milestones would read two ways or
   that the review rubric would call a defect (e.g. a mandated test that
   asserts nothing). Resolve what the spec's intent settles, write it into
   the section it belongs to, and commit; only a product, taste, or substantive design decision the spec
   does not cover goes to whoever
   dispatched you (the spec's author session, or your human partner when
   you are running the loop yourself). A clean check proceeds without
   comment.
3. **Per task, in Plan of Work order:** record BASE (the current commit),
   dispatch the executor (`doperpowers:task-executor`, briefed per Dispatch
   hygiene below) and write the task's `executed` ledger line with its
   agent handle (Durable Progress below) — fixes resume it. Answer its
   questions before it proceeds. One executor at a time — parallel
   executors conflict in a shared worktree.
4. **Write the report back.** When an executor returns, read the decisions
   and discoveries in its report, write the ones a later reader needs into
   the section each belongs to
   ([../execspec/references/living-spec.md](../execspec/references/living-spec.md),
   "Keeping the spec current"), and commit, so the next executor reads them
   in the spec rather than in your dispatch. What the next milestone
   consumes — an interface as built, a fact about the environment — goes
   in now. A choice that changes a design decision goes in once the task's
   review is clean: written into its section it reads as approved design,
   and a later executor builds on it. A decision that works against the
   spec's intent or makes a product, taste, or substantive design decision
   the spec does not cover is not written in: it goes back to
   the executor, or up to whoever dispatched you.
5. **Review at the frontier:** a task is reviewed clean — nothing left
   that must be fixed (step 6) — before any task that consumes what it
   produced dispatches. The milestones' Interfaces name the producers, the
   spec's last milestone consumes the whole branch, and where none is
   declared but two tasks touch the same files, an overlap that looks
   load-bearing counts. Tasks nothing downstream consumes yet may keep
   executing and are reviewed together when the frontier closes; the
   frontier is the ceiling on deferral, not the floor — a
   DONE_WITH_CONCERNS or a doubt of your own is a reason to review that
   task now. Each task gets its own package (`scripts/review-package
   SPEC_FILE BASE HEAD`, its own BASE..HEAD) and its own reviewer
   (`doperpowers:task-reviewer`) with the printed path. Reviews read their
   package, not the tree, so reviewers whose focused tests are hermetic
   run together; suites that share mutable state — a test database, a
   fixed port — run one reviewer at a time.
   A deferred review's package ends at the task's HEAD while the checkout
   sits at the wave's last one. Name the current HEAD and the sibling
   commits and files that landed since in the dispatch, so a sibling's
   effect is not read as this task's; a check that must see the task's
   own tree — a focused test, a named risk — runs in a detached worktree
   at the packaged HEAD (`git worktree add --detach <workspace>/review-N
   <HEAD_N>`, removed after the review) rather than in the shared
   checkout.
6. **Findings:** the reviewer reports what it sees; what the task owes
   is your call against the spec, made for each Critical/Important
   finding before any goes back. A defect this task introduced that
   its consumers would meet, or one that is costly or irreversible if
   wrong, is fixed. One that was there before the task, or is rare or
   cosmetic and cheap to live with, is recorded in the ledger with a
   one-line reason, beside the Minor findings, and not reopened. One
   the spec's intent contradicts is dismissed. One you cannot place is
   fixed. Those to fix go back to the executor that wrote the code —
   resume it with the findings; it holds the task's context and skips
   the orientation a fresh fixer pays. Several tasks with findings in one
   wave resume one at a time (shared worktree). Fix through a worker, not
   your own edits: manual fixes pollute your context and skip review.
   Re-review by resuming the reviewer with the fix range's package
   (`scripts/review-package SPEC_FILE FIX_BASE FIX_HEAD`): it already
   holds the task's original package, and a deferred task's fix lands
   past its siblings' commits. The message names what you dismissed or
   recorded, so it is not raised again, sends the reviewer back to the
   report for the fix's test evidence, and carries the refreshed checkout
   head and what landed since — plus a fresh detached worktree at the fix
   head if the review needs the task's own tree; otherwise a resumed
   reviewer judges the fix against its pre-fix memory. Repeat until a
   round leaves nothing to fix: a reviewer finds something on every pass,
   so a loop that waits for its clean verdict has no end of its own. A
   fresh fixer (a new `doperpowers:task-executor` briefed with the
   findings) takes over when the executor cannot be resumed, or when its
   frame is the problem — two failed re-reviews is the usual sign. Record
   Minor findings in the ledger — the final review triages that list, so
   it is read, not discarded.
7. Mark the task complete in the ledger, and tick its milestone
   in the spec's `Progress` with a timestamp and commit — the tick means
   reviewed clean, the same as the ledger's `complete`, and the ledger is
   gitignored, so the committed spec is what a recovery reader sees. For
   a child of a composite spec, what the task makes false in the composite
   goes into the execution document's `For the composite's writer` list,
   and a binding contradiction up as `[parent-impact]` per
   doperpowers:decomposing; the composite is its writer's to edit. Implementation noise stays in commit
   messages.
8. **After all tasks:** dispatch the final whole-branch review through
   doperpowers:review-code against `<base>` at the rung the spec's
   verification names, or the level the branch warrants when none is
   named — a rung agent, or the panel for a large branch — with its own
   package (`scripts/review-package SPEC_FILE MERGE_BASE HEAD`,
   MERGE_BASE = `git merge-base main HEAD`). Its brief names the spec and
   the commit your human partner approved — for a child of a composite,
   the composite and the child's parent pin as well — and asks the
   reviewer to read `git diff --word-diff <commit> <head> -- <file>` for
   an acceptance item reduced or a design decision changed along the way:
   a spec first committed on the branch shows in the branch diff only as
   its final text. The panel takes no brief, so when the review is the
   panel those facts go up with the pinned range to the session that
   runs it.
   Then write the spec's `## Outcomes & Retrospective` entry, commit it,
   and integrate the branch ([isolated-workspace.md](isolated-workspace.md), "At finish").

## Model selection

The workers run at their pins whatever model wrote the spec:
`doperpowers:task-executor` at opus at high effort, the tier the
milestone grain is calibrated to, and `doperpowers:task-reviewer` at sol
at xhigh, the medium review rung, since the frontier review is a
task-scoped gate and the whole-branch review is the deep read. The
frontier's work is the design and the spec; building its milestones is
close-frontier work, and the top tier (fable, astra) adds cost there
without adding reliability. A simple task — a doc update, a mechanical
rename, a verification walk with every command given — can go to sonnet
with `model: sonnet` at dispatch (Executor statuses says where a sonnet
task BLOCKED on reasoning goes); any other pin change is your human
partner's, and reaches you in your brief.

## Executor statuses

- **DONE** → write its report back (step 4), then review at the frontier
  (step 5): package and reviewer now when something downstream consumes
  the task or an early-review reason applies, otherwise it waits for the
  wave.
- **DONE_WITH_CONCERNS** → read the concerns first: correctness or scope
  concerns get addressed before review; observations ride along to it.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → diagnose before retrying: missing context (provide it),
  reasoning capacity (sonnet → opus; from opus, resolve the hard call in
  the spec), task too large (split it), a product, taste, or substantive
  design decision the spec does not cover (return to
  the session that dispatched you, or to the human when that is you).
  Something must change — a bare retry answers an escalation with
  nothing.

**Reviewer ⚠️ items** — requirements the reviewer could not verify from the
diff (unchanged code, cross-task) come back marked ⚠️. Resolve each one
yourself before marking the task complete; you hold the cross-task context
the reviewer lacks. A confirmed gap is a failed spec review: back to the
executor, then re-review.

## Dispatch hygiene

Everything pasted into a dispatch prompt — and everything a subagent prints
back — stays resident in your context for the rest of the session, and
pasted prior-task history is what bloats a dispatch. Hand artifacts over as
files:

- The worker contracts — TDD, deciding gaps and reporting decisions,
  self-review, escalation statuses, the report shape, the reviewer's
  rubric and read-only posture — live in the agent definitions, not in
  your dispatch. A dispatch carries only what is particular to this task.
- The spec is the single source of requirements; exact values live only
  there, and anything decided since goes into the spec (step 4), not into
  a dispatch. An executor dispatch carries: the spec path and the
  milestone ("read the whole spec; you own M3 of its Plan of Work"); for
  a composite child, the composite's path and the child id its execution
  document cites, since the design lives in that section; the directory
  to work from; the report-file path; and your answer to anything the
  executor asked.
- The report file is `task-N-report.md` in the workspace; the executor
  writes detail there and returns the short form its definition gives
  (`agents/task-executor.md`, Report).
- A reviewer dispatch carries the spec path and milestone (and, for a
  composite child, the composite's path and child id), the report path,
  the review package path, the task's BASE and HEAD and, for a deferred
  review, a checkout line: where the shared checkout sits, the
  sibling commits and files that landed since HEAD, and the detached
  worktree at HEAD if one was made. Omit the checkout line when the
  checkout is at HEAD.
- `review-package` BASE is the commit you recorded before dispatching the
  executor — never `HEAD~1`, which silently drops all but the last
  commit of a multi-commit task. A re-review's BASE is the ledger's
  `fix-base` — the HEAD when the fix dispatched — so the package is the
  fix alone.
- Let the reviewer judge: don't pre-rate severity or list things not to
  flag ("don't treat X as a defect", "at most Minor") — that impulse is
  usually you sparing yourself a review loop. Adjudicate findings when they
  come back, against the spec's intent. A finding that exposes a spec
  statement as wrong is fixed in the spec by you — the statement
  rewritten; you are its one writer — and in the code by the worker; only
  a product, taste, or substantive design decision the spec does not
  cover goes up.
- Fix messages — to a resumed executor or a fresh fixer — name the
  covering tests to re-run (a one-line fix doesn't need the whole suite);
  confirm the fix report carries their command and output before
  re-review. A resumed executor's view of the tree ends at its own HEAD:
  name what landed since (commits and files) and have it re-read before
  editing; its covering tests include sibling suites touching the same
  files.
- Final-review findings go to one fixer with the complete list — per-finding
  fixers each rebuild context and re-run suites, and a per-finding fix wave
  has cost more than all the tasks before it.

## Durable progress

Conversation memory does not survive compaction, and a controller that
loses its place re-dispatches completed tasks, the costliest failure this
loop has. The spec's Progress is the human-readable
state; the ledger file holds the mechanics a resume needs (bases, heads,
agent handles), which do not belong in the spec:

- The workspace (`scripts/sde-workspace SPEC_FILE` →
  `<repo-root>/.doperpowers/sde/<spec-basename>/`) holds every artifact for
  THIS spec: ledger, reports, review packages. Another spec's directory is
  never yours to read or write.
- The ledger lives at `<workspace>/progress.md`, first line
  `# SDE ledger — spec: <path of the file you execute>`. If that line
  names your spec, tasks with a `Task <N>: complete` line are done; a task
  with an `executed` line but no `complete` line is awaiting review or
  fixes — resume its review (or its handles), never re-execute it; resume
  executing at the first task with neither. A ledger naming a different
  file is another run's progress: leave it, start your own.
- At dispatch, append `Task N: executed (base <sha7>, executor
  <handle>)`; add `head <sha7>` when the executor returns and
  `reviewer <handle>` when the review dispatches — a fix resumes those
  handles, and after compaction the ledger is the only place they
  survive. When a fix dispatches append `fix-base <sha7>` (the HEAD at
  that moment) and `fix-head <sha7>` when it lands: a deferred task's
  fix commits sit past its siblings', so `base..head` no longer bounds
  the task's history.
- When a task's review comes back clean, append `Task N: complete
  (commits <base7>..<head7>[, fix <base7>..<head7>], review clean)`.
- After compaction, trust the ledger and `git log` over your own
  recollection. (`git clean -fdx` destroys the workspace — recover from
  `git log`.)

## Integration

- [isolated-workspace.md](isolated-workspace.md) — the workspace before the first task and its cleanup after the last
- **doperpowers:execspec** — writes the spec this skill executes and, in its `## Executing` section, dispatches this loop through a `doperpowers:plan-executor` subagent
