# R2 — Ticket SSOT at scale, and where the transition graph lives

Research date: 2026-07-23. Target load (from brief): hundreds–thousands of
implementer+reviewer runs/hour/project, ~10 board ops/run. Working number used
throughout: **1,000 runs/hr/project × 10 ops = 10,000 board ops/hr/project**,
of which roughly 60% are writes (claim, state transitions, comments as the
durable human-answer record) → **~6,000 writes/hr, ~100/min average, with
bursts well above that** (dispatch waves are bursty, not smooth).

---

## 1. Findings per question

### 1.1 Linear as board SSOT

**Rate limits** (official: https://linear.app/developers/rate-limiting, fetched 2026-07-23):

| Auth mode | Requests/hr | Per | Complexity points/hr |
|---|---|---|---|
| API key | **2,500** | user | 3,000,000 |
| OAuth app | **5,000** | user (or App User) | 2,000,000 |
| Unauthenticated | 600 | IP | 100,000 |

- Max complexity of a single query: **10,000 points**.
- "Some queries and mutations have individual request rate limits that are
  lower than the global request limit" — per-endpoint limits exist and are
  surfaced only via `X-RateLimit-Endpoint-*` response headers; the numbers are
  not published.
- Escape hatch, quoted: *"If you temporarily require higher limits, you can
  request them by contacting Linear support where we'll review them on a case
  by case basis."*
- Note: prose elsewhere on the page says "up to 5,000 requests per hour" for
  API keys, but the limits table says 2,500/user for API-key auth and 5,000
  for OAuth. Plan against the table (conservative).

**Webhooks** (official: https://linear.app/developers/webhooks):
- Retry policy: **3 retries** on failure, at **1 minute, 1 hour, 6 hours**.
  Failure = non-200, or consumer response slower than **5 seconds**.
  Persistently unresponsive webhooks *may be disabled by Linear*.
- Dedupe: `Linear-Delivery` UUID header uniquely identifies each payload
  (consumer-side idempotency is possible); HMAC-SHA256 `Linear-Signature`.
- **No ordering guarantee is documented.** No explicit at-least-once
  guarantee either — after 3 failed retries the event is dropped. So webhooks
  alone cannot be a correctness-bearing sync channel; a periodic full poll
  (`sort by updatedAt`, filtered) is required as backstop. Payloads do include
  `updatedFrom` (previous values on updates), which is useful for a
  reconciliation validator.
- Supported entities cover what we need: Issues, Comments, Labels, Projects.

**Workflow states & transition enforcement:**
- States are per-team objects with a `type`
  (triage/backlog/unstarted/started/completed/canceled); fully customizable —
  our park states (needs-human / needs-info / interactive-preferred) map to
  custom states or labels cleanly (https://linear.app/docs/configuring-workflows).
- `issueUpdate(input: { stateId })` accepts **any** stateId belonging to the
  team. **No server-side legal-transition restriction feature exists anywhere
  in Linear's docs or API schema** — unlike Jira workflows, Azure DevOps state
  rules, or Plane's workflow-transition permissions, which all advertise it.
  (Confidence: high, but this is an absence-of-evidence finding — see §4.)
- No optimistic-concurrency / compare-and-swap on `issueUpdate` — there is no
  "update only if current state is X" primitive. Claim races between 1000s of
  writers cannot be resolved *at* Linear.

**Audit/history:** `auditEntries` GraphQL query with filtering by type/actor;
audit log retained **90 days**, streamable to a SIEM webhook; available on
Plus/Enterprise plans (https://linear.app/docs/audit-log). Issue-level
`history` connection exists for per-issue state-change forensics.

**Bulk ops:** `issueBatchUpdate` mutation exists (multiple issues, one
request). Community sources report batch tools capped at **50 issues per
call** (matches the native bulk-UI limit); official docs do not publish the
cap — verify empirically before relying on it.

**Enterprise SLA:** the Enterprise plan lists an **uptime SLA** plus SAML/SCIM,
audit log, priority support; terms are custom/sales-gated, no public number
(https://linear.app/pricing). Business is $16/user/mo — relevant because
rate limits are **per user/actor**, so "more actors" = more paid seats or an
OAuth app with app-actors.

### 1.2 GitHub Issues at the same load

Official: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
and https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api.

**Primary limits:** PAT user 5,000 req/hr; GitHub App installation 5,000
base, +50/repo and +50/user beyond 20, capped **12,500/hr**; Enterprise
Cloud-owned apps **15,000/hr**. GraphQL: 5,000 pts/hr (10,000 Enterprise
Cloud); plain query = 1 pt, **mutation = 5 pts** minimum.

**Secondary limits (the real ceiling) — quoted:**
- *"No more than 80 content-generating requests per minute and no more than
  500 content-generating requests per hour."* Issue creation, comments, and
  most issue edits are content-generating; the limit spans web UI + REST +
  GraphQL. Some endpoints have *lower* unpublished limits.
- No more than **900 points/min** per REST endpoint (write = 5 pts → ~180
  writes/min to any one endpoint, e.g. create-comment).
- No more than **100 concurrent requests** across REST+GraphQL; GraphQL
  additionally capped at 2,000 pts/min.
- Secondary limits are explicitly abuse-prevention, undocumented in full, and
  changeable without notice.

**Where it breaks first:** the **500 content-generating requests/hour per
actor**. Our ~6,000 writes/hr/project is **12× over** that per-actor cap —
hit long before the 5,000/hr primary limit. The 80/min burst cap bites even
sooner during dispatch waves.

**Is app-per-project sharding viable?** Primary limits shard cleanly per
installation. But secondary limits do not shard reliably: community
investigation (devactivity.com writeup, GitHub community discussions) reports
hidden shared buckets — multiple tokens from the same app, or traffic from
the same IP, can share one secondary-limit bucket, and GitHub does not
publish the bucketing. To clear 6,000 writes/hr you'd need **≥12 fully
independent actors per project** with per-actor client-side throttling to
≤80/min and ≤500/hr each, and hope the hidden buckets don't merge them.
That is an adversarial posture against your own SSOT vendor's abuse system.
Projects v2 (GraphQL-only: `ProjectV2`, field mutations) adds board views
but every mutation still spends the same GraphQL/secondary budgets — it
changes nothing about the ceiling.

### 1.3 Third option: thin self-owned board service

**Prior art — OpenAI Symphony** (spec: https://github.com/openai/symphony/blob/main/SPEC.md,
announcement https://openai.com/index/open-source-codex-orchestration-symphony/, May 2026):
- Symphony v1 makes the **tracker (Linear) the source of truth**; the
  reference orchestrator (Elixir) keeps only in-memory scheduling state
  (`running`, `claimed`, `retry_attempts`, `completed`) and recovers by
  re-polling — *"Support tracker/filesystem-driven restart recovery without
  requiring a persistent database."*
- Tracker adapter interface is deliberately thin: `fetch_issues_by_states`,
  `fetch_issues_by_ids` as first-class reads; *"Ticket mutations (state
  transitions, comments, attachments, PR metadata) are typically handled by
  the coding agent through the selected adapter's provider-native tools."* —
  i.e., **enforcement is client-side, in the agent**, exactly our current
  pattern.
- Concurrency is solved by fiat: *"The orchestrator serializes state
  mutations through one authority to avoid duplicate dispatch."* — **a single
  orchestrator process. No distributed claiming protocol is specified.**
  Polling default 30 s; rate limits are tracked for observability only.
- Reported result: internal teams saw landed PRs +500% in three weeks
  (InfoQ/press coverage) — but nothing in the spec addresses our scale tier;
  Symphony's answer to 1000s of concurrent writers is "don't have them —
  funnel through one process."
- Takeaway: Symphony *validates the shape* (tracker as human-facing control
  plane, orchestrator owns scheduling, agent does mutations) and
  simultaneously demonstrates the gap: at multi-orchestrator, multi-thousand-
  writer scale, "one serializing authority" must become a real service with a
  real database — which is exactly the thin board service.

**Jira for comparison** (https://developer.atlassian.com/cloud/jira/platform/rate-limiting/,
https://www.atlassian.com/blog/development/evolving-api-rate-limits): moving
to a points-based hourly quota model (phased enforcement from **March 2,
2026**; REST first, GraphQL later): cost scales with work (a 50-issue search
≈ 51 points; **writes ≈ 1 point**), plus per-second burst limits, with tiered
quotas (Tier 1 shared across tenants; Tier 2 per-tenant per-app by request).
Even the biggest incumbent tracker is tightening, not loosening — betting
the SSOT on any SaaS tracker's rate policy is betting on a moving target.

**Postgres capacity check:** a transition op is one row UPDATE with a
condition + one history INSERT. 10,000 ops/hr/project = **~3 TPS average per
project**; even 100 projects with 10× bursts is a few thousand TPS — small
single-node Postgres territory. Throughput is a non-issue; the design
questions are only schema and mirror fidelity.

### 1.4 Where does transition-graph enforcement live?

Three placements, with real-world anchors:

**(a) Client-side (every worker checks)** — our today. Works only while
writer count is small and homogeneous. Two structural failures at scale:
(1) **TOCTOU claim races** — neither GitHub Issues nor Linear offers
conditional update / CAS on issue state, so "read state, verify legal, write"
has an unclosable race window; with 1,000 runs/hr the double-claim rate stops
being theoretical. (2) **Enforcement drifts with the client fleet** — every
harness/version must carry an identical copy of the graph; one stale worker
corrupts the board silently. Symphony dodges this only via its single-process
serialization assumption (§1.3).

**(b) Server-side (API service owns the graph)** — the Kubernetes precedent.
The API server is the single enforcement point: writes carry
`resourceVersion`; a stale write is rejected with **HTTP 409 Conflict** and
the client must re-fetch and retry
(https://kubernetes.io/docs/reference/using-api/api-concepts/). Admission
control validates *before* persistence. In Postgres terms:
`UPDATE ticket SET state='in-progress', owner=$run WHERE id=$id AND state='ready-for-agent'`
— rows-affected=0 *is* the legality check and the claim lock in one atomic
statement. This is the only placement where an illegal state is never
observable.

**(c) Reconciliation (webhook validator reverts illegal writes)** — the
controller pattern *misapplied*. Kubernetes controllers reconcile toward
desired state, but Kubernetes still enforces *legality* synchronously at the
API server; reconciliation handles convergence, not validity. A
webhook-driven reverter over Linear/GitHub has: an open window where the
illegal state is live (workers dispatch off it — duplicate/ghost runs), no
ordering guarantee on the webhook stream (Linear documents none), and event
loss after 3 failed retries (Linear drops the delivery). Reconciliation is
the right tool for the **mirror back-edge** (absorbing human edits made in
the tracker UI), not for the legality gate.

### 1.5 PR coupling (flag)

PRs/merges stay on GitHub regardless of ticket store. Linear's GitHub
integration (https://linear.app/docs/github) auto-links PRs via issue ID in
branch name / PR title / magic words ("Fixes ENG-123"), and runs **its own
per-team state automations**: PR opened → In Progress, merged → Done,
configurable per branch; GitHub Enterprise Cloud (*.ghe.com) has full parity,
GitHub Enterprise Server only partial (no issue sync; magic words limited to
PR descriptions). **Coupling hazard:** these automations are a second,
uncoordinated writer of ticket state. If Linear is SSOT, its own PR
automation can fire "merged → Done" while our semantic layer requires
in-review → landed via the review worker's tiered merge authority — a direct
fight over the frozen semantics. If Linear is a display mirror, the
automations must be disabled per team (they are configurable) or the mirror
sync must treat Linear-originated state changes as advisory events, never as
truth. Also note: multiple PRs on one issue only trigger the merged
automation on the *final* PR — wrong for decomposed child-ticket flows.

---

## 2. The load math

Per project: 10,000 ops/hr, ~6,000 writes/hr, bursts ≥3× average.

| Option | Binding limit | Our load vs limit | Verdict |
|---|---|---|---|
| GitHub, one App installation | 500 content-writes/hr, 80/min (secondary) | 6,000/hr → **12× over**; bursts blow 80/min immediately | Breaks first at content creation, not primary limits |
| GitHub, app-per-project shards | Same secondary caps per actor; hidden shared buckets (IP/app-level) documented by community, not by GitHub | Need ≥12 independent actors/project + per-actor throttles; sharding not guaranteed to multiply secondary buckets | Fragile; adversarial to vendor abuse controls |
| Linear, one OAuth app-actor | 5,000 req/hr/actor | 10,000/hr → **2× over**; complexity budget (2M pts/hr) not binding for small mutations | Close but over; no burst headroom |
| Linear, sharded (2–3 actors/project or teams-as-shards) + `issueBatchUpdate` | 5,000/hr × N actors; unpublished per-endpoint mutation limits; support can raise limits "case by case" | Fits with 2–3 actors *if* per-endpoint limits cooperate — unverifiable in advance | Feasible on paper; correctness (no CAS, no transition enforcement) still unsolved |
| Thin board service (Postgres) + mirror | Postgres: ~3 TPS avg/project vs thousands of TPS on one node. Mirror to Linear: ≤1 batched write per *human-relevant* transition, coalesced → hundreds/hr, ~10% of one actor's budget | **≥100× headroom** on SSOT; mirror comfortably inside Linear limits | Only option where both throughput and correctness close |

Key insight from the math: workers make ~10 ops/run but humans only care
about ~2–3 of them. Any mirror architecture that coalesces machine-tempo
writes into human-tempo updates shrinks tracker traffic by ~5–10× before
sharding is even discussed.

---

## 3. Recommendation

**Thin self-owned board service as ticket SSOT; Linear as the human-facing
mirror; GitHub keeps PRs. Transition-graph enforcement moves server-side
into the board service.**

The board service is small: Postgres, a ~6-endpoint API
(claim / transition / comment / park / query / reconcile), the legal-transition
graph enforced as conditional UPDATEs (atomic legality-check + claim-lock,
K8s-style 409 on conflict), append-only history table (permanent — beats
Linear's 90-day audit retention, which alone is disqualifying for an SSOT
carrying the durable human-answer record). Round-1's finding makes this
cheaper than it sounds: run liveness lives in the durable-execution engine,
so this service stores *ticket* state only — it is a state machine over rows,
not an orchestrator. A one-way sync worker mirrors human-relevant transitions
to Linear (batched, coalesced); a webhook+poll back-edge ingests
human actions in Linear (park-state answers, priority edits) as *events into*
the board service, which remains the only writer of record. Linear's own
GitHub PR automations get disabled per team; PR linkage stays via branch-name
convention (works identically from the board service's ticket IDs).

| Criterion | Linear as SSOT (sharded) | GitHub sharded apps | Thin service + Linear mirror |
|---|---|---|---|
| Fits 10k ops/hr/project | Marginal (2–3 actors + batching + support ticket) | No (12× over content cap; hidden buckets) | Yes, ≥100× headroom |
| Server-side transition enforcement | **None exists** | **None exists** | Native (conditional UPDATE) |
| Atomic claim (no double-dispatch) | No CAS primitive | No CAS primitive | Yes (rows-affected=0 ⇒ lost race) |
| Burst tolerance | Per-actor hourly buckets, unpublished endpoint caps | 80/min hard wall | Postgres; ours to size |
| Audit/history | 90-day audit log (Plus+); issue history | Timeline events | Append-only, retained forever |
| Human UX | Best-in-class, free | Familiar | Linear mirror = same UX, slightly stale (seconds) |
| Multi-writer correctness under vendor rate-limiting | Enforcement still client-side → drift | Same, plus abuse-system roulette | Single enforcement point, versioned once |
| Ops burden | None | None | One small service + sync worker (real, but tiny; no run-liveness state) |
| Prior-art alignment | Symphony v1 (single orchestrator only) | Community Symphony ports | Symphony's "one serializing authority" made explicit and durable; K8s API-server pattern |

The counterargument to the thin service is "you're rebuilding a tracker."
We are not: the mirror keeps Linear as 100% of the human surface. The service
owns exactly the two things no SaaS tracker sells at any price — **server-side
enforcement of our legal-transition graph** and **atomic claims for thousands
of concurrent machine writers** — which is precisely the frozen semantic
layer's carrier. That the semantic layer stays frozen is *because* its
enforcement stops depending on every client getting it right.

Fallback noted for completeness: if the org refuses to run any service,
Linear-as-SSOT with 2–3 OAuth actors per project, batched mutations, a
support-negotiated limit raise, and a webhook reconciliation *detector*
(alert on illegal transitions, don't auto-revert) is survivable at the low
end of the target range — with the double-claim race accepted as a cost.

---

## 4. Confidence notes — what I could not verify

- **Linear per-endpoint mutation limits**: existence confirmed by official
  docs and headers; the actual numbers are unpublished. Whether
  `issueUpdate`/`commentCreate` throttle below 5,000/hr under sustained
  machine load is unknowable without a load test. This is the single biggest
  unknown in the Linear-as-SSOT fallback.
- **Linear "no transition restriction" is an absence-of-evidence finding**:
  no docs page, changelog entry, or schema field for restricting transitions
  was found (competitors advertise theirs). I could not find an official "we
  don't support this" statement.
- **`issueBatchUpdate` 50-issue cap**: from community/third-party sources,
  not official docs.
- **GitHub secondary-limit bucketing** (shared hidden buckets across tokens
  of one app / one IP): community-documented (devactivity.com, org
  discussions), explicitly *not* documented by GitHub; GitHub reserves the
  right to change these without notice — which cuts both ways.
- **Linear Enterprise uptime SLA number**: the pricing page lists "uptime
  SLA" as an Enterprise feature; the actual percentage is sales-gated.
- **Symphony production scale**: the +500% landed-PRs figure is press-relayed
  from OpenAI; no per-hour run-rate or Linear rate-limit incident data is
  public. Whether OpenAI internally hit Linear limits and how they handled it
  is not disclosed.
- The Linear rate-limit page's prose (5,000/hr API key) contradicts its own
  table (2,500/hr); I planned on the table. Worth an email to Linear support
  if the fallback is ever pursued.

## 5. Sources

- https://linear.app/developers/rate-limiting — Linear rate limits (fetched 2026-07-23)
- https://linear.app/developers/webhooks — Linear webhook retries/dedupe/timeout
- https://linear.app/docs/configuring-workflows — Linear workflow states
- https://linear.app/docs/audit-log — audit log, 90-day retention, `auditEntries`
- https://linear.app/docs/github — GitHub integration, PR automations
- https://linear.app/pricing — Enterprise plan (uptime SLA, SCIM), Business $16/user/mo
- https://github.com/linear/linear/issues/1087, /issues/210 — batch mutation requests/limits (community)
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api — REST primary/secondary limits
- https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api — GraphQL points, 2,000 pts/min
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/rate-limits-for-github-apps — App installation scaling
- https://devactivity.com/insights/navigating-github-s-secondary-rate-limits-a-community-call-for-clarity-on-git-productivity-tools/ — hidden shared secondary buckets (community)
- https://github.com/openai/symphony/blob/main/SPEC.md — Symphony spec (tracker adapter, serialization, recovery)
- https://openai.com/index/open-source-codex-orchestration-symphony/ — Symphony announcement (May 2026)
- https://betterstack.com/community/guides/ai/openai-symphony/ — Symphony config walkthrough (states, polling, PR hook)
- https://www.infoq.com/news/2026/05/openai-symphony-agents/ — Symphony coverage (+500% landed PRs)
- https://developer.atlassian.com/cloud/jira/platform/rate-limiting/ — Jira points model
- https://www.atlassian.com/blog/development/evolving-api-rate-limits — Jira/Confluence quota tiers, March 2, 2026 enforcement
- https://kubernetes.io/docs/reference/using-api/api-concepts/ — resourceVersion optimistic concurrency, 409 Conflict
