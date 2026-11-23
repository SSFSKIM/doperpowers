#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# Declared channels through the launcher, on one machine (CH1 of
# docs/doperpowers/specs/2026-11-21-sminos-channels-ch-design.md; its plan,
# docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, the proof map):
# `join <channel>` is refused naming
# `channel add`, and a `.smns` naming a channel's id files its directory in
# the machine's project, saying why (A8's halves); a verb that writes a fact
# about a thread (`charge`, `status`, `retire`) writes it to the thread's own
# project however the thread is named (A11), through a channel it is in
# included (CH2's M1), and one that names it through a channel it is not in
# is refused, naming where the name answers. The verbs
# `channel create`, `add` and `remove` (M4): refused without the capability,
# every log unchanged; with it, a thread creating a channel with itself,
# adding and removing another by a request carried out before the command
# returns, from a session and from a terminal, each refusal of §8 before
# anything is written, and an emptied channel's name bringing it back under
# its id; no session's turn started. The listing (M5): a member's bare
# `list` ends with its channel's section, a session in no channel lists none,
# `--channel` in text and `--json`, `channel show` with its request applied
# and its pool's count, `channel env` refused before anything is written
# from a terminal, a thread not in the channel and for a machine the org
# does not list, then adding and removing a machine by hand, and `list
# --org` ending with a section for a channel with a member and none once its
# last member left. What is said into a channel (CH2's M4): a person's
# untagged note, a session in no channel saying into it (its project in
# `from_project`, its copy, its line), the refusals of a name no member
# answers, a selector and the unquoted `name#short` qualifier with every
# log unchanged, `chat <channel>` and `list <channel>`. The lead (CH2's
# M8): `channel lead` refused inside a session, with no terminal and without
# a typed yes, every log unchanged; a typed yes on a controlling pty names
# it, `channel show` prints it, the person's untagged post is addressed to
# it and a session's is not, and `none` clears it. The first channel is
# registered as the org's directory registers one (sminos_channels.register).
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

echo "the channel verbs (create, add, remove):"
S2=6c000002-0000-4000-8000-0000000000c2
live_pid
session_record helper "$S2" "$LIVE_PID" "$APPDIR"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
NOCAP="this machine's endpoint does not serve channels (its welcome listed no channels): nothing was written"
BEFORE="$(logs_sum)"
for verb in "create desk-two" "add desk-integration" "remove desk-integration" "add desk-integration helper"; do
  # shellcheck disable=SC2086
  run_in "$APPDIR" in_session "$S1" "$SMINOS" channel $verb
  assert_rc 1 "$RC" "channel $verb without the capability is refused, exit 1"
  assert_contains "$OUT" "$NOCAP" "saying the endpoint serves no channels ($verb)"
