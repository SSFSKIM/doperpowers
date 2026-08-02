# Codex Workflow Engine — Design

**Status:** Approved design, pre-implementation
**Branch:** `codex-workflow-engine` (off `main` @ 6765c24, post-PR #42)
**Owner consumers:** interactive Claude sessions, headless daemon workers (QAgent lineage), any harness that can run Bash

## Purpose

The E2 hardening campaign ran 15 *serial* codex review rounds against one
branch. The rounds conflated two different jobs: discovery breadth on a fixed
diff (parallelizable — single-pass review has limited recall, which is why
findings kept surfacing on unchanged code across rounds) and regression
checking after fixes (inherently serial). Discovery deserves a parallel
multi-agent pass.

More generally: Claude Code's Dynamic Workflow primitive (deterministic
orchestration fanning out model workers) has no counterpart on the Codex
runtime. This spec adds one to the vendored codex-companion runtime — a
general `workflow` verb that executes a JS orchestration script whose workers
are codex threads — with a multi-lens code-review workflow as the first
consumer and acceptance test.

What the codex-native engine buys over orchestrating N codex processes from
the Claude side:

1. **One detached process** — the whole fan-out has one pid, one stdout, one
   job record. This structurally dissolves the harness-background-kill and
   state-root-race failure modes observed all through the E2 campaign,
   instead of working around them per-invocation.
2. **Headless** — a daemon worker or cron job invokes a full
   find→verify→synthesize review as one command, with no Claude
   orchestration loop spending tokens on bookkeeping.
3. **Harness-independent** — doperpowers is a multi-harness plugin; a
   Bash-invocable engine works identically from every harness.

## Grounding (verified against the vendored runtime, 2026-08-03)

- `runAppServerTurn(cwd, {prompt, model, effort, outputSchema,
  resumeThreadId, sandbox, ...})` (`runtime/scripts/lib/codex.mjs:1095`)
  already is the worker primitive: one call = one thread turn, per-call
  model/effort, `{finalMessage, threadId, status}` out.
- Schema-forced output is production-proven: `outputSchema` rides
  `turn/start` (codex.mjs:1141) and the `adversarial-review` verb already
  passes `REVIEW_SCHEMA` (`codex-companion.mjs:415`), with
  `parseStructuredOutput` exposing `parseError` for retry.
- Native review is a distinct protocol method (`review/start`,
  codex.mjs:1026) — non-steerable, needs its own hook.
- Concurrency: each `withAppServer` call spawns its own `codex app-server`
  process; N workers = N independent processes.
- The shared job ledger (`state.json`) is an unlocked read-modify-write —
  parallel writers lose records (documented in references/reviews.md). The
  engine therefore keeps per-run state in its own directory.

## Design

### 1. CLI contract

New verb on the existing runtime entrypoint:

```
CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
CODEX_COMPANION_SESSION_ID="<session>" \
  node "<skill-base>/runtime/scripts/codex-companion.mjs" workflow \
  --script <path.mjs> [--args '<json>'] [--max-concurrency N] \
  [--cwd <dir>] [--resume <run-id>] [--json]
```

- **stdout**: the script's return value, JSON-serialized, plus run metadata
  (`{runId, result, agents: <count>, durationMs}`). Written once, after the
  run completes — same read contract as every other work verb.
- **stderr**: streamed progress — one line per worker lifecycle event
  (spawn, turn complete, retry, failure) prefixed `[workflow]`. Callers
  redirect it (`2> scratch.events.log`) exactly as with `review`/`task`.
- **Job record**: the run registers ONE summary job in the existing ledger
  at start and finalizes it at exit, so `status`/`result`/`cancel` work
  unchanged. Individual workers never touch the shared ledger.
- The verb always spawns per-worker app-servers on the direct path;
  `CODEX_COMPANION_APP_SERVER_ENDPOINT` is not consulted (harmless if set).
  Worker processes are children of the run process: killing the run (or
  `cancel <job-id>`) reaps the whole panel.
