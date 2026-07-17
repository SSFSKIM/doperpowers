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

# stub daemon scripts (same shape as test-review-dispatch.sh)
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "spawn:$*" >> "$SPAWN_LOG"
echo "spawn-env:settings=${DAEMON_CLAUDE_SETTINGS:-};effort=${DAEMON_CLAUDE_EFFORT:-}" >> "$SPAWN_LOG"
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
ready="$(printf '%s\n' "$task" | grep '^- startup barrier:' | cut -d' ' -f4- || true)"
if [ -n "$ready" ] && [ "${STUB_NO_BIND_ACK:-0}" != "1" ]; then
  READY="$ready" UUID="$uuid" python3 - <<'PY' >/dev/null 2>&1 &
import json,os,time
for _ in range(500):
    if os.path.isfile(os.environ['READY']):
        p=os.environ['READY']+'.ack'; tmp=p+'.tmp'
        json.dump({'uuid':os.environ['UUID']},open(tmp,'w')); os.replace(tmp,p); break
    time.sleep(0.01)
PY
fi
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
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
ready="$(printf '%s\n' "$task" | grep '^- startup barrier:' | cut -d' ' -f4- || true)"
if [ -n "$ready" ] && [ "${STUB_NO_BIND_ACK:-0}" != "1" ]; then
  READY="$ready" UUID="$uuid" python3 - <<'PY' >/dev/null 2>&1 &
import json,os,time
for _ in range(500):
    if os.path.isfile(os.environ['READY']):
        p=os.environ['READY']+'.ack'; tmp=p+'.tmp'
        json.dump({'uuid':os.environ['UUID']},open(tmp,'w')); os.replace(tmp,p); break
    time.sleep(0.01)
PY
fi
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$1" >> "$SPAWN_LOG"
STUB
cat > "$STUB_DAEMONS/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "finalize:$1" >> "$SPAWN_LOG"
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
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/codex-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh" "$STUB_DAEMONS/daemon-finalize.sh"
export DAEMON_SCRIPTS="$STUB_DAEMONS"
export WORKER_ENGINE=claude

# stub board scripts (only board-bind.sh is executed by the dispatcher)
STUB_BOARD="$TEST_ROOT/stub-board"; mkdir -p "$STUB_BOARD"
cat > "$STUB_BOARD/board-bind.sh" <<'STUB'
#!/usr/bin/env bash
echo "bind:$1:$2" >> "$BIND_LOG"
if [ -n "${FAIL_BIND:-}" ]; then echo "stub bind: simulated failure" >&2; exit 1; fi
Q="$1" T="$2" D="$DAEMON_HOME" python3 - <<'PY'
import glob,json,os
hits=[p for p in glob.glob(os.path.join(os.environ['D'],'*.json'))
      if os.path.basename(p)[:-5].startswith(os.environ['Q'])]
if len(hits)!=1: raise SystemExit(1)
target=hits[0]
for p in glob.glob(os.path.join(os.environ['D'],'*.json')):
    m=json.load(open(p))
    if p!=target and str(m.get('ticket','')).lstrip('#')==os.environ['T'].lstrip('#'):
        m.pop('ticket',None); json.dump(m,open(p,'w'),indent=2)
m=json.load(open(target)); m['ticket']=os.environ['T']; json.dump(m,open(target,'w'),indent=2)
PY
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

