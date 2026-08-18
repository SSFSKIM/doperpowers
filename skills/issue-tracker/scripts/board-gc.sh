#!/bin/bash
# board-gc.sh — janitor for merged-branch worktrees and throwaway-DB docker
# debris. Runs as the sweep's last pass (opt-in), or standalone.
#
# Why the sweep owns this and not the Reviewer worker: the merge that makes a
# worktree garbage usually lands AFTER every worker's turn ended (armed
# auto-merge, an orchestrator pin-merge, a human click) — there is no worker
# present at merge time. The sweep is the janitor that already owns worker
# lifecycle, and it holds the one dataset a safe removal needs: the daemon
# registry (who is still working where). Measured backlog that motivated
# this: 251 worktrees / 88GB and 84 orphaned docker volumes on one worker VM.
#
# A worktree is removed ONLY when all three hold:
#   1. its branch is finished upstream — the branch is gone from origin, or
#      its PR is merged (REST lookup, capped per run by GC_PR_CHECKS so a
#      cold backlog cannot burn API quota in one tick)
#   2. the worktree is clean — `git status --porcelain` empty; a dirty tree
#      is somebody's uncommitted work and is never deleted here
#   3. no working|blocked daemon meta references its path — idle metas do
#      not hold a worktree alive: a finished worker's meta lingers idle for
#      days, and with its branch merged there is no turn left that needs the
#      tree. Active turns are what the guard protects.
# `git worktree remove` is used WITHOUT --force, so git's own dirty check
# backs guard 2 even if the porcelain read races a write.
#
# Age gate: worktrees younger than GC_MIN_AGE_MINUTES are skipped outright.
# A just-dispatched worker's tree defeats the other guards for a window:
# its branch has never been pushed (so "branch-gone" evidence matches), and
# the busy set is a snapshot taken at pass start (a spawn during the tick
# is invisible to it). Observed live: a GC pass attempted removal of a
# worker's tree seconds after dispatch — only the no-force backstop held,
# and only because the bootstrap happened to be mid-write. The gate closes
# the window structurally; 90min comfortably exceeds any tick duration.
#
# Docker debris (separate opt-in — volume prune removes ALL unused volumes,
# which is right on a worker VM and wrong on a dev machine with precious
# local volumes): exited postgres:* containers from throwaway-DB harnesses
# are removed WITH their anonymous volumes (-v; leaking those volumes is
# exactly how 84 orphans accumulated), then unused volumes are pruned.
#
# Env:
#   WORKTREE_GC=1     enable the worktree pass (absent → skipped entirely)
#   DOCKER_GC=1       enable the docker pass  (absent → skipped entirely)
#   LOCAL_REPO        repo whose .claude/worktrees is swept (default $PWD)
#   BOARD_REPO        owner/repo for PR-state lookups
#   DAEMON_HOME       registry dir for the busy-path guard
#   GC_PR_CHECKS      max PR-state lookups per run (default 20)
#   GC_MIN_AGE_MINUTES  skip worktrees younger than this (default 90; 0 disables)
set -uo pipefail
LOCAL_REPO="${LOCAL_REPO:-$PWD}"
DAEMON_HOME="${DAEMON_HOME:-$HOME/.claude/orchestrating-daemons}"
GC_PR_CHECKS="${GC_PR_CHECKS:-20}"
GC_MIN_AGE="${GC_MIN_AGE_MINUTES:-90}"

log() { echo "$*"; }

gc_worktrees() {
  [ "${WORKTREE_GC:-0}" = 1 ] || return 0
  [ -n "${BOARD_REPO:-}" ] || { log "[gc] WORKTREE: no BOARD_REPO — skipped"; return 0; }
  local wt_root="$LOCAL_REPO/.claude/worktrees"
  [ -d "$wt_root" ] || return 0

  # Paths held by ACTIVE metas only (see header for why idle does not hold).
  local busy
  busy=$(T_DHOME="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
out = set()
for p in glob.glob(os.path.join(os.environ["T_DHOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("status") in ("working", "blocked"):
        for k in ("worktree", "cwd"):
            v = m.get(k)
            if v:
                out.add(v)
print("\n".join(sorted(out)))
PY
  ) || busy=""

  # One network call for the bulk signal: branches that no longer exist on
  # origin. A branch present here is NOT finished; absence is evidence of a
  # post-merge delete. A failed ls-remote poisons that inference (every
  # branch would look deleted), so the pass aborts instead.
  local remote_heads
  remote_heads=$(git -C "$LOCAL_REPO" ls-remote --heads origin 2>/dev/null \
    | sed 's#.*refs/heads/##') \
    || { log "[gc] WORKTREE: ls-remote failed — skipped"; return 0; }
  [ -n "$remote_heads" ] || { log "[gc] WORKTREE: empty remote heads — skipped"; return 0; }

  local owner="${BOARD_REPO%%/*}"
  local removed=0 checks=0 dir br state evidence
  for dir in "$wt_root"/*/; do
    dir="${dir%/}"
    [ -e "$dir/.git" ] || continue
    if [ "$GC_MIN_AGE" -gt 0 ] \
       && [ -z "$(find "$dir/.git" -maxdepth 0 -mmin +"$GC_MIN_AGE" 2>/dev/null)" ]; then
      continue                                     # too young: spawn-race window
    fi
    case "$busy" in *"$dir"*) continue ;; esac
    br=$(git -C "$dir" branch --show-current 2>/dev/null)
    [ -n "$br" ] || continue                       # detached: not ours to judge
    [ -z "$(git -C "$dir" status --porcelain 2>/dev/null | head -1)" ] || continue

    evidence=""
    if ! grep -qxF "$br" <<<"$remote_heads"; then
      evidence="branch-gone"
    elif [ "$checks" -lt "$GC_PR_CHECKS" ]; then
      checks=$((checks + 1))
      state=$(gh api "repos/$BOARD_REPO/pulls?head=$owner:$br&state=all&per_page=1" \
        --jq '.[0] | if . == null then "none" elif .merged_at != null then "merged" else .state end' \
        2>/dev/null) || state=""
      [ "$state" = "merged" ] && evidence="pr-merged"
    fi
    [ -n "$evidence" ] || continue

    if git -C "$LOCAL_REPO" worktree remove "$dir" >/dev/null 2>&1; then
      git -C "$LOCAL_REPO" branch -D "$br" >/dev/null 2>&1
      removed=$((removed + 1))
      log "[gc] WORKTREE: removed $dir ($br, $evidence)"
    else
      log "[gc] WORKTREE: remove refused for $dir — left in place"
    fi
  done
  git -C "$LOCAL_REPO" worktree prune >/dev/null 2>&1
  log "[gc] WORKTREE: $removed removed ($checks PR lookups)"
}

gc_docker() {
  [ "${DOCKER_GC:-0}" = 1 ] || return 0
  command -v docker >/dev/null 2>&1 || return 0
  local removed=0 id name img
  while read -r id name img; do
    [ -n "$id" ] || continue
    case "$img" in
      postgres:*) docker rm -v "$id" >/dev/null 2>&1 \
        && { removed=$((removed + 1)); log "[gc] DOCKER: removed container $name ($img)"; } ;;
    esac
  done <<EOF
$(docker ps -a --filter status=exited --format '{{.ID}} {{.Names}} {{.Image}}' 2>/dev/null)
EOF
  docker volume prune -f >/dev/null 2>&1
  log "[gc] DOCKER: $removed containers removed, unused volumes pruned"
}

gc_worktrees
gc_docker
