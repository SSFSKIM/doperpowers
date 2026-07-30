# R2 — Platform: k8s + Agent Sandbox + board service (2026-07-30)

> **Round:** clean-slate R1–R4 (`round-brief.md` §R2). **Class A held
> throughout:** both tiers k8s + gVisor; runtime = cc-harness (Claude Agent
> SDK harness, co-designed); Postgres SSOT board with GitHub Issues / Linear
> as one-way mirrors; the two governing principles. This report does not
> re-litigate any of that — it decides the platform shape UNDER it.
>
> **Method note.** Class C sources were re-fetched this session (2026-07-30):
> Agent Sandbox upstream (kubernetes-sigs), GKE docs, GKE/GCE pricing and CUD
> pages, FQDN-network-policy docs; the cc-harness repo was read directly at
> `/Users/new/developer/github/codex_somersault/CC-to-SDK` (Postgres
> sessionStore adapter verified as shipped code, not prose). Web fetches ran
> through a summarizing fetch tool; where its output was ambiguous (release
> YEARS on the GitHub releases page rendered inconsistently) that is flagged
> inline rather than smoothed over. Every 2026-07-23 number reused here is
> marked as such — per round policy those are stale for pricing and retained
> only for structure. No cluster exists in this environment: every claim that
> needs a cluster is listed in §8 for in-cluster verification, none is
> fabricated.

---

## 0. Verdict up front

1. **Adopt the Agent Sandbox CRDs; do not self-build the
   template/warm-pool/claim shape.** The project is no longer a GKE-only
   product sketch: it is a Kubernetes SIG-Apps subproject
   (`kubernetes-sigs/agent-sandbox`), API graduated to
   `agents.x-k8s.io/v1beta1` (v0.5.0), installable on any cluster via
   `kubectl apply`, gVisor optional-but-supported upstream and mandatory in
   GKE's addon. Self-building the same three controllers buys nothing and
   costs a reconciler estate; the risks are pre-GA churn (real — v0.5.0
   broke `SandboxClaim.spec.templateRef` → `warmpoolRef`) and a
   GKE-addon-vs-upstream version skew (GKE docs still show
   `extensions.agents.x-k8s.io/v1alpha1`). Pin the upstream version; treat
   the GKE addon as a convenience install of the same thing, not a
   different substrate.
2. **Cluster shape: GKE Standard + Dataplane V2 + GKE Sandbox node pools is
   the default; Autopilot is the legitimate low-ops entry knob; self-managed
   is real but gated on R3.** All three run the SAME manifests (CRDs are
   vendor-neutral; `runtimeClassName: gvisor` works on Standard node pools,
   on Autopilot natively, and on self-managed runsc installs) — which is
   this report's contribution to the through-question: **at the platform
   layer, A0 and enterprise are one architecture; the cluster shape is a
   knob** (§7).
3. **Warm pools should be small (single digits at A0) and sized to dispatch
   bursts, not steady rate** — claim latency from a warm pool is sub-second
   and run lengths are 10–60 min, so the pool exists to absorb bursts and
   node-provisioning tails, not to shave milliseconds. On Autopilot every
   idle warm pod bills at full per-pod rates (~$79/mo per 2vCPU/4GiB warm
   pod at list) — warm-pool size is a first-class cost dial there, and
   nearly free headroom on Standard (§2).
4. **Egress: deny-by-default is NOT what Agent Sandbox gives you** — its
   secure-by-default posture blocks RFC-1918/metadata but allows public
   internet. Run-class egress profiles are built from three GA pieces:
   NetworkPolicy (in-cluster: gateway, router, DNS only),
   `FQDNNetworkPolicy` (GKE Dataplane V2, GA, domain allowlists with a
   50-IP-per-resolution cap) for the implement lane's short external list,
   and the classifier-gated egress proxy from the Class-A run-class
   decision for the research lane. Self-managed gets the identical
   semantics from Cilium `toFQDNs` (§3).
5. **Virtual-key brokering: an in-cluster LLM-gateway (LiteLLM-class) in
   the control-plane namespace, keys minted per claim by the dispatcher,
   revoked on reclaim.** One structural finding: **warm pools break
   inject-credentials-via-env** (env is fixed at pod creation, warm pods
   are created before their run exists), so per-run credentials must be
   delivered in-band at claim — a cc-harness co-design item (§4).
6. **srt-inside-gVisor (P4): likely-yes, medium confidence, desk-only** —
   consumed as-is; the in-cluster probe is queued as this platform's first
   cluster-day task; either outcome leaves the two-container sidecar
   available as the fallback default, so this gates a cost knob, not the
   design (§5).
