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
branch="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T3']['branch'])")"
assert_equals "$branch" "worktree-t3" "branch recorded on in-review"

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

# ---- Deferred minors: stale-note clearing ------------------------------------
echo "board-transition (stale notes):"

# A note travels with the state that required it; the next move clears it.
run board-register.sh "Stale note ticket" bug --state blocked --note "waiting on API key" >/dev/null  # T13
note="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T13']['note'])")"
assert_equals "$note" "waiting on API key" "birth note stored"
run board-transition.sh T13 ready-for-agent >/dev/null
note="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T13']['note'])")"
assert_equals "$note" "None" "stale note cleared on the next transition"

# ---- Deferred minors: one-line titles, spoof-proof list rows -------------------
echo "board-register / board-list (one-line display):"

# A newline smuggled into a title or note must not spoof extra board-list rows.
out="$(run board-register.sh "$(printf 'Spoof\nT99 done bug FAKE')" enhancement)"   # T14
assert_contains "$out" "T14" "newline title registers"
title="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T14']['title'])")"
assert_equals "$title" "Spoof T99 done bug FAKE" "title normalized to one line at registration"
run board-transition.sh T14 blocked "$(printf 'line one\nline two')" >/dev/null
rows="$(run board-list.sh | wc -l | tr -d ' ')"
assert_equals "$rows" "14" "board-list prints exactly one row per ticket"
out="$(run board-list.sh blocked)"
assert_contains "$out" "line one line two" "multi-line note flattened, not truncated, in display"

assert_fails run board-register.sh "$(printf ' \n\t ')" bug     # whitespace-only title

# ---- board-map (minimal MD fallback + HTML graph) -----------------------------
echo "board-map:"

run board-register.sh "Map edge probe" enhancement --blocked-by T14 >/dev/null      # T15
run board-register.sh "Map lineage probe" enhancement --spawned-by T15 >/dev/null   # T16
run board-register.sh "Map epic child probe" enhancement --parent T16 >/dev/null    # T17

# Default stdout is now the graphless fallback table, not a mermaid block.
out="$(run board-map.sh)"
assert_contains "$out" "| ticket | state | title | PR |" "map stdout is the fallback table"
printf '%s' "$out" | grep -Fq '```mermaid' && fail "no mermaid in the fallback" || pass "no mermaid in the fallback"
echo "$out" | grep "T14" | grep -q "blocked" && pass "T14 row shows its state" || fail "T14 row shows its state"

run board-map.sh --write >/dev/null 2>&1
assert_file_exists "$BOARD/BOARD.md" "--write saves BOARD.md (fallback table)"
assert_file_exists "$BOARD/BOARD.html" "--write saves BOARD.html (graph)"
assert_contains "$(cat "$BOARD/BOARD.md")" "| T15 |" "BOARD.md table has a row per ticket"

# The graph facts that used to be asserted on the mermaid BOARD.md now live in BOARD.html.
html="$(tr -d ' \n\t' < "$BOARD/BOARD.html")"
assert_contains "$html" '"from":"T14","to":"T15","kind":"block-active"' "active block edge in BOARD.html"
assert_contains "$html" '"from":"T15","to":"T16","kind":"spawned"' "lineage edge in BOARD.html"
assert_contains "$html" '"id":"T16","descendants":["T17"]' "epic + child in BOARD.html"
assert_contains "$html" '"id":"T14","state":"blocked"' "state travels into BOARD.html"

# Every board WRITE auto-refreshes BOTH render caches — they cannot go stale.
run board-transition.sh T17 in-progress >/dev/null
assert_contains "$(tr -d ' \n\t' < "$BOARD/BOARD.html")" '"id":"T17","state":"in-progress"' \
    "a board write auto-refreshes BOARD.html"
assert_contains "$(cat "$BOARD/BOARD.md")" "in-progress" "a board write auto-refreshes BOARD.md"

# ---- board-relate (symmetric relates annotation) -------------------------------
echo "board-relate:"

