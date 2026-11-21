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
#   test-older-cli.sh [--older <path to an older sminos launcher>]
#
# The two pinned copies are revisions of this repository, extracted by `git
# archive`, each fetched from `origin` by its id when the clone lacks it (the
# gates check out one commit, shallow); when one cannot be had the script
# fails, never passing on a line saying it was skipped. `--older` adds a third
# copy (one in a plugin cache, say), run after them with the expectations of
# the version its plugin says (`<plugin>/.claude-plugin/plugin.json`, the
# launcher being `<plugin>/skills/sminos/scripts/sminos`): 1.27.x as 1.27.10,
# 1.51.x as 1.51.0, any other with the every-copy expectation alone.
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

# ---- run each copy with its version's expectations -----------------------------------
run_copy() { # label launcher
  OLDER="$2"
  local v
  v="$(version_of "$OLDER")"
  echo "$1: sminos $v ($OLDER)"
  case "$v" in
    1.27.*) case_1_27 "$1" ;;
    1.51.*) case_1_51 "$1" ;;
    *) echo " no expectations of its own for $v: every copy's alone"; every_copy "$1-every" ;;
  esac
}
run_copy pinned-1.27 "$COPY_1_27"
run_copy pinned-1.51 "$COPY_1_51"
[ -z "$THIRD" ] || run_copy third "$THIRD"

echo
echo "older CLI: $PASSES passed, $FAILURES failed"
[ "$FAILURES" -eq 0 ]
