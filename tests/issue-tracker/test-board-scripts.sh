#!/usr/bin/env bash
#
# Hermetic tests for the issue-tracker board toolkit (v7: GitHub SSOT).
#
# The board lives on GitHub, so the scripts' only side channel is `gh` — we
# substitute a PATH-shimmed mock (mock-gh/gh) that keeps issue state in a JSON
# file and records every invocation. The real scripts run end-to-end; we
# assert on the mock's state, the scripts' output, and their refusals.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/issue-tracker/scripts"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() {
    # a mid-test failure must not leak the --serve http.server
    local pidfile="$TEST_ROOT/work/doperpowers/issue-tracker/.server.pid"
    [ -f "$pidfile" ] && kill "$(cat "$pidfile")" 2>/dev/null || true
    rm -rf "$TEST_ROOT"
}
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
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
assert_fails() { # cmd... — passes when the command exits non-zero
    if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; else pass "refused: $*"; fi
}

# ---- environment: throwaway git repo, mock gh, fake daemon registry ---------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export BOARD_REPO="test/repo"
export MOCK_GH_STATE="$TEST_ROOT/gh-state.json"
# Plan pins are verified against the remote (N3): the mock serves
# repos/<repo>/compare and /contents from this file. Seed it with the shapes
# the suite's own pinned handoffs use; individual cases override it.
export MOCK_GH_REFS="$TEST_ROOT/gh-refs.json"
SHA40="0123456789abcdef0123456789abcdef01234567"
python3 - <<'REFS'
import json, os
sha = "0123456789abcdef0123456789abcdef01234567"
json.dump({"compare": {"%s...%s" % (b, sha): "identical"
                       for b in ("tick/plan-probe", "tick/plan-clear", "tick/plan-keep",
                                 "tick/conv-reset", "tick/reach", "tick/earlier")},
           "contents": ["%s@%s" % (p, sha) for p in
                        ("docs/plans/x.md", "docs/p.md", "docs/q.md", "docs/plan.md",
                         "docs/plans/reach.md", "docs/sneaky.md")]},
          open(os.environ["MOCK_GH_REFS"], "w"))
REFS
export MOCK_GH_LOG="$TEST_ROOT/gh-log.jsonl"
export PATH="$SCRIPT_DIR/mock-gh:$PATH"
WORK="$TEST_ROOT/work"
git init -q "$WORK"
git -C "$WORK" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$WORK" worktree add -q -b t-branch "$TEST_ROOT/wt"

run() { (cd "$WORK" && "$SCRIPTS_DIR/$1" "${@:2}"); }
# state(): eval is safe here — the expression is a test-author-written literal
# from THIS file (never external input), evaluated against the mock's state.
state() { python3 -c "import json,sys;print(eval(sys.argv[1], {'s': json.load(open('$MOCK_GH_STATE'))}))" "$1"; }
# A filled spec body: ready-for-implementer births require one (a pre-spec skeleton
# is never implementable — see the pre-spec guard section).
SPEC_BODY="$TEST_ROOT/spec-body.md"
printf '## Problem & intent\n\nA real spec.\n\n## Success criteria\n\n- verifiable\n' > "$SPEC_BODY"

# ---- register ----------------------------------------------------------------
echo "board-register:"
out="$(run board-register.sh "Epic: alpha" enhancement P2 --body-file "$SPEC_BODY")"
assert_contains "$out" "1 https://github.com/test/repo/issues/1" "prints number + url"
assert_equals "$(state "s['issues']['1']['labels']")" "['enhancement', 'status:ready-for-implementer', 'priority:P2']" "category + birth status + priority labels"

out="$(run board-register.sh $'Multi\nline title' bug P1 --state needs-human --note "waiting on A")"
assert_equals "$(state "s['issues']['2']['title']")" "Multi line title" "title newlines collapsed"
assert_contains "$(state "s['issues']['2']['labels']")" "status:needs-human" "birth state honored"
assert_contains "$(state "s['issues']['2']['comments'][0]")" "[board] needs-human: waiting on A" "birth note posted as [board] comment"
assert_contains "$(state "s['issues']['2']['body']")" "note: waiting on A" "birth note in board:meta"

out="$(run board-register.sh "Child A" enhancement P1 --parent 1 --spawned-by 2 --body-file "$SPEC_BODY")"
assert_equals "$(state "s['issues']['3']['parent']")" "1" "parent sub-issue edge created"
assert_contains "$(state "s['issues']['3']['body']")" "spawned-by: #2" "spawned-by in board:meta"

out="$(run board-register.sh "Child B" enhancement P2 --parent 1 --blocked-by 3 --body-file "$SPEC_BODY")"
assert_equals "$(state "s['issues']['4']['blockedBy']")" "[3]" "blocked_by dependency edge created"

assert_fails run board-register.sh "X" gadget P2
assert_fails run board-register.sh "X" bug                             # priority required
assert_fails run board-register.sh "X" bug P9                          # bad grade
assert_fails run board-register.sh "X" bug P2 --state needs-info       # note required
assert_fails run board-register.sh "X" bug P2 --state interactive-preferred  # note required
assert_fails run board-register.sh "X" bug P2 --state blocked          # retired state (v8)
assert_fails run board-register.sh "X" bug P2 --state "done"             # not a birth state
assert_fails run board-register.sh "X" bug P2 --parent 999             # unknown ref

# ---- priority (managed label swap) --------------------------------------------
echo "board-priority:"
out="$(run board-priority.sh 2 P0)"
assert_contains "$out" "#2: P1 → P0" "swap reported"
assert_contains "$(state "s['issues']['2']['labels']")" "priority:P0" "new label present"
assert_not_contains "$(state "s['issues']['2']['labels']")" "priority:P1" "old label removed"
out="$(run board-priority.sh 2 P0)"
assert_contains "$out" "#2: P0 → P0" "same-grade re-run reports a no-op"
assert_fails run board-priority.sh 2 P9                                # bad grade
assert_fails run board-priority.sh 999 P1                              # unknown issue
python3 - <<'STRIP'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["4"]["labels"] = [l for l in s["issues"]["4"]["labels"]
                              if not l.startswith("priority:")]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
STRIP
out="$(run board-priority.sh 4 P2)"
assert_contains "$out" "#4: none → P2" "unset reported as none"

# ---- transition: legality + note/PR gates ------------------------------------
echo "board-transition:"
assert_fails run board-transition.sh 3 "done"                            # ready → done illegal
assert_fails run board-transition.sh 3 needs-human                     # note required
assert_fails run board-transition.sh 999 in-progress                   # unknown issue

out="$(run board-transition.sh 3 in-progress)"
assert_contains "$out" "#3: ready-for-implementer → in-progress" "transition applied"
assert_contains "$out" "#1: ready-for-implementer → in-progress" "epic pulled by first active child"
assert_contains "$(state "s['issues']['3']['labels']")" "status:in-progress" "label swapped"
assert_not_contains "$(state "s['issues']['3']['labels']")" "status:ready-for-implementer" "old label removed"

assert_fails run board-transition.sh 3 in-review                       # PR link required
out="$(run board-transition.sh 3 in-review "review round 1" --pr https://github.com/test/repo/pull/9 --branch feat/a)"
assert_contains "$(state "s['issues']['3']['body']")" "pr: https://github.com/test/repo/pull/9" "pr in board:meta"
assert_contains "$(state "s['issues']['3']['body']")" "branch: feat/a" "branch in board:meta"
assert_contains "$(state "s['issues']['3']['comments'][-1]")" "[board] in-review: review round 1" "note comment posted"

out="$(run board-transition.sh 3 "done")"
assert_equals "$(state "s['issues']['3']['state']")" "CLOSED" "done closes the issue"
assert_equals "$(state "s['issues']['3']['stateReason']")" "COMPLETED" "close reason completed"
assert_equals "$(state "s['issues']['3']['labels']")" "['enhancement', 'priority:P1']" "status labels stripped on close (priority kept — inert history)"
assert_contains "$out" "now eligible" "dependent unblocked report"
assert_contains "$out" "#4" "names the newly-eligible dependent"
assert_not_contains "$out" "#1: in-progress" "epic stays open (child 4 not terminal)"

out="$(run board-transition.sh 4 wontfix "superseded")"
assert_equals "$(state "s['issues']['4']['stateReason']")" "NOT_PLANNED" "wontfix → not planned"
assert_contains "$out" "#1: in-progress → ready-for-architect" "last terminal child returns the epic for recomposition"
assert_contains "$(state "s['issues']['1']['labels']")" "status:ready-for-architect" "epic waits in ready-for-architect"
assert_not_contains "$out" "#1: in-progress → done" "epic never auto-closes"

assert_fails run board-transition.sh 3 in-progress                     # terminal is terminal

# ---- edge: cycles, deadlocks, sweeps ------------------------------------------
echo "board-edge:"
run board-register.sh "Epic: beta" enhancement P2  --body-file "$SPEC_BODY" >/dev/null                            # 5
run board-register.sh "B1" enhancement P2 --parent 5  --body-file "$SPEC_BODY" >/dev/null                         # 6
run board-register.sh "B2" enhancement P2 --parent 5 --blocked-by 6  --body-file "$SPEC_BODY" >/dev/null          # 7
run board-register.sh "Loose" enhancement P3  --body-file "$SPEC_BODY" >/dev/null                                 # 8

assert_fails run board-edge.sh 6 --block 6                              # self
assert_fails run board-edge.sh 6 --block 7                              # cycle (7 waits on 6)
assert_fails run board-edge.sh 6 --block 5                              # ancestor epic deadlock
out="$(run board-edge.sh 8 --block 6)"
assert_equals "$(state "s['issues']['8']['blockedBy']")" "[6]" "block edge added"
out="$(run board-edge.sh 8 --unblock 6)"
assert_equals "$(state "s['issues']['8']['blockedBy']")" "[]" "block edge cut"
assert_contains "$out" "now eligible: #8" "unblock reports eligibility"

out="$(run board-edge.sh 8 --parent 5)"
assert_equals "$(state "s['issues']['8']['parent']")" "5" "parent set"
out="$(run board-edge.sh 8 --orphan)"
assert_equals "$(state "s['issues']['8']['parent']")" "None" "parent cleared"
assert_fails run board-edge.sh 8 --orphan                               # no parent

run board-transition.sh 6 in-progress >/dev/null
out="$(run board-edge.sh 6 --parent 8)"                                 # move active child under new epic
assert_contains "$out" "#8: ready-for-implementer → in-progress" "in-progress child pulls new epic"

# ---- relate --------------------------------------------------------------------
echo "board-relate:"
out="$(run board-relate.sh 7 8)"
assert_contains "$(state "s['issues']['7']['body']")" "relates-to: #8" "relates on a"
assert_contains "$(state "s['issues']['8']['body']")" "relates-to: #7" "relates on b"
assert_fails run board-relate.sh 7 8                                    # already related
out="$(run board-relate.sh 7 8 --cut)"
assert_not_contains "$(state "s['issues']['7']['body']")" "relates-to" "relates cut on a"
assert_fails run board-relate.sh 7 7                                    # self

# ---- list ----------------------------------------------------------------------
echo "board-list:"
out="$(run board-list.sh)"
assert_contains "$out" "#7" "lists tickets"
assert_contains "$out" "waiting:#6" "waiting tag with blocker"
assert_contains "$out" "[epic]" "epic tag"
out="$(run board-list.sh "done")"
assert_contains "$out" "#3" "state filter"
assert_not_contains "$out" "#7" "filter excludes others"

run board-transition.sh 6 wontfix "dropped" >/dev/null
out="$(run board-list.sh)"
assert_contains "$out" "STUCK(wontfix blocker)" "wontfix blocker marks dependent stuck"

# ---- lint ----------------------------------------------------------------------
echo "board-lint:"
python3 - <<'FIX'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["9"] = dict(s["issues"]["8"], number=9, id="ID_9", title="raw untracked",
                        labels=[], state="OPEN", stateReason=None, parent=None,
                        blockedBy=[], body="", comments=[],
                        url="https://github.com/test/repo/issues/9")
s["issues"]["7"]["labels"].append("status:in-progress")          # conflict (2 labels)
s["issues"]["3"]["labels"].append("status:done")                 # closed but labeled
s["next"] = 10
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX
set +e
out="$(run board-lint.sh 2>&1)"; rc=$?
set -e
assert_equals "$rc" "1" "lint exits 1 on FAILs"
assert_contains "$out" "FAIL #9: open with no status:* label" "untracked named"
assert_contains "$out" "FAIL #7: open with 2 status:* labels" "conflict named"
assert_contains "$out" "WARN #9: no priority label" "missing priority WARNed"

# duplicate priority labels FAIL, with a copy-paste-runnable FIX hint (bare grade),
# then repaired immediately so the later clean-board lint stays green.
python3 - <<'DUP'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["7"]["labels"].append("priority:P0")
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
DUP
set +e
outp="$(run board-lint.sh 2>&1)"
set -e
assert_contains "$outp" "FAIL #7: 2 priority:* labels" "duplicate priority FAILs"
assert_contains "$outp" "board-priority.sh 7 P0" "FIX hint uses a bare grade"
run board-priority.sh 7 P2 >/dev/null
set +e
outp2="$(run board-lint.sh 2>&1)"
set -e
assert_not_contains "$outp2" "FAIL #7: 2 priority:* labels" "repair clears the FAIL"

