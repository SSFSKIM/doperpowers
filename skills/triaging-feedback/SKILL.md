---
name: triaging-feedback
description: Use when operating or adopting the feedback→triage loop — a poller that reads pending rows from the product's in-app feedback table, drives a read-only Codex-SDK worker per row through diagnose→author, and registers a worker-authored board ticket (ready-for-agent when grounded and gate-worthy, needs-human/needs-info otherwise). Covers the triage worker protocol, the registration gate, the state routing, the config/kill switch, and repo setup.
---

# Triaging feedback — the feedback→triage loop

## Overview

An in-app "피드백" button lets users (students, parents, academy admins)
report bugs, ask questions, or drop ideas straight into a `feedback` table.
Left alone, every row is a human triage chore. This loop turns each row into
a **well-authored board ticket**, unattended: a poller (`src/poll.ts`,
launchd-cron'd) claims pending rows, drives a read-only Codex-SDK worker
through the Triage Worker Protocol (`references/triage-worker-protocol.md`)
in a disposable detached worktree, and registers the ticket the worker
authored — born `ready-for-agent` when the diagnosis is grounded and the
ticket honestly passes the implement-side gate definitions, else parked
(`needs-human`/`needs-info`) with an explicit note saying what is unclear.

**The worker is a translator, not a fixer.** It writes no code and opens no
PRs. Fixes happen downstream through the normal tri-CI pipeline: a
`ready-for-agent` ticket is dispatched by `implementing-tickets` (whose
Ticket Gate re-runs at ORIENT — the triage worker's judgment is a
recommendation, never inherited trust), and the resulting PR is reviewed by
`reviewing-prs`. *(The v1 direct-fix path — a second `workspace-write` turn
opening fix PRs — was deleted 2026-07-11 before ever going live; see the
spec's Decision Log.)*

**There is no orchestrator beyond the poller itself.** Each row is
independent, claimed atomically (so two poller instances can run
concurrently without double-processing), and dispatched sequentially within
one tick. `failed` is a **terminal** state — `findActionable`/`claim` only
ever pick up `pending` or stale-`claimed` rows, never `failed`, so a failed
row is not silently retried. To retry, an operator resets that row's
`triage_state` back to `pending`.

Full design + rationale:
`docs/doperpowers/specs/2026-07-09-feedback-ci-triage-design.md`.

## The pieces

| piece | what |
|---|---|
| `src/config.ts` | `loadConfig(env)` — required `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`OPENAI_API_KEY`/`TRIAGE_REPO_PATH`/`TRIAGE_BASE_BRANCH`/`TRIAGE_BOARD_SCRIPTS_DIR`, plus `TRIAGE_MODEL` (default `gpt-5.6-sol`), `TRIAGE_EFFORT` (default `medium`), `TRIAGE_K`/`TRIAGE_TIMEOUT_MS`/`TRIAGE_RECLAIM_MS`, and the `TRIAGE_ENABLED` kill switch |
| `src/verdict.ts` | `parseVerdict(text)` — extracts the single fenced ```json block the worker emits, including the worker-authored `ticket` (title/body/state/note); malformed/missing → treated as a failure, not a guess |
| `src/gate.ts` | `routeTicket(rowCategory, verdict)` — the registration gate (R1–R5): idea/question forced `needs-human`; `ready-for-agent` honored only for a cited, non-risk-surface bug (dispatcher scans paths out of the verdict text itself); park states get a note. Plus `RISK_SURFACES` and `extractCandidatePaths` |
| `src/db.ts` | `makeDb(cfg)` — Supabase adapter: `findActionable` (pending + stale-claimed rows), `claim` (atomic `pending→claimed` update, returns false if lost the race), `writeback` (final `triage_state` + issue URL) |
| `src/sideEffects.ts` | `makeSideEffects(cfg, sh)` — the only place that touches the outside world: `findExisting` (idempotency guard via a `feedback:<id>` marker in issue bodies), `registerTicket` (any birth state, via the board scripts) |
| `src/codexAdapter.ts` | `makeCodexRunner(cfg)` — the Codex SDK seam: a fresh **read-only** thread per row, model/effort pinned from config (never inherited from `~/.codex/config.toml`), locked-down child env (`buildCodexOptions`: PATH/HOME only, no inherited secrets), `approvalPolicy:never` + network off, per-turn abort timeout |
| `src/git.ts` | `makeGit(repoPath, baseBranch)` — per-feedback disposable **detached** worktree (`addWorktree`/`removeWorktree`), pinned to `origin/<baseBranch>` for `file:line` citation integrity (no branch, no build, no `node_modules`) |
| `src/dispatch.ts` | `dispatchRow(row, deps)` — the orchestration: idempotency check → single diagnose+author turn → registration gate → ticket → writeback. Composes the final ticket body: worker-authored content + dispatcher-appended provenance block (quoted raw feedback marked as data) |
| `src/poll.ts` | the entry: `loadConfig` → exit early if `TRIAGE_ENABLED=false` → `findActionable` → per-row `claim` + `dispatchRow`, sequential, catch → writeback `failed` |
| `references/triage-worker-protocol.md` | the Triage Worker Protocol — rendered (`{{PLACEHOLDERS}}`) into every turn's prompt by `src/prompt.ts` |
| `scripts/feedback-poll.sh` | launchd entry point: loads the skill dir's `.env`, runs `npx tsx src/poll.ts` |

## Model proposes, dispatcher disposes — scoped to execution, not authorship

The Codex thread runs inside a disposable read-only worktree with **no
credentials**: no Supabase key, no `gh` auth, no board-script access, no
network. It cannot register a ticket or write to the `feedback` table — it
can only emit a diagnosis and a structured verdict (the fenced JSON block)
that the dispatcher parses. But *within* that verdict the worker has full
editorial voice: it authors the ticket's title and body to the board's
standard (the implement-side well-defined + well-scoped gate is the
authoring bar) and recommends the birth state.

The dispatcher (`dispatch.ts`, running with real credentials) is the only
thing that ever performs a side effect. It re-validates the recommendation
(the registration gate in `gate.ts`), fixes priority at P2 (so an injected
feedback body can never jump the implement-dispatch queue), and appends the
provenance block — the quoted raw feedback explicitly marked as data — so a
downstream implement worker always sees the trust boundary inside the
ticket.

## Why the worker has no network and no approvals reviewer

The feedback body is arbitrary end-user text — the least-trusted input in
the system, unlike the repo-internal input (PRs, tickets) the codex
review/implement workers consume. Network access would combine untrusted
input + private codebase + an exfiltration channel, and an LLM approvals
reviewer (`auto_review`) is itself promptable. A read-only
diagnose-and-author worker also has nothing to escalate, so
`approvalPolicy:'never'` is descriptive. If live tickets show diagnosis
starved for reproduction capability, revisit with evidence (narrowest
option first).

## Kill switch

**`TRIAGE_ENABLED=false`** — the top-level stop. `poll.ts` exits 0 before
touching the DB or spawning any worker. *(The v1 `TRIAGE_FIX_ENABLED` shadow
toggle is gone — ticket-only is the terminal shape, so there is no
riskier mode to graduate into.)*

## Relationship to the board loops

This loop **writes the board's inbox**; it never implements or reviews.
A `ready-for-agent` triage ticket is picked up by the
`implementing-tickets` dispatch loop exactly like any other ticket — the
implement worker re-runs its own gate from fresh context, treating the
triage diagnosis as context, not inherited trust. Parked tickets surface in
the human's wake queue (`issue-tracker`). Keep the legs separate: triage
translates, implement builds, review judges.

## Adopting a repo (checklist)

Full step-by-step in `references/setup.md`. Summary:

1. **Prerequisite: the feedback-triage migration must be live** — the
   `feedback.triage_state`/`host` migration (`sql/p86_*.sql` in
   ida-solution) applied in Supabase, including the historical-row
   `skipped` backfill. Without it, claim/writeback fail every tick.
2. Write `.env` (never committed) with the `SUPABASE_*`/`OPENAI_API_KEY`
   secrets and all `TRIAGE_*` config, in particular `TRIAGE_REPO_PATH`
   pointing at the target repo's base checkout and `TRIAGE_BASE_BRANCH` set
   to the integration branch whose snapshot the worker should diagnose
   against.
3. Confirm `TRIAGE_BOARD_SCRIPTS_DIR` + a `TRIAGE_REPO_PATH` that resolves
   `BOARD_REPO` to the **target repo**, not this skill's repo — tickets must
   file into the target's own board.
4. One-time: `gh label create source:user-feedback` and
   `gh label create type:question` on the target repo.
5. Register the launchd agent for `scripts/feedback-poll.sh` on a
   ~10-minute `StartInterval`, starting with `TRIAGE_K=1` and watching
   ticket quality (classification, grounding, state recommendations) on the
   first rows.
