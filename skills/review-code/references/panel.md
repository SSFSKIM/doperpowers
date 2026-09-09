# The review workflow: contract and findings doctrine

`workflows/code-review.js` is one script with one routing input, `level`.
xhigh and max run the panel. Low, medium, and high run a single reviewer at
the same model and effort as the registered `doperpowers:reviewer-<level>`
agents — the direct Agent dispatch is the normal path for those rungs; the
workflow form exists for a structured result from the main session and for
the benchmark. Both shapes return the same object.

## Args

Required: `level`, `base`, `baseCommit` (`git merge-base <base> HEAD`),
`headCommit` (`git rev-parse HEAD`). The script cannot run git, so the caller
pins the range; every prompt names both commits and the diff command is
`git diff <mb> <head>`.

Optional:

- `repo` — absolute path of the checkout under review when it is not the
  session's cwd (a worktree). Shell-quoted into every command.
- `lens` — one scalpel mandate for a single-reviewer level, at most two plain
  sentences naming one structural risk surface.
- `lenses` — an array replacing the panel's derived scalpel set (fixes the
  finder count: sweep + one per lens).
- `maxLenses` — cap on derived scalpels, at most 5.
- `finderAgent` — agent type for every reviewer (default
  `doperpowers:reviewer-medium`; the registered reviewers share one body, and
  the rung's model and effort override the agent's own pin per call).
- `deriverModel`/`deriverEffort`, `finderModel`/`finderEffort`,
  `verifierModel`/`verifierEffort` — per-lane overrides of the level's ladder.

## The ladder

| Level | Shape | Deriver | Finders | Verifier |
|---|---|---|---|---|
| low | single | – | sol / high | – |
| medium | single | – | sol / xhigh | – |
| high | single | – | astra / high | – |
| xhigh | panel | sol / high | sol / xhigh | sol / xhigh |
| max | panel | sol / xhigh | astra / high | astra / high |

Sol at xhigh is the rung the X1 benchmark baseline was scored on, and the
medium rung reproduced it exactly (17/17, FP 0, `tests/review-bench/results/
2026-09-09-native-x1`). The verifier never runs below its finders. Known
tendency of xhigh: Sol finders raise intent-documented design choices as
candidates and the Sol verifier confirms them (two such FPs on the seeded
set; the astra panel at max raised none) — weigh an xhigh finding against the
change's stated intent before acting on it.

## The panel

One lens deriver reads the diff and writes zero to five scalpel mandates (a
mandate must earn its slot; a small single-concern diff gets zero or one). One
lens-free sweep plus one reviewer per mandate run concurrently, each returning
structured findings. One binding verifier re-inspects every candidate, marks
duplicates, and rules CONFIRMED or REFUTED; its verdict set is checked
mechanically (one verdict per candidate, a duplicate graph that resolves) with
one repair round. Expect six to seven agents and five to ten minutes.

## Isolation

Without `repo`, every stage runs in a fresh worktree at HEAD: reviewers read
committed content, and nothing they run can touch the session's working tree.
With `repo` set that isolation does not apply, so point it at an untouched
checkout. The agents also exclude the mutating tools — the only guarantee a
direct Agent dispatch of a reviewer has.

## Result

```
{ verdict, findings, coverage, lenses, explanation, target, level, pool? }
```

- `verdict` — `correct` (no confirmed defect and nothing lost), `incorrect`
  (confirmed defects), or `interrupted` (no verdict about this diff can be
  asserted).
- `findings` — priority-sorted `{id, priority, title, file, lines, comment,
  sources}`. On panel levels only verifier-confirmed items, deduplicated, with
  `sources` naming every lane that independently raised it; on single levels
  the reviewer's own findings.
- `coverage` — one row per lane: `{finder, lens, status: ok|dead, candidates}`.
- `interrupted` means the sweep, the verifier, or the single reviewer was lost,
  or a lane died where a clean verdict would otherwise have been claimed.
  Confirmed findings still ride along as partial evidence; an unjudged
  candidate pool is attached raw as `pool` rather than dropped.

When the run returns, re-resolve the merge-base and HEAD: if either moved, the
verdict describes a diff that no longer exists — read it as `interrupted`.

## Working with findings

A review is rigorous by design, so not every finding is action-worthy, and
verifying one means more than checking whether it is real. A finding that is
real but too small to act on now is logged as tech debt, not fixed inline. One
that contradicts the design's intent is dismissed; one that fits the purpose
but was deliberately scoped out is deferred to the backlog. What remains goes
to a fix wave through a subagent, not your own edits, and a re-review follows a
substantial wave. Several rounds are fine; a round that yields only logged debt
and dismissals is the signal the review has converged — stop there.
