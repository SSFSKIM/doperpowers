#!/usr/bin/env bash
# codex-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model] [effort]
#
# Spawn a durable background CODEX worker (`codex exec --json`, detached) — the
# codex sibling of daemon-spawn.sh, writing the SAME registry so board-bind /
# board-reconcile / daemon-list work unchanged. Runs the FIRST turn, waits for
# it, and records the reply. NEVER RUN IN THE FOREGROUND (same contract as
# daemon-spawn.sh): use a Monitor or a background shell.
#
#   name       display name (registry)
#   task       initial prompt (delivered via stdin — no ARG_MAX limit on codex)
#   cwd        repo/dir the worker runs in (default: $PWD)
#   worktree   OPTIONAL worktree name → isolated git worktree at
#              <cwd>/.claude/worktrees/<name> on branch worktree-<name>
#              (created here; claude's --worktree is claude-native)
#   model      default $CODEX_MODEL or gpt-5.6-sol
#   effort     default $CODEX_EFFORT or high
#   --no-wait  register as soon as the session id materializes and return
#
# Status semantics: codex exec has no interactive approval prompts, so a codex
# daemon is NEVER `blocked` — the approvals reviewer adjudicates escalations
# in-flight; a declined escalation is a failed command the worker sees.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"
# shellcheck source=_codex_lib.sh
source "$DIR/_codex_lib.sh"
CODEX_LIB_DIR="$DIR"; export CODEX_LIB_DIR

nowait=0
if [ "${1:-}" = "--no-wait" ]; then nowait=1; shift; fi
name="${1:?usage: codex-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model] [effort]}"
task="${2:?missing task}"
cwd="${3:-$PWD}"
worktree="${4:-}"
model="${5:-${CODEX_MODEL:-gpt-5.6-sol}}"
effort="${6:-${CODEX_EFFORT:-high}}"

command -v codex >/dev/null 2>&1 || { echo "codex-spawn: codex CLI not found" >&2; exit 1; }

# Worktree isolation (mirror of claude --worktree; reuse an existing one).
runcwd="$cwd"
if [ -n "$worktree" ]; then
  wt="$(printf '%s' "$worktree" | tr -c 'a-zA-Z0-9._-' '-')"
  wtdir="$cwd/.claude/worktrees/$wt"
  if [ ! -d "$wtdir" ]; then
    git -C "$cwd" worktree add "$wtdir" -b "worktree-$wt" >/dev/null 2>&1 \
      || git -C "$cwd" worktree add "$wtdir" "worktree-$wt" >/dev/null \
      || { echo "codex-spawn: worktree add failed for $wt" >&2; exit 1; }
  fi
  runcwd="$wtdir"
fi

# Skills parity with claude workers: expose the doperpowers skill doctrine at
# <workspace>/.agents/skills — codex scans that path (see _codex_vendor_skills).
_codex_vendor_skills "$runcwd"

runs="$DAEMON_HOME/runs"; mkdir -p "$runs"
_codex_gc_runs   # reclaim orphaned scratch from earlier turns before adding ours
run="$(mktemp "$runs/codex-run.XXXXXX")"; rm -f "$run"
taskf="$run.task.txt"
printf '%s' "$task" > "$taskf"

_codex_flags "$model" "$effort"
addroot="$(_codex_main_root "$runcwd")"
[ -n "$addroot" ] && CODEX_FLAGS=( "${CODEX_FLAGS[@]}" --add-dir "$addroot" )

_codex_launch "$runcwd" "$taskf" "$run" exec "${CODEX_FLAGS[@]}"

# Register as soon as the session id materializes.
uuid=""; i=0; max="${DAEMON_UUID_POLL:-30}"
while [ -z "$uuid" ]; do
  uuid="$(_codex_thread_id "$run.events.jsonl")"
  [ -n "$uuid" ] && break
  if [ -f "$run.rc" ] && [ -z "$(_codex_thread_id "$run.events.jsonl")" ]; then
    echo "codex-spawn: codex exited (rc=$(cat "$run.rc")) before a session id:" >&2
    tail -5 "$run.err" >&2 2>/dev/null || true
    exit 1
  fi
  i=$((i + 1)); [ "$i" -ge "$max" ] && break
  sleep 2
done
[ -n "$uuid" ] || { echo "codex-spawn: no session id after $((max * 2))s" >&2; exit 1; }

pid="$(cat "$run.pid" 2>/dev/null || printf '')"
status="working"
[ -f "$run.rc" ] && status="$(_codex_final_status "$(cat "$run.rc")" "$run.events.jsonl")"
_meta_set "$uuid" \
  uuid "$uuid" current "$uuid" short "$(printf '%.8s' "$uuid")" name "$name" \
  task "$task" cwd "$runcwd" worktree "$worktree" model "$model" effort "$effort" \
  engine "codex" pid "$pid" event_log "$run.events.jsonl" \
  status "$status" created "$(_now)" updated "$(_now)" turns "1"
# The wrapper may have finalized between our check and the write — re-apply.
[ -f "$run.rc" ] && _meta_set "$uuid" \
  status "$(_codex_final_status "$(cat "$run.rc")" "$run.events.jsonl")" updated "$(_now)"

if [ "$nowait" -eq 1 ]; then
  echo "daemon spawned (no-wait): $name  [codex $(printf '%.8s' "$uuid") / $uuid]  status=$(_meta_get "$uuid" status)  (reply: daemon-reply.sh $(printf '%.8s' "$uuid"))"
  exit 0
fi

# Blocking: wait for the wrapper's rc, bounded by DAEMON_TIMEOUT (watcher bound
# only — the turn itself is never killed; on timeout status stays working).
i=0; max=$((DAEMON_TIMEOUT / 2)); [ "$max" -le 0 ] && max=0
while [ ! -f "$run.rc" ]; do
  i=$((i + 1))
  if [ "$max" -gt 0 ] && [ "$i" -ge "$max" ]; then
    echo "daemon spawned: $name  [codex $uuid]  status=working (watcher timeout — turn continues; reply: daemon-reply.sh $(printf '%.8s' "$uuid"))"
    exit 0
  fi
  sleep 2
done
echo "daemon spawned: $name  [codex $(printf '%.8s' "$uuid") / $uuid]  status=$(_meta_get "$uuid" status)"
echo "--- reply ---"
_reply_text "$uuid"
