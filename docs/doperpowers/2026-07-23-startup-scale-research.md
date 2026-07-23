# Startup-scale (A0) cloud infra — research convergence

**Date:** 2026-07-23. **Question:** what cloud infrastructure should a 10–20
person AI-native startup run the doperpowers worker/reviewer board pipeline
on, at productivity-maximizing intensity, with zero dedicated infra staff?

**Relation to prior work.** This is the downscale companion to
`2026-07-23-cloud-scale-research.md` (enterprise convergence) and
`specs/2026-07-23-cloud-scale-reference-architecture-design.md` (Bundle A
reference architecture). The six source articles were not re-read; their
verdicts live in `research/2026-07-23-cloud-scale/` and were injected as
baseline. This round is five targeted reports in
`research/2026-07-23-startup-scale/`:

| report | axis |
|---|---|
| `sandbox-substrate-a0.md` | managed sandbox/compute at A0 |
| `managed-agents-substrate.md` | managed brain+hands runtimes as worker substrate |
| `managed-postgres-core.md` | one managed Postgres for board+dispatch+session store |
| `board-simplification-a0.md` | can the custom board service be dropped? |
| `zero-ops-economics-a0.md` | observability, secrets, failure posture, token economics |

**Human-fixed frame (grill outcomes):** anchor = A0 (below); deliverable =
named-default-stack spec (opinionated vendors + per-slot swap conditions);
posture = zero-ops first, infra budget $1–5k/month ex-tokens. Assumed and
unchallenged: semantic layer frozen (pre-code gate, park states, independent
adversarial review, tiered merge authority); cheap invariants from day one
(three-plane split, same-transaction property, hash-keyed environments),
expensive things behind swap conditions.

---

## 0. Verdict up front — the A0 stack

**Anchor A0** (extends the enterprise ladder downward, below A1): ~50–200
concurrent runs, ~250–1,000 starts/hour work-hours-weighted (≈3–5k runs/day),
mean run 10–15 min, ~25–30k run-hours/month.

| slot | named default | monthly (list) | runner-up / escape | report |
|---|---|---|---|---|
| Sandbox compute | **E2B Pro** (template-per-env-hash, pause/resume; egress ≈ tie with Daytona post-correction — E2B wins on 1,100 concurrency headroom + uptime) | ~$2.2–4.7k (runs/day-dependent; $3.3k if 1-vCPU suffices) | Daytona (nearer runner-up than first written — see correction §1.1); Northflank ~$1.8k budget hatch (spike egress first) | sandbox |
| Worker runtime | **Claude Code, self-orchestrated** (our harness on rented sandboxes) | — | Managed Agents = port-not-swap, rejected now; nearest flip = Claude Code on the web gaining a fleet API | managed-agents |
| Board + dispatch + session store | **One Supabase Pro Postgres** (Large/XL compute + PITR add-on) | ~$253–353 | Neon Launch ~$140–220 (bursty loads); RDS t4g if AWS-native | postgres |
| Board tier | **Thin board service kept** (~6 endpoints, conditional-UPDATE transitions) on Fly/Render/Railway; **Linear as human-facing one-way mirror** | ~$10–45 + Linear seats | Linear-direct only under 7 strict conditions (low-A0, serialized dispatcher, verify-after-write…) | board |
| Observability | **Axiom free tier** (logs) + Postgres session store as metrics/cost SSOT | $0–25 | Better Stack; Grafana Cloud free at low end; Datadog confirmed 5–30× too expensive | zero-ops |
| Secrets | **1Password Service Accounts** if already on Business (verify SA pricing — absent from docs), else **Infisical free** (~3 machine identities needed) | $0–20 | Doppler mispriced per-user for this shape | zero-ops |
| Reconciler | **Cron, not resident** (1–5 min tick): pg_cron/Fly schedule/GitHub Actions | ~$0–2 | resident controller returns at A1 tempo | zero-ops |

