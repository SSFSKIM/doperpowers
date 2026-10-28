#!/usr/bin/env bash
#
# Enrollment and hub projects (DC4 M2 of the desk), against hub_standin.py's
# DX7 redemption. Pins DC4.G1: `sminos hub enroll` reads the code from stdin
# (or a hidden prompt; never argv, which it refuses unread), decodes it as
# the hub's decoder does (enroll_parity.py, over codes the hub's own encoders
# built: one-time codes and provisioning codes, whose name must start with the
# key's prefix), redeems it, and stores the credential at mode 0600 — the org key and
# the service token's secret never in any output or in daemon.log; every DX7
# error said with what to do; a second installation claiming an enrolled name
# is refused and told to pick another with --name; the enrolled name is the
# writer host, and a rename leaves this machine's seats and members its own
# while another machine enrolled under the old name stays another;
# `project init --hub` writes the org; a hub project, a malformed hub
# included, runs no git phase and `project attach` refuses it. `hub check`
# and `hub leave` read the hub's answer to the stored credential as accepted,
# rejected (the Worker's not-enrolled at once; Access's 401 page past the
# propagation grace and again on its recheck) or undecided, and only leave,
# on acceptance or rejection, removes hub.json.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per installation;
# `claude` is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="$PLUGIN_ROOT/skills/sminos/scripts"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smh.XXXXXX)"
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
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
assert_rc() { if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; fi; }
# Every output of the CLI is kept, to be searched for secrets at the end.
run() { set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e; printf '%s\n' "$OUT" >> "$T/all.out"; }
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
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }
json_get() { python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(json.dumps(eval(sys.argv[2], {"d": d})))' "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST MAWS_USER_DATA SMINOS_RL10
export SMINOS_DERIVE_EVERY=0
export DAEMON_BOOT_ID=boot-current
mkdir -p "$T/bin"
# One installation: its HOME, its SMINOS_HOME, its host name.
as() { # name host — the installation `name` is the one the verbs after it run as
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

# A stub `claude`: `agents` lists $STUB_STATE/agents.json; `stop` is recorded.
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
  stop) echo "$2" >> "$STUB_STATE/stops"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

# The hub stand-in: org-1, `testhost` already enrolled (cid-1 / secret-1).
python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-1 secret-1 2000 & PIDS+=("$!")
until_true 100 test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"

# The test's hands on the stand-in, and codes built as the browser builds them
# (encodeEnrollmentCode: JSON.stringify of {hub, org, token, machine, key}).
cat > "$T/ctl.py" <<'PY'
import base64, http.client, json, sys
port = int(open(sys.argv[1]).read())

def call(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body),
              headers={"Content-Type": "application/json", **(headers or {})})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")

cmd = sys.argv[2]
if cmd == "token":  # [ttl_s]
    print(call("POST", "/control/enrollment", {"ttl_s": int(sys.argv[3])} if len(sys.argv) > 3 else {})[1]["token"])
elif cmd == "code":  # hub token machine key
    body = json.dumps(dict(zip(("hub", "org", "token", "machine", "key"), [sys.argv[3], "org-1", *sys.argv[4:7]])),
                      separators=(",", ":"), ensure_ascii=False).encode()
    print("smns-enroll-v1." + base64.urlsafe_b64encode(body).rstrip(b"=").decode())
elif cmd == "fault":
    call("POST", "/control/fault", {"redeem": sys.argv[3:]})
elif cmd == "state":  # a python expression over the state, d
    print(json.dumps(eval(sys.argv[3], {"d": call("GET", "/control/state")[1]})))
elif cmd == "pkey":  # prefix [max_uses] — a provisioning key, as an admin makes it: "<secret> <id>"
    r = call("POST", "/control/provisioning-key",
             {"prefix": sys.argv[3], **({"max_uses": int(sys.argv[4])} if len(sys.argv) > 4 else {})})[1]
    print(r["token"], r["id"])
elif cmd == "pkeyset":  # id revoked|expired — the key revoked, or past its expiry
    call("POST", "/control/provisioning-key", {"id": sys.argv[3], sys.argv[4]: True})
elif cmd == "pcode":  # hub secret prefix key — a provisioning code, as the browser builds it
    body = json.dumps(dict(zip(("hub", "org", "token", "prefix", "key"), [sys.argv[3], "org-1", *sys.argv[4:7]])),
                      separators=(",", ":"), ensure_ascii=False).encode()
    print("smns-provision-v1." + base64.urlsafe_b64encode(body).rstrip(b"=").decode())
elif cmd == "revoke":  # machine [orphan] — an admin's revocation (orphan: the token's deletion still owed)
    call("POST", "/control/revoke", {"machine": sys.argv[3], "orphan": sys.argv[4:] == ["orphan"]})
elif cmd == "edge":  # machine n — Access answers its token 401 for n requests, then admits it
    call("POST", "/control/edge", {"machine": sys.argv[3], "requests": int(sys.argv[4])})
elif cmd == "answer":  # JSON list — the next /machine/enrollment requests answered these
    call("POST", "/control/answer", {"answers": json.loads(sys.argv[3])})
elif cmd == "cut":  # status content-type text n — the next n answered chunked, `text` padded to 65 536 bytes in
    # one chunk, and the connection closed before the last (zero) chunk: an answer cut short of its end
    body = sys.argv[5].ljust(65536)
    raw = ("HTTP/1.1 %s Cut\r\nContent-Type: %s\r\nTransfer-Encoding: chunked\r\n\r\n%x\r\n%s\r\n"
           % (sys.argv[3], sys.argv[4], len(body), body))
    call("POST", "/control/answer", {"answers": [{"raw": raw}] * int(sys.argv[6])})
elif cmd == "release":  # a held answer goes
    call("POST", "/control/release")
elif cmd == "outage":  # path — no listener until the file exists
    call("POST", "/control/outage", {"until": sys.argv[3]})
elif cmd == "connect":  # hub.json — open the stream with its credential, read the welcome, close
    cred = json.load(open(sys.argv[3]))
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/machine/stream", headers={"CF-Access-Client-Id": cred["client_id"],
                                                 "CF-Access-Client-Secret": cred["client_secret"]})
    r = c.getresponse()
    print(r.status, r.readline().decode().strip() if r.status == 200 else r.read().decode())
    c.close()
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }
code_for() { # machine [ttl_s] — a fresh token's code proposing `machine`
  local token; token="$(ctl token ${2:+"$2"})"
  ctl code "$HUB" "$token" "$1" "$KEY"
}
redemptions() { ctl state 'len(d["redemptions"])'; }
cred() { echo "$SMINOS_HOME/daemon/hub.json"; }
# Every code is fed on stdin, as a human pastes it; each is kept, to be
# searched for in every output and log at the end.
enroll() { # code [args...]
  local code="$1"; shift
  printf '%s\n' "$code" >> "$T/codes"
  run "$SMINOS" hub enroll "$@" <<<"$code"
  # Each secret stored is kept, to be searched for, though `leave` removes it.
  if [ "$RC" = 0 ]; then json_get "$(cred)" 'd["client_secret"]' | tr -d '"' >> "$T/secrets"; fi
}
mode_of() { python3 -c 'import os, stat, sys; print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode)))' "$1"; }

# ---- the code, as the hub decodes it
echo "the code:"
while IFS= read -r line; do
  case "$line" in "ok "*) pass "enroll parity: ${line#ok }" ;; *) fail "enroll parity: ${line#FAIL }" ;; esac
done < <(python3 "$SCRIPT_DIR/enroll_parity.py" "$SCRIPTS" "$SCRIPT_DIR/dx7-enroll-codes.json" 2>&1)

