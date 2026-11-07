#!/usr/bin/env bash
#
# test-bump-version.sh — bump-version.sh bumps every manifest declared for
# one plugin together, never another plugin's, and a declared manifest that
# is missing or unreadable aborts the bump before anything is written (no
# partial bumps). A marketplace entry is addressed by the plugin's name, so
# reordering the marketplace never moves the wrong version. A version not
# above the current one is refused.
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

# A repo with two plugins: `fixture` at the root (package.json, its
# plugin.json, its marketplace entry) and `extra` in extra/ (its plugin.json,
# its marketplace entry). The marketplace lists a third plugin with no version
# between them, and `extra` before `fixture`.
make_fixture() {
  local repo="$1"
  local second_manifest="$2"

  mkdir -p "$repo/scripts" "$repo/.claude-plugin" "$repo/extra/.claude-plugin"
  cp "$SCRIPT_SOURCE" "$repo/scripts/bump-version.sh"
  cat >"$repo/.version-bump.json" <<'JSON'
{
  "plugins": [
    {
      "name": "fixture",
      "files": [
        { "path": "package.json", "field": "version" },
        { "path": ".claude-plugin/plugin.json", "field": "version" },
        { "path": ".claude-plugin/marketplace.json", "field": "plugins[name=fixture].version" }
      ],
      "unshipped": ["CLAUDE.md", "*/CLAUDE.md", "docs/*", ".claude-plugin/marketplace.json"],
      "audit": { "exclude": ["extra"] }
    },
    {
      "name": "extra",
      "root": "extra",
      "files": [
        { "path": "extra/.claude-plugin/plugin.json", "field": "version" },
        { "path": ".claude-plugin/marketplace.json", "field": "plugins[name=extra].version" }
      ],
      "unshipped": ["tests/*"],
      "audit": { "exclude": [] }
    }
  ]
}
JSON
  cat >"$repo/package.json" <<'JSON'
{
  "name": "fixture",
  "version": "1.2.3"
}
JSON
  printf '%s\n' "$second_manifest" >"$repo/.claude-plugin/plugin.json"
  printf '{ "name": "extra", "version": "0.1.0" }\n' >"$repo/extra/.claude-plugin/plugin.json"
  cat >"$repo/.claude-plugin/marketplace.json" <<'JSON'
{
  "name": "fixture-market",
  "plugins": [
    { "name": "extra", "version": "0.1.0", "source": "./extra" },
    { "name": "other", "source": { "source": "url", "url": "https://example.com/other.git" } },
    { "name": "fixture", "version": "1.2.3", "source": "./" }
  ]
}
JSON
}

market_version() {
  jq -r --arg name "$2" '.plugins[] | select(.name == $name) | .version' "$1/.claude-plugin/marketplace.json"
}

# Happy path: every manifest of the plugin bumps together, the default plugin
# being the first declared.
happy_repo="$TEST_ROOT/happy"
make_fixture "$happy_repo" '{ "name": "fixture-plugin", "version": "1.2.3" }'

/bin/bash "$happy_repo/scripts/bump-version.sh" --check >"$TEST_ROOT/check.out" \
  || fail "--check reported drift on a fixture in sync"
/bin/bash "$happy_repo/scripts/bump-version.sh" 2.3.4 >"$TEST_ROOT/bump.out"

[[ "$(jq -r '.version' "$happy_repo/package.json")" == "2.3.4" ]] \
  || fail "package.json was not bumped"
[[ "$(jq -r '.version' "$happy_repo/.claude-plugin/plugin.json")" == "2.3.4" ]] \
  || fail "plugin.json was not bumped"
[[ "$(market_version "$happy_repo" fixture)" == "2.3.4" ]] \
  || fail "the plugin's marketplace entry was not bumped"
[[ "$(market_version "$happy_repo" extra)" == "0.1.0" ]] \
  || fail "bumping one plugin moved another plugin's marketplace version"
