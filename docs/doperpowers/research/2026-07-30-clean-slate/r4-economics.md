# R4 — Economics remeasure (2026-07-30)

> **Round:** clean-slate R1–R4 (`round-brief.md` §R4). **Class A held
> throughout:** both tiers k8s + gVisor; runtime = cc-harness; Postgres SSOT
> board with GitHub/Linear as one-way mirrors; the two governing principles.
> R4 does not re-litigate the substrate — it prices it.
>
> **Baseline / counterfactual:**
> `research/2026-07-23-startup-scale/zero-ops-economics-a0.md` (Class B). Every
> number in that document is treated as **stale by round policy** and is quoted
> only to show movement.
>
> **Inputs consumed:** `r1-runtime-gaps.md` (pod anatomy, turn-durability
> ceiling, fleet-auth verdict), `r2-platform.md` + `r2-board-schema.md`
> (cluster shape, warm-pool coupling, Postgres cohabitation, lane routing),
> `r3-agent-ops.md` (the refined agent-ops cost band and the spike's promotion
> bar).
>
> **Method note — what is live and what is not.** Every price in §2 was
> fetched from the web on **2026-07-30** and carries its URL. Three classes of
> figure are *not* live and are labelled inline: (a) **derived** — my
> arithmetic on live rates; (b) **inherited** — workload assumptions taken from
> the 07-23 anchors (run-hours, per-run token volumes) that no one has ever
> measured; (c) **not re-fetched** — object storage, log-vendor, and secrets
> pricing, where the 07-23 figures are small enough that re-fetching would not
> move a verdict (flagged at each use). No cluster and no billing account
> exists in this environment, so **nothing here is a measured bill**; §11 lists
> what only a live cluster can settle.

---

## 0. Verdict up front

1. **Replacing the human-engineer constant with the agent-ops constant moves
   the self-host/managed crossover by roughly two orders of magnitude.** The
   07-23 model priced self-hosting at infra + 0.1–0.2 FTE of a senior engineer
   (~$3.1k/mo) or a dedicated hire (~$20.8k/mo), which put the crossover at
   **300–500 sustained concurrent runs**. With R3's measured-design agent-ops
   term (~$150/mo central, $500/mo ceiling) the crossover falls to **≈3.7k–5.8k
   run-hours/month, i.e. 5–8 sustained concurrent runs** (§7). Below that, a
   managed sandbox is genuinely cheaper; above it — which includes every point
   in the A0 band and everything beyond — self-host wins on cost with no
   labour offset.
2. **At the A0 anchor (27.5k run-hr/mo, 2 vCPU / 4 GiB) self-host is ~1.9×
   cheaper on-demand and ~2.5–2.7× cheaper on Spot than the agent-sandbox
   leaders.** Full bill of materials: **≈$2.3–2.5k/mo** (GKE Standard,
   on-demand) or **≈$1.7–1.9k/mo** (Spot sandbox pool) against **$4.6–4.7k/mo**
   for E2B or Daytona at list (§4).
3. **GKE Autopilot is not an economic tier — it is an ops purchase priced like
   a managed sandbox.** At A0, Autopilot lands at **$3.0k/mo list, $3.6k with a
   warm pool of 8**, versus $1.7–2.4k for Standard: a **~$1.9k/mo premium for
   node ops that the agent-ops layer already removes for ~$150/mo**. R2 kept
   Autopilot as "the A0 entry"; the economics say make Standard the default at
   both tiers and keep Autopilot as break-glass (§4.4, §9).
4. **Self-managed bare metal no longer clears R3's ≥2× gate, and probably
   never re-enters.** GKE Standard with a 3-year resource CUD prices the
   enterprise anchor at **~$14.7k/mo**; a Hetzner-class fleet at the same
   concurrency is **$5.4k–15.2k/mo** depending on which of three mutually
   inconsistent live sources is right about the rate card. The 5–10× gap the
   07-23 research assumed has collapsed to **0–2.7×**, and Hetzner raised cloud
   prices **94–192% on 2026-06-15** (live-verified) — the input price is not
   stable enough to justify a hardware ops catalog (§5, §8 FT6).
5. **Token:infra is ~40–260× (mid ≈100×) — the ratio survived a complete
   re-price**, which is itself the finding: it was 60–170× on 07-23 and is
   unchanged in order of magnitude after every input moved. Infra is
   **0.4–2.7% of all-in spend**; the entire managed-vs-self-host delta
   (~$2.1–2.9k/mo) is **≈5–7 hours of mid-volume token burn** (§6.4).
6. **The E1 architect lane is worth 12–49× the whole infrastructure question.**
   A Fable-5 run costs **$9.72** against **$1.94** for a Sonnet-5 implementer
   run on identical run shape (5.0×). Routing 15% of runs to the architect lane
   adds **~$103k/month** at A0-mid — versus $2.1–2.9k/month for the entire
   self-host-vs-managed decision. R2's "architect-lane concurrency cap (the
   Fable-spend lever)" is the highest-value dial in the system (§6.3).
7. **A scheduled cost event lands in 32 days.** Sonnet 5 introductory pricing
   ($2/$10 per MTok) expires **2026-08-31**, after which the rate is $3/$15 —
   **+50% on the Sonnet line, ≈+$86k/month at A0-mid**. Budget for it now
   (§6.2).
8. **Through-question, economic half: one architecture holds.** The cost
   function is identical across tiers; what differs is *procurement*, not
   design. R4 names a third knob R2/R3 did not: **the discount instrument** —
   Spot at A0 (duty cycle ~30%, which fails both CUD break-evens) and 3-year
   resource CUD at enterprise (duty cycle ~100%). One architecture, three
   knobs: cluster mode, discount instrument, warm-pool size (§9).

---

## 1. Basis, anchors, and what carries over unexamined

Two anchors, both **inherited** from the 07-23 work and re-used unchanged so
the remeasure is a like-for-like comparison against the baseline:

| Anchor | Definition | Source |
|---|---|---|
| **A0** | 27.5k run-hours/month at 2 vCPU / 4 GiB; ~250–1,000 starts/hr work-hours-weighted; mean run 10–15 min; ≈3–5k runs/day | `sandbox-substrate-a0.md` §1 (inherited) |
| **Enterprise** | 1,000 sustained concurrent runs, 24/7 → 730k pod-hours/month | `2026-07-23-cloud-scale/r2-sandbox-substrate.md` Q4 (inherited) |

Two derived quantities used throughout:

- **A0 average concurrency** = 27,500 ÷ 730 h = **37.7** pods averaged over the
  whole month.
- **A0 duty cycle.** Work-hours-weighted load concentrates into roughly
  10 h × 22 workdays = 220 h/month, so mean concurrency *inside the window* is
  27,500 ÷ 220 = **125 pods**, and the fleet's duty cycle is
  220 ÷ 730 = **30%**. This number does more work in §9 than any price does.

**Neither anchor has ever been measured.** They are Fermi estimates from the
07-23 rounds. Every dollar figure below is linear in run-hours, so a 2× error
in the anchor is a 2× error in the infra column — and, because the same anchor
drives both sides of every comparison, it is *not* an error in any ratio.

---

## 2. The live price base (all fetched 2026-07-30)

