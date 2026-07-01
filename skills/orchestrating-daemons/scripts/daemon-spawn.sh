#!/usr/bin/env bash
# daemon-spawn.sh <name> <task> [cwd] [model]
#
# Spawn a durable background daemon with `claude --bg` — an independent process,
# visible in `claude agents`, that survives this orchestrator ending. Runs its
# FIRST turn, waits for it to finish, and records the reply.
#
# LAUNCH THIS IN A BACKGROUND SHELL (Bash run_in_background: true): it blocks
# while polling for the first turn to complete, then exits — the shell's exit
# re-invokes you with the reply preview.
#
#   name   short display name (shown in `claude agents` and the resume picker)
#   task   the initial prompt / task text
#   cwd    working dir the daemon runs in (default: $PWD). Recorded because
#          `claude --resume` is scoped to the cwd's project.
#   model  optional model alias/id (default: inherit)

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

name="${1:?usage: daemon-spawn.sh <name> <task> [cwd] [model]}"
task="${2:?missing task}"
cwd="${3:-$PWD}"
model="${4:-}"

# --bg manages the session id (it ignores --session-id), so we capture the short
# id it prints and resolve the full UUID from `claude agents`.
args=( --bg --permission-mode auto -n "$name" )
[ -n "$model" ] && args+=( --model "$model" )
args+=( "$task" )

banner="$(cd "$cwd" && claude "${args[@]}" </dev/null 2>&1 | _strip_ansi)"
short="$(printf '%s\n' "$banner" | sed -n 's/.*backgrounded · \([0-9a-f][0-9a-f]*\).*/\1/p' | head -1)"
[ -n "$short" ] || { echo "spawn failed — could not parse background id from:" >&2; echo "$banner" >&2; exit 1; }

# Wait for the first turn to finish, then resolve the UUID + terminal state.
read -r uuid state < <(_poll_until_done "$short" "$((DAEMON_TIMEOUT / 2))") || true
[ -n "$uuid" ] || { echo "spawn: daemon $short never appeared in 'claude agents'" >&2; exit 1; }

status="idle"; [ "$state" = "blocked" ] && status="blocked"; [ "$state" = "error" ] && status="error"
_transcript_reply "$uuid" "$cwd" > "$(_reply_path "$uuid")"
_meta_set "$uuid" \
  uuid "$uuid" short "$short" name "$name" task "$task" cwd "$cwd" model "$model" \
  status "$status" created "$(_now)" updated "$(_now)" turns "1"

echo "daemon spawned: $name  [$short / $uuid]  cwd=$cwd  state=$state  (visible in 'claude agents')"
echo "--- reply ---"
_reply_text "$uuid"
