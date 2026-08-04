#!/usr/bin/env bash
# run-case-workflow.sh — X1 bench adapter for the codex review PANEL
# (skills/codex-companion/workflows/code-review.mjs on the `workflow` verb).
#
# Same contract as run-case.sh: one case -> one findings file the adjudication
# flow reads like any other engine output. Materialization is identical (the
# committed `bench-change` branch vs `main` in an ephemeral scratch repo), so a
# panel run is comparable to the recorded codex-engine baseline.
#
# Usage:
#   run-case-workflow.sh --case <case-dir> --out <findings-file>
#
# Alongside <findings-file> it writes:
#   <findings-file>.json        the verb's stdout ({runId, result, agents, ...})
#   <findings-file>.events.log  the verb's [workflow] progress stream
# The run id in the JSON names the journal directory
# ($CLAUDE_PLUGIN_DATA/workflows/<run-id>/) that holds every finder's raw
# reviewText — the only place to audit clean-sentinel compliance after the fact.
#
# Env: CLAUDE_PLUGIN_DATA pins the workflow state root (defaults to a bench-local
#      root so a bench run never collides with a session's own runs).
#      CODEX_COMPANION_SESSION_ID scopes the job record (default: bench-<case>).
#      PANEL_ARGS overrides the --args JSON (default {"base":"main"}); use it to
#      pin finderModel/finderEffort/verifierEffort for an engine-cell run.
#      PANEL_CONCURRENCY sets --max-concurrency (default: the verb's own 6).
#      BENCH_KEEP=1 keeps the scratch repo (printed) for postmortem.
#
# Deliberately NOT set: CODEX_COMPANION_APP_SERVER_ENDPOINT. The workflow engine
# connects every worker with disableBroker, so the endpoint env is never read.
set -euo pipefail

usage() {
  echo "usage: run-case-workflow.sh --case <dir> --out <file>" >&2
  exit 2
}

case_dir="" out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --case) case_dir="${2:-}"; shift 2 ;;
    --out) out="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$case_dir" ] && [ -n "$out" ] || usage

case_dir="$(cd "$case_dir" && pwd)"
out="$(cd "$(dirname "$out")" && pwd)/$(basename "$out")"
bench_root="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$bench_root/../.." && pwd)"
runtime="$repo_root/skills/codex-companion/runtime/scripts/codex-companion.mjs"
panel="$repo_root/skills/codex-companion/workflows/code-review.mjs"
case_name="$(basename "$case_dir")"

command -v node >/dev/null || { echo "run-case-workflow: node is required" >&2; exit 2; }
[ -f "$runtime" ] || { echo "run-case-workflow: no runtime at $runtime" >&2; exit 2; }
[ -f "$panel" ] || { echo "run-case-workflow: no panel script at $panel" >&2; exit 2; }

scratch="$(mktemp -d "${TMPDIR:-/tmp}/review-bench.XXXXXX")"
cleanup() { [ "${BENCH_KEEP:-0}" = "1" ] && echo "scratch kept: $scratch" >&2 || rm -rf "$scratch"; }
trap cleanup EXIT

# --- Materialize: a repo with base branch `main` and the change committed on
# `bench-change` — byte-for-byte the same procedure as run-case.sh, so the panel
# reviews the identical range the baseline engines reviewed.
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
  src="$repo"
  [ -d "$src/.git" ] || src="https://github.com/$repo.git"
  git clone -q "$src" "$scratch/repo"
  scratch_repo="$scratch/repo"
  git -C "$scratch_repo" fetch -q origin "$head_sha" "$base_sha" 2>/dev/null || true
  git -C "$scratch_repo" checkout -q -B main "$base_sha"
  git -C "$scratch_repo" checkout -q -B bench-change "$head_sha"
  # Same reason as run-case.sh: an origin/main that already contains the merged
  # head would collapse the merge base onto the head itself — an empty diff.
  git -C "$scratch_repo" remote remove origin
  scratch="$scratch_repo"
else
  echo "run-case-workflow: $case_dir has neither patch.diff nor case.json" >&2
  exit 2
fi

# --- Run the panel as ONE foreground process from the scratch repo.
export CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/doperpowers/codex-companion-bench}"
export CODEX_COMPANION_SESSION_ID="${CODEX_COMPANION_SESSION_ID:-bench-$case_name}"
concurrency=()
[ -n "${PANEL_CONCURRENCY:-}" ] && concurrency=(--max-concurrency "$PANEL_CONCURRENCY")

panel_args="${PANEL_ARGS:-}"
[ -n "$panel_args" ] || panel_args='{"base":"main"}'

started="$(date +%s)"
set +e
node "$runtime" workflow \
  --script "$panel" \
  --args "$panel_args" \
  --cwd "$scratch" \
  ${concurrency[@]+"${concurrency[@]}"} \
  >"$out.json" 2>"$out.events.log"
rc=$?
set -e
secs=$(($(date +%s) - started))

if [ "$rc" -ne 0 ]; then
  echo "run-case-workflow: workflow verb exited $rc (see $out.events.log)" >&2
  tail -5 "$out.events.log" >&2 || true
  exit "$rc"
fi

# --- Render the panel result as a findings file.
# Coverage is rendered in its own right, not folded into the explanation: a lost
# sweep (or a null verifier) rewrites the explanation and would hide the other
# lost lanes from a reader who only had the prose.
python3 - "$out.json" >"$out" <<'PY'
import json, sys

doc = json.load(open(sys.argv[1]))
r = doc.get("result") or {}
w = sys.stdout.write

w(f"panel verdict: {r.get('verdict','(none)')}\n")
w(f"explanation: {r.get('explanation','')}\n")
w(f"run: runId={doc.get('runId','?')} agents={doc.get('agents','?')} durationMs={doc.get('durationMs','?')}\n")

lenses = r.get("lenses") or []
w(f"\nderived lenses ({len(lenses)}):\n")
for i, lens in enumerate(lenses, 1):
    w(f"  scalpel-{i}: {lens}\n")
if not lenses:
    w("  (none — sweep only)\n")

# Coverage stands on its own: the explanation is rewritten by a lost sweep or a
# null verifier and then names none of the other lost lanes.
cov = r.get("coverage") or []
w(f"\ncoverage ({sum(1 for c in cov if c.get('status') == 'ok')}/{len(cov)} ok):\n")
for c in cov:
    w(f"  {c.get('finder')}: status={c.get('status')} stubs={c.get('stubs')}"
      f" lens={c.get('lens') or '(lens-free sweep)'}\n")

findings = r.get("findings") or []
w(f"\nFull review comments ({len(findings)}):\n\n")
for f in findings:
    loc = f"{f.get('file','?')}:{f.get('lines','?')}"
    w(f"- [{f.get('priority','P?')}] {f.get('title','')} — {loc}\n")
    w(f"  {(f.get('comment') or '').strip()}\n")
    w(f"  (raised by: {', '.join(f.get('sources') or [])})\n\n")
if not findings:
    w("(no confirmed findings)\n\n")

# Only present when the verifier could not be made to honour its contract; these
# are candidates nobody re-inspected, so they are labelled, never scored as findings.
pool = r.get("pool")
if pool is not None:
    w(f"UNVERIFIED candidate pool ({len(pool)}) — verifier produced no valid verdict set:\n")
    for s in pool:
        w(f"- [{s.get('priority','P?')}] {s.get('title','')} — {s.get('file','?')}:{s.get('lines','?')} ({s.get('id')})\n")
        if s.get("body"):
            w(f"  {s['body'].strip()}\n")
PY

echo "engine=panel case=$case_name secs=$secs out=$out" >&2
