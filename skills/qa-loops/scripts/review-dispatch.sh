#!/usr/bin/env bash
# review-dispatch.sh — dispatch a review-worker daemon onto an open PR.
#
# The trigger half of doperpowers:qa-loops — mechanical only, no model
# judgment. Gathers PR + linked-ticket context, creates a DETACHED worktree
# at the PR head SHA, renders the skill-invocation bootstrap, and spawns a
# `review-pr-<n>` seat via `sminos spawn`.
#
# Usage:
#   review-dispatch.sh <pr-number>    triggered mode (GH workflow / manual)
#   review-dispatch.sh --sweep        catch-up: every unbound open PR, then
#                                     every in-review recomposition EPIC, then
#                                     the retirement of scale reviewers whose
#                                     epic has left in-review
#
# Two reviewer variants share one worker harness (see _spawn_reviewer):
#   review-pr-<n>     a GitHub PR, worktree detached at the PR head SHA.
#   review-epic-<n>   E2 scale review — an epic in in-review whose `pr:` meta
#                     is a CLOSURE PACKAGE, not a PR (its children already
#                     merged). Worktree detached at the epic's integration
#                     branch; the engine's base is what that branch merges
#                     into (the default branch), so the review range is the
#                     epic's aggregate diff. Sweep-only: nothing external
#                     triggers it, and the epic's verdict (which leaves
#                     in-review) is what ends the path.
#
# Env:
#   LOCAL_REPO          canonical local clone of the target repo (default: $PWD)
#   BOARD_REPO          owner/name (default: resolved from LOCAL_REPO via gh)
#   REVIEW_MODEL        optional model override for the review daemon
#                       (claude route defaults to opus, gateway route to fable)
#   REVIEW_EFFORT       reasoning effort for the claude route (default high —
#                       the QAgent tier is opus/high by design)
#   WORKER_ENGINE       which MODEL ROUTE the worker daemon uses: claude|codex
#                       (default claude). Every worker is a Claude-harness
#                       daemon; "claude" means plain Claude models, "codex"
#                       opts the spawn into the clodex gateway settings (GPT
#                       models via the local proxy). Resolution order per PR:
#                       an `engine:claude`/`engine:codex` label wins, else
#                       this env var, else claude.
#   CLODEX_SETTINGS     gateway settings file for the codex route
#                       (default ~/.claude/clodex-settings.json)
#   CLODEX_EFFORT       reasoning effort for the codex route (default xhigh)
#   CODEX_REVIEW_MODEL  codex model for the review ENGINE (default gpt-5.6-sol)
#   CODEX_REVIEW_EFFORT  codex reasoning effort for the review engine (default xhigh)
#   REVIEW_PRIORITY_LABEL  opt-in sweep ordering hint (dp#64): PRs carrying
#                       this label enumerate FIRST in --sweep (stable within
#                       both groups), so a priority cohort cannot be starved
#                       by newest-first inflow under a full review cap. The
#                       cohort rides its own --label listing, so it is found
#                       even beyond the main listing's 100-newest window.
#                       Unset = enumeration order untouched.
#   AUTO_MERGE_ENABLED  merge kill switch (default false = observation mode:
#                       the worker reviews and judges the verdict but parks
#                       the ticket needs-human instead of merging). Supplied
#                       as a skill runtime binding; the dispatch layer never
#                       merges.
#   DEFAULT_BRANCH      repo default branch (default: resolved via gh, or from
#                       the local clone's origin/HEAD in API mode); the
#                       scale-review lane resolves integration refs against it,
#                       and the API lane takes its manifest snapshots from it
#   REVIEW_MAX_CONCURRENT  reviewer slot cap (default 3). API mode: qagent-lane
#                       cap enforced against the local registry before claiming
#                       and sent as the server-side `laneCap`. gh mode: the
#                       sweep's new-spawn throttle — live reviewers are counted
#                       off the registry and dispatches beyond the cap queue to
#                       a later tick (a deep open-PR backlog would otherwise
#                       spawn one daemon per PR in a single tick). Triggered
#                       dispatches are an explicit event and are never gated.
#   SMINOS_CLI           sminos CLI launcher override (tests)
#   DAEMON_HOME         sminos seat registry dir (default ~/.claude/sminos)
#   BOARD_SCRIPTS       issue-tracker scripts dir override (tests)
#   REVIEW_BIND_ATTEMPTS / REVIEW_BIND_DELAY
#                       ticket-bind retries (defaults 3 attempts, 2s delay)
#   REVIEW_ACK_POLLS / REVIEW_ACK_DELAY
#                       startup-barrier acknowledgement wait (600 x 0.2s)
#   WORKTREE_BOOTSTRAP_CMD
#                       optional project bootstrap run inside each fresh review
#                       worktree before the worker spawns (e.g. `npm run
#                       setup:worktree`). Unset = no bootstrap (prior behavior).
#                       Runs with the worktree at the TRUSTED base ref, never
#                       the PR head (see BOOTSTRAP TRUST INVARIANT below).
#                       Failure logs to $DAEMON_HOME/<name>.bootstrap.log and
#                       never blocks dispatch.
#   WORKTREE_BOOTSTRAP_TIMEOUT
#                       bootstrap time budget in seconds (default 480). The
#                       PR-triggered Actions path is bounded ABOVE by
#                       pr-review-dispatch.yml `timeout-minutes: 10` — keep
#                       this default below that cap or GitHub kills the job
#                       before the nonfatal-failure path can run.
#   DISPATCH_LOCK_STALE per-worker dispatch-lock stale-steal age in minutes
#                       (default 30, same policy as board-sweep.sh)
#
# Per-repo risk surfaces: an optional file at <base>:.doperpowers/risk-surfaces.md
# in the target repo declares the repo's validated hot paths/patterns —
# lens-derivation input for the worker's engine fan-out, not a merge gate.
# It is read from the PR's BASE ref (never HEAD) so a PR cannot delist a
# surface it touches in the same commit.
# Per-repo facts: an optional file at <base>:.doperpowers/repo-facts.md declares
# Bootstrap / Validation / Evidence add-on facts (see executing).
# Same BASE-ref discipline; the Reviewer worker cross-checks claimed evidence
# against the declared validation commands and add-on requirements.
# LOCAL_REPO must be a FULL clone (not --single-branch): the base read resolves
# origin/<base>, refreshed by the per-dispatch fetch; a narrowed clone can
# leave that tracking ref stale and the manifests would silently read empty.
#
# Dedupe policy (references/operation-manual.md table):
# a live ACTIVE reviewer → skip; a dead ACTIVE reviewer →
# retire + respawn; a cleanly finished reviewer → triggered mode re-dispatches
# (explicit event = fresh signal), sweep mode skips; a FAILED reviewer —
# reply carries the ENGINE-UNAVAILABLE marker, or the turn finalized
# status=error (the worker died; a pre-first-turn gateway refusal leaves no
# reply to carry any marker) → retire + respawn (sweep too, capped at 3
# consecutive failed reviewers per PR — beyond that only an explicit PR
# event re-dispatches). A scale review has no such event: at the cap the
# sweep retires the failed reviewer and parks the EPIC needs-human, and the
# human's answer is what returns it to in-review for a fresh dispatch
# (sweep_epic).
#
# Stale reviewer, any route off in-review: a reviewer bound to a ticket
# whose board state is no longer in-review (ready-for-architect, parked on
# the human, or anything else) is stale by definition — nothing will ever
# re-dispatch a normally-finished reviewer on its own (sweep mode's
# "cleanly finished → skip" row above is permanent, not a retry). The sweep
# loop below resolves the ticket's status
# BEFORE consulting the registry dedupe machinery: when the ticket
# isn't in-review, any FINISHED (non-active) reviewer meta it finds is
# retired right there and the tick is skipped without spawning — never an
# ACTIVE (working/blocked) reviewer, which owns its own exit. That retire
# is what makes the ticket's eventual return to in-review land on the
# ordinary "none / retired → dispatch" row above, with no special-case
# dispatch logic needed once the ticket is back.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SMINOS_CLI="${SMINOS_CLI:-$(cd "$SKILL_DIR/../sminos/scripts" && pwd)/sminos}"
# lib.sh applies the one registry-root rule ($SMINOS_HOME, then $DAEMON_HOME,
# then ~/.claude/sminos) and leaves both names holding it, so the root is
# already settled here. Exported at the same value as the other entrypoints:
# the CLI, the board scripts and every spawned child read one registry.
# shellcheck source=../../sminos/scripts/lib.sh
. "$SKILL_DIR/../sminos/scripts/lib.sh"
export SMINOS_HOME DAEMON_HOME
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)}"
BOOTSTRAP_TEMPLATE="$SKILL_DIR/references/review-worker-bootstrap.md"

die() { echo "error: $*" >&2; exit 1; }

git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
# The board scripts this run invokes bare (board-bind, board-transition, …)
# anchor _lib.sh's BOARD_ROOT on the CURRENT directory and die at source time
# when it is not a checkout ("not inside a git repo"). Our own git calls use
# `git -C`, so cwd would otherwise never be corrected — and the GitHub Actions
# entrypoint runs us from an EMPTY workspace, because pr-review-dispatch.yml
# deliberately omits actions/checkout (the job must never execute PR code).
# Every path above is already absolute, so this is safe to do here.
cd "$LOCAL_REPO" || die "cannot cd to LOCAL_REPO: $LOCAL_REPO"
[ -f "$BOOTSTRAP_TEMPLATE" ] || die "worker bootstrap missing: $BOOTSTRAP_TEMPLATE"
[ -x "$SMINOS_CLI" ] || die "the sminos CLI is not executable at $SMINOS_CLI (set SMINOS_CLI)"
# The registry root moved to ~/.claude/sminos and this script scans it
# directly, so it must never be the first process to look at an empty new
# root: let sminos fold the old root in first. Idempotent, and FAIL CLOSED
# — a half-migrated registry reads as an empty fleet, which passes every
# dedupe and cap check and dispatches over live workers.
"$SMINOS_CLI" migrate --quiet || die "sminos migrate failed — refusing to dispatch against a possibly half-migrated registry"

# THE TICK IS NOT ITS SESSION, and it has to say so BEFORE the binding is
# resolved: _binding.sh reads this session's seat record at SOURCE time when the
# checkout's board.json predates the `repo` key, so a declaration made further
# down would arrive after the one read it exists to close. The doctrine is the
# block beside `unset BOARD_RUN_TOKEN` in the api branch below; only the timing
# puts the export up here.
export BOARD_NO_SELF_LOCATE=1
# THE BINDING IS RESOLVED BEFORE THE gh PROBE, for the same reason
# execute-dispatch resolves it there: an api-bound repo never invokes gh at
# all, so requiring the CLI before knowing the binding would make the whole API
# path unreachable on a machine that has no gh. Everything above is
# mode-independent; the gh-mode initialization starts below.
# shellcheck source=../../issue-tracker/scripts/_binding.sh
. "$BOARD_SCRIPTS/_binding.sh"

REVIEW_CAP="${REVIEW_MAX_CONCURRENT:-3}"

if [ "$BOARD_BINDING" = api ]; then
  # No gh, so neither of gh mode's two repo facts is resolvable the usual way.
  # BOARD_REPO arrives from _binding.sh (the api binding's declared `repo`,
  # which it refuses to run without) and is both the repo every claim narrows
  # to and the project key board-bind posts. It used to fall back to
  # `basename $BOARD_ROOT` here — a guess that is right only while the checkout
  # happens to be named after the board's key, and wrong silently otherwise.
  # The default branch comes off the clone's own origin/HEAD, falling back to
  # main when the clone has no remote-tracking head.
  if [ -z "${DEFAULT_BRANCH:-}" ]; then
    DEFAULT_BRANCH="$(git -C "$LOCAL_REPO" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    DEFAULT_BRANCH="${DEFAULT_BRANCH#origin/}"
  fi
  # AND ONE RUNG BELOW THE CLONE, BEFORE THE `main` GUESS: DEFAULT_BRANCH is
  # the ref every dispatch reads its two manifest snapshots from (MANIFEST_REF),
  # so a wrong guess hands the worker manifests from a branch the repo does not
  # even use. (The api-scale review RANGE no longer rides this value — the
  # worker re-resolves its base from the remote — but the snapshots do.) A clone with
  # no origin/HEAD — every `git clone --single-branch` and every worktree cut
  # from one — has the answer on the remote, and ls-remote asks for it without
  # gh. Best-effort: the `main` fallback below still catches a dead network.
  # `|| true` is load-bearing under `set -e -o pipefail`: a clone with no origin
  # at all (every fixture repo, and a legitimate local-only checkout) makes
  # ls-remote exit 128, which would take the whole dispatcher down instead of
  # falling through to the guess this rung is only trying to improve on.
  if [ -z "$DEFAULT_BRANCH" ]; then
    DEFAULT_BRANCH="$(git -C "$LOCAL_REPO" ls-remote --symref origin HEAD 2>/dev/null \
      | sed -n 's#^ref: refs/heads/\([^[:space:]]*\)[[:space:]].*#\1#p' | head -1 || true)"
  fi
else
  command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
  if [ -z "${BOARD_REPO:-}" ]; then
    BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
  fi
  [ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"
  #   DEFAULT_BRANCH — the scale lane's integration-ref fallback.
  DEFAULT_BRANCH="${DEFAULT_BRANCH:-$(gh repo view "$BOARD_REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main)}"
