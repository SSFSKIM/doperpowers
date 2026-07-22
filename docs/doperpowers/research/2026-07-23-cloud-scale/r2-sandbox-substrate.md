# R2 — Sandbox/provisioning substrate for per-run ephemeral coding-agent environments

**Question**: what sandbox tech should back per-run ephemeral environments at hundreds–thousands of runs/hour, enterprise-internal (teams isolated, tenants not adversarial), and what are the real numbers?

**Headline answer up front**: at *minutes-to-hours* run durations, the millisecond snapshot-restore arms race (Firecracker 4–28ms, Morph <250ms) is mostly irrelevant to us — a 5-second start is noise against a 40-minute run. What actually decides the substrate is (a) warm *disk* state distribution (repo + deps + build cache, multi-GB), (b) per-host disk-I/O density, and (c) operability on plain Kubernetes. That points at **k8s + gVisor (the GKE Agent Sandbox pattern: template / warm pool / claim) on local-NVMe nodes, with disk-level snapshots keyed by env-spec+lockfile hash** — not microVM memory snapshots, and not a commodity sandbox SaaS.

---

## 1. Findings per question

### Q1 — Isolation/runtime candidates

**Firecracker microVMs.**
- Cold boot ~125–200ms; snapshot restore published as low as **4ms** (research) and reliably **<10ms** (Catalyzer paper); a practitioner writeup reports **28ms end-to-end boots** from snapshots (memory-map the snapshot file, load vCPU state, resume — no kernel boot, no init). Sources: Firecracker docs, arXiv 2102.12892, dev.to/adwitiya.
- **Memory-snapshot caveats are real and documented by the project itself** (snapshot-support.md):
  - *Entropy/identity*: restoring one snapshot into N clones replicates the guest entropy pool, cached random numbers, tokens, UUIDs. Linux 5.18+ reseeds via VMGenID, but "unique identifiers, cached random numbers, cryptographic tokens … **will** still be replicated."
  - *Clock*: guest wall-clock resumes from snapshot-creation time; must be fixed manually (optional `clock_realtime` on x86_64 makes the clock "suddenly jump"). Fly.io confirms in production: resumed machines break JWT validation, cron, cache TTLs, TLS validation for a window.
  - *Network*: "guest network connectivity is not guaranteed to be preserved after resume"; open vsock connections are closed.
  - *Portability*: snapshots require essentially identical host hardware/kernel; only narrow forward-compat paths exist. Cgroups v1 hosts have high restore latency.
  - Diff snapshots are still developer-preview and generally not directly resumable.
