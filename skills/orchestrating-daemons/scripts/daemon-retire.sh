#!/usr/bin/env bash
# daemon-retire.sh <short-or-full-uuid> [purge]
#
# Retire a daemon from the active fleet. By default marks it status=retired but
# keeps its registry record. Pass `purge` to also delete the registry files
# (metadata/reply/err). The underlying claude session transcript on disk is NEVER
# touched — the human can still `claude --resume <uuid>` it interactively.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-retire.sh <uuid> [purge]}")"
name="$(_meta_get "$uuid" name)"
short="$(_meta_get "$uuid" short)"
worktree="$(_meta_get "$uuid" worktree)"

# Stop the live turn if it is still running (idempotent) — engine-specific:
# a claude daemon is stopped via the supervisor; a codex daemon is a detached
# process we own directly, so we signal its recorded pid ourselves.
engine="$(_meta_get "$uuid" engine)"
if [ "$engine" = "codex" ]; then
  pid="$(_meta_get "$uuid" pid)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    # Killing the pid makes _codex_launch's own detached wrapper (the one
    # that finalizes status+reply once `wait` on the codex pid returns) wake
    # up and write a terminal status (idle/error) of its own — racing our
    # "retired" write below. Its rc file is the same completion barrier
    # codex-resume.sh already waits on; wait for it here too so "retired" is
    # written LAST and isn't immediately clobbered by the wrapper's own
    # finalization of the turn we just killed.
    log="$(_meta_get "$uuid" event_log)"
    if [ -n "$log" ]; then
      rc_barrier="${log%.events.jsonl}.rc"
      bound="${CODEX_RC_BARRIER_WAIT:-10}"; j=0
      while [ ! -f "$rc_barrier" ] && [ "$j" -lt "$bound" ]; do sleep 1; j=$((j + 1)); done
    fi
  fi
  resume_hint="codex resume $uuid"
else
  [ -n "$short" ] && claude stop "$short" >/dev/null 2>&1 || true
  resume_hint="claude --resume $uuid"
fi

# Never auto-delete a worktree/branch — the daemon may have committed work you
# still want to review or merge (see finishing-a-development-branch).
wtnote=""
[ -n "$worktree" ] && wtnote="  NOTE: work is on branch worktree-$(printf '%s' "$worktree" | tr -c 'a-zA-Z0-9._-' '-') — merge or remove its worktree yourself."

if [ "${2:-}" = "purge" ]; then
  # A codex daemon's turn scratch (codex-run.*) lives under $DAEMON_HOME/runs;
  # its event_log points into that set. We are about to drop the meta, so the
  # runs GC would never again see this daemon to reclaim it — remove the set now.
  if [ "$engine" = "codex" ]; then
    el="$(_meta_get "$uuid" event_log)"
    [ -n "$el" ] && rm -f "${el%.events.jsonl}".* 2>/dev/null || true
  fi
  rm -f "$(_meta_path "$uuid")" "$(_reply_path "$uuid")" "$(_err_path "$uuid")"
  echo "purged $name [$uuid] from registry (session transcript left intact; resume with: $resume_hint)${wtnote}"
else
  _meta_set "$uuid" status "retired" updated "$(_now)"
  echo "retired $name [$uuid] (still resumable: $resume_hint)${wtnote}"
fi
