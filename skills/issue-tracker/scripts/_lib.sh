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

# shellcheck source=_binding.sh
. "$BOARD_SCRIPTS/_binding.sh"

# The target repo (owner/name) — gh mode only: $BOARD_REPO wins, else the
# checkout's repo. Fail-loud when gh is missing/unauthenticated/offline.
if [ "$BOARD_BINDING" = gh ] && [ -z "${BOARD_REPO:-}" ]; then
  command -v gh >/dev/null 2>&1 || die "\`gh\` not found — the board lives on GitHub"
  BOARD_REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
    || die "cannot resolve the GitHub repo (gh auth status? set BOARD_REPO=owner/name)"
fi
# EXPORTED IN gh MODE ONLY. gh consumers read it out of the environment
# (_board.py's repo(), board-transition's closed-ticket probe), so there it has
# to travel. In api mode nothing downstream reads the environment — _api_py
# hands the value to python3 explicitly — and exporting it would make this
# process's repo the DEFAULT for any descendant that resolves its own binding:
# _binding.sh honours an inherited BOARD_REPO so a user can override the file,
# and a value derived from the parent's board.json is not that override. A verb
# run from a neighbouring checkout would then read and write the parent's repo,
# which is the accident this key exists to prevent, one level down.
#
# Worker handovers are the deliberate exception: they put the key in the child's
# environment ON PURPOSE, because a worker checks out the head it was dispatched
# for and a head predating this key carries a board.json without one. That child
# is bound to the handing-over process's repo by construction — the run bearer
# beside the key ties it to a ticket in that repo — so it is a pin, not a leak.
# An ambient export is neither, which is why these are scoped.
#
# THE RULE, one line: wherever BOARD_API_URL is pinned on an env prefix for a
# worker, BOARD_REPO is pinned beside it. The two facts have the same lifetime
# and the same blast radius, and a worker that kept the URL while losing the
# repo dies on `binding=api but no repo` mid-run. Today that is the two
# dispatchers' spawns and the sweep's three handovers (relay resume, successor
# resume, fresh-successor spawn); a new one inherits the rule, not a review.
# The prefix is the DECLARED channel, not yet a delivered one: `claude --bg`
# drops every spawn-prefix variable (the run bearer and the fence included, not
# just these two), so today the pin reaches a worker's own shells only on the
# foreground route. Board ticket 35 owns that handoff; these pins ride along the
# moment it is fixed, and the rule above is what makes that true without a
# second pass over every call site.
if [ "$BOARD_BINDING" = gh ]; then export BOARD_REPO; fi

# Daemon registry — same default (and same test override) as orchestrating-daemons.
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"

# Render-cache dir: created on demand, always gitignored — BOARD.html/BOARD.md
# are views of GitHub state and must never be committed (a committed render is
# how v6's board forked across branches).
_render_dir() {
  mkdir -p "$BOARD_DIR"
  [ -f "$BOARD_DIR/.gitignore" ] || printf '*\n' > "$BOARD_DIR/.gitignore"
}

# The recorded --serve pid, but only when it still looks like OUR python
# http.server (prints it and returns 0). A reboot can recycle a stale
# pidfile's pid onto an unrelated process — which --stop must not kill and
# --serve must not mistake for a running board server.
_board_server_pid() {
  local pid
  pid="$(cat "$BOARD_DIR/.server.pid" 2>/dev/null)" || return 1
  [ -n "$pid" ] || return 1
  case "$(ps -o command= -p "$pid" 2>/dev/null)" in
    *http.server*) printf '%s\n' "$pid" ;;
    *) return 1 ;;
  esac
}

# Live tab refresh: when `board-map.sh --serve` left a server up, a successful
# mutation re-renders the cache in the background — every open BOARD.html tab
# hot-reloads on its next poll. No server → free no-op, so mutating scripts
# call this unconditionally as their last step.
_rerender_if_serving() {
  _board_server_pid >/dev/null 2>&1 || return 0
  ("$BOARD_SCRIPTS/board-map.sh" --write >/dev/null 2>&1 &)
}

# Run an inline python3 board operation with _board.py importable.
export BOARD_SCRIPTS
_py() { PYTHONPATH="$BOARD_SCRIPTS${PYTHONPATH:+:$PYTHONPATH}" python3 "$@"; }

# Verbs with no API-mode counterpart refuse in one voice: the same message from
# four copies drifted the moment one of them was edited, and this one described
# a route set (edge re-cut / priority / relates / body edits) that does not name
# what board-migrate-gh actually is. The caller says what IT is; the pointer is
# shared.
_refuse_no_api_route() {  # <what this verb does>
  [ "$BOARD_BINDING" != api ] || die "$1 has no API-mode counterpart — \
file a server-side ticket in the arkho repo if the need is real; \
until such a route lands, run this against a gh-bound repo only"
}

# The script's own header block — the CONTIGUOUS run of column-0 `#` lines
# after the shebang, and nothing else. Grepping every column-0 `#` line in the
# file swept up any later comment that happened to start at column 0, so a
# usage message grew a paragraph about lock stealing as the file grew; scripts
# indented such notes by one space purely to stay out of it.
usage_from_header() {
  awk 'NR == 1 && /^#!/ { next }
       /^#/ { sub(/^# ?/, ""); print; next }
       { exit }' "$1"
}
