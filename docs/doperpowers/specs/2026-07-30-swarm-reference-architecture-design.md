# Swarm Reference Architecture — One Architecture, Knob-Set Tiers (2026-07-30)

> **What this is.** The synthesis spec closing the 2026-07-30 clean-slate
> research round (`docs/doperpowers/research/2026-07-30-clean-slate/`,
> reports r1–r4 + probes p1–p4). It is the **successor to both 2026-07-23
> specs** — `2026-07-23-cloud-scale-reference-architecture-design.md`
> (enterprise) and `2026-07-23-startup-scale-a0-design.md` (A0) — which
> remain citable design history but no longer describe the current
> architecture. Authored interactively with the human partner; the three
> open forks the round queued were settled by the human in this session
> (Decision Log).
>
> **Citation discipline:** this spec cites the round reports rather than
> re-deriving them (read-once-then-cite). Where a claim below carries no
> inline evidence, the named report section does.

## Purpose

One system runs autonomous agent swarms end to end: tickets are born on an
AI-native Postgres board, workers execute them inside sandboxed Kubernetes
pods running the cc-harness (Claude Agent SDK harness), humans steer
through a control plane, and an agent — not a human — operates the
infrastructure. After this spec, someone standing up the platform does not
choose between a "startup" design and an "enterprise" design: **there is
one architecture, and scale is expressed as knob values.** The 2026-07-23
program maintained two parallel specs because the ops cost of self-hosting
was priced as a human engineer; the clean-slate round removed that constant
(agent-ops ≈ $150/mo, flat in volume — `r4-economics.md` §7) and the
round's four sequenced, non-circular evidence bases each found no fork at
its own layer — the single-architecture answer (`r1` §3, `r2` §7,
`r3` §6.2, `r4` §10).

**Terms of art.** *cc-harness*: the Claude Agent SDK harness co-designed
with this platform (repo `CC-to-SDK`). *Run*: one worker session bound to
one ticket claim. *Run-class*: the lane-derived profile (implement /
research / review / ops) that selects a pod's egress policy and
credentials. *Park*: a worker's blocking question, addressed to the human
queue (board park) or an SDK decision (appserver park). *Turn*: one model
API round-trip; the engine writes transcripts only at turn boundaries.
*MTTR spike*: the gated ops experiment of `r3-agent-ops.md` §5 — distinct
from the board's `spike` lane (exploratory tickets). *Agent
Sandbox*: the `kubernetes-sigs/agent-sandbox` CRDs
(SandboxTemplate / SandboxWarmPool / SandboxClaim / Sandbox).

## 1. The through-question verdict and the knob list

**One architecture; tiers are knob values.** The same manifests, the same
CRDs, the same board schema, the same harness binary, and the same ops
framework deploy at every scale. The knobs:

| # | Knob | A0 value | Enterprise value | Owner |
|---|------|----------|------------------|-------|
| K1 | Discount instrument | **Spot** on the sandbox pool (duty cycle ~30% fails every CUD break-even; preemption costs ≤1 turn) | 3-yr resource CUD on baseline + Spot on burst | `r4` §9.1 |
| K2 | Warm-pool size | small (≈5–16), near-free on Standard node headroom | sized to lane concurrency caps | `r2` §2 |
| K3 | Run-class egress profile | credential-aligned 3-layer (§3.2) | same + optional hardening (proxy attenuator, srt inner layer) | this spec, DL-4 |
| K4 | Ops runbook catalog | Standard catalog (T1–T7 taxonomy) | larger catalog; at ≥2 clusters, cross-watch | `r3` §6.2 |
| K5 | Architect-lane concurrency cap | set from a **cost target** (Fable run ≈ 5× a Sonnet run; a 5-point share move ≈ $34k/mo at A0-mid) | same mechanism, larger budget | `r4` §6.3 |
| K6 | Execution sidecar | none (virtual keys + gVisor + egress substitute) | deferred option: two-container sidecar on the push-credential implement class, exercisable only once T14 (§2) exists | governing principle; DL-12 |

**Cluster mode is not a knob.** GKE Standard + Dataplane V2 + gVisor node
pools is the default at BOTH tiers. Autopilot is retired as a tier and
kept as **break-glass**: if the agent-ops spike fails its promotion bar,
Autopilot is the managed-ops purchase — same manifests, zero switching
cost (DL-2). One purchase-console fact rides the break-glass option and
stays open: whether Autopilot resource CUDs are still purchasable
(`r2` §8.9; corroborated but not closed by `r4` §11.5). Self-managed
bare metal stays gated closed (DL-8).

The strongest form of the one-architecture result is economic: the managed
alternative's bill is linear in volume while the agent-ops term is flat,
so the architecture's advantage **compounds with scale** (`r4` §10).

## 2. Runtime layer — cc-harness worker pods

One pod = one accountable worker = one harness session. The substrate for
this already exists and is largely proven (`r1` §0.1); what follows are
the design commitments layered on it.

