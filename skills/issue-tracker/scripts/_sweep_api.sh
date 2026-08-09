#!/usr/bin/env bash
# _sweep_api.sh — the API-binding unattended tick (spec § four-phase tick):
#   renew → relay → resume-first → fresh claims. Each phase independently
#   guarded; each invokable alone: _sweep_api.sh [renew|relay|resume|dispatch|all]
#
# The gh-mode tick (board-sweep.sh) re-derives its work-list from GitHub and
# the registry; this one re-derives it from the board API and the registry.
# Same contract: mechanical only, no model calls, every action idempotent, so
# overlapping or repeated ticks are safe and a restart loses nothing.
#
#   RENEW  every LIVE run's lease. A dead session's lease is deliberately NOT
#          renewed — letting it expire is how the server reclaims the run. A
#          409 run-ended is routed to the resume path, never fatal. A meta the
#          server never confirmed a bind for is repaired here.
#   RELAY  answers the human has posted, from /answers/unrelayed, into the
#          bound worker session. The ack is DELIVERY-GATED: it fires only when
#          the sentinel is already in the transcript or a resume returned
#          success. Undeliverable answers are never ack-and-dropped.
#
# Env:
#   DAEMON_HOME DAEMON_SCRIPTS   registry + daemon toolkit (test seams)
#   SWEEP_LOCK_STALE             minutes before a held tick lock is stolen (30)
#   BOARD_API_URL BOARD_CREDENTIALS_FILE   resolved by _binding.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_binding.sh
. "$SCRIPT_DIR/_binding.sh"
[ "$BOARD_BINDING" = api ] || {
  echo "error: _sweep_api.sh runs only under an api binding" >&2; exit 1; }
die() { echo "error: $*" >&2; exit 1; }
# The delivery marker, from the client module rather than a second copy of the
# literal: what the relay WRITES into a transcript and what it later greps for
# have to be the same string as anyone else keying on it (the resume path, the
# worker protocol) — a private copy here would drift silently, and the drift
# reads as "never delivered", i.e. an answer relayed twice.
SENTINEL_FMT="$(_api_py -c "import _board_api; print(_board_api.SENTINEL)")"
_sentinel() {
  # shellcheck disable=SC2059  # SENTINEL_FMT is the module's printf template
  printf "$SENTINEL_FMT" "$1"
}
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SCRIPT_DIR/../../orchestrating-daemons/scripts" && pwd)}"
mkdir -p "$DAEMON_HOME"

# One tick at a time (Codex review F1): overlapping ticks would race the
# sentinel check between its grep and its resume, and double-deliver the same
# answer. An mkdir lock, not flock(1) — macOS ships no flock binary, and this
# tick runs under launchd there; `flock -n 9 || exit 0` would silently skip
# EVERY tick on the platform the fleet actually runs on. Idempotence is the
# real safety, so a lock older than SWEEP_LOCK_STALE minutes is stolen rather
# than obeyed (same rule as board-sweep.sh's).
LOCK="$DAEMON_HOME/.sweep-api.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +"${SWEEP_LOCK_STALE:-30}" 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || true
    mkdir "$LOCK" 2>/dev/null || { echo "another api sweep holds the lock — exiting"; exit 0; }
  else
    echo "another api sweep holds the lock — exiting"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# Registry metas that carry a run, one row each, US-separated (0x1f):
