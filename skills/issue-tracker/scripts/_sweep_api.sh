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
#   CLAIM  fresh work, by handing the tick to implement-dispatch.sh and
#          review-dispatch.sh in their API claim modes. They own pick-order
#          hand-off, the local cap and the claim journal; this tick only hands
#          them the suppression directory the resume phase writes.
#
# Env:
#   DAEMON_HOME DAEMON_SCRIPTS   registry + daemon toolkit (test seams)
#   SWEEP_LOCK_STALE             minutes before a held tick lock is stolen (30)
#   BOARD_RELAY_RESUME_TIMEOUT   DAEMON_TIMEOUT for a relay OR successor resume
#                                (300 → a wait of ≤150 polls), so one long
#                                worker turn cannot hold the tick lock past a
#                                lease. An expired wait is not a failed
#                                delivery — both phases read the transcript.
#   BOARD_SUPPRESS_DIR           (exported to the dispatchers) suppression
#                                records; they read, this tick writes
#   IMPLEMENT_MODEL LOCAL_REPO   model pin / repo for a successor fresh spawn
#   BOARD_API_URL BOARD_CREDENTIALS_FILE   resolved by _binding.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_binding.sh
. "$SCRIPT_DIR/_binding.sh"
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
# The ONLY place a run token legitimately appears in this script is the
# explicit env prefix on the relay's resume call, read from that run's meta.
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
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"; rmdir "$LOCK" 2>/dev/null || true' EXIT
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
_registry_metas() {
  local rc=0
  T_DHOME="$DAEMON_HOME" python3 - <<'PY' || rc=$?
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
  # Every column gets its own name, including the ones this phase ignores.
  # Not because repeated `_` placeholders misbehave — they are fine in bash
  # 3.2 — but because named columns are what makes the row layout auditable
  # against the 0x1f contract above, which is where the real field-shift bug
  # lived (tab as IFS whitespace collapsed the empty bearer column and the
  # fence came back as the lane).
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
  _scan_ok || die "registry scan failed — renew phase saw no metas it can trust"
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

# uuid, bearer, run_id, fence (0x1f-separated) for every meta bound to ticket
# $1 — CANDIDATES, not one answer. Two metas can name the same ticket for a
# window: a reclaimed predecessor whose ticket-strip has not landed yet, beside
# the successor that actually holds the run. Taking the first glob match would
# hand the answer to the dead one. Server-confirmed binds are emitted first,
# and the caller takes the first LIVE candidate.
_metas_for_ticket() {
  _registry_metas | awk -F$'\x1f' -v t="$1" -v s=$'\x1f' '
    $4 != t { next }
    { row = $1 s $5 s $2 s $6
      if ($3 == "True" || $3 == "true") print row; else rest[++n] = row }
    END { for (i = 1; i <= n; i++) print rest[i] }'
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
  local c_uuid c_bearer c_run c_fence
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
      aid="$(cut -d$'\x1f' -f1 "$dir/$i.meta")"
      tid="$(cut -d$'\x1f' -f2 "$dir/$i.meta")"
      replies="$(cat "$dir/$i.replies")"
      i=$((i + 1))
      uuid=""; bearer=""; run=""; fence=""
      while IFS=$'\x1f' read -r c_uuid c_bearer c_run c_fence; do
        _alive "$c_uuid" || continue
        uuid="$c_uuid"; bearer="$c_bearer"; run="$c_run"; fence="$c_fence"
        break
      done < <(_metas_for_ticket "$tid")
      _scan_ok || die "registry scan failed — cannot resolve the session bound to #$tid"
      if [ -z "$uuid" ]; then
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
      # DAEMON_TIMEOUT is bounded here on purpose. daemon-resume's default is
      # 18000 (a wait of DAEMON_TIMEOUT/2 polls — hours), and this tick holds
      # the whole-tick lock throughout: one long turn would starve lease
      # renewal past the 15-minute lease and A1 would reclaim runs that are
      # very much alive. Bounding it is safe because daemon-resume advances
      # the meta's `current` to the new turn and injects this prompt BEFORE it
      # blocks: a timed-out resume exits nonzero, so nothing is acked this
      # tick, and the next tick's sentinel grep finds the marker in the new
      # transcript and acks WITHOUT re-delivering (the replay case the test
      # pins on u-3/u-3-cur). The delivery gate holds; only the ack is late.
      elif BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" \
        BOARD_API_URL="$BOARD_API_URL" \
        DAEMON_TIMEOUT="${BOARD_RELAY_RESUME_TIMEOUT:-300}" \
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
}

# ---- phase 3: resume-first -------------------------------------------------
# Suppression records sit beside the claim journal, one per stuck ticket:
#   {"ticket": N, "state": "<board state when it stuck>", "env_issue": N}
# THIS PHASE IS THEIR ONLY WRITER. Both dispatchers read the directory
# (BOARD_SUPPRESS_DIR) and release any claim that yields a suppressed ticket.
SUPPRESS_DIR="$DAEMON_HOME/board-suppress"
CLAIMS_DIR="$DAEMON_HOME/board-claims"

_suppressed() { [ -f "$SUPPRESS_DIR/$1.json" ]; }

# Lift the suppression on ticket $1 if either trigger fired. Both are checked
# every tick because either one alone is a trap: an operator who moves the
# ticket should not also have to close the env-issue, and closing the
# env-issue is the natural "I fixed the substrate" gesture. A ticket that has
# fallen off the listing entirely (terminal) reads as moved, which is right.
_check_lift() {
  T_TID="$1" T_DIR="$SUPPRESS_DIR" _api_py - <<'PY'
import json, os
import _board_api as A
path = os.path.join(os.environ["T_DIR"], os.environ["T_TID"] + ".json")
if not os.path.exists(path):
    raise SystemExit(0)
with open(path) as f:
    rec = json.load(f)
rows = {str(t["id"]): t["state"] for t in A.tickets(principal="automation")}
moved = rows.get(str(rec["ticket"])) != rec["state"]
closed = rows.get(str(rec["env_issue"])) in (None, "done", "wontfix")
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
_fold_answers() {  # <ticket> <dir>
  T_TID="$1" T_DIR="$2" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_TID"]
d = os.environ["T_DIR"]
mine = [a for a in A.unrelayed() if str(a.get("ticketId")) == tid]
with open(os.path.join(d, "ids"), "w") as f:
    f.write(",".join(str(a["answerEventId"]) for a in mine))
with open(os.path.join(d, "text"), "w") as f:
    f.write("\n\n".join(A.SENTINEL % a["answerEventId"] + "\n" +
                        "\n".join(a.get("replies") or []) for a in mine))
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

_successor_prompt() {  # <ticket> <run> <folded answer text ('' if none)>
  cat <<EOF
$(_successor_marker "$2") You are the successor run for ticket #$1 — your
predecessor was reclaimed, so the board handed its work to you on a fresh run.

Read your own ticket timeline FIRST (board-show.sh $1). The park and answer
history there is part of your assignment: answers delivered to the session you
are replacing live in it and nowhere else. Then continue under your original
protocol.${3:+

---- answers relayed with this resume (verbatim) ----
$3}
EOF
}

# One claim-journal entry, written whole. json.dump rather than printf: the
# run id must land as a JSON number (or null), and BOTH dispatchers parse
# every file in this shared directory — one they cannot read is reported and
# left forever. Lane `successor` is outside both dispatchers, lane sets on
# purpose: neither may replay or end a run it does not own.
_journal() {  # <path> <run-id ('' = null)> <spawn-completed 0|1> <ticket> <daemon>
  J_PATH="$1" J_RUN="$2" J_DONE="$3" J_TICKET="$4" J_DAEMON="$5" python3 - <<'PY'
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
    # must not exist world-readable even for the width of one write.
    tmp = path + ".tmp"
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
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
_resume_one() {
  local tid="$1" nonce dir exports ids text prompt transcript delivered=""
  local C_CLAIMED=0 C_RUN="" C_FENCE="" C_BEARER="" C_SESS=""
  nonce="$(uuidgen)"
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
out = A.claim_successor(os.environ["T_TID"], os.environ["T_NONCE"])
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
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
loc = out.get("sessionLocator") or {}
q("C_SESS", loc.get("sessionId") or "")
with open(os.environ["T_BODY"], "w") as f:
    f.write(out.get("body") or "")
PY
)" || {
    # The journal STAYS: a claim that died on the wire may still have landed.
    echo "resume: #$tid — successor claim failed; journal $nonce kept" >&2
    return 1
  }
  eval "$exports"
  if [ "$C_CLAIMED" != 1 ]; then
    rm -f "$CLAIMS_DIR/$nonce.json"
    echo "resume: #$tid — the board granted no successor"
    return 0
  fi
  _journal "$CLAIMS_DIR/$nonce.json" "$C_RUN" 0 "$tid" ''

  : > "$dir/ids"; : > "$dir/text"
  _fold_answers "$tid" "$dir" \
    || echo "resume: #$tid — unrelayed feed unreadable; answers stay on it" >&2
  ids="$(cat "$dir/ids")"
  text="$(cat "$dir/text")"
  prompt="$(_successor_prompt "$tid" "$C_RUN" "$text")"

  [ -z "$C_SESS" ] || _persist_successor "$C_SESS" "$C_RUN" "$C_FENCE" "$C_BEARER" "$tid" \
    || echo "resume: #$tid — registry persist FAILED; delivering anyway" >&2

  # daemon-resume forks a fresh process from OUR env, so the successor
  # credentials ride the invocation or the worker can write nothing. The wait
  # is bounded for the same reason phase 2 bounds it: this tick holds the
  # whole-tick lock throughout, and daemon-resume defaults to hours.
  if [ -n "$C_SESS" ] && BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN" \
       BOARD_RUN_FENCE="$C_FENCE" BOARD_API_URL="$BOARD_API_URL" \
       DAEMON_TIMEOUT="${BOARD_RELAY_RESUME_TIMEOUT:-300}" \
       "$DAEMON_SCRIPTS/daemon-resume.sh" "$C_SESS" "$prompt"; then
    delivered="$C_SESS"
    echo "resume: #$tid run $C_RUN → resumed session $C_SESS"
  elif [ -n "$C_SESS" ] && transcript="$(_transcript_for_uuid "$C_SESS")" \
       && [ -n "$transcript" ] \
       && grep -qF "$(_successor_marker "$C_RUN")" "$transcript" 2>/dev/null; then
    # A BOUNDED WAIT IS NOT A FAILED DELIVERY. daemon-resume forks the turn,
    # advances the meta and injects this prompt BEFORE it blocks, then exits 1
    # when its watcher expires — and a successor turn routinely runs longer
    # than the bound this tick needs in order not to starve lease renewal, so
    # this is the COMMON case, not the corner. Fresh-spawning on it would put
    # a second worker on a run the first one is actively holding. The
    # transcript is the marker, exactly as in phase 2.
    delivered="$C_SESS"
    echo "resume: #$tid run $C_RUN → the resume wait expired but the delivery landed in $C_SESS"
  else
    # FRESH SPAWN ON THE SAME SUCCESSOR BEARER. A successor is a fresh run by
    # contract; resuming the predecessor session is an optimization, not the
    # substance. The assignment body rides along — by contract it is the only
    # route a run has to its own ticket text, and this session has never seen
    # it — on top of the timeline direction the prompt already carries.
    local name="$tid-successor" spawn_out uuid
    prompt="$prompt

---- assignment (from the successor claim) ----
$(cat "$dir/body.md")"
    # DAEMON_CLAUDE_SETTINGS/EFFORT cleared for the dispatchers, reason: this
    # tick can itself run inside a gateway-routed daemon, and daemon-spawn
    # persists what it inherits into the meta, so every later resume would
    # ride the gateway while the log said claude.
    if spawn_out="$(BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN" \
         BOARD_RUN_FENCE="$C_FENCE" BOARD_API_URL="$BOARD_API_URL" \
         DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT='' \
         "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" \
         "${LOCAL_REPO:-$BOARD_ROOT}" "$name" "${IMPLEMENT_MODEL:-opus}")"; then
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
  _journal "$CLAIMS_DIR/$nonce.json" "$C_RUN" 1 "$tid" "$delivered"
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
  # The bearer goes THROUGH board-bind so it lands at rest in the delivered
  # session's own meta — a freshly spawned one has none, and a worker whose
  # bearer was never stored can never be spoken for again.
  BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN" BOARD_RUN_FENCE="$C_FENCE" \
    "$SCRIPT_DIR/board-bind.sh" "$delivered" "$tid" \
    || echo "resume: #$tid — bind FAILED; phase 1 repairs it next tick" >&2
  _attempts "$tid" reset
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
  echo "resume: #$1 — recovery cycle $n of 3 failed"
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
tid = os.environ["T_TID"]
print(next((t["state"] for t in A.tickets(principal="automation")
            if str(t["id"]) == tid), ""))
PY
)" || { echo "resume: #$tid — board state unreadable; escalation deferred" >&2; return 1; }
  eid="$(T_TID="$tid" _api_py - <<'PY'
import os
import _board_api as A
tid = os.environ["T_TID"]
out = A.register({"title": "stuck resume: ticket #%s cannot be revived" % tid,
                  "category": "env-issue",
                  "body": "Three resume and fresh-spawn cycles failed for ticket "
                          "#%s. The sweep has SUPPRESSED that ticket: phase 3 skips "
                          "it and phase 4 releases any claim that yields it. "
                          "Investigate the session/daemon substrate, then either "
                          "move ticket #%s (any transition) or close this env-issue "
                          "— either one lifts the suppression on the next tick."
                          % (tid, tid)},
                 principal="automation")
print(out["id"])
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
  # Lift first: a suppression that no longer holds must not cost this tick a
  # resume it could have made.
  for f in "$SUPPRESS_DIR"/*.json; do
    [ -e "$f" ] || continue
    _check_lift "$(basename "$f" .json)" \
      || echo "resume: suppression check for $(basename "$f" .json) failed" >&2
  done
  dir="$(mktemp -d "$SCRATCH/feed.XXXXXX")"
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
  impl="$SCRIPT_DIR/../../implementing/scripts/implement-dispatch.sh"
  revw="$SCRIPT_DIR/../../reviewing-prs/scripts/review-dispatch.sh"
  # DAEMON_HOME/DAEMON_SCRIPTS are resolved here but NOT exported (see above),
  # so they are passed explicitly: without them a non-default registry — a
  # test seam, a second fleet on one host — would silently split in two, this
  # tick renewing one registry while the dispatchers filled another.
  # BOARD_CREDENTIALS_FILE is deliberately NOT passed: it is repo-scoped, and
  # each dispatcher re-derives it from the repo it resolves for itself.
  local env_common=(BOARD_SUPPRESS_DIR="$SUPPRESS_DIR" DAEMON_HOME="$DAEMON_HOME"
                    DAEMON_SCRIPTS="$DAEMON_SCRIPTS" LOCAL_REPO="${LOCAL_REPO:-$BOARD_ROOT}")
  env "${env_common[@]}" "$impl" --sweep \
    || echo "dispatch: the implement lanes failed this tick" >&2
  env "${env_common[@]}" "$revw" --sweep \
    || echo "dispatch: the review lane failed this tick" >&2
}

case "${1:-all}" in
  renew) phase_renew ;;
  relay) phase_relay ;;
  resume) phase_resume ;;
  dispatch) phase_dispatch ;;
  all) phase_renew || true; phase_relay || true; phase_resume || true; phase_dispatch || true ;;
  *) die "usage: _sweep_api.sh [renew|relay|resume|dispatch|all]" ;;
esac
