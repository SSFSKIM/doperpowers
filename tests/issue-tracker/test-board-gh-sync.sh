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

# ---- Task 5: board-gh-apply.sh — apply the plan + refresh the watermark -----
echo "board-gh-apply (dry-run):"
run board-gh-plan.sh --gh-json "$TEST_ROOT/gh.json" > "$TEST_ROOT/plan.json"
map_before="$(cat "$BOARD/map.json")"
out="$(run board-gh-apply.sh --plan "$TEST_ROOT/plan.json" --dry-run)"
assert_contains "$out" "gh: issue close 101 --reason completed" "dry-run plans the board->gh close"
assert_contains "$out" "board-transition.sh $B wontfix" "dry-run plans the gh->board wontfix"
assert_equals "$(cat "$BOARD/map.json")" "$map_before" "dry-run writes nothing to the board"
[ -f "$BOARD/.sync-state.json.tmp" ] && fail "dry-run no watermark tmp" || pass "dry-run leaves no watermark tmp"

echo "board-gh-apply (board side):"
# Apply only the gh->board wontfix for B by feeding a filtered plan (board side, no gh calls).
python3 - "$TEST_ROOT/plan.json" "$TEST_ROOT/plan-b.json" "$B" <<'PY'
import json,sys
src,dst,B=sys.argv[1:4]
p=json.load(open(src))
p["actions"]=[a for a in p["actions"] if a["ticket"]==B]
json.dump(p,open(dst,"w"))
PY
run board-gh-apply.sh --plan "$TEST_ROOT/plan-b.json" --no-github
st="$(python3 -c "import json;print(json.load(open('$BOARD/map.json'))['tickets']['$B']['state'])")"
assert_equals "$st" "wontfix" "gh->board wontfix applied to the board via board-transition"
wm="$(python3 -c "import json;print(json.load(open('$BOARD/.sync-state.json'))['tickets']['$B']['state'])")"
assert_equals "$wm" "wontfix" "watermark refreshed to the reconciled board state"

# ---- Task 5 regression: filtered-plan safety ---------------------------------
# The bug this guards: apply's watermark refresh used to re-walk ALL of map.json
# and stamp every linked, non-conflict ticket — so a ticket whose action was held
# back (filtered OUT of the plan handed to apply) still got its watermark set to
# its *current* board state, falsely recording a sync that never happened. The
# fix makes the refresh set plan-driven: only tickets with an auto/non-conflict
# action in the plan, plus the plan's "agree" set, get touched.
echo "board-gh-apply (filtered-plan safety):"
run board-register.sh "Filter safety A" enhancement >/dev/null
FA="$(run board-list.sh | grep 'Filter safety A' | awk '{print $1}')"
run board-transition.sh "$FA" in-progress >/dev/null
run board-transition.sh "$FA" done >/dev/null                        # board done, gh still open
run board-meta.sh "$FA" --gh 201 >/dev/null
run board-register.sh "Filter safety B" enhancement >/dev/null
FB="$(run board-list.sh | grep 'Filter safety B' | awk '{print $1}')"
run board-transition.sh "$FB" in-progress >/dev/null                  # done-reachable
run board-meta.sh "$FB" --gh 202 >/dev/null

cat > "$TEST_ROOT/gh2.json" <<JSON
[ {"number":201,"state":"OPEN","stateReason":null,"labels":[],"body":"","title":"fa"},
  {"number":202,"state":"CLOSED","stateReason":"not_planned","labels":[],"body":"","title":"fb"} ]
JSON
# FB gets a watermark baseline so its diff is a clean auto gh->board action. FA
# is deliberately left with NO prior watermark entry at all — it never has been
# synced, and it is about to be held back by the filter below, so it must come
# out of this apply exactly as it went in: absent from .sync-state.json.
python3 - "$BOARD/.sync-state.json" "$FB" <<'PY'
import json,sys
p,FB=sys.argv[1:3]
d=json.load(open(p))
d["tickets"][FB]={"gh":202,"state":"in-progress"}
json.dump(d,open(p,"w"))
PY
run board-gh-plan.sh --gh-json "$TEST_ROOT/gh2.json" > "$TEST_ROOT/plan2.json"
python3 -c "
import json
p = json.load(open('$TEST_ROOT/plan2.json'))
a = {x['ticket']: x for x in p['actions']}
assert a['$FB']['direction'] == 'gh->board' and a['$FB']['auto'], 'expected FB auto gh->board action'
assert '$FA' not in p.get('agree', []), 'FA must not silently agree in this fixture'
print('fixture-ok')
"
# Filter the plan down to ONLY FB's action (FA's action/absence is held back —
# this is the exact "confirmed subset" scenario the spec allows), and drop FA
# from "agree" too (defensively) so only FB survives anywhere in the plan.
python3 - "$TEST_ROOT/plan2.json" "$TEST_ROOT/plan2-fb.json" "$FA" "$FB" <<'PY'
import json,sys
src,dst,FA,FB=sys.argv[1:5]
p=json.load(open(src))
p["actions"]=[a for a in p["actions"] if a["ticket"]==FB]
p["agree"]=[t for t in p.get("agree",[]) if t != FA]
json.dump(p,open(dst,"w"))
PY
run board-gh-apply.sh --plan "$TEST_ROOT/plan2-fb.json" --no-github >/dev/null
has_fa="$(python3 -c "import json;print('$FA' in json.load(open('$BOARD/.sync-state.json'))['tickets'])")"
assert_equals "$has_fa" "False" "ticket held back from a filtered plan gets NO watermark entry (regression guard)"

# ---- Task 5 regression: conflicted tickets keep their prior watermark --------
echo "board-gh-apply (conflict keeps watermark):"
run board-register.sh "Conflict ticket" enhancement >/dev/null
FC="$(run board-list.sh | grep 'Conflict ticket' | awk '{print $1}')"
run board-meta.sh "$FC" --gh 999 >/dev/null
python3 - "$BOARD/.sync-state.json" "$FC" <<'PY'
import json,sys
p,FC=sys.argv[1:3]
d=json.load(open(p))
d["tickets"][FC]={"gh":999,"state":"seeded-state","labels":["keep-me"]}
json.dump(d,open(p,"w"))
PY
seeded_before="$(python3 -c "import json;print(json.dumps(json.load(open('$BOARD/.sync-state.json'))['tickets']['$FC'], sort_keys=True))")"
cat > "$TEST_ROOT/plan-conflict.json" <<JSON
{"generated_by": "test", "actions": [
  {"ticket": "$FC", "gh": 999, "facet": "state", "conflict": true, "auto": false,
   "board": "ready-for-agent", "gh_state": null, "watermark": "seeded-state",
   "reason": "test conflict"}
], "agree": [], "unlinked_board": [], "unlinked_gh": []}
JSON
run board-gh-apply.sh --plan "$TEST_ROOT/plan-conflict.json" --no-github >/dev/null
seeded_after="$(python3 -c "import json;print(json.dumps(json.load(open('$BOARD/.sync-state.json'))['tickets']['$FC'], sort_keys=True))")"
assert_equals "$seeded_after" "$seeded_before" "conflicted ticket's watermark entry is left unchanged"

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
