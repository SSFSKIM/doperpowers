#!/usr/bin/env bash
# implement-dispatch.sh — mechanical implement/spike dispatcher (the dispatch
# ritual of doperpowers:issue-tracker, automated; no model, no judgment).
#
# Usage:
#   implement-dispatch.sh <issue-number>   triggered mode (issue event / manual)
#   implement-dispatch.sh --sweep          catch-up: every ELIGIBLE ticket in
#                                          dispatch order, up to the cap
#
# Per ticket: re-verify eligibility from a fresh board snapshot (a trigger is
# a hint, never inherited trust), dedupe against the registry, render the
# worker bootstrap with every dispatcher-owned binding, spawn the daemon
# --no-wait in its own worktree, and bind it to the ticket. The worker's
# first board write is its own gate verdict — this script writes nothing to
# the board beyond the binding.
#
# Dedupe and the concurrency cap read the REGISTRY first (bound metas in
# status working/blocked/error), the board second: a just-spawned worker's
# meta exists before its gate verdict moves the ticket off its lane's
# dispatchable state (ready-for-architect / ready-for-implementer), so
# board-state-only counting would double-dispatch inside that window.
# An IDLE bound session never blocks a dispatch — re-dispatch is fresh
# context by doctrine, and board-bind strips the stale owner.
#
# Env:
#   LOCAL_REPO      canonical local clone of the target repo (default: $PWD)
#   BOARD_REPO      owner/name (default: resolved from LOCAL_REPO via gh)
#   IMPLEMENT_MAX_CONCURRENT  implement/spike worker slot cap (default 5);
#                   review-pr-*/land-pr-* workers never count against it
#   ARCHITECT_MAX_CONCURRENT  architect-lane slot cap (default 1) — the
#                   Fable-spend lever; counted over ready-for-architect/
#                   in-design bound metas, separate from the implement cap
#   ARCHITECT_MODEL model pin for the architect route (default fable);
#                   the architect dispatch IGNORES engine:* labels and
#                   WORKER_ENGINE — plan authorship is never label-routed
#   WORKER_ENGINE   model route codex|claude (default claude); an engine:*
#                   ticket label wins over the env, so `engine:codex` opts a
#                   single ticket back onto the gateway
#   CLODEX_SETTINGS gateway settings file for the codex route
#                   (default ~/.claude/clodex-settings.json)
#   CLODEX_EFFORT   reasoning effort for the codex route (default xhigh)
#   IMPLEMENT_MODEL model pin for the implement/spike routes (claude route
#                   default opus, codex route default fable) — the worker-tier
#                   half of the lane split's model economics, symmetric with
#                   ARCHITECT_MODEL; pinned rather than inherited so the
#                   operator's own session model never silently re-fuses the
#                   two lanes onto one price
#   BOARD_SCRIPTS / DAEMON_SCRIPTS / DAEMON_HOME / IMPLEMENT_BOOTSTRAP_TEMPLATE
#                   overrides (tests)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
export DAEMON_HOME
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)}"
BOOTSTRAP_TEMPLATE="${IMPLEMENT_BOOTSTRAP_TEMPLATE:-$SKILL_DIR/references/worker-bootstrap.md}"
SPIKE_PROTOCOL="$SKILL_DIR/references/spike-worker-protocol.md"
IMPLEMENT_PROTOCOL="$SKILL_DIR/SKILL.md"
ARCHITECT_PROTOCOL="$SKILL_DIR/../architecting/SKILL.md"
ARCH_CAP="${ARCHITECT_MAX_CONCURRENT:-1}"
DECOMPOSE_DOC="$SKILL_DIR/references/implement-decompose.md"
CAP="${IMPLEMENT_MAX_CONCURRENT:-5}"
# Surfaces claimed by dispatches earlier in this process (one sweep = one
# process, so a plain variable is the in-tick claim set — see the surface
# guard in dispatch_one). SURFACE_OVERRIDE=1 bypasses that guard, loudly.
DISPATCHED_SURFACES=""

die() { echo "error: $*" >&2; exit 1; }

git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
# Bare board-script calls anchor _lib.sh's BOARD_ROOT on the CURRENT directory
# and die at source time when it is not a checkout. Our own git calls use
# `git -C`, so cwd would otherwise never be corrected. Every path above is
# already absolute, so this is safe to do here. It is also what makes the
# binding resolution below read the TARGET repo's board.json rather than
# whatever checkout the operator happened to invoke us from.
cd "$LOCAL_REPO" || die "cannot cd to LOCAL_REPO: $LOCAL_REPO"
[ -f "$BOOTSTRAP_TEMPLATE" ] || die "worker bootstrap missing: $BOOTSTRAP_TEMPLATE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

# THE BINDING IS RESOLVED BEFORE THE gh PROBE. An api-bound repo never invokes
# gh at all, so requiring the CLI before knowing the binding would make the
# whole API path unreachable on a machine that has no gh. Everything above is
# mode-independent; the gh-mode half starts below the api branch.
# shellcheck source=../../issue-tracker/scripts/_binding.sh
. "$BOARD_SCRIPTS/_binding.sh"

# The uuid daemon-spawn --no-wait prints, from its banner line:
#   daemon spawned (no-wait): <name>  [<short> / <uuid>]  status=working
# Both dispatch paths hand that uuid to board-bind, so both parse it here.
extract_spawn_uuid() { sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1; }

