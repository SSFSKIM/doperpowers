#!/usr/bin/env bash
# lib.sh — the sourced half of sminos, for shell consumers that need the
# registry root and host identity inline (the board pipeline's dispatchers).
# Everything else is a verb of the `sminos` CLI next to this file. Not meant to
# be run directly.
#
# The registry is one directory of seat records: a "seat" is a named position
# in a group that a Claude Code session fills; its record is
# $SMINOS_HOME/<seat-id>.json (seat id = the first session's uuid), and the
# board pipeline reads and writes those records directly under the shared
# flock file $SMINOS_HOME/.metalock. `DAEMON_HOME` is the older name of the
# same root and is honored so existing consumers and tests keep working.

set -euo pipefail

SMINOS_HOME="${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}"
DAEMON_HOME="$SMINOS_HOME"
# The registry is private to the agent fleet (records can carry the board run
# bearer): create it 0700 and tighten a root the old substrate left wider. The
# mode is meant for the deepest directory only — its parent is ~/.claude, whose
# own mode is not ours to change.
# shellcheck disable=SC2174
mkdir -p -m 700 "$SMINOS_HOME"
chmod 700 "$SMINOS_HOME" 2>/dev/null || true

# Host + boot identity — stamped into records at every registration. A pid
# (and a `claude agents` short id) is only meaningful in the host's current
# boot. Hostname catches volume migration; boot id catches a rebuilt/rebooted
# machine that kept its name but received a fresh pid namespace. Override both
# values for tests.
DAEMON_HOST="${DAEMON_HOST:-$(hostname)}"
_boot_id() {
  if [ -r /proc/sys/kernel/random/boot_id ]; then
    cat /proc/sys/kernel/random/boot_id
  elif command -v sysctl >/dev/null 2>&1; then
    # Anchor on the LEADING `{ sec = N,` field: a greedy `.*sec = ` lands on
    # the `sec` inside `usec = ` and records the microseconds instead.
    sysctl -n kern.boottime 2>/dev/null | sed -E 's/^\{ sec = ([0-9]+),.*/\1/' || true
  fi
}
DAEMON_BOOT_ID="${DAEMON_BOOT_ID:-$(_boot_id)}"

# How long a spawn/wake WATCHER polls `claude agents` for a turn to finish — a
# wait bound only, never a turn budget: every turn is an independent `--bg`
# process that keeps running regardless. Default 5 hours; 0 = watch forever.
DAEMON_TIMEOUT="${DAEMON_TIMEOUT:-18000}"

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# rc 0 iff a record's recorded host/boot identity belongs to this boot. Empty
# values preserve legacy local behavior.
_identity_local() {
  local host="${1:-}" boot_id="${2:-}"
  [ -z "$host" ] || [ "$host" = "$DAEMON_HOST" ] || return 1
  [ -z "$boot_id" ] || [ -z "$DAEMON_BOOT_ID" ] || [ "$boot_id" = "$DAEMON_BOOT_ID" ] || return 1
}

# rc 0 iff pid <1> is live in THIS HOST BOOT. An identity mismatch is DEAD
# regardless of kill -0: only the number survived.
_pid_alive() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  _identity_local "${2:-}" "${3:-}" || return 1
  kill -0 "$pid" 2>/dev/null
}
