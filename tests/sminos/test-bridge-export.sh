#!/usr/bin/env bash
#
# The bridge's live export to the host (DC2 M4, G4; smns §4): the mod posts
# the main loop's rows that may hold a mark — a text row with a `<message>`
# candidate, an async ask with its result — as an `export` event, and the
# child appends their host events to the project's log through the record
# path's own writer and (kind, src) keys, so the Stop hook's export of the
# same rows finds them there and appends nothing twice. A stand-in for the
# mod (fakemod) spawns the child; the test posts the mod's events itself.
# Hermetic: HOME and SMINOS_HOME are temporary (SMINOS_HOME short, for the
# socket's path). run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SMINOS="$REPO_ROOT/skills/sminos/scripts/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smx.XXXXXX)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "bridge --session 5b000001-0000-4000-8000-0000000000e" >/dev/null 2>&1 || break; sleep 0.05; done
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
# Polls every 50 ms until the command holds. The leading count is kept for the
# call sites, but the ceiling is one liveness bound, 30 s, not a claim about the
# machine's speed (ci-kit §6): a loaded host is slow, not wrong.
until_true() { # tries command...
  local end=$((SECONDS + 30)); shift
  until "$@"; do
    [ "$SECONDS" -ge "$end" ] && return 1
    sleep 0.05
  done
}

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME CLAUDE_CONFIG_DIR
export HOME="$T/home"
export SMINOS_HOME="$T/s"
export DAEMON_HOST=testhost
mkdir -p "$HOME/.claude/sessions" "$HOME/.claude/projects/x"
mkdir -m 700 "$SMINOS_HOME"
REPO="$T/repo"
mkdir -p "$REPO"
git -c init.defaultBranch=main init -q "$REPO"
(cd "$REPO" && "$SMINOS" project init --name exdemo >/dev/null)
PID_LOG="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$REPO/.smns")"
LOG="$SMINOS_HOME/projects/$PID_LOG/log"

cat > "$T/ctl.py" <<'PY'
import http.client, json, os, socket, subprocess, sys

class Conn(http.client.HTTPConnection):
    def __init__(self, path, timeout=10):
        super().__init__("bridge", timeout=timeout)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)

# The nonce each child named in its hello, kept by the stand-in that read it:
# a post of the mod's events carries it, as the mod's do (DX5's fence).
NONCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nonces")

def keep_nonce(hello):
    os.makedirs(NONCES, exist_ok=True)
    path = os.path.join(NONCES, os.path.basename(hello["socket"]))
    with open(path + ".tmp", "w") as f:
        f.write(hello["nonce"])
    os.replace(path + ".tmp", path)

def nonce_of(sock):
    try:
        with open(os.path.join(NONCES, os.path.basename(sock))) as f:
            return f.read()
    except OSError:
        return None

def request(path, method, url, body=None, nonce=None):
    headers = {"content-type": "application/json"}
    if method == "POST" and url == "/events":
        nonce = nonce if nonce is not None else nonce_of(path)
        if nonce:
            headers["X-Bridge-Nonce"] = nonce
    c = Conn(path)
    c.request(method, url, body=body, headers=headers)
    r = c.getresponse()
    return r.status, r.read().decode()

op = sys.argv[1]
if op == "post":            # sock events-json
    print(request(sys.argv[2], "POST", "/events", sys.argv[3])[0])
elif op == "status":        # sock
    status, text = request(sys.argv[2], "GET", "/status")
    print(status, "ready" if status == 200 and json.loads(text).get("ready") else "")
elif op == "subscribe":     # sock out-file: every line of the stream, until killed
    c = Conn(sys.argv[2], None)
    c.request("GET", "/events")
    r = c.getresponse()
    with open(sys.argv[3], "a") as f:
        for line in r:
            f.write(line.decode())
            f.flush()
elif op == "fakemod":       # sminos session: spawns the child, as the mod does, and lives until killed
    child = subprocess.Popen([sys.argv[2], "bridge", "--session", sys.argv[3]], stdout=subprocess.PIPE, text=True)
    for line in child.stdout:
        msg = json.loads(line)
        if msg.get("op") == "hello":   # as the mod's first post: its copy of the live state (DX5)
            keep_nonce(msg)
            request(msg["socket"], "POST", "/events", json.dumps([{"type": "resync", "turns": [], "streaming": [], "agents": []}]))
    child.wait()
PY
ctl() { python3 "$T/ctl.py" "$@"; }

# Transcript rows as the mod hands them over, and as the transcript keeps them.
cat > "$T/rows.py" <<'PY'
import json, sys
ASK = "mcp__doperpowers__AskUserQuestion"
ASYNC_RESULT = ("Your questions are waiting for the human; this call does not wait for them. Their answer will "
                "reach you in a later message that quotes each question. Go on with work that does not depend on it.")
