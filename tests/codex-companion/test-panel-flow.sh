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
DIE='{"die":true}'

# A scenario that addresses its finders BY LENS instead of by the global turn
# counter: the racing finders each get the behavior whose key prefixes the
# developer_instructions they were spawned with, and spend no global slot, so
# `turns` is left holding the deriver and verifier slots alone. This is the only
# way to give one lane of the fan-out an outcome that differs from its
# neighbour's — a dead sweep beside a live scalpel — and it also pins WHICH
# review text lands in which finder, so a per-finder title is assertable.
lens_scenario() { # turns-json-list prefix behavior-json [prefix behavior-json ...]
  local turns="$1" by='{}'; shift
  while [ "$#" -gt 0 ]; do
    by="$(jq -c --arg k "$1" --argjson v "$2" '. + {($k): $v}' <<<"$by")"
    shift 2
  done
  printf '{"turns":[%s],"byLens":%s}' "$turns" "$by"
}

# --- panel observables -------------------------------------------------------
# The clean sentinel EVERY finder carries. Real clean native reviews are
# free-form prose (fixtures/review-texts/clean-prose-unsentineled.md), so
# without it a finder that found nothing is indistinguishable from one that
# went dark. It rides the FINDINGS channel because that is the only channel a
# review turn's render exposes — a final-message sentinel was live-disproven,
# a marker finding live-proven (both in
# tests/review-bench/results/2026-08-03-native-clean-render-probe/notes.md).
SENTINEL='If and only if your review finds no material issues, report exactly one finding titled "NO-MATERIAL-FINDINGS" at the lowest priority, pointing at any changed file.'

# The sweep carries the sentinel and nothing else, so its developer_instructions
# START with the sentinel's opening words while a scalpel's start with its own
# mandate: that is what makes the two addressable apart in `lens_scenario`.
SWEEP_LENS='If and only if your review finds'

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

# result readers. The assembled result carries the verdict, the published
# findings, the coverage and the lenses; the raw candidate pool rides along only
# when the verifier could not be trusted (there is nothing else to hand back).
# So pool assertions read the pool the verifier was actually given, out of its
# own prompt — sorted, so a nondeterministic pool ORDER can never green or red an
# assertion about pool CONTENT.
prompt_pool() { # the candidates JSON of the FIRST verifier prompt
  # No early `exit`: this reads from a pipe under `set -o pipefail`, where an
  # awk that quits first turns a healthy run into a broken-pipe failure.
  verifier_prompts | awk '/^\[$/ && !seen {f=1; seen=1} f {print} /^\]$/ {f=0}'
}
pool_ids()      { prompt_pool | jq -r '[.[].id] | sort | join(",")'; }
pool_titles()   { prompt_pool | jq -r '[.[].title] | sort | join(" | ")'; }
coverage_rows() { jq -c '[.result.coverage[] | {finder, lens, status, stubs}]' "$scratch/out.json"; }
verdict()       { jq -r '.result.verdict' "$scratch/out.json"; }
explanation()   { jq -r '.result.explanation' "$scratch/out.json"; }
finding_count() { jq -r '.result.findings | length' "$scratch/out.json"; }
# Published findings IN ORDER — the order is the P0→P3 assertion, so this one is
# deliberately unsorted. Each is rendered as id/priority[the finders that raised
# it] title.
findings_lines() {
  jq -r '[.result.findings[] | "\(.id)/\(.priority)[\(.sources | join("+"))] \(.title)"] | join(" | ")' \
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

# What a clean finder actually renders once it carries the marker instruction:
# byte-identical to the live sentinelcheck2 run recorded in
# tests/review-bench/results/2026-08-03-native-clean-render-probe/notes.md.
# Note what the real render does NOT have — no [P#] tag on the marker, and no
# "Full review comments:" heading. Both were guesses in the hand-written version
# of this fixture, and neither survived contact with the model.
CLEAN_TEXT="$(cat "$FIXTURES/marker-clean.md")"
DRIFT_TEXT="$(cat "$FIXTURES/partial-drift.md")"

# Marker beside real findings — the finder misread "if and only if". The marker
# must be dropped and the real finding kept, and the marker sits FIRST in both
# renders so the surviving stub's id is #2 in either slot the race hands out.
MIXED_A='# Codex Review

Full review comments:

- [P3] NO-MATERIAL-FINDINGS — app.py:1
  Nothing material beyond the note below.

- [P1] Charge the handoff to the source lane — skills/implementing/scripts/implement-dispatch.sh:169
  The destination lane is charged a worker it does not own.'

MIXED_B='# Codex Review

Full review comments:

- [P3] NO-MATERIAL-FINDINGS — app.py:1
  Nothing material beyond the note below.

- [P2] Move the sweep cursor outside the daemon registry — skills/issue-tracker/scripts/board-sweep.sh:429
  The cursor is addressable by daemon commands.'

# ---------------------------------------------------------------------------
# 1. The whole panel on the derived path: one deriver turn, three finders
#    (sweep + two scalpels) each carrying the clean sentinel, one verifier whose
#    verdict set satisfies the postconditions on the first try, and the assembly
#    that turns all of it into one verdict. Each finder's render is pinned to its
#    own lens, so this case can assert WHICH finder raised what.
# ---------------------------------------------------------------------------
VERDICTS_OK='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P0","comment":"the lane is charged twice"},
  {"id":"sweep#2","verdict":"CONFIRMED","duplicateOf":null,"priority":"P3","comment":"the label really is ignored"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"registry namespace collision confirmed"},
  {"id":"scalpel-1#2","verdict":"CONFIRMED","duplicateOf":"sweep#1","priority":null,"comment":"same lane accounting defect"},
  {"id":"scalpel-2#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P2","comment":"the head ref is genuinely unfetched"},
  {"id":"scalpel-2#2","verdict":"REFUTED","duplicateOf":null,"priority":null,"comment":"retirement validates the shape first"}
]}'

