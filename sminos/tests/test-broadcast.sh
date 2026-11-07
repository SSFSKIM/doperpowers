#!/usr/bin/env bash
#
# Scoped broadcast (§5a of the sminos org directory,
# docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md): `say` with
# list's selector (--org, --project, --machine, --here, --state) reaches the
# live sessions `list` shows with the same flags, the sender left out; one
# event is recorded in each project that has a recipient, its `to` that
# project's recipients and `scope` the selector, with a copy in the sender's
# own project when no recipient is there; a recipient on another machine is
# recorded for that machine's daemon, which delivers it; the frame and `chat`
# name the scope (`@all on beta`, `@org`); the frame's reply line answers the
# sender alone; a selector with opening @tags is refused, as is a scope with
# no live session. Two machines simulated on one Mac — two SMINOS_HOMEs,
# alpha and beta, each cut over to its own endpoint_standin.py and running its
# daemon, delivering to scripted inboxes — what one endpoint took reaching the
# other as arrivals (rl10-machines.sh's hand-off); then a third home, gamma,
# whose logs alone pin the live-only rule against published states.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smb.XXXXXX)"
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

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
as() { # a|b|c host — one machine: its HOME, its SMINOS_HOME, its host name
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
esac
echo "$*" >> "$STUB_STATE/launches"
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

# A running session with an inbox (inbox_standin.py, which appends each frame
# it receives and answers nothing, as the engine's does): its engine record
# (the inbox's pid is the session's process, its status `status`), its
# transcript launched in `dir`. Frames land in $T/<inbox>.received, the inbox
# the name unless another is given.
live_session() { # name session dir [status] [inbox]
  local box=${5:-$1}
  : > "$T/$box.received"
  python3 "$SCRIPT_DIR/inbox_standin.py" "$T/$box.sock" "$T/$box.received" & PIDS+=("$!")
  local pid=$!
  until_true test -S "$T/$box.sock"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"%s","cwd":"%s","messagingSocketPath":"%s","entrypoint":"cli"}\n' \
    "$pid" "$2" "$1" "${4:-idle}" "$3" "$T/$box.sock" > "$HOME/.claude/sessions/$box.json"
  local tx="$HOME/.claude/projects/p-$2/$2.jsonl"
  mkdir -p "$(dirname "$tx")"
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
    "${2:0:8}" "$2" "$3" > "$tx"
}
# The frames an inbox received, each one's content on lines of its own.
frames() {
  python3 - "$T/$1.received" <<'PY'
import json, sys
try:
    lines = open(sys.argv[1]).read().splitlines()
except OSError:
    lines = []
for line in lines:
    if line.strip():
        print(json.loads(line)["message"]["content"])
PY
}
got() { frames "$1" | grep -Fq -- "$2"; }   # name text — whether the inbox holds a frame carrying the text

smns_id() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$1/.smns"; }
write_smns() { # dir name — a .smns naming only the org
  python3 -c 'import json, sys, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": sys.argv[1], "remote": "", "hub": {"org": "org-1"}}, indent=2))' \
    "$2" > "$1/.smns"
}
start_daemon() {
  "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & PIDS+=("$!")
}
# The events of a project's log on this machine that carry a text, as JSON lines.
events_with() { # project-id text
  cat "$SMINOS_HOME/projects/$1/log/"*.jsonl 2>/dev/null | grep -F -- "$2" || true
}
field_of() { # json-line field — one field of an event, as JSON
  python3 -c 'import json, sys; print(json.dumps(json.loads(sys.argv[1]).get(sys.argv[2])))' "$1" "$2"
}
to_of() { # json-line — the sessions of an event's `to`, sorted, one line
  python3 -c 'import json, sys; print(" ".join(sorted(r["session"] for r in json.loads(sys.argv[1])["to"])))' "$1"
}
in_session() { # session dir command... — the command as that session runs it, in dir
  local sid=$1 d=$2; shift 2
  set +e; OUT="$(cd "$d" && env CLAUDE_CODE_SESSION_ID="$sid" "$@" 2>&1)"; RC=$?; set -e
}
# Whether this machine reads the session as a live member of the project (its
# word, for another machine's, the one that machine published); a list that
# is not there yet (no JSON) is none.
live_in() { # project session
  (cd "$T/x" && "$SMINOS" list "$1" --json --all 2>/dev/null) | python3 -c 'import json, sys
print(any(m["session"] == sys.argv[1] and m["state"] in ("busy", "idle", "waiting") for m in json.load(sys.stdin)))' "$2" 2>/dev/null \
    | grep -q True
}
mkdir -p "$T/x"
sorted() { printf '%s\n' "$@" | sort | tr '\n' ' ' | sed 's/ $//'; }

