#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# Older sminos copies beside this one, on one machine (the composite's D7;
# T1's M6, and T2's M5, "Older copies, per version"): this code writes a
# store, an older CLI runs its verbs against the same store and the same test
# engine, and this code runs again after it. Each copy is held to what its
# version is expected to do:
#
# - Every copy: no verb of it starts a process for a thread its human opened
#   that the copy did not itself give a seat. The thread here is stopped in
#   `auto`, a thread this code wakes; every verb that can address it is run.
# - 1.27.10, from before threads: T1's expectations. Its first reading verb
#   reconciles the session, which has no process and no seat, to an
#   unstamped `ended`; a tag and `send` naming it are refused as ended, and
#   `resume` and `fill` find no seat; its tick reports what is owed from
#   another machine as `recorded`. This code passes the `ended` by. Accepted
#   and asserted as it is: when it writes the session's delivery record it
#   drops every hold mark (it knows none).
# - 1.51.0, T1's release: a `say` and a `send` of its own to the stopped
#   thread are recorded and marked held, its sender told 1.51's line, and
#   nothing starts; this code's next pass (`daemon tick`) wakes the thread
#   and pushes each once. Accepted and asserted as it is: its tick settles
#   as `recorded` what this code held for a spawned thread (its rule for a
#   seat: no conversation of it here, so no resume); and its refill leaves
#   the record's `waking` naming the displaced session, which this code
#   ignores (T2's §7): it holds nothing for the new occupant, whose message
#   from another machine its daemon's pass delivers, waking it, while that
#   failure's backoff would still hold it, and a sender's own call wakes it.
#
# - 1.52.0, T2's release (CH1's M2 pins it): the cut below, and CH1's M8 cases.
# - Every copy from 1.51.0 on, CH1's M2: a membership change this code began
#   and was cut after its record's write (the record holds the set, where its
#   membership began and the request it answered; the entry owes the
#   statement) is finished by the copy's reading verb, with no step of its
#   own: the statement appended once, the record's keys as written. 1.27.10,
#   which has no journal, finishes nothing, and this code's next verb does.
#
# - Every copy, CH1's M8, over a store this code gave channels (through its own functions, the machine not
#   being enrolled: the channel registered as the org's directory registers it, the thread placed in it by a
#   request of this machine's person, its statement answering it, and a channel-env of its own): its `list`,
#   `list --json`, tagged `say`, `send` and `daemon tick` exit and print what they do over the same store
#   without channels (normalised: ids, paths, times), launch as they did, land and fare as they did (each message
#   in the log it went to, the thread's delivery record, the outcomes, what the engine's inbox took: 1.27 refuses
#   both, 1.51 holds both, 1.52 wakes the thread and pushes each once), and leave the record's set, positions
#   and answer as written; its tick reconciles the channel as a project with no member, and its `projects`
#   lists it as one, where this code's lists none. A `joined` the copy writes for the session (1.27's, once its
#   human reopens it) is followed at this code's next reconciliation by a statement of the same set; so is a
#   return's, after an end over which the channel's log gained an event: 1.51's and 1.52's return leaves where
#   the membership began as it was before the end (accepted), 1.27 returns nothing and this code's writes it
#   anew. Accepted and asserted as it is: 1.51's and 1.52's `list --json` of a spawned thread in a channel shows
#   its seat's `began` and `answered` and hides its `channels`. Then the copy's `join <channel id>` by hand from
#   the running session: this code's next reconciliation, while the session runs or once it runs again (closed
#   in between, it is listed in neither), leaves it a member of its one project with its set as it was and a
#   `retired` `moved` in the channel's log; and an uplink run on that store (older_channel_wire.py, the store
#   enrolled then) is clean by channel_wire.py, baselined on the store as the older copy left it: the older
#   `joined` uploaded in its place, this code's `retired` after it (the order the stand-in first received them,
#   across frames and within one), and nothing else of this code's. 1.52.0 has
#   no every-copy case (it wakes the thread its human opened, as this code does): over channels it is held to
#   what it does without them.
#
#   test-older-cli.sh [--older <path to an older sminos launcher>]
#
# The two pinned copies are revisions of this repository, extracted by `git
# archive`, each fetched from `origin` by its id when the clone lacks it (the
# gates check out one commit, shallow); when one cannot be had the script
# fails, never passing on a line saying it was skipped. `--older` adds a third
# copy (one in a plugin cache, say), run after them with the expectations of
# the version its plugin says (`<plugin>/.claude-plugin/plugin.json`, the
# launcher being `<plugin>/skills/sminos/scripts/sminos`): 1.27.x as 1.27.10,
# 1.51.x as 1.51.0, 1.52.x as 1.52.0, any other with the every-copy
# expectation alone.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per case; `claude` is
# a stand-in that logs every call with the copy that made it and hands it to
# the test engine (wake_engine.py); the machine is not enrolled.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"
ENGINE="$SCRIPT_DIR/wake_engine.py"
REV_1_27=aefb80aa55bb8d95c47341ca21051ba244e103dd   # sminos 1.27.10
REV_1_51=0387f2b794167fae12113f9ff654c3743e4dcfc7   # sminos 1.51.0, the merge that released it
REV_1_52=f051d4f2a28615d7b3517963aed0ac68233435fb   # sminos 1.52.0, the merge that released it

THIRD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --older) [ $# -ge 2 ] || { echo "FAIL --older needs a launcher"; exit 1; }; THIRD="$2"; shift 2 ;;
    *) THIRD="$1"; shift ;;   # T1's positional form
  esac