# Render the worker bootstrap from the P_* variables in scope (P_FOO fills
# {{FOO}}); an unrendered placeholder is a hard error, never a prompt shipped
# with a hole in it. The template carries one api-only region: under the API
# binding the claim DELIVERS the assignment as a file, which gh mode has no
# equivalent for, so that block is dropped there rather than rendered with a
# value nothing could satisfy.
_render_bootstrap() {
  P_BINDING="$BOARD_BINDING" python3 - "$BOOTSTRAP_TEMPLATE" <<'PY'
import os, re, sys
t = open(sys.argv[1]).read()
keep = os.environ.get("P_BINDING") == "api"
t = re.sub(r"(?s)<!-- api-only[^>]*-->\n(.*?)<!-- /api-only -->\n",
           lambda m: m.group(1) if keep else "", t)
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
out = re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), m.group(0)), t)
left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", out)))
if left:
    sys.stderr.write("unrendered placeholder(s): %s\n" % " ".join(left))
    sys.exit(1)
print(out)
PY
}

# ---- API binding: claim-based dispatch -----------------------------------------
# The SERVER owns pick order, eligibility and the lease; this side owns local
# concurrency, the crash-recoverable claim journal, and the worker handover.
# There is no board snapshot here and no gh call anywhere below.
#
# The journal and its reconciliation are SHARED with review-dispatch (they were
# verbatim copies): _claim_journal.sh owns both, and this side supplies the
# lanes, the per-lane cap and the journal-drop.
CLAIM_LANES=architect,implementer,spike
_claim_lane_cap() { [ "$1" != architect ] && echo "$CAP" || echo "$ARCH_CAP"; }
_claim_drop_journal() {  # <nonce>
  rm -f "$DAEMON_HOME/board-claims/$1.json" "$DAEMON_HOME/board-claims/$1.body.md"
}
_claim_retire_worker() { "$DAEMON_SCRIPTS/daemon-retire.sh" "$1" >/dev/null 2>&1 || true; }
# shellcheck source=../../issue-tracker/scripts/_claim_journal.sh
. "$BOARD_SCRIPTS/_claim_journal.sh"

# The sweep's tick deadline, when it set one. A single budget check ahead of
# the whole dispatch phase admitted every loop below in full — and, on the
# review side, a barrier wait per candidate — inside the sweep's global lock,
# so a tick with one second left could spend minutes more. Checked before each
# FRESH claim; a replay from reconciliation is recovery, not new work, and is
# never gated. Absent or unparseable = no gate: a direct --sweep and the
# by-name `dispatch` phase are their own tick with their own clock.
_tick_deadline_left() {
  case "${BOARD_TICK_DEADLINE:-}" in ''|*[!0-9]*) return 0 ;; esac
  [ "$(date +%s)" -lt "$BOARD_TICK_DEADLINE" ]
}

