# Cloud-scale research synthesis — the board pipeline at enterprise fleet scale

> **Date:** 2026-07-23. **Status: research complete — round 1 (six-article
> deep read) and round 2 (four deep-research tracks) both synthesized.
> Next artifact: the design spec, working §8's decision agenda.**
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
> dedicated agent with in-content citations followed; full reports archived
> in `docs/doperpowers/research/2026-07-23-cloud-scale/`, load-bearing
> content absorbed here):
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
> **Sources — round 2** (four deep-research tracks, each grounded in primary
> sources with per-claim confidence notes; full reports with source lists in
> `docs/doperpowers/research/2026-07-23-cloud-scale/` as `r2-*.md`, verdicts
> absorbed into §7): ticket-store limits
> (Linear/GitHub official rate-limit docs, Symphony spec, Kubernetes API
> concepts), dispatch engines (Temporal docs/testimonies, Hatchet, River/Oban,
> Kueue, SQS), sandbox substrate (Firecracker project docs, gVisor production
> numbers, GKE Agent Sandbox, NVMe-vs-EBS benchmarks, E2B/Modal/Daytona
> pricing), review/merge at scale (Google TAP paper + SWE book, Uber
> SubmitQueue EuroSys 2019, Meta TestGen-LLM/Conveyor, Cursor Bugbot,
> Anthropic Code Review, Kayenta).

---

## 0. Verdict up front

Every article, read independently by a separate agent, returned the same two
top-level judgments:

1. **The doctrine survives.** "The durable log is the identity of the work;
   compute is disposable" is independently converged on by Cursor (loop /
   machine state / conversation state decoupling, at 100× our target scale)
   and Anthropic (session / harness / sandbox). Nothing in six articles
   contradicts it. What scale changes is *where each piece lives* (§1).
2. **No scale-forced semantic-layer change was found.** Five of six
   readers returned "none forced" verbatim; the sixth (agent swarms)
   implies it while raising the most pressure points. What they returned
   instead is a short list of pressure points where the substrate must do
   real work to keep the frozen semantics viable (§5) — plus one previously
   settled substrate decision that must be re-judged rather than inherited
   (resident-vs-invoked orchestration, §2.1).

The single most load-bearing external datum: **Cursor's v1 cloud-agent
substrate — worker nodes picking up agents and looping them to completion,
i.e. structurally our file-based daemon registry — ran at one nine of
reliability; migrating the loop into Temporal took them past two nines at
>50M actions/day across >7M unique workflows.** Our current substrate is their
measured failure case.

## 1. The doctrine sharpens: one SSOT becomes three

Today the doctrine is implemented as "board = SSOT, session JSONL on the
host volume = resume optimization." At fleet scale that conflates three
different authorities, and the articles cleanly split them:

| authority | owns | lives | today |
|---|---|---|---|
| **Ticket state** | what work exists, its lifecycle state, the human-answer record | the board (store TBD — §7.1) | GitHub issues ✓ |
| **Run ownership** | which execution owns a ticket *right now*; leases, retries, timeouts, heartbeats | durable-execution engine (§2.1) | file registry (host, pid) ✗ |
| **Run history** | everything that happened inside a run; resume context | central append-only session store (no dedicated research track — §8 item 8) | JSONL on host volume ✗ |

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
idempotent one-shot passes, no resident orchestrator) was argued from
principle in the symphony comparison's §9: in-RAM claims force
single-instance, restart evaporates the retry queue, a resident service is
a new failure domain needing its own watchdog. (The oft-quoted "dispatch
latency is noise against multi-hour turns" belongs to the steals doc's
*per-worker-compute* rejection, not to the residency call — and review
capacity, not dispatch latency, remains the system bottleneck at any scale,
per §4.2.) The re-judgment stands on different ground: a durable-execution
engine answers all three principled objections directly — claims, retries,
and timeouts live in durable storage under horizontally scaled workers —
while fleet scale adds two needs a batch cron cadence cannot serve:
seconds-to-minutes lease reclaim and admission ordering across tenants:

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
- The symphony comparison's §9 sweep-tick checklist (transient auto-resume with exponential
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
  the dispatcher is substrate. (Honestly: the boundary is porous — the
  degrade path below routes "environment unverified" *into* the gate/park
  machinery; the placement claim is about where the check runs, not where
  its failures route.)
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
  diets: transcript-blind / transcript-aware / codebase-only) — an option
  for the human, not an assumed enrichment; see flag §4.4 on the evidence
  boundary a transcript-aware lens would cross.
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
| symphony §9 sweep tick (cron, invoked-not-resident) | unattended phase | **functions transfer, carrier changes** — engine workflows, not cron (§2.1) |
| getEvents() interrogation layer — rejected (steals §4) | no consumer | **half-fired** — adopt durable-store + ranged reads; defer model-driven rewind |
| session-as-REPL — rejected (steals §4) | no consumer | stands rejected |
| FD-2 hard transition schema | third friction case | FD-2's actual question (schema-vs-config granularity) stays deferred on its original trigger; enforcement *location* moves server-side as a consequence of the NEW board-service decision (§7.1) — not FD-2's resolution |

