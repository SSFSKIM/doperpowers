# Codex worker species — symmetric implementer/reviewer (2026-07-10)

## Purpose

The board pipeline's workers are Claude-only: implement workers and review
workers are `claude --bg` daemons (doperpowers:orchestrating-daemons), and
the review engine reaches codex only through the codex-companion plugin —
with its machine-wide lock, 30-minute backoff, and Claude-subagent fallback.
With the gpt-5.6 model line, Codex is both cheaper and stronger than the
Claude models these fleets default to, and the human wants **Codex as the
main implementer and reviewer**.

This spec adds a symmetric **Codex worker species** beside the Claude one.
Symmetry, not replacement: nothing Claude-side is removed or degraded — the
Claude implement worker, Claude review worker, and its Claude-subagent
review fallback all stay fully operational. "Codex is the main worker" is
expressed only through the default of a new engine knob, flippable back per
repo (env) or per ticket/PR (label) any day. The board schema, park states,
the Ticket Gate, merge tiers, and worker-authority rules change **zero**: a
Codex worker is the same worker under the same protocol, differently
propelled.

## Ground truth (researched 2026-07-10)

- **Drive mechanism: plain `codex exec`.** `codex exec --json` emits a
  `thread.started` event carrying the session id (field `thread_id`, not
  `id` — confirmed by smoke test); `codex exec resume <session-id> "<msg>"`
  continues it from any cwd **that is itself a trusted/git directory, or
  with `--skip-git-repo-check`** (confirmed: resuming into plain `/tmp`
  fails closed with "Not inside a trusted directory..." until that flag is
  added); `-o <file>` captures the final message. This mirrors the
  `claude --bg` daemon contract almost 1:1.
  The App Server (what OpenAI Symphony's Director drives over JSON-RPC
  stdio) requires a resident driver process holding the pipes for the whole
  turn — Symphony has an orchestrator; this pipeline deliberately has none.
  It is also marked Experimental. The TS SDK wraps `codex exec` and adds
  nothing reachable from bash.
- **Native review is headless-capable, but PROMPT and a target flag are
  mutually exclusive.** `codex exec review` is the automation variant
  (`--json`, `-o`, `--output-schema`, `-m`); target via `--base <branch>`,
  `--commit <sha>`, or `--uncommitted`. No `-C` flag — the caller must `cd`
  into the checkout. **Confirmed live (Task 2 spike, codex-cli 0.144.1):**
  `--base`, `--commit`, and `--uncommitted` each hard-conflict with a
  custom PROMPT at the clap argument-parser level — `rc=2`, no JSON
  emitted, `error: the argument '--base <BRANCH>' cannot be used with
  '[PROMPT]'` (same shape for the other two flags). PROMPT-alone (no
  target flag) DOES compose with the built-in correctness preset — a
  custom spec-compliance instruction produced both a correctness finding
  and the compliance finding in the same call — but its implicit target is
  only the last commit (`HEAD` vs `HEAD^`) or the working tree if dirty,
  never a multi-commit range against a base branch. So for a real PR diff
  against `origin/<base>`, the `review` subcommand cannot carry custom
  criteria at all; the cookbook pattern (plain `codex exec` with a prompt
  that self-diffs against the base branch, plus inlined correctness +
  compliance instructions, optionally `--output-schema`) is not an
  edge-case fallback — it is the only working path for that case. See
  Surprises & Discoveries, Task 2 spike.
- **The review lock is a companion artifact, not a Codex one.** Direct
  `codex exec review` has no machine-wide lock.
