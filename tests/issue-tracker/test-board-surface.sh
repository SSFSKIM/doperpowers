#!/usr/bin/env bash
#
# Hermetic tests for the surface topology layer (spec:
# docs/doperpowers/specs/2026-08-10-surface-topology-design.md).
#
# Same harness as test-board-scripts.sh: the real scripts run end-to-end
# against the PATH-shimmed mock gh; the surfaces registry is a committed
# .doperpowers/surfaces.md in the throwaway repo, read via SURFACES_REF=HEAD
# (production resolves the remote default branch; the env override IS the
# tested seam). Acceptance numbers cited from the spec.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/issue-tracker/scripts"

FAILURES=0
ASSERTIONS=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; ASSERTIONS=$((ASSERTIONS + 1)); }
fail() {
    echo "  [FAIL] $1"
    ASSERTIONS=$((ASSERTIONS + 1))
    FAILURES=$((FAILURES + 1))
}
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_fails() { # cmd... — passes when the command exits non-zero
    if "$@" >/dev/null 2>&1; then fail "expected failure: $*"; else pass "refused: $*"; fi
}

export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export BOARD_REPO="test/repo"
export MOCK_GH_STATE="$TEST_ROOT/gh-state.json"
export MOCK_GH_LOG="$TEST_ROOT/gh-log.jsonl"
export PATH="$SCRIPT_DIR/mock-gh:$PATH"
WORK="$TEST_ROOT/work"
git init -q "$WORK"
git -C "$WORK" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q

run() { (cd "$WORK" && "$SCRIPTS_DIR/$1" "${@:2}"); }
# state(): eval is safe here — the expression is a test-author-written literal
# from THIS file (never external input), evaluated against the mock's state.
# (Same idiom as test-board-scripts.sh.)
state() { python3 -c "import json,sys;print(eval(sys.argv[1], {'s': json.load(open('$MOCK_GH_STATE'))}))" "$1"; }

registry_commit() {  # <content> — (re)commit .doperpowers/surfaces.md
    mkdir -p "$WORK/.doperpowers"
    printf '%s\n' "$1" > "$WORK/.doperpowers/surfaces.md"
    git -C "$WORK" add .doperpowers/surfaces.md
    git -C "$WORK" -c user.email=t@t -c user.name=t commit -qm surfaces
}

