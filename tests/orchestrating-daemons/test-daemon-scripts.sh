#!/usr/bin/env bash
#
# Integration tests for the orchestrating-daemons toolkit.
#
# The daemon scripts shell out to the real `claude` CLI (claude --bg [--resume] /
# agents / stop). To stay hermetic — deterministic, offline, no auth, no real
# sessions — this test puts a STUB `claude` first on PATH that mimics the CLI's
# observable behavior (colored bg banner, agents --json, transcript files, fork
# via --bg --resume, stop). We then drive the real scripts end-to-end and assert
# on the registry, replies, and status transitions they produce.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/orchestrating-daemons/scripts"

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
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"
    else pass "$3"; fi
}
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
assert_file_absent() {
    if [[ ! -e "$1" ]]; then pass "$2"; else fail "$2"; echo "    still present: $1"; fi
}

# ---- environment: isolated HOME, registry, PATH-shadowed claude stub ---------
export HOME="$TEST_ROOT/home"
export DAEMON_HOME="$TEST_ROOT/registry"
export STUB_STATE="$TEST_ROOT/stub"
export DAEMON_TIMEOUT=10
export DAEMON_UUID_POLL=5
export DAEMON_BOOT_ID="boot-current"
WORK="$TEST_ROOT/work"
mkdir -p "$HOME" "$WORK" "$STUB_STATE/agents"

STUB_BIN="$TEST_ROOT/bin"
mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
# Minimal deterministic stand-in for the `claude` CLI (test use only).
set -euo pipefail
mkdir -p "$STUB_STATE/agents" "$STUB_STATE/log"
echo "$*" >> "$STUB_STATE/log/calls.log"

case "${1:-}" in
  agents)
    python3 - "$STUB_STATE/agents" <<'PY'
import glob, json, os, sys
out = []
for f in glob.glob(os.path.join(sys.argv[1], '*')):
    m = dict(l.strip().split('=', 1) for l in open(f) if '=' in l)
    out.append({"id": m.get("short"), "sessionId": m.get("uuid"), "kind": "background",
                "name": m.get("name"), "state": m.get("state", "done"),
                "status": m.get("status", ""), "cwd": m.get("cwd", "")})
print(json.dumps(out))
PY
    exit 0 ;;
  stop) echo "stopped ${2:-}"; exit 0 ;;
  rm)
    # Real `claude rm` deregisters the session (jobs entry + supervisor record)
    # and deletes a CLEAN worktree with the owning turn. The purge dirty-guards
    # the daemon's worktree with a sentinel — log whether it was present at rm
    # time so the test can prove the guard held DURING the call.
    g="absent"
    [ -n "${STUB_GUARD_DIR:-}" ] && [ -f "$STUB_GUARD_DIR/.daemon-turn-live" ] && g="present"
    echo "rm-guard:$g" >> "$STUB_STATE/log/calls.log"
    rm -f "$STUB_STATE/agents/${2:-}"
    echo "removed ${2:-}"; exit 0 ;;
esac

args=("$@")
prompt="${args[$((${#args[@]} - 1))]}"
has_bg=0; name=""; resume_uuid=""; worktree=""; i=0
while [ $i -lt ${#args[@]} ]; do
  case "${args[$i]}" in
    --bg) has_bg=1 ;;
    -n) i=$((i + 1)); name="${args[$i]}" ;;
    --resume) i=$((i + 1)); resume_uuid="${args[$i]}" ;;
    --worktree) i=$((i + 1)); worktree="${args[$i]}" ;;
  esac
  i=$((i + 1))
done

tx_path() { printf '%s/.claude/projects/%s/%s.jsonl' "$HOME" "$(printf '%s' "$PWD" | sed 's#/#-#g')" "$1"; }
write_asst() {
  local f; f="$(tx_path "$1")"; mkdir -p "$(dirname "$f")"
  python3 - "$f" "$2" <<'PY'
import json, sys
open(sys.argv[1], 'a').write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": sys.argv[2]}]}}) + "\n")
PY
}

