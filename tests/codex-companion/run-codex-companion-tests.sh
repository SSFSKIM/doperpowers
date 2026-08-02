#!/usr/bin/env bash
# Test runner for the vendored codex-companion runtime (skills/codex-companion/runtime).
# Runs the upstream node:test suite (adapted import paths) against a fake codex fixture —
# no real Codex install or auth is needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# The suite's companion invocations spawn detached broker + codex app-server pairs in temp
# workspaces (upstream relies on a SessionEnd hook to reap them); kill anything serving a
# codex-plugin-test-* workspace on the way out.
cleanup() { pkill -f 'codex-plugin-test-' 2>/dev/null || true; }
trap cleanup EXIT

# Sessions with a codex plugin installed leak CLAUDE_PLUGIN_DATA / CODEX_COMPANION_* into the
# environment via its SessionStart hook; the suite asserts tmpdir-fallback behavior, so run clean.
env -u CLAUDE_PLUGIN_DATA -u CODEX_COMPANION_SESSION_ID -u CODEX_COMPANION_TRANSCRIPT_PATH \
  node --test ./*.test.mjs
