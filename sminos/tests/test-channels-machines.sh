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
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; the sessions are `sleep`s with engine records the suite writes;
# nothing listens beyond Unix sockets there.
# run-sminos-tests.sh runs this file in its `channels` part.
set -euo pipefail

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
SA=6a000001-0000-4000-8000-0000000000a1
SB=6b000001-0000-4000-8000-0000000000b1
DIR="$(python3 - "$APP" "$WEB" <<'PY'
import json, sys
print(json.dumps({"projects": [{"id": sys.argv[1], "name": "app", "kind": "hub", "retired": False},
                               {"id": sys.argv[2], "name": "web", "kind": "hub", "retired": False}],
                  "machines": [{"name": n, "online": False} for n in ("alpha", "beta", "gamma")]}))
PY
)"
SERVE="\"capabilities\": [\"channels\"], \"org\": $DIR"

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
rl10_serve "$SERVE"
start_daemon

caps_kept() { # this machine's kept welcome lists channels
  python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_audience
sys.exit(0 if sminos_audience.advertised("channels") else 1)' 2>/dev/null
}
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

echo "nothing is published or written under the channel:"
# A fresh store on every machine: the baseline is empty, so nothing this code wrote under the channel,
# its creation included, is excused (only a store an older copy wrote into has one: test_channels_wire.py).
CHECKED="$(python3 -B - "$SCRIPT_DIR" "$DESK" "$EPA" "$EPB" "$EPC" "$T/a/s" "$T/b/s" "$T/c/s" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import channel_wire, endpoint_standin
cid, eps, homes = sys.argv[2], sys.argv[3:6], sys.argv[6:9]
out = []
for ep, home, name in zip(eps, homes, ("alpha", "beta", "gamma")):
    state = json.loads(endpoint_standin.ctl_call(ep, "state", {}))
    frames = [(r["conn"], r["frame"]) for r in state["received"]]
    welcomed = {w["conn"] for w in state["welcomes"] if "channels" in w["welcome"]["capabilities"]}
    out += ["%s: %s" % (name, b) for b in channel_wire.published(frames, [cid], {}, welcomed=welcomed)]
    out += ["%s: %s" % (name, b) for b in channel_wire.written(home, [cid], name, {})]
print("\n".join(out) or "clean")
PY
)"
assert_equals "$CHECKED" clean "the checker passes over the three stand-ins and the three stores"
launched=0
for m in a b c; do
  launched=$((launched + $( (cat "$T/$m/stub/calls" 2>/dev/null || true) | grep -c -e resume -e '--bg' || true)))
done
assert_equals "$launched" 0 "no session's turn was started"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-channels-machines.sh: $PASSES passed, 0 failed"
else
  echo "test-channels-machines.sh: $PASSES passed, $FAILURES failed"
  exit 1
fi
