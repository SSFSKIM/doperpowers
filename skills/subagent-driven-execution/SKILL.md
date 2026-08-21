---
name: subagent-driven-execution
description: Use when running an execution plan with independent tasks in the current session
---

# Subagent-Driven Execution

Execute a plan by dispatching a fresh executor subagent per task, a task
review (spec compliance + code quality) at each dependency frontier, and a
broad whole-branch review at the end.

**Why subagents:** each worker gets exactly the context its task needs — no
session history, no other tasks' noise — and your own context stays free for
coordination. Quality comes from the loop: fresh executor, independent
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
   the workspace (`scripts/sde-workspace PLAN_FILE`) and check for an
   existing ledger (Durable Progress below) before dispatching anything.
2. **Pre-flight:** scan the plan for tasks that contradict each other, the
   Global Constraints, or the review rubric (e.g. a mandated test that
   asserts nothing). Present findings to your human partner as one batched
   question — each beside the plan text that mandates it — before execution;
   a clean scan proceeds without comment.
3. **Per task, in plan order:** extract the brief (`scripts/task-brief
   PLAN_FILE N`), record BASE (the current commit), dispatch the executor
   ([executor-prompt.md](executor-prompt.md)) and write the task's
   `executed` ledger line with its agent handle (Durable Progress below)
   — fixes resume it. Answer its questions before it proceeds. One
   executor at a time — parallel executors conflict in a shared worktree.
4. **Review at the frontier:** a task is reviewed clean — findings fixed
   and re-reviewed — before any task that consumes what it produced
   dispatches; the briefs' Interfaces name the producers, and the plan's
   final verification task consumes the whole branch. Tasks nothing
   downstream consumes yet may keep executing and are reviewed together
   when the frontier closes (the next task consumes from them, or the
   plan ends): one review package per task (`scripts/review-package
   PLAN_FILE BASE HEAD`, each task's own BASE..HEAD), one task reviewer
   per task ([task-reviewer-prompt.md](task-reviewer-prompt.md)) with the
   printed path, dispatched together when their focused tests cannot
   collide — reviews read their package, not the tree, so hermetic suites
   run concurrently; suites that share mutable state — a test database, a
   fixed port — run one reviewer at a time.
   Where no interface is declared but two tasks touch the same files,
   judge from their Files lists: an overlap that looks load-bearing is
   reviewed before the later task dispatches. The frontier is the ceiling
   on deferral, not the floor: a DONE_WITH_CONCERNS, a doubt of your own,
   or a first task whose brief style the executor may have misread are
   reasons to review that task now.
   A deferred review reads a tree that has moved past its package —
   Task 1's package is BASE1..HEAD1 while the checkout sits at the
   wave's last HEAD. Name the current HEAD and what landed since the
   task's own HEAD (the sibling commits and files) in the dispatch, so
   a sibling's effect is not read as this task's; a check that must see
   the task's own tree — a focused test, a named risk — runs in a
   detached worktree at the packaged HEAD (`git worktree add --detach
   <workspace>/review-N <HEAD_N>`, removed after the review) rather
   than in the shared checkout.
5. **Findings:** Critical/Important findings go back to the executor that
   wrote the code — resume it with the findings; it holds the task's
   context and skips the orientation a fresh fixer pays. Several tasks
   with findings in one wave resume one at a time (shared worktree).
   Re-review by resuming the reviewer with the fix commits' package
   (`scripts/review-package PLAN_FILE FIX_BASE FIX_HEAD` — the fix range:
   the reviewer already holds the task's original package, and a deferred
   task's fix lands past its siblings' commits); repeat until both
   verdicts are clean. That message names the fix range, sends the
   reviewer back to the report (the executor appended the fix's test
   evidence there), and carries the refreshed checkout head and what
   landed since — plus a fresh detached worktree at the fix head if the
   review needs the task's own tree. A resumed reviewer otherwise judges
   the fix against its pre-fix memory. A fresh fixer when the executor
   cannot be resumed, or when its frame is the problem — two failed
   re-reviews is the usual sign. Record Minor findings in the ledger —
   the final review triages that list, so it is read, not discarded. Fix
   through a worker, not your own edits: manual fixes pollute your
   context and skip review.
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

Dispatch workers — executors, task reviewers, fixers — on opus at high
reasoning effort; the task grain is calibrated to that tier. A simple
task — a doc update, a mechanical rename, a verification walk with every
command given — can go to sonnet. Never dispatch workers on the top tier
(fable): it adds cost without adding reliability and is the controller's
tier, not the worker's — the plan and the brief absorb the difficulty,
not the model. When a worker reports BLOCKED on reasoning capacity rather
than missing context, a sonnet task moves to opus; from opus there is no
tier above — the difficulty moves into the brief: resolve the hard call
yourself and re-dispatch, or split the task.

The final whole-branch review is the deliberate exception: strongest
available model, highest effort — it is the last gate before merge and the
only reader of the entire branch.

Name the model in every dispatch — an omitted model silently inherits your
session's, usually the most expensive.

## Executor statuses

- **DONE** → review at the frontier (step 4): package and reviewer now
  when something downstream consumes the task or an early-review reason
  applies, otherwise it waits for the wave.
- **DONE_WITH_CONCERNS** → read the concerns first: correctness or scope
  concerns get addressed before review; observations ride along to it.
- **NEEDS_CONTEXT** → provide the missing context, re-dispatch.
- **BLOCKED** → diagnose before retrying: missing context (provide it),
  reasoning capacity (sonnet → opus; from opus, resolve the hard call in
  the brief), task too large (split it), plan wrong (escalate to the
  human). Something must change — a bare retry
  answers an escalation with nothing.

**Reviewer ⚠️ items** — requirements the reviewer could not verify from the
diff (unchanged code, cross-task) come back marked ⚠️. Resolve each one
yourself before marking the task complete; you hold the plan and cross-task
context the reviewer lacks. A confirmed gap is a failed spec review: back
to the executor, then re-review.

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
  `task-N-report.md`); the executor writes detail there and returns only
  status, commits, a one-line test summary, and concerns.
