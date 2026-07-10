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
out="$(CODEX_RC_BARRIER_WAIT=6 "$SCRIPTS_DIR/codex-resume.sh" "$uuid" "after dead wrapper" 2>&1)"
elapsed=$(( $(date +%s) - start_ts ))
assert_contains "$out" "stub reply: after dead wrapper" "resume proceeds once the rc-barrier wait times out"
if [ "$elapsed" -ge 5 ]; then pass "resume waited the full rc-barrier bound (${elapsed}s)"; else
    fail "resume waited the full rc-barrier bound (${elapsed}s)"; fi
assert_contains "$out" "completion barrier never appeared" "barrier timeout is surfaced on stderr"

echo "== codex-resume: proceeds early once the prior rc barrier lands =="
# Same stale-meta shape, but this time the prior wrapper is merely SLOW: its
# rc file lands 2s in. Resume must stop waiting as soon as it appears (well
# under the 15s bound) and must NOT emit the barrier-timeout warning.
prev_log2="$TEST_ROOT/late-wrapper.events.jsonl"; : > "$prev_log2"
prev_rc2="$TEST_ROOT/late-wrapper.rc"; rm -f "$prev_rc2"
python3 - "$DAEMON_HOME/$uuid.json" "$prev_log2" "$DEADPID" <<'PY'
import json, sys
path, ev, pid = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(path))
d["status"] = "working"; d["pid"] = pid; d["event_log"] = ev
json.dump(d, open(path, "w"))
PY
( sleep 2; echo 0 > "$prev_rc2" ) &
start_ts=$(date +%s)
out="$(CODEX_RC_BARRIER_WAIT=15 "$SCRIPTS_DIR/codex-resume.sh" "$uuid" "after late barrier" 2>&1)"
elapsed=$(( $(date +%s) - start_ts ))
assert_contains "$out" "stub reply: after late barrier" "resume proceeds after the rc barrier lands"
assert_not_contains "$out" "completion barrier never appeared" "no timeout warning when the barrier lands in time"
if [ "$elapsed" -le 8 ]; then pass "resume stopped waiting once the barrier landed (${elapsed}s, bound 15)"; else
    fail "resume stopped waiting once the barrier landed (${elapsed}s, bound 15)"; fi

echo "== codex-resume: meta without event_log skips the barrier wait =="
# Metas predating the event_log field (or hand-registered ones) have nothing
# to derive an rc path from — the guard must proceed immediately, not stall.
python3 - "$DAEMON_HOME/$uuid.json" "$DEADPID" <<'PY'
import json, sys
path, pid = sys.argv[1], sys.argv[2]
d = json.load(open(path))
d["status"] = "working"; d["pid"] = pid; d.pop("event_log", None)
json.dump(d, open(path, "w"))
PY
start_ts=$(date +%s)
out="$(CODEX_RC_BARRIER_WAIT=15 "$SCRIPTS_DIR/codex-resume.sh" "$uuid" "no prior log")"
elapsed=$(( $(date +%s) - start_ts ))
assert_contains "$out" "stub reply: no prior log" "resume proceeds with no event_log in the meta"
if [ "$elapsed" -le 5 ]; then pass "no barrier wait without an event_log (${elapsed}s)"; else
    fail "no barrier wait without an event_log (${elapsed}s)"; fi

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
# 6s (not 4) keeps the turn provably live through --no-wait registration
# (~2s of uuid polling) plus the resume attempt even under load — observed
# flaking once at 4s when the whole suite ran under heavier I/O.
STUB_SLEEP=6 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-e "long turn" "$WORK" >/dev/null
uuid_e="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
if "$SCRIPTS_DIR/codex-resume.sh" "$uuid_e" "interrupt" >/dev/null 2>&1; then
    fail "resume refuses while a turn is live"
else
    pass "resume refuses while a turn is live"
fi
for _ in $(seq 1 15); do [ "$(meta_field "$uuid_e" status)" != "working" ] && break; sleep 1; done

echo "== read-side engine awareness =="
# $uuid's most-recently recorded reply by this point in the suite is whatever
# the last preceding resume left behind ("no prior log", from the event_log-less
# barrier test) — not "follow up". Resume once more with a known message
# immediately before asserting, so the assertion stays honest (codex's OWN
# recorded reply, not a stale fixture) rather than being weakened to match
# whatever text happened to be left over from an earlier test.
"$SCRIPTS_DIR/codex-resume.sh" "$uuid" "follow up" >/dev/null
listing="$("$SCRIPTS_DIR/daemon-list.sh")"
assert_contains "$listing" "ENG" "daemon-list has an engine column"
assert_contains "$listing" "codex" "daemon-list shows codex engine"
reply_out="$("$SCRIPTS_DIR/daemon-reply.sh" "$uuid")"
assert_contains "$reply_out" "stub reply: follow up" "daemon-reply prints the codex reply"