done
run_in "$APPDIR" "$SMINOS" channel add desk-integration helper
assert_rc 1 "$RC" "and from a terminal"
assert_equals "$(logs_sum)" "$BEFORE" "no log file changed"
python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_audience
sminos_audience.keep_capabilities(["channels"])   # what a welcome that listed channels keeps
PY
channel_id() { python3 - "$1" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
print(" ".join(c.id for c in sminos.known_channels() if c.name == sys.argv[1]))
PY
}
set_of() { # session — its thread's set, as its record holds it
  python3 - "$1" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_channels
print(" ".join(sminos_channels.channels_of(sys.argv[1])))
PY
}
log_kinds() { # channel id — every kind its log holds, each once
  cat "$SMINOS_HOME/projects/$1/log/"*.jsonl 2>/dev/null | python3 -c 'import json, sys
print(" ".join(sorted({json.loads(l)["kind"] for l in sys.stdin if l.strip()})))'
}
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel create desk-two
assert_rc 0 "$RC" "a session creates a channel"
TWO="$(channel_id desk-two)"
assert_contains "$OUT" "created channel desk-two ($TWO) with worker#${S1:0:8}" "with itself its first member"
assert_equals "$(set_of "$S1")" "$TWO" "its record holds the channel"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel add desk-two helper
assert_rc 0 "$RC" "it adds another thread of the machine"
assert_contains "$OUT" "helper#${S2:0:8}: in desk-two" "placed when the command returns"
assert_equals "$(set_of "$S2")" "$TWO" "the other thread's record holds it"
assert_equals "$(log_kinds "$TWO")" "channel-request" "the channel's log holds the request alone"
assert_contains "$(kinds_of "$APP" "$S2")" "channels" "the answer is a statement in the thread's own project"
echo "the roster, the listing and the pool:"
run_in "$APPDIR" in_session "$S1" "$SMINOS" list
assert_rc 0 "$RC" "a member lists"
assert_equals "$(grep -v '^sminos: warning' <<<"$OUT" | sed -n 1p)" "app" "its project's section as before"
assert_contains "$(sed -n '/^# desk-two$/,$p' <<<"$OUT")" "helper [${S2:0:8}]" "then # desk-two, with its roster"
assert_contains "$(sed -n '/^# desk-two$/,$p' <<<"$OUT")" "you: worker [${S1:0:8}]" "the section before the caller's line"
run_in "$APPDIR" in_session "$S3" "$SMINOS" list
assert_equals "$(grep -c '^#' <<<"$OUT" || true)" 0 "a session in no channel lists no section"
run_in "$T" "$SMINOS" list --channel desk-two
assert_rc 0 "$RC" "--channel from a terminal"
assert_contains "$OUT" "worker [${S1:0:8}]" "prints the channel's rows"
assert_contains "$OUT" "helper [${S2:0:8}]" "both of them"
OUT="$("$SMINOS" list --channel desk-two --json 2>/dev/null)"
assert_equals "$(python3 -c 'import json, sys; print(sorted({c for r in json.load(sys.stdin) for c in r["channels"]}))' <<<"$OUT")" "['$TWO']" "--json: the flat list, each row carrying channels"
run_in "$T" "$SMINOS" channel show desk-two
assert_rc 0 "$RC" "channel show"
assert_contains "$OUT" "# desk-two  $TWO" "its heading"
assert_contains "$OUT" "by worker#${S1:0:8}  applied" "the request for helper, applied"
assert_contains "$OUT" "alpha  2 live, 0 stopped" "the pool's count"
printf '{"projects": [], "machines": [{"name": "alpha"}, {"name": "beta"}], "at": "2026-11-21T00:00:00.000Z"}\n' \
  > "$SMINOS_HOME/daemon/org.json"
