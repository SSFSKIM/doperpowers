#!/usr/bin/env bash
#
# Hermetic tests for implement-dispatch.sh — the mechanical implement/spike
# dispatcher (the dispatch ritual, automated).
#
# Side channels: `gh` is the shared issue-tracker mock (state in
# $MOCK_GH_STATE); the orchestrating-daemons scripts are stubs that log and
# write registry meta like the real --no-wait spawn; the BOARD scripts
# (_board.py eligibility, board-bind) are REAL and run against the mock gh.
# git is real: a bare origin + clone carrying .doperpowers/repo-facts.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DISPATCH="$REPO_ROOT/skills/implementing-tickets/scripts/implement-dispatch.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_file_contains() {
    if grep -Fq -- "$2" "$1" 2>/dev/null; then pass "$3"; else
        fail "$3"; echo "    expected file $1 to contain: $2"; fi
}
assert_file_not_contains() {
    if grep -Fq -- "$2" "$1" 2>/dev/null; then
        fail "$3"; echo "    expected file $1 NOT to contain: $2"; else pass "$3"; fi
}

# ---- environment --------------------------------------------------------------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export MOCK_GH_STATE="$TEST_ROOT/gh-state.json"
export MOCK_GH_LOG="$TEST_ROOT/gh-log.jsonl"
export PATH="$REPO_ROOT/tests/issue-tracker/mock-gh:$PATH"
export SPAWN_LOG="$TEST_ROOT/spawn.log"; : > "$SPAWN_LOG"
export PROMPT_DIR="$TEST_ROOT/prompts"; mkdir -p "$PROMPT_DIR"
export STUB_COUNT="$TEST_ROOT/count"
export BOARD_REPO="test/repo"
export BOARD_SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"

# real git: bare origin + clone whose main carries a repo-facts manifest
ORIGIN="$TEST_ROOT/origin.git"
git init -q --bare "$ORIGIN"
CLONE="$TEST_ROOT/clone"
git clone -q "$ORIGIN" "$CLONE" 2>/dev/null
git -C "$CLONE" checkout -q -b main
mkdir -p "$CLONE/.doperpowers"
printf '## Bootstrap\n\nARM64-FACT: run npm ci fresh.\n' > "$CLONE/.doperpowers/repo-facts.md"
git -C "$CLONE" add .doperpowers/repo-facts.md
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m init
git -C "$CLONE" push -q -u origin main
git -C "$CLONE" remote set-head origin main
export LOCAL_REPO="$CLONE"

# stub daemon scripts: log + register meta like the real --no-wait spawn
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
export DAEMON_SCRIPTS="$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
flag=""; [ "${1:-}" = "--no-wait" ] && { flag="--no-wait"; shift; }
name="$1"; task="$2"
echo "spawn:$flag $name wt=${4:-} model=${5:-}" >> "$SPAWN_LOG"
echo "spawn-env:settings=${DAEMON_CLAUDE_SETTINGS:-};effort=${DAEMON_CLAUDE_EFFORT:-}" >> "$SPAWN_LOG"
if [ -n "${FAIL_SPAWN_FOR:-}" ] && [ "$name" = "$FAIL_SPAWN_FOR" ]; then
  echo "stub daemon-spawn: simulated failure for $name" >&2
  exit 1
fi
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'aaaa%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"],
           "status": "working", "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$*" >> "$SPAWN_LOG"
STUB
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh"

# ---- board seed ---------------------------------------------------------------
# 1 ELIGIBLE P1 impl · 2 blocked-by-1 · 3 ELIGIBLE P0 spike · 4 in-progress ·
# 5 ELIGIBLE P2 engine:claude
python3 - <<'PY'
import json, os
def issue(num, title, labels, body="body of #%s", blocked=None):
    return {"number": num, "id": "ID_%d" % num, "title": title,
            "body": body % num if "%s" in body else body,
            "state": "OPEN", "stateReason": None, "labels": labels,
            "assignees": [], "parent": None, "blockedBy": blocked or [],
            "closesPRs": [], "xrefPRs": [], "comments": [],
            "createdAt": "2026-07-18T00:00:00Z", "updatedAt": "2026-07-18T00:00:00Z",
            "url": "https://github.com/test/repo/issues/%d" % num}
s = {"next": 6, "labels": [], "issues": {
    "1": issue(1, "Fix the report builder pipeline",
               ["status:ready-for-agent", "priority:P1", "bug"],
               body="Repro: the report build fails on BUILD-MARKER."),
    "2": issue(2, "Downstream cleanup", ["status:ready-for-agent"], blocked=[1]),
    "3": issue(3, "Probe the cache layer", ["status:ready-for-agent", "priority:P0", "spike"]),
    "4": issue(4, "Mid-flight work", ["status:in-progress"]),
    "5": issue(5, "Tune the copy", ["status:ready-for-agent", "priority:P2", "engine:claude"]),
}}
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY

run() { "$DISPATCH" "$@" 2>&1; }

echo "implement-dispatch: triggered mode"

out="$(run 1)"
assert_contains "$out" "dispatched #1" "triggered dispatch reports the ticket"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 1-fix-the-report-builder-pipeline" \
  "spawn is --no-wait with the <n>-<slug> name"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=$HOME/.claude/clodex-settings.json;effort=xhigh" \
  "default engine codex rides the gateway env"
assert_contains "$(grep '^spawn:' "$SPAWN_LOG" | head -1)" "model=fable" \
  "codex route pins the gateway model alias"