fi
# EXPORTED IN gh MODE, not just set: the scale-review passes shell out to python
# that imports _board, whose repo() reads the ENVIRONMENT. Run from board-sweep
# it arrives exported already and the miss is invisible; run directly — the
# documented path — an unexported value made every scale epic die
# "BOARD_REPO is unset" inside the subprocess and be silently skipped.
#
# NOT in api mode, where that reader does not exist (_board's state-machine half
# is never exercised there) and everything that needs the value takes it from
# this shell: _api_py hands it to python3 explicitly, and P_REPO below is an
# ordinary expansion. Exported, it would become the default for any checkout a
# descendant resolves its own binding in — including one whose board.json says a
# different repo, which _binding.sh would then never read.
#
# The worker spawn below is the one deliberate exception, and it states itself
# on the prefix rather than riding an ambient export: a reviewer checks out the
# PR head, and a head predating the repo key carries a board.json without one,
# so the pin is what lets that worker finish its own review. It cannot leak —
# the run bearer beside it binds the worker to a ticket in this very repo.
if [ "$BOARD_BINDING" = gh ]; then export BOARD_REPO; fi
[ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH="main"
# Repo-wide config injected into every worker prompt (constant across PRs):
#   AUTO_MERGE_DISPLAY — the merge kill switch as the worker sees it.
case "${AUTO_MERGE_ENABLED:-false}" in
  true|1|on|yes|TRUE|True) AUTO_MERGE_DISPLAY="on" ;;
  *) AUTO_MERGE_DISPLAY="off" ;;
esac
CODEX_REVIEW_MODEL="${CODEX_REVIEW_MODEL:-gpt-5.6-sol}"
CODEX_REVIEW_EFFORT="${CODEX_REVIEW_EFFORT:-xhigh}"
REVIEW_ENGINE="$SCRIPT_DIR/review-engine.sh"

# Newest registry entry for worker name <1> (review-pr-<n> or review-epic-<n>)
# → "uuid|status|current|engine|pid|host|boot" (empty if none).
_reviewer_meta() {
  DAEMON_HOME="$DAEMON_HOME" WNAME="$1" python3 - <<'PY'
import glob, json, os
home = os.environ["DAEMON_HOME"]; name = os.environ["WNAME"]
best = None
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("name") == name:
        key = str(m.get("updated") or m.get("created") or "")
        if best is None or key > best[0]:
            best = (key, m)
if best:
    m = best[1]
    print("%s|%s|%s|%s|%s|%s|%s" % (m.get("uuid", ""), m.get("status", ""), m.get("current", ""),
                                    m.get("engine") or "claude", m.get("pid", ""), m.get("host", ""),
                                    m.get("boot_id", "")))
PY
}

# Live gh-mode reviewers counted off the registry — the sweep's new-spawn
# throttle (REVIEW_MAX_CONCURRENT). Same slot definition as execute-dispatch's
# _slots_used: a meta in an active status holds a slot. A finished --no-wait
# meta stays `working` until _decide finalizes it (which happens as the sweep
# visits its PR), so a tick can briefly overcount and under-dispatch; the next
# tick self-corrects. `error` metas do NOT count: their respawn is itself the
# capped action, and counting them would wedge the cap closed on exactly the
# failure class it should be retrying. Same-identity ONLY (_identity_local's
# rule, inlined): a meta from another host or a previous boot is a dead
# session, not a slot — and parked-ticket metas are deliberately never
# finalized (they are board-answer wake targets), so without this filter a
# reboot's stale parked reviewers hold the cap closed forever (observed:
# 8 dead metas, 53 PRs queued, 0 spawns). `idle` needs one more cut: the
# no-wait spawn samples the fresh session and sometimes records idle at
# BIRTH while the review is actually just starting (observed: 12 spawns in
# one tick sailed past cap 8 because their metas never read working) — a
# premature-idle meta has an empty reply, a genuinely finished reviewer's
# finalize wrote a substantive one. So idle counts as a slot only while its
# reply file is missing or trivially small.
_gh_review_slots() {
  T_DHOME="$DAEMON_HOME" T_HOST="${DAEMON_HOST:-}" T_BOOT="${DAEMON_BOOT_ID:-}" python3 - <<'PYEOF'
import glob, json, os
host = os.environ.get("T_HOST") or ""
boot = os.environ.get("T_BOOT") or ""
home = os.environ["T_DHOME"]
n = 0
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    if not (name.startswith("review-pr-") or name.startswith("review-epic-")):
        continue
    status = m.get("status")
    if status not in ("working", "blocked", "idle"):
        continue
    mh = str(m.get("host") or "")
    mb = str(m.get("boot_id") or "")
    if mh and host and mh != host:
        continue
    if mb and boot and mb != boot:
        continue
    if status == "idle":
        rp = os.path.join(home, str(m.get("uuid") or "") + ".reply.txt")
        try:
            if os.path.getsize(rp) > 64:
                continue  # finished for real — finalize wrote a substantive reply
        except OSError:
            pass  # no reply yet — premature idle, still a slot
    n += 1
print(n)
PYEOF
}

# rc 0 when the reviewer's CURRENT turn is live: claude → session uuid visible
# in `claude agents`; codex → recorded pid alive ON THIS HOST (a foreign-host
# pid is dead by definition — only its number migrated with the registry).
_is_live() {  # <current> <engine> <pid> <host> <boot>
  _identity_local "${4:-}" "${5:-}" || return 1
  if [ "$2" = "codex" ]; then
    [ -n "$3" ] || return 1
    kill -0 "$3" 2>/dev/null
    return
  fi
  claude agents --json --all 2>/dev/null | CUR="$1" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
sys.exit(0 if any(a.get("sessionId") == os.environ["CUR"] for a in d) else 1)'
}

_retire() { "$SMINOS_CLI" retire "$1" >/dev/null 2>&1 || true; }

# Retire a meta that is being replaced BECAUSE IT FAILED, stamping why before
# the retire lands. `sminos retire` is sminos-owned and writes status=retired
# over whatever terminal status the failure left, which is the only evidence
# _outage_streak had — so a dead-worker cycle (finalize error → respawn →
# retire) erased its own failure and the streak reset every tick, leaving the
# 3-consecutive cap unreachable for exactly the failure class it exists for.
# Only failure retirements carry the stamp; a superseded reviewer (a new
# closure package) and a stale-ticket retirement carry none, so a
# non-failure retirement still breaks the streak and cannot inflate the cap.
_retire_failed() {  # <uuid>
  _stamp_meta "$1" retired_from failure 2>/dev/null || true
  _retire "$1"
}

# One field of daemon <1>'s registry meta (empty when absent).
_meta_field() {  # <uuid> <key>
  DAEMON_HOME="$DAEMON_HOME" M_UUID="$1" M_KEY="$2" python3 - <<'PY'
import json, os
try:
    m = json.load(open(os.path.join(os.environ["DAEMON_HOME"], os.environ["M_UUID"] + ".json")))
except Exception:
    m = {}
print(m.get(os.environ["M_KEY"]) or "")
PY
}