**Decoupling boundary (envelope asymmetry, applied).** Read/Write/Edit/
Grep/Glob and foreground Bash never leave the pod — the transcript mirror
itself assumes engine and SDK parent share a filesystem (`r1` §1C). Two
tool families decouple: **Task above the durability threshold** becomes
`DetachedTask` (spawns `ccx --bg`: own session id, own top-level
transcript — `p2` §3), and **background Bash above the lifetime
threshold** becomes a detached spawn or a board ticket. Everything else
is blast-radius isolation (gVisor, optionally srt), not per-call
containers. **Placement rule:** a `DetachedTask` child runs *in the
parent's pod* and therefore survives parent-*process* death only — the
shape P2 verified live; work that must survive the *pod* goes through
the board instead: a child ticket claimed onto its own pod, with its own
credentials and egress class. In-pod detached children remain
subordinate sessions of the pod's one accountable worker
(subagents-never-write unchanged), so DL-6's tenancy model holds.

**The turn-durability ceiling.** The engine writes transcripts only at
turn boundaries; a pod evicted mid-turn loses the in-flight turn in any
store, and in-memory SDK parks die with the process (`p2` §4, engine-owned,
unfixable from outside). Design-arounds are platform config: SIGTERM grace
≥ turn close, small turns, idempotent re-dispatch, and park mirroring
(T5). This ceiling is also why Spot preemption is affordable (K1).

**Fleet auth: gateway virtual keys only.** Subscription OAuth is a
fleet-wide correlated single point of failure — live-demonstrated when
this round's own probe phase was disabled by a shared weekly limit
(`r1` §1E). Keys are minted per claim, budget-tagged, and revoked on lease
reclaim (spend-plane fencing). Because warm pods predate their runs,
nothing per-run can arrive via env: **credentials and sessionStore
selection are delivered in-band at claim** over `thread/start` config
(`r2` §4.4).

**cc-harness backlog.** R1's thirteen ticket-scoped co-design items
(T1–T13, `r1-runtime-gaps.md` §4) are the runtime work list. Three form
the **pre-spike set** (DL-10): **T5** — park mirroring to the board
(converts park durability from process-memory to board-recoverable; also
the authoritative park feed for the E2 ledger and the E3 unified queue);
**T6** — `ccx serve --config` process-side defaults (without it a pod
cannot pin its sessionStore/hooks/posture; the probe-era workaround is a
bespoke entry point); and **T12** — the fleet SDK pin + drift gate, which
closes the version skew R1 found live (harness 0.3.220 vs probes
0.3.211) so spike evidence lands on a pinned SDK. Two items join the
backlog from the critique round: **T14** (REDEFINED 2026-07-31 by DL-14
— the egress-proxy sidecar: Phase-A transparent CONNECT/SNI proxy +
`iptables-legacy` REDIRECT init container, then Phase-B TLS termination
+ egress credential brokering. The original value case carries over —
preventing executed code from ever *touching* the push credential — now
achieved at the network layer with six shipped precedents instead of
unprecedented cross-container exec routing; K6's exec-split variant
remains possible further hardening but loses its primary motivation)
and **T15** (the sessionStore append-failure posture: bounded
buffer-and-retry, then fail loud — never silent local divergence).
T5's acceptance additionally covers answer-to-re-raise correlation: a
park answered while its pod is dead must bind to the re-raised decision
on resume.

## 3. Platform layer — k8s + Agent Sandbox + egress

### 3.1 Substrate

Adopt the **upstream Agent Sandbox CRDs** — now a vendor-neutral
Kubernetes SIG-Apps subproject, which collapses the old "adopt the GKE
product vs self-host the shape" fork (`r2` §1.2). Pin the controller
version; treat upgrades as change windows (the v0.4→v0.5 warm-pool
adoption bug is the validated failure state). On GKE, install via the
addon only if its CRD version matches the pinned upstream — the addon
lags (`v1alpha1` in its docs vs upstream `v1beta1`); otherwise install
upstream directly (`r2` §1.1–1.2). The `Sandbox` CRD's stable
DNS identity is the pod-addressability mechanism for the appserver seam
(in-cluster check queued). GKE Standard + Dataplane V2 + gVisor node
pools at both tiers (§1).

### 3.2 Egress: credential-aligned three layers (DL-4)

The sandbox's principal adversary is **the code the worker executes**
(package postinstalls, build scripts, cloned repos), not the worker's
judgment — model-quality arguments do not reduce that vector, and npm
supply-chain compromise is a validated failure state (public record:
recurring registry postinstall-malware campaigns — a synthesis-session
premise, not a round-report finding). At the same time,
blanket egress denial creates the exact environmental friction
long-running autonomous work cannot afford. The posture aligns
restriction with what the pod holds:

- **Layer 1 — gVisor pod boundary: every class, always.** Transparent to
  the workload; zero friction; protects the node and neighbors from
  executed code.
- **Layer 2 — RFC-1918 / CoreDNS-spoof / metadata-server block: every
  class, always** — plus the in-cluster allowances that ride with it:
  standard NetworkPolicy permitting exactly {LLM gateway service, sandbox
  router, kube-dns} (`r2` §3 items 1–2). Kills lateral movement and the
  GKE credential-theft path while leaving the public internet open and
  the pod able to resolve names and reach its model gateway; zero
  friction for research, Playwright, or scripts.
