#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# Declared channels across three machines (CH1 of
# docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md; its plan,
# docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, M6 and the proof
# map's A7): alpha, beta and gamma, each a real sminos home with its daemon
# and its endpoint_standin.py serving `channels`, joined by rl10-machines.sh.
# The org's directory each is given is built from the stand-ins' `known`
# (rl10_known_directory), so a machine follows a channel because another
# holds it, as on the fleet. A thread on alpha creates the channel; a thread
# on beta, once beta follows it, adds itself: the stand-ins of alpha and beta
# list the channel in `known`, gamma's (which follows it) does not. beta's
# member removed withdraws beta alone; its thread ended and back in the
# channel makes beta hold it again; the last member removed leaves no
# machine holding it. A removal retires no one. The checker (channel_wire.py)
# passes over the three stand-ins' frames and the three stores, and no
# session's turn is started.
# Requests across machines (M7): a thread on alpha asks for beta's, beta's
# daemon asks its endpoint (`reach?`) and carries the request out on its word;
# at the requester each outcome is read where it can be known: refused with
# its reason, applied with the roster on both machines, pending on a machine
# whose endpoint never answers, refused as not reachable where the hub
# withheld it, and nothing once a request relayed late has expired, which its
# target's machine never carries out. Then the scene, CH1's acceptance (the
# plan's Concrete Steps, "M8, the acceptance"), on three fresh machines;
# `--scene` runs it alone, `--show` prints each of its commands with what it
# printed.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; the sessions are `sleep`s with engine records the suite writes;
# nothing listens beyond Unix sockets there.
# run-sminos-tests.sh runs this file in its `channels` part.
set -euo pipefail

SCENE_ONLY=0
SHOW=0
for arg in "$@"; do
  case $arg in
    --scene) SCENE_ONLY=1 ;;   # the scene alone (CH1's acceptance)
    --show) SHOW=1 ;;          # each of the scene's commands printed with what it printed
    *) echo "usage: $0 [--scene] [--show]" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(cd "$(mktemp -d /tmp/smm.XXXXXX)" && pwd -P)"
PIDS=()
cleanup() {
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

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
unset MAWS_USER_DATA SMINOS_RL10 CLAUDE_CONFIG_DIR
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
as() { # dir host — one machine: its HOME, its SMINOS_HOME, its host name
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}
# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_STATE/calls"
case "${1:-}" in
  agents) echo "[]"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

