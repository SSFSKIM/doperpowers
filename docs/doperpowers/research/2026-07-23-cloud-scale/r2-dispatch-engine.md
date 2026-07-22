# R2 — Dispatch engine: what should own dispatch, retries, leases, and run ownership at 10²–10³ agent runs/hour

Research round 2. Question: at hundreds–thousands of implementer+reviewer runs per hour per project
(multi-project, multi-host), what should own dispatch, retries, leases, and run ownership — and what
does each candidate actually cost to operate? All claims below cite primary or near-primary sources;
confidence notes in §4.

**Scale framing used throughout.** "Hundreds to thousands of runs/hour/project," several projects →
call it 1k–20k run *starts*/hour system-wide, i.e. **0.3–6 starts/second**, runs lasting minutes to
hours, each run internally making dozens–hundreds of model/tool steps. If every internal step were an
engine-tracked action at, say, 5k runs/hour × 50 actions, that is ~6M actions/day — **roughly 10× below
Cursor's 50M actions/day** and 2–3 orders below where Temporal's Cassandra tier is needed. This matters:
we are in the range where a single Postgres can own the whole dispatch plane, *and* in the range where
Temporal Cloud is affordable. Both doors are open; the decision is about discipline cost and doctrine
fit, not raw throughput.

---

## 1. Findings per question

### Q1 — Self-hosted Temporal at enterprise scale

**What self-hosting actually requires.** Temporal server is four independently-scaled services
(frontend, history, matching, worker) plus a persistence DB (Postgres/MySQL for smaller, Cassandra
recommended at scale) plus Elasticsearch for visibility. Temporal's own scaling guide and third-party
operators agree the labor is real: "It can be labor-intensive to scale the Temporal Service for a
high-throughput use case, as you must scale your database … and manage four additional independent
services" (Temporal, "Scaling Temporal: The basics"; Vymo Engineering load-testing writeup).

