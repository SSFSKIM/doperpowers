#!/usr/bin/env bash
# board-sweep.sh — the unattended tick: one idempotent pass over the board
# and the daemon registry, run by cron/launchd every ~5 minutes. Mechanical
# only — no model calls, no judgment; every action re-derives its work-list
# from durable state (GitHub + registry metas), so overlapping or repeated
# ticks are safe and a restart loses nothing.
#
# Passes, each independently guarded so one failure never stops the rest:
#   RECOVER  in-flight tickets (in-progress, in-design) with a bound
#            implement/architect/spike worker that is dead (sminos sync:
#            absent/error), silent past the stall timeout, or finished
#            without a board transition → bounded resume (a nudge on the SAME
#            session — context intact), 3 lifetime attempts per daemon, then
#            park needs-human with an orientation note. A worker on a
#            still-pre-verdict (ready-for-*) ticket is just retired — dead,
#            or live-but-silent past the stall threshold on a state it has
#            already handed off — and the dispatch pass fresh-dispatches it
#            (re-orientation is cheap pre-verdict; a lingering binding is
#            not, it holds the destination lane's slot). An in-review ticket's
#            bound seat is the OWNER of the review it dispatched: same
#            verdicts, same nudge-then-park ladder, but counted in its own
#            key and bounded by the REVIEW's progress — a new [review-trail]
#            comment on the ticket resets the count, so only a review that
#            has actually stopped reaches the cap.
#   CANCEL   live implement/spike workers whose ticket reached a terminal
#            state (done/wontfix) → retire + a [board] termination comment.
#            Park states never cancel (park = pause); review-pr-* and
#            review-epic-* workers own their own lifecycle
#            (the reviewer IS what put the ticket in its terminal state)
#            and are never board-cancelled.
#   FINALIZE closed tickets still carrying a status:* label — an armed
#            auto-merge lands after the QA agent's turn ended, so the
#            PR's "Closes #N" closed the issue but board-transition's
#            terminal path (label strip, terminal sweeps, epic
#            recomposition) never ran → re-run the terminal transition
#            (board-transition's idempotent finalize path).
#   IMPACT   children in ANY state whose ticket carries a [parent-impact]
#            proposal the parent it NAMES has not yet consumed (the format
#            pins that parent; a reparented child's proposal still belongs to
#            the contract it cited) → that parent returns to
#            ready-for-architect (reconciliation-due), plus a
#            [board-epic] reconcile: #<child>@<comment-id> dedupe marker.
#            The marker is written ONLY when that return actually fires:
#            a parent that is parked, terminal, or already in the architect
#            lane is skipped UNMARKED and re-read next tick, so no proposal
#            is marked consumed while nobody is there to read it. Parks in
#            particular are never disturbed — unparking one would destroy
#            its note and drop it out of the RELAY pass's wake queue below.
#            Both scans read only comments from repo-side authors
#            (authorAssociation OWNER/MEMBER/COLLABORATOR): they are
#            comment-CONTROLLED board writes, and on a public repo anyone
#            can comment.
#   STALL    waiting tickets whose dependency has stopped moving — a leaf in
#            a lane queue, unbound, whose blocker is unfinished, unworked and
#            untouched past SWEEP_STALL_DEPENDENCY_MINUTES, or which sits on a
#            ring of blocked-by edges with no member in flight → park
#            needs-human with a [dependency-stall] / [dependency-cycle] note
#            naming the blocker, the chain behind it, and the repairs. The gh
#            half of the binding-neutral contract the API board's reconciler
#            owns (arkho #56); its dedupe is the pass's own marker, so a
#            report never repeats until the situation it named changes.
#   DISPATCH execute-dispatch.sh --sweep (cap-bounded).
#   REVIEW   review-dispatch.sh --sweep (its own dedupe + failure caps).
#   RELAY    needs-human tickets with a bound idle session whose newest
#            REPO-SIDE issue comment (authorAssociation OWNER/MEMBER/
#            COLLABORATOR) is newer than the session's last activity and is
#            not machine-authored ([answers]/[board]/[gate] prefixes) →
#            board-answer.sh <n> --posted, backgrounded. What this selects is
#            relayed verbatim into a live session, so an outsider's comment is
#            skipped entirely — never relayed, and never allowed to shadow a
#            real answer under it. The relayed comment id is recorded in the
#            meta BEFORE relaying so a crashed relay cannot re-fire.
#   REPORT   board-reconcile.sh (read-only) into the sweep log — CLOSE?
#            candidates and orphans surface there for the human's wake.
#   GC       board-gc.sh (opt-in via WORKTREE_GC=1 / DOCKER_GC=1, else
#            skipped entirely) — removes worktrees whose branch finished
#            upstream and throwaway-DB docker debris; see its header for
#            the three-guard removal rule.
#
# Env:
#   LOCAL_REPO BOARD_REPO           as the lane dispatchers take them
#   WORKTREE_GC DOCKER_GC GC_PR_CHECKS   the GC pass (opt-in, see board-gc.sh)
#   SWEEP_STALL_MINUTES             silence threshold for a live worker (45)
#   SWEEP_STALL_DEPENDENCY_MINUTES  silence threshold for a BLOCKER before the
#                                   ticket waiting on it is parked (2880 = 48h,
#                                   the API board's DEPENDENCY_STALL_MS default)
#   SWEEP_RECOVERY_CAP              lifetime sweep resumes per daemon (3)
#   IMPLEMENT_MAX_CONCURRENT AUTO_MERGE_ENABLED
#                                   exported through to the lanes
#   SWEEP_LOG                       log file (default $DAEMON_HOME/sweep.log)
#   IMPLEMENT_DISPATCH_CMD REVIEW_DISPATCH_CMD
#   BOARD_ANSWER_CMD RECONCILE_CMD SMINOS_CLI DAEMON_HOME  (test seams)
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$SCRIPT_DIR}"
SMINOS_CLI="${SMINOS_CLI:-$(cd "$SKILL_DIR/../sminos/scripts" && pwd)/sminos}"
# ONE registry-root rule, the sminos CLI's own: $SMINOS_HOME, then $DAEMON_HOME,
# then the default. Both names are exported at the same value below, so the
# CLI, the board scripts and every child resolve one root — a pipeline that
# preferred DAEMON_HOME while sminos preferred SMINOS_HOME would have the two
# halves of one tick reading different registries.
DAEMON_HOME="${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}"
SMINOS_HOME="$DAEMON_HOME"
# The registry root moved to ~/.claude/sminos and this script scans it
# directly, so it must never be the first process to look at an empty new
# root: let sminos fold the old root in first. Idempotent, and FAIL CLOSED
# — a half-migrated registry reads as an empty fleet, which passes every
# dedupe and cap check and dispatches over live workers.
"$SMINOS_CLI" migrate --quiet || { echo "error: sminos migrate failed — refusing to sweep against a possibly half-migrated registry" >&2; exit 1; }
export SMINOS_HOME DAEMON_HOME BOARD_SCRIPTS
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
export LOCAL_REPO
# The board scripts this tick invokes bare (board-reconcile, board-answer,
# board-transition) anchor _lib.sh's BOARD_ROOT on the CURRENT directory —
# under launchd/cron the cwd is not a repo and they die at source time
# ("not inside a git repo"; REPORT failed every launchd tick, and RELAY
# would stamp its at-most-once guard and then lose the answer the same
# way). Run the whole tick from the consumer repo.
cd "$LOCAL_REPO" || { echo "error: cannot cd to LOCAL_REPO=$LOCAL_REPO" >&2; exit 1; }

# THE BINDING IS RESOLVED BEFORE THE gh PROBE, as in the lane dispatchers: an
# api-bound repo runs an entirely different tick (four phases against the board
# API, gh never invoked), so resolving BOARD_REPO through gh first would make
# that tick unreachable on a machine without the CLI. It sits AFTER the cd for
# the same reason the cd exists: _binding.sh reads .doperpowers/board.json from
# the git root of the CURRENT directory, and under launchd/cron the invocation
# cwd is not a repo at all.
# shellcheck source=_binding.sh
. "$SCRIPT_DIR/_binding.sh" || exit 1
if [ "$BOARD_BINDING" = api ]; then exec "$SCRIPT_DIR/_sweep_api.sh" all; fi

