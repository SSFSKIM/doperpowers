# PR Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Autonomous review workers for opened PRs — a new `reviewing-prs` skill (dispatch script, worker protocol, GH workflow + runner templates), a `confident-ready` board state in issue-tracker, a `--no-wait` spawn mode in orchestrating-daemons, and the ida-solution deployment.

**Architecture:** PR event → GH workflow on a self-hosted runner (no checkout, no token perms) → `review-dispatch.sh` mechanically gathers PR + linked-ticket context, creates a detached worktree at the PR head SHA, and spawns a `review-pr-<n>` daemon via `daemon-spawn.sh --no-wait`. The daemon runs `codex-companion.mjs adversarial-review --base <PR base>`, verifies/routes findings (fix / ticket / tech-debt / rebut), re-reviews per rubric, then self-merges (small tier) or escalates PR + ticket to `confident-ready`. No orchestrator anywhere in the loop.

**Tech Stack:** bash (macOS 3.2-compatible), stdlib-only python3 heredocs, `gh` CLI, `git worktree`, GitHub Actions self-hosted runner, hermetic shell tests with PATH-shimmed `gh`/`claude` stubs.

**Spec:** `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md` — read it first; the acceptance section is Task 9.

## Global Constraints

- Shell: bash 3.2 compatible (macOS default) — no associative arrays, no `${var,,}`; match the existing scripts' style (`set -euo pipefail`, python3 heredocs for anything structured).
- Python inside scripts: stdlib only (repo rule, `_board.py:10`).
- Every new/modified shell file passes `scripts/lint-shell.sh` (shellcheck baseline).
- Tests are hermetic: PATH-shimmed stub `gh` and `claude`, throwaway git repos, `DAEMON_HOME` overridden — no network, no real sessions.
- Naming (verbatim from spec): daemon registry name `review-pr-<n>`; worktree `<repo>/.claude/worktrees/review-pr-<n>`; issue label `status:confident-ready` (color `008672`); PR label `confident-ready` (unprefixed — a PR is not a board node).
- Rubric thresholds (verbatim from spec, live in the protocol template only): self-merge ≤ ~150 changed lines AND ≤ 5 files; re-review when fixes exceed ~50 lines or 3 files or fixed a critical/high or changed behavior; max 3 codex rounds; codex-lock backoff ≤ ~30 min.
- Commits: no `Co-Authored-By` lines; follow the fork's `type(scope): 한국어 요약` message style; commit to `main` directly (personal fork, no upstream concerns).
- ida-solution deployment is scoped to that repo only (private); doperpowers ships templates but gets no live runner.

---

### Task 1: `daemon-spawn.sh --no-wait` (fire-and-forget spawn)

**Files:**
- Modify: `skills/orchestrating-daemons/scripts/_lib.sh` (add `_poll_uuid` after `_poll_until_done`, i.e. at end of file)
- Modify: `skills/orchestrating-daemons/scripts/daemon-spawn.sh`
- Test: `tests/orchestrating-daemons/test-daemon-scripts.sh`

**Interfaces:**
- Consumes: existing `_lib.sh` helpers (`_meta_set`, `_record_reply`, `_now`, `_strip_ansi`).
- Produces: `daemon-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model]` — with `--no-wait` (leading flag) it registers the daemon (status `working`, or the true state if the first turn already ended) and exits immediately instead of polling for the turn. Task 5's dispatch script calls exactly this surface. `_poll_uuid <short> [max-iterations]` (env override `DAEMON_UUID_POLL`) echoes `"<uuid> <state> <cwd>"` as soon as the agents row has a sessionId; rc 1 if it never materializes.

- [ ] **Step 1: Write the failing tests**

Insert into `tests/orchestrating-daemons/test-daemon-scripts.sh` immediately after the `# ---- 2) spawn` section (i.e. after the line `SHORT="$(sed -n 's/.*"short": "\([^"]*\)".*/\1/p' "$DAEMON_HOME/$UUID.json")"`):

```bash
# ---- 2b) spawn --no-wait (fire-and-forget registration) -----------------------
# For runner/cron dispatch: register the daemon and return immediately; the
# first turn keeps running. Contract: status=working + no reply file while the
# turn runs (daemon-reply reads the live transcript, same as a watcher
# timeout); when the turn ALREADY ended at poll time, record the truth instead.
echo "spawn --no-wait:"
NW_OUT="$(STUB_BG_STATE=running "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "nowaiter" "LONG-TASK-7" "$WORK")"
assert_contains "$NW_OUT" "daemon spawned (no-wait): nowaiter" "no-wait reports the spawn"
NW_UUID="$(printf '%s' "$NW_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
NW_META="$(cat "$DAEMON_HOME/$NW_UUID.json")"
assert_contains "$NW_META" '"status": "working"' "no-wait records status=working while the turn runs"
assert_contains "$NW_META" '"turns": "1"' "no-wait records turn 1"
assert_contains "$NW_META" "\"current\": \"$NW_UUID\"" "no-wait seeds current = the first-turn uuid"
assert_file_absent "$DAEMON_HOME/$NW_UUID.reply.txt" "no-wait writes no reply file for a running turn"
assert_contains "$("$SCRIPTS_DIR/daemon-reply.sh" "$NW_UUID")" "ANSWER:LONG-TASK-7" "daemon-reply reads the running no-wait turn's transcript"

NW2_OUT="$("$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "nowaiter2" "QUICK-TASK-8" "$WORK")"
NW2_UUID="$(printf '%s' "$NW2_OUT" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1)"
assert_contains "$(cat "$DAEMON_HOME/$NW2_UUID.json")" '"status": "idle"' "no-wait records idle when the first turn already finished"
assert_file_exists "$DAEMON_HOME/$NW2_UUID.reply.txt" "no-wait records the reply of an already-finished turn"

NWX_RC=0
STUB_NO_UUID=1 DAEMON_UUID_POLL=2 "$SCRIPTS_DIR/daemon-spawn.sh" --no-wait "nouuid-nw" "seed-nw" "$WORK" >/dev/null 2>&1 || NWX_RC=$?
[ "$NWX_RC" -ne 0 ] && pass "no-wait with a uuid-less agents row exits nonzero" \
    || fail "no-wait with a uuid-less agents row exits nonzero"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/orchestrating-daemons/test-daemon-scripts.sh`
Expected: FAILs in the new `spawn --no-wait:` section (the flag is treated as the daemon *name* today, so the output/registry asserts miss), everything else still passes.

- [ ] **Step 3: Add `_poll_uuid` to `_lib.sh`**

Append at the end of `skills/orchestrating-daemons/scripts/_lib.sh`:

