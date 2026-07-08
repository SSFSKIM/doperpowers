#!/usr/bin/env bash
#
# Hermetic tests for review-dispatch.sh (the reviewing-prs trigger half).
#
# Side channels stubbed: `gh` (canned per-PR JSON + a call log), `claude`
# (agents view from a file), and the orchestrating-daemons scripts (a stub
# dir that logs spawn/retire and writes registry meta like the real ones).
# git is real: a bare origin + clone, so worktree/fetch behavior is genuine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DISPATCH="$REPO_ROOT/skills/reviewing-prs/scripts/review-dispatch.sh"

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
export MOCK_LOG="$TEST_ROOT/gh-calls.log"; : > "$MOCK_LOG"
export SPAWN_LOG="$TEST_ROOT/spawn.log"; : > "$SPAWN_LOG"
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

# stub daemon scripts: log + register meta like the real --no-wait spawn
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "spawn:$*" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
if [ -n "${FAIL_SPAWN_FOR:-}" ] && [ "$name" = "$FAIL_SPAWN_FOR" ]; then
  echo "stub daemon-spawn: simulated failure for $name" >&2
  exit 1
fi
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'aaaa%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "status": "working", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$1" >> "$SPAWN_LOG"
STUB
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh"
export DAEMON_SCRIPTS="$STUB_DAEMONS"

# stub gh + claude
STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$MOCK_LOG"
case "${1:-} ${2:-}" in
  "pr view")   cat "$MOCK_DIR/pr-$3.json" ;;
  "pr list")   cat "$MOCK_DIR/pr-list.json" ;;
  "issue view")
    case "$*" in
      *"--json url"*)  N="$3" python3 -c 'import json,os;print(json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"))["url"])' ;;
      *"--json body"*) N="$3" python3 -c 'import json,os;print(json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"))["body"])' ;;
      *) echo "mock gh: unhandled issue view: $*" >&2; exit 1 ;;
    esac ;;
  "issue list") cat "$MOCK_DIR/techdebt-number.txt" ;;
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

# canned GitHub data
echo "[]" > "$MOCK_DIR/agents.json"
echo "99" > "$MOCK_DIR/techdebt-number.txt"
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
def pr(n, **kw):
    base = {"number": n, "title": "feat: add f", "body": "Adds f.\n\nCloses #7",
            "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
            "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": False,
            "state": "OPEN", "labels": [], "closingIssuesReferences": []}
    base.update(kw)
    json.dump(base, open(os.path.join(d, "pr-%d.json" % n), "w"))
pr(5)
pr(6, isDraft=True)
pr(8, labels=[{"name": "confident-ready"}])
pr(9, title="chore: tidy", body="No ticket for this one.")
json.dump([{"number": 5, "isDraft": False, "labels": []},
           {"number": 6, "isDraft": True, "labels": []},
           {"number": 8, "isDraft": False, "labels": [{"name": "confident-ready"}]}],
          open(os.path.join(d, "pr-list.json"), "w"))
json.dump({"url": "https://github.com/test/repo/issues/7",
           "body": "Ticket seven brief body"}, open(os.path.join(d, "issue-7.json"), "w"))
PY

# fake codex companion installs — dispatch must resolve the NEWEST version
mkdir -p "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.5/scripts" \
         "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.9/scripts"
touch "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.5/scripts/codex-companion.mjs" \
      "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.9/scripts/codex-companion.mjs"

reset_state() { rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo "[]" > "$MOCK_DIR/agents.json"; }

# ---- triggered dispatch (happy path) ------------------------------------------
echo "triggered dispatch:"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "spawns --no-wait with the registry name"
WT="$LOCAL_REPO/.claude/worktrees/review-pr-5"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "worktree checked out at the PR head SHA"
if git -C "$WT" symbolic-ref -q HEAD >/dev/null; then
    fail "worktree is detached"; else pass "worktree is detached"; fi
PROMPT="$(cat "$PROMPT_DIR/review-pr-5.prompt")"
assert_contains "$PROMPT" "REVIEW worker for PR #5" "prompt carries the protocol header"
assert_contains "$PROMPT" "Adds f." "prompt carries the PR body"
assert_contains "$PROMPT" "---- Ticket #7 brief ----" "prompt names the primary ticket (Closes #7 parsed from the body)"
assert_contains "$PROMPT" "Ticket seven brief body" "prompt carries the linked issue body"
assert_contains "$PROMPT" "origin/main" "prompt carries the base ref"
assert_contains "$PROMPT" "codex/1.0.9/scripts/codex-companion.mjs" "prompt resolves the NEWEST codex companion"
assert_contains "$PROMPT" "tech-debt issue: #99" "prompt carries the standing tech-debt issue"
assert_not_contains "$PROMPT" "{{" "no unsubstituted placeholder survives"

