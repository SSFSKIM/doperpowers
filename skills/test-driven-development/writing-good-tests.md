# Writing Good Tests

A test exists to catch a specific break. Two principles govern everything
here: every test names the break it catches, and every test exercises the
real thing. Strict TDD produces both naturally — a test written first and
watched failing against real code has already proven it can fail, and only
earns a mock when the real dependency proves slow or external.

## Rules a capable reader still gets wrong

**Behavior, not text.** Asserting that a script, skill, or config contains
an exact line proves only that the source is the source. Run scripts
against controlled inputs and assert outputs, side effects, or exit codes.
Documents that instruct agents are tested by the consuming agent's
behavior (doperpowers:writing-skills); prose for humans earns no test at all.

**No change detectors.** If only intentional decisions can fail a test — a
constant's value, exact message wording, private structure — it fires on
redesign and sleeps through bugs. Test the behavior that depends on the
decision: not `MAX_RETRIES == 5` but "a failing call is retried 5 times and
the 6th attempt never happens."

**Your code, not the framework.** Test the contract your code makes at its
boundaries — the route you register, the query you emit, the payload you
produce. Upstream mechanics are their maintainers' tests to write. When
upstream behavior genuinely surprised you, write one narrow
characterization test naming the assumption.

**Mirror real data completely.** A mock response carries every documented
field, not just the ones this test reads. Partial mocks pass while
integration breaks on the omitted field.

**Production classes carry production methods only.** Cleanup only tests
need lives in test utilities, never as a `destroy()` on the production
class. A method called only from test files is in the wrong place.

## Quick reference

| When you... | Do |
|-------------|-----|
| Write any test | Name the break it catches — a bug, not a decision |
| Build an expected value | Derive it by hand; never with the code under test |
| Test a script or document | Run it / pressure-test its consumer; never grep its text |
| Reach for a dependency test | Test your boundary contract, not their documented mechanics |
| Want to assert on a mocked element | Test the real component, or unmock it |
| Are about to mock a method | Learn its side effects; mock the slow/external level below them |
| Build a mock response | Mirror the real structure completely |
| Need cleanup only tests use | Put it in test utilities |
| Watch mock setup balloon | Switch to an integration test with real components |
| Finish a test file | Mutate the production code in your head — wrong constant, wrong branch, missing side effect, empty return, missing validation — and confirm a test fails for each |

## Warning signs

- Setup and assertion share the same object, guaranteeing equality
- The test can fail only through a panic, crash, or missing selector
- The test fails on every intentional change, never on accidental breakage
- Expected values are hidden behind loops, builders, or helpers
- The test greps source text, or asserts a removed symbol stays removed
- The test would still matter if only the framework remained
- The test exists for coverage, checking no side effect or outcome
- An assertion checks a `*-mock` test ID, or fails if you remove the mock
- A method is called only from test files
- Mock setup is more than half the test, or you can't explain why the mock is needed