# a lone INVALID grade must FAIL too (a P9 would otherwise sort as unprioritized)
python3 - <<'BAD'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["8"]["labels"] = [l for l in s["issues"]["8"]["labels"]
                              if not l.startswith("priority:")] + ["priority:P9"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
BAD
set +e
outb="$(run board-lint.sh 2>&1)"
set -e
assert_contains "$outb" "FAIL #8: invalid priority label: priority:P9" "invalid grade FAILs"
run board-priority.sh 8 P3 >/dev/null                                  # restore

# an OPEN issue with a lone terminal label (legacy merge automation) = conflict
python3 - <<'FIX2'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["9"]["labels"] = ["status:done"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX2
set +e
out2="$(run board-lint.sh 2>&1)"
set -e
assert_contains "$out2" "FAIL #9" "open issue with lone status:done is not a state"
python3 - <<'FIX2'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["9"]["labels"] = []
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX2
assert_contains "$out" "FAIL #3: closed but still labeled" "closed-labeled named"
assert_contains "$out" "FIX:" "FIX lines present"

out="$(run board-transition.sh 9 ready-for-implementer)"               # repair path: untracked → open state
assert_contains "$(state "s['issues']['9']['labels']")" "status:ready-for-implementer" "repair labels untracked issue"
out="$(run board-transition.sh 7 in-progress)"                   # repair path: conflict → normalized
assert_equals "$(state "sorted(l for l in s['issues']['7']['labels'] if l.startswith('status:'))")" "['status:in-progress']" "repair normalizes conflict to one label"
python3 - <<'FIX'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["3"]["labels"].remove("status:done")
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX

# cycle detection (mutual block, forged directly in the store)
python3 - <<'FIX'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["7"]["blockedBy"] = [9]
s["issues"]["9"]["blockedBy"] = [7]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX
set +e
out="$(run board-lint.sh 2>&1)"; rc=$?
set -e
assert_equals "$rc" "1" "cycle → exit 1"
assert_contains "$out" "dependency cycle" "cycle named"
python3 - <<'FIX'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["7"]["blockedBy"] = [6]
s["issues"]["9"]["blockedBy"] = []
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX
set +e
out="$(run board-lint.sh 2>&1)"; rc=$?
set -e
assert_equals "$rc" "0" "clean board lints green (WARNs allowed)"

# ---- bind / show / reconcile ----------------------------------------------------
echo "board-bind / board-show / board-reconcile:"
cat > "$DAEMON_HOME/aaaa-bbbb.json" <<'J'
{"uuid": "aaaa-bbbb", "status": "running", "cwd": "/tmp", "worktree": "wt-9"}
J
cat > "$DAEMON_HOME/old9-impl.json" <<'J'
{"uuid": "old9-impl", "status": "idle", "ticket": "9", "cwd": "/tmp/old"}
J
out="$(run board-bind.sh aaaa 9)"
assert_contains "$out" "bound #9 ← aaaa-bbbb" "bind writes registry"
assert_equals "$(python3 -c "import json;print(json.load(open('$DAEMON_HOME/aaaa-bbbb.json'))['ticket'])")" "9" "registry meta has ticket"
assert_not_contains "$(cat "$DAEMON_HOME/old9-impl.json")" '"ticket"' "exclusive bind strips the old ticket owner before binding the new one"
# A live owner is stable: a second reviewer cannot steal its answer route.
python3 - <<PY
import json
p='$DAEMON_HOME/aaaa-bbbb.json'; m=json.load(open(p)); m.update(name='review-pr-9', status='working'); json.dump(m,open(p,'w'))
json.dump({'uuid':'cccc-dddd','name':'review-pr-10','status':'working'},open('$DAEMON_HOME/cccc-dddd.json','w'))
PY
assert_fails run board-bind.sh cccc 9
assert_contains "$(cat "$DAEMON_HOME/aaaa-bbbb.json")" '"ticket": "9"' "active owner keeps the ticket binding"
assert_not_contains "$(cat "$DAEMON_HOME/cccc-dddd.json")" '"ticket"' "rejected takeover never binds the contender"
# An idle needs-human owner is also stable until board-answer resumes it.
cat > "$DAEMON_HOME/parked-two.json" <<'J'
{"uuid":"parked-two","name":"review-pr-2","status":"idle","ticket":"2"}
J
cat > "$DAEMON_HOME/park-contender.json" <<'J'
{"uuid":"park-contender","name":"review-pr-22","status":"working"}
J
assert_fails run board-bind.sh park-contender 2
assert_contains "$(cat "$DAEMON_HOME/parked-two.json")" '"ticket":"2"' "parked needs-human owner keeps its binding"
assert_not_contains "$(cat "$DAEMON_HOME/park-contender.json")" '"ticket"' "parked ticket rejects a new owner"

# The registry lock serializes two simultaneous claims: exactly one wins and
# exactly one meta owns the ticket afterward.
cat > "$DAEMON_HOME/race-one.json" <<'J'
{"uuid":"race-one","name":"review-pr-81","status":"working"}
J
cat > "$DAEMON_HOME/race-two.json" <<'J'
{"uuid":"race-two","name":"review-pr-82","status":"working"}
J
( set +e; run board-bind.sh race-one 8 >"$TEST_ROOT/race1.out" 2>&1; echo $? >"$TEST_ROOT/race1.rc" ) & p1=$!
( set +e; run board-bind.sh race-two 8 >"$TEST_ROOT/race2.out" 2>&1; echo $? >"$TEST_ROOT/race2.rc" ) & p2=$!
wait "$p1"; wait "$p2"
successes="$(python3 - <<PY
r=[int(open('$TEST_ROOT/race1.rc').read()),int(open('$TEST_ROOT/race2.rc').read())]
print(sum(x==0 for x in r))
PY
)"
owners="$(python3 - <<PY
import glob,json
print(sum(str(json.load(open(p)).get('ticket',''))=='8' for p in glob.glob('$DAEMON_HOME/*.json')))
PY
)"
assert_equals "$successes" "1" "concurrent bind has exactly one winner"
assert_equals "$owners" "1" "concurrent bind leaves exactly one ticket owner"

# Park state must be read after acquiring the metadata lock. Reproduce a bind
# waiting on the lock while the ticket transitions ready-for-implementer→needs-human:
# a pre-lock snapshot would wrongly strip the newly parked owner.
python3 - <<'PY'
import json,os
p=os.environ['MOCK_GH_STATE']; s=json.load(open(p)); src=dict(s['issues']['8'])
src.update(number=999,id='ID_999',title='bind race park',state='OPEN',stateReason=None,
           labels=['bug','status:ready-for-implementer','priority:P2'],body='## Problem & intent\n\nrace')
s['issues']['999']=src; json.dump(s,open(p,'w'))
json.dump({'uuid':'park-race-old','name':'review-pr-999','status':'idle','ticket':'999'},
          open(os.path.join(os.environ['DAEMON_HOME'],'park-race-old.json'),'w'))
json.dump({'uuid':'park-race-new','name':'review-pr-1000','status':'working'},
          open(os.path.join(os.environ['DAEMON_HOME'],'park-race-new.json'),'w'))
PY
LOCK="$DAEMON_HOME/.metalock" MARK="$TEST_ROOT/lock-held" python3 - <<'PY' & lock_pid=$!
import fcntl,os,time
f=open(os.environ['LOCK'],'a'); fcntl.flock(f,fcntl.LOCK_EX)
open(os.environ['MARK'],'w').write('held')
time.sleep(1.0)
fcntl.flock(f,fcntl.LOCK_UN); f.close()
PY
while [ ! -f "$TEST_ROOT/lock-held" ]; do sleep 0.01; done
( set +e; run board-bind.sh park-race-new 999 >"$TEST_ROOT/park-race.out" 2>&1; echo $? >"$TEST_ROOT/park-race.rc" ) & bind_pid=$!
sleep 0.2
run board-transition.sh 999 needs-human "human decision" >/dev/null
wait "$lock_pid"; wait "$bind_pid"
assert_equals "$(cat "$TEST_ROOT/park-race.rc")" "1" "bind re-reads needs-human after lock acquisition"
assert_contains "$(cat "$DAEMON_HOME/park-race-old.json")" '"ticket": "999"' "lock-wait park keeps the original owner"
assert_not_contains "$(cat "$DAEMON_HOME/park-race-new.json")" '"ticket"' "lock-wait contender never acquires the parked ticket"

out="$(run board-show.sh 9)"
assert_contains "$out" "daemon: aaaa-bbbb" "show finds bound daemon"
assert_contains "$out" '"state": "ready-for-implementer"' "show prints node"

run board-transition.sh 9 in-progress >/dev/null
out="$(run board-reconcile.sh)"
assert_contains "$out" "parked    #2: needs-human — waiting on A" "reconcile lists the wake queue"
assert_not_contains "$out" "proposal" "the proposal scanner is gone (v8: no orchestrator)"
run board-transition.sh 7 in-progress >/dev/null 2>&1 || true    # 7 has no daemon
out="$(run board-reconcile.sh)"
assert_contains "$out" "orphaned  #7" "orphaned in-progress flagged"
assert_contains "$out" "board-lint" "reconcile ends with a lint pass"

# ---- map -------------------------------------------------------------------------
echo "board-map:"
out="$(run board-map.sh)"
assert_contains "$out" "| #9 |" "table row per ticket"
assert_contains "$out" "| #8 | P3 |" "table shows the priority column"
run board-map.sh --write >/dev/null 2>&1
assert_file_exists "$WORK/doperpowers/issue-tracker/BOARD.html" "BOARD.html rendered"
assert_file_exists "$WORK/doperpowers/issue-tracker/BOARD.md" "BOARD.md rendered"
assert_file_exists "$WORK/doperpowers/issue-tracker/BOARD.rev" "BOARD.rev change token rendered"
assert_equals "$(cat "$WORK/doperpowers/issue-tracker/.gitignore")" "*" "render dir is gitignored"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"id": "#9"' "html payload uses display ids"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"priority": "P3"' "html payload carries priority"

# native GitHub-linked PRs (closes + cross-ref) surface without any pr: meta —
# the merge-autoclose gap the manual meta could not cover.
python3 -c "import json;p='$MOCK_GH_STATE';s=json.load(open(p));i=s['issues']['9'];i['closesPRs']=[{'number':58,'url':'https://github.com/test/repo/pull/58','state':'MERGED'}];i['xrefPRs']=[{'number':61,'url':'https://github.com/test/repo/pull/61','state':'OPEN'}];json.dump(s,open(p,'w'))"
out="$(run board-map.sh)"
assert_contains "$out" "#58 #61" "md table shows native linked PRs (closes + xref)"
run board-map.sh --write >/dev/null 2>&1
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"num": 58' "html payload carries closing PR number"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"rel": "closes"' "closing PR keeps the closes relation"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"num": 61' "html payload carries cross-ref PR number"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"rel": "ref"' "cross-ref PR keeps the ref relation"

# ---- map --serve: live server + hot-reload plumbing -------------------------------
echo "board-map --serve:"
export BOARD_NO_OPEN=1
# an actually-free port (bind :0), not a random guess that can collide
BOARD_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
export BOARD_PORT
out="$(run board-map.sh --serve 2>&1)"
assert_contains "$out" "http://127.0.0.1:$BOARD_PORT/BOARD.html" "serve prints the board url"
assert_file_exists "$WORK/doperpowers/issue-tracker/.server.pid" "server pid recorded"
body="$(curl -s "http://127.0.0.1:$BOARD_PORT/BOARD.html")"
assert_contains "$body" '"id": "#9"' "served page carries the payload"
assert_contains "$body" "hot reload" "served page carries the hot-reload poller"
out="$(run board-map.sh --serve 2>&1)"
assert_contains "$out" "already up" "second --serve reuses the running server"
# a mutation while the server is up re-renders the cache in the background
# (no relates edge exists on the board here — the earlier 7--8 was cut)
run board-relate.sh 8 9 >/dev/null 2>&1
for _ in $(seq 1 20); do   # background render: give it a beat
  grep -Fq '"kind": "relates"' "$WORK/doperpowers/issue-tracker/BOARD.html" 2>/dev/null && break
  sleep 0.25
done
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"kind": "relates"' "mutation auto-refreshed the served render"
run board-relate.sh 8 9 --cut >/dev/null 2>&1   # restore board state for later asserts
out="$(run board-map.sh --stop 2>&1)"
assert_contains "$out" "stopped" "--stop kills the server"
gone=0
for _ in $(seq 1 20); do   # SIGTERM latency: wait for the port to close
  if ! curl -s --max-time 2 "http://127.0.0.1:$BOARD_PORT/BOARD.html" >/dev/null 2>&1; then gone=1; break; fi
  sleep 0.25
done
if [ "$gone" -eq 1 ]; then pass "server gone after --stop"; else fail "server gone after --stop"; fi
# a stale pidfile whose pid was recycled onto an unrelated process must be
# left alone: --stop refuses to kill anything that isn't a http.server
sleep 60 & bystander=$!
echo "$bystander" > "$WORK/doperpowers/issue-tracker/.server.pid"
out="$(run board-map.sh --stop 2>&1)"
assert_contains "$out" "no board server running" "recycled-pid pidfile treated as no server"
if kill -0 "$bystander" 2>/dev/null; then pass "--stop spared the unrelated process"; else fail "--stop spared the unrelated process"; fi
kill "$bystander" 2>/dev/null || true
unset BOARD_PORT BOARD_NO_OPEN

# ---- worktree friendliness (the v6 guard is gone) --------------------------------
echo "worktree:"
out="$(cd "$TEST_ROOT/wt" && "$SCRIPTS_DIR/board-list.sh")"
assert_contains "$out" "#9" "reads fine from a worktree"
out="$(cd "$TEST_ROOT/wt" && "$SCRIPTS_DIR/board-transition.sh" 9 in-review "wt" --pr https://x/pr/1)"
assert_contains "$out" "#9: in-progress → in-review" "writes fine from a worktree"

# ---- migrate ----------------------------------------------------------------------
echo "board-migrate-gh:"
LEGACY="$TEST_ROOT/legacy"
mkdir -p "$LEGACY/tickets"
cat > "$LEGACY/board.json" <<J
{"version": 1, "next_id": 3, "tickets": {
  "T1": {"title": "Linked (GH#8)", "md": "tickets/T1.md", "state": "in-progress",
         "category": "enhancement", "note": "mid-flight", "parent": null,
         "blocked_by": [], "spawned_by": null, "relates_to": [], "branch": "feat/t1",
         "pr": null, "created": "2026-07-01", "updated": "2026-07-05", "gh": 8},
  "T2": {"title": "Unlinked new", "md": "tickets/T2.md", "state": "ready-for-implementer",
         "category": "bug", "note": null, "parent": null, "blocked_by": ["T1"],
         "spawned_by": "T1", "relates_to": [], "branch": null, "pr": null,
         "created": "2026-07-02", "updated": "2026-07-02", "gh": null}
}}
J
printf -- '---\nid: T1\n---\n# T1\n\n## Problem & intent\n\nreal content line 1\nreal content line 2\nreal content line 3\n' > "$LEGACY/tickets/T1.md"
printf -- '---\nid: T2\n---\n# T2\n' > "$LEGACY/tickets/T2.md"

before="$(cat "$MOCK_GH_STATE")"
out="$(run board-migrate-gh.sh --board "$LEGACY/board.json")"
assert_contains "$out" "plan  create issue for T2" "dry-run plans creation"
assert_contains "$out" "T1→#8" "dry-run plans linked updates"
assert_equals "$(cat "$MOCK_GH_STATE")" "$before" "dry-run mutates nothing"

out="$(run board-migrate-gh.sh --board "$LEGACY/board.json" --apply)"
assert_contains "$(state "s['issues']['8']['labels']")" "status:in-progress" "linked state applied"
assert_contains "$(state "s['issues']['8']['body']")" "branch: feat/t1" "linked meta applied"
assert_contains "$(state "s['issues']['8']['body']")" "Board pre-spec (migrated)" "md content appended"
assert_equals "$(state "s['issues']['10']['title']")" "Unlinked new" "unlinked ticket created"
assert_equals "$(state "s['issues']['10']['blockedBy']")" "[8]" "created ticket got its edges"
assert_contains "$(state "s['issues']['10']['body']")" "spawned-by: #8" "created ticket got provenance"

# ---- finalize: PR-merge auto-close ("Closes #N") -----------------------------
echo "finalize (merge auto-close):"
run board-register.sh "Epic: delta" enhancement P2  --body-file "$SPEC_BODY" >/dev/null                    # 11
run board-register.sh "D1" enhancement P0 --parent 11  --body-file "$SPEC_BODY" >/dev/null                 # 12
run board-register.sh "D2" enhancement P2 --blocked-by 12  --body-file "$SPEC_BODY" >/dev/null             # 13
top="$(run board-list.sh | head -1)"
assert_contains "$top" "P0" "P0 row floats to the top of the list"
run board-transition.sh 12 in-progress >/dev/null
run board-transition.sh 12 in-review "pr open" --pr https://github.com/test/repo/pull/33 >/dev/null
# GitHub merges the PR: "Closes #12" auto-closes the issue — labels stay put,
# no script ran, so the sweeps never fired.
python3 - <<'FIX'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["12"]["state"] = "CLOSED"
s["issues"]["12"]["stateReason"] = "COMPLETED"
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
FIX
set +e
lint_out="$(run board-lint.sh 2>&1)"
set -e
assert_contains "$lint_out" "FAIL #12: closed but still labeled" "auto-closed leftover label named"
assert_contains "$lint_out" "board-transition.sh 12 done" "lint FIX points at finalize"

