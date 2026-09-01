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
# The live-binding guard (board-transition.sh, dp#63) adjudicates on the LOCAL
# seat registry — an operator's real registry (a live worker bound to a
# ticket number these fixtures reuse) would inject refusals into suites that
# never seeded a binding. Every suite starts from an empty registry of its
# own; `finish` takes it away again.
DAEMON_HOME="$(mktemp -d)"; export DAEMON_HOME
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