# ---- RL10: two machines' broadcasts, each cut over to its endpoint (#153 M3d)
# alpha and beta are real sminos homes, each with its daemon and its
# endpoint_standin.py, never enrolled at a hub. What one endpoint accepted
# reaches the other's connection as arrivals through the stand-in's own echo
# (rl10_relay); each case asserts what the producer's endpoint took and what
# the consumer resolved, recorded or delivered. The org's directory is the
# stand-ins': both projects and both machine projects.
echo "RL10: two machines through their endpoints:"
# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"
rl10_as ra alpha
rl10_cut_over
EPA=$EP
RAMP="$(rl10_mp alpha)"
RRA="$T/ra/projA"
gitq init -q "$RRA"
write_smns "$RRA" projA
RAID="$(smns_id "$RRA")"
RSA=6a0000a1-0000-4000-8000-0000000000a1
RA2=6a0000a2-0000-4000-8000-0000000000a2
live_session sa "$RSA" "$RRA" idle r-sa
live_session a2 "$RA2" "$RRA" idle r-a2
RABARE="$T/ra/bare"
mkdir -p "$RABARE"
RWA=6a0000a4-0000-4000-8000-0000000000a4
RWW=6a0000a5-0000-4000-8000-0000000000a5
live_session wa "$RWA" "$RABARE" idle r-wa
live_session ww "$RWW" "$RABARE" waiting r-ww
run_in "$RRA" "$SMINOS" list
run_in "$RABARE" "$SMINOS" list
rl10_as rb beta
rl10_cut_over
EPB=$EP
RBMP="$(rl10_mp beta)"
RRB="$T/rb/projB"
gitq init -q "$RRB"
write_smns "$RRB" projB
RBID="$(smns_id "$RRB")"
RRBS=6b0000b1-0000-4000-8000-0000000000b1
live_session rb "$RRBS" "$RRB" idle r-rb
RRA2="$T/rb/projA"
gitq init -q "$RRA2"
cp "$RRA/.smns" "$RRA2/.smns"
RAB=6b0000b2-0000-4000-8000-0000000000b2
live_session ab "$RAB" "$RRA2" idle r-ab
RMB=6b0000b8-0000-4000-8000-0000000000b8
live_session mb "$RMB" "$T/rb/home" idle r-mb
run_in "$RRB" "$SMINOS" list
run_in "$RRA2" "$SMINOS" list
run_in "$T/rb/home" "$SMINOS" list
RDIR="$(python3 - "$RAID" "$RBID" "$RAMP" "$RBMP" <<'PY'
import json, sys
a, b, amp, bmp = sys.argv[1:5]
print(json.dumps({"projects": [{"id": a, "name": "projA", "kind": "hub", "retired": False},
                               {"id": b, "name": "projB", "kind": "hub", "retired": False},
                               {"id": amp, "name": "alpha", "kind": "machine", "machine": "alpha", "retired": False},
                               {"id": bmp, "name": "beta", "kind": "machine", "machine": "beta", "retired": False}],
                  "machines": [{"name": "alpha", "online": True}, {"name": "beta", "online": True}]}))