out="$(run board-transition.sh 12 "done")"
assert_contains "$out" "#12: done — stripped residual status labels" "finalize strips labels"
assert_not_contains "$(state "s['issues']['12']['labels']")" "status:in-review" "stale in-review label gone"
assert_contains "$out" "#11: in-progress → ready-for-architect" "finalize returns the epic for recomposition"
assert_contains "$(state "s['issues']['11']['labels']")" "status:ready-for-architect" "finalized epic waits in ready-for-architect"
assert_contains "$out" "now eligible: #13" "finalize reports unblocked dependent"

out="$(run board-transition.sh 12 "done")"                          # idempotent re-run
assert_contains "$out" "now eligible: #13" "finalize re-run is safe"
assert_fails run board-transition.sh 12 wontfix "flip"            # done → wontfix still illegal
assert_fails run board-transition.sh 13 ready-for-implementer           # already ready (open states still die)

# ---- close candidate (derived signal, never a label) --------------------------
# Open ticket + every linked PR merged/closed + ≥1 merged → CLOSE? in list,
# WARN in lint (unless actively worked), marked in BOARD.md, flagged in the
# html payload. All-CLOSED-unmerged (abandoned attempt) and any OPEN linked PR
# are NOT candidates.
echo "close-candidate:"
run board-register.sh "Cand ready" enhancement P2  --body-file "$SPEC_BODY" >/dev/null            # 14: closes MERGED + xref CLOSED
run board-register.sh "Abandoned only" enhancement P2  --body-file "$SPEC_BODY" >/dev/null        # 15: closes CLOSED (no merge)
run board-register.sh "Still open PR" enhancement P2  --body-file "$SPEC_BODY" >/dev/null         # 16: MERGED + xref OPEN
python3 - <<'PRS'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["14"]["closesPRs"] = [{"number": 70, "url": "https://github.com/test/repo/pull/70", "state": "MERGED"}]
s["issues"]["14"]["xrefPRs"]   = [{"number": 71, "url": "https://github.com/test/repo/pull/71", "state": "CLOSED"}]
s["issues"]["15"]["closesPRs"] = [{"number": 72, "url": "https://github.com/test/repo/pull/72", "state": "CLOSED"}]
s["issues"]["16"]["closesPRs"] = [{"number": 73, "url": "https://github.com/test/repo/pull/73", "state": "MERGED"}]
s["issues"]["16"]["xrefPRs"]   = [{"number": 74, "url": "https://github.com/test/repo/pull/74", "state": "OPEN"}]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PRS
out="$(run board-list.sh)"
line14="$(printf '%s\n' "$out" | grep '^#14 ')"
assert_contains "$line14" "CLOSE?" "all-landed ticket tagged CLOSE?"
assert_contains "$line14" "ELIGIBLE" "CLOSE? does not eat eligibility"
assert_not_contains "$(printf '%s\n' "$out" | grep '^#15 ')" "CLOSE?" "all-closed-unmerged is NOT a candidate"
assert_not_contains "$(printf '%s\n' "$out" | grep '^#16 ')" "CLOSE?" "an open linked PR is NOT a candidate"

set +e
lint_out="$(run board-lint.sh 2>&1)"
set -e
assert_contains "$lint_out" "WARN #14: all 2 linked PR(s) merged/closed" "candidate WARNed"
assert_not_contains "$lint_out" "WARN #15: all" "abandoned-only not WARNed"
assert_not_contains "$lint_out" "WARN #16: all" "open-PR not WARNed"

out="$(run board-map.sh)"
assert_contains "$out" "| #14 | P2 | ready-for-implementer · ELIGIBLE · CLOSE? |" "md table marks the candidate"
run board-map.sh --write >/dev/null 2>&1
# pull the per-node flag out of the embedded payload (grep can't scope to a node)
ccflag() { python3 - "$WORK/doperpowers/issue-tracker/BOARD.html" "$1" <<'PY'
import json, re, sys
h = open(sys.argv[1]).read()
m = re.search(r'<script id="board-data" type="application/json">(.*?)</script>', h, re.S)
d = json.loads(m.group(1).replace('\\u003c', '<').replace('\\u003e', '>').replace('\\u0026', '&'))
print([x for x in d["nodes"] if x["id"] == sys.argv[2]][0]["close_candidate"])
PY
}
assert_equals "$(ccflag '#14')" "True" "html payload flags the candidate"
assert_equals "$(ccflag '#15')" "False" "html payload keeps non-candidates false"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"close-candidate"' "kanban column vocabulary present"

# actively-worked candidate: lint goes quiet (mid-flight merged PR is normal),
# the list still states the fact.
run board-transition.sh 14 in-progress >/dev/null
set +e
lint_out2="$(run board-lint.sh 2>&1)"
set -e
assert_not_contains "$lint_out2" "WARN #14: all" "active (in-progress) candidate not WARNed"
out="$(run board-list.sh)"
assert_contains "$(printf '%s\n' "$out" | grep '^#14 ')" "CLOSE?" "active candidate still tagged in list"

# a truncated PR fetch (connection totalCount exceeds the capped nodes the
# query returns) must not claim "all PRs landed" — an uncounted PR may be
# open, so the candidate is conservatively disqualified.
python3 - <<'TRUNC'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["14"]["closesTotal"] = 25            # 25 linked PRs, only 1 fetched
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
TRUNC
out="$(run board-list.sh)"
assert_not_contains "$(printf '%s\n' "$out" | grep '^#14 ')" "CLOSE?" "truncated PR fetch disqualifies the candidate"

# ---- confident-ready (review-loop escalation state) ---------------------------
# Reachable only from in-review (a review verdict presupposes a PR); demotes
# back to in-review on a new push; closes normally. Note optional.
echo "confident-ready:"
run board-register.sh "Review target" enhancement P2  --body-file "$SPEC_BODY" >/dev/null                  # 17
assert_fails run board-transition.sh 17 confident-ready                          # ready → confident-ready illegal
run board-transition.sh 17 in-progress >/dev/null
assert_fails run board-transition.sh 17 confident-ready                          # in-progress → illegal (must pass through in-review)
run board-transition.sh 17 in-review "pr open" --pr https://github.com/test/repo/pull/80 >/dev/null
out="$(run board-transition.sh 17 confident-ready "codex approve, 2 rounds")"
assert_contains "$out" "#17: in-review → confident-ready" "in-review → confident-ready applied"
assert_contains "$(state "s['issues']['17']['labels']")" "status:confident-ready" "label swapped in"
assert_not_contains "$(state "s['issues']['17']['labels']")" "status:in-review" "old label removed"
assert_contains "$(state "s['issues']['17']['comments'][-1]")" "[board] confident-ready: codex approve" "note comment posted"
out="$(run board-list.sh confident-ready)"
assert_contains "$out" "#17" "board-list filters confident-ready"
set +e
lint_out="$(run board-lint.sh 2>&1)"; lint_rc=$?
set -e
assert_equals "$lint_rc" "0" "board with a confident-ready ticket lints green"
out="$(run board-transition.sh 17 in-review "new push demoted" --pr https://github.com/test/repo/pull/80)"
assert_contains "$out" "#17: confident-ready → in-review" "confident-ready demotes to in-review"
run board-transition.sh 17 confident-ready >/dev/null                            # note optional
out="$(run board-transition.sh 17 "done")"
assert_equals "$(state "s['issues']['17']['state']")" "CLOSED" "confident-ready → done closes the issue"
assert_equals "$(state "s['issues']['17']['stateReason']")" "COMPLETED" "closes as completed"

run board-register.sh "CR map probe" enhancement P2  --body-file "$SPEC_BODY" >/dev/null                    # 18
run board-transition.sh 18 in-progress >/dev/null
run board-transition.sh 18 in-review "pr" --pr https://github.com/test/repo/pull/81 >/dev/null
run board-transition.sh 18 confident-ready >/dev/null
run board-map.sh --write >/dev/null 2>&1
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"cls": "s_cready"' "html payload carries the confident-ready class"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"confident-ready"' "kanban vocabulary carries the confident-ready column"

# ---- in-review escalations: needs-info/needs-human (review-worker protocol
# safety valves) -------------------------------------------------------------
# The reviewing-prs Review Worker Protocol escalates in-review → needs-info
# (round cap reached, impasse) and in-review → needs-human (push conflict,
# precondition failure) — both were illegal transitions before this fix.
# Reuses #18 (left at confident-ready above); demote it back to in-review
# first.
echo "in-review escalations:"
out="$(run board-transition.sh 18 in-review "demote for escalation test" --pr https://github.com/test/repo/pull/81)"
assert_contains "$out" "#18: confident-ready → in-review" "confident-ready demotes back to in-review for the escalation test"

assert_fails run board-transition.sh 18 needs-info                             # note required
out="$(run board-transition.sh 18 needs-info "round cap reached, escalate")"
assert_contains "$out" "#18: in-review → needs-info" "in-review → needs-info is now legal (protocol escalation)"
assert_contains "$(state "s['issues']['18']['labels']")" "status:needs-info" "needs-info label applied"

run board-transition.sh 18 in-progress >/dev/null
out="$(run board-transition.sh 18 in-review "back for another round" --pr https://github.com/test/repo/pull/81)"
assert_contains "$out" "#18: in-progress → in-review" "back to in-review ahead of the needs-human escalation"
assert_fails run board-transition.sh 18 needs-human                            # note required
out="$(run board-transition.sh 18 needs-human "push conflict — needs a human")"
assert_contains "$out" "#18: in-review → needs-human" "in-review → needs-human is legal (protocol escalation)"
assert_contains "$(state "s['issues']['18']['labels']")" "status:needs-human" "needs-human label applied"

# ---- interactive-preferred (park: ticket shape wants live human steering) -----
echo "interactive-preferred:"
assert_fails run board-register.sh "IP birth" enhancement P2 --state interactive-preferred  # note required
run board-register.sh "IP birth" enhancement P2 --state interactive-preferred --note "product-core: onboarding voice" --body-file "$SPEC_BODY" >/dev/null   # 19
assert_contains "$(state "s['issues']['19']['labels']")" "status:interactive-preferred" "birth state honored"
out="$(run board-list.sh)"
line19="$(printf '%s\n' "$out" | grep '^#19 ')"
assert_not_contains "$line19" "ELIGIBLE" "interactive-preferred is never ELIGIBLE"
out="$(run board-transition.sh 19 in-progress)"
assert_contains "$out" "#19: interactive-preferred → in-progress" "human takes it up: in-progress legal"
assert_fails run board-transition.sh 19 interactive-preferred                  # note required
out="$(run board-transition.sh 19 interactive-preferred "back to parked")"
assert_contains "$out" "#19: in-progress → interactive-preferred" "in-progress → interactive-preferred legal (gate-fail mid-build)"
out="$(run board-transition.sh 19 ready-for-implementer)"
assert_contains "$out" "#19: interactive-preferred → ready-for-implementer" "re-spec exit: settled decisions return it to the pool"
run board-transition.sh 19 interactive-preferred "back to parked" >/dev/null   # restore the park for the kanban asserts
set +e
lint_out="$(run board-lint.sh 2>&1)"; lint_rc=$?
set -e
assert_equals "$lint_rc" "0" "board with a noted interactive-preferred ticket lints green"

# ---- needs-human (park: the human as themselves unparks) ---------------------
echo "needs-human:"
run board-register.sh "NH probe" enhancement P2  --body-file "$SPEC_BODY" >/dev/null                     # 20
assert_fails run board-transition.sh 20 needs-human                            # note required
out="$(run board-transition.sh 20 needs-human "pick auth provider: A or B (rec: A)")"
assert_contains "$out" "#20: ready-for-implementer → needs-human" "gate-fail park applied"
out="$(run board-transition.sh 20 needs-info "research first: provider capability matrix")"
assert_contains "$out" "#20: needs-human → needs-info" "park-to-park re-triage legal"
out="$(run board-transition.sh 20 ready-for-implementer)"
assert_contains "$out" "#20: needs-info → ready-for-implementer" "answered park returns to ready"

# ---- blocked is retired (v8) --------------------------------------------------
echo "blocked retired:"
assert_fails run board-transition.sh 20 blocked "any"                          # unknown state
python3 - <<'LEGACY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["20"]["labels"] = ["enhancement", "status:blocked", "priority:P2"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
LEGACY
set +e
lint_out="$(run board-lint.sh 2>&1)"; rc=$?
set -e
assert_equals "$rc" "1" "legacy status:blocked FAILs lint"
assert_contains "$lint_out" "retired state: status:blocked" "retired label named"
assert_contains "$lint_out" "board-transition.sh 20 needs-human" "FIX points at the needs-human migration"
out="$(run board-transition.sh 20 needs-human "migrated: carried note")"
assert_contains "$(state "s['issues']['20']['labels']")" "status:needs-human" "migration swaps the label"
assert_not_contains "$(state "s['issues']['20']['labels']")" "status:blocked" "retired label removed"

# ---- ready-for-agent is retired (v9) --------------------------------------------
# A lone status:ready-for-agent label used to fall into the generic
# CONFLICT else-branch, which reports "N status:* labels" under a rule that
# means 2+ — nonsense at N=1. Same treatment as blocked: a named branch with
# an actionable FIX line naming the v9 migration path.
echo "ready-for-agent retired:"
run board-register.sh "Retired label probe" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
rfa_t="$(state "s['next']-1")"
python3 - <<PY
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["$rfa_t"]["labels"] = ["enhancement", "status:ready-for-agent", "priority:P2"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
set +e
lint_out="$(run board-lint.sh 2>&1)"; rc=$?
set -e
assert_equals "$rc" "1" "legacy status:ready-for-agent FAILs lint"
assert_contains "$lint_out" "retired state: status:ready-for-agent" "retired label named"
assert_not_contains "$lint_out" "with 1 status:* labels" "not misreported as a 1-label conflict (the bug this fix closes)"
assert_contains "$lint_out" "board-transition.sh $rfa_t ready-for-implementer" "FIX points at the ready-for-implementer migration"
out="$(run board-transition.sh "$rfa_t" ready-for-implementer "migrated: carried note")"
assert_contains "$(state "s['issues']['$rfa_t']['labels']")" "status:ready-for-implementer" "migration swaps the label"
assert_not_contains "$(state "s['issues']['$rfa_t']['labels']")" "status:ready-for-agent" "retired label removed"

# ---- map: v8 park classes ------------------------------------------------------
echo "board-map (v8 park classes):"
run board-map.sh --write >/dev/null 2>&1
BOARD_HTML="$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")"
assert_contains "$BOARD_HTML" '"cls": "s_needh"' "html payload carries the needs-human class"
assert_contains "$BOARD_HTML" '"cls": "s_ipref"' "html payload carries the interactive-preferred class"
assert_contains "$BOARD_HTML" '"interactive-preferred"' "kanban vocabulary carries the interactive-preferred column"
assert_not_contains "$BOARD_HTML" 's_blk' "retired blocked class gone from the render"

