# Prior cloud research, filtered for one person's cloud dev environment

Subagent digest, 2026-09-30. Written for the personal-cloud-environment design question
(see `../../2026-09-30-personal-cloud-env-research.md`). Read-only pass over the 2026-07
cloud-scale / startup-scale / clean-slate research and the worker-host infra.

**How to read the citations.** Unless noted, paths are under `docs/doperpowers/`. Short names:
- **CS** = `2026-07-23-cloud-scale-research.md`
- **SS** = `2026-07-23-startup-scale-research.md`
- **R2S / LL / OI / MA / AI** = `research/2026-07-23-cloud-scale/` files `r2-sandbox-substrate`, `lessons-learned`, `own-infra`, `managed-agents`, `autoinstall`
- **SA0 / MAS / ZO** = `research/2026-07-23-startup-scale/` files `sandbox-substrate-a0`, `managed-agents-substrate`, `zero-ops-economics-a0`
- **RB / R1 / R2P / R4 / R5** = `research/2026-07-30-clean-slate/` files `round-brief`, `r1-runtime-gaps`, `r2-platform`, `r4-economics`, `r5-egress-transport`
- **P1–P4** = `research/2026-07-30-clean-slate/probes/p1…p4`
- **SCS / SWS / SA0S** = `specs/` files `2026-07-23-cloud-scale-reference-architecture-design`, `2026-07-30-swarm-reference-architecture-design`, `2026-07-23-startup-scale-a0-design`
- **WH** = `infra/worker-host/README.md` (plus its `env.example` and `env.triage.example`)
- **MAST** = `2026-07-12-managed-agents-steals.md`

The core finding is that this repo already has a single-VM "persistence in storage, compute disposable" design, built on a Hetzner server with the home directory on a volume and Tailscale access. The cloud-scale research then argued against much of it *because of scale*. At personal scale most of those arguments reverse (see §6).

## 1. Sandbox and runtime verdicts, with the numbers

**Enterprise choice: k8s + gVisor, one pod per run, on local-NVMe hosts.** Warm state is treated as a disk problem, not a memory-snapshot problem (R2S:5, R2S:92-99; CS:591-645; SCS:153-186).
- **gVisor overhead:** 70% of apps under 1% and another 25% under 3%. Syscall- and filesystem-heavy builds cost 10–30% (R2S:27).
- **Kata:** about 150 ms boot with Cloud Hypervisor, 300–500 ms with QEMU. About 47% overhead on syscall-heavy work versus 18% for gVisor. It needs bare metal or nested virtualization (R2S:25).
- **Firecracker:** cold boot 125–200 ms; snapshot restore 4–28 ms (R2S:14). It was rejected for correctness, not speed:
  - one snapshot restored into N clones copies the entropy pool, UUIDs and tokens;
  - the wall clock resumes at snapshot time, which Fly saw break JWT validation and cron;
  - open network connections are not preserved (R2S:15-21).
- **CRIU:** 30–60 s at multi-GB sizes (R2S:23).
- **Lambda:** 15-minute hard cap, disqualified. **Fargate:** no local NVMe; overflow tier only (R2S:38).
- **Why start latency was dismissed:** "5 s against a 30–40 min run is 0.3%" (R2S:5, R2S:97). This depends on run length, which matters for §6.
- **The real controls for a prompt-injected agent:** egress deny-by-default, workspace-scoped writes and scoped credentials — "blast-radius controls, not hypervisors." Anthropic's own sandbox-runtime (srt) is just bubblewrap plus an egress proxy (R2S:30-32).
- **Disk:** local NVMe versus network volume is the decisive number. 2 TB io2 EBS at 64k IOPS is about $3,850/mo; a consumer NVMe doing over 1M IOPS costs under $200 once. SOCI lazy loading pulls a 2.5 GB image in about 2.8 s (R2S:54-55).
- **Snapshot keys:** hash(env-spec) ⊕ hash(lockfiles) ⊕ image digest. Restore only on an exact match; rebuild on a miss; expire after 30–90 idle days (R2S:67-74).