reset_state() { rm -f "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; rm -rf "$DAEMON_HOME"/land-pr-*-control.*; : > "$SPAWN_LOG"; : > "$BIND_LOG"; : > "$EDIT_LOG"; echo "[]" > "$MOCK_DIR/agents.json"; }

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
LAND_READY="$(printf '%s\n' "$PROMPT" | grep '^- startup barrier:' | cut -d' ' -f4- || true)"
assert_contains "$PROMPT" "BINDING BARRIER" "land worker blocks before any merge action until binding completes"
if [ -n "$LAND_READY" ] && [ -f "$LAND_READY" ]; then pass "land ready barrier opens after binding"; else fail "land ready barrier opens after binding"; fi
if [ -f "$LAND_READY.ack" ]; then pass "land dispatch waits for worker barrier acknowledgement"; else fail "land dispatch waits for worker barrier acknowledgement"; fi
assert_contains "$PROMPT" "Land mode: dry-run" "LAND_ENABLED unset renders dry-run (staged rollout)"
assert_contains "$PROMPT" "GitHub review decision APPROVED" "prompt names the approval signal"
assert_contains "$PROMPT" "gh pr merge 5 --squash" "prompt carries the resolved native merge method"
assert_contains "$PROMPT" "primary ticket: #7" "prompt names the primary ticket (Closes #7 parsed)"
assert_contains "$PROMPT" "NEVER rebase, NEVER force-push" "merge-main-never-rebase is pinned"
assert_contains "$PROMPT" "references/land-conflicts.md" "prompt carries the runtime conflicts-procedure pointer (absolute path)"
assert_not_contains "$PROMPT" "protocol violation" "the conflicts doc binds by its bounds, not a violation flourish"
assert_not_contains "$PROMPT" "before touching a single hunk" "no read-choreography mandate — the bounds live in the doc and bind"
CONFLICTS_DOC_CONTENT="$(cat "$REPO_ROOT/skills/reviewing-prs/references/land-conflicts.md")"
assert_contains "$CONFLICTS_DOC_CONTENT" "at most 50 hand-resolved lines across at most 3 conflicted files" "land bounds live in the runtime-opened procedure"
assert_not_contains "$CONFLICTS_DOC_CONTENT" "{{" "conflicts procedure is placeholder-free (opened at runtime, never rendered)"
assert_contains "$CONFLICTS_DOC_CONTENT" "Resolve ONLY the conflict hunks" "hunks-only bound survives"
assert_not_contains "$CONFLICTS_DOC_CONTENT" "no refactors, no improvements" "hunks-only is stated as the unreviewed-code state, not a prohibition list"
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

reset_state
python3 - <<'PY'
import json, os
u = "feed0000-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "land-pr-5", "engine": "claude",
           "host": "old-host", "boot_id": "boot-old", "status": "working",
           "updated": "2026-07-12T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000"}]' > "$MOCK_DIR/agents.json"
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "foreign-host Claude land worker is retired despite a visible migrated session"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "foreign-host Claude land worker is respawned"

reset_state; seed_lander idle
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "finished land worker retired (explicit dispatch = fresh signal)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "finished land worker re-dispatched"

# host-aware: a working codex land worker whose live-here pid was recorded on
# another host (registry migrated on a state volume) is DEAD → retire+respawn.
reset_state
sleep 300 & LANDPID=$!
PID="$LANDPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "feed0000-0000-4000-8000-000000000000",
           "current": "feed0000-0000-4000-8000-000000000000",
           "name": "land-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": "old-host", "status": "working",
           "updated": "2026-07-12T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "feed0000-0000-4000-8000-000000000000.json"), "w"))