- **Layer 3 — allowlist egress: on lanes holding long-lived
  credentials** (the push-credential implement class) **and, by DL-13's
  adversarial-code exception, the review lane** (executes the PR under
  review by design; near-zero friction claim).
  Lanes mapped to the research class run **open public egress** and hold
  no durable credentials — restricting such a pod is a hard gate without
  a validated *credential* failure state. What those pods do still hold
  is the private source tree and transcript context; their exfiltration
  over open egress is an explicitly ACCEPTED risk, not an oversight
  (DL-13).
  Direct Playwright/web access is first-class on these lanes. The
  classifier-gated proxy attenuator (2026-07-29 enterprise DL) is
  **demoted to an enterprise hardening knob**, no longer the research-lane
  default — a human-authorized revision (DL-4).

**Lane → run-class mapping** (input = the board's `run.lane`; the
dispatcher stamps the class as the pod label the egress objects select
on):

| Board lane | Run-class | Egress | Credentials in-pod |
|---|---|---|---|
| `implementer` | implement | Layers 1–3 (proxy allowlist) | virtual key; push credential in-pod until Phase B, then sidecar-brokered (never in the agent container) |
| `architect`, `spike` (board lane) | research | Layers 1–2 (open public) | virtual key only; repo via claim-time ephemeral read token, scrubbed after workspace provisioning |
| `qagent` | review | Layers 1–3 (proxy allowlist: git host, registries, doc hosts) — DL-13, human-confirmed 2026-07-31 | virtual key only; same ephemeral-read mechanism; no push credential, no implementer-volume mounts |
| `ops` | ops | n/a — not a sandbox pod | own key path on the out-of-cluster VM (§5) |

The ephemeral-read mechanism is a synthesis addition: clone with a
short-lived token at claim, **scrub it, and only then install
dependencies** — postinstalls must never run while the token is live.
After provisioning, those pods hold no durable credentials. The qagent
row deliberately departs from pure credential alignment: review executes
adversarial code *by design* (the PR under review) while its residual
friction is near zero — doc lookups ride the provider's server-side
web_search/web_fetch, and a genuinely blocked fetch files an env-issue
or parks, never quietly widens the allowlist. The spike lane's
deliverable is its report on the ticket; branch-producing exploration is
not spike work — it re-enters as an implement-class ticket.

**Enforcement mechanism (DL-14, 2026-07-31): a pod-local egress-proxy
sidecar over a kernel default-drop floor** — FQDNNetworkPolicy is
demoted to optional belt (its 50-resolved-IP cap, no-CNAME-chase rule,
shared-CDN-VIP over-permission, and open-port-53 requirement are
structural; `r5-egress-transport.md`). The shape is the field-converged
one (GitHub AWF / Anthropic srt / Cloudflare): a native sidecar
container whose readinessProbe gates pod readiness, plus an
`iptables-legacy` init step — **NET_ADMIN on the init container ONLY,
never the agent container** — that REDIRECTs 80/443 to the sidecar,
forces DNS through the sidecar's resolver, and default-drops the rest
of the pod netns. Interception is transparent, so the measured
HTTP_PROXY-compliance gap (Node fetch, Playwright, Gradle, npm) never
becomes an enforcement hole; gVisor supports exactly this primitive
(nat-table REDIRECT + SO_ORIGINAL_DST verified upstream; TPROXY is NOT
implemented — the inverse of general-Linux advice). Run-class proxy
policy is delivered at claim, in-band with credentials, and is
**runtime-updatable**: a blocked request is a structured proxy event →
env-issue/park → policy update with no pod restart — friction becomes a
board event, not a stalled run. **Phase A** (the spike substrate):
CONNECT/SNI hostname allowlisting + full connection logging, no TLS
termination (domain fronting accepted at this phase, as the vendor
defaults do). **Phase B** (implement lane first): TLS termination with
a per-pod ephemeral CA + **egress credential brokering** — the push
credential lives in the sidecar and is injected only toward the git
host over HTTPS (git forced HTTPS-only; SSH-over-CONNECT rejected as an
opaque channel), so the agent container never holds it. Known limits
carried from the vendors that ship this: request-signing clients
(SigV4), format-validating CLIs, and OAuth token-exchange flows sit
outside egress injection; cert-pinned clients need per-domain
termination excludes. The egress class is still chosen by the control
plane, never the workload (dispatcher-stamped `run-class:` labels select
the Layer-2 objects; the claim delivers the proxy policy). The
pull-through registry cache remains the warm-disk mitigation (`r2` §3).
Cluster checks gating commitment (r5 §3): GKE Sandbox multi-container
netns sharing; REDIRECT + SO_ORIGINAL_DST end-to-end under GKE Sandbox;
the Agent Sandbox VAP edit exempting the egress-init container's
NET_ADMIN.

### 3.3 Credential plane

