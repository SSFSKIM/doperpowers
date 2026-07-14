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
#   review-dispatch.sh --sweep        catch-up: every unbound open PR
#
# Env:
#   LOCAL_REPO          canonical local clone of the target repo (default: $PWD)
#   BOARD_REPO          owner/name (default: resolved from LOCAL_REPO via gh)
#   REVIEW_MODEL        optional model override for the review daemon (claude model;
#                       only used when the resolved engine is claude)
#   WORKER_ENGINE       which engine spawns the review worker: claude|codex
#                       (default codex). Resolution order per PR: an
#                       `engine:claude`/`engine:codex` label on the PR wins,
#                       else this env var, else codex.
#   CODEX_REVIEW_MODEL  codex model for the review engine (default gpt-5.6-sol)
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
#
# Per-repo risk surfaces: an optional file at <base>:.doperpowers/risk-surfaces.md
# in the target repo declares concrete self-merge-disqualifying paths/patterns.
# It is read from the PR's BASE ref (never HEAD) so a PR cannot weaken its own
# gate in the same commit, and it only ADDS to the always-on risk categories.
# Per-repo facts: an optional file at <base>:.doperpowers/repo-facts.md declares
# Bootstrap / Validation / Evidence add-on facts (see implementing-tickets).
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
# retire + respawn; a finished reviewer → triggered mode re-dispatches
# (explicit event = fresh signal), sweep mode skips; a finished reviewer
# whose reply carries the ENGINE-UNAVAILABLE marker → retire + respawn
# (sweep too).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
# shellcheck source=../../orchestrating-daemons/scripts/_lib.sh
. "$SKILL_DIR/../orchestrating-daemons/scripts/_lib.sh"
export DAEMON_HOME
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)"
BOOTSTRAP_TEMPLATE="$SKILL_DIR/references/review-worker-bootstrap.md"
IMPLEMENT_PROTOCOL_FILE="$(cd "$SKILL_DIR/../implementing-tickets/references" && pwd)/implement-worker-protocol.md"

die() { echo "error: $*" >&2; exit 1; }

_sha256_file() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

_normalized_issue_body_sha256() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys
text = pathlib.Path(sys.argv[1]).read_text().replace("\r\n", "\n").rstrip("\r\n")
print(hashlib.sha256(text.encode()).hexdigest())
PY
}

command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
[ -f "$BOOTSTRAP_TEMPLATE" ] || die "worker bootstrap missing: $BOOTSTRAP_TEMPLATE"
[ -f "$IMPLEMENT_PROTOCOL_FILE" ] || die "implement worker protocol missing: $IMPLEMENT_PROTOCOL_FILE"
IMPLEMENT_PROTOCOL_SHA256="$(_sha256_file "$IMPLEMENT_PROTOCOL_FILE")" \
  || die "could not hash implement worker protocol: $IMPLEMENT_PROTOCOL_FILE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"

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
ENGINE_BLOCK_FILE="$SKILL_DIR/references/engine-blocks/engine-codex-review.md"
FALLBACK_FILE="$SKILL_DIR/references/engine-blocks/fallback-engine.md"
REVIEW_ENGINE="$SCRIPT_DIR/review-engine.sh"

