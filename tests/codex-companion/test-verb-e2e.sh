#!/usr/bin/env bash
# End-to-end test for the `workflow` verb: the CLI contract (stdout JSON only,
# `[workflow]` stderr, run directory), the summary job record, signal cleanup,
# and the cancel / liveness awareness in the read paths.
#
# Everything is asserted against artifacts the verb and the mock app-server
# actually wrote — the run directory, the mock's live/* files, and what a
# SEPARATE `status`/`result` process reads back out of the shared ledger.
#
# Each case gets its own scratch (mock state dir, plugin data root, repo): the
# mock's scenario counter and live/* set are global to a mock dir.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-mock.sh
source "$HERE/lib-mock.sh"

FIXTURES="$HERE/fixtures"
fail=0
scratches=()
scratch=""
repo=""

command -v jq >/dev/null || { echo "jq is required for this test"; exit 2; }

ok()   { printf '  ok   %s\n' "$1"; }
bad()  { printf '  FAIL %s\n' "$1"; fail=1; }

assert_eq() { # desc want got
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$2', got '$3')"; fi
}

assert_contains() { # desc file needle
  if grep -Fq -- "$3" "$2"; then ok "$1"; else bad "$1 (no '$3' in $2)"; fi
}

assert_file() { # desc path
  if [ -e "$2" ]; then ok "$1"; else bad "$1 (missing $2)"; fi
}

live_count() { find "$CODEX_MOCK_DIR/live" -type f 2>/dev/null | wc -l | tr -d ' '; }