- `--max-concurrency` default **6** (fits the first consumer's panel; each
  worker is its own app-server process). No token budget; concurrency and
  the script's own structure are the cost controls.

### 2. Script contract

A workflow script is a plain ESM module. Hooks arrive as an explicit context
argument — no injected globals, no VM sandboxing; a script is trusted code
from the skill bundle or authored by the orchestrating agent:

```js
export const meta = { name: "code-review", description: "…" }; // optional

export default async function run({ agent, review, parallel, pipeline, log, args }) {
  // … orchestrate …
  return result; // becomes stdout JSON
}
```

Shipped workflows live in `skills/codex-companion/workflows/*.mjs` and are
addressed by path only — no name registry.

### 3. Hook semantics

- `agent(prompt, opts)` → one codex thread turn (`runAppServerTurn`).
  - `opts`: `{model, effort, schema, write, label, cwd}`. Effort passes
    through to `turn/start` (the task path's native effort field — no
    with-effort wrapper needed).
  - `schema` (a JSON-schema object): sets `outputSchema`; the engine parses
    the final message. **On parse/validation failure it retries once by
    resuming the same thread** with a repair prompt naming the error and
    demanding JSON-only re-emission. A second failure rejects.
  - Read-only sandbox unless `write: true`. Caveat documented: concurrent
    writers share one working tree; per-worker worktree isolation is a
    later milestone.
  - Returns the parsed object (with schema) or the final message string.
    Hard worker failure (spawn error, turn error, double schema failure)
    **rejects**; combinators below define how rejection is absorbed.
- `review({base, scope, model, effort, cwd})` → the native non-steerable
  reviewer via `review/start`, returning the structured findings payload
  the existing `review` verb produces. Same target-selection semantics as
  the `review` verb (`base` wins; `scope` auto|working-tree|branch).
- `parallel(thunks)` → runs thunks under the global semaphore; **barrier**;
  a rejected thunk resolves to `null` in the result array — the call itself
  never rejects.
- `pipeline(items, ...stages)` → per-item stage chains with **no barrier**
  between stages; a stage that throws nulls that item and skips its
  remaining stages. Each stage callback receives
  `(prevResult, originalItem, index)`.
- `log(msg)` → a `[workflow]` stderr line + journal entry.
- `args` → the `--args` JSON, verbatim.

Semantics deliberately mirror Claude Code's Workflow tool so the mental
model transfers between harnesses.

### 4. Run state, journal, resume

Per-run directory: `$CLAUDE_PLUGIN_DATA/workflows/<run-id>/`

- `journal.jsonl` — one entry per hook call: monotonic call index, hook
  kind, SHA-256 of the prompt+opts, codex thread id, outcome (result or
  error), timestamps.
- `agent-<index>.events.log` — per-worker streamed progress.
- `result.json` — the final stdout payload.

Resume (`--resume <run-id> --script <path>`): replay the longest journal
prefix whose (call order, prompt hash) match; cached calls return their
recorded results instantly; execution goes live at the first mismatch or
first unfinished call. Because the journal records thread ids, a resumed
run can also *continue* a thread that died mid-turn rather than restarting
it — codex-native resume the Claude-side Workflow cannot do. Determinism is
guidance, not enforcement: scripts that vary prompts across runs simply get
less cache benefit.

### 5. Failure semantics (engine-level)

- Worker turn failure → one automatic retry (fresh turn on the same thread
  when the thread survives, fresh thread otherwise), then rejection into
  the combinator rules above.
- Run-level crash → the summary job record is finalized as failed with the
  journal path; `--resume` picks up from the journal.
- The engine never interprets worker output beyond schema parsing — result
  semantics (including coverage accounting) belong to the script.

## First consumer: `workflows/code-review.mjs`

The multi-lens review panel, deliberately simpler than the argus-review
multi-agent ladder (that protocol's grouping mechanics, refuter votes, and
diff-proportional fleet sizing are dropped by owner decision — one strong
verifier replaces them).

**Args:** `{ base }` required (review target: merge-base diff against the
ref, same semantics as `review --base`); optional `{ cwd, finderModel,
finderEffort, verifierModel, verifierEffort }`.

