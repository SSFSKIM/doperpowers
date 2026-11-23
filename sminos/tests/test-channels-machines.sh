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
# The speaking scene (CH2's M6; M11's acceptance, which M8 extends with the
# lead): three fresh machines whose `claude` is the test engine
# (wake_engine.py): a message said into a channel on alpha goes up under the
# channel's id, beta's uplink asks its endpoint (`reach?`) and keeps the word,
# and beta's daemon carries it out, waking its stopped member; the reply by the
# frame's line returns the same way; `@all`, an untagged note and a tag to a
# stopped thread on its own machine; a thread in no channel says into it and is
# answered directly; a member that left is sent to directly and one that came
# back through the channel; a notice from a machine of the channel's
# environment; the lead (CH2's M8), named at alpha's terminal with a typed yes
# on a pty, its person's untagged post asked about (`words?`) and handed to
# the lead as a person's words (the engine supervisor's reply, a stand-in of
# it serving alpha's config dir), a notice tagged to it an inbox frame
# whatever the word, and the verb refused to a session; and the checker over
# the three stand-ins and stores. Then M6's
# cases on the same machines: a writer on a machine that holds no member (its
# member frame first, its log opened with `follow`), what beta held at a
# removal and a return, and the outcomes the
# checker reads after beta uploaded again. `--speak` runs the scene alone.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub (the test engine in the speaking scene); the sessions are `sleep`s with engine records the suite writes;
# nothing listens beyond Unix sockets there.
# run-sminos-tests.sh runs this file in its `channels` part.
set -euo pipefail