- **Sandbox facts** (partly via Symphony's hardening): `codex exec`
  defaults to `read-only`; `workspace-write` blocks network unless
  `-c sandbox_workspace_write.network_access=true`; a clone-shipped
  `.codex/hooks.json` would execute at session start unless
  `-c features.hooks=false`; a linked worktree's real `.git` lives under
  the main repo (outside the workspace root — needs `--add-dir`).
- **Approvals:** Codex's analog of Claude's `--permission-mode auto` is the
  automated approvals reviewer (`-c approval_policy=on-request
  -c approvals_reviewer=<auto value>`) — a fail-closed reviewer adjudicates
  escalation requests so safe ops continue and unsafe ones are declined.
  The human's interactive config already runs `guardian_subagent`; Symphony
  sets `auto_review`. Both values confirmed headless-safe (Task 1 spike);
  recommended default `auto_review` — see Surprises & Discoveries.
- **Models:** `gpt-5.6-sol` (flagship), `gpt-5.6-terra` (workhorse);
  reasoning efforts `minimal|low|medium|high|xhigh`. **Caveat (smoke
  test, codex-cli 0.142.5, ChatGPT-account auth):** neither `gpt-5.6-sol`
  nor `gpt-5.6-terra` — the latter is this environment's own
  `~/.codex/config.toml` default — is actually invocable via `codex exec`
  today; both 400 with "requires a newer version of Codex" (0.144.1 is
  available per `codex doctor`; 0.142.5 is installed). `gpt-5.5` is the
  newest model confirmed working end-to-end. Design target unchanged
  (Decision Log #8). **Resolved same day:** codex-cli upgraded to 0.144.1
  (npm); `gpt-5.6-sol` confirmed working end-to-end (`rc=0`, reply `pong`)
  with event shapes identical to the Task 1 pinning — the caveat no longer
  gates the live shakedown.

## Design

### Substrate — `codex-spawn.sh` / `codex-resume.sh` (orchestrating-daemons)

Sibling scripts to `daemon-spawn.sh` / `daemon-resume.sh`, same positional
contract plus a trailing `[effort]` arg, writing the **same registry**
(`~/.claude/orchestrating-daemons/<id>.json`) with `engine: "codex"`,
`pid`, and the Codex session id as the registry key (UUID-shaped, so
`board-bind.sh` prefix matching works unchanged).

Spawn: create the worktree if named (`git worktree add` at
`<repo>/.claude/worktrees/<name>`, branch `worktree-<name>`, mirroring
Claude's native `--worktree`), then launch detached:

```
nohup codex exec --json -C <workdir> --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=true -c features.hooks=false \
  -c approval_policy=on-request -c approvals_reviewer=<auto value> \
  --add-dir <main-repo-root> -m <model> -c model_reasoning_effort=<effort> \
  -o <reply-file> - < <task-file> > <event-log> 2>&1 &
```

Session id parsed from the first `thread.started` event in the log; a
detached watcher polls the PID and flips registry status
`working → idle|error` on exit, recording the reply from `-o`. `--no-wait`
= register as soon as the session id materializes (same contract as
today). `codex-resume.sh <id> "<msg>"` wraps `codex exec resume`, records
the new PID, increments turns — **not** "the same flags" verbatim: `codex
exec resume` has no `--sandbox` option at all (confirmed via
`codex exec resume --help`); sandbox mode is set via `-c sandbox_mode=<mode>`
instead. It also does not inherit the spawning session's model — a
mismatch fires a non-fatal warning item and the turn falls back to
`~/.codex/config.toml`'s default model — so `codex-resume.sh` must
re-pass `-m <model> -c model_reasoning_effort=<effort>` on every resume
call, the same as the initial spawn. Resuming into a cwd that isn't
itself trusted/git needs `--skip-git-repo-check` too.

**Status semantics, documented in orchestrating-daemons:** `blocked` never
occurs for this engine — exec has no interactive approval prompts; the
auto-reviewer approves or declines, and a declined escalation is a failed
command the worker works around or parks over.

Read-side scripts stay single-entry with small engine branches:
`daemon-list.sh` (engine column; Codex liveness = `kill -0 <pid>`),
`daemon-reply.sh` (read the `-o` file), `daemon-retire.sh` /
`daemon-mark.sh` (registry-only, near-unchanged). `board-bind.sh` and
`board-reconcile.sh`: **unchanged**.

### Engine selection

Precedence: per-ticket/PR label `engine:claude|engine:codex` → env
`WORKER_ENGINE` → default `codex`. Model/effort env: the implement worker
uses `codex-spawn.sh`'s own `CODEX_MODEL`/`CODEX_EFFORT` (default
`gpt-5.6-sol`/`high`) directly — no dedicated `*_IMPL_*` knob, because the
implement defaults ARE the spawner's defaults, so nothing needs overriding to
reach them. The review worker needs a dedicated pair — `CODEX_REVIEW_MODEL`/
`CODEX_REVIEW_EFFORT` (default `gpt-5.6-sol`/`xhigh`), which `review-dispatch.sh`
translates into `codex-spawn.sh`'s positional model/effort args — precisely
because review wants `xhigh`, which differs from the spawner's `high` default.
`REVIEW_MODEL` keeps meaning the Claude review worker's model. The
issue-tracker ritual step 3 and `review-dispatch.sh`'s spawn become a
two-way switch: render the engine's protocol, call the engine's spawner.

### Protocols — shared core + engine blocks

Protocol files remain the single source of policy (gate, park
discriminant, authority, bins, tiers — identical across engines).
Engine-specific text lives in block files under each skill's
`references/engine-blocks/`, substituted through the existing `{{WORD}}`
render:

- **implement protocol `{{EXECUTION_BLOCK}}`** — Claude block: today's
  text (doperpowers:test-driven-development / doperpowers:execplan). Codex
  block: the same discipline inlined — DIRECT = red/green TDD, frequent
  commits, PR via `gh`; PLAN mode = author an ExecPlan-style plan file
  (milestones, observable acceptance) committed in the worktree, then
  execute it to the letter.
- **review protocol `{{ENGINE_BLOCK}}` + `{{FALLBACK_BLOCK}}`** — the
  `codex exec review --base <branch> ... <stdin PROMPT>` composition
  originally sketched here is impossible: Task 2's spike confirmed
  `--base` (and `--commit`, `--uncommitted`) hard-conflict with a custom
  PROMPT at the CLI level (`rc=2`). The engine block is now the SAME for
  both species but uses the cookbook pattern instead of the `review`
  subcommand's target flags: `cd` to the worktree root, plain `codex exec
  --ephemeral -m $CODEX_REVIEW_MODEL -c
  model_reasoning_effort=$CODEX_REVIEW_EFFORT -o <findings>` with a stdin
  prompt that (1) instructs the model to self-diff against
  `origin/<base>` (`git diff origin/<base>...HEAD`), (2) inlines the same
  correctness discipline `codex exec review`'s preset applies, and (3)
  adds **spec compliance** — the linked ticket brief with "are the
  acceptance criteria fulfilled; is anything out of scope; is anything
  claimed but missing". This full shape — multi-commit self-diff plus
  combined criteria in one plain `codex exec` call — is live-verified
  (see Surprises & Discoveries, Task 2 spike (b), follow-up). (The
  `review` subcommand's target flags remain usable standalone — e.g. a
  no-custom-instructions correctness-only pass — just never combined
  with custom criteria in the same call.) Fallback
  differs by species: the Claude worker falls back to a fresh Claude
  reviewer subagent (as today); a Codex worker has no second engine —
  after brief retries it parks `needs-human` with the failure as the
  note.

The codex-companion path — machine-wide lock, 30-minute backoff,
`/codex:cancel` warnings — **retires from the worker protocol and
reviewing-prs SKILL.md**. The companion stays installed for interactive
use; workers stop touching it.

### Dispatch & liveness

`review-dispatch.sh`: `_is_live` gains an engine branch (registry `pid`
alive vs `claude agents`); `_wt_occupied` checks both sources; the dedupe
table's semantics are unchanged. The implement side stays the mechanical
ritual (render → spawn → bind), now engine-aware. Trail comments and
`[gate]` comments record the engine, so the audit trail names which
species did what.

### Security posture

Always-on for every Codex worker: `--sandbox workspace-write`,
`-c features.hooks=false`, network access on, `--add-dir
<main-repo-root>`, the approvals auto-reviewer. **Never**
`--yolo`/`--dangerously-bypass-approvals-and-sandbox` — the mirror of the
Claude-side `--dangerously-skip-permissions` ban; lands in
orchestrating-daemons' Permissions section. Workers inherit the dispatch
env, as Claude workers do today (personal-machine threat model; Symphony's
multi-tenant deny-by-default env is a deliberate non-goal).

### Feasibility smoke tests (front-loaded in the plan)

1. `codex exec` exit codes + `thread.started` id capture from `--json`.
   **Done (Task 1 spike).**
2. Commit/push from a linked worktree under `workspace-write` +
   `--add-dir <main-repo-root>`. **Done (Task 2 spike): confirmed working
   end-to-end** — push landed on the bare origin, verified by fetch.
3. `codex exec review` PROMPT + `--base` composition and output shape.
   **Done (Task 2 spike): they do NOT compose** — mutually exclusive at
   the CLI level (`rc=2`). The cookbook pattern (plain `codex exec` +
   self-diffing review prompt, optional `--output-schema`) is the only
   path — **and was itself verified live in a post-review follow-up**:
   a two-commit range reviewed against its base produced correctness
   findings from both commits plus the injected spec-compliance finding
   in one call (`rc=0`). See Surprises & Discoveries, Task 2 spike (b).
4. Codex-in-Codex: inner `codex exec review --ephemeral` under the outer
   worker's sandbox. **Done (Task 2 spike): bare `--ephemeral` fails
   nested** (`rc=1`, app-server client init blocked by the outer sandbox);
   **the workspace-local `CODEX_HOME` + symlinked `auth.json` fallback
   works** (`rc=0`, confirmed Symphony's pattern).
5. `codex exec resume <id>` from a different cwd.
6. Approvals auto-reviewer headless: exact config value (`auto_review` vs
   `guardian_subagent`) and that `codex exec` honors it.

### Testing & docs

New shell tests for `codex-spawn.sh`/`codex-resume.sh` against a stub
`codex` binary emitting canned JSONL (same style as the daemon-script
stubs); `review-dispatch` engine-switch tests; all existing suites stay
green; `scripts/lint-shell.sh` clean. Docs: orchestrating-daemons
(engine-aware substrate, no-blocked semantics, sandbox rules),
reviewing-prs (engine section rewrite; adoption checklist gains "codex CLI
installed + authed"), implementing-tickets (pieces table), issue-tracker
(ritual step 3).

## Out of scope

- **Model routing by issue/review size** — a later initiative; for now the
  fixed defaults above (human's explicit deferral).
- **Auto-fallback between engines** — a failed Codex spawn surfaces as a
  dispatch error; the sweep retries; the human decides.
- **App Server / SDK drive** — rejected (see Decision Log).
- **Retiring anything Claude-side** — symmetry, not replacement.
- **Deny-by-default worker env** — Symphony's multi-tenant hardening;
  wrong threat model here.

## Acceptance

- `codex-spawn.sh` against a stub `codex` registers a registry entry with
  `engine=codex` and a session-id key; `board-bind.sh` binds it;
  `daemon-list.sh` shows it with correct liveness; `daemon-reply.sh`
  prints the stub's final message.
- The implement ritual and `review-dispatch.sh` with `WORKER_ENGINE=codex`
  render the Codex-block protocol and call `codex-spawn.sh`; a ticket/PR
  labeled `engine:claude` gets a Claude daemon despite the env; unset env
  defaults to codex.
- `review-dispatch.sh` dedupe treats a live Codex reviewer (pid alive) as
  ACTIVE-skip and a dead one as retire-and-respawn, mirroring the Claude
  table.
- Both review species' rendered protocols carry the identical engine block
  including the spec-compliance instructions with the ticket brief; only
  the fallback block differs.
- Live shakedown: a Codex implement worker on a real ticket gates
  (`[gate]` comment naming the engine), builds in its worktree, commits,
  pushes, opens a PR, transitions the board; a Codex review worker reviews
  a real PR end-to-end and routes the escalation tier correctly.
- All existing test suites pass; `scripts/lint-shell.sh` reports no new
  findings.

## Decision Log

1. **Drive Codex via plain `codex exec`, not App Server or SDK.** The
   pipeline is fire-and-forget with no orchestrator; app-server needs a
   resident JSON-RPC driver (and is Experimental); the TS SDK wraps exec.
   `codex exec --json` + `resume` + `-o` mirrors the `claude --bg`
   contract. Rejected: App Server (Symphony's choice — Symphony has a
   Director to hold the pipes); TS SDK (nothing for bash).
2. **Sibling toolkit + shared registry** (Approach 1). Rejected:
   engine-branching inside daemon-spawn.sh et al. (every script's
   internals are saturated with Claude assumptions; branch trees would
   risk the battle-tested path); separate skill with own registry (forks
   the fleet view; board-bind/reconcile would need two homes).
3. **Hard default flip with overrides, no auto-fallback** (human's
   choice). Default `codex`, env `WORKER_ENGINE`, label `engine:*`.
   Rejected: staged env-gated rollout (delays the stated goal); automatic
   Claude respawn on Codex failure (more machinery, surprise engine swaps
   mid-sprint).
4. **Shared protocol core + per-engine block files.** The policy text
   (gate, parks, authority, bins, tiers) stays single-sourced. Rejected:
   two full protocol copies per loop — a divergence factory for
   load-bearing policy text.
5. **The review engine runs inside the worker, not the dispatch layer.**
   Re-review rounds (max 3) are worker-driven; a dispatch-run engine caps
   the loop at one round structurally.
6. **Companion retirement from worker paths.** The machine-wide lock,
   backoff, and cancel warnings existed only because workers went through
   the companion; direct `codex exec review` has no lock. The companion
   remains for interactive use.
7. **Approvals: auto-reviewer, sandbox stays on** (human's requirement,
   sharpened). `-c approval_policy=on-request -c approvals_reviewer=<auto>`
   is Codex's `--permission-mode auto`: fail-closed adjudication keeps
   work moving without granting `--yolo`. Rejected: bare
   `approval_policy=never` (sandbox denials silently kill legitimate
   steps); `--yolo` (mirror-banned).
8. **Models fixed at `gpt-5.6-sol`/high (implement) and
   `gpt-5.6-sol`/xhigh (review)** (human's choice). Size-based model
   routing explicitly deferred.
9. **Symmetry principle** (human's requirement): Claude workers stay fully
   available until Codex proves itself; the flip is a knob default, not a
   removal.

## Surprises & Discoveries

- The review lock the pipeline engineers around is a codex-*companion*
  artifact; the native engine has no lock. Retiring the companion from
  worker paths deletes the whole backoff apparatus.
- Symphony already contains the reverse of this design — a Claude worker
  speaking the codex-app-server protocol (`worker-runtime/`) — confirming
  the "one protocol, two runtimes" seam is viable in both directions.
- Real Codex CLI scans `<workspace>/.agents/skills/` for skills (Symphony
  vendors doperpowers there per-workspace) — not used in v1 (protocol
  blocks inline the discipline instead), but it's the path if Codex
  workers ever need full skills.
- `codex exec review` has no `-C` flag (plain `codex exec` does) — review
  workers must `cd` before invoking the engine.
- `~/.codex/config.toml` carries a stale pin note ("0.140.0, do not
  upgrade") while 0.142.5 is installed and working.
- **The `_codex_launch` finalization wrapper turns any external kill of a
  live codex turn into a status race** (found building Task 5's
  `daemon-retire.sh`). Killing the codex pid wakes the wrapper's blocked
  `wait`, which then writes its own terminal status *after* the caller's —
  clobbering a `retired` (or any other) write back to `error`/`idle` milli-
  seconds later, deterministically (reproduced 3/3, timestamp-instrumented).
  Every caller that kills a live codex pid must wait on the wrapper's `.rc`
  completion barrier before writing status — the same barrier
  `codex-resume.sh`'s dead-pid guard already waits on. `daemon-retire.sh`
  now does; a future non-`daemon-retire` kill path would have to as well.
- **Latent registration-time lost-update, defended by turn duration** (raised
  by the final whole-branch review). `_meta_set` is atomic per-write
  (`os.replace`) but not atomic *across* the detached `_codex_launch` wrapper
  and the foreground spawn/resume script. In principle, if a turn finished in
  the millisecond window between the foreground script detecting
  `thread.started` and writing the full-field meta, the wrapper's finalize —
  having read the meta while it was still empty — could clobber the
  `engine`/`pid`/`turns` fields back to just `{status, updated}` (the daemon
  would then render as `claude` in `daemon-list`). This is **unreachable with
  real codex turns**: `thread.started` fires at turn *start* and the wrapper
  finalizes at turn *end*, seconds apart, so the foreground write always lands
  first (the hermetic fast-turn test confirms the observed interleaving is
  safe). **Fixed 2026-07-10 (post-review follow-up):** rather than leave it a
  known property, `_meta_set` now serializes its read-modify-write with an
  advisory `fcntl.flock` on a shared `$DAEMON_HOME/.metalock`, making each write
  atomic w.r.t. every other. A concurrency regression test proved the race was
  in fact worse than "unreachable" — under real parallel writers the unlocked
  RMW both lost fields AND crashed on the `<path>.tmp` `os.replace`; the lock
  closes both. See Revision Note 5.

### Task 1 spike: `codex exec --json` contract (2026-07-10, codex-cli 0.142.5, ChatGPT-account auth)

- **Event shapes, confirmed live.** `thread.started` carries the id as
  `thread_id` (not `id`): `{"type":"thread.started","thread_id":"019f..."}`.
  A successful turn's agent reply arrives as
  `{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"pong"}}`.
  The terminal event on success is
  `{"type":"turn.completed","usage":{"input_tokens":N,"cached_input_tokens":N,"output_tokens":N,"reasoning_output_tokens":N}}`.
  On failure the terminal event is
  `{"type":"turn.failed","error":{"message":"<JSON-string of the API error object>"}}`,
  immediately preceded by a top-level `{"type":"error","message":"..."}`
  event with the same nested message. Non-fatal advisory items (stale
  model-metadata warnings, the "skill descriptions were shortened"
  notice, malformed plugin-hooks-config parse errors, resume
  model-mismatch warnings) also arrive as `item.completed` with
  `item.type:"error"` but do **not** fail the run — only the
  top-level `error` + `turn.failed` pair means the turn actually failed.
- **Exit codes, confirmed live.** `rc=0` on `turn.completed`; `rc=1` on
  `turn.failed` (tested via an invalid model on both fresh `exec` and
  `exec resume`); `rc=2` on CLI-level argument/usage errors (observed live:
  `--sandbox` passed to `exec resume` → `error: unexpected argument
  '--sandbox' found`) — in the rc=2 case **no JSON events are emitted at
  all**, so wrappers must not assume an event log exists on failure.
- **Model availability blocked the happy path as specified.** The
  brief's `-m gpt-5.6-sol` failed: `"The 'gpt-5.6-sol' model requires a
  newer version of Codex."` Retried with this environment's own
  configured default, `gpt-5.6-terra` — same error. Retried with
  `gpt-5.3-codex` (named in `config.toml`'s `model_migrations` map) —
  different error: `"...is not supported when using Codex with a ChatGPT
  account."` `~/.codex/models_cache.json` (the CLI's own fetched model
  list) confirms only `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini` carry
  `supported_in_api: true` for this account/CLI version; no `gpt-5.6-*`
  slug exists in the cache at all. `codex doctor` reports 0.144.1 is
  available vs. the installed 0.142.5. Completed the remaining spike
  steps with `gpt-5.5` (confirmed working) as a substitute — this is an
  environment/version gate, not a design defect; see the Ground truth
  models bullet above for the caveat and the Revision Notes entry below.
- **`codex exec resume` has no `--sandbox` flag.** `codex exec resume
  --help` lists no `-s/--sandbox` option — passing it errors with
  `"unexpected argument '--sandbox' found"`. Sandbox mode on resume must
  go through `-c sandbox_mode=<mode>` instead.
- **Resuming into an untrusted/non-git cwd fails closed.** `cd /tmp &&
  codex exec resume <id> ...` (exactly the brief's cross-cwd test)
  produced `"Not inside a trusted directory and --skip-git-repo-check
  was not specified."` — `/tmp` itself isn't a git repo or a
  previously-trusted project directory. Adding `--skip-git-repo-check`
  fixed it; the resume then re-emitted the identical `thread_id`,
  confirming cross-cwd resume genuinely works once past the trust gate.
- **Resume does not inherit the spawning session's model.** Without
  re-passing `-m`, the resumed turn silently falls back to
  `~/.codex/config.toml`'s default model (`gpt-5.6-terra` here) and a
  non-fatal warning item fires: `"This session was recorded with model
  X but is resuming with Y."` Since the config default is currently one
  of the unusable 5.6 models, an unqualified resume call fails the
  turn. `-m`/`-c model_reasoning_effort` must be re-passed on every
  resume, not assumed to persist.
- **stdin `-` prompt works on resume** — no fallback to a positional
  argv prompt is needed; `codex exec resume <id> --json ... - <<<
  "msg"` behaved identically to fresh `exec`.
- **Approvals reviewer: both values run headless without error.**
  `-c approval_policy=on-request -c approvals_reviewer=auto_review` and
  `...=guardian_subagent` both returned `rc=0` running `git status` end
  to end, no CLI-level rejection either way. Neither run surfaced any
  "approval" text in the JSONL stream (`grep -c approval` = 0 for both)
  — a benign `git status` never escalates past the `workspace-write`
  sandbox, so this test confirms the config value is *accepted*, not
  that the auto-reviewer *adjudicates* anything; an actual escalation
  scenario wasn't exercised. No first-party CLI documentation
  distinguishing the two values was found (checked `codex exec --help`,
  `codex exec resume --help`, bundled resources, installed plugin
  caches — no hits). Recommendation: default `CODEX_APPROVALS_REVIEWER`
  to `auto_review`, on the existing ground-truth evidence that Symphony
  — an automated, headless orchestrator — sets `auto_review`, while the
  human's own interactive session config uses `guardian_subagent`; the
  interactive/headless split maps to that reviewer/orchestrator
  distinction.
- **Hooks parse errors are cosmetic without `-c features.hooks=false`.**
  Two installed plugins' `hooks.json` files fail to parse (`unknown
  field "description", expected "hooks"`) and surface as non-fatal
  `item.completed` errors on every run that doesn't disable hooks —
  consistent with, and reinforcing, the design's existing
  `-c features.hooks=false` requirement.

### Task 2 spike: sandboxed worktree git, review composition, Codex-in-Codex (2026-07-10, codex-cli 0.144.1, ChatGPT-account auth)

All three flags the brief expects (`--base`, `--ephemeral`, positional
PROMPT/`-` stdin) exist on `codex exec review` and `codex exec` unchanged
from the brief's assumptions — no flag-name adaptation was needed before
running the steps.

- **(a) Sandboxed commit + push from a linked worktree: confirmed
  working.** From `$S/wt` (a `git worktree add` sibling of `$S/main`,
  whose bare origin is `$S/origin.git`), `codex exec --sandbox
  workspace-write -c features.hooks=false --add-dir "$S/main" -m
  gpt-5.6-sol -c model_reasoning_effort=low` created `hello.txt`,
  committed it, and ran `git push origin HEAD:feat` — both the commit
  (`git add && git commit`) and the push were plain `command_execution`
  items with `exit_code: 0`, and `turn.completed` fired (`rc=0`). Verified
  independently: `git -C "$S/main" fetch origin feat && git log --oneline
  FETCH_HEAD` showed the new commit on the bare origin. One transient
  wrinkle worth recording: the agent's *first* attempt used its internal
  file-write tool to create `hello.txt`, which it reported as blocked by
  the sandbox on `index.lock` creation (the worktree's real git metadata
  lives under `$S/main/.git/worktrees/wt`, outside the workspace root
  until `--add-dir` exposes it) — but it self-corrected by re-running the
  file creation and all git operations as plain shell commands
  (`command_execution`), and every one of those succeeded on its first
  real try (`exit_code: 0`, no retries needed). Net result: `--add-dir
  <main-clone-root>` is sufficient for a linked worktree to commit and
  push; this becomes `_codex_main_root`'s contract in Task 3, and Task 3
  should keep git operations as explicit shell commands in worker
  instructions rather than relying on the agent's internal file-edit tool
  for anything touching `.git`.
- **(b) `codex exec review --base X` does NOT compose a stdin PROMPT with
  the built-in correctness review — they are mutually exclusive at the
  CLI argument-parser level, not merely "one replaces the other."**
  Running `codex exec review --base master --ephemeral -m gpt-5.6-sol -c
  model_reasoning_effort=low -o /tmp/spike-review.txt -` (stdin carrying a
  spec-compliance instruction) failed immediately: `rc=2`, no JSON
  emitted, stderr `error: the argument '--base <BRANCH>' cannot be used
  with '[PROMPT]'` — consistent with the Task 1 rc=2 contract ("CLI
  argument error, no JSON events emitted at all"). The same conflict was
  confirmed for the other two targeting flags: `--commit <sha>` and
  `--uncommitted` each independently produced the identical
  `cannot be used with '[PROMPT]'` rejection when combined with a stdin
  PROMPT. So this is not `--base`-specific — **no targeting flag can be
  combined with a custom PROMPT on `codex exec review`, full stop.**
  Composition *does* happen, but only in the mode the brief didn't test:
  PROMPT passed **alone**, with no targeting flag at all. Live test: with
  a dirty/committed repo whose last commit added `bug.py` containing `x =
  1/0`, running `codex exec review --ephemeral -m gpt-5.6-sol -c
  model_reasoning_effort=low -o out.txt -` with the same spec-compliance
  instruction ("the change was supposed to add greeting.py") produced
  **both** findings in one output: `[P1] Add the required greeting.py
  file` and `[P1] Avoid unconditional division by zero`. So the preset
  and the custom instructions genuinely compose — just never in the same
  invocation as a `--base`/`--commit`/`--uncommitted` target. The catch:
  PROMPT-alone's implicit target is narrow. Instrumented via its own
  `git` calls (visible in the human-readable transcript), it ran `git
  diff HEAD^ HEAD` — i.e. it reviews only the single last commit (or the
  working tree if dirty), never a multi-commit range against a named base
  branch. For a real PR — potentially many commits since it branched from
  `origin/<base>` — this mode cannot be pointed at the actual PR diff.
  **Verdict: for a real PR review that must carry both the correctness
  preset and custom spec-compliance criteria, `codex exec review` (the
  subcommand) has no working invocation at all.** The Ground truth's
  documented "fallback" — plain `codex exec` with a review prompt that
  self-diffs against the base branch (`git diff origin/<base>...HEAD`),
  inlining both correctness discipline and spec-compliance instructions,
  optionally with `--output-schema` for structured findings — is not an
  edge-case fallback; it is the only path that reaches the actual
  requirement. Task 6's engine block must be written around the cookbook
  pattern, not the `codex exec review --base ... <stdin>` sketch
  originally in the Design section (now corrected in place).
  **Cookbook pattern itself verified live (post-review follow-up, same
  day):** the spike had only proven the negative (targeting flags reject
  a PROMPT) plus a single-commit composition; the actual Task 6 shape —
  plain `codex exec --ephemeral` (no `review` subcommand) with a stdin
  prompt instructing a self-diff against the base branch over a
  **two-commit** range plus inlined correctness + spec-compliance
  criteria — was then executed for real: `rc=0`, and the findings list
  contained defects from BOTH commits (`bug.py` ZeroDivisionError from
  commit 1, `util.py` NameError from commit 2) AND the compliance finding
  (required `greeting.py` missing). Multi-commit self-diff review with
  combined criteria is observed behavior, not inference.
- **(c) Codex-in-Codex: bare `--ephemeral` fails nested; workspace-local
  `CODEX_HOME` with a symlinked `auth.json` fixes it.** Running an inner
  `codex exec review --commit HEAD --ephemeral -c
  model_reasoning_effort=low -o /tmp/inner.txt` (no PROMPT, to isolate
  this question from finding (b)'s CLI-arg conflict — the brief's literal
  inner command used `--base` + stdin PROMPT together, which finding (b)
  already shows is `rc=2` regardless of nesting) from inside an outer
  `codex exec --sandbox workspace-write -c
  sandbox_workspace_write.network_access=true --add-dir "$S/main" -m
  gpt-5.6-sol -c model_reasoning_effort=low` session produced `rc=1` on
  the inner command specifically: `WARNING: proceeding, even though we
  could not create PATH aliases: Operation not permitted (os error 1)`
  followed by `Error: failed to initialize in-process app-server client:
  Operation not permitted (os error 1)` — root cause not fully
  diagnosed; the observed symptom (PATH-alias creation then app-server
  client init both dying on `Operation not permitted`) points at the
  outer sandbox denying writes/setup the inner CLI needs under the real
  `~/.codex`, even for a read-only review. The outer turn itself still
  completed (`rc=0`) — only the nested `codex` invocation failed. Retried
  with the brief's suggested fallback: `mkdir -p .codex-home && ln -sf
  ~/.codex/auth.json .codex-home/auth.json && CODEX_HOME=$PWD/.codex-home
  codex exec review --commit HEAD --ephemeral -c
  model_reasoning_effort=low -o /tmp/inner2.txt` — this completed with
  `exit_code: 0` for the inner command and the outer turn. Caveat worth
  carrying into Task 6: because the workspace-local `.codex-home` has no
  `config.toml`, the inner review ran under stock CLI defaults (banner
  showed `sandbox: read-only`, `approval: never`) rather than any
  repo-configured defaults or the outer session's `-c` overrides — fine
  for a review (read-only is exactly what a reviewer needs), but the
  inner invocation must have its own `-m`/`-c model_reasoning_effort`
  passed explicitly; nothing from the outer `-c` flags carries through
  the `CODEX_HOME` boundary. **The working variant — workspace-local
  `CODEX_HOME` with a symlinked `auth.json`, no bare `--ephemeral` sharing
  the outer's real `~/.codex`, and explicit `-m`/`-c` on the inner call —
  goes verbatim into the Task 6 engine block.**

## Outcomes & Retrospective

**Code/test milestone: complete and merge-approved** (2026-07-10). All ten
plan tasks landed via subagent-driven development with a per-task review gate
and a final whole-branch review on the strongest model (verdict: Ready to
merge, 0 Critical / 0 Important). The live shakedown remains the trigger for
the *ultimate* closure (below).

**Achieved against Purpose.** The board pipeline now drives two worker species
under one registry: the existing Claude daemons and a new detached `codex exec`
species (`engine: codex` in the meta), selected per dispatch by
`label → WORKER_ENGINE → codex`. Codex is the default engine, but nothing
Claude-side was removed — symmetry, not replacement. Both the implement
pipeline (issue-tracker ritual + per-engine EXECUTION blocks) and the review
pipeline (`review-dispatch.sh` engine switch + cookbook `codex exec` reviewer
with spec-compliance criteria) understand both engines. The codex-companion
lock+backoff apparatus is fully retired.

**Gaps / deferred.** (1) The **live shakedown** — a real Codex implement worker
driving a real ticket to a PR, and a real Codex review worker reviewing a real
PR — has not run; it happens on the next real board dispatch and is what closes
this spec for good. (2) The two non-blocking follow-ups from the final review
are now **closed** (Revision Note 5): `_meta_set` serialization (flock) and
`$DAEMON_HOME/runs` garbage collection both shipped with regression tests.

**Lessons.** The two front-loaded spikes paid for themselves repeatedly: Spike
B's finding that `codex exec review` + a target flag + a custom PROMPT is a
CLI-level impossibility (rc=2) invalidated the engine-block sketch the plan had
carried into *three* later tasks (6, 7, 9) — each caught at pre-dispatch and
corrected in place, before an implementer could faithfully build the broken
form. Encoding hard-won CLI contract facts (event shapes, exit codes, the
resume flag differences, the `_codex_launch` kill-race) into the spec's
Surprises section, not just commit messages, is what made those catches
mechanical rather than lucky.

## Revision Notes

1. **2026-07-10 (Task 1 spike).** Corrected two Design-section claims
   that the live `codex exec`/`codex exec resume` contract contradicted:
   (a) the Ground truth drive-mechanism bullet's "continues it from any
   cwd" now carries the `--skip-git-repo-check` caveat for cwds that
   aren't themselves trusted/git directories; (b) the
   `codex-resume.sh` sketch's "wraps `codex exec resume` with the same
   flags" is corrected — resume has no `--sandbox` option (use `-c
   sandbox_mode=<mode>`) and does not inherit the spawning session's
   model (re-pass `-m`/`-c model_reasoning_effort` every call). The
   Ground truth models bullet gained a caveat: on this spike's
   environment (codex-cli 0.142.5, ChatGPT-account auth), neither
   `gpt-5.6-sol` nor `gpt-5.6-terra` is invocable via `codex exec` today
   (both 400 with "requires a newer version of Codex"); `gpt-5.5` is the
   newest confirmed-working model. The model *decision* (Decision Log
   #8) is unchanged — this is an environment/CLI-version gate, not a
   reason to retarget — but Task 3's stub-codex tests and any live
   shakedown should account for it (upgrade codex-cli first, or treat
   `gpt-5.5` as an interim substitute). Full evidence in Surprises &
   Discoveries above.
- **2026-07-10 (controller, post-Task 1).** The CLI-version gate is closed:
  codex-cli upgraded 0.142.5 → 0.144.1 (`npm install -g @openai/codex@latest`),
  and `gpt-5.6-sol` verified end-to-end on the new CLI (rc=0, `-o` reply
  `pong`, event stream `thread.started{thread_id}` →
  `item.completed{item:{type:"agent_message",text}}` →
  `turn.completed{usage}` — byte-identical shapes to the Task 1 pinning, so
  the recorded contract carries over unchanged). Remaining spike and
  shakedown steps run the design's real models; the `gpt-5.5` interim
  substitute is no longer needed.
2. **2026-07-10 (Task 2 spike).** Corrected two Design-section claims the
   live `codex exec review` contract contradicted: (a) the Ground truth
   review bullet's "whether PROMPT composes with `--base` ... is
   undocumented" is resolved — it does not; `--base`/`--commit`/
   `--uncommitted` each hard-conflict with a custom PROMPT (`rc=2`, no
   JSON) — and the "fallback: cookbook pattern" is promoted from
   contingency to the only confirmed path for a real base-branch-range
   review with custom criteria; (b) the review protocol's `{{ENGINE_BLOCK}}`
   sketch (`codex exec review --base origin/<base> ... <stdin PROMPT>`) is
   corrected to the cookbook pattern (plain `codex exec` with a
   self-diffing, criteria-inlining prompt), since the sketched invocation
   is a CLI-level impossibility, not a stylistic preference. Also recorded:
   commit+push from a linked worktree under `--add-dir <main-clone-root>`
   is confirmed working (feeds `_codex_main_root` in Task 3), and
   Codex-in-Codex needs the workspace-local `CODEX_HOME` + symlinked
   `auth.json` variant — bare nested `--ephemeral` fails closed with an
   app-server init error under the outer sandbox. Full evidence in
   Surprises & Discoveries, "Task 2 spike" above.
3. **2026-07-10 (post-Task 2 review follow-up).** Task 2's reviewer flagged
   that the cookbook self-diff invocation (Task 6's engine-block shape) was
   recorded with "confirmed" confidence while only the negative
   (target-flag/PROMPT conflict) and a single-commit composition had been
   executed. Resolved by running the missing experiment rather than
   softening the language: plain `codex exec --ephemeral` with a
   self-diff-against-base prompt over a two-commit range returned findings
   from both commits plus the injected compliance criterion (`rc=0`).
   Recorded in Surprises (b) and Feasibility item 3. Also softened finding
   (c)'s root-cause gloss to observed-symptom language per the same review.
4. **2026-07-10 (Tasks 3–10 execution).** Two substantive Design/Surprises
   shifts surfaced during implementation. (a) **Engine-selection env vars
   reconciled** (Task 8): the implement worker has no dedicated `*_IMPL_*`
   model/effort knob — `codex-spawn.sh` reads generic `CODEX_MODEL`/
   `CODEX_EFFORT`, whose defaults (`gpt-5.6-sol`/`high`) already ARE the
   implement defaults, so nothing needs overriding to reach them. The review
   worker keeps its dedicated `CODEX_REVIEW_MODEL`/`CODEX_REVIEW_EFFORT`
   precisely because it wants `xhigh` (≠ the spawner's `high`), which
   `review-dispatch.sh` translates into positional args. The Engine-selection
   section was corrected from the earlier `CODEX_IMPL_*` naming. (b) **The
   `_codex_launch` external-kill race** (Task 5), added to Surprises:
   killing a live codex turn wakes the wrapper's own finalization, which then
   clobbers any status a caller writes — so every path that kills a live codex
   pid (currently `daemon-retire.sh`, and `codex-resume.sh`'s dead-pid guard)
   must wait the wrapper's `.rc` completion barrier before writing status.
   Three plan-side engine-block/test sketches were also corrected in place
   pre-dispatch (the `codex exec review --base ... <PROMPT>` composition
   Spike B disproved, in Tasks 6/7/9) — the spec's Design already carried the
   cookbook correction from Revision Note 2, so only the plan needed aligning.
5. **2026-07-10 (post-review follow-ups closed).** The two non-blocking items
   the final whole-branch review flagged were both fixed rather than deferred.
   (a) **`_meta_set` serialization** — its cross-process read-modify-write is
   now wrapped in an advisory `fcntl.flock` on `$DAEMON_HOME/.metalock`. A new
   concurrency test (61 parallel writers on one meta) showed the pre-fix code
   was worse than the review's "unreachable" framing: it lost fields *and*
   crashed on the `<path>.tmp` `os.replace` under real contention. The lock is
   global (all daemons serialize on one file) — coarser than a per-uuid lock
   but negligible given the tiny critical section, and it benefits claude
   daemons too. (b) **runs GC** — `_codex_gc_runs` age-gates and sweeps
   `codex-run.*` sets that no live meta's `event_log` references, called at
   spawn/resume, plus purge-time removal of a daemon's own run files. Both
   reviewed and green across the codex, daemon, and review-dispatch suites.
