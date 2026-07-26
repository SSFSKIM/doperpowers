#!/usr/bin/env bash
# run-batch.sh — run a set of cases against one engine into results/<run-id>/.
#
# Usage: run-batch.sh --engine codex|argus --run-id <id> [--cases "case1 case2 …"]
#   --cases  space-separated case names under cases/seeded or cases/real
#            (default: every seeded case, then every real case)
#   --jobs   parallel runs (default 2 — engine backends rate-limit; keep low)
# Findings land as results/<run-id>/<case>.<engine>.txt (+ .log per case).
set -uo pipefail

bench_root="$(cd "$(dirname "$0")" && pwd)"
engine="" run_id="" cases="" jobs=2
while [ $# -gt 0 ]; do
  case "$1" in
    --engine) engine="${2:-}"; shift 2 ;;
    --run-id) run_id="${2:-}"; shift 2 ;;
    --cases)  cases="${2:-}"; shift 2 ;;
    --jobs)   jobs="${2:-}"; shift 2 ;;
    *) echo "usage: run-batch.sh --engine codex|argus --run-id <id> [--cases \"…\"] [--jobs N]" >&2; exit 2 ;;
  esac
done
[ -n "$engine" ] && [ -n "$run_id" ] || { echo "run-batch: --engine and --run-id required" >&2; exit 2; }

if [ -z "$cases" ]; then
  for d in "$bench_root"/cases/seeded/*/ "$bench_root"/cases/real/*/; do
    [ -d "$d" ] && cases="$cases $(basename "$d")"
  done
fi

outdir="$bench_root/results/$run_id"
mkdir -p "$outdir"

resolve_case_dir() {
  if [ -d "$bench_root/cases/seeded/$1" ]; then echo "$bench_root/cases/seeded/$1"
  elif [ -d "$bench_root/cases/real/$1" ]; then echo "$bench_root/cases/real/$1"
  else return 1; fi
}

pids=() names=()
running=0 fail=0
for c in $cases; do
  dir="$(resolve_case_dir "$c")" || { echo "run-batch: unknown case $c" >&2; fail=1; continue; }
  out="$outdir/$c.$engine.txt"
  if [ -s "$out" ]; then echo "skip $c ($engine): $out exists" >&2; continue; fi
  "$bench_root/run-case.sh" --case "$dir" --engine "$engine" --out "$out" \
    > "$outdir/$c.$engine.log" 2>&1 &
  pids+=($!); names+=("$c")
  running=$((running+1))
  if [ "$running" -ge "$jobs" ]; then
    wait "${pids[0]}" || { echo "FAIL ${names[0]} ($engine) — see $outdir/${names[0]}.$engine.log" >&2; fail=1; }
    pids=("${pids[@]:1}"); names=("${names[@]:1}"); running=$((running-1))
  fi
done
i=0
for p in ${pids[@]+"${pids[@]}"}; do
  wait "$p" || { echo "FAIL ${names[$i]} ($engine) — see $outdir/${names[$i]}.$engine.log" >&2; fail=1; }
  i=$((i+1))
done
echo "batch done: engine=$engine run-id=$run_id ($(ls "$outdir" | grep -c "\.$engine\.txt$") findings files)" >&2
exit "$fail"
