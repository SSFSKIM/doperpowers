#!/usr/bin/env bash
#
# The bridge's session endpoint (DC2 M1, DX5): `sminos bridge --session <id>`,
# the child the bridge mod spawns for a session's life, and `sminos watch`, the
# local client that prints its live stream. A stand-in for the mod (fakemod)
# spawns the child as the mod does, reads its command lines from stdout and
# answers each over the socket; the test posts the mod's events itself.
# Hermetic: HOME and SMINOS_HOME are temporary (SMINOS_HOME short, since a
# Unix socket's path holds about 100 bytes), and no real session runs.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SMINOS="$REPO_ROOT/skills/sminos/scripts/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smb.XXXXXX)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
  # Every child a fakemod started dies with it (its parent is gone); wait for that.
  for _ in $(seq 1 60); do pgrep -f "bridge --session 5b000001-0000-4000-8000-00000000005b" >/dev/null 2>&1 || break; sleep 0.05; done
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
run() { set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e; }
mode_of() { python3 -c 'import os, sys; print("%04o" % (os.stat(sys.argv[1]).st_mode & 0o777))' "$1"; }
until_true() { # tries command... — poll every 50 ms
  local tries="$1"; shift
  for _ in $(seq 1 "$tries"); do "$@" && return 0; sleep 0.05; done
  return 1
}

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME
export HOME="$T/home"
export SMINOS_HOME="$T/s"
export SMINOS_BRIDGE_RECONNECT=1
mkdir -p "$HOME/.claude/sessions"
mkdir -m 700 "$SMINOS_HOME"
SID=5b000001-0000-4000-8000-00000000005b
SOCK="$SMINOS_HOME/bridge/$SID.sock"

# The test's own hands on the endpoint: post the mod's events, send a command,
# read a route, leave a stale socket file behind; and the mod's stand-in.
cat > "$T/ctl.py" <<'PY'
import http.client, json, os, socket, subprocess, sys, threading, time

class Conn(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("bridge", timeout=10)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
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
elif op == "get":           # sock url
    status, text = request(sys.argv[2], "GET", sys.argv[3])
    print(status, text)
elif op == "cmd":           # sock body [wait]
    url = "/command" + ("?wait=%s" % sys.argv[4] if len(sys.argv) > 4 else "")
    status, text = request(sys.argv[2], "POST", url, sys.argv[3])
    print(status, text)
elif op == "stale":         # path: a socket file nobody listens on
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(sys.argv[2])
    s.close()
elif op == "fakemod":       # sminos session lines-file
    # Spawns the child as the mod does and answers its command lines: `ping`
    # with a pong, anything else as an unknown op. Lives until killed; the
    # child, whose parent it is, follows it.
    sminos, session, out = sys.argv[2], sys.argv[3], sys.argv[4]
    child = subprocess.Popen([sminos, "bridge", "--session", session], stdout=subprocess.PIPE, text=True)
    sock = None
    with open(out, "a") as f:
        for line in child.stdout:
            f.write(line)
            f.flush()
            msg = json.loads(line)
            if msg.get("op") == "hello":
                sock = msg["socket"]
                keep_nonce(msg)
                # As the mod's first post: its copy of the live state (DX5).
                request(sock, "POST", "/events", json.dumps([{"type": "resync", "turns": [], "streaming": [], "agents": []}]))
                continue
            if "id" not in msg:
                continue
            if msg["op"] == "ping":
                ev = {"type": "result", "id": msg["id"], "op": "ping", "ok": True, "result": {"pong": True}}
            else:
                ev = {"type": "result", "id": msg["id"], "op": msg["op"], "ok": False, "error": "unknown op: %s" % msg["op"]}
            request(sock, "POST", "/events", json.dumps([ev]))
    child.wait()
PY
ctl() { python3 "$T/ctl.py" "$@"; }
fakemod() { # session lines-file → starts the stand-in, which starts the child
  python3 "$T/ctl.py" fakemod "$SMINOS" "$1" "$2" &
  FAKEMOD=$!
  PIDS+=("$FAKEMOD")
}
answers() { ctl get "$1" /status 2>/dev/null | grep -q '"ready": true'; }
child_pid() { ctl get "$1" /status | python3 -c 'import json, sys; print(json.loads(sys.stdin.read().split(" ", 1)[1])["pid"])'; }
nth_line() { sed -n "$2p" "$1"; }
field_of() { # json-text dotted.path
  python3 -c 'import json, sys
v = json.loads(sys.argv[1])
for k in sys.argv[2].split("."):
    v = v[int(k)] if isinstance(v, list) else v.get(k)
print(v if isinstance(v, str) else json.dumps(v))' "$1" "$2"
}
watch_json() { # session out-file → a background `watch --json`
  "$SMINOS" watch "$1" --json > "$2" 2>&1 &
  WATCHER=$!
  PIDS+=("$WATCHER")
}
lines_in() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }
has_lines() { [ "$(lines_in "$1")" -ge "$2" ]; }