BEFORE="$(logs_sum)"
run_in "$APPDIR" "$SMINOS" channel env add desk-two beta
assert_rc 1 "$RC" "channel env from a terminal is refused"
run_in "$APPDIR" in_session "$S3" "$SMINOS" channel env add desk-two beta
assert_rc 1 "$RC" "and from a thread not in the channel"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel env add desk-two nowhere
assert_rc 1 "$RC" "and for a machine the org does not list"
assert_equals "$(logs_sum)" "$BEFORE" "no log file changed"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel env add desk-two beta
assert_rc 0 "$RC" "a member adds a machine to the pool by hand"
run_in "$T" "$SMINOS" channel show desk-two
assert_contains "$OUT" "beta  0 live, 0 stopped, added by hand" "the pool it prints"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel env remove desk-two beta
run_in "$T" "$SMINOS" channel show desk-two
assert_equals "$(grep -c beta <<<"$OUT" || true)" 0 "and removes it"
run_in "$T" "$SMINOS" list --org
assert_contains "$OUT" "# desk-two" "list --org ends with a section for the channel"
run_in "$APPDIR" "$SMINOS" channel add desk-two helper
assert_rc 0 "$RC" "a terminal names the thread"
assert_contains "$OUT" "helper#${S2:0:8}: already in desk-two" "which is in it already"
run_in "$APPDIR" "$SMINOS" channel add desk-two
assert_rc 1 "$RC" "a terminal that names no thread is refused"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel create desk-two
assert_rc 1 "$RC" "a name a channel with a member answers is refused"
assert_contains "$OUT" "cannot create channel desk-two: desk-two#${TWO:0:8} (channel) already answers to that name" "naming it"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel create desk-three helper
assert_rc 1 "$RC" "a session's create that names a thread is refused"
run_in "$APPDIR" "$SMINOS" channel create desk-three
assert_rc 1 "$RC" "a terminal's create that names no thread is refused"
run_in "$APPDIR" "$SMINOS" channel add no-such-channel helper
assert_rc 4 "$RC" "an unknown channel, exit 4"
run_in "$APPDIR" "$SMINOS" channel create desk-three helper
assert_rc 0 "$RC" "a terminal creates one with a thread of this machine"
assert_contains "$OUT" "created channel desk-three ($(channel_id desk-three)) with helper#${S2:0:8}" "its first member"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel remove desk-two helper
assert_rc 0 "$RC" "a thread removes another"
assert_contains "$OUT" "helper#${S2:0:8}: out of desk-two" "out when the command returns"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel remove desk-two
assert_contains "$OUT" "worker#${S1:0:8}: out of desk-two" "and itself, with none named"
assert_equals "$(set_of "$S1")" "" "its set is empty"
run_in "$T" "$SMINOS" list --org
assert_equals "$(grep -c '^# desk-two$' <<<"$OUT" || true)" 0 "its last member left: no section in list --org"
assert_contains "$OUT" "# desk-three" "while a channel with a member keeps its own"
run_in "$T" "$SMINOS" list app --json
assert_contains "$OUT" "\"session\": \"$S1\"" "a removal retires no one"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel create desk-two
assert_rc 0 "$RC" "the emptied channel's name"
assert_contains "$OUT" "desk-two exists and has no member: worker#${S1:0:8} is in it again" "brings it back under its id"
assert_equals "$(set_of "$S1")" "$TWO" "the same id"
assert_equals "$( (cat "$STUB_STATE/calls" 2>/dev/null || true) | grep -c resume || true)" 0 "no session's turn was started"

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
# Named through a channel it is in (CH2's M1), a verb finds it in the channel's roster and writes where it writes
# today, in its own project; `who --thread` (EN.G1) names its thread through find_target too. Through a channel it
# is not in, no member answers, and the refusal names where the name does.
TWO_BEFORE="$(find "$SMINOS_HOME/projects/$TWO" -type f -name '*.jsonl' -exec shasum {} + | LC_ALL=C sort)"
for q in desk-two "$TWO" "desk-two#${TWO:0:8}"; do
  run_in "$APPDIR" "$SMINOS" charge "$q/worker" "minding via $q"
  assert_rc 0 "$RC" "charge names the thread through $q"
  run_in "$APPDIR" "$SMINOS" status "$q/worker" "now via $q"
  assert_rc 0 "$RC" "status names the thread through $q"
  run_in "$APPDIR" "$SMINOS" who --thread "$q/worker"
  assert_rc 0 "$RC" "who --thread names it through $q"
done
assert_equals "$(kinds_of "$APP" "$S1" | tr ' ' '\n' | grep -c '^in-charge$')" 6 "three more in-charge lines in its project's log"
assert_equals "$(kinds_of "$APP" "$S1" | tr ' ' '\n' | grep -c '^status$')" 6 "three more status lines there"
for verb in "who --thread desk-integration/worker" "charge desk-integration/worker x" "status desk-integration/worker x" \
    "retire desk-integration/worker"; do
  # shellcheck disable=SC2086
  run_in "$APPDIR" "$SMINOS" $verb
  assert_rc 4 "$RC" "$verb is refused, exit 4"
  assert_contains "$OUT" "no member worker in channel desk-integration; elsewhere: app/worker#$SHORT" "naming where it answers ($verb)"