as a alpha
run "$SMINOS" hub show
assert_contains "$OUT" "not enrolled" "an installation that never enrolled says so"
assert_rc 1 "$RC" "and hub show exits 1: no credential is held"
CODE_P="$(code_for alpha)"
printf '%s\n' "$CODE_P" >> "$T/codes"
run "$SMINOS" hub enroll "$CODE_P"
assert_rc 2 "$RC" "a code given as an argument is refused"
assert_contains "$OUT" "never given on the command line" "saying the code belongs at the prompt"
assert_contains "$OUT" "Run sminos hub enroll with no code and paste it at the prompt" "and how to give it"
assert_not_contains "$OUT" "$CODE_P" "without echoing it"
run "$SMINOS" hub enroll --name alpha2 "$CODE_P" more words
assert_rc 2 "$RC" "with other words too"
assert_not_contains "$OUT" "$CODE_P" "still unechoed"
# However the words fall, no parse of them echoes one: stdout and stderr apart.
refused_unechoed() { # label words... (after `sminos hub`)
  local label="$1"; shift
  set +e; "$SMINOS" hub "$@" > "$T/hub.stdout" 2> "$T/hub.stderr" < /dev/null; RC=$?; set -e
  cat "$T/hub.stdout" "$T/hub.stderr" >> "$T/all.out"
  assert_rc 2 "$RC" "refused: $label"
  assert_not_contains "$(cat "$T/hub.stdout")" "$CODE_P" "the code not on stdout: $label"
  assert_not_contains "$(cat "$T/hub.stderr")" "$CODE_P" "nor on stderr: $label"
}
refused_unechoed "a word, then --name, then the code" enroll extra --name beta "$CODE_P"
refused_unechoed "an unknown option carrying the code" enroll --bogus "$CODE_P"
refused_unechoed "an unknown option=the code" enroll "--bogus=$CODE_P"
refused_unechoed "the code as --name" enroll --name "$CODE_P"
refused_unechoed "the code as --name=" enroll "--name=$CODE_P"
refused_unechoed "the code after --replace, --name with no value" enroll --replace "$CODE_P" --name
refused_unechoed "the code in place of the verb" "$CODE_P"
refused_unechoed "the code after show" show "$CODE_P"
refused_unechoed "the code before the verb's options" enroll "$CODE_P" --name=beta --replace
assert_equals "$(redemptions)" 0 "no request reaches the hub"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing is written"
assert_equals "$(cat "$SMINOS_HOME/daemon.log" 2>/dev/null | wc -l | tr -d " ")" 0 "nor logged"
enroll "smns-enroll-v2.e30"
assert_rc 2 "$RC" "a code of another version is refused as usage"
assert_contains "$OUT" "enrollment code: not smns-enroll-v1" "in the hub decoder's words"
enroll "$(ctl code "http://desk.example.com" tok alpha "$KEY")"
assert_rc 2 "$RC" "a code naming a hub over plain http off this machine is refused"
assert_contains "$OUT" "enrollment code: the hub is not https" "saying why"
enroll "$(code_for alpha)" --name hub
assert_rc 2 "$RC" "--name hub is refused (the log's own prefix)"
assert_contains "$OUT" "--name takes an admitted machine name" "saying why, without repeating the value"
assert_equals "$(redemptions)" 0 "nothing refused by the CLI reaches the hub"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "and nothing is stored"

# ---- enrollment under this machine's own name
echo "enrolling:"
enroll "$(code_for proposed-a)"
assert_rc 0 "$RC" "enrollment succeeds"
assert_contains "$OUT" "enrolled this machine as alpha" "under this machine's own name, not the one the code proposed"
assert_contains "$OUT" "code proposed proposed-a" "saying which name the code proposed"
assert_contains "$OUT" "--name proposed-a" "and how to claim it instead"
assert_not_contains "$OUT" "no longer as" "no rename: nothing is said of one"
assert_equals "$(mode_of "$(cred)")" "0o600" "the credential is stored at mode 0600"
assert_equals "$(json_get "$SMINOS_HOME/daemon/heads.json" '[d["name"], d["enrolled"]]')" \
  "$(json_get "$(cred)" '[d["machine"], d["enrolled"]]')" \
  "the enrolment is marked: its operator writer waits for the hub's head of it (#147)"
assert_equals "$(json_get "$(cred)" '[d[k] for k in ("hub", "org", "machine", "key", "former")]')" \
  "[\"$HUB\", \"org-1\", \"alpha\", \"$KEY\", {}]" "with the hub, the org, the name, the key, and no former name"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "alpha"][0]')" \
  "the service token is the one the hub minted for alpha"
run ctl connect "$(cred)"
assert_contains "$OUT" "200 event: welcome" "the stored credential opens the stream"
assert_equals "$(ctl state '[e["state"] for e in d["enrollments"] if e["machine"] == "alpha"][0]')" '"confirmed"' \
  "and that first connection confirms the enrollment"
assert_contains "$(cat "$SMINOS_HOME/daemon.log")" "hub: enrolled as alpha at $HUB (org org-1)" "daemon.log records the enrollment"
run "$SMINOS" hub show
assert_rc 0 "$RC" "hub show exits 0 once a credential is held"
assert_contains "$OUT" "machine  alpha" "hub show names the machine"
assert_contains "$OUT" "hub      $HUB (org org-1)" "and its hub"
BEFORE="$(redemptions)"
enroll "$(code_for other-a)"
assert_rc 1 "$RC" "an enrolled installation refuses a new code"
assert_contains "$OUT" "already enrolled at $HUB as alpha" "saying what it is enrolled as"
assert_contains "$OUT" "--replace" "and how to replace it"
assert_equals "$(redemptions)" "$BEFORE" "without redeeming the code"
assert_equals "$(json_get "$(cred)" 'd["machine"]')" '"alpha"' "the identity is unchanged"

# ---- a second installation under the same host name
echo "a second installation named alpha:"
as b alpha
CODE_B="$(code_for alpha)"
enroll "$CODE_B"
assert_rc 3 "$RC" "claiming a name another machine holds is refused, with name-taken's own exit code"
assert_contains "$OUT" "another machine of this org is enrolled as alpha" "saying the name is taken"
assert_contains "$OUT" "run sminos hub enroll --name <another name> and paste the same code at the prompt" \
  "and how to pick another with the same code"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing is stored"
# Under another host name for once: from alpha, ALPHA differs only in case
# and is refused here before the hub is asked (below).
DAEMON_HOST=b-host enroll "$CODE_B" --name ALPHA
assert_rc 3 "$RC" "the name is taken whatever its case"
assert_contains "$OUT" "another machine of this org is enrolled as ALPHA" "the hub says so"

# ---- this installation's state under alpha, before it is renamed
echo "state before the rename:"
PB="$T/b/proj"
mkdir -p "$PB"
gitq init -q "$PB"
cd "$PB"
"$SMINOS" project init --name bproj >/dev/null
S1=5b000001-0000-4000-8000-0000000000b1
S2=5b000002-0000-4000-8000-0000000000b2
: > "$T/inbox.received"
python3 "$SCRIPT_DIR/inbox_standin.py" "$T/in.sock" "$T/inbox.received" & INBOX=$!
PIDS+=("$INBOX")
until_true 100 test -S "$T/in.sock"
sleep 600 & SLEEPER=$!
PIDS+=("$SLEEPER")
printf '{"pid":%s,"sessionId":"%s","name":"s1","nameSource":"derived","kind":"bg","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX" "$S1" "$PB" "$T/in.sock" > "$HOME/.claude/sessions/s1.json"
printf '{"pid":%s,"sessionId":"%s","name":"term","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$SLEEPER" "$S2" "$PB" > "$HOME/.claude/sessions/term.json"
printf '[{"id": "b1short", "sessionId": "%s", "state": "idle"}]\n' "$S1" > "$STUB_STATE/agents.json"
"$SMINOS" seat add bproj s1 --session "$S1" >/dev/null
machines() { printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))'; }
run "$SMINOS" list --json
assert_equals "$(machines)" "[('s1', 'alpha', True), ('term', 'alpha', True)]" "the seat and the session run on alpha"
BLOG="$SMINOS_HOME/projects/$(json_get "$PB/.smns" 'd["project"]' | tr -d '"')/log"
alpha_writers() { local n=0 f; for f in "$BLOG"/alpha.*.jsonl; do [ -e "$f" ] && n=$((n + 1)); done; echo "$n"; }
assert_equals "$(alpha_writers)" 2 "each joined under an alpha/ writer"