echo "the bridge endpoint:"

run "$SMINOS" bridge
assert_rc 2 "$RC" "bridge without --session is a usage error"
run "$SMINOS" bridge --session not-a-session
assert_rc 2 "$RC" "bridge with a session that is no session id is a usage error"
assert_contains "$OUT" "not a session id" "saying so"

# The child serves the session's endpoint once its first line, hello, is out.
fakemod "$SID" "$T/lines-a"
until_true 100 answers "$SOCK" || true
assert_equals "$(answers "$SOCK" && echo yes || echo no)" "yes" "the child answers on \$SMINOS_HOME/bridge/<session>.sock"
assert_equals "$(mode_of "$SMINOS_HOME/bridge")" "0700" "the bridge directory is owner-only"
assert_equals "$(mode_of "$SOCK")" "0600" "and so is the socket"
HELLO="$(nth_line "$T/lines-a" 1)"
assert_equals "$(field_of "$HELLO" op)" "hello" "the child's first line is hello"
assert_equals "$(field_of "$HELLO" session)" "$SID" "naming the session"
assert_equals "$(field_of "$HELLO" socket)" "$SOCK" "and the socket it serves"
assert_equals "$(field_of "$HELLO" protocol)" "1" "and the protocol version"
assert_contains "$(field_of "$HELLO" presence)" "$HOME/.claude/sessions/" "and the session's engine record (<config>/sessions/<the session's pid>.json), which the mod reads for idle after a reload"
run ctl get "$SOCK" /status
assert_contains "$OUT" "200 " "status answers 200"
assert_equals "$(field_of "${OUT#200 }" session)" "$SID" "naming the session"
assert_equals "$(field_of "${OUT#200 }" protocol)" "1" "and the protocol"
assert_equals "$(ls -A "$SMINOS_HOME")" "bridge" "the child touches nothing else under SMINOS_HOME (no migration)"

# Commands: a line on the child's stdout, the mod's result relayed back.
run ctl cmd "$SOCK" '{"op":"ping"}' 3000
assert_contains "$OUT" "200 " "a command waited for answers 200"
assert_equals "$(field_of "${OUT#200 }" ok)" "true" "with the mod's result"
assert_equals "$(field_of "${OUT#200 }" result.pong)" "true" "carrying what the mod answered"
CID="$(field_of "${OUT#200 }" id)"
assert_contains "$(cat "$T/lines-a")" "\"id\": \"$CID\", \"op\": \"ping\"" "the command reached the mod as one stdout line, id first"
run ctl cmd "$SOCK" '{"op":"levitate","height":3}' 3000
assert_equals "$(field_of "${OUT#200 }" ok)" "false" "an op the mod does not know comes back refused"
assert_contains "$(cat "$T/lines-a")" '"height": 3' "the command's arguments ride the line"
run ctl cmd "$SOCK" '{"op":"ping"}' 0
assert_contains "$OUT" "202 " "without a wait, a command is accepted at once (202)"
assert_contains "$OUT" '"id"' "with its id"
run ctl cmd "$SOCK" '{"nop":1}'
assert_contains "$OUT" "400 " "a command without an op is refused (400)"
run ctl cmd "$SOCK" '{"op":"hello"}'
assert_contains "$OUT" "400 " "and so is one that would pass for the child's own hello"
run ctl get "$SOCK" /nowhere
assert_contains "$OUT" "404 " "an unknown route is 404"

# The stream: a snapshot, then every event the mod posts, numbered from 1.
watch_json "$SID" "$T/w1"
until_true 100 has_lines "$T/w1" 1 || true
SNAP="$(nth_line "$T/w1" 1)"
assert_equals "$(field_of "$SNAP" type)" "snapshot" "a subscription opens with a snapshot"
assert_equals "$(field_of "$SNAP" session)" "$SID" "of this session"
TURN=11111111-aaaa-4aaa-8aaa-111111111111
ctl post "$SOCK" '[{"type":"turn","phase":"start","turnId":"'$TURN'","agentId":null,"text":"build it"},
 {"type":"step","phase":"start","turnId":"'$TURN'","agentId":null,"step":0,"model":"m"},
 {"type":"chunk","turnId":"'$TURN'","agentId":null,"step":0,"chunkIndex":0,"chunk":{"kind":"text","index":0,"text":"Hel"}},
 {"type":"chunk","turnId":"'$TURN'","agentId":null,"step":0,"chunkIndex":1,"chunk":{"kind":"text","index":0,"text":"lo"}}]' >/dev/null
ctl post "$SOCK" '[{"type":"agent","phase":"spawn","agentId":"a7","subagentType":"general-purpose","description":"scout","background":true},
 {"type":"step","phase":"start","turnId":"t-sub","agentId":"a7","step":0,"model":"m"},
 {"type":"chunk","turnId":"t-sub","agentId":"a7","step":0,"chunkIndex":0,"chunk":{"kind":"text","index":0,"text":"sub says"}}]' >/dev/null
until_true 100 has_lines "$T/w1" 8 || true
assert_equals "$(field_of "$(nth_line "$T/w1" 2)" n)" "1" "live messages are numbered from 1"
assert_equals "$(field_of "$(nth_line "$T/w1" 2)" type)" "turn" "in the order the mod posted them"
CH="$(nth_line "$T/w1" 5)"
assert_equals "$(field_of "$CH" n)" "4" "each numbered one past the last"
assert_equals "$(field_of "$CH" chunk.text)" "lo" "a chunk carries the engine's chunk verbatim"
assert_equals "$(field_of "$CH" chunkIndex)" "1" "its index in its message"
assert_equals "$(field_of "$CH" turnId)" "$TURN" "and its turn"
SUBCH="$(nth_line "$T/w1" 8)"
assert_equals "$(field_of "$SUBCH" agentId)" "a7" "a subagent's chunk carries its agentId"

# A subscriber that arrives mid-message gets the partial text and its watermark.
watch_json "$SID" "$T/w2"
until_true 100 has_lines "$T/w2" 1 || true
SNAP2="$(nth_line "$T/w2" 1)"
MAIN="$(python3 -c 'import json, sys
s = json.loads(sys.argv[1])
print(json.dumps([m for m in s["streaming"] if m["agentId"] is None][0]))' "$SNAP2")"
assert_equals "$(field_of "$MAIN" blocks.0.text)" "Hello" "the snapshot carries a streaming block's partial text"
assert_equals "$(field_of "$MAIN" blocks.0.kind)" "text" "its kind"
assert_equals "$(field_of "$MAIN" blocks.0.index)" "0" "and its index, the one its chunks carry"
assert_equals "$(field_of "$MAIN" blocks.0.upTo)" "1" "and upTo, the last chunk that text includes"
assert_equals "$(field_of "$MAIN" upTo)" "1" "the message's upTo is the last chunk the snapshot accounts for"
assert_equals "$(field_of "$MAIN" step)" "0" "identified by turn, agent and step"
assert_equals "$(field_of "$SNAP2" turns.0.turnId)" "$TURN" "the snapshot lists the open turns"
assert_contains "$(field_of "$SNAP2" agents)" '"a7"' "and the subagents"
assert_equals "$(field_of "$SNAP2" pending)" "[]" "and the pending requests (none yet)"
ctl post "$SOCK" '[{"type":"chunk","turnId":"'$TURN'","agentId":null,"step":0,"chunkIndex":2,"chunk":{"kind":"text","index":0,"text":"!"}},
 {"type":"step","phase":"end","turnId":"'$TURN'","agentId":null,"step":0,"stopReason":"end_turn"},
 {"type":"turn","phase":"complete","turnId":"'$TURN'","agentId":null,"reason":"answer"}]' >/dev/null
until_true 100 has_lines "$T/w2" 4 || true
assert_equals "$(field_of "$(nth_line "$T/w2" 2)" chunkIndex)" "2" "after it, the late subscriber reads on from the next chunk"
watch_json "$SID" "$T/w3"
until_true 100 has_lines "$T/w3" 1 || true
assert_equals "$(field_of "$(nth_line "$T/w3" 1)" turns)" "[]" "a completed turn leaves the snapshot"
assert_not_contains "$(field_of "$(nth_line "$T/w3" 1)" streaming)" "$TURN" "and so do its messages"

# A snapshot never claims an upTo its text does not cover. A chunk lost on
# the way (B) takes its message out of the snapshot; the mod's resync puts it
# back whole, and the chunks after it follow on.
streaming_of() { # snapshot-line turnId → that turn's streaming message, or "none"
  python3 -c 'import json, sys
s = json.loads(sys.argv[1])
m = [m for m in s["streaming"] if m["turnId"] == sys.argv[2]]
print(json.dumps(m[0]) if m else "none")' "$1" "$2"
}
T3=33333333-aaaa-4aaa-8aaa-333333333333
ctl post "$SOCK" '[{"type":"turn","phase":"start","turnId":"'$T3'","agentId":null,"text":"x"},
 {"type":"step","phase":"start","turnId":"'$T3'","agentId":null,"step":0,"model":"m"},
 {"type":"chunk","turnId":"'$T3'","agentId":null,"step":0,"chunkIndex":0,"chunk":{"kind":"text","index":0,"text":"A"}},
 {"type":"chunk","turnId":"'$T3'","agentId":null,"step":0,"chunkIndex":2,"chunk":{"kind":"text","index":0,"text":"C"}}]' >/dev/null
watch_json "$SID" "$T/w7"
until_true 100 has_lines "$T/w7" 1 || true
assert_equals "$(streaming_of "$(nth_line "$T/w7" 1)" "$T3")" "none" "a message a chunk is missing from is left out of the snapshot"
ctl post "$SOCK" '[{"type":"gap","dropped":2},
 {"type":"resync","turns":[{"turnId":"'$T3'","agentId":null}],
  "agents":[{"agentId":"a7","subagentType":"general-purpose","running":true}],
  "streaming":[{"turnId":"'$T3'","agentId":null,"step":0,"model":"m","upTo":2,"blocks":[{"index":0,"kind":"text","text":"ABC","upTo":2}]}]},
 {"type":"chunk","turnId":"'$T3'","agentId":null,"step":0,"chunkIndex":3,"chunk":{"kind":"text","index":0,"text":"D"}}]' >/dev/null
watch_json "$SID" "$T/w8"
until_true 100 has_lines "$T/w8" 1 || true
M3="$(streaming_of "$(nth_line "$T/w8" 1)" "$T3")"
assert_equals "$(field_of "$M3" blocks.0.text)" "ABCD" "after the resync the message is whole again, the next chunk on it"
assert_equals "$(field_of "$M3" blocks.0.upTo)" "3" "its upTo the last chunk its text holds"
assert_equals "$(field_of "$(nth_line "$T/w8" 1)" turns.0.turnId)" "$T3" "the resync replaced the open turns"
assert_equals "$(field_of "$(nth_line "$T/w8" 1)" agents.0.agentId)" "a7" "and the subagents"

# Streaming is per content block: a thinking block, then text, then a tool
# call whose arguments stream. A block-row (the engine wrote the block's
# transcript row) settles its block: the snapshot keeps only the blocks
# without one, and a late chunk for a settled block is ignored.
block_indexes() { python3 -c 'import json, sys; print([b["index"] for b in json.loads(sys.argv[1])["blocks"]])' "$1"; }
T6=66666666-aaaa-4aaa-8aaa-666666666666
ctl post "$SOCK" '[{"type":"turn","phase":"start","turnId":"'$T6'","agentId":null,"text":"x"},
 {"type":"step","phase":"start","turnId":"'$T6'","agentId":null,"step":0,"model":"m"},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":0,"chunk":{"kind":"thinking","index":0,"text":"hm"}},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":1,"chunk":{"kind":"text","index":1,"text":"Run"}},
 {"type":"block-row","uuid":"row-think","turnId":"'$T6'","agentId":null,"step":0,"index":0},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":2,"chunk":{"kind":"text","index":1,"text":"ning"}},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":3,"chunk":{"kind":"tool","index":2,"id":"toolu_9","name":"Bash"}},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":4,"chunk":{"kind":"input","index":2,"json":"{\"comm"}}]' >/dev/null
