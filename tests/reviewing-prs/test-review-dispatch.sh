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
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
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
export DAEMON_BOOT_ID="boot-current"

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
echo "spawn-env:settings=${DAEMON_CLAUDE_SETTINGS:-};effort=${DAEMON_CLAUDE_EFFORT:-}" >> "$SPAWN_LOG"
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
# Simulate the worker's first protocol action: wait for the dispatcher-owned
# ready file, validate it, then acknowledge before ORIENT. Tests can suppress
# this to prove dispatch does not report success for a worker that never starts.
bind_ready="$(printf '%s\n' "$task" | grep '^- `BIND_READY_FILE`:' | cut -d' ' -f3- || true)"
if [ -n "$bind_ready" ] && [ "${STUB_NO_BIND_ACK:-0}" != "1" ]; then
  READY="$bind_ready" UUID="$uuid" python3 - <<'PY' >/dev/null 2>&1 &
import json, os, time
ready=os.environ["READY"]
for _ in range(500):
    if os.path.isfile(ready):
        ack=ready+".ack"; tmp=ack+".tmp"
        with open(tmp,"w") as f: json.dump({"uuid":os.environ["UUID"]},f)
        os.replace(tmp,ack)
        break
    time.sleep(0.01)
PY
fi
if [ "${STUB_BAD_SPAWN_BANNER:-0}" = "1" ]; then
  echo "daemon spawned without parseable identity"
else
  echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
fi
STUB
cat > "$STUB_DAEMONS/codex-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "codex-spawn:$*" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
if [ -n "${FAIL_SPAWN_FOR:-}" ] && [ "$name" = "$FAIL_SPAWN_FOR" ]; then
  echo "stub codex-spawn: simulated failure for $name" >&2
  exit 1
fi
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'cdec%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "engine": "codex", "pid": "99999",
           "status": "working", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$1" >> "$SPAWN_LOG"
