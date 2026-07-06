#!/usr/bin/env bash
# _lib.sh — shared helpers for the issue-tracker board toolkit.
# Sourced by board-*.sh. Not meant to be run directly.
#
# The board is one board.json (graph + states) plus per-ticket markdown and an
# append-only log.jsonl under doperpowers/issue-tracker/ in the consumer repo.
# Single-writer rule for BULK ops: allocating/reconciling writes (register a new
# ticket + bump next_id, board-gh sync, reconcile) run only from the repo's MAIN
# checkout — sourcing this file refuses a linked worktree to keep board.json from
# diverging across trees and to avoid next_id collisions.
# Exception: a single-ticket state change (board-transition.sh) is worktree-safe —
# the worker that OWNS a ticket may move its own ticket from its isolated worktree.
# Such scripts export BOARD_WORKTREE_OK=1 before sourcing to opt out of the guard.
set -euo pipefail

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
_today() { date -u +%Y-%m-%d; }

die() {
  echo "error: $*" >&2
  exit 1
}

# Arity guard for option parsing: die (naming the option) instead of tripping a
# raw `set -u` unbound-variable error when an option is given its final operand.
# Call as `_need_arg "$1" "${2:-}"` right before consuming "$2".
_need_arg() { [ -n "${2:-}" ] || die "option $1 requires a value"; }

# Resolve the repo root; refuse linked worktrees (canonical-copy rule) unless the
# sourcing script opted in with BOARD_WORKTREE_OK=1 (single-ticket ops only).
# In a linked worktree, --git-dir points under <main>/.git/worktrees/<name>
# while --git-common-dir points at <main>/.git — they differ.
_board_root() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repo"
  local gd cdir
  gd="$(cd "$(git rev-parse --git-dir)" && pwd)"
  cdir="$(cd "$(git rev-parse --git-common-dir)" && pwd)"
  if [ "$gd" != "$cdir" ] && [ -z "${BOARD_WORKTREE_OK:-}" ]; then
    die "refusing to touch the board from a worktree — run bulk ops from the main checkout (single-ticket board-transition.sh is allowed and sets BOARD_WORKTREE_OK=1)"
  fi
  git rev-parse --show-toplevel
}

BOARD_ROOT="$(_board_root)"
BOARD_DIR="$BOARD_ROOT/doperpowers/issue-tracker"
MAP="$BOARD_DIR/board.json"
LOG="$BOARD_DIR/log.jsonl"

# Daemon registry — same default (and same test override) as orchestrating-daemons.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"

# Lazy bootstrap: first register creates the data dir + an empty map.
# Atomic like every other map write: tmp then rename — mv within the same
# directory is rename(2), so a crash can never leave a partial board.json.
_board_init() {
  [ -f "$MAP" ] && return 0
  mkdir -p "$BOARD_DIR/tickets"
  printf '{\n  "version": 1,\n  "next_id": 1,\n  "tickets": {}\n}\n' > "$MAP.tmp"
  mv "$MAP.tmp" "$MAP"
}

# Run an inline python3 board operation with the board paths exported.
_py() { BOARD_MAP="$MAP" BOARD_LOG="$LOG" python3 "$@"; }

usage_from_header() { grep '^#' "$1" | grep -v '^#!' | sed 's/^# \{0,1\}//'; }
