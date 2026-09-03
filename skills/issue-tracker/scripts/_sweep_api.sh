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
#   RESUME every run the server reclaimed, from /runs/needing-resume, on a
#          freshly claimed SUCCESSOR — the registry persist lands BEFORE any
#          delivery attempt, unrelayed answers for that ticket ride the same
#          resume behind the relay sentinel, and a session resume that cannot
#          deliver falls back to a fresh spawn on the same successor bearer.
#          Three failed cycles register an env-issue and SUPPRESS the ticket:
#          automation holds no transition authority, so a stuck ticket is
#          never parked — the env-issue is the signal.
#   CLAIM  fresh work, by handing the tick to execute-dispatch.sh and
#          review-dispatch.sh in their API claim modes. They own pick-order
#          hand-off, the local cap and the claim journal; this tick only hands
#          them the suppression directory the resume phase writes.
#
# Env:
#   DAEMON_HOME SMINOS_CLI        seat registry + sminos CLI (test seams)
#   SWEEP_LOCK_STALE             minutes before a DEAD owner's tick lock is
#                                stolen (30) — a live owner's is never taken
#   BOARD_RELAY_RESUME_TIMEOUT   DAEMON_TIMEOUT for a relay OR successor resume
#                                (300 → a wait of ≤150 polls; clamped ≥2, since
#                                a resume reads 0 polls as UNLIMITED), so one
#                                long worker turn cannot hold the tick lock past
#                                a lease. An expired wait is not a failed
#                                delivery — both phases read the transcript.
#   BOARD_SWEEP_TICK_BUDGET      seconds after which the serial phases stop
#                                taking NEW items (900); the item in flight
#                                always finishes. Lease safety across a long
#                                tick is renewal interleaved between items, not
#                                this budget.
#   BOARD_SUPPRESS_DIR           (exported to the dispatchers) suppression
#                                records; they read, this tick writes
#   BOARD_RESUMED_LEDGER         (exported to the dispatchers) the tickets this
#                                tick already attempted a recovery for; they
#                                read, phase 3 writes
#   IMPLEMENT_MODEL LOCAL_REPO   model pin / repo for a successor fresh spawn
#   BOARD_API_URL BOARD_CREDENTIALS_FILE   resolved by _binding.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_binding.sh
. "$SCRIPT_DIR/_binding.sh"
# For _claim_nonce ONLY — the successor claim below is filed under a nonce on
# exactly the dispatchers' terms, and a host without uuidgen must not journal a
# claim under an empty name. The reconciler this file also defines belongs to
# the DISPATCHERS and is not called here: the successor lane is outside their
# lanes and _reconcile_successors reconciles it.
# shellcheck source=_claim_journal.sh
. "$SCRIPT_DIR/_claim_journal.sh"
[ "$BOARD_BINDING" = api ] || {
  echo "error: _sweep_api.sh runs only under an api binding" >&2; exit 1; }
die() { echo "error: $*" >&2; exit 1; }
# THE TICK IS AUTOMATION, FULL STOP. The client's token() hands back
# BOARD_RUN_TOKEN for whatever principal is asked once one is in env, so a
# tick inherited from a worker's shell would renew, ack and unrelayed-read as
# that worker — against runs it does not own (spec § phase 1: "Renewal is
# dispatch automation, never worker prose") — and, worse, a bind repair would
# hand board-bind.sh the foreign bearer to stamp into a DIFFERENT run's meta,
# after which every later resume of that run authenticates as someone else.
# A run token appears in this script ONLY as an explicit env prefix carrying a
# bearer this tick read out of THAT run's own meta (or was just handed by that
# run's own claim): the relay's resume, the successor's resume/spawn/bind, and
# phase 1's bind repair. Never inherited, never ambient.
unset BOARD_RUN_TOKEN
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
# ONE registry-root rule, the sminos CLI's own: $SMINOS_HOME, then $DAEMON_HOME,
# then the default. Both names are exported at the same value below, so the
# CLI, the board scripts and every child resolve one root — a pipeline that
# preferred DAEMON_HOME while sminos preferred SMINOS_HOME would have the two
# halves of one tick reading different registries.
DAEMON_HOME="${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}"
SMINOS_HOME="$DAEMON_HOME"
export SMINOS_HOME DAEMON_HOME
SMINOS_CLI="${SMINOS_CLI:-$(cd "$SCRIPT_DIR/../../sminos/scripts" && pwd)/sminos}"
# The registry root moved to ~/.claude/sminos and this script scans it
# directly, so it must never be the first process to look at an empty new
# root: let sminos fold the old root in first. Idempotent, and FAIL CLOSED
# — a half-migrated registry reads as an empty fleet, which passes every
# dedupe and cap check and dispatches over live workers.
"$SMINOS_CLI" migrate --quiet || { echo "error: sminos migrate failed — refusing to sweep against a possibly half-migrated registry" >&2; exit 1; }
mkdir -p "$DAEMON_HOME"

# One tick at a time (Codex review F1): overlapping ticks would race the
# sentinel check between its grep and its resume, and double-deliver the same
# answer. An mkdir lock, not flock(1) — macOS ships no flock binary, and this
# tick runs under launchd there; `flock -n 9 || exit 0` would silently skip
# EVERY tick on the platform the fleet actually runs on. Idempotence is the
# real safety, so a lock older than SWEEP_LOCK_STALE minutes is stolen rather
# than obeyed (same rule as board-sweep.sh's).
LOCK="$DAEMON_HOME/.sweep-api.lock"
# The lock NAMES ITS OWNER. Age alone was the whole steal rule, and age alone
# is wrong in both directions: a legitimate tick can run for the better part of
# half an hour (serial bounded waits, one per item), so a live owner was robbed
# and two ticks then interleaved the sentinel check with its resume — the exact
# double delivery this lock exists to prevent; and the robbed owner's
# unconditional EXIT rmdir went on to delete the REPLACEMENT owner's lock.
#
# A PID IS NOT AN IDENTITY. Pids are recycled, and after a crash — above all
# across a REBOOT, where low numbers are handed straight back out — the dead
# sweep's number very plausibly belongs to some long-lived process. `kill -0`
# then answers "alive" forever, the lock is never stolen, and every later api
# sweep exits at once: no renewal, no relay, no resume, no dispatch, until a
# human notices. So the owner's PROCESS START TIME is recorded beside its pid
# and both must match before the owner counts as live. `ps -o lstart=` is the
# portable form of that (macOS bash 3.2 and Linux procps both print it) — but
# it is a RENDERED date, and the renderer reads the environment: the month and
# day names come from the locale and the clock from the zone. A lock written by
# a launchd tick and checked by one started from a shell with its own LC_ALL or
# TZ would compare two spellings of the same instant and call them different
# processes. Both sides go through this one function, and it pins both knobs, so
# the token means the same thing to every writer and every reader.
#
# AND THE TOKEN SAYS WHICH RENDERING IT IS. Pinning the format only settles
# locks written after the pin; the sweep holding the lock during the upgrade
# ITSELF wrote a bare `lstart` under whatever it inherited, and comparing that
# against a C/UTC rendering of the same live process says "different process" —
# so the upgrade would rob a live owner the moment its lock aged past stale,
# causing the very double delivery this lock prevents. The version prefix is
# what lets a reader tell a token it can compare from one it cannot. Bump it
# whenever the rendering below changes, and old locks degrade instead of lying.
#
# BUT "UNVERSIONED" IS NOT "UNREADABLE", and conflating the two is its own
# defect: a bare token this code can still REPRODUCE is evidence, and refusing
# to read it means a recycled pid under such a lock is believed alive forever —
# no renewal, no relay, no resume, no dispatch, which is the exact wedge the
# start time was recorded to prevent. So a bare token is compared, against the
# two renderings a previous version of this script could have written: C/UTC
# (what the pinning wrote before it was versioned) and C in the machine's OWN
# zone (what an unpinned writer produced, since an unset LC_ALL already renders
# C-like and only the zone moved). Matching either is the same process. Only a
# rendering neither of those reproduces — a genuinely localized one — is
# UNKNOWN, and unknown keeps the owner (see _owner_live).
_START_FMT=c1
# The C rendering under ONE zone. Called with no zone argument it inherits the
# machine's; TZ= would NOT do that — an empty TZ reads as UTC on most libc,
# which is the very value we are trying to tell apart.
_start_raw() {  # <pid> [tz]
  if [ "$#" -ge 2 ]; then
    LC_ALL=C TZ="$2" ps -p "$1" -o lstart= 2>/dev/null | sed 's/^ *//;s/ *$//' || true
  else
    LC_ALL=C ps -p "$1" -o lstart= 2>/dev/null | sed 's/^ *//;s/ *$//' || true
  fi
}
_proc_start() {
  local s
  s="$(_start_raw "$1" UTC)"
  # No answer at all is not an empty token, it is NO token: printing a bare
  # prefix here would hand _owner_live a well-formed value meaning nothing.
  [ -n "$s" ] || return 0
  printf '%s:%s\n' "$_START_FMT" "$s"
}
# Is this bare token even the shape this script renders? The locale moves the
# day and month NAMES, so the month field is where a foreign rendering shows
# itself; the zone moves only the clock, which is a value difference, not a
# shape one. Five fields: `Thu Jan  1 00:00:00 2000`.
_c_rendered() {  # <token>
  # shellcheck disable=SC2086  # the split IS the check: these fields are the shape
  set -- $1
  [ "$#" -eq 5 ] || return 1
  case "$2" in Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) ;; *) return 1 ;; esac
}
_take_lock() {
  mkdir "$LOCK" 2>/dev/null || return 1
  printf '%s\n' "$$" > "$LOCK/owner"
  _proc_start "$$" > "$LOCK/owner-start"
}
# The owner is live only when its pid answers AND that pid is still the SAME
# process the lock was taken by. A lock written before this file existed names
# no start time; there the pid answer is all the evidence there is, which is
# exactly the behaviour it already had.
#
# THE START COMPARISON HAS MORE THAN TWO ANSWERS, and the extra ones decide
# which way this fails. A mismatch is the only thing that means "different
# process"; every other shape means NOT KNOWN, and not-known keeps the owner,
# because `kill -0` has ALREADY said this pid answers. Read as a mismatch
# instead, each of them robs a live owner, and two ticks then interleave the
# sentinel check with its resume — the double delivery this lock exists to
# prevent. The age rule alone never overrides a live pid; the cost of holding
# is one skipped tick, against a duplicated answer.
#
#   no recorded start   a lock written before this file existed. The pid answer
#                       is all the evidence there is, exactly as it always was.
#   a rendering this code cannot reproduce   a localized `lstart` from some
#                       earlier version's environment, or a NEWER format. It may
#                       well be the same live process, spelled a way this code
#                       cannot generate, so it is never grounds to steal. A bare
#                       token it CAN reproduce is not in this class — it is
#                       compared, because refusing to read it wedges the sweep.
#   no current answer   `ps` printed nothing: a lost race with the process
#                       table, a form some later OS renders differently.
_owner_live() {  # <pid> <recorded start ('' = unknown)>
  local now
  kill -0 "$1" 2>/dev/null || return 1
  [ -n "$2" ] || return 0
  case "$2" in
    "$_START_FMT":*)
      now="$(_proc_start "$1")"
      [ -n "$now" ] || return 0
      [ "$now" = "$2" ] ;;
    *)
      # Unversioned, from a previous shape of this script. Readable only if it
      # is the C rendering; then it is this process only if it matches under
      # one of the two zones such a writer could have used.
      _c_rendered "$2" || return 0
      now="$(_start_raw "$1" UTC)"
      [ -n "$now" ] || return 0
      [ "$now" = "$2" ] && return 0
      now="$(_start_raw "$1")"
      [ -n "$now" ] || return 0
      [ "$now" = "$2" ] ;;
  esac
}
if ! _take_lock; then
  _lock_owner="$(cat "$LOCK/owner" 2>/dev/null || true)"
  _lock_start="$(cat "$LOCK/owner-start" 2>/dev/null || true)"
  # BOTH halves are required to steal: old enough that a crash is plausible,
  # AND an owner that is provably gone (or a lock too old to name one — the
  # pre-owner-token shape). Idempotence is the real safety, so a stolen lock is
  # recoverable; a stolen-from-a-live-owner lock is not.
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +"${SWEEP_LOCK_STALE:-30}" 2>/dev/null)" ] \
     && { [ -z "$_lock_owner" ] || ! _owner_live "$_lock_owner" "$_lock_start"; }; then
    rm -rf "$LOCK" 2>/dev/null || true
    _take_lock || { echo "another api sweep holds the lock — exiting"; exit 0; }
    echo "stole a stale api sweep lock (owner ${_lock_owner:-unnamed} is gone)" >&2
  else
    echo "another api sweep holds the lock — exiting"; exit 0
  fi