- Consequence: Firecracker memory snapshots are superb for **sub-second interactive sandboxes** (E2B's whole business) but bring a real correctness tax (clock/RNG/TCP) that a *fresh-boot-per-run* design simply doesn't have.

**CRIU (container checkpoint/restore).** Checkpoint/restore time scales with allocated virtual memory; practical reports show a 2GB-memory app taking a checkpoint/restore cycle with **30–60s of degraded performance**. Research literature (TClone, arXiv 2605.17320) explicitly calls CRIU "too expensive for speculative agent execution." Production-grade for migration, wrong tool for high-rate fan-out.

**Kata Containers.** Boot ~**300–500ms (QEMU)** / ~**150ms (Cloud Hypervisor)**, ~130–200MB fixed memory overhead per pod; a 2026 benchmark put Kata 3.0 at **~47% median overhead on syscall-heavy work vs 18% for gVisor**, and Firecracker 512MB cold start at 120ms vs Kata 480ms. Kata's value is *kernel-level isolation that runs as a k8s RuntimeClass*. It needs bare-metal or nested-virt nodes.

**gVisor (runsc).** Syscall interception costs 10–30% on I/O-heavy work in adversarial benchmarks; but Google's production numbers at Ant: **70% of apps <1% overhead, another 25% <3%**. Build workloads (the ABSL compile benchmark) are gVisor's known worst case (syscall/filesystem heavy) — expect the 10–30% end there, mitigated by rootfs overlay and Systrap improvements (2023+). Runs on any k8s node, no virtualization extensions needed.

**Plain containers + user namespaces — is VM isolation even warranted?**
- Threat model per NVIDIA's sandboxing guidance and the Microsoft "prompts become shells" work: the attacker is **indirect prompt injection riding in repo content/PRs/deps**, driving a fully-privileged agent. The *mandatory* controls named across these sources are **egress deny-by-default + workspace-scoped filesystem writes + scoped credentials** — i.e., blast-radius controls, not hypervisors. "A sandbox … combined with scoped IAM bindings and network policies that deny egress by default cannot be talked out of its job."
- Anthropic's own open-sourced approach for Claude Code (`sandbox-runtime`) is **bubblewrap + a domain-allowlist egress proxy — no containers, no VMs at all**. That is the vendor of the most-deployed coding agent judging OS-level namespaces + egress filtering sufficient for exactly our workload class.
- The counterweight: container escape via a kernel 0-day is the residual risk; gVisor exists precisely to shrink that kernel attack surface without paying VM overhead. For internal non-adversarial tenants, gVisor is the defensible middle; Firecracker/Kata is warranted only where a compliance boundary demands a separate kernel per team.

**GKE Agent Sandbox** (announced KubeCon '25 / Next '26). A k8s-native primitive set: `SandboxTemplate` (blueprint) → `SandboxWarmPool` (pre-initialized pods) → `SandboxClaim` (per-run checkout). Runtime is **gVisor mandatory** (`runtimeClassName: gvisor`), Kata referenced as future alternative. Warm-pool claims start **in under a second**; third-party coverage cites ~**300 sandboxes/second** creation at cluster level. Egress to RFC-1918/metadata blocked by default. No extra charge beyond GKE resources. Companion **GKE Pod Snapshots** (GA): gVisor-based checkpoint of full pod state (memory+fs), restore = kernel restore in "a few seconds" then background memory streaming; marketed numbers are model-loading (70B model in 80s, "minutes down to seconds"). This is the closest thing to a first-party managed version of exactly our design — and it validates the architecture pattern even if we don't run on GCP.

**Fly.io machines suspend/resume** (Firecracker-based): boots 250ms; suspend/resume exists but production reports show **>30s resumes for 256MB machines** during incidents, snapshots discarded on redeploy or host migration (fall back to cold start), clock-skew bugs, and suspended machines still reserve capacity. Cautionary tale: memory-snapshot dependability is the hard part, not the demo latency.

**AWS managed options**: Lambda hard-caps at **15 minutes** — disqualified for minutes-to-hours runs. Fargate has no duration limit and up to **200GiB ephemeral storage**, but no snapshot/restore, no local NVMe (network-backed storage), per-task pricing that beats nothing at sustained load, and no warm-state story. Usable as an overflow tier only.

### Q2 — Commodity agent-sandbox platforms

| Platform | Cold start | Snapshot/fork | Sustained price | Self-host |
|---|---|---|---|---|
| **E2B** | ~150ms (Firecracker) | pause ≈ **4s/GiB RAM**, resume ≈ 1s; paused kept indefinitely | ~$0.05/vCPU-hr + $150/mo Pro floor | **Yes** — Apache-2.0 infra repo, Terraform for GCP (AWS WIP); needs bare-metal/KVM nodes; Nomad+Consul orchestration ("a real infrastructure project, not a helm install") |
| **Daytona** | ~90ms claimed (27ms optimized) | snapshots + volumes, "unlimited persistence" | ~$0.0504/vCPU-hr, pure usage | OSS core; enterprise self-host offered |
| **Modal** | warm sub-second; cold with image pull 10s+ | filesystem + memory snapshots | **$0.0000394/core/s ≈ $0.142/vCPU-hr** (~3× E2B/Daytona) | No |
| **Morph** | ms-level | **Infinibranch: snapshot/branch/restore whole VM <250ms**, copy-on-write branching — unique | custom; cloud or self-host deal | Partially (commercial) |
| **Northflank** | seconds | container/microVM options | usage | BYOC on your cloud |

**Enterprise-internal credibility check**: at 1,000 sustained concurrent runs × 2 vCPU, usage-priced platforms cost ≈ 2,000 vCPU × 730h × $0.05 ≈ **$73k/month** (E2B/Daytona rates) or ≈ **$207k/month** (Modal) — versus roughly **$5–15k/month for ~15 rented bare-metal NVMe hosts** (Hetzner class) or ~$45–120k for equivalent AWS i3en.metal (reserved vs on-demand). The SaaS platforms are also optimized for a different problem (sub-second interactive REPL sandboxes for product features), not hours-long build/test runs with multi-GB repo state. **E2B self-hosted is the only credible SaaS-lineage substrate for internal use, and it costs you a Nomad/Consul/KVM-bare-metal estate — at which point k8s+gVisor is less exotic to operate.** Verdict: build on k8s; treat E2B-self-host or Morph as accelerators only if VM forking becomes a hard requirement.

### Q3 — Warm state distribution (getting multi-GB repo+deps+cache onto the host fast)

- **Image lazy-loading**: SOCI pull time is ~constant in image size — **1.3GB image in ~2.8s (7.4×), 2.5GB in ~2.8s (9.3×)**; startup becomes proportional to the *working set*, not image size. eStargz: container creation 26s → 8s in serverless tests; but Grab's production comparison found eStargz *slower to app-ready* than SOCI/overlayfs (25s vs 5s) because per-file fetch stalls hit at runtime. Nydus replaces the layer format entirely (block-level dedup). Lesson: lazy-loading trades pull time for runtime page-fault latency — fine for toolchain images, wrong for a build that will touch most of `node_modules` anyway.
- **Local NVMe vs network storage is the decisive number**: 2TB io2 EBS provisioned at 64k IOPS ≈ **$3,850/month**; a 2TB consumer NVMe doing **>1M IOPS costs <$200 once**. RunsOn/Blacksmith/Depot benchmarks all converge: CI-class workloads are IOPS-bound and network volumes lose. Blacksmith's architecture = ephemeral VMs + **colocated NVMe cache service (>400MB/s hits, up to 40× faster Docker builds vs network-bound caching)**; Depot's equivalent is persistent NVMe layer caches. This independently corroborates Cursor's finding that disk I/O, not CPU/RAM, is the single-host ceiling.
- **Practical distribution ladder for us**: (1) toolchain image pre-pulled/pinned on every node (or SOCI-indexed); (2) post-install snapshot as a **content-addressed disk artifact** (tar/zstd of workspace, or better an overlayfs lowerdir / ZFS-btrfs clone) held in a node-local NVMe content cache Blacksmith-style, backfilled from object storage at 1–10GB in seconds on 10–25Gbps NICs; (3) shared network build caches (Bazel remote cache, sccache, pnpm store) as the *incremental* layer — they avoid recomputation rather than re-download, and are orthogonal/complementary.

### Q4 — Capacity math (1,000 concurrent runs, 1–4 vCPU / 4–16GB, NVMe-heavy)

- Take the midpoint: 2 vCPU / 8GB / ~30GB NVMe scratch per run → 2,000 vCPU, 8TB RAM, 30TB scratch aggregate.
- Coding agents idle most of wall-clock waiting on LLM tokens; CPU oversubscription of 2–4× is safe (Cursor: CPU/RAM never the ceiling). **RAM is the packing constraint; disk I/O is the performance constraint.**
- Reference host: i3en.metal-class (96–128 vCPU, 768GB–1TB RAM, 8× NVMe ≈ 30–60TB, ~16GB/s aggregate read, ~2M IOPS) or Hetzner dual-NVMe bare metal. At 8GB/run with headroom → **~80–110 runs/host RAM-bound**. I/O check: if ~⅓ of runs are in an active build burst at 300–500MB/s each, that's ~10–17GB/s — right at the host ceiling, matching Cursor's "many GB/s" report; so ~100/host is realistic *only* with NVMe scratch, and would collapse to ~10–20/host on network volumes.
- **Fleet: ~10–15 large NVMe hosts + 30% headroom ≈ 15–20 hosts.** This is a small, boring fleet — the scale target does not require exotic infrastructure. Industry practice for the I/O storm is uniform: **local NVMe scratch, ephemeral, destroyed with the run; durability lives elsewhere** (object storage for snapshots/caches, the board/log for work identity — which matches our doctrine that the durable log is the identity and compute is disposable).

### Q5 — Drift/staleness detection (the round-1 open question)

Prior art converges on **content-hash keying, not detection-after-the-fact**:
- **DevPod/devcontainer prebuilds**: hash the environment config files → image tag; config change ⇒ different hash ⇒ automatic rebuild. The devcontainer spec adds a **lockfile** (pinned feature versions + checksums) precisely to make cache keys stable and honest.
- **GitHub-Actions-style cache keys** (`hashFiles('**/package-lock.json')`) are the same idea for dependency stores — universal, boring, works.
- **Fly.io**: snapshots are "tied to the exact code and state of the machine they were taken from; deploy new code and the old snapshot can't be resumed safely and is **discarded**" — invalidate-on-deploy, never repair.
- **Cursor**: snapshots GC'd after 90 idle days (TTL as the backstop for slow drift the hashes can't see: registry mutations, base-image CVE churn).
- Nobody credible does "diff the environment against HEAD and patch it." The pattern is: **key exactly, restore only on exact hit, rebuild+re-certify on miss, TTL everything.**

