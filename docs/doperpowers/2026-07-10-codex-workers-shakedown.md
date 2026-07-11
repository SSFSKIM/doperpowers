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

## Non-blocking follow-ups (from the final whole-branch review) — DONE

Both addressed in commit `1ff71ea` (reviewed, all suites green).

- [x] **FU-1 · registration-time lost-update.** Resolved by serializing
  `_meta_set`'s cross-process read-modify-write with an advisory `fcntl.flock`
  on a shared `$DAEMON_HOME/.metalock`. Turned out to be more than theoretical:
  under real concurrency the unserialized RMW not only lost fields but crashed
  on the `<path>.tmp` `os.replace`. The lock makes each `_meta_set` atomic
  w.r.t. every other, for claude and codex daemons alike.
- [x] **FU-2 · `$DAEMON_HOME/runs` garbage collection.** Added `_codex_gc_runs`
  — an age-gated sweep of run sets no live meta's `event_log` references —
  called at spawn/resume, plus removal of a codex daemon's run files on
  `purge`. The age gate spares a run another spawn is mid-registration on.
  (Known limitation: a daemon resumed once and never spawned/resumed again
  leaves its orphan un-swept until the next spawn — accepted, since growth is
  driven by active resuming, which the sweep bounds.)

## Live run — 2026-07-11 (macbook, mini unavailable)

Shakedown executed on the macbook (the usual mini host was not accessible).
Prereqs re-verified on this host: `codex-cli 0.144.1`, `claude 2.1.206`, `gh
2.87.3` authed as `SSFSKIM`, `~/.codex/auth.json` present. Target: the real
ida-solution board (doperpowers itself has Issues disabled). Only one
code-shaped gate-ready ticket existed (**#460**, the midnight-wrap camera
bug), so coverage was: **SD-1** codex-implement on #460, then **SD-3/SD-4**
codex+claude review of the resulting PR (run sequentially — the review dedupe
skips a PR with a live reviewer). **SD-2** (claude-implement) had no second
gate-ready code ticket and was left for a human ticket-promotion decision.

### FU-3 · `gh` unauthenticated inside the codex sandbox — FIXED

The first codex implement worker gated #460 (pass, PLAN mode) but every `gh`
call — starting with its first board write — returned **HTTP 403
unauthenticated**; it could not even park, and exited clean with no code (a
correct disciplined failure, but dead in the water).

- **Root cause.** `gh` here authenticates from the **macOS keychain**. Codex
  runs workers in a Seatbelt `workspace-write` sandbox that cannot read the
  login keychain, so `gh` ran signed-out. The claude engine never hit this:
  claude workers run **un-sandboxed on the host**, where the keychain is
  reachable. The asymmetry is the sandbox, not the token. The prereq check
  above missed it because it verified codex's *own* `auth.json`, not that
  `gh` (a different tool, different credential store) works *inside* the
  sandbox.
- **Fix** (`_codex_lib.sh`, `_codex_launch`, shared by spawn **and** resume):
  capture the token with `gh auth token` in the dispatcher's context (which
  has keychain access) and export it as `GH_TOKEN`; `gh` prefers the env
  token over the keychain, and the sandbox reads process env. Auth parity
  with the claude workers; the standard CI pattern. Guarded on `GH_TOKEN` /
  `GITHUB_TOKEN` being unset so an explicit token still wins.
- **Verified live.** Minimal sandbox probe printed `Logged in … (GH_TOKEN)`;
  re-dispatched worker's process carried `GH_TOKEN` in its env; #460
  transitioned `ready-for-agent → in-progress` with a `[gate] pass —
  codex/PLAN` comment — i.e. the first board write now succeeds.
- **Security note for review.** This places a repo-scoped token in the
  worker's sandbox env (visible to its own subprocesses). It is parity with
  what claude workers already wield via the keychain, not new exposure — but
  flagged here so the human can veto if they read the surface differently.

### FU-4 · skills parity — codex workers now get the doperpowers doctrine