```bash
# Poll `claude agents` until short id <1> has a non-empty sessionId — the row
# can lag the --bg banner by a beat (same hole the no-uuid hardening in
# spawn/resume guards). Echoes "<uuid> <state> <cwd>" as soon as the uuid
# materializes; rc 1 if it never does within <2> iterations (default 30,
# 2s apart; env override DAEMON_UUID_POLL). Used by daemon-spawn --no-wait,
# which registers the daemon without waiting for the turn to finish.
_poll_uuid() {
  local short="$1" max="${2:-${DAEMON_UUID_POLL:-30}}" i=0 uuid state cwd
  while :; do
    read -r uuid state cwd < <(claude agents --json --all 2>/dev/null | DAEMON_SHORT="$short" python3 -c '
import json, os, sys
s = os.environ["DAEMON_SHORT"]
try:
    d = json.load(sys.stdin)
except Exception:
    d = []
for a in d:
    if a.get("id") == s and a.get("sessionId"):
        print(a.get("sessionId"), a.get("state", ""), a.get("cwd", "")); break
') || true
    if [ -n "${uuid:-}" ]; then printf '%s %s %s' "$uuid" "$state" "$cwd"; return 0; fi
    i=$((i + 1))
    [ "$i" -ge "$max" ] && break
    sleep 2
  done
  return 1
}
```

- [ ] **Step 4: Add the `--no-wait` path to `daemon-spawn.sh`**

In `skills/orchestrating-daemons/scripts/daemon-spawn.sh`:

(a) Update the header comment usage line to `daemon-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model]` and add below the existing param docs:

```bash
#   --no-wait  (leading flag) register the daemon as soon as its session uuid
#              materializes and return — do NOT wait for the first turn. For
#              runner/cron dispatch where blocking would hold the job slot for
#              the whole turn. Status is recorded as `working` (or the true
#              state when the turn already ended); read the reply later with
#              daemon-reply.sh.
```

(b) Replace the argument block:

```bash
name="${1:?usage: daemon-spawn.sh <name> <task> [cwd] [worktree] [model]}"
```

with:

```bash
nowait=0
if [ "${1:-}" = "--no-wait" ]; then nowait=1; shift; fi
name="${1:?usage: daemon-spawn.sh [--no-wait] <name> <task> [cwd] [worktree] [model]}"
```

(c) Insert the no-wait exit immediately after the `[ -n "$short" ] || { ... }` banner-parse guard (before the `_poll_until_done` block):

```bash
if [ "$nowait" -eq 1 ]; then
  # Fire-and-forget: register and return; the turn keeps running (it is an
  # independent --bg process). daemon-reply.sh reads the live transcript
  # meanwhile — the same contract as a watcher timeout (status=working).
  poll_out="$(_poll_uuid "$short")" \
    || { echo "spawn: daemon $short produced no usable session uuid" >&2; exit 1; }
  uuid="${poll_out%% *}"; rest="${poll_out#* }"
  state="${rest%% *}"; runcwd="${rest#* }"
  [ "$runcwd" = "$rest" ] && runcwd=""
  case "$uuid" in
    *[!0-9a-f-]*) echo "spawn: daemon $short produced no usable session uuid" >&2; exit 1 ;;
  esac
  [ -n "$runcwd" ] || runcwd="$cwd"
  # Don't blindly claim working — a fast first turn may already be over.
  status="working"
  case "$state" in
    done)    status="idle";    _record_reply "$uuid" "$uuid" "$state" ;;
    blocked) status="blocked"; _record_reply "$uuid" "$uuid" "$state" ;;
    error)   status="error";   _record_reply "$uuid" "$uuid" "$state" ;;
  esac
  _meta_set "$uuid" \
    uuid "$uuid" current "$uuid" short "$short" name "$name" task "$task" cwd "$runcwd" \
    worktree "$worktree" model "$model" \
    status "$status" created "$(_now)" updated "$(_now)" turns "1"
  echo "daemon spawned (no-wait): $name  [$short / $uuid]  status=$status  (reply: daemon-reply.sh $short)"
  exit 0
fi
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `tests/orchestrating-daemons/test-daemon-scripts.sh`
Expected: `All orchestrating-daemons tests passed.` (including the 9 new asserts)

- [ ] **Step 6: Shellcheck + commit**

```bash
scripts/lint-shell.sh
git add skills/orchestrating-daemons/scripts/_lib.sh skills/orchestrating-daemons/scripts/daemon-spawn.sh tests/orchestrating-daemons/test-daemon-scripts.sh
git commit -m "feat(orchestrating-daemons): daemon-spawn --no-wait — 러너/크론 디스패치용 즉시 반환 스폰"
```

---

### Task 2: `confident-ready` board state (schema + transition + docs)

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:20-54`
- Modify: `skills/issue-tracker/SKILL.md` (state vocabulary section)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: nothing new.
- Produces: state `confident-ready` — open + `status:confident-ready`, reachable only from `in-review`, leaving to `{in-progress, in-review, done, wontfix, deferred}`, note optional, auto-created label color `008672`. `board-transition.sh <n> confident-ready [note]` works with no script change (legality flows from `_board.py`). Tasks 3–5 and the protocol rely on this exact state name.

- [ ] **Step 1: Write the failing tests**

Insert into `tests/issue-tracker/test-board-scripts.sh` immediately BEFORE the `# template view logic ... runs under node` comment block (the `echo "board template (kanban view logic):"` line):

```bash
# ---- confident-ready (review-loop escalation state) ---------------------------
# Reachable only from in-review (a review verdict presupposes a PR); demotes
# back to in-review on a new push; closes normally. Note optional.
echo "confident-ready:"
run board-register.sh "Review target" enhancement P2 >/dev/null                  # 17
assert_fails run board-transition.sh 17 confident-ready                          # ready → confident-ready illegal
run board-transition.sh 17 in-progress >/dev/null
assert_fails run board-transition.sh 17 confident-ready                          # in-progress → illegal (must pass through in-review)
run board-transition.sh 17 in-review "pr open" --pr https://github.com/test/repo/pull/80 >/dev/null
out="$(run board-transition.sh 17 confident-ready "codex approve, 2 rounds")"
assert_contains "$out" "#17: in-review → confident-ready" "in-review → confident-ready applied"
assert_contains "$(state "s['issues']['17']['labels']")" "status:confident-ready" "label swapped in"
assert_not_contains "$(state "s['issues']['17']['labels']")" "status:in-review" "old label removed"
assert_contains "$(state "s['issues']['17']['comments'][-1]")" "[board] confident-ready: codex approve" "note comment posted"
out="$(run board-list.sh confident-ready)"
assert_contains "$out" "#17" "board-list filters confident-ready"
set +e
lint_out="$(run board-lint.sh 2>&1)"; lint_rc=$?
set -e
assert_equals "$lint_rc" "0" "board with a confident-ready ticket lints green"
out="$(run board-transition.sh 17 in-review "new push demoted" --pr https://github.com/test/repo/pull/80)"
assert_contains "$out" "#17: confident-ready → in-review" "confident-ready demotes to in-review"
run board-transition.sh 17 confident-ready >/dev/null                            # note optional
out="$(run board-transition.sh 17 "done")"
assert_equals "$(state "s['issues']['17']['state']")" "CLOSED" "confident-ready → done closes the issue"
assert_equals "$(state "s['issues']['17']['stateReason']")" "COMPLETED" "closes as completed"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: the first `confident-ready` transition FAILs with `unknown state: confident-ready`; prior sections all pass.

- [ ] **Step 3: Extend the state machine in `_board.py`**

Three edits:

(a) `OPEN_STATES` (line 20):

```python
OPEN_STATES = ("ready-for-agent", "in-progress", "blocked", "needs-info",
               "in-review", "confident-ready", "deferred")