run board-register.sh "Relate probe A" enhancement >/dev/null   # T18
run board-register.sh "Relate probe B" enhancement >/dev/null   # T19
out="$(run board-relate.sh T18 T19)"
assert_contains "$out" "related: T18 -- T19" "relate reports the new edge"
got="$(python3 -c "import json;t=json.load(open('$BOARD/map.json'))['tickets'];print(t['T18']['relates_to'],t['T19']['relates_to'])")"
assert_equals "$got" "['T19'] ['T18']" "relates edge stored on BOTH nodes"
assert_fails run board-relate.sh T18 T19            # duplicate
assert_fails run board-relate.sh T19 T18            # duplicate, reversed
assert_fails run board-relate.sh T18 T18            # self
assert_fails run board-relate.sh T18 T99            # unknown ref
run board-map.sh --write >/dev/null 2>&1
rel="$(tr -d ' \n\t' < "$BOARD/BOARD.html")"
assert_contains "$rel" '"from":"T18","to":"T19","kind":"relates"' "relate auto-refreshed BOARD.html"
printf '%s' "$rel" | grep -Fq '"from":"T19","to":"T18","kind":"relates"' \
    && fail "symmetric relate renders exactly once (no reverse dup)" \
    || pass "symmetric relate renders exactly once (no reverse dup)"
out="$(run board-relate.sh T19 T18 --cut)"          # cut works from either side
assert_contains "$out" "cut: T19 -- T18" "cut reported"
got="$(python3 -c "import json;t=json.load(open('$BOARD/map.json'))['tickets'];print(t['T18']['relates_to'],t['T19']['relates_to'])")"
assert_equals "$got" "[] []" "cut removed both sides"
assert_fails run board-relate.sh T18 T19 --cut      # nothing left to cut

# ---- board-edge (re-cut blocked_by / parent after birth) ------------------------
echo "board-edge:"

run board-register.sh "Edge blocker" enhancement >/dev/null        # T20
run board-register.sh "Edge dependent" enhancement >/dev/null      # T21
out="$(run board-edge.sh T21 --block T20)"
assert_contains "$out" "T21: blocked_by += T20" "block adds the edge"
run board-list.sh | grep "T21" | grep -q "waiting:T20" \
    && pass "T21 now waiting on T20" || fail "T21 now waiting on T20"
assert_contains "$(tr -d ' \n\t' < "$BOARD/BOARD.html")" '"from":"T20","to":"T21","kind":"block-active"' \
    "block auto-refreshed BOARD.html (active-block edge)"

assert_fails run board-edge.sh T21 --block T20        # duplicate
assert_fails run board-edge.sh T21 --block T21        # self
assert_fails run board-edge.sh T20 --block T21        # direct cycle
run board-register.sh "Edge transitive" enhancement --blocked-by T21 >/dev/null   # T22
assert_fails run board-edge.sh T20 --block T22        # transitive cycle T22→T21→T20
assert_fails run board-edge.sh T21 --block T99        # unknown ref
assert_fails run board-edge.sh T21 --block T20 --parent T22   # one op per call
assert_fails run board-edge.sh T21 --unblock T22      # not a blocker

out="$(run board-edge.sh T21 --unblock T20)"
assert_contains "$out" "T21: blocked_by -= T20" "unblock cuts the edge"
assert_contains "$out" "now eligible: T21" "unblock reports restored eligibility"

# ancestor-epic deadlock guard: a child may not block on its own epic
run board-register.sh "Edge epic" enhancement >/dev/null                      # T23
run board-register.sh "Edge epic child" enhancement --parent T23 >/dev/null   # T24
assert_fails run board-edge.sh T24 --block T23

# re-parent pulls the new epic chain when the moved child is in-progress
run board-transition.sh T24 in-progress >/dev/null    # pulls T23 in-progress too
run board-register.sh "Edge epic 2" enhancement >/dev/null                    # T25
run board-register.sh "Edge epic 2 child" enhancement --parent T25 >/dev/null # T26
out="$(run board-edge.sh T24 --parent T25)"
assert_contains "$out" "T24: parent = T25 (was T23)" "re-parent recorded"
assert_contains "$out" "T25: ready-for-agent → in-progress" "in-progress child pulls its new epic"

assert_fails run board-edge.sh T25 --parent T24       # cycle: T25 is T24's ancestor
assert_fails run board-edge.sh T25 --parent T25       # self
assert_fails run board-edge.sh T24 --parent T25       # already the parent

