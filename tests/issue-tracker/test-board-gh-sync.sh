#!/usr/bin/env bash
#
# Hermetic tests for the issue-tracker board toolkit.
#
# The board scripts touch only the filesystem (a git repo's main checkout, the
# board data dir, and the daemon registry dir) — no network, no `claude` CLI.
# We build a throwaway git repo + worktree and a fake daemon registry, drive
# the real scripts end-to-end, and assert on board.json / log.jsonl / output.
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
gh="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$tid'].get('gh','MISSING'))")"
assert_equals "$gh" "None" "new ticket has gh field defaulting to null"
labels="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$tid'].get('labels','MISSING'))")"
assert_equals "$labels" "[]" "new ticket has labels field defaulting to []"

# ---- Task 2: board-meta.sh writes gh link + free labels ---------------------
echo "board-meta:"
run board-register.sh "Meta target" enhancement >/dev/null           # next Tn
tid="$(run board-list.sh | grep 'Meta target' | awk '{print $1}')"
out="$(run board-meta.sh "$tid" --gh 42)"
assert_contains "$out" "$tid: gh = 42" "meta sets gh"
gh="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$tid']['gh'])")"
assert_equals "$gh" "42" "gh written as integer"
run board-meta.sh "$tid" --add-label P0 --add-label size:M >/dev/null
run board-meta.sh "$tid" --add-label P0 >/dev/null                    # idempotent
labels="$(python3 -c "import json;print(','.join(json.load(open('$BOARD/board.json'))['tickets']['$tid']['labels']))")"
assert_equals "$labels" "P0,size:M" "labels added once, order preserved"
run board-meta.sh "$tid" --rm-label P0 >/dev/null
labels="$(python3 -c "import json;print(','.join(json.load(open('$BOARD/board.json'))['tickets']['$tid']['labels']))")"
assert_equals "$labels" "size:M" "label removed"
run board-meta.sh "$tid" --gh 0 >/dev/null
gh="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$tid']['gh'])")"
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
n="$(python3 -c "import json;t=json.load(open('$BOARD/board.json'))['tickets'];print(sum(1 for x in t.values() if x.get('gh')==35))")"
assert_equals "$n" "1" "exactly one ticket linked to #35"
# a ticket without a marker stays unlinked
un="$(python3 -c "import json;t=json.load(open('$BOARD/board.json'))['tickets'];print([x['gh'] for x in t.values() if x['title']=='No marker here'][0])")"
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
gh_sugar="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$tid_sugar']['gh'])")"
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

# ---- board-gh-plan.sh — explicit `--gh-json -` reads stdin, same as FILE ----
# Bare (no --gh-json) used to fall into an implicit "read stdin if non-TTY"
# branch — under cron/subagent Bash (always non-TTY) a bare call would read
# zero bytes and silently treat GitHub as empty. The fix requires stdin be
# opted into explicitly via `--gh-json -`; this proves that seam still works
# and produces byte-identical output to the file seam for the same data.
echo "board-gh-plan (--gh-json - stdin seam):"
plan_stdin="$(cat "$TEST_ROOT/gh.json" | run board-gh-plan.sh --gh-json -)"
assert_equals "$plan_stdin" "$plan" "--gh-json - (stdin) matches --gh-json FILE for the same input"

# ---- Task 4 regression: done ticket must not become an illegal wontfix -----
# The bug this guards: when the board is terminal `done` and GitHub closes the
# linked issue as not_planned, plan used to emit an auto:true gh->board wontfix
# action — but `done` has no legal transitions (LEGAL["done"] is empty in
# board-transition.sh), so apply would die mid-loop applying it on a cron run.
# The fix forces this specific combination to a conflict instead of an auto
# action, and apply must then leave the ticket untouched.
echo "board-gh-plan (done + gh not_planned → conflict, not auto wontfix):"
run board-register.sh "Done vs not_planned" enhancement >/dev/null
E="$(run board-list.sh | grep 'Done vs not_planned' | awk '{print $1}')"
run board-transition.sh "$E" in-progress >/dev/null
run board-transition.sh "$E" done >/dev/null                          # board terminal: done
run board-meta.sh "$E" --gh 200 >/dev/null
python3 - "$BOARD/.sync-state.json" "$E" <<'PY'
import json,sys
p,E=sys.argv[1:3]
d=json.load(open(p))
d["tickets"][E]={"gh":200,"state":"done"}
json.dump(d,open(p,"w"))
PY
cat > "$TEST_ROOT/gh-donewontfix.json" <<JSON
[ {"number":200,"state":"CLOSED","stateReason":"not_planned","labels":[],"title":"e"} ]
JSON
run board-gh-plan.sh --gh-json "$TEST_ROOT/gh-donewontfix.json" > "$TEST_ROOT/plan-e.json"
python3 -c "
import json
p = json.load(open('$TEST_ROOT/plan-e.json'))
a = {x['ticket']: x for x in p['actions']}
act = a['$E']
assert act['auto'] is False, 'expected auto:false, got %r' % act
assert act.get('conflict') is True, 'expected conflict:true, got %r' % act
assert act.get('target_board') is None, 'target_board must stay unset (nothing to apply)'
print('done-wontfix-guard-ok')
" && pass "done ticket + gh not_planned yields conflict, not auto wontfix" \
  || fail "done ticket + gh not_planned yields conflict, not auto wontfix"