**Fixed shape — 6 finders + 1 verifier:**

1. **Five lens finders** — parallel schema-forced `agent()` turns at
   **gpt-5.6-sol / xhigh**, read-only, one lens each. Lens scopes (texts
   adapted at implementation from argus-review's L1–L5, which this owner
   authored):
   - L1 changed-logic accuracy (defects inside the changed code itself)
   - L2 cross-file contract impact (breakage at callers/callees/readers)
   - L3 removed & moved behavior (guarantees deleted code used to provide)
   - L4 security surface (injection sinks, authz gaps, secrets, TOCTOU)
   - L5 performance & resources (complexity blowups, leaks, hot-path I/O)

   Finder output schema: `{ findings: [{ title, priority: "P0"|"P1"|"P2"|"P3",
   file, startLine, endLine, body }] }` — `body` carries evidence and the
   concrete failure scenario.
2. **One overall sweep** — the native `review({base})` holistic reviewer at
   **gpt-5.6-sol / xhigh** (served via a per-worker app-server configured at
   that effort), running in the same parallel wave. Its findings join the
   candidate pool. Rationale: codex's native reviewer *is* the
   general-purpose sweep; steering it is neither possible nor needed.
3. **One verifier** — a single `agent()` turn at **gpt-5.6-sol / high**
   receiving every candidate from all six finders (source-labeled), with
   the full diff context available to it in-repo. For each candidate it
   returns `{ id, verdict: "CONFIRMED"|"REFUTED", duplicateOf?, comment }`.
   One model seeing the whole pool replaces argus's mechanical grouping:
   it dedups (`duplicateOf`), confirms with a reconstructed trigger, or
   refutes with the reason. Verifier verdicts are binding — the script
   never re-judges.

**Assembly (deterministic, in script code):**

- Keep CONFIRMED, collapse duplicates onto the primary formulation, order
  P0 → P3.
- Verdict: `incorrect` iff ≥ 1 CONFIRMED finding survives; else `correct`.
- Output object carries `## Findings`-shaped entries plus the verdict,
  explanation (decisive findings or their absence), and a coverage section.

