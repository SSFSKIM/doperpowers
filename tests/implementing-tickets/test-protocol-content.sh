#!/usr/bin/env bash
#
# Structural invariants over the implement-worker protocol + skill doctrine.
# Prose is behavior here: these asserts pin the load-bearing clauses so a
# future edit cannot silently drop the gate, resurrect the proposal block,
# or reintroduce retired vocabulary.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROTO="$REPO_ROOT/skills/implementing-tickets/references/implement-worker-protocol.md"
SKILL="$REPO_ROOT/skills/implementing-tickets/SKILL.md"

FAILURES=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; else pass "$3"; fi
}

echo "protocol content:"
[ -f "$PROTO" ] || { echo "missing $PROTO"; exit 1; }
proto="$(cat "$PROTO")"
assert_contains "$proto" "THE GATE comes before everything" "gate precedes everything"
assert_contains "$proto" "WELL-DEFINED" "check 1 present"
assert_contains "$proto" "WELL-SCOPED" "check 2 present"
assert_contains "$proto" "Even minor taste is never your call" "minor-taste rule present"
assert_contains "$proto" "VERDICT IS YOUR FIRST BOARD WRITE" "verdict-first-write present"
assert_contains "$proto" "WHO UNPARKS IT" "park discriminant present"
assert_contains "$proto" "a chain IS" "serialization-as-edges present"
assert_contains "$proto" "## Roadmap" "JIT roadmap escape hatch present"
assert_contains "$proto" "FOLLOW-UPS: none" "follow-ups contract present"
assert_contains "$proto" "A follow-up not registered does not exist" "direct registration doctrine"
assert_contains "$proto" "Closes #{{ISSUE_NUMBER}}" "merge-closes contract present"
assert_contains "$proto" "NO orchestrator" "no-orchestrator doctrine"
assert_contains "$proto" "doperpowers:execplan" "execplan mode wired"
assert_contains "$proto" "A fork discovered mid-build" "post-gate park clause present"
assert_contains "$proto" "doperpowers:reviewing-prs" "handoff to the review loop named"
assert_not_contains "$proto" '"ticket":' "the JSON proposal block is dead"
assert_not_contains "$proto" "→ blocked" "no retired blocked vocabulary"
assert_not_contains "$proto" "status:blocked" "no retired blocked label"

echo "placeholders:"
want="{{BOARD_SCRIPTS}} {{ISSUE_BODY}} {{ISSUE_NUMBER}} {{ISSUE_TITLE}} {{ISSUE_URL}} {{REPO}}"
got="$(grep -o '{{[A-Z_]*}}' "$PROTO" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got" = "$want" ]; then pass "placeholder set is exactly: $want"; else
    fail "placeholder set drifted"; echo "    expected: $want"; echo "    actual:   $got"; fi

echo "skill doctrine:"
[ -f "$SKILL" ] || { echo "missing $SKILL"; exit 1; }
skill="$(cat "$SKILL")"
assert_contains "$skill" "name: implementing-tickets" "frontmatter name"
assert_contains "$skill" "references/implement-worker-protocol.md" "skill points at the protocol"
assert_contains "$skill" "doperpowers:issue-tracker" "skill points at the board schema"
assert_not_contains "$skill" "status:blocked" "no retired vocabulary in doctrine"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES test(s) FAILED"; exit 1; fi
echo "all tests passed"
