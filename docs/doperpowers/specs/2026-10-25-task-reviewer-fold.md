# Retiring task-reviewer: frontier reviews go to the review-code rungs

> **Status:** decided 2026-10-25 by the owner ("eval, then fold"), on the
> replay below. Ships in doperpowers 7.206.0.

## Decision

`doperpowers:task-reviewer` is retired. subagent-driven-execution's
frontier reviews dispatch `doperpowers:reviewer-medium` by default, or the
rung the spec's verification entry names for its milestones. The reviewer
agents gain a `## Requirements` section: when the brief names a spec, a
milestone, or other requirements, a requirement left unbuilt, built
differently, or work not asked for is a finding. The SDE controller
adjudicates findings the way review-code's "Working with findings" does
(holds the task → back to the executor; real but small → ledger), in
place of task-reviewer's Critical/Important/Minor routing.

## Why

- task-reviewer ran the same model and effort as reviewer-medium
  (sol/xhigh); the two differed only in contract.
- Sessions were already overriding it: in 7 of 118 multi-milestone
  plan-executor runs (2026-09-21 → 10-25) the main session's brief sent
  every milestone review to a reviewer rung, and in the week of 10-19
  plan-executors dispatched 136 task-reviewer and 126 reviewer-rung
  reviews. Two contracts for one job meant two severity scales in one run.
- One contract is one place to tune, one Codex port, and a rung choice per
  milestone instead of a fixed pin.

## The replay

Ten historical milestone reviews whose task-reviewer report had raised
Critical or Important findings (6 MAWS, 2 sminos in this repo, 2
manim-master), commits still present. Each was re-run on a detached
worktree at the task's HEAD with its original dispatch brief, the review
package regenerated, the executor report unavailable to both arms:
reviewer-medium with the Requirements paragraph in the brief, and a fresh
task-reviewer as the baseline. A finding counted as caught when the run
named the same defect (same root cause at the same site).

| | reviewer-medium | task-reviewer (fresh) |
|---|---|---|
| Original findings caught | 12 / 26 | 14 / 26 |
| The two Criticals | both, tagged P1 | both, downgraded to Important |
| Cases where it caught more | 1 (by 2) | 4 (by 1 each) |
| Tokens, ten runs | 1.93M (one run 640k) | 1.38M |

Run-to-run variance dominates: task-reviewer re-found 54% of its own
earlier findings on identical inputs. Where task-reviewer led, the
findings were requirement and test-strength ones (a schema weaker than its
contract, a title rule the spec spells out, a test comparing only process
identity); reviewer-medium with the Requirements paragraph caught the
never-built startup requirement and the unasserted memory cross-check, and
reported more new runtime defects. The result showed no quality loss large
enough to keep a second contract; the lean on spec checks is the thing to
watch.