new_case derive "$(lens_scenario \
  "$(msg_turn '{"lenses":["watch the auth paths.","check removed guards."]}'),$(msg_turn "$VERDICTS_OK")" \
  "$SWEEP_LENS"             "$(review_turn "$SWEEP_TEXT")" \
  "watch the auth paths."   "$(review_turn "$SCALPEL1_TEXT")" \
  "check removed guards."   "$(review_turn "$SCALPEL2_TEXT")")"
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
# The API's strict dialect, live-proven on the 2026-08-03 X1 run: without
# additionalProperties:false on EVERY object, and a `required` naming every
# property it declares, the turn is rejected 400 before the model runs. The
# optional fields survive that as nullable-and-required.
assert_eq "every object in the verifier schema is closed" "false false" \
  "$(verifier_turns '"\(.outputSchema.additionalProperties) \(.outputSchema.properties.verdicts.items.additionalProperties)"')"
assert_eq "the verdict schema requires every property it declares" \
  "comment duplicateOf id priority verdict" \
  "$(verifier_turns '.outputSchema.properties.verdicts.items | (.required | sort | join(" ")) as $r | (.properties | keys | sort | join(" ")) as $p | if $r == $p then $r else "required=\($r) properties=\($p)" end')"
assert_eq "the optional verdict fields are nullable rather than absent" "string,null string,null" \
  "$(verifier_turns '.outputSchema.properties.verdicts.items.properties | "\(.duplicateOf.type | join(",")) \(.priority.type | join(","))"')"
assert_eq "the deriver schema is closed too" "false" \
  "$(turn_field 0 '.params.outputSchema.additionalProperties')"
verifier_prompts > "$scratch/vprompt.txt"
assert_contains "the verifier is told to re-inspect the code itself" "$scratch/vprompt.txt" "re-inspect the code yourself"
assert_contains "the verifier prompt names the diff base" "$scratch/vprompt.txt" "merge-base(HEAD, main)"
assert_contains "the verifier prompt carries the candidate pool verbatim" "$scratch/vprompt.txt" '"id": "scalpel-2#2"'
# A lens-directed claim reads differently once you know which mandate produced
# it, so the roster rides above the candidates.
assert_contains "the verifier is shown the sweep as lens-free" "$scratch/vprompt.txt" "- sweep: (lens-free sweep)"
assert_contains "the verifier is shown each scalpel's mandate" "$scratch/vprompt.txt" "- scalpel-2: check removed guards."