watch_json "$SID" "$T/w10"
until_true 100 has_lines "$T/w10" 1 || true
M6="$(streaming_of "$(nth_line "$T/w10" 1)" "$T6")"
assert_equals "$(block_indexes "$M6")" "[1, 2]" "a block whose row was written leaves the snapshot; the others stay, by index"
assert_equals "$(field_of "$M6" blocks.0.text)" "Running" "a text block holds its text"
assert_equals "$(field_of "$M6" blocks.1.kind)/$(field_of "$M6" blocks.1.name)/$(field_of "$M6" blocks.1.id)" "tool/Bash/toolu_9" \
  "a tool block names the tool and the call"
assert_equals "$(field_of "$M6" blocks.1.text)" '{"comm' "and holds its arguments as they stream"
assert_equals "$(field_of "$M6" upTo)" "4" "the message's upTo counts every chunk, a settled block's included"
ctl post "$SOCK" '[{"type":"block-row","uuid":"row-text","turnId":"'$T6'","agentId":null,"step":0,"index":1},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":5,"chunk":{"kind":"text","index":1,"text":"late"}}]' >/dev/null
watch_json "$SID" "$T/w11"
until_true 100 has_lines "$T/w11" 1 || true
M6="$(streaming_of "$(nth_line "$T/w11" 1)" "$T6")"
assert_equals "$(block_indexes "$M6")" "[2]" "a chunk for a settled block is ignored"
assert_equals "$(field_of "$M6" upTo)" "5" "though the message's upTo moves past it"
# A resync between the block-row and a late chunk: the block stays settled,
# from this child's own memory when the mod's copy does not name it, and from
# the copy's `settled` for a message this child never saw (a child that took
# over from another).
T7=77777777-aaaa-4aaa-8aaa-777777777777
ctl post "$SOCK" '[{"type":"resync","turns":[{"turnId":"'$T6'","agentId":null},{"turnId":"'$T7'","agentId":null}],"agents":[{"agentId":"a7","subagentType":"general-purpose","running":true}],
 "streaming":[{"turnId":"'$T6'","agentId":null,"step":0,"model":"m","upTo":5,"blocks":[{"index":1,"kind":"text","text":"Running","upTo":2},{"index":2,"kind":"tool","text":"{\"comm","upTo":4,"id":"toolu_9","name":"Bash"}]},
  {"turnId":"'$T7'","agentId":null,"step":0,"model":"m","upTo":1,"settled":[0],"blocks":[{"index":1,"kind":"text","text":"B","upTo":1}]}]},
 {"type":"chunk","turnId":"'$T6'","agentId":null,"step":0,"chunkIndex":6,"chunk":{"kind":"text","index":1,"text":"later"}},
 {"type":"chunk","turnId":"'$T7'","agentId":null,"step":0,"chunkIndex":2,"chunk":{"kind":"text","index":0,"text":"late"}}]' >/dev/null