- The task reviewer gets three paths — brief, report, review package — plus
  the plan's binding constraints copied verbatim (exact values, formats,
  stated relationships) and, for a deferred review, the checkout head and
  what landed since (the template's Checkout line). Its template already
  carries the process rules.
- `review-package` BASE is the commit you recorded before dispatching the
  executor — never `HEAD~1`, which silently drops all but the last
  commit of a multi-commit task. A re-review's BASE is the ledger's
  `fix-base` — the HEAD when the fix dispatched — so the package is the
  fix alone.
- Let the reviewer judge: don't pre-rate severity or list things not to
  flag ("don't treat X as a defect", "at most Minor") — that impulse is
  usually you sparing yourself a review loop. Adjudicate findings when they
  come back. A finding that conflicts with the plan's own text is the
  human's decision: present the finding and the plan text, ask which
  governs.
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
expensive failure observed. The ledger file, not your todos, is the record:

- The workspace (`scripts/sde-workspace PLAN_FILE` →
  `<repo-root>/.doperpowers/sde/<plan-basename>/`) holds every artifact for
  THIS plan: ledger, briefs, reports, review packages. Another plan's
  directory is never yours to read or write.
- The ledger lives at `<workspace>/progress.md`, first line
  `# SDE ledger — plan: <plan file path>`. If that line names your plan,
  tasks with a `Task <N>: complete` line are done; a task with an
  `executed` line but no `complete` line is awaiting review or fixes —
  resume its review (or its handles), never re-execute it; resume
  executing at the first task with neither. A ledger naming a different
  plan file is another plan's progress: leave it, start your own.
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

- **doperpowers:using-git-worktrees** — isolated workspace before starting
- **doperpowers:writing-plans** — creates the plan this skill executes
- **doperpowers:finishing-a-development-branch** — after the final review