echo "== daemon-retire kills a live codex turn =="
STUB_SLEEP=30 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-f "hang" "$WORK" >/dev/null
uuid_f="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
pid_f="$(meta_field "$uuid_f" pid)"
retire_out="$("$SCRIPTS_DIR/daemon-retire.sh" "$uuid_f")"
assert_contains "$retire_out" "codex resume $uuid_f" "retire prints codex resume hint"
sleep 1
if kill -0 "$pid_f" 2>/dev/null; then fail "retire stops the live codex turn"; else pass "retire stops the live codex turn"; fi
assert_equals "$(meta_field "$uuid_f" status)" "retired" "retire records status"

echo "== _meta_set serializes concurrent RMW — no lost fields (FU-1) =="
# The lost-update race: the detached _codex_launch wrapper and the foreground
# spawn each read-modify-write the same meta; without serialization the later
# writer's stale snapshot clobbers the other's fields (e.g. `engine` is lost and
# the daemon renders as claude). Hammer one meta with many concurrent writers —
# 60 each adding a distinct key, plus one laying down a registration block — and
# assert every field survives. Without the flock this loses updates; with it,
# never.
mb="metabench-0000-4000-8000-000000000000"
printf '{}' > "$DAEMON_HOME/$mb.json"
for k in $(seq 1 60); do
  ( source "$SCRIPTS_DIR/_lib.sh"; _meta_set "$mb" "k$k" "v$k" ) &
done
( source "$SCRIPTS_DIR/_lib.sh"; _meta_set "$mb" engine codex pid 4242 status working ) &
wait 2>/dev/null || true
survived="$(DAEMON_HOME="$DAEMON_HOME" MB="$mb" python3 - <<'PY'
import json, os
d = json.load(open(os.path.join(os.environ["DAEMON_HOME"], os.environ["MB"] + ".json")))
lost = [k for k in range(1, 61) if d.get("k%d" % k) != "v%d" % k]
# whole registration block must survive intact, not just `engine`
reg = "%s/%s/%s" % (d.get("engine", "MISSING"), d.get("pid", "MISSING"), d.get("status", "MISSING"))
print("%d %s" % (len(lost), reg))
PY
)"
assert_equals "${survived%% *}" "0" "no field lost across 61 concurrent _meta_set writers"
assert_equals "${survived##* }" "codex/4242/working" "registration block (engine/pid/status) survives the race"

echo "== _codex_gc_runs sweeps old orphans, keeps referenced + fresh (FU-2) =="
gcruns="$DAEMON_HOME/runs"; mkdir -p "$gcruns"
mkset() { for e in task.txt events.jsonl reply.txt err pid rc; do : > "$gcruns/codex-run.$1.$e"; done; }
mkset REF; mkset OLDORPH; mkset FRESH
# a live meta references REF's event log → must survive
printf '{"uuid":"gcref","engine":"codex","status":"working","event_log":"%s/codex-run.REF.events.jsonl"}' "$gcruns" > "$DAEMON_HOME/gcref.json"
# backdate OLDORPH beyond the GC age; FRESH stays new (in-flight-spawn safety)
python3 - "$gcruns" <<'PY'
import glob, os, sys, time
old = time.time() - 99999
for f in glob.glob(os.path.join(sys.argv[1], "codex-run.OLDORPH.*")):
    os.utime(f, (old, old))
PY
( source "$SCRIPTS_DIR/_lib.sh"; source "$SCRIPTS_DIR/_codex_lib.sh"; CODEX_RUNS_GC_AGE=600 _codex_gc_runs )
assert_file_exists "$gcruns/codex-run.REF.events.jsonl" "GC keeps a run referenced by a live meta"
assert_file_exists "$gcruns/codex-run.FRESH.events.jsonl" "GC keeps a fresh orphan (in-flight spawn safety)"
if [ ! -f "$gcruns/codex-run.OLDORPH.events.jsonl" ]; then pass "GC sweeps an old orphaned run"; else
    fail "GC sweeps an old orphaned run"; fi

