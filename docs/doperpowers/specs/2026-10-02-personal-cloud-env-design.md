# Personal cloud agent environment — design

**Date.** 2026-10-02. **Status.** Presented for approval; routes to doperpowers:execspec.
**Research.** `docs/doperpowers/2026-09-30-personal-cloud-env-research.md` (+ four reports under
`docs/doperpowers/research/2026-09-30-personal-cloud-env/`). **Critique.** One round with
`doperpowers:critique` on 2026-10-02; converged positions are folded in and listed in §10.

## 1. Purpose

One person's agent environment should outlive a closed laptop, hold as many sessions as the work
needs rather than as many as one 16 GB Mac can swap, and still be *that person's computer*: their
config, credentials, tools, session history, and the things only their Macs can do. The initiative
builds the agent's home in the cloud and makes the two Macs peers and hands of it.

The higher purpose is the way of working this repository exists for: a person orchestrating many
long-running agent sessions, with the human's attention as the scarce resource. Anything that makes
a session harder to start, find, resume, or trust works against that purpose.

**Best manifestation.** From any terminal, `mosh devbox` → tmux → the same `claude` as on the Macs,
with the same `~/.claude`, the same model routing, the same plugins and MCP servers, the same
session list, and `ssh mini` or a cua call one tool away. Forty seats run while the laptop sleeps.
A session started on the Mac yesterday resumes on the devbox today. When the home goes dark, the
devbox keeps working on Anthropic directly. Nothing in this is a "cloud session" in Anthropic's
sense; it is the person's own computer, elsewhere.

**What it must not be.** A fleet (one trust domain, no per-session containers). A mirror of a Mac
(state is decomposed by class, not copied by machine). A second place to configure things (the
synced `settings.json` stays byte-identical on every host). A dependency on Anthropic's cloud
sessions, Remote Control, or self-hosted runners (all refused or inapplicable behind the relay).
A box that can delete its own soul (no write-scoped cloud token on the devbox).

## 2. Architecture

```
  laptop "SK" (peer: own sessions, mosh client)        tailnet, ACL-restricted
        ▲ mutagen (initiated by mini)                   ───────────────────────
        │
  Mac mini (hub: identity archive, relay, hands)  ◄── mutagen (initiated by mini) ──►  devbox (agent home)
   • ClaudeUsage relay, tailscale-served :8641                                        • Hetzner fsn1/nbg1 CAX41 ARM, Ubuntu 24.04
   • union of ~/.claude/projects (60-day live window)                                 • volume = /Users/new (btrfs zstd, daily ro snapshots, 365 d)
   • cua / Chrome / Keychain hands over ssh                                            • HAProxy 127.0.0.1:8641 → mini relay, fallback api.anthropic.com
   • controller: sync, watchers, reaper, restic                                       • seats under tmux + sminos, worktrees per session
   • runs few or zero seats after M3                                                  • restic of the volume → B2
```

Three roles. The **devbox** is the agent's home: a disposable Hetzner server ("body") around a
persistent volume ("soul") mounted as `/Users/new`. The **mini** is the hub: always on, holds the
relay every host's inference goes through, the union of session history, the Mac-only hands, and
every controller timer. The **laptop** is a peer: it runs sessions of its own, syncs them through
the mini, and reaches the devbox with mosh. The devbox holds a key to the mini only; nothing holds
a key to the laptop.

## 3. State classes and their mechanisms

| Class | Mechanism | Source of truth | History |
|---|---|---|---|
| Authored config (`~/.claude` whitelist: `settings.json`, `CLAUDE.md`, skills, agents, hooks, commands, keybindings, `sync/`, `tools/`) | existing `claude-config` git repo; `sync.sh` on a systemd timer on the devbox | git remote | git |
| Session state (`~/.claude/projects` incl. `memory/`, `plans/`, `tasks/`) | Mutagen `two-way-safe`, star topology initiated from the mini; one writer per file; `--fork-session` on cross-host resume | the writing host per file; mini = union | 60-day live window everywhere (`cleanupPeriodDays: 60` in the synced settings); devbox btrfs daily read-only snapshots kept 365 days = long online window; restic → B2 = disaster copy |
| Shared logs (`history.jsonl`), runtime (`sessions/`, `~/.claude.json`, `debug/`, `shell-snapshots/`, `session-env/`, `paste-cache/`, `file-history/`, `jobs/`, tailscaled state) | host-local, excluded from every sync | each host | none (devbox: btrfs snapshots incidentally) |
| Caches (`plugins/`, package caches) | rebuilt per host from the manifest (`sync/apply.py`) | manifest in git | git |
| Secrets (GitHub PAT, Tailscale auth key, setup-token fallback, restic key, Hetzner token on the mini) | the secret handler (§5); never plaintext in the repo or on the devbox disk except the one per-host root key | the vault (§5 fork) | vault |
| Repositories | git; canonical clones on the volume, worktrees per session; WIP pushed to `wip/<host>` branches | git remote | git |
| Device-bound capabilities (GUI, Chrome profile, Keychain, TCC, Xcode) | hands over ssh to the mini (§7) | the mini | — |