PY
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "foreign-host live pid → land worker treated as dead and retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "foreign-host live pid → respawned"
reset_state
PID="$LANDPID" H="$(hostname)" python3 - <<'PY'
import json, os
json.dump({"uuid": "feed0000-0000-4000-8000-000000000000",
           "current": "feed0000-0000-4000-8000-000000000000",
           "name": "land-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": os.environ["H"], "boot_id": "boot-old",
           "status": "working", "updated": "2026-07-12T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "feed0000-0000-4000-8000-000000000000.json"), "w"))
PY
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "prior-boot live pid → land worker treated as dead and retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "prior-boot live pid → respawned"
kill "$LANDPID" 2>/dev/null; wait "$LANDPID" 2>/dev/null || true

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

reset_state
rc=0; out="$(STUB_NO_BIND_ACK=1 LAND_ACK_POLLS=2 LAND_ACK_DELAY=0.01 "$DISPATCH" 5 2>&1)" || rc=$?
assert_equals "$rc" "1" "missing land-worker barrier ack fails dispatch"
assert_contains "$(cat "$SPAWN_LOG")" "retire:" "missing land ack retires the non-started worker"
assert_not_contains "$out" "land worker dispatched" "no success report before worker ack"

# ---- exclusive ticket ownership (board-answer must resume THE LAND WORKER) -------------
echo "exclusive binding:"
reset_state
# a finished implement worker still bound to ticket 7 sits in the registry
python3 - <<'PY'
import json, os
json.dump({"uuid": "0000impl-0000-4000-8000-000000000000",
           "current": "0000impl-0000-4000-8000-000000000000",
           "name": "review-pr-570", "status": "working", "turn_state": "idle", "ticket": "7",
           "updated": "2026-07-11T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "0000impl-0000-4000-8000-000000000000.json"), "w"))
PY
"$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "finalize:0000impl" "land handoff finalizes a lingering finished reviewer before bind"
old_ticket="$(python3 -c '
import json, os
m = json.load(open(os.path.join(os.environ["DAEMON_HOME"], "0000impl-0000-4000-8000-000000000000.json")))
print(m.get("ticket", "STRIPPED"))')"
assert_equals "$old_ticket" "STRIPPED" "the implement worker's stale binding is stripped (ownership transferred)"
assert_contains "$(cat "$BIND_LOG")" ":7" "the land worker holds the binding"

# A genuinely active owner blocks BEFORE the write-capable land worker starts.
reset_state
python3 - <<'PY'
import json,os
json.dump({'uuid':'active-review-0000-4000-8000-000000000000','current':'active-review-0000-4000-8000-000000000000',
           'name':'review-pr-570','status':'working','turn_state':'busy','ticket':'7'},
          open(os.path.join(os.environ['DAEMON_HOME'],'active-review-0000-4000-8000-000000000000.json'),'w'))
PY
echo '[{"id":"active-re","sessionId":"active-review-0000-4000-8000-000000000000","state":"working","status":"busy"}]' > "$MOCK_DIR/agents.json"
rc=0; out="$($DISPATCH 5 2>&1)" || rc=$?
assert_equals "$rc" "1" "active ticket owner blocks land dispatch"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "land worker never starts before ownership is available"

# A dead/absent stale owner is retired, then handoff proceeds.
reset_state
python3 - <<'PY'
import json,os
json.dump({'uuid':'dead-review-0000-4000-8000-000000000000','current':'dead-review-0000-4000-8000-000000000000',
           'name':'review-pr-570','status':'working','turn_state':'absent','ticket':'7'},
          open(os.path.join(os.environ['DAEMON_HOME'],'dead-review-0000-4000-8000-000000000000.json'),'w'))
PY
"$DISPATCH" 5 >/dev/null
assert_contains "$(cat "$SPAWN_LOG")" "retire:dead-review" "absent stale owner is retired before land handoff"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "land dispatch proceeds after dead owner cleanup"

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
# ONE worker species: both routes spawn via daemon-spawn.sh; the codex route
# rides the clodex gateway settings (mirrors review-dispatch.sh).
echo "engine resolution:"
reset_state
WORKER_ENGINE=codex "$DISPATCH" 5 > /dev/null
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-5" "WORKER_ENGINE=codex spawns the one worker species via daemon-spawn"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=$HOME/.claude/clodex-settings.json;effort=xhigh" "codex route rides the gateway DAEMON_CLAUDE_SETTINGS/EFFORT"
if grep -q "codex-spawn:" "$SPAWN_LOG"; then
    fail "no codex-CLI worker is ever spawned (species retired)"
else
    pass "no codex-CLI worker is ever spawned (species retired)"
fi
reset_state
"$DISPATCH" 12 > /dev/null     # suite default WORKER_ENGINE=claude; label must win
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait land-pr-12" "engine:codex label overrides the env (gateway route)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=$HOME/.claude/clodex-settings.json;effort=xhigh" "label-selected codex route also rides the gateway settings"
reset_state
"$DISPATCH" 5 > /dev/null      # suite default WORKER_ENGINE=claude
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=;effort=" "claude route spawns without the gateway settings"

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