```

(b) `LEGAL` — change the `in-review` row and add a `confident-ready` row directly under it:

```python
    "in-review":       {"in-progress", "confident-ready", "done", "wontfix", "deferred"},
    # confident-ready: PR rigorously reviewed by the reviewing-prs loop.
    # Reachable ONLY from in-review (a review verdict presupposes an open PR);
    # deliberately NOT in ACTIVE — a confident-ready ticket whose PRs all
    # merged SHOULD surface as a close candidate (the finalize cue).
    "confident-ready": {"in-progress", "in-review", "done", "wontfix", "deferred"},
```

(c) `STATUS_COLORS` — add after the `"in-review"` entry:

```python
    "confident-ready": "008672",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `all tests passed` (the confident-ready section's 12 asserts included).

- [ ] **Step 5: Document the state in `skills/issue-tracker/SKILL.md`**

(a) Replace the happy-path line (`## State vocabulary` opening):

```markdown
`ready-for-agent → in-progress → in-review → done` is the happy path; under
the review loop (doperpowers:reviewing-prs) a PR passes through
`confident-ready` between `in-review` and `done`.
```

(b) Add a state-table row between `in-review` and `done`:

```markdown
| `confident-ready` | open + `status:confident-ready` | PR rigorously reviewed (reviewing-prs loop); merge/close with confidence | optional |
```

- [ ] **Step 6: Commit**

```bash
git add skills/issue-tracker/scripts/_board.py skills/issue-tracker/SKILL.md tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): confident-ready 상태 — 리뷰 루프의 in-review→done 사이 에스컬레이션 단계"
```

---

### Task 3: `confident-ready` in the board map (BOARD.html / kanban)

**Files:**
- Modify: `skills/issue-tracker/scripts/board-map.sh:130-131` (CLASS dict)
- Modify: `skills/issue-tracker/scripts/board-map.template.html` (CSS + BADGE + STATE_CLS + KB_STATES)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: Task 2's state.
- Produces: node class `s_cready` in the BOARD.html payload; kanban column `confident-ready` ordered after `in-review`. (The template tolerates unknown states — these edits are for correct color/badge/column order, not correctness.)

- [ ] **Step 1: Write the failing test**

Append to the `confident-ready` test section added in Task 2 (after the `done` asserts):

```bash
run board-register.sh "CR map probe" enhancement P2 >/dev/null                    # 18
run board-transition.sh 18 in-progress >/dev/null
run board-transition.sh 18 in-review "pr" --pr https://github.com/test/repo/pull/81 >/dev/null
run board-transition.sh 18 confident-ready >/dev/null
run board-map.sh --write >/dev/null 2>&1
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"cls": "s_cready"' "html payload carries the confident-ready class"
assert_contains "$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")" '"confident-ready"' "kanban vocabulary carries the confident-ready column"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: FAIL `html payload carries the confident-ready class` (falls back to `s_wait` today).

- [ ] **Step 3: Add the class + template entries**

(a) `board-map.sh` CLASS dict — add `"confident-ready": "s_cready"` after the `"in-review"` entry:

```python
CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev",
         "confident-ready": "s_cready", "blocked": "s_blk",
         "needs-info": "s_info", "deferred": "s_def", "wontfix": "s_wf",
         "conflict": "s_conflict", "untracked": "s_untracked"}
```

(b) `board-map.template.html` — four edits:

CSS, directly after the `.s_rev` line (line ~65):

```css
  .s_cready { --bd: #14b8a6; --bgc: rgba(20,184,166,.09); --tx: #5eead4; --glow: rgba(20,184,166,.22); }
```

`BADGE` map — add after `s_rev: "review",`:

```js
s_cready: "confident",
```

`STATE_CLS` map — add after `"in-review": "s_rev",`:

```js
"confident-ready": "s_cready",
```

`KB_STATES` literal — insert `"confident-ready"` between `"in-review"` and `"close-candidate"`:

```js
    KB_STATES = ["ready-for-agent", "in-progress", "in-review", "confident-ready",
                 "close-candidate", "blocked", "needs-info", "deferred",
                 "conflict", "untracked", "done", "wontfix"];
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `all tests passed` (node-based template tests included, if node is installed).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-map.sh skills/issue-tracker/scripts/board-map.template.html tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): 보드 맵에 confident-ready 클래스/칸반 컬럼 추가"
```

---

### Task 4: `reviewing-prs` skill — SKILL.md + Review Worker Protocol template

**Files:**
- Create: `skills/reviewing-prs/SKILL.md`
- Create: `skills/reviewing-prs/references/review-worker-protocol.md`

**Interfaces:**
- Consumes: Task 2's state name; the daemon/board script surfaces.
- Produces: the protocol template with `{{PLACEHOLDER}}` slots that Task 5's renderer substitutes: `PR_NUMBER, PR_URL, PR_TITLE, REPO, BASE_REF, HEAD_REF, HEAD_SHA, ISSUE_NUMBER, ISSUE_URL, ISSUE_LIST, TECH_DEBT_ISSUE, CODEX_COMPANION, BOARD_SCRIPTS, PR_BODY, ISSUE_BODY` — these names are load-bearing; Task 5 sets exactly these.

- [ ] **Step 1: Write `skills/reviewing-prs/SKILL.md`** (complete content):

````markdown
---
name: reviewing-prs
description: Use when operating or setting up the autonomous PR-review loop — dispatching review workers onto opened PRs, the confident-ready escalation state, the Review Worker Protocol, the self-merge rubric, sweep/dedupe policy, or the self-hosted-runner trigger. The inverse of the issue-tracker dispatch loop, reviewing PRs instead of implementing tickets.
---

# Reviewing PRs — the autonomous review loop

## Overview

The inverse-symmetric counterpart of the implementing daemon: where a worker
turns a ticket into a PR, a **review worker** turns a PR into a confident
merge. Every non-draft PR opened in an adopting repo gets a fresh-context
background daemon (`orchestrating-daemons`) that reviews it with codex,
verifies every finding against the code, applies the valid fixes, re-reviews
when the fixes warrant it, and then either merges it (small/simple tier, CI
green) or escalates the PR + its linked ticket to **`confident-ready`** for
the human.

**This loop has NO orchestrator.** A review worker's escalation targets are
GitHub itself (labels, comments, tickets) and the human on their next wake.
Full design + rationale: `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md`.

## The pieces

| piece | what |
|---|---|
| `scripts/review-dispatch.sh <pr#> \| --sweep` | mechanical trigger: dedupe → PR + ticket context → detached worktree at the PR head SHA → spawn a `review-pr-<n>` daemon (`daemon-spawn.sh --no-wait`) |
| `references/review-worker-protocol.md` | the Review Worker Protocol — rendered (`{{PLACEHOLDERS}}`) into every spawn prompt |
| `references/pr-review-dispatch.yml` | GH workflow template: PR events → self-hosted runner → dispatch script. No checkout, no token permissions |
| `references/runner-setup.md` | one-time machine setup: runner registration, launchd service, PATH, sweep cron |
| `confident-ready` state | owned by doperpowers:issue-tracker (state table there); this loop is its only writer |

## Dedupe & sweep policy

A PR labeled `confident-ready` is never dispatched — confidence is bound to
the reviewed head SHA; remove the label to force a re-review. Otherwise, by
the newest `review-pr-<n>` registry entry:

