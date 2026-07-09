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

# ---- register ----------------------------------------------------------------
echo "board-register:"
out="$(run board-register.sh "Epic: alpha" enhancement P2)"
assert_contains "$out" "1 https://github.com/test/repo/issues/1" "prints number + url"
assert_equals "$(state "s['issues']['1']['labels']")" "['enhancement', 'status:ready-for-agent', 'priority:P2']" "category + birth status + priority labels"

out="$(run board-register.sh $'Multi\nline title' bug P1 --state needs-human --note "waiting on A")"
assert_equals "$(state "s['issues']['2']['title']")" "Multi line title" "title newlines collapsed"
assert_contains "$(state "s['issues']['2']['labels']")" "status:needs-human" "birth state honored"
assert_contains "$(state "s['issues']['2']['comments'][0]")" "[board] needs-human: waiting on A" "birth note posted as [board] comment"
assert_contains "$(state "s['issues']['2']['body']")" "note: waiting on A" "birth note in board:meta"

out="$(run board-register.sh "Child A" enhancement P1 --parent 1 --spawned-by 2)"
assert_equals "$(state "s['issues']['3']['parent']")" "1" "parent sub-issue edge created"
assert_contains "$(state "s['issues']['3']['body']")" "spawned-by: #2" "spawned-by in board:meta"

out="$(run board-register.sh "Child B" enhancement P2 --parent 1 --blocked-by 3)"
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
run board-register.sh "Epic: beta" enhancement P2 >/dev/null                            # 5
run board-register.sh "B1" enhancement P2 --parent 5 >/dev/null                         # 6
run board-register.sh "B2" enhancement P2 --parent 5 --blocked-by 6 >/dev/null          # 7
run board-register.sh "Loose" enhancement P3 >/dev/null                                 # 8

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
out="$(run board-bind.sh aaaa 9)"
assert_contains "$out" "bound #9 ← aaaa-bbbb" "bind writes registry"
assert_equals "$(python3 -c "import json;print(json.load(open('$DAEMON_HOME/aaaa-bbbb.json'))['ticket'])")" "9" "registry meta has ticket"
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
run board-register.sh "Epic: delta" enhancement P2 >/dev/null                    # 11
run board-register.sh "D1" enhancement P0 --parent 11 >/dev/null                 # 12
run board-register.sh "D2" enhancement P2 --blocked-by 12 >/dev/null             # 13
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
run board-register.sh "Cand ready" enhancement P2 >/dev/null            # 14: closes MERGED + xref CLOSED
run board-register.sh "Abandoned only" enhancement P2 >/dev/null        # 15: closes CLOSED (no merge)
run board-register.sh "Still open PR" enhancement P2 >/dev/null         # 16: MERGED + xref OPEN
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
run board-register.sh "Review target" enhancement P2 >/dev/null                  # 17
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

run board-register.sh "CR map probe" enhancement P2 >/dev/null                    # 18
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
run board-register.sh "IP birth" enhancement P2 --state interactive-preferred --note "product-core: onboarding voice" >/dev/null   # 19
assert_contains "$(state "s['issues']['19']['labels']")" "status:interactive-preferred" "birth state honored"
out="$(run board-list.sh)"
line19="$(printf '%s\n' "$out" | grep '^#19 ')"
assert_not_contains "$line19" "ELIGIBLE" "interactive-preferred is never ELIGIBLE"
out="$(run board-transition.sh 19 in-progress)"
assert_contains "$out" "#19: interactive-preferred → in-progress" "human takes it up: in-progress legal"
assert_fails run board-transition.sh 19 interactive-preferred                  # note required
out="$(run board-transition.sh 19 interactive-preferred "back to parked")"
assert_contains "$out" "#19: in-progress → interactive-preferred" "in-progress → interactive-preferred legal (gate-fail mid-build)"
set +e
lint_out="$(run board-lint.sh 2>&1)"; lint_rc=$?
set -e
assert_equals "$lint_rc" "0" "board with a noted interactive-preferred ticket lints green"

# ---- needs-human (park: the human as themselves unparks) ---------------------
echo "needs-human:"
run board-register.sh "NH probe" enhancement P2 >/dev/null                     # 20
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

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