done

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smo.XXXXXX)"
T="$(cd "$T" && pwd -P)"
PIDS=()
ENGINES=()
cleanup() {
  for st in ${ENGINES[@]+"${ENGINES[@]}"}; do
    python3 -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import wake_engine; wake_engine.stop_all(sys.argv[2])' \
      "$SCRIPT_DIR" "$st" 2>/dev/null || true
  done
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
run() { # command... — OUT (stdout and stderr) and RC of the command, run in the repository
  set +e; OUT="$(cd "$REPO" && "$@" 2>&1)"; RC=$?; set -e
}
older() { # verb... — the older copy's verb, its calls to the engine logged as the older copy's (a --wait ends in 10 s)
  run env STUB_WHO=older DAEMON_TIMEOUT=10 "$OLDER" "$@"
}
py() { python3 -B -c "$@"; }

# ---- the older copies ---------------------------------------------------------
if [ -n "$THIRD" ]; then
  [ -x "$THIRD" ] || { echo "FAIL the older sminos launcher $THIRD is not an executable file"; exit 1; }
  THIRD="$(cd "$(dirname "$THIRD")" && pwd)/$(basename "$THIRD")"   # each verb runs in the case's repository
fi
TOP="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
version_of() { # launcher — the version its plugin.json says
  py 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' \
    "$(dirname "$1")/../../../.claude-plugin/plugin.json" 2>/dev/null || echo unknown
}
pinned() { # revision version — the launcher of that revision's sminos, extracted under $T
  local rev="$1" want="$2" dest="$T/copy-$2"
  if ! git -C "$TOP" cat-file -e "$rev^{commit}" 2>/dev/null \
      && ! git -C "$TOP" fetch -q --depth=1 origin "$rev"; then
    echo "FAIL sminos $want (revision ${rev:0:8}) cannot be had from this clone or from origin" >&2
    exit 1
  fi
  mkdir -p "$dest"
  git -C "$TOP" archive "$rev" sminos | tar -x -C "$dest"
  local got
  got="$(version_of "$dest/sminos/skills/sminos/scripts/sminos")"
  [ "$got" = "$want" ] || { echo "FAIL revision ${rev:0:8} is sminos $got, not $want" >&2; exit 1; }
  echo "$dest/sminos/skills/sminos/scripts/sminos"
}
COPY_1_27="$(pinned "$REV_1_27" 1.27.10)"
COPY_1_51="$(pinned "$REV_1_51" 1.51.0)"
COPY_1_52="$(pinned "$REV_1_52" 1.52.0)"

# ---- the stand-in engine, first on PATH -------------------------------------------
unset CLAUDE_CODE_SESSION_ID CLAUDE_PID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME CLAUDE_PLUGIN_ROOT \
  CLAUDE_PROJECT_DIR CLAUDE_CONFIG_DIR
export DAEMON_HOST=alpha DAEMON_BOOT_ID=boot-current SMINOS_DERIVE_EVERY=0 WAKE_ENGINE="$ENGINE"
mkdir -p "$T/bin"
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
# The engine for this file: every call logged with the copy that made it, then the test engine's.
printf '%s %s\n' "${STUB_WHO:-this}" "$*" >> "$STUB_STATE/calls"
exec python3 -B "$WAKE_ENGINE" "$@"
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"
[ "$(command -v claude)" = "$T/bin/claude" ] || { echo "FAIL claude on PATH is $(command -v claude), not the stand-in"; exit 1; }

# ---- one machine per case: a store, an engine, a repository ------------------------
fresh() { # name — a new HOME, SMINOS_HOME, engine state and repository for one case
  local b="$T/case-$1"
  export HOME="$b/home" SMINOS_HOME="$b/s" STUB_STATE="$b/stub" WAKE_ENGINE_STATE="$b/engine"
  ENGINES+=("$WAKE_ENGINE_STATE")
  mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME/daemon" "$STUB_STATE" "$WAKE_ENGINE_STATE"
  # The machine's ceiling admits `auto`, so that a wake is decided by the thread's own last turn.
  printf '{"ceiling": "auto"}\n' > "$SMINOS_HOME/daemon/policy.json"
  REPO="$b/repo"
  git -c init.defaultBranch=main init -q "$REPO"
  py 'import json, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": "olderproj", "remote": "", "hub": {"org": "org-1"}}))' \
    > "$REPO/.smns"
  PROJECT="$(py 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$REPO/.smns")"
  SID="$(py 'import uuid; print(uuid.uuid4())')"
  TX="$HOME/.claude/projects/p-$SID/$SID.jsonl"
  mkdir -p "$(dirname "$TX")"
}
last_turn() { # mode — the session's transcript, its last turn in that mode
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","permissionMode":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
    "${SID:0:8}" "$SID" "$REPO" "$1" > "$TX"
}
opened() { # the session run by a process of its human's terminal (a `sleep`), named keeper by them
  sleep 600 & PIDS+=("$!")
  printf '{"pid":%s,"sessionId":"%s","name":"keeper","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
    "$!" "$SID" "$REPO" > "$HOME/.claude/sessions/keeper.json"
}
closed() { # its terminal closed
  local last="${PIDS[$((${#PIDS[@]} - 1))]}"   # bash 3.2, macOS's /bin/bash, has no negative subscript
  kill "$last"; wait "$last" 2>/dev/null || true
  rm -f "$HOME/.claude/sessions/keeper.json"
}
stopped_thread() { # mode — this code's member keeper, its human-opened thread, stopped with its last turn in mode
  last_turn "$1"
  opened
  run "$SMINOS" list
  assert_contains "$OUT" "keeper [${SID:0:8}]" "the session its human opened is a member"
  THREAD="$(row thread)"
  assert_equals "$(row opened)" human "it is a thread its human opened"
  closed
  for sweep in 1 2; do
    run "$SMINOS" daemon tick
    assert_equals "$RC" 0 "this code's sweep $sweep runs"
  done
  assert_equals "$(row state)" stopped "two sweeps after its terminal closed it is stopped"
}
# The session's own events, one line each: writer seq kind reason stamped
own_events() {
  cat "$SMINOS_HOME/projects/$PROJECT/log/"*.jsonl | py 'import json, sys
for line in sys.stdin:
    e = json.loads(line)
    if e.get("session") == sys.argv[1] and e.get("kind") in ("joined", "retired"):
        print(e["kind"], e.get("reason", "-"), "stamped" if isinstance(e.get("thread"), str) and e["thread"] else "unstamped")' "$SID"
}
row() { # field [session] — the session's row in this code's `list --stopped --json`, one field
  (cd "$REPO" && "$SMINOS" list --stopped --json 2>/dev/null) | py 'import json, sys
rows = [m for m in json.load(sys.stdin) if m["session"] == sys.argv[1]]
print(rows[0][sys.argv[2]] if rows else "<no row>")' "${2:-$SID}" "$1"
}
calls() { # who — the engine calls that copy made ("this" or "older")
  { grep "^$1 " "$STUB_STATE/calls" 2>/dev/null || true; } | cut -d' ' -f2-
}
launches() { cat "$WAKE_ENGINE_STATE/launches" 2>/dev/null || echo 0; }
violations() { cat "$WAKE_ENGINE_STATE/violations" 2>/dev/null || true; }
marks() { # [session] — the hold marks of its delivery record: "<writer> <seq> <the thread it names>", one a line
  py 'import json, sys
try:
    rec = json.load(open(sys.argv[1]))
except OSError:
    rec = {}
for w, d in sorted(rec.items()):
    for seq, t in sorted((d.get("held") if isinstance(d, dict) else None) or []):
        print(w, seq, t)' "$SMINOS_HOME/projects/$PROJECT/delivered/${1:-$SID}.json"
}
settled() { # writer [session] — that writer's settled prefix in the session's delivery record
  py 'import json, sys
try:
    rec = json.load(open(sys.argv[1]))
except OSError:
    rec = {}
print((rec.get(sys.argv[2]) or {}).get("settled", 0))' "$SMINOS_HOME/projects/$PROJECT/delivered/${2:-$SID}.json" "$1"
}
frames() { # session — what the engine's inbox took for it: each line of a frame that quotes this file's texts, its tag off
  py 'import json, re, sys
try:
    lines = open(sys.argv[1]).read().splitlines()
except OSError:
    lines = []
for line in lines:
    for text in json.loads(line)["message"]["content"].splitlines() if line.strip() else ():
        if "from the older" in text or "for the seat" in text or "from this code" in text or "from beta" in text:
            print(re.sub(r"^@\S+ ", "", text))' "$WAKE_ENGINE_STATE/inputs/$1"
}
human_line() { # the outside event a person on another machine wrote to keeper
  printf '{"ts":"%s","writer":"beta/human","seq":1,"kind":"human","from":"human","to":[{"session":"%s","alias":"keeper"}],"text":"@keeper hello from beta"}\n' \
    "$(py 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')" \
    "$SID" > "$SMINOS_HOME/projects/$PROJECT/log/beta.human.jsonl"
}
older_launches() { calls older | grep -c -e '--bg' || true; }
hold_of() { # session — this code's hold of it, as a view reads it and as a push asks it last: "[<hold_of>] [<hold_now>]",
  # a failed wake's backoff an hour (SMINOS_WAKE_RETRY), so a failure read as the session's own holds it `failed`
  (cd "$REPO" && SMINOS_WAKE_RETRY=3600 SMINOS_WAKE_RETRY_MAX=3600 python3 -B -c 'import sys
sys.path.insert(0, sys.argv[1])
import sminos
t = sminos.threads_module()
print("[%s] [%s]" % (t.hold_of(sys.argv[2]), t.hold_now(sys.argv[2])))' "$SCRIPTS" "$1")
}
seat_field() { # seat field — one field of the seat's record in the seat store, as JSON
  py 'import json, sys; print(json.dumps(json.load(open(sys.argv[1])).get(sys.argv[2]), sort_keys=True))' \
    "$SMINOS_HOME/$1.json" "$2"
}
# 1.51.0's line to a sender for a message to a held session (its `held_line`, as that release has it).
HELD_1_51="recorded and held: the session is stopped, and a session its human opened is not woken; it is pushed only if its human reopens the session before it ends (three days stopped, or a retire), else it stays in the log"

# ---- every copy: nothing started for a thread its human opened ------------------------
# The thread is stopped with its last turn in `auto`, so this code would wake it; the older copy runs every verb
# that can address it. A copy's own seat over the session (`seat add --session`) and its resume are D7's accepted
# degradation, and are not run.
every_copy() { # case — the verbs, their outputs kept for the version's own case (SAY_*, SEND_*, …)
  fresh "$1"
  stopped_thread auto
  older say "@keeper hello from the older say"; SAY_RC=$RC; SAY_OUT="$OUT"
  older send keeper "a send from the older copy"; SEND_RC=$RC; SEND_OUT="$OUT"
  older resume keeper "a resume from the older copy"; RESUME_RC=$RC; RESUME_OUT="$OUT"
  older fill --resume keeper "a fill --resume from the older copy"; FILLR_RC=$RC; FILLR_OUT="$OUT"
  older send --wait keeper "a wait from the older copy"; WAIT_RC=$RC; WAIT_OUT="$OUT"
  older fill keeper "a fill from the older copy"; FILL_RC=$RC; FILL_OUT="$OUT"
  older daemon tick
  assert_equals "$RC" 0 "its daemon tick runs"
  assert_equals "$(older_launches)" 0 "no verb of the older copy launched anything"
  assert_equals "$(launches)" 0 "the engine started no process"
  assert_equals "$(violations)" "" "and no resume carried a message"
}

# ---- 1.27.10, from before threads (T1's case) --------------------------------------
case_1_27() {
  every_copy "$1-every"
  fresh "$1"
  # Its last turn in `plan` mode (T2's M3): this code holds it for `mode`, so T1's expectations of the older copy
  # stand; a thread this code wakes is every_copy's.
  echo " this code makes the thread, stops it, holds a message:"
  stopped_thread plan
  run "$SMINOS" say "@keeper hello from this code"
  assert_equals "$RC" 0 "its say exits 0"
  assert_contains "$OUT" "recorded and held" "a message to it is recorded and held"
  human_line   # a person's words from another machine, as that machine's log reaches this one
  BEFORE="$(own_events)"
  assert_equals "$BEFORE" "joined - stamped" "its one membership event is a stamped joined"
  assert_equals "$(marks)" "alpha/human 1 $THREAD" "this code marked its own message held for the thread"

  echo " the older CLI over the same store:"
  assert_equals "$(calls this)" "" "this code asked the engine nothing"
  older list
  assert_equals "$RC" 0 "its list runs"
  assert_contains "$OUT" "(no members in olderproj)" "its list shows no member: a closed session it does not know as a thread"
  assert_equals "$(own_events)" "$(printf 'joined - stamped\nretired ended unstamped')" \
    "its first reading verb reconciled the session to an unstamped ended"
  older say "@keeper hello from the older code"
  assert_equals "$RC" 4 "its tagged say is refused (exit 4)"
  assert_contains "$OUT" "session ended" "it says the session ended"
  older send keeper "a send from the older code"
  assert_equals "$RC" 4 "its send is refused (exit 4)"
  assert_contains "$OUT" "keeper: keeper's session ended" "it says the session ended"
  older resume keeper "a resume from the older code"
  assert_equals "$RC" 4 "its resume finds no seat (exit 4)"
  assert_contains "$OUT" "no seat matching 'keeper'" "it says there is no seat"
  older fill keeper "a fill from the older code"
  assert_equals "$RC" 4 "its fill finds no seat (exit 4)"
  assert_contains "$OUT" "no seat matching 'keeper'" "it says there is no seat"
  older fill --resume keeper "a fill --resume from the older code"
  assert_equals "$RC" 4 "its fill --resume finds no seat (exit 4)"
  assert_contains "$OUT" "no seat matching 'keeper'" "it says there is no seat"
  older daemon tick
  assert_equals "$RC" 0 "its daemon tick runs"
  assert_contains "$OUT" "delivered 0" "its tick delivers nothing"
  OUTBOX="$(cat "$SMINOS_HOME/projects/$PROJECT/outcomes.jsonl" 2>/dev/null || true)"
  assert_contains "$OUTBOX" '"writer": "beta/human", "seq": 1}, "session": "'"$SID"'", "outcome": "recorded"' \
    "its tick reports the message from another machine as recorded"
  assert_equals "$(calls older)" "" "no verb of the older CLI called the engine: nothing resumed or started"
  # The boundary: the older CLI's last verb has run, this code has made no call yet.
  BOUNDARY="$(own_events)"
  assert_equals "$BOUNDARY" "$(printf 'joined - stamped\nretired ended unstamped')" \
    "at the boundary: this code's stamped joined, then the older copy's unstamped ended, and nothing else"

  echo " this code after the older CLI:"
  assert_equals "$(row state)" stopped "list --stopped still shows it stopped"
  assert_equals "$(row thread)" "$THREAD" "under the same thread"
  run "$SMINOS" daemon owed
  assert_equals "$RC" 0 "daemon owed exits 0: what is held is no debt"
  assert_contains "$OUT" "closed sessions 2" "both messages are still held for it: the older tick settled nothing"
  run "$SMINOS" list
  assert_equals "$RC" 0 "this code's list runs"
  assert_equals "$(own_events)" "$BOUNDARY" "this code's reads wrote nothing over the older copy's ended: no repair joined"
  run "$SMINOS" daemon tick
  assert_equals "$RC" 0 "this code's tick runs"
  assert_equals "$(own_events)" "$BOUNDARY" "nor did its tick: the older ended is passed by"
  assert_equals "$(marks)" "$(printf 'alpha/human 1 %s\nbeta/human 1 %s' "$THREAD" "$THREAD")" \
    "and it marked the message from another machine held too"
  opened
  run "$SMINOS" list
  assert_contains "$OUT" "keeper [${SID:0:8}]" "reopened by its human, it is live as keeper"
  assert_equals "$(row thread)" "$THREAD" "the same thread"
  assert_equals "$(calls this)" "" "and nothing called the engine: nothing resumed it but its human"

  # Accepted (D7) and asserted as it is: a copy before 1.51.0 rewrites the delivery record from its own load,
  # which knows no hold. Its pass over the session reopened with no inbox yet settles both held messages unpushed,
  # every mark with them; the session reads them in the chat (TECH-DEBT, "An older copy's delivery write drops
  # held marks").
  echo " the older CLI over the reopened session:"
  older daemon tick
  assert_equals "$RC" 0 "its daemon tick runs"
  assert_equals "$(marks)" "" "its delivery write dropped every mark"
  assert_equals "$(settled alpha/human) $(settled beta/human)" "1 1" "and settled both messages"
  assert_equals "$(frames "$SID")" "" "pushing neither"
  assert_equals "$(calls older)$(launches)" "0" "and it started nothing"
}

# ---- 1.51.0, T1's release ------------------------------------------------------------
case_1_51() {
  every_copy "$1-every"
  echo " its own messages to the thread, which this code wakes:"
  assert_equals "$SAY_RC $SEND_RC" "0 0" "its tagged say and its send exit 0"
  assert_contains "$SAY_OUT" "keeper: $HELD_1_51" "its say is recorded and held, told in 1.51's words"
  assert_contains "$SEND_OUT" "for keeper: $HELD_1_51" "its send is recorded and held, told in 1.51's words"
  assert_equals "$RESUME_RC $FILLR_RC $WAIT_RC" "4 4 4" "its resume, fill --resume and send --wait exit 4"
  for out in "$RESUME_OUT" "$FILLR_OUT" "$WAIT_OUT"; do
    assert_contains "$out" "nothing was started: keeper is a session its human opened" "it says nothing was started"
    assert_contains "$out" "for keeper: $HELD_1_51" "and the message is recorded and held"
  done
  assert_equals "$FILL_RC" 4 "its fresh fill is refused (exit 4)"
  assert_contains "$FILL_OUT" "a fresh fill of it is refused, and nothing was recorded" "recording nothing"
  assert_equals "$(marks | cut -d' ' -f1,2 | tr '\n' ' ')" "alpha/human 1 alpha/human 2 alpha/human 3 alpha/human 4 alpha/human 5 " \
    "each of its five messages is marked held"
  assert_equals "$(marks | cut -d' ' -f3 | sort -u)" "$THREAD" "for the thread"
  ALL="$(printf '%s\n' "hello from the older say" "a send from the older copy" "a resume from the older copy" \
    "a fill --resume from the older copy" "a wait from the older copy")"
  run "$SMINOS" daemon tick
  assert_equals "$RC" 0 "this code's next pass runs"
  assert_contains "$OUT" "delivered 5 to keeper" "and delivers the five"
  assert_equals "$(launches)" 1 "waking the thread once"
  assert_contains "$(calls this)" "--bg --resume $SID --permission-mode auto" "under its own id, in its last turn's mode"
  assert_equals "$(frames "$SID")" "$ALL" "each message pushed once, in its order"
  assert_equals "$(marks)" "" "no mark is left"
  assert_equals "$(settled alpha/human)" 5 "and every one is settled"
  run "$SMINOS" daemon tick
  assert_equals "$(launches) $(frames "$SID")" "1 $ALL" "a second pass wakes nothing and pushes nothing again"
  assert_equals "$(violations)" "" "no resume carried a message"

  fresh "$1-seat"
  echo " a thread this code spawned:"
  run "$SMINOS" spawn seata "for the seat task"
  assert_equals "$RC" 0 "this code spawns seata"
  SEAT="$(printf '%s' "$OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p')"
  run env STUB_WHO=test claude stop "${SEAT:0:8}"
  assert_equals "$(row state "$SEAT")" stopped "its process stopped, it is stopped"
  # (a) Accepted and asserted as it is: what this code held for a seat, 1.51.0's pass settles `recorded`. Its rule
  # for a seat keeps no hold (only a thread its human opened is held), and a seat with no conversation here is not
  # resumed: it is settled with a warning, pushed to nothing.
  STX="$(ls "$HOME"/.claude/projects/*/"$SEAT".jsonl)"
  mv "$STX" "$STX.aside"
  run "$SMINOS" say "@seata for the seat, its conversation gone"
  assert_contains "$OUT" "seata: recorded and held: the session is stopped and is not woken: no conversation of it is on that machine" \
    "this code holds a message for it, its conversation gone"
  assert_equals "$(marks "$SEAT")" "alpha/human 1 $SEAT" "marked held for the seat's thread"
  older daemon tick
  assert_equals "$RC" 0 "the older copy's daemon tick runs"
  assert_contains "$OUT" "seata is gone — no transcript for its session on this machine" "it finds the seat gone"
  assert_equals "$(marks "$SEAT") $(settled alpha/human "$SEAT")" " 1" "and settles the held message, its mark dropped"
  assert_equals "$(launches) $(older_launches) $(frames "$SEAT")" "1 0 " "starting nothing, pushing nothing"
  mv "$STX.aside" "$STX"

  # (c) Accepted and asserted as it is: a refill by 1.51.0 keeps the record's unknown keys, so `waking` names the
  # session it displaced; this code reads the field only for the record's current session (§7).
  touch "$WAKE_ENGINE_STATE/fail-job"
  run "$SMINOS" say "@seata for the seat, a wake that fails"
  rm "$WAKE_ENGINE_STATE/fail-job"
  assert_contains "$OUT" "waking it failed, and its machine tries again" "this code's wake of it fails, held"
  assert_equals "$(seat_field "$SEAT" waking | py 'import json, sys; w = json.load(sys.stdin); print(w["session"], w["failed"])')" \
    "$SEAT 1" "the record's waking counts the failure for its session"
  older fill seata "for the seat, a refill by the older copy"
  assert_equals "$RC" 0 "the older copy refills the seat"
  NEW="$(seat_field "$SEAT" current | tr -d '"')"
  assert_not_contains "$NEW" "$SEAT" "with a session of its own"
  assert_equals "$(seat_field "$SEAT" waking | py 'import json, sys; w = json.load(sys.stdin); print(w["session"], w["failed"])')" \
    "$SEAT 1" "its record keeps the waking, naming the session it displaced"
  run env STUB_WHO=test claude stop "${NEW:0:8}"
  assert_equals "$(row state "$NEW")" stopped "the new occupant's process stopped, it is stopped"
  # Before anything is sent, and by the daemon, which follows the schedule (a sender's own call passes over a
  # failed wake's backoff, §4): the displaced session's failure, an hour from due, read as the new occupant's
  # would hold it `failed`.
  assert_equals "$(hold_of "$NEW")" "[] []" "this code holds nothing for the new occupant: the waking names another session"
  printf '{"ts":"%s","writer":"beta/human","seq":1,"kind":"human","from":"human","to":[{"session":"%s","alias":"seata"}],"text":"@seata for the seat from beta"}\n' \
    "$(py 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')" \
    "$NEW" > "$SMINOS_HOME/projects/$PROJECT/log/beta.human.jsonl"
  BEFORE_TICK="$(launches)"
  run env SMINOS_WAKE_RETRY=3600 SMINOS_WAKE_RETRY_MAX=3600 "$SMINOS" daemon tick
  assert_equals "$RC" 0 "this code's tick runs, a failed wake's backoff an hour"
  assert_contains "$OUT" "delivered 1 to seata" "and delivers the message from another machine to the new occupant"
  assert_equals "$(( $(launches) - BEFORE_TICK ))" 1 "waking it once"
  assert_equals "$(frames "$NEW")" "for the seat from beta" "the new occupant takes it once"
  assert_contains "$(cat "$SMINOS_HOME/projects/$PROJECT/outcomes.jsonl")" \
    '"writer": "beta/human", "seq": 1}, "session": "'"$NEW"'", "outcome": "delivered"' "its outcome delivered"
  assert_equals "$(seat_field "$SEAT" waking)" null "the waking it ignored is gone once its own wake is done"
  run env STUB_WHO=test claude stop "${NEW:0:8}"
  assert_equals "$(row state "$NEW")" stopped "stopped again"
  run "$SMINOS" say "@seata for the seat, after the refill"
  assert_equals "$RC" 0 "this code's say to it exits 0"
  assert_contains "$OUT" "seata: sent (woken)" "woken at once: the displaced session's failure holds nothing"
  assert_equals "$(frames "$NEW")" "$(printf '%s\n' "for the seat from beta" "for the seat, after the refill")" \
    "the new occupant takes each message once, and not what was held for the session it displaced"
  assert_equals "$(seat_field "$SEAT" waking)" null "nor does a wake leave one"
  assert_equals "$(violations)" "" "no resume carried a message"
}

# ---- a membership change cut after its record's write (CH1's M2) ---------------------
CHANNEL=5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c   # a declared channel's id, registered here with no root
here_py() { # code args... — python run with this code's modules
  python3 -B -c "import sys; sys.path.insert(0, sys.argv[1]); $1" "$SCRIPTS" "${@:2}"
}
statements() { # the session's statements in the project's log: "<op> <channels joined by ,>", one a line
  cat "$SMINOS_HOME/projects/$PROJECT/log/"*.jsonl | py 'import json, sys
for line in sys.stdin:
    e = json.loads(line)
    if e.get("session") == sys.argv[1] and e.get("kind") == "channels":
        print(e.get("op"), ",".join(e["channels"]))' "$SID"
}
record_keys() { # the thread's record: its set, positions, answered requests and open entry's op, as one JSON line
  py 'import json, sys
r = json.load(open(sys.argv[1]))
print(json.dumps([r.get("channels"), r.get("began"), [a[:2] for a in r.get("answered") or []],
                  (r.get("pending") or {}).get("op")], sort_keys=True))' "$SMINOS_HOME/threads/$THREAD.json"
}
cut_finished() { # label — the cut, the older copy's reading verb, and this code after it
  fresh "$1-cut"
  echo " a membership change this code began, cut after its record's write:"
  opened
  run "$SMINOS" list
  assert_contains "$OUT" "keeper [${SID:0:8}]" "a live session its human opened is a member"
  THREAD="$(row thread)"
  # The channel's log holds two other writers' events; the change places the thread in it, answering a request.
  ENTRY="$(here_py 'import sminos, sminos_threads as threads
cid, sid, tid, pid = sys.argv[2:6]
sminos.register_if_absent(sminos.make_project(cid, "desk-integration", "", "", None))
c = sminos.known_project(cid)
for w in ("beta/human", "beta/human", "gamma/6b000001-0000-4000-8000-0000000000b1"):
    sminos.log_append(c, w, "channel-env", op="add", machine="beta", thread="x")
answer = {"channel": cid, "id": "req-1", "ts": sminos.now(ms=True), "result": "applied", "reason": None}
entry = threads.set_channels(tid, lambda rec: {"project": sminos.known_project(pid), "session": sid,
                                               "channels": [cid], "answer": answer})
print(entry["id"])' "$CHANNEL" "$SID" "$THREAD" "$PROJECT")"
  WRITTEN='[["'"$CHANNEL"'"], {"'"$CHANNEL"'": {"beta/human": 2, "gamma/6b000001-0000-4000-8000-0000000000b1": 1}}, [["'"$CHANNEL"'", "req-1"]], '
  assert_equals "$(record_keys)" "${WRITTEN}\"channels\"]" "the record holds the set, its positions and the answer, its entry open"
  assert_equals "$(statements)" "" "and nothing is stated yet"
  older list
  assert_equals "$RC" 0 "the older copy's list runs"
  case "$(version_of "$OLDER")" in
    1.27.*)
      assert_equals "$(statements)" "" "1.27, with no journal, finishes nothing"
      assert_equals "$(record_keys)" "${WRITTEN}\"channels\"]" "and leaves the record as it was"
      run "$SMINOS" list
      assert_equals "$RC" 0 "this code's next verb runs" ;;
  esac
  assert_equals "$(statements)" "$ENTRY $CHANNEL" "the statement appended once, under the entry's id"
  assert_equals "$(record_keys)" "${WRITTEN}null]" "the entry cleared, the record's set, positions and answer as written"
  run "$SMINOS" list
  run "$SMINOS" daemon tick
  assert_equals "$(statements)" "$ENTRY $CHANNEL" "this code's reads and tick state nothing again"
  assert_equals "$(here_py 'import sminos, sminos_channels as ch
sid, tid, cid = sys.argv[2:5]
p = sminos.resolve_project(sys.argv[5])
row = next(m for m in sminos.view_of(p).members if m.session == sid)
print(" ".join(row.channels), "|", " ".join(ch.channels_of(sid)), "|", sorted(ch.began_of(tid, cid).items()))' \
    "$SID" "$THREAD" "$CHANNEL" "$REPO")" \
    "$CHANNEL | $CHANNEL | [('beta/human', 2), ('gamma/6b000001-0000-4000-8000-0000000000b1', 1)]" \
    "this code reads the log stating the set, and the record's set and positions"
  assert_equals "$(launches)" 0 "and nothing started"
  closed
}

