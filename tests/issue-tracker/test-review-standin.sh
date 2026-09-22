#!/usr/bin/env bash
# Structural invariants for the review stand-in — the seat that hosts a review
# nobody owns: its protocol, its dispatch bootstrap, the wave-board reference
# its agent opens at runtime, and the operator reference. Assertions pin
# STRUCTURE (headings, ordering, tokens, placeholder sets) — not sentences.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROTOCOL="$REPO_ROOT/skills/issue-tracker/references/review-standin-protocol.md"
MANUAL="$REPO_ROOT/skills/issue-tracker/references/review-loop.md"
BOOTSTRAP="$REPO_ROOT/skills/issue-tracker/references/review-standin-bootstrap.md"
WAVEBOARD="$REPO_ROOT/skills/issue-tracker/references/wave-board.md"
DISPATCH="$REPO_ROOT/skills/issue-tracker/scripts/review-dispatch.sh"
# The retired skill's name is BUILT, never written: spelled out anywhere in this
# file it would be its own hit in the route sweep below.
retired="qa-loop""s"
RETIRED_SKILL="$REPO_ROOT/skills/$retired"

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
    # `|| true`: under `set -euo pipefail` a missing needle makes the whole
    # pipeline non-zero, and the assignment would abort the suite silently
    # instead of reporting the failed assertion.
    first="$(grep -nF -- "$2" "$1" 2>/dev/null | cut -d: -f1 | head -1 || true)"
    second="$(grep -nF -- "$3" "$1" 2>/dev/null | cut -d: -f1 | head -1 || true)"
    if [[ -n "$first" && -n "$second" && "$first" -lt "$second" ]]; then
        pass "$4"
    else
        fail "$4"; echo "    expected before: $2"; echo "    expected after:  $3"
    fi
}

echo "the retired skill:"
assert_missing "$RETIRED_SKILL" "the retired skill's directory is gone — the loop is the qa-loop agent"
routes() {
    grep -rnE "doperpowers:$retired|skills/$retired|tests/$retired" \
        "$REPO_ROOT/skills" "$REPO_ROOT/agents" "$REPO_ROOT/hooks" "$REPO_ROOT/scripts" \
        "$REPO_ROOT/tests" "$REPO_ROOT/CLAUDE.md" "$REPO_ROOT/README.md" 2>/dev/null
}
if [[ -n "$(routes)" ]]; then
    fail "nothing routes to the retired skill any more"
    routes | sed 's/^/    /'
else
    pass "nothing routes to the retired skill any more"
fi

echo "stand-in protocol — structure:"
assert_file "$PROTOCOL" "the stand-in protocol exists"
want_headings="Role
Position
Dispatch
Relay"
got_headings="$(grep '^## ' "$PROTOCOL" 2>/dev/null | sed 's/^## //' || true)"
if [[ "$got_headings" == "$want_headings" ]]; then
    pass "the four sections exist in order"
else
    fail "the four sections exist in order"
    echo "    expected:"; printf '      %s\n' $want_headings
    echo "    actual:";   printf '      %s\n' $got_headings
fi
assert_contains "$PROTOCOL" "no review judgment" "the stand-in judges nothing — the agent does"
assert_before "$PROTOCOL" "## Position" "## Dispatch" "positioning precedes the dispatch it positions for"

echo "stand-in protocol — positioning:"
assert_contains "$PROTOCOL" 'git checkout --detach {{HEAD_SHA}}' "a PR review positions at the briefed head"
assert_contains "$PROTOCOL" "baseRefName,headRefName,headRefOid" "the api mode resolves base and head off the PR"
assert_contains "$PROTOCOL" "ls-remote --symref origin HEAD" "a scale review resolves its base from origin's own symref"
assert_contains "$PROTOCOL" "aggregate range: none" "an epic with no integration branch says so in the brief"
assert_contains "$PROTOCOL" "needs-human" "a ref that will not resolve parks instead of reviewing the wrong range"