Q = [{"question": "Which backend?", "header": "Backend", "multiSelect": False,
      "options": [{"label": "Postgres", "description": "running"}, {"label": "SQLite", "description": "a file"}]}]

def text(uuid, t):
    return {"type": "assistant", "uuid": uuid, "message": {"content": [{"type": "text", "text": t}]}}

def ask(uuid, call, is_async):
    return {"type": "assistant", "uuid": uuid, "message": {"content": [
        {"type": "tool_use", "id": call, "name": ASK, "input": {"questions": Q, "async": is_async}}]}}

def result(uuid, call, t=ASYNC_RESULT):
    return {"type": "user", "uuid": uuid, "message": {"content": [{"type": "tool_result", "tool_use_id": call, "content": t}]}}

MARKS = "Reading.\n<message>first to the host</message>\nAnd `<message>not this</message>` is literal.\n<message>second</message>"
ROWS = {
    "marks": [text("e1", MARKS)],
    "ask": [ask("e2", "toolu_ex_async", True), result("e3", "toolu_ex_async")],
    "blocking": [ask("e4", "toolu_ex_block", False), result("e5", "toolu_ex_block", "Your questions have been answered.")],
}
op = sys.argv[1]
def rows(name):
    return ROWS.get(name) or [text(name, "<message>%s, one row</message>" % name)]

if op == "export":          # name: the export event the mod posts for these rows
    print(json.dumps([{"type": "export", "records": rows(sys.argv[2]), "t": 1}]))
elif op == "transcript":    # path name...: the rows as the transcript keeps them, appended
    with open(sys.argv[2], "a") as f:
        for name in sys.argv[3:]:
            for r in ([{"type": "user", "uuid": "p-" + name, "isSidechain": False, "message": {"role": "user", "content": "go"}}]
                      if name == "prompt" else rows(name)):
                f.write(json.dumps({"isSidechain": False, **r}) + "\n")
PY
rows() { python3 "$T/rows.py" "$@"; }
events_of() { # session → "kind[:src]" words from its own writer file
  python3 -c 'import json, sys
try:
    lines = open(sys.argv[1]).read().splitlines()
except OSError:
    lines = []
print(" ".join(json.loads(l)["kind"] + (":" + json.loads(l)["src"] if json.loads(l).get("src") else "") for l in lines))' \
    "$LOG/testhost.$1.jsonl"
}
peer() { # session name kind entrypoint [cwd] — a running harness session, in the project unless cwd says
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"%s","entrypoint":"%s","status":"busy","cwd":"%s"}\n' \
    "$$" "$1" "$2" "$3" "$4" "${5:-$REPO}" > "$HOME/.claude/sessions/$2.json"
}
start_child() { # session
  python3 "$T/ctl.py" fakemod "$SMINOS" "$1" &
  PIDS+=("$!")
  until_true 200 test -S "$SMINOS_HOME/bridge/$1.sock" || true
  until_true 100 sh -c "python3 '$T/ctl.py' status '$SMINOS_HOME/bridge/$1.sock' 2>/dev/null | grep -q '200 ready'" || true
}
hook() { # event session transcript
  printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","hook_event_name":"%s","source":"startup"}' \
    "$2" "$REPO" "$3" "$1" | "$SMINOS" record
}
has() { [[ " $(events_of "$1") " == *" $2 "* ]]; }

echo "the bridge's live export to the host:"
SA=5b000001-0000-4000-8000-0000000000e1
SOCK="$SMINOS_HOME/bridge/$SA.sock"
TA="$HOME/.claude/projects/x/$SA.jsonl"
peer "$SA" exa interactive cli
start_child "$SA"
python3 "$T/ctl.py" subscribe "$SOCK" "$T/stream" &
PIDS+=("$!")
ctl post "$SOCK" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SA\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
ctl post "$SOCK" "$(rows export marks)" >/dev/null
until_true 100 has "$SA" "message:e1#1" || true
assert_equals "$(events_of "$SA")" "joined message:e1#0 message:e1#1" \
  "a text row's marks reach the log as the bridge sees the row: the session joined on sight, each span under src <row uuid>#<index>, a backticked tag left literal"
assert_contains "$(grep '"e1#0"' "$LOG/testhost.$SA.jsonl")" '"kind": "message", "from": "exa", "to": "host", "text": "first to the host", "src": "e1#0"' \
  "a message carries from (the member's alias), to host, text and src, as the Stop hook writes it"