In-cluster LiteLLM-class gateway, control-plane namespace, HA pair; real
provider keys live only there; sandbox pods can reach only the gateway
for model traffic. Key lifecycle rides the claim lifecycle (§2). The ops
agent never uses this gateway (§5). Warm pods are born with their own
appserver bearer as a 0600 token-file minted at pool creation; the claim
registers its hash on the run row, and plaintext tokens live only in the
E3 gateway's own secret store — never on the board. srt-inside-gVisor
(likely-yes, desk confidence) is cluster-day-one probe P4. The P4-FAIL
posture is **no second exec layer** — srt is never the load-bearing
boundary (that stays egress + credential brokering), so losing it
degrades defense-in-depth without forcing topology; the K6 sidecar
remains a deferred enterprise option gated on T14, not a fallback
default (DL-12, superseding the pre-synthesis fallback note in
`p4` §(c)).

## 4. Board layer — Postgres SSOT

The board schema draft `r2-board-schema.md` is the binding shape and the
input to the E3 platform decomposing run. Properties this architecture
depends on:

- **Append-only `ticket_event` + mutable current state** (E2): append-only
  by *privilege* — no role holds UPDATE/DELETE. Any past board state
  reconstructs from the log; reading current state never folds it.
- **Claim ≠ state transition** (E1): claim sets ownership + fence; the
  worker's first board write is its gate verdict.
- **The heartbeat dissolves**: lease liveness = a reconciler JOIN on the
  cc-harness Postgres sessionStore's `mtime` stamp — zero new worker
  duties, extended to the lease. One Postgres, two schemas
  (`board` / `sessions`), pooler-safe by construction; promote-sessions-
  first is the standing separation ladder. **Liveness is phased and
  probe-confirmed.** Pre-T11 (mtime only): the `mtime` stamp lands at
  turn boundaries only (probe 62), so the lease window — per-lane
  config, never a fleet scalar — MUST exceed that lane's maximum turn
  duration; otherwise a long live turn reads as dead and reclaim
  revokes its virtual key mid-turn. Once T11's hook-event emitter
  lands, the liveness grain shrinks to the tool call under a
  **suspicion → probe → condemn** rule: hook-silence past the lane's
  window is suspicion only; condemnation requires a failed active probe
  (pod get + the tokenless `/healthz` from T7). A healthy pod with
  silent hooks is never reclaimed — it is logged as a T5-class
  env-issue (wedged emitter). **Continuity gate, both signals:** the
  reconciler may not condemn on ANY staleness unless the state plane
  was continuously reachable for the relevant window since its own
  recovery — otherwise a Postgres restart mass-false-reclaims the
  fleet, revoking every live run's key; and staleness is judged on
  board insertion time (`ticket_event.at`), never emitter-side
  timestamps (T15 buffering makes late arrivals with old payloads
  normal). Named residual: a live pod with a hung engine is
  indistinguishable from a legitimately long tool call by every passive
  signal — that tail stays ops-agent judgment (`r3` §2.3 feed 3),
  bounded by per-lane tool-call ceilings; the phased liveness narrows
  the ambiguity window, it does not close it.
- **Mirrors are outbound-only daemons** on a transactional outbox with
  per-ticket coalescing (GitHub's ~500 content-writes/hr/actor cap).
  No inbound webhook surface exists at all; mirror edits are repaired,
  never ingested.
- **The board owns discovery**: `run` rows carry pod DNS / session /
  thread / virtual-key ids — "which pod holds ticket N" is a board query
  (`thread/list` is per-process memory and unusable cross-pod, `p3`).

**Appserver tenancy (DL-6).** The pod is the tenant boundary: one
accountable worker per pod, so the appserver stays **single-tenant by
design** — its bearer token is pod-root and that is acceptable *because
the pod holds one tenant*. Cross-pod access (humans, control plane, other
agents) is authenticated and authorized at the **E3 gateway**, per-thread,
backed by the board's `run` table. R1's T8 fork (in-harness principal vs
authorizing proxy) resolves to the proxy side by architecture rather than
by harness code; TLS terminates at the mesh/ingress.

## 5. Ops layer — agent-operated, spike-gated

The ops agent is **one more accountable worker** on the board's
`env-issue` lane (`r3` §1): same claim path, same park queue, same audit
trail — MTTR and intervention counts are SQL over `ticket_event`. Its
three structural distinctions: it runs on a small VM **outside the
cluster** (in-project; alert evaluation + dead-man's switch also outside,
so cluster-down pages); its **own key path**, never the in-cluster
gateway; an **independently pinned harness version**, upgraded last, so a
fleet regression cannot disable its own fixer. Its patrol includes a
self-check of its own key's credit/limit state (this round's live
lesson: both local credentials died at once), and its silence trips the
same outside dead-man alert as the fleet's.

**Authority is structural, not prompted** (`r3` §3): runbooks are skills
(guidance); the boundary is RBAC + a CEL ValidatingAdmissionPolicy +
board/gateway scopes. Direction-of-safety: contraction (kill pod, revoke
key, pause dispatch) always autonomous; restoration bounded to human-set
[min, max]; egress policy, DDL, versions, IAM, budgets human-only — each
ban mapped to a validated failure state. T7 (security trips) is
containment-and-escalate only.

