#!/usr/bin/env bash
# review-dispatch.sh — dispatch a review-worker daemon onto an open PR.
#
# The trigger half of doperpowers:reviewing-prs — mechanical only, no model
# judgment. Gathers PR + linked-ticket context, creates a DETACHED worktree
# at the PR head SHA, renders the skill-invocation bootstrap, and spawns a
# `review-pr-<n>` daemon via daemon-spawn.sh --no-wait.
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
#                       (gateway route defaults to fable, claude route to inherit)
#   WORKER_ENGINE       which MODEL ROUTE the worker daemon uses: codex|claude
#                       (default codex). Every worker is a Claude-harness
#                       daemon; "codex" means the gateway settings ride the
#                       spawn (GPT models via the local proxy), "claude" means
#                       plain Claude models. Resolution order per PR: an
#                       `engine:claude`/`engine:codex` label wins, else this
#                       env var, else codex.
#   CLODEX_SETTINGS     gateway settings file for the codex route
#                       (default ~/.claude/clodex-settings.json)
#   CLODEX_EFFORT       reasoning effort for the codex route (default xhigh)
#   CODEX_REVIEW_MODEL  codex model for the review ENGINE (default gpt-5.6-sol)
#   CODEX_REVIEW_EFFORT  codex reasoning effort for the review engine (default xhigh)
#   AUTO_MERGE_ENABLED  staged-rollout gate for the worker's self-merge tier
#                       (default false = observation mode: the worker reviews
#                       and judges the tier but routes self-merge-eligible PRs
#                       to confident-ready instead of merging). Supplied as a
#                       skill runtime binding; the dispatch layer never merges.
#   DEFAULT_BRANCH      repo default branch (default: resolved via gh); the
#                       worker never self-merges a PR whose base is this branch
#   DAEMON_SCRIPTS      orchestrating-daemons scripts dir override (tests)
#   DAEMON_HOME         daemon registry dir (default ~/.claude/orchestrating-daemons)
#   BOARD_SCRIPTS       issue-tracker scripts dir override (tests)
#   REVIEW_BIND_ATTEMPTS / REVIEW_BIND_DELAY
#                       ticket-bind retries (defaults 3 attempts, 2s delay)
#   REVIEW_ACK_POLLS / REVIEW_ACK_DELAY
#                       startup-barrier acknowledgement wait (600 x 0.2s)
#
# Per-repo risk surfaces: an optional file at <base>:.doperpowers/risk-surfaces.md
# in the target repo declares concrete self-merge-disqualifying paths/patterns.
# It is read from the PR's BASE ref (never HEAD) so a PR cannot weaken its own
# gate in the same commit, and it only ADDS to the always-on risk categories.
# Per-repo facts: an optional file at <base>:.doperpowers/repo-facts.md declares
# Bootstrap / Validation / Evidence add-on facts (see implementing).
# Same BASE-ref discipline; the review worker cross-checks claimed evidence
# against the declared validation commands and add-on requirements.
# LOCAL_REPO must be a FULL clone (not --single-branch): the base read resolves
# origin/<base>, refreshed by the per-dispatch fetch; a narrowed clone can
# leave that tracking ref stale and the manifest would silently fall back to
# the always-on categories only (fail-safe — self-merge still never lands on
# the default branch, but a repo-declared surface would go unenforced).
#
# Dedupe policy (references/operation-manual.md table): confident-ready-labeled PRs are never
# dispatched; a live ACTIVE reviewer → skip; a dead ACTIVE reviewer →
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
# loop below resolves the ticket's status alongside the confident-ready
# check, BEFORE consulting the registry dedupe machinery: when the ticket
# isn't in-review, any FINISHED (non-active) reviewer meta it finds is
# retired right there and the tick is skipped without spawning — never an
# ACTIVE (working/blocked) reviewer, which owns its own exit. That retire
# is what makes the ticket's eventual return to in-review land on the
# ordinary "none / retired → dispatch" row above, with no special-case
# dispatch logic needed once the ticket is back.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
# shellcheck source=../../orchestrating-daemons/scripts/_lib.sh
. "$SKILL_DIR/../orchestrating-daemons/scripts/_lib.sh"
export DAEMON_HOME
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)}"
BOOTSTRAP_TEMPLATE="$SKILL_DIR/references/review-worker-bootstrap.md"