| registry entry | triggered mode (PR event) | sweep mode (cron) |
|---|---|---|
| none / retired | dispatch | dispatch |
| ACTIVE (working/blocked), session live | skip | skip |
| ACTIVE, session gone (daemon died) | retire → dispatch | retire → dispatch |
| finished (idle/error/awaiting-human) | retire → dispatch (an explicit event is a fresh signal) | skip (finished stays finished) |

The sweep (`review-dispatch.sh --sweep`, cron every ~30 min) is the self-heal
net: PRs opened while the machine slept (GitHub queues self-hosted jobs only
24h) and reviewers that died mid-turn.

## Merge authority (two tiers)

Encoded as Rubric 3 in the protocol — ALL clauses must hold for self-merge:
final verdict approve (or only low findings, each explicitly routed);
post-fix diff ≤ ~150 changed lines AND ≤ 5 files; zero touches on risk
surfaces (CI/workflows, auth/security, migrations/schema,
release/versioning); every CI check green — a repo with no checks
disqualifies self-merge, no exceptions. Anything else → `confident-ready`
label on the PR + `status:confident-ready` on the ticket; the human merges.

## Tech-debt sink

Small valid-but-non-blocking findings go to ONE standing GitHub issue per
repo (label `tech-debt`) as structured comments — never to a tracked file:
parallel workers on branches editing one file is a merge-conflict factory,
and the edit would land inside the very PR under review. Register the
standing issue as a `deferred` P3 ticket so board-lint stays green. Promote
accumulated comments into real tickets during gardening passes
(doperpowers:issue-register).

## Codex-lock handling

The codex companion serializes ALL jobs behind one machine-wide lock with no
dead-holder detection. Workers therefore retry with backoff up to ~30 min,
then fall back to a fresh Claude high-effort reviewer subagent — and NEVER
run `/codex:cancel` (a busy lock may be another worker's live review; only
the human cancels).

## Edge cases

- **Reopened PR still labeled `confident-ready`** — dispatch skips it while
  the consumer label automation may have set the issue back to `in-review`.
  Safe and rare; the human decides: remove the PR label to force re-review,
  or restore the ticket state.
- **PR with no linked issue** — reviewed normally; every board write is
  skipped; escalation lands on the PR alone (label + comment).
- **Two reviewers, one codex lock** — parallel review daemons contend; the
  backoff serializes them. Expected, not an error.

## Adopting a repo (checklist)

1. **PRIVATE repos only** — a self-hosted runner on a public repo lets a
   stranger's fork PR reach the machine (see `references/runner-setup.md`).
2. Register the runner + service per `references/runner-setup.md`.
3. Copy `references/pr-review-dispatch.yml` → `.github/workflows/`; set
   `LOCAL_REPO` to the canonical local clone path.
4. Consumer label automation (if any) must add `status:confident-ready` to
   its managed label set, and demote `confident-ready → in-review` on
   `synchronize` — confidence is bound to a commit.
5. Create the PR label `confident-ready`; the issue label
   `status:confident-ready` is auto-created by the board scripts.
6. Register the standing tech-debt issue (`--state deferred`, P3, plus the
   `tech-debt` label).
7. Cron the sweep: `review-dispatch.sh --sweep` every ~30 min.
````

- [ ] **Step 2: Write `skills/reviewing-prs/references/review-worker-protocol.md`** (complete content — the `{{NAMES}}` are substituted by review-dispatch.sh):

````markdown
You are a REVIEW worker for PR #{{PR_NUMBER}} ({{PR_URL}}) in {{REPO}},
running unattended in a detached worktree at the PR head (SHA {{HEAD_SHA}},
head branch {{HEAD_REF}}, base {{BASE_REF}}). There is NO orchestrator in
this loop: your escalation targets are GitHub itself (labels, comments,
tickets) and the human on their next wake. The PR brief and its linked
ticket brief are at the bottom of this prompt; treat them as the source of
truth.

Toolkit:
- board scripts: {{BOARD_SCRIPTS}}
- codex companion: {{CODEX_COMPANION}}
- standing tech-debt issue: #{{TECH_DEBT_ISSUE}}
- primary ticket: #{{ISSUE_NUMBER}} — when this is "none", skip EVERY board
  write below; escalation lands on the PR alone (label + comment).

ORIENT before anything else: read the PR diff against its base
(git diff origin/{{BASE_REF}}...HEAD), the PR body, and the ticket brief.

REVIEW ENGINE — run the codex reviewer from the worktree root:
  node {{CODEX_COMPANION}} adversarial-review --wait --base origin/{{BASE_REF}} "Review PR #{{PR_NUMBER}}: {{PR_TITLE}}"
Its stdout carries "Verdict: approve|needs-attention" and findings as
"- [severity] title (file:lines)". If the companion path is "none", or it
still refuses after retrying with backoff for up to 30 minutes (another
review may hold the machine-wide lock), fall back to a fresh Claude reviewer
subagent at high effort over the same diff. Record in the review-trail
comment which engine reviewed. NEVER run /codex:cancel — a busy lock may be
another worker's live review; you cannot distinguish wedged from busy.

EVALUATE every finding against codebase reality before acting:
- Never implement from the finding text alone — read the code it names first.
- Rebut with technical evidence: a rejected finding cites the code that
  refutes it.
- A finding you cannot verify is an escalation (needs-info), never a
  shrug-and-proceed.
- YAGNI-check scope-inflating suggestions ("implement this properly"): grep
  for actual usage before accepting the scope.
- Fix one finding at a time; test each before the next.

ROUTE each finding to exactly one bin:
- FIX NOW — valid and within this PR's scope: fix, test, commit, push
  (git push origin HEAD:{{HEAD_REF}} — you are on a detached HEAD).
- TOO BIG — valid but new scope (a design fork, a new subsystem, or more
  than about half the original PR's size): register a ticket —
  {{BOARD_SCRIPTS}}/board-register.sh "<title>" <bug|enhancement> <P0..P3> --spawned-by {{ISSUE_NUMBER}}
  — then flesh out its pre-spec body (gh issue edit <new> --body-file -).
  NEVER fix it in this PR.
- TOO SMALL — valid, non-blocking, and fixing it costs momentum or an
  unwarranted re-review round: append a structured comment to the standing
  tech-debt issue (gh issue comment {{TECH_DEBT_ISSUE}}) — finding,
  file:line, severity, why deferred.
- INVALID — does not hold against the code: rebuttal comment on the PR
  citing the refuting code.

RE-REVIEW (max 3 codex rounds total) when ANY: a critical/high finding led
to a fix; cumulative fixes exceed ~50 changed lines or 3 files; any fix
changed behavior (not comments/docs/renames). Skip when fixes were trivial
or none. At the cap with unresolved critical/high findings: do NOT grant
confidence — set ticket #{{ISSUE_NUMBER}} to needs-info with an impasse
summary and end your turn.

ESCALATE when review is complete:
- SELF-MERGE tier — ALL must hold: final verdict approve (or only low
  findings, each explicitly routed); post-fix diff ≤ ~150 changed lines AND
  ≤ 5 files; zero touches on risk surfaces (CI/workflows, auth/security,
  migrations/schema, release/versioning); every CI check green
  (gh pr checks {{PR_NUMBER}}) — a repo with NO checks disqualifies
  self-merge, no exceptions. Then: merge with the repo's default method
  (gh pr merge {{PR_NUMBER}}), post the review-trail comment, and finalize:
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} done
- HUMAN tier — anything else:
  gh pr edit {{PR_NUMBER}} --add-label confident-ready
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} confident-ready "<one-line review summary>"
  — post the review-trail comment, end your turn.