PY
)"
rl10_as ra alpha
rl10_serve "\"org\": $RDIR"
start_daemon
rl10_as rb beta
rl10_serve "\"org\": $RDIR"
start_daemon
relayed() { rl10_relay "$EPA" "$EPB"; "$@"; }
r_up() { [ -n "$(rl10_up "$@")" ]; }   # ep-dir pid text — the endpoint took an event of the project carrying it
r_state_up() { # ep-dir pid session — the endpoint took the session's published word in the project
  [ "$(rl10_q "$1" "any(e['kind'] == 'state' and e.get('session') == '$3' for c, e in up('$2'))")" = true ]; }
r_signer() { # json-line → the name of the machine the endpoint verified it from
  python3 -c 'import json, sys; print(json.loads(sys.argv[1]).get("verified", {}).get("signer", {}).get("name"))' "$1"
}

rl10_as ra alpha
until_true r_state_up "$EPB" "$RBID" "$RRBS" || true
until_true r_state_up "$EPB" "$RAID" "$RAB" || true
until_true r_state_up "$EPB" "$RBMP" "$RMB" || true
r_state_up "$EPB" "$RBID" "$RRBS" && r_state_up "$EPB" "$RAID" "$RAB" && r_state_up "$EPB" "$RBMP" "$RMB" \
  && pass "RL10: beta's endpoint takes the word rb, ab and mb publish, each in its project" \
  || fail "RL10: beta's endpoint takes the word rb, ab and mb publish, each in its project"
r_beta_live() { live_in "$RBID" "$RRBS" && live_in "$RAID" "$RAB" && live_in "$RBMP" "$RMB"; }
until_true relayed r_beta_live || true
r_beta_live && pass "RL10: alpha reads beta's sessions live: rb in projB, ab in projA, mb in beta" \
  || fail "RL10: alpha reads beta's sessions live: rb in projB, ab in projA, mb in beta"
rl10_as rb beta
until_true relayed live_in "$RAID" "$RSA" || true

echo "RL10: --machine:"
rl10_as ra alpha
in_session "$RSA" "$RRA" "$SMINOS" say --machine beta "beta reboots at three"
assert_rc 0 "$RC" "RL10: say --machine beta is accepted"
assert_contains "$OUT" "@all on beta: 3 sessions" "RL10: it says how many sessions it sends to, and under which label"
assert_contains "$OUT" "rb#${RRBS:0:8}: recorded (on beta)" "RL10: rb is recorded for beta's daemon"
assert_contains "$OUT" "ab#${RAB:0:8}: recorded (on beta)" "RL10: as is ab"
assert_contains "$OUT" "mb#${RMB:0:8}: recorded (on beta)" "RL10: and mb"
DB="$(events_with "$RBID" "beta reboots at three")"
DA="$(events_with "$RAID" "beta reboots at three")"
DM="$(events_with "$RBMP" "beta reboots at three")"
assert_equals "$(to_of "$DB")" "$RRBS" "RL10: projB's event is addressed to its recipient, rb"
assert_equals "$(to_of "$DM")" "$RMB" "RL10: beta's machine project's to mb"
assert_equals "$(to_of "$DA")" "$RAB" "RL10: projA's to ab: the sender's own project has a recipient there"
assert_equals "$(field_of "$DB" scope)" '{"machines": ["beta"]}' "RL10: each event names the scope"
assert_equals "$(field_of "$DB" wake)$(field_of "$DB" kind)" 'true"say"' "RL10: and wakes, a session's broadcast a say"
assert_equals "$(field_of "$DB" from_project)$(field_of "$DA" from_project)" "\"$RAID\"null" \
  "RL10: an event outside the sender's project names it, the one in its own does not"
assert_equals "$(echo "$DA" | grep -c . | tr -d ' ')$(field_of "$DA" copy)" "1null" "RL10: projA holds the one event, no copy beside it"
R_LISTED="$(cd "$T/x" && "$SMINOS" list --machine beta --json | python3 -c 'import json, sys
print(" ".join(sorted(m["session"] for m in json.load(sys.stdin) if m["state"] in ("busy", "idle", "waiting"))))')"
assert_equals "$(sorted "$RRBS" "$RAB" "$RMB")" "$R_LISTED" "RL10: list --machine beta shows those three as its live rows"
for p in "$RBID" "$RAID" "$RBMP"; do
  until_true r_up "$EPA" "$p" "beta reboots at three" || true