# Apply must be a no-op for this conflicted ticket: the illegal done→wontfix
# transition is never attempted, and board-gh-apply.sh must still exit 0.
if run board-gh-apply.sh --plan "$TEST_ROOT/plan-e.json" --no-github >/dev/null; then
  pass "apply exits 0 for a plan holding only the conflicted done/not_planned action"
else
  fail "apply exits 0 for a plan holding only the conflicted done/not_planned action"
fi
st_e="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$E']['state'])")"
assert_equals "$st_e" "done" "ticket stays done — illegal transition never attempted"

# ---- Task 4b: GitHub 'completed' close is authoritative → board catches up -----
# A linked issue closed as `completed` reconciles the board to `done` even when the
# ticket never reached in-progress (born ready-for-agent). LEGAL forbids the direct
# ready-for-agent→done jump, so plan emits an auto gh->board done and apply must
# route it through in-progress. This is the "PR merged on an integration branch →
# issue closed → board done" tail that used to stall as a conflict.
echo "board-gh-plan/apply (gh completed → board done from ready-for-agent):"
run board-register.sh "Completed from backlog" enhancement >/dev/null   # birth: ready-for-agent
F="$(run board-list.sh | grep 'Completed from backlog' | awk '{print $1}')"
run board-meta.sh "$F" --gh 300 >/dev/null
# watermark: previous sync saw both sides open (board ready-for-agent, gh open)
python3 - "$BOARD/.sync-state.json" "$F" <<'PY'
import json,sys
p,F=sys.argv[1:3]
d=json.load(open(p))
d["tickets"][F]={"gh":300,"state":"ready-for-agent"}
json.dump(d,open(p,"w"))
PY
cat > "$TEST_ROOT/gh-completed.json" <<JSON
[ {"number":300,"state":"CLOSED","stateReason":"completed","labels":[],"title":"f"} ]
JSON
run board-gh-plan.sh --gh-json "$TEST_ROOT/gh-completed.json" > "$TEST_ROOT/plan-f.json"
python3 -c "
import json
p = json.load(open('$TEST_ROOT/plan-f.json'))
act = {x['ticket']: x for x in p['actions']}['$F']
assert act['auto'] is True, 'expected auto:true, got %r' % act
assert not act.get('conflict'), 'must not be a conflict, got %r' % act
assert act['direction']=='gh->board' and act['target_board'][0]=='done', 'expected gh->board done, got %r' % act
print('completed-authoritative-plan-ok')
" && pass "gh completed + ready-for-agent → auto gh->board done (not conflict)" \
  || fail "gh completed + ready-for-agent → auto gh->board done (not conflict)"
# apply must route ready-for-agent → in-progress → done without the illegal jump
run board-gh-apply.sh --plan "$TEST_ROOT/plan-f.json" --no-github >/dev/null
st_f="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$F']['state'])")"
assert_equals "$st_f" "done" "ready-for-agent ticket routed to done via in-progress"

# ---- Task 5: board-gh-apply.sh — apply the plan + refresh the watermark -----
echo "board-gh-apply (dry-run):"
run board-gh-plan.sh --gh-json "$TEST_ROOT/gh.json" > "$TEST_ROOT/plan.json"
map_before="$(cat "$BOARD/board.json")"
out="$(run board-gh-apply.sh --plan "$TEST_ROOT/plan.json" --dry-run)"
assert_contains "$out" "gh: issue close 101 --reason completed" "dry-run plans the board->gh close"
assert_contains "$out" "board-transition.sh $B wontfix" "dry-run plans the gh->board wontfix"
assert_equals "$(cat "$BOARD/board.json")" "$map_before" "dry-run writes nothing to the board"
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
st="$(python3 -c "import json;print(json.load(open('$BOARD/board.json'))['tickets']['$B']['state'])")"
assert_equals "$st" "wontfix" "gh->board wontfix applied to the board via board-transition"
wm="$(python3 -c "import json;print(json.load(open('$BOARD/.sync-state.json'))['tickets']['$B']['state'])")"
assert_equals "$wm" "wontfix" "watermark refreshed to the reconciled board state"