# Write one field into daemon <1>'s registry meta, under the same lock
# board-bind.sh takes (read-modify-write; unknown keys are preserved), and
# under its write_meta mode discipline too. This helper lands on API metas —
# a failure retirement stamps one — and an API meta holds the run bearer.
# Recreating that file at the umask default republishes the secret
# world-readable, and permanently: the api claim path's own stamp preserves
# whatever mode it finds, so a widened mode is never narrowed again.
_stamp_meta() {  # <uuid> <key> <value>
  DAEMON_HOME="$DAEMON_HOME" M_UUID="$1" M_KEY="$2" M_VAL="$3" python3 - <<'PY'
import fcntl, json, os
home = os.environ["DAEMON_HOME"]
path = os.path.join(home, os.environ["M_UUID"] + ".json")
lock = open(os.path.join(home, ".metalock"), "a")
fcntl.flock(lock, fcntl.LOCK_EX)
try:
    with open(path) as f:
        m = json.load(f)
    m[os.environ["M_KEY"]] = os.environ["M_VAL"]
    mode = 0o600 if m.get("run_bearer") else os.stat(path).st_mode & 0o777
    tmp = path + ".tmp"
    # The mode argument applies only to an inode this open CREATES; a .tmp left
    # by an earlier crash is an existing inode at whatever mode it had. Unlink
    # first, create exclusively, chmod against a narrowing umask.
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

# rc 0 when some LOCAL `claude agents` row's cwd equals worktree path <1>. A
# visible row with matching foreign registry metadata migrated with the session
# store, not the process, so it does not occupy the worktree. Unmanaged rows
# have no identity evidence and remain conservatively local/occupied. A MANAGED
# local row whose turn is over no longer occupies: finished daemons stay
# LISTED with state=working while their process lingers — `status` (busy →
# idle) is the turn signal, and retire + respawn deliberately reuses the path.
_wt_occupied() {
  claude agents --json --all 2>/dev/null | \
    DAEMON_HOME="$DAEMON_HOME" DAEMON_HOST="$DAEMON_HOST" DAEMON_BOOT_ID="$DAEMON_BOOT_ID" WT="$1" python3 -c '
import glob, json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
metas = {}
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if (m.get("engine") or "claude") == "claude" and m.get("current"):
        metas[str(m["current"])] = m
def local(m):
    host = str(m.get("host") or "")
    boot = str(m.get("boot_id") or "")
    return (not host or host == os.environ["DAEMON_HOST"]) and \
           (not boot or not os.environ["DAEMON_BOOT_ID"] or boot == os.environ["DAEMON_BOOT_ID"])
for a in d:
    if a.get("cwd") != os.environ["WT"]:
        continue
    m = metas.get(str(a.get("sessionId") or ""))
    if m is None:
        if a.get("state") in ("stopped", "done", "failed"):
            continue  # A PREVIOUS OCCUPANT of a re-filled seat. A seat keeps
                      # ONE record across fills and moves `current` to the new
                      # session, so the old session is no longer keyed here and
                      # would fall into the conservative branch below — pinning
                      # the worktree forever after the first re-fill. A row
                      # whose turn already ended holds nothing.
        if a.get("state") in ("working", "blocked") and a.get("status") == "idle":
            continue  # the SAME lingering shape the mapped branch normalises:
                      # a finished turn keeps its state and goes status=idle.
                      # An unmapped row gets the same reading — there is no
                      # record to consult, and a turn that ended holds nothing.
        sys.exit(0)   # unmanaged RUNNING row: no identity evidence, so occupied
    if not local(m):
        continue      # foreign identity: only the registry migrated
    if m.get("status") == "retired":
        continue      # dispatcher-retired identity: its listing row lingers
                      # stopped/status-less and would otherwise occupy forever
    if a.get("status") == "idle" and a.get("state") != "blocked":
        continue      # finished turn lingering in the listing — free for reuse
    sys.exit(0)
sys.exit(1)' && return 0
  # codex workers never appear in `claude agents` — scan the registry, but
  # count ONLY codex metas with a live pid; a stale claude-engine `working`
  # meta must NOT start blocking removal (the claude path's fail-open
  # behavior above is unchanged).
  DAEMON_HOME="$DAEMON_HOME" DAEMON_HOST="$DAEMON_HOST" DAEMON_BOOT_ID="$DAEMON_BOOT_ID" WT="$1" python3 - <<'PY'
import glob, json, os, sys
home = os.environ["DAEMON_HOME"]; wt = os.environ["WT"]
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("engine") != "codex" or m.get("cwd") != wt:
        continue
    if m.get("status") not in ("working", "blocked"):
        continue
    host = str(m.get("host") or "")
    if host and host != os.environ["DAEMON_HOST"]:
        continue   # foreign-host pid — the process did not migrate with the registry
    boot_id = str(m.get("boot_id") or "")
    if boot_id and os.environ["DAEMON_BOOT_ID"] and boot_id != os.environ["DAEMON_BOOT_ID"]:
        continue   # prior-boot pid — the pid namespace did not survive the reboot
    pid = str(m.get("pid") or "")
    if pid.isdigit():
        try:
            os.kill(int(pid), 0)
            sys.exit(0)   # live codex worker sits in this worktree
        except OSError:
            pass
sys.exit(1)
PY
}

# ---- worktree bootstrap (optional, config-driven) ------------------------------
# Detached review worktrees start bare — no dependencies, no local env files —
# which made reviewers' verification runs fail red or pass vacuously (the env
# tracker's dominant thread). When WORKTREE_BOOTSTRAP_CMD is set, run it inside
# the fresh worktree BEFORE the worker spawns, so the environment is ready by
# the time the reviewer's first verification command runs. Failure is recorded
# but never fatal: the reviewer can finish bootstrap by hand, and blocking the
# whole review on a provisioning hiccup would trade a known-bad env for no
# review at all.
# BOOTSTRAP TRUST INVARIANT — extends the "must never execute PR code"
# invariant the Actions entrypoint already enforces (see the cd comment near
# the top): the bootstrap runs while the worktree is checked out at the
# TRUSTED ref (the PR's base / the epic's base branch), never at the PR head.
# package.json, lockfiles, and every script the command resolves come from
# code that survived review; only after the bootstrap does the worktree move
# to the reviewed ref, and untracked artifacts (node_modules, .env.local)
# survive that checkout. A PR that edits the bootstrap's own inputs is
# deliberately not honored at dispatch time — the worker re-verifies its
# environment per protocol. The callers below own that ref choreography; this
# helper only runs the command where it is told to.
#
# GNU `timeout` does not exist on the stock-macOS runner (runner-setup.md),
# where an unguarded call would exit 127 and silently skip every bootstrap —
# and TERM alone lets a signal-ignoring bootstrap overrun its budget. Prefer
# timeout/gtimeout with a KILL backstop; otherwise a portable watchdog: TERM
# at the budget, KILL 10s later.
_run_with_budget() {  # <seconds> <command-string> — runs via bash -lc
  local budget="$1" cmd="$2" rc=0 pid wd
  if command -v timeout >/dev/null 2>&1; then
    timeout -k 10 "$budget" bash -lc "$cmd"; return $?
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout -k 10 "$budget" bash -lc "$cmd"; return $?
  fi
  bash -lc "$cmd" & pid=$!
  ( sleep "$budget"; kill -TERM "$pid" 2>/dev/null; sleep 10; kill -KILL "$pid" 2>/dev/null ) & wd=$!
  wait "$pid" || rc=$?
  kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null || true
  return "$rc"
}

_bootstrap_worktree() {  # <worktree-path> <worker-name>
  [ -n "${WORKTREE_BOOTSTRAP_CMD:-}" ] || return 0
  local wt="$1" wname="$2" log rc=0
  log="$DAEMON_HOME/$wname.bootstrap.log"
  ( cd "$wt" && _run_with_budget "${WORKTREE_BOOTSTRAP_TIMEOUT:-480}" \
      "$WORKTREE_BOOTSTRAP_CMD" ) >"$log" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$wname: worktree bootstrap failed rc=$rc (see $log) — dispatching anyway" >&2
  fi
  return 0
}

# ---- per-worker dispatch lock --------------------------------------------------
# A PR event and the sweep can overlap while a long bootstrap runs: neither
# sees reviewer metadata yet (it is published at spawn), both pass dedupe, and
# the second would remove/recreate the same worktree mid-bootstrap. Dedupe on
# dispatch stays the primary serializer (operation manual, "Two dispatches,
# one PR"); this lock only covers the metadata-free window between workspace
# preparation and spawn. mkdir lock — portable, macOS ships no flock — with
# the same stale-steal policy as board-sweep.sh: a lock a dead dispatch left
# behind is stolen after 30 min, not obeyed.
_with_dispatch_lock() {  # <worker-name> <fn> [args…]
  local wname="$1" lock rc=0; shift
  lock="$DAEMON_HOME/$wname.dispatch.lock"
  if ! mkdir "$lock" 2>/dev/null; then
    if [ -n "$(find "$lock" -maxdepth 0 -mmin +"${DISPATCH_LOCK_STALE:-30}" 2>/dev/null)" ]; then
      rmdir "$lock" 2>/dev/null || true
      mkdir "$lock" 2>/dev/null \
        || { echo "$wname: concurrent dispatch holds the lock — skip"; return 0; }
    else
      echo "$wname: concurrent dispatch holds the lock — skip"; return 0
    fi
  fi
  "$@" || rc=$?
  rmdir "$lock" 2>/dev/null || true
  return "$rc"
}

# ---- per-PR dispatch (dedupe already decided by the caller) --------------------
# Every step is explicitly guarded: in sweep mode this function runs behind
# `||` (which suspends errexit through the WHOLE call subtree), so an
# unguarded mid-function failure would be silently absorbed — dispatching
# with stale vars from the previous iteration or an empty prompt. Guards
# return 1 so the sweep's per-PR reporter fires instead.
dispatch_one() { _with_dispatch_lock "review-pr-$1" _dispatch_one_locked "$@"; }
_dispatch_one_locked() {
  local pr="$1" mode="${2:-triggered}" tmp pr_json exports issue td wt prompt engine control_dir bind_ready ledger
  tmp="$(mktemp -d)"
  pr_json="$(gh pr view "$pr" -R "$BOARD_REPO" --json number,title,body,baseRefName,headRefName,headRefOid,url,isDraft,state,labels,closingIssuesReferences)" \
    || { echo "#$pr: gh pr view failed" >&2; rm -rf "$tmp"; return 1; }
  printf '%s' "$pr_json" > "$tmp/pr.json"
  exports="$(TMP="$tmp" python3 - <<'PY'
import json, os, re, shlex
d = json.load(open(os.path.join(os.environ["TMP"], "pr.json")))
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
q("PR_TITLE", d["title"]); q("BASE_REF", d["baseRefName"]); q("HEAD_REF", d["headRefName"])
q("HEAD_SHA", d["headRefOid"]); q("PR_URL", d["url"]); q("PR_STATE", d["state"])
q("PR_DRAFT", 1 if d["isDraft"] else 0)
names = [l.get("name", "") for l in (d.get("labels") or [])]
eng = "claude" if "engine:claude" in names else ("codex" if "engine:codex" in names else "")
q("ENGINE_LABEL", eng)
linked = [str(n["number"]) for n in (d.get("closingIssuesReferences") or [])]
text = (d.get("title") or "") + "\n" + (d.get("body") or "")
# same close-keyword semantics as the consumer label automation: stacked PRs
# onto integration branches leave closingIssuesReferences empty.
for m in re.finditer(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+#(\d+)", text, re.I):
    if m.group(1) not in linked:
        linked.append(m.group(1))
q("LINKED_ISSUES", " ".join(linked))
PY
)" || { echo "#$pr: PR json parse failed" >&2; rm -rf "$tmp"; return 1; }
  eval "$exports"
  engine="${ENGINE_LABEL:-${WORKER_ENGINE:-claude}}"
  if [ "$PR_STATE" != "OPEN" ]; then echo "#$pr: not open ($PR_STATE) — skip"; rm -rf "$tmp"; return 0; fi
  if [ "$PR_DRAFT" != "0" ]; then echo "#$pr: draft — skip"; rm -rf "$tmp"; return 0; fi

  # primary ticket (first linked issue; the full list rides the prompt as
  # numbers only — the worker reads PR and ticket bodies live via gh)
  issue="${LINKED_ISSUES%% *}"

  # standing tech-debt sink (optional)
  td="$(gh issue list -R "$BOARD_REPO" --label tech-debt --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"
  et="$(gh issue list -R "$BOARD_REPO" --label env-tracker --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"

  # DETACHED worktree at the PR head SHA — the PR branch is usually checked
  # out in the executor's worktree, and git forbids a second checkout;
  # detached HEAD sidesteps it (spec Decision Log). Fixes push HEAD:<branch>.
  wt="$LOCAL_REPO/.claude/worktrees/review-pr-$pr"
  git -C "$LOCAL_REPO" fetch -q origin "$HEAD_REF" "$BASE_REF" \
    || { echo "#$pr: git fetch failed ($HEAD_REF/$BASE_REF)" >&2; rm -rf "$tmp"; return 1; }

  # Per-repo risk-surface manifest, read from the BASE ref (not HEAD) so a PR
  # cannot weaken its own gate in the same commit. Absent file → empty, and
  # the worker falls back to the always-on categories. Never fails dispatch.
  git -C "$LOCAL_REPO" show "origin/$BASE_REF:.doperpowers/risk-surfaces.md" > "$tmp/risk.md" 2>/dev/null \
    || : > "$tmp/risk.md"
  git -C "$LOCAL_REPO" show "origin/$BASE_REF:.doperpowers/repo-facts.md" > "$tmp/facts.md" 2>/dev/null \
    || : > "$tmp/facts.md"
  [ -z "$issue" ] || _finalize_ticket_owners "$issue"
  if [ -e "$wt" ]; then
    if _wt_occupied "$wt"; then
      echo "#$pr: live daemon occupies $wt — not removing (retire it first)" >&2
      rm -rf "$tmp"; return 1
    fi
    git -C "$LOCAL_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$LOCAL_REPO" worktree prune
  # Trust choreography (see the BOOTSTRAP TRUST INVARIANT above): with a
  # bootstrap configured, the worktree is born at the trusted BASE ref, the
  # bootstrap runs there, and only then does the worktree move to the PR
  # head. Without one, the head checkout is direct as before.
  if [ -n "${WORKTREE_BOOTSTRAP_CMD:-}" ]; then
    git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "origin/$BASE_REF" \
      || { echo "#$pr: worktree add failed (origin/$BASE_REF)" >&2; rm -rf "$tmp"; return 1; }
    _bootstrap_worktree "$wt" "review-pr-$pr"
    git -C "$wt" checkout -q --detach "$HEAD_SHA" \
      || { echo "#$pr: checkout of PR head failed" >&2; rm -rf "$tmp"; return 1; }
  else
    git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "$HEAD_SHA" \
      || { echo "#$pr: worktree add failed" >&2; rm -rf "$tmp"; return 1; }
  fi

  # Startup barrier + orchestrator-only control state. The worker receives only
  # the ready-file path; fixers receive neither it nor the sibling ledger path.
  # A ticketed barrier is published only AFTER exclusive binding succeeds.
  control_dir="$(mktemp -d "$DAEMON_HOME/review-pr-$pr-control.XXXXXX")" \
    || { echo "#$pr: control dir allocation failed" >&2; rm -rf "$tmp"; return 1; }
  bind_ready="$control_dir/bind-ready.json"
  ledger="$control_dir/accepted-commits.json"
  if ! chmod 700 "$control_dir" \
    || ! printf '{"push_base":"","commits":{}}\n' > "$ledger" \
    || ! chmod 600 "$ledger"; then
    echo "#$pr: control state initialization failed" >&2
    rm -rf "$tmp" "$control_dir"
    return 1
  fi

  prompt="$(P_PR_NUMBER="$pr" P_PR_URL="$PR_URL" P_REVIEW_MODE="pr" \
    P_WORKER_NAME="review-pr-$pr" \
    P_REPO="$BOARD_REPO" P_BASE_REF="$BASE_REF" P_HEAD_REF="$HEAD_REF" \
    P_HEAD_SHA="$HEAD_SHA" P_ISSUE_NUMBER="${issue:-none}" \
    P_ISSUE_LIST="${LINKED_ISSUES:-none}" \
    P_TECH_DEBT_ISSUE="${td:-none}" \
    P_ENV_TRACKER_ISSUE="${et:-none}" \
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" P_AUTO_MERGE="$AUTO_MERGE_DISPLAY" \
    P_MANIFEST_REF="$BASE_REF" \
    P_BIND_READY_FILE="$bind_ready" P_SKILL_FILE="$SKILL_DIR/SKILL.md" \
    P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/executing/SKILL.md" \
    P_ENGINE_NAME="$engine" P_CODEX_REVIEW_MODEL="$CODEX_REVIEW_MODEL" \
    P_CODEX_REVIEW_EFFORT="$CODEX_REVIEW_EFFORT" P_REVIEW_ENGINE="$REVIEW_ENGINE" \
    RISK_FILE="$tmp/risk.md" FACTS_FILE="$tmp/facts.md" \
    _render_prompt)" \
    || { echo "#$pr: prompt render failed" >&2; rm -rf "$tmp" "$control_dir"; return 1; }
  rm -rf "$tmp"
  [ -n "$prompt" ] || { echo "#$pr: empty prompt — not dispatching" >&2; rm -rf "$control_dir"; return 1; }

  _spawn_reviewer "review-pr-$pr" "$issue" "$prompt" "$wt" "$engine" "$control_dir"
}

# ---- scale review: one in-review recomposition epic (no PR) --------------------
# E2: an epic reaches in-review with a CLOSURE PACKAGE in its `pr:` meta and
# no GitHub PR — its children are already merged. Same worker harness as a PR
# review, different entry artifact and worktree: a detached checkout of the
# epic's integration branch (`branch:` meta), or the repo default branch when
# that branch is gone — the normal shape once children merge and their
# branches are deleted. Guarded per step for the same reason dispatch_one is:
# the sweep runs it behind `||`.
dispatch_epic() {  # <epic> <closure-package-url> [integration-branch] [engine-label] [child pull numbers]
  # Scale review is sweep-only, so the spawn throttle sits on the wrapper —
  # every epic spawn route (fresh, respawn, superseded) funnels through here.
  if [ "$(_gh_review_slots)" -ge "$REVIEW_CAP" ]; then
    echo "epic #$1: review cap reached ($REVIEW_CAP live) — queued for a later tick"
    return 0
  fi
  _with_dispatch_lock "review-epic-$1" _dispatch_epic_locked "$@"
}
_dispatch_epic_locked() {
  local etid="$1" pkg="$2" branch="${3:-}" eng_label="${4:-}" pulls="${5:-}"
  local name tmp wt int_ref base_ref td prompt engine pr_ref
  local control_dir bind_ready ledger range_note
  name="review-epic-$etid"
  # The epic's own engine:* label wins over the environment, exactly as the PR
  # path resolves it. Scale review is a QAgent route, and per-ticket engine
  # overrides apply to every QAgent route — the X4 exemption covers ARCHITECT
  # dispatch only, where plan authorship is deliberately never label-routed.
  engine="${eng_label:-${WORKER_ENGINE:-claude}}"
  # Two different refs, and conflating them cost the engine its whole range:
  #   int_ref  — the epic's integration branch, where the worktree sits (the
  #              aggregate of the children's merged work).
  #   base_ref — what that branch integrates INTO, i.e. the repo default
  #              branch. This is the ENGINE's --base: `merge-base(base,HEAD)
  #              ..HEAD` is the epic's aggregate diff. Binding BASE_REF to the
  #              integration branch itself (which the worktree is checked out
  #              at) made that range empty.
  # It is also the manifest ref, on the same discipline a PR review uses: the
  # risk-surface/repo-facts snapshots come from the branch the reviewed work
  # merges into, never from the reviewed work itself.
  int_ref="${branch:-$DEFAULT_BRANCH}"
  base_ref="$DEFAULT_BRANCH"
  if ! git -C "$LOCAL_REPO" fetch -q origin "$int_ref" 2>/dev/null; then
    if [ "$int_ref" = "$DEFAULT_BRANCH" ]; then
      echo "$name: git fetch failed ($int_ref)" >&2; return 1
    fi
    echo "$name: integration branch '$int_ref' is gone (deleted when its children merged) — the closure package's PR ranges are the review ranges" >&2
    int_ref="$DEFAULT_BRANCH"
    # The fetch that just failed never reached the default branch, and
    # collapsing int_ref onto it makes the base_ref fetch below a no-op — so
    # fetch it HERE or everything downstream is built from a possibly-stale
    # local origin/<default>: the worktree, both manifests, and the merged
    # per-child head SHAs the closure package names. This is precisely the
    # mode whose prompt sends the worker at those per-child ranges, so a
    # stale ref is the difference between reviewing them and not finding them.
    git -C "$LOCAL_REPO" fetch -q origin "$DEFAULT_BRANCH" \
      || { echo "$name: git fetch failed ($DEFAULT_BRANCH)" >&2; return 1; }
  fi
  if [ "$int_ref" != "$base_ref" ]; then
    git -C "$LOCAL_REPO" fetch -q origin "$base_ref" \
      || { echo "$name: git fetch failed ($base_ref)" >&2; return 1; }
  fi
  # The children's PR heads. Squash and rebase merges rewrite commits, so a
  # merged child's head SHA is an ancestor of nothing on the default branch
  # and its branch is usually deleted — yet the closure package names those
  # SHAs and the no-integration-branch mode tells the reviewer to detach at
  # each one. In a fresh clone that detach simply fails. GitHub retains
  # refs/pull/<n>/head past branch deletion, so fetch them here. Objects land
  # in LOCAL_REPO and every worktree of it shares that object store, so the
  # reviewer's worktree can reach them. Per-ref non-fatal: a pull ref that is
  # genuinely gone is a finding for the reviewer to report against the closure
  # package, not a reason for the dispatcher to refuse the whole review.
  for pr_ref in $pulls; do
    git -C "$LOCAL_REPO" fetch -q origin "refs/pull/$pr_ref/head" 2>/dev/null \
      || echo "$name: pull head refs/pull/$pr_ref/head is unfetchable — that child's range may not resolve" >&2
  done
  # No integration branch left ⇒ the worktree sits on the default branch and
  # there is no aggregate range at all; say so in the prompt rather than
  # letting the worker run an engine over nothing.
  if [ "$int_ref" = "$base_ref" ]; then
    range_note="This epic has NO aggregate branch range: its integration branch is gone (deleted when its children merged), so this worktree sits on $base_ref itself and an engine run based on origin/$base_ref would review nothing. The review ranges are the per-child base/head ranges the closure package names — drive the engine over those, one range at a time (the worktree is yours to move: detach it at a range's head and run the engine with that range's base)."
  else
    range_note="Your aggregate review range is this worktree's integration branch '$int_ref' against origin/$base_ref — the branch it merges into — which is exactly what the engine's \`--base origin/$base_ref\` reviews."
  fi
  _finalize_ticket_owners "$etid"

  tmp="$(mktemp -d)"
  # Same BASE-ref manifest discipline as a PR review (no head to read from).
  git -C "$LOCAL_REPO" show "origin/$base_ref:.doperpowers/risk-surfaces.md" > "$tmp/risk.md" 2>/dev/null \
    || : > "$tmp/risk.md"
  git -C "$LOCAL_REPO" show "origin/$base_ref:.doperpowers/repo-facts.md" > "$tmp/facts.md" 2>/dev/null \
    || : > "$tmp/facts.md"
  td="$(gh issue list -R "$BOARD_REPO" --label tech-debt --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"
  et="$(gh issue list -R "$BOARD_REPO" --label env-tracker --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"

  wt="$LOCAL_REPO/.claude/worktrees/$name"
  if [ -e "$wt" ]; then
    if _wt_occupied "$wt"; then
      echo "$name: live daemon occupies $wt — not removing (retire it first)" >&2
      rm -rf "$tmp"; return 1
    fi
    git -C "$LOCAL_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$LOCAL_REPO" worktree prune
  # Same trust choreography as the PR path: bootstrap at the trusted base
  # branch, then move to the integration ref under review.
  if [ -n "${WORKTREE_BOOTSTRAP_CMD:-}" ]; then
    git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "origin/$base_ref" \
      || { echo "$name: worktree add failed (origin/$base_ref)" >&2; rm -rf "$tmp"; return 1; }
    _bootstrap_worktree "$wt" "$name"
    git -C "$wt" checkout -q --detach "origin/$int_ref" \
      || { echo "$name: checkout of origin/$int_ref failed" >&2; rm -rf "$tmp"; return 1; }
  else
    git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "origin/$int_ref" \
      || { echo "$name: worktree add failed (origin/$int_ref)" >&2; rm -rf "$tmp"; return 1; }
  fi

  control_dir="$(mktemp -d "$DAEMON_HOME/$name-control.XXXXXX")" \
    || { echo "$name: control dir allocation failed" >&2; rm -rf "$tmp"; return 1; }
  bind_ready="$control_dir/bind-ready.json"
  ledger="$control_dir/accepted-commits.json"
  if ! chmod 700 "$control_dir" \
    || ! printf '{"push_base":"","commits":{}}\n' > "$ledger" \
    || ! chmod 600 "$ledger"; then
    echo "$name: control state initialization failed" >&2
    rm -rf "$tmp" "$control_dir"
    return 1
  fi

  # No PR bindings at all: the mode:scale template blocks carry no
  # {{PR_NUMBER}}/{{PR_URL}}/{{HEAD_*}} slot to fill.
  prompt="$(P_REVIEW_MODE="scale" P_CLOSURE_PACKAGE="$pkg" \
    P_REPO="$BOARD_REPO" P_BASE_REF="$base_ref" \
    P_WORKER_NAME="$name" P_INTEGRATION_REF="$int_ref" \
    P_SCALE_RANGE_NOTE="$range_note" \
    P_ISSUE_NUMBER="$etid" P_ISSUE_LIST="$etid" \
    P_TECH_DEBT_ISSUE="${td:-none}" \
    P_ENV_TRACKER_ISSUE="${et:-none}" \
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" P_AUTO_MERGE="$AUTO_MERGE_DISPLAY" \
    P_MANIFEST_REF="$base_ref" \
    P_BIND_READY_FILE="$bind_ready" P_SKILL_FILE="$SKILL_DIR/SKILL.md" \
    P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/executing/SKILL.md" \
    P_ENGINE_NAME="$engine" P_CODEX_REVIEW_MODEL="$CODEX_REVIEW_MODEL" \
    P_CODEX_REVIEW_EFFORT="$CODEX_REVIEW_EFFORT" P_REVIEW_ENGINE="$REVIEW_ENGINE" \
    RISK_FILE="$tmp/risk.md" FACTS_FILE="$tmp/facts.md" \
    _render_prompt)" \
    || { echo "$name: prompt render failed" >&2; rm -rf "$tmp" "$control_dir"; return 1; }
  rm -rf "$tmp"
  [ -n "$prompt" ] || { echo "$name: empty prompt — not dispatching" >&2; rm -rf "$control_dir"; return 1; }

  _spawn_reviewer "$name" "$etid" "$prompt" "$wt" "$engine" "$control_dir" || return 1
  # Stamp WHICH closure package this reviewer was dispatched against. That
  # stamp is what lets the next recomposition cycle tell a superseded
  # reviewer from a current one (see sweep_epic). Non-fatal: an unstamped
  # meta reads as superseded, which costs one redundant re-review — never a
  # stranded epic.
  _stamp_meta "$REVIEWER_UUID" closure_package "$pkg" \
    || echo "$name: closure-package stamp failed (non-fatal)" >&2
}

# ---- shared worker plumbing (both review variants) -----------------------------
# Normalize lingering finished owners of ticket <1> BEFORE binding:
# a claude-species worker has no self-finalizer,
# so its meta lingers status=working after its turn ends and board-bind
# protects it as a stable ACTIVE owner — which blocked the reviewer's bind
# and retired three reviewers in the 2026-07-18 live shakedown. finalize
# settles the truth (a genuinely live owner stays live and bind still
# refuses — correctly). The scale variant needs it just as much: the epic's
# outgoing owner is the Architect that assembled the closure package.
_finalize_ticket_owners() {  # <ticket>
  local owner
  while IFS= read -r owner; do
    [ -n "$owner" ] || continue
    "$SMINOS_CLI" sync "$owner" >/dev/null 2>&1 || true
  done <<EOF2
$(DAEMON_HOME="$DAEMON_HOME" T_ISSUE="$1" python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if str(m.get("ticket", "")).lstrip("#") == os.environ["T_ISSUE"] \
            and m.get("status") in ("working", "blocked"):
        print(m.get("uuid", ""))
PY
)
EOF2
}

# Bootstrap render: every P_* var in the environment fills the matching
# {{PLACEHOLDER}}, plus the two BASE-ref manifest snapshots (capped, with
# their absent-file fallbacks). A placeholder no call site supplies is a HARD
# ERROR, never a prompt shipped with a hole in it (execute-dispatch's
# _render_bootstrap has always worked this way): rendered as a blank it reads
# to the worker as "bound to nothing", and no downstream assertion can tell
# that apart from a value that is empty by design. The check runs over the
# mode-stripped TEMPLATE, not the output — the manifest snapshots and any other
# injected content are data, and a `{{...}}` inside them is not an unfilled slot.
#
# The template also carries `<!-- mode:X -->…<!-- /mode:X -->` blocks: the
# block whose X is this run's P_REVIEW_MODE survives, every other block is
# dropped whole. That is how one template serves both variants without
# either worker reading the other's framing — a scale reviewer is never
# told it has a PR, and a PR reviewer never sees scale prose. Both modes'
# wording stays here in the reference file where it is reviewable, rather
# than moving into the dispatcher.
_render_prompt() {  # P_* + RISK_FILE/FACTS_FILE in the environment
  python3 - "$BOOTSTRAP_TEMPLATE" <<'PY'
import os, re, sys
CAP = 20000  # keep the spawn arg well under the OS arg-size limit
def readcap(path):
    t = open(path).read()
    if len(t) > CAP:
        t = t[:CAP] + "\n[... truncated for dispatch — read the rest on GitHub]"
    return t
t = open(sys.argv[1]).read()
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
mode = subs.get("REVIEW_MODE", "pr")
t = re.sub(r"<!-- mode:([\w-]+) -->\n(.*?)<!-- /mode:\1 -->\n",
           lambda m: m.group(2) if m.group(1) == mode else "", t, flags=re.S)
subs["RISK_MANIFEST"] = readcap(os.environ["RISK_FILE"]) or \
    "(no repo risk-surface manifest at .doperpowers/risk-surfaces.md — the always-on categories are the only risk surfaces)"
subs["REPO_FACTS"] = readcap(os.environ["FACTS_FILE"]) or \
    "(no repo-facts manifest at .doperpowers/repo-facts.md — no declared validation commands or evidence add-ons to cross-check against)"
missing = sorted(n for n in set(re.findall(r"\{\{(\w+)\}\}", t)) if n not in subs)
if missing:
    sys.stderr.write("unrendered placeholders: %s\n" % " ".join(missing))
    sys.exit(1)
print(re.sub(r"\{\{(\w+)\}\}", lambda m: subs[m.group(1)], t))
PY
}

# Spawn tail shared by both variants: spawn → parse identity → bind the
# ticket → publish the startup barrier → wait for the worker's ack. Every
# failure retires the worker and removes the control dir, leaving the
# barrier closed; the caller's own guards handle everything before this.
# On success the spawned identity is left in REVIEWER_UUID for callers that
# stamp their own bookkeeping onto the fresh meta.
_spawn_reviewer() {  # <name> <ticket|""> <prompt> <worktree> <engine> <control-dir> [worktree-name]
  local name="$1" issue="$2" prompt="$3" wt="$4" engine="$5" control_dir="$6"
  # gh mode hands `sminos spawn` a cwd it prepared itself (the detached PR/epic
  # worktree) and no worktree NAME, so the seat runs right there. The API
  # path has no PR to detach at — it hands over the repo and lets `sminos spawn`
  # cut the isolated worktree, which is the same shape execute-dispatch uses.
  local wt_name="${7:-}"
  local bind_ready="$control_dir/bind-ready.json"
  local ledger="$control_dir/accepted-commits.json"
  local spawn_out uuid ack
  REVIEWER_UUID=""
  # Both spawns below carry `--role QAGENT`, which is the seat's honest role in
  # every fleet view from birth. Provenance is a different question and a
  # different field: `board_dispatch` is what the client reads to refuse a
  # dispatched reviewer whose bind never landed rather than let it write as the
  # operator (dp#35), and `role` cannot serve — `sminos join` takes whatever a
  # human types and a re-fill preserves it. The nonce comes off the journal path
  # the api caller set; gh mode has no claim and says `true`.
  # ATOMIC WITH THE RECORD, not a write after it. `--stamp` merges into the
  # launch dict, so provenance is on the record's very FIRST write: a separate
  # `meta set` never runs when `sminos spawn` times out polling the session uuid
  # (up to 60s) or the caller dies inside that poll, and a marker that can go
  # missing is a marker that fails open — the worker would be live, unbound, and
  # taken for an operator's own seat.
  local dispatch_mark
  dispatch_mark="$([ -n "${CLAIM_JOURNAL:-}" ] && basename "$CLAIM_JOURNAL" .json || echo true)"

  # ONE worker harness, two model routes. The default "claude" engine is a
  # plain Claude-model daemon. engine:codex opts a PR into the GATEWAY
  # route: the same Claude-harness daemon pointed at the local gateway (GPT
  # models) via --settings — the codex CLI survives only as the review
  # engine inside the worker. The codex-CLI-as-worker species is retired.
  if [ "$engine" = "codex" ]; then
    spawn_out="$(DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" \
      DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" \
      "$SMINOS_CLI" spawn "$name" "$prompt" --cwd "$wt" --worktree "$wt_name" \
      --model "${REVIEW_MODEL:-fable}" --role QAGENT \
      --stamp "board_dispatch=$dispatch_mark")" \
      || { echo "$name: Reviewer worker spawn failed" >&2; rm -rf "$control_dir"; return 1; }
  else
    # The QAgent tier is opus/high by design — pinned, not inherited, so the
    # operator's own session model never silently sets the review lane's
    # price. `sminos spawn` persists effort into the record; resumes keep it.
    # The gateway settings are CLEARED, not merely unset by us: this
    # dispatcher can itself run inside a gateway-routed seat whose
    # environment exports them, `sminos spawn` would inherit and persist them,
    # and every later resume would ride the gateway while the log said claude.
    spawn_out="$(DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT="${REVIEW_EFFORT:-high}" \
      "$SMINOS_CLI" spawn "$name" "$prompt" --cwd "$wt" --worktree "$wt_name" \
      --model "${REVIEW_MODEL:-opus}" --role QAGENT \
      --stamp "board_dispatch=$dispatch_mark")" \
      || { echo "$name: Reviewer worker spawn failed" >&2; rm -rf "$control_dir"; return 1; }
  fi
  printf '%s\n' "$spawn_out"
  uuid="$(printf '%s\n' "$spawn_out" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
  REVIEWER_UUID="$uuid"

  # The worker's first protocol action waits on bind_ready. Publish it only
  # after the new registry meta exists and (for ticketed work) board-bind has
  # stripped every old owner and bound THIS reviewer. Thus spawn-before-bind
  # cannot race into review work, and any failure leaves the barrier closed.
  local bound="" attempts="${REVIEW_BIND_ATTEMPTS:-3}"
  if [ -z "$uuid" ]; then
    echo "$name: spawned reviewer UUID was not parseable — startup barrier stays closed" >&2
    rm -rf "$control_dir"
    return 1
  fi
  if [ -n "$issue" ]; then
    local try=1
    while [ "$try" -le "$attempts" ]; do
      if "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$issue"; then bound=1; break; fi
      [ "$try" -lt "$attempts" ] && sleep "${REVIEW_BIND_DELAY:-2}"
      try=$((try + 1))
    done
    if [ -z "$bound" ]; then
      _retire "$uuid"
      rm -rf "$control_dir"
      echo "$name: bind to ticket #$issue failed after $attempts attempt(s) — Reviewer worker retired (a parked reviewer must be resumable via board-answer)" >&2
      return 1
    fi
    # Persist role: QAGENT into the registry meta. board-answer.sh's
    # needs-human fallback (no recorded pre-park:) reads it back to return
    # this park to in-review — a reviewer resumed into in-progress owns no
    # implementation branch and has no legal exit. Non-fatal: metas written
    # before this stamp are still recognized by board-answer's review-pr-* /
    # review-epic-* name inference.
    #
    # GH MODE ONLY — this tail is shared with the api claim path, which stamps
    # role itself (alongside lane and nonce) in the one write that also has to
    # hold the run bearer's 0600. Two stamps racing that file buys nothing and
    # risks the mode. CLAIM_JOURNAL is this file's gh/api discriminator.
    if [ -z "${CLAIM_JOURNAL:-}" ]; then
      _stamp_meta "$uuid" role QAGENT \
        || echo "$name: role meta write failed (non-fatal)" >&2
    fi
  fi
  if ! READY="$bind_ready" LEDGER="$ledger" UUID="$uuid" TICKET="${issue:-none}" python3 - <<'PY'
import json, os
ready = os.environ["READY"]
tmp = ready + ".tmp"
with open(tmp, "w") as f:
    json.dump({"uuid": os.environ["UUID"], "ticket": os.environ["TICKET"],
               "ledger": os.environ["LEDGER"]}, f, indent=2)
os.chmod(tmp, 0o600)
os.replace(tmp, ready)
PY
  then
    _retire "$uuid"
    rm -rf "$control_dir"
    echo "$name: could not publish startup barrier — Reviewer worker retired" >&2
    return 1
  fi

  # Success means the worker actually crossed the barrier, not merely that the
  # dispatcher published it. A model/auth failure or worker-side timeout never
  # becomes an ordinary "finished" review that sweep would skip.
  ack="$bind_ready.ack"
  local poll=0 max_polls="${REVIEW_ACK_POLLS:-600}"
  while [ ! -f "$ack" ] && [ "$poll" -lt "$max_polls" ]; do
    sleep "${REVIEW_ACK_DELAY:-0.2}"
    poll=$((poll + 1))
  done
  if [ ! -f "$ack" ] || ! ACK="$ack" UUID="$uuid" python3 - <<'PY'
import json, os, sys
try:
    data = json.load(open(os.environ["ACK"]))
except Exception:
    sys.exit(1)
sys.exit(0 if data.get("uuid") == os.environ["UUID"] else 1)
PY
  then
    _retire "$uuid"
    rm -rf "$control_dir"
    echo "$name: worker did not acknowledge startup barrier — retired" >&2
    return 1
  fi

  # API mode only: THE HANDOFF IS DURABLE ONLY NOW — the bind landed, the
  # startup barrier is published, and the worker acknowledged crossing it.
  # Marked at the bind instead, a crash in the remaining window left a journal
  # saying "handed off" over a reviewer that can NEVER start: its barrier wait
  # is 120 seconds and then it ends without reviewing, so the session goes idle
  # still holding the run, the tick renews that lease forever, and the ticket
  # is owned by nobody who will work it. (Marking it earlier still — ahead of
  # the bind — was the original bug, and left the same journal over a meta with
  # no run credential at all.) The crash window this ordering opens, a bound
  # meta under an unmarked journal, is reconciliation's `stranded` arm: the
  # control dir travels in the journal so that arm can tell a reviewer that
  # crossed the barrier from one that never could. Unset in gh mode, where no
  # claim journal exists at all.
  [ -z "${CLAIM_JOURNAL:-}" ] || _api_mark_spawned
}

# Consecutive FAILED reviewers for worker name <1>, newest first: a reply carrying the
# ENGINE-UNAVAILABLE marker (engine outage), a turn finalized status=error
# (dead worker — e.g. the gateway refused its first turn, so no reply exists
# to carry any marker), or a retirement STAMPED as a failure one
# (_retire_failed — `sminos retire` overwrites the terminal status, and without
# the stamp a dead-worker cycle erased the very evidence of itself and the
# streak never reached the cap). One shared streak, so interleaved failure
# kinds don't reset the count; the sweep's cap reads it so neither a dead
# engine nor a dead gateway can make the cron respawn forever. Any cleanly
# finished reviewer breaks the streak — as does an UNSTAMPED retirement (a
# superseded reviewer, a stale-ticket cleanup), which is not a failure.
#
# COUNTING RECORDS ALONE UNDERCOUNTS. A seat keeps ONE record per alias across
# re-fills, retiring each previous occupant into `history[]` rather than
# leaving a record behind, so three failed reviewers on one PR are one row and
# the 3-consecutive cap would never be reached. A seat therefore contributes
# its own trailing failure run: itself, plus the history entries behind it,
# stopping at the first occupant that did NOT fail. Lifetime fill count is the
# wrong number — a seat re-filled twice cleanly and failing once has failed
# ONCE, and capping it at three would retire a healthy PR. Rows and seat runs
# are then combined with max(), so a pre-seat registry (a record per turn)
# reads exactly as it did before.
#
# A RETIREMENT ERASES THE STATUS IT REPLACED. `sminos retire` writes
# status=retired over whatever terminal status the failure left, so a failed
# occupant reads `retired` once it has been retired into history — which is
# why _retire_failed stamps `retired_from: failure` first. The stamp is the
# durable evidence, on history entries exactly as on records: read it too, or
# the streak forgets every failure the moment its occupant is retired, and the
# cap becomes unreachable for the dead-worker cycle it exists for.
_outage_streak() {
  DAEMON_HOME="$DAEMON_HOME" WNAME="$1" python3 - <<'PY'
import glob, json, os
home = os.environ["DAEMON_HOME"]; name = os.environ["WNAME"]
rows = []
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("name") == name:
        hist = m.get("history")
        rows.append((str(m.get("updated") or m.get("created") or ""),
                     m.get("uuid") or "", str(m.get("status") or ""),
                     str(m.get("retired_from") or ""),
                     hist if isinstance(hist, list) else []))
rows.sort(reverse=True)
FAILED = ("error", "failed")
def failed(status, retired_from):
    return str(status or "") in FAILED or str(retired_from or "") == "failure"
def past_failures(hist):
    """Trailing failed occupants of a re-filled seat, newest first."""
    n = 0
    for h in reversed(hist):
        if not isinstance(h, dict) \
                or not failed(h.get("status"), h.get("retired_from")):
            break
        n += 1
    return n
records = 0
occupants = 0
for _, uuid, status, retired_from, hist in rows:
    try:
        lines = open(os.path.join(home, uuid + ".reply.txt")).read().splitlines()
    except Exception:
        lines = None
    if (lines is not None and "ENGINE-UNAVAILABLE" in lines) \
            or failed(status, retired_from) \
            or (status == "retired" and retired_from):
        records += 1
        occupants += 1 + past_failures(hist)
    else:
        break
print(max(records, occupants))
PY
}

# Verdict for a FINISHED reviewer named <1>, uuid <2>, mode <3>, status <4>.
# Triggered mode always re-dispatches (explicit event = fresh signal). Sweep
# mode retries two failure kinds: an engine outage — the worker marks it with
# a final-message marker line (fallback block) — and a turn that finalized
# status=error, where the WORKER died (a pre-first-turn gateway refusal
# leaves no reply, so no marker can exist). Both share the 3-consecutive
# failed-reviewer cap per PR; anything else finished stays finished.
_finished_verdict() {
  local name="$1" uuid="$2" mode="$3" status="$4"
  # A triggered re-review REPLACES a cleanly finished reviewer — an explicit
  # PR event, not a failure. It gets its own verdict so the retire that
  # follows carries no failure stamp: two ordinary re-reviews plus one real
  # outage must not reach the 3-consecutive cap.
  if [ "$mode" = "triggered" ]; then echo "respawn-clean $uuid"
  elif [ "$status" = "error" ] \
    || grep -qx 'ENGINE-UNAVAILABLE' "$DAEMON_HOME/$uuid.reply.txt" 2>/dev/null; then
    if [ "$(_outage_streak "$name")" -ge 3 ]; then
      echo "skip outage/dead-worker failure persists (3 consecutive reviewers — an explicit PR event re-dispatches)"
    else
      echo "respawn $uuid"
    fi
  else echo "skip finished reviewer ($status)"; fi
}

# Dedupe verdict for worker name <1> in mode <2> (triggered|sweep).
# Prints: "dispatch" | "respawn <uuid>" (a FAILED reviewer is being
# replaced — the retire is stamped) | "respawn-clean <uuid>" (an explicit
# event replacing a finished one — unstamped) | "skip <why>".
_decide() {
  local name="$1" mode="$2" meta uuid status current rest engine pid whost wboot fin
  meta="$(_reviewer_meta "$name")"
  if [ -z "$meta" ]; then echo "dispatch"; return; fi
  uuid="${meta%%|*}"; rest="${meta#*|}"; status="${rest%%|*}"; rest="${rest#*|}"
  current="${rest%%|*}"; rest="${rest#*|}"; engine="${rest%%|*}"; rest="${rest#*|}"
  pid="${rest%%|*}"; rest="${rest#*|}"; whost="${rest%%|*}"; wboot="${rest#*|}"
  case "$status" in
    working|blocked)
      if [ "$engine" = "codex" ]; then
        # legacy codex-CLI metas: pid liveness (read path kept for old entries)
        if _is_live "$current" "$engine" "$pid" "$whost" "$wboot"; then echo "skip active reviewer"; else echo "respawn $uuid"; fi
      elif ! _identity_local "$whost" "$wboot"; then
        echo "respawn $uuid"    # foreign-host meta: only the registry migrated
      else
        # A --no-wait worker's meta stays status=working after its turn ends,
        # and finished --bg sessions stay LISTED in `claude agents` — presence
        # is not liveness. Sync first (records reply + terminal status),
        # then judge: live → skip; finished → the finished-reviewer verdict;
        # session gone → dead worker → respawn.
        fin="$("$SMINOS_CLI" sync "$uuid" 2>/dev/null || echo "")"
        case "$fin" in
          live)       echo "skip active reviewer" ;;
          idle|error) _finished_verdict "$name" "$uuid" "$mode" "$fin" ;;
          noop)       echo "skip finished reviewer (raced sync)" ;;
          *)          echo "respawn $uuid" ;;
        esac
      fi ;;
    retired) echo "dispatch" ;;
    *) _finished_verdict "$name" "$uuid" "$mode" "$status" ;;
  esac
}

