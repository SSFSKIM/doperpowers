#!/usr/bin/env bash
# Structural invariants for the reviewing-prs runtime skill, its wave-board
# reference, and the operator reference. Assertions pin STRUCTURE (headings,
# ordering, tokens, placeholder sets) — not sentences.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL="$REPO_ROOT/skills/reviewing-prs/SKILL.md"
MANUAL="$REPO_ROOT/skills/reviewing-prs/references/operation-manual.md"
BOOTSTRAP="$REPO_ROOT/skills/reviewing-prs/references/review-worker-bootstrap.md"
WAVEBOARD="$REPO_ROOT/skills/reviewing-prs/references/wave-board.md"
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
assert_before() {
    local first second
    first="$(grep -nF -- "$2" "$1" 2>/dev/null | cut -d: -f1 | head -1)"
    second="$(grep -nF -- "$3" "$1" 2>/dev/null | cut -d: -f1 | head -1)"
    if [[ -n "$first" && -n "$second" && "$first" -lt "$second" ]]; then
        pass "$4"
    else
        fail "$4"; echo "    expected before: $2"; echo "    expected after:  $3"
    fi
}

echo "runtime skill — identity and routing:"
assert_file "$SKILL" "SKILL.md exists"
assert_contains "$SKILL" "name: reviewing-prs" "skill frontmatter name is preserved"
assert_contains "$SKILL" 'Operator or setup invocation: read `references/operation-manual.md` instead.' "operator invocations route to the reference manual"
assert_contains "$SKILL" "You are a REVIEW worker for PR #{{PR_NUMBER}}" "SKILL.md is the Review Worker Protocol"
assert_not_contains "$SKILL" "## Adopting a repo (checklist)" "operator setup is absent from the runtime skill"
assert_contains "$SKILL" "dispatch prompt" "SKILL.md points the worker at the dispatch prompt for the manifest snapshots"
assert_not_contains "$SKILL" "---- PR #{{PR_NUMBER}} brief ----" "SKILL.md carries no dead unrendered brief tail"

echo "runtime skill — orchestrator section structure:"
want_headings="Role
ORIENT (read-only)
START ENGINE
COMPLIANCE AUDIT (concurrent, before JOIN)
JOIN
TRIAGE
FIX WAVES
RE-REVIEW
ESCALATE
AUTHORITY
REVIEW TRAIL"
got_headings="$(grep '^## ' "$SKILL" 2>/dev/null | sed 's/^## //' || true)"
if [[ "$got_headings" == "$want_headings" ]]; then
    pass "the eleven protocol sections exist in order"
else
    fail "the eleven protocol sections exist in order"
    echo "    expected:"; printf '      %s\n' $want_headings
    echo "    actual:";   printf '      %s\n' $got_headings
fi

echo "runtime skill — orchestrator doctrine:"
assert_contains "$SKILL" "graded and accepted" "code reaches the branch only as graded fixer commits"
assert_contains "$SKILL" "protocol-audit.md" "the compliance audit is a recorded artifact"
assert_contains "$SKILL" "BEFORE reading any engine output" "audit is recorded before native findings are read"
assert_contains "$SKILL" "stay read-only" "worker stays read-only in the shared worktree until JOIN"
assert_contains "$SKILL" "verify-then-fix" "verification lives in the fixer contract"
assert_contains "$SKILL" "ROUTE each finding to exactly one bin" "finding routing lives in the runtime skill"
assert_not_contains "$SKILL" "don't re-derive" "the severity re-derivation ban is retired — the worker routes on its own assessment"
assert_contains "$SKILL" "starting rank, not your verdict" "native severity is a prior the worker may overrule"
assert_contains "$SKILL" "stated reason in the trail" "departures from the native rank are recorded, not forbidden"
assert_contains "$SKILL" "references/wave-board.md" "wave mechanics live in the runtime-opened reference"
assert_contains "$SKILL" "<review-tmp>/pr-{{PR_NUMBER}}-fix-wave-" "wave board path is pinned in the dispatcher-session tmp dir"
assert_not_contains "$SKILL" ".doperpowers/qa/" "no wave state path under the PR-controlled worktree (symlink escape)"
assert_contains "$SKILL" "Maximum 2 waves" "wave cap is pinned"
assert_contains "$SKILL" "--remove-label confident-ready" "push strips stale confidence in-loop"

