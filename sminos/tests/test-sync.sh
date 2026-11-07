#!/usr/bin/env bash
#
# Sync of hub projects (DC4 M3 of the desk), on machines cut over to their
# endpoints (endpoint_standin.py), never enrolled at a hub and holding no
# hub.json. First gamma, whose git-mirrored project's forged operator line
# is delivered unverified and never asked about, while words said here go on
# the endpoint's verdict. Then one machine, renamed by its endpoint's
# welcome, proves the one-machine cases: a live member that joined under a
# former name joined again under the new one (also on a connection already
# open, with the daemon saying once that its session still writes under the
# former name), the seat, send and retirement after the rename; projects
# leaving the hub; an arrival whose shape is refused never entering the log
# and reported up as `rejected`, the positions the endpoint spent, and
# delivery past them; hello and the machine's presence before any upload on
# every connection, and the daemon never running git for a hub project; a
# refusal the resend after it does not undo. Last, two machines, each cut
# over to its own endpoint_standin.py, prove the two-machine sync, what one
# endpoint took reaching the other as arrivals (rl10-machines.sh's hand-off):
# a fresh machine's bootstrap, members and states, a burst on both with
# messages across, titles, a daemon restart and a dropped connection.
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
T="$(mktemp -d /tmp/sms.XXXXXX)"
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
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
# One machine: its HOME, its SMINOS_HOME, its host name; the verbs after it run there.
as() { # a|b host
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
# ssh, as git calls it for the projects' remote: a hub project must never reach it.
cat > "$T/bin/fake-ssh" <<SSH
#!/bin/sh
: > "$T/ssh-entered"
exit 1
SSH
chmod +x "$T/bin/fake-ssh"
export PATH="$T/bin:$PATH" GIT_SSH_COMMAND="$T/bin/fake-ssh" GIT_SSH_VARIANT=simple

# A live session's inbox (inbox_standin.py): appends each frame it receives
# and answers nothing, as the engine's does.
inbox() { # name → INBOX_PID; the socket $T/<name>.sock, the frames in $T/<name>.received
  : > "$T/$1.received"
  python3 "$SCRIPT_DIR/inbox_standin.py" "$T/$1.sock" "$T/$1.received" & INBOX_PID=$!
  PIDS+=("$INBOX_PID")
  until_true 100 test -S "$T/$1.sock"
}

MEMBER=4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c

says() { # count label — `say` as the operator, from the working directory
  local i
  for i in $(seq 1 "$1"); do "$SMINOS" say "$2 $i" >/dev/null; done
}
start_daemon() { # → DAEMON_PID (of the machine `as` named last)
  "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & DAEMON_PID=$!
  PIDS+=("$DAEMON_PID")
}
membership() { # log-file → its session's latest joined/retired (with the reason) and the titles the file holds
  python3 -c 'import json, sys
evs = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
m = [e for e in evs if e["kind"] in ("joined", "retired")][-1]
print(m["kind"] + (":" + m["reason"] if m.get("reason") else ""), [e["title"] for e in evs if e["kind"] == "titled"])' "$1" 2>/dev/null || true
}
membership_is() { [ "$(membership "$1")" = "$2" ]; }

# ---- a git mirror on a machine cut over to its endpoint (O12 M6)
# The writer name is not provenance. A `<thisname>/human` line forged into a
# project's git mirror and merged in by `daemon run`'s tick (integrate) has
# no append receipt: it is never asked about (`words?`), and that tick
# delivers it as an unverified peer message, said in daemon.log and in chat;
# words said here (`sminos say`, which writes the receipt) are asked and
# delivered on the endpoint's verdict by the uplink. Nothing of the
# git-mirrored project is opened on the endpoint's socket. A third machine,
# gamma, cut over to endpoint_standin.py, with no hub.
echo "a forged operator event through a git mirror, on a cut-over machine:"
as c gamma
export MAWS_USER_DATA="$T/c/maws"
EPDIR="$MAWS_USER_DATA/mawsd/endpoint"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPDIR" '{"identity": {"org": "org-1", "hub": "http://127.0.0.1:9", "name": "gamma", "former": [], "ref": "ref-gamma", "enrolled": "2026-10-27T00:00:00.000Z"}, "verdict": "words", "ask_legacy": false}' &
PIDS+=("$!")
until_true 100 test -S "$EPDIR/ctl.sock"
epq() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPDIR" state | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1], {"d": d})))' "$1"; }
MIRROR="$T/c/mirror.git"
gitq init -q --bare "$MIRROR"
RG="$T/c/repo"
mkdir -p "$RG"
gitq init -q "$RG"
(cd "$RG" && "$SMINOS" project init --name mirrored --remote "$MIRROR" >/dev/null)
gitq -C "$RG" add .smns
gitq -C "$RG" commit -qm smns
MPID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$RG/.smns")"
MC=5c000001-0000-4000-8000-0000000000c1
inbox mc
printf '{"pid":%s,"sessionId":"%s","name":"mc","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX_PID" "$MC" "$RG" "$T/mc.sock" > "$HOME/.claude/sessions/mc.json"
run "$SMINOS" daemon tick
assert_contains "$OUT" "mirrored: synced" "gamma's first tick attaches the mirror"
python3 - "$SMINOS_HOME/daemon/identity.json" <<'PY_ID'
import json, os, sys
with open(sys.argv[1], "w") as f:
    json.dump({"org": "org-1", "hub": "http://127.0.0.1:9", "name": "gamma", "former": {}, "ref": "ref-gamma",
               "enrolled": "2026-10-27T00:00:00.000Z", "cutover": "2026-10-27T00:00:01.000Z", "build": "b"}, f)
os.chmod(sys.argv[1], 0o600)
PY_ID
"$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & G_DAEMON=$!
PIDS+=("$G_DAEMON")
member_sent() { [ "$(epq "any(f['frame'].get('t') == 'member' and f['frame'].get('session') == '$MC' for f in d['received'])")" = true ]; }
until_true 400 member_sent || true
assert_equals "$(member_sent && echo sent)" sent "the uplink, on the endpoint's socket, sends mc's member frame"
SCRATCH="$T/c/scratch"
gitq clone -q "$MIRROR" "$SCRATCH"
python3 - "$SCRATCH/gamma.human.jsonl" "$MC" <<'PY_FORGE'
import json, sys, time
e = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()), "writer": "gamma/human", "seq": 1, "kind": "human",
     "from": "human", "to": [{"session": sys.argv[2], "alias": "mc"}], "text": "forged through the mirror"}
with open(sys.argv[1], "a") as f:
    f.write(json.dumps(e) + "\n")
PY_FORGE
gitq -C "$SCRATCH" add -A
gitq -C "$SCRATCH" commit -qm "a line under gamma's operator writer"
gitq -C "$SCRATCH" push -q origin HEAD:main
forged_in() { grep -q "forged through the mirror" "$T/mc.received"; }
until_true 400 forged_in || true
FRAME="$(grep "forged through the mirror" "$T/mc.received" | tail -1)"
assert_contains "$FRAME" "from human (unverified)" "daemon run's tick merges it in and delivers it as an unverified peer message"
assert_contains "$(cat "$SMINOS_HOME/daemon.log")" "gamma/human:1 (mirrored) is delivered as an unverified peer message, never asked: no append receipt bears it out" \
  "said in daemon.log, naming the project, the writer and the seq"
assert_equals "$(test -s "$SMINOS_HOME/projects/$MPID/receipts/gamma.human.jsonl" && echo some || echo none)" none \
  "it has no append receipt"
run "$SMINOS" say --in mirrored "@mc said here"
assert_equals "$RC" 0 "an operator say from gamma's terminal exits 0"
assert_contains "$OUT" "mc: recorded; the endpoint decides its delivery" "is left to the endpoint's verdict"
said_in() { grep -q "said here" "$T/mc.received"; }
until_true 400 said_in || true
assert_equals "$(said_in && echo delivered)" delivered "and delivered by the uplink on its verdict"
assert_equals "$(epq "[f['frame']['event']['text'] for f in d['received'] if f['frame'].get('t') == 'words?']")" '["@mc said here"]' \
  "words? asked for the say alone, never for the forged line"