# Open workers in a lane-set, counted off the registry: the local cap. A
# just-claimed worker's meta exists long before the board could show its first
# write, which is the same window the gh path's registry-first rule closes.
_api_registry_count() {  # <lane[,lane...]>
  T_DHOME="$DAEMON_HOME" T_LANES="$1" python3 - <<'PY'
import glob, json, os
lanes = set(os.environ["T_LANES"].split(","))
n = 0
for p in glob.glob(os.path.join(os.environ["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    # AN OPEN RUN is what a slot is: `lane` alone counted a session whose run
    # the server has since ended (the sweep strips run_id from such a meta and
    # deliberately keeps the lane, which is what a successor inherits), so a
    # normally finished worker held a dispatch slot forever.
    if (m.get("run_id") and m.get("lane") in lanes
            and m.get("status") in ("working", "blocked", "idle")):
        n += 1
print(n)
PY
}

# The sweep's resume phase suppresses a ticket it has escalated to an env-issue
# (it writes these files; we only read them). A claim is the only way to learn
# WHICH ticket the server picked, so suppression can only be honored after the
# fact — by handing the run straight back.
_api_suppressed() { [ -f "${BOARD_SUPPRESS_DIR:-$DAEMON_HOME/board-suppress}/$1.json" ]; }

_api_end_run() {  # <run-id> <reason> — best-effort release of a claimed run
  T_RUN="$1" T_REASON="$2" _api_py - <<'PY' || true
import os
import _board_api as A
try:
    A.end_run(os.environ["T_RUN"], os.environ["T_REASON"])
except A.RunEnded:
    pass
PY
}

# Claim one ticket on <lane> under <nonce> and hand it to a fresh worker.
#   rc 0  claimed and handed off
#   rc 1  nothing dispatched and NOTHING IS OUTSTANDING — the lane was empty,
#         the claim was refused, the ticket is suppressed, or the handover
#         failed and its run was released. Another lane may be tried.
#   rc 2  the claim may have LANDED and its journal is kept for replay. No
#         further claim may be made this tick: reconciliation owns the replay,
#         and a second lane claimed now would run beside the replayed one,
#         over the combined cap.
_claim_one_with_nonce() {  # <lane> <nonce> <lane-cap>
  local lane="$1" nonce="$2" cap="$3" claims_dir="$DAEMON_HOME/board-claims"
  local body_file="$claims_dir/$nonce.body.md" exports
  mkdir -p "$claims_dir"
  # The nonce is journalled BEFORE the POST. A crash between the two leaves a
  # record reconciliation can replay, and the server answers a repeated nonce
  # with the same claim rather than a second one.
  _journal_write "$claims_dir/$nonce.json" "$lane" '' 0
  # One process for the whole exchange (the _ticket_exports idiom above):
  # claim, write the assignment body, hand back shell-quoted facts. The run
  # bearer crosses exactly one boundary.
  local C_CLAIMED=0 C_RUN_ID="" C_TICKET="" C_FENCE="" C_BEARER="" C_PARENT_PIN=""
  exports="$(T_LANE="$lane" T_NONCE="$nonce" T_CAP="$cap" T_BODY="$body_file" _api_py - <<'PY'
import os, shlex
import _board_api as A
out = A.claim(os.environ["T_LANE"], os.environ["T_NONCE"],
              lane_cap=int(os.environ["T_CAP"]))
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
# An empty lane answers {"claimed": false}; a grant answers with the run. Any
# other falsy value for that key is read as "no claim" — when bytes from a
# foreign process are ambiguous, the safe direction is not to spawn.
# (Apostrophes are avoided in this heredoc on purpose: bash 3.2 rescans a
# heredoc body nested in $( ) for quoting, and a lone one is a parse error.)
if not out.get("claimed", True):
    q("C_CLAIMED", 0)
    raise SystemExit(0)
fields = (("C_RUN_ID", "runId"), ("C_TICKET", "ticketId"),
          ("C_FENCE", "fence"), ("C_BEARER", "bearer"))
missing = [f for _, f in fields if f not in out]
if missing:
    # Never echo the payload back: it carries the run bearer.
    A.die("claim answered without %s — the run cannot be handed to a worker"
          % ", ".join(missing))
q("C_CLAIMED", 1)
for var, field in fields:
    q(var, out[field])
# The parent-contract window this claim was cut against: A1 answers
# `{"parent_id": N, "parent_event_cursor": C}` (or null) and stores it on the
# run. It is the run-specific cursor the recomposing Architect needs, and no
# read a worker may make hands it over — so it travels with the dispatch or
# not at all. Flattened to one line; there is nothing to parse downstream.
pin = out.get("parentPin") or {}
q("C_PARENT_PIN",
  "#%s @ event %s" % (pin.get("parent_id"), pin.get("parent_event_cursor"))
  if pin.get("parent_id") is not None else "")
with open(os.environ["T_BODY"], "w") as f:
    f.write(out.get("body") or "")
PY
)" || {
    # The journal STAYS: a claim that died on the wire may still have landed,
    # and the replay is the only thing that can recover it. A permanently
    # refused claim retries once per tick, loudly, which is the cheaper side
    # of this trade than silently dropping a granted run's only record.
    echo "claim on lane $lane failed — journal $nonce kept for replay" >&2
    return 2
  }
  eval "$exports"
  if [ "$C_CLAIMED" != 1 ]; then
    rm -f "$claims_dir/$nonce.json" "$body_file"
    return 1
  fi
  if _api_suppressed "$C_TICKET"; then
    # This BLOCKS the lane for the tick — head-of-line, not a skip. The server
    # picks; we can only refuse what it handed us, so the suppressed ticket is
    # still the head of that lane on the next claim and every ticket behind it
    # waits. Server-side suppression (a claim that never offers the ticket) is
    # the real fix — recorded on arkho#7.
    echo "#$C_TICKET is suppressed — releasing run $C_RUN_ID; lane $lane stands down this tick"
    _api_end_run "$C_RUN_ID" abandoned
    rm -f "$claims_dir/$nonce.json" "$body_file"
    return 1
  fi

  local role protocol_file decompose model name prompt spawn_out uuid
  case "$lane" in
    architect)  role=ARCHITECT; protocol_file="$ARCHITECT_PROTOCOL"; decompose="$DECOMPOSE_DOC"
                model="${ARCHITECT_MODEL:-fable}" ;;
    spike)      role=SPIKE;     protocol_file="$SPIKE_PROTOCOL";     decompose="(none — spike lane)"
                model="${IMPLEMENT_MODEL:-opus}" ;;
    *)          role=IMPLEMENT; protocol_file="$IMPLEMENT_PROTOCOL"; decompose="$DECOMPOSE_DOC"
                model="${IMPLEMENT_MODEL:-opus}" ;;
  esac
  name="$C_TICKET-api-$lane"
  # Ticket and daemon name are journalled BEFORE the spawn, not after it. The
  # run id reaches a registry meta only through board-bind, which runs at the
  # END of the handover — so a crash anywhere in the spawn (the uuid poll is
  # seconds wide, and the session is already detached and surviving) leaves a
  # journal with a run id that no meta knows, indistinguishable from a run that
  # never spawned at all. The daemon name is the only evidence of that session
  # that exists before the bind, and reconciliation needs it to tell "never
  # spawned" from "spawned, live, unbound".
  _journal_write "$claims_dir/$nonce.json" "$lane" "$C_RUN_ID" 0 "$C_TICKET" "$name"
  # ENGINE_NAME is claude here and the engine label plays no part: a claim
  # response carries the assignment, not the ticket's labels, so there is
  # nothing to route on. ENV_TRACKER_ISSUE is "none" for the same reason —
  # the API board has no env-tracker label, and an env-issue ticket is
  # registered by the sweep, not pointed at from here.
  prompt="$(P_ROLE="$role" P_ISSUE_NUMBER="$C_TICKET" \
    P_ISSUE_URL="$BOARD_API_URL/tickets/$C_TICKET" \
    P_REPO="$(basename "$BOARD_ROOT")" P_BOARD_SCRIPTS="$BOARD_SCRIPTS" \
    P_ENV_TRACKER_ISSUE=none P_ENGINE_NAME=claude \
    P_PROTOCOL_FILE="$protocol_file" P_DECOMPOSE_DOC="$decompose" \
    P_TICKET_BODY_FILE="$body_file" P_PARENT_PIN="${C_PARENT_PIN:-none (no parent)}" \
    _render_bootstrap)" \
    || { echo "#$C_TICKET: prompt render failed — releasing run $C_RUN_ID" >&2
         _api_end_run "$C_RUN_ID" abandoned
         rm -f "$claims_dir/$nonce.json" "$body_file"; return 1; }

  # DAEMON_CLAUDE_SETTINGS/EFFORT cleared for the same reason as the gh path's
  # claude route: this dispatcher can itself run inside a gateway-routed
  # daemon, and daemon-spawn persists what it inherits into the registry meta,
  # so every later resume would ride the gateway while the log said claude.
  spawn_out="$(BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN_ID" \
    BOARD_RUN_FENCE="$C_FENCE" BOARD_API_URL="$BOARD_API_URL" \
    DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT='' \
    "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
    "$model")" \
    || { echo "#$C_TICKET: worker spawn failed — releasing run $C_RUN_ID" >&2
         _api_end_run "$C_RUN_ID" abandoned
         rm -f "$claims_dir/$nonce.json" "$body_file"; return 1; }
  printf '%s\n' "$spawn_out"
  uuid="$(printf '%s\n' "$spawn_out" | extract_spawn_uuid)"
  [ -n "$uuid" ] || { echo "#$C_TICKET: spawned worker UUID was not parseable — releasing run $C_RUN_ID (a session may be orphaned)" >&2
                      _api_end_run "$C_RUN_ID" abandoned
                      rm -f "$claims_dir/$nonce.json" "$body_file"; return 1; }
  # The bearer goes to board-bind so it lands in the meta at 0600: the sweep's
  # renew/relay/resume phases read it back out of there, and a worker whose
  # bearer was never stored can never be spoken for again.
  BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN_ID" BOARD_RUN_FENCE="$C_FENCE" \
    "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$C_TICKET" \
    || { echo "#$C_TICKET: bind failed — retiring the worker and releasing run $C_RUN_ID" >&2
         "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
         _api_end_run "$C_RUN_ID" abandoned
         rm -f "$claims_dir/$nonce.json" "$body_file"; return 1; }
  # THE HANDOFF IS DONE ONLY NOW: the journal may no longer be replayed, only
  # observed. Marked before the bind, a crash in that window left a journal
  # saying "handed off" over a meta holding no run credential and no locator —
  # reconciliation skipped it (its whole point is the unbound-but-live case),
  # nothing renewed the lease, and after the server reclaimed it the still
  # running worker overlapped its replacement.
  _journal_write "$claims_dir/$nonce.json" "$lane" "$C_RUN_ID" 1 "$C_TICKET" "$name"

  # Lane, role, nonce and the parent pin into the registry meta: the lane is
  # what the cap above counts, the role is what a lane-aware resume reads back,
  # the nonce is the link from a live worker to the journal entry that made it,
  # and the pin is the parent-contract window the claim handed this run.
  T_UUID="$uuid" T_LANE="$lane" T_ROLE="$role" T_NONCE="$nonce" \
  T_PARENT_PIN="$C_PARENT_PIN" T_DHOME="$DAEMON_HOME" \
  python3 - <<'PY' || echo "#$C_TICKET: lane meta write failed (non-fatal)" >&2
