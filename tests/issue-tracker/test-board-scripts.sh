#!/usr/bin/env bash
#
# Hermetic tests for the issue-tracker board toolkit.
#
# The board scripts touch only the filesystem (a git repo's main checkout, the
# board data dir, and the daemon registry dir) — no network, no `claude` CLI.
# We build a throwaway git repo + worktree and a fake daemon registry, drive
# the real scripts end-to-end, and assert on map.json / log.jsonl / output.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/issue-tracker/scripts"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() {
    echo "  [FAIL] $1"
    FAILURES=$((FAILURES + 1))
}
assert_equals() {
    if [[ "$1" == "$2" ]]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
assert_fails() { # cmd... — passes when the command exits non-zero
    if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; else pass "refused: $*"; fi
}

# ---- environment: throwaway git repo + worktree, fake daemon registry -------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
WORK="$TEST_ROOT/work"
git init -q "$WORK"
git -C "$WORK" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$WORK" worktree add -q -b t-branch "$TEST_ROOT/wt"
BOARD="$WORK/doperpowers/issue-tracker"

run() { # run a board script from the main checkout
    local s="$1"; shift
    (cd "$WORK" && "$SCRIPTS_DIR/$s" "$@")
}

# ---- Task 1: register + lazy init + worktree guard ---------------------------
echo "board-register:"

out="$(run board-register.sh "Worktree map viewer" enhancement)"
assert_equals "$out" "T1 tickets/T1-worktree-map-viewer.md" "first register returns T1 + slug md path"
assert_file_exists "$BOARD/map.json" "lazy init created map.json"
assert_file_exists "$BOARD/log.jsonl" "birth logged to log.jsonl"
state="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T1']['state'])")"
assert_equals "$state" "ready-for-agent" "default birth state is ready-for-agent"

out="$(run board-register.sh "Deferred idea" bug --state deferred)"
assert_contains "$out" "T2" "second register allocates T2"

out="$(run board-register.sh "Child slice" enhancement --parent T1 --blocked-by T2)"
assert_contains "$out" "T3" "third register allocates T3"
parent="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['parent'])")"
assert_equals "$parent" "T1" "parent edge stored"

loglines="$(wc -l < "$BOARD/log.jsonl" | tr -d ' ')"
assert_equals "$loglines" "3" "log.jsonl has exactly 3 lines after the three registers"

out="$(run board-register.sh "Needs more detail" bug --state needs-info --note "what info")"
assert_contains "$out" "T4" "needs-info with --note succeeds (T4)"

out="$(run board-register.sh "This is a very long ticket title that should be truncated in the slug" enhancement)"
assert_equals "$out" "T5 tickets/T5-this-is-a-very-long-ticket-title-that-sh.md" "long title slug capped at 40 chars"

assert_fails run board-register.sh "Bad" gadget                       # bad category
assert_fails run board-register.sh "Bad" bug --state blocked          # blocked without note
assert_fails run board-register.sh "Bad" bug --parent T99             # dangling ref
assert_fails run board-register.sh "Bad" bug --state in-progress      # not a birth state

(cd "$TEST_ROOT/wt" && "$SCRIPTS_DIR/board-register.sh" "From worktree" bug) \
    >/dev/null 2>&1 && fail "worktree guard" || pass "refused to run from a worktree"

[ -f "$BOARD/map.json.tmp" ] && fail "no tmp litter" || pass "no tmp litter after writes"

# ---- Task 2: transition legality, notes, sweeps, log --------------------------
echo "board-transition:"

# Board so far: T1 ready (epic-to-be), T2 deferred, T3 ready (parent T1, blocked_by T2)
assert_fails run board-transition.sh T1 "done"               # illegal ready→done
assert_fails run board-transition.sh T1 blocked              # note required
assert_fails run board-transition.sh T1 ready-for-agent      # same-state
assert_fails run board-transition.sh T99 "done"              # unknown ticket
assert_fails run board-transition.sh T1 shipping             # unknown state

out="$(run board-transition.sh T3 in-progress)"
assert_contains "$out" "T3: ready-for-agent → in-progress" "transition applied"
assert_contains "$out" "T1: ready-for-agent → in-progress" "epic parent pulled to in-progress"

out="$(run board-transition.sh T3 in-review "" --branch worktree-t3 --pr "PR#12")"
pr="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['pr'])")"
assert_equals "$pr" "PR#12" "pr recorded on in-review"

out="$(run board-transition.sh T2 ready-for-agent)"    # revive the deferred blocker
out="$(run board-transition.sh T2 in-progress)"
out="$(run board-transition.sh T2 "done")"
assert_contains "$out" "T2: in-progress → done" "blocker done"

out="$(run board-transition.sh T3 "done")"
assert_contains "$out" "T1: in-progress → done" "epic auto-closed when all children terminal"