#   uuid  run_id  bind_confirmed  ticket  run_bearer  fence  lane  status  path
# NOT tab-separated: tab is IFS *whitespace*, so a run of tabs collapses into
# one delimiter and an empty column (a meta with no bearer) silently shifts
# every field after it — the fence came back as the lane. 0x1f is
# IFS-non-whitespace, so empty columns are preserved, and it cannot occur in
# a token, a ticket id or a path.
# The bearer is a secret at rest (0600): it rides this pipeline into a shell
# variable and from there into a child's ENVIRONMENT — it is never logged,
# echoed, or written anywhere.
_registry_metas() {
  T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
for p in sorted(glob.glob(os.path.join(os.environ["T_DHOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if not m.get("run_id"):
        continue
    # The meta FILENAME is the daemon identity every other tool resolves by;
    # the uuid field only mirrors it.
    uuid = m.get("uuid") or os.path.basename(p)[:-5]
    cols = [uuid] + [str(m.get(k, "")) for k in
                     ("run_id", "bind_confirmed", "ticket", "run_bearer",
                      "fence", "lane", "status")]
    print("\x1f".join(cols) + "\x1f" + p)
PY
}

# One field out of one meta. Used where a value must NOT travel through the
# row pipeline above (and for `current`, which the row layout does not carry).
_meta_field() {
  T_PATH="$1" T_KEY="$2" python3 - <<'PY'
import json, os
try:
    with open(os.environ["T_PATH"]) as f:
        print(json.load(f).get(os.environ["T_KEY"], "") or "")
except Exception:
    print("")
PY
}

# The transcript of a daemon's CURRENT turn — the same derivation
# orchestrating-daemons' own _lib.sh uses (_transcript_path): a daemon is
# continued by FORKING, so its live session is the meta's `current`, not its
# stable uuid, and Claude Code mangles the cwd into the project-dir name, so
# the file is found by globbing for the session uuid rather than by
# reproducing that rule. Empty when no transcript exists yet.
_transcript_for_uuid() {
  local cur
  cur="$(_meta_field "$DAEMON_HOME/$1.json" current)"
  [ -n "$cur" ] || cur="$1"
  find "$HOME/.claude/projects" -name "$cur.jsonl" 2>/dev/null | head -1
}

# rc 0 iff the session still exists. `absent` is the only dead answer:
# `noop` is what daemon-finalize says about an already-terminal (idle/error)
# meta, and a parked worker waiting on an answer is exactly that shape.
_alive() { [ "$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$1" 2>/dev/null || echo absent)" != absent ]; }

# ---- phase 1: lease renewal + bind repair ----------------------------------
phase_renew() {
  # Every column gets its own name, including the ones this phase ignores: in
  # bash 3.2 a repeated placeholder name in `read` collapses and silently
  # SHIFTS every field after it (fence read back as the lane, observed).
  local uuid run bindc ticket bearer fence lane status path
  # shellcheck disable=SC2034  # the trailing names exist to hold the columns
  while IFS=$'\x1f' read -r uuid run bindc ticket bearer fence lane status path; do
    [ -n "$run" ] || continue
    # A DEAD session's lease is left to expire: that expiry is the server's
    # signal to reclaim the run and hand the ticket to a successor. Renewing
    # it would pin the ticket to a worker that no longer exists.
    _alive "$uuid" || continue
    if T_RUN="$run" _api_py - <<'PY'
import os, sys
import _board_api as A
try:
    A.renew(os.environ["T_RUN"])
except A.RunEnded as e:
    # Not an error: the server reaped this run while its session kept
    # running. The resume phase claims a successor for it.
    print("run %s: ended (%s) — resume path" % (os.environ["T_RUN"], e))
    sys.exit(3)
PY
    then
      # bind_confirmed is a claim about what the SERVER accepted. A run whose
      # bind never landed is invisible to the board as a session — repair it
      # while the lease is provably fresh. board-bind speaks as automation
      # here: an unconfirmed meta is precisely the one that may hold no bearer.
      case "$bindc" in
        True | true) : ;;
        *)
          if [ -n "$ticket" ]; then
            echo "run $run: bind unconfirmed — repairing the board-side binding for #$ticket"
            BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
              "$SCRIPT_DIR/board-bind.sh" "$uuid" "$ticket" \
              || echo "run $run: bind repair FAILED — retried next tick"
          fi ;;
      esac
    fi
  done < <(_registry_metas)
}

# ---- phase 2: answer relay -------------------------------------------------
_relay_prompt() {  # $1=answer id, $2=replies text
  local sentinel
  sentinel="$(_sentinel "$1")"
  cat <<EOF
$sentinel Your needs-human park on this ticket was answered by
the human. Re-state your gate verdict against the answers in ONE paragraph as
a ticket comment ("[gate] re-pass — <one line>" — PLAN-EXECUTION, which ran no
gate, restates plan-execution status instead), or park fresh if the answers
reshape the work's scope, then proceed under your original protocol. Never
build on momentum past an answer that changed the work's shape.

---- answers (verbatim) ----
$2
EOF
}

# uuid, bearer, run_id, fence (0x1f-separated) for the bound meta of ticket $1
_meta_for_ticket() {
  _registry_metas | awk -F$'\x1f' -v t="$1" -v s=$'\x1f' \
    '$4 == t { print $1 s $5 s $2 s $6; exit }'
}

# One page of the unrelayed feed, spilled to files under $1 (id/ticket in
# <i>.meta, the replies verbatim in <i>.replies) so multi-line answer text
# never has to survive a shell round-trip. Prints the row count.
_unrelayed_dump() {
  T_DIR="$1" _api_py - <<'PY'
import os
import _board_api as A
d = os.environ["T_DIR"]
rows = A.unrelayed()
for i, a in enumerate(rows):
    with open(os.path.join(d, "%d.meta" % i), "w") as f:
        f.write("%s\x1f%s" % (a.get("answerEventId"), a.get("ticketId")))
    with open(os.path.join(d, "%d.replies" % i), "w") as f:
        f.write("\n".join(a.get("replies") or []))
print(len(rows))
PY
}

phase_relay() {
  local dir n i acked aid tid replies uuid bearer run fence transcript
  dir="$(mktemp -d)"
  # shellcheck disable=SC2064  # $dir is expanded now, on purpose
  trap "rm -rf '$dir'; rmdir '$LOCK' 2>/dev/null || true" EXIT
  while :; do
    rm -f "$dir"/*.meta "$dir"/*.replies 2>/dev/null || true
    n="$(_unrelayed_dump "$dir")" || break
    [ "$n" -gt 0 ] || break
    acked=0
    i=0
    while [ "$i" -lt "$n" ]; do
      aid="$(cut -d$'\x1f' -f1 "$dir/$i.meta")"
      tid="$(cut -d$'\x1f' -f2 "$dir/$i.meta")"
      replies="$(cat "$dir/$i.replies")"
      i=$((i + 1))
      uuid=""; bearer=""; run=""; fence=""
      IFS=$'\x1f' read -r uuid bearer run fence < <(_meta_for_ticket "$tid") || true
      if [ -z "$uuid" ] || ! _alive "$uuid"; then
        # NEVER ack-and-drop: the answer stays on the feed so the successor
        # this ticket gets (resume phase) delivers it instead.
        echo "relay: #$tid answer $aid — no live bound session; successor path will deliver"
        continue
      fi
      transcript="$(_transcript_for_uuid "$uuid")"
      # The ack is gated on PROVEN delivery (Codex review F1): the sentinel is
      # already in the transcript, or a resume returned success. A failed
      # resume acks nothing — the answer stays on the feed for the next tick.
      if [ -n "$transcript" ] && grep -qF "$(_sentinel "$aid")" "$transcript" 2>/dev/null; then
        echo "relay: #$tid answer $aid already delivered (sentinel) — acking"
      elif BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
        BOARD_API_URL="$BOARD_API_URL" \
        "$DAEMON_SCRIPTS/daemon-resume.sh" "$uuid" "$(_relay_prompt "$aid" "$replies")"; then
        echo "relay: #$tid answer $aid delivered to $uuid"
      else
        echo "relay: #$tid answer $aid — resume FAILED; not acked, retried next tick"
        continue
      fi
      T_AID="$aid" _api_py - <<'PY'
import os
import _board_api as A
A.ack(os.environ["T_AID"])
PY
      acked=$((acked + 1))
    done
    # Level-triggered drain: re-read only while progress is being made. A pass
    # that acked nothing (every entry dead-session or failed delivery) must
    # break, or this loop spins on the same page forever.
    [ "$acked" -gt 0 ] || break
  done
  rm -rf "$dir"
  trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
}

phase_resume() { :; }    # Task 10
phase_dispatch() { :; }  # Task 10

case "${1:-all}" in
  renew) phase_renew ;;
  relay) phase_relay ;;
  resume) phase_resume ;;
  dispatch) phase_dispatch ;;
  all) phase_renew || true; phase_relay || true; phase_resume || true; phase_dispatch || true ;;
  *) die "usage: _sweep_api.sh [renew|relay|resume|dispatch|all]" ;;
esac
