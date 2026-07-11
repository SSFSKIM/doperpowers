#!/usr/bin/env bash
# land-dispatch.sh — dispatch a LAND worker onto an approved confident-ready PR.
#
# The post-approval landing phase of doperpowers:reviewing-prs (FD-4,
# docs/doperpowers/2026-07-11-symphony-comparison.md): the human's approval
# is a pure decision; the merge mechanics (base sync, CI babysitting,
# conflict triage, finalize) belong to a worker. Mechanical only — this
# script verifies the authority signal, gathers context, creates a DETACHED
# worktree at the PR head SHA, renders the Land Worker Protocol, spawns a
# `land-pr-<n>` daemon, and BINDS it to the linked ticket so the
# board-answer relay can resume a parked land worker in place.
#
# Usage: land-dispatch.sh <pr-number>
#   No sweep mode — landing always follows an explicit human signal; the
#   PR-review-event trigger arrives with runner registration.
#
# Authority gate (both required):
#   - the PR carries the `confident-ready` label (the review loop's verdict);
#   - the PR's review decision is APPROVED, or it carries a `land` label —
#     the explicit manual override (e.g. your own PR, which GitHub will not
#     let you approve).
#
# Env:
#   LOCAL_REPO      canonical local clone of the target repo (default: $PWD)
#   BOARD_REPO      owner/name (default: resolved from LOCAL_REPO via gh)
#   WORKER_ENGINE   claude|codex (default codex); an engine:* PR label wins
#   LAND_MODEL      optional claude model override for the land daemon
#   LAND_ENABLED    staged rollout (default false = DRY-RUN mode: the worker
#                   analyzes and posts what it WOULD do; merges nothing)
#   BOARD_SCRIPTS   issue-tracker scripts dir override (tests)
#   DAEMON_SCRIPTS  orchestrating-daemons scripts dir override (tests)
#   DAEMON_HOME     daemon registry dir (default ~/.claude/orchestrating-daemons)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
export DAEMON_HOME
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="${BOARD_SCRIPTS:-$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)}"
PROTOCOL_TEMPLATE="$SKILL_DIR/references/land-worker-protocol.md"

die() { echo "error: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
[ -f "$PROTOCOL_TEMPLATE" ] || die "protocol template missing: $PROTOCOL_TEMPLATE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

[ $# -ge 1 ] || die "usage: land-dispatch.sh <pr-number>"
pr="${1#\#}"
case "$pr" in ""|*[!0-9]*) die "not a PR number: $1" ;; esac

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"

case "${LAND_ENABLED:-false}" in
  true|1|on|yes|TRUE|True) LAND_MODE="live" ;;
  *) LAND_MODE="dry-run" ;;
esac

# Newest land-pr-<n> registry entry → "uuid|status|current|engine|pid" (empty if none).
_land_meta() {
  DAEMON_HOME="$DAEMON_HOME" PRN="$1" python3 - <<'PY'
import glob, json, os
home = os.environ["DAEMON_HOME"]; name = "land-pr-" + os.environ["PRN"]
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
    print("%s|%s|%s|%s|%s" % (m.get("uuid", ""), m.get("status", ""), m.get("current", ""),
                              m.get("engine") or "claude", m.get("pid", "")))
PY
}

