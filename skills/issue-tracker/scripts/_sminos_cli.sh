#!/usr/bin/env bash
# _sminos_cli.sh — the board's one route to the sminos CLI. Sourced by _lib.sh
# and, directly, by the entrypoints that need the CLI before they could source
# _lib.sh (the dispatchers and the sweep resolve it ahead of their cd into the
# consumer repo, where _lib.sh would die "not inside a git repo") or that never
# source it (board-gc). Defines functions only; nothing runs at source time.
#
# sminos_cli resolves, in order:
#   1. $SMINOS_CLI when set;
#   2. the CLI beside the repository these scripts live in — a checkout, or the
#      doperpowers plugin copy, which carries the whole repository;
#   3. the doperpowers marketplace clone's (known_marketplaces.json's
#      installLocation) — the path the sminos daemon runs;
# and exports the answer as SMINOS_CLI, or dies naming it.

sminos_cli() {
  if [ -z "${SMINOS_CLI:-}" ]; then
    local root rel="sminos/skills/sminos/scripts/sminos" clone="" cli
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
    cli="$root/$rel"
    if [ ! -x "$cli" ]; then
      clone="$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(str(((d or {}).get("doperpowers") or {}).get("installLocation") or ""))
except (OSError, ValueError, AttributeError):
    pass
' "$HOME/.claude/plugins/known_marketplaces.json" 2>/dev/null || true)"
      if [ -n "$clone" ] && [ -x "$clone/$rel" ]; then
        cli="$clone/$rel"
      else
        echo "error: no sminos CLI found — not beside these board scripts ($root/$rel), nor in the doperpowers marketplace clone (${clone:-none in $HOME/.claude/plugins/known_marketplaces.json}); set SMINOS_CLI" >&2
        exit 1
      fi
    fi
    SMINOS_CLI="$cli"
  fi
  export SMINOS_CLI
}

# lib.sh, the sourced half of sminos, is the one beside the resolved CLI.
sminos_lib() {
  sminos_cli
  printf '%s/lib.sh\n' "$(dirname "$SMINOS_CLI")"
}
