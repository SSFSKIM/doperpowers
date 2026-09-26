---
name: subagent-driven-execution
description: Use when running a spec whose Plan of Work has several milestones in the current session — a fresh executor per milestone, reviewed at dependency frontiers. Invoke this only after doperpowers:execspec produced that spec; never straight from a request.
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
only for a BLOCKED you cannot resolve, a fork under brainstorming's gate
that the spec does not cover, or completion. Between tool calls, narrate at
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
   section, create todos, make sure you are on an isolated checkout
   ([isolated-workspace.md](isolated-workspace.md)), resolve the artifact
   workspace (`scripts/sde-workspace SPEC_FILE`) and check for an existing
   ledger (Durable Progress below) before dispatching anything.
2. **Pre-flight:** check the milestones' order against what each consumes,
   and look for anything in the spec two milestones would read two ways or
   that the review rubric would call a defect (e.g. a mandated test that
   asserts nothing). Resolve what the spec's intent settles, record it in
   the Decision Log, and commit; only a fork under the gate goes to whoever
   dispatched you (the spec's author session, or your human partner when
   you are running the loop yourself). A clean check proceeds without
   comment.
3. **Per task, in Plan of Work order:** record BASE (the current commit),
   dispatch the executor (`doperpowers:task-executor`, briefed per Dispatch
   hygiene below) and write the task's `executed` ledger line with its
   agent handle (Durable Progress below) — fixes resume it. Answer its
   questions before it proceeds. One executor at a time — parallel
   executors conflict in a shared worktree.
4. **Fold the report back.** When an executor returns, read the decisions
   and discoveries in its report. Fold the ones a later reader needs into
   the spec — a decision into the Decision Log, a discovery into
   Surprises & Discoveries — and commit, so the next executor reads them
   in the spec rather than in your dispatch. A decision that works
   against the spec's intent or crosses the gate is not folded: it goes
   back to the executor, or up to whoever dispatched you; one the reviewer
   later rejects is reversed in the log when the fix lands.