# rc 0 when the worker's CURRENT turn is live (same semantics as review-dispatch).
_is_live() {  # <current> <engine> <pid>
  if [ "$2" = "codex" ]; then
    [ -n "$3" ] && kill -0 "$3" 2>/dev/null
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

# ---- gate: PR state + human authority signal -----------------------------------
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
gh pr view "$pr" -R "$BOARD_REPO" \
  --json number,title,body,baseRefName,headRefName,headRefOid,url,isDraft,state,labels,closingIssuesReferences,reviewDecision \
  > "$tmp/pr.json" || die "#$pr: gh pr view failed"
exports="$(TMP="$tmp" python3 - <<'PY'
import json, os, re, shlex
d = json.load(open(os.path.join(os.environ["TMP"], "pr.json")))
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
q("PR_TITLE", d["title"]); q("BASE_REF", d["baseRefName"]); q("HEAD_REF", d["headRefName"])
q("HEAD_SHA", d["headRefOid"]); q("PR_URL", d["url"]); q("PR_STATE", d["state"])
q("PR_DRAFT", 1 if d["isDraft"] else 0)
q("REVIEW_DECISION", d.get("reviewDecision") or "")
names = [l.get("name", "") for l in (d.get("labels") or [])]
q("HAS_CR", 1 if "confident-ready" in names else 0)
q("HAS_LAND_LABEL", 1 if "land" in names else 0)
eng = "claude" if "engine:claude" in names else ("codex" if "engine:codex" in names else "")
q("ENGINE_LABEL", eng)
linked = [str(n["number"]) for n in (d.get("closingIssuesReferences") or [])]
text = (d.get("title") or "") + "\n" + (d.get("body") or "")
for m in re.finditer(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+#(\d+)", text, re.I):
    if m.group(1) not in linked:
        linked.append(m.group(1))
q("LINKED_ISSUES", " ".join(linked))
PY
)" || die "#$pr: PR json parse failed"
eval "$exports"
engine="${ENGINE_LABEL:-${WORKER_ENGINE:-codex}}"

[ "$PR_STATE" = "OPEN" ] || die "#$pr: not open ($PR_STATE) — nothing to land"
[ "$PR_DRAFT" = "0" ] || die "#$pr: draft — nothing to land"
[ "$HAS_CR" = "1" ] || die "#$pr: no confident-ready label — landing follows the review loop's verdict (run the review first, or merge by hand if you are overriding the pipeline)"
if [ "$HAS_LAND_LABEL" = "1" ]; then
  APPROVAL_SIGNAL="manual 'land' label (explicit human override)"
elif [ "$REVIEW_DECISION" = "APPROVED" ]; then
  # Stale-approval guard: a repo that does not dismiss stale reviews keeps
  # reviewDecision=APPROVED across later pushes. Require an approving review
  # that targets the CURRENT head; fail closed when the check itself fails.
  owner="${BOARD_REPO%%/*}"; repo_name="${BOARD_REPO#*/}"
  # shellcheck disable=SC2016  # GraphQL $vars are bound via -f/-F, not the shell
  approved_oids="$(gh api graphql \
    -f query='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){reviews(states:APPROVED,last:100){nodes{commit{oid}}}}}}' \
    -f owner="$owner" -f name="$repo_name" -F number="$pr" \
    -q '.data.repository.pullRequest.reviews.nodes[].commit.oid')" \
    || die "#$pr: could not verify which commit the approval targets — refusing on stale-authority risk"
  printf '%s\n' "$approved_oids" | grep -qx "$HEAD_SHA" \
    || die "#$pr: approval is stale — no approving review targets the current head ($HEAD_SHA); re-approve the PR, or add the 'land' label to override"
  APPROVAL_SIGNAL="GitHub review decision APPROVED (approval targets the current head)"
else
  die "#$pr: no landing authority — review decision is '${REVIEW_DECISION:-none}'; approve the PR or add the 'land' label"
fi

# ---- dedupe against an existing land worker ------------------------------------
meta="$(_land_meta "$pr")"
if [ -n "$meta" ]; then
  uuid="${meta%%|*}"; rest="${meta#*|}"; status="${rest%%|*}"; rest="${rest#*|}"
  current="${rest%%|*}"; rest="${rest#*|}"; w_engine="${rest%%|*}"; w_pid="${rest#*|}"
  case "$status" in
    working|blocked)
      if _is_live "$current" "$w_engine" "$w_pid"; then
        echo "#$pr: skip active land worker"; exit 0
      fi
      _retire "$uuid" ;;
    *) _retire "$uuid" ;;   # finished/retired — an explicit dispatch is a fresh signal
  esac
fi

# ---- repo merge method (native preference: squash > merge > rebase) ------------
# --rebase here is GitHub's rebase-MERGE landing method — it replays commits
# onto the BASE branch server-side and never rewrites or force-pushes the PR
# branch, so it does not violate the never-rebase-the-branch rule. It is the
# last resort only for repos that allow nothing else.
MERGE_METHOD="$(gh repo view "$BOARD_REPO" --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed 2>/dev/null \
  | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print("--squash" if d.get("squashMergeAllowed") else
      "--merge" if d.get("mergeCommitAllowed") else
      "--rebase" if d.get("rebaseMergeAllowed") else "--squash")')"

issue="${LINKED_ISSUES%% *}"

# ---- detached worktree at the PR head SHA --------------------------------------
wt="$LOCAL_REPO/.claude/worktrees/land-pr-$pr"
git -C "$LOCAL_REPO" fetch -q origin "$HEAD_REF" "$BASE_REF" \
  || die "#$pr: git fetch failed ($HEAD_REF/$BASE_REF)"