watch_json "$SID" "$T/w11b"
until_true 100 has_lines "$T/w11b" 1 || true
assert_equals "$(block_indexes "$(streaming_of "$(nth_line "$T/w11b" 1)" "$T6")")" "[2]" \
  "after a resync whose copy still holds a block this child saw settled, its late chunk is ignored"
M7="$(streaming_of "$(nth_line "$T/w11b" 1)" "$T7")"
assert_equals "$(block_indexes "$M7")" "[1]" "a resync's settled blocks stay settled in a child that never saw their rows"
assert_equals "$(field_of "$M7" upTo)" "2" "the late chunk still moves the message on"
ctl post "$SOCK" '[{"type":"turn","phase":"complete","turnId":"'$T6'","agentId":null,"reason":"answer"},
 {"type":"turn","phase":"complete","turnId":"'$T7'","agentId":null,"reason":"answer"}]' >/dev/null

# The human view: the conversation as it streams, subagents labelled.
"$SMINOS" watch "$SID" > "$T/h1" 2>&1 &
PIDS+=("$!")
until_true 100 grep -q "watching" "$T/h1" || true
T2=22222222-aaaa-4aaa-8aaa-222222222222
ctl post "$SOCK" '[{"type":"turn","phase":"start","turnId":"'$T2'","agentId":null,"text":"tidy the docs\nplease"},
 {"type":"step","phase":"start","turnId":"'$T2'","agentId":null,"step":0,"model":"m"},
 {"type":"chunk","turnId":"'$T2'","agentId":null,"step":0,"chunkIndex":0,"chunk":{"kind":"text","index":0,"text":"On it"}},
 {"type":"tool","phase":"call","toolUseId":"tu1","tool":"Bash","agentId":null,"input":{"command":"ls docs"}},
 {"type":"chunk","turnId":"t-sub","agentId":"a7","step":0,"chunkIndex":1,"chunk":{"kind":"text","index":0,"text":" more"}},
 {"type":"tool","phase":"result","toolUseId":"tu1","tool":"Bash","agentId":null,"isError":true,"text":"ls: docs: No such file"},
 {"type":"turn","phase":"complete","turnId":"'$T2'","agentId":null,"reason":"answer"}]' >/dev/null
