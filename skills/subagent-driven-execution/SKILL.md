---
name: subagent-driven-execution
description: Use to run a doperpowers:execspec spec whose Plan of Work has several milestones in this session.
---

# Subagent-Driven Execution

Execute a spec's Plan of Work by dispatching a fresh executor subagent per
milestone — each has its task reviewed (spec compliance + code quality) and
fixes what the review finds before it returns — and a broad whole-branch
review at the end. Each milestone of the spec is one task of this loop —
the ledger and the scripts count tasks.

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
   hygiene below) with `run_in_background: true` — a nested dispatch that
   leaves the flag out ran in the foreground, where you cannot read its
   verdicts — and write the task's `executed` ledger line with its agent
   handle (Durable Progress below). Then wait in the foreground until it
   returns: Bash loops of a few minutes each that come back early when a
   new `task-N-review-*.md` lands in the workspace; its return reaches you
   between calls. A controller that is itself a subagent and ends its turn while its
   executor runs is told to hand back at once, mid-milestone (seen in a
   live run of this loop; friction tracker #304). One executor at a time —
   parallel executors conflict in a shared worktree — and an executor
   holds the checkout until its review is clean.
4. **The task's review runs inside it:** the executor packages its range,
   dispatches `doperpowers:task-reviewer`, fixes, and re-reviews with a
   fresh reviewer, writing each round's verdict, with what it will do
   about each finding, as `task-N-review-K.md`. Read each one as it lands
   against what only you hold — sibling milestones and the interfaces
   they share, the owner's rulings, the spec — and message the executor
   when that changes the fix: a contract a sibling relies on, a ruling it
   has not heard, a spec statement the finding exposes as wrong (fix the
   spec first, with a dated Decision Log entry; you are its one writer).
   Otherwise stay silent; it reads silence as proceed.
5. **Fold the report back.** The executor returns once its review is clean,
   or with findings disputed or still open after two rejected fixes. Read
   the decisions and discoveries in its report and fold the ones a later
   reader needs into the spec — a decision into the Decision Log, a
   discovery into Surprises & Discoveries — and commit, so the next
   executor reads them in the spec rather than in your dispatch. A
   decision that works against the spec's intent or crosses the gate is
   not folded: it goes back to the executor, or up to whoever dispatched
   you. Record the deferred Minor findings in the ledger — the final
   review triages that list, so it is read, not discarded.
6. **Disputes and open findings** are yours to adjudicate against the
   spec's intent: the author does not grade its own work, and the reviewer
   is rigorous by design, so a real finding can still be too minor to act
   on or bounded by the design. Upheld, resume the executor to fix and
   re-review; when its frame is the problem — two rejected fixes is the
   usual sign — or it cannot be resumed, dispatch a fresh
   `doperpowers:task-executor` briefed with the findings, which reviews its
   fix the same way. Fix through a worker, not your own edits: manual
   fixes pollute your context and skip review.
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
the medium review rung's model and effort — and the executor dispatches it
at that pin, a sonnet executor's included: the task review is a
task-scoped gate, and the whole-branch review at the spec's named rung is
the deep read. A simple task — a doc update, a mechanical rename, a
verification walk with every command given — can go to sonnet, the tier
below opus, by passing `model: sonnet` at dispatch, which overrides the
executor's pin. Never dispatch workers on fable or astra: the top tier
adds cost without adding reliability — the spec absorbs the difficulty,
not the model, whatever model wrote the spec. When a worker reports BLOCKED on reasoning capacity rather
than missing context, a sonnet task moves to opus; from opus there is no
tier above — resolve the hard call yourself in the spec's Decision Log and
re-dispatch, or split the milestone.

The final whole-branch review is the deliberate exception: it goes through
doperpowers:review-code at the rung the spec's verification entry names
(its Decision Log), or the level the branch warrants when none is
recorded — it is the last gate before merge and the only reader of the
entire branch.

## Executor statuses

- **DONE** → its review is clean: fold its report back (step 5) and mark
  the task complete (step 7).
- **DONE_WITH_CONCERNS** → read the concerns first: disputed or open
  findings go to step 6; correctness or scope concerns are addressed —
  back to the executor, then re-review — before the task is complete;
  observations are folded like any other report.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → diagnose before retrying: missing context (provide it),
  reasoning capacity (sonnet → opus; from opus, resolve the hard call in
  the spec), task too large (split it), a fork under the gate (return to
  the session that dispatched you, or to the human when that is you).
  Something must change — a bare retry answers an escalation with
  nothing.

**Reviewer ⚠️ items** — requirements the reviewer could not verify from the
diff come back marked ⚠️. The executor checks the ones its task's code
answers; one that spans tasks reaches you in its verdict. Resolve each of
those yourself before marking the task complete; you hold the cross-task
context the reviewer lacks. A confirmed gap is a failed spec review: back
to the executor, then re-review.

## Dispatch hygiene

Everything pasted into a dispatch prompt — and everything a subagent prints
back — stays resident in your context for the rest of the session. Hand
artifacts over as files (a real session's dispatch hit 42k chars, 99% of it
pasted prior-task history):

- The worker contracts — TDD, deciding gaps and reporting decisions,
  self-review, the task review and its brief, escalation statuses, the
  report shape, the reviewer's rubric and read-only posture — live in the
  agent definitions, not in
  your dispatch. A dispatch carries only what is particular to this task.
- The spec is the single source of requirements; exact values live only
  there, and anything decided since goes into the spec (step 5), not into
  a dispatch. An executor dispatch carries: the spec path and the
  milestone ("read the whole spec; you own M3 of its Plan of Work"); for
  a composite child, the composite's path and the child id its execution
  document cites, since the design lives in that section; the directory
  to work from; the report-file path; the task's BASE (the commit you
  recorded); the path of this skill's `scripts/review-package`; and your
  answer to anything the executor asked.
- The report file is `task-N-report.md` in the workspace; the executor
  writes detail there — its reviewer's reports beside it — and returns
  only status, commits, a one-line test summary, the review's outcome,
  decisions made, and concerns.
- Adjudicate disputed findings against the spec's intent. A finding that
  exposes a spec statement as wrong is fixed in the spec by you — the
  design section revised, a dated Decision Log entry; you are its one
  writer — and in the code by the worker; only a fork under the gate goes
  up.
- A fix message to a resumed executor, or a fresh fixer's brief, names
  the findings and the tests that cover them — a one-line fix doesn't need
  the whole suite. A resumed executor's view of the tree ends at its own
  HEAD: name what landed since (commits and files) and have it re-read
  before editing; its covering tests include sibling suites touching the
  same files.
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
  with an `executed` line but no `complete` line is still building or in
  its review — resume its executor (its report records the rounds so far),
  never re-execute it; resume executing at the first task with neither. A
  ledger naming a different file is another run's progress: leave it,
  start your own.
- At dispatch, append `Task N: executed (base <sha7>, executor
  <handle>)` — a fix or a recovery resumes that handle, and after
  compaction the ledger is the only place it survives.
- When the executor returns reviewed clean, append `Task N: complete
  (commits <base7>..<head7>, review clean in <n> rounds)`, and the
  deferred Minor findings beneath it.
- After compaction, trust the ledger and `git log` over your own
  recollection. (`git clean -fdx` destroys the workspace — recover from
  `git log`.)

## Integration

- [isolated-workspace.md](isolated-workspace.md) — the workspace before the first task and its cleanup after the last
- **doperpowers:execspec** — writes the spec this skill executes and, at its step 4, dispatches this loop through a `doperpowers:plan-executor` subagent
