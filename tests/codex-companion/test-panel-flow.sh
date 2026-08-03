#!/usr/bin/env bash
# Mock-driven e2e for the review-panel workflow
# (skills/codex-companion/workflows/code-review.mjs), run through the real
# `workflow` verb against the mock codex app-server.
#
# Scope: the argument contract, adaptive lens derivation, the finder fan-out
# (including the clean sentinel every finder carries), how each finder's render
# becomes coverage plus a candidate pool, and the binding verifier's mechanical
# postconditions with their single repair retry. Every assertion reads an
# artifact the run actually produced: the mock's turns.jsonl / threads.jsonl /
# spawn-<pid>.json and the verb's stdout JSON.
#
# ORDERING: the mock's scenario is consumed in GLOBAL request order, but the
# finders run in parallel and race for their slots. So the deriver turn (first)
# and the verifier turns (after the barrier) are at fixed positions, while the
# finder slots are handed out nondeterministically. Every finder assertion here
# is therefore order-insensitive — a sorted pool, a sorted lens set, coverage
# keyed by finder label — and each case gives all its finders renders with the
# SAME finding count so the candidate ids are invariant under permutation while
# the finding TEXT still differs (a panel that ran one review and reused it
# would show the same title three times).
#
# Each case gets its own scratch: the mock's scenario counter and turn log are
# global to a mock dir.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-mock.sh
source "$HERE/lib-mock.sh"

PANEL="$REPO_ROOT/skills/codex-companion/workflows/code-review.mjs"
FIXTURES="$HERE/fixtures/review-texts"
fail=0
scratches=()
scratch=""
repo=""

command -v jq >/dev/null || { echo "jq is required for this test"; exit 2; }

ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fail=1; }

assert_eq() { # desc want got
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$2', got '$3')"; fi
}

assert_contains() { # desc file needle
  if grep -Fq -- "$3" "$2"; then ok "$1"; else bad "$1 (no '$3' in $2)"; fi
}

cleanup() {
  local dir
  for dir in "${scratches[@]:-}"; do
    [ -n "$dir" ] || continue
    rm -rf "$dir"
  done
}
trap cleanup EXIT

new_case() { # name scenario-json
  echo "-- case: $1"
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/codex-panel-$1-XXXXXX")"
  # TMPDIR usually ends in a slash; `tr -s` rather than a bash replacement
  # because bash 3.2 keeps the backslash from a `\/` replacement string.
  scratch="$(printf '%s' "$scratch" | tr -s /)"
  scratches+=("$scratch")
  mock_env "$scratch"
  repo="$scratch/repo"
  git init -q -b main "$repo"
  git -C "$repo" -c user.email=t@example.com -c user.name=t \
    -c commit.gpgsign=false commit -q --allow-empty -m base
  printf '%s' "$2" > "$scratch/mockstate/scenario.json"
}

run_panel() { # args-json → rc in $rc, stdout in $scratch/out.json
  rc=0
  node "$RUNTIME" workflow --script "$PANEL" --args "$1" --cwd "$repo" \
    > "$scratch/out.json" 2> "$scratch/err.log" || rc=$?
}

turn_count() {
  if [ -f "$CODEX_MOCK_DIR/turns.jsonl" ]; then
    wc -l < "$CODEX_MOCK_DIR/turns.jsonl" | tr -d ' '
  else
    echo 0
  fi
}

# "no turn was spent" is only meaningful next to a run that actually ran: a
# workflow that never started also spends no turns. Every turn-count assertion
# below therefore carries the run's exit code with it.
rc_and_turns() { printf '%s:%s' "$rc" "$(turn_count)"; }

turn_field() { # index field-path — MISSING when no turn was logged at all
  jq -r -s --argjson i "$1" ".[\$i] | $2" "$CODEX_MOCK_DIR/turns.jsonl" 2>/dev/null || echo MISSING
}

# --- scenario builders -------------------------------------------------------
# The mock reads {turns:[...]} and clamps past the end, so an over-long run
# silently reuses the last slot; every case asserts its exact turn count.
msg_turn()    { jq -nc --arg m "$1" '{finalMessage:$m}'; }
review_turn() { jq -nc --arg t "$1" '{reviewText:$t}'; }
scenario()    { printf '{"turns":[%s]}' "$(printf '%s,' "$@" | sed 's/,$//')"; }

