#!/usr/bin/env bash
# Test runner for Claude Code skills
# Tests skills by invoking Claude Code CLI and verifying behavior
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo " Claude Code Skills Test Suite"
echo "========================================"
echo ""
echo "Repository: $(cd ../.. && pwd)"
echo "Test time: $(date)"
echo "Claude version: $(claude --version 2>/dev/null || echo 'not found')"
echo ""

# Check if Claude Code is available
if ! command -v claude &> /dev/null; then
    echo "ERROR: Claude Code CLI not found"
    echo "Install Claude Code first: https://code.claude.com"
    exit 1
fi

# Parse command line arguments
VERBOSE=false
SPECIFIC_TEST=""
TIMEOUT=900  # Per-test-file budget; must exceed the file's worst case
             # (test-subagent-driven-execution.sh: 9 prompts x 90s each)
RUN_INTEGRATION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --test|-t)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --integration|-i)
            RUN_INTEGRATION=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --verbose, -v        Show verbose output"
            echo "  --test, -t NAME      Run only the specified test"
            echo "  --timeout SECONDS    Set timeout per test (default: 900)"
            echo "  --integration, -i    Run integration tests (slow, 10-30 min)"
            echo "  --help, -h           Show this help"
            echo ""
            echo "Tests:"
            echo "  test-subagent-driven-execution.sh  Test skill loading and requirements"
            echo "  board-api/test-*.sh                  A2 board-API toolkit suites (fixture mock)"
            echo "  board-api/integration/test-*.sh      A2 vs. a real A1 service (needs \$ARKHO_DIR)"
            echo ""
            echo "Integration Tests (use --integration):"
            echo "  test-subagent-driven-execution-integration.sh  Full workflow execution"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# List of skill tests to run (fast unit tests)
tests=(
    "test-worktree-path-policy.sh"
    "test-sde-workspace.sh"
    "test-subagent-driven-execution.sh"
    # board-api (A2): hermetic and fast — every suite below drives the toolkit's
    # verbs against the fixture mock in board-api/mock-server.py, no network and
    # no gh. They ran only by hand until this list picked them up.
    "board-api/test-binding.sh"
    "board-api/test-client-core.sh"
    "board-api/test-read-verbs.sh"
    "board-api/test-register-transition.sh"
    "board-api/test-edge-verbs.sh"
    "board-api/test-comment.sh"
    "board-api/test-answer.sh"
    "board-api/test-bind.sh"
    "board-api/test-dispatch-claim.sh"
    "board-api/test-review-dispatch-claim.sh"
    "board-api/test-sweep-renew-relay.sh"
    "board-api/test-sweep-resume.sh"
    # The integration tier carries its OWN gate rather than living under
    # --integration: it needs $ARKHO_DIR plus a container runtime for the
    # scratch Postgres, and skips loudly (exit 0) when either is missing. On a
    # machine that has them the smoke test is ~20s and the six fast drills are
    # ~30s each — each boots and tears down its own scratch database, so they
    # are independent in any order. test-lease-renewal.sh is the outlier at
    # ~4 minutes: its subject IS the clock (A1's write-freshness window is 120s
    # and not configurable), so it cannot be made shorter without ceasing to
    # drill what it drills.
    "board-api/integration/test-harness-smoke.sh"
    "board-api/integration/test-protocol-walk.sh"
    "board-api/integration/test-transcript-diff.sh"
    "board-api/integration/test-crash-boundaries.sh"
    "board-api/integration/test-resume-first.sh"
    "board-api/integration/test-escalation.sh"
    "board-api/integration/test-human-verbs.sh"
    "board-api/integration/test-lease-renewal.sh"
    # qa-loops: the suites in tests/qa-loops/ are hand-run (the spec's
    # acceptance invokes them as a glob). The bootstrap parity fence is listed
    # here because it is hermetic and sub-second — no dispatcher, no gh, no
    # ports, just the two bootstrap templates rendered in-process.
    "../qa-loops/test-bootstrap-parity.sh"
)

# Integration tests (slow, full execution)
integration_tests=(
    "test-subagent-driven-execution-integration.sh"
)

# Add integration tests if requested
if [ "$RUN_INTEGRATION" = true ]; then
    tests+=("${integration_tests[@]}")
fi

# Filter to specific test if requested
if [ -n "$SPECIFIC_TEST" ]; then
    tests=("$SPECIFIC_TEST")
fi

# Track results
passed=0
failed=0
skipped=0

# Run each test
for test in "${tests[@]}"; do
    echo "----------------------------------------"
    echo "Running: $test"
    echo "----------------------------------------"

    test_path="$SCRIPT_DIR/$test"

    if [ ! -f "$test_path" ]; then
        echo "  [SKIP] Test file not found: $test"
        skipped=$((skipped + 1))
        continue
    fi

    if [ ! -x "$test_path" ]; then
        echo "  Making $test executable..."
        chmod +x "$test_path"
    fi

    start_time=$(date +%s)

    if [ "$VERBOSE" = true ]; then
        if timeout "$TIMEOUT" bash "$test_path"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo ""
            echo "  [PASS] $test (${duration}s)"
            passed=$((passed + 1))
        else
            exit_code=$?
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo ""
            if [ $exit_code -eq 124 ]; then
                echo "  [FAIL] $test (timeout after ${TIMEOUT}s)"
            else
                echo "  [FAIL] $test (${duration}s)"
            fi
            failed=$((failed + 1))
        fi
    else
        # Capture output for non-verbose mode
        if output=$(timeout "$TIMEOUT" bash "$test_path" 2>&1); then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo "  [PASS] (${duration}s)"
            # A gated tier that skipped exits 0 like a pass. Non-verbose mode
            # captures output and only prints it on failure, which would turn
            # every skip into a silent pass — so surface the reason it printed.
            grep '^SKIP' <<<"$output" | sed 's/^/    /' || true
            passed=$((passed + 1))
        else
            exit_code=$?
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            if [ $exit_code -eq 124 ]; then
                echo "  [FAIL] (timeout after ${TIMEOUT}s)"
            else
                echo "  [FAIL] (${duration}s)"
            fi
            echo ""
            echo "  Output:"
            echo "$output" | sed 's/^/    /'
            failed=$((failed + 1))
        fi
    fi

    echo ""
done

# Print summary
echo "========================================"
echo " Test Results Summary"
echo "========================================"
echo ""
echo "  Passed:  $passed"
echo "  Failed:  $failed"
echo "  Skipped: $skipped"
echo ""

if [ "$RUN_INTEGRATION" = false ] && [ ${#integration_tests[@]} -gt 0 ]; then
    echo "Note: Integration tests were not run (they take 10-30 minutes)."
    echo "Use --integration flag to run full workflow execution tests."
    echo ""
fi

if [ $failed -gt 0 ]; then
    echo "STATUS: FAILED"
    exit 1
else
    echo "STATUS: PASSED"
    exit 0
fi