live_pid() { sleep 600 & LIVE_PID=$!; PIDS+=("$LIVE_PID"); }
session_record() { # name session pid cwd — an engine record for a running interactive session
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
    "$3" "$2" "$1" "$4" > "$HOME/.claude/sessions/$1.json"
}
start_daemon() { "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & PIDS+=("$!"); }
set_ep() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$1" set "$2" >/dev/null; }   # ep-dir JSON
relay_until() { # command... — one relay among the stand-ins in EPS between each look, until it holds (30 s)
  local end=$((SECONDS + 30))
  until "$@"; do
    [ "$SECONDS" -ge "$end" ] && return 1
    # shellcheck disable=SC2086
    rl10_relay $EPS || true
    sleep 0.1
  done
}
shows() { # dir session channel text — the channel's `show`, run there as the session, prints the text
  local out
  out="$(cd "$1" && env CLAUDE_CODE_SESSION_ID="$2" "$SMINOS" channel show "$3" 2>&1)" || true
  grep -Fq -- "$4" <<<"$out"
}
channel_id() { # name → this machine's channel of that name
  python3 - "$1" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
print(" ".join(c.id for c in sminos.known_channels() if c.name == sys.argv[1]))
PY
}
asked_of() { # ep-dir request-id → how many `reach?` the stand-in took about the request
  rl10_q "$1" "len([f for c, f in F if f.get('t') == 'reach?' and f.get('event', {}).get('id') == '$2'])"
}
request_id() { # channel-id writer-session thread-session → the id of the writer's last request for the session
  python3 - "$SMINOS_HOME/projects/$1/log" "$2" "$3" <<'PY'
import glob, json, os, sys
ids = [e["id"] for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.%s.jsonl" % sys.argv[2])))
       for e in map(json.loads, open(p)) if e.get("kind") == "channel-request" and e.get("session") == sys.argv[3]]
print(ids[-1] if ids else "")
PY
}
held_set() { # session → the channels of the record whose current session it is, as JSON
  python3 - "$1" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_threads
t = sminos_threads.current_record(sys.argv[1])
print(json.dumps(t.get("channels") if t else None))
PY
}
request_state() { # request-id — of the JSON `channel show` printed in OUT, [(state, reason, machine)] of the request
  python3 -c 'import json, sys
d = json.load(sys.stdin)
print([(r["state"], r["reason"], r["machine"]) for r in d["requests"] if r["id"] == sys.argv[1]])' "$1" <<<"$OUT"
}
shown() { # dir session channel python-expression — the expression over the channel's `show --json` there (d)
  local out
  out="$(cd "$1" && env CLAUDE_CODE_SESSION_ID="$2" "$SMINOS" channel show "$3" --json 2>/dev/null)" || true
  python3 -c 'import json, sys
try:
    d = json.loads(sys.stdin.read())
except ValueError:
    d = {"members": [], "requests": [], "pool": []}
def state(rid):
    return [(r["state"], r["reason"], r["machine"]) for r in d["requests"] if r["id"] == rid]
def members():
    return " ".join(sorted(m["session"][:8] for m in d["members"]))
print(eval(sys.argv[1]))' "$4" <<<"$out"
}
shown_is() { [ "$(shown "$1" "$2" "$3" "$4")" = "$5" ]; }   # dir session channel expression expected
on_beta() { (on b beta; "$@"); }
held_is() { [ "$(held_set "$1")" = "$2" ]; }   # session JSON
no_launch() { # dir... — no session's turn was started on those machines (the engine stub's calls)
  local n=0 m
  for m in "$@"; do n=$((n + $( (cat "$T/$m/stub/calls" 2>/dev/null || true) | grep -c -e resume -e '--bg' || true))); done
  [ "$n" -eq 0 ]
}
in_session() { local sid=$1; shift; env CLAUDE_CODE_SESSION_ID="$sid" "$@"; }
known() { rl10_q "$1" "'$2' in d['known']"; }   # ep-dir id → true | false
knows() { [ "$(known "$1" "$2")" = "$3" ]; }
follows() { # ep-dir id → the follow of the live connection's last hello of it: True | False | none
  python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$1" opened \
    | python3 -c 'import json, sys; o = json.load(sys.stdin)["projects"].get(sys.argv[1]); print(o["follow"] if o else "none")' "$2"
}
follows_as() { [ "$(follows "$1" "$2")" = "$3" ]; }
registered() { # id → whether this machine registered the log
  python3 - "$1" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
print("yes" if sminos.known_project(sys.argv[1]) is not None else "no")
PY
}
is_registered() { [ "$(registered "$1")" = yes ]; }
on() { # dir host → the machine the commands after it run on
  rl10_as "$1" "$2"
}

APP=7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d
WEB=1b2c3d4e-5f60-4718-8293-a4b5c6d7e8f9
OPS=2c3d4e5f-6071-4829-93a4-b5c6d7e8f901
SA=6a000001-0000-4000-8000-0000000000a1
SB=6b000001-0000-4000-8000-0000000000b1
SG=6c000001-0000-4000-8000-0000000000c1
directory() { # project-id name ... → the org's directory naming those projects and the three machines
  python3 - "$@" <<'PY'
import json, sys
a = sys.argv[1:]
print(json.dumps({"projects": [{"id": a[i], "name": a[i + 1], "kind": "hub", "retired": False}
                               for i in range(0, len(a), 2)],
                  "machines": [{"name": n, "online": False} for n in ("alpha", "beta", "gamma")]}))
PY
}
DIR="$(directory "$APP" app "$WEB" web "$OPS" ops)"
# `reach` too, so a request from another machine is asked about (CH1's M7: the endpoint's word).
SERVE="\"capabilities\": [\"channels\", \"reach\"], \"org\": $DIR"
TTL=3   # gamma's daemon holds a request this many seconds, so one relayed late is expired there (M7)

caps_kept() { # this machine's kept welcome lists channels
  python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_audience
sys.exit(0 if sminos_audience.advertised("channels") else 1)' 2>/dev/null
}
# ------------------------------------------------------------ the scene (CH1's acceptance, M8's step: Concrete Steps)
# Three fresh machines, alpha, beta and gamma, each a sminos home with its daemon and a stand-in that lists
# `channels` (and `reach`, so beta is asked about a request from alpha, and says deliver). On alpha a live thread
# its human opened, A (alder), and a stopped spawned thread, S (sable); on beta a stopped thread its human opened,
# B (birch), in another project; on gamma no thread. A pass is one relay between the stand-ins and one
# `sminos daemon tick` on each machine (the org's directory built again from the stand-ins' `known` first, as
# the fleet keeps it), then relays until what the step expects is there. With --show each command is printed
# with what it printed.
scene_cmd() { # label dir session|- args... — sminos run there (as the session), OUT and RC; printed with --show
  local label=$1 dir=$2 sid=$3
  shift 3
  if [ "$sid" = - ]; then run_in "$dir" "$SMINOS" "$@"; else run_in "$dir" in_session "$sid" "$SMINOS" "$@"; fi
  if [ "$SHOW" = 1 ]; then
    printf '\n  [%s] $ sminos %s\n' "$label" "$*"
    [ -n "$OUT" ] && sed 's/^/    /' <<<"$OUT"
    printf '    (exit %s)\n' "$RC"
  fi
}
scene_pass() { # command... — a pass, then relays until the command holds (30 s)
  [ "$SHOW" = 1 ] && printf '\n  -- a pass: one relay between the stand-ins, one daemon tick on each machine\n'
  rl10_known_directory "$SDIR" $EPS >/dev/null
  # shellcheck disable=SC2086
  rl10_relay $EPS || true
  local m
  for m in "sa alpha" "sb beta" "sc gamma"; do
    # shellcheck disable=SC2086
    (on $m; "$SMINOS" daemon tick >/dev/null 2>&1) || true
  done
  relay_until "$@"
}
section_rows() { # the rows of OUT's `# desk-integration` section
  awk '/^# desk-integration/ { f = 1; next } f && /^  / { print; next } f { exit }' <<<"$OUT"
}
logs_sum() { # every log file of this machine, and what it holds
  (find "$SMINOS_HOME/projects" -path '*/log/*' -type f | sort | while read -r f; do printf '%s ' "$f"; shasum < "$f"; done) |
    shasum | cut -c1-40
}

scene() {
  echo "the scene (CH1's acceptance):"
  SA=6a000002-0000-4000-8000-0000000000a2
  SS=6a000003-0000-4000-8000-0000000000a3
  SB=6b000002-0000-4000-8000-0000000000b2
  SDIR="$(directory "$APP" app "$WEB" web)"
  local serve="\"capabilities\": [\"channels\", \"reach\"], \"org\": $SDIR"
  on sa alpha
  rl10_cut_over
  EPA=$EP
  mkdir -p "$T/sa/app"
  printf '{"project": "%s", "name": "app", "hub": {"org": "org-1"}}\n' "$APP" > "$T/sa/app/.smns"
  live_pid
  session_record alder "$SA" "$LIVE_PID" "$T/sa/app"
  run_in "$T/sa/app" "$SMINOS" seat add crew sable --session "$SS"
  live_pid
  local s_pid=$LIVE_PID
  session_record sable "$SS" "$s_pid" "$T/sa/app"
  "$SMINOS" daemon tick >/dev/null 2>&1 || true
  kill "$s_pid" 2>/dev/null || true
  rm -f "$HOME/.claude/sessions/sable.json"
  rl10_serve "$serve"
  start_daemon
  on sb beta
  rl10_cut_over
  EPB=$EP
  mkdir -p "$T/sb/web"
  printf '{"project": "%s", "name": "web", "hub": {"org": "org-1"}}\n' "$WEB" > "$T/sb/web/.smns"
  live_pid
  local b_pid=$LIVE_PID
  session_record birch "$SB" "$b_pid" "$T/sb/web"
  "$SMINOS" daemon tick >/dev/null 2>&1 || true
  kill "$b_pid" 2>/dev/null || true
  rm -f "$HOME/.claude/sessions/birch.json"
  rl10_serve "$serve, \"reach_verdict\": \"deliver\""
  start_daemon
  on sc gamma
  rl10_cut_over
  EPC=$EP
  rl10_serve "$serve"
  start_daemon
  EPS="$EPA $EPB $EPC"
  for m in "sa alpha" "sb beta" "sc gamma"; do
    # shellcheck disable=SC2086
    on $m
    until_true caps_kept || true
  done
  on sa alpha
  sees_b() { (cd "$T/sa/app" && "$SMINOS" list --org 2>/dev/null) | grep -q "birch"; }
  relay_until sees_b || true
  assert_equals "$(sees_b && echo yes)" yes "alpha reads beta's thread B, relayed"

  echo " 1. create, and add S and B:"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel create desk-integration
  local desk
  desk="$(channel_id desk-integration)"
  assert_rc 0 "$RC" "A creates the channel"
  assert_equals "$OUT" "created channel desk-integration ($desk) with alder#${SA:0:8}" \
    "one line naming the channel, its id and A"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel add desk-integration sable "birch#${SB:0:8}"
  assert_rc 0 "$RC" "A adds S and B"
  assert_contains "$OUT" "sable#${SS:0:8}: in desk-integration" "S is reported in the channel"
  assert_contains "$OUT" "birch#${SB:0:8}: asked; pending on beta" "B as asked and pending on beta"
  no_launch sa sb sc && pass "the test engine has recorded no launch" || fail "the test engine has recorded no launch"

  echo " 2. after a pass, the roster, the request and the pool:"
  scene_pass shown_is "$T/sa/app" "$SA" desk-integration "members()" "${SA:0:8} ${SS:0:8} ${SB:0:8}" || true
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel show desk-integration
  assert_equals "$(sed -n '/^members/,/^requests/p' <<<"$OUT" | grep -c -e "alder \\[${SA:0:8}\\].*  app" -e "sable \\[${SS:0:8}\\].*  app" -e "birch \\[${SB:0:8}\\].*  web" || true)" 3 \
    "A, S and B under members, each with its own project"
  assert_contains "$(grep "birch" <<<"$(sed -n '/^requests/,/^pool/p' <<<"$OUT")")" "applied" "the request for B as applied"
  assert_contains "$OUT" "alpha  1 live, 1 stopped" "the pool: alpha with one live and one stopped"
  assert_contains "$OUT" "beta  0 live, 1 stopped" "and beta with one stopped"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" list
  assert_equals "$(section_rows | grep -c -e alder -e sable -e birch || true)" 3 \
    "sminos list as A: its project, then # desk-integration with the three rows"
  assert_equals "$(head -1 <<<"$OUT" | grep -c '^#' || true)" 0 "its project first"
  on sb beta
  relay_until shown_is "$T/sb/web" "$SB" desk-integration "members()" "${SA:0:8} ${SS:0:8} ${SB:0:8}" || true
  scene_cmd "beta, as B" "$T/sb/web" "$SB" list
  assert_equals "$(section_rows | grep -c -e alder -e sable -e birch || true)" 3 \
    "sminos list as B: its project, then # desk-integration with the three rows"
  no_launch sa sb sc && pass "B and S placed with no launch" || fail "B and S placed with no launch"

  echo " 3. who holds it:"
  assert_equals "$(known "$EPA" "$desk") $(known "$EPB" "$desk") $(known "$EPC" "$desk")" "true true false" \
    "the stand-ins of alpha and beta list the channel in known, gamma's does not"
  on sc gamma
  gamma_sees() { (cd "$T/sc" && "$SMINOS" list --org 2>/dev/null) | sed -n '/^# desk-integration/,$p' | grep -c -e alder -e sable -e birch | grep -q 3; }
  relay_until gamma_sees || true
  scene_cmd "gamma" "$T/sc" - list --org
  assert_equals "$(grep '^#' <<<"$OUT" | tail -1)" "# desk-integration" "sminos list --org on gamma ends with the section"

  echo " 4. nothing is said into it:"
  on sa alpha
  local before refused
  before="$(logs_sum)"
  refused="is a channel, and speaking in a channel is not available in this version of sminos yet: nothing was recorded"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" say --in desk-integration "x"
  assert_rc 1 "$RC" "say --in, from A: refused"
  assert_contains "$OUT" "desk-integration $refused" "in §8's sentence"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" say "@desk-integration/birch x"
  assert_rc 1 "$RC" "a tag qualified by the channel: refused"
  assert_contains "$OUT" "$refused" "in §8's sentence"
  scene_cmd "alpha, a terminal" "$T/sa/app" - say --in desk-integration "x"
  assert_rc 1 "$RC" "say --in from a terminal: refused"
  assert_contains "$OUT" "$refused" "in §8's sentence"
  assert_equals "$(logs_sum)" "$before" "no file of any log has changed"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" join desk-integration
  assert_rc 1 "$RC" "join: refused"
  assert_contains "$OUT" "sminos channel add" "naming sminos channel add"

  echo " 5. B removed:"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel remove desk-integration "birch#${SB:0:8}"
  assert_contains "$OUT" "birch#${SB:0:8}: asked; pending on beta" "asked of beta"
  b_out() { shown_is "$T/sa/app" "$SA" desk-integration "members()" "${SA:0:8} ${SS:0:8}" && knows "$EPB" "$desk" false; }
  scene_pass b_out || true
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel show desk-integration
  assert_equals "$(sed -n '/^members/,/^requests/p' <<<"$OUT" | grep -c "birch" || true)" 0 "B is out of the roster"
  on sb beta
  scene_cmd "beta" "$T/sb/web" - list --stopped
  assert_contains "$(grep birch <<<"$OUT")" "stopped" "sminos list --stopped on beta still shows B stopped in its project"
  assert_equals "$(known "$EPB" "$desk") $(known "$EPA" "$desk")" "false true" \
    "beta's known no longer lists the channel while alpha's does"

  echo " 6. the last members leave:"
  on sa alpha
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel remove desk-integration sable
  assert_contains "$OUT" "sable#${SS:0:8}: out of desk-integration" "S out"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel remove desk-integration
  assert_contains "$OUT" "alder#${SA:0:8}: out of desk-integration" "A out"
  none_known_s() { [ "$(known "$EPA" "$desk")$(known "$EPB" "$desk")$(known "$EPC" "$desk")" = falsefalsefalse ]; }
  scene_pass none_known_s || true
  assert_equals "$(known "$EPA" "$desk") $(known "$EPB" "$desk") $(known "$EPC" "$desk")" "false false false" \
    "no stand-in lists the channel in known"
  on sc gamma
  gamma_none() { ! (cd "$T/sc" && "$SMINOS" list --org 2>/dev/null) | grep -q '^# desk-integration'; }
  relay_until gamma_none || true
  scene_cmd "gamma" "$T/sc" - list --org
  assert_equals "$(grep -c '^# desk-integration' <<<"$OUT" || true)" 0 "sminos list --org on gamma shows no section for it"

  echo " 7. nothing published or written under it:"
  local checked
  checked="$(python3 -B - "$SCRIPT_DIR" "$desk" "$EPA" "$EPB" "$EPC" "$T/sa/s" "$T/sb/s" "$T/sc/s" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import channel_wire, endpoint_standin
ids, eps, homes = [sys.argv[2]], sys.argv[3:6], sys.argv[6:9]
out = []
for ep, home, name in zip(eps, homes, ("alpha", "beta", "gamma")):
    state = json.loads(endpoint_standin.ctl_call(ep, "state", {}))
    frames = [(r["conn"], r["frame"]) for r in state["received"]]
    welcomed = {w["conn"] for w in state["welcomes"] if "channels" in w["welcome"]["capabilities"]}
    out += ["%s: %s" % (name, b) for b in channel_wire.published(frames, ids, {}, welcomed=welcomed)]
    out += ["%s: %s" % (name, b) for b in channel_wire.written(home, ids, name, {})]   # delivery records too
print("\n".join(out) or "clean")
PY
)"
  assert_equals "$checked" clean "the checker passes over the three stand-ins and the three stores, no delivery record under the channel"
  no_launch sa sb sc && pass "and no launch was recorded" || fail "and no launch was recorded"
}