if [ $has_bg -eq 1 ]; then
  # Failure-mode switch: make the --bg launch itself fail (e.g. session not
  # resumable). Exercises daemon-resume's fork-launch-failure path.
  if [ "${STUB_FAIL_BG:-0}" = "1" ]; then
    echo "stub: simulated --bg launch failure" >&2
    exit 1
  fi
  n=$(cat "$STUB_STATE/counter" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_STATE/counter"
  short=$(printf '%08x' "$n")
  uuid="${short}-e808-4cad-a7e0-c1e6447bad28"
  # STUB_NO_UUID emulates an agents row whose sessionId never materializes.
  [ "${STUB_NO_UUID:-0}" = "1" ] && uuid=""
  # --worktree makes the daemon's real cwd the worktree path (what agents reports).
  cwd="$PWD"; [ -n "$worktree" ] && cwd="$PWD/.claude/worktrees/$worktree"
  # STUB_BG_STATE pins the created agent's reported state (default done). Setting
  # it to `running` keeps the turn non-terminal so the resume watcher times out.
  { echo "short=$short"; echo "uuid=$uuid"; echo "name=$name"; echo "state=${STUB_BG_STATE:-done}"; echo "status=${STUB_BG_STATUS:-}"; echo "cwd=$cwd"; } > "$STUB_STATE/agents/$short"
  # A resume FORKS a new session: the new turn's transcript records which session
  # it forked from, so the test can prove the registry chains ids across turns.
  if [ -z "$uuid" ]; then
    :  # no session uuid → no transcript to write
  elif [ -n "$resume_uuid" ]; then
    write_asst "$uuid" "FORKED:$resume_uuid:ANSWER:$prompt"
  else
    write_asst "$uuid" "ANSWER:$prompt"
  fi
  printf 'backgrounded · \033[36m%s\033[39m · %s\n' "$short" "$name"
  exit 0
fi

echo "stub: unhandled invocation: $*" >&2; exit 1
STUB
chmod +x "$STUB_BIN/claude"
export PATH="$STUB_BIN:$PATH"

# ---- 1) lib helpers ----------------------------------------------------------
echo "lib helpers:"
LIB_OUT="$(
  source "$SCRIPTS_DIR/_lib.sh"
  printf 'backgrounded · \033[36mabc12345\033[39m · x\n' | _strip_ansi
  _meta_set 11111111-aaaa-4000-8000-000000000000 name one
  _meta_set 22222222-bbbb-4000-8000-000000000000 name two
  echo "resolve_full=$(_resolve_uuid 11111111-aaaa-4000-8000-000000000000)"
  echo "resolve_short=$(_resolve_uuid 22222222)"
  echo "resolve_missing_rc=$(_resolve_uuid deadbeef 2>/dev/null; echo $?)"
)"
assert_contains "$LIB_OUT" "backgrounded · abc12345 · x" "_strip_ansi removes ANSI codes"
assert_contains "$LIB_OUT" "resolve_full=11111111-aaaa-4000-8000-000000000000" "_resolve_uuid resolves a full uuid"
assert_contains "$LIB_OUT" "resolve_short=22222222-bbbb-4000-8000-000000000000" "_resolve_uuid resolves a short id"
assert_contains "$LIB_OUT" "resolve_missing_rc=1" "_resolve_uuid fails on unknown id"

# A daemon can end a turn blocked on an AskUserQuestion tool call (observed
# live: `claude agents` shows state=blocked, and the question text lives in the
# tool_use input, not in any text block). _transcript_reply must surface it —
# otherwise the recorded reply is empty and the question is invisible.
ASKQ_UUID="33333333-cccc-4000-8000-000000000000"
ASKQ_TX="$HOME/.claude/projects/fake-proj/$ASKQ_UUID.jsonl"
mkdir -p "$(dirname "$ASKQ_TX")"
python3 - "$ASKQ_TX" <<'PY'
import json, sys
row = {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Before I pick, one question."},
    {"type": "tool_use", "name": "AskUserQuestion",
     "input": {"questions": [{"question": "Which color should the widget be?",
                              "options": [{"label": "Red"}, {"label": "Blue"}]}]}}]}}
open(sys.argv[1], "w").write(json.dumps(row) + "\n")
PY
ASKQ_OUT="$(source "$SCRIPTS_DIR/_lib.sh"; _transcript_reply "$ASKQ_UUID")"
assert_contains "$ASKQ_OUT" "Which color should the widget be?" "pending AskUserQuestion question surfaced in reply"
assert_contains "$ASKQ_OUT" "Red / Blue" "pending question options rendered"
assert_contains "$ASKQ_OUT" "Before I pick, one question." "turn text still printed alongside the pending question"
assert_contains "$ASKQ_OUT" "daemon-resume.sh" "reply points at the answer path"

# A turn can also be blocked with NO pending AskUserQuestion in the transcript —
# a harness-level (permission) prompt holds the tool call before it is written
# (observed live). _record_reply must annotate that shape, and must NOT annotate
# a blocked turn whose transcript already carries the pending question.
PERM_UUID="55555555-eeee-4000-8000-000000000000"
PERM_TX="$HOME/.claude/projects/fake-proj/$PERM_UUID.jsonl"
python3 - "$PERM_TX" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps(
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "About to ask something."}]}}) + "\n")
PY
(source "$SCRIPTS_DIR/_lib.sh"; _record_reply "$PERM_UUID" "$PERM_UUID" blocked)
assert_contains "$(cat "$DAEMON_HOME/$PERM_UUID.reply.txt")" "blocked on a harness prompt" \
    "blocked-without-question reply carries the harness-prompt marker"
MARK2_UUID="66666666-ffff-4000-8000-000000000000"
(source "$SCRIPTS_DIR/_lib.sh"; _record_reply "$ASKQ_UUID" "$MARK2_UUID" blocked)
grep -q "blocked on a harness prompt" "$DAEMON_HOME/$MARK2_UUID.reply.txt" \
    && fail "pending-question reply has no harness-prompt marker" \
    || pass "pending-question reply has no harness-prompt marker"
(source "$SCRIPTS_DIR/_lib.sh"; _record_reply "$PERM_UUID" "$MARK2_UUID" "done")
grep -q "blocked on a harness prompt" "$DAEMON_HOME/$MARK2_UUID.reply.txt" \
    && fail "non-blocked reply has no harness-prompt marker" \
    || pass "non-blocked reply has no harness-prompt marker"

# DAEMON_TIMEOUT=0 makes the watcher poll without an iteration cap (watch forever).
{ echo "short=eeeeeeee"; echo "uuid=eeeeeeee-0000-4000-8000-000000000000"
  echo "name=z"; echo "state=done"; echo "status="; echo "cwd=/tmp"; } > "$STUB_STATE/agents/eeeeeeee"
NOCAP_OUT="$(
  source "$SCRIPTS_DIR/_lib.sh"
  _poll_until_done eeeeeeee 0
)"
assert_contains "$NOCAP_OUT" "eeeeeeee-0000-4000-8000-000000000000 done" "_poll_until_done 0 has no iteration cap"
rm -f "$STUB_STATE/agents/eeeeeeee"

