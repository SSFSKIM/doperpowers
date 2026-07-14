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
TRACKER_SKILL="$REPO_ROOT/skills/issue-tracker/SKILL.md"

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
assert_contains "$proto" "issue-body-sha256={{ISSUE_BODY_SHA256}}" "gate records the authorization-time issue body hash"
assert_contains "$proto" "implement-protocol-sha256={{IMPLEMENT_PROTOCOL_SHA256}}" "gate records the exact Implement Worker contract hash"
assert_contains "$proto" "WHO UNPARKS IT" "park discriminant present"
assert_contains "$proto" "{{DECOMPOSE_DOC}}" "decompose procedure pointer present (runtime-opened)"
assert_contains "$proto" "FOLLOW-UPS: none" "follow-ups contract present"
assert_contains "$proto" "A follow-up not registered does not exist" "direct registration doctrine"
assert_contains "$proto" "Closes #{{ISSUE_NUMBER}}" "merge-closes contract present"
assert_contains "$proto" "NO orchestrator" "no-orchestrator doctrine"
assert_contains "$proto" "{{EXECUTION_BLOCK}}" "execution block placeholder present"
assert_contains "$proto" "A fork discovered mid-build" "post-gate park clause present"
assert_contains "$proto" "ASK EARLY" "ask-early clause present (no assumption-building past human-grade forks)"
assert_contains "$proto" "a pause, not a death" "park-pause doctrine present"
assert_contains "$proto" "IF RESUMED WITH ANSWERS" "answer-relay resume clause present"
assert_contains "$proto" "[gate] re-pass" "re-verdict guard present"
assert_contains "$proto" "CLOSING ARTIFACT" "PR body is the closing artifact (FD-7: no live workpad)"
assert_contains "$proto" "## Validation Evidence" "validation-evidence section mandated"
assert_contains "$proto" "## Confusions" "confusions section (conditional) mandated"
assert_contains "$proto" "ORIENTATION SUMMARY" "park orientation summary mandated"
assert_contains "$proto" "no live progress mirror" "no-mirror doctrine stated in the protocol"
assert_contains "$proto" "big-but-ATOMIC" "atomic-counts-as-one-unit scoping clause present"
assert_contains "$proto" "land on main independently" "landability decompose criterion present"
assert_contains "$proto" "ENUMERABLE" "enumerable-decisions→needs-human discriminant present"
assert_contains "$proto" "doperpowers:reviewing-prs" "handoff to the review loop named"
assert_not_contains "$proto" '"ticket":' "the JSON proposal block is dead"
assert_not_contains "$proto" "→ blocked" "no retired blocked vocabulary"
assert_not_contains "$proto" "status:blocked" "no retired blocked label"

echo "placeholders:"
want="{{BOARD_SCRIPTS}} {{DECOMPOSE_DOC}} {{ENGINE_NAME}} {{EXECUTION_BLOCK}} {{IMPLEMENT_PROTOCOL_SHA256}} {{ISSUE_BODY_SHA256}} {{ISSUE_BODY}} {{ISSUE_NUMBER}} {{ISSUE_TITLE}} {{ISSUE_URL}} {{REPO_FACTS}} {{REPO}}"
got="$(grep -o '{{[A-Z0-9_]*}}' "$PROTO" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got" = "$want" ]; then pass "placeholder set is exactly: $want"; else
    fail "placeholder set drifted"; echo "    expected: $want"; echo "    actual:   $got"; fi

echo "spike protocol:"
SPIKE="$REPO_ROOT/skills/implementing-tickets/references/spike-worker-protocol.md"
[ -f "$SPIKE" ] || { echo "missing $SPIKE"; exit 1; }
spike="$(cat "$SPIKE")"
want_spike="{{BOARD_SCRIPTS}} {{ENGINE_NAME}} {{ISSUE_BODY}} {{ISSUE_NUMBER}} {{ISSUE_TITLE}} {{ISSUE_URL}} {{REPO_FACTS}} {{REPO}}"
got_spike="$(grep -o '{{[A-Z0-9_]*}}' "$SPIKE" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got_spike" = "$want_spike" ]; then pass "spike placeholder set is exactly: $want_spike"; else
    fail "spike placeholder set drifted"; echo "    expected: $want_spike"; echo "    actual:   $got_spike"; fi