Path identity is the invariant that makes the second row portable: every host has user `new`
(uid 501), home `/Users/new`, repositories under `/Users/new/Developer/GitHub/<repo>`.

## 4. The devbox

**Provisioning** (`infra/devbox/`, derived from `infra/worker-host/`): cloud-init for Ubuntu 24.04
ARM; formats the volume as btrfs (`compress=zstd:3`, `noatime`) only when blank; mounts it at
`/Users` with a `home` subvolume at `/Users/new` and a `.snapshots` subvolume; creates user `new`
uid 501 with that home (`snap set system homedirs=/Users`, Chromium/Playwright non-snap); installs
git, build-essential, python3, Node LTS (nvm, as on the Macs), `gh`, `claude` (native installer,
as `new`), Tailscale, tmux, mosh, HAProxy, restic, rclone, mise; sets the per-body hostname
`devbox-<machine-id[:6]>` (host-aware seat liveness; `/etc/machine-id` is never persisted);
restores the SSH host key from the volume; `ufw` allows inbound only on `tailscale0` once the node
has joined. A hard gate aborts provisioning if `/Users` is not a mountpoint, as in worker-host.

**Server type.** CAX41 (16 vCPU ARM / 32 GB / 320 GB local NVMe), fsn1 or nbg1, €41.49/month at
2026-10 prices; ≈0.5 GB RSS per session measured on the Macs gives ~40 sessions of headroom. Stated
trade-off: ~250–300 ms RTT from Korea on every keystroke and every hand call, accepted for price;
Hetzner repriced 30–175% in 2026 without grandfathering (vendor risk, revisited at M6). The volume
(100 GB, delete-protected) is Ceph-backed: 5,000 IOPS / 200 MB/s. Transcripts are fine there;
whether worktrees, `jobs/` and the plugin cache move to the local NVMe (bind-mounted under the
home) is decided by an fio measurement in M3, not in advance.

**Identity seeding** (once per volume, never per body): clone `claude-config` into
`/Users/new/.claude`; `sync/apply.py` adds marketplaces, plugins, user-scope MCP servers; a
template seeds `~/.claude.json` with `projects["/Users/new/Developer/GitHub/<repo>"].hasTrustDialogAccepted`
for the canonical clones so detached seats never block on the trust dialog; `gh auth login` with the
single account PAT from the vault; one ssh key (restricted below) for the mini; git identity.

**Inference.** HAProxy listens on `127.0.0.1:8641` so the synced `settings.json`
(`ANTHROPIC_BASE_URL=http://127.0.0.1:8641`, the non-secret relay marker as the auth token) is true
unchanged. Backend `mini`: the mini's tailscale-served TLS endpoint (`ssl verify required`, system
CA, SNI); health check `GET /claudeusage/state` with the marker header, expecting an HTTP answer
from the relay itself (a TCP check would pass while the relay app is down, because `tailscale
serve` accepts the handshake). Backend `anthropic`: `api.anthropic.com` with the Authorization
header replaced by the setup-token from the vault, used only while `nbsrv(mini) == 0`. Failover is
connection-level only, never on 429/5xx: the relay deliberately holds requests near account limits,
and a response-level fallback would spend the fallback account outside the relay's ledger.
Consequences stated: the fallback is Claude-only (the GPT rungs the review agents use are relay
routing), and a flip changes account so prompt caches rebuild once. The config is root-owned 0600,
rendered from the vault. Managed settings (`/etc/claude-code/managed-settings.json`) remain the
documented mechanism for any other per-host divergence, since policy settings beat the synced user
settings and settings `env` is assigned over the shell environment.

**Sessions.** Interactive: `mosh devbox` → tmux. Detached: sminos seats (`claude --bg`), registry on
the volume, host-stamped. Cross-session messaging works among seats on the devbox as on one
computer. Remote Control is not used.

## 5. Secrets

The handler is `~/.claude/tools/secret-env` (synced): it resolves `secret://<name>` references into
environment variables at session or shell start, caches nothing on disk, and has a pluggable
backend. Two backends are candidates; this is the design's one open fork (§9).