# daemon-reply falls back to the live transcript when the recorded reply file is
# missing/empty (the watcher gave up before a long turn finished). The fallback
# must read the CURRENT (latest-forked) session, not the daemon key — so point
# `current` at a distinct session with its own transcript and assert on its text.
CURSESS="44444444-dddd-4000-8000-000000000000"
CURSESS_TX="$HOME/.claude/projects/fake-proj2/$CURSESS.jsonl"
mkdir -p "$(dirname "$CURSESS_TX")"
python3 - "$CURSESS_TX" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps(
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "reply from the current forked turn"}]}}) + "\n")
PY
(source "$SCRIPTS_DIR/_lib.sh"; _meta_set "$ASKQ_UUID" name lagged task probe status idle turns 2 current "$CURSESS")
LAG_OUT="$("$SCRIPTS_DIR/daemon-reply.sh" 33333333)"
assert_contains "$LAG_OUT" "reply from the current forked turn" "daemon-reply falls back to the CURRENT session's transcript"
rm -rf "${DAEMON_HOME:?}"/*

# ---- 2) spawn (claude --bg) --------------------------------------------------
echo "spawn:"
SPAWN_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "researcher" "PING-scope-42" "$WORK")"
assert_contains "$SPAWN_OUT" "PING-scope-42" "spawn reads the first-turn reply from the transcript"
assert_contains "$SPAWN_OUT" "visible in 'claude agents'" "spawn reports claude agents visibility"
UUID=""
for _f in "$DAEMON_HOME"/*.json; do
  case "$_f" in *.reply.json) continue ;; esac
  UUID="$(basename "$_f" .json)"; break
done
META="$(cat "$DAEMON_HOME/$UUID.json")"
assert_contains "$META" '"name": "researcher"' "spawn registers the name"
assert_contains "$META" '"status": "idle"' "spawn marks status idle after a done first turn"
assert_contains "$META" '"turns": "1"' "spawn records turn 1"
assert_contains "$META" '"short":' "spawn records the short id (needed for the fork's claude stop)"
assert_contains "$META" "\"current\": \"$UUID\"" "spawn seeds current = the first-turn uuid"
SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$UUID.json")"

# ---- 2b) spawn --no-wait (fire-and-forget registration) -----------------------
# For runner/cron dispatch: register the daemon and return immediately; the
# first turn keeps running. Contract: status=working + no reply file while the
# turn runs (daemon-reply reads the live transcript, same as a watcher
# timeout); when the turn ALREADY ended at poll time, record the truth instead.
echo "spawn --no-wait:"
NW_OUT="$(STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "nowaiter" "LONG-TASK-7" "$WORK")"
assert_contains "$NW_OUT" "daemon spawned (no-wait): nowaiter" "no-wait reports the spawn"
NW_UUID="$(printf '%s' "$NW_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
NW_META="$(cat "$DAEMON_HOME/$NW_UUID.json")"
assert_contains "$NW_META" '"status": "working"' "no-wait records status=working while the turn runs"
assert_contains "$NW_META" '"turns": "1"' "no-wait records turn 1"
assert_contains "$NW_META" "\"current\": \"$NW_UUID\"" "no-wait seeds current = the first-turn uuid"
assert_file_absent "$DAEMON_HOME/$NW_UUID.reply.txt" "no-wait writes no reply file for a running turn"
assert_contains "$("$SCRIPTS_DIR/daemon-reply.sh" "$NW_UUID")" "ANSWER:LONG-TASK-7" "daemon-reply reads the running no-wait turn's transcript"

NW2_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "nowaiter2" "QUICK-TASK-8" "$WORK")"
NW2_UUID="$(printf '%s' "$NW2_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
assert_contains "$(cat "$DAEMON_HOME/$NW2_UUID.json")" '"status": "idle"' "no-wait records idle when the first turn already finished"
assert_file_exists "$DAEMON_HOME/$NW2_UUID.reply.txt" "no-wait records the reply of an already-finished turn"

NWX_RC=0
STUB_NO_UUID=1 DAEMON_UUID_POLL=2 "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "nouuid-nw" "seed-nw" "$WORK" >/dev/null 2>&1 || NWX_RC=$?
[ "$NWX_RC" -ne 0 ] && pass "no-wait with a uuid-less agents row exits nonzero" \
    || fail "no-wait with a uuid-less agents row exits nonzero"

# ---- 3) list / reply / mark --------------------------------------------------
echo "list / reply / mark:"
assert_contains "$("$SCRIPTS_DIR/daemon-list.sh")" "researcher" "list shows the daemon"
assert_contains "$("$SCRIPTS_DIR/daemon-reply.sh" "$SHORT")" "ANSWER:PING-scope-42" "reply prints the latest reply by short id"
"$SCRIPTS_DIR/daemon-mark.sh" "$SHORT" awaiting-human "needs a product call" >/dev/null
assert_contains "$(cat "$DAEMON_HOME/$UUID.json")" '"status": "awaiting-human"' "mark sets the judgment status"
assert_contains "$("$SCRIPTS_DIR/daemon-list.sh" awaiting-human)" "researcher" "list filters by status"

# ---- 4) resume (fork a new native --bg turn) ---------------------------------
echo "resume:"
meta_field() { sed -n "s/.*\"$1\": \"\([^\"]*\)\".*/\1/p" "$DAEMON_HOME/$UUID.json"; }

