# Zero-ops operational model & economics at anchor A0 (startup scale)

> **Date:** 2026-07-23. **Scenario:** 10–20 person AI-native startup, no
> infra engineer, infra budget **$1–5k/month excluding model tokens**.
> **Anchor A0:** ~50–200 concurrent runs, ~250–1,000 starts/hour
> (work-hours-weighted), ≈3–5k runs/day, mean run 10–15 min. Workers are
> Claude Code sessions on rented sandboxes; board + dispatch + session
> store on managed Postgres.
>
> Companion to `docs/doperpowers/2026-07-23-cloud-scale-research.md`
> (§2.5 observability, §2.6 economics, §5 design rules) and the reference
> architecture spec's §7/§8 and scale-anchors table (A1 ≈ 1k runs/hr /
> ~500 concurrent). A0 sits **below A1**: roughly 1/4 to 1/10 of A1's
> start rate, with shorter runs.
>
> **Evidence discipline:** every price below is labeled
> **[verified — vendor page]**, **[vendor-claimed]** (vendor's number via
> vendor blog/docs quoted by press), or **[3rd-party, medium
> confidence]** (2026 pricing aggregators/articles; not confirmed on the
> vendor page in this session). Absence-of-evidence findings are flagged
> explicitly. Claude API pricing is from the bundled `claude-api` skill
> reference (cached 2026-06-24) — treated as verified.

---

## 0. Verdict up front

- **Observability pick: Axiom** — A0's entire log volume (45–300 GB/mo)
  fits inside Axiom's **free** Personal tier (500 GB/mo loaded)
  [verified — axiom.co/pricing]; the paid tier is a $25/mo platform fee
  including 1 TB/mo. Runner-up: Better Stack (~$45–100/mo). Datadog is
  confirmed too expensive per dollar of value (per-event indexing is the
  trap, §1.3). The "just query Postgres" null option is viable but only
  wins if the team refuses a new vendor — Axiom's free tier removes the
  cost argument for it.
- **Secrets pick: ride what you already pay for.** If the company has
  1Password Business (likely at 10–20 people), Service Accounts + `op`
  CLI in the dispatcher = $0 marginal (pricing/limits **not confirmed**
  on the vendor docs page — flagged §3). Otherwise **Infisical free tier**
  (≤5 machine identities — enough: this design needs ~3). Doppler at
  $21/user/mo [3rd-party] is mispriced for this shape. The enterprise
  doctrine (structural unreachability) survives at A0 through **secret
  placement, not vault features** — §3.
- **Token spend is ~30–100× infra** — even wider than the enterprise
  research's 10–100× heuristic, because A0's infra is nearly free while
  per-run token cost is not. All-in monthly at A0: **≈$55k (low) /
  ≈$110–160k (mid) / ≈$260–340k (top)**, of which infra is $0.7–5k. The
  only levers that matter are model tiering, cache discipline, and
  run-length control (§4).
- **The binding constraint nobody prices: Anthropic rate limits.** At A0
  mid, sustained fresh-input tempo approaches Tier-4 Sonnet ITPM
  [3rd-party, medium confidence — verify against the org's actual
  limits]. The growth threshold that fires first at A0 is a *quota*
  conversation, not an infra migration (§5).

---

## 1. Observability

### 1.1 Volume Fermi

Session logs are the volume driver (per the task's premise, and
consistent with the enterprise research's failure-boundary framing —
harness/dispatch logs are tiny beside session transcripts):

| input | low | mid | top |
|---|---|---|---|
| runs/day | 3,000 | 4,000 | 5,000 |
| structured log/run | 0.5 MB | 1 MB | 2 MB |
| **GB/day** | 1.5 | 4 | 10 |
| **GB/month (30d)** | **45** | **120** | **300** |

Add ~10–20% for dispatch/controller/board logs. Event count (for
event-priced vendors): a 12-min run emits ~500–2,000 structured events
(tool calls, transitions) → **60–300M events/month**.

### 1.2 Managed options priced at 45–300 GB/mo