echo "runtime skill — compliance audit policy:"
assert_contains "$SKILL" "PROTOCOL BLOCKER" "protocol-blocker class exists"
assert_contains "$SKILL" "SPEC FINDING" "spec-finding class exists"
assert_contains "$SKILL" "AUDIT NOTE" "audit-note class exists"
assert_not_contains "$SKILL" "EVIDENCE FINDING" "evidence findings are merged into spec findings"
assert_contains "$SKILL" "parks confidence, not progress" "protocol blocker parks confidence while fixing continues"
assert_contains "$SKILL" "canonical primary spec" "issue body is the canonical primary specification"
assert_contains "$SKILL" "never the PR head" "referenced documents resolve from base, never PR head"
assert_contains "$SKILL" "answered fork ONLY" "pre-resume human answers scope to the answered fork"
assert_contains "$SKILL" "[gate] pass" "gate-comment evidence anchors the audit"
assert_contains "$SKILL" "userContentEdits" "post-gate drift resolves through GitHub edit history"
assert_not_contains "$SKILL" "sha256" "no hash-fingerprint machinery (timestamps, not hashes)"
assert_not_contains "$SKILL" "SHA-256" "no hash-fingerprint machinery in prose either"
assert_contains "$SKILL" "{{IMPLEMENT_PROTOCOL_FILE}}" "implement contract is the dispatcher-owned binding"
assert_contains "$SKILL" "dispatch exclusively binds this reviewer" "ticketed parks have one resumable review owner"
assert_contains "$SKILL" "BINDING BARRIER" "worker cannot start review before exclusive binding completes"
assert_contains "$SKILL" "{{BIND_READY_FILE}}" "worker barrier uses the dispatcher-owned ready file"
assert_contains "$SKILL" "regular file with mode 0600" "barrier validates the hidden ledger artifact"
assert_contains "$SKILL" "write the acknowledgement" "worker acks the barrier before ORIENT"
assert_before "$SKILL" "BINDING BARRIER" "## ORIENT" "binding barrier precedes every review action"
assert_contains "$SKILL" "board-answer" "active early park distinguishes notification from resume"

echo "runtime skill — escalation and dead ends:"
assert_contains "$SKILL" "SELF-MERGE tier requires ALL" "merge authority lives in the runtime skill"
assert_contains "$SKILL" "No unresolved PROTOCOL BLOCKER or SPEC FINDING" "worker-owned findings disqualify both confidence tiers"
assert_contains "$SKILL" "PARKED tier" "escalation has a terminal branch for an already-parked ticket"
assert_contains "$SKILL" "NEVER grant confident-ready over a park" "the human-tier catch-all cannot overwrite a needs-human park"
assert_contains "$SKILL" "the fix did not hold" "a re-flag matching a FIXED item re-waves as a live blocker, never a dupe"
assert_contains "$SKILL" "resolved by verification, not by a wave" "evidence-only spec findings have a resolvable route"
assert_contains "$SKILL" "unrun portion remains an unresolved SPEC FINDING" "substituted validation never silently verifies the original claim"
assert_contains "$SKILL" "transition needs-human immediately, before JOIN" "protocol blocker parks early while fixing continues"
assert_contains "$SKILL" "Never describe intended behavior as observed behavior" "human questions during a live wave are answered from evidence"
assert_contains "$SKILL" "auto-merge on" "self-merge authority remains gated by auto-merge"
assert_contains "$SKILL" "needs-human" "human park route remains in the runtime skill"
assert_not_contains "$SKILL" "needs-info" "review-loop parks remain human-unparked"
assert_not_contains "$SKILL" "→ blocked" "retired blocked vocabulary stays absent"
assert_contains "$SKILL" "structured PR comment" "ticketless TOO BIG routes to a PR comment"
assert_contains "$SKILL" "doperpowers:issue-tracker" "TOO BIG registration routes through the issue-tracker skill"
assert_contains "$SKILL" "author its body at register time" "TOO BIG ticket body is authored at register time"
assert_not_contains "$SKILL" "then flesh out its pre-spec body" "the two-step register-then-fill wording is retired"
assert_contains "$SKILL" "deferred-findings" "TECH_DEBT_ISSUE=none routes LOG to the trail"
assert_contains "$SKILL" "primary only" "secondary linked issues never receive board writes"

