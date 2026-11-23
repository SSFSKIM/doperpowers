#!/usr/bin/env bash
# Adversarial resume: what a workflow run has to survive between a SIGKILL and a
# `--resume` of the same run id.
#
# One scratch, one run directory, one repo — the phases are deliberately
# stateful, because that IS resume: phase 1 kills a run with a HOLE in it (a
# started-but-never-finished call sitting before a later call that DID finish),
# phase 3 tears the journal's last line the way a killed writer would, phase 4
# resumes and proves the cache is keyed by call identity (the hole re-runs live,
# the finished calls come back from the journal with their ORIGINAL values), and
# phases 5-7 prove the two guards that refuse a resume: the run lease, and the
# fingerprint over both the repo (phase 6) and the workflow script itself
# (phase 7).
#
# Everything is asserted against artifacts the verb, the engine and the mock
# app-server actually wrote — the journal, result.json, the mock's scenario
# counter, and what a separate `status` process reads out of the ledger.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-mock.sh
source "$HERE/lib-mock.sh"

FIXTURES="$HERE/fixtures"
SCRIPT="$FIXTURES/fx-resume.mjs"
fail=0

command -v jq >/dev/null || { echo "jq is required for this test"; exit 2; }

ok()   { printf '  ok   %s\n' "$1"; }
bad()  { printf '  FAIL %s\n' "$1"; fail=1; }

assert_eq() { # desc want got
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$2', got '$3')"; fi
}

assert_ne() { # desc unwanted got
  if [ "$2" != "$3" ]; then ok "$1"; else bad "$1 (got the unwanted '$3')"; fi
}

assert_contains() { # desc file needle
  if grep -Fq -- "$3" "$2"; then ok "$1"; else bad "$1 (no '$3' in $2)"; fi
}

assert_absent() { # desc file needle
  if grep -Fq -- "$3" "$2"; then bad "$1 (found '$3' in $2)"; else ok "$1"; fi
}

scratch="$(mktemp -d "${TMPDIR:-/tmp}/codex-wf-resume-XXXXXX")"
# TMPDIR usually ends in a slash; node's path.join collapses the resulting `//`,
# so paths the runtime records would not match ours literally. `tr -s` rather
# than a bash replacement: bash 3.2 (the system bash on macOS) keeps the
# backslash from a `\/` replacement string, and a scratch path carrying a literal
# backslash is invisible until something feeds it to node's pathToFileURL, which
# percent-encodes it and rejects the import.
scratch="$(printf '%s' "$scratch" | tr -s /)"
mock_env "$scratch"
repo="$scratch/repo"
# A SECOND workspace sharing the same plugin data root: its ledger cannot see
# the first repo's job records, which is how phase 5 reaches the engine's lease
# instead of stopping at the ledger's own liveness guard.
other="$scratch/other"
for r in "$repo" "$other"; do
  git init -q -b main "$r"
  git -C "$r" -c user.email=t@example.com -c user.name=t \
    -c commit.gpgsign=false commit -q --allow-empty -m base
done