assert_equals "$(epq "[f['frame'].get('project') for f in d['received'] if f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$MPID']")" '[]' \
  "the git-mirrored project is never opened on the endpoint's socket"
run "$SMINOS" chat mirrored -n 5
assert_contains "$OUT" "human (unverified) → @mc  forged through the mirror" "chat shows the forged line unverified"
assert_contains "$OUT" "human → @mc  @mc said here" "and the say said here as it always was"
kill "$G_DAEMON"
set +e; wait "$G_DAEMON"; set -e
assert_not_contains "$(cat "$SMINOS_HOME/daemon.log")" "Traceback" "nothing in gamma's daemon.log is a traceback"
unset MAWS_USER_DATA

# ---- RL10: one machine cut over to its endpoint (#153 M3c)
# test-sync's one-machine cases: a machine whose sessions joined under a
# former name, projects that leave the hub, hello and presence before
# uploads, delivery past spent positions, and a refusal the resend after it
# does not undo. One machine,
# cut over by its endpoint's welcome to `daemon probe` (the production path:
# a rename is a welcome naming the new name with the old one in `former`),
# never enrolled at a hub and holding no hub.json; endpoint_standin.py
# serves its endpoint, and stands in for every other machine: their events
# arrive through it as RL10 arrivals, and the endpoint's own verdicts come
# down as its frames. A person's words are delivered on the endpoint's
# `words` verdict. What another machine sees of all this is the two-machine
# compositions'.

# ---- a machine that held its sessions under another name, then is
# welcomed as beta
echo "RL10: a machine renamed by its endpoint's welcome:"
as r betaold
export MAWS_USER_DATA="$T/r/maws"
REP="$MAWS_USER_DATA/mawsd/endpoint"
rctl() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$REP" "$@"; }
# What the stand-in received, as a Python expression over its state (d) and
# these: F, every frame [(connection, frame)]; up(pid), every event uploaded
# in pid [(connection, event)]; rejected(pid), the rejected frames up; conns,
# the uplink's connections, in order (a probe's sends its hello alone).
cat > "$T/rl10q.py" <<'PY'
import json, sys
d = json.load(sys.stdin)
F = [(r["conn"], r["frame"]) for r in d["received"]]
conns = sorted({c for c, f in F if not (f.get("t") == "hello" and "token" in f)})
def up(pid):
    return [(c, e) for c, f in F if f.get("t") == "events" and f.get("project") == pid for e in f.get("events", [])]
def rejected(pid):
    return [f for c, f in F if f.get("t") == "rejected" and f.get("project") == pid]
print(json.dumps(eval(sys.argv[1])))
PY
rq() { rctl state | python3 "$T/rl10q.py" "$1"; }
# Another machine's event, or a person's from the web, as the endpoint sends
# it down: {event, signer}, or shapes it never sends (no signer, a `verified`
# of the event's own, a seq no log holds, an event not wrapped at all).
cat > "$T/arrival.py" <<'PY'
import json, sys, time
variant, writer, seq, text = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
to = [{"session": s, "alias": a} for s, a in zip(sys.argv[5::2], sys.argv[6::2])]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
member = writer.partition("/")[2]
signer = {"kind": "device", "member": member, "device": "dev-1", "keyId": "k-dev-1"}
e = {"ts": ts, "writer": writer, "seq": seq, "kind": "human", "from": "human", "member": member, "to": to,
     "text": text, "created": ts, "sig": {"kid": "k-dev-1", "sig": "AA"}}
if variant == "shapeless":
    e["seq"] = "the %dth" % seq
if variant == "verified":
    e["verified"] = {"signer": signer}
raw = {"event": e, "signer": signer}
if variant == "nosigner":
    del raw["signer"]
print(json.dumps(e if variant == "unwrapped" else raw))
PY
arrival() { python3 "$T/arrival.py" "$@"; }
RR="$T/r/repo"
RPID=7d000001-0000-4000-8000-0000000000d1
RLOG="$T/r/s/projects/$RPID/log"
mkdir -p "$RR"
gitq init -q "$RR"
# The checkout's .smns, as a hub project's is committed (`project init --hub`
# on a machine enrolled in its org): this one was not enrolled yet.
printf '{"project": "%s", "name": "rlproj", "remote": "ssh://archive%s/rl-archive.git", "hub": {"org": "org-1"}}\n' \
  "$RPID" "$T" > "$RR/.smns"
cd "$RR"
RMB=5d000001-0000-4000-8000-0000000000d1
RNB=5d000002-0000-4000-8000-0000000000d2
inbox rmb
sleep 600 & RNB_PID=$!
PIDS+=("$RNB_PID")
printf '{"pid":%s,"sessionId":"%s","name":"mb","nameSource":"derived","kind":"bg","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX_PID" "$RMB" "$RR" "$T/rmb.sock" > "$HOME/.claude/sessions/mb.json"
printf '{"pid":%s,"sessionId":"%s","name":"nb","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$RNB_PID" "$RNB" "$RR" > "$HOME/.claude/sessions/nb.json"
printf '[{"id": "mbshort", "sessionId": "%s", "state": "idle"}]\n' "$RMB" > "$STUB_STATE/agents.json"
"$SMINOS" seat add rlproj mb --session "$RMB" >/dev/null 2>&1
run "$SMINOS" list --json
assert_contains "$OUT" '"machine": "betaold"' "RL10: the seat mb and the session nb join as betaold"
assert_equals "$(find "$RLOG" -name 'betaold.*.jsonl' | wc -l | tr -d ' ')" 2 "RL10: beta's log holds its own two writers"
printf '{"pid":%s,"sessionId":"%s","name":"nb-renamed","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$RNB_PID" "$RNB" "$RR" > "$HOME/.claude/sessions/nb.json"
run "$SMINOS" daemon tick
assert_equals "$(python3 -c 'import json, sys
print([(e["kind"], e.get("alias") or e.get("state")) for e in map(json.loads, open(sys.argv[1])) if e["kind"] != "joined"])' \
  "$RLOG/betaold.$RNB.jsonl")" "[('state', 'idle'), ('renamed', 'nb-renamed')]" \
  "RL10: nb's state and its rename to nb-renamed are published under betaold"
# ob: a session this machine holds as betaold in another checkout, a plain git one.
RRO="$T/r/other"
gitq init -q "$RRO"
ROB=5d000003-0000-4000-8000-0000000000d3
sleep 600 & ROB_PID=$!
PIDS+=("$ROB_PID")
printf '{"pid":%s,"sessionId":"%s","name":"ob","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$ROB_PID" "$ROB" "$RRO" > "$HOME/.claude/sessions/ob.json"
(cd "$RRO" && "$SMINOS" list >/dev/null 2>&1)
# The endpoint enrolled the machine as beta just now, beta formerly betaold.
RL_ENROLLED="$(python3 -c 'import time; t = time.time(); print(time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime(t)) + "%03dZ" % int(t % 1 * 1000))')"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$REP" "{\"identity\": {\"org\": \"org-1\", \"hub\": \"http://127.0.0.1:9\", \"name\": \"beta\", \"former\": [\"betaold\"], \"ref\": \"ref-beta\", \"enrolled\": \"$RL_ENROLLED\"}, \"verdict\": \"words\", \"ask_legacy\": false}" &
PIDS+=("$!")
until_true 100 test -S "$REP/ctl.sock"
run "$SMINOS" daemon probe
assert_contains "$OUT" "welcomed as beta of org org-1: this machine is cut over" \
  "RL10: beta is cut over under a new name by its endpoint's welcome"
assert_equals "$(test -e "$T/r/s/daemon/hub.json" && echo held || echo none)" none "RL10: and holds no hub.json"
as r beta
start_daemon
R_DAEMON=$DAEMON_PID
rl_writers() { rq "sorted({e['writer'] for c, e in up('$RPID') if e['writer'].startswith('beta')})"; }
rl_rejoined() { [ "$(rl_writers)" = "[\"beta/$RMB\", \"beta/$RNB\"]" ]; }
until_true 400 rl_rejoined || true
assert_equals "$(rl_writers)" "[\"beta/$RMB\", \"beta/$RNB\"]" \
  "RL10: the seat and the session that joined as betaold join again as beta, and only as beta"
assert_contains "$(cat "$T/r/s/daemon.log")" "mb in rlproj joined again as beta (it had joined as betaold)" "RL10: saying so"
assert_equals "$(rq "[(e['kind'], e.get('alias'), e.get('name_source'), e.get('state')) for c, e in up('$RPID') if e['writer'] == 'beta/$RNB'][:2]")" \
  '[["joined", "nb-renamed", "user", null], ["state", null, null, "idle"]]' \
  "RL10: nb joins again under its name now, nb-renamed, and with its state: what betaold published stays local"
run "$SMINOS" list --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))')" \
  "[('mb', 'beta', True), ('nb-renamed', 'beta', True)]" "RL10: beta keeps mb and nb-renamed its own"

