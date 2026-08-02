# Codex Workflow Engine — Design

**Status:** v2 — revised after independent adversarial review (codex sol/xhigh, 2026-08-03); panel finder substrate awaiting owner confirmation (see Open Questions)
**Branch:** `codex-workflow-engine` (off `main` @ 6765c24, post-PR #42)
**Owner consumers:** interactive Claude sessions, headless daemon workers (QAgent lineage), any harness that can run Bash

## Purpose

The E2 hardening campaign ran 15 *serial* codex review rounds against one
branch. The rounds conflated two different jobs: discovery breadth on a fixed
diff (parallelizable — single-pass review has limited recall, which is why
findings kept surfacing on unchanged code across rounds) and regression
checking after fixes (inherently serial). Discovery deserves a parallel
multi-agent pass — and this repo has already proven the premise: the
multilens engine work (`docs/doperpowers/execplans/2026-07-28-multilens-review-engine.md`,
shipped v7.25.0) showed seven differently-configured single reviews of one
large PR each found a different 8–10 of 13 confirmed defects whose union was
all 13.

More generally: Claude Code's Dynamic Workflow primitive (deterministic
orchestration fanning out model workers) has no counterpart on the Codex
runtime. This spec adds one to the vendored codex-companion runtime — a
general `workflow` verb that executes a JS orchestration script whose
workers are codex threads — with a multi-lens code-review panel workflow as
the first consumer and acceptance case.

What the codex-native engine buys over orchestrating N codex processes from
the Claude side:

1. **One detached process** — the whole fan-out has one pid, one stdout, one
   job record. This structurally dissolves the harness-background-kill and
   state-root-race failure modes observed all through the E2 campaign.
2. **Headless** — a daemon worker or cron job invokes a full
   find→verify→synthesize review as one command, with no Claude
   orchestration loop spending tokens on bookkeeping.
3. **Harness-independent** — doperpowers is a multi-harness plugin; a
   Bash-invocable engine works identically from every harness.

## Grounding (verified against the vendored runtime and repo history, 2026-08-03)

- `runAppServerTurn(cwd, {prompt, model, effort, outputSchema,
  resumeThreadId, sandbox, ...})` (`runtime/scripts/lib/codex.mjs:1095`) is
  the worker primitive: one call = one thread turn, per-call model/effort,
  `{finalMessage, threadId, status}` out. `outputSchema` rides `turn/start`
  and is production-proven by `adversarial-review`.
- `parseStructuredOutput` (codex.mjs:1188) does **JSON.parse only — no
  schema validation**. The engine must validate structurally itself.
- `runAppServerTurn` cannot continue a turn that died mid-turn: resuming a
  persisted thread always starts a NEW `turn/start` (codex.mjs:1104-1141);
  new threads are ephemeral unless `persistThread` is set. Retry semantics
  must be "new turn", never "continue turn".
- Native review is a distinct protocol method (`review/start`,
  codex.mjs:1026) returning **rendered `reviewText`**, not structured
  findings. It has no per-request effort field — effort (and any other
  config) must be set on the serving app-server process
  (references/reviews.md:31). It IS steerable via the
  `-c developer_instructions=...` config override — verified live
  2026-07-12 and shipped in `reviewing-prs`' lens transport
  (`CODEX_REVIEW_LENS_FILE`, multilens execplan Milestone 2). The
  "non-steerable" note in references/reviews.md refers only to positional
  focus text.
- `withAppServer` consults/creates a broker when configured
  (app-server.mjs:335) — per-worker isolation requires explicit direct
  spawn. `scripts/with-effort.mjs` demonstrates the mechanism: spawn
  `codex -c key=value … app-server` per connection.
- The shared job ledger (`state.json`) is an unlocked
  load-mutate-`writeFileSync` (state.mjs:118-129) — ANY two concurrent
  top-level runs can lose each other's records, not just intra-run
  workers. Cancellation signals the process group of the recorded pid
  (process.mjs:100) and assumes the record-holder is a group leader; dead
  sessions remain `running` forever (references/jobs.md).