# template view logic (kanban relocation + chip filtering) runs under node —
# the only surface a shell test can't execute. Skipped, not failed, where node
# is absent (the toolkit itself never needs node; this guards the template).
echo "board template (kanban view logic):"
if command -v node >/dev/null 2>&1; then
    if node "$SCRIPT_DIR/test-board-template.cjs"; then :; else
        fail "template kanban tests (see output above)"
    fi
else
    echo "  [SKIP] node not installed — template JS tests not run"
fi

# ---- answer relay (park = pause, not death) ------------------------------------
echo "board-answer:"
STUB_DS="$TEST_ROOT/stub-daemon-scripts"; mkdir -p "$STUB_DS"
export STUB_STATE="$TEST_ROOT/stub-state"; mkdir -p "$STUB_STATE"
for eng in codex daemon; do
    cat > "$STUB_DS/$eng-resume.sh" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$1" > "\$STUB_STATE/$eng-resume.uuid"
printf '%s' "\$2" > "\$STUB_STATE/$eng-resume.msg"
echo "resumed: [$eng stub]"
STUB
    chmod +x "$STUB_DS/$eng-resume.sh"
done
cat > "$STUB_DS/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$1" >> "$STUB_STATE/finalize.log"
M="$(find "$DAEMON_HOME" -name "$1*.json" -type f | head -1)"
[ -n "$M" ] || { echo absent; exit 0; }
M="$M" python3 - <<'PY'
import json,os
p=os.environ['M']; m=json.load(open(p))
if m.get('status') in ('working','blocked') and m.get('turn_state') == 'idle':
    m['status']='idle'; json.dump(m,open(p,'w'),indent=2); print('idle')
elif m.get('status') in ('working','blocked') and m.get('turn_state') == 'absent': print('absent')
elif m.get('status') in ('working','blocked'): print('live')
else: print('noop')
PY
STUB
chmod +x "$STUB_DS/daemon-finalize.sh"
cat > "$STUB_DS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$1" >> "$STUB_STATE/retire.log"
M="$(find "$DAEMON_HOME" -name "$1*.json" -type f | head -1)"
[ -n "$M" ] || exit 0
M="$M" python3 - <<'PY'
import json,os
p=os.environ['M']; m=json.load(open(p)); m['status']='retired'; json.dump(m,open(p,'w'),indent=2)
PY
STUB
chmod +x "$STUB_DS/daemon-retire.sh"
export DAEMON_SCRIPTS="$STUB_DS"

