# Codex workers — pending live shakedown (runbook)

> **Why this doc exists.** The Codex-worker feature
> (`specs/2026-07-10-codex-workers-design.md`, plan
> `plans/2026-07-10-codex-workers.md`) is code-complete and merge-approved,
> but its spec closes only after a **live shakedown**: real workers driving
> real tickets/PRs, not stubs. GitHub Issues are disabled on this fork and no
> issue-tracker board is configured for doperpowers itself, so the pending
> work is tracked here. Each item below is written so a fresh session can pick
> it up and run it.
>
> **Status of prerequisites (verified 2026-07-10):** `codex-cli 0.144.1` is
> installed and authed (`~/.codex/auth.json` present); `claude 2.1.203` is
> installed. The worker binaries are ready — what's missing is real work items
> and, for the *automated* review trigger only, a self-hosted runner.

## The four shakedown cells

The feature adds a Codex worker species beside the Claude one on both the
implement and the review pipelines. A full shakedown exercises all four
combinations. They split by how each pipeline is triggered.

### Implement pipeline (ritual-driven — no infrastructure needed)

There is no dispatch script or workflow for the implement side; an agent
following the **issue-tracker dispatch ritual** renders
`implementing-tickets/references/implement-worker-protocol.md` (with the
engine's `references/engine-blocks/execution-<engine>.md`) and calls the
spawner directly into a worktree. Runnable now.

- [ ] **SD-1 · implement × Codex.** Pick one real, gate-ready ticket. Run the
  issue-tracker dispatch with the default engine (or `WORKER_ENGINE=codex`).
  It spawns `codex-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>`
  (model/effort default `gpt-5.6-sol`/`high`, overridable via
  `CODEX_MODEL`/`CODEX_EFFORT`).
  - **Acceptance:** the Codex worker reads the rendered protocol, works the
    ticket under strict TDD (or authors + executes a plan file for a
    multi-milestone ticket), commits on its worktree branch, opens a PR via
    `gh`, and posts the gate comment `[gate] pass — codex/<mode>: …`. Verify
    with `daemon-list.sh` (ENG column shows `codex`) and `daemon-reply.sh`.
- [ ] **SD-2 · implement × Claude.** Same ticket-shaped work, dispatched with
  `WORKER_ENGINE=claude` or a `engine:claude` label → `daemon-spawn.sh`.
  - **Acceptance:** the Claude worker does the same end-to-end (TDD →
    commits → PR), gate comment reads `[gate] pass — claude/<mode>: …`.
    Confirms the engine switch routes correctly and nothing Claude-side
    regressed.

### Review pipeline (workflow + runner for automation; the script runs standalone)

The automated path is `reviewing-prs/references/pr-review-dispatch.yml` — a
GitHub Actions workflow that fires on `pull_request` events, runs on a
self-hosted runner (`[self-hosted, claude-review]`), and invokes
`review-dispatch.sh <PR#>`. That script also runs by hand against any PR
number in a local clone, so a **manual** review shakedown needs no runner.

- [ ] **SD-3 · review × Codex.** Against a real open PR (ideally the one SD-1
  produced), run `review-dispatch.sh <PR#>` with the default engine (or
  `WORKER_ENGINE=codex`) from a local clone (`LOCAL_REPO`).
  - **Acceptance:** dispatch resolves `engine=codex`, renders the cookbook
    engine block, and `codex-spawn.sh` launches a Codex reviewer that runs
    `codex exec` self-diffing `git diff origin/<base>...HEAD`, applies
    correctness **and** the ticket's spec-compliance criteria, posts findings
    + a verdict, and transitions the board (or comments on a PR with no linked
    issue). The review-trail comment names `codex` as the engine.
- [ ] **SD-4 · review × Claude.** Same PR (or SD-2's), dispatched with
  `WORKER_ENGINE=claude` or `engine:claude` → `daemon-spawn.sh` Claude
  reviewer, with the `fallback-claude` block.
  - **Acceptance:** a Claude reviewer produces findings + verdict over the
    same diff and criteria; review-trail names `claude`. Confirms both the
    engine switch and the differing fallback blocks.

## Recommended path (covers all four, no runner)

Pick one ticket per engine (or run one ticket twice). For each: dispatch the
**implement** worker (SD-1 / SD-2) — that *produces* a real PR — then point a
**review** worker (SD-3 / SD-4) at that PR. The implement worker's output
feeds the review worker's input, and the engine is chosen independently at
each step. Two chains cover every cell without touching the self-hosted runner.

## Infrastructure blocker (automated review only)

- **Self-hosted runner registration — ida-solution#302.** The GitHub Actions
  auto-dispatch (PR opens → review fires) needs a registered, online
  self-hosted runner labeled `claude-review`. Registration was blocked because
  the operating account lacks `admin` on the org repo (404 on the
  registration-token endpoint). This blocks the *automated* trigger for
  **both** review engines equally — it is upstream of the engine switch — but
  does **not** block the manual `review-dispatch.sh <PR#>` runs in SD-3/SD-4.
  The board's cron sweep is deliberately left un-armed until a manual
  shakedown passes.

## Non-blocking follow-ups (from the final whole-branch review)

Separate from the shakedowns; captured here so they aren't lost.

- [ ] **FU-1 · registration-time lost-update (defensive hardening).**
  `_codex_launch`'s meta finalize and the foreground spawn/resume meta write
  are each atomic but not atomic across the two processes. Unreachable with
  real Codex turn durations (documented in the spec's Surprises), so no fix is
  required — but a future hardening could have the wrapper *merge* rather than
  *overwrite* the meta, closing the theoretical window.
- [ ] **FU-2 · `$DAEMON_HOME/runs` garbage collection.** Each Codex turn
  leaves `codex-run.*.{task,events.jsonl,reply.txt,err,pid,rc}` behind; the
  live `event_log` reference forbids blind deletion, so the directory grows
  unbounded. Add GC for runs whose meta is retired/purged.