mkdir -p "$HOME/.claude/jobs/$SHORT"   # the first turn's dashboard (jobs) entry
RESUME_OUT="$("$SCRIPTS_DIR/daemon-resume.sh" "$SHORT" "stay in scope please")"
# The forked turn's reply proves it carried the ORIGINAL session forward.
assert_contains "$RESUME_OUT" "FORKED:$UUID:ANSWER:stay in scope please" "resume returns the forked follow-up reply"
CUR1="$(meta_field current)"
[ -n "$CUR1" ] && [ "$CUR1" != "$UUID" ] && pass "resume advances current to a NEW forked uuid" \
    || fail "resume advances current to a NEW forked uuid"
SHORT1="$(meta_field short)"
[ -n "$SHORT1" ] && [ "$SHORT1" != "$SHORT" ] && pass "resume updates short to the new turn's short" \
    || fail "resume updates short to the new turn's short"
assert_contains "$(cat "$DAEMON_HOME/$UUID.json")" '"turns": "2"' "resume increments the turn count"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "stop $SHORT" "resume stops the old bg turn before forking"
# The reply file stays keyed by the ORIGINAL uuid.
assert_file_exists "$DAEMON_HOME/$UUID.reply.txt" "reply file keyed by the original uuid"
assert_contains "$(cat "$DAEMON_HOME/$UUID.reply.txt")" "FORKED:$UUID:ANSWER:stay in scope please" "reply file holds the fork reply"
# The superseded turn is PURGED once the fork is confirmed: its dashboard
# (jobs) entry and transcript are gone; the fork carried the content forward.
assert_file_absent "$HOME/.claude/jobs/$SHORT" "resume purges the old turn's dashboard jobs entry"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "rm $SHORT" "resume deregisters the old turn via claude rm (file deletion alone resurrects on attach)"
[ -z "$(ls "$HOME/.claude/projects/"*"/$UUID.jsonl" 2>/dev/null)" ] && pass "resume purges the old turn's transcript" \
    || fail "resume purges the old turn's transcript"
assert_file_exists "$(ls "$HOME/.claude/projects/"*"/$CUR1.jsonl" 2>/dev/null | head -1)" "forked session has its own transcript"
# _resolve_uuid maps the CURRENT short id back to the daemon's stable key.
assert_equals "$(source "$SCRIPTS_DIR/_lib.sh"; _resolve_uuid "$SHORT1")" "$UUID" "_resolve_uuid resolves a daemon by its current short id"

# A SECOND resume must fork from the PREVIOUS current (chain), driven by the
# current short — proving the id chain, not the original, is what advances.
RESUME2_OUT="$("$SCRIPTS_DIR/daemon-resume.sh" "$SHORT1" "one more thing")"
assert_contains "$RESUME2_OUT" "FORKED:$CUR1:ANSWER:one more thing" "second resume forks from the previous current (chain)"
assert_contains "$(cat "$DAEMON_HOME/$UUID.json")" '"turns": "3"' "second resume increments turns again"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "stop $SHORT1" "second resume stops the previous turn's short"
[ -z "$(ls "$HOME/.claude/projects/"*"/$CUR1.jsonl" 2>/dev/null)" ] && pass "second resume purges the middle turn's transcript" \
    || fail "second resume purges the middle turn's transcript"
SHORT2="$(meta_field short)"
assert_contains "$("$SCRIPTS_DIR/daemon-list.sh")" "$SHORT2" "list SHORT column shows the current turn's short"

# ---- 4b) gateway settings/effort dimension ------------------------------------
# A daemon spawned with DAEMON_CLAUDE_SETTINGS/DAEMON_CLAUDE_EFFORT must carry
# --settings/--effort on the spawn argv, persist both in its registry meta, and
# — the part that actually bites — reconstruct BOTH on every resume fork.
# Without the meta round-trip, a gateway daemon silently reverts to plain
# Anthropic models on its first resume.
echo "gateway settings:"
GW_SETTINGS="$TEST_ROOT/gw-settings.json"
echo '{}' > "$GW_SETTINGS"
GW_OUT="$(DAEMON_CLAUDE_SETTINGS="$GW_SETTINGS" DAEMON_CLAUDE_EFFORT="xhigh" \
  "$SCRIPTS_DIR/daemon-spawn.sh" "gwdaemon" "GW-TASK-1" "$WORK")"
GW_UUID="$(printf '%s' "$GW_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
GW_SPAWN_CALL="$(grep -- "GW-TASK-1" "$STUB_STATE/log/calls.log" | head -1)"
assert_contains "$GW_SPAWN_CALL" "--settings $GW_SETTINGS" "gateway spawn argv carries --settings"
assert_contains "$GW_SPAWN_CALL" "--effort xhigh" "gateway spawn argv carries --effort"
GW_META="$(cat "$DAEMON_HOME/$GW_UUID.json")"
assert_contains "$GW_META" "\"settings\": \"$GW_SETTINGS\"" "gateway spawn persists settings in the registry meta"
assert_contains "$GW_META" '"effort": "xhigh"' "gateway spawn persists effort in the registry meta"
GW_SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$GW_UUID.json")"
mkdir -p "$HOME/.claude/jobs/$GW_SHORT"
GW_RESUME_OUT="$("$SCRIPTS_DIR/daemon-resume.sh" "$GW_SHORT" "GW-FOLLOWUP-2")"
assert_contains "$GW_RESUME_OUT" "FORKED:$GW_UUID:ANSWER:GW-FOLLOWUP-2" "gateway resume forks the session"
GW_FORK_CALL="$(grep -- "GW-FOLLOWUP-2" "$STUB_STATE/log/calls.log" | head -1)"
assert_contains "$GW_FORK_CALL" "--settings $GW_SETTINGS" "gateway resume fork argv carries --settings (no silent model swap)"
assert_contains "$GW_FORK_CALL" "--effort xhigh" "gateway resume fork argv carries --effort"
PLAIN_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "plaindaemon" "PLAIN-TASK-9" "$WORK")"
PLAIN_UUID="$(printf '%s' "$PLAIN_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
PLAIN_CALL="$(grep -- "PLAIN-TASK-9" "$STUB_STATE/log/calls.log" | head -1)"
assert_not_contains "$PLAIN_CALL" "--settings" "plain spawn argv carries no --settings"
assert_not_contains "$PLAIN_CALL" "--effort" "plain spawn argv carries no --effort"
assert_not_contains "$(cat "$DAEMON_HOME/$PLAIN_UUID.json")" '"settings"' "plain spawn meta has no settings field"