# The assembly: refuted candidates are dropped, the duplicate collapses onto the
# formulation the verifier chose, the survivors come out P0-first, and each one
# names the finders that actually raised it.
assert_eq "a panel with confirmed findings answers incorrect" "incorrect" "$(verdict)"
assert_eq "confirmed findings are published P0-first, the duplicate collapsed, the refuted one dropped" \
  "sweep#1/P0[sweep+scalpel-1] Require the worker role to match the charged lane | scalpel-1#1/P1[scalpel-1] Move the sweep cursor outside the daemon registry | scalpel-2#1/P2[scalpel-2] Fetch child PR heads before deleted-branch scale review | sweep#2/P3[sweep] Honor engine labels on scale-review epics" \
  "$(findings_lines)"
# A finding is half stub, half verdict: the location the finder reported, the
# judgement the verifier reached. Reading the comment off the stub, or the file
# off the verdict, both fail here.
assert_eq "a published finding carries the stub's location and the verifier's own comment" \
  '{"id":"sweep#1","priority":"P0","title":"Require the worker role to match the charged lane","file":"skills/implementing/scripts/implement-dispatch.sh","lines":"169-170","comment":"the lane is charged twice","sources":["sweep","scalpel-1"]}' \
  "$(jq -c '.result.findings[0]' "$scratch/out.json")"
assert_eq "the explanation names the confirmed findings, at most three of them" \
  "confirmed: Require the worker role to match the charged lane; Move the sweep cursor outside the daemon registry; Fetch child PR heads before deleted-branch scale review" \
  "$(explanation)"
# The raw pool is a fallback for a panel that could not publish findings, not a
# second copy of them: a verified panel hands back the verdict, not the material.
assert_eq "a verified panel does not carry the raw candidate pool" "null" \
  "$(jq -c '.result.pool' "$scratch/out.json")"

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
# A drifted finder's partial stubs are withheld, so there is nothing to verify —
# the turn count above is what proves it (a pool would have bought a verifier
# turn) and the empty findings list is what the caller sees. An all-drifted panel
# is emphatically NOT a clean one.
assert_eq "no finding is published from a drifted finder's withheld stubs" "0" "$(finding_count)"
assert_eq "a panel that understood none of its finders cannot call the diff clean" \
  "interrupted" "$(verdict)"
# The sweep drifted too, and a lost sweep is the round failing — that is what
# gets said, ahead of the per-lane accounting.
assert_eq "the reason the verdict is withheld is named, sweep first" \
  "the lens-free sweep did not complete — round is interrupted" "$(explanation)"

# ---------------------------------------------------------------------------
# 3. Caller lenses are still capped and cleaned: at most five, trimmed, blanks
#    dropped — the caller is not trusted with the owner's cap either. Every
#    finder gets the same clean render (the scenario holds nothing else, so a
#    deriver turn sneaking in would take a review slot and blow up on the
#    schema), which is also the multi-finder all-clean panel: five lanes that all
#    reported, none lost, one correct verdict.
# ---------------------------------------------------------------------------
new_case bypass-cap "$(scenario "$(review_turn "$CLEAN_TEXT")")"
run_panel '{"base":"main","lenses":["  a.  ","","b.","c.","d.","e.","f."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the capped bypass run spends one turn per surviving finder and no more" "0:5" "$(rc_and_turns)"
assert_eq "caller lenses sliced to five, trimmed, blanks dropped" \
  '["a.","b.","c.","d."]' "$(jq -c '.result.lenses' "$scratch/out.json")"
assert_eq "the cleaned mandates are what the finders actually receive" \
  "$(expected_lenses "a." "b." "c." "d.")" "$(actual_lenses)"
assert_eq "five finders that all came back clean make one correct verdict" "correct" "$(verdict)"