import fcntl, json, os
home = os.environ["T_DHOME"]
path = os.path.join(home, os.environ["T_UUID"] + ".json")
lock = open(os.path.join(home, ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    with open(path) as f:
        m = json.load(f)
    m["lane"] = os.environ["T_LANE"]
    m["role"] = os.environ["T_ROLE"]
    m["nonce"] = os.environ["T_NONCE"]
    if os.environ.get("T_PARENT_PIN"):
        m["parent_pin"] = os.environ["T_PARENT_PIN"]
    tmp = path + ".tmp"
    # The meta already holds the run bearer (board-bind wrote it): recreate it
    # at the mode it has, never at the umask's.
    mode = os.stat(path).st_mode & 0o777
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), "w") as f:
        json.dump(m, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
  echo "claimed #$C_TICKET run=$C_RUN_ID lane=$lane → $uuid"
}

# A FRESH claim on <lane> — the only claims the tick deadline gates, and the
# only ones that mint a nonce. Both refusals here are rc 2: nothing was
# claimed, but neither is a reason to try the next lane instead.
_claim_one() {  # <lane> <lane-cap>
  local nonce
  _tick_deadline_left \
    || { echo "dispatch: the sweep tick deadline has passed — lane $1 takes no fresh claim this tick"; return 2; }
  nonce="$(_claim_nonce)" || return 2
  _claim_one_with_nonce "$1" "$nonce" "$2"
}

dispatch_api() {
  local rc
  mkdir -p "$DAEMON_HOME/board-claims"
  _reconcile_claims
  # Local cap first (the registry), the server's laneCap as the belt: if a
  # lane stamp is ever lost the count cannot rise, and laneCap is then the
  # only thing that ends the loop.
  while [ "$(_api_registry_count architect)" -lt "$ARCH_CAP" ]; do
    _claim_one architect "$ARCH_CAP" || break
  done
  while [ "$(_api_registry_count implementer,spike)" -lt "$CAP" ]; do
    rc=0; _claim_one implementer "$CAP" || rc=$?
    case "$rc" in
      0) : ;;
      # ONLY A CLEAN REFUSAL FALLS THROUGH TO SPIKE. rc 2 says the implementer
      # claim may have landed and is journalled for replay — claiming a spike
      # now would put its worker beside the replayed implementer, over the
      # combined cap this loop exists to hold.
      1) _claim_one spike "$CAP" || break ;;
      *) break ;;
    esac
  done
}

if [ "$BOARD_BINDING" = api ]; then
  # DISPATCH IS AUTOMATION, FULL STOP — the doctrine block at the head of
  # _sweep_api.sh applies verbatim here. _board_api.token() hands back an
  # ambient BOARD_RUN_TOKEN for whatever principal is asked, so a --sweep run
  # straight out of a worker shell would claim, and end runs, as that worker.
  # The claim path's explicit `BOARD_RUN_TOKEN=…` prefixes set it per command,
  # after this, and are unaffected. This is the automation route only: no
  # human-route verb is touched.
  unset BOARD_RUN_TOKEN
  case "${1:-}" in
    --sweep) dispatch_api; exit 0 ;;
    ''|--*)  die "usage: implement-dispatch.sh <issue-number> | --sweep" ;;
    *) die "API-mode dispatch is claim-based — the server owns pick order, and the contract has no claim-by-ticket route; use --sweep. Targeted claim is a flow-back candidate recorded on arkho#7 (spec Revision Notes v1.2)." ;;
  esac
