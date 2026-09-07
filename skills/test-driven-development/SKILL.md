---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
---

# Test-Driven Development (TDD)

Write the test first. Watch it fail. Write minimal code to pass.

Any change with testable behavior: features, bugfixes, refactoring.
Throwaway prototypes, generated code, and configuration are out; judge
the boundary yourself and name the call when it is genuinely ambiguous.

**Watch the failure.** Run the new test before writing implementation and
read why it failed: it must fail because the behavior is missing, not
from a typo or setup error. A test whose failure you never saw may pass
for reasons unrelated to your code — it proves nothing. This one step is
the discipline; everything else is ordinary good engineering.

**Then minimal code to pass, then clean up on green.** Just enough for
this test, nothing speculative. When the test fails after implementation,
the default suspect is the code: the test records intent you settled
before implementing. Rewrite the test only if that intent was wrong.

**Implementation already written?** Set it aside and let tests drive a
fresh version. Tests written to fit existing code inherit its blind spots
and pass immediately, so they never demonstrate they can catch anything.
The time is spent either way; what you choose now is whether the tests
can be trusted.

**A bug fix starts with a test that reproduces the bug** — it proves the
fix and pins it against regression.

When writing or changing any test, read
[writing-good-tests.md](writing-good-tests.md): name the production
change that would make the test fail before writing it, assert on real
behavior rather than mock behavior, and keep test-only code out of
production classes.