# ---- 4c) finalize (the claude-species finisher) --------------------------------
# A --no-wait daemon registers status=working and NOTHING ever finalized it:
# daemon-reply only reads, and the self-finalizer belonged to the codex
# species. daemon-finalize.sh records a finished --bg turn's reply + terminal
# status into the registry so dispatch dedupe can tell finished from live.
echo "finalize:"
FIN_OUT="$(STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "finwork" "FIN-TASK-1" "$WORK")"
FIN_UUID="$(printf '%s' "$FIN_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
FIN_SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$FIN_UUID.json")"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN_UUID")" "live" "finalize reports a running turn live and touches nothing"
assert_contains "$(cat "$DAEMON_HOME/$FIN_UUID.json")" '"status": "working"' "finalize leaves a live turn's meta working"
assert_file_absent "$DAEMON_HOME/$FIN_UUID.reply.txt" "finalize writes no reply for a live turn"
sed -i '' 's/^state=running$/state=done/' "$STUB_STATE/agents/$FIN_SHORT"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN_UUID")" "idle" "finalize records a done turn as idle"
assert_contains "$(cat "$DAEMON_HOME/$FIN_UUID.json")" '"status": "idle"' "finalize persists the idle status"
assert_contains "$(cat "$DAEMON_HOME/$FIN_UUID.reply.txt")" "ANSWER:FIN-TASK-1" "finalize records the turn's reply from the transcript"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN_UUID")" "noop" "finalize is idempotent on an already-final meta"
FIN2_OUT="$(STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "finerr" "FIN-TASK-2" "$WORK")"
FIN2_UUID="$(printf '%s' "$FIN2_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
FIN2_SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$FIN2_UUID.json")"
sed -i '' 's/^state=running$/state=blocked/' "$STUB_STATE/agents/$FIN2_SHORT"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN2_UUID")" "live" "finalize treats a prompt-blocked session as live (resumable)"
sed -i '' 's/^state=blocked$/state=error/' "$STUB_STATE/agents/$FIN2_SHORT"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN2_UUID")" "error" "finalize records an errored turn as error"
FIN3_OUT="$(STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "fingone" "FIN-TASK-3" "$WORK")"
FIN3_UUID="$(printf '%s' "$FIN3_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
FIN3_SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$FIN3_UUID.json")"
rm -f "$STUB_STATE/agents/$FIN3_SHORT"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN3_UUID")" "absent" "finalize reports a vanished session absent, meta untouched"
assert_contains "$(cat "$DAEMON_HOME/$FIN3_UUID.json")" '"status": "working"' "absent session leaves the meta for the caller's dead-worker path"
CODEX_FIN="cdxf0000-0000-4000-8000-000000000000"
printf '{"uuid":"%s","current":"%s","short":"cdxf0000","name":"cdxfin","engine":"codex","status":"working"}' \
  "$CODEX_FIN" "$CODEX_FIN" > "$DAEMON_HOME/$CODEX_FIN.json"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$CODEX_FIN")" "noop" "finalize noops on codex-engine metas (they self-finalize)"
rm -f "$DAEMON_HOME/$CODEX_FIN.json"

# Production shape (observed live 2026-07-15): a finished --bg session LINGERS
# in `claude agents` with state=working while its harness process stays alive;
# the turn signal is `status` (busy while a turn runs, idle after). Keying on
# state alone reads a finished daemon as live forever.
FIN5_OUT="$(STUB_BG_STATE=working STUB_BG_STATUS=busy "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "finling" "FIN-TASK-5" "$WORK")"
FIN5_UUID="$(printf '%s' "$FIN5_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
FIN5_SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$FIN5_UUID.json")"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN5_UUID")" "live" "state=working with status=busy is a live turn"
sed -i '' 's/^status=busy$/status=idle/' "$STUB_STATE/agents/$FIN5_SHORT"
assert_equals "$("$SCRIPTS_DIR/daemon-finalize.sh" "$FIN5_UUID")" "idle" "state=working with status=idle is a FINISHED lingering turn, not live"
assert_contains "$(cat "$DAEMON_HOME/$FIN5_UUID.reply.txt")" "ANSWER:FIN-TASK-5" "lingering finished turn's reply is recorded"

# The blocking-mode watcher must see the same truth: a lingering finished
# session (state=working, status=idle) terminates _poll_until_done as done
# instead of polling to timeout.
POLL_OUT="$(
  export PATH="$STUB_BIN:$PATH"
  # shellcheck source=/dev/null
  . "$SCRIPTS_DIR/_lib.sh"
  _poll_until_done "$FIN5_SHORT" 2
)" || true
assert_contains "$POLL_OUT" " done " "poll normalizes the lingering finished shape to done"

# ---- 5) retire ---------------------------------------------------------------
echo "retire:"
"$SCRIPTS_DIR/daemon-retire.sh" "$SHORT" >/dev/null
assert_contains "$(cat "$DAEMON_HOME/$UUID.json")" '"status": "retired"' "retire marks the daemon retired"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "stop $SHORT2" "retire stops the CURRENT turn's short"
"$SCRIPTS_DIR/daemon-retire.sh" "$SHORT" purge >/dev/null
assert_file_absent "$DAEMON_HOME/$UUID.json" "retire purge removes the registry record"

