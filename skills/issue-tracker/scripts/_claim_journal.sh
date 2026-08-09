#!/usr/bin/env bash
# _claim_journal.sh — the API dispatchers' shared claim journal: how a claimed
# run is recorded before it is handed to a worker, and how a crash mid-handover
# is reconciled afterwards. Sourced by implement-dispatch.sh and
# review-dispatch.sh, which had verbatim copies of both halves.
#
# THE JOURNAL DIRECTORY IS SHARED ($DAEMON_HOME/board-claims) and every entry
# names its lane. A dispatcher touches only its OWN lanes: replaying a qagent
# nonce from the implement side would hand a review assignment an implementer
# prompt, and ending a qagent run would strand the review dispatcher's ticket.
# A lane nobody recognizes is skipped for the same reason — not acting is the
# safe direction. The sweep's `successor` lane is outside both, and the sweep
# reconciles it itself.
#
# The caller supplies (all required):
#   CLAIM_LANES                  comma-separated lanes this dispatcher owns
#   _claim_one_with_nonce L N C  replay one claim under an existing nonce
#   _claim_lane_cap L            the lane cap to replay that lane under
#   _claim_drop_journal N        remove a nonce's journal (and its body file)
#   _api_end_run R REASON        best-effort release of a claimed run
#   DAEMON_HOME                  registry root

# One journal entry, written whole. json.dump rather than printf: the run id is
# whatever the server sent, and a non-integer one (a string id, a null slipping
# through) rendered into a bare `"run_id": %s` slot produces a file no reader
# can parse — and an unparseable journal is a claimed run nobody can reconcile.
# `ticket` and `daemon` land BEFORE the spawn on purpose; see _reconcile_claims.
# `pid` is this dispatcher's, so a concurrent peer can tell a journal whose
# writer is still working from one a crash left behind.
_journal_write() {  # <path> <lane> <run-id ('' = null)> <spawn-completed 0|1> [ticket] [daemon]
  J_PATH="$1" J_LANE="$2" J_RUN="$3" J_DONE="$4" J_TICKET="${5:-}" J_DAEMON="${6:-}" \
  J_PID="$$" python3 - <<'PY'
import json, os
e = os.environ
run = e["J_RUN"]
if run == "":
    run = None
else:
    try:
        run = int(run)
    except ValueError:
        pass
j = {"lane": e["J_LANE"], "run_id": run, "spawn_completed": e["J_DONE"] == "1",
     "pid": int(e["J_PID"])}
if e["J_TICKET"]:
    j["ticket"] = e["J_TICKET"]
if e["J_DAEMON"]:
    j["daemon"] = e["J_DAEMON"]
with open(e["J_PATH"], "w") as f:
    json.dump(j, f)
    f.write("\n")
PY
}

