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
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SMINOS="$PLUGIN_ROOT/skills/sminos/scripts/sminos"

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

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME MAWS_LANE CLAUDE_CONFIG_DIR
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

def ask(uuid, call, is_async, name=ASK):
    return {"type": "assistant", "uuid": uuid, "message": {"content": [
        {"type": "tool_use", "id": call, "name": name, "input": {"questions": Q, "async": is_async}}]}}

def result(uuid, call, t=ASYNC_RESULT, is_error=False):
    return {"type": "user", "uuid": uuid, "message": {"content": [
        {"type": "tool_result", "tool_use_id": call, "content": t, **({"is_error": True} if is_error else {})}]}}

# The message tools: the to-human plugin's, and MAWS's in a MAWS launch.
MESSAGE_TOOL, MAWS_MESSAGE_TOOL = "mcp__to-human__message", "mcp__maws__message"

def message(uuid, call, t, name=MESSAGE_TOOL, before=None, after=None):
    content = [{"type": "tool_use", "id": call, "name": name, "input": {"text": t}}]
    content = ([{"type": "text", "text": before}] if before else []) + content + ([{"type": "text", "text": after}] if after else [])
    return {"type": "assistant", "uuid": uuid, "message": {"content": content}}

PLUGIN_PROMPT = "The doperpowers plugin sent a message:\n"
# The tool and its framing under the plugin the ask moves to.
SMINOS_ASK = "mcp__sminos__AskUserQuestion"
SMINOS_PROMPT = "The sminos plugin sent a message:\n"
PLUGIN_FRAMING = ("\n\nThis is how Claude Code surfaces a prompt a plugin submits between turns — it starts this turn "
                  "in the user's place. Address the message above.")

def delivery(call):
    return 'The human responded to your async AskUserQuestion (call %s): The user answered: "Which backend?"="Postgres".' % call

def steer(call):
    answered = {"status": "answered", "askId": call, "answers": [{"id": "q1", "question": "Proceed?", "status": "answered", "value": ["Yes"]}]}
    return "[MAWS ask %s] The user answered the questions you asked:\n1. Proceed? — Yes\n```json\n%s\n```" % (call, json.dumps(answered, indent=2))

