#!/usr/bin/env bash
# board-sweep.sh — the unattended tick: one idempotent pass over the board
# and the daemon registry, run by cron/launchd every ~5 minutes. Mechanical
# only — no model calls, no judgment; every action re-derives its work-list
# from durable state (GitHub + registry metas), so overlapping or repeated
# ticks are safe and a restart loses nothing.
#
# Passes, each independently guarded so one failure never stops the rest:
#   RECOVER  in-progress tickets with a bound implement/spike worker that is
#            dead (finalize: absent/error), silent past the stall timeout, or
#            finished without a board transition → bounded resume (a nudge on
#            the SAME session — context intact), 3 lifetime attempts per
#            daemon, then park needs-human with an orientation note. A dead
#            worker on a still-ready-for-agent ticket is just retired — the
#            dispatch pass fresh-dispatches it (re-orientation is cheap
#            pre-gate).
#   CANCEL   live implement/spike workers whose ticket reached a terminal
#            state (done/wontfix) → retire + a [board] termination comment.
#            Park states never cancel (park = pause); review-pr-*/land-pr-*
#            workers are PR-lifecycle species and are never board-cancelled.
#   DISPATCH implement-dispatch.sh --sweep (cap-bounded).
#   REVIEW   review-dispatch.sh --sweep (its own dedupe + failure caps).
#   LAND     open confident-ready PRs with a human APPROVED review or a
#            `land` label, and NO land-pr-<n> meta yet → land-dispatch.sh.
#            One sweep attempt per PR — a dead lander is a wake item, not a
#            retry loop.
#   RELAY    needs-human tickets with a bound idle session whose newest
#            issue comment is newer than the session's last activity and is
#            not machine-authored ([answers]/[board]/[gate] prefixes) →
#            board-answer.sh <n> --posted, backgrounded. The relayed comment
#            id is recorded in the meta BEFORE relaying so a crashed relay
#            cannot re-fire.
#   REPORT   board-reconcile.sh (read-only) into the sweep log — CLOSE?
#            candidates and orphans surface there for the human's wake.
#
# Env:
#   LOCAL_REPO BOARD_REPO           as the lane dispatchers take them
#   SWEEP_STALL_MINUTES             silence threshold for a live worker (45)
#   SWEEP_RECOVERY_CAP              lifetime sweep resumes per daemon (3)
#   IMPLEMENT_MAX_CONCURRENT WORKER_ENGINE CLODEX_* AUTO_MERGE_ENABLED
#   LAND_ENABLED                    exported through to the lanes
#   SWEEP_LOG                       log file (default $DAEMON_HOME/sweep.log)
#   IMPLEMENT_DISPATCH_CMD REVIEW_DISPATCH_CMD LAND_DISPATCH_CMD
#   BOARD_ANSWER_CMD RECONCILE_CMD DAEMON_SCRIPTS DAEMON_HOME  (test seams)
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$SCRIPT_DIR}"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
export DAEMON_HOME BOARD_SCRIPTS
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
export LOCAL_REPO
# The board scripts this tick invokes bare (board-reconcile, board-answer,
# board-transition) anchor _lib.sh's BOARD_ROOT on the CURRENT directory —
# under launchd/cron the cwd is not a repo and they die at source time
# ("not inside a git repo"; REPORT failed every launchd tick, and RELAY
# would stamp its at-most-once guard and then lose the answer the same
# way). Run the whole tick from the consumer repo.
cd "$LOCAL_REPO" || { echo "error: cannot cd to LOCAL_REPO=$LOCAL_REPO" >&2; exit 1; }
IMPLEMENT_DISPATCH_CMD="${IMPLEMENT_DISPATCH_CMD:-$SKILL_DIR/../implementing-tickets/scripts/implement-dispatch.sh}"
REVIEW_DISPATCH_CMD="${REVIEW_DISPATCH_CMD:-$SKILL_DIR/../reviewing-prs/scripts/review-dispatch.sh}"
LAND_DISPATCH_CMD="${LAND_DISPATCH_CMD:-$SKILL_DIR/../reviewing-prs/scripts/land-dispatch.sh}"
BOARD_ANSWER_CMD="${BOARD_ANSWER_CMD:-$SCRIPT_DIR/board-answer.sh}"
RECONCILE_CMD="${RECONCILE_CMD:-$SCRIPT_DIR/board-reconcile.sh}"
SWEEP_LOG="${SWEEP_LOG:-$DAEMON_HOME/sweep.log}"
STALL_MIN="${SWEEP_STALL_MINUTES:-45}"
RECOVERY_CAP="${SWEEP_RECOVERY_CAP:-3}"

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "${BOARD_REPO:-}" ] || { echo "error: could not resolve BOARD_REPO" >&2; exit 1; }
export BOARD_REPO