out="$(run board-register.sh "Parked ticket" enhancement P2 --state needs-human --note "Q1? Q2?")"
ans_t="${out%% *}"
out="$(run board-register.sh "Unbound parked" enhancement P2 --state needs-human --note "Q?")"
unb_t="${out%% *}"
out="$(run board-register.sh "Open ticket" enhancement P2 --body-file "$SPEC_BODY")"
open_t="${out%% *}"
cat > "$DAEMON_HOME/cccccccc-1111-2222-3333-444444444444.json" <<META
{"uuid": "cccccccc-1111-2222-3333-444444444444", "engine": "codex",
 "status": "idle", "ticket": "$ans_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META

assert_fails run board-answer.sh "$open_t" "answer"     # not needs-human
assert_fails run board-answer.sh "$unb_t" "answer"      # no bound session
assert_fails run board-answer.sh "$ans_t"               # missing answers (arity)

out="$(run board-answer.sh "$ans_t" "1: use X. 2: defer Y.")"
assert_contains "$(state "s['issues']['$ans_t']['comments']")" "[answers] 1: use X. 2: defer Y." "answers posted on the ticket first"
assert_contains "$(state "s['issues']['$ans_t']['labels']")" "status:in-progress" "ticket resumed to in-progress"
assert_equals "$(cat "$STUB_STATE/codex-resume.uuid")" "cccccccc-1111-2222-3333-444444444444" "codex meta routed to codex-resume"
msg="$(cat "$STUB_STATE/codex-resume.msg")"
assert_contains "$msg" "1: use X. 2: defer Y." "answers relayed verbatim"
assert_contains "$msg" "[gate] re-pass" "relay carries the re-verdict guard"
assert_contains "$msg" "the ticket remains the record" "relay names the record"

# engine-less meta → claude resume; --posted relays a pointer, posts nothing
run board-transition.sh "$ans_t" needs-human "round 2 questions" >/dev/null
rm "$DAEMON_HOME/cccccccc-1111-2222-3333-444444444444.json"
cat > "$DAEMON_HOME/dddddddd-1111-2222-3333-444444444444.json" <<META
{"uuid": "dddddddd-1111-2222-3333-444444444444", "status": "working", "turn_state": "idle",
 "ticket": "$ans_t", "cwd": "$WORK", "updated": "2026-07-12T00:00:00Z"}
META
out="$(run board-answer.sh "$ans_t" --posted)"
assert_contains "$(cat "$STUB_STATE/finalize.log")" "dddddddd-1111-2222-3333-444444444444" "answer relay finalizes a lingering finished Claude owner before status check"
assert_equals "$(cat "$STUB_STATE/daemon-resume.uuid")" "dddddddd-1111-2222-3333-444444444444" "engine-less meta routed to daemon-resume"
assert_contains "$(cat "$STUB_STATE/daemon-resume.msg")" "already on the ticket" "--posted relays a pointer, not a body"
assert_equals "$(state "len([c for c in s['issues']['$ans_t']['comments'] if c.startswith('[answers]')])")" "2" "--posted posts its own [answers] marker (the mechanical convergence reset)"

# a mid-turn session is refused — nothing is waiting for answers
run board-transition.sh "$ans_t" needs-human "round 3 questions" >/dev/null
python3 - <<WORKING
import json, os
p = os.path.join(os.environ["DAEMON_HOME"], "dddddddd-1111-2222-3333-444444444444.json")
m = json.load(open(p)); m["status"] = "working"; m["turn_state"] = "busy"; json.dump(m, open(p, "w"))
WORKING
assert_fails run board-answer.sh "$ans_t" "late answer"
assert_contains "$(state "s['issues']['$ans_t']['labels']")" "status:needs-human" "active-owner refusal leaves the ticket parked"

# Dead/error/retired owners are fresh-dispatch cases: never transition the
# ticket to in-progress and attempt a doomed resume.
python3 - <<ABSENT
import json,os
p=os.path.join(os.environ['DAEMON_HOME'],'dddddddd-1111-2222-3333-444444444444.json')
m=json.load(open(p)); m['status']='working'; m['turn_state']='absent'; json.dump(m,open(p,'w'))
ABSENT
assert_fails run board-answer.sh "$ans_t" "after dead owner"
assert_contains "$(cat "$STUB_STATE/retire.log")" "dddddddd-1111-2222-3333-444444444444" "absent owner is retired for fresh dispatch"
assert_contains "$(state "s['issues']['$ans_t']['labels']")" "status:needs-human" "absent owner leaves ticket needs-human"
python3 - <<ERROR
import json,os
p=os.path.join(os.environ['DAEMON_HOME'],'dddddddd-1111-2222-3333-444444444444.json')
m=json.load(open(p)); m['status']='error'; json.dump(m,open(p,'w'))
ERROR
assert_fails run board-answer.sh "$ans_t" "after error"
python3 - <<RETIRED
import json,os
p=os.path.join(os.environ['DAEMON_HOME'],'dddddddd-1111-2222-3333-444444444444.json')
m=json.load(open(p)); m['status']='retired'; json.dump(m,open(p,'w'))
RETIRED
assert_fails run board-answer.sh "$ans_t" "after retirement"
assert_contains "$(state "s['issues']['$ans_t']['labels']")" "status:needs-human" "terminal owners never orphan the ticket in-progress"

# lane-aware return: an architect park's answer resumes into in-design
out="$(run board-register.sh "Architect answer probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY")"
ans_arch_t="${out%% *}"
run board-transition.sh "$ans_arch_t" in-design >/dev/null
run board-transition.sh "$ans_arch_t" needs-human "Q: layout A or B?" >/dev/null
cat > "$DAEMON_HOME/eeeeeeee-1111-2222-3333-444444444444.json" <<META
{"uuid": "eeeeeeee-1111-2222-3333-444444444444", "engine": "codex",
 "status": "idle", "ticket": "$ans_arch_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META
run board-answer.sh "$ans_arch_t" "layout A" >/dev/null
assert_contains "$(state "s['issues']['$ans_arch_t']['labels']")" "status:in-design" "answered architect park resumes into in-design"

# lane-aware return: an in-review park's answer resumes into in-review
# WITHOUT re-supplying --pr (regression test for the merge blocker: the
# invariant is "a ticket in in-review always has a PR recorded", not
# "every entry needs the flag" — PRE_PARK["in-review"] = "in-review"
# relies on the pr: meta already recorded at the original entry).
out="$(run board-register.sh "In-review answer probe" enhancement P2 --body-file "$SPEC_BODY")"
ans_rev_t="${out%% *}"
run board-transition.sh "$ans_rev_t" in-progress >/dev/null
run board-transition.sh "$ans_rev_t" in-review "opened PR" --pr https://github.com/test/repo/pull/77 >/dev/null
run board-transition.sh "$ans_rev_t" needs-human "reviewer flagged a design gap" >/dev/null
cat > "$DAEMON_HOME/ffffffff-1111-2222-3333-444444444444.json" <<META
{"uuid": "ffffffff-1111-2222-3333-444444444444", "status": "idle", "ticket": "$ans_rev_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META
run board-answer.sh "$ans_rev_t" "still looks right" >/dev/null
assert_contains "$(state "s['issues']['$ans_rev_t']['labels']")" "status:in-review" "answered in-review park resumes into in-review without re-supplying --pr"

# ---- unrecorded pre-park fallback is lane-aware (Finding D) --------------------
# PRE_PARK has no entry for needs-info (or interactive-preferred/deferred),
# so a needs-human park reached via needs-info records no pre-park: meta.
# board-answer's fallback must consult the BOUND worker's own role (persisted
# at spawn by implement-dispatch.sh) rather than hardcoding in-progress — an
# Architect resumed into in-progress has no legal exit from it.
echo "unrecorded pre-park fallback:"
out="$(run board-register.sh "Architect fallback probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY")"
fb_arch_t="${out%% *}"
run board-transition.sh "$fb_arch_t" needs-info "need more research" >/dev/null
run board-transition.sh "$fb_arch_t" needs-human "human decision needed" >/dev/null
assert_not_contains "$(state "s['issues']['$fb_arch_t']['body']")" "pre-park:" "needs-info -> needs-human records no pre-park (PRE_PARK has no needs-info entry)"
cat > "$DAEMON_HOME/11111111-1111-2222-3333-444444444444.json" <<META
{"uuid": "11111111-1111-2222-3333-444444444444", "role": "ARCHITECT",
 "status": "idle", "ticket": "$fb_arch_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META
run board-answer.sh "$fb_arch_t" "layout A" >/dev/null
assert_contains "$(state "s['issues']['$fb_arch_t']['labels']")" "status:in-design" "unrecorded pre-park falls back on the bound Architect's own lane (in-design), never a hardcoded in-progress"

out="$(run board-register.sh "Implement fallback probe" enhancement P2 --body-file "$SPEC_BODY")"
fb_impl_t="${out%% *}"
run board-transition.sh "$fb_impl_t" needs-info "need more research" >/dev/null
run board-transition.sh "$fb_impl_t" needs-human "human decision needed" >/dev/null
cat > "$DAEMON_HOME/22222222-1111-2222-3333-444444444444.json" <<META
{"uuid": "22222222-1111-2222-3333-444444444444", "role": "IMPLEMENT",
 "status": "idle", "ticket": "$fb_impl_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META
run board-answer.sh "$fb_impl_t" "answer" >/dev/null
assert_contains "$(state "s['issues']['$fb_impl_t']['labels']")" "status:in-progress" "unrecorded pre-park with a non-architect role falls back on in-progress"

out="$(run board-register.sh "Unknown-role fallback probe" enhancement P2 --body-file "$SPEC_BODY")"
fb_unk_t="${out%% *}"
run board-transition.sh "$fb_unk_t" needs-info "need more research" >/dev/null
run board-transition.sh "$fb_unk_t" needs-human "human decision needed" >/dev/null
cat > "$DAEMON_HOME/33333333-1111-2222-3333-444444444444.json" <<META
{"uuid": "33333333-1111-2222-3333-444444444444",
 "status": "idle", "ticket": "$fb_unk_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META
run board-answer.sh "$fb_unk_t" "answer" >/dev/null
assert_contains "$(state "s['issues']['$fb_unk_t']['labels']")" "status:in-progress" "a meta with no role at all (pre-fix daemon) preserves the prior default: in-progress"

unset DAEMON_SCRIPTS STUB_STATE

# ---- spike lane (category spike) ---------------------------------------------
echo "spike category:"
spike_t="$(run board-register.sh "Spike: is X feasible" spike P2  --body-file "$SPEC_BODY" | awk '{print $1}')"
assert_equals "$(state "s['issues']['$spike_t']['labels']")" "['spike', 'status:ready-for-implementer', 'priority:P2']" "spike category + status + priority labels"
assert_contains "$(state "s['labels']")" "spike" "spike label auto-created by ensure_labels"
assert_contains "$(run board-list.sh)" "spike" "board-list shows the spike category"
run board-transition.sh "$spike_t" in-progress >/dev/null
out="$(run board-transition.sh "$spike_t" needs-human "findings ready: X is feasible via Y")"
assert_contains "$(state "s['issues']['$spike_t']['comments'][-1]")" "findings ready" "spike handoff park lands with its note"
run board-transition.sh "$spike_t" "done" >/dev/null   # the human read the findings
assert_equals "$(state "s['issues']['$spike_t']['state']")" "CLOSED" "needs-human → done: the human closes a read spike directly"

# ---- pre-spec guard (the #567 hole) --------------------------------------------
# A ticket whose body is still the pre-spec skeleton was born ready-for-implementer
# and auto-dispatched to an implementer 45 seconds later — before any spec
# existed. A skeleton is never implementable: explicit ready-for-implementer birth
# refuses it, a default birth demotes to needs-info, and the promotion to
# ready-for-implementer re-checks the body.
echo "pre-spec guard:"
assert_fails run board-register.sh "Skeleton explicit" bug P2 --state ready-for-implementer
out="$(run board-register.sh "Skeleton follow-up" bug P2 --spawned-by 2)"
skel="${out%% *}"
assert_contains "$(state "s['issues']['$skel']['labels']")" "status:needs-info" "default skeleton birth demotes to needs-info"
assert_not_contains "$(state "s['issues']['$skel']['labels']")" "status:ready-for-implementer" "a skeleton is never born ready-for-implementer"
assert_contains "$(state "s['issues']['$skel']['comments'][0]")" "pre-spec" "demotion posts the spec-pending note"
assert_fails run board-transition.sh "$skel" ready-for-implementer
SKEL="$skel" python3 - <<'PY'
import json, os
p = os.environ["MOCK_GH_STATE"]
s = json.load(open(p))
s["issues"][os.environ["SKEL"]]["body"] = "## Problem & intent\n\nnow specified\n"
json.dump(s, open(p, "w"))
PY
out="$(run board-transition.sh "$skel" ready-for-implementer)"
assert_contains "$(state "s['issues']['$skel']['labels']")" "status:ready-for-implementer" "a filled body promotes to ready-for-implementer"
# a body-file that still carries the placeholder is a skeleton too
printf '## Problem & intent\n\n_(pre-spec: fill in)_\n' > "$TEST_ROOT/still-skel.md"
assert_fails run board-register.sh "Still skeleton" bug P2 --state ready-for-implementer --body-file "$TEST_ROOT/still-skel.md"

# ---- lane births (E1 birth classification) ------------------------------------
echo "lane births:"
out="$(run board-register.sh "Design-heavy epic work" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY")"
arch_t="${out%% *}"
assert_contains "$(state "s['issues']['$arch_t']['labels']")" "status:ready-for-architect" "explicit architect-lane birth honored"
out="$(run board-register.sh "Default lane probe" enhancement P2 --body-file "$SPEC_BODY")"
impl_t="${out%% *}"
assert_contains "$(state "s['issues']['$impl_t']['labels']")" "status:ready-for-implementer" "default birth is the implementer lane (unsure → implementer)"
assert_fails run board-register.sh "Arch skeleton" bug P2 --state ready-for-architect   # skeleton refused in BOTH lanes

# ---- spike / ready-for-architect: the ban is RETIRED ---------------------------
# Finding A banned a leaf spike from this queue at both the source
# (registration) and every transition into it, because role resolution was
# category-first: the spike protocol dispatched from either lane queue and its
# gate-pass write (`in-progress`) has no LEGAL edge from ready-for-architect.
# implement-dispatch.sh now routes that queue on STATE, so the ticket gets an
# ARCHITECT and its exit is `in-design`. Both gates are gone and these two
# asserts are the old refusals INVERTED — a design-first leaf spike is a
# supported route.
echo "spike/architect-lane (ban retired):"
spike_birth_t="$(run board-register.sh "Spike arch birth" spike P2 --state ready-for-architect --body-file "$SPEC_BODY" | awk '{print $1}')"
assert_contains "$(state "s['issues']['$spike_birth_t']['labels']")" "status:ready-for-architect" "a leaf spike may be BORN into the architect queue"
run board-transition.sh "$spike_birth_t" in-design >/dev/null
assert_contains "$(state "s['issues']['$spike_birth_t']['labels']")" "status:in-design" "...and its architect-lane exit is legal"
spike_ban_t="$(run board-register.sh "Spike transition probe" spike P2 --body-file "$SPEC_BODY" | awk '{print $1}')"
run board-transition.sh "$spike_ban_t" in-progress >/dev/null
run board-transition.sh "$spike_ban_t" ready-for-architect "needs design first" >/dev/null
assert_contains "$(state "s['issues']['$spike_ban_t']['labels']")" "status:ready-for-architect" "a leaf spike may be TRANSITIONED into the architect queue"
# The spike EPIC case that motivated the ban's leaf-hood carve-out still works,
# now for the general reason rather than a special one: the state decides.
run board-register.sh "Spike that decomposed" spike P1 --body-file "$SPEC_BODY" >/dev/null
spike_epic_t="$(state "s['next']-1")"
run board-register.sh "Spike epic child" enhancement P2 --parent "$spike_epic_t" --body-file "$SPEC_BODY" >/dev/null
spike_kid_t="$(state "s['next']-1")"
run board-transition.sh "$spike_kid_t" in-progress >/dev/null
run board-transition.sh "$spike_kid_t" "done" >/dev/null            # epic → ready-for-architect
run board-transition.sh "$spike_epic_t" in-design >/dev/null
run board-transition.sh "$spike_epic_t" in-review --pr "https://github.com/o/r/issues/$spike_epic_t#pkg" >/dev/null
out="$(run board-transition.sh "$spike_epic_t" ready-for-architect "scale review: corrective child")"
assert_contains "$out" "#$spike_epic_t: in-review → ready-for-architect" "a spike EPIC takes the architect-queue edge (epic rules, not category)"
assert_contains "$(state "s['issues']['$spike_epic_t']['labels']")" "status:ready-for-architect" "and lands there instead of sitting mislabeled in-review"

# ---- lane display (E1: list/map render the new lane states) -------------------
# $arch_t (registered just above) is still ready-for-architect: nothing between
# its birth and here transitions it.
echo "lane display:"
assert_contains "$(run board-list.sh)" "ELIGIBLE" "board-list still tags eligibility"
assert_contains "$(run board-list.sh ready-for-architect)" "ready-for-architect" "state filter works for the architect queue"
out="$(run board-map.sh)"
assert_contains "$out" "ready-for-architect · ELIGIBLE" "board-map table shows lane + eligibility"

# ---- plan meta (E1 transitions 2 and 3) ---------------------------------------
echo "plan meta:"
run board-register.sh "Architect handoff probe" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
plan_t="$(state "s['next']-1")"
run board-transition.sh "$plan_t" in-design >/dev/null
out="$(run board-transition.sh "$plan_t" ready-for-implementer "plan ready: do X then Y" --branch tick/plan-probe --plan "docs/plans/x.md@0123456789abcdef0123456789abcdef01234567")"
assert_contains "$(state "s['issues']['$plan_t']['body']")" "plan: docs/plans/x.md@0123456789abcdef0123456789abcdef01234567" "plan pin recorded in board:meta"
assert_contains "$(state "s['issues']['$plan_t']['body']")" "branch: tick/plan-probe" "branch recorded on the handoff"
run board-register.sh "Shortcircuit probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
sc_t="$(state "s['next']-1")"
run board-transition.sh "$sc_t" in-design >/dev/null
out="$(run board-transition.sh "$sc_t" ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec)"
assert_contains "$(state "s['issues']['$sc_t']['body']")" "plan: pre-spec" "down-shortcircuit sentinel recorded"
assert_fails run board-transition.sh "$plan_t" in-progress --plan "also/here.md@0123456789abcdef0123456789abcdef01234567"   # --plan only on the handoff edge
# The EDGE, not the destination: every other legal promotion INTO
# ready-for-implementer (a park return) would otherwise mint a plan pin,
# and a pin is what makes the implementer skip its gate (PLAN-EXECUTION).
run board-register.sh "Park-return plan probe" enhancement P2 --state needs-info \
  --note "waiting on a spec detail" --body-file "$SPEC_BODY" >/dev/null
pr_t="$(state "s['next']-1")"
plan_err="$(run board-transition.sh "$pr_t" ready-for-implementer "unparked" \
  --plan "docs/sneaky.md@0123456789abcdef0123456789abcdef01234567" 2>&1 || true)"
assert_contains "$plan_err" "in-design → ready-for-implementer" "the refusal names the full edge, not just the destination"
assert_contains "$(state "s['issues']['$pr_t']['labels']")" "status:needs-info" "the refused park return wrote nothing"
assert_not_contains "$(state "s['issues']['$pr_t']['body']")" "plan:" "a park return can never mint a plan pin"

# ---- plan pin auto-clear (Finding B) -------------------------------------------
# A superseded plan: pin is void by definition on two edges: any entry into
# ready-for-architect (the design is being re-cut), and the Architect's own
# decompose exit in-design -> ready-for-implementer with no --plan (a
# positive "no plan" statement). Reproduces the reviewer's exact sequence:
# --plan -> in-progress -> ready-for-architect "blocked" -> in-design ->
# ready-for-implementer "decomposed" (no --plan) must leave no plan: pin —
# otherwise an Implementer enters gate-free PLAN-EXECUTION against a plan
# the Architect just declared blocked.
echo "plan pin auto-clear:"
run board-register.sh "Plan clear probe" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pc_t="$(state "s['next']-1")"
run board-transition.sh "$pc_t" in-design >/dev/null
run board-transition.sh "$pc_t" ready-for-implementer "plan ready" --branch tick/plan-clear --plan "docs/p.md@0123456789abcdef0123456789abcdef01234567" >/dev/null
assert_contains "$(state "s['issues']['$pc_t']['body']")" "plan: docs/p.md@0123456789abcdef0123456789abcdef01234567" "pin recorded before the escalation"
run board-transition.sh "$pc_t" in-progress >/dev/null
run board-transition.sh "$pc_t" ready-for-architect "plan is blocked" >/dev/null
assert_not_contains "$(state "s['issues']['$pc_t']['body']")" "plan: docs/p.md" "entry into ready-for-architect clears the superseded plan pin"
run board-transition.sh "$pc_t" in-design >/dev/null
run board-transition.sh "$pc_t" ready-for-implementer "decomposed" >/dev/null
assert_not_contains "$(state "s['issues']['$pc_t']['body']")" "plan:" "decompose exit with no --plan leaves no stale plan pin behind"

# Deliberately NOT auto-cleared: a human unparking from needs-human back to
# ready-for-implementer must not silently void a still-valid plan.
run board-register.sh "Plan keep probe" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pk_t="$(state "s['next']-1")"
run board-transition.sh "$pk_t" in-design >/dev/null
run board-transition.sh "$pk_t" ready-for-implementer "plan ready" --branch tick/plan-keep --plan "docs/q.md@0123456789abcdef0123456789abcdef01234567" >/dev/null
run board-transition.sh "$pk_t" needs-human "unrelated human question" >/dev/null
run board-transition.sh "$pk_t" ready-for-implementer >/dev/null
assert_contains "$(state "s['issues']['$pk_t']['body']")" "plan: docs/q.md@0123456789abcdef0123456789abcdef01234567" "a needs-human unpark does not void a still-valid plan pin"

# ---- epic pull routing (Finding C) ----------------------------------------------
# The pull walks DISPATCHABLE parents, but LEGAL["ready-for-architect"] has no
# in-progress edge — the first active child of an epic sitting in the design
# QUEUE must pull it to in-design (PRE_PARK's queue -> in-flight mapping),
# never the illegal in-progress.
echo "epic pull routing:"
run board-register.sh "Design epic" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
epic_c_t="$(state "s['next']-1")"
run board-register.sh "Epic child" enhancement P2 --parent "$epic_c_t" --body-file "$SPEC_BODY" >/dev/null
child_c_t="$(state "s['next']-1")"
out="$(run board-transition.sh "$child_c_t" in-progress)"
assert_contains "$out" "#$epic_c_t: ready-for-architect → in-design" "epic parked ready-for-architect is pulled to in-design, not the illegal in-progress"
assert_contains "$(state "s['issues']['$epic_c_t']['labels']")" "status:in-design" "epic label reflects the legal in-flight state"
assert_not_contains "$(state "s['issues']['$epic_c_t']['labels']")" "status:in-progress" "epic never carries the illegal edge's label"

# PULL_FROM = the two lane queues + needs-info, and the discriminant is the
# park CONTRACT. needs-info is fold-and-recut: no bound session, no relay
# entry, and on an epic it is the reconciling Architect's release exit
# ("waiting on children") — so a child going active is the very information
# that park names, and the pull IS the wake. It lands in-progress (PRE_PARK
# has no needs-info entry, so the default applies) and folds the park's note.
run board-register.sh "Released epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
epic_ni_t="$(state "s['next']-1")"
run board-register.sh "Released epic child" enhancement P2 --parent "$epic_ni_t" --body-file "$SPEC_BODY" >/dev/null
child_ni_t="$(state "s['next']-1")"
run board-transition.sh "$epic_ni_t" needs-info "reconciled: acceptance holds — waiting on children" >/dev/null
out="$(run board-transition.sh "$child_ni_t" in-progress)"
assert_contains "$out" "#$epic_ni_t: needs-info → in-progress" "a needs-info release IS pulled back in-flight by a child going active"
assert_contains "$(state "s['issues']['$epic_ni_t']['body']")" "(was: reconciled: acceptance holds — waiting on children)" "the pull folds the release note into its bookkeeping note"
# ACTIVE, not in-progress: an architect-lane child entering in-design is its
# epic's first active child exactly as an implementer-lane child is — and the
# from-non-ACTIVE half keeps the pull to ENTRIES, so a later in-review does
# not re-fire it.
run board-register.sh "Design-lane released epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
epic_ad_t="$(state "s['next']-1")"
run board-register.sh "Design-lane child" enhancement P2 --parent "$epic_ad_t" \
  --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
child_ad_t="$(state "s['next']-1")"
run board-transition.sh "$epic_ad_t" needs-info "reconciled: still waiting on children" >/dev/null
out="$(run board-transition.sh "$child_ad_t" in-design)"
assert_contains "$out" "#$epic_ad_t: needs-info → in-progress" "a child entering in-design pulls its released parent in-flight"
assert_contains "$(state "s['issues']['$epic_ad_t']['body']")" "(was: reconciled: still waiting on children)" "the in-design pull folds the release note too"
run board-transition.sh "$child_ad_t" ready-for-implementer "plan cut" --plan pre-spec >/dev/null
run board-transition.sh "$child_ad_t" in-progress >/dev/null
out="$(run board-transition.sh "$child_ad_t" in-review "PR up" --pr https://github.com/test/repo/pull/91)"
assert_not_contains "$out" "#$epic_ad_t:" "in-review is only ever entered from an active state — the pull does not re-fire"

# The other three parks own a bound session (needs-human) or a claim on the
# human (interactive-preferred, deferred) and are never disturbed by
# bookkeeping. deferred first — and its own transition stays illegal for a
# worker/human too (LEGAL["deferred"] has no in-progress edge), so nothing
# can skip the queue and the gate this way.
run board-register.sh "Deferred epic" enhancement P1 --state deferred --body-file "$SPEC_BODY" >/dev/null
epic_def_t="$(state "s['next']-1")"
run board-register.sh "Deferred epic child" enhancement P2 --parent "$epic_def_t" --body-file "$SPEC_BODY" >/dev/null
child_def_t="$(state "s['next']-1")"
out="$(run board-transition.sh "$child_def_t" in-progress)"
assert_not_contains "$out" "#$epic_def_t:" "a deferred epic's active child does not pull it out of the park"
assert_contains "$(state "s['issues']['$epic_def_t']['labels']")" "status:deferred" "the deferred epic stays parked"
run board-register.sh "Plain deferred ticket" enhancement P2 --state deferred --body-file "$SPEC_BODY" >/dev/null
plain_def_t="$(state "s['next']-1")"
assert_fails run board-transition.sh "$plain_def_t" in-progress   # LEGAL["deferred"] unchanged: no gate-skip for a worker/human
run board-register.sh "Steered epic" enhancement P1 --state interactive-preferred \
  --note "the spine needs live steering" --body-file "$SPEC_BODY" >/dev/null
epic_ip_t="$(state "s['next']-1")"
run board-register.sh "Steered epic child" enhancement P2 --parent "$epic_ip_t" --body-file "$SPEC_BODY" >/dev/null
child_ip_t="$(state "s['next']-1")"
out="$(run board-transition.sh "$child_ip_t" in-progress)"
assert_not_contains "$out" "#$epic_ip_t:" "an interactive-preferred epic's child does not pull it off the human's attention"
assert_contains "$(state "s['issues']['$epic_ip_t']['labels']")" "status:interactive-preferred" "the steered epic stays parked"

# needs-human is the session-resume contract: a bound worker waits on the
# answer, and the sweep's RELAY pass selects on THAT state to find it. A
# child going active must not silently remove the epic from that queue —
# the child transitions, the epic does not move, its note survives intact.
run board-register.sh "Parked epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
epic_pk_t="$(state "s['next']-1")"
run board-register.sh "Parked epic child" enhancement P2 --parent "$epic_pk_t" --body-file "$SPEC_BODY" >/dev/null
child_pk_t="$(state "s['next']-1")"
run board-transition.sh "$epic_pk_t" needs-human "Q: which flavor?" >/dev/null
out="$(run board-transition.sh "$child_pk_t" in-progress)"
assert_contains "$out" "#$child_pk_t: ready-for-implementer → in-progress" "the child of a needs-human epic still goes active"
assert_not_contains "$out" "#$epic_pk_t:" "the pull reports no write on the parked epic"
assert_contains "$(state "s['issues']['$epic_pk_t']['labels']")" "status:needs-human" "the epic stays in the human's wake queue"
assert_contains "$(state "s['issues']['$epic_pk_t']['body']")" "note: Q: which flavor?" "the park's own note is untouched by the child's dispatch"
# recompose_epics is the ONE bookkeeping write that still unparks an epic —
# nothing but a recomposition verdict can close it — and it folds the park's
# note into its own instead of overwriting it.
out="$(run board-transition.sh "$child_pk_t" "done")"
assert_contains "$out" "#$epic_pk_t: needs-human → ready-for-architect" "the last child's landing returns the parked epic for recomposition"
assert_contains "$(state "s['issues']['$epic_pk_t']['body']")" "recomposition-due: all children terminal (was: Q: which flavor?)" "the recomposition return preserves the park's note"
# an IN-FLIGHT epic's note is the board's own previous line — simply replaced
assert_not_contains "$(state "s['issues']['$epic_c_t']['body']")" "(was:" "an unparked epic's pull note carries no fold"

# ---- pre-park + lane-aware answer return (E1 transition 7) --------------------
echo "pre-park returns:"
run board-register.sh "Architect park probe" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pp_t="$(state "s['next']-1")"
run board-transition.sh "$pp_t" in-design >/dev/null
run board-transition.sh "$pp_t" needs-human "Q1: layout A or B? (rec: A)" >/dev/null
assert_contains "$(state "s['issues']['$pp_t']['body']")" "pre-park: in-design" "architect park records its in-flight return target"
out="$(run board-transition.sh "$pp_t" in-design "answers relayed")"
assert_contains "$out" "#$pp_t: needs-human → in-design" "needs-human → in-design is a legal return"
assert_not_contains "$(state "s['issues']['$pp_t']['body']")" "pre-park:" "return clears the pre-park meta"
# gate-fail park from the architect QUEUE also returns to in-design
run board-register.sh "Gate-fail park probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
gf_t="$(state "s['next']-1")"
run board-transition.sh "$gf_t" needs-human "gate fail: purpose unstated" >/dev/null
assert_contains "$(state "s['issues']['$gf_t']['body']")" "pre-park: in-design" "architect-queue gate-fail park targets in-design"

# ---- edge notes + convergence (E1 transitions 4/5/6) --------------------------
echo "convergence:"
run board-register.sh "Escalation probe" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
cv_t="$(state "s['next']-1")"
assert_fails run board-transition.sh "$cv_t" ready-for-architect            # edge note required
out="$(run board-transition.sh "$cv_t" ready-for-architect "gate: plan-need — multi-milestone")"
assert_contains "$out" "#$cv_t: ready-for-implementer → ready-for-architect" "gate escalation applied"
assert_contains "$(state "s['issues']['$cv_t']['comments'][-1]")" "[board] ready-for-implementer → ready-for-architect: gate: plan-need" "escalation comment carries the edge"
# complete a design pass, execute, then hit the SAME escalation edge again
run board-transition.sh "$cv_t" in-design >/dev/null
run board-transition.sh "$cv_t" ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec >/dev/null
out="$(run board-transition.sh "$cv_t" ready-for-architect "still believe plan-need")"
assert_contains "$out" "#$cv_t: ready-for-implementer → needs-human" "second traversal of the same edge converts to needs-human"
assert_contains "$(state "s['issues']['$cv_t']['body']")" "convergence: second traversal" "conversion note names the convergence rule"
assert_contains "$(state "s['issues']['$cv_t']['body']")" "pre-park: in-progress" "converted park still records a return target"
# an [answers] comment resets the count: a sanctioned re-traversal of the
# SAME edge passes. Fresh ticket (the converted one is parked) — the reset
# only proves anything on the edge that was previously counted.
run board-register.sh "Escalation probe 2" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
cv2_t="$(state "s['next']-1")"
run board-transition.sh "$cv2_t" ready-for-architect "gate: plan-need — round 1" >/dev/null
run board-transition.sh "$cv2_t" in-design >/dev/null
run board-transition.sh "$cv2_t" ready-for-implementer "plan cut" --plan pre-spec >/dev/null
CV2_T="$cv2_t" python3 - <<'ANS'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
t = os.environ["CV2_T"]
s["issues"][t]["comments"].append("[answers] yes — architect may take it again")
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
ANS
out="$(run board-transition.sh "$cv2_t" ready-for-architect "human-sanctioned re-escalation")"
assert_contains "$out" "#$cv2_t: ready-for-implementer → ready-for-architect" "same-edge re-traversal passes after [answers] reset (no needs-human conversion)"

# ---- mid-execution return edge: in-progress → ready-for-architect -------------
# The Implementer's escalation when a plan turns out genuinely unbuildable
# mid-build (E1's fourth new edge) — distinct from the ready-for-implementer →
# ready-for-architect gate-fail edge exercised above. It is convergence-counted
# too (EDGE_NOTE_REQUIRED minus only the in-design→ready-for-implementer
# carve-out), so it must both require a note and emit the arrow-keyed comment.
echo "mid-execution return:"
run board-register.sh "Mid-execution return probe" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
mer_t="$(state "s['next']-1")"
run board-transition.sh "$mer_t" in-progress >/dev/null
assert_fails run board-transition.sh "$mer_t" ready-for-architect           # edge note required
out="$(run board-transition.sh "$mer_t" ready-for-architect "blocked: plan assumed an API that doesn't exist")"
assert_contains "$out" "#$mer_t: in-progress → ready-for-architect" "mid-execution return applied (legal edge)"
assert_contains "$(state "s['issues']['$mer_t']['comments'][-1]")" "[board] in-progress → ready-for-architect: blocked: plan assumed an API that doesn't exist" "escalation comment carries the arrow-keyed edge form (convergence-counted)"

# ---- convergence reset via --posted relay --------------------------------------
# The unattended sweep's RELAY pass always calls board-answer.sh --posted (the
# human commented directly on the ticket, never through board-answer's inline
# --answers arg). board-transition's convergence-park reset fires only at a
# comment prefixed [answers] — if --posted never posted one, a resumed
# worker's human-authorized retry of the SAME escalation edge would be
# bounced right back to needs-human: exactly the livelock the human's answer
# was meant to end. Reuses the board-answer daemon stubs.
echo "convergence reset (--posted relay):"
STUB_DS2="$TEST_ROOT/stub-daemon-scripts-2"; mkdir -p "$STUB_DS2"
STUB_STATE2="$TEST_ROOT/stub-state-2"; mkdir -p "$STUB_STATE2"
export STUB_STATE="$STUB_STATE2"
cat > "$STUB_DS2/daemon-resume.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$1" > "$STUB_STATE/daemon-resume.uuid"
printf '%s' "$2" > "$STUB_STATE/daemon-resume.msg"
echo "resumed: [daemon stub]"
STUB
chmod +x "$STUB_DS2/daemon-resume.sh"
cat > "$STUB_DS2/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
echo noop
STUB
chmod +x "$STUB_DS2/daemon-finalize.sh"
cat > "$STUB_DS2/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
true
STUB
chmod +x "$STUB_DS2/daemon-retire.sh"
export DAEMON_SCRIPTS="$STUB_DS2"

run board-register.sh "Convergence reset probe" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
cr_t="$(state "s['next']-1")"
run board-transition.sh "$cr_t" in-progress >/dev/null
run board-transition.sh "$cr_t" ready-for-architect "blocked: issue A" >/dev/null                    # 1st traversal
run board-transition.sh "$cr_t" in-design >/dev/null
run board-transition.sh "$cr_t" ready-for-implementer "plan ready" --branch tick/conv-reset --plan "docs/plan.md@0123456789abcdef0123456789abcdef01234567" >/dev/null
run board-transition.sh "$cr_t" in-progress >/dev/null
out="$(run board-transition.sh "$cr_t" ready-for-architect "blocked: issue A again")"                # 2nd traversal
assert_contains "$out" "#$cr_t: in-progress → needs-human" "2nd traversal converts (unreset baseline)"
cat > "$DAEMON_HOME/99999999-1111-2222-3333-444444444444.json" <<META
{"uuid": "99999999-1111-2222-3333-444444444444", "status": "idle", "ticket": "$cr_t", "cwd": "$WORK",
 "updated": "2026-07-12T00:00:00Z"}
META
run board-answer.sh "$cr_t" --posted >/dev/null
assert_contains "$(state "s['issues']['$cr_t']['comments'][-2]")" "[answers]" "--posted relay posts an [answers] marker for the mechanical reset"
out="$(run board-transition.sh "$cr_t" ready-for-architect "blocked: issue A still")"                # 3rd traversal
assert_contains "$out" "#$cr_t: in-progress → ready-for-architect" "3rd traversal after a --posted relay does NOT convert (reset fired)"
unset DAEMON_SCRIPTS STUB_STATE

# The counter is comment-CONTROLLED board behavior: on a public consumer repo
# an outsider could pre-seed an edge marker (forcing the next legitimate
# traversal into a needs-human park) or post [answers] (buying unbounded
# bounces). Only repo-side authors count or reset — every board and worker
# write is the token identity, i.e. OWNER.
echo "convergence author trust:"
seed_comment() {  # <ticket> <authorAssociation> <body>
    T_N="$1" T_ASSOC="$2" T_BODY="$3" python3 - <<'PY'
import json, os
p = os.environ["MOCK_GH_STATE"]
with open(p) as f:
    s = json.load(f)
s["issues"][os.environ["T_N"]]["comments"].append(
    {"body": os.environ["T_BODY"], "authorAssociation": os.environ["T_ASSOC"]})
with open(p, "w") as f:
    json.dump(s, f)
PY
}
run board-register.sh "Untrusted marker probe" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
ut_t="$(state "s['next']-1")"
seed_comment "$ut_t" NONE "[board] ready-for-implementer → ready-for-architect: pre-seeded by a stranger"
out="$(run board-transition.sh "$ut_t" ready-for-architect "gate: plan-need")"
assert_contains "$out" "#$ut_t: ready-for-implementer → ready-for-architect" "an outsider's pre-seeded edge marker is not counted as a traversal"
assert_not_contains "$(state "s['issues']['$ut_t']['labels']")" "status:needs-human" "so the FIRST legitimate traversal is not converted into a park"

run board-register.sh "Untrusted answers probe" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
ua_t="$(state "s['next']-1")"
run board-transition.sh "$ua_t" ready-for-architect "gate: plan-need" >/dev/null
run board-transition.sh "$ua_t" in-design >/dev/null
run board-transition.sh "$ua_t" ready-for-implementer "plan cut" --plan pre-spec >/dev/null
seed_comment "$ua_t" NONE "[answers] go ahead, bounce it as often as you like"
out="$(run board-transition.sh "$ua_t" ready-for-architect "second time")"
assert_contains "$out" "#$ua_t: ready-for-implementer → needs-human" "an outsider's [answers] does not reset the count"

# The count reads the WHOLE comment log, not page 1 (R2). `gh issue view
# --json comments` serves a single page, so on a busy ticket the earlier
# traversal falls off the read and the bounce that should have parked the
# ticket is waved through — the convergence rule silently stops applying to
# exactly the tickets that bounce most. Two seeded comments sit ahead of the
# first marker here and the mock's page is shrunk to two, so a page-1 reader
# sees chatter only.
echo "convergence past page 1:"
export MOCK_GH_COMMENT_PAGE=2
run board-register.sh "Long-trail convergence probe" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
pg_t="$(state "s['next']-1")"
seed_comment "$pg_t" OWNER "worker chatter that predates the first escalation"
seed_comment "$pg_t" OWNER "more chatter, same"
run board-transition.sh "$pg_t" ready-for-architect "gate: plan-need — round 1" >/dev/null
run board-transition.sh "$pg_t" in-design >/dev/null
run board-transition.sh "$pg_t" ready-for-implementer "plan cut" --plan pre-spec >/dev/null
out="$(run board-transition.sh "$pg_t" ready-for-architect "second traversal, buried first one")"
assert_contains "$out" "#$pg_t: ready-for-implementer → needs-human" \
    "a traversal marker past page 1 is still counted (paginated read)"
unset MOCK_GH_COMMENT_PAGE

# ---- a real plan pin needs a branch the sha is reachable from -----------------
# The pin authorizes gate-free PLAN-EXECUTION, and the worker starts from a
# fresh cattle clone: with no recorded ref there is nothing to fetch the sha
# from, so the pin cannot serve the reclaim contract it exists for.
echo "plan pin reachability:"
PIN="docs/plans/reach.md@0123456789abcdef0123456789abcdef01234567"
run board-register.sh "Pin reachability probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pr1_t="$(state "s['next']-1")"
run board-transition.sh "$pr1_t" in-design >/dev/null
pin_err="$(run board-transition.sh "$pr1_t" ready-for-implementer "plan ready" --plan "$PIN" 2>&1 || true)"
assert_contains "$pin_err" "needs a recorded branch the sha is reachable" "a pinned plan with no branch anywhere is refused"
assert_contains "$(state "s['issues']['$pr1_t']['labels']")" "status:in-design" "the refused handoff wrote nothing"
out="$(run board-transition.sh "$pr1_t" ready-for-implementer "plan ready" --branch tick/reach --plan "$PIN")"
assert_contains "$out" "#$pr1_t: in-design → ready-for-implementer" "the same handoff passes with --branch"
# a branch already in meta satisfies it — the ref is recorded either way
run board-register.sh "Pin with prior branch" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pr2_t="$(state "s['next']-1")"
run board-transition.sh "$pr2_t" in-design "claimed" --branch tick/earlier >/dev/null
out="$(run board-transition.sh "$pr2_t" ready-for-implementer "plan ready" --plan "$PIN")"
assert_contains "$out" "#$pr2_t: in-design → ready-for-implementer" "a branch: already in meta satisfies the pin's reachability"
# pre-spec names no revision — the issue body IS the plan, so no branch is owed
run board-register.sh "Pre-spec needs no branch" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pr3_t="$(state "s['next']-1")"
run board-transition.sh "$pr3_t" in-design >/dev/null
out="$(run board-transition.sh "$pr3_t" ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec)"
assert_contains "$out" "#$pr3_t: in-design → ready-for-implementer" "the pre-spec sentinel still needs no branch"

# A recorded branch is not a FETCHABLE artifact. A mistyped or unpushed sha,
# or one whose tree lacks the named path, still minted gate-free
# PLAN-EXECUTION against something no cattle clone can fetch — the worker
# would discover it only after the gate was already skipped. Both checks are
# remote and both fail CLOSED, API errors included.
echo "plan pin verification:"
mk_probe() {  # -> a fresh ticket sitting in in-design
    run board-register.sh "$1" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
    probe_t="$(state "s['next']-1")"
    run board-transition.sh "$probe_t" in-design >/dev/null
}
mk_probe "Pin off-branch probe"
off_t="$probe_t"
err="$(run board-transition.sh "$off_t" ready-for-implementer "plan ready" --branch tick/nowhere --plan "docs/plans/reach.md@$SHA40" 2>&1 || true)"
assert_contains "$err" "cannot verify the plan pin against branch tick/nowhere" "an unverifiable branch/sha pair is refused"
assert_contains "$(state "s['issues']['$off_t']['labels']")" "status:in-design" "the refused handoff wrote nothing"

# the sha resolves but is NOT an ancestor of the branch (ahead/diverged)
python3 - <<'REFS'
import json, os
p = os.environ["MOCK_GH_REFS"]
refs = json.load(open(p))
sha = "0123456789abcdef0123456789abcdef01234567"
refs["compare"]["tick/diverged...%s" % sha] = "diverged"
json.dump(refs, open(p, "w"))
REFS
mk_probe "Pin diverged probe"
div_t="$probe_t"
err="$(run board-transition.sh "$div_t" ready-for-implementer "plan ready" --branch tick/diverged --plan "docs/plans/reach.md@$SHA40" 2>&1 || true)"
assert_contains "$err" "is not on branch tick/diverged (compare says diverged)" "a sha that is not on the branch is refused"

# the sha is on the branch, but the tree has no such path
python3 - <<'REFS'
import json, os
p = os.environ["MOCK_GH_REFS"]
refs = json.load(open(p))
sha = "0123456789abcdef0123456789abcdef01234567"
refs["compare"]["tick/reach...%s" % sha] = "identical"
json.dump(refs, open(p, "w"))
REFS
mk_probe "Pin missing-path probe"
mp_t="$probe_t"
err="$(run board-transition.sh "$mp_t" ready-for-implementer "plan ready" --branch tick/reach --plan "docs/plans/absent.md@$SHA40" 2>&1 || true)"
assert_contains "$err" "does not exist at 0123456789ab" "a path absent at the pinned sha is refused"
assert_contains "$(state "s['issues']['$mp_t']['labels']")" "status:in-design" "that refusal wrote nothing either"

# an API error is not a pass: an unverifiable pin is not a pin
python3 - <<'REFS'
import json, os
p = os.environ["MOCK_GH_REFS"]
refs = json.load(open(p))
refs["fail"] = ["/compare/tick/flaky"]
json.dump(refs, open(p, "w"))
REFS
mk_probe "Pin API-error probe"
api_t="$probe_t"
err="$(run board-transition.sh "$api_t" ready-for-implementer "plan ready" --branch tick/flaky --plan "docs/plans/reach.md@$SHA40" 2>&1 || true)"
assert_contains "$err" "the pin is refused until it verifies" "an API error fails CLOSED"
python3 - <<'REFS'
import json, os
p = os.environ["MOCK_GH_REFS"]
refs = json.load(open(p)); refs.pop("fail", None)
json.dump(refs, open(p, "w"))
REFS

# ...and a pin that verifies on both counts still passes
mk_probe "Pin good probe"
good_t="$probe_t"
out="$(run board-transition.sh "$good_t" ready-for-implementer "plan ready" --branch tick/reach --plan "docs/plans/reach.md@$SHA40")"
assert_contains "$out" "#$good_t: in-design → ready-for-implementer" "a pin that verifies on both counts passes"
assert_contains "$(state "s['issues']['$good_t']['body']")" "plan: docs/plans/reach.md@$SHA40" "and is recorded"

# ---- in-design orphan (board-reconcile) ----------------------------------------
# The missing-daemon check must cover the Architect's in-flight state too,
# not just the Implementer's — an orphaned in-design ticket is mid-design
# work with nothing local to show for it until its next park/handoff.
echo "in-design orphan (board-reconcile):"
run board-register.sh "In-design orphan probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
id_orphan_t="$(state "s['next']-1")"
run board-transition.sh "$id_orphan_t" in-design >/dev/null      # no bound daemon
out="$(run board-reconcile.sh)"
assert_contains "$out" "orphaned  #$id_orphan_t: in-design" "orphaned in-design flagged (Architect's in-flight state)"
# ...but a PULLED epic is in-design by bookkeeping and has no daemon by
# design: a corrective child going active drags its queued parent here
# (PRE_PARK) and the children are the ones working. Calling that orphaned
# invents work, and acting on the advice puts a second Architect on a live
# epic. Three shapes, one discriminant — the children.
run board-register.sh "Pulled epic probe" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
pull_e="$(state "s['next']-1")"
run board-register.sh "Its corrective child" bug P1 --parent "$pull_e" --body-file "$SPEC_BODY" >/dev/null
pull_c="$(state "s['next']-1")"
run board-transition.sh "$pull_e" ready-for-architect "gate: recomposition" >/dev/null
run board-transition.sh "$pull_c" in-progress >/dev/null        # pulls the parent to in-design
assert_contains "$(state "s['issues']['$pull_e']['labels']")" "status:in-design" "the child's activation pulled the parent to in-design"
out="$(run board-reconcile.sh)"
assert_contains "$out" "pulled    #$pull_e: in-design by the epic pull" "a pulled epic reports as bookkeeping, not as an orphan"
assert_not_contains "$out" "orphaned  #$pull_e" "...and never asks the operator to respawn a worker onto it"
# The discriminant is the note the PULL wrote, not "has live children". An
# Architect actively RECONCILING an epic sits in in-design WITH live children
# by definition, so a children-only test hid exactly the stranded claim this
# report exists to surface. Same board shape as above, different note.
PULL_E="$pull_e" python3 - <<'NOTE'
import json, os
p = os.environ["MOCK_GH_STATE"]
s = json.load(open(p))
it = s["issues"][os.environ["PULL_E"]]
it["body"] = it["body"].replace("note: epic: child", "note: reconciled: waiting on child")
json.dump(s, open(p, "w"))
NOTE
out="$(run board-reconcile.sh)"
assert_contains "$out" "orphaned  #$pull_e: in-design" "an in-design epic with live children but no pull note is a stranded claim, and is warned about"
assert_not_contains "$out" "pulled    #$pull_e" "...and is not written off as bookkeeping"
# all children terminal: this IS a recomposition claim that should have a
# live Architect, so the warning comes back
run board-transition.sh "$pull_c" "done" >/dev/null             # epic → ready-for-architect
run board-transition.sh "$pull_e" in-design >/dev/null          # claimed, but no daemon bound
out="$(run board-reconcile.sh)"
assert_contains "$out" "orphaned  #$pull_e: in-design" "an epic whose children are all terminal is a possibly-abandoned claim"

# ---- env-issue category (E2 interim slice) --------------------------------------
echo "env-issue category:"
# default birth inverts to needs-human (spec v2.1 birth rule)
out="$(run board-register.sh "Registry flakes on pull" env-issue P2 \
  --note "need registry mirror credentials rotated" --body-file "$SPEC_BODY")"
env_t="$(state "s['next']-1")"
assert_contains "$(state "s['issues']['$env_t']['labels']")" "env-issue" "env-issue category label applied"
assert_contains "$(state "s['issues']['$env_t']['labels']")" "status:needs-human" "env-issue defaults to needs-human, not ready-for-implementer"
# the label is board-managed: ensure_labels created it in the mock label store
assert_contains "$(state "sorted(s['labels'])")" "env-issue" "ensure_labels creates the env-issue label"
# default birth without a note is refused (needs-human requires one)
assert_fails run board-register.sh "Mystery env pain" env-issue P2 --body-file "$SPEC_BODY"
# a named repair path births an agent lane explicitly
run board-register.sh "Pin the broken fixture image" env-issue P2 \
  --state ready-for-implementer --body-file "$SPEC_BODY" >/dev/null
env_a="$(state "s['next']-1")"
assert_contains "$(state "s['issues']['$env_a']['labels']")" "status:ready-for-implementer" "explicit agent-lane env-issue birth allowed"
# filing never touches another ticket: register with --spawned-by and assert source unchanged
run board-register.sh "Source ticket" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
src_t="$(state "s['next']-1")"
run board-transition.sh "$src_t" in-progress >/dev/null
before="$(state "sorted(s['issues']['$src_t']['labels'])")"
run board-register.sh "Flaky DNS in CI" env-issue P3 \
  --note "needs infra DNS fix" --spawned-by "$src_t" --body-file "$SPEC_BODY" >/dev/null
assert_equals "$(state "sorted(s['issues']['$src_t']['labels'])")" "$before" "env-issue filing leaves the source ticket untouched"

# ---- recomposition lifecycle (E2) -----------------------------------------------
echo "recomposition:"
run board-register.sh "Recomp epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
rc_e="$(state "s['next']-1")"
run board-register.sh "Recomp child A" enhancement P2 --parent "$rc_e" --body-file "$SPEC_BODY" >/dev/null
rc_a="$(state "s['next']-1")"
run board-register.sh "Recomp child B" enhancement P2 --parent "$rc_e" --body-file "$SPEC_BODY" >/dev/null
rc_b="$(state "s['next']-1")"
run board-transition.sh "$rc_a" in-progress >/dev/null
# all-wontfix epic also returns (the one-done guard is retired)
run board-transition.sh "$rc_a" wontfix "not needed" >/dev/null
out="$(run board-transition.sh "$rc_b" wontfix "not needed either")"
assert_contains "$out" "#$rc_e: in-progress → ready-for-architect" "all-wontfix epic returns for recomposition (guard retired)"
# the return's audit comment is the bookkeeping marker, not the convergence format
assert_contains "$(state "s['issues']['$rc_e']['comments'][-1]")" "[board-epic]" "recomposition return posts the board-epic marker"
# board-list must show an operator what the dispatcher will actually claim:
# a recomposition-due epic is eligible, and the epic tag alone hid that.
list_rc="$(run board-list.sh)"
assert_contains "$(grep -E "^#$rc_e " <<<"$list_rc" || true)" "[epic ELIGIBLE]" "a recomposition-due epic lists as eligible"
# same predicate, one surface over: the map's fallback table
map_rc="$(run board-map.sh)"
assert_contains "$(grep -F "| #$rc_e |" <<<"$map_rc" || true)" "ready-for-architect · ELIGIBLE" "the map marks the recomposition-due epic eligible too"
assert_not_contains "$(state "s['issues']['$rc_e']['comments'][-1]")" "[board] in-progress → ready-for-architect:" "return never writes the convergence-counted format"
# second cycle: corrective child, land it, return fires again w/o needs-human conversion
run board-register.sh "Recomp gap child" enhancement P2 --parent "$rc_e" --body-file "$SPEC_BODY" >/dev/null
rc_c="$(state "s['next']-1")"
run board-transition.sh "$rc_c" in-progress >/dev/null
# the gap child's pull maps the ready-for-architect epic to in-design
# (PRE_PARK), so the second return fires from in-design, not in-progress
out="$(run board-transition.sh "$rc_c" "done")"
assert_contains "$out" "#$rc_e: in-design → ready-for-architect" "second recomposition cycle returns again"
assert_not_contains "$(state "s['issues']['$rc_e']['labels']")" "status:needs-human" "bookkeeping returns never trip the convergence counter"

# Architect recomposition verdict paths (epic-guarded edges)
run board-transition.sh "$rc_e" in-design >/dev/null           # Architect claims
list_rc2="$(run board-list.sh)"
assert_contains "$(grep -E "^#$rc_e " <<<"$list_rc2" || true)" "[epic]" "a claimed (in-design) epic still lists its epic tag"
assert_not_contains "$(grep -E "^#$rc_e " <<<"$list_rc2" || true)" "ELIGIBLE" "an in-design epic is not eligible — nothing dispatches it"
out="$(run board-transition.sh "$rc_e" "done")"
assert_contains "$out" "#$rc_e: in-design → done" "recomposition Architect closes a non-code epic from in-design"
assert_equals "$(state "s['issues']['$rc_e']['stateReason']")" "COMPLETED" "epic closed as completed"
# a LEAF may never use the epic edges
run board-register.sh "Leaf in design" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
leaf_t="$(state "s['next']-1")"
run board-transition.sh "$leaf_t" in-design >/dev/null
assert_fails run board-transition.sh "$leaf_t" "done"
assert_fails run board-transition.sh "$leaf_t" in-review --pr "https://example.com/pkg"
# wontfix is the THIRD terminal out of in-design and LEGAL has it, so the
# guard has to cover it or an epic can be abandoned with children still
# running — every recomposition invariant bypassed by picking a different
# terminal. Epics only: the leaf case below is pinned unchanged on purpose.
echo "epic wontfix guard:"
run board-register.sh "Abandonable epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
wf_e="$(state "s['next']-1")"
run board-register.sh "Its live child" enhancement P2 --parent "$wf_e" --body-file "$SPEC_BODY" >/dev/null
wf_c="$(state "s['next']-1")"
run board-transition.sh "$wf_e" ready-for-architect "gate: design the epic" >/dev/null
run board-transition.sh "$wf_e" in-design >/dev/null
run board-transition.sh "$wf_c" in-progress >/dev/null
assert_fails run board-transition.sh "$wf_e" wontfix "abandon it"
assert_contains "$(state "s['issues']['$wf_e']['labels']")" "status:in-design" "the epic with a live child is not abandoned"
assert_equals "$(state "s['issues']['$wf_e']['state']")" "OPEN" "...and its issue is not closed behind the board's back"
run board-transition.sh "$wf_c" "done" >/dev/null               # epic → ready-for-architect
run board-transition.sh "$wf_e" in-design >/dev/null            # Architect re-claims
out="$(run board-transition.sh "$wf_e" wontfix "recomposed: not worth building")"
assert_contains "$out" "#$wf_e: in-design → wontfix" "a recomposition-ready epic may still be wontfixed"
# LEAF wontfix from in-design is untouched by this guard — pinning today's
# behavior explicitly so the guard's scope is visible, not adjudicating it.
run board-register.sh "Leaf abandoned mid-design" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
wf_l="$(state "s['next']-1")"
run board-transition.sh "$wf_l" in-design >/dev/null
out="$(run board-transition.sh "$wf_l" wontfix "not worth designing further")"
assert_contains "$out" "#$wf_l: in-design → wontfix" "a LEAF wontfix from in-design keeps whatever legality it had"
# code-bearing epic routes in-review with the closure package as the pr slot
run board-register.sh "Code epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
ce_e="$(state "s['next']-1")"
run board-register.sh "Code child" enhancement P2 --parent "$ce_e" --body-file "$SPEC_BODY" >/dev/null
ce_c="$(state "s['next']-1")"
run board-transition.sh "$ce_c" in-progress >/dev/null
run board-transition.sh "$ce_c" "done" >/dev/null                 # epic → ready-for-architect
run board-transition.sh "$ce_e" in-design >/dev/null
assert_fails run board-transition.sh "$ce_e" in-review          # package required
out="$(run board-transition.sh "$ce_e" in-review --pr "https://github.com/o/r/issues/$ce_e#closure-package" --branch epic/integration-1)"
assert_contains "$out" "#$ce_e: in-design → in-review" "code-bearing epic enters scale review with the closure package"
assert_contains "$(state "s['issues']['$ce_e']['body']")" "branch: epic/integration-1" "the Architect supplies this cycle's integration ref alongside the package"

# Second recomposition cycle: the scale review found a defect, so a corrective
# child is registered and the epic waits for it again.
run board-transition.sh "$ce_e" ready-for-architect "scale review: corrective child" >/dev/null
run board-register.sh "Corrective child" bug P1 --parent "$ce_e" --body-file "$SPEC_BODY" >/dev/null
ce_x="$(state "s['next']-1")"
# ready-for-architect but NOT eligible: a nonterminal corrective child means
# no recomposition claim, and there is no reconciliation-due note either. Both
# operator surfaces must agree with the dispatcher, not with a blocker check.
map_ce="$(run board-map.sh)"
assert_not_contains "$(grep -F "| #$ce_e |" <<<"$map_ce" || true)" "ELIGIBLE" "the map does not mark an epic with a live corrective child eligible"
list_ce="$(run board-list.sh)"
assert_not_contains "$(grep -E "^#$ce_e " <<<"$list_ce" || true)" "ELIGIBLE" "nor does board-list"
out="$(run board-transition.sh "$ce_x" in-progress)"
assert_contains "$out" "#$ce_e: ready-for-architect → in-design" "the corrective child pulls the waiting epic back in-flight"
# The verdict edges are RECOMPOSITION edges: an epic holding a reconciliation
# claim over live children may not close or open a scale review early.
assert_fails run board-transition.sh "$ce_e" "done"
assert_fails run board-transition.sh "$ce_e" in-review --pr "https://github.com/o/r/issues/$ce_e#pkg-2"
out="$(run board-transition.sh "$ce_x" "done")"
assert_contains "$out" "#$ce_e: in-design → ready-for-architect" "the corrective child's landing returns the epic for a second recomposition"
assert_not_contains "$(state "s['issues']['$ce_e']['body']")" "pr: https" "the recomposition return clears the previous cycle's closure package"
assert_not_contains "$(state "s['issues']['$ce_e']['body']")" "branch:" "...and the integration ref with it — both describe a composition that just changed"
run board-transition.sh "$ce_e" in-design >/dev/null
assert_fails run board-transition.sh "$ce_e" in-review   # the cleared slot demands a FRESH package
out="$(run board-transition.sh "$ce_e" in-review --pr "https://github.com/o/r/issues/$ce_e#pkg-2")"
assert_contains "$out" "#$ce_e: in-design → in-review" "a fresh closure package re-enters scale review"
out="$(run board-transition.sh "$ce_e" "done")"
assert_contains "$out" "#$ce_e: in-review → done" "clean scale review closes the epic"

# ---- in-review entry: a stale pr: never satisfies a fresh entry ---------------
# pr: survives every route back out of in-review (a review that bounced the
# ticket to ready-for-architect leaves it behind; only recomposition clears
# it), so honoring the meta on ANY entry pointed the board at a superseded PR
# — or, on an epic, at the previous cycle's closure package. Only the park
# return whose pre-park: records in-review may ride the recorded value.
# ---- recomposition bookkeeping on an ALREADY-queued epic ----------------------
# The return carries cycle-scoped writes now — clearing pr/branch and emitting
# the [board-epic] comment that resets the convergence count — so a corrective
# child landing BEFORE an Architect claims the queued epic is a new cycle that
# still owes all three. Only the state write is skipped.
echo "recomposition bookkeeping (queued epic):"
run board-register.sh "Queued cycle epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
qc_e="$(state "s['next']-1")"
run board-register.sh "Queued cycle child" enhancement P2 --parent "$qc_e" --body-file "$SPEC_BODY" >/dev/null
qc_c="$(state "s['next']-1")"
run board-transition.sh "$qc_c" in-progress >/dev/null
run board-transition.sh "$qc_c" "done" >/dev/null                  # epic → ready-for-architect
run board-transition.sh "$qc_e" in-design >/dev/null
run board-transition.sh "$qc_e" in-review --pr "https://github.com/o/r/issues/$qc_e#pkg-a" --branch epic/cycle-a >/dev/null
run board-transition.sh "$qc_e" ready-for-architect "scale review: corrective child" >/dev/null
run board-register.sh "Queued cycle corrective" bug P1 --parent "$qc_e" --body-file "$SPEC_BODY" >/dev/null
qc_x="$(state "s['next']-1")"
# The corrective child reaches terminal without any Architect ever claiming
# the epic — it is closed straight from the queue (wontfix needs no active
# turn, so no pull moves the epic), leaving it in ready-for-architect with
# the reviewer's note still on it.
assert_contains "$(state "s['issues']['$qc_e']['labels']")" "status:ready-for-architect" "the epic is still queued, unclaimed"
before_marks="$(state "sum(1 for c in s['issues']['$qc_e']['comments'] if '[board-epic] ready-for-architect:' in str(c))")"
out="$(run board-transition.sh "$qc_x" wontfix "not needed after all")"
assert_contains "$out" "#$qc_e: already ready-for-architect — recomposition bookkeeping refreshed" "the queued epic's bookkeeping still runs, and says so"
assert_contains "$(state "s['issues']['$qc_e']['labels']")" "status:ready-for-architect" "the state write is the only thing skipped"
assert_not_contains "$(state "s['issues']['$qc_e']['body']")" "branch: epic/cycle-a" "the previous cycle's integration ref is cleared"
assert_not_contains "$(state "s['issues']['$qc_e']['body']")" "pkg-a" "and its closure package with it"
assert_contains "$(state "s['issues']['$qc_e']['body']")" "note: recomposition-due: all children terminal" "the reviewer's note gives way to the recomposition-due one"
after_marks="$(state "sum(1 for c in s['issues']['$qc_e']['comments'] if '[board-epic] ready-for-architect:' in str(c))")"
assert_equals "$after_marks" "$((before_marks + 1))" "the cycle-reset comment is emitted"
# idempotence: everything is already folded and cleared, so a re-run is silent
out="$(run board-transition.sh "$qc_x" wontfix "still not needed")"
assert_not_contains "$out" "recomposition bookkeeping refreshed" "a re-run with the bookkeeping already done writes nothing"
assert_equals "$(state "sum(1 for c in s['issues']['$qc_e']['comments'] if '[board-epic] ready-for-architect:' in str(c))")" "$after_marks" "...and posts no second cycle-reset comment"
# the reset this path emitted is a real convergence boundary
run board-transition.sh "$qc_e" in-design >/dev/null
run board-transition.sh "$qc_e" in-review --pr "https://github.com/o/r/issues/$qc_e#pkg-b" >/dev/null
out="$(run board-transition.sh "$qc_e" ready-for-architect "scale review: a different defect")"
assert_contains "$out" "#$qc_e: in-review → ready-for-architect" "the escalation after this path's reset is not a mechanical bounce"
assert_not_contains "$(state "s['issues']['$qc_e']['labels']")" "status:needs-human" "so no spurious needs-human park"

echo "in-review entry guard:"
run board-register.sh "Stale PR probe" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
sp_t="$(state "s['next']-1")"
run board-transition.sh "$sp_t" in-progress >/dev/null
run board-transition.sh "$sp_t" in-review "round 1" --pr https://github.com/test/repo/pull/90 >/dev/null
run board-transition.sh "$sp_t" ready-for-architect "review found a design gap" >/dev/null
run board-transition.sh "$sp_t" in-design >/dev/null
run board-transition.sh "$sp_t" ready-for-implementer "re-cut" >/dev/null
run board-transition.sh "$sp_t" in-progress >/dev/null
assert_contains "$(state "s['issues']['$sp_t']['body']")" "pr: https://github.com/test/repo/pull/90" "the superseded pr: is still on the ticket (nothing clears it on a leaf)"
sp_err="$(run board-transition.sh "$sp_t" in-review "round 2" 2>&1 || true)"
assert_contains "$sp_err" "Only a park return" "a fresh in-review entry may not ride the recorded pr:"
assert_contains "$(state "s['issues']['$sp_t']['labels']")" "status:in-progress" "the refused entry wrote nothing"
out="$(run board-transition.sh "$sp_t" in-review "round 2" --pr https://github.com/test/repo/pull/92)"
assert_contains "$out" "#$sp_t: in-progress → in-review" "a fresh entry passes with its own --pr"
# the park return still rides the meta — that is the whole point of pre-park
run board-transition.sh "$sp_t" needs-human "push conflict — needs a human" >/dev/null
assert_contains "$(state "s['issues']['$sp_t']['body']")" "pre-park: in-review" "the in-review park records its return target"
out="$(run board-transition.sh "$sp_t" in-review "answered")"
assert_contains "$out" "#$sp_t: needs-human → in-review" "a pre-park: in-review return needs no --pr"

# The same return, on an EPIC — this is the path the capped scale-review park
# tells the human to take (reply, then board-transition <n> in-review), so it
# has to work end to end with the closure package the epic already carries.
run board-register.sh "Capped scale epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
cs_e="$(state "s['next']-1")"
run board-register.sh "Capped scale child" enhancement P2 --parent "$cs_e" --body-file "$SPEC_BODY" >/dev/null
cs_c="$(state "s['next']-1")"
run board-transition.sh "$cs_c" in-progress >/dev/null
run board-transition.sh "$cs_c" "done" >/dev/null                 # epic → ready-for-architect
run board-transition.sh "$cs_e" in-design >/dev/null
run board-transition.sh "$cs_e" in-review --pr "https://github.com/o/r/issues/$cs_e#pkg" >/dev/null
run board-transition.sh "$cs_e" needs-human "scale review: the review engine was unavailable on 3 consecutive attempts; this reviewer was retired, so there is no session to resume — reply on this ticket, then run board-transition.sh $cs_e in-review (no --pr needed) and the next sweep dispatches a fresh reviewer" >/dev/null
assert_contains "$(state "s['issues']['$cs_e']['body']")" "pre-park: in-review" "the capped-scale park records in-review as its return target"
out="$(run board-transition.sh "$cs_e" in-review "answered: retry the review")"
assert_contains "$out" "#$cs_e: needs-human → in-review" "the recipe in the park note works: the epic returns with no --pr"
assert_contains "$(state "s['issues']['$cs_e']['body']")" "pr: https://github.com/o/r/issues/$cs_e#pkg" "the closure package it returns with is the one it carried"

# ---- convergence resets at a recomposition-cycle boundary ---------------------
# Two successive closure packages that each turn up a real defect are not a
# mechanical bounce: the second escalation is about a package that did not
# exist during the first. The board's own [board-epic] ready-for-architect:
# return is what marks the boundary.
echo "convergence across recomposition cycles:"
run board-register.sh "Cycle epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
cy_e="$(state "s['next']-1")"
run board-register.sh "Cycle child A" enhancement P2 --parent "$cy_e" --body-file "$SPEC_BODY" >/dev/null
cy_a="$(state "s['next']-1")"
run board-transition.sh "$cy_a" in-progress >/dev/null
run board-transition.sh "$cy_a" "done" >/dev/null                 # [board-epic] return #1
run board-transition.sh "$cy_e" in-design >/dev/null
run board-transition.sh "$cy_e" in-review --pr "https://github.com/o/r/issues/$cy_e#pkg-1" >/dev/null
out="$(run board-transition.sh "$cy_e" ready-for-architect "scale review: defect — corrective child")"
assert_contains "$out" "#$cy_e: in-review → ready-for-architect" "first cycle's escalation is an ordinary traversal"
run board-register.sh "Cycle child B" enhancement P2 --parent "$cy_e" --body-file "$SPEC_BODY" >/dev/null
cy_b="$(state "s['next']-1")"
run board-transition.sh "$cy_b" in-progress >/dev/null
out="$(run board-transition.sh "$cy_b" "done")"
assert_contains "$out" "#$cy_e: in-design → ready-for-architect" "the corrective child's landing opens a NEW recomposition cycle"
run board-transition.sh "$cy_e" in-design >/dev/null
run board-transition.sh "$cy_e" in-review --pr "https://github.com/o/r/issues/$cy_e#pkg-2" >/dev/null
out="$(run board-transition.sh "$cy_e" ready-for-architect "scale review: a different defect in the NEW package")"
assert_contains "$out" "#$cy_e: in-review → ready-for-architect" "the second cycle's escalation is not a mechanical bounce"
assert_not_contains "$(state "s['issues']['$cy_e']['labels']")" "status:needs-human" "the [board-epic] return reset the convergence count"
# ...and WITHOUT a boundary between them, the conversion still fires: same
# edge twice inside one cycle is exactly what the rule is for.
run board-transition.sh "$cy_e" in-design >/dev/null
run board-transition.sh "$cy_e" in-review --pr "https://github.com/o/r/issues/$cy_e#pkg-2" >/dev/null
out="$(run board-transition.sh "$cy_e" ready-for-architect "same package, same complaint")"
assert_contains "$out" "#$cy_e: in-review → needs-human" "a second traversal inside ONE cycle still converts to needs-human"

echo "board-migrate-gh (retired v6 state):"
# A legacy ticket in the RETIRED v6 queue state, migrated on its own board so
# the numbering above is untouched. v9 split ready-for-agent into the two lane
# queues and dropped its label, so passing it straight to set_state_label
# leaves the issue in `conflict`. It must land in ready-for-implementer — the
# disposition board-lint.sh's FIX text prescribes for the same legacy label.
run board-register.sh "Legacy agent-queue ticket" enhancement P2 \
  --state needs-human --note "parked before the migration" >/dev/null
legacy_rfa="$(state "s['next']-1")"
cat > "$LEGACY/board-v6.json" <<J
{"version": 1, "next_id": 2, "tickets": {
  "T1": {"title": "Legacy agent-queue ticket", "md": "tickets/T3.md",
         "state": "ready-for-agent", "category": "enhancement", "note": null,
         "parent": null, "blocked_by": [], "spawned_by": null, "relates_to": [],
         "branch": null, "pr": null, "created": "2026-07-01",
         "updated": "2026-07-05", "gh": $legacy_rfa}
}}
J
printf -- '---\nid: T3\n---\n# T3\n' > "$LEGACY/tickets/T3.md"
out="$(run board-migrate-gh.sh --board "$LEGACY/board-v6.json" --apply)"
assert_contains "$(state "s['issues']['$legacy_rfa']['labels']")" "status:ready-for-implementer" \
  "the retired ready-for-agent state migrates into the implementer queue"
assert_not_contains "$(state "s['issues']['$legacy_rfa']['labels']")" "status:ready-for-agent" \
  "no issue is ever labelled with the retired state"
assert_not_contains "$(state "s['issues']['$legacy_rfa']['labels']")" "status:needs-human" \
  "the superseded label is swapped out, not left alongside (that would read as conflict)"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