until_true 100 grep -q "turn ended" "$T/h1" || true
HV="$(cat "$T/h1")"
assert_contains "$HV" "» tidy the docs" "the human view prints the prompt a turn starts with"
assert_contains "$HV" "[main] On it" "the main loop's text as it streams"
assert_contains "$HV" "Bash ls docs" "a tool call with what it runs"
assert_contains "$HV" "[general-purpose a7]  more" "a subagent's text under its own label"
assert_contains "$HV" "ls: docs: No such file" "a failed tool's error"
assert_not_contains "$HV" '"type"' "and no raw JSON"

# A gap in the human view: what was printed misses the lost chunk, so the
# watcher reads a fresh snapshot and prints the message whole, then follows on.
"$SMINOS" watch "$SID" > "$T/h2" 2>&1 &
PIDS+=("$!")
until_true 100 grep -q "watching" "$T/h2" || true
T5=55555555-aaaa-4aaa-8aaa-555555555555
ctl post "$SOCK" '[{"type":"turn","phase":"start","turnId":"'$T5'","agentId":null,"text":"count"},
 {"type":"step","phase":"start","turnId":"'$T5'","agentId":null,"step":0,"model":"m"},
 {"type":"chunk","turnId":"'$T5'","agentId":null,"step":0,"chunkIndex":0,"chunk":{"kind":"text","index":0,"text":"one "}}]' >/dev/null
