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

# ---- Task 1: register writes additive gh/labels node fields -----------------
echo "board-register (sync fields):"
out="$(run board-register.sh "First ticket" enhancement)"
tid="$(printf '%s' "$out" | awk '{print $1}')"
gh="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid'].get('gh','MISSING'))")"
assert_equals "$gh" "None" "new ticket has gh field defaulting to null"
labels="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid'].get('labels','MISSING'))")"
assert_equals "$labels" "[]" "new ticket has labels field defaulting to []"

# ---- Task 2: board-meta.sh writes gh link + free labels ---------------------
echo "board-meta:"
run board-register.sh "Meta target" enhancement >/dev/null           # next Tn
tid="$(run board-list.sh | grep 'Meta target' | awk '{print $1}')"
out="$(run board-meta.sh "$tid" --gh 42)"
assert_contains "$out" "$tid: gh = 42" "meta sets gh"
gh="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid']['gh'])")"
assert_equals "$gh" "42" "gh written as integer"
run board-meta.sh "$tid" --add-label P0 --add-label size:M >/dev/null
run board-meta.sh "$tid" --add-label P0 >/dev/null                    # idempotent
labels="$(python3 -c "import json;print(','.join(json.load(open('$BOARD/map.json'))['tickets']['$tid']['labels']))")"
assert_equals "$labels" "P0,size:M" "labels added once, order preserved"
run board-meta.sh "$tid" --rm-label P0 >/dev/null
labels="$(python3 -c "import json;print(','.join(json.load(open('$BOARD/map.json'))['tickets']['$tid']['labels']))")"
assert_equals "$labels" "size:M" "label removed"
run board-meta.sh "$tid" --gh 0 >/dev/null
gh="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid']['gh'])")"
assert_equals "$gh" "None" "gh 0 clears the link"
assert_fails run board-meta.sh T999 --gh 1                            # unknown ticket
assert_fails run board-meta.sh "$tid" --gh notanumber                # non-integer

# ---- Task 3: board-link.sh — gh sugar + one-time title backfill -------------
echo "board-link (backfill):"
run board-register.sh "Legacy epic (GH#35)" enhancement >/dev/null
tid_backfilled="$(run board-list.sh | grep 'Legacy epic' | awk '{print $1}')"
run board-register.sh "No marker here" bug >/dev/null
out="$(run board-link.sh --backfill)"
assert_contains "$out" "gh = 35 (from title)" "backfill parses GH#NN from title"
n="$(python3 -c "import json;t=json.load(open('$BOARD/map.json'))['tickets'];print(sum(1 for x in t.values() if x.get('gh')==35))")"
assert_equals "$n" "1" "exactly one ticket linked to #35"
# a ticket without a marker stays unlinked
un="$(python3 -c "import json;t=json.load(open('$BOARD/map.json'))['tickets'];print([x['gh'] for x in t.values() if x['title']=='No marker here'][0])")"
assert_equals "$un" "None" "markerless ticket stays unlinked"
# backfill appends an audit entry to log.jsonl, same shape as board-meta's
logged="$(grep -F "\"ticket\": \"$tid_backfilled\"" "$BOARD/log.jsonl" | grep -F '"meta": "gh"' | grep -c '"op": "set"' || true)"
assert_equals "$logged" "1" "backfill appends a gh log entry"
# re-running backfill does not overwrite an existing link
run board-link.sh --backfill >/dev/null

# ---- board-link.sh — <id> --gh N sugar delegates to board-meta.sh -----------
echo "board-link (--gh sugar):"
run board-register.sh "Sugar target" enhancement >/dev/null
tid_sugar="$(run board-list.sh | grep 'Sugar target' | awk '{print $1}')"
run board-link.sh "$tid_sugar" --gh 7 >/dev/null
gh_sugar="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$tid_sugar']['gh'])")"
assert_equals "$gh_sugar" "7" "board-link --gh sugar sets gh via board-meta delegation"

# ---- Task 4: board-gh-plan.sh — deterministic state reconcile diff ----------
echo "board-gh-plan:"
# scratch board: 4 tickets, drive states, link to issues
run board-register.sh "Completion push" enhancement >/dev/null        # A
A="$(run board-list.sh | grep 'Completion push' | awk '{print $1}')"
run board-transition.sh "$A" in-progress >/dev/null
run board-transition.sh "$A" done >/dev/null                          # board done, issue still open
run board-meta.sh "$A" --gh 101 >/dev/null
run board-register.sh "GH closed it" enhancement >/dev/null           # B
B="$(run board-list.sh | grep 'GH closed it' | awk '{print $1}')"
run board-transition.sh "$B" in-progress >/dev/null                   # done-reachable
run board-meta.sh "$B" --gh 102 >/dev/null
run board-register.sh "Already agree" enhancement >/dev/null          # C  (open ↔ open)
C="$(run board-list.sh | grep 'Already agree' | awk '{print $1}')"
run board-meta.sh "$C" --gh 103 >/dev/null
run board-register.sh "Unlinked local" bug >/dev/null                 # D  (no gh)
D="$(run board-list.sh | grep 'Unlinked local' | awk '{print $1}')"

cat > "$TEST_ROOT/gh.json" <<JSON
[ {"number":101,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"x"},
  {"number":102,"state":"CLOSED","stateReason":"not_planned","labels":[],"body":"","title":"y"},
  {"number":103,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"z"},
  {"number":900,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"orphan"} ]
JSON
# empty watermark → C already agrees (no action); A/B each moved on one side only
: > "$BOARD/.sync-state.json"; echo '{"version":1,"tickets":{}}' > "$BOARD/.sync-state.json"
python3 - "$BOARD/.sync-state.json" "$A" "$B" "$C" <<'PY'
import json,sys
p,A,B,C=sys.argv[1:5]
d=json.load(open(p))
d["tickets"]={A:{"gh":101,"state":"in-progress"},B:{"gh":102,"state":"in-progress"},C:{"gh":103,"state":"ready-for-agent"}}
json.dump(d,open(p,"w"))
PY
plan="$(run board-gh-plan.sh --gh-json "$TEST_ROOT/gh.json")"
assert_contains "$plan" "\"ticket\": \"$A\"" "plan includes the board-moved ticket"
printf '%s' "$plan" | python3 -c "import json,sys;p=json.load(sys.stdin);a={x['ticket']:x for x in p['actions']}; import os
A,B,C,D='$A','$B','$C','$D'
assert a[A]['direction']=='board->gh' and a[A]['auto'] and a[A]['target_gh'][0]=='closed', 'A board->gh close'
assert a[B]['direction']=='gh->board' and a[B]['auto'] and a[B]['target_board'][0]=='wontfix', 'B gh->board wontfix'
assert C not in a, 'C already agrees, no action'
assert D in p['unlinked_board'], 'D unlinked_board'
assert 900 in p['unlinked_gh'], 'orphan open issue surfaced'
print('plan-assertions-ok')" && pass "plan diff correct each direction" || fail "plan diff correct each direction"

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
