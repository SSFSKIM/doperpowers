# R5 — Egress transport: per-pod proxy sidecar vs L3/FQDN policy (2026-07-31)

> **Supplemental to the clean-slate round** (post-synthesis, human-triggered):
> the human proposed a dedicated network-egress sidecar container ("main
> agent container has zero direct egress; a proxy container mediates") and
> asked how other companies handle agent egress, noting that network
> restriction is a real friction source for long-running work. Three
> parallel researchers (opus) surveyed live sources on 2026-07-31: (1)
> first-party vendor practice (Anthropic, OpenAI), (2) the field
> (agent products + sandbox vendors + friction/incident record), (3)
> k8s/gVisor platform prior art + the proxy-compat friction axis. Every
> claim below carries its source; VERIFIED = official/primary page or
> upstream source code, REPORTED = third-party. This report feeds a
> proposed revision of the swarm reference architecture's §3.2 Layer-3
> enforcement (DL-14 candidate).

## 0. Verdict up front

1. **The industry has already converged on the human's proposal.** Every
   first-party agent-runtime implementation surveyed — Anthropic
   sandbox-runtime (srt), Claude Code sandboxing, Claude Managed Agents,
   OpenAI Codex cloud + CLI, GitHub Copilot coding agent, Devin, Factory,
   Vercel Sandbox, Cloudflare Sandboxes, E2B — enforces egress at a
   **proxy the agent cannot bypass**. None ships DNS-snooping FQDN policy
   or L3-only rules as its product-layer enforcement. srt goes furthest:
   it deletes the sandbox's network namespace outright so proxy-or-nothing
   is structural (VERIFIED, srt README).
2. **The most load-bearing single artifact is GitHub's open-source agent
   firewall (`github/gh-aw-firewall`)** — a three-container pod-shaped
   sandbox that is exactly the proposed design: Squid forward proxy
   enforcing domain ACLs; an **iptables init container sharing the agent's
   network namespace** that DNATs 80/443 to the proxy before user code
   starts (belt: proxy env vars; braces: DNAT for proxy-unaware tools);
   DNS restricted to allowlisted resolvers at L3 (anti-tunneling);
   non-HTTP dropped at L3/L4; **NET_ADMIN granted only to the init
   container, never the agent**; optional credential-holding API-proxy
   sidecar. (VERIFIED, github.com/github/gh-aw-firewall.)
3. **Transparent interception (iptables REDIRECT), not proxy env vars, is
   what erases the friction axis.** The env-var compliance gap is measured
   and wide: Node native `fetch` ignores `HTTP_PROXY` below Node 24
   (undici #1650), Playwright doesn't pass proxy env to the browser
   (#20741) and Chromium won't send Proxy-Authorization (#37444), Gradle/
   JVM need their own properties, npm/Go have documented quirks, and even
   Claude Code's own docs warn that background-agent supervisors
   inherit proxy env only "when that shell happened to cold-start the
   supervisor". LangChain states transparency as the explicit design
   reason for the LangSmith Auth Proxy: "not implemented by hoping every
   language, package manager, SDK, or subprocess respects HTTP_PROXY."
4. **gVisor supports the required interception primitive — and the
   general-Linux advice is inverted.** Upstream gVisor implements the
   iptables `nat` table with REDIRECT/DNAT/SNAT and `SO_ORIGINAL_DST`
   (VERIFIED: `pkg/tcpip/stack/iptables.go`, `netfilter/targets.go`,
   `test/iptables/nat.go`), and does **not** implement TPROXY. The
   widely-cited claim that gVisor lacks the nat table (OpenSandbox #934)
   is contradicted by upstream source; the observed failure is the
   `iptables-nft` wrapper (gVisor has no nftables interpreter — issue
   #10510) — fixed by invoking `iptables-legacy`. So: **REDIRECT-style
   transparent proxying is the supported path inside a gVisor pod;
   TPROXY-based designs do not port.**
5. **Credential injection at egress is a settled, shipped pattern** — six+
   independent implementations (Claude Code `mask` + `injectHosts`;
   Managed Agents vaults "substituted at egress… the agent never sees the
   secret"; Vercel "credentials brokering"; Cloudflare outbound Workers;
   LangSmith Auth Proxy; iron-proxy; agentgateway implementing the IETF
   CB4A draft's Model A). It structurally requires a TLS-terminating
   proxy ("masking fails closed" without `tlsTerminate` — Claude Code
   docs; "egress is yours, so there's nowhere to substitute the secret" —
   the stated reason CMA vaults don't work on self-hosted sandboxes).
   **This subsumes the goal of the K6 execution sidecar** (preventing
   executed code from ever touching the push credential) at the network
   layer, without T14's cross-container exec routing.
6. **The incident record indicts hostname-string matching, not proxies.**
   Claude Code's SOCKS5 allowlist was bypassable for ~5.5 months via a
   null-byte parser differential (`attacker.com\x00.google.com` passes JS
   `endsWith()`, libc dials `attacker.com`; v2.0.24→v2.1.89, fixed
   silently 2026-04-01, no CVE); Anthropic's own docs concede domain
   fronting defeats a non-TLS-terminating proxy; the July-2026 frontier-
   lab intrusion escaped *through an allowlisted* package-registry proxy.
   Production systems that survived review (Snowflake SNAS, GitHub AWF)
   all pair **L7 proxy policy with a kernel L3/L4 default-drop floor**.
7. **The friction record is configuration-shaped, not architecture-shaped
   — and the fixes are the proxy's dynamism.** Copilot's ~200-domain
   curated allowlist still missed Playwright's Chrome download; Codex's
   "unrestricted" mode 403s on an internal allowlist; Anthropic closed
   "unblock my own domain" as not-planned. Vendors fixed friction with
   org-level self-service, egress dashboards, first-use allow prompts,
   and **runtime policy updates without restart** (Vercel, Modal, Daytona,
   Cloudflare all ship this) — never by abandoning the proxy layer. Our
   env-issue/park lane is exactly this pattern's board-native form.

## 1. What each layer can and cannot express

| Capability | L3 NetworkPolicy | FQDN policy (DNS-snoop) | CONNECT/SNI proxy (no MITM) | TLS-terminating proxy |
|---|---|---|---|---|
| Block lateral movement / metadata | yes | — | — | — |
| Domain allowlist | no | yes (holes below) | yes (hostname) | yes |
| Survive CDN IP churn / shared VIPs | no | **no** — 50-IP cap (GKE), no CNAME chase, one allowed domain = every domain on the VIP (Google's own doc) | yes | yes |
| Close DNS tunneling | partial (force resolver) | **no** (port 53 must be open to snoop) | yes (no direct DNS needed; resolver behind proxy) | yes |
| HTTP method / path policy | no | no | no | yes (Codex ships GET/HEAD/OPTIONS-only mode) |
| Request logging (domain+path) | no | no | host only | full |
| **Credential injection at egress** | no | no | **no** | **yes** (the only layer that can) |
| Runtime policy update w/o pod restart | no (object churn) | no | yes | yes |
| Cert-pinning / Docker compat | n/a | n/a | unaffected | breaks without excludes (documented: Docker, Go CLIs on macOS, pinned clients) |

The two named weaknesses of proxies: hostname-parsing fragility (the
null-byte incident — "enforce egress on the packet, not on the string")
and, without MITM, domain fronting. Both are answered by the same
composition: kernel-level default-drop beneath the proxy, TLS termination
where the policy needs to see content.

## 2. Proposed architecture (DL-14 candidate for the reference spec)

**Layer 3's enforcement mechanism becomes a pod-local egress-proxy
sidecar over a kernel floor; FQDNNetworkPolicy is demoted from
load-bearing to optional belt.** Layers 1–2 (gVisor; RFC-1918/metadata
block + in-cluster allowances) are unchanged.

- **Pod anatomy (the AWF shape, adapted):** native sidecar container
  (k8s ≥1.29/1.33-GA `initContainers` with `restartPolicy: Always`;
  its readinessProbe gates pod readiness so no window exists where the
  agent has egress before policy loads) + an `iptables-legacy` init step
  that REDIRECTs 80/443 to the sidecar, forces DNS to the sidecar's
  resolver, and default-drops everything else in the pod netns.
  **NET_ADMIN goes to the init container only — never the agent
  container** (a confused or injected agent cannot undo the rules).
- **Class policy moves from k8s objects into proxy policy, delivered at
  claim** — riding the same in-band claim handshake as credentials
  (r2 §4.4). This is what makes egress *dynamic*: research-class = open
  mode with logging (the human's friction posture preserved verbatim —
  transparent, no allowlist, Playwright unaffected); implement-class =
  allowlist; review-class = allowlist (DL-13, veto pending). A blocked
  request surfaces as a structured proxy event → env-issue/park →
  policy update **without pod restart** — friction becomes a board
  event, not a stalled run.
- **Phase A (no MITM):** CONNECT/SNI hostname allowlisting + full
  connection logging + L3 floor. Cheap, no CA tax, covers policy +
  dynamism + observability. Residual: domain fronting (accepted at
  Phase A, as Anthropic's default does), body-blind.
- **Phase B (TLS termination + credential brokering, implement lane
  first):** per-pod ephemeral CA (Cloudflare pattern — CA installed by
  entrypoint into every trust store; cannot be baked into the image;
  `NODE_EXTRA_CA_CERTS` additive-vs-replace is the known landmine;
  Claude Code itself reads the OS trust store on Node 22.15+), push
  credential held by the sidecar and injected only toward the git host
  over HTTPS (git forced HTTPS-only; SSH-over-CONNECT rejected as an
  opaque channel). The agent container never holds the push token —
  **T14 is redefined** from "cross-container exec routing" (heavy,
  unprecedented in the field) to "egress credential brokering sidecar"
  (light, six shipped precedents). The iron-proxy dummy-token variant
  (sandbox holds a worthless sentinel; proxy swaps it at egress) keeps
  token-expecting CLIs working unmodified and makes exfiltrated tokens
  inert — same shape as Claude Code `mask`.
- **Non-HTTP:** srt's answer — an optional SOCKS5 listener beside the
  HTTP proxy for genuinely needed TCP (DB connections in dev lanes);
  default posture is L3-drop for non-80/443 (AWF's answer). Named hole
  either way: an allowed SSH/opaque stream is uninspectable.
- **Known limits carried honestly** (from the vendors that ship this):
  egress injection cannot serve request-signing clients (AWS SigV4),
  format-validating CLIs, or OAuth token-exchange flows (the returned
  session token lands in the sandbox unredacted — CMA docs); cert-pinned
  clients need per-domain TLS-termination excludes; Docker-in-sandbox
  remains incompatible; the sidecar is a credential holder (CB4A rates
  broker compromise CRITICAL — mitigated by per-pod scoping: one pod's
  sidecar holds one run's secrets, revoked at reclaim).

**What this buys over the current spec:** closes the DNS-tunneling hole
critique F4 flagged (no direct DNS from the agent container at all);
survives CDN churn that FQDNNetworkPolicy structurally cannot (50-IP
cap, no CNAME, shared VIPs); makes per-run egress policy dynamic (the
warm-pool problem solved the same way as credentials — nothing
run-specific in env); converts blocked-fetch friction into a policy
event; and absorbs K6's credential-touch goal at a fraction of T14's
original cost. **What it costs:** a sidecar per pod (~tens of MB RSS —
the Istio ambient counter-argument doesn't transfer: agent egress is
bursty and the pod IS the tenant boundary, so per-node sharing would
remix tenants at the exact seam we isolate), the Phase-B CA tax, and
two cluster verifications before commitment (§3).

## 3. What only the cluster can verify (added to the standing list)

1. **GKE Sandbox multi-container pods share one gVisor sandbox / one
   netns** — load-bearing for the whole design; no Google primary
   statement found. Bench-test first.
2. **`iptables-legacy` REDIRECT + `SO_ORIGINAL_DST` works end-to-end
   inside a GKE Sandbox pod** — upstream test-suite evidence exists;
   GKE integration does not. Bench-test second.
3. The Agent Sandbox hardening VAP **blocks capability additions for
   init containers** (documented: breaks service-mesh init) — the policy
   ships `EnsureExists` and is editable to exempt the named egress-init
   container for NET_ADMIN; confirm the edit survives addon upgrades.
4. Sidecar RSS/latency under gVisor at our pod shape; per-pod CA
   entrypoint time across the toolchain trust stores (Phase B).

## 4. Sources (fetched 2026-07-31)

**Anthropic (VERIFIED):** github.com/anthropic-experimental/sandbox-runtime
(netns removal; HTTP+SOCKS5 split; deny-by-default; env-var limitation;
domain-fronting caveat) · code.claude.com/docs/en/sandboxing.md
(tlsTerminate; credential mask/injectHosts fails-closed; trust scoping;
first-use prompts; named breakages) · platform.claude.com/docs/en/
managed-agents/vaults.md + environments.md (egress substitution;
host+location scoping; two-layer policy; self-hosted limitation; SigV4/
OAuth-exchange limits) · code-execution-tool.md (zero-egress tier) ·
code.claude.com/docs/en/network-config (OS trust store, Node 22.15+;
no SOCKS; background-agent env-var warning) ·
github.com/anthropics/claude-code/.devcontainer/init-firewall.sh
(resolve-once ipset; open UDP/53+TCP/22).

**OpenAI (VERIFIED unless noted):** learn.chatgpt.com/docs/cloud/
internet-access (default-off; presets; GET/HEAD/OPTIONS mode; risk
rationale) · docs/environments/cloud-environment.md (all traffic
proxied; secrets removed before agent phase) · agent-approvals-security
(CLI network_proxy, deny-wins, DNS-rebinding best-effort + lower-layer
recommendation) · REPORTED: openai/codex#20928 (Envoy CONNECT 403,
env-var-independent), #23197 (non-HTTP unsupported), #22387 (no DNS in
sandbox); community.openai.com/t/1362921 (hardcoded allowlist friction).

**Field (VERIFIED unless noted):** github/gh-aw-firewall (3-container
Squid+iptables-init+credential-sidecar; NET_ADMIN never to agent; DNS
resolver allowlist) · docs.github.com Copilot firewall + allowlist
reference (default-on, ~200 domains, warnings in PR; MCP/setup-steps
exemptions; "sophisticated attacks may bypass") · docs.devin.ai/cli/
sandbox (loopback managed proxy; GET-only limited mode; admin-
authoritative allowlist; "currently unstable") · cursor.com/docs/
cloud-agent/security-network (allow-all default; 3 modes; anti-wildcard
guidance) · docs.factory.ai/cli/configuration/sandbox (deny-by-default
HTTP/SOCKS proxy; allow-once/always; "every allowed domain is a leak
channel") · e2b.dev/docs/sandbox/internet-access (Host/SNI inspection
80/443-only; runtime updateNetwork; header transforms beta; "blocked may
appear successful") · modal.com/docs/guide/sandbox-networking (TLS-only
domain allowlist; runtime updates alpha) · daytona.io/docs/network-limits
(tiered defaults; 20-domain cap; hot reconfigure) · vercel.com/docs/
sandbox/concepts/firewall (SNI matching; credentials brokering; requests
proxying + OIDC stamping; per-sandbox CA; SNI-less passthrough gap) ·
blog.cloudflare.com/sandbox-auth + developers.cloudflare.com/containers
(outbound Workers outside sandbox; ephemeral per-sandbox CA at runtime
not build time; 80/443-only; DNS forced to Cloudflare resolvers) ·
arxiv.org/abs/2606.17533 (Snowflake SNAS: eBPF + overlay + distributed
egress proxies) · REPORTED friction: community discussions #180953
(Playwright Chrome blocked), #163374 (allowlist var trap), #171470 +
github.blog 2026-04-03 changelog (org-level governance gap→fix) ·
anthropics/claude-code#52982 (own-domain block, not planned) ·
innoq.com/en/blog/2026/03/dev-sandbox-network (12-URL Squid, no-MITM
rationale, per-tool proxy config pain).

**Incidents (REPORTED):** null-byte SOCKS5 bypass write-ups
(medium.com/@Koukyosyumei; oddguan.com — v2.0.24→v2.1.89, "enforce
egress on the packet, not on the string") · simonwillison.net 2026-07-28
(intrusion through allowlisted registry proxy; secondary summarization,
JFrog/Modal attribution unconfirmed) · CSA research note on
CVE-2025-66032 (egress filtering recommended; caveat: that exfil rode
allowed github.com APIs).

**Platform (VERIFIED unless noted):** docs.cloud.google.com FQDN network
policies (50-IP cap, 100/hostname quota, no CNAME chase, single-label
wildcards, kube-dns-only, shared-VIP over-permission) · agent-sandbox
doc (L3-only managed posture, public egress allowed; VAP blocks
service-mesh init capability adds, EnsureExists) · sandbox-pods doc
(no privileged/hostPath; NET_RAW gating) · gVisor upstream source
(nat table + REDIRECT/DNAT/SNAT + SO_ORIGINAL_DST tests; no TPROXY;
no nftables — issue #10510; #9917 iptables-nft error closed-stale) ·
kubernetes.io sidecar-containers (v1.33 stable; ordered start; probes;
reverse-order shutdown) · cilium docs (toFQDNs caps/flags; node-local
Envoy; DNS-proxy HA caveat) + REPORTED cilium#31197/#28427 (truncated-DNS
and many-IP failures) · CNCF egress guide (port-53 exfil concession) ·
REPORTED: OpenSandbox#934 (the refuted no-nat claim) · istio.io ambient
blog + solo.io (per-pod overhead argument — scoped as non-transferring) ·
undici#1650, playwright#20741/#6094/#37444, golang#16704/#40909,
npm#6957/#18735, headroom#998, cline#8816, bruno#6854 (env-var and CA
compliance record) · linkerd.io/2-edge/features/nft (iptables-nft split) ·
langchain.com/blog LangSmith Auth Proxy (transparency rationale) ·
github.com/ironsh/iron-proxy (dummy-token swap; MITM+DNS; limits) ·
agentgateway.dev CB4A blog (Model A; broker-compromise CRITICAL) ·
gateway.envoyproxy.io credential-injection (alpha, ingress-side) ·
opensource.zalando.com/skipper egress bearer injection ·
corkscrew (SSH-over-CONNECT).