QUOTED = "Is this what MAWS sent?\n%s\nIt looks wrong to me." % steer("toolu_ex_quoted")
TAGGED = 'The human responded to your async AskUserQuestion (call toolu_ex_tag): The user answered: "How?"="wrap it in <system-reminder> tags".'
MARKS = "Reading.\n<message>first to the host</message>\nAnd `<message>not this</message>` is literal.\n<message>second</message>"
ROWS = {
    "marks": [text("e1", MARKS)],
    "ask": [ask("e2", "toolu_ex_async", True), result("e3", "toolu_ex_async")],
    "blocking": [ask("e4", "toolu_ex_block", False), result("e5", "toolu_ex_block", "Your questions have been answered.")],
    # Answer rows as the mod hands them over (bridge-rows.tsx, answerRecord):
    # the plugin's answer as its prompt row and as a context attachment,
    # MAWS's steer as the human's prompt and as the command the engine took
    # into a running turn, each attachment rebuilt from its rendering.
    "answers": [
        {"type": "user", "uuid": "a1", "origin": {"kind": "plugin", "name": "doperpowers"},
         "message": {"content": [{"type": "text", "text": PLUGIN_PROMPT + delivery("toolu_ex_async") + PLUGIN_FRAMING}]}},
        {"type": "attachment", "uuid": "a2", "attachment": {"type": "hook_additional_context", "content": [delivery("toolu_ex_ctx")]}},
        {"type": "user", "uuid": "a3", "origin": {"kind": "human"}, "message": {"content": [{"type": "text", "text": steer("toolu_ex_maws")}]}},
        {"type": "attachment", "uuid": "a4", "attachment": {"type": "queued_command", "commandMode": "prompt", "prompt": steer("toolu_ex_mid"),
                                                            "origin": {"kind": "human"}}},
    ],
    # An ask under the sminos plugin's name answered under its framing, and
    # one under doperpowers' answered under sminos's: a session resumed across
    # the move holds both.
    "renamed": [
        ask("r1", "toolu_ex_sminos", True, SMINOS_ASK), result("r2", "toolu_ex_sminos"),
        ask("r3", "toolu_ex_crossed", True), result("r4", "toolu_ex_crossed"),
        {"type": "user", "uuid": "r5", "origin": {"kind": "plugin", "name": "sminos"},
         "message": {"content": [{"type": "text", "text": SMINOS_PROMPT + delivery("toolu_ex_sminos") + PLUGIN_FRAMING}]}},
        {"type": "user", "uuid": "r6", "origin": {"kind": "plugin", "name": "sminos"},
         "message": {"content": [{"type": "text", "text": SMINOS_PROMPT + delivery("toolu_ex_crossed") + PLUGIN_FRAMING}]}},
    ],
    # A message sent through either message tool, with its result, the pair
    # one export as the mod posts it; and a refused call.
    "message": [message("m1", "toolu_ex_msg", "Approve the dialog at 07:15, please."), result("m2", "toolu_ex_msg", "sent")],
    "maws-message": [message("m3", "toolu_ex_maws_msg", "Built; deploying next.", MAWS_MESSAGE_TOOL), result("m4", "toolu_ex_maws_msg", "sent")],
    # A call followed by a span, under each name, as the mod posts them: the
    # pair once the result is in, then the span that waited behind it; and a
    # row holding a span, a call and a span, posted whole with the call's result.
    **{"call-then-span-" + tag: [message("o1-" + tag, "toolu_ex_first_" + tag, "A, sent first", name), result("o2-" + tag, "toolu_ex_first_" + tag, "sent")]
       for tag, name in (("plugin", MESSAGE_TOOL), ("maws", MAWS_MESSAGE_TOOL))},
    **{"span-after-" + tag: [text("o3-" + tag, "<message>B, written after the call</message>")]
       for tag in ("plugin", "maws")},
    **{"one-row-" + tag: [message("o4-" + tag, "toolu_ex_row_" + tag, "the call", name, "<message>ahead of the call</message>", "<message>after the call</message>"),
                          result("o5-" + tag, "toolu_ex_row_" + tag, "sent")]
       for tag, name in (("plugin", MESSAGE_TOOL), ("maws", MAWS_MESSAGE_TOOL))},
    # A row holding two calls and a span, posted once both results are in.
    **{"two-calls-" + tag: [
        {"type": "assistant", "uuid": "o6-" + tag, "message": {"content": [
            {"type": "tool_use", "id": "toolu_ex_x_" + tag, "name": name, "input": {"text": "X, the first call"}},
            {"type": "tool_use", "id": "toolu_ex_y_" + tag, "name": name, "input": {"text": "Y, the second call"}},
            {"type": "text", "text": "<message>after both calls</message>"}]}},
        result("o7-" + tag, "toolu_ex_y_" + tag, "sent"), result("o8-" + tag, "toolu_ex_x_" + tag, "sent")]
       for tag, name in (("plugin", MESSAGE_TOOL), ("maws", MAWS_MESSAGE_TOOL))},
    # A call whose result the bridge missed, as the mod posts it once it gives
    # the call up (its row, no result), and two later calls with theirs; the
    # transcript holds the missed result, which the Stop hook reads.
    "missed-row": [message("q1", "toolu_ex_missed", "its result never reached the bridge")],
    "missed-result": [result("q2", "toolu_ex_missed", "sent")],
    "after-missed": [message("q3", "toolu_ex_later1", "later, one"), result("q4", "toolu_ex_later1", "sent")],
    "after-missed-2": [message("q5", "toolu_ex_later2", "later, two", MAWS_MESSAGE_TOOL), result("q6", "toolu_ex_later2", "sent")],
    "refused-message": [message("m5", "toolu_ex_msg_refused", "from a subagent"),
                        result("m6", "toolu_ex_msg_refused", "message is for the main conversation", True)],
    # The human's mid-turn message quoting a steer, which the mod hands over whole.
    "quoted": [
        {"type": "attachment", "uuid": "a5", "attachment": {"type": "queued_command", "commandMode": "prompt", "prompt": QUOTED,
                                                            "origin": {"kind": "human"}}},
    ],
}
# The same answer rows as the transcript keeps them, where the Stop hook reads
# them: a prompt's content a string, an attachment's payload whole, beside its
# rendering.
KEPT = {
    "answers": [
        {"type": "user", "uuid": "a1", "origin": {"kind": "plugin", "name": "doperpowers"}, "promptSource": "system",
         "message": {"role": "user", "content": PLUGIN_PROMPT + delivery("toolu_ex_async") + PLUGIN_FRAMING}},
        {"type": "attachment", "uuid": "a2",
         "attachment": {"type": "hook_additional_context", "content": [delivery("toolu_ex_ctx")], "hookName": "tool.call", "hookEvent": "PostToolUse"},
         "rendered": [{"content": "<system-reminder>\ntool.call hook additional context: %s\n</system-reminder>" % delivery("toolu_ex_ctx")}]},
        {"type": "user", "uuid": "a3", "origin": {"kind": "human"}, "promptSource": "sdk", "message": {"role": "user", "content": steer("toolu_ex_maws")}},
        {"type": "attachment", "uuid": "a4", "attachment": {"type": "queued_command", "prompt": steer("toolu_ex_mid"), "source_uuid": "s-a4",
                                                            "commandMode": "prompt", "origin": {"kind": "human"}, "humanTurn": True}},
    ],
    "quoted": [
        {"type": "attachment", "uuid": "a5", "attachment": {"type": "queued_command", "prompt": QUOTED, "source_uuid": "s-a5",
                                                            "commandMode": "prompt", "origin": {"kind": "human"}, "humanTurn": True}},
    ],
    # An answer holding a system-reminder tag, which the engine's rendering
    # escapes: the mod does not export it, and the Stop hook reads the payload.
    "tagged": [
        {"type": "attachment", "uuid": "a6",
         "attachment": {"type": "hook_additional_context", "content": [TAGGED], "hookName": "tool.call", "hookEvent": "PostToolUse"},
         "rendered": [{"content": "<system-reminder>\ntool.call hook additional context: %s\n</system-reminder>"
                                  % TAGGED.replace("<system-reminder>", "&lt;system-reminder>")}]},
    ],
}
op = sys.argv[1]
def rows(name):
    return ROWS.get(name) or [text(name, "<message>%s, one row</message>" % name)]

