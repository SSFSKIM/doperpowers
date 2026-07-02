#!/usr/bin/env bash
#
# Hermetic tests for the issue-tracker board toolkit.
#
# The board scripts touch only the filesystem (a git repo's main checkout, the
# board data dir, and the daemon registry dir) — no network, no `claude` CLI.
# We build a throwaway git repo + worktree and a fake daemon registry, drive
# the real scripts end-to-end, and assert on map.json / log.jsonl / output.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/issue-tracker/scripts"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() {
    echo "  [FAIL] $1"
    FAILURES=$((FAILURES + 1))
}
assert_equals() {
    if [[ "$1" == "$2" ]]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
assert_fails() { # cmd... — passes when the command exits non-zero
    if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; else pass "refused: $*"; fi
}

# ---- environment: throwaway git repo + worktree, fake daemon registry -------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
WORK="$TEST_ROOT/work"
git init -q "$WORK"
git -C "$WORK" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$WORK" worktree add -q -b t-branch "$TEST_ROOT/wt"
BOARD="$WORK/doperpowers/issue-tracker"

run() { # run a board script from the main checkout
    local s="$1"; shift
    (cd "$WORK" && "$SCRIPTS_DIR/$s" "$@")
}

# ---- Task 1: register + lazy init + worktree guard ---------------------------
echo "board-register:"

out="$(run board-register.sh "Worktree map viewer" enhancement)"
assert_equals "$out" "T1 tickets/T1-worktree-map-viewer.md" "first register returns T1 + slug md path"
assert_file_exists "$BOARD/map.json" "lazy init created map.json"
assert_file_exists "$BOARD/log.jsonl" "birth logged to log.jsonl"
state="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T1']['state'])")"
assert_equals "$state" "ready-for-agent" "default birth state is ready-for-agent"

out="$(run board-register.sh "Deferred idea" bug --state deferred)"
assert_contains "$out" "T2" "second register allocates T2"

out="$(run board-register.sh "Child slice" enhancement --parent T1 --blocked-by T2)"
assert_contains "$out" "T3" "third register allocates T3"
parent="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['parent'])")"
assert_equals "$parent" "T1" "parent edge stored"

assert_fails run board-register.sh "Bad" gadget                       # bad category
assert_fails run board-register.sh "Bad" bug --state blocked          # blocked without note
assert_fails run board-register.sh "Bad" bug --parent T99             # dangling ref
assert_fails run board-register.sh "Bad" bug --state in-progress      # not a birth state

(cd "$TEST_ROOT/wt" && "$SCRIPTS_DIR/board-register.sh" "From worktree" bug) \
    >/dev/null 2>&1 && fail "worktree guard" || pass "refused to run from a worktree"

[ -f "$BOARD/map.json.tmp" ] && fail "no tmp litter" || pass "no tmp litter after writes"

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