PROMPT="$PROMPT_DIR/1-fix-the-report-builder-pipeline.prompt"
assert_file_contains "$PROMPT" "IMPLEMENT worker for ticket #1" "prompt carries the IMPLEMENT role"
assert_file_contains "$PROMPT" "BUILD-MARKER" "prompt embeds the issue body"
assert_file_contains "$PROMPT" "ARM64-FACT" "prompt embeds repo-facts from origin default branch"
assert_file_contains "$PROMPT" "EXECUTION (gate passed)" "prompt embeds the execution block"
assert_file_contains "$PROMPT" "implementing-tickets/SKILL.md" "implement lane opens the SKILL protocol"
assert_file_not_contains "$PROMPT" "{{" "no unrendered placeholder survives"
meta_ticket="$(python3 -c "
import glob, json
print(next((m.get('ticket','') for p in glob.glob('$DAEMON_HOME/*.json')
            for m in [json.load(open(p))] if m.get('name','').startswith('1-')), ''))")"
assert_contains "$meta_ticket" "1" "board-bind bound the worker to ticket 1"

out="$(run 2)"
assert_contains "$out" "skip #2" "blocked ticket is refused"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 2-" "blocked ticket spawns nothing"

out="$(run 4)"
assert_contains "$out" "skip #4" "non-ready ticket is refused"

out="$(run 1)"
assert_contains "$out" "skip #1: bound worker" "working bound meta dedupes re-dispatch"

echo "implement-dispatch: spike lane + engine label"

out="$(run 3)"
PROMPT3="$PROMPT_DIR/3-probe-the-cache-layer.prompt"
assert_file_contains "$PROMPT3" "SPIKE worker for ticket #3" "spike role"
assert_file_contains "$PROMPT3" "spike-worker-protocol.md" "spike lane opens the spike protocol"
assert_file_contains "$PROMPT3" "(none — spike lane)" "spike gets the literal no-execution-block binding"

out="$(run 5)"
assert_contains "$(grep 'spawn:--no-wait 5-' "$SPAWN_LOG")" "5-tune-the-copy" "claude-engine ticket dispatches"
last_env="$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)"
assert_contains "$last_env" "settings=;effort=" "engine:claude label suppresses the gateway env"

echo "implement-dispatch: idle owner does not block"

python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m = json.load(open(p))
    if m.get("name", "").startswith("1-"):
        m["status"] = "idle"
        json.dump(m, open(p, "w"))
PY
out="$(run 1)"
assert_contains "$out" "dispatched #1" "idle bound session does not block a fresh dispatch"

echo "implement-dispatch: sweep mode order + cap"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(run --sweep)"
order="$(grep -o 'spawn:--no-wait [0-9]*-' "$SPAWN_LOG" | tr -d ' ' | paste -sd, -)"
assert_contains "$order" "spawn:--no-wait3-,spawn:--no-wait1-,spawn:--no-wait5-" \
  "sweep dispatches in priority order (P0, P1, P2)"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 2-" "sweep skips blocked tickets"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 4-" "sweep skips non-ready tickets"

out="$(run --sweep)"
assert_contains "$out" "skip #3: bound worker" "consecutive sweep re-dispatches nothing"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(IMPLEMENT_MAX_CONCURRENT=2 run --sweep)"
assert_contains "$out" "cap reached" "sweep names the cap when it stops"
n_spawns="$(grep -c '^spawn:' "$SPAWN_LOG")"
assert_contains "$n_spawns" "2" "cap 2 permits exactly two dispatches"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
python3 - <<'PY'
import json, os
json.dump({"uuid": "eeee0001-0000-4000-8000-000000000000", "current": "x",
           "name": "4-mid-flight-work", "ticket": "4", "status": "working",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "eeee0001-0000-4000-8000-000000000000.json"), "w"))
PY
out="$(IMPLEMENT_MAX_CONCURRENT=2 run --sweep)"
n_spawns="$(grep -c '^spawn:' "$SPAWN_LOG")"
assert_contains "$n_spawns" "1" "a pre-existing working implement meta occupies a slot"

python3 - <<'PY'
import json, os
json.dump({"uuid": "ffff0001-0000-4000-8000-000000000000", "current": "y",
           "name": "review-pr-9", "ticket": "9", "status": "working",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "ffff0001-0000-4000-8000-000000000000.json"), "w"))
PY
rm -f "$DAEMON_HOME"/aaaa*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(IMPLEMENT_MAX_CONCURRENT=2 run --sweep)"
n_spawns="$(grep -c '^spawn:' "$SPAWN_LOG")"
assert_contains "$n_spawns" "1" "review/land workers never count against the implement cap"

echo "implement-dispatch: failure isolation + strict render"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(FAIL_SPAWN_FOR="3-probe-the-cache-layer" run --sweep)" || true
assert_contains "$out" "#3: " "spawn failure is reported per ticket"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 1-" "sweep continues past a failed spawn"

BAD_TEMPLATE="$TEST_ROOT/bad-bootstrap.md"
printf 'hello {{NOT_A_REAL_BINDING}}\n' > "$BAD_TEMPLATE"
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(IMPLEMENT_BOOTSTRAP_TEMPLATE="$BAD_TEMPLATE" run 1)" || true
assert_contains "$out" "unrendered placeholder" "strict render aborts on a surviving placeholder"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "strict-render failure spawns nothing"

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
