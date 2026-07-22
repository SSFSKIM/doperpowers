# Cloud-scale research synthesis — the board pipeline at enterprise fleet scale

> **Date:** 2026-07-23. **Status: round 1 synthesized; round 2 (four deep-research
> tracks) in flight — §7 slots marked PENDING fill as they land.**
>
> **Purpose.** Reference-architecture research for running the board pipeline
> (implementer workers + adversarial review workers over a ticket board) at
> enterprise-internal fleet scale: multiple large projects, **hundreds to
> thousands of worker runs per hour per project, multi-host**. Not a product
> sold to others. This doc is the convergence artifact the design spec will be
> written from, the same way `2026-07-11-symphony-comparison.md` fed the FD
> agenda and `2026-07-12-managed-agents-steals.md` fed the single-host infra.
>
> **Invariant boundary (fixed by the human, 2026-07-23):**
> - **Semantic layer FROZEN** — pre-code gate, park states, independent
>   adversarial review, tiered merge authority. Scale-forced changes must be
>   flagged explicitly (§5), never designed in silently.
> - **Substrate fully OPEN** — ticket store (Linear is a named candidate),
>   SSOT storage, dispatch, compute, credentials.
>
> **Sources — round 1** (six engineering articles, each deep-read by a
> dedicated agent with in-content citations followed; full reports in the
> session scratchpad, load-bearing content absorbed here):
> - Cursor, *Agent swarms and the new model economics* (Jul 20, 2026) + its
>   lineage posts *Scaling agents* and *Self-driving codebases*
> - Cursor, *What we've learned building cloud agents* (Jun 2, 2026) + the
>   Temporal case-study record
> - Cursor, *Development environments for your cloud agents* (May 13, 2026)
>   + cloud-agent setup docs
> - Cursor, *Run cloud agents in your own infrastructure* (Mar 25, 2026)
>   + self-hosted pool / Kubernetes-operator docs + `cursor/cookbook`
> - Cursor, *Bootstrapping Composer with autoinstall* (May 6, 2026)
>   + Composer 1/2 posts (Anyrun scale disclosures)
> - Anthropic, *Scaling Managed Agents: Decoupling the brain from the hands*
>   (Apr 8, 2026) + Managed Agents platform docs (self-hosted sandboxes)
>
> **Sources — round 2 (in flight):** ticket-store limits (Linear vs GitHub vs
> thin service), dispatch-engine selection (Temporal vs alternatives), sandbox
> substrate (isolation tech + numbers), review/merge at scale (submit-queue
> prior art, agent-review data).

---

## 0. Verdict up front

Every article, read independently by a separate agent, returned the same two
top-level judgments:

1. **The doctrine survives.** "The durable log is the identity of the work;
   compute is disposable" is independently converged on by Cursor (loop /
   machine state / conversation state decoupling, at 100× our target scale)
   and Anthropic (session / harness / sandbox). Nothing in six articles
   contradicts it. What scale changes is *where each piece lives* (§1).
2. **No scale-forced semantic-layer change was found.** All six readers
   checked explicitly; all six returned "none forced." What they returned
   instead is a short list of pressure points where the substrate must do
   real work to keep the frozen semantics viable (§5) — plus one previously
   settled substrate decision that must be re-judged rather than inherited
   (resident-vs-invoked orchestration, §2.1).

The single most load-bearing external datum: **Cursor's v1 cloud-agent
substrate — worker nodes picking up agents and looping them to completion,
i.e. structurally our file-based daemon registry — ran at one nine of
reliability; migrating the loop into Temporal took them past two nines at
>50M actions/day across >7M workflows/day.** Our current substrate is their
measured failure case.

## 1. The doctrine sharpens: one SSOT becomes three

Today the doctrine is implemented as "board = SSOT, session JSONL on the
host volume = resume optimization." At fleet scale that conflates three
different authorities, and the articles cleanly split them:

| authority | owns | lives | today |
|---|---|---|---|
| **Ticket state** | what work exists, its lifecycle state, the human-answer record | the board (store TBD — §7.1) | GitHub issues ✓ |
| **Run ownership** | which execution owns a ticket *right now*; leases, retries, timeouts, heartbeats | durable-execution engine (§2.1) | file registry (host, pid) ✗ |
| **Run history** | everything that happened inside a run; resume context | central append-only session store (§2.2) | JSONL on host volume ✗ |

