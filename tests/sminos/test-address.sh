#!/usr/bin/env bash
#
# Addressing across the org and the copy in the sender's log (M5 of the
# sminos org directory, docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md
# §5, §6): a bare `@alias` reaches only the sender's project, and its refusal
# lists the org's candidates as `@<project>/<alias>#<short>`; `@short` and
# `@alias#short` resolve across every project known here, a short two
# sessions share refused naming both; `@<project>/<alias>` reaches a stray as
# `@<machine>/<alias>`, reads an ordinary project before a machine project of
# the same name, and names a session that moved away `moved to <project>`; a
# message into another project is recorded where it delivers and copied into
# the sender's own log (`copy`, `to[].project`), and the copy delivers
# nothing; a reply through the frame's reply line crosses back the same way;
# `send` on an enrolled machine never takes the raw-name route. Two machines
# simulated on one Mac — two SMINOS_HOMEs enrolled as alpha and beta against
# hub_standin.py — each with its daemon, delivering to scripted inboxes.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$REPO_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/sma.XXXXXX)"
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
as() { # a|b host — one machine: its HOME, its SMINOS_HOME, its host name
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

# A live session's inbox: appends each frame it receives and answers ok.
cat > "$T/inbox.py" <<'PY'
import socket, sys
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(sys.argv[1])
srv.listen(8)
while True:
    c, _ = srv.accept()
    buf = b""
    while True:
        chunk = c.recv(65536)
        if not chunk:
            break
        buf += chunk
    with open(sys.argv[2], "ab") as f:
        f.write(buf)
    try:
        c.sendall(b"ok\n")
    except OSError:
        pass
    c.close()
PY
# A running session with an inbox: its engine record (the inbox's pid is the
# session's process), its transcript launched in `dir`. Frames land in $T/<name>.received.
live_session() { # name session dir [entrypoint] [inbox, else the name]
  local box=${5:-$1}
  : > "$T/$box.received"
  python3 "$T/inbox.py" "$T/$box.sock" "$T/$box.received" & PIDS+=("$!")
  local pid=$!
  until_true test -S "$T/$box.sock"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s","entrypoint":"%s"}\n' \
    "$pid" "$2" "$1" "$3" "$T/$box.sock" "${4:-cli}" > "$HOME/.claude/sessions/$box.json"
  local tx="$HOME/.claude/projects/p-$2/$2.jsonl"
  mkdir -p "$(dirname "$tx")"
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
    "${2:0:8}" "$2" "$3" > "$tx"
}
received() { cat "$T/$1.received" 2>/dev/null || true; }
got() { received "$1" | grep -Fq -- "$2"; }   # name text — whether the inbox holds a frame carrying the text

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
has_event() { [ -n "$(events_with "$1" "$2")" ]; }
field_of() { # json-line field — one field of an event, as JSON
  python3 -c 'import json, sys; print(json.dumps(json.loads(sys.argv[1]).get(sys.argv[2])))' "$1" "$2"
}
in_session() { # session dir command... — the command as that session runs it, in dir
  local sid=$1 d=$2; shift 2
  set +e; OUT="$(cd "$d" && env CLAUDE_CODE_SESSION_ID="$sid" "$@" 2>&1)"; RC=$?; set -e
}
member_of() { # project session → whether this machine's log of the project holds the session joined
  (cd "$T/x" && "$SMINOS" list "$1" --json --all 2>/dev/null) | grep -q "\"session\": \"$2\""
}
mkdir -p "$T/x"

# ---- alpha: projA with the sender, a stray in a bare directory
as a alpha
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" alpha "$KEY")" >/dev/null
AMP="$(mp_of alpha)"
RA="$T/a/projA"
gitq init -q "$RA"
write_smns "$RA" projA
AID="$(smns_id "$RA")"
SA=5a00000a-0000-4000-8000-0000000000a1
live_session sa "$SA" "$RA"
ABARE="$T/a/bare"
mkdir -p "$ABARE"
WD=5a00000d-0000-4000-8000-0000000000a4
live_session wand "$WD" "$ABARE"
run_in "$RA" "$SMINOS" list
run_in "$ABARE" "$SMINOS" list
start_daemon

# ---- beta: projB with rb, two strays in its home directory
as b beta
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" beta "$KEY")" >/dev/null
BMP="$(mp_of beta)"
RB="$T/b/projB"
gitq init -q "$RB"
write_smns "$RB" projB
BID="$(smns_id "$RB")"
RBS=5b00000b-0000-4000-8000-0000000000b1
live_session rb "$RBS" "$RB"
BHOME="$T/b/home"
M7=5b00007c-0000-4000-8000-0000000000b7
live_session mini-7c "$M7" "$BHOME"
M8=5b00008c-0000-4000-8000-0000000000b8
live_session m8 "$M8" "$BHOME"
run_in "$RB" "$SMINOS" list
run_in "$BHOME" "$SMINOS" list
start_daemon

as a alpha
until_true member_of "$BID" "$RBS" || true
member_of "$BID" "$RBS" && pass "alpha follows projB and reads rb there" || fail "alpha follows projB and reads rb there"
until_true member_of "$BMP" "$M7" || true
until_true member_of "$BMP" "$M8" || true
member_of "$BMP" "$M7" && pass "and beta's strays in beta's machine project" || fail "and beta's strays in beta's machine project"

# ---- a bare name stays in the project
echo "a bare name:"
in_session "$SA" "$RA" "$SMINOS" say "@rb are you there"
assert_rc 4 "$RC" "@alias of another project's member is refused"
assert_contains "$OUT" "@projB/rb#${RBS:0:8}" "naming the member as @<project>/<alias>#<short>"
assert_contains "$OUT" "a bare name reaches only your project; @short reaches anyone" "and how to reach anyone"
in_session "$SA" "$RA" "$SMINOS" say "@mini-7c are you there"
assert_rc 4 "$RC" "@alias of a stray on another machine is refused"
assert_contains "$OUT" "@beta/mini-7c#${M7:0:8}" "naming it by its machine: @<machine>/<alias>#<short>"
assert_equals "$(events_with "$BID" "are you there")$(events_with "$AID" "are you there")" "" "a refused message is recorded nowhere"

# ---- @<project>/<alias>: delivered in its project, copied into the sender's
echo "@<project>/<alias> and the copy:"
in_session "$SA" "$RA" "$SMINOS" say "@projB/rb hello B"
assert_rc 0 "$RC" "@projB/rb is accepted"
assert_contains "$OUT" "rb: recorded (on beta)" "for beta's daemon to deliver"
DEST="$(events_with "$BID" "hello B")"
COPY="$(events_with "$AID" "hello B")"
assert_equals "$(field_of "$DEST" from_project)" "\"$AID\"" "the delivering event is in projB's log, from projA"
assert_equals "$(field_of "$COPY" copy)" "\"$BID:alpha/$SA:$(field_of "$DEST" seq)\"" \
  "the copy in projA's log names the delivering event: <project>:<writer>:<seq>"
assert_equals "$(field_of "$COPY" to)" "[{\"session\": \"$RBS\", \"alias\": \"rb\", \"project\": \"$BID\"}]" \
  "its recipients carry their project"
assert_equals "$(field_of "$COPY" ts)$(field_of "$COPY" from)$(field_of "$COPY" text)" \
  "$(field_of "$DEST" ts)$(field_of "$DEST" from)$(field_of "$DEST" text)" "with the same ts, from and text"
assert_equals "$(field_of "$COPY" from_project)" "null" "and no from_project: it is in the sender's own project"
assert_equals "$(field_of "$DEST" copy)" "null" "the delivering event is no copy"
assert_equals "$(python3 - "$AID" "$RBS" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
p = sminos.find_project(sys.argv[1])
print([e["text"] for e in sminos._owed(sminos.log_read(p), sys.argv[2], {})])
PY
)" "[]" "the copy, whose to names rb, is owed to no one in projA's log"
run_in "$RA" "$SMINOS" chat projA -n 5
assert_contains "$OUT" "sa → @rb → projB  @projB/rb hello B" "chat in projA shows the copy marked with its destination"
as b beta
until_true got rb "hello B" || true
got rb "hello B" && pass "rb receives it on beta" || fail "rb receives it on beta"
REPLY="$(python3 - "$T/rb.received" <<'PY'
import json, re, sys
for line in open(sys.argv[1]):
    if "hello B" in line:
        m = re.search(r"\[To reply, run in Bash: (.*) <your reply>\"\]", json.loads(line)["message"]["content"])
        print(m.group(1) if m else "")
