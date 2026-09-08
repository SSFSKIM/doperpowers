#!/usr/bin/env bash
# Regression check: Doperpowers should not route new worktrees through the old
# global worktree directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WORKSPACE_REF="$REPO_ROOT/skills/subagent-driven-execution/isolated-workspace.md"
ROTOTILL_SPEC="$REPO_ROOT/docs/doperpowers/specs/2026-04-06-worktree-rototill-design.md"
ROTOTILL_PLAN="$REPO_ROOT/docs/doperpowers/plans/2026-04-06-worktree-rototill.md"

failures=0

assert_contains() {
    local file="$1"
    local pattern="$2"
    local label="$3"

    if grep -Fq "$pattern" "$file"; then
        echo "  [PASS] $label"
    else
        echo "  [FAIL] $label"
        echo "    Expected to find: $pattern"
        echo "    In file: $file"
        failures=$((failures + 1))
    fi
}

assert_not_contains() {
    local file="$1"
    local pattern="$2"
    local label="$3"

    if grep -Fq "$pattern" "$file"; then
        echo "  [FAIL] $label"
        echo "    Did not expect to find: $pattern"
        echo "    In file: $file"
        failures=$((failures + 1))
    else
        echo "  [PASS] $label"
    fi
}

echo "=== Worktree Path Policy Test ==="
echo ""

assert_not_contains "$WORKSPACE_REF" "~/.config/doperpowers/worktrees" "isolated-workspace does not mention old global path"
assert_not_contains "$WORKSPACE_REF" "global legacy" "isolated-workspace does not use unclear global legacy shorthand"
assert_contains "$WORKSPACE_REF" '`git worktree add .worktrees/<branch>' "isolated-workspace defaults new manual worktrees to .worktrees/"
assert_contains "$WORKSPACE_REF" '`.worktrees/` or `worktrees/`' "isolated-workspace keeps project-local cleanup ownership"

assert_not_contains "$ROTOTILL_SPEC" "~/.config/doperpowers/worktrees" "rototill spec does not preserve old global path policy"
assert_not_contains "$ROTOTILL_PLAN" "~/.config/doperpowers/worktrees" "rototill plan does not preserve old global path policy"
assert_not_contains "$ROTOTILL_PLAN" "legacy path compat" "rototill plan does not advertise legacy path compatibility"

echo ""

if [ "$failures" -gt 0 ]; then
    echo "STATUS: FAILED ($failures failures)"
    exit 1
fi

echo "STATUS: PASSED"
