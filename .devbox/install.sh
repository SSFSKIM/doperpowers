#!/usr/bin/env bash
# devenv-inputs: application-agents/triaging-feedback/package.json application-agents/triaging-feedback/package-lock.json
#
# Makes a doperpowers checkout ready to work in: the triaging-feedback poller's dependencies, and a
# check that tests/mods can run. Idempotent — npm ci rebuilds node_modules from the lockfile on
# every run; devenv skips the whole script while the inputs above and the manifest are unchanged.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v npm >/dev/null || { echo "install: npm not found; install Node.js 22+ first" >&2; exit 1; }
echo "== application-agents/triaging-feedback: npm ci (node $(node --version))"
(cd application-agents/triaging-feedback && npm ci --no-audit --no-fund)

# tests/mods/run-mods-tests.sh stages its plugin folder in a fresh temp directory on every run, so
# nothing is staged here ahead of time; what it needs from the host is the claude CLI.
if command -v claude >/dev/null; then
  echo "== tests/mods: claude CLI at $(command -v claude)"
else
  echo "== tests/mods: claude CLI not on PATH; tests/mods/run-mods-tests.sh cannot run on this host"
fi
