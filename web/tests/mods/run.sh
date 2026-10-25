#!/usr/bin/env bash
# Runs the web plugin's mod tests. `claude plugin test <dir>` runs every
# *.test.ts under a plugin folder, and web/ also holds the clipper's own
# tests (node --test) and its node_modules, so the plugin's manifest, hooks
# and these tests are staged as a copy in a folder of their own (the runner
# refuses symlinks as path traversal).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

mkdir -p "$stage/tests"
cp -R "$root/.claude-plugin" "$stage/.claude-plugin"
rm -rf "$stage/.claude-plugin/types"
cp -R "$root/hooks" "$stage/hooks"
cp -R "$root/tests/mods" "$stage/tests/mods"

claude plugin test "$stage"