The v1 design deliberately inlined the TDD/PLAN discipline into
`execution-codex.md` because codex workers had no doperpowers skills, while
the claude block references `doperpowers:test-driven-development` /
`doperpowers:execplan` directly (spec: "not used in v1 … but it's the path if
Codex workers ever need full skills"). That path is now live:

- **Verified empirically** — with a correction. The first probe (scratch repo
  + symlink → codex listed `doperpowers:*`) turned out to be **contaminated**:
  this machine's codex has the released doperpowers **7.10.0 plugin installed**
  (`~/.codex/plugins/cache/doperpowers-dev/…`), discovered when SD-1's
  pre-vendoring worker ran skill scripts from that cache. A clean canary test
  settled it: a fake skill existing ONLY in a scratch `.agents/skills` symlink
  target was seen by codex (`yes-XYZZY-CANARY`) — so directory scanning is
  real and plugin-independent on codex-cli 0.144.1.
- **Mechanism:** `_codex_vendor_skills` (in `_codex_lib.sh`, called by
  `codex-spawn.sh` after worktree resolution) symlinks the doperpowers
  `skills/` root to `<runcwd>/.agents/skills` and adds `.agents/skills` to
  the repo's shared `info/exclude` (local, never committed) so the symlink is
  invisible to `git status` in every worktree — a worker cannot accidentally
  commit it. No-op for non-git cwds and for repos that already have
  `.agents/skills`. Covers both pipelines: implement (worktree arg) and
  review (`review-dispatch.sh` passes its detached worktree as cwd).
- **Engine block:** `execution-codex.md` keeps the inlined discipline as the
  primary instruction (proven in SD-1) and gains a pointer to
  `.agents/skills/` for the full doctrine. Rewriting the block to reference
  skills the way the claude block does is a follow-up that wants eval
  evidence, per the skill-change bar.
- Six new assertions in `tests/orchestrating-daemons/test-codex-scripts.sh`;
  all orchestrating-daemons + reviewing-prs suites green; shellcheck clean.
- **Open policy question — one skills source, not two.** On machines with the
  codex marketplace plugin installed, post-FU-4 workers see BOTH the released
  plugin skills (7.10.0) and the vendored working tree — version skew plus a
  known "2% skills context budget" squeeze (descriptions get truncated).
  Either uninstall the codex doperpowers plugin on worker machines (pin to
  working tree via vendoring) or skip vendoring when the plugin is present.
  Human call; not blocking the shakedown.
- **Live observation (SD-1):** the codex worker discovered the doperpowers
  skills (via the plugin cache — it predated vendoring) and elected
  subagent-driven development on its own: per-task codex sub-threads, 47
  collab waits, `.doperpowers/sdd/task-N-report.md` artifacts. Codex-in-Codex
  works unprompted; wall-clock cost ~1h for a 3-root-cause ticket. Whether
  workers should fan out sub-agents (latency/token multiplier) vs execute
  in-thread is a protocol-tuning question for after the shakedown.
  **DECIDED (human, 2026-07-11): in-thread solo execution.** writing-plans
  and subagent-driven-development are interactive-session doctrine, never a
  daemon worker's. Both engine blocks now (a) rename the codex mode
  PLAN → **EXECPLAN**, routing explicitly to the vendored
  `doperpowers:execplan` doctrine (one self-contained plan, executed by the
  worker itself, milestone by milestone), and (b) carry a work-ALONE clause
  naming the forbidden skills — no sub-agents, no collab threads. Pinned by
  the protocol-content test.

### FU-5 · `codex exec resume` rejects `--add-dir` — linked-worktree resume was broken

SD-1's worker died mid-turn on an upstream capacity error (`"Selected model
is at capacity"` — transient, not ours), which made it the first LIVE test of
`codex-resume.sh` on a linked-worktree daemon. The resume failed to start
(rc=2): **`codex exec resume` accepts no `--add-dir`**, the same CLI
asymmetry family as the `--sandbox` quirk Task 1's spike documented — the
spike caught `--sandbox` but missed `--add-dir` because no worktree resume
had ever run. The rc=2 guard held (turns not incremented, loud error).

- **Fix:** the config-space equivalent, `-c
  sandbox_workspace_write.writable_roots=["<main-root>"]` — the same table as
  the `network_access` override every spawn already passes.
- **Verified live:** the re-run resume turn started and ran (status
  `working`, turns=2) where the old flags died at rc=2.
- Regression test: worktree-daemon resume must carry `writable_roots` and
  never `--add-dir` (test-codex-scripts.sh).
- Bonus coverage: this exercised the crash-mid-build → resume path end-to-end
  on a real ticket (plan + 5 commits survived; fresh turn re-oriented from
  the plan file), which no SD cell explicitly covered.

### Remaining engine asymmetries — audited, deliberate (not gaps)

| surface | claude worker | codex worker | verdict |
|---|---|---|---|
| repo instructions | `CLAUDE.md` (+`CLAUDE.local.md`) | `AGENTS.md` → chains to `CLAUDE.md` in ida-solution | OK; `CLAUDE.local.md` stays claude-only by design |
| approvals | `--permission-mode auto`; can surface `blocked` | sandbox + `auto_review` approvals reviewer; **never** `blocked` | deliberate (codex-spawn.sh header) |
| hooks | normal claude hooks | `features.hooks=false` | deliberate (two installed plugins' hooks.json fail codex's parser — spec Surprises) |
| worktree | native `--worktree` | manual `git worktree add` + `--add-dir` main root | equivalent outcome, different mechanism |
| reply/resume | native `claude --resume` | `codex-resume.sh` + reply file / event log | engine-routed in daemon-reply/daemon-list; verified live |
| review fallback | fresh claude reviewer subagent | no second engine → parks `needs-human` | deliberate (spec) |
| effort knob | (model arg only) | `CODEX_MODEL` + `CODEX_EFFORT` | minor cosmetic asymmetry; claude CLI has no spawn-time effort flag |

_(FU-3 and FU-4 should also be reflected as Surprises in
`specs/2026-07-10-codex-workers-design.md` at retrospective.)_