IMPLEMENT_DISPATCH_CMD="${IMPLEMENT_DISPATCH_CMD:-$SCRIPT_DIR/execute-dispatch.sh}"
REVIEW_DISPATCH_CMD="${REVIEW_DISPATCH_CMD:-$SKILL_DIR/scripts/review-dispatch.sh}"
BOARD_ANSWER_CMD="${BOARD_ANSWER_CMD:-$SCRIPT_DIR/board-answer.sh}"
RECONCILE_CMD="${RECONCILE_CMD:-$SCRIPT_DIR/board-reconcile.sh}"
GC_CMD="${GC_CMD:-$SCRIPT_DIR/board-gc.sh}"
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
#   <state>|<ticket>|<uuid>|<status>|<current>|<updated>|<recoveries>|<is-epic>
#   |<review-trail>|<review-recoveries>|<review-trail-seen>
# Review/land species are excluded here once, for every pass.
#
# The last three columns are the OWNER-IN-REVIEW ladder (pass_recover's
# in-review arm): the ticket's count of `[review-trail]` comments — the
# review's own progress signal, one per round — beside the seat's own count of
# nudges and of the trail it last reset on. The comment count costs a gh read
# per row, so it is taken only where it is read: for an `in-review` row, and
# only when the caller asks (`_bound_rows trail`). Repo-side authors only, like
# every other comment-driven decision this tick makes — on a public consumer
# repo an outsider could otherwise post `[review-trail]` and keep an abandoned
# review's ladder resetting forever.
_bound_rows() {  # [trail]
  T_TRAIL="${1:-}" python3 - <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
eps = B.epics(tickets)
want_trail = bool(os.environ.get("T_TRAIL"))
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
for p in sorted(glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    # Review/land species own their own lifecycle: review-epic- is in the
    # list because a scale reviewer that just wrote its epic's verdict
    # (done/wontfix) is still finishing its trail and cleanup, and the
    # terminal-ticket rule in pass_cancel would retire it mid-turn.
    if name.startswith("review-pr-") or name.startswith("review-epic-") \
       or name.startswith("land-pr-"):
        continue
    tk = str(m.get("ticket") or "").lstrip("#")
    if not tk or tk not in tickets:
        continue
    trail = "0"
    if want_trail and tickets[tk]["state"] == "in-review":
        trail = str(sum(1 for c in B.comments(tk)
                        if (c.get("authorAssociation") or "") in TRUSTED
                        and (c.get("body") or "").lstrip().startswith("[review-trail]")))
    print("|".join([tickets[tk]["state"], tk, m.get("uuid") or "",
                    m.get("status") or "", m.get("current") or m.get("uuid") or "",
                    str(m.get("updated") or ""), str(m.get("sweep_recoveries") or "0"),
                    "1" if tk in eps else "0", trail,
                    str(m.get("review_recoveries") or "0"),
                    str(m.get("review_trail_seen") or "0")]))
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
# A meta holding the run bearer is 0600 from creation — recreating it at the
# default umask would republish that secret, if only for the width of one
# write. Any other meta keeps the mode it already had. (Today the api tick
# execs away before this helper is reachable, so no bearer meta arrives here;
# the guard costs two lines and does not depend on that staying true.)
mode = 0o600 if m.get("run_bearer") else os.stat(p).st_mode & 0o777
tmp = p + ".tmp"
with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), "w") as f:
    json.dump(m, f, indent=2)
os.chmod(tmp, mode)   # umask narrowing, and a tmp left by an earlier crash
os.replace(tmp, p)
PY
}

_transcript() { find "$HOME/.claude/projects" -name "$1.jsonl" 2>/dev/null | head -1; }

# File mtime as epoch seconds — GNU stat first, BSD fallback. The BSD-first
# order was NOT portable: GNU `stat -f %m` treats -f as filesystem mode and
# %m as a filename, so it dumps the surviving file's filesystem status to
# stdout while exiting nonzero — the fallback's number lands AFTER that
# garbage, and arithmetic saw `File:` (every RECOVER tick with a live
# worker crashed: "line 261: File: unbound variable"). GNU `stat -c` on BSD
# fails cleanly to stderr, so this order composes; the numeric guard drops
# anything else.
_mtime_epoch() {
  local e
  e="$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null)" || return 1
  case "$e" in ''|*[!0-9]*) return 1 ;; esac
  printf '%s\n' "$e"
}

# File mtime as UTC ISO-8601 — the turn-end ordering signal for the relay pass.
_mtime_iso() {
  local e
  e="$(_mtime_epoch "$1")" || return 1
  date -u -r "$e" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "@$e" +%Y-%m-%dT%H:%M:%SZ
}