echo "stand-in protocol — the dispatch:"
assert_contains "$PROTOCOL" "doperpowers:qa-loop" "the review is one qa-loop agent"
assert_not_contains "$PROTOCOL" "doperpowers:$retired" "the retired skill is not named"
assert_contains "$PROTOCOL" 'isolation: "worktree"' "the agent reviews in its own worktree"
assert_contains "$PROTOCOL" "ticket body file:" "the claim's body file rides the brief when the bootstrap bound one"
assert_contains "$PROTOCOL" "your dispatcher answers escalations; return for them" "the brief carries the escalation sentence the agent expects"
assert_contains "$PROTOCOL" "review level floor:" "the brief relays the dispatcher-owned floor"
assert_contains "$PROTOCOL" "auto-merge:" "the brief relays the merge switch"

echo "stand-in protocol — the relay:"
assert_contains "$PROTOCOL" "NEEDS_PANEL" "panel levels come back to the seat that has the Workflow tool"
assert_contains "$PROTOCOL" "code-review.js" "the panel runs review-code's own workflow"
assert_contains "$PROTOCOL" "Workflow(" "the panel call is the Workflow tool's"
assert_contains "$PROTOCOL" "PARKED" "a park ends the turn and resumes through the answer relay"
assert_contains "$PROTOCOL" "ESCALATE" "the three escalation kinds are answered here"
assert_contains "$PROTOCOL" "ready-for-architect" "a design gap on a PR goes back to the architect lane"
assert_contains "$PROTOCOL" "board-register.sh" "a scale design gap registers the corrective child first"
assert_contains "$PROTOCOL" "no dismissal channel" "a stand-in holds no design intent to dismiss a finding with"
assert_contains "$PROTOCOL" "ENGINE-UNAVAILABLE" "an engine outage is echoed, not judged"
assert_contains "$PROTOCOL" "DONE" "a finished review ends the turn"
assert_contains "$PROTOCOL" "git worktree remove" "the agent's worktree is removed on DONE"
assert_not_contains "$PROTOCOL" "BIND_READY" "no startup barrier survives in the protocol"
assert_not_contains "$PROTOCOL" "RISK_MANIFEST" "no manifest snapshot rides the stand-in"