# $3/$4 (sweep mode only): the primary ticket's off-review status name
# (e.g. "ready-for-architect", "needs-human") and its number, when the
# sweep already resolved the ticket is NOT in-review. Empty $3 means
# in-review, ticketless, or triggered mode — never gated, same as before.
#
# A reviewer bound to a ticket that has left in-review is stale by
# definition (header comment). $verdict from the ordinary dedupe machinery
# already tells us everything needed to act on that: "skip active
# reviewer" means a live session is mid-turn and owns its own exit (never
# touched); anything else — dispatch, respawn
# <uuid>, or any other "skip ..." — means at most a NON-live reviewer meta
# is on file, so it's retired here instead of being left to strand the
# ticket's next return to in-review behind "skip finished reviewer"
# forever.
run_for() {  # $1=pr $2=mode $3=off-review-status $4=ticket-number
  local pr="$1" mode="$2" stale="${3:-}" tid="${4:-}" verdict resume
  verdict="$(_decide "review-pr-$pr" "$mode")"
  if [ -n "$stale" ]; then
    case "$verdict" in
      "skip active reviewer")
        echo "#$pr: skip — primary ticket #$tid is status:$stale, not in-review; its still-active reviewer owns its own exit"
        return ;;
    esac
    if [ "$stale" = "needs-human" ]; then
      # NOT stale: this is the resumable park. board-answer.sh relays to the
      # BOUND session and accepts only an idle/awaiting-human one, so retiring
      # the finalized meta here would break the wake path the park's own note
      # promises. The meta is the park's wake target — leave it exactly alone.
      # (needs-human is the whole set: board-answer refuses every other park
      # state by name, so no other park has a session-resume path to protect.)
      echo "#$pr: skip — primary ticket #$tid is parked needs-human; its reviewer meta is the park's wake target (board-answer resumes it), left intact"
      return
    fi
    local m
    m="$(_reviewer_meta "review-pr-$pr")"
    [ -n "$m" ] && _retire "${m%%|*}"
    case "$stale" in
      closed)
        echo "#$pr: skip — primary ticket #$tid is CLOSED (terminal); nothing to review against"
        return ;;
      conflict*)
        # Off-machine, not parked: two or more status labels. board-lint
        # names it and board-transition repairs it; nothing here should bind
        # a reviewer to a ticket whose state is undecided.
        echo "#$pr: skip — primary ticket #$tid carries multiple status labels ($stale); repair it (board-lint.sh names the fix) before a reviewer binds"
        return ;;
      needs-info|interactive-preferred|deferred)
        # board-answer relays needs-human parks ONLY (it dies on these by
        # name), so there is no bound-session wake here — the ticket returns
        # to in-review by hand, and a fresh reviewer goes out then.
        resume="it resumes when the ticket returns to in-review — board-answer relays needs-human parks only" ;;
      *)
        resume="resumes when the ticket returns to in-review, not from here" ;;
    esac
    echo "#$pr: skip — primary ticket #$tid is parked (status:$stale); $resume"
    return
  fi
  case "$verdict" in
    dispatch|respawn\ *|respawn-clean\ *)
      if [ "$mode" = "sweep" ] && [ "$(_gh_review_slots)" -ge "$REVIEW_CAP" ]; then
        echo "#$pr: review cap reached ($REVIEW_CAP live) — queued for a later tick"
        return 0
      fi ;;
  esac
  case "$verdict" in
    dispatch)  dispatch_one "$1" "$2" ;;
    respawn\ *)       _retire_failed "${verdict#respawn }"; dispatch_one "$1" "$2" ;;
    respawn-clean\ *) _retire "${verdict#respawn-clean }"; dispatch_one "$1" "$2" ;;
    *)         echo "#$1: $verdict" ;;
  esac
}