REGISTRY='## recommend-rpc
- paths: sql/*recommend*.sql, lib/recommend*
- identifiers: recommend_for_student
- born-of: #1258
- note: one function body

## scrubber
- paths: lib/scrub/**
- identifiers: buildPlanText'

# ---- T1: inertness — no registry, no behavior (acceptance 9) ---------------
echo "T1: no registry → surface features inert"
body="$TEST_ROOT/body.md"; printf 'touches recommend_for_student directly\n' > "$body"
out="$(run board-register.sh "no registry yet" enhancement P2 --body-file "$body")"
n1="${out%% *}"
assert_contains "$(state "s['issues']['$n1']['labels']")" "enhancement" "T1: ticket created"
assert_not_contains "$(state "s['issues']['$n1']['labels']")" "surface:" "T1: no surface label without a registry"
assert_fails run board-surface.sh "$n1" --add recommend-rpc
lint_out="$(run board-lint.sh || true)"
assert_not_contains "$lint_out" "SURFACE" "T1: lint carries no surface section without a registry"

# ---- registry lands (SURFACES_REF pins the read to a committed ref) --------
registry_commit "$REGISTRY"
export SURFACES_REF=HEAD

# ---- T2: board-surface.sh add/remove roundtrip -----------------------------
echo "T2: board-surface.sh add/remove"
out="$(run board-surface.sh "$n1" --add recommend-rpc)"
assert_contains "$out" "surface += recommend-rpc" "T2: add reports"
assert_contains "$(state "s['issues']['$n1']['labels']")" "surface:recommend-rpc" "T2: label landed"
assert_fails run board-surface.sh "$n1" --add no-such-surface
out="$(run board-surface.sh "$n1" --remove recommend-rpc)"
assert_contains "$out" "surface -= recommend-rpc" "T2: remove reports"
assert_not_contains "$(state "s['issues']['$n1']['labels']")" "surface:recommend-rpc" "T2: label removed"

# ---- T3: lint FAILs an invented surface label (acceptance 7) ---------------
echo "T3: lint — closed vocabulary"
gh issue edit "$n1" -R test/repo --add-label surface:bogus >/dev/null
lint_out="$(run board-lint.sh || true)"
assert_contains "$lint_out" "surface label with no registry entry: surface:bogus" "T3: invented label FAILs"
assert_contains "$lint_out" "board-surface.sh $n1 --remove bogus" "T3: FIX names board-surface.sh"
gh issue edit "$n1" -R test/repo --remove-label surface:bogus >/dev/null

# ---- T4: lint validates registry names + reports queue depth ---------------
echo "T4: lint — registry name rule + depth report"
registry_commit "$REGISTRY

## Bad_Name
- paths: x/**"
lint_out="$(run board-lint.sh || true)"
assert_contains "$lint_out" "surfaces.md entry 'Bad_Name'" "T4: non-kebab name FAILs"
registry_commit "$REGISTRY"
run board-surface.sh "$n1" --add recommend-rpc >/dev/null
lint_out="$(run board-lint.sh || true)"
assert_contains "$lint_out" "SURFACE recommend-rpc: 1 open ticket(s)" "T4: depth report line"
run board-surface.sh "$n1" --remove recommend-rpc >/dev/null

# ---- T5: register-time matching + auto-relate (acceptance 1) ---------------
echo "T5: register auto-labels and auto-relates"
printf 'the recommend_for_student sample block is wrong\n' > "$body"
out="$(run board-register.sh "성적 표본 결함" bug P1 --body-file "$body")"
n2="${out%% *}"
assert_contains "$(state "s['issues']['$n2']['labels']")" "surface:recommend-rpc" "T5: identifier match labels at create"
assert_contains "$out" "surface recommend-rpc: no open label-mates" "T5: first ticket has no mates"
out="$(run board-register.sh "같은 함수 두 번째 결함" bug P1 --body-file "$body")"
n3="${out%% *}"
assert_contains "$out" "surface recommend-rpc: open label-mates #$n2" "T5: second ticket reports the mate"
assert_contains "$(state "s['issues']['$n2']['body']")" "relates-to: #$n3" "T5: mate side got the relates edge"
assert_contains "$(state "s['issues']['$n3']['body']")" "relates-to: #$n2" "T5: new side got the relates edge"

# ---- T6: --surface path hint matches path globs ----------------------------
echo "T6: --surface path hint"
printf 'no identifiers here at all\n' > "$body"
out="$(run board-register.sh "스크럽 후속" enhancement P2 --body-file "$body" --surface lib/scrub/wipe.ts)"
n4="${out%% *}"
assert_contains "$(state "s['issues']['$n4']['labels']")" "surface:scrubber" "T6: path hint matched the glob"

# ---- T8: transition-time re-match (acceptance 2) ---------------------------
echo "T8: lane-entry transition re-matches the current body"
out="$(run board-register.sh "제목만 있는 티켓" bug P2)"   # skeleton → needs-info
n5="${out%% *}"
assert_not_contains "$(state "s['issues']['$n5']['labels']")" "surface:" "T8: title-only birth stays unlabeled"
printf 'now the body names recommend_for_student explicitly\n' | gh issue edit "$n5" -R test/repo --body-file - >/dev/null
out="$(run board-transition.sh "$n5" ready-for-implementer)"
assert_contains "$out" "surface: += recommend-rpc" "T8: transition reports the re-match"
assert_contains "$(state "s['issues']['$n5']['labels']")" "surface:recommend-rpc" "T8: label added on lane entry"

# ---- T9: live-worker deferral of the relates body write --------------------
echo "T9: relates edge defers on a live bound worker"
cat > "$DAEMON_HOME/aaaa0001-0000-4000-8000-000000000000.json" <<EOF
{"uuid": "aaaa0001-0000-4000-8000-000000000000", "name": "$n2-worker",
 "status": "working", "ticket": "$n2"}
EOF
before="$(state "s['issues']['$n2']['body']")"
printf 'recommend_for_student third strike\n' > "$body"
out="$(run board-register.sh "세 번째 결함" bug P1 --body-file "$body")"
n6="${out%% *}"
assert_contains "$out" "relate deferred to sweep: #$n2" "T9: deferral reported"
assert_contains "$before" "relates-to: #$n3" "T9(pre): mate body baseline sane"
after="$(state "s['issues']['$n2']['body']")"
if [ "$before" = "$after" ]; then pass "T9: live mate's body untouched"; else
    fail "T9: live mate's body untouched"; echo "    body changed while worker live"; fi
rm -f "$DAEMON_HOME/aaaa0001-0000-4000-8000-000000000000.json"

# ---- sweep SURFACE pass ----------------------------------------------------
# The real board-sweep.sh with every other pass stubbed to no-ops; only the
# SURFACE pass touches the mock board.
SWEEP="$SCRIPTS_DIR/board-sweep.sh"
sweep() {
    (cd "$WORK" && IMPLEMENT_DISPATCH_CMD=true REVIEW_DISPATCH_CMD=true \
        BOARD_ANSWER_CMD=true RECONCILE_CMD=true \
        SWEEP_LOG="$TEST_ROOT/sweep.log" "$SWEEP" 2>&1)
}

# Park most of the cluster first: the queue-depth watch fires at >= 3 open
# implement-lane members, and T16/T17 need the sweep to run BELOW that
# threshold (T18 owns the trip). Parks are not implement-lane states.
run board-transition.sh "$n3" needs-human "test park" >/dev/null
run board-transition.sh "$n5" needs-human "test park" >/dev/null
run board-transition.sh "$n6" needs-human "test park" >/dev/null

# T16: PR-diff labeling is add-only (acceptance 4 + 5)
echo "T16: sweep labels from the PR diff, add-only"
printf 'no identifiers in this body\n' > "$body"
out="$(run board-register.sh "diff-only ticket" bug P2 --body-file "$body")"
n7="${out%% *}"
python3 - "$n7" <<'PY'
import json, os, sys
s = json.load(open(os.environ["MOCK_GH_STATE"]))
it = s["issues"][sys.argv[1]]
it["xrefPRs"] = [{"number": 900, "url": "https://github.com/test/repo/pull/900",
                  "state": "OPEN"}]
s["pr_files"] = {"900": ["sql/p187_recommend_grade_axis.sql", "README.md"]}
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out16="$(sweep)"
assert_contains "$out16" "SURFACE: #$n7 += surface:recommend-rpc (PR diff)" "T16: diff match reported"
assert_contains "$(state "s['issues']['$n7']['labels']")" "surface:recommend-rpc" "T16: label landed from the diff"
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["pr_files"] = {"900": ["tests/only.test.ts"]}   # early-WIP shape: no match
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out="$(sweep)"
assert_contains "$(state "s['issues']['$n7']['labels']")" "surface:recommend-rpc" \
  "T16: a no-longer-matching diff never REMOVES the label (add-only)"

# T17: relates backstop between label-mates — a diff-labeled ticket had no
# register-moment relate, so the SAME sweep that labeled it wires the edges.
echo "T17: sweep adds the deferred relates edge"
assert_contains "$out16" "SURFACE: related #" "T17: sweep reports the retroactive edge"
assert_contains "$(state "s['issues']['$n7']['body']")" "relates-to: " "T17: edge written on the diff-labeled side"

# T18: queue-depth consolidation, exactly once (acceptance 6)
echo "T18: queue-depth watch registers one consolidation ticket"
printf 'recommend_for_student rewrite N\n' > "$body"
out="$(run board-register.sh "네 번째 결함" bug P1 --body-file "$body")"
out="$(sweep)"
assert_contains "$out" "SURFACE: consolidation #" "T18: consolidation registered at depth >= 3"
count_mid="$(state "len(s['issues'])")"
cons="$(state "max(int(k) for k in s['issues'])")"
assert_contains "$(state "s['issues']['$cons']['labels']")" "status:ready-for-architect" "T18: consolidation born in the architect lane"
assert_contains "$(state "s['issues']['$cons']['labels']")" "surface:recommend-rpc" "T18: consolidation carries the surface label (structural dedupe key)"
out="$(sweep)"
count_after="$(state "len(s['issues'])")"
if [ "$count_mid" = "$count_after" ]; then pass "T18: second sweep registers nothing (dedupe holds)"; else
    fail "T18: second sweep registers nothing (dedupe holds)"; echo "    issues grew $count_mid -> $count_after"; fi

# T19: sweep is inert without a registry (acceptance 9)
echo "T19: sweep SURFACE pass inert without a registry"
out="$(SURFACES_REF=no-such-ref sweep)"
assert_contains "$out" "SURFACE: no registry — skipped" "T19: pass reports the skip and does nothing"

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "FAILED: $FAILURES of $ASSERTIONS assertions"
    exit 1
fi
echo "OK ($ASSERTIONS assertions)"
