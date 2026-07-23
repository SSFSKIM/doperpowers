# Managed Postgres for the A0 startup core — board + dispatch + session store on one database

> **Date:** 2026-07-23. **Scenario:** 10–20 person startup, zero-ops, $1–5k/month
> infra ex-tokens. **Anchor A0:** ~50–200 concurrent runs, ~250–1,000 starts/hour,
> mean run 10–15 min. All three planes (board service, dispatch plane, session
> store) live in ONE managed Postgres, preserving the enterprise spec's
> same-transaction property (board mirror row + claim row commit in one
> transaction), `FOR UPDATE SKIP LOCKED` claims, minutes-scale leases with
> session-log-append-as-heartbeat, fencing tokens, and the append-only session
> event log [spec §1, §2, §4].
>
> **Method note.** Pricing and limits below are from vendor docs/pricing pages
> and third-party trackers fetched 2026-07-23; each claim is tagged
> **[vendor-doc]** (official docs/pricing), **[vendor-claim]** (marketing or
> uncorroborated blog), **[3p]** (third-party tracker/community, not
> independently verified), or **[inference]** (our arithmetic/judgment).
> Absence-of-evidence findings are flagged explicitly.

---

## 0. Verdict up front

**Default: Supabase Pro with a dedicated Large or XL compute add-on + the PITR
add-on — ~$253–353/month at A0.** It is the only candidate that combines: a
dedicated, always-on Postgres (no autosuspend semantics to reason about at
all), *both* session-mode and transaction-mode pooling *plus* direct
connections (so LISTEN/NOTIFY and session state have a first-class home), the
cheapest disk of the serverless-class vendors for an append-heavy log
($0.125/GB-mo), a bolt-on PITR, and — uniquely — a no-code path to the
"workers never hold DB creds" posture via PostgREST + RLS with per-run JWTs.

**Runner-up: Neon (Launch plan) — ~$140–220/month at A0.** Swap to it if the
load is genuinely bursty/business-hours-only (pay-per-CU-hour then roughly
halves the bill), or if branch-per-test-environment workflows earn their keep.
Its costs at A0: storage 2.8× Supabase's price per GB, a transaction-mode-only
pooler, and the scale-to-zero × LISTEN/NOTIFY interaction (mitigable, §3.1).

**Wildcard, only if already all-in on AWS:** plain RDS PostgreSQL
db.t4g.medium Multi-AZ (~$120/mo) — cheapest real PITR and ~410 direct
connections, but the most ops of the managed set (VPC, parameter groups,
maintenance windows), which violates the zero-ops constraint for a team
without an AWS habit.

Move to the enterprise Bundle A shape (dedicated/self-run Postgres) when any
of the §6 triggers fire — roughly at sustained >2–3k starts/hour or when the
hot session-log set can't be held under ~500 GB despite archival.

---

## 1. Load model at A0 (stated assumptions)

All numbers below are **[inference]** from the anchor definition; the write
sizes are assumptions to be replaced by measurement in week one.

| flow | model | rate |
|---|---|---|
| Session-event appends (heartbeat = append) | 50–200 workers × 1 append / 2–5 s | **~15–100 writes/s steady, 50–200/s peak** (bursts when tool-call storms align) |
| Claim transactions | 250–1,000 starts/hr; 1 claim txn each (`SELECT … FOR UPDATE SKIP LOCKED` + board mirror UPDATE + fencing-token bump, one transaction) | **0.07–0.28 txn/s** — three orders below any contention regime |
| Board transitions/comments | ~10 board ops/run | **0.7–2.8 writes/s** |
| Dispatch wakeups | LISTEN/NOTIFY (1–2 controller connections) or 1–2 s polling | negligible either way |
| Reads | controller reconcile scans, resume reads, human UI | low tens/s |