until_true 100 grep -q "\[main\] one" "$T/h2" || true
ctl post "$SOCK" '[{"type":"gap","dropped":1},
 {"type":"resync","turns":[{"turnId":"'$T5'","agentId":null}],
  "agents":[{"agentId":"a7","subagentType":"general-purpose","running":true}],
  "streaming":[{"turnId":"'$T5'","agentId":null,"step":0,"model":"m","upTo":1,"blocks":[{"index":0,"kind":"text","text":"one two ","upTo":1}]}]},
 {"type":"chunk","turnId":"'$T5'","agentId":null,"step":0,"chunkIndex":2,"chunk":{"kind":"text","index":0,"text":"three"}}]' >/dev/null
until_true 100 grep -q "three" "$T/h2" || true
HV2="$(cat "$T/h2")"
assert_contains "$HV2" "events were lost" "a gap is said in the human view"
assert_contains "$HV2" "[main] one two three" "and the message is printed whole again from a fresh snapshot, the next chunk on it"
ctl post "$SOCK" '[{"type":"turn","phase":"complete","turnId":"'$T5'","agentId":null,"reason":"answer"}]' >/dev/null

# A later resync ends every subscription (DX5's one discontinuity): a
# watcher subscribes again to the same child and goes on from a fresh
# snapshot; no subscriber is handed the resync itself.
"$SMINOS" watch "$SID" > "$T/h3" 2>&1 &
PIDS+=("$!")
watch_json "$SID" "$T/w12"
until_true 100 grep -q "watching" "$T/h3" || true
until_true 100 has_lines "$T/w12" 1 || true
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[]}]' >/dev/null
until_true 100 grep -q "resubscribed" "$T/h3" || true
until_true 100 has_lines "$T/w12" 3 || true
ctl post "$SOCK" '[{"type":"turn","phase":"start","turnId":"'$T5'","agentId":null,"text":"after the resync"}]' >/dev/null
until_true 100 grep -q "after the resync" "$T/h3" || true
assert_contains "$(cat "$T/h3")" "· the session's state was sent again; resubscribed" "a watcher whose stream a resync ended says so and subscribes again"
assert_contains "$(cat "$T/h3")" "» after the resync" "and follows on"
assert_equals "$(grep -c '"type": "snapshot"' "$T/w12")" "2" "with --json, the fresh snapshot follows"
assert_not_contains "$(cat "$T/w12")" '"resync"' "and no subscriber is handed the resync"
ctl post "$SOCK" '[{"type":"turn","phase":"complete","turnId":"'$T5'","agentId":null,"reason":"answer"}]' >/dev/null

