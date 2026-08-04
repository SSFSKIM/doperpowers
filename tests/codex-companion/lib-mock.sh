#!/usr/bin/env bash
# Shared mock env for codex-companion workflow tests.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../.." && pwd)"
# Exported for the sourcing test and for anything it shells out to.
export RUNTIME="$REPO_ROOT/skills/codex-companion/runtime/scripts/codex-companion.mjs"
mock_env() { # $1 = scratch dir
  local scratch="$1"
  mkdir -p "$scratch/mockstate" "$scratch/data"
  export CODEX_MOCK_DIR="$scratch/mockstate"
  export PATH="$TESTS_DIR/mock:$PATH"
  export CLAUDE_PLUGIN_DATA="$scratch/data"
  export CODEX_COMPANION_SESSION_ID="wf-test"
  unset CODEX_COMPANION_APP_SERVER_ENDPOINT || true
}