fi
SCRATCH="$(mktemp -d)"
# Remove ONLY our own lock: by the time this fires the lock may already belong
# to a replacement owner, and an unconditional rmdir would hand a third tick
# the lock that tick is holding.
trap 'rm -rf "$SCRATCH"
      [ "$(cat "$LOCK/owner" 2>/dev/null || true)" = "$$" ] && rm -rf "$LOCK"
      true' EXIT

# Whole-tick wall-clock budget for the serial phases. Interleaved renewal (see
# _tick_renew) keeps every lease fresh across a long tick, but the LOCK is held
# throughout, so a feed of many slow items would starve every other phase and
# every later tick behind it. The budget stops taking NEW items; the item in
# flight always finishes, so the worst case is one bounded wait past it.
TICK_BUDGET="${BOARD_SWEEP_TICK_BUDGET:-900}"
TICK_START="$(date +%s)"
_budget_left() { [ "$(( $(date +%s) - TICK_START ))" -lt "$TICK_BUDGET" ]; }

# One long worker turn must not hold the tick lock past a lease, so both resume
# vehicles bound their wait. CLAMPED at 2, and validated as an integer: a
# resume waits DAEMON_TIMEOUT/2 polls and _poll_until_done reads 0 as
# UNLIMITED, so an operator setting 1 turns the bound into its exact opposite —
# an unbounded wait inside the global lock.
RELAY_RESUME_TIMEOUT="${BOARD_RELAY_RESUME_TIMEOUT:-300}"
case "$RELAY_RESUME_TIMEOUT" in ''|*[!0-9]*) RELAY_RESUME_TIMEOUT=300 ;; esac
[ "$RELAY_RESUME_TIMEOUT" -ge 2 ] || RELAY_RESUME_TIMEOUT=2
# Where _registry_metas parks its exit status. The status, never the rows: the
# rows carry the run bearer, and that secret does not touch disk here.
SCAN_RC="$SCRATCH/scan-rc"

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
#
# Both callers consume these rows through a pipe or a process substitution,
# which HIDES this function's exit status — a python3 that died would read as
# an empty registry, i.e. a phase that silently did nothing. The status is
# parked in $SCAN_RC and every caller checks it with _scan_ok.
#
# `all` ADMITS RUNLESS METAS, and one caller family needs it. _retire_run_locally
# strips run/bearer/fence off a meta whose run the server ended while KEEPING
# ticket, lane and pending_short — so between the renew that retires a reclaimed
# predecessor and the successor that replaces it, the only record of that
# ticket's lane and of an unresolved fork on it is a meta the default scan
# filters out. Read through the default scan, the recovery path saw no
# predecessor at all: it fell back to IMPLEMENT for an architect/spike/qagent
# ticket, and re-resumed a fork it should have refused.
_registry_metas() {  # [all]
  local rc=0
  T_DHOME="$DAEMON_HOME" T_ALL="${1:-}" python3 - <<'PY' || rc=$?
import glob, json, os
keep_runless = os.environ.get("T_ALL") == "all"
for p in sorted(glob.glob(os.path.join(os.environ["T_DHOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if not m.get("run_id") and not keep_runless:
        continue
    # The meta FILENAME is the daemon identity every other tool resolves by
    # (board-bind resolves the same way); the uuid FIELD only mirrors it, and
    # a stale mirror would name a session nothing else can reach.
    uuid = os.path.basename(p)[:-5] or m.get("uuid") or ""
    cols = [uuid] + [str(m.get(k, "")) for k in
                     ("run_id", "bind_confirmed", "ticket", "run_bearer",
                      "fence", "lane", "status")]
    print("\x1f".join(cols) + "\x1f" + p)
PY
  echo "$rc" > "$SCAN_RC"
}
_scan_ok() { [ "$(cat "$SCAN_RC" 2>/dev/null || echo 1)" = 0 ]; }

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

# The transcript of a seat's CURRENT turn — the same derivation the sminos
# CLI itself uses (transcript_path): a seat's live session is the record's
# `current`, not its stable seat id, and Claude Code mangles the cwd into
# the project-dir name, so
# the file is found by globbing for the session uuid rather than by
# reproducing that rule. Empty when no transcript exists yet.
_transcript_for_uuid() {
  local cur
  cur="$(_meta_field "$DAEMON_HOME/$1.json" current)"
  [ -n "$cur" ] || cur="$1"
  find "$HOME/.claude/projects" -name "$cur.jsonl" 2>/dev/null | head -1
}

# DELIVERY PROOF READS DELIVERED PROMPTS, not the whole file. The transcript is
# JSONL and holds everything the session ever saw — tool results, file contents,
# the worker's own prose — so a fixed-string grep over the raw bytes accepts a
# marker that merely appeared as DATA (a worker cat-ing this script, a human
# pasting an earlier answer back) as proof the answer was delivered, and acks it
# undelivered. A DELIVERED PROMPT is a user-role entry whose content is a plain
# string; tool results ride the same `user` type but arrive as a content LIST,
# which is exactly the channel arbitrary bytes come back through.
_delivered() {  # <transcript path> <marker>
  [ -n "${1:-}" ] || return 1
  T_PATH="$1" T_NEEDLE="$2" python3 - <<'PY'
import json, os, sys
needle = os.environ["T_NEEDLE"]
try:
    f = open(os.environ["T_PATH"], errors="replace")
except OSError:
    sys.exit(1)
with f:
    for line in f:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "user":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str) and needle in content:
            sys.exit(0)
sys.exit(1)
PY
}

# The liveness verdict for a bound session, in ONE word. THREE outcomes, not
# two, because the middle one is real and collapsing it into either extreme is
# a defect this branch already paid for twice:
#
#   live    the session exists and can be spoken to — a running turn, or a
#           worker parked on an answer. `noop` is what `sminos sync` says
#           about an ALREADY-TERMINAL meta, and a parked worker is exactly that
#           shape, so `noop` is disambiguated from the meta rather than trusted.
#   forked  a resume LAUNCHED a turn whose session uuid never resolved:
#           `sminos resume` stamps status=error + pending_short and deliberately
#           leaves `current` on the superseded turn. The fork may be running and
#           holding the run, so the lease is still RENEWED — but nothing may be
#           delivered into this session and no delivery can be proven, because
#           every transcript read still lands on the OLD turn. Resuming again
#           forks AGAIN: a fresh zombie turn every tick, each one possibly live
#           on the same run.
#   dead    the session is gone from the harness (`absent`), or its turn errored
#           out. A dead session's lease is deliberately NOT renewed — letting it
#           expire is how the server reclaims the run and hands the ticket to a
#           successor, which IS the designed recovery. Renewing it instead
#           immortalizes the failure: the ticket stays pinned to a worker that
#           will never write again, forever.
#
# pending_short is never cleared once written (a later successful resume only
# re-stamps `current`/`status`), so the UNRESOLVED fork is the PAIR
# status=error + pending_short, never the field on its own — keying on the
# field alone would wedge every session that ever survived a failed fork.
_liveness() {
  local fin
  fin="$("$SMINOS_CLI" sync "$1" 2>/dev/null || echo absent)"
  case "$fin" in
    absent | error) echo dead; return 0 ;;
    noop) : ;;
    *) echo live; return 0 ;;
  esac
  T_PATH="$DAEMON_HOME/$1.json" python3 - <<'PY'
import json, os
try:
    with open(os.environ["T_PATH"]) as f:
        m = json.load(f)
except Exception:
    m = {}
if m.get("status") == "error":
    print("forked" if m.get("pending_short") else "dead")
else:
    print("live")
PY
}
_alive() { [ "$(_liveness "$1")" = live ]; }