**The MTTR spike is the single promotion gate** for agent-ops — and the
only gate through which self-managed substrate could ever re-enter.
Execution is separately gated (real spend, ≈$1,030 at live rates, abort
cap $1.5k; halving the real-model Haiku lane is the cheapest headroom
lever — `r4` §9.3). Promotion bar (`r3` §5.6, with DL-3 applied):

1. ≤1 human intervention/week (precisely defined; by-design human-only
   parks half-weight when containment was complete).
2. MTTR ≤ 8 working hours, detection → verified resolution; the clock
   does not pause while parked.
3. Measured platform + agent-ops cost, scaled to 27.5k run-hr/mo,
   ≤ 0.5× the **capability-parity managed band** — vendors that can
   express the run-class egress allowlist (E2B / Daytona / Modal), i.e.
   the counterfactual we would actually buy (≈ Autopilot's all-in price).
   Consequence: the bar passes on Spot with 21–26% margin and is marginal
   on-demand, so **Spot is a spike design requirement**, including
   preemption-behavior validation (DL-3, DL-7).

**Failure attribution — the bar is a verdict vector, not one bit.** A
failed bar names its taxonomy class, and the remedy follows the class:
node/infra-class failures (T2, the node runbooks) → Autopilot
break-glass; agent-judgment failures (lost diagnoses, thrash) → human
ops retained and the runbook catalog iterated; queue-latency failures
(parks nobody drained) → an E3/process fix. Autopilot remedies ONLY the
first family — buying node ops cannot fix a judgment or queue failure.
The cost leg is primarily live validation of the ops-token term (the
one degree of freedom R4 could not price from a desk). Week 0
additionally runs an **adversarial egress day**: red-team the boundary
from inside pods, explicitly including DNS tunneling through allowed
kube-dns against the implement lane's FQDN allowlist — a standard
postinstall-malware technique that meets the validated-failure bar.

## 6. Economics layer — standing rules

- **token:infra ≈ 100× (band 37–264×)**, stable under a complete re-price
  of both sides: infra decisions are rounding error; token decisions are
  the budget (`r4` §6.4).
- **The architect-lane cap (K5) is the system's most valuable dial** —
  worth 12–49× the entire substrate decision. Set it from a cost target;
  the board carries per-lane spend rollups; judge the architect lane on
  total downstream run cost (it pays for itself at ~5 avoided implementer
  runs per architect run).
- **The self-host crossover is 5–8 sustained concurrent** (was 300–500
  under the human-engineer constant); every operating point of this
  program sits far above it. Flip triggers FT1–FT8 (`r4` §8) are the
  standing re-entry conditions; notably there is **no growth path that
  makes managed cheaper**.
- **Scheduled event:** Sonnet 5 intro pricing expires **2026-08-31**
  (+50% on the implementer line, ≈ +$86k/mo at A0-mid). Budget now.
- **Day-one instrumentation:** the per-run cache-hit-ratio meter (a +4×
  downside lever — a fleet-wide cache regression ≈ +$640k/mo at A0-mid)
  and bytes-per-run egress measurement.
- **Ramp posture:** before the swarm campaign is approved there is no
  standing cluster — the platform exists only as the separately gated
  MTTR spike, and current tempo sits far below the crossover (FT1's
  fixed floor, $445–700/mo plus the ops term, runs from cluster day one
  regardless of volume). The standing rules above are stated at
  campaign scale; the demand anchors remain unmeasured Fermi estimates
  until the board's own run data replaces them.

## 7. Adoption path and gates

1. **cc-harness backlog** (T1–T13; pre-spike set T5+T6+T12 first) —
   ticket-shaped work. Whether it runs on the interim GitHub board or
   waits for the Postgres board remains the human's standing call.
2. **E3 platform decomposing run** — now unblocked: `r2-board-schema.md`
   is the input the E3 spec was gated on.
3. **The MTTR spike** — separately gated go (spends real infra).
4. **Production promotion** — only through the spike bar; failure →
   Autopilot break-glass.

Standing gates unchanged: A0 plan execution deferred; swarm campaign
approval-gated.

## Acceptance

Observable behaviors, each checkable when its layer lands:

1. **One-architecture check:** the A0 and enterprise deployments differ
   only in knob-confined changes — a single declared values file (K1/K2/
   K5 numbers, K3 lane→class assignments) plus the declared optional
   overlays (K6's sidecar container — exercisable only once T14 exists —
   and K3's enterprise hardening objects).
   Any structural diff outside the values file and the named overlays is
   a fork and fails the check.
2. **Egress posture check (in-cluster):** a research-class pod fetches an
   arbitrary public URL successfully AND is refused RFC-1918/metadata
   endpoints other than the declared in-cluster allowances (gateway,
   router, kube-dns); an implement-class pod is refused any
   non-allowlisted external host AT THE PROXY, and a direct-route
   attempt from its agent container (dialing a raw IP with proxy env
   scrubbed) is dropped by the pod-netns rules — proving enforcement
   does not depend on client cooperation. All as `kubectl exec` probes.
3. **Detached-worker check:** a model in a worker session dispatches a
   `DetachedTask`; the parent harness *process* is SIGKILLed inside the
   pod; the child completes and its transcript is resumable from a third
   process (P2's §6 probe run with a funded credential). Pod-level
   durability is exercised separately as the board path: a child ticket
   claimed onto its own pod survives deletion of the parent's pod.
4. **Board-durability check:** kill any worker pod mid-run; the
   reconciler reclaims via the sessionStore-mtime JOIN with zero worker
   heartbeat writes in the log, and the ticket resumes per the E1
   recovery split.
5. **Spike bar check:** MTTR and intervention counts compute as SQL over
   `ticket_event` plus the k8s audit log; the cost bar joins the
   gateway's spend rollups and the cloud billing export. No separate
   incident/intervention datastore exists.
6. **Break-glass check:** switching the sandbox pool from Standard to
   Autopilot requires only cluster-level changes plus knob-value edits
   (warm-pool replicas down, Spot selectors) — zero *structural* edits
   to Sandbox/Template/WarmPool/Claim manifests and zero board/harness
   config changes.

## Decision Log

- Decision: **One architecture with knob-set tiers; this spec supersedes
  both 2026-07-23 specs.**
  Rationale: four independent evidence bases converged (runtime forces no
  fork; platform CRD layer identical; ops framework tier-invariant; one
  cost function with procurement knobs). Rejected: maintaining two specs
  (enterprise + A0) — the divergence they encoded was the human-ops
  constant, now removed.
  Date/Author: 2026-07-30, round synthesis; human-approved.

- Decision: **GKE Standard at both tiers; Autopilot retired as a tier,
  kept as break-glass.**
  Rationale: Autopilot at A0 ≈ $4.2k/mo all-in vs Standard $2.4k
  (on-demand) / $1.7k (Spot) — a ~$1.9k/mo premium for node ops that
  agent-ops replaces at ~$150/mo ("paying twice for the same thing",
  `r4` §4.4; directional — the premium buys only the node-ops slice of
  what the flat ops term covers, so a raw multiplier overstates it). The
  break-glass framing reconciles R2's dissent: if the
  spike fails, Autopilot IS the managed-ops purchase, same manifests.
  Rejected: R2's "Autopilot as the A0 entry" (does not survive its own
  price); deferring the call to the spike (the spike runs on Standard
  regardless, so deferral collapses into this decision).
  Date/Author: 2026-07-30, human (grill Q1).

- Decision: **Spike promotion-bar comparator pinned to the
  capability-parity managed band** (vendors that can express the
  run-class egress allowlist: E2B / Daytona / Modal).
  Rationale: the comparator must be the counterfactual actually purchased
  on failure — which is ≈ Autopilot's price band, matched by the parity
  vendors. Pinning to the whole band (incl. Northflank/Cloudflare, which
  cannot enforce the boundary) makes the bar mechanically unpassable — a
  dead-letter clause. The pin also defines FT4 trigger membership.
  Rejected: whole-band comparator; dropping the economic leg (would
  remove the only numeric answer to "why keep self-hosting").
  Date/Author: 2026-07-30, human (grill Q2, after clarification).

- Decision: **Run-class egress = credential-aligned three layers**;
  research/browse lanes run open public egress; the classifier-gated
  proxy attenuator is demoted from research-lane default to an
  enterprise hardening knob (revising the 2026-07-29 enterprise DL).
  Rationale: the sandbox's principal adversary is executed third-party
  code (validated in the public record: recurring npm postinstall-malware
  campaigns), which layers 1–2 counter at zero friction; layer 3 only
  defends credentials, so it applies only where credentials exist. Restricting a pod holding nothing but a revocable
  virtual key is a hard gate without a validated failure state
  (constraint-minimization golden rule). Swarm trial counts (a day of A0
  ≈ months of local use) and unattended operation justify layers 1–2
  everywhere despite months of incident-free local auto-mode — the local
  evidence speaks to the model-judgment channel, not the executed-code
  channel. Rejected: R2's blanket default-deny + FQDN (recreates
  environmental friction for long-running research work); layer-2-only
  everywhere (leaves the push-credential exfiltration path open in the
  supply-chain scenario).
  Date/Author: 2026-07-30, human (raised the auto-mode challenge; grill
  Q3).

- Decision: **Adopt upstream Agent Sandbox CRDs; do not self-build the
  template/warm-pool/claim shape.**
  Rationale: the project became a vendor-neutral k8s SIG subproject —
  the 07-23 fork's premise (GKE-only product) is dead; self-building
  re-implements three hardened reconcilers with zero differentiation.
  Risk accepted: pre-GA churn — pin versions, upgrades are change
  windows. Rejected: self-hosting the shape (`r2` §1.2).
  Date/Author: 2026-07-30, R2 verdict, adopted at synthesis.

- Decision: **Appserver stays single-tenant per pod; cross-pod
  authorization lives at the E3 gateway, backed by the board's run
  table.**
  Rationale: one accountable worker per pod makes the pod the tenant
  boundary; the shared bearer token being pod-root is then acceptable.
  Resolves R1's T8 fork on the proxy side by architecture. Rejected:
  in-harness per-identity principal (builds multi-tenancy the pod model
  never needs).
  Date/Author: 2026-07-30, synthesis.

- Decision: **Spot is the A0 procurement default and a spike design
  requirement.**
  Rationale: A0 duty cycle ~30% fails every CUD break-even; preemption
  costs ≤1 turn (turn-durability ceiling); the comparator pin makes the
  economic bar passable specifically on Spot. Rejected: CUDs at A0
  (break-even needs ≥45–72% duty).
  Date/Author: 2026-07-30, `r4` §9.1, adopted at synthesis.

- Decision: **The self-managed bare-metal gate stays closed.**
  Rationale: the assumed 5–10× cost gap collapsed to 0–2.7× against
  CUD-discounted GKE, on a rate card three live sources dispute by 2.8×,
  from a vendor with a +94–192% repricing precedent (FT6). Rejected:
  funding a second self-managed spike.
  Date/Author: 2026-07-30, `r4` §5, adopted at synthesis.

- Decision: **Fleet auth is gateway virtual keys only; subscription OAuth
  is banned for fleet workers.**
  Rationale: live-demonstrated this round — one shared OAuth weekly limit
  disabled the entire probe phase (a fleet-wide correlated failure with a
  multi-day reset). Rejected: subscription auth for economy (the failure
  mode is disqualifying regardless of price).
  Date/Author: 2026-07-30, `r1` §1E.

- Decision: **Pre-spike cc-harness set = T5 (park mirroring) + T6
  (`ccx serve --config`) + T12 (SDK pin/drift gate).**
  Rationale: T5 changes park-loss accounting under fault injection and
  feeds the E2 ledger/E3 queue; T6 is the highest-leverage single item
  (pods cannot pin store/hooks without it); T12 closes the live-found
  version skew so spike evidence lands on a pinned SDK. Rejected:
  running the spike on the bespoke-entry-point workaround alone.
  Date/Author: 2026-07-30, synthesis (`r3` §7.4 asked the T5-timing
  half; T6/T12 added here).

- Decision: **Board schema per `r2-board-schema.md`** (claim ≠
  transition; heartbeat dissolved into the sessionStore-mtime JOIN;
  append-only-by-privilege event log; outbound-only mirrors; board-owned
  discovery).
  Rationale: recorded in the draft and the E1/E2 specs (single copies);
  this spec binds to it rather than restating it.
  Date/Author: 2026-07-30, R2 deliverable, adopted at synthesis.

- Decision: **The P4-fail posture is "no second exec layer"; the K6
  sidecar is a deferred enterprise option gated on backlog item T14.**
  Rationale: srt is never the load-bearing boundary, so a failed
  srt-inside-gVisor probe removes an optional inner layer without
  forcing topology at either tier. The pre-synthesis fallback note in
  `p4` §(c) ("sidecar becomes the default shape") contradicts the same
  probe's own closing line ("a defense-in-depth degradation, not a
  design blocker") and is superseded. K6's future value case is
  recorded on T14: with the push credential in-container, executed code
  can USE it directly (the git host is necessarily on the Layer-3
  allowlist) — the sidecar is the only layer preventing credential
  touch, vs branch protection + QAgent review as the current weaker
  backstop. Rejected: killing K6 outright (discards a legitimate
  defense-in-depth option at near-zero carrying cost);
  sidecar-as-default on P4 failure (would make an unbuilt, unticketed
  topology a mandatory outcome).
  Date/Author: 2026-07-30, critique-round convergence.

- Decision: **The qagent lane moves behind a Layer-3 allowlist (git
  host, registries, doc hosts) — HUMAN VETO PENDING; source-tree
  confidentiality on the remaining research-class lanes is an
  explicitly accepted risk; the two-hop injection chain is a named
  residual.**
  Rationale: review executes adversarial code by design (the PR under
  review) while its friction claim is near zero — doc lookups ride the
  provider's server-side web tools, and a blocked fetch files an
  env-issue or parks, never quietly widens the allowlist. The remaining
  research-class lanes (architect, board-lane spike) keep open egress
  with the residual NAMED rather than hidden: those pods hold the
  private source tree and transcript context, and exfiltration by
  executed code is accepted per the human's stated risk appetite —
  DL-4's original record argued only the credential axis. The injection
  axis is likewise recorded: injected web content → architect plan →
  implementer executing it WITH push credentials is invisible to
  per-pod credential alignment; the mitigation chain is the implementer
  gate binding the plan, plan-review + QAgent review downstream, and
  Layer 3 on the only credentialed pod. Rejected: leaving qagent on
  open egress (the one lane where the open-egress justification does
  not apply); keeping the "nothing to steal" phrasing (false — fixed to
  "no durable credentials").
  Date/Author: 2026-07-30, critique-round convergence. Veto resolved
  2026-07-31: the human approved the allowlist.

- Decision: **Layer 3's enforcement mechanism is a pod-local
  egress-proxy sidecar over a kernel default-drop floor, adopted
  phased (A: CONNECT/SNI allowlist + transparent REDIRECT + runtime
  policy delivery at claim; B: per-pod-CA TLS termination + egress
  credential brokering, implement lane first); FQDNNetworkPolicy is
  demoted to optional belt; T14 is redefined accordingly.**
  Rationale: the three-researcher survey `r5-egress-transport.md`
  (2026-07-31, human-triggered) — every first-party agent vendor
  enforces egress at a proxy, none ships DNS-snooping as its product
  layer, and GitHub's open-source AWF is the exact three-container
  shape; FQDN policy is structurally over-permissive (shared CDN VIPs,
  50-IP cap, no CNAME chase) and requires open port 53 (a conceded
  exfil channel); transparent REDIRECT erases the measured
  HTTP_PROXY-compliance friction; gVisor implements REDIRECT and not
  TPROXY (upstream-source-verified, refuting the circulating no-nat
  claim); egress credential injection is a settled pattern (six shipped
  implementations + the CB4A draft) that subsumes K6's credential-touch
  goal; runtime-updatable proxy policy converts blocked-fetch friction
  into board events — directly serving the friction concern that
  triggered the inquiry. Rejected: keeping FQDNNetworkPolicy
  load-bearing (the structural holes above); env-var-only proxying
  (compliance gap = enforcement hole); Phase-A-only adoption (loses the
  K6 subsumption; retained as fallback if Phase B's CA tax proves too
  high in practice); a node-local shared proxy (remixes tenants at the
  isolation seam — the Istio-ambient cost argument does not transfer
  to bursty per-tenant pods with per-pod CAs).
  Date/Author: 2026-07-31, human (grill: phased adoption).

## Surprises & Discoveries

- Observation: the round's probe phase was itself disabled by a shared
  OAuth weekly limit — which became the fleet-auth decision's strongest
  evidence rather than a mere obstacle.
  Evidence: `r1-runtime-gaps.md` §0.5, probe transcripts in `p1`–`p3`.
- Observation: the tiers' economic difference reduced to a purchase
  order (discount instrument) plus a scale-invariant $445–700/mo floor —
  "the same architecture, whose advantage compounds with scale" is the
  strongest available form of the one-architecture answer.
  Evidence: `r4-economics.md` §9.1, §10.
- Observation: the human's local auto-mode experience (months, no
  sandbox, no incident) survived the grill as evidence about the
  model-judgment channel and reshaped the egress posture (DL-4) — while
  the executed-code channel argument kept layers 1–2 universal.
  Evidence: this session's egress discussion; DL-4.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-30: v1. Authored at round close, interactively with the human;
  three queued forks settled (Autopilot, comparator pin, egress posture);
  supersession banners added to both 2026-07-23 specs.