# ---- the seat, the session, send, retirement and new writers after the
# endpoint's welcome renamed the machine. What reaches a session from this
# machine's terminal goes on the endpoint's verdict (`words`); the seat's
# retirement, and the session of a machine now named betaold, are at the end
# of this file's RL10 cases, which deliver to mb until then.
echo "RL10: after the rename:"
run "$SMINOS" send mb "after the rename"
assert_equals "$RC" 0 "RL10: send reaches the seat"
until_true 200 grep -q "after the rename" "$T/rmb.received" || true
assert_contains "$(cat "$T/rmb.received")" "after the rename" "RL10: through its inbox"
assert_equals "$(rq "[f['event']['text'] for c, f in F if f.get('t') == 'words?' and f['event'].get('text') == 'after the rename']")" \
  '["after the rename"]' "RL10: on the endpoint's verdict, asked with words?"
rl_writers_here() { find "$RLOG" -name "$1.*.jsonl" | wc -l | tr -d ' '; }
BETAOLD_WRITERS="$(rl_writers_here betaold)"
kill "$RNB_PID"
set +e; wait "$RNB_PID" 2>/dev/null; set -e
rl_nb_retired() { grep -q '"reason": "ended"' "$RLOG/beta.$RNB.jsonl" 2>/dev/null; }
(cd "$RR" && "$SMINOS" list --all --json >/dev/null)
until_true 200 rl_nb_retired || true
assert_equals "$(rl_nb_retired && echo retired)" retired \
  "RL10: a session that joined as betaold and ended is retired as this machine's own, under beta"
assert_not_contains "$(cat "$RLOG/betaold.$RNB.jsonl")" '"retired"' "RL10: and nothing is written under the former name"
"$SMINOS" say "said as beta" >/dev/null
assert_contains "$(cat "$RLOG/beta.human.jsonl")" "said as beta" "RL10: new events are written under beta"
assert_equals "$(rl_writers_here betaold)" "$BETAOLD_WRITERS" "RL10: and no new betaold/ writer appears"

# ---- ob joins rlproj while beta's connection is open, written as betaold:
# the hook of a Claude Code whose plugin predates the enrollment names the
# writer after the host, as that plugin did.
echo "RL10: a member joined as betaold on an open connection:"
R_CONN="$(rq "d['current']")"
python3 - "$ROB" "$ROB_PID" "$RR" "$HOME/.claude/sessions/ob.json" <<'PY'
import json, os, sys
tmp = sys.argv[4] + ".tmp"
with open(tmp, "w") as f:   # replaced whole: a record read mid-write would be no record, and ob ended
    json.dump({"pid": int(sys.argv[2]), "sessionId": sys.argv[1], "name": "ob", "nameSource": "derived",
               "kind": "interactive", "entrypoint": "sdk-cli", "status": "idle", "cwd": sys.argv[3]}, f)
os.replace(tmp, sys.argv[4])
PY
# ob's engine record moves to rlproj first, and only once two of beta's
# ticks have read it does the joined land: a reconciliation that read the
# joined beside the record still naming ob's other checkout would retire ob
# here as `moved` (the uplink's runs as soon as an append lands). The record
# is an SDK run's, which no reconciliation joins on sight, so nothing joins
# ob as beta before its betaold joined: what joins it again is the daemon's
# rejoin of a former name, which says so.
tick_r() { python3 -c 'import os, sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$T/r/s/daemon/ticked" 2>/dev/null || true; }
tick_r_moved() { [ "$(tick_r)" != "$1" ]; }
r_ticks() { local i t; for i in $(seq 1 "$1"); do t="$(tick_r)"; until_true 200 tick_r_moved "$t" || true; done; }
r_ticks 2
python3 - "$RR" "$ROB" <<'PY'
import os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
project, ob = sminos.resolve_project(sys.argv[1]), sys.argv[2]
# The daemon names a former name's writer only for an event a second past
# the enrollment's stamp (identity.json's `enrolled`, whole seconds).
since = sminos.daemon_module().enrolled_at()
if since is not None:
    time.sleep(max(0.0, since + 1.05 - time.time()))
sminos._append(project, "betaold/" + ob, [{"kind": "joined", "session": ob, "alias": "ob", "name_source": "derived",
                                            "machine": "betaold", "cwd": sys.argv[1], "worktree": "", "role": "",
                                            "seat": "", "by": ""}])
PY
until_true 200 grep -Fq "ob in rlproj still writes as betaold" "$T/r/s/daemon.log" || true
rl_ob_up() { [ "$(rq "len([1 for c, e in up('$RPID') if e['writer'] == 'beta/$ROB'])")" -ge 1 ]; }
until_true 200 rl_ob_up || true
assert_contains "$(cat "$T/r/s/daemon.log")" "ob in rlproj joined again as beta (it had joined as betaold)" \
  "RL10: the daemon's rejoin of the former name is what joins ob as beta"
assert_equals "$(rq "[(c, e['kind'], e.get('alias')) for c, e in up('$RPID') if e['writer'] == 'beta/$ROB'][:1]")" \
  "[[$R_CONN, \"joined\", \"ob\"]]" "RL10: ob joins again as beta, on the connection already open"
assert_equals "$(rq "d['current']")" "$R_CONN" "RL10: which stays open"
assert_contains "$(cat "$T/r/s/daemon.log")" "ob in rlproj still writes as betaold" \
  "RL10: the daemon says ob still writes under the former name"
assert_not_contains "$(cat "$T/r/s/daemon.log")" "nb-renamed in rlproj still writes" \
  "RL10: and says nothing of nb, which wrote as betaold only before the enrollment"
r_ticks 3
assert_equals "$(grep -c "ob in rlproj still writes" "$T/r/s/daemon.log")" 1 "RL10: said once, however many ticks see the writer"
assert_equals "$(rq "sorted({e['writer'] for c, e in up('$RPID') if e['writer'].startswith('betaold/')})")" "[]" \
  "RL10: no writer of the former name reaches the endpoint"

# ---- projects that stop being hub projects of this org
echo "RL10: projects that leave the hub:"
for q in q1 q2 q3; do
  mkdir -p "$T/r/$q"
  gitq init -q "$T/r/$q"
  (cd "$T/r/$q" && "$SMINOS" project init --name "$q" --hub >/dev/null && "$SMINOS" say "first in $q" >/dev/null)
done
rqid() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$T/r/$1/.smns"; }
RQ1="$(rqid q1)" RQ2="$(rqid q2)" RQ3="$(rqid q3)"
rq_up() { [ "$(rq "all(any(e['writer'] == 'beta/human' for c, e in up(p)) for p in ['$RQ1', '$RQ2', '$RQ3'])")" = true ]; }
until_true 200 rq_up || true
if rq_up; then pass "RL10: three more hub projects open and upload"; else fail "RL10: three more hub projects open and upload"; fi
R_CONN="$(rq "d['current']")"
python3 - "$T/r" <<'PY'
import json, sys
for q, change in (("q1", lambda d: d.update(hub={"url": "https://elsewhere.example"})), ("q2", lambda d: d["hub"].update(org="org-2")),
                  ("q3", lambda d: d.pop("hub"))):
    path = "%s/%s/.smns" % (sys.argv[1], q)
    d = json.load(open(path)); change(d); json.dump(d, open(path, "w"))
PY
# Left, whichever scans saw the three edits: daemon.log has named each one,
# and the connection up now, made since, has opened rlproj and none of them.
rl_left() {
  local said q
  said="$(grep "no longer a hub project of org org-1" "$T/r/s/daemon.log" || true)"
  for q in q1 q2 q3; do grep -Eq "[ ,]$q(,|:|$)" <<<"$said" || return 1; done
  [ "$(rq "d['current'] is not None and d['current'] > $R_CONN and any(c == d['current'] and f.get('t') == 'hello' and f.get('project') == '$RPID' for c, f in F) and not any(c == d['current'] and f.get('t') == 'hello' and f.get('project') in ('$RQ1', '$RQ2', '$RQ3') for c, f in F)")" = true ]
}
until_true 200 rl_left || true
R_LEFT="$(rq "d['current'] or 0")"   # the connection made once all three had left
for q in q1 q2 q3; do
  (cd "$T/r/$q" && "$SMINOS" say "after $q left the hub" >/dev/null 2>&1)
done
# What beta appends from here is uploaded; a say in rlproj after them marks the time.
"$SMINOS" say "beta after the projects left" >/dev/null
rl_text_up() { [ "$(rq "any(e.get('text') == '$1' for c, e in up('$RPID'))")" = true ]; }
until_true 200 rl_text_up "beta after the projects left" || true
assert_equals "$(rl_text_up "beta after the projects left" && echo up)" up "RL10: the say after them is uploaded"
for q in q1 q2 q3; do
  assert_equals "$(rq "[e.get('text') for c, e in up('$(rqid "$q")')]")" "[\"first in $q\"]" "RL10: $q's later say never reaches the endpoint"
done
assert_contains "$(grep "no longer a hub project of org org-1" "$T/r/s/daemon.log")" "q1" "RL10: a malformed hub ends the project's sync, saying so"
assert_contains "$(grep "no longer a hub project of org org-1" "$T/r/s/daemon.log")" "q2" "RL10: so does a hub of another org"
assert_contains "$(grep "no longer a hub project of org org-1" "$T/r/s/daemon.log")" "q3" "RL10: and a .smns that names no hub"
assert_equals "$(rq "sorted({f['project'] for c, f in F if c >= $R_LEFT and f.get('t') == 'hello' and f.get('project') in ('$RQ1', '$RQ2', '$RQ3')})")" "[]" \
  "RL10: beta's new connection opens none of them at the endpoint"

# ---- refused before the log: the endpoint verifies, and what sminos still
# refuses is an arrival's shape — reported up as `rejected` — beside the
# positions the endpoint itself spends
echo "RL10: refused before the log, and spent positions:"
RW="hub/$MEMBER"
rl_send() { rctl send "{\"frames\": $1}" >/dev/null; }
rl_events() { printf '{"t": "events", "project": "%s", "events": [%s]}' "$RPID" "$1"; }
rl_spent() { printf '{"t": "spent", "project": "%s", "writer": "%s", "seq": %s, "reason": "%s"}' "$RPID" "$RW" "$1" "$2"; }
rl_send "[$(rl_events "$(arrival ok "$RW" 1 "from the web, first" "$RMB" mb), $(arrival nosigner "$RW" 2 "forged: no signer" "$RMB" mb), $(arrival verified "$RW" 3 "forged: a verified of its own" "$RMB" mb)"),
  $(rl_spent 4 bad-signature), $(rl_spent 5 replayed),
  $(rl_events "$(arrival shapeless "$RW" 6 "forged: no seq a log holds" "$RMB" mb), $(arrival unwrapped "$RW" 6 "forged: not wrapped" "$RMB" mb)"),
  $(rl_events "$(arrival ok "$RW" 6 "from the web, after the forgeries" "$RMB" mb)")]"
