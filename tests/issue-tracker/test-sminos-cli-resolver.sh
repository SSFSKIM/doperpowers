#!/usr/bin/env bash
#
# The board's one route to the sminos CLI (_sminos_cli.sh, sourced by _lib.sh
# and by the entrypoints that resolve before or without it): $SMINOS_CLI when
# set; else the CLI beside the checkout (or plugin copy) the board scripts live
# in; else the doperpowers marketplace clone's, read from
# known_marketplaces.json; else a death naming SMINOS_CLI. Each place is driven
# through a staged copy of the scripts under a temporary HOME, so nothing here
# reads the real ~/.claude.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"
RESOLVER="$SCRIPTS/_sminos_cli.sh"
REAL_CLI="$REPO_ROOT/sminos/skills/sminos/scripts/sminos"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_eq() {
    if [ "$2" = "$3" ]; then pass "$1"; else
        fail "$1"; echo "    expected: $2"; echo "    actual:   $3"; fi
}
assert_contains() {
    if grep -Fq -- "$2" <<<"$3"; then pass "$1"; else
        fail "$1"; echo "    expected to find: $2"; echo "    in: $3"; fi
}

[ -f "$RESOLVER" ] || { fail "the resolver exists at $RESOLVER"; echo "FAILED: $FAILURES"; exit 1; }

# A staged copy of the board scripts at <root>/skills/issue-tracker/scripts —
# the resolver's location is the only thing it derives the checkout from.
stage() {  # stage <root>
    mkdir -p "$1/skills/issue-tracker/scripts"
    cp "$RESOLVER" "$1/skills/issue-tracker/scripts/_sminos_cli.sh"
}
fake_cli() {  # fake_cli <dir> — an executable CLI with lib.sh beside it
    mkdir -p "$1"
    printf '#!/bin/sh\nexit 0\n' > "$1/sminos"; chmod +x "$1/sminos"
    : > "$1/lib.sh"
}
known() {  # known <home> <installLocation>
    mkdir -p "$1/.claude/plugins"
    printf '{"doperpowers": {"source": {"source": "github"}, "installLocation": "%s"}}\n' "$2" \
        > "$1/.claude/plugins/known_marketplaces.json"
}
# Resolve in a fresh shell: prints SMINOS_CLI as a child process sees it (the
# export is part of the contract), then sminos_lib's answer.
resolve() {  # resolve <root> <home> [SMINOS_CLI]
    env -u SMINOS_CLI HOME="$2" ${3:+SMINOS_CLI="$3"} bash -c '
        set -euo pipefail
        . "$1/skills/issue-tracker/scripts/_sminos_cli.sh"
        sminos_cli
        bash -c "printf \"%s\n\" \"\$SMINOS_CLI\""
        sminos_lib' _ "$1"
}

echo "1. \$SMINOS_CLI wins when set:"
R1="$TEST_ROOT/r1"; H1="$TEST_ROOT/h1"; stage "$R1"; mkdir -p "$H1"
fake_cli "$R1/sminos/skills/sminos/scripts"
fake_cli "$TEST_ROOT/env-cli"
out="$(resolve "$R1" "$H1" "$TEST_ROOT/env-cli/sminos")"
assert_eq "the env CLI is resolved and exported" "$TEST_ROOT/env-cli/sminos" "$(sed -n 1p <<<"$out")"
assert_eq "sminos_lib is lib.sh beside the env CLI" "$TEST_ROOT/env-cli/lib.sh" "$(sed -n 2p <<<"$out")"

echo "2. else the CLI beside the checkout the scripts live in:"
R2="$TEST_ROOT/r2"; H2="$TEST_ROOT/h2"; stage "$R2"
fake_cli "$R2/sminos/skills/sminos/scripts"
fake_cli "$TEST_ROOT/clone2/sminos/skills/sminos/scripts"
known "$H2" "$TEST_ROOT/clone2"
out="$(resolve "$R2" "$H2")"
assert_eq "the sibling CLI is resolved (ahead of the marketplace clone)" \
    "$R2/sminos/skills/sminos/scripts/sminos" "$(sed -n 1p <<<"$out")"