if [ "$SCENE_ONLY" = 0 ]; then
on a alpha
rl10_cut_over
EPA=$EP
mkdir -p "$T/a/app"
printf '{"project": "%s", "name": "app", "hub": {"org": "org-1"}}\n' "$APP" > "$T/a/app/.smns"
live_pid
session_record worker "$SA" "$LIVE_PID" "$T/a/app"
rl10_serve "$SERVE"
start_daemon

on b beta
rl10_cut_over
EPB=$EP
mkdir -p "$T/b/web"
printf '{"project": "%s", "name": "web", "hub": {"org": "org-1"}}\n' "$WEB" > "$T/b/web/.smns"
live_pid
B_PID=$LIVE_PID
session_record helper "$SB" "$LIVE_PID" "$T/b/web"
rl10_serve "$SERVE"
start_daemon

on c gamma
rl10_cut_over
EPC=$EP
EPS="$EPA $EPB $EPC"
mkdir -p "$T/c/ops"
printf '{"project": "%s", "name": "ops", "hub": {"org": "org-1"}}\n' "$OPS" > "$T/c/ops/.smns"
live_pid
session_record gauge "$SG" "$LIVE_PID" "$T/c/ops"
rl10_serve "$SERVE"
SMINOS_CHANNEL_REQUEST_TTL=$TTL start_daemon

