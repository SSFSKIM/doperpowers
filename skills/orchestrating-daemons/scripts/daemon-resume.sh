#!/usr/bin/env bash
# daemon-resume.sh <short-or-full-uuid> <message>
#
# Send a follow-up to a daemon and run one more turn IN PLACE (same id, full
# context). A live `--bg` daemon holds an ownership lock, so this first runs
# `claude stop` (idempotent — harmless if already released) to hand the session
# off to a foreground `-p --resume`. Same session id, no fork; the session stays
# in `claude agents --all` history and resumable by the human.
#
# LAUNCH THIS IN A BACKGROUND SHELL (Bash run_in_background: true) so the blocking
# turn doesn't tie up the orchestrator — the shell's exit re-invokes you with the
# reply. Resume is scoped to the daemon's cwd, which this script restores.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-resume.sh <uuid> <message>}")"
msg="${2:?missing message}"

cwd="$(_meta_get "$uuid" cwd)"; model="$(_meta_get "$uuid" model)"
short="$(_meta_get "$uuid" short)"
turns="$(_meta_get "$uuid" turns)"; [ -n "$turns" ] || turns=0

# Release the bg ownership lock so -p --resume can continue in place.
[ -n "$short" ] && claude stop "$short" >/dev/null 2>&1 || true

_meta_set "$uuid" status "working" updated "$(_now)"

args=( -p --resume "$uuid" --permission-mode auto --output-format text )
[ -n "$model" ] && args+=( --model "$model" )
args+=( "$msg" )

reply="$(_reply_path "$uuid")"; err="$(_err_path "$uuid")"
rc=0
( cd "$cwd" && _timeout "$DAEMON_TIMEOUT" claude "${args[@]}" </dev/null ) >"$reply" 2>"$err" || rc=$?

if [ "$rc" -eq 0 ] && [ -s "$reply" ]; then
  _meta_set "$uuid" status "idle" updated "$(_now)" turns "$((turns + 1))"
else
  _meta_set "$uuid" status "error" updated "$(_now)" exit_code "$rc"
fi

echo "daemon resumed: $(_meta_get "$uuid" name)  [$short / $uuid]  status=$(_meta_get "$uuid" status)  turns=$(_meta_get "$uuid" turns)"
echo "--- reply ---"
_reply_text "$uuid"