## 4. Semantic-layer flags (for the human; no changes designed in)

Five of six readers state it verbatim (the agent-swarms reader implies it,
with the most equivocation): **no scale-forced semantic change found.** Six
pressure points where the substrate must carry load to keep it that way —
one carrying an honest conditional:

1. **Park states need queue infrastructure.** At thousands of runs/hour,
   even a few percent parking makes park queues a human-throughput
   bottleneck. The states survive only with routed park queues,
   batching, notifications, and SLOs. (Substrate work; their alternative —
   prompt agents to never stop — is worse than our named states.)
2. **The human merge tier becomes the bottleneck by construction.** The
   substrate must (a) make auto-land carry the overwhelming majority,
   (b) queue/budget the human tier explicitly, (c) optionally use stacked
   lenses to widen what safely auto-lands — (c) is itself a merge-authority
   change and therefore the human's call, not a substrate must; note also
   that today's shipped auto-land tier is *narrower* (size- and
   scope-bounded) than the "small/safe" shorthand suggests, so the
   beyond-precedent concern (flag 7) attaches to the proposed widening,
   not the existing design. **Conditional flag:** if human-tier volume
   still exceeds human capacity after (a)–(c), that is the one place scale
   genuinely pressures the frozen layer — e.g. a fourth authority tier
   (multi-lens unanimous auto-land for medium changes). Option named for
   the human; nothing proposed now. Round-2 evidence: §7.4.
3. **A third agent species exists at swarm scale** — neutral maintenance
   agents (merge-resolver, doc-reconciler, megafile-decomposer) that are
   neither implementer nor reviewer. Recommended absorption: auto-registered
   maintenance tickets (keeps the two-species semantic layer intact);
   the alternative (acknowledge a third species) is the human's call.
   The absorption's weak seam is specifically the merge-resolver: at ~40%
   conflict probability with just 16 in-flight changes (§7.4), it runs at
   merge-queue tempo and cannot absorb a full gate+review cycle per
   conflict — this is where the third-species question gets real.
4. **"One review verdict, N lenses" — an option needing the human's yes,
   not an assumed enrichment.** The evidence says lens decorrelation is
   the review multiplier — but a transcript-aware lens crosses an evidence
   boundary today's reviewer deliberately keeps closed (the review engine
   receives no ticket/spec/transcript input at all), and an aggregation
   stage restructures a deliberately single-engine design. The
   independence argument (the other lenses stay blind) is an argument to
   *make* to the human, not to assume under "untouched."
5. **Hand-passing stops at the review boundary.** Anthropic's "brains pass
   hands to one another" is rejected across implement/review: a reviewer
   inheriting the implementer's sandbox erodes adversarial independence.
   Fine within an implementer's own retry chain.
6. (Enforcement note, not a change:) their split-brain fix — decision
   ownership is non-delegable at the parent; no two child tickets may own
   the same question — is already our decomposition doctrine, but at swarm
   scale it wants a gate-check, not just doctrine prose.

**Round-2 additions (review/merge track, §7.4):**

