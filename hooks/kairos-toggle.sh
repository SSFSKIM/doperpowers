#!/usr/bin/env bash
# kairos — UserPromptExpansion hook, matched on the `kairos` command. When the
# human types /kairos, the skill body enters this turn on its own; this hook
# records the mode so kairos.sh re-injects it after every compaction and on
# resume. `/kairos off` removes the record. The flag is one empty file named
# by the session id under ~/.claude/kairos (see kairos.sh for why a file).
set -euo pipefail

KAIROS_DIR="${KAIROS_DIR:-$HOME/.claude/kairos}"

input="$(cat)"
read -r sid args < <(python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("session_id") or "-", (d.get("command_args") or "").strip())' <<<"$input" 2>/dev/null || echo "-")
[ "$sid" != "-" ] || exit 0

case "${args:-}" in
  off|stop|end)
    rm -f "$KAIROS_DIR/$sid"
    ;;
  *)
    # The mode is only for the deepest directory; its parent is ~/.claude.
    # shellcheck disable=SC2174
    mkdir -p -m 700 "$KAIROS_DIR"
    : > "$KAIROS_DIR/$sid"
    ;;
esac