# Newest activity anywhere in a session's transcript TREE, epoch seconds;
# empty when the session has no transcript at all (callers read that as "no
# signal" and skip, exactly as they did with a missing file).
#
# The parent <uuid>.jsonl is only half the story. A session whose turn has
# ENDED while a subagent it dispatched keeps working writes nothing to its own
# file for the entire run — the harness puts the child's stream in the sibling
# directory <uuid>/subagents/agent-*.jsonl instead. So the parent-only clock
# reads a perfectly healthy delegated build as silence, and the stall arms
# below reap it: `sminos resume` stops the live turn first, killing the work,
# and the recovery cap eventually force-parks the ticket. Observed on a
# four-minute delegated build: a 3m42s hole in the parent while the child's
# file was appended to within two seconds of the return. Descendant work IS
# the session being alive, so the stall clock takes the newest mtime in the
# whole tree. (The meta's `updated` stays out of it — the sync in each caller
# bumps it, which is why the transcript is the clock in the first place.)
_activity_epoch() {  # <session-uuid>
  local tx dir newest e f
  tx="$(_transcript "$1")"
  [ -n "$tx" ] || return 0
  newest="$(_mtime_epoch "$tx" 2>/dev/null || true)"
  dir="${tx%.jsonl}"
  if [ -d "$dir" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      e="$(_mtime_epoch "$f" 2>/dev/null || true)"
      [ -n "$e" ] || continue
      if [ -z "$newest" ] || [ "$e" -gt "$newest" ]; then newest="$e"; fi
    done <<EOF
$(find "$dir" -type f 2>/dev/null)
EOF
  fi
  printf '%s' "$newest"
}

# <ticket> <uuid> <recoveries> <why> [review]
#
# The fifth argument selects the REVIEW ladder: its own counter
# (`review_recoveries`, reset by the review's own progress — see pass_recover)
# and a nudge that asks for the review rather than for the build. The two
# ladders never read or write each other's counter: a seat recovered twice
# mid-build and a review that stopped are different failures, and the second
# gets its own three attempts.
_recover() {
  local tk="$1" uuid="$2" recov="$3" why="$4" kind="${5:-build}"
  local key=sweep_recoveries role="worker" note prompt
  if [ "$kind" = review ]; then
    key=review_recoveries
    role="owner"
    note="auto-recovery exhausted: the owner $uuid was nudged $RECOVERY_CAP times about its review of this ticket's pull request and no new [review-trail] comment appeared between them ($why); review the PR by hand, or answer here to put the owner back on it"
    prompt="SWEEP RECOVERY: your review of ticket #$tk's pull request has no live QA agent ($why). Re-read the ticket and the PR, and if no review is running, dispatch doperpowers:qa-loop again per your protocol's Closing Artifact; if the review already reached a park or a verdict, restate it."
  else
    note="auto-recovery exhausted: bound worker $uuid $why $RECOVERY_CAP times; resume it by hand (sminos resume/board-answer) or re-cut to its ready-for-* lane for a fresh dispatch"
    prompt="SWEEP RECOVERY: your previous turn on ticket #$tk ended abnormally ($why). Re-read the ticket and the board state, restate your gate verdict against them in one paragraph (PLAN-EXECUTION, which ran no gate, restates plan-execution status instead), then continue your protocol from where the work actually stands. If the scope has shifted, park honestly instead."
  fi
  if [ "$recov" -ge "$RECOVERY_CAP" ]; then
    log "[sweep] RECOVER: #$tk $role $uuid $why — cap ($RECOVERY_CAP) exhausted, parking needs-human"
    # The one sanctioned cross-session transition on a LIVE binding: a stalled
    # worker at cap still holds a working meta, and the live-binding guard
    # (board-transition.sh, dp#63) refuses everyone but the owner without a
    # stated override. Recovery-exhaustion is that stated case.
    BOARD_OWNER_OVERRIDE="sweep recovery: cap exhausted on bound $role $uuid ($why)" \
      "$BOARD_SCRIPTS/board-transition.sh" "$tk" needs-human "$note" \
      >>"$SWEEP_LOG" 2>&1 \
      || log "[sweep] RECOVER: #$tk park transition FAILED (see log)"
    return
  fi
  _meta_put "$uuid" "$key" "$((recov + 1))" \
    || { log "[sweep] RECOVER: #$tk meta update failed — skipping resume"; return; }
  log "[sweep] RECOVER: #$tk $role $uuid $why — resume attempt $((recov + 1))/$RECOVERY_CAP"
  nohup "$SMINOS_CLI" resume --wait "$uuid" "$prompt" >>"$SWEEP_LOG" 2>&1 &
}

pass_recover() {
  local acted=0 state tk uuid status current recov fin tx age act
  local is_epic trail rrecov seen
  while IFS='|' read -r state tk uuid status current _ recov is_epic \
                        trail rrecov seen; do
    [ -n "$uuid" ] || continue
    case "$status" in working|blocked|error) ;; *) [ "$status" = "idle" ] || continue ;; esac
    fin="$("$SMINOS_CLI" sync "$uuid" 2>/dev/null)" || fin="noop"
    # sync says noop for an ALREADY-terminal meta (error/idle) — the
    # meta's own status is the verdict then, or the recovery ladder would
    # silently abandon exactly the failed-resume and fast-fail-spawn shapes.
    [ "$fin" = "noop" ] && fin="$status"
    case "$state" in
      in-progress|in-design)
        # An EPIC's in-progress is never a worker's own lane — it is the
        # pull's bookkeeping state (a child went active). The architect lane
        # is in-design; children own real in-progress. So an idle worker
        # bound to an epic sitting in in-progress is a FINISHED Architect
        # whose handoff the pull moved out from under it: the normal
        # decomposed-epic path is hand off to ready-for-implementer, end the
        # turn, then a child pulls the parent to in-progress — and L1's
        # stall-retire only covers the queue-state window the pull closes.
        # Resuming it would restart a worker with nothing left to do.
        if [ "$state" = "in-progress" ] && [ "${is_epic:-0}" = "1" ] && [ "$fin" = "idle" ]; then
          log "[sweep] RECOVER: #$tk is an epic pulled to in-progress and worker $uuid is idle — its handoff is done; retiring the binding instead of resuming it"
          "$SMINOS_CLI" retire "$uuid" >/dev/null 2>&1 || true
          acted=$((acted+1))
          continue
        fi
        case "$fin" in
          absent) _recover "$tk" "$uuid" "$recov" "died mid-turn (session gone)"; acted=$((acted+1)) ;;
          error)  _recover "$tk" "$uuid" "$recov" "turn errored"; acted=$((acted+1)) ;;
          idle)   _recover "$tk" "$uuid" "$recov" "finished without a board transition"; acted=$((acted+1)) ;;
          live)
            # Silence measured across the whole transcript tree: an Architect
            # past the build edge has ended its turn and is silent in its own
            # file while its plan-executor subagent works. See _activity_epoch.
            act="$(_activity_epoch "$current")"
            if [ -n "$act" ]; then
              age="$(( ( $(date +%s) - act ) / 60 ))"
              if [ "$age" -ge "$STALL_MIN" ]; then
                _recover "$tk" "$uuid" "$recov" "silent for ${age}m (stall threshold ${STALL_MIN}m)"
                acted=$((acted+1))
              fi
            fi ;;
        esac ;;
      ready-for-architect|ready-for-implementer)
        # a dead pre-gate worker frees its slot; the dispatch pass re-runs it
        case "$fin" in
          absent|error)
            log "[sweep] RECOVER: #$tk pre-verdict worker $uuid dead — retired (dispatch pass re-runs the gate fresh)"
            "$SMINOS_CLI" retire "$uuid" >/dev/null 2>&1 || true
            acted=$((acted+1)) ;;
          live)
            # Live but silent past the threshold, on a ticket sitting in a
            # lane QUEUE. A queue state is a HANDED-OFF state: whatever this
            # worker was doing, its writes on this ticket are done — the
            # ticket is waiting for the next lane's dispatch. Yet the meta
            # still binds the ticket, and execute-dispatch charges it to
            # the destination lane's slots (and refuses to dispatch a ticket
            # with a bound working worker at all), so a cap-1 lane blocks for
            # as long as the process lingers. Retire the binding — not the
            # in-flight arm's resume ladder, which exists for a worker that
            # still owns its exit. Same silence signal as that arm: the
            # transcript tree's newest mtime, the only stable turn-end clock
            # here (the meta's `updated` is bumped by the sync just above).
            # A live worker with a working subagent is not silent, on this
            # state as much as on an in-flight one.
            act="$(_activity_epoch "$current")"
            if [ -n "$act" ]; then
              age="$(( ( $(date +%s) - act ) / 60 ))"
              if [ "$age" -ge "$STALL_MIN" ]; then
                log "[sweep] RECOVER: #$tk worker $uuid is live but silent for ${age}m (threshold ${STALL_MIN}m) on a handed-off $state ticket — retiring the binding; it owns no further writes here"
                "$SMINOS_CLI" retire "$uuid" >/dev/null 2>&1 || true
                acted=$((acted+1))
              fi
            fi ;;
        esac ;;
      in-review)
        # THE OWNER'S REVIEW. What is bound to an in-review ticket here is the
        # seat that opened the PR — the review species own their own lifecycle
        # and _bound_rows dropped them — and while its QA agent runs that seat
        # is BUSY in the harness's eyes, which is why the same four verdicts
        # read the same way as on an in-flight ticket.
        #
        # The ladder is the difference, and it is bounded by the REVIEW's
        # progress rather than the seat's: the agent posts a [review-trail]
        # comment at every round's end, so a count above the one this seat last
        # saw means the nudges are landing and the count starts over. A review
        # that keeps moving is never parked for taking a long time; one that
        # has stopped reaches a human in three.
        #
        # AND A RESET THAT DID NOT PERSIST IS NOT A DECISION. Progress was
        # observed; if the write recording it failed, the count in hand is a
        # stale one that says the opposite — at the cap it would park a ticket
        # whose review had just posted a round. Nothing is spent on this
        # candidate at all until the reset lands, and the next tick re-reads
        # the same trail and tries again.
        if [ "${trail:-0}" -gt "${seen:-0}" ]; then
          if _meta_put "$uuid" review_recoveries 0 review_trail_seen "$trail"; then
            log "[sweep] RECOVER: #$tk review trail advanced (${seen:-0} → ${trail:-0}) — the owner's recovery count starts over"
            rrecov=0
          else
            log "[sweep] RECOVER: #$tk review trail advanced (${seen:-0} → ${trail:-0}) but the meta update failed — neither nudged nor parked this tick; the next one re-reads the trail"
            continue
          fi
        fi
        case "$fin" in
          absent) _recover "$tk" "$uuid" "$rrecov" "the session is gone" review; acted=$((acted+1)) ;;
          error)  _recover "$tk" "$uuid" "$rrecov" "the turn errored" review; acted=$((acted+1)) ;;
          idle)   _recover "$tk" "$uuid" "$rrecov" "its turn ended with nothing running under it" review; acted=$((acted+1)) ;;
          live)
            # Same tree-wide silence signal as the in-flight arm: the QA agent
            # writes under the seat's session directory, so a review in
            # progress is never silent.
            act="$(_activity_epoch "$current")"
            if [ -n "$act" ]; then
              age="$(( ( $(date +%s) - act ) / 60 ))"
              if [ "$age" -ge "$STALL_MIN" ]; then
                _recover "$tk" "$uuid" "$rrecov" "nothing has been written for ${age}m (stall threshold ${STALL_MIN}m)" review
                acted=$((acted+1))
              fi
            fi ;;
        esac ;;
    esac
  done <<EOF
$(_bound_rows trail | grep -E '^(in-progress|in-design|in-review|ready-for-architect|ready-for-implementer)\|' || true)
EOF
  log "[sweep] RECOVER: $acted acted"
}

pass_cancel() {
  local acted=0 state tk uuid status current recov fin
  # Every column is named, the ones this pass ignores included: the last
  # variable of a `read` takes the whole remainder, so an unnamed tail would
  # arrive inside `is_epic` the next time a column is added.
  while IFS='|' read -r state tk uuid status current _ recov is_epic _ _ _; do
    [ -n "$uuid" ] || continue
    case "$status" in working|blocked) ;; *) continue ;; esac
    fin="$("$SMINOS_CLI" sync "$uuid" 2>/dev/null)" || fin="noop"
    [ "$fin" = "live" ] || continue
    log "[sweep] CANCEL: #$tk is $state but worker $uuid still runs — retiring"
    "$SMINOS_CLI" retire "$uuid" >/dev/null 2>&1 || true
    gh issue comment "$tk" -R "$BOARD_REPO" --body \
      "[board] sweep: retired worker $uuid — the ticket reached \`$state\` while it ran. Its worktree and any committed branch are preserved." \
      >/dev/null 2>&1 || log "[sweep] CANCEL: #$tk termination comment failed"
    acted=$((acted+1))
  done <<EOF
$(_bound_rows | grep -E '^(done|wontfix)\|' || true)
EOF
  log "[sweep] CANCEL: $acted acted"
}

# An armed auto-merge lands after the QA agent's turn ended: the PR's
# "Closes #N" closes the ticket, but the label strip, terminal sweeps, and
# epic recomposition run only through board-transition — the issue sits
# closed with a residual status:* label (lint flags it) and its parent
# never recomposes. Re-derive the list from the live board and re-run the
# terminal transition; the finalize path is idempotent, so racing a
# reviewer that is still writing its own `done` is harmless.
pass_finalize() {
  local acted=0 tk st
  while IFS='|' read -r tk st; do
    [ -n "$tk" ] || continue
    log "[sweep] FINALIZE: #$tk closed as $st with residual status labels — finalizing"
    if "$BOARD_SCRIPTS/board-transition.sh" "$tk" "$st" >>"$SWEEP_LOG" 2>&1; then
      acted=$((acted+1))
    else
      log "[sweep] FINALIZE: #$tk board-transition failed (see log)"
    fi
  done <<EOF
$(python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
for t, n in sorted(tickets.items(), key=lambda kv: int(kv[0])):
    if n["state"] in B.TERMINAL and n["status_labels"]:
        print("%s|%s" % (t, n["state"]))
PY
)
EOF
  log "[sweep] FINALIZE: $acted acted"
}

