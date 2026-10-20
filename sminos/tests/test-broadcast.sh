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
# no live session. Two machines simulated on one Mac — two SMINOS_HOMEs
# enrolled as alpha and beta against hub_standin.py — each with its daemon,
# delivering to scripted inboxes; then a third home, gamma, whose logs alone
# pin the live-only rule against published states.
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
# transcript launched in `dir`. Frames land in $T/<name>.received.
live_session() { # name session dir [status]
  : > "$T/$1.received"
  python3 "$SCRIPT_DIR/inbox_standin.py" "$T/$1.sock" "$T/$1.received" & PIDS+=("$!")
  local pid=$!
  until_true test -S "$T/$1.sock"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"%s","cwd":"%s","messagingSocketPath":"%s","entrypoint":"cli"}\n' \
    "$pid" "$2" "$1" "${4:-idle}" "$3" "$T/$1.sock" > "$HOME/.claude/sessions/$1.json"
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

python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-0 secret-0 1000 & PIDS+=("$!")
until_true test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"

cat > "$T/ctl.py" <<'PY'
import base64, http.client, json, sys
port = int(open(sys.argv[1]).read())

def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")

cmd, args = sys.argv[2], sys.argv[3:]
if cmd == "token":
    print(call("POST", "/control/enrollment", {})[1]["token"])
elif cmd == "code":  # hub token machine key
    body = json.dumps(dict(zip(("hub", "org", "token", "machine", "key"), [args[0], "org-1", *args[1:4]])),
                      separators=(",", ":")).encode()
    print("smns-enroll-v1." + base64.urlsafe_b64encode(body).rstrip(b"=").decode())
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }
mp_of() { python3 -c 'import sys, uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:org-1:" + sys.argv[1].lower()))' "$1"; }
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
# word, for another machine's, the one that machine published).
live_in() { # project session
  (cd "$T/x" && "$SMINOS" list "$1" --json --all 2>/dev/null) | python3 -c 'import json, sys
print(any(m["session"] == sys.argv[1] and m["state"] in ("busy", "idle", "waiting") for m in json.load(sys.stdin)))' "$2" \
    | grep -q True
}
mkdir -p "$T/x"
sorted() { printf '%s\n' "$@" | sort | tr '\n' ' ' | sed 's/ $//'; }

# ---- alpha: projA with the sender sa and a2; two strays, one waiting
as a alpha
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" alpha "$KEY")" >/dev/null
AMP="$(mp_of alpha)"
RA="$T/a/projA"
gitq init -q "$RA"
write_smns "$RA" projA
AID="$(smns_id "$RA")"
SA=5a0000a1-0000-4000-8000-0000000000a1
A2=5a0000a2-0000-4000-8000-0000000000a2
live_session sa "$SA" "$RA"
live_session a2 "$A2" "$RA"
ABARE="$T/a/bare"
mkdir -p "$ABARE"
WA=5a0000a4-0000-4000-8000-0000000000a4
WW=5a0000a5-0000-4000-8000-0000000000a5
live_session wa "$WA" "$ABARE"
live_session ww "$WW" "$ABARE" waiting
run_in "$RA" "$SMINOS" list
run_in "$ABARE" "$SMINOS" list
start_daemon

# ---- beta: projB with rb, a checkout of projA with ab, a stray mb
as b beta
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" beta "$KEY")" >/dev/null
BMP="$(mp_of beta)"
RB="$T/b/projB"
gitq init -q "$RB"
write_smns "$RB" projB
BID="$(smns_id "$RB")"
RBS=5b0000b1-0000-4000-8000-0000000000b1
live_session rb "$RBS" "$RB"
RA2="$T/b/projA"
gitq init -q "$RA2"
cp "$RA/.smns" "$RA2/.smns"
AB=5b0000b2-0000-4000-8000-0000000000b2
live_session ab "$AB" "$RA2"
MB=5b0000b8-0000-4000-8000-0000000000b8
live_session mb "$MB" "$T/b/home"
run_in "$RB" "$SMINOS" list
run_in "$RA2" "$SMINOS" list
run_in "$T/b/home" "$SMINOS" list
start_daemon

as a alpha
until_true live_in "$BID" "$RBS" || true
until_true live_in "$AID" "$AB" || true
until_true live_in "$BMP" "$MB" || true
live_in "$BID" "$RBS" && live_in "$AID" "$AB" && live_in "$BMP" "$MB" \
  && pass "alpha reads beta's sessions live: rb in projB, ab in projA, mb in beta" \
  || fail "alpha reads beta's sessions live: rb in projB, ab in projA, mb in beta"