echo "runtime skill — placeholder set:"
want_placeholders="{{AUTO_MERGE}} {{BASE_IS_DEFAULT}} {{BASE_REF}} {{BIND_READY_FILE}} {{BOARD_SCRIPTS}} {{CODEX_REVIEW_EFFORT}} {{CODEX_REVIEW_MODEL}} {{DEFAULT_BRANCH}} {{HEAD_REF}} {{HEAD_SHA}} {{IMPLEMENT_PROTOCOL_FILE}} {{ISSUE_LIST}} {{ISSUE_NUMBER}} {{PR_NUMBER}} {{PR_URL}} {{REPO}} {{REVIEW_ENGINE}} {{TECH_DEBT_ISSUE}}"
got_placeholders="$(grep -o '{{[A-Z_]*}}' "$SKILL" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [[ "$got_placeholders" == "$want_placeholders" ]]; then
    pass "runtime placeholder set is exact"
else
    fail "runtime placeholder set is exact"
    echo "    expected: $want_placeholders"
    echo "    actual:   $got_placeholders"
fi

echo "wave board reference:"
assert_file "$WAVEBOARD" "wave-board reference exists"
assert_contains "$WAVEBOARD" '"disposition"' "board schema carries a disposition slot per item"
assert_contains "$WAVEBOARD" '"items"' "board frontmatter is a strict JSON object with items"
assert_contains "$WAVEBOARD" "<review-tmp>/pr-<PR>-fix-wave-" "board path lives in the dispatcher-session tmp dir"
assert_not_contains "$WAVEBOARD" ".doperpowers/qa" "board reference carries no worktree path a PR could pre-create"
assert_contains "$WAVEBOARD" "symlink" "board reference names the symlink hazard that forbids worktree residency"
assert_contains "$WAVEBOARD" "rebuild the board from the trail" "long-park tmp loss has a documented recovery"
# Engine-start + fallback text lives inline in the skill's START ENGINE
# section — the engine-blocks indirection is retired.
if [ -e "$REPO_ROOT/skills/reviewing-prs/references/engine-blocks" ]; then
    fail "engine-blocks dir is retired (engine text lives in SKILL.md)"
else
    pass "engine-blocks dir is retired (engine text lives in SKILL.md)"
