#!/usr/bin/env bash
# helpers.sh — board-api test scaffolding. Source from every test in this dir.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../../.." && pwd)"
# shellcheck disable=SC2034  # consumed by the tests that source this file
SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"
FAILS=0
t() {  # t <name> <expected-substring> cmd...
  local name="$1" want="$2"; shift 2 || { echo "t: bad call"; exit 2; }
  local out; out="$("$@" 2>&1)" || true
  if grep -qF -- "$want" <<<"$out"; then echo "ok   $name"
  else echo "FAIL $name — wanted '$want' in:"; sed 's/^/     /' <<<"$out"; FAILS=$((FAILS+1)); fi
}
mkrepo() {  # fresh throwaway git repo, prints its path
  local d; d="$(mktemp -d)"; git -C "$d" init -q; echo "$d"
}
finish() { [ "$FAILS" -eq 0 ] && echo "PASS $(basename "$0")" || { echo "FAIL $(basename "$0") ($FAILS)"; exit 1; }; }
