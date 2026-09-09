---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

You already know how to debug: read the whole error, reproduce, check what
changed, compare against code that works, one hypothesis at a time, the
smallest change that tests it. This skill is not that method. It is the
three rules that hold when the pull to skip the method is strongest.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

A fix proposed before the failure is reproduced and its cause traced to
where the bad value or state originates is a guess, however obvious it
looks. Guessing is slower than investigating: a wrong guess costs the
investigation anyway, plus the guess. This holds hardest exactly when it is
most tempting to drop it: production is down, the fix is "two minutes", the
bug looks too simple to need process. Simple bugs have root causes too.

Fix at the source, not where the symptom surfaces. Before the fix, write the
failing reproduction (doperpowers:test-driven-development); after it,
verify the original symptom is gone, not just that the tests pass.

## Three strikes: question the architecture

Count your fix attempts. A failed fix returns you to investigation with the
new evidence, not to a second fix stacked on the first. At three failed
fixes, stop. When each fix exposes a new symptom somewhere else, or every
fix seems to need a large refactor, the hypothesis is not what is wrong; the
design is. Bring that to your human partner before attempting a fourth.
This is not a failed hypothesis. It is the wrong architecture.

## "No root cause"

An issue that is truly environmental, timing-dependent, or external is a
finding you can only make after the investigation, and it earns handling
(retry, timeout, a clear error) plus logging for the next time. Reached
early, it is almost always an incomplete investigation.

## Red Flags - STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals new problem in different place**

**ALL of these mean: STOP. Return to investigation.**

## Tools in this directory

- **`condition-based-waiting.md`** — a flaky test that sleeps: wait for the
  condition instead of guessing its duration.
- **`find-polluter.sh <path-to-check> <test-glob>`** — bisects a test suite
  to find which test leaves the file or state behind.