rl_rejections() { rq "len(rejected('$RPID'))"; }
rl_rejected_at_least() { [ "$(rl_rejections)" -ge "$1" ]; }
until_true 200 rl_rejected_at_least 4 || true
until_true 200 grep -q "after the forgeries" "$T/rmb.received" || true
assert_not_contains "$(cat "$RLOG/"*.jsonl)" "forged:" "RL10: no forged event enters beta's log"
assert_not_contains "$(cat "$T/rmb.received")" "forged:" "RL10: or reaches mb"
assert_contains "$(cat "$T/rmb.received")" "from the web, first" "RL10: the authentic web human before them reaches mb"
assert_contains "$(cat "$T/rmb.received")" "from the web, after the forgeries" \
  "RL10: and so does the one after them: a refused position holds back no later event"
rl_reported() { # writer seq reason — how many rejected reports name it so (writer "": the event null)
  rq "len([f for f in rejected('$RPID') if f['reason'] == '$3' and (f['event'] == {'writer': '$1', 'seq': $2} if '$1' else f['event'] is None)])"; }
assert_equals "$(rl_reported "$RW" 2 bad-shape)" 1 "RL10: beta reports the arrival with no signer: bad-shape, with its position"
assert_equals "$(rl_reported "$RW" 3 bad-shape)" 1 "RL10: beta reports the event carrying a verified of its own: bad-shape"
assert_equals "$(rl_reported "" 0 bad-shape)" 2 "RL10: beta reports what is no log event, and an event not wrapped: bad-shape, its event null"
assert_equals "$(rq "[f['event']['seq'] for f in rejected('$RPID') if f['event'] and f['event']['seq'] in (4, 5)]")" "[]" \
  "RL10: and nothing of the positions the endpoint spent, which it rejected up itself"
assert_contains "$(cat "$T/r/s/daemon.log")" "the endpoint spent $RW:4 in rlproj ($RPID): bad-signature" \
  "RL10: beta's daemon.log says each position the endpoint spent, with its reason"
rl_send "[$(rl_events "$(arrival ok "$RW" 7 "from the web, later still" "$RMB" mb)")]"
until_true 200 grep -q "later still" "$T/rmb.received" || true
assert_contains "$(cat "$T/rmb.received")" "from the web, later still" "RL10: a later web human is delivered past the spent positions"
run "$SMINOS" chat rlproj -n 400
assert_contains "$OUT" "from the web, after the forgeries" "RL10: beta's chat shows the human after the hole"
assert_contains "$OUT" "from the web, later still" "RL10: and the one after it"
assert_not_contains "$OUT" "forged:" "RL10: and nothing forged"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$RLOG/../delivered/$RMB.json" "$RW")" \
  "{'settled': 7, 'pending': None, 'attempts': 0}" "RL10: mb's delivery record settles hub/$MEMBER at 7, past the hole, nothing pending"
assert_not_contains "$(cat "$T/r/s/daemon.log")" "out of order" "RL10: no deliverer finds the hole out of order"
# A spent position is a tombstone: an event that is whole, arriving there later, is refused too —
# at a position sminos refused, and at one the endpoint spent.
rl_send "[$(rl_events "$(arrival nosigner "$RW" 8 "forged: at 8" "$RMB" mb)"), $(rl_events "$(arrival ok "$RW" 8 "valid, at a spent position" "$RMB" mb), $(arrival ok "$RW" 4 "valid, at a position the endpoint spent" "$RMB" mb)")]"
until_true 200 rl_rejected_at_least 7 || true
assert_equals "$(rl_reported "$RW" 8 bad-shape) $(rl_reported "$RW" 8 conflict) $(rl_reported "$RW" 4 conflict)" "1 1 1" \
  "RL10: beta refuses the events at 8: the shapeless one as bad-shape, then the whole one at its tombstone as conflict, and one at a position the endpoint spent"
assert_not_contains "$(cat "$RLOG/hub.$MEMBER.jsonl")" "valid, at" "RL10: nothing is appended at a spent position"
assert_equals "$(rq "sorted({f['event']['seq'] for f in rejected('$RPID') if f['reason'] == 'conflict' and 'was refused here before' in f['message']})")" "[4, 8]" \
  "RL10: saying it was refused there before"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["spent"][sys.argv[2]])' "$RLOG/../uplink.json" "$RW")" \
  "[2, 3, 4, 5, 8]" "RL10: and the positions spent, kept in beta's uplink.json"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("unreported"))' "$RLOG/../uplink.json")" "[]" "RL10: every report delivered"
# The positions refused are spent: a new connection does not ask for them
# again (its hello's have carries the writer past them), nor report them twice.
R_CONN="$(rq "d['current']")"
rctl drop >/dev/null
rl_hello_since() { [ "$(rq "any(c > $1 and f.get('t') == 'hello' and f.get('project') == '$RPID' for c, f in F)")" = true ]; }
until_true 200 rl_hello_since "$R_CONN" || true
"$SMINOS" say "beta after the forgeries" >/dev/null
until_true 200 rl_text_up "beta after the forgeries" || true
assert_equals "$(rl_text_up "beta after the forgeries" && echo up)" up "RL10: reconnected, beta uploads again"
assert_equals "$(rl_rejections)" 7 "RL10: reconnected, beta reports no refused event again"
assert_equals "$(rq "[f['have'].get('$RW') for c, f in F if c > $R_CONN and f.get('t') == 'hello' and f.get('project') == '$RPID']")" "[8]" \
  "RL10: its hello holds hub/$MEMBER at 8, past the spent positions: the hole is not asked for again"