# ---- enrolling under another name
echo "the rename:"
enroll "$CODE_B" --name beta
assert_rc 0 "$RC" "the same code, under another name, enrolls"
assert_contains "$OUT" "enrolled this machine as beta" "as beta"
assert_contains "$OUT" "no longer as alpha" "saying this machine is renamed"
assert_contains "$OUT" "already written under alpha stay on this machine" "that what it wrote as alpha stays here"
assert_contains "$OUT" "never reach the hub" "and never reaches the hub or another machine"
assert_contains "$OUT" "DAEMON_HOST" "and that DAEMON_HOST is no longer read"
assert_equals "$(json_get "$(cred)" '[d["machine"], d["former"]]')" "[\"beta\", {\"alpha\": [\"$S1\", \"$S2\"]}]" \
  "hub.json records beta, and alpha as a former name with the sessions this installation held under it"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "s1"' "the seat is listed"
assert_equals "$(machines)" "[('s1', 'beta', True), ('term', 'beta', True)]" "the seat and the session are this machine's, on beta"
run "$SMINOS" send s1 "after the rename"
assert_rc 0 "$RC" "send reaches the seat"
until_true 100 grep -q "after the rename" "$T/inbox.received" || true
assert_contains "$(cat "$T/inbox.received")" "after the rename" "through its inbox"
kill "$SLEEPER"
set +e; wait "$SLEEPER" 2>/dev/null; set -e
run "$SMINOS" list --all --json
assert_contains "$(cat "$BLOG"/beta."$S2".jsonl 2>/dev/null)" '"reason": "ended"' \
  "a session that joined as alpha and ended is retired as this machine's own"
# A's own alpha session, as the hub would bring it here: A holds alpha now.
SA=5a00000a-0000-4000-8000-0000000000aa
python3 - "$SCRIPTS" "$SA" "$PB" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
p = sminos.resolve_project(sys.argv[3])
sminos.log_append(p, "alpha/" + sys.argv[2], "joined", session=sys.argv[2], alias="a-term", name_source="derived",
                  machine="alpha", cwd="/elsewhere", worktree="", role="", seat="", by="")
PY
run "$SMINOS" list --all --json
assert_contains "$(machines)" "('a-term', 'alpha', False)" "a session of the machine now enrolled as alpha is that machine's, not this one's"
run "$SMINOS" list --all --json
assert_equals "$(test -e "$BLOG/beta.$SA.jsonl" && echo there || echo none)" none "and this machine never retires it"
echo "[]" > "$STUB_STATE/agents.json"
run "$SMINOS" retire s1
assert_rc 0 "$RC" "retire acts on the seat"
assert_equals "$(cat "$STUB_STATE/stops" 2>/dev/null)" "b1short" "stopping the session it recorded on alpha"
run "$SMINOS" say "said as beta"
assert_contains "$(cat "$BLOG/beta.human.jsonl")" "said as beta" "new events are written under beta"
assert_equals "$(alpha_writers)" 3 "and no new alpha/ writer appears (two of this machine's, one of the other alpha's)"

# ---- a name that differs only in case
# DX7 compares machine names without case, and a file system that ignores case
# would put Kappa.human.jsonl and kappa.human.jsonl in one file.
echo "a name that differs only in case:"
as k Kappa
PK="$T/k/proj"
mkdir -p "$PK"
gitq init -q "$PK"
cd "$PK"
"$SMINOS" project init --name kproj >/dev/null
"$SMINOS" say "said as Kappa" >/dev/null
KLOG="$SMINOS_HOME/projects/$(json_get "$PK/.smns" 'd["project"]' | tr -d '"')/log"
BEFORE="$(redemptions)"
enroll "$(code_for kappa)" --name kappa
assert_rc 2 "$RC" "a name that differs from this machine's own only in case is refused"
assert_contains "$OUT" "differs from Kappa, the name this machine writes under, only in case" "saying so"
assert_contains "$OUT" "--name Kappa" "and how to keep its name"
assert_equals "$(redemptions)" "$BEFORE" "before anything is redeemed"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing is stored"
"$SMINOS" say "said after the refusal" >/dev/null
assert_equals "$(python3 -c 'import glob, json, sys
print(sorted(json.loads(l)["writer"] for p in glob.glob(sys.argv[1] + "/*.jsonl") for l in open(p) if l.strip()))' "$KLOG")" \
  "['Kappa/human', 'Kappa/human']" "this machine still writes as Kappa"
as b alpha
enroll "$(code_for beta)" --name Alpha --replace
assert_rc 2 "$RC" "a name that differs from a former name only in case is refused"
assert_contains "$OUT" "differs from alpha, a name this machine wrote under before, only in case" "saying so"
assert_equals "$(redemptions)" "$BEFORE" "before anything is redeemed"
assert_equals "$(json_get "$(cred)" 'd["machine"]')" '"beta"' "the enrollment is unchanged"
cd "$T"

# ---- what the hub answers, said with what to do
echo "the hub's answers:"
as c gamma
ctl fault lose
enroll "$(code_for gamma)"
assert_rc 0 "$RC" "a lost answer is redeemed again, and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "gamma"][0]')" \
  "with the credential of the second redemption, the one the hub holds"
run ctl connect "$(cred)"
assert_contains "$OUT" "200 event: welcome" "which opens the stream"
as c2 gamma2
ctl fault truncate
enroll "$(code_for gamma2)"
assert_rc 0 "$RC" "a 200 cut short of its length is redeemed again, and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "gamma2"][0]')" \
  "with the rotated credential the hub holds"
as c3 gamma3
CODE_C3="$(code_for gamma3)"
ctl fault truncate truncate truncate
enroll "$CODE_C3"
assert_rc 1 "$RC" "answers cut short every time end the command"
assert_contains "$OUT" "short of its length" "saying how the answer came back"
assert_contains "$OUT" "run the same command again" "and to run it again"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing stored"
enroll "$CODE_C3"
assert_rc 0 "$RC" "run again, it enrolls"
as d delta
CODE_D="$(code_for delta)"
ctl fault lose lose lose
enroll "$CODE_D"
assert_rc 1 "$RC" "answers lost every time end the command"
assert_contains "$OUT" "run the same command again" "saying to run it again"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "nothing stored"
assert_equals "$(ctl state 'len(d["faults"])')" 0 "after three attempts"
enroll "$CODE_D"
assert_rc 0 "$RC" "the same command, run again, rotates the credential and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "delta"][0]')" \
  "storing the rotated one"
as e epsilon
CODE_E="$(code_for epsilon)"
ctl fault busy
enroll "$CODE_E"
assert_rc 1 "$RC" "busy ends the command"
assert_contains "$OUT" "in flight" "saying a redemption is in flight"
assert_contains "$OUT" "run the same command again" "and to run it again"
ctl fault mint-failed
enroll "$CODE_E"
assert_rc 1 "$RC" "mint-failed ends the command"
assert_contains "$OUT" "could not mint" "saying the mint failed"
assert_contains "$OUT" "run the same command again" "and to run it again"
enroll "$CODE_E"
assert_rc 0 "$RC" "the same command then enrolls"
as f zeta
enroll "$CODE_E" --name zeta
assert_rc 1 "$RC" "a token bound to another name is refused"
assert_contains "$OUT" "bound to the machine \"epsilon\"" "naming the name it is bound to"
assert_contains "$OUT" "new code" "and saying to ask for a new code"
as e epsilon
ctl connect "$(cred)" >/dev/null
as f zeta
enroll "$CODE_E" --name epsilon
assert_rc 1 "$RC" "a spent token is refused"
assert_contains "$OUT" "spent" "saying so"
as g eta
CODE_X="$(code_for eta 1)"
sleep 1.2
enroll "$CODE_X"
assert_rc 1 "$RC" "an expired token is refused"
assert_contains "$OUT" "expired" "saying so"
enroll "$(ctl code "$HUB" never-minted eta "$KEY")"
assert_rc 1 "$RC" "a token the hub never issued is refused"
assert_contains "$OUT" "does not know this code's token" "saying so"
ctl fault other-org
enroll "$(code_for eta)"
assert_rc 1 "$RC" "an answer for another org than the code's is refused"
assert_contains "$OUT" "nothing is stored" "and nothing is stored"
assert_equals "$(test -e "$(cred)" && echo there || echo none)" none "indeed"
as h 'not a name'
enroll "$(code_for theta)"
assert_rc 0 "$RC" "a host name the hub would not admit leaves the code's name"
assert_contains "$OUT" "enrolled this machine as theta" "which is claimed"

