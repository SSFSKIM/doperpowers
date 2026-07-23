# A0 — Managed sandbox substrate for the worker/reviewer pipeline at startup scale

**Date:** 2026-07-23. **Scenario:** a 10–20 person AI-native startup runs the
board pipeline (workers = Claude Code harness sessions with skills). Needs per
run: git clone/push with token isolation, network egress control,
persistent-ish workspace restore keyed by environment content hash, session
log streaming out. **Scale anchor A0:** ~50–200 concurrent runs, ~250–1,000
run starts/hour during work hours, mean run ~10–15 min. **Ops posture:
ZERO-OPS** — no dedicated infra engineer; infra budget $1–5k/month excluding
model tokens.

**Relation to prior research:** the enterprise verdict
(`../2026-07-23-cloud-scale/r2-sandbox-substrate.md` — own k8s+gVisor fleet on
NVMe hosts) was driven by cost at ~1,000–20,000 sustained concurrent
(~$73k+/mo SaaS vs ~$5–15k/mo self-host) plus an ops team to absorb the fleet.
At A0 both drivers invert: the SaaS bill fits inside $5k/mo, and the ops team
does not exist. This report re-runs the substrate evaluation under those
constraints. Nothing here touches the semantic layer.

---

## 1. Fermi baseline (stated assumptions)

- Run starts: ~5,000/workday (≈500/hr × 10 work hours; top of the stated
  250–1,000/hr band at mid-day).
- Mean run 12.5 min → ~1,040 run-hours/day → **~23k run-hours/month on a
  22-workday month; call it 25–30k run-hours/month** with weekend stragglers
  and retries. I use **27.5k run-hours/month** below.
- Shape per run: **2 vCPU / 4 GiB RAM / ~15–20 GB disk** (Claude Code harness
  + clone + deps; CPU mostly idle waiting on tokens).
- Peak concurrency check: 500 starts/hr × 12.5 min ≈ 104 concurrent
  steady-state; bursts to ~200. Consistent with the anchor.
- Run starts: ~150k/month (matters only for per-creation fees and API rate
  limits).
- All monthly figures are provisioned-duration billing unless a vendor bills
  active-CPU only (noted where so). List prices, no negotiated discounts.

**Cost formula:** monthly ≈ 27.5k × (2 × CPU-rate/vCPU-hr + 4 × RAM-rate/GiB-hr)
+ plan fee. Vendor-claimed numbers are marked (V); independently corroborated
or first-party-documented numbers (D); my arithmetic (F).

## 2. Candidates

### 2.1 E2B (e2b.dev)

- **Pricing (D, first-party pricing page):** 2 vCPU $0.000028/s =
  $0.1008/hr; RAM $0.0000045/GiB-s = $0.0162/GiB-hr; storage free (20 GiB on
  Pro). Pro plan $150/mo. Per-run-hour: $0.1008 + 4×$0.0648/4 → **$0.1656/hr**.
- **A0 monthly (F): 27.5k × $0.1656 + $150 ≈ $4,700/mo.** At 1 vCPU where
  sufficient: ≈ $3,300/mo. **Top edge of the $1–5k budget.**
- **Cold start:** ~150 ms Firecracker create (V, widely repeated; consistent
  with prior research); resume from pause ≈ 1 s (D, docs); pause ≈ 4 s/GiB
  RAM (D, docs).
- **Snapshot/restore keyed by hash:** two mechanisms. (a) **Custom templates**
  built from a Dockerfile — name the template with the env content hash;
  exact-match restore = create-from-template. (b) **Pause/resume persistence**:
  paused sandboxes kept indefinitely, filesystem+memory or filesystem-only
  (D, docs). Paused-storage pricing **not published — absence of evidence,
  ask sales before relying on a large paused fleet.**
- **Git credential isolation:** env vars injected at sandbox create; wire a
  short-lived GitHub App installation token into the remote URL at init
  (our standard pattern). No platform-native git-credential broker (absence).
- **Egress control (the differentiator):** internet on by default; can be
  disabled per sandbox; **domain-based allowlists with wildcards, plus IP/CIDR
  blocks, updateable on a running sandbox** (D, docs
  e2b.dev/docs/sandbox/internet-access). This is the only candidate at this
  price point where "allow github.com + api.anthropic.com + registry.npmjs.org,
  deny everything else" is expressible directly.
- **API quality:** purpose-built SDK (create/exec/PTY/stream/kill), 20,000
  requests per 30 s rate limit on lifecycle ops (D, docs) — ~3 orders above
  our ~0.3 starts/sec.
