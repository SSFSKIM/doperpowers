#!/usr/bin/env bash
# Test runner for the codex-companion workflow engine — every test here drives the
# transport-faithful mock `codex` app-server in tests/codex-companion/mock/.
set -euo pipefail
cd "$(dirname "$0")"
shopt -s nullglob
fail=0
for t in test-*.mjs; do
  echo "== node $t"
  node "$t" || { echo "FAIL: $t"; fail=1; }
done
for t in test-*.sh; do
  echo "== bash $t"
  bash "$t" || { echo "FAIL: $t"; fail=1; }
done
[ "$fail" -eq 0 ] && echo "all workflow tests passed"
exit "$fail"