# ---- skips --------------------------------------------------------------------
echo "skips:"
reset_state
out="$("$DISPATCH" 6)"
assert_contains "$out" "draft" "draft PR skipped"
assert_equals "$(cat "$SPAWN_LOG")" "" "draft PR spawns nothing"
out="$("$DISPATCH" 8)"
assert_contains "$out" "confident-ready" "confident-ready-labeled PR skipped"
assert_equals "$(cat "$SPAWN_LOG")" "" "confident-ready PR spawns nothing"

# ---- dedupe: active / dead / finished -----------------------------------------
echo "dedupe:"
seed_reviewer() {  # $1=status
    S="$1" python3 - <<'PY'
import json, os
json.dump({"uuid": "feed0000-0000-4000-8000-000000000000",
           "current": "feed0000-0000-4000-8000-000000000000",
           "name": "review-pr-5", "status": os.environ["S"],
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "feed0000-0000-4000-8000-000000000000.json"), "w"))
PY
}
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "live ACTIVE reviewer → skip"
assert_equals "$(cat "$SPAWN_LOG")" "" "live ACTIVE reviewer spawns nothing"

reset_state; seed_reviewer working    # agents.json now [] → session gone
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "dead reviewer retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "dead reviewer respawned"

reset_state; seed_reviewer idle
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "triggered mode retires a finished reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "triggered mode re-dispatches after an explicit event"

# ---- sweep ---------------------------------------------------------------------
echo "sweep:"
reset_state; seed_reviewer idle
out="$("$DISPATCH" --sweep)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips finished(5)/draft(6)/labeled(8)"
reset_state
out="$("$DISPATCH" --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "sweep dispatches the unbound open PR"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-6" "sweep never dispatches a draft"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-8" "sweep never dispatches a confident-ready PR"

# ---- no linked issue ------------------------------------------------------------
echo "no linked issue:"
reset_state
out="$("$DISPATCH" 9)"
PROMPT9="$(cat "$PROMPT_DIR/review-pr-9.prompt")"
assert_contains "$PROMPT9" "primary ticket: #none" "no-issue PR renders ticket=none"
assert_contains "$PROMPT9" "(no linked issue)" "no-issue PR renders the empty ticket brief"

# ---- stale worktree replaced -----------------------------------------------------
echo "stale worktree:"
reset_state
mkdir -p "$WT"; echo junk > "$WT/junk.txt"
out="$("$DISPATCH" 5)"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "stale worktree dir replaced with a fresh checkout"

# ---- sweep failure isolation ----------------------------------------------------
echo "sweep failure isolation:"
# PR 4 (earlier in the sweep order) fails mid-dispatch; PR 5 must still be
# dispatched afterward, and the failure must be surfaced rather than
# silently swallowed or left to abort the rest of the pass.
#
# NOTE on how the failure is injected: dispatch_one runs inside
# `run_for ... || echo ...`, and bash suspends `errexit` for the *entire*
# call subtree of a command guarded by `||` (verified directly: a failing
# command substitution — e.g. `gh issue view` on a deleted linked issue, or
# a failing `git fetch` — deep inside a `||`-guarded function does NOT abort
# that function; execution just continues with the failed step's output
# treated as empty/absent, and the PR still gets dispatched with degraded
# data). Only a failure in dispatch_one's actual *last* command — the
# `daemon-spawn.sh` call — propagates as dispatch_one's own nonzero return,
# which is what `|| echo "dispatch error"` can observe. So this test
# simulates a realistic spawn-time failure (e.g. a daemon registry write
# conflict) for review-pr-4 specifically, via the stub's FAIL_SPAWN_FOR hook,
# rather than a gh/git failure that (correctly, per the fix) never aborts
# the sweep but also never becomes an *observable* per-PR "dispatch error".
#
# pr-list.json is overwritten so PR 4 sorts BEFORE PR 5 (which must still be
# dispatched). Safe to mutate here: no later test in this file depends on
# the original pr-list.json contents.
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
def pr(n, **kw):
    base = {"number": n, "title": "fix: something", "body": "No ticket for this one.",
            "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
            "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": False,
            "state": "OPEN", "labels": [], "closingIssuesReferences": []}
    base.update(kw)
    json.dump(base, open(os.path.join(d, "pr-%d.json" % n), "w"))