kill_live_workers() { # each live/<pid> file names a mock app-server still running
  local file
  for file in "$CODEX_MOCK_DIR"/live/*; do
    [ -e "$file" ] || continue
    kill -9 "$(basename "$file")" 2>/dev/null || true
  done
}

cleanup() { kill_live_workers; rm -rf "$scratch"; }
trap cleanup EXIT

reset_mock() { # scenario-json [stagger]
  kill_live_workers
  rm -rf "$CODEX_MOCK_DIR/live"
  rm -f "$CODEX_MOCK_DIR/counter" "$CODEX_MOCK_DIR/turns.jsonl" \
        "$CODEX_MOCK_DIR/peak" "$CODEX_MOCK_DIR/stagger"
  mkdir -p "$CODEX_MOCK_DIR/live"
  printf '%s' "$1" > "$CODEX_MOCK_DIR/scenario.json"
  if [ "${2:-}" = stagger ]; then : > "$CODEX_MOCK_DIR/stagger"; fi
}

turns_taken() { # scenario slots the mock has handed out since the last reset
  if [ -e "$CODEX_MOCK_DIR/counter" ]; then cat "$CODEX_MOCK_DIR/counter"; else echo 0; fi
}

live_count() { find "$CODEX_MOCK_DIR/live" -type f 2>/dev/null | wc -l | tr -d ' '; }

has_file() { if [ -e "$1" ]; then echo yes; else echo no; fi; }

wait_for_live() { # want deadline-seconds
  local deadline=$(( SECONDS + $2 ))
  while [ "$(live_count)" != "$1" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.1; done
  live_count
}

# --- journal reads: the same torn-tail tolerance loadJournal() applies --------
count_ev() { # jq select-expression -> how many parseable events match
  jq -R 'fromjson? // empty' "$journal" | jq -s "[.[] | select($1)] | length"
}
ev_started() { count_ev "(.type == \"started\") and (.key | startswith(\"agent|$1|\"))"; }
ev_finished() { count_ev "(.type == \"finished\") and (.key | startswith(\"agent|$1|\"))"; }

wait_ev() { # what-expr want deadline-seconds
  local deadline=$(( SECONDS + $3 ))
  while [ "$(count_ev "$1")" != "$2" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.1; done
  count_ev "$1"
}

# --- ledger reads ------------------------------------------------------------
job_ids() { # every workflow id the given workspace's ledger knows about
  node "$RUNTIME" status --json --all --cwd "${1:-$repo}" \
    | jq -r '[.running[], .latestFinished, .recent[]] | map(select(. != null)) | .[].id'
}
snapshot_status() { node "$RUNTIME" status --json --all --cwd "$repo" > "$scratch/status.json"; }
listed_field() { # job-id field
  jq -r --arg id "$1" --arg field "$2" \
    '[.running[], .latestFinished, .recent[]] | map(select(. != null)) | map(select(.id == $id)) | (.[0][$field] // "MISSING")' \
    "$scratch/status.json"
}
wait_job_id() { # exclude-ids deadline-seconds -> the one workflow id that is not excluded
  local deadline=$(( SECONDS + $2 )) id="" candidate
  while [ -z "$id" ] && [ "$SECONDS" -lt "$deadline" ]; do
    for candidate in $(job_ids || true); do
      case " $1 " in *" $candidate "*) continue ;; esac
      case "$candidate" in wf-*) id="$candidate" ;; esac
    done
    [ -n "$id" ] || sleep 0.2
  done
  printf '%s\n' "$id"
}

# ---------------------------------------------------------------------------
# Phase 1: kill a run with a hole in it.
#   A finishes, B hangs, C finishes while B is still in flight.
# ---------------------------------------------------------------------------
echo "-- phase 1: SIGKILL with a started-only call in the middle"
reset_mock '{"turns":[{"finalMessage":"A-first"},{"hangMs":60000},{"finalMessage":"C-first"}]}' stagger
node "$RUNTIME" workflow --script "$SCRIPT" --cwd "$repo" \
  > "$scratch/out1.json" 2> "$scratch/err1.log" &
verb_pid=$!
run_id="$(wait_job_id "" 30)"
if [ -n "$run_id" ]; then ok "run registered a job record while running"; else bad "run never registered a job record"; fi
run_dir="$CLAUDE_PLUGIN_DATA/workflows/$run_id"
journal="$run_dir/journal.jsonl"

assert_eq "C finished while B was still in flight" \
  1 "$(wait_ev '(.type == "finished") and (.key | startswith("agent|C|"))' 1 40)"
kill -9 "$verb_pid"
wait "$verb_pid" 2>/dev/null || true
kill_live_workers

# ---------------------------------------------------------------------------
# Phase 2: the journal records the hole, not a tidy prefix.
# ---------------------------------------------------------------------------
echo "-- phase 2: the journal kept the out-of-order truth"
assert_eq "A finished" 1 "$(ev_finished A)"
assert_eq "C finished" 1 "$(ev_finished C)"
assert_eq "B started" 1 "$(ev_started B)"
assert_eq "B never finished" 0 "$(ev_finished B)"
assert_eq "D never started" 0 "$(ev_started D)"
assert_eq "exactly two calls finished" 2 "$(count_ev '.type == "finished"')"
b_started_line="$(grep -n '"type":"started"' "$journal" | grep -F 'agent|B|' | cut -d: -f1)"
c_finished_line="$(grep -n '"type":"finished"' "$journal" | grep -F 'agent|C|' | cut -d: -f1)"
if [ "$b_started_line" -lt "$c_finished_line" ]; then
  ok "the finished calls are NOT a prefix of the started ones"
else
  bad "the hole is not in the middle (B started line $b_started_line, C finished line $c_finished_line)"
fi
assert_eq "the killed run left its lease behind" yes "$(has_file "$run_dir/lease.json")"

# ---------------------------------------------------------------------------
# Phase 3: a killed writer can leave half a line. Tolerating it must also mean
# CONTAINING it — the next append must not glue onto the torn line and take a
# good event down with it.
# ---------------------------------------------------------------------------
echo "-- phase 3: torn tail"
printf '%s' '{"type":"finis' >> "$journal"
# Command substitution strips trailing newlines, so a non-empty answer here IS
# the proof that the file no longer ends in one.
if [ -n "$(tail -c 1 "$journal")" ]; then ok "the journal now ends mid-line"; else bad "the torn line did not stick"; fi

# ---------------------------------------------------------------------------
# Phase 4: resume. Fresh scenario, fresh counter — every live turn from here is
# one the resume actually paid for.
# ---------------------------------------------------------------------------
echo "-- phase 4: resume re-runs the hole and nothing else"
reset_mock '{"turns":[{"finalMessage":"B-live"},{"finalMessage":"D-live"}]}'
rc=0
node "$RUNTIME" workflow --script "$SCRIPT" --resume "$run_id" --cwd "$repo" \
  > "$scratch/out2.json" 2> "$scratch/err2.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err2.log"
assert_eq "resume exits 0" 0 "$rc"
assert_eq "resume keeps the run id" "$run_id" "$(jq -r '.runId' "$scratch/out2.json")"

# B runs live inside the parallel (C is a cache hit and issues no turn), then D
# runs after it — so the two live turns take the scenario's slots in that order.
assert_eq "the mock served exactly two turns" 2 "$(turns_taken)"
assert_eq "two turn/start requests reached the mock" 2 "$(wc -l < "$CODEX_MOCK_DIR/turns.jsonl" | tr -d ' ')"
assert_eq "cached A keeps its ORIGINAL value" A-first "$(jq -r '.result.a' "$scratch/out2.json")"
assert_eq "cached C keeps its ORIGINAL value" C-first "$(jq -r '.result.c' "$scratch/out2.json")"
assert_eq "the hole B was re-run live" B-live "$(jq -r '.result.b' "$scratch/out2.json")"
assert_eq "the never-reached D ran live" D-live "$(jq -r '.result.d' "$scratch/out2.json")"
assert_eq "result.json composes the same object" \
  "A-first B-live C-first D-live" \
  "$(jq -r '[.a, .b, .c, .d] | join(" ")' "$run_dir/result.json")"
assert_eq "only the live calls are counted as agents" 2 "$(jq -r '.agents' "$scratch/out2.json")"
assert_contains "the cache hit for A is reported" "$scratch/err2.log" "[workflow] cache agent:A"
assert_contains "the cache hit for C is reported" "$scratch/err2.log" "[workflow] cache agent:C"
assert_absent "A was not re-run" "$scratch/err2.log" "[workflow] start agent:A"

assert_eq "A was never started a second time" 1 "$(ev_started A)"
assert_eq "C was never started a second time" 1 "$(ev_started C)"
assert_eq "B's re-run was journaled past the torn line" 2 "$(ev_started B)"
assert_eq "B finished this time" 1 "$(ev_finished B)"
assert_eq "D finished" 1 "$(ev_finished D)"
assert_eq "the finished run released its lease" no "$(has_file "$run_dir/lease.json")"

# ---------------------------------------------------------------------------
# Phase 5: two guards refuse a resume of a run that is still going — the
# ledger's liveness check (which protects the record) and the engine's lease
# (which is the race-free one, and the only one left when the ledger is blind).
# ---------------------------------------------------------------------------
echo "-- phase 5: a live run cannot be resumed out from under itself"
reset_mock '{"turns":[{"finalMessage":"A2"},{"hangMs":60000},{"finalMessage":"C2"}]}' stagger
node "$RUNTIME" workflow --script "$SCRIPT" --cwd "$repo" \
  > "$scratch/out3.json" 2> "$scratch/err3.log" &
verb_pid=$!
live_id="$(wait_job_id "$run_id" 30)"
if [ -n "$live_id" ]; then ok "second run registered its own record"; else bad "second run never registered"; fi
journal="$CLAUDE_PLUGIN_DATA/workflows/$live_id/journal.jsonl"
assert_eq "the second run also reached the hole" \
  1 "$(wait_ev '(.type == "finished") and (.key | startswith("agent|C|"))' 1 40)"
kill -9 "$verb_pid"
wait "$verb_pid" 2>/dev/null || true
kill_live_workers

# Resume it with a scenario that hangs, so the resumed run stays live.
reset_mock '{"turns":[{"hangMs":60000},{"finalMessage":"D2"}]}'
node "$RUNTIME" workflow --script "$SCRIPT" --resume "$live_id" --cwd "$repo" \
  > "$scratch/out4.json" 2> "$scratch/err4.log" &
resume_pid=$!
assert_eq "the resumed run has a live worker" 1 "$(wait_for_live 1 30)"
snapshot_status
assert_eq "the resumed run owns the record" running "$(listed_field "$live_id" status)"
assert_eq "the record names the resume process" "$resume_pid" "$(listed_field "$live_id" pid)"

rc=0
node "$RUNTIME" workflow --script "$SCRIPT" --resume "$live_id" --cwd "$repo" \
  > /dev/null 2> "$scratch/refuse-ledger.err" || rc=$?
assert_eq "resuming a live resume is refused" 1 "$rc"
assert_contains "the refusal names the active run" "$scratch/refuse-ledger.err" "is still active"
snapshot_status
assert_eq "the live run still owns its record" running "$(listed_field "$live_id" status)"
assert_eq "the live run's recorded pid is untouched" "$resume_pid" "$(listed_field "$live_id" pid)"

# Same resume from a workspace whose ledger has never heard of this run: the
# liveness check cannot fire, so the engine's lease is the only thing left.
rc=0
node "$RUNTIME" workflow --script "$SCRIPT" --resume "$live_id" --cwd "$other" \
  > /dev/null 2> "$scratch/refuse-lease.err" || rc=$?
assert_ne "a lease-blind resume is still refused" 0 "$rc"
assert_contains "the refusal names the lease" "$scratch/refuse-lease.err" "lease"
assert_absent "the lease refused before anything else could" "$scratch/refuse-lease.err" "fingerprint"
snapshot_status
assert_eq "the refused resume did not touch the live record" running "$(listed_field "$live_id" status)"
assert_eq "the refused resume did not take over the pid" "$resume_pid" "$(listed_field "$live_id" pid)"
assert_eq "the live worker survived both refusals" 1 "$(live_count)"

kill -TERM "$resume_pid"
rc=0; wait "$resume_pid" || rc=$?
assert_eq "the live resume was still cancellable" 130 "$rc"
assert_eq "cancelling it killed its worker" 0 "$(wait_for_live 0 5)"

# ---------------------------------------------------------------------------
# Phase 6: the repo moved on. A journal recorded against different content is
# not a cache any more, so the resume must refuse rather than compose stale
# results with fresh ones.
# ---------------------------------------------------------------------------
echo "-- phase 6: fingerprint drift"
git -C "$repo" -c user.email=t@example.com -c user.name=t \
  -c commit.gpgsign=false commit -q --allow-empty -m drift
reset_mock '{"turns":[{"finalMessage":"must-not-run"}]}'
rc=0
node "$RUNTIME" workflow --script "$SCRIPT" --resume "$run_id" --cwd "$repo" \
  > "$scratch/out5.json" 2> "$scratch/refuse-fp.err" || rc=$?
assert_ne "a drifted resume is refused" 0 "$rc"
assert_contains "the refusal names the fingerprint" "$scratch/refuse-fp.err" "fingerprint-mismatch"
# The refusal has to name WHICH input moved: repo content, repo path, script and
# args are four independent causes, and one shared message leaves the caller with
# four things to check and no way to tell which.
assert_contains "the refusal names the repository content as the cause" "$scratch/refuse-fp.err" \
  "changed since the original run: the repository content"
assert_absent "…and does not blame the script" "$scratch/refuse-fp.err" "workflow script"
assert_absent "…and does not blame the args" "$scratch/refuse-fp.err" "--args"
assert_eq "no turn was spent on the refused resume" 0 "$(turns_taken)"
assert_eq "the earlier result is left intact" \
  "A-first B-live C-first D-live" \
  "$(jq -r '[.a, .b, .c, .d] | join(" ")' "$run_dir/result.json")"
snapshot_status
assert_eq "the refused resume finalized its own record" failed "$(listed_field "$run_id" status)"

# ---------------------------------------------------------------------------
# Phase 7: the SCRIPT moved on while the repo stood still. An ad-hoc workflow
# script living outside the repo is invisible to a repo-only fingerprint, so a
# resume would serve a cache recorded against different orchestration code. The
# script's own content rides the fingerprint for exactly this case.
#
# The script here is a COPY in the scratch area, deliberately outside the repo:
# an in-repo script is already covered as untracked (or diffed) content, so only
# an out-of-tree one can tell the two fingerprints apart. Nothing about the repo
# changes across this phase, which is what makes the refusal below attributable
# to the script and to nothing else.
# ---------------------------------------------------------------------------
echo "-- phase 7: workflow script drift"
adhoc="$scratch/adhoc-workflow.mjs"
cp "$FIXTURES/fx-solo.mjs" "$adhoc"
head_before="$(git -C "$repo" rev-parse HEAD)"

reset_mock '{"turns":[{"finalMessage":"S-first"}]}'
rc=0
node "$RUNTIME" workflow --script "$adhoc" --cwd "$repo" \
  > "$scratch/out6.json" 2> "$scratch/err6.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err6.log"
assert_eq "the ad-hoc run exits 0" 0 "$rc"
drift_id="$(jq -r '.runId' "$scratch/out6.json")"

# Control leg: the UNEDITED script resumes and is served from the journal. Without
# it, a fingerprint that simply never matches for out-of-tree scripts would pass
# the refusal below for the wrong reason.
reset_mock '{"turns":[{"finalMessage":"must-not-run"}]}'
rc=0
node "$RUNTIME" workflow --script "$adhoc" --resume "$drift_id" --cwd "$repo" \
  > "$scratch/out7.json" 2> "$scratch/err7.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err7.log"
assert_eq "an unedited ad-hoc script still resumes" 0 "$rc"
assert_eq "the cached result came back" S-first "$(jq -r '.result.one' "$scratch/out7.json")"
assert_eq "no turn was spent on the cached resume" 0 "$(turns_taken)"

printf '\n// edited between runs\n' >> "$adhoc"
reset_mock '{"turns":[{"finalMessage":"must-not-run"}]}'
rc=0
node "$RUNTIME" workflow --script "$adhoc" --resume "$drift_id" --cwd "$repo" \
  > "$scratch/out8.json" 2> "$scratch/refuse-script.err" || rc=$?
assert_ne "an edited script refuses to resume" 0 "$rc"
assert_contains "the refusal names the fingerprint" "$scratch/refuse-script.err" "fingerprint-mismatch"
assert_contains "the refusal names the script as the cause" "$scratch/refuse-script.err" \
  "changed since the original run: the workflow script"
assert_absent "…and does not blame the repository" "$scratch/refuse-script.err" "repository content"
assert_eq "no turn was spent on the refused resume" 0 "$(turns_taken)"
assert_eq "the repo never moved during this phase" "$head_before" "$(git -C "$repo" rev-parse HEAD)"
assert_eq "the repo is still clean" "" "$(git -C "$repo" status --porcelain)"

# ---------------------------------------------------------------------------
# Phase 8: the --args contract. Args ride the run fingerprint, so a resume that
# does not repeat them byte-for-byte is refused — which would make EVERY resume
# of an args-taking workflow a refusal, since nothing used to record what the run
# was issued with. The run records them; a resume that names none is handed them
# back; a resume that names different ones is refused by name.
# ---------------------------------------------------------------------------
echo "-- phase 8: --args are recorded, and a resume defaults to them"
ARGS_SCRIPT="$FIXTURES/fx-args-count.mjs"
reset_mock '{"turns":[{"finalMessage":"N1"}]}'
rc=0
node "$RUNTIME" workflow --script "$ARGS_SCRIPT" --args '{"n":1}' --cwd "$repo" \
  > "$scratch/out9.json" 2> "$scratch/err9.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err9.log"
assert_eq "the args run exits 0" 0 "$rc"
args_id="$(jq -r '.runId' "$scratch/out9.json")"
args_dir="$CLAUDE_PLUGIN_DATA/workflows/$args_id"
assert_eq "the run recorded the args it was issued with" '{"n":1}' "$(jq -c '.' "$args_dir/args.json")"

reset_mock '{"turns":[{"finalMessage":"must-not-run"}]}'
rc=0
node "$RUNTIME" workflow --script "$ARGS_SCRIPT" --resume "$args_id" --cwd "$repo" \
  > "$scratch/out10.json" 2> "$scratch/err10.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err10.log"
assert_eq "a resume naming no --args replays the recorded ones" 0 "$rc"
assert_eq "the cached result came back" N1 "$(jq -r '.result[0]' "$scratch/out10.json")"
assert_eq "no turn was spent on the defaulted resume" 0 "$(turns_taken)"

rc=0
node "$RUNTIME" workflow --script "$ARGS_SCRIPT" --resume "$args_id" --args '{"n":1}' --cwd "$repo" \
  > "$scratch/out11.json" 2> "$scratch/err11.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err11.log"
assert_eq "a resume repeating the same --args also resumes" 0 "$rc"
assert_eq "no turn was spent on it either" 0 "$(turns_taken)"

rc=0
node "$RUNTIME" workflow --script "$ARGS_SCRIPT" --resume "$args_id" --args '{"n":2}' --cwd "$repo" \
  > /dev/null 2> "$scratch/refuse-args.err" || rc=$?
assert_ne "a resume with DIFFERENT --args is refused" 0 "$rc"
assert_contains "the refusal names the args as the cause" "$scratch/refuse-args.err" \
  "changed since the original run: --args"
assert_eq "no turn was spent on the refused resume" 0 "$(turns_taken)"

# ---------------------------------------------------------------------------
# Phase 9: the killed run's workers are still RUNNING. A SIGKILLed run cannot
# reap its own children, so a resume that just replays the unfinished leaf runs
# it a second time alongside the first — two app-servers doing the same work,
# with whatever side effects that carries. The resume sweeps workers.json before
# it starts, with the same instance-guarded kill cancel uses.
# ---------------------------------------------------------------------------
echo "-- phase 9: a resume reaps the workers the killed run left behind"
reset_mock '{"turns":[{"finalMessage":"A9"},{"hangMs":60000},{"finalMessage":"C9"}]}' stagger
node "$RUNTIME" workflow --script "$SCRIPT" --cwd "$repo" \
  > "$scratch/out12.json" 2> "$scratch/err12.log" &
verb_pid=$!
orphan_id="$(wait_job_id "$run_id $live_id $drift_id $args_id" 30)"
if [ -n "$orphan_id" ]; then ok "the run registered a record"; else bad "the run never registered a record"; fi
orphan_dir="$CLAUDE_PLUGIN_DATA/workflows/$orphan_id"
assert_eq "one worker is left hanging" 1 "$(wait_for_live 1 40)"

# SIGKILL only the run process: its children are deliberately left alive, which
# is exactly the state a crashed harness leaves behind.
kill -9 "$verb_pid"
wait "$verb_pid" 2>/dev/null || true
orphan_pids="$(jq -r '.[] | if type == "number" then . else .pid end' "$orphan_dir/workers.json")"
assert_ne "the killed run left a worker tracked" "" "$orphan_pids"
alive=0
for p in $orphan_pids; do if kill -0 "$p" 2>/dev/null; then alive=$((alive + 1)); fi; done
assert_eq "…and that worker outlived the run" 1 "$alive"

# A fresh scenario WITHOUT reset_mock: resetting would kill the orphan itself.
printf '%s' '{"turns":[{"finalMessage":"B9"},{"finalMessage":"D9"}]}' > "$CODEX_MOCK_DIR/scenario.json"
rm -f "$CODEX_MOCK_DIR/counter" "$CODEX_MOCK_DIR/turns.jsonl" "$CODEX_MOCK_DIR/stagger"
rc=0
node "$RUNTIME" workflow --script "$SCRIPT" --resume "$orphan_id" --cwd "$repo" \
  > "$scratch/out13.json" 2> "$scratch/err13.log" || rc=$?
[ "$rc" -eq 0 ] || cat "$scratch/err13.log"
assert_eq "the resume exits 0" 0 "$rc"

deadline=$(( SECONDS + 10 ))
still=1
while [ "$still" -ne 0 ] && [ "$SECONDS" -lt "$deadline" ]; do
  still=0
  for p in $orphan_pids; do if kill -0 "$p" 2>/dev/null; then still=$((still + 1)); fi; done
  [ "$still" -eq 0 ] || sleep 0.2
done
assert_eq "the orphaned worker was reaped by the resume" 0 "$still"
assert_contains "the resume reports what it swept" "$scratch/err13.log" "orphaned worker"

if [ "$fail" -eq 0 ]; then echo "workflow resume: all phases passed"; fi
exit "$fail"
