#!/usr/bin/env bash
# Test: subagent-driven-execution skill
# Verifies that the skill is loaded and follows correct workflow
#
# No drill coverage: this test asks the agent to *describe* SDE (string-
# matches its verbal explanation against expected keywords like
# "self-review", "skeptical", "worktree", "Step 1", "loop"). Drill scenarios
# test behavior (real subagent dispatch, plan-following, review loops),
# not description-recall. Kept by design.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

CLAUDE_PROMPT_TIMEOUT="${CLAUDE_PROMPT_TIMEOUT:-90}"

echo "=== Test: subagent-driven-execution skill ==="
echo ""

# Answer-line patterns for the fixed-structure prompts below. Each anchors its
# option to the START of the answer value, because grep matches the letters
# anywhere: a bare ".*no" also fires on the "no" inside "not"/"cannot", so
# "yes, but not directly" — the design error the assertion exists to catch —
# read as "no". "<" is excluded from the run-up so a placeholder echoed back
# from the prompt ("<yes or no>") is never read as a choice. Matching stays
# case-insensitive: that is assert_contains's deliberate choice (test-helpers.sh).
#
# The same anchor decides which option a two-option answer picked: unanchored,
# "task text pasted into the prompt, not the spec path" passed as "spec".
# One leading word is tolerated so "a spec"/"the spec"/"spec" all count,
# which is far short of reaching the losing option's own mention of it.
PAT_SELF_REVIEW_REPLACES_NO='Self-review replaces external review:[^a-zA-Z<]*no'
PAT_REQUIREMENTS_AS_SPEC='Requirements reach the executor as:[^a-zA-Z<]*[a-z]* *spec'
PAT_EXECUTOR_READS_SPEC_YES='Executor must read the whole spec:[^a-zA-Z<]*yes'

# These patterns are the test, so pin their verdicts on the near-miss phrasings
# before spending live model time. Fields: want|pattern variable|answer line.
check_answer_patterns() {
    local failures=0 want var line got
    while IFS='|' read -r want var line; do
        [ -n "$want" ] || continue
        if printf '%s\n' "$line" | grep -qi "${!var}"; then got=match; else got=nomatch; fi
        if [ "$got" != "$want" ]; then
            printf '  [FAIL] answer-line pattern: wanted %s, got %s\n    pattern: %s\n    line:    %s\n' \
                "$want" "$got" "${!var}" "$line"
            failures=$((failures + 1))
        fi
    done
    [ "$failures" -eq 0 ]
}

echo "Pre-flight: answer-line assertion patterns..."

check_answer_patterns <<'FIXTURES' || exit 1
nomatch|PAT_SELF_REVIEW_REPLACES_NO|Self-review replaces external review: yes, notionally
nomatch|PAT_SELF_REVIEW_REPLACES_NO|Self-review replaces external review: <yes or no>
match|PAT_SELF_REVIEW_REPLACES_NO|Self-review replaces external review: no
match|PAT_SELF_REVIEW_REPLACES_NO|**Self-review replaces external review:** No
match|PAT_REQUIREMENTS_AS_SPEC|Requirements reach the executor as: the spec path
match|PAT_REQUIREMENTS_AS_SPEC|Requirements reach the executor as: spec path
match|PAT_REQUIREMENTS_AS_SPEC|**Requirements reach the executor as:** the spec path - it reads the whole spec and owns one milestone
match|PAT_REQUIREMENTS_AS_SPEC|Requirements reach the executor as: the spec path (not the task text pasted into the prompt)
nomatch|PAT_REQUIREMENTS_AS_SPEC|Requirements reach the executor as: task text pasted into the prompt
nomatch|PAT_REQUIREMENTS_AS_SPEC|Requirements reach the executor as: task text pasted into the prompt, not the spec path
nomatch|PAT_REQUIREMENTS_AS_SPEC|Requirements reach the executor as: <the spec path or task text pasted into the prompt>
nomatch|PAT_EXECUTOR_READS_SPEC_YES|Executor must read the whole spec: no, only its milestone
nomatch|PAT_EXECUTOR_READS_SPEC_YES|Executor must read the whole spec: no (it gets a brief)
nomatch|PAT_EXECUTOR_READS_SPEC_YES|Executor must read the whole spec: no
nomatch|PAT_EXECUTOR_READS_SPEC_YES|Executor must read the whole spec: <yes or no>
match|PAT_EXECUTOR_READS_SPEC_YES|Executor must read the whole spec: yes
match|PAT_EXECUTOR_READS_SPEC_YES|**Executor must read the whole spec:** Yes, and owns one milestone of it
FIXTURES