# ---- a store with channels, per copy (CH1's M8) ----------------------------------------
HUB_JSON='{"url": "http://127.0.0.1:9", "org": "org-1"}'   # the org's hub, as its directory registers a log
REQUEST=00000000000000000000000000000001   # a request this machine's person wrote for keeper, answered
with_channels() { # what this code's verbs write, through its own functions (the machine is not enrolled, so
  # `channel create` is refused here): the channel registered as the org's directory registers a log, the thread
  # placed in it by a request of this machine's person (its statement answering it), and a channel-env of its own
  here_py 'import json, sminos, sminos_channels as ch, sminos_threads as threads
cid, sid, tid, pid, rid, hub = sys.argv[2:8]
sminos.register_if_absent(sminos.make_project(cid, "desk-integration", "", "", json.loads(hub)))
sminos.forget_caches()
c, p = sminos.known_project(cid), sminos.known_project(pid)
req = sminos.log_append(c, "%s/human" % sminos.machine_name_now(), "channel-request", op="add", session=sid, thread=tid, id=rid)
answer = {"channel": cid, "id": rid, "ts": req["ts"], "result": "applied", "reason": None}
entry = threads.set_channels(tid, lambda rec: {"project": p, "session": sid, "channels": [cid], "answer": answer})
assert entry is not None and sminos.finish_thread(tid, project=p), entry
writer, aud = sminos.own_stream(c, sid)
sminos.log_append(c, writer, "channel-env", op="add", machine="beta", thread=tid)' \
    "$CHANNEL" "$SID" "$THREAD" "$PROJECT" "$REQUEST" "$HUB_JSON"
}
normal() { # text — a verb's output with what differs between two cases of one shape put as names
  py 'import re, sys
text, subs = sys.stdin.read(), sys.argv[1:]
for value, name in zip(subs[::2], subs[1::2]):
    if value:
        text = text.replace(value, name)
text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z?", "<ts>", text)
text = re.sub(r"\b\d+(\.\d+)?[smhd]\b", "<age>", text)
sys.stdout.write(text)' "$SID" "<sid>" "${SID:0:8}" "<short>" "$THREAD" "<thread>" "${THREAD:0:8}" "<tshort>" \
    "$PROJECT" "<project>" "${PROJECT:0:8}" "<pshort>" "$CHANNEL" "<channel>" "$REPO" "<repo>" "$(dirname "$HOME")" "<case>" <<<"$1"
}
older_over() { # the older copy's verbs over the case's store: VERBS, each one's exit and output, normalised,
  # its tick's line for the channel, the channel's own, apart in TICK_CHANNEL; with KEYS set, the thread record's
  # keys asserted as they were after each verb
  VERBS="" TICK_CHANNEL=""
  local label out
  for label in list list-json say send tick; do
    case "$label" in
      list) older list ;;
      list-json) older list --json ;;
      say) older say "@keeper hello from the older say" ;;
      send) older send keeper "a send from the older copy" ;;
      tick) older daemon tick ;;
    esac
    out="$(normal "$OUT")"
    if [ "$label" = tick ]; then
      TICK_CHANNEL="$(grep '^desk-integration: ' <<<"$out" || true)"
      out="$(grep -v '^desk-integration: ' <<<"$out" || true)"
    fi
    VERBS="$VERBS== $label $RC