for m in "a alpha" "b beta" "c gamma"; do
  # shellcheck disable=SC2086
  on $m
  until_true caps_kept || true
done

echo "a channel two machines hold and a third follows:"
on a alpha
until_true caps_kept || true
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel create desk-integration
assert_rc 0 "$RC" "a thread on alpha creates the channel"
DESK="$(python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
print(" ".join(c.id for c in sminos.known_channels() if c.name == "desk-integration"))
PY
)"
assert_contains "$OUT" "created channel desk-integration ($DESK) with worker#${SA:0:8}" "with itself in it"
until_true knows "$EPA" "$DESK" true || true
assert_equals "$(known "$EPA" "$DESK")" true "alpha's stand-in lists the channel in known"
rl10_known_directory "$DIR" "$EPA" "$EPB" "$EPC" >/dev/null
on b beta
until_true is_registered "$DESK" || true
assert_equals "$(registered "$DESK")" yes "beta registers the channel from the org's directory"
until_true follows_as "$EPB" "$DESK" True || true
assert_equals "$(follows "$EPB" "$DESK")" True "and follows its log, no thread there being in it"
run_in "$T/b/web" in_session "$SB" "$SMINOS" channel add desk-integration
assert_rc 0 "$RC" "a thread on beta adds itself"
assert_contains "$OUT" "helper#${SB:0:8}: in desk-integration" "placed when the command returns"
until_true knows "$EPB" "$DESK" true || true
assert_equals "$(known "$EPB" "$DESK")" true "beta's stand-in lists it in known"
assert_equals "$(follows "$EPB" "$DESK")" False "beta opens its log without follow"
on c gamma
until_true follows_as "$EPC" "$DESK" True || true
assert_equals "$(follows "$EPC" "$DESK")" True "gamma follows the channel's log"
assert_equals "$(known "$EPC" "$DESK")" false "and gamma's stand-in does not list it in known"
assert_equals "$(known "$EPA" "$DESK")" true "alpha's still does"
member_channels() { # ep-dir session → the channels of the session's last member frame on the live connection
  rl10_q "$1" "next((f.get('channels') for c, f in reversed(F) if c == d['current'] and f.get('t') == 'member' and f.get('session') == '$2'), 'none')"
}
assert_equals "$(member_channels "$EPB" "$SB")" "[\"$DESK\"]" "beta's member frame for its thread carries the channel"
assert_equals "$(rl10_q "$EPB" "next(f['project'] for c, f in reversed(F) if f.get('t') == 'member' and f.get('session') == '$SB')")" "\"$WEB\"" "under its own project"