# ---- Task 5 regression: filtered-plan safety ---------------------------------
# The bug this guards: apply's watermark refresh used to re-walk ALL of board.json
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

# ---- Task 5 regression: --no-github must not watermark a skipped board->gh --
# The bug this guards: under --no-github the gh call is skipped entirely (step
# 2 is a no-op for board->gh actions), but the watermark refresh used to count
# ANY auto, non-conflict action — including board->gh ones — as reconciled.
# That falsely recorded a GitHub push that never happened. The fix excludes
# board->gh actions from the refresh set specifically when --no-github is set.
echo "board-gh-apply (--no-github excludes board->gh from the watermark):"
run board-register.sh "NoGH board->gh guard" enhancement >/dev/null
G="$(run board-list.sh | grep 'NoGH board->gh guard' | awk '{print $1}')"
run board-transition.sh "$G" in-progress >/dev/null
run board-transition.sh "$G" done >/dev/null                          # board done, gh issue still open
run board-meta.sh "$G" --gh 301 >/dev/null
# G has no prior watermark entry at all — nothing has ever been reconciled for it.
cat > "$TEST_ROOT/plan-nogh.json" <<JSON
{"generated_by": "test", "actions": [
  {"ticket": "$G", "gh": 301, "facet": "state", "direction": "board->gh", "conflict": false, "auto": true,
   "board": "done", "gh_state": "OPEN", "target_gh": ["closed", "completed"], "watermark": null,
   "reason": "test: board->gh under --no-github"}
], "agree": [], "unlinked_board": [], "unlinked_gh": []}
JSON
run board-gh-apply.sh --plan "$TEST_ROOT/plan-nogh.json" --no-github >/dev/null
has_g="$(python3 -c "import json;print('$G' in json.load(open('$BOARD/.sync-state.json'))['tickets'])")"
assert_equals "$has_g" "False" "board->gh action skipped by --no-github gets NO watermark entry (regression guard)"

# ---- Task 6: board-reconcile.sh surfaces pending board-sync conflicts -------
# Spec: board-reconcile.sh reads SYNC-REPORT.md's machine-countable header
# line ("board-sync conflicts: N") and, read-only, surfaces a summary line
# when N>0 — additive, so reconcile's other output/tests are unaffected when
# no report exists.
echo "board-reconcile (surfaces SYNC-REPORT.md conflicts):"
cat > "$BOARD/SYNC-REPORT.md" <<'EOF'
board-sync conflicts: 2

## Conflicts
- T1: board=done gh_state=OPEN watermark=in-progress (reason: test)
- T2: board=ready-for-agent gh_state=CLOSED watermark=ready-for-agent (reason: test)

## Unlinked (board)
(none)

## Unlinked (GitHub)
(none)
EOF
out="$(run board-reconcile.sh)"
assert_contains "$out" "board-sync: 2 conflict(s) pending (SYNC-REPORT.md)" "reconcile surfaces pending board-sync conflicts"

# a report with zero conflicts stays silent
cat > "$BOARD/SYNC-REPORT.md" <<'EOF'
board-sync conflicts: 0

## Conflicts
(none)
EOF
out="$(run board-reconcile.sh)"
if printf '%s' "$out" | grep -q 'board-sync:.*conflict'; then
  fail "reconcile stays silent when SYNC-REPORT.md reports zero conflicts"
else
  pass "reconcile stays silent when SYNC-REPORT.md reports zero conflicts"
fi

# no report at all stays silent too
rm -f "$BOARD/SYNC-REPORT.md"
out="$(run board-reconcile.sh)"
if printf '%s' "$out" | grep -q 'board-sync:.*conflict'; then
  fail "reconcile stays silent when no SYNC-REPORT.md exists"
else
  pass "reconcile stays silent when no SYNC-REPORT.md exists"
fi

# ---- summary -----------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then echo "ALL TESTS PASSED"; else
    echo "$FAILURES TEST(S) FAILED"; exit 1; fi