assert_contains "$spike" "DRAFT" "spike: evidence PR is draft-only"
assert_not_contains "$spike" "{{EXECUTION_BLOCK}}" "spike: no engine execution block (exploration, not TDD)"
assert_contains "$spike" 'NEVER "Closes #{{ISSUE_NUMBER}}"' "spike: Closes is forbidden"
assert_contains "$spike" 'needs-human "findings ready:' "spike: findings-ready handoff park"
assert_contains "$spike" "terminal states" "spike: terminal states stay the human's"
assert_contains "$spike" "[findings]" "spike: structured findings comment mandated"

echo "decompose procedure (runtime-opened):"
DECOMP="$REPO_ROOT/skills/implementing-tickets/references/implement-decompose.md"
[ -f "$DECOMP" ] || { echo "missing $DECOMP"; exit 1; }
decomp="$(cat "$DECOMP")"
assert_contains "$decomp" "a chain IS" "decompose doc: serialization-as-edges present"
assert_contains "$decomp" "## Roadmap" "decompose doc: JIT roadmap escape hatch present"
assert_contains "$decomp" "NO code" "decompose doc: write-no-code clause present"
assert_contains "$decomp" "grants no authority beyond your prompt" "decompose doc: no-extra-authority framing"
assert_not_contains "$decomp" "{{" "decompose doc: placeholder-free (opened at runtime, never rendered)"

echo "engine blocks:"
EXEC_CLAUDE="$REPO_ROOT/skills/implementing-tickets/references/engine-blocks/execution-claude.md"
EXEC_CODEX="$REPO_ROOT/skills/implementing-tickets/references/engine-blocks/execution-codex.md"
[ -f "$EXEC_CLAUDE" ] || { echo "missing $EXEC_CLAUDE"; exit 1; }
[ -f "$EXEC_CODEX" ] || { echo "missing $EXEC_CODEX"; exit 1; }
exec_claude="$(cat "$EXEC_CLAUDE")"
exec_codex="$(cat "$EXEC_CODEX")"
assert_contains "$exec_claude" "doperpowers:execplan" "claude block: execplan mode wired"
assert_contains "$exec_codex" "EXECPLAN:" "codex block: execplan mode wired (not bare PLAN)"
assert_contains "$exec_codex" "doperpowers:execplan" "codex block: routes to the execplan doctrine"
assert_contains "$exec_codex" ".agents/skills" "codex block: vendored skill doctrine pointer"
assert_contains "$exec_codex" "do NOT spawn sub-agents" "codex block: work-alone clause (no collab threads)"
assert_contains "$exec_claude" "do NOT dispatch subagents" "claude block: work-alone clause"
assert_contains "$exec_codex" "subagent-driven-development" "codex block: names the forbidden interactive skills"
assert_contains "$exec_claude" "subagent-driven-development" "claude block: names the forbidden interactive skills"
assert_contains "$exec_claude" "never" "claude block: evidence mandate present"
assert_contains "$exec_claude" "claim completion on reasoning alone" "claude block: no-evidence-no-done clause"
assert_contains "$exec_codex" "claim completion on reasoning alone" "codex block: no-evidence-no-done clause"
assert_contains "$exec_claude" "big-but-atomic" "claude block: atomic execplan trigger"
assert_contains "$exec_codex" "big-but-atomic" "codex block: atomic plan trigger"

echo "skill doctrine:"
[ -f "$SKILL" ] || { echo "missing $SKILL"; exit 1; }
skill="$(cat "$SKILL")"
assert_contains "$skill" "name: implementing-tickets" "frontmatter name"
assert_contains "$skill" "references/implement-worker-protocol.md" "skill points at the protocol"
assert_contains "$skill" "doperpowers:issue-tracker" "skill points at the board schema"
[ -f "$TRACKER_SKILL" ] || { echo "missing $TRACKER_SKILL"; exit 1; }
tracker_skill="$(cat "$TRACKER_SKILL")"
assert_contains "$tracker_skill" "ISSUE_BODY_SHA256" "dispatch ritual binds the exact issue-body snapshot hash"
assert_contains "$tracker_skill" "IMPLEMENT_PROTOCOL_SHA256" "dispatch ritual binds the exact protocol-template hash"
assert_contains "$skill" "board-answer.sh" "skill names the answer relay (park = pause)"
assert_not_contains "$skill" "status:blocked" "no retired vocabulary in doctrine"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES test(s) FAILED"; exit 1; fi
echo "all tests passed"