fi

# ---- gh binding ----------------------------------------------------------------
command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"
export BOARD_REPO

# Board facts for ticket <1>, shell-quoted (state, eligibility, title, url,
# category, engine label). _board.py is the single eligibility authority —
# the same predicate board-list.sh tags ELIGIBLE.
# Known cost: this and _slots_used each take a fresh full-board snapshot
# (one GraphQL call), so a dispatching tick runs roughly three snapshots
# per ticket. Harmless at a 5-minute cadence on a ~300-issue board; add
# snapshot caching before the board grows ~10x.
_ticket_exports() {
  T_ID="$1" BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import os, shlex, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
tid = os.environ["T_ID"]
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
if tid not in tickets:
    q("T_STATE", "missing"); q("T_ELIGIBLE", 0)
    raise SystemExit(0)
n = tickets[tid]
q("T_STATE", n["state"])
q("T_ELIGIBLE", 1 if B.eligible(tickets, tid) else 0)
q("T_TITLE", n["title"]); q("T_URL", n["url"]); q("T_CATEGORY", n["category"])
q("T_PARENT", n.get("parent") or "")
eng = "claude" if "engine:claude" in n["labels"] else ("codex" if "engine:codex" in n["labels"] else "")
q("T_ENGINE_LABEL", eng)
# Surface labels, gated on a loaded registry: without .doperpowers/
# surfaces.md on the default branch the whole surface feature is inert BY
# CONTRACT — a leftover label in a repo whose registry was removed must not
# queue work forever. The occupancy CHECK runs later, under the per-surface
# lock (dispatch_one) — computing it here would be a check outside the lock.
q("T_SURFACES", " ".join(n["surfaces"]) if n["surfaces"]
  and B.surfaces_registry() is not None else "")
import re
slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", n["title"].lower())).strip("-")[:32].rstrip("-")
q("T_SLUG", slug or "ticket")
PY
}

# Surface occupancy for ticket <1> across its surfaces (space-joined <2>),
# given the surfaces claimed earlier this tick (<3>). Fresh snapshot each
# call ON PURPOSE — it runs under the per-surface lock, and a check computed
# before the lock would be the TOCTOU the lock exists to close. A surface is
# OCCUPIED when another open non-epic non-spike ticket with the same label
# is in an in-flight board state (in-progress/in-review/in-design —
# in-design so a consolidation redesign holds patch work off the surface),
# OR has a live bound non-reviewer worker (registry-first: board state lags
# a fresh spawn by minutes), OR sits in the in-tick claim set (the belt for
# a crashed meta write). Prints "<surface>|<occupant>" or nothing.
_surface_occupant() {  # <ticket> <surfaces> <claimed>
  T_ID="$1" T_SURFS="$2" T_CLAIMED="$3" BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
tid = os.environ["T_ID"]
claimed = set((os.environ.get("T_CLAIMED") or "").split())
live = B.live_bound_tickets(include_reviewers=False)
epics = {t for t in tickets if any(
    tickets[c].get("parent") == t for c in tickets)}
for s in os.environ["T_SURFS"].split():
    for t, m in tickets.items():
        if t == tid or s not in m["surfaces"] or t in epics \
           or m["category"] == "spike" or m["state"] in B.TERMINAL:
            continue
        if m["state"] in ("in-progress", "in-review", "in-design") \
           or t in live:
            print("%s|#%s" % (s, t))
            raise SystemExit(0)
    if s in claimed:
        print("%s|an earlier dispatch this tick" % s)
        raise SystemExit(0)
PY
}

# Per-surface mkdir locks under $DAEMON_HOME/surface-locks/ — the
# cross-PROCESS half of serialization (the in-tick claim set only covers one
# sweep process; two triggered dispatches, or a triggered dispatch beside the
# sweep, would otherwise both pass the occupancy check inside the
# check-to-meta window). Same stale-steal policy as the review dispatch lock.
# Also taken by the sweep SURFACE pass around its relates body writes, which
# is what serializes those against this dispatcher's parent-pin stamp.
_surf_lock() {  # <surfaces...> — 0 = all acquired; 1 = contention (none held)
  local s got=""
  mkdir -p "$DAEMON_HOME/surface-locks"
  for s in $1; do
    if ! mkdir "$DAEMON_HOME/surface-locks/$s" 2>/dev/null; then
      if [ -n "$(find "$DAEMON_HOME/surface-locks/$s" -maxdepth 0 -mmin +"${SURFACE_LOCK_STALE:-30}" 2>/dev/null)" ]; then
        rmdir "$DAEMON_HOME/surface-locks/$s" 2>/dev/null || true
        mkdir "$DAEMON_HOME/surface-locks/$s" 2>/dev/null \
          || { _surf_unlock "$got"; return 1; }
      else
        _surf_unlock "$got"; return 1
      fi
    fi
    got="$got $s"
  done
  return 0
}
_surf_unlock() {  # <surfaces...>
  local s
  for s in $1; do rmdir "$DAEMON_HOME/surface-locks/$s" 2>/dev/null || true; done
}

# Newest registry meta bound to ticket <1> → "uuid|status|name" (empty if none).
_bound_meta() {
  T_ID="$1" python3 - <<'PY'
import glob, json, os
best = None
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if str(m.get("ticket", "")).lstrip("#") == os.environ["T_ID"]:
        key = str(m.get("updated") or m.get("created") or "")
        if best is None or key > best[0]:
            best = (key, m)
if best:
    m = best[1]
    print("%s|%s|%s" % (m.get("uuid", ""), m.get("status", ""), m.get("name", "")))
PY
}

