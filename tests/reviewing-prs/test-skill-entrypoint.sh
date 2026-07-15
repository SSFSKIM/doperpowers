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

echo "runtime skill:"
assert_file "$SKILL" "SKILL.md exists"
assert_contains "$SKILL" "name: reviewing-prs" "skill frontmatter name is preserved"
assert_contains "$SKILL" 'Operator or setup invocation: read `references/operation-manual.md` instead.' "operator invocations route to the reference manual"
assert_contains "$SKILL" "You are a REVIEW worker for PR #{{PR_NUMBER}}" "SKILL.md is the Review Worker Protocol"
assert_contains "$SKILL" "ROUTE each finding to exactly one bin" "finding routing lives in the runtime skill"
assert_contains "$SKILL" "SELF-MERGE tier requires ALL" "merge authority lives in the runtime skill"
assert_contains "$SKILL" "CROSS-CHECK the PR's closing artifact" "closing-artifact cross-check lives in the runtime skill"
assert_contains "$SKILL" "not verifiable is itself a finding" "unverifiable claimed evidence remains a finding"
assert_contains "$SKILL" "only when auto-merge is on" "self-merge authority remains gated by auto-merge"
assert_contains "$SKILL" "needs-human" "human park route remains in the runtime skill"
assert_not_contains "$SKILL" "needs-info" "review-loop parks remain human-unparked"
assert_not_contains "$SKILL" "→ blocked" "retired blocked vocabulary stays absent"
assert_not_contains "$SKILL" "git diff origin/{{BASE_REF}}...HEAD)" "ORIENT still forbids a full-diff read"
assert_not_contains "$SKILL" "## Adopting a repo (checklist)" "operator setup is absent from the runtime skill"
assert_not_contains "$SKILL" "---- PR #{{PR_NUMBER}} brief ----" "SKILL.md carries no dead unrendered brief tail (briefs ride the dispatch prompt)"
assert_not_contains "$SKILL" "{{PR_BODY}}" "PR body placeholder lives only in the rendered bootstrap"
assert_not_contains "$SKILL" "{{ISSUE_BODY}}" "issue body placeholder lives only in the rendered bootstrap"
assert_contains "$SKILL" "dispatch prompt" "SKILL.md points the worker at the dispatch prompt for briefs and manifests"
want_placeholders="{{AUTO_MERGE}} {{BASE_IS_DEFAULT}} {{BASE_REF}} {{BOARD_SCRIPTS}} {{DEFAULT_BRANCH}} {{ENGINE_BLOCK}} {{FALLBACK_BLOCK}} {{HEAD_REF}} {{HEAD_SHA}} {{ISSUE_NUMBER}} {{PR_NUMBER}} {{PR_URL}} {{REPO}} {{TECH_DEBT_ISSUE}}"
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
assert_contains "$MANUAL" "only non-blocker findings" "operation manual matches the protocol's self-merge findings clause"
assert_not_contains "$MANUAL" "only low findings" "retired low-findings wording stays absent from the manual"

echo "worker bootstrap:"
assert_file "$BOOTSTRAP" "worker bootstrap exists"
assert_contains "$BOOTSTRAP" "REQUIRED SUB-SKILL: Use doperpowers:reviewing-prs" "bootstrap explicitly invokes the runtime skill"
assert_contains "$BOOTSTRAP" "unconditionally open" "bootstrap always loads dispatcher-owned doctrine"
assert_contains "$BOOTSTRAP" '{{SKILL_FILE}}' "bootstrap binds the canonical skill path"
assert_contains "$BOOTSTRAP" 'Do not resolve this protocol from the workspace `.agents/skills`' "bootstrap rejects PR-owned same-name skill spoofing"
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
