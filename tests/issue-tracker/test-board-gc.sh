#!/usr/bin/env bash
#
# Hermetic tests for board-gc.sh — the sweep's opt-in janitor pass.
#
# Real git (an origin bare repo + a consumer clone with worktrees), a gh
# stub on PATH serving a fixture PR table, a docker stub logging its calls.
# What these pin: the three-guard removal rule (finished upstream + clean +
# not actively held), opt-in inertness, the PR-lookup cap, and that the
# docker pass touches only exited postgres containers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GC="$REPO_ROOT/skills/issue-tracker/scripts/board-gc.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_dir_gone() {
    if [ ! -d "$2" ]; then pass "$1"; else fail "$1 (still exists: $2)"; fi
}
assert_dir_kept() {
    if [ -d "$2" ]; then pass "$1"; else fail "$1 (was removed: $2)"; fi
}

# ---- environment --------------------------------------------------------------
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export BOARD_REPO="test/repo"
export GH_FIXTURE="$TEST_ROOT/pr-table.txt"   # lines: <branch> <state>
export STUB_LOG="$TEST_ROOT/stub-calls.log"; : > "$STUB_LOG"

# gh stub: answers the pulls?head= lookup off the fixture table.
mkdir -p "$TEST_ROOT/bin"
cat > "$TEST_ROOT/bin/gh" <<'EOF'
#!/bin/bash
echo "gh $*" >> "$STUB_LOG"
case "$2" in
  repos/*/pulls?head=*)
    br="${2#*head=test:}"; br="${br%%&*}"
    state=$(awk -v b="$br" '$1 == b {print $2}' "$GH_FIXTURE")
    [ -n "$state" ] || { echo "none"; exit 0; }
    echo "$state"; exit 0 ;;
esac
echo "none"
EOF
cat > "$TEST_ROOT/bin/docker" <<'EOF'
#!/bin/bash
echo "docker $*" >> "$STUB_LOG"
case "$1" in
  ps) printf 'aaa111 ida-old-pg postgres:17\nbbb222 other-app node:22\n' ;;
  rm|volume) exit 0 ;;
esac
EOF
chmod +x "$TEST_ROOT/bin/gh" "$TEST_ROOT/bin/docker"
export PATH="$TEST_ROOT/bin:$PATH"

# The gh stub prints a bare state string; board-gc's --jq flag parsing is
# bypassed because the stub ignores flags. Wire the stub's answer shape to
# what the script consumes: it reads stdout as the state verbatim.

# ---- repo fixture --------------------------------------------------------------
ORIGIN="$TEST_ROOT/origin.git"
git init -q --bare "$ORIGIN"
export LOCAL_REPO="$TEST_ROOT/consumer"
git clone -q "$ORIGIN" "$LOCAL_REPO" 2>/dev/null || {
  git init -q "$LOCAL_REPO"
  git -C "$LOCAL_REPO" remote add origin "$ORIGIN"
}
cd "$LOCAL_REPO"
git config user.email t@t; git config user.name t
echo base > base.txt; git add .; git commit -qm base
git push -q origin HEAD:main
git branch --set-upstream-to=origin/main >/dev/null 2>&1 || true

mk_worktree() { # <name> <branch> [push]
  git -C "$LOCAL_REPO" worktree add -q -b "$2" "$LOCAL_REPO/.claude/worktrees/$1" >/dev/null 2>&1
  [ "${3:-}" = push ] && git -C "$LOCAL_REPO" push -q origin "$2"
  return 0
}

# t1: PR merged, clean, unheld → removed
mk_worktree t1 br-merged push
echo "br-merged merged" >> "$GH_FIXTURE"
# t2: PR still open → kept
mk_worktree t2 br-open push
echo "br-open open" >> "$GH_FIXTURE"
# t3: branch deleted on origin (never pushed) → removed via branch-gone
mk_worktree t3 br-gone
# t4: PR merged but tree dirty → kept
mk_worktree t4 br-dirty push
echo "br-dirty merged" >> "$GH_FIXTURE"
echo wip > "$LOCAL_REPO/.claude/worktrees/t4/wip.txt"
# t5: PR merged but an ACTIVE meta holds the path → kept
mk_worktree t5 br-held push
echo "br-held merged" >> "$GH_FIXTURE"
cat > "$DAEMON_HOME/w1.json" <<EOF
{"status": "working", "worktree": "$LOCAL_REPO/.claude/worktrees/t5"}
EOF
# t6: idle meta does NOT hold — PR merged → removed
mk_worktree t6 br-idleheld push
echo "br-idleheld merged" >> "$GH_FIXTURE"
cat > "$DAEMON_HOME/w2.json" <<EOF
{"status": "idle", "worktree": "$LOCAL_REPO/.claude/worktrees/t6"}
EOF

echo "=== opt-in inertness ==="
out=$(WORKTREE_GC=0 DOCKER_GC=0 "$GC" 2>&1 || true)
assert_dir_kept "no flags → nothing removed" "$LOCAL_REPO/.claude/worktrees/t1"
[ -z "$out" ] && pass "no flags → silent" || fail "no flags → silent (got: $out)"

echo "=== worktree pass ==="
out=$(WORKTREE_GC=1 "$GC" 2>&1)
assert_dir_gone "merged PR removed"            "$LOCAL_REPO/.claude/worktrees/t1"
assert_dir_kept "open PR kept"                 "$LOCAL_REPO/.claude/worktrees/t2"
assert_dir_gone "branch-gone removed"          "$LOCAL_REPO/.claude/worktrees/t3"
assert_dir_kept "dirty tree kept"              "$LOCAL_REPO/.claude/worktrees/t4"
assert_dir_kept "working-meta path kept"       "$LOCAL_REPO/.claude/worktrees/t5"
assert_dir_gone "idle-meta path removed"       "$LOCAL_REPO/.claude/worktrees/t6"
assert_contains "$out" "branch-gone" "evidence logged for branch-gone"
assert_contains "$out" "pr-merged"   "evidence logged for pr-merged"
# local branch of a removed worktree is deleted too
if git -C "$LOCAL_REPO" show-ref --verify --quiet refs/heads/br-merged; then
  fail "local branch deleted after removal"
else
  pass "local branch deleted after removal"
fi

echo "=== PR-lookup cap ==="
: > "$STUB_LOG"
mk_worktree t7 br-cap1 push; echo "br-cap1 merged" >> "$GH_FIXTURE"
mk_worktree t8 br-cap2 push; echo "br-cap2 merged" >> "$GH_FIXTURE"
out=$(WORKTREE_GC=1 GC_PR_CHECKS=1 "$GC" 2>&1)
lookups=$(grep -c "pulls?head=" "$STUB_LOG" || true)
if [ "$lookups" -le 2 ]; then pass "PR lookups capped ($lookups incl. open-PR recheck)"; else
  fail "PR lookups capped (got $lookups)"; fi

echo "=== docker pass ==="
: > "$STUB_LOG"
out=$(DOCKER_GC=1 "$GC" 2>&1)
assert_contains "$(cat "$STUB_LOG")" "docker rm -v aaa111" "exited postgres container removed with volumes"
if grep -q "rm -v bbb222" "$STUB_LOG"; then fail "non-postgres container untouched"; else
  pass "non-postgres container untouched"; fi
assert_contains "$(cat "$STUB_LOG")" "docker volume prune -f" "unused volumes pruned"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES test(s) failed"; exit 1; fi
echo "all tests passed"