YOUR AUTHORITY: ticket #{{ISSUE_NUMBER}}'s open states via
board-transition.sh (confident-ready / needs-info / blocked — note required
for the latter two); registering finding-tickets; merging ONLY in the
self-merge tier; done ONLY as post-merge finalize. NEVER: wontfix, other
tickets' states, force-push, opening your own PRs, /codex:cancel.
Escalation discriminant: waiting on an action/precondition → blocked;
waiting on knowledge or a human taste/product decision → needs-info.

If your push is rejected (the head moved), fetch and rebase your fixes onto
the new head and retry once; a second rejection → needs-info with the
conflict described.

The review-trail comment on the PR records: engine and rounds run, every
finding with its bin and a one-line disposition, and the tier judgment with
the rubric clauses it satisfied.

---- PR #{{PR_NUMBER}} brief ----
Title: {{PR_TITLE}}
Linked issues: {{ISSUE_LIST}} (primary: #{{ISSUE_NUMBER}} {{ISSUE_URL}})

{{PR_BODY}}

---- Ticket #{{ISSUE_NUMBER}} brief ----
{{ISSUE_BODY}}
````

- [ ] **Step 3: Sanity-check and commit**

Run: `ls skills/reviewing-prs/SKILL.md skills/reviewing-prs/references/review-worker-protocol.md` — both exist; skim the frontmatter (name matches dir, description present).

```bash
git add skills/reviewing-prs/
git commit -m "feat(reviewing-prs): 신규 스킬 — 자율 PR 리뷰 루프 독트린 + 리뷰 워커 프로토콜 템플릿"
```

---

### Task 5: `review-dispatch.sh` + hermetic tests

**Files:**
- Create: `skills/reviewing-prs/scripts/review-dispatch.sh`
- Create: `tests/reviewing-prs/test-review-dispatch.sh` (executable)

**Interfaces:**
- Consumes: Task 1's `daemon-spawn.sh --no-wait` CLI; Task 4's protocol template placeholders; the daemon registry JSON shape (`name`/`status`/`current`/`updated` fields, files `$DAEMON_HOME/<uuid>.json`).
- Produces: `review-dispatch.sh <pr-number>` (triggered) and `review-dispatch.sh --sweep`; env `LOCAL_REPO`, `BOARD_REPO`, `REVIEW_MODEL`, `DAEMON_SCRIPTS`, `DAEMON_HOME`. Task 6's workflow template and Task 8's cron call exactly this surface.

- [ ] **Step 1: Write the failing tests** — create `tests/reviewing-prs/test-review-dispatch.sh` (complete content), then `chmod +x` it:

````bash
#!/usr/bin/env bash
#
# Hermetic tests for review-dispatch.sh (the reviewing-prs trigger half).
#
# Side channels stubbed: `gh` (canned per-PR JSON + a call log), `claude`
# (agents view from a file), and the orchestrating-daemons scripts (a stub
# dir that logs spawn/retire and writes registry meta like the real ones).
# git is real: a bare origin + clone, so worktree/fetch behavior is genuine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DISPATCH="$REPO_ROOT/skills/reviewing-prs/scripts/review-dispatch.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_equals() {
    if [[ "$1" == "$2" ]]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}

# ---- environment --------------------------------------------------------------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export MOCK_DIR="$TEST_ROOT/mock"; mkdir -p "$MOCK_DIR"
export MOCK_LOG="$TEST_ROOT/gh-calls.log"; : > "$MOCK_LOG"
export SPAWN_LOG="$TEST_ROOT/spawn.log"; : > "$SPAWN_LOG"
export PROMPT_DIR="$TEST_ROOT/prompts"; mkdir -p "$PROMPT_DIR"
export STUB_COUNT="$TEST_ROOT/count"

# real git: bare origin + working clone with main and a PR head branch
ORIGIN="$TEST_ROOT/origin.git"
git init -q --bare "$ORIGIN"
CLONE="$TEST_ROOT/clone"
git clone -q "$ORIGIN" "$CLONE" 2>/dev/null
git -C "$CLONE" checkout -q -b main
git -C "$CLONE" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$CLONE" push -q -u origin main
git -C "$CLONE" checkout -q -b feat/x
echo hi > "$CLONE/f.txt"
git -C "$CLONE" add f.txt
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -m feat -q
git -C "$CLONE" push -q -u origin feat/x
HEAD_SHA="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
export LOCAL_REPO="$CLONE" BOARD_REPO="test/repo"

# stub daemon scripts: log + register meta like the real --no-wait spawn
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "spawn:$*" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'aaaa%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "status": "working", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$1" >> "$SPAWN_LOG"
STUB
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh"
export DAEMON_SCRIPTS="$STUB_DAEMONS"

# stub gh + claude
STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$MOCK_LOG"
case "${1:-} ${2:-}" in
  "pr view")   cat "$MOCK_DIR/pr-$3.json" ;;
  "pr list")   cat "$MOCK_DIR/pr-list.json" ;;
  "issue view")
    case "$*" in
      *"--json url"*)  N="$3" python3 -c 'import json,os;print(json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"))["url"])' ;;
      *"--json body"*) N="$3" python3 -c 'import json,os;print(json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"))["body"])' ;;
      *) echo "mock gh: unhandled issue view: $*" >&2; exit 1 ;;
    esac ;;
  "issue list") cat "$MOCK_DIR/techdebt-number.txt" ;;
  *) echo "mock gh: unhandled: $*" >&2; exit 1 ;;
esac
STUB
cat > "$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
[ "${1:-}" = "agents" ] && { cat "$MOCK_DIR/agents.json"; exit 0; }
exit 0
STUB
chmod +x "$STUB_BIN/gh" "$STUB_BIN/claude"
export PATH="$STUB_BIN:$PATH"

# canned GitHub data
echo "[]" > "$MOCK_DIR/agents.json"
echo "99" > "$MOCK_DIR/techdebt-number.txt"
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
def pr(n, **kw):
    base = {"number": n, "title": "feat: add f", "body": "Adds f.\n\nCloses #7",
            "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
            "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": False,
            "state": "OPEN", "labels": [], "closingIssuesReferences": []}
    base.update(kw)
    json.dump(base, open(os.path.join(d, "pr-%d.json" % n), "w"))
pr(5)
pr(6, isDraft=True)
pr(8, labels=[{"name": "confident-ready"}])
pr(9, title="chore: tidy", body="No ticket for this one.")
json.dump([{"number": 5, "isDraft": False, "labels": []},
           {"number": 6, "isDraft": True, "labels": []},
           {"number": 8, "isDraft": False, "labels": [{"name": "confident-ready"}]}],
          open(os.path.join(d, "pr-list.json"), "w"))
json.dump({"url": "https://github.com/test/repo/issues/7",
           "body": "Ticket seven brief body"}, open(os.path.join(d, "issue-7.json"), "w"))