done
assert_equals "$(for p in "$RBID" "$RAID" "$RBMP"; do to_of "$(rl10_up "$EPA" "$p" "beta reboots at three")"; done | tr '\n' ' ')" \
  "$RRBS $RAB $RMB " "RL10: alpha's endpoint takes the three events, each with its project's recipients"
assert_equals "$(field_of "$(rl10_up "$EPA" "$RBID" "beta reboots at three")" scope)" '{"machines": ["beta"]}' \
  "RL10: and its scope"
rl10_as rb beta
r_three() { got r-rb "beta reboots at three" && got r-ab "beta reboots at three" && got r-mb "beta reboots at three"; }
until_true relayed r_three || true
r_three && pass "RL10: beta's daemon delivers it to all three" || fail "RL10: beta's daemon delivers it to all three"
assert_equals "$(r_signer "$(events_with "$RBID" "beta reboots at three")")" alpha \
  "RL10: from the event beta holds as the endpoint verified it, from alpha"
FRAME="$(frames r-rb)"
assert_contains "$FRAME" "from sa (owners unverified) → @all on beta" \
  "RL10: the frame names the scope, after the owners clause the endpoint's attestation (none) gives the sender"
assert_contains "$FRAME" "say \"@$RAID/${RSA:0:8} <your reply>\"" "RL10: its reply line answers the sender alone"
assert_contains "$(frames r-ab)" "say \"@$RAID/${RSA:0:8} <your reply>\"" "RL10: in the sender's own project too"
assert_equals "$(frames r-a2)$(frames r-wa)$(frames r-ww)$(frames r-sa)" "" "RL10: no session on alpha, the sender's included, is reached"
run_in "$RRB" "$SMINOS" chat projB -n 5
assert_contains "$OUT" "sa (owners unverified) → @all on beta  beta reboots at three" "RL10: chat in a recipient's project names the scope"

echo "RL10: the reply:"
REPLY="$(frames r-rb | sed -n "s/.*\[To reply, run in Bash: \(.*\) <your reply>\"\]/\1/p" | head -1)"
in_session "$RRBS" "$RRB" bash -c "$REPLY noted, draining\""
assert_rc 0 "$RC" "RL10: rb's reply line runs as written"
RE="$(events_with "$RAID" "noted, draining" | grep -v '"copy"' || true)"
assert_equals "$(to_of "$RE")" "$RSA" "RL10: the reply is addressed to the sender alone"
assert_equals "$(field_of "$RE" scope)$(field_of "$RE" wake)" "nullnull" "RL10: no scope, no wake: it is no broadcast"
until_true r_up "$EPB" "$RAID" "noted, draining" || true
r_up "$EPB" "$RAID" "noted, draining" && pass "RL10: beta's endpoint takes it in projA" || fail "RL10: beta's endpoint takes it in projA"
rl10_as ra alpha
until_true relayed got r-sa "noted, draining" || true
got r-sa "noted, draining" && pass "RL10: and sa receives it on alpha" || fail "RL10: and sa receives it on alpha"
assert_equals "$(frames r-a2 | grep -c "noted, draining")" 0 "RL10: a2 does not"

echo "RL10: --project with --machine:"
in_session "$RSA" "$RRA" "$SMINOS" say --project projB --machine beta "projB on beta only"
assert_rc 0 "$RC" "RL10: say --project projB --machine beta is accepted"
assert_contains "$OUT" "@all in projB on beta: 1 session" "RL10: one session"
DB="$(events_with "$RBID" "projB on beta only")"
assert_equals "$(to_of "$DB")" "$RRBS" "RL10: rb alone"
assert_equals "$(field_of "$DB" scope)" "{\"projects\": [\"$RBID\"], \"machines\": [\"beta\"]}" \
  "RL10: the scope names its projects by id"