wait_for_live() { # want deadline-seconds
  local want="$1" deadline=$(( SECONDS + $2 ))
  while [ "$(live_count)" != "$want" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.1; done
  live_count
}

kill_live_workers() { # mock state dir — each live/<pid> file names a live worker
  local file
  for file in "$1"/live/*; do
    [ -e "$file" ] || continue
    kill -9 "$(basename "$file")" 2>/dev/null || true
  done
}

cleanup() {
  local dir
  for dir in "${scratches[@]:-}"; do
    [ -n "$dir" ] || continue
    kill_live_workers "$dir/mockstate"
    rm -rf "$dir"
  done
}
trap cleanup EXIT

new_case() { # name scenario-json
  echo "-- case: $1"
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/codex-wf-$1-XXXXXX")"
  # TMPDIR usually ends in a slash; node's path.join collapses the resulting
  # `//`, so paths the runtime records would not match ours literally. `tr -s`
  # rather than a bash replacement: bash 3.2 (the system bash on macOS) keeps the
  # backslash from a `\/` replacement string, leaving a scratch path that node's
  # pathToFileURL percent-encodes and then refuses to import.
  scratch="$(printf '%s' "$scratch" | tr -s /)"
  scratches+=("$scratch")
  mock_env "$scratch"
  repo="$scratch/repo"
  git init -q -b main "$repo"
  git -C "$repo" -c user.email=t@example.com -c user.name=t \
    -c commit.gpgsign=false commit -q --allow-empty -m base
  printf '%s' "$2" > "$scratch/mockstate/scenario.json"
}

snapshot_status() { node "$RUNTIME" status --json --all --cwd "$repo" > "$scratch/status.json"; }
listed_ids() { jq -r '[.running[], .latestFinished, .recent[]] | map(select(. != null)) | .[].id' "$scratch/status.json"; }
listed_status() { # job-id
  jq -r --arg id "$1" \
    '[.running[], .latestFinished, .recent[]] | map(select(. != null)) | map(select(.id == $id)) | (.[0].status // "MISSING")' \
    "$scratch/status.json"
}
listed_field() { # job-id field
  jq -r --arg id "$1" --arg field "$2" \
    '[.running[], .latestFinished, .recent[]] | map(select(. != null)) | map(select(.id == $id)) | (.[0][$field] // "MISSING")' \
    "$scratch/status.json"
}
sole_job_id() { listed_ids | head -1; }

# ---------------------------------------------------------------------------
# 1. Happy path: CLI contract, run directory, job record, `result`.
# ---------------------------------------------------------------------------
new_case happy '{"turns":[{}]}'
rc=0
node "$RUNTIME" workflow --script "$FIXTURES/fx-happy-small.mjs" --args '{"n":1}' --cwd "$repo" \
  > "$scratch/out.json" 2> "$scratch/err.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err.log"
assert_eq "verb exits 0" 0 "$rc"

assert_eq "stdout is exactly one JSON value" 1 "$(jq -s 'length' "$scratch/out.json")"
assert_eq "result.n round-trips --args" 1 "$(jq -r '.result.n' "$scratch/out.json")"
assert_eq "three leaf agents reported" 3 "$(jq -r '.agents' "$scratch/out.json")"
assert_eq "durationMs present" number "$(jq -r '.durationMs | type' "$scratch/out.json")"
run_id="$(jq -r '.runId' "$scratch/out.json")"
if [ -n "$run_id" ] && [ "$run_id" != "null" ]; then ok "runId non-empty"; else bad "runId non-empty (got '$run_id')"; fi

assert_contains "stderr carries [workflow] start lines" "$scratch/err.log" "[workflow] start agent:"
assert_eq "stderr carries no JSON" 0 "$(grep -c '^[{]' "$scratch/err.log" || true)"

run_dir="$CLAUDE_PLUGIN_DATA/workflows/$run_id"
assert_file "run dir under the data root" "$run_dir"
assert_file "journal.jsonl written" "$run_dir/journal.jsonl"
assert_file "result.json written" "$run_dir/result.json"

snapshot_status
assert_eq "status finalized the summary job" completed "$(listed_status "$run_id")"
node "$RUNTIME" status --cwd "$repo" > "$scratch/status.txt"
assert_contains "human status names the run" "$scratch/status.txt" "$run_id"

node "$RUNTIME" result "$run_id" --cwd "$repo" > "$scratch/result.txt"
assert_contains "result reports the run directory" "$scratch/result.txt" "$run_dir"
assert_contains "result reports the completed status" "$scratch/result.txt" "Status: completed"

# ---------------------------------------------------------------------------
# 2. Overlap: concurrent workflows must all keep their ledger row.
# ---------------------------------------------------------------------------
new_case overlap '{"turns":[{}]}'
pids=()
for _ in 1 2 3 4 5 6; do
  node "$RUNTIME" workflow --script "$FIXTURES/fx-solo.mjs" --cwd "$repo" \
    > /dev/null 2>> "$scratch/err.log" &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || bad "concurrent workflow $pid failed"; done
snapshot_status
assert_eq "all six concurrent workflow records survive" 6 "$(listed_ids | grep -c '^wf-')"

# ---------------------------------------------------------------------------
# 3. Mixed-verb overlap: the legacy (unlocked-until-now) `task` writer must no
#    longer be able to clobber a workflow record, or vice versa.
# ---------------------------------------------------------------------------
new_case mixed '{"turns":[{}]}'
pids=()
for _ in 1 2 3; do
  node "$RUNTIME" workflow --script "$FIXTURES/fx-solo.mjs" --cwd "$repo" \
    > /dev/null 2>> "$scratch/err.log" &
  pids+=("$!")
  node "$RUNTIME" task --cwd "$repo" "hello" > /dev/null 2>> "$scratch/err.log" &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || bad "concurrent run $pid failed"; done
snapshot_status
assert_eq "three workflow records survive alongside tasks" 3 "$(listed_ids | grep -c '^wf-')"
assert_eq "three task records survive alongside workflows" 3 "$(listed_ids | grep -c '^task-')"

# ---------------------------------------------------------------------------
# 4. Cancel by signal: SIGTERM to the run process kills every live worker.
# ---------------------------------------------------------------------------
new_case cancel-signal '{"turns":[{"hangMs":20000}]}'
node "$RUNTIME" workflow --script "$FIXTURES/fx-par3.mjs" --cwd "$repo" \
  > "$scratch/out.json" 2> "$scratch/err.log" &
verb_pid=$!
assert_eq "three workers went live" 3 "$(wait_for_live 3 15)"
kill -TERM "$verb_pid"
assert_eq "every live worker is gone within 2s" 0 "$(wait_for_live 0 2)"
rc=0; wait "$verb_pid" || rc=$?
assert_eq "cancelled run exits 130" 130 "$rc"
snapshot_status
assert_eq "cancelled job is recorded cancelled" cancelled "$(listed_status "$(sole_job_id)")"

# ---------------------------------------------------------------------------
# 5. The `cancel` verb: reaches a run process that is not a group leader, and
#    its workers with it.
# ---------------------------------------------------------------------------
new_case cancel-verb '{"turns":[{"hangMs":20000}]}'
node "$RUNTIME" workflow --script "$FIXTURES/fx-par3.mjs" --cwd "$repo" \
  > "$scratch/out.json" 2> "$scratch/err.log" &
verb_pid=$!
assert_eq "three workers went live" 3 "$(wait_for_live 3 15)"
snapshot_status
live_id="$(sole_job_id)"
live_pid="$(listed_field "$live_id" pid)"

# --resume reuses the run id, so resuming a run that is still going must be
# refused BEFORE it can overwrite that run's own record — the engine's lease
# check fires too late to protect the ledger.
rc=0
node "$RUNTIME" workflow --script "$FIXTURES/fx-par3.mjs" --resume "$live_id" --cwd "$repo" \
  > /dev/null 2> "$scratch/resume.err" || rc=$?
assert_eq "resuming a live run is refused" 1 "$rc"
assert_contains "the refusal names the active run" "$scratch/resume.err" "is still active"
snapshot_status
assert_eq "the live run still owns its record" running "$(listed_status "$live_id")"
assert_eq "the live run's recorded pid is untouched" "$live_pid" "$(listed_field "$live_id" pid)"
assert_eq "the live run's pid is the run process" "$verb_pid" "$live_pid"

node "$RUNTIME" cancel "$live_id" --cwd "$repo" > "$scratch/cancel.txt"
assert_eq "cancel verb killed every worker" 0 "$(wait_for_live 0 5)"
rc=0; wait "$verb_pid" || rc=$?
assert_eq "cancelled run process exited" 130 "$rc"
snapshot_status
assert_eq "cancel verb job is recorded cancelled" cancelled "$(listed_status "$(sole_job_id)")"

# ---------------------------------------------------------------------------
# 6. Cancel under a contended ledger: the signal handler's bookkeeping can throw
#    (`state lock timeout` after 5s), and that must not cost the exit code or
#    leave workers alive. The record is NOT asserted here — a finalize that
#    could not run leaves it to the liveness repair, which is the accepted
#    outcome in this case.
# ---------------------------------------------------------------------------
new_case cancel-contended '{"turns":[{"hangMs":20000}]}'
node "$RUNTIME" workflow --script "$FIXTURES/fx-par3.mjs" --cwd "$repo" \
  > "$scratch/out.json" 2> "$scratch/err.log" &
verb_pid=$!
assert_eq "three workers went live" 3 "$(wait_for_live 3 15)"

# Hold the ledger lock with a stamp naming this shell — a live pid, so the lock
# is never breakable and every writer waits out the full timeout.
state_lock="$(dirname "$(echo "$CLAUDE_PLUGIN_DATA"/state/*/state.json)")/state.json.lock"
mkdir "$state_lock"
printf '%s' "$$" > "$state_lock/holder"

kill -TERM "$verb_pid"
assert_eq "workers die even with the ledger locked" 0 "$(wait_for_live 0 5)"
rc=0; wait "$verb_pid" || rc=$?
assert_eq "a contended finalize still exits 130" 130 "$rc"
assert_contains "the failed bookkeeping is reported" "$scratch/err.log" "cancel bookkeeping failed"
rm -rf "$state_lock"

# ---------------------------------------------------------------------------
# 7. Liveness repair: a SIGKILLed run is finalized lazily on read, not reported
#    as a phantom running job.
# ---------------------------------------------------------------------------
new_case liveness '{"turns":[{"hangMs":20000}]}'
node "$RUNTIME" workflow --script "$FIXTURES/fx-par3.mjs" --cwd "$repo" \
  > "$scratch/out.json" 2> "$scratch/err.log" &
verb_pid=$!
assert_eq "three workers went live" 3 "$(wait_for_live 3 15)"
kill -9 "$verb_pid"
wait "$verb_pid" 2>/dev/null || true
snapshot_status
killed_id="$(sole_job_id)"
assert_eq "SIGKILLed run is repaired to failed" failed "$(listed_status "$killed_id")"
rc=0
node "$RUNTIME" result "$killed_id" --cwd "$repo" > "$scratch/result.txt" 2> "$scratch/result.err" || rc=$?
assert_eq "result on a killed run exits 0" 0 "$rc"
assert_contains "result reports the failure" "$scratch/result.txt" "Status: failed"
assert_contains "result still names the run directory" "$scratch/result.txt" "workflows/$killed_id"

if [ "$fail" -eq 0 ]; then echo "workflow verb e2e: all cases passed"; fi
exit "$fail"
