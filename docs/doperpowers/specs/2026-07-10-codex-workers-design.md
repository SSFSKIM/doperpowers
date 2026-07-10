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
- **Native review is headless-capable.** `codex exec review` is the
  automation variant (`--json`, `-o`, `--output-schema`, `-m`); target via
  `--base <branch>`; custom instructions via positional PROMPT (`-` =
  stdin). No `-C` flag — the caller must `cd` into the checkout. Whether
  PROMPT composes with `--base` or replaces the preset review scope is
  undocumented (smoke test; fallback: OpenAI's cookbook pattern — plain
  `codex exec` + review prompt + `--output-schema` findings JSON).
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
  sets `auto_review`. Exact value + headless behavior: smoke test.
- **Models:** `gpt-5.6-sol` (flagship), `gpt-5.6-terra` (workhorse);
  reasoning efforts `minimal|low|medium|high|xhigh`. **Caveat (smoke
  test, codex-cli 0.142.5, ChatGPT-account auth):** neither `gpt-5.6-sol`
  nor `gpt-5.6-terra` — the latter is this environment's own
  `~/.codex/config.toml` default — is actually invocable via `codex exec`
  today; both 400 with "requires a newer version of Codex" (0.144.1 is
  available per `codex doctor`; 0.142.5 is installed). `gpt-5.5` is the
  newest model confirmed working end-to-end. Design target unchanged
  (Decision Log #8); the live-shakedown acceptance step needs a Codex CLI
  upgrade first, or `gpt-5.5` as an interim substitute.

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
`WORKER_ENGINE` → default `codex`. Model/effort env:
`CODEX_IMPL_MODEL`/`CODEX_IMPL_EFFORT` (default `gpt-5.6-sol`/`high`),
`CODEX_REVIEW_MODEL`/`CODEX_REVIEW_EFFORT` (default `gpt-5.6-sol`/`xhigh`).
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
  engine block is now the SAME for both species: `cd` to the worktree
  root, `codex exec review --base origin/<base> --ephemeral
  -m $CODEX_REVIEW_MODEL -c model_reasoning_effort=$CODEX_REVIEW_EFFORT
  -o <findings>`
  with custom instructions on stdin: the correctness preset plus **spec
  compliance** — the linked ticket brief with "are the acceptance criteria
  fulfilled; is anything out of scope; is anything claimed but missing".
  Fallback differs by species: the Claude worker falls back to a fresh
  Claude reviewer subagent (as today); a Codex worker has no second engine
  — after brief retries it parks `needs-human` with the failure as the
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
2. Commit/push from a linked worktree under `workspace-write` +
   `--add-dir <main-repo-root>`.
3. `codex exec review` PROMPT + `--base` composition and output shape
   (fallback: cookbook pattern with `--output-schema`).
4. Codex-in-Codex: inner `codex exec review --ephemeral` under the outer
   worker's sandbox (fallback: workspace-local `CODEX_HOME` with symlinked
   `auth.json` — Symphony-proven).
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
  `exec resume`). No other rc value was observed.
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

## Outcomes & Retrospective

Pending — written at finish.

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