- **Concurrency:** Hobby 20 → Pro **100 base, purchasable up to 1,100**
  (D, pricing page). A0 peak ~200 fits; extra-concurrency pricing not
  published (absence).
- **Reliability:** status.e2b.dev shows 99.99–100% across Mar–Jun 2026; one
  notable incident Mar 5, 2026 (sandbox create/pause/resume error rates,
  US+EU) (D, status page). Best public record of the pure-play sandbox
  vendors.

### 2.2 Daytona (daytona.io)

- **Pricing (D, first-party):** $0.0504/vCPU-hr, $0.0162/GiB-hr, storage
  $0.000108/GiB-hr after 5 GiB free; $200 sign-up credit. Per-run-hour
  **$0.1656 + ~$0.002 storage** — identical compute rate to E2B.
- **A0 monthly (F): ≈ $4,600/mo.** No plan fee.
- **Cold start:** ~90 ms claimed (V, marketing; not independently verified);
  warm pools of pre-created sandboxes supported (D, docs).
- **Snapshot/restore keyed by hash:** the cleanest fit on paper —
  **snapshots are named, uniquely-identified images** built from
  Dockerfile/declarative builder or captured from a running sandbox
  (container = filesystem-only; VM class = memory too); `latest`-style mutable
  tags are explicitly unsupported, forcing digest discipline (D, docs). Name =
  env hash gives exact-match restore. Unlimited session length.