7. **No public precedent for human-free merge of general agent code.**
   Anthropic, Google, and OpenAI all keep a human approval per change even
   at >90% agent authorship; every published auto-land policy is bounded by
   a machine-verifiable *change class* (dependency bumps, pattern-conforming
   LSC shards, guardrailed test additions), never by diff size. Our
   auto-land tier goes beyond public practice — not a reason to retreat, but
   its safety case rests on our own guardrail design (change-class whitelist
   + verifier stage + canary/revert), not on industry precedent.
8. **Batch verification vs per-change gating.** The only proven mechanisms
   at hundreds of landings/hour are TAP-style batching + auto-bisection
   (per-change verification abandoned) or SubmitQueue-style speculation +
   build-target independence (per-change verification kept, at speculation
   cost). If the frozen layer is read as "every change individually verified
   pre-merge," batching pressures that reading. Options: accept
   batch+bisect as satisfying the intent / pay for speculation / per-repo
   choice by risk class. Human's call at spec time.
9. **The verifier stage is load-bearing and must be named.** Cursor
   (8-pass voting → one aggressive finder + validator) and Anthropic
   (parallel hunters → verification filter → severity rank; vendor-reported
   <1% findings marked incorrect) converged on the same shape; HackerOne's 2026
   bug-bounty pause under AI-amplified volume shows an unfiltered finding
   stream can DoS a human tier. The semantic layer implies but does not
   name a false-escalation-rate SLO on what reaches humans; the spec
   should name it (substrate component, not a semantic change).
10. **Post-land canary is a de-facto authority tier in every org at this
   scale** (Kayenta: score → auto-promote / route-to-human / auto-rollback;
   Meta: 2% canary ladder, 97% of deploy pipelines human-free). This
   sharpens flag 2's conditional: the "fourth tier" may be better framed as
   **auto-land-under-watch** — landing conditional on canary verdict —
   which every reference org has in substance. Presented as an option.

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
10. Reviewer sandboxes are fresh, never inherited: read-only repo mount
    with full build/test execution, and no push credentials.

## 6. Feasibility calibration

- VM-per-run at our scale: proven with ample headroom — Cursor runs
  hundreds of thousands of *concurrent* sandboxes vs our ~1,000–20,000
  concurrent (concurrency = start rate × mean run duration; see §7.3) —
  one to two orders of magnitude depending on where on the duration curve
  we land.
- Reliability delta of the engine migration: one nine → two-plus nines at
  50M actions/day (their measured numbers; our v1-shaped substrate is the
  failure case).
- 40%+ of Cursor's internal PRs are agent-authored — validating that review
  capacity, not implementation capacity, is the scaling constraint. They
  publish nothing about how that volume is reviewed: our costliest
  component has no public reference — hence round-2 track §7.4.

## 7. Round-2 tracks (landed 2026-07-23; full reports in `research/2026-07-23-cloud-scale/`)

### 7.1 Ticket SSOT → thin self-owned board service; Linear as human mirror

**Verdict: neither SaaS tracker can be the SSOT at target load, and neither
can enforce our state machine.** Working load: 1,000 runs/hr/project × ~10
board ops = 10,000 ops/hr, ~6,000 writes/hr, bursty.

- **GitHub breaks first on content creation, not primary limits**: the
  documented secondary limit is **500 content-generating requests/hour and
  80/minute per actor** — our write load is 12× over, and community
  evidence shows secondary limits use hidden buckets that can span tokens
  of one app or one IP, so app-per-project sharding is not guaranteed to
  multiply them. Sharding your SSOT against your vendor's abuse system is
  an adversarial posture.
- **Linear**: 2,500 req/hr per API key (5,000 per OAuth actor) — direct
  worker writes are ~2× over per actor with unpublished per-endpoint
  mutation caps as an untestable unknown (and the ~2× is on total ops —
  writes alone are ~1.2× over). Decisive independent of limits:
  `issueUpdate` accepts any `stateId` — **no transition-restriction feature
  and no compare-and-swap were found** (an absence-of-evidence finding: no
  docs, changelog, or schema surface for either, where competitors
  advertise theirs; no official "unsupported" statement exists), so the
  claim race is unclosable at Linear as far as can be established; and the audit log retains 90 days, disqualifying for the durable
  human-answer record. Webhooks: 3 retries (1 min/1 hr/6 hrs) then dropped,
  no ordering guarantee — a sync channel, not a correctness channel.