# --- panel observables -------------------------------------------------------
# The clean sentinel EVERY finder carries. Real clean native reviews are
# free-form prose (fixtures/review-texts/clean-prose-unsentineled.md), so
# without it a finder that found nothing is indistinguishable from one that
# went dark — see the spec's clean-render probe. The sentinel sits ALONE on its
# own line: asked for it at the end of a sentence, a model reproduces the
# sentence's punctuation, and extraction wants the bare line.
SENTINEL='If your review finds no issues, end your final message with exactly this line (alone on its own line):
No material findings.'

# Every developer_instructions override any worker was spawned with, one
# JSON-encoded string per line (the scalpel lenses are multi-line), sorted so
# the finder race cannot decide the outcome.
actual_lenses() {
  jq -c '.argv[] | select(startswith("developer_instructions="))' \
    "$CODEX_MOCK_DIR"/spawn-*.json | LC_ALL=C sort
}

# What actual_lenses must be for a panel whose scalpels carry these mandates:
# the sweep gets the sentinel ALONE (format only — the lens-free sweep must
# keep its attention unsteered), each scalpel its mandate plus the sentinel.
expected_lenses() { # mandate...
  {
    jq -nc --arg s "$SENTINEL" '"developer_instructions=" + $s'
    local m
    for m in "$@"; do
      jq -nc --arg m "$m" --arg s "$SENTINEL" '"developer_instructions=" + $m + "\n" + $s'
    done
  } | LC_ALL=C sort
}

# The model each spawned worker started its thread on, sorted with counts.
thread_models() {
  jq -r 'select(.method=="thread/start") | .params.model' \
    "$CODEX_MOCK_DIR/threads.jsonl" | LC_ALL=C sort | uniq -c | sed 's/^ *//'
}

