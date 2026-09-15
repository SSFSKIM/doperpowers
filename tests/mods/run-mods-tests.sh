#!/usr/bin/env bash
# Runs the function-hook mods' tests. `claude plugin test <dir>` takes a
# plugin folder and runs every *.test.ts under it, which at the repo root
# would sweep in the TypeScript tests of application-agents/; so the mods
# and their tests are staged as a copy in a plugin folder of their own
# (the runner refuses symlinks as path traversal).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

mkdir -p "$stage/.claude-plugin" "$stage/hooks" "$stage/tests"
printf '{ "name": "doperpowers-mods", "version": "0.0.0" }\n' > "$stage/.claude-plugin/plugin.json"
printf '{ "modules": ["./mods/register.tsx"] }\n' > "$stage/hooks/hooks.json"
cp -R "$root/hooks/mods" "$stage/hooks/mods"
cp -R "$root/tests/mods" "$stage/tests/mods"

claude plugin test "$stage"