if op == "export":          # name: the export event the mod posts for these rows
    print(json.dumps([{"type": "export", "records": rows(sys.argv[2]), "t": 1}]))
elif op == "exports":       # name: one export event per row, as the mod posts an answer row's
    print(json.dumps([{"type": "export", "records": [r], "t": 1} for r in rows(sys.argv[2])]))
elif op == "transcript":    # path name...: the rows as the transcript keeps them, appended
    with open(sys.argv[2], "a") as f:
        for name in sys.argv[3:]:
            for r in ([{"type": "user", "uuid": "p-" + name, "isSidechain": False, "message": {"role": "user", "content": "go"}}]
                      if name == "prompt" else KEPT.get(name) or rows(name)):
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
text_of() { # session kind src → that event's text, from the session's own writer file
  python3 -c 'import json, sys
for l in open(sys.argv[1]):
    e = json.loads(l)
    if e["kind"] == sys.argv[2] and e.get("src") == sys.argv[3]:
        print(e["text"])' "$LOG/testhost.$1.jsonl" "$2" "$3"
}

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

# An answer reaches the log as its row is kept, not at the turn's end. The
# quoting message goes first: once the last answer is in, it was read too.
ctl post "$SOCK" "$(rows exports quoted)" >/dev/null
ctl post "$SOCK" "$(rows exports answers)" >/dev/null
until_true 100 has "$SA" "answered:toolu_ex_mid" || true
LIVE="joined message:e1#0 message:e1#1 question:toolu_ex_async message:es#0 answered:toolu_ex_async answered:toolu_ex_ctx answered:toolu_ex_maws answered:toolu_ex_mid"
assert_equals "$(events_of "$SA")" "$LIVE" \
  "each exported answer row appends answered under its ask's id: the plugin's delivery as a prompt and as context, MAWS's steer as a prompt and taken mid-turn"
