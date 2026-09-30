# A personal agent environment in the cloud that mirrors your own computer — research synthesis

**Date.** 2026-09-30. **Status.** Research complete; design settled at the level below; first
implementation unit pending one decision (where the session host lives, §7).

**The question.** A person runs coding-agent sessions (Claude Code) on their own computer. When a
session runs in the cloud instead — one process per session or per project — it stops being
*theirs*: the global config under `~/.claude` is missing, credentials and tools are missing, the
things only their machine can do are out of reach, and nothing persists between sessions. How can a
person maintain an agent environment in the cloud that functions like a mirror of their own
computer: persistent like a personal computer, always on so sessions outlive a closed laptop, and
with each session still a disposable unit of compute?

This document answers the general question first (§1–§5) and then applies it to the setup that
prompted it (§6–§8). Full reports are under `research/2026-09-30-personal-cloud-env/`:

| Report | What it holds |
|---|---|
| `prior-research-digest.md` | The 2026-07 swarm/cloud-scale research re-read for one person: which verdicts hold, which were scale-driven and reverse |
| `claude-code-host-state.md` | Source-level inventory (Claude Code 2.1.283) of every piece of host state the CLI depends on, and every remote/cloud mechanism already in the binary |
| `product-landscape.md` | 2026 survey: Sprites, Claude Code cloud/Remote Control/self-hosted runners, Codex cloud, sandbox APIs, Coder/Ona/Codespaces/Workstations |
| `storage-mirror.md` | Sync and storage options (Mutagen, Syncthing, NFS, JuiceFS, block volumes, ZFS, git) with measured sizes and growth of this `~/.claude` |

---

## 1. The problem, defined correctly

"Mirror my computer" is the wrong unit. A personal computer, as an agent environment, is a bundle of
seven things that differ in who writes them, how big they are, and whether they can leave the
machine at all:

| # | Class | Examples | Writer pattern | Can it leave the machine? |
|---|---|---|---|---|
| 1 | Authored config | `CLAUDE.md`, `settings.json`, skills, agents, hooks, keybindings, dotfiles | small, textual, edited on any machine, mergeable | yes, by git |
| 2 | Accumulated state | session transcripts, memory, plans, tasks, file-history | large, append-mostly, **one writer per file**, UUID-named | yes, by file sync |
| 3 | Shared logs | `history.jsonl` | many writers, one file | no (host-local; union-merge if wanted) |
| 4 | Rebuildable caches | plugin cache, `node_modules`, jobs scratch | regenerable from a manifest | no need |
| 5 | Machine-local runtime | pid registries, sockets, `~/.claude.json`, tailscaled state | one host only; corrupts when shared | never |
| 6 | Credentials | OAuth refresh tokens, Keychain items, PATs, ssh keys | refresh races when copied; Keychain not on disk | only by brokering |
| 7 | Device-bound capabilities | GUI automation, a logged-in browser profile, Keychain, TCC grants, Xcode, local hardware | bound to a user-approved process on that device | never; reached remotely |

Two more properties define the target: **continuity** (sessions keep running when the laptop
closes) and **elastic compute** (as many sessions as the work needs, not as many as one box's RAM
allows). Every failed "cloud mirror" copies the machine instead of decomposing this table.

## 2. Principles

**P1. Decompose by state class; give each class its own mechanism and its own source of truth.**
Git for class 1 (with structural merge for JSON so two-sided edits never leave conflict markers).
File sync for class 2, with a conflict policy that only ever renames the loser. Host-local for
classes 3–5. Brokering for class 6. Remote hands for class 7. One mechanism for everything is the
mistake every vendor and every home-grown mirror makes.

**P2. Path identity.** Agent harnesses bake absolute paths into their state. In Claude Code the
session store is keyed by the working directory's absolute path (`projects/-Users-new-…`),
transcripts and file-history carry absolute `cwd` and tracking paths, plugin registries hold
absolute install paths, trust and local MCP are keyed by project path. State is portable only if
every host presents the **same absolute paths**: same username, same home path, same repository
roots. On Linux this means deliberately creating `/Users/<name>` with the same uid, not
`/home/<name>`.

