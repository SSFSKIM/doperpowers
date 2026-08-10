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
DISPATCH="$REPO_ROOT/skills/implementing/scripts/implement-dispatch.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
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
# Ambient gateway route, as a gateway-routed daemon (or an operator shell that
# sourced one) exports it. Present for the WHOLE suite on purpose: it makes every
# "no gateway env" assertion below a regression test — the claude route must hand
# daemon-spawn.sh nothing, since daemon-spawn.sh persists what it inherits into
# the registry meta and every later resume would silently ride the gateway.
export DAEMON_CLAUDE_SETTINGS="$TEST_ROOT/ambient-gateway.json"
export DAEMON_CLAUDE_EFFORT="high"

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
# also into the gh log, so board writes and the release of the worker share
# ONE ordered stream (the parent-pin stamp must precede this line)
[ -z "${MOCK_GH_LOG:-}" ] || printf '["spawn", "%s"]\n' "$name" >> "$MOCK_GH_LOG"
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
# 5 ELIGIBLE P2 engine:claude · 7 ELIGIBLE unprioritized engine:codex
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
s = {"next": 10, "labels": [], "issues": {
    "1": issue(1, "Fix the report builder pipeline",
               ["status:ready-for-implementer", "priority:P1", "bug"],
               body="Repro: the report build fails on BUILD-MARKER."),
    "2": issue(2, "Downstream cleanup", ["status:ready-for-implementer"], blocked=[1]),
    "3": issue(3, "Probe the cache layer", ["status:ready-for-implementer", "priority:P0", "spike"]),
    "4": issue(4, "Mid-flight work", ["status:in-progress"]),
    "5": issue(5, "Tune the copy", ["status:ready-for-implementer", "priority:P2", "engine:claude"]),
    "6": issue(6, "Delivered, awaiting review", ["status:in-review"]),
    "7": issue(7, "Port the legacy adapter", ["status:ready-for-implementer", "engine:codex"]),
    "8": issue(8, "Design the ledger split", ["status:ready-for-architect", "priority:P0"]),
    "9": issue(9, "Design with codex label", ["status:ready-for-architect", "priority:P1", "engine:codex"]),
}}
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY

run() { "$DISPATCH" "$@" 2>&1; }

echo "implement-dispatch: triggered mode"

out="$(run 1)"
assert_contains "$out" "dispatched #1" "triggered dispatch reports the ticket"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 1-fix-the-report-builder-pipeline" \
  "spawn is --no-wait with the <n>-<slug> name"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | head -1)" "settings=;effort=" \
  "default engine claude passes no gateway env"
# bracketed so the fixed-string match is exact — the model arg is last on the
# spawn line, so the closing bracket pins the whole value and an unpinned
# (empty) or differently-pinned arg cannot satisfy it by prefix.
first_spawn="$(grep '^spawn:' "$SPAWN_LOG" | head -1)"
assert_contains "[${first_spawn##* }]" "[model=opus]" \
  "claude route pins the worker tier (IMPLEMENT_MODEL overrides; never inherited)"
PROMPT="$PROMPT_DIR/1-fix-the-report-builder-pipeline.prompt"
assert_file_contains "$PROMPT" "IMPLEMENT worker for ticket #1" "prompt carries the IMPLEMENT role"
assert_file_not_contains "$PROMPT" "BUILD-MARKER" "prompt carries no inlined issue body (the worker reads its ticket via gh)"
assert_file_not_contains "$PROMPT" "ARM64-FACT" "prompt carries no inlined repo-facts (the worker reads the manifest from its worktree)"
assert_file_not_contains "$PROMPT" "EXECUTION (gate passed)" "prompt carries no execution block (the doctrine lives in the protocol)"
assert_file_contains "$PROMPT" "implementing/SKILL.md" "implement lane opens the SKILL protocol"
assert_file_not_contains "$PROMPT" "{{" "no unrendered placeholder survives"
meta_ticket="$(python3 -c "
import glob, json
print(next((m.get('ticket','') for p in glob.glob('$DAEMON_HOME/*.json')
            for m in [json.load(open(p))] if m.get('name','').startswith('1-')), ''))")"