### 2.1 Model tokens — Anthropic first-party

Fetched: <https://platform.claude.com/docs/en/about-claude/pricing> and
<https://platform.claude.com/docs/en/about-claude/models/overview.md>.

| Model | Base input | 5-min cache write | 1-h cache write | Cache read | Output |
|---|---|---|---|---|---|
| Claude Fable 5 | $10 | $12.50 | $20 | $1.00 | $50 |
| Claude Opus 5 | $5 | $6.25 | $10 | $0.50 | $25 |
| Claude Sonnet 5 (**intro, through 2026-08-31**) | $2 | $2.50 | $4 | $0.20 | $10 |
| Claude Sonnet 5 (**from 2026-09-01**) | $3 | $3.75 | $6 | $0.30 | $15 |
| Claude Haiku 4.5 | $1 | $1.25 | $2 | $0.10 | $5 |

All figures per million tokens. Cache multipliers stated on the same page:
**5-min write 1.25×, 1-h write 2×, read 0.1×** of base input. Batch API is
**50% off** input and output. Two facts the 07-23 economics did not have:

- **Tokenizer inflation.** "Claude 4.7 and later models … use a newer
  tokenizer … approximately **30% more tokens for the same text**" (same page).
  This applies to Fable 5, Opus 5, and Sonnet 5 — i.e. every model in the fleet
  except Haiku 4.5. The 07-23 per-run Fermi was calibrated on Sonnet-4.6-era
  tokenization, so its token *volumes* are ~30% low for the current fleet.
- **Claude Managed Agents runtime SKU: $0.08 per session-hour** (same page,
  "Session runtime", metered on `running` status only). Not a substrate we can
  use — Class A fixes the runtime as cc-harness and CMA runs *its* loop — but
  it is the sharpest available read on what a vendor thinks an agent-hour costs
  to host, and it is used as a flip trigger in §8.

### 2.2 GKE and Compute Engine (us-central1)

| Item | Rate | Source (fetched 2026-07-30) |
|---|---|---|
| GKE cluster management fee | **$0.10 / cluster-hour** | <https://www.cloudzero.com/blog/gke-pricing/> (page states "Last updated: May 01, 2026") + search corroboration |
| GKE free-tier credit | **$74.40 / month per billing account** | same |
| Autopilot general-purpose | **$0.0445 / vCPU-hr**, **$0.0049 / GiB-hr**, $0.00014 / GiB-hr ephemeral SSD | same + WebSearch corroboration (two independent trackers) |
| e2-standard-4 (4 vCPU / 16 GiB) | on-demand **$0.134/hr** ($97.84/mo); 1-yr CUD $61.64/mo (**$0.0844/hr, −37%**); 3-yr CUD $44.03/mo (**$0.0603/hr, −55%**); **Spot $0.0804/hr (−40%)** | <https://gcloud-compute.com/e2-standard-4.html>; on-demand cross-checked at <https://instances.vantage.sh/gcp/e2-standard-4> |
| e2-standard-8 (8 vCPU / 32 GiB) | on-demand **$0.268/hr** ($195.67/mo); 1-yr $123.27/mo (**$0.1689/hr**); 3-yr $88.05/mo (**$0.1206/hr**); **Spot $0.1608/hr** | <https://gcloud-compute.com/e2-standard-8.html> |
| Resource-based CUD | **37% (1-yr) / 55% (3-yr)** | <https://www.usage.ai/blogs/gcp/committed-use-discounts/>; matches the e2 CUD arithmetic above exactly |
| Flexible (spend-based) CUD | **28% (1-yr) / 46% (3-yr)** | same |
| Autopilot resource CUDs | **no longer purchasable for new commitments** (two independent trackers; the official CUD page does not say so) | usage.ai, CloudZero — **R2 §8.9 flagged this discrepancy; R4 corroborates but cannot close it** |
| Internet egress (Premium tier) | **$0.12/GB** first 1 TB, **$0.11/GB** 1–10 TB, $0.08/GB above | WebSearch → <https://egresscost.com/gcp/>, <https://cloud.google.com/network-tiers/pricing> |
| Persistent disk | $0.04/GB-mo standard, $0.17/GB-mo SSD | CloudZero (above) |
| GKE Agent Sandbox addon | **no extra charge** beyond underlying compute | R2 §1.1, re-fetched by R2 on 2026-07-30 |

**Consistency check on the CUD percentages.** $0.268 × 0.45 = $0.1206/hr =
$88.05/month at 730 h. The published 3-year e2-standard-8 price reproduces the
55% resource-CUD figure to the cent, and the 1-year price reproduces 37%. Two
independently fetched pages agree; treat both percentages as **high
confidence**.