# ---------------------------------------------------------------------------
# 3b. The marker beside real findings. "If and only if" is exactly the kind of
#     condition a finder mis-applies, and the marker is a stub like any other
#     until extraction reads it, so the failure mode to bar is a real finding
#     lost to a stray marker. The marker leads BOTH renders, so the surviving
#     stub is #2 of its finder either way and the id gap is visible in the pool
#     the verifier is handed.
# ---------------------------------------------------------------------------
new_case marker-mixed "$(lens_scenario \
  "$(msg_turn '{"verdicts":[
       {"id":"sweep#2","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"real"},
       {"id":"scalpel-1#2","verdict":"CONFIRMED","duplicateOf":null,"priority":"P2","comment":"real"}]}')" \
  "$SWEEP_LENS"   "$(review_turn "$MIXED_A")" \
  "mixed lane."   "$(review_turn "$MIXED_B")")"
run_panel '{"base":"main","lenses":["mixed lane."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the mixed panel runs two finders and one verifier" "0:3" "$(rc_and_turns)"
assert_eq "the marker is not counted as coverage — each lane reports its real finding" \
  '[{"finder":"sweep","lens":null,"status":"ok","stubs":1},{"finder":"scalpel-1","lens":"mixed lane.","status":"ok","stubs":1}]' \
  "$(coverage_rows)"
assert_eq "the verifier is never asked to judge the marker" \
  "scalpel-1#2,sweep#2" "$(pool_ids)"
assert_eq "the real findings survive the marker beside them" \
  "Charge the handoff to the source lane | Move the sweep cursor outside the daemon registry" \
  "$(pool_titles)"
assert_eq "a lane that filed a marker AND a real finding is not a clean lane" \
  "incorrect" "$(verdict)"
assert_eq "both real findings are published" "2" "$(finding_count)"

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
# Nothing to verify is not the same as nothing verified: every lane reported,
# every lane clean. That is the ONE shape entitled to a correct verdict — and it
# still says out loud that zero findings can also mean the wrong diff.
assert_eq "a panel whose every lane reported clean answers correct" "correct" "$(verdict)"
assert_eq "nothing published, and no finding is claimed" "0" "$(finding_count)"
assert_eq "a zero-finding verdict says what else zero findings can mean" \
  "no confirmed findings (note: all finders returned zero findings — verify the diff target is what you intended)" \
  "$(explanation)"

# ---------------------------------------------------------------------------
# 6. Verifier omission: a verdict set that skips a candidate is rejected
#    mechanically, repaired ONCE, and — if the repair is no better — abandoned.
#    A null `verified` is what Task 4 turns into an interrupted verdict; the
#    pool rides along so the findings are not silently lost.
#    This case also carries explicit model routing, the only place the finder
#    model is observable at all (it rides thread/start, not review/start).
# ---------------------------------------------------------------------------
SHORT_VERDICTS='{"verdicts":[{"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"real"}]}'
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
  "interrupted" "$(verdict)"
assert_eq "nothing is published on a verdict set that was never trusted" "0" "$(finding_count)"
assert_eq "the interrupted panel says the verifier, not the code, is why" \
  "verifier did not produce a contract-valid verdict set; raw candidate pool attached" \
  "$(explanation)"
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
  {"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":"scalpel-1#1","priority":null,"comment":"same as the other"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#1","priority":null,"comment":"same as the other"}
]}'
new_case verifier-cycle "$(scenario \
  "$(review_turn "$ONE_A")" \
  "$(review_turn "$ONE_B")" \
  "$(msg_turn "$CYCLIC")" \
  "$(msg_turn "$CYCLIC")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "a cyclic verdict set costs exactly one repair turn" "0:4" "$(rc_and_turns)"
assert_eq "a complete but cyclic verdict set is refused" "interrupted" "$(verdict)"
assert_eq "a refused verdict set publishes nothing, however confirmed it looked" "0" "$(finding_count)"
assert_contains "the run names the cycle" "$scratch/err.log" "duplicateOf cycle at"

# ---------------------------------------------------------------------------
# 8. The repair that works: a phantom id and a duplicate pointing at a REFUTED
#    finding are both caught, and a corrected second answer is accepted.
# ---------------------------------------------------------------------------
BAD_VERDICTS='{"verdicts":[
  {"id":"ghost#1","verdict":"CONFIRMED","duplicateOf":null,"priority":null,"comment":"invented"},
  {"id":"sweep#1","verdict":"REFUTED","duplicateOf":null,"priority":null,"comment":"not real"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#1","priority":null,"comment":"dup of a refuted one"}
]}'
GOOD_VERDICTS='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"reinspected: real"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#1","priority":null,"comment":"same defect"}
]}'
new_case verifier-repair "$(lens_scenario \
  "$(msg_turn "$BAD_VERDICTS"),$(msg_turn "$GOOD_VERDICTS")" \
  "$SWEEP_LENS"         "$(review_turn "$ONE_A")" \
  "only one mandate."   "$(review_turn "$ONE_B")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the repaired run spends the same four turns" "0:4" "$(rc_and_turns)"