# Occupied slots for one lane: bound metas in an active status whose
# ticket is still in that lane's active states. The architect lane's
# states are (ready-for-architect, in-design); the implement lane's are
# (ready-for-implementer, in-progress). A stale `working` meta on any
# other state never eats a slot — that worker's scope ended when the
# ticket moved on (binding release IS this accounting).
_slots_used() {  # <architect|implement>
  LANE="$1" BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
LANE = os.environ["LANE"]
lane = {"architect": ("ready-for-architect", "in-design"),
        "implement": ("ready-for-implementer", "in-progress")}[LANE]
ROLES = {"architect": ("ARCHITECT",), "implement": ("IMPLEMENT", "SPIKE")}[LANE]
used = 0
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    # Reviewer species are accounted in their OWN registry and never against a
    # lane's slots. review-epic- matters here for the same reason the other two
    # do, and for a window G1's stale-side cleanup cannot cover: a LIVE scale
    # reviewer that has already moved its epic to ready-for-architect is still
    # posting its trail, and while it does, its meta sat on the single
    # architect slot and blocked every unrelated Architect dispatch. (This is
    # only the lane-wide count — _bound_meta still refuses to dispatch THAT
    # epic while a worker owns it, correctly.)
    if name.startswith("review-pr-") or name.startswith("review-epic-") \
       or name.startswith("land-pr-"):
        continue
    tk = str(m.get("ticket") or "").lstrip("#")
    if not tk or m.get("status") not in ("working", "blocked", "error"):
        continue
    if tickets.get(tk, {}).get("state") not in lane:
        continue
    # ROLE **and** state. State alone charged a worker to whichever lane its
    # ticket had reached, so a live Implementer that handed off to the
    # architect queue sat on the single architect slot while it wrote its
    # closing trail — blocking every unrelated Architect until finalize or
    # the stall reaper caught up, up to 45 minutes later. Lane crossing IS
    # binding release (lane-split spec, transition 8); a handed-off worker
    # charges nothing to either lane and L1's stall reaper owns the rest of
    # its lifecycle. A meta with NO role predates this write (or its
    # non-fatal write failed): fall back to state alone rather than stop
    # counting a worker that is genuinely in-lane.
    role = str(m.get("role") or "")
    if role and role not in ROLES:
        continue
    used += 1
print(used)
PY
}