- **Prior art confirms the shape**: OpenAI Symphony (May 2026, Linear-based,
  exactly our problem class) keeps enforcement client-side and solves
  concurrency by mandating ONE serializing orchestrator — i.e. at
  multi-writer scale their "one authority" must become a real service. The
  Kubernetes API server (resourceVersion + 409 Conflict; legality enforced
  synchronously at one server, reconciliation only for convergence) is the
  working reference model.
- **Recommendation**: a small Postgres board service (~6 endpoints: claim /
  transition / comment / park / query / reconcile) where the legal-transition
  graph is a conditional UPDATE — `... WHERE id=$id AND state='ready-for-agent'`
  makes legality check + claim lock one atomic statement; rows-affected=0 IS
  the lost race. Load is ~3 TPS/project — ≥100× headroom on one node.
  Append-only history retained forever. Linear becomes the human-facing
  mirror (one-way coalesced sync — humans care about 2–3 of the ~10
  machine-tempo ops, shrinking tracker traffic 5–10×); human actions in
  Linear flow back as *events into* the board service, never as truth.
  Enforcement location thereby moves **server-side, into our service** —
  the frozen semantic layer stops depending on every client getting it
  right. (A new decision, not FD-2's resolution: FD-2's recorded open
  question — which invariants are schema-worthy vs per-repo policy — stays
  deferred on its original trigger.)
- **Coupling flag**: Linear's own GitHub PR automations (merged → Done)
  are a second uncoordinated writer that would fight tiered merge
  authority — disable per team.

### 7.2 Dispatch engine → Postgres-owned dispatch plane + resident reconcile controller; runner-up Temporal Cloud

**Scale framing that decides everything**: our envelope is ~0.3–6 run
*starts*/second — ~6M engine actions/day at the mid-band (5k runs/hr ×
~50 actions) and ~26M/day at the top (20k runs/hr) — below Cursor's 50M
actions/day, and 2–3 orders below Postgres-queue ceilings (River-class
~10k jobs/sec, per its author). Both "one Postgres owns it" and "Temporal
Cloud is affordable at mid-band" are true; the decision is discipline cost
and doctrine fit.