**The shard-count trap is the signature failure mode.** History shard count is fixed at cluster
creation and cannot be changed without a **full cluster migration**. Xgrid's enterprise engagement
report: one engagement "followed six months of effort spent resolving shard limitations, ultimately
requiring a full cluster migration to scale." Their sizing guidance: 512 shards for moderate load,
2048–4096 for millions of executions/day. Under-provision and you migrate; over-provision and you pay
constant DB overhead. (xgrid.co success story, and Temporal's scaling-basics blog.)

**Ops-burden testimony.** Multiple self-hosting testimonies (Zachary McDonnell "My Journey Self
Hosting a Temporal Cluster"; Naman Gupta "Temporal Burned Me in Production," Jun 2026; Automation
Atlas cost guide 2026) converge on: Cassandra needs local-SSD nodes ("rotational storage becomes the
bottleneck fast"), monitoring of shard-level metrics is mandatory, and a small production-grade
self-host lands around **$2,500–4,500/month infrastructure before labor**. The Automation Atlas
guide's conclusion: managed cloud "consistently proving to be the operationally sound choice except in
environments with strict on-premises compliance requirements."

**The versioning/replay discipline is a permanent tax, not a setup cost.** Workflow code must be
deterministic against recorded history; any change that alters the command sequence of an in-flight
workflow throws non-determinism errors on replay. Temporal's own docs: "If you make a change to your
Workflow code that would cause non-deterministic behavior on Replay, you'll need to use one of our
Versioning methods." Patching "requires you to maintain both code paths until all old Workflows
complete." Practitioner testimony (Nexumo, "Temporal Replay Bugs Hide in Plain Sight"): "the workflow
starts fine, sleeps fine, waits fine, and then explodes later when a worker replays history against
code that now behaves just a little differently." Mitigations that work: replay-testing production
histories in CI (Temporal's recommended practice; Cursor does exactly this per round-1) and Worker
Versioning pinning deployments (Temporal blog, "Safe deployments with Temporal Worker Versioning on
Kubernetes"). Two structural mitigations cut the tax dramatically for agent workloads: **short
task-scoped workflows** (old code paths drain in hours, not months — Cursor moved from "eternal"
workflows to "multiple shorter ones that exit after completing a single task") and **keeping
conversation state outside the workflow** (Cursor: "We built an efficient append-only storage
mechanism that streams conversation updates out to web and desktop clients"), which keeps workflow
code a thin, slowly-changing shell.

**License and pricing.** Self-host is MIT-licensed, free. Temporal Cloud (2026 plans): Essentials
$100/mo (1M actions incl.), Business $500/mo (2.5M actions incl.), then **~$50 per million actions**
with volume discounts from 5M actions (docs.temporal.io/cloud/pricing). At our envelope's high end
(~6M actions/day ≈ 180M/month) that's list-price ≈ $9k/mo before discounts; at the mid envelope
(~1–2M/day) it's ~$1.5–3k/mo — comparable to or below the *infrastructure-only* cost of self-hosting,
before counting platform-engineer time. Self-hosting only wins on compliance/on-prem grounds at our
scale, not on money.

**Who runs agent fleets on Temporal.** Besides Cursor (50M actions/day, >7M workflows/day, "past two
9s" — cursor.com/blog/cloud-agent-lessons, June 2026): **OpenAI Codex** — "OpenAI's Codex web agent is
built on Temporal … handling millions of requests" — and **Replit Agent 3** — "Replit's new
long-running Agent 3" is built on Temporal (Temporal blog, "Of course you can build dynamic AI agents
with Temporal"). InfoQ (Sept 2025) also covers Temporal's OpenAI Agents SDK integration. So the three
most visible cloud coding-agent products all converged on Temporal — strong prior art, with the caveat
that all three are external-facing products at 10²–10³× our scale.

### Q2 — Alternatives, honestly compared at our scale

**(a) Queue + reconcile-controller (SQS/PubSub or Postgres queue + level-triggered controller over
declared state).** This is the Kubernetes-controller doctrine applied to our board: desired state
(board tickets in ready/in-progress/in-review) vs observed state (running workers), a loop that
"always asks 'is the world in the state I want?' and drives toward that state" — level-triggered, so
missed events don't matter (OneUptime reconciliation-loop writeup; kubebuilder/operator literature).
It is philosophically identical to our cron-sweep, upgraded from batch-cadence to resident-loop
cadence. Claim semantics must be built or borrowed:
  - **SQS**: visibility timeout capped at **12 hours** (AWS docs) — covers minutes-to-hours runs only
    via the heartbeat pattern (ChangeMessageVisibility extensions; AWS-recommended, tecRacer/AWS
    builders writeups). At-least-once; FIFO groups give ordering, not fairness; per-tenant fairness is
    DIY (one queue per tenant + weighted polling).
  - **Postgres queue (River/Oban-class)**: `FOR UPDATE SKIP LOCKED` claim, lease/attempt fencing
    ("a worker claims a job … the claim increments run_lease, which guards completion so stale workers
    cannot finish a newer attempt" — hardbyte's PG-queue benchmarking notes), transactional enqueue
    (job row commits atomically with your own tables — the cleanest possible answer to "engine must
    not become a second authority": the claim row and the board mirror live in the same transaction).
    Proven headroom: Oban community reports 10M+ jobs/day patterns; River-class engines benchmark at
    ~14k jobs/sec — 3 orders above our start rate. At-least-once; fairness and priority are DIY but
    cheap at 6 starts/sec (per-tenant token buckets in SQL).
  - Operational footprint: the controller is one stateless process (run 2 for HA with leader
    election); the queue is either a managed service (SQS) or the Postgres you already run. **This is
    the smallest-footprint option that still fixes lease reclaim and fairness.** What you give up:
    per-step retry bookkeeping inside a run (the run process owns its own step retries), and you write
    ~1–3k lines of controller/lease/fairness code that Temporal/Hatchet give you off the shelf.

**(b) k8s Jobs / CRD controller alone.** Kubernetes Jobs as the dispatch unit hits control-plane
limits well below our ceiling if runs are short: "etcd and the Kubernetes scheduler can stall out
before hitting 5,000 jobs when running through a queue of jobs" (kubernetes/kubernetes #95492,
"Kubernetes won't run 50,000 Jobs"); completed-Job bloat pressures etcd (mitigate with
`ttlSecondsAfterFinished`). At 5k runs/hour × minutes-to-hours runtimes, live-object counts (~10³–10⁴)
are workable but near the discomfort zone, and etcd is now your dispatch database — a worse queue than
Postgres. **Kueue** adds the missing multi-tenant layer (see Q3) but still leaves run-level retry
semantics to `backoffLimit` (blunt: whole-pod re-run, no lease nuance). Verdict: fine as the *compute*
substrate under any of the other options; weak as the *ownership* layer by itself.

**(c) Lighter durable-execution engines.**
  - **Hatchet** (MIT, Go): "orchestration engine for background tasks, AI agents, and durable
    workflows"; Postgres is the durability layer for both runtime and observability; claim via
    `FOR UPDATE SKIP LOCKED`; ships concurrency keys with round-robin fairness strategies, rate
    limits, priority, DAGs, a real UI/metrics/alerting layer. Community-reported "PostgreSQL handled
    1B tasks/month with proper tuning." Self-host = Postgres + engine + dashboard (docker-compose
    grade; older versions also carried RabbitMQ). Positioning per ZenML's comparison: "Temporal-style
    durable execution … without the operational footprint of a full Temporal cluster."
  - **Restate**: single self-contained Rust binary ("run several instances for HA, snapshot to object
    storage … no separate database, no search engine to operate" — restate.dev). Lowest-ops durable
    engine, but it wants to own service invocation (you re-architect handlers around its dispatch),
    and it is the youngest of the set.
  - **DBOS**: durable execution as a *library* checkpointing to your Postgres — "install the library
    and annotate workflows and steps"; minimum possible footprint, but couples durability to the app
    process and is per-language.
  - **Inngest**: no workers at all — it invokes your functions over HTTP (inngest.com/compare-to-
    temporal). Wrong shape for hours-long CLI processes on our own hosts.
  - All of these are at-least-once engines like Temporal (exactly-once *recording*, at-least-once
    *side effects* — see Q4). None has Temporal's replay-determinism tax in the same degree (Hatchet/
    queue models don't replay your code against history; DBOS checkpoints step results).

**(d) Nomad.** Single-binary scheduler, no external data store, proven to 10k+ nodes and the 2020
"2-million-container" challenge; deploys in minutes (HashiCorp docs; comparison literature). But it
answers "place and supervise processes," not "own retries/leases/fairness of run state" — you would
still build (a) on top. Also note license: Nomad moved to BSL in 2023 (non-OSI), a real consideration
for an internal-platform bet. Verdict: a compute substrate candidate competing with k8s, not a
dispatch-ownership candidate.

### Q3 — Admission control and fairness across projects/teams

Two mature, directly-usable bodies of prior art:

- **Kueue** (k8s-native job queueing): ClusterQueues hold cluster-wide quota policy; namespaced
  LocalQueues per team feed them; **Admission Fair Sharing** "carefully orders waiting jobs based on
  the already consumed resources, always favoring the queue with the lowest historical usage" —
  explicitly built to stop time-based and volume-based starvation of small tenants by big ones
  (kueue.sigs.k8s.io fair-sharing docs; Kubernetes blog "Introducing Kueue"). Borrowing terms even
  without k8s: quota at admission time, usage-history-weighted ordering, cohort borrowing with
  preemption.
- **Temporal Task Queue Priority and Fairness** (GA'd 2025): within a priority tier "each fairness
  key is a virtual queue. Keys are dispatched proportional to their weights — a key with weight 2.0
  is dispatched twice as often as one with weight 1.0"; tenant IDs as fairness keys; "supports
  millions of fairness keys"; priority separates urgent from batch, fairness prevents tenant
  domination within a tier (docs.temporal.io/develop/task-queue-priority-fairness; Temporal blog).
  This is weighted fair queuing productized — and it means Temporal now answers our Q3 natively,
  which older Temporal evaluations (pre-2025) could not claim.

For minutes-to-hours jobs specifically, the literature's consistent shape is: **fairness belongs at
admission (which run starts next), quotas belong at concurrency (how many run at once per tenant),
and preemption of long-running work is a last resort** — Kueue does admission-time ordering + quota
+ optional preemption; Temporal does dispatch-time WFQ + per-key rate limits. A DIY Postgres
controller can implement the same two knobs (per-tenant concurrency cap + pick-next = lowest
recent-usage tenant first) in a few hundred lines; the hard part — defining weights/quotas per team —
is policy, not code, under every candidate.

### Q4 — Idempotency/retry semantics for agent runs (the double-execution problem)

The engines are unanimous and explicit that **they do not solve this; they scope it**:

- Temporal activity docs/blog: "Temporal Activities provide an 'at-least-once' execution guarantee,
  and your idempotent Activity implementation provides the 'no-more-than-once' business effect.
  Together … an effective 'exactly-once' execution." The canonical failure: "If a Worker executes an
  Activity successfully but crashes before notifying the Temporal Service, the Activity will be
  retried." That is precisely our "git push landed but event not recorded" case.
- Published patterns (Temporal "What is idempotency?" blog; error-handling guide; practitioner
  posts):
  1. **Deterministic idempotency key** derived from engine identity: "you can use
     `workflowRunId + '-' + activityId`" — generate once in workflow state, pass into every retry.
  2. **Check-then-act wrapper** for non-idempotent externals: "Wrap the non-idempotent operation in a
     function that … verif[ies] it succeeded with a read operation" — for us: before `git push`,
     check whether the remote ref already contains the commit SHA; before opening a PR, query for an
     existing PR with the run's marker.
  3. **At-most-once opt-out**: set max attempts = 1 and use a compensating step for things that must
     never double-fire.
- Agent-specific framing (buildmvpfast "Idempotent AI Agents," 2026, and Cursor's blog): split the
  loop so **pure inference steps are freely retryable and side-effecting steps are separated,
  keyed, and individually guarded**. Cursor's client-visible version of the same idea: the
  append-only conversation layer "accounts for retries, so that if a step of the agent loop fails
  after streaming partial output and then gets retried, the client can detect this, rewind its
  stream, and show the new data instead of the old."

**Consequence for us (engine-independent):** the fix lives in the worker protocol, not the engine
choice. Git is actually a friendly side-effect surface — push is idempotent by SHA, PR-create is
dedupable by branch name — provided every run derives **one stable run-attempt key** and stamps it on
branch names, PR bodies, and board comments. Every candidate engine gives at-least-once; none gives
more; the decision table therefore does not differentiate on this axis.

### Q5 — Claim semantics and agent behavior

- **Cursor's risk-aversion finding is real but belongs to agent-vs-agent coordination, not
  engine-vs-agent leases.** Source: cursor.com/blog/scaling-agents ("Scaling long-running autonomous
  coding" — the 100+ concurrent-agent experiment). Verbatim: with locks, "Agents would hold locks for
  too long, or forget to release them entirely… Twenty agents would slow down to the effective
  throughput of two or three." After switching to optimistic concurrency (reads free, writes fail if
  state changed): "With no hierarchy, agents became risk-averse. They avoided difficult tasks and
  made small, safe changes instead. No agent took responsibility for hard problems or end-to-end
  implementation." Their fix was **structural, not mechanical**: a planner/worker pipeline with
  exclusive task ownership ("Workers pick up tasks and focus entirely on completing them"). Lesson
  for us: keep *exclusive-claim* semantics at the ticket level (one worker owns one ticket — which
  our board already does) and never make agents themselves negotiate shared mutable state
  optimistically. The lease is infrastructure's concern; the agent should experience unconditional
  ownership.
- **Anthropic Managed Agents self-hosted sandboxes** (platform.claude.com docs, fetched): the
  `self_hosted` environment "acts as a work queue… Your worker claims work items from that queue."
  Claim by polling (always-on or webhook-woken); `reclaim_older_than_ms` "re-claims items leased to a
  dead worker" — their webhook example uses **`reclaim_older_than_ms=2000`** with `drain=True`,
  i.e. lease-expiry two seconds after last activity, safe because posting tool results continually
  refreshes liveness. Clean shutdown releases explicitly: the CLI worker "cancels any in-flight tool
  call, posts its error result, and releases the work item before stopping." Pattern: **short lease,
  refreshed by progress (results posted), plus explicit release** — progress-as-heartbeat rather
  than a separate liveness channel.
- **Heartbeat vs lease-length prior art**: SQS caps visibility at 12h and AWS's recommended pattern
  for long work is heartbeat-extension, not long leases (AWS docs; tecRacer). Temporal is explicit
  about why: "If you have a two-hour Activity and it hangs after five minutes, you'd wait nearly two
  hours to find out" without heartbeats — hence "for long-running Activities … a relatively short
  Heartbeat Timeout and a frequent Heartbeat" (docs.temporal.io detecting-activity-failures).
  River-style fencing adds the complementary guard: increment an attempt/lease token on claim so a
  zombie from a previous lease cannot complete a newer attempt.
- Synthesis for agent runs (minutes–hours): **never size the lease to the run**. Lease ≈ minutes,
  renewed by observable progress (a session-log append is a natural heartbeat — our JSONL logs
  already emit progress at every step), reclaim = lease expiry + fencing token, and resume from the
  durable session log rather than restarting the run. Our existing "durable log is the identity of
  the work" doctrine composes perfectly with short-lease/fenced-claim semantics.

---

## 2. Decision table

Requirements: (R1) durable run ownership — a run survives host/process death and is resumable;
(R2) lease reclaim — dead workers' runs are reclaimed in seconds–minutes with zombie fencing;
(R3) fairness — per-team/project admission weights + concurrency quotas, no starvation;
(R4) ops burden tolerable for an internal platform team (not a product-infra org);
(R5) doctrine fit — board stays ticket SSOT; engine owns *run execution* only and must not become a
second ticket-state authority.

| Candidate | R1 run ownership | R2 lease reclaim | R3 fairness | R4 ops burden | R5 doctrine fit |
|---|---|---|---|---|---|
| **Temporal self-hosted** | Excellent (per-step history, heartbeats, retries) | Excellent (heartbeat timeout + retry policy) | Excellent — native fairness keys/weights (2025) | **Worst in table**: 4 services + Cassandra/PG + ES; irreversible shard count (6-month migration testimony); $2.5–4.5k/mo infra + real headcount; permanent determinism/versioning tax | OK *if* workflows are task-scoped runs (Cursor pattern); constant temptation to leak ticket state into workflow state |
| **Temporal Cloud** | Same as above | Same | Same (native) | Low-moderate: no cluster ops; still worker-fleet ops + versioning/replay-CI discipline; ~$50/M actions → ~$1.5–9k/mo across our envelope | Same as above; per-action pricing actively rewards keeping the agent loop's chatty steps *outside* the engine |
| **Hatchet (self-hosted)** | Good (durable tasks, checkpointed steps, retention-limited history) | Good (lease via SKIP LOCKED + retries/timeouts) | Good — concurrency keys w/ round-robin fairness, rate limits, priority | Low: Postgres + engine + dashboard; single-team operable; younger project, UI/engine version churn | Good: it is a task engine, not a state machine for tickets; Postgres substrate can share transactions with a board mirror |
| **Restate** | Good (journaled invocations, single binary) | Good | Partial (no WFQ-grade multi-tenant story yet) | Lowest of the durable engines (one binary + object storage) | Moderate: wants to own service dispatch; youngest, smallest ecosystem |
| **DBOS** | Good within one app/language (library + your Postgres) | Moderate | DIY | Very low footprint, but couples durability into worker process; awkward for polyglot CLI-process workers | Good (your Postgres, your transactions) |
| **SQS/PubSub + reconcile controller** | Partial — queue owns *pending* work only; running-run ownership is the controller's job | Moderate: visibility-timeout heartbeats, 12h cap; fencing DIY | DIY (per-tenant queues + weighted poll) | Low (managed queue + 1 stateless controller) | **Best-in-class philosophy fit** (level-triggered reconcile over declared board state) but state split across queue+DB |
| **Postgres queue (River/Oban-class) + reconcile controller** | Good: claim rows + attempt fencing + our durable JSONL sessions carry the run | Good: short leases, progress-refreshed, `run_lease` fencing, SKIP LOCKED reclaim | DIY but cheap at 6 starts/sec (per-tenant caps + lowest-recent-usage pick-next; Kueue semantics in ~10² lines of SQL) | Low: one Postgres (likely already present) + 1–2 controller processes; ~1–3k lines owned code | **Best**: single transactional store; board-mirror row and claim row commit atomically; engine structurally *cannot* fork ticket authority |
| **k8s Jobs (+Kueue) alone** | Weak (backoffLimit re-runs, no step nuance) | Weak-moderate | Excellent via Kueue (admission fair sharing, quotas) | Moderate if k8s already run; etcd is a bad queue (stalls "before 5,000 jobs" in queue-through patterns) | Moderate — Job objects become a shadow run-state authority in etcd |
| **Nomad** | Not its job (placement/supervision only) | Not its job | Partial (scheduler-level) | Very low (single binary; 2M-container challenge 2020) — but BSL license | N/A as ownership layer; compute-substrate candidate only |

---

## 3. Recommendation

**Recommendation: a Postgres-owned dispatch plane — claim/lease/fairness in one Postgres (River/
Oban-class semantics, or Hatchet if we'd rather adopt than build) — driven by a resident
level-triggered reconcile controller whose desired state is the board.**

Concretely: the board (ticket SSOT) mirrors into Postgres rows; a controller loop continuously
computes "tickets that should have a run but don't" and admits them under per-tenant concurrency caps
with lowest-recent-usage-first ordering (Kueue's admission-fair-sharing semantics, reimplemented at
our 0.3–6 starts/sec where they are trivial); workers claim via `SKIP LOCKED` with a fencing token
and a **minutes-scale lease refreshed by session-log progress** (Anthropic's progress-as-liveness
pattern, `reclaim_older_than_ms` writ large); reclaim resumes the run from the durable JSONL, it does
not restart it. Every side-effecting step carries a run-attempt key (workflow-run-id+activity-id
pattern) with check-then-act guards on push/PR-create.

Why this over Temporal, despite Cursor/OpenAI/Replit all converging on Temporal: (1) our unit of
durability is already the session log — the per-step replayable history Temporal sells is largely
redundant with a doctrine we've already proven, whereas its determinism/versioning tax on
fast-evolving agent-loop code is not redundant, it's new; (2) we are 1–3 orders of magnitude below
the scale that forced Cursor off a loop-on-VM design, and their one-nine failure mode (mid-run
compute death losing the run) is answered by lease-reclaim + resume-from-log, which is exactly the
part we're adding; (3) doctrine: a transactional Postgres claim table is the only candidate where the
engine *structurally cannot* become a second ticket-state authority, because the board mirror and the
claim commit in one transaction. The one principle we must explicitly retire is "no resident
orchestrator": at thousands of runs/hour with seconds-scale reclaim and admission ordering, the cron
sweep must become a resident (but stateless, restart-cheap, HA-paired) controller. The level-triggered
reconcile doctrine survives; the batch cadence does not.

**Honest runner-up: Temporal Cloud (not self-hosted), Cursor-shaped** — short task-scoped workflows
per run/turn, signal-with-start for continuity, conversation state outside the workflow, replay tests
in CI, native fairness keys per team. Choose it instead if any of these hold: we expect 10×+ scale
growth (their 2025 fairness feature + heartbeat machinery + three flagship agent fleets are exactly
our requirements off the shelf); we don't want to own ~1–3k lines of lease/fairness code and its
3am pages; or multi-region/DR requirements arrive early. It loses today only on the determinism-
discipline tax and on doctrine risk (workflow state gravitationally attracts ticket state). **Self-
hosted Temporal is not a serious option at our scale**: it combines the highest ops burden in the
table with a cost profile ($2.5–4.5k/mo + headcount) that exceeds Temporal Cloud's bill for the same
envelope, and adds an irreversible shard-sizing decision on day one.

If a later round chooses k8s as the compute substrate, Kueue slots in as the quota/admission layer
under this same controller without changing the recommendation; Nomad remains a viable minimal-ops
substrate but its BSL license and non-ownership of run state keep it out of the dispatch-plane
decision.

**Semantic-layer flag check:** nothing found forces a semantic-layer change. Fairness/admission
control is purely substrate. One near-miss worth naming: Cursor's risk-aversion evidence implies the
*claim regime the agent experiences* must remain exclusive-ownership (one worker, one ticket,
unconditional), which our semantic layer already guarantees — the finding constrains the substrate to
preserve it (no optimistic shared-state writes exposed to agents), not to change it.

---

## 4. Confidence notes

- **High confidence**: Cursor migration facts and quotes (primary blog, fetched directly, June 2026);
  Cursor risk-aversion quotes (primary blog "Scaling long-running autonomous coding," fetched);
  Anthropic work-queue semantics incl. `reclaim_older_than_ms=2000` example (primary docs, fetched);
  Temporal at-least-once/idempotency-key guidance (primary docs/blog, fetched); Temporal fairness-key
  mechanics (primary docs); Temporal Cloud list pricing (primary docs); SQS 12h cap + heartbeat
  pattern (AWS docs); Kueue admission fair sharing (SIG docs); k8s ~5k-job queue stall
  (kubernetes/kubernetes #95492); Hatchet SKIP LOCKED/Postgres architecture (repo + author posts).
- **Medium confidence**: OpenAI Codex and Replit Agent 3 on Temporal — vendor's own blog (Temporal),
  not OpenAI/Replit primary posts; directionally corroborated by InfoQ. Xgrid's "six months / full
  cluster migration" shard testimony — consultancy success-story, single source. Self-host cost band
  $2.5–4.5k/mo — one 2026 cost guide, plausible but not independently triangulated. Hatchet "1B
  tasks/month" — community-reported, not audited. Temporal license reported as MIT by multiple
  secondary sources (historically server was MIT with some ee components separate) — verify LICENSE
  file before a bet relies on it.
- **Judgment, not sourced fact**: the actions/day envelope math (§ framing); the claim that per-step
  replay is "largely redundant" given our JSONL doctrine — this is an inference from our own design
  history plus Cursor's storage-outside-workflow choice, and is the load-bearing joint of the
  recommendation; if implementer runs turn out to need engine-visible per-step retry telemetry
  (e.g. for the review-side audit trail), the balance tilts toward Temporal Cloud.
- **Known gap**: no published head-to-head reliability data for Hatchet/Restate/DBOS at multi-month
  production scale comparable to the Temporal testimonies; their columns rest on architecture docs
  and benchmarks more than scar tissue.

---

## 5. Sources

Primary (fetched directly this session):
- Cursor, "What we've learned building cloud agents" — https://cursor.com/blog/cloud-agent-lessons
- Cursor, "Scaling long-running autonomous coding" — https://cursor.com/blog/scaling-agents
- Anthropic, "Self-hosted sandboxes" (Managed Agents) — https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes
- Temporal, "Of course you can build dynamic AI agents with Temporal" — https://temporal.io/blog/of-course-you-can-build-dynamic-ai-agents-with-temporal
- Temporal, "What is idempotency?" — https://temporal.io/blog/idempotency-and-durable-execution

Docs and engineering posts (via search, key claims quoted above):
- Temporal Task Queue Priority and Fairness — https://docs.temporal.io/develop/task-queue-priority-fairness ; blog: https://temporal.io/blog/task-queue-priority-and-fairness-your-task-queue-your-way
- Temporal multi-tenant patterns — https://docs.temporal.io/production-deployment/multi-tenant-patterns
- Temporal Cloud pricing — https://docs.temporal.io/cloud/pricing
- Temporal, "Scaling Temporal: The basics" — https://temporal.io/blog/scaling-temporal-the-basics
- Temporal, detecting activity failures (heartbeats) — https://docs.temporal.io/encyclopedia/detecting-activity-failures
- Temporal safe deployments / worker versioning — https://docs.temporal.io/develop/safe-deployments ; https://temporal.io/blog/safe-deployments-with-temporal-worker-versioning-on-kubernetes
- Xgrid, "Deploy Temporal Workflows at Scale" — https://www.xgrid.co/resources/success-stories/temporal-production-workflows-enterprise-scale/
- Vymo Engineering, scaling Temporal load testing — https://medium.com/vymo-engineering/scaling-temporal-load-testing-with-postgres-cassandra-elasticsearch-monitoring-alerting-1176b7a4968b
- Zachary McDonnell, "My Journey Self Hosting a Temporal Cluster" — https://medium.com/@mailman966/my-journey-hosting-a-temporal-cluster-237fec22a5ec
- Naman Gupta, "Temporal Burned Me in Production" (Jun 2026) — https://medium.com/javarevisited/temporal-burned-me-in-production-heres-everything-i-learned-about-scaling-it-right-0fca63c35770
- Automation Atlas, Temporal Cloud vs self-hosted 2026 — https://automationatlas.io/guides/temporal-cloud-vs-self-hosted-2026/
- Nexumo, "Temporal Replay Bugs Hide in Plain Sight" — https://medium.com/@Nexumo_/temporal-replay-bugs-hide-in-plain-sight-7e436f4b3ea4
- Hatchet repo + "durable execution the hard way" — https://github.com/hatchet-dev/hatchet ; https://github.com/hatchet-dev/durable-execution-the-hard-way
- Hatchet vs Temporal — https://hatchet.run/versus/hatchet-vs-temporal ; ZenML Temporal alternatives — https://www.zenml.io/blog/temporal-alternatives
- Restate vs Temporal / first-principles engine — https://www.restate.dev/vs/temporal ; https://www.restate.dev/blog/building-a-modern-durable-execution-engine-from-first-principles
- DBOS, "Postgres is all you need for durable execution" — https://www.dbos.dev/blog/postgres-is-all-you-need-for-durable-execution
- Inngest vs Temporal — https://www.inngest.com/compare-to-temporal
- River (brandur) — https://brandur.org/river ; PG queue benchmarking (fencing/`run_lease`) — https://github.com/hardbyte/postgresql-job-queue-benchmarking ; Oban — https://github.com/oban-bg/oban
- AWS SQS visibility timeout — https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html ; heartbeat pattern — https://www.tecracer.com/blog/2023/03/the-beating-heart-of-sqs-of-heartbeats-and-watchdogs.html
- Kueue fair sharing — https://kueue.sigs.k8s.io/docs/concepts/fair_sharing/ ; https://kubernetes.io/blog/2022/10/04/introducing-kueue/
- kubernetes/kubernetes #95492 "Kubernetes won't run 50,000 Jobs" — https://github.com/kubernetes/kubernetes/issues/95492
- Reconciliation-loop pattern — https://oneuptime.com/blog/post/2026-02-09-operator-reconciliation-loop/view
- Nomad — https://developer.hashicorp.com/nomad/docs/what-is-nomad (2M-container challenge referenced in comparison literature)
- Idempotent AI agents — https://www.buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026
- InfoQ, Temporal + OpenAI Agents SDK (Sept 2025) — https://www.infoq.com/news/2025/09/temporal-aiagent