# ---- hub projects
echo "hub projects:"
as a alpha
gitq init -q --bare "$T/archive.git"
gitq init -q --bare "$T/archive-h.git"
PH="$T/a/hp"
mkdir -p "$PH"
gitq init -q "$PH"
cd "$PH"
run "$SMINOS" project init --hub --name hubproj --remote "$T/archive-h.git"
assert_rc 0 "$RC" "project init --hub makes a hub project"
assert_equals "$(json_get "$PH/.smns" 'd["hub"]')" '{"org": "org-1"}' ".smns names the org alone: the URL is each machine's enrollment's"
assert_contains "$OUT" "a hub project of org org-1 (through $HUB here)" "and says so"
run "$SMINOS" project show
assert_contains "$OUT" "hub      $HUB (org org-1)" "project show names the hub"
PG="$T/a/gp"
mkdir -p "$PG"
gitq init -q "$PG"
cd "$PG"
"$SMINOS" project init --name gitproj --remote "$T/archive.git" >/dev/null
"$SMINOS" say "before the hub" >/dev/null
run "$SMINOS" daemon tick
assert_contains "$OUT" "gitproj: synced" "a hub-less project syncs through its remote"
SMNS_BEFORE="$(json_get "$PG/.smns" '{k: v for k, v in d.items() if k != "hub"}')"
run "$SMINOS" project init --hub
assert_rc 0 "$RC" "--hub on an existing .smns adds the field"
assert_equals "$(json_get "$PG/.smns" '{k: v for k, v in d.items() if k != "hub"}')" "$SMNS_BEFORE" "keeping every other field"
assert_equals "$(json_get "$PG/.smns" 'd["hub"]')" '{"org": "org-1"}' "with the org"
assert_contains "$OUT" "no longer synced" "saying its remote is no longer the live path"
run "$SMINOS" project init --hub
assert_rc 0 "$RC" "--hub again changes nothing"
assert_contains "$OUT" "already a hub project" "and says so"
run "$SMINOS" project init --hub --name renamed
assert_rc 2 "$RC" "--hub on an existing .smns changes nothing else"
REMOTE_HEAD="$(git -C "$T/archive.git" rev-parse main)"
"$SMINOS" say "after the hub" >/dev/null
run "$SMINOS" daemon tick
assert_contains "$OUT" "gitproj: reconciled" "the hub project ticks"
assert_not_contains "$OUT" "gitproj: synced" "with no git phase"
assert_not_contains "$OUT" "hubproj: synced" "nor for the project made a hub project at init"
assert_equals "$(git -C "$T/archive.git" rev-parse main)" "$REMOTE_HEAD" "its remote is not pushed"
assert_equals "$(test -d "$SMINOS_HOME/projects/$(json_get "$PH/.smns" 'd["project"]' | tr -d '"')/log/.git" && echo git || echo none)" none \
  "a hub project's log is never made a git working tree, though its .smns names a remote"
run "$SMINOS" project attach
assert_rc 1 "$RC" "project attach refuses a hub project"
assert_contains "$OUT" "syncs through its hub" "saying why"
cd "$T"
mv "$PG" "$PG.moved"
"$SMINOS" say --in gitproj "while its checkout is gone" >/dev/null
run "$SMINOS" daemon tick
assert_not_contains "$OUT" "gitproj: synced" "a hub project whose checkout is gone still gets no git phase"
assert_equals "$(git -C "$T/archive.git" rev-parse main)" "$REMOTE_HEAD" "its remote still not pushed"
cd "$T"
gitq init -q --bare "$T/archive-n.git"
PN="$T/a/np"
mkdir -p "$PN"
gitq init -q "$PN"
cd "$PN"
"$SMINOS" project init --name nullhub --remote "$T/archive-n.git" >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = None; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PN/.smns"
"$SMINOS" say "under a null hub" >/dev/null 2>&1
run "$SMINOS" daemon tick
assert_not_contains "$OUT" "nullhub: synced" "a .smns whose hub is null gets no git phase"
assert_contains "$OUT" "its hub names no org" "with a warning"
assert_equals "$(git -C "$T/archive-n.git" rev-parse --verify -q main || echo none)" none "its remote is never pushed"
run "$SMINOS" project attach
assert_rc 1 "$RC" "project attach refuses it"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "--hub does not overwrite a malformed hub"
assert_contains "$OUT" "fix its .smns by hand" "saying to fix it by hand"
PO="$T/a/op"
mkdir -p "$PO"
gitq init -q "$PO"
cd "$PO"
"$SMINOS" project init --name orgonly >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = {"org": "org-1"}; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PO/.smns"
"$SMINOS" say "under an org-only hub" >/dev/null 2>&1
importable() { # project dir — whether the uplink would import an events frame for it, for org-1
  python3 - "$SCRIPTS" "$1" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import sminos_uplink
pid = json.load(open(os.path.join(sys.argv[2], ".smns")))["project"]
print("imports" if sminos_uplink.hub_project(pid, {"org": "org-1"}) else "refuses")
PY
}
assert_equals "$(importable "$PO" 2>/dev/null)" imports "the uplink imports into a project whose hub carries only its org"
assert_equals "$(importable "$PH" 2>/dev/null)" imports "and into one made by init --hub"
assert_equals "$(importable "$PN" 2>/dev/null)" refuses "and nothing into one whose hub names no org"
cd "$T"