FOREIGN_UUID="face0000-0000-4000-8000-000000000000"
printf '{"uuid":"%s","current":"%s","short":"face0000","name":"foreign","engine":"claude","host":"old-host","boot_id":"boot-old","status":"working"}' \
  "$FOREIGN_UUID" "$FOREIGN_UUID" > "$DAEMON_HOME/$FOREIGN_UUID.json"
: > "$STUB_STATE/log/calls.log"
"$SCRIPTS_DIR/daemon-retire.sh" "$FOREIGN_UUID" >/dev/null
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "stop face0000" "retire does not stop a foreign-host Claude session"
assert_contains "$(cat "$DAEMON_HOME/$FOREIGN_UUID.json")" '"status": "retired"' "foreign-host Claude record is still retired"

# _boot_id must record the BOOT identity — on macOS the sec field, where a
# greedy `.*sec = ` match lands inside `usec = ` and records microseconds.
# Cross-check against an independent parse (Linux: the boot_id file verbatim;
# macOS: the first integer in kern.boottime is the sec field).
if [ -r /proc/sys/kernel/random/boot_id ]; then
    BOOT_EXPECT="$(cat /proc/sys/kernel/random/boot_id)"
else
    BOOT_EXPECT="$(sysctl -n kern.boottime | grep -oE '[0-9]+' | head -1)"
fi
BOOT_GOT="$(bash -c "source '$SCRIPTS_DIR/_lib.sh' >/dev/null 2>&1; _boot_id")"
[ -n "$BOOT_GOT" ] && [ "$BOOT_GOT" = "$BOOT_EXPECT" ] \
    && pass "_boot_id records the boot identity, not a substring field" \
    || fail "_boot_id records the boot identity, not a substring field (got: $BOOT_GOT, want: $BOOT_EXPECT)"

# ---- 6) worktree isolation (native --worktree threading) ---------------------
echo "worktree isolation:"
WT_REPO="$TEST_ROOT/wtrepo"; mkdir -p "$WT_REPO"
WT_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "featdaemon" "build the feature" "$WT_REPO" "featdaemon")"
assert_contains "$WT_OUT" "branch worktree-featdaemon" "spawn reports the isolated branch"
WT_SHORT="$(printf '%s' "$WT_OUT" | sed -n 's/.*\[\([0-9a-f]*\) \/ .*/\1/p' | head -1)"
WT_UUID="$(printf '%s' "$WT_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
WT_META="$(cat "$DAEMON_HOME/$WT_UUID.json")"
assert_contains "$WT_META" '"worktree": "featdaemon"' "spawn records the worktree name"
assert_contains "$WT_META" '.claude/worktrees/featdaemon' "spawn records the worktree cwd reported by claude agents"
assert_contains "$("$SCRIPTS_DIR/daemon-retire.sh" "$WT_SHORT")" "branch worktree-featdaemon" "retire surfaces the isolated branch to merge"

# ---- 7) failure windows (fork launch failure, watcher timeout, ordering) -----
echo "failure windows:"
spawn_short() { printf '%s' "$1" | sed -n 's/.*\[\([0-9a-f]*\) \/ .*/\1/p' | head -1; }
spawn_uuid()  { printf '%s' "$1" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1; }

# A resumed turn must become locally owned as soon as its UUID appears, before
# the long terminal-state watcher returns. Otherwise migrated metadata remains
# foreign while a real local turn is running and dispatch can duplicate it.
M_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "migrated-resume" "seed-m" "$WORK")"
M_SHORT="$(spawn_short "$M_OUT")"; M_UUID="$(spawn_uuid "$M_OUT")"
python3 - "$DAEMON_HOME/$M_UUID.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
m["host"] = "old-host"
m["boot_id"] = "boot-old"
json.dump(m, open(p, "w"), indent=2)
PY
# The migrated short may be REUSED by an unrelated local agent — resume must
# never stop/rm through it. Seed a jobs dir standing in for that local agent.
mkdir -p "$HOME/.claude/jobs/$M_SHORT"
: > "$STUB_STATE/log/calls.log"
STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-resume.sh" "$M_SHORT" "continue locally" > "$TEST_ROOT/migrated-resume.out" 2>&1 &
M_RESUME_PID=$!
for _ in $(seq 1 20); do
    M_CUR="$(sed -n 's/.*"current": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$M_UUID.json")"
    [ -n "$M_CUR" ] && [ "$M_CUR" != "$M_UUID" ] && break
    sleep 0.25
done
M_META="$(cat "$DAEMON_HOME/$M_UUID.json")"
assert_contains "$M_META" '"host": "'"$(hostname)"'"' "running resume is re-stamped to the local host before terminal polling"
assert_contains "$M_META" '"boot_id": "boot-current"' "running resume is re-stamped to the local boot before terminal polling"
[ -n "${M_CUR:-}" ] && [ "$M_CUR" != "$M_UUID" ] \
    && pass "running resume advances current before terminal polling" \
    || fail "running resume advances current before terminal polling"
wait "$M_RESUME_PID" 2>/dev/null || true
M_CALLS="$(cat "$STUB_STATE/log/calls.log")"
assert_not_contains "$M_CALLS" "stop $M_SHORT" "migrated resume never stops through the foreign short"
assert_not_contains "$M_CALLS" "rm $M_SHORT" "migrated resume never rms through the foreign short"
[ -d "$HOME/.claude/jobs/$M_SHORT" ] && pass "migrated resume leaves the reused short's jobs dir intact" \
    || fail "migrated resume leaves the reused short's jobs dir intact"

