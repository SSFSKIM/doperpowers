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

loglines="$(wc -l < "$BOARD/log.jsonl" | tr -d ' ')"
assert_equals "$loglines" "3" "log.jsonl has exactly 3 lines after the three registers"

out="$(run board-register.sh "Needs more detail" bug --state needs-info --note "what info")"
assert_contains "$out" "T4" "needs-info with --note succeeds (T4)"

out="$(run board-register.sh "This is a very long ticket title that should be truncated in the slug" enhancement)"
assert_equals "$out" "T5 tickets/T5-this-is-a-very-long-ticket-title-that-sh.md" "long title slug capped at 40 chars"

assert_fails run board-register.sh "Bad" gadget                       # bad category
assert_fails run board-register.sh "Bad" bug --state blocked          # blocked without note
assert_fails run board-register.sh "Bad" bug --parent T99             # dangling ref
assert_fails run board-register.sh "Bad" bug --state in-progress      # not a birth state

(cd "$TEST_ROOT/wt" && "$SCRIPTS_DIR/board-register.sh" "From worktree" bug) \
    >/dev/null 2>&1 && fail "worktree guard" || pass "refused to run from a worktree"

[ -f "$BOARD/map.json.tmp" ] && fail "no tmp litter" || pass "no tmp litter after writes"

# ---- Task 2: transition legality, notes, sweeps, log --------------------------
echo "board-transition:"

# Board so far: T1 ready (epic-to-be), T2 deferred, T3 ready (parent T1, blocked_by T2)
assert_fails run board-transition.sh T1 "done"               # illegal ready→done
assert_fails run board-transition.sh T1 blocked              # note required
assert_fails run board-transition.sh T1 ready-for-agent      # same-state
assert_fails run board-transition.sh T99 "done"              # unknown ticket
assert_fails run board-transition.sh T1 shipping             # unknown state

out="$(run board-transition.sh T3 in-progress)"
assert_contains "$out" "T3: ready-for-agent → in-progress" "transition applied"
assert_contains "$out" "T1: ready-for-agent → in-progress" "epic parent pulled to in-progress"

out="$(run board-transition.sh T3 in-review "" --branch worktree-t3 --pr "PR#12")"
pr="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['pr'])")"
assert_equals "$pr" "PR#12" "pr recorded on in-review"

out="$(run board-transition.sh T2 ready-for-agent)"    # revive the deferred blocker
out="$(run board-transition.sh T2 in-progress)"
out="$(run board-transition.sh T2 "done")"
assert_contains "$out" "T2: in-progress → done" "blocker done"

out="$(run board-transition.sh T3 "done")"
assert_contains "$out" "T1: in-progress → done" "epic auto-closed when all children terminal"

# done unblocks dependents: T7 blocked_by the not-yet-done T6
run board-register.sh "Blocker" bug >/dev/null                       # T6
run board-register.sh "Dependent" bug --blocked-by T6 >/dev/null     # T7
run board-transition.sh T6 in-progress >/dev/null
out="$(run board-transition.sh T6 "done")"
assert_contains "$out" "now eligible: T7" "done sweep reports newly eligible dependents"

lines="$(wc -l < "$BOARD/log.jsonl" | tr -d ' ')"
assert_equals "$lines" "17" "every applied change logged (7 births + 10 transitions)"

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