done
run_in "$APPDIR" "$SMINOS" retire "desk-two/worker"
assert_rc 0 "$RC" "retire names it through the channel"
assert_contains "$(kinds_of "$APP" "$S1")" "retired" "its retirement is in its own project's log"
assert_equals "$(find "$SMINOS_HOME/projects/$TWO" -type f -name '*.jsonl' -exec shasum {} + | LC_ALL=C sort)" \
  "$TWO_BEFORE" "the channel's log files byte for byte as they were"
assert_equals "$(channel_files)" 0 "nothing was ever written in the channel's log"
assert_equals "$(log_kinds "$TWO")" "channel-env channel-request" "nor, with the thread in a channel, anything but requests and the pool's events in that one's"

echo "what is said into a channel (CH2's M4):"
said_in() { # log-id — each message of the log in order: its kind, whom its to names, whether it carries from_project and copy
  python3 - "$SMINOS_HOME/projects/$1/log" <<'PY'
import glob, json, os, sys
rows = []
for p in glob.glob(os.path.join(sys.argv[1], "*.jsonl")):
    for line in open(p):
        e = json.loads(line)
        if e["kind"] in ("say", "human"):
            to = e["to"] if e["to"] == "*" else ",".join(
                str(r.get("alias")) + ("+thread" if r.get("thread") else "") for r in e["to"])
            rows.append((e["ts"], e["kind"], to, "from_project" if "from_project" in e else "-",
                         "copy" if "copy" in e else "-"))
print("\n".join(" ".join(r[1:]) for r in sorted(rows)))
PY
}
THREE="$(channel_id desk-three)"
run_in "$T" "$SMINOS" say --in desk-three "a person's note"
assert_rc 0 "$RC" "a terminal says into a channel"
assert_contains "$OUT" "in desk-three" "recorded in the channel's log"
assert_equals "$(said_in "$THREE")" "human * - -" "untagged: one event under the machine's human writer, no from_project"
run_in "$T" in_session "$S3" "$SMINOS" say --in desk-three "@helper from outside"
assert_rc 0 "$RC" "a session in no channel says into it"
assert_contains "$OUT" "you are not in desk-three: replies to this come to you directly, in alpha. sminos channel add desk-three places you in it" "told it is no member, where replies come and how to add itself"
assert_contains "$OUT" "copy " "its copy kept in its own project"
assert_equals "$(said_in "$THREE" | tail -1)" "say helper+thread from_project -" "its message names the member's thread and carries its project"
BEFORE="$(logs_sum)"
run_in "$APPDIR" in_session "$S2" "$SMINOS" say "@desk-three/there hi"
assert_rc 4 "$RC" "a name no member of the channel answers is refused, exit 4"
assert_contains "$OUT" "no member there in channel desk-three; elsewhere: @alpha/there#${S3:0:8}" "naming where it answers"
run_in "$APPDIR" in_session "$S2" "$SMINOS" say --in desk-three "@there hi"
assert_contains "$OUT" "Drop --in to reach it in its own project" "and with --in, how to reach it"
run_in "$APPDIR" in_session "$S2" "$SMINOS" say --project desk-three "hello"
assert_rc 1 "$RC" "a selector naming a channel is refused, exit 1"
assert_contains "$OUT" "desk-three is a channel, and a selector names projects: sminos say --in desk-three \"@all …\" reaches its live members" "naming --in"
run_in "$APPDIR" in_session "$S2" "$SMINOS" say "@desk-three#${THREE:0:8}/helper hi"
assert_rc 1 "$RC" "the unquoted name#short qualifier is refused, exit 1"
assert_contains "$OUT" "opens no tag (a tag's qualifier takes no #): nothing was recorded" "it opens no tag"
assert_equals "$(logs_sum)" "$BEFORE" "no log file changed by a refusal"
run_in "$T" "$SMINOS" chat desk-three -n 5
assert_rc 0 "$RC" "chat <channel>"
assert_contains "$OUT" "human → *  a person's note" "reads the person's note"
assert_contains "$OUT" "there (not in desk-three) → @helper" "and the outsider's message, saying it is not in the channel"
run_in "$T" "$SMINOS" list desk-three
assert_rc 0 "$RC" "list <channel>"
assert_contains "$OUT" "# desk-three" "prints the channel as --channel does"
assert_contains "$OUT" "helper [${S2:0:8}]" "with its member"
run_in "$APPDIR" "$SMINOS" say "@helper the plain tag"
assert_rc 0 "$RC" "the plain tag still reaches the thread"
assert_contains "$OUT" "in app" "in its own project"