[[ "$(jq -r '.version' "$happy_repo/extra/.claude-plugin/plugin.json")" == "0.1.0" ]] \
  || fail "bumping one plugin moved another plugin's manifest"
[[ "$(jq -c '.plugins[1]' "$happy_repo/.claude-plugin/marketplace.json")" == '{"name":"other","source":{"source":"url","url":"https://example.com/other.git"}}' ]] \
  || fail "a versionless marketplace entry was changed"

# --plugin: the second plugin bumps alone.
/bin/bash "$happy_repo/scripts/bump-version.sh" --plugin extra 0.2.0 >"$TEST_ROOT/extra.out"
[[ "$(jq -r '.version' "$happy_repo/extra/.claude-plugin/plugin.json")" == "0.2.0" ]] \
  || fail "--plugin extra did not bump extra's manifest"
[[ "$(market_version "$happy_repo" extra)" == "0.2.0" ]] \
  || fail "--plugin extra did not bump extra's marketplace entry"
[[ "$(market_version "$happy_repo" fixture)" == "2.3.4" && "$(jq -r '.version' "$happy_repo/package.json")" == "2.3.4" ]] \
  || fail "--plugin extra moved the other plugin's version"
/bin/bash "$happy_repo/scripts/bump-version.sh" --check >"$TEST_ROOT/check2.out" \
  || fail "--check reported drift after bumping each plugin on its own"

# An unknown plugin is refused, nothing written.
cp "$happy_repo/.claude-plugin/marketplace.json" "$TEST_ROOT/market.before"
if /bin/bash "$happy_repo/scripts/bump-version.sh" --plugin nope 9.9.9 >"$TEST_ROOT/nope.out" 2>&1; then
  fail "bump accepted an unknown plugin"
fi
cmp -s "$TEST_ROOT/market.before" "$happy_repo/.claude-plugin/marketplace.json" \
  || fail "an unknown plugin's bump changed the marketplace"

# A version not above the current one is refused, nothing written: the
# marketplace updates by number alone, so a lower or equal number never
# installs. Compared numerically (2.3.10 is above 2.3.4).
for stale in 2.3.3 2.3.4 1.9.99; do
  if /bin/bash "$happy_repo/scripts/bump-version.sh" "$stale" >"$TEST_ROOT/stale.out" 2>&1; then
    fail "bump accepted $stale over 2.3.4"
  fi
  [[ "$(jq -r '.version' "$happy_repo/package.json")" == "2.3.4" && "$(market_version "$happy_repo" fixture)" == "2.3.4" ]] \
    || fail "a refused bump to $stale changed a manifest"
done
/bin/bash "$happy_repo/scripts/bump-version.sh" 2.3.10 >"$TEST_ROOT/numeric.out" \
  || fail "bump refused 2.3.10 over 2.3.4"
[[ "$(jq -r '.version' "$happy_repo/package.json")" == "2.3.10" ]] \
  || fail "2.3.10 was not written"

# Drift: the bump must be above the highest declared version, not just the
# first file's.
drift_repo="$TEST_ROOT/drift"
make_fixture "$drift_repo" '{ "name": "fixture-plugin", "version": "1.5.0" }'
if /bin/bash "$drift_repo/scripts/bump-version.sh" 1.3.0 >"$TEST_ROOT/drift.out" 2>&1; then
  fail "bump accepted 1.3.0 under a manifest at 1.5.0"
fi
[[ "$(jq -r '.version' "$drift_repo/package.json")" == "1.2.3" ]] \
  || fail "a refused drift bump changed package.json"