**Infra total at A0: ≈$2.5k (low) / ≈$3.3k (mid) / ≈$5k+ (top of band)** —
fits the budget except at the very top, where E2B list pricing must be
negotiated or the Northflank hatch taken. Note: the economics report's
smaller infra figures ($0.4–0.9k low/mid) assumed Fly-class sandbox rates;
the sandbox axis rejected Fly (no egress control, Jan 2026 15h+11h
management-plane outages), so **the reconciled infra line is $2.5–5k with
E2B**. Token conclusion unchanged either way.

**Token spend dominates everything: ≈$55k / $110–160k / $260–340k per month**
(low/mid/top, Fermi $0.8–3/run across the band) — a token:infra ratio of ~20–100×
even at E2B rates. Every infra decision at A0 is a rounding error; every
token decision is the budget.

---

## 1. The five axis verdicts, compressed

### 1.1 Sandbox substrate — the enterprise verdict flips as predicted

The enterprise own-fleet answer (k8s+gVisor on NVMe) was carried by two
premises that both fail at A0: SaaS cost at 1,000–20,000 concurrent
(~$73k+/mo) and an ops team to absorb a fleet. At A0 the SaaS bill is
$2–5k/mo and the ops team does not exist. **[Corrected post-review,
verified live 2026-07-23]** The report's original tiebreaker — "only E2B
can express the domain allowlist" — is wrong: Daytona's live docs show a
`domainAllowList` (max 20 entries, wildcards) plus 10 CIDRs,
runtime-changeable on Tier 3+ (erratum added to the archived report). Both
finalists express "allow github.com + api.anthropic.com + registries, deny
rest" — the control that makes short-lived-token git isolation actually
contain a prompt-injected worker. **E2B still wins**, on concurrency
headroom (purchasable to 1,100 vs Daytona Tier 4 ≈ 250 two-vCPU runs —
bare A0 peak) and the better public uptime record; Daytona has arguably
the cleanest hash-keyed snapshot story (digest-pinned named snapshots;
mutable tags refused) and is a nearer runner-up than first written. Keep
the substrate
behind one thin create/exec/destroy adapter so a vendor swap is config, not
rewrite. Own-fleet returns at ~$25–30k/mo sustained managed bill (~300–500
sustained concurrent, 5–10× A0) or on a compliance/BYOC mandate.

### 1.2 Worker runtime — nobody sells "your harness on our runtime"

Every managed brain+hands product (Managed Agents, Codex cloud, Cursor
Cloud Agents, Devin) bundles its own agent loop; ours IS the harness
(Claude Code + skills + board client + git flow), so a substrate that
replaces the harness replaces the worker. Managed Agents is the closest
port target (custom SKILL.md upload is first-class; $0.08/session-hour ≈
$2.4k/mo at A0 — officially documented) but: no Claude Code, no plugins, no
documented git-credential injection for hosted sandboxes (token would
co-reside with generated code), undocumented org concurrency cap, beta
harness that "may be refined between releases" under our tuned skills,
Claude-only fleet. **The structural near-miss is Claude Code on the web**:
actual Claude Code on Anthropic VMs, repo-declared plugins install at
session start, GitHub proxy keeps tokens out of the container — but
dispatch is an experimental per-routine webhook under unpublished per-plan
daily allowances on subscription billing. Right architecture, no fleet
contract. **Flip condition (watch this):** a stable session-create API +
published org quotas + API-key billing for Claude Code cloud sessions flips
the whole compute slot to viable-now.

### 1.3 Postgres core — one database, doctrine intact

A0 load is trivial for any 2-vCPU Postgres (15–100 writes/s steady
heartbeat appends; 0.07–0.28 claims/s — no contention regime). **Storage is
the real driver**: 1–3 MB/run of session events → ~150–630 GB/month raw at
A0 rates (the earlier 1 TB top assumed 10k runs/day, 2× A0-top);
archival of closed runs >14 days to object storage is mandatory within the
first quarter (this is the enterprise spec §4 promotion, run early and
partially), holding the hot set to ~100–300 GB. **The pooling footgun is
settled**: `FOR UPDATE SKIP LOCKED` claims are safe under transaction-mode
pooling (row locks are transaction-scoped — the doctrine's one-transaction
claim is exactly the shape pooling preserves); what breaks is `LISTEN` and
session advisory locks, which must live on the reconciler's 1–2 direct
connections. Supabase wins on: no autosuspend semantics at all, both
session- and transaction-mode pooling plus direct connections, cheapest
disk of the class ($0.125/GB-mo) for an append-heavy log, and a PostgREST+
RLS+per-run-JWT path to "workers never hold DB creds" without writing code.
Same-transaction property survives unchanged.