**Synthesized answer for our architecture**: snapshot key = `hash(env-as-code spec) ⊕ hash(all lockfiles) ⊕ toolchain-image digest ⊕ (host kernel/arch class if memory snapshots ever used)`. Exact hit → restore and run the env spec's *certification commands* as a cheap smoke probe before handing the sandbox to the worker (the certification gate from round 1 gives us the drift probe for free — expected-output commands ARE the drift detector). Miss → restore nearest base, incremental install, full re-certify, publish new snapshot under the new key. TTL/GC (e.g., 30–90 idle days) plus scheduled re-certification for long-lived keys catches non-hermetic drift (mutable registries, `latest` tags).

---

## 2. Decision table

Requirements: R1 restore/start fast *relative to run length* (seconds fine), R2 hours-long runs, R3 k8s-operable, R4 fits internal-tenant threat model (prompt-injected agent, non-adversarial teams), R5 I/O density on NVMe, R6 ops burden.

| Tech | R1 start | R2 long runs | R3 k8s-op | R4 threat fit | R5 I/O density | R6 ops | Verdict |
|---|---|---|---|---|---|---|---|
| Plain containers + userns + egress proxy | ~20ms | ✔ | native | acceptable (Anthropic ships weaker for same threat); kernel-0day residual | best (native I/O) | lowest | Floor option; fine if security org accepts shared kernel |
| **gVisor (runsc / Agent Sandbox pattern)** | warm-pool <1s | ✔ | **native RuntimeClass, any node** | **strong fit — kernel-surface reduction w/o VMs; Google's pick for exactly this workload** | 10–30% I/O tax worst-case, <3% typical | low | **Recommended** |
| Kata (CLH) | ~150ms boot | ✔ | RuntimeClass, needs bare-metal/nested-virt nodes | more than needed | ~47% syscall-heavy overhead | medium | Only if separate-kernel mandate |
| Firecracker + memory snapshots (E2B-style) | 4–30ms restore | ✔ but snapshot clock/RNG/TCP caveats | poor (Nomad/Consul or custom; not k8s-native) | more than needed | good | **high** (KVM bare metal, snapshot compat matrix) | Overkill; caveats cost correctness |
| CRIU | 30–60s class at multi-GB | ✔ | k8s alpha (forensic checkpoint) | n/a | n/a | high | Rejected for fan-out |
| Fargate | seconds–minutes | ✔ (no limit, 200GiB) | ECS not k8s | fine | **no local NVMe — fails I/O ceiling** | low | Overflow tier only |
| SaaS sandboxes (E2B/Modal/Daytona/Morph cloud) | ms | mixed (session caps, pricing) | n/a | data-residency/credential concerns for internal repos | opaque | none | ~$73–207k/mo at target scale vs ~$10k self-hosted — rejected as substrate |

