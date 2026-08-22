#!/usr/bin/env bash
#
# test-bump-version.sh — bump-version.sh bumps every declared manifest
# together, and a declared manifest that is missing or unreadable aborts
# the bump before anything is written (no partial bumps).
#
# BUMP_SCRIPT overrides the script under test (used to verify the test
# fails against a pre-preflight version of the script).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT_SOURCE="${BUMP_SCRIPT:-$REPO_ROOT/scripts/bump-version.sh}"
TEST_ROOT="$(mktemp -d)"

cleanup() {
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_fixture() {
  local repo="$1"
  local second_manifest="$2"

  mkdir -p "$repo/scripts" "$repo/.claude-plugin"
  cp "$SCRIPT_SOURCE" "$repo/scripts/bump-version.sh"
  cat >"$repo/.version-bump.json" <<'JSON'
{
  "files": [
    { "path": "package.json", "field": "version" },
    { "path": ".claude-plugin/plugin.json", "field": "version" }
  ],
  "audit": { "exclude": [] }
}
JSON
  cat >"$repo/package.json" <<'JSON'
{
  "name": "fixture",
  "version": "1.2.3"
}
JSON
  printf '%s\n' "$second_manifest" >"$repo/.claude-plugin/plugin.json"
}

# Happy path: every declared manifest bumps together.
happy_repo="$TEST_ROOT/happy"
make_fixture "$happy_repo" '{ "name": "fixture-plugin", "version": "1.2.3" }'

/bin/bash "$happy_repo/scripts/bump-version.sh" --check >"$TEST_ROOT/check.out"
/bin/bash "$happy_repo/scripts/bump-version.sh" 2.3.4 >"$TEST_ROOT/bump.out"

[[ "$(jq -r '.version' "$happy_repo/package.json")" == "2.3.4" ]] \
  || fail "package.json was not bumped"
[[ "$(jq -r '.version' "$happy_repo/.claude-plugin/plugin.json")" == "2.3.4" ]] \
  || fail "plugin.json was not bumped"

# Unreadable manifest: the bump must fail before writing ANY file.
invalid_repo="$TEST_ROOT/invalid"
make_fixture "$invalid_repo" '{ this is not json'
cp "$invalid_repo/package.json" "$TEST_ROOT/package.before"
cp "$invalid_repo/.claude-plugin/plugin.json" "$TEST_ROOT/plugin.before"

if /bin/bash "$invalid_repo/scripts/bump-version.sh" 2.3.4 \
  >"$TEST_ROOT/invalid.out" 2>&1; then
  fail "bump accepted an unreadable manifest"
fi

cmp -s "$TEST_ROOT/package.before" "$invalid_repo/package.json" \
  || fail "package.json changed before manifest validation failed"
cmp -s "$TEST_ROOT/plugin.before" "$invalid_repo/.claude-plugin/plugin.json" \
  || fail "unreadable manifest changed"

# Missing manifest: a declared file that does not exist must abort the bump
# too — a partial bump is still a broken bump.
missing_repo="$TEST_ROOT/missing"
make_fixture "$missing_repo" '{ "name": "fixture-plugin", "version": "1.2.3" }'
rm "$missing_repo/.claude-plugin/plugin.json"
cp "$missing_repo/package.json" "$TEST_ROOT/package.before-missing"

if /bin/bash "$missing_repo/scripts/bump-version.sh" 2.3.4 \
  >"$TEST_ROOT/missing.out" 2>&1; then
  fail "bump accepted a missing declared manifest"
fi

cmp -s "$TEST_ROOT/package.before-missing" "$missing_repo/package.json" \
  || fail "package.json changed despite a missing declared manifest"

echo "Version-bump tests passed"