PY

# fake codex companion installs — dispatch must resolve the NEWEST version
mkdir -p "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.5/scripts" \
         "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.9/scripts"
touch "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.5/scripts/codex-companion.mjs" \
      "$HOME/.claude/plugins/cache/openai-codex/codex/1.0.9/scripts/codex-companion.mjs"

reset_state() { rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo "[]" > "$MOCK_DIR/agents.json"; }

# ---- triggered dispatch (happy path) ------------------------------------------
echo "triggered dispatch:"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "spawns --no-wait with the registry name"
WT="$LOCAL_REPO/.claude/worktrees/review-pr-5"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "worktree checked out at the PR head SHA"
if git -C "$WT" symbolic-ref -q HEAD >/dev/null; then
    fail "worktree is detached"; else pass "worktree is detached"; fi
PROMPT="$(cat "$PROMPT_DIR/review-pr-5.prompt")"
assert_contains "$PROMPT" "REVIEW worker for PR #5" "prompt carries the protocol header"
assert_contains "$PROMPT" "Adds f." "prompt carries the PR body"
assert_contains "$PROMPT" "---- Ticket #7 brief ----" "prompt names the primary ticket (Closes #7 parsed from the body)"
assert_contains "$PROMPT" "Ticket seven brief body" "prompt carries the linked issue body"
assert_contains "$PROMPT" "origin/main" "prompt carries the base ref"
assert_contains "$PROMPT" "codex/1.0.9/scripts/codex-companion.mjs" "prompt resolves the NEWEST codex companion"
assert_contains "$PROMPT" "tech-debt issue: #99" "prompt carries the standing tech-debt issue"
assert_not_contains "$PROMPT" "{{" "no unsubstituted placeholder survives"

# ---- skips --------------------------------------------------------------------
echo "skips:"
reset_state
out="$("$DISPATCH" 6)"
assert_contains "$out" "draft" "draft PR skipped"
assert_equals "$(cat "$SPAWN_LOG")" "" "draft PR spawns nothing"
out="$("$DISPATCH" 8)"
assert_contains "$out" "confident-ready" "confident-ready-labeled PR skipped"
assert_equals "$(cat "$SPAWN_LOG")" "" "confident-ready PR spawns nothing"

# ---- dedupe: active / dead / finished -----------------------------------------
echo "dedupe:"
seed_reviewer() {  # $1=status
    S="$1" python3 - <<'PY'
import json, os
json.dump({"uuid": "feed0000-0000-4000-8000-000000000000",
           "current": "feed0000-0000-4000-8000-000000000000",
           "name": "review-pr-5", "status": os.environ["S"],
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "feed0000-0000-4000-8000-000000000000.json"), "w"))
PY
}
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "live ACTIVE reviewer → skip"
assert_equals "$(cat "$SPAWN_LOG")" "" "live ACTIVE reviewer spawns nothing"

reset_state; seed_reviewer working    # agents.json now [] → session gone
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "dead reviewer retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "dead reviewer respawned"

reset_state; seed_reviewer idle
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "triggered mode retires a finished reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "triggered mode re-dispatches after an explicit event"

# ---- sweep ---------------------------------------------------------------------
echo "sweep:"
reset_state; seed_reviewer idle
out="$("$DISPATCH" --sweep)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips finished(5)/draft(6)/labeled(8)"
reset_state
out="$("$DISPATCH" --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "sweep dispatches the unbound open PR"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-6" "sweep never dispatches a draft"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-8" "sweep never dispatches a confident-ready PR"

# ---- no linked issue ------------------------------------------------------------
echo "no linked issue:"
reset_state
out="$("$DISPATCH" 9)"
PROMPT9="$(cat "$PROMPT_DIR/review-pr-9.prompt")"
assert_contains "$PROMPT9" "primary ticket: #none" "no-issue PR renders ticket=none"
assert_contains "$PROMPT9" "(no linked issue)" "no-issue PR renders the empty ticket brief"

# ---- stale worktree replaced -----------------------------------------------------
echo "stale worktree:"
reset_state
mkdir -p "$WT"; echo junk > "$WT/junk.txt"
out="$("$DISPATCH" 5)"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "stale worktree dir replaced with a fresh checkout"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `chmod +x tests/reviewing-prs/test-review-dispatch.sh && tests/reviewing-prs/test-review-dispatch.sh`
Expected: immediate failure — `review-dispatch.sh` does not exist yet.

- [ ] **Step 3: Write `skills/reviewing-prs/scripts/review-dispatch.sh`** (complete content), then `chmod +x`:

````bash
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
  eval "$(printf '%s' "$pr_json" | TMP="$tmp" python3 - <<'PY'
import json, os, re, shlex, sys
d = json.load(sys.stdin)
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
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `tests/reviewing-prs/test-review-dispatch.sh`
Expected: `all tests passed` (every assert green across the six sections).

Note: the mock `gh pr view` returns the full canned JSON regardless of the requested `--json` field list — both call sites parse with python, so the extra keys are harmless. The mock `gh` exports `MOCK_DIR` via the test's environment.

- [ ] **Step 5: Shellcheck + commit**

```bash
scripts/lint-shell.sh
git add skills/reviewing-prs/scripts/review-dispatch.sh tests/reviewing-prs/test-review-dispatch.sh
git commit -m "feat(reviewing-prs): review-dispatch.sh — 디듑/스윕 정책 + PR 헤드 SHA detached 워크트리 + no-wait 스폰"
```

---

### Task 6: Workflow template + runner setup guide

**Files:**
- Create: `skills/reviewing-prs/references/pr-review-dispatch.yml`
- Create: `skills/reviewing-prs/references/runner-setup.md`

**Interfaces:**
- Consumes: Task 5's script surface (`review-dispatch.sh <pr#>`, env `LOCAL_REPO`/`BOARD_REPO`).
- Produces: the two templates Task 8 copies into ida-solution.

- [ ] **Step 1: Write `skills/reviewing-prs/references/pr-review-dispatch.yml`** (complete content):

```yaml
# pr-review-dispatch.yml — dispatch a local review-worker daemon on PR events.
# Template from doperpowers:reviewing-prs — copy into .github/workflows/.
#
# SETUP (per adopting repo — see runner-setup.md in the reviewing-prs skill):
#   1. PRIVATE REPOS ONLY. A self-hosted runner on a public repo lets a
#      stranger's fork PR reach the machine.
#   2. Register a self-hosted runner labeled `claude-review` on the machine
#      running the daemon fleet, and set LOCAL_REPO below to that machine's
#      canonical clone path.
#   3. Security properties this template maintains — keep them:
#      - NO actions/checkout: the job never executes PR code (the PR runs
#        only inside the daemon's worktree behind --permission-mode auto).
#      - permissions: {} — the job needs no GitHub token; the dispatch
#        script uses the runner machine's own `gh` auth.
#      - Only ${{ github.event.pull_request.number }} (numeric) is
#        interpolated. NEVER interpolate PR title/body here (injection).
#      - The actor gate keeps other accounts' PRs off the runner.
#   4. `synchronize` is deliberately NOT a trigger: fix pushes by the review
#      worker itself must not re-dispatch. The sweep cron is the catch-up.
name: PR review dispatch
on:
  pull_request:
    types: [opened, reopened, ready_for_review]
permissions: {}
concurrency:
  group: review-dispatch-${{ github.event.pull_request.number }}
  cancel-in-progress: false
jobs:
  dispatch:
    if: github.event.pull_request.draft == false && github.actor == github.repository_owner
    runs-on: [self-hosted, claude-review]
    timeout-minutes: 10
    env:
      LOCAL_REPO: /CHANGE/ME/absolute/path/to/local/clone
      BOARD_REPO: ${{ github.repository }}
    steps:
      - name: Dispatch review daemon
        run: |
          "${DOPERPOWERS_HOME:-$HOME/.claude/plugins/marketplaces/doperpowers}/skills/reviewing-prs/scripts/review-dispatch.sh" "${{ github.event.pull_request.number }}"
```

