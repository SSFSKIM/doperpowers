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
# Positioning is section-local: the harness's worktree isolation belongs in
# Workspace and must NOT reach the engine's reviewer dispatches, so those two
# assertions need a section, not the whole file.
section() {
    awk -v want="$1" '
        $0 == want { inside = 1; next }
        inside && (/^## / || /^### /) { exit }
        inside { print }
    ' "$AGENT"
}
assert_text_contains() {
    if printf '%s\n' "$1" | grep -Fq -- "$2" 2>/dev/null; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in section: $4"; fi
}
assert_text_not_contains() {
    if printf '%s\n' "$1" | grep -Fq -- "$2" 2>/dev/null; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in section: $4"; else pass "$3"; fi
}
assert_text_order() {
    local first second
    first="$(printf '%s\n' "$1" | grep -nF -m1 -- "$2" | cut -d: -f1 || true)"
    second="$(printf '%s\n' "$1" | grep -nF -m1 -- "$3" | cut -d: -f1 || true)"
    if [[ -n "$first" && -n "$second" && "$first" -lt "$second" ]]; then
        pass "$4"
    else
        fail "$4"; echo "    expected '$2' before '$3'"; echo "    in section: $5"
    fi
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
assert_contains "$AGENT" "doperpowers:reviewer-" "the single-reviewer rungs are dispatched by name"
assert_contains "$AGENT" "Lens for this review:" "a lensed call appends the engine's lens line"
assert_contains "$AGENT" "review-trail" "the trail is posted as a typed board comment"
assert_contains "$AGENT" "mktemp -d" "control state lives in a scratch directory outside the worktree"
assert_contains "$AGENT" "hash" "a panel findings file is pinned by hash in the trail"

# The harness cuts an isolated child at the REPOSITORY'S MAIN CHECKOUT head, not
# the dispatcher's — two live board drills parked on it before their first engine
# round (Task 11, 2026-09-22). So the agent positions its own workspace, and the
# reviewers it dispatches are pointed at that path instead of being isolated onto
# the same wrong range. Both halves are section-local: `isolation` belongs in
# Workspace and nowhere near the engine's dispatches.
echo "positioning — the agent finds the reviewed head itself:"
workspace="$(section '### Workspace')"
engine="$(section '## Engine')"
[[ -n "$workspace" ]] || { echo "  [FAIL] the Workspace section exists"; FAILURES=$((FAILURES + 1)); }
[[ -n "$engine" ]] || { echo "  [FAIL] the Engine section exists"; FAILURES=$((FAILURES + 1)); }
assert_contains "$AGENT" "head branch: <branch>" "the brief carries the head branch the agent fetches"
assert_text_contains "$workspace" 'isolation: "worktree"' \
    "the workspace is still the harness's isolated worktree" "Workspace"
assert_text_contains "$workspace" "MAIN CHECKOUT head" \
    "...but the body says where that worktree is actually cut" "Workspace"
# Each branch rides an explicit refspec: a single-branch clone's fetch of a bare
# name moves only FETCH_HEAD, leaving no origin/<head branch> for the push gate
# and no origin/<base> for the engine.
assert_text_contains "$workspace" "git fetch origin '+refs/heads/<head branch>:refs/remotes/origin/<head branch>'" \
    "...so the agent's first act fetches the head branch into its tracking ref" "Workspace"
assert_text_contains "$workspace" "'+refs/heads/<base>:refs/remotes/origin/<base>'" \
    "...and the base into its own, which the engine and the manifests read" "Workspace"
assert_not_contains "$AGENT" "git fetch origin <head branch>" "no fetch names a bare, unquoted branch"
assert_contains "$AGENT" "git push origin 'HEAD:<head branch>'" "the wave push quotes the branch it names"
assert_not_contains "$AGENT" "git push origin HEAD:<head branch>" "...and no unquoted push survives"
assert_contains "$AGENT" "git show 'origin/<base>:.doperpowers/risk-surfaces.md'" "the base-ref manifest read quotes the ref"
# Quoting cannot make an arbitrary ref safe to paste into a command the agent
# composes itself — an apostrophe is a legal ref character — so the safeguard is
# a charset gate: a name outside it parks instead of reaching a shell.
assert_text_contains "$workspace" 'A branch name is used in a command only if it matches `^[A-Za-z0-9._/-]+$`;' \
    "a branch name reaches a command only inside a safe charset" "Workspace"
assert_text_contains "$workspace" "any other name is a park naming the branch, never a command" \
    "...and any other name parks rather than being run" "Workspace"
assert_not_contains "$AGENT" "Quote branch names in every" "quoting is no longer offered as the safeguard"
assert_text_contains "$workspace" "git checkout --detach <head>" \
    "...and detaches at the brief's head" "Workspace"
assert_text_contains "$workspace" "\`git rev-parse HEAD\` must then print the brief's" \
    "...and the position is verified against the brief before the review starts" "Workspace"
assert_text_contains "$workspace" "cannot reach is a park" \
    "...a head the fetch cannot reach parks rather than reviewing the wrong range" "Workspace"
assert_text_contains "$workspace" "never check out another ref in this worktree" \
    "...and the no-ref-switch rule holds from that point" "Workspace"
assert_text_contains "$engine" "The repository under review is at" \
    "a single-rung reviewer is pointed at the agent's worktree by the location line" "Engine"
assert_text_not_contains "$engine" "isolation" \
    "...and is dispatched without it — an isolated reviewer lands on the main checkout" "Engine"
assert_text_contains "$engine" "as the workflow's \`repo\`" \
    "a handed-up panel is run over the dispatcher's checkout, named as the workflow's repo arg" "Engine"

# A re-pin is a commit the owner pushed onto the PR branch, so the head the
# review holds is no longer the PR's head: auditing or merging the old one would
# drop the repaired contract from the very range the verdict covers.
echo "a re-pin moves the reviewed head:"
escalations="$(section '### The three escalations')"
[[ -n "$escalations" ]] || { echo "  [FAIL] the escalations section exists"; FAILURES=$((FAILURES + 1)); }
assert_text_contains "$escalations" "git merge --ff-only 'origin/<head branch>'" \
    "on a re-pin answer the agent fast-forwards to the owner's pushed pin commit" "The three escalations"
assert_text_contains "$escalations" "prints the PR's new head" \
    "...verifies the position against the PR's new head" "The three escalations"
assert_text_contains "$escalations" "the audit and the merge use that head" \
    "...and audits and merges that head, not the one it was briefed" "The three escalations"
# The adopted head carries the owner's commit, which no engine round has seen;
# the merge pins the head the final engine round reviewed, so it needs one.
assert_text_contains "$escalations" "A head adopted after a re-pin is merge-eligible only after a fresh engine" \
    "...and that head is merge-eligible only once a fresh engine round has covered it" "The three escalations"
rereview="$(section '## Re-review')"
assert_text_contains "$rereview" "or a re-pin that moved the head" \
    "Re-review's trigger includes the head a re-pin moved" "Re-review"

echo "the fixer's view of the scratch directory:"
assert_contains "$AGENT" "absolute board path" "a fixer is given the absolute wave-board path the wave-board contract requires"
assert_contains "$AGENT" "no fixer prompt ever names" "the accepted-commit ledger's path is the one thing withheld from a fixer"
assert_not_contains "$AGENT" "Never write that path into a fixer prompt" "secrecy is not blanket over the scratch directory — that would make the wave impossible"

echo "the terminal outcomes:"
escalate="$(section '## Escalate')"
[[ -n "$escalate" ]] || { echo "  [FAIL] the Escalate section exists"; FAILURES=$((FAILURES + 1)); }
assert_text_contains "$escalate" "The trail is therefore a precondition, not aftercare" \
    "the trail is a precondition for an auto-merge-on terminal path" "Escalate"
assert_text_order "$escalate" "The trail is therefore a precondition, not aftercare" "gh pr merge <pr>" \
    "the trail is posted before a merge can auto-close the ticket and trigger cancellation" "Escalate"
assert_contains "$AGENT" "--json mergedAt" "running checks are waited out by polling the PR's merge state"
assert_contains "$AGENT" "every 60 seconds for up to 20 minutes" "the wait for running checks is bounded"
assert_contains "$AGENT" "auto-merge armed on <sha>; the board's finalize pass writes done" "an armed auto-merge returns DONE with its verbatim second line"
assert_contains "$AGENT" "the PR comment IS the park record" "ticketless observation mode parks on the PR instead of the board"
assert_contains "$AGENT" "the corrective child you recommend" "a scale defect hands its corrective child to the dispatcher"
assert_not_contains "$AGENT" 'ready-for-architect "scale review' "a scale defect no longer moves the epic itself"
assert_not_contains "$AGENT" "board-transition.sh <ticket> ready-for-architect" "the agent never writes the ready-for-architect edge"
assert_contains "$AGENT" "never yours to write" "ready-for-architect is the answerer's edge, on every path"

# The sweep reads each posted trail as the review's progress. A hand-up of any
# kind leaves the review waiting on its dispatcher, so the trail so far goes up
# before every one of them — not only before the design-gap that can end it.
echo "the trail precedes every hand-up:"
trail_section="$(section '## Review Trail')"
assert_text_contains "$trail_section" "before every \`ESCALATE\` or \`NEEDS_PANEL\` return" \
    "the trail so far is posted before any escalation or panel hand-up" "Review Trail"
assert_not_contains "$AGENT" "a design-gap answer may end your review outright" \
    "...and no design-gap-only wording survives"

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
