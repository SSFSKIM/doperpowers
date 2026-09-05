#!/usr/bin/env bash
# helpers.sh — board-api test scaffolding. Source from every test in this dir.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../../.." && pwd)"
# shellcheck disable=SC2034  # consumed by the tests that source this file
SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"
# The client legitimately branches on BOARD_RUN_TOKEN (claim-gate guard,
# board-show's degrade), so an operator who happens to hold one in their
# environment changes what these suites are testing. Every drill that wants a
# run context sets the bearer on the invocation itself, so nothing here loses
# reach by starting from none.
unset BOARD_RUN_TOKEN
# Same reason, for the repo an api binding speaks for: BOARD_REPO wins over
# .doperpowers/board.json when it is set, so an operator holding one in their
# environment would silently retarget every fixture repo in these suites. Each
# drill that wants an override states it on the invocation.
unset BOARD_REPO
# Same reason again, for the session a verb self-locates by: a run context is
# resolved from the seat record whose id matches $CLAUDE_CODE_SESSION_ID, and
# every one of these suites is itself run from inside a Claude session. Left
# set, that ambient id would let a verb here find the OPERATOR's own seat
# record and speak as whatever run it is bound to. The drills that want a
# self-locating session state the id on the invocation.
unset CLAUDE_CODE_SESSION_ID
# The live-binding guard (board-transition.sh, dp#63) adjudicates on the LOCAL
# seat registry — an operator's real registry (a live worker bound to a
# ticket number these fixtures reuse) would inject refusals into suites that
# never seeded a binding. Every suite starts from an empty registry of its
# own; `finish` takes it away again.
#
# $SMINOS_HOME goes with it, and goes AWAY rather than to the same value: the
# root rule is $SMINOS_HOME first, then $DAEMON_HOME, so an operator holding
# one would send every read here at their real registry — while a scratch one
# exported from this file would OUTRANK the per-invocation `DAEMON_HOME=…`
# prefixes these suites pin their fixtures with. Unset, DAEMON_HOME is the
# whole rule, which is what every drill in this tier already assumes.
unset SMINOS_HOME
DAEMON_HOME="$(mktemp -d)"; export DAEMON_HOME
# The per-binding subdirectory a store's records live in. $DAEMON_HOME is
# machine-global and a board is not, so `board-claims`, `board-suppress` and
# `surface-locks` are each filed under one 16-hex digest of the binding — a
# neighbour repo on the same service keys differently, and a FLAT record
# directly under the store root is the legacy shape that predates the key.
# Drills plant and read through this so a fixture path can never disagree with
# the digest the scripts compute.
store_dir() {  # store_dir <registry root> <store> <port> [repo key]
  SMINOS_HOME="" DAEMON_HOME="$1" BOARD_BINDING=api \
  BOARD_API_URL="http://127.0.0.1:$3" BOARD_REPO="${4:-testrepo}" \
  PYTHONPATH="$SCRIPTS" python3 -c \
    'import sys, _board_api as A; print(A.store_dir(sys.argv[1]))' "$2"
}
FAILS=0
t() {  # t <name> <expected-substring> cmd...
  local name="$1" want="$2"; shift 2 || { echo "t: bad call"; exit 2; }
  local out; out="$("$@" 2>&1)" || true
  if grep -qF -- "$want" <<<"$out"; then echo "ok   $name"
  else echo "FAIL $name — wanted '$want' in:"; sed 's/^/     /' <<<"$out"; FAILS=$((FAILS+1)); fi
}
nt() {  # nt <name> <forbidden-substring> cmd... — the inverse of t
  local name="$1" bad="$2"; shift 2 || { echo "nt: bad call"; exit 2; }
  local out; out="$("$@" 2>&1)" || true
  if grep -qF -- "$bad" <<<"$out"; then echo "FAIL $name — '$bad' must NOT appear, but:"
    sed 's/^/     /' <<<"$out"; FAILS=$((FAILS+1))
  else echo "ok   $name"; fi
}
rc() {  # rc <expected-code> <name> cmd... — the exit STATUS, and nothing else
  # t/nt read the output and tolerate any exit, so a refusal that decays from
  # exit 2 to exit 1 (or to success) still passes them. Exit codes are pinned
  # contract for the verbs; this asserts that half on its own.
  local want="$1" name="$2"; shift 2 || { echo "rc: bad call"; exit 2; }
  local out code=0; out="$("$@" 2>&1)" || code=$?
  if [ "$code" -eq "$want" ]; then echo "ok   $name"
  else echo "FAIL $name — wanted exit $want, got $code:"
    sed 's/^/     /' <<<"$out"; FAILS=$((FAILS+1)); fi
}
# Every throwaway repo mkrepo hands out, so `finish` can take them away again:
# a suite makes a handful per run and left every one of them in $TMPDIR.
MKREPO_DIRS=()
mkrepo() {  # fresh throwaway git repo, prints its path
  local d; d="$(mktemp -d)"; git -C "$d" init -q
  MKREPO_DIRS+=("$d")
  echo "$d"
}
_mkrepo_cleanup() {
  local d
  for d in ${MKREPO_DIRS[@]+"${MKREPO_DIRS[@]}"}; do
    # A worktree registered under another repo has to be de-registered, or its
    # administrative files outlive the checkout this removes.
    git -C "$d" worktree prune >/dev/null 2>&1 || true
    rm -rf "$d"
  done
  MKREPO_DIRS=()
}
finish() {
  _mkrepo_cleanup
  rm -rf "$DAEMON_HOME"
  [ "$FAILS" -eq 0 ] && echo "PASS $(basename "$0")" || { echo "FAIL $(basename "$0") ($FAILS)"; exit 1; }
}
