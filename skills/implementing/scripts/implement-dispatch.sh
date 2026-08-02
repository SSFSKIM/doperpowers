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

die() { echo "error: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
[ -f "$BOOTSTRAP_TEMPLATE" ] || die "worker bootstrap missing: $BOOTSTRAP_TEMPLATE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

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
import re
slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", n["title"].lower())).strip("-")[:32].rstrip("-")
q("T_SLUG", slug or "ticket")
PY
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
  local n="$1" exports engine role protocol_file decompose prompt name spawn_out uuid meta status lane model

  meta="$(_bound_meta "$n")"
  if [ -n "$meta" ]; then
    status="$(printf '%s' "$meta" | cut -d'|' -f2)"
    case "$status" in
      working|blocked|error)
        echo "skip #$n: bound worker ${meta%%|*} status=$status"
        return 0 ;;
    esac
  fi

  exports="$(_ticket_exports "$n")" \
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
  prompt="$(P_ROLE="$role" P_ISSUE_NUMBER="$n" P_ISSUE_URL="$T_URL" \
    P_REPO="$BOARD_REPO" P_BOARD_SCRIPTS="$BOARD_SCRIPTS" \
    P_ENGINE_NAME="$engine" P_PROTOCOL_FILE="$protocol_file" \
    P_DECOMPOSE_DOC="$decompose" \
    python3 - "$BOOTSTRAP_TEMPLATE" <<'PY'
import os, re, sys
t = open(sys.argv[1]).read()
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
out = re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), m.group(0)), t)
left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", out)))
if left:
    sys.stderr.write("unrendered placeholder(s): %s\n" % " ".join(left))
    sys.exit(1)
print(out)
PY
)" || { echo "#$n: prompt render failed (unrendered placeholder or template error)" >&2; return 1; }
  [ -n "$prompt" ] || { echo "#$n: empty prompt — not dispatching" >&2; return 1; }

  name="$n-$T_SLUG"
  # ONE worker harness, two model routes (same shape as review-dispatch):
  # codex = the clodex gateway settings (GPT models via the local proxy),
  # claude = plain Claude models.
  if [ "$engine" = "codex" ]; then
    spawn_out="$(DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" \
      DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" \
      "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
      "${IMPLEMENT_MODEL:-fable}")" \
      || { echo "#$n: worker spawn failed" >&2; return 1; }
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
      || { echo "#$n: worker spawn failed" >&2; return 1; }
  fi
  printf '%s\n' "$spawn_out"
  uuid="$(printf '%s\n' "$spawn_out" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
  [ -n "$uuid" ] || { echo "#$n: spawned worker UUID was not parseable" >&2; return 1; }

  local try=1 bound=""
  while [ "$try" -le "${IMPLEMENT_BIND_ATTEMPTS:-3}" ]; do
    if "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$n"; then bound=1; break; fi
    [ "$try" -lt "${IMPLEMENT_BIND_ATTEMPTS:-3}" ] && sleep "${IMPLEMENT_BIND_DELAY:-2}"
    try=$((try + 1))
  done
  if [ -z "$bound" ]; then
    "$DAEMON_SCRIPTS/daemon-retire.sh" "$uuid" >/dev/null 2>&1 || true
    echo "#$n: bind failed — worker retired (an unbindable worker cannot be answer-relayed)" >&2
    return 1
  fi

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
