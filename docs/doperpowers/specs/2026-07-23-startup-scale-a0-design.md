# Startup-Scale (A0) Cloud Infrastructure — Named-Stack Design

**Date:** 2026-07-23 · **Status:** Living spec · **Track:** controlled
(brainstorming → this spec → writing-plans)

## Purpose

A 10–20 person AI-native startup wants to run the doperpowers worker/reviewer
board pipeline as cloud agents at productivity-maximizing intensity — each
person driving several agents in parallel, all day — with **zero dedicated
infrastructure staff**. This spec names the exact stack to contract and
deploy, slot by slot, with per-slot swap conditions.

It is the **A0 instantiation (profile) of the enterprise reference
architecture** (`2026-07-23-cloud-scale-reference-architecture-design.md`),
not a separate world. The semantic layer is frozen and identical: pre-code
gate, park states, independent adversarial review with implementation-blind
lenses, tiered merge authority. The three cheap invariants are kept from day
one because they cost nothing at A0 and make every growth step a swap rather
than a rearchitecture: **three-plane SSOT split**, **same-transaction
property**, **hash-keyed environments**.

Where the enterprise spec is vendor-neutral by design, this spec is
deliberately opinionated: at startup scale the design's value is a buildable
recipe — "contract X, deploy Y" — with explicit conditions for when each
named choice stops being right.

Evidence base: five targeted research reports in
`research/2026-07-23-startup-scale/` synthesized in
`2026-07-23-startup-scale-research.md`, on top of the enterprise round's ten
reports. Fermi figures below inherit that convergence doc's honesty ledger;
the week-one instrumentation (§Adoption) exists to collapse them.

## Terms of art

Inherits all terms from the enterprise spec (run, lease, fencing token,
same-transaction property, certified environment, environment key,
progress-as-heartbeat, level-triggered reconcile). New or narrowed here:

- **A0** — the scale anchor below A1: ~50–200 concurrent runs, ~250–1,000
  starts/hour work-hours-weighted (≈3–5k runs/day), mean run 10–15 min,
  ≈13–27.5k run-hours/month across the band.
- **Substrate adapter** — the single thin interface (create-from-template /
  exec-stream / destroy) between the dispatcher and the sandbox vendor.
  Everything vendor-specific lives behind it; a vendor swap is a config
  change, not a worker-protocol change.
- **Mirror** — a coalesced projection of board state into a SaaS tracker
  for humans: **one-way authority, two-way visibility**. Never
  authoritative; human edits return as events through the board's legality
  check; conflicts always resolve to the board service.
- **Cost meter** — per-run token-usage rows (input / output / cache-read /
  cache-write × model) written to the session store at run end; the SSOT for
  spend, cache-hit ratio, and $/ticket.

## Scale anchor and budget envelope

| | A0-low | A0-mid | A0-top |
|---|---|---|---|
| runs/day | ~3,000 | ~4,000 | ~5,000 |
| concurrent (peak) | ~50–100 | ~100–150 | ~200 |
| run-hours/month | ~13k | ~18k | ~27.5k |
| infra (this stack, list) | ≈$2.5k | ≈$3.3k | ≈$5k+ |
| tokens (Fermi, $0.8–3/run across the band) | ≈$55k | ≈$110–160k | ≈$260–340k |

Infra budget: **$1–5k/month ex-tokens** (human-confirmed). Token:infra ratio
≈20–100× — every infra decision is a rounding error against token decisions;
this ordering drives §10.

---

## §1 Board service — ticket SSOT (kept, thin, hand-written)

**What.** The enterprise spec §1 board service at its smallest honest size:
~6 endpoints (claim / transition / comment / park / query / reconcile) over
the board schema in the shared Postgres. A few hundred lines, hand-written
(human-confirmed over the PostgREST+RLS stopgap — see Decision Log).