last_seq_r() { python3 -c 'import json, sys; print(json.loads(open(sys.argv[1]).read().splitlines()[-1])["seq"])' "$1"; }
assert_equals "$(last_seq_r "$RLOG/hub.$MEMBER.jsonl") $(wc -l < "$RLOG/hub.$MEMBER.jsonl" | tr -d ' ')" "7 3" \
  "RL10: hub/$MEMBER's last seq is 7, holding the three authentic events of its eight positions"
# A lone surrogate in an arrival's writer, escaped in the endpoint's JSON: refused
# by its shape, reported up as it came, its position spent as it came.
RL_SURROGATE="$(python3 -c 'import json, sys; e = json.loads(sys.argv[1]); e["event"]["writer"] += "\ud800"; print(json.dumps(e))' \
  "$(arrival ok "$RW" 9 "forged: a surrogate in the writer" "$RMB" mb)")"
rl_send "[$(rl_events "$RL_SURROGATE")]"
until_true 200 rl_rejected_at_least 8 || true
assert_equals "$(rq "[(f['reason'], f['event']['writer'].endswith(chr(0xd800))) for f in rejected('$RPID') if f['event'] and f['event']['seq'] == 9]")" \
  '[["bad-shape", true]]' "RL10: a writer carrying a lone surrogate is reported up as it came"
assert_equals "$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(sorted((w.endswith(chr(0xd800)), ss) for w, ss in d["spent"].items() if w.startswith(sys.argv[2])))' "$RLOG/../uplink.json" "$RW")" \
  "[(False, [2, 3, 4, 5, 8]), (True, [9])]" "RL10: and its position spent, kept in beta's uplink.json as it came"
assert_not_contains "$(cat "$RLOG/"*.jsonl)" "a surrogate in the writer" "RL10: and nothing of it in the log"

# ---- what each connection carried: a daemon restart, one more connection
echo "RL10: what each connection carried:"
kill "$R_DAEMON"
set +e; wait "$R_DAEMON"; set -e
R_CONN="$(rq "d['conns']")"
start_daemon
R_DAEMON=$DAEMON_PID
until_true 200 rl_hello_since "$R_CONN" || true
"$SMINOS" say "beta after its daemon restarts" >/dev/null
until_true 200 rl_text_up "beta after its daemon restarts" || true
rctl state > "$T/r/state.json"
assert_equals "$(python3 - "$T/r/state.json" "$RPID" <<'PY'
import json, sys
d, pid = json.load(open(sys.argv[1])), sys.argv[2]
F = [(r["conn"], r["frame"]) for r in d["received"]]
conns = sorted({c for c, f in F if not (f.get("t") == "hello" and "token" in f)})   # a probe's sends its hello alone
bad = []
for c in conns:
    hellos, machine = set(), None
    for n, f in F:
        if n != c:
            continue
        t = f.get("t")
        if t == "hello" and isinstance(f.get("project"), str):
            hellos.add(f["project"])
        elif t == "session" and machine is None and f.get("message", {}).get("kind") == "machine" \
                and f["message"].get("project") == pid:
            machine = f["message"]["body"]
            if not any(x["path"].endswith("/repo") and x["branch"] == "main" for x in machine["checkouts"]):
                bad.append("connection %d: a machine presence without the checkout: %r" % (c, machine))
        elif t == "events":
            if f["project"] not in hellos:
                bad.append("connection %d uploaded in %s before its hello" % (c, f["project"]))
            if f["project"] == pid and machine is None:
                bad.append("connection %d uploaded in rlproj before the machine's presence" % c)
    if pid not in hellos or machine is None:
        bad.append("connection %d: hello of rlproj %s, the machine's presence %s" % (c, pid in hellos, machine is not None))
print(bad or ("ok" if len(conns) >= 4 else "only %d connections" % len(conns)))
PY
)" ok "RL10: on each of beta's four connections: hello and the machine's presence (its checkout and branch) before any upload"
assert_equals "$(test -e "$T/ssh-entered" && echo fetched || echo never)" never "RL10: beta never ran git against the project's remote"
assert_equals "$(test -e "$RLOG/.git" && echo git || echo none)" none "RL10: nor made its log a git working tree"

# ---- an event the endpoint refuses for good, and one after it: an own
# event refused too-large, and a resend from the refused position right
# behind the refusal; the refusal wins on that connection.
echo "RL10: an own event refused too-large, and the resend after it:"
RBIG=5d0000bb-0000-4000-8000-0000000000bb
python3 - "$RLOG" "$RBIG" <<'PY'
import json, os, sys, time
log, s = sys.argv[1], sys.argv[2]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
nobody = [{"session": "5d0000bc-0000-4000-8000-0000000000bc", "alias": "nobody"}]
evs = [{"ts": ts, "writer": "beta/" + s, "seq": 1, "kind": "say", "from": "big", "to": nobody, "text": "the large one"},
       {"ts": ts, "writer": "beta/" + s, "seq": 2, "kind": "say", "from": "big", "to": nobody, "text": "after the large one"}]
tmp = os.path.join(log, ".big.tmp")
with open(tmp, "w") as f:
    f.write("".join(json.dumps(e) + "\n" for e in evs))
os.replace(tmp, os.path.join(log, "beta.%s.jsonl" % s))
PY
rl_big_ups() { rq "len([1 for c, e in up('$RPID') if e['writer'] == 'beta/$RBIG' and e['seq'] == 1])"; }
rl_big_up() { [ "$(rl_big_ups)" -ge 1 ]; }
until_true 200 rl_big_up || true
rl_send "[{\"t\": \"refused\", \"project\": \"$RPID\", \"refusal\": {\"reason\": \"too-large\", \"writer\": \"beta/$RBIG\", \"seq\": 1, \"message\": \"the event is past 1 MiB\"}},
  {\"t\": \"resend\", \"project\": \"$RPID\", \"writer\": \"beta/$RBIG\", \"from\": 1}]"
until_true 200 grep -Fq "the hub asks beta/$RBIG of rlproj again from 1" "$T/r/s/daemon.log" || true
# A writer followed again goes up within the upload pass the resend starts:
# 2 s is many of those, and nothing else would send it.
sleep 2
assert_equals "$(rl_big_ups)" 1 "RL10: beta does not upload it again on this connection: the resend after its refusal does not reopen the writer"
assert_contains "$(cat "$T/r/s/daemon.log")" "the hub refused in rlproj: too-large beta/$RBIG:1" "RL10: daemon.log says the endpoint refused it"
assert_contains "$(cat "$T/r/s/daemon.log")" "the hub asks beta/$RBIG of rlproj again from 1, where it refused it" \
  "RL10: and that the resend after it is not followed"

# ---- the rest of "after the rename" above: a session of the machine now
# named betaold is that machine's, and
# the seat that joined as betaold is retired as this machine's own, stopping
# the session it recorded then.
echo "RL10: after the rename, the former name's other holder and the seat's retirement:"
RSA=5d00000a-0000-4000-8000-0000000000aa
# Its joined, as the endpoint relays the other machine's event down: wrapped, that machine its signer.
rl_send "$(python3 - "$RSA" "$RPID" <<'PY'
import json, sys, time
sid, pid = sys.argv[1], sys.argv[2]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
e = {"ts": ts, "writer": "betaold/" + sid, "seq": 1, "kind": "joined", "session": sid, "alias": "a-term",
     "name_source": "derived", "machine": "betaold", "cwd": "/elsewhere", "worktree": "", "role": "", "seat": "",
     "by": "", "created": ts, "sig": {"kid": "k-betaold", "sig": "AA"}}
signer = {"kind": "machine", "ref": "ref-betaold", "name": "betaold", "keyId": "k-betaold"}
print(json.dumps([{"t": "events", "project": pid, "events": [{"event": e, "signer": signer, "owners": []}]}]))
PY
)"
rl_rsa_imported() { grep -q '"verified": {"signer": {"kind": "machine"' "$RLOG/betaold.$RSA.jsonl" 2>/dev/null; }
until_true 200 rl_rsa_imported || true
assert_equals "$(rl_rsa_imported && echo imported)" imported "RL10: the other betaold's joined arrives from the endpoint, verified"
run "$SMINOS" list --all --json
assert_contains "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))')" "('a-term', 'betaold', False)" \
  "RL10: a session of the machine now named betaold is that machine's, not this one's"
