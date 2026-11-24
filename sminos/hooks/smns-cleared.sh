#!/usr/bin/env bash
# SessionEnd hook: at a /clear the engine ends the session in this process
# and starts another in the same one, and by the new session's start nothing
# the engine offers names the session that was left; this payload does
# (reason `clear`, the old session's id). It is kept as
# $SMINOS_HOME/cleared/<the engine's pid>.json for the new session's own
# hooks (`cleared_from` in sminos.py), which move the session's alias to it,
# and for the daemon's question sheet sweep (`<pid>.sheet` beside it). A write
# and a rename each, and no Python: an ending session's hooks are given
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
# The question sheet the session left, as it is now: its record directory's
# device, inode and nonce (`.incarnation` in it, minted here if no reader has
# yet: a no-clobber link, so a concurrent minter's wins; sminos_sheet's
# record_identity), `<pid>.sheet`, written before the note. What the note
# witnessed, so the daemon's sweep removes that record and never one made
# after it. None when there is no record; a stale one is removed.
sid=${input#*\"session_id\":}
sid=${sid#"${sid%%[![:space:]]*}"}
sid=${sid#\"}
sid=${sid%%\"*}
rec=$home/sheet/$sid
rm -f "$dir/$pid.sheet" 2>/dev/null
if [[ $sid =~ ^[0-9a-fA-F-]+$ && -d $rec && ! -L $rec ]]; then
  if [[ ! -e $rec/.incarnation ]]; then
    mint=$rec/.tmp-cleared-$pid-$$
    (umask 077 && od -An -N16 -tx1 /dev/urandom | tr -d ' \n' >"$mint" && echo >>"$mint") 2>/dev/null \
      && ln "$mint" "$rec/.incarnation" 2>/dev/null
    rm -f "$mint" 2>/dev/null
  fi
  nonce=$(cat "$rec/.incarnation" 2>/dev/null)
  id=$(stat -c '%d:%i' "$rec" 2>/dev/null || stat -f '%d:%i' "$rec" 2>/dev/null) \
    && [[ $id =~ ^[0-9]+:[0-9]+$ && $nonce =~ ^[0-9a-f]{32}$ ]] \
    && (umask 077 && printf '%s:%s\n' "$id" "$nonce" >"$tmp") 2>/dev/null && mv -f "$tmp" "$dir/$pid.sheet" 2>/dev/null
fi
(umask 077 && printf '%s' "$input" >"$tmp") 2>/dev/null && mv -f "$tmp" "$dir/$pid.json" 2>/dev/null
rm -f "$tmp" 2>/dev/null
exit 0