# ---- a machine: every session on it, whatever its project
echo "--machine:"
in_session "$SA" "$RA" "$SMINOS" say --machine beta "beta reboots at three"
assert_rc 0 "$RC" "say --machine beta is accepted"
assert_contains "$OUT" "@all on beta: 3 sessions" "it says how many sessions it sends to, and under which label"
assert_contains "$OUT" "rb#${RBS:0:8}: recorded (on beta)" "rb is recorded for beta's daemon"
assert_contains "$OUT" "ab#${AB:0:8}: recorded (on beta)" "as is ab"
assert_contains "$OUT" "mb#${MB:0:8}: recorded (on beta)" "and mb"
DB="$(events_with "$BID" "beta reboots at three")"
DA="$(events_with "$AID" "beta reboots at three")"
DM="$(events_with "$BMP" "beta reboots at three")"
assert_equals "$(to_of "$DB")" "$RBS" "projB's event is addressed to its recipient, rb"
assert_equals "$(to_of "$DM")" "$MB" "beta's machine project's to mb"
assert_equals "$(to_of "$DA")" "$AB" "projA's to ab: the sender's own project has a recipient there"
assert_equals "$(field_of "$DB" scope)" '{"machines": ["beta"]}' "each event names the scope"
assert_equals "$(field_of "$DB" wake)" "true" "and wakes, as @all does"
assert_equals "$(field_of "$DB" kind)" '"say"' "a session's broadcast is a say"
assert_equals "$(field_of "$DB" from_project)" "\"$AID\"" "an event outside the sender's project names it, for the reply"
assert_equals "$(field_of "$DA" from_project)" "null" "the event in the sender's own project does not"
assert_equals "$(echo "$DA" | grep -c . | tr -d ' ')" "1" "projA holds the one event, no copy beside it"
assert_equals "$(field_of "$DA" copy)" "null" "since a recipient is there"
LISTED="$(cd "$T/x" && "$SMINOS" list --machine beta --json | python3 -c 'import json, sys
print(" ".join(sorted(m["session"] for m in json.load(sys.stdin) if m["state"] in ("busy", "idle", "waiting"))))')"
assert_equals "$(sorted "$RBS" "$AB" "$MB")" "$LISTED" "list --machine beta shows those three as its live rows"
as b beta
until_true got rb "beta reboots at three" || true
until_true got ab "beta reboots at three" || true
until_true got mb "beta reboots at three" || true
got rb "beta reboots at three" && got ab "beta reboots at three" && got mb "beta reboots at three" \
  && pass "beta's daemon delivers it to all three" || fail "beta's daemon delivers it to all three"
FRAME="$(frames rb)"
assert_contains "$FRAME" "from sa → @all on beta" "the frame names the scope"
assert_contains "$FRAME" "say \"@$AID/${SA:0:8} <your reply>\"" "its reply line answers the sender alone"
assert_contains "$(frames ab)" "say \"@$AID/${SA:0:8} <your reply>\"" "in the sender's own project too"
assert_equals "$(frames a2)$(frames wa)$(frames ww)$(frames sa)" "" "no session on alpha, the sender's included, is reached"
run_in "$RB" "$SMINOS" chat projB -n 5
assert_contains "$OUT" "sa → @all on beta  beta reboots at three" "chat in a recipient's project names the scope"

# ---- the reply goes to the sender alone
echo "the reply:"
REPLY="$(frames rb | sed -n "s/.*\[To reply, run in Bash: \(.*\) <your reply>\"\]/\1/p" | head -1)"
in_session "$RBS" "$RB" bash -c "$REPLY noted, draining\""
assert_rc 0 "$RC" "rb's reply line runs as written"
RE="$(events_with "$AID" "noted, draining" | grep -v '"copy"' || true)"
assert_equals "$(to_of "$RE")" "$SA" "the reply is addressed to the sender alone"
assert_equals "$(field_of "$RE" scope)$(field_of "$RE" wake)" "nullnull" "no scope, no wake: it is no broadcast"

# ---- projects × machines intersect; a copy where no recipient is the sender's
echo "--project with --machine:"
as a alpha
in_session "$SA" "$RA" "$SMINOS" say --project projB --machine beta "projB on beta only"
assert_rc 0 "$RC" "say --project projB --machine beta is accepted"
assert_contains "$OUT" "@all in projB on beta: 1 session" "one session"
DB="$(events_with "$BID" "projB on beta only")"
assert_equals "$(to_of "$DB")" "$RBS" "rb alone"
assert_equals "$(field_of "$DB" scope)" "{\"projects\": [\"$BID\"], \"machines\": [\"beta\"]}" \
  "the scope names its projects by id"
assert_equals "$(events_with "$BMP" "projB on beta only")" "" "beta's machine project is outside it"
COPY="$(events_with "$AID" "projB on beta only")"
assert_equals "$(field_of "$COPY" copy)" "\"$BID:alpha/$SA:$(field_of "$DB" seq)\"" \
  "the sender's project, with no recipient, holds a copy naming the delivering event"
assert_equals "$(field_of "$COPY" to)" "[{\"session\": \"$RBS\", \"alias\": \"rb\", \"project\": \"$BID\"}]" \
  "its recipients with their project"
assert_equals "$(field_of "$COPY" scope)" "$(field_of "$DB" scope)" "and the scope"
run_in "$RA" "$SMINOS" chat projA -n 1
assert_contains "$OUT" "sa → @all in projB on beta → projB  projB on beta only" "chat in projA shows the scope and the copy's destination"

