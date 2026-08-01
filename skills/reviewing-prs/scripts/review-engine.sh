#!/usr/bin/env bash
# review-engine.sh — the ONE review-engine invocation for the reviewing-prs
# loop, driven by the doperpowers:codex-companion runtime (vendored codex
# app-server client; sibling skill). PURE correctness review: a plain run is
# codex's native `review` verb with no ticket/spec input of any kind; the
# single optional modification is a diff-derived structural LENS
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
# empty keeps the plain review).
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
companion="$script_dir/../../codex-companion"
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

# with-effort.mjs serves the verb a private app-server carrying the effort
# override (the review protocol has no effort field) and provides its own
# live endpoint — no detached broker, nothing outlives this run. Findings
# render on stdout (--out), progress on stderr (<out>.events.log).
rc=0
node "$companion/scripts/with-effort.mjs" --effort "$effort" -- \
  "${verb_args[@]}" > "$out" 2> "$out.events.log" || rc=$?
exit "$rc"
