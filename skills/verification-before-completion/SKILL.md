---
name: verification-before-completion
description: Use when about to claim work is complete, fixed, or passing — before committing, creating PRs, or expressing any success.
---

# Verification Before Completion

A completion claim is a factual report — it is honest only if evidence
backs it. This covers every expression of success, not just the literal
words: "should work now" and "great, that fixes it" are claims too.

**Core principle:** before stating success, ask what would prove it, run
that, and read the output. Then speak.

Two judgments calibrate the work:

- **Freshness.** Evidence is fresh while nothing relevant has changed
  since it was produced. A test run from before your last edit proves
  nothing about the current state; a run nothing has invalidated needs
  no ritual re-run.
- **Scope.** Match verification to the claim. A one-line fix is proven
  by its covering tests; "the branch is ready" is proven by the whole
  suite. Claim only what your evidence covers.

## What counts as evidence

| Claim | Evidence | Commonly mistaken for evidence |
|-------|----------|-------------------------------|
| Tests pass | fresh run, zero failures | an earlier run, "should pass" |
| Bug fixed | the original symptom re-tested | code changed, fix assumed |
| Regression test works | red-green: revert the fix → test fails; restore → passes | the test passing once |
| Subagent finished | the diff / the artifact itself | the agent's "success" report |
| Requirements met | the plan or spec walked item by item | tests passing |

When verification fails, report the actual state with the output. A
truthful "not done yet" costs a turn; a false "done" costs the trust the
next claim needs.