**P3. One pet, N cattle — applied to the person, not the fleet.** The July research's doctrine was
"the durable log is the identity of the work; compute is disposable." At personal scale the durable
identity is the *person's home*, and exactly one always-on machine holds it: the **hub**. It is where
the union of state lands, where snapshots and backups run, where credentials are brokered from, and
where device-bound capabilities live if it is a real personal machine. Every other machine —
laptop, cloud VM, sandbox — is a **session host**: disposable compute that pulls the identity at
boot and pushes its state back. The hub may be a home machine (this case) or a cloud VM with a
volume (when there is no home machine); the architecture is the same.

**P4. Cut at the seams the harness already offers; do not cut where it does not.** The tempting cut
is "agent process in the cloud, tools executed on my computer" (brain/hands split). For Claude Code
that seam does not exist for built-in tools (Bash, Read, Edit, Write, Glob, Grep run in-process; a
flag-gated "remote tool serving" path exists in the binary but is not shipped), and re-creating it
means rewriting the harness and paying WAN latency per tool call. The seams that do exist:
- **UI/control seam** — the process runs on the always-on host; you attach from anywhere (tmux +
  mosh/ssh over a tailnet; `claude --bg` + attach; Remote Control when its preconditions hold).
- **Capability seam** — MCP. A stdio MCP server that only works on one device becomes a "remote
  hand" by launching it over SSH (`ssh device node …/server.mjs`); an HTTP MCP server is reached
  over the tailnet. This is the "many hands" idea from Anthropic's Managed Agents, achieved with zero
  harness changes.
- **Session mobility seam** — resume needs only the transcript file present at the same path;
  `--fork-session` on cross-host resume keeps one writer per file. `claude --teleport` pulls
  Anthropic-hosted cloud sessions into a local host.
- **Config seam** — the settings cascade, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_PLUGIN_SEED_DIR`, plugin
  registries that re-base on load (2.1.283+).
- **Credential seam** — `ANTHROPIC_BASE_URL` to a gateway that holds the credential, `apiKeyHelper`,
  `claude setup-token`, per-host logins.
What Anthropic's own cloud does not offer: forwarding user-level `~/.claude` into cloud sessions
(the "home seed" producer is a stub in 2.1.283; only claude.ai-enabled skills sync, downward).

**P5. Isolation follows trust, not architecture.** A personal environment is one trust domain. A
container or microVM per session is for running untrusted code; it is not what makes sessions
"units." Sessions on one host share the kernel, page cache and unix sockets — which is exactly what
lets them message each other (`ListAgents`/`SendMessage`, the seat registry's inbox sockets) the way
processes on one computer do. MicroVMs break that. Separation that matters between sessions is at
the working tree (a worktree per session), not the kernel.

**P6. Guardrails come from real failure modes, and each maps to one.** See §5.

## 3. Reference architecture

```
                 tailnet (Tailscale): every box, no inbound ports, MagicDNS names
   ┌──────────────┐        ┌──────────────────────────────┐        ┌──────────────────────┐
   │  laptop(s)   │ ◄────► │  HUB: always-on personal      │ ◄────► │  session host(s) 0..N │
   │  = peer or   │        │  computer                     │        │  (cloud VM / home box │
   │    client    │        │  • home = identity             │        │   / sandbox), Linux   │
   └──────────────┘        │  • credential broker (gateway) │        │  • same absolute paths│
                           │  • device-bound capabilities   │        │  • config from git    │
                           │  • archive of record + backups │        │  • Mac tools via SSH  │
                           └──────────────────────────────┘        └──────────────────────┘
   class 1 config     : git, structural merge ─────────── every host
   class 2 sessions   : file sync, star topology, hub = union ── every host ⇄ hub
   class 6 credentials: hub-held gateway / per-host login ── never copied
   class 7 capabilities: stdio MCP over SSH to the device that has them
   repos              : git; per-session worktrees; WIP on wip/<host> branches
