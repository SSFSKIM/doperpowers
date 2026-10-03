#!/usr/bin/env bash
# doperpowers' automated checks for `devenv validate doperpowers`: the hermetic suites that need
# no model calls (shell lint of changed scripts, sminos, the feedback poller). The checks that
# drive the real claude CLI are in .devbox/skill/validation.md.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s\n' "$*"; }

if command -v shellcheck >/dev/null; then
  step "shell lint (changed scripts)"
  scripts/lint-shell.sh
else
  step "shell lint skipped: shellcheck is not installed"
fi

step "sminos"
tests/sminos/run-sminos-tests.sh

step "feedback poller"
(cd application-agents/triaging-feedback && npm test --silent)