assert_equals "$(events_with "$RBMP" "projB on beta only")" "" "RL10: beta's machine project is outside it"
COPY="$(events_with "$RAID" "projB on beta only")"
assert_equals "$(field_of "$COPY" copy)" "\"$RBID:alpha/$RSA:$(field_of "$DB" seq)\"" \
  "RL10: the sender's project, with no recipient, holds a copy naming the delivering event"
assert_equals "$(field_of "$COPY" to)" "[{\"session\": \"$RRBS\", \"alias\": \"rb\", \"project\": \"$RBID\"}]" \
  "RL10: its recipients with their project"
assert_equals "$(field_of "$COPY" scope)" "$(field_of "$DB" scope)" "RL10: and the scope"
run_in "$RRA" "$SMINOS" chat projA -n 1
assert_contains "$OUT" "sa → @all in projB on beta → projB  projB on beta only" "RL10: chat in projA shows the scope and the copy's destination"
until_true r_up "$EPA" "$RAID" "projB on beta only" || true
assert_equals "$(field_of "$(rl10_up "$EPA" "$RAID" "projB on beta only")" copy)" "$(field_of "$COPY" copy)" \
  "RL10: alpha's endpoint takes the copy"
until_true r_up "$EPA" "$RBID" "projB on beta only" || true
rl10_as rb beta
until_true relayed got r-rb "projB on beta only" || true
got r-rb "projB on beta only" && pass "RL10: and rb receives the delivering event on beta" \
  || fail "RL10: and rb receives the delivering event on beta"
r_copy_on_beta() { [ -n "$(events_with "$RAID" "projB on beta only")" ]; }
until_true relayed r_copy_on_beta || true
assert_equals "$(frames r-ab | grep -c "projB on beta only")" 0 "RL10: ab, in the copy's project on beta, is not reached by it"

echo "RL10: a copy of several:"
rl10_as ra alpha
in_session "$RSA" "$RRA" "$SMINOS" say --project projB,beta "two projects"
assert_rc 0 "$RC" "RL10: say --project projB,beta is accepted"
assert_contains "$OUT" "@all in projB,beta: 2 sessions" "RL10: two sessions"
DB="$(events_with "$RBID" "two projects")"
DM="$(events_with "$RBMP" "two projects")"
COPY="$(events_with "$RAID" "two projects")"
assert_equals "$(field_of "$COPY" copy)" \
  "[\"$RBID:alpha/$RSA:$(field_of "$DB" seq)\", \"$RBMP:alpha/$RSA:$(field_of "$DM" seq)\"]" \
  "RL10: a copy of events in several projects names each delivering event"
assert_equals "$(to_of "$COPY")" "$(sorted "$RRBS" "$RMB")" "RL10: and every recipient"
assert_equals "$(python3 - "$RAID" "$RRBS" "$RMB" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
p = sminos.find_project(sys.argv[1])
print([e["text"] for s in sys.argv[2:] for e in sminos._owed(sminos.log_read(p), s, {}) if e["text"] == "two projects"])
PY
)" "[]" "RL10: the copy is owed to no one"
run_in "$RRA" "$SMINOS" chat projA -n 1
assert_contains "$OUT" "sa → @all in projB,beta → projB, beta  two projects" "RL10: chat names both destinations"
rl10_as rb beta
r_two() { got r-rb "two projects" && got r-mb "two projects"; }
until_true relayed r_two || true
r_two && pass "RL10: beta delivers both delivering events" || fail "RL10: beta delivers both delivering events"
assert_equals "$(frames r-rb | grep -c "two projects")$(frames r-mb | grep -c "two projects")" 11 "RL10: each once"

echo "RL10: --org and --here:"
rl10_as ra alpha
in_session "$RSA" "$RRA" "$SMINOS" say --org "reviews go to their own pins again"
assert_rc 0 "$RC" "RL10: say --org is accepted"
assert_contains "$OUT" "@org: 6 sessions" "RL10: every live session of the org but the sender"
assert_equals "$(to_of "$(events_with "$RAID" "reviews go to their own pins")")" "$(sorted "$RA2" "$RAB")" \
  "RL10: projA's event: a2 here and ab on beta"