# Single instance per registry — an mkdir lock (portable; macOS ships no
# flock). Idempotence is the real safety; the lock only prevents wasted
# work, so a stale lock (older than 30 min) is stolen, not obeyed. The
# registry dir may not exist yet on a fresh machine — a missing parent
# would make every mkdir fail and read as "held" forever.
mkdir -p "$DAEMON_HOME"
LOCK="$DAEMON_HOME/board-sweep.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +"${SWEEP_LOCK_STALE:-30}" 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || true
    mkdir "$LOCK" 2>/dev/null || { echo "another sweep holds the lock — exiting"; exit 0; }
  else
    echo "another sweep holds the lock — exiting"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# Self-truncating log: keep the newest quarter once it crosses 1 MB.
if [ -f "$SWEEP_LOG" ] && [ "$(wc -c < "$SWEEP_LOG")" -gt 1048576 ]; then
  tail -c 262144 "$SWEEP_LOG" > "$SWEEP_LOG.tmp" && mv "$SWEEP_LOG.tmp" "$SWEEP_LOG"
fi
log() { printf '%s\n' "$*" | tee -a "$SWEEP_LOG"; }
log "[sweep $(date -u +%Y-%m-%dT%H:%M:%SZ)] tick — repo=$BOARD_REPO"

# Bound implement/spike metas joined with ticket state, one line each:
#   <state>|<ticket>|<uuid>|<status>|<current>|<updated>|<recoveries>
# Review/land species are excluded here once, for every pass.
_bound_rows() {
  python3 - <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
for p in sorted(glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    if name.startswith("review-pr-") or name.startswith("land-pr-"):
        continue
    tk = str(m.get("ticket") or "").lstrip("#")
    if not tk or tk not in tickets:
        continue
    print("|".join([tickets[tk]["state"], tk, m.get("uuid") or "",
                    m.get("status") or "", m.get("current") or m.get("uuid") or "",
                    str(m.get("updated") or ""), str(m.get("sweep_recoveries") or "0")]))
PY
}

# Set meta fields (uuid, k, v, ...) under the registry lock; never touches
# `updated` (the relay pass reads it as last-turn-activity).
_meta_put() {
  M_UUID="$1" M_KV="$(printf '%s\n' "${@:2}")" python3 - <<'PY'
import fcntl, json, os
home = os.environ["DAEMON_HOME"]
lock = open(os.path.join(home, ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
p = os.path.join(home, os.environ["M_UUID"] + ".json")
m = json.load(open(p))
kv = os.environ["M_KV"].splitlines()
for k, v in zip(kv[0::2], kv[1::2]):
    m[k] = v
tmp = p + ".tmp"
json.dump(m, open(tmp, "w"), indent=2)
os.replace(tmp, p)
PY
}

_transcript() { find "$HOME/.claude/projects" -name "$1.jsonl" 2>/dev/null | head -1; }

# File mtime as UTC ISO-8601 (BSD stat first, GNU fallback) — the turn-end
# ordering signal for the relay pass.
_mtime_iso() {
  local e
  e="$(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null)" || return 1
  date -u -r "$e" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "@$e" +%Y-%m-%dT%H:%M:%SZ
}

_recover() {  # <ticket> <uuid> <recoveries> <why>
  local tk="$1" uuid="$2" recov="$3" why="$4"
  if [ "$recov" -ge "$RECOVERY_CAP" ]; then
    log "[sweep] RECOVER: #$tk worker $uuid $why — cap ($RECOVERY_CAP) exhausted, parking needs-human"
    "$BOARD_SCRIPTS/board-transition.sh" "$tk" needs-human \
      "auto-recovery exhausted: bound worker $uuid $why $RECOVERY_CAP times; resume it by hand (daemon-resume/board-answer) or re-cut to ready-for-agent for a fresh dispatch" \
      >>"$SWEEP_LOG" 2>&1 \
      || log "[sweep] RECOVER: #$tk park transition FAILED (see log)"
    return
  fi
  _meta_put "$uuid" sweep_recoveries "$((recov + 1))" \
    || { log "[sweep] RECOVER: #$tk meta update failed — skipping resume"; return; }
  log "[sweep] RECOVER: #$tk worker $uuid $why — resume attempt $((recov + 1))/$RECOVERY_CAP"
  nohup "$DAEMON_SCRIPTS/daemon-resume.sh" "$uuid" \
    "SWEEP RECOVERY: your previous turn on ticket #$tk ended abnormally ($why). Re-read the ticket and the board state, restate your gate verdict against them in one paragraph, then continue your protocol from where the work actually stands. If the scope has shifted, park honestly instead." \
    >>"$SWEEP_LOG" 2>&1 &
}

pass_recover() {
  local acted=0 state tk uuid status current recov fin tx age
  while IFS='|' read -r state tk uuid status current _ recov; do
    [ -n "$uuid" ] || continue
    case "$status" in working|blocked|error) ;; *) [ "$status" = "idle" ] || continue ;; esac
    fin="$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$uuid" 2>/dev/null)" || fin="noop"
    # finalize says noop for an ALREADY-terminal meta (error/idle) — the
    # meta's own status is the verdict then, or the recovery ladder would
    # silently abandon exactly the failed-resume and fast-fail-spawn shapes.
    [ "$fin" = "noop" ] && fin="$status"
    case "$state" in
      in-progress)
        case "$fin" in
          absent) _recover "$tk" "$uuid" "$recov" "died mid-turn (session gone)"; acted=$((acted+1)) ;;
          error)  _recover "$tk" "$uuid" "$recov" "turn errored"; acted=$((acted+1)) ;;
          idle)   _recover "$tk" "$uuid" "$recov" "finished without a board transition"; acted=$((acted+1)) ;;
          live)
            tx="$(_transcript "$current")"
            if [ -n "$tx" ]; then
              age="$(( ( $(date +%s) - $(stat -f %m "$tx" 2>/dev/null || stat -c %Y "$tx") ) / 60 ))"
              if [ "$age" -ge "$STALL_MIN" ]; then
                _recover "$tk" "$uuid" "$recov" "silent for ${age}m (stall threshold ${STALL_MIN}m)"
                acted=$((acted+1))
              fi
            fi ;;
        esac ;;
      ready-for-agent)
        # a dead pre-gate worker frees its slot; the dispatch pass re-runs it
        case "$fin" in
          absent|error)
            log "[sweep] RECOVER: #$tk pre-gate worker $uuid dead — retired (dispatch pass re-runs the gate fresh)"
            "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
            acted=$((acted+1)) ;;
        esac ;;
    esac
  done <<EOF