assert_not_contains "$(events_of "$SA")" "toolu_ex_quoted" \
  "a mid-turn message that quotes a steer, exported whole, answers nothing: it neither opens with the tag nor ends with the fence"
assert_equals "$(text_of "$SA" answered toolu_ex_async)" 'The user answered: "Which backend?"="Postgres".' \
  "a delivery's answered carries the engine's result text, without the plugin prompt's framing"
assert_equals "$(text_of "$SA" answered toolu_ex_mid)" "1. Proceed? — Yes" \
  "a steer's carries its answer lines, without MAWS's header or the result's fence"

# The Stop hook's export over the same rows: what the bridge already put in
# the log is there; only what it never saw (the tagged answer, row e9) is
# appended.
hook SessionStart "$SA" "$TA"
rows transcript "$TA" prompt marks ask answers quoted tagged e9
hook Stop "$SA" "$TA"
assert_equals "$(events_of "$SA")" "$LIVE answered:toolu_ex_tag message:e9#0" \
  "the Stop hook's export finds the bridge's events, answers included, already there and appends only what the bridge did not export"
assert_equals "$(text_of "$SA" answered toolu_ex_tag)" 'The user answered: "How?"="wrap it in <system-reminder> tags".' \
  "an answer holding a system-reminder tag, left by the bridge, lands at the Stop as the human wrote it, not as the engine's escaped rendering"
hook Stop "$SA" "$TA"
assert_equals "$(events_of "$SA")" "$LIVE answered:toolu_ex_tag message:e9#0" \
  "and a Stop replayed appends nothing"
# The same answer rows in a session no bridge exported: the Stop hook alone
# reads each as the bridge's export did, under the same src with the same text.
# toolu_ex_async is a question SA asked, so this session's answer to it is
# SA's, as a copy's answer to its original's question is, and SA's file
# already holds it.
SF=5b000001-0000-4000-8000-0000000000e8
TF="$HOME/.claude/projects/x/$SF.jsonl"
peer "$SF" exstop interactive cli
hook SessionStart "$SF" "$TF"
rows transcript "$TF" prompt answers quoted
hook Stop "$SF" "$TF"
assert_equals "$(events_of "$SF")" "joined answered:toolu_ex_ctx answered:toolu_ex_maws answered:toolu_ex_mid" \
  "without the bridge, the Stop hook reads the same answer rows as the same answered events, and the quoting message as none"
assert_equals "$(events_of "$SA")" "$LIVE answered:toolu_ex_tag message:e9#0" \
  "and its answer to the question another session asked goes to that session's writer, which holds it once"
same_texts=yes
for src in toolu_ex_ctx toolu_ex_maws toolu_ex_mid; do
  [[ "$(text_of "$SA" answered "$src")" == "$(text_of "$SF" answered "$src")" ]] || same_texts="no: $src"
done
assert_equals "$same_texts" yes "and with the texts the bridge's export logged"
"$SMINOS" chat exdemo --host > "$T/host" 2>&1 || true
assert_contains "$(cat "$T/host")" "exa: first to the host" "chat --host prints what the bridge exported"