echo "a copy of several:"
in_session "$SA" "$RA" "$SMINOS" say --project projB,beta "two projects"
assert_rc 0 "$RC" "say --project projB,beta is accepted"
assert_contains "$OUT" "@all in projB,beta: 2 sessions" "two sessions"
DB="$(events_with "$BID" "two projects")"
DM="$(events_with "$BMP" "two projects")"
COPY="$(events_with "$AID" "two projects")"
assert_equals "$(field_of "$COPY" copy)" \
  "[\"$BID:alpha/$SA:$(field_of "$DB" seq)\", \"$BMP:alpha/$SA:$(field_of "$DM" seq)\"]" \
  "a copy of events in several projects names each delivering event"
assert_equals "$(to_of "$COPY")" "$(sorted "$RBS" "$MB")" "and every recipient"
assert_equals "$(python3 - "$AID" "$RBS" "$MB" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
p = sminos.find_project(sys.argv[1])
print([e["text"] for s in sys.argv[2:] for e in sminos._owed(sminos.log_read(p), s, {}) if e["text"] == "two projects"])
PY
)" "[]" "the copy is owed to no one"
run_in "$RA" "$SMINOS" chat projA -n 1
assert_contains "$OUT" "sa → @all in projB,beta → projB, beta  two projects" "chat names both destinations"

# ---- the org, and this machine
echo "--org and --here:"
in_session "$SA" "$RA" "$SMINOS" say --org "reviews go to their own pins again"
assert_rc 0 "$RC" "say --org is accepted"
assert_contains "$OUT" "@org: 6 sessions" "every live session of the org but the sender"
assert_equals "$(to_of "$(events_with "$AID" "reviews go to their own pins")")" "$(sorted "$A2" "$AB")" \
  "projA's event: a2 here and ab on beta"
assert_equals "$(to_of "$(events_with "$AMP" "reviews go to their own pins")")" "$(sorted "$WA" "$WW")" \
  "alpha's machine project's: wa, and ww, which waits"
assert_equals "$(field_of "$(events_with "$AID" "reviews go to their own pins")" scope)" "{}" "the scope of the whole org is {}"
until_true got a2 "reviews go to their own pins" || true
got a2 "reviews go to their own pins" && pass "a session on the sender's machine is delivered at once" \
  || fail "a session on the sender's machine is delivered at once"
assert_contains "$(frames ww)" "from sa → @org" "the frame says @org"
in_session "$SA" "$RA" "$SMINOS" say --here "alpha only"
assert_rc 0 "$RC" "say --here is accepted"
assert_contains "$OUT" "@all on alpha: 3 sessions" "this machine's live sessions"
assert_equals "$(field_of "$(events_with "$AMP" "alpha only")" scope)" '{"here": "alpha"}' "--here names this machine"
assert_equals "$(events_with "$BID" "alpha only")$(events_with "$BMP" "alpha only")" "" "nothing for beta"
in_session "$SA" "$RA" "$SMINOS" say --state waiting "who waits"
assert_rc 0 "$RC" "say --state waiting is accepted"
assert_equals "$(to_of "$(events_with "$AMP" "who waits")")" "$WW" "it reaches the waiting session alone"
assert_contains "$OUT" "@org (waiting): 1 session" "its label names the state"

# ---- refusals
echo "refusals:"
in_session "$SA" "$RA" "$SMINOS" say --machine beta "@rb tagged and scoped"
assert_rc 2 "$RC" "a selector with an opening @tag is refused"
assert_contains "$OUT" "a selector picks the recipients" "saying why"
in_session "$SA" "$RA" "$SMINOS" say --org "@all both"
assert_rc 2 "$RC" "a selector with @all too"
in_session "$SA" "$RA" "$SMINOS" say --machine nosuch "anyone there"
assert_rc 4 "$RC" "a scope with no live session is refused"
assert_contains "$OUT" "no live session" "saying so"
in_session "$SA" "$RA" "$SMINOS" say --state stopped "the stopped"
assert_rc 2 "$RC" "a scope of non-live states is refused: a broadcast wakes only the live"
assert_equals "$(events_with "$AID" "tagged and scoped")$(events_with "$BID" "tagged and scoped")$(events_with "$AID" "anyone there")$(events_with "$AID" "the stopped")" \
  "" "a refused broadcast is recorded nowhere"
run_in "$RA" "$SMINOS" say --in projA --machine beta "in and scope"
assert_rc 2 "$RC" "an operator's --in with a selector is refused"

# ---- the operator, from a terminal
echo "the operator:"
run_in "$RA" "$SMINOS" say --machine beta --project projB "from the owner"
assert_rc 0 "$RC" "the operator may send at any scope"
OE="$(events_with "$BID" "from the owner")"
assert_equals "$(field_of "$OE" kind)$(field_of "$OE" writer)" '"human""alpha/human"' "as a human event under its writer"
assert_equals "$(events_with "$AID" "from the owner")" "" "with no copy: the operator has no project of its own"
as b beta
until_true got rb "from the owner" || true
got rb "from the owner" && pass "beta delivers it" || fail "beta delivers it"

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
  for f in "$T"/a/s/daemon.log "$T"/b/s/daemon.log "$T"/a/s/run.out "$T"/b/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
