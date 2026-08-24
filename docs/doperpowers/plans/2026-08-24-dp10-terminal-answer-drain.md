# dp#10 — Terminal-Ticket Answer Drain (client side) Implementation Plan

> **For agentic workers:** Small plan — execute solo, task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out dp#10 ("unrelayed park answers on terminal tickets never drain"). The architect decision is **route 1, server-side**: `GET /answers/unrelayed` excludes answers whose ticket reached a terminal state — filed as [arkho#20](https://github.com/SSFSKIM/arkho/issues/20), implemented in the arkho board-service repo, deployed via Render on its main. The doperpowers side therefore carries exactly two things: a one-comment sharpening of the relay header's feed contract, and live end-to-end verification of the ticket's success criterion against the production board.

**Decision Log (why route 1, for the record):**
- Terminal states (`done`, `wontfix`) have no outgoing edges in the server's `LEGAL_ROWS` — "ticket is terminal" is permanent, so a server-side feed filter can never hide an answer that later becomes deliverable. The feed's contract sharpens to "answers a successor could still deliver".
- Route 2 (client acks when the ticket reads terminal) was rejected: it re-implements terminality in every consumer, and it stamps `relayed_at` — whose meaning is "answer reached its worker" — on an answer nobody received. The delivery-gated ack invariant the relay is built on ("undeliverable answers are never ack-and-dropped") stays intact under route 1: the rows stay unacked forever, as the honest durable record, and the feed simply stops serving them.
- Route 1 also fixes a latent starvation hazard the ticket didn't name: the feed is a flat 500-row page, oldest-first, no cursor — immortal rows accumulate at the head and would eventually crowd live answers out of the page.

**Constraints:**
- NO `Co-Authored-By` / attribution lines in commits. Commit style: `docs(board-client): …`.
- The repro's board commands run as the configured human/automation principals, NOT as your run: prefix each with `env -u BOARD_RUN_TOKEN` (harmless if the variable is absent; required if your shell carries it, because your run's fence reaches only your own ticket). This is a deliberate, scoped exception for the verification this plan prescribes — do not reuse the pattern beyond it.
- If verification shows the server fix is NOT live yet, do NOT fall back to acking the answer as a "fix" (that is rejected route 2). Clean up the scratch row (failure arm below) and park dp#10 `needs-info`.

`$SCRIPTS` below = `skills/issue-tracker/scripts` in your worktree.

---

### Task 0: Worktree board binding

Worker worktrees do not inherit the untracked `.doperpowers/board.json`, and without it every board command silently falls back to **gh mode against GitHub issues** — a misroute, not an error you'd notice. Mirror it before any board command:

- [ ] `mkdir -p <worktree>/.doperpowers && cp /Users/new/Developer/GitHub/doperpowers/.doperpowers/board.json <worktree>/.doperpowers/board.json`