echo "stand-in bootstrap:"
assert_file "$BOOTSTRAP" "the stand-in bootstrap exists"
assert_contains "$BOOTSTRAP" "dispatcher-pinned copy" "bootstrap routes the protocol through the dispatcher-pinned file"
assert_contains "$BOOTSTRAP" '{{PROTOCOL_FILE}}' "bootstrap binds the stand-in protocol's path"
assert_not_contains "$BOOTSTRAP" '{{SKILL_FILE}}' "no skill path binding survives"
assert_not_contains "$BOOTSTRAP" "Use doperpowers:$retired" "the bootstrap invokes no skill"
assert_not_contains "$BOOTSTRAP" '{{BIND_READY_FILE}}' "no startup barrier binding survives"
assert_not_contains "$BOOTSTRAP" '{{MANIFEST_REF}}' "no manifest ref binding survives"
assert_not_contains "$BOOTSTRAP" '{{RISK_MANIFEST}}' "no risk-surface snapshot rides the prompt"
assert_not_contains "$BOOTSTRAP" '{{REPO_FACTS}}' "no repo-facts snapshot rides the prompt"
assert_not_contains "$BOOTSTRAP" "{{PR_BODY}}" "no inlined PR body (the agent reads the PR live via gh)"
assert_not_contains "$BOOTSTRAP" "{{ISSUE_BODY}}" "no inlined ticket body"
assert_contains "$BOOTSTRAP" '{{IMPLEMENT_PROTOCOL_FILE}}' "bootstrap binds the canonical implement contract path"
assert_contains "$BOOTSTRAP" '`ROLE`: {{ROLE}}' "bootstrap binds the seat's role"
assert_contains "$BOOTSTRAP" '`REVIEW_MODE`: {{REVIEW_MODE}}' "bootstrap binds the review variant"
assert_contains "$BOOTSTRAP" '`CLOSURE_PACKAGE`: {{CLOSURE_PACKAGE}}' "bootstrap binds the scale variant's entry artifact"
assert_contains "$BOOTSTRAP" '`WORKER_NAME`: {{WORKER_NAME}}' "bootstrap binds the registry identity"
assert_contains "$BOOTSTRAP" "<!-- mode:pr -->" "PR-only prose is fenced into a mode block"
assert_contains "$BOOTSTRAP" "<!-- mode:scale -->" "scale-only prose is fenced into a mode block"
# Spec acceptance 5's roster, plus PROTOCOL_FILE. The per-mode split is
# test-bootstrap-parity.sh's; this is the set the template may name at all.
want_rboot="{{AUTO_MERGE}} {{BASE_REF}} {{BOARD_SCRIPTS}} {{CLOSURE_PACKAGE}} {{ENV_TRACKER_ISSUE}} {{HEAD_REF}} {{HEAD_SHA}} {{IMPLEMENT_PROTOCOL_FILE}} {{INTEGRATION_REF}} {{ISSUE_LIST}} {{ISSUE_NUMBER}} {{ISSUE_URL}} {{PR_NUMBER}} {{PR_URL}} {{PROTOCOL_FILE}} {{REPO}} {{REVIEW_CODE_DIR}} {{REVIEW_LEVEL}} {{REVIEW_MODE}} {{ROLE}} {{TECH_DEBT_ISSUE}} {{TICKET_BODY_FILE}} {{WORKER_NAME}}"
got_rboot="$(grep -o '{{[A-Z_]*}}' "$BOOTSTRAP" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [[ "$got_rboot" == "$want_rboot" ]]; then
    pass "bootstrap placeholder set is exact"
else
    fail "bootstrap placeholder set is exact"
    echo "    expected: $want_rboot"
    echo "    actual:   $got_rboot"
fi

echo "wave board reference:"
assert_file "$WAVEBOARD" "wave-board reference exists"
assert_contains "$WAVEBOARD" '"disposition"' "board schema carries a disposition slot per item"
assert_contains "$WAVEBOARD" '"items"' "board frontmatter is a strict JSON object with items"
assert_contains "$WAVEBOARD" "<review-tmp>/pr-<PR>-fix-wave-" "board path lives in the agent's scratch dir"
assert_not_contains "$WAVEBOARD" ".doperpowers/qa" "board reference carries no worktree path a PR could pre-create"
assert_contains "$WAVEBOARD" "symlink" "board reference names the symlink hazard that forbids worktree residency"
assert_contains "$WAVEBOARD" "rebuild the board from the trail" "long-park tmp loss has a documented recovery"
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
assert_contains "$WAVEBOARD" "never written into a fixer prompt" "the ledger path is undisclosed to the fixer tree"
assert_not_contains "$WAVEBOARD" "binding barrier" "the retired barrier no longer supplies the ledger"
assert_not_contains "$WAVEBOARD" "dispatcher control directory" "the ledger lives in the agent's own scratch dir now"
assert_contains "$WAVEBOARD" "ledger content fingerprint" "late ledger tampering is detected before push"
assert_contains "$WAVEBOARD" "remote head differs from <push-base>" "unexpected remote movement blocks automatic salvage"
assert_before "$WAVEBOARD" "fresh remote SHA" "git reset --hard <wave-base>" "remote publication is ruled out before local reset"
assert_contains "$WAVEBOARD" "If this was the last wave the protocol's cap allows" "wave-cap contamination parks instead of exceeding the cap"
assert_contains "$WAVEBOARD" "Agent tool, \`general-purpose\`" "the fixer is dispatched through the Agent tool"
assert_before "$WAVEBOARD" "record <wave-base> before dispatch" "Dispatch the wave's fixer" "wave boundary is captured before dispatch"
assert_before "$WAVEBOARD" "stop the authorized fixer and every descendant" "QUIESCENCE GATE" "descendants stop before quiescence"
assert_before "$WAVEBOARD" "QUIESCENCE GATE" "discard the contaminated board" "quiescence precedes contaminated-state disposal"
assert_before "$WAVEBOARD" "grade ONLY the snapshot" "- FIXED:<sha>" "submitted snapshot precedes grading branches"
assert_contains "$WAVEBOARD" "never rewrite history" "rejected fixes are corrected fix-forward, not rebased away"
assert_not_contains "$WAVEBOARD" "Stage only the files" "no staging-means mandate — the board-file ban and mixed-commit grading carry it"
assert_contains "$WAVEBOARD" "commit the board file" "the board-file ban survives in the fixer never list"
assert_contains "$WAVEBOARD" "appears in the commits being pushed" "push gate scans commit contents for the board, not just the working tree"
assert_contains "$WAVEBOARD" "published history is never rewritten" "the board-removal exception is scoped to unpushed commits"