SCENE_ONLY=0
SPEAK_ONLY=0
SHOW=0
for arg in "$@"; do
  case $arg in
    --scene) SCENE_ONLY=1 ;;   # the scene alone (CH1's acceptance)
    --speak) SPEAK_ONLY=1 ;;   # the speaking scene alone (CH2's, from M6)
    --show) SHOW=1 ;;          # each of the scene's commands printed with what it printed
    *) echo "usage: $0 [--scene] [--speak] [--show]" >&2; exit 2 ;;
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
  for st in "$T"/*/engine; do
    [ -d "$st" ] || continue
    python3 -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import wake_engine; wake_engine.stop_all(sys.argv[2])' \
      "$SCRIPT_DIR" "$st" 2>/dev/null || true
  done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "$T/" >/dev/null 2>&1 || break; sleep 0.05; done
  rm -rf "$T"
  if [ -n "${SUPDIR:-}" ]; then rm -rf "$SUPDIR"; fi   # the supervisor stand-in's, outside $T (where the engine's is)
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
checked_clean() { # "channel-id ..." "ep-dir home name" ... — the checker over each machine's stand-in and store
  python3 -B - "$SCRIPT_DIR" "$@" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import channel_wire, endpoint_standin
ids, out = sys.argv[2].split(), []
for machine in sys.argv[3:]:
    ep, home, name = machine.split()
    state = json.loads(endpoint_standin.ctl_call(ep, "state", {}))
    frames = [(r["conn"], r["frame"]) for r in state["received"]]
    welcomed = {w["conn"] for w in state["welcomes"] if "channels" in w["welcome"]["capabilities"]}
    # A fresh store on every machine: the baseline is empty, so nothing this code wrote under a channel, its
    # creation included, is excused (only a store an older copy wrote into has one: test_channels_wire.py).
    spoken = channel_wire.ALLOWED_SPOKEN   # what is said into a channel (CH2's M4) is allowed, in its shape
    out += ["%s: %s" % (name, b) for b in channel_wire.published(frames, ids, {}, spoken, welcomed=welcomed)]
    out += ["%s: %s" % (name, b) for b in channel_wire.written(home, ids, name, {}, spoken)]   # delivery records too
print("\n".join(out) or "clean")
PY
}
imported() { # channel-id request-id → whether this machine's copy of the channel's log holds the request
  python3 - "$SMINOS_HOME/projects/$1/log" "$2" <<'PY'
import glob, json, os, sys
print("yes" if any(e.get("id") == sys.argv[2] for p in glob.glob(os.path.join(sys.argv[1], "*.jsonl"))
                   for e in map(json.loads, open(p))) else "no")
PY
}
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
logs_but() { # channel-id — logs_sum over every log but that channel's
  (find "$SMINOS_HOME/projects" -path '*/log/*' -type f -not -path "*/projects/$1/*" | sort |
    while read -r f; do printf '%s ' "$f"; shasum < "$f"; done) | shasum | cut -c1-40
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
  assert_rc 0 "$RC" "channel show"
  assert_equals "$(sed -n '/^members/,/^requests/p' <<<"$OUT" | grep -c -e "alder \\[${SA:0:8}\\].*  app" -e "sable \\[${SS:0:8}\\].*  app" -e "birch \\[${SB:0:8}\\].*  web" || true)" 3 \
    "A, S and B under members, each with its own project"
  assert_contains "$(grep "birch" <<<"$(sed -n '/^requests/,/^pool/p' <<<"$OUT")")" "applied" "the request for B as applied"
  assert_contains "$(grep "sable \\[${SS:0:8}\\]" <<<"$OUT")" "seat         gone" \
    "S, a spawned seat with no conversation here, reads gone in the roster (its project's view's word)"
  assert_contains "$OUT" "alpha  1 live, 1 stopped" "the pool: alpha with one live and one stopped (S counted stopped)"
  assert_contains "$OUT" "beta  0 live, 1 stopped" "and beta with one stopped"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" list
  assert_rc 0 "$RC" "sminos list as A"
  assert_equals "$(head -1 <<<"$OUT")" "app" "its project's section first"
  assert_equals "$(section_rows | grep -c -e alder -e sable -e birch || true)" 3 \
    "sminos list as A: its project, then # desk-integration with the three rows"
  on sb beta
  relay_until shown_is "$T/sb/web" "$SB" desk-integration "members()" "${SA:0:8} ${SS:0:8} ${SB:0:8}" || true
  scene_cmd "beta, as B" "$T/sb/web" "$SB" list
  assert_rc 0 "$RC" "sminos list as B"
  assert_equals "$(head -2 <<<"$OUT")" "(no members in web)
+1 hidden (stopped, retired, gone) — sminos list --stopped shows stopped; --all shows all" \
    "its project first, as list prints it today: its rows are hidden"
  assert_equals "$(sed -n 3p <<<"$OUT")" "# desk-integration" "then the channel's section"
  assert_equals "$(section_rows | grep -c -e alder -e sable -e birch || true)" 3 "with the three rows"
  no_launch sa sb sc && pass "B and S placed with no launch" || fail "B and S placed with no launch"

  echo " 3. who holds it:"
  assert_equals "$(known "$EPA" "$desk") $(known "$EPB" "$desk") $(known "$EPC" "$desk")" "true true false" \
    "the stand-ins of alpha and beta list the channel in known, gamma's does not"
  on sc gamma
  gamma_sees() { (cd "$T/sc" && "$SMINOS" list --org 2>/dev/null) | sed -n '/^# desk-integration/,$p' | grep -c -e alder -e sable -e birch | grep -q 3; }
  relay_until gamma_sees || true
  scene_cmd "gamma" "$T/sc" - list --org
  assert_rc 0 "$RC" "sminos list --org on gamma"
  assert_equals "$(grep '^#' <<<"$OUT" | tail -1)" "# desk-integration" "ends with the section"

  echo " 4. said into it (CH2's M4), and what still opens no tag:"
  on sa alpha
  local before refused others
  before="$(logs_sum)"
  refused="opens no tag (a tag's qualifier takes no #): nothing was recorded"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" say "@desk-integration#${desk:0:8}/birch x"
  assert_rc 1 "$RC" "the unquoted name#short qualifier: refused"
  assert_contains "$OUT" "$refused" "it opens no tag"
  assert_equals "$(logs_sum)" "$before" "no file of any log has changed"
  others="$(logs_but "$desk")"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" say --in desk-integration "a note"
  assert_rc 0 "$RC" "say --in, untagged, from A: recorded"
  assert_contains "$OUT" "in desk-integration" "in the channel's log"
  scene_cmd "alpha, a terminal" "$T/sa/app" - say --in desk-integration "a person's note"
  assert_rc 0 "$RC" "say --in from a terminal: recorded"
  assert_equals "$(logs_but "$desk")" "$others" "of every log, the channel's alone changed"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" join desk-integration
  assert_rc 1 "$RC" "join: refused"
  assert_contains "$OUT" "sminos channel add" "naming sminos channel add"

  echo " 5. B removed:"
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel remove desk-integration "birch#${SB:0:8}"
  assert_contains "$OUT" "birch#${SB:0:8}: asked; pending on beta" "asked of beta"
  b_out() { shown_is "$T/sa/app" "$SA" desk-integration "members()" "${SA:0:8} ${SS:0:8}" && knows "$EPB" "$desk" false; }
  scene_pass b_out || true
  scene_cmd "alpha, as A" "$T/sa/app" "$SA" channel show desk-integration
  assert_rc 0 "$RC" "channel show"
  assert_equals "$(sed -n '/^members/,/^requests/p' <<<"$OUT" | grep -c "birch" || true)" 0 "B is out of the roster"
  on sb beta
  scene_cmd "beta" "$T/sb/web" - list --stopped
  assert_rc 0 "$RC" "sminos list --stopped on beta"
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
  gamma_none() { local out; out="$(cd "$T/sc" && "$SMINOS" list --org 2>/dev/null)" && ! grep -q '^# desk-integration' <<<"$out"; }
  relay_until gamma_none || true
  scene_cmd "gamma" "$T/sc" - list --org
  assert_rc 0 "$RC" "sminos list --org on gamma"
  assert_contains "$OUT" "alder [${SA:0:8}]" "which lists the org's threads"
  assert_equals "$(grep -c '^# desk-integration' <<<"$OUT" || true)" 0 "and shows no section for the channel"

  echo " 7. nothing published or written under it:"
  local checked
  checked="$(checked_clean "$desk" "$EPA $T/sa/s alpha" "$EPB $T/sb/s beta" "$EPC $T/sc/s gamma")"
  assert_equals "$checked" clean "the checker passes over the three stand-ins and the three stores, no delivery record under the channel"
  no_launch sa sb sc && pass "and no launch was recorded" || fail "and no launch was recorded"
}

# ------------------------------------------------------------ the speaking scene (CH2's M6, M11's acceptance; M8 adds the lead)
# Three fresh machines, alpha, beta and gamma, each a sminos home with its daemon, the test engine
# (wake_engine.py, whose launches and inputs are kept under the machine's engine/) and a stand-in that lists
# `channels` and `reach` and answers `reach?` deliver. On alpha a live thread its human opened, A (alder), a stopped
# spawned thread, S (sable), and a live thread in no channel, X (xeno); on beta a stopped thread its human opened,
# B (birch), in another project, last run in `auto`; on gamma no thread. A pass is the org's directory built again
# from the stand-ins' `known`, then relays between the stand-ins until what the step expects is there.
speak_machines() {
  mkdir -p "$T/engine-bin"
  printf '#!/usr/bin/env bash\nexec python3 -B "%s" "$@"\n' "$SCRIPT_DIR/wake_engine.py" > "$T/engine-bin/claude"
  chmod +x "$T/engine-bin/claude"
  export PATH="$T/engine-bin:$PATH"
  as() { # dir host — one machine: its HOME, its SMINOS_HOME, its engine's state, its host name
    export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" WAKE_ENGINE_STATE="$T/$1/engine" DAEMON_HOST="$2"
    mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME/daemon" "$WAKE_ENGINE_STATE"
  }
  SA=6a00000a-0000-4000-8000-0000000000aa SS=6a00000b-0000-4000-8000-0000000000ab
  SX=6a00000c-0000-4000-8000-0000000000ac SB=6b00000a-0000-4000-8000-0000000000ba
  SG=6c00000a-0000-4000-8000-0000000000ca
  SDIR="$(directory "$APP" app "$WEB" web "$OPS" ops)"
  local serve="\"capabilities\": [\"channels\", \"reach\"], \"reach_verdict\": \"deliver\", \"org\": $SDIR" m
  on pa alpha
  rl10_cut_over
  printf '{"ceiling": "auto"}\n' > "$SMINOS_HOME/daemon/policy.json"   # a wake in auto mode asks nothing
  EPA=$EP
  mkdir -p "$T/pa/app"
  printf '{"project": "%s", "name": "app", "hub": {"org": "org-1"}}\n' "$APP" > "$T/pa/app/.smns"
  live_session alder "$SA" "$T/pa/app"
  live_session xeno "$SX" "$T/pa/app"
  run_in "$T/pa/app" "$SMINOS" seat add crew sable --session "$SS"
  live_session sable "$SS" "$T/pa/app" bg
  "$SMINOS" daemon tick >/dev/null 2>&1 || true
  ended sable
  rl10_serve "$serve"
  start_daemon
  on pb beta
  rl10_cut_over
  printf '{"ceiling": "auto"}\n' > "$SMINOS_HOME/daemon/policy.json"
  EPB=$EP
  mkdir -p "$T/pb/web"
  printf '{"project": "%s", "name": "web", "hub": {"org": "org-1"}}\n' "$WEB" > "$T/pb/web/.smns"
  live_session birch "$SB" "$T/pb/web"
  "$SMINOS" daemon tick >/dev/null 2>&1 || true
  ended birch
  rl10_serve "$serve"
  start_daemon
  on pc gamma
  rl10_cut_over
  printf '{"ceiling": "auto"}\n' > "$SMINOS_HOME/daemon/policy.json"
  EPC=$EP
  mkdir -p "$T/pc/ops"
  printf '{"project": "%s", "name": "ops", "hub": {"org": "org-1"}}\n' "$OPS" > "$T/pc/ops/.smns"
  rl10_serve "$serve"
  start_daemon
  EPS="$EPA $EPB $EPC"
  for m in "pa alpha" "pb beta" "pc gamma"; do
    # shellcheck disable=SC2086
    on $m
    until_true caps_kept || true
  done
  on pa alpha
  sees_b() { (cd "$T/pa/app" && "$SMINOS" list --org --all 2>/dev/null) | grep -q "birch"; }   # B stopped: shown by --all
  speak_pass sees_b || true
  TA="$(thread_of "$SA")"
}
live_session() { # box session dir [kind] — a running session with an inbox (inbox_standin.py): frames in $T/<box>.received
  : > "$T/$1.received"
  python3 "$SCRIPT_DIR/inbox_standin.py" "$T/$1.sock" "$T/$1.received" & PIDS+=("$!")
  local pid=$!
  until_true test -S "$T/$1.sock"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"%s","status":"idle","cwd":"%s","messagingSocketPath":"%s","entrypoint":"cli"}\n' \
    "$pid" "$2" "$1" "${4:-interactive}" "$3" "$T/$1.sock" > "$HOME/.claude/sessions/$1.json"
  local tx="$HOME/.claude/projects/p-$2/$2.jsonl"   # its transcript, its last turn in `auto` (a wake asks nothing)
  mkdir -p "$(dirname "$tx")"
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","permissionMode":"auto","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
    "${2:0:8}" "$2" "$3" > "$tx"
  eval "PID_$1=$pid"
}
ended() { # box — its process gone, its engine record with it
  local pid
  eval "pid=\${PID_$1}"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -f "$HOME/.claude/sessions/$1.json"
}
speak_pass() { # command... — the org's directory from the stand-ins' `known`, then relays until it holds (30 s)
  [ "$SHOW" = 1 ] && printf '\n  -- a pass: relays between the stand-ins\n'
  # shellcheck disable=SC2086
  rl10_known_directory "$SDIR" $EPS >/dev/null
  relay_until "$@"
}
received_n() { grep -cF -- "$2" "$T/$1.received" 2>/dev/null || true; }   # box text → frames carrying it
got() { [ "$(received_n "$1" "$2")" -gt 0 ]; }
inputs_n() { (cat "$WAKE_ENGINE_STATE/inputs/$1" 2>/dev/null || true) | grep -cF -- "$2" || true; }   # session text
input_has() { [ "$(inputs_n "$1" "$2")" -gt 0 ]; }
launches() { cat "$WAKE_ENGINE_STATE/launches" 2>/dev/null || echo 0; }
thread_of() { # session → its thread id on this machine
  python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_threads
print(sminos_threads.stamp(sys.argv[1]) or "")' "$1"
}
content_with() { # file text — the content of the file's first frame (a JSON line's message content) carrying the text
  python3 -c 'import json, sys
for line in open(sys.argv[1]):
    c = json.loads(line)["message"]["content"] if line.strip() else ""
    if sys.argv[2] in c:
        print(c)
        break' "$1" "$2"
}
in_log() { # project-id text → kind, from_project and copy of each of this machine's events of the log carrying the text
  python3 - "$SMINOS_HOME/projects/$1/log" "$2" <<'PY'
import glob, json, os, sys
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.jsonl"))):
    for line in open(p):
        e = json.loads(line)
        if sys.argv[2] in str(e.get("text") or ""):
            print(e["kind"], "from_project" in e, "copy" in e)
PY
}
messages_outside() { # channel-id → the say and human events of this machine's logs but the channel's
  python3 - "$SMINOS_HOME/projects" "$1" <<'PY'
import glob, json, os, sys
n = 0
for p in glob.glob(os.path.join(sys.argv[1], "*", "log", "*.jsonl")):
    if os.sep + sys.argv[2] + os.sep not in p:
        n += sum(1 for line in open(p) if line.strip() and json.loads(line).get("kind") in ("say", "human"))
print(n)
PY
}
asked_about() { # ep-dir text → the questions the stand-in took about events carrying the text: "<t> <project>" lines
  rl10_q "$1" "sorted({f['t'] + ' ' + f.get('project', '') for c, f in F if f.get('t') in ('words?', 'reach?') and '$2' in str(f.get('event', {}).get('text'))})"
}
checked_spoken() { # "channel-id ..." "ep-dir home name" ... — the checker, this child's rules
  python3 -B - "$SCRIPT_DIR" "$@" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import channel_wire, endpoint_standin
ids, out = sys.argv[2].split(), []
for machine in sys.argv[3:]:
    ep, home, name = machine.split()
    state = json.loads(endpoint_standin.ctl_call(ep, "state", {}))
    frames = [(r["conn"], r["frame"]) for r in state["received"]]
    welcomed = {w["conn"] for w in state["welcomes"] if "channels" in w["welcome"]["capabilities"]}
    spoken = channel_wire.ALLOWED_SPOKEN   # a thread's delivery records allowed, their contents checked
    out += ["%s: %s" % (name, b) for b in channel_wire.published(frames, ids, {}, spoken, welcomed=welcomed)]
    out += ["%s: %s" % (name, b) for b in channel_wire.written(home, ids, name, {}, spoken, deliveries=False)]
    for cid in ids:
        if os.path.exists(os.path.join(home, "projects", cid, "outbox.jsonl")):
            out.append("%s: an outbox under channel %s" % (name, cid))
print("\n".join(out) or "clean")
PY
}
from_project_texts() { # channel-id → the texts of the channel's events on this machine that carry from_project
  python3 - "$SMINOS_HOME/projects/$1/log" <<'PY'
import glob, json, os, sys
print(" | ".join(sorted(json.loads(line).get("text", "") for p in glob.glob(os.path.join(sys.argv[1], "*.jsonl"))
                        for line in open(p) if line.strip() and "from_project" in json.loads(line))))
PY
}

tty_cmd() { # label dir answer args... — sminos run there on a controlling pty of its own, the answer typed at its
  local label=$1 dir=$2 answer=$3 line   # prompt (pty_answer.py: killed and reaped at its deadline, exit 124): OUT
  shift 3                                # and RC; printed with --show
  set +e
  OUT="$(cd "$dir" && env -u CLAUDE_CODE_SESSION_ID python3 -B "$SCRIPT_DIR/pty_answer.py" "$answer" "$SMINOS" "$@" 2>&1)"
  RC=$?; set -e
  if [ "$SHOW" = 1 ]; then
    printf '\n  [%s] $ sminos %s   (typed: %s)\n' "$label" "$*" "$answer"
    while IFS= read -r line; do printf '    %s\n' "$line"; done <<<"$OUT"
    printf '    (exit %s)\n' "$RC"
  fi
}
supervisor_standin() { # out — the engine supervisor's control socket for this machine's config dir: each `reply`
  # it takes appended to `out` and answered ok, as the engine's supervisor takes a person's words for a --bg job
  local sup
  sup="$(python3 -c 'import hashlib, os, sys; print(os.path.join("/tmp", "cc-daemon-%d" % os.getuid(), hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8], "control.sock"))' "$HOME/.claude")"
  SUPDIR="$(dirname "$sup")"
  case "$SUPDIR" in /tmp/cc-daemon-*/????????) ;; *) echo "refusing an unexpected supervisor path: $SUPDIR"; exit 1 ;; esac
  [ -d "$(dirname "$SUPDIR")" ] || mkdir -m 700 "$(dirname "$SUPDIR")"
  [ -d "$SUPDIR" ] || mkdir -m 700 "$SUPDIR"
  mkdir -p "$HOME/.claude/daemon"
  printf '0123456789abcdef0123456789abcdef' > "$HOME/.claude/daemon/control.key"
  python3 - "$sup" "$1" <<'PY' & PIDS+=("$!")