echo "the ask under either plugin's name:"
SG=5b000001-0000-4000-8000-0000000000e9
peer "$SG" exboth interactive cli
start_child "$SG"
ctl post "$SMINOS_HOME/bridge/$SG.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SG\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SG.sock" "$(rows export renamed)" >/dev/null
until_true 100 has "$SG" "answered:toolu_ex_crossed" || true
assert_equals "$(events_of "$SG")" "joined question:toolu_ex_sminos question:toolu_ex_crossed answered:toolu_ex_sminos answered:toolu_ex_crossed" \
  "an ask under the sminos plugin's name, and one under doperpowers' answered under sminos's framing, each export a question and its answer"
assert_equals "$(text_of "$SG" answered toolu_ex_sminos)" 'The user answered: "Which backend?"="Postgres".' \
  "the answer under the sminos framing is the engine's result text, without the framing"

echo "the message tools:"
# A message tool's call and its result, which the mod hands over as one
# export: the child logs an accepted call as the message the Stop hook's
# export logs for it, under the same src, so the Stop appends nothing more.
SH=5b000001-0000-4000-8000-0000000000ea
TH="$HOME/.claude/projects/x/$SH.jsonl"
peer "$SH" exmsg interactive cli
start_child "$SH"
ctl post "$SMINOS_HOME/bridge/$SH.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SH\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
for pair in message maws-message refused-message; do
  ctl post "$SMINOS_HOME/bridge/$SH.sock" "$(rows export "$pair")" >/dev/null
done
ctl post "$SMINOS_HOME/bridge/$SH.sock" "$(rows export eh)" >/dev/null
until_true 100 has "$SH" "message:eh#0" || true
MSGS="joined message:toolu_ex_msg message:toolu_ex_maws_msg message:eh#0"
assert_equals "$(events_of "$SH")" "$MSGS" \
  "an accepted call of either message tool reaches the log as a message, src its call id; a refused call is none"
assert_contains "$(grep '"toolu_ex_msg"' "$LOG/testhost.$SH.jsonl")" '"kind": "message", "from": "exmsg", "to": "host", "text": "Approve the dialog at 07:15, please.", "src": "toolu_ex_msg"' \
  "the message carries from, to host, the call's text and src, as the Stop hook writes it"
hook SessionStart "$SH" "$TH"
rows transcript "$TH" prompt message maws-message refused-message eh
hook Stop "$SH" "$TH"
assert_equals "$(events_of "$SH")" "$MSGS" "the Stop hook's export over the same rows appends no second copy"
"$SMINOS" chat exdemo --host > "$T/host" 2>&1 || true
assert_contains "$(cat "$T/host")" "exmsg: Built; deploying next." "chat --host prints a message sent through MAWS's tool"
# Order: a call followed by a span, and a row holding a span, a call and a
# span, reach the log in the transcript's order, as the Stop hook reads it.
for tag in plugin maws; do
  case "$tag" in plugin) SO=5b000001-0000-4000-8000-0000000000fa ;; *) SO=5b000001-0000-4000-8000-0000000000fb ;; esac
  TO="$HOME/.claude/projects/x/$SO.jsonl"
  peer "$SO" "exorder$tag" interactive cli
  start_child "$SO"
  ctl post "$SMINOS_HOME/bridge/$SO.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SO\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
  for part in "call-then-span-$tag" "span-after-$tag" "one-row-$tag" "two-calls-$tag"; do
    ctl post "$SMINOS_HOME/bridge/$SO.sock" "$(rows export "$part")" >/dev/null
  done
  until_true 100 has "$SO" "message:o6-$tag#0" || true
  ORDER="joined message:toolu_ex_first_$tag message:o3-$tag#0 message:o4-$tag#0 message:toolu_ex_row_$tag message:o4-$tag#1"
  ORDER="$ORDER message:toolu_ex_x_$tag message:toolu_ex_y_$tag message:o6-$tag#0"
  assert_equals "$(events_of "$SO")" "$ORDER" \
    "$tag's message tool: a call, the span after it, a row's span, call and span, and a row's two calls and span reach the log in the transcript's order"
  hook SessionStart "$SO" "$TO"
  rows transcript "$TO" prompt "call-then-span-$tag" "span-after-$tag" "one-row-$tag" "two-calls-$tag"
  hook Stop "$SO" "$TO"
  assert_equals "$(events_of "$SO")" "$ORDER" "$tag's message tool: the Stop hook's export over the same rows reads the same order, and appends nothing"