echo "a removal withdraws its machine alone, and a return holds it again:"
on b beta
run_in "$T/b/web" in_session "$SB" "$SMINOS" channel remove desk-integration
assert_rc 0 "$RC" "beta's thread removes itself"
# Either input alone clears known (the tick publishes members before it hellos again): wait for both.
removed() { knows "$EPB" "$DESK" false && follows_as "$EPB" "$DESK" True && [ "$(member_channels "$EPB" "$SB")" = null ]; }
until_true removed || true
assert_equals "$(known "$EPB" "$DESK")" false "beta's stand-in no longer lists the channel"
assert_equals "$(follows "$EPB" "$DESK")" True "beta follows its log again"
assert_equals "$(member_channels "$EPB" "$SB")" "null" "its member frame carries no channels key"
assert_equals "$(known "$EPA" "$DESK")" true "alpha's still lists it"
run_in "$T/b/web" "$SMINOS" list web --json
assert_contains "$OUT" "\"session\": \"$SB\"" "the removal retired no one"
run_in "$T/b/web" in_session "$SB" "$SMINOS" channel add desk-integration
assert_rc 0 "$RC" "and adds itself again"
until_true knows "$EPB" "$DESK" true || true
assert_equals "$(known "$EPB" "$DESK")" true "beta holds the channel again"
# Its thread ends (its process gone, retired) and returns (its session running again).
kill "$B_PID" 2>/dev/null || true
rm -f "$HOME/.claude/sessions/helper.json"
run_in "$T/b/web" "$SMINOS" retire "helper#${SB:0:8}"
assert_rc 0 "$RC" "beta's thread is retired: it has ended"
until_true knows "$EPB" "$DESK" false || true
assert_equals "$(known "$EPB" "$DESK")" false "an ended member holds nothing: beta's stand-in no longer lists the channel"
live_pid
session_record helper "$SB" "$LIVE_PID" "$T/b/web"
"$SMINOS" list web >/dev/null 2>&1 || true
until_true knows "$EPB" "$DESK" true || true
assert_equals "$(known "$EPB" "$DESK")" true "back, in the channels it was in: beta holds it again"
assert_equals "$(member_channels "$EPB" "$SB")" "[\"$DESK\"]" "its member frame carries the channel again"

