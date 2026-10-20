#!/usr/bin/env bash
# Runs the to-human plugin's mod tests. `claude plugin test <dir>` runs every
# *.test.ts under a plugin folder, and to-human/ is one whose only TypeScript
# tests are these, so it takes the folder as it is. Then the transcript search
# a module that starts mid-session runs, proved by execution (session-places.ts,
# run by bun: it starts processes, which a kit test does not).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
claude plugin test "$root"
command -v bun >/dev/null || { echo "to-human tests need bun" >&2; exit 1; }
bun "$root/tests/mods/session-places.ts"
