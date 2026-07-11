#!/usr/bin/env bash
#
# Hermetic tests for land-dispatch.sh (the reviewing-prs landing phase, FD-4).
#
# Side channels stubbed as in test-review-dispatch.sh: `gh` (canned per-PR
# JSON + repo merge-method JSON), `claude` (agents view), the
# orchestrating-daemons scripts, and board-bind.sh (a stub that logs).
# git is real: a bare origin + clone, so worktree/fetch behavior is genuine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DISPATCH="$REPO_ROOT/skills/reviewing-prs/scripts/land-dispatch.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
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

# ---- environment --------------------------------------------------------------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export MOCK_DIR="$TEST_ROOT/mock"; mkdir -p "$MOCK_DIR"
export SPAWN_LOG="$TEST_ROOT/spawn.log"; : > "$SPAWN_LOG"
export BIND_LOG="$TEST_ROOT/bind.log"; : > "$BIND_LOG"
export EDIT_LOG="$TEST_ROOT/edit.log"; : > "$EDIT_LOG"
export PROMPT_DIR="$TEST_ROOT/prompts"; mkdir -p "$PROMPT_DIR"
export STUB_COUNT="$TEST_ROOT/count"

# real git: bare origin + working clone with main and a PR head branch
ORIGIN="$TEST_ROOT/origin.git"
git init -q --bare "$ORIGIN"
CLONE="$TEST_ROOT/clone"
git clone -q "$ORIGIN" "$CLONE" 2>/dev/null
git -C "$CLONE" checkout -q -b main
git -C "$CLONE" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$CLONE" push -q -u origin main
git -C "$CLONE" checkout -q -b feat/x
echo hi > "$CLONE/f.txt"
git -C "$CLONE" add f.txt
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -m feat -q
git -C "$CLONE" push -q -u origin feat/x
HEAD_SHA="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
export LOCAL_REPO="$CLONE" BOARD_REPO="test/repo"

# stub daemon scripts (same shape as test-review-dispatch.sh)
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "spawn:$*" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'aaaa%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "status": "working", "updated": "2026-07-12T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name"
STUB
cat > "$STUB_DAEMONS/codex-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "codex-spawn:$*" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'cdec%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "engine": "codex", "pid": "99999",
           "status": "working", "updated": "2026-07-12T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$1" >> "$SPAWN_LOG"
STUB
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/codex-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh"
export DAEMON_SCRIPTS="$STUB_DAEMONS"
export WORKER_ENGINE=claude

# stub board scripts (only board-bind.sh is executed by the dispatcher)
STUB_BOARD="$TEST_ROOT/stub-board"; mkdir -p "$STUB_BOARD"
cat > "$STUB_BOARD/board-bind.sh" <<'STUB'
#!/usr/bin/env bash
echo "bind:$1:$2" >> "$BIND_LOG"
if [ -n "${FAIL_BIND:-}" ]; then echo "stub bind: simulated failure" >&2; exit 1; fi
STUB
chmod +x "$STUB_BOARD/board-bind.sh"
export BOARD_SCRIPTS="$STUB_BOARD"

# stub gh + claude
STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-} ${2:-}" in
  "repo view")   cat "$MOCK_DIR/repo-merge.json" ;;
  "pr view")     cat "$MOCK_DIR/pr-$3.json" ;;
  "pr edit")     echo "edit:$*" >> "$EDIT_LOG" ;;
  "api graphql") cat "$MOCK_DIR/approved-oids.txt" ;;   # stands in for the -q jq extraction
  *) echo "mock gh: unhandled: $*" >&2; exit 1 ;;
esac
STUB
cat > "$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
[ "${1:-}" = "agents" ] && { cat "$MOCK_DIR/agents.json"; exit 0; }
exit 0
STUB
chmod +x "$STUB_BIN/gh" "$STUB_BIN/claude"
export PATH="$STUB_BIN:$PATH"

echo "[]" > "$MOCK_DIR/agents.json"
echo '{"squashMergeAllowed": true, "mergeCommitAllowed": true, "rebaseMergeAllowed": false}' \
  > "$MOCK_DIR/repo-merge.json"