echo "the last member leaves:"
run_in "$T/b/web" in_session "$SB" "$SMINOS" channel remove desk-integration
assert_rc 0 "$RC" "beta's thread removes itself"
on a alpha
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel remove desk-integration
assert_rc 0 "$RC" "and alpha's, the last member"
none_known() { [ "$(known "$EPA" "$DESK")$(known "$EPB" "$DESK")$(known "$EPC" "$DESK")" = falsefalsefalse ]; }
until_true none_known || true
assert_equals "$(known "$EPA" "$DESK") $(known "$EPB" "$DESK") $(known "$EPC" "$DESK")" "false false false" \
  "no stand-in lists the channel in known"
assert_equals "$(rl10_known_directory "$DIR" "$EPA" "$EPB" "$EPC" | grep -c "$DESK" || true)" 0 \
  "and the directory built from them no longer lists it"

echo "requests across machines: the endpoint's word, and what the requester is told:"
on a alpha
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel create desk-requests
assert_rc 0 "$RC" "a thread on alpha creates a second channel"
REQ="$(channel_id desk-requests)"
until_true knows "$EPA" "$REQ" true || true
rl10_known_directory "$DIR" "$EPA" "$EPB" "$EPC" >/dev/null
for m in "b beta" "c gamma"; do
  # shellcheck disable=SC2086
  on $m
  until_true is_registered "$REQ" || true
