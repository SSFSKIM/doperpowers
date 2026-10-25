# task-reviewer kept: a three-arm replay of milestone reviews

> **Status:** decided 2026-10-25 by the owner. `doperpowers:task-reviewer`
> stays as subagent-driven-execution's frontier reviewer; the fold into
> the review-code rungs (PR #369) was closed unmerged.

## Question

task-reviewer runs the same model and effort as `reviewer-medium`
(sol/xhigh) and differs only in its contract, and dispatching sessions
had begun overriding it with the reviewer rungs. Does its contract earn
its place, or should frontier reviews go to the rungs?

## Method

Ten historical frontier reviews whose task-reviewer report raised
Critical or Important findings, commits still present: six MAWS
milestones, two sminos milestones from this repository, two
manim-master tasks. Each was replayed on a detached worktree at the
task's HEAD with its original dispatch brief and a regenerated review
package; the executor reports and `.doperpowers/sde/` briefs no longer
existed, so no arm had them. Three arms, one run per case:

- **task-reviewer**, fresh;
- **reviewer-medium**, with a candidate Requirements paragraph (a
  requirement left unbuilt or built differently is a finding) in the
  brief;
- **plain `sol-xhigh`**, a general subagent with no reviewer system
  prompt, its brief adding one line to leave the checkout unchanged
  (it holds edit tools). None of its runs delegated; every checkout was
  clean afterwards.

The answer key is the original report's 26 Critical/Important findings.
A finding counts as recovered when a run names the same defect (same
root cause at the same site); a related defect at another site does not
count.

## Result

| | task-reviewer | plain sol-xhigh | reviewer-medium |
|---|---|---|---|
| Original findings recovered | 14 / 26 | 14 / 26 | 12 / 26 |
| Recovered by this arm alone | 1 | 2 | 0 |
| Tokens, ten runs | 1.38M | 1.68M | 1.93M (one run 640k) |
| Mean wall time per review | 7.2 min | 12.2 min | 8.0 min |
| The two Criticals | recovered, rated Important | recovered, P1 | recovered, P1 |

- **The contract is not where recall comes from.** Same model, same
  effort, three different system prompts, recall within two findings;
  the controller's brief (spec, milestone, named risks) carries most of
  the review's direction.
- **Each pass samples.** task-reviewer re-found 54% of its own earlier
  findings on identical inputs, and the three fresh arms together
  recovered 18 of 26 against at most 14 for any one. Half the cases
  were 1.5k–4.3k changed lines over 13–43 files, at or over
  review-code's panel threshold; on the two most-reviewed of them each
  run reported 4–6 findings while the four runs together (the original
  and the three arms) found 10 and 12 distinct defects. Recall on a
  large milestone is a function of the number of independent passes, which
  matches the 2026-07-27 real-PR bench
  (`2026-07-26-claude-review-stack-roadmap.md`, "X1 parity does not
  transfer to large real diffs").
- **The plain arm verifies by running code.** It recovered the two
  findings both reviewer arms missed (on the two smallest diffs) and
  reproduced most findings with probes, at the highest wall time.
- **task-reviewer's contract buys efficiency at equal recall:** reading
  the package once, not crawling the codebase, and not re-running suites
  kept every run between 88k and 198k tokens and made it the fastest
  arm. That is the reason it stays.

A transcript count corrected along the way: most task-reviewer reports
arrive through the hand-back tool, not a text block. Counted with those,
422 of 688 reports (2026-09-21 → 10-25) list spec-compliance issues and
460 ask for fixes.

## Open

Fanning a panel-sized milestone review out to several lensed passes,
from inside plan-executor (which has no Workflow tool for the panel),
is the lever these numbers point to. Deferred by the owner on
2026-10-25.