# One line per verifier turn — first and repair alike, in the order spent —
# rendered by the caller's jq filter over that turn's request params.
verifier_turns() { # jq-filter over the turn's params
  jq -r "select(.method==\"turn/start\")
    | .params.input[0].text as \$t
    | select ((\$t | startswith(\"You are the binding verifier\")) or (\$t | startswith(\"Your verdict set violated\")))
    | .params | $1" "$CODEX_MOCK_DIR/turns.jsonl"
}

verifier_prompts() { # → every verifier prompt, concatenated, for grepping
  jq -r 'select(.method=="turn/start")
    | .params.input[0].text as $t
    | select(($t | startswith("You are the binding verifier")) or ($t | startswith("Your verdict set violated")))
    | $t' "$CODEX_MOCK_DIR/turns.jsonl"
}

# result readers — id/verdict/duplicate triples, sorted, so a nondeterministic
# pool ORDER can never green or red an assertion about pool CONTENT.
pool_ids()      { jq -r '[.result.pool[].id] | sort | join(",")' "$scratch/out.json"; }
pool_titles()   { jq -r '[.result.pool[].title] | sort | join(" | ")' "$scratch/out.json"; }
coverage_rows() { jq -c '[.result.coverage[] | {finder, lens, status, stubs}]' "$scratch/out.json"; }
verdict_lines() {
  jq -r '[.result.verified[] | "\(.id)=\(.verdict)\(if .duplicateOf then "→"+.duplicateOf else "" end)\(if .priority then "/"+.priority else "" end)"] | sort | join(" ")' \
    "$scratch/out.json"
}

# --- finder renders ----------------------------------------------------------
# Shaped exactly like the real renders the extractor was calibrated on
# (fixtures/review-texts/campaign-r1[45].md): a `- [P#] Title — path:lines` head
# with an indented body. Two findings each, distinct titles, so the six
# candidate ids are invariant while the titles still prove three distinct
# reviews actually ran.
SWEEP_TEXT='# Codex Review

Target: branch diff against main

Two defects in the lane scheduler.

Full review comments:

- [P0] Require the worker role to match the charged lane — skills/implementing/scripts/implement-dispatch.sh:169-170
  This state-only test charges the source-lane worker to the destination lane, so one live handoff blocks every unrelated Architect.

- [P2] Honor engine labels on scale-review epics — skills/reviewing-prs/scripts/review-dispatch.sh:439
  dispatch_epic ignores the ticket label and always uses WORKER_ENGINE, so the experiment runs through the wrong model route.'

SCALPEL1_TEXT='# Codex Review

Target: branch diff against main

The IMPACT cursor shares the daemon registry namespace.

Full review comments:

- [P1] Move the sweep cursor outside the daemon registry — skills/issue-tracker/scripts/board-sweep.sh:429
  daemon-list.sh adds the cursor as a bogus fleet row and daemon-retire.sh can delete it.

- [P3] Document the lane-aware wake state — skills/issue-tracker/scripts/board-answer.sh:115
  The published command table still says the ticket always returns to in-progress.'

SCALPEL2_TEXT='# Codex Review

Target: branch diff against main

Two gaps in the scale-review dispatch path.

Full review comments:

- [P2] Fetch child PR heads before deleted-branch scale review — skills/reviewing-prs/scripts/review-dispatch.sh:466
  A squash-merged child head is not an ancestor of the default branch, so the required detach fails.

- [P1] Guard the impact cursor against retirement — skills/issue-tracker/scripts/daemon-retire.sh:88-92
  _resolve_uuid resolves impact-scan as a daemon, so retirement corrupts the cursor.'

# One finding each — for the verifier cases, where the pool must be small
# enough to write exact verdict sets against by hand.
ONE_A='# Codex Review

Full review comments:

- [P1] Charge the handoff to the source lane — skills/implementing/scripts/implement-dispatch.sh:169
  The destination lane is charged a worker it does not own.'

ONE_B='# Codex Review

Full review comments:

- [P2] Move the sweep cursor outside the daemon registry — skills/issue-tracker/scripts/board-sweep.sh:429
  The cursor is addressable by daemon commands.'

CLEAN_TEXT="$(cat "$FIXTURES/no-findings.md")"
DRIFT_TEXT="$(cat "$FIXTURES/partial-drift.md")"

# ---------------------------------------------------------------------------
# 1. The whole panel on the derived path: one deriver turn, three finders
#    (sweep + two scalpels) each carrying the clean sentinel, one verifier whose
#    verdict set satisfies the postconditions on the first try.
# ---------------------------------------------------------------------------
VERDICTS_OK='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","priority":"P0","comment":"the lane is charged twice"},
  {"id":"sweep#2","verdict":"REFUTED","comment":"the label is read one frame up"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","priority":"P1","comment":"registry namespace collision confirmed"},
  {"id":"scalpel-1#2","verdict":"CONFIRMED","duplicateOf":"sweep#1","comment":"same lane accounting defect"},
  {"id":"scalpel-2#1","verdict":"CONFIRMED","priority":"P2","comment":"the head ref is genuinely unfetched"},
  {"id":"scalpel-2#2","verdict":"REFUTED","comment":"retirement validates the shape first"}
]}'

new_case derive "$(scenario \
  "$(msg_turn '{"lenses":["watch the auth paths.","check removed guards."]}')" \
  "$(review_turn "$SWEEP_TEXT")" \
  "$(review_turn "$SCALPEL1_TEXT")" \
  "$(review_turn "$SCALPEL2_TEXT")" \
  "$(msg_turn "$VERDICTS_OK")")"
run_panel '{"base":"main"}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the full panel exits 0 having spent deriver + 3 finders + verifier" "0:5" "$(rc_and_turns)"
assert_eq "the first turn is the deriver agent turn, not a review" "turn/start" "$(turn_field 0 .method)"
assert_eq "deriver runs on the panel's deriver model" "gpt-5.6-sol" "$(turn_field 0 .params.model)"
assert_eq "deriver runs at medium effort" "medium" "$(turn_field 0 .params.effort)"
assert_eq "deriver turn is schema-forced" "object" "$(turn_field 0 '.params.outputSchema.type')"
assert_eq "exactly three finders ran, as native reviews" 3 \
  "$(jq -rs '[.[] | select(.method=="review/start")] | length' "$CODEX_MOCK_DIR/turns.jsonl")"
assert_eq "every finder reviews the caller's base as a native branch target" \
  '[{"type":"baseBranch","branch":"main"},{"type":"baseBranch","branch":"main"},{"type":"baseBranch","branch":"main"}]' \
  "$(jq -cs '[.[] | select(.method=="review/start") | .params.target]' "$CODEX_MOCK_DIR/turns.jsonl")"

turn_field 0 '.params.input[0].text' > "$scratch/prompt.txt"
assert_contains "deriver prompt names the diff base" "$scratch/prompt.txt" "merge-base(HEAD, main)"
assert_contains "deriver prompt caps mandate length" "$scratch/prompt.txt" "AT MOST TWO SIMPLE SENTENCES"
assert_contains "deriver prompt caps mandate count" "$scratch/prompt.txt" "between 0 and 5"
assert_contains "deriver prompt says sharper beats padding" "$scratch/prompt.txt" "fewer, sharper mandates beat coverage padding"

assert_eq "derived lenses reach the result" \
  '["watch the auth paths.","check removed guards."]' "$(jq -c '.result.lenses' "$scratch/out.json")"
assert_eq "every finder carries the clean sentinel; only the scalpels carry a mandate" \
  "$(expected_lenses "watch the auth paths." "check removed guards.")" "$(actual_lenses)"
assert_eq "finder effort defaults to xhigh, on every finder's own app-server" "3" \
  "$(jq -r '.argv[] | select(. == "model_reasoning_effort=xhigh")' "$CODEX_MOCK_DIR"/spawn-*.json | wc -l | tr -d ' ')"
assert_eq "finder model defaults to sol — deriver, finders and verifier all on it" \
  "5 gpt-5.6-sol" "$(thread_models)"
assert_contains "the run logs the panel shape" "$scratch/err.log" "panel: sweep + 2 scalpels"
# Each finder's label is its own journal key, so a resume gives each lane back
# its OWN cached review; finders sharing a label would be re-matched by
# completion order, which the race makes arbitrary.
assert_eq "each finder runs as its own named lane" "scalpel-1 scalpel-2 sweep" \
  "$(grep -o 'start review:[a-z0-9-]*' "$scratch/err.log" | sed 's/start review://' | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//')"

assert_eq "coverage carries one row per finder, keyed by label, with its mandate" \
  '[{"finder":"sweep","lens":null,"status":"ok","stubs":2},{"finder":"scalpel-1","lens":"watch the auth paths.","status":"ok","stubs":2},{"finder":"scalpel-2","lens":"check removed guards.","status":"ok","stubs":2}]' \
  "$(coverage_rows)"
assert_eq "the pool is every finder's stubs under that finder's own id" \
  "scalpel-1#1,scalpel-1#2,scalpel-2#1,scalpel-2#2,sweep#1,sweep#2" "$(pool_ids)"
assert_eq "three DISTINCT reviews reached the pool, not one review counted thrice" \
  "Document the lane-aware wake state | Fetch child PR heads before deleted-branch scale review | Guard the impact cursor against retirement | Honor engine labels on scale-review epics | Move the sweep cursor outside the daemon registry | Require the worker role to match the charged lane" \
  "$(pool_titles)"

assert_eq "the verifier spends exactly one turn when its verdicts hold" "1" \
  "$(verifier_prompts | grep -c '^You are the binding verifier' || true)"
assert_eq "no repair turn is spent on a contract-clean verdict set" "0" \
  "$(verifier_prompts | grep -c '^Your verdict set violated' || true)"
assert_eq "the verifier runs on sol at high effort" "gpt-5.6-sol high" \
  "$(verifier_turns '"\(.model) \(.effort)"')"
assert_eq "the verifier turn is schema-forced on a verdicts array" "array" \
  "$(verifier_turns '.outputSchema.properties.verdicts.type')"
verifier_prompts > "$scratch/vprompt.txt"
assert_contains "the verifier is told to re-inspect the code itself" "$scratch/vprompt.txt" "re-inspect the code yourself"
assert_contains "the verifier prompt names the diff base" "$scratch/vprompt.txt" "merge-base(HEAD, main)"
assert_contains "the verifier prompt carries the candidate pool verbatim" "$scratch/vprompt.txt" '"id": "scalpel-2#2"'
# A lens-directed claim reads differently once you know which mandate produced
# it, so the roster rides above the candidates.
assert_contains "the verifier is shown the sweep as lens-free" "$scratch/vprompt.txt" "- sweep: (lens-free sweep)"
assert_contains "the verifier is shown each scalpel's mandate" "$scratch/vprompt.txt" "- scalpel-2: check removed guards."
assert_eq "the verified verdicts reach the result untouched" \
  "scalpel-1#1=CONFIRMED/P1 scalpel-1#2=CONFIRMED→sweep#1 scalpel-2#1=CONFIRMED/P2 scalpel-2#2=REFUTED sweep#1=CONFIRMED/P0 sweep#2=REFUTED" \
  "$(verdict_lines)"

# ---------------------------------------------------------------------------
# 2. Caller bypass: `args.lenses` spends no deriver turn and is passed through.
#    The scenario would hand back a DIFFERENT lens set, so a workflow that
#    derived anyway fails on both the turn count and the lens text. Both finders
#    drift out of format here: a drifted finder is a failed one whose stubs are
#    withheld, and an all-failed panel leaves nothing for the verifier to judge.
# ---------------------------------------------------------------------------
new_case bypass "$(scenario \
  "$(msg_turn '{"lenses":["derived-should-not-happen."]}')" \
  "$(review_turn "$DRIFT_TEXT")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the bypass run exits 0 having spent no deriver turn and no verifier turn" "0:2" "$(rc_and_turns)"
assert_eq "caller lenses pass through untouched" \
  '["only one mandate."]' "$(jq -c '.result.lenses' "$scratch/out.json")"
assert_contains "the run logs one scalpel" "$scratch/err.log" "panel: sweep + 1 scalpels"
assert_eq "the caller's mandate still gets the sentinel appended" \
  "$(expected_lenses "only one mandate.")" "$(actual_lenses)"
assert_eq "a drifted finder is reported as extraction-failed with no stubs" \
  '[{"finder":"sweep","lens":null,"status":"extraction-failed","stubs":0},{"finder":"scalpel-1","lens":"only one mandate.","status":"extraction-failed","stubs":0}]' \
  "$(coverage_rows)"
assert_eq "the drifted finder's partial stubs never reach the pool" \
  '[]' "$(jq -c '.result.pool' "$scratch/out.json")"
assert_eq "an empty pool is verified vacuously, not left unverified" \
  '[]' "$(jq -c '.result.verified' "$scratch/out.json")"

# ---------------------------------------------------------------------------
# 3. Caller lenses are still capped and cleaned: at most five, trimmed, blanks
#    dropped — the caller is not trusted with the owner's cap either.
# ---------------------------------------------------------------------------
new_case bypass-cap "$(scenario \
  "$(msg_turn '{"lenses":["derived-should-not-happen."]}')" \
  "$(review_turn "$CLEAN_TEXT")")"
run_panel '{"base":"main","lenses":["  a.  ","","b.","c.","d.","e.","f."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the capped bypass run spends one turn per surviving finder and no more" "0:5" "$(rc_and_turns)"
assert_eq "caller lenses sliced to five, trimmed, blanks dropped" \
  '["a.","b.","c.","d."]' "$(jq -c '.result.lenses' "$scratch/out.json")"
assert_eq "the cleaned mandates are what the finders actually receive" \
  "$(expected_lenses "a." "b." "c." "d.")" "$(actual_lenses)"

# ---------------------------------------------------------------------------
# 4. The cap binds the model too: a deriver that returns more than five
#    mandates is truncated rather than obeyed.
# ---------------------------------------------------------------------------
new_case derive-cap "$(scenario \
  "$(msg_turn '{"lenses":["one.","two.","three.","four.","five.","six.","seven."]}')" \
  "$(review_turn "$CLEAN_TEXT")")"
run_panel '{"base":"main"}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "over-long derivation still exits 0, and only six finders run" "0:7" "$(rc_and_turns)"
assert_eq "derived lenses capped at five" 5 "$(jq -r '.result.lenses | length' "$scratch/out.json")"
assert_eq "the cap keeps the first five" \
  '["one.","two.","three.","four.","five."]' "$(jq -c '.result.lenses' "$scratch/out.json")"

# ---------------------------------------------------------------------------
# 5. Zero lenses: the deriver is entitled to answer "nothing to sharpen", and
#    the panel then IS the sweep. Its clean render is a real verdict (the
#    sentinel it was instructed to emit), so the pool is empty and the verifier
#    is never paid for.
# ---------------------------------------------------------------------------
new_case zero-lens "$(scenario \
  "$(msg_turn '{"lenses":[]}')" \
  "$(review_turn "$CLEAN_TEXT")")"
run_panel '{"base":"main"}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "a zero-lens panel spends the deriver and the sweep only" "0:2" "$(rc_and_turns)"
assert_contains "the run logs a sweep-only panel" "$scratch/err.log" "panel: sweep + 0 scalpels"
assert_eq "the lone sweep still carries the sentinel, and nothing else" \
  "$(expected_lenses)" "$(actual_lenses)"
assert_eq "a sentinelled clean review is coverage, not a failure" \
  '[{"finder":"sweep","lens":null,"status":"ok","stubs":0}]' "$(coverage_rows)"
assert_eq "nothing to verify leaves an empty verdict set, never a null one" \
  '[]' "$(jq -c '.result.verified' "$scratch/out.json")"

# ---------------------------------------------------------------------------
# 6. Verifier omission: a verdict set that skips a candidate is rejected
#    mechanically, repaired ONCE, and — if the repair is no better — abandoned.
#    A null `verified` is what Task 4 turns into an interrupted verdict; the
#    pool rides along so the findings are not silently lost.
#    This case also carries explicit model routing, the only place the finder
#    model is observable at all (it rides thread/start, not review/start).
# ---------------------------------------------------------------------------
SHORT_VERDICTS='{"verdicts":[{"id":"sweep#1","verdict":"CONFIRMED","priority":"P1","comment":"real"}]}'
new_case verifier-omission "$(scenario \
  "$(review_turn "$ONE_A")" \
  "$(review_turn "$ONE_B")" \
  "$(msg_turn "$SHORT_VERDICTS")" \
  "$(msg_turn "$SHORT_VERDICTS")")"
run_panel '{"base":"main","lenses":["only one mandate."],"finderModel":"gpt-5.6-terra","finderEffort":"high","verifierModel":"gpt-5.6-luna","verifierEffort":"xhigh"}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "an unrepairable verifier still exits 0, having spent exactly one retry" "0:4" "$(rc_and_turns)"
assert_eq "the pool the verifier was given had both candidates" \
  "scalpel-1#1,sweep#1" "$(pool_ids)"
assert_eq "an incomplete verdict set is refused rather than half-trusted" \
  "null" "$(jq -c '.result.verified' "$scratch/out.json")"
assert_eq "the unverified pool survives on the result for the caller to see" 2 \
  "$(jq -r '.result.pool | length' "$scratch/out.json")"
assert_contains "the run names the postcondition that failed" "$scratch/err.log" \
  "verifier postconditions failed: missing verdict for scalpel-1#1"
assert_eq "exactly one repair turn is spent — never a second" "1" \
  "$(verifier_prompts | grep -c '^Your verdict set violated' || true)"
verifier_prompts | sed -n '/^Your verdict set violated/,$p' > "$scratch/repair.txt"
assert_contains "the repair prompt names the violation" "$scratch/repair.txt" \
  "Your verdict set violated the contract: missing verdict for scalpel-1#1"
assert_contains "the repair prompt demands the FULL set, not a patch" "$scratch/repair.txt" \
  "Return the FULL corrected verdicts array covering every candidate id exactly once"
assert_contains "the repair prompt re-sends the candidates" "$scratch/repair.txt" '"id": "scalpel-1#1"'
# The repair rides a FRESH thread, so anything the first turn was told and this
# one is not, the repairing verifier simply does not know — and case 8 makes its
# answer BINDING. The whole contract therefore travels with the repair.
assert_contains "the repair prompt restates the verifier's role" "$scratch/repair.txt" \
  "You are the binding verifier of a multi-reviewer panel"
assert_contains "the repair prompt keeps the re-inspect instruction" "$scratch/repair.txt" \
  "re-inspect the code yourself before judging"
assert_contains "the repair prompt keeps the verdict definitions" "$scratch/repair.txt" \
  "CONFIRMED (you can name the concrete failure) or REFUTED"
assert_contains "the repair prompt keeps the duplicateOf and priority rules" "$scratch/repair.txt" \
  "Mark true duplicates with duplicateOf pointing at the strongest formulation"
assert_contains "the repair prompt keeps the diff base" "$scratch/repair.txt" "merge-base(HEAD, main)"
assert_contains "the repair prompt keeps the lens map" "$scratch/repair.txt" "- sweep: (lens-free sweep)"
assert_eq "finders run on the caller's finder model, the verifier on its own" \
  "2 gpt-5.6-luna
2 gpt-5.6-terra" "$(thread_models)"
assert_eq "the verifier's own model and effort ride both its turns" \
  "gpt-5.6-luna xhigh
gpt-5.6-luna xhigh" "$(verifier_turns '"\(.model) \(.effort)"')"
assert_eq "the caller's finder effort reaches both finders" "2" \
  "$(jq -r '.argv[] | select(. == "model_reasoning_effort=high")' "$CODEX_MOCK_DIR"/spawn-*.json | wc -l | tr -d ' ')"

# ---------------------------------------------------------------------------
# 7. A duplicateOf cycle: every id is covered exactly once, so only the graph
#    check catches it. Same fate as an omission — one repair, then abandoned.
# ---------------------------------------------------------------------------
CYCLIC='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":"scalpel-1#1","comment":"same as the other"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#1","comment":"same as the other"}
]}'
new_case verifier-cycle "$(scenario \
  "$(review_turn "$ONE_A")" \
  "$(review_turn "$ONE_B")" \
  "$(msg_turn "$CYCLIC")" \
  "$(msg_turn "$CYCLIC")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "a cyclic verdict set costs exactly one repair turn" "0:4" "$(rc_and_turns)"
