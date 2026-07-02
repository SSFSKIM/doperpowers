#!/usr/bin/env bash
# _lib.sh — shared helpers for the issue-tracker board toolkit.
# Sourced by board-*.sh. Not meant to be run directly.
#
# The board is one map.json (graph + states) plus per-ticket markdown and an
# append-only log.jsonl under doperpowers/issue-tracker/ in the consumer repo.
# Single-writer rule: only the orchestrator (main session) writes it, and only
# from the repo's MAIN checkout — sourcing this file enforces the second half
# by refusing to run from a linked worktree.
set -euo pipefail

_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
_today() { date -u +%Y-%m-%d; }

die() {
  echo "error: $*" >&2
  exit 1
}

# Resolve the repo root; refuse linked worktrees (canonical-copy rule).
# In a linked worktree, --git-dir points under <main>/.git/worktrees/<name>
# while --git-common-dir points at <main>/.git — they differ.
_board_root() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repo"
  local gd cdir
  gd="$(cd "$(git rev-parse --git-dir)" && pwd)"
  cdir="$(cd "$(git rev-parse --git-common-dir)" && pwd)"
  [ "$gd" = "$cdir" ] || die "refusing to touch the board from a worktree — run from the main checkout"
  git rev-parse --show-toplevel
}

BOARD_ROOT="$(_board_root)"
BOARD_DIR="$BOARD_ROOT/doperpowers/issue-tracker"
MAP="$BOARD_DIR/map.json"
LOG="$BOARD_DIR/log.jsonl"

# Daemon registry — same default (and same test override) as orchestrating-daemons.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"

# Lazy bootstrap: first register creates the data dir + an empty map.
# Atomic like every other map write: tmp then rename — mv within the same
# directory is rename(2), so a crash can never leave a partial map.json.
_board_init() {
  [ -f "$MAP" ] && return 0
  mkdir -p "$BOARD_DIR/tickets"
  printf '{\n  "version": 1,\n  "next_id": 1,\n  "tickets": {}\n}\n' > "$MAP.tmp"
  mv "$MAP.tmp" "$MAP"
}

# Run an inline python3 board operation with the board paths exported.
_py() { BOARD_MAP="$MAP" BOARD_LOG="$LOG" python3 "$@"; }

usage_from_header() { grep '^#' "$1" | grep -v '^#!' | sed 's/^# \{0,1\}//'; }
