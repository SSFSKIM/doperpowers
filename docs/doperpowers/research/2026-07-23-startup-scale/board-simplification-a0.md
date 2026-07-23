# Board simplification at startup scale (A0) — can the custom board service be dropped?

Research date: 2026-07-23. Companion to the enterprise-scale analysis
(`../2026-07-23-cloud-scale/r2-ticket-store.md`) which disqualified both SaaS
trackers as ticket SSOT at 1,000 runs/hr/project. This report redoes that
analysis at a much smaller anchor and asks whether the whole board-service
tier can be deleted.

**Scenario A0** — 10–20 person startup, zero-ops mandate, $1–5k/month
infrastructure budget excluding tokens:

- ~50–200 concurrent runs, ~250–1,000 run starts/hour (system-wide, not
  per-project)
- Per run: 1 claim + ~3–6 state transitions + ~2–5 comments/verdicts
  → **~6–12 board writes/run**
- System write load: **~1,500–8,000 writes/hour**; with reads (ready-queue
  queries, claim polls, reconciles) total board traffic ≈ **3,000–16,000
  requests/hour**
- Writers: either one bot actor or per-run tokens

Semantic layer that must survive on whatever carrier is chosen (frozen, per
`2026-07-11-symphony-comparison.md`): ticket states including three park
states, pre-code gate, **atomic claim of ready tickets**, independent review
verdicts as a durable record.

---

## 1. Rate-limit math at A0

### 1.1 GitHub Issues / Projects v2

Limits re-verified 2026-07-23 against
https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api:

- Secondary (the binding one): **"No more than 80 content-generating
  requests per minute and no more than 500 content-generating requests per
  hour"** per actor. Issue creation, comments, label/state edits are all
  content-generating; the cap spans REST + GraphQL + web UI.
- Secondary points: 900 pts/min REST per endpoint (write = 5 pts → ~180
  writes/min to any single endpoint); GraphQL 2,000 pts/min.
- Primary: 5,000 req/hr per App installation (scales +50/repo and +50/user
  past 20, capped 12,500; 15,000 on Enterprise Cloud). GraphQL primary
  budget 5,000 pts/hr; a mutation costs ≥5 pts → ≤1,000 GraphQL
  mutations/hr per actor *before* secondary limits bite. Projects v2 is
  GraphQL-only, so it inherits both ceilings and changes nothing.
- Best practices (https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api):
  *"If you are making a large number of POST, PATCH, PUT, or DELETE
  requests, wait at least one second between each request"* and *"make
  requests serially instead of concurrently."* One serial actor pacing 1
  write/sec has a theoretical ceiling of 3,600 writes/hr — but the 500/hr
  content cap arrives long before that.

**The math.** One actor sustains ~500 writes/hr ≈ **~60 runs/hr** at 8
writes/run. A0 needs 1,500–8,000 writes/hr:

| A0 point | writes/hr | actors needed (at 500/hr each) |
|---|---|---|
| low (250 starts/hr) | ~1,500–3,000 | 3–6 |
| high (1,000 starts/hr) | ~6,000–12,000 | 12–24 |