# A marketplace entry the plugin's name does not find: the bump must fail
# before writing ANY file.
unlisted_repo="$TEST_ROOT/unlisted"
make_fixture "$unlisted_repo" '{ "name": "fixture-plugin", "version": "1.2.3" }'
jq '.plugins |= map(select(.name != "extra"))' "$unlisted_repo/.claude-plugin/marketplace.json" >"$TEST_ROOT/m.json"
mv "$TEST_ROOT/m.json" "$unlisted_repo/.claude-plugin/marketplace.json"
cp "$unlisted_repo/extra/.claude-plugin/plugin.json" "$TEST_ROOT/extra.before"
if /bin/bash "$unlisted_repo/scripts/bump-version.sh" --plugin extra 0.3.0 >"$TEST_ROOT/unlisted.out" 2>&1; then
  fail "bump accepted a marketplace that does not list the plugin"
fi
cmp -s "$TEST_ROOT/extra.before" "$unlisted_repo/extra/.claude-plugin/plugin.json" \
  || fail "extra's manifest changed before the marketplace check failed"

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

# --since BASE [HEAD]: a plugin whose shipped files changed since BASE must
# carry a version above BASE's at HEAD (the working tree when HEAD is absent).
# A path belongs to the innermost plugin root above it; a path matching that
# plugin's unshipped globs needs no bump.
commit_all() {
  git -C "$1" add -A
  git -C "$1" -c user.name=t -c user.email=t@example.com commit -qm "$2"
}
since() {
  local repo="$1"
  shift
  /bin/bash "$repo/scripts/bump-version.sh" --since "$@" >"$TEST_ROOT/since.out" 2>&1
}
since_fails_naming() {
  local repo="$1" plugin="$2" why="$3"
  shift 3
  if since "$repo" "$@"; then
    fail "--since passed $why"
  fi
  grep -q "^  $plugin .*NOT BUMPED" "$TEST_ROOT/since.out" \
    || fail "--since did not name $plugin as not bumped ($why): $(cat "$TEST_ROOT/since.out")"
}

since_repo="$TEST_ROOT/since"
make_fixture "$since_repo" '{ "name": "fixture-plugin", "version": "1.2.3" }'
mkdir -p "$since_repo/skills" "$since_repo/extra/hooks" "$since_repo/extra/tests"
echo one >"$since_repo/skills/SKILL.md"
echo one >"$since_repo/extra/hooks/hook.sh"
git -C "$since_repo" init -q
commit_all "$since_repo" base
base=$(git -C "$since_repo" rev-parse HEAD)

# Only unshipped paths: no plugin needs a bump. `*` crosses directories, and
# the root plugin's `docs/*` reaches nothing of the nested plugin's.
mkdir -p "$since_repo/docs/deep/er" "$since_repo/skills/x"
echo doc >"$since_repo/docs/deep/er/note.md"
echo doc >"$since_repo/skills/x/CLAUDE.md"
echo t >"$since_repo/extra/tests/t.sh"
commit_all "$since_repo" docs
since "$since_repo" "$base" HEAD || fail "--since failed on unshipped changes only: $(cat "$TEST_ROOT/since.out")"
grep -q "(none)" "$TEST_ROOT/since.out" || fail "--since named a plugin for unshipped changes: $(cat "$TEST_ROOT/since.out")"

# A shipped change without a bump fails, naming that plugin and not the other.
echo two >"$since_repo/skills/SKILL.md"
commit_all "$since_repo" skill
since_fails_naming "$since_repo" fixture "a root plugin's skill change without a bump" "$base" HEAD
! grep -q "^  extra " "$TEST_ROOT/since.out" || fail "--since named extra for the root plugin's change"
# Given HEAD, the change is HEAD's, whatever the working tree holds.
echo one >"$since_repo/skills/SKILL.md"
since_fails_naming "$since_repo" fixture "HEAD's change, the working tree having undone it" "$base" HEAD
git -C "$since_repo" checkout -q -- .

# The nested plugin owns its tree: its change is its own, not the root's.
nested_base=$(git -C "$since_repo" rev-parse HEAD)
echo two >"$since_repo/extra/hooks/hook.sh"
commit_all "$since_repo" hook
since_fails_naming "$since_repo" extra "a nested plugin's change without a bump" "$nested_base" HEAD
! grep -q "^  fixture " "$TEST_ROOT/since.out" || fail "--since gave the nested plugin's change to the root plugin"

