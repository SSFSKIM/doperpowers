#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# A machine's notice between two machines (EN.G1's plan, M1:
# docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, acceptance
# 8, 9 and 10): `vm` plays a devcloud host, which speaks with no session, and
# `mac` the machine that holds the thread owning it.
#
# - Today's call (`say "@<short> devcloud on vm: …"`, unmarked: a host made
#   before this change) names a session its thread has left, by a hand-off
#   and by a refill; once vm has read the change it is recorded for the
#   thread's current session and pushed to it, and a stopped one is woken
#   first, once.
# - Marked (`--notice devcloud --exit-held`): the frame from devcloud@vm,
#   whether mac's endpoint answers `peer` or `words`; on vm itself, its own
#   endpoint answering `words`, the broadcast reaches a session's inbox and
#   never its bridge.
# - Going on (§3's order, run by hand): a thread held for `mode` that mac
#   published makes step 1 exit 3, and the broadcast reaches a live member of
#   its project on mac; held and nobody live: 3, then 4, then the
#   `--in` note under vm's plain writer, which a session that joins later
#   reads in `sminos chat`.
# - The accepted limit: a notice vm writes before it has read a hand-off
#   names the session the thread left: pushed to nobody, no process started,
#   and in the current session's next `sminos chat`.
#
# Two real sminos homes, each cut over to its own endpoint_standin.py and
# running its daemon (rl10-machines.sh), what one endpoint took reaching the
# other through rl10_relay. mac's `claude` is the test engine
# (wake_engine.py). Hermetic: HOME and SMINOS_HOME are temporary, one pair per
# machine; nothing reaches a network beyond 127.0.0.1.
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