**2026-07-30 platform: upstream Agent Sandbox CRDs** (`kubernetes-sigs/agent-sandbox`, v1beta1, pre-GA churn) (R2P:26-38).
- Its `Sandbox` object gives stable hostname and identity, persistent storage that survives restarts, and pause/resume (R2P:88-98). The swarm design called this "more than our cattle doctrine needs" (R2P:152-157).
- Claiming from a warm pool is sub-second. A cold node takes about 1–2 min (R2P:211-216).
- GKE's managed form is free, but allows public egress by default (R2P:119-126).

**Startup-scale (A0) choice: E2B** (SA0:285-297).
- Firecracker create about 150 ms; pause about 4 s per GiB of RAM; resume about 1 s; paused sandboxes kept indefinitely, but paused-storage pricing is unpublished (SA0:61-69).
- Runner-up Daytona: named, digest-pinned snapshots and unlimited session length (SA0:98-103). Its egress allowlist was corrected post-review to 20 domains plus 10 CIDRs (SA0:3-11).

**Measured cost of one Claude Code process** (P1:17-28; R1:229-235):
- Native `claude` binary: 245 MB (darwin-arm64); the Linux size was never measured (P1:177-182).
- Harness wrapper: 70–105 MB RSS idle.
- Engine: 350–413 MB RSS before a turn completed. This is a floor, not a ceiling (P1:119-128).
- The installed `claude daemon run` process idles at about 122 MB (P1:144-147).
- Engine start: 51 ms warm versus 602 ms cold (R1:82).
- Starting assumption: at least 1 GiB per session (R1:234). Pod request suggested at 1 vCPU / 2 GiB, 4 GiB limit (R2P:244-247).

**What changes with one person and a few sessions:**
- Density, fleet-host packing (R2S:58-63) and warm-pool burst sizing (R2P:218-232) stop mattering.
- Interactive attach reverses the "startup latency is noise" premise. Cursor built hibernate/resume of VMs between messages for exactly that interactive case (LL:18); we rejected it only because our workers are batch-shaped (LL:84).
- Memory-snapshot correctness caveats still apply. The clock and network issues bite any VM resumed after idle time.

## 2. State doctrine: what is durable and what is cache

- **Invariant:** "The durable log is the identity of the work; compute is disposable." Cursor and Anthropic converged on it independently (CS:58-62).
- **Three authorities:** ticket state, run ownership, and run history (CS:84-88; rule at CS:451-452).
- **Snapshots are cache, never identity.** A deleted snapshot must cost only warm-start time (CS:99-103, CS:453). Cursor expires snapshots after 90 idle days.
- **Compaction never rewrites the log;** summaries are derived views (CS:104-107; MA:95-112).
- **Environment registry:** "a cache with a certificate"; losing it costs one re-certification run (CS:213-216; AI:109).
- **Caveat 1 — the log records narrative, not artifacts.** Uncommitted worktree state and in-flight background processes die with the compute. The design tolerates this through commit discipline and cheap rebuilds, not by preserving them (SCS:635-645).
- **Caveat 2 — durability ends at the turn** (R1:38-43; P2:193-204; RB:187-192).
  - The engine writes transcripts only at turn boundaries, so a killed process loses the whole in-flight turn in any store.
  - Parked permission, question and plan decisions live in process memory and are lost (P3:435-452).
  - Mitigations: a shutdown grace period at least as long as a turn, small turns, and mirroring parks outward (SWS:95-100).
- **Caveat 3 — a subagent is a subkey, not a session.**
  - It lives at `…/<parent>/subagents/agent-<id>.jsonl` and carries the parent's `sessionId`. Nothing can resume it (P2:17, P2:88-95).
  - The parent transcript holds none of the subagent's turns, so deleting the sidechain directory silently loses the detail (P2:94).
  - A detached `ccx --bg` session does get its own session id and survives its parent (P2:163-185).
  - In-process subagents and background shells die with the parent: the SDK sends SIGTERM on clean exit, and the engine exits on stdin EOF (P2:20, P2:155-161).
- **Session store implementations:**
  - The cc-harness Postgres adapter stores payloads as TEXT (not jsonb), dedups on uuid, and is pooler-safe (R2P:479-511).
  - A0 sizing is 1–3 MB per run, archived to object storage after about 14 days (SA0S:189-202; SS:112-116).
  - Cursor uses content-addressed S3 plus Redis streams; a retried step's partial output is treated as invalid (LL:31-34, LL:79).
  - Managed Agents: the session is an append-only log in a service, with a stateless harness and `wake`/`getSession`/`getEvents` calls (MA:28-55).
