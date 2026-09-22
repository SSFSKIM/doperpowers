#!/usr/bin/env bash
#
# Structural fence over the qa-loop agent body. The body IS the board's review
# loop, so its prose is behavior: these asserts pin the frontmatter, the
# section order, the bins, the escalation kinds, the return lines, the caps,
# and the load-bearing clauses a future edit could silently drop. They also
# pin the placeholder-free rehoming — a dispatcher template string left in an
# agent body reaches the model unrendered.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT="$REPO_ROOT/agents/qa-loop.md"

FAILURES=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_file() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; fi
}
assert_contains() {
    if grep -Fq -- "$2" "$1" 2>/dev/null; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" "$1" 2>/dev/null; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}

echo "agent identity:"
assert_file "$AGENT" "agents/qa-loop.md exists"
assert_contains "$AGENT" "name: qa-loop" "frontmatter names the agent"
assert_contains "$AGENT" "model: sol" "the agent is pinned to sol"
assert_contains "$AGENT" "effort: high" "the agent is pinned to high effort"

# `|| true`: grep finding nothing under `set -e` would abort the suite before
# the assertion could report.
disallowed="$(grep -m1 '^disallowedTools:' "$AGENT" 2>/dev/null || true)"
if [[ "$disallowed" == *Skill* ]]; then
    pass "Skill is blocked — no repository instruction routes the agent into a review skill"
else
    fail "Skill is blocked — no repository instruction routes the agent into a review skill"
    echo "    disallowedTools line: ${disallowed:-<missing>}"
fi
if [[ -n "$disallowed" && "$disallowed" != *Agent* ]]; then
    pass "Agent stays available — the agent dispatches reviewers and fixers"
else
    fail "Agent stays available — the agent dispatches reviewers and fixers"
    echo "    disallowedTools line: ${disallowed:-<missing>}"
fi

echo "protocol section structure:"
want_headings="Role
Orient
Engine
Compliance Audit
Join
Triage
Fix Waves
Re-review
Escalate
Scale review
Authority
Review Trail"
got_headings="$(grep '^## ' "$AGENT" 2>/dev/null | sed 's/^## //' || true)"
if [[ "$got_headings" == "$want_headings" ]]; then
    pass "the twelve protocol sections exist in order"
else
    fail "the twelve protocol sections exist in order"
    echo "    expected:"; printf '%s\n' "$want_headings" | sed 's/^/      /'
    echo "    actual:";   printf '%s\n' "$got_headings" | sed 's/^/      /'
fi

echo "triage bins and escalation kinds:"
for bin in WAVE "TOO BIG" LOG INVALID; do
    assert_contains "$AGENT" "$bin" "the $bin bin is named"
done
for kind in spec-conflict design-gap dismissal; do
    assert_contains "$AGENT" "$kind" "the $kind escalation is named"
done

echo "the return contract:"
assert_contains "$AGENT" '`DONE`' "DONE is a return line"
assert_contains "$AGENT" 'PARKED <question>' "PARKED carries the question"
assert_contains "$AGENT" 'NEEDS_PANEL level=<xhigh|max> base=<ref> baseCommit=<sha> headCommit=<sha> round=<n>' "NEEDS_PANEL carries the pinned range and round"
assert_contains "$AGENT" 'ESCALATE kind=<spec-conflict|design-gap|dismissal> finding=<id>' "ESCALATE carries the kind and the finding"
assert_contains "$AGENT" 'ENGINE-UNAVAILABLE' "ENGINE-UNAVAILABLE is a return line"

echo "the caps:"
assert_contains "$AGENT" "4 waves" "four fix waves per review"
assert_contains "$AGENT" "5 engine rounds" "five engine rounds per review"
assert_contains "$AGENT" "closing wave" "the closing wave stands outside the wave cap"
assert_contains "$AGENT" "45 minutes" "a hung engine call is bounded at 45 minutes"

echo "load-bearing clauses:"
assert_contains "$AGENT" "P2 or P3" "dismissal is a non-blocker channel only"
assert_contains "$AGENT" "[trail] dismissed" "an accepted dismissal has a verbatim trail line"
assert_contains "$AGENT" "[trail] re-pin" "a re-pin has a verbatim trail line"
assert_contains "$AGENT" "plausibly speaks" "dismissal needs a spec that speaks to the finding"
assert_contains "$AGENT" "reads the pointed section" "the agent verifies the pointer rather than taking it"
assert_contains "$AGENT" "not in the tech-debt" "a dismissal never enters the deferred-work sink"
assert_contains "$AGENT" "which governs" "a spec-conflict answer may settle precedence"
assert_contains "$AGENT" "one re-pin" "the re-pin channel is bounded at one per review"
assert_contains "$AGENT" "second design-gap" "a second design-gap belongs to the human"
assert_contains "$AGENT" 'isolation: "worktree"' "the engine's reviewers run isolated from this checkout"
assert_contains "$AGENT" "doperpowers:reviewer-" "the single-reviewer rungs are dispatched by name"
assert_contains "$AGENT" "Lens for this review:" "a lensed call appends the engine's lens line"
assert_contains "$AGENT" "review-trail" "the trail is posted as a typed board comment"
assert_contains "$AGENT" "mktemp -d" "control state lives in a scratch directory outside the worktree"
assert_contains "$AGENT" "hash" "a panel findings file is pinned by hash in the trail"

echo "the fixer's view of the scratch directory:"
assert_contains "$AGENT" "absolute board path" "a fixer is given the absolute wave-board path the wave-board contract requires"
assert_contains "$AGENT" "no fixer prompt ever names" "the accepted-commit ledger's path is the one thing withheld from a fixer"
assert_not_contains "$AGENT" "Never write that path into a fixer prompt" "secrecy is not blanket over the scratch directory — that would make the wave impossible"

echo "the terminal outcomes:"
assert_contains "$AGENT" "--json mergedAt" "running checks are waited out by polling the PR's merge state"
assert_contains "$AGENT" "every 60 seconds for up to 20 minutes" "the wait for running checks is bounded"
assert_contains "$AGENT" "auto-merge armed on <sha>; the board's finalize pass writes done" "an armed auto-merge returns DONE with its verbatim second line"
assert_contains "$AGENT" "the PR comment IS the park record" "ticketless observation mode parks on the PR instead of the board"
assert_contains "$AGENT" "the corrective child you recommend" "a scale defect hands its corrective child to the dispatcher"
assert_not_contains "$AGENT" 'ready-for-architect "scale review' "a scale defect no longer moves the epic itself"
assert_not_contains "$AGENT" "board-transition.sh <ticket> ready-for-architect" "the agent never writes the ready-for-architect edge"
assert_contains "$AGENT" "never yours to write" "ready-for-architect is the answerer's edge, on every path"

echo "the rehoming is complete:"
assert_not_contains "$AGENT" "{{" "no dispatcher placeholder survives in the agent body"
assert_not_contains "$AGENT" "Workflow(" "the agent never calls the workflow a subagent cannot reach"
assert_not_contains "$AGENT" "BIND_READY_FILE" "the binding barrier is gone"
assert_not_contains "$AGENT" "MANIFEST_REF" "the agent reads the manifests from the base ref itself"
assert_not_contains "$AGENT" "SKILL_FILE" "the body is the contract — no skill file to open"
assert_not_contains "$AGENT" "qa-loops" "the retired skill is never named"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