# ---- per-ticket dispatch -------------------------------------------------------
# Runs behind `||` in sweep mode (which suspends errexit through the call
# subtree), so every step is explicitly guarded and returns 1 on failure.
dispatch_one() {
  local n="$1" exports engine role protocol_file decompose prompt name spawn_out uuid meta status lane model surf_locked="" occ

  meta="$(_bound_meta "$n")"
  if [ -n "$meta" ]; then
    status="$(printf '%s' "$meta" | cut -d'|' -f2)"
    case "$status" in
      working|blocked|error)
        echo "skip #$n: bound worker ${meta%%|*} status=$status"
        return 0 ;;
    esac
  fi

  exports="$(T_CLAIMED="${DISPATCHED_SURFACES:-}" _ticket_exports "$n")" \
    || { echo "#$n: board snapshot failed" >&2; return 1; }
  eval "$exports"
  if [ "${T_ELIGIBLE:-0}" != "1" ]; then
    echo "skip #$n: not eligible (state=${T_STATE:-unknown})"
    return 0
  fi

  if [ "$T_STATE" = "ready-for-architect" ]; then
    # THE ARCHITECT QUEUE IS STATE-BASED, and the state OUTRANKS CATEGORY.
    # Every legal exit from ready-for-architect is an architect-lane exit; the
    # spike protocol's first board write (ready-for-architect → in-progress)
    # has no LEGAL edge from here at all. Routed on category, EVERY spike in
    # this queue hard-fails, the sweep re-dispatches into the same failure,
    # and the architect slot burns every tick. Category selects a protocol
    # only within the IMPLEMENT lane (a spike dispatches on the spike protocol
    # from ready-for-implementer).
    # An epic is the same rule, not an exception to it: it reaches this state
    # as a recomposition or reconciliation claim — the ONLY way an epic is
    # dispatchable at all (B.eligible's carve-out) — and that claim is the
    # Architect's work whatever the parent's own category says. A spike that
    # decomposed keeps its spike label and returns here the same way.
    lane="architect"; role="ARCHITECT"; protocol_file="$ARCHITECT_PROTOCOL"
    decompose="$DECOMPOSE_DOC"
  elif [ "$T_CATEGORY" = "spike" ]; then
    # category routes WITHIN the implement lane: a spike out of
    # ready-for-implementer dispatches on the spike protocol
    lane="implement"; role="SPIKE"; protocol_file="$SPIKE_PROTOCOL"
    decompose="(none — spike lane)"
  else
    lane="implement"; role="IMPLEMENT"; protocol_file="$IMPLEMENT_PROTOCOL"
    decompose="$DECOMPOSE_DOC"
  fi
  [ -f "$protocol_file" ] || { echo "#$n: protocol file missing: $protocol_file" >&2; return 1; }

  if [ "$lane" = "architect" ]; then
    if [ "$(_slots_used architect)" -ge "$ARCH_CAP" ]; then
      echo "architect cap reached ($ARCH_CAP): #$n stays queued for the next sweep"
      return 0
    fi
    # X4 exemption: plan authorship is never label-routed
    engine="claude"
  else
    if [ "$(_slots_used implement)" -ge "$CAP" ]; then
      echo "cap reached ($CAP): #$n stays queued for the next sweep"
      return 0
    fi
    engine="${T_ENGINE_LABEL:-}"
    [ -n "$engine" ] || engine="${WORKER_ENGINE:-claude}"
  fi

  # Surface serialization (spec: one in-flight implement worker per surface).
  # Lock FIRST, check UNDER the lock: the per-surface mkdir lock is what
  # makes the occupancy check atomic across processes (two triggered
  # dispatches, or a triggered dispatch racing the sweep). Held from here
  # through the spawn — the spawn writes the registry meta, after which the
  # registry arm of the check takes over. Only the IMPLEMENT role waits:
  # the architect lane is the resolver (a consolidation ticket must dispatch
  # ONTO an occupied surface; on lock contention it proceeds unlocked rather
  # than queue) and a spike is read-only exploration. A skip is normal
  # scheduling — return 0, next tick retries. SURFACE_OVERRIDE=1 is the
  # deliberate operator bypass; both entry points share this guard.
  if [ -n "${T_SURFACES:-}" ] && [ "$role" != "SPIKE" ]; then
    if _surf_lock "$T_SURFACES"; then
      surf_locked="$T_SURFACES"
      occ="$(_surface_occupant "$n" "$T_SURFACES" "${DISPATCHED_SURFACES:-}")"
      if [ -n "$occ" ] && [ "$role" = "IMPLEMENT" ]; then
        if [ "${SURFACE_OVERRIDE:-0}" = "1" ]; then
          echo "SURFACE_OVERRIDE=1: dispatching #$n onto occupied surface ${occ%%|*} (occupant ${occ#*|})"
        else
          echo "surface ${occ%%|*} occupied by ${occ#*|} — #$n queued"
          _surf_unlock "$surf_locked"
          return 0
        fi
      fi
    elif [ "$role" = "IMPLEMENT" ] && [ "${SURFACE_OVERRIDE:-0}" != "1" ]; then
      echo "surface lock contention ($T_SURFACES) — #$n queued"
      return 0
    else
      echo "surface lock contention ($T_SURFACES) — #$n proceeding UNLOCKED (role=$role SURFACE_OVERRIDE=${SURFACE_OVERRIDE:-0})"
    fi
  fi

  # E2 parent-pin: stamp the inherited-contract pin BEFORE the worker is
  # released. The parent's contract keeps moving between the cut and the
  # dispatch, so the pin has to say which REVISION OF THE CONTRACT this child
  # inherited — and the contract is the parent's ISSUE BODY. It was the repo
  # HEAD sha, which answers a different question entirely: a body edit does
  # not move HEAD and an unrelated commit does, so the pin changed when the
  # contract had not and held still when it had. The recomposing Architect's
  # lineage check (doperpowers:architecting, "compare its parent-pin against
  # the parent's current revision") could not be performed at all.
  # B.contract_hash: sha256/12 over the parent's body with its board:meta
  # block STRIPPED — immutable, comparable by re-hashing the body today, and
  # still `#<n> @ <hex>` so the M1/N1 lineage parsing (which reads the `#<n>`
  # head) is untouched. Stripping matters: recompose_epics clears pr:/branch:
  # every recomposition cycle, so a whole-body hash announced a changed
  # contract every cycle and trained the reader to ignore the signal.
  # The write is a full-body read-modify-write, so it must land while this
  # dispatcher is still the only writer. Stamped after the spawn it raced
  # the worker two ways: a fast worker could read its ticket before the pin
  # existed, and the RMW could overwrite the worker's OWN first board write
  # (its note, its pre-park meta). Everything the stamp needs is resolved
  # above; nothing in it wants the worker's name or uuid. Non-fatal like the
  # role write below — a missing pin costs the parent-impact reconcile its
  # lineage check on THIS child, nothing more.
  # The pin ACCUMULATES across reparents. A single-value overwrite erased the
  # previous parent from the record, and the IMPACT pass reads exactly this
  # field to decide whether a proposal may name that parent (M1): a child
  # reparented and redispatched while its old proposal still sat unmarked —
  # the parent was parked, or in the architect lane — lost the only evidence
  # that made the proposal admissible, and it was rejected forever. Entries
  # are separated by "; " (parse_meta splits a meta line on the FIRST colon
  # only, so the value carries separators safely), newest last. A redispatch
  # under the SAME parent replaces that parent entry with the fresh sha —
  # accumulation tracks lineage, not attempts. No expiry: a pin retires when
  # the board forgets the ticket.
  if [ -n "${T_PARENT:-}" ]; then
    T_N="$n" T_PARENT="$T_PARENT" \
    PYTHONPATH="$BOARD_SCRIPTS" python3 - <<'PY' \
      || echo "#$n: parent-pin meta write failed (non-fatal)" >&2
import os
import _board as B
env = os.environ
tickets = B.snapshot()
tid = B.resolve(env["T_N"], tickets)
node = tickets[tid]
parent = env["T_PARENT"]
pbody = (tickets.get(parent) or {}).get("body") or ""
pin = "#%s @ %s" % (parent, B.contract_hash(pbody))
recorded = B.parse_meta(node["body"]).get("parent-pin") or ""
mine = pin.split("@")[0].strip()
kept = [e.strip() for e in recorded.split(";")
        if e.strip() and e.split("@")[0].strip() != mine]
B.update_meta(tid, node,
              **{"parent-pin": "; ".join(kept + [pin])})
