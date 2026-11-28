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

**Pin real data whole when the answer is known by example.** When correctness
is "this real input produces this output" rather than a rule you can state — a
parser over real exports, a renderer, a report — the real captured input is the
fixture and its complete output is the expectation. A row count or a
first-and-last spot check leaves the middle rows unpinned, and the middle row
is the one that breaks. Deriving that expectation by hand means reading it,
however it was produced: check every line against the input before committing,
and accept a regeneration only after reading its diff. Minimal hand-built
inputs still belong beside it, one per quirk, so a failure names its cause.

**Production classes carry production methods only.** Cleanup only tests
need lives in test utilities, never as a `destroy()` on the production
class. A method called only from test files is in the wrong place.

## Also

- Build an expected value by hand, never with the code under test or a
  helper that shares its logic: a value derived from the code agrees with
  it by construction.
- Mock the slow or external level below a method, once you know the
  method's side effects, rather than the method itself; an assertion on a
  mocked element tests the mock. When mock setup outgrows the test, an
  integration test with real components is the better test.
- Finishing a test file, mutate the production code in your head — wrong
  constant, wrong branch, missing side effect, empty return, missing
  validation — and confirm a test fails for each.