# Registry-driven cleanup for a reviewer whose WORK OBJECT is gone — an epic
# that left in-review, or a PR that left the open listing. Neither is visible
# to any dispatch path (the listings enumerate live work only) and
# board-sweep's pass_cancel deliberately skips reviewer metas, so nothing else
# would ever finalize one. Its meta lingers `working` and keeps OWNING the
# ticket: execute-dispatch's _bound_meta refuses to dispatch a ticket with a
# bound working worker, and _slots_used charges it to a lane. Same rule as
# everywhere else — a live reviewer owns its own exit and is untouched; a
# finished one is finalized (that is what _decide does before judging it) and
# retired, unstamped: this is not a failure, so it must not feed the streak.
_cleanup_orphaned_reviewer() {  # <worker-name> <why>
  local name="$1" why="$2" verdict meta
  verdict="$(_decide "$name" sweep)"
  if [ "$verdict" = "skip active reviewer" ]; then
    echo "$name: skip — $why; its still-active reviewer owns its own exit"
    return
  fi
  meta="$(_reviewer_meta "$name")"
  [ -n "$meta" ] || return
  _retire "${meta%%|*}"
  echo "$name: reviewer ${meta%%|*} retired — $why"
}

# One in-review epic's dedupe → dispatch decision, isolated per epic exactly
# as run_for isolates a PR (the sweep runs it behind `||`).
#
# An epic is reviewed once PER RECOMPOSITION CYCLE, and there can be many:
# a defect becomes a corrective child, the epic leaves in-review, the child
# lands, the Architect pins a NEW closure package and the epic returns. Board
# state alone cannot dedupe that — the first reviewer's meta stays on file
# with a terminal status forever (the stale-reviewer pass at the bottom of
# --sweep retires a reviewer whose epic LEFT in-review, but this is the
# opposite case: the epic came back), so every
# cycle after the first would hit "skip finished reviewer" and strand. The
# discriminator is the closure package each reviewer was dispatched against,
# stamped into its meta: a finished reviewer whose stamp no longer matches
# the ticket reviewed a PREVIOUS cycle and is retired here. A missing stamp
# counts as superseded — costing one redundant review, never a strand.
# An ACTIVE reviewer is never touched: it owns its own exit, and its package
# is the current one by construction.
sweep_epic() {  # $1=epic $2=closure-package $3=integration-branch $4=engine-label $5=child pull numbers
  local etid="$1" pkg="$2" verdict meta uuid
  verdict="$(_decide "review-epic-$etid" sweep)"
  case "$verdict" in
    dispatch)   dispatch_epic "$@"; return ;;
    respawn\ *)       _retire_failed "${verdict#respawn }"; dispatch_epic "$@"; return ;;
    respawn-clean\ *) _retire "${verdict#respawn-clean }"; dispatch_epic "$@"; return ;;
    "skip active reviewer") echo "epic #$etid: $verdict"; return ;;
  esac
  # Every remaining verdict means a NON-live reviewer meta is on file and
  # _decide has already finalized it.
  meta="$(_reviewer_meta "review-epic-$etid")"
  uuid="${meta%%|*}"
  if [ -n "$uuid" ] && [ "$(_meta_field "$uuid" closure_package)" != "$pkg" ]; then
    _retire "$uuid"
    echo "epic #$etid: superseded reviewer $uuid retired — new closure package, new recomposition cycle"
    dispatch_epic "$@"
    return
  fi
  # The 3-consecutive-failure cap is PERMANENT on the PR path because an
  # explicit PR event can always re-dispatch. A scale review is sweep-only:
  # no event exists, so a capped epic would sit unreviewed forever with an
  # unchanged closure package. Escalate to the human instead — retire the
  # last failed reviewer and park the epic. The park is self-limiting (a
  # parked epic leaves the in-review sweep list, so this fires once).
  #
  # The note carries the RECIPE, not just the situation. This park has no
  # resumable session behind it — we just retired the reviewer — and
  # board-answer.sh refuses a dead or retired bound session by design, so
  # "answer it" alone would send the human down a path that dies. The
  # documented fallback is the two-step one below; the board-transition it
  # names needs no --pr because entering needs-human from in-review recorded
  # `pre-park: in-review`, which is exactly the case the in-review gate lets
  # reuse the epic's recorded closure package.
  case "$verdict" in
    "skip outage/dead-worker failure persists"*)
      [ -n "$uuid" ] && _retire_failed "$uuid"
      if "$BOARD_SCRIPTS/board-transition.sh" "$etid" needs-human \
        "scale review: the review engine was unavailable on 3 consecutive attempts; this reviewer was retired, so there is no session to resume — reply on this ticket, then run board-transition.sh $etid in-review (no --pr needed) and the next sweep dispatches a fresh reviewer"; then
        echo "epic #$etid: review engine unavailable 3 consecutive attempts — reviewer $uuid retired and the epic parked needs-human"
      else
        echo "epic #$etid: outage cap reached but the needs-human park FAILED — the epic stays in-review" >&2
      fi
      return ;;
  esac
  echo "epic #$etid: $verdict"
}