die() { echo "error: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
[ -f "$BOOTSTRAP_TEMPLATE" ] || die "worker bootstrap missing: $BOOTSTRAP_TEMPLATE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"
# EXPORTED, not just set: the scale-review passes shell out to python that
# imports _board, whose repo() reads the ENVIRONMENT. Run from board-sweep it
# arrives exported already and the miss is invisible; run directly — the
# documented path — an unexported value made every scale epic die
# "BOARD_REPO is unset" inside the subprocess and be silently skipped.
export BOARD_REPO

# Repo-wide config injected into every worker prompt (constant across PRs):
#   DEFAULT_BRANCH — self-merge is forbidden onto it (main-exclusion).
#   AUTO_MERGE_DISPLAY — the staged-rollout gate as the worker sees it.
DEFAULT_BRANCH="${DEFAULT_BRANCH:-$(gh repo view "$BOARD_REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo main)}"
[ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH="main"
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

_retire() { "$DAEMON_SCRIPTS/daemon-retire.sh" "$1" >/dev/null 2>&1 || true; }

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
# board-bind.sh takes (read-modify-write; unknown keys are preserved).
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
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=2)
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
        sys.exit(0)   # unmanaged row: no identity evidence — conservatively occupied
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

# ---- per-PR dispatch (dedupe already decided by the caller) --------------------
# Every step is explicitly guarded: in sweep mode this function runs behind
# `||` (which suspends errexit through the WHOLE call subtree), so an
# unguarded mid-function failure would be silently absorbed — dispatching
# with stale vars from the previous iteration or an empty prompt. Guards
# return 1 so the sweep's per-PR reporter fires instead.
dispatch_one() {
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
  engine="${ENGINE_LABEL:-${WORKER_ENGINE:-codex}}"
  if [ "$PR_STATE" != "OPEN" ]; then echo "#$pr: not open ($PR_STATE) — skip"; rm -rf "$tmp"; return 0; fi
  if [ "$PR_DRAFT" != "0" ]; then echo "#$pr: draft — skip"; rm -rf "$tmp"; return 0; fi

  # primary ticket (first linked issue; the full list rides the prompt as
  # numbers only — the worker reads PR and ticket bodies live via gh)
  issue="${LINKED_ISSUES%% *}"

  # standing tech-debt sink (optional)
  td="$(gh issue list -R "$BOARD_REPO" --label tech-debt --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"

  # DETACHED worktree at the PR head SHA — the PR branch is usually checked
  # out in the implementer's worktree, and git forbids a second checkout;
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
  # base-is-default drives the worker's main-exclusion clause.
  local base_is_default="no"
  [ "$BASE_REF" = "$DEFAULT_BRANCH" ] && base_is_default="yes"
  if [ -e "$wt" ]; then
    if _wt_occupied "$wt"; then
      echo "#$pr: live daemon occupies $wt — not removing (retire it first)" >&2
      rm -rf "$tmp"; return 1
    fi
    git -C "$LOCAL_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$LOCAL_REPO" worktree prune
  git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "$HEAD_SHA" \
    || { echo "#$pr: worktree add failed" >&2; rm -rf "$tmp"; return 1; }

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
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" P_AUTO_MERGE="$AUTO_MERGE_DISPLAY" \
    P_DEFAULT_BRANCH="$DEFAULT_BRANCH" P_BASE_IS_DEFAULT="$base_is_default" \
    P_BIND_READY_FILE="$bind_ready" P_SKILL_FILE="$SKILL_DIR/SKILL.md" \
    P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/implementing/SKILL.md" \
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
dispatch_epic() {  # <epic-ticket> <closure-package-url> [integration-branch]
  local etid="$1" pkg="$2" branch="${3:-}" name tmp wt int_ref base_ref td prompt engine
  local control_dir bind_ready ledger base_is_default range_note
  name="review-epic-$etid"
  engine="${WORKER_ENGINE:-codex}"
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
  # No integration branch left ⇒ the worktree sits on the default branch and
  # there is no aggregate range at all; say so in the prompt rather than
  # letting the worker run an engine over nothing.
  # Same formula as the PR path, on the same binding: BASE_REF is what the
  # reviewed work merges into, and for an epic that is always the default
  # branch — so this is always "yes". Hand-setting it "no" for the
  # integration-branch case contradicted the BASE_REF the same prompt binds,
  # and pointed the (scale-inapplicable) self-merge tier the permissive way.
  base_is_default="no"
  [ "$base_ref" = "$DEFAULT_BRANCH" ] && base_is_default="yes"
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

  wt="$LOCAL_REPO/.claude/worktrees/$name"
  if [ -e "$wt" ]; then
    if _wt_occupied "$wt"; then
      echo "$name: live daemon occupies $wt — not removing (retire it first)" >&2
      rm -rf "$tmp"; return 1
    fi
    git -C "$LOCAL_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$LOCAL_REPO" worktree prune
  git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "origin/$int_ref" \
    || { echo "$name: worktree add failed (origin/$int_ref)" >&2; rm -rf "$tmp"; return 1; }

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
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" P_AUTO_MERGE="$AUTO_MERGE_DISPLAY" \
    P_DEFAULT_BRANCH="$DEFAULT_BRANCH" P_BASE_IS_DEFAULT="$base_is_default" \
    P_BIND_READY_FILE="$bind_ready" P_SKILL_FILE="$SKILL_DIR/SKILL.md" \
    P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/implementing/SKILL.md" \
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
# Normalize lingering finished owners of ticket <1> BEFORE binding (same
# preflight as land-dispatch): a claude-species worker has no self-finalizer,
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
    "$DAEMON_SCRIPTS/daemon-finalize.sh" "$owner" >/dev/null 2>&1 || true
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
# their absent-file fallbacks). A placeholder with no P_* renders empty.
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
t = re.sub(r"<!-- mode:(\w+) -->\n(.*?)<!-- /mode:\1 -->\n",
           lambda m: m.group(2) if m.group(1) == mode else "", t, flags=re.S)
subs["RISK_MANIFEST"] = readcap(os.environ["RISK_FILE"]) or \
    "(no repo risk-surface manifest at .doperpowers/risk-surfaces.md — the always-on categories are the only risk surfaces)"
subs["REPO_FACTS"] = readcap(os.environ["FACTS_FILE"]) or \
    "(no repo-facts manifest at .doperpowers/repo-facts.md — no declared validation commands or evidence add-ons to cross-check against)"
print(re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), ""), t))
PY
}