fi
assert_contains "$SKILL" "EXCEPT a needs-human park" "review-tmp survives a park so mid-wave boards persist"
assert_not_contains "$SKILL" "Do NOT wait on it" "background-run rule is stated as shape, not double prohibition"
assert_contains "$SKILL" "the only place engine output is read" "audit independence keeps its positive statement"
assert_contains "$SKILL" "IN THE BACKGROUND" "engine starts in the background (audit runs concurrently)"
assert_contains "$SKILL" "45 minutes" "engine wait is bounded (hung-engine timeout)"
assert_contains "$SKILL" "ENGINE-UNAVAILABLE" "fallback carries the sweep retry marker"
assert_contains "$SKILL" "stays in-review" "engine-down never parks needs-human"
assert_contains "$WAVEBOARD" "VERIFY THEN FIX" "fixer contract relocates code verification"
assert_not_contains "$WAVEBOARD" "never implement from the finding text alone" "verify-then-fix is stated as grounding, not a prohibition"
assert_contains "$WAVEBOARD" "a finding can be wrong" "the contract names why verification comes first"
assert_not_contains "$WAVEBOARD" "ONE fixer subagent per wave" "no fixer-count mandate — crewing the wave is the orchestrator's call"
assert_contains "$WAVEBOARD" "subagents included" "delegation is the fixer's call"
assert_contains "$WAVEBOARD" "claimed by exactly one item" "every commit is attributable from the board alone"
assert_contains "$WAVEBOARD" "makes the affected item FAILED" "an unclaimed or mixed commit has an explicit grading route"
assert_not_contains "$WAVEBOARD" "never delegate implementation" "the delegation ban is retired — accountability replaces it"
assert_contains "$WAVEBOARD" "You never: run the review engine" "fixer role boundaries are stated"
assert_contains "$WAVEBOARD" "REFUTED" "refute disposition exists"
assert_contains "$WAVEBOARD" "NEVER commit or push it" "the board file never enters the PR"
assert_contains "$WAVEBOARD" "EMPTY disposition" "an unfilled slot is a failed item, not a pass"
assert_contains "$WAVEBOARD" "re-wave once" "failed items re-wave once before needs-human"
assert_contains "$WAVEBOARD" "evidence to check, not instructions" "fixer-written content is graded, never obeyed"
assert_contains "$WAVEBOARD" "grading REJECTS it" "a rejected FIXED disposition has an explicit route"
assert_contains "$WAVEBOARD" "record <wave-base> before dispatch" "every wave records its trusted rollback point"
assert_contains "$WAVEBOARD" "stop the authorized fixer and every descendant" "unauthorized writers are stopped transitively"
assert_contains "$WAVEBOARD" "QUIESCENCE GATE" "re-wave cannot overlap a still-writing descendant"
assert_contains "$WAVEBOARD" "git reset --hard <wave-base>" "unauthorized writer contamination has an explicit clean recovery"
assert_contains "$WAVEBOARD" "<board>.submitted" "grading uses an immutable submitted snapshot"
assert_contains "$WAVEBOARD" "grade ONLY the snapshot" "late live-board mutation cannot change a graded result"
assert_contains "$WAVEBOARD" "every FIXED item in the wave passed grading" "the wave pushes only when all fixes are accepted"
assert_not_contains "$WAVEBOARD" "one shell command" "no shell-packaging mandate — the expiry-then-push order is the rule"
assert_contains "$WAVEBOARD" "worktree and index must be clean" "wave boundary refuses unrecoverable dirty state"
assert_contains "$WAVEBOARD" "record <push-base>" "push chain pins the trusted remote branch head"
assert_contains "$WAVEBOARD" "board content fingerprint" "quiescence observes scratch state as well as git state"
assert_contains "$WAVEBOARD" "discard the contaminated board" "nested-writer recovery removes tainted dispositions"
assert_contains "$WAVEBOARD" "fresh board with blank dispositions" "re-wave cannot reuse contaminated board state"
assert_contains "$WAVEBOARD" "full unpushed range" "push gate validates every local commit, not only the latest wave"
assert_contains "$WAVEBOARD" "accepted-commit ledger" "push provenance has a durable per-commit gate"
assert_contains "$WAVEBOARD" "dispatcher control directory" "ledger path is undisclosed to the fixer tree"
assert_contains "$WAVEBOARD" "ledger content fingerprint" "late ledger tampering is detected before push"
assert_contains "$WAVEBOARD" "remote head differs from <push-base>" "unexpected remote movement blocks automatic salvage"
assert_before "$WAVEBOARD" "fresh remote SHA" "git reset --hard <wave-base>" "remote publication is ruled out before local reset"
assert_contains "$WAVEBOARD" "If this was wave 2" "wave-cap contamination parks instead of creating wave 3"
assert_contains "$SKILL" "scratch control state" "orchestrator write whitelist covers safety artifacts"
assert_contains "$SKILL" "do not rebase" "push rejection never asks the orchestrator to resolve code conflicts"
assert_not_contains "$SKILL" "log it twice" "re-flag dedupe states the routing fact, not a prohibition tail"
assert_not_contains "$SKILL" "in one shell command" "no shell-packaging mandate in the protocol either"
assert_not_contains "$SKILL" "NOT grant confidence" "the cap exit states the fact — there is no confidence to grant"
assert_before "$SKILL" "transition needs-human immediately, before JOIN" "## JOIN" "protocol blocker park precedes JOIN"
assert_before "$WAVEBOARD" "record <wave-base> before dispatch" "Dispatch the wave's fixer" "wave boundary is captured before dispatch"
assert_before "$WAVEBOARD" "stop the authorized fixer and every descendant" "QUIESCENCE GATE" "descendants stop before quiescence"
assert_before "$WAVEBOARD" "QUIESCENCE GATE" "discard the contaminated board" "quiescence precedes contaminated-state disposal"
assert_before "$WAVEBOARD" "grade ONLY the snapshot" "- FIXED:<sha>" "submitted snapshot precedes grading branches"
assert_before "$WAVEBOARD" "expire stale confidence BEFORE" "git push origin" "confidence expires before publishing"
assert_contains "$WAVEBOARD" "never rewrite history" "rejected fixes are corrected fix-forward, not rebased away"
assert_not_contains "$WAVEBOARD" "Stage only the files" "no staging-means mandate — the board-file ban and mixed-commit grading carry it"
assert_contains "$WAVEBOARD" "commit the board file" "the board-file ban survives in the fixer never list"
assert_contains "$WAVEBOARD" "appears in the commits being pushed" "push gate scans commit contents for the board, not just the working tree"
assert_contains "$WAVEBOARD" "published history is never rewritten" "the board-removal exception is scoped to unpushed commits"