assert_contains "$meta_ticket" "1" "board-bind bound the worker to ticket 1"
role_meta_1="$(python3 -c "
import glob, json
print(next((m.get('role','') for p in glob.glob('$DAEMON_HOME/*.json')
            for m in [json.load(open(p))] if m.get('name','').startswith('1-')), ''))")"
assert_contains "$role_meta_1" "IMPLEMENT" "dispatch persists the IMPLEMENT role into the registry meta"

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
assert_file_contains "$PROMPT3" "(none — spike lane)" "spike gets the literal no-decompose binding"
role_meta_3="$(python3 -c "
import glob, json
print(next((m.get('role','') for p in glob.glob('$DAEMON_HOME/*.json')
            for m in [json.load(open(p))] if m.get('name','').startswith('3-')), ''))")"
assert_contains "$role_meta_3" "SPIKE" "dispatch persists the SPIKE role into the registry meta"

out="$(run 5)"
assert_contains "$(grep 'spawn:--no-wait 5-' "$SPAWN_LOG")" "5-tune-the-copy" "claude-engine ticket dispatches"
last_env="$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)"
assert_contains "$last_env" "settings=;effort=" "engine:claude label (redundant since the default flipped) still suppresses the gateway env"

out="$(run 7)"
assert_contains "$(grep 'spawn:--no-wait 7-' "$SPAWN_LOG")" "7-port-the-legacy-adapter" "codex-engine ticket dispatches"
last_env="$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)"
assert_contains "$last_env" "settings=$HOME/.claude/clodex-settings.json;effort=xhigh" \
  "engine:codex label opts back into the gateway route"
assert_contains "$(grep '^spawn:' "$SPAWN_LOG" | tail -1)" "model=fable" \
  "label-selected codex route pins the gateway model alias"

echo "implement-dispatch: WORKER_ENGINE env override"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(WORKER_ENGINE=codex run 1)"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)" "settings=$HOME/.claude/clodex-settings.json;effort=xhigh" \
  "WORKER_ENGINE=codex overrides the claude default on a label-less ticket"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(WORKER_ENGINE=codex run 5)"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)" "settings=;effort=" \
  "engine:claude label still wins over WORKER_ENGINE=codex"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(run 1)"

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
assert_contains "$order" "spawn:--no-wait3-,spawn:--no-wait8-,spawn:--no-wait1-,spawn:--no-wait5-" \
  "sweep dispatches in priority order (P0, P1, P2) across both lanes (#8 is the P0 architect ticket, tid-tiebreaks after #3)"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 2-" "sweep skips blocked tickets"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 4-" "sweep skips non-ready tickets"
n_gateway="$(grep -c "settings=$HOME/.claude/clodex-settings.json" "$SPAWN_LOG" || true)"
assert_contains "$n_gateway" "1" \
  "sweep sends only the engine:codex ticket through the gateway — every other worker rides the claude default"

out="$(run --sweep)"
assert_contains "$out" "skip #3: bound worker" "consecutive sweep re-dispatches nothing"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(IMPLEMENT_MAX_CONCURRENT=2 run --sweep)"
assert_contains "$out" "cap reached" "sweep names the cap when it stops"
n_spawns="$(grep -c '^spawn:' "$SPAWN_LOG")"
assert_contains "$n_spawns" "3" "implement cap 2 permits exactly two implement dispatches (plus #8's independent architect-lane slot)"

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
assert_contains "$n_spawns" "2" "a pre-existing working implement meta occupies its lane's slot (the architect lane still dispatches independently)"

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
assert_contains "$n_spawns" "2" "review/land workers never count against the implement cap (the architect lane's own dispatch is unaffected)"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
python3 - <<'PY'
import json, os
json.dump({"uuid": "dddd0006-0000-4000-8000-000000000000", "current": "z",
           "name": "6-delivered", "ticket": "6", "status": "working",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "dddd0006-0000-4000-8000-000000000000.json"), "w"))
PY
out="$(IMPLEMENT_MAX_CONCURRENT=2 run --sweep)"
n_spawns="$(grep -c '^spawn:' "$SPAWN_LOG")"
assert_contains "$n_spawns" "3" "a stale working meta on an in-review ticket does not eat a slot (2 implement + #8's architect slot)"

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