- [ ] **Step 2: Write `skills/reviewing-prs/references/runner-setup.md`** (complete content):

````markdown
# Self-hosted runner setup (PR review dispatch)

One-time setup of the machine that runs the daemon fleet (macOS assumed).
**Private repos only** — a `pull_request`-triggered workflow on a self-hosted
runner attached to a public repo can hand a stranger's fork PR a path onto
this machine. The workflow template's actor gate and no-checkout design are
defense in depth, not a substitute.

## 1. Install the runner

```bash
mkdir -p ~/actions-runner-<repo> && cd ~/actions-runner-<repo>
# latest version tag:
gh api repos/actions/runner/releases/latest -q .tag_name        # e.g. v2.321.0
curl -o runner.tar.gz -L \
  "https://github.com/actions/runner/releases/download/<TAG>/actions-runner-osx-arm64-<TAG-without-v>.tar.gz"
tar xzf runner.tar.gz
```

## 2. Register it (label: `claude-review`)

```bash
TOKEN="$(gh api -X POST repos/<OWNER>/<REPO>/actions/runners/registration-token -q .token)"
./config.sh --url "https://github.com/<OWNER>/<REPO>" --token "$TOKEN" \
  --labels claude-review --name "$(hostname -s)-claude" --unattended
```

## 3. Environment for the job

The runner builds the job PATH from a `.path` file and env from `.env` in
the runner directory. The dispatch script needs `gh`, `git`, `node`,
`python3`, and `claude` reachable:

```bash
echo "$PATH" > .path                       # snapshot a PATH that has them all
cat > .env <<'EOF'
DOPERPOWERS_HOME=/Users/<you>/.claude/plugins/marketplaces/doperpowers
EOF
```

## 4. Run as a service (launchd)

```bash
./svc.sh install && ./svc.sh start
./svc.sh status
```

Note: `svc.sh` installs a LaunchAgent — it runs while the user is logged in.
A PR opened while the machine is asleep queues on GitHub's side for up to
24h; beyond that the sweep cron below catches it.

## 5. Verify

```bash
gh api repos/<OWNER>/<REPO>/actions/runners \
  -q '.runners[] | "\(.name) \(.status) \(.labels|map(.name)|join(","))"'
# expect: <name> online ... claude-review
```

## 6. Sweep cron (self-heal)

```bash
crontab -e
# every 30 min: dispatch any unbound open PR, respawn dead reviewers
*/30 * * * * LOCAL_REPO=/path/to/clone BOARD_REPO=<OWNER>/<REPO> $HOME/.claude/plugins/marketplaces/doperpowers/skills/reviewing-prs/scripts/review-dispatch.sh --sweep >> $HOME/Library/Logs/review-sweep.log 2>&1
```
````

- [ ] **Step 3: Commit**

```bash
git add skills/reviewing-prs/references/
git commit -m "feat(reviewing-prs): GH 워크플로 템플릿 + 셀프호스티드 러너 설치 가이드"
```

---

### Task 7: Repo-wide verification + release

**Files:**
- Modify: `RELEASE-NOTES.md` (new top section)
- Modify (via script): `package.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json`

**Interfaces:** none new — this task proves Tasks 1–6 and ships them.

- [ ] **Step 1: Run every affected suite**

```bash
tests/orchestrating-daemons/test-daemon-scripts.sh
tests/issue-tracker/test-board-scripts.sh
tests/reviewing-prs/test-review-dispatch.sh
scripts/lint-shell.sh
```

Expected: all pass / lint clean. Fix anything that fails before proceeding.

- [ ] **Step 2: Version bump**

Parallel sessions release concurrently in this fork — sync first, then bump
one minor above whatever is current:

```bash
git fetch origin && git pull --rebase --autostash origin main
scripts/bump-version.sh --check          # see the current version (7.8.2 at plan time)
scripts/bump-version.sh 7.9.0            # or the next minor above what --check shows
scripts/bump-version.sh --audit          # no stray old-version strings
```

- [ ] **Step 3: Release notes**

Add at the top of `RELEASE-NOTES.md` (below the `# Doperpowers Release Notes` title), matching the existing section format:

```markdown
## v7.9.0 (2026-07-08)

### reviewing-prs — autonomous PR review loop (new skill)

The inverse of the issue-tracker dispatch loop: opened PRs get fresh-context
review daemons that run codex adversarial-review against the PR base, verify
and route findings (fix / spawned ticket / tech-debt sink / rebuttal),
re-review per rubric, then self-merge small low-risk PRs (CI green) or
escalate PR + ticket to the new `confident-ready` state for the human. No
orchestrator in the loop. Ships review-dispatch.sh (dedupe/sweep policy,
detached worktree at the PR head SHA), the Review Worker Protocol template,
a self-hosted-runner GH workflow template, and a runner setup guide.
Spec: docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md.

- issue-tracker: new `confident-ready` state (open + status:confident-ready)
  between in-review and done — reachable only from in-review, demotable back
  on new pushes; board map/kanban render it (s_cready).
- orchestrating-daemons: `daemon-spawn.sh --no-wait` — fire-and-forget spawn
  for runner/cron dispatch; registers the daemon and returns while the first
  turn keeps running.
```

- [ ] **Step 4: Commit + push**

```bash
git add -A
git commit -m "release: 7.9.0 — reviewing-prs 자율 PR 리뷰 루프 + confident-ready 상태 + daemon-spawn --no-wait"
git push origin main
```

---

### Task 8: ida-solution deployment

**Files (in `/Users/new/documents/github/ida-solution`):**
- Create: `.github/workflows/pr-review-dispatch.yml` (from the template)
- Modify: `.github/workflows/issue-status-labels.yml`
- GitHub side: labels, standing tech-debt issue, self-hosted runner, sweep cron

**Interfaces:**
- Consumes: everything shipped in Task 7 (the plugin update must be installed/synced on this machine first — `claude plugin update doperpowers` or equivalent — so `~/.claude/plugins/marketplaces/doperpowers` carries the new skill).
- Produces: the live loop Task 9 shakes down.

- [ ] **Step 1: Update the local plugin, copy the workflow template**

```bash
cd /Users/new/documents/github/ida-solution
git pull --rebase origin main
cp "$HOME/.claude/plugins/marketplaces/doperpowers/skills/reviewing-prs/references/pr-review-dispatch.yml" .github/workflows/pr-review-dispatch.yml
```

