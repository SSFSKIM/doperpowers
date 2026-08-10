#!/usr/bin/env bash
# review-engine.sh — the ONE review-engine invocation for the reviewing-prs
# loop, driven by the doperpowers:codex-companion runtime (vendored codex
# app-server client; sibling skill). PURE correctness review: a plain run is
# codex's native `review` verb with no ticket/spec input of any kind — and
# on a big diff it routes instead to the companion's code-review PANEL
# (native sweep + diff-derived scalpel lenses + binding verifier; see the
# panel-routing block below), still behind the same --base/--out contract.
# The single optional modification is a diff-derived structural LENS
# (CODEX_REVIEW_LENS_FILE / CODEX_REVIEW_LENS, see the lens block below),
# which routes the run through the `adversarial-review` verb with the lens
# as its focus mandate. Ticket/spec compliance is the REVIEW WORKER's own
# audit, performed outside this engine (skills/reviewing-prs/SKILL.md). The
# script stays synchronous; the caller chooses foreground or background. The
# verdict lands in --out as rendered findings (progress stream:
# <out>.events.log); the PR diff never enters the caller's context.
#
# Usage: review-engine.sh --base <ref> --out <file>
#   --base  diff base (e.g. origin/main); the engine reviews <ref>...HEAD
#   --out   findings file the engine writes
# Env: CODEX_REVIEW_MODEL (default gpt-5.6-sol), CODEX_REVIEW_EFFORT
# (default xhigh), CODEX_REVIEW_LENS_FILE / CODEX_REVIEW_LENS (optional
# diff-derived structural focus mandate — see the lens block below; both
# empty keeps the plain review), CODEX_REVIEW_PANEL (auto|always|never,
# default auto — see the panel-routing block below).
# Run from the worktree root — the engine reviews $PWD.
# Exits 127 when codex/node are missing, 2 on usage error, else the
# runtime's rc.
set -euo pipefail

usage() { echo "usage: review-engine.sh --base <ref> --out <file>" >&2; exit 2; }
base="" out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base="${2:-}"; shift 2 ;;
    --out)  out="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$base" ] && [ -n "$out" ] || usage
command -v codex >/dev/null 2>&1 || { echo "review-engine: codex CLI not found" >&2; exit 127; }
command -v node  >/dev/null 2>&1 || { echo "review-engine: node not found" >&2; exit 127; }

script_dir="$(cd "$(dirname "$0")" && pwd)"
companion="${REVIEW_COMPANION_DIR:-$script_dir/../../codex-companion}"   # override: tests
[ -f "$companion/scripts/with-effort.mjs" ] || { echo "review-engine: codex-companion skill not found at $companion" >&2; exit 127; }

model="${CODEX_REVIEW_MODEL:-gpt-5.6-sol}"
effort="${CODEX_REVIEW_EFFORT:-xhigh}"
source_codex_home="${CODEX_HOME:-$HOME/.codex}"

# TLS trust anchors as a FILE bundle — a nested codex cannot reach the OS
# keychain/trustd under the outer seatbelt (shakedown FU-6). macOS ships the
# bundle as cert.pem, Debian/Ubuntu as ca-certificates.crt.
if [ -z "${SSL_CERT_FILE:-}" ]; then
  for _cert in /etc/ssl/cert.pem /etc/ssl/certs/ca-certificates.crt; do
    if [ -f "$_cert" ]; then export SSL_CERT_FILE="$_cert"; break; fi
  done
fi
# A nested codex resolves its code-mode command host to /usr/local/bin
# (absent here) instead of ~/.local/bin — point it explicitly.
if [ -z "${CODEX_CODE_MODE_HOST_PATH:-}" ] && [ -x "$HOME/.local/bin/codex-code-mode-host" ]; then
  export CODEX_CODE_MODE_HOST_PATH="$HOME/.local/bin/codex-code-mode-host"
fi
# Temporary CODEX_HOME: the engine must WRITE session state, and the default
# ~/.codex is read-only under the outer seatbelt. Keep that state outside the
# reviewed tree so untracked snapshots cannot affect the review. auth.json is
# symlinked so login state carries over. A temporary CLAUDE_PLUGIN_DATA
# isolates each run's companion job ledger (state.json is unlocked
# read-modify-write — parallel lens runs must not share a root). Both removed
# on every exit path.
eng_home="$(mktemp -d "${TMPDIR:-/tmp}/review-engine-home.XXXXXX")"
trap 'rm -rf "$eng_home"' EXIT
if [ -f "$source_codex_home/auth.json" ]; then
  ln -s "$source_codex_home/auth.json" "$eng_home/auth.json"
fi
export CODEX_HOME="$eng_home"
export CLAUDE_PLUGIN_DATA="$eng_home/companion-state"

# Nested-codex caveat: review threads run their probing commands under
# codex's own read-only sandbox, applied unconditionally by the app-server
# (thread/start pins it; codex never skips seatbelt when CODEX_SANDBOX says
# it is already inside one — verified against codex-rs). Under an OUTER
# codex seatbelt those probes may fail; the review still renders findings
# from the diff. Claude-harness workers (this loop's normal shape) are
# unaffected. Warn so a degraded nested run is attributable.
if [ -n "${CODEX_SANDBOX:-}" ]; then
  echo "review-engine: warning — running nested under a codex sandbox; engine probe commands may be confined" >&2
fi