# done unblocks dependents: T7 blocked_by the not-yet-done T6
run board-register.sh "Blocker" bug >/dev/null                       # T6
run board-register.sh "Dependent" bug --blocked-by T6 >/dev/null     # T7
run board-transition.sh T6 in-progress >/dev/null
out="$(run board-transition.sh T6 "done")"
assert_contains "$out" "now eligible: T7" "done sweep reports newly eligible dependents"

lines="$(wc -l < "$BOARD/log.jsonl" | tr -d ' ')"
assert_equals "$lines" "17" "every applied change logged (7 births + 10 transitions)"

# ---- Task 3: list + show ------------------------------------------------------
echo "board-list / board-show:"

# Fresh eligible ticket + a blocked-by-live-ticket dependent
run board-register.sh "Solo ready" enhancement >/dev/null            # T8
run board-register.sh "Waiting on T8" bug --blocked-by T8 >/dev/null # T9

out="$(run board-list.sh)"
assert_contains "$out" "T8" "list shows all tickets"
echo "$out" | grep "T8" | grep -q "ELIGIBLE" && pass "T8 eligible" || fail "T8 eligible"
echo "$out" | grep "T9" | grep -q "waiting:T8" && pass "T9 waiting on T8" || fail "T9 waiting on T8"
echo "$out" | grep "T1 " | grep -q "epic" && pass "T1 tagged epic" || fail "T1 tagged epic"

out="$(run board-list.sh "done")"
assert_contains "$out" "T2" "state filter shows done tickets"
echo "$out" | grep -q "T8" && fail "filter excludes others" || pass "filter excludes others"

out="$(run board-show.sh T8)"
assert_contains "$out" "Solo ready" "show prints the node"
assert_contains "$out" "(none bound)" "show reports no bound daemon"

# Fake a bound daemon in the registry, then show finds it
cat > "$DAEMON_HOME/aaaa1111-0000-0000-0000-000000000001.json" <<'META'
{"uuid": "aaaa1111-0000-0000-0000-000000000001", "short": "aaaa1111",
 "name": "t8-worker", "status": "idle", "cwd": "/tmp/x", "worktree": "t8",
 "ticket": "T8"}
META
out="$(run board-show.sh T8)"
assert_contains "$out" "aaaa1111" "show finds the bound daemon"

assert_fails run board-show.sh T99

# A stray tmp from an interrupted write is ignored by readers (atomicity).
touch "$BOARD/map.json.tmp"
run board-list.sh >/dev/null && pass "stray map.json.tmp ignored" || fail "stray map.json.tmp ignored"
rm -f "$BOARD/map.json.tmp"

# ---- Task 4: bind + reconcile --------------------------------------------------
echo "board-bind / board-reconcile:"

cat > "$DAEMON_HOME/bbbb2222-0000-0000-0000-000000000002.json" <<'META'
{"uuid": "bbbb2222-0000-0000-0000-000000000002", "short": "bbbb2222",
 "name": "t9-worker", "status": "idle", "cwd": "/tmp/y", "worktree": "t9"}
META
out="$(run board-bind.sh bbbb2222 T9)"
assert_contains "$out" "bound T9" "bind reports success"
tk="$(python3 -c "import json;print(json.load(open('$DAEMON_HOME/bbbb2222-0000-0000-0000-000000000002.json'))['ticket'])")"
assert_equals "$tk" "T9" "bind wrote the ticket key into daemon meta"
assert_fails run board-bind.sh bbbb2222 T99          # unknown ticket
assert_fails run board-bind.sh zzzz9999 T9           # no matching daemon

# Reconcile case 1: a proposal in a reply that the board hasn't applied.
run board-transition.sh T8 in-progress >/dev/null
cat > "$DAEMON_HOME/aaaa1111-0000-0000-0000-000000000001.reply.txt" <<'REPLY'
Build finished; PR opened.
{"ticket":"T8","from":"in-progress","to":"in-review","reason":"build done","evidence":"PR #9"}
REPLY
# Reconcile case 2: in-progress with no bound daemon.
run board-transition.sh T9 in-progress >/dev/null
rm "$DAEMON_HOME/bbbb2222-0000-0000-0000-000000000002.json"

out="$(run board-reconcile.sh)"
assert_contains "$out" "proposal  T8: in-progress → in-review" "reconcile surfaces the unapplied proposal"
assert_contains "$out" "board-transition.sh T8 in-review" "reconcile prints the apply command"
assert_contains "$out" "orphaned  T9" "reconcile flags in-progress ticket with no daemon"

map_before="$(cat "$BOARD/map.json")"
run board-reconcile.sh >/dev/null
assert_equals "$(cat "$BOARD/map.json")" "$map_before" "reconcile never writes the board"

# ---- Task 5: review findings — PR-gated in-review, in-review→deferred, --------
#              hardened reconcile, option-arity guard.
# All new activity is appended AFTER the last log-count assertion, so those
# earlier counts stay valid. Highest ticket registered so far is T9 → T10 next.
echo "board-transition / board-reconcile (review findings):"