Then edit the copied file: set `LOCAL_REPO: /Users/new/documents/github/ida-solution`.

- [ ] **Step 2: Patch `issue-status-labels.yml`** — three edits:

(a) Trigger types — add `synchronize`:

```yaml
  pull_request:
    types: [opened, reopened, ready_for_review, converted_to_draft, closed, synchronize]
```

(b) Managed set — replace the `MANAGED` line:

```js
            const CR = 'status:confident-ready';
            const MANAGED = [A, P, R, CR, 'status:blocked', 'status:needs-info', 'status:deferred'];
```

(c) In the `pull_request` branch: strip the PR-side label on any push, and demote a confident-ready issue. Insert right after `const pr = payload.pull_request;`:

```js
              if (payload.action === 'synchronize') {
                // 새 커밋 push → 신뢰 무효화(신뢰는 리뷰된 head SHA에 바인딩 — reviewing-prs 루프).
                // PR 쪽 confident-ready 라벨을 떼고, 아래 루프에서 이슈만 강등한다.
                await github.rest.issues.removeLabel({
                  owner, repo, issue_number: pr.number, name: 'confident-ready',
                }).catch(() => {});
              }
```

and add a `synchronize` case in the per-issue loop, between the `converted_to_draft` branch and the final `else`:

```js
                } else if (payload.action === 'synchronize') {
                  // confident-ready인 이슈만 in-review로 강등 — 다른 상태(needs-info 등)는
                  // push가 덮어쓰면 안 된다.
                  const { data } = await github.rest.issues.listLabelsOnIssue({ owner, repo, issue_number: n });
                  if (data.map(l => l.name).includes(CR)) await assertStatus(n, R);
                }
```

- [ ] **Step 3: Labels + standing tech-debt issue**

```bash
gh label create confident-ready -R SSFSKIM/ida-solution --color 14b8a6 \
  --description "reviewing-prs: rigorously reviewed, ready to merge" --force
gh label create tech-debt -R SSFSKIM/ida-solution --color c2e0c6 \
  --description "standing sink for small non-blocking review findings" --force
# status:confident-ready is auto-created by the board scripts (ensure_labels)
# on their next write — no manual step.

# standing tech-debt issue: registered as deferred/P3 so board-lint stays green
BOARD_REPO=SSFSKIM/ida-solution \
  "$HOME/.claude/plugins/marketplaces/doperpowers/skills/issue-tracker/scripts/board-register.sh" \
  "Tech-debt tracker — small non-blocking review findings" enhancement P3 \
  --state deferred --note "standing sink: reviewing-prs 루프의 too-small findings 수집처"
gh issue edit <N> -R SSFSKIM/ida-solution --add-label tech-debt   # <N> from register output
# pin it:
NODE_ID="$(gh api repos/SSFSKIM/ida-solution/issues/<N> -q .node_id)"
gh api graphql -f query='mutation($id: ID!) { pinIssue(input: {issueId: $id}) { issue { number } } }' -f id="$NODE_ID"
```

- [ ] **Step 4: Register the runner + sweep cron**

Follow `references/runner-setup.md` exactly, with `<OWNER>/<REPO>` = `SSFSKIM/ida-solution`, runner dir `~/actions-runner-ida-solution`, and the sweep cron line's `LOCAL_REPO=/Users/new/documents/github/ida-solution`. Verify:

```bash
gh api repos/SSFSKIM/ida-solution/actions/runners -q '.runners[] | "\(.name) \(.status)"'
# expect: <name> online
```

- [ ] **Step 5: Commit + push the consumer changes**

```bash
cd /Users/new/documents/github/ida-solution
git add .github/workflows/pr-review-dispatch.yml .github/workflows/issue-status-labels.yml
git commit -m "ci: PR 리뷰 디스패치 워크플로 + confident-ready 라벨 자동화 (reviewing-prs 루프 도입)"
git push origin main
```

---

### Task 9: Final verification — the spec's acceptance, as written

Execute `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md` §Acceptance in ida-solution. Quoted verbatim, with setup for each scenario. Run the three PR scenarios sequentially (they share the runner and the codex lock).

**Scenario setup.** Create a throwaway ticket + branch per scenario:

```bash
cd /Users/new/documents/github/ida-solution
BOARD="$HOME/.claude/plugins/marketplaces/doperpowers/skills/issue-tracker/scripts"
BOARD_REPO=SSFSKIM/ida-solution "$BOARD/board-register.sh" "shakedown: <scenario>" enhancement P3
git checkout -b shakedown/<scenario> origin/main
# ...make the scenario's change, commit, push...
gh pr create --title "shakedown: <scenario>" --body "…\n\nCloses #<N>"
```

- (a) trivial: a one-line docs fix (self-merge tier expected).
- (b) sizable + planted findings: a multi-file change (>150 lines) including a deliberate critical-severity flaw (e.g. a shell script interpolating unquoted user input into a command) — human tier + re-review expected.
- (c) planted too-big finding: a small change whose PR body admits a known architectural gap ("auth is skipped here; needs a real design") — expect a spawned ticket, not a fix.

- [ ] **1. Trigger**: "open a non-draft PR … Within ~2 minutes, `daemon-list.sh` shows `review-pr-<n> … working`, and the Actions job that dispatched it completed in seconds." Check: `gh run list --workflow=pr-review-dispatch.yml -L1` (completed, <60s) and `"$HOME/.claude/plugins/marketplaces/doperpowers/skills/orchestrating-daemons/scripts/daemon-list.sh"`.
- [ ] **2. Self-merge tier** (scenario a): "a trivial PR … ends merged without human action; the PR carries a review-trail comment; the linked issue is closed (reason: completed); `board-lint.sh` exits 0."
- [ ] **3. Human tier** (scenario b): "ends open with fix commits pushed by the worker, a `confident-ready` PR label, the issue at `status:confident-ready` (`board-list.sh confident-ready` shows it), and a review-trail comment recording ≥2 review rounds."
- [ ] **4. Too-big routing** (scenario c): "a planted architectural finding produces a new issue whose `board:meta` records `spawned-by: <reviewed ticket>`, and no fix for it appears in the PR."
- [ ] **5. Too-small routing**: "a planted nit produces a new comment on the standing tech-debt issue, not a PR commit." (Fold a nit into scenario b's PR.)
- [ ] **6. Confidence invalidation**: "pushing a new commit to a confident-ready PR flips the linked issue back to `status:in-review`." (Push a whitespace commit to scenario b's branch after it reaches confident-ready.)
- [ ] **7. Self-heal**: "kill a working reviewer daemon; `review-dispatch.sh --sweep` spawns a replacement bound to the same PR." (`claude stop <short>` mid-review on any scenario, then run the sweep manually.)
- [ ] **8. Schema**: "`board-transition.sh <n> confident-ready "note"` succeeds from `in-review`, appears in `board-list.sh`/`BOARD.md`, and `board-lint.sh` passes."
- [ ] **Record the outcome**: append findings (rubric threshold tuning, protocol wording gaps, runner quirks) to the spec's `## Surprises & Discoveries`, and clean up the shakedown tickets/branches (`wontfix` the throwaway tickets with a note, delete the branches).

Anything the shakedown breaks goes back into the relevant task's code with a test before re-running the scenario.