r_ticks 2
assert_equals "$(test -e "$RLOG/beta.$RSA.jsonl" && echo there || echo none)" none "RL10: and this machine never retires it"
# claude, as this file's stub, recording each `stop`.
mkdir -p "$T/r/bin"
cat > "$T/r/bin/claude" <<STUB
#!/usr/bin/env bash
[ "\${1:-}" = stop ] && { echo "\$2" >> "\$STUB_STATE/stops"; exit 0; }
exec "$T/bin/claude" "\$@"
STUB
chmod +x "$T/r/bin/claude"
echo "[]" > "$STUB_STATE/agents.json"
R_PATH="$PATH"
export PATH="$T/r/bin:$PATH"
run "$SMINOS" retire mb
export PATH="$R_PATH"
assert_equals "$RC" 0 "RL10: retire acts on the seat"
assert_equals "$(cat "$STUB_STATE/stops" 2>/dev/null)" "mbshort" "RL10: stopping the session it recorded as betaold"
assert_contains "$(cat "$RLOG/beta.$RMB.jsonl")" '"kind": "retired"' "RL10: its retirement written under beta"

kill "$R_DAEMON"
set +e; wait "$R_DAEMON"; set -e
assert_not_contains "$(cat "$T/r/s/daemon.log")" "Traceback" "RL10: nothing in beta's daemon.log is a traceback"
unset MAWS_USER_DATA

# ---- RL10: two machines, each cut over to its endpoint (#153 M3d)
# The two-machine sync: alpha and beta are real
# sminos homes, each with its daemon and its endpoint_standin.py, never
# enrolled at a hub and holding no hub.json. What one endpoint accepted
# reaches the other's connection as arrivals through the stand-in's own echo
# (rl10_relay, the hand-off that stands in for MAWS's relay); each case
# asserts what the producer's endpoint took and what the consumer holds,
# shows or delivered: a fresh machine's bootstrap, the members and their
# states, a burst on both with messages across, titles, a daemon restart and
# a dropped connection, the logs identical on both machines and the
# endpoints at each step. (The former name, and the cases of one machine,
# are the block above.)
echo "RL10: two machines through their endpoints:"
# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"
export SCRIPT_DIR   # the comparisons below import endpoint_standin from it
rl10_as ya alpha
rl10_cut_over
YEPA=$EP
YRA="$T/ya/repo"
mkdir -p "$YRA"
gitq init -q "$YRA"
cd "$YRA"
"$SMINOS" project init --name syncproj --hub --remote "ssh://archive$T/rl-archive2.git" >/dev/null
YPID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$YRA/.smns")"
YALOG="$T/ya/s/projects/$YPID/log"
YBLOG="$T/yb/s/projects/$YPID/log"
YMA=6a000001-0000-4000-8000-0000000000a1
inbox yma
printf '{"pid":%s,"sessionId":"%s","name":"ma","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX_PID" "$YMA" "$YRA" "$T/yma.sock" > "$HOME/.claude/sessions/ma.json"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "ma"' "RL10: ma joins syncproj on alpha"
rl10_serve
start_daemon
YA_DAEMON=$DAEMON_PID
y_relayed() { rl10_relay "$YEPA" "$YEPB"; "$@"; }
# The log of the project as each machine and the endpoints hold it, writer by
# writer: counts, last seq, and payloads (each event without what an endpoint
# adds to it — `created`, `sig`, `attest`, and the `verified` its arrival is
# stored with), an own writer's as its machine's endpoint took it; beta's
# former name's writers, which stay on beta, left out.
cat > "$T/rl10compare.py" <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["SCRIPT_DIR"])
import endpoint_standin
pid, alog, blog, epa, epb = sys.argv[1:6]
def local(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*.jsonl")):
        evs = [json.loads(l) for l in open(p) if l.strip()]
        if evs:
            out[evs[0]["writer"]] = sorted(evs, key=lambda e: e["seq"])
    return out
def endpoint(d):
    out = {}
    for a in json.loads(endpoint_standin.ctl_call(d, "accepted", {"project": pid}))["events"]:
        out.setdefault(a["event"]["writer"], []).append(a["event"])
    return out
held = {"alpha": local(alog), "beta": local(blog)}
for side in held.values():   # a former name's writers stay on their machine
    for w in [w for w in side if w.startswith("betaold/")]:
        del side[w]
took = {"alpha": endpoint(epa), "beta": endpoint(epb)}
def payload(e):
    return json.dumps({k: v for k, v in e.items() if k not in ("created", "sig", "attest", "verified")}, sort_keys=True)
bad, n = [], 0
for w in sorted(set().union(*held.values(), *took.values())):
    machine = w.partition("/")[0]
    views = {"alpha": held["alpha"].get(w, []), "beta": held["beta"].get(w, []),
             "%s's endpoint" % machine: took.get(machine, {}).get(w, [])}
    shape = {s: (len(evs), evs[-1]["seq"] if evs else 0) for s, evs in views.items()}
    if len(set(shape.values())) != 1:
        bad.append("%s: (count, last) %s" % (w, shape))
        continue
    if len({tuple(map(payload, evs)) for evs in views.values()}) != 1:
        bad.append("%s: payloads differ" % w)
    other = "beta" if machine == "alpha" else "alpha"
    if any((e.get("verified") or {}).get("signer", {}).get("name") != machine for e in views[other]):
        bad.append("%s: %s holds an event of it not verified from %s" % (w, other, machine))
    n += shape["alpha"][0]
print("identical: %d writers, %d events" % (len(set().union(*held.values())), n) if not bad else "\n".join(bad))
sys.exit(1 if bad else 0)
PY
y_compare() { SCRIPT_DIR="$SCRIPT_DIR" python3 -B "$T/rl10compare.py" "$YPID" "$YALOG" "$YBLOG" "$YEPA" "$YEPB"; }
y_identical() { rl10_relay "$YEPA" "$YEPB"; y_compare >/dev/null 2>&1; }
y_settle() { # label — wait until the two machines and their endpoints hold the same log
  until_true 400 y_identical || true
  run y_compare
  if [[ "$RC" == 0 ]]; then pass "RL10: $1: identical on alpha, beta, and their endpoints ($OUT)"; else
    fail "RL10: $1: identical on alpha, beta, and their endpoints"; echo "    ${OUT:0:1500}"; fi
}
y_took() { [ -n "$(rl10_up "$1" "$YPID" "$2")" ]; }   # ep-dir text — the endpoint took an event of the project carrying it
y_joined_up() { [ "$(rl10_q "$YEPA" "any(e['kind'] == 'joined' and e['writer'] == 'alpha/$YMA' for c, e in up('$YPID'))")" = true ]; }
until_true 200 y_joined_up || true
y_joined_up && pass "RL10: alpha's uplink opens the project at its endpoint and uploads ma's joined" \
  || fail "RL10: alpha's uplink opens the project at its endpoint and uploads ma's joined"

echo "RL10: a burst on alpha alone:"
says 10 "alpha alone"
CLAUDE_CODE_SESSION_ID=$YMA says 5 "ma alone"
y_alpha_took() { python3 - "$YALOG" "$YEPA" "$YPID" <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["SCRIPT_DIR"])
import endpoint_standin
d, ep, pid = sys.argv[1:4]
took = {}
for a in json.loads(endpoint_standin.ctl_call(ep, "accepted", {"project": pid}))["events"]:
    took.setdefault(a["event"]["writer"], []).append(a["event"]["seq"])
mine = {}
for p in glob.glob(d + "/*.jsonl"):
    evs = [json.loads(l) for l in open(p) if l.strip()]
    mine[evs[0]["writer"]] = [e["seq"] for e in evs]
sys.exit(0 if took == mine else 1)
PY
}
until_true 200 y_alpha_took || true
y_alpha_took && pass "RL10: alpha's writers are at its endpoint, each event once" || fail "RL10: alpha's writers are at its endpoint, each event once"