assert_contains "a verdict for a candidate that was never raised is caught" "$scratch/err.log" "phantom id ghost#1"
assert_contains "a duplicate of a refuted finding is caught" "$scratch/err.log" "duplicateOf targets refuted sweep#1"
assert_eq "the corrected verdict set is what gets assembled — the rejected one is gone" \
  "sweep#1/P1[sweep+scalpel-1] Charge the handoff to the source lane" "$(findings_lines)"
assert_eq "a repaired panel is a verified panel: the verdict is the code's, not the verifier's" \
  "incorrect" "$(verdict)"

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
assert_eq "a panel that lost every lane is interrupted, never clean" "interrupted" "$(verdict)"
# The sweep is gone, so the round failed — that is said first, before any
# accounting of the other lanes.
assert_eq "a lost sweep is reported as the round failing" \
  "the lens-free sweep did not complete — round is interrupted" "$(explanation)"

# ---------------------------------------------------------------------------
# 10. A dead SCALPEL over an otherwise clean panel. The sweep understood its
#     lane and found nothing; one mandate was never reviewed at all. `verified`
#     is [] here exactly as it is for a genuinely clean panel — the difference
#     lives only in coverage, and the assembly has to read it, or an unreviewed
#     mandate is published as a clean bill of health.
# ---------------------------------------------------------------------------
new_case dead-scalpel-clean "$(lens_scenario "" \
  "$SWEEP_LENS"                 "$(review_turn "$CLEAN_TEXT")" \
  "authorization on the new routes."  "$DIE")"
run_panel '{"base":"main","lenses":["authorization on the new routes."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the clean sweep is spent once, the dead scalpel twice" "0:3" "$(rc_and_turns)"
assert_eq "the surviving lane is ok and the lost one keeps its mandate on the record" \
  '[{"finder":"sweep","lens":null,"status":"ok","stubs":0},{"finder":"scalpel-1","lens":"authorization on the new routes.","status":"dead","stubs":0}]' \
  "$(coverage_rows)"
assert_eq "an unreviewed mandate is never published as a clean verdict" "interrupted" "$(verdict)"
assert_eq "the interrupted panel names the lane it never got" \
  "coverage incomplete (scalpel-1) — a clean verdict cannot be asserted" "$(explanation)"
assert_eq "no finding is invented to justify the interruption" "0" "$(finding_count)"

# ---------------------------------------------------------------------------
# 11. A dead SCALPEL beside a CONFIRMED defect. A lost lens costs the panel its
#     claim to completeness, never a defect it actually confirmed: the verdict
#     stays incorrect and the partial coverage rides on the explanation.
# ---------------------------------------------------------------------------
CONFIRM_SWEEP='{"verdicts":[{"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"the destination lane is charged"}]}'
new_case dead-scalpel-confirmed "$(lens_scenario "$(msg_turn "$CONFIRM_SWEEP")" \
  "$SWEEP_LENS"          "$(review_turn "$ONE_A")" \
  "removed guards."      "$DIE")"
run_panel '{"base":"main","lenses":["removed guards."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the surviving finder is still verified" "0:4" "$(rc_and_turns)"
assert_eq "a lost scalpel never suppresses a confirmed defect" "incorrect" "$(verdict)"
assert_eq "the confirmed finding is published in full" \
  "sweep#1/P1[sweep] Charge the handoff to the source lane" "$(findings_lines)"
assert_eq "the verdict carries its own coverage caveat" \
  "confirmed: Charge the handoff to the source lane; coverage partial: scalpel-1" "$(explanation)"

