#!/usr/bin/env bash
#
# The bridge's control verbs and delivery (DC2 M2, DX5): `sminos steer`,
# `interrupt`, `model`, `compact` through a session's endpoint, what the child
# keeps across a module reload, and a delivery's last hop — the bridge, keyed
# by the log event; the engine supervisor's `reply` for a human's event to a
# --bg job with no bridge; else the inbox frame. A stand-in for the mod
# (fakemod) spawns the child and answers its command lines as the mod would;
# a stand-in inbox socket and a stand-in supervisor control socket record what
# reaches them. Hermetic: HOME and SMINOS_HOME are temporary (SMINOS_HOME
# short, for the socket's path), so the supervisor socket sminos computes is
# that temporary config's, never a real one. run-sminos-tests.sh runs this.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SMINOS="$REPO_ROOT/skills/sminos/scripts/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smc.XXXXXX)"
PIDS=()
SUPDIR=""
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "bridge --session 5b000001-0000-4000-8000-0000000000c1" >/dev/null 2>&1 || break; sleep 0.05; done
  [ -n "$SUPDIR" ] && rm -rf "$SUPDIR"
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
field_of() { # json-text dotted.path
  python3 -c 'import json, sys
v = json.loads(sys.argv[1])
for k in sys.argv[2].split("."):
    v = v[int(k)] if isinstance(v, list) else v.get(k)
print(v if isinstance(v, str) else json.dumps(v))' "$1" "$2"
}
last_op() { # lines-file op → the last command line of that op
  python3 -c 'import json, sys
hits = [l for l in open(sys.argv[1]) if json.loads(l).get("op") == sys.argv[2]]
print(hits[-1].strip() if hits else "")' "$1" "$2"
}
count_op() { python3 -c 'import json, sys; print(sum(1 for l in open(sys.argv[1]) if json.loads(l).get("op") == sys.argv[2]))' "$1" "$2"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME CLAUDE_CONFIG_DIR
export HOME="$T/home"
export SMINOS_HOME="$T/s"
export DAEMON_HOST=testhost
mkdir -p "$HOME/.claude/sessions"
mkdir -m 700 "$SMINOS_HOME"
SID=5b000001-0000-4000-8000-0000000000c1
SOCK="$SMINOS_HOME/bridge/$SID.sock"
KEPT="$SMINOS_HOME/bridge/$SID.json"

cat > "$T/ctl.py" <<'PY'
import hashlib, http.client, json, os, socket, socketserver, subprocess, sys, threading, time

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

def post(sock, events):
    request(sock, "POST", "/events", json.dumps(events))

def serve_lines(path, out, answer):
    """A Unix socket that appends what each connection sent to `out` and
    answers it with answer(line) (None: no answer)."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    class H(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline()
            if not line.strip():   # a liveness probe: connected, sent nothing
                return
            with open(out, "a") as f:
                f.write(line.decode().rstrip("\n") + "\n")
            reply = answer(line)
            if reply is not None:
                self.wfile.write((json.dumps(reply) + "\n").encode())
    srv = socketserver.UnixStreamServer(path, H)
    srv.serve_forever()

op = sys.argv[1]
if op == "post":            # sock events-json
    print(request(sys.argv[2], "POST", "/events", sys.argv[3])[0])
elif op == "get":           # sock url
    status, text = request(sys.argv[2], "GET", sys.argv[3])
    print(status, text)
elif op == "inbox":         # path out — a session's inbox socket
    serve_lines(sys.argv[2], sys.argv[3], lambda line: None)
elif op == "supervisor":    # path out mode — the engine supervisor's control.sock: `reply` answered ok, or refused
    mode = sys.argv[4]
    def answer(line):
        req = json.loads(line)
        if mode == "refuse":
            return {"ok": False, "code": "ENOREPLY", "error": "job isn't accepting replies"}
        return {"ok": True, "op": req.get("op")}
    serve_lines(sys.argv[2], sys.argv[3], answer)
elif op == "supsock":       # home → where sminos looks for that config's supervisor
    cfg = os.path.abspath(os.path.join(sys.argv[2], ".claude"))
    print(os.path.join("/tmp", "cc-daemon-%d" % os.getuid(), hashlib.sha256(cfg.encode()).hexdigest()[:8], "control.sock"))
elif op == "fakemod":       # sminos session lines-file mode-file
    # Spawns the child as the mod does, and answers its command lines as the
    # mod would; mode-file says whether a turn is running ("busy"), the
    # session is idle ("idle"), or deliveries are refused ("refuse").
    sminos, session, out, modefile = sys.argv[2:6]
    # The child's stderr is the mod's debug log: kept beside the lines.
    child = subprocess.Popen([sminos, "bridge", "--session", session], stdout=subprocess.PIPE,
                             stderr=open(out + ".err", "a"), text=True)
    sock = None
    delivered = {}
    with open(out, "a") as f:
        for line in child.stdout:
            f.write(line)
            f.flush()
            msg = json.loads(line)
            if msg.get("op") == "hello":
                sock = msg["socket"]
                keep_nonce(msg)
                delivered = dict((msg.get("kept") or {}).get("delivered") or {})
                post(sock, [{"type": "resync", "turns": [], "streaming": [], "agents": []}])
                continue
            mode = open(modefile).read().strip() if os.path.exists(modefile) else "busy"
            cid, o = msg["id"], msg["op"]
            events, result = [], None
            if mode == "unknown" and o in ("steer", "interrupt", "compact"):
                result = {"ok": False, "error": "turn state unknown since the bridge reloaded; retry after the next model request"}
            elif o == "steer":
                result = {"ok": False, "error": "no turn is running to steer: send it instead"} if mode == "idle" \
                    else {"ok": True, "result": {"row": "row-uuid-1"}}
            elif o == "interrupt":
                result = {"ok": True, "result": {"turnId": None, "stopped": [], "running": []}} if mode == "idle" \
                    else {"ok": True, "result": {"turnId": "t1", "stopped": ["b5y6zo7fe"], "running": ["stuck01"]}} \
                    if mode == "stuck" else {"ok": True, "result": {"turnId": "t1", "stopped": ["b5y6zo7fe"], "running": []}}
            elif o == "stop":
                result = {"ok": False, "error": "Task %s is not running (status: completed)" % msg.get("taskId")} \
                    if msg.get("taskId") == "bdone001" else {"ok": True, "result": {"taskId": msg.get("taskId")}}
            elif o == "model":
                pick = {"model": msg.get("model"), "effort": msg.get("effort")}
                events.append({"type": "model", **pick})
                result = {"ok": True, "result": pick}
            elif o == "compact":
                if mode == "idle":
                    result = {"ok": True, "result": {"started": True}}
                    later = [{"type": "compact", "phase": "start", "id": cid},
                             {"type": "compact", "phase": "end", "id": cid, "tokensBefore": 900, "tokensAfter": 100}]
                    threading.Timer(0.3, post, (sock, later)).start()
                else:
                    result = {"ok": True, "result": {"queued": True, "turnId": "t1"}}
            elif o == "deliver":
                key = msg["key"]
                if mode == "refuse":
                    result = {"ok": False, "error": "deliver needs key {writer, seq} and text"}
                elif key["seq"] <= delivered.get(key["writer"], 0):
                    events.append({"type": "delivered", "key": key, "outcome": "duplicate"})
                    result = {"ok": True, "result": {"duplicate": True}}
                else:
                    delivered[key["writer"]] = key["seq"]
                    events.append({"type": "delivered", "key": key, "outcome": "submitted"})
                    result = {"ok": True, "result": {"submitted": True}}
            else:
                result = {"ok": False, "error": "unknown op: %s" % o}
            post(sock, events + [{"type": "result", "id": cid, "op": o, **result}])
    child.wait()
PY
ctl() { python3 "$T/ctl.py" "$@"; }
answers() { ctl get "$1" /status 2>/dev/null | grep -q '"ready": true'; }
fakemod() { # session lines-file → starts the stand-in, which starts the child
  python3 "$T/ctl.py" fakemod "$SMINOS" "$1" "$2" "$T/mode" &
  FAKEMOD=$!
  PIDS+=("$FAKEMOD")
}
snapshot() { python3 -c 'import http.client, socket, sys
class C(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.sock.connect(sys.argv[1])
c = C("bridge"); c.request("GET", "/events"); print(c.getresponse().readline().decode().strip())' "$1"; }
mode() { printf '%s\n' "$1" > "$T/mode"; }

echo "what the child keeps:"
mode busy
fakemod "$SID" "$T/lines-a"
until_true 100 answers "$SOCK" || true
assert_equals "$(field_of "$(sed -n 1p "$T/lines-a")" kept)" '{"override": null, "delivered": {}}' "a first child's hello says it keeps nothing yet"
ctl post "$SOCK" '[{"type":"model","model":"sonnet","effort":"high"},
 {"type":"delivered","key":{"writer":"testhost/human","seq":3},"outcome":"submitted"},
 {"type":"delivered","key":{"writer":"testhost/human","seq":2},"outcome":"duplicate"}]' >/dev/null
assert_equals "$(cat "$KEPT")" '{"override": {"model": "sonnet", "effort": "high"}, "delivered": {"testhost/human": 3}}' \
  "the model chosen and the highest key delivered per writer are kept in <session>.json"
assert_equals "$(python3 -c 'import os, sys; print("%04o" % (os.stat(sys.argv[1]).st_mode & 0o777))' "$KEPT")" "0600" "owner-only"
assert_equals "$(field_of "$(snapshot "$SOCK")" override)" '{"model": "sonnet", "effort": "high"}' "the snapshot carries the session's model choice"
ctl post "$SOCK" '[{"type":"resync","turns":[],"streaming":[],"agents":[],"override":null,"delivered":{"testhost/human":3,"other/x":1}}]' >/dev/null
assert_equals "$(cat "$KEPT")" '{"override": null, "delivered": {"testhost/human": 3, "other/x": 1}}' "a resync replaces what is kept with the mod's own"
ctl post "$SOCK" '[{"type":"model","model":"opus","effort":null}]' >/dev/null

# A module reload kills the child with a signal while the session goes on:
# what was kept stays, and the next child's hello hands it back.
CHILD="$(ctl get "$SOCK" /status | python3 -c 'import json, sys; print(json.loads(sys.stdin.read().split(" ", 1)[1])["pid"])')"
kill -TERM "$CHILD"
until_true 100 test ! -e "$SOCK" || true
assert_equals "$([ -e "$KEPT" ] && echo kept || echo gone)" "kept" "a child stopped by a signal (a reload) leaves what it kept"
fakemod "$SID" "$T/lines-b"
until_true 100 answers "$SOCK" || true
assert_equals "$(field_of "$(sed -n 1p "$T/lines-b")" kept)" '{"override": {"model": "opus", "effort": null}, "delivered": {"testhost/human": 3, "other/x": 1}}' \
  "and the next child's hello carries it back to the mod"
# The first fakemod's parent role ended with its child; stop it.
kill "${PIDS[0]}" 2>/dev/null || true

# A write that fails is said on the stream, and not taken as kept: the next
# change writes the whole of what the mod handed over, the failed part included.
WATCHK="$T/wk"
"$SMINOS" watch "$SID" --json > "$WATCHK" 2>&1 &
PIDS+=("$!")
until_true 100 test -s "$WATCHK" || true
chmod 500 "$SMINOS_HOME/bridge"
ctl post "$SOCK" '[{"type":"model","model":"claude-fable-5","effort":"max"}]' >/dev/null
chmod 700 "$SMINOS_HOME/bridge"
until_true 100 grep -q '"type": "kept"' "$WATCHK" || true
KEPTEV="$(grep -m1 '"type": "kept"' "$WATCHK" || echo '{}')"
assert_equals "$(field_of "$KEPTEV" ok)" "false" "a write the child could not make is said on the stream as a kept event"
assert_contains "$(field_of "$KEPTEV" error)" "ermission denied" "with the reason"
assert_not_contains "$(cat "$KEPT")" "claude-fable-5" "and the file still holds what it held"
ctl post "$SOCK" '[{"type":"model","model":"claude-fable-5","effort":"max"}]' >/dev/null
assert_contains "$(cat "$KEPT")" '"model": "claude-fable-5"' "the same choice sent again is written: a failed write was not taken as kept"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"testhost/human","seq":9},"outcome":"submitted"}]' >/dev/null
assert_equals "$(cat "$KEPT")" '{"override": {"model": "claude-fable-5", "effort": "max"}, "delivered": {"testhost/human": 9, "other/x": 1}}' \
  "the next change writes the model choice that failed to land as well"
# A delivery key whose write failed is written by the next event, though that
# event (a duplicate of it, a heartbeat) moves no key.
chmod 500 "$SMINOS_HOME/bridge"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"mac/human","seq":1},"outcome":"submitted"}]' >/dev/null
chmod 700 "$SMINOS_HOME/bridge"
assert_not_contains "$(cat "$KEPT")" "mac/human" "a delivery key whose write failed is not in the file"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"mac/human","seq":1},"outcome":"duplicate"}]' >/dev/null
assert_contains "$(cat "$KEPT")" '"mac/human": 1' "the next event, a duplicate moving no key, writes it"
# $WATCHK fills asynchronously: the baseline below is taken only once the
# recovery just above has reached it. A recovery follows the failure it
# recovers from, so both are in then; the stream holds two recoveries by now
# (the model choice's and this key's).
kept_oks() { grep -c '"type": "kept", "ok": true' "$WATCHK" || true; }
kept_oks_reach() { [ "$(kept_oks)" -ge "$1" ]; }
until_true 100 kept_oks_reach 2 || true
assert_equals "$(kept_oks)" "2" "the stream has said the earlier recoveries before the failures are counted"
chmod 500 "$SMINOS_HOME/bridge"
FAILS="$(grep -c '"type": "kept", "ok": false' "$WATCHK" || true)"
ctl post "$SOCK" '[{"type":"delivered","key":{"writer":"mac/human","seq":2},"outcome":"submitted"}]' >/dev/null
ctl post "$SOCK" '[{"type":"heartbeat","state":{}}]' >/dev/null
chmod 700 "$SMINOS_HOME/bridge"
until_true 100 bash -c '[ "$(grep -c "\"type\": \"kept\", \"ok\": false" "$1")" -gt "$2" ]' _ "$WATCHK" "$FAILS" || true
assert_equals "$(( $(grep -c '"type": "kept", "ok": false' "$WATCHK") - FAILS ))" "1" \
  "a failure that persists over several events is said once"
ctl post "$SOCK" '[{"type":"heartbeat","state":{}}]' >/dev/null
assert_contains "$(cat "$KEPT")" '"mac/human": 2' "and a heartbeat writes it once the write can be made"
until_true 100 kept_oks_reach 3 || true
assert_equals "$(kept_oks)" "3" "the recovery is said on the stream too, once"
ctl post "$SOCK" '[{"type":"model","model":"opus","effort":null},
 {"type":"resync","turns":[],"streaming":[],"agents":[],"override":{"model":"opus","effort":null},"delivered":{"testhost/human":3,"other/x":1}}]' >/dev/null

echo "the control verbs, bridged:"
mode busy
run "$SMINOS" steer "$SID" "also print the date"
assert_rc 0 "$RC" "steer exits 0"
assert_contains "$OUT" "row-uuid-1" "naming the row it appended"
assert_equals "$(field_of "$(last_op "$T/lines-b" steer)" text)" "also print the date" "the text reached the mod as a steer"
mode idle
run "$SMINOS" steer "$SID" "anyone?"
assert_rc 1 "$RC" "a steer the session refuses (idle) exits 1"
assert_contains "$OUT" "no turn is running" "with the session's reason"
mode busy
run "$SMINOS" interrupt "$SID"
assert_rc 0 "$RC" "interrupt exits 0"
assert_contains "$OUT" "b5y6zo7fe" "naming the background task it stopped"
mode stuck
run "$SMINOS" interrupt "$SID"
assert_rc 1 "$RC" "an interrupt that left a background task running exits 1"
assert_contains "$OUT" "stuck01" "naming the task still running"
assert_contains "$OUT" "still running" "and saying so"
mode idle
run "$SMINOS" interrupt "$SID"
assert_contains "$OUT" "nothing to interrupt" "an idle session has nothing to interrupt, said so"
run "$SMINOS" stop "$SID" bsrv0001
assert_rc 0 "$RC" "stop exits 0"
assert_contains "$OUT" "bsrv0001" "naming the task it stopped"
assert_equals "$(field_of "$(last_op "$T/lines-b" stop)" taskId)" "bsrv0001" "the task reached the mod as a stop"
run "$SMINOS" stop "$SID" bdone001
assert_rc 1 "$RC" "a stop the engine refuses exits 1"
assert_contains "$OUT" "is not running (status: completed)" "in the engine's words"
# After a module reload, until the mod knows whether a turn runs, the verbs
# that need it are refused with the reason: never a false idle.
mode unknown
for VERB in "interrupt" "steer|and the date" "compact"; do
  IFS='|' read -r V ARG <<<"$VERB"
  if [ -n "$ARG" ]; then run "$SMINOS" "$V" "$SID" "$ARG"; else run "$SMINOS" "$V" "$SID"; fi
  assert_rc 1 "$RC" "$V while the turn state is unknown exits 1"
  assert_contains "$OUT" "turn state unknown since the bridge reloaded; retry after the next model request" "saying why ($V)"
done
mode idle
run "$SMINOS" model "$SID" sonnet --effort high
assert_rc 0 "$RC" "model exits 0"
assert_contains "$OUT" "sonnet" "saying the model in force"
L="$(last_op "$T/lines-b" model)"
assert_equals "$(field_of "$L" model)/$(field_of "$L" effort)" "sonnet/high" "the model and effort reached the mod"
run "$SMINOS" model "$SID" default
L="$(last_op "$T/lines-b" model)"
assert_equals "$(field_of "$L" model)/$(field_of "$L" effort)" "null/null" "default clears the choice"
run "$SMINOS" model "$SID" sonnet --effort turbo
assert_rc 2 "$RC" "an effort that is none is a usage error"
mode busy
run "$SMINOS" compact "$SID"
assert_rc 0 "$RC" "compact during a turn exits 0"
assert_contains "$OUT" "when the running turn ends" "saying it is queued for the turn's end"
mode idle
run "$SMINOS" compact "$SID" "keep the plan"
assert_rc 0 "$RC" "compact on an idle session exits 0"
assert_contains "$OUT" "900 → 100" "once it has run, with the counts"
assert_equals "$(field_of "$(last_op "$T/lines-b" compact)" instructions)" "keep the plan" "its instructions reached the mod"

echo "the control verbs, no bridge:"
NOB=5c000002-0000-4000-8000-0000000000c2
for verb in interrupt stop model compact; do
  if [ "$verb" = model ]; then run "$SMINOS" model "$NOB" sonnet
  elif [ "$verb" = stop ]; then run "$SMINOS" stop "$NOB" bsrv0001
  else run "$SMINOS" "$verb" "$NOB"; fi
  assert_rc 4 "$RC" "$verb with no bridge exits 4"
  assert_contains "$OUT" "no bridge" "saying so"
done

echo "delivery:"
R="$T/repo"
mkdir -p "$R"
git -c init.defaultBranch=main init -q "$R"
(cd "$R" && "$SMINOS" project init --name ctldemo >/dev/null)
INBOX="$T/rover.sock"
python3 "$T/ctl.py" inbox "$INBOX" "$T/rover-inbox" &
PIDS+=("$!")
until_true 100 test -S "$INBOX" || true
printf '{"pid":%s,"sessionId":"%s","name":"rover","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$SID" "$R" "$INBOX" > "$HOME/.claude/sessions/rover.json"
mode busy
set +e; OUT="$(cd "$R" && "$SMINOS" say "@rover read the plan" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a human's say to a bridged member exits 0"
assert_contains "$OUT" "rover: sent" "reporting it sent"
L="$(last_op "$T/lines-b" deliver)"
assert_equals "$(field_of "$L" key.writer)" "testhost/human" "it went through the bridge, keyed by the event's writer"
SEQ="$(field_of "$L" key.seq)"
LOGSEQ="$(python3 -c 'import glob, json, sys
for p in glob.glob(sys.argv[1] + "/projects/*/log/testhost.human.jsonl"):
    for l in open(p):
        e = json.loads(l)
        if e.get("text") == "@rover read the plan":
            print(e["seq"])' "$SMINOS_HOME")"
assert_equals "$SEQ" "$LOGSEQ" "and its seq"
assert_contains "$(field_of "$L" text)" "[sminos chat ctldemo" "the text is the frame the inbox would carry"
assert_contains "$(field_of "$L" text)" "read the plan" "with the message"
assert_equals "$([ -s "$T/rover-inbox" ] && echo framed || echo none)" "none" "and nothing went to the inbox socket"
set +e; OUT="$(cd "$R" && "$SMINOS" send rover "check the tests" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "send to a bridged member exits 0"
L="$(last_op "$T/lines-b" deliver)"
assert_contains "$(field_of "$L" text)" "[sminos message from human id=" "send's own frame went through the bridge"
assert_equals "$(( $(field_of "$L" key.seq) > SEQ ))" "1" "keyed by its own event"
# The bridge refusing a delivery (it did not submit) leaves the inbox frame.
mode refuse
set +e; OUT="$(cd "$R" && "$SMINOS" say "@rover second try" 2>&1)"; RC=$?; set -e
assert_contains "$OUT" "rover: sent" "a delivery the bridge refuses still reaches the member"
until_true 100 test -s "$T/rover-inbox" || true
assert_contains "$(cat "$T/rover-inbox" 2>/dev/null)" "second try" "through its inbox socket"
mode busy

# A --bg job with no bridge: a human's event goes through the engine
# supervisor's control socket (`reply`, human-origin), else the inbox frame.
BG=5d000003-0000-4000-8000-0000000000c3
BGINBOX="$T/bg.sock"
python3 "$T/ctl.py" inbox "$BGINBOX" "$T/bg-inbox" &
PIDS+=("$!")
until_true 100 test -S "$BGINBOX" || true
printf '{"pid":%s,"sessionId":"%s","name":"bgone","nameSource":"user","kind":"bg","jobId":"0a1b2c3d","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$BG" "$R" "$BGINBOX" > "$HOME/.claude/sessions/bgone.json"
SUP="$(ctl supsock "$HOME")"
SUPDIR="$(dirname "$SUP")"
case "$SUPDIR" in /tmp/cc-daemon-*/????????) ;; *) echo "refusing an unexpected supervisor path: $SUPDIR"; exit 1 ;; esac
# The engine's own socket root is owner-only at every level; so is the stand-in's.
[ -d "$(dirname "$SUPDIR")" ] || mkdir -m 700 "$(dirname "$SUPDIR")"
mkdir -m 700 "$SUPDIR" "$HOME/.claude/daemon"
printf '0123456789abcdef0123456789abcdef' > "$HOME/.claude/daemon/control.key"
python3 "$T/ctl.py" supervisor "$SUP" "$T/sup-in" ok &
SUPPID=$!
PIDS+=("$SUPPID")
until_true 100 test -S "$SUP" || true
set +e; OUT="$(cd "$R" && "$SMINOS" say "@bgone pick up the review" 2>&1)"; RC=$?; set -e
assert_contains "$OUT" "bgone: sent" "a human's say to a --bg job with no bridge is sent"
REQ="$(tail -1 "$T/sup-in" 2>/dev/null)"
assert_equals "$(field_of "$REQ" op)" "reply" "through the supervisor's reply"
assert_equals "$(field_of "$REQ" short)" "0a1b2c3d" "to the job"
assert_equals "$(field_of "$REQ" auth)" "0123456789abcdef0123456789abcdef" "presenting the control key"
assert_equals "$(field_of "$REQ" nextTurn)" "true" "as queued input, never an answer to an open question"
assert_contains "$(field_of "$REQ" text)" "pick up the review" "carrying the frame"
assert_equals "$([ -s "$T/bg-inbox" ] && echo framed || echo none)" "none" "and not the inbox frame"
run "$SMINOS" steer "$BG" "stop after this file"
assert_rc 0 "$RC" "a steer to a --bg job with no bridge exits 0"
assert_contains "$OUT" "supervisor" "through the supervisor"
assert_contains "$(tail -1 "$T/sup-in")" "stop after this file" "which got the text"
# A peer's say is a peer message, as today: the inbox frame.
set +e; OUT="$(cd "$R" && CLAUDE_CODE_SESSION_ID="$SID" "$SMINOS" say "@bgone from a peer" 2>&1)"; RC=$?; set -e
until_true 100 test -s "$T/bg-inbox" || true
assert_contains "$(cat "$T/bg-inbox" 2>/dev/null)" "from a peer" "a session's say to it is the inbox frame"
assert_not_contains "$(cat "$T/sup-in")" "from a peer" "not the supervisor's reply"
# The supervisor refusing: the inbox frame.
kill "$SUPPID"; wait "$SUPPID" 2>/dev/null || true
python3 "$T/ctl.py" supervisor "$SUP" "$T/sup-in" refuse &
PIDS+=("$!")
until_true 100 test -S "$SUP" || true
set +e; OUT="$(cd "$R" && "$SMINOS" say "@bgone refused then framed" 2>&1)"; RC=$?; set -e
assert_contains "$OUT" "bgone: sent" "a reply the supervisor refuses still reaches the job"
until_true 100 grep -q "refused then framed" "$T/bg-inbox" || true
assert_contains "$(cat "$T/bg-inbox")" "refused then framed" "as the inbox frame"
# A terminal session with no bridge: a steer goes as a cross-session frame.
TERM_SID=5e000004-0000-4000-8000-0000000000c4
TINBOX="$T/term.sock"
python3 "$T/ctl.py" inbox "$TINBOX" "$T/term-inbox" &
PIDS+=("$!")
until_true 100 test -S "$TINBOX" || true
printf '{"pid":%s,"sessionId":"%s","name":"termy","nameSource":"user","kind":"interactive","status":"busy","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$TERM_SID" "$R" "$TINBOX" > "$HOME/.claude/sessions/termy.json"
set +e; OUT="$(cd "$R" && "$SMINOS" steer termy "mind the tabs" 2>&1)"; RC=$?; set -e
assert_rc 0 "$RC" "a steer to a terminal session with no bridge exits 0"
assert_contains "$OUT" "frame" "as a cross-session frame"
until_true 100 test -s "$T/term-inbox" || true
assert_contains "$(cat "$T/term-inbox" 2>/dev/null)" "mind the tabs" "which its inbox got"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES bridge control assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge control assertions FAILED"
  exit 1
fi
