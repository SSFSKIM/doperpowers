#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# A machine enrolled after the work it must read exists: its first download of
# a project's log, as the hub runs it on the fleet (EN.G1's live check,
# docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, M5). The
# hub sends the backlog writer by writer, lexically, a page at a time, and
# what is written after the hello waits behind the whole backlog; until the
# writer of a session arrives, nothing here holds a row of it.
#
# - The spawner reached meanwhile: a seat `spawn --asked-from` opened here,
#   its record carrying the spawner's address as that launch writes it,
#   reaches its spawner by `@<short>` with no row of the spawner on this
#   machine at all (the relay from mac held back for the whole case), and
#   mac delivers it to the spawner's session; with the address absent the
#   tag is refused (exit 4); once the row arrives after the spawner's thread
#   changed session, the row wins.
# - The thread reached once read: before the backlog reaches a stopped
#   thread that changed session, `@<short>` of its first session is refused
#   as it always was (exit 4); a page at a time, and what mac writes after
#   the hello only behind the backlog; at its end, the host's notice to the
#   first session's short reaches the thread's current session.
#
# Two real sminos homes, each cut over to its own endpoint_standin.py and
# running its daemon (rl10-machines.sh); between them only endpoint_standin's
# `hand`, one way at a time, with its `page` for the backlog. Hermetic: HOME
# and SMINOS_HOME are temporary, one pair per machine.
#
# FRESH_MACHINE_ORDER=reverse hands the backlog's writers in reverse lexical
# order instead (the thread's second session before its first, the spawner
# before the filler): the hub may come to send recently active writers
# first, and nothing here may depend on the lexical order.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"
ENGINE="$SCRIPT_DIR/wake_engine.py"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smn.XXXXXX)"
T="$(cd "$T" && pwd -P)"
PIDS=()
cleanup() {
  for st in "$T/mac/engine" "$T/vm/engine"; do
    python3 -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import wake_engine; wake_engine.stop_all(sys.argv[2])' \
      "$SCRIPT_DIR" "$st" 2>/dev/null || true
  done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "$T/" >/dev/null 2>&1 || break; sleep 0.05; done
  rm -rf "$T"
}
trap cleanup EXIT

pass() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "  FAIL $1"; }
assert_equals() {
  if [[ "$1" == "$2" ]]; then pass "$3"; else
    fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
  if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:900}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
assert_rc() { if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; fi; }
run_in() { # dir command... — OUT and RC of the command run there
  local d=$1; shift
  set +e; OUT="$(cd "$d" && "$@" 2>&1)"; RC=$?; set -e
}
# Polls every 50 ms until the command holds; one liveness bound, 30 s (ci-kit §6).
until_true() {
  local end=$((SECONDS + 30))
  until "$@"; do
    [ "$SECONDS" -ge "$end" ] && return 1
    sleep 0.05
  done
}
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }
py() { python3 -B -c "$@"; }

# SMINOS_RL10 first: sminos_rl10 prefers it to the machine's own endpoint, so one inherited would have these
# daemons dial an endpoint outside the test; each machine's is its stand-in's, under its MAWS_USER_DATA (rl10_as).
unset SMINOS_RL10 CLAUDE_CODE_SESSION_ID CLAUDE_PID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT \
  CLAUDE_PROJECT_DIR CLAUDE_CONFIG_DIR
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS WAKE_ENGINE="$ENGINE"
mkdir -p "$T/bin"
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
exec python3 -B "$WAKE_ENGINE" "$@"
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"
[ "$(command -v claude)" = "$T/bin/claude" ] || { echo "FAIL claude on PATH is $(command -v claude), not the stand-in"; exit 1; }

as() { # dir host — one machine: its HOME, its SMINOS_HOME, its engine's state, its host name
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" WAKE_ENGINE_STATE="$T/$1/engine" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME/daemon" "$WAKE_ENGINE_STATE"
}

