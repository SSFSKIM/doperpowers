#!/usr/bin/env bash
# SessionEnd hook: at a /clear the engine ends the session in this process
# and starts another in the same one, and by the new session's start nothing
# the engine offers names the session that was left; this payload does
# (reason `clear`, the old session's id). It is kept as
# $SMINOS_HOME/cleared/<the engine's pid>.json for the new session's own
# hooks (`cleared_from` in sminos.py), which move the session's alias to it.
# One write and a rename, and no Python: an ending session's hooks are given
# little time. Nothing for another reason, nor in an internal fork. Every
# path exits 0, printing nothing.
set -uo pipefail
[[ -n ${SMNS_INTERNAL:-} ]] && exit 0
pid=${CLAUDE_PID:-}
[[ $pid =~ ^[0-9]+$ ]] || exit 0

# `read` rather than `$(cat)`: one line of JSON holds no NUL, so this reads to the end.
IFS= read -r -d '' input
reason=${input#*\"reason\":}
[[ $reason != "$input" ]] || exit 0
reason=${reason#"${reason%%[![:space:]]*}"}
[[ $reason == '"clear"'* ]] || exit 0

home=${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}
[[ -d $home ]] || exit 0
dir=$home/cleared
mkdir -p "$dir" 2>/dev/null && chmod 700 "$dir" 2>/dev/null
tmp=$dir/.$pid.$$.tmp
(umask 077 && printf '%s' "$input" >"$tmp") 2>/dev/null && mv -f "$tmp" "$dir/$pid.json" 2>/dev/null
rm -f "$tmp" 2>/dev/null
exit 0