# (a) The fork command itself fails (session not resumable). Resume must exit
# nonzero, flip status=error, and leave `current`/turns untouched — the daemon
# must not be silently advanced past a launch that never happened.
A_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "failfork" "seed-a" "$WORK")"
A_SHORT="$(spawn_short "$A_OUT")"; A_UUID="$(spawn_uuid "$A_OUT")"
mkdir -p "$HOME/.claude/jobs/$A_SHORT"
A_RC=0
STUB_FAIL_BG=1 "$SCRIPTS_DIR/daemon-resume.sh" "$A_SHORT" "go" >/dev/null 2>&1 || A_RC=$?
[ "$A_RC" -ne 0 ] && pass "fork launch failure makes resume exit nonzero" \
    || fail "fork launch failure makes resume exit nonzero"
A_META="$(cat "$DAEMON_HOME/$A_UUID.json")"
assert_contains "$A_META" '"status": "error"' "fork launch failure sets status=error"
assert_contains "$A_META" "\"current\": \"$A_UUID\"" "fork launch failure leaves current unchanged (no phantom advance)"
assert_contains "$A_META" '"turns": "1"' "fork launch failure does not bump turns"
[ -d "$HOME/.claude/jobs/$A_SHORT" ] && pass "fork launch failure purges nothing (jobs entry kept)" \
    || fail "fork launch failure purges nothing (jobs entry kept)"
assert_file_exists "$(ls "$HOME/.claude/projects/"*"/$A_UUID.jsonl" 2>/dev/null | head -1)" "fork launch failure keeps the old transcript"

# (b) The fork launches but the turn is still running when the watcher expires.
# The chain must advance to the NEW session (current/short) with status=working
# (the turn IS still running), the reply file must NOT be overwritten, and turns
# must not increment (no final reply has landed).
B_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "slowfork" "seed-b" "$WORK")"
B_SHORT="$(spawn_short "$B_OUT")"; B_UUID="$(spawn_uuid "$B_OUT")"
printf 'SENTINEL-REPLY-DO-NOT-OVERWRITE' > "$DAEMON_HOME/$B_UUID.reply.txt"
mkdir -p "$HOME/.claude/jobs/$B_SHORT"
B_RC=0
STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-resume.sh" "$B_SHORT" "long task" >/dev/null 2>&1 || B_RC=$?
[ "$B_RC" -ne 0 ] && pass "watcher timeout makes resume exit nonzero" \
    || fail "watcher timeout makes resume exit nonzero"
B_META="$(cat "$DAEMON_HOME/$B_UUID.json")"
assert_contains "$B_META" '"status": "working"' "watcher timeout records status=working (turn still running)"
B_CUR="$(sed -n 's/.*"current": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$B_UUID.json")"
[ -n "$B_CUR" ] && [ "$B_CUR" != "$B_UUID" ] && pass "watcher timeout advances current to the new forked session" \
    || fail "watcher timeout advances current to the new forked session"
B_SHORT_NEW="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$B_UUID.json")"
[ -n "$B_SHORT_NEW" ] && [ "$B_SHORT_NEW" != "$B_SHORT" ] && pass "watcher timeout advances short to the new turn" \
    || fail "watcher timeout advances short to the new turn"
assert_contains "$B_META" '"turns": "1"' "watcher timeout does not bump turns"
assert_equals "$(cat "$DAEMON_HOME/$B_UUID.reply.txt")" "SENTINEL-REPLY-DO-NOT-OVERWRITE" "watcher timeout leaves the reply file untouched"
assert_file_absent "$HOME/.claude/jobs/$B_SHORT" "confirmed-but-running fork still purges the superseded turn"

# (b2) Recovery path: once the timed-out turn lands, daemon-reply must surface
# the CURRENT session's transcript — a stale reply file from a previous turn
# must not shadow it while status=working.
B_REPLY="$("$SCRIPTS_DIR/daemon-reply.sh" "$B_UUID")"
assert_contains "$B_REPLY" "FORKED:$B_UUID:ANSWER:long task" "daemon-reply reads the timed-out turn's transcript (status=working)"
printf '%s' "$B_REPLY" | grep -Fq "SENTINEL-REPLY-DO-NOT-OVERWRITE" \
    && fail "daemon-reply ignores the stale reply file while working" \
    || pass "daemon-reply ignores the stale reply file while working"

# (e) A forked agent whose agents row never carries a sessionId must not corrupt
# the chain: the poll skips uuid-less rows, so resume times out with no uuid →
# recovery path (pending_short), current unchanged, nothing purged.
E_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "nouuid" "seed-e" "$WORK")"
E_SHORT="$(spawn_short "$E_OUT")"; E_UUID="$(spawn_uuid "$E_OUT")"
mkdir -p "$HOME/.claude/jobs/$E_SHORT"
E_RC=0
STUB_NO_UUID=1 "$SCRIPTS_DIR/daemon-resume.sh" "$E_SHORT" "go" >/dev/null 2>&1 || E_RC=$?
[ "$E_RC" -ne 0 ] && pass "uuid-less forked row makes resume exit nonzero" \
    || fail "uuid-less forked row makes resume exit nonzero"
E_META="$(cat "$DAEMON_HOME/$E_UUID.json")"
assert_contains "$E_META" "\"current\": \"$E_UUID\"" "uuid-less row leaves current unchanged"
assert_contains "$E_META" '"pending_short"' "uuid-less row stashes pending_short"
[ -d "$HOME/.claude/jobs/$E_SHORT" ] && pass "uuid-less row purges nothing" \
    || fail "uuid-less row purges nothing"

