#!/usr/bin/env bash
#
# Hermetic tests for the surface topology layer (spec:
# docs/doperpowers/specs/2026-08-10-surface-topology-design.md).
#
# Same harness as test-board-scripts.sh: the real scripts run end-to-end
# against the PATH-shimmed mock gh; the surfaces registry is a committed
# .doperpowers/surfaces.md in the throwaway repo, read via SURFACES_REF=HEAD
# (production resolves the remote default branch; the env override IS the
# tested seam). Acceptance numbers cited from the spec.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/issue-tracker/scripts"

FAILURES=0
ASSERTIONS=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; ASSERTIONS=$((ASSERTIONS + 1)); }
fail() {
    echo "  [FAIL] $1"
    ASSERTIONS=$((ASSERTIONS + 1))
    FAILURES=$((FAILURES + 1))
}
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_fails() { # cmd... — passes when the command exits non-zero
    if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; else pass "refused: $*"; fi
}

export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export BOARD_REPO="test/repo"
export MOCK_GH_STATE="$TEST_ROOT/gh-state.json"
export MOCK_GH_LOG="$TEST_ROOT/gh-log.jsonl"
export PATH="$SCRIPT_DIR/mock-gh:$PATH"
WORK="$TEST_ROOT/work"
git init -q "$WORK"
git -C "$WORK" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q

run() { (cd "$WORK" && "$SCRIPTS_DIR/$1" "${@:2}"); }
# state(): eval is safe here — the expression is a test-author-written literal
# from THIS file (never external input), evaluated against the mock's state.
# (Same idiom as test-board-scripts.sh.)
state() { python3 -c "import json,sys;print(eval(sys.argv[1], {'s': json.load(open('$MOCK_GH_STATE'))}))" "$1"; }

registry_commit() {  # <content> — (re)commit .doperpowers/surfaces.md
    mkdir -p "$WORK/.doperpowers"
    printf '%s\n' "$1" > "$WORK/.doperpowers/surfaces.md"
    git -C "$WORK" add .doperpowers/surfaces.md
    git -C "$WORK" -c user.email=t@t -c user.name=t commit -qm surfaces
}

REGISTRY='## recommend-rpc
- paths: sql/*recommend*.sql, lib/recommend*
- identifiers: recommend_for_student
- born-of: #1258
- note: one function body

## scrubber
- paths: lib/scrub/**
- identifiers: buildPlanText'

# ---- T1: inertness — no registry, no behavior (acceptance 9) ---------------
echo "T1: no registry → surface features inert"
body="$TEST_ROOT/body.md"; printf 'touches recommend_for_student directly\n' > "$body"
out="$(run board-register.sh "no registry yet" enhancement P2 --body-file "$body")"
n1="${out%% *}"
assert_contains "$(state "s['issues']['$n1']['labels']")" "enhancement" "T1: ticket created"
assert_not_contains "$(state "s['issues']['$n1']['labels']")" "surface:" "T1: no surface label without a registry"
assert_fails run board-surface.sh "$n1" --add recommend-rpc
lint_out="$(run board-lint.sh || true)"
assert_not_contains "$lint_out" "SURFACE" "T1: lint carries no surface section without a registry"

# ---- registry lands (SURFACES_REF pins the read to a committed ref) --------
registry_commit "$REGISTRY"
export SURFACES_REF=HEAD

# ---- T2: board-surface.sh add/remove roundtrip -----------------------------
echo "T2: board-surface.sh add/remove"
out="$(run board-surface.sh "$n1" --add recommend-rpc)"
assert_contains "$out" "surface += recommend-rpc" "T2: add reports"
assert_contains "$(state "s['issues']['$n1']['labels']")" "surface:recommend-rpc" "T2: label landed"
assert_fails run board-surface.sh "$n1" --add no-such-surface
out="$(run board-surface.sh "$n1" --remove recommend-rpc)"
assert_contains "$out" "surface -= recommend-rpc" "T2: remove reports"
assert_not_contains "$(state "s['issues']['$n1']['labels']")" "surface:recommend-rpc" "T2: label removed"

# ---- T3: lint FAILs an invented surface label (acceptance 7) ---------------
echo "T3: lint — closed vocabulary"
gh issue edit "$n1" -R test/repo --add-label surface:bogus >/dev/null
lint_out="$(run board-lint.sh || true)"
assert_contains "$lint_out" "surface label with no registry entry: surface:bogus" "T3: invented label FAILs"
assert_contains "$lint_out" "board-surface.sh $n1 --remove bogus" "T3: FIX names board-surface.sh"
gh issue edit "$n1" -R test/repo --remove-label surface:bogus >/dev/null

# ---- T4: lint validates registry names + reports queue depth ---------------
echo "T4: lint — registry name rule + depth report"
registry_commit "$REGISTRY

## Bad_Name
- paths: x/**"
lint_out="$(run board-lint.sh || true)"
assert_contains "$lint_out" "surfaces.md entry 'Bad_Name'" "T4: non-kebab name FAILs"
registry_commit "$REGISTRY"
run board-surface.sh "$n1" --add recommend-rpc >/dev/null
lint_out="$(run board-lint.sh || true)"
assert_contains "$lint_out" "SURFACE recommend-rpc: 1 open ticket(s)" "T4: depth report line"
run board-surface.sh "$n1" --remove recommend-rpc >/dev/null

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "FAILED: $FAILURES of $ASSERTIONS assertions"
    exit 1
fi
echo "OK ($ASSERTIONS assertions)"
