#!/usr/bin/env bash
# SessionStart hook (every source): the Task Board's start line
# (docs/doperpowers/plans/2026-11-27-task-board-b1.md, M1). Where this
# machine's store exists, `sminos task remind` prints the keys of the outcomes
# it names on its first line and the start line after it; the hook prints the
# start line, which the engine adds to the session's context, and only then
# marks exactly those keys shown with `sminos task shown` (with none too, which
# binds a /clear's pair to this session's thread). Printing first and marking
# second: a failure between the two names the same acts again at the next
# start. No store, no Python; a failure prints nothing more and never blocks a
# start: every path exits 0.
set -uo pipefail
[[ -n ${SMNS_INTERNAL:-} ]] && exit 0
home=${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}
[[ -e $home/tasks/state.json ]] || exit 0

IFS= read -r -d '' input
[[ -n $input ]] || exit 0
# The payload's session_id and source, read without Python: a session id is a UUID, a source a word.
sid=${input#*\"session_id\":}
[[ $sid != "$input" ]] || exit 0
sid=${sid#"${sid%%[![:space:]]*}"}
sid=${sid#\"}
sid=${sid%%\"*}
[[ $sid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 0
src=""
rest=${input#*\"source\":}
if [[ $rest != "$input" ]]; then
  rest=${rest#"${rest%%[![:space:]]*}"}
  rest=${rest#\"}
  src=${rest%%\"*}
  [[ $src =~ ^[a-z]{1,16}$ ]] || src=""
fi

root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
cli=$root/skills/sminos/scripts/sminos
out=$("$cli" task remind --session "$sid" --source "$src" 2>/dev/null) || exit 0
keys=${out%%$'\n'*}
[[ $out == *$'\n'* ]] && text=${out#*$'\n'} || text=""
[[ -n $text ]] && printf '%s\n' "$text"
"$cli" task shown --session "$sid" --keys "${keys// /,}" >/dev/null 2>&1
exit 0