## 3. Recommendation

**Kubernetes + gVisor RuntimeClass, per-run pods, warm pools, local-NVMe nodes — i.e., self-host the GKE Agent Sandbox shape (or adopt Agent Sandbox itself if the org lands on GCP).**

1. **Isolation**: gVisor pods, one per ticket run, exit-and-replace (already decided). Egress deny-by-default with a domain-allowlist proxy and per-run scoped credentials — these, not the hypervisor, are the controls the threat model actually demands. Teams separated by namespace + NetworkPolicy + node pools where required. Escalate to Kata only for a repo class with a hard compliance boundary.
2. **Warm state**: skip memory snapshots entirely at first. The snapshot ladder from round 1 maps to: pinned toolchain image (node-local, SOCI-indexed if >2GB) → **post-install workspace snapshot as content-addressed disk artifact on a node-local NVMe cache, backfilled from object storage** → overlayfs clone per run (sub-second on cache hit, seconds on backfill). This delivers the Cursor "70% faster" economics without Firecracker's clock/RNG/TCP snapshot tax, and it's why run-length matters: 5s of restore against 30-minute runs is 0.3%.
3. **Capacity**: ~15–20 bare-metal-class NVMe hosts carry 1,000 concurrent runs (RAM-packs ~100/host; NVMe is what keeps that density real). Scratch is ephemeral and dies with the pod; durability lives in object storage and the board.
4. **Drift (the open question)**: don't detect drift — make it structurally impossible to use a stale snapshot. Composite content-hash key (env-spec ⊕ lockfiles ⊕ image digest); exact-hit restore runs the certification commands as a smoke probe; any miss rebuilds through the full certification gate; TTL/GC at 30–90 idle days as the backstop for non-hermetic inputs. Fly's invalidate-on-deploy and DevPod's hash-keyed prebuilds are the precedents.