echo "implement-dispatch: no origin/HEAD dependency"

git -C "$CLONE" symbolic-ref -d refs/remotes/origin/HEAD
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(run 1)"
assert_contains "$out" "dispatched #1" "a clone without origin/HEAD still dispatches (nothing reads the default branch)"

echo "implement-dispatch: architect lane"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(run 8)"
assert_contains "$out" "dispatched #8" "architect ticket dispatches"
assert_contains "$out" "role=ARCHITECT" "architect role selected off the state"
PROMPT8="$PROMPT_DIR/8-design-the-ledger-split.prompt"
assert_file_contains "$PROMPT8" "ARCHITECT worker for ticket #8" "prompt carries the ARCHITECT role"
assert_file_contains "$PROMPT8" "architecting/SKILL.md" "architect lane opens the architecting protocol"
assert_contains "$(grep '^spawn:' "$SPAWN_LOG" | tail -1)" "model=fable" "architect route pins the frontier model"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)" "settings=;effort=" "architect route never rides the gateway"
role_meta_8="$(python3 -c "
import glob, json
print(next((m.get('role','') for p in glob.glob('$DAEMON_HOME/*.json')
            for m in [json.load(open(p))] if m.get('name','').startswith('8-')), ''))")"
assert_contains "$role_meta_8" "ARCHITECT" "dispatch persists the ARCHITECT role into the registry meta (Finding D: board-answer's needs-human fallback reads it back)"

out="$(run 9)"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)" "settings=;effort=" "engine:codex label is IGNORED on the architect lane (X4 exemption)"
assert_contains "$(grep '^spawn:' "$SPAWN_LOG" | tail -1)" "model=fable" "labelled architect ticket still pins fable"

echo "implement-dispatch: per-lane caps"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(ARCHITECT_MAX_CONCURRENT=1 run --sweep)"
n_arch="$(grep -c 'role=ARCHITECT' <<<"$out" || true)"
assert_contains "$n_arch" "1" "architect cap 1 admits exactly one design dispatch"
assert_contains "$out" "architect cap reached" "sweep names the architect cap"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 3-" "implementer lane still dispatches under its own cap (the P0 spike rides it)"

# an in-design bound meta occupies an ARCHITECT slot (binding release = slot accounting)
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
python3 - <<'PY'
import json, os
json.dump({"uuid": "cccc0008-0000-4000-8000-000000000000", "current": "w",
           "name": "8-design-the-ledger-split", "ticket": "8", "status": "working",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "cccc0008-0000-4000-8000-000000000000.json"), "w"))