- **Single-host prior (the shape you are describing), MAST:77-101 and WH:13-19.** All mutable state lives on one detachable volume, with `$HOME` volume-backed so `~/.claude/projects`, `~/.claude/jobs` and `~/.codex` persist. The machine itself (the "body") is rebuilt by cloud-init. Recovery: new host plus the same volume, and every parked session resumes (WH:141-154).
  - This works because liveness checks are host-aware: registry entries carry the host name, and a rebuilt machine gets a new hostname (env.example:33-37).
  - At fleet scale this volume was judged "itself a pet … doctrine-compliant at one host and doctrine-violating at many" (MA:226-227, MA:315-317).

## 3. What headless Claude Code needs from its host

The r1 and probe findings are about **cc-harness**, a wrapper built on the Claude Agent SDK. They are not about the interactive `claude` terminal app. Running stock interactive `claude` in tmux inside a container would avoid most SDK-only gaps. This split was never evaluated.

**How the SDK starts the engine** (P1:55-59). It runs the native binary with:
`--output-format stream-json --input-format stream-json --setting-sources=user,project,local --permission-mode auto`.
So it reads user settings (`~/.claude/settings.json`). The settings cascade and all 6 permission modes, including `auto` and `dontAsk`, work headless (R1:80).

**Auth:**
- `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, valid about a year, pasted into an env file (env.example:13-15; WH:70-71; P1:13-15). Or `ANTHROPIC_API_KEY`. Or a gateway set through `ANTHROPIC_BASE_URL` (R1:197).
- The setup-token lacks the `user:profile` scope, so `usage().rate_limits` returns null. It is populated only under the interactive credential (R1:91).
- Failures arrive as a *successful* result whose text is the error ("Credit balance is too low", "You've hit your weekly limit"). Detection has to read the text (R1:194-196).
- One subscription's weekly limit killed the whole probe phase (P1:115-135; RB:170-179).
- On macOS the stored credential lives in the Keychain. The research touches this only once: "no macOS keychain here, so … `gh` calls need an explicit token" (env.triage.example:21-22). It never examined `~/.claude.json`, `.credentials.json`, or refresh-token behaviour.
- Codex auth is a file, `~/.codex/auth.json` (env.example:17-18).

**On-disk layout:**
- Sessions: `~/.claude/projects/<encoded-absolute-cwd>/<sid>.jsonl`, plus `<sid>/subagents/agent-<id>.jsonl` and `.meta.json` files holding agentType, description and toolUseId (P2:64-68, P2:83-90).
- The SDK's `dir` argument is the *project cwd*, not the storage path. Passing the storage path returns an empty list with no error (P2:95).
- **Inference:** session lookup is keyed by absolute path. A mirrored `~/.claude` resumes a Mac session in the cloud only if the cloud uses the same absolute path (`/Users/new/...`) or remaps it. The research does not address this.
- `~/.claude/sessions/<pid>.json` is written at start and deleted at exit. It is keyed by pid, so it collides or goes stale across hosts sharing a mirror (P2:201).
- cc-harness adds `~/.claude/ccx/{roster,run}/`. `ccx attach` uses a Unix socket at `~/.claude/ccx/run/<pid>.sock`, so it works only on the same machine (P3:155, P3:215-222).
- Two `ccx serve` processes sharing a `$HOME` overwrite each other's run file; `CCX_FLEET_ROOT` isolates them (P3:490-495).

**Environment variable traps:**
- If the engine's `CLAUDE_CONFIG_DIR` or filesystem differs from its parent process's, the live transcript mirror silently drops frames with only a `warn` (P2:121; R1:112, R1:274-278).
- An inherited `CLAUDE_JOB_DIR` absorbs the session into a parent agent's job row, so it must be scrubbed on spawn (R1:94).
- `DAEMON_HOME` defaults to `~/.claude/sminos`. `DAEMON_HOST` must stay the real hostname (env.example:33-37).

**Plugins, skills, hooks, MCP:**
- Claude Code on the web installs plugins declared in the repo's `.claude/settings.json` at session start. **User-level `~/.claude` does NOT carry over** (MAS:195-200). This is exactly the gap you want to close.
- Managed Agents has no plugins, hooks or slash commands. Custom skills are uploaded to `/workspace/skills/<name>/` (MAS:87-99).
- Cursor runs stdio MCP servers on the worker, which gives them private-network access, and runs HTTP/SSE MCP servers on its backend, which handles their OAuth. Hooks and skills run on the worker or are baked into its image (OI:121-124).
- The single-VM worker host installs plugins "exactly as on the Mac" (WH:99-100).
- Over the appserver, `thread/start` accepts `cwd`, `permissionMode`, `settings` and `mcpServers` as JSON (P3:370-374). Function-valued settings (hooks, sessionStore) cannot cross the wire (P3:467-475).

**Headless-SDK gaps:**
- Only 17 of 30 hook events fire. Never firing: `SessionEnd`, `Notification`, `FileChanged`, `SubagentStart`, `UserPromptExpansion`, `ConfigChange` (R1:152, R1:169-174).
- **`SessionStart` fires at the /compact boundary, not at process start** (R1:164). This matters for SessionStart-based modes such as kairos.
- Impossible headless: `CronCreate`, `PushNotification`, `/goal` (R1:89); converting a running shell to background with Ctrl+B (R1:88).
- OTel exports metrics and logs only, no traces (R1:90).

**Network and sandbox inside a container:**
- Claude Code docs warn that background-agent supervisors inherit proxy env only "when that shell happened to cold-start the supervisor." Node `fetch` below v24 ignores `HTTP_PROXY` (R5:38-48).
- Claude Code reads the OS trust store on Node 22.15+. `NODE_EXTRA_CA_CERTS` is a known trap because it can add to or replace the trusted set (R5:141-143).
- srt (bubblewrap) inside a container needs `enableWeakerNestedSandbox` when it cannot mount `/proc`, which "considerably weakens security" (P4:100-115).

**Warm pools break env-based identity.** A prewarmed pod or VM is created before its session exists, so credentials and config must be delivered when it is claimed, not at boot (R2P:65-68, R2P:335-349; SWS:105-109).

## 4. Egress and transport

- **Outbound-only workers:** each dials the control plane over long-lived HTTPS. No inbound ports, no VPN; adding a host is one command plus a token (CS:165-168; OI:16-17, OI:49-50, OI:190-196). Idle-release grace is 600 s, then exit 0 and a fresh replacement (OI:55-59).
- **Private connectivity menus:**
  - Cursor offers AWS PrivateLink, Cloudflare Tunnel or Tailscale (OI:313-314), and supports Tailscale private networking for cloud agents (AI:43).
  - The worker host runs `tailscale up` and allows inbound only on `tailscale0` (`ufw allow in on tailscale0`), with public SSH closed (WH:36, WH:48-49).
- **The appserver over Tailscale works, with limits:**
  - A WebSocket JSON-RPC handshake succeeded over LAN, Tailscale (`100.92.238.1`) and loopback, but every client ran on the same machine; a foreign host was not proven (P3:15-16, P3:90-94, P3:105-112).
  - The bearer token travels in the first message only, never in the URL. A browser `Origin` header is refused (P3:146-154).
  - There is no TLS (P3:347-351). The token equals arbitrary code execution (P3:370-376).
  - There is no heartbeat; load balancers drop silent connections after 30–60 s (P3:397-409).
  - Parks never expire, and reconnecting replays missed events first (P3:317-341).
- **"Many hands" concept.** A harness calls any "hand" through `execute(name, input)` — a container, an MCP server, "a phone" (MA:43-45, MA:114-126). This is the conceptual route for Mac-only capabilities: the Mac as a remote hand. It is not designed anywhere.
- **Egress control:**
  - The field has converged on a proxy the agent cannot bypass, with transparent iptables REDIRECT (gVisor supports REDIRECT; it does not support TPROXY) (R5:19-59).
  - Injecting credentials at egress requires TLS termination, and cannot serve SigV4 signing or OAuth token-exchange flows (R5:60-71, R5:157-164).
  - Friction turned out to be configuration-shaped; vendors fixed it with runtime policy updates (R5:81-89).
- **Posture:** restrict egress only where durable credentials live. Research-class sessions run open egress (SWS:163-186). Your months of local auto-mode with no incident were recorded as evidence about the model-judgment channel (SWS:503-505, SWS:655-659).
- **Hyperscaler caveat:** compute there carries an ambient credential — the metadata-server service-account token (SA0S:616-620).

## 5. Economics for one person

**Scenario (arithmetic on the reports' list prices, which are stale by policy):** 3 concurrent sessions × 8 h = 24 session-hours/day at 2 vCPU / 4 GiB.

| Substrate | Cost per day | Basis |
|---|---|---|
| E2B | about $4.0 + $150/mo Pro if the Hobby tier's 20 concurrent isn't enough (Hobby price not in reports) | $0.1656/hr (SA0:56-60) |
| Daytona | about $4.0, no plan fee, $200 signup credit | SA0:92-95 |
| Modal | about $5.7 (Team plan $250/mo) | $0.238/hr (SA0:125-129) |
| Northflank | about $1.6 | $0.0667/hr (SA0:147-149) |
| Fly Machines | about $0.7; about $21.5/mo if always on | $0.0295/hr (SA0:170-173) |
| Morph | about $2.4 + $40/mo tier | SA0:214-219 |
| Vercel Sandbox | about $3.6; **24 h max duration** | SA0:232-236 |
| Cloudflare | about $1.7 | SA0:240-245 |
| Runloop | about $7.6 + $250/mo Pro | SA0:200-202 |
| GKE Standard | about $1.1/day, or about $0.64 on Spot (Spot is 40% off) | pod $0.0447/hr (R4:326); one e2-standard-4 node $0.134/hr, Spot $0.0804 (R4:150) |
| GKE Autopilot | about $2.6; a warm pod costs about $79/mo each | $0.0445/vCPU-hr + $0.0049/GiB-hr (R2P:165, R2P:233-237) |
| Cloud Run Jobs | never priced (a research gap) | SA0S:548-565 |
| Own box (Hetzner AX102) | about €4.1 flat | €124/mo for 128 GB + 2×1.92 TB NVMe (SA0:249-254) |
| Managed Agents | about $1.9, but it does not run Claude Code | $0.08 per running session-hour (MAS:170-180) |
| Claude Code on the web | no separate compute charge; draws on subscription usage and daily allowances | 4 vCPU / 16 GB / 30 GB (MAS:192-219) |

- **GKE fixed costs:** the $73/mo cluster fee is covered by the $74.40 free credit (R4:330). The swarm's $445–700/mo fixed floor (control plane, Cloud SQL, ops VM) is fleet machinery a single user does not need (R4:623-625).
- **Hetzner pricing risk:** Hetzner repriced its *cloud* servers by +94–192% on 2026-06-15 (R4:672). The worker host is a Hetzner CX43 VM whose price is not in the reports (WH:23).
- **Crossover:** below 5–8 sustained concurrent sessions, a managed sandbox is cheaper than self-hosting a cluster with that floor. One person sits below this trigger, called FT1 (R4:34-43, R4:616-631, R4:667).
- **Tokens dominate:** interactive Claude Code runs about $13 per developer per active day (vendor-claimed), and an autonomous 12-minute run costs $1–4 on Sonnet (ZO:255-260). On a subscription, tokens are flat. Either way, $1–6/day of infrastructure is small next to them.

## 6. Explicit rejections — which reverse at personal scale

Marked **[SCALE]** when the rejection was scale-driven and likely reverses, **[HOLDS]** when it still applies.

- **[SCALE]** SaaS sandboxes: rejected at about $73–207k/mo for 1k concurrent (R2S:50, R2S:90; SCS:481-483). At one person they cost dollars a day.
- **[SCALE]** Subscription OAuth: banned for fleets as a correlated single point of failure (R1:194; SWS:547-553). For one person it is the natural credential. Caveats: it shares the weekly limit with Mac use, `rate_limits` is null, it is valid about a year, and the blast radius if leaked is the whole subscription.
- **[SCALE]** Claude Code on the web: rejected for lacking a fleet contract (MAS:207-223; SA0S:448-461). For one person it may be viable. Blocker: user-level `~/.claude` is not carried over (MAS:198).
- **[SCALE]** Personal overrides: called "an interactive-IDE feature, a reproducibility leak for an autonomous fleet" (CS:200-204). For you, they are the goal.
- **[SCALE]** The home volume as a "pet" (MA:226-227, MA:315-317), and per-worker ephemeral compute being justified only at scale (MA:228-234). The earlier single-tenant decision said boot cost is invisible at a few workers (MAST:98-101, MAST:133-140).
- **[SCALE, and shape]** Hibernate/resume between messages and conversation plumbing: rejected because our workers were batch-shaped (LL:84). A personal environment is conversation-shaped.
- **[SCALE, and budget]** Modal over budget (SA0:142-143); Runloop 2× over budget (SA0:209-210); Morph's 256-vCPU tier cap (SA0:217-219). None of these bind for one person.
- **[SCALE]** Hetzner self-managed (0.1–0.2 FTE of ops, SA0:255-268) and the bare-metal gate staying closed (SWS:540-545). You already run this box. Reprice risk remains (R4:672).
- **[PARTLY]** Fly: rejected for no egress control, do-it-yourself layers, and 15 h + 11 h management-plane outages in January 2026 (SA0:181-194; SA0S:491-495). Outages still block starting new sessions.
- **[PARTLY]** Firecracker memory snapshots: the clock, entropy and network defects hold regardless of scale (R2S:15-21). The "restore speed is irrelevant" half reverses for interactive use.
- **[HOLDS]**
  - Managed Agents: it does not run Claude Code, and the harness-identity problem does not depend on scale (MAS:357-367).
  - Lambda's 15-minute cap and Vercel's 24-hour cap (R2S:38; SA0:236).
  - Kata without a mandated boundary (R2S:86).
  - The brain-in-cloud split: it would mean reimplementing the harness and paying WAN latency on every tool call (CS:328-332; OI:287-289).
  - Credentials should be unreachable from generated code (MA:76-93; CS:252-276). This directly conflicts with mounting a full personal-home mirror into the sandbox.
- **[GAP]** Cloud Run Jobs was never evaluated: 168-hour timeout, plus the ambient metadata-server credential (SA0S:548-565, SA0S:611-620).

## 7. Dotfiles, home mirroring, "feels like my machine"

- The only real home-persistence design is the state volume with `$HOME` on it, seeded once per volume and never per machine (MAST:77-92; WH:13-19). Plugins are installed "exactly as on the Mac" (WH:99-100).
- Cursor's line: environment setup is "the most important step," and an incomplete environment silently degrades output (AI:43; LL:16-21, LL:62). Their triad is agent-led setup, snapshot, or a Dockerfile in `.cursor/environment.json`. Cursor also invests in "tight harness/client integrations so both agents and humans can inspect and interact with the environment" (LL:20).
- Anthropic's "locality assumption baked in" lesson: when the harness assumes everything is next to it, customers who need to reach their own private resources hit network peering pain (MA:69-71).
- Claude Code on the web carries repo configuration, not user configuration (MAS:195-200).
- Cloud agents are prompted to be more autonomous because blocking costs more when nobody is watching (LL:41).

## What the prior research did NOT cover

1. Claude Code's own on-disk config and credential model: `~/.claude.json`, `.credentials.json` versus the Keychain; whether two machines sharing one OAuth refresh token invalidate each other; which `~/.claude` files are safe to share read-write between Mac and cloud at the same moment.
2. The absolute-path problem for session lookup (`/Users/new` versus a Linux home), and path remapping.
3. Any file-sync or mount technology: Mutagen, Syncthing, JuiceFS, NFS or SSHFS over Tailscale, versioned object stores, ZFS send. Only Postgres, S3 and Redis session stores were considered.
4. Mac-only capabilities (Keychain, GUI through cua, Xcode, local apps) reached from the cloud — the reverse path, with the Mac as a "hand."
5. Interactive attach (ssh, mosh, tmux, web terminal) latency and ergonomics. All prior work was batch-shaped.
6. Stock interactive `claude` running in a container, as opposed to the cc-harness SDK. Also Linux binary size and memory under gVisor or a microVM.
7. Idle persistence cost: paused VMs, volumes, E2B paused storage (unpublished).
8. A security model for a sandbox holding a person's entire identity — the opposite of the credential doctrine.
9. Terms-of-service posture for running a personal subscription headless in the cloud (explicitly bracketed at R2P:332).
10. Whether Claude Code's own cloud offering can move sessions between local and cloud.
11. Cloud Run Jobs pricing.
12. Portability of this repo's macOS-assuming hooks, mods and MCP servers (kairos, cua) to Linux.