- **sops + age, inside `claude-config`.** `sync/secrets.yaml` encrypted to one age recipient per
  host; the per-host age key is the only hand-seeded secret (0600 on the volume / in the Mac's
  home). No network at boot, no SaaS, four strings today.
- **GCP Secret Manager.** The laptop reads with its existing ADC (project `ytdownload-505811`).
  The devbox has no GCP identity and Hetzner offers no OIDC issuer, so it can only authenticate with
  a service-account key file on the volume — a secret to protect the secrets — and needs the
  network at boot. Gains central UI, audit, versioning, rotation.

Either way: no plaintext secret in the repo; the relay marker is not a secret and stays in
`settings.json`; the Hetzner token lives only on the mini (controller) and the laptop (operator).

## 6. Sync, windows, archives

- **Mutagen** is installed on the mini only; it creates two sessions (mini ⇄ devbox, mini ⇄ laptop)
  over ssh with `--sync-mode two-way-safe`, roots `~/.claude/projects`, `~/.claude/plans`,
  `~/.claude/tasks`, and the exclusion set of §3. Peers need only sshd. The chained laptop → mini →
  devbox hop is 20–30 s; acceptable for transcripts. The ignore set and conflict policy are kept
  tool-agnostic so Syncthing can replace Mutagen (unmaintained since 2025-02).
- **Conflicts** (`memory/*.md`, `plans/*.md` are multi-writer): a watcher timer on the mini runs
  `mutagen sync list`, and for each conflict keeps the newer mtime, moves the loser to a sibling
  `<name>.conflict-<host>-<ts>` on its host (which then syncs as a new file), and notifies only when
  the same path conflicts repeatedly. Nothing is lost; the stall ends without a human.
- **Live window:** `cleanupPeriodDays: 60` in the synced settings (today 36500). Deletions
  propagate, so the smallest disk bounds the window: the mini has 113 GB free against 1–1.5 GB/day
  from three hosts. Alternative if the window must grow: `projects/` on an external NVMe on the mini.
- **Long window:** daily `btrfs subvolume snapshot -r` of the devbox home into `.snapshots/`, kept
  365 days; nearly free for append-only files at 4.2× zstd. A swept transcript is still there,
  greppable, and resumable by copying it back under `projects/<key>/` and `--fork-session`.
- **Disaster copy:** restic nightly from the mini (the union) and from the devbox (the whole
  volume: repo WIP, `~/.codex`, caches excluded) to one B2 repository. Time Machine excludes
  `~/.claude/projects` (whole-file hourly copies of 80 MB transcripts would churn tens of GB/day);
  the mini has no Time Machine destination today, so M1 creates the restic backup rather than
  keeping one.
- **To verify in M2:** that Mutagen preserves mtime on the receiving side (the sweep is mtime-based;
  if arrival time is stamped, a re-seeded peer restarts the window).

## 7. Hands and security

- The devbox's ssh key is authorized on the mini only, with `from="100.64.0.0/10"` on the
  `authorized_keys` line, so an exfiltrated key works only from the tailnet. It is a full-shell key:
  GUI automation of the mini is full control of the mini anyway, and general bash/python-heredoc
  hands are the point. The laptop is the hard boundary: nothing reaches it.
- Mac-bound stdio MCP servers (`cua_repl`, the Chrome-extension Playwright server,
  `codex_computer_use`) run through one wrapper, `~/.claude/tools/mcp-hand <server>`, which execs
  the server locally on Darwin and `ssh mini …` elsewhere; the manifest (`sync/mcp.json`) names the
  wrapper so every host carries the same entry. Preconditions on the mini: auto-login GUI session,
  ChatGPT.app resident for cua, per-app approvals pre-granted (`CUA_SHIM_PERSIST=always`). The
  Chrome profile the Playwright extension uses lives on the mini.
- **Tailscale ACLs before M3.** The tailnet has ~890 ephemeral `writer-`/`chapter-` nodes from
  other projects; today any of them, while online, can reach the relay (tailscale serve is
  tailnet-wide and the relay has no client authentication). Policy: tag the devbox `tag:devbox`;
  only `tag:devbox` and the laptop reach `mac-mini:8641` and `:22`; the worker tags reach nothing on
  the Macs. This exposure predates the design and is fixed first.
- No Hetzner write token on the devbox. The reaper and every cloud API call run on the mini; the
  volume has delete protection on.