done

# A call whose result the bridge missed: the mod gives it up at its bound and
# the calls after it flow; the Stop hook's export writes the missed call.
SL=5b000001-0000-4000-8000-0000000000fc
TL="$HOME/.claude/projects/x/$SL.jsonl"
peer "$SL" exmissed interactive cli
start_child "$SL"
ctl post "$SMINOS_HOME/bridge/$SL.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SL\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
for part in missed-row after-missed after-missed-2; do
  ctl post "$SMINOS_HOME/bridge/$SL.sock" "$(rows export "$part")" >/dev/null
done
until_true 100 has "$SL" "message:toolu_ex_later2" || true
assert_equals "$(events_of "$SL")" "joined message:toolu_ex_later1 message:toolu_ex_later2" \
  "a given-up call's row, sent without its result, logs nothing; the calls after it log in order"
hook SessionStart "$SL" "$TL"
rows transcript "$TL" prompt missed-row missed-result after-missed after-missed-2
hook Stop "$SL" "$TL"
assert_equals "$(events_of "$SL")" "joined message:toolu_ex_later1 message:toolu_ex_later2 message:toolu_ex_missed" \
  "the Stop hook's export writes the missed call once, its result on disk, and nothing else again"

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
SM=5b000001-0000-4000-8000-0000000000e7
peer "$SM" exmaws interactive sdk-ts
SMNS_MEMBER="$(ps -o ppid= -p $$ | tr -d ' ')" start_child "$SM"
ctl post "$SMINOS_HOME/bridge/$SM.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SM\",\"cwd\":\"$REPO\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SM.sock" "$(rows export marks)" >/dev/null
until_true 100 has "$SM" "message:e1#1" || true
assert_equals "$(events_of "$SM")" "joined message:e1#0 message:e1#1" \
  "an SDK run its host marked as a member (MAWS's SMNS_MEMBER, naming the engine's parent, which the bridge's child inherits) joins and exports as a terminal session does"

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

echo "a machine cut over to its endpoint (RL10): the host store:"
# daemon/identity.json is what the first RL10 welcome writes: from then on a
# hub project's host events stay on the machine, in its host store
# (projects/<id>/host/), and never reach its log, which the hub carries; a
# project with no hub keeps them in its log (O12 M8).
printf '{"org": "org-a", "hub": "https://hub.test", "name": "testhost", "former": {}, "ref": "machine-ref", "enrolled": "2026-10-01T00:00:00Z", "cutover": "2026-10-27T00:00:00Z", "build": "x"}\n' \
  > "$SMINOS_HOME/daemon/identity.json"
chmod 600 "$SMINOS_HOME/daemon/identity.json"
RC3="$T/cut"
mkdir -p "$RC3"
git -c init.defaultBranch=main init -q "$RC3"
(cd "$RC3" && "$SMINOS" project init --hub --name cut >/dev/null)
CUTP="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RC3/.smns")"
store_events() { # project-id file-stem → "kind[:src]" words of that writer's file in the host store
  python3 -c 'import json, sys
try:
    lines = open(sys.argv[1]).read().splitlines()
except OSError:
    lines = []
print(" ".join(json.loads(l)["kind"] + (":" + json.loads(l)["src"] if json.loads(l).get("src") else "") for l in lines))' \
    "$SMINOS_HOME/projects/$1/host/$2.jsonl"
}
hook_in() { # cwd event session transcript
  printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","hook_event_name":"%s","source":"startup"}' \
    "$3" "$1" "$4" "$2" | "$SMINOS" record
}
SK=5b000001-0000-4000-8000-0000000000f1
TK="$HOME/.claude/projects/x/$SK.jsonl"
peer "$SK" excut interactive cli "$RC3"
start_child "$SK"
ctl post "$SMINOS_HOME/bridge/$SK.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SK\",\"cwd\":\"$RC3\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SK.sock" "$(rows export marks)" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SK.sock" "$(rows export ask)" >/dev/null
store_has() { [[ " $(store_events "$CUTP" "testhost.$SK") " == *" question:toolu_ex_async "* ]]; }
until_true 100 store_has || true
CUT="message:e1#0 message:e1#1 question:toolu_ex_async"
assert_equals "$(store_events "$CUTP" "testhost.$SK")" "$CUT" \
  "the bridge's live export of a hub project's session goes to the host store, under the session's writer"