# ---- the conversion against a tick that syncs the project through git
# A tick read each project when it began; `project init --hub` may land while
# it waits on the remote. The conversion takes the mirror's sync lock, and
# each git phase reads .smns again under that lock, so what is left of the
# tick neither integrates nor pushes, and no git event enters the hub log.
echo "a conversion during a tick's sync:"
cat > "$T/race.py" <<'PY'
import json, os, subprocess, sys, threading
scripts, root, mode = sys.argv[1:4]
sys.path.insert(0, scripts)
import sminos, sminos_daemon as daemon
project = sminos.resolve_project(root)  # as the tick read it: no hub yet
convert = [os.path.join(scripts, "sminos"), "project", "init", "--hub"]
report = {}
if mode == "held":
    # The tick's fetch waits until the conversion has started and had a second
    # to finish; the tick's delivery waits for the conversion to end, so its
    # push comes after the switch.
    entered, gate, proc = threading.Event(), threading.Event(), []
    real_fetch, real_deliver = daemon.fetch, daemon.deliver_owed
    def held_fetch(log):
        entered.set()
        gate.wait(60)
        real_fetch(log)
    def deliver_after(project_, view):
        proc[0].wait(60)
        return real_deliver(project_, view)
    daemon.fetch, daemon.deliver_owed = held_fetch, deliver_after
    out = {}
    t = threading.Thread(target=lambda: out.update(daemon.tick(project)))
    t.start()
    entered.wait(60)
    proc.append(subprocess.Popen(convert, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said during the held fetch"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    try:
        proc[0].wait(1.0)
    except subprocess.TimeoutExpired:
        pass
    report["converted during the fetch"] = proc[0].poll() is not None
    gate.set()
    t.join(120)
    report["tick"] = out
elif mode == "elsewhere":
    # The switch landed in another checkout of the project (sys.argv[4]),
    # which shares its log, between the tick's read of this one and its sync;
    # then a session in this checkout, whose .smns names no hub, wrote.
    import sminos_uplink
    subprocess.run(convert, cwd=sys.argv[4], stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said where no hub is named"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    sminos.forget_caches()
    report["uplink feeds it"] = project.id in sminos_uplink.hub_projects({"org": "org-1"})
    sminos.forget_caches()
    report["tick"] = daemon.tick(project)
elif mode == "registering":
    # This checkout, whose .smns names no hub, registers itself over the
    # registration the other checkout (sys.argv[4]) left, and is held just
    # before it writes; meanwhile the other checkout converts and registers.
    import time, sminos_uplink
    other = sys.argv[4]
    sminos.project_path(sminos.resolve_project(other), "log")
    sminos.forget_caches()
    held, release, real_write = threading.Event(), threading.Event(), sminos.write_json
    def held_write(path, data, mode=0o600):
        if path.endswith("project.json") and not held.is_set():
            held.set()
            release.wait(60)
        return real_write(path, data, mode)
    sminos.write_json = held_write
    t = threading.Thread(target=sminos.project_path, args=(project, "log"))
    t.start()
    held.wait(60)
    proc = subprocess.Popen(convert, cwd=other, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 60
    while time.time() < deadline and proc.poll() is None and not sminos.names_hub(other, project.id):
        time.sleep(0.05)
    try:
        proc.wait(2.0)  # as far as it gets while this registration is held
    except subprocess.TimeoutExpired:
        pass
    report["converted while held"] = proc.poll() is not None
    release.set()
    t.join(60)
    report["converted"] = proc.wait(60) == 0
    sminos.write_json = real_write
    sminos.forget_caches()
    report["registered from the hub checkout"] = \
        os.path.realpath(str(sminos.registration(project.id).get("root") or "")) == os.path.realpath(other)
    report["uplink feeds it"] = project.id in sminos_uplink.hub_projects({"org": "org-1"})
    try:
        daemon.ensure_mirrored(project)
        report["git barred"] = False
    except daemon.BecameHub:
        report["git barred"] = True
else:  # "stale": the switch landed between the tick's read and its sync of the project
    subprocess.run(convert, cwd=root, stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said after the switch"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    report["tick"] = daemon.tick(project)
print(json.dumps(report))
PY
other_pushes() { # bare-remote text — another machine's git event, pushed to the remote
  rm -rf "$T/other-clone"
  gitq clone -q "$1" "$T/other-clone" 2>/dev/null
  printf '{"ts": "2026-10-15T00:00:00.000Z", "writer": "other/human", "seq": 1, "kind": "say", "from": "human", "to": "*", "text": "%s"}\n' \
    "$2" > "$T/other-clone/other.human.jsonl"
  gitq -C "$T/other-clone" add other.human.jsonl
  gitq -C "$T/other-clone" commit -qm other
  gitq -C "$T/other-clone" push -q origin HEAD:main
}
mirrored_project() { # name → a checkout under $T/a/<name> of a git-mirrored project, synced once
  gitq init -q --bare "$T/$1.git"
  mkdir -p "$T/a/$1"
  gitq init -q "$T/a/$1"
  cd "$T/a/$1"
  "$SMINOS" project init --name "$1" --remote "$T/$1.git" >/dev/null
  "$SMINOS" say "before the switch" >/dev/null
  run "$SMINOS" daemon tick
  assert_contains "$OUT" "$1: synced" "$1 syncs through git before the switch"
  cd "$T"
}
log_of() { echo "$SMINOS_HOME/projects/$(json_get "$T/a/$1/.smns" 'd["project"]' | tr -d '"')/log"; }
as a alpha
mirrored_project heldproj
HELD_HEAD="$(git -C "$T/heldproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/heldproj" held
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["converted during the fetch"])')" \
  False "a conversion started while a tick fetches waits for that sync to end"
assert_equals "$(json_get "$T/a/heldproj/.smns" 'd["hub"]')" '{"org": "org-1"}' "then converts the project"
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["tick"]["pushed"])')" \
  False "the rest of the tick, after the switch, pushes nothing"
assert_equals "$(git -C "$T/heldproj.git" rev-parse main)" "$HELD_HEAD" "the remote is where it was"
assert_contains "$(cat "$(log_of heldproj)/alpha.human.jsonl")" "said during the held fetch" \
  "though the log holds what was said meanwhile"
mirrored_project staleproj
STALE_HEAD="$(git -C "$T/staleproj.git" rev-parse main)"
other_pushes "$T/staleproj.git" "a git event after the switch"
OTHER_HEAD="$(git -C "$T/staleproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/staleproj" stale
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; t = json.load(sys.stdin)["tick"]; print([t["integrated"], t["pushed"]])')" \
  "[False, False]" "a tick that read the project before the switch neither integrates nor pushes it after"
assert_equals "$(test -e "$(log_of staleproj)/other.human.jsonl" && echo there || echo none)" none \
  "no git event enters the hub project's log"
assert_equals "$(git -C "$T/staleproj.git" rev-parse main)" "$OTHER_HEAD" "nothing of this machine is pushed"
[[ "$OTHER_HEAD" != "$STALE_HEAD" ]] || fail "the other machine's push moved the remote"
# Two checkouts of one project share its log: the switch made in one bars git
# for a tick that read the other, whose .smns names no hub, and a session
# writing from that other checkout does not take the project back to git.
mirrored_project twoproj
TWO_B="$T/a/twoproj-b"
mkdir -p "$TWO_B"
gitq init -q "$TWO_B"
cp "$T/a/twoproj/.smns" "$TWO_B/.smns"
other_pushes "$T/twoproj.git" "a git event after the switch in the other checkout"
TWO_HEAD="$(git -C "$T/twoproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/twoproj" elsewhere "$TWO_B"
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys
out = sys.stdin.read()
try:
    r = json.loads(out.strip().splitlines()[-1])
    print([r["uplink feeds it"], r["tick"]["integrated"], r["tick"]["pushed"]])
except (ValueError, IndexError, KeyError):
    print(out)')" \
  "[True, False, False]" "a switch in another checkout: the uplink feeds the project, and a tick that read this one neither integrates nor pushes it"
assert_equals "$(test -e "$(log_of twoproj)/other.human.jsonl" && echo there || echo none)" none \
  "no git event enters the log both checkouts share"
assert_equals "$(git -C "$T/twoproj.git" rev-parse main)" "$TWO_HEAD" "nothing of this machine is pushed"
assert_equals "$(python3 -c 'import json, os, sys; print(os.path.realpath(json.load(open(sys.argv[1]))["root"]) == os.path.realpath(sys.argv[2]))' \
  "$(log_of twoproj)/../project.json" "$TWO_B")" True "the project stays registered from the checkout that names the hub"
# A checkout registering without a hub, held just before it writes, while
# another checkout of the project converts: the conversion registers after it.
# The other checkout is at an older head that named the project otherwise, so
# its registration is not this checkout's project as it is now, and this one
# writes over it (an identical one it would keep: project_path's kept_root).
mirrored_project regproj
REG_B="$T/a/regproj-b"
mkdir -p "$REG_B"
gitq init -q "$REG_B"
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["name"] = "regproj-then"; json.dump(d, open(sys.argv[2], "w"))' \
  "$T/a/regproj/.smns" "$REG_B/.smns"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/regproj" registering "$REG_B"
reg_report() { printf '%s' "$OUT" | python3 -c 'import json, sys
out = sys.stdin.read()
try:
    print(json.loads(out.strip().splitlines()[-1])[sys.argv[1]])
except (ValueError, IndexError, KeyError):
    print(out)' "$1"; }
assert_equals "$(reg_report "converted while held")" False \
  "a conversion in another checkout waits for a registration in flight"
assert_equals "$(reg_report converted)" True "then converts the project"
assert_equals "$(reg_report "registered from the hub checkout")" True \
  "the project ends registered from the checkout that names the hub"
assert_equals "$(reg_report "uplink feeds it")" True "the uplink feeds the project"
assert_equals "$(reg_report "git barred")" True "git no longer syncs it from the checkout that names no hub"
cd "$T"
as b2 beta2
P0="$T/b2/p"
mkdir -p "$P0"
gitq init -q "$P0"
cd "$P0"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "project init --hub on a machine not enrolled is refused"
assert_contains "$OUT" "sminos hub enroll" "saying to enroll first"
assert_equals "$(test -e "$P0/.smns" && echo there || echo none)" none "and writes no .smns"
cd "$T"

# ---- enrollment through a provisioning key
# A provisioning code (smns-provision-v1.{hub, org, token, prefix, key}) is
# piped as a VM's boot pipes it: the name is --name, else the host's, and one
# not under the key's prefix is refused before anything is sent.
echo "provisioning keys:"
pcode_for() { # prefix [max_uses] — a fresh key's code; the key's id in $T/key.id
  local out; out="$(ctl pkey "$@")"
  echo "${out#* }" > "$T/key.id"
  echo "${out%% *}" >> "$T/secrets"
  ctl pcode "$HUB" "${out%% *}" "$1" "$KEY"
}
machine_requests() { ctl state 'len(d["requests"])'; }
enrollment_requests() { ctl state '[r["at"] for r in d["requests"] if r["path"] == "/machine/enrollment"]'; }
nothing_stored() { test -e "$(cred)" && echo there || echo none; }
key_uses() { ctl state "[k[\"uses\"] for k in d[\"keys\"] if k[\"id\"] == \"${1:-$(cat "$T/key.id")}\"][0]"; }
CODE_K="$(pcode_for dc-)"
KEY_K="$(cat "$T/key.id")"
as p1 p1host
enroll "$CODE_K" --name dc-x
assert_rc 0 "$RC" "a provisioning code piped with --name dc-x enrolls"
assert_contains "$OUT" "enrolled this machine as dc-x at $HUB (org org-1)" "as dc-x"
assert_not_contains "$OUT" "code proposed" "a provisioning code proposes no name"
assert_equals "$(mode_of "$(cred)")" "0o600" "the credential is stored at mode 0600"
assert_equals "$(json_get "$(cred)" '[d[k] for k in ("hub", "org", "machine", "key")]')" \
  "[\"$HUB\", \"org-1\", \"dc-x\", \"$KEY\"]" "with the hub, the org, the name and the org key, as a one-time code leaves it"
assert_equals "$(key_uses)" 1 "one use of the key is counted"
as p2 dc-host2
enroll "$CODE_K"
assert_rc 0 "$RC" "without --name, a host name under the prefix is the name"
assert_contains "$OUT" "enrolled this machine as dc-host2" "as the host's name"
as p3 build-3
BEFORE="$(machine_requests)"
enroll "$CODE_K"
assert_rc 2 "$RC" "without --name, a host name not under the prefix is refused"
assert_contains "$OUT" "the name build-3 does not start with this key's prefix dc-: pass --name dc-" "saying which prefix, and how to name one"
enroll "$CODE_K" --name build-3
assert_rc 2 "$RC" "so is --name build-3"
assert_contains "$OUT" "does not start with this key's prefix dc-" "in the same words"
assert_equals "$(machine_requests)" "$BEFORE" "neither sends a request"
assert_equals "$(nothing_stored)" none "nor stores anything"
enroll "$CODE_K" --name DC-p3
assert_rc 0 "$RC" "the prefix is compared without case"
as p4 dc-p4
ctl fault lose
enroll "$CODE_K"
assert_rc 0 "$RC" "a lost answer through a key is redeemed again, and enrolls"
assert_equals "$(json_get "$(cred)" 'd["client_id"]')" "$(ctl state '[m["client_id"] for m in d["machines"] if m["name"] == "dc-p4"][0]')" \
  "with the rotated credential the hub holds"
assert_equals "$(key_uses)" 4 "the rotation counts no use"
# The hub's refusals of a key, each said with what to do.
as p5 dc-p5
REVOKED="$(pcode_for dc-)"
ctl pkeyset "$(cat "$T/key.id")" revoked
enroll "$REVOKED"
assert_rc 1 "$RC" "a revoked key is refused"
assert_contains "$OUT" "this key was revoked at the hub: ask an admin for a new key" "saying so"
EXPIRED="$(pcode_for dc-)"
ctl pkeyset "$(cat "$T/key.id")" expired
enroll "$EXPIRED"
assert_rc 1 "$RC" "an expired key is refused"
assert_contains "$OUT" "this key has expired: ask an admin for a new key" "saying so"
CAPPED="$(pcode_for dc- 1)"
enroll "$CAPPED"
assert_rc 0 "$RC" "a key with max_uses 1 enrolls one machine"
as p6 dc-p6
enroll "$CAPPED"
assert_rc 1 "$RC" "and refuses the next"
assert_contains "$OUT" "this key has enrolled all the machines it may: ask an admin for a new key or a higher cap" "saying so"
read -r K_SECRET _ <<<"$(ctl pkey dc-)"
echo "$K_SECRET" >> "$T/secrets"
enroll "$(ctl pcode "$HUB" "$K_SECRET" build- "$KEY")" --name build-7
assert_rc 1 "$RC" "a hand-built code whose prefix is not the key's is refused at the hub"
assert_contains "$OUT" "this key does not enroll the name build-7" "saying the key does not cover the name"
assert_contains "$OUT" "dc-" "naming the prefix the hub holds"
as p1 p1host
run "$SMINOS" hub check
assert_rc 0 "$RC" "dc-x's credential is accepted (and its machine confirmed)"
as p7 p7host
enroll "$CODE_K" --name dc-x
assert_rc 3 "$RC" "a name another machine holds exits 3, for the boot to pick another"
assert_contains "$OUT" "another machine of this org is enrolled as dc-x" "saying the name is taken"
assert_equals "$(nothing_stored)" none "and nothing is stored"

# ---- hub check and hub leave: the hub's answer to a stored credential
# Accepted, rejected (the Worker's not-enrolled at once; Access's marked 401
# past the 600 s grace and held on a recheck), or anything else: undecided.
echo "hub check and hub leave:"
export SMINOS_ACCESS_RECHECK_S=1
fresh() { # name — a new installation enrolled through the key under its host name
  as "$1" "$1"
  enroll "$CODE_K"
  [ "$RC" = 0 ] || fail "enrolling $1 through the key"
}
past_grace() { # the credential's `enrolled` 700 s back, as a credential enrolled before the grace
  python3 - "$(cred)" <<'PY'
import datetime, json, os, sys
d = json.load(open(sys.argv[1]))
d["enrolled"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=700)).strftime("%Y-%m-%dT%H:%M:%SZ")
open(sys.argv[1], "w").write(json.dumps(d))
os.chmod(sys.argv[1], 0o600)
PY
}
digest() { python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$(cred)"; }
asked() { # since — how many /machine/enrollment requests came after the `since`-th one
  ctl state "len([r for r in d[\"requests\"] if r[\"path\"] == \"/machine/enrollment\"]) - $1"
}
asked_now() { ctl state 'len([r for r in d["requests"] if r["path"] == "/machine/enrollment"])'; }
check_is() { # rc words label — hub check's exit and words, its credential file byte-identical, then
  local sum; sum="$(digest)"
  run "$SMINOS" hub check
  assert_rc "$1" "$RC" "check: $3"
  assert_contains "$OUT" "$2" "check: $3, saying so"
  assert_equals "$(digest)" "$sum" "check: $3, the credential untouched"
}

fresh dc-c1
N="$(asked_now)"
check_is 0 "enrolled as dc-c1 at $HUB (org org-1): accepted" "a 200 naming the stored org and machine"
assert_equals "$(asked "$N")" 1 "one request"
assert_equals "$(ctl state '[m["state"] for m in d["machines"] if m["name"] == "dc-c1"][0]')" '"active"' "which confirmed the machine"
ctl revoke dc-c1 orphan
check_is 3 "sminos: the hub no longer accepts this machine's credential: the hub answered not-enrolled" \
  "the Worker's 403 not-enrolled is a rejection at once, inside the grace"
fresh dc-c2
ctl revoke dc-c2
past_grace
N="$(asked_now)"
check_is 3 "sminos: the hub no longer accepts this machine's credential: Access answered 401" \
  "Access's 401 past the grace, held on its recheck"
assert_equals "$(asked "$N")" 2 "two requests: the first and its recheck"
assert_equals "$(ctl state '(lambda a: a[-1] - a[-2] >= 1)([r["at"] for r in d["requests"] if r["path"] == "/machine/enrollment"])')" \
  true "the recheck sent SMINOS_ACCESS_RECHECK_S after the first"
fresh dc-c3
past_grace
ctl answer '[{"access": true}]'
N="$(asked_now)"
check_is 0 "accepted" "Access's 401 past the grace whose recheck is admitted"
assert_equals "$(asked "$N")" 2 "after its recheck"
fresh dc-c4
ctl revoke dc-c4
N="$(asked_now)"
check_is 4 "sminos: Access answered 401 to a credential enrolled" "Access's 401 inside the grace decides nothing"
assert_contains "$OUT" "s ago, which may not have reached Access's edge yet" "saying it may still be propagating"
assert_equals "$(asked "$N")" 1 "one request, no recheck"
fresh dc-c5
ctl answer '[{"status": 503, "body": "{\"error\": \"unavailable\"}"}]'
check_is 4 "sminos: the hub answered 503" "a 5xx is undecided"
ctl answer '[{"status": 401, "body": "{\"error\": \"unauthorized\"}"}]'
check_is 4 "401 without Access's page" "a 401 without Access's mark is undecided"
ctl answer '[{"status": 403, "body": "{\"error\": \"not-admin\"}"}]'
check_is 4 "sminos: the hub answered 403" "a 403 of another error is undecided"
ctl answer '[{"status": 200, "body": "{\"org\": \"org-1\", \"machine\": \"other\", \"state\": \"active\", \"confirmed\": null}"}]'
check_is 4 "sminos: the hub answered" "a 200 naming another machine is undecided"
past_grace
ctl answer '[{"status": 302, "body": "", "type": "text/html"}]'
check_is 4 "sminos: the hub answered 302" "a redirect is undecided, past the grace too"
cp "$(cred)" "$T/dc-c5.json"
python3 -c 'import json, socket, sys
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
d = json.load(open(sys.argv[1])); d["hub"] = "http://127.0.0.1:%d" % port; open(sys.argv[1], "w").write(json.dumps(d))' "$(cred)"
check_is 4 "sminos: the hub did not answer" "a hub that does not answer is undecided"
SUM_DEAD="$(digest)"
run "$SMINOS" hub leave
assert_rc 1 "$RC" "leave: a hub that does not answer keeps the credential, exit 1"
assert_equals "$(digest)" "$SUM_DEAD" "leave: the credential untouched"
cp -p "$T/dc-c5.json" "$(cred)"
ctl answer '[{"status": 502, "body": "{\"error\": \"bad-gateway\"}"}]'
run "$SMINOS" hub leave
assert_rc 1 "$RC" "leave: a 5xx keeps the credential, exit 1"
assert_contains "$OUT" "the hub answered 502" "saying what came"
assert_equals "$(nothing_stored)" there "the credential kept"
as nobody nobody
run "$SMINOS" hub check
assert_rc 1 "$RC" "check with no hub.json exits 1"
assert_contains "$OUT" "this machine is not enrolled at a hub" "saying so"
run "$SMINOS" hub leave
assert_rc 0 "$RC" "leave with no hub.json exits 0"
assert_contains "$OUT" "this machine is not enrolled at a hub: nothing to leave" "saying so"
run "$SMINOS" hub check extra
assert_rc 2 "$RC" "check takes no words"

fresh dc-l1
run "$SMINOS" hub leave
assert_rc 0 "$RC" "leave: a 200 leaves"
assert_contains "$OUT" "left the hub as dc-l1" "saying so"
assert_equals "$(nothing_stored)" none "hub.json is removed"
assert_equals "$(ctl state '[m["name"] for m in d["machines"] if m["name"] == "dc-l1"]')" "[]" "the hub no longer holds the machine"
run "$SMINOS" hub show
assert_rc 1 "$RC" "hub show then exits 1"
run "$SMINOS" hub leave
assert_rc 0 "$RC" "a second leave exits 0"
assert_contains "$OUT" "not enrolled" "saying there is nothing to leave"
fresh dc-l2
ctl revoke dc-l2
past_grace
run "$SMINOS" hub leave
assert_rc 0 "$RC" "leave: Access's 401 past the grace, held on its recheck"
assert_contains "$OUT" "the hub had already revoked dc-l2; the stale credential is removed" "says the hub had already revoked it"
assert_equals "$(nothing_stored)" none "and removes hub.json"
fresh dc-l3
ctl revoke dc-l3 orphan
run "$SMINOS" hub leave
assert_rc 0 "$RC" "leave: the Worker's not-enrolled"
assert_contains "$OUT" "had already revoked dc-l3" "says the hub had already revoked it"
assert_equals "$(nothing_stored)" none "and removes hub.json"
fresh dc-l4
ctl revoke dc-l4
SUM="$(digest)"
run "$SMINOS" hub leave
assert_rc 1 "$RC" "leave: Access's 401 inside the grace keeps the credential"
assert_contains "$OUT" "which may not have reached Access's edge yet" "saying why"
assert_equals "$(digest)" "$SUM" "the credential untouched"

# A token not yet at Access's edge: Access answers it 401 at first, then admits it.
fresh dc-e1
ctl edge dc-e1 2
SUM="$(digest)"
run "$SMINOS" hub check
assert_rc 4 "$RC" "a fresh token Access does not admit yet: check is undecided"
run "$SMINOS" hub leave
assert_rc 1 "$RC" "and leave keeps it"
assert_equals "$(digest)" "$SUM" "the credential untouched"
run "$SMINOS" hub check
assert_rc 0 "$RC" "once at the edge, check accepts it"
run "$SMINOS" hub leave
assert_rc 0 "$RC" "and leave leaves"
assert_contains "$OUT" "left the hub as dc-e1" "saying so"

# The boot's rule through an outage: revoked while down, the hub unreachable
# at the check, then back — all in one home, no reboot.
fresh dc-o1
OLD_CID="$(json_get "$(cred)" 'd["client_id"]')"
ctl revoke dc-o1
past_grace
ctl outage "$T/hub.up"
SUM="$(digest)"
run "$SMINOS" hub check
assert_rc 4 "$RC" "the hub unreachable: check is undecided"
assert_contains "$OUT" "sminos: the hub did not answer" "saying so"
assert_equals "$(digest)" "$SUM" "the credential kept"
run "$SMINOS" hub show
assert_rc 0 "$RC" "and show still exits 0"
touch "$T/hub.up"
until_true 100 ctl state 1 >/dev/null 2>&1
check_is 3 "Access answered 401" "the hub back on the same port and state, the revocation is learned"
USES="$(key_uses "$KEY_K")"
enroll "$CODE_K" --name dc-o1 --replace
assert_rc 0 "$RC" "enroll --replace with the same piped code enrolls anew under the same name"
assert_equals "$(key_uses "$KEY_K")" "$((USES + 1))" "a new enrollment: one more use of the key"
assert_not_contains "$(json_get "$(cred)" 'd["client_id"]')" "$OLD_CID" "with a new credential"
check_is 0 "accepted" "whose check is accepted"

# A leave whose answer is slow, and an enrollment that replaces hub.json
# meanwhile (the revocation freed the name): the replacement is another, live
# credential, which the leave neither removes nor revokes.
fresh dc-r1
ctl answer '[{"hold": true}]'
"$SMINOS" hub leave > "$T/leave.out" 2>&1 & LEAVE=$!
PIDS+=("$LEAVE")
revoked_r1() { [ "$(ctl state '[m["name"] for m in d["machines"] if m["name"] == "dc-r1"]')" = "[]" ]; }
until_true 100 revoked_r1
enroll "$CODE_K" --name dc-r1 --replace
assert_rc 0 "$RC" "while leave waits for its answer, enroll --replace enrolls dc-r1 anew"
SUM="$(digest)"
ctl release
set +e; wait "$LEAVE"; RC=$?; set -e
OUT="$(cat "$T/leave.out")"
printf '%s\n' "$OUT" >> "$T/all.out"
assert_rc 1 "$RC" "the leave, answered at last, exits 1"
assert_contains "$OUT" "left the hub as dc-r1, but another enrollment replaced this machine's credential while leave ran" \
  "saying its own enrollment ended and another replaced it"
assert_contains "$OUT" "run sminos hub leave again to end that one" "and how to end that one"
assert_equals "$(digest)" "$SUM" "the replacement's hub.json survives byte-identical"
check_is 0 "accepted" "and the hub still accepts it"

# An answer cut short of its end decides nothing, whatever its first bytes
# say: a chunked 403 not-enrolled whose last chunk never came, and Access's
# 401 page cut the same way, past the grace (the first and its recheck).
fresh dc-t1
leave_keeps() { # label — leave exits 1 and leaves the credential byte-identical
  local sum; sum="$(digest)"
  run "$SMINOS" hub leave
  assert_rc 1 "$RC" "leave: $1"
  assert_contains "$OUT" "cut short" "leave: $1, saying the answer was cut short"
  assert_equals "$(digest)" "$sum" "leave: $1, the credential untouched"
}
ctl cut 403 application/json '{"error":"not-enrolled","message":"cut"}' 2
check_is 4 "was cut short of its end" "a chunked 403 not-enrolled cut short of its end is undecided"
ctl cut 403 application/json '{"error":"not-enrolled","message":"cut"}' 2
leave_keeps "a chunked 403 not-enrolled cut short of its end"
past_grace
ctl cut 401 text/html '<html><title>Cloudflare Access</title></html>' 2
check_is 4 "was cut short of its end" "Access's 401 page cut short, past the grace, is undecided"
ctl cut 401 text/html '<html><title>Cloudflare Access</title></html>' 2
leave_keeps "Access's 401 page cut short, past the grace"
ctl answer '[]'
check_is 0 "accepted" "the credential, kept, is still accepted"
cd "$T"

# ---- a machine cut over to its endpoint (O12 M5)
# Enrolled at the hub as omega, the machine is cut over by its endpoint's
# welcome (endpoint_standin.py, as `daemon run`'s probe meets it), which names
# it sigma: identity.json holds the identity, omega's sessions stay this
# machine's, and the enrollment is the endpoint's — hub show prints it,
# enroll, check and leave exit 1 without a word to the hub, and hub.json
# stays, its key the endpoint's to ask for.
echo "a machine cut over to its endpoint:"
as cut omega
enroll "$(code_for omega)"
assert_rc 0 "$RC" "enrolled at the hub as omega"
PC="$T/cut/proj"
mkdir -p "$PC"
gitq init -q "$PC"
cd "$PC"
"$SMINOS" project init --name cproj >/dev/null
S5=5c000005-0000-4000-8000-0000000000c5
printf '{"pid":%s,"sessionId":"%s","name":"cterm","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$$" "$S5" "$PC" > "$HOME/.claude/sessions/cterm.json"
run "$SMINOS" list --json
assert_equals "$(machines)" "[('cterm', 'omega', True)]" "a session joins as omega"
export MAWS_USER_DATA="$T/cut/maws"
EPC="$MAWS_USER_DATA/mawsd/endpoint"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPC" "{\"identity\": {\"org\": \"org-1\", \"hub\": \"$HUB\", \"name\": \"sigma\", \"former\": [\"omega\"], \"ref\": \"ref-sigma\", \"enrolled\": \"2026-10-27T00:00:00.000Z\"}}" &
PIDS+=("$!")
until_true 100 test -S "$EPC/ctl.sock"
REQUESTS="$(ctl state 'len(d["requests"])')"
CRED_BEFORE="$(cat "$(cred)")"
run "$SMINOS" daemon probe
assert_rc 0 "$RC" "the endpoint's whole welcome cuts the machine over"
IDENT="$SMINOS_HOME/daemon/identity.json"
assert_equals "$(mode_of "$IDENT")" 0o600 "identity.json is mode 600"
assert_equals "$(json_get "$IDENT" '[d["name"], d["org"], d["ref"], d["former"]]')" "[\"sigma\", \"org-1\", \"ref-sigma\", {\"omega\": [\"$S5\"]}]" \
  "it holds the endpoint's name, and omega with the session held under it"
run "$SMINOS" list --json
assert_equals "$(machines)" "[('cterm', 'sigma', True)]" "the session is this machine's, on sigma"
run "$SMINOS" hub show
assert_rc 0 "$RC" "hub show reads the identity"
assert_contains "$OUT" "machine  sigma" "printing the endpoint's name"
assert_contains "$OUT" "former   omega (1 sessions)" "the former name"
assert_contains "$OUT" "cut over " "marked cut over"
assert_contains "$OUT" "$IDENT holds it, and removing it undoes the cutover" "naming the file that undoes it"
enroll "$(code_for sigma)" --replace
assert_rc 1 "$RC" "hub enroll exits 1 on a cut-over machine"
assert_contains "$OUT" "this machine's enrollment is its endpoint's: \`mawsd endpoint" "saying the enrollment is the endpoint's"
run "$SMINOS" hub check
assert_rc 1 "$RC" "hub check exits 1"
assert_contains "$OUT" "this machine's enrollment is its endpoint's" "saying so"
run "$SMINOS" hub leave
assert_rc 1 "$RC" "hub leave exits 1"
assert_contains "$OUT" "this machine's enrollment is its endpoint's" "saying so"
assert_equals "$(cat "$(cred)")" "$CRED_BEFORE" "hub.json stays as it was"
assert_equals "$(ctl state 'len(d["requests"])')" "$REQUESTS" "and not one of them asked the hub anything"
run "$SMINOS" say "said as sigma"
assert_contains "$(cat "$SMINOS_HOME/projects/$(json_get "$PC/.smns" 'd["project"]' | tr -d '"')/log/sigma.human.jsonl")" \
  "said as sigma" "new events are written under sigma"
PC2="$T/cut/proj2"
mkdir -p "$PC2"
gitq init -q "$PC2"
cd "$PC2"
run "$SMINOS" project init --hub --name cproj2
assert_rc 0 "$RC" "project init --hub takes the hub from the identity"
assert_equals "$(json_get "$PC2/.smns" 'd["hub"]')" '{"org": "org-1"}' "the org"
unset MAWS_USER_DATA
cd "$T"

# ---- no secret anywhere
echo "secrets:"
SECRETS="$(python3 - "$T" <<'PY'
import glob, json, os, sys
for p in glob.glob(sys.argv[1] + "/*/s/daemon/hub.json"):
    print(json.load(open(p))["client_secret"])
if os.path.exists(sys.argv[1] + "/secrets"):
    print(open(sys.argv[1] + "/secrets").read())
PY
)"
for f in "$T"/*/s/daemon.log "$T/all.out"; do
  [ -f "$f" ] || continue
  assert_not_contains "$(cat "$f")" "$KEY" "the org key is not in ${f#"$T"/}"
  while IFS= read -r c; do
    if grep -Fq -- "$c" "$f"; then fail "an enrollment code is in ${f#"$T"/}"; echo "    ${c:0:40}…"; fi
  done < "$T/codes"
  for s in $SECRETS; do
    assert_not_contains "$(cat "$f")" "$s" "no service token secret is in ${f#"$T"/}"
  done
done

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES hub assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) hub assertions FAILED"
  exit 1
fi