echo "operator reference:"
assert_file "$MANUAL" "operation manual exists"
assert_contains "$MANUAL" "# Reviewing PRs — the autonomous review loop" "operation manual preserves the loop overview"
assert_contains "$MANUAL" "## Dedupe & sweep policy" "operation manual preserves operating policy"
assert_contains "$MANUAL" "## Adopting a repo (checklist)" "operation manual preserves setup guidance"
assert_contains "$MANUAL" '`SKILL.md` | the Review Worker Protocol' "operation manual points to the runtime skill"
assert_contains "$MANUAL" "only non-blocker findings" "operation manual matches the protocol's self-merge findings clause"
assert_not_contains "$MANUAL" "only low findings" "retired low-findings wording stays absent from the manual"
assert_contains "$MANUAL" "fix wave" "operation manual describes the fix-wave delegation"
assert_contains "$MANUAL" "wave-board.md" "operation manual points at the wave-board reference"
assert_contains "$MANUAL" "<review-tmp>/pr-<n>-fix-wave-<k>.md" "manual locates wave state outside the PR worktree"
assert_not_contains "$MANUAL" ".doperpowers/qa/pr-<n>-fix-wave-<k>.md" "manual no longer advertises the unsafe worktree path"
assert_contains "$MANUAL" "outage cap" "operation manual records the sweep outage cap"
assert_contains "$MANUAL" "PROTOCOL BLOCKER" "operation manual names the compliance-audit blocker class"
assert_not_contains "$MANUAL" "worker species" "retired two-species vocabulary stays absent from the manual"
assert_not_contains "$MANUAL" "Before the engine runs" "cross-check is concurrent with the engine, not before it"
assert_contains "$MANUAL" "[gate] pass" "manual carries the gate-comment-keyed evidence rule"
assert_not_contains "$MANUAL" "--criteria" "retired criteria interface stays absent from the manual"
assert_not_contains "$MANUAL" "developer instructions" "retired engine policy stays absent from the manual"
assert_not_contains "$MANUAL" "it never edits code" "manual states edit ownership, not an edit prohibition"
assert_not_contains "$MANUAL" "works the batch sequentially" "wave-work organization is the fixer's call"
assert_not_contains "$MANUAL" "below the engine's critical/high class" "manual routes findings by the worker's judgment, not a severity class"
assert_not_contains "$MANUAL" "one fail-safe shell step" "manual states the fail-safe order, not shell packaging"