echo "RL10: beta, fresh, renamed by its endpoint:"
# beta held its sessions as betaold, and its endpoint's first welcome names
# it beta, formerly betaold (`daemon probe`): what alpha reads of it is
# beta's alone.
rl10_as yb betaold
YEPB=$EP
YRB="$T/yb/repo"
cp -R "$YRA" "$YRB"
cd "$YRB"
YMB=6b000001-0000-4000-8000-0000000000b1
YNB=6b000002-0000-4000-8000-0000000000b2
inbox ymb
sleep 600 & YNB_PID=$!
PIDS+=("$YNB_PID")
printf '{"pid":%s,"sessionId":"%s","name":"mb","nameSource":"derived","kind":"bg","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$INBOX_PID" "$YMB" "$YRB" "$T/ymb.sock" > "$HOME/.claude/sessions/mb.json"
printf '{"pid":%s,"sessionId":"%s","name":"nb","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$YNB_PID" "$YNB" "$YRB" > "$HOME/.claude/sessions/nb.json"
printf '[{"id": "mbshort", "sessionId": "%s", "state": "idle"}]\n' "$YMB" > "$STUB_STATE/agents.json"
"$SMINOS" seat add syncproj mb --session "$YMB" >/dev/null
run "$SMINOS" list --json
assert_contains "$OUT" '"machine": "betaold"' "RL10: the seat mb and the session nb join as betaold"
assert_equals "$(find "$YBLOG" -name '*.jsonl' | sed 's|.*/||; s|\..*||' | sort | uniq -c | awk '{print $2 "=" $1}' | tr '\n' ' ')" "betaold=2 " \
  "RL10: beta's log holds its own two writers, and nothing of alpha's"
printf '{"pid":%s,"sessionId":"%s","name":"nb-renamed","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$YNB_PID" "$YNB" "$YRB" > "$HOME/.claude/sessions/nb.json"
run "$SMINOS" daemon tick
assert_equals "$(python3 -c 'import json, sys
print([(e["kind"], e.get("alias") or e.get("state")) for e in map(json.loads, open(sys.argv[1])) if e["kind"] != "joined"])' \
  "$YBLOG/betaold.$YNB.jsonl")" "[('state', 'idle'), ('renamed', 'nb-renamed')]" \
  "RL10: nb's state and its rename to nb-renamed are published under betaold"
Y_ENROLLED="$(python3 -c 'import time; t = time.time(); print(time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime(t)) + "%03dZ" % int(t % 1 * 1000))')"
rl10_serve "\"identity\": {\"org\": \"org-1\", \"hub\": \"http://127.0.0.1:9\", \"name\": \"beta\", \"former\": [\"betaold\"], \"ref\": \"ref-beta\", \"enrolled\": \"$Y_ENROLLED\"}"
run "$SMINOS" daemon probe
assert_contains "$OUT" "welcomed as beta of org org-1: this machine is cut over" "RL10: beta's endpoint welcomes it as beta"
rl10_as yb beta
start_daemon
YB_DAEMON=$DAEMON_PID
y_settle "a fresh machine bootstraps the project from what alpha's endpoint took"
assert_equals "$(rl10_q "$YEPB" "sorted({e['writer'] for c, e in up('$YPID')})")" "[\"beta/$YMB\", \"beta/$YNB\"]" \
  "RL10: beta's endpoint takes the seat and the session that joined as betaold, joined again as beta and only as beta: never a writer of alpha's or of the former name"
assert_equals "$(rl10_q "$YEPB" "[(e['kind'], e.get('alias'), e.get('name_source'), e.get('state')) for c, e in up('$YPID') if e['writer'] == 'beta/$YNB'][:2]")" \
  '[["joined", "nb-renamed", "user", null], ["state", null, null, "idle"]]' \
  "RL10: nb joins again under its name now, nb-renamed, and with its state"
rl10_as ya alpha
cd "$YRA"
run "$SMINOS" list --json
y_members() { printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))'; }
assert_equals "$(y_members)" "[('ma', 'alpha', True), ('mb', 'beta', False), ('nb-renamed', 'beta', False)]" \
  "RL10: alpha sees mb and nb-renamed as beta's members"
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print([r["state"] for r in json.load(sys.stdin) if r["alias"] == "nb-renamed"])')" "['idle']" "RL10: and nb-renamed's state"
assert_equals "$(find "$YALOG" -name 'betaold.*' | wc -l | tr -d ' ')" 0 "RL10: alpha holds no writer of beta's former name"
rl10_as yb beta
cd "$YRB"
run "$SMINOS" list --json
assert_equals "$(y_members)" "[('ma', 'alpha', False), ('mb', 'beta', True), ('nb-renamed', 'beta', True)]" \
  "RL10: beta keeps mb and nb-renamed its own, and sees ma as alpha's"

echo "RL10: a burst on both:"
rl10_as ya alpha
(cd "$YRA" && says 20 "alpha burst" && CLAUDE_CODE_SESSION_ID=$YMA "$SMINOS" say "@mb ping from ma" >/dev/null) & BURST_A=$!
rl10_as yb beta
(cd "$YRB" && says 20 "beta burst" && CLAUDE_CODE_SESSION_ID=$YMB "$SMINOS" say "@ma pong from mb" >/dev/null) & BURST_B=$!
wait "$BURST_A" "$BURST_B"
y_settle "after a burst of say on both"
until_true 200 y_took "$YEPA" "ping from ma" || true
y_took "$YEPA" "ping from ma" && pass "RL10: alpha's endpoint takes ma's say to mb" || fail "RL10: alpha's endpoint takes ma's say to mb"
until_true 200 y_relayed grep -q "ping from ma" "$T/ymb.received" || true
assert_contains "$(cat "$T/ymb.received")" "ping from ma" "RL10: and it reaches mb on beta"
until_true 200 y_took "$YEPB" "pong from mb" || true
y_took "$YEPB" "pong from mb" && pass "RL10: beta's endpoint takes mb's say to ma" || fail "RL10: beta's endpoint takes mb's say to ma"
until_true 200 y_relayed grep -q "pong from mb" "$T/yma.received" || true
assert_contains "$(cat "$T/yma.received")" "pong from mb" "RL10: and it reaches ma on alpha"
assert_equals "$(grep -c "ping from ma" "$T/ymb.received")$(grep -c "pong from mb" "$T/yma.received")" 11 "RL10: each once"

echo "RL10: titles:"
rl10_as ya alpha
YTXA="$HOME/.claude/projects/-syncproj"
mkdir -p "$YTXA"
y_title_rec() { # kind value: one title record into ma's transcript, as the harness appends (and re-appends) it
  printf '{"type":"%s","%s":"%s","sessionId":"%s"}\n' "$1" "$([ "$1" = custom-title ] && echo customTitle || echo aiTitle)" \
    "$2" "$YMA" >> "$YTXA/$YMA.jsonl"
}
y_filler() { printf '{"type":"user","message":{"role":"user","content":"a turn"}}\n' >> "$YTXA/$YMA.jsonl"; }
y_titles() { # [session] → the titles alpha's endpoint took for it (ma's by default), each position once
  rl10_q "$YEPA" "[e['title'] for s, e in sorted({e['seq']: e for c, e in up('$YPID') if e['writer'] == 'alpha/${1:-$YMA}' and e['kind'] == 'titled'}.items())]"; }
