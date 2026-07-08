#!/usr/bin/env bash
# review-dispatch.sh — dispatch a review-worker daemon onto an open PR.
#
# The trigger half of doperpowers:reviewing-prs — mechanical only, no model
# judgment. Gathers PR + linked-ticket context, creates a DETACHED worktree
# at the PR head SHA, renders the Review Worker Protocol, and spawns a
# `review-pr-<n>` daemon via daemon-spawn.sh --no-wait.
#
# Usage:
#   review-dispatch.sh <pr-number>    triggered mode (GH workflow / manual)
#   review-dispatch.sh --sweep        catch-up: every unbound open PR
#
# Env:
#   LOCAL_REPO      canonical local clone of the target repo (default: $PWD)
#   BOARD_REPO      owner/name (default: resolved from LOCAL_REPO via gh)
#   REVIEW_MODEL    optional model override for the review daemon
#   DAEMON_SCRIPTS  orchestrating-daemons scripts dir override (tests)
#   DAEMON_HOME     daemon registry dir (default ~/.claude/orchestrating-daemons)
#
# Dedupe policy (SKILL.md table): confident-ready-labeled PRs are never
# dispatched; a live ACTIVE reviewer → skip; a dead ACTIVE reviewer →
# retire + respawn; a finished reviewer → triggered mode re-dispatches
# (explicit event = fresh signal), sweep mode skips.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DAEMON_SCRIPTS="${DAEMON_SCRIPTS:-$(cd "$SKILL_DIR/../orchestrating-daemons/scripts" && pwd)}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
BOARD_SCRIPTS="$(cd "$SKILL_DIR/../issue-tracker/scripts" && pwd)"
PROTOCOL_TEMPLATE="$SKILL_DIR/references/review-worker-protocol.md"