done
on a alpha
sees() { (cd "$T/a/app" && "$SMINOS" list --org 2>/dev/null) | grep -q -e "${1:0:8}"; }
relay_until sees "$SB" || true
relay_until sees "$SG" || true
assert_equals "$(sees "$SB" && sees "$SG" && echo yes)" yes "alpha reads beta's and gamma's threads, relayed"
set_ep "$EPB" '{"reach_verdict": "refuse"}'
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel add desk-requests "helper#${SB:0:8}"
assert_rc 0 "$RC" "a thread on alpha asks for beta's thread"
assert_contains "$OUT" "helper#${SB:0:8}: asked; pending on beta: its machine carries it out when its daemon reads the request" \
  "it is asked, and pending on beta"
R1="$(request_id "$REQ" "$SA" "$SB")"
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel show desk-requests
assert_contains "$OUT" "pending on beta since 20" "channel show reads it pending on beta, and since when"
relay_until shows "$T/a/app" "$SA" desk-requests "refused: its machine does not let you message it" || true
assert_equals "$(shown "$T/a/app" "$SA" desk-requests "state('$R1')")" "[('refused', 'not-reachable', None)]" \
  "a refusal its endpoint gave is read at the requester, with its reason"
assert_equals "$(asked_of "$EPB" "$R1")" 1 "beta asked its endpoint once"
on b beta
assert_equals "$(held_set "$SB")" "[]" "and beta's thread is not in the channel"
on a alpha
set_ep "$EPB" '{"reach_verdict": "deliver"}'
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel add desk-requests "helper#${SB:0:8}"
assert_contains "$OUT" "asked; pending on beta" "asked again"
R2="$(request_id "$REQ" "$SA" "$SB")"
relay_until on_beta held_is "$SB" "[\"$REQ\"]" || true
on b beta
assert_equals "$(held_set "$SB")" "[\"$REQ\"]" "carried out on beta when its endpoint said deliver"
on a alpha
relay_until shown_is "$T/a/app" "$SA" desk-requests "state('$R2')" "[('applied', None, None)]" || true
assert_equals "$(shown "$T/a/app" "$SA" desk-requests "state('$R2')")" "[('applied', None, None)]" \
  "the request reads applied at the requester"
relay_until shown_is "$T/a/app" "$SA" desk-requests "members()" "${SA:0:8} ${SB:0:8}" || true
assert_equals "$(shown "$T/a/app" "$SA" desk-requests "members()")" "${SA:0:8} ${SB:0:8}" "the roster on alpha holds both"
on b beta
relay_until shown_is "$T/b/web" "$SB" desk-requests "members()" "${SA:0:8} ${SB:0:8}" || true
assert_equals "$(shown "$T/b/web" "$SB" desk-requests "members()")" "${SA:0:8} ${SB:0:8}" "and so does the roster on beta"
on a alpha
set_ep "$EPB" '{"reach_verdict": null}'
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel remove desk-requests "helper#${SB:0:8}"
R3="$(request_id "$REQ" "$SA" "$SB")"
asked_r3() { [ "$(asked_of "$EPB" "$R3")" -ge 1 ]; }
relay_until asked_r3 || true
assert_equals "$(asked_of "$EPB" "$R3")" 1 "beta asks its endpoint, which never answers"
rl10_relay $EPS || true
assert_equals "$(shown "$T/a/app" "$SA" desk-requests "state('$R3')")" "[('pending', None, 'beta')]" \
  "a machine that never answers: pending on beta"