# approving reviews target the current head by default (stale guard passes)
echo "$HEAD_SHA" > "$MOCK_DIR/approved-oids.txt"

# canned PRs: label sets + review decisions per case
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
def pr(n, labels=(), decision="APPROVED", **kw):
    base = {"number": n, "title": "feat: add f", "body": "Adds f.\n\nCloses #7",
            "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
            "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": False,
            "state": "OPEN", "labels": [{"name": l} for l in labels],
            "closingIssuesReferences": [], "reviewDecision": decision}
    base.update(kw)
    json.dump(base, open(os.path.join(d, "pr-%d.json" % n), "w"))
pr(5, labels=["confident-ready"])                                  # approved + cr → land
pr(6, labels=["confident-ready"], isDraft=True)                    # draft
pr(7, labels=[])                                                   # approved, NO cr label
pr(8, labels=["confident-ready"], decision="REVIEW_REQUIRED")      # cr, not approved
pr(9, labels=["confident-ready", "land"], decision="")             # land label override
pr(10, labels=["confident-ready"], state="MERGED")                 # already merged
pr(11, labels=["confident-ready"], title="chore: tidy",
   body="No ticket for this one.")                                 # ticketless
pr(12, labels=["confident-ready", "engine:codex"])                 # engine label
PY

reset_state() { rm -f "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; : > "$SPAWN_LOG"; : > "$BIND_LOG"; : > "$EDIT_LOG"; echo "[]" > "$MOCK_DIR/agents.json"; }

# ---- happy path (approved + confident-ready, default dry-run) -------------------
echo "happy path:"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "spawns --no-wait with the land registry name"
WT="$LOCAL_REPO/.claude/worktrees/land-pr-5"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "worktree checked out at the PR head SHA"
if git -C "$WT" symbolic-ref -q HEAD >/dev/null; then
    fail "worktree is detached"; else pass "worktree is detached"; fi
PROMPT="$(cat "$PROMPT_DIR/land-pr-5.prompt")"
assert_contains "$PROMPT" "LAND worker for PR #5" "prompt carries the protocol header"
assert_contains "$PROMPT" "Land mode: dry-run" "LAND_ENABLED unset renders dry-run (staged rollout)"
assert_contains "$PROMPT" "GitHub review decision APPROVED" "prompt names the approval signal"
assert_contains "$PROMPT" "gh pr merge 5 --squash" "prompt carries the resolved native merge method"
assert_contains "$PROMPT" "primary ticket: #7" "prompt names the primary ticket (Closes #7 parsed)"
assert_contains "$PROMPT" "NEVER rebase, NEVER force-push" "merge-main-never-rebase is pinned"
assert_contains "$PROMPT" "at most 50 hand-resolved lines across at most 3 conflicted files" "land bounds tightened below the self-merge tier"
assert_contains "$PROMPT" "needs-human" "out-of-bounds conflicts park needs-human"
assert_contains "$PROMPT" "IF RESUMED WITH ANSWERS" "prompt carries the board-answer resume clause"
assert_contains "$PROMPT" "board-transition.sh 7 done" "post-merge finalize transitions the ticket"
assert_contains "$PROMPT" "finalize-sweep" "cleanup ownership stays with the finalize sweep"
assert_contains "$PROMPT" "no repo risk-surface manifest" "manifest-absent fallback rendered"
assert_not_contains "$PROMPT" "{{" "no unsubstituted placeholder survives"
assert_contains "$(cat "$BIND_LOG")" ":7" "daemon bound to the linked ticket (FD-9 relay resumable)"
assert_contains "$out" "land worker dispatched" "dispatch reports success"

# ---- live mode -------------------------------------------------------------------
echo "live mode:"
reset_state
LAND_ENABLED=true "$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$PROMPT_DIR/land-pr-5.prompt")" "Land mode: live" "LAND_ENABLED=true renders live mode"

