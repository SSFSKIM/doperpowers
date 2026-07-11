# Managed-Agents steals — what we take, what we skip, and why

**Source.** Anthropic engineering blog, *"Scaling Managed Agents: Decoupling
the brain from the hands"* (https://www.anthropic.com/engineering/managed-agents),
read 2026-07-12 during the production-infrastructure discussion (cloud host
for the board pipeline: implement / review / land workers, feedback intake).
This doc records the transfer analysis and what was actually adopted, the
same way `2026-07-11-symphony-comparison.md` did for OpenAI Symphony.

**The article in one line.** Virtualize the agent into three interfaces —
**session** (append-only durable log), **harness** (the loop; stateless,
rebootable via `wake(sessionId)`), **sandbox** (execution environment;
provisioned on demand, disposable) — so each can fail or be replaced without
the others. Pets-vs-cattle applied to agents: the pet is not the machine,
it is *state fused to compute*.

## 0. Mapping onto our architecture

| Managed Agents | doperpowers equivalent | already decoupled? |
|---|---|---|
| session (durable event log) | claude JSONL transcripts (`~/.claude/projects`), codex rollouts (`~/.codex/sessions`) — plus, for the human-relevant slice, GitHub issue comments (FD-9 answer relay) | **yes** — resume = re-materialize the brain from the log |
| harness (stateless loop, `wake(sessionId)`) | `claude --bg --resume` / `codex exec resume` under the daemon registry | **yes** — every resume is already a fresh process over the log |
| sandbox (disposable hands) | git worktrees under `LOCAL_REPO/.claude/worktrees/` | **yes** — reconstructible from git at any time |
| the coupling they broke | our registry binds ticket → **(pid on one host, session file on one host)** | **no — this was our pet**, fixed by steal 1 |

The conclusion that shaped the infra discussion: what must be persistent is
the **state volume** (registry + session stores + clones), never the compute.
A worker host — VM, Fly machine, container — is a disposable body around
that volume. Recovery semantics were already right before this doc: the
board is the source of truth, sessions are a resume *optimization*, and the
worst case after total state loss is a fresh re-dispatch with the durable
issue-comment record. The steals below close the gaps that remained.

## 1. Steal 1 — host-stamped registry, host-aware liveness (IMPLEMENTED)

**Their form.** The container became cattle the moment the harness stopped
assuming it shared a box with the sandbox; failure detection became "the
tool call errored," not "nurse the box."

**Our defect.** Registry metas recorded a bare `pid`, and four consumers
tested liveness with `kill -0`:

- `codex-resume.sh` — one-turn-per-daemon guard
- `daemon-retire.sh` — kills the live turn before retiring
- `review-dispatch.sh` `_is_live` + `_wt_occupied` — dedupe and
  worktree-removal guards
- `land-dispatch.sh` `_is_live` — same

A pid is only meaningful on the machine that recorded it. Move the registry
to a new host on a state volume (host died, host rebuilt, migrated to
cloud) and a **reused pid number** reads as a live worker: resume refuses
("a turn is still running"), retire signals an unrelated process, dispatch
skips a dead reviewer as active, worktree removal is blocked by a ghost.
Every failure is silent and directional — the pipeline stalls open.

**The fix (shipped with this doc).** Every registration and resume stamps
`host` (`DAEMON_HOST`, default `hostname`) into the meta; `_pid_alive()`
in `_lib.sh` treats a host mismatch as dead regardless of `kill -0`
(empty `host` = legacy meta = local, preserving old behavior). All four
consumers now route through host-aware checks. Claude-engine metas get the
stamp too: their `short`/`current` ids are just as host-local (`claude
agents` is a per-host view). Pinned by tests in
`tests/orchestrating-daemons/test-codex-scripts.sh` (foreign-host pid:
resume proceeds + re-stamps, retire leaves the process alone) and
`tests/reviewing-prs/test-{review,land}-dispatch.sh` (foreign-host pid:
treated dead → retire+respawn; same-host control still skips as active).

This is the registry's cattle key without the migration project: metas are
now effectively keyed (host, pid, session), so a future multi-host or
container fleet only adds a dispatcher — no semantic change.