- A richer remote-file MCP (read with image/PDF content blocks, edit with read-before-write
  tracking, tailnet-only HTTP on each Mac) is a separate later goal, not this initiative.

## 8. Observability, elasticity, fallback

- Timers on the mini: Mutagen conflict/health, relay reachability from the devbox (HAProxy stats),
  restic success, disk headroom on the mini and the volume. Notification through the existing
  notify hook; a push channel (ntfy) is optional.
- Elasticity (later milestone): `hcloud server change-type --keep-disk` between CAX11 (idle,
  ≈€4/month) and CAX41 (busy), driven from the mini when no seat is busy / on the first spawn. Same
  host identity, host key, tailnet node, Mutagen session; no snapshot image to keep fresh. The
  earlier delete-and-recreate design is superseded.
- The inference fallback (§4) is in v1; a Linux build of the relay's gateway target (it is already
  a separate Swift target with a `CredentialSource` protocol) is the mature endpoint for "the
  devbox's own login" and a separate later goal.
- `claude` auto-updates on each host; `minimumVersion` in the synced settings bounds skew.

## 9. Open fork — secrets backend

| | sops + age in claude-config | GCP Secret Manager |
|---|---|---|
| per-host root secret | age private key file | service-account key JSON |
| boot/network dependency | none | yes (session start fetches; needs caching) |
| management | edit an encrypted YAML in git | console, audit, versions, rotation, IAM |
| fits | four strings, one person, headless box | many secrets, several principals, compliance |

Recommendation: sops + age now; the handler's backend flag lets GCP replace it later without
touching callers. The human asked for GCP first, so this is theirs to decide.

## 10. Decision log (from research and critique)

1. Cloud devbox over a bigger Mac mini or a home Linux box — justified by the standby property only
   because the inference fallback is in v1; the home box stays the named alternative.
2. btrfs over ZFS on the volume: in-kernel (no DKMS failure after an unattended kernel update),
   zstd, snapshots, online grow; monthly defragment of `projects/`, qgroups off.
3. HAProxy on 127.0.0.1:8641 over socat or a per-host managed-settings override: keeps the synced
   settings identical everywhere and makes failover automatic for running seats; HAProxy, not
   custom code, because 40 concurrent SSE streams are exactly what a small proxy gets wrong.
4. Mutagen initiated from the mini: peers need only sshd; a recreated or re-typed body resumes the
   same session.
5. Always-on first, change-type elasticity later: €41 vs ~€15 is not worth a reaper before the duty
   cycle is known.
6. Hands on the mini only; full-shell key with a `from=` restriction; no forced-command dispatcher
   (theater when cua already means full control).
7. Live window 60 days + btrfs long window + restic, replacing "everything live forever" and Time
   Machine for `projects/`.
8. The relay marker is not a secret; the vault holds four strings.
9. No per-repo GitHub tokens: one account credential, injected by the handler (the human's call,
   2026-10-02).
10. Per-session isolation not wanted; sessions share one computer's semantics.

## 11. Delegated unknowns

- fio on the volume vs local NVMe (M3) → decides what lives on the NVMe.
- Mutagen mtime preservation (M2) → decides whether re-seeding a peer needs a touch-back.
- cua / Playwright over ssh from Linux (M3 day one) → decides whether the wrapper needs a
  persistent agent on the mini instead of per-call ssh.
- HAProxy health route: `GET /claudeusage/state` with the marker; if the relay refuses it without
  a session, add `/healthz` to the relay (the human owns it).
- Hetzner CAX41 availability on the day (stock varies by location).

## 12. Plan of work (outline for execspec)

| # | Milestone | Outcome |
|---|---|---|
| M0 | Tailnet ACLs; Hetzner project + token on the laptop and mini | the relay reachable only from the Macs and `tag:devbox` |
| M1 | Hub prep on the mini: Mutagen, restic → B2, `cleanupPeriodDays: 60`, TM exclusion, conflict watcher, `jobs/` pruned | the union has an archive and a window |
| M2 | Mini ⇄ laptop sync live; `--fork-session` cross-host resume verified; mtime check | two Macs share one session history |
| M3 | `infra/devbox/`: cloud-init, volume, identity seeding, HAProxy with fallback, hands wrapper, trust seeding; first session over mosh; cua over ssh; fio | the devbox is the person's computer |
| M4 | Mini ⇄ devbox sync; seats on the devbox under sminos; mini runs few or zero seats | elastic sessions, one history |
| M5 | Observability timers; standby drill (mini off → devbox keeps working on Anthropic) | the standby is real |
| M6 | Elasticity via change-type; cost review against the duty cycle | scale-to-idle |