import json, os, socketserver, sys
path, out = sys.argv[1], sys.argv[2]
try:
    os.unlink(path)
except FileNotFoundError:
    pass
class H(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline()
        if not line.strip():
            return
        with open(out, "a") as f:
            f.write(line.decode().rstrip("\n") + "\n")
        self.wfile.write((json.dumps({"ok": True, "op": json.loads(line).get("op")}) + "\n").encode())
socketserver.UnixStreamServer(path, H).serve_forever()
PY
  until_true test -S "$sup"
}
lead_post_to() { # channel-id text — the threads the `to` of this machine's event carrying the text names
  python3 - "$SMINOS_HOME/projects/$1/log" "$2" <<'PY'
import glob, json, os, sys
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.jsonl"))):
    for line in open(p):
        e = json.loads(line)
        if sys.argv[2] in str(e.get("text") or ""):
            print(e["kind"], " ".join(r.get("thread", "-") for r in e["to"]) if isinstance(e["to"], list) else e["to"])
PY
}

speak_scene() {
  echo "the speaking scene (CH2's M6):"
  speak_machines
  assert_equals "$(sees_b && echo yes)" yes "alpha reads beta's thread B, relayed"
  local desk frame b_line marks

  echo " 1. A creates the channel and adds S and B:"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel create desk-integration
  assert_rc 0 "$RC" "A creates the channel"
  desk="$(channel_id desk-integration)"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel add desk-integration sable "birch#${SB:0:8}"
  assert_contains "$OUT" "sable#${SS:0:8}: in desk-integration" "S is in"
  assert_contains "$OUT" "birch#${SB:0:8}: asked; pending on beta" "B asked of beta"
  local three="${SA:0:8} ${SS:0:8} ${SB:0:8}"
  speak_pass shown_is "$T/pa/app" "$SA" desk-integration "members()" "$three" || true
  assert_equals "$(shown "$T/pa/app" "$SA" desk-integration "members()")" "$three" "alpha's roster holds the three"
  on pb beta
  speak_pass shown_is "$T/pb/web" "$SB" desk-integration "members()" "$three" || true
  assert_equals "$(shown "$T/pb/web" "$SB" desk-integration "members()")" "$three" "and beta's"
  marks="$(on pa alpha; messages_outside "$desk") $(messages_outside "$desk")"

  echo " 2. A says into it to B: beta's uplink asks, keeps the word, and its daemon wakes B:"
  on pa alpha
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say --in desk-integration "@birch one"
  assert_rc 0 "$RC" "recorded"
  assert_contains "$OUT" "birch: recorded (on beta): the session is stopped, and its machine wakes it with this" \
    "its line for B is what a sender reads for a stopped thread on another machine"
  on pb beta
  speak_pass input_has "$SB" "@birch one" || true
  assert_equals "$(launches)" 1 "beta's engine recorded one launch for B"
  assert_equals "$(inputs_n "$SB" "@birch one")" 1 "B's input holds one frame"
  frame="$(content_with "$WAKE_ENGINE_STATE/inputs/$SB" "@birch one")"
  assert_contains "$(sed -n 2p <<<"$frame")" "[sminos chat desk-integration " "its header names the channel"
  assert_contains "$frame" "[sminos] A note from sminos on this machine" "with the [sminos] line"
  b_line="@$desk/${TA:0:8}"
  assert_contains "$frame" "say \"$b_line <your reply>\"]" "its reply line names the channel's id and A's thread"
  assert_equals "$(asked_about "$EPB" "@birch one")" "[\"reach? $desk\"]" \
    "beta asked its endpoint reach? under the channel's id, nothing else"

  echo " 3. B's reply by that line is recorded in the channel and reaches A:"
  scene_cmd "beta, as B" "$T/pb/web" "$SB" say "$b_line two, from B"
  assert_rc 0 "$RC" "B's reply recorded"
  assert_contains "$OUT" "in desk-integration" "in the channel's log"
  on pa alpha
  speak_pass got alder "two, from B" || true
  assert_equals "$(received_n alder "two, from B")" 1 "A's inbox holds it once"
  assert_equals "$(messages_outside "$desk") $(on pb beta; messages_outside "$desk")" "$marks" \
    "no project's log on either machine gained a message"
  assert_equals "$(from_project_texts "$desk")" "" "no event of the channel's log carries from_project"
  assert_equals "$(in_log "$desk" "" | grep -c True || true)" 0 "nor copy"

  echo " 4. @all reaches the live members, an untagged note no one, a tag the stopped S on its own machine:"
  b_filled() { [ "$(shown "$T/pa/app" "$SA" desk-integration "[m['state'] in ('busy', 'idle', 'waiting') for m in d['members'] if m['session'] == '$SB']")" = "[True]" ]; }
  speak_pass b_filled || true   # alpha reads B live, as beta publishes it since its wake
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say --in desk-integration "@all three to all"
  assert_rc 0 "$RC" "recorded"
  on pb beta
  speak_pass input_has "$SB" "three to all" || true
  assert_equals "$(inputs_n "$SB" "three to all")" 1 "B, live since step 2, receives it"
  assert_equals "$(launches)" 1 "with no second launch"
  on pa alpha
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say --in desk-integration "a note"
  assert_rc 0 "$RC" "the untagged note recorded"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say "@desk-integration/sable four, to S"
  assert_rc 0 "$RC" "the tag to S recorded"
  until_true input_has "$SS" "four, to S" || true
  assert_equals "$(inputs_n "$SS" "four, to S")" 1 "S is woken on alpha with it"
  assert_equals "$(launches)" 1 "one launch on alpha"
  assert_equals "$(inputs_n "$SS" "three to all")" 0 "S, stopped then, was given nothing of the @all"
  assert_equals "$(asked_about "$EPA" "four, to S")" "[]" "and alpha's endpoint was asked nothing about it"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say --in desk-integration "@birch after the note"
  on pb beta
  speak_pass input_has "$SB" "after the note" || true   # what A said after the note has reached B
  assert_equals "$(inputs_n "$SB" "a note") $(received_n alder "a note") $(received_n xeno "a note") $(on pa alpha; inputs_n "$SS" "a note")" \
    "0 0 0 0" "the note reached no inbox"

  echo " 5. X, in no channel, says into it; A's answer reaches X directly:"
  on pa alpha
  scene_cmd "alpha, as X" "$T/pa/app" "$SX" say --in desk-integration "@alder five, from X"
  assert_rc 0 "$RC" "recorded"
  assert_contains "$OUT" "you are not in desk-integration" "X is told it is no member"
  assert_contains "$OUT" "sminos channel add" "and how to join"
  assert_equals "$(in_log "$desk" "five, from X")" "say True False" "in the channel's log, with from_project"
  assert_equals "$(in_log "$APP" "five, from X")" "say False True" "a copy in X's project"
  until_true got alder "five, from X" || true
  frame="$(content_with "$T/alder.received" "five, from X")"
  assert_contains "$(sed -n 2p <<<"$frame")" "(not in desk-integration)" "A's frame says its sender is outside"
  assert_contains "$frame" "say \"@$APP/${SX:0:8} <your reply>\"]" "its reply line names X in X's project"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say "@$APP/${SX:0:8} six, to X"
  assert_rc 0 "$RC" "A's answer recorded"
  until_true got xeno "six, to X" || true
  assert_equals "$(received_n xeno "six, to X")" 1 "X's inbox holds A's answer"
  assert_equals "$(in_log "$APP" "six, to X" | head -1)" "say False False" "in X's project's log"
  assert_equals "$(in_log "$desk" "six, to X")" "" "and not the channel's"
  scene_cmd "alpha, as X" "$T/pa/app" "$SX" say "@desk-integration/birch seven, to B"
  assert_rc 0 "$RC" "X's tag to B in the channel recorded"
  scene_cmd "alpha, as X" "$T/pa/app" "$SX" say --in desk-integration "@all eight to all"
  assert_rc 0 "$RC" "X's @all recorded"
  on pb beta
  speak_pass input_has "$SB" "eight to all" || true
  assert_equals "$(inputs_n "$SB" "seven, to B") $(inputs_n "$SB" "eight to all")" "1 1" "B receives both"
  on pa alpha
  until_true got alder "eight to all" || true
  assert_equals "$(received_n alder "eight to all")" 1 "A receives the @all"
  assert_equals "$(grep -c "desk-integration" "$T/xeno.received" || true)" 0 \
    "nothing of the channel's log, its @alls among it, was pushed to X"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say "@birch nine, to B's project"
  assert_rc 0 "$RC" "A's tag to B's alias recorded"
  assert_equals "$(in_log "$APP" "nine, to B's project")" "say False True" "a copy in A's project"
  on pb beta
  in_web() { [ "$(in_log "$WEB" "nine, to B's project")" = "say True False" ]; }
  speak_pass in_web || true
  assert_equals "$(in_log "$WEB" "nine, to B's project")" "say True False" "recorded in B's project's log"

  echo " 6. A leaves, and B's line goes to A directly; A back, and it is the channel's again; B removed:"
  on pa alpha
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel remove desk-integration
  assert_contains "$OUT" "alder#${SA:0:8}: out of desk-integration" "A out"
  on pb beta
  speak_pass shown_is "$T/pb/web" "$SB" desk-integration "members()" "${SS:0:8} ${SB:0:8}" || true
  scene_cmd "beta, as B" "$T/pb/web" "$SB" say "$b_line ten, from B"
  assert_rc 0 "$RC" "B's line run again: recorded"
  assert_contains "$OUT" "not in desk-integration now" "B is told A is not in the channel now"
  assert_equals "$(in_log "$desk" "ten, from B")" "" "not in the channel's log"
  on pa alpha
  speak_pass got alder "ten, from B" || true
  assert_equals "$(received_n alder "ten, from B")" 1 "A receives it"
  assert_equals "$(in_log "$APP" "ten, from B" | head -1 | cut -d' ' -f1)" say "in A's project's log"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel add desk-integration
  assert_contains "$OUT" "alder#${SA:0:8}: in desk-integration" "A back"
  on pb beta
  speak_pass shown_is "$T/pb/web" "$SB" desk-integration "members()" "$three" || true
  scene_cmd "beta, as B" "$T/pb/web" "$SB" say "$b_line eleven, from B"
  assert_rc 0 "$RC" "B's line once more: recorded"
  assert_contains "$OUT" "in desk-integration" "in the channel's log"
  on pa alpha
  speak_pass got alder "eleven, from B" || true
  assert_equals "$(received_n alder "eleven, from B")" 1 "and it reaches A"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel remove desk-integration "birch#${SB:0:8}"
  assert_rc 0 "$RC" "A removes B"
  speak_pass shown_is "$T/pa/app" "$SA" desk-integration "members()" "${SA:0:8} ${SS:0:8}" || true
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" say "@desk-integration/birch x"
  assert_rc 4 "$RC" "a tag to B in the channel: refused"
  assert_contains "$OUT" "birch" "naming B"
  assert_contains "$OUT" "elsewhere: @web/birch#${SB:0:8}" "and where it is"

  echo " 7. gamma, which holds no member, posts a notice into it:"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel env add desk-integration gamma
  assert_rc 0 "$RC" "gamma added to the channel's environment"
  on pc gamma
  gamma_knows() { [ -n "$(channel_id desk-integration)" ]; }
  speak_pass gamma_knows || true
  scene_cmd "gamma, a terminal" "$T/pc" - say --notice devcloud --in desk-integration "lease ends"
  assert_rc 0 "$RC" "recorded"
  on pa alpha
  shows_notice() { (cd "$T/pa/app" && "$SMINOS" chat desk-integration -n 5 2>/dev/null) | grep -F "lease ends" | grep -qF "devcloud@gamma"; }
  speak_pass shows_notice || true
  scene_cmd "alpha, a terminal" "$T/pa/app" - chat desk-integration -n 5
  assert_contains "$(grep -F "lease ends" <<<"$OUT")" "devcloud@gamma" "sminos chat on alpha shows it from devcloud@gamma"
  assert_equals "$(received_n alder "lease ends") $(on pb beta; inputs_n "$SB" "lease ends")" "0 0" "no session was prompted"

  echo " 8. at a terminal on alpha, S the lead: the person's untagged post reaches it as its human's words:"
  on pa alpha
  set_ep "$EPA" '{"verdict": "words", "notice_words": true}'   # this machine's own human writer; a notice too
  supervisor_standin "$T/sup-in"   # S runs as the --bg job its wake started, with no bridge: its supervisor's reply
  tty_cmd "alpha, a terminal" "$T/pa/app" y channel lead desk-integration sable
  assert_rc 0 "$RC" "the lead named with a typed yes"
  assert_contains "$OUT" "sable#${SS:0:8} leads desk-integration" "S leads the channel"
  scene_cmd "alpha, a terminal" "$T/pa/app" - say --in desk-integration "do it"
  assert_rc 0 "$RC" "the person's untagged post recorded"
  assert_equals "$(lead_post_to "$desk" "do it")" "human $(thread_of "$SS")" "its event names S's thread in to"
  sup_has() { grep -qF -- "$1" "$T/sup-in" 2>/dev/null; }
  speak_pass sup_has "do it" || true
  assert_equals "$(asked_about "$EPA" "do it")" "[\"words? $desk\"]" \
    "alpha's endpoint was asked one words? under the channel's id (and answered words)"
  assert_equals "$(grep -cF "do it" "$T/sup-in" 2>/dev/null || true)" 1 "S was handed it as a person's words"
  assert_equals "$(inputs_n "$SS" "do it")" 0 "never as a peer's frame"
  scene_cmd "alpha, a terminal" "$T/pa/app" - say --notice devcloud --in desk-integration "@sable lease ends, S"
  assert_rc 0 "$RC" "a notice tagged to the lead recorded"
  until_true input_has "$SS" "lease ends, S" || true
  frame="$(content_with "$WAKE_ENGINE_STATE/inputs/$SS" "lease ends, S")"
  assert_contains "$(sed -n 2p <<<"$frame")" "from devcloud@alpha" "S receives an inbox frame from devcloud@alpha"
  assert_equals "$(grep -c "To reply" <<<"$frame" || true)" 0 "with no reply line"
  assert_equals "$(asked_about "$EPA" "lease ends, S")" "[\"words? $desk\"]" "though the stand-in's word for it was words"
  assert_equals "$(grep -cF "lease ends, S" "$T/sup-in" 2>/dev/null || true)" 0 "and nothing of it was handed as words"
  scene_cmd "alpha, as A" "$T/pa/app" "$SA" channel lead desk-integration sable
  assert_rc 1 "$RC" "the lead verb run as A is refused"
  assert_contains "$OUT" "channel lead is for a person at a terminal" "saying it is the person's"

  echo " 9. the checker over the three stand-ins and stores:"
  assert_equals "$(checked_spoken "$desk" "$EPA $T/pa/s alpha" "$EPB $T/pb/s beta" "$EPC $T/pc/s gamma")" clean \
    "nothing went up under the channel but its events, reach? and words?; no outbox under it"
  assert_equals "$(on pa alpha; from_project_texts "$desk")" "@alder five, from X | @all eight to all | @desk-integration/birch seven, to B" \
    "from_project is carried by X's three messages alone"
  DESK_SPOKEN=$desk
}

# M6's cases on the scene's machines, in a channel of their own (desk-ops: A and B): a writer on a machine that holds
# no member, what beta held at the boundary, and the outcomes the checker reads once beta has uploaded since. That
# gamma's log stays open while what it wrote has not gone up is test_channels_wire.py's (a follower leaves only
# after LEAVE_AFTER_S of connected time, a day, which no scene waits out).
speak_cases() {
  echo "speaking across machines (CH2's M6): a writer that holds no member, the boundary, the outcomes:"
  local ops_ch two="${SA:0:8} ${SB:0:8}" id
  on pa alpha
  run_in "$T/pa/app" in_session "$SA" "$SMINOS" channel create desk-ops
  ops_ch="$(channel_id desk-ops)"
  run_in "$T/pa/app" in_session "$SA" "$SMINOS" channel add desk-ops "birch#${SB:0:8}"
  speak_pass shown_is "$T/pa/app" "$SA" desk-ops "members()" "$two" || true
  on pb beta
  speak_pass shown_is "$T/pb/web" "$SB" desk-ops "members()" "$two" || true
  assert_equals "$(shown "$T/pb/web" "$SB" desk-ops "members()")" "$two" "desk-ops holds A and B on beta"

  on pc gamma
  live_session gauge "$SG" "$T/pc/ops"
  gamma_knows_ops() { [ -n "$(channel_id desk-ops)" ]; }
  speak_pass gamma_knows_ops || true
  run_in "$T/pc/ops" in_session "$SG" "$SMINOS" say --in desk-ops "@all g1, from gamma"
  assert_rc 0 "$RC" "on gamma, which holds no member, G says into desk-ops"
  assert_contains "$OUT" "you are not in desk-ops" "told it is no member"
  up_after_frame() { # gamma's stand-in took G's member frame under ops before the events frame carrying the text
    rl10_q "$EPC" "(lambda m, u: m is not None and u is not None and m < u)(next((n for n, (c, f) in enumerate(F) if f.get('t') == 'member' and f.get('session') == '$SG' and f.get('project') == '$OPS'), None), next((n for n, (c, f) in enumerate(F) if f.get('t') == 'events' and f.get('project') == '$ops_ch' and any('$1' in str(e.get('text')) for e in f.get('events', []))), None))"
  }
  went_up() { [ "$(up_after_frame g1)" = true ]; }
  until_true went_up || true
  assert_equals "$(up_after_frame g1)" true "uploaded under the channel's id after G's member frame under its own project"
  assert_equals "$(follows "$EPC" "$ops_ch")" True "from a log gamma opened with follow"
  on pa alpha
  speak_pass got alder "g1, from gamma" || true
  assert_equals "$(received_n alder "g1, from gamma")" 1 "delivered on alpha"
  on pb beta
  speak_pass input_has "$SB" "g1, from gamma" || true
  assert_equals "$(inputs_n "$SB" "g1, from gamma")" 1 "and on beta"
  on pa alpha
  run_in "$T/pa/app" in_session "$SA" "$SMINOS" say "@$OPS/${SG:0:8} g2, to gamma"
  assert_rc 0 "$RC" "A answers by the frame's line"
  on pc gamma
  speak_pass got gauge "g2, to gamma" || true
  assert_equals "$(received_n gauge "g2, to gamma")" 1 "the answer reaches G in its project on gamma"
  on pa alpha
  run_in "$T/pa/app" in_session "$SA" "$SMINOS" say --in desk-ops "@birch b1, relayed late"
  assert_rc 0 "$RC" "a message to B written on alpha, not relayed yet"
  on pb beta
  run_in "$T/pb/web" in_session "$SB" "$SMINOS" channel remove desk-ops
  assert_rc 0 "$RC" "B removes itself on beta"
  run_in "$T/pb/web" in_session "$SB" "$SMINOS" channel add desk-ops
  assert_rc 0 "$RC" "and adds itself again"
  speak_pass input_has "$SB" "b1, relayed late" || true
  assert_equals "$(inputs_n "$SB" "b1, relayed late")" 1 "relayed to beta only after that: pushed"
  set_ep "$EPB" '{"reach_verdict": null}'
  on pa alpha
  run_in "$T/pa/app" in_session "$SA" "$SMINOS" say --in desk-ops "@birch b2, relayed early"
  on pb beta
  asked_b2() { [ "$(asked_about "$EPB" "b2, relayed early")" != "[]" ]; }
  speak_pass asked_b2 || true
  assert_equals "$(asked_about "$EPB" "b2, relayed early")" "[\"reach? $ops_ch\"]" "relayed to beta and asked about, its answer held"
  run_in "$T/pb/web" in_session "$SB" "$SMINOS" channel remove desk-ops
  run_in "$T/pb/web" in_session "$SB" "$SMINOS" channel add desk-ops
  assert_rc 0 "$RC" "B removed and added again before the answer"
  id="$(rl10_q "$EPB" "[f['id'] for c, f in F if f.get('t') == 'reach?' and 'b2, relayed early' in str(f.get('event', {}).get('text'))][-1]")"
  python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPB" send "{\"frames\": [{\"t\": \"reach\", \"id\": $id, \"verdict\": \"deliver\"}]}" >/dev/null
  set_ep "$EPB" '{"reach_verdict": "deliver"}'
  on pa alpha
  run_in "$T/pa/app" in_session "$SA" "$SMINOS" say --in desk-ops "@birch b3, after"
  on pb beta
  speak_pass input_has "$SB" "b3, after" || true
  assert_equals "$(inputs_n "$SB" "b3, after") $(inputs_n "$SB" "b2, relayed early")" "1 0" \
    "the message beta held before the removal is not pushed after it; the next one is"

  run_in "$T/pb/web" in_session "$SB" "$SMINOS" say --in desk-ops "@alder b4, from B"
  on pa alpha
  speak_pass got alder "b4, from B" || true
  assert_equals "$(received_n alder "b4, from B")" 1 "beta uploaded since its pushes were settled"
  assert_equals "$(checked_spoken "$DESK_SPOKEN $ops_ch" "$EPA $T/pa/s alpha" "$EPB $T/pb/s beta" "$EPC $T/pc/s gamma")" clean \
    "the checker over both channels: no delivery frame names one, no outbox under one"
}

if [ "$SCENE_ONLY" = 0 ] && [ "$SPEAK_ONLY" = 0 ]; then
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
# The endpoint refuses with a reason word (MAWS: not-reachable, or unverified); a refusal is a refusal whatever it is.
set_ep "$EPB" '{"reach_verdict": ["refuse", "unverified"]}'
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
# A request is uploaded, imported and asked about under the channel's id, the log it is in, and nothing else.
assert_equals "$(rl10_q "$EPA" "sorted({f['project'] for c, f in F if f.get('t') == 'events' for e in f.get('events', []) if e.get('kind') == 'channel-request'})")" \
  "[\"$REQ\"]" "alpha uploads its requests under the channel's id alone"
assert_equals "$(rl10_q "$EPB" "sorted({f['project'] for c, f in F if f.get('t') == 'reach?'})")" "[\"$REQ\"]" \
  "beta asks about them under the channel's id alone"
assert_equals "$(on_beta imported "$REQ" "$R2")" yes "and holds them in the channel's log"
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
assert_equals "$(asked_of "$EPB" "$R4")" 0 "beta asked nothing about it"
assert_equals "$(on_beta imported "$REQ" "$R4")" no "and its copy of the channel's log does not hold it: it never reached beta"
assert_equals "$(on_beta imported "$REQ" "$R3")" yes "(the request before it there did)"
no_launch a b c && pass "no turn of any session was started" || fail "no turn of any session was started"

echo "nothing is published or written under the channel:"
CHECKED="$(checked_clean "$DESK $REQ" "$EPA $T/a/s alpha" "$EPB $T/b/s beta" "$EPC $T/c/s gamma")"
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

[ "$SPEAK_ONLY" = 0 ] && scene
if [ "$SCENE_ONLY" = 0 ]; then
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
  PIDS=()
  speak_scene
  [ "$SPEAK_ONLY" = 0 ] && speak_cases
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-channels-machines.sh: $PASSES passed, 0 failed"
else
  echo "test-channels-machines.sh: $PASSES passed, $FAILURES failed"
  exit 1
fi
