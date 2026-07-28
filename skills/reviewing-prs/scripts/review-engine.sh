#!/usr/bin/env bash
# review-engine.sh — the ONE review-engine invocation for the reviewing-prs
# loop. PURE correctness review: the native `codex exec review --base` runs
# with no ticket/spec input of any kind; the single optional modification is
# a diff-derived structural LENS (CODEX_REVIEW_LENS_FILE / CODEX_REVIEW_LENS,
# see the lens block below) delivered as developer_instructions. Ticket/spec
# compliance is the REVIEW WORKER's own audit, performed outside this engine
# (skills/reviewing-prs/SKILL.md). The script stays synchronous; the caller
# chooses foreground or background. The verdict lands in --out as a compact
# findings file; the PR diff never enters the caller's context.
#
# Usage: review-engine.sh --base <ref> --out <file>
#   --base  diff base (e.g. origin/main); the engine reviews <ref>...HEAD
#   --out   findings file the engine writes (event stream: <out>.events.jsonl)
# Env: CODEX_REVIEW_MODEL (default gpt-5.6-sol), CODEX_REVIEW_EFFORT
# (default xhigh), CODEX_REVIEW_LENS_FILE / CODEX_REVIEW_LENS (optional
# diff-derived structural focus mandate — see the lens block below; both
# empty keeps the plain review).
# Run from the worktree root — the engine reviews $PWD.
# Exits with codex's rc (127 codex missing, 2 usage error).
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
# symlinked so login state carries over. Removed on every exit path.
eng_home="$(mktemp -d "${TMPDIR:-/tmp}/review-engine-home.XXXXXX")"
trap 'rm -rf "$eng_home"' EXIT
if [ -f "$source_codex_home/auth.json" ]; then
  ln -s "$source_codex_home/auth.json" "$eng_home/auth.json"
fi
export CODEX_HOME="$eng_home"

# Nested only: macOS forbids applying a second Seatbelt profile
# (sandbox_apply), so a nested engine must be told to skip self-profiling —
# the OUTER workspace-write profile still confines it (children inherit).
# Non-nested the flag would be a real widening, so it is omitted.
sandbox_flags=()
if [ -n "${CODEX_SANDBOX:-}" ]; then
  sandbox_flags=( -c 'sandbox_mode="danger-full-access"' )
fi

# Optional lens: a diff-derived structural focus mandate delivered into the
# review thread as a developer message (the rubric's own override channel).
# Never ticket/spec content. CODEX_REVIEW_LENS_FILE (a path; read verbatim,
# so generated prose never passes through shell interpolation — the review
# worker MUST use this form) takes precedence over CODEX_REVIEW_LENS (inline,
# for trusted/manual invocations). Passed as a raw literal — codex falls back
# to the raw string when the value is not valid TOML, so plain prose needs no
# extra quoting. Both empty/unset = today's exact invocation.
lens=""
if [ -n "${CODEX_REVIEW_LENS_FILE:-}" ]; then
  [ -f "$CODEX_REVIEW_LENS_FILE" ] || { echo "review-engine: CODEX_REVIEW_LENS_FILE not found: $CODEX_REVIEW_LENS_FILE" >&2; exit 2; }
  lens="$(cat "$CODEX_REVIEW_LENS_FILE")"
elif [ -n "${CODEX_REVIEW_LENS:-}" ]; then
  lens="$CODEX_REVIEW_LENS"
fi
lens_flags=()
if [ -n "$lens" ]; then
  lens_flags=( -c "developer_instructions=$lens" )
fi

rc=0
codex exec review --base "$base" \
  -m "$model" -c "model_reasoning_effort=\"$effort\"" \
  -c 'features.hooks=false' \
  ${lens_flags[@]+"${lens_flags[@]}"} \
  ${sandbox_flags[@]+"${sandbox_flags[@]}"} \
  --json -o "$out" > "$out.events.jsonl" || rc=$?
exit "$rc"