- Review-quality evidence base: `tests/review-bench/` (the X1 benchmark —
  5 seeded truth-set cases with false-positive baits, 3 real-PR cases, a
  predeclared non-regression bar) and the multilens results: native codex
  review at sol/xhigh beat every Claude-side cell (10/13 vs 8/13 → argus
  engine discarded by owner 2026-07-28); a lensed run is a **scalpel, not
  a sweep** (the authz lens returned exactly 1 finding — the F3 defect
  both plain runs missed — vs the sweep's 10; lenses redirect the whole
  attention budget). Shipped doctrine: one lens-free sweep + diff-derived
  scalpel lenses.

## Design — the engine

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
  (`{runId, result, agents, durationMs, coverage}`). Written once, after
  the run completes.
- **stderr**: streamed progress — one `[workflow]` line per worker
  lifecycle event (spawn, turn complete, retry, failure). Callers redirect
  it (`2> scratch.events.log`).
- **M0 is read-only**: no `write` option exists. Every worker turn runs
  `sandbox: "read-only"`; native-review workers are read-only by nature.
  Write-capable steps are deferred until replay/idempotency semantics
  exist (see Out of scope) — this is what makes journal replay sound.
- The verb never consults `CODEX_COMPANION_APP_SERVER_ENDPOINT`: every
  worker gets its own directly-spawned `codex app-server` child with
  per-worker `-c` overrides (the with-effort.mjs mechanism, in-process).
- `--max-concurrency` default **6**; the semaphore guards **leaf worker
  spawns** (`agent`/`review` acquisitions), not combinators — a script
  calling bare `Promise.all` over 10 `agent()`s still never exceeds the
  cap.

### 2. Process ownership, jobs, cancel

- Worker app-servers are direct children of the run process (same process
  group, `detached: false`). The engine tracks live worker pids in the run
  directory and installs SIGTERM/SIGINT handlers: on signal, kill all live
  workers, finalize the job record (`canceled`), exit.