assert_equals "$(writer_events "$CUTP" "testhost.$SK")" "joined" "and nothing of it to the log, which holds its join alone"
hook_in "$RC3" SessionStart "$SK" "$TK"
rows transcript "$TK" prompt marks ask
hook_in "$RC3" Stop "$SK" "$TK"
assert_equals "$(store_events "$CUTP" "testhost.$SK")" "$CUT" \
  "the Stop hook's export of the same rows finds them in the store: one copy"
assert_equals "$(writer_events "$CUTP" "testhost.$SK")" "joined" "and appends nothing to the log"
# A session the bridge never saw answers the question SK asked: the answer
# goes under SK's writer, in the store.
SN=5b000001-0000-4000-8000-0000000000f2
TN="$HOME/.claude/projects/x/$SN.jsonl"
peer "$SN" excopy interactive cli "$RC3"
hook_in "$RC3" SessionStart "$SN" "$TN"
rows transcript "$TN" prompt answers
hook_in "$RC3" Stop "$SN" "$TN"
assert_equals "$(store_events "$CUTP" "testhost.$SK")" "$CUT answered:toolu_ex_async" \
  "an answer to a question another session asked goes under the asker's writer, in the store"
assert_equals "$(store_events "$CUTP" "testhost.$SN")" "answered:toolu_ex_ctx answered:toolu_ex_maws answered:toolu_ex_mid" \
  "the answering session's other answers in its own store file"
assert_equals "$(writer_events "$CUTP" "testhost.$SN")" "joined" "and nothing of them in the log"
"$SMINOS" chat cut --host > "$T/host" 2>&1 || true
assert_contains "$(cat "$T/host")" "excut: first to the host" "chat --host reads the store"
# A git-mirrored project on the same machine keeps them in its log.
RM="$T/mirrored"
mkdir -p "$RM"
git -c init.defaultBranch=main init -q "$RM"
(cd "$RM" && "$SMINOS" project init --remote "$T/mirror.git" --name mirrored >/dev/null)
MIRP="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RM/.smns")"
SR=5b000001-0000-4000-8000-0000000000f3
peer "$SR" exmirror interactive cli "$RM"
start_child "$SR"
ctl post "$SMINOS_HOME/bridge/$SR.sock" "[{\"type\":\"session\",\"phase\":\"start\",\"session\":\"$SR\",\"cwd\":\"$RM\",\"t\":1}]" >/dev/null
ctl post "$SMINOS_HOME/bridge/$SR.sock" "$(rows export marks)" >/dev/null
mirror_has() { [[ " $(writer_events "$MIRP" "testhost.$SR") " == *" message:e1#1 "* ]]; }
until_true 100 mirror_has || true
assert_equals "$(writer_events "$MIRP" "testhost.$SR")" "joined message:e1#0 message:e1#1" \
  "a git-mirrored project on a cut-over machine keeps its host events in its log, as today"
assert_equals "$(ls "$SMINOS_HOME/projects/$MIRP/host" 2>/dev/null | wc -l | tr -d ' ')" "0" "and has no host store"
rm -f "$SMINOS_HOME/daemon/identity.json"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES bridge export assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) bridge export assertions FAILED"
  exit 1
fi
