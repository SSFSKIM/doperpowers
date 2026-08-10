#!/usr/bin/env bash
# run-case.sh — X1 review-benchmark runner: one case x one engine -> findings file.
#
# The X1 contract (docs/doperpowers/specs/2026-07-26-claude-review-stack-roadmap.md):
# both engines review the SAME committed branch-vs-base range of a materialized
# case repo; the argus side always runs through the headless invocation path
# (the C1.G3 probe mechanism) so baseline and deployment measure the same thing.
#
# Usage:
#   run-case.sh --case <case-dir> --engine codex|argus|review|code-review --out <findings-file>
#
#   review / code-review run Claude Code's BUILT-IN slash commands in a fresh
#   `claude --bg` background session started from the scratch repo (not the
#   headless -p path): launch, poll ~/.claude/jobs/<id>/state.json until done,
#   then extract the ReportFindings tool call (from the transcript that
#   state.json's linkScanPath names) plus the final message.
#
# Case dir layouts:
#   seeded:  base/ + patch.diff (+ truth.json, case.md, intent.md)
#   real:    case.json {"repo": "<owner/name-or-local-path>", "head": "<sha>", "base": "<sha>"}
#
# Env: CODEX_REVIEW_MODEL / CODEX_REVIEW_EFFORT pick the codex model/effort.
#      ARGUS_TIMEOUT (default 2700s) bounds the argus run; codex is bounded the same.
#      ARGUS_LEVEL (default plain) pins the argus effort level.
#      CR_LEVEL (default medium) pins the code-review effort level.
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
case "$engine" in codex|argus|review|code-review) ;; *) usage ;; esac
case_dir="$(cd "$case_dir" && pwd)"
out="$(cd "$(dirname "$out")" && pwd)/$(basename "$out")"
bench_root="$(cd "$(dirname "$0")" && pwd)"
timeout_s="${ARGUS_TIMEOUT:-2700}"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/review-bench.XXXXXX")"
eng_home=""
cleanup() {
  if [ -n "$eng_home" ]; then rm -rf "$eng_home"; fi
  [ "${BENCH_KEEP:-0}" = "1" ] && echo "scratch kept: $scratch" >&2 || rm -rf "$scratch"
}
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
  git -C "$scratch_repo" checkout -q -B main "$base_sha"
  git -C "$scratch_repo" checkout -q -B bench-change "$head_sha"
  # Kill the origin remote: both engines prefer a branch's upstream when it
  # is ahead, and origin/main (which already contains a merged PR's head)
  # would resolve the merge base to the head itself — an empty diff.
  git -C "$scratch_repo" remote remove origin
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
    # The production single-review path (review-engine.sh is retired): the
    # with-effort wrapper serving the native review verb, findings on stdout,
    # under the same preamble the live loop's START ENGINE sets up — codex
    # must WRITE session state, the default home may be read-only under an
    # outer sandbox, and that state must stay out of the reviewed tree. So:
    # a throwaway CODEX_HOME with login symlinked over, an isolated
    # CLAUDE_PLUGIN_DATA (the job ledger is unlocked read-modify-write), TLS
    # anchors as a FILE bundle, and the code-mode host a nested codex
    # resolves to /usr/local/bin instead of ~/.local/bin.
    eng_home="$(mktemp -d "${TMPDIR:-/tmp}/review-bench-codex.XXXXXX")"
    source_codex_home="${CODEX_HOME:-$HOME/.codex}"
    if [ -f "$source_codex_home/auth.json" ]; then
      ln -s "$source_codex_home/auth.json" "$eng_home/auth.json"
    fi
    export CODEX_HOME="$eng_home" CLAUDE_PLUGIN_DATA="$eng_home/companion-state"
    if [ -z "${SSL_CERT_FILE:-}" ]; then
      for _cert in /etc/ssl/cert.pem /etc/ssl/certs/ca-certificates.crt; do
        if [ -f "$_cert" ]; then export SSL_CERT_FILE="$_cert"; break; fi
      done
    fi
    if [ -z "${CODEX_CODE_MODE_HOST_PATH:-}" ] && [ -x "$HOME/.local/bin/codex-code-mode-host" ]; then
      export CODEX_CODE_MODE_HOST_PATH="$HOME/.local/bin/codex-code-mode-host"
    fi
    node "$bench_root/../../skills/codex-companion/scripts/with-effort.mjs" \
      --effort "${CODEX_REVIEW_EFFORT:-xhigh}" -- \
      review --base main --wait --model "${CODEX_REVIEW_MODEL:-gpt-5.6-sol}" \
      > "$out" 2> "$out.events.log"
    ;;
  argus)
    # Headless path (C1.G3): base-branch target with precomputed merge base —
    # the same seed the skill's Step 3A prescribes. ARGUS_LEVEL (default
    # plain) pins the effort level explicitly (X3: named level always wins).
    level="${ARGUS_LEVEL:-plain}"
    prompt="/argus-review:argus-review Review the code changes against the base branch 'main'. The merge base commit for this comparison is ${merge_base}. Run \`git diff ${merge_base}\` to inspect the changes relative to main. Provide prioritized, actionable findings. Use the ${level} effort level."
    # ARGUS_CLAUDE_ARGS: extra claude flags (model/effort/settings) for
    # engine-cell experiments, e.g. "--settings ~/.claude/clodex-settings.json
    # --model fable --effort xhigh" for the clodex gateway route. Unquoted on
    # purpose (word-split flags).
    # shellcheck disable=SC2086
    timeout "$timeout_s" claude -p "$prompt" --permission-mode auto ${ARGUS_CLAUDE_ARGS:-} > "$out"
    ;;
  review|code-review)
    # Built-in slash commands, run as a real background session (`claude --bg`)
    # from the scratch repo — same target seeding as the argus prompt so the
    # engines measure the same comparison.
    # Both commands take STRUCTURED args (freeform prose after the command is
    # misparsed as a target) — /review is documented PR-only, so it runs bare
    # as a behavioral probe; /code-review gets the explicit merge-base range.
    if [ "$engine" = "review" ]; then
      prompt="/review"
    else
      prompt="/code-review ${CR_LEVEL:-medium} main...bench-change"
    fi
    # ARGUS_CLAUDE_ARGS applies here too (model/effort/settings cell pinning).
    # shellcheck disable=SC2086
    launch="$(claude --bg --permission-mode auto ${ARGUS_CLAUDE_ARGS:-} "$prompt" 2>&1)" || { printf '%s\n' "$launch" >&2; exit 1; }
    job_id="$(printf '%s\n' "$launch" | sed $'s/\x1b\\[[0-9;]*m//g' | sed -n 's/^backgrounded · \([0-9a-f]*\).*/\1/p')"
    [ -n "$job_id" ] || { echo "run-case: could not parse bg job id from launch output:" >&2; printf '%s\n' "$launch" >&2; exit 1; }
    state_file="$HOME/.claude/jobs/$job_id/state.json"
    echo "run-case: bg job $job_id ($prompt) — polling $state_file" >&2
    waited=0
    while :; do
      st="$(python3 -c "import json;print(json.load(open('$state_file')).get('state',''))" 2>/dev/null || echo "")"
      case "$st" in done|failed|error) break ;; esac
      if [ "$waited" -ge "$timeout_s" ]; then
        echo "run-case: bg job $job_id timed out after ${timeout_s}s (state=$st)" >&2
        claude stop "$job_id" >/dev/null 2>&1 || true
        exit 1
      fi
      sleep 15; waited=$((waited+15))
    done
    python3 "$bench_root/extract-bg-findings.py" "$state_file" "$st" > "$out"
    ;;
esac
echo "engine=$engine case=$(basename "$case_dir") secs=$(( $(date +%s) - started )) out=$out" >&2
