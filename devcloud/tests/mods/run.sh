#!/usr/bin/env bash
# Runs the devcloud plugin's mod tests. `claude plugin test <dir>` runs every
# *.test.ts under a plugin folder, and devcloud/ is one whose only TypeScript
# tests are these, so it takes the folder as it is.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
claude plugin test "$root"
