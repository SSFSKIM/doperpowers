#!/usr/bin/env bash
# test-store-scope.sh — the registry root is machine-global and a board is not.
# Every store under that root is filed in a per-binding subdirectory keyed by
# one digest, so two bound repos on one machine share the root and see none of
# each other's state. This suite drills the STORE itself: what a binding
# resolves, and what a neighbour's records do to it. The stores' consumers are
# drilled where they live (claims and suppressions in test-dispatch-claim.sh
# and test-sweep-resume.sh); surface locks have no hermetic consumer harness,
# so their neighbour-blindness is drilled here directly.
. "$(dirname "$0")/helpers.sh"

# Two repos on ONE service — the exposure this keying exists for. Only the repo
# key separates them, which is exactly the case a digest over the url alone
# would have merged.
mkbound() {  # mkbound <url> <repo key> — prints a fresh checkout bound to it
  local d; d="$(mkrepo)"; mkdir -p "$d/.doperpowers"
  printf '{"binding":"api","url":"%s","repo":"%s"}' "$1" "$2" \
    > "$d/.doperpowers/board.json"
  printf '%s\n' "$d"
}
OURS="$(mkbound https://board.example ours)"
THEIRS="$(mkbound https://board.example theirs)"
# A gh-bound checkout: no board.json at all, and the repo resolved the way
# _lib.sh and board-sweep.sh resolve it before any store is reached.
GHR="$(mkrepo)"

store() {  # store <repo dir> <store name> [VAR=val ...]
  local d="$1" name="$2"; shift 2
  ( cd "$d" && env "$@" bash -c ". '$SCRIPTS/_binding.sh'; board_store_dir '$name'" )
}

OURS_LOCKS="$(store "$OURS" surface-locks)"
THEIRS_LOCKS="$(store "$THEIRS" surface-locks)"

t "a store is a subdirectory of the machine-global root" \
  "$DAEMON_HOME/surface-locks/" bash -c "printf '%s\n' '$OURS_LOCKS'"
t "two repos on one service file into different subdirectories" "differ" \
  bash -c "[ '$OURS_LOCKS' != '$THEIRS_LOCKS' ] && echo differ || echo same"

# The drill this store exists for: a surface name means something only within
# one board, so two repos that both call a surface `auth` serialized against
# each other for no reason — one repo's dispatcher declined to dispatch because
# the other's held the name.
mkdir "$THEIRS_LOCKS/auth"
t "a neighbour holding the same surface name does not block us" "acquired" \
  bash -c "mkdir '$OURS_LOCKS/auth' 2>/dev/null && echo acquired || echo blocked"
t "while our own hold still contends, as it always did" "blocked" \
  bash -c "mkdir '$OURS_LOCKS/auth' 2>/dev/null && echo acquired || echo blocked"
rmdir "$OURS_LOCKS/auth" "$THEIRS_LOCKS/auth"

# BOTH BINDINGS, one rule. The gh-side users (board-register.sh's relate pass,
# board-sweep.sh's SURFACE pass) take the same keyed root, and a gh binding is
# a THIRD board even when its repo name matches an api one — the service is
# part of the identity.
gh_locks() { store "$GHR" surface-locks BOARD_REPO=acme/ours; }
t "a gh binding's surface locks are keyed too" \
  "$DAEMON_HOME/surface-locks/" gh_locks
nt "and never share an api binding's key" "$OURS_LOCKS" gh_locks

# The three users of this store sit in three files and in both bindings, and
# there is no hermetic harness that drives the gh two. This is the guard that
# keeps them routed through the one helper: a user that resolved the root for
# itself is how the boards silently re-merge.
surface_lock_users() {
  grep -c 'board_store_dir surface-locks' \
    "$REPO_ROOT/skills/executing/scripts/execute-dispatch.sh" \
    "$REPO_ROOT/skills/issue-tracker/scripts/board-register.sh" \
    "$REPO_ROOT/skills/issue-tracker/scripts/board-sweep.sh"
}
nt "no surface-lock user resolves the store root for itself" ":0" surface_lock_users

finish