# in-review → deferred is legal (spec's "any → deferred"): register a fresh
# ticket, drive it in-progress → in-review (--pr) → deferred.
run board-register.sh "Review-cycle ticket" enhancement >/dev/null   # T10
run board-transition.sh T10 in-progress >/dev/null
out="$(run board-transition.sh T10 in-review --pr "PR#T10")"
assert_contains "$out" "T10: in-progress → in-review" "in-progress → in-review recorded with --pr"
out="$(run board-transition.sh T10 deferred)"
assert_contains "$out" "T10: in-review → deferred" "in-review → deferred is legal"

# Moving to in-review WITHOUT --pr is refused (a PR link is mandatory).
run board-register.sh "Needs a PR link" bug >/dev/null               # T11
run board-transition.sh T11 in-progress >/dev/null
assert_fails run board-transition.sh T11 in-review

# A malformed daemon meta (ticket that isn't a real board ticket) must not
# crash reconcile — it is the wake-up recovery path. Reconcile stays exit 0
# and reports the anomaly by name.
cat > "$DAEMON_HOME/cccc3333-0000-0000-0000-000000000003.json" <<'META'
{"uuid": "cccc3333-0000-0000-0000-000000000003", "short": "cccc3333",
 "name": "ghost", "status": "idle", "cwd": "/tmp/z", "worktree": "z",
 "ticket": "bogus"}
META
if out="$(run board-reconcile.sh)"; then pass "reconcile survives malformed daemon meta (exit 0)"; else
    fail "reconcile survives malformed daemon meta (exit 0)"; fi
assert_contains "$out" "anomaly" "reconcile reports an anomaly for the malformed meta"
assert_contains "$out" "bogus" "reconcile names the bogus ticket instead of crashing"

# Hostile proposal evidence (daemon reply text is semi-trusted) must come out
# shell-safe in the printed apply hint — shlex single-quotes it, so `"`, $()
# and backticks can't inject if the orchestrator runs the hint verbatim.
cat > "$DAEMON_HOME/dddd4444-0000-0000-0000-000000000004.json" <<'META'
{"uuid": "dddd4444-0000-0000-0000-000000000004", "short": "dddd4444",
 "name": "t11-worker", "status": "idle", "cwd": "/tmp/w", "worktree": "w",
 "ticket": "T11"}
META
cat > "$DAEMON_HOME/dddd4444-0000-0000-0000-000000000004.reply.txt" <<'REPLY'
Opened the PR.
{"ticket":"T11","from":"in-progress","to":"in-review","reason":"done","evidence":"PR \"x\" $(rm -rf /) `boom`"}
REPLY
if out="$(run board-reconcile.sh)"; then pass "reconcile survives hostile evidence (exit 0)"; else
    fail "reconcile survives hostile evidence (exit 0)"; fi
assert_contains "$out" "proposal  T11: in-progress → in-review" "hostile-evidence proposal still surfaced"
assert_contains "$out" "--pr 'PR \"x\" \$(rm -rf /) \`boom\`'" "apply hint single-quotes the evidence (shlex-safe)"

# A hostile proposed *state* must never reach the paste-able apply hint.
# States are a closed set, so an unknown `to` is whitelisted out and reported
# as an anomaly (safe %r repr) — no proposal line, no hint at all.
run board-register.sh "Hostile state proposal" bug >/dev/null        # T12
run board-transition.sh T12 in-progress >/dev/null
cat > "$DAEMON_HOME/eeee5555-0000-0000-0000-000000000005.json" <<'META'
{"uuid": "eeee5555-0000-0000-0000-000000000005", "short": "eeee5555",
 "name": "t12-worker", "status": "idle", "cwd": "/tmp/v", "worktree": "v",
 "ticket": "T12"}
META
cat > "$DAEMON_HOME/eeee5555-0000-0000-0000-000000000005.reply.txt" <<'REPLY'
Done, promise.
{"ticket":"T12","from":"in-progress","to":"in-review; rm -rf ~","reason":"pwn","evidence":"x"}
REPLY
if out="$(run board-reconcile.sh)"; then pass "reconcile survives hostile proposed state (exit 0)"; else
    fail "reconcile survives hostile proposed state (exit 0)"; fi
assert_contains "$out" "anomaly   T12: daemon proposes unknown state 'in-review; rm -rf ~'" \
    "hostile state reported as anomaly with safe repr"
printf '%s' "$out" | grep -Fq "apply: board-transition.sh T12" \
    && fail "no apply hint for hostile-state proposal" || pass "no apply hint for hostile-state proposal"

# A missing option operand dies cleanly, naming the option (not a raw set -u
# unbound-variable error).
err="$( { run board-transition.sh T11 in-progress --branch; } 2>&1 1>/dev/null || true )"
assert_contains "$err" "--branch" "missing option operand names the option in the error"
assert_fails run board-transition.sh T11 in-progress --branch

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