# A transcript of the session, launched in dir, its last turn in `auto` (a mode whose wake asks nothing).
transcript() { # session dir [mode]
  local tx="$HOME/.claude/projects/p-$1/$1.jsonl"
  mkdir -p "$(dirname "$tx")"
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","permissionMode":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
    "${1:0:8}" "$1" "$2" "${3:-auto}" > "$tx"
}
# A running session with an inbox (inbox_standin.py, which appends each frame it takes): its engine record (the
# inbox's pid is the session's process). Frames land in $T/<box>.received.
live_session() { # box session dir [kind] [mode]
  : > "$T/$1.received"
  python3 "$SCRIPT_DIR/inbox_standin.py" "$T/$1.sock" "$T/$1.received" & PIDS+=("$!")
  local pid=$!
  until_true test -S "$T/$1.sock"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"%s","status":"idle","cwd":"%s","messagingSocketPath":"%s","entrypoint":"cli"}\n' \
    "$pid" "$2" "$1" "${4:-interactive}" "$3" "$T/$1.sock" > "$HOME/.claude/sessions/$1.json"
  [ -f "$HOME/.claude/projects/p-$2/$2.jsonl" ] || transcript "$2" "$3" "${5:-auto}"
  eval "PID_$1=$pid"
}
ended() { # box — its process gone, its record with it
  local pid
  eval "pid=\${PID_$1}"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -f "$HOME/.claude/sessions/$1.json"
}
handed_off() { # from-session to-session — the engine's hand-off to a background job: `continued-in` at the end
  printf '{"type":"continued-in","timestamp":"2026-11-21T10:00:00.000Z","sessionId":"%s","continuedInSessionId":"%s"}\n' \
    "$1" "$2" >> "$HOME/.claude/projects/p-$1/$1.jsonl"
}
received() { cat "$T/$1.received" 2>/dev/null || true; }
got() { received "$1" | grep -Fq -- "$2"; }   # box text — whether the inbox holds a frame carrying the text
inputs() { cat "$WAKE_ENGINE_STATE/inputs/$1" 2>/dev/null || true; }