The GKE pricing page itself (<https://cloud.google.com/kubernetes-engine/pricing>)
could not be read — the fetch tool truncated it on three attempts. Every GKE
rate above therefore rests on third-party trackers that agree with each other;
**verify at the console before committing spend.**

### 2.3 Managed sandbox vendors

| Vendor | Published rates | Derived $/pod-hr (2 vCPU / 4 GiB) | Source (fetched 2026-07-30) |
|---|---|---|---|
| **E2B** | 2 vCPU $0.000028/s (= $0.1008/hr); RAM $0.0000045/GiB-s (= $0.0162/GiB-hr); Pro $150/mo; 100 concurrent, purchasable to 1,100 | **$0.1656** | <https://e2b.dev/pricing> |
| **Daytona** | $0.0504/vCPU-hr; $0.0162/GiB-hr; storage $0.000108/GiB-hr after 5 GiB free; $200 signup credit | **$0.1656** (+$0.0022 for 20 GiB disk) | <https://www.daytona.io/pricing> (Windows row only rendered) + WebSearch corroboration of the standard rates |
| **Modal** (Sandbox tier) | CPU $0.00003942/core-s (1 core ≈ 2 vCPU → $0.1419/hr); memory $0.00000667/GiB-s (= $0.024/GiB-hr); Team $250/mo incl. $100 credits | **$0.2379** | <https://modal.com/pricing> |
| **Northflank** | $0.01667/vCPU-hr; $0.00833/GB-hr | **$0.0667** | <https://northflank.com/pricing> |
| **Vercel Sandbox** | Active CPU $0.128/hr; provisioned memory $0.0212/GB-hr; creations $0.60/1M; **egress $0.15/GB**; 2,000 concurrent; 24 h max | **$0.1488** at 25% CPU duty; $0.1104 at 10% | <https://vercel.com/docs/vercel-sandbox/pricing> (page states `last_updated: 2026-06-16`) |
| **Cloudflare Containers** | $0.000020/vCPU-s (= $0.072/vCPU-hr, active only); $0.0000025/GiB-s (= $0.009/GiB-hr); disk $0.00000007/GB-s; Workers Paid $5/mo | **$0.072** at 25% CPU duty | <https://developers.cloudflare.com/containers/pricing/> |
| **Anthropic CMA** | $0.08 per session-hour (runtime only; tokens billed separately) | **$0.08** — not a like-for-like substrate | pricing page, §2.1 |

**Every one of these rates is unchanged from the 07-23 report.** The
agent-sandbox price floor has not moved in a week of vendor time; the movement
in this remeasure is all on the self-host and token sides. Runloop and Morph
were not re-fetched (both were eliminated on price/unknowns in 07-23 and
nothing suggests re-entry); their rows are **stale, carried for shape only**.

### 2.4 Managed Postgres

| Option | Rate | Source |
|---|---|---|
| **Cloud SQL for PostgreSQL, Enterprise** | **$0.0413/vCPU-hr**, **$0.0070/GB-memory-hr**; SSD ≈$0.22/GB-mo (non-HA), ≈$0.34/GB-mo (HA); HA doubles compute; CUD 25% (1-yr) / 52% (3-yr), compute only | <https://www.usage.ai/blogs/gcp/cloud-sql/pricing/> (article dated May 2026, us-central1). **The official page truncated on fetch — 3rd-party, medium confidence.** |
| **Neon** | Launch $0.106/CU-hr, Scale $0.222/CU-hr; storage $0.35/GB-mo; 500 GB egress included then $0.10/GB; branches $1.50/mo | <https://neon.com/pricing> (first-party, high confidence) |
| **Supabase** | Pro $25/mo (incl. $10 compute credit); compute add-ons Micro $10 / Small $15 / Medium $60 / Large $110 / XL $210 / 2XL $410; disk $0.125/GB-mo general purpose; egress 250 GB then $0.09/GB | <https://supabase.com/pricing> (first-party, high confidence) |

Derived for the board + sessionStore cohabitation shape R2 §6.4 specifies
(one Postgres, two schemas, appends dominating):

- Cloud SQL 4 vCPU / 16 GiB non-HA + 100 GB SSD
  = 4 × $0.0413 × 730 + 16 × $0.0070 × 730 + 100 × $0.22
  = $120.60 + $81.76 + $22.00 = **$224/mo**; HA ≈ **$427/mo**.
- Neon Launch at a 2 CU average = 2 × $0.106 × 730 = **$155/mo** + storage.
- Supabase Pro + Large compute = **$135/mo** + disk.

**Band used below: $135–430/mo**, centred on $224.

### 2.5 Self-managed bare metal — contested, unresolved

Three live sources for the same Hetzner AX-line hardware disagree by up to
2.8×:

| Source (fetched 2026-07-30) | Figure |
|---|---|
| WebSearch snippet of hetzner.com | AX102 **€124/mo** (+€269 setup) |
| <https://looking.house/companies/hetzner-com/dedicated-servers> | AX102 **$295.08/mo**; AX162-S $363.44/mo |
| <https://serverlist.dev/servers/compare/4747-hetzner-ax162> | AX162 **€350.90/mo** (+€42.90 setup) |
| <https://www.hetzner.com/dedicated-rootserver/ax102/> and `/matrix-ax/` | Specs render; **prices are client-side placeholders and do not render to a fetch** |
| <https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/> | **Cloud servers repriced 2026-06-15: CAX11 €4.49→€5.99 (+33%), CPX22 €7.99→€19.49 (+144%), CCX13 €15.99→€42.99 (+169%), CPX11 (US) €5.99→€17.49 (+192%).** Dedicated tiers listed as unchanged. |

I could not resolve the dedicated-server list price from an authoritative
source in this session and **will not fabricate one**. §5 therefore carries the
self-managed column as a **band ($5.4k–15.2k/mo at the enterprise anchor)** and
treats the verdict as robust across the whole band. The verified cloud-server
repricing is used directly as flip-trigger FT6: the cheap-European-metal
premise the 07-23 research leaned on is no longer a safe input.

### 2.6 Not re-fetched this session (flagged)

Object storage (transcript archive), log-vendor pricing (Axiom/Better
Stack/Grafana), and secrets-manager pricing. The 07-23 report priced these at
**$5–125/mo combined**; at that magnitude they cannot move any verdict here (the
smallest gap in §4 is $2.2k/mo). They are carried as a **$25–125/mo lump,
labelled stale**, and are listed in §11 for the next pass.

---

## 3. The unit economics of one run-hour

This is the arithmetic every later section reduces to. Pod shape = the A0
anchor's **2 vCPU / 4 GiB** unless noted.

### 3.1 Managed (rates from §2.3)

```
E2B         2 × $0.0504/vCPU-hr-equiv + 4 × $0.0162/GiB-hr
            = $0.1008 + $0.0648                       = $0.1656 /pod-hr
Daytona     identical compute rates + 20 GiB storage  = $0.1678 /pod-hr
Modal       $0.1419 (1 core = 2 vCPU) + 4 × $0.0240   = $0.2379 /pod-hr
Northflank  2 × $0.01667 + 4 × $0.00833               = $0.0667 /pod-hr
Vercel      0.5 CPU-hr × $0.128 + 4 GB × $0.0212      = $0.1488 /pod-hr  (25% duty)
Cloudflare  0.5 vCPU-hr × $0.072 + 4 GiB × $0.009     = $0.0720 /pod-hr  (25% duty)
```

### 3.2 GKE Autopilot (per-pod billing, §2.2)

```
list        2 × $0.0445 + 4 × $0.0049 = $0.0890 + $0.0196 = $0.1086 /pod-hr
1-yr flex CUD (−28%)                                      = $0.0782
3-yr flex CUD (−46%)                                      = $0.0586
```

Autopilot bills a warm pod at the full pod rate: **$0.1086 × 730 = $79.28/mo
per idle warm pod** — R2 §2's figure, confirmed on live rates.

### 3.3 GKE Standard (per-node billing → packing matters)

e2-standard-8 at $0.268/hr, 8 vCPU / 32 GiB. Allocatable after kubelet/system
reservations ≈ **7.6 vCPU / 27 GiB** (standard GKE reservation shape;
**derived, not fetched**).

```
(a) strict 2 vCPU request  → CPU-bound: floor(7.6/2) = 3 pods/node
    $0.268 / 3                                        = $0.0893 /pod-hr
(b) R2 §2 v1 request shape (1 vCPU request, 2 GiB request, 4 GiB limit)
    → memory-bound at the limit: floor(27/4) = 6 pods/node
    $0.268 / 6                                        = $0.0447 /pod-hr
```

Shape (b) is the honest self-host number: R1/R2 establish that agents idle on
tokens and CPU oversubscribes 2–4×, so *requesting* 2 vCPU per pod would be
paying for CPU nobody uses. Shape (a) is retained because it is what the
managed vendors charge for, and comparing (a) to managed is the strictly
conservative comparison. Discounted:

```
              list      1-yr CUD    3-yr CUD    Spot
shape (a)   $0.0893     $0.0563     $0.0402    $0.0536
shape (b)   $0.0447     $0.0282     $0.0201    $0.0268
```

**gVisor overhead is not free but is not material here.** The cloud-scale
research measured gVisor at 10–30% CPU overhead on syscall-heavy work, ~1–3%
on most workloads, plus a per-pod Sentry of tens of MB. Our packing is
memory-bound (shape b), so the Sentry costs ~2% of a 4 GiB pod and the CPU
overhead lands on oversubscribed capacity. **Sensitivity: +15% on shape (b)
gives $0.0514/pod-hr and changes no verdict.** The managed vendors run
Firecracker or gVisor too and have already priced their own overhead in.

### 3.4 The three sandbox price tiers, ranked

| $/pod-hr | Option | Can it express the run-class egress allowlist? |
|---|---|---|
| $0.0201–0.0447 | **GKE Standard, shape (b)** | Yes — FQDNNetworkPolicy (GA) + NetworkPolicy, R2 §3 (50-IP cap unverified) |
| $0.0402–0.0893 | GKE Standard, shape (a) | Yes |
| $0.0586–0.1086 | GKE Autopilot | Yes — same manifests |
| $0.0667 | Northflank | **Not published** (07-23 absence-of-evidence, unchanged) |
| $0.0720 | Cloudflare Containers | Thin (07-23) |
| $0.1488 | Vercel Sandbox | **Not published** |
| $0.1656 | **E2B** | **Yes — domain allowlists, runtime-updatable** |
| $0.1678 | **Daytona** | Yes — 20 domain entries with wildcards (07-23 erratum) |
| $0.2379 | Modal | Yes — domain allowlist (beta) |

**The cheap managed options are cheap because they do not sell the one control
the architecture is built on.** Any comparison that mixes them into "the
managed band" is comparing unlike things — this matters directly for R3's
promotion bar (§9.2).

---

## 4. A0 remeasure — full bill of materials

### 4.1 Self-host (GKE Standard + pinned upstream Agent Sandbox), on-demand

| Line | Arithmetic | $/mo |
|---|---|---|
| Sandbox pods | 27,500 pod-hr × $0.0447 | 1,229 |
| Fragmentation / provisioning tails | +25% (derived allowance) | 307 |
| Warm pool (8 pods × 220 h in-window) | 8 × 220 × $0.0447 — packs into node headroom already paid for | 0–79 |
| Control plane (board API, LLM gateway HA pair, dispatcher/reconciler, OTel collector, mirror writer) | 2 × e2-standard-4 24/7 = 2 × $97.84 | 196 |
| GKE cluster fee | $0.10 × 730 = $73.00, less the $74.40 free-tier credit | 0 |
| Postgres (board + sessionStore, one instance) | Cloud SQL 4 vCPU / 16 GiB + 100 GB SSD, non-HA (§2.4) | 224 |
| Internet egress | §4.3 below | 175 |
| Object storage + logging | **stale, not re-fetched** | 25–125 |
| Ops-agent VM (R3 §1.3, 4 GiB class) | e2-medium class, ≈½ × e2-standard-2 ($0.067/hr) | 25 |
| **Agent-ops tokens (R3 §6.1 central)** | flat in run-volume | 150 |
| **Total** | | **$2,331–2,510** |

With **Spot** on the sandbox node pool only (−40%; preemption costs at most one
in-flight turn per R1 §0.2, and the reconciler already re-dispatches):

| Line | $/mo |
|---|---|
| Sandbox pods + fragmentation at $0.0268/pod-hr (27,500 × $0.0268 = $737, +25%) | 921 |
| Everything else unchanged (control plane 196 + Postgres 224 + egress 175 + ops VM 25 + ops tokens 150 + obs 25–125 + warm pool 0–47) | 795–942 |
| **Total** | **$1,716–1,863** |

Under the strictly conservative pod shape (a) — paying for 2 vCPU of requests
per pod — the on-demand total is **$3,558** and the Spot total is **$2,469**.

### 4.2 Managed, at the same 27,500 run-hours

| Option | Arithmetic | $/mo |
|---|---|---|
| **E2B Pro** | 27,500 × $0.1656 + $150 | **4,704** |
| **Daytona** | 27,500 × $0.1678 | **4,615** |
| Modal Team | 27,500 × $0.2379 + $250 | 6,792 |
| Vercel Sandbox Pro | 27,500 × $0.1488 (+ egress at $0.15/GB — ~$225 more, §4.3) | 4,092+ |
| Cloudflare Containers | 27,500 × $0.0720 + $5 | 1,985 |
| Northflank | 27,500 × $0.0667 | 1,834 |
| **GKE Autopilot, list** | 27,500 × $0.1086 | **2,987** |
| GKE Autopilot + warm pool of 8 | + 8 × $79.28 | 3,619 |
| GKE Autopilot, 1-yr flex CUD | × 0.72 (+ pool) | 2,606 |
| GKE Autopilot, 3-yr flex CUD | × 0.54 (+ pool) | 1,954 |

Autopilot rows exclude the same control-plane / Postgres / egress / ops lines
the self-host BOM carries (~$600–700/mo), which apply to Autopilot too. Add
them for a true comparison: **Autopilot all-in ≈ $4.2–4.3k/mo list.**

### 4.3 The egress line the baseline under-counted

The 07-23 report folded egress into "cron/misc/egress $20–150". At A0 that is
too low, and the mechanism is worth naming because it is structural to a
prompt-cached agent loop: **prompt caching is server-side, so the client
re-sends the full message array on every turn.** The cache saves *processing*,
not *bytes on the wire*.

```
per turn outbound ≈ 70k tokens × ~4 bytes/token          ≈ 280 KB
per run            45 turns × 280 KB                      ≈ 12.6 MB
per month (A0-mid) 4,000 runs/day × 22 days × 12.6 MB     ≈ 1.11 TB
                   (+ retries, board/mirror traffic)      ≈ 1.5 TB
cost               1 TB × $0.12 + 0.5 TB × $0.11          ≈ $175/mo
```

**Derived, and the single infra line most likely to surprise on a real bill.**
Inbound (git clone, package pulls, model responses) is free on GCP. On Vercel
Sandbox the same traffic bills at $0.15/GB ≈ **$225/mo**, which is not in the
$4,092 row above. E2B and Daytona publish no egress charge (absence of
evidence, unchanged from 07-23). Instrumenting bytes-per-run is a day-one ask
(§11).

### 4.4 A0 verdict

| Comparison | Ratio |
|---|---|
| Self-host on-demand ($2.4k) vs E2B/Daytona ($4.6–4.7k) | **1.9×** |
| Self-host on Spot ($1.7–1.9k) vs E2B/Daytona | **2.5–2.7×** |
| Self-host on-demand vs Autopilot all-in ($4.2k) | **1.8×** |
| Self-host vs Northflank/Cloudflare ($1.8–2.0k) | **0.8× on-demand; ~1.1× on Spot — parity either way** |
| Autopilot all-in vs E2B/Daytona | **1.1× — effectively parity** |

Two readings, both load-bearing:

1. **Against capability-equivalent managed sandboxes, self-host is ~2× cheaper
   and gets cheaper on Spot.** The gap is real but small in absolute terms
   ($2.1–2.9k/mo) — see §6.4 for why that makes it nearly irrelevant.
2. **Autopilot costs what a managed sandbox costs.** Its value proposition is
   ops removal, and the agent-ops layer already removes ops for $150/mo.
   Paying Autopilot's ~$1.9k/mo premium *and* running an ops agent is paying
   twice for the same thing. **R4 recommends Standard as the default at both
   tiers** — which, incidentally, also removes the one place R2 had to caveat
   the "same manifests everywhere" claim (no local NVMe on Autopilot) and gives
   R3's spike the substrate it actually needs to learn anything.

---

## 5. Enterprise anchor remeasure (730k pod-hr/mo, 24/7)

| Option | Arithmetic | $/mo |
|---|---|---|
| Modal | 730k × $0.2379 | 173,667 |
| Daytona | 730k × $0.1678 | 122,494 |
| **E2B** | 730k × $0.1656 + $150 | **120,838** — and you are at the published 1,100-concurrency ceiling |
| GKE Autopilot, list | 730k × $0.1086 | 79,278 |
| GKE Autopilot, 3-yr flex CUD | × 0.54 | 42,810 |
| GKE Standard shape (a), list | 730k × $0.0893 | 65,189 |
| GKE Standard shape (a), 3-yr CUD | 730k × $0.0402 | 29,346 |
| **GKE Standard shape (b), list** | 730k × $0.0447 | **32,631** |
| **GKE Standard shape (b), 3-yr CUD** | 730k × $0.0201 | **14,673** |
| Self-managed bare metal | ~40 boxes at 128 GB / ~25 pods each, 80% packing; €124–€350/box (**contested, §2.5**) | **5,400–15,200** |

Plus, on every self-host row: control plane and Postgres scale sublinearly
(call it $2–5k/mo at this size), and **agent-ops tokens stay flat** — R3 §5.6.3
establishes that the ops term tracks incident tempo, not run volume; at
enterprise tempo call it $300–800/mo. That asymmetry is the whole ballgame:
**the managed bill is linear in volume, the ops bill is not.**

**Findings:**

- **Self-host beats capability-equivalent managed by 4–8×** at the enterprise
  anchor ($15–33k vs $121–122k). This direction is unchanged from 07-23; the
  magnitude is now grounded in fetched rates rather than a $0.05/vCPU-hr
  shorthand that ignored RAM.
- **Self-managed bare metal beats GKE Standard + 3-yr CUD by 0–2.7×,** with the
  midpoint of the contested price band landing at roughly **1.4×**. The 07-23
  premise — SaaS ~$73k vs self-host $5–15k, therefore hire an engineer — was
  never a comparison against a CUD-discounted managed Kubernetes; inserting
  that middle option collapses the case for owning hardware.
- **Therefore R3's ≥2× gate for self-managed is not met at the enterprise
  anchor on the central price estimate, and is not remotely met at A0** (where
  a 3-box Hetzner floor of ~$400–1,050/mo sits against a $2.4k self-host total
  that already includes Postgres, egress, and control plane the bare-metal
  figure does not). §8 FT6 adds the input-price-instability argument. **R4's
  recommendation: keep the self-managed gate closed, and do not spend a second
  spike on it unless the bare-metal rate card is confirmed at the low end of
  §2.5 *and* volume is enterprise-anchored.**

---

## 6. Token economics remeasure

### 6.1 Per-run Fermi, re-priced

Run shape **inherited unchanged** from `zero-ops-economics-a0.md` §4.1 so the
comparison is like-for-like: a 12-minute implementer run, ~45 API turns,
context 20k → 120k (avg ~70k), the harness cache-reading the whole prefix each
turn.

- **Basis A** = the 07-23 token volumes exactly: 3.1M cache reads, 150k cache
  writes, 50k fresh input, 40k output.
- **Basis B** = Basis A × 1.30, applying the live-verified tokenizer inflation
  (§2.1) to every model except Haiku 4.5: 4.03M / 195k / 65k / 52k.

| Model | Basis A $/run | Basis B $/run |
|---|---|---|
| Haiku 4.5 | 0.31 + 0.19 + 0.05 + 0.20 = **$0.75** | $0.75 (old tokenizer) |
| Sonnet 5 **intro** | 0.62 + 0.38 + 0.10 + 0.40 = **$1.50** | 0.81 + 0.49 + 0.13 + 0.52 = **$1.94** |
| Sonnet 5 **from Sept 1** | **$2.24** | 1.21 + 0.73 + 0.20 + 0.78 = **$2.92** |
| Opus 5 | 1.55 + 0.94 + 0.25 + 1.00 = **$3.74** | 2.02 + 1.22 + 0.33 + 1.30 = **$4.86** |
| Fable 5 | 3.10 + 1.88 + 0.50 + 2.00 = **$7.48** | 4.03 + 2.44 + 0.65 + 2.60 = **$9.72** |

*(Columns are cache reads + cache writes + fresh input + output.)*

**Basis B is the right one to plan on** — the tokenizer note is a live vendor
statement about the models the fleet will actually run — but Basis A is
retained because the volumes themselves are inherited estimates and a reader
may reasonably argue the agent works to a fixed context budget rather than a
fixed corpus.

**The headline is a near-cancellation.** On Sonnet, the 07-23 baseline was
**$2.20/run** (Sonnet 4.6 at $3/$15). Today it is **$1.94** — the introductory
price cut (−33%) is almost exactly offset by the tokenizer (+30%). From
2026-09-01 it becomes **$2.92**, i.e. **+33% against the baseline**, with no
change to the workload.

### 6.2 Monthly token spend at A0

| | runs/day | runs/mo (22 d) | blended $/run (Basis B) | tokens $/mo |
|---|---|---|---|---|
| **A0-low** (Haiku share, tight tiering, short runs) | 3,000 | 66,000 | $1.00–1.30 | **$66–86k** |
| **A0-mid** (Sonnet implementers + short Opus verdicts + a small Fable architect lane) | 4,000 | 88,000 | $2.00–3.10 | **$176–273k** |
| **A0-top** (Opus-heavy, 15-min runs, larger architect share) | 5,000 | 110,000 | $4.00–6.00 | **$440–660k** |

Basis A equivalents: **$56–66k / $135–200k / $340–500k**. Baseline (07-23):
$53k / $110–155k / $260–330k.

**The scheduled event.** All-Sonnet A0-mid is 88,000 × $1.94 = **$171k/mo**
today and 88,000 × $2.92 = **$257k/mo** from 2026-09-01: **+$86k/month, +50%,
in 32 days**, purely from the intro-pricing expiry. Nothing in the
infrastructure decision space is within an order of magnitude of that number.

### 6.3 The E1 architect lane is the dominant cost dial

R2 §6.2 routes `ready-for-architect` to the Fable route and
`ready-for-implementer` to the Opus route, with "a separate architect-lane
concurrency cap (the Fable-spend lever)". Priced:

```
Fable 5 run    $9.72   =  5.0 × a Sonnet 5 intro implementer run ($1.94)
                       =  2.0 × an Opus 5 run ($4.86)

Blended $/run at A0-mid, by architect-lane share (rest on Sonnet 5 intro):
   0%   → $1.94      88k runs → $171k/mo
   5%   → $2.33      88k runs → $205k/mo     (+$34k)
  10%   → $2.72      88k runs → $239k/mo     (+$68k)
  15%   → $3.11      88k runs → $274k/mo     (+$103k)
```

**A five-percentage-point move in the architect-lane share is worth
$34k/month. The entire self-host-versus-managed decision is worth
$2.1–2.9k/month.** The lane-mix knob is **12–49× more valuable than the
substrate knob**, and the concurrency cap R2 already specified is the control
surface for it. Two corollaries:

- The cap should be set from a **cost target**, not only a throughput target,
  and the board should carry per-lane spend rollups (E2's ledger already has
  the event stream to derive them).
- Evaluating the architect lane on its own bill is the wrong frame — the
  07-23 corollary stands: judge the gate/planner model on **total downstream
  run cost**, since a better decomposition removes implementer runs. One
  avoided 12-min Sonnet run pays for 0.2 of a Fable architect run; the lane
  pays for itself if it avoids ~5 implementer runs per architect run.

### 6.4 Token:infra ratio, and what it makes irrelevant

| | tokens $/mo (Basis B) | infra + agent-ops $/mo | ratio |
|---|---|---|---|
| A0-low (≈16.5k run-hr) | $66–86k | ~$1.8k | **37–48×** |
| A0-mid (≈22k run-hr) | $176–273k | ~$2.1k | **84–130×** |
| A0-top (≈27.5k run-hr, the anchor) | $440–660k | ~$2.5k | **176–264×** |

Infra scales with run-hours, which scale with runs/day: 3,000 / 4,000 / 5,000
starts per day at a 12.5-minute mean give ≈16.5k / 22k / 27.5k run-hours per
month, so the anchor's 27.5k corresponds to the *top* row, not the middle
(**inherited basis, §1**).

**Band: ~37–264×, mid ≈100×.** The 07-23 figure was 60–170× computed / "30–100×"
headline. **The ratio is stable under a complete re-price of both sides** — a
result worth stating plainly, because it means the design rule derived from it
("every infra decision is a rounding error; every token decision is the
budget") is not an artifact of one price snapshot.

Concretely, at A0-mid:

- Infra + ops is **0.8–1.2%** of all-in spend (0.4–2.7% across the band).
- The managed-vs-self-host delta ($2.1–2.9k/mo) is **~1% of the bill** and
  equals **≈5–7 hours** of token burn at the mid daily rate (~$10k/day).
- A **cache regression** — unstable prompt prefix, mid-loop tool-set churn —
  reprices ~4M tokens/run from $0.20/MTok to $2/MTok, i.e. **+$7.25/run,
  ≈ +4×** on Sonnet. At A0-mid that is **+$640k/month**, or **260 months of the
  entire infrastructure bill**. The per-run cache-hit-ratio meter remains the
  highest-leverage instrument in the system, exactly as the baseline said.

**Not levers, re-confirmed:** the Batch API (50% off, but 24-hour turnaround
does not fit an interactive worker loop — unchanged), and negotiating sandbox
rates (see the ratio).

---

## 7. The crossover math, with the human constant removed

### 7.1 The old model

`zero-ops-economics-a0.md` §5 and `sandbox-substrate-a0.md` §2.9/§4: self-hosting
carried "**~0.1–0.2 FTE of a senior engineer, spiky**", and the enterprise
inversion point was "the crossover arrives with the first infra hire, ~300–500
concurrent". Priced at a loaded senior infra salary of ~$250k/yr:

```
0.15 FTE  = $37.5k/yr  = $3,125/mo
1.0 FTE   = $250k/yr   = $20,833/mo
```

Applying that constant to *today's* live prices: the A0 infra-only saving from
self-hosting is managed $4,615–4,704 − self-host-without-ops $2,181–2,360 =
**$2,255–2,523/mo**. Under the old constant that saving is **smaller than
0.15 FTE ($3,125/mo)** and an order of magnitude smaller than a dedicated hire
— so managed wins at A0, exactly reproducing the baseline's verdict
(**"the fleet you don't operate is worth ~3–4× the raw compute premium"**).
The baseline was correct under its own constant, on today's prices as well as
its own.

### 7.2 The new model

R3 §6.1 replaces the human with an accountable agent worker on the ops lane:
scheduled patrols $10–30, incident responses $30–200, weekly hygiene $10–40,
substrate $15–30 → **$65–300/mo steady state, ~$500/mo ceiling in change-heavy
months**, with **~$150/mo as the central estimate** and — critically —
**flat in run-volume**.

The constant shrinks by a factor of **21× (against 0.15 FTE)** to **139×
(against a dedicated hire)**.

### 7.3 Where the crossover now sits

Let *H* = monthly pod-hours. Using the live rates of §3 and the fixed floor of
§4.1:

```
managed(H)   = $150 (plan fee) + $0.1656 · H
self-host(H) = F + $0.0447 · H + $150 (agent-ops tokens)

  where F = fixed floor = control plane $196 + Postgres $224 + ops VM $25
          = $445   (lean: single-instance Postgres, no HA, no log vendor)
          → $700   (loaded: HA Postgres, obs, headroom)

Crossover, lean floor:    445 = 0.1209 · H  →  H = 3,681 pod-hr/mo  = 5.0 sustained concurrent
Crossover, loaded floor:  700 = 0.1209 · H  →  H = 5,790 pod-hr/mo  = 7.9 sustained concurrent
Crossover, agent-ops at its $500 ceiling:
                        1,050 = 0.1209 · H  →  H = 8,685 pod-hr/mo  = 11.9 sustained concurrent
```

| | old constant | new constant |
|---|---|---|
| Ops term | $3,125–20,833/mo | **$150/mo** (ceiling $500) |
| Crossover | **300–500 sustained concurrent** | **5–8 sustained concurrent** (12 at the ops ceiling) |
| Shift | — | **40–100× lower** |

**Reading it.** The crossover is no longer a scale threshold anyone in this
program will sit below. A0's *average* concurrency is 37.7 and its in-window
concurrency is 125 — 5–25× past the crossover. The question "when does
self-hosting start paying?" has effectively been answered out of existence;
what remains is "does self-hosting cost us anything else?", which is R2's and
R3's territory, not R4's.

**What the new constant does not include, stated honestly.** The agent-ops
term is a *designed* cost, not a measured one — R3 §7.1 flags that if the real
tail-incident tempo is 5× its assumption, both the intervention bar and the
band move. At 5× the incident term ($150–1,000 instead of $30–200), the ops
constant becomes ~$1,100/mo and the crossover moves to ~12 sustained
concurrent. **Still two orders of magnitude below the old one.** The verdict is
robust to a 5× error in R3's central input, which is the sensitivity that
matters.

---

## 8. Flip triggers — under what conditions does managed RE-enter?

Each trigger is stated as a measurable threshold, with the instrument that
would detect it. **Two 07-23 triggers are retired:** the "price/volume flip"
(sustained run-hours ≥2× A0 breaking a $5k budget — self-host has no such
cliff) and "the crossover arrives with the first infra hire" (the hire is what
got replaced).

| # | Trigger | Threshold (live-priced) | Instrument |
|---|---|---|---|
| **FT1** | **Volume floor.** Sustained load falls below the fixed-floor crossover | **< ~5k pod-hours/month (≈5–8 sustained concurrent)** | Board query: monthly pod-hours from the `run` table |
| **FT2** | **Duty-cycle collapse.** Load becomes hard-burst with long idle, and node provisioning tails exceed the warm pool's absorption | duty cycle **< ~10%** *and* p95 cold-node provisioning **> 90 s** | R2 §8.2 warm-pool latency measurement + board start-rate histogram |
| **FT3** | **Egress capability failure.** `FQDNNetworkPolicy`'s 50-resolved-IP cap cannot express the implement lane's registry list and the pull-through registry cache does not remove the need (R2 §8.4) | binary — any lane that cannot be expressed | The in-cluster probe R2 already queued |
| **FT4** | **Vendor price/capability collapse.** A managed sandbox publishes **≤$0.09/pod-hr *with* per-sandbox domain allowlists** | Northflank is **already at $0.0667** and is one product announcement away from this; Cloudflare at $0.0720 likewise | Quarterly re-fetch of §2.3 |
| **FT5** | **Hosted-harness offer.** Someone sells "your harness on our runtime" (R1 Class B: nobody does today) | Anthropic's CMA runtime SKU is **$0.08/session-hour = $2,200/mo at A0** — *already inside the self-host band*. A hosted runtime that accepted cc-harness would be competitive on day one | Vendor release notes; re-run §4 immediately if it appears |
| **FT6** | **Self-host input-price instability.** The cloud/metal rate card moves against us | **Live-verified precedent: Hetzner repriced cloud servers +94–192% on 2026-06-15.** GCP CUD percentages are contractual for the term; on-demand is not | Annual re-price; never build a 3-year plan on one vendor's rate card |
| **FT7** | **Compliance / data-residency mandate** forcing a specific substrate | binary, cost-independent | Unchanged from 07-23 |
| **FT8** | **Provider quota**, not infra. Sustained ITPM near the tier ceiling | fires *before* any infra threshold, exactly as the baseline said | `limitState` board events (R1 §1E) |

**Asymmetry worth naming:** FT1 and FT2 are *scale-down* triggers — they fire
if the program shrinks, not if it grows. FT3, FT4, and FT5 are capability or
market triggers. **There is no growth path that makes managed cheaper.** That
is the structural change from the baseline, where growth was precisely what
made self-host cheaper and shrinkage what made managed cheaper; now managed
only wins at the bottom.

---

## 9. Consequences for R2's and R3's open items

### 9.1 The discount instrument is tier-dependent — a third knob

Break-even duty cycles for the live discount instruments:

```
1-yr resource CUD, −37%  →  pays if the committed capacity runs ≥ 63% of the time
3-yr resource CUD, −55%  →  pays if it runs ≥ 45% of the time
1-yr flex CUD,     −28%  →  ≥ 72%
3-yr flex CUD,     −46%  →  ≥ 54%
Spot,              −40%  →  no commitment; pays at any duty cycle
```

**A0's duty cycle is ~30% (§1). It fails every CUD break-even and clears Spot
trivially.** The enterprise anchor runs 24/7 (100%) and clears every CUD, where
the 3-year resource CUD at −55% is the single largest lever available on the
infra side.

So the correct procurement posture differs by tier while the architecture does
not:

| | A0 | Enterprise |
|---|---|---|
| Sandbox pool | **Spot** (preemption ≤1 turn, R1 §0.2) | 3-yr resource CUD on the baseline + Spot on the burst |
| Always-on tier (control plane, gateway, Postgres) | on-demand or 1-yr CUD (it *is* 100% duty) | 3-yr CUD |
| Warm pool | free-ish on Standard | free-ish on Standard |

This is R4's addition to the knob list. It is a procurement parameter, not a
design parameter: **the manifests do not change**.

### 9.2 R3's promotion bar needs its comparator pinned

R3 §5.6.3 states the bar as: measured platform + agent-ops cost, scaled to
27.5k run-hr/mo, **≤ 0.5 × the R4-refreshed managed-sandbox band**. Priced:

```
Comparator = capability-equivalent managed sandboxes (E2B $4,704 / Daytona $4,615)
  0.5 × band = $2,308 – $2,352
  self-host on-demand ($2,331–2,510)  →  FAILS or ties
  self-host on Spot   ($1,716–1,863)  →  PASSES with 21–26% margin

Comparator = "all managed sandboxes" (including Northflank $1,834 / Cloudflare $1,985)
  0.5 × band = $917 – $992
  self-host on Spot ($1,716)          →  FAILS
```

**The bar's verdict is decided by the comparator, not by the platform.**
Recommendation for the gate: **fix the comparator to managed sandboxes that can
express the run-class egress allowlist** (E2B, Daytona, Modal — §3.4), because
that is the capability-parity line the architecture requires; comparing against
vendors that cannot enforce the boundary is comparing unlike things. With that
comparator, the bar is **met on Spot and marginal on-demand** — which is a
useful, discriminating test rather than a foregone one, and it makes "run the
sandbox pool on Spot" a spike design decision rather than an optimisation.

### 9.3 R3's spike, re-priced on live rates

| Line | Arithmetic | $ |
|---|---|---|
| Sandbox + control-plane nodes | 3 × e2-standard-4 × 24 h × 25 days × $0.134 | 241 |
| GKE cluster fee | $0.10 × 600 h = $60, within the $74.40 credit | 0 |
| Postgres | Cloud SQL 2 vCPU / 8 GiB × 600 h + 50 GB SSD | 94 |
| Ops-agent VM | e2-medium class × ~1 month | 25 |
| Egress, registry, object storage | derived allowance | 50 |
| **Infra subtotal** | | **410** |
| Real-model minority lane | 25 runs/day × 25 days × $0.75 (Haiku 4.5, live) | 469 |
| Ops-agent tokens over the window | R3 §6.1 at ~1 month | 150 |
| **Token subtotal** | | **619** |
| **Total** | | **≈ $1,030** (range $0.9–1.3k) |

R3 estimated $550–1,150; the live re-price lands at **$0.9–1.3k**, at or just
above the top of that range, driven by the Haiku minority lane (25–50 runs/day
at $0.75/run is $470–940 alone). **The suggested $1.5k abort cap still holds
but with ~15–30% headroom rather than ~50%.** If the human wants more headroom,
the cheapest lever is halving the real-model lane to 10–15 runs/day; the mock
lane carries the platform surface at zero token cost either way.

---

## 10. The economic half of the through-question

**Do A0 and enterprise unify into one architecture with two scale knobs, or
remain two designs?**

**Economically: one architecture. The tiers differ in procurement, not in
design.** The evidence:

1. **The cost function is identical.** Every row in §3–§5 is
   `$/pod-hour × pod-hours`, with the same $/pod-hour formula at both anchors,
   because the same manifests run on the same CRDs on the same machine family.
   Nothing in the arithmetic forks.
2. **What differs is the discount instrument, and it is a knob** (§9.1): Spot
   at 30% duty cycle, 3-year CUD at 100%. Same nodes, same pods, different
   purchase order.
3. **The fixed floor ($445–700/mo) is scale-invariant, so it is a per-unit
   penalty at A0 that vanishes with volume** — 1.6–2.5 ¢/pod-hour at A0,
   0.1 ¢ at enterprise. That is the entire economic content of "A0 is smaller",
   and the mitigation (amortise the floor across repos/tenants on one cluster)
   is again a knob.
4. **The economics actively argue for removing one of R2's knobs.** Autopilot
   at A0 costs ~$4.2k all-in against Standard's ~$2.4k — a $1.9k/mo premium for
   node ops that R3's agent-ops layer removes for $150/mo, i.e. **12× more
   expensive than the thing that replaces it.** The tier split R2 proposed
   ("Autopilot is the A0 entry, Standard at scale") does not survive its own
   price. Recommend Standard at both tiers, Autopilot as break-glass; R3 §6.2
   already noted the spike would learn nothing on Autopilot, which now has a
   cost reason as well as an ops reason.
5. **Self-managed, the only genuine third design, fails its gate** (§5) and is
   additionally exposed to input-price instability (§8 FT6). Keeping it closed
   removes the last candidate for a real fork.

**Where the tiers *do* diverge economically, and it is not the infrastructure.**
The one number that changes character with scale is the **agent-ops term's
relationship to volume**: it is flat, while every managed alternative is
linear. At A0 that is a $2.2k/mo difference; at enterprise it is a $106k/mo
difference. The tier story is therefore not "two architectures" but "the same
architecture, whose advantage compounds with scale" — which is the strongest
possible form of a one-architecture answer.

**Concurrence.** R1 §3 (runtime evidence forces no fork), R2 §7 (platform layer
is one architecture, cluster mode is a knob), R3 §6.2 (one ops framework, the
catalog is the knob), and R4 (one cost function, procurement is the knob) all
land in the same place from four independent evidence bases. R4 adds one
dissent to R2: **the Autopilot knob should be retired, not kept**, because its
price is its only argument and its price is bad.

---

## 11. What only a live cluster, a real bill, or a spike can settle

Nothing below is settled by this report, and none of it is fabricated here.

1. **Pod-hours per run.** The 0.25 h/run and 27.5k run-hr/mo anchors are
   inherited Fermi estimates, never measured. Every infra dollar is linear in
   them.
2. **Packing density under gVisor.** 6 pods per e2-standard-8 is memory
   arithmetic against R2's v1 request shape; R1's RSS measurement was a floor
   (no completed turn) and the linux binary size is unmeasured. Real density
   could be 4 or 8, moving the self-host column ±50%.
3. **Spot preemption rate on gVisor node pools**, and the real cost of a lost
   turn at the fleet's turn length. The 40% Spot discount is the difference
   between passing and failing R3's bar (§9.2).
4. **Bytes-on-the-wire per run (§4.3).** The 12.6 MB/run estimate is the single
   infra line most likely to be wrong by a large factor, and it is the only one
   that grows with context length rather than with wall-clock.
5. **Autopilot resource-CUD purchasability.** Two trackers say no; the official
   doc is silent. A purchase-console fact (R2 §8.9, still open).
6. **The Hetzner/bare-metal rate card.** Three live sources disagree by 2.8×
   (§2.5). Only a signed quote resolves it — and only if the self-managed gate
   is ever reopened.
7. **Cloud SQL rates.** The official pricing page truncated on fetch; §2.4's
   Cloud SQL row is 3rd-party, medium confidence. Verify at the console.
8. **Object storage, log vendor, secrets** — not re-fetched (§2.6). Small, but
   should be closed in the next pass for completeness.
9. **Production cache-hit ratio per run** — the ±4× lever (§6.4). The cost
   meter that measures it is still the cheapest, highest-leverage thing to
   build.
10. **Real lane mix (architect share).** §6.3's whole magnitude depends on it,
    and it is a board query the moment E1 ships.

---

## 12. Confidence register

**First-party pages fetched this session (high confidence):**
<https://platform.claude.com/docs/en/about-claude/pricing> ·
<https://platform.claude.com/docs/en/about-claude/models/overview.md> ·
<https://e2b.dev/pricing> · <https://modal.com/pricing> ·
<https://northflank.com/pricing> · <https://vercel.com/docs/vercel-sandbox/pricing> ·
<https://developers.cloudflare.com/containers/pricing/> ·
<https://neon.com/pricing> · <https://supabase.com/pricing> ·
<https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/>

**Third-party trackers, cross-checked against at least one other source
(medium-high confidence):**
<https://gcloud-compute.com/e2-standard-4.html> ·
<https://gcloud-compute.com/e2-standard-8.html> ·
<https://instances.vantage.sh/gcp/e2-standard-4> ·
<https://www.cloudzero.com/blog/gke-pricing/> (states last updated 2026-05-01) ·
<https://www.usage.ai/blogs/gcp/committed-use-discounts/> ·
<https://egresscost.com/gcp/>. The e2 CUD percentages are corroborated by exact
arithmetic agreement across two machine sizes.

**Third-party, single source (medium confidence — verify before committing):**
Cloud SQL per-vCPU/per-GB rates (<https://www.usage.ai/blogs/gcp/cloud-sql/pricing/>,
article dated May 2026); Daytona's standard vCPU/GiB rates (first-party page
rendered only the Windows row; rates corroborated by search snippets and
identical to the 07-23 first-party fetch).

**Could not be fetched (named, not worked around):**
<https://cloud.google.com/kubernetes-engine/pricing> (truncated on three
attempts) · <https://cloud.google.com/sql/pricing> (truncated) ·
<https://cloud.google.com/storage/pricing> (truncated) · Hetzner dedicated-server
list prices (client-side rendering; three third-party sources disagree by 2.8×).