## 4. Confidence notes

- **High confidence**: Lambda 15-min cap; Fargate 200GiB/no-time-limit; Firecracker snapshot caveats (project's own docs); gVisor production overhead figures (Google/Ant first-party); SOCI constant-time pull numbers; EBS-vs-NVMe cost/IOPS gap; E2B self-host requirements (first-party repo); drift = hash-keying as universal industry pattern.
- **Medium confidence**: GKE Agent Sandbox "300 sandboxes/sec" (third-party coverage, not in Google docs I fetched — docs confirm only "under a second" from warm pool); Kata-vs-gVisor 47%/18% comparison (single 2026 benchmark site); Daytona 90ms/Morph 250ms (vendor marketing, unverified independently); Modal/E2B pricing exactness (aggregator articles, order-of-magnitude solid).
- **Low confidence / estimated by me**: capacity math (per-run burst I/O of 300–500MB/s and ⅓ duty cycle are assumptions calibrated to Cursor's qualitative "many GB/s" finding, not measured); SaaS-vs-self-host monthly cost figures are my arithmetic from listed rates.
- **Gap**: Cursor's Anyrun internals remain undisclosed; no primary-source per-host density numbers exist anywhere public. Our density estimate should be validated with a 1-host load test before fleet sizing is committed.

## 5. Sources

- Firecracker snapshot docs: https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md
- Snapshot uniqueness (RNG/clock) paper: https://ar5iv.labs.arxiv.org/html/2102.12892 ; 28ms sandbox boots: https://dev.to/adwitiya/how-i-built-sandboxes-that-boot-in-28ms-using-firecracker-snapshots-i0k
- GKE Agent Sandbox docs: https://docs.cloud.google.com/kubernetes-engine/docs/how-to/agent-sandbox ; Pod Snapshots: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/pod-snapshots ; InfoQ: https://www.infoq.com/news/2026/05/gke-agent-sandbox-hypercluster/
- gVisor performance: https://gvisor.dev/blog/2021/12/02/running-gvisor-in-production-at-scale-in-ant/ ; https://github.com/google/gvisor/blob/master/g3doc/architecture_guide/performance.md ; seccomp/ABSL: https://gvisor.dev/blog/2024/02/01/seccomp/
- Kata/gVisor/Firecracker comparative: https://johal.in/benchmark-gvisor-10-vs-kata-containers-30-vs/ ; https://github.com/bikramkgupta/container-runtime-benchmarks
- CRIU limits: https://www.devzero.io/blog/checkpoint-restore-with-criu ; TClone (CRIU too slow for agent forking): https://arxiv.org/pdf/2605.17320
- Fly.io suspend/resume: https://fly.io/docs/reference/suspend-resume/ ; slow-resume incident: https://community.fly.io/t/fixed-unreasonably-slow-resumes-of-suspended-machines/26207/1 ; long-running blueprint (snapshot discard on deploy): https://fly.io/docs/blueprints/long-running-tasks/
- Lambda/Fargate limits: https://awsfundamentals.com/blog/lambda-limitations ; https://oneuptime.com/blog/post/2026-02-12-configure-fargate-ephemeral-storage/view
- Platform comparisons/pricing: https://www.superagent.sh/blog/ai-code-sandbox-benchmark-2026 ; https://www.agenticwire.news/article/e2b-vs-modal-agent-sandbox-cost-comparison ; https://www.zenml.io/blog/e2b-vs-daytona ; https://rywalker.com/research/ai-agent-sandboxes
- E2B self-host: https://github.com/e2b-dev/infra/blob/main/self-host.md ; https://www.beam.cloud/blog/how-to-self-host-code-sandbox
- Morph Infinibranch: https://www.morph.so/blog/infinibranch/ ; https://cloud.morph.so/docs/documentation/snapshots
- Lazy loading: SOCI paper: https://arxiv.org/html/2607.06868v1 ; Grab production study: https://engineering.grab.com/docker-lazy-loading ; eStargz: https://github.com/containerd/stargz-snapshotter
- NVMe vs EBS for CI: https://runs-on.com/benchmarks/github-actions-disk-performance/ ; https://pythonspeed.com/articles/slow-ci-aws-ec2/ ; Blacksmith caching: https://info.blacksmith.sh/task/blog/github-actions-fast-persistent-storage
- Threat model/controls: https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/ ; https://www.microsoft.com/en-us/security/blog/2026/05/07/prompts-become-shells-rce-vulnerabilities-ai-agent-frameworks/ ; Anthropic sandbox-runtime: https://github.com/anthropic-experimental/sandbox-runtime ; https://code.claude.com/docs/en/sandboxing
- Drift/hash-keying: DevPod prebuilds: https://devpod.sh/docs/developing-in-workspaces/prebuild-a-workspace ; devcontainer lockfile spec: https://github.com/devcontainers/spec/blob/main/docs/specs/devcontainer-lockfile.md
- Round-1 internal context: Cursor environment/autoinstall analysis (70% faster builds on cache hit, 90-day snapshot GC, disk-I/O host ceiling, Anyrun scale claim).