# What the session started as stays in the snapshot past its end.
ctl post "$SOCK" '[{"type":"session","phase":"start","session":"'$SID'","cwd":"/w","model":"m"},
 {"type":"session","phase":"end","reason":"clear"}]' >/dev/null
watch_json "$SID" "$T/w6"
until_true 100 has_lines "$T/w6" 1 || true
assert_equals "$(field_of "$(nth_line "$T/w6" 1)" sessionInfo.cwd)" "/w" "the snapshot carries what the session started as"
assert_equals "$(field_of "$(nth_line "$T/w6" 1)" sessionInfo.ended)" "clear" "and why it ended, once it has"

# Ending: the child follows its parent, and a watcher says the bridge ended.
kill "$FAKEMOD"
wait "$FAKEMOD" 2>/dev/null || true
until_true 100 test ! -e "$SOCK" || true
assert_equals "$([ -e "$SOCK" ] && echo present || echo gone)" "gone" "the child exits when the session (its parent) is gone, removing its socket"
set +e; wait "$WATCHER"; WRC=$?; set -e
assert_rc 1 "$WRC" "a watcher whose bridge ended exits 1"
assert_contains "$(cat "$T/w6")" "the bridge ended" "saying so"

# No bridge, and a stale socket: said, non-zero, and the stale file removed.
run "$SMINOS" watch "$SID"
assert_rc 4 "$RC" "watch on a session with no bridge exits 4"
assert_contains "$OUT" "no bridge" "saying it has no bridge"
ctl stale "$SOCK"
run "$SMINOS" watch "$SID" --json
assert_rc 4 "$RC" "a socket file nobody answers is no bridge either"
assert_equals "$([ -e "$SOCK" ] && echo present || echo gone)" "gone" "whoever finds a stale socket removes it"

# A stale socket left by a dead child is replaced by the next child.
ctl stale "$SOCK"
fakemod "$SID" "$T/lines-b"
until_true 100 answers "$SOCK" || true
assert_equals "$(answers "$SOCK" && echo yes || echo no)" "yes" "a new child replaces a stale socket"
FIRST="$(child_pid "$SOCK")"

# A newer child for the same session takes the endpoint over (a module reload
# spawns one before the old is gone); the older exits without removing it.
watch_json "$SID" "$T/w4"
until_true 100 has_lines "$T/w4" 1 || true
fakemod "$SID" "$T/lines-c"
until_true 100 bash -c '[ "$(python3 "$1/ctl.py" get "$2" /status 2>/dev/null | python3 -c "import json, sys; print(json.loads(sys.stdin.read().split(\" \", 1)[1])[\"pid\"])" 2>/dev/null)" != "$3" ]' _ "$T" "$SOCK" "$FIRST" || true
SECOND="$(child_pid "$SOCK")"
assert_equals "$([ "$SECOND" != "$FIRST" ] && echo replaced || echo same)" "replaced" "a newer child for the session takes the endpoint over"
until_true 100 bash -c '! kill -0 "$1" 2>/dev/null' _ "$FIRST" || true
assert_equals "$(kill -0 "$FIRST" 2>/dev/null && echo alive || echo exited)" "exited" "the superseded child exits"
assert_equals "$(answers "$SOCK" && echo yes || echo no)" "yes" "leaving the newer child's socket in place"
until_true 100 grep -q "reconnected" "$T/w4" || true
assert_contains "$(cat "$T/w4")" "reconnected" "a watcher follows the endpoint to the newer child"
assert_equals "$(grep -c '"type": "snapshot"' "$T/w4")" "2" "taking a fresh snapshot there"
# A new child knows nothing until the mod's first post: the session's start and
# a resync carrying the message it replaced the old child in the middle of.
T4=44444444-aaaa-4aaa-8aaa-444444444444
ctl post "$SOCK" '[{"type":"session","phase":"start","session":"'$SID'","cwd":"/w"},
 {"type":"resync","turns":[{"turnId":"'$T4'","agentId":null}],"agents":[],
  "streaming":[{"turnId":"'$T4'","agentId":null,"step":1,"model":"m","upTo":0,"blocks":[{"index":0,"kind":"text","text":"Hel","upTo":0}]}]},
 {"type":"chunk","turnId":"'$T4'","agentId":null,"step":1,"chunkIndex":1,"chunk":{"kind":"text","index":0,"text":"lo"}}]' >/dev/null