PY
  fi

  # The prompt carries bindings only — the worker reads its ticket (and the
  # repo's .doperpowers/repo-facts.md, if any) from gh / its own worktree.
  et="$(gh issue list -R "$BOARD_REPO" --label env-tracker --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"
  prompt="$(P_ROLE="$role" P_ISSUE_NUMBER="$n" P_ISSUE_URL="$T_URL" \
    P_REPO="$BOARD_REPO" P_BOARD_SCRIPTS="$BOARD_SCRIPTS" \
    P_ENV_TRACKER_ISSUE="${et:-none}" \
    P_ENGINE_NAME="$engine" P_PROTOCOL_FILE="$protocol_file" \
    P_DECOMPOSE_DOC="$decompose" \
    _render_bootstrap)" \
    || { echo "#$n: prompt render failed (unrendered placeholder or template error)" >&2; _surf_unlock "$surf_locked"; return 1; }
  [ -n "$prompt" ] || { echo "#$n: empty prompt — not dispatching" >&2; _surf_unlock "$surf_locked"; return 1; }

  name="$n-$T_SLUG"
  # ONE worker harness, two model routes (same shape as review-dispatch):
  # codex = the clodex gateway settings (GPT models via the local proxy),
  # claude = plain Claude models.
  if [ "$engine" = "codex" ]; then
    spawn_out="$(DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" \
      DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" \
      "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
      "${IMPLEMENT_MODEL:-fable}")" \
      || { echo "#$n: worker spawn failed" >&2; _surf_unlock "$surf_locked"; return 1; }
  else
    # Cleared, not merely unset by us: this dispatcher can itself run inside a
    # gateway-routed daemon whose environment exports these, and daemon-spawn.sh
    # would inherit them, apply the flags AND persist them into the registry
    # meta — so every later resume would keep riding the gateway while the log
    # said engine=claude.
    local model="${IMPLEMENT_MODEL:-opus}"
    [ "$lane" != "architect" ] || model="${ARCHITECT_MODEL:-fable}"
    spawn_out="$(DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT='' \
      "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
      "$model")" \
      || { echo "#$n: worker spawn failed" >&2; _surf_unlock "$surf_locked"; return 1; }
  fi
  printf '%s\n' "$spawn_out"
  uuid="$(printf '%s\n' "$spawn_out" | extract_spawn_uuid)"
  [ -n "$uuid" ] || { echo "#$n: spawned worker UUID was not parseable" >&2; _surf_unlock "$surf_locked"; return 1; }

  local try=1 bound=""
  while [ "$try" -le "${IMPLEMENT_BIND_ATTEMPTS:-3}" ]; do
    if "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$n"; then bound=1; break; fi
    [ "$try" -lt "${IMPLEMENT_BIND_ATTEMPTS:-3}" ] && sleep "${IMPLEMENT_BIND_DELAY:-2}"
    try=$((try + 1))
  done
  if [ -z "$bound" ]; then
    "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
    echo "#$n: bind failed — worker retired (an unbindable worker cannot be answer-relayed)" >&2
    _surf_unlock "$surf_locked"
    return 1
  fi
  # Only NOW is the meta bound (ticket field written) — the registry arm of
  # the occupancy check can see this worker, so the lock may be released.
  # Releasing at spawn was a hole: an unbound meta carries no ticket, and a
  # second process's check between spawn and bind saw a free surface.
  _surf_unlock "$surf_locked"; surf_locked=""

  # Persist the role (ARCHITECT/IMPLEMENT/SPIKE) this dispatcher already
  # knows into the registry meta, same read-modify-write-under-lock shape
  # board-bind.sh uses. board-answer.sh's needs-human fallback (no
  # recorded pre-park:) reads it back to pick a lane-correct return state
  # instead of hardcoding in-progress — an Architect resumed there would
  # land in a state its protocol cannot exit. Non-fatal: a failed write
  # only costs that fallback its lane-aware branch on THIS worker later.
  T_UUID="$uuid" T_ROLE="$role" DAEMON_HOME="$DAEMON_HOME" python3 - <<'PY' \
    || echo "#$n: role meta write failed (non-fatal)" >&2
import fcntl, json, os
home = os.environ["DAEMON_HOME"]
path = os.path.join(home, os.environ["T_UUID"] + ".json")
lock = open(os.path.join(home, ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    with open(path) as f:
        m = json.load(f)
    m["role"] = os.environ["T_ROLE"]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=2)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY

  # Claim this ticket's surfaces for the rest of the tick: two eligible
  # same-surface tickets in ONE sweep must yield one dispatch (the in-tick
  # arm of occupancy — the registry meta exists, but a later _ticket_exports
  # in this same loop could race the meta write). Spikes never occupy.
  if [ "$role" != "SPIKE" ] && [ -n "${T_SURFACES:-}" ]; then
    DISPATCHED_SURFACES="${DISPATCHED_SURFACES:-} $T_SURFACES"
  fi

  echo "dispatched #$n → $name [$uuid] engine=$engine role=$role"
}

# ---- modes ---------------------------------------------------------------------
if [ "${1:-}" = "--sweep" ]; then
  BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY' |
import os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
def rank(tid):
    p = tickets[tid]["priority"]
    return (B.PRIORITIES.index(p) if p in B.PRIORITIES else len(B.PRIORITIES), int(tid))
for tid in sorted(tickets, key=rank):
    if B.eligible(tickets, tid):
        print(tid)
PY
  while IFS= read -r tid; do
    [ -n "$tid" ] || continue
    if [ "$(_slots_used implement)" -ge "$CAP" ] && [ "$(_slots_used architect)" -ge "$ARCH_CAP" ]; then
      echo "cap reached: both lanes full — remaining eligible tickets stay queued"
      break
    fi
    dispatch_one "$tid" || echo "#$tid: dispatch error (continuing sweep)" >&2
  done
  exit 0
fi

[ $# -ge 1 ] || die "usage: implement-dispatch.sh <issue-number> | --sweep"
n="${1#\#}"
case "$n" in ""|*[!0-9]*) die "not an issue number: $1" ;; esac
dispatch_one "$n"
