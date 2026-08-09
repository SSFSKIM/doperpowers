#!/usr/bin/env bash
# board-sweep.sh — the unattended tick: one idempotent pass over the board
# and the daemon registry, run by cron/launchd every ~5 minutes. Mechanical
# only — no model calls, no judgment; every action re-derives its work-list
# from durable state (GitHub + registry metas), so overlapping or repeated
# ticks are safe and a restart loses nothing.
#
# Passes, each independently guarded so one failure never stops the rest:
#   RECOVER  in-flight tickets (in-progress, in-design) with a bound
#            implement/architect/spike worker that is dead (finalize:
#            absent/error), silent past the stall timeout, or finished
#            without a board transition → bounded resume (a nudge on the SAME
#            session — context intact), 3 lifetime attempts per daemon, then
#            park needs-human with an orientation note. A worker on a
#            still-pre-verdict (ready-for-*) ticket is just retired — dead,
#            or live-but-silent past the stall threshold on a state it has
#            already handed off — and the dispatch pass fresh-dispatches it
#            (re-orientation is cheap pre-verdict; a lingering binding is
#            not, it holds the destination lane's slot).
#   CANCEL   live implement/spike workers whose ticket reached a terminal
#            state (done/wontfix) → retire + a [board] termination comment.
#            Park states never cancel (park = pause); review-pr-*,
#            review-epic-* and land-pr-* workers own their own lifecycle
#            (the reviewer IS what put the ticket in its terminal state)
#            and are never board-cancelled.
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
#   DISPATCH implement-dispatch.sh --sweep (cap-bounded).
#   REVIEW   review-dispatch.sh --sweep (its own dedupe + failure caps).
#   LAND     open confident-ready PRs with a human APPROVED review or a
#            `land` label, and NO land-pr-<n> meta yet → land-dispatch.sh.
#            One sweep attempt per PR — a dead lander is a wake item, not a
#            retry loop.
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

IMPLEMENT_DISPATCH_CMD="${IMPLEMENT_DISPATCH_CMD:-$SKILL_DIR/../implementing/scripts/implement-dispatch.sh}"
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
#   <state>|<ticket>|<uuid>|<status>|<current>|<updated>|<recoveries>|<is-epic>
# Review/land species are excluded here once, for every pass.
_bound_rows() {
  python3 - <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
eps = B.epics(tickets)
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
    print("|".join([tickets[tk]["state"], tk, m.get("uuid") or "",
                    m.get("status") or "", m.get("current") or m.get("uuid") or "",
                    str(m.get("updated") or ""), str(m.get("sweep_recoveries") or "0"),
                    "1" if tk in eps else "0"]))
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
      "auto-recovery exhausted: bound worker $uuid $why $RECOVERY_CAP times; resume it by hand (daemon-resume/board-answer) or re-cut to its ready-for-* lane for a fresh dispatch" \
      >>"$SWEEP_LOG" 2>&1 \
      || log "[sweep] RECOVER: #$tk park transition FAILED (see log)"
    return
  fi
  _meta_put "$uuid" sweep_recoveries "$((recov + 1))" \
    || { log "[sweep] RECOVER: #$tk meta update failed — skipping resume"; return; }
  log "[sweep] RECOVER: #$tk worker $uuid $why — resume attempt $((recov + 1))/$RECOVERY_CAP"
  nohup "$DAEMON_SCRIPTS/daemon-resume.sh" "$uuid" \
    "SWEEP RECOVERY: your previous turn on ticket #$tk ended abnormally ($why). Re-read the ticket and the board state, restate your gate verdict against them in one paragraph (PLAN-EXECUTION, which ran no gate, restates plan-execution status instead), then continue your protocol from where the work actually stands. If the scope has shifted, park honestly instead." \
    >>"$SWEEP_LOG" 2>&1 &
}

