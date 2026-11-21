#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# Declared channels through the launcher, on one machine (CH1 of
# docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md; its plan,
# docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, the proof map):
# nothing is said into a channel, from a session or from a terminal, every
# log's files unchanged (A10); `join <channel>` is refused naming
# `channel add`, and a `.smns` naming a channel's id files its directory in
# the machine's project, saying why (A8's halves); a verb that writes a fact
# about a thread (`charge`, `status`, `retire`) writes it to the thread's own
# project however the thread is named, and one that names it through a
# channel is refused (A11). The channel is registered as the org's directory
# registers one (sminos_channels.register): no verb creates one yet.
# One machine cut over to its endpoint (daemon/identity.json); no endpoint
# runs. Hermetic: HOME and SMINOS_HOME are temporary; `claude` is a stub;
# the sessions are `sleep`s with engine records the suite writes.
# run-sminos-tests.sh runs this file in its `channels` part.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(cd "$(mktemp -d /tmp/smc.XXXXXX)" && pwd -P)"   # its real path: a warning names the file so
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
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
in_session() { # session command... — the command as that session runs it
  local sid=$1; shift
  env CLAUDE_CODE_SESSION_ID="$sid" "$@"
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
logs_sum() { # every log and host file of every project here, as one digest: what a refusal must leave as it was
  (cd "$SMINOS_HOME/projects" && find . -path '*/log/*.jsonl' -o -path '*/host/*.jsonl' | LC_ALL=C sort |
    while read -r f; do printf '%s ' "$f"; shasum < "$f"; done) | shasum | cut -c1-40
}
kinds_of() { # project-id session — the kinds of the session's events in the project's log, in order
  python3 - "$SMINOS_HOME/projects/$1/log" "$2" <<'PY'
import glob, json, os, sys
rows = []
for p in glob.glob(os.path.join(sys.argv[1], "*.jsonl")):
    for line in open(p):
        e = json.loads(line)
        if e.get("session") == sys.argv[2]:
            rows.append((e["ts"], e["seq"], e["kind"]))
print(" ".join(k for _, _, k in sorted(rows)))
PY
}
channel_files() { find "$SMINOS_HOME/projects/$DESK" -type f -name '*.jsonl' | wc -l | tr -d ' '; }

DESK=5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c
APP=7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d
S1=6c000001-0000-4000-8000-0000000000c1
S3=6c000003-0000-4000-8000-0000000000c3

rl10_as a alpha
rl10_cut_over
APPDIR="$T/a/app"
mkdir -p "$APPDIR"
printf '{"project": "%s", "name": "app", "hub": {"org": "org-1"}}\n' "$APP" > "$APPDIR/.smns"
python3 - "$DESK" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_channels
sminos_channels.register(sys.argv[1], "desk-integration")
PY
live_pid
session_record worker "$S1" "$LIVE_PID" "$APPDIR"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
run_in "$APPDIR" "$SMINOS" list --json
assert_contains "$OUT" "\"session\": \"$S1\"" "a session in app is a member of it"

echo "nothing is said into a channel:"
BEFORE="$(logs_sum)"
REFUSED="is a channel, and speaking in a channel is not available in this version of sminos yet: nothing was recorded. Tag the thread itself (@<alias>#<short> or @<short>), which reaches it in its own project as today"
for how in "terminal" "session"; do
  pre=(); [ "$how" = session ] && pre=(env CLAUDE_CODE_SESSION_ID="$S1")
  run_in "$APPDIR" ${pre[@]+"${pre[@]}"} "$SMINOS" say --in desk-integration "hello there"
  assert_rc 1 "$RC" "say --in <channel> from a $how is refused, exit 1"
  assert_contains "$OUT" "desk-integration $REFUSED" "saying why, and which tag works today ($how)"
  run_in "$APPDIR" ${pre[@]+"${pre[@]}"} "$SMINOS" say --in "$DESK" "hello there"
  assert_rc 1 "$RC" "and by its id ($how)"
  run_in "$APPDIR" ${pre[@]+"${pre[@]}"} "$SMINOS" say "@desk-integration/worker hello there"
  assert_rc 1 "$RC" "a tag qualified by a channel is refused ($how)"
  assert_contains "$OUT" "desk-integration $REFUSED" "in the same words ($how)"
  run_in "$APPDIR" ${pre[@]+"${pre[@]}"} "$SMINOS" say --project desk-integration "hello there"
  assert_rc 1 "$RC" "a selector naming a channel is refused ($how)"
  assert_contains "$OUT" "desk-integration $REFUSED" "in the same words, before the selector reads its scope ($how)"
done
assert_equals "$(logs_sum)" "$BEFORE" "no log file of any project or channel changed"
assert_equals "$(channel_files)" 0 "the channel's log holds nothing"
run_in "$APPDIR" "$SMINOS" say "@worker the plain tag"
assert_rc 0 "$RC" "the plain tag reaches the thread in its own project"
assert_contains "$(kinds_of "$APP" "$S1")" "joined" "its project's log is where it is"

echo "join and .smns:"
run_in "$APPDIR" in_session "$S1" "$SMINOS" join desk-integration
assert_rc 1 "$RC" "join <channel> is refused, exit 1"
assert_contains "$OUT" "cannot join desk-integration: it is a channel, not a project — sminos channel add desk-integration places a thread in it, and its project stays where it is" "naming channel add"
run_in "$APPDIR" in_session "$S1" "$SMINOS" join "$DESK"
assert_rc 1 "$RC" "and by its id"
assert_equals "$([ -e "$SMINOS_HOME/sessions/$S1.json" ] && echo override || echo none)" none "no override written"
CDIR="$T/a/chan-dir"
mkdir -p "$CDIR"
printf '{"project": "%s", "name": "desk-integration", "hub": {"org": "org-1"}}\n' "$DESK" > "$CDIR/.smns"
live_pid
session_record there "$S3" "$LIVE_PID" "$CDIR"
run_in "$CDIR" "$SMINOS" project show
assert_contains "$OUT" "ignoring $CDIR/.smns: it names a channel's id, and a channel is no project; this directory is in the machine's project" "a .smns naming a channel says why it is not taken"
assert_contains "$OUT" "alpha" "and its directory is in the machine's project"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
run_in "$T" "$SMINOS" list alpha --json
assert_contains "$OUT" "\"session\": \"$S3\"" "a session there is a member of the machine's project"
assert_equals "$(channel_files)" 0 "and nothing of it is in the channel's log"

echo "a verb's fact goes to the thread's own project:"
SHORT="${S1:0:8}"
for name in "$SHORT" "$S1" "worker#$SHORT"; do
  run_in "$APPDIR" "$SMINOS" charge "$name" "minding the desk via $name"
  assert_rc 0 "$RC" "charge names the thread by $name"
  run_in "$APPDIR" "$SMINOS" status "$name" "now via $name"
  assert_rc 0 "$RC" "status names the thread by $name"
done
assert_equals "$(kinds_of "$APP" "$S1" | tr ' ' '\n' | grep -c '^in-charge$')" 3 "three in-charge lines in its project's log"
assert_equals "$(kinds_of "$APP" "$S1" | tr ' ' '\n' | grep -c '^status$')" 3 "three status lines there"
for verb in "charge desk-integration/worker x" "status desk-integration/worker x" "retire desk-integration/worker"; do
  # shellcheck disable=SC2086
  run_in "$APPDIR" "$SMINOS" $verb
  assert_rc 4 "$RC" "$verb is refused, exit 4"
  assert_contains "$OUT" "'desk-integration/worker' names a thread through a channel, which is not available in this version of sminos yet: name it by its own name (<alias>#<short> or <short>)" "saying how to name it ($verb)"
done
run_in "$APPDIR" "$SMINOS" retire "worker#$SHORT"
assert_rc 0 "$RC" "retire names it by alias#short"
assert_contains "$(kinds_of "$APP" "$S1")" "retired" "its retirement is in its own project's log"
assert_equals "$(channel_files)" 0 "nothing was ever written in the channel's log"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-channels.sh: $PASSES passed, 0 failed"
else
  echo "test-channels.sh: $PASSES passed, $FAILURES failed"
  exit 1
fi
