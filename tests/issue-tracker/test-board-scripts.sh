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
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
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
# A filled spec body: ready-for-agent births require one (a pre-spec skeleton
# is never implementable — see the pre-spec guard section).
SPEC_BODY="$TEST_ROOT/spec-body.md"
printf '## Problem & intent\n\nA real spec.\n\n## Success criteria\n\n- verifiable\n' > "$SPEC_BODY"

# ---- register ----------------------------------------------------------------
echo "board-register:"
out="$(run board-register.sh "Epic: alpha" enhancement P2 --body-file "$SPEC_BODY")"
assert_contains "$out" "1 https://github.com/test/repo/issues/1" "prints number + url"
assert_equals "$(state "s['issues']['1']['labels']")" "['enhancement', 'status:ready-for-agent', 'priority:P2']" "category + birth status + priority labels"

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
assert_contains "$out" "#3: ready-for-agent → in-progress" "transition applied"
assert_contains "$out" "#1: ready-for-agent → in-progress" "epic pulled by first active child"
assert_contains "$(state "s['issues']['3']['labels']")" "status:in-progress" "label swapped"
assert_not_contains "$(state "s['issues']['3']['labels']")" "status:ready-for-agent" "old label removed"

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
assert_contains "$out" "#1: in-progress → done" "epic closes when all children terminal, one done"
assert_equals "$(state "s['issues']['1']['stateReason']")" "COMPLETED" "epic closed as completed"

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
assert_contains "$out" "#8: ready-for-agent → in-progress" "in-progress child pulls new epic"

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

out="$(run board-transition.sh 9 ready-for-agent)"               # repair path: untracked → open state
assert_contains "$(state "s['issues']['9']['labels']")" "status:ready-for-agent" "repair labels untracked issue"
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
# waiting on the lock while the ticket transitions ready-for-agent→needs-human:
# a pre-lock snapshot would wrongly strip the newly parked owner.
python3 - <<'PY'
import json,os
p=os.environ['MOCK_GH_STATE']; s=json.load(open(p)); src=dict(s['issues']['8'])
src.update(number=999,id='ID_999',title='bind race park',state='OPEN',stateReason=None,
           labels=['bug','status:ready-for-agent','priority:P2'],body='## Problem & intent\n\nrace')
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
assert_contains "$out" '"state": "ready-for-agent"' "show prints node"

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
  "T2": {"title": "Unlinked new", "md": "tickets/T2.md", "state": "ready-for-agent",
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
assert_contains "$out" "#11: in-progress → done" "finalize closes the epic"
assert_equals "$(state "s['issues']['11']['stateReason']")" "COMPLETED" "epic closed as completed"
assert_contains "$out" "now eligible: #13" "finalize reports unblocked dependent"

out="$(run board-transition.sh 12 "done")"                          # idempotent re-run
assert_contains "$out" "now eligible: #13" "finalize re-run is safe"
assert_fails run board-transition.sh 12 wontfix "flip"            # done → wontfix still illegal
assert_fails run board-transition.sh 13 ready-for-agent           # already ready (open states still die)

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
assert_contains "$out" "| #14 | P2 | ELIGIBLE · CLOSE? |" "md table marks the candidate"
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
out="$(run board-transition.sh 19 ready-for-agent)"
assert_contains "$out" "#19: interactive-preferred → ready-for-agent" "re-spec exit: settled decisions return it to the pool"
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
assert_contains "$out" "#20: ready-for-agent → needs-human" "gate-fail park applied"
out="$(run board-transition.sh 20 needs-info "research first: provider capability matrix")"
assert_contains "$out" "#20: needs-human → needs-info" "park-to-park re-triage legal"
out="$(run board-transition.sh 20 ready-for-agent)"
assert_contains "$out" "#20: needs-info → ready-for-agent" "answered park returns to ready"

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
assert_equals "$(state "len([c for c in s['issues']['$ans_t']['comments'] if c.startswith('[answers]')])")" "1" "--posted posts no second [answers] comment"

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
unset DAEMON_SCRIPTS STUB_STATE

# ---- spike lane (category spike) ---------------------------------------------
echo "spike category:"
spike_t="$(run board-register.sh "Spike: is X feasible" spike P2  --body-file "$SPEC_BODY" | awk '{print $1}')"
assert_equals "$(state "s['issues']['$spike_t']['labels']")" "['spike', 'status:ready-for-agent', 'priority:P2']" "spike category + status + priority labels"
assert_contains "$(state "s['labels']")" "spike" "spike label auto-created by ensure_labels"
assert_contains "$(run board-list.sh)" "spike" "board-list shows the spike category"
run board-transition.sh "$spike_t" in-progress >/dev/null
out="$(run board-transition.sh "$spike_t" needs-human "findings ready: X is feasible via Y")"
assert_contains "$(state "s['issues']['$spike_t']['comments'][-1]")" "findings ready" "spike handoff park lands with its note"
run board-transition.sh "$spike_t" "done" >/dev/null   # the human read the findings
assert_equals "$(state "s['issues']['$spike_t']['state']")" "CLOSED" "needs-human → done: the human closes a read spike directly"

# ---- pre-spec guard (the #567 hole) --------------------------------------------
# A ticket whose body is still the pre-spec skeleton was born ready-for-agent
# and auto-dispatched to an implementer 45 seconds later — before any spec
# existed. A skeleton is never implementable: explicit ready-for-agent birth
# refuses it, a default birth demotes to needs-info, and the promotion to
# ready-for-agent re-checks the body.
echo "pre-spec guard:"
assert_fails run board-register.sh "Skeleton explicit" bug P2 --state ready-for-agent
out="$(run board-register.sh "Skeleton follow-up" bug P2 --spawned-by 2)"
skel="${out%% *}"
assert_contains "$(state "s['issues']['$skel']['labels']")" "status:needs-info" "default skeleton birth demotes to needs-info"
assert_not_contains "$(state "s['issues']['$skel']['labels']")" "status:ready-for-agent" "a skeleton is never born ready-for-agent"
assert_contains "$(state "s['issues']['$skel']['comments'][0]")" "pre-spec" "demotion posts the spec-pending note"
assert_fails run board-transition.sh "$skel" ready-for-agent
SKEL="$skel" python3 - <<'PY'
import json, os
p = os.environ["MOCK_GH_STATE"]
s = json.load(open(p))
s["issues"][os.environ["SKEL"]]["body"] = "## Problem & intent\n\nnow specified\n"
json.dump(s, open(p, "w"))
PY
out="$(run board-transition.sh "$skel" ready-for-agent)"
assert_contains "$(state "s['issues']['$skel']['labels']")" "status:ready-for-agent" "a filled body promotes to ready-for-agent"
# a body-file that still carries the placeholder is a skeleton too
printf '## Problem & intent\n\n_(pre-spec: fill in)_\n' > "$TEST_ROOT/still-skel.md"
assert_fails run board-register.sh "Still skeleton" bug P2 --state ready-for-agent --body-file "$TEST_ROOT/still-skel.md"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