ctl post "$SOCK" "$(rows export ask)" >/dev/null
until_true 100 has "$SA" "question:toolu_ex_async" || true
assert_contains "$(events_of "$SA")" "question:toolu_ex_async" "an async ask the tool accepted reaches the log as a question, src its call id"
assert_contains "$(grep toolu_ex_async "$LOG/testhost.$SA.jsonl")" '"text": ["Which backend?"], "choices": ["Postgres", "SQLite"]' \
  "with its questions and option labels"
ctl post "$SOCK" "$(rows export blocking)" >/dev/null
ctl post "$SOCK" "$(rows export marks)" >/dev/null
ctl post "$SOCK" '[{"type":"heartbeat","state":{},"t":2}]' >/dev/null
# Exports are appended in the order they came: once the last is in, the rest were done.
ctl post "$SOCK" "$(rows export es)" >/dev/null
until_true 100 has "$SA" "message:es#0" || true
until_true 100 grep -q heartbeat "$T/stream" || true
assert_not_contains "$(events_of "$SA")" "toolu_ex_block" "a blocking ask is no event"
assert_equals "$(events_of "$SA")" "joined message:e1#0 message:e1#1 question:toolu_ex_async message:es#0" \
  "a row exported twice (a redelivered batch) appends nothing more"
assert_not_contains "$(cat "$T/stream")" '"export"' "the export is the child's to act on: it is not handed to subscribers"

# The Stop hook's export over the same rows: what the bridge already put in
# the log is there; only what it never saw (row e9) is appended.
hook SessionStart "$SA" "$TA"
rows transcript "$TA" prompt marks ask e9
hook Stop "$SA" "$TA"
assert_equals "$(events_of "$SA")" "joined message:e1#0 message:e1#1 question:toolu_ex_async message:es#0 message:e9#0" \
  "the Stop hook's export finds the bridge's events already there and appends only what the bridge did not export"
hook Stop "$SA" "$TA"
assert_equals "$(events_of "$SA")" "joined message:e1#0 message:e1#1 question:toolu_ex_async message:es#0 message:e9#0" \
  "and a Stop replayed appends nothing"
"$SMINOS" chat exdemo --host > "$T/host" 2>&1 || true
assert_contains "$(cat "$T/host")" "exa: first to the host" "chat --host prints what the bridge exported"

echo "a recovery resync (the first post lost):"
# The mod's first post, [session start, resync], never reached the child; its
# recovery is a gap and a resync, which carries the session's start info.
SD=5b000001-0000-4000-8000-0000000000e4
peer "$SD" exrec interactive cli
start_child "$SD"
ctl post "$SMINOS_HOME/bridge/$SD.sock" "[{\"type\":\"gap\",\"dropped\":2,\"t\":1},{\"type\":\"resync\",\"turns\":[],\"streaming\":[],\"agents\":[],\"sessionInfo\":{\"session\":\"$SD\",\"cwd\":\"$REPO\",\"surface\":\"terminal\",\"isInteractive\":true},\"t\":1}]" >/dev/null
SNAP_SD="$(python3 - "$SMINOS_HOME/bridge/$SD.sock" <<'PY2'
import http.client, json, socket, sys
class C(http.client.HTTPConnection):
    def __init__(self, p):
        super().__init__("bridge", timeout=10); self.p = p
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.sock.connect(self.p)
c = C(sys.argv[1]); c.request("GET", "/events")
print(json.dumps(json.loads(c.getresponse().readline()).get("sessionInfo")))
PY2
)"
assert_contains "$SNAP_SD" "\"cwd\": \"$REPO\"" "the resync's sessionInfo is the child's: its snapshot carries the session's start info"
ctl post "$SMINOS_HOME/bridge/$SD.sock" "$(rows export marks)" >/dev/null
until_true 100 has "$SD" "message:e1#1" || true
assert_contains "$(events_of "$SD")" "message:e1#0 message:e1#1" "and an export lands, its cwd the resync's"

echo "who the export is for:"
SB=5b000001-0000-4000-8000-0000000000e2
peer "$SB" exsdk interactive sdk-cli
start_child "$SB"
ctl post "$SMINOS_HOME/bridge/$SB.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SB\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SB.sock" "$(rows export marks)" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SB.sock" '[{"type":"heartbeat","state":{},"t":2}]' >/dev/null
sleep 0.5
assert_equals "$(events_of "$SB")" "" "a session that is no member (a headless SDK run) exports nothing"

SC=5b000001-0000-4000-8000-0000000000e3
peer "$SC" exout interactive cli
start_child "$SC"
mkdir -p "$T/nowhere"
ctl post "$SMINOS_HOME/bridge/$SC.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SC\",\"cwd\":\"$T/nowhere\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SC.sock" "$(rows export marks)" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SC.sock" '[{"type":"export","records":"not a list"},{"type":"export"}]' >/dev/null
sleep 0.5
assert_equals "$(find "$SMINOS_HOME/projects" -name "*$SC*" | wc -l | tr -d ' ')" "0" "a session in no project exports nothing"
assert_equals "$(ctl status "$SMINOS_HOME/bridge/$SC.sock")" "200 ready" "and a malformed export leaves the child serving"