7. **Board service: one Postgres, two schemas, one process** — the thin
   board service (A0 Plan 1 lineage) extended with the E1 lane states and
   the E2 append-only event log + mutable current state, cohabiting with
   the cc-harness Postgres sessionStore tables. The heartbeat duty
   dissolves: the sessionStore append stream IS the progress signal, so
   lease renewal becomes a join, not a worker write. Full schema draft in
   **`r2-board-schema.md`** (the E3 decomposing input) (§6).

---

## 1. Cluster shape and the CRD adoption question

### 1.1 What Agent Sandbox is now (re-fetched 2026-07-30)

- **Upstream:** `github.com/kubernetes-sigs/agent-sandbox` — a formal
  Kubernetes SIG Apps subproject; docs at `agent-sandbox.sigs.k8s.io`.
  Four CRDs: **`Sandbox`** (core: a declarative API for one stateful pod
  with stable identity — stable hostname/network identity, persistent
  storage surviving restarts, lifecycle incl. scheduled deletion,
  **pause/resume**), **`SandboxTemplate`** (reusable blueprint),
  **`SandboxWarmPool`** (maintains N pre-initialized pods), and
  **`SandboxClaim`** (adopts a ready sandbox from a pool). API group
  `agents.x-k8s.io/v1beta1` upstream. Vendor-neutral: install is
  `kubectl apply` on any cluster; gVisor/Kata are presented as optional
  runtime hardening, not requirements.
  (Sources: https://agent-sandbox.sigs.k8s.io/docs/getting_started/overview/,
  https://github.com/kubernetes-sigs/agent-sandbox — both fetched
  2026-07-30.)
- **Maturity signal:** current release line v0.5.x (latest v0.5.3; the
  releases page as summarized by the fetch tool rendered ambiguous years —
  Kubernetes 1.36 / controller-runtime v0.24 support in v0.5.1 pins the
  line to mid-2026, and v0.5.3 is dated July 23 of the current year).
  Notable recent history, all relevant to adoption risk:
  - **v0.5.0: API graduation to `v1beta1` with breaking changes** —
    `spec.replicas` → `spec.operatingMode`; `SandboxClaim.spec.templateRef`
    → `spec.warmpoolRef`; sandbox-router moved to `agent-sandbox-system`
    namespace; SSRF / pod-metadata-hijack hardening.
  - v0.5.2: fixed **warm-pool adoption issues on upgrade from v0.4.x**;
    added **WebSocket proxying support to the sandbox router** (directly
    relevant to the P3 appserver seam — the ccx appserver WS can transit
    the router).
  - v0.4.6: Service creation became opt-in "to improve scalability when
    managing thousands of pods."
  (Source: https://github.com/kubernetes-sigs/agent-sandbox/releases,
  fetched 2026-07-30.)
- **GKE's managed form:** the Agent Sandbox addon on GKE works on **both
  Standard and Autopilot**, is **offered at no extra charge** (you pay only
  the underlying compute), and enforces gVisor
  (`runtimeClassName: gvisor`, node selector
  `sandbox.gke.io/runtime: gvisor`, non-root, all capabilities dropped,
  **memory limits mandatory**). Its network posture: ingress blocked except
  from the Sandbox Router; egress **blocked to RFC-1918 ranges, CoreDNS,
  and the metadata server — public internet egress allowed by default**.
  The GKE docs still present the CRDs under
  `extensions.agents.x-k8s.io/v1alpha1` — a version skew against
  upstream's `v1beta1` that must be re-checked at adoption (the addon may
  lag upstream's breaking renames).
  (Source: https://docs.cloud.google.com/kubernetes-engine/docs/how-to/agent-sandbox,
  fetched 2026-07-30.)

### 1.2 Adopt vs self-host the shape

The 07-23 recommendation ("self-host the GKE Agent Sandbox shape, or adopt
the product if the org lands on GCP" — `2026-07-23-cloud-scale/r2-sandbox-substrate.md`
§3) was written when Agent Sandbox looked like a GKE product. That premise
is dead: the controllers are open source, SIG-governed, and cluster-agnostic,
so "self-host the shape" and "adopt the CRDs" have collapsed into the same
option. **Adopt the upstream CRDs everywhere; on GKE, install via the addon
if its CRD version matches the pinned upstream, else install upstream
directly.** Self-building the template/warm-pool/claim triple would
re-implement ~three reconcilers plus a router that upstream already
hardened (SSRF, metadata hijack, scale past thousands of pods) — with zero
differentiation for us, since our differentiation lives in the board, the
harness, and the credential plane.