PY
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["8"]["labels"] = ["status:in-design", "priority:P0"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out="$(ARCHITECT_MAX_CONCURRENT=1 run 9)"
assert_contains "$out" "architect cap reached" "an in-design bound worker occupies the architect slot"

# ...but a REVIEWER never occupies a lane slot, whatever state its ticket is
# in. A live scale reviewer that has moved its epic to ready-for-architect is
# still posting its trail, and while it does its meta sat on the single
# architect slot and blocked every unrelated Architect dispatch.
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["8"]["labels"] = ["status:ready-for-architect", "priority:P0"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
u = "eeee0008-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-epic-8", "ticket": "8",
           "status": "working", "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
os.remove(os.path.join(os.environ["DAEMON_HOME"],
                       "cccc0008-0000-4000-8000-000000000000.json"))
PY
: > "$SPAWN_LOG"
out="$(ARCHITECT_MAX_CONCURRENT=1 run 9)"
assert_not_contains "$out" "architect cap reached" "a working scale reviewer does not occupy the architect slot"
assert_contains "$out" "dispatched #9" "so an unrelated architect-lane ticket still dispatches"
# the per-ticket binding is untouched: the epic the reviewer owns stays blocked
out="$(run 8)"
assert_contains "$out" "skip #8: bound worker" "the reviewer still blocks dispatch of ITS OWN ticket"

# LANE CROSSING RELEASES THE SLOT (spec transition 8). State alone charged a
# worker to whichever lane its ticket had REACHED, so an Implementer that
# handed its ticket to the architect queue kept writing its closing trail
# while sitting on the single architect slot — every unrelated Architect
# blocked until finalize or the stall reaper, up to 45 minutes. The charge
# now needs BOTH the persisted role and the current state.
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["8"]["labels"] = ["status:ready-for-architect", "priority:P0"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
d = os.environ["DAEMON_HOME"]
for f in os.listdir(d):                     # #9 got dispatched just above
    if f.endswith(".json"):
        try:
            if str(json.load(open(os.path.join(d, f))).get("ticket")) == "9":
                os.remove(os.path.join(d, f))
        except Exception:
            pass
u = "ffff0008-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "8-handed-off", "ticket": "8",
           "status": "working", "role": "IMPLEMENT",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
: > "$SPAWN_LOG"
out="$(ARCHITECT_MAX_CONCURRENT=1 run 9)"
assert_not_contains "$out" "architect cap reached" "a live IMPLEMENT worker whose ticket crossed into the architect queue charges no architect slot"
assert_contains "$out" "dispatched #9" "so an unrelated architect-lane ticket still dispatches"
# ...and the same meta with the matching role DOES charge: this is a
# role/state agreement test, not a licence to stop counting.
python3 - <<'PY'
import json, os
d = os.environ["DAEMON_HOME"]
for f in os.listdir(d):                     # #9 got dispatched again
    if f.endswith(".json"):
        try:
            if str(json.load(open(os.path.join(d, f))).get("ticket")) == "9":
                os.remove(os.path.join(d, f))
        except Exception:
            pass
u = "ffff0008-0000-4000-8000-000000000000"
p = os.path.join(d, u + ".json")
m = json.load(open(p)); m["role"] = "ARCHITECT"
json.dump(m, open(p, "w"))
PY
: > "$SPAWN_LOG"
out="$(ARCHITECT_MAX_CONCURRENT=1 run 9)"
assert_contains "$out" "architect cap reached" "an ARCHITECT-role worker on a ready-for-architect ticket still occupies the slot"
python3 - <<'PY'
import json, os
os.remove(os.path.join(os.environ["DAEMON_HOME"],
                       "ffff0008-0000-4000-8000-000000000000.json"))
PY
python3 - <<'PY'
import json, os
d = os.environ["DAEMON_HOME"]
os.remove(os.path.join(d, "eeee0008-0000-4000-8000-000000000000.json"))
for p in os.listdir(d):
    if p.startswith("aaaa") or p.startswith("cccc"):
        os.remove(os.path.join(d, p))
PY

echo "implement-dispatch: parent-pin stamp + recomposition dispatch"

# Fixtures land AFTER the sweep/cap sections on purpose — a new eligible
# ticket would shift their spawn counts and priority order.
#   10 = child of epic 11 · 12 = recomposition-ready epic (child 13 closed)
python3 - <<'PY'
import json, os
def issue(num, title, labels, parent=None, state="OPEN", reason=None):
    return {"number": num, "id": "ID_%d" % num, "title": title,
            "body": "body of #%d" % num,
            "state": state, "stateReason": reason, "labels": labels,
            "assignees": [], "parent": parent, "blockedBy": [],
            "closesPRs": [], "xrefPRs": [], "comments": [],
            "createdAt": "2026-07-18T00:00:00Z", "updatedAt": "2026-07-18T00:00:00Z",
            "url": "https://github.com/test/repo/issues/%d" % num}
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["10"] = issue(10, "Child of the ledger epic",
                          ["status:ready-for-implementer", "priority:P1"], parent=11)
s["issues"]["11"] = issue(11, "Ledger epic mid-flight", ["status:in-design", "priority:P1"])
s["issues"]["12"] = issue(12, "Epic awaiting recomposition",
                          ["status:ready-for-architect", "priority:P1"])
s["issues"]["13"] = issue(13, "Landed child", [], parent=12,
                          state="CLOSED", reason="COMPLETED")
s["next"] = 14
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY

mock_issue_body() {
    MB_N="$1" python3 -c "
import json, os
print(json.load(open(os.environ['MOCK_GH_STATE']))['issues'][os.environ['MB_N']]['body'])"
}

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"; : > "$MOCK_GH_LOG"
# The pin names the revision of the CONTRACT the child inherited, and the
# contract is the parent's issue BODY. It used to be the repo HEAD sha, which
# answers a different question: a body edit leaves HEAD alone and an unrelated
# commit moves it, so the Architect's lineage check ("compare the pin against
# the parent's current revision") could not be carried out at all.
# The expectation comes from _board.contract_hash itself — the SAME function
# the stamp calls and the same one the architecting protocol's documented
# command calls. Re-implementing the hash here would let the two drift and
# still pass.
body_hash() {  # <ticket> — the hash the stamp must produce for that parent
    BH_N="$1" PYTHONPATH="$BOARD_SCRIPTS" python3 -c "
import json, os, _board as B
s = json.load(open(os.environ['MOCK_GH_STATE']))
print(B.contract_hash(s['issues'][os.environ['BH_N']]['body']))" 2>/dev/null || true
}
# The INVARIANCE asserts read the pin the dispatcher actually wrote, not a
# recomputed expectation: an expectation helper that stops working reports
# nothing and every "still the same" assert passes vacuously.
pin_of() {  # <child ticket> — the hash out of its parent-pin meta
    mock_issue_body "$1" | sed -n 's/.*parent-pin: #[0-9]* @ \([0-9a-f]*\).*/\1/p' | tail -1
}
PIN11="$(body_hash 11)"
# The helper must actually answer — if it stops existing, every "the pin is
# still X" assert below would compare against an empty string and pass.
case "$PIN11" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f])
    pass "_board.contract_hash answers with a 12-hex contract id" ;;
  *) fail "_board.contract_hash answers with a 12-hex contract id (got '$PIN11')" ;;