## 2. Steal 2 — the state-volume convention (CONVENTION, this doc is the spec)

**Their form.** Session outlives harness; harness outlives container;
nothing in the compute needs to survive.

**Ours.** When provisioning a dedicated worker host, ALL mutable pipeline
state lives under paths that sit on one detachable volume, and the compute
is fully reproducible from a setup script (cloud-init or equivalent):

| state | path | owner |
|---|---|---|
| daemon registry + codex run scratch | `DAEMON_HOME` (default `~/.claude/orchestrating-daemons`) | ours, env-overridable everywhere (verified: all scripts honor it) |
| claude sessions + jobs | `~/.claude/projects`, `~/.claude/jobs` | harness-owned — placed on the volume by making `$HOME` (or the whole user dir) volume-backed |
| codex sessions + auth | `~/.codex` | harness-owned, same treatment |
| canonical clones + worktrees | `LOCAL_REPO` per consumer repo | ours |

Host dies → new host + attach volume → every parked session resumes; the
host-aware liveness from steal 1 is exactly what makes the stale pids in
the migrated registry harmless. Nothing else in the pipeline needs backup
discipline: the board (GitHub) already carries ticket state and the
human-answer record.

Non-goal: we did NOT adopt per-worker ephemeral compute (their full cattle
shape). At single-tenant scale with a few concurrent workers, dispatch
latency is noise against multi-hour turns, and the refactor would reopen
freshly shaken-down rituals for a TTFT win we cannot feel.

## 3. Steal 3 — token-wired remote (RECIPE, apply at host provisioning)

**Their form.** Credentials are never reachable from where generated code
runs: the repo token is wired into the git remote during sandbox init
(push/pull work; the agent never handles the token), everything else sits
behind a vault + proxy.

**Ours, honestly scoped.** Full unreachability is impossible in this
design — a worker must hold a board-write token (`gh` issue transitions,
PR creation) *by contract*. The stealable part is **scope separation**:

- `LOCAL_REPO` on the worker host is cloned with a fine-grained token
  (contents: read/write on that repo ONLY) embedded in the remote URL.
  Worktrees share the parent repo's remote config, so worker `git push`
  just works — the push credential never enters worker env.
- Worker env `GH_TOKEN` gets a second fine-grained token scoped to
  issues + pull-requests (board writes, PR open/comment) with NO contents
  write. `_codex_launch` already prefers a pre-set `GH_TOKEN` over the
  keychain capture, so injection needs zero code.
- Net effect: a prompt-injected worker can vandalize the board (visible,
  reversible, audited) but cannot push code with authority the reviewer
  didn't grant, and neither token can spawn broader sessions.

Not applied on the current Mac host — the keychain token is the user's
full-power credential either way, so the split is theater there. The
TECH-DEBT accepted note ("GH_TOKEN in worker env") now points here as its
narrowing path.

## 4. Non-steals

- **Harness out of the container / on-demand sandbox provisioning.** Their
  TTFT win (p50 −60%) comes from thousands of multi-tenant sessions paying
  container boot before first token. Our workers run minutes-to-hours;
  boot cost is invisible. Skip until worker concurrency outgrows one host.
- **MCP vault + proxy for tool credentials.** Right shape at multi-tenant
  scale; for us it adds a resident service (the thing our no-orchestrator
  architecture deliberately avoids) to protect one token we can scope
  instead.
- **`getEvents()` context-interrogation layer.** Our equivalent pressure
  is already answered compositionally: FD-7 closing artifacts (PR body as
  the durable orientation record) + transcript-on-disk + fork-carries-context
  resume. A positional event-slicing API over transcripts is capability we
  have no consumer for.
- **Session-as-REPL-object context management.** Same reason — no consumer;
  the harnesses own their context engineering.

## 5. Relationship to the Symphony comparison

Symphony gave us the *work semantics* debates (FD-1..FD-9); Managed Agents
gives the *substrate* doctrine. They agree on the load-bearing point: the
durable log is the identity of the work, the loop is disposable. Symphony
puts that log in an orchestrator's memory + Linear; Managed Agents puts it
in a session store; we put it in GitHub (board) + session files (resume
cache). The steals above keep that stack true when the pipeline leaves the
Mac it was born on.