$out
"
    [ -z "${KEYS:-}" ] || assert_equals "$(record_keys)" "$KEYS" "after its $label the record's set, positions and answer are as written"
  done
  VERBS="$VERBS== launches $(launches) $(older_launches)
== delivery
$(normal "$(delivery)")"
}
delivery() { # what became of the older copy's say and send: each message in the log it landed in (its writer, kind
  # and recipients), the thread's delivery record there (held marks, settled prefixes), the outcomes, and what the
  # engine's inbox took for the session
  py 'import glob, json, os, sys
home, sid = sys.argv[1], sys.argv[2]
for log in sorted(glob.glob(os.path.join(home, "projects", "*", "log"))):
    pid = os.path.basename(os.path.dirname(log))
    for path in sorted(glob.glob(os.path.join(log, "*.jsonl"))):
        for line in open(path):
            e = json.loads(line)
            if "from the older" in str(e.get("text") or ""):
                print("message", pid, e["writer"], e["seq"], e["kind"], [r.get("session") for r in e.get("to") or []],
                      e["text"])
    rec = os.path.join(home, "projects", pid, "delivered", sid + ".json")
    if os.path.exists(rec):
        d = json.load(open(rec))
        for w in sorted(d):
            if isinstance(d[w], dict):
                print("delivered", pid, w, "settled", d[w].get("settled", 0), "held", sorted(d[w].get("held") or []))
    out = os.path.join(home, "projects", pid, "outcomes.jsonl")
    if os.path.exists(out):
        for line in open(out):
            o = json.loads(line)
            print("outcome", pid, json.dumps({k: o[k] for k in ("event", "session", "outcome") if k in o}, sort_keys=True))
' "$SMINOS_HOME" "$SID"
  frames "$SID" | sed 's/^/pushed /'
}
stated() { # this code's view of the session's row: the set its log states there, "<none>" for no row
  here_py 'import sminos
p, sid = sminos.resolve_project(sys.argv[2]), sys.argv[3]
row = next((m for m in sminos.view_of(p).members if m.session == sid), None)
print(" ".join(row.channels) if row is not None else "<none>")' "$REPO" "$SID"
}
channel_store() { # label — the copy's verbs over a store with channels, against the same store without them
  fresh "$1-plain"
  stopped_thread auto
  KEYS="" older_over
  local plain="$VERBS"
  fresh "$1-chan"
  echo " the same verbs over a store with the thread in a channel (its statement), a request and a channel-env:"
  stopped_thread auto
  with_channels
  KEYS="$(record_keys)"
  assert_equals "$KEYS" '[["'"$CHANNEL"'"], {"'"$CHANNEL"'": {"alpha/human": 1}}, [["'"$CHANNEL"'", "'"$REQUEST"'"]], null]' \
    "the record holds the set, where its membership began and the request it answered"
  older_over
  assert_equals "$VERBS" "$plain" "each verb exits and prints as it did without channels, launches as it did, and its messages land and fare as they did"
  local fate
  fate="$(normal "$(delivery)")"
  assert_not_contains "$fate" "<channel>" "neither message is in the channel's log"
  case "$(version_of "$OLDER")" in
    1.27.*) assert_equals "$fate" "" "1.27 refuses both (the session ended, as it reads it): neither lands anywhere" ;;
    1.51.*)
      assert_equals "$(grep -c '^message <project> alpha/human [12] human \[.<sid>.\]' <<<"$fate")" 2 \
        "1.51 records both in the thread's project, addressed to the session"
      assert_contains "$fate" "delivered <project> alpha/human settled 0 held [[1, '<thread>'], [2, '<thread>']]" \
        "and holds both for the thread, pushing neither" ;;
    1.52.*)
      assert_equals "$(grep -c '^message <project> alpha/human [12] human \[.<sid>.\]' <<<"$fate")" 2 \
        "1.52 records both in the thread's project, addressed to the session"
      assert_equals "$(grep '^pushed\|^delivered' <<<"$fate")" "$(printf '%s\n' \
        "delivered <project> alpha/human settled 2 held []" "pushed hello from the older say" \
        "pushed a send from the older copy")" "wakes the thread and pushes each once, settling both" ;;
  esac
  assert_equals "$TICK_CHANNEL" "desk-integration: reconciled 0 · published 0 · delivered 0" \
    "its tick reconciles the channel as a project with no member"
  KEYS=""
  older projects
  assert_equals "$(grep -cE '^desk-integration +hub +0 +0 +-$' <<<"$OUT")" 1 "it lists the channel as a project with no member"
  run "$SMINOS" projects
  assert_not_contains "$OUT" "desk-integration" "this code lists it as none"
  echo " the session reopened by its human, the older copy first:"
  opened
  older list
  assert_equals "$RC" 0 "its list runs"
  local before
  before="$(statements | wc -l | tr -d ' ')"
  run "$SMINOS" daemon tick
  case "$(version_of "$OLDER")" in
    1.27.*)
      assert_equals "$(own_events | tail -2)" "$(printf 'joined - unstamped\njoined - stamped')" \
        "1.27 joined it unstamped, and this code stamped it again"
      assert_equals "$(statements | wc -l | tr -d ' ')" "$((before + 1))" \
        "this code's next reconciliation states the set after that joined" ;;
    *) assert_equals "$(statements | wc -l | tr -d ' ')" "$before" "it joined nothing again: nothing is stated again" ;;
  esac
  assert_equals "$(stated)" "$CHANNEL" "the log states the record's set"
  assert_equals "$(record_keys)" '[["'"$CHANNEL"'"], {"'"$CHANNEL"'": {"alpha/human": 1}}, [["'"$CHANNEL"'", "'"$REQUEST"'"]], null]' \
    "and the record's keys are as written"
  closed
}
channel_seat() { # label — accepted (the constraints' list) and asserted as it is: 1.51 and 1.52's list --json of a
  # spawned thread in a channel hides `channels`, which they know (SEAT_KEYS), and shows `began` and `answered`
  fresh "$1-chan-seat"
  run "$SMINOS" spawn seata "for the seat task"
  assert_equals "$RC" 0 "this code spawns seata"
  local seat
  seat="$(printf '%s' "$OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p')"
  SID="$seat" THREAD="$seat" with_channels
  assert_equals "$( (cd "$REPO" && STUB_WHO=older "$OLDER" list --json 2>/dev/null) | py 'import json, sys
row = next(r for r in json.load(sys.stdin) if r["session"] == sys.argv[1])
print(" ".join(k for k in ("channels", "began", "answered") if k in (row["seat"] or {})))' "$seat")" "began answered" \
    "its list --json shows the seat's began and answered, and hides its channels"
}
channel_return() { # label — the thread ended in the channel, its log gaining an event meanwhile, then returned
  fresh "$1-chan-return"
  echo " an end, an event in the channel's log, and a return:"
  opened
  run "$SMINOS" list
  THREAD="$(row thread)"
  with_channels
  closed
  run "$SMINOS" retire keeper
  assert_equals "$RC" 0 "this code ends the thread"
  here_py 'import sminos
sminos.log_append(sminos.known_project(sys.argv[2]), "beta/human", "channel-env", op="add", machine="beta", thread="x")' \
    "$CHANNEL"
  opened
  older list
  assert_equals "$RC" 0 "its list runs"
  local old='{"'"$CHANNEL"'": {"alpha/human": 1}}' kind
  case "$(version_of "$OLDER")" in
    1.27.*)
      assert_equals "$(own_events | tail -1)" "retired retire stamped" "1.27, with no journal, returns nothing"
      run "$SMINOS" daemon tick
      kind="this code's return writes where the membership began anew, the event the log gained meanwhile included"
      assert_contains "$(record_keys)" '"beta/human": 1' "$kind" ;;
    *)
      assert_equals "$(own_events | tail -1)" "joined - stamped" "it returned the thread"
      assert_contains "$(record_keys)" "$old" "accepted: its return leaves where the membership began as it was before the end"
      run "$SMINOS" daemon tick ;;
  esac
  assert_equals "$(statements | wc -l | tr -d ' ')" 2 "this code's next reconciliation states the set after the return's joined"
  assert_equals "$(stated)" "$CHANNEL" "the log states the record's set"
  closed
}
channel_join() { # label live|closed — the copy's `join <channel id>` by hand from the running session; this code's
  # next reconciliation runs while it runs, or once it runs again; then the wire check over the store
  fresh "$1-chan-join-$2"
  echo " its join of the running session into the channel's id, this code reconciling it $2:"
  opened
  run "$SMINOS" list
  THREAD="$(row thread)"
  with_channels
  local keys
  keys="$(record_keys)"
  run env STUB_WHO=older CLAUDE_CODE_SESSION_ID="$SID" "$OLDER" join "$CHANNEL"
  assert_equals "$RC" 0 "the older copy joins it into the channel"
  SMINOS_SCRIPTS="$SCRIPTS" python3 -B "$SCRIPT_DIR/older_channel_wire.py" baseline "$T/baseline-$1-$2" "$CHANNEL"
  channel_kinds() { # the events under the session's own writer in the channel's log
    cat "$SMINOS_HOME/projects/$CHANNEL/log/"*.jsonl | py 'import json, sys
print(" ".join(e["kind"] + ("-" + e["reason"] if e.get("reason") else "") for e in map(json.loads, sys.stdin)
               if e["writer"].endswith("/" + sys.argv[1])))' "$SID"
  }
  assert_equals "$(channel_kinds)" "channel-env joined" "its joined is in the channel's log"
  if [ "$2" = closed ]; then
    closed
    run "$SMINOS" daemon tick
    assert_equals "$(channel_kinds)" "channel-env joined" "closed, the session's joined in the channel is left as it is"
    assert_equals "$(row state)" "<no row>" "and it is listed in neither: not in its project"
    assert_equals "$(here_py 'import sminos
print(len(sminos.view_of(sminos.known_project(sys.argv[2])).members))' "$CHANNEL")" 0 "nor in the channel"
    opened
  fi
  run "$SMINOS" daemon tick
  assert_equals "$(channel_kinds)" "channel-env joined retired-moved" "this code undoes the joined: retired moved"
  assert_equals "$(own_events | tail -1)" "joined - stamped" "the session is a member of its one project again"
  assert_equals "$(row state)" idle "listed live there"
  assert_equals "$(record_keys)" "$keys" "its set, positions and answer as they were"
  assert_equals "$(stated)" "$CHANNEL" "and its log states the set"
  OUT="$(MAWS_USER_DATA="$(dirname "$HOME")/m" SMINOS_SCRIPTS="$SCRIPTS" python3 -B "$SCRIPT_DIR/older_channel_wire.py" \
    check "$T/baseline-$1-$2" alpha "$CHANNEL" 2>&1)" || true
  assert_equals "$OUT" "$(printf '%s channel-env joined retired\nhuman channel-request\nbreaches 0' "$SID")" \
    "an uplink run on it: the older joined goes up in its place, this code's retired after it, nothing else of this code's"
  closed
}
channels_case() { # label — CH1's M8, per copy
  channel_store "$1"
  case "$(version_of "$OLDER")" in 1.51.*|1.52.*) channel_seat "$1" ;; esac
  channel_return "$1"
  channel_join "$1" live
  channel_join "$1" closed
}

# ---- run each copy with its version's expectations -----------------------------------
run_copy() { # label launcher
  OLDER="$2"
  local v
  v="$(version_of "$OLDER")"
  echo "$1: sminos $v ($OLDER)"
  case "$v" in
    1.27.*) case_1_27 "$1" ;;
    1.51.*) case_1_51 "$1" ;;
    1.52.*) ;;   # T2's release, which wakes what every_copy holds it must not: channels_case holds it to itself
    *) echo " no expectations of its own for $v: every copy's alone"; every_copy "$1-every" ;;
  esac
  cut_finished "$1"
  channels_case "$1"
}
run_copy pinned-1.27 "$COPY_1_27"
run_copy pinned-1.51 "$COPY_1_51"
run_copy pinned-1.52 "$COPY_1_52"
[ -z "$THIRD" ] || run_copy third "$THIRD"

echo
echo "older CLI: $PASSES passed, $FAILURES failed"
[ "$FAILURES" -eq 0 ]
