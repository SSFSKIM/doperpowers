---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
---

# Test-Driven Development (TDD)

Write the test first. Watch it fail. Write minimal code to pass.

**Core principle:** If you didn't watch the test fail, you don't know if it
tests the right thing. A test you never saw fail may pass for reasons
unrelated to your code — it proves nothing.

## Where it applies

Any change with testable behavior: features, bugfixes, refactoring. It does
not apply to throwaway prototypes, generated code, or configuration. Judge
the boundary yourself; when a case is genuinely ambiguous, name the call
you made.

## The cycle

**RED — write one failing test.** One behavior, named for that behavior,
asserting on real code (mock only what you cannot avoid). Run it and read
the failure: it must fail because the feature is missing, not from a typo
or setup error. This verification is the heart of the discipline — a test
whose failure you never saw is the one that silently tests nothing.

**GREEN — minimal code to pass.** Just enough for this test; nothing
speculative beyond it. Run the test, then the suite: everything green,
output clean. When the test fails, the default suspect is the code — the
test records intent you settled before implementing; rewrite the test only
if that intent was wrong.

**REFACTOR — clean up on green.** Duplication, names, helpers. No new
behavior; the suite stays green.

Repeat: next behavior, next failing test.

## Why test-first, not test-after

A test written after the code passes immediately, so it never demonstrates
it can catch the bug it guards against. It answers "what does this code
do?" — biased by the implementation you already wrote — where a test
written first answers "what should this do?" You cover the cases you
remembered, not the ones writing the test would have forced you to discover.

## If implementation already exists

When you notice you've written implementation before its test, set it
aside and let tests drive a fresh version — tests written to fit existing
code inherit its blind spots. The time spent is spent either way; what
you're choosing now is whether the tests can be trusted.

## Test quality

When writing or changing any test, read [writing-good-tests.md](writing-good-tests.md)
for the rules that keep tests honest:
- Name the production change that would make the test fail — before writing it
- Assert on real behavior, never on mock behavior
- Keep test-only code in test utilities, out of production classes
- Understand a dependency's side effects before mocking it

## When stuck

| Problem | Signal |
|---------|--------|
| Don't know how to test | Write the wished-for API; write the assertion first. |
| Test too complicated | The design is too complicated. Simplify the interface. |
| Must mock everything | The code is too coupled. Inject dependencies. |
| Test setup huge | Extract helpers. Still huge? Simplify the design. |

## Bug fixes

A fix starts with a failing test that reproduces the bug — the test proves
the fix and pins it against regression.
