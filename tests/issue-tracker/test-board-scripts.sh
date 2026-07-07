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
out="$(run board-register.sh "Epic: alpha" enhancement)"
assert_contains "$out" "1 https://github.com/test/repo/issues/1" "prints number + url"
assert_equals "$(state "s['issues']['1']['labels']")" "['enhancement', 'status:ready-for-agent']" "category + birth status label"

out="$(run board-register.sh $'Multi\nline title' bug --state blocked --note "waiting on A")"
assert_equals "$(state "s['issues']['2']['title']")" "Multi line title" "title newlines collapsed"
assert_contains "$(state "s['issues']['2']['labels']")" "status:blocked" "birth state honored"
assert_contains "$(state "s['issues']['2']['comments'][0]")" "[board] blocked: waiting on A" "birth note posted as [board] comment"
assert_contains "$(state "s['issues']['2']['body']")" "note: waiting on A" "birth note in board:meta"

out="$(run board-register.sh "Child A" enhancement --parent 1 --spawned-by 2)"
assert_equals "$(state "s['issues']['3']['parent']")" "1" "parent sub-issue edge created"
assert_contains "$(state "s['issues']['3']['body']")" "spawned-by: #2" "spawned-by in board:meta"

out="$(run board-register.sh "Child B" enhancement --parent 1 --blocked-by 3)"
assert_equals "$(state "s['issues']['4']['blockedBy']")" "[3]" "blocked_by dependency edge created"

assert_fails run board-register.sh "X" gadget
assert_fails run board-register.sh "X" bug --state needs-info          # note required
assert_fails run board-register.sh "X" bug --state "done"                # not a birth state
assert_fails run board-register.sh "X" bug --parent 999                # unknown ref

# ---- transition: legality + note/PR gates ------------------------------------
echo "board-transition:"
assert_fails run board-transition.sh 3 "done"                            # ready → done illegal
assert_fails run board-transition.sh 3 blocked                         # note required
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
assert_equals "$(state "s['issues']['3']['labels']")" "['enhancement']" "status labels stripped on close"
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
run board-register.sh "Epic: beta" enhancement >/dev/null                            # 5
run board-register.sh "B1" enhancement --parent 5 >/dev/null                         # 6
run board-register.sh "B2" enhancement --parent 5 --blocked-by 6 >/dev/null          # 7
run board-register.sh "Loose" enhancement >/dev/null                                 # 8

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
cat > "$DAEMON_HOME/aaaa-bbbb.reply.txt" <<'J'
work done, proposing:
{"ticket":"9","from":"in-progress","to":"in-review","reason":"PR open","evidence":"https://github.com/test/repo/pull/12"}
J
out="$(run board-reconcile.sh)"
assert_contains "$out" "proposal  #9: in-progress → in-review" "reconcile surfaces proposal"
assert_contains "$out" "board-transition.sh 9 in-review --pr https://github.com/test/repo/pull/12" "apply hint carries PR"
run board-transition.sh 7 in-progress >/dev/null 2>&1 || true    # 7 has no daemon
out="$(run board-reconcile.sh)"
assert_contains "$out" "orphaned  #7" "orphaned in-progress flagged"
assert_contains "$out" "board-lint" "reconcile ends with a lint pass"

# ---- map -------------------------------------------------------------------------
echo "board-map:"
out="$(run board-map.sh)"
assert_contains "$out" "| #9 |" "table row per ticket"
run board-map.sh --write >/dev/null 2>&1
assert_file_exists "$WORK/doperpowers/issue-tracker/BOARD.html" "BOARD.html rendered"
assert_file_exists "$WORK/doperpowers/issue-tracker/BOARD.md" "BOARD.md rendered"
assert_equals "$(cat "$WORK/doperpowers/issue-tracker/.gitignore")" "*" "render dir is gitignored"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"id": "#9"' "html payload uses display ids"

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
run board-register.sh "Epic: delta" enhancement >/dev/null                    # 11
run board-register.sh "D1" enhancement --parent 11 >/dev/null                 # 12
run board-register.sh "D2" enhancement --blocked-by 12 >/dev/null             # 13
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

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