```

**Variants.**
- *Hub = home machine* (this case): zero mirror for the hub itself; Mac-native capabilities; the
  weakness is home power and ISP, mitigated by a cloud session host that doubles as the standby.
- *Hub = cloud VM with a volume* (no always-on home machine): the July `infra/worker-host` shape
  (body/soul/seeding) with the "soul" being the person's home instead of a bot's; laptop syncs to
  it; device-bound capabilities stay on the laptop and are unavailable when it sleeps. About
  €12/month for a small ARM VM with a 100 GB volume and offsite copy (`storage-mirror.md` §5).
- *Hub-less* (a SaaS sandbox per session + an object store): the weakest; every vendor's persistence
  is per-machine, none shares one home across N concurrent machines, and checkpoint restores rewind
  the session store with the code (`product-landscape.md`, cross-cutting §1 and §3).

## 4. What the market offers, and why none of it is this (2026-09)

- **Whole-machine persistence products** (Fly Sprites, E2B pause, Vercel persistent sandboxes,
  Daytona, Morph, CodeSandbox, Runloop, Codespaces) persist *one machine*. Cheap per session-hour
  (Sprites ≈ $0.11 active, cents idle) but: TCP and VPN state die on every pause, Tailscale breaks
  under egress policies, keep-alive semantics bill or sleep unexpectedly, retention reapers delete
  work, and there were data-loss reports (Sprites, 2026-03).
- **Per-repo environment products** (Claude Code cloud sessions, Codex cloud, Cursor cloud agents)
  by design carry repository config and never `~/.claude`. Claude Code cloud VMs are 4 vCPU / 16 GB /
  30 GB, reclaimed on idle, with only claude.ai-enabled skills synced down.
- **Anthropic's answer to "my own always-on machine, driven from anywhere" is Remote Control**
  (Pro/Max/Team/Enterprise): the session runs on your machine, phone/web drive it, server mode
  creates sessions on demand (`--spawn worktree`, `--capacity 32`, a device card on the phone since
  Week 34). It refuses to run when `ANTHROPIC_BASE_URL` points at an LLM gateway.
- **Self-hosted environments** (Team/Enterprise public beta since 2.1.224) run cloud sessions on
  your runner with a snapshot of the operator's `~/.claude` minus an exclusion list; each session
  gets its own config dir; inference cannot go through a gateway; pool sessions never sync files.
  The exclusion list (`claude-code-host-state.md` §D.6) is the best published statement of which
  state should travel and which should not.
- **The "local executor" pattern** (Cursor My Machines, ChatGPT desktop as executor for Work Cloud
  "dots", Codex Remote) is the industry's answer to device-bound capabilities: a user-approved
  process on the device holds the TCC grants and receives tool calls over an outbound connection.
  Claude Code has the inverse (Remote Control) and MCP; the flag-gated remote tool serving would be
  the same pattern.

## 5. Guardrails, each from an observed failure

1. **Retention sweeps propagate through sync.** `cleanupPeriodDays` defaults to 30; on this laptop
   the oldest transcript is exactly 30 days old — history is already being deleted daily. Set it
   explicitly on every host *before* the first sync, or one host's sweep deletes everywhere.
2. **One writer per file.** Cross-host resume is `claude --resume <id> --fork-session`. Sync
   conflict policy renames, never overwrites (Mutagen `two-way-safe`, never `two-way-resolved`).
3. **Never sync** `sessions/` (a launch clears "crash leftovers"), `history.jsonl` (multi-writer),
   `~/.claude.json` (rewritten whole; corrupts under two writers), `.credentials.json`, `jobs/`
   (20 GB of scratch here), `plugins/` (rebuild from the manifest), `debug/`, `shell-snapshots/`,
   `session-env/`, `paste-cache/`, `file-history/` (rewind only), tailscaled state (duplicate node
   keys).
4. **One refresh token per machine.** Copying Claude Code's OAuth credential to two machines makes
   them race; whichever refreshes second is logged out. Log in per host, or route inference through
   a gateway that holds the credential.
5. **Snapshots and checkpoints are cache, never identity.** A restored VM checkpoint rewinds the
   session store with the code. Keep class-2 state in a sync tree that is never inside a rewindable
   image, and version it on the hub (ZFS or Time Machine + offsite), not with the sandbox vendor.
6. **APFS local snapshots are an undo buffer** (gone within ~24 h), not a history layer.
7. **Durability ends at the turn.** Transcripts are appended per message but a killed process
   loses its in-flight turn; parked permission prompts live in memory. Run sessions under tmux and
   give hosts a shutdown grace at least as long as a turn.
8. **Headless Macs:** FileVault on + auto-restart = stuck at the pre-boot login screen; auto-login is
   required for GUI-bound tools and menubar services; `pmset sleep 0 womp 1 autorestart 1`.
9. **Secrets in images and snapshots** are the recurring leak (`.npmrc` tokens in Cursor snapshots,
   setup secrets on Codex disks). Broker, don't bake.

## 6. The setup this was written for, measured

Three machines, all on one tailnet, two of them Macs with identical `/Users/new` paths:

| Machine | Role today | Measured 2026-09-30 |
|---|---|---|
| Laptop "SK" (M-series, 32 GB) | primary interactive | 12 live sessions, 5.8 GB of Claude-related RSS (≈0.5 GB/session) |
| Mac mini (M2 Pro, 16 GB, macOS 27) | already an always-on host | 9 live sessions, 4.6 GB Claude RSS, load ≈6, swap 1.8/3 GB used, 116k pageouts; Docker Desktop VM 0.6 GB; `sleep 0`, `womp 1`, FileVault off; the inference gateway (claude-usage-menubar, `127.0.0.1:8641`) running and already published tailnet-wide via `tailscale serve` on port 8641 |
| Hetzner worker host `ida-worker-1` | the July board-pipeline host | unreachable (timed out) — presumed retired |

Already in place: `~/.claude` hand-authored config is a git repo (`SSFSKIM/claude-config`) with a
structural JSON merge driver, synced by launchd every 30 minutes on both Macs; plugins and MCP
follow a manifest (`sync/apply.py`). Sessions are seats (`claude --bg`) under sminos with a
host-stamped registry. Inference for every session goes through the local gateway, which also
provides the GPT model rungs used by the review agents.

Findings that reshaped the design:
- **Remote Control does not work here.** Every recent session's debug log shows `bridge not
  enabled`; the documented cause is `ANTHROPIC_BASE_URL` pointing at the gateway. Decision: keep the
  gateway (model routing and usage tracking matter more); remote access is mosh + tmux; the phone is
  handled another way.
- **The mini is already at its RAM ceiling** at ~9–10 sessions. The "cloud" is therefore not a mirror
  but **elastic session compute** that carries the person's identity.
- **Real sync volume is 13–15 GB / 55k files** (`projects/`), growing 0.43–0.6 GB/day, compressing
  4.2×; `jobs/` holds 20 GB of scratch and is excluded.
- **Per-session isolation is not wanted** (confirmed by the human); the mini as the hub is wanted;
  the laptop stays a peer that runs sessions of its own, synced two-way with Mutagen.

## 7. The design, instantiated

**Hub = Mac mini** (identity, gateway, Mac-only capabilities, archive of record). Nothing to mirror
for it. Remaining hub work: versioning (Time Machine + nightly restic to B2; APFS local snapshots do
not count), and reclaiming RAM (stop Docker Desktop when idle; retire finished seats).

**Peers = laptop and one or more Linux session hosts.** A Linux session host is the July
`infra/worker-host` recipe (disposable body, volume as `$HOME`, cloud-init, Tailscale) with five
changes that turn a bot's soul into the person's:

1. **Path identity:** user `new`, uid 501, home `/Users/new`; repos under
   `/Users/new/Developer/GitHub/...` exactly as on the Macs.
2. **Config:** clone `claude-config` into `/Users/new/.claude`, run `sync/apply.py`; a systemd
   timer replaces the launchd job.
3. **Inference:** a local forwarder on `127.0.0.1:8641` to the mini's tailnet gateway
   (`socat TCP-LISTEN:8641,bind=127.0.0.1,fork OPENSSL:mac-mini.<tailnet>.ts.net:8641`), so the
   synced `settings.json` is true unchanged on every host and no Anthropic login is needed on the
   host — the gateway holds the credential.
4. **Mac-bound MCP servers as remote hands:** `cua_repl`, the Chrome-extension Playwright server and
   `codex_computer_use` are stdio servers; one wrapper script per server execs locally on macOS and
   `ssh mini …` on Linux, so the manifest entry is identical everywhere.
5. **Session store union:** Mutagen `two-way-safe` sessions host ⇄ mini and laptop ⇄ mini for
   `~/.claude/projects` (memory lives inside it), `plans/`, `tasks/`; ignore `sessions/`,
   `history.jsonl`, `debug/`, `file-history/` and everything in §5 item 3; `cleanupPeriodDays` set
   explicitly on all three hosts first; cross-host resume with `--fork-session`. Mutagen was chosen
   by the human; known risks: last release Feb 2025 with SSPL-licensed components, and 20–30 s on a
   chained hop (`storage-mirror.md` §3A). Syncthing is the fallback (with its own macOS FSEvents leak
   to watch, #10894).

**Sizing.** At ≈0.5 GB per session plus peaks, a 32 GB Linux host holds ~40 sessions; 64 GB ~80.
Candidates: Hetzner CAX41-class ARM (16 vCPU / 32 GB, roughly €25–35/month after the 2026
repricing) or a dedicated AX42/AX102 (64–128 GB, €45–124/month); or a home mini-PC with 64 GB (a
one-time ₩600–900k) on the same LAN as the mini. The Claude native binary ships for linux-arm64.

**Where sessions run.** sminos gains `--host <name>`: spawn a seat over SSH on a named host, attach
across hosts, list per host. Cross-host chats and inbox sockets remain per host; a family stays on
one host.

**Access from anywhere.** `mosh <host>` → tmux → `claude`; Screen Sharing over the tailnet for the
full macOS desktop ("beyond a dev environment").

**The honest alternative.** A 64 GB Mac mini (≈₩3M one-time) removes the RAM ceiling with no new
architecture and no sync; it wins if the target is under ~40 sessions and no off-site standby is
wanted. Above that, or if the home going dark must not stop work, the session-host design wins.

## 7a. Cost: the session host runs only while sessions are busy

An always-on 32 GB VM is the wrong default for one person: at Hetzner's 2026 prices a CAX41-class
ARM box is roughly €30–35/month whether or not a session is running, and Hetzner bills a *created*
server hourly even while it is powered off. The body/soul split already in `infra/worker-host`
makes scale-to-zero cheap instead: keep the volume (the soul, €5.72/month for 100 GB), and create
and delete the body on demand.

- **Create on demand.** `sminos spawn --host cloud` (M4) creates the server from a pre-baked
  Hetzner snapshot image (≈€0.01/GB-month; boots in well under a minute versus 2–5 minutes from
  raw cloud-init), attaches the volume, joins the tailnet, and spawns the seat. Cold start is one
  to two minutes end to end. The SSH host key lives on the volume and is restored at boot so the
  mini's Mutagen and SSH sessions see the same host every time.
- **Delete when nothing is busy.** Seats are already designed to be stopped and resumed from
  their transcript (`sminos wake`, `fill --resume`). A reaper on the host retires seats idle for
  N minutes and, when no seat is busy, deletes the server (a project-scoped API token on the
  volume). A message to a retired seat recreates the host and resumes it; the 1–2 minute wait is
  the price of scale-to-zero and lands on the person who sent the message, not mid-turn.
- **The mini initiates every sync.** Mutagen sessions are created from the mini toward each peer
  (`mutagen sync create ~/.claude/projects new@host:/Users/new/.claude/projects`), so a peer needs
  only sshd and the volume; a recreated body resumes the same Mutagen session.

Approximate monthly cost of a 32 GB session host (compute figures ±30%, Hetzner repriced in
2026-06; volume €5.72 included):

| Usage pattern | Hetzner on-demand body | Hetzner always-on | Fly Machine, stopped when idle | Home 64 GB box |
|---|---|---|---|---|
| ~4 busy hours/day | ≈ €12 | ≈ €36–41 | volume ≈ $15 + running hours (higher per-hour rate) | electricity ≈ ₩5k |
| ~12 busy hours/day | ≈ €24 | ≈ €36–41 | same, ×3 hours | same |
| 24/7 | ≈ €36–41 | ≈ €36–41 | ≈ Hetzner ×2–3 | same |

Fly Machines stop and start in seconds and a stopped machine bills only its volume, so Fly wins
when the 1–2 minute Hetzner recreate is too slow; it loses on per-hour price and on the January
2026 management-plane outages recorded in the July research. Sprites are cheaper still per busy
hour (≈ $0.11) but their Tailscale and keep-alive semantics (`product-landscape.md` §1) make the
gateway forward and the sync fragile; they fit a per-session throwaway computer, not a peer that
carries the person's identity. A home box has no marginal cost at all and only the home-dependence
already accepted for the mini.

**Why the body is a VM and not a container.** "VM" is not a principle here; it is what a
session host needs and what is cheapest for it. A session host must hold 32 GB or more for hours
to days, mount a persistent POSIX volume as `/Users/new` (transcripts are appended per message,
so object-backed FUSE mounts that rewrite whole objects on close are out), run sshd, mosh and
Tailscale with a tun device, have no lifetime cap, and cost little while idle. Container products
fail one of these each: Lambda (15 min), Vercel and E2B (24 h continuous), Cloud Run (no block
volume; Filestore's 1 TB minimum), Cloudflare (small instances, no persistent disk, in-container
work does not count as activity), and the sandbox APIs (Modal, Daytona, E2B) price per
GiB-second for bursty jobs, which for a 32 GB box held for hours comes to roughly $0.9–1.3 per
hour against about €0.05 for a Hetzner ARM VM — a 15–25× difference at the same RAM. Fly
Machines are the container-shaped exception: a Docker image run as a microVM with a volume,
stopped and started in seconds, billed only while running, at 2–3× Hetzner per hour. Inside the
host, sessions remain processes (P5); Docker on the host is available for projects that need it.
One shared volume also decides the topology: a block volume attaches to one body, so "one
container per session" would need a network filesystem from the hub, which the storage research
found fragile at WAN distance — hence one on-demand host per person, not one container per
session.

## 8. Plan of work (proposed milestones)

| # | Milestone | Depends on |
|---|---|---|
| M1 | Guardrails on the two Macs: `cleanupPeriodDays` explicit; prune `jobs/`; Time Machine + restic on the mini | — |
| M2 | Mutagen laptop ⇄ mini for `projects/`, `plans/`, `tasks/` with the ignore set; verify `--fork-session` resume from the other Mac | M1 |
| M3 | `infra/session-host/`: cloud-init derived from `worker-host` with the five changes of §7; bring up one host; verify a session there sees config, gateway, cua over SSH, and its transcript lands on the mini | M1 |
| M4 | sminos `--host`: spawn/attach/list across hosts | M3 |
| M5 | Standby drill: mini off → sessions continue on the host; laptop attaches; config edits merge | M3 |

Open decision (§7): cloud VM first, home Linux box, or the 64 GB mini instead.

## 9. What is still unverified

- Mutagen's behaviour on an 80 MB transcript being appended mid-sync (delta transfer is
  rsync-style; staging is atomic; conflict detection window undocumented).
- Whether `settings.env` values override or defer to shell env at startup (matters only if the
  forwarder approach in §7.3 is replaced by per-host `ANTHROPIC_BASE_URL`).
- Remote tool serving (`_host` routing) shipping publicly; if it does, an Anthropic-hosted session
  could use the mini as a hand without any of this.
- Hetzner ARM prices after the 2026-06 repricing; the figures above are approximate.