# A run the SERVER has ended is over locally too. Without this the meta keeps
# its run id and its lane, and the dispatchers' local cap counts it — so a
# normally released run occupies a dispatch slot forever while never appearing
# in needing-resume (nothing reclaimed it; it simply finished).
#
# The RUN ASSOCIATION is stripped, and only that: the session is still a real
# session, it just no longer speaks for a run. The bearer goes with it — a
# token for an ended run authenticates nothing, and keeping it is only a secret
# still lying at rest. `lane` and `role` STAY, deliberately: the reclaim path
# reaches this same branch (a reclaimed run answers renew with 409 run-ended),
# and the successor claimed for that ticket inherits its lane from exactly this
# meta. The slot is freed by the run id going away, not the lane — the
# dispatchers count OPEN RUNS, which is what a cap is about.
_retire_run_locally() {  # <meta path> <run id>
  T_PATH="$1" T_RUN="$2" T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import fcntl, json, os
env = os.environ
lock = open(os.path.join(env["T_DHOME"], ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    path = env["T_PATH"]
    with open(path) as f:
        m = json.load(f)
    # Only if the meta STILL names the run that ended. A successor persist can
    # re-point this very meta at a fresh run between the renew and this write,
    # and clearing that one would strand a live run nothing could speak for.
    if str(m.get("run_id") or "") != env["T_RUN"]:
        raise SystemExit(0)
    for k in ("run_id", "run_bearer", "fence", "bind_confirmed", "nonce"):
        m.pop(k, None)
    m["run_ended_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    __import__("time").gmtime())
    mode = os.stat(path).st_mode & 0o777
    tmp = path + ".tmp"
    # Unlink first: os.open(..., mode) does NOT re-mode an existing inode, so a
    # leftover 0644 tmp from an earlier crash would be truncated and rewritten
    # world-readable. (This writer removes the bearer rather than adding one,
    # but the rule is the writer's, not the payload's.)
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
        json.dump(m, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
}

# ---- phase 1: lease renewal + bind repair ----------------------------------
phase_renew() {
  # Every column gets its own name, including the ones this phase ignores.
  # Not because repeated `_` placeholders misbehave — they are fine in bash
  # 3.2 — but because named columns are what makes the row layout auditable
  # against the 0x1f contract above, which is where the real field-shift bug
  # lived (tab as IFS whitespace collapsed the empty bearer column and the
  # fence came back as the lane).
  local uuid run bindc ticket bearer fence lane status path rc
  # shellcheck disable=SC2034  # the trailing names exist to hold the columns
  while IFS=$'\x1f' read -r uuid run bindc ticket bearer fence lane status path; do
    [ -n "$run" ] || continue
    # A DEAD session's lease is left to expire: that expiry is the server's
    # signal to reclaim the run and hand the ticket to a successor. Renewing
    # it would pin the ticket to a worker that no longer exists — or, worse,
    # to one that ERRORED OUT, which is the same thing with a longer tail.
    # A `forked` session still gets its lease: an unresolved fork may well be
    # running on that run, and expiring the lease under it would hand the same
    # ticket to a successor while the fork keeps writing.
    [ "$(_liveness "$uuid")" != dead ] || continue
    rc=0
    T_RUN="$run" _api_py - <<'PY' || rc=$?
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
    case "$rc" in
      0)
      # bind_confirmed is a claim about what the SERVER accepted. A run whose
      # bind never landed is invisible to the board as a session — repair it
      # while the lease is provably fresh. board-bind speaks as automation
      # here: an unconfirmed meta is precisely the one that may hold no bearer,
      # so the bearer read out of the registry rides the repair explicitly —
      # without it the repair would stamp bind_confirmed on a meta that can
      # never authenticate as its own run again.
      case "$bindc" in
        True | true) : ;;
        *)
          if [ -n "$ticket" ]; then
            echo "run $run: bind unconfirmed — repairing the board-side binding for #$ticket"
            BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
              "$SCRIPT_DIR/board-bind.sh" "$uuid" "$ticket" \
              || echo "run $run: bind repair FAILED — retried next tick"
          fi ;;
      esac ;;
      3) _retire_run_locally "$path" "$run" \
           || echo "run $run: ended, but the local lane could not be retired — it keeps a dispatch slot until the meta is repaired" >&2 ;;
      *) echo "run $run: renew failed — retried next tick" >&2 ;;
    esac
  done < <(_registry_metas)
  _scan_ok || die "registry scan failed — renew phase saw no metas it can trust"
}

# INTERLEAVED RENEWAL (spec v1.2.7, amending the v1.2.3 per-item ruling). One
# renewal covered the WHOLE tick while the bound was PER ITEM, so the arithmetic
# never closed: four worst-case deliveries at 300s each out-run A1's 15-minute
# lease, and the server reclaims runs that are very much alive — including the
# ones this tick is not even touching. Renewal is one cheap idempotent POST per
# live run, so it runs again AHEAD OF EVERY ITEM rather than once ahead of all
# of them: no live run's lease then ages more than a single item's bound.
_tick_renew() { phase_renew || true; }

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

# uuid, bearer, run_id, fence (0x1f-separated) for every meta bound to ticket
# $1 — CANDIDATES, not one answer. Two metas can name the same ticket for a
# window: a reclaimed predecessor whose ticket-strip has not landed yet, beside
# the successor that actually holds the run. Taking the first glob match would
# hand the answer to the dead one. Server-confirmed binds are emitted first,
# and the caller takes the first LIVE candidate.
#
# $2 = `all` includes RUNLESS metas — not delivery candidates (a meta with no
# run holds no bearer to speak with), but the fork guard reads this same list
# and an unresolved fork survives its run's end.
_metas_for_ticket() {  # <ticket> [all]
  _registry_metas "${2:-}" | awk -F$'\x1f' -v t="$1" -v s=$'\x1f' '
    $4 != t { next }
    { row = $1 s $5 s $2 s $6
      if ($3 == "True" || $3 == "true") print row; else rest[++n] = row }
    END { for (i = 1; i <= n; i++) print rest[i] }'
}