# The working tree is the default HEAD: an uncommitted bump of both passes.
/bin/bash "$since_repo/scripts/bump-version.sh" 1.3.0 >/dev/null
/bin/bash "$since_repo/scripts/bump-version.sh" --plugin extra 0.2.0 >/dev/null
since "$since_repo" "$base" || fail "--since failed after both plugins were bumped: $(cat "$TEST_ROOT/since.out")"
grep -q "^  fixture .*1.2.3 -> 1.3.0" "$TEST_ROOT/since.out" || fail "--since did not report fixture's bump: $(cat "$TEST_ROOT/since.out")"
grep -q "^  extra .*0.1.0 -> 0.2.0" "$TEST_ROOT/since.out" || fail "--since did not report extra's bump: $(cat "$TEST_ROOT/since.out")"
since "$since_repo" "$base" HEAD && fail "--since read the working tree when given HEAD"

# A partial bump (one declared file left behind) fails, as does a lower version.
commit_all "$since_repo" bumped
jq '.version = "1.2.3"' "$since_repo/.claude-plugin/plugin.json" >"$TEST_ROOT/p.json"
mv "$TEST_ROOT/p.json" "$since_repo/.claude-plugin/plugin.json"
since_fails_naming "$since_repo" fixture "a bump that left plugin.json at the base's version" "$base"
jq '.version = "1.2.2"' "$since_repo/package.json" >"$TEST_ROOT/p.json"
mv "$TEST_ROOT/p.json" "$since_repo/package.json"
since_fails_naming "$since_repo" fixture "a version below the base's" "$base"
git -C "$since_repo" checkout -q -- .

# In the working tree, an untracked file is part of the change.
echo new >"$since_repo/extra/hooks/new.sh"
since_fails_naming "$since_repo" extra "an untracked shipped file in the working tree" "$(git -C "$since_repo" rev-parse HEAD)"
rm "$since_repo/extra/hooks/new.sh"

# --plugin limits the check to that plugin.
echo three >"$since_repo/skills/SKILL.md"
since "$since_repo" "$(git -C "$since_repo" rev-parse HEAD)" --plugin extra \
  || fail "--since --plugin extra failed on the root plugin's change: $(cat "$TEST_ROOT/since.out")"
git -C "$since_repo" checkout -q -- .

# A plugin absent at the base is new: nothing to compare its version with.
new_repo="$TEST_ROOT/since-new"
make_fixture "$new_repo" '{ "name": "fixture-plugin", "version": "1.2.3" }'
mv "$new_repo/extra" "$TEST_ROOT/extra-later"
jq '.plugins |= map(select(.name != "extra"))' "$new_repo/.claude-plugin/marketplace.json" >"$TEST_ROOT/m.json"
cp "$TEST_ROOT/m.json" "$new_repo/.claude-plugin/marketplace.json"
git -C "$new_repo" init -q
commit_all "$new_repo" base
new_base=$(git -C "$new_repo" rev-parse HEAD)
git -C "$new_repo" checkout -q HEAD -- .
mv "$TEST_ROOT/extra-later" "$new_repo/extra"
jq '.plugins += [{ "name": "extra", "version": "0.1.0", "source": "./extra" }]' "$TEST_ROOT/m.json" \
  >"$new_repo/.claude-plugin/marketplace.json"
commit_all "$new_repo" add-extra
since "$new_repo" "$new_base" HEAD || fail "--since failed on a plugin new since the base: $(cat "$TEST_ROOT/since.out")"
grep -q "^  extra .*new since" "$TEST_ROOT/since.out" || fail "--since did not call extra new: $(cat "$TEST_ROOT/since.out")"

# A base that is not a commit is an error, not a pass.
since "$since_repo" no-such-rev && fail "--since accepted a base that is not a commit"

echo "Version-bump tests passed"