# Newest review-pr-<n> registry entry → "uuid|status|current|engine|pid|host|boot"
# (empty if none).
_reviewer_meta() {
  DAEMON_HOME="$DAEMON_HOME" PRN="$1" python3 - <<'PY'
import glob, json, os
home = os.environ["DAEMON_HOME"]; name = "review-pr-" + os.environ["PRN"]
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

# rc 0 when some LOCAL `claude agents` row's cwd equals worktree path <1>. A
# visible row with matching foreign registry metadata migrated with the session
# store, not the process, so it does not occupy the worktree. Unmanaged rows
# have no identity evidence and remain conservatively local/occupied.
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
    if m is None or local(m):
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
  local pr="$1" tmp pr_json exports issue issue_url issue_body_sha256 td wt prompt engine
  tmp="$(mktemp -d)"
  pr_json="$(gh pr view "$pr" -R "$BOARD_REPO" --json number,title,body,baseRefName,headRefName,headRefOid,url,isDraft,state,labels,closingIssuesReferences)" \
    || { echo "#$pr: gh pr view failed" >&2; rm -rf "$tmp"; return 1; }
  printf '%s' "$pr_json" > "$tmp/pr.json"
  exports="$(TMP="$tmp" python3 - <<'PY'
import json, os, re, shlex
d = json.load(open(os.path.join(os.environ["TMP"], "pr.json")))
open(os.path.join(os.environ["TMP"], "pr-body.md"), "w").write(d.get("body") or "")
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

  # primary ticket brief (first linked issue; the full list rides the prompt)
  issue="${LINKED_ISSUES%% *}"
  issue_url="none"
  issue_body_sha256="none"
  : > "$tmp/issue-body.md"
  if [ -n "$issue" ]; then
    # degrade gracefully — a deleted linked issue must not block the review
    issue_url="$(gh issue view "$issue" -R "$BOARD_REPO" --json url -q .url 2>/dev/null || echo none)"
    gh issue view "$issue" -R "$BOARD_REPO" --json body -q .body > "$tmp/issue-body.md" 2>/dev/null \
      || : > "$tmp/issue-body.md"
    issue_body_sha256="$(_normalized_issue_body_sha256 "$tmp/issue-body.md")" \
      || { echo "#$pr: issue body hash failed" >&2; rm -rf "$tmp"; return 1; }
  fi

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

  prompt="$(P_PR_NUMBER="$pr" P_PR_URL="$PR_URL" P_PR_TITLE="$PR_TITLE" \
    P_REPO="$BOARD_REPO" P_BASE_REF="$BASE_REF" P_HEAD_REF="$HEAD_REF" \
    P_HEAD_SHA="$HEAD_SHA" P_ISSUE_NUMBER="${issue:-none}" \
    P_ISSUE_URL="$issue_url" P_ISSUE_LIST="${LINKED_ISSUES:-none}" \
    P_TECH_DEBT_ISSUE="${td:-none}" \
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" P_AUTO_MERGE="$AUTO_MERGE_DISPLAY" \
    P_DEFAULT_BRANCH="$DEFAULT_BRANCH" P_BASE_IS_DEFAULT="$base_is_default" \
    P_SKILL_FILE="$SKILL_DIR/SKILL.md" \
    P_IMPLEMENT_PROTOCOL_FILE="$IMPLEMENT_PROTOCOL_FILE" \
    P_IMPLEMENT_PROTOCOL_SHA256="$IMPLEMENT_PROTOCOL_SHA256" \
    P_ISSUE_BODY_SHA256="$issue_body_sha256" \
    P_ENGINE_NAME="$engine" P_CODEX_REVIEW_MODEL="$CODEX_REVIEW_MODEL" \
    P_CODEX_REVIEW_EFFORT="$CODEX_REVIEW_EFFORT" P_REVIEW_ENGINE="$REVIEW_ENGINE" \
    ENGINE_BLOCK_FILE="$ENGINE_BLOCK_FILE" FALLBACK_FILE="$FALLBACK_FILE" \
    PR_BODY_FILE="$tmp/pr-body.md" ISSUE_BODY_FILE="$tmp/issue-body.md" \
    RISK_FILE="$tmp/risk.md" FACTS_FILE="$tmp/facts.md" \
    python3 - "$BOOTSTRAP_TEMPLATE" <<'PY'
import os, re, sys
CAP = 20000  # keep the spawn arg well under the OS arg-size limit
def readcap(path):
    t = open(path).read()
    if len(t) > CAP:
        t = t[:CAP] + "\n[... truncated for dispatch — read the rest on GitHub]"
    return t
t = open(sys.argv[1]).read()
t = t.replace("{{ENGINE_BLOCK}}", open(os.environ["ENGINE_BLOCK_FILE"]).read())
t = t.replace("{{FALLBACK_BLOCK}}", open(os.environ["FALLBACK_FILE"]).read())
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
subs["PR_BODY"] = readcap(os.environ["PR_BODY_FILE"]) or "(empty PR body)"
subs["ISSUE_BODY"] = readcap(os.environ["ISSUE_BODY_FILE"]) or "(no linked issue)"
subs["RISK_MANIFEST"] = readcap(os.environ["RISK_FILE"]) or \
    "(no repo risk-surface manifest at .doperpowers/risk-surfaces.md — the always-on categories are the only risk surfaces)"
subs["REPO_FACTS"] = readcap(os.environ["FACTS_FILE"]) or \
    "(no repo-facts manifest at .doperpowers/repo-facts.md — no declared validation commands or evidence add-ons to cross-check against)"
print(re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), ""), t))
PY
)" || { echo "#$pr: prompt render failed" >&2; rm -rf "$tmp"; return 1; }
  rm -rf "$tmp"
  [ -n "$prompt" ] || { echo "#$pr: empty prompt — not dispatching" >&2; return 1; }

  if [ "$engine" = "codex" ]; then
    "$DAEMON_SCRIPTS/codex-spawn.sh" --no-wait "review-pr-$pr" "$prompt" "$wt" "" \
      "$CODEX_REVIEW_MODEL" "$CODEX_REVIEW_EFFORT"
  else
    "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "review-pr-$pr" "$prompt" "$wt" "" "${REVIEW_MODEL:-}"
  fi
}