| vendor | pricing basis | A0 low (45 GB) | A0 mid (120 GB) | A0 top (300 GB) | confidence |
|---|---|---|---|---|---|
| **Axiom** | free: 500 GB/mo load, 10 GB-hr query, 25 GB storage, 30-day retention; paid: $25/mo incl. 1 TB load + 100 GB-hr query + 100 GB storage | **$0** | **$0** (query compute may push to paid) | **$0–25** | **verified — [axiom.co/pricing](https://axiom.co/pricing)** |
| **Better Stack** | $0.15/GB ingest + $0.08/GB-mo retention; ~$24/mo base | ~$35 | ~$55 | ~$95 | 3rd-party ([Modern DataTools](https://www.modern-datatools.com/tools/better-stack/pricing), [CubeAPM](https://cubeapm.com/blog/betterstack-pricing-review/)) |
| **Grafana Cloud** | free: 50 GB logs/mo, 14-day retention; Pro: ~$0.45/GB ingest (+$0.10/GB-mo retention) + $19 platform | **$0** (free tier) | ~$75 | ~$170 | 3rd-party ([CloudZero](https://www.cloudzero.com/blog/grafana-cloud-pricing/), [CubeAPM](https://cubeapm.com/blog/grafana-cloud-pricing-and-review/)) |
| **Honeycomb** | free: 20M events/mo; Pro from $130 per 100M events/mo | ~$130 | ~$130–260 | ~$390 | 3rd-party ([CubeAPM](https://cubeapm.com/blog/honeycomb-io-review-pricing/), [PricingSaaS](https://pricingsaas.com/companies/honeycomb)) |
| **Datadog** | $0.10/GB ingest **plus** $1.70–2.55 per **million events indexed** (15-day) + per-host fees | ~$110+ | ~$220–400 | ~$550–800+ | 3rd-party ([SigNoz](https://signoz.io/blog/datadog-logs-pricing/), [Parseable](https://www.parseable.com/blog/datadog-log-management-cost)) |
| **Null option: Postgres + dashboard** | run metadata/metrics in the existing managed PG; full JSONL to object storage (~$0.015/GB-mo); Grafana free tier or Metabase on top | ~$5 | ~$10 | ~$20 | computed |

**Datadog verdict — verified too expensive, with the mechanism named:**
ingest at $0.10/GB is misleadingly cheap ($12–30/mo at A0); the cost is
the separate **per-million-events indexing** fee — 60–300M events/mo
indexed is $100–750/mo before a single host or APM SKU, and Datadog's
value proposition assumes you buy the platform (hosts ~$15–31 each, APM,
etc.). At A0 it is 5–30× Axiom-equivalent cost for capability the team
won't use. [Pricing figures 3rd-party; the two-meter structure
(ingest + index) is consistently reported across independent sources.]

**Null-option honest assessment:** the session store is *already*
Postgres per the scenario, so run metadata, state transitions, token
usage, and session-end reasons are queryable for free. But 45–300 GB/mo
of raw transcripts does **not** belong in managed Postgres (Neon storage
$0.35/GB-mo [3rd-party] → 300 GB is $105/mo and grows; also bloats
backups). The null option is really "PG for metrics + object storage for
transcripts + build your own search/alerting." Since Axiom's free tier
covers the whole volume with search, dashboards, monitors, and a Slack
notifier, the null option only wins on vendor-count minimalism.

### 1.3 Recommendation and what a 15-person team actually needs

**Pick: Axiom free tier** for logs, with the Postgres session store as
the metrics/billing SSOT. Concretely, the four needs:

1. **Per-run traces** — every log line stamped with `run_id` /
   `ticket_id` / `attempt_key`; "what did run X do" = one Axiom query.
   The durable JSONL in the session store remains the *identity* of the
   run (doctrine); Axiom is a disposable **view** — losing it loses
   nothing (design rule 2's spirit: observability data is cache, never
   identity).
2. **Fleet dashboard** — one dashboard, ~8 panels, fed from Postgres
   (queue depth, claimed-not-acked, workers live, starts/hr, session-end
   reason taxonomy, park-queue depth) + Axiom (log error rates). The
   three Anthropic fleet gauges (depth / pending / polling) carry over
   from the enterprise spec §7 unchanged — they're SQL queries here.
3. **Cost meter** — per-run usage rows (input / output / cache-read /
   cache-write tokens × model) written by the worker wrapper at run end
   into Postgres; a daily rollup gives $/run, $/ticket, $/repo, and the
   **cache-hit ratio per run** — §4 makes this the highest-leverage
   metric in the whole system.
4. **Alerting to Slack** — Axiom monitors → Slack for log-shaped alerts;
   a 5-minute cron (§2) evaluates the Postgres-shaped breakers (spend,
   stall, storm) and posts to Slack. No PagerDuty, no on-call product.

---

## 2. Failure posture without on-call

Governing rule (inherited from design rules 8–9): **every bounded thing
fails into "paused + loud (Slack) + parked", never into silent
degradation or silent retry-forever.** Nothing pages at 3am because
nothing needs a human inside 24h: the pipeline's failure mode is "stops
making progress", not "corrupts state" — the board and session log are
the SSOT and are always resumable.

### 2.1 The ~5 failure classes at A0 and their zero-ops answer

| # | failure class | detection | zero-ops answer | human needed? |
|---|---|---|---|---|
| 1 | **Runaway run** (agent loops; burns tokens/wall-clock) | per-run token + wall-clock budget stamped at dispatch; reconciler compares usage vs cap | kill sandbox, park ticket `needs-human` with transcript pointer; per-run cap bounds the damage (~$5–10 max at Sonnet rates) | reviews parked ticket next work-block |
| 2 | **Dead run** (sandbox dies, network drop, harness crash) | lease older than N min with no session-log progress (progress-as-liveness, same primitive as the enterprise design) | dead-run reconciler cron reclaims the lease, re-dispatches; resume from the durable session log — never restart from zero | no — self-heals |
| 3 | **Claim/dispatch storm** (bug fans out too many starts) | starts-per-minute and global-concurrency counters vs caps, in SQL | dispatcher enforces max-starts/min + max-concurrency as conditional INSERTs; breach trips **dispatch pause** flag + Slack | flips the unpause flag after reading the alert |
| 4 | **Spend runaway** (aggregate, across many normal-looking runs) | hourly token-spend rollup vs budget; plus Anthropic Console workspace **spend limits** as the provider-side backstop | budget breach → dispatch pause + Slack; provider spend cap is the hard floor if the pipeline's own meter is the thing that broke | decides whether to raise budget or investigate |
| 5 | **Provider outage / rate-limit exhaustion** (429/529 storm) | step-level retry metrics; failure-ratio window in the reconciler | per-step backoff (SDK default) absorbs blips; sustained ratio trips dispatch pause; in-flight runs park as `stream-error` (infra, not agent, per the session-end taxonomy) and auto-resume on a successful canary run | no — self-heals; Slack FYI |

A sixth class exists but is weekly-tempo at A0, not operational:
**merge-plane conflict contention** (at ~16 concurrent changes on one
repo, conflict probability ≈ 40% per the enterprise research §7.4). At
A0's per-repo volume this is handled by the existing review-bounce loop;
it becomes a breaker only near A1.

### 2.2 The reconciler as a cron on managed compute

One idempotent pass, one schedule, no resident service (A0 does not need
the enterprise re-judgment in favor of a resident controller — batch
cadence at 1–5 min covers 250–1,000 starts/hr fine; the resident-
controller re-judgment fires at A1+ tempo):

- **What it does per tick:** reclaim stale leases (class 2) → kill
  over-budget runs (class 1) → evaluate storm/spend/failure-ratio
  breakers (classes 3–5) → drain the Slack notification outbox. All
  state in Postgres; the pass is a handful of conditional UPDATEs —
  restart-safe by construction.
- **Where it runs (pick one, all fit the budget):** Supabase `pg_cron`
  calling an edge function (zero extra vendors if Supabase is the
  Postgres pick); a Fly Machine on a schedule (~$2/mo); or a GitHub
  Actions `schedule:` workflow (free, but ~5-min minimum granularity and
  best-effort timing — acceptable at A0, and this repo's pipeline
  already uses Actions as an event trigger).

### 2.3 What reaches a human, and when

Three Slack-severity levels, zero pages: **FYI** (breaker absorbed
something: retries, one dead run reclaimed), **Action-next-work-block**
(park queue > threshold; recurring same-ticket failures),
**Action-today** (dispatch paused — the pipeline is stopped and will
stay stopped until a human flips the flag). The weekly human ritual is a
30-minute board reconcile + cost-meter review. If "Action-today" fires
more than ~once/week, that is itself a growth signal (§5).

---

## 3. Secrets & credentials at A0

### 3.1 The insight: at A0, unreachability is placement, not tooling

The enterprise doctrine (research §2.4) is: credentials **structurally
unreachable** from where generated code runs; merge authority and
credential topology are the same shape. At A0 the credential inventory
is small enough that this is achieved by *where each secret lives*, and
no vault product feature is load-bearing:

| credential | who holds it | worker can reach? |
|---|---|---|
| Git push token (contents-only, consumer repos, branch-protection on) | **bundled into the remote URL at sandbox init** — never in worker env, never in the transcript path | reachable-by-shape only (it's in `.git/config`), contained by token scope + branch protection — same honest boundary the worker-host README already documents |
| Board-write credential | dispatcher/reconciler only (platform secret on the dispatch compute) | **no — structurally** (different machine/identity) |
| Merge credential (GitHub App / landing workflow) | landing path only (Actions secret / runner env) | **no — structurally** |
| Anthropic API key | injected into worker env at dispatch, from a **per-workspace key with a Console spend limit** | yes — accepted at A0: it is a spend credential, not a data credential; blast radius = the workspace spend cap |
| Observability/DB admin keys | humans + reconciler identity | no |

That is ~3 machine identities (dispatcher, reconciler, landing) plus
human access.

### 3.2 Vendor options at this shape

| option | cost at A0 | fit | confidence |
|---|---|---|---|
| **1Password Service Accounts** (if already on 1Password Business, ~$7.99/user) | **$0 marginal** | `op run` / `op inject` in dispatcher & CI; humans already live there | Business plan price [3rd-party]; **Service-Account pricing/limits NOT found on the vendor docs page fetched this session — absence of evidence, confirm before committing** ([1password.dev/service-accounts](https://www.1password.dev/service-accounts/)) |
| **Infisical** | **$0** (free ≤5 identities, 3 projects) → Pro $18/identity-mo for the few machine identities | purpose-built machine-identity model; MIT self-host is the credible growth rung toward Bundle A's vault+proxy | 3rd-party ([xpay](https://www.xpay.sh/saas-pricing/infisical/), [dev.to teardown](https://dev.to/beton/infisical-pricing-teardown-2026-1ang)) |
| **Doppler** | ~$21/user/mo Team → ~$315/mo for 15 seats | per-*user* pricing punishes a small team with few secrets; features fine, price shape wrong | 3rd-party ([Vendr](https://www.vendr.com/marketplace/doppler), [CyberSecTool](https://www.cybersectool.com/blog/secrets-management-pricing-breakdown-2026)) |
| **Fly/Modal native secrets** | $0 | delivery mechanism, not a manager: no versioning/audit/rotation UX; right place for dispatcher-level env, wrong place for the source of truth | verified-by-design (platform feature) |

### 3.3 Minimal shape (the pick)

**Source of truth:** 1Password Service Accounts if already paying for
1Password Business (verify SA limits first — flagged above), else
Infisical free tier. **Delivery:** platform-native secrets (Fly/Modal)
hold the dispatcher's own identity token; the dispatcher fetches at
dispatch time and injects per run: Anthropic workspace key → worker env;
git token → **remote URL only**. Workers get **zero standing secrets**
beyond those two, and the board-write and merge credentials never touch
any machine a worker runs on — the doctrine's topology, at $0–20/month.

---

## 4. Token economics at A0 — the dominant line

Claude pricing used (verified via the bundled `claude-api` skill,
cached 2026-06-24): Sonnet 4.6 $3/$15 per MTok ($2/$10 Sonnet 5 intro
through 2026-08-31); Opus 4.8 $5/$25; Haiku 4.5 $1/$5. Cache reads
≈0.1× input price; 5-min cache writes 1.25× input price.

### 4.1 Fermi: one 12-minute Claude Code implementer run (input-heavy, cached)

Assumptions: ~45 API turns; context grows ~20k → ~120k tokens (avg
~70k); per turn the harness cache-reads the whole prefix, cache-writes
the new suffix, sends a few k fresh tokens, emits ~0.5–1k output
(incl. thinking).

| component | tokens/run | Sonnet 4.6 $ | Opus 4.8 $ |
|---|---|---|---|
| cache reads (45 × ~70k avg) | ~3.1M | 3.1 × $0.30 = **$0.94** | 3.1 × $0.50 = $1.55 |
| cache writes (each new token written ~once) | ~150k | 0.15 × $3.75 = **$0.56** | 0.15 × $6.25 = $0.94 |
| fresh input | ~50k | **$0.15** | $0.25 |
| output + thinking | ~40k | 0.04 × $15 = **$0.60** | 0.04 × $25 = $1.00 |
| **total/run** | ~3.3M billed-token events | **≈ $2.2** | **≈ $3.7** |

Range across ticket sizes: **$1–4/run** on Sonnet (Haiku ≈ $0.7, Opus ≈
$3–6). Sanity check: Anthropic reports ~$13/dev/active-day for
interactive Claude Code [vendor-claimed, via
[CloudZero](https://www.cloudzero.com/blog/claude-code-pricing/) /
[Finout](https://www.finout.io/blog/claude-code-pricing-2026)] — one
autonomous 12-min run ≈ $1.5–3 is 4–8 runs per dev-day-equivalent,
plausible. The Batch API's 50% discount does **not** apply as a lever:
worker loops are sequential/interactive; 24-hour batch turnaround
doesn't fit the run shape.

### 4.2 Daily and monthly, and the token:infra ratio

Blended $/run (mostly Sonnet implementers + Opus gate/review verdict
calls, which are short): **$1.5–3/run**. Work-hours-weighted →
~22 working days/month:

| | runs/day | $/run | $/day | **tokens $/month** |
|---|---|---|---|---|
| A0-low (tiering discipline, short runs, Haiku share) | 3,000 | $0.80 | $2.4k | **≈ $53k** |
| A0-mid | 4,000 | $1.75 | $7k | **≈ $110–155k** |
| A0-top (5k runs, Opus-heavy, 15-min runs) | 5,000 | $3.00 | $15k | **≈ $260–330k** |

Infra at A0 (all rungs within the $1–5k budget):

| line | low | mid | top | basis |
|---|---|---|---|---|
| sandboxes: ~18–30k machine-hrs/mo (runs/day × 0.2 h × 30) | $300 (Fly shared-cpu-2x ≈ $0.015/hr [3rd-party]) | $700 | $2.5–3k (E2B ≈ $0.10–0.13/2-vCPU-hr [3rd-party citing e2b.dev]; Modal ≈ 1.5–3× that with multipliers [3rd-party]) | per-second billing, pay only during runs |
| managed Postgres (board + dispatch + session metadata) | $30 (Neon $0.106/CU-hr [3rd-party]) | $60 (Supabase Pro + compute) | $150 | A0 engine load ≈ 150–250k actions/day — far under one node's ceiling |
| object storage (transcript archive) | $5 | $10 | $25 | ~$0.015/GB-mo |
| observability | $0 (Axiom free) | $0–25 | $25–100 | §1 |
| secrets | $0 | $0 | $20 | §3 |
| cron/misc/egress | $20 | $50 | $150 | |
| **infra total** | **≈ $0.4k** | **≈ $0.9k** | **≈ $3–5k** | |

**Token:infra ratio ≈ 60–130× (low), ≈ 120–170× (mid), ≈ 70–100×
(top).** The enterprise heuristic (10–100×) is *conservative* at A0
because rented per-second sandboxes make infra nearly free while token
cost per run is unchanged. Consequence: **every infra decision at A0 is
a rounding error; every token decision is the budget.** All-in monthly:
**≈ $55k / ≈ $110–160k / ≈ $260–340k** (low/mid/top).

### 4.3 The three levers that actually move total cost

1. **Model tiering per phase** (the enterprise §2.6 finding, unchanged):
   frontier models only at decision points (gate, park/escalate, review
   verdicts — short calls), cheap models for implementation bulk.
   Sonnet→Haiku on mechanical ticket classes ≈ 3× on those runs;
   Opus-everywhere vs tiered ≈ 1.7–2× total. Cursor's controlled runs
   showed ~8× cost spread at similar quality [vendor-claimed, absorbed
   in the research doc] — the single biggest lever.
2. **Caching discipline**: in the Fermi, cache reads are ~94% of input
   volume. A broken cache (unstable system-prompt prefix, mid-loop tool
   set changes, per-run timestamps in the prompt) reprices ~3M
   tokens/run from $0.30/M to $3/M ≈ **+$8/run ≈ +4×** total cost.
   This is why §1.3's cost meter records the per-run cache-read ratio:
   a fleet-wide cache regression is a five-figure monthly event that
   looks like nothing else.
3. **Run-length control**: cost is **superlinear** in run length
   (context grows, so cache-read volume per turn grows). Cutting mean
   run 12 → 8 min is roughly −45% tokens, not −33%. Better-scoped
   tickets at the gate, per-run task budgets, and early park/kill are
   cost features, not just quality features. (Corollary from the
   enterprise research: evaluate the gate/planner model on total
   downstream run cost, not its own bill.)

Not levers at A0: infra substrate choice (rounding error), Batch API
(shape mismatch), and negotiating sandbox pricing (see ratio).

---

## 5. Growth thresholds — the measurable signal per managed choice

Each row: the number that says "you've outgrown this," and the next rung
toward the enterprise Bundle A architecture (sovereign Postgres core;
spec's adoption path P0–P3).

| managed choice at A0 | you've outgrown it when (measurable) | next rung (toward Bundle A) |
|---|---|---|
| **Managed Postgres board+dispatch** (Supabase/Neon, one DB) | engine actions/day sustained > ~1M (A1's floor); p95 claim latency > ~250 ms; connection-pool saturation alarms | dedicated/larger Postgres first (still managed); then Bundle A's board service + SKIP-LOCKED dispatch plane on the same PG — schema carries over, the one-transaction board+claim guarantee is already the design |
| **Rented sandboxes** (Fly Machines → E2B/Modal) | sandbox line > ~$3–5k/mo (≈ 400–600 sustained concurrent at listed rates), or cold-start/queue p95 visibly stretching mean run time | self-hosted k8s + gVisor per-run pods on NVMe hosts (research §7.3: ~$73k/mo SaaS vs $5–15k self-hosted at 1,000 concurrent; the crossover arrives with the first infra hire, ~300–500 concurrent) |
| **Axiom free tier** | >500 GB/mo loaded, or query compute > 10 GB-hr/mo (dashboards eating the allowance) → $25/mo tier; outgrown *as a category* when circuit breakers need sub-minute automated reaction fed by contention telemetry | Axiom Cloud first (trivial); then Bundle A §7's self-owned telemetry: conflict-rate/hottest-file breakers wired into dispatch, harness logs outside data-bearing sandboxes |
| **Reconciler-as-cron** | dispatch-pause events needing a human > ~1/week; reclaim latency (cron cadence) starts costing meaningful queue time; starts approach A1's 0.3/sec sustained | the resident level-triggered reconcile controller (the enterprise re-judgment §7.2 — same functions, resident carrier), HA-paired |
| **Secrets: 1Password SA / Infisical free** | >5 machine identities; first need for per-run short-lived credentials, per-environment egress allowlists, or credential issuance at dispatch tempo | Infisical Pro/self-host (MIT) as the interim vault; then Bundle A §5: per-claim STS-style short-lived creds + vault/egress proxy |
| **Anthropic API self-serve tier** | 429s appearing in the failure-ratio breaker; sustained fresh-input ITPM > ~50% of tier limit. A0-mid Fermi: ~200k fresh tokens/run × 4k runs over ~10 h ≈ **1.3M ITPM sustained** — near the reported Tier-4 Sonnet limit of 2M ITPM [3rd-party, medium confidence]. Note the load-bearing detail that **cache reads don't count toward ITPM** [3rd-party — verify on the org's rate-limit page]: without it this threshold would already be breached at A0-low | enterprise agreement / custom quotas; provider quota architecture becomes a first-class design input (spec §8) — at A0 this threshold fires **before any infra migration does** |
| **Zero-ops posture itself** | park-queue drain time > 1 working day; >1 Action-today Slack/week; any incident where "paused until morning" cost real money | first infra engineer + the spec's P1 (supervised autonomy) practices; on-call only when the business tempo demands sub-day reaction |

Reading the table: at A0 the pressure order is **rate limits → sandbox
bill → cron cadence → Postgres**, roughly the reverse of what
infra-minded instinct expects. The board/dispatch Postgres — the thing
the enterprise spec spends the most design on — is the *last* thing a
startup outgrows.

---

## 6. Source register & confidence notes

**Verified on vendor page this session:** Axiom pricing
([axiom.co/pricing](https://axiom.co/pricing)). **Verified via bundled
skill reference (2026-06-24 cache):** all Claude model + cache pricing.

**Vendor-claimed (vendor's own number, not independently measured):**
Anthropic's ~$13/dev/active-day Claude Code figure; E2B plan structure
(3rd-party articles citing [e2b.dev/pricing](https://e2b.dev/pricing)).

**3rd-party, medium confidence (2026 pricing articles/aggregators; spot-
check before contracting):** Grafana Cloud
([CloudZero](https://www.cloudzero.com/blog/grafana-cloud-pricing/),
[CubeAPM](https://cubeapm.com/blog/grafana-cloud-pricing-and-review/),
[MonitoringCost](https://monitoringcost.com/grafana-cloud-pricing));
Better Stack
([Modern DataTools](https://www.modern-datatools.com/tools/better-stack/pricing),
[CubeAPM](https://cubeapm.com/blog/betterstack-pricing-review/));
Honeycomb ([CubeAPM](https://cubeapm.com/blog/honeycomb-io-review-pricing/),
[PricingSaaS](https://pricingsaas.com/companies/honeycomb));
Datadog ([SigNoz](https://signoz.io/blog/datadog-logs-pricing/),
[Parseable](https://www.parseable.com/blog/datadog-log-management-cost),
[Last9](https://last9.io/blog/datadog-pricing-all-your-questions-answered/));
Doppler ([Vendr](https://www.vendr.com/marketplace/doppler),
[CyberSecTool](https://www.cybersectool.com/blog/secrets-management-pricing-breakdown-2026)
— sources disagree: $12–14 vs $21/user/mo);
Infisical ([xpay](https://www.xpay.sh/saas-pricing/infisical/),
[dev.to](https://dev.to/beton/infisical-pricing-teardown-2026-1ang));
Fly.io ([Deploy Handbook](https://deployhandbook.com/pricing/fly-io),
[ToolPick](https://www.toolpick.dev/reviews/fly-io-review));
Modal ([Northflank](https://northflank.com/blog/ai-sandbox-pricing),
[Beam](https://www.beam.cloud/blog/modal-pricing-explained) — incl. the
1.25–2.5× regional / non-preemption multiplier claim);
E2B ([Morph](https://www.morphllm.com/e2b-pricing),
[Beam](https://www.beam.cloud/blog/e2b-pricing-explained));
Neon/Supabase ([simplyblock](https://vela.simplyblock.io/articles/neon-serverless-postgres-pricing-2026/),
[Makerkit](https://makerkit.dev/blog/saas/supabase-pricing));
Anthropic Tier-4 rate limits and the cache-reads-exempt-from-ITPM rule
([MindStudio](https://www.mindstudio.ai/blog/claude-api-token-limits-increase-tier-breakdown),
[aifreeapi](https://www.aifreeapi.com/en/posts/claude-api-quota-tiers-limits)).

**Absence-of-evidence flags:** (1) 1Password Service Accounts pricing
and rate limits — the vendor developer page fetched this session
contains no pricing; whether they are free within Business, capped, or
metered is **unestablished** — confirm before making them the pick.
(2) No public per-run token measurements exist for autonomous Claude
Code runs of this shape — §4.1 is a Fermi cross-checked against
Anthropic's interactive per-dev figure, not a measurement; the spec's
S3-style spike (instrument 50 real runs) supersedes it.
(3) Doppler's 2026 list price is inconsistently reported ($12–21/user)
— either number leaves the verdict unchanged.

**Instrumentation-first caveat:** the three A0 cost figures span 6× —
the spread collapses only with the §1.3 cost meter live. Build the meter
in week one; it is the cheapest line item in this document and governs
the largest.