esac
out="$(run 10)"
assert_contains "$out" "dispatched #10" "a child of an epic dispatches on the implement lane"
assert_contains "$(mock_issue_body 10)" "parent-pin: #11 @ $PIN11" \
  "dispatch stamps parent-pin (parent + a hash of the PARENT BODY) into the child meta"
assert_not_contains "$(mock_issue_body 10)" "$(git -C "$CLONE" rev-parse HEAD)" \
  "...and never the repo HEAD sha, which no body edit moves"
# ORDERING, not just presence: the stamp is a full-body read-modify-write, so
# it has to land while this dispatcher is still the only writer. After the
# spawn it raced the worker — a fast worker reads a ticket with no pin, and
# the RMW can overwrite the worker's own first board write.
PIN_ORDER="$(python3 - <<'PY'
import json, os
pin = spawn = None
for i, line in enumerate(open(os.environ["MOCK_GH_LOG"])):
    try:
        a = json.loads(line)
    except Exception:
        continue
    if spawn is None and a[:1] == ["spawn"]:
        spawn = i
    if pin is None and a[:3] == ["issue", "edit", "10"] and "--body-file" in a:
        pin = i
print("pin=%s spawn=%s %s" % (pin, spawn,
      "STAMP-BEFORE-SPAWN" if (pin is not None and spawn is not None and pin < spawn)
      else "OUT-OF-ORDER"))
PY
)"
assert_contains "$PIN_ORDER" "STAMP-BEFORE-SPAWN" \
  "the parent-pin body write lands BEFORE the worker is released"
assert_contains "$(mock_issue_body 10)" "body of #10" \
  "the stamp preserves the ticket body outside the meta block"
assert_not_contains "$(mock_issue_body 1)" "parent-pin:" \
  "no parent-pin on a parentless dispatch"