**Can multiple machine actors legally multiply the budget?** Primary limits
are documented per-installation, so registering several genuinely distinct
GitHub Apps multiplies *primary* budgets by design. But the binding limit is
secondary, and its scoping is deliberately unpublished: community
investigation (devactivity.com; multiple org discussions) reports hidden
shared buckets across tokens of one app and across a shared IP. No GitHub
document found this session either blesses or forbids multi-app sharding of
the content-generating cap — but the cap is an anti-abuse control, and
structuring a fleet specifically to evade it is (a) unsupported, (b)
unreliable (buckets can merge without notice; limits "changeable without
notice"), (c) the same adversarial posture the enterprise analysis rejected.

**GitHub verdict at A0:** *fits* only below ~60 runs/hr on one actor —
under the A0 floor. *Fits with N bot actors* only at the very bottom of A0
(3–4 Apps on distinct IPs, per-actor throttles), fragile and adversarial.
*Doesn't fit* from mid-A0 up. GitHub as direct board SSOT is out even at
startup scale.

### 1.2 Linear

Limits re-fetched 2026-07-23 from https://linear.app/developers/rate-limiting:

- API key: "up to **5,000 requests/hour**" (note: the enterprise-round
  fetch of the same page read the limits table as 2,500/hr for API keys —
  the page carries both figures; plan on 2,500–5,000 and treat the exact
  number as a support question).
- OAuth app: **5,000 req/hr per actor** (user or App User), complexity
  2,000,000 points/hr. Small mutations cost tens of points — the request
  count binds, not complexity.
- **"We dynamically increase rate limits for workspace level OAuth apps
  using Actor Authorization based on number of paid users in that
  workspace"** — vendor-claimed, multiplier unpublished. At 10–20 paid
  seats this plausibly lifts the effective app budget, but it is not a
  number you can size against.
- Per-endpoint mutation caps exist ("some queries and mutations have
  individual request rate limits that are lower than the global request
  limit"), surfaced only via response headers, numbers unpublished. Support
  raises offered "case by case."
- Agent-era API surface (https://linear.app/developers/agents, fetched
  2026-07-23): agents authenticate as **app users** (`actor=app`), issues
  are *delegated* to agents (`delegateId` — present in `IssueUpdateInput`)
  while humans keep `assignee`. No agent-specific rate limits documented;
  no exclusivity or concurrency guarantee on delegation documented
  (absence of evidence).

**The math.** Total traffic 3,000–16,000 req/hr against 5,000/hr/actor:

| A0 point | total req/hr | one OAuth actor | with N actors |
|---|---|---|---|
| low (250 starts/hr) | ~3,000–6,000 | marginal — fits on average, no burst headroom | comfortable at N=2 |
| high (1,000 starts/hr) | ~12,000–24,000 | over 2.4–4.8× | fits at N=3–5 |

Unlike GitHub, multiplying actors is *inside* Linear's documented model:
limits are defined per actor, App-User actors are a first-class concept,
dynamic seat-based scaling is advertised, and support raises are the
documented escape hatch. Per-run tokens are also possible (each of 10–20
paid humans has an independent 5,000/hr budget), but machine writes under
human identities muddy the audit record — prefer 2–5 App-User actors.

**Linear verdict at A0:** *fits* at the low end with 1–2 actors; *fits with
N bot actors* (N=3–5, legitimately) across the whole A0 envelope. The
residual rate risk is the unpublished per-endpoint mutation caps — a load
test (or one support email) is mandatory before committing. This is a real
change from the enterprise verdict: **at A0, Linear's rate limits are not
the disqualifier.** What remains is correctness (§2).

---

## 2. Transition enforcement and atomic claim without a server

### 2.1 What exists in 2026 — verified

- **Linear has no compare-and-swap.** Upgraded this session from
  absence-of-evidence to schema-verified: the complete `IssueUpdateInput`
  field list was extracted from Linear's official SDK schema
  (`linear/linear` `packages/sdk/src/schema.graphql`, fetched 2026-07-23).
  Fields: `addedLabelIds, addedReleaseIds, assigneeId,
  autoClosedByParentClosing, cycleId, delegateId, description,
  descriptionData, dueDate, estimate, inheritsSharedAccess, labelIds,
  lastAppliedTemplateId, parentId, priority, prioritySortOrder, projectId,
  projectMilestoneId, releaseIds, removedLabelIds, removedReleaseIds,
  slaBreachesAt, slaStartedAt, slaType, snoozedById, snoozedUntilAt,
  sortOrder, stateId, subIssueSortOrder, subscriberIds, teamId, title,
  trashed, trusted`. **No `expectedUpdatedAt`, no version, no precondition
  of any kind.** `issueUpdate` is last-writer-wins. (`fromStateId` exists
  only in the read-only `IssueHistory` type / webhook `updatedFrom`
  payloads — forensics, not preconditions.)
- **Linear has no server-side transition restriction** (re-confirmed:
  nothing in docs, 2026 changelog, or schema; competitors advertise
  theirs). Still absence-of-evidence for the *feature's* nonexistence, but
  the schema now positively shows no input surface for it.
- **GitHub GraphQL has no precondition on issue/Projects mutations.**
  GitHub *does* ship CAS where it chose to (`updateRef` takes an expected
  OID; the contents API requires the blob SHA) — its omission from issue
  and ProjectV2 field mutations is a design choice, not a gap about to
  close. (Absence-of-evidence on any roadmap item.)
- **GitHub Projects v2 built-in automations** (docs fetched 2026-07-23):
  event-triggered status *setting* only (item added → Todo, PR merged →
  Done, auto-archive, auto-add). **No transition restriction capability of
  any kind.** Same class of hazard as Linear's PR automations: a second
  uncoordinated writer, must be disabled where they fight the pipeline's
  authority tiers.
- **Webhook/Actions guard bots** (revert illegal transitions after the
  fact) are reconciliation, not legality: the illegal state is live and
  dispatchable for the delivery+processing window (seconds for a Linear
  webhook consumer; ~tens of seconds to minutes for a GitHub Actions run),
  Linear drops a delivery after 3 failed retries (1 min / 1 hr / 6 hrs)
  with no ordering guarantee, so a guard can silently miss events — a
  periodic full poll is the required backstop. At A0 tempo this is
  *survivable* (illegal transitions are rare events caused by stale
  workers, and 10–20 humans can absorb the occasional anomaly), but it is
  detection, never prevention.

### 2.2 Collision math: the double-claim rate at A0

Without CAS, a claim is read-ready → write-claim → (optionally) verify. Let
λ = claim rate, w = effective race window (staleness of the claimant's view
of "ready" + write latency), R = ready tickets the picker chooses among
(uniformly at random). Per-claim collision probability ≈ λ·w/R.

- λ: 250/hr = 0.07/s (low A0) to 1,000/hr = 0.28/s (high A0).
- w: ~1–3 s event-driven; **~15 s mean under 30 s polling** (Symphony's
  default poll — polling multiplies every number below ~5–7×).
- R: 10–50 ready tickets in a healthy backlog.

| scenario | per-claim collision | double-claims |
|---|---|---|
| low A0, event-driven (w=2s, R=10) | ~1.4% | ~3–4/hr, dozens/day |
| high A0, event-driven (w=2s, R=10) | ~5.6% | ~50–60/hr |
| high A0, event-driven, deep backlog (R=50) | ~1.1% | ~11/hr |
| high A0, 30s polling (w=15s, R=10) | ~35–40% | catastrophic |
| any rate, deterministic top-of-queue pick (R_eff=1) | ~λw → up to ~43% | disqualified |

Three design consequences: (1) deterministic "everyone grabs the
top-priority ticket" pick order is disqualified without CAS — randomize the
pick; (2) polling-based claiming is disqualified at high A0; (3) even in
the best uncoordinated case, double-claims are a percent-level steady-state
event, not a freak occurrence — dozens per day.

**Idempotent-recovery pattern and its cost.** Because `issueUpdate` is
last-writer-wins, a *verify-after-write* protocol resolves every collision
deterministically: write the claim (set `assigneeId`/`delegateId` +
`stateId`), wait longer than the maximum write-settle skew (~5–10 s), read
back; if the final assignee is not you, abort. Exactly one winner survives.
Cost: +2 API requests and +5–10 s latency on **every** claim, plus one
wasted run start per collision (sandbox boot + orientation tokens,
~$0.05–0.50 and ~1 min each — $1–25/day at high A0, noise at low A0). The
real residual risk is not math but discipline: every worker version must
implement the protocol correctly forever; one stale client re-creates
duplicate PRs silently.

**The zero-infra serializer.** The collision rate goes to ~0 if claims are
assigned by a single serialized dispatcher instead of grabbed by workers —
Symphony's "one serializing authority" fiat, which is honest at A0's scale.
A zero-ops implementation exists on GitHub: a GitHub Actions workflow with
a `concurrency` group (runs serialize per group) that assigns ready tickets
to runs. Latency ~10–60 s per dispatch — acceptable at A0 tempo. But note
what happened: the "no server" option now contains a dispatcher, a guard
bot, and (for Linear's 90-day audit retention) a nightly history-export
job. Shape (a) does not eliminate infrastructure; it disperses it into
cron-shaped pieces that still cannot provide atomicity.

---

## 3. The middle option: the ~6-endpoint board service, zero-ops managed

The service from the enterprise spec §1 (claim / transition / comment /
park / query / reconcile; legal-transition graph as one conditional
UPDATE — `... WHERE id=$id AND state='ready-for-agent'`, rows-affected=0 =
lost race) is a few hundred lines over one Postgres schema. A0 load is
~1–4 TPS average — any managed tier holds it with 100× headroom. Verified
pricing (2026-07):

| platform | shape | $/month | notes |
|---|---|---|---|
| Fly.io | 1 shared-cpu machine + **Managed** Postgres Basic | ~$40–45 | MPG Basic $38/mo (shared-2x, 1 GB, HA, backups, pooling) + $0.28/GB storage; machine ~$2–5. Unmanaged Fly Postgres is ~$7/mo but makes you the DBA — not zero-ops. |
| Render | Starter web service + managed Postgres Basic | ~$15–25 | $7 service + ~$6 Postgres + $0.30/GB storage |
| Railway | Hobby + usage | ~$10–25 | community-measured real cost for small service + small Postgres |
| Cloudflare Workers + Neon | Workers Paid + Neon Launch (usage-based) | ~$10–20 | Workers $5/mo (10M req, 30M CPU-ms incl.; Hyperdrive included, unlimited queries on paid); Neon $0.106/CU-hr + $0.35/GB-mo, **no monthly floor** — at A0's trickle likely $5–15 |

Operational demand honestly stated: initial build ~1–2 days (the schema and
endpoint list are already specced); then git-push deploys, occasional
migrations, a quarterly backup-restore drill, free uptime monitoring, secret
rotation — **~2–4 hours/month**. Every option above includes managed
backups; board unreachability is survivable because workers fail closed and
humans still see the tracker mirror. Against a $1–5k/month budget the dollar
cost is 1–4% of budget floor — less than one Linear Business seat
($16/user/mo).

The Linear mirror sync (one-way, coalesced to human-relevant transitions
only — ~2–3 of the ~8 writes/run) adds ~100–200 LOC and runs at hundreds of
Linear writes/hour system-wide: inside a *single* OAuth actor's budget with
10× headroom, with zero per-endpoint-cap anxiety.

---

## 4. Weighing the three shapes at A0

**(a) SaaS tracker (Linear) direct as SSOT.** Rate-feasible (§1.2) — the
first shape change vs enterprise scale. Humans get their daily UI natively;
zero deployed services. But the semantic layer runs degraded: no atomic
claim (percent-level double-claims + verify-after-write on every claim, or
a serializing dispatcher), no transition legality (guard-bot reconciliation
with live illegal windows and droppable webhooks), 90-day audit retention
vs the permanent human-answer record (nightly export job required), Linear's
own GitHub PR automations must be disabled per team, and the unpublished
per-endpoint mutation caps hang over the whole design. Each mitigation is
itself a small piece of infrastructure — dispatcher + guard + export ≈ three
cron jobs that still never add up to atomicity. Migration cost later: full
data-model migration off Linear *plus* retraining every worker protocol
onto new endpoints — the expensive kind of migration.

**(b) Thin board service (managed PaaS) as SSOT + Linear as human mirror.**
$10–45/mo and ~2–4 hrs/mo buys: server-side transition legality and atomic
claim (the two things no SaaS tracker sells at any price), permanent
append-only history, no rate-limit exposure on the machine path (the mirror
uses <10% of one Linear actor), and the humans keep 100% of the Linear UX.
Migration to the enterprise architecture is near-zero: this *is* the
enterprise board service (§1 of the reference spec) on a smaller box; the
enterprise step is re-hosting the same schema next to the dispatch plane's
Postgres, not a redesign.

**(c) Board service only, no tracker.** Saves the ~150-LOC mirror and the
Linear seats, but 10–20 humans need a good daily surface, and building even
a mediocre board UI dwarfs everything else in this report. Rejected.

---

## 5. Verified vs vendor-claimed vs absence-of-evidence

**Verified this session (primary source fetched/extracted):**
- GitHub secondary limits (80/min, 500/hr content-generating; 900 pts/min;
  100 concurrent) and App primary limits — official docs.
- GitHub best-practices serial/1-second-spacing guidance — official docs.
- Projects v2 automations = status-setting only, no restriction — official docs.
- Linear OAuth 5,000 req/hr/actor, 2M pts/hr, support-raise clause, dynamic
  seat scaling sentence — official page.
- **Linear `IssueUpdateInput` has no precondition field** — full field list
  from the official SDK GraphQL schema (strongest new evidence in this
  report).
- Linear agent delegation model (`actor=app`, `delegateId`) — official docs.
- Hosting prices: Fly MPG $38 Basic, Workers $5 paid plan w/ Hyperdrive,
  Neon Launch usage rates — official pages; Render/Railway figures from
  2026 third-party comparisons (medium confidence).

**Vendor-claimed, unverifiable in advance:**
- Linear's dynamic seat-based limit scaling (no multiplier published).
- Linear support limit raises ("case by case").
- Linear per-endpoint mutation caps' actual values (headers-only).

**Absence-of-evidence (flagged, not proven):**
- No Linear server-side transition restriction: no docs/changelog/schema
  surface found through 2026-07; no official "unsupported" statement either.
- No exclusivity/concurrency guarantee on Linear agent delegation.
- GitHub secondary-limit bucketing across apps/IPs: community-documented
  shared hidden buckets; GitHub publishes nothing either way and reserves
  the right to change without notice.
- No published GitHub statement blessing or forbidding multi-app sharding
  of secondary limits (no ToS clause was verified this session).

**Contradiction to record:** Linear's rate-limit page was read as
2,500/hr-per-API-key (table) in the enterprise round and 5,000/hr (prose)
today, same day. Both readings are of the same live page. Resolve by email
to Linear support if any Linear-direct path is pursued; all A0 conclusions
above survive either number because OAuth actors (unambiguously 5,000) are
the recommended path.

---

## 6. Verdict

**Shape (b): keep the thin board service — as a $10–45/month managed
deployment — as ticket SSOT, with Linear as the human-facing mirror. A0
does NOT justify dropping the tier.**

The reasoning inverted but the answer held: at enterprise scale the SaaS
trackers failed on *rate limits and* correctness; at A0 the rate-limit
disqualifier genuinely dissolves (Linear fits with 1–5 legitimate actors),
so the decision rests purely on the semantic layer — and there the facts
are unchanged and now schema-verified: no CAS, no transition enforcement,
90-day audit horizon. The "simplification" of shape (a) is largely an
illusion: it re-materializes as a serializing dispatcher + guard bot +
export cron (three pieces of un-atomic infrastructure), while shape (b)
costs less per month than one Linear seat, takes 1–2 days to stand up from
an already-written spec, and is itself the first brick of the enterprise
architecture rather than a migration liability.

**Swap conditions — when Linear-direct (shape a) is acceptable at A0:**
all of: (1) the team hard-refuses any deployed service; (2) sustained rate
stays in low-A0 (≲250 starts/hr, ≲3,000 writes/hr); (3) claims are
serialized through exactly one dispatcher (e.g. a GitHub Actions
concurrency-group assigner) — never uncoordinated worker grabs; (4)
verify-after-write is in the worker protocol anyway (defense in depth);
(5) a nightly issue-history export covers the 90-day audit horizon;
(6) Linear's GitHub PR automations are disabled per team; (7) one load test
or support confirmation clears the per-endpoint mutation caps.

**Growth thresholds where the board service becomes mandatory (any one):**
- Sustained board writes > ~4–5,000/hr (2 Linear actors' worth) or bursts
  that per-endpoint caps clip — approximately >1,000 starts/hr, i.e. the
  A0→A1 boundary;
- More than one dispatcher process needed (multi-project or HA dispatch) —
  the serialization fiat breaks and only CAS closes the claim race;
- The audit/compliance requirement hardens (the permanent human-answer
  record stops tolerating an export-job reconstruction);
- Adoption of the enterprise dispatch plane (same-transaction claim+mirror
  rows, reference spec §2) — which requires the board rows to live in your
  own Postgres by construction.

**Biggest uncertainty:** Linear's unpublished per-endpoint mutation caps —
the only number that could retroactively break even the low-A0 Linear-direct
fallback, and it is untestable except by load test or support disclosure.
Second: GitHub secondary-limit bucket scoping (moot under the verdict, since
GitHub is out as SSOT at every scale examined).

---

## Sources

- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api — secondary limits (80/min, 500/hr content-generating), App primaries (fetched 2026-07-23)
- https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api — serial requests, 1 s between mutations (fetched 2026-07-23)
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations — Projects v2 automations (fetched 2026-07-23)
- https://devactivity.com/insights/navigating-github-s-secondary-rate-limits-a-community-call-for-clarity-on-git-productivity-tools/ — hidden shared secondary buckets (community)
- https://linear.app/developers/rate-limiting — Linear limits, dynamic seat scaling, support raises (fetched 2026-07-23)
- https://raw.githubusercontent.com/linear/linear/master/packages/sdk/src/schema.graphql — official SDK schema; full `IssueUpdateInput` extraction (fetched 2026-07-23)
- https://linear.app/developers/agents — agent auth (`actor=app`), delegation semantics (fetched 2026-07-23)
- https://linear.app/changelog/2026-06-11-coding-sessions — Linear's own agent coding sessions (context)
- https://linear.app/developers/webhooks — 3-retry drop policy, no ordering (via r2, same-day)
- https://linear.app/docs/audit-log — 90-day retention (via r2, same-day)
- https://fly.io/docs/mpg/ and community pricing threads — Managed Postgres Basic $38/mo
- https://developers.cloudflare.com/workers/platform/pricing/ — Workers Paid $5/mo, Hyperdrive included (fetched 2026-07-23)
- https://expresstech.io/render-vs-railway-vs-fly-io-2026-pricing-showdown/ , https://northflank.com/blog/railway-vs-flyio , https://dev.to/pavel-hostim/render-vs-railway-vs-flyio-pricing-compared-2026-2e5p — 2026 PaaS pricing comparisons (third-party)
- https://vela.simplyblock.io/articles/neon-serverless-postgres-pricing-2026/ , https://www.saaspricepulse.com/tools/neon — Neon Launch usage pricing (third-party)
- Internal: `docs/doperpowers/research/2026-07-23-cloud-scale/r2-ticket-store.md`, `docs/doperpowers/2026-07-23-cloud-scale-research.md` §7.1, `docs/doperpowers/specs/2026-07-23-cloud-scale-reference-architecture-design.md` §1, `docs/doperpowers/2026-07-11-symphony-comparison.md`