pr(4)
json.dump([{"number": 4, "isDraft": False, "labels": []},
           {"number": 5, "isDraft": False, "labels": []}],
          open(os.path.join(d, "pr-list.json"), "w"))
PY
reset_state
out="$(FAIL_SPAWN_FOR="review-pr-4" "$DISPATCH" --sweep 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "sweep still dispatches PR 5 after PR 4 (earlier) fails mid-dispatch"
assert_contains "$out" "#4: dispatch error (continuing sweep)" "sweep surfaces PR 4's dispatch failure instead of swallowing it"

# ---- dispatch_one step guards (nounset loop kill / stale-state contamination) ----
echo "dispatch guards:"
# With the sweep's `|| echo` reporter suspending errexit through the whole
# dispatch_one call, mid-function failures need explicit per-step guards.
# Two concrete consequences are pinned here (both reproduced pre-fix):
#  (a) FIRST-PR gh failure: eval of the failed parse left PR_STATE unbound
#      and `set -u` (NOT suspended by ||) killed the loop subshell —
#      starvation again, on a narrower trigger.
#  (b) contamination: a gh failure AFTER a successful iteration left the
#      previous PR's eval'd vars (HEAD_SHA/HEAD_REF/PR_STATE...) in place —
#      the bad PR was dispatched anyway, with a worktree at the WRONG PR's
#      SHA and an EMPTY prompt (the render failed silently).
# PR 3 has NO canned pr-3.json, so the mock `gh pr view 3` exits nonzero.

# (a) first-PR failure: [bad(3), good(5)] — loop must survive and report
python3 - <<'PY'
import json, os
json.dump([{"number": 3, "isDraft": False, "labels": []},
           {"number": 5, "isDraft": False, "labels": []}],
          open(os.path.join(os.environ["MOCK_DIR"], "pr-list.json"), "w"))
PY
reset_state
out="$("$DISPATCH" --sweep 2>&1)" || true
assert_contains "$out" "#3: gh pr view failed" "first-PR gh failure surfaced as a per-step error"
assert_contains "$out" "#3: dispatch error (continuing sweep)" "first-PR gh failure reaches the sweep reporter"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "loop survives a first-PR gh failure (no nounset kill)"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-3" "failing first PR is not spawned"

# (b) contamination: [good-A(5), bad(3), good-B(4)] — good-B on its OWN
# branch feat/y with a distinct SHA, so a stale-state dispatch is detectable
git -C "$CLONE" checkout -q -b feat/y main
echo yo > "$CLONE/g.txt"
git -C "$CLONE" add g.txt
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -m feat2 -q
git -C "$CLONE" push -q -u origin feat/y
HEAD_SHA2="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
SHA2="$HEAD_SHA2" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha2 = os.environ["SHA2"]
json.dump({"number": 4, "title": "feat: add g", "body": "No ticket for this one.",
           "baseRefName": "main", "headRefName": "feat/y", "headRefOid": sha2,
           "url": "https://github.com/test/repo/pull/4", "isDraft": False,
           "state": "OPEN", "labels": [], "closingIssuesReferences": []},
          open(os.path.join(d, "pr-4.json"), "w"))
json.dump([{"number": 5, "isDraft": False, "labels": []},
           {"number": 3, "isDraft": False, "labels": []},
           {"number": 4, "isDraft": False, "labels": []}],
          open(os.path.join(d, "pr-list.json"), "w"))
PY
reset_state
rm -f "$PROMPT_DIR/review-pr-3.prompt"
out="$("$DISPATCH" --sweep 2>&1)" || true
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-3" "bad PR after a good one is never spawned (no stale-state dispatch)"
if [ -f "$PROMPT_DIR/review-pr-3.prompt" ]; then
    fail "no prompt rendered for the bad PR"; else pass "no prompt rendered for the bad PR"; fi
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-4" "good-B after the bad PR still dispatched"
assert_equals "$(git -C "$LOCAL_REPO/.claude/worktrees/review-pr-4" rev-parse HEAD)" "$HEAD_SHA2" "good-B worktree at its OWN head SHA, not the previous PR's"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
