#!/usr/bin/env bash
# Mock-driven e2e for the review-panel workflow
# (skills/codex-companion/workflows/code-review.mjs), run through the real
# `workflow` verb against the mock codex app-server.
#
# Task 1 scope: the argument contract and adaptive lens derivation — whether a
# deriver turn is spent at all, what the deriver is asked for, and how the
# owner's caps (at most five mandates, non-empty) survive both the derived and
# the caller-supplied path. Every assertion reads an artifact the run actually
# produced: the mock's turns.jsonl and the verb's stdout JSON.
#
# Each case gets its own scratch: the mock's scenario counter and turn log are
# global to a mock dir.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-mock.sh
source "$HERE/lib-mock.sh"

PANEL="$REPO_ROOT/skills/codex-companion/workflows/code-review.mjs"
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

# ---------------------------------------------------------------------------
# 1. Derived path: one deriver turn, at the panel's fixed deriver model/effort,
#    asking for the owner's mandate shape; its lenses come back on the result.
# ---------------------------------------------------------------------------
new_case derive '{"turns":[{"finalMessage":"{\"lenses\":[\"watch the auth paths.\",\"check removed guards.\"]}"}]}'
run_panel '{"base":"main"}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the derived run exits 0 having spent exactly one turn" "0:1" "$(rc_and_turns)"
assert_eq "the turn is an agent turn, not a review" "turn/start" "$(turn_field 0 .method)"
assert_eq "deriver runs on the panel's deriver model" "gpt-5.6-sol" "$(turn_field 0 .params.model)"
assert_eq "deriver runs at medium effort" "medium" "$(turn_field 0 .params.effort)"
assert_eq "deriver turn is schema-forced" "object" "$(turn_field 0 '.params.outputSchema.type')"

turn_field 0 '.params.input[0].text' > "$scratch/prompt.txt"
assert_contains "deriver prompt names the diff base" "$scratch/prompt.txt" "merge-base(HEAD, main)"
assert_contains "deriver prompt caps mandate length" "$scratch/prompt.txt" "AT MOST TWO SIMPLE SENTENCES"
assert_contains "deriver prompt caps mandate count" "$scratch/prompt.txt" "between 0 and 5"
assert_contains "deriver prompt says sharper beats padding" "$scratch/prompt.txt" "fewer, sharper mandates beat coverage padding"

assert_eq "derived lenses reach the result" \
  '["watch the auth paths.","check removed guards."]' "$(jq -c '.result.lenses' "$scratch/out.json")"
assert_eq "finder model defaults to sol" "gpt-5.6-sol" "$(jq -r '.result.finderModel' "$scratch/out.json")"
assert_eq "finder effort defaults to xhigh" "xhigh" "$(jq -r '.result.finderEffort' "$scratch/out.json")"
assert_contains "the run logs the panel shape" "$scratch/err.log" "panel: sweep + 2 scalpels"

# ---------------------------------------------------------------------------
# 2. Caller bypass: `args.lenses` spends no deriver turn and is passed through.
#    The scenario would hand back a DIFFERENT lens set, so a workflow that
#    derived anyway fails on both the turn count and the lens text.
# ---------------------------------------------------------------------------
new_case bypass '{"turns":[{"finalMessage":"{\"lenses\":[\"derived-should-not-happen.\"]}"}]}'
run_panel '{"base":"main","lenses":["only one mandate."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the bypass run exits 0 having spent no turn" "0:0" "$(rc_and_turns)"
assert_eq "caller lenses pass through untouched" \
  '["only one mandate."]' "$(jq -c '.result.lenses' "$scratch/out.json")"
assert_contains "the run logs one scalpel" "$scratch/err.log" "panel: sweep + 1 scalpels"

# ---------------------------------------------------------------------------
# 3. Caller lenses are still capped and cleaned: at most five, trimmed, blanks
#    dropped — the caller is not trusted with the owner's cap either.
# ---------------------------------------------------------------------------
new_case bypass-cap '{"turns":[{"finalMessage":"{\"lenses\":[\"derived-should-not-happen.\"]}"}]}'
run_panel '{"base":"main","lenses":["  a.  ","","b.","c.","d.","e.","f."]}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "the capped bypass run exits 0 having spent no turn" "0:0" "$(rc_and_turns)"
assert_eq "caller lenses sliced to five, trimmed, blanks dropped" \
  '["a.","b.","c.","d."]' "$(jq -c '.result.lenses' "$scratch/out.json")"

# ---------------------------------------------------------------------------
# 4. The cap binds the model too: a deriver that returns more than five
#    mandates is truncated rather than obeyed.
# ---------------------------------------------------------------------------
new_case derive-cap '{"turns":[{"finalMessage":"{\"lenses\":[\"one.\",\"two.\",\"three.\",\"four.\",\"five.\",\"six.\",\"seven.\"]}"}]}'
run_panel '{"base":"main"}'
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "over-long derivation still exits 0" 0 "$rc"
assert_eq "derived lenses capped at five" 5 "$(jq -r '.result.lenses | length' "$scratch/out.json")"
assert_eq "the cap keeps the first five" \
  '["one.","two.","three.","four.","five."]' "$(jq -c '.result.lenses' "$scratch/out.json")"

# ---------------------------------------------------------------------------
# 5. No base: refused before any worker is spawned.
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