### 1.4 Board tier — the simplification is an illusion; the thin service stays

The genuinely new finding vs enterprise: **at A0, Linear's rate limits are
no longer the disqualifier** (3–16k req/hr total vs 5,000/hr per OAuth
actor; 1–5 App-User actors is inside Linear's documented model). GitHub
remains out at every A0 point (500 content-writes/hr/actor ≈ 60 runs/hr).
So the decision collapses onto correctness, where the evidence hardened:
Linear's `IssueUpdateInput` was schema-verified to carry **no precondition
field of any kind** — `issueUpdate` is last-writer-wins, and no transition-
restriction feature exists. Collision math without CAS: ~5% double-claims
at high A0 with event-driven claiming (~50/hr); 30-second polling or
deterministic top-of-queue picking make it catastrophic. And "no service"
re-materializes as a serializing dispatcher + webhook guard bot + nightly
audit export (Linear retains history 90 days) — three cron jobs that still
never provide atomicity. **Verdict: keep the ~6-endpoint board service**
($10–45/mo managed, 1–2 days to stand up — schema plus endpoints from the
enterprise spec §1 endpoint list — ~2–4 hrs/month), Linear as one-way
human mirror (coalesced transitions; honest math: 500–3,000 req/hr across
the band = 10–60% of one OAuth actor — debounce per ticket or add a second
actor at the top end). It is the first brick
of the enterprise architecture, not a migration liability.

### 1.5 Zero-ops operations and economics

**Observability:** A0's log volume (45–300 GB/mo) fits inside Axiom's free
tier (500 GB/mo); per-run traces via run_id-stamped lines; fleet dashboard
is ~8 SQL panels off Postgres; the cost meter (per-run token usage rows,
cache-hit ratio) is the highest-leverage instrument in the system — build
it week one. Observability data is a view, never identity (the durable
session log remains the run's identity). **Failure posture:** five failure
classes (runaway run, dead run, claim storm, spend runaway, provider
outage) all resolve to one idempotent reconciler cron + circuit breakers
that fail into "dispatch paused + Slack + parked" — nothing pages; the
human ritual is a weekly 30-minute reconcile. **Secrets:** ~3 machine
identities (dispatcher, reconciler, landing); structural unreachability is
achieved by placement, not vault features — board-write and merge
credentials never touch worker machines; git token bundled into the remote
at init; Anthropic key accepted in worker env as a spend credential bounded
by workspace spend caps. **Token levers (the only ones that matter):**
model tiering per phase (~1.7–2× total), cache discipline (a broken cache
≈ +4×/run; meter the per-run cache-read ratio), run-length control (cost is
superlinear in run length; 12→8 min ≈ −45% tokens).

---

## 2. Cross-cutting syntheses

1. **Verdicts are functions of scale; the doctrine is not.** Three
   enterprise verdicts flipped at A0 (own fleet → E2B; resident controller
   → cron; big dedicated Postgres → one small managed Postgres) and two
   held (board service stays; SaaS trackers still can't be SSOT). Every
   flip traces to a premise that was explicitly scale-indexed in the
   enterprise round. The semantic layer and the ten design rules survive
   contact with A0 without a single amendment.
2. **The pressure order inverts infra instinct.** What a growing A0 system
   hits first, in order: **Anthropic tier → sandbox bill → cron cadence →
   Postgres**. **[Corrected post-review, verified live 2026-07-23 on the
   official rate-limits page]** Tiers are named Start/Build/Scale/Custom
   (no numbered tiers), and the binding meter is the **monthly spend cap**
   — $500 / $1,000 / $200,000 / uncapped — so A0's token spend requires
   Scale from day one and Custom at A0-top. ITPM is officially cache-aware
   (cache reads don't count, except retired Haiku 3.5 — the must-verify
   flag resolves in the design's favor): A0-mid's ~1.3M fresh-input
   tokens/min is 65% of even Start-tier Sonnet (2M), with 2.5–5× headroom
   at Build/Scale; only **Fable-class ITPM (0.5M/1.5M/4M) sits at or below
   A0-mid tempo through Build**. The provider conversation still fires
   before any infra migration — as commercial onboarding, not scarcity.
   The board/dispatch Postgres — where the enterprise spec spends most of
   its design — is the *last* thing a startup outgrows.
3. **Growth path is swap-by-swap, not rearchitecture.** Because the thin
   board service, the same-transaction Postgres schema, the substrate
   adapter, and the session-log identity doctrine are all kept at A0, every
   growth rung toward Bundle A is a vendor/carrier swap behind a stable
   contract: Postgres resize → dedicated; cron → resident controller; E2B
   → k8s+gVisor fleet; Axiom → owned telemetry. The workers never notice.
4. **The budget tension is real and lives in one line.** Every slot except
   sandboxes is $0–400/mo; E2B at list is $2.2–4.7k and the honest band is
   ~$2–7k (A0's own definition spans 2.5×). Pre-contract actions: get
   paused-storage + extra-concurrency pricing in writing, pressure-test for
   a startup discount, measure real run-hours and CPU duty in week one
   (1-vCPU sufficiency alone is −30%).
5. **Credential doctrine survives downscaling through three placements:**
   egress allowlist on the sandbox (E2B native), board writes behind
   per-run bearer tokens (API or PostgREST+RLS), merge credential on the
   landing path only. None of these cost meaningful money at A0 — the
   doctrine was never expensive; it was only ever a design discipline.

## 3. Honesty ledger (what we do NOT know)

- **E2B unknowns:** paused-storage pricing, extra-concurrency pricing —
  both unpublished; ask before contracting. All cold-start latencies in
  the field are vendor-claimed; the one independent benchmark publishes no
  methodology.
- **Linear unknowns:** per-endpoint mutation caps (headers-only,
  unpublished) — the one number that could break even the low-A0
  Linear-direct fallback; its rate-limit page self-contradicts (2,500 vs
  5,000/hr API keys; OAuth actors unambiguously 5,000).
- **Anthropic unknowns:** Managed Agents org concurrency cap (would have
  to be answered before committing A0 traffic, were that path taken; its
  skill auto-trigger semantics are likewise unverified); Claude Code on
  the web per-plan daily run allowances. ~~Tier ITPM figures and the
  cache-read exemption~~ — resolved post-review against the live official
  rate-limits page (named tiers Start/Build/Scale/Custom; cache-read
  exemption confirmed, Haiku 3.5 excepted; see §2 item 2).
- **1Password Service Accounts pricing/limits:** absent from vendor docs
  fetched — confirm before making it the pick.
- **Fermi spans:** session-event size assumption (2–8 KB) spans 4× of all
  storage math; per-run token cost spans 6× ($0.8–3/run×runs) — no public
  measurements of autonomous Claude Code runs of this shape exist. Both
  collapse with week-one instrumentation (cost meter + event-size
  measurement), which is why instrumentation precedes contracts in the
  adoption order.
- **Crunchy Bridge continuity** (Dec 2026 support-deadline report) is
  single-sourced; it was eliminated on that risk, not capability.

## 4. Open items the spec must decide

1. Stack bundle choice (managed-default vs lean vs frugal) — human call,
   presented with the approaches.
2. Board-service v0 form: hand-written ~6-endpoint service vs Supabase
   PostgREST+RLS stopgap (couples worker contract to Supabase; RLS becomes
   load-bearing security code; claim needs an RPC function either way).
3. Week-one instrumentation list as a first-class deliverable (cost meter,
   event-size measurement, run-hour/CPU-duty measurement) — it governs
   every Fermi in this document.
4. Provider-quota posture: which Anthropic tier/agreement, and whether the
   spec treats quota as a designed input (per-phase model tiering to
   spread ITPM) or an operational escalation.
5. Linear seat plan + mirror coalescing rules (which transitions humans
   see).
6. The E2B pre-contract action list and the decision threshold for the
   Northflank spike.