echo "an enrollment while the child runs:"
# The hub admits only the writers of the name this machine enrolled under: an
# export after the enrollment goes there, though the child began before it.
SE=5b000001-0000-4000-8000-0000000000e5
peer "$SE" exren interactive cli
start_child "$SE"
ctl post "$SMINOS_HOME/bridge/$SE.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SE\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SE.sock" "$(rows export before-enrolling)" >/dev/null
until_true 100 has "$SE" "message:before-enrolling#0" || true
assert_contains "$(events_of "$SE")" "message:before-enrolling#0" "before the enrollment, an export goes under the host's name"
mkdir -p "$SMINOS_HOME/daemon"
printf '{"machine": "enrolled", "former": {"testhost": ["%s"]}}\n' "$SE" > "$SMINOS_HOME/daemon/hub.json"
ctl post "$SMINOS_HOME/bridge/$SE.sock" "$(rows export after-enrolling)" >/dev/null
until_true 100 grep -q after-enrolling "$LOG/enrolled.$SE.jsonl" 2>/dev/null || true
assert_contains "$(cat "$LOG/enrolled.$SE.jsonl" 2>/dev/null)" '"src": "after-enrolling#0"' \
  "after it, under the enrolled name: the child reads the machine's identity afresh at each export"
assert_not_contains "$(events_of "$SE")" "after-enrolling" "and not under the name it began with"
rm -f "$SMINOS_HOME/daemon/hub.json"

echo "a checkout that becomes a hub project while the child runs:"
# A session in a checkout with no .smns exports to the repository's local
# project. The machine enrolls, the checkout gets a .smns naming the hub, and
# the session's next export goes to that project under the enrolled name: the
# child, which began before both, resolves the project afresh at each export.
SG=5b000001-0000-4000-8000-0000000000e6
R2="$T/walk"
mkdir -p "$R2/sub"
git -c init.defaultBranch=main init -q "$R2"
writer_events() { # project-id file-stem → "kind[:src]" words of that writer file
  python3 -c 'import json, sys
try:
    lines = open(sys.argv[1]).read().splitlines()
except OSError:
    lines = []
print(" ".join(json.loads(l)["kind"] + (":" + json.loads(l)["src"] if json.loads(l).get("src") else "") for l in lines))' \
    "$SMINOS_HOME/projects/$1/log/$2.jsonl"
}
peer "$SG" exwalk interactive cli "$R2/sub"
start_child "$SG"
ctl post "$SMINOS_HOME/bridge/$SG.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SG\",\"cwd\":\"$R2/sub\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SG.sock" "$(rows export before-smns)" >/dev/null
local_has() { [[ " $(writer_events local-walk "testhost.$SG") " == *" message:before-smns#0 "* ]]; }
until_true 100 local_has || true
assert_equals "$(writer_events local-walk "testhost.$SG")" "joined message:before-smns#0" \
  "before the .smns, an export goes to the repository's local project"
mkdir -p "$SMINOS_HOME/daemon"
printf '{"hub": "https://hub.test", "org": "org-a", "machine": "enrolled", "former": {"testhost": ["%s"]}}\n' "$SG" \
  > "$SMINOS_HOME/daemon/hub.json"
(cd "$R2" && "$SMINOS" project init --hub --name walk >/dev/null)
HUBP="$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d["project"] if d.get("hub") else "")' "$R2/.smns")"
assert_contains "$HUBP" "-" "project init --hub wrote a .smns naming the hub"
ctl post "$SMINOS_HOME/bridge/$SG.sock" "$(rows export after-hub)" >/dev/null
hub_has() { [[ " $(writer_events "$HUBP" "enrolled.$SG") " == *" message:after-hub#0 "* ]]; }
until_true 100 hub_has || true
assert_equals "$(writer_events "$HUBP" "enrolled.$SG")" "joined message:after-hub#0" \
  "after it, the next export goes to the hub project, under the enrolled name, the session joined there on sight"
assert_not_contains "$(writer_events local-walk "testhost.$SG") $(writer_events local-walk "enrolled.$SG")" "after-hub" \
  "and nothing more to the local project"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("hub"))' "$SMINOS_HOME/projects/$HUBP/project.json")" \
  "{'url': 'https://hub.test', 'org': 'org-a'}" "the hub project is registered with its hub"
rm -f "$SMINOS_HOME/daemon/hub.json"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES bridge export assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge export assertions FAILED"
  exit 1
fi
