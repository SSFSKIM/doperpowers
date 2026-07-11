#!/usr/bin/env bash
# review-engine.sh — the ONE review-engine invocation for the reviewing-prs
# loop (spec: docs/doperpowers/specs/2026-07-12-native-review-recovery-design.md).
#
# Runs the native `codex exec review --base` with custom criteria riding
# `-c developer_instructions=` (a CONFIG value — the positional [PROMPT]
# hard-conflicts with --base at the CLI parser, so criteria can never be
# the prompt). Both worker species call this same script: a codex worker
# NESTED inside its own seatbelt, a claude worker on the host. The verdict
# lands in --out as a compact findings file; the PR diff never enters the
# caller's context.
#
# Usage: review-engine.sh --base <ref> --criteria <file> --out <file>
#   --base      diff base (e.g. origin/main); the engine reviews <ref>...HEAD
#   --criteria  file carrying correctness discipline + ticket acceptance
#   --out       findings file the engine writes (event stream: <out>.events.jsonl)
# Env: CODEX_REVIEW_MODEL (default gpt-5.6-sol), CODEX_REVIEW_EFFORT
# (default xhigh). Run from the worktree root — the engine reviews $PWD.
# Exits with codex's rc (127 codex missing, 2 usage error).
set -euo pipefail

usage() { echo "usage: review-engine.sh --base <ref> --criteria <file> --out <file>" >&2; exit 2; }
base="" criteria="" out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base)     base="${2:-}"; shift 2 ;;
    --criteria) criteria="${2:-}"; shift 2 ;;
    --out)      out="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$base" ] && [ -n "$criteria" ] && [ -n "$out" ] || usage
[ -f "$criteria" ] || { echo "review-engine: criteria file missing: $criteria" >&2; exit 2; }
command -v codex >/dev/null 2>&1 || { echo "review-engine: codex CLI not found" >&2; exit 127; }

model="${CODEX_REVIEW_MODEL:-gpt-5.6-sol}"
effort="${CODEX_REVIEW_EFFORT:-xhigh}"

# TLS trust anchors as a FILE bundle — a nested codex cannot reach the OS
# keychain/trustd under the outer seatbelt (shakedown FU-6).
if [ -z "${SSL_CERT_FILE:-}" ] && [ -f /etc/ssl/cert.pem ]; then
  export SSL_CERT_FILE=/etc/ssl/cert.pem
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
if [ -f "$HOME/.codex/auth.json" ]; then
  ln -s "$HOME/.codex/auth.json" "$eng_home/auth.json"
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

rc=0
codex exec review --base "$base" \
  -m "$model" -c "model_reasoning_effort=\"$effort\"" \
  -c 'features.hooks=false' \
  ${sandbox_flags[@]+"${sandbox_flags[@]}"} \
  -c "developer_instructions=$(cat "$criteria")" \
  --json -o "$out" > "$out.events.jsonl" || rc=$?
exit "$rc"
