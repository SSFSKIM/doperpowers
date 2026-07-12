#!/usr/bin/env bash
# daemon-resume.sh <short-or-full-uuid> <message>
#
# Continue a daemon by FORKING a new native background turn. A daemon's identity
# is its ORIGINAL session uuid (the registry meta filename); each resume runs
# `claude stop` on the current turn to release its bg ownership (which also drops
# it from the active `claude agents` view), then `claude --bg --resume <current>`
# to fork a fresh bg agent that carries the full conversation forward. The new
# turn gets its own short/uuid; the registry chains them via the `current` field,
# so the daemon keeps one stable id while its human-visible short changes. Once
# the fork is confirmed, the superseded turn's session is purged (jobs entry +
# transcript) so the dashboard shows one session per daemon.
#
# Because the forked turn is a native `--bg` agent, it is visible in
# `claude agents` (kind=background) and survives this orchestrator ending — the
# toolkit never kills it.
#
# NEVER RUN THIS IN THE FOREGROUND — it blocks while the watcher polls for the
# forked turn to finish, prints the reply, then exits. Run it under a Monitor (the
# reply streams into context as an event — no read step) or a background shell
# (Bash run_in_background: true). Resume is scoped to the daemon's cwd, which this
# script restores.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-resume.sh <uuid> <message>}")"
msg="${2:?missing message}"

[ "$(_meta_get "$uuid" engine)" = "codex" ] \
  && { echo "daemon-resume: $uuid is a codex daemon — use codex-resume.sh" >&2; exit 1; }

name="$(_meta_get "$uuid" name)"
cwd="$(_meta_get "$uuid" cwd)"; model="$(_meta_get "$uuid" model)"
turns="$(_meta_get "$uuid" turns)"; [ -n "$turns" ] || turns=0
# Worktree'd daemon → purge needs the worktree path to dirty-guard it while
# `claude rm` runs (rm deletes a CLEAN worktree with the owning turn).
wtpath=""; [ -n "$(_meta_get "$uuid" worktree)" ] && wtpath="$cwd"

# The turn to fork from is the CURRENT session (backward compat: metas created
# before the fork rework have no `current`, so fall back to the daemon's uuid).
cur="$(_meta_get "$uuid" current)"; [ -n "$cur" ] || cur="$uuid"
curshort="$(_meta_get "$uuid" short)"

# Release the current bg turn (idempotent — harmless if already stopped). This
# also drops it from the active `claude agents` view before the next turn forks.
[ -n "$curshort" ] && claude stop "$curshort" >/dev/null 2>&1 || true

_meta_set "$uuid" status "working" updated "$(_now)"

# Fork a new native bg agent from the current session — new short/uuid, full
# context. `-n` keeps the daemon's display name stable across turns.
args=( --bg --resume "$cur" --permission-mode auto -n "$name" )
[ -n "$model" ] && args+=( --model "$model" )
args+=( "$msg" )

# Fork the new native bg agent. Capture the banner WITHOUT tripping `set -e`: a
# nonzero fork exit (e.g. the session is not resumable) MUST fall through to the
# error handler below rather than kill the script on this assignment — otherwise
# the meta is stranded status=working with `current` still on the old (stopped)
# turn. A nonzero exit AND a banner with no parseable short id both land in the
# same error path.
# env -u RUNNER_TRACKING_ID: the forked agent must survive a runner dispatch
# job's post-job cleanup, which kills marker-carrying processes (see
# daemon-spawn.sh).
newshort=""
if banner="$(cd "$cwd" && env -u RUNNER_TRACKING_ID claude "${args[@]}" </dev/null 2>&1 | _strip_ansi)"; then
  newshort="$(printf '%s\n' "$banner" | sed -n 's/.*backgrounded · \([0-9a-f][0-9a-f]*\).*/\1/p' | head -1)"
fi
if [ -z "$newshort" ]; then
  _meta_set "$uuid" status "error" updated "$(_now)"
  echo "resume failed — fork did not launch or produced no background id:" >&2
  echo "$banner" >&2
  exit 1
fi

# Register local ownership as soon as the new UUID materializes, BEFORE the
# terminal watcher can block for hours. This is the liveness handoff: dispatch
# must see the active fork as local, not keep reading the migrated source host.
newuuid=""
if uuid_out="$(_poll_uuid "$newshort")"; then
  newuuid="${uuid_out%% *}"
fi
case "$newuuid" in
  ""|*[!0-9a-f-]*)
    _meta_set "$uuid" status "error" pending_short "$newshort" updated "$(_now)"
    echo "resume: forked agent $newshort produced no usable session uuid; kept previous current (recover via meta pending_short)." >&2
    exit 1 ;;
esac
_meta_set "$uuid" current "$newuuid" short "$newshort" host "$DAEMON_HOST" boot_id "$DAEMON_BOOT_ID" \
  status "working" updated "$(_now)"
# The fork is confirmed live — the superseded turn's session can go now rather
# than waiting for terminal state.
if [ "$cur" != "$newuuid" ]; then _session_purge "$curshort" "$cur" "$wtpath"; fi

# Wait for the forked turn to finish, PRESERVING the watcher's exit status so we
# can tell a terminal turn (rc 0) from a timeout (rc != 0). Parse via parameter
# expansion, not word-splitting: the watcher's timeout line can lead with an
# empty uuid field, and `read` would collapse that leading space and mistake the
# state token for the uuid. The cwd is fixed at spawn and never changes.
poll_rc=0
poll_out="$(_poll_until_done "$newshort" "$((DAEMON_TIMEOUT / 2))")" || poll_rc=$?
polled_uuid="${poll_out%% *}"; state="${poll_out#* }"; state="${state%% *}"
case "$polled_uuid" in
  *[!0-9a-f-]*) polled_uuid="" ;;  # defensive: a jumbled poll line is not a session uuid
esac
[ -n "$polled_uuid" ] && newuuid="$polled_uuid"

# The UUID was already confirmed and registered above. A watcher timeout leaves
# that truthful working state in place; no reply or turn-count update has landed.
if [ "$poll_rc" -ne 0 ]; then
  echo "resume: watcher expired after $((DAEMON_TIMEOUT / 2)) polls; forked turn $newshort ($newuuid) is still running (status=working)." >&2
  echo "        run daemon-reply.sh $uuid once it lands to read the reply." >&2
  exit 1
fi

# Terminal state — the turn produced a final reply. Record it and finalize.
status="idle"; [ "$state" = "blocked" ] && status="blocked"; [ "$state" = "error" ] && status="error"

# Reply file stays keyed by the ORIGINAL uuid; read the reply from the new turn.
_record_reply "$newuuid" "$uuid" "$state"
_meta_set "$uuid" current "$newuuid" short "$newshort" host "$DAEMON_HOST" boot_id "$DAEMON_BOOT_ID" \
  status "$status" updated "$(_now)" turns "$((turns + 1))"

echo "daemon resumed: $name  [$newshort / $uuid]  status=$(_meta_get "$uuid" status)  turns=$(_meta_get "$uuid" turns)  current=$newuuid"
echo "--- reply ---"
_reply_text "$uuid"