# Spawn tail shared by both variants: spawn → parse identity → bind the
# ticket → publish the startup barrier → wait for the worker's ack. Every
# failure retires the worker and removes the control dir, leaving the
# barrier closed; the caller's own guards handle everything before this.
# On success the spawned identity is left in REVIEWER_UUID for callers that
# stamp their own bookkeeping onto the fresh meta.
_spawn_reviewer() {  # <name> <ticket|""> <prompt> <worktree> <engine> <control-dir>
  local name="$1" issue="$2" prompt="$3" wt="$4" engine="$5" control_dir="$6"
  local bind_ready="$control_dir/bind-ready.json"
  local ledger="$control_dir/accepted-commits.json"
  local spawn_out uuid ack
  REVIEWER_UUID=""

  # ONE worker harness, two model routes. The default "codex" engine is a
  # GATEWAY worker: the same Claude-harness daemon pointed at the local
  # gateway (GPT models) via --settings — the codex CLI survives only as the
  # review engine inside the worker. engine:claude opts a PR into plain
  # Claude models. The codex-CLI-as-worker species is retired from this loop.
  if [ "$engine" = "codex" ]; then
    spawn_out="$(DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" \
      DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" \
      "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$wt" "" \
      "${REVIEW_MODEL:-fable}")" \
      || { echo "$name: review worker spawn failed" >&2; rm -rf "$control_dir"; return 1; }
  else
    spawn_out="$("$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$wt" "" "${REVIEW_MODEL:-}")" \
      || { echo "$name: review worker spawn failed" >&2; rm -rf "$control_dir"; return 1; }
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
      echo "$name: bind to ticket #$issue failed after $attempts attempt(s) — review worker retired (a parked reviewer must be resumable via board-answer)" >&2
      return 1
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
    echo "$name: could not publish startup barrier — review worker retired" >&2
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
}

# Consecutive FAILED reviewers for worker name <1>, newest first: a reply carrying the
# ENGINE-UNAVAILABLE marker (engine outage) or a turn finalized status=error
# (dead worker — e.g. the gateway refused its first turn, so no reply exists
# to carry any marker). One shared streak, so interleaved failure kinds don't
# reset the count; the sweep's cap reads it so neither a dead engine nor a
# dead gateway can make the cron respawn a PR forever. Any cleanly finished
# reviewer breaks the streak.
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
        rows.append((str(m.get("updated") or m.get("created") or ""),
                     m.get("uuid") or "", str(m.get("status") or "")))
rows.sort(reverse=True)
streak = 0
for _, uuid, status in rows:
    try:
        lines = open(os.path.join(home, uuid + ".reply.txt")).read().splitlines()
    except Exception:
        lines = None
    if (lines is not None and "ENGINE-UNAVAILABLE" in lines) or status == "error":
        streak += 1
    else:
        break