# (e2) The SAME uuid-less hole on the spawn side: the first turn's agents row
# never carries a sessionId → spawn must exit nonzero without registering
# corrupt meta (the old `read` parsing promoted the "timeout" state token into
# the uuid slot and created timeout.json).
S_RC=0
STUB_NO_UUID=1 "$SCRIPTS_DIR/daemon-spawn.sh" "nouuid-spawn" "seed-s" "$WORK" >/dev/null 2>&1 || S_RC=$?
[ "$S_RC" -ne 0 ] && pass "spawn with a uuid-less agents row exits nonzero" \
    || fail "spawn with a uuid-less agents row exits nonzero"
assert_file_absent "$DAEMON_HOME/timeout.json" "spawn never registers the state token as a uuid"

# (f) _session_purge guards: only an exactly-8-lowercase-hex short is ever
# rm -rf'ed — malformed input is a no-op, not a deletion.
mkdir -p "$HOME/.claude/jobs/deadbeef"
(source "$SCRIPTS_DIR/_lib.sh"
 _session_purge "dead;rm " ""
 _session_purge "deadbe" ""
 _session_purge "DEADBEEF" "")
[ -d "$HOME/.claude/jobs/deadbeef" ] && pass "_session_purge ignores malformed shorts" \
    || fail "_session_purge ignores malformed shorts"
(source "$SCRIPTS_DIR/_lib.sh"; _session_purge "deadbeef" "")
[ ! -d "$HOME/.claude/jobs/deadbeef" ] && pass "_session_purge removes a valid short's jobs entry" \
    || fail "_session_purge removes a valid short's jobs entry"

# (g) A worktree'd daemon's purge dirty-guards the worktree while `claude rm`
# runs: rm deletes a CLEAN worktree along with its owning turn (verified live),
# and the daemon's later turns still run inside that worktree. The stub logs
# whether the sentinel was present at rm time; it must be gone again after.
G_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "wtguard" "seed-g" "$WT_REPO" "wtguard")"
G_SHORT="$(spawn_short "$G_OUT")"
G_WT="$WT_REPO/.claude/worktrees/wtguard"; mkdir -p "$G_WT"
mkdir -p "$HOME/.claude/jobs/$G_SHORT"
STUB_GUARD_DIR="$G_WT" "$SCRIPTS_DIR/daemon-resume.sh" "$G_SHORT" "go" >/dev/null
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "rm-guard:present" "worktree purge holds the dirty-guard sentinel during claude rm"
assert_file_absent "$G_WT/.daemon-turn-live" "dirty-guard sentinel removed after purge"

# Failure paths must never deregister the old turn either — `claude rm` on the
# only recovery point would be worse than the ghost it prevents.
grep -Eq "^rm $A_SHORT$" "$STUB_STATE/log/calls.log" \
    && fail "fork launch failure never claude-rm's the old turn" \
    || pass "fork launch failure never claude-rm's the old turn"
grep -Eq "^rm $E_SHORT$" "$STUB_STATE/log/calls.log" \
    && fail "uuid-less row never claude-rm's the old turn" \
    || pass "uuid-less row never claude-rm's the old turn"

# (c) The old turn is stopped BEFORE the fork launches (never stop an in-flight
# turn after forking). Assert the ordering in calls.log for a fresh daemon.
C_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" "ordercheck" "seed-c" "$WORK")"
C_SHORT="$(spawn_short "$C_OUT")"; C_UUID="$(spawn_uuid "$C_OUT")"
"$SCRIPTS_DIR/daemon-resume.sh" "$C_SHORT" "next" >/dev/null
C_STOP_LINE="$(grep -nF "stop $C_SHORT" "$STUB_STATE/log/calls.log" | tail -1 | cut -d: -f1 || true)"
C_FORK_LINE="$(grep -nF -- "--bg --resume $C_UUID" "$STUB_STATE/log/calls.log" | tail -1 | cut -d: -f1 || true)"
if [ -n "$C_STOP_LINE" ] && [ -n "$C_FORK_LINE" ] && [ "$C_STOP_LINE" -lt "$C_FORK_LINE" ]; then
    pass "stop <old-short> precedes the --bg --resume fork in calls.log"
else
    fail "stop <old-short> precedes the --bg --resume fork in calls.log"
    echo "    stop line: ${C_STOP_LINE:-<none>}  fork line: ${C_FORK_LINE:-<none>}"
fi

# (d) An ambiguous query prints the specific ambiguity message and NOT the
# generic "no daemon matching" (python exits 4, not 3 — the wrapper must not
# double up the error).
AMBIG_ERR="$(
  source "$SCRIPTS_DIR/_lib.sh"
  _meta_set aabb0000-0000-4000-8000-000000000000 name amb-one
  _meta_set aabb1111-1111-4000-8000-000000000000 name amb-two
  _resolve_uuid aabb 2>&1 1>/dev/null || true
)"
assert_contains "$AMBIG_ERR" "ambiguous id 'aabb'" "ambiguous query prints the ambiguity message"
if printf '%s' "$AMBIG_ERR" | grep -Fq "no daemon matching"; then
    fail "ambiguous query does NOT also print 'no daemon matching'"
else
    pass "ambiguous query does NOT also print 'no daemon matching'"
fi
rm -f "$DAEMON_HOME"/aabb*.json

echo
if [ "$FAILURES" -eq 0 ]; then
    echo "All orchestrating-daemons tests passed."
else
    echo "$FAILURES orchestrating-daemons test(s) failed."
    exit 1
fi