**Coverage honesty (script-level, inherited from the campaign's lesson):**

- A lens finder or the sweep dead after the engine's retry → the run
  proceeds, but the output names the lost lens ("L4 did not complete —
  coverage is partial") and a clean verdict is downgraded to
  `interrupted` — lost coverage never launders into a confident pass.
- The verifier dead after retry → the run reports `interrupted` with the
  raw candidate pool attached; unverified candidates are never published
  as findings and never silently dropped.

## Acceptance

Behavior-phrased; commands assume the skill base dir and env contract from
SKILL.md.

1. **Engine, mocked**: with the app-server mocked at the transport level, a
   test script exercising `agent` (with and without schema), `review`,
   `parallel` (including one rejecting thunk → `null`), and `pipeline`
   (including one throwing stage → nulled item) — invoked via
   `… workflow --script tests/…/fixture.mjs --args '{"n":3}'` — exits 0,
   prints the script's return value as JSON on stdout, streams `[workflow]`
   lines on stderr only, and writes `journal.jsonl` + `result.json` under
   the run directory.
2. **Schema repair**: a mocked worker whose first final message violates the
   schema and whose second (same thread, repair prompt observed) is valid →
   `agent()` resolves with the parsed object; journal shows one retry.
3. **Resume**: kill a mocked run after its second `agent()` completes;
   `… workflow --resume <run-id> --script <same>` re-executes only calls
   ≥ 3 (journal prefix served from cache, verified by mock invocation
   counts).
4. **Concurrency cap**: a script issuing 10 parallel agents under
   `--max-concurrency 2` never has more than 2 live mock app-servers
   (mock asserts peak concurrency).
5. **Panel, live (the A/B)**: `… workflow --script
   skills/codex-companion/workflows/code-review.mjs --args
   '{"base":"e0b1835"}'` run against this repo (the exact E2 diff the
   15-round campaign exhausted) completes with 6 finder workers + 1
   verifier in the journal and produces the Findings/Verdict contract.
   Panel output is compared against the campaign's adjudicated findings
   ledger (`.doperpowers/sdd/2026-08-01-e2-interim-slice/progress.md`) —
   recall against known-real findings and any novel confirmed finding are
   recorded in this spec's Surprises section. This is the eval evidence
   the repo requires for behavior-shaping content.
6. **Coverage honesty, mocked**: kill one mocked lens finder twice → output
   names the lens and a would-be-clean verdict reports `interrupted`, not
   `correct`.

## Testing strategy

- Engine unit/integration tests live at `tests/codex-companion/` with a
  `run-workflow-tests.sh` runner (node test scripts + a mock `codex`
  app-server binary on PATH). Per the mock-fidelity lesson: the mock speaks
  the real JSON-RPC transport shape (initialization, `turn/start`
  streaming notifications, interleaved events, a schema-violating final
  message case) — never the parsed shape the engine wants.
- Every new assert must fail against the parent commit with a naming
  signature (test-discrimination discipline).
- The live A/B (acceptance 5) is run once during implementation and its
  transcript kept under `docs/doperpowers/specs/` evidence or the spec's
  Surprises section.

## Out of scope (M0)

- Token budget accounting, nested `workflow()`, per-agent git-worktree
  isolation, a workflow name registry, phase-grouped progress UI.
- Any change to existing verbs (`review`, `adversarial-review`, `task`,
  jobs) beyond registering the new verb; their contracts are untouched.
- Fix-wave orchestration: the panel reviews; fixing remains the calling
  session's loop. (The serial fix→re-review cycle is intentionally NOT
  replaced — parallelism replaces discovery breadth only.)

## Decision Log

- **Codex-native engine over Claude-side orchestration** (Workflow-tool
  hybrid with thin Claude subagents shelling to codex, or hand-launched
  parallel Bash). Rejected: N detached processes + pollers reintroduce the
  harness-kill and state-root races the campaign fought; not headless; not
  harness-independent. The one-process property is the point.
- **General engine first, code-review as first consumer** — over
  code-review-first-extract-later (orchestration born entangled with
  review semantics) and over full Workflow parity (budget/nesting/
  worktrees have no consumer yet). Owner choice, 2026-08-03.
- **Panel simplified away from the argus ladder** (owner decision,
  2026-08-03): fixed 5-lens + native-sweep finder wave at sol/xhigh, ONE
  verifier at sol/high judging the whole pool — replacing argus's
  mechanical line-range grouping, packed verifier waves, and 2-refuter
  adversarial votes. Rationale: one strong model over the full candidate
  pool dedups and judges better than mechanical partitioning, at a
  fraction of the machinery; quota is explicitly not a concern.
- **Native `review` as the overall sweep** — over a sixth prompted
  "holistic lens" agent. The native reviewer is codex's own tuned
  general-purpose pass; a prompted imitation adds steering surface for no
  recall gain.
- **Explicit context parameter over injected globals/VM** — scripts are
  trusted bundle/agent-authored code; explicit `{agent, …}` is testable
  with a fake context and needs no sandbox machinery.
- **Schema repair by same-thread resume** — over respawn-with-stricter
  prompt. The thread already holds the analysis; a repair turn re-emits
  cheaply. Codex-native advantage; falls back to fresh thread when the
  thread died.
- **Per-run state directory** — over the shared `state.json` ledger, whose
  unlocked read-modify-write is a documented race under parallelism. One
  summary job record keeps `status`/`result`/`cancel` working.
- **Default `--max-concurrency` 6** — sized to the first consumer's panel;
  each worker is a full app-server process. Tunable; revisit with data
  from the A/B run.

## Surprises & Discoveries

(accumulates during implementation)

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-08-03: Initial version, from the brainstorming round following the
  E2 15-round serial campaign. Panel shape fixed by owner (5 lenses +
  native sweep at sol/xhigh; single verifier at sol/high).