unset CLAUDE_CODE_SESSION_ID CLAUDE_PID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT \
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
from_name() { # box text — the from-name of the inbox's frame carrying the text
  py 'import json, re, sys
for line in open(sys.argv[1]):
    c = json.loads(line)["message"]["content"]
    if sys.argv[2] in c:
        m = re.match(r"<cross-session-message from-name=\"([^\"]*)\">", c)
        print(m.group(1) if m else "")
        break' "$T/$1.received" "$2"
}
inputs() { cat "$WAKE_ENGINE_STATE/inputs/$1" 2>/dev/null || true; }
launches() { cat "$WAKE_ENGINE_STATE/launches" 2>/dev/null || echo 0; }

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
# Whether this machine reads the member's published wake as `held`.
held_here() { # project-id session
  (cd "$T/x" && python3 -B -c 'import sys
sys.path.insert(0, sys.argv[1])
import sminos
p = sminos.find_project(sys.argv[2])
m = next((m for m in sminos.members(p) if m.session == sys.argv[3]), None)
sys.exit(0 if m is not None and sminos.remote_held(m) else 1)' "$SCRIPTS" "$1" "$2") 2>/dev/null
}
mkdir -p "$T/x"

# ---- two machines --------------------------------------------------------------------------
# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"
declare_project() { # dir name — a repository of mac's with a hub .smns; its id in PID_OUT
  gitq init -q "$1"
  write_smns "$1" "$2"
  PID_OUT="$(smns_id "$1")"
}
rl10_as mac mac
rl10_cut_over
printf '{"ceiling": "auto"}\n' > "$SMINOS_HOME/daemon/policy.json"
EPM=$EP
P="$T/mac/home/team"; declare_project "$P" team; PP=$PID_OUT
Q1="$T/mac/home/held"; declare_project "$Q1" heldproj; PQ1=$PID_OUT
Q2="$T/mac/home/quiet"; declare_project "$Q2" quietproj; PQ2=$PID_OUT
rl10_as vm vm
rl10_cut_over
EPV=$EP
VHOME="$T/vm/home"
mkdir -p "$VHOME/team"
cp "$P/.smns" "$VHOME/team/.smns"
DIRECTORY="$(python3 - "$PP" "$PQ1" "$PQ2" "$(rl10_mp mac)" "$(rl10_mp vm)" <<'PY'
import json, sys
p, q1, q2, mmp, vmp = sys.argv[1:6]
print(json.dumps({"projects": [{"id": p, "name": "team", "kind": "hub", "retired": False},
                               {"id": q1, "name": "heldproj", "kind": "hub", "retired": False},
                               {"id": q2, "name": "quietproj", "kind": "hub", "retired": False},
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
start_daemon
relayed() { rl10_relay "$EPM" "$EPV"; "$@"; }
on_vm() { rl10_as vm vm; run_in "$VHOME" "$@"; }   # the host's own program: no session
verdict() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$1" set "{\"verdict\": \"$2\"}" >/dev/null; }

# ---- today's call reaches the thread's current session -------------------------------------
echo "today's call, after a hand-off:"
rl10_as mac mac
S1=5a000001-0000-4000-8000-0000000000a1
S2=5a000002-0000-4000-8000-0000000000a2
live_session s1 "$S1" "$P"
run_in "$P" "$SMINOS" list
rl10_as vm vm
until_true relayed binds "$PP" "${S1:0:8}" "$S1" || true
binds "$PP" "${S1:0:8}" "$S1" && pass "vm reads S1 in team" || fail "vm reads S1 in team"
rl10_as mac mac
handed_off "$S1" "$S2"
transcript "$S2" "$P"
live_session s2 "$S2" "$P" bg
ended s1
run_in "$P" "$SMINOS" list
rl10_as vm vm
until_true relayed binds "$PP" "${S1:0:8}" "$S2" || true
binds "$PP" "${S1:0:8}" "$S2" && pass "vm has read the hand-off: S1's short binds S2" \
  || fail "vm has read the hand-off: S1's short binds S2"
on_vm "$SMINOS" say "@${S1:0:8} devcloud on vm: idle 3d (today)"
assert_rc 0 "$RC" "today's call is accepted"
assert_equals "$(field_of "$(events_with "$PP" "idle 3d (today)")" to)" "[{\"session\": \"$S2\", \"alias\": \"s2\"}]" \
  "recorded in team's log for S2"
rl10_as mac mac
until_true relayed got s2 "idle 3d (today)" || true
got s2 "idle 3d (today)" && pass "S2's inbox holds it" || fail "S2's inbox holds it"

echo "today's call, the thread stopped:"
ended s2
for _ in 1 2; do run_in "$P" "$SMINOS" daemon tick; done
before="$(launches)"
on_vm "$SMINOS" say "@${S1:0:8} devcloud on vm: idle 6d (stopped)"
assert_rc 0 "$RC" "accepted for the stopped thread"
rl10_as mac mac
input_has() { inputs "$1" | grep -Fq -- "$2"; }   # session text — whether the engine's inbox took it
until_true relayed input_has "$S2" "idle 6d (stopped)" || true
assert_contains "$(inputs "$S2")" "idle 6d (stopped)" "pushed to S2 once woken"
assert_equals "$(launches)" "$((before + 1))" "one wake"
assert_equals "$(inputs "$S2" | grep -c "idle 6d (stopped)")" 1 "once"

echo "today's call, after a refill:"
rl10_as mac mac
R1=5b000001-0000-4000-8000-0000000000b1
R2=5b000002-0000-4000-8000-0000000000b2
transcript "$R1" "$P"
run_in "$P" "$SMINOS" seat add team keeper --session "$R1"
assert_rc 0 "$RC" "a seat filled by R1"
live_session keeper1 "$R1" "$P" bg
run_in "$P" "$SMINOS" list
rl10_as vm vm
until_true relayed binds "$PP" "${R1:0:8}" "$R1" || true
rl10_as mac mac
ended keeper1
transcript "$R2" "$P"
run_in "$P" "$SMINOS" seat add team keeper --session "$R2"
assert_rc 0 "$RC" "refilled by R2"
live_session keeper2 "$R2" "$P" bg
run_in "$P" "$SMINOS" list
rl10_as vm vm
until_true relayed binds "$PP" "${R1:0:8}" "$R2" || true
binds "$PP" "${R1:0:8}" "$R2" && pass "vm has read the refill: R1's short binds R2" \
  || fail "vm has read the refill: R1's short binds R2"
on_vm "$SMINOS" say "@${R1:0:8} devcloud on vm: lease ends (refill)"
assert_rc 0 "$RC" "accepted"
rl10_as mac mac
until_true relayed got keeper2 "lease ends (refill)" || true
got keeper2 "lease ends (refill)" && pass "R2's inbox holds it" || fail "R2's inbox holds it"

# ---- marked ------------------------------------------------------------------------------
echo "marked, under each of mac's verdicts:"
for v in peer words; do
  rl10_as mac mac
  verdict "$EPM" "$v"
  on_vm "$SMINOS" say --notice devcloud --exit-held "@${R1:0:8} devcloud on vm: marked ($v)"
  assert_rc 0 "$RC" "marked, $v: exit 0 for a live thread"
  assert_equals "$(field_of "$(events_with "$PP" "marked ($v)")" notice)" '"devcloud"' "marked, $v: the field"
  rl10_as mac mac
  until_true relayed got keeper2 "marked ($v)" || true
  assert_equals "$(from_name keeper2 "marked ($v)")" "devcloud@vm" "marked, $v: the frame from devcloud@vm, in the inbox"
  assert_contains "$(received keeper2 | grep -F "marked ($v)")" "from devcloud@vm" "marked, $v: its chat header names it"
  assert_not_contains "$(received keeper2 | grep -F "marked ($v)")" "To reply" "marked, $v: no reply line"
done
verdict "$EPM" peer

echo "on vm itself, its own endpoint answering words:"
rl10_as vm vm
V1=5c000001-0000-4000-8000-0000000000c1
live_session v1 "$V1" "$VHOME/team"
run_in "$VHOME/team" "$SMINOS" list
mkdir -p "$SMINOS_HOME/bridge"
python3 - "$SMINOS_HOME/bridge/$V1.sock" "$T/v1.bridge" <<'PY' & PIDS+=("$!")
# A bridge for v1 that takes every command and writes it down: the route a person's words would take.
import http.server, json, os, socket, socketserver, sys
path, log = sys.argv[1], sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        with open(log, "ab") as f:
            f.write(body + b"\n")
        out = json.dumps({"ok": True, "result": {}}).encode()
        self.send_response(200)
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
    def log_message(self, *a):
        pass
class S(socketserver.UnixStreamServer):
    def get_request(self):
        req, _ = super().get_request()
        return req, ("bridge", 0)
tmp = path + ".tmp"
s = S(tmp, H)
os.rename(tmp, path)
s.serve_forever()
PY
until_true test -S "$SMINOS_HOME/bridge/$V1.sock"
on_vm "$SMINOS" say --notice devcloud --project "$PP" "devcloud on vm: to all (on vm)"
assert_rc 0 "$RC" "the broadcast is accepted"
until_true got v1 "to all (on vm)" || true
assert_equals "$(from_name v1 "to all (on vm)")" "devcloud@vm" "v1's inbox holds the notice frame"
assert_equals "$(cat "$T/v1.bridge" 2>/dev/null || true)" "" "and its bridge was handed nothing"
ended v1

# ---- going on -----------------------------------------------------------------------------
echo "a thread held for mode, and a live member of its project:"
rl10_as mac mac
H1=5d000001-0000-4000-8000-0000000000d1
M1=5d000002-0000-4000-8000-0000000000d2
live_session h1 "$H1" "$Q1" interactive plan
live_session m1 "$M1" "$Q1"
run_in "$Q1" "$SMINOS" list
ended h1
for _ in 1 2; do run_in "$Q1" "$SMINOS" daemon tick; done
rl10_as vm vm
until_true relayed held_here "$PQ1" "$H1" || true
held_here "$PQ1" "$H1" && pass "vm reads h1 held" || fail "vm reads h1 held"
on_vm "$SMINOS" say --notice devcloud --exit-held "@${H1:0:8} devcloud on vm: idle (held)"
assert_rc 3 "$RC" "step 1 exits 3"
assert_contains "$OUT" "recorded and held on mac: the session is stopped and is not woken: a wake would run it in a mode that asks for approval" \
  "with the held line"
on_vm "$SMINOS" say --notice devcloud --project "$PQ1" "devcloud on vm: idle (to the project)"
assert_rc 0 "$RC" "the broadcast that follows is accepted"
rl10_as mac mac
until_true relayed got m1 "idle (to the project)" || true
got m1 "idle (to the project)" && pass "and reaches m1, live on mac" || fail "and reaches m1, live on mac"
assert_equals "$(from_name m1 "idle (to the project)")" "devcloud@vm" "from devcloud@vm"

# Its reach left the default: a private one's state reaches vm only through the endpoint's audiences, which this
# pair of stand-ins does not relay, and what is asserted here, each step's exit and the note, does not turn on it
# (the host runs the note step whatever step 1 recorded: devcloud's test_idle.py pins that order).
echo "held, nobody live:"
rl10_as mac mac
H2=5e000001-0000-4000-8000-0000000000e1
live_session h2 "$H2" "$Q2" interactive plan
run_in "$Q2" "$SMINOS" list
ended h2
for _ in 1 2; do run_in "$Q2" "$SMINOS" daemon tick; done
rl10_as vm vm
until_true relayed held_here "$PQ2" "$H2" || true
held_here "$PQ2" "$H2" && pass "vm reads h2 held" || fail "vm reads h2 held"
on_vm "$SMINOS" say --notice devcloud --exit-held "@${H2:0:8} devcloud on vm: idle (nobody live)"
assert_rc 3 "$RC" "step 1 exits 3"
on_vm "$SMINOS" say --notice devcloud --project "$PQ2" "devcloud on vm: idle (nobody live)"
assert_rc 4 "$RC" "the broadcast exits 4: nobody live"
on_vm "$SMINOS" say --notice devcloud --in "$PQ2" "devcloud on vm: idle (the note)"
assert_rc 0 "$RC" "the note is written"
NOTE="$(events_with "$PQ2" "idle (the note)")"
assert_equals "$(field_of "$NOTE" writer) $(field_of "$NOTE" to) $(field_of "$NOTE" notice)" '"vm/human" "*" "devcloud"' \
  "in quietproj's log under vm's plain writer, untagged, marked"
rl10_as mac mac
J1=5e000002-0000-4000-8000-0000000000e2
until_true relayed test -n "$(events_with "$PQ2" "idle (the note)")" || true
live_session j1 "$J1" "$Q2"
run_in "$Q2" "$SMINOS" list
run_in "$Q2" env CLAUDE_CODE_SESSION_ID="$J1" "$SMINOS" chat
assert_contains "$OUT" "devcloud on vm: idle (the note)" "a session that joins later reads it in chat"
assert_contains "$(grep -F "idle (the note)" <<<"$OUT")" " devcloud@vm" "from devcloud@vm"

# ---- the accepted limit ---------------------------------------------------------------------
echo "a notice vm writes before it read the hand-off:"
rl10_as mac mac
U1=5f000001-0000-4000-8000-0000000000f1
U2=5f000002-0000-4000-8000-0000000000f2
live_session u1 "$U1" "$P"
run_in "$P" "$SMINOS" list
rl10_as vm vm
until_true relayed binds "$PP" "${U1:0:8}" "$U1" || true
rl10_as mac mac
handed_off "$U1" "$U2"
transcript "$U2" "$P"
live_session u2 "$U2" "$P" bg
ended u1
run_in "$P" "$SMINOS" list
before="$(launches)"
on_vm "$SMINOS" say --notice devcloud --exit-held "@${U1:0:8} devcloud on vm: lagging"
assert_rc 0 "$RC" "accepted: vm still reads U1 as the thread's session"
assert_equals "$(field_of "$(events_with "$PP" "lagging")" to)" "[{\"session\": \"$U1\", \"alias\": \"u1\"}]" \
  "the event names U1"
rl10_as mac mac
until_true relayed test -n "$(events_with "$PP" "lagging")" || true
for _ in 1 2 3; do relayed run_in "$P" "$SMINOS" daemon tick; done
assert_not_contains "$(received u2)" "lagging" "pushed to no session: not to U2"
assert_equals "$(launches)" "$before" "and no process started"
run_in "$P" env CLAUDE_CODE_SESSION_ID="$U2" "$SMINOS" chat
assert_contains "$OUT" "devcloud on vm: lagging" "in U2's next sminos chat"

echo
if [ "$FAILURES" -eq 0 ]; then echo "test-notice-machines: all $PASSES assertions passed"; else
  echo "test-notice-machines: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"; exit 1; fi