# One page of the unrelayed feed, spilled to files under $1 (id/ticket in
# <i>.meta, the replies verbatim in <i>.replies) so multi-line answer text
# never has to survive a shell round-trip. Prints the row count.
#
# GET /answers/unrelayed IS A FLAT ROUTE, capped at 500 rows (arkho API.md §1
# Boundary bounds) with no cursor to page it. That is sound here because the
# drain loop below re-reads until the feed answers empty: a full page just
# costs another lap.
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
  local c_uuid c_bearer c_run c_fence forked bearerless
  # Under $SCRATCH, so the EXIT trap installed beside the lock cleans it up —
  # no second trap here to chain the lock's rmdir into.
  dir="$(mktemp -d "$SCRATCH/relay.XXXXXX")"
  while :; do
    rm -f "$dir"/*.meta "$dir"/*.replies 2>/dev/null || true
    n="$(_unrelayed_dump "$dir")" || break
    [ "$n" -gt 0 ] || break
    acked=0
    i=0
    while [ "$i" -lt "$n" ]; do
      _budget_left || { echo "relay: tick budget exhausted — the rest of the feed rides the next tick"; break; }
      aid="$(cut -d$'\x1f' -f1 "$dir/$i.meta")"
      tid="$(cut -d$'\x1f' -f2 "$dir/$i.meta")"
      replies="$(cat "$dir/$i.replies")"
      i=$((i + 1))
      uuid=""; bearer=""; run=""; fence=""; forked=""; bearerless=""
      while IFS=$'\x1f' read -r c_uuid c_bearer c_run c_fence; do
        case "$(_liveness "$c_uuid")" in
          live) : ;;
          # An UNRESOLVED FORK is not a deliverable session. `current` still
          # names the superseded turn, so the sentinel check below reads the
          # WRONG transcript, finds nothing, and resumes — forking a second
          # zombie turn onto the same run, every tick, forever. Skipped and
          # surfaced; the answer stays on the feed.
          forked) forked="$c_uuid"; continue ;;
          *) continue ;;
        esac
        # A RELAY CANDIDATE WITHOUT A BEARER IS NOT A CANDIDATE. Resuming it
        # would inject an EMPTY BOARD_RUN_TOKEN, and the client's token() falls
        # back to the configured HUMAN/AUTOMATION credentials the moment the run
        # token is blank — so the worker would speak every ordinary verb with
        # broader authority than its own run, outside its fence. Phase 1's bind
        # repair is the route that gives such a meta its bearer back.
        [ -n "$c_bearer" ] || { bearerless="$c_uuid"; continue; }
        uuid="$c_uuid"; bearer="$c_bearer"; run="$c_run"; fence="$c_fence"
        break
      done < <(_metas_for_ticket "$tid")
      _scan_ok || die "registry scan failed — cannot resolve the session bound to #$tid"
      if [ -z "$uuid" ]; then
        # NEVER ack-and-drop: the answer stays on the feed so the successor
        # this ticket gets (resume phase) delivers it instead.
        if [ -n "$forked" ]; then
          echo "relay: #$tid answer $aid — the bound session $forked carries an UNRESOLVED FORK (status=error + pending_short); nothing is delivered or acked until it resolves — recover it by hand (daemon meta pending_short) or retire the session" >&2
        elif [ -n "$bearerless" ]; then
          echo "relay: #$tid answer $aid — the bound session $bearerless holds no run bearer; phase 1's bind repair owns it, not this relay" >&2
        else
          echo "relay: #$tid answer $aid — no live bound session; successor path will deliver"
        fi
        continue
      fi
      # Every live run's lease, refreshed ahead of a delivery that may block for
      # the whole bound — including the runs this answer has nothing to do with.
      _tick_renew
      # THAT RENEWAL MAY HAVE JUST ENDED THIS CANDIDATE'S RUN. A run the server
      # reclaimed answers renew with 409 run-ended, and _retire_run_locally then
      # strips run id, bearer and fence from exactly this meta — while the four
      # locals read above still hold the pre-renew values. Resuming on them
      # injects REVOKED credentials into the predecessor and forks it, moments
      # before the resume phase gives the ticket a real successor. The candidate
      # is re-resolved from the meta, and only a meta that still names the same
      # run is delivered to; anything else leaves the answer on the feed for the
      # successor to pick up.
      if [ "$(_meta_field "$DAEMON_HOME/$uuid.json" run_id)" != "$run" ]; then
        echo "relay: #$tid answer $aid — run $run ended under the renewal that preceded this delivery (the session no longer speaks for it); nothing delivered or acked, the successor path takes it" >&2
        continue
      fi
      transcript="$(_transcript_for_uuid "$uuid")"
      # The ack is gated on PROVEN delivery (Codex review F1): the sentinel is
      # already in the transcript, or a resume returned success. A failed
      # resume acks nothing — the answer stays on the feed for the next tick.
      if _delivered "$transcript" "$(_sentinel "$aid")"; then
        echo "relay: #$tid answer $aid already delivered (sentinel) — acking"
      # DAEMON_TIMEOUT is bounded here on purpose. `sminos resume`'s default is
      # 18000 (a wait of DAEMON_TIMEOUT/2 polls — hours), and this tick holds
      # the whole-tick lock throughout: one long turn would starve lease
      # renewal past the 15-minute lease and A1 would reclaim runs that are
      # very much alive. Bounding it is safe because `sminos resume` advances
      # the meta's `current` to the new turn and injects this prompt BEFORE it
      # blocks: a timed-out resume exits nonzero, so nothing is acked this
      # tick, and the next tick's sentinel grep finds the marker in the new
      # transcript and acks WITHOUT re-delivering (the replay case the test
      # pins on u-3/u-3-cur). The delivery gate holds; only the ack is late.
      elif BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
        BOARD_API_URL="$BOARD_API_URL" \
        DAEMON_TIMEOUT="$RELAY_RESUME_TIMEOUT" \
        "$SMINOS_CLI" resume --wait "$uuid" "$(_relay_prompt "$aid" "$replies")"; then
        echo "relay: #$tid answer $aid delivered to $uuid"
      else
        # NOT NECESSARILY A FAILURE. `sminos resume` also exits nonzero when its
        # bounded watcher expires on a turn it already injected the prompt into
        # — the ORDINARY outcome for a long worker turn, since the bound exists
        # to keep this tick from starving lease renewal. Either way nothing is
        # acked, and the next tick's sentinel check settles which it was without
        # re-delivering. Calling it FAILED trained the reader to expect a broken
        # relay on every long turn.
        echo "relay: #$tid answer $aid — the resume returned no delivery (a long turn whose bounded wait expired looks the same here); not acked, settled next tick by the sentinel"
        continue
      fi
      # PROGRESS IS A SUCCESSFUL ACK, and the ack has to be checked explicitly.
      # This whole function runs behind `|| true` in the `all` case, which
      # suspends errexit through its entire subtree — so a failed ack does not
      # abort the loop, it falls THROUGH. Counted as progress, the level-
      # triggered drain re-reads a feed that still carries the same unacked
      # answer and re-reads it again, forever, inside the whole-tick lock.
      if T_AID="$aid" _api_py - <<'PY'
import os
import _board_api as A
A.ack(os.environ["T_AID"])
PY
      then
        acked=$((acked + 1))
      else
        echo "relay: #$tid answer $aid — DELIVERED but the ack FAILED; the feed re-serves it next tick and the sentinel makes that replay a no-op" >&2
      fi
    done
    # Level-triggered drain: re-read only while progress is being made. A pass
    # that acked nothing (every entry dead-session or failed delivery) must
    # break, or this loop spins on the same page forever.
    [ "$acked" -gt 0 ] || break
  done
  rm -rf "$dir"
}

# ---- phase 3: resume-first -------------------------------------------------
# Suppression records sit beside the claim journal, one per stuck ticket:
#   {"ticket": N, "state": "<board state when it stuck>", "env_issue": N}
# THIS PHASE IS THEIR ONLY WRITER. Both dispatchers read the directory
# (BOARD_SUPPRESS_DIR) and release any claim that yields a suppressed ticket.
# An operator-set BOARD_SUPPRESS_DIR is honored (the header documents it, and
# both dispatchers already default-respect it at their _api_suppressed);
# overwriting it here split the two halves of one mechanism — this phase wrote
# records into the registry default while the dispatchers read the configured
# directory, so every suppression was invisible to the side that enforces it.
SUPPRESS_DIR="${BOARD_SUPPRESS_DIR:-$DAEMON_HOME/board-suppress}"
CLAIMS_DIR="$DAEMON_HOME/board-claims"

_suppressed() { [ -f "$SUPPRESS_DIR/$1.json" ]; }

# Lift the suppression on ticket $1 if either trigger fired. Both are checked
# every tick because either one alone is a trap: an operator who moves the
# ticket should not also have to close the env-issue, and closing the
# env-issue is the natural "I fixed the substrate" gesture.
#
# AN ABSENT ROW IS NOT A STATE. This is a TARGETED `ids=` read of exactly the
# two rows the record names, so absence in a completed answer is authoritative
# rather than truncation — the failure this guard was written against (one
# short whole-board listing lifting every suppression it could not see, because
# a missing row read as a value fires BOTH triggers: absent != the recorded
# state, and absent sits in the closed tuple) is now structurally impossible.
# tickets_by_ids either completes or dies.
# The conservative rule stands anyway, on the other absence this read can
# answer: the board has no delete path, so an id missing from a completed
# answer names a record pointing at a ticket that never existed — registry
# corruption, or a record carried over from a foreign board. That is not a
# state either. Absent is UNKNOWN on both sides: keep waiting.
# This is the read-site mirror of the write-site guard at _escalate.
_check_lift() {
  T_TID="$1" T_DIR="$SUPPRESS_DIR" _api_py - <<'PY'
import json, os
import _board_api as A
path = os.path.join(os.environ["T_DIR"], os.environ["T_TID"] + ".json")
if not os.path.exists(path):
    raise SystemExit(0)
with open(path) as f:
    rec = json.load(f)
rows = A.tickets_by_ids([rec["ticket"], rec["env_issue"]],
                        principal="automation")
row = rows.get(int(rec["ticket"]))
cur = row["state"] if row else None
moved = cur is not None and cur != rec["state"]
env_row = rows.get(int(rec["env_issue"]))
env = env_row["state"] if env_row else None
closed = env in ("done", "wontfix")   # absent env-issue: unknown, keep waiting
if moved or closed:
    os.remove(path)
    print("suppression lifted for #%s — %s" %
          (rec["ticket"], "the ticket moved" if moved else "the env-issue closed"))
PY
}

# Unrelayed answers for ticket $1, spilled into dir $2 as `ids` (comma
# separated, possibly empty) and `text` (the replies verbatim, each block
# behind THE SAME sentinel phase 2 writes — the successor fold is the second
# delivery vehicle for one relay mechanism, and a vehicle without the sentinel
# is an answer the next tick cannot tell from undelivered).
# Files rather than one delimited line: the replies are multi-line by nature,
# and an empty id column ahead of them is exactly the field collapse the 0x1f
# row layout above exists to avoid.
#
# TEXT BEFORE IDS, and that order is the whole safety property. The caller acks
# whatever `ids` names, and only the prompt built from `text` delivers those
# answers — so a death between the two writes decides which way the pair fails.
# ids-first leaves ids populated beside an empty text: the prompt carries no
# answers, the delivery still succeeds, and the ack fires on answers nobody
# ever saw. text-first fails the other way — answers ride the prompt, nothing
# is acked, and the feed re-serves them next tick (the sentinel makes the
# duplicate visible). Never-ack is the recoverable direction.
#
# THE CAP MATTERS MORE HERE than at the drain loop. /answers/unrelayed is flat,
# capped at 500 rows (arkho API.md §1), and this is the one site that FILTERS
# that capped read down to ONE ticket: with more than 500 standing unrelayed
# answers, this ticket's replies could sit past the cap and simply not be
# folded — silently, until the backlog drains. Nothing approaches the cap
# today; paging this route is an arkho follow-up if the board ever nears it.
_fold_answers() {  # <ticket> <dir>
  T_TID="$1" T_DIR="$2" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_TID"]
d = os.environ["T_DIR"]
mine = [a for a in A.unrelayed() if str(a.get("ticketId")) == tid]
with open(os.path.join(d, "text"), "w") as f:
    f.write("\n\n".join(A.SENTINEL % a["answerEventId"] + "\n" +
                        "\n".join(a.get("replies") or []) for a in mine))
with open(os.path.join(d, "ids"), "w") as f:
    f.write(",".join(str(a["answerEventId"]) for a in mine))
PY
}

# The successor's orientation. The timeline read is not a courtesy: the
# ticket's park/answer history — including answers already delivered to the
# session being replaced, and already acked — lives only there, and the claim
# body alone would silently drop exactly what the park existed to obtain.
#
# The marker is per successor RUN, not per ticket: every cycle claims a fresh
# run, so a later cycle can never read an earlier cycle's delivery as its own.
# Same principle as the relay sentinel — the durable record of delivery is the
# delivery itself, and no new state file is needed to hold it.
_successor_marker() { printf '[board-successor run:%s]' "$1"; }

_successor_prompt() {  # <ticket> <run> <folded answer text ('' if none)> <parent pin ('' if none)>
  # The pin block is assembled OUT here rather than as a `${4:+...}` inside the
  # heredoc: bash 3.2 parses the word of that expansion for quoting, so the
  # apostrophe in the sentence would open a quote that swallows the closing
  # brace ("bad substitution") and the whole prompt would come back empty.
  local pin=""
  [ -z "${4:-}" ] || pin="

Parent pin (your run's parent-contract window): $4 — the parent contract
snapshot your dispatch was cut against; no board read hands it over."
  cat <<EOF
$(_successor_marker "$2") You are the successor run for ticket #$1 — your
predecessor was reclaimed, so the board handed its work to you on a fresh run.

Read your own ticket timeline FIRST (board-show.sh $1). The park and answer
history there is part of your assignment: answers delivered to the session you
are replacing live in it and nowhere else. Then continue under your original
protocol.$pin${3:+

---- answers relayed with this resume (verbatim) ----
$3}
EOF
}

# THE SUCCESSOR INHERITS ITS PREDECESSOR'S LANE. A fresh process has no earlier
# conversation to carry the architect / spike / qagent protocol, so a fallback
# that always spent IMPLEMENT_MODEL on a generic orientation prompt handed an
# Architect's ticket to an executor, on the wrong model, with no plan-
# authorship protocol anywhere in its context. The lane is read off the meta the
# dispatcher stamped it on (the predecessor's), which survives the run's end —
# see _retire_run_locally. Which is why the scan is the `all` one: by the time a
# successor is claimed the predecessor's run is normally already RETIRED (the
# renew that answered run-ended is what put the ticket on this feed), so the
# run-carrying scan no longer shows it and every recovery read lane "".
_lane_for_ticket() {  # <ticket> — the lane stamped on a meta bound to it, or ''
  _registry_metas all | awk -F$'\x1f' -v t="$1" '$4 == t && $7 != "" { print $7; exit }'
}
_role_for_lane() {
  case "$1" in architect) echo ARCHITECT ;; spike) echo SPIKE ;;
               qagent) echo QAGENT ;; *) echo IMPLEMENT ;; esac
}
_model_for_lane() {
  # Same two knobs, same defaults, as the dispatchers': plan authorship is the
  # frontier tier, worker lanes are the worker tier. Inheriting the operator's
  # own session model here would silently re-fuse the two prices.
  case "$1" in architect) echo "${ARCHITECT_MODEL:-fable}" ;;
               *) echo "${IMPLEMENT_MODEL:-opus}" ;; esac
}
_protocol_for_lane() {
  local skills; skills="$(cd "$SCRIPT_DIR/../.." && pwd)"
  case "$1" in
    architect) echo "$skills/architecting/SKILL.md" ;;
    spike)     echo "$skills/executing/references/spike-worker-protocol.md" ;;
    *)         echo "$skills/executing/SKILL.md" ;;
  esac
}

# One claim-journal entry, written whole. json.dump rather than printf: the
# run id must land as a JSON number (or null), and BOTH dispatchers parse
# every file in this shared directory — one they cannot read is reported and
# left forever. Lane `successor` is outside both dispatchers, lane sets on
# purpose: neither may replay or end a run it does not own.
_journal() {  # <path> <run-id ('' = null)> <spawn-completed 0|1> <ticket> <daemon> [session]
  J_PATH="$1" J_RUN="$2" J_DONE="$3" J_TICKET="$4" J_DAEMON="$5" \
  J_SESSION="${6:-}" python3 - <<'PY'
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
j = {"lane": "successor", "run_id": run, "spawn_completed": e["J_DONE"] == "1"}
if e["J_TICKET"]:
    j["ticket"] = e["J_TICKET"]
if e["J_DAEMON"]:
    j["daemon"] = e["J_DAEMON"]
# The session the delivery was aimed at, recorded the moment the claim names
# it: reconciliation reads its TRANSCRIPT to tell a delivery that landed from
# one that never happened, and after a crash that transcript is the only
# witness either way.
if e["J_SESSION"]:
    j["session"] = e["J_SESSION"]
with open(e["J_PATH"], "w") as f:
    json.dump(j, f)
    f.write("\n")
PY
}

# PERSIST BEFORE RESUME. The successor run identity has to be durable before
# any delivery attempt: a crash after the resume but before the bind is
# repaired by phase 1 only if the registry already names run_id/fence/bearer,
# and a granted run no meta knows is one nothing local can ever speak for
# again. The predecessor session is the one being resumed, so its meta is the
# one updated — resolved by FILENAME, the identity board-bind and every other
# tool resolves by (the `uuid` field only mirrors it, and a stale mirror names
# a session nothing can reach).
_persist_successor() {  # <uuid> <run> <fence> <bearer> <ticket>
  T_UUID="$1" T_RUN="$2" T_FENCE="$3" T_BEARER="$4" T_TID="$5" T_DHOME="$DAEMON_HOME" \
  python3 - <<'PY'
import fcntl, json, os
env = os.environ
home = env["T_DHOME"]
path = os.path.join(home, env["T_UUID"] + ".json")
lock = open(os.path.join(home, ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    with open(path) as f:
        m = json.load(f)
    m["run_id"] = int(env["T_RUN"])
    m["fence"] = int(env["T_FENCE"])
    m["run_bearer"] = env["T_BEARER"]
    m["ticket"] = env["T_TID"]
    # A claim about what the SERVER accepted, and nothing has been posted yet.
    m["bind_confirmed"] = False
    # 0600 from creation: the meta now carries the run bearer, and the secret
    # must not exist world-readable even for the width of one write. The mode
    # argument only applies to an inode this open CREATES, so a leftover .tmp
    # from an earlier crash — 0644, world-readable — would simply be truncated
    # and handed the bearer, with the chmod arriving after the write. Unlink
    # first and create exclusively, so the file this bearer lands in is always
    # one this call made.
    tmp = path + ".tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(m, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
}

# Claim a successor for ticket $1 and deliver it. Called behind `|| true`,
# which suspends errexit through the whole subtree, so every step is guarded
# explicitly.
# ---- successor claim-journal reconciliation --------------------------------
# The `successor` lane sits OUTSIDE both dispatchers, lane sets by design — and
# for the whole branch that meant NOTHING reconciled it. Two crash windows lived
# in the gap, and both end in the same place: a ticket the board thinks is owned
# and this machine cannot move.
#
#   replay   the journal names no run: claim-successor went out and its response
#            was lost. The run may well have been granted, in which case the
#            ticket is owned and never comes back on needing-resume. The nonce
#            is what the contract provides for exactly this — replayed, the
#            server hands back the SAME claim (with a rotated bearer).
#   settle   the journal names a run but was never marked handed off: the claim
#            landed and the delivery did not complete. If the successor marker
#            is in the target session's transcript the delivery DID land and
#            only the bookkeeping was lost — closed, and phase 1 finishes the
#            bind. Otherwise nothing was delivered, so the run is released and
#            the ticket returns to needing-resume for a clean recovery.
#   orphaned the journal names a spawned daemon the registry still knows: a live
#            worker whose bind never landed. NOT ended (that would kill it) and
#            not replayed — reported, and the server's lease reclaim owns it.
#
# Runs BEFORE the feed is read, so anything it releases is served in this tick,
# and AFTER the lift pass, so a just-lifted ticket replays its own standing
# journal here rather than minting a fresh nonce down in the feed loop.
#
# A SUPPRESSED TICKET IS FROZEN, ITS JOURNAL INCLUDED. Suppression means "stop
# spending recovery on this ticket until a human clears the substrate", and a
# reconciliation that kept replaying the journal spent it anyway: every replay
# charged another cycle, every third cycle re-escalated, and each re-escalation
# rewrote the suppression record with the state read seconds earlier in the same
# tick — so _check_lift's `moved` could never fire and the "move the ticket"
# half of the escalation's own instructions was inert. The journal is left
# exactly where it is; it is still the retry handle when the suppression lifts.
# The price of "untouched" is real and small: a suppressed ticket's undelivered
# successor run now holds until its lease expires rather than being released
# here, and the orphan warning is silent for the duration of the suppression.
#
# $RESUMED_LEDGER (phase_resume owns it) collects the tickets this TICK
# ATTEMPTED a recovery for — written before the attempt, because a guard that
# leaves the ticket for the next tick has spent this ticket's turn either way.
# Of the reconciliation arms only replay writes it: settle and orphaned make no
# claim, and settle's release is designed to be served by this very tick's
# feed. The feed loop writes it too — an attempt is an attempt whichever door
# it came through, and phase 4 reads the ledger to stay off both.
_reconcile_successors() {
  local plan lines line act nonce run tid sess daemon transcript
  [ -d "$CLAIMS_DIR" ] || return 0
  plan="$(T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
home = os.environ["T_DHOME"]
live, names = set(), set()
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("run_id"):
        live.add(str(m["run_id"]))
    # ONLY A RUNNING SESSION IS EVIDENCE OF A SPAWN — the same rule
    # _claim_journal.sh already applies on the dispatchers' side. Successor
    # names are deterministic per ticket and lane (`<ticket>-successor-<lane>`)
    # and `sminos retire` keeps the record unless --purge, so a HISTORICAL entry
    # from an earlier recovery matched the new journal's name: the crash was
    # misread as `orphaned`, the journal was closed as complete, and the run
    # just claimed owned the ticket with nobody able to speak for it until the
    # lease expired.
    if m.get("name") and m.get("status") in ("working", "blocked"):
        names.add(str(m["name"]))
for p in sorted(glob.glob(os.path.join(home, "board-claims", "*.json"))):
    try:
        j = json.load(open(p))
    except Exception:
        # Both dispatchers already report an unreadable journal and leave it;
        # a third voice saying the same thing every tick adds nothing.
        continue
    if j.get("lane") != "successor" or j.get("spawn_completed"):
        continue
    nonce = os.path.basename(p)[:-5]
    run = j.get("run_id")
    row = (nonce, str(run or ""), str(j.get("ticket") or ""),
           str(j.get("session") or ""), str(j.get("daemon") or ""))
    # 0x1f, NOT tab, for the same reason the registry rows use it: TAB IS IFS
    # WHITESPACE, so a run of tabs collapses into one delimiter and every field
    # after an empty column shifts left. Three of these five columns are
    # routinely empty — `run` is empty for EVERY replay row, by definition —
    # so the replay arm read the ticket out of the run column, found it empty,
    # and silently did nothing at all; a settle row with no session read the
    # daemon name as the session. 0x1f is IFS-non-whitespace and cannot occur
    # in a nonce, a ticket id or a daemon name.
    if not run:
        print("replay\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s" % row)
    elif row[4] and row[4] in names:
        print("orphaned\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s" % row)
    else:
        print("settle\x1f%s\x1f%s\x1f%s\x1f%s\x1f%s" % row)
PY
)" || { echo "resume: successor journal reconciliation failed — skipped this tick" >&2; return 0; }
  [ -n "$plan" ] || return 0
  # The whole plan is read BEFORE anything acts on it: every action below runs
  # children that inherit this stdin, and one of them consuming the rest would
  # silently drop recoveries.
  lines=()
  while IFS= read -r line; do
    [ -n "$line" ] && lines+=("$line")
  done <<<"$plan"
  for line in ${lines[@]+"${lines[@]}"}; do
    IFS=$'\x1f' read -r act nonce run tid sess daemon <<<"$line"
    if [ -n "$tid" ] && _suppressed "$tid"; then
      echo "resume: successor claim $nonce for #$tid is suppressed — the journal stands untouched until the suppression lifts"
      continue
    fi
    case "$act" in
      replay)
        # The ledger is CONSULTED here as well as written, or the invariant
        # holds only across the hand-off to the feed and not within this pass:
        # two unfinished journals naming one ticket are two replay rows, and
        # each one claimed and charged. Reachable because the intermediate
        # commit on this branch minted an extra journal per tick during a claim
        # fault, so a registry that ticked on it arrives here holding several.
        if [ -n "$tid" ] && grep -qxF -- "$tid" "$RESUMED_LEDGER"; then
          echo "resume: successor claim $nonce waits — #$tid already had its one recovery attempt this tick"
          continue
        fi
        echo "resume: successor claim $nonce never reached a run — replaying it for #$tid"
        [ -z "$tid" ] || { printf '%s\n' "$tid" >> "$RESUMED_LEDGER"
                           _resume_one "$tid" "$nonce" || true; } ;;
      orphaned)
        echo "resume: successor claim $nonce spawned $daemon for run $run but never bound it — the session is live and is NOT being ended; it holds no bearer at rest, so no later relay or resume can speak for it (retire it by hand once it is done)" >&2
        _journal "$CLAIMS_DIR/$nonce.json" "$run" 1 "$tid" "$daemon" "$sess" ;;
      settle)
        # An UNRESOLVED FORK on the target session is the one shape this may not
        # settle either way: the fork may be live on exactly this run, so
        # releasing it would put a successor beside a working worker, and
        # closing the journal would claim a delivery nobody can see. Held.
        if [ -n "$sess" ] && [ "$(_liveness "$sess")" = forked ]; then
          echo "resume: successor run $run for #$tid is HELD — its target session $sess carries an unresolved fork that may be live on it; neither released nor closed until the fork resolves" >&2
          continue
        fi
        transcript=""
        [ -z "$sess" ] || transcript="$(_transcript_for_uuid "$sess")"
        if _delivered "$transcript" "$(_successor_marker "$run")"; then
          echo "resume: successor run $run was delivered to $sess but never recorded — closing the journal; phase 1 completes the bind"
          _journal "$CLAIMS_DIR/$nonce.json" "$run" 1 "$tid" "$daemon" "$sess"
        else
          echo "resume: successor run $run was claimed for #$tid and never delivered — releasing it so the ticket returns to needing-resume"
          # THE JOURNAL IS THE ONLY RETRY HANDLE. A transport or service outage
          # fails the release while the run stays open and keeps owning the
          # ticket — and deleting the journal anyway removed the one record any
          # later tick could retry from, so "retried next tick" was never true
          # and recovery stalled until the lease reclaimed the run. It goes only
          # on a release that actually landed (a typed run-ended answer counts:
          # the run is already over).
          if T_RUN="$run" _api_py - <<'PY'
import os
import _board_api as A
try:
    A.end_run(os.environ["T_RUN"], "abandoned")
except A.RunEnded:
    pass
PY
          then
            rm -f "$CLAIMS_DIR/$nonce.json"
          else
            echo "resume: releasing successor run $run failed — the journal is KEPT so the next tick can retry the release" >&2
          fi
        fi ;;
    esac
  done
}

_resume_one() {
  local tid="$1" nonce="${2:-}" dir exports ids text prompt transcript delivered=""
  local pre_pending="" post_pending="" lane="" role=""
  local C_CLAIMED=0 C_RUN="" C_FENCE="" C_BEARER="" C_SESS="" C_PIN="" C_OBSOLETE=""
  # AN UNRESOLVED FORK IS NOT A RESUMABLE SESSION, and that is settled BEFORE
  # the claim so this tick never mints a successor run it cannot deliver.
  # `sminos resume` stamps status=error + pending_short when a fork LAUNCHED
  # whose session uuid never resolved, and deliberately leaves `current` on the
  # superseded turn. Resuming there forks AGAIN — a fresh zombie turn every
  # tick, each one possibly live on the same run — and no delivery can ever be
  # proven, because every transcript read lands on the old turn. Skip, surface,
  # charge no cycle: nothing was attempted, so nothing failed.
  local f_uuid f_rest
  # shellcheck disable=SC2034  # f_rest exists to absorb the other columns
  while IFS=$'\x1f' read -r f_uuid f_rest; do
    [ "$(_liveness "$f_uuid")" = forked ] || continue
    echo "resume: #$tid — the bound session $f_uuid carries an UNRESOLVED FORK (status=error + pending_short); no successor claimed and no cycle charged until it resolves — recover the fork by hand (its meta names it in pending_short) or retire the session" >&2
    return 1
  done < <(_metas_for_ticket "$tid" all)
  _scan_ok || { echo "resume: #$tid — registry scan failed; the fork guard cannot run, so this ticket is left for the next tick" >&2; return 1; }
  # The predecessor's lane/role, for the fresh-spawn fallback and the successor
  # meta stamp below. Read here, while the predecessor meta is still the one
  # bound to this ticket — and read through the `all` scan, because that meta
  # has usually already lost its run to _retire_run_locally.
  lane="$(_lane_for_ticket "$tid")"; role="$(_role_for_lane "$lane")"
  # A FAILED SCAN IS NOT AN EMPTY LANE. "" is also what a scan that never ran
  # returns, and it routes an architect/spike/qagent ticket to a generic
  # executor on the wrong model with the wrong protocol. Left for the next
  # tick instead, exactly as the fork guard above does.
  _scan_ok || { echo "resume: #$tid — registry scan failed; the predecessor's lane is unreadable, so this ticket is left for the next tick rather than recovered as an executor" >&2; return 1; }
  # A nonce handed in by reconciliation is a REPLAY of a claim that may already
  # have landed: the server answers it with the same run rather than a second.
  [ -n "$nonce" ] || nonce="$(_claim_nonce)" || return 1
  mkdir -p "$CLAIMS_DIR"
  dir="$(mktemp -d "$SCRATCH/resume.XXXXXX")"
  # Journalled BEFORE the POST, the dispatchers, rule: a crash between the two
  # leaves a record, and the server answers a repeated nonce with the same
  # claim rather than a second one.
  _journal "$CLAIMS_DIR/$nonce.json" '' 0 "$tid" ''
  # One process for the whole exchange (the dispatchers, _claim_one idiom):
  # claim, spill the assignment body, hand back shell-quoted facts. The run
  # bearer crosses exactly one boundary and is never echoed.
  # (Apostrophes are avoided in this heredoc on purpose: bash 3.2 rescans a
  # heredoc body nested in $( ) for quoting, and a lone one is a parse error.)
  exports="$(T_TID="$tid" T_NONCE="$nonce" T_BODY="$dir/body.md" _api_py - <<'PY'
import os, shlex
import _board_api as A
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
try:
    out = A.claim_successor(os.environ["T_TID"], os.environ["T_NONCE"])
except A.ClaimObsolete as e:
    # A spent handle, not a sick board — handed back as a fact for the shell
    # to route on rather than as the failure exit every other refusal takes.
    q("C_OBSOLETE", e.code)
    raise SystemExit(0)
if not out.get("claimed", True):
    q("C_CLAIMED", 0)
    raise SystemExit(0)
missing = [f for f in ("runId", "fence", "bearer") if f not in out]
if missing:
    # Never echo the payload back: it carries the run bearer.
    A.die("claim-successor answered without %s — the run cannot be delivered"
          % ", ".join(missing))
q("C_CLAIMED", 1)
q("C_RUN", out["runId"])
q("C_FENCE", out["fence"])
q("C_BEARER", out["bearer"])
# The parent-contract window, flattened into the dispatchers exact spelling.
# Empty when the run has no parent: a rendered "#None @ event None" is worse
# than silence, because a worker would act on it.
pin = out.get("parentPin") or {}
q("C_PIN",
  "#%s @ event %s" % (pin.get("parent_id"), pin.get("parent_event_cursor"))
  if pin.get("parent_id") is not None else "")
loc = out.get("sessionLocator") or {}
q("C_SESS", loc.get("sessionId") or "")
with open(os.environ["T_BODY"], "w") as f:
    f.write(out.get("body") or "")
PY
)" || {
    # A FAULT, and the first exit that ever charged for one: transport death
    # after retries, a 5xx, a malformed grant, an untyped refusal. Left
    # uncounted, a ticket whose claim persistently errors churns forever — and
    # the kept journal is re-classified `replay` next tick while the feed ALSO
    # re-serves the ticket, so the churn costs two claims and a leaked journal
    # a tick. The journal STAYS: a claim that died on the wire may still have
    # landed, and it is the only handle a replay has.
    echo "resume: #$tid — successor claim failed; journal $nonce kept" >&2
    _attempts "$tid" fail
    return 1
  }
  eval "$exports"
  # THE JOURNAL IS OBSOLETE, NOT THE SUBSTRATE SICK. `nonce-consumed` says the
  # predecessor's run ended, so this nonce is spent for good; `stale-resume`
  # says the ticket moved after the feed read, so its new state governs.
  # Neither is a fault to charge: the handle is dropped and the ticket comes
  # back around — on a fresh nonce, or through ordinary dispatch.
  if [ -n "$C_OBSOLETE" ]; then
    rm -f "$CLAIMS_DIR/$nonce.json"
    echo "resume: #$tid — the successor journal is obsolete ($C_OBSOLETE); dropped uncharged, and the ticket comes back around on its own"
    return 0
  fi
  # Uncharged on purpose: no grant is the server's BACKPRESSURE — a lane cap,
  # an eligibility rule — and a healthy wait state. A suppression written from
  # it would take a healthy ticket out of both the resume and the dispatch
  # phase until a human closed an env-issue, which is strictly worse than the
  # wait it would be "fixing".
  if [ "$C_CLAIMED" != 1 ]; then
    rm -f "$CLAIMS_DIR/$nonce.json"
    echo "resume: #$tid — the board granted no successor"
    return 0
  fi
  _journal "$CLAIMS_DIR/$nonce.json" "$C_RUN" 0 "$tid" '' "$C_SESS"

  : > "$dir/ids"; : > "$dir/text"
  _fold_answers "$tid" "$dir" \
    || echo "resume: #$tid — unrelayed feed unreadable; answers stay on it" >&2
  ids="$(cat "$dir/ids")"
  text="$(cat "$dir/text")"
  prompt="$(_successor_prompt "$tid" "$C_RUN" "$text" "$C_PIN")"

  # PERSIST-BEFORE-RESUME IS A BOUNDARY, NOT A PREFERENCE. Delivering anyway
  # past a failed persist produces the exact state the boundary exists to
  # forbid: a granted run whose identity, fence and bearer live nowhere on this
  # machine, so a death between the delivery and the late bind leaves nothing
  # able to speak for it ever again. The run is released and the item is left
  # for the next tick, where a working registry can do it properly.
  if [ -n "$C_SESS" ] && ! _persist_successor "$C_SESS" "$C_RUN" "$C_FENCE" "$C_BEARER" "$tid"; then
    echo "resume: #$tid — registry persist FAILED; run $C_RUN is released rather than delivered to a session nothing could recover" >&2
    rm -f "$CLAIMS_DIR/$nonce.json"
    _attempts "$tid" fail "$C_RUN"
    return 1
  fi

  # The pending-fork watermark, read BEFORE the resume so the fallback below
  # can tell a fork THIS call launched from a stale one an earlier tick left
  # behind — a leftover pending_short must not wedge the ticket forever.
  [ -z "$C_SESS" ] || pre_pending="$(_meta_field "$DAEMON_HOME/$C_SESS.json" pending_short)"

  # `sminos resume` forks a fresh process from OUR env, so the successor
  # credentials ride the invocation or the worker can write nothing. The wait
  # is bounded for the same reason phase 2 bounds it: this tick holds the
  # whole-tick lock throughout, and `sminos resume` defaults to hours.
  if [ -n "$C_SESS" ] && BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN" \
       BOARD_RUN_FENCE="$C_FENCE" BOARD_API_URL="$BOARD_API_URL" \
       DAEMON_TIMEOUT="$RELAY_RESUME_TIMEOUT" \
       "$SMINOS_CLI" resume --wait "$C_SESS" "$prompt"; then
    delivered="$C_SESS"
    echo "resume: #$tid run $C_RUN → resumed session $C_SESS"
  elif [ -n "$C_SESS" ] && transcript="$(_transcript_for_uuid "$C_SESS")" \
       && _delivered "$transcript" "$(_successor_marker "$C_RUN")"; then
    # A BOUNDED WAIT IS NOT A FAILED DELIVERY. `sminos resume` forks the turn,
    # advances the meta and injects this prompt BEFORE it blocks, then exits 1
    # when its watcher expires — and a successor turn routinely runs longer
    # than the bound this tick needs in order not to starve lease renewal, so
    # this is the COMMON case, not the corner. Fresh-spawning on it would put
    # a second worker on a run the first one is actively holding. The
    # transcript is the marker, exactly as in phase 2.
    delivered="$C_SESS"
    echo "resume: #$tid run $C_RUN → the resume wait expired but the delivery landed in $C_SESS"
  else
    # AN AMBIGUOUS RESUME IS NOT A FAILED ONE. `sminos resume` has a third
    # outcome beside delivered and failed: the fork LAUNCHED, but its session
    # uuid never resolved, so it stamps status=error + pending_short and
    # deliberately leaves `current` on the old turn. The marker check above
    # then reads the PREDECESSOR's transcript, finds nothing, and fresh-spawning
    # on that would put a second worker onto a run a live fork may already be
    # holding — the same double-spawn the expired-wait branch exists to prevent,
    # by the other door. Delivery is unknown, so this tick neither spawns nor
    # charges a cycle: next tick reads a resolved `current` (or the operator
    # recovers the fork through pending_short) and settles it.
    [ -z "$C_SESS" ] || post_pending="$(_meta_field "$DAEMON_HOME/$C_SESS.json" pending_short)"
    if [ -n "$post_pending" ] && [ "$post_pending" != "$pre_pending" ]; then
      # Reported as an UNRESOLVED outcome, and returned as one: a success here
      # said "this ticket is handled" about a run whose worker nobody can name.
      # No cycle is charged either — nothing failed, the answer is simply not
      # known yet — and the guard at the top of this function refuses to claim
      # a further successor until the fork resolves or is recovered by hand.
      echo "resume: #$tid run $C_RUN → the resume forked a turn whose session never resolved; delivery is AMBIGUOUS — no fresh spawn this tick, and no further successor until the fork (pending_short=$post_pending) resolves" >&2
      return 1
    fi
    # A QAGENT IS NOT FRESH-SPAWNABLE FROM HERE. A Reviewer worker only functions
    # with its control directory, its accepted-commits ledger and its review
    # barrier — all built by review-dispatch's own handover, none of them
    # reproducible here except as a second, drifting copy of it. The designed
    # route already exists: release the run, and the review dispatcher's
    # ordinary claim converts the unowned in-flight ticket into a properly
    # equipped successor (API.md, cold-successor conversion). The folded
    # answers are NOT acked, so the feed re-serves them to whoever picks it up.
    if [ "$lane" = qagent ]; then
      echo "resume: #$tid — the predecessor session could not be resumed, and a QAgent cannot be fresh-spawned from the tick (it needs its review barrier and accepted-commit ledger); releasing run $C_RUN so the review dispatcher claims a fully equipped successor" >&2
      rm -f "$CLAIMS_DIR/$nonce.json"
      _attempts "$tid" fail "$C_RUN"
      return 1
    fi
    # FRESH SPAWN ON THE SAME SUCCESSOR BEARER, IN THE PREDECESSOR'S LANE. A
    # successor is a fresh run by contract; resuming the predecessor session is
    # an optimization, not the substance. But a fresh PROCESS carries none of
    # the predecessor's conversation, so the lane's own protocol has to be named
    # and the lane's own model pinned — a generic implement prompt on
    # IMPLEMENT_MODEL is the wrong worker for an architect or a spike ticket.
    # The assignment body rides along too: by contract it is the only route a
    # run has to its own ticket text, and this session has never seen it.
    local name="$tid-successor${lane:+-$lane}" spawn_out uuid
    prompt="$prompt

You are a FRESH process: nothing of your predecessor's context is in it. Read
your protocol for this lane FIRST — $(_protocol_for_lane "$lane") — and work as
$role.

---- assignment (from the successor claim) ----
$(cat "$dir/body.md")"
    # The daemon NAME is journalled BEFORE the spawn, the dispatchers' rule: the
    # run reaches a registry meta only through board-bind at the very end of the
    # handover, so a crash anywhere in the spawn leaves a journal with a run no
    # meta knows — indistinguishable from a run that never spawned at all. The
    # name is the only evidence of that session which exists before the bind,
    # and reconciliation needs it to tell "never spawned" from "spawned, live,
    # unbound" (which is never ended).
    _journal "$CLAIMS_DIR/$nonce.json" "$C_RUN" 0 "$tid" "$name" "$C_SESS"
    # DAEMON_CLAUDE_SETTINGS/EFFORT cleared for the dispatchers, reason: this
    # tick can itself run inside a gateway-routed seat, and `sminos spawn`
    # persists what it inherits into the record, so every later resume would
    # ride the gateway while the log said claude.
    if spawn_out="$(BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN" \
         BOARD_RUN_FENCE="$C_FENCE" BOARD_API_URL="$BOARD_API_URL" \
         DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT='' \
         "$SMINOS_CLI" spawn "$name" "$prompt" \
         --cwd "${LOCAL_REPO:-$BOARD_ROOT}" --worktree "$name" \
         --model "$(_model_for_lane "$lane")")"; then
      printf '%s\n' "$spawn_out"
      uuid="$(printf '%s\n' "$spawn_out" \
        | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
      if [ -n "$uuid" ]; then
        delivered="$uuid"
        echo "resume: #$tid run $C_RUN → fresh worker $uuid (session resume failed)"
      else
        echo "resume: #$tid — spawned worker UUID unparseable (a session may be orphaned)" >&2
      fi
    fi
  fi

  if [ -z "$delivered" ]; then
    echo "resume: #$tid — neither vehicle delivered run $C_RUN" >&2
    rm -f "$CLAIMS_DIR/$nonce.json"
    _attempts "$tid" fail "$C_RUN"
    return 1
  fi
  # OWNERSHIP BEFORE ACKNOWLEDGEMENT. The bearer goes THROUGH board-bind so it
  # lands at rest in the DELIVERED session's own meta — a freshly spawned one
  # holds nothing at all until this runs. Marking the journal handed-off,
  # acking the folded answers and resetting the failure counter ahead of it
  # claimed a durability that did not exist yet: a crash in that window left the
  # real worker with no credentials, phase 1 repairing the run onto the
  # PREDECESSOR meta (the only one naming it), and the answers acked off a feed
  # that had delivered them nowhere recoverable. Same persist-before-resume
  # principle the successor leg already obeys, applied to the fresh-spawn leg.
  if ! BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN" BOARD_RUN_FENCE="$C_FENCE" \
       "$SCRIPT_DIR/board-bind.sh" "$delivered" "$tid"; then
    if [ "$delivered" = "$C_SESS" ]; then
      # The resumed session's own meta already names run/fence/bearer
      # (persist-before-resume), so phase 1 has everything it needs to finish.
      echo "resume: #$tid — bind FAILED; phase 1 repairs it next tick" >&2
    else
      # A fresh worker whose bearer never landed can never be spoken for again,
      # and no repair can even find it — its meta names no run. Retire it and
      # release the run rather than leave an unreachable worker on the lease.
      echo "resume: #$tid — the fresh worker could not be bound; retiring it and releasing run $C_RUN" >&2
      "$SMINOS_CLI" retire "$delivered" >/dev/null 2>&1 || true
      rm -f "$CLAIMS_DIR/$nonce.json"
      _attempts "$tid" fail "$C_RUN"
      return 1
    fi
  fi
  _stamp_lane "$delivered" "$lane" "$role" "$C_PIN"
  _journal "$CLAIMS_DIR/$nonce.json" "$C_RUN" 1 "$tid" "$delivered" "$C_SESS"
  # ACK ONLY AFTER DELIVERY, exactly as phase 2 does: a folded answer that was
  # never delivered stays on the feed for the next tick rather than being
  # acked-and-dropped.
  if [ -n "$ids" ]; then
    T_IDS="$ids" _api_py - <<'PY' || echo "resume: #$tid — ack failed; the feed re-serves next tick" >&2
import os
import _board_api as A
for aid in os.environ["T_IDS"].split(","):
    if aid:
        A.ack(aid)
PY
  fi
  _attempts "$tid" reset
}

# Lane and role onto the DELIVERED meta. Without them the dispatchers' local cap
# cannot see this open run at all — it counts lane-stamped metas holding a run —
# so every recovery silently loosened the combined executor+spike cap the
# client owns by one. Non-fatal: the server's own laneCap still bounds it.
#
# The parent pin rides here too: this is the ONE stamp point BOTH delivery legs
# share (it runs after board-bind for the resumed session and the fresh spawn
# alike), while _persist_successor runs only when a session locator exists and
# board-bind writes no parent_pin at all.
_stamp_lane() {  # <uuid> <lane> <role> [parent-pin]
  # No lane, nothing stamped — and the pin shares the lane's fate: an unknown
  # predecessor lane drops `parent_pin` from the meta too. Deliberate. The
  # prompt is the pin's actual delivery channel and carries it unconditionally;
  # nothing reads `parent_pin` back out of a meta yet; and in this same state
  # the lane itself is already lost, so the meta is incomplete either way.
  [ -n "${2:-}" ] || return 0
  T_PATH="$DAEMON_HOME/$1.json" T_LANE="$2" T_ROLE="$3" T_PIN="${4:-}" T_DHOME="$DAEMON_HOME" \
  python3 - <<'PY' || echo "resume: lane/role stamp on $1 failed (non-fatal)" >&2
import fcntl, json, os
env = os.environ
lock = open(os.path.join(env["T_DHOME"], ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    path = env["T_PATH"]
    with open(path) as f:
        m = json.load(f)
    m["lane"] = env["T_LANE"]
    m["role"] = env["T_ROLE"]
    if env.get("T_PIN"):
        m["parent_pin"] = env["T_PIN"]
    mode = 0o600 if m.get("run_bearer") else os.stat(path).st_mode & 0o777
    tmp = path + ".tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
        json.dump(m, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
}

# Failed-cycle counter, in the registry beside the suppression records.
_attempts() {  # <ticket> reset|fail [run-to-release]
  local f="$SUPPRESS_DIR/.attempts-$1" n
  mkdir -p "$SUPPRESS_DIR"
  if [ "$2" = reset ]; then rm -f "$f"; return 0; fi
  n="$(( $(cat "$f" 2>/dev/null || echo 0) + 1 ))"
  echo "$n" > "$f"
  # An undeliverable successor run must not squat the ticket until its lease
  # expires: released now, so the next tick claims a fresh one.
  if [ -n "${3:-}" ]; then
    T_RUN="$3" _api_py - <<'PY' || echo "resume: #$1 — releasing run $3 failed" >&2
import os
import _board_api as A
try:
    A.end_run(os.environ["T_RUN"], "abandoned")
except A.RunEnded:
    pass
PY
  fi
  # "cycle 4 of 3" is what the plain label printed once an escalation deferred
  # itself (an unreadable board state holds the counter rather than resetting
  # it), which reads as a broken counter rather than the pending escalation it
  # actually is.
  if [ "$n" -le 3 ]; then
    echo "resume: #$1 — recovery cycle $n of 3 failed"
  else
    echo "resume: #$1 — recovery cycle $n failed; the 3-cycle ladder is done and the escalation is still pending (it defers until the board can name the state it would freeze)"
  fi
  [ "$n" -ge 3 ] || return 0
  _escalate "$1"
}

# AUTOMATION HAS NO TRANSITION AUTHORITY (the matrix admits humans and runs
# only), and that constraint is obeyed rather than worked around: gh mode
# parks a thrice-failed worker needs-human, this side registers an env-issue
# (born needs-human server-side) and suppresses the ticket. The env-issue is
# the signal; the suppression record is what stops the churn.
_escalate() {  # <ticket>
  local tid="$1" state eid
  state="$(T_TID="$tid" _api_py - <<'PY'
import os
import _board_api as A
row = A.ticket(os.environ["T_TID"], principal="automation")
print(row["state"] if row else "")
PY
)" || { echo "resume: #$tid — board state unreadable; escalation deferred" >&2; return 1; }
  # AN EMPTY ANSWER IS NOT A STATE. The read is by id now, so "" is the board
  # saying authoritatively that no such ticket exists rather than a listing
  # that might merely have been short — but the deferral is right either way,
  # because a suppression record needs a state it can NAME. A record written
  # from "" would say `"state": ""`, against which _check_lift's
  # `moved = current != recorded` is true for every value the board can ever
  # return: the suppression would lift on the very next tick, the ladder would
  # run again, and the human would collect a fresh env-issue every three
  # cycles. The counter stands, so the next tick retries.
  [ -n "$state" ] || {
    echo "resume: #$tid — board state came back empty (no such ticket); escalation deferred" >&2
    return 1; }
  # THE REGISTRATION IS RECOVERABLE, because it is not atomic with the record
  # it authorizes. A1 can commit the env-issue and the response still be lost;
  # every retry then meets the server's dedup on this deterministic title and
  # answers `duplicate` — so a bare failure here left the ticket cycling
  # forever, escalating every three cycles, with no suppression record ever
  # written and no second env-issue ever creatable. The duplicate answer names
  # the existing ticket, and that IS the escalation: it is read back out of the
  # refusal and the suppression is written from it.
  eid="$(T_TID="$tid" _api_py - <<'PY'
import io, os, sys, contextlib
import _board_api as A
tid = os.environ["T_TID"]
payload = {"title": "stuck resume: ticket #%s cannot be revived" % tid,
           "category": "env-issue",
           "body": "Three recovery cycles failed for ticket #%s (successor "
                   "claim, resume, or fresh spawn). "
                   "The sweep has SUPPRESSED that ticket: phase 3 skips "
                   "it and phase 4 releases any claim that yields it. "
                   "Investigate the session/daemon substrate, then either "
                   "move ticket #%s (any transition) or close this env-issue "
                   "— either one lifts the suppression on the next tick."
                   % (tid, tid)}
err = io.StringIO()
try:
    with contextlib.redirect_stderr(err):
        out = A.register(payload, principal="automation")
    print(out["id"])
except BaseException:
    msg = err.getvalue()
    sys.stderr.write(msg)
    # A `duplicate` refusal means the registration ALREADY LANDED — this is the
    # lost-response retry, not a new failure. The title is deterministic, so the
    # env-issue is found by it in a full walk (rather than by parsing an id out
    # of a human-facing message); title is not a server predicate and `category`
    # is bare-only on the paged surface, so the scan stays client-side.
    # Walk absence is report-grade: a row whose sort position moved behind the
    # cursor mid-walk is missing from every page. That costs one extra
    # escalation cycle and self-heals — the raise below leaves the counter
    # standing and the next tick reads again (spec § Semantics preservation).
    if "duplicate" not in msg:
        raise
    hit = next((t["id"] for t in A.tickets_all(principal="automation")
                if t.get("title") == payload["title"]), None)
    if hit is None:
        raise
    print(hit)
PY
)" || { echo "resume: #$tid — env-issue registration failed; retried next tick" >&2; return 1; }
  T_TID="$tid" T_STATE="$state" T_EID="$eid" T_DIR="$SUPPRESS_DIR" python3 - <<'PY'
import json, os
env = os.environ
rec = {"ticket": int(env["T_TID"]), "state": env["T_STATE"],
       "env_issue": int(env["T_EID"])}
with open(os.path.join(env["T_DIR"], env["T_TID"] + ".json"), "w") as f:
    json.dump(rec, f, indent=1)
    f.write("\n")
PY
  rm -f "$SUPPRESS_DIR/.attempts-$tid"
  echo "escalated #$tid → env-issue #$eid (suppressed)"
}

phase_resume() {
  local dir f tid tids=()
  mkdir -p "$SUPPRESS_DIR"
  # LIFT FIRST: a suppression that no longer holds must not cost this tick a
  # resume it could have made — and, now that reconciliation honors suppression,
  # lifting after it would strand journals. A suppression lifting mid-tick in
  # the old order left the journal untouched in reconcile, dropped the record,
  # and then let the feed claim a FRESH nonce: the old journal survived to
  # replay beside the new successor on a later tick. Lifting first lets a
  # just-lifted ticket replay its own standing journal.
  for f in "$SUPPRESS_DIR"/*.json; do
    [ -e "$f" ] || continue
    _check_lift "$(basename "$f" .json)" \
      || echo "resume: suppression check for $(basename "$f" .json) failed" >&2
  done
  # Unfinished successor claims before the feed: a run this machine already
  # holds but never delivered keeps its ticket off the feed below, so
  # reconciling after the read would postpone every such recovery by a whole
  # tick. ONE RECOVERY ATTEMPT PER TICKET PER TICK: the ledger carries the
  # tickets reconciliation already claimed for into the feed loop, where a
  # ticket re-served by the feed would otherwise buy a second successor claim,
  # a second charged cycle and a second journal in the same tick.
  RESUMED_LEDGER="$(mktemp "$SCRATCH/resumed.XXXXXX")"
  _reconcile_successors
  dir="$(mktemp -d "$SCRATCH/feed.XXXXXX")"
  # GET /runs/needing-resume is a FLAT route too — capped at 500 rows by the
  # service's FEED_LIMIT (arkho API.md §1), with no cursor. A backlog longer
  # than that is served on the next tick; the sweep's own budget stops this one
  # well before 500 recoveries anyway.
  _api_py - > "$dir/feed" <<'PY' || { echo "resume: needing-resume feed unavailable this tick" >&2; return 0; }
import _board_api as A
for e in A.needing_resume():
    tid = e.get("ticketId")
    if tid is not None:
        print(tid)
PY
  # The whole feed is read BEFORE anything acts on it. Every action below runs
  # children (a resume, a spawn, board-bind) that inherit this shell's stdin,
  # and one of them consuming the rest of the feed would silently drop
  # recoveries — invisible until the tick that needed them.
  while IFS= read -r tid; do
    [ -n "$tid" ] && tids+=("$tid")
  done < "$dir/feed"
  for tid in ${tids[@]+"${tids[@]}"}; do
    if _suppressed "$tid"; then
      echo "resume: suppressed — skipping #$tid"
      continue
    fi
    if grep -qxF -- "$tid" "$RESUMED_LEDGER"; then
      echo "resume: #$tid — already replayed this tick"
      continue
    fi
    _budget_left || { echo "resume: tick budget exhausted — the rest of the feed rides the next tick"; break; }
    # Every live run's lease, refreshed ahead of a recovery that may block for
    # the whole bound — including the runs this ticket has nothing to do with.
    _tick_renew
    # LEDGERED BEFORE THE ATTEMPT, exactly as the replay arm does it. A feed
    # recovery that faults or releases leaves the ticket unowned and equally
    # spent, and phase 4 would otherwise claim and spawn it in the same tick.
    # A recovery that SUCCEEDS makes the ticket owned, so the record costs it
    # nothing.
    printf '%s\n' "$tid" >> "$RESUMED_LEDGER"
    _resume_one "$tid" || true
  done
}

# ---- phase 4: fresh claims -------------------------------------------------
# The dispatchers own claiming: the server owns pick order, they own the local
# cap, the claim journal and the worker handover. This phase hands them the
# tick and the suppression directory phase 3 writes — nothing else. Neither
# claims `ops`; no plugin protocol runs that lane, and lane discipline is
# exactly that line.
phase_dispatch() {
  local impl revw
  impl="$SCRIPT_DIR/../../executing/scripts/execute-dispatch.sh"
  revw="$SCRIPT_DIR/../../qa-loops/scripts/review-dispatch.sh"
  # DAEMON_HOME/SMINOS_CLI are resolved here but NOT exported (see above),
  # so they are passed explicitly: without them a non-default registry — a
  # test seam, a second fleet on one host — would silently split in two, this
  # tick renewing one registry while the dispatchers filled another.
  # BOARD_CREDENTIALS_FILE is deliberately NOT passed: it is repo-scoped, and
  # each dispatcher re-derives it from the repo it resolves for itself.
  # BOARD_TICK_DEADLINE hands the tick's own clock across the process boundary,
  # so the dispatchers can stop BETWEEN claims. The _budget_left gate below
  # admits this whole phase on one second of remaining budget, and both
  # dispatchers then run to completion inside the global lock — repeated claims
  # on every lane, plus a startup-barrier wait per review candidate. The
  # deadline bounds the phase from the inside as well as at its door. Empty
  # unless the `all` tick set it: a phase asked for by name is its own tick
  # with its own clock, and is no more gated inside the dispatchers than it is
  # at the case arm below.
  # BOARD_RESUMED_LEDGER travels for the same reason BOARD_SUPPRESS_DIR does:
  # ONE RECOVERY ATTEMPT PER TICKET PER TICK is an invariant of the TICK. A
  # replay that FAULTED leaves its ticket unowned, so the ordinary lane claim
  # below could pick that very ticket seconds later and spend a second attempt
  # on it. Empty on a phase asked for by name — that tick made no recovery
  # attempt, so it fences nothing.
  local env_common=(BOARD_SUPPRESS_DIR="$SUPPRESS_DIR" DAEMON_HOME="$DAEMON_HOME"
                    SMINOS_CLI="$SMINOS_CLI" LOCAL_REPO="${LOCAL_REPO:-$BOARD_ROOT}"
                    BOARD_RESUMED_LEDGER="${RESUMED_LEDGER:-}"
                    BOARD_TICK_DEADLINE="${TICK_DEADLINE:-}")
  env "${env_common[@]}" "$impl" --sweep \
    || echo "dispatch: the execution lanes failed this tick" >&2
  env "${env_common[@]}" "$revw" --sweep \
    || echo "dispatch: the review lane failed this tick" >&2
}

case "${1:-all}" in
  renew) phase_renew ;;
  relay) phase_relay ;;
  resume) phase_resume ;;
  dispatch) phase_dispatch ;;
  # THE BUDGET BOUNDS THE WHOLE TICK, so the phase that starts the most new
  # work is gated by it too. Relay and resume stopped taking new items and then
  # handed the tick to the dispatchers anyway, which claim fresh implement and
  # review work — including a review barrier wait — inside the same lock: a tick
  # that had already spent its 900 seconds went on to spend more. A phase asked
  # for BY NAME is its own tick with its own clock and is never gated here.
  all) phase_renew || true; phase_relay || true; phase_resume || true
       # The same budget the arms above stop on, as an absolute the dispatchers
       # can read across the process boundary. Set only here: this is the tick
       # that owns the clock.
       TICK_DEADLINE="$((TICK_START + TICK_BUDGET))"
       if _budget_left; then phase_dispatch || true
       else echo "dispatch: tick budget exhausted — fresh claims ride the next tick"; fi ;;
  *) die "usage: _sweep_api.sh [renew|relay|resume|dispatch|all]" ;;
esac