y_titles_are() { [ "$(y_titles "${2:-$YMA}")" = "$1" ]; }
y_tick_a() { python3 -c 'import os, sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$T/ya/s/daemon/ticked" 2>/dev/null || true; }
y_tick_moved() { [ "$(y_tick_a)" != "$1" ]; }
y_two_ticks() { local t; t="$(y_tick_a)"; until_true 100 y_tick_moved "$t" || true; t="$(y_tick_a)"; until_true 100 y_tick_moved "$t" || true; }
y_ma_on_beta() { # → ma's in-charge line and its source as beta's list --json carries them
  (rl10_as yb beta && cd "$YRB" && "$SMINOS" list --json) | python3 -c 'import json, sys
print(" / ".join("%s (%s)" % (r["charge"], r["charge_source"]) for r in json.load(sys.stdin) if r["alias"] == "ma"))'
}
y_ma_on_beta_is() { [ "$(y_ma_on_beta)" = "$1" ]; }
for _ in 1 2 3; do y_filler; y_title_rec ai-title "Codex native Computer Use internals"; done
until_true 200 y_titles_are '["Codex native Computer Use internals"]' || true
assert_equals "$(y_titles)" '["Codex native Computer Use internals"]' \
  "RL10: alpha's daemon publishes ma's title once, and its endpoint takes it, though the harness re-appended it"
until_true 200 y_relayed y_ma_on_beta_is "Codex native Computer Use internals (title)" || true
assert_equals "$(y_ma_on_beta)" "Codex native Computer Use internals (title)" \
  "RL10: beta, which holds no transcript of ma, names ma by the title alpha published"
for _ in 1 2 3; do y_filler; y_title_rec custom-title "cua_repl"; y_title_rec ai-title "Codex native Computer Use internals"; done
until_true 200 y_titles_are '["Codex native Computer Use internals", "cua_repl"]' || true
y_two_ticks
for _ in 1 2 3; do y_filler; y_title_rec custom-title "cua_repl"; y_title_rec ai-title "Codex native Computer Use internals"; done
y_two_ticks
assert_equals "$(membership "$YALOG/alpha.$YMA.jsonl")" "joined ['Codex native Computer Use internals', 'cua_repl']" \
  "RL10: a /rename is published as the new title, once: ticks over an unchanged title publish nothing"
assert_equals "$(y_titles)" '["Codex native Computer Use internals", "cua_repl"]' "RL10: and alpha's endpoint takes it once"
until_true 200 y_relayed y_ma_on_beta_is "cua_repl (title)" || true
assert_equals "$(y_ma_on_beta)" "cua_repl (title)" "RL10: and beta names ma by it"
YMA_REC="$(cat "$HOME/.claude/sessions/ma.json")"
y_ma_ends_renamed() { # title
  local t; t="$(y_tick_a)"; until_true 100 y_tick_moved "$t" || true
  y_filler; y_title_rec custom-title "$1"; rm "$HOME/.claude/sessions/ma.json"
}
y_ma_ends_renamed "cua_repl, wrapped up"
until_true 200 y_titles_are '["Codex native Computer Use internals", "cua_repl", "cua_repl, wrapped up"]' || true
assert_equals "$(y_titles)" '["Codex native Computer Use internals", "cua_repl", "cua_repl, wrapped up"]' \
  "RL10: ma renamed and closed between two ticks: alpha publishes the name it ended under, and its endpoint takes it"
until_true 200 y_relayed membership_is "$YBLOG/alpha.$YMA.jsonl" "retired:ended ['Codex native Computer Use internals', 'cua_repl', 'cua_repl, wrapped up']" || true
assert_equals "$(membership "$YBLOG/alpha.$YMA.jsonl")" \
  "retired:ended ['Codex native Computer Use internals', 'cua_repl', 'cua_repl, wrapped up']" \
  "RL10: and beta holds it beside ma's retirement, for a view of ended sessions to name it by"
printf '%s\n' "$YMA_REC" > "$HOME/.claude/sessions/ma.json"
until_true 200 membership_is "$YALOG/alpha.$YMA.jsonl" "joined ['Codex native Computer Use internals', 'cua_repl', 'cua_repl, wrapped up']" || true
y_ma_ends_renamed "cua_repl, round two"
until_true 200 y_titles_are '["Codex native Computer Use internals", "cua_repl", "cua_repl, wrapped up", "cua_repl, round two"]' || true
assert_equals "$(y_titles)" '["Codex native Computer Use internals", "cua_repl", "cua_repl, wrapped up", "cua_repl, round two"]' \
  "RL10: resumed, renamed and closed again between two ticks: that name is published too"
until_true 200 y_relayed membership_is "$YBLOG/alpha.$YMA.jsonl" "retired:ended ['Codex native Computer Use internals', 'cua_repl', 'cua_repl, wrapped up', 'cua_repl, round two']" || true
assert_equals "$(membership "$YBLOG/alpha.$YMA.jsonl")" \
  "retired:ended ['Codex native Computer Use internals', 'cua_repl', 'cua_repl, wrapped up', 'cua_repl, round two']" \
  "RL10: and beta holds that one too"
y_settle "after titles"

echo "RL10: a daemon restart:"
kill "$YA_DAEMON"
set +e; wait "$YA_DAEMON"; set -e
rl10_as ya alpha
(cd "$YRA" && says 5 "alpha while its daemon is down")
# ea joins and ends while no daemon runs here: no daemon ever saw it a member.
YEA=6a000002-0000-4000-8000-0000000000a2
sleep 600 & YEA_PID=$!
PIDS+=("$YEA_PID")
printf '{"type":"ai-title","aiTitle":"Desk sidebar for ended sessions","sessionId":"%s"}\n' "$YEA" > "$YTXA/$YEA.jsonl"
printf '{"pid":%s,"sessionId":"%s","name":"ea","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$YEA_PID" "$YEA" "$YRA" > "$HOME/.claude/sessions/ea.json"
(cd "$YRA" && "$SMINOS" list >/dev/null)
rm "$HOME/.claude/sessions/ea.json"
(cd "$YRA" && "$SMINOS" list >/dev/null)
rl10_as yb beta
(cd "$YRB" && says 5 "beta while alpha's daemon is down")
rl10_as ya alpha
Y_CONNS="$(rl10_q "$YEPA" "d['conns']")"
start_daemon
YA_DAEMON=$DAEMON_PID
y_reconnected() { [ "$(rl10_q "$1" "d['current'] or 0")" -gt "$2" ]; }
until_true 200 y_reconnected "$YEPA" "$Y_CONNS" || true
y_took_ea() { [ "$(rl10_q "$YEPA" "any(e['kind'] == 'titled' and e['writer'] == 'alpha/$YEA' for c, e in up('$YPID'))")" = true ]; }
until_true 200 y_took_ea || true
y_took_ea && pass "RL10: alpha's endpoint takes the title of a session that ended before alpha's daemon started" \
  || fail "RL10: alpha's endpoint takes the title of a session that ended before alpha's daemon started"
until_true 200 y_relayed membership_is "$YBLOG/alpha.$YEA.jsonl" "retired:ended ['Desk sidebar for ended sessions']" || true
y_settle "after alpha's daemon restarts"
assert_equals "$(membership "$YBLOG/alpha.$YEA.jsonl")" "retired:ended ['Desk sidebar for ended sessions']" \
  "RL10: and beta holds it"
assert_equals "$(grep -c "beta while alpha's daemon is down" <<<"$(cat "$YALOG/"beta.*.jsonl)")" 5 \
  "RL10: what beta said while alpha's daemon was down reaches alpha on its new connection, each once"

echo "RL10: a dropped connection:"
Y_CONNS="$(rl10_q "$YEPB" "d['conns']")"
python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$YEPB" drop >/dev/null
rl10_as ya alpha
(cd "$YRA" && says 3 "alpha while beta reconnects")
rl10_as yb beta
(cd "$YRB" && says 3 "beta while it reconnects")
until_true 200 y_reconnected "$YEPB" "$Y_CONNS" || true
y_reconnected "$YEPB" "$Y_CONNS" && pass "RL10: beta reconnects to its endpoint" || fail "RL10: beta reconnects to its endpoint"
y_settle "after beta's connection drops"
assert_equals "$(rl10_q "$YEPB" "[f['have'].get('alpha/$YMA', 0) > 0 for c, f in F if c == d['current'] and f.get('t') == 'hello' and f.get('project') == '$YPID']")" \
  "[true]" "RL10: its new hello says what it holds of alpha's, so only what it lacks is handed again"
assert_equals "$(grep -c "alpha while beta reconnects" <<<"$(cat "$YBLOG/"alpha.*.jsonl)")" 3 "RL10: what alpha said meanwhile reaches beta, each once"

kill "$YA_DAEMON" "$YB_DAEMON"
set +e; wait "$YA_DAEMON" "$YB_DAEMON"; set -e
for side in ya yb; do
  assert_not_contains "$(cat "$T/$side/s/daemon.log")" "Traceback" "RL10: nothing in $side's daemon.log is a traceback"
done
assert_equals "$(test -e "$T/ya/s/daemon/hub.json" || test -e "$T/yb/s/daemon/hub.json"; echo $?)" 1 "RL10: and neither holds a hub.json"
unset MAWS_USER_DATA

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES sync assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) sync assertions FAILED"
  exit 1
fi