5. **Review at the frontier:** a task is reviewed clean — findings fixed
   and re-reviewed — before any task that consumes what it produced
   dispatches; the milestones' Interfaces name the producers, and the
   spec's last milestone consumes the whole branch. Tasks nothing
   downstream consumes yet may keep executing and are reviewed together
   when the frontier closes (the next task consumes from them, or the Plan
   of Work ends): one review package per task (`scripts/review-package
   SPEC_FILE BASE HEAD`, each task's own BASE..HEAD), one task reviewer
   per task (`doperpowers:task-reviewer`) with the printed path,
   dispatched together when their focused tests cannot
   collide — reviews read their package, not the tree, so hermetic suites
   run concurrently; suites that share mutable state — a test database, a
   fixed port — run one reviewer at a time.
   Where no interface is declared but two tasks touch the same files,
   judge from what each milestone says it touches: an overlap that looks
   load-bearing is reviewed before the later task dispatches. The frontier
   is the ceiling on deferral, not the floor: a DONE_WITH_CONCERNS or a
   doubt of your own is a reason to review that task now.
   A deferred review reads a tree that has moved past its package —
   Task 1's package is BASE1..HEAD1 while the checkout sits at the
   wave's last HEAD. Name the current HEAD and what landed since the
   task's own HEAD (the sibling commits and files) in the dispatch, so
   a sibling's effect is not read as this task's; a check that must see
   the task's own tree — a focused test, a named risk — runs in a
   detached worktree at the packaged HEAD (`git worktree add --detach
   <workspace>/review-N <HEAD_N>`, removed after the review) rather
   than in the shared checkout.
6. **Findings:** Critical/Important findings go back to the executor that
   wrote the code — resume it with the findings; it holds the task's
   context and skips the orientation a fresh fixer pays. Several tasks
   with findings in one wave resume one at a time (shared worktree).
   Re-review by resuming the reviewer with the fix commits' package
   (`scripts/review-package SPEC_FILE FIX_BASE FIX_HEAD` — the fix range:
   the reviewer already holds the task's original package, and a deferred
   task's fix lands past its siblings' commits); repeat until both
   verdicts are clean. That message names the fix range, sends the
   reviewer back to the report (the executor appended the fix's test
   evidence there), and carries the refreshed checkout head and what
   landed since — plus a fresh detached worktree at the fix head if the
   review needs the task's own tree. A resumed reviewer otherwise judges
   the fix against its pre-fix memory. A fresh fixer (a new
   `doperpowers:task-executor` briefed with the findings) when the executor
   cannot be resumed, or when its frame is the problem — two failed
   re-reviews is the usual sign. Record Minor findings in the ledger —
   the final review triages that list, so it is read, not discarded. Fix
   through a worker, not your own edits: manual fixes pollute your
   context and skip review.
7. Mark the task complete in todos and the ledger, and tick its milestone
   in the spec's `Progress` with a timestamp and commit — the tick means
   reviewed clean, the same as the ledger's `complete`, and the ledger is
   gitignored, so the committed spec is what a recovery reader sees. For
   a child of a composite spec, advisory content goes in place and a
   binding contradiction up as `[parent-impact]` per doperpowers:decomposing
   rather than into the composite. Implementation noise stays in commit
   messages.
8. **After all tasks:** dispatch the final whole-branch review through
   doperpowers:review-code against `<base>` at the rung the spec's
   verification entry names (its Decision Log), or the level the branch
   warrants when none is recorded — a rung agent, or the panel for a
   large branch — with its own package (`scripts/review-package
   SPEC_FILE MERGE_BASE HEAD`, MERGE_BASE = `git merge-base main HEAD`).
   Then write the spec's `## Outcomes & Retrospective` entry, commit it,
   and integrate the branch ([isolated-workspace.md](isolated-workspace.md), "At finish").

## Model selection

`doperpowers:task-executor` is pinned to opus at high reasoning effort;
the milestone grain is calibrated to that tier, and fixes resume the same
executor. `doperpowers:task-reviewer` is pinned to sol at xhigh effort —
the low review rung's model and effort: the frontier review is a
task-scoped gate, and the whole-branch review at the spec's named rung is
the deep read. A simple task — a doc update, a mechanical rename, a
verification walk with every command given — can go to sonnet, the tier
below opus, by passing `model: sonnet` at dispatch, which overrides the
executor's pin. Never dispatch workers on fable or astra: the top tier
adds cost without adding reliability — the spec absorbs the difficulty,
not the model. When a worker reports BLOCKED on reasoning capacity rather
than missing context, a sonnet task moves to opus; from opus there is no
tier above — resolve the hard call yourself in the spec's Decision Log and
re-dispatch, or split the milestone.

The final whole-branch review is the deliberate exception: it goes through
doperpowers:review-code at the rung the spec's verification entry names
(its Decision Log), or the level the branch warrants when none is
recorded — it is the last gate before merge and the only reader of the
entire branch.

## Executor statuses

- **DONE** → fold its report back (step 4), then review at the frontier
  (step 5): package and reviewer now when something downstream consumes
  the task or an early-review reason applies, otherwise it waits for the
  wave.
- **DONE_WITH_CONCERNS** → read the concerns first: correctness or scope
  concerns get addressed before review; observations ride along to it.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → diagnose before retrying: missing context (provide it),
  reasoning capacity (sonnet → opus; from opus, resolve the hard call in
  the spec), task too large (split it), a fork under the gate (return to
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
back — stays resident in your context for the rest of the session. Hand
artifacts over as files (a real session's dispatch hit 42k chars, 99% of it
pasted prior-task history):

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
  writes detail there and returns only status, commits, a one-line test
  summary, decisions made, and concerns.
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
  statement as wrong is fixed in the spec by you — the design section
  revised, a dated Decision Log entry; you are its one writer — and in
  the code by the worker; only a fork under the gate goes up.
- Fix messages — to a resumed executor or a fresh fixer — carry the
  executor contract: re-run the covering tests (name them — a one-line
  fix doesn't need the whole suite), report the command and output;
  confirm all three are in the fix report before re-review. A resumed
  executor's view of the tree ends at its own HEAD: name what landed
  since (commits and files) and have it re-read before editing; its
  covering tests include sibling suites touching the same files.
- Final-review findings go to ONE fixer with the complete list — per-finding
  fixers each rebuild context and re-run suites; a real session's
  per-finding fix wave cost more than all its tasks combined.

## Durable progress

Conversation memory does not survive compaction. Controllers that lost
their place have re-dispatched entire completed task sequences — the most
expensive failure observed. The spec's Progress is the human-readable
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
- **doperpowers:execspec** — writes the spec this skill executes and, at its step 4, dispatches this loop through a `doperpowers:plan-executor` subagent
