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
# "task text pasted into the prompt, not a brief file path" passed as "brief".
# One leading word is tolerated so "a brief"/"the brief"/"brief" all count,
# which is far short of reaching the losing option's own mention of it.
PAT_SELF_REVIEW_REPLACES_NO='Self-review replaces external review:[^a-zA-Z<]*no'
PAT_REQUIREMENTS_AS_BRIEF='Requirements reach the executor as:[^a-zA-Z<]*[a-z]* *brief'
PAT_EXECUTOR_READS_PLAN_NO='Executor must read the plan file:[^a-zA-Z<]*no'

# Free-prose assertion: the reviewer engages with the artifact rather than the
# executor's report. One engagement verb plus one artifact noun, in that order,
# replaces an alternation that enumerated verb/noun pairs and so turned the
# verdict on vocabulary: it accepted "reads the code" but rejected "verify
# against the actual diff" and "judge the implementation" — the wording
# agents/task-reviewer.md itself uses. An answer that only restates the report
# names no artifact at all, which is what keeps this from being too broad.
PAT_REVIEWER_READS_ARTIFACT='\(read\|inspect\|examin\|verify\|check\|review\|judge\|look at\|against\|evaluate\).*\(code\|diff\|implementation\)\|actual \(code\|diff\|implementation\)\|code itself'

# These patterns are the test, so pin their verdicts on the near-miss phrasings
# before spending live model time. Fields: want|pattern variable|answer line.
check_answer_patterns() {
    local failures=0 want var line got
    while IFS='|' read -r want var line; do
        [ -n "$want" ] || continue
        if printf '%s\n' "$line" | grep -qi "${!var}"; then got=match; else got=nomatch; fi
        if [ "$got" != "$want" ]; then
            printf '  [FAIL] assertion pattern: wanted %s, got %s\n    pattern: %s\n    line:    %s\n' \
                "$want" "$got" "${!var}" "$line"
            failures=$((failures + 1))
        fi
    done
    [ "$failures" -eq 0 ]
}

echo "Pre-flight: assertion patterns..."

check_answer_patterns <<'FIXTURES' || exit 1
nomatch|PAT_SELF_REVIEW_REPLACES_NO|Self-review replaces external review: yes, notionally
nomatch|PAT_SELF_REVIEW_REPLACES_NO|Self-review replaces external review: <yes or no>
match|PAT_SELF_REVIEW_REPLACES_NO|Self-review replaces external review: no
match|PAT_SELF_REVIEW_REPLACES_NO|**Self-review replaces external review:** No
match|PAT_REQUIREMENTS_AS_BRIEF|Requirements reach the executor as: a brief file path
match|PAT_REQUIREMENTS_AS_BRIEF|Requirements reach the executor as: brief file path
match|PAT_REQUIREMENTS_AS_BRIEF|**Requirements reach the executor as:** a brief file path - the brief holds the full text of the task
match|PAT_REQUIREMENTS_AS_BRIEF|Requirements reach the executor as: a brief file path (not the task text pasted into the prompt)
nomatch|PAT_REQUIREMENTS_AS_BRIEF|Requirements reach the executor as: task text pasted into the prompt
nomatch|PAT_REQUIREMENTS_AS_BRIEF|Requirements reach the executor as: task text pasted into the prompt, not a brief file path
nomatch|PAT_REQUIREMENTS_AS_BRIEF|Requirements reach the executor as: <a brief file path or task text pasted into the prompt>
nomatch|PAT_EXECUTOR_READS_PLAN_NO|Executor must read the plan file: yes, but not directly
nomatch|PAT_EXECUTOR_READS_PLAN_NO|Executor must read the plan file: yes (it cannot be skipped)
nomatch|PAT_EXECUTOR_READS_PLAN_NO|Executor must read the plan file: yes - it has no brief
nomatch|PAT_EXECUTOR_READS_PLAN_NO|Executor must read the plan file: yes
nomatch|PAT_EXECUTOR_READS_PLAN_NO|Executor must read the plan file: <yes or no>
match|PAT_EXECUTOR_READS_PLAN_NO|Executor must read the plan file: no
match|PAT_EXECUTOR_READS_PLAN_NO|**Executor must read the plan file:** No
match|PAT_REVIEWER_READS_ARTIFACT|Verify every implementation claim against the actual diff.
match|PAT_REVIEWER_READS_ARTIFACT|Judge the code against the task brief and global constraints.
match|PAT_REVIEWER_READS_ARTIFACT|trust the diff and judge the implementation on its merits
match|PAT_REVIEWER_READS_ARTIFACT|Read the code, do not trust the report.
match|PAT_REVIEWER_READS_ARTIFACT|Inspect the actual implementation.
nomatch|PAT_REVIEWER_READS_ARTIFACT|Accept the executor's report and approve if it claims success.
FIXTURES

echo "  [PASS] Assertion patterns read the chosen option and the artifact, not stray letters"
echo ""

# Test 1: Verify skill can be loaded
echo "Test 1: Skill loading..."

output=$(run_claude "What is the subagent-driven-execution skill? Describe its key steps briefly." "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "subagent-driven-execution\|Subagent-Driven Execution\|Subagent Driven" "Skill is recognized"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "Load Plan\|read.*plan\|extract.*tasks" "Mentions loading plan"; then
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

if assert_contains "$output" "$PAT_REVIEWER_READS_ARTIFACT" "Reviewer reads the code or diff"; then
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

# Test 7: Verify requirements are handed over as a brief file
# Both assertions anchor to their answer line: grep is line-based, so the
# label and the chosen option must appear together. An unanchored
# alternation here matched incidental prose ("the brief holds the full text
# of the task") and passed without reading the answer at all.
echo "Test 7: Task context provision..."

output=$(run_claude "In subagent-driven-execution, the controller dispatches a task-executor subagent to do one task of the plan. Answer using exactly this structure, choosing one option per line:
Requirements reach the executor as: <a brief file path or task text pasted into the prompt>
Executor must read the plan file: <yes or no>" "$CLAUDE_PROMPT_TIMEOUT")

if assert_contains "$output" "$PAT_REQUIREMENTS_AS_BRIEF" "Requirements handed over as a brief file"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "$PAT_EXECUTOR_READS_PLAN_NO" "Executor is not sent to the plan file"; then
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