**Transition legality is a server-side conditional UPDATE** — e.g.
`UPDATE ticket SET state='in-progress', owner=$run WHERE id=$id AND
state='ready-for-agent'`; rows-affected=0 means a lost race, reported as
such. This one statement is simultaneously the legality check and the atomic
claim lock. No SaaS tracker sells this at any price: Linear's
`IssueUpdateInput` was schema-verified to carry no precondition field
(last-writer-wins), and GitHub's rate limits exclude it at every A0 point
(500 content-writes/hr/actor ≈ 60 runs/hr).

**Workers authenticate with per-run bearer tokens** scoped to {this run's
event stream, this ticket's legal transitions}, minted at dispatch. The DB
credential exists only in the board service and the reconciler.

**Deployment:** one small always-on process, two instances for availability,
on Render (default; Fly.io as alternate — Decision Log 9) at ~$10–45/month. Load at A0 is ~1–4 requests/second of
tiny JSON — a single instance holds it with 100× headroom. Workers fail
closed when the board is unreachable.

**Linear mirror (human surface) — one-way authority, two-way visibility:**
sync human-relevant transitions only (~2–3 of the ~8 board writes/run).
Honest budget math: that is 500–3,000 req/hr across the A0 band — **10–60%
of one OAuth App-User actor's 5,000/hr**, not a rounding error — so run one
actor at low A0, and at the high end add per-ticket debouncing (at most one
mirror write per ticket per short window) or a second App-User actor, both
inside Linear's documented model. Humans work in Linear daily; agents never
read it. Linear's own PR automations are disabled on mirrored teams (a
second uncoordinated writer otherwise). Back-edge — a design addition
beyond the research reports: human edits in Linear arrive as webhook events
that the board service applies through the same legality check. Visibility
flows both ways; authority never does.

## §2 Dispatch plane — same database, same doctrine

Dispatch state (claims, leases, fencing tokens, admission counters) lives in
**the same Supabase Postgres** as the board schema — the same-transaction
property is non-negotiable and survives A0 trivially: the claim row and the
board mirror row commit in one transaction.

- **Claim idiom:** `SELECT … FOR UPDATE SKIP LOCKED` inside the claim
  transaction. Verified safe under transaction-mode pooling (row locks are
  transaction-scoped); at A0's 0.07–0.28 claims/sec there is no contention
  regime at all.
- **Pooling placement rule (write into the service contract):** board
  service and dispatcher use the transaction-mode pooler; anything using
  `LISTEN` or session advisory locks uses 1–2 **direct** connections.
  `pg_advisory_xact_lock` only, never the session variant. (The A0 cron
  reconciler needs neither LISTEN nor leader election — this rule
  future-proofs the resident controller that arrives at A1.)
- **Leases:** minutes-scale, progress-refreshed — a session-event append IS
  the heartbeat. Expiry means reclaim-and-resume from the session log, never
  lost work. Fencing token increments per claim of the same run; stale
  processes cannot complete a superseded attempt. Run-attempt keys stamp
  branches/PRs/comments for idempotent recovery.
- **Dispatcher:** one process (may live inside the board service at A0),
  admission-controlled by two SQL counters: max-starts/minute and
  max-global-concurrency, enforced as conditional INSERTs (these are also
  circuit-breaker levers, §9). The counters are global, not per-tenant — a
  deliberate simplification of the enterprise plane's admission fairness,
  fine at one company's few-project scale.

## §3 Compute plane — E2B sandboxes running our harness

