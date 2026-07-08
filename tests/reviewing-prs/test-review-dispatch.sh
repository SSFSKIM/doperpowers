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

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