echo "operator reference:"
assert_file "$MANUAL" "the review loop's operator reference exists"
assert_contains "$MANUAL" "## Dedupe & sweep policy" "operation manual preserves operating policy"
assert_contains "$MANUAL" "## Adopting a repo (checklist)" "operation manual preserves setup guidance"
assert_contains "$MANUAL" "## Migrating an installed workflow" "an installed Action copy has a migration note"
assert_contains "$MANUAL" "owner reviews" "the dedupe table leads with the owner's own review"
assert_contains "$MANUAL" "agents/qa-loop.md" "the manual points at the agent that IS the loop"
assert_contains "$MANUAL" "references/review-standin-protocol.md" "...and at the stand-in's protocol"
assert_contains "$MANUAL" "references/review-standin-bootstrap.md" "...and at the stand-in's bootstrap"
assert_not_contains "$MANUAL" '`SKILL.md`' "the retired skill is no longer a piece of the loop"
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
assert_not_contains "$MANUAL" "review-engine.sh" "manual no longer names the codex engine script"
assert_not_contains "$MANUAL" "codex login" "the codex CLI is no longer a runner prerequisite"
assert_contains "$MANUAL" "REVIEW_LEVEL" "manual documents the operator's level floor"
assert_not_contains "$MANUAL" "REVIEW_ACK_POLLS" "the retired barrier's knobs are gone from the manual"
assert_not_contains "$MANUAL" "one fail-safe shell step" "manual states the fail-safe order, not shell packaging"

echo "dispatch wiring:"
assert_contains "$DISPATCH" 'BOOTSTRAP_TEMPLATE="$SKILL_DIR/references/review-standin-bootstrap.md"' "dispatcher renders the stand-in bootstrap"
assert_contains "$DISPATCH" 'PROTOCOL_FILE="$SKILL_DIR/references/review-standin-protocol.md"' "dispatcher pins the stand-in protocol"
assert_contains "$DISPATCH" "P_IMPLEMENT_PROTOCOL_FILE" "dispatcher binds the implement contract path"
assert_not_contains "$DISPATCH" "REVIEW_ACK_POLLS" "the barrier's acknowledgement poll is gone"
assert_not_contains "$DISPATCH" "bind-ready.json" "the barrier file is gone"
assert_not_contains "$DISPATCH" "accepted-commits.json" "the dispatcher no longer owns the accepted-commit ledger"
assert_contains "$REPO_ROOT/skills/issue-tracker/references/pr-review-dispatch.yml" \
  "skills/issue-tracker/scripts/review-dispatch.sh" \
  "the installed GH Action runs the dispatcher at its issue-tracker home"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