- 2026-07-30: v1.1 — independent fable review, all 7 findings adopted:
  Layer 2 gains the in-cluster allowances {gateway, router, kube-dns}
  (was self-contradictory with §3.3); `DetachedTask` placement rule
  (in-pod = process-death durability only; pod-death durability = board
  path) and Acceptance 3 rewritten to the shape P2 actually verified;
  Acceptance 5's cost bar re-sourced to gateway rollups + billing export
  (was unobservable as written); lease-window > max-turn sizing
  constraint added to §4 (turn-boundary mtime seam); Acceptance 1/6 made
  decidable (knob-confined = values file + declared overlays); lane →
  run-class → egress mapping table added with the ephemeral-read-token
  mechanism, "MTTR spike" disambiguated from the board's spike lane;
  minor citation fixes (DL-10 scope, +4× one-directional, npm premise
  sourced, GKE addon install rule, Autopilot-CUD open fact carried).
- 2026-07-30: v1.2 — critique-round convergence (doperpowers:critique,
  multi-turn debate, no open disagreements beyond the flagged veto):
  DL-12 (P4-fail = no second exec layer; K6 reclassified as a
  T14-gated deferred option, no longer a knob-value) and DL-13 (qagent
  → Layer-3 allowlist, human veto pending; source-confidentiality
  accepted-risk record; two-hop injection residual named); liveness
  redesigned as phased suspicion → probe → condemn with a generalized
  state-plane continuity gate (Postgres-restart mass-reclaim closed)
  and per-lane lease windows; T14/T15 added to the backlog; spike bar
  becomes a verdict vector with per-class remedies + week-0 adversarial
  egress day; ramp posture added to §6; ephemeral-token
  clone→scrub→install ordering; warm-pod appserver bearer scheme; ops
  agent self-credential check; "independent convergence" softened to
  sequenced non-circular.
- 2026-07-31: v1.3 — DL-14 (human-approved on the r5 survey): Layer-3
  enforcement moves from FQDNNetworkPolicy to the pod-local
  egress-proxy sidecar over a kernel floor, phased (A: CONNECT/SNI +
  transparent REDIRECT + claim-delivered runtime policy; B: per-pod-CA
  TLS termination + egress credential brokering on the implement lane);
  T14 redefined from cross-container exec routing to the egress
  sidecar (K6's credential-touch goal absorbed); DL-13 veto resolved —
  qagent allowlist human-confirmed; Acceptance 2 gains the
  client-cooperation-independence probe; three cluster checks added
  (netns sharing, REDIRECT e2e, VAP init-container exemption).
  Evidence: `research/2026-07-30-clean-slate/r5-egress-transport.md`.