**Derived (my arithmetic on live rates, labelled at each use):** all $/pod-hour
figures; all monthly totals; the node allocatable assumption (7.6 vCPU /
27 GiB); the egress Fermi; the crossover algebra; the packing densities.

**Inherited and never measured:** both scale anchors; the per-run token volumes;
the 25% CPU-duty assumption used for the active-billed vendors; the 25%
fragmentation allowance.

**Stale, carried for shape only:** object storage / observability / secrets
lines; Runloop and Morph; every 07-23 dollar figure quoted as a baseline.

---

## Sources

**This round:** `r1-runtime-gaps.md` (§0.2 turn-durability ceiling → Spot
viability; §2 pod anatomy; §1E fleet auth) · `r2-platform.md` (§1.3 cluster
shapes and CUD structure; §2 warm-pool cost coupling and v1 request shape; §3
egress stack; §6.4 one-Postgres convergence; §8 verify list) ·
`r2-board-schema.md` (§3.5 env-issue lane, §4 cohabitation roles) ·
`r3-agent-ops.md` (§5 spike design and cost estimate; §5.6.3 promotion-bar
formula and the flat-in-volume asymmetry; §6.1 the refined agent-ops band;
§7.1 the tail-tempo caveat).

**Class B baseline:** `research/2026-07-23-startup-scale/zero-ops-economics-a0.md`
(the counterfactual: §4 token Fermi and levers, §4.2 token:infra ratio, §5
growth thresholds) · `research/2026-07-23-startup-scale/sandbox-substrate-a0.md`
(§1 the 27.5k run-hour basis; §2.9 the 0.1–0.2 FTE self-managed tax; §4 swap
conditions — the flip triggers this report rewrites) ·
`research/2026-07-23-cloud-scale/r2-sandbox-substrate.md` (the enterprise
anchor and the $73k-vs-$5–15k comparison this report re-derives) ·
`specs/2026-07-23-startup-scale-a0-design.md` (DL entries on the Hetzner ops
tax and the E2B flip threshold).

**Class A:** `round-brief.md` §R4 · the 2026-07-30 pivot decisions ·
`specs/2026-07-30-implement-lane-split-design.md` (the architect/implementer
lane split priced in §6.3).

**Live vendor sources:** listed in full in §12.