pass_recover() {
  local acted=0 state tk uuid status current recov fin tx age
  while IFS='|' read -r state tk uuid status current _ recov is_epic; do
    [ -n "$uuid" ] || continue
    case "$status" in working|blocked|error) ;; *) [ "$status" = "idle" ] || continue ;; esac
    fin="$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$uuid" 2>/dev/null)" || fin="noop"
    # finalize says noop for an ALREADY-terminal meta (error/idle) — the
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
          "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
          acted=$((acted+1))
          continue
        fi
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
      ready-for-architect|ready-for-implementer)
        # a dead pre-gate worker frees its slot; the dispatch pass re-runs it
        case "$fin" in
          absent|error)
            log "[sweep] RECOVER: #$tk pre-verdict worker $uuid dead — retired (dispatch pass re-runs the gate fresh)"
            "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
            acted=$((acted+1)) ;;
          live)
            # Live but silent past the threshold, on a ticket sitting in a
            # lane QUEUE. A queue state is a HANDED-OFF state: whatever this
            # worker was doing, its writes on this ticket are done — the
            # ticket is waiting for the next lane's dispatch. Yet the meta
            # still binds the ticket, and implement-dispatch charges it to
            # the destination lane's slots (and refuses to dispatch a ticket
            # with a bound working worker at all), so a cap-1 lane blocks for
            # as long as the process lingers. Retire the binding — not the
            # in-flight arm's resume ladder, which exists for a worker that
            # still owns its exit. Same silence signal as that arm: the
            # transcript's mtime, the only stable turn-end clock here (the
            # meta's `updated` is bumped by the finalize just above).
            tx="$(_transcript "$current")"
            if [ -n "$tx" ]; then
              age="$(( ( $(date +%s) - $(stat -f %m "$tx" 2>/dev/null || stat -c %Y "$tx") ) / 60 ))"
              if [ "$age" -ge "$STALL_MIN" ]; then
                log "[sweep] RECOVER: #$tk worker $uuid is live but silent for ${age}m (threshold ${STALL_MIN}m) on a handed-off $state ticket — retiring the binding; it owns no further writes here"
                "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
                acted=$((acted+1))
              fi
            fi ;;
        esac ;;
    esac
  done <<EOF
$(_bound_rows | grep -E '^(in-progress|in-design|ready-for-architect|ready-for-implementer)\|' || true)
EOF
  log "[sweep] RECOVER: $acted acted"
}

pass_cancel() {
  local acted=0 state tk uuid status current recov fin
  while IFS='|' read -r state tk uuid status current _ recov is_epic; do
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
  # SUBDIRECTORY, because the top level of DAEMON_HOME is the daemon
  # metadata namespace: every *.json there is read as a worker meta, so a
  # cursor sitting beside them showed up as a bogus fleet row in
  # daemon-list, answered to `daemon-retire impact-scan` through
  # _resolve_uuid's prefix match, and could be deleted or rewritten by
  # daemon tooling that had every right to assume it owned the file).
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
    # reparents (implement-dispatch appends on a differing parent), and an
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
  while IFS='|' read -r state tk uuid status current _ recov is_epic; do
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

pass_recover  || log "[sweep] RECOVER pass errored (continuing)"
pass_cancel   || log "[sweep] CANCEL pass errored (continuing)"
pass_impact   || log "[sweep] IMPACT pass errored (continuing)"
"$IMPLEMENT_DISPATCH_CMD" --sweep 2>&1 | tee -a "$SWEEP_LOG" \
  || log "[sweep] DISPATCH pass errored (continuing)"
"$REVIEW_DISPATCH_CMD" --sweep 2>&1 | tee -a "$SWEEP_LOG" \
  || log "[sweep] REVIEW pass errored (continuing)"
pass_land     || log "[sweep] LAND pass errored (continuing)"
pass_relay    || log "[sweep] RELAY pass errored (continuing)"
"$RECONCILE_CMD" 2>&1 | tee -a "$SWEEP_LOG" >/dev/null \
  || log "[sweep] REPORT pass errored (continuing)"
log "[sweep] tick complete"