# ---- API binding: claim-based qagent dispatch ----------------------------------
# The SERVER owns pick order, eligibility and the lease; this side owns local
# concurrency, the crash-recoverable claim journal, and the worker handover.
# There is no PR listing here, no board snapshot, and no gh call anywhere below:
# the review lane is drawn one ticket at a time out of `POST /runs/claim`.
#
# The journal and its reconciliation ARE execute-dispatch's — they were
# verbatim copies, and _claim_journal.sh now owns both. This side supplies the
# lane, its cap and the journal-drop.
CLAIM_LANES=qagent
_claim_lane_cap() { : "$1"; echo "$REVIEW_CAP"; }
_claim_drop_journal() { _api_drop_journal "$1"; }
# NOT `_retire`, which is best-effort by design for this file's own callers:
# the reconciler's orphan arm ends a run only when the worker it belongs to is
# actually stopped, so this one reports the CLI's status.
_claim_retire_worker() { "$SMINOS_CLI" retire "$1" >/dev/null 2>&1; }
# shellcheck source=../../issue-tracker/scripts/_claim_journal.sh
. "$BOARD_SCRIPTS/_claim_journal.sh"

# The sweep's tick deadline, when it set one. A single budget check ahead of
# the whole dispatch phase admitted this lane in full — including a startup
# barrier wait of up to REVIEW_ACK_POLLS x REVIEW_ACK_DELAY per candidate —
# inside the sweep's global lock, so a tick with one second left could spend
# minutes more. Checked before each FRESH claim; a replay from reconciliation
# is recovery, not new work, and is never gated. Absent or unparseable = no
# gate: a direct --sweep and the by-name `dispatch` phase are their own tick
# with their own clock.
_tick_deadline_left() {
  case "${BOARD_TICK_DEADLINE:-}" in ''|*[!0-9]*) return 0 ;; esac
  [ "$(date +%s)" -lt "$BOARD_TICK_DEADLINE" ]
}

