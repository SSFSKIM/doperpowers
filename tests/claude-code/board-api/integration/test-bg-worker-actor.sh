#!/usr/bin/env bash
# test-bg-worker-actor.sh — the acceptance of dp#35, and the only drill in this
# tier that spawns a REAL model session.
#
# Every other drill in this directory stands a scripted stub in for the sminos
# layer, because none of their claims is about that layer. This one's claim is
# about nothing else: `sminos spawn` launches `claude --bg`, and a backgrounded
# session's own Bash shells are forked from a supervisor rather than from the
# launch — so the dispatcher's whole env prefix (`BOARD_RUN_TOKEN`,
# `BOARD_RUN_ID`, `BOARD_RUN_FENCE`, `BOARD_API_URL`, `BOARD_REPO`) is simply
# not there when the worker runs a board verb. A stub cannot show that, and no
# hermetic suite can: the drop is a property of the real harness.
#
# So: a real ticket on the real service, a real claim, a real `claude --bg`
# worker, and one question — when that worker runs board-transition.sh with
# nothing in its environment, does the board record the write as the RUN?
# `ready-for-implementer -> in-progress` is the edge an Executor's gate pass
# takes, so the drill asks it on the same edge production does.
#
# The repo it works in carries an api board.json with NO `repo` key — the
# older-head case, where the worker's checkout predates the key and the prefix
# that was meant to pin it is gone too. If the write lands, the repo came from
# the same place the bearer did.
#
# WHAT THE DRILL INJECTS, and why it does not weaken the claim: the worker's
# session gets ONE setting, `{"env": {"SMINOS_HOME": …}}`, so its registry
# reads land in this drill's scratch root instead of the operator's real
# `~/.claude/sminos`. In production that redirection is unnecessary — the
# default root IS the real one. Nothing board-shaped rides that channel: the
# worker receives no bearer, no run id, no fence, no url and no repo key by any
# route, which is the whole point.
#
# COST: one real haiku session (a handful of turns) and ~2 minutes of wall
# clock. Set A2_BG_WORKER_MODEL to change the model — the drill records which
# one it used, because a model that refuses a shell command under the
# permission mode `sminos spawn` passes is a fixture failure, not a finding.
. "$(dirname "$0")/drill-lib.sh"

command -v claude >/dev/null 2>&1 || {
  echo "SKIP $(basename "$0") — no \`claude\` on PATH; this drill launches a real background session (exit 77)"
  exit 77; }

drill_start

# The REAL sminos CLI, on this drill's scratch registry root. drill_start left
# SMINOS_CLI pointing at the stub every other drill uses; the stub spawns
# nothing, which is exactly what this drill may not do.
SMINOS_CLI="$REPO_ROOT/skills/sminos/scripts/sminos"
SMINOS_HOME="$DAEMON_HOME"; export SMINOS_HOME
MODEL="${A2_BG_WORKER_MODEL:-haiku}"
WORK="$DRILL_TMP/worker"; mkdir -p "$WORK"

WORKER_UUID=""
# Retired on EVERY exit path, pass or fail: a real background session outlives
# this shell, and one left running would go on holding a lease against a board
# that is about to be torn down under it.
retire_worker() {
  [ -n "$WORKER_UUID" ] || return 0
  "$SMINOS_CLI" retire "$WORKER_UUID" >/dev/null 2>&1 || true
  WORKER_UUID=""
}
trap 'retire_worker; drill_stop' EXIT
trap 'retire_worker; drill_stop; exit 130' INT
trap 'retire_worker; drill_stop; exit 143' TERM

# A bound checkout whose board.json predates the `repo` key (dp#33) — two keys,
# not three. api_repo writes three, so this one is written here.
REPO="$(mkrepo)"
mkdir -p "$REPO/.doperpowers"
printf '{"binding":"api","url":"%s"}\n' "$BOARD_API_URL" >"$REPO/.doperpowers/board.json"
DRILL_REPOS+=("$REPO")
REPO_KEY=doperpowers
drill_repo_key() { echo "$REPO_KEY"; }   # the file cannot answer it here

# ---- a ticket, and a run that owns it --------------------------------------
BODY="$DRILL_TMP/spec.md"
cat >"$BODY" <<'MD'
## Problem & intent

A ticket with a real body, so birth lands in the executor queue.

## Success criteria