pass_impact() {
  # E2 upward revision: a child worker may not write its parent — it posts
  # a [parent-impact] comment on its OWN ticket, and this pass performs
  # the parent's reconciliation return (board bookkeeping). Dedupe is a
  # [board-epic] reconcile: marker on the parent naming child@comment-id.
  #
  # The CHILD's state is not a filter. It used to be (ACTIVE only), which
  # meant the primary case never got scanned mid-flight: a spike's standard
  # exit is post-findings-then-park, and a child that parks or lands right
  # after posting its proposal left it for the Architect's end-of-epic
  # lineage check. So: every parented child is read, in any state.
  # SCAN BOUND (state file $DAEMON_HOME/sweep/impact-scan.json — a
  # SUBDIRECTORY, because the top level of DAEMON_HOME is the seat
  # record namespace: every *.json there is read as a seat record, so a
  # cursor sitting beside them showed up as a bogus fleet row in
  # `sminos list`, answered to `sminos retire impact-scan` through the
  # CLI's prefix match, and could be deleted or rewritten by sminos
  # tooling that had every right to assume it owned the file).
  # Reading every
  # child every tick cost one `gh issue view --json comments` per child: at
  # the documented ~300-ticket board size and a 5-minute cadence that is
  # 3,600+ sequential calls an hour, most of the GraphQL quota and minutes
  # added to every tick. A child is now read only when one of two things
  # holds, and BOTH are required for correctness:
  #   (a) its issue updatedAt advanced since the last completed scan — every
  #       new comment bumps it, so a fresh proposal always qualifies; or
  #   (b) the last scan saw a proposal it did not disposition (an unclaimable
  #       or invalid target). Those get no new comment, so an updatedAt
  #       cursor alone would strand them forever — this is the trap that
  #       makes a naive cursor wrong here, and `pending` is what closes it.
  # State file format (JSON, rewritten atomically at the end of a successful
  # pass; NEVER a board write):
  #   {"version": 1, "children": {"<ticket>": {"seen": "<updatedAt>",
  #                                            "pending": true|false}}}
  # `seen` is the child updatedAt at the last completed read; `pending` is
  # set when that read left a proposal undispositioned and cleared when one
  # disposes of them all. Entries for tickets that left the board are pruned.
  # A missing or corrupt file means a full rescan — the failure direction is
  # correctness, never a silent skip — and so does a pass that dies before
  # the write.
  # Remaining cost: one read per QUALIFYING child, plus one per proposal
  # TARGET (cached per tick — see markers_on).
  # The tally is printed by the python body, not counted in shell: a
  # heredoc nested inside $(...) is mis-parsed by bash 3.2 (macOS, where
  # launchd runs this) as soon as the body contains an apostrophe. It also
  # reads better — a missing tally line means the body died early, where a
  # shell-side count would have reported a confident "0 acted".
  PYTHONPATH="$BOARD_SCRIPTS" python3 - <<'PY' | tee -a "$SWEEP_LOG"
import json
import os
import re
import _board as B
# The parent states that CANNOT take the return right now. Terminal: nothing
# left to reconcile — a return would only stamp a label and a comment onto a
# closed issue. Parked: the park owns the ticket's note AND its wake-queue
# membership; unparking a needs-human parent here would destroy the human's
# question and drop it out of the relay pass's needs-human selection — in
# the same tick, since IMPACT runs first. Every skip is UNMARKED, so the
# next tick re-sees the proposal once the parent is claimable again.
UNCLAIMABLE = frozenset(B.TERMINAL) | frozenset(B.PARKED)
# The architect lane: the return is already pending (ready-for-architect) or
# an Architect is mid-claim (in-design). Re-checked per proposal, because
# the first return of this tick puts the parent here itself.
ARCHITECT_LANE = ("ready-for-architect", "in-design")
# Both scans below are comment-CONTROLLED board writes, and on a public
# consumer repo anyone can comment. An outsider's [parent-impact] would force
# reconciliation cycles at will; an outsider's pre-seeded reconcile marker
# would suppress a real proposal (the Architect's lineage check still catches
# it at end-of-epic, but mid-flight reconciliation goes silent). So both
# scans read only repo-side authors. Workers comment as the token identity,
# which is OWNER, so no legitimate path is cut; an absent field fails closed.
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")


def trusted(c):
    return (c.get("authorAssociation") or "") in TRUSTED


# A proposal names the parent whose contract it contradicts — the protocols
# pin the format `[parent-impact] #<parent> <affected clauses>: ...` — and it
# is routed to THAT ticket, not to whatever parent the child happens to point
# at now. A child can be reparented after posting (board-edge --parent), and
# consuming the proposal against the new parent did two wrong things at once:
# it yanked an unrelated epic to ready-for-architect, and it marked the REAL
# target reconciled without anyone having read it. The discovery is about
# reality, not about edge membership — a recut does not retire it. A comment
# with no parseable target falls back to the child's current parent, which is
# what every proposal written before this rule meant anyway.
TARGET_RE = re.compile(r"^\[parent-impact\]\s*#(\d+)")
# ...but only within the child's own LINEAGE. authorAssociation proves
# repo-side authorship, not truthfulness: workers post through the repo
# token, so a malformed or prompt-injected proposal could name ANY open
# ticket and this pass would move it to ready-for-architect — a write no
# LEGAL edge authorizes and nobody asked for. The admissible targets are the
# child's current native parent and the parent recorded in its `parent-pin:`
# meta (stamped at dispatch). The pin is what makes the legitimate cases
# work: it holds the OLD parent across a reparent (K3) and survives an
# orphan (L4), which is exactly when current-parent alone is not enough.
PIN_RE = re.compile(r"#(\d+)")


def lineage(node):
    out = set()
    if node.get("parent"):
        out.add(str(node["parent"]))
    # EVERY recorded parent, not just the newest: the pin accumulates across
    # reparents (execute-dispatch appends on a differing parent), and an
    # older entry is exactly what keeps an undispositioned proposal about a
    # previous parent admissible after the child was redispatched.
    pin = B.parse_meta(node.get("body") or "").get("parent-pin") or ""
    out.update(PIN_RE.findall(pin))
    return out
# Marker homes follow the TARGET, so the dedupe scan is keyed by target and
# cached per tick — one read per target rather than per (child, proposal).
seen_cache = {}


def markers_on(target):
    if target not in seen_cache:
        comments = B.comments(target)   # paginated: a marker past page 1 read
                                        # as absent re-consumes its proposal
        found = set()
        for c in comments:
            body = (c.get("body") or "").strip()
            if trusted(c) and body.startswith("[board-epic] reconcile:"):
                found.add(body.split(":", 1)[1].strip())
        seen_cache[target] = found
    return seen_cache[target]


acted = 0
tickets = B.snapshot()

STATE_DIR = os.path.join(os.environ["DAEMON_HOME"], "sweep")
STATE_PATH = os.path.join(STATE_DIR, "impact-scan.json")
try:
    with open(STATE_PATH) as f:
        _loaded = json.load(f)
    # SHAPE, not just syntax. A file holding well-formed JSON of the wrong
    # shape (`[]`, `null`, a bare string) made `.get` raise AttributeError
    # OUTSIDE this catch: the body died before the atomic rewrite, so the bad
    # file survived and every later pass died at the same line — reconciliation
    # permanently dead until a human deleted the file, the exact opposite of
    # the documented full-rescan-on-corruption. Anything that is not the
    # documented shape is discarded like a parse failure. Per-entry values are
    # filtered the same way (`prior.get` below would raise on a non-dict);
    # a dropped entry costs that one child a rescan.
    if not isinstance(_loaded, dict) or _loaded.get("version") != 1 \
       or not isinstance(_loaded.get("children"), dict):
        raise ValueError("scan state is not the documented shape")
    scan_state = {k: v for k, v in _loaded["children"].items()
                  if isinstance(v, dict)}
except (OSError, ValueError, KeyError, TypeError):
    scan_state = {}          # missing or corrupt: rescan everything
next_state = {}

for tid in sorted(tickets, key=int):
    n = tickets[tid]
    p = n.get("parent")
    if p and p not in tickets:
        continue
    prior = scan_state.get(tid) or {}
    now = str(n.get("updated_at") or "")
    if prior and prior.get("seen") == now and not prior.get("pending"):
        # Unchanged since the last completed read, and that read left nothing
        # owing. Carry its record forward untouched and skip the call.
        next_state[tid] = prior
        continue
    # No native parent is no longer a reason to skip: board-edge --orphan
    # after a proposal was posted would otherwise kill the discovery, which
    # is exactly what routing-by-named-target exists to prevent — the recut
    # does not retire what the child found. A parentless child's comments
    # have to be READ to know whether it carries one, so the read cost that
    # widened when the child-state filter went (F3) and again when the
    # parent-state filter went (K3) now covers every child with a parent
    # edge or a proposal. Same bound options if it ever matters: a per-child
    # "no proposals" marker, or a since-filter on the comment read.
    #
    # The parent-state skip that used to sit here is gone too: the proposal
    # may name a DIFFERENT parent than the one this child points at, and
    # that one can be perfectly claimable.
    # Paginated: this read is what the cursor below records as "seen". A
    # page-1 read that missed a proposal would write seen=<updatedAt> anyway
    # and skip that child forever.
    child_comments = B.comments(tid)
    proposals = [(str(c.get("id") or ""), (c.get("body") or "").lstrip())
                 for c in child_comments
                 if trusted(c)
                 and (c.get("body") or "").lstrip().startswith("[parent-impact]")]
    if not proposals:
        next_state[tid] = {"seen": now, "pending": False}
        continue
    undispositioned = 0
    for cid, body in proposals:
        m = TARGET_RE.match(body)
        target = m.group(1) if m else p
        if not target:
            # no named target and no native parent to fall back on
            print("[sweep] IMPACT: #%s carries a proposal naming no parent and "
                  "has none itself — left unmarked" % tid)
            undispositioned += 1
            continue
        marker = "#%s@%s" % (tid, cid)
        kin = lineage(n)
        if target not in kin:
            print("[sweep] IMPACT: #%s claims parent #%s, which is not in its "
                  "lineage (%s) — left unmarked" %
                  (tid, target, ", ".join("#" + k for k in sorted(kin, key=int)) or "none"))
            undispositioned += 1
            continue
        if target not in tickets:
            print("[sweep] IMPACT: #%s names parent #%s, which is not on the "
                  "board — left unmarked" % (tid, target))
            undispositioned += 1
            continue
        if marker in markers_on(target):
            continue
        tstate = tickets[target]["state"]
        if tstate in B.TERMINAL:
            # SETTLED, not pending. Terminal is the one unclaimable state that
            # never resolves on its own, so counting it as owing pinned
            # pending=true forever: this child and its target were re-read and
            # re-logged every tick, for a reconciliation that can never
            # happen. Deliberate corner — if a human reopens a wontfixed
            # parent, re-raising the impact is theirs. Nothing is destroyed:
            # the [parent-impact] comment stays on the child, so any later
            # recomposition's lineage check still finds it.
            print("[sweep] IMPACT: #%s names parent #%s, which is %s — nothing "
                  "to reconcile; left unmarked" % (tid, target, tstate))
            continue
        # Parked, or already in the architect lane: skip UNMARKED and re-see it
        # next tick. Both are transient and say nothing, so neither logs.
        if tstate in UNCLAIMABLE or tstate in ARCHITECT_LANE:
            undispositioned += 1
            continue
        ln = B.apply_state(
            tickets, target, "ready-for-architect",
            "reconciliation-due: [parent-impact] from #%s" % tid,
            bookkeeping=True)
        B.comment(target, "[board-epic] reconcile: %s" % marker)
        markers_on(target).add(marker)
        acted += 1
        print("[sweep] IMPACT: %s" % ln)
    next_state[tid] = {"seen": now, "pending": undispositioned > 0}
print("[sweep] IMPACT: %d acted" % acted)
# Rewritten atomically, and only now: a pass that died earlier leaves the old
# file (or none) and the next tick re-reads more than it strictly must, which
# is the harmless direction.
try:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"version": 1, "children": next_state}, f)
    os.replace(tmp, STATE_PATH)