PY
)"
assert_contains "$REPLY" "say \"@$AID/${SA:0:8}" "its reply line names the sender in projA"

# ---- @short, across machines and projects
echo "@short:"
as a alpha
in_session "$SA" "$RA" "$SMINOS" say "@${RBS:0:8} by short"
assert_rc 0 "$RC" "@short resolves to a member of another project"
assert_contains "$OUT" "in projB" "recorded in its project"
assert_contains "$(events_with "$AID" "by short")" "\"copy\": \"$BID:alpha/$SA:" "with its copy in the sender's"
as b beta
until_true got rb "by short" || true
got rb "by short" && pass "and delivered" || fail "and delivered"
assert_equals "$(received rb | grep -c "hello B")" 1 "the copy is never pushed: rb's inbox holds the message once"

# ---- the reply line, from beta back into projA
echo "the reply:"
in_session "$RBS" "$RB" bash -c "$REPLY back from rb\""
assert_rc 0 "$RC" "the reply line runs as written"
assert_contains "$OUT" "in projA" "into projA"
assert_contains "$(events_with "$BID" "back from rb")" "\"copy\": \"$AID:beta/$RBS:" "its copy in rb's own project"
as a alpha
until_true got sa "back from rb" || true
got sa "back from rb" && pass "sa receives the reply on alpha" || fail "sa receives the reply on alpha"