A background worker moves it to in-progress as its own run.
MD
TID="$(in_repo BOARD_REPO="$REPO_KEY" "$SCRIPTS/board-register.sh" \
  'bg worker speaks as its run' enhancement P0 --body-file "$BODY" 2>&1 |
  awk 'END{print $1}')"
TID="${TID#\#}"
IFS=$'\t' read -r RUN TICKET FENCE BEARER <<<"$(claim_run implementer bg-actor-1)"
t "the claim landed on the registered ticket" "ticket=[$TID]" \
  echo "ticket=[$TICKET]"

# ---- the worker ------------------------------------------------------------
# Four mechanical steps. The `go` gate orders the drill against the worker:
# the seat cannot be bound until `sminos spawn` has told us its uuid. The
# release comes BEFORE the bind, on purpose — that is the dispatcher's order
# (execute-dispatch spawns, parses the uuid, then binds, with no startup
# barrier on the executor lane), so the worker's first board verb finds a
# seat record whose bind is still in flight and has to wait it out.
SETTINGS="$DRILL_TMP/worker-settings.json"
printf '{"env":{"SMINOS_HOME":"%s","DAEMON_HOME":"%s"}}\n' \
  "$DAEMON_HOME" "$DAEMON_HOME" >"$SETTINGS"
PROMPT="$(cat <<EOF
You are a fixture in an automated test. Do exactly the four steps below, in
order — steps 1 to 3 with the Bash tool, step 4 with the Task tool. Do not read
files, do not explore this repository, do not ask questions, do not improvise,
and do not stop before step 4.

Step 1. Run this Bash command:
printf '%s\n' "\$CLAUDE_CODE_SESSION_ID" > $WORK/main-session-id

Step 2. Run this Bash command. It blocks until the test releases you; that wait
is expected and is not a hang:
for i in \$(seq 1 45); do [ -f $WORK/go ] && break; sleep 2; done

Step 3. Run this Bash command, exactly as written:
$SCRIPTS/board-transition.sh $TID in-progress drill > $WORK/transition.log 2>&1; echo "rc=\$?" >> $WORK/transition.log

Step 4. Use the Task tool to launch exactly one general-purpose subagent, whose
prompt is this and nothing else:
  Run this single Bash command, then report the one line it wrote and nothing else: printf '%s\n' "\$CLAUDE_CODE_SESSION_ID" > $WORK/subagent-session-id

Then say DONE and stop.
EOF
)"

# The spawn prefix a dispatcher sets, in full — and it is precisely what the
# worker will NOT see. Passing it anyway is the honest fixture: the drill
# reproduces the production handover and lets the harness drop it, rather than
# arranging the absence itself.
SPAWN_OUT="$(BOARD_RUN_TOKEN="$BEARER" BOARD_RUN_ID="$RUN" BOARD_RUN_FENCE="$FENCE" \
  BOARD_API_URL="$BOARD_API_URL" BOARD_REPO="$REPO_KEY" \
  DAEMON_CLAUDE_EFFORT='' \
  "$SMINOS_CLI" spawn "dp35-$TID" "$PROMPT" --cwd "$REPO" --model "$MODEL" \
  --settings "$SETTINGS" 2>&1)" || true
printf '%s\n' "$SPAWN_OUT" >"$DRILL_TMP/spawn.out"
WORKER_UUID="$(printf '%s\n' "$SPAWN_OUT" |
  sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
if [ -z "$WORKER_UUID" ]; then
  echo "FAIL $(basename "$0") — sminos spawn produced no session uuid; there is no worker to drill. It said:"
  sed 's/^/     /' <<<"$SPAWN_OUT"
  exit 1
fi
echo "note: worker model=$MODEL uuid=$WORKER_UUID"

# ---- the release, then the bind --------------------------------------------
# The worker polls for `go` every 2s and runs its transition at once, which on
# this repo-less checkout enters own_seat()'s bind wait; the bind lands a few
# seconds into that window. board-bind.sh runs with the run env, as the
# dispatcher runs it, and with the repo key it cannot read from this checkout's
# board.json — that stamp is what the worker resolves its own repo from.
: >"$WORK/go"
sleep 4
in_repo BOARD_RUN_TOKEN="$BEARER" BOARD_RUN_ID="$RUN" BOARD_RUN_FENCE="$FENCE" \
  BOARD_REPO="$REPO_KEY" "$SCRIPTS/board-bind.sh" "$WORKER_UUID" "$TID" \
  >"$DRILL_TMP/bind.log" 2>&1
