#!/usr/bin/env bash
#
# Hermetic tests for the tick-scoped snapshot cache (BOARD_SNAPSHOT_CACHE).
#
# The dispatch sweep re-verifies every queued candidate in a fresh python
# process; uncached, that cost O(queue) full-board GraphQL sweeps per tick
# and starved every later pass of quota. These tests pin the cache contract:
# opt-in via env, TTL-bounded, refresh bypasses AND rewrites, deleting the
# file is the invalidation path, and a sweep over a deep queue with full
# lanes performs exactly ONE GraphQL fetch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_equals() {
    if [ "$1" = "$2" ]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}

# ---- environment --------------------------------------------------------------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export MOCK_GH_STATE="$TEST_ROOT/gh-state.json"
export MOCK_GH_LOG="$TEST_ROOT/gh-log.jsonl"
export BOARD_REPO="test/repo"
export BOARD_SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"
export PATH="$SCRIPT_DIR/mock-gh:$PATH"

seed_board() {
    rm -f "$MOCK_GH_STATE"
    "$BOARD_SCRIPTS/board-register.sh" "seed ticket $1" bug P2 >/dev/null
}

graphql_calls() {
    grep -c '"graphql"' "$MOCK_GH_LOG" 2>/dev/null || true
}

snapshot_once() {  # one fresh python process; prints ticket count
    BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
print(len(B.snapshot()))
PY
}

snapshot_refresh() {
    BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
print(len(B.snapshot(refresh=True)))
PY
}

echo "== snapshot cache: opt-in, TTL, refresh, invalidation =="
seed_board 1

# 1. Without the env: every process fetches.
unset BOARD_SNAPSHOT_CACHE || true
: > "$MOCK_GH_LOG"
snapshot_once >/dev/null
snapshot_once >/dev/null
assert_equals "$(graphql_calls)" "2" "no env → two processes fetch twice (opt-in only)"

# 2. With the env: second process reads the file, no second fetch.
export BOARD_SNAPSHOT_CACHE="$TEST_ROOT/snap.json"
rm -f "$BOARD_SNAPSHOT_CACHE"
: > "$MOCK_GH_LOG"
n1="$(snapshot_once)"
n2="$(snapshot_once)"
assert_equals "$(graphql_calls)" "1" "cache env → two processes, one fetch"
assert_equals "$n2" "$n1" "cached read returns the same board"
[ -s "$BOARD_SNAPSHOT_CACHE" ] && pass "fetch wrote the cache file" || fail "fetch wrote the cache file"

# 3. Deleting the file invalidates.
rm -f "$BOARD_SNAPSHOT_CACHE"
: > "$MOCK_GH_LOG"
snapshot_once >/dev/null
assert_equals "$(graphql_calls)" "1" "rm cache → next read refetches"

# 4. Expired TTL refetches.
touch -t 202001010000 "$BOARD_SNAPSHOT_CACHE"
: > "$MOCK_GH_LOG"
snapshot_once >/dev/null
assert_equals "$(graphql_calls)" "1" "stale mtime beyond TTL → refetch"

# 5. refresh=True bypasses the cache and rewrites it.
: > "$MOCK_GH_LOG"
snapshot_refresh >/dev/null
assert_equals "$(graphql_calls)" "1" "refresh=True fetches despite fresh cache"

# 6. Corrupt cache falls through to a fetch instead of crashing.
printf 'not json' > "$BOARD_SNAPSHOT_CACHE"
: > "$MOCK_GH_LOG"
out="$(snapshot_once)"
assert_equals "$(graphql_calls)" "1" "corrupt cache → refetch"
assert_equals "$out" "$n1" "corrupt cache read still returns the board"

echo "== dispatch sweep: one fetch serves the whole candidate iteration =="
# Deep eligible queue, both lanes at cap 0: the loop's slot probes for every
# break decision must be served by the single list fetch's cache write.
# A skeleton-bodied default birth demotes to needs-info (not eligible), so
# these seeds carry a real body.
unset BOARD_SNAPSHOT_CACHE
BODY_FILE="$TEST_ROOT/body.md"
printf '## Problem\nreal enough to dispatch\n\n## Success criteria\n- observable\n' > "$BODY_FILE"
rm -f "$MOCK_GH_STATE"
for i in 1 2 3 4 5; do
    "$BOARD_SCRIPTS/board-register.sh" "seed ticket $i" bug P2 --body-file "$BODY_FILE" >/dev/null
done
: > "$MOCK_GH_LOG"
out="$(IMPLEMENT_MAX_CONCURRENT=0 ARCHITECT_MAX_CONCURRENT=0 \
       "$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh" --sweep 2>&1)" || true
assert_contains "$out" "cap reached: both lanes full" "capped sweep reports and stops"
assert_equals "$(graphql_calls)" "1" "sweep over 5 eligible tickets = exactly one GraphQL fetch"

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