assert_eq "sminos_lib is lib.sh beside the sibling CLI" \
    "$R2/sminos/skills/sminos/scripts/lib.sh" "$(sed -n 2p <<<"$out")"

echo "3. else the doperpowers marketplace clone's CLI:"
R3="$TEST_ROOT/r3"; H3="$TEST_ROOT/h3"; stage "$R3"
fake_cli "$TEST_ROOT/clone3/sminos/skills/sminos/scripts"
known "$H3" "$TEST_ROOT/clone3"
out="$(resolve "$R3" "$H3")"
assert_eq "the marketplace clone's CLI is resolved when no sibling exists" \
    "$TEST_ROOT/clone3/sminos/skills/sminos/scripts/sminos" "$(sed -n 1p <<<"$out")"
assert_eq "sminos_lib is lib.sh beside the clone's CLI" \
    "$TEST_ROOT/clone3/sminos/skills/sminos/scripts/lib.sh" "$(sed -n 2p <<<"$out")"

echo "4. else it dies naming SMINOS_CLI:"
R4="$TEST_ROOT/r4"; H4="$TEST_ROOT/h4"; stage "$R4"; mkdir -p "$H4"
rc=0; err="$(resolve "$R4" "$H4" 2>&1 >/dev/null)" || rc=$?
[ "$rc" -ne 0 ] && pass "no CLI anywhere fails (rc=$rc)" || fail "no CLI anywhere fails"
assert_contains "the death names SMINOS_CLI" "SMINOS_CLI" "$err"
# A clone named in known_marketplaces.json without the CLI in it is not a hit.
known "$H4" "$TEST_ROOT/clone4-empty"; mkdir -p "$TEST_ROOT/clone4-empty"
rc=0; err="$(resolve "$R4" "$H4" 2>&1 >/dev/null)" || rc=$?
[ "$rc" -ne 0 ] && pass "a clone without the CLI fails too (rc=$rc)" || fail "a clone without the CLI fails too"
assert_contains "…naming SMINOS_CLI" "SMINOS_CLI" "$err"

echo "5. the checkout's own resolution:"
out="$(resolve "$REPO_ROOT" "$TEST_ROOT/h-empty")"
assert_eq "this checkout's board scripts resolve this checkout's CLI" "$REAL_CLI" "$(sed -n 1p <<<"$out")"
assert_eq "…and its lib.sh" "$(dirname "$REAL_CLI")/lib.sh" "$(sed -n 2p <<<"$out")"
[ -f "$(sed -n 2p <<<"$out")" ] && pass "lib.sh exists beside the checkout's CLI" || fail "lib.sh exists beside the checkout's CLI"

echo "6. every board file routes through the one resolver:"
# The CLI's old home (skills/sminos/scripts) holds a transition shim with no
# lib.sh; no board script or template may spell a path to it.
stale="$(cd "$REPO_ROOT" && grep -rn 'sminos/scripts' skills/issue-tracker/scripts skills/issue-tracker/references \
    | grep -v 'sminos/skills/sminos/scripts' || true)"
assert_eq "no board script or template spells the CLI's old path" "" "$stale"
for f in _lib.sh execute-dispatch.sh review-dispatch.sh board-sweep.sh _sweep_api.sh board-gc.sh; do
    if grep -Eq '^\. ".*/_sminos_cli\.sh"$' "$SCRIPTS/$f"; then
        pass "$f loads the resolver"; else fail "$f loads the resolver"; fi
done
if grep -Fq '. "$(sminos_lib)"' "$SCRIPTS/review-dispatch.sh"; then
    pass "review-dispatch sources lib.sh beside the resolved CLI"; else
    fail "review-dispatch sources lib.sh beside the resolved CLI"; fi

echo
if [ "$FAILURES" -eq 0 ]; then echo "ALL PASSED"; else echo "FAILED: $FAILURES"; exit 1; fi
