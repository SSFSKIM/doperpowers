#!/usr/bin/env bash
# experimental-context — UserPromptExpansion hook, matched on the experimental-context command. The
# harness expands a plugin skill under its qualified name
# (`doperpowers:experimental-context`) and the matcher is a whole-string match, so hooks.json
# names both forms. When the human types /experimental-context, the skill body enters this
# turn on its own; this hook records the mode so experimental-context.sh re-injects the body
# and the session's live <revisit> entries after every compaction and on
# resume. `/experimental-context off` removes the record. The flag is one empty file named
# by the session id under ~/.claude/experimental-context (see kairos.sh for why a file).
set -euo pipefail

CONTEXT_DIR="${CONTEXT_DIR:-$HOME/.claude/experimental-context}"

input="$(cat)"
read -r sid args < <(python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("session_id") or "-", (d.get("command_args") or "").strip())' <<<"$input" 2>/dev/null || echo "-")
[ "$sid" != "-" ] || exit 0

case "${args:-}" in
  off|stop|end)
    rm -f "$CONTEXT_DIR/$sid"
    ;;
  *)
    # The mode is only for the deepest directory; its parent is ~/.claude.
    # shellcheck disable=SC2174
    mkdir -p -m 700 "$CONTEXT_DIR"
    : > "$CONTEXT_DIR/$sid"
    ;;
esac