assert_eq "a complete but cyclic verdict set is refused" "null" "$(jq -c '.result.verified' "$scratch/out.json")"
assert_contains "the run names the cycle" "$scratch/err.log" "duplicateOf cycle at"

# ---------------------------------------------------------------------------
# 8. The repair that works: a phantom id and a duplicate pointing at a REFUTED
#    finding are both caught, and a corrected second answer is accepted.
# ---------------------------------------------------------------------------
BAD_VERDICTS='{"verdicts":[
  {"id":"ghost#1","verdict":"CONFIRMED","comment":"invented"},
  {"id":"sweep#1","verdict":"REFUTED","comment":"not real"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#1","comment":"dup of a refuted one"}
]}'
GOOD_VERDICTS='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","priority":"P1","comment":"reinspected: real"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#1","comment":"same defect"}
]}'
new_case verifier-repair "$(scenario \
  "$(review_turn "$ONE_A")" \
  "$(review_turn "$ONE_B")" \
  "$(msg_turn "$BAD_VERDICTS")" \
  "$(msg_turn "$GOOD_VERDICTS")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the repaired run spends the same four turns" "0:4" "$(rc_and_turns)"
assert_contains "a verdict for a candidate that was never raised is caught" "$scratch/err.log" "phantom id ghost#1"
assert_contains "a duplicate of a refuted finding is caught" "$scratch/err.log" "duplicateOf targets refuted sweep#1"
assert_eq "the corrected verdict set is accepted and replaces the rejected one" \
  "scalpel-1#1=CONFIRMED→sweep#1 sweep#1=CONFIRMED/P1" "$(verdict_lines)"