$(_bound_rows | grep -E '^(in-progress|ready-for-agent)\|' || true)
EOF
  log "[sweep] RECOVER: $acted acted"
}

pass_cancel() {
  local acted=0 state tk uuid status current recov fin
  while IFS='|' read -r state tk uuid status current _ recov; do
    [ -n "$uuid" ] || continue
    case "$status" in working|blocked) ;; *) continue ;; esac
    fin="$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$uuid" 2>/dev/null)" || fin="noop"
    [ "$fin" = "live" ] || continue
    log "[sweep] CANCEL: #$tk is $state but worker $uuid still runs — retiring"
    "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
    gh issue comment "$tk" -R "$BOARD_REPO" --body \
      "[board] sweep: retired worker $uuid — the ticket reached \`$state\` while it ran. Its worktree and any committed branch are preserved." \
      >/dev/null 2>&1 || log "[sweep] CANCEL: #$tk termination comment failed"
    acted=$((acted+1))
  done <<EOF
$(_bound_rows | grep -E '^(done|wontfix)\|' || true)
EOF
  log "[sweep] CANCEL: $acted acted"
}

pass_land() {
  local acted=0 rows pr
  rows="$(gh pr list -R "$BOARD_REPO" --state open --label confident-ready \
            --json number,reviewDecision,labels 2>/dev/null)" || rows="[]"
  while IFS= read -r pr; do
    [ -n "$pr" ] || continue
    if python3 - "$pr" <<'PY'
import glob, json, os, sys
name = "land-pr-" + sys.argv[1]
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        if json.load(open(p)).get("name") == name:
            sys.exit(1)
    except Exception:
        continue
sys.exit(0)
PY
    then
      log "[sweep] LAND: PR #$pr approved and unlanded — dispatching land worker"
      "$LAND_DISPATCH_CMD" "$pr" >>"$SWEEP_LOG" 2>&1 \
        || log "[sweep] LAND: PR #$pr land dispatch failed (see log)"
      acted=$((acted+1))
    fi
  done <<EOF
$(printf '%s' "$rows" | python3 -c '
import json, sys
for p in json.load(sys.stdin):
    labels = [l.get("name", "") for l in (p.get("labels") or [])]
    if p.get("reviewDecision") == "APPROVED" or "land" in labels:
        print(p["number"])' 2>/dev/null || true)
EOF
  log "[sweep] LAND: $acted acted"
}

pass_relay() {
  local acted=0 state tk uuid status current recov fin tx turn_end verdict cid
  while IFS='|' read -r state tk uuid status current _ recov; do
    [ -n "$uuid" ] || continue
    # Normalize first: a --no-wait worker that parked leaves its meta
    # status=working forever (nothing else finalizes it). Only a genuinely
    # ended turn is resumable; finalize prints noop for already-terminal
    # metas, so fall back to the meta's own status.
    case "$status" in working|blocked|idle) ;; *) continue ;; esac
    fin="$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$uuid" 2>/dev/null)" || fin="noop"
    [ "$fin" = "noop" ] && fin="$status"
    [ "$fin" = "idle" ] || continue
    # Turn-end ordering signal: the current turn's transcript mtime. It is
    # stable once the turn ends, and — unlike the meta's `updated` field,
    # which the finalize above just bumped — it cannot postdate (and so
    # hide) the human's answer. Comments from before the turn ended are
    # the worker's own trail, never an answer to relay.
    tx="$(_transcript "$current")"
    [ -n "$tx" ] || continue
    turn_end="$(_mtime_iso "$tx")" || continue
    verdict="$(gh issue view "$tk" -R "$BOARD_REPO" --json comments 2>/dev/null | \
      T_TURN_END="$turn_end" T_UUID="$uuid" python3 -c '