- **Git credential isolation:** same env-injection pattern; nothing native.
- **Egress control — the weak point:** `networkBlockAll` or
  `networkAllowList` of **at most 5 IPv4 CIDR blocks** (D, docs
  daytona.io/docs/en/network-limits). Domain names are not supported.
  GitHub's published git/API ranges alone exceed 5 CIDRs, and
  api.anthropic.com has no stable published CIDR — so at A0 the practical
  choices are block-all (breaks the harness), mostly-open (weakens token
  containment), or run your own egress proxy (ops you don't have). Dynamic
  policy updates gated to Tier 3+.
- **API quality:** strong SDK (create/exec/sessions/logs); sandbox creation
  rate-limited at 300–600 ops/min by tier (D, limits docs) — fine.
- **Concurrency/quota:** tiered by total org compute — Tier 3 ($500 top-up):
  250 vCPU = ~125 concurrent 2-vCPU runs; **Tier 4 ($2k/mo top-up): 500 vCPU
  = ~250 concurrent** (D, limits docs). A0 needs Tier 4; the top-up is below
  the organic bill, so not a real cost adder.
- **Reliability:** status page shows May 1, 2026 downtime (self-inflicted
  rate-limit misconfiguration) and Jun 27, 2026 degraded runners (D, status
  page). Acceptable, slightly worse record than E2B.

### 2.3 Modal (modal.com)

- **Pricing (D, first-party):** Sandboxes are billed at ~3× Modal's normal
  compute: $0.00003942 per **physical core**-second (1 physical core ≈ 2 vCPU)
  = $0.1419/hr for our 2 vCPU, + $0.00000667/GiB-s = $0.0240/GiB-hr →
  per-run-hour **$0.238**. Team plan $250/mo (includes $100 credits).
- **A0 monthly (F): ≈ $6,800/mo. Over budget at list.**
- **Cold start:** warm sub-second; cold with image pull can be 10 s+ (prior
  research, corroborated by vendor comparisons).
- **Snapshot/restore:** images cached by content; filesystem snapshots →
  restorable images; memory snapshots exist. Good fit technically.
- **Egress control:** best-in-class — `block_network`, CIDR allowlist, and
  **domain allowlist (beta, TLS-only)**, plus experimental runtime policy
  updates (D, docs modal.com/docs/guide/sandbox-networking).
- **Concurrency:** Team plan 1,000 containers (D, pricing).
- **Reliability:** Sandboxes component 99.841% (D, status aggregators);
  2026 incidents include **Apr 27 — 6.5 h degradation caused by a CIDR
  allowlist code change** (exactly the feature we would depend on), Apr 28
  16.5 h degradation, May 6 2.4 h downtime, June database incident.
- **Verdict:** technically excellent, ~1.4–1.5× E2B/Daytona on price at A0
  → eliminated on budget, would re-enter with a negotiated rate.

### 2.4 Northflank sandboxes

- **Pricing (D, first-party):** $0.01667/vCPU-hr + $0.00833/GB-hr → per
  run-hour **$0.0667** — the cheapest published rate among managed platforms.
- **A0 monthly (F): ≈ $1,830/mo. Comfortably in budget.**
- **Cold start:** microVM boot "under a second" (V, product page).
- **Isolation:** Kata/gVisor microVMs (V, product page; consistent with
  their engineering blog).
- **Snapshot/restore:** image/build-service based (build from Dockerfile,
  registry-backed) — hash-keyed images work; **no published sandbox-native
  snapshot-of-running-state API** (absence of evidence).
- **Egress control:** **no published per-sandbox egress allowlist** for the
  managed platform (absence of evidence — their sandbox marketing pages do
  not document it; network policy control exists in BYOC/k8s mode where you
  own the cluster).
- **API quality:** full REST/CLI for create/exec/destroy; the platform is a
  general PaaS first, sandbox product second — orchestration primitives are
  there but the agent-sandbox SDK surface is younger than E2B/Daytona's.
- **Concurrency:** "10,000+ isolated workloads" claimed (V); no published
  per-plan concurrency table (absence).
- **Reliability:** no public incident history found for the sandbox product
  specifically (absence of evidence, not evidence of absence).

### 2.5 Fly Machines

- **Pricing (D, first-party):** shared-cpu-2x preset $4.04/mo (512 MB) +
  ~$5/GB/30d additional RAM → 2 vCPU/4 GB ≈ $21.5/mo full-time ≈
  **$0.0295/hr**, billed per second. A0 monthly (F): **≈ $800–900/mo** —
  cheapest managed option by 2×.
- **Cold start:** ~250 ms boot when image is on the host; image pull
  dominates otherwise. No snapshot-restore of running state you can rely on
  (suspend/resume exists; prior research documented >30 s resumes, clock
  bugs, snapshots discarded on deploy/migration).
- **Workspace restore:** build one OCI image per env hash, push to Fly's
  registry, boot machines from it — workable and exact-match, but **you own
  the image build pipeline**.
- **Egress control: none platform-native** (no per-machine egress
  allowlist; you'd run your own proxy/WireGuard — ops).
- **API quality:** the Machines REST API is genuinely good
  (create/start/exec/destroy, per-second billing); but log streaming out is
  DIY (fly-log-shipper/NATS), and there is no agent-sandbox SDK.
- **Concurrency/quota:** no hard published ceiling; **regional capacity is a
  real operational hazard** — placement fails when a region is out of
  capacity; Fly added capacity APIs precisely because users hit this (D,
  community/docs).
- **Reliability:** Jan 2026 management-plane outages of **15 h and 11 h**
  (D, status aggregators) — run *starts* stall even though running machines
  keep running; a mid-day 11 h dispatch stall is a pipeline-wide outage for
  us. July 2026 Machines-API auth incident.
- **Verdict:** the price is tempting, but at zero-ops it re-imports exactly
  the DIY layers (egress proxy, image builder, log shipping, capacity
  management) the scenario forbids.

### 2.6 Runloop (runloop.ai)

- **Pricing (D, first-party):** $0.108/CPU-hr + $0.0252/GB-hr → per-run-hour
  **$0.3168**; Pro $250/mo (needed for production: suspend/resume, repo
  connections). A0 monthly (F): **≈ $9,000/mo. ~2× over budget.**
- **Fit notes:** devboxes + **blueprints (templates) + snapshots** are
  purpose-built for coding agents — the feature shape (repo connections,
  suspend with zero compute charge, 10k concurrent devboxes demonstrated by
  a customer (V, press)) matches our pipeline closely. Concurrency quota
  tables not published (absence). No public status/incident history found
  (absence).
- **Verdict:** right shape, wrong price at list. Re-enters only with a
  negotiated rate cut of ~2×.

### 2.7 Morph (morph.so)

- **Pricing (V, subscribe page via search — could not fetch the page
  directly):** billed in MCU-hr where MCU = max(vCPU, ceil(RAM/4 GiB),
  ceil(disk/16 GiB)); $0.05/MCU-hr. Our shape = 2 MCU → **$0.10/hr** → A0
  (F) **≈ $2,750/mo + snapshot storage.** $40/mo tier caps at **256 vCPU ≈
  128 concurrent 2-vCPU runs — below the A0 peak of 200**; enterprise tier
  required above that.
- **Snapshot/branch/restore <250 ms (Infinibranch)** is the headline feature
  (V, first-party blog) — the strongest snapshot story in the field, and
  overkill at 10–15 min runs (a 1–5 s start is 0.3–0.8% overhead).
- **Egress control / quotas / reliability:** no published egress policy
  feature, no published status page or incident history, small vendor
  (absence of evidence across the board).
- **Verdict:** interesting price and unique tech; too many unknowns for a
  zero-ops default. Candidate for a 1-day spike if E2B/Daytona pricing
  becomes a problem.

### 2.8 Discovered candidates

- **Vercel Sandbox** — Firecracker microVMs; $0.128 per **active**-CPU-hr +
  $0.0212/GB-hr provisioned + $0.60/1M creations (D, docs). Because coding
  agents idle on tokens, active-CPU billing is structurally favorable: at
  ~25% CPU duty, per-run-hour ≈ $0.149 → **≈ $4.1k/mo (F)**; at 10% duty ≈
  $3.1k/mo. **2,000 concurrent on Pro, 24 h max duration** (D, changelog).
  Unknowns: no published egress allowlist, no snapshot/restore (image
  bootstrap only), base-image flexibility limited. A real dark horse if its
  egress story materializes.
- **Cloudflare Sandboxes** (on Containers) — active-CPU-only billing
  ($0.000020/vCPU-s) + $0.009/GiB-hr memory → **≈ $2k/mo (F)**; limits now
  ample (1,500 vCPU / 6 TiB org-wide, Feb 2026 raise) (D, docs/changelog).
  But: no snapshot/restore, thin egress control, orchestration must ride
  Workers/Durable Objects, 2–3 s cold starts (V). Wrong shape for a
  git-heavy 4 GiB workspace pipeline today.

### 2.9 Baseline: 2–3 Hetzner boxes + Docker (self-managed)

- **Pricing (D, Hetzner):** AX102 (16-core Ryzen, 128 GB, 2×1.92 TB NVMe)
  €124/mo; AX162-R (EPYC, 256 GB, 2×1.92 TB NVMe) from €199/mo. RAM-packing
  at 4 GiB/run with ~20% headroom: ~25–28 runs per 128 GB box, ~55 per
  256 GB box. **A0 peak (200 concurrent) ≈ 3× AX162-R ≈ €600 ≈ $650/mo; the
  ~100-concurrent steady state fits 2 boxes ≈ $450/mo.** 5–8× cheaper than
  E2B/Daytona, 15× cheaper than Modal.
- **What the price buys you into owning:** Docker-per-run lifecycle,
  an egress proxy (Anthropic sandbox-runtime-style domain allowlist —
  the one piece with no managed equivalent on the box), image/snapshot cache
  keyed by env hash (Docker images make this easy), host patching, capacity
  planning, disk GC, on-call for two hosts, and the same runner/daemon
  plumbing `infra/worker-host/README.md` documents for one VM. Realistic
  steady-state burden: **~0.1–0.2 FTE of a senior engineer, spiky** — which
  is precisely what the zero-ops posture says the startup does not have.
  It also concentrates all runs on 2–3 failure domains with no warm-pool
  or API-driven quota elasticity.
- **When it is right anyway:** if the team decides $3–4k/mo of savings is
  worth a rotating infra chore, the current single-VM playbook scales to 3
  boxes without new architecture. This is a legitimate frugal choice, not
  the default under the stated posture.

## 3. Comparison table (A0: 27.5k run-hr/mo, 2 vCPU/4 GiB, ~150k starts/mo)

| Substrate | $/run-hr | A0 monthly (F) | In $1–5k? | Hash-keyed restore | Egress allowlist | Concurrency ceiling | Public reliability record |
|---|---|---|---|---|---|---|---|
| **E2B** | $0.1656 | **~$4.7k** | at the edge | templates + pause | **domains + CIDR, runtime-updatable** | 100→1,100 (Pro) | good (99.99–100% Mar–Jun '26, 1 incident) |
| **Daytona** | $0.1656+stor | ~$4.6k | at the edge | **named snapshots, digest-pinned** | CIDR only, **max 5 blocks** | Tier 4: 500 vCPU (~250 runs) | fair (2 incidents May–Jun '26) |
| Modal | $0.238 | ~$6.8k | no | fs+memory snapshots | domains (beta) + CIDR | 1,000 containers (Team) | fair; Apr '26 CIDR-feature incident |
| Northflank | $0.0667 | **~$1.8k** | yes | images (no live snapshot API published) | not published | not published | none published |
| Fly Machines | ~$0.0295 | ~$0.9k | yes | DIY images; suspend unreliable | **none** | regional capacity risk | poor (Jan '26: 15 h + 11 h mgmt-plane outages) |
| Runloop | $0.3168 | ~$9k | no | blueprints + snapshots (purpose-built) | not published | 10k demonstrated (V) | none published |
| Morph | ~$0.10 | ~$2.8k | yes | **Infinibranch <250 ms** (V) | not published | 256 vCPU on paid tier (<A0 peak) | none published |
| Vercel Sandbox | ~$0.15 (duty-dep.) | ~$3–4.5k | yes | none (image bootstrap) | not published | 2,000 (Pro) | good (platform-level) |
| Cloudflare | ~$0.07 | ~$2k | yes | none | thin | 1,500 vCPU org | good (platform-level) |
| Hetzner 2–3 boxes | — | **~$0.45–0.65k** | yes | DIY (easy w/ Docker) | DIY proxy | you own it | you own it |

## 4. Verdict

**Default: E2B (Pro, ~$4.3–4.9k/mo at list; ~$3.3k if 1-vCPU runs prove
sufficient).** It is the only candidate inside the budget that satisfies the
security-critical requirement natively: **domain-level egress allowlisting**
("github.com + api.anthropic.com + package registries, deny rest"), which is
what makes short-lived-token git isolation actually contain a prompt-injected
worker. It also has exact-match template restore, pause/resume, 1,100
concurrency headroom (5× A0 peak), lifecycle rate limits three orders above
our start rate, and the best public uptime record in the category. Actions
before committing: get paused-storage and extra-concurrency pricing in
writing, and pressure-test the $4.7k list price for a startup discount —
at list it consumes the whole infra budget.

**Runner-up: Daytona (~$4.6k/mo).** Identical compute price, arguably the
cleanest hash-keyed snapshot model (uniquely-named, digest-pinned snapshots +
warm pools) and unlimited session length. It loses the default on one
concrete gap: egress control is 5 CIDR blocks max, which cannot express our
allowlist — the fallback (mostly-open egress) meaningfully weakens token
containment, and the fix (own proxy) violates zero-ops. **Swap to Daytona
if:** E2B refuses acceptable terms on price/concurrency, or Daytona ships
domain-based egress rules (watch daytonaio/daytona issue #3357 — dynamic
egress control is on their radar), or our egress requirement relaxes to
block-all-with-proxy anyway.

**Budget escape hatch: Northflank (~$1.8k/mo)** if the bill must sit
mid-budget rather than at the top — accepting undocumented egress control
and a younger sandbox API (verify both in a spike before committing).
**Fly Machines and Hetzner are the frugal endpoints** ($0.9k / $0.5k) and
both re-import ops the posture forbids; Hetzner is the better of the two if
frugality wins, since the team already runs the single-VM version of it.

**Swap conditions on the default (explicit thresholds):**

1. **Price/volume flip:** sustained run-hours ≥ ~2× A0 (≥55–60k run-hr/mo →
   ≥$9k/mo at E2B list) breaks the budget → renegotiate to enterprise
   pricing, or drop to Northflank, or accept the Hetzner ops tax.
2. **Concurrency flip:** sustained peak > ~1,100 concurrent (E2B's published
   purchasable ceiling) → enterprise tier or substrate change.
3. **Duty-cycle flip:** if measured CPU duty is ≤ ~15%, Vercel Sandbox's
   active-CPU billing undercuts E2B at equal capability minus egress —
   re-run this comparison if Vercel publishes an egress allowlist.
4. **Reliability flip:** any month with ≥ 2 dispatch-blocking vendor
   incidents (run starts failing during work hours) → activate the runner-up
   and keep both SDK paths warm (the pipeline's substrate surface is small:
   create-from-template / exec-stream / destroy — keep it behind one thin
   adapter so this swap is a config change, not a rewrite).

**When the enterprise own-fleet answer becomes right again:** the k8s+gVisor
fleet re-enters when *either* (a) the managed bill sustains ≥ ~$25–30k/mo —
i.e. ~150–200k run-hr/mo, roughly **300–500 sustained concurrent runs, 5–10×
A0** — at which point the SaaS-vs-self-host gap (~$73k vs ~$5–15k at 1,000
concurrent, per the enterprise track) funds a dedicated infra engineer with
margin; or (b) a compliance/data-residency mandate forces BYOC regardless of
cost (Daytona and Northflank both offer BYOC as an intermediate step that
keeps the same API). Below that line, at A0, the enterprise verdict is
inverted: **the fleet you don't operate is worth ~3–4× the raw compute
premium.**

## 5. Confidence notes

- **High confidence (first-party docs/pricing fetched this session):**
  E2B rates, tiers, concurrency, egress features, rate limits, pause
  behavior; Daytona rates, tier quotas, 5-CIDR egress limit, snapshot
  model; Modal sandbox rates, tiers, network controls; Fly pricing
  presets and volume/egress rates; Northflank compute rates; Runloop
  rates and tiers; Vercel Sandbox rates, 2,000-concurrency, 24 h duration;
  Cloudflare Containers rates and Feb 2026 limit raises; Hetzner AX
  pricing class.
- **Medium confidence (vendor-claimed, not independently verified):**
  all cold-start latencies (~90–250 ms claims); Northflank isolation and
  scale claims; Runloop 10k-concurrent customer story; Morph MCU pricing
  (from search snippets of their subscribe page — their pricing page did
  not render to fetch); status-page summaries relayed via aggregators.
- **My arithmetic (F):** every monthly figure; the 27.5k run-hr/mo basis;
  the 25% CPU-duty assumption for active-billed vendors; Hetzner packing
  density (calibrated to the enterprise track's RAM-packing analysis, not
  measured).
- **Notable absences of evidence (flagged, not resolved):** E2B
  paused-storage and extra-concurrency pricing; Northflank sandbox egress
  and concurrency documentation; Runloop and Morph public reliability
  records; Vercel/Cloudflare egress allowlisting. The single most
  independent benchmark found (Superagent, Jan 2026) publishes no
  methodology — treat every latency table in vendor comparisons as
  marketing until self-measured.
- **Biggest uncertainty:** the real bill. It is linear in run-hours and
  provisioned shape, and A0's band (250–1,000 starts/hr, 10–15 min means)
  spans ~2.5× — the honest monthly range at E2B list is **~$2–7k**, which
  straddles the budget ceiling. First week on any vendor: measure actual
  run-hour consumption and CPU duty before trusting any row of §3.

## 6. Sources

Pricing/limits (first-party): https://e2b.dev/pricing ·
https://e2b.dev/docs/sandbox/internet-access ·
https://e2b.dev/docs/sandbox/persistence · https://e2b.dev/docs/sandbox/rate-limits ·
https://www.daytona.io/pricing · https://www.daytona.io/docs/en/limits/ ·
https://www.daytona.io/docs/en/network-limits/ ·
https://www.daytona.io/docs/en/snapshots/ · https://modal.com/pricing ·
https://modal.com/docs/guide/sandbox-networking · https://fly.io/docs/about/pricing/ ·
https://northflank.com/pricing · https://northflank.com/product/sandboxes ·
https://runloop.ai/pricing · https://cloud.morph.so/web/subscribe (via search) ·
https://vercel.com/docs/sandbox/pricing ·
https://vercel.com/changelog/vercel-sandbox-increases-concurrency-and-port-limits ·
https://vercel.com/changelog/vercel-sandbox-can-now-run-for-up-to-24-hours ·
https://developers.cloudflare.com/containers/pricing/ ·
https://developers.cloudflare.com/sandbox/platform/limits/ ·
https://www.hetzner.com/dedicated-rootserver/ax102/ ·
https://www.hetzner.com/dedicated-rootserver/ax162/configurator/

Reliability: https://status.e2b.dev/ · https://status.app.daytona.io/incidents ·
https://status.modal.com/ · https://isdown.app/status/modal-labs ·
https://status.flyio.net/ · https://statusgator.com/services/flyio/machines-api ·
https://community.fly.io/t/regional-capacity-in-machines-api-and-flyctl/24843

Comparisons (secondary, used with caution):
https://www.superagent.sh/blog/ai-code-sandbox-benchmark-2026 ·
https://northflank.com/blog/ai-sandbox-pricing ·
https://www.agenticwire.news/article/e2b-vs-modal-agent-sandbox-cost-comparison ·
https://www.beam.cloud/blog/e2b-pricing-explained ·
https://github.com/daytonaio/daytona/issues/3357

Internal: `docs/doperpowers/research/2026-07-23-cloud-scale/r2-sandbox-substrate.md`
(enterprise verdict this report inverts) · `infra/worker-host/README.md`
(current single-VM baseline).