except OSError as e:
    print("[sweep] IMPACT: scan-state write failed (%s) — next tick rescans" % e)
PY
}

# STALL — a dependency wait is BOUNDED. The board already refuses to draw a
# ticket whose blocker is unfinished (B.eligible), and that refusal is the
# whole of what it does about the wait: nothing ages it, nothing asks whether
# the blocker is still moving, nothing tells a human when it is not. A ticket
# whose blocker never lands — parked and unanswered, shelved `deferred`,
# closed `wontfix` (which gh's own eligibility never accepts as landed),
# reclaimed and never resumed, or caught in a ring — sits in its queue
# forever, owned by nobody and reported to nobody. The dependency yield
# (dp#146) lets a worker put its own ticket there without a human ever
# having looked at it.
#
# The contract is binding-neutral doctrine — arkho #56, whose reconciler pass
# owns it on the API board (`docs/specs/2026-09-14-dependency-stall-design.md`,
# Design 1-3). This is its gh half. The API board has a ledger, an owner_run
# column and a server; gh has none of the three, so each predicate is
# translated to a signal the sweep ALREADY reads:
#
#   activity(B)   the newest `updatedAt` over B's SUBTREE. GitHub bumps it on
#                 every comment, label, body edit and state change, which is
#                 what the ledger is for on the other binding — and the IMPACT
#                 pass above already trusts it as a per-child scan cursor. The
#                 subtree clause is for an epic blocker: a decomposed epic's
#                 own row goes quiet while its children do the work.
#   being worked  a binding on B or anything under it that is still somebody's
#                 responsibility — gh's owner_run, read out of the daemon
#                 registry here rather than through B.live_bound_tickets(),
#                 because two qualifiers that reader does not make are
#                 load-bearing for this pass. The registry is MACHINE-GLOBAL
#                 and a board is not, so a meta counts only once its own board
#                 identity matches ours: ticket numbers collide across repos as
#                 a matter of course, and a neighbouring checkout's worker on
#                 ITS #42 must not silence this board's report about OUR #42.
#                 And the recovery LADDER is read, not just the status — the
#                 RECOVER pass backgrounds `sminos resume` and returns within
#                 this same tick, so a binding it is still recovering reads
#                 `idle`/`error` here and must count as worked. The exhausted
#                 ladder is the exclusion that matters in the other direction:
#                 when RECOVER gives up it parks the blocker `needs-human`
#                 itself, and a blocker nobody will ever resume is precisely
#                 the stall root this pass exists to report. A dead binding
#                 must never suppress a report forever.
#   chain link    a blocker whose wait is somebody else's report: a waiting
#                 leaf (a candidate in its own right, whose own blocker gets
#                 its own turn) or a ticket this pass already parked. The
#                 second is read from the park NOTE, which the snapshot
#                 carries for free and which board-show puts in front of a
#                 human anyway. Only the link NEAREST the stuck root fires, so
#                 a five-deep chain is one park, not five.
#   reported      the pass's own marker comment, and it records the blocker
#                 ACTIVITY it reported (`marker: stall #42@<iso>`) rather than
#                 leaning on the comment clock. "Not again until the situation
#                 changes" is then a string comparison — and it is the only
#                 dedupe available for a ring, which has no timestamp at all.
#
# Two signals, because they have different false-positive profiles. The CYCLE
# is structural and needs no clock: a ring of blocked-by edges among
# unfinished tickets can never resolve itself. It fires only once NO member is
# in flight — an in-flight member can still be finished by its worker or
# resumed. The STALL is temporal and judges the BLOCKER's silence, not the
# waiter's age: a four-day build with a live worker is a normal wait however
# long it lasts. The waiting ticket's own wait must reach the threshold too,
# so a ticket that yields TODAY onto a blocker silent for a week is reported
# one threshold from now, not within minutes of the worker putting it down.
#
# ONE unfinished-blocker predicate, and it is gh's, not the spec's: B.eligible
# draws a ticket only when every blocker is `done`, so a `wontfix` blocker —
# and a blocker that is not on this board at all — strands its waiter exactly
# as a live one does. Reading TERMINAL here (the API board's rule) would make
# the most permanent gh stall the one case this pass cannot see.
#
# Mechanical, no model calls, idempotent per tick. Comment reads happen only
# for a candidate that is otherwise DUE, so a board with nothing stranded
# costs this pass zero gh calls beyond the snapshot every pass shares.
pass_stall() {
  PYTHONPATH="$BOARD_SCRIPTS" \
  T_STALL_DEP_MIN="${SWEEP_STALL_DEPENDENCY_MINUTES:-2880}" \
  T_RECOVERY_CAP="$RECOVERY_CAP" \
  python3 - <<'PY' | tee -a "$SWEEP_LOG"
import datetime
import glob
import json
import os
import re
import _board as B
import _board_api as BA

# Minutes. 2880 = 48h, the same number DEPENDENCY_STALL_MS defaults to on the
# API board: one doctrine, one threshold. A non-numeric or non-positive value
# falls back rather than firing instantly — a misconfigured threshold must not
# park a whole board's worth of normal waits.
try:
    THRESHOLD = int(os.environ.get("T_STALL_DEP_MIN") or 0)
except ValueError:
    THRESHOLD = 0
if THRESHOLD <= 0:
    THRESHOLD = 2880

# The RECOVER ladder's own cap, passed in from the shell so the two passes
# cannot disagree about when a recovery has given up. Parsed defensively like
# the threshold, except that 0 is honoured: a deployment that sets the cap to
# zero has disabled auto-recovery, and every idle binding on it really is
# nobody's. Only a garbled value falls back.
try:
    RECOVERY_CAP = int(os.environ.get("T_RECOVERY_CAP", ""))
except ValueError:
    RECOVERY_CAP = 3
if RECOVERY_CAP < 0:
    RECOVERY_CAP = 3

# This board's identity in the machine-global registry. gh mode's `board` key
# is the whole identity — there is no repo dimension to add (meta_is_mine).
BOARD = "gh:" + (os.environ.get("BOARD_REPO") or "")

TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
# The park note's opening marker, which is also how a chain link is
# recognised; and the machine tail the dedupe reads back.
NOTE_RE = re.compile(r"\[dependency-(stall|cycle)\]")
MARKER_RE = re.compile(r"marker: (stall|cycle) ([^\n]*)")

def worked_tickets():
    """Ticket numbers this BOARD still counts as somebody's responsibility.

    Deliberately not B.live_bound_tickets(): that reader is board-blind (it
    returns numbers from every repository on the machine) and it counts only
    `working`/`blocked`, which reads a recovery still in flight as an
    abandoned binding. Both directions matter here — the first would suppress
    a real report because of a stranger's worker, the second would file one
    against a blocker that is being resumed right now. Unreadable and
    malformed metas are skipped; a meta with no board stamp is legacy and
    reads as ours, which is meta_is_mine's documented safe direction.
    """
    home = (os.environ.get("SMINOS_HOME") or os.environ.get("DAEMON_HOME")
            or os.path.expanduser("~/.claude/sminos"))
    out = set()
    for path in glob.glob(os.path.join(home, "*.json")):
        if path.endswith(".reply.json"):
            continue
        try:
            with open(path) as f:
                m = json.load(f)
        except (ValueError, OSError):
            continue
        if not BA.meta_is_mine(m, BOARD):
            continue
        status = str(m.get("status") or "")
        if status not in ("working", "blocked"):
            # `idle`/`error` is where a binding sits between RECOVER's
            # backgrounded resume and the resumed process actually launching,
            # so it counts as worked for as long as the ladder has a rung
            # left. Once the ladder is exhausted RECOVER parks the blocker
            # itself and stops trying — nothing is coming, and the binding
            # must stop suppressing this pass. Anything else (`retired`, and
            # any status the registry grows later) is nobody's.
            if status not in ("idle", "error"):
                continue
            try:
                recoveries = int(m.get("sweep_recoveries") or 0)
            except (TypeError, ValueError):
                recoveries = 0
            if recoveries >= RECOVERY_CAP:
                continue
        t = str(m.get("ticket") or "").lstrip("#")
        if t:
            out.add(t)
    return out


tickets = B.snapshot()
live = worked_tickets()
UTC = datetime.timezone.utc
cutoff = (datetime.datetime.now(UTC)
          - datetime.timedelta(minutes=THRESHOLD)).strftime("%Y-%m-%dT%H:%M:%SZ")

kids = {}
for _t, _n in tickets.items():
    if _n.get("parent"):
        kids.setdefault(_n["parent"], []).append(_t)


def iso(s):
    """A GitHub timestamp normalized to one comparable width. Every value in
    play is `YYYY-MM-DDTHH:MM:SSZ`, so ordering is lexicographic and no
    parsing is needed — which also makes the string itself the dedupe key."""
    s = str(s or "")
    return (s[:19] + "Z") if len(s) >= 19 else ""


def subtree(t):
    """t and everything under it. Cycle-safe, and tolerant of an id that is
    not on this board — a blocked-by can point at a transferred, deleted, or
    another repository's issue."""
    out, stack = set(), [t]
    while stack:
        x = stack.pop()
        if x in out:
            continue
        out.add(x)
        stack.extend(kids.get(x, ()))
    return out


def activity(t):
    """Newest issue activity over t's subtree, as a timestamp string; "" when
    nothing on the board says (an off-board blocker). "" sorts below every
    real timestamp, which is the right reading: an issue this board cannot
    see can never be observed to move.

    One deliberate reading: a park THIS pass writes onto a ticket that happens
    to sit inside the blocker's subtree bumps that ticket's `updatedAt`, and
    that is bookkeeping, not progress on the blocker — so the snapshot is not
    re-read to pick it up within a tick. The honest cost is that a LATER tick
    does see the timestamp and reads the subtree as active, buying the wait
    one more threshold of patience before it is reported again."""
    best = ""
    for x in subtree(t):
        n = tickets.get(x)
        if n:
            u = iso(n.get("updated_at"))
            if u > best:
                best = u
    return best


def being_worked(t):
    return any(x in live for x in subtree(t))


def unfinished(b):
    return tickets.get(b, {}).get("state") != "done"


def waiting(t):
    """A candidate: a leaf in a lane queue, nobody bound to it, with at least
    one unfinished blocker. Exactly the set B.eligible refuses to draw.
    Leaves only — an epic in a queue waits on its CHILDREN, and the epic
    passes judge that."""
    n = tickets.get(t)
    return bool(n) and n["state"] in B.DISPATCHABLE and t not in live \
        and not kids.get(t) \
        and any(unfinished(b) for b in n["blocked_by"])


def chain_link(b):
    # A waiting EPIC is NOT a link: this pass never visits epics, so nobody
    # else would report its wait. It is a root, judged by its own subtree.
    n = tickets.get(b)
    if not n:
        return False
    if waiting(b):
        return True
    return n["state"] == "needs-human" \
        and NOTE_RE.match((n.get("note") or "").strip()) is not None


def dispatch_pending(b):
    """The blocker sits in a lane queue with nothing holding it back — the
    DISPATCH pass owns its liveness, not this one.

    This clause has no counterpart in the API board's pass, and it is the
    difference between the two queues. There, claimNext draws an eligible
    ticket within seconds. Here a lane is cap-bounded and a ticket can sit in
    `ready-for-implementer` for days purely because the slots are full — the
    ordinary "do A before B" edge with A still queued. Without this clause,
    every ticket behind a lane backlog is parked once the backlog is two days
    old: a report about dispatch capacity dressed up as a dependency failure.
    With it, this and chain_link read as one rule — a blocker sitting in a
    lane QUEUE is never a stall root, because it waits either on its own
    blocker (somebody else's report) or on a dispatch slot (somebody else's
    pass)."""
    return b in tickets and B.eligible(tickets, b)


def stalled(b):
    return unfinished(b) and not being_worked(b) and not chain_link(b) \
        and not dispatch_pending(b) and activity(b) < cutoff


_reports = {}


def reports(t):
    """This pass's own markers on a ticket — [(kind, payload)]. Read from the
    COMMENT trail, not the note: a human who re-queues the ticket by hand
    overwrites the note, and losing the dedupe there would re-park the ticket
    the moment they put it back."""
    if t not in _reports:
        found = []
        for c in B.comments(t):
            if (c.get("authorAssociation") or "") not in TRUSTED:
                continue
            m = MARKER_RE.search(c.get("body") or "")
            if m:
                found.append((m.group(1), m.group(2).strip()))
        _reports[t] = found
    return _reports[t]


def hours_since(a):
    """Whole hours from timestamp string `a` to now; "?" when a is unknown."""
    try:
        then = datetime.datetime.strptime(a[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return "?"
    d = datetime.datetime.now(UTC) - then.replace(tzinfo=UTC)
    return str(int(d.total_seconds() // 3600))


# blocked-by over UNFINISHED, on-board tickets, both directions. An edge into
# a landed ticket is not a wait, and a ring through one is not a deadlock.
fwd, rev = {}, {}
for _t, _n in tickets.items():
    if not unfinished(_t):
        continue
    for _b in _n["blocked_by"]:
        if _b in tickets and unfinished(_b):
            fwd.setdefault(_t, []).append(_b)
            rev.setdefault(_b, []).append(_t)


def reach(start, graph, through=None):
    out, stack = set(), list(graph.get(start, ()))
    while stack:
        x = stack.pop()
        if x in out or (through is not None and not through(x)):
            continue
        out.add(x)
        stack.extend(graph.get(x, ()))
    return out


def ring_walk(t, members):
    """One closed walk t -> ... -> t through the members, for the note.

    DEPTH-FIRST, WITH BACKTRACKING. A greedy forward walk strands itself on
    any component that branches: it takes one exit, dead-ends at a member
    whose every successor is already visited, and the only way to finish is
    to append the start — naming a blocked-by link that does not exist. The
    note is read by a human deciding which edge to cut, so a fabricated edge
    is worse than no walk at all. Every step returned here is a real edge,
    the closing one included. Successors in ascending numeric order, so a
    given ring reads the same on every tick. The ring is already known to
    exist when this is called; if the search somehow exhausts anyway it
    returns the degenerate [t] rather than inventing the link back."""
    seen = {t}

    def step(path):
        for b in sorted(fwd.get(path[-1], ()), key=int):
            if b == t and len(path) > 1:
                return path + [t]
            if b in members and b not in seen:
                seen.add(b)
                got = step(path + [b])
                if got:
                    return got
                seen.discard(b)
        return None

    return step([t]) or [t]


def park(tid, kind, note):
    # No pre-park: the ticket is UNBOUND, so there is no session to resume and
    # no in-flight state to return it to. Its lane queue is where it belongs
    # once the blocker lands, and board-answer refuses an unbound park anyway
    # — the note names the by-hand path instead.
    ln = B.apply_state(tickets, tid, "needs-human", note,
                       extra_meta={"pre-park": None})
    print("[sweep] STALL: %s (%s)" % (ln, kind))


acted = 0
for tid in sorted([t for t in tickets if waiting(t)], key=int):
    if not waiting(tid):        # a park earlier in this loop moved it
        continue
    n = tickets[tid]
    lane = n["state"]

    # ---- 1. the cycle: structural, no clock, outranks the stall ----------
    # This block either PARKS a ring or FALLS THROUGH. It never skips the
    # ticket: every reason a ring declines to park — a member still in flight,
    # this ticket not being the ring's representative, the ring already
    # reported — says nothing about whether THIS ticket's own wait has gone
    # stale, and arkho #56 is explicit that a ring member which is in flight,
    # unowned and silent past the threshold is a stalled root the STALL rule
    # below must catch. That is how a never-resumed member is found at all.
    # Nothing doubles up, because the chain-link rule already absorbs the
    # redundant shapes: a ring member sitting in a lane QUEUE is a waiting
    # leaf, and a parked representative is `needs-human` carrying a
    # [dependency- note, so neither can be a stall root. Only a genuinely
    # stuck non-queue member — an old unbound `in-progress`, say — becomes
    # one, which is exactly the case the spec wants reported.
    members = set()
    if tid in reach(tid, fwd):
        members = {tid} | (reach(tid, fwd) & reach(tid, rev))
    if members:
        ordered = sorted(members, key=int)
        # A ring with an in-flight member is not yet a deadlock: that member
        # can still be finished by its worker (a close applies no blocker
        # check) or resumed. Otherwise one park per ring, on a deterministic
        # member — the lowest-numbered one this pass is able to write. The
        # parked representative stays a member (it is non-terminal), so
        # without the ring-wide dedupe below, the next candidate in this same
        # loop would be parked next, and the next. The dedupe's comment read
        # is deliberately the last thing tried, so a ring that is not a park
        # candidate at all costs nothing.
        reps = [m for m in ordered if waiting(m)]
        if not any(tickets[m]["state"] in B.ACTIVE for m in ordered) \
           and reps and reps[0] == tid:
            edges = ["%s>%s" % (a, b) for a in ordered
                     for b in fwd.get(a, ()) if b in members]
            payload = " ".join(
                sorted(edges, key=lambda e: [int(x) for x in e.split(">")]))
            if not any(("cycle", payload) in reports(m) for m in ordered):
                note = ("[dependency-cycle] %s: every member waits on another, "
                        "none is in flight, so none can be claimed and a run "
                        "cannot cut an edge. Members: %s. Repairs: cut one "
                        "edge (board-edge.sh <x> --unblock <y>) or close a "
                        "member; re-queueing #%s alone leaves the ring "
                        "standing. marker: cycle %s"
                        % (" -> ".join("#" + x
                                       for x in ring_walk(tid, members)),
                           ", ".join("#%s (%s)" % (m, tickets[m]["state"])
                                     for m in ordered),
                           tid, payload))
                park(tid, "dependency-cycle", note)
                _reports.setdefault(tid, []).append(("cycle", payload))
                acted += 1
                continue

    # ---- 2. the stall: temporal, on the BLOCKER's silence ----------------
    # The waiting ticket's own wait has to reach the threshold too. Its
    # `updatedAt` is where that wait starts: the yield's label write, body
    # write and note comment all bump it, and so does a human re-queueing the
    # ticket by hand after reading a previous report.
    if iso(n.get("updated_at")) >= cutoff:
        continue
    due = []
    for b in sorted(set(n["blocked_by"]), key=int):
        if not stalled(b):
            continue
        act = activity(b)
        key = "#%s@%s" % (b, act or "-")
        if any(k == "stall" and key in p for k, p in reports(tid)):
            continue        # reported, and the blocker has not moved since
        due.append((b, act, key))
    if not due:
        continue
    # The chain BEHIND this ticket. Only the link nearest the stuck root
    # fires, so these never get a report of their own — they are named here
    # instead.
    behind = sorted(reach(tid, rev, through=waiting), key=int)
    clauses = []
    for b, act, _k in due:
        bn = tickets.get(b)
        if bn is None:
            clauses.append("#%s, which is not on this board (transferred, "
                           "deleted, or another repository's) — no `done` can "
                           "ever land on it" % b)
        else:
            clauses.append("#%s, which is %s, unworked, and untouched since "
                           "%s (%sh)" % (b, bn["state"], act, hours_since(act)))
    blockers = " / ".join("#" + b for b, _a, _k in due)
    note = ("[dependency-stall] #%s has waited in %s since %s on %s "
            "(threshold %sh). %sRepairs: cut the edge (board-edge.sh %s "
            "--unblock %s), move %s along, or comment the answer and re-queue "
            "by hand (board-transition.sh %s %s \"<why>\") — this report does "
            "not repeat until %s moves. marker: stall %s"
            % (tid, lane, iso(n.get("updated_at")), "; ".join(clauses),
               THRESHOLD // 60,
               ("Also waiting behind #%s: %s. "
                % (tid, ", ".join("#" + x for x in behind))) if behind else "",
               tid, due[0][0], blockers, tid, lane, blockers,
               " ".join(k for _b, _a, k in due)))
    park(tid, "dependency-stall", note)
    _reports.setdefault(tid, []).append(
        ("stall", " ".join(k for _b, _a, k in due)))
    acted += 1

print("[sweep] STALL: %d acted" % acted)
PY
}

pass_relay() {
  local acted=0 state tk uuid status current recov fin tx turn_end verdict cid
  # Named to the end of the row for the reason pass_cancel names its tail.
  while IFS='|' read -r state tk uuid status current _ recov is_epic _ _ _; do
    [ -n "$uuid" ] || continue
    # Normalize first: a --no-wait worker that parked leaves its meta
    # status=working forever (nothing else syncs it). Only a genuinely
    # ended turn is resumable; sync prints noop for already-terminal
    # metas, so fall back to the meta's own status.
    case "$status" in working|blocked|idle) ;; *) continue ;; esac
    fin="$("$SMINOS_CLI" sync "$uuid" 2>/dev/null)" || fin="noop"
    [ "$fin" = "noop" ] && fin="$status"
    [ "$fin" = "idle" ] || continue
    # Turn-end ordering signal: the current turn's transcript mtime. It is
    # stable once the turn ends, and — unlike the meta's `updated` field,
    # which the sync above just bumped — it cannot postdate (and so
    # hide) the human's answer. Comments from before the turn ended are
    # the worker's own trail, never an answer to relay.
    tx="$(_transcript "$current")"
    [ -n "$tx" ] || continue
    turn_end="$(_mtime_iso "$tx")" || continue
    verdict="$(PYTHONPATH="$BOARD_SCRIPTS" T_TK="$tk" T_TURN_END="$turn_end" \
      T_UUID="$uuid" python3 -c '
import json, os, sys
import _board as B
TRUSTED = ("OWNER", "MEMBER", "COLLABORATOR")
# Paginated, like the other comment-controlled reads. This one selects the
# NEWEST trusted comment, so a page cap hits it hardest: the newest comments
# are exactly what a first-page read hides, and the answer is then missed
# outright or an older comment is taken for the newest and relayed verbatim
# into a live session. A read that fails at all exits non-zero here (B.gh
# dies), which the caller turns into "no relay" — the same silence the old
# suppressed-stderr read produced.
comments = B.comments(os.environ["T_TK"])
# The candidate is the newest TRUSTED comment. This is the widest of the
# board comment-controlled reads: what it selects is relayed VERBATIM into a
# live worker session, and on a public consumer repo anyone can comment. An
# outsider is therefore not merely un-relayable — it must not SHADOW a real
# answer either, so untrusted comments are skipped rather than allowed to end
# the scan. Every board, worker and human write here is the token identity or
# a repo member.
cand = None
for c in reversed(comments):
    if (c.get("authorAssociation") or "") in TRUSTED:
        cand = c
        break
if cand is None:
    sys.exit(0)
body = (cand.get("body") or "").lstrip()
if body.startswith(("[answers]", "[board]", "[board-epic]", "[gate]", "[findings]")):
    sys.exit(0)
if str(cand.get("createdAt") or "") <= os.environ["T_TURN_END"]:
    sys.exit(0)
home = os.environ["DAEMON_HOME"]
meta = json.load(open(os.path.join(home, os.environ["T_UUID"] + ".json")))
if str(meta.get("relayed_comment") or "") == str(cand.get("id") or ""):
    sys.exit(0)
print(cand.get("id") or "")' 2>/dev/null)" || verdict=""
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

# SURFACE — the PR-diff matching moment (spec: surface topology). Ordered
# BEFORE dispatch: a diff-derived label must exist before dispatch decisions
# read it, or it always arrives one dispatch too late. Three jobs, all inert
# without a .doperpowers/surfaces.md registry on the default branch:
#   1. add-only labeling from open linked PR diffs (removal is never
#      automatic — an early-WIP diff must not un-serialize a mid-flight
#      ticket; stale labels are lint WARNs a human clears);
#   2. retroactive relates edges between label-mates, only when NEITHER side
#      has a live bound worker (update_meta is a full-body RMW), capped per
#      tick — the remainder lands next tick;
#   3. queue-depth watch: >= 3 open implement-lane tickets on one surface
#      with no open architect-lane ticket carrying it → REGISTER a
#      consolidation ticket (ready-for-architect) naming the members. The
#      label on that ticket is the structural dedupe — its existence
#      suppresses re-registration; no marker to drift.
pass_surface() {
  local line surface members bodyf out num
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    case "$line" in
      CONSOLIDATE\ *)
        surface="$(printf '%s' "$line" | cut -d' ' -f2)"
        members="$(printf '%s' "$line" | cut -d' ' -f3-)"
        bodyf="$(mktemp)"
        { printf '## Problem & intent\n\n'
          printf 'The surface `%s` (see `.doperpowers/surfaces.md`) carries %s open implement-lane tickets: %s.\n' \
            "$surface" "$(printf '%s\n' "$members" | wc -w | tr -d ' ')" "$members"
          printf 'Three or more parallel tickets on one contested seam means patch-wise work has outgrown the seam — parallel rewrites of one body revert each other silently. This ticket owns the unified redesign: one contract, the members re-cut as its slices or closed.\n\n'
          printf '## Constraints\n\n- Registered mechanically by the board sweep (queue-depth watch). The member list is the evidence; verify it against the live board before designing.\n\n'
          printf '## Success criteria\n\n- A single contract for the surface exists and every member ticket is a slice of it or is closed with a reason.\n'
        } > "$bodyf"
        out="$("$SCRIPT_DIR/board-register.sh" "surface $surface: consolidation redesign (queue-depth auto)" \
                enhancement P1 --state ready-for-architect --surface "$surface" --body-file "$bodyf" 2>&1)" \
          && num="${out%% *}" \
          && log "[sweep] SURFACE: consolidation #$num registered for $surface (members: $members)" \
          || log "[sweep] SURFACE: consolidation register failed for $surface"
        rm -f "$bodyf"
        ;;
      *) log "$line" ;;
    esac
  done <<EOF
$(BOARD_SCRIPTS="$BOARD_SCRIPTS" T_LOCK_ROOT="$(board_store_dir surface-locks)" \
  python3 - <<'PY'
import json
import os
import sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
import _board_api as BA
reg = B.surfaces_registry()
if reg is None:
    print("[sweep] SURFACE: no registry — skipped")
    raise SystemExit(0)
tickets = B.snapshot()
live = B.live_bound_tickets()
epics = {t for t in tickets if any(
    tickets[c].get("parent") == t for c in tickets)}
labeled = 0
for tid in sorted(tickets, key=int):
    n = tickets[tid]
    if n["state"] in B.TERMINAL:
        continue
    open_prs = [p for p in n["prs"] if p["state"] == "OPEN"]
    if not open_prs:
        continue
    paths = []
    for p in open_prs:
        try:
            # --slurp wraps each page in one outer array — without it a
            # multi-page diff is concatenated arrays json.loads rejects,
            # and the silent skip would leave the PR unserialized.
            pages = json.loads(B.gh(["api", "--paginate", "--slurp",
                                     "repos/%s/pulls/%s/files"
                                     % (B.repo(), p["num"])]))
        except (SystemExit, ValueError):
            continue
        files = [f for page in pages or [] for f in page or []]
        for f in files:
            # A rename contributes BOTH names: previous_filename is how a
            # file renamed OUT of a surface still marks the ticket.
            paths.append(f.get("filename") or "")
            if f.get("previous_filename"):
                paths.append(f["previous_filename"])
    for s in [x for x in B.match_paths(reg, paths) if x not in n["surfaces"]]:
        B.ensure_surface_label(s)
        B.edit_labels(tid, add=(B.SURFACE_PREFIX + s,))
        n["surfaces"].append(s)
        labeled += 1
        print("[sweep] SURFACE: #%s += surface:%s (PR diff)" % (tid, s))
# Retroactive relates between label-mates — the backstop for edges the
# register moment deferred (live workers) or never saw (diff-derived
# labels). Bounded per tick: body writes are the expensive, racy resource.
writes = 0
# KEYED BY BINDING, and handed in rather than resolved here: this is the
# same store the dispatcher's _surf_lock takes, so both sides have to agree
# on the path down to the digest or the lock serializes nothing.
lock_root = os.environ["T_LOCK_ROOT"]
# Registered names only, here and in the queue-depth watch below: an
# orphaned label (entry deleted, or invented — lint FAILs it) must not
# drive body writes, and a CONSOLIDATE on it would register with a
# --surface hint that matches nothing — an unlabeled consolidation the
# structural dedupe can never see, duplicated every tick.
for s in sorted({x for n in tickets.values() for x in n["surfaces"]} & set(reg)):
    mates = [t for t in tickets if s in tickets[t]["surfaces"]
             and tickets[t]["state"] not in B.TERMINAL]
    if len(mates) < 2:
        continue
    # The dispatcher holds this same lock across its occupancy-check →
    # spawn window (including the parent-pin body stamp) — taking it here
    # is what keeps these relates RMWs from racing a dispatch. Contention
    # or a fresh live worker → skip; next tick converges.
    lock = os.path.join(lock_root, s)
    # A dispatch started before the locks were keyed holds the FLAT path;
    # taking the keyed name beside it would race the very body writes this
    # lock serializes. Probed, never created.
    if BA.flat_surface_lock_held(s):
        continue
    try:
        os.mkdir(lock)
    except OSError:
        continue
    try:
        live_now = B.live_bound_tickets()
        for i, a in enumerate(mates):
            for b in mates[i + 1:]:
                if writes >= 8:
                    break
                # Each SIDE is checked and repaired independently — a
                # one-sided edge (a crashed prior tick) must converge, not
                # be skipped as "already related".
                for src_t, dst in ((a, b), (b, a)):
                    if dst in tickets[src_t]["relates_to"]:
                        continue
                    if src_t in live_now:
                        continue
                    B.update_meta(src_t, tickets[src_t],
                                  **{"relates-to": " ".join(
                                      "#%s" % r for r in
                                      tickets[src_t]["relates_to"] + [dst])})
                    tickets[src_t]["relates_to"].append(dst)
                    writes += 1
                    print("[sweep] SURFACE: related #%s -> #%s (%s)"
                          % (src_t, dst, s))
    finally:
        os.rmdir(lock)
# Members = every ticket still in the rewrite race. Parks COUNT — a
# needs-human/needs-info rewrite resumes into its lane without another
# registration or search; only deferred, terminal, spike, epic, and the
# architect lane (the resolver) are out.
ARCH_STATES = ("ready-for-architect", "in-design")
OUT_STATES = B.TERMINAL + ARCH_STATES + ("deferred",)
for s in sorted({x for n in tickets.values() for x in n["surfaces"]} & set(reg)):
    members = [t for t in sorted(tickets, key=int)
               if s in tickets[t]["surfaces"]
               and tickets[t]["state"] not in OUT_STATES
               and tickets[t]["category"] != "spike" and t not in epics]
    if len(members) < 3:
        continue
    # Structural dedupe covers the consolidation's WHOLE open lifecycle:
    # architect states before decompose, epic-with-children after (decompose
    # moves it to ready-for-implementer while members stay open — arch-states
    # alone re-registered every tick from that moment).
    if any(s in tickets[t]["surfaces"]
           and tickets[t]["state"] not in B.TERMINAL
           and (tickets[t]["state"] in ARCH_STATES or t in epics)
           for t in tickets):
        continue
    print("CONSOLIDATE %s %s" % (s, " ".join("#%s" % m for m in members)))
print("[sweep] SURFACE: %d labeled" % labeled)
PY
)
EOF
}

pass_recover  || log "[sweep] RECOVER pass errored (continuing)"
pass_cancel   || log "[sweep] CANCEL pass errored (continuing)"
pass_finalize || log "[sweep] FINALIZE pass errored (continuing)"
pass_impact   || log "[sweep] IMPACT pass errored (continuing)"
pass_stall    || log "[sweep] STALL pass errored (continuing)"
pass_surface  || log "[sweep] SURFACE pass errored (continuing)"
"$IMPLEMENT_DISPATCH_CMD" --sweep 2>&1 | tee -a "$SWEEP_LOG" \
  || log "[sweep] DISPATCH pass errored (continuing)"
"$REVIEW_DISPATCH_CMD" --sweep 2>&1 | tee -a "$SWEEP_LOG" \
  || log "[sweep] REVIEW pass errored (continuing)"
pass_relay    || log "[sweep] RELAY pass errored (continuing)"
"$RECONCILE_CMD" 2>&1 | tee -a "$SWEEP_LOG" >/dev/null \
  || log "[sweep] REPORT pass errored (continuing)"
if [ "${WORKTREE_GC:-0}" = 1 ] || [ "${DOCKER_GC:-0}" = 1 ]; then
  "$GC_CMD" 2>&1 | tee -a "$SWEEP_LOG" \
    || log "[sweep] GC pass errored (continuing)"
fi
log "[sweep] tick complete"
