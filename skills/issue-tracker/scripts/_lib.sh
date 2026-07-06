#!/usr/bin/env bash
# _lib.sh — shared helpers for the issue-tracker board toolkit (v7: GitHub SSOT).
# Sourced by board-*.sh. Not meant to be run directly.
#
# The board IS the repo's GitHub issues — there is no local state file, no
# single-writer rule, and no worktree guard (nothing here writes a git file).
# Scripts talk to GitHub through `gh` via the shared python module _board.py;
# doperpowers/issue-tracker/ survives only as a gitignored render-cache dir
# for board-map.sh.
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

# Repo root — render caches and the daemon-registry lookups anchor here. Any
# checkout works, worktrees included: the board lives on GitHub, so there is
# nothing local to diverge.
_board_root() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repo"
  git rev-parse --show-toplevel
}

BOARD_ROOT="$(_board_root)"
BOARD_DIR="$BOARD_ROOT/doperpowers/issue-tracker"   # render cache only (gitignored)
BOARD_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The target repo (owner/name): $BOARD_REPO wins, else the checkout's repo.
# Resolved once; fail-loud when gh is missing/unauthenticated/offline — the
# board has no offline fallback by design.
if [ -z "${BOARD_REPO:-}" ]; then
  command -v gh >/dev/null 2>&1 || die "\`gh\` not found — the board lives on GitHub"
  BOARD_REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
    || die "cannot resolve the GitHub repo (gh auth status? set BOARD_REPO=owner/name)"
fi
export BOARD_REPO

# Daemon registry — same default (and same test override) as orchestrating-daemons.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"

# Render-cache dir: created on demand, always gitignored — BOARD.html/BOARD.md
# are views of GitHub state and must never be committed (a committed render is
# how v6's board forked across branches).
_render_dir() {
  mkdir -p "$BOARD_DIR"
  [ -f "$BOARD_DIR/.gitignore" ] || printf '*\n' > "$BOARD_DIR/.gitignore"
}

# Run an inline python3 board operation with _board.py importable.
export BOARD_SCRIPTS
_py() { PYTHONPATH="$BOARD_SCRIPTS${PYTHONPATH:+:$PYTHONPATH}" python3 "$@"; }

usage_from_header() { grep '^#' "$1" | grep -v '^#!' | sed 's/^# \{0,1\}//'; }