watch_json "$SID" "$T/w9"
until_true 100 has_lines "$T/w9" 1 || true
M4="$(python3 -c 'import json, sys; print(json.dumps(json.loads(sys.argv[1])["streaming"][0]))' "$(nth_line "$T/w9" 1)")"
assert_equals "$(field_of "$M4" blocks.0.text)" "Hello" "a child that came in mid-message holds the message whole from the resync on"
assert_equals "$(field_of "$M4" blocks.0.upTo)" "1" "with the upTo of its last chunk"

# Two children starting at once: the older one moves its socket in, the newer
# one moves its own over it before the older has looked. The older must know
# itself by its own socket, find the path taken, and leave without removing it.
OVL=5d000003-0000-4000-8000-00000000005d
OVLSOCK="$SMINOS_HOME/bridge/$OVL.sock"
cat > "$T/overlap.py" <<'PY'
import os, socket, sys
sys.path.insert(0, sys.argv[1])
import sminos_bridge as B
real_replace = os.replace
held = []
def racing_replace(src, dst):
    real_replace(src, dst)
    if dst.endswith(".sock") and not held:
        newer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        newer.bind(dst + ".n")
        newer.listen(1)
        held.append(newer)
        real_replace(dst + ".n", dst)
os.replace = racing_replace
B.serve(sys.argv[2])
PY
python3 "$T/overlap.py" "$REPO_ROOT/skills/sminos/scripts" "$OVL" > "$T/overlap.out" 2>&1 &
OVLPID=$!
PIDS+=("$OVLPID")
until_true 60 bash -c '! kill -0 "$1" 2>/dev/null' _ "$OVLPID" || true
if kill -0 "$OVLPID" 2>/dev/null; then
  fail "the older of two overlapping children exits, the path not its own"
  kill "$OVLPID"; wait "$OVLPID" 2>/dev/null || true
else
  pass "the older of two overlapping children exits, the path not its own"
fi
assert_equals "$([ -e "$OVLSOCK" ] && echo present || echo gone)" "present" "leaving the newer child's socket where it is"
rm -f "$OVLSOCK"

# A member by name: resolved in the working directory's project.
R="$T/repo"
mkdir -p "$R"
git -c init.defaultBranch=main init -q "$R"
(cd "$R" && "$SMINOS" project init --name bridgedemo >/dev/null)
printf '{"pid":%s,"sessionId":"%s","name":"rover","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$$" "$SID" "$R" > "$HOME/.claude/sessions/rover.json"
OTHER=5c000002-0000-4000-8000-00000000005c
printf '{"pid":%s,"sessionId":"%s","name":"idler","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$$" "$OTHER" "$R" > "$HOME/.claude/sessions/idler.json"
(cd "$R" && exec "$SMINOS" watch rover --json > "$T/w5" 2>&1) &
PIDS+=("$!")
until_true 100 has_lines "$T/w5" 1 || true
assert_equals "$(field_of "$(nth_line "$T/w5" 1)" session)" "$SID" "watch resolves a member by its alias"
set +e; OUT="$(cd "$R" && "$SMINOS" watch idler 2>&1)"; RC=$?; set -e
assert_rc 4 "$RC" "a member with no bridge exits 4"
assert_contains "$OUT" "idler has no bridge" "naming the member"
set +e; OUT="$(cd "$R" && "$SMINOS" watch nobody 2>&1)"; RC=$?; set -e
assert_rc 4 "$RC" "an unknown member exits 4"

# The endpoint's path must fit a Unix socket's: a long SMINOS_HOME is refused.
LONGHOME="$T/$(printf 'x%.0s' $(seq 1 80))"
mkdir -p "$LONGHOME"
run env SMINOS_HOME="$LONGHOME" "$SMINOS" bridge --session "$SID"
assert_rc 1 "$RC" "an endpoint path too long for a Unix socket fails the child"
assert_contains "$OUT" "too long" "saying why"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES bridge assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge assertions FAILED"
  exit 1
fi