# ---------------------------------------------------------------------------
# 12. A dead SWEEP beside a CONFIRMED defect — the round-failure rule, and the
#     one case the assembly must not report as a plain `incorrect`. The sweep is
#     the only lane that reads the whole diff, so losing it means the panel does
#     not know what it missed; the round is interrupted no matter what the
#     surviving lenses confirmed. The confirmed findings still ride along —
#     interrupted withholds the CLAIM OF COMPLETENESS, not the evidence.
# ---------------------------------------------------------------------------
CONFIRM_SCALPEL='{"verdicts":[{"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P0","comment":"the cursor is addressable as a daemon"}]}'
new_case dead-sweep-confirmed "$(lens_scenario "$(msg_turn "$CONFIRM_SCALPEL")" \
  "$SWEEP_LENS"           "$DIE" \
  "the daemon registry."  "$(review_turn "$ONE_B")")"
run_panel '{"base":"main","lenses":["the daemon registry."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the dead sweep is retried once, the scalpel and verifier run normally" "0:4" "$(rc_and_turns)"
assert_eq "losing the sweep interrupts the round even with a confirmed finding in hand" \
  "interrupted" "$(verdict)"
assert_eq "the confirmed finding is still attached, not dropped with the verdict" \
  "scalpel-1#1/P0[scalpel-1] Move the sweep cursor outside the daemon registry" "$(findings_lines)"
assert_eq "the explanation names the sweep AND marks the findings as partial evidence" \
  "the lens-free sweep did not complete — round is interrupted; 1 confirmed finding(s) attached as partial evidence" \
  "$(explanation)"

# ---------------------------------------------------------------------------
# 13. Finders that produced no usable signal, two ways: a review that answered
#     in unsentineled prose (understood as nothing at all — see the clean-render
#     probe) and a review that came back empty. Neither is a clean lane; the
#     would-be-clean panel degrades to interrupted and each lost lane is named.
#     Note the different rows: the prose review SUCCEEDED and failed extraction,
#     while an empty review is refused by the transport itself and dies.
# ---------------------------------------------------------------------------
PROSE_TEXT="$(cat "$FIXTURES/clean-prose-unsentineled.md")"
new_case no-signal "$(lens_scenario "" \
  "$SWEEP_LENS"       "$(review_turn "$CLEAN_TEXT")" \
  "prose lane."       "$(review_turn "$PROSE_TEXT")" \
  "empty lane."       '{"reviewText":""}')"
run_panel '{"base":"main","lenses":["prose lane.","empty lane."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the empty lane is the only one retried" "0:4" "$(rc_and_turns)"
assert_eq "prose is an extraction failure; an empty review is a dead lane" \
  '[{"finder":"sweep","lens":null,"status":"ok","stubs":0},{"finder":"scalpel-1","lens":"prose lane.","status":"extraction-failed","stubs":0},{"finder":"scalpel-2","lens":"empty lane.","status":"dead","stubs":0}]' \
  "$(coverage_rows)"
assert_eq "a finder that said nothing recognizable is not a finder that found nothing" \
  "interrupted" "$(verdict)"
assert_eq "both unusable lanes are named, in panel order" \
  "coverage incomplete (scalpel-1, scalpel-2) — a clean verdict cannot be asserted" "$(explanation)"

# ---------------------------------------------------------------------------
# 14. A verifier that dies outright, on its first call and on its repair: the
#     candidates exist and nobody could judge them. Same fate as an unrepairable
#     verdict set — interrupted, nothing published, the raw pool attached so the
#     candidates are recoverable by hand.
# ---------------------------------------------------------------------------
new_case verifier-dead "$(scenario \
  "$(review_turn "$ONE_A")" \
  "$(review_turn "$ONE_B")" \
  "$DIE")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
# Two finders, then the verifier's first call and its repair, each dying through
# the engine's one transport retry: 2 + 2 + 2.
assert_eq "a verifier that never answers costs its two calls and no more" "0:6" "$(rc_and_turns)"
assert_eq "candidates nobody could judge are never published as findings" "interrupted" "$(verdict)"
assert_eq "nothing is published from an unjudged pool" "0" "$(finding_count)"
assert_eq "the raw candidates survive on the result" 2 "$(jq -r '.result.pool | length' "$scratch/out.json")"
assert_contains "the run says the verifier itself failed" "$scratch/err.log" \
  "verifier postconditions failed: verifier failed"