die() { echo "error: $*" >&2; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh not found — install/auth the GitHub CLI"
git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1 || die "LOCAL_REPO is not a git repo: $LOCAL_REPO"
[ -f "$PROTOCOL_TEMPLATE" ] || die "protocol template missing: $PROTOCOL_TEMPLATE"
[ -x "$DAEMON_SCRIPTS/daemon-spawn.sh" ] || die "daemon-spawn.sh not found under $DAEMON_SCRIPTS"

if [ -z "${BOARD_REPO:-}" ]; then
  BOARD_REPO="$(cd "$LOCAL_REPO" && gh repo view --json nameWithOwner -q .nameWithOwner)"
fi
[ -n "$BOARD_REPO" ] || die "could not resolve BOARD_REPO"

# Newest review-pr-<n> registry entry → "uuid|status|current" (empty if none).
_reviewer_meta() {
  PRN="$1" python3 - <<'PY'
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
    print("%s|%s|%s" % (m.get("uuid", ""), m.get("status", ""), m.get("current", "")))
PY
}

# rc 0 when session uuid <1> is visible in `claude agents` (a live turn).
_is_live() {
  claude agents --json --all 2>/dev/null | CUR="$1" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
sys.exit(0 if any(a.get("sessionId") == os.environ["CUR"] for a in d) else 1)'
}

_retire() { "$DAEMON_SCRIPTS/daemon-retire.sh" "$1" >/dev/null 2>&1 || true; }

# ---- per-PR dispatch (dedupe already decided by the caller) --------------------
dispatch_one() {
  local pr="$1" tmp pr_json issue issue_url td companion wt prompt
  tmp="$(mktemp -d)"
  pr_json="$(gh pr view "$pr" -R "$BOARD_REPO" --json number,title,body,baseRefName,headRefName,headRefOid,url,isDraft,state,labels,closingIssuesReferences)"
  printf '%s' "$pr_json" > "$tmp/pr.json"
  eval "$(TMP="$tmp" python3 - <<'PY'
import json, os, re, shlex
d = json.load(open(os.path.join(os.environ["TMP"], "pr.json")))
open(os.path.join(os.environ["TMP"], "pr-body.md"), "w").write(d.get("body") or "")
def q(k, v): print("%s=%s" % (k, shlex.quote(str(v))))
q("PR_TITLE", d["title"]); q("BASE_REF", d["baseRefName"]); q("HEAD_REF", d["headRefName"])
q("HEAD_SHA", d["headRefOid"]); q("PR_URL", d["url"]); q("PR_STATE", d["state"])
q("PR_DRAFT", 1 if d["isDraft"] else 0)
linked = [str(n["number"]) for n in (d.get("closingIssuesReferences") or [])]
text = (d.get("title") or "") + "\n" + (d.get("body") or "")
# same close-keyword semantics as the consumer label automation: stacked PRs
# onto integration branches leave closingIssuesReferences empty.
for m in re.finditer(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+#(\d+)", text, re.I):
    if m.group(1) not in linked:
        linked.append(m.group(1))
q("LINKED_ISSUES", " ".join(linked))
PY
)"
  if [ "$PR_STATE" != "OPEN" ]; then echo "#$pr: not open ($PR_STATE) — skip"; rm -rf "$tmp"; return 0; fi
  if [ "$PR_DRAFT" != "0" ]; then echo "#$pr: draft — skip"; rm -rf "$tmp"; return 0; fi

  # primary ticket brief (first linked issue; the full list rides the prompt)
  issue="${LINKED_ISSUES%% *}"
  issue_url="none"
  : > "$tmp/issue-body.md"
  if [ -n "$issue" ]; then
    issue_url="$(gh issue view "$issue" -R "$BOARD_REPO" --json url -q .url)"
    gh issue view "$issue" -R "$BOARD_REPO" --json body -q .body > "$tmp/issue-body.md"
  fi

  # standing tech-debt sink (optional) + newest installed codex companion
  td="$(gh issue list -R "$BOARD_REPO" --label tech-debt --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"
  companion="$(ls "$HOME"/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs 2>/dev/null | sort -V | tail -1 || true)"

  # DETACHED worktree at the PR head SHA — the PR branch is usually checked
  # out in the implementer's worktree, and git forbids a second checkout;
  # detached HEAD sidesteps it (spec Decision Log). Fixes push HEAD:<branch>.
  wt="$LOCAL_REPO/.claude/worktrees/review-pr-$pr"
  git -C "$LOCAL_REPO" fetch -q origin "$HEAD_REF" "$BASE_REF"
  if [ -e "$wt" ]; then
    git -C "$LOCAL_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$LOCAL_REPO" worktree prune
  git -C "$LOCAL_REPO" worktree add -q --detach "$wt" "$HEAD_SHA"

  prompt="$(P_PR_NUMBER="$pr" P_PR_URL="$PR_URL" P_PR_TITLE="$PR_TITLE" \
    P_REPO="$BOARD_REPO" P_BASE_REF="$BASE_REF" P_HEAD_REF="$HEAD_REF" \
    P_HEAD_SHA="$HEAD_SHA" P_ISSUE_NUMBER="${issue:-none}" \
    P_ISSUE_URL="$issue_url" P_ISSUE_LIST="${LINKED_ISSUES:-none}" \
    P_TECH_DEBT_ISSUE="${td:-none}" P_CODEX_COMPANION="${companion:-none}" \
    P_BOARD_SCRIPTS="$BOARD_SCRIPTS" \
    PR_BODY_FILE="$tmp/pr-body.md" ISSUE_BODY_FILE="$tmp/issue-body.md" \
    python3 - "$PROTOCOL_TEMPLATE" <<'PY'
import os, re, sys
CAP = 20000  # keep the spawn arg well under the OS arg-size limit
def readcap(path):
    t = open(path).read()
    if len(t) > CAP:
        t = t[:CAP] + "\n[... truncated for dispatch — read the rest on GitHub]"
    return t
t = open(sys.argv[1]).read()
subs = {k[2:]: v for k, v in os.environ.items() if k.startswith("P_")}
subs["PR_BODY"] = readcap(os.environ["PR_BODY_FILE"]) or "(empty PR body)"
subs["ISSUE_BODY"] = readcap(os.environ["ISSUE_BODY_FILE"]) or "(no linked issue)"
print(re.sub(r"\{\{(\w+)\}\}", lambda m: subs.get(m.group(1), ""), t))
PY
)"
  rm -rf "$tmp"

  "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "review-pr-$pr" "$prompt" "$wt" "" "${REVIEW_MODEL:-}"
}

# Dedupe verdict for PR <1> in mode <2> (triggered|sweep), cr-label flag <3>.
# Prints: "dispatch" | "respawn <uuid>" | "skip <why>".
_decide() {
  local pr="$1" mode="$2" cr="$3" meta uuid status current rest
  if [ "$cr" = "1" ]; then echo "skip confident-ready label (remove it to force re-review)"; return; fi
  meta="$(_reviewer_meta "$pr")"
  if [ -z "$meta" ]; then echo "dispatch"; return; fi
  uuid="${meta%%|*}"; rest="${meta#*|}"; status="${rest%%|*}"; current="${rest#*|}"
  case "$status" in
    working|blocked)
      if _is_live "$current"; then echo "skip active reviewer"; else echo "respawn $uuid"; fi ;;
    retired) echo "dispatch" ;;
    *)
      if [ "$mode" = "triggered" ]; then echo "respawn $uuid"
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
        run_for "$prn" sweep "$cr"
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