on b beta
assert_equals "$(held_set "$SB")" "[\"$REQ\"]" "nothing carried out meanwhile"
on a alpha
# A request relayed later than gamma's TTL: expired there, never asked about or carried out.
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel add desk-requests "gauge#${SG:0:8}"
assert_contains "$OUT" "gauge#${SG:0:8}: asked; pending on gamma" "a thread of gamma asked for"
R5="$(request_id "$REQ" "$SA" "$SG")"
sleep $((TTL + 1))
on c gamma
has_r5() { [ -n "$(request_id "$REQ" "$SA" "$SG")" ]; }
relay_until has_r5 || true
assert_equals "$(request_id "$REQ" "$SA" "$SG")" "$R5" "gamma imports it, late"
SMINOS_CHANNEL_REQUEST_TTL=$TTL "$SMINOS" daemon tick >/dev/null 2>&1 || true
sleep 1.5   # a pass of gamma's uplink after the import
assert_equals "$(asked_of "$EPC" "$R5")" 0 "an expired request is never asked about"
assert_equals "$(held_set "$SG")" "[]" "nor carried out"
on a alpha
assert_equals "$(shown "$T/a/app" "$SA" desk-requests "state('$R5')")" "[('pending', None, 'gamma')]" \
  "the requester reads it pending until its lifetime is out"
OUT="$(cd "$T/a/app" && SMINOS_CHANNEL_REQUEST_TTL=$TTL CLAUDE_CODE_SESSION_ID="$SA" "$SMINOS" channel show desk-requests --json 2>&1)"
assert_equals "$(request_state "$R5")" "[]" "and reads nothing after it"
# Last of this writer's requests: the stand-in relays no tombstone, so another machine imports none past it.
set_ep "$EPA" "{\"withhold\": {\"project\": \"$REQ\", \"kind\": \"channel-request\"}}"
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel add desk-requests "helper#${SB:0:8}"
R4="$(request_id "$REQ" "$SA" "$SB")"
until_true shows "$T/a/app" "$SA" desk-requests "refused: not reachable (the hub withheld it)" || true
run_in "$T/a/app" in_session "$SA" "$SMINOS" channel show desk-requests
assert_contains "$OUT" "refused: not reachable (the hub withheld it)" "a request the hub withheld reads refused, not reachable"
assert_equals "$(shown "$T/a/app" "$SA" desk-requests "state('$R4')")" "[('withheld', 'not-reachable', None)]" \
  "and so in JSON"
set_ep "$EPA" '{"withhold": null}'
rl10_relay $EPS || true
assert_equals "$(asked_of "$EPB" "$R4")" 0 "it never reached beta"
no_launch a b c && pass "no turn of any session was started" || fail "no turn of any session was started"

echo "nothing is published or written under the channel:"
# A fresh store on every machine: the baseline is empty, so nothing this code wrote under the channel,
# its creation included, is excused (only a store an older copy wrote into has one: test_channels_wire.py).
CHECKED="$(python3 -B - "$SCRIPT_DIR" "$DESK $REQ" "$EPA" "$EPB" "$EPC" "$T/a/s" "$T/b/s" "$T/c/s" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import channel_wire, endpoint_standin
ids, eps, homes = sys.argv[2].split(), sys.argv[3:6], sys.argv[6:9]
out = []
for ep, home, name in zip(eps, homes, ("alpha", "beta", "gamma")):
    state = json.loads(endpoint_standin.ctl_call(ep, "state", {}))
    frames = [(r["conn"], r["frame"]) for r in state["received"]]
    welcomed = {w["conn"] for w in state["welcomes"] if "channels" in w["welcome"]["capabilities"]}
    out += ["%s: %s" % (name, b) for b in channel_wire.published(frames, ids, {}, welcomed=welcomed)]
    out += ["%s: %s" % (name, b) for b in channel_wire.written(home, ids, name, {})]
print("\n".join(out) or "clean")
PY
)"
assert_equals "$CHECKED" clean "the checker passes over the three stand-ins and the three stores"
launched=0
for m in a b c; do
  launched=$((launched + $( (cat "$T/$m/stub/calls" 2>/dev/null || true) | grep -c -e resume -e '--bg' || true)))
done
assert_equals "$launched" 0 "no session's turn was started"
# The main part's machines stopped before the scene's are made.
for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
PIDS=()
fi

scene

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-channels-machines.sh: $PASSES passed, 0 failed"
else
  echo "test-channels-machines.sh: $PASSES passed, $FAILURES failed"
  exit 1
fi
