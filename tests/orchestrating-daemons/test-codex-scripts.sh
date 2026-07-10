#!/usr/bin/env bash
#
# Integration tests for the codex-engine half of the orchestrating-daemons
# toolkit. Hermetic: a STUB `codex` first on PATH mimics `codex exec --json`
# (thread.started + agent_message + turn.completed JSONL, -o reply file,
# resume). We drive the real scripts and assert on registry meta, replies,
# and status transitions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS_DIR="$REPO_ROOT/skills/orchestrating-daemons/scripts"

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
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"
    else pass "$3"; fi
}

export HOME="$TEST_ROOT/home"
export DAEMON_HOME="$TEST_ROOT/registry"
export STUB_STATE="$TEST_ROOT/stub"
export DAEMON_TIMEOUT=10
export DAEMON_UUID_POLL=5
WORK="$TEST_ROOT/work"
mkdir -p "$HOME" "$WORK" "$STUB_STATE"

STUB_BIN="$TEST_ROOT/bin"
mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/codex" <<'STUB'
#!/usr/bin/env bash
# Minimal deterministic stand-in for `codex exec [resume]` (test use only).
# Event field names mirror the real CLI as pinned by Spike A.
set -euo pipefail
mkdir -p "$STUB_STATE"
echo "$*" >> "$STUB_STATE/calls.log"
[ "${1:-}" = "exec" ] || { echo "stub codex: only exec supported" >&2; exit 2; }
shift
resume=""
if [ "${1:-}" = "resume" ]; then resume="$2"; shift 2; fi
if [ -n "$resume" ]; then
  # Real `codex exec resume` has no --sandbox flag at all (rc=2, no JSON,
  # confirmed live — see docs/doperpowers/specs/2026-07-10-codex-workers-design.md).
  # Validate like the real CLI so a regression that re-adds --sandbox to a
  # resume call is actually caught here instead of silently "passing."
  for a in "$@"; do
    if [ "$a" = "--sandbox" ]; then
      echo "error: unexpected argument '--sandbox' found" >&2
      exit 2
    fi
  done
  if [ "${STUB_RESUME_FAIL_EARLY:-0}" = "1" ]; then
    echo "error: simulated early resume failure" >&2
    exit 2
  fi
fi
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift ;;
    -) : ;;
  esac
  shift
done
task="$(cat)"
if [ "${STUB_FAIL_EARLY:-0}" = "1" ]; then
  echo "stub codex: simulated launch failure" >&2
  exit 1
