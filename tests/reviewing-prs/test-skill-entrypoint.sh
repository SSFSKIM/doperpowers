#!/usr/bin/env bash
# Structural invariants for the reviewing-prs runtime skill and operator reference.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL="$REPO_ROOT/skills/reviewing-prs/SKILL.md"
MANUAL="$REPO_ROOT/skills/reviewing-prs/references/operation-manual.md"
BOOTSTRAP="$REPO_ROOT/skills/reviewing-prs/references/review-worker-bootstrap.md"
DISPATCH="$REPO_ROOT/skills/reviewing-prs/scripts/review-dispatch.sh"
OLD_PROTOCOL="$REPO_ROOT/skills/reviewing-prs/references/review-worker-protocol.md"

FAILURES=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_file() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; fi
}
assert_missing() {
    if [[ ! -e "$1" ]]; then pass "$2"; else fail "$2"; fi
}
assert_contains() {
    if grep -Fq -- "$2" "$1" 2>/dev/null; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" "$1" 2>/dev/null; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_order() {
    local first_line second_line
    first_line="$(grep -nFm1 -- "$2" "$1" 2>/dev/null | cut -d: -f1 || true)"
    second_line="$(grep -nFm1 -- "$3" "$1" 2>/dev/null | cut -d: -f1 || true)"
    if [[ -n "$first_line" && -n "$second_line" && "$first_line" -lt "$second_line" ]]; then
        pass "$4"
    else
        fail "$4"; echo "    expected '$2' before '$3' in: $1"
    fi
}

echo "runtime skill:"
assert_file "$SKILL" "SKILL.md exists"
assert_contains "$SKILL" "name: reviewing-prs" "skill frontmatter name is preserved"
assert_contains "$SKILL" 'Operator or setup invocation: read `references/operation-manual.md` instead.' "operator invocations route to the reference manual"
assert_contains "$SKILL" "You are a REVIEW worker for PR #{{PR_NUMBER}}" "SKILL.md is the Review Worker Protocol"
assert_contains "$SKILL" "ROUTE each verified finding to exactly one bin" "finding routing lives in the runtime skill"
assert_contains "$SKILL" "SELF-MERGE tier requires ALL" "merge authority lives in the runtime skill"
assert_contains "$SKILL" "CROSS-CHECK the PR's closing artifact" "closing-artifact cross-check lives in the runtime skill"
assert_contains "$SKILL" "not verifiable is an EVIDENCE FINDING" "unverifiable claimed evidence remains a finding"
assert_contains "$SKILL" "START NATIVE CORRECTNESS REVIEW IN BACKGROUND" "runtime skill starts native correctness review without waiting"
assert_contains "$SKILL" "IMPLEMENTER-PROTOCOL AUDIT" "runtime skill owns the spec and decision-discipline audit"
assert_contains "$SKILL" "JOIN THE TWO TRACKS" "runtime skill joins independent review results before routing"
assert_contains "$SKILL" "issue body is the canonical primary specification" "issue body is the primary specification"
assert_contains "$SKILL" "only documents explicitly referenced by the issue body" "secondary specification evidence is issue-selected"
assert_contains "$SKILL" 'Repository documents are read from origin/{{BASE_REF}}, never from the PR head.' "repo specification documents are pinned to the pre-PR base"
assert_contains "$SKILL" "human answers recorded on the issue before implementation resumes are authoritative ticket content" "resumed-ticket answers refine the specification"
assert_contains "$SKILL" "PROTOCOL BLOCKER" "worker audit defines the confidence-blocking protocol class"
assert_contains "$SKILL" "SPEC FINDING" "worker audit defines clear requirement mismatches"
assert_contains "$SKILL" "AUDIT NOTE" "worker audit keeps evidence gaps non-blocking when appropriate"
assert_contains "$SKILL" "EVIDENCE FINDING" "closing-artifact failures have an independent routing class"
assert_contains "$SKILL" "ticketless EVIDENCE FINDING" "ticketless evidence failures block confidence on the PR"
assert_contains "$SKILL" 'reached `ready-for-agent`' "worker audit checks dispatch authorization timing"
assert_contains "$SKILL" "mandatory Implement Worker protocol contract" "worker audit covers closing-artifact protocol violations"
assert_contains "$SKILL" "Missing timeline evidence" "missing authorization history alone remains an audit note"
assert_contains "$SKILL" "Derive the native verdict yourself" "join derives the native verdict without custom engine policy"
assert_contains "$SKILL" "native severity is the blocker bit only for native correctness findings" "native severity is scoped to native findings"
assert_order "$SKILL" "START NATIVE CORRECTNESS REVIEW IN BACKGROUND" "IMPLEMENTER-PROTOCOL AUDIT" "native review starts before the worker audit"
assert_order "$SKILL" "IMPLEMENTER-PROTOCOL AUDIT" "JOIN THE TWO TRACKS" "worker audit completes before native findings are joined"
assert_contains "$SKILL" "only when auto-merge is on" "self-merge authority remains gated by auto-merge"
assert_contains "$SKILL" "needs-human" "human park route remains in the runtime skill"
assert_not_contains "$SKILL" "needs-info" "review-loop parks remain human-unparked"
assert_not_contains "$SKILL" "→ blocked" "retired blocked vocabulary stays absent"
assert_not_contains "$SKILL" "## Adopting a repo (checklist)" "operator setup is absent from the runtime skill"
want_placeholders="{{AUTO_MERGE}} {{BASE_IS_DEFAULT}} {{BASE_REF}} {{BOARD_SCRIPTS}} {{DEFAULT_BRANCH}} {{ENGINE_BLOCK}} {{FALLBACK_BLOCK}} {{HEAD_REF}} {{HEAD_SHA}} {{ISSUE_BODY}} {{ISSUE_LIST}} {{ISSUE_NUMBER}} {{ISSUE_URL}} {{PR_BODY}} {{PR_NUMBER}} {{PR_TITLE}} {{PR_URL}} {{REPO_FACTS}} {{REPO}} {{RISK_MANIFEST}} {{TECH_DEBT_ISSUE}}"
got_placeholders="$(grep -o '{{[A-Z_]*}}' "$SKILL" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [[ "$got_placeholders" == "$want_placeholders" ]]; then
    pass "runtime placeholder set is unchanged"