The board never becomes fictional about in-flight work (its picture is
derived from engine state), the engine never becomes a second ticket-state
authority (workflow = dispatch + retry only; every semantic transition is
written to the board and **the board wins on conflict**), and the log stops
being load-bearing for *ownership* — which is exactly the arbiter-less gap
that made Cursor's v1 (and would make ours) fall over at multi-host.

Two corollary invariants, worth stating in the spec verbatim:

- **Snapshots are cache, never identity.** Cursor leans on VM
  checkpoint/restore/fork for cheap resume; they also expire snapshots (90
  idle days) and call caching "best effort." A deleted snapshot must never
  lose work — only warm-start time. If this isn't written down, snapshot
  state quietly becomes load-bearing.
- **Compaction never rewrites the log.** Anthropic's session store makes
  compacted context a derived *view* over an untouched event log. Our
  session store must guarantee the same: append-only, ranged reads, any
  summarization downstream.

## 2. Substrate verdicts by axis

### 2.1 Dispatch and run ownership → durable-execution engine (re-judgment of "invoked, never resident")

The 2026-07-12 resolution ("import the functions, refuse the form" — cron ×
idempotent one-shot passes, no resident orchestrator) was argued half from
principle and half from scale ("dispatch latency is noise against multi-hour
turns"). The scale half is now void, and the principle half is answered
better by an engine than by cron:

- The principled objections to residency (in-RAM claims force
  single-instance; restart evaporates the retry queue; a resident service
  needs its own watchdog) are objections to a *hand-rolled* resident
  orchestrator. A durable-execution engine keeps claims, retries, and
  timeouts in durable storage with horizontal workers — it is the sweep
  tick's semantics (idempotent passes over durable state) at industrial
  throughput.
- Shape stolen from Cursor's production account: **short task-scoped
  workflows** — one workflow per ticket-phase (gate → implement → open-PR
  → review → land), never one eternal workflow per worker — because
  eternal workflows block code upgrades mid-flight and we will have
  thousands of in-flight runs during every deploy. Continuity across
  phases via signal-with-start. Per-step activities carry their own
  timeout/retry so a provider blip retries a step, not a run.
- Shape stolen from Anthropic's self-hosted-sandbox docs: **claim/ack queue
  with lease reclaim** (`reclaim_older_than_ms`) as the dead-worker recovery
  primitive, and the three fleet metrics — queue `depth` (autoscaling
  signal), `pending` = claimed-not-acked (stall detection),
  `workers_polling` (liveness) — as the substrate's core gauges.
- The §9 sweep-tick checklist (transient auto-resume with exponential
  backoff, stall detection, board-driven cancel, dispatch-until-cap,
  startup recovery) transfers **as the engine's workflow logic**, not as
  cron scripts — same functions, industrial carrier. Board-driven
  cancellation (FD-8) becomes: ticket leaves the active states → engine
  cancels the workflow → worker terminated within one tick; the board is
  finally a control plane in both directions.

Engine selection (Temporal vs queue+controller vs lighter engines) and the
fairness/admission-control design: **round 2, §7.2.**

### 2.2 Workers and fleet shape → outbound-only, warm-pool, exit-and-replace

Convergent across Cursor's self-hosted product and Anthropic's worker
protocol; this axis is essentially settled:

- **Outbound-only workers.** Workers dial the control plane over long-lived
  HTTPS; no inbound ports, no VPN choreography. Adding a host = one command
  + a pool token. Hosts become fungible across clouds/on-prem. (This
  inverts today's model where the dispatcher reaches into hosts.)
- **Warm pool with idle-count semantics.** Desired state counts *idle*
  workers (`readyReplicas`); a claim removes a worker from the ready set
  and the controller backfills. Readiness doubles as the claim signal
  (`/readyz` 503-while-busy), which lets any generic orchestrator do
  scale-down and rolling updates while **never terminating a busy worker**.
- **One session per worker; exit-0-and-replace.** A finished worker
  terminates and is replaced fresh — cross-ticket contamination is
  prevented structurally, not by cleanup discipline. Idle-grace before
  release (their 600 s) adapts to our review-bounce window: keep the
  claim briefly in case review returns the PR for a same-worker fix-up.
- **Label-based routing with reserved, non-spoofable labels** (`repo=`
  auto-derived; `pool=` named): per-team pools, and — our twist —
  **separate implementer and reviewer pools**, with reviewer sandboxes
  read+execute only (a readonly worker class both saves money and
  *strengthens* adversarial independence).
- **Fleet API as the portable scaling contract**: two numbers per pool
  (`totalConnected`, `inUse`); Kubernetes operator is one optional consumer
  of it, not the architecture.
- **Session-end reason taxonomy** as a first-class counter (clean end /
  stream error / closed / error / timeout / aborted) — this is what lets
  the pipeline distinguish infra failure (re-dispatch) from agent failure
  (park), per worker, mechanically.

### 2.3 Environment layer → a new durable artifact class

The strongest genuinely-new import of the whole research round. Cursor's
flagship operational failure mode: **an incomplete environment does not
error — it silently degrades output quality fleet-wide, and gets
misattributed to the model.** At fleet scale we cannot afford to discover
that by manual root-causing. The layer that prevents it:

- **Environment-as-code, in-repo**: `build` (Dockerfile, toolchain only —
  never COPY the project; the platform owns checkout) / `install`
  (idempotent) / `start`, with repo → team resolution. No per-worker
  snowflakes: personal overrides are an interactive-IDE feature, a
  reproducibility leak for an autonomous fleet.
- **Certification gate (autoinstall pattern)**: a specifier agent proposes
  N verification commands + expected outputs for the repo *before* any
  attempt; a separate executor agent must make a sampled subset pass;
  bounded fresh retries; success emits a **certified snapshot + the command
  contract**. Propose-then-verify with criteria fixed in advance — our
  adversarial-review shape applied to infrastructure. Where Cursor
  discards after 5 failures (elastic repo supply), we **park**: a
  needs-human infrastructure ticket. Existing machinery absorbs it.
- **Environment registry**: per (repo, env-relevant key) → certified
  snapshot + contract, alongside board/engine/session-store. It is a cache
  *with a certificate*, not identity — losing it costs a re-certification
  run, nothing more. Doctrine intact; substrate inventory grows by one.
- **Contract commands double as dispatch-time health probes**: one contract
  command runs before the worker touches the ticket; failure routes to
  re-certification instead of burning the run. Placement matters: this is
  a **dispatcher precondition**, not a new clause in the pre-code gate —
  bolting it into the gate skill would be a semantic edit; keeping it in
  the dispatcher is substrate.
- **Snapshot ladder for cold-start**: layer cache (70% faster on hit) →
  automatic post-install checkpoint → restore per run; idempotent
  `install` is the invariant that makes cache misses safe; GC by idle
  expiry. At hundreds of runs/hour/repo this ladder is the difference
  between a fleet and a `npm ci` storm.
- **Mock fence (protects a frozen invariant)**: certification agents mock
  aggressively (fake DBs, MinIO-for-S3, mock auth users). Unfenced, green
  tests against fake services would hollow out adversarial review and make
  tiered merge authority meaningless. Rule: mocks are allowed, must be
  **declared in the environment manifest, and the manifest is surfaced to
  the review worker** so it can weigh what green actually proves. Mock
  dev-service sidecars: yes. Mock the system under test: no.
- **Degrade-don't-fail, adapted**: on env-build failure Cursor boots a
  fallback base image with loud warnings (an interactive user sees them).
  Our autonomous adaptation: fallback env + "environment unverified" as
  gate-relevant input → verify the test loop actually runs before
  building, park needs-human if it doesn't. Reuses frozen semantics; no
  new state.
- **Env-version provenance**: record the environment version in each PR's
  provenance (Cursor shows agents their env version; they don't say if it
  reaches the PR — we should do it regardless).
- Drift *detection* (what invalidates a certificate as the repo moves) was
  the #1 open question from two independent readers: **round 2, §7.3.**

### 2.4 Credentials → structural unreachability over scoping

Anthropic's argument, accepted: narrow token scoping is itself a stale-able
assumption ("Claude is getting increasingly smart"); the durable posture is
tokens **structurally unreachable** from where generated code runs. FD-6's
recorded ladder (fine-grained PAT first, broker only if blast radius still
too wide) collapses at run-count × team-count; go straight to:

- **Auth-bundled-with-resource for git** (cheap at ANY scale; we should
  have taken it the first time): short-lived installation token wired into
  the remote at sandbox init; the agent never sees a token; nothing to
  leak into env or transcript.
- **Per-claim, least-privilege, short-lived credentials** minted at
  dispatch (STS-style ~1 h expiry, auto-refresh), scoped per environment;
  build secrets scoped to the build step and absent from the running
  agent's env; per-environment egress allowlists.
- **Merge-capable credentials issued only to the landing path, never to
  implementers** — the credential topology mirrors tiered merge authority.
- **Vault + proxy for service credentials** (the previously rejected
  resident service): accepted at this scale, implemented against the
  enterprise's existing secrets manager rather than bespoke machinery.
- **Rotation without restarts**: controller-managed short-lived tokens at
  a mounted path, re-read on reconnect.
- Honest boundary to document: if external model APIs are used, **the
  model context window is an egress path no data-plane design closes**
  (Cursor's own docs concede file chunks transit their cloud even in
  "self-hosted" mode).

### 2.5 Observability → contention telemetry as circuit breakers

Cursor's swarm spiral (70,000+ accelerating conflicts) was caught *by
humans watching*. At fleet scale the substrate must watch itself:

- Per-repo **conflict rate, hottest-file contention, PR-rework rate,
  commit-churn ratio** as automatic circuit breakers — a spiraling repo
  gets dispatch paused mechanically.
- Commit/PR volume is a **vanity metric**; conflict acceleration is the
  health signal.
- Failure-boundary separation (Anthropic's lesson): harness/dispatch logs
  live OUTSIDE data-bearing sandboxes, so harness bug / transport drop /
  sandbox death are distinguishable without entering user-data
  environments.
- **Megafile machinery riding the same telemetry**: any worker can flag a
  hotspot file → merge-queue freeze → auto-registered decomposition
  ticket. (Tragedy-of-the-commons fix with zero new semantics.)

### 2.6 Economics → tier by phase, overspend on review

From the swarm post's controlled runs (quality roughly invariant to model
mix; cost varied ~8×; worker fleets 23× apart in cost at similar quality):

- **Model tier is a per-phase routing decision, not per-worker**: frontier
  models at decision points (pre-code gate, decomposition, park/escalate
  judgment, review verdicts), cheap models for implementation bulk inside
  a gated, well-scoped ticket. Workers carried 69–90%+ of tokens in their
  runs — the bulk is where the cheap tier pays.
- **Evaluate gate/planner models on total downstream run cost**, not their
  own bill (their Fable-planner run: cheapest planner bill, most expensive
  run — decomposition style drives worker verbosity).
- **Review is underpriced**: no single lens catches everything; decorrelated
  lenses stack; review is far cheaper than the work it audits. Within the
  frozen "independent adversarial review": one review *verdict*, N
  decorrelated lenses beneath it (different models, different evidence
  diets: transcript-blind / transcript-aware / codebase-only).
- **Per-model prompt profiles are a substrate config object** (their
  GPT-5.6 Sol wording-sensitivity spirals): worker/planner prompts
  versioned per model family.
- Capacity datum for host sizing: at dense agent packing, **disk I/O from
  build artifacts — not CPU or RAM — was the single-host ceiling** (many
  GB/s); budget NVMe per worker slot and expect shared remote build caches
  to matter. Feasibility calibration: Cursor runs *hundreds of thousands*
  of concurrent sandboxes; our thousands-per-hour target is two orders of
  magnitude inside proven territory.

### 2.7 What we explicitly do NOT import

- **Their brain-in-cloud split literally** — our loop runs on the worker
  (Claude Code / Codex CLI); moving it into a control plane means
  reimplementing the harness and inheriting per-tool-call WAN latency they
  never publish numbers for. We adopt the *consequence* (state central,
  executor stateless), not the topology.
- **Managed Agents (the product) as the substrate** — beta API, session
  data on Anthropic's control plane, forecloses the mixed Claude+Codex
  fleet. Best-documented reference design for our own control plane; not
  the control plane.
- **Custom VCS** — justified at ~1,000 commits/sec into one tree; our
  concurrency unit is the ticket/PR and git + merge queue holds. Reopen
  only if intra-ticket swarms ever show git lock contention in telemetry.
- **Dynamic planner-tree topology replacing the board** — their tree fits
  one monolithic goal; our board fits a stream of independent tickets, and
  tree-shaped work already has a semantic answer (decomposing-goals).
- **Per-commit error budgeting with no human in loop** — their green-branch
  fixup works inside a run; our landed PRs are consumed continuously;
  tiered merge authority IS our error-budget mechanism.
- **Session-as-REPL (RLM-style) context objects; harness-shrinkage as gate
  license** — the shrinkage ratchet applies to mechanical scaffolding, not
  semantic governance; their own trajectory shrank means, not
  accountability.

## 3. The reopen-trigger audit (past deferrals, resolved)

| past decision (doc, date) | recorded trigger | verdict at fleet scale |
|---|---|---|
| per-worker ephemeral compute — rejected (steals §2, 07-12) | "concurrency outgrows one host" | **FIRED — adopt** (§2.2) |
| on-demand sandbox provisioning — rejected (steals §4) | thousands of sessions | **FIRED — adopt**, plus gate-aligned lazy provisioning: gate runs sandbox-less, provision only after pass (their TTFT p50 −60% analogue) |
| MCP vault + proxy — rejected (steals §4) | multi-tenant scale | **FIRED — adopt scoped** (§2.4) |
| FD-6 credential ladder (PAT-first) | unattended phase | **superseded** — skip the PAT rung (§2.4) |
| FD-8 board-driven cancel | unattended phase | **FIRED** — engine cancellation, board as two-way control plane (§2.1) |
| §9 sweep tick (cron, invoked-not-resident) | unattended phase | **functions transfer, carrier changes** — engine workflows, not cron (§2.1) |
| getEvents() interrogation layer — rejected (steals §4) | no consumer | **half-fired** — adopt durable-store + ranged reads; defer model-driven rewind |
| session-as-REPL — rejected (steals §4) | no consumer | stands rejected |
| FD-2 hard transition schema | third friction case | schema stays; **enforcement location moves** — open, §7.1 |

## 4. Semantic-layer flags (for the human; no changes designed in)

All six readers confirmed: **no scale-forced semantic change found.** Five
pressure points where the substrate must carry load to keep it that way —
and one honest conditional:

1. **Park states need queue infrastructure.** At thousands of runs/hour,
   even a few percent parking makes park queues a human-throughput
   bottleneck. The states survive only with routed park queues,
   batching, notifications, and SLOs. (Substrate work; their alternative —
   prompt agents to never stop — is worse than our named states.)
2. **The human merge tier becomes the bottleneck by construction.** The
   substrate must (a) make auto-land carry the overwhelming majority,
   (b) queue/budget the human tier explicitly, (c) use stacked lenses to
   widen what safely auto-lands. **Conditional flag:** if human-tier volume
   still exceeds human capacity after (a)–(c), that is the one place scale
   genuinely pressures the frozen layer — e.g. a fourth authority tier
   (multi-lens unanimous auto-land for medium changes). Option named for
   the human; nothing proposed now. Round-2 evidence: §7.4.
3. **A third agent species exists at swarm scale** — neutral maintenance
   agents (merge-resolver, doc-reconciler, megafile-decomposer) that are
   neither implementer nor reviewer. Recommended absorption: auto-registered
   maintenance tickets (keeps the two-species semantic layer intact);
   the alternative (acknowledge a third species) is the human's call.
4. **"One review worker" should read "one review verdict, N lenses".**
   Their evidence says lens decorrelation is the review multiplier; the
   frozen layer's *independence* guarantee is untouched — enrichment, not
   change.
5. **Hand-passing stops at the review boundary.** Anthropic's "brains pass
   hands to one another" is rejected across implement/review: a reviewer
   inheriting the implementer's sandbox erodes adversarial independence.
   Fine within an implementer's own retry chain.
6. (Enforcement note, not a change:) their split-brain fix — decision
   ownership is non-delegable at the parent; no two child tickets may own
   the same question — is already our decomposition doctrine, but at swarm
   scale it wants a gate-check, not just doctrine prose.

## 5. Cross-cutting design rules the spec must carry

1. Board = SSOT of ticket state; engine = SSOT of run ownership; session
   store = SSOT of run history. Board wins conflicts on ticket state.
2. Snapshots (env or VM) are cache with certificates, never identity.
3. Compaction/summarization never rewrites a durable log.
4. Environment readiness is a dispatcher precondition, not a gate clause.
5. Mocks exist only if declared in the manifest the reviewer sees.
6. Credentials: structurally unreachable beats scoped; merge authority and
   credential topology are the same shape.
7. Workers: outbound-only, one-session, exit-and-replace, never kill busy.
8. Every bounded thing (retries, pools, queues) parks loudly at its bound —
   nothing loops silently and nothing discards work.
9. Autonomy prompting: blocking is expensive in the cloud — bias to loud,
   routed escalation (park), never silent waiting.
10. Reviewer sandboxes are read+execute; fresh, never inherited.

## 6. Feasibility calibration

- VM-per-run at our scale: proven with two orders of magnitude of headroom
  (Cursor: hundreds of thousands concurrent sandboxes).
- Reliability delta of the engine migration: one nine → two-plus nines at
  50M actions/day (their measured numbers; our v1-shaped substrate is the
  failure case).
- 40%+ of Cursor's internal PRs are agent-authored — validating that review
  capacity, not implementation capacity, is the scaling constraint. They
  publish nothing about how that volume is reviewed: our costliest
  component has no public reference — hence round-2 track §7.4.

## 7. Round-2 tracks (PENDING — filled as reports land)

### 7.1 Ticket SSOT: Linear vs GitHub-sharded vs thin board service
PENDING. Question: does 1,000 runs/hour × ~10 board ops/run fit each
option's limits; where does the FD-2 transition graph get enforced
server-side; board↔forge PR linkage.

### 7.2 Dispatch engine: Temporal vs queue+controller vs lighter engines
PENDING. Question: ops burden self-hosted, claim/lease semantics, fairness
and admission control, idempotent side effects (the double-git-push
problem), doctrine fit (engine must not become a ticket-state authority).

### 7.3 Sandbox substrate: isolation tech, snapshot numbers, drift detection
PENDING. Question: Firecracker/CRIU/gVisor/containers for hours-long
runs under an internal (prompt-injection, not adversarial-tenant) threat
model; warm-state distribution; the drift-detection answer; capacity math
against the disk-I/O ceiling.

### 7.4 Review & merge at scale: submit-queue prior art, agent-review data
PENDING. Question: merge-queue throughput ceilings per repo; auto-land
criteria prior art; post-merge detection + cheap revert vs deeper pre-merge
review for low-blast-radius classes; evidence for/against a fourth
authority tier (feeds flag §4.2).

## 8. Open questions that survive both rounds → spec's decision agenda

(To be finalized after §7 lands; seeded now from round 1:)

- Retry/idempotency for side-effect-heavy agent steps — what prevents the
  duplicate push after a crash between "tool executed" and "event emitted."
- Prompt-cache economics of harness-as-cattle (rebooted harness cold-starts
  the cache; unquantified everywhere).
- Re-certification cadence for environments (nothing published; likely
  lockfile/manifest-hash keying + probe-failure-driven).
- Claim-regime behavioral economics: what lease semantics keep agents bold
  but safe (Cursor: OCC bred risk-aversion; nobody has published the right
  regime).
- Multi-repo atomic changes vs tiered merge authority at cross-repo scope
  (silent in all sources).
- Park-queue SLO design — entirely ours to invent; no prior art surfaced.