echo "the lead (CH2's M8):"
at_tty() { # answer command... — OUT and RC of the command on a controlling pty of its own, the answer typed at
  set +e   # its prompt (pty_answer.py: killed and reaped at its deadline, exit 124)
  OUT="$(python3 -B "$SCRIPT_DIR/pty_answer.py" "$@" 2>&1)"; RC=$?; set -e
}
no_tty() { # command... — OUT and RC of the command with no controlling terminal (a new session)
  set +e
  OUT="$(python3 -c 'import subprocess, sys; sys.exit(subprocess.run(sys.argv[1:], start_new_session=True).returncode)' "$@" 2>&1)"
  RC=$?; set -e
}
BEFORE="$(logs_sum)"
run_in "$APPDIR" in_session "$S1" "$SMINOS" channel lead desk-three helper
assert_rc 1 "$RC" "channel lead inside a session is refused"
assert_contains "$OUT" "channel lead is for a person at a terminal, and this runs inside a session: nothing was written" "saying it is the person's"
no_tty "$SMINOS" channel lead desk-three helper
assert_rc 1 "$RC" "and where there is no terminal"
assert_contains "$OUT" "needs its owner at a terminal to confirm it, and this has none: nothing was written" "saying so"
at_tty n "$SMINOS" channel lead desk-three helper
assert_rc 1 "$RC" "a person who does not type yes"
assert_contains "$OUT" "not confirmed: nothing was written" "is told nothing was written"
assert_equals "$(logs_sum)" "$BEFORE" "no log file changed by a refusal"
at_tty y "$SMINOS" channel lead desk-three helper
assert_rc 0 "$RC" "a typed yes at a terminal names the lead"
assert_contains "$OUT" "Make helper#${S2:0:8} the lead of desk-three?" "after asking"
assert_contains "$OUT" "helper#${S2:0:8} leads desk-three" "and says so"
run_in "$T" "$SMINOS" channel show desk-three
assert_equals "$(grep -A1 "^# desk-three " <<<"$OUT" | sed -n 2p)" "lead  helper#${S2:0:8}" "channel show prints the lead after its heading"
run_in "$T" "$SMINOS" say --in desk-three "do it"
assert_rc 0 "$RC" "the person's untagged post"
assert_equals "$(said_in "$THREE" | tail -1)" "human helper+thread - -" "is addressed to the lead"
run_in "$APPDIR" in_session "$S1" "$SMINOS" say --in desk-three "a session's note"
assert_equals "$(said_in "$THREE" | tail -1)" "say * from_project -" "a session's untagged post is not the lead's"
at_tty y "$SMINOS" channel lead desk-three none
assert_rc 0 "$RC" "none clears it"
assert_contains "$OUT" "desk-three has no lead" "saying so"
run_in "$T" "$SMINOS" channel show desk-three
assert_equals "$(grep -c '^lead ' <<<"$OUT" || true)" 0 "and channel show prints no lead"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-channels.sh: $PASSES passed, 0 failed"
else
  echo "test-channels.sh: $PASSES passed, $FAILURES failed"
  exit 1
fi
