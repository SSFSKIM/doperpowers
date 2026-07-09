---
name: triaging-feedback
description: Use when operating or adopting the feedback→triage loop — a poller that reads pending rows from the product's in-app feedback table, drives a Codex-SDK worker per row through diagnose→decide→act, and either opens a fix PR or files a needs-human ticket. Covers the triage worker protocol, the fix gate, the fix-vs-ticket route, the config/kill switches, and repo setup.
---

# Triaging feedback — the feedback→triage loop

## Overview

An in-app "피드백" button lets users (students, parents, academy admins)
report bugs, ask questions, or drop ideas straight into a `feedback` table.
Left alone, every row is a human triage chore. This loop turns most of them
into either a merge-ready fix PR or a well-scoped ticket, unattended: a
poller (`src/poll.ts`, launchd-cron'd) claims pending rows, drives a
Codex-SDK worker through the Triage Worker Protocol
(`references/triage-worker-protocol.md`) in a disposable git worktree, and
lets the dispatcher act on the worker's verdict.

**There is no orchestrator beyond the poller itself.** Each row is
independent, claimed atomically (so two poller instances can run
concurrently without double-processing), and dispatched sequentially within
one tick. A row that errors is written back `failed` and retried on a later
tick (up to the reclaim window) — nothing is silently dropped.

Full design + rationale:
`docs/doperpowers/specs/2026-07-09-feedback-ci-triage-design.md`.

## The pieces

| piece | what |
|---|---|
| `src/config.ts` | `loadConfig(env)` — required `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`OPENAI_API_KEY`/`TRIAGE_REPO_PATH`/`TRIAGE_BASE_BRANCH`/`TRIAGE_BOARD_SCRIPTS_DIR`, plus `TRIAGE_K`/`TRIAGE_TIMEOUT_MS`/`TRIAGE_RECLAIM_MS` and the two kill switches below |
| `src/route.ts` | `preRoute(category)` — the cheap category prior: `idea`/`question` always route to a ticket before any diagnosis runs |
| `src/verdict.ts` | `parseVerdict(text)` — extracts the single fenced ```json block the worker emits; malformed/missing → treated as a failure, not a guess |
| `src/gate.ts` | `enforceGate(...)` — re-checks G1–G6 against the **real diff** (the worker's self-report in the verdict is advisory only) |
| `src/db.ts` | `makeDb(cfg)` — Supabase adapter: `findActionable` (pending + stale-claimed rows), `claim` (atomic `pending→claimed` update, returns false if lost the race), `writeback` (final `triage_state` + PR/issue URL) |
| `src/sideEffects.ts` | `makeSideEffects(cfg, sh)` — the only place that touches the outside world: `findExisting` (idempotency guard via a `feedback:<id>` marker in PR/issue bodies), `openFixPr`, `registerTicket` (needs-human, via the board scripts) |
| `src/codexAdapter.ts` | `runTurn(...)` — the Codex SDK seam: starts/resumes a thread at a given sandbox (`read_only` diagnose turn, `workspace_write` fix turn) |
| `src/git.ts` | `makeGit(repoPath, baseBranch)` — per-feedback disposable worktree (`addWorktree`/`removeWorktree`), `diffStat` (feeds G3/G4), `buildAndTest` (feeds G5, `npm run build`, 15-min timeout). Symlinks the base checkout's `node_modules` into every new worktree — see `references/setup.md` §1 |
| `src/dispatch.ts` | `dispatchRow(row, deps)` — the orchestration: idempotency check → diagnose turn → pre-route/verdict-route decision → (if fixing) fix turn → gate → PR-or-ticket → writeback. This is where the phases in the protocol actually get enforced in code |
| `src/poll.ts` | the entry: `loadConfig` → exit early if `TRIAGE_ENABLED=false` → `findActionable` → per-row `claim` + `dispatchRow`, sequential, catch → writeback `failed` |
| `references/triage-worker-protocol.md` | the Triage Worker Protocol — rendered (`{{PLACEHOLDERS}}`) into every diagnose-turn prompt by `src/prompt.ts` |
| `scripts/feedback-poll.sh` | launchd entry point: loads the skill dir's `.env`, runs `npx tsx src/poll.ts` |

## Model-proposes, dispatcher-disposes

The Codex thread runs inside a disposable worktree with two capabilities and
nothing else: `read_only` filesystem access to diagnose, and — only if the
gate is later satisfied — `workspace_write` access to edit files in that
same worktree. It has **no credentials**: no Supabase key, no `gh` auth, no
board-script access. It cannot open a PR, register a ticket, or write to the
`feedback` table — it can only emit a diagnosis and a structured verdict
(the fenced JSON block) that the dispatcher parses.

The dispatcher (`dispatch.ts`, running with real credentials) is the only
thing that ever performs a side effect: it decides route (pre-route by
category, then the worker's verdict), re-enforces the fix gate (G1–G6)
against the **actual diff** — not the worker's self-report — and only then
commits, pushes, opens the PR, or files the ticket. A worker that claims its
diff is small/safe/tested is not trusted; `git.ts`'s `diffStat` and
`buildAndTest` are the ground truth the gate checks against.

## Kill switches

- **`TRIAGE_ENABLED=false`** — the top-level stop. `poll.ts` exits 0 before
  touching the DB or spawning any worker. Use this to pause the whole loop.
- **`TRIAGE_FIX_ENABLED=false`** — shadow mode. `dispatch.ts`'s `wantsFix`
  is forced false, so every row that would have become a fix PR becomes a
  needs-human ticket carrying the diagnosis instead — no `workspace_write`
  turn ever runs, no code is ever written. This is the recommended starting
  state for a newly adopted repo (`references/setup.md` §5); flip it on
  only after watching ticket quality for a while.

## Relationship to `reviewing-prs`

This loop does **not** self-review or self-merge the fix PRs it opens — that
would be double review by the same untrusted-input class of worker that
wrote the fix. Deliberately, a fix PR from `triaging-feedback` is just
another PR: the existing `reviewing-prs --sweep` loop picks it up, reviews
it against the codebase, and either self-merges (small/simple tier) or
escalates to a human, exactly as it does for any human-authored PR. Keep the
two loops separate rather than teaching this one to trust its own diff.

## Adopting a repo (checklist)

Full step-by-step in `references/setup.md`. Summary:

1. **Prerequisite: Plan A must be live** — the `feedback.triage_state`/`host`
   migration (`sql/p86_*.sql` in ida-solution) applied in Supabase, including
   the historical-row `skipped` backfill. Without it, claim/writeback fail
   every tick.
2. `npm install` in the target repo's base checkout — worktrees symlink to
   its `node_modules` rather than reinstalling per feedback row.
3. Write `.env` (never committed) with the `SUPABASE_*`/`OPENAI_API_KEY`
   secrets and all `TRIAGE_*` config, in particular `TRIAGE_REPO_PATH`
   pointing at that base checkout and `TRIAGE_BASE_BRANCH` set to the
   integration branch (not the default branch) fix PRs should target.
4. Confirm `TRIAGE_BOARD_SCRIPTS_DIR` + a `TRIAGE_REPO_PATH` that resolves
   `BOARD_REPO` to the **target repo**, not this skill's repo — tickets must
   file into the target's own board.
5. One-time: `gh label create source:user-feedback` and
   `gh label create type:question` on the target repo.
6. **Start in shadow mode**: `TRIAGE_FIX_ENABLED=false` until ticket quality
   earns trust.
7. Register the launchd agent for `scripts/feedback-poll.sh` on a ~10-minute
   `StartInterval`.