- **Recommendation**: claims via `FOR UPDATE SKIP LOCKED` + fencing tokens;
  **minutes-scale leases refreshed by session-log progress** (a JSONL
  append is a natural heartbeat — Anthropic's progress-as-liveness
  `reclaim_older_than_ms` pattern writ large); reclaim resumes from the
  durable log, never restarts; per-tenant admission fairness in SQL
  (Kueue's lowest-recent-usage-first semantics, trivial at 6 starts/sec);
  driven by a **resident level-triggered reconcile controller whose desired
  state is the board** (stateless, restart-cheap, HA-paired). Hatchet is
  the adopt-instead-of-build embodiment (MIT, Postgres substrate,
  SKIP LOCKED claims, fairness keys, community-reported 1B tasks/month).
- **Doctrine resolution**: "no resident orchestrator" is formally retired —
  but the *level-triggered reconcile* doctrine survives; only the batch
  cadence dies. The Postgres claim table is the one candidate where the
  engine *structurally cannot* become a second ticket-state authority:
  board mirror row and claim row commit in the same transaction.
- **Honest runner-up: Temporal Cloud, Cursor-shaped** (short task-scoped
  workflows, conversation state outside the workflow, replay-CI, native
  fairness keys — Temporal's own blog additionally claims OpenAI Codex and
  Replit Agent 3 as Temporal-based; vendor-claimed, not independently
  confirmed).
  Choose it if scale grows 10×+, or we refuse to own ~1–3k lines of
  lease/fairness code. It loses today on the permanent determinism/
  versioning tax and on doctrine risk (workflow state gravitationally
  attracts ticket state). **Self-hosted Temporal is eliminated on ops
  grounds, not dollars**: 4 services + Cassandra/ES, an irreversible
  day-one shard-count decision (one enterprise testimony: six months +
  full cluster migration), $2.5–4.5k/mo infra before labor. On money alone
  the comparison flips across the envelope: Temporal Cloud at ~$50/M
  actions is ~$9k/mo at mid-band but ~$26–39k/mo at the top (before
  volume discounts), where self-host infra-only is cheaper — the
  elimination rests on the shard trap, the determinism tax, and the
  headcount. Decision 2's revisit trigger must be recalibrated against
  the top-of-envelope Cloud bill, not the old mid-band figure.
- **Engine-independent finding**: every engine is at-least-once for side
  effects. The duplicate-git-push problem is solved in the **worker
  protocol**: one stable run-attempt key (workflowRunId+activityId pattern)
  stamped on branch names / PR bodies / board comments, check-then-act
  guards before push and PR-create (git is friendly: push is idempotent by
  SHA, PR-create dedupes by branch name).
- **Behavioral finding**: Cursor's OCC-bred risk-aversion belongs to
  agent-vs-agent shared state, not engine leases. Constraint on us: the
  agent must experience **unconditional exclusive ticket ownership** (which
  the semantic layer already guarantees); leases are infrastructure's
  concern and must never surface as optimistic shared-state writes to the
  agent.

### 7.3 Sandbox substrate → k8s + gVisor per-run pods on local NVMe; snapshots are disk artifacts, not memory images

**Verdict: the millisecond snapshot-restore arms race is irrelevant at our
run lengths, and disk I/O density is the real constraint.**

- **Skip Firecracker memory snapshots**: 4–28 ms restores are real, but the
  project's own docs list replicated RNG/entropy pools, wrong wall-clock,
  and unpreserved TCP state on resume — Fly.io hit all three in production
  (30 s+ resumes, JWT/cron breakage, snapshots discarded on every deploy).
  Against minutes-to-hours runs, a 5-second fresh gVisor start is 0.3%
  overhead with none of those bugs. CRIU: 30–60 s class at multi-GB —
  rejected for fan-out.
- **Recommended isolation**: gVisor `RuntimeClass` pods, one per run, warm
  pools — the **GKE Agent Sandbox shape** (SandboxTemplate → SandboxWarmPool
  → SandboxClaim, gVisor mandatory, sub-second warm claims; adopt the
  product itself if the org lands on GCP). Threat model honesty (NVIDIA
  guidance, Microsoft's prompt-injection RCE work, Anthropic's own
  bubblewrap+egress-proxy sandbox-runtime): the mandatory controls for a
  prompt-injected internal agent are **egress deny-by-default + scoped
  per-run credentials + workspace-scoped writes** — blast-radius controls,
  not hypervisors. gVisor buys kernel-surface reduction at <3% typical
  overhead (10–30% worst-case on syscall-heavy builds); Kata/microVMs only
  for repo classes with a hard separate-kernel compliance mandate.
- **Warm state is a disk problem**: pinned toolchain image (SOCI-indexed if
  large: 2.5 GB pulls in ~2.8 s) → **post-install workspace snapshot as a
  content-addressed disk artifact on a node-local NVMe cache** (Blacksmith
  pattern), backfilled from object storage → overlayfs clone per run.
  Network storage fails the economics: 2 TB io2 EBS at 64k IOPS ≈
  $3,850/month vs a 2 TB NVMe doing >1M IOPS for <$200 once.
- **Capacity math**: ~100 runs/host RAM-packed (2 vCPU / 8 GB midpoint; CPU
  oversubscribes 2–4× since agents idle on tokens), density held real only
  by NVMe (build bursts ≈ 10–17 GB/s/host at ⅓ duty cycle — matches
  Cursor's "many GB/s" ceiling). **~80–110 runs/host RAM-packed; with
  ~30% headroom, 1,000 concurrent runs ≈ 15–20 large NVMe hosts.** A
  small, boring fleet — but 1,000 concurrent is one named point on a
  curve: **concurrency = start rate × mean run duration**, and at the
  dispatch envelope's top (6 starts/sec) with hour-long runs concurrency
  reaches ~20,000, scaling the fleet linearly. The spec must size fleet
  and cost at named (start-rate, duration) points, never conflating
  per-hour throughput with concurrency. Validate per-host density with a
  one-host load test before committing fleet sizing.
- **SaaS sandboxes rejected as substrate**: ~$73k/mo (E2B/Daytona rates)
  to ~$104k/mo (Modal — billed per physical core ≈ 2 vCPU, so ~1.4× the
  others, not 3×) at 1,000 sustained concurrent runs vs ~$5–15k/mo
  self-hosted bare metal. Daytona and Northflank also offer
  self-host/BYOC; E2B is the only one with an open self-host infra stack —
  and it requires a Nomad/Consul/KVM estate anyway.
- **Drift (round-1's #1 open question) — solved by construction, not
  detection**: snapshot key = hash(env-spec) ⊕ hash(lockfiles) ⊕
  toolchain-image digest. Exact hit → restore + run the certification
  commands as a smoke probe (the certification gate doubles as the drift
  detector for free); any miss → rebuild through the certification gate;
  TTL/GC 30–90 idle days as the backstop for non-hermetic inputs (mutable
  registries). Nobody credible patches stale environments — DevPod keys
  prebuilds by config hash; Fly invalidates on deploy.

### 7.4 Review & merge at scale → change-class auto-land, TAP/SubmitQueue-style queue, verifier as named infrastructure

- **Merge-queue capacity is a hard published hierarchy**: bors serial
  ~10/day → GitLab trains 20 parallel → GitHub merge queue ≤100 concurrency
  with drop-and-rebuild-behind-failure semantics (degrades sharply as
  failure rate rises — and agent PRs fail CI more than human PRs) →
  Shopify ~400/day with a predictive branch → **Google TAP >50,000/day
  (~2,000/hr) — the only published system at our target rate — achieved
  only by abandoning per-change verification for batching + automatic
  bisection of failing batches (~11-min average submit wait)**. The proven
  per-change-verifying alternative: Uber SubmitQueue (EuroSys 2019) —
  speculation trees + a 97%-accurate pass-predictor + build-target
  independence analysis; 1.2× oracle turnaround; mainline green 52%→100%.
  Planning number: **at just 16 concurrent changes in flight, conflict
  probability ≈ 40%** — neutral merge-resolver agents are steady-state,
  not an edge case.
- **Auto-land is precedented ONLY as a change-class whitelist, never a size
  heuristic**: Google Rosie auto-approves pattern-conforming LSC shards;
  Renovate automerges by dependency class + merge-confidence + 3-day age;
  Meta TestGen-LLM lands only build + pass-repeatedly + coverage-up changes
  (73% human acceptance of guardrail-passing output). Define our auto-land
  tier as **a whitelist of machine-verifiable change classes with per-class
  guardrail chains**; unclassifiable ⇒ not auto-landable. Never reduce
  pre-merge depth for schema/data/security/config changes regardless of
  size; reduce it only where failure is fast-detectable and cheaply
  revertible behind canary.
- **The verifier stage is what makes review scale**: Cursor Bugbot evolved
  from 8-pass majority voting to ONE aggressive finder + a validator stage
  (>2M PRs/month; published resolution rate 52% → "over 70%"); Anthropic's
  internal Code Review converged on the same shape (parallel hunters →
  verification filter → severity ranking; vendor-reported <1% findings
  marked incorrect; explicitly never auto-approves). Lens-stacking ROI is
  real but **conditional on the downstream verifier** (the causal reading —
  the validator is what makes aggressive finding affordable — is our
  inference from Cursor's published evolution, supported by Anthropic's
  independently converged shape); budget it as a distinct component with
  its own false-escalation SLO (HackerOne's 2026 pause = the DoS failure
  mode).
- **Human tier survives dozens of escalations/day if all four hold**
  (published practice): small units (PRs <200 lines approve ~3× faster —
  vendor marketing analysis of 1.5M PRs, methodology unpublished),
  pre-verified severity-ranked escalations, a dedicated approver rotation
  (Google's global-approver analog) routed by ownership, and a
  first-response SLO (Google: 1-business-day max, <1 h median).
- **Semantic-layer flags raised to §4 (items 7–10)**: no public precedent
  for human-free general auto-land; batch-vs-per-change verification
  reading; verifier as named load-bearing component; post-land canary as
  de-facto fourth tier (auto-land-under-watch option).

## 8. Decision agenda for the design spec

Questions the spec must settle (research done; these are now design
choices, most with a research-backed default):

1. **Board service shape** — the ~6-endpoint Postgres service + Linear
   mirror (default per §7.1); or the Linear-as-SSOT fallback (2–3 OAuth
   actors + support-negotiated limits + accepted claim races) if the org
   refuses to run any service. Must also settle the service's own HA/DR/
   backup posture (it holds the permanent append-only history) and
   fail-closed worker behavior when the board is unreachable.
2. **Build vs adopt the dispatch plane** — own ~1–3k lines
   (SKIP LOCKED + leases + fairness) vs adopt Hatchet vs Temporal Cloud
   (default: Postgres-owned per §7.2). **Coupled to decision 1**: §7.2's
   strongest doctrinal guarantee — board mirror row and claim row commit
   in one transaction, so the engine structurally cannot fork ticket
   authority — exists ONLY if decisions 1 and 2 land on the same Postgres;
   Hatchet's own schema, Temporal Cloud, and the Linear-as-SSOT fallback
   each break it. That coupling is the real tiebreaker between the
   options. Temporal Cloud revisit trigger: sustained growth toward the
   envelope's top — where its bill also grows to ~$26–39k/mo (§7.2).
3. **Merge-queue mechanism per repo class** — batch+bisect (TAP) vs
   speculation+independence (SubmitQueue) vs hosted GitHub queue for
   low-rate repos; ties to semantic flag §4.8 (human decides the
   verification reading).
4. **Auto-land change-class whitelist v1** — which classes, which guardrail
   chains, and whether auto-land-under-watch (canary-conditional landing,
   flag §4.10) enters the authority model.
5. **Isolation tier mapping** — gVisor default; which repo classes (if any)
   mandate Kata/separate-kernel; egress allowlist policy per team.
6. **Park-queue SLOs** — routing, batching, notification channels,
   first-response targets (no prior art; ours to invent, informed by
   Google's review-SLO numbers).
7. **Worker idempotency protocol** — run-attempt key derivation, stamped
   surfaces (branch/PR/board), check-then-act guard list (engine-independent,
   must be in the worker contract).
8. **Session-store technology** — the only one of the three SSOT planes
   with NO research track behind it: design it in the spec from first
   principles or run a small follow-up track. Options: object store +
   streaming tail (Cursor's S3+Redis shape) vs a simpler Postgres-backed
   event log at our volume. Coupled to decision 2: the lease heartbeat is
   "session-log progress," so the dispatch plane needs visibility into
   session-store appends. Plus prompt-cache economics of resume
   (unquantified anywhere — measure).
9. **Multi-repo atomic changes** — cross-repo ticket scope vs per-repo PRs
   with a coordinating parent ticket (silent in all sources; semantic-layer
   adjacent, needs the human).
10. **Field Guide / stigmergy adoption** — per-repo agent-curated index
    with line budget: adopt now or defer to a later phase.
11. **Code-host load plan (the PR plane)** — the arithmetic that
    disqualified GitHub-as-board applies to the PR plane too: PR creation,
    review comments, and verdict comments are content-generating requests
    under the same 500/hr-per-actor secondary limit — plausibly ~8–14×
    over at target rate per project. Decision 3 presumes GitHub-hosted
    PRs; the spec must run the same load math for the code host and pick
    mitigations explicitly (GHES with configurable limits,
    per-installation actor sharding, verdict/comment traffic moved onto
    the board service, batched review submission) rather than assume them.
12. **Aggregate ops-burden budget** — each build-vs-adopt verdict is
    individually reasonable, but together the platform team owns: board
    service + Linear mirror sync, dispatch plane + reconcile controller,
    k8s/gVisor NVMe fleet, environment registry + certification pipeline,
    session store, vault/egress proxy, contention telemetry, merge queue.
    One explicit ownership-budget line item, since it silently shapes
    every build-vs-adopt call above.
13. **Token-spend Fermi at envelope** — the research priced infra
    (~$5–15k/mo self-hosted) but never the model bill; at thousands of
    runs/hour token spend plausibly exceeds infra by 10–100×, which
    reframes every cost-based substrate argument. Include provider
    rate-limit/quota architecture at that token tempo as a first-class
    design input.