Total: **well under 500 TPS of small-row traffic.** Any 2-vCPU / 4–8 GB
Postgres sustains this with an order of magnitude of headroom; the ready-queue
hot-row contention that makes SKIP LOCKED interesting at A2–A3 is essentially
absent at 0.3 claims/s. **Throughput does not discriminate between candidates
at A0 — connection semantics, autosuspend behavior, storage price, and ops
posture do.**

### 1.1 Storage growth (the real sizing driver)

Assume a session event averages 2–8 KB stored (JSONL-style lines; large tool
results trimmed or pointered). A 10–15 min run appending every 2–5 s produces
~150–450 events ≈ **1–3 MB/run**. At a startup's realistic duty cycle
(business-hours-heavy, ~3,000–10,000 runs/day):

- **~5–30 GB/day raw → ~150 GB–1 TB/month** unpruned (×~1.2–1.4 with WAL +
  index overhead before archival).
- **Archival is mandatory within the first quarter on every candidate.**
  Path: a nightly job promotes events of closed runs older than ~14 days to
  object storage (S3/R2 at $0.015–0.023/GB-mo — 5–30× cheaper than any
  managed-PG disk), leaving a pointer row; the append-only API is unchanged
  (this is exactly the spec §4 promotion, run early and partially).
- **Design steady-state hot set: ~100–300 GB.** All per-candidate storage
  costs below use 150 GB.

This also previews the enterprise-promotion trigger: if you *can't* keep the
hot set bounded (retention requirements, audit), the session store outgrows
the shared database first, exactly as spec §4 predicts.

---

## 2. The pooling footgun, settled (applies to every candidate)

The claim pattern and the dispatch plane touch three Postgres features that
interact differently with pgbouncer-style transaction pooling. Facts, with
sources:

1. **`FOR UPDATE SKIP LOCKED` is SAFE under transaction-mode pooling** —
   row locks are transaction-scoped and release at COMMIT/ROLLBACK; the
   pooler reassigns the server connection only between transactions. The
   doctrine already mandates that the claim SELECT and the board-mirror
   UPDATE commit in one transaction, which is precisely the shape transaction
   pooling preserves. **[vendor-doc + 3p]** (pgbouncer feature matrix;
   JP Camara, "PgBouncer is useful, important, and fraught with peril,"
   https://jpcamara.com/2023/04/12/pgbouncer-is-useful.html)
2. **Session-level advisory locks (`pg_advisory_lock`) BREAK** in
   transaction mode (the lock lives on whichever server connection took it;
   your next transaction may run elsewhere). `pg_advisory_xact_lock` is
   transaction-scoped and safe. If any leader-election or singleton logic
   uses advisory locks, it must use the xact variant or a direct connection.
   **[vendor-doc]** (same sources; pgbouncer issue #976,
   https://github.com/pgbouncer/pgbouncer/issues/976)
3. **`LISTEN` BREAKS in transaction mode** on every pooler (notifications
   can arrive on a server connection already returned to the pool). Dispatch
   wakeups via LISTEN/NOTIFY need a **direct or session-mode connection**.
   NOTIFY (the sending side) works. **[vendor-doc]** (pgbouncer docs; Neon
   pooling docs, https://neon.com/docs/connect/connection-pooling; Supabase
   Supavisor docs)
4. Session `SET`, SQL-level `PREPARE`, `WITH HOLD` cursors also break in
   transaction mode; protocol-level prepared statements are supported on
   modern pgbouncer/Supavisor. **[vendor-doc]**

**Consequence for this architecture:** the heartbeat appends and claim
transactions — the two high-volume flows — are pooler-safe. Only the
reconcile controller's LISTEN channel (1–2 connections) and any
advisory-lock leader election need direct/session connections. So *pooler
limitations do not constrain the design* — provided the wakeup path and
leader election are explicitly placed on direct connections. That placement
should be written into the worker/controller contract.

---

## 3. Candidates

### 3.1 Neon (Databricks) — runner-up

- **Pricing** **[vendor-doc]**: usage-based, no monthly minimum since Dec
  2025. Launch $0.106/CU-hour, Scale $0.222/CU-hour (1 CU = 1 vCPU/4 GB);
  storage **$0.35/GB-month** both plans; instant-restore history
  $0.20/GB-month of retained change. (https://neon.com/pricing,
  https://neon.com/docs/introduction/plans)
- **Connections** **[vendor-doc]**: direct `max_connections` scales with
  compute size — 104 @ 0.25 CU, 419 @ 1 CU, 839 @ 2 CU, capped 4,000. Managed
  PgBouncer pooler on every endpoint, **transaction mode only**, up to 10,000
  clients. No session-mode pooler exists — LISTEN and session state require
  direct connections. (https://neon.com/docs/connect/connection-pooling)
  *Caution (medium confidence, not re-verified): with autoscaling,
  `max_connections` is sized from the minimum compute size, so 200+ direct
  connections implies pinning the floor at ≥1 CU — verify before committing.*
- **Autosuspend under heartbeat load** **[vendor-doc + inference]**: default
  scale-to-zero after 5 min idle (disableable on Launch). Under A0's steady
  heartbeats the compute **never suspends** — so "serverless" buys nothing
  here; you pay always-on rates (~$77/mo per always-on CU on Launch). The
  real footgun is the quiet tail: overnight/weekend idle → suspend →
  **all LISTEN listeners terminated; notifications during restart are lost**
  (Neon's own guides say to disable scale-to-zero if you depend on
  LISTEN/NOTIFY). A level-triggered polling reconcile controller (which the
  spec mandates anyway) makes this survivable; a purely NOTIFY-driven
  dispatcher would silently stall. (https://neon.com/guides/pub-sub-listen-notify,
  https://neon.com/docs/introduction/compute-lifecycle)
- **Storage for append-heavy logs**: $0.35/GB-mo — 150 GB hot ≈ **$52/mo**;
  restore-history billing on an append-heavy workload is change-volume-driven
  (~180 GB change/mo × 1-day default window ≈ ~$1; a 7-day window ≈ ~$8)
  **[inference from vendor-doc rates]**.
- **PITR/backup**: instant restore up to 7 days (Launch) / 30 days (Scale),
  branch-based; this is genuine PITR. **[vendor-doc]**
- **Monthly cost at A0** **[inference]**: ~1–2 CU average always-on ≈
  $77–155 compute + $52 storage + history ≈ **~$140–220/mo**.
- **Fit notes**: cheapest credible option; copy-on-write branches are
  genuinely useful for test environments. Costs: transaction-only pooler,
  the suspend/LISTEN interaction, storage at 2.8× Supabase's per-GB rate as
  the log grows, and compute restarts (maintenance/updates) dropping all
  connections — fine with reconnect logic, but the "dispatch plane never
  blinks" property is weaker than a dedicated instance.

### 3.2 Supabase — DEFAULT

- **Pricing** **[vendor-doc]**: Pro $25/mo (includes $10 compute credit).
  Dedicated compute add-ons: Micro $10, Small $15, Medium $60, **Large $110,
  XL $210**, 2XL $410. Disk: 8 GB included, then **$0.125/GB-mo**. Daily
  backups (7-day retention) included; **PITR add-on $100/mo per 7 days of
  retention**. IPv4 add-on $4/mo. (https://supabase.com/pricing)
- **Connections** **[vendor-doc]**: per-compute hard limits — Large: **160
  direct / 800 pooler**; XL: **240 direct / 1,000 pooler**. Supavisor pooler
  offers **transaction mode (port 6543) AND session mode (port 5432)**
  (session mode on 6543 was deprecated Feb 2025; 5432 remains session mode).
  Direct connections are IPv6-native; IPv4 needs the $4 add-on or the pooler.
  (https://supabase.com/docs/guides/platform/compute-and-disk,
  https://supabase.com/docs/guides/database/connecting-to-postgres,
  https://supabase.com/changelog/32755)
- **Autosuspend**: none on paid dedicated compute — **always-on by
  construction**; the dispatch plane never interacts with scale-to-zero
  semantics at all. **[vendor-doc]**
- **Storage for append-heavy logs**: 150 GB ≈ **$18/mo** — the cheapest
  serverless-class disk here by ~3× vs Neon, ~4× vs PlanetScale.
- **PITR/backup**: daily included; real WAL-based PITR as a $100/mo add-on.
  **[vendor-doc]**
- **Monthly cost at A0** **[inference]**: Pro $25 + Large $110 + disk $18 +
  PITR $100 ≈ **$253/mo** (with XL: **$353/mo**). Well inside budget.
- **Fit notes**: 200+ direct worker connections do NOT fit Large (160) —
  either buy XL (240) or, better, put worker traffic on the pooler / behind
  an API (§4), keeping direct connections for the controller. The unique
  extra: **PostgREST + RLS + per-run JWTs** give a per-run-scoped write API
  with zero service code — a credible v0 of the board-service API's
  credential posture (§4). Risk to note: Supabase's platform surface (auth,
  realtime, etc.) is machinery you don't need; you're buying the boring
  Postgres underneath, which is fine.

### 3.3 AWS RDS PostgreSQL (small instance) — wildcard for AWS-native teams

- **Pricing** **[3p, consistent across trackers]**: db.t4g.medium
  (2 vCPU/4 GB) ≈ $0.065/hr ≈ **$47.5/mo single-AZ, ~$95 Multi-AZ**;
  db.m7g.large (2 vCPU/8 GB) ≈ $0.168/hr ≈ $123/mo single-AZ. gp3 storage
  ~$0.115/GB-mo, 3,000 IOPS baseline included.
  (https://instances.vantage.sh/aws/rds/db.t4g.medium)
- **Connections** **[vendor-doc]**: `max_connections =
  LEAST(DBInstanceClassMemory/9531392, 5000)` → ~**410 direct** on 4 GB —
  200 workers fit directly, no pooler needed. RDS Proxy exists but is
  unnecessary at A0 (and is transaction-pooling with the same §2 caveats).
- **Autosuspend**: none; always-on instance. t4g is burstable — sustained
  50–200 small writes/s is comfortably inside baseline, but watch CPU
  credits **[inference]**.
- **PITR/backup**: built-in continuous backup, restore to any second, up to
  35-day retention, backup storage free up to DB size. The best
  PITR-per-dollar in this list. **[vendor-doc]**
- **Monthly cost at A0** **[inference]**: Multi-AZ t4g.medium + 200 GB gp3 ≈
  **~$120/mo**.
- **Fit notes**: violates zero-ops for a team without AWS muscle memory
  (VPC/SG/parameter groups/minor-version windows/extension management), and
  single-AZ has real maintenance downtime. If the startup already lives in
  AWS, this is the cheapest boring-Postgres-with-real-PITR and the closest
  shape to Bundle A's eventual dedicated instance (making later promotion a
  resize, not a migration).

### 3.4 Aurora Serverless v2 — eliminated at A0

- $0.12/ACU-hr (standard) or $0.156 (I/O-Optimized); 1 ACU ≈ 2 GB RAM;
  storage $0.10/GB-mo + I/O $0.20/1M requests on standard. Min capacity 0
  ACU with auto-pause supported since late 2024 (PG 13.15+/14.12+/15.7+/16.3+).
  **[vendor-doc]** (https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html)
- **Auto-pause requires zero connections** — under A0's steady heartbeats it
  **never pauses** (and resume is ~15 s when it does — an outage-shaped
  event for a dispatch plane). So you pay a floor of ~1–2 ACU always-on
  (~$88–175/mo) **plus I/O** (~100 w/s ≈ 260M req/mo ≈ ~$52) plus storage:
  **~$150–350/mo** for strictly more operational surface than RDS with none
  of Aurora's scale benefits realized at A0. **[inference]**
- Verdict: the serverless pitch is inert under heartbeat load; RDS dominates
  it in this scenario.

### 3.5 Crunchy Bridge — best Postgres DNA, disqualified on continuity risk

- **Pricing** **[vendor-doc]**: Hobby-4 (1 vCPU/4 GB) $70/mo; Standard tier
  from $70 (Standard-4); storage $0.10/GB-mo; **daily + WAL backups and PITR
  included; pgbouncer included**. ~150 GB + Standard-8-class ≈ **~$155/mo**
  **[inference]**. (https://www.crunchydata.com/pricing)
- **Risk** **[3p, unverified]**: Crunchy Data was acquired by Snowflake
  (June 2025, $250M); Snowflake Postgres reached GA Feb 24, 2026. One
  customer-relayed report claims a December 2026 support deadline for
  existing Crunchy arrangements — **not formally verifiable**; no official
  Bridge sunset notice exists (absence of evidence, flagged as such). The
  pricing page is still live and selling.
- Verdict: on pure product merits (superuser access, included PITR, included
  pooler, Postgres-first support) this would contend for default; betting a
  three-plane SSOT on a product whose owner just shipped its successor is
  not zero-ops. Eliminated on continuity risk, not capability.

### 3.6 Fly.io Managed Postgres (MPG) — eliminated; Supabase-on-Fly is dead

- Supabase-on-Fly was **deprecated April 11, 2025** — signups disabled,
  migration recommended. Remove it from any candidate list. **[vendor-doc]**
  (https://supabase.com/changelog/33413)
- Fly's own MPG: Basic (1 GB) $38, Starter (2 GB) $72, **Launch (8 GB)
  $282**; storage $0.28/GB-mo; 1 TB max. **[vendor-doc]**
  (https://fly.io/docs/mpg/) At A0 you'd want Launch-class → **~$324/mo** for
  a younger product at a higher price than Supabase XL-class, from a vendor
  whose previous Postgres product was famously "not managed." Eliminated on
  price/maturity.

### 3.7 Railway / Render — eliminated as the authority store

- **Railway** **[vendor-doc]**: Postgres is a template on a volume;
  snapshot-based backups by default; PITR exists only as a newer
  template-provisioned pgBackRest + Railway Bucket WAL-streaming setup
  (https://docs.railway.com/volumes/point-in-time-recovery). That's DIY
  posture for the system of record — fine for apps, not for the board SSOT.
- **Render** **[vendor-doc/3p]**: genuinely managed, PITR 3 days (Hobby) /
  7 days (paid), read replicas + HA on Pro+. Credible but nothing it wins
  on: connection ceilings and compute pricing are unremarkable, and it lacks
  both Supabase's session-mode-pooler/RLS story and Neon's price floor.
- Both remain excellent hosts for the *thin board-service API process* (§4)
  next to whichever database wins.

### 3.8 PlanetScale for Postgres — wrong storage economics for logs

- Single-node from $5, 3-node HA ~3×; Metal (local NVMe) from $50; storage
  **$0.50/GB-mo beyond 10 GB**; backups $0.023/GB. **[vendor-doc/3p]**
  (https://planetscale.com/pricing) Operationally excellent, but 150 GB of
  hot session log = **$70/mo storage alone**, 4× Supabase — the append-heavy
  workload hits its most expensive dial. A serious candidate at A1+ *after*
  the session store moves to object storage (when the Postgres footprint is
  small and hot); wrong fit while all three planes share one database.

### 3.9 Also checked, one line each

- **DigitalOcean Managed PG**: ~25 connections/GiB (≈100 on 4 GB — 200
  direct doesn't fit), pgbouncer pools, 7-day PITR, ~$60–122/mo — credible
  budget option if the API-mediated topology (§4) is adopted, but no
  session-mode pooler and thin surrounding tooling. **[vendor-doc]**
  (https://docs.digitalocean.com/products/databases/postgresql/details/limits/)
- **Cloud SQL (GCP)**: RDS-shaped, same verdict as §3.3 for GCP-native
  teams; not separately priced here.

---

## 4. Direct-to-Postgres vs thin board-service API at A0

The enterprise spec mandates all worker writes through the board-service API.
Should A0 keep that?

**Yes — keep a thin API (or an API-shaped substitute), and the reasons are
security and portability, not throughput.**

- **Credential story (decisive).** Workers execute generated code in
  sandboxes. A worker holding a raw DB credential — even a "scoped" role —
  can write the board: forge transitions, extend its own lease, rewrite
  another run's history, read every other run's events. That is precisely
  the spec §5 posture ("tokens structurally unreachable from where generated
  code runs") inverted. With an API, workers hold a per-run bearer token
  scoped to {this run's event stream, this ticket's transitions}; the DB
  credential exists only in the API process and the reconcile controller.
- **Connection arithmetic (convenient side effect).** API-mediated topology
  needs ~5–20 pooled DB connections total instead of 200+ worker
  connections — every candidate's connection ceiling becomes irrelevant, and
  the §2 pooler footguns shrink to "controller uses a direct connection."
- **Same-transaction property is preserved and centralized.** The API/
  controller is where claim + board-mirror commit in one transaction; workers
  never speak SQL, so no client can accidentally split the transaction.
- **Cost of the API at A0**: one small always-on process (Fly/Railway/Render,
  $5–20/mo) handling ≤ a few hundred req/s of tiny JSON appends — well
  within a single instance; run two for availability. **[inference]**
- **The Supabase shortcut**: PostgREST + RLS + per-run JWTs is an
  API-with-credential-scoping you don't have to write — a legitimate v0.
  Trade-off: RLS policies become load-bearing security code, and claim
  transactions still need server-side SQL (an RPC function) to stay atomic;
  and it couples the worker contract to Supabase. Reasonable stopgap,
  not the end state.
- **The honest hybrid** (acceptable at A0 if the team refuses to run any
  service): workers write *session events only* through the pooler under a
  role that can INSERT into event tables and nothing else (append-only
  grants, no UPDATE/DELETE anywhere); all claims/transitions live in the
  reconcile controller. This bounds the blast radius of a leaked worker
  cred to "spam events into your own log." Board-state integrity survives;
  confidentiality of other runs' events does not (SELECT would need
  row-level scoping anyway → you've reinvented RLS; see shortcut above).

---

## 5. Cost summary at A0 (150 GB hot set, always-on under heartbeats)

| candidate | monthly est. | 200+ direct conns? | LISTEN home | PITR | killer issue |
|---|---|---|---|---|---|
| **Supabase Pro + Large/XL + PITR** | **$253–353** | XL yes / Large no (pooler yes) | session mode 5432 or direct | $100/mo add-on, 7 d | none at A0 |
| **Neon Launch** | **$140–220** | at ≥1 CU floor (verify autoscale coupling) | direct only | included, ≤7 d | suspend kills listeners; $0.35/GB disk |
| RDS t4g.medium Multi-AZ | ~$120 | yes (~410) | direct | included, ≤35 d | not zero-ops |
| Aurora Sv2 | ~$150–350 | yes | direct | included | never pauses; I/O metering; most AWS surface |
| Crunchy Bridge Std-8 | ~$155 | yes | direct | included | acquisition continuity risk |
| Fly MPG Launch | ~$324 | yes | direct | backups; PITR posture thin in docs | price/maturity |
| Railway (+PITR template) | ~$60–120 | volume-dependent | direct | DIY pgBackRest template | DIY SSOT posture |
| Render Pro-class | ~$100–200 | plan-dependent | direct | 7 d paid | wins on nothing |
| PlanetScale PG | ~$150–300 | yes | direct | $0.023/GB backups | $0.50/GB disk × append-heavy |

All candidates fit the $1–5k budget with 10× headroom — **cost does not pick
the winner; semantics and ops posture do.** Token spend will dwarf all of
these regardless [convergence doc §8.13].

## 6. Promotion threshold — when this core must become Bundle A

Move from "one managed Postgres" to the enterprise shape (dedicated or
self-run Postgres, session store promoted to object storage + streaming tail)
when ANY of these fire — they are the A0-scale version of spike S4's trigger:

1. **Session-write interference**: p99 claim/transition latency measurably
   degrades during append bursts (the shared-plane compromise is the first
   thing scale breaks — promote the session store *first*, keep board +
   dispatch together to preserve the same-transaction property; this is a
   partial promotion, not a migration).
2. **Sustained starts >~2–3k/hour** (entering A1 territory): claim tempo and
   controller fan-out start to justify the dedicated dispatch design.
3. **Hot set >~500 GB despite archival**, or retention/audit requirements
   forbid aggressive archival — managed-PG disk economics collapse
   ($0.125–0.50/GB-mo vs ~$0.02 object storage / ~$0.01 NVMe-per-GB
   amortized).
4. **>~500 genuinely-direct DB consumers** (only reachable if the API
   mandate is abandoned) — past every small-instance connection ceiling.
5. **Managed bill crossing ~$600–1,000/mo** for database alone — at which
   point an RDS m7g.xlarge-class dedicated instance (or self-run with WAL-G,
   if the team has grown an ops function) is strictly cheaper and you are
   already running the board-service API it requires.

Note the direction of travel: because the API-mediated topology (§4) is kept
from day one, promotion is a database swap behind a stable API contract —
the workers never notice.

## 7. Biggest uncertainties (honest list)

1. **Session-event size** drives everything storage-shaped; the 2–8 KB
   assumption spans 4×. Measure in week one; re-run §1.1 and §5.
2. **Neon autoscale × max_connections coupling** (floor-pinning claim) is
   medium-confidence; verify against current docs before choosing Neon.
3. **Crunchy Bridge continuity** — the Dec 2026 support-deadline report is
   single-sourced and unverified; if Bridge publishes a continuity
   commitment, it re-enters as a strong contender.
4. **Supabase Supavisor session-mode capacity** under 100+ session-mode
   clients is hard-capped per compute tier; the API topology avoids this,
   the hybrid topology should load-test it.
5. Third-party pricing trackers (RDS $/hr, Fly plan table) were not
   cross-checked against the AWS/Fly calculators line-by-line; treat ±15%.

## Sources

- Neon pricing/plans/pooling/lifecycle: https://neon.com/pricing ·
  https://neon.com/docs/introduction/plans ·
  https://neon.com/docs/connect/connection-pooling ·
  https://neon.com/docs/introduction/compute-lifecycle ·
  https://neon.com/guides/pub-sub-listen-notify ·
  https://neon.com/docs/introduction/restore-window
- Supabase: https://supabase.com/pricing ·
  https://supabase.com/docs/guides/platform/compute-and-disk ·
  https://supabase.com/docs/guides/database/connecting-to-postgres ·
  https://supabase.com/changelog/32755 (session-mode port change) ·
  https://supabase.com/changelog/33413 (Fly deprecation)
- PgBouncer semantics: https://github.com/pgbouncer/pgbouncer/issues/976 ·
  https://jpcamara.com/2023/04/12/pgbouncer-is-useful.html
- Aurora Sv2: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html ·
  https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-aurora-serverless-v2-scaling-zero-capacity
- RDS: https://instances.vantage.sh/aws/rds/db.t4g.medium ·
  https://repost.aws/knowledge-center/rds-mysql-max-connections
- Crunchy: https://www.crunchydata.com/pricing ·
  https://www.crunchydata.com/blog/crunchy-data-joins-snowflake ·
  https://www.snowflake.com/en/blog/snowflake-postgres-enterprise-ai-database/
- Fly MPG: https://fly.io/docs/mpg/ · https://fly.io/docs/about/pricing/
- Railway PITR: https://docs.railway.com/volumes/point-in-time-recovery ·
  https://railway.com/deploy/postgres-pitr
- PlanetScale: https://planetscale.com/pricing ·
  https://planetscale.com/docs/planetscale-plans
- DigitalOcean: https://docs.digitalocean.com/products/databases/postgresql/details/limits/
