# The review workflow: contract and findings doctrine

`workflows/code-review.js` has one routing input, `level`. xhigh and max run
the panel; low, medium, and high run one reviewer at the registered agent's
model and effort (a structured-result form of the direct dispatch, used by
the benchmark). Both shapes return the same object.

## Args

Required: `level`, `base`, `baseCommit` (`git merge-base <base> HEAD`),
`headCommit` (`git rev-parse HEAD`). The caller pins the range; every prompt
names both commits and diffs `<mb> <head>`.

Optional:

- `repo` — absolute path of the checkout under review when it is not the
  session's cwd (a worktree). Shell-quoted into every command.
- `lens` — one scalpel mandate for a single-reviewer level.
- `lenses` — an array replacing the panel's derived scalpel set (sweep + one
  reviewer per lens).
- `maxLenses` — cap on derived scalpels, at most 5.
- `finderAgent` — agent type for every reviewer (default
  `doperpowers:reviewer-medium`; the rung's model and effort override its pin).
- `deriverModel`/`deriverEffort`, `finderModel`/`finderEffort`,
  `verifierModel`/`verifierEffort` — per-lane overrides of the ladder.

## The ladder

| Level | Shape | Deriver | Finders | Verifier |
|---|---|---|---|---|
| low | single | – | sol / high | – |
| medium | single | – | sol / xhigh | – |
| high | single | – | astra / high | – |
| xhigh | panel | sol / high | sol / xhigh | sol / xhigh |
| max | panel | sol / xhigh | astra / high | astra / high |

Medium reproduced the codex baseline exactly on the X1 seeded set (17/17,
FP 0; `tests/review-bench/results/2026-09-09-native-x1`). Known tendency of
xhigh: Sol finders raise intent-documented design choices and the Sol
verifier confirms them (two such FPs on the seeded set; max raised none) —
weigh an xhigh finding against the change's stated intent.

## The panel

A lens deriver reads the diff and writes zero to five scalpel mandates (a
mandate must earn its slot). A lens-free sweep plus one reviewer per mandate
run concurrently, each returning structured findings. One binding verifier
re-inspects every candidate, marks duplicates, and rules CONFIRMED or REFUTED;
its verdict set is checked mechanically (one verdict per candidate, a
duplicate graph that resolves) with one repair round. Six to seven agents,
five to ten minutes.

## Isolation

Without `repo`, every stage runs in a fresh worktree at HEAD: reviewers read
committed content, and nothing they run can touch the session's working tree.
With `repo` set that isolation does not apply, so point it at an untouched
checkout. The agents themselves only exclude the mutating tools.

## Result

```
{ verdict, findings, coverage, lenses, explanation, target, level, pool? }
```

- `verdict` — `correct` (no confirmed defect, nothing lost), `incorrect`
  (confirmed defects), or `interrupted` (no verdict about this diff can be
  asserted: the sweep, the verifier, or the single reviewer was lost, or a
  lane died where a clean verdict would otherwise have been claimed).
- `findings` — priority-sorted `{id, priority, title, file, lines, comment,
  sources}`; on panel levels only verifier-confirmed items, deduplicated, with
  `sources` naming every lane that raised it.
- `coverage` — one row per lane: `{finder, lens, status: ok|dead, candidates}`.
- On `interrupted`, confirmed findings still ride along as partial evidence,
  and an unjudged candidate pool is attached raw as `pool`.

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
