# The task review moves inside the executor

> **Status:** decided 2026-10-25 by the owner ("nested, with verdicts to
> the plan-executor"). Each `doperpowers:task-executor` now dispatches
> its own `doperpowers:task-reviewer`, fixes, re-reviews, and returns
> reviewed clean; the controller reads each verdict as it lands and keeps
> the adjudication of anything the executor disputes.

## Question

subagent-driven-execution's controller (in practice a plan-executor)
mediated every task review: it dispatched the executor, packaged the
diff, dispatched the reviewer, resumed the executor with the findings,
re-packaged the fix, and resumed the reviewer, round after round. Should
the executor that wrote the code run that loop itself?

## Evidence

From this machine's transcripts (Claude Code 2.1.310), 120 plan-executor
runs that dispatched task-executors (33.6k plan-executor calls), and a
classified sample of 96 review cycles: 48 handled by a plan-executor
between reviewer and executor, 48 by implementer subagents that had
dispatched their own reviewer (about 70 such agents, mostly MAWS and desk
work). sol-xhigh classifiers judged, per blocking finding, what the
handler did and whether it was sound, from transcript text; the data,
rubric and scripts were kept in `/tmp/nest-eval/` for the session.

| | controller between | implementer handles |
|---|---|---|
| blocking findings sent to a fix | 110 / 113 | 94 / 101 (3 deferred, sound; 3 unreadable) |
| findings lost or weakened | 2 (the controller overrode the spec unasked) | 1 (dropped silently) |
| checked the finding against the code first | 2 / 48 | 31 / 48 |
| reviewer brief prejudged the work | 1 / 48 | 5 / 48 |
| the controller's knowledge changed the fix | 15 / 48 | — |

- Findings survive either handler at the same rate. What the controller
  adds is context the executor cannot see: a sibling milestone rewriting
  the same path, an owner's ruling, a contradiction in the spec. An
  executor cannot ask for what it does not know exists, so verdicts still
  reach the controller.
- The implementer writing its own reviewer's brief is where independence
  leaks: five briefs argued for the code or fenced off part of the diff.
  The executor's brief is therefore a fixed recipe of paths, and its
  reasoning goes in the report the reviewer reads as claims.
- The executor already carries the task: its median final context was
  308k against the plan-executor's 274k during review handling. Token
  cost is roughly unchanged (the review loop was about a quarter of the
  plan-executor's calls, and the executor now makes the packaging and
  re-review calls instead); the gain is a simpler loop — deferred
  reviews, checkout lines, fix ranges and reviewer handles leave the
  controller's skill.

## Costs accepted

- **Throughput.** An executor holds the shared checkout until its review
  is clean. Under the old loop, 48% of executor dispatches overlapped an
  in-flight task review, about 152 of 777 in the same checkout. Those
  milestones now wait a review round first: median 8 minutes for a first
  round, about 6 for each re-review. Milestones in worktrees of their own
  are unaffected; the parallel-milestones design (2026-09-27, unexecuted)
  is where overlap within one plan would come back.
- **One extra message per dispatch.** A subagent has no address for its
  dispatcher until the dispatcher messages it (friction tracker #304), so
  the controller messages each executor once after dispatching it.
- **A fresh reviewer per round.** A re-review is a new foreground
  dispatch, briefed with the fix package and the previous round's report,
  not a resume of the reviewer that already holds the task: it re-reads
  the spec each round (rounds per task in the old loop: median 2).

## Rules that carry a reason

- The executor's brief to its reviewer is exactly the spec and milestone,
  the report file, the package, BASE and HEAD (the 5/48 above).
- A finding the executor disputes, or one that conflicts with the spec,
  returns to the controller; the author does not settle it.
- A fix the reviewer rejects twice returns DONE_WITH_CONCERNS: the
  old loop's sign that the executor's frame is the problem (rounds per
  reviewer in the corpus: 1: 173, 2: 200, 3: 94, 4+: 43).
- `SendMessage` to `main` from a nested agent reaches the top session (18
  executor messages did, skipping their plan-executor), so the executor
  uses the address the controller's message carries.
- The executor dispatches its reviewer in the foreground and repeats a
  review by a fresh dispatch. In the first live run an executor resumed
  its finished reviewer with `SendMessage` and ended its turn to wait; the
  engine told it to hand back 12 s later, and the reviewer's report went
  to the top session, twice (friction tracker #304, the
  `[handback-send-enforce]` row).
- The controller dispatches each executor in the background. In the first
  live run it chose the foreground for two of three, which left it unable
  to send the address message or read a verdict until the executor
  returned.

## Verification

Live runs of a three-milestone spec (slugify, unique slugs, a CLI; each
consumes the last) in a throwaway repository, through
`claude -p --plugin-dir <this worktree>` with the installed plugin
turned off, the design session dispatching one plan-executor:

- **Run 1** (definitions at f15aded1): every milestone built and
  reviewed clean (M1 in two rounds), 53/53 tests, the Purpose's example
  exact. Every reviewer brief carried only paths, at the pin. The
  re-review broke as described above, and the plan-executor dispatched in
  the foreground; the M1 executor found its controller's id through
  `ListAgents` and its verdicts arrived. Both fixed in e5300304.
- **Run 2**: pending.

## Open

- Codex: the ports carry the same contract, but whether Codex lets a
  spawned agent spawn one beneath it at this depth was not run.