# ---------------------------------------------------------------------------
# 15. A duplicate CHAIN: the verifier pointed one duplicate at another duplicate
#     rather than at the primary. The postconditions allow it — they forbid a
#     cycle and a refuted target, not a chain — so the assembly is what has to
#     follow the chain to its end. Crediting only the link a duplicate NAMED
#     drops the last finder to raise the defect off the record, and a finder that
#     raised the same defect twice must not be counted twice.
# ---------------------------------------------------------------------------
CHAINED='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"the lane is charged twice"},
  {"id":"sweep#2","verdict":"CONFIRMED","duplicateOf":"sweep#1","priority":null,"comment":"the same accounting defect, said twice"},
  {"id":"scalpel-1#1","verdict":"CONFIRMED","duplicateOf":"sweep#2","priority":null,"comment":"third sighting of the same defect"}
]}'
new_case duplicate-chain "$(lens_scenario "$(msg_turn "$CHAINED")" \
  "$SWEEP_LENS"          "$(review_turn "$SWEEP_TEXT")" \
  "only one mandate."    "$(review_turn "$ONE_B")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the chained verdict set passes the postconditions on the first try" "0:3" "$(rc_and_turns)"
assert_eq "a chain of duplicates collapses onto the one primary, crediting every finder once" \
  "sweep#1/P1[sweep+scalpel-1] Require the worker role to match the charged lane" "$(findings_lines)"

# ---------------------------------------------------------------------------
# 15b. A REFUTED verdict that carries duplicateOf. The postconditions allow it —
#     its target is confirmed, so nothing about the graph is broken — and the
#     verifier really does write this: "same claim as sweep#1, and it is wrong".
#     What it must NOT buy is corroboration. `sources` is the published finding's
#     claim about how many reviewers independently stand behind it, and a lane
#     whose own verdict was refuted stands behind nothing.
# ---------------------------------------------------------------------------
REFUTED_DUP='{"verdicts":[
  {"id":"sweep#1","verdict":"CONFIRMED","duplicateOf":null,"priority":"P1","comment":"the lane is charged twice"},
  {"id":"scalpel-1#1","verdict":"REFUTED","duplicateOf":"sweep#1","priority":null,"comment":"same claim, and the cursor is namespaced after all"}
]}'
new_case refuted-duplicate "$(lens_scenario "$(msg_turn "$REFUTED_DUP")" \
  "$SWEEP_LENS"          "$(review_turn "$ONE_A")" \
  "only one mandate."    "$(review_turn "$ONE_B")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "a refuted duplicate is a contract-valid verdict set, repaired never" "0:3" "$(rc_and_turns)"
assert_eq "a refuted duplicate never credits its lane as a corroborating source" \
  "sweep#1/P1[sweep] Charge the handoff to the source lane" "$(findings_lines)"

# ---------------------------------------------------------------------------
# 16. Every candidate refuted: the finders raised real material, the verifier
#     re-inspected it and none of it held. That is a clean diff arrived at the
#     hard way — correct, with nothing published — and it must NOT carry the
#     zero-findings caveat, which is about a panel that saw nothing at all.
# ---------------------------------------------------------------------------
ALL_REFUTED='{"verdicts":[
  {"id":"sweep#1","verdict":"REFUTED","duplicateOf":null,"priority":null,"comment":"the lane is charged one frame up"},
  {"id":"scalpel-1#1","verdict":"REFUTED","duplicateOf":null,"priority":null,"comment":"the cursor is namespaced after all"}
]}'
new_case all-refuted "$(lens_scenario "$(msg_turn "$ALL_REFUTED")" \
  "$SWEEP_LENS"          "$(review_turn "$ONE_A")" \
  "only one mandate."    "$(review_turn "$ONE_B")")"
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the refuting verifier is paid for exactly once" "0:3" "$(rc_and_turns)"
assert_eq "a panel whose every candidate was refuted is correct" "correct" "$(verdict)"
assert_eq "nothing refuted is published" "0" "$(finding_count)"
assert_eq "a panel that examined candidates says so, without the saw-nothing caveat" \
  "no confirmed findings" "$(explanation)"

# ---------------------------------------------------------------------------
# 17. No base: refused before any worker is spawned.
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