- The run registers ONE summary job record. Workflow-path writes to the
  shared ledger go through an **advisory lockfile + write-temp-then-rename**
  (atomic replace), fixing the cross-run lost-record race for this verb
  (existing verbs' behavior is untouched; their documented race stands).
- Liveness repair: when `status`/`result` reads a workflow job whose
  recorded pid is dead but status is `running`, it finalizes the record as
  `failed` (journal path attached) instead of reporting a phantom run.
  `cancel` keeps its group-signal path and additionally kills the tracked
  worker pids from the run directory, so it works even when the run
  process is not a group leader.

### 3. Script contract

A workflow script is a plain ESM module. Hooks arrive as an explicit
context argument — no injected globals, no VM sandboxing; a script is
trusted code from the skill bundle or authored by the orchestrating agent:

```js
export const meta = { name: "code-review", description: "…" }; // optional

export default async function run({ agent, review, parallel, pipeline, log, args }) {
  // … orchestrate …
  return result; // becomes stdout JSON
}
```

Shipped workflows live in `skills/codex-companion/workflows/*.mjs`,
addressed by path only — no name registry.

### 4. Hook semantics

- `agent(prompt, opts)` → one read-only codex thread turn
  (`runAppServerTurn` against the worker's private app-server).
  - `opts`: `{model, effort, schema, label, cwd}`. Effort rides
    `turn/start` natively.
  - `schema`: sets `outputSchema` AND the engine validates the parsed
    result against the schema structurally (a minimal validator for the
    subset used: `type`, `properties`, `required`, `items`, `enum`) —
    `parseStructuredOutput` alone accepts any syntactically-valid JSON.
    On parse OR validation failure: one repair retry as a **new turn on
    the same thread** naming the error and demanding JSON-only
    re-emission (fresh thread if the thread died). Second failure
    rejects.
  - Returns the validated object (with schema) or the final message
    string. Hard failure rejects; combinators define absorption.
- `review(opts)` → one native review via a private app-server spawned
  with per-worker config overrides:
  `{base, scope, model, effort, lens, cwd}` — `effort` becomes
  `-c model_reasoning_effort=…`, `lens` becomes
  `-c developer_instructions=…` on the spawn argv (no shell — argv-array
  spawn, injection-safe by construction). Returns the RAW result:
  `{reviewText, threadId, status}`. **Normalization of review text into
  findings is explicitly not the engine's job** — it belongs to the
  calling script.
- `parallel(thunks)` → runs thunks; **barrier**; a rejected thunk resolves
  to `null` in the result array — the call itself never rejects.
- `pipeline(items, ...stages)` → per-item stage chains, **no barrier**;
  a throwing stage nulls that item and skips its remaining stages. Stage
  callbacks receive `(prevResult, originalItem, index)`.
- `log(msg)` → `[workflow]` stderr line + journal event.
- `args` → the `--args` JSON, verbatim.

Semantics mirror Claude Code's Workflow tool so the mental model transfers.

### 5. Run state, journal, resume

Per-run directory: `$CLAUDE_PLUGIN_DATA/workflows/<run-id>/`

- `journal.jsonl` — **event-sourced**, torn-tail tolerant: a `started`
  record when a hook call dispatches (kind, cache key, thread id once
  known) and a `finished` record on settle (result or error). A torn or
  missing final line invalidates only that record, never the file.
- **Cache identity is content-keyed, not order-keyed**: cache key =
  `(hook kind, label, SHA-256 of prompt+opts, occurrence #)` where
  occurrence # disambiguates deliberate repeats. Parallel calls may
  finish in any order; resume replays every `finished` record whose key
  matches and re-runs everything else. A `started`-without-`finished`
  call re-runs as a fresh turn (the recorded thread id is context, never
  a mid-turn continuation — the protocol has none).
- **Run lease**: a lockfile (pid + timestamp) in the run directory; a
  second `--resume` of a leased, live run refuses. Dead-pid leases are
  broken automatically.
- **Repo fingerprint**: HEAD sha + a hash of `git status --porcelain`
  recorded at run start. `--resume` against a differing fingerprint
  refuses (cached analysis of a changed tree is stale by definition);
  re-running fresh is always available.
- `workers.json` — live worker pids (for cancel). `result.json` — the
  final stdout payload.

## First consumer: `workflows/code-review.mjs`

A multi-lens review panel packaging the doctrine the multilens work
validated — one lens-free sweep + scalpel lenses, native reviewer as the
engine — as a single workflow run. Deliberately simpler than the discarded
argus ladder: no mechanical grouping, no refuter votes, no effort ladder;
one strong verifier judges the pool.

**Args:** `{ base }` required (merge-base diff target, `review --base`
semantics); optional `{ cwd, finderModel, finderEffort, verifierModel,
verifierEffort, lenses }`.

**Shape — 6 finders + 1 verifier** (models fixed by owner: finders
gpt-5.6-sol/xhigh, verifier gpt-5.6-sol/high):

1. **Lens derivation** (cheap, sol/medium `agent()` turn): reads the diff
   stat and summary, writes **five diff-derived structural scalpel
   mandates** — concrete focus statements anchored on this diff's actual
   surfaces ("authorization and actor-identity assumptions in the changed
   API routes"), not generic taxonomy labels. The derivation prompt names
   the five defect families from the X1 taxonomy (changed-logic accuracy,
   cross-file contract impact, removed/moved behavior, security surface,
   performance/resources) as coverage inspiration, but the mandates must
   be diff-specific. Callers may bypass derivation by passing `lenses`
   explicitly. *Rationale: the lens-as-scalpel evidence — a lens
   redirects the run's whole attention budget, so a taxonomy family
   irrelevant to this diff would waste an entire finder.* (Owner
   confirmation pending — see Open Questions.)
2. **Six parallel finders**: one lens-free `review({base})` sweep + five
   `review({base, lens})` scalpels, all native codex review at
   sol/xhigh (per-worker app-server config). Native review is the
   benchmark-winning engine; scalpels ride `developer_instructions`
   exactly as `reviewing-prs` ships today.
3. **Mechanical candidate extraction** (script code, no model): parse
   each finder's `reviewText` into candidate stubs
   (`[P#] title — path:lines` + body), assigning stable ids
   (`<finder>#<n>`). Extraction failure guard: a text containing `[P`
   markers that yields zero stubs marks that finder **extraction-failed**
   (treated as a dead finder for coverage purposes) — a formatting drift
   can never silently become an empty pool.
4. **One verifier** — a single `agent()` turn at sol/high with a findings
   schema, receiving every stub (source-labeled) and free to re-read the
   diff in-repo. Returns, per candidate id:
   `{ id, verdict: "CONFIRMED"|"REFUTED", duplicateOf?, priority, comment }`.
   Verifier verdicts are binding — the script never re-judges.
   **Mechanically validated postconditions** (violation → one repair
   retry → else the run reports `interrupted`):
   - exact-set coverage: every input candidate id appears exactly once,
     no extras;
   - the `duplicateOf` graph is acyclic, targets existing candidate ids,
     and never targets a REFUTED entry.

**Assembly (deterministic script code):**

- Keep CONFIRMED, collapse duplicates onto their primary formulation,
  order P0 → P3.
- Verdict: `incorrect` iff ≥1 CONFIRMED survives; else `correct`; either
  degrades to `interrupted` under the coverage rules below.
- Output: findings entries (`[P#] title — path:lines` + verifier comment),
  verdict, explanation, and a coverage section naming every finder with
  its status and stub count (an all-clean run on a real diff where all six
  finders returned zero stubs is reported as suspicious in the coverage
  section, though not blocked).

**Coverage honesty:**

- A finder (sweep or scalpel) dead or extraction-failed after the
  engine's retry → the run proceeds, the output names the lost lens, and
  a would-be-clean verdict reports `interrupted`, never `correct`. The
  sweep dying is always `interrupted` (mirrors reviewing-prs'
  sweep-failure = round-failure rule).
- The verifier dead or postcondition-invalid after retry → `interrupted`
  with the raw stub pool attached; unverified candidates are never
  published as findings and never silently dropped.

**Pool bound:** native review self-caps per run (≈10 findings), so six
finders bound the pool structurally (≈60 worst case) — within one
sol/high context. No sharding in M0; revisit with data.

## Acceptance

Behavior-phrased; engine cases run against a **transport-faithful mock**
(see Testing).

1. **Engine happy path**: a fixture script exercising `agent` (with and
   without schema), `review`, `parallel` (one rejecting thunk → `null`),
   and `pipeline` (one throwing stage → nulled item) exits 0, prints the
   script's return JSON on stdout only, streams `[workflow]` lines on
   stderr only, and leaves `journal.jsonl` + `result.json` in the run dir.
2. **Schema repair, both failure shapes**: (a) malformed JSON, (b)
   **syntactically valid JSON violating the schema** (missing required
   key) — each triggers exactly one same-thread repair turn (mock asserts
   the repair prompt), then resolves; a third shape (repair also invalid)
   rejects.
3. **Resume, adversarial**: kill a run with calls A,B,C in flight where C
   `finished`, A `finished`, B has `started` only, and the journal's last
   line is torn. `--resume` serves A and C from cache (mock invocation
   counts prove it), re-runs B fresh, ignores the torn line. A second
   concurrent `--resume` while the first holds the lease refuses. A
   `--resume` after a commit touching the tree refuses on fingerprint
   mismatch.
4. **Concurrency cap at the leaf**: a script issuing 10 agents via bare
   `Promise.all` under `--max-concurrency 2` never has more than 2 live
   mock app-servers (mock asserts peak concurrency).
5. **Cancel and liveness**: SIGTERM to a running workflow kills all live
   mock worker processes and finalizes the job `canceled`; SIGKILL to the
   run followed by `status` shows the job lazily finalized `failed`, and
   two overlapping workflow runs both keep their summary records (lock +
   atomic replace).
6. **Verifier postconditions**: a mocked verifier response omitting one
   candidate id (or adding a phantom id, or a cyclic `duplicateOf`)
   triggers the repair retry; persistent violation yields `interrupted`
   with the stub pool attached — never a `correct` verdict.
7. **Coverage honesty**: one mocked lens finder dead twice → output names
   the lens and a would-be-clean verdict reports `interrupted`; mocked
   sweep dead → always `interrupted`.
8. **Panel quality gate (live, the X1 bench)**: run the panel workflow as
   an engine over `tests/review-bench/cases/seeded/case1..case5`
   (adapter analogous to run-case.sh's codex engine). Bar, predeclared
   per X1: **seeded recall ≥ the recorded single-codex baseline, and FP
   growth ≤ +1 across the whole seeded set** (baits count as FPs).
   Comparative evidence on `cases/real/` (esp. PR752: does the panel
   union approach the known 13-defect union?) is recorded in this spec's
   Surprises section. This is the eval evidence the repo requires for
   behavior-shaping content; the panel does not become a recommended
   engine anywhere until it passes.

An optional shakedown against the E2 diff may run for anecdote, pinned at
a frozen checkout (`3742a0f`, base `e0b1835`) — it is NOT an acceptance
gate: the E2 ledger records defects fixed across moving heads, not a
truth set for one frozen diff.

## Testing strategy

- Engine tests live at `tests/codex-companion/` with a
  `run-workflow-tests.sh` runner. The mock is a fake `codex` binary on
  PATH speaking the **real JSON-RPC transport shape** — initialization
  handshake, `turn/start`/`review/start` streaming notifications,
  interleaved events, torn output, schema-violating-but-valid-JSON final
  messages (per the mock-fidelity lesson: mock the awkward raw transport,
  never the parsed shape the caller wants).
- Every new assert must fail against the parent commit with a naming
  signature (test-discrimination discipline).
- The X1 run (acceptance 8) executes once during implementation; scores
  and adjudication land in `tests/review-bench/results/<run-id>/` like
  every prior bench run.

## Out of scope (M0)

- `write: true` workers and any replay of side-effectful steps (needs
  idempotency semantics first); per-agent worktree isolation; a frozen
  workflow-level snapshot worktree (fingerprint-refusal covers
  correctness; snapshotting is convenience — revisit if refusals annoy).
- Token budget accounting, nested `workflow()`, name registry,
  phase-grouped progress UI.
- Changes to existing verbs beyond the new verb registration and the
  workflow-scoped ledger locking; `review`/`adversarial-review`/`task`
  contracts are untouched.
- Wiring `reviewing-prs` to this workflow (its shell-based 1–4 fan-out
  stands; convergence is a natural M2 once the panel passes X1).
- Fix-wave orchestration: the panel reviews; fixing remains the calling
  session's loop. Parallelism replaces discovery breadth only — the
  serial fix→re-review cycle is intentionally kept.

## Open Questions (owner)

1. **Finder substrate + lens source.** Owner's original instruction:
   five FIXED taxonomy lenses (argus L1–L5) as schema-forced task turns.
   This spec's recommendation, per the repo's own shipped evidence:
   five DIFF-DERIVED scalpel mandates riding steered NATIVE review
   (`developer_instructions`), because (a) native review outperformed
   every prompted-agent configuration on the real-PR benchmark, and
   (b) a lens consumes its finder's whole attention budget, so a
   taxonomy family irrelevant to the diff wastes a sol/xhigh run.
   Reverting to fixed L1–L5 texts (still on native review) is a
   one-line change in the workflow script; reverting to schema-forced
   task-turn finders is also supported by the engine (`agent()` with the
   finder schema) but contradicts the benchmark. Decision needed before
   the panel script is written; the engine is unaffected either way.
2. (Noted, defaulted per owner) Verifier stays ONE model at sol/high, no
   refuter vote — the mechanical exact-set postconditions close the
   silent-laundering hole; a P0/P1 second-vote option and verifier-effort
   escalation remain script-level knobs if X1 results argue for them.

## Decision Log

- **Codex-native engine over Claude-side orchestration** (Workflow-tool
  hybrid with thin Claude subagents shelling to codex, or hand-launched
  parallel Bash). Rejected: N detached processes + pollers reintroduce
  the harness-kill and state-root races the campaign fought; not
  headless; not harness-independent.
- **General engine first, code-review as first consumer** — over
  code-review-first-extract-later and over full Workflow parity
  (budget/nesting/worktrees have no consumer yet). Owner, 2026-08-03.
- **Panel simplified away from the argus ladder** (owner, 2026-08-03):
  finder wave + ONE verifier, replacing mechanical grouping, packed
  verifier waves, and refuter votes.
- **M0 is read-only** (spec-review adoption, 2026-08-03): `write: true`
  dropped from M0 entirely — journal replay of side-effectful steps is
  unsound without idempotency semantics, and the first consumer never
  writes. Supersedes v1's write-passthrough-with-caveat.
- **Event-sourced, content-keyed journal; no mid-turn continuation**
  (spec-review adoption): v1's call-order prefix replay breaks under
  parallel completion order; v1's "continue a half-dead worker" claim is
  unsupported by the protocol (thread resume always starts a new turn).
  Replaced with started/finished events, content-keyed cache, run lease,
  repo fingerprint.
- **Native `review()` returns raw text; per-worker config-spawned
  app-servers** (spec-review adoption): `review/start` yields rendered
  `reviewText` with no effort field — v1's structured-payload +
  `effort` param claims were wrong. Effort and lens ride `-c` overrides
  on a directly-spawned per-worker app-server (with-effort.mjs
  mechanism); normalization moved to the script (extraction stubs +
  verifier).
- **Workflow-scoped ledger locking + liveness repair** (spec-review
  adoption): per-run state alone does not fix the cross-run `state.json`
  lost-record race, and cancel/status needed real process ownership
  (tracked worker pids, signal handlers, dead-pid finalization).
- **Engine-side schema validation** (spec-review adoption):
  `parseStructuredOutput` is JSON.parse-only; a syntactically-valid
  wrong shape would silently pass. Minimal structural validator added to
  the `agent()` contract and to acceptance.
- **X1 review-bench as the panel's quality gate** (spec-review adoption):
  v1's E2-ledger A/B could not reject a bad panel (no threshold; ledger
  is not a truth set for a frozen diff; unfrozen HEAD would include this
  work itself). Replaced with the existing seeded-recall + FP bar.
- **Diff-derived scalpel lenses on steered native review**
  (spec-review + multilens-evidence adoption; OWNER CONFIRMATION
  PENDING): supersedes v1's fixed L1–L5 schema-turn finders. Grounds:
  10/13-vs-8/13 native-review benchmark win; lens-as-scalpel
  attention-budget evidence; `developer_instructions` steering already
  shipped in reviewing-prs.
- **Native `review` as the overall sweep** — the native reviewer is
  codex's tuned general pass; a prompted imitation adds steering surface
  for no recall gain. (Unchanged from v1, now with benchmark grounding.)
- **Explicit context parameter over injected globals/VM** — trusted
  scripts; testable with a fake context. (Unchanged.)
- **Per-run state directory** — the durable artifact boundary.
  (Unchanged; no longer claimed to solve the shared-ledger race, which
  the locking decision above addresses.)
- **Default `--max-concurrency` 6, enforced at leaf spawns** — sized to
  the panel; revisit with A/B data. (Sharpened: leaf-level enforcement.)

## Surprises & Discoveries

- (2026-08-03, spec review) The independent critic surfaced that this
  repo had ALREADY run the core experiment: `tests/review-bench/` (X1)
  and the 2026-07-28 multilens execplan — native-review superiority,
  argus discarded, lens-as-scalpel, `developer_instructions` steering.
  The v1 spec was written blind to all of it (session context had been
  compacted past it). Lesson reinforced: the look-outside pass before
  locking a design must include *this repo's own* specs/execplans/bench
  results, not just external prior art.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-08-03: v1 — initial design from the brainstorming round following
  the E2 15-round serial campaign.
- 2026-08-03: v2 — adversarial spec review (codex sol/xhigh) adjudicated:
  5 findings adopted (resume model rebuilt event-sourced; native-review
  hook contract corrected to raw-text + config-spawned servers; ledger
  locking + process ownership added; verifier postconditions added; X1
  bench replaces the E2-ledger A/B as the quality gate; M0 restricted to
  read-only). Panel finder substrate revised to diff-derived scalpels on
  steered native review per repo evidence — flagged for owner
  confirmation (Open Question 1). Acceptance rewritten so every case
  discriminates (false-green table addressed).