(A durable fix — resolving `board.json` via the git common dir, as `_binding.sh` already does for the credentials slug — is follow-up ticket dp#12, not this plan's scope.)

### Task 1: Sharpen the relay header's feed contract

**File:** `skills/issue-tracker/scripts/_sweep_api.sh` (header comment only; no behavior).

The RELAY block currently reads:

```
#   RELAY  answers the human has posted, from /answers/unrelayed, into the
#          bound worker session. The ack is DELIVERY-GATED: it fires only when
#          the sentinel is already in the transcript or a resume returned
#          success. Undeliverable answers are never ack-and-dropped.
```

- [ ] **Step 1:** Append two lines to that block so it reads:

```
#   RELAY  answers the human has posted, from /answers/unrelayed, into the
#          bound worker session. The ack is DELIVERY-GATED: it fires only when
#          the sentinel is already in the transcript or a resume returned
#          success. Undeliverable answers are never ack-and-dropped. The feed
#          itself serves only answers a successor could still deliver — a
#          ticket gone terminal drops its answer server-side (arkho#20), so
#          never-dropped has no immortal-entry corollary.
```

- [ ] **Step 2:** `bash -n skills/issue-tracker/scripts/_sweep_api.sh` (syntax guard), then commit: `docs(board-client): note the unrelayed feed's terminal-ticket exclusion (dp#10 / arkho#20)`.

No tests: comment-only change; there is no behavior for a test to discriminate.

### Task 2: Live verification (doubles as the arkho#20 deployment probe)

Stage the exact incident shape from the ticket on the production board and read the feed. Do not probe deployment by arkho#20's issue state — closed does not mean deployed; the repro is the evidence.

- [ ] **Step 1 — scratch ticket.** Write a two-line body file (say `/tmp/dp10-scratch.md`: "Scratch repro for dp#10 terminal-answer drain. Wontfix on sight; the answer row this ticket leaves behind is the artifact under test."), then:

```bash
env -u BOARD_RUN_TOKEN "$SCRIPTS/board-register.sh" \
  "SCRATCH drain repro (dp#10) — wontfix on sight" bug P3 \
  --spawned-by 10 --body-file /tmp/dp10-scratch.md \
  --state needs-human --note "1. dp#10 drain repro — any reply completes the park shape."
```

Capture the printed ticket number as `N`.

- [ ] **Step 2 — answer, then terminate, back-to-back.** The answer targets a dispatch queue the live sweep could claim within a tick, so run these two immediately in sequence (one `&&` chain). The answer is an UNBOUND disposition — no session exists to resume, so it returns immediately and foreground is fine:

```bash
env -u BOARD_RUN_TOKEN "$SCRIPTS/board-answer.sh" "$N" "ack — drain repro" --to ready-for-implementer && \
env -u BOARD_RUN_TOKEN "$SCRIPTS/board-transition.sh" "$N" wontfix "drain repro complete (dp#10)"
```

- [ ] **Step 3 — read the feed twice.** From the worktree root:

```bash
cd <worktree> && . skills/issue-tracker/scripts/_binding.sh && \
env -u BOARD_RUN_TOKEN true && \
_api_py -c "import _board_api as A; rows=[r for r in A.unrelayed() if r['ticketId']==$N]; print('rows for #'+'$N'+':', rows); raise SystemExit(1 if rows else 0)"
```

Run it twice (the feed is level-triggered; two reads pin that nothing re-serves). **PASS = exit 0 both times.**

- [ ] **Step 4 — one relay pass prints nothing for it.** `env -u BOARD_RUN_TOKEN "$SCRIPTS/_sweep_api.sh" relay 2>&1 | tee /tmp/dp10-relay.out` then `! grep -q "#$N " /tmp/dp10-relay.out`. Note: this runs the real relay phase, which may legitimately deliver OTHER tickets' pending answers — that is the sweep's normal job, not a side effect to fear; the mkdir tick lock serializes against the launchd tick (if the lock is held, wait and rerun).

- [ ] **Step 5 — evidence comment.** Post the feed-read and relay-grep results on dp#10 via `board-comment.sh 10 "..."` (your own ticket — ordinary bound write, no `env -u`).

**Failure arm (feed still serves the row → arkho#20 not live yet):**
1. Quiet the board exactly as the operator did for event 62 — ack the scratch answer manually. Its `answerEventId` is in the row Step 3 printed: `_api_py -c "import _board_api as A; A.ack(<answerEventId>)"` (under `env -u BOARD_RUN_TOKEN`, `_binding.sh` sourced).
2. Commit/push whatever is done (Task 1's commit at minimum) on your branch.
3. Park your ticket: `"$SCRIPTS/board-transition.sh" 10 needs-info "waiting on arkho#20 (server-side unrelayed feed filter) to deploy — plan Task 2 re-runs verbatim on resume"`. Do NOT improvise a client-side workaround.

### Task 3: Finish

- [ ] Push the branch; open the PR for the Task-1 commit (title: `docs(board-client): unrelayed feed excludes terminal tickets (dp#10)`; body links dp#10 and arkho#20, quotes the Step-3/Step-4 evidence); hand off per your executor protocol (`in-review` with `--pr`).

**Success criteria (from the ticket, all now checkable):** a sweep over a board containing an answered-then-terminated ticket prints nothing for it; `/answers/unrelayed` no longer serves such answers (two consecutive empty reads); the scratch ticket's answer row remains unacked in the ledger — that last part is by design, not residue.