import json, os, sys
try:
    comments = json.load(sys.stdin).get("comments") or []
except Exception:
    comments = []
if not comments:
    sys.exit(0)
last = comments[-1]
body = (last.get("body") or "").lstrip()
if body.startswith(("[answers]", "[board]", "[gate]", "[findings]")):
    sys.exit(0)
if str(last.get("createdAt") or "") <= os.environ["T_TURN_END"]:
    sys.exit(0)
home = os.environ["DAEMON_HOME"]
meta = json.load(open(os.path.join(home, os.environ["T_UUID"] + ".json")))
if str(meta.get("relayed_comment") or "") == str(last.get("id") or ""):
    sys.exit(0)
print(last.get("id") or "")')" || verdict=""
    cid="$verdict"
    [ -n "$cid" ] || continue
    _meta_put "$uuid" relayed_comment "$cid" \
      || { log "[sweep] RELAY: #$tk meta guard write failed — skipping"; continue; }
    log "[sweep] RELAY: #$tk has a fresh human comment ($cid) — resuming the bound worker"
    nohup "$BOARD_ANSWER_CMD" "$tk" --posted >>"$SWEEP_LOG" 2>&1 &
    acted=$((acted+1))
  done <<EOF
$(_bound_rows | grep -E '^needs-human\|' || true)
EOF
  log "[sweep] RELAY: $acted acted"
}

pass_recover  || log "[sweep] RECOVER pass errored (continuing)"
pass_cancel   || log "[sweep] CANCEL pass errored (continuing)"
"$IMPLEMENT_DISPATCH_CMD" --sweep 2>&1 | tee -a "$SWEEP_LOG" \
  || log "[sweep] DISPATCH pass errored (continuing)"
"$REVIEW_DISPATCH_CMD" --sweep 2>&1 | tee -a "$SWEEP_LOG" \
  || log "[sweep] REVIEW pass errored (continuing)"
pass_land     || log "[sweep] LAND pass errored (continuing)"
pass_relay    || log "[sweep] RELAY pass errored (continuing)"
"$RECONCILE_CMD" 2>&1 | tee -a "$SWEEP_LOG" >/dev/null \
  || log "[sweep] REPORT pass errored (continuing)"
log "[sweep] tick complete"
