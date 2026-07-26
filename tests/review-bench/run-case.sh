#!/usr/bin/env bash
# run-case.sh — X1 review-benchmark runner: one case x one engine -> findings file.
#
# The X1 contract (docs/doperpowers/specs/2026-07-26-claude-review-stack-roadmap.md):
# both engines review the SAME committed branch-vs-base range of a materialized
# case repo; the argus side always runs through the headless invocation path
# (the C1.G3 probe mechanism) so baseline and deployment measure the same thing.
#
# Usage:
#   run-case.sh --case <case-dir> --engine codex|argus --out <findings-file>
#
# Case dir layouts:
#   seeded:  base/ + patch.diff (+ truth.json, case.md, intent.md)
#   real:    case.json {"repo": "<owner/name-or-local-path>", "head": "<sha>", "base": "<sha>"}
#
# Env: CODEX_REVIEW_MODEL / CODEX_REVIEW_EFFORT pass through to review-engine.sh.
#      ARGUS_TIMEOUT (default 2700s) bounds the argus run; codex is bounded the same.
#      BENCH_KEEP=1 keeps the scratch repo (printed) for postmortem.
set -euo pipefail

usage() { echo "usage: run-case.sh --case <dir> --engine codex|argus --out <file>" >&2; exit 2; }
case_dir="" engine="" out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --case)   case_dir="${2:-}"; shift 2 ;;
    --engine) engine="${2:-}"; shift 2 ;;
    --out)    out="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$case_dir" ] && [ -n "$engine" ] && [ -n "$out" ] || usage
case "$engine" in codex|argus) ;; *) usage ;; esac
case_dir="$(cd "$case_dir" && pwd)"
out="$(cd "$(dirname "$out")" && pwd)/$(basename "$out")"
bench_root="$(cd "$(dirname "$0")" && pwd)"
timeout_s="${ARGUS_TIMEOUT:-2700}"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/review-bench.XXXXXX")"
cleanup() { [ "${BENCH_KEEP:-0}" = "1" ] && echo "scratch kept: $scratch" >&2 || rm -rf "$scratch"; }
trap cleanup EXIT

# --- Materialize: a repo with base branch `main` and the change committed on `bench-change`.
if [ -f "$case_dir/patch.diff" ]; then
  cp -R "$case_dir/base/." "$scratch/"
  git -C "$scratch" init -q -b main
  git -C "$scratch" add -A
  git -C "$scratch" -c user.email=bench@x -c user.name=bench commit -qm "base"
  git -C "$scratch" checkout -q -b bench-change
  git -C "$scratch" apply "$case_dir/patch.diff"
  git -C "$scratch" add -A
  msg="bench change"
  [ -f "$case_dir/intent.md" ] && msg="$(head -1 "$case_dir/intent.md")"
  git -C "$scratch" -c user.email=bench@x -c user.name=bench commit -qm "$msg"
elif [ -f "$case_dir/case.json" ]; then
  repo="$(jq -r .repo "$case_dir/case.json")"
  head_sha="$(jq -r .head "$case_dir/case.json")"
  base_sha="$(jq -r .base "$case_dir/case.json")"
  src="$repo"; [ -d "$src/.git" ] || src="https://github.com/$repo.git"
  git clone -q "$src" "$scratch/repo"
  scratch_repo="$scratch/repo"
  git -C "$scratch_repo" fetch -q origin "$head_sha" "$base_sha" 2>/dev/null || true
  git -C "$scratch_repo" checkout -q -b main "$base_sha"
  git -C "$scratch_repo" checkout -q -b bench-change "$head_sha"
  scratch="$scratch_repo"
else
  echo "run-case: $case_dir has neither patch.diff nor case.json" >&2; exit 2
fi
merge_base="$(git -C "$scratch" merge-base main bench-change)"

# --- Run the engine from the scratch repo root, on branch bench-change.
cd "$scratch"
started="$(date +%s)"
case "$engine" in
  codex)
    "$bench_root/../../skills/reviewing-prs/scripts/review-engine.sh" \
      --base main --out "$out"
    ;;
  argus)
    # Headless path (C1.G3): plain-level, base-branch target with precomputed
    # merge base — the same seed the skill's Step 3A prescribes.
    prompt="/argus-review:argus-review Review the code changes against the base branch 'main'. The merge base commit for this comparison is ${merge_base}. Run \`git diff ${merge_base}\` to inspect the changes relative to main. Provide prioritized, actionable findings. Use the plain effort level."
    timeout "$timeout_s" claude -p "$prompt" --permission-mode auto > "$out"
    ;;
esac
echo "engine=$engine case=$(basename "$case_dir") secs=$(( $(date +%s) - started )) out=$out" >&2
