#!/usr/bin/env bash
# Runs the devcloud plugin's mod tests. `claude plugin test <dir>` runs every
# *.test.ts under a plugin folder, and devcloud/ is one whose only TypeScript
# tests are these, so it takes the folder as it is. Then the Bash restoration
# rule, proved by execution under bash and zsh (shell-exec.ts, run by bun: it
# starts processes, which a kit test does not).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -I -m unittest discover -s "$root/tests/mods" -p 'provenance_index_test.py'
claude plugin test "$root"
for need in bun /bin/bash /bin/zsh; do
  command -v "$need" >/dev/null || { echo "devcloud tests need $need" >&2; exit 1; }
done
bun "$root/tests/mods/shell-exec.ts"