# leaving an epic can close it: T27 epic, kids T28 (done) + T29 (leaver)
run board-register.sh "Edge close epic" enhancement >/dev/null                    # T27
run board-register.sh "Edge close done kid" enhancement --parent T27 >/dev/null   # T28
run board-register.sh "Edge close leaver" enhancement --parent T27 >/dev/null     # T29
run board-transition.sh T28 in-progress >/dev/null
run board-transition.sh T28 "done" >/dev/null         # T27 stays open: T29 not terminal
st="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['T27']['state'])")"
assert_equals "$st" "in-progress" "epic still open while a child remains active"
out="$(run board-edge.sh T29 --orphan)"
assert_contains "$out" "T29: parent cleared (was T27)" "orphan recorded"
assert_contains "$out" "T27: in-progress → done" "last active child leaving closes the epic"
assert_fails run board-edge.sh T29 --orphan           # no parent to clear

# edge mutations are audited in log.jsonl with an "edge" key
grep -q '"edge": "blocked_by"' "$BOARD/log.jsonl" && pass "blocked_by mutations logged" || fail "blocked_by mutations logged"
grep -q '"edge": "parent"' "$BOARD/log.jsonl" && pass "parent mutations logged" || fail "parent mutations logged"
grep -q '"edge": "relates_to"' "$BOARD/log.jsonl" && pass "relates mutations logged" || fail "relates mutations logged"

# a missing option operand dies cleanly, naming the option
err="$( { run board-edge.sh T21 --block; } 2>&1 1>/dev/null || true )"
assert_contains "$err" "--block" "missing operand names the option"

# ---- board-map (interactive HTML) --------------------------------------------
# Fresh probes with known states so assertions don't depend on the board's
# accumulated end-state. Highest ticket so far is T29 → T30 next.
echo "board-map (html):"

run board-register.sh "HTML blocker" enhancement >/dev/null                        # T30
run board-register.sh "HTML dependent" enhancement --blocked-by T30 >/dev/null      # T31
run board-register.sh "HTML spawned child" enhancement --spawned-by T31 >/dev/null  # T32
run board-register.sh "HTML epic" enhancement >/dev/null                            # T33
run board-register.sh "HTML epic child" enhancement --parent T33 >/dev/null         # T34
run board-relate.sh T30 T32 >/dev/null

run board-map.sh --write >/dev/null 2>&1
assert_file_exists "$BOARD/BOARD.html" "--write saves BOARD.html in the board dir"

# Whitespace-stripped view lets us grep the injected JSON as compact substrings.
# (Explicit ' \n\t' — BSD tr does not treat [:space:] as a class.)
html="$(tr -d ' \n\t' < "$BOARD/BOARD.html")"
assert_contains "$html" '"id":"T31","state":"ready-for-agent"' "node T31 present with its state"
assert_contains "$html" '"from":"T30","to":"T31","kind":"block-active"' "active block edge in payload"
assert_contains "$html" '"label":"waiting:T30"' "T31 carries the unmet-blocker label"
assert_contains "$html" '"from":"T31","to":"T32","kind":"spawned"' "spawned lineage edge in payload"
assert_contains "$html" '"from":"T30","to":"T32","kind":"relates"' "relates edge in payload (single direction)"
printf '%s' "$html" | grep -Fq '"from":"T32","to":"T30","kind":"relates"' \
    && fail "relates edge de-duplicated to one direction" || pass "relates edge de-duplicated to one direction"
assert_contains "$html" '"id":"T33","descendants":["T34"]' "epic T33 lists its descendant"
assert_contains "$html" '"id":"T31","state":"ready-for-agent","eligible":false' "blocked dependent is not eligible"

# Self-contained: no external references anywhere in the file.
ext="$(grep -Eic 'src="https?://|href="https?://[^"]*\.css|cdnjs|unpkg|jsdelivr' "$BOARD/BOARD.html" || true)"
assert_equals "$ext" "0" "BOARD.html has no external references (self-contained)"

# block-done appears once the blocker lands.
run board-transition.sh T30 in-progress >/dev/null
run board-transition.sh T30 "done" >/dev/null
run board-map.sh --write >/dev/null 2>&1
html="$(tr -d ' \n\t' < "$BOARD/BOARD.html")"
assert_contains "$html" '"from":"T30","to":"T31","kind":"block-done"' "satisfied block flips to block-done"
assert_contains "$html" '"id":"T31","state":"ready-for-agent","eligible":true' "dependent becomes eligible once blocker is done"

# The template token was fully substituted.
printf '%s' "$html" | grep -Fq '__BOARD_PAYLOAD__' \
    && fail "payload token fully substituted" || pass "payload token fully substituted"

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