Residual risks, named: (a) `v1beta1` is pre-GA — expect at least one more
breaking rename; pin the controller version and treat upgrades as change
windows (the v0.4.x→v0.5.x warm-pool adoption bug is the cautionary tale);
(b) the GKE addon's version lag; (c) the `Sandbox` CRD's stable-identity /
persistent-storage orientation is *more* than our cattle doctrine needs —
per-run sandboxes stay exit-and-replace; we consume identity/persistence
only where the appserver seam wants a stable DNS name (P3 §f.4 — the
`Sandbox` stable hostname replaces the StatefulSet workaround the probe
proposed, worth an explicit in-cluster check).

### 1.3 GKE Standard vs Autopilot vs self-managed

Facts (all re-fetched 2026-07-30 unless marked):

| dimension | GKE Standard | GKE Autopilot | self-managed (upstream CRDs on kubeadm/k3s + runsc) |
|---|---|---|---|
| billing | per node (Compute Engine) + $0.10/hr cluster fee (free tier ~$74.40/mo credit) | per pod: ~$0.0445/vCPU-hr + ~$0.0049/GiB-hr (us-central1, ~Apr 2026 verification by CloudZero) + same cluster fee | hardware rental (07-23 basis: Hetzner NVMe boxes ~$450–650/mo at A0 scale; stale, R4 re-prices) |
| CUD | resource-based via Compute Engine: **37% (1-yr) / 55% (3-yr)**, 70% 3-yr memory-optimized; flexible CUD 28%/46% also applies | **flexible CUD only: 28% (1-yr) / 46% (3-yr)**; per one 2026 tracker, Autopilot-specific resource CUDs are no longer purchasable (the official CUD doc page does not state this — discrepancy flagged, verify at purchase) | n/a |
| gVisor | GKE Sandbox node pools (`--sandbox type=gvisor`), no extra charge | supported natively via `runtimeClassName: gvisor` (GKE ≥1.27.4-gke.800) | install runsc yourself; upstream CRDs treat it as optional |
| local NVMe | full control: Local-SSD/NVMe node pools (ephemeral or raw block; NVMe interface GA) | **not supported for most compute classes** — ephemeral Local SSD only on Accelerator-class / specific machine-series selections | full control (the 07-23 density argument's home turf) |
| egress tooling | Dataplane V2 → `FQDNNetworkPolicy` (GA) | Dataplane V2 is the default → same | Cilium `toFQDNs` |
| ops surface | node pools, upgrades, capacity | near zero (nodes are Google's problem) | everything — the R3 question |

(Pricing/CUD sources: https://docs.cloud.google.com/kubernetes-engine/cud ·
https://www.cloudzero.com/blog/gke-pricing/ ·
https://docs.cloud.google.com/compute/docs/instances/committed-use-discounts-overview
via search · https://www.usage.ai/blogs/gcp/committed-use-discounts/ ·
local SSD: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/local-ssd ·
Autopilot gVisor: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/sandbox-pods.)

**Cost sketch at the A0 anchor** (27.5k run-hr/mo at 2vCPU/4GiB, the
`sandbox-substrate-a0.md` basis — the run-hour basis is structure, the
rates are fresh): Autopilot ≈ 27.5k × (2×$0.0445 + 4×$0.0049) ≈
**$2,990/mo list, ~$2,150 with 1-yr flex CUD** — comparable to the managed
sandbox SaaS band's low end ($1.8–4.7k, 07-23 numbers) while keeping the
substrate identical to the enterprise tier. Standard with bin-packed
general-purpose nodes lands in the same band at list and **~$1.3–1.9k with
3-yr resource CUDs**, at the cost of owning node pools; the 07-23
self-managed floor (~$0.5k A0, ~$5–15k at 1,000 concurrent vs ~$73k+ SaaS)
is why self-managed stays on the table at all. These are R2 shape
comparisons only — R4 owns the real remeasure.

**Recommendation.** Default the reference architecture to **GKE Standard +
Dataplane V2 + GKE Sandbox node pools + pinned upstream Agent Sandbox**,
because it is the only shape that satisfies all three tiers of
requirements simultaneously: deep CUDs, local-NVMe node pools when the
warm-disk ladder starts to matter (cloud-scale r2's decisive I/O-density
argument), and zero-compromise egress tooling. **Autopilot is the A0
entry**: same manifests, no node ops, per-pod billing — accept (a) warm
pods billed at full rate (§2) and (b) no local-NVMe ephemeral, which at A0
tempo (10–15-min runs, modest repos) the 07-23 analysis already said is
survivable on balanced PD + image streaming. **Self-managed re-enters only
through R3's gate** (agent-operated ops ≥2× cheaper than the managed band
at ≤1 human intervention/week) — the platform layer imposes no switching
cost since the CRD layer is identical.

---

## 2. Warm-pool sizing vs claim latency

The latency ladder, with sources:

| path | latency | source |
|---|---|---|
| claim from warm pool | **sub-second** (ownership flip: pod's `ownerReferences` moves `SandboxWarmPool` → `Sandbox`) | GKE agent-sandbox doc + upstream overview, 2026-07-30 |
| pool replenish, image already on node | pod start ≈ seconds | inference from pinned/pre-pulled images; verify in-cluster |
| pool replenish, image pull needed | image-size-dependent; the cc-harness image will be ~1.5–2 GB (P1: 312 MB prod `node_modules` incl. the 245 MB darwin CLI binary — linux size unverified — plus base + toolchain), mitigated by GKE image streaming / pre-pull DaemonSet | P1 `probes/p1-pod-footprint.md`; GKE image streaming |
| cold node (Standard autoscale / Autopilot pod-triggered provisioning) | ~1–2 min class | medium confidence, not re-verified — measure in-cluster |

**The sizing logic is burst-shaped, not rate-shaped.** Runs last 10–60 min;
even a 60 s cold start is 1–10% overhead — the 07-23 conclusion ("the
millisecond snapshot arms race is irrelevant at our run lengths",
`r2-sandbox-substrate.md` §headline) stands. What a warm pool actually buys
is absorbing a **dispatch burst** (sweep wave, decomposition fan-out,
review-wave fix dispatches) without queuing claims behind node
provisioning. Sizing model:

- steady state: pool ≥ λ × T_replenish. A0: λ = 250–1,000 starts/hr
  (0.07–0.28/s) × T_r ≈ 15 s → **1–4 pods in-flight replenishment** —
  i.e. a pool of ~5 covers steady state with headroom.
- burst: to absorb a burst of B near-simultaneous dispatches at warm
  latency, pool ≥ B. Our realistic B is a decomposition landing 5–15
  children or a fix-wave — **pool 8–16 at A0**, scaling with lane
  concurrency caps at A1+.
- **Autopilot cost coupling:** a warm pod is a running pod billed at full
  requested-resource rates — a 2vCPU/4GiB warm pod ≈ $0.108/hr ≈
  **$79/mo each** at list. Pool-of-10 ≈ $790/mo — same order as the entire
  A0 active-compute bill. On Autopilot, run the pool small (≤5) and accept
  provisioning-tail latency on bursts, or use smaller warm-pod requests
  (see below). On Standard, warm pods pack into node headroom you already
  pay for — pool sizing is nearly free there, another point for Standard
  as the scale default.
- **Pod shape input from P1:** the harness wrapper idles ~100 MB RSS; the
  CLI subprocess reached ~400 MB RSS before the quota wall cut the
  measurement (a floor, not a ceiling; gVisor overhead unmeasured).
  Sensible v1 requests: 1 vCPU (agents idle on tokens; CPU oversubscribes
  2–4× on Standard) / 2 GiB request, 4 GiB limit — **memory limits are
  mandatory under the GKE Agent Sandbox template anyway.** In-cluster
  measurement (P1 §what-a-cluster-must-verify) revises this.

One structural consequence for §4: **warm pods are created before any run
exists, so nothing run-specific can arrive via env vars.** Everything
per-run must be delivered at claim time over the wire.

---

## 3. Run-class egress enforcement

Class A binds the run-class decision (enterprise spec DL 2026-07-29:
egress binds to run class; permission-layer automation is rejected as a
boundary; research traffic rides provider-side web tools + a
classifier-gated proxy-attenuator). What R2 adds is the concrete k8s
enforcement stack, verified against current GA features:

1. **Baseline (all classes): the Agent Sandbox default is necessary but
   not sufficient.** It blocks lateral movement (RFC-1918, CoreDNS
   spoofing, metadata server — the GKE credential-theft path) but allows
   the public internet. Add a default-deny egress NetworkPolicy per
   sandbox namespace on top.
2. **In-cluster allowances (all classes):** standard NetworkPolicy to
   exactly {LLM gateway service (§4), sandbox router, kube-dns}. These are
   L3/L4 rules to cluster-internal endpoints — no FQDN machinery needed.
3. **Implement lane (external):** `FQDNNetworkPolicy` (GKE Dataplane V2,
   **GA**) expressing the short list — git host + the environment class's
   package registries. Verified constraint: **max 50 resolved IPs per
   FQDN rule** (it enforces via DNS-answer snooping, so CDN-heavy
   registries with large rotating IP sets can exceed it). Mitigation that
   also serves the warm-disk ladder: an **in-cluster pull-through registry
   cache** (Artifact Registry remote repositories or a caching proxy) so
   sandbox egress for dependencies is cluster-internal, and only the cache
   process — outside the sandbox trust boundary — talks to the CDN.
   (Source: https://docs.cloud.google.com/kubernetes-engine/docs/how-to/fqdn-network-policies,
   fetched 2026-07-30.)
4. **Research/spike lane:** per Class A — primary traffic through the
   provider's server-side web_search/web_fetch (no sandbox egress change);
   residual raw fetches only via the classifier-gated proxy attenuator
   (secretless requester, headers stripped, logged); **minimum action
   authority** (no push credentials) because this lane carries maximum
   injection exposure.
5. **Self-managed parity:** Cilium `toFQDNs` policies give the same
   domain-allowlist semantics; the run-class profiles port unchanged.
6. **Enforcement placement:** profiles are k8s objects selected by pod
   labels stamped by the dispatcher at claim (`run-class: implement|
   research|review`), so the egress class is chosen by the control plane,
   never by the workload — consistent with "sandbox containment is what
   makes intra-sandbox auto-approval safe, not the reverse."

Reviewer pods (per enterprise spec §3/§5): same stack, minus push
credentials, plus the mechanical ban on mounting implementer workspace
volumes.

---

## 4. Virtual-key brokering placement

Class A's governing principle (sidecar necessity ∝
1/credential-substitutability) makes the model key the *most* substitutable
credential — LLM-gateway virtual keys are the mature product class
(enterprise spec DL 2026-07-29). Placement decisions:

1. **In-cluster, control-plane namespace, non-sandboxed, HA pair.** The
   gateway (LiteLLM-class) holds the real Anthropic/API keys sourced from
   the platform secret manager; sandbox pods can reach ONLY the gateway
   for model traffic (§3 item 2), so the real key is structurally
   unreachable from generated code — the credential-substitutability
   principle satisfied with zero sidecars for this credential class.
   In-cluster (vs hosted gateway) wins on: no external egress hole in the
   implement lane, no third-party in the token path, and per-run key
   minting on the claim path with single-digit-ms latency. The R3
   ops-agent runs OUTSIDE this cluster and must carry its own key path —
   its independence requirement is R3's, noted here so the gateway is not
   accidentally made a cluster-wide single point for agents that fix the
   cluster.
2. **Key lifecycle rides the claim lifecycle.** Dispatcher claims ticket →
   mints a virtual key (budget = the ticket's/lane's token budget; tags =
   ticket, run, fence) → delivers it in-band (below) → **revokes it on
   lease reclaim** (the spend-plane analog of the fencing token: a zombie
   pod's key dies when its lease does). Budgets and instant revocation are
   exactly what the virtual-key product class ships.
3. **Fleet auth is API-key/virtual-key ONLY — live evidence.** Both P1 and
   P2 were blocked by the OAuth subscription credential hitting its weekly
   limit mid-probe ("You've hit your weekly limit", P1) — a subscription
   quota is a fleet-wide correlated failure with a multi-day reset, which
   is disqualifying for fleet auth regardless of ToS posture. This
   confirms R1's brief line (fleet auth: never OAuth subscription) from
   direct observation.
4. **The warm-pool injection problem (needs-build, cc-harness co-design).**
   Env-var injection happens at pod creation; warm pods predate their
   runs (§2). Running pods cannot have env changed; Secret-backed
   projected volumes update too slowly/coarsely for per-claim delivery.
   The clean shape: **the claim handshake delivers the credential in-band**
   — the dispatcher passes either the virtual key itself or a short-lived
   claim token (exchanged at the gateway by the harness) as part of
   `thread/start` config over the appserver WS. P3 §f.6 verified that
   `thread/start` config crosses the wire as plain JSON (strings fine,
   objects-with-methods impossible) and that `ccx serve` today has no
   process-side default config — so this lands as one R1-reconciliation
   backlog item: *per-thread model-credential (and sessionStore selection)
   at serve/start time*. Until it ships, the workaround is the P3 fallback
   (a ~15-line custom entry point constructing `AppServer` with
   `AppServerDeps`), which is how the probe itself ran.

---

## 5. srt-inside-gVisor (probe P4 consumed)

P4 is desk-only (no cluster/Linux on this host; nothing executed) —
verdict **likely yes, medium confidence**: bubblewrap earns its power from
unprivileged `unshare(CLONE_NEWUSER)` (no `SYS_ADMIN` requested through the
pod spec, so Autopilot/GKE-Sandbox capability walls don't obviously apply);
every syscall in its sequence is listed as implemented by gVisor's Sentry;
gVisor's own rootless mode uses the identical trick; Docker-in-gVisor
(deeper nesting) is an officially documented working configuration. The one
recorded failure mode — bubblewrap unable to mount a fresh `/proc` inside a
container-shaped boundary — has a named srt fallback
(`enableWeakerNestedSandbox`) at reduced isolation.
(`probes/p4-srt-inside-gvisor.md`, incl. its exact 4-step in-cluster probe
plan with pass/fail signals.)

Platform consequences, per P4 §(c):

- **This gates a cost knob, not the architecture.** The 07-30 pivot to
  k8s already dissolved the constraint that made the two-container
  execution sidecar "inexpressible" at A0 (single-`sandboxId` substrate,
  A0 spec DL11) — pods are natively multi-container. If srt works inside
  gVisor, cheap run-classes get an inner defense layer inside one
  container; if it fails (or only the weakened mode works), the
  two-container sidecar becomes the default shape at both tiers and only
  the *cheap* inner option is lost.
- **Scheduling note for the probe:** it is the first task on cluster day
  one (its Step-1 bare check is ~5 minutes), and it must run on whichever
  cluster shape §1.3 lands (Autopilot admission is stricter — P4 Step 4).
- **Either way, srt is never the load-bearing boundary** — that stays the
  pod's egress allowlist + credential brokering (§3–§4), per DL11's
  framing and the Class-A principles.

---

## 6. Board-service internals

The full schema draft — DDL, legality table with the E1 lane states,
event/current-state split, claim function, mirror outbox, cohabitation
DDL — is the sibling deliverable **`r2-board-schema.md`** (input to the E3
platform decomposing run). This section records the design findings and
their evidence.

### 6.1 Lineage and what changes

Seed = A0 Plan 1 (`plans/2026-07-23-a0-core-board-service.md`): one small
process over one Postgres, workers never speak SQL, claim = one
transaction (`FOR UPDATE SKIP LOCKED` pick + conditional ticket UPDATE +
run INSERT + fence bump), server-side transition legality as conditional
UPDATE, per-run bearer tokens (hashes only), stale-lease reclaim. All of
that survives. Four things change:

1. **State vocabulary = live v8 + E1.** The real board's vocabulary
   (verified from `skills/issue-tracker/scripts/_board.py`, not from the
   Plan-1 frozen list) includes `deferred` and `wontfix`, which Plan 1
   lacked. E1 splits `ready-for-agent` into `ready-for-architect` /
   `ready-for-implementer`, adds `in-design`, the three
   escalation/return edges, edge-keyed note requirements, the
   convergence rule, and the pre-park return rule
   (`specs/2026-07-30-implement-lane-split-design.md`).
2. **E2's split becomes structural**: an append-only `ticket_event` log
   (any past board state reconstructible from it alone) + mutable
   current-state columns (reading current state never folds the log), an
   `env-issue` ticket category with fire-and-continue registration, and
   subagents-never-write enforced by the auth model (only the bound run's
   token writes).
3. **The heartbeat duty dissolves.** Plan 1 had workers POST session
   events as lease heartbeats. In the converged database the cc-harness
   sessionStore adapter already writes an append per SDK persist batch
   and stamps `ccs_sessions.mtime` on every fold — **progress-as-heartbeat
   becomes a reconciler JOIN on the sessionStore sidecar, zero worker
   duties** (E2's "zero new write duties" acceptance, achieved for the
   lease too). The board keeps a fallback `lease_expires_at` for the
   claim-to-session-bind window when no transcript exists yet.
4. **Claim ≠ state transition.** E1's acceptance requires the worker's
   *first board write* to be the gate verdict, so the claim no longer
   moves state (Plan 1 moved to `in-progress` at claim). Claim = set
   `owner_run` + bump fence + append a `claim` event (automation-
   authored); eligibility = lane state AND unowned. Reclaim clears
   ownership without touching state for `ready-for-*`, and applies E1's
   in-flight recovery split (resume-with-nudge for `in-design`/
   `in-progress`, fresh dispatch for pre-verdict states).

### 6.2 Claim path on the managed-postgres-core facts

The substrate-independent Postgres facts
(`research/2026-07-23-startup-scale/managed-postgres-core.md` §2) place
every connection:

- `FOR UPDATE SKIP LOCKED` claims and all single-statement/CTE writes are
  **transaction-pooler-safe** → the board API process runs entirely on
  pooled connections.
- `LISTEN` breaks under transaction pooling; session advisory locks break
  (xact-scoped are safe) → **the dispatcher/reconciler holds 1–2 direct
  connections** for `LISTEN board_events` (with the level-triggered poll
  as the mandated fallback) and uses `pg_advisory_xact_lock` (never
  session-scoped) for the per-lane concurrency-cap serialization.
- Load at A0–A1 is rounding error (claims ~0.1–0.3 txn/s; board writes
  ~1–3/s) — connection *semantics*, not throughput, drive the design.

Lane routing is data: `ready-for-architect` dispatches the Fable
architect route, `ready-for-implementer` the Opus route, with a separate
architect-lane concurrency cap (the Fable-spend lever) — the dispatcher
stays judgment-free exactly as E1 requires.

### 6.3 Mirror writers (GitHub Issues, Linear)

**Transactional outbox, one-way, coalescing.** Every event append also
inserts an outbox row in the same transaction; per-mirror writer loops
consume with SKIP LOCKED, **coalesce to newest-state per ticket**, and
map states → mirror vocabulary. Rate evidence: GitHub's binding limit is
the **~500 content-generating requests/hour/actor secondary cap**
(`board-simplification-a0.md` §1.1, verified against GitHub docs
2026-07-23) — a raw event feed (~6–12 writes/run) exceeds it from mid-A0,
a coalesced human-relevant feed (~2–3/run) fits one actor with headroom at
A0 and needs batching/sharding at A1+; Linear fits with 1–5 legitimate
App-User actors (§1.2 same report). **Class A hardens one-way-ness beyond
the 07-23 enterprise spec:** no back-edge from mirrors (the enterprise
spec's "human actions in Linear flow back as events" is superseded —
edits on a mirror never mutate the SSOT; humans act through the E3
control plane). Mirror writers therefore need no inbound webhook surface
at all — they are pure outbound daemons plus a `mirror_ref` table
(ticket ↔ external id) and a reconcile pass that repairs drift by
re-asserting board state.

### 6.4 One-Postgres convergence (board + sessionStore)

Verified live in the harness repo (Class C):
`harness/src/store/postgresSessionStore.ts` shipped 2026-07-30
(coverage.md: "Postgres adapter SHIPPED (2026-07-30, execplan
`2026-07-30-postgres-session-store`)"), with `createPostgresSessionStore`,
`ensurePostgresSessionStoreSchema`, and a `postgresSessionStoreDDL(prefix)`
export. Facts that shape cohabitation:

- **Tables:** `<prefix>_entries` (BIGSERIAL id, project_key, session_id,
  subpath, uuid, entry TEXT) + `<prefix>_sessions` sidecar (mtime, seq,
  summary). Prefix-parameterized; the adapter does not schema-qualify, so
  schema separation is done via the sessions role's `search_path`.
- **Pooler-safe by construction** — the adapter's own header: single
  statements only, uuid dedup *inside* the INSERT (partial unique index +
  ON CONFLICT), summary updates via seq-CAS with a generation token,
  "BEGIN/COMMIT is unsound here — a pooled client may serve each query()
  from a different connection." It needs no direct connections, no
  LISTEN, no advisory locks — it can ride the same transaction pooler as
  the board API.
- **Payloads are TEXT, not jsonb** (deliberately: jsonb rejects U+0000 /
  lone-surrogate escapes). Consequence for E2's derived stream: SQL
  cannot cheaply index into entry payloads; the merged timeline join is
  by `(project_key, session_id)` via the board's run binding, ordered by
  `id` within a session, with per-entry timestamps parsed at render time
  in the E3 service — not in SQL. Recorded honestly in the schema draft.
- **Load shape:** appends dominate everything (A0: ~15–100 writes/s
  steady vs ~1–3/s board, managed-postgres-core §1), and the adapter's
  summary fold does **one indexed SELECT of the session's full main
  transcript per append batch** — O(session length) read amplification
  per write. Fine at A0 (sessions are 10²–10³ rows); it is the first
  thing to watch at A1 and strengthens the standing promotion rule:
  *when shared-plane interference appears, the session store promotes
  first* (managed-postgres-core §6.1), behind the unchanged SessionStore
  interface (Redis adapter already ships as the swap target).
- **Separation levers, in escalation order** (all in the schema draft):
  separate schemas + roles (day one) → separate pooler pools sized so
  session appends cannot starve board claims (day one) → statement
  timeouts per role → table partitioning of `_entries` by time →
  physical split to a second database / Redis adapter (the promotion
  trigger; the board API contract never changes).
- **Retention:** `ticket_event` is permanent (the durable human-answer
  record — the reason Linear could never be SSOT). `_entries` follows the
  archival path: closed runs older than ~14 days promote to object
  storage with a pointer, hot set held ~100–300 GB
  (managed-postgres-core §1.1). E2 explicitly defers derived-stream
  retention policy; the schema leaves it a job, not a schema property.

### 6.5 Discovery: the board owns `thread → pod`

P3 §f.4 verified `thread/list` is a per-process in-memory registry — a
ClusterIP round-robin is unusable. The board's `run` table therefore
carries `pod` (stable DNS name — from the Agent Sandbox `Sandbox` stable
identity, §1.2), `session_id`, `project_key`, and `thread_id` — making
"which pod holds ticket N's session" a board row, exactly the shape P3
recommended ("the board is the registry"). The E3 gateway resolves
terminals and decision-park subscriptions through it. Park durability
stays P3's honest ceiling (turn-level, not decision-level): a pod restart
loses parked SDK decisions; turns resume via `thread/resume` against the
shared sessionStore — the board's event log records board-parks (which DO
survive), and the appserver-park mirroring question stays an R1/harness
item, not a schema one.

---

## 7. Through-question contribution

**At the platform layer the answer is: one architecture, two knobs.**
Evidence assembled above: (a) the CRD layer is identical across
Autopilot / Standard / self-managed (§1); (b) the egress stack has a
1:1 mapping between GKE (`FQDNNetworkPolicy`) and self-managed (Cilium
`toFQDNs`) (§3); (c) the board schema is substrate-independent Postgres
riding facts that hold on every credible host (§6.2); (d) the credential
plane is an in-cluster deployment either way (§4). The knobs are: cluster
mode (Autopilot at A0 → Standard+CUD+NVMe pools at scale → self-managed
iff R3's bar is met) and warm-pool size (a cost dial on Autopilot, nearly
free on Standard). What R2 canNOT settle: whether the *economics* also
unify (R4 — flexible-vs-resource CUD math, warm-pool carrying cost,
managed-Postgres vs Cloud SQL at each tier) and whether *ops* unify (R3 —
whether one ops-agent runbook really spans Autopilot and self-managed,
which differ enormously in what there is to operate).

---

## 8. What only a cluster can verify (honest list)

1. **P4 in-cluster probe** (first task, both cluster shapes) — §5.
2. Warm-pool claim latency and replenish time distributions under our
   image; Autopilot pod-provisioning tail on pool exhaustion (§2).
3. GKE addon CRD version vs upstream `v1beta1` skew at install time (§1.1).
4. `FQDNNetworkPolicy` behavior against registry CDNs (50-IP cap in
   practice); whether the pull-through cache removes the need (§3).
5. Per-thread credential delivery over `thread/start` end-to-end with a
   real model turn (blocked this session: both local credentials
   exhausted — the same evidence backing §4.3).
6. Agent Sandbox `Sandbox` stable-DNS identity as the pod-addressability
   mechanism for the appserver seam (replacing P3's StatefulSet
   suggestion) (§6.5).
7. cc-harness pod RSS ceiling under gVisor with a completed multi-turn
   run (P1's floor-only measurement), and the linux-x64/arm64 CLI binary
   size (§2).
8. sessionStore fold read-amplification at realistic session lengths
   under concurrent appenders (§6.4).
9. Actual Autopilot resource-CUD purchasability (docs-vs-tracker
   discrepancy, §1.3) — a purchase-console fact.

## Sources

**Class C re-fetched 2026-07-30:**
https://docs.cloud.google.com/kubernetes-engine/docs/how-to/agent-sandbox ·
https://agent-sandbox.sigs.k8s.io/docs/getting_started/overview/ ·
https://github.com/kubernetes-sigs/agent-sandbox (+ /releases) ·
https://docs.cloud.google.com/kubernetes-engine/cud ·
https://www.cloudzero.com/blog/gke-pricing/ (pricing verified Apr 2026 per
the page) ·
https://docs.cloud.google.com/kubernetes-engine/docs/concepts/sandbox-pods ·
https://docs.cloud.google.com/kubernetes-engine/docs/how-to/fqdn-network-policies ·
https://docs.cloud.google.com/kubernetes-engine/docs/concepts/local-ssd ·
https://www.usage.ai/blogs/gcp/committed-use-discounts/ ·
cc-harness repo: `/Users/new/developer/github/codex_somersault/CC-to-SDK`
(`harness/src/store/postgresSessionStore.ts`, `docs/parity/coverage.md`).

**Round probes:** `probes/p1-pod-footprint.md` ·
`probes/p3-cross-pod-appserver.md` · `probes/p4-srt-inside-gvisor.md`.

**Class A:** `specs/2026-07-30-implement-lane-split-design.md` ·
`specs/2026-07-30-ticket-ledger-observability-design.md` ·
`specs/2026-07-30-control-plane-product-design.md` ·
`specs/2026-07-23-cloud-scale-reference-architecture-design.md` (DL
2026-07-29 entries).

**Class B:** `research/2026-07-23-cloud-scale/r2-sandbox-substrate.md` ·
`research/2026-07-23-startup-scale/managed-postgres-core.md` ·
`research/2026-07-23-startup-scale/board-simplification-a0.md` ·
`research/2026-07-23-startup-scale/sandbox-substrate-a0.md` (rejected-
alternatives record) · `plans/2026-07-23-a0-core-board-service.md`.

**Live repo reads:** `skills/issue-tracker/scripts/_board.py` (v8 state
vocabulary), `skills/issue-tracker/SKILL.md` (board:meta fields).