# Dedupe verdict for PR <1> in mode <2> (triggered|sweep), cr-label flag <3>.
# Prints: "dispatch" | "respawn <uuid>" | "skip <why>".
_decide() {
  local pr="$1" mode="$2" cr="$3" meta uuid status current rest engine pid whost wboot
  if [ "$cr" = "1" ]; then echo "skip confident-ready label (remove it to force re-review)"; return; fi
  meta="$(_reviewer_meta "$pr")"
  if [ -z "$meta" ]; then echo "dispatch"; return; fi
  uuid="${meta%%|*}"; rest="${meta#*|}"; status="${rest%%|*}"; rest="${rest#*|}"
  current="${rest%%|*}"; rest="${rest#*|}"; engine="${rest%%|*}"; rest="${rest#*|}"
  pid="${rest%%|*}"; rest="${rest#*|}"; whost="${rest%%|*}"; wboot="${rest#*|}"
  case "$status" in
    working|blocked)
      if _is_live "$current" "$engine" "$pid" "$whost" "$wboot"; then echo "skip active reviewer"; else echo "respawn $uuid"; fi ;;
    retired) echo "dispatch" ;;
    *)
      if [ "$mode" = "triggered" ]; then echo "respawn $uuid"
      # an engine outage is a retryable condition, not a finished review —
      # the worker marks it with a final-message marker line (fallback block)
      elif grep -qx 'ENGINE-UNAVAILABLE' "$DAEMON_HOME/$uuid.reply.txt" 2>/dev/null; then
        echo "respawn $uuid"
      else echo "skip finished reviewer ($status)"; fi ;;
  esac
}

run_for() {  # $1=pr $2=mode $3=cr-label
  local verdict
  verdict="$(_decide "$1" "$2" "$3")"
  case "$verdict" in
    dispatch)  dispatch_one "$1" ;;
    respawn\ *) _retire "${verdict#respawn }"; dispatch_one "$1" ;;
    *)         echo "#$1: $verdict" ;;
  esac
}

if [ "${1:-}" = "--sweep" ]; then
  gh pr list -R "$BOARD_REPO" --state open --limit 100 --json number,isDraft,labels \
    | python3 -c '
import json, sys
for p in json.load(sys.stdin):
    if p.get("isDraft"):
        continue
    cr = 1 if any(l.get("name") == "confident-ready" for l in p.get("labels") or []) else 0
    print("%s %s" % (p["number"], cr))' \
    | while read -r prn cr; do
        run_for "$prn" sweep "$cr" || echo "#$prn: dispatch error (continuing sweep)" >&2
      done
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