echo "== daemon-retire purge removes a codex daemon's run files (FU-2) =="
STUB_SLEEP=0 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-gc "quick" "$WORK" >/dev/null
uuid_gc="$(basename "$(ls -t "$DAEMON_HOME"/cdec*.json | head -1)" .json)"
el_gc="$(meta_field "$uuid_gc" event_log)"
assert_file_exists "$el_gc" "spawn left a run event log"
"$SCRIPTS_DIR/daemon-retire.sh" "$uuid_gc" purge >/dev/null
if [ ! -f "$el_gc" ]; then pass "purge removes the codex daemon's run files"; else
    fail "purge removes the codex daemon's run files"; fi

echo "== spawn vendors doperpowers skills into the workspace (FU-4) =="
# Implement path: git repo + worktree arg → vendored into the worktree.
VWORK="$TEST_ROOT/vendorrepo"; mkdir -p "$VWORK"
git -C "$VWORK" init -q
git -C "$VWORK" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
STUB_SLEEP=0 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-vendor "hello" "$VWORK" vwt >/dev/null
VWT="$VWORK/.claude/worktrees/vwt"
if [ -L "$VWT/.agents/skills" ]; then pass "worktree gets an .agents/skills symlink"; else
    fail "worktree gets an .agents/skills symlink"; fi
assert_equals "$(readlink "$VWT/.agents/skills")" "$REPO_ROOT/skills" \
    ".agents/skills points at the doperpowers skills root"
assert_equals "$(git -C "$VWT" status --porcelain)" "" \
    "vendored skills are invisible to git status (shared info/exclude)"
# Review path shape: an existing git dir passed as cwd, no worktree arg.
VDIRECT="$TEST_ROOT/vendordirect"; mkdir -p "$VDIRECT"
git -C "$VDIRECT" init -q
git -C "$VDIRECT" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
STUB_SLEEP=0 "$SCRIPTS_DIR/codex-spawn.sh" --no-wait job-vendor2 "hello" "$VDIRECT" >/dev/null
if [ -L "$VDIRECT/.agents/skills" ]; then pass "plain git cwd (review path) gets the symlink"; else
    fail "plain git cwd (review path) gets the symlink"; fi
assert_equals "$(git -C "$VDIRECT" status --porcelain)" "" \
    "review-path vendoring invisible to git status"
# Idempotent + respects a pre-existing .agents/skills (does not clobber).
mkdir -p "$TEST_ROOT/vendorown/.agents/skills"
git -C "$TEST_ROOT/vendorown" init -q 2>/dev/null
( source "$SCRIPTS_DIR/_lib.sh"; source "$SCRIPTS_DIR/_codex_lib.sh"
  _codex_vendor_skills "$TEST_ROOT/vendorown" )
if [ -d "$TEST_ROOT/vendorown/.agents/skills" ] && [ ! -L "$TEST_ROOT/vendorown/.agents/skills" ]; then
    pass "a repo's own .agents/skills is left untouched"; else
    fail "a repo's own .agents/skills is left untouched"; fi
# Non-git cwd → silent no-op (implicitly also covered by every $WORK spawn above).
( source "$SCRIPTS_DIR/_lib.sh"; source "$SCRIPTS_DIR/_codex_lib.sh"
  _codex_vendor_skills "$WORK" )
if [ ! -e "$WORK/.agents" ]; then pass "non-git cwd: vendoring is a no-op"; else
    fail "non-git cwd: vendoring is a no-op"; fi

echo "== codex-resume from a linked worktree: writable_roots, never --add-dir (FU-5) =="
# The job-vendor daemon above lives in the VWT linked worktree — resume it.
uuid_v="$(DAEMON_HOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("name") == "job-vendor":
        print(m["uuid"]); break
PY
)"
if [ -n "$uuid_v" ]; then pass "found the worktree daemon's meta"; else fail "found the worktree daemon's meta"; fi
STUB_SLEEP=0 "$SCRIPTS_DIR/codex-resume.sh" "$uuid_v" "resume in worktree" >/dev/null
wtresume="$(grep "exec resume $uuid_v" "$STUB_STATE/calls.log" | tail -1)"
assert_not_contains "$wtresume" "--add-dir" "worktree resume omits --add-dir (real CLI rejects it, rc=2)"
mainroot="$(cd "$VWORK" && git rev-parse --show-toplevel)"
assert_contains "$wtresume" "sandbox_workspace_write.writable_roots=[\"$mainroot\"]" \
    "worktree resume passes -c writable_roots at the main repo root instead"

echo ""
if [ "$FAILURES" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$FAILURES FAILURE(S)"; exit 1; fi