# The pin ACCUMULATES across reparents: a redispatch under a new parent must
# not erase the old entry, because the IMPACT pass reads exactly this field to
# decide whether a proposal naming that old parent is admissible (M1). A
# redispatch under the SAME parent refreshes its sha in place — lineage, not
# attempts.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 10)"
assert_contains "$(mock_issue_body 10)" "parent-pin: #11 @ $PIN11" "same-parent redispatch keeps a single entry"
assert_not_contains "$(mock_issue_body 10)" ";" "...refreshed in place, not appended"
# An EDIT to the parent contract moves the pin; a repo commit does not. This
# is the whole point of the change and neither half is observable alone.
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["11"]["body"] = "body of #11 - acceptance clause rewritten"
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
PIN11_EDITED="$(body_hash 11)"
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 10)"
assert_contains "$(mock_issue_body 10)" "parent-pin: #11 @ $PIN11_EDITED" "editing the parent body moves the pin"
assert_not_contains "$(mock_issue_body 10)" "$PIN11" "...to a different hash than the one the child first inherited"
(cd "$CLONE" && git commit -q --allow-empty -m "unrelated commit that must not move the pin")
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 10)"
assert_contains "$(mock_issue_body 10)" "parent-pin: #11 @ $PIN11_EDITED" "a repo commit with no body edit leaves the pin where it was"
# The board writes to the parent's OWN body constantly — recompose_epics
# clears pr:/branch: on every recomposition cycle alone. Hashing the whole
# body announced a changed contract every cycle, so the Architect adjudicated
# a fake diff each time and learned to discount the signal. The hash covers
# the contract text only; board:meta is stripped.
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
it = s["issues"]["11"]
it["body"] = it["body"] + "\n\n<!-- board:meta\npr: https://github.com/o/r/pull/9\nbranch: epic/int-1\n-->\n"
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
PIN_BEFORE_META="$(pin_of 10)"
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 10)"
assert_contains "$(pin_of 10)" "$PIN_BEFORE_META" "gaining a board:meta block does not move the pin"
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
it = s["issues"]["11"]
it["body"] = it["body"].replace("pr: https://github.com/o/r/pull/9\nbranch: epic/int-1", "note: reconciled")
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 10)"
assert_contains "$(pin_of 10)" "$PIN_BEFORE_META" "...and neither does a recomposition cycle rewriting that block"
# The command the architecting protocol documents must produce the STAMP.
# Two implementations of one hash is how a lineage check quietly stops
# working, so the protocol calls the same helper the dispatcher does.
DOC_HASH="$(MOCK_GH_STATE="$MOCK_GH_STATE" python3 -c "
import json, os
print(json.dumps({'body': json.load(open(os.environ['MOCK_GH_STATE']))['issues']['11']['body']}))" \
  | PYTHONPATH="$BOARD_SCRIPTS" python3 -c "import json,sys,_board as B; print(B.contract_hash(json.load(sys.stdin)['body']))")"
assert_contains "$DOC_HASH" "$PIN11_EDITED" "the protocol's documented command reproduces the stamped pin exactly"
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["10"]["parent"] = 12          # reparented onto the other epic
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 10)"
assert_contains "$(mock_issue_body 10)" "#11 @ $PIN11_EDITED; #12 @ $(body_hash 12)" \
  "a redispatch under a NEW parent appends, preserving the old lineage entry"
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["10"]["parent"] = 11          # put it back for the blocks below
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY

out="$(run 12)"
assert_contains "$out" "dispatched #12" "recomposition-ready epic dispatches"
assert_contains "$out" "role=ARCHITECT" \
  "recomposition-ready epic in ready-for-architect dispatches an Architect"

# THE ARCHITECT QUEUE IS STATE-BASED and the state outranks category. Every
# legal exit from ready-for-architect is an architect-lane exit; the spike
# protocol's first board write (ready-for-architect → in-progress) has no LEGAL
# edge from here — a category-routed spike hard-fails and the sweep
# re-dispatches into the same failure every tick. Case one: the epic (a spike
# that decomposed keeps its label and returns here for recomposition).
python3 - <<'PY'
import json, os
def issue(num, title, labels, parent=None, state="OPEN", reason=None):
    return {"number": num, "id": "ID_%d" % num, "title": title,
            "body": "body of #%d" % num,
            "state": state, "stateReason": reason, "labels": labels,
            "assignees": [], "parent": parent, "blockedBy": [],
            "closesPRs": [], "xrefPRs": [], "comments": [],
            "createdAt": "2026-07-18T00:00:00Z", "updatedAt": "2026-07-18T00:00:00Z",
            "url": "https://github.com/test/repo/issues/%d" % num}
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["14"] = issue(14, "Spike that decomposed",
                          ["status:ready-for-architect", "priority:P1", "spike"])