fi
if [ -z "$resume" ]; then
  n=$(cat "$STUB_STATE/n" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_STATE/n"
  tid="$(printf 'cdec%04d-0000-4000-8000-000000000000' "$n")"
else
  tid="$resume"
fi
printf '{"type":"thread.started","thread_id":"%s"}\n' "$tid"
[ "${STUB_SLEEP:-0}" != "0" ] && sleep "$STUB_SLEEP"
if [ "${STUB_FAIL_TURN:-0}" = "1" ]; then
  printf '{"type":"turn.failed","error":{"message":"stub turn failure"}}\n'
  exit 1
fi
reply="stub reply: $(printf '%s' "$task" | head -c 40)"
printf '{"type":"item.completed","item":{"type":"agent_message","text":"%s"}}\n' "$reply"
printf '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
[ -n "$out" ] && printf '%s' "$reply" > "$out"
exit 0
STUB
chmod +x "$STUB_BIN/codex"
export PATH="$STUB_BIN:$PATH"

meta_field() {  # <uuid> <field>
    python3 -c "import json,sys; print(json.load(open('$DAEMON_HOME/$1.json')).get('$2',''))"
}
first_uuid() { basename "$(ls "$DAEMON_HOME"/cdec*.json | head -1)" .json; }

echo "== codex-spawn: blocking happy path =="
out="$("$SCRIPTS_DIR/codex-spawn.sh" job-a "say hi" "$WORK")"
uuid="$(first_uuid)"
assert_contains "$out" "--- reply ---" "blocking spawn prints reply banner"
assert_contains "$out" "stub reply: say hi" "blocking spawn prints the reply"
assert_equals "$(meta_field "$uuid" engine)" "codex" "meta engine=codex"
assert_equals "$(meta_field "$uuid" status)" "idle" "meta status=idle after clean turn"
assert_equals "$(meta_field "$uuid" turns)" "1" "meta turns=1"
assert_equals "$(meta_field "$uuid" current)" "$uuid" "current equals uuid"
assert_file_exists "$DAEMON_HOME/$uuid.reply.txt" "reply file recorded under uuid"
flags="$(grep 'exec' "$STUB_STATE/calls.log" | head -1)"
assert_contains "$flags" "--sandbox workspace-write" "spawn passes workspace-write"
assert_contains "$flags" "features.hooks=false" "spawn disables repo hooks"
assert_contains "$flags" "approval_policy=on-request" "spawn sets approval policy"
assert_contains "$flags" "model_reasoning_effort=high" "default effort high"
assert_contains "$flags" "-m gpt-5.6-sol" "default model gpt-5.6-sol"

echo "== codex-spawn: --no-wait leaves a working daemon, then finalizes =="
STUB_SLEEP=4 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-b "slow task" "$WORK" >/dev/null
uuid_b="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
assert_equals "$(meta_field "$uuid_b" status)" "working" "no-wait registers status=working"
pid_b="$(meta_field "$uuid_b" pid)"
if kill -0 "$pid_b" 2>/dev/null; then pass "recorded pid is alive mid-turn"; else fail "recorded pid is alive mid-turn"; fi
for _ in $(seq 1 15); do [ "$(meta_field "$uuid_b" status)" != "working" ] && break; sleep 1; done
assert_equals "$(meta_field "$uuid_b" status)" "idle" "watcher finalizes status=idle"
assert_file_exists "$DAEMON_HOME/$uuid_b.reply.txt" "watcher records reply file"

echo "== codex-spawn: turn failure -> error =="
STUB_FAIL_TURN=1 "$SCRIPTS_DIR/codex-spawn.sh" job-c "will fail" "$WORK" >/dev/null 2>&1 || true
uuid_c="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
assert_equals "$(meta_field "$uuid_c" status)" "error" "failed turn records status=error"

echo "== codex-spawn: launch failure fails loud, registers nothing =="
n_before="$(ls "$DAEMON_HOME"/*.json 2>/dev/null | wc -l | tr -d ' ')"
if STUB_FAIL_EARLY=1 "$SCRIPTS_DIR/codex-spawn.sh" job-d "never starts" "$WORK" >/dev/null 2>&1; then
    fail "early failure exits nonzero"
else
    pass "early failure exits nonzero"
fi
n_after="$(ls "$DAEMON_HOME"/*.json 2>/dev/null | wc -l | tr -d ' ')"
assert_equals "$n_after" "$n_before" "early failure registers no meta"

echo "== codex-resume: same session id, turns increment =="
out="$("$SCRIPTS_DIR/codex-resume.sh" "$uuid" "follow up")"
assert_contains "$out" "stub reply: follow up" "resume prints the new reply"
assert_equals "$(meta_field "$uuid" turns)" "2" "resume increments turns"
assert_equals "$(meta_field "$uuid" current)" "$uuid" "resume keeps the session id"
assert_contains "$(cat "$STUB_STATE/calls.log")" "exec resume $uuid" "stub saw exec resume <uuid>"
resume_call="$(grep "exec resume $uuid" "$STUB_STATE/calls.log" | tail -1)"
assert_not_contains "$resume_call" "--sandbox" "resume omits --sandbox (real CLI rejects it, rc=2)"
assert_contains "$resume_call" "sandbox_mode=workspace-write" "resume passes -c sandbox_mode=workspace-write instead"

echo "== codex-resume: early launch failure does not bump turns, exits nonzero =="
turns_before="$(meta_field "$uuid" turns)"
if STUB_RESUME_FAIL_EARLY=1 "$SCRIPTS_DIR/codex-resume.sh" "$uuid" "boom" >/dev/null 2>&1; then
    fail "resume exits nonzero on an early (pre-session) launch failure"
else
    pass "resume exits nonzero on an early (pre-session) launch failure"
fi
assert_equals "$(meta_field "$uuid" turns)" "$turns_before" "turns not bumped when the turn never started"

echo "== codex-resume: waits on a dying wrapper's rc barrier before proceeding =="
# Simulate the liveness-guard race: status=working, pid already dead (the
# codex process exited), but the previous wrapper's rc file (its completion
# barrier per _codex_launch) hasn't appeared yet. Resume must wait a bounded
# window for it rather than racing ahead immediately.
# A fixed, certainly-nonexistent pid (well past any real process id) — the
# test only needs `kill -0` to fail, and a real spawn-then-kill sequence
# raced with bash job control under piped output in earlier iterations.
DEADPID=999999
prev_log="$TEST_ROOT/dead-wrapper.events.jsonl"; : > "$prev_log"
python3 - "$DAEMON_HOME/$uuid.json" "$prev_log" "$DEADPID" <<'PY'
import json, sys
path, ev, pid = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(path))
d["status"] = "working"; d["pid"] = pid; d["event_log"] = ev
json.dump(d, open(path, "w"))
PY
start_ts=$(date +%s)
# Bound picked well above the ~1-2s of incidental sleep the OTHER (pre-existing,
# unrelated) polling loops in codex-resume.sh can add on their own — only the
# rc-barrier wait itself should be able to push elapsed past that margin.
out="$(CODEX_RC_BARRIER_WAIT=6 "$SCRIPTS_DIR/codex-resume.sh" "$uuid" "after dead wrapper")"
elapsed=$(( $(date +%s) - start_ts ))
assert_contains "$out" "stub reply: after dead wrapper" "resume proceeds once the rc-barrier wait times out"
if [ "$elapsed" -ge 5 ]; then pass "resume waited the full rc-barrier bound (${elapsed}s)"; else
    fail "resume waited the full rc-barrier bound (${elapsed}s)"; fi

echo "== engine guards =="
if "$SCRIPTS_DIR/daemon-resume.sh" "$uuid" "hi" >/dev/null 2>&1; then
    fail "daemon-resume refuses a codex daemon"
else
    pass "daemon-resume refuses a codex daemon"
fi
if "$SCRIPTS_DIR/codex-resume.sh" "not-a-daemon" "hi" >/dev/null 2>&1; then
    fail "codex-resume errors on unknown id"
else
    pass "codex-resume errors on unknown id"
fi

echo "== codex-resume: refuses a live working turn =="
STUB_SLEEP=4 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-e "long turn" "$WORK" >/dev/null
uuid_e="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
if "$SCRIPTS_DIR/codex-resume.sh" "$uuid_e" "interrupt" >/dev/null 2>&1; then
    fail "resume refuses while a turn is live"
else
    pass "resume refuses while a turn is live"
fi
for _ in $(seq 1 15); do [ "$(meta_field "$uuid_e" status)" != "working" ] && break; sleep 1; done

echo ""
if [ "$FAILURES" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$FAILURES FAILURE(S)"; exit 1; fi
