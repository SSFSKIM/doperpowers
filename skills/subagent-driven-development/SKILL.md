---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

# Subagent-Driven Development

Execute a plan by dispatching a fresh implementer subagent per task, a task
review (spec compliance + code quality) after each, and a broad whole-branch
review at the end.

**Why subagents:** each worker gets exactly the context its task needs — no
session history, no other tasks' noise — and your own context stays free for
coordination. Quality comes from the loop: fresh implementer, independent
review, fixes re-reviewed.

**Working posture:** execute all tasks without pausing to check in — stop
only for a BLOCKED you cannot resolve, ambiguity that genuinely prevents
progress, or completion. Between tool calls, narrate at most a line; the
ledger and tool results carry the record.

## When to use

A written plan with mostly-independent tasks, executed in this session.
Tightly-coupled tasks or no plan yet → work manually or brainstorm first.

## The loop

1. Read the plan once. Note the Global Constraints, create todos, resolve
   the workspace (`scripts/sdd-workspace PLAN_FILE`) and check for an
   existing ledger (Durable Progress below) before dispatching anything.
2. **Pre-flight:** scan the plan for tasks that contradict each other, the
   Global Constraints, or the review rubric (e.g. a mandated test that
   asserts nothing). Present findings to your human partner as one batched
   question — each beside the plan text that mandates it — before execution;
   a clean scan proceeds without comment.
3. **Per task:** extract the brief (`scripts/task-brief PLAN_FILE N`),
   record BASE (the current commit), dispatch the implementer
   ([implementer-prompt.md](implementer-prompt.md)). Answer its questions
   before it proceeds. One implementer at a time — parallel implementers
   conflict in a shared worktree.
4. On DONE: generate the review package
   (`scripts/review-package PLAN_FILE BASE HEAD`), dispatch the task
   reviewer ([task-reviewer-prompt.md](task-reviewer-prompt.md)) with the
   printed path.
5. **Findings:** dispatch a fix subagent for Critical/Important findings,
   then re-review; repeat until both verdicts are clean. Record Minor
   findings in the ledger — the final review triages that list, so it is
   read, not discarded. Fix through a subagent, not your own edits: manual
   fixes pollute your context and skip review.
6. Mark the task complete in todos and the ledger; route anything that
   changed design understanding into the spec's living tail
   (doperpowers:execspec). Implementation noise stays in commit messages.
7. **After all tasks:** dispatch the final whole-branch review (external
   reviewer — codex native review via doperpowers:codex-companion's
   `review` verb with `--base <base>`; a
   fresh top-tier Claude reviewer if codex is unavailable) with its own
   package (`scripts/review-package PLAN_FILE MERGE_BASE HEAD`,
   MERGE_BASE = `git merge-base main HEAD`). Then
   doperpowers:finishing-a-development-branch.

## Model selection

Dispatch workers — implementers, task reviewers, fixers — on the mid-tier
model at high reasoning effort (Claude: sonnet, effort high). This default
is empirical: cheap-tier implementers take 2–3× the turns and cost more
overall, and top-tier workers add cost without adding reliability — the
plan and the brief absorb the difficulty, not the model. Escalate per
incident: when a worker reports BLOCKED on reasoning capacity rather than
missing context, re-dispatch that one task on a stronger model.

The final whole-branch review is the deliberate exception: strongest
available model, highest effort — it is the last gate before merge and the
only reader of the entire branch.

Name the model in every dispatch — an omitted model silently inherits your
session's, usually the most expensive.

## Implementer statuses

- **DONE** → review package → task reviewer.
- **DONE_WITH_CONCERNS** → read the concerns first: correctness or scope
  concerns get addressed before review; observations ride along to it.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → diagnose before retrying: missing context (provide it),
  reasoning capacity (stronger model), task too large (split it), plan
  wrong (escalate to the human). Something must change — a bare retry
  answers an escalation with nothing.

**Reviewer ⚠️ items** — requirements the reviewer could not verify from the
diff (unchanged code, cross-task) come back marked ⚠️. Resolve each one
yourself before marking the task complete; you hold the plan and cross-task
context the reviewer lacks. A confirmed gap is a failed spec review: back
to the implementer, then re-review.

## Dispatch hygiene

Everything pasted into a dispatch prompt — and everything a subagent prints
back — stays resident in your context for the rest of the session. Hand
artifacts over as files (a real session's dispatch hit 42k chars, 99% of it
pasted prior-task history):

- The brief file is the single source of requirements; exact values
  (numbers, magic strings, signatures, test cases) live only there. A
  dispatch carries: one line on where the task fits; the brief path ("read
  this first — it is your requirements"); interfaces and decisions from
  earlier tasks the brief cannot know; your resolution of any ambiguity you
  noticed in the brief; the report-file path and report contract.
- The report file is named after the brief (`task-N-brief.md` →
  `task-N-report.md`); the implementer writes detail there and returns only
  status, commits, a one-line test summary, and concerns.
- The task reviewer gets three paths — brief, report, review package — plus
  the plan's binding constraints copied verbatim (exact values, formats,
  stated relationships). Its template already carries the process rules.
- `review-package` BASE is the commit you recorded before dispatching the
  implementer — never `HEAD~1`, which silently drops all but the last
  commit of a multi-commit task.
- Let the reviewer judge: don't pre-rate severity or list things not to
  flag ("don't treat X as a defect", "at most Minor") — that impulse is
  usually you sparing yourself a review loop. Adjudicate findings when they
  come back. A finding that conflicts with the plan's own text is the
  human's decision: present the finding and the plan text, ask which
  governs.
- Fix dispatches carry the implementer contract: re-run the covering tests
  (name them in the dispatch — a one-line fix doesn't need the whole
  suite), report the command and output; confirm all three are in the fix
  report before re-review.
- Final-review findings go to ONE fixer with the complete list — per-finding
  fixers each rebuild context and re-run suites; a real session's
  per-finding fix wave cost more than all its tasks combined.

## Durable progress

Conversation memory does not survive compaction. Controllers that lost
their place have re-dispatched entire completed task sequences — the most
expensive failure observed. The ledger file, not your todos, is the record:

- The workspace (`scripts/sdd-workspace PLAN_FILE` →
  `<repo-root>/.doperpowers/sdd/<plan-basename>/`) holds every artifact for
  THIS plan: ledger, briefs, reports, review packages. Another plan's
  directory is never yours to read or write.
- The ledger lives at `<workspace>/progress.md`, first line
  `# SDD ledger — plan: <plan file path>`. If that line names your plan,
  tasks with a `Task <N>: complete` line are done — resume at the first
  task without one. A ledger naming a different plan file is another plan's
  progress: leave it, start your own.
- When a task's review comes back clean, append
  `Task N: complete (commits <base7>..<head7>, review clean)`.
- After compaction, trust the ledger and `git log` over your own
  recollection. (`git clean -fdx` destroys the workspace — recover from
  `git log`.)

## Integration

- **doperpowers:using-git-worktrees** — isolated workspace before starting
- **doperpowers:writing-plans** — creates the plan this skill executes
- **doperpowers:finishing-a-development-branch** — after the final review