# Open workers in a lane, counted off the registry: the local cap. A
# just-claimed worker's meta exists long before the board could show its first
# write, which is the same window gh mode's registry-first dedupe closes.
_api_registry_count() {  # <lane[,lane...]>
  T_DHOME="$DAEMON_HOME" T_LANES="$1" _api_py - <<'PY'
import glob, json, os
import _board_api as A
lanes = set(os.environ["T_LANES"].split(","))
MINE = (A.board_key(), A.repo())
n = 0
for p in glob.glob(os.path.join(os.environ["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    # A SLOT IS THIS REPO'S TO SPEND. The registry is machine-global, so a
    # neighbouring api-bound repo's open worker in the same lane read as one of
    # ours: at cap 1 this checkout saw its lane full and fell through to the
    # next lane, dispatching its own ticket to the wrong role and model.
    if not A.meta_is_mine(m, *MINE):
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
_api_suppress_dir() { echo "${BOARD_SUPPRESS_DIR:-$DAEMON_HOME/board-suppress}"; }
_api_suppressed() { [ -f "$(_api_suppress_dir)/$1.json" ]; }

# The same sweep's resume phase records every ticket it already attempted a
# recovery for THIS TICK. A replay that faulted leaves its ticket unowned, so
# the server can hand it to an ordinary lane claim moments later — a second
# attempt inside the one tick the ledger holds to one. Absent (a dispatcher run
# by hand, a phase asked for by name) it fences nothing.
_api_tick_ledgered() {
  [ -n "${BOARD_RESUMED_LEDGER:-}" ] && [ -f "$BOARD_RESUMED_LEDGER" ] \
    && grep -qxF -- "$1" "$BOARD_RESUMED_LEDGER"
}

# A delivered recovery is a recovery, whichever phase delivered it: the failed
# cycle count is the sweep's ladder to an env-issue escalation, and a count
# left standing after a successful dispatch escalates a much later, unrelated
# fault two rungs early. Cleared ONE LINE AHEAD of the journal's durable mark
# (_api_mark_spawned), so the only crash that can skip it is the one
# reconciliation still sees (`repaired`), which clears it there.
_api_attempts_clear() { rm -f "$(_api_suppress_dir)/.attempts-$1"; }
_claim_suppress_dir() { _api_suppress_dir; }

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

# The handoff is done: the journal may no longer be replayed, only observed.
# Called from the END of _spawn_reviewer, once the handoff is durable.
_api_mark_spawned() {
  [ -z "${CLAIM_TICKET:-}" ] || _api_attempts_clear "$CLAIM_TICKET"
  _journal_write "$CLAIM_JOURNAL" "$CLAIM_LANE" "$CLAIM_RUN" 1 \
    "${CLAIM_TICKET:-}" "${CLAIM_DAEMON:-}" "${CLAIM_CONTROL:-}"
}

_api_drop_journal() {  # <nonce>
  rm -f "$DAEMON_HOME/board-claims/$1.json" "$DAEMON_HOME/board-claims/$1.body.md"
}

# Claim one ticket on the qagent lane under <nonce> and hand it to a fresh
# Reviewer worker. The return contract is the implement dispatcher's, verbatim —
# one shared function name, one shared meaning:
#   rc 0  claimed and handed off
#   rc 1  nothing dispatched and NOTHING IS OUTSTANDING — the lane was empty,
#         the claim was refused, the ticket is suppressed, or the handover
#         failed and its run was released.
#   rc 2  the claim may have LANDED and its journal is kept for replay. No
#         further claim may be made this tick; reconciliation owns the replay.
# This lane has no sibling to fall through to, so its loop stops on either.
_claim_one_with_nonce() {  # <lane> <nonce> <lane-cap>
  local lane="$1" nonce="$2" cap="$3" claims_dir="$DAEMON_HOME/board-claims"
  local body_file="$claims_dir/$nonce.body.md" exports
  mkdir -p "$claims_dir"
  # The nonce is journalled BEFORE the POST. A crash between the two leaves a
  # record reconciliation can replay, and the server answers a repeated nonce
  # with the same claim rather than a second one.
  _journal_write "$claims_dir/$nonce.json" "$lane" '' 0
  # One process for the whole exchange: claim, write the assignment body, hand
  # back shell-quoted facts. The run bearer crosses exactly one boundary.
  local C_CLAIMED=0 C_RUN_ID="" C_TICKET="" C_FENCE="" C_BEARER="" C_PARENT_PIN=""
  local C_PR="" C_BRANCH=""
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
# The working bindings the variant split reads: for a leaf, the PR URL and its
# working branch; for an epic, the closure-package event id and the integration
# ref. The dispatcher is the only party that sees them.
q("C_PR", out.get("pr") or "")
q("C_BRANCH", out.get("branch") or "")
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
    # and the replay is the only thing that can recover it.
    echo "claim on lane $lane failed — journal $nonce kept for replay" >&2
    return 2
  }
  eval "$exports"
  if [ "$C_CLAIMED" != 1 ]; then
    _api_drop_journal "$nonce"
    return 1
  fi
  if _api_suppressed "$C_TICKET"; then
    echo "#$C_TICKET is suppressed — releasing run $C_RUN_ID; lane $lane stands down this tick"
    _api_end_run "$C_RUN_ID" abandoned
    _api_drop_journal "$nonce"
    return 1
  fi
  if _api_tick_ledgered "$C_TICKET"; then
    # Head-of-line, like suppression above: the server picks, so the only
    # refusal available is to hand the run straight back. The next tick serves
    # the ticket if it is still unowned.
    echo "#$C_TICKET already had its one recovery attempt this tick — releasing run $C_RUN_ID; lane $lane stands down this tick"
    _api_end_run "$C_RUN_ID" abandoned
    _api_drop_journal "$nonce"
    return 1
  fi
  local name engine tmp control_dir prompt
  name="$C_TICKET-api-$lane"
  # Ticket and daemon name are journalled BEFORE the spawn, not after it. The
  # run id reaches a registry meta only through board-bind, which runs at the
  # END of the handover — so a crash anywhere in the spawn (the uuid parse and
  # the worker's barrier ack are seconds to minutes wide, and the session is
  # already detached and surviving) leaves a journal with a run id that no meta
  # knows, indistinguishable from a run that never spawned at all. The daemon
  # name is the only evidence of that session that exists before the bind, and
  # reconciliation needs it to tell "never spawned" from "spawned, live,
  # unbound".
  _journal_write "$claims_dir/$nonce.json" "$lane" "$C_RUN_ID" 0 "$C_TICKET" "$name"
  # No labels reach a claim response, so the per-ticket engine override gh mode
  # reads off the ticket has no API-mode source; the environment is the whole
  # resolution order here.
  engine="${WORKER_ENGINE:-claude}"
  tmp="$(mktemp -d)"
  # Same manifest discipline as a PR review — a snapshot from outside the
  # reviewed work — but taken from the DEFAULT BRANCH, the only ref this
  # dispatcher can name (see the BASE_REF note below). MANIFEST_REF tells the
  # worker which ref these copies came from, so it can re-read them itself when
  # the PR's real base turns out to be a different branch.
  #
  # REFRESH THE TRACKING REF FIRST, as the PR path does before its own two
  # `git show` calls. Nothing else on this path fetches, so a clone whose
  # origin/<default> was stale — or, in a fresh clone, absent — handed the
  # worker an outdated or empty policy and then told it to KEEP these copies
  # whenever its resolved base matches MANIFEST_REF. Best-effort: the empty
  # snapshot below is the designed degradation and the worker's own PR fetch is
  # the hard gate, so a failure warns and dispatch continues. git only — this
  # dispatcher never invokes gh (see the BASE_REF note below).
  git -C "$LOCAL_REPO" fetch -q origin "$DEFAULT_BRANCH" 2>/dev/null \
    || echo "#$C_TICKET: could not fetch origin/$DEFAULT_BRANCH — the risk-surface and repo-facts snapshots are whatever this clone already held" >&2
  git -C "$LOCAL_REPO" show "origin/$DEFAULT_BRANCH:.doperpowers/risk-surfaces.md" > "$tmp/risk.md" 2>/dev/null \
    || : > "$tmp/risk.md"
  git -C "$LOCAL_REPO" show "origin/$DEFAULT_BRANCH:.doperpowers/repo-facts.md" > "$tmp/facts.md" 2>/dev/null \
    || : > "$tmp/facts.md"
  control_dir="$(mktemp -d "$DAEMON_HOME/$name-control.XXXXXX")" \
    || { echo "#$C_TICKET: control dir allocation failed — releasing run $C_RUN_ID" >&2
         rm -rf "$tmp"; _api_end_run "$C_RUN_ID" abandoned; _api_drop_journal "$nonce"; return 1; }
  if ! chmod 700 "$control_dir" \
    || ! printf '{"push_base":"","commits":{}}\n' > "$control_dir/accepted-commits.json" \
    || ! chmod 600 "$control_dir/accepted-commits.json"; then
    echo "#$C_TICKET: control state initialization failed — releasing run $C_RUN_ID" >&2
    rm -rf "$tmp" "$control_dir"; _api_end_run "$C_RUN_ID" abandoned
    _api_drop_journal "$nonce"; return 1
  fi
  # The control dir joins the journal BEFORE the spawn. After a crash between
  # the bind and the durable mark, the ack file inside it is the ONLY thing
  # that separates a reviewer which crossed the startup barrier from one
  # waiting on a barrier nobody will ever publish — see the `stranded` arm in
  # _claim_journal.sh, and the mark at the end of _spawn_reviewer.
  _journal_write "$claims_dir/$nonce.json" "$lane" "$C_RUN_ID" 0 "$C_TICKET" "$name" "$control_dir"

  # A PR's BASE_REF IS NOT KNOWABLE HERE, and saying `$DEFAULT_BRANCH` was not a
  # conservative default — it was a wrong answer. A claim carries no PR: the
  # ticket's `pr` value is read by the WORKER, and a ticket whose PR targets an
  # integration branch (a stacked PR) then had its engine run
  # `--base origin/<default>`, i.e. review its whole stack rather than its own
  # commits, against manifests from the wrong ref. Resolving it here would mean
  # a `gh` call, and this dispatcher deliberately never invokes gh — that is why
  # the binding is resolved ahead of the gh probe, so an api-bound board works
  # on a machine with no GitHub CLI at all. So the binding says UNRESOLVED and
  # the protocol makes the worker (which does have gh, and already resolves the
  # PR number and checks out its head) resolve base and head before ORIENT. The
  # sentinel is deliberately not a ref: a worker that skipped the step gets
  # `fatal: bad revision` from git, not a quietly wrong review range.
  #
  # THE VARIANT IS THE DISPATCHER'S CALL — it alone sees the claim response.
  # Shape, not Number(): the entry-edge guard (arkho#7) makes a leaf's `pr`
  # URL-shaped, so a URL is the PR variant and anything else non-empty is an
  # epic's closure-package event id — the scale variant, whose base IS the
  # default branch (what a recomposition epic merges into) and whose bindings
  # no board read hands over. THAT BASE IS RENDERED AS AN ECHO, NOT AN
  # AUTHORITY: DEFAULT_BRANCH is resolved here by a ladder that can settle on a
  # stale local origin/HEAD or, with no network, on the literal `main` — so the
  # api-scale protocol has the worker re-resolve it from `git ls-remote
  # --symref origin HEAD` and park when the remote will not answer. The
  # rendered value stays as context (and as MANIFEST_REF, the ref these
  # snapshots actually came from). An epic claim with no integration branch parks
  # via the worker (the api-scale block's empty-ref check), not here: the
  # dispatcher refusing to spawn would strand the ticket with no park note
  # naming the gap.
  local mode=api
  case "$C_PR" in
    http://*|https://*) mode=api ;;
    ?*) mode=api-scale ;;
  esac
  prompt="$(P_REVIEW_MODE="$mode" P_WORKER_NAME="$name" \
    P_CLOSURE_PACKAGE="$C_PR" P_INTEGRATION_REF="$C_BRANCH" \
    P_REPO="$BOARD_REPO" \
    P_BASE_REF="$([ "$mode" = api-scale ] && echo "$DEFAULT_BRANCH" || echo UNRESOLVED-resolve-from-the-PR)" \
    P_ISSUE_NUMBER="$C_TICKET" P_ISSUE_LIST="$C_TICKET" \
    P_TICKET_BODY_FILE="$body_file" \
    P_TECH_DEBT_ISSUE=none P_ENV_TRACKER_ISSUE=none \
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" P_AUTO_MERGE="$AUTO_MERGE_DISPLAY" \
    P_MANIFEST_REF="$DEFAULT_BRANCH" \
    P_BIND_READY_FILE="$control_dir/bind-ready.json" P_SKILL_FILE="$SKILL_DIR/SKILL.md" \
    P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/executing/SKILL.md" \
    P_ENGINE_NAME="$engine" P_CODEX_REVIEW_MODEL="$CODEX_REVIEW_MODEL" \
    P_CODEX_REVIEW_EFFORT="$CODEX_REVIEW_EFFORT" P_REVIEW_ENGINE="$REVIEW_ENGINE" \
    RISK_FILE="$tmp/risk.md" FACTS_FILE="$tmp/facts.md" \
    _render_prompt)" \
    || { echo "#$C_TICKET: prompt render failed — releasing run $C_RUN_ID" >&2
         rm -rf "$tmp" "$control_dir"; _api_end_run "$C_RUN_ID" abandoned
         _api_drop_journal "$nonce"; return 1; }
  rm -rf "$tmp"
  [ -n "$prompt" ] || { echo "#$C_TICKET: empty prompt — releasing run $C_RUN_ID" >&2
                        rm -rf "$control_dir"; _api_end_run "$C_RUN_ID" abandoned
                        _api_drop_journal "$nonce"; return 1; }

  # The run credentials are exported ONLY across this call: `sminos spawn` puts
  # them in the worker's environment (its only way to speak for its run), and
  # board-bind — which _spawn_reviewer calls — needs the same three to post the
  # session locator and to store the bearer at rest for every later resume.
  #
  # CLAIM_* is the journal hook — _spawn_reviewer marks spawn_completed between
  # the spawn and the bind — and it is set as a plain SHELL variable, never on
  # that export prefix: _spawn_reviewer runs in this shell and reads it either
  # way, while anything on the prefix would be inherited by `sminos spawn` and
  # land in the worker's own environment. A reviewer has no business holding
  # the dispatcher's journal path.
  local spawn_rc=0
  CLAIM_JOURNAL="$claims_dir/$nonce.json" CLAIM_LANE="$lane" CLAIM_RUN="$C_RUN_ID"
  CLAIM_TICKET="$C_TICKET" CLAIM_DAEMON="$name" CLAIM_CONTROL="$control_dir"
  BOARD_RUN_TOKEN="$C_BEARER" BOARD_RUN_ID="$C_RUN_ID" BOARD_RUN_FENCE="$C_FENCE" \
  BOARD_API_URL="$BOARD_API_URL" BOARD_REPO="$BOARD_REPO" \
    _spawn_reviewer "$name" "$C_TICKET" "$prompt" "$LOCAL_REPO" "$engine" \
      "$control_dir" "$name" || spawn_rc=1
  unset CLAIM_JOURNAL CLAIM_LANE CLAIM_RUN CLAIM_TICKET CLAIM_DAEMON CLAIM_CONTROL
  # THE RECORD LOSES THE RUN WITH THE RUN. _spawn_reviewer's post-bind failures
  # — the barrier could not be published, the worker never acknowledged it —
  # retire the worker, but a retire stops a turn; it does not make the seat
  # forget. The bind has already landed by then, so without a strip the record
  # keeps a confirmed bind and a live bearer for the run ended on the next line,
  # and a session resolves its own run context out of exactly those fields
  # (dp#35): resumed by hand, that seat would authenticate with a revoked bearer
  # on every verb instead of falling back cleanly. Ended through the reconciler's
  # helper rather than _api_end_run's swallow, because here the answer decides
  # whether the strip is owed — and _retire_run_locally strips only while the
  # record still names THAT run. The pre-bind failures reach this line too and
  # cost nothing: their record names no run for the guard to match.
  [ "$spawn_rc" -eq 0 ] \
    || { echo "#$C_TICKET: handover failed — releasing run $C_RUN_ID" >&2
         if _claim_end_run "$C_RUN_ID" abandoned \
            && [ -n "${REVIEWER_UUID:-}" ] && [ -f "$DAEMON_HOME/$REVIEWER_UUID.json" ]; then
           _retire_run_locally "$DAEMON_HOME/$REVIEWER_UUID.json" "$C_RUN_ID" \
             || echo "#$C_TICKET: run $C_RUN_ID ended, but $REVIEWER_UUID's record could not be stripped of it — clear run_bearer/bind_confirmed there by hand" >&2
         fi
         _api_drop_journal "$nonce"; return 1; }

  # Lane, role and nonce into the registry meta: the lane is what the cap above
  # counts, the role is what a lane-aware resume reads back, and the nonce is
  # the link from a live worker to the journal entry that made it.
  T_UUID="$REVIEWER_UUID" T_LANE="$lane" T_ROLE=QAGENT T_NONCE="$nonce" \
  T_PARENT_PIN="$C_PARENT_PIN" T_DHOME="$DAEMON_HOME" python3 - <<'PY' || echo "#$C_TICKET: lane meta write failed (non-fatal)" >&2
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
    # at the mode it has, never at the umask default.
    mode = os.stat(path).st_mode & 0o777
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), "w") as f:
        json.dump(m, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
  echo "claimed #$C_TICKET run=$C_RUN_ID lane=$lane → $REVIEWER_UUID"
}

# A FRESH claim on <lane> — the only claims the tick deadline gates, and the
# only ones that mint a nonce. Both refusals here are rc 2: nothing was
# claimed, and neither is a reason to keep claiming.
_claim_one() {  # <lane> <lane-cap>
  local nonce
  _tick_deadline_left \
    || { echo "dispatch: the sweep tick deadline has passed — lane $1 takes no fresh claim this tick"; return 2; }
  nonce="$(_claim_nonce)" || return 2
  _claim_one_with_nonce "$1" "$nonce" "$2"
}

dispatch_api() {
  mkdir -p "$DAEMON_HOME/board-claims"
  _reconcile_claims
  # Local cap first (the registry), the server's laneCap as the belt: if a lane
  # stamp is ever lost the count cannot rise, and laneCap is then the only
  # thing that ends the loop.
  while [ "$(_api_registry_count qagent)" -lt "$REVIEW_CAP" ]; do
    _claim_one qagent "$REVIEW_CAP" || break
  done
}

if [ "$BOARD_BINDING" = api ]; then
  # DISPATCH IS AUTOMATION, FULL STOP — the doctrine block at the head of
  # _sweep_api.sh applies verbatim here. _board_api.token() hands back an
  # ambient BOARD_RUN_TOKEN for whatever principal is asked, so a --sweep run
  # straight out of a worker shell would claim, and end runs, as that worker.
  # The claim path's explicit `BOARD_RUN_TOKEN=…` prefixes set it per command,
  # after this, and are unaffected. This is the automation route only: no
  # human-route verb is touched. The second channel — the seat record
  # $CLAUDE_CODE_SESSION_ID names, which is how a `claude --bg` worker gets its
  # credentials at all (dp#35) — is shut by $BOARD_NO_SELF_LOCATE, exported at
  # the head of this file because it governs the binding resolution too.
  unset BOARD_RUN_TOKEN
  case "${1:-}" in
    --sweep) dispatch_api; exit 0 ;;
    ''|--*)  die "usage: review-dispatch.sh <pr-number> | --sweep" ;;
    *) die "API-mode review dispatch is claim-based — the server owns pick order, the board has no PR listing to trigger off, and the contract has no claim-by-ticket route; use --sweep. Targeted claim is a flow-back candidate recorded on arkho#7 (spec Revision Notes v1.2)." ;;
  esac
fi