# ---------------------------------------------------------------------------
# 9. Dead finders: a worker that dies is not a clean review. Its lane is
#    reported dead so the loss is visible in the coverage, not inferred from an
#    empty pool.
# ---------------------------------------------------------------------------
new_case dead-finders '{"turns":[{"die":true}]}'
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "a panel whose finders all die still returns a result, each retried once" "0:4" "$(rc_and_turns)"
assert_eq "each dead finder is reported dead, with its mandate" \
  '[{"finder":"sweep","lens":null,"status":"dead","stubs":0},{"finder":"scalpel-1","lens":"only one mandate.","status":"dead","stubs":0}]' \
  "$(coverage_rows)"
assert_eq "no verifier turn is spent on a panel that produced nothing" "0" \
  "$(verifier_prompts | wc -l | tr -d ' ')"

# ---------------------------------------------------------------------------
# 10. No base: refused before any worker is spawned.
# ---------------------------------------------------------------------------
new_case no-base '{"turns":[{"finalMessage":"{\"lenses\":[]}"}]}'
run_panel '{}'
# The exit code and the turn count alone cannot tell "the script refused" from
# "the script never ran", so the refusal message rides the same assertion.
assert_eq "no base is refused by the script itself, before any turn" \
  "1:0:code-review workflow requires args.base" \
  "$rc:$(turn_count):$(head -1 "$scratch/err.log")"

if [ "$fail" -eq 0 ]; then echo "panel flow: all cases passed"; fi
exit "$fail"