# risk-surface manifest from the BASE ref (same never-from-HEAD rule as review)
git -C "$LOCAL_REPO" show "origin/$BASE_REF:.doperpowers/risk-surfaces.md" > "$tmp/risk.md" 2>/dev/null \
  || : > "$tmp/risk.md"
if [ -e "$wt" ]; then
  git -C "$LOCAL_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
fi
git -C "$LOCAL_REPO" worktree prune
git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "$HEAD_SHA" \
  || die "#$pr: worktree add failed"

# ---- render + spawn + bind ------------------------------------------------------
prompt="$(P_PR_NUMBER="$pr" P_PR_URL="$PR_URL" P_PR_TITLE="$PR_TITLE" \
  P_REPO="$BOARD_REPO" P_BASE_REF="$BASE_REF" P_HEAD_REF="$HEAD_REF" \
  P_HEAD_SHA="$HEAD_SHA" P_ISSUE_NUMBER="${issue:-none}" \
  P_ISSUE_LIST="${LINKED_ISSUES:-none}" P_BOARD_SCRIPTS="$BOARD_SCRIPTS" \
  P_LAND_MODE="$LAND_MODE" P_APPROVAL_SIGNAL="$APPROVAL_SIGNAL" \
  P_MERGE_METHOD="$MERGE_METHOD" RISK_FILE="$tmp/risk.md" \
  python3 - "$PROTOCOL_TEMPLATE" <<'PY'
import os, re, sys
t = open(sys.argv[1]).read()
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
risk = open(os.environ["RISK_FILE"]).read()
subs["RISK_MANIFEST"] = risk or \
    "(no repo risk-surface manifest at .doperpowers/risk-surfaces.md — the always-on categories are the only risk surfaces)"
print(re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), ""), t))
PY
)" || die "#$pr: prompt render failed"
[ -n "$prompt" ] || die "#$pr: empty prompt — not dispatching"

if [ "$engine" = "codex" ]; then
  "$DAEMON_SCRIPTS/codex-spawn.sh" --no-wait "land-pr-$pr" "$prompt" "$wt" ""
else
  "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "land-pr-$pr" "$prompt" "$wt" "" "${LAND_MODEL:-}"
fi

# Bind the daemon to the ticket so a needs-human park is resumable via
# board-answer.sh (park = pause, not death). The binding is MANDATORY for a
# ticketed PR: an unbound land worker would park into a state the answer
# relay cannot reach, so a failed bind is a failed dispatch — the worker is
# retired (daemon-retire.sh stops a live codex pid too), not left running.
if [ -n "$issue" ]; then
  meta="$(_land_meta "$pr")"; uuid="${meta%%|*}"
  bound=""
  if [ -n "$uuid" ]; then
    for _try in 1 2 3; do
      if "$BOARD_SCRIPTS/board-bind.sh" "$uuid" "$issue"; then bound=1; break; fi
      sleep 2
    done
  fi
  if [ -z "$bound" ]; then
    [ -n "$uuid" ] && _retire "$uuid"
    die "#$pr: bind to ticket #$issue failed after 3 attempts — land worker retired (a parked land worker must be resumable via board-answer; if #$issue is not a board ticket, drop the Closes link or merge by hand)"
  fi
  # Ticket ownership is EXCLUSIVE: strip the binding from every other meta
  # (typically the finished implement worker's) — board-answer.sh resumes
  # the first bound match it finds, and it must be THIS land worker.
  DAEMON_HOME="$DAEMON_HOME" TICKET="$issue" KEEP="$uuid" python3 - <<'PY'
import glob, json, os
home = os.environ["DAEMON_HOME"]; tk = os.environ["TICKET"].lstrip("#")
keep = os.environ["KEEP"]
for p in glob.glob(os.path.join(home, "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if str(m.get("ticket", "")).lstrip("#") != tk or m.get("uuid") == keep:
        continue
    del m["ticket"]
    tmp = p + ".tmp"
    json.dump(m, open(tmp, "w"), indent=2)
    os.replace(tmp, p)
PY
fi
# The land label is SINGLE-USE authority: a live dispatch consumes it so a
# lingering label can never authorize commits the human has not seen. A
# dry-run leaves it in place for the eventual live run.
if [ "$HAS_LAND_LABEL" = "1" ] && [ "$LAND_MODE" = "live" ]; then
  gh pr edit "$pr" -R "$BOARD_REPO" --remove-label land \
    || echo "#$pr: could not consume the land label — remove it by hand" >&2
fi
echo "#$pr: land worker dispatched ($engine, $LAND_MODE, $APPROVAL_SIGNAL)"
