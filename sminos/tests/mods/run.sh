#!/usr/bin/env bash
# Runs the sminos plugin's mod tests. `claude plugin test <dir>` runs every
# *.test.ts under a plugin folder, and sminos/ is one whose only TypeScript
# tests are these, so it takes the folder as it is. Then what the mods' tests
# cannot reach (a process, a file), beside them.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
claude plugin test "$root"
"$root/tests/mods/test-ask-search.sh"