else
    fail "runtime placeholder set is unchanged"
    echo "    expected: $want_placeholders"
    echo "    actual:   $got_placeholders"
fi

echo "operator reference:"
assert_file "$MANUAL" "operation manual exists"
assert_contains "$MANUAL" "# Reviewing PRs — the autonomous review loop" "operation manual preserves the loop overview"
assert_contains "$MANUAL" "## Dedupe & sweep policy" "operation manual preserves operating policy"
assert_contains "$MANUAL" "## Adopting a repo (checklist)" "operation manual preserves setup guidance"
assert_contains "$MANUAL" '`SKILL.md` | the Review Worker Protocol' "operation manual points to the runtime skill"

echo "worker bootstrap:"
assert_file "$BOOTSTRAP" "worker bootstrap exists"
assert_contains "$BOOTSTRAP" "REQUIRED SUB-SKILL: Use doperpowers:reviewing-prs" "bootstrap explicitly invokes the runtime skill"
assert_contains "$BOOTSTRAP" 'unconditionally open `{{SKILL_FILE}}`' "bootstrap always loads the dispatcher-owned canonical skill"
assert_contains "$BOOTSTRAP" 'Do not resolve this protocol from the workspace `.agents/skills`' "PR-owned same-name skills cannot replace the protocol"
assert_not_contains "$BOOTSTRAP" "If the named skill is not discoverable" "canonical skill loading is unconditional, not a fallback"
assert_contains "$BOOTSTRAP" "{{SKILL_FILE}}" "bootstrap binds the version-matched canonical skill file"
assert_contains "$BOOTSTRAP" "{{ENGINE_BLOCK}}" "bootstrap supplies the engine-block binding"
assert_contains "$BOOTSTRAP" "{{PR_BODY}}" "bootstrap supplies PR context"
assert_contains "$BOOTSTRAP" "{{ISSUE_BODY}}" "bootstrap supplies ticket context"
assert_contains "$BOOTSTRAP" "{{RISK_MANIFEST}}" "bootstrap supplies risk-surface context"
assert_contains "$BOOTSTRAP" "{{REPO_FACTS}}" "bootstrap supplies repo facts"

echo "dispatch wiring:"
assert_contains "$DISPATCH" 'BOOTSTRAP_TEMPLATE="$SKILL_DIR/references/review-worker-bootstrap.md"' "dispatcher renders the worker bootstrap"
assert_not_contains "$DISPATCH" "review-worker-protocol.md" "dispatcher no longer bypasses the skill entrypoint"
assert_missing "$OLD_PROTOCOL" "retired protocol reference file is removed"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
