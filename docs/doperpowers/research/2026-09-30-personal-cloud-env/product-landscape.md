# Personal cloud dev environments for coding agents: 2026 landscape survey

Subagent report, researched 2026-09-30, for the personal-cloud-environment design question
(see `../../2026-09-30-personal-cloud-env-research.md`). Sources are primary vendor docs unless
marked (3P) for third-party or (vendor-claim) for unaudited marketing claims. [UNVERIFIED] means
it could not be confirmed. Figures marked "my arithmetic" are the researcher's own calculations.

---

## 1. Fly.io Sprites (the closest match)

Sources: https://fly.io/sprites · https://docs.fly.io/llms.txt · https://fly.io/blog/design-and-implementation/ (Jan 2026) · https://fly.io/blog/code-and-let-live/ · https://fly.io/blog/kurt-scott-money-sprites/ (Jul 24 2026)

**(a) Isolation.** Each Sprite is a Fly Machine, a KVM microVM (press says Firecracker; Fly's design post does not name it). User code runs in an inner container; the storage stack, service manager, logs and port exposure run in the VM's root namespace, so Fly can "bounce a Sprite without rebooting the whole VM, even on checkpoint restores." No user images: every Sprite boots from one standard Ubuntu image with the Claude, Codex, Gemini and Cursor CLIs preinstalled; pre-warmed pools make create 1–2 s. Resources are fixed: 8 vCPU, 100 GB disk, platform-managed memory; none resizable (docs.fly.io/sprites/concepts/lifecycle.md).

**(b) Persistence** (lifecycle.md). "Disk persists, memory does not." Warm: ~30 s after activity stops the VM is suspended with memory frozen; wake 100–500 ms. Cold: after a longer idle the VM is stopped and memory dropped; wake 1–2 s, processes start fresh. "Open TCP connections do not survive a pause, warm or cold." Services (`sprite-env services create`) restart after a cold wake; hand-started processes, TTYs and `sprite exec` sessions do not. Host failure: durable state "is simply a URL" in object storage. Counter-evidence: users reported Sprites reset to empty with data and checkpoints gone on 2026-03-17, no staff reply (https://community.fly.io/t/sprite-reset-to-a-new-empty-instance-can-fly-restore-original-storage-checkpoints/27377); a sibling thread "Sprite file system corrupted?".

**(c) Checkpoint, restore, fork** (docs.fly.io/sprites/concepts/checkpoints.md). A checkpoint captures the whole writable overlay as a copy-on-write snapshot, not processes or memory. Create latency reported as ~300 ms (Willison, https://simonwillison.net/2026/Jan/9/sprites-dev/), "about one second" (product page), "roughly 10–30 seconds" (docs). Restore is asynchronous, replaces the whole filesystem, restarts the environment, kills sessions, and does not back up the state it replaces. The last 5 checkpoints are mounted read-only at `/.sprite/checkpoints/vN`. Automatic checkpoints are taken after sustained work, on idle and on graceful shutdown; older ones pruned. No GA fork into a new Sprite; the July 2026 "nu-Sprites" post announces drive forking behind a beta signup.

**(d) Config and secrets in.** No dotfiles or settings-sync feature; install once and it persists. Credentials go through **Connectors**, a gateway that brokers auth to GitHub, Slack or any HTTP API "without the credential ever entering the Sprite." SSH keys are piped in with `sprite exec`. No general env or secrets store found [UNVERIFIED absence].

**(e) Reaching your machine or network** (docs.fly.io/sprites/concepts/networking/). Inbound: an HTTPS URL per Sprite (private by default; an inbound request wakes it), `sprite proxy` (remote port to laptop), SSH via `sprite proxy -W :22`. Egress open by default; an optional DNS allowlist policy, and "private IP ranges are always blocked" once a policy is in force. Tailscale works in kernel mode only while no policy is set; any domain rule blocks UDP and breaks it (https://community.fly.io/t/using-tailscale-with-sprites/26867). tailscaled goes one-way and stale after a pause and must be restarted; MagicDNS fails because `/etc/resolv.conf` is read-only; one user switched to an SSH ProxyJump through an always-on VPS (https://madflex.de/sprite-tailscale-forgejo/, Aug 2026).

**(f) Storage technology.** v1 (Jan 2026): "a very hacked-up JuiceFS" — chunks in S3-compatible object storage, SQLite metadata made durable by Litestream, a sparse 100 GB NVMe read-through cache. v2 "Sprite Block Device" (Jul 2026): ext4 on an object-storage-backed block device, "faster, more reliable"; the product page lists an "S3 Block Device" as early access. The filesystem "syncs continuously, not as a snapshot taken at hibernation."

**(g) Pricing** (fly.io/sprites). CPU $0.07 per CPU-hour (actual usage via cpu.stat); memory $0.04375 per GB-hour of actual usage; storage hot $0.000683/GB-h (≈$0.50/GB-mo), cold $0.000027/GB-h (≈$0.02/GB-mo); written blocks only, TRIM-aware, checkpoints count. Warm and cold states have no compute charge. Pay-as-you-go, 10 creates per minute; Hero $100/mo with allowances; $30 trial credit; egress not metered. Fly's example: a 4-hour Claude Code session costs $0.44.

**Keep-alive caveat** (docs.fly.io/sprites/keeping-sprites-running.md). Outbound websockets and long-polls do **not** keep a Sprite awake; only inbound requests, console/exec activity, or a live **Task** do. Tasks last at most 1 hour and must be refreshed (5-minute expiry, refreshed every 60 s). "A forgotten heartbeat loop keeps the Sprite billing." Company context: in Jul 2026 Fly made Sprites "the focus of our company" and changed CEO.

---

## 2. Anthropic Claude Code

Sources: https://code.claude.com/docs/en/claude-code-on-the-web · /cloud-environments · /settings ("Settings in cloud sessions") · /skills · /remote-control · /self-hosted-environments

**(a) Isolation.** Each cloud session gets a fresh Anthropic-managed VM: Ubuntu 24.04 x86_64, ~4 vCPU, 16 GB RAM, 30 GB disk. Self-hosted environments run each session as a child Claude Code process on your own host, isolation your responsibility; public beta for **Team and Enterprise only**.

**(b) Persistence.** An idle session's VM is reclaimed ("Environment expired"); reopening provisions a fresh VM with the conversation restored, but running subagents and shell commands are lost. Packages installed mid-session don't carry to other sessions. The pushed branch is the durable artifact; Anthropic stores the transcript.

**(c) Checkpoint, restore, handoff.** Anthropic "snapshots the filesystem" after setup only if setup finishes in ~5 minutes; the snapshot expires after ~7 days and is rebuilt when the script or network hosts change. No user-facing snapshot or fork. `claude --cloud "task"` (`--remote` deprecated alias) starts a new session: clones the remote branch, or uploads a git bundle under 100 MB including uncommitted tracked changes but excluding credential-like files. `claude --teleport` and `/teleport` pull a session's conversation and branch into the terminal; from the CLI this is one-way; the Desktop app's "Continue in" can push a local session to the cloud. `claude -p "msg" --cloud <id>` queues a follow-up.

**(d) Config in.** Only what is committed to the repo reaches a cloud session. Carried: repo CLAUDE.md, `.claude/settings.json` (single-repo sessions), `.mcp.json`, `.claude/{skills,agents,commands,rules}`. **Not carried:** `~/.claude/CLAUDE.md`, `~/.claude/skills|agents|commands`, user-scope plugins, user-scope MCP servers, user-level hooks; plugins declared in the repo also don't install. The one sync channel is skills enabled on your claude.ai account (download-only into `~/.claude/skills/synced/`, ~every 10 minutes, v2.1.273+). Environment variables: `.env` format, readable by anyone using the environment. API credentials (Pro/Max): the agent proxy attaches the key after requests leave the VM, so the key "never reaches Claude." GitHub: server-side proxy, credentials never enter the VM.

**(e) Reaching your machine.** Anthropic-hosted sessions only offer network access levels (None, Trusted, custom allowlist); no VPN or Tailscale option found [UNVERIFIED absence]. Self-hosted runners poll `api.anthropic.com` outbound only. **Remote Control is the inverse pattern:** the session runs on your machine, "makes outbound HTTPS requests only and never opens inbound ports," driven from claude.ai or the phone app. Server mode `claude remote-control` supports `--spawn worktree` and `--capacity` (default 32). Pro, Max, Team, Enterprise. **Unavailable when `ANTHROPIC_BASE_URL` points to an LLM gateway.** In server mode it exits after ~10 minutes without network.

**(f)** Storage not disclosed. **(g)** "No separate compute charge for the cloud VM"; usage shares the subscription's rate limits.

---

## 3. OpenAI Codex cloud, plus Remote and "dots"

Sources: https://learn.chatgpt.com/docs/environments/cloud-environments · /cloud-environment (legacy)

**(a)** Each task runs in its own VM: 2 vCPU / 8 GiB / 8 GiB disk on Plus; 4 vCPU / 16 GiB / 32 GiB on Pro, Business, Enterprise. Legacy used containers from `codex-universal`.
**(b)** An existing task "continues with its own saved files, including uncommitted changes and installed tools," recoverable for up to 7 days after the last turn. A new task starts from the published environment's filesystem.
**(c)** "Publishing captures the prepared filesystem." No user fork. Legacy container cache lasted up to 12 hours; users reported it not working (openai/codex #6604, #25086).
**(d)** A per-user "personal vault" of secrets scoped to environments. "Network secrets": the program sees a placeholder and the proxy substitutes the real value (HTTPS 443 only). Repo skills and AGENTS.md apply. "Personal skills from your local computer aren't synced."
**(e)** "Tailscale is currently the supported VPN provider" (reusable ephemeral key, IPv4-only, no private DNS/SSH/native DB protocols). **Codex Remote** (https://learn.chatgpt.com/docs/remote-connections): phone drives a macOS/Windows desktop-app host through a relay; the desktop app drives SSH "devbox" hosts; "handoff to a Codex cloud environment isn't supported." **Work Cloud and dots** (dots launched 2026-09-29; https://learn.chatgpt.com/docs/enterprise/cloud-local-access): coordination in the cloud, tools execute on your computer through the ChatGPT desktop app as the "local executor"; a dot has its own persistent cloud computer, local access opt-in.
**(f)** Not disclosed. **(g)** Included in ChatGPT plans; no compute price published.

---

## 4. Sandbox APIs

**Modal Sandboxes** (https://modal.com/docs/guide/sandbox-snapshots, https://modal.com/pricing). gVisor containers. State dies with the sandbox unless snapshotted; Volumes $0.09/GiB-month. Filesystem snapshots stored as a diff against the base image, become Images, can fork many sandboxes; default TTL now 30 days (was indefinite). Directory snapshots mountable into a running sandbox. Memory snapshots alpha: hard 7-day expiry, "snapshotting a Sandbox will currently cause it to terminate," TCP closed, restore needs the same instance type. No API to list snapshots. $0.00003942 per physical core-second, $0.00000667 per GiB-second; Starter $0 with $30/month credit.

**E2B** (https://docs.e2b.dev/sandbox/persistence, https://github.com/e2b-dev/runtime, https://e2b.dev/pricing). Forked Firecracker, one microVM per sandbox. Pause saves memory and filesystem, "kept indefinitely… no TTL"; auto-pause opt-in. Continuous running limited to 1 h Hobby / 24 h Pro, reset on resume. Pause ~4 s per GiB RAM; resume ~1 s; one-to-many forks. Templates, env vars; volumes private beta. "Pause diffs memory and disk against the template and ships the diff to object storage." $0.000014 per vCPU-second, $0.0000045 per GiB-second; storage included (10 GiB Hobby, 20 GiB Pro); Pro $150/month; paused-sandbox cost not stated.

**Daytona** (https://www.daytona.io/docs/en/persistence/, https://www.daytona.io/pricing). Containers (Sysbox default per 3P; Kata optional), plus Linux/Windows VM and GPU classes. Persistent by default: containers stop keeps filesystem, auto-stop after 15 min, auto-archive to object storage after 7 days; VMs pause keeps memory, auto-pause 60 min. Cold snapshots (filesystem) and hot snapshots (fs + memory, VM only); `fork()` VM-only. Volumes are "S3-backed mounts." $0.0504/vCPU-hour, $0.0162/GiB-hour, $0.000108/GiB-hour storage (≈$0.08/GiB-month) after 5 GiB free; $200 credit.

**Morph Cloud** (https://cloud.morph.so/docs/developers). Snapshot, branch and restore of the whole running VM including processes in under 250 ms. Devboxes can disable auto-sleep and TTL to act like a VPS; SSH and `expose-http`. Pricing 3P only [UNVERIFIED]: $0.05 per MCU (1 vCPU-hour + 4 GB RAM-hour + 16 GB disk-hour).

**CodeSandbox SDK / Together Code Sandbox** (https://codesandbox.io/blog/how-we-scale-our-microvm-infrastructure-using-low-latency-memory-decompression; SDK docs 403, rest 3P). Firecracker; hibernate takes a memory snapshot. Resume 0.5–2 s from memory snapshot, 5–20 s from disk snapshot, 20–60 s once archived after 7 idle days; fork of a live VM 1–3 s. $0.01486 per credit; Nano VM (2 cores, 4 GB) $0.1486/hour.

**Vercel Sandbox** (https://vercel.com/docs/sandbox, /concepts/persistent-sandboxes, /pricing). Firecracker. **Persistent is now the default**: stopping auto-snapshots the filesystem; resume boots a new session from it, no memory. Sessions capped at 24 hours, sandbox lifetime unbounded; sandboxes that cannot resume are removed after 14 days. Snapshots expire 30 days after last use (configurable, including never); `keepLastSnapshots` 1–10; rollback via `currentSnapshotId`; Drives (beta) are persistent mounts. Secure Compute: static IPs, VPC peering; privileged processes allow VPN clients. Active CPU $0.128/hour, memory $0.0212/GB-hour, snapshots $0.08/GB-month, drives $0.05/GB-month.

**Cloudflare Sandbox / Containers** (https://developers.cloudflare.com/sandbox/concepts/lifetime/, /containers/platform/pricing/). A microVM per instance fronted by a Worker and Durable Object. Disk and memory gone on stop. "Code that runs inside the instance does not count as activity"; inactivity timeout up to 6 hours. `snapshotContainer()` captures the writable root only, expires after 30 days, beta; R2 mount is the only durable disk. Credentials stay in the Worker. Workers Paid $5/month, then $0.000020 per active vCPU-second, $0.0000025 per GiB-second, $0.00000007 per GB-second; zero while asleep.

**Runloop** (https://docs.runloop.ai/docs/devboxes/lifecycle). Disk deleted on shutdown by default; suspend snapshots disk not memory, keeps ID and SSH keys; idle suspend available; default lifetime 1 hour; disk snapshots persist indefinitely. $0.108/CPU-hour, $0.0252/GB-hour, $0.20/GB-month; suspend requires the $250/month Pro plan (3P).

**Blaxel** (vendor-claim, https://blaxel.ai/sandbox). Firecracker fork; standby after ~15 s network inactivity keeps memory and filesystem indefinitely; resume ~25 ms. Volumes $0.12/GB-month, snapshots $0.20/GB-month.

**Northflank** (vendor-claim, https://northflank.com/product/sandboxes). Kata with Cloud Hypervisor (Firecracker or gVisor per workload). Persistent volumes 4 GB–64 TB, no session time limit. $0.01667/vCPU-hour, $0.00833/GB-hour, $0.15/GB-month; BYOC.

---

## 5. Classic cloud dev environments

**Coder** (https://coder.com/docs/admin/templates/extending-templates/resource-persistence). Whatever your Terraform template provisions. Canonical pattern: ephemeral compute (`count = start_count`) with a persistent `/home/coder` volume; name the volume by the immutable `owner_id` — naming by username means "Terraform will recreate the volume (wiping its data!)" when the username changes. `coder dotfiles <repo>` (Codespaces-compatible), the dotfiles module, a `~/personalize` script. A WireGuard tailnet built on Tailscale's implementation (DERP + STUN); Coder Desktop's "Coder Connect" makes workspaces reachable at `<name>.coder`. Coder Tasks runs Claude Code in its own workspace. Self-hosted OSS; you pay your own cloud.

**Ona (formerly Gitpod)** (https://ona.com/docs/ona/environments/persistent-storage). A VM per environment running a Dev Container; the attached disk persists `/workspaces`, `/home/gitpod` and system packages across stop/start; Core plan auto-deletes after 7 inactive days. Ona recommends a fresh environment per task for agents. Dotfiles repo applies to new environments only; user secrets reach running environments within 2 minutes. Core from $20/month; ~$0.23/hour for 4 vCPU / 16 GB (Sep-2025 figure).

**GitHub Codespaces** (https://docs.github.com/en/codespaces/about-codespaces/deep-dive). Dedicated VM + dev container. Stop/start keeps the whole container; rebuild keeps only `/workspaces`; idle timeout 30 min default; auto-delete 30 days after stopping. Anthropic's docs note `~/.claude` survives stop/start but is cleared on rebuild. Dotfiles repo, VS Code Settings Sync, user secrets as env vars. $0.09 per core-hour, $0.07 per GiB-month billed while stopped.

**DevPod.** Client-only, provider-agnostic, `--dotfiles`; upstream loft-sh/devpod no commits since Nov 2025; active fork skevetter/devpod (loft-sh/devpod #1946).

**Google Cloud Workstations** (https://docs.cloud.google.com/workstations/docs/architecture). Ephemeral GCE VM; persistent disk mounted at `/home` at session start, detached at end; reclaim DELETE by default or RETAIN; archive timeout converts the disk to a snapshot; idle timeout 2 h, running timeout 12 h. GCE rates + $0.05 per vCPU-hour management fee + PD (≈$0.10/GB-month).

**Nix / Devbox / chezmoi.** `devbox global push/pull` git-syncs `devbox.json` + `shellenv`. Standalone home-manager: `nix run home-manager -- switch --flake github:you/dotfiles#host`. chezmoi (optionally age-encrypted) is the common way to sync `~/.claude` (https://www.arun.blog/sync-claude-code-with-chezmoi-and-age/). Claude Code devcontainer docs (https://code.claude.com/docs/en/devcontainer): `~/.claude.json` sits outside `~/.claude`, so mount a volume and set `CLAUDE_CONFIG_DIR` to the same path; `~/.claude/projects` is keyed by absolute path; keep `.credentials.json`, `sessions` and `history` local to each machine.

---

## Cross-cutting 1: which products treat the machine or home directory as the persistent unit?

**Whole machine as identity** (one persistent machine per unit, not per repo): Sprites; E2B pause and Blaxel standby; Daytona; Vercel persistent sandboxes; Morph and CodeSandbox; Runloop suspend; Codespaces between stop and start.

**Home directory as identity, compute disposable** (the classic pattern): Google Cloud Workstations (`/home` disk), Coder (`/home/coder` volume), Ona (disk attached to the VM), Codespaces `/workspaces` across rebuilds. In all of these the home is per-workspace, not shared across a user's workspaces.

**Per-repo environment spec plus a setup snapshot, no personal state:** Claude Code cloud sessions, Codex cloud, Cursor Cloud Agents (https://cursor.com/docs/cloud-agent/builds). Personal layers arrive only through narrow channels: claude.ai skill sync, Codex's personal vault, dotfiles repos. OpenAI dots and Codex existing tasks keep per-agent or per-task machines, but they are not user-shaped homes.

**How persistence is implemented:** block volume attached to a VM (Workstations, Coder, Codespaces, Ona, Northflank); object storage behind a local NVMe cache (Sprites, E2B diffs, Daytona archive/volumes); snapshot/restore of the whole machine (E2B, Blaxel, Morph, CodeSandbox, Vercel, Runloop, the setup caches of Claude, Codex, Cursor).

**No product offers one persistent home shared across N concurrent disposable session machines.** Vercel Drives, E2B/Modal/Daytona volumes and Cloudflare R2 mounts are the closest building blocks.

## Cross-cutting 2: letting a cloud agent do things only the physical machine can

The dominant 2026 pattern is "cloud brain, local hands": a worker on the machine opens a long-lived *outbound* connection and receives tool calls over it, no inbound ports.
- **Cursor "My Machines"** (https://cursor.com/docs/cloud-agent/self-hosted/my-machines): `agent worker start` runs terminal, file, browser and computer-use tools locally, plus stdio MCP servers reaching local and private services; on macOS it installs a Computer Use helper needing Accessibility and Screen Recording grants.
- **OpenAI Work Cloud and dots:** the ChatGPT desktop app is the "local executor."
- **Codex Remote:** phone to desktop host through a relay, or desktop to SSH devbox.
- **Claude Code Remote Control:** the *whole session* runs locally and the phone or web only drives it, over outbound HTTPS polling.
- Claude Code has no documented way for an Anthropic-hosted cloud session to delegate tool calls to your Mac (the "remote tool serving" path exists in the binary behind feature flags; see `claude-code-host-state.md` §D.4).
- An inferred, untested workaround: a remote-HTTP MCP server on the Mac, exposed over Tailscale or a tunnel.
- **TCC-gated resources** (Keychain, Screen Recording, Accessibility) can only be reached by a local process the user approved, so a network tunnel alone can't provide them; the local executor has to be a user-approved app.

## Cross-cutting 3: failure modes practitioners report

- **Durability of object-store-backed VMs:** the Sprites resets and corruption reports (Mar 2026), after which Fly rebuilt the storage stack as SBD.
- **Compute and storage bound together:** "every hard failure came from that binding"; after image drift, re-creating the sandbox lost its state; the fix was a Drive with the sandbox disposable (https://github.com/dennisofficial/atlas/pull/792, Sep 2026).
- **Suspend breaks network state:** TCP drops on every pause (Sprites, E2B, Modal); Tailscale inside a Sprite goes stale after a pause.
- **Idle semantics catch people out, both directions:** Sprites that didn't pause caused cost anxiety (https://news.ycombinator.com/item?id=46634450); Cloudflare doesn't count in-container work as activity; outbound long-polls don't keep a Sprite awake; closing a Codespaces tab doesn't stop it.
- **Retention reapers delete work:** Codespaces after 30 days stopped; Ona Core after 7 inactive days; Vercel after 14 days once snapshots expired; Modal fs snapshots 30-day TTL, memory snapshots 7 days; Codex tasks 7 days; Claude Code cloud VMs on idle (background work lost).
- **Snapshot sprawl and bloat:** snapshots outlive the sandbox and keep billing (Vercel, Daytona); Runloop snapshots and E2B paused sandboxes never expire; Modal has no API to list snapshots.
- **Secrets sprawl:** tokens baked into snapshots (an `.npmrc` token in a Cursor snapshot, https://infisical.com/blog/secure-secrets-management-for-cursor-cloud-agents); Codex setup-only secrets copied to disk; Claude environment variables readable by every user of the environment; Ona env-var secrets leak through `ps`. Industry response: proxy-side credential brokering (Sprites Connectors, Claude API credentials, Codex network secrets).
- **Drift:** persistent environments drift into works-on-my-machine (https://blog.jetbrains.com/codecanvas/2024/12/from-vdi-to-cdes-solving-remote-development-challenges/); dotfiles repos apply only to *new* environments (Ona, Codespaces).
- **Setup caches that silently don't cache:** Codex #6604, #25086; Claude's cache skipped if setup exceeds ~5 minutes.
- **Idle disk cost** is small for one user: $0.02–$0.50/GB-month (Sprites), $0.07 (Codespaces), ~$0.10 (GCP PD), $0.20 (Runloop). The bigger idle risk is something keeping compute awake: heartbeats, polling, VPN daemons.

## What this implies for a single-developer personal cloud environment

The market splits into whole-machine persistence (one Sprite/E2B box/Vercel sandbox/Codespace per unit) and per-repo specs (Anthropic, OpenAI, Cursor clouds, which by design never carry `~/.claude`). Nobody sells one persistent personal identity behind several disposable session machines; it has to be composed:
- **Identity layer:** a durable store you own (git/chezmoi or Nix/Devbox for config and toolchain; object storage or a drive for state).
- **Session layer:** cheap boxes that mount or pull the identity layer at boot. Sprites give the best single-user economics (~$0.11 per active session-hour, pennies idle) but poor Tailscale and keep-alive semantics.
- **Anthropic-hosted cloud sessions can't be the substrate for personal-computer semantics.** User settings, plugins and MCP never sync; only claude.ai skills do. You need to run Claude Code yourself on the machine.
- **Session logs must live outside any rewindable filesystem.** A Sprite checkpoint restore or a Vercel snapshot rollback rewinds `~/.claude/projects` along with the code.
- **Budget the keep-alive cost of remote steering.** A Remote Control server inside a Sprite needs a Task heartbeat, which bills continuously. Remote Control also refuses to run when `ANTHROPIC_BASE_URL` points at a gateway.
- **For Mac-only work (GUI, Keychain, TCC),** the proven pattern is an outbound-connecting local executor holding the TCC grants (Cursor My Machines, the ChatGPT desktop executor). For Claude Code today, the equivalent is running that session on the Mac. Tunnelling from the cloud does not reach TCC-gated resources.

## Could not verify

The Firecracker basis of Sprites and Morph; Morph and CodeSandbox pricing (3P only); the cost of a paused E2B sandbox; a secrets or env store on Sprites; a VPN option for Claude Code cloud sessions; how Codex cloud is priced; whether an outbound connection keeps a Sprite warm; Blaxel and Northflank figures are vendor-published only.