s["issues"]["15"] = issue(15, "Its landed child", [], parent=14,
                          state="CLOSED", reason="COMPLETED")
s["next"] = 16
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 14)"
assert_contains "$out" "dispatched #14" "a recomposed spike EPIC dispatches"
assert_contains "$out" "role=ARCHITECT" "...as an Architect claim, not on its spike category"
PROMPT14="$PROMPT_DIR/14-spike-that-decomposed.prompt"
assert_file_contains "$PROMPT14" "ARCHITECT worker for ticket #14" "the recomposed spike opens the architect protocol"
assert_file_not_contains "$PROMPT14" "spike-worker-protocol.md" "never the spike protocol, whose first write is an illegal edge here"
# Case two: the CHILDLESS spike. Epic-hood was never what made the old routing
# wrong — the state is. A leaf spike lands in this queue whenever a human files
# one design-first, and an ex-epic lands here childless once its children are
# reparented away (the sweep's reconciliation-due return does exactly that).
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["16"] = {"number": 16, "id": "ID_16", "title": "Leaf spike awaiting design",
                     "body": "body of #16", "state": "OPEN", "stateReason": None,
                     "labels": ["status:ready-for-architect", "priority:P1", "spike"],
                     "assignees": [], "parent": None, "blockedBy": [],
                     "closesPRs": [], "xrefPRs": [], "comments": [],
                     "createdAt": "2026-07-18T00:00:00Z",
                     "updatedAt": "2026-07-18T00:00:00Z",
                     "url": "https://github.com/test/repo/issues/16"}
s["next"] = 17
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"
out="$(run 16)"
assert_contains "$out" "dispatched #16" "a childless spike in the architect queue dispatches"
assert_contains "$out" "role=ARCHITECT" "...on its STATE, not its spike category"
PROMPT16="$PROMPT_DIR/16-leaf-spike-awaiting-design.prompt"
assert_file_contains "$PROMPT16" "ARCHITECT worker for ticket #16" "the childless spike opens the architect protocol"
assert_file_not_contains "$PROMPT16" "spike-worker-protocol.md" "never the spike protocol — its first write is an illegal edge from this state"
# category still routes WITHIN the implement lane — #3 above is a leaf spike
# sitting in ready-for-implementer
assert_file_contains "$PROMPT3" "SPIKE worker for ticket #3" "a spike out of ready-for-implementer still routes SPIKE"
assert_not_contains "$(mock_issue_body 12)" "parent-pin:" \
  "a parentless epic gets no stamp"

echo "implement-dispatch: surface serialization"

# Fresh board: four tickets sharing surface:recommend-rpc across the lanes.
# Labels are seeded directly (registration matching is the register script's
# concern; the dispatcher reads labels alone — no surfaces.md needed here).
seed_surface_board() {  # <state-of-22>
python3 - "$1" <<'PY'
import json, os, sys
def issue(num, title, labels):
    return {"number": num, "id": "ID_%d" % num, "title": title,
            "body": "body", "state": "OPEN", "stateReason": None,
            "labels": labels, "assignees": [], "parent": None,
            "blockedBy": [], "closesPRs": [], "xrefPRs": [], "comments": [],
            "createdAt": "2026-08-10T00:00:00Z", "updatedAt": "2026-08-10T00:00:00Z",
            "url": "https://github.com/test/repo/issues/%d" % num}
s = {"next": 30, "labels": [], "issues": {
    "20": issue(20, "First rewrite", ["status:ready-for-implementer", "priority:P1",
                                      "surface:recommend-rpc"]),
    "21": issue(21, "Second rewrite", ["status:ready-for-implementer", "priority:P2",
                                       "surface:recommend-rpc"]),
    "22": issue(22, "Occupant", ["status:%s" % sys.argv[1], "priority:P1",
                                 "surface:recommend-rpc"]),
    "23": issue(23, "Consolidation design", ["status:ready-for-architect", "priority:P0",
                                             "surface:recommend-rpc"]),
    "24": issue(24, "Read-only probe", ["status:ready-for-implementer", "priority:P0",
                                        "spike", "surface:recommend-rpc"]),
}}
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
}