# Optional lens: a diff-derived structural focus mandate. A lensed run uses
# the adversarial-review verb — the steerable challenge review — with the
# lens as its focus text; the rubric hunts along that mandate instead of
# re-running the broad native sweep. Never ticket/spec content.
# CODEX_REVIEW_LENS_FILE (a path; read verbatim, so generated prose never
# passes through shell interpolation — the review worker MUST use this form)
# takes precedence over CODEX_REVIEW_LENS (inline, for trusted/manual
# invocations). The lens travels as a single argv element after `--`, so the
# companion parser never re-tokenizes it into flags. Both empty/unset =
# the plain native review.
lens=""
if [ -n "${CODEX_REVIEW_LENS_FILE:-}" ]; then
  [ -f "$CODEX_REVIEW_LENS_FILE" ] || { echo "review-engine: CODEX_REVIEW_LENS_FILE not found: $CODEX_REVIEW_LENS_FILE" >&2; exit 2; }
  lens="$(cat "$CODEX_REVIEW_LENS_FILE")"
elif [ -n "${CODEX_REVIEW_LENS:-}" ]; then
  lens="$CODEX_REVIEW_LENS"
fi

verb_args=( review --base "$base" --wait --model "$model" )
if [ -n "$lens" ]; then
  verb_args=( adversarial-review --base "$base" --wait --model "$model" -- "$lens" )
fi

# Panel routing: one reviewer's recall thins on a big diff — the multilens
# execplan's PR752 benchmark (22 files, +2,101 lines) had the best single
# engine find 10 of 13 confirmed defects while seven single runs' union
# found all 13. At the codex-companion rule-of-thumb threshold (~20+ files
# or ~2k changed lines) a plain run therefore routes to the bundled
# code-review panel — one native sweep, diff-derived scalpel lenses, one
# binding verifier — instead of a single native review. A lensed
# invocation is already a scalpel and never routes. CODEX_REVIEW_PANEL
# overrides the size gate: `always` / `never` (default `auto`).
panel=""
if [ -z "$lens" ]; then
  case "${CODEX_REVIEW_PANEL:-auto}" in
    always) panel=1 ;;
    never)  ;;
    auto)
      # --numstat: "added deleted path"; binary files carry "-" and count
      # toward files only. A git failure (unfetched base, not a repo) counts
      # nothing — the review verb below then surfaces the real error.
      counts="$({ git diff --numstat "$base...HEAD" 2>/dev/null || true; } | \
        awk '{files++; if ($1 != "-") changed += $1 + $2} END {printf "%d %d", files+0, changed+0}')"
      if [ "${counts% *}" -ge 20 ] || [ "${counts#* }" -ge 2000 ]; then panel=1; fi
      ;;
    *) echo "review-engine: CODEX_REVIEW_PANEL must be auto|always|never (got: $CODEX_REVIEW_PANEL)" >&2; exit 2 ;;
  esac
fi

rc=0
if [ -n "$panel" ]; then
  # The workflow verb runs the panel as ONE foreground process; every worker
  # spawns its own app-server (disableBroker), so with-effort's private
  # endpoint has no role here — finder/verifier model and effort ride the
  # script args instead. Args are built by node so no shell value is ever
  # interpolated into JSON. The raw panel result stays in <out>.panel.json
  # beside the rendered findings for the review trail.
  args_json="$(P_BASE="$base" P_MODEL="$model" P_EFFORT="$effort" node -e \
    'console.log(JSON.stringify({base: process.env.P_BASE, finderModel: process.env.P_MODEL, finderEffort: process.env.P_EFFORT, verifierModel: process.env.P_MODEL}))')"
  node "$companion/runtime/scripts/codex-companion.mjs" workflow \
    --script "$companion/workflows/code-review.mjs" \
    --args "$args_json" > "$out.panel.json" 2> "$out.events.log" || rc=$?
  if [ "$rc" -eq 0 ]; then
    # Exit 4 = panel verdict `interrupted` (lost lane or moved head): no
    # findings file exists, the caller retries like any engine failure.
    node "$script_dir/render-panel-findings.mjs" "$out.panel.json" > "$out" || rc=$?
  fi
else
  # with-effort.mjs serves the verb a private app-server carrying the effort
  # override (the review protocol has no effort field) and provides its own
  # live endpoint — no detached broker, nothing outlives this run. Findings
  # render on stdout (--out), progress on stderr (<out>.events.log).
  node "$companion/scripts/with-effort.mjs" --effort "$effort" -- \
    "${verb_args[@]}" > "$out" 2> "$out.events.log" || rc=$?
fi

# Fail closed when the engine's own fs sandbox never worked. Observed live
# (ida-worker-1, 2026-08-09): a host that blocks unprivileged userns makes
# every probe fail (`bwrap: loopback: Failed RTM_NEWADDR`), yet codex exits 0
# and renders findings anyway — 22 consecutive runs across 6 review workers
# passed as "clean" or fabricated defects from the lens text. The events log
# is the only reliable trace, so its sandbox-failure markers turn the run
# into a hard error. Skipped under an OUTER codex sandbox (CODEX_SANDBOX):
# there probe confinement is expected and the degraded diff-only render is
# the documented behavior (warned above).
if [ "$rc" -eq 0 ] && [ -z "${CODEX_SANDBOX:-}" ] && \
   grep -qE 'RTM_NEWADDR|shell is unavailable|fs sandbox helper failed' "$out.events.log" 2>/dev/null; then
  echo "review-engine: fs sandbox unavailable during run — findings in $out are untrustworthy (see $out.events.log); treat as ENGINE-UNAVAILABLE" >&2
  exit 3
fi
exit "$rc"