write_smns() { # dir name — a .smns naming only the org
  py 'import json, sys, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": sys.argv[1], "remote": "", "hub": {"org": "org-1"}}, indent=2))' \
    "$2" > "$1/.smns"
}
smns_id() { py 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$1/.smns"; }
start_daemon() { "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & PIDS+=("$!"); }
events_with() { # project-id text — the events of this machine's log of the project that carry the text
  cat "$SMINOS_HOME/projects/$1/log/"*.jsonl 2>/dev/null | grep -F -- "$2" || true
}
has_event() { [ -n "$(events_with "$1" "$2")" ]; }   # project-id text — read again at each call
field_of() { py 'import json, sys; print(json.dumps(json.loads(sys.argv[1]).get(sys.argv[2])))' "$1" "$2"; }
# Whether this machine's projection of the project binds `name` to the session (a former session's short included).
binds() { # project-id name session
  (cd "$T/x" && python3 -B -c 'import sys
sys.path.insert(0, sys.argv[1])
import sminos
p = sminos.find_project(sys.argv[2])
m = sminos.match_members(sys.argv[3], "", [p], alias=False)
sys.exit(0 if len(m) == 1 and m[0][1].session == sys.argv[4] else 1)' "$SCRIPTS" "$1" "$2" "$3") 2>/dev/null
}
mkdir -p "$T/x"

# ---- two machines, the second enrolled late ------------------------------------------------
# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"
rl10_as mac mac
rl10_cut_over
printf '{"ceiling": "auto"}\n' > "$SMINOS_HOME/daemon/policy.json"
EPM=$EP
P="$T/mac/home/team"
gitq init -q "$P"
write_smns "$P" team
PP="$(smns_id "$P")"
rl10_as vm vm
rl10_cut_over
EPV=$EP
VHOME="$T/vm/home"
mkdir -p "$VHOME/team"
cp "$P/.smns" "$VHOME/team/.smns"
DIRECTORY="$(python3 - "$PP" "$(rl10_mp mac)" "$(rl10_mp vm)" <<'PY'
import json, sys
p, mmp, vmp = sys.argv[1:4]
print(json.dumps({"projects": [{"id": p, "name": "team", "kind": "hub", "retired": False},
                               {"id": mmp, "name": "mac", "kind": "machine", "machine": "mac", "retired": False},
                               {"id": vmp, "name": "vm", "kind": "machine", "machine": "vm", "retired": False}],
                  "machines": [{"name": "mac", "online": True}, {"name": "vm", "online": True}]}))
PY
)"
rl10_as mac mac
rl10_serve "\"org\": $DIRECTORY, \"verdict\": \"peer\""
start_daemon
rl10_as vm vm
rl10_serve "\"org\": $DIRECTORY"
hand() { python3 "$SCRIPT_DIR/endpoint_standin.py" hand "$@" >/dev/null; }   # source destination [page]
accepted_holds() { # ep-dir writer-substring — whether the stand-in took an event of that writer in team
  python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$1" accepted "{\"project\": \"$PP\"}" | grep -Fq -- "$2"
}
on_vm() { rl10_as vm vm; run_in "$VHOME/team" "$@"; }   # the host's own program: no session
input_has() { inputs "$1" | grep -Fq -- "$2"; }   # session text — whether the engine's inbox took it

# ---- mac's work, before vm enrolls ------------------------------------------------------------
# Writers sort as the hub sends them: mac/0f… (filler), mac/5c… (the spawner), mac/fa… and mac/fb… (the thread).
echo "mac's work, before vm enrolls:"
rl10_as mac mac
F=0f000001-0000-4000-8000-0000000000f1
SA=5c000001-0000-4000-8000-0000000000c1
SA2=5c000002-0000-4000-8000-0000000000c2
R1=fa000001-0000-4000-8000-0000000000a1
R2=fb000002-0000-4000-8000-0000000000b2
ORDER=()
[ "${FRESH_MACHINE_ORDER:-}" = reverse ] && ORDER=("mac/$R2,mac/$R1,mac/$SA,mac/$F")
page() { hand "$EPM" "$EPV" 2 ${ORDER[@]+"${ORDER[@]}"}; }   # one page of mac's backlog to vm
live_session filler "$F" "$P"
live_session spa "$SA" "$P"
run_in "$P" "$SMINOS" list
for n in 1 2 3; do run_in "$P" env CLAUDE_CODE_SESSION_ID="$F" "$SMINOS" say "filler $n"; done
transcript "$R1" "$P"
run_in "$P" "$SMINOS" seat add team keeper --session "$R1"
assert_rc 0 "$RC" "a seat filled by R1"
live_session keeper1 "$R1" "$P" bg
run_in "$P" "$SMINOS" list
ended keeper1
transcript "$R2" "$P"
run_in "$P" "$SMINOS" seat add team keeper --session "$R2"
assert_rc 0 "$RC" "refilled by R2: the thread changed session"
live_session keeper2 "$R2" "$P" bg
run_in "$P" "$SMINOS" list
ended keeper2
for _ in 1 2; do run_in "$P" "$SMINOS" daemon tick; done
if until_true accepted_holds "$EPM" "mac/$R2"; then pass "mac's endpoint holds the thread's second session"; else
  fail "mac's endpoint holds the thread's second session"; fi

echo "vm enrolls:"
rl10_as vm vm
start_daemon
vm_opened() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPV" opened | grep -Fq -- "$PP"; }
if until_true vm_opened; then pass "vm's uplink opened team (its hello)"; else fail "vm's uplink opened team (its hello)"; fi

# ---- the spawner, with no row of it here --------------------------------------------------------
echo "the spawner reached by its address:"
rl10_as vm vm
C=5d000001-0000-4000-8000-0000000000d1
transcript "$C" "$VHOME/team"
run_in "$VHOME/team" "$SMINOS" seat add team child --session "$C"
assert_rc 0 "$RC" "the child is a seat of vm"
live_session child "$C" "$VHOME/team" bg
run_in "$VHOME/team" "$SMINOS" list
binds "$PP" "${SA:0:8}" "$SA" && fail "vm holds no row of the spawner (nothing relayed from mac)" \
  || pass "vm holds no row of the spawner (nothing relayed from mac)"
run_in "$VHOME/team" env CLAUDE_CODE_SESSION_ID="$C" "$SMINOS" say "@${SA:0:8} up on vm, no address"
assert_rc 4 "$RC" "with the address absent, the tag is refused as before"
assert_contains "$OUT" "no member @${SA:0:8} in project team, nor a session of that id in any project known here" \
  "in words that say what was searched"
# The seat's record as spawn --asked-from's launch writes it: the request's spawner, with its org.
py 'import sys
sys.path.insert(0, sys.argv[1])
import sminos
[seat] = [s for s in sminos.seats() if s["current"] == sys.argv[2]]
sminos.meta_set(seat["seat_id"], {sminos.SPAWNER_ADDRESS: {"session": sys.argv[3], "alias": "spa", "project": sys.argv[4],
                                                           "machine": "mac", "org": "org-1"}})' "$SCRIPTS" "$C" "$SA" "$PP"
run_in "$VHOME/team" env CLAUDE_CODE_SESSION_ID="$C" "$SMINOS" say "@${SA:0:8} up on vm"
assert_rc 0 "$RC" "the child's tag is accepted"
assert_equals "$(field_of "$(events_with "$PP" "up on vm\"")" to)" "[{\"session\": \"$SA\", \"alias\": \"spa\"}]" \
  "recorded for the spawner's session"
rl10_as mac mac
until_true accepted_holds "$EPV" "up on vm\"" || true
until_true eval 'hand "$EPV" "$EPM"; got spa "up on vm"' || true
got spa "up on vm" && pass "mac delivered it to the spawner's session" || fail "mac delivered it to the spawner's session"

# ---- the backlog, a page at a time ----------------------------------------------------------------
echo "the backlog, a page at a time:"
rl10_as vm vm
on_vm "$SMINOS" who --thread="${R1:0:8}"
assert_rc 4 "$RC" "before the backlog reaches the thread: who --thread of its first session answers nothing"
on_vm "$SMINOS" say "@${R1:0:8} devcloud on vm: too early"
assert_rc 4 "$RC" "and a tag of it is refused, as it always was"
page
rl10_as mac mac
run_in "$P" env CLAUDE_CODE_SESSION_ID="$F" "$SMINOS" say "live after the hello"
until_true accepted_holds "$EPM" "live after the hello" || true
rl10_as vm vm
passes=1
until binds "$PP" "${R1:0:8}" "$R2"; do
  [ "$passes" -ge 400 ] && break
  [ -z "$(events_with "$PP" "live after the hello")" ] || { fail "the live event came before the backlog's end"; break; }
  page
  passes=$((passes + 1))
  sleep 0.1
done
binds "$PP" "${R1:0:8}" "$R2" && pass "at the backlog's end the first session's short binds R2 ($passes passes)" \
  || fail "at the backlog's end the first session's short binds R2 ($passes passes)"
assert_equals "$(events_with "$PP" "live after the hello")" "" "what mac wrote after the hello waits behind the backlog"
until_true eval 'page; has_event "$PP" "live after the hello"' || true
has_event "$PP" "live after the hello" && pass "then it comes" || fail "then it comes"

echo "the notice reaches the thread's current session:"
on_vm "$SMINOS" say --notice devcloud --exit-held "@${R1:0:8} devcloud on vm: idle 3d (fresh)"
# 0 or 3: in this harness mac publishes the stopped thread's state as held, then as woken, more than once in its first
# seconds, and the VM's say reads whichever word it holds; either way the notice is recorded for R2 and mac wakes it.
[[ "$RC" == 0 || "$RC" == 3 ]] && pass "the host's notice to the first session's short is accepted (exit $RC)" \
  || fail "the host's notice to the first session's short is accepted (exit $RC)"
assert_equals "$(field_of "$(events_with "$PP" "idle 3d (fresh)")" to)" "[{\"session\": \"$R2\", \"alias\": \"keeper\"}]" \
  "recorded for R2"
rl10_as mac mac
until_true accepted_holds "$EPV" "idle 3d (fresh)" || true
until_true eval 'hand "$EPV" "$EPM"; input_has "$R2" "idle 3d (fresh)"' || true
assert_contains "$(inputs "$R2")" "idle 3d (fresh)" "R2 woken and handed the notice"

# ---- the row wins once it arrives -----------------------------------------------------------------
echo "the spawner's row wins once it arrives:"
rl10_as mac mac
handed_off "$SA" "$SA2"
transcript "$SA2" "$P"
live_session spa2 "$SA2" "$P" bg
ended spa
run_in "$P" "$SMINOS" list
rl10_as vm vm
until_true eval 'hand "$EPM" "$EPV"; binds "$PP" "${SA:0:8}" "$SA2"' || true
binds "$PP" "${SA:0:8}" "$SA2" && pass "vm has read the spawner's hand-off" || fail "vm has read the spawner's hand-off"
run_in "$VHOME/team" env CLAUDE_CODE_SESSION_ID="$C" "$SMINOS" say "@${SA:0:8} after the change"
assert_rc 0 "$RC" "accepted"
assert_equals "$(field_of "$(events_with "$PP" "after the change")" to)" "[{\"session\": \"$SA2\", \"alias\": \"spa2\"}]" \
  "recorded for the session the spawner's thread holds now, not the one the address names"
assert_equals "$(py 'import sys
sys.path.insert(0, sys.argv[1])
import sminos
print([s[sminos.SPAWNER_ADDRESS]["session"] for s in sminos.seats() if s["current"] == sys.argv[2]])' "$SCRIPTS" "$C")" \
  "['$SA']" "though the child's seat still carries the spawner's address"
rl10_as mac mac
until_true accepted_holds "$EPV" "after the change" || true
until_true eval 'hand "$EPV" "$EPM"; got spa2 "after the change"' || true
got spa2 "after the change" && pass "mac delivered it to that session" || fail "mac delivered it to that session"

echo
if [ "$FAILURES" -eq 0 ]; then echo "test-fresh-machine${ORDER[0]:+ (writers in reverse order)}: all $PASSES assertions passed"; else
  echo "test-fresh-machine: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"; exit 1; fi