assert_equals "$(to_of "$(events_with "$RAMP" "reviews go to their own pins")")" "$(sorted "$RWA" "$RWW")" \
  "RL10: alpha's machine project's: wa, and ww, which waits"
assert_equals "$(field_of "$(events_with "$RAID" "reviews go to their own pins")" scope)" "{}" "RL10: the scope of the whole org is {}"
until_true got r-a2 "reviews go to their own pins" || true
got r-a2 "reviews go to their own pins" && pass "RL10: a session on the sender's machine is delivered at once" \
  || fail "RL10: a session on the sender's machine is delivered at once"
until_true got r-ww "reviews go to their own pins" || true
assert_contains "$(frames r-ww)" "from sa → @org" "RL10: the frame says @org"
rl10_as rb beta
r_org() { got r-ab "reviews go to their own pins" && got r-rb "reviews go to their own pins" && got r-mb "reviews go to their own pins"; }
until_true relayed r_org || true
r_org && pass "RL10: and beta delivers it to ab, rb and mb" || fail "RL10: and beta delivers it to ab, rb and mb"
assert_contains "$(frames r-ab)" "from sa (owners unverified) → @org" "RL10: saying @org"
rl10_as ra alpha
in_session "$RSA" "$RRA" "$SMINOS" say --here "alpha only"
assert_rc 0 "$RC" "RL10: say --here is accepted"
assert_contains "$OUT" "@all on alpha: 3 sessions" "RL10: this machine's live sessions"
assert_equals "$(field_of "$(events_with "$RAMP" "alpha only")" scope)" '{"here": "alpha"}' "RL10: --here names this machine"
assert_equals "$(events_with "$RBID" "alpha only")$(events_with "$RBMP" "alpha only")" "" "RL10: nothing for beta"
in_session "$RSA" "$RRA" "$SMINOS" say --state waiting "who waits"
assert_rc 0 "$RC" "RL10: say --state waiting is accepted"
assert_equals "$(to_of "$(events_with "$RAMP" "who waits")")" "$RWW" "RL10: it reaches the waiting session alone"
assert_contains "$OUT" "@org (waiting): 1 session" "RL10: its label names the state"

echo "RL10: refusals:"
in_session "$RSA" "$RRA" "$SMINOS" say --machine beta "@rb tagged and scoped"
assert_rc 2 "$RC" "RL10: a selector with an opening @tag is refused"
assert_contains "$OUT" "a selector picks the recipients" "RL10: saying why"
in_session "$RSA" "$RRA" "$SMINOS" say --org "@all both"
assert_rc 2 "$RC" "RL10: a selector with @all too"
in_session "$RSA" "$RRA" "$SMINOS" say --machine nosuch "anyone there"
assert_rc 4 "$RC" "RL10: a scope with no live session is refused"
assert_contains "$OUT" "no live session" "RL10: saying so"
in_session "$RSA" "$RRA" "$SMINOS" say --state stopped "the stopped"
assert_rc 2 "$RC" "RL10: a scope of non-live states is refused: a broadcast wakes only the live"
assert_equals "$(events_with "$RAID" "tagged and scoped")$(events_with "$RBID" "tagged and scoped")$(events_with "$RAID" "anyone there")$(events_with "$RAID" "the stopped")" \
  "" "RL10: a refused broadcast is recorded nowhere"
run_in "$RRA" "$SMINOS" say --in projA --machine beta "in and scope"
assert_rc 2 "$RC" "RL10: an operator's --in with a selector is refused"

