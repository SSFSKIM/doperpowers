# Codex Review

Target: branch diff against main

The patch contains cancellation and teardown races that can leave workers running, resurrect removed jobs, or signal an unrelated process group. It also has crash-consistency and fingerprint gaps that can lose state or replay stale results.

Full review comments:

- [P1] Stamp queued workers before applying the PID guard — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/codex-companion.mjs:1207-1209
  When `task --background` is cancelled before `task-worker` transitions from queued to running, `queuedRecord` contains the child PID but no `pidStart`, so this verification always fails. The detached worker is not terminated, yet cancellation records `cancelled`; because `handleTaskWorker` does not reject cancelled requests, it can subsequently transition back to running and a `--write` task may continue modifying the repository.

- [P1] Verify broker PIDs with the kill-path predicate — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/lib/broker-lifecycle.mjs:193-193
  During broker teardown, a transient failure to read the current process start time makes `pidInstanceAlive` return true by design. If the durable broker PID has been reused, this therefore authorizes `terminateProcessTree` against the unrelated successor and its process group; teardown must use the fail-closed `pidInstanceVerified` predicate used by the other signal paths.

- [P2] Sweep workers when the workflow parent is unverifiable — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/session-lifecycle-hook.mjs:79-80
  If a workflow parent has already exited, its PID was reused, or its start time is temporarily unreadable, this `continue` skips the independently instance-guarded `killWorkflowWorkers` call. Session cleanup then removes the job row, losing the run-directory pointer while any surviving app-server workers continue running.

- [P2] Quiesce workflow finalization before removing session jobs — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/session-lifecycle-hook.mjs:88-91
  For a live workflow, SessionEnd sends SIGTERM while still holding the state lock. The workflow's SIGTERM handler writes its per-job file and then blocks in `upsertJob`; after this callback removes the row and releases the lock, that pending upsert recreates a cancelled ledger row, usually after cleanup deleted its job and log files.

- [P2] Publish workers.json atomically — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/lib/workflow/engine.mjs:141-142
  If the workflow process is SIGKILLed between truncating and finishing this write, `workers.json` becomes empty or invalid JSON. Both dead-job repair and resume then treat it as having no workers, so surviving app-servers are not reaped and the replayed leaf can run alongside its orphaned predecessor.

- [P2] Settle cleanup when broker initialization creates no socket — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/lib/app-server.mjs:468-474
  With a malformed broker endpoint, `BrokerCodexAppServerClient.initialize()` throws before assigning `this.socket`. This catch then awaits `client.close()`, but broker `close()` has no no-socket settlement path and waits forever on an `exitPromise` that only socket handlers resolve, causing every affected command to hang instead of reporting the configuration error.

- [P2] Keep workflow job records in one generation — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/lib/workflow/job.mjs:73-74
  If a terminal workflow is resumed and the process dies between these writes, the per-job record has already been replaced with `running` while the ledger still reports the previous terminal generation. Dead-job repair only examines running or queued ledger rows, so it never reconciles this direction and the prior stored result remains lost or contradictory to `result --json`.

- [P2] Parse untracked names losslessly — /Users/new/Developer/GitHub/doperpowers/.claude/worktrees/pr43-dogfood/skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs:253-256
  With Git's default quoting, untracked names containing non-ASCII or control characters are emitted as quoted escape sequences, which are then passed literally to `hash-object` and recorded as `unreadable`. Editing such a file leaves the fingerprint unchanged, allowing a resume to serve stale worker results; use a NUL-delimited listing and parse bytes losslessly, including in submodules.