STUB
# Faithful stand-in for daemon-finalize.sh: same contract (noop/live/absent/
# idle/error on stdout), driven by the registry meta + the mock agents view;
# reply content comes from an optional $MOCK_DIR/reply-<uuid>.txt fixture.
cat > "$STUB_DAEMONS/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
meta=""
for f in "$DAEMON_HOME"/*.json; do
  case "$f" in *.reply.json) continue ;; esac
  case "$(basename "$f" .json)" in "$1"*) meta="$f"; break ;; esac
done
[ -n "$meta" ] || { echo "noop"; exit 0; }
uuid="$(basename "$meta" .json)"
out="$(M="$meta" A="$MOCK_DIR/agents.json" python3 <<'PY'
import json, os
m = json.load(open(os.environ["M"]))
if m.get("engine") == "codex" or m.get("status") not in ("working", "blocked"):
    print("noop"); raise SystemExit
cur = m.get("current") or m.get("uuid")
try:
    rows = json.load(open(os.environ["A"]))
except Exception:
    rows = []
row = next((r for r in rows if r.get("sessionId") == cur), None)
state = (row or {}).get("state") or ""
# mirror the real script: a lingering finished session stays state=working;
# status (busy -> idle) is the turn signal
if row is not None and state == "working" and row.get("status") == "idle":
    state = "done"
if state == "":
    print("absent")
elif state in ("working", "blocked"):
    print("live")
elif state == "done":
    print("idle")
else:
    print("error")
PY
)"
case "$out" in
  idle|error)
    if [ -f "$MOCK_DIR/reply-$uuid.txt" ]; then
      cp "$MOCK_DIR/reply-$uuid.txt" "$DAEMON_HOME/$uuid.reply.txt"
    else
      echo "review finished." > "$DAEMON_HOME/$uuid.reply.txt"
    fi
    M="$meta" S="$out" python3 -c '
import json, os
m = json.load(open(os.environ["M"]))
m["status"] = os.environ["S"]
json.dump(m, open(os.environ["M"], "w"))
' ;;
esac
echo "$out"
STUB
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/codex-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh" "$STUB_DAEMONS/daemon-finalize.sh"
export DAEMON_SCRIPTS="$STUB_DAEMONS"

# Minimal board-bind stand-in: this suite tests dispatch ownership mechanics,
# while the issue-tracker suite tests board-bind's GitHub validation itself.
STUB_BOARD="$TEST_ROOT/stub-board"; mkdir -p "$STUB_BOARD"
cat > "$STUB_BOARD/board-bind.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
q="$1"; ticket="$2"; hit=""
for p in "$DAEMON_HOME"/*.json; do
  [ "$(basename "$p" .json)" = "$q" ] || [[ "$(basename "$p" .json)" == "$q"* ]] || continue
  [ -z "$hit" ] || exit 1
  hit="$p"
done
[ -n "$hit" ] || exit 1
M="$hit" T="$ticket" D="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
p=os.environ["M"]; ticket=os.environ["T"]
for q in glob.glob(os.path.join(os.environ["D"], "*.json")):
    if q == p or q.endswith(".reply.json"): continue
    m=json.load(open(q))
    if str(m.get("ticket", "")).lstrip("#") == ticket.lstrip("#"):
        del m["ticket"]; json.dump(m, open(q,"w"), indent=2)
m=json.load(open(p)); m["ticket"]=ticket
json.dump(m, open(p,"w"), indent=2)
PY
STUB
chmod +x "$STUB_BOARD/board-bind.sh"
export BOARD_SCRIPTS="$STUB_BOARD"
# Every PRE-EXISTING case in this file exercises the claude path unchanged —
# the label→env→codex resolution only kicks in per-test below via an
# explicit WORKER_ENGINE=codex prefix.
export WORKER_ENGINE=claude

# stub gh + claude
STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$MOCK_LOG"
case "${1:-} ${2:-}" in
  "repo view") echo "${MOCK_DEFAULT_BRANCH:-main}" ;;   # -q .defaultBranchRef.name
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

reset_state() { rm -f "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; rm -rf "$DAEMON_HOME"/review-pr-*-control.*; : > "$SPAWN_LOG"; echo "[]" > "$MOCK_DIR/agents.json"; }

# ---- triggered dispatch (happy path) ------------------------------------------
echo "triggered dispatch:"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "spawns --no-wait with the registry name"
assert_contains "$(cat "$DAEMON_HOME/aaaa0001-0000-4000-8000-000000000000.json")" '"ticket": "7"' "ticketed review worker is bound for board-answer resume"
WT="$LOCAL_REPO/.claude/worktrees/review-pr-5"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "worktree checked out at the PR head SHA"
if git -C "$WT" symbolic-ref -q HEAD >/dev/null; then
    fail "worktree is detached"; else pass "worktree is detached"; fi
PROMPT="$(cat "$PROMPT_DIR/review-pr-5.prompt")"
BIND_READY="$(printf '%s\n' "$PROMPT" | grep '^- `BIND_READY_FILE`:' | cut -d' ' -f3- || true)"
assert_contains "$PROMPT" "REVIEW worker for PR #5" "prompt carries the worker bootstrap header"
assert_contains "$PROMPT" '`BIND_READY_FILE`:' "prompt carries the startup binding barrier"
if [ -n "$BIND_READY" ] && [ -f "$BIND_READY" ]; then pass "bind-ready barrier opens after exclusive binding"; else fail "bind-ready barrier opens after exclusive binding"; fi
assert_contains "$(cat "$BIND_READY" 2>/dev/null || true)" '"ticket": "7"' "barrier proves the primary ticket binding"
assert_contains "$(cat "$BIND_READY" 2>/dev/null || true)" '"ledger"' "barrier carries the undisclosed ledger path to the orchestrator"
if [ -f "$BIND_READY.ack" ]; then pass "dispatch waits for worker barrier acknowledgement"; else fail "dispatch waits for worker barrier acknowledgement"; fi
assert_not_contains "$PROMPT" "Adds f." "prompt carries no inlined PR body (the worker reads the PR live via gh)"
assert_contains "$PROMPT" '`ISSUE_NUMBER`: 7' "prompt binds the primary ticket (Closes #7 parsed from the body)"
assert_not_contains "$PROMPT" "Ticket seven brief body" "prompt carries no inlined ticket body"
assert_contains "$PROMPT" '`BASE_REF`: main' "prompt carries the base ref"
assert_contains "$PROMPT" '`TECH_DEBT_ISSUE`: 99' "prompt carries the standing tech-debt issue binding"
assert_contains "$PROMPT" '`AUTO_MERGE`: off' "prompt binds auto-merge off by default (observation mode)"
assert_contains "$PROMPT" '`BASE_IS_DEFAULT`: yes' "prompt binds base==default (PR 5 targets main, the default) → always human tier"
assert_contains "$PROMPT" "no repo risk-surface manifest" "prompt renders the manifest-absent fallback when the repo has none"
assert_contains "$PROMPT" "no repo-facts manifest" "prompt renders the repo-facts-absent fallback when the repo has none"
assert_not_contains "$PROMPT" "{{" "no unsubstituted bootstrap placeholder survives"
assert_contains "$PROMPT" "Use doperpowers:reviewing-prs" "prompt names the Review Worker Protocol skill"
assert_contains "$PROMPT" "dispatcher-pinned copy" "prompt routes the protocol through the dispatcher-pinned file"
assert_contains "$PROMPT" "$REPO_ROOT/skills/reviewing-prs/SKILL.md" "prompt carries the canonical dispatcher-owned skill path"
assert_contains "$PROMPT" "$REPO_ROOT/skills/implementing-tickets/SKILL.md" "prompt carries the canonical implement-contract path (the skill IS the protocol)"
assert_contains "$PROMPT" "scripts/review-engine.sh" "prompt binds the engine script path"
assert_contains "$PROMPT" '`CODEX_REVIEW_MODEL`:' "prompt binds the engine model"
assert_contains "$PROMPT" '`CODEX_REVIEW_EFFORT`:' "prompt binds the engine effort"

# Ticket ownership is exclusive: the reviewer replaces the finished implement
# worker as board-answer's resume target.
echo "review ticket binding:"
reset_state
OLD="impl0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["OLD"]
json.dump({"uuid": u, "current": u, "name": "implement-ticket-7",
           "status": "idle", "ticket": "7", "updated": "2026-07-07T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
"$DISPATCH" 5 >/dev/null
NEW_META="$(python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m=json.load(open(p))
    if m.get("name") == "review-pr-5": print(p); break
PY
)"
assert_contains "$(cat "$NEW_META")" '"ticket": "7"' "new reviewer owns ticket #7"
assert_not_contains "$(cat "$DAEMON_HOME/impl0000-0000-4000-8000-000000000000.json")" '"ticket"' "old implement worker binding is stripped"

# Binding is mandatory: an unbound reviewer could park needs-human where the
# answer relay cannot reach it. Retire it instead of allowing the dispatch.
FAIL_BOARD="$TEST_ROOT/fail-board"; mkdir -p "$FAIL_BOARD"
printf '#!/usr/bin/env bash\nexit 1\n' > "$FAIL_BOARD/board-bind.sh"
chmod +x "$FAIL_BOARD/board-bind.sh"
reset_state
if BOARD_SCRIPTS="$FAIL_BOARD" REVIEW_BIND_ATTEMPTS=1 REVIEW_BIND_DELAY=0 "$DISPATCH" 5 >/dev/null 2>&1; then
    fail "bind failure aborts review dispatch"
else
    pass "bind failure aborts review dispatch"
fi
assert_contains "$(cat "$SPAWN_LOG")" "retire:" "bind failure retires the unreachable reviewer"
assert_equals "$(find "$DAEMON_HOME" -name bind-ready.json -type f -print)" "" "bind failure never opens the startup barrier"

# A published barrier is not success until the worker acknowledges it. A model
# that died/timed out before reading the prompt is retired and dispatch fails.
reset_state
if STUB_NO_BIND_ACK=1 REVIEW_ACK_POLLS=2 REVIEW_ACK_DELAY=0.01 "$DISPATCH" 5 >/dev/null 2>&1; then
    fail "missing worker barrier ack fails dispatch"
else
    pass "missing worker barrier ack fails dispatch"
fi
assert_contains "$(cat "$SPAWN_LOG")" "retire:" "missing barrier ack retires the non-started reviewer"

# Exact spawn identity is mandatory. A changed/unparseable banner must fail
# closed, never fall back to a same-name registry heuristic.
reset_state
if STUB_BAD_SPAWN_BANNER=1 "$DISPATCH" 5 >/dev/null 2>&1; then
    fail "unparseable spawn UUID fails dispatch"
else
    pass "unparseable spawn UUID fails dispatch"
fi
assert_equals "$(find "$DAEMON_HOME" -name bind-ready.json -type f -print)" "" "identity parse failure never opens the barrier"

# Every control-state initialization step is explicitly guarded in sweep mode;
# set -e is suspended beneath the per-PR `||` wrapper.
assert_contains "$(cat "$DISPATCH")" "control state initialization failed" "control-state setup has a fail-closed guard"

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
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "live ACTIVE reviewer → skip"
assert_equals "$(cat "$SPAWN_LOG")" "" "live ACTIVE reviewer spawns nothing"

reset_state; seed_reviewer working    # agents.json now [] → session gone
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "dead reviewer retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "dead reviewer respawned"

reset_state
H="old-host" B="boot-old" python3 - <<'PY'
import json, os
u = "feed0000-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "claude",
           "host": os.environ["H"], "boot_id": os.environ["B"], "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "foreign-host Claude reviewer is retired despite a visible migrated session"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host Claude reviewer is respawned"

reset_state; seed_reviewer idle
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "triggered mode retires a finished reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "triggered mode re-dispatches after an explicit event"

# ---- finished-but-unfinalized reviewer (the one-harness lifecycle) ---------------
# A --no-wait worker's meta stays status=working after its turn ends; only
# `claude agents` knows the truth, and finished --bg sessions stay LISTED
# indefinitely — presence alone is NOT liveness. Dispatch must finalize
# through daemon-finalize.sh before deciding.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "finished-but-unfinalized reviewer is finalized + retired, not skipped as active"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "finished-but-unfinalized reviewer re-dispatches on an explicit event"
assert_contains "$(cat "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.json")" '"status": "idle"' "dispatch finalized the meta through daemon-finalize"

# The ENGINE-UNAVAILABLE marker reaches the reply file THROUGH finalization,
# so the sweep's outage retry works on the one-harness lifecycle.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
printf 'trail posted; engine down.\nENGINE-UNAVAILABLE\n' > "$MOCK_DIR/reply-feed0000-0000-4000-8000-000000000000.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "sweep finalizes and retries an unfinalized ENGINE-UNAVAILABLE reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep re-dispatches after finalizing the outage turn"
rm -f "$MOCK_DIR/reply-feed0000-0000-4000-8000-000000000000.txt"

# A normally-finished turn finalizes to idle and the sweep SKIPS it — no
# endless respawn of completed reviews.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "sweep finalizes a normally-finished reviewer and skips it"
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:" "a finalized finished reviewer is not retired by the sweep"

# Production shape (observed live 2026-07-15): a finished daemon LINGERS in
# `claude agents` with state=working while its process lives — `status`
# (busy → idle) is the turn signal. An explicit PR event must still finalize
# and re-dispatch such a reviewer instead of skipping it as active forever.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working", "status": "idle"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "lingering finished reviewer (state=working, status=idle) is finalized + retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "lingering finished reviewer re-dispatches on an explicit event"
assert_contains "$(cat "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.json")" '"status": "idle"' "lingering finished reviewer's meta finalized idle"

# ...and a genuinely mid-turn reviewer (status=busy) still skips as active.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working", "status": "busy"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "busy reviewer still skips as active"
assert_equals "$(cat "$SPAWN_LOG")" "" "busy reviewer spawns nothing"

# ---- dedupe without exported DAEMON_HOME (production repro) -------------------
# In launchd/cron the parent process never exports DAEMON_HOME — the script's
# own `DAEMON_HOME="${DAEMON_HOME:-...}"` default assignment computes it fine
# either way, but _reviewer_meta's python subprocess only sees it if the
# shell var was exported (or passed inline). Seed the registry at the
# DEFAULT location ($HOME/.claude/orchestrating-daemons, not the test's
# $DAEMON_HOME override) and invoke the dispatcher with DAEMON_HOME entirely
# absent from the child environment.
echo "dedupe without exported DAEMON_HOME:"
reset_state
DEFAULT_DAEMON_HOME="$HOME/.claude/orchestrating-daemons"; mkdir -p "$DEFAULT_DAEMON_HOME"
NOEXPORT_UUID="cafe1234-0000-4000-8000-000000000000"
D="$DEFAULT_DAEMON_HOME" U="$NOEXPORT_UUID" python3 - <<'PY'
import json, os
json.dump({"uuid": os.environ["U"], "current": os.environ["U"],
           "name": "review-pr-5", "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["D"], os.environ["U"] + ".json"), "w"))
PY
echo "[{\"id\": \"cafe1234\", \"sessionId\": \"$NOEXPORT_UUID\", \"state\": \"working\"}]" > "$MOCK_DIR/agents.json"
out="$(env -u DAEMON_HOME HOME="$HOME" PATH="$PATH" LOCAL_REPO="$LOCAL_REPO" BOARD_REPO="$BOARD_REPO" \
    DAEMON_SCRIPTS="$DAEMON_SCRIPTS" MOCK_DIR="$MOCK_DIR" MOCK_LOG="$MOCK_LOG" SPAWN_LOG="$SPAWN_LOG" \
    PROMPT_DIR="$PROMPT_DIR" STUB_COUNT="$STUB_COUNT" "$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "ACTIVE+live reviewer skipped even with DAEMON_HOME absent from the child env"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn logged — DAEMON_HOME reached _reviewer_meta via explicit passthrough, not inheritance"
rm -rf "$DEFAULT_DAEMON_HOME"

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

# ---- sweep retries an engine-unavailable reviewer -------------------------------
reset_state
U="feed0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-09T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'trail posted; engine down after 3 attempts.\nENGINE-UNAVAILABLE\n' \
  > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "sweep retires an ENGINE-UNAVAILABLE reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep re-dispatches the PR after the outage"

# ---- sweep still skips a normally-finished reviewer ------------------------------
reset_state
U="feed0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-09T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'review complete; confident-ready set.\n' \
  > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep still skips a finished reviewer without the marker"

# ---- sweep outage cap ------------------------------------------------------------
# A persistent engine outage must not make the cron sweep respawn forever:
# after 3 CONSECUTIVE ENGINE-UNAVAILABLE reviewers for one PR, the sweep
# skips it. An explicit PR event (triggered mode) always re-dispatches.
echo "sweep outage cap:"
seed_outage_metas() {  # $1 = how many consecutive outage reviewers to seed
  local i
  for f in "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; do rm -f "$f"; done
  for i in $(seq 1 "$1"); do
    U="feed000$i-0000-4000-8000-000000000000" I="$i" python3 - <<'PY'
import json, os
u = os.environ["U"]; i = os.environ["I"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-0%sT00:00:00Z" % i},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
    printf 'trail posted; engine down.\nENGINE-UNAVAILABLE\n' \
      > "$DAEMON_HOME/feed000$i-0000-4000-8000-000000000000.reply.txt"
  done
}
reset_state
seed_outage_metas 2
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep still respawns below the outage cap (2 consecutive)"
reset_state
seed_outage_metas 3
OUT_CAP="$("$DISPATCH" --sweep 2>&1 || true)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips a PR at the outage cap (3 consecutive)"
assert_contains "$OUT_CAP" "outage" "sweep names the outage cap as the skip reason"
: > "$SPAWN_LOG"
OUT_EVT="$("$DISPATCH" 5 2>&1 || true)"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "an explicit PR event ignores the outage cap"
[ -s "$SPAWN_LOG" ] || echo "    dispatch said: $OUT_EVT"

# ---- sweep retries a dead worker (terminal error, no reply marker) ---------------
# A worker that dies BEFORE it can speak — e.g. the gateway refuses its very
# first turn — finalizes status=error with an EMPTY reply: no assistant
# message exists to carry ENGINE-UNAVAILABLE. The sweep must treat terminal
# worker errors as retryable (same 3-consecutive cap), or a gateway outage
# parks the PR out of the sweep until an explicit event.
echo "sweep dead-worker retry:"
reset_state; seed_reviewer error
printf '\n' > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "sweep retires an errored worker whose reply is empty"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep re-dispatches after a dead worker"

# one-harness lifecycle: an unfinalized worker whose SESSION errored is
# finalized to status=error by the sweep itself, then retried in the same pass.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "error"}]' > "$MOCK_DIR/agents.json"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.json")" '"status": "error"' "sweep finalized the errored session through daemon-finalize"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep finalizes an errored session and re-dispatches in the same pass"

# dead workers share the outage cap: 3 consecutive errored reviewers (empty
# replies — the marker never existed) stop the sweep respawning.
seed_error_metas() {  # $1 = how many consecutive errored reviewers to seed
  local i
  for f in "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; do rm -f "$f"; done
  for i in $(seq 1 "$1"); do
    U="feed000$i-0000-4000-8000-000000000000" I="$i" python3 - <<'PY'
import json, os
u = os.environ["U"]; i = os.environ["I"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5",
           "status": "error", "updated": "2026-07-0%sT00:00:00Z" % i},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
    printf '\n' > "$DAEMON_HOME/feed000$i-0000-4000-8000-000000000000.reply.txt"
  done
}
reset_state
seed_error_metas 2
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep still respawns below the cap (2 consecutive dead workers)"
reset_state
seed_error_metas 3
OUT_DEAD="$("$DISPATCH" --sweep 2>&1 || true)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips a PR after 3 consecutive dead workers"
assert_contains "$OUT_DEAD" "3 consecutive" "sweep names the failure cap as the skip reason"

# marker outages and dead workers form ONE streak — interleaving them must
# not reset the count.
reset_state
seed_error_metas 2
U="feed0003-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-03T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'trail posted; engine down.\nENGINE-UNAVAILABLE\n' \
  > "$DAEMON_HOME/feed0003-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_equals "$(cat "$SPAWN_LOG")" "" "marker outages and dead workers count as one 3-streak"

# ---- no linked issue ------------------------------------------------------------
echo "no linked issue:"
reset_state
out="$("$DISPATCH" 9)"
PROMPT9="$(cat "$PROMPT_DIR/review-pr-9.prompt")"
assert_contains "$PROMPT9" '`ISSUE_NUMBER`: none' "no-issue PR binds ticket=none"
assert_contains "$PROMPT9" '`ISSUE_LIST`: none' "no-issue PR binds an empty issue list"

# ---- stale worktree replaced -----------------------------------------------------
echo "stale worktree:"
reset_state
mkdir -p "$WT"; echo junk > "$WT/junk.txt"
out="$("$DISPATCH" 5)"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "stale worktree dir replaced with a fresh checkout"

# ---- live worktree guard (defense-in-depth on top of dedupe) ------------------
# A live daemon can occupy $WT even when the DAEMON_HOME registry has no
# record of it (e.g. a non-review daemon, or a registry that was cleared).
# The registry-only dedupe check would say "dispatch"; the cwd-based guard
# must refuse anyway rather than force-removing a worktree a live process is
# sitting in.
echo "live worktree guard:"
reset_state
out="$("$DISPATCH" 5)"                                     # real dispatch: (re)creates $WT
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "setup: worktree created via a real dispatch"
reset_state                                                  # clears registry → dedupe alone would say "dispatch"
echo "[{\"id\": \"live0001\", \"sessionId\": \"live0001-0000-4000-8000-000000000000\", \"cwd\": \"$WT\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "occupied worktree refuses removal"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn when the worktree is occupied by a live daemon"
if [ -d "$WT" ]; then pass "worktree still exists after the refused dispatch"; else
    fail "worktree still exists after the refused dispatch"; fi
reset_state

# A session restored from a foreign state volume can still be visible in the
# local dashboard, but its foreign registry identity must not occupy the worktree.
U="foreign1-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "other-daemon", "engine": "claude",
           "cwd": os.environ["WT"], "host": "old-host", "boot_id": "boot-old",
           "status": "working", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"foreign1\", \"sessionId\": \"foreign1-0000-4000-8000-000000000000\", \"cwd\": \"$WT\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host Claude session does not occupy the worktree"
assert_not_contains "$out" "live daemon occupies" "foreign-host Claude session does not block removal"
reset_state

# A MANAGED local session whose turn is over (lingering shape: state=working,
# status=idle — finished daemons stay listed) must NOT occupy the worktree:
# retire + respawn deliberately reuses that path.
U="linger01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "claude",
           "cwd": os.environ["WT"], "status": "retired",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"linger01\", \"sessionId\": \"linger01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"working\", \"status\": \"idle\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "a finished lingering session frees the worktree for re-dispatch"
assert_not_contains "$out" "live daemon occupies" "finished lingering session does not block worktree removal"
reset_state

# The observed post-retire shape (2026-07-19 live board, PR #574): the
# retired reviewer's row lingers state=stopped with NO status field, so the
# idle escape never matches — only the meta's `retired` status can free the
# worktree.
U="retire01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "claude",
           "cwd": os.environ["WT"], "status": "retired",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"retire01\", \"sessionId\": \"retire01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"stopped\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "a retired reviewer's statusless stopped row frees the worktree"
assert_not_contains "$out" "live daemon occupies" "retired meta overrides the statusless stopped row"
reset_state

# ...but a PARKED worker's stopped row (meta NOT retired — its worktree is
# the resume context) must still occupy.
U="parked01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "other-daemon", "engine": "claude",
           "cwd": os.environ["WT"], "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"parked01\", \"sessionId\": \"parked01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"stopped\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "a parked (non-retired) stopped session still occupies the worktree"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn over a parked session's worktree"
reset_state

# ...while a managed local session that is genuinely mid-turn (status=busy)
# still occupies it.
U="linger01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "other-daemon", "engine": "claude",
           "cwd": os.environ["WT"], "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"linger01\", \"sessionId\": \"linger01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"working\", \"status\": \"busy\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "busy managed session still occupies the worktree"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn over a busy session's worktree"
reset_state

# ---- sweep failure isolation ----------------------------------------------------
echo "sweep failure isolation:"
# PR 4 (earlier in the sweep order) fails mid-dispatch; PR 5 must still be
# dispatched afterward, and the failure must be surfaced rather than
# silently swallowed or left to abort the rest of the pass.
#
# NOTE on how the failure is injected: dispatch_one runs inside
# `run_for ... || echo ...`, and bash suspends `errexit` for the *entire*
# call subtree of a command guarded by `||`. That USED to mean a gh/git
# failure deep inside dispatch_one could go unreported — it no longer does:
# every gh/git step that can fail (git fetch, gh pr view, worktree add, ...)
# is now explicitly guarded inline (`... || { echo "#$pr: <step> failed" >&2;
# return 1; }`), so those failures surface as their own observable per-PR
# error today — see the "dispatch guards" section below, which pins exactly
# that (`#3: gh pr view failed`, reaching the sweep's reporter). This section
# instead simulates a SPAWN-time failure (e.g. a daemon registry write
# conflict) for review-pr-4 specifically, via the stub's FAIL_SPAWN_FOR hook:
# `daemon-spawn.sh` is dispatch_one's actual *last* command, so its failure
# is the one that exercises the sweep's own `|| echo "dispatch error"`
# loop-isolation reporter directly, distinct from the per-step gh/git guards
# already covered elsewhere in this file.
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

# ---- risk-surface manifest (read from BASE, not HEAD) + rollout flags ----------
echo "risk manifest + rollout flags:"
# Commit a manifest to main (the base) with a distinctive marker, then a
# DIFFERENT version on the PR head branch. The prompt must carry the BASE
# version and never the HEAD version — a PR cannot weaken its own gate.
git -C "$CLONE" checkout -q main
mkdir -p "$CLONE/.doperpowers"
printf 'RISK-FROM-BASE\nlib/auth.ts\n' > "$CLONE/.doperpowers/risk-surfaces.md"
printf '## Validation\nFACTS-FROM-BASE: npm test\n' > "$CLONE/.doperpowers/repo-facts.md"
git -C "$CLONE" add .doperpowers
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "add manifests"
git -C "$CLONE" push -q origin main
git -C "$CLONE" checkout -q -b feat/z main
printf 'RISK-FROM-HEAD-SHOULD-NOT-APPEAR\n' > "$CLONE/.doperpowers/risk-surfaces.md"
printf 'FACTS-FROM-HEAD-SHOULD-NOT-APPEAR\n' > "$CLONE/.doperpowers/repo-facts.md"
git -C "$CLONE" add .doperpowers
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "sneak manifest edit"
git -C "$CLONE" push -q origin feat/z
HEAD_SHA_Z="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
SHAZ="$HEAD_SHA_Z" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHAZ"]
json.dump({"number": 10, "title": "feat: z", "body": "No ticket for this one.",
           "baseRefName": "main", "headRefName": "feat/z", "headRefOid": sha,
           "url": "https://github.com/test/repo/pull/10", "isDraft": False,
           "state": "OPEN", "labels": [], "closingIssuesReferences": []},
          open(os.path.join(d, "pr-10.json"), "w"))
PY
reset_state
out="$(AUTO_MERGE_ENABLED=true DEFAULT_BRANCH=develop "$DISPATCH" 10)"
P10="$(cat "$PROMPT_DIR/review-pr-10.prompt")"
assert_contains "$P10" "RISK-FROM-BASE" "manifest content injected from the BASE ref"
assert_not_contains "$P10" "RISK-FROM-HEAD-SHOULD-NOT-APPEAR" "HEAD-side manifest edit does not leak (read from base, not head)"
assert_contains "$P10" "FACTS-FROM-BASE" "repo-facts content injected from the BASE ref"
assert_not_contains "$P10" "FACTS-FROM-HEAD-SHOULD-NOT-APPEAR" "HEAD-side repo-facts edit does not leak (read from base, not head)"
assert_contains "$P10" '`AUTO_MERGE`: on' "AUTO_MERGE_ENABLED=true binds auto-merge on"
assert_contains "$P10" '`BASE_IS_DEFAULT`: no' "base (main) != default branch (develop) → not main-excluded"

# ---- engine switch (label → WORKER_ENGINE → codex) + codex liveness ------------
# Canned PR on feat/x (labels overridable) + a thin wrapper over $DISPATCH, so
# an env-var prefix (e.g. `WORKER_ENGINE=codex run_dispatch 41`) reaches the
# script for exactly one call.
gh_pr() {  # $1=number $2=state $3=isDraft(0|1) $4=labels (comma-separated, "" for none)
    N="$1" STATE="$2" DRAFT="$3" LABELS="$4" SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
n = int(os.environ["N"])
labels = [{"name": l} for l in os.environ["LABELS"].split(",") if l]
d = {"number": n, "title": "feat: add f", "body": "Adds f.\n\nCloses #7",
     "baseRefName": "main", "headRefName": "feat/x", "headRefOid": os.environ["SHA"],
     "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": os.environ["DRAFT"] == "1",
     "state": os.environ["STATE"], "labels": labels, "closingIssuesReferences": []}
json.dump(d, open(os.path.join(os.environ["MOCK_DIR"], "pr-%d.json" % n), "w"))
PY
}
run_dispatch() { "$DISPATCH" "$@"; }

echo "engine switch (one harness, two model routes):"
reset_state
: > "$SPAWN_LOG"
gh_pr 41 OPEN 0 ""                                  # helper: canned PR, no labels
WORKER_ENGINE=codex run_dispatch 41
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-41" "default-codex env spawns the one-harness daemon"
assert_not_contains "$(cat "$SPAWN_LOG")" "codex-spawn:" "codex-CLI worker species is retired from dispatch"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=$HOME/.claude/clodex-settings.json;effort=xhigh" "gateway route rides DAEMON_CLAUDE_SETTINGS/EFFORT"
prompt="$(cat "$PROMPT_DIR/review-pr-41.prompt")"
assert_contains "$prompt" "review-engine.sh" "prompt binds the engine script path"
assert_contains "$prompt" '`BASE_REF`: main' "prompt binds the base ref the engine call uses"
assert_not_contains "$prompt" "--criteria" "criteria concept is gone from the rendered prompt"
assert_not_contains "$prompt" "developer_instructions" "no developer instructions ride the rendered prompt"
assert_not_contains "$prompt" "{{ENGINE_BLOCK}}" "engine block placeholder rendered"
assert_not_contains "$prompt" "CODEX_COMPANION" "companion is gone from the prompt"

: > "$SPAWN_LOG"
gh_pr 42 OPEN 0 "engine:claude"
WORKER_ENGINE=codex run_dispatch 42
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-42" "engine:claude label overrides env"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=;effort=" "claude route spawns without the gateway settings"
prompt42="$(cat "$PROMPT_DIR/review-pr-42.prompt")"
assert_contains "$prompt42" "scripts/review-engine.sh" "claude route binds the same single engine (no per-route fork)"

echo "codex reviewer liveness in dedupe:"
sleep 300 & LIVEPID=$!
python3 - "$DAEMON_HOME" "$LIVEPID" <<'PY'
import json, sys
json.dump({"uuid": "cdec9999-0000-4000-8000-000000000000", "current": "cdec9999-0000-4000-8000-000000000000",
           "name": "review-pr-43", "engine": "codex", "pid": str(sys.argv[2]),
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(sys.argv[1] + "/cdec9999-0000-4000-8000-000000000000.json", "w"))
PY
gh_pr 43 OPEN 0 ""
out="$(WORKER_ENGINE=codex run_dispatch 43)"
assert_contains "$out" "skip active reviewer" "live codex pid dedupes"
kill "$LIVEPID" 2>/dev/null; wait "$LIVEPID" 2>/dev/null || true
: > "$SPAWN_LOG"
out="$(WORKER_ENGINE=codex run_dispatch 43)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-43" "dead codex pid retires + respawns (via the one-harness spawn)"

# ---- _wt_occupied codex-registry scan (worktree-removal guard, not dedupe) -----
# The "live worktree guard" section above pins _wt_occupied's FIRST branch (a
# `claude agents` cwd hit). Codex workers never appear in `claude agents`, so
# the function falls through to a registry scan that must count a worktree as
# occupied ONLY when a meta has ALL of: engine == "codex", cwd == the target
# worktree, status in (working, blocked), and a live pid. This section
# targets that scan directly, observed the same way as the claude-path guard:
# through dispatch_one's "live daemon occupies" refusal and whether a spawn
# happens — not by calling _wt_occupied as an internal. These dispatches use
# the suite's default WORKER_ENGINE=claude (unqualified "$DISPATCH" 5) since
# what's under test is the engine field of the meta SITTING in the worktree,
# not which engine this dispatch itself would spawn as.
echo "live worktree guard (codex registry scan):"
reset_state
out="$("$DISPATCH" 5)"                                     # setup: (re)creates $WT via a real dispatch
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "setup: worktree created via a real dispatch"
reset_state                                                  # clears registry + agents.json ([] by reset_state)

# (a) live codex-engine meta, same cwd, status working → OCCUPIED, blocked
sleep 300 & WTPID=$!
WT="$WT" PID="$WTPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8001-0000-4000-8000-000000000000",
           "current": "cdec8001-0000-4000-8000-000000000000",
           "name": "occupant", "engine": "codex", "cwd": os.environ["WT"],
           "pid": os.environ["PID"], "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8001-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "live codex-engine meta (same cwd, live pid) blocks worktree removal"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn while a live codex worker occupies the worktree"
if [ -d "$WT" ]; then pass "worktree still exists after the refused dispatch"; else
    fail "worktree still exists after the refused dispatch"; fi
kill "$WTPID" 2>/dev/null; wait "$WTPID" 2>/dev/null || true

# (b) same shape of meta, but the pid is now dead → NOT occupied, dispatch proceeds
WT="$WT" PID="$WTPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8001-0000-4000-8000-000000000000",
           "current": "cdec8001-0000-4000-8000-000000000000",
           "name": "occupant", "engine": "codex", "cwd": os.environ["WT"],
           "pid": os.environ["PID"], "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8001-0000-4000-8000-000000000000.json"), "w"))
PY
: > "$SPAWN_LOG"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "dead codex pid in the registry does not block removal — dispatch proceeds"

# (c) guard: a STALE claude-engine "working" meta in this SAME cwd must NOT
# block removal either. This pins the fail-open behavior the task required
# to preserve: the codex-registry scan filters on engine == "codex", so a
# non-codex (or missing-engine) meta is skipped outright regardless of cwd,
# status, or pid — it never reaches the pid-liveness check at all.
reset_state
WT="$WT" python3 - <<'PY'
import json, os
json.dump({"uuid": "aaaa9001-0000-4000-8000-000000000000",
           "current": "aaaa9001-0000-4000-8000-000000000000",
           "name": "stale-claude-occupant", "engine": "claude", "cwd": os.environ["WT"],
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "aaaa9001-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "stale claude-engine meta in the same cwd does not block removal (fail-open preserved)"
reset_state

# (d) host-aware: a codex meta whose pid is live HERE but was recorded on
# another host (registry migrated on a state volume) is NOT an occupant —
# the process did not migrate, only its number did.
sleep 300 & WTPID=$!
WT="$WT" PID="$WTPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8002-0000-4000-8000-000000000000",
           "current": "cdec8002-0000-4000-8000-000000000000",
           "name": "occupant", "engine": "codex", "cwd": os.environ["WT"],
           "pid": os.environ["PID"], "host": "old-host", "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8002-0000-4000-8000-000000000000.json"), "w"))
PY
: > "$SPAWN_LOG"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host codex pid does not block removal — dispatch proceeds"
kill "$WTPID" 2>/dev/null; wait "$WTPID" 2>/dev/null || true
reset_state

# ---- dedupe is host-aware too ---------------------------------------------------
# A working codex reviewer meta whose live-here pid carries a foreign host must
# read as DEAD in _decide: respawn, not "skip active reviewer".
echo "dedupe (host-aware):"
sleep 300 & DEDUPID=$!
PID="$DEDUPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8003-0000-4000-8000-000000000000",
           "current": "cdec8003-0000-4000-8000-000000000000",
           "name": "review-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": "old-host", "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8003-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:cdec8003" "foreign-host live pid → reviewer treated as dead and retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host live pid → respawned"
reset_state
# A rebuilt host can keep its hostname while getting a fresh pid namespace.
PID="$DEDUPID" H="$(hostname)" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8003-0000-4000-8000-000000000000",
           "current": "cdec8003-0000-4000-8000-000000000000",
           "name": "review-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": os.environ["H"], "boot_id": "boot-old",
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8003-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:cdec8003" "prior-boot live pid → reviewer treated as dead and retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "prior-boot live pid → respawned"
reset_state
# control: same live pid, HOST MATCHING this machine → still a live occupant
PID="$DEDUPID" H="$(hostname)" B="$DAEMON_BOOT_ID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8003-0000-4000-8000-000000000000",
           "current": "cdec8003-0000-4000-8000-000000000000",
           "name": "review-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": os.environ["H"], "boot_id": os.environ["B"], "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8003-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "same-host live pid still skips as active"
assert_equals "$(cat "$SPAWN_LOG")" "" "same-host live pid spawns nothing"
kill "$DEDUPID" 2>/dev/null; wait "$DEDUPID" 2>/dev/null || true
reset_state

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