echo "RL10: the operator:"
run_in "$RRA" "$SMINOS" say --machine beta --project projB "from the owner"
assert_rc 0 "$RC" "RL10: the operator may send at any scope"
OE="$(events_with "$RBID" "from the owner")"
assert_equals "$(field_of "$OE" kind)$(field_of "$OE" writer)" '"human""alpha/human"' "RL10: as a human event under its writer"
assert_equals "$(events_with "$RAID" "from the owner")" "" "RL10: with no copy: the operator has no project of its own"
until_true r_up "$EPA" "$RBID" "from the owner" || true
assert_equals "$(field_of "$(rl10_up "$EPA" "$RBID" "from the owner")" writer)" '"alpha/human"' \
  "RL10: alpha's endpoint takes it under alpha's operator writer"
rl10_as rb beta
until_true relayed got r-rb "from the owner" || true
got r-rb "from the owner" && pass "RL10: beta delivers it" || fail "RL10: beta delivers it"
r_words_asked() { [ "$(rl10_q "$EPB" "any(f.get('t') == 'words?' and f.get('event', {}).get('text') == 'from the owner' for c, f in F)")" = true ]; }
r_words_asked && pass "RL10: on its endpoint's words verdict, a person's words being the endpoint's to admit" \
  || fail "RL10: on its endpoint's words verdict, a person's words being the endpoint's to admit"
for m in ra rb; do
  assert_not_contains "$(cat "$T/$m/s/daemon.log" 2>/dev/null)" "Traceback" "RL10: nothing in $m's daemon.log is a traceback"
done
unset MAWS_USER_DATA

# ---- the logs alone: only the live receive it
echo "the logs alone:"
as c gamma
reg() { # id name — a hub project registered here with no checkout
  python3 - "$SMINOS_HOME/projects/$1" "$1" "$2" <<'PY'
import json, os, sys
d, pid, name = sys.argv[1:4]
os.makedirs(d, exist_ok=True)
json.dump({"project": pid, "name": name, "remote": "", "root": "", "hub": {"url": "", "org": "org-1"}},
          open(os.path.join(d, "project.json"), "w"))
PY
}
member() { # project session alias state — a session of machine delta, joined and publishing its word
  python3 - "$@" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
p, sid, alias, word = sys.argv[1:5]
project = sminos.find_project(p)
sminos.log_append(project, "delta/" + sid, "joined", session=sid, alias=alias, name_source="user", machine="delta",
                  cwd="/d", worktree="", role="", seat="", by="")
sminos.log_append(project, "delta/" + sid, "state", session=sid, state=word)
PY
}
PG=0c0c0c0a-1111-4222-8333-44445555666a
PR=0c0c0c0e-1111-4222-8333-44445555666e
reg "$PG" pg
reg "$PR" pr
mkdir -p "$SMINOS_HOME/daemon"
printf '{"projects": [{"id": "%s", "name": "pr", "kind": "hub", "retired": true}], "machines": [], "at": ""}\n' "$PR" \
  > "$SMINOS_HOME/daemon/org.json"
GI=0d0d0d01-0000-4000-8000-000000000001
GS=0d0d0d02-0000-4000-8000-000000000002
GW=0d0d0d03-0000-4000-8000-000000000003
GR=0d0d0d04-0000-4000-8000-000000000004
member pg "$GI" idler idle
member pg "$GS" stopper stopped
member pg "$GW" waiter waiting
member pr "$GR" retiree idle
run_in "$T/x" "$SMINOS" say --machine delta "for delta"
assert_rc 0 "$RC" "a broadcast to another machine's sessions"
assert_equals "$(to_of "$(events_with "$PG" "for delta")")" "$(sorted "$GI" "$GW")" \
  "reaches its live ones (idle, waiting), never the stopped one"
assert_equals "$(events_with "$PR" "for delta")" "" "nor one in a project the org's directory retires"
run_in "$T/x" "$SMINOS" say --project pr "into the retired"
assert_rc 4 "$RC" "a selector naming a retired project is refused"
run_in "$T/x" "$SMINOS" say --project nosuch "nowhere"
assert_rc 4 "$RC" "as is one naming no project known here"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-broadcast: all $PASSES assertions passed"
else
  echo "test-broadcast: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  for f in "$T"/ra/s/daemon.log "$T"/rb/s/daemon.log "$T"/ra/s/run.out "$T"/rb/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