# Startup pass over the claim journal: every entry a crash could have left
# mid-handoff is either finished or released. One python pass classifies them
# against the registry (a journal that names a run the registry knows was in
# fact handed off); the shell performs only the two actions that leave this
# machine.
#
# ENDING A RUN IS THE ONLY DESTRUCTIVE ACTION HERE, and it is taken only when
# the evidence says no session exists. A run id alone never proves that: it
# reaches a meta through board-bind, the LAST step of the handover, so the whole
# spawn window shows up as "run claimed, registry silent" while a detached
# worker is already running. Ending there kills a live run and frees the ticket
# for a second worker. The daemon name in the journal closes that window;
# anything else the registry cannot speak to is held, and the server lease
# reclaim — not this dispatcher — resolves it.
#
# A JOURNAL WHOSE WRITER IS STILL ALIVE IS NOT A CRASH. Nothing serializes two
# dispatch processes (an operator's `--sweep` beside the tick's), and a peer's
# claim is journalled BEFORE its POST goes out — so replaying that nonce while
# its response is in flight makes A1 rotate the bearer under the peer, and both
# callers spawn from their own answers. A journal younger than
# BOARD_CLAIM_INFLIGHT_GRACE seconds whose pid is still running is left alone.
_reconcile_claims() {
  local actions lines line act nonce lane run extra
  actions="$(T_DHOME="$DAEMON_HOME" T_LANES="$CLAIM_LANES" \
             T_GRACE="${BOARD_CLAIM_INFLIGHT_GRACE:-120}" python3 - <<'PY'
import glob, json, os, time
home = os.environ["T_DHOME"]
lanes = set(os.environ["T_LANES"].split(","))
grace = float(os.environ["T_GRACE"])
live = set()
names = set()
blind = []
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        # A meta we cannot read is a session we cannot rule out. Say so, and
        # let every end below downgrade to a hold.
        blind.append(p)
        continue
    if m.get("run_id"):
        live.add(str(m["run_id"]))
    # ONLY A RUNNING SESSION IS EVIDENCE OF A SPAWN. Daemon names are
    # deterministic per ticket and lane (`<ticket>-api-<lane>`) and a retired
    # daemon keeps its meta, so a HISTORICAL entry into the same lane left a
    # name that falsely proved the NEXT claim had spawned — closing its journal
    # and leaving the new run ownerless until the lease expired.
    if m.get("name") and m.get("status") in ("working", "blocked"):
        names.add(str(m["name"]))


def alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


for p in blind:
    print("unreadable\t%s\t\t\t" % p)
for p in sorted(glob.glob(os.path.join(home, "board-claims", "*.json"))):
    try:
        j = json.load(open(p))
    except Exception:
        # Silently skipping this hid a claimed run forever. It is reported and
        # left alone: a journal nobody can read is not a journal anybody may
        # act on. Its lane is unknowable too, so no lane filter can apply —
        # both dispatchers report it and neither touches it.
        print("unreadable\t%s\t\t\t" % p)
        continue
    if j.get("spawn_completed") or j.get("lane") not in lanes:
        continue
    nonce = os.path.basename(p)[:-5]
    lane = j.get("lane") or ""
    run = j.get("run_id")
    daemon = j.get("daemon") or ""
    if run and str(run) in live:
        # the spawn DID complete — its worker is in the registry — and only
        # the marker write was lost. Repair it in place; nothing to send.
        j["spawn_completed"] = True
        with open(p, "w") as f:
            json.dump(j, f)
        print("repaired\t%s\t%s\t%s\t" % (nonce, lane, run))
    elif run and daemon and daemon in names:
        # A session by that name exists but no meta carries the run: the spawn
        # landed and the bind did not. The worker is alive with its bearer in
        # its environment, so the run is NOT ended and the ticket is NOT freed.
        # The journal is closed to replay and left as the record.
        j["spawn_completed"] = True
        with open(p, "w") as f:
            json.dump(j, f)
        print("orphaned\t%s\t%s\t%s\t%s" % (nonce, lane, run, daemon))
    elif run and blind:
        print("held\t%s\t%s\t%s\t" % (nonce, lane, run))
    elif (time.time() - os.path.getmtime(p) < grace) and alive(j.get("pid")):
        # Another dispatch process is mid-handover on this nonce right now.
        print("inflight\t%s\t%s\t%s\t%s" % (nonce, lane, run or "", j.get("pid")))
    elif run:
        print("end\t%s\t%s\t%s\t" % (nonce, lane, run))
    else:
        print("replay\t%s\t%s\t\t" % (nonce, lane))
PY
)" || { echo "claim reconciliation failed — skipping it this tick" >&2; return 0; }
  [ -n "$actions" ] || return 0
  # Read the whole plan BEFORE acting on it. The actions below run children
  # (a replayed claim, an end, a spawn) that inherit this stdin, and one of
  # them consuming the rest of the plan would silently drop reconciliation
  # steps — the class of bug that is invisible until the tick that needed them.
  lines=()
  while IFS= read -r line; do
    [ -n "$line" ] && lines+=("$line")
  done <<<"$actions"
  for line in ${lines[@]+"${lines[@]}"}; do
    IFS=$'\t' read -r act nonce lane run extra <<<"$line"
    case "$act" in
      unreadable)
        echo "reconcile: unreadable json at $nonce — left untouched; no claim under it can be reconciled until it is repaired or removed by hand" >&2 ;;
      repaired)
        echo "reconcile: $nonce did spawn (run $run) — marker repaired" ;;
      orphaned)
        echo "reconcile: $nonce spawned $extra for run $run but never bound it — the session is live and is NOT being ended; it has no bearer at rest, so no later relay or resume can speak for it (retire it by hand once it is done)" ;;
      held)
        echo "reconcile: $nonce claimed run $run — holding it; the registry has an unreadable meta, so a live session cannot be ruled out. The server lease reclaim owns this one." >&2 ;;
      inflight)
        echo "reconcile: $nonce is in flight under a live dispatcher (pid $extra) — left alone" ;;
      end)
        # Claimed but never handed off. The response WAS received, so a replay
        # would rotate nothing; the lease would otherwise strand the ticket
        # until the server's own reclaim.
        echo "reconcile: $nonce claimed run $run but never spawned — ending it"
        _api_end_run "$run" abandoned
        _claim_drop_journal "$nonce" ;;
      replay)
        # The nonce persisted but no run id ever did: the response was lost in
        # flight. Replaying THIS nonce is the only legal replay there is.
        echo "reconcile: $nonce never reached a run — replaying the claim"
        _claim_one_with_nonce "$lane" "$nonce" "$(_claim_lane_cap "$lane")" || true ;;
    esac
  done
}
