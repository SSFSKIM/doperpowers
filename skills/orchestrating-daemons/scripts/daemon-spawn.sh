#!/usr/bin/env bash
# daemon-spawn.sh <name> <task> [cwd] [worktree] [model]
#
# Spawn a durable background daemon with `claude --bg` — an independent process,
# visible in `claude agents`, that survives this orchestrator ending. Runs its
# FIRST turn, waits for it to finish, and records the reply.
#
# NEVER RUN THIS IN THE FOREGROUND: it blocks while polling for the first turn
# to complete, prints the reply, then exits. Run it under a Monitor (the reply
# streams into context as an event — no read step) or a background shell (Bash
# run_in_background: true; Read the output file when it completes).
#
#   name       short display name (shown in `claude agents` and resume picker)
#   task       the initial prompt / task text
#   cwd        repo/dir the daemon runs in (default: $PWD). Recorded because
#              `claude --resume` is scoped to the cwd's project.
#   worktree   OPTIONAL worktree name. If set (and cwd is a git repo), the daemon
#              runs in an isolated worktree at <repo>/.claude/worktrees/<name> on
#              branch worktree-<name> — use for any daemon that WRITES code so
#              parallel daemons never clobber each other. Empty = run in cwd.
#   model      optional model alias/id (default: inherit)

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

name="${1:?usage: daemon-spawn.sh <name> <task> [cwd] [worktree] [model]}"
task="${2:?missing task}"
cwd="${3:-$PWD}"
worktree="${4:-}"
model="${5:-}"

# --bg manages the session id (it ignores --session-id), so we capture the short
# id it prints and resolve the full UUID from `claude agents`.
args=( --bg --permission-mode auto -n "$name" )
if [ -n "$worktree" ]; then
  wt="$(printf '%s' "$worktree" | tr -c 'a-zA-Z0-9._-' '-')"
  args+=( --worktree "$wt" )
fi
[ -n "$model" ] && args+=( --model "$model" )
args+=( "$task" )

banner="$(cd "$cwd" && claude "${args[@]}" </dev/null 2>&1 | _strip_ansi)"
short="$(printf '%s\n' "$banner" | sed -n 's/.*backgrounded · \([0-9a-f][0-9a-f]*\).*/\1/p' | head -1)"
[ -n "$short" ] || { echo "spawn failed — could not parse background id from:" >&2; echo "$banner" >&2; exit 1; }

# Wait for the first turn to finish; capture the UUID, state, and ACTUAL cwd
# (the worktree path when --worktree was used). Parse via parameter expansion,
# not `read` — the watcher's no-uuid timeout line leads with an empty field that
# word-splitting would collapse, promoting the state token into the uuid slot
# and registering corrupt meta. Same hardening as daemon-resume.
poll_rc=0
poll_out="$(_poll_until_done "$short" "$((DAEMON_TIMEOUT / 2))")" || poll_rc=$?
uuid="${poll_out%% *}"; rest="${poll_out#* }"
state="${rest%% *}"; runcwd="${rest#* }"
[ "$runcwd" = "$rest" ] && runcwd=""
case "$uuid" in
  *[!0-9a-f-]*) uuid="" ;;  # defensive: a jumbled poll line is not a session uuid
esac
[ -n "$uuid" ] || { echo "spawn: daemon $short produced no usable session uuid" >&2; exit 1; }
[ -n "$runcwd" ] || runcwd="$cwd"

# A watcher timeout on a live first turn is not a finished turn: record the
# truth (status=working) — daemon-reply reads the live transcript for it.
status="idle"; [ "$state" = "blocked" ] && status="blocked"; [ "$state" = "error" ] && status="error"
[ "$poll_rc" -ne 0 ] && status="working"
_record_reply "$uuid" "$uuid" "$state"
_meta_set "$uuid" \
  uuid "$uuid" current "$uuid" short "$short" name "$name" task "$task" cwd "$runcwd" \
  worktree "$worktree" model "$model" \
  status "$status" created "$(_now)" updated "$(_now)" turns "1"

wtnote=""; [ -n "$worktree" ] && wtnote="  worktree=$runcwd (branch worktree-$wt)"
echo "daemon spawned: $name  [$short / $uuid]  state=$state${wtnote}  (visible in 'claude agents')"
echo "--- reply ---"
_reply_text "$uuid"