t "the seat is bound to the ticket" "bound #$TID" cat "$DRILL_TMP/bind.log"
t "and the record carries the repo the checkout cannot name" \
  '"board_repo": "doperpowers"' cat "$DAEMON_HOME/$WORKER_UUID.json"

LANDED=1
# The LOG, not the board state: a refused write is an answer too, and waiting
# out the full budget for a state that will never arrive costs five minutes and
# tells the reader nothing the log does not already say.
worker_wrote() { [ -s "$WORK/transition.log" ]; }
wait_until 300 "the background worker's board write" worker_wrote || LANDED=0

# ---- the verdicts ----------------------------------------------------------
# The write happened at all, and it happened as the RUN. `actor` is derived
# server-side from the token's class, never from anything the caller asserts,
# so `run:<id>` is the board's own statement about which principal wrote.
ticket_state "$TID" >"$DRILL_TMP/state.txt"
last_transition_actor() {
  api automation GET "/tickets/$TID/timeline" | python3 -c '
import json, sys
board = [r for r in json.load(sys.stdin)["records"]
         if r.get("source") == "board" and r.get("kind") == "transition"]
print("actor=[%s]" % (board[-1]["body"].get("actor") if board else "none"))'
}
t "the ticket reached in-progress" "state=[in-progress]" \
  bash -c "echo \"state=[\$(cat '$DRILL_TMP/state.txt')]\""
t "and the board recorded the write as the run, not as the human" \
  "actor=[run:$RUN]" last_transition_actor

# The fence is not a separate assertion the drill could fake: the service
# refuses a run actor's transition that carries no fence, or a stale one
# (`fence-mismatch`). A successful run-actor write IS the fence honoured, and
# the worker had no fence in its environment to send.
nt "no fence was missing or stale" "fence-mismatch" cat "$WORK/transition.log"
nt "and the repo-less board.json never bit" "binding=api but no repo" \
  cat "$WORK/transition.log"
t  "the verb reported the state the server wrote" "#$TID: → in-progress" \
  cat "$WORK/transition.log"
# The stderr note is the direct evidence of WHICH channel answered: an
# inherited prefix prints nothing, a resolved seat record prints this.
t  "the worker resolved its run from its own seat record" \
  "speaking as run $RUN via seat $WORKER_UUID" cat "$WORK/transition.log"
nt "and never leaked the bearer into its own output" "$BEARER" \
  cat "$WORK/transition.log"

# The environment the worker actually had, from inside it: its session id is
# the only locator it holds, and it is the one the record is keyed by.
t "the worker's own shell knows its session id, and it is the seat's" \
  "$WORKER_UUID" cat "$WORK/main-session-id"

# ---- the measurement this design left open ---------------------------------
# Does a SUBAGENT's shell carry the same session id? If it does, a subagent
# self-locates to its parent's run — which is the behaviour the protocols
# already assume when they let a worker delegate. If it carries its own, a
# delegated board write falls back to the operator credentials instead, and
# that is a gap to record rather than to guess at. Reported, never asserted:
# this drill measures it, it does not legislate it.
SUB_WAIT=90
for _ in $(seq 1 "$SUB_WAIT"); do [ -s "$WORK/subagent-session-id" ] && break; sleep 1; done
if [ -s "$WORK/subagent-session-id" ]; then
  SUB_ID="$(tr -d '[:space:]' <"$WORK/subagent-session-id")"
  if [ "$SUB_ID" = "$WORKER_UUID" ]; then
    echo "measurement: a subagent's shell carries the PARENT's CLAUDE_CODE_SESSION_ID ($SUB_ID) — a delegated board write self-locates to the same run"
  else
    echo "measurement: a subagent's shell carries its OWN CLAUDE_CODE_SESSION_ID ($SUB_ID != $WORKER_UUID) — a delegated board write finds no seat record and falls back"
  fi
else
  echo "measurement: UNMEASURED — the worker never wrote $WORK/subagent-session-id within ${SUB_WAIT}s"
fi

[ "$LANDED" -eq 1 ] || echo "note: the transition did not land inside the wait; the worker's last output follows"
[ "$LANDED" -eq 1 ] || { "$SMINOS_CLI" reply "$WORKER_UUID" 2>&1 | tail -30; cat "$WORK/transition.log" 2>/dev/null; }

retire_worker
finish