print(streak)
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
  if [ "$mode" = "triggered" ]; then echo "respawn $uuid"
  elif [ "$status" = "error" ] \
    || grep -qx 'ENGINE-UNAVAILABLE' "$DAEMON_HOME/$uuid.reply.txt" 2>/dev/null; then
    if [ "$(_outage_streak "$name")" -ge 3 ]; then
      echo "skip outage/dead-worker failure persists (3 consecutive reviewers — an explicit PR event re-dispatches)"
    else
      echo "respawn $uuid"
    fi
  else echo "skip finished reviewer ($status)"; fi
}

# Dedupe verdict for worker name <1> in mode <2> (triggered|sweep), cr-label
# flag <3>. Prints: "dispatch" | "respawn <uuid>" | "skip <why>".
_decide() {
  local name="$1" mode="$2" cr="$3" meta uuid status current rest engine pid whost wboot fin
  if [ "$cr" = "1" ]; then echo "skip confident-ready label (remove it to force re-review)"; return; fi
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
        # is not liveness. Finalize first (records reply + terminal status),
        # then judge: live → skip; finished → the finished-reviewer verdict;
        # session gone → dead worker → respawn.
        fin="$("$DAEMON_SCRIPTS/daemon-finalize.sh" "$uuid" 2>/dev/null || echo "")"
        case "$fin" in
          live)       echo "skip active reviewer" ;;
          idle|error) _finished_verdict "$name" "$uuid" "$mode" "$fin" ;;
          noop)       echo "skip finished reviewer (raced finalize)" ;;
          *)          echo "respawn $uuid" ;;
        esac
      fi ;;
    retired) echo "dispatch" ;;
    *) _finished_verdict "$name" "$uuid" "$mode" "$status" ;;
  esac
}

# $4/$5 (sweep mode only): the primary ticket's off-review status name
# (e.g. "ready-for-architect", "needs-human") and its number, when the
# sweep already resolved the ticket is NOT in-review. Empty $4 means
# in-review, ticketless, or triggered mode — never gated, same as before.
#
# A reviewer bound to a ticket that has left in-review is stale by
# definition (header comment). $verdict from the ordinary dedupe machinery
# already tells us everything needed to act on that: "skip active
# reviewer" means a live session is mid-turn and owns its own exit (never
# touched); "skip confident-ready ..." is an unrelated, already-correct
# skip (passed through unchanged); anything else — dispatch, respawn
# <uuid>, or any other "skip ..." — means at most a NON-live reviewer meta
# is on file, so it's retired here instead of being left to strand the
# ticket's next return to in-review behind "skip finished reviewer"
# forever.
run_for() {  # $1=pr $2=mode $3=cr-label $4=off-review-status $5=ticket-number
  local pr="$1" mode="$2" cr="$3" stale="${4:-}" tid="${5:-}" verdict resume
  verdict="$(_decide "review-pr-$pr" "$mode" "$cr")"
  if [ -n "$stale" ]; then
    case "$verdict" in
      "skip active reviewer")
        echo "#$pr: skip — primary ticket #$tid is status:$stale, not in-review; its still-active reviewer owns its own exit"
        return ;;
      "skip confident-ready"*)
        echo "#$pr: $verdict"
        return ;;
    esac
    case "$stale" in
      needs-human|needs-info|interactive-preferred)
        resume="the review resumes via board-answer, not a fresh dispatch" ;;
      *)
        resume="resumes when the ticket returns to in-review, not from here" ;;
    esac
    local m
    m="$(_reviewer_meta "review-pr-$pr")"
    [ -n "$m" ] && _retire "${m%%|*}"
    echo "#$pr: skip — primary ticket #$tid is parked (status:$stale); $resume"
    return
  fi
  case "$verdict" in
    dispatch)  dispatch_one "$1" "$2" ;;
    respawn\ *) _retire "${verdict#respawn }"; dispatch_one "$1" "$2" ;;
    *)         echo "#$1: $verdict" ;;
  esac
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
sweep_epic() {  # $1=epic-ticket $2=closure-package $3=integration-branch
  local etid="$1" pkg="$2" verdict meta uuid
  verdict="$(_decide "review-epic-$etid" sweep 0)"
  case "$verdict" in
    dispatch)   dispatch_epic "$@"; return ;;
    respawn\ *) _retire "${verdict#respawn }"; dispatch_epic "$@"; return ;;
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
      [ -n "$uuid" ] && _retire "$uuid"
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

if [ "${1:-}" = "--sweep" ]; then
  # Extend the one list call with the same fields dispatch_one resolves the
  # primary ticket from (closingIssuesReferences, else a close-keyword
  # regex over title+body — identical logic, duplicated here rather than
  # shared: it's the only way to know which PRs are ticketed before the
  # per-PR ticket-status read below, with no extra gh call of its own).
  gh pr list -R "$BOARD_REPO" --state open --limit 100 \
      --json number,isDraft,labels,title,body,closingIssuesReferences \
    | python3 -c '