if [ "${1:-}" = "--sweep" ]; then
  # Extend the one list call with the same fields dispatch_one resolves the
  # primary ticket from (closingIssuesReferences, else a close-keyword
  # regex over title+body — identical logic, duplicated here rather than
  # shared: it's the only way to know which PRs are ticketed before the
  # per-PR ticket-status read below, with no extra gh call of its own).
  # The listing's health is tracked, not swallowed: the cleanup pass below
  # treats absence from it as evidence a PR is gone, and a transient gh
  # failure would otherwise read as "every PR closed" and retire completed
  # dedupe records wholesale — duplicate reviews on the next healthy sweep.
  pr_list_ok=1
  pr_list_json="$(gh pr list -R "$BOARD_REPO" --state open --limit 100 \
      --json number,isDraft,labels,title,body,closingIssuesReferences)" \
    || { pr_list_json="[]"; pr_list_ok=0; }
  # The dp#64 cohort can sit BEYOND the 100-newest window the main listing
  # sees — the starved-oldest case is the point of the hint. When it is on,
  # one dedicated --label listing fetches the cohort by itself: its rows lead
  # the enumeration and count as open for the cleanup pass (a labeled PR
  # outside the window must not read as "gone", or its completed dedupe
  # record is retired and the next healthy sweep re-reviews it). A failed
  # cohort read degrades to the in-window sort — the hint never fails the
  # sweep.
  pr_prio_json="[]"
  if [ -n "${REVIEW_PRIORITY_LABEL:-}" ]; then
    pr_prio_json="$(gh pr list -R "$BOARD_REPO" --state open --limit 100 \
        --label "$REVIEW_PRIORITY_LABEL" \
        --json number,isDraft,labels,title,body,closingIssuesReferences)" \
      || pr_prio_json="[]"
  fi
  # Every open PR number, drafts included — the registry cleanup below asks
  # "is this reviewer's PR still open?", and a draft is open (it is merely
  # never dispatched, so a meta for one should not exist in the first place).
  open_prs="$(printf '%s' "$pr_list_json" | PR_PRIO_JSON="$pr_prio_json" python3 -c '
import json, os, sys
try:
    ns = [str(p["number"]) for p in json.load(sys.stdin)]
except Exception:
    ns = []
try:
    ns += [str(p["number"]) for p in json.loads(os.environ["PR_PRIO_JSON"])
           if str(p["number"]) not in ns]
except Exception:
    pass
print(" ".join(ns))')" || open_prs=""
  printf '%s' "$pr_list_json" \
    | PR_PRIO_JSON="$pr_prio_json" python3 -c '
import json, os, re, sys
prs = json.load(sys.stdin)
# Priority pre-pass (dp#64): the listing rides gh'"'"'s newest-first server
# order, so under sustained inflow a full review cap starves the old cohort —
# its turn never comes. REVIEW_PRIORITY_LABEL names an opt-in first-pass
# cohort: the dedicated --label listing leads the enumeration (rows beyond
# the main window included), the stable sort covers in-window labels when
# that listing failed, and order is untouched within both groups. Unset,
# the enumeration is exactly the listing.
try:
    _prio = json.loads(os.environ["PR_PRIO_JSON"])
except Exception:
    _prio = []
if _prio:
    _seen = {p.get("number") for p in _prio}
    prs = _prio + [p for p in prs if p.get("number") not in _seen]
_pl = os.environ.get("REVIEW_PRIORITY_LABEL")
if _pl:
    prs.sort(key=lambda p: 0 if any(
        (l or {}).get("name") == _pl for l in (p.get("labels") or [])) else 1)
for p in prs:
    if p.get("isDraft"):
        continue
    linked = [str(n["number"]) for n in (p.get("closingIssuesReferences") or [])]
    text = (p.get("title") or "") + "\n" + (p.get("body") or "")
    for m in re.finditer(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+#(\d+)", text, re.I):
        if m.group(1) not in linked:
            linked.append(m.group(1))
    print("%s %s" % (p["number"], linked[0] if linked else "-"))' \
    | while read -r prn issue; do
        [ "$issue" = "-" ] && issue=""
        # A reviewer only makes sense while its ticket is in-review — read
        # the ticket's status label (the same read Finding 2 always did)
        # BEFORE the dedupe machinery, so a normally-finished reviewer
        # never even reaches the "skip finished reviewer" wall once its
        # ticket has moved on. Absent any status:* label at all (untracked/
        # off-machine), fail open — proceed as before.
        #
        # EXACTLY one label, though. Two or more is `conflict` by _board.py's
        # own definition, and reading the first position let a ticket labelled
        # in-review + needs-human pass as in-review and bind a reviewer to an
        # unrepaired ticket — whose park, incidentally, said a human was
        # waiting. A conflict is reported by its own name so the operator sees
        # what to repair rather than a puzzling "not in-review".
        stale=""
        if [ -n "$issue" ]; then
          # STATE, not just labels. A done/wontfix ticket is CLOSED and the
          # terminal write strips its status label, so a labels-only lookup
          # printed nothing — indistinguishable from "in-review" — and a
          # reviewer spawned onto a finished ticket. A lookup that FAILS is a
          # different thing from a lookup that succeeds and finds no state:
          # the first keeps the deliberate fail-open (an API blip must not
          # stall review), the second is stale. So a parse failure exits
          # NON-ZERO here and the caller's `|| stale=""` restores fail-open,
          # while a clean read of a CLOSED ticket names itself. An OPEN issue
          # with no status label stays fail-open on purpose: that is an
          # untracked issue a PR merely references, not a board ticket, and
          # blocking review on it would be the wrong direction.
          stale="$(gh issue view "$issue" -R "$BOARD_REPO" --json labels,state 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    labels = [l.get("name") for l in d.get("labels") or []]
    state = (d.get("state") or "").upper()
except Exception:
    sys.exit(1)
status = [l[len("status:"):] for l in labels if l.startswith("status:")]
if state == "CLOSED":
    print("closed")
elif len(status) > 1:
    print("conflict(%s)" % ",".join(sorted(status)))
elif status and status[0] != "in-review":
    print(status[0])')" || stale=""
        fi
        run_for "$prn" sweep "$stale" "$issue" \
          || echo "#$prn: dispatch error (continuing sweep)" >&2
      done

  # E2 scale review: recomposition epics enter in-review with a closure
  # package in the pr: meta and no GitHub PR — the PR loop above cannot
  # see them. List them off the board and dispatch the scale variant.
  # Same dedupe machinery, keyed review-epic-<n>; the epic's own board state
  # is what retires the path (a landed verdict leaves in-review, so the next
  # sweep no longer lists it).
  epic_rows="$(PYTHONPATH="$BOARD_SCRIPTS" python3 - <<'PY'
import re
import _board as B
tickets = B.snapshot()
eps = B.epics(tickets)
for tid in sorted(tickets, key=int):
    n = tickets[tid]
    # recomposition_ready is part of the selector, not a detail: a LEAF that
    # gained children after opening a real PR is in-review with a `pr:` meta
    # too, and dispatching a scale reviewer onto it would put a second
    # reviewer on the wrong artifact.
    if not (tid in eps and n["state"] == "in-review" and n.get("pr")
            and B.recomposition_ready(tickets, tid)):
        continue
    # ...and recomposition-ready is not by itself proof the `pr:` value is a
    # closure package. That same leaf reaches recomposition-ready once its
    # last child lands, and nothing cleared the real PR URL it entered
    # in-review with (only the recomposition return clears `pr`, and an
    # auto-close path never runs it). Handing a PR to a scale reviewer as its
    # closure package is the wrong artifact again — the PR loop owns real PRs.
    if "/pull/" in n["pr"]:
        print("SKIP|%s|%s||" % (tid, n["pr"]))
        continue
    # Per-ticket engine override, same rule the PR path applies: the label
    # wins over the environment. Scale review is a QAgent route and QAgent
    # routes honor it — only ARCHITECT dispatch is exempt (X4).
    # (No apostrophes anywhere in this heredoc: it is nested inside $( ), and
    # bash 3.2 — macOS, where launchd runs this — mis-parses that combination
    # the moment the body contains one.)
    labels = n.get("labels") or []
    eng = "claude" if "engine:claude" in labels else (
        "codex" if "engine:codex" in labels else "")
    # The PR head refs of the children. A squash- or rebase-merged child
    # leaves a head SHA that is an ancestor of nothing on the default branch,
    # and a deleted branch, so a fresh clone cannot detach at the per-child
    # heads the closure package names — which is exactly what the
    # no-integration-branch mode tells the reviewer to do. GitHub keeps
    # refs/pull/<n>/head after the branch dies, so name the pulls here and let
    # the dispatcher fetch them.
    pulls = []
    for kid in B.children(tickets, tid):
        k = tickets[kid]
        for p in k.get("prs") or []:
            pulls.append(str(p["num"]))
        m = re.search(r"/pull/(\d+)", k.get("pr") or "")
        if m:
            pulls.append(m.group(1))
    seen = []
    for x in pulls:
        if x not in seen:
            seen.append(x)
    print("%s|%s|%s|%s|%s" % (tid, n["pr"], n.get("branch") or "", eng,
                              " ".join(seen)))
PY
)" || { echo "scale review: board snapshot failed — no epic swept this pass" >&2; epic_rows=""; }
  while IFS='|' read -r etid epkg ebranch eengine epulls; do
    [ -n "$etid" ] || continue
    if [ "$etid" = "SKIP" ]; then
      echo "epic #$epkg: pr: meta is a PR ($ebranch), not a closure package — no scale review (the PR loop owns it)"
      continue
    fi
    # </dev/null: the loop is fed by this heredoc, and anything dispatched
    # inside it that read stdin would eat the remaining epic rows.
    sweep_epic "$etid" "$epkg" "$ebranch" "$eengine" "$epulls" </dev/null \
      || echo "epic #$etid: scale dispatch error (continuing sweep)" >&2
  done <<EOF
$epic_rows
EOF

  # Stale scale reviewers, mirroring run_for's off-review retirement on the
  # epic side. The loop above lists only epics that ARE in-review, so a
  # reviewer whose epic left in-review mid-run (it found a defect, a
  # corrective child was cut, the epic moved on) is never looked at again —
  # and board-sweep's pass_cancel deliberately skips review-epic-* metas, so
  # nothing else finalizes it either. Its meta then lingers `working` and
  # keeps OWNING the ticket: execute-dispatch's _bound_meta refuses to
  # dispatch a ticket with a bound working worker, and _slots_used counts it
  # against the architect lane. Same rule as everywhere else: a live reviewer
  # owns its own exit and is untouched; a finished one is finalized (that is
  # what _decide does before judging) and retired. Metas already retired are
  # not enumerated, so this fires once.
  stale_epics="$(PYTHONPATH="$BOARD_SCRIPTS" DAEMON_HOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
import _board as B
tickets = B.snapshot()
seen = set()
for p in sorted(glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    if not name.startswith("review-epic-") or m.get("status") == "retired":
        continue
    tid = name[len("review-epic-"):]
    if tid in seen or tid not in tickets:
        continue
    # needs-human is the resumable park: board-answer relays to THIS bound
    # session, so retiring it would break the wake path (the M2 rule, applied
    # on the registry side too).
    if tickets[tid]["state"] not in ("in-review", "needs-human"):
        seen.add(tid)
        print(tid)
PY
)" || { echo "scale review: stale-reviewer scan failed (continuing)" >&2; stale_epics=""; }
  while IFS= read -r etid; do
    [ -n "$etid" ] || continue
    _cleanup_orphaned_reviewer "review-epic-$etid" "the epic has left in-review"
  done <<EOF
$stale_epics
EOF

  # Same deadlock, PR side: the loop above enumerates OPEN PRs, so when a
  # reviewer routes its ticket off in-review and the PR then closes, nothing
  # ever finalizes the lingering meta and the now-eligible ticket is skipped
  # by execute-dispatch forever. Walk review-pr-* metas whose PR is not in
  # this tick's open listing. A parked (needs-human) ticket is exempt for the
  # same reason as above — that meta is the park's wake target.
  stale_prs=""
  if [ "$pr_list_ok" = "1" ]; then
  stale_prs="$(OPEN_PRS="$open_prs" PYTHONPATH="$BOARD_SCRIPTS" DAEMON_HOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
import _board as B
open_prs = set((os.environ.get("OPEN_PRS") or "").split())
tickets = B.snapshot()
seen = set()
for p in sorted(glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    if not name.startswith("review-pr-") or m.get("status") == "retired":
        continue
    prn = name[len("review-pr-"):]
    if prn in seen or prn in open_prs:
        continue
    tk = str(m.get("ticket") or "").lstrip("#")
    if tk and tickets.get(tk, {}).get("state") == "needs-human":
        continue
    seen.add(prn)
    print(prn)
PY
)" || { echo "review sweep: stale PR-reviewer scan failed (continuing)" >&2; stale_prs=""; }
  while IFS= read -r prn; do
    [ -n "$prn" ] || continue
    # Absence from the listing is a CANDIDATE, not a verdict: the listing is
    # capped at 100, so PR #101 is absent while perfectly open. Candidates are
    # few, so each one is checked directly — and one that will not answer is
    # left alone this tick rather than retired on a guess.
    pr_state="$(gh pr view "$prn" -R "$BOARD_REPO" --json state -q .state 2>/dev/null)" || pr_state=""
    case "$pr_state" in
      "")
        echo "review sweep: cannot confirm PR #$prn is closed — leaving its reviewer alone this tick" >&2 ;;
      OPEN)
        : ;;   # open but off the listing (the 100-cap) — nothing to clean up
      *)
        _cleanup_orphaned_reviewer "review-pr-$prn" "PR #$prn is $pr_state, no longer open" ;;
    esac
  done <<EOF
$stale_prs
EOF
  else
    echo "review sweep: the open-PR listing failed this tick — no reviewer cleanup (absence is not evidence when the listing is unhealthy)" >&2
  fi
else
  [ $# -ge 1 ] || die "usage: review-dispatch.sh <pr-number> | --sweep"
  pr="${1#\#}"
  case "$pr" in ""|*[!0-9]*) die "not a PR number: $1" ;; esac
  run_for "$pr" triggered
fi