# ---- authority gate refusals ------------------------------------------------------
echo "authority gate:"
reset_state
rc=0; out="$("$DISPATCH" 6 2>&1)" || rc=$?
assert_equals "$rc" "1" "draft PR refused"
rc=0; out="$("$DISPATCH" 7 2>&1)" || rc=$?
assert_equals "$rc" "1" "missing confident-ready label refused"
assert_contains "$out" "confident-ready" "refusal names the missing label"
rc=0; out="$("$DISPATCH" 8 2>&1)" || rc=$?
assert_equals "$rc" "1" "confident-ready without approval refused"
assert_contains "$out" "no landing authority" "refusal names the missing authority"
rc=0; out="$("$DISPATCH" 10 2>&1)" || rc=$?
assert_equals "$rc" "1" "non-open PR refused"
assert_equals "$(cat "$SPAWN_LOG")" "" "no refusal case spawns anything"

# ---- land label override -----------------------------------------------------------
echo "land label override:"
reset_state
"$DISPATCH" 9 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-9" "land label dispatches without an approving review"
assert_contains "$(cat "$PROMPT_DIR/land-pr-9.prompt")" "manual 'land' label" "prompt names the label as the signal"

# ---- dedupe -------------------------------------------------------------------------
echo "dedupe:"
seed_lander() {  # $1=status
    S="$1" python3 - <<'PY'
import json, os
json.dump({"uuid": "feed0000-0000-4000-8000-000000000000",
           "current": "feed0000-0000-4000-8000-000000000000",
           "name": "land-pr-5", "status": os.environ["S"],
           "updated": "2026-07-12T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "feed0000-0000-4000-8000-000000000000.json"), "w"))
PY
}
reset_state; seed_lander working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active land worker" "live ACTIVE land worker → skip"
assert_equals "$(cat "$SPAWN_LOG")" "" "live ACTIVE land worker spawns nothing"

reset_state; seed_lander working    # agents.json [] → session gone
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "dead land worker retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "dead land worker respawned"

reset_state; seed_lander idle
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "finished land worker retired (explicit dispatch = fresh signal)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "finished land worker re-dispatched"

# ---- ticketless PR --------------------------------------------------------------------
echo "ticketless:"
reset_state
"$DISPATCH" 11 > /dev/null
assert_contains "$(cat "$PROMPT_DIR/land-pr-11.prompt")" "primary ticket: #none" "ticketless PR renders ticket=none"
assert_equals "$(cat "$BIND_LOG")" "" "ticketless PR binds nothing"

# ---- bind is mandatory for a ticketed PR: retry, then retire + fail -------------------
echo "bind failure:"
reset_state
rc=0; out="$(FAIL_BIND=1 "$DISPATCH" 5 2>&1)" || rc=$?
assert_equals "$rc" "1" "persistent bind failure fails the dispatch"
assert_equals "$(grep -c "^bind:" "$BIND_LOG")" "3" "bind retried three times before giving up"
assert_contains "$(cat "$SPAWN_LOG")" "retire:aaaa" "the spawned worker is retired on bind failure (not left running unbound)"
assert_contains "$out" "bind to ticket #7 failed" "failure names the ticket"
assert_not_contains "$out" "land worker dispatched" "no success report on a failed bind"

# ---- exclusive ticket ownership (board-answer must resume THE LAND WORKER) -------------
echo "exclusive binding:"
reset_state
# a finished implement worker still bound to ticket 7 sits in the registry
python3 - <<'PY'
import json, os
json.dump({"uuid": "0000impl-0000-4000-8000-000000000000",
           "current": "0000impl-0000-4000-8000-000000000000",
           "name": "impl-7", "status": "idle", "ticket": "7",
           "updated": "2026-07-11T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "0000impl-0000-4000-8000-000000000000.json"), "w"))
PY
"$DISPATCH" 5 > /dev/null
old_ticket="$(python3 -c '
import json, os
m = json.load(open(os.path.join(os.environ["DAEMON_HOME"], "0000impl-0000-4000-8000-000000000000.json")))
print(m.get("ticket", "STRIPPED"))')"
assert_equals "$old_ticket" "STRIPPED" "the implement worker's stale binding is stripped (ownership transferred)"
assert_contains "$(cat "$BIND_LOG")" ":7" "the land worker holds the binding"

# ---- stale approval refused --------------------------------------------------------------
echo "stale approval:"
reset_state
echo "0123456789abcdef0123456789abcdef01234567" > "$MOCK_DIR/approved-oids.txt"
rc=0; out="$("$DISPATCH" 5 2>&1)" || rc=$?
assert_equals "$rc" "1" "approval targeting an old head refused"
assert_contains "$out" "approval is stale" "refusal names the staleness"
assert_equals "$(cat "$SPAWN_LOG")" "" "stale approval spawns nothing"
echo "$HEAD_SHA" > "$MOCK_DIR/approved-oids.txt"

# ---- land label is single-use in live mode -------------------------------------------------
echo "land label consumption:"
reset_state
LAND_ENABLED=true "$DISPATCH" 9 > /dev/null
assert_contains "$(cat "$EDIT_LOG")" "--remove-label land" "live dispatch consumes the land label"
reset_state
"$DISPATCH" 9 > /dev/null
assert_equals "$(cat "$EDIT_LOG")" "" "dry-run leaves the land label in place"

# ---- engine resolution -------------------------------------------------------------------
echo "engine resolution:"
reset_state
WORKER_ENGINE=codex "$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "codex-spawn:--no-wait land-pr-5" "WORKER_ENGINE=codex spawns via codex"
reset_state
"$DISPATCH" 12 > /dev/null     # suite default WORKER_ENGINE=claude; label must win
assert_contains "$(cat "$SPAWN_LOG")" "codex-spawn:--no-wait land-pr-12" "engine:codex label overrides the env"

# ---- merge-method resolution ----------------------------------------------------------------
echo "merge method:"
reset_state
echo '{"squashMergeAllowed": false, "mergeCommitAllowed": true, "rebaseMergeAllowed": true}' \
  > "$MOCK_DIR/repo-merge.json"
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$PROMPT_DIR/land-pr-5.prompt")" "gh pr merge 5 --merge" "squash disallowed → merge commit preferred next"
echo '{"squashMergeAllowed": true, "mergeCommitAllowed": true, "rebaseMergeAllowed": false}' \
  > "$MOCK_DIR/repo-merge.json"

# ---- risk manifest read from BASE, never HEAD ------------------------------------------------
echo "risk manifest from base:"
git -C "$CLONE" checkout -q main
mkdir -p "$CLONE/.doperpowers"
printf 'RISK-FROM-BASE\nlib/auth.ts\n' > "$CLONE/.doperpowers/risk-surfaces.md"
git -C "$CLONE" add .doperpowers/risk-surfaces.md
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "add risk manifest"
git -C "$CLONE" push -q origin main
git -C "$CLONE" checkout -q -b feat/z main
printf 'RISK-FROM-HEAD-SHOULD-NOT-APPEAR\n' > "$CLONE/.doperpowers/risk-surfaces.md"
git -C "$CLONE" add .doperpowers/risk-surfaces.md
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "sneak manifest edit"
git -C "$CLONE" push -q origin feat/z
HEAD_SHA_Z="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
SHAZ="$HEAD_SHA_Z" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHAZ"]
json.dump({"number": 13, "title": "feat: z", "body": "No ticket for this one.",
           "baseRefName": "main", "headRefName": "feat/z", "headRefOid": sha,
           "url": "https://github.com/test/repo/pull/13", "isDraft": False,
           "state": "OPEN", "labels": [{"name": "confident-ready"}],
           "closingIssuesReferences": [], "reviewDecision": "APPROVED"},
          open(os.path.join(d, "pr-13.json"), "w"))
PY
reset_state
printf '%s\n%s\n' "$HEAD_SHA" "$HEAD_SHA_Z" > "$MOCK_DIR/approved-oids.txt"
"$DISPATCH" 13 > /dev/null
P13="$(cat "$PROMPT_DIR/land-pr-13.prompt")"
assert_contains "$P13" "RISK-FROM-BASE" "manifest content injected from the BASE ref"
assert_not_contains "$P13" "RISK-FROM-HEAD-SHOULD-NOT-APPEAR" "HEAD-side manifest edit does not leak"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