import json, re, sys
for p in json.load(sys.stdin):
    if p.get("isDraft"):
        continue
    cr = 1 if any(l.get("name") == "confident-ready" for l in p.get("labels") or []) else 0
    linked = [str(n["number"]) for n in (p.get("closingIssuesReferences") or [])]
    text = (p.get("title") or "") + "\n" + (p.get("body") or "")
    for m in re.finditer(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+#(\d+)", text, re.I):
        if m.group(1) not in linked:
            linked.append(m.group(1))
    print("%s %s %s" % (p["number"], cr, linked[0] if linked else "-"))' \
    | while read -r prn cr issue; do
        [ "$issue" = "-" ] && issue=""
        # A reviewer only makes sense while its ticket is in-review — read
        # the ticket's status label (the same read Finding 2 always did)
        # BEFORE the dedupe machinery, so a normally-finished reviewer
        # never even reaches the "skip finished reviewer" wall once its
        # ticket has moved on. Absent any status:* label at all (untracked/
        # off-machine), fail open — proceed as before.
        stale=""
        if [ -n "$issue" ]; then
          stale="$(gh issue view "$issue" -R "$BOARD_REPO" --json labels 2>/dev/null | python3 -c '
import json, sys
try:
    labels = [l.get("name") for l in json.load(sys.stdin).get("labels") or []]
except Exception:
    labels = []
status = [l[len("status:"):] for l in labels if l.startswith("status:")]
print(status[0] if status and status[0] != "in-review" else "")')" || stale=""
        fi
        run_for "$prn" sweep "$cr" "$stale" "$issue" || echo "#$prn: dispatch error (continuing sweep)" >&2
      done

  # E2 scale review: recomposition epics enter in-review with a closure
  # package in the pr: meta and no GitHub PR — the PR loop above cannot
  # see them. List them off the board and dispatch the scale variant.
  # Same dedupe machinery, keyed review-epic-<n>; the epic's own board state
  # is what retires the path (a landed verdict leaves in-review, so the next
  # sweep no longer lists it).
  epic_rows="$(PYTHONPATH="$BOARD_SCRIPTS" python3 - <<'PY'
import _board as B
tickets = B.snapshot()
eps = B.epics(tickets)
for tid in sorted(tickets, key=int):
    n = tickets[tid]
    # recomposition_ready is part of the selector, not a detail: a LEAF that
    # gained children after opening a real PR is in-review with a `pr:` meta
    # too, and dispatching a scale reviewer onto it would put a second
    # reviewer on the wrong artifact.
    if tid in eps and n["state"] == "in-review" and n.get("pr") \
       and B.recomposition_ready(tickets, tid):
        print("%s|%s|%s" % (tid, n["pr"], n.get("branch") or ""))
PY
)" || { echo "scale review: board snapshot failed — no epic swept this pass" >&2; epic_rows=""; }
  while IFS='|' read -r etid epkg ebranch; do
    [ -n "$etid" ] || continue
    # </dev/null: the loop is fed by this heredoc, and anything dispatched
    # inside it that read stdin would eat the remaining epic rows.
    sweep_epic "$etid" "$epkg" "$ebranch" </dev/null \
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
  # keeps OWNING the ticket: implement-dispatch's _bound_meta refuses to
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
    if tickets[tid]["state"] != "in-review":
        seen.add(tid)
        print(tid)
PY
)" || { echo "scale review: stale-reviewer scan failed (continuing)" >&2; stale_epics=""; }
  while IFS= read -r etid; do
    [ -n "$etid" ] || continue
    verdict="$(_decide "review-epic-$etid" sweep 0)"
    if [ "$verdict" = "skip active reviewer" ]; then
      echo "epic #$etid: skip — no longer in-review; its still-active reviewer owns its own exit"
      continue
    fi
    meta="$(_reviewer_meta "review-epic-$etid")"
    [ -n "$meta" ] || continue
    _retire "${meta%%|*}"
    echo "epic #$etid: reviewer ${meta%%|*} retired — the epic has left in-review"
  done <<EOF
$stale_epics
EOF
else
  [ $# -ge 1 ] || die "usage: review-dispatch.sh <pr-number> | --sweep"
  pr="${1#\#}"
  case "$pr" in ""|*[!0-9]*) die "not a PR number: $1" ;; esac
  cr="$(gh pr view "$pr" -R "$BOARD_REPO" --json labels 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(1 if any(l.get("name") == "confident-ready" for l in d.get("labels") or []) else 0)')"
  run_for "$pr" triggered "$cr"
fi
