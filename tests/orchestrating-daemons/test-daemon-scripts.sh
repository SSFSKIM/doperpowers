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
  n=$(cat "$STUB_STATE/counter" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_STATE/counter"
  short=$(printf '%08x' "$n")
  uuid="${short}-e808-4cad-a7e0-c1e6447bad28"
  # --worktree makes the daemon's real cwd the worktree path (what agents reports).
  cwd="$PWD"; [ -n "$worktree" ] && cwd="$PWD/.claude/worktrees/$worktree"
  { echo "short=$short"; echo "uuid=$uuid"; echo "name=$name"; echo "state=done"; echo "status="; echo "cwd=$cwd"; } > "$STUB_STATE/agents/$short"
  # A resume FORKS a new session: the new turn's transcript records which session
  # it forked from, so the test can prove the registry chains ids across turns.
  if [ -n "$resume_uuid" ]; then
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
UUID="$(ls "$DAEMON_HOME"/*.json | grep -v '\.reply\.' | head -1 | xargs basename | sed 's/\.json$//')"
META="$(cat "$DAEMON_HOME/$UUID.json")"
assert_contains "$META" '"name": "researcher"' "spawn registers the name"
assert_contains "$META" '"status": "idle"' "spawn marks status idle after a done first turn"
assert_contains "$META" '"turns": "1"' "spawn records turn 1"
assert_contains "$META" '"short":' "spawn records the short id (needed for the fork's claude stop)"
assert_contains "$META" "\"current\": \"$UUID\"" "spawn seeds current = the first-turn uuid"
SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$UUID.json")"

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
# Two sessions forked → the original transcript AND the new one both exist.
assert_file_exists "$(ls "$HOME/.claude/projects/"*"/$UUID.jsonl" 2>/dev/null | head -1)" "original session transcript still exists"
assert_file_exists "$(ls "$HOME/.claude/projects/"*"/$CUR1.jsonl" 2>/dev/null | head -1)" "forked session has its own transcript"
# _resolve_uuid maps the CURRENT short id back to the daemon's stable key.
assert_equals "$(source "$SCRIPTS_DIR/_lib.sh"; _resolve_uuid "$SHORT1")" "$UUID" "_resolve_uuid resolves a daemon by its current short id"

# A SECOND resume must fork from the PREVIOUS current (chain), driven by the
# current short — proving the id chain, not the original, is what advances.
RESUME2_OUT="$("$SCRIPTS_DIR/daemon-resume.sh" "$SHORT1" "one more thing")"
assert_contains "$RESUME2_OUT" "FORKED:$CUR1:ANSWER:one more thing" "second resume forks from the previous current (chain)"
assert_contains "$(cat "$DAEMON_HOME/$UUID.json")" '"turns": "3"' "second resume increments turns again"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "stop $SHORT1" "second resume stops the previous turn's short"
SHORT2="$(meta_field short)"
assert_contains "$("$SCRIPTS_DIR/daemon-list.sh")" "$SHORT2" "list SHORT column shows the current turn's short"

# ---- 5) retire ---------------------------------------------------------------
echo "retire:"
"$SCRIPTS_DIR/daemon-retire.sh" "$SHORT" >/dev/null
assert_contains "$(cat "$DAEMON_HOME/$UUID.json")" '"status": "retired"' "retire marks the daemon retired"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "stop $SHORT2" "retire stops the CURRENT turn's short"
"$SCRIPTS_DIR/daemon-retire.sh" "$SHORT" purge >/dev/null
assert_file_absent "$DAEMON_HOME/$UUID.json" "retire purge removes the registry record"

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

echo
if [ "$FAILURES" -eq 0 ]; then
    echo "All orchestrating-daemons tests passed."
else
    echo "$FAILURES orchestrating-daemons test(s) failed."
    exit 1
fi