echo "worker bootstrap:"
assert_file "$BOOTSTRAP" "worker bootstrap exists"
assert_contains "$BOOTSTRAP" "Use doperpowers:reviewing-prs" "bootstrap names the runtime skill"
assert_contains "$BOOTSTRAP" "dispatcher-pinned copy" "bootstrap routes the protocol through the dispatcher-pinned file"
assert_contains "$BOOTSTRAP" '{{SKILL_FILE}}' "bootstrap binds the canonical skill path"
assert_contains "$BOOTSTRAP" "over any same-named skill" "bootstrap outranks PR-controlled workspace skills"
assert_contains "$BOOTSTRAP" '{{IMPLEMENT_PROTOCOL_FILE}}' "bootstrap binds the canonical implement contract path"
assert_contains "$BOOTSTRAP" '{{BIND_READY_FILE}}' "bootstrap binds the dispatcher-owned startup barrier"
assert_not_contains "$BOOTSTRAP" "{{PR_BODY}}" "no inlined PR body (the worker reads the PR live via gh)"
assert_not_contains "$BOOTSTRAP" "{{ISSUE_BODY}}" "no inlined ticket body (the worker reads the ticket live via gh)"
assert_not_contains "$BOOTSTRAP" "{{ENGINE_BLOCK}}" "no engine-block binding (engine text lives in the skill)"
assert_contains "$BOOTSTRAP" "{{RISK_MANIFEST}}" "bootstrap supplies the BASE-ref risk-surface snapshot"
assert_contains "$BOOTSTRAP" "{{REPO_FACTS}}" "bootstrap supplies the BASE-ref repo-facts snapshot"
want_rboot="{{AUTO_MERGE}} {{BASE_IS_DEFAULT}} {{BASE_REF}} {{BIND_READY_FILE}} {{BOARD_SCRIPTS}} {{CODEX_REVIEW_EFFORT}} {{CODEX_REVIEW_MODEL}} {{DEFAULT_BRANCH}} {{HEAD_REF}} {{HEAD_SHA}} {{IMPLEMENT_PROTOCOL_FILE}} {{ISSUE_LIST}} {{ISSUE_NUMBER}} {{PR_NUMBER}} {{PR_URL}} {{REPO_FACTS}} {{REPO}} {{REVIEW_ENGINE}} {{RISK_MANIFEST}} {{SKILL_FILE}} {{TECH_DEBT_ISSUE}}"
got_rboot="$(grep -o '{{[A-Z_]*}}' "$BOOTSTRAP" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [[ "$got_rboot" == "$want_rboot" ]]; then
    pass "bootstrap placeholder set is exact"
else
    fail "bootstrap placeholder set is exact"
    echo "    expected: $want_rboot"
    echo "    actual:   $got_rboot"
fi

echo "dispatch wiring:"
assert_contains "$DISPATCH" 'BOOTSTRAP_TEMPLATE="$SKILL_DIR/references/review-worker-bootstrap.md"' "dispatcher renders the worker bootstrap"
assert_contains "$DISPATCH" "P_IMPLEMENT_PROTOCOL_FILE" "dispatcher binds the implement contract path"
assert_not_contains "$DISPATCH" "review-worker-protocol.md" "dispatcher no longer bypasses the skill entrypoint"
assert_missing "$OLD_PROTOCOL" "retired protocol reference file is removed"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