echo "  [PASS] Answer-line patterns read the chosen option, not stray letters"
echo ""

# Test 1: Verify skill can be loaded
echo "Test 1: Skill loading..."

output=$(run_claude "What is the subagent-driven-execution skill? Describe its key steps briefly." "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "subagent-driven-execution\|Subagent-Driven Execution\|Subagent Driven" "Skill is recognized"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "read.*spec\|Read the spec\|Plan of Work\|milestone" "Mentions reading the spec"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 2: Verify skill describes correct workflow order
echo "Test 2: Workflow ordering..."

output=$(run_claude "In the subagent-driven-execution skill, what comes first: spec compliance review or code quality review? Answer using exactly this structure:
First: <review type>
Second: <review type>" "$CLAUDE_PROMPT_TIMEOUT")

if assert_order "$output" "First:.*spec.*compliance" "Second:.*code.*quality" "Spec compliance before code quality"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 3: Verify self-review is mentioned
echo "Test 3: Self-review requirement..."

output=$(run_claude "Does the subagent-driven-execution skill require executors to self-review before handoff, and can self-review replace the external reviews? Answer using exactly this structure:
Self-review required: <yes or no>
Self-review replaces external review: <yes or no>" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "Self-review required:.*yes" "Mentions self-review"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "$PAT_SELF_REVIEW_REPLACES_NO" "Self-review does not replace external review"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 4: Verify plan is read once
echo "Test 4: Plan reading efficiency..."

output=$(run_claude "In subagent-driven-execution, how many times should the controller read the plan file? When does this happen?" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "once\|one time\|single" "Read plan once"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "Step 1\|beginning\|start\|Load Plan" "Read at beginning"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 5: Verify spec compliance reviewer is skeptical
echo "Test 5: Spec compliance reviewer mindset..."

output=$(run_claude "What is the spec compliance reviewer's attitude toward the executor's report in subagent-driven-execution?" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "not trust\|don't trust\|skeptical\|verify.*independently\|suspiciously" "Reviewer is skeptical"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "read.*code\|inspect.*code\|verify.*code\|examin.*code\|look.*at.*code\|read.*diff\|inspect.*diff\|examin.*diff\|review.*diff\|check.*code\|against.*code\|code itself\|actual code\|actual implementation" "Reviewer reads code"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 6: Verify review loops
echo "Test 6: Review loop requirements..."

output=$(run_claude "In subagent-driven-execution, what happens if a reviewer finds issues? Is it a one-time review or a loop?" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "loop\|again\|repeat\|until.*approved\|until.*compliant" "Review loops mentioned"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "executor.*fix\|fix.*issues" "Executor fixes issues"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 7: Verify requirements are handed over as the spec, read whole
# Both assertions anchor to their answer line: grep is line-based, so the
# label and the chosen option must appear together. An unanchored
# alternation here matched incidental prose and passed without reading the
# answer at all.
echo "Test 7: Task context provision..."

output=$(run_claude "In subagent-driven-execution, the controller dispatches a task-executor subagent to do one milestone of the spec's Plan of Work. Answer using exactly this structure, choosing one option per line:
Requirements reach the executor as: <the spec path or task text pasted into the prompt>
Executor must read the whole spec: <yes or no>" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "$PAT_REQUIREMENTS_AS_SPEC" "Requirements handed over as the spec path"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "$PAT_EXECUTOR_READS_SPEC_YES" "Executor reads the whole spec"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 8: Verify worktree requirement
echo "Test 8: Worktree requirement..."

output=$(run_claude "What workflow skills are required before using subagent-driven-execution? List any prerequisites or required skills." "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "worktree" "Mentions worktree requirement"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 9: Verify main branch warning
echo "Test 9: Main branch red flag..."

output=$(run_claude "In subagent-driven-execution, is it okay to start implementation directly on the main branch?" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "worktree\|feature.*branch\|not.*main\|never.*main\|avoid.*main\|don't.*main\|consent\|permission" "Warns against main branch"; then
    : # pass
else
    exit 1
fi

echo ""

echo "=== All subagent-driven-execution skill tests passed ==="