# ---- a stray, by its machine
echo "@<machine>/<alias>:"
in_session "$SA" "$RA" "$SMINOS" say "@beta/mini-7c did the image build"
assert_rc 0 "$RC" "@beta/mini-7c is accepted"
assert_contains "$OUT" "in beta" "into beta's machine project"
assert_contains "$(events_with "$BMP" "did the image build")" "\"from_project\": \"$AID\"" "recorded in its log"
assert_contains "$(events_with "$AID" "did the image build")" "\"copy\": \"$BMP:alpha/$SA:" "and copied into projA"
as b beta
until_true got mini-7c "did the image build" || true
got mini-7c "did the image build" && pass "the stray receives it on beta" || fail "the stray receives it on beta"

# ---- a session that moved away
echo "a session that moved:"
as a alpha
in_session "$WD" "$ABARE" "$SMINOS" join projA
assert_rc 0 "$RC" "wand joins projA"
as b beta
moved_here() { [ -n "$(events_with "$AMP" '"reason": "moved"')" ]; }
until_true moved_here || true
in_session "$RBS" "$RB" "$SMINOS" say "@alpha/wand still there"
assert_rc 4 "$RC" "a tag naming its former project is refused"
assert_contains "$OUT" "moved to projA" "saying where it went"
in_session "$RBS" "$RB" "$SMINOS" say "@${WD:0:8} found you"
assert_rc 0 "$RC" "@short reaches it"
assert_contains "$OUT" "in projA" "in the project it moved to"
as a alpha
until_true got wand "found you" || true
got wand "found you" && pass "and delivers on alpha" || fail "and delivers on alpha"

# ---- a short two sessions share; a bare 8-hex name that is an alias here
echo "shorts:"
X1=5d0000dd-0000-4000-8000-000000000001
X2=5d0000dd-0000-4000-8000-000000000002
live_session x1 "$X1" "$ABARE"
live_session x2 "$X2" "$RA"
run_in "$ABARE" "$SMINOS" list
in_session "$SA" "$RA" "$SMINOS" say "@5d0000dd which one"
assert_rc 4 "$RC" "a short two sessions share is refused"
assert_contains "$OUT" "@alpha/x1#5d0000dd" "naming one with its project"
assert_contains "$OUT" "@projA/x2#5d0000dd" "and the other"
H8=5a0000e8-0000-4000-8000-0000000000e8
live_session 5d0000dd "$H8" "$RA"
in_session "$SA" "$RA" "$SMINOS" say "@5d0000dd the alias"
assert_rc 0 "$RC" "a bare 8-hex name a member of the sender's project has as alias is that alias"
assert_contains "$(events_with "$AID" "the alias")" "\"session\": \"$H8\"" "the member, not the short"

# ---- a project and a machine of one name
echo "a project named after a machine:"
RN="$T/a/named-beta"
gitq init -q "$RN"
write_smns "$RN" beta
NID="$(smns_id "$RN")"
N7=5a0000f7-0000-4000-8000-0000000000f7
live_session mini-7c "$N7" "$RN" cli mini-7c-alpha
run_in "$RN" "$SMINOS" list
in_session "$SA" "$RA" "$SMINOS" say "@beta/mini-7c which beta"
assert_rc 0 "$RC" "@beta/mini-7c resolves"
assert_contains "$(events_with "$NID" "which beta")" "\"session\": \"$N7\"" "to the ordinary project's member first"
assert_equals "$(events_with "$BMP" "which beta")" "" "not the machine project's"
in_session "$SA" "$RA" "$SMINOS" say "@beta/m8 only on the machine"
assert_rc 0 "$RC" "@beta/m8, which the project named beta has not"
assert_contains "$(events_with "$BMP" "only on the machine")" "\"session\": \"$M8\"" "falls back to the machine project"

# ---- send never takes the raw-name route on an enrolled machine
echo "send:"
HL=5a0000c1-0000-4000-8000-0000000000c1
live_session hl "$HL" "$ABARE" sdk-cli
run_in "$RA" "$SMINOS" send hl "raw by name"
assert_rc 4 "$RC" "send to a harness name no member answers to is refused"
in_session "$SA" "$ABARE" "$SMINOS" send hl "raw from a session"
assert_rc 4 "$RC" "from a session too"
assert_equals "$(received hl)" "" "and nothing reaches the session by its raw name"
run_in "$RA" "$SMINOS" send rb "a bare send"
assert_rc 4 "$RC" "send to another project's member by its bare name is refused"
assert_contains "$OUT" "projB/rb#${RBS:0:8}" "naming it as <project>/<alias>#<short>"
in_session "$SA" "$RA" "$SMINOS" send "projB/rb" "sent across"
assert_rc 0 "$RC" "send <project>/<alias> records for the member"
assert_contains "$(events_with "$AID" "sent across")" "\"copy\": \"$BID:alpha/$SA:" "with its copy in the sender's project"
as b beta
until_true got rb "sent across" || true
got rb "sent across" && pass "and beta delivers it" || fail "and beta delivers it"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-address: all $PASSES assertions passed"
else
  echo "test-address: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  for f in "$T"/a/s/daemon.log "$T"/b/s/daemon.log "$T"/a/s/run.out "$T"/b/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