# T9b: WITHOUT a surfaces.md registry, a surface label is ignored — the
# leftover-label case must not queue eligible work forever (the no-registry
# inertness contract covers the dispatcher too).
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board in-progress
out="$(run 20)"
assert_contains "$out" "dispatched #20" \
  "no registry: a surface label does not serialize (inertness holds)"

# The registry lands on the clone's default branch (what production reads:
# origin/HEAD, freshly fetched); every scenario below runs with it present.
mkdir -p "$CLONE/.doperpowers"
printf '## recommend-rpc\n- paths: sql/*recommend*.sql\n- identifiers: recommend_for_student\n' \
  > "$CLONE/.doperpowers/surfaces.md"
git -C "$CLONE" add .doperpowers/surfaces.md
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m surfaces
git -C "$CLONE" push -q origin main

# T10: a board-state occupant (in-progress) blocks the implement lane only —
# the architect (resolver) and the spike (read-only) still dispatch.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board in-progress
out="$(run --sweep)"
assert_contains "$out" "surface recommend-rpc occupied by #22 — #20 queued" \
  "surface occupant blocks an implement dispatch with a named reason"
assert_contains "$out" "surface recommend-rpc occupied by #22 — #21 queued" \
  "every queued implement ticket on the surface reports, none spawns"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 20-" "blocked ticket #20 did not spawn"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 23-" "architect lane is never surface-blocked"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 24-" "spike lane is never surface-blocked"

# T11: the registry arm — an occupant whose board state still lags (fresh
# spawn: ready-for-implementer + live working meta) must still occupy.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board ready-for-implementer
python3 - <<'PY'
import json, os
json.dump({"uuid": "ffff0001-0000-4000-8000-000000000000", "current": "x",
           "name": "22-occupant", "ticket": "22", "status": "working",
           "updated": "2026-08-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "ffff0001-0000-4000-8000-000000000000.json"), "w"))
PY
out="$(run --sweep)"
assert_contains "$out" "surface recommend-rpc occupied by #22 — #20 queued" \
  "a live bound worker occupies before its first board write (registry arm)"

# T12: in-tick claim — two eligible same-surface tickets in ONE sweep yield
# exactly one dispatch; the second names the in-tick claim. The architect and
# spike rows are removed: an architect dispatch would claim the surface first
# (it occupies by design), which is T14's scenario, not this one.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board "done"   # 22 out of the way (terminal states never occupy)
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
del s["issues"]["23"], s["issues"]["24"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out="$(run --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 20-" "first same-surface ticket dispatches (priority order)"
assert_contains "$out" "surface recommend-rpc occupied by #20 — #21 queued" \
  "second same-surface ticket waits in the same tick (registry arm names the fresh spawn; the in-tick claim set is its belt)"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 21-" "in-tick claim held: #21 did not spawn"

# T13: occupancy clears → the queued ticket dispatches on the next sweep.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board "done"
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
del s["issues"]["20"], s["issues"]["23"], s["issues"]["24"]   # nothing occupies now
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out="$(run --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 21-" "queued ticket dispatches once the surface is free"

# T14: an architect mid-design (in-design) occupies against implementers —
# patch work waits while the consolidation redesign runs.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board "done"
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["23"]["labels"] = ["status:in-design", "priority:P0", "surface:recommend-rpc"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out="$(run --sweep)"
assert_contains "$out" "surface recommend-rpc occupied by #23 — #20 queued" \
  "an in-design architect ticket occupies the surface against implementers"

# T15: SURFACE_OVERRIDE=1 — deliberate bypass, loudly logged.
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
seed_surface_board in-progress
out="$(SURFACE_OVERRIDE=1 run 20)"
assert_contains "$out" "SURFACE_OVERRIDE=1: dispatching #20 onto occupied surface recommend-rpc (occupant #22)" \
  "override dispatches with a loud line (triggered mode shares the guard)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 20-" "override actually spawned"

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