**Substrate: E2B Pro** (~$0.1656 per 2-vCPU/4-GiB run-hour + $150/mo plan;
≈$2.2–4.7k/month across the A0 band at list; ≈$3.3k if 1-vCPU proves
sufficient). Both finalists can express the egress allowlist — "allow
github.com + api.anthropic.com + package registries, deny everything else",
the control that makes short-lived-token git isolation actually contain a
prompt-injected worker: E2B natively with runtime-updatable domain rules;
Daytona via its `domainAllowList` (max 20 entries, wildcard support;
runtime firewall changes on Tier 3+, which A0's concurrency demands anyway)
— verified live 2026-07-23, correcting the archived report's 5-CIDR claim.
E2B wins on **concurrency headroom** (purchasable to 1,100 ≈ 5× A0 peak,
vs Daytona Tier 4's 500 vCPU ≈ 250 two-vCPU runs — bare A0 peak, no
headroom) **and the best public uptime record** in the category; lifecycle
API limits sit three orders above our start rate.

- **Environments:** one E2B template per environment key
  (hash(env-spec) ⊕ hash(lockfiles) ⊕ toolchain digest) — template name IS
  the key; exact-match restore by construction, drift impossible rather than
  detected. Certification gate and mock fence carry over from the enterprise
  spec unchanged.
- **Worker runtime: Claude Code + the doperpowers plugin, self-orchestrated.**
  Research verdict: no vendor sells "your harness on our runtime" — Managed
  Agents replaces the harness (rejected; flip conditions in Decision Log),
  and Claude Code on the web runs our harness perfectly but sells no
  fleet-scale dispatch contract yet. Watch that flip condition; it is the
  nearest thing to a compute-slot revolution.
- **Substrate adapter:** all E2B calls behind the create/exec/destroy
  adapter. Runner-up (Daytona) SDK path kept warm; activating it is config.
- **Pre-contract action list (blocking, cheap):** get paused-storage and
  extra-concurrency pricing in writing (both unpublished); pressure-test for
  a startup discount (list price consumes the budget top); confirm the
  Mar-2026-style incident posture in the SLA conversation.

**Swap conditions:** sustained ≥2× A0 run-hours (bill ≥$9k) → renegotiate,
drop to Northflank (after spike T4 verifies its undocumented egress), or
accept the Hetzner ops tax (~$0.5–0.65k + 0.1–0.2 FTE — reverses the
zero-ops decision, so it is a posture change, not a line-item change).
Measured CPU duty ≤15% → re-run the comparison against Vercel Sandbox's
active-CPU billing if it ships egress control. ≥2 dispatch-blocking vendor
incidents in a month → activate Daytona. Own-fleet (k8s+gVisor) returns at
~$25–30k/month sustained managed bill (≈300–500 sustained concurrent,
5–10× A0) or on a compliance/BYOC mandate.

## §4 Session store — append-only in the same Postgres, archival early

Session events (the identity of work — doctrine unchanged) append to the
shared Postgres; the append doubles as the lease heartbeat. Sizing truth: A0
writes 15–100 events/sec steady (trivial) but **1–3 MB/run of storage —
~150–630 GB/month raw at A0 rates** (WAL/index overhead on top). Therefore,
from the first quarter:

- **Nightly archival job:** events of closed runs older than ~14 days
  promote to object storage (S3/R2, ~$0.015–0.023/GB-mo, 5–30× cheaper than
  managed-PG disk), leaving pointer rows. The append-only API is unchanged —
  this is the enterprise §4 promotion executed early and partially.
- Hot-set design target: ~100–300 GB (≈$13–38/month on Supabase disk).
- Compaction never rewrites logs; summaries are derived views.

## §5 Postgres core — Supabase Pro

**Supabase Pro + dedicated Large or XL compute + PITR add-on ≈
$253–353/month.** Chosen because it is the only candidate with: always-on
dedicated compute (no autosuspend semantics for the dispatch plane to
reason about at all), *both* session- and transaction-mode pooling plus
direct connections (LISTEN gets a first-class home), and the cheapest disk
of its class for an append-heavy log ($0.125/GB-mo).

Connection arithmetic under the API-mediated topology: ~5–20 pooled
connections total (board service + dispatcher) + 1–2 direct (reconciler) —
every per-tier connection ceiling becomes irrelevant.

**Swap conditions:** genuinely bursty/business-hours-only load → Neon Launch
(~$140–220, pay-per-CU roughly halves the bill; accept transaction-only
pooler + autosuspend-kills-LISTEN, mitigated by the polling reconciler).
AWS-native team → RDS t4g.medium Multi-AZ (~$120, best PITR-per-dollar, not
zero-ops). **Promotion to the Bundle A shape** when any fire: sustained
>2–3k starts/hour; hot set >~500 GB despite archival; append bursts degrade
claim p99 (promote the session store FIRST, keep board+dispatch together to
preserve same-transaction); DB bill crossing ~$600–1k/month. Because the
API contract is stable, promotion is a database swap the workers never see.

## §6 Credentials — unreachability by placement

At A0 the doctrine ("credentials structurally unreachable from where
generated code runs") is achieved by where each secret lives, not by vault
features. Three machine identities exist: dispatcher, reconciler, landing.

| credential | lives | worker can reach? |
|---|---|---|
| git push token (contents-only, branch-protection on) | bundled into the remote URL at sandbox init | by-shape only; contained by scope + E2B egress allowlist |
| board-write credential | board service / reconciler only | no — structurally |
| merge credential | landing path (Actions/runner) only | no — structurally |
| Anthropic API key | injected per run from a workspace key with a Console spend limit | yes — accepted: spend credential, blast radius = the cap |
| DB/observability admin | humans + reconciler | no |

**Source of truth:** 1Password Service Accounts if the company already pays
for Business (verify SA pricing/limits first — absent from vendor docs),
else Infisical free tier (published cap: up to 5 identities total; we need
~3). Platform
secrets (Fly/Render/E2B env) are delivery only, never the source of truth.

## §7 Review & merge plane — inherited frozen, scale machinery deferred

The semantic tiers are the enterprise spec's §6 unchanged, including the
three ★ human-approved amendments (N-lens review with all lenses
implementation-blind; auto-land-under-watch as the fourth authority tier;
the merge-resolver third species). What A0 does NOT need yet is the scale
machinery around them: no verifier-stage SLO component (the finding stream
at A0 per-repo volume does not DoS the human tier), no batch+bisect or
speculation queues (merge-conflict contention is a weekly-tempo event at A0
per-repo volume, absorbed by the normal review-bounce loop). Adopt the
verifier stage when finding volume measurably outpaces human triage; adopt
queue machinery near A1 per-repo tempo (the enterprise research's ~40%
conflict probability at ~16 concurrent changes on one repo, used here as
the tempo signal). Auto-land starts
with an empty change-class whitelist and grows only by evidence.

## §8 Observability — Axiom as view, Postgres as meter

- **Logs: Axiom free tier.** A0's whole volume (45–300 GB/month) fits
  inside the free 500 GB/month; every line stamped with
  `run_id`/`ticket_id`/`attempt_key`, so a per-run trace is one query.
  Paid tier is a $25/month cliff, not a renegotiation.
- **Metrics/spend SSOT: the Postgres session store.** The fleet dashboard
  is ~8 SQL panels (queue depth, claimed-not-acked, live workers,
  starts/hour, session-end-reason taxonomy, park-queue depth) plus Axiom
  error rates. The three fleet gauges from the enterprise spec §7 (depth /
  pending / polling) are SQL queries here.
- **Cost meter (week one, before any contract):** per-run token-usage rows
  written at run end; daily rollups give $/run, $/ticket, cache-read
  ratio, and the infra:token split. This is the highest-leverage
  instrument in the system (§10 explains why the cache-read ratio alone
  can be worth five figures monthly).
- **Doctrine:** observability data is a disposable view — deleting all of
  it loses nothing (the session log is the identity of work). Alerting:
  Axiom monitors → Slack for log-shaped alerts; the reconciler evaluates
  the Postgres-shaped breakers and posts to the same channel.

## §9 Failure posture — nothing pages

Governing rule: every bounded thing fails into **paused + Slack + parked**,
never silent degradation or retry-forever. The board and session log are
always resumable, so the failure mode is "stops making progress", not
"corrupts state". No on-call product, no 3am pages.

| failure class | detection | answer | human? |
|---|---|---|---|
| runaway run | per-run token+wall-clock budget vs usage | kill sandbox, park `needs-human` with transcript pointer | next work-block |
| dead run | lease stale with no session-append progress | reconciler reclaims, re-dispatches, resume from log | no — self-heals |
| claim/dispatch storm | starts/min + concurrency counters vs caps (SQL) | dispatch-pause flag + Slack | flips the flag |
| spend runaway | hourly rollup vs budget; Console spend cap as backstop | dispatch pause + Slack | raise budget or investigate |
| provider outage / 429 storm | step-retry ratio window | backoff absorbs blips; sustained → pause; in-flight park as `stream-error`, auto-resume on canary success | no — Slack FYI |

**The reconciler is a cron, not a resident controller** (the enterprise
re-judgment reverses below A1 tempo): one idempotent pass every 1–5 minutes
— reclaim stale leases → kill over-budget runs → evaluate breakers → drain
the Slack outbox. All state in Postgres; conditional UPDATEs; restart-safe.
Carrier: Supabase pg_cron (zero extra vendors), or a scheduled Fly Machine
(~$2/mo). Three Slack severities (FYI / next-work-block / Action-today),
zero pages; the weekly ritual is a 30-minute reconcile + cost review.
"Action-today" firing >~1/week is itself a growth signal (§11).

## §10 Economics and provider quotas — the real ceilings

Tokens are the budget; infra is noise. The three levers that move total
cost, in order of leverage:

1. **Model tiering per phase** — frontier models only at decision points
   (gate, park/escalate, review verdicts — short calls); implementation bulk
   on cheaper tiers. ≈1.7–2× total; the single biggest lever.
2. **Cache discipline** — cache reads are ~94% of input volume in the run
   Fermi; a broken cache (unstable prompt prefix, mid-loop tool-set churn,
   per-run timestamps) ≈ +4× per run. The cost meter records per-run
   cache-read ratio precisely because a fleet-wide cache regression is a
   five-figure monthly event that looks like nothing else.
3. **Run-length control** — cost is superlinear in run length (context
   growth compounds cache-read volume): 12→8 min ≈ −45% tokens. Gate-side
   ticket scoping and early park/kill are cost features.

**Provider quota is a first-class design input — and the binding meter is
the monthly spend cap, not ITPM** (verified live 2026-07-23 on the official
rate-limits page, superseding the research round's 3rd-party figures).
Anthropic's tiers are named Start/Build/Scale/Custom with monthly spend
caps of **$500 / $1,000 / $200,000 / uncapped** — A0's token spend
($55k–340k/month) requires the **Scale tier from day one** and crosses into
Custom territory at A0-top. ITPM, meanwhile, is officially cache-aware
(cache reads do not count, except retired Haiku 3.5 — the research round's
must-verify flag resolves in the design's favor): A0-mid's ~1.3M
fresh-input tokens/min is 65% of even the Start-tier Sonnet cap (2M), with
2.5–5× headroom at Build/Scale (5M/10M). The exception is **Fable-class
ITPM (0.5M / 1.5M / 4M by tier), which sits below or beside A0-mid's tempo
through the Build tier** — a frontier-heavy model mix re-tightens the
ceiling. Net: the Anthropic conversation still fires before any infra
migration, but as a commercial onboarding step (tier escalation to
Scale/Custom), not an ITPM scarcity crisis. Tiering (lever 1) doubles as
ITPM-spreading for the frontier share. Console workspace spend limits are
the provider-side backstop for breaker class 4.

## §11 Growth path — swap-by-swap to Bundle A

Pressure order at A0 (inverts infra instinct): **provider quotas → sandbox
bill → cron cadence → Postgres.** The board/dispatch Postgres — where the
enterprise spec spends most of its design — is the last thing outgrown.

| A0 choice | outgrown when (measurable) | next rung |
|---|---|---|
| Anthropic Start/Build tier | monthly spend approaching the tier cap (Build caps at $1k/month — any real A0 usage exceeds it); 429s in the breaker window; fresh-input ITPM >50% of the model's tier limit | Scale tier immediately; Custom tier / enterprise agreement at A0-top |
| E2B | sustained bill ≥$25–30k/mo (~300–500 concurrent) or BYOC mandate | k8s+gVisor per-run pods on NVMe (enterprise §3), first infra hire funded by the gap |
| reconciler-as-cron | pause events needing humans >1/week; reclaim latency costs queue time; ~0.3 starts/sec sustained | resident level-triggered controller, HA pair (enterprise §2) |
| one shared Postgres | §5 promotion triggers | session store to object-storage+tail first; then dedicated PG; board+dispatch stay co-located |
| Axiom free | >500 GB/mo or breakers need sub-minute reaction | Axiom paid → owned telemetry wired into dispatch (enterprise §7) |
| secrets free tier | >5 machine identities; per-claim short-lived creds needed | Infisical Pro/self-host → vault + egress proxy (enterprise §5) |
| zero-ops posture itself | park-queue drain >1 workday; >1 Action-today/week; a "paused until morning" that cost real money | first infra engineer + the enterprise spec's P1 phase (supervised autonomy) practices |

## Adoption order

1. **Week 1 — instrument before contracting (T1).** Cost meter + event-size
   measurement + run-hour/CPU-duty measurement on the existing single-VM
   setup (`infra/worker-host/`). Every Fermi above spans 4–6×; this is the
   cheapest deliverable and governs the largest line.
2. **Week 1–2 — E2B contract facts (T2)** and Supabase + board service
   standup (1–2 days: write the schema plus the ~6 endpoints from the
   enterprise spec §1 endpoint list — that spec carries the list and one
   example UPDATE, not a finished schema). Linear mirror +
   per-endpoint-cap confirmation (T3). Open the Anthropic tier
   conversation in the same window (Scale-tier spend caps, §10).
3. **Week 2–4 — cutover:** dispatcher → E2B adapter; reconciler cron;
   breakers; Axiom; secrets placement. Old VM becomes the canary/fallback.
4. **Steady state:** weekly 30-min reconcile; monthly re-read of the swap
   conditions against the meter (a standing agenda item, not an aspiration).

**Spikes** (named T1–T4 to avoid collision with the enterprise spec's
S1–S4): **T1** instrumentation (precedes contracts); **T2** E2B unpublished
pricing + discount (blocking the contract); **T3** Linear per-endpoint
mutation caps (support email + one load test; blocking the mirror's final
shape only); **T4** Northflank egress verification (fires only if E2B
negotiation fails or the budget hatch is needed).

## Acceptance (behavior-phrased)

The A0 deployment conforms when:

1. Two workers racing one ready ticket: exactly one claim succeeds; the
   loser observes rows-affected=0 and walks away without a wasted run.
2. A worker killed mid-run: within one reconciler tick its lease is
   reclaimed, the run resumes from the session log on a fresh sandbox, and
   the superseded sandbox's late writes are refused by fencing token.
3. A prompt-injected worker attempting to exfiltrate its git token reaches
   only allowlisted domains; the token cannot touch protected branches or
   merge anything — its honest blast radius is pushes to unprotected
   branches, bounded by attempt-key provenance at review and fencing at
   landing; board-write and merge credentials are absent from the sandbox
   by inspection.
4. An illegal transition submitted directly to the board service returns a
   legality error; no illegal state is ever observable in the board, and
   the Linear mirror never shows a state the board didn't hold.
5. Deleting the entire Axiom dataset loses no ability to resume, audit, or
   re-derive any run (observability is a view; the session log is identity).
6. Tripping any breaker (storm, spend, failure-ratio) halts new dispatch
   within one tick, posts one Slack message, parks in-flight work
   resumable, and unpausing is a single human flag-flip.
7. Swapping the sandbox vendor in the adapter config (E2B→Daytona) requires
   zero changes to worker protocol, board schema, or session-log format.
8. The monthly cost meter reports $/run, $/ticket, cache-read ratio, and
   infra:token split without manual collation; a deliberately
   cache-broken canary run is visibly flagged by the ratio metric.
9. Restoring the same environment key twice yields byte-identical
   toolchains (drift impossible by construction).
10. The board service down for an hour: workers fail closed (no local
    claims), humans keep reading Linear's last mirrored state, and recovery
    requires no reconciliation beyond the reconciler's normal tick.

## Decision Log

1. **Stack M (managed default) over Stack L (Northflank lean) and Stack F
   (Hetzner frugal)** — human-confirmed. L saves ~$2.5k/mo but its egress
   control is undocumented (security property, not taste); F saves ~$4k but
   costs 0.1–0.2 FTE, reversing the zero-ops posture decision. Reopen: L
   via spike T4; F only as an explicit posture change.
2. **E2B over Daytona** — tie on price ($0.1656/run-hr both) and,
   corrected post-review, effectively tie on egress: live Daytona docs
   (2026-07-23) show a `domainAllowList` (max 20 entries, wildcards)
   alongside 10 CIDR entries, with runtime firewall changes on Tier 3+ —
   the archived report's 5-CIDR/no-domain claim was stale/wrong, and the
   original "only E2B can express the allowlist" tiebreaker fell with it.
   The real margins: **concurrency headroom** (E2B purchasable to 1,100 vs
   Daytona Tier 4 ≈ 250 two-vCPU runs — bare A0 peak) and the **better
   public uptime record**. The decision holds, but the gap is thinner and
   the swap barrier lower than first written. Reopen: E2B refuses
   acceptable terms, or Daytona publishes a >500-vCPU tier. Lesson
   recorded: a decisive vendor-fact tiebreaker gets re-verified on
   contract day, not research day.
3. **Self-orchestrated Claude Code over Anthropic Managed Agents** —
   Managed Agents replaces the harness (no Claude Code, no plugins, no
   documented git-credential injection; an undocumented org concurrency
   cap that would have to be answered by Anthropic before committing any
   A0 traffic; skill auto-trigger semantics unverified against our tuned
   skills; beta harness churn; Claude-only fleet). Cost was a wash ($2.4k
   vs ~$3–4.5k at the same 30k run-hour basis; §3's $2.2–4.7k is the band
   across A0). Flip conditions, any one: (a) Managed Agents
   documents bring-your-own-harness or plugin support; (b) **Claude Code on
   the web ships a stable session-create API + published org quotas +
   API-key billing — the nearest flip, would be viable-now**; (c) GA + org
   caps + residency controls AND the human trades away the mixed-vendor
   review fleet (frozen-layer call); (d) a documented git-credential proxy
   for hosted sandboxes.
4. **Board service kept; Linear demoted to mirror** — at A0 Linear's rate
   limits genuinely fit (the enterprise disqualifier dissolves), but
   `issueUpdate` is schema-verified last-writer-wins with no transition
   enforcement; double-claims run ~5% at high A0; and "no service"
   re-materializes as dispatcher + guard bot + audit-export crons that
   still never provide atomicity. Linear-direct acceptable only under all
   seven conditions in the board report §6. Reopen: never expected;
   the service IS the enterprise architecture's first brick.
5. **Hand-written ~6-endpoint service over Supabase PostgREST+RLS** —
   human-confirmed. RLS would make policies load-bearing security code,
   claims need a server-side RPC anyway, and PostgREST couples the worker
   contract to Supabase. PostgREST remains a legitimate prototype path.
6. **Supabase over Neon (runner-up) and RDS (wildcard)** — always-on
   dedicated compute (no autosuspend to reason about), both pooling modes +
   direct connections, cheapest append-heavy disk. Neon wins if load turns
   genuinely bursty; RDS if the team goes AWS-native. Crunchy eliminated on
   acquisition-continuity risk (single-sourced — re-enters on an official
   continuity commitment); Fly MPG on price/maturity; Aurora Sv2 because
   auto-pause never fires under heartbeats; PlanetScale on $0.50/GB
   append-heavy storage economics; Railway/Render as SSOT on DIY-PITR
   posture (both remain fine hosts for the board-service process).
7. **Reconciler as cron over resident controller** — the enterprise
   re-judgment reverses below A1 tempo (our inference from its
   fleet-scale premises, not its text); batch cadence 1–5 min
   covers A0 with margin. Reopen at the §11 cron row's triggers.
8. **Axiom over Better Stack / Grafana Cloud / Honeycomb / Datadog / null
   option** — A0's whole volume fits Axiom's free tier; Datadog's
   per-million-event indexing makes it 5–30× at A0; the null option only
   wins on vendor-count minimalism and Axiom's $0 removes its cost case.
9. **Fly Machines rejected for compute despite lowest price** (~$0.9k) —
   no egress control, DIY image/log/capacity layers, and Jan 2026 15h+11h
   management-plane outages = mid-day dispatch stalls. Kept as a
   board-service host candidate only (control-plane outage there is
   survivable: workers fail closed).
10. **Provider quota treated as designed input** — post-review live
    verification replaced the 3rd-party "Tier-4 ITPM" framing: the binding
    meter is the monthly spend cap (Scale tier required from day one,
    Custom at A0-top); ITPM binds mainly for Fable-class-heavy mixes.
    The conversation is scheduled (adoption week 1–2, alongside
    contracts), not awaited.

## Surprises & Discoveries

- **The pressure order inverts infra instinct:** provider tier → sandbox
  bill → cron cadence → Postgres. The thing the enterprise spec designs
  hardest (the dispatch database) is the last thing a startup outgrows;
  the thing no infra document usually mentions — the provider's commercial
  tier, whose monthly spend caps bind long before ITPM does — fires first.
- **Two vendor facts moved between research morning and review evening**
  (Daytona's egress model; Anthropic's tier structure). Faithfully
  archived research disagreed with same-day live docs. Standing lesson:
  every vendor fact carries a verification date, and any decisive
  tiebreaker is re-checked on the day of contract.
- **Linear's no-CAS finding hardened from absence-of-evidence to
  schema-verified** — the full `IssueUpdateInput` field list contains no
  precondition of any kind. The enterprise round's caution became a fact.
- **The pooling footgun dissolved on inspection:** `FOR UPDATE SKIP LOCKED`
  is exactly the shape transaction pooling preserves; only LISTEN and
  session advisory locks need direct connections — a placement rule, not a
  constraint.
- **"No server" is an illusion at every scale examined:** dropping the
  board service re-materializes as three cron-shaped pieces that still
  cannot provide atomicity.
- **Nobody sells "your harness on our runtime"** — and the one product
  that runs our harness verbatim (Claude Code on the web) is blocked
  purely by its commercial/dispatch contract, not architecture. The
  compute slot has a named, watchable flip condition.
- **Token:infra at A0 is wider than the enterprise heuristic** (20–100×
  with E2B, up to 170× on cheaper substrates) — infra frugality is
  measurably the wrong place to spend attention at this scale.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-23: Initial version, from the five-report A0 research round and
  the grill-fixed frame (A0 anchor, named-stack deliverable, zero-ops
  posture, Stack M + hand-written board service human-confirmed).
- 2026-07-23 (later): external-review correction pass, all findings
  accepted after live re-verification. Decision-relevant: DL2 rewritten
  (Daytona's live docs show domain egress — tiebreaker is now concurrency
  headroom + uptime); acceptance drill 3 de-overclaimed (contents-scoped
  token can push unprotected branches; same repair applied to the
  enterprise spec's drill 6); §10 rewritten from the live rate-limits page
  (named tiers; monthly spend caps are the binding meter — Scale tier
  required from day one; cache-read ITPM exemption now officially
  confirmed; Fable-class ITPM caveat added). Coherence: token band
  relabeled $0.8–3/run; mirror budget restated as 10–60% of one actor;
  run-hour band 13–27.5k; storage bound tightened to ~150–630 GB/mo;
  assorted hedges restored.
